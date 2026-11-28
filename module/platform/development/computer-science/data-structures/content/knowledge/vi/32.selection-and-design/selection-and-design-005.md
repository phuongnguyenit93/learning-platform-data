# Đánh đổi giữa bảo đảm xấu nhất, kỳ vọng và khấu hao

Cùng một phép toán `insert(x)`, tài liệu có thể ghi `O(1)`, `O(log n)` hoặc `O(n)` mà **không nhất thiết mâu thuẫn**. Lý do là mỗi kết quả có thể nói về một kiểu bảo đảm khác nhau: chi phí ở **trường hợp xấu nhất** (*worst case*), chi phí **kỳ vọng** (*expected*) hoặc chi phí **khấu hao** (*amortized*).

Trong chương *Lựa chọn và thiết kế* cấu trúc dữ liệu, đây là ba góc nhìn bắt buộc phải phân biệt. Khi học mảng động, stack, queue, bảng băm, cây tìm kiếm, heap và đồ thị, ta không chỉ quan tâm thao tác nào nhanh mà còn cần biết **lời hứa hiệu năng áp dụng cho một yêu cầu hay cho cả chuỗi yêu cầu**, giả định nào khiến lời hứa đúng, và có đáp ứng giới hạn thời gian/bộ nhớ của hệ thống hay không.

Bài học đi từ khái niệm đến ví dụ và cách lựa chọn thực tế. Các độ phức tạp dưới đây nói về số bước tính toán trong một mô hình thuật toán phù hợp; **không tự động là cam kết độ trễ tính bằng mili giây**, vì cấp phát bộ nhớ, cache, đồng bộ và môi trường chạy cũng ảnh hưởng thời gian thực.

## 1. Ba loại bảo đảm trả lời ba câu hỏi khác nhau

Giả sử cấu trúc chứa `n` phần tử và ta thực hiện một thao tác `op`.

| Loại phân tích | Câu hỏi thực sự | Kết luận mẫu |
| --- | --- | --- |
| **Trường hợp xấu nhất** (*worst-case*) | Trong mọi trạng thái và đầu vào hợp lệ có kích thước `n`, thao tác có thể tốn tối đa bao nhiêu bước? | Tìm trong AVL có `O(log n)` phép so sánh ở trường hợp xấu |
| **Kỳ vọng** (*expected*) | Nếu có biến ngẫu nhiên với giả định được nêu rõ, chi phí trung bình theo phân bố đó là bao nhiêu? | Tra cứu bảng băm thường có kỳ vọng `O(1)` dưới giả định băm phù hợp và hệ số tải được khống chế |
| **Khấu hao** (*amortized*) | Trong *một chuỗi* gồm `m` thao tác, tổng chi phí có được chặn tốt, dù có thao tác riêng lẻ rất đắt? | Thêm cuối mảng động tăng dung lượng theo cấp số nhân có `O(1)` khấu hao |

Ba cách phân tích có thể cùng đúng cho một cấu trúc, nhưng diễn đạt **các bảo đảm khác nhau**.

### 1.1. Trường hợp xấu nhất: chặn cho từng thao tác

Gọi `C(op, D)` là số bước của phép toán `op` khi cấu trúc đang ở trạng thái `D`. Trường hợp xấu nhất ở quy mô `n` xét giá trị lớn nhất của `C` trên các trạng thái và đầu vào hợp lệ phù hợp quy mô.

Ví dụ:

- Tìm trên một **cây tìm kiếm tự cân bằng** có chiều cao `O(log n)`, nên số bước đi từ gốc xuống vị trí tìm được chặn bởi `O(log n)`.
- Truy cập mảng `A[i]` với `i` hợp lệ mất `O(1)` trong mô hình RAM vì có thể tính trực tiếp vị trí.
- Tìm khóa trong **danh sách liên kết không có chỉ mục** có thể phải kiểm tra `n` nút, nên trường hợp xấu `O(n)`.

Nếu một phép toán được bảo đảm `O(log n)` trường hợp xấu, ta biết **mỗi lần gọi** đều có chặn tiệm cận đó khi bất biến được duy trì. Tuy nhiên, phát biểu `O(log n)` không khẳng định mọi lần đều mất một số mili giây cố định hay bất biến trước việc dừng luồng, thu gom rác, truy cập đĩa hoặc tranh chấp khóa.

### 1.2. Kỳ vọng: cần chỉ rõ ngẫu nhiên đến từ đâu

Nếu chi phí là biến ngẫu nhiên `X`, giá trị kỳ vọng là:

```text
E[X] = tổng theo mọi kết quả ω của Pr[ω] × X(ω)
```

Tính kỳ vọng phải dựa vào **một mô hình xác suất cụ thể**:

- Cấu trúc tự dùng ngẫu nhiên, ví dụ **treap** gán mức ưu tiên ngẫu nhiên cho nút; kỳ vọng được tính trên lựa chọn mức ưu tiên.
- Hàm băm được chọn ngẫu nhiên từ họ hàm băm đáp ứng giả định thích hợp; kỳ vọng được tính trên lựa chọn hàm băm.
- Hoặc người phân tích giả định dữ liệu đầu vào tuân theo một phân bố đã định; khi ấy kỳ vọng phụ thuộc phân bố đầu vào đó.

Câu “dữ liệu thực tế thường ngẫu nhiên” chưa phải chứng minh. Nếu khóa được kiểm soát bởi bên ngoài, có va chạm băm hoặc phân bố lệch mạnh, giả định xác suất có thể không còn phản ánh tải công việc.

**Kỳ vọng thấp không đồng nghĩa không có thao tác chậm.** Một phép toán có thể kỳ vọng `O(1)` nhưng có những trường hợp tốn `Θ(n)`. Giá trị trung bình cũng không trực tiếp cho biết p95, p99 hay thời gian lớn nhất.

### 1.3. Khấu hao: chặn tổng chi phí của cả chuỗi

Xét chuỗi `m` thao tác với chi phí thực lần lượt là `c_1, c_2, ..., c_m`. Nếu chứng minh được:

```text
c_1 + c_2 + ... + c_m ≤ A × m + B
```

với `A` và `B` không tăng theo `m` trong phạm vi giả định đã nêu, thì chi phí khấu hao bình quân mỗi thao tác có thể là `O(1)`. Với bài toán phụ thuộc `n`, ta dùng dạng tổng phù hợp, ví dụ `O(m log n)`.

**Khấu hao không cần giả định ngẫu nhiên.** Một thao tác có thể tốn `Θ(n)` nhưng vẫn có `O(1)` khấu hao nếu nhiều thao tác rẻ trước đó “trả trước” cho lần đắt này. Bảo đảm khấu hao gắn với **toàn bộ chuỗi hợp lệ** và quy tắc vận hành cấu trúc.

Điểm quan trọng: `O(1)` khấu hao không phải `O(1)` trường hợp xấu **cho từng thao tác**, và cũng không phải “mỗi thao tác được lấy trung bình trên các bộ dữ liệu ngẫu nhiên”.

## 2. Ví dụ nền tảng: mảng động và thao tác `pushBack`

Mảng động giữ hai thông số:

- `size`: số phần tử hiện có.
- `capacity`: số phần tử vùng nhớ đang cấp phát chứa được.

Bất biến là `0 ≤ size ≤ capacity`, và phần tử đang dùng nằm ở vị trí `0..size-1`. Giả sử khi đầy, mảng cấp phát vùng mới có dung lượng **gấp đôi** rồi sao chép toàn bộ phần tử cũ.

```text
pushBack(x):
    if size == capacity:
        newCapacity = max(1, 2 * capacity)
        newArray = allocate(newCapacity)
        copy(newArray, oldArray, size)  // sao chép size phần tử
        oldArray = newArray
        capacity = newCapacity

    oldArray[size] = x
    size += 1
```

Nếu còn chỗ trống, `pushBack` chỉ ghi một phần tử: `O(1)`. Nhưng nếu `size = capacity = n`, lần chèn kế tiếp phải sao chép `n` phần tử rồi mới ghi phần tử mới: **`Θ(n)` trường hợp xấu**.

### 2.1. Vì sao tổng chi phí vẫn tuyến tính?

Bắt đầu từ mảng rỗng, thực hiện `m` lần `pushBack`:

- Mỗi lần chèn phải ghi phần tử mới, tổng khoảng `m` lần ghi.
- Các lần tăng dung lượng sao chép số phần tử cũ lần lượt xấp xỉ `1, 2, 4, 8, ...`, nhỏ hơn `2m` phần tử được sao chép trong cả chuỗi.
- Tổng công việc ghi/sao chép là `O(m)`, nên **mỗi lần chèn có chi phí khấu hao `O(1)`**.

```text
Dung lượng sau khi tăng:     1 → 2 → 4 → 8 → 16 → ...
Số phần tử được sao chép:      1   2   4    8  ...
Tổng trước khi đạt m:       1 + 2 + 4 + ... < 2m
```

Đây là lý do mảng động thường phù hợp cho luồng dữ liệu chỉ thêm cuối. Tuy nhiên, **một lần** chèn đúng thời điểm cần tăng dung lượng vẫn có thể chậm bất thường; thuật toán khấu hao không xóa được sự kiện ấy.

### 2.2. Ba kết luận khác nhau về cùng thao tác

| Câu hỏi | Với `pushBack` trên mảng động nhân đôi |
| --- | --- |
| Một lần chèn bất kỳ có thể tốn bao nhiêu? | `O(n)` trường hợp xấu nếu phải mở rộng mảng |
| Trong `m` lần chèn liên tiếp, tổng thời gian là bao nhiêu? | `O(m)` theo phân tích khấu hao, tính cả sao chép |
| Có cần khóa ngẫu nhiên hoặc đầu vào ngẫu nhiên để đạt chặn tổng này? | **Không**; đúng với chuỗi chèn hợp lệ trong mô hình đã nêu |

Nếu dùng mảng có dung lượng **cố định và đủ lớn**, việc thêm cuối khi còn chỗ có thể là `O(1)` trường hợp xấu, nhưng phải quyết định rõ chuyện gì xảy ra khi đầy: từ chối, chặn, hoặc chuyển sang vùng nhớ khác. Nếu dùng `reserve(maxSize)`, ta đã **trả trước chi phí bộ nhớ** để tránh một số lần mở rộng sau đó.

### 2.3. Xóa phần tử và hiện tượng tăng/giảm liên tục

Nếu mảng cứ **đầy thì nhân đôi, nửa đầy thì lập tức chia đôi**, một chuỗi thêm/xóa gần ranh giới có thể khiến mảng liên tục cấp phát và sao chép. Chỉ biết quy tắc tăng dung lượng là chưa đủ để chứng minh tốt cho **cả chèn và xóa**.

Một cách triển khai phổ biến là tạo **khoảng cách ngưỡng** (*hysteresis*): nhân đôi khi đầy nhưng chỉ giảm một nửa khi số phần tử tụt xuống khoảng một phần tư dung lượng. Quy tắc này giúp tránh các lần đổi dung lượng liên tiếp do dao động một phần tử và có thể chứng minh chi phí khấu hao `O(1)` cho chèn/xóa cuối, trong giả định cấp phát và sao chép tương ứng.

Nếu xóa ở giữa dãy phải dồn phần tử để giữ thứ tự, thao tác ấy vẫn là `O(n)`; bảo đảm khấu hao của **thêm/xóa cuối** không tự mở rộng sang **xóa bất kỳ**.

## 3. Bảng băm: kỳ vọng từ va chạm, khấu hao từ tái băm

Hash map/set được dùng cho `get(key)`, `put(key,value)` và `remove(key)`. Với bảng băm thông thường, hai nguồn chi phí cần phân biệt:

1. **Va chạm:** nhiều khóa rơi cùng bucket hoặc cùng chuỗi thăm dò.
2. **Thay đổi kích thước:** khi hệ số tải tăng quá ngưỡng, có thể phải cấp phát bảng lớn hơn và chuyển nhiều phần tử sang vị trí mới (*rehash*).

### 3.1. Vì sao tra cứu thường được nói là kỳ vọng `O(1)`?

Giả sử `n` khóa nằm trong bảng có `b` bucket, hệ số tải là:

```text
α = n / b
```

Với **separate chaining**, nếu hàm băm phân phối khóa đủ đều theo giả định chuẩn, số phần tử trung bình cần kiểm tra trong bucket có thể được phân tích theo `O(1 + α)`. Giữ `α` bị chặn bởi hằng số giúp chi phí kỳ vọng của tra cứu đạt `O(1)` trong mô hình thích hợp.

Với **open addressing**, chi phí kỳ vọng còn phụ thuộc cách thăm dò, hệ số tải và mô hình băm; thường phải giữ hệ số tải đủ thấp. Không được lấy kết quả của một chiến lược va chạm để tự động áp dụng cho tất cả triển khai.

Bảng băm **không mặc định có bảo đảm `O(1)` cho mọi khóa và mọi trạng thái**:

- Trong separate chaining không có cơ chế tăng cường, `n` khóa có thể cùng rơi vào một bucket và một lần tìm mất `O(n)`.
- Với open addressing, chuỗi thăm dò có thể dài, đặc biệt khi bảng gần đầy hoặc khóa phân bố bất lợi.
- Nếu một lần thêm kích hoạt rehash, phép toán ấy có thể phải xử lý `Θ(n)` phần tử.

Có thư viện dùng các cấu trúc bổ sung như cây trong bucket hoặc cơ chế chống va chạm, nhờ đó có những chặn khác. Cần xem **đúng hợp đồng của triển khai cụ thể**, không suy bảo đảm từ tên “hash map”.

### 3.2. Vì sao thêm vào bảng băm có thể vừa kỳ vọng vừa khấu hao?

Giả sử một bảng tăng dung lượng theo cấp số nhân khi vượt ngưỡng tải:

- Trong các lần thêm **không mở rộng**, chi phí tìm bucket/ghi là kỳ vọng `O(1)` với giả định băm phù hợp.
- Những lần **mở rộng** phải di chuyển các mục cũ; xét một chuỗi thêm đủ dài, tổng số mục phải tái băm được chặn theo một cấp số nhân, như mảng động.
- Vì vậy, trong mô hình phù hợp có thể nói: **chi phí kỳ vọng khấu hao `O(1)` cho mỗi lần thêm**.

Hai từ “kỳ vọng” và “khấu hao” ở đây **giải quyết hai nguồn biến động khác nhau**: kỳ vọng xử lý phân phối va chạm; khấu hao xử lý chi phí tái phân bổ theo chuỗi. Một lần thêm cụ thể vẫn có thể tốn `Θ(n)`.

Không nên diễn giải phát biểu đó thành chặn trường hợp xấu khi người dùng chủ động chọn khóa gây va chạm hoặc có thể quan sát/điều chỉnh theo hàm băm. Khi dữ liệu đến từ bên ngoài, cần xét tính chống đầu vào đối kháng, giới hạn tài nguyên và chính sách băm của thư viện.

### 3.3. Mô hình thao tác cụ thể

| Thao tác | Kết quả điển hình với hash map thông dụng | Điều kiện / ngoại lệ |
| --- | --- | --- |
| `get(key)` | Kỳ vọng `O(1)` | Phụ thuộc giả định băm, tải và cách xử lý va chạm; trường hợp xấu có thể `O(n)` |
| `put(key,value)` không resize | Kỳ vọng `O(1)` | Có thể chịu chuỗi va chạm dài |
| `put(key,value)` có resize | Một lần có thể `O(n)` | Rehash nhiều mục; chi phí được khấu hao trên chuỗi thêm |
| `remove(key)` | Thường kỳ vọng `O(1)` trong điều kiện tương tự | Có thể còn chi phí xử lý tombstone/thu nhỏ hoặc tái cấu trúc |
| Duyệt toàn bộ | Phụ thuộc số mục và cấu trúc bucket | Thứ tự duyệt thường không bảo đảm theo thứ tự khóa |

Hash map tốt cho **tra cứu chính xác**, nhưng không tự hỗ trợ hiệu quả `lowerBound(key)`, duyệt khóa tăng dần hay truy vấn khoảng. Nếu ứng dụng cần những phép toán ấy, hãy cân nhắc cây có thứ tự hoặc chỉ mục thứ hai.

## 4. Cây tìm kiếm: trả thêm `log n` để đổi lấy chặn xấu nhất

Cây tìm kiếm nhị phân giữ bất biến:

- Các khóa ở cây con trái nhỏ hơn khóa nút hiện tại.
- Các khóa ở cây con phải lớn hơn khóa nút hiện tại.
- Nếu cho phép khóa trùng, phải có quy tắc nhất quán về lưu trữ hoặc khóa ghép.

Nhưng **bất biến thứ tự không tự bảo đảm cây thấp**. Nếu lần lượt chèn `1,2,3,...,n` vào BST thông thường không cân bằng, cây có thể biến thành một đường dài `n` nút:

```text
1
 \
  2
   \
    3
     \
      4
       \
        5
```

Khi đó tìm/chèn theo đường đi dài có thể mất `Θ(n)` trong trường hợp xấu.

### 4.1. AVL và red-black tree

Cây tìm kiếm **tự cân bằng** duy trì thêm bất biến về chiều cao/màu sắc để chiều cao luôn `O(log n)`. Do đó:

- `find(key)`: `O(log n)` **trường hợp xấu**.
- `insert(key)` và `delete(key)`: `O(log n)` **trường hợp xấu** với triển khai chuẩn.
- `lowerBound(key)`: `O(log n)` trường hợp xấu.
- Liệt kê `k` phần tử liên tiếp theo thứ tự: `O(log n + k)` khi bắt đầu từ cận và dùng bộ duyệt thích hợp.

Đổi lại, mỗi nút và mỗi lần cập nhật cần công sức duy trì liên kết, màu sắc/chiều cao hoặc metadata. Cấu trúc dạng cây thường có locality kém hơn mảng và overhead bộ nhớ cho nút. Đối với tra cứu khóa chính xác trong tải thông thường, hash map có thể nhanh hơn dù bảo đảm yếu hơn.

### 4.2. Treap và cấu trúc ngẫu nhiên

**Treap** kết hợp thứ tự BST theo `key` với thứ tự heap theo `priority` ngẫu nhiên. Nếu mức ưu tiên được chọn độc lập, phù hợp và giữ nguyên trong đời nút, có thể phân tích chiều cao/chi phí tìm kiếm, chèn và xóa ở **kỳ vọng `O(log n)`**.

Nhưng một cấu hình ưu tiên bất lợi vẫn có thể tạo cây cao `Θ(n)`. Do đó:

- AVL/red-black tree: bảo đảm logarithmic theo **trường hợp xấu**.
- Treap chuẩn: bảo đảm logarithmic theo **kỳ vọng**, với giả định ngẫu nhiên thích hợp.
- BST thường: không có bảo đảm cân bằng; trường hợp xấu `Θ(n)`.

Việc một cấu trúc là “cây” không đủ để suy độ phức tạp. Phải biết chính xác **bất biến cân bằng hoặc phân bố ngẫu nhiên** mà thuật toán dựa vào.

### 4.3. Vì sao đôi khi chọn cây dù hash map kỳ vọng nhanh hơn?

Giả sử dịch vụ nhận khóa từ khách hàng và cần `lowerBound`, xóa theo khóa, duyệt tăng dần. Một cây tự cân bằng có thể hấp dẫn vì:

1. Những phép toán có thứ tự là chức năng chính, không thể khai thác trực tiếp bằng hash map thông thường.
2. Tìm, chèn và xóa theo khóa được chặn bởi `O(log n)` ở trường hợp xấu.
3. Hệ thống ít phụ thuộc giả định va chạm băm và phân bố khóa.

Chấp nhận chi phí `log n` cho mỗi thao tác có thể là đánh đổi hợp lý để nhận **bảo đảm rõ ràng hơn** và ngữ nghĩa đúng. Tuy vậy, chặn thuật toán không loại bỏ các nguồn trễ ngoài thuật toán như truy cập đĩa, bộ gom rác hoặc tranh chấp giữa các luồng.

## 5. So sánh trên nhiều cấu trúc quen thuộc

Bảng sau giả định các triển khai cơ bản trong RAM, bỏ qua chi phí hệ thống bên ngoài thuật toán. `n` là số phần tử, `L` là độ dài khóa; “trường hợp xấu” nghĩa là cho **một phép toán**, trừ khi ghi rõ dạng khác.

| Cấu trúc và thao tác | Bảo đảm điển hình | Rủi ro / điều kiện |
| --- | --- | --- |
| Mảng: `get(i)` hợp lệ | `O(1)` trường hợp xấu | Cần chỉ số hợp lệ và mảng hỗ trợ truy cập trực tiếp |
| Mảng động: thêm cuối khi còn chỗ | `O(1)` trường hợp xấu | Chỉ đúng khi không phải mở rộng |
| Mảng động: thêm cuối có tăng dung lượng | `O(1)` khấu hao, có lần `O(n)` | Cần quy tắc tăng dung lượng theo cấp số nhân |
| Stack/queue trên mảng vòng cố định | `O(1)` trường hợp xấu cho push/pop hoặc enqueue/dequeue trong điều kiện cho phép | Phải quyết định xử lý khi đầy/rỗng |
| Stack/queue trên mảng động | Thao tác đầu/cuối phù hợp thường `O(1)` khấu hao | Resize có thể khiến một lần thao tác `O(n)` |
| Danh sách liên kết đôi: xóa khi đã có nút | `O(1)` trường hợp xấu cho sửa liên kết | Tìm nút theo khóa có thể là `O(n)` |
| Hash map: `get(key)` | Kỳ vọng `O(1)` dưới giả định thích hợp | Trường hợp xấu thông dụng có thể `O(n)` |
| Hash map: `put(key)` có resize | Kỳ vọng khấu hao `O(1)` dưới giả định thích hợp | Va chạm và rehash; có lần `O(n)` |
| BST không cân bằng: tìm | `O(h)` với chiều cao `h`; xấu nhất `O(n)` | Đầu vào tăng dần có thể làm cây suy biến |
| AVL/red-black tree: tìm/chèn/xóa | `O(log n)` trường hợp xấu | Phải duy trì bất biến cân bằng |
| Treap: tìm/chèn/xóa | Kỳ vọng `O(log n)` | Cần giả định mức ưu tiên ngẫu nhiên; xấu nhất `O(n)` |
| Min-heap nhị phân: xem đỉnh | `O(1)` trường hợp xấu | Chỉ trả phần tử ưu tiên cực trị |
| Min-heap nhị phân: thêm/lấy đỉnh | `O(log n)` trường hợp xấu cho điều chỉnh heap | Nếu mảng nền cần resize, một lần thêm có thể `O(n)` vì cấp phát/sao chép |
| Trie: tìm khóa dài `L` | `O(L)` trường hợp xấu khi truy cập mỗi cạnh `O(1)` | Bộ nhớ phụ và chi phí xử lý Unicode |
| Fenwick/segment tree: cập nhật điểm, tổng đoạn | `O(log n)` trường hợp xấu | Bất biến tổng hợp phải được duy trì |
| BFS/DFS dùng danh sách kề | `O(V+E)` trường hợp xấu để thăm đỉnh/cạnh | Chi phí là của **toàn bộ lượt duyệt**, không phải mỗi cạnh được hỏi |

**Chú ý về heap và queue:** người ta thường ghi thao tác heap `O(log n)` và queue `O(1)` theo cấu trúc logic. Nếu triển khai bằng mảng động chưa đủ dung lượng, **chi phí mở rộng mảng** phải được cộng vào khi cần chặn từng lời gọi. Có thể dùng dung lượng cấp sẵn, bộ nhớ chia khối hoặc cơ chế khác để thỏa ràng buộc độ trễ, nhưng phải phân tích lại chính triển khai ấy.

**Chú ý về graph:** ma trận kề cho phép `hasEdge(u,v)` trong `O(1)` trường hợp xấu theo truy cập mảng, đổi lại `O(V²)` bộ nhớ. Danh sách kề chỉ cần `O(V+E)` bộ nhớ nhưng `hasEdge(u,v)` có thể tốn `O(deg(u))` nếu phải quét hàng xóm. Nếu đổi sang tập băm cho từng danh sách hàng xóm, ta lại mang các giả định kỳ vọng/va chạm của hash set vào truy vấn kiểm tra cạnh.

## 6. Khấu hao được chứng minh bằng cách nào?

Việc nói “trung bình về lâu dài sẽ nhanh” không đủ để chứng minh bảo đảm. Phân tích khấu hao có các phương pháp chuẩn.

### 6.1. Phương pháp cộng dồn (*aggregate analysis*)

Chứng minh trực tiếp tổng chi phí của `m` thao tác không vượt một chặn thích hợp, sau đó chia cho `m`.

Với mảng động nhân đôi, tổng số lần sao chép khi mở rộng trong `m` lần thêm cuối nhỏ hơn một hằng số nhân `m`, nên tổng chi phí `O(m)`. Đây là cách chứng minh ở phần trước.

### 6.2. Phương pháp tài khoản (*accounting method*)

Gán cho mỗi thao tác một **chi phí khấu hao** có thể cao hơn chi phí thực của thao tác rẻ. Phần chênh lệch được giữ thành “tín dụng” trả cho những lần tái cấu trúc đắt về sau.

Ví dụ, với mảng nhân đôi, mỗi lần thêm trả một lượng tín dụng hằng số; các lần thêm rẻ tích lũy đủ tín dụng để thanh toán sao chép khi mảng đầy. Phải đảm bảo số tín dụng tích lũy không âm ở mọi thời điểm hợp lệ.

Phương pháp tài khoản là công cụ toán học để tính chi phí, **không yêu cầu chương trình thực sự lưu biến tín dụng**.

### 6.3. Phương pháp thế năng (*potential method*)

Đặt hàm thế năng không âm `Φ(D)` cho trạng thái `D` của cấu trúc. Định nghĩa chi phí khấu hao của thao tác thứ `i`:

```text
ĉ_i = c_i + Φ(D_i) - Φ(D_(i-1))
```

Ở đây `c_i` là chi phí thực và `D_i` là trạng thái sau thao tác. Cộng các đẳng thức sẽ triệt tiêu phần thế năng trung gian:

```text
Σ ĉ_i = Σ c_i + Φ(D_m) - Φ(D_0)

=> Σ c_i = Σ ĉ_i + Φ(D_0) - Φ(D_m)
```

Nếu `Φ(D_i) ≥ 0` cho mọi trạng thái và `Φ(D_0)=0`, ta có:

```text
Σ c_i ≤ Σ ĉ_i
```

Vì vậy, nếu chứng minh được mỗi `ĉ_i = O(1)` thì tổng chi phí thực của `m` thao tác là `O(m)`. Với các phép toán có nhiều loại, cần chặn thế năng và chi phí tương ứng cho từng loại.

**Điểm cốt lõi:** chặn khấu hao vẫn đúng cả khi người dùng chọn một chuỗi thao tác bất lợi, miễn chuỗi nằm trong những điều kiện mà chứng minh bao phủ. Điều đó khác với phân tích kỳ vọng dựa vào mô hình ngẫu nhiên.

### 6.4. Khi chứng minh khấu hao không áp dụng

Bảo đảm khấu hao là kết luận của **một chính sách triển khai cụ thể**. Nếu thay quy tắc mở rộng mảng, đổi ngưỡng thu nhỏ, cho phép xóa tùy ý trong dãy, hoặc thêm thao tác làm lại toàn bộ chỉ mục mà không tính phí, cần kiểm chứng lại.

Tương tự, một cấu trúc có `O(1)` khấu hao cho `pushBack` không đồng nghĩa nó có `O(1)` khấu hao cho `insert(0,x)`. Phân tích luôn phải chỉ rõ **tập thao tác được phép**.

## 7. Ba bảo đảm dưới góc nhìn giới hạn độ trễ

Giả sử hệ thống xử lý yêu cầu trên một luồng và mỗi yêu cầu có hạn xử lý tối đa. Một phép toán đôi lúc tốn tuyến tính có thể khiến các yêu cầu phía sau phải chờ, dù chi phí trung bình thấp.

### 7.1. Khi nào kỳ vọng hoặc khấu hao là đủ?

Nếu ứng dụng chủ yếu xử lý hàng loạt, tổng throughput quan trọng hơn thời gian phản hồi của **một** tác vụ, những cấu trúc kỳ vọng/khấu hao thường rất hiệu quả:

- Nạp một triệu phần tử vào mảng động, có thể chịu vài lần mở rộng.
- Xây hash map một lần rồi xử lý nhiều truy vấn chính xác với khóa không mang tính đối kháng.
- Tạo danh sách kết quả theo đợt, nơi một lần tái cấu trúc không làm vi phạm hạn xử lý tương tác.

Bản thân ứng dụng có thể đáp ứng tốt với việc một số thao tác chậm hơn phần lớn còn lại.

### 7.2. Khi nào cần chặn trường hợp xấu rõ ràng?

Chặn trường hợp xấu có giá trị khi:

- Một yêu cầu đơn lẻ có hạn thời gian chặt và vi phạm gây hậu quả nghiệp vụ lớn.
- Dữ liệu đến từ nguồn không tin cậy, người dùng có thể cố tạo tải bất lợi.
- Hệ thống cần hiệu năng dễ dự đoán để phân bổ CPU hoặc bộ nhớ cho nhiều tác vụ.
- Truy vấn bắt buộc được thực hiện đúng trong mọi phân bố khóa hợp lệ.

Có thể cân nhắc cây tự cân bằng thay cho hash map khi cần truy vấn có thứ tự và chặn theo `log n`, hoặc dùng queue dung lượng cố định khi việc cấp phát ở thời điểm xử lý là không mong muốn. Tuy nhiên **chặn thuật toán không tự chứng minh hạn thời gian thực**: còn phải phân tích bộ cấp phát, đồng bộ, cache, hệ điều hành, garbage collector và phần cứng.

### 7.3. Phương án trung gian: chia nhỏ công việc đắt

Một số cấu trúc có thể được thiết kế để **trải dần công việc tái cấu trúc** qua nhiều thao tác (*deamortization*). Ví dụ, thay vì rehash tất cả phần tử ngay khi bảng đầy, thuật toán có thể phân bổ bảng mới rồi chuyển một số lượng bucket/mục được khống chế sau mỗi thao tác.

Nhưng đây không phải mẹo có thể áp dụng tùy ý. Để đáp ứng chặn trường hợp xấu, cần chứng minh:

- Mỗi thao tác thực hiện tối đa bao nhiêu việc di chuyển.
- Tra cứu vẫn tìm đúng phần tử trong **cả bảng cũ và bảng mới** khi đang chuyển.
- Những lần mở rộng mới không vượt khả năng xử lý phần việc đang tồn.
- Chính sách xóa, cập nhật và đồng thời duy trì bất biến.

**Rehash từng bước có thể giảm đỉnh chi phí resize**, nhưng không tự giải quyết các chuỗi va chạm băm bất lợi. Muốn cam kết giới hạn trường hợp xấu cho bảng băm, cần phân tích đầy đủ cả xử lý va chạm, cấp phát, di chuyển và các điều kiện mô hình.

## 8. Kỳ vọng, xác suất cao và phần trăm độ trễ là những thứ khác nhau

Một nhầm lẫn phổ biến là nhìn vào độ phức tạp kỳ vọng và suy ngay rằng “99% thao tác đều nhanh”.

### 8.1. Kỳ vọng không tự nói lên phần đuôi phân bố

Xét một phân bố chi phí giả định, với `n` lớn:

```text
X = 1       với xác suất 1 - 1/n
X = n       với xác suất 1/n
```

Khi đó:

```text
E[X] = (1 - 1/n) × 1 + (1/n) × n
     = 2 - 1/n
     = O(1)
```

Chi phí **kỳ vọng là hằng số**, nhưng vẫn có xác suất `1/n` xảy ra một thao tác tốn `n` bước. Đây là ví dụ toán học, không phải mô tả cụ thể của một thư viện bảng băm.

Để nói “với xác suất ít nhất 99,9%, chi phí không vượt một ngưỡng” cần một **chặn xác suất/phân vị** phù hợp. Để nói “không có trường hợp nào vượt ngưỡng” cần một **bảo đảm trường hợp xấu** với giả định rõ ràng.

### 8.2. p95/p99 đo điều gì?

p99 của độ trễ đo phân vị 99% của các quan sát theo phương pháp đo cụ thể. Nó chịu tác động của phân bố yêu cầu, tốc độ cấp phát, tải hệ thống, thread scheduling, I/O và các yếu tố bên ngoài thuật toán.

Do đó:

- `E[T] = O(1)` theo một mô hình xác suất không đủ để suy ra p99 tính bằng mili giây.
- `O(1)` khấu hao không hứa rằng mọi thao tác sẽ có cùng thời gian đáp ứng.
- `O(log n)` trường hợp xấu của số phép so sánh không bảo đảm p99 thấp nếu có dừng luồng lâu hoặc tranh chấp khóa.

Khi cần giới hạn p99, hãy kết hợp chọn cấu trúc có chặn phù hợp với **benchmark có phân bố dữ liệu, quy mô và mức đồng thời đại diện**, đồng thời theo dõi các đỉnh độ trễ do resize, GC, khởi tạo và I/O.

## 9. Ví dụ thực tế: chọn bộ lưu trữ phiên làm việc

Một máy chủ duy trì tối đa `n = 500.000` phiên người dùng. Nhiệm vụ chính là `find(sessionId)`, `insert(session)` và `delete(sessionId)`. Các khóa được gửi từ máy khách. Ta xét ba phương án:

| Phương án | Tra cứu/chèn/xóa theo khóa | Bộ nhớ và đặc điểm |
| --- | --- | --- |
| Mảng chưa sắp, quét theo `sessionId` | Tìm thường `O(n)`; thêm cuối `O(1)` khấu hao | Đơn giản, duyệt hiệu quả; tìm mã rất tốn khi `n` lớn |
| Hash map theo `sessionId` | Kỳ vọng `O(1)` dưới giả định phù hợp, thêm có thể kỳ vọng khấu hao `O(1)` | Thêm bucket/vùng trống; phải xử lý va chạm, resize |
| Cây tìm kiếm tự cân bằng theo `sessionId` | `O(log n)` trường hợp xấu | Tốn liên kết/metadata, hỗ trợ duyệt mã tăng dần |

### Trường hợp A: ưu tiên thông lượng

Nếu dịch vụ có thể chịu các đỉnh chi phí hiếm, đã có chính sách băm phù hợp, và chỉ cần tìm khóa chính xác, hash map là ứng viên mạnh. Có thể cấp trước dung lượng hợp lý để giảm số lần resize và đo tải thực tế.

Với `n = 500.000`, không thể kết luận “bảng băm chắc chắn mất 1 bước”: còn phải xử lý hàm băm, so sánh khóa, va chạm, vùng nhớ và cache.

### Trường hợp B: ưu tiên tính dự đoán và thứ tự

Nếu API còn yêu cầu liệt kê phiên theo `sessionId` hoặc phải có chặn rõ ràng về số phép so sánh cho từng lần tra cứu, cây tự cân bằng là ứng viên đáng chọn. Đánh đổi là khoảng `O(log n)` thao tác so sánh/đi theo liên kết, cùng overhead bộ nhớ và điều chỉnh cây.

Nếu chỉ yêu cầu kiểm tra `sessionId` có tồn tại và miền khóa nhỏ/dày đặc, một mảng đánh địa chỉ trực tiếp cũng có thể cho chặn `O(1)` trường hợp xấu, nhưng phải trả bộ nhớ `O(U)` cho toàn miền khóa `U` và chấp nhận cách ánh xạ khóa phù hợp.

### Trường hợp C: nhận dữ liệu đối kháng

Nếu một khách hàng có thể cố tạo nhiều khóa va chạm, phát biểu “hash map trung bình `O(1)`” không đủ làm cơ sở chống lạm dụng. Cần xem giới hạn khóa, cách thư viện xử lý va chạm, độ phức tạp trong trường hợp xấu của triển khai và các cơ chế giới hạn tài nguyên.

Cây cân bằng có chặn thuật toán rõ ràng hơn cho thao tác theo khóa, nhưng nếu mỗi khóa là chuỗi dài, chi phí **so sánh** chuỗi phải được tính thêm. Nếu mỗi lần so sánh có thể mất `O(L)` ký tự thì chi phí tìm có thể là `O(L log n)` trong trường hợp xấu theo mô hình đó, thay vì tự coi là `O(log n)` thời gian CPU tuyệt đối.

## 10. Những ngộ nhận dễ dẫn đến lựa chọn sai

**“Khấu hao `O(1)` nghĩa là từng lần đều `O(1)`.”** Sai. Một lần tăng dung lượng mảng có thể sao chép `n` phần tử.

**“Kỳ vọng `O(1)` là bảo đảm cho dữ liệu ngoài đời.”** Chưa đủ. Kỳ vọng phụ thuộc mô hình xác suất và các giả định về hàm băm, khóa, tải hoặc ưu tiên ngẫu nhiên.

**“Khấu hao là trung bình của các đầu vào ngẫu nhiên.”** Sai. Khấu hao chặn **tổng chi phí của chuỗi thao tác**; thường không cần ngẫu nhiên.

**“Đã có `O(1)` kỳ vọng thì không cần quan tâm worst case.”** Còn tùy yêu cầu. Với các API có độ trễ cứng hoặc đầu vào đối kháng, phần đuôi thời gian có thể quyết định phương án.

**“Cây luôn `O(log n)`.”** Chỉ những cây có bất biến cân bằng hoặc giả định kỳ vọng tương ứng mới cho kết luận đó. BST không cân bằng có thể cao `n`.

**“Heap `push` luôn có worst case `O(log n)` trong mọi chương trình.”** Chi phí sửa heap có chặn `O(log n)`, nhưng nếu heap nằm trên mảng động phải mở rộng, một lần `push` còn có thể trả chi phí sao chép tuyến tính.

**“Giảm độ phức tạp là đủ để đáp ứng thời gian thực.”** Phải xét cả phần cứng, cấp phát, đồng bộ, chi phí so sánh khóa và độ trễ phần đuôi.

**“Chỉ cần dùng một kiểu bảo đảm cho cả cấu trúc.”** Một cấu trúc có thể có nhiều bảo đảm cho **các phép toán khác nhau**. Ví dụ mảng động đọc theo chỉ số `O(1)` trường hợp xấu, thêm cuối `O(1)` khấu hao, chèn đầu `O(n)` trường hợp xấu.

**“Tái băm là nguyên nhân duy nhất của trường hợp xấu ở hash map.”** Không. Va chạm còn là nguồn chi phí riêng; việc loại bỏ hoặc trải đều resize không tự xử lý va chạm.

## 11. Quy trình chọn bảo đảm phù hợp

Trước khi chốt cấu trúc, hãy dùng phiếu quyết định ngắn:

```text
1. Phép toán nào là chủ đạo?
   get(key), pushBack, range(a,b), popMin, update(i), ...?

2. Mức bảo đảm bắt buộc?
   - Chặn từng thao tác?
   - Chấp nhận thời gian trung bình/kỳ vọng?
   - Chỉ cần thông lượng tốt trên cả chuỗi?

3. Giả định nào được phép?
   - Khóa có thể do tác nhân đối kháng tạo không?
   - Có thể dùng ngẫu nhiên không?
   - Có biết trước số phần tử tối đa không?

4. Tính đủ chi phí.
   - Xây dựng, truy vấn, cập nhật, duyệt và xuất kết quả
   - Resize, rehash, metadata, cấp phát, bộ nhớ
   - Bộ nhớ đỉnh khi thay đổi kích thước

5. Tìm phương án thỏa ngữ nghĩa và bảo đảm.
   - Loại phương án có trường hợp xấu không chấp nhận được
   - So thời gian/bộ nhớ trên tải thực tế

6. Kiểm tra bằng dữ liệu đại diện và dữ liệu bất lợi.
   - Kiểm tra đúng bất biến sau cập nhật
   - Đo độ trễ thường gặp và đỉnh độ trễ
```

Bảng sau là gợi ý để bắt đầu, không thay thế việc kiểm chứng triển khai:

| Yêu cầu nổi bật | Hướng lựa chọn | Đánh đổi |
| --- | --- | --- |
| Thêm cuối cực nhiều, ưu tiên tổng thông lượng | Mảng động tăng dung lượng theo cấp số nhân | `O(1)` khấu hao, vẫn có lần chèn `Θ(n)` |
| Tra cứu khóa chính xác, chấp nhận giả định băm | Hash map | Kỳ vọng tốt, cần quản lý va chạm và resize |
| Tra cứu có thứ tự, cần chặn trường hợp xấu | AVL/red-black tree | `O(log n)`, thêm metadata và chi phí cân bằng |
| Luôn lấy cực trị theo ưu tiên | Binary heap | `O(1)` xem đỉnh; `O(log n)` điều chỉnh heap, xét cả bộ nhớ nền |
| Tổng đoạn có cập nhật điểm | Fenwick tree/segment tree | `O(log n)` trường hợp xấu trong mô hình chuẩn |
| Hàng đợi với dung lượng biết trước và hạn xử lý chặt | Bộ đệm vòng cố định | Thao tác đầu/cuối có thể `O(1)` trường hợp xấu; cần chính sách khi đầy |
| Đồ thị thưa, chủ yếu duyệt | Danh sách kề/CSR | Duyệt `O(V+E)`, kiểm tra cạnh riêng lẻ tùy biểu diễn |
| Miền khóa nhỏ, dày đặc, cần chặn truy cập | Mảng đánh địa chỉ trực tiếp | `O(1)` theo chỉ số, trả giá bộ nhớ `O(U)` |

### Tự kiểm tra

**Bài 1.** Mảng động đang có `size = capacity = 1.024` và áp dụng nhân đôi khi đầy. Chi phí trường hợp xấu của lần `pushBack` tiếp theo là gì? Có mâu thuẫn với `O(1)` khấu hao không?

*Đáp án:* phải sao chép 1.024 phần tử, nên lần này `Θ(n)` theo số phần tử hiện có. Không mâu thuẫn vì tổng chi phí của một chuỗi thêm cuối vẫn `O(m)`.

**Bài 2.** Hash map có tra cứu kỳ vọng `O(1)` và `n = 100.000`. Có thể kết luận mọi lần `get` đều tối đa một số phép so sánh cố định không?

*Đáp án:* không. Cần biết mô hình băm, cách xử lý va chạm và trường hợp xấu cụ thể của thư viện; kỳ vọng không chặn riêng từng lần gọi.

**Bài 3.** Cần duy trì các khóa để `lowerBound` và xóa bất kỳ theo khóa, đầu vào có thể tăng dần. Chọn BST không cân bằng hay AVL nếu yêu cầu mỗi thao tác tìm/xóa có chặn `O(log n)`?

*Đáp án:* AVL (hoặc cây tự cân bằng tương đương). BST thường có thể suy biến thành đường dài `n`.

**Bài 4.** Một cấu trúc đạt `O(1)` khấu hao cho 1.000.000 lần thêm, nhưng yêu cầu sản phẩm là “không lần thêm nào được gây gián đoạn phục vụ”. Kết quả khấu hao có đủ để chấp nhận không?

*Đáp án:* chưa đủ. Phải xem chi phí tệ nhất từng lần, thiết kế bộ nhớ/cấp phát hoặc cơ chế trải công việc và đo độ trễ trong môi trường triển khai.

**Bài 5.** Một thuật toán có `E[T] = O(1)`. Có thể suy rằng “p99 luôn nhỏ hơn 2 ms” không?

*Đáp án:* không. Kỳ vọng không cho phân vị bằng mili giây; phải phân tích phân bố xác suất cụ thể và đo hệ thống thực tế.

## Kết luận

**Trường hợp xấu nhất** trả lời câu hỏi một thao tác có thể tốn tối đa bao nhiêu trong mô hình đã nêu. **Kỳ vọng** trả lời câu hỏi chi phí trung bình theo một nguồn ngẫu nhiên và giả định xác suất xác định. **Khấu hao** trả lời câu hỏi tổng chi phí của cả chuỗi có được kiểm soát dù đôi lúc xuất hiện thao tác đắt.

Không loại bảo đảm nào luôn tốt hơn trong mọi bài toán. Mảng động, bảng băm và cấu trúc ngẫu nhiên có thể tối ưu thông lượng với chi phí kỳ vọng/khấu hao; cây tìm kiếm tự cân bằng và các cấu trúc có chặn tệ nhất thường phù hợp khi cần hành vi dễ dự đoán. Khi thiết kế, hãy **ghi rõ phép toán, loại bảo đảm, giả định, bất biến, bộ nhớ và yêu cầu độ trễ thực tế**. Đây là cơ sở để chọn cấu trúc dữ liệu theo yêu cầu hệ thống thay vì chỉ dựa vào ký hiệu `O(1)` hay `O(log n)`.
