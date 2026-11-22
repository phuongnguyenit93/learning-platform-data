# So sánh nhu cầu chọn một phần với sắp xếp toàn bộ

## 1. Mục tiêu và câu hỏi trung tâm

Trong nhiều bài toán thuật toán, câu hỏi không phải “sắp xếp nhanh nhất bằng cách nào?” mà là **“đề bài thực sự yêu cầu bao nhiêu thông tin về thứ tự?”**. Nếu chỉ cần một phần tử hạng k, k phần tử đứng đầu bảng xếp hạng hoặc một ngưỡng, sắp xếp toàn bộ dãy có thể làm thừa công việc. Ngược lại, nếu cần xuất cả dãy đã sắp, truy vấn rất nhiều thứ hạng hoặc tái sử dụng thứ tự nhiều lần, sắp toàn bộ có thể hợp lý hơn.

Sau bài này, bạn sẽ:

- Phân biệt **selection** (chọn phần tử theo hạng), **top-k**, **partial sorting** và **full sorting**.
- Biết đặc tả hạng k theo chỉ số từ 0 hoặc 1, cách đếm phần tử trùng và cách xử lý đồng hạng.
- So sánh các chiến lược quét một lần, **Quickselect**, heap kích thước k, Quickselect rồi sắp k phần tử, và sắp xếp toàn bộ.
- Hiểu sự khác nhau giữa **kỳ vọng O(n)** của Quickselect ngẫu nhiên và **worst-case O(n²)**; biết khi nào có thể dùng selection worst-case O(n).
- Chọn thuật toán theo n, k, số lượng truy vấn, dữ liệu tĩnh hay luồng, bộ nhớ và yêu cầu ổn định.
- Cài đặt, chạy và kiểm thử các cách tiếp cận bằng **Java 17+**.

Xét dãy:

```text
Dữ liệu gốc:      [7, 2, 9, 2, 5, 9, 1]
Đã sắp tăng:      [1, 2, 2, 5, 7, 9, 9]
Đã sắp giảm:      [9, 9, 7, 5, 2, 2, 1]
```

Nếu chỉ hỏi “số lớn nhất là gì?”, câu trả lời `9` không yêu cầu biết 6 phần tử còn lại nằm theo thứ tự nào. Nếu hỏi “3 phần tử lớn nhất là gì?”, đa tập đáp án `{9,9,7}` vẫn không đòi sắp tất cả 7 phần tử. Nếu đề bài yêu cầu “in toàn bộ dãy theo thứ tự tăng”, khi đó việc tạo toàn bộ thứ tự là phần không thể thiếu của hợp đồng đầu ra.

## 2. Đặc tả chính xác trước khi chọn thuật toán

Có những câu hỏi rất giống nhau về ngôn từ nhưng không giống nhau về đầu ra:

| Yêu cầu | Ví dụ đầu ra | Thực sự cần |
| --- | --- | --- |
| Giá trị nhỏ nhất | `1` | Một cực trị |
| Giá trị lớn nhất | `9` | Một cực trị |
| Phần tử nhỏ thứ ba, đếm cả trùng | `2` | Một thống kê thứ tự |
| Phần tử lớn thứ ba, đếm cả trùng | `7` | Một thống kê thứ tự |
| Top-3 lớn nhất, không yêu cầu thứ tự | Đa tập `{7,9,9}` | Chọn 3 lần xuất hiện |
| Top-3 lớn nhất, giảm dần | `[9,9,7]` | Chọn 3 rồi sắp riêng 3 phần tử |
| Toàn bộ dãy tăng | `[1,2,2,5,7,9,9]` | Sắp tất cả |
| Nhiều truy vấn “phần tử thứ k” trên một dãy cố định | `b[k-1]` trên mảng đã sắp `b` | Có thể chuẩn bị toàn bộ thứ tự một lần |

Những thông tin bắt buộc phải có trong hợp đồng API:

1. **k đánh số từ đâu?** Với phần tử hạng k, nhiều đặc tả dùng k **1-based** (`1≤k≤n`); nhiều thư viện dùng chỉ số **0-based** (`0≤index<n`).
2. **Có tính giá trị trùng như những lần xuất hiện riêng biệt không?** Ví dụ hai số `2` chiếm hai vị trí thứ hạng trong dãy đã sắp.
3. **Có cần trả đúng k phần tử không?** Nếu có đồng hạng ở ngưỡng, “trả mọi người đồng điểm” có thể tạo **nhiều hơn k** kết quả.
4. **Có cần thứ tự của các phần tử được chọn không?** “Top-k” có thể chỉ là tập ứng viên, còn “top-k theo điểm giảm dần” yêu cầu thêm thứ tự.
5. **Dữ liệu có mang danh tính không?** Hai bản ghi khác nhau cùng điểm có thể cần giữ thứ tự xuất hiện trước–sau.
6. **Được sửa dữ liệu nguồn không?** Quickselect có thể hoán đổi phần tử; nếu đầu vào phải giữ nguyên, cần sao chép hoặc một phương pháp không sửa.
7. **Dữ liệu có được đọc lại không?** Dữ liệu đến một lượt qua luồng khác với mảng lưu sẵn trong RAM.

**Số phần tử phân biệt** cũng là một hợp đồng khác. Với `[1,2,2,5,7,9,9]`, phần tử nhỏ thứ ba **đếm trùng** là `2`, còn giá trị phân biệt nhỏ thứ ba là `5`. Không được đổi hai định nghĩa cho nhau.

## 3. Selection và thống kê thứ tự (order statistics)

Gọi `b` là bản sao của mảng `a` được sắp xếp tăng dần, có độ dài `n`. Với `1≤k≤n`:

\[
\operatorname{kthSmallest}(a,k)=b[k-1].
\]

Để lấy phần tử **lớn thứ k**, tính:

\[
\operatorname{kthLargest}(a,k)=b[n-k].
\]

Ví dụ `n=7`:

- `kthSmallest(a,3)=b[2]=2`.
- `kthLargest(a,3)=b[4]=7`.
- `kthLargest(a,2)=b[5]=9`, vì hai lần xuất hiện của 9 đều được tính.

Điều quan trọng là **chỉ cần biết giá trị của một hạng**, không cần biết thứ tự đầy đủ của các phần tử. Đây là lý do selection có thể có thuật toán nhanh hơn full sort trên đầu vào tổng quát.

Trung vị cũng là một bài toán chọn thứ hạng:

- Với `n` lẻ, trung vị là `b[n/2]` (nếu chỉ số từ 0).
- Với `n` chẵn, nhiều quy ước lấy trung bình `(b[n/2-1]+b[n/2])/2`; cần tìm **hai hạng**, và nếu dùng Java nên nâng sang kiểu rộng trước khi cộng để tránh tràn số nguyên.
- Một số ứng dụng chọn trung vị thấp hoặc trung vị cao thay vì trung bình. Phải nêu rõ định nghĩa.

Cũng vậy, phân vị 90% phụ thuộc quy tắc nội suy và làm tròn hạng. Thuật toán chọn không quyết định thay quy tắc thống kê.

## 4. Cực trị: chỉ cần một lượt quét

Nếu chỉ cần phần tử lớn nhất hoặc nhỏ nhất, giải pháp đơn giản nhất là duyệt n phần tử một lần:

```text
MAXIMUM(a):
    yêu cầu: n >= 1
    best = a[0]
    for i = 1..n-1:
        if a[i] > best:
            best = a[i]
    return best
```

- Thời gian `Θ(n)`; trong mô hình so sánh, xác định max của n phần tử phân biệt cần ít nhất `n-1` phép so sánh.
- Bộ nhớ phụ `O(1)`.
- Không cấp phát mảng kết quả kích thước n.
- Với mảng rỗng, phải trả lỗi hoặc định nghĩa kiểu kết quả tùy chọn; không thể đọc `a[0]`.

Nếu chỉ cần min **và** max, vẫn có thể quét tuyến tính, không cần sắp xếp. Một số biến thể so sánh theo cặp còn giảm số lần so sánh; điểm cốt lõi là **sắp toàn bộ thường tạo thừa thông tin** cho một hoặc hai cực trị.

## 5. Quickselect: tìm hạng k mà không sắp cả dãy

**Quickselect** kế thừa thao tác **phân hoạch (partition)** từ họ quicksort, nhưng chỉ tiếp tục xử lý miền còn chứa thứ hạng cần tìm. Với `target=k-1` (k 1-based), thuật toán:

1. Chọn một `pivot` trong đoạn đang xét.
2. Phân hoạch thành các phần tử **nhỏ hơn**, **bằng**, và **lớn hơn** pivot.
3. Nếu chỉ số `target` ở miền nhỏ hơn, chỉ tìm trong miền đó.
4. Nếu `target` ở miền lớn hơn, chỉ tìm trong miền đó.
5. Nếu `target` nằm trong miền bằng pivot, trả `pivot` ngay.

```text
Trước phân hoạch: [các khóa chưa biết thứ tự]
Sau phân hoạch:  [ < pivot ][ == pivot ][ > pivot ]
                    left       giữa        right
```

Đây là **phân hoạch ba miền (Dutch national flag partition)**. Nó đặc biệt hữu ích khi dữ liệu có nhiều phần tử trùng: một lần phân hoạch có thể giải quyết tất cả thứ hạng nằm trong dải bằng pivot.

### Giả mã

```text
QUICKSELECT(a, target):
    yêu cầu: 0 <= target < n
    left = 0
    right = n-1

    while true:
        pivot = chọn ngẫu nhiên một phần tử trong a[left..right]
        phân hoạch đoạn theo pivot thành:
            [left, less)      : giá trị < pivot
            [less, greater]   : giá trị = pivot
            (greater, right]  : giá trị > pivot

        if target < less:
            right = less - 1
        else if target > greater:
            left = greater + 1
        else:
            return pivot
```

**Bất biến tính đúng:** `target` luôn nằm trong miền mà thuật toán đang xử lý, trừ khi nó đã thuộc dải đúng hạng có giá trị pivot. Các phần tử bị loại nằm hoàn toàn về phía không thể chứa hạng đích, nên không ảnh hưởng đến giá trị hạng k. Mỗi lần chưa trả kết quả, miền đang xét ngắn lại.

### Thời gian kỳ vọng và trường hợp xấu

Một lần phân hoạch m phần tử tốn `O(m)`. Nếu pivot thường chia miền còn lại thành những phần nhỏ đáng kể, tổng công việc kiểu:

\[
n+n/2+n/4+\ldots=O(n).
\]

Với **pivot được lấy ngẫu nhiên đều từ miền đang xét**, Quickselect có **thời gian kỳ vọng `O(n)`** theo lựa chọn pivot ngẫu nhiên, ngay cả khi đầu vào không được giả sử phân bố đều.

Tuy nhiên, nếu các pivot liên tục rất xấu, có thể phát sinh:

\[
n+(n-1)+(n-2)+\cdots=\Theta(n^2).
\]

Vậy **worst-case của Quickselect thông thường có thể là `O(n²)`**. “Kỳ vọng `O(n)`” không phải “mọi lần chạy đều `O(n)`”, và cũng không phải “mảng ngẫu nhiên thì chắc chắn `O(n)`”.

**Bộ nhớ:** phân hoạch dùng vòng lặp có thể triển khai tại chỗ với `O(1)` biến phụ, nhưng **làm xáo trộn mảng đầu vào**. Nếu phải giữ nguyên input, có thể `clone()` mảng, dùng thêm `O(n)` bộ nhớ và `O(n)` thời gian sao chép.

### Khi cần bảo đảm worst-case tuyến tính

Thuật toán **median of medians** chọn pivot có bảo đảm để giải selection trong `O(n)` **trường hợp xấu** theo mô hình so sánh. Cách cài đặt phức tạp hơn và hằng số có thể lớn; đây là lựa chọn cho yêu cầu nghiêm ngặt về worst-case, không phải cách thay thế bắt buộc cho mọi chương trình.

**Lưu ý:** chọn pivot cố định là “phần tử giữa” hoặc “phần tử đầu” không đồng nghĩa với chọn pivot **ngẫu nhiên**, nên không thể tự nhận cùng bảo đảm kỳ vọng nếu chưa có giả thiết.

## 6. Top-k bằng min-heap kích thước k

Nếu cần **k phần tử lớn nhất**, có thể giữ một **min-heap** chứa tối đa k ứng viên. Đỉnh heap là **phần tử nhỏ nhất trong số k phần tử đang được chọn**.

Khi đọc thêm một phần tử:

- Nếu heap chưa đủ k phần tử, thêm vào.
- Nếu đã đủ k và phần tử mới **lớn hơn** đỉnh, bỏ đỉnh rồi thêm phần tử mới.
- Nếu phần tử mới nhỏ hơn hoặc bằng đỉnh, giữ nguyên heap đối với hợp đồng so sánh **giá trị**.

```text
TOP_K_LARGEST(a, k):
    yêu cầu: 0 <= k <= n
    if k == 0: return []
    heap = min-heap rỗng

    for value trong a:
        if size(heap) < k:
            add(heap, value)
        else if value > min(heap):
            removeMin(heap)
            add(heap, value)

    return các giá trị trong heap
```

**Bất biến:** sau khi đã đọc i phần tử, heap chứa `min(i,k)` lần xuất hiện có giá trị lớn nhất của tiền tố đã đọc. Khi gặp ứng viên mới tốt hơn phần tử yếu nhất của nhóm top-k, việc thay thế bảo toàn bất biến.

Với `a=[7,2,9,2,5,9,1]` và `k=3`:

| Dữ liệu vừa xét | Top-3 đang giữ (viết tăng để minh họa, không phải cấu trúc heap thực) |
| --- | --- |
| `7` | `{7}` |
| `2` | `{2,7}` |
| `9` | `{2,7,9}` |
| `2` | `{2,7,9}` |
| `5` | `{5,7,9}` |
| `9` | `{7,9,9}` |
| `1` | `{7,9,9}` |

Kết quả là đa tập `{7,9,9}`. Muốn đầu ra giảm dần `[9,9,7]` phải xử lý thêm việc **xuất/sắp theo thứ tự**. Heap tự thân **không** duy trì thứ tự đầy đủ của tất cả phần tử bên trong.

### Chi phí và ứng dụng luồng

Với `1≤k≤n`:

- Xử lý n phần tử: `O(n log(k+1))`.
- Nếu lấy k giá trị theo thứ tự bằng cách `poll` liên tục: cộng thêm `O(k log(k+1))`.
- Bộ nhớ phụ: `O(k)`.

Khi `k=1`, nên cân nhắc quét max trực tiếp, `O(n)` thời gian và `O(1)` bộ nhớ. Khi `k≈n`, heap không còn lợi thế rõ so với sắp toàn bộ.

Heap đặc biệt hữu ích khi dữ liệu **đến theo luồng** và không thể hoặc không muốn giữ n phần tử: bộ nhớ chỉ tăng theo k. Nhưng nếu sau đó người dùng tăng k từ 10 lên 100 mà các phần tử ngoài top-10 đã bị bỏ, không thể khôi phục top-100 nếu không có nguồn phát lại hay dữ liệu lưu trữ.

**Top-k nhỏ nhất:** dùng **max-heap kích thước k** và bỏ phần tử **lớn nhất** trong heap khi gặp ứng viên nhỏ hơn. Không đổi thuật toán chỉ bằng cách đổi tên “lớn” thành “nhỏ”.

## 7. Chỉ sắp k phần tử được chọn

Khi đề yêu cầu **top-k có thứ tự**, có ba hướng:

1. **Heap kích thước k:** duyệt đầu vào, giữ top-k, sau đó lấy ra/sắp riêng các phần tử trong heap.
2. **Quickselect + sort k:** phân hoạch để tách k phần tử lớn nhất, rồi chỉ sắp **k phần tử đó**.
3. **Full sort + lấy đuôi:** sắp toàn mảng, sau đó lấy k phần tử cuối khi sắp tăng.

Nếu dùng Quickselect ngẫu nhiên và sắp k phần tử bằng thuật toán có chi phí `O(k log(k+1))`, thời gian kỳ vọng:

\[
O(n+k\log(k+1)).
\]

Nếu không cần thứ tự của top-k, có thể bỏ bước sắp k phần tử, đạt kỳ vọng `O(n)` cho phần chọn (cộng chi phí xuất k phần tử). Nếu input phải giữ nguyên, bản sao chiếm thêm `O(n)` bộ nhớ.

### Ranh giới đồng hạng

Ví dụ `[10,9,9,9,4]`, `k=2`, ngưỡng top-2 là 9. Nếu lọc **mọi** phần tử `>=9`, ta nhận `[10,9,9,9]`, tức **4 phần tử**, không phải đúng 2.

Vì vậy:

- Nếu hợp đồng yêu cầu **đúng k lần xuất hiện**, phải lấy đủ các phần tử **lớn hơn ngưỡng** và **đúng số cần thiết** trong nhóm bằng ngưỡng.
- Nếu hợp đồng yêu cầu **tất cả phần tử đồng hạng tại ngưỡng**, kết quả có thể có hơn k phần tử.
- Nếu là các bản ghi có `id`, phải quy định chọn ai trước khi nhiều người cùng khóa.

Không được coi việc chọn theo điểm tương đương việc chọn một tập bản ghi ổn định khi ngưỡng có nhiều phần tử trùng.

## 8. Sắp xếp toàn bộ: khi nào đáng làm?

**Sắp xếp toàn bộ** tạo quan hệ thứ tự của tất cả n phần tử. Trong mô hình **chỉ dựa trên so sánh khóa phân biệt**, có giới hạn dưới `\Omega(n log n)` cho sorting nói chung, và có các thuật toán như mergesort/heapsort đạt `O(n log n)` worst-case.

Việc sắp xếp toàn bộ hợp lý khi:

- Phải xuất cả danh sách theo thứ tự.
- Cần xử lý rất nhiều truy vấn phần tử hạng k trên **cùng dữ liệu tĩnh**.
- K gần n nên việc “chỉ sắp k phần tử” cũng phải xử lý gần như toàn bộ đầu ra.
- Kết quả đã sắp phục vụ bước tiếp theo như tìm kiếm nhị phân, tìm các giá trị trùng liền nhau, truy vấn theo khoảng hoặc duyệt thứ tự.
- Thuật toán full sort đơn giản, dễ kiểm thử và đáp ứng yêu cầu worst-case/độ ổn định hơn lựa chọn selection cụ thể.

Nếu chỉ có **một** truy vấn hạng k, sắp toàn mảng thường làm thừa. Nếu cần **hàng trăm nghìn** truy vấn hạng k mà mảng không đổi, chi phí sắp một lần có thể được bù qua nhiều lần truy cập `O(1)`.

**Một lưu ý về thư viện Java:** `Arrays.sort(int[])` là API sắp mảng nguyên. Không nên suy ra mọi overload `Arrays.sort` hoặc mọi cách cài đặt có cùng bảo đảm worst-case và bộ nhớ. Khi phát biểu một giới hạn lý thuyết cứng, hãy nêu thuật toán cụ thể có bảo đảm đó, không gán một đặc tính nội bộ không được công bố cho mọi API.

## 9. Bảng so sánh các lựa chọn

Bảng sau dùng n là số phần tử, k trong khoảng `1..n` (trừ top-0), và mô hình so sánh khóa cơ bản:

| Nhu cầu | Phương án | Thời gian | Bộ nhớ phụ / lưu ý |
| --- | --- | --- | --- |
| Chỉ min/max | Quét một lần | `Θ(n)` | `O(1)` |
| Một giá trị hạng k | Quickselect ngẫu nhiên | Kỳ vọng `O(n)`, worst-case có thể `O(n²)` | Có thể in-place; bản sao `O(n)` nếu giữ nguyên input |
| Một giá trị hạng k, cần worst-case | Median of medians | `O(n)` worst-case | Cài đặt khó hơn |
| Top-k không cần thứ tự | Quickselect rồi lấy đúng k | Kỳ vọng `O(n)` | Xử lý đồng hạng đúng hợp đồng |
| Top-k trên luồng | Min-heap kích thước k | `O(n log(k+1))` | `O(k)` |
| Top-k có thứ tự | Heap + xuất k | `O(n log(k+1)+k log(k+1))` | `O(k)` |
| Top-k có thứ tự trên mảng | Quickselect + sắp k | Kỳ vọng `O(n+k log(k+1))` | Có thể sửa input hoặc cần sao chép |
| Toàn bộ thứ tự | Một sort so sánh có cận tốt | `O(n log n)` worst-case với mergesort/heapsort chuẩn | Bộ nhớ/ổn định tùy thuật toán |
| Nhiều truy vấn hạng trên mảng tĩnh | Sắp một lần, sau đó tra chỉ số | `O(n log n+q)` cho q truy vấn | Sắp và lưu một lần |

Lưu ý các chặn trong bảng nói về **thuật toán đã mô tả**, không bảo đảm công cụ thực tế luôn có cùng tốc độ. Ví dụ, heap chứa `Integer` trong Java có overhead đối tượng/boxing so với `int[]`.

### K nhỏ, K lớn và số truy vấn

- **k rất nhỏ:** heap top-k có lợi nếu không thể giữ n phần tử; với k=1, quét min/max trực tiếp còn đơn giản hơn.
- **k gần n:** trả gần toàn bộ dãy đã có thứ tự có thể khiến full sort hợp lý hơn.
- **Một truy vấn hạng k:** Quickselect ngẫu nhiên thường đáng cân nhắc nếu không cần worst-case cứng.
- **Nhiều truy vấn hạng:** sắp một lần có thể tốt hơn chạy selection nhiều lần.
- **Dữ liệu đổi liên tục:** một bản sao đã sắp nhanh chóng trở nên cũ; có thể cần cấu trúc thứ tự động và phân tích chi phí cập nhật.
- **Luồng không thể đọc lại:** heap top-k giữ ít dữ liệu, nhưng không tự trả lời được truy vấn yêu cầu k lớn hơn kích thước đã lưu.

## 10. Nhiều truy vấn và chi phí chuẩn bị

Giả sử có q câu hỏi “phần tử nhỏ thứ k là gì?” trên cùng một mảng **không đổi**.

**Cách 1:** chạy Quickselect ngẫu nhiên độc lập q lần, mỗi lần kỳ vọng `O(n)`. Tổng kỳ vọng `O(qn)`; có thể còn thêm chi phí sao chép nếu giữ nguyên input.

**Cách 2:** sắp mảng một lần bằng thuật toán `O(n log n)`, rồi mỗi truy vấn truy cập một vị trí trong `O(1)`. Tổng `O(n log n+q)`.

Khi q lớn, cách 2 có thể có lợi. Khi q rất nhỏ, cách 1 không nhất thiết cần chuẩn bị toàn bộ thứ tự.

Nếu biết **một tập nhỏ các thứ hạng cần chọn cùng lúc**, có thể xét thuật toán multiselection hoặc tái sử dụng phân hoạch, nhưng cần chứng minh riêng; không tự coi mọi q truy vấn được giải bằng đúng một lần Quickselect.

Nếu yêu cầu trả chính các **bản ghi** theo thứ hạng mà bản ghi đồng khóa có chính sách ưu tiên riêng, việc truy cập từ bản sao đã sắp cũng phải dựa trên comparator đúng với hợp đồng.

## 11. Trùng giá trị, hòa điểm và ổn định

Xét các bản ghi:

```text
A: 95 điểm
B: 90 điểm
C: 90 điểm
D: 85 điểm
```

Với k=2, có ít nhất ba hợp đồng:

- **Đúng 2 bản ghi, ưu tiên ai đến trước khi bằng điểm:** trả `[A,B]`.
- **Lấy tất cả bản ghi cùng điểm với vị trí k:** trả `[A,B,C]`, vì ngưỡng top-2 là 90.
- **Đúng 2 bản ghi, không quy tắc hòa:** cả `[A,B]` và `[A,C]` đều có thể hợp lệ.

Nếu muốn kết quả xác định và lặp lại được, dùng thứ tự so sánh rõ ràng, ví dụ:

1. Điểm giảm dần.
2. Cùng điểm thì chỉ số đầu vào tăng dần.
3. Nếu cần, dùng khóa `id` duy nhất làm tie-breaker cuối.

**Quickselect không tự ổn định:** việc hoán đổi phần tử có thể đảo thứ tự các bản ghi có khóa bằng nhau. **Heap top-k với comparator chỉ nhìn điểm** cũng không tự bảo đảm ưu tiên theo thời điểm đến khi xảy ra đồng hạng ở ranh giới.

Với mảng số nguyên, các lần xuất hiện bằng nhau không mang danh tính quan sát được. Muốn kiểm thử tính ổn định, phải dùng bản ghi chứa `id` cùng khóa so sánh.

### Hạng k “theo giá trị phân biệt” là bài khác

`a=[7,2,9,2,5,9,1]` có:

- Hạng nhỏ thứ 3 đếm trùng: `2`.
- Hạng nhỏ thứ 3 theo giá trị phân biệt: `5`.
- Hạng lớn thứ 2 đếm trùng: `9`.
- Hạng lớn thứ 2 phân biệt: `7`.

Nếu yêu cầu **top-k giá trị phân biệt**, không đủ để chọn k lần xuất hiện rồi loại trùng, vì có thể nhận ít hơn k giá trị. Phải duy trì tập phân biệt hoặc dùng thuật toán phù hợp định nghĩa mới; đồng thời xử lý trường hợp tổng số giá trị phân biệt nhỏ hơn k.

## 12. Java 17+: so sánh các cách giải trên cùng dữ liệu

Chương trình độc lập dưới đây có tên tệp **`SelectionVsSortDemo.java`**. Nó minh họa quét max, Quickselect ngẫu nhiên ba miền, min-heap top-k và full sort, đồng thời **không sửa mảng input**.

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.concurrent.ThreadLocalRandom;

public class SelectionVsSortDemo {

    static int maximum(int[] input) {
        Objects.requireNonNull(input, "input");
        if (input.length == 0) {
            throw new IllegalArgumentException("empty array");
        }
        int best = input[0];
        for (int i = 1; i < input.length; i++) {
            if (input[i] > best) {
                best = input[i];
            }
        }
        return best;
    }

    private static void swap(int[] a, int i, int j) {
        int temporary = a[i];
        a[i] = a[j];
        a[j] = temporary;
    }

    // Rank is 1-based; equal values count as separate occurrences.
    static int kthSmallest(int[] input, int rank) {
        Objects.requireNonNull(input, "input");
        if (rank < 1 || rank > input.length) {
            throw new IllegalArgumentException("rank not in [1, n]");
        }

        int[] a = input.clone();
        int target = rank - 1;
        int left = 0;
        int right = a.length - 1;

        while (left <= right) {
            int pivot = a[
                    ThreadLocalRandom.current().nextInt(left, right + 1)];

            int less = left;
            int scan = left;
            int greater = right;

            while (scan <= greater) {
                if (a[scan] < pivot) {
                    swap(a, less++, scan++);
                } else if (a[scan] > pivot) {
                    swap(a, scan, greater--);
                } else {
                    scan++;
                }
            }

            if (target < less) {
                right = less - 1;
            } else if (target > greater) {
                left = greater + 1;
            } else {
                return a[target];
            }
        }

        throw new AssertionError("valid rank must be found");
    }

    // Output is the top-k multiset in ASCENDING order.
    static int[] topKLargestHeap(int[] input, int k) {
        Objects.requireNonNull(input, "input");
        if (k < 0 || k > input.length) {
            throw new IllegalArgumentException("k not in [0, n]");
        }
        if (k == 0) {
            return new int[0];
        }

        PriorityQueue<Integer> heap = new PriorityQueue<>();
        for (int value : input) {
            if (heap.size() < k) {
                heap.offer(value);
            } else if (value > heap.peek()) {
                heap.poll();
                heap.offer(value);
            }
        }

        int[] result = new int[k];
        for (int i = 0; i < k; i++) {
            result[i] = heap.poll();
        }
        return result;
    }

    static int[] fullSort(int[] input) {
        Objects.requireNonNull(input, "input");
        int[] result = input.clone();
        Arrays.sort(result);
        return result;
    }

    static int[] topKFromFullSort(int[] input, int k) {
        Objects.requireNonNull(input, "input");
        if (k < 0 || k > input.length) {
            throw new IllegalArgumentException("k not in [0, n]");
        }
        int[] sorted = fullSort(input);
        return Arrays.copyOfRange(
                sorted, sorted.length - k, sorted.length);
    }

    public static void main(String[] args) {
        int[] values = {7, 2, 9, 2, 5, 9, 1};

        System.out.println("Original: " + Arrays.toString(values));
        System.out.println("Maximum: " + maximum(values));
        System.out.println("3rd smallest: " + kthSmallest(values, 3));
        System.out.println("3rd largest: "
                + kthSmallest(values, values.length - 3 + 1));
        System.out.println("Top-3 via heap (asc): "
                + Arrays.toString(topKLargestHeap(values, 3)));
        System.out.println("Full sort (asc): "
                + Arrays.toString(fullSort(values)));
        System.out.println("Top-3 via full sort (asc): "
                + Arrays.toString(topKFromFullSort(values, 3)));
        System.out.println("Top-0: "
                + Arrays.toString(topKLargestHeap(values, 0)));
        System.out.println("Input unchanged: "
                + Arrays.toString(values));
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```bash
javac SelectionVsSortDemo.java
java SelectionVsSortDemo
```

Đầu ra chuẩn chính xác (giá trị Quickselect không đổi theo cách chọn pivot):

```text
Original: [7, 2, 9, 2, 5, 9, 1]
Maximum: 9
3rd smallest: 2
3rd largest: 7
Top-3 via heap (asc): [7, 9, 9]
Full sort (asc): [1, 2, 2, 5, 7, 9, 9]
Top-3 via full sort (asc): [7, 9, 9]
Top-0: []
Input unchanged: [7, 2, 9, 2, 5, 9, 1]
```

### Giải thích code và độ phức tạp

- `maximum` chỉ giữ một biến `best`; đầu vào rỗng bị từ chối.
- `kthSmallest` yêu cầu hạng **1-based**. `rank=3` tương ứng `target=2`; hạng không hợp lệ ném ngoại lệ.
- `input.clone()` bảo toàn mảng nguồn. Quickselect thao tác trên bản sao, tốn thêm `O(n)` bộ nhớ và công sao chép.
- Pivot được chọn trong miền hiện hành bằng `ThreadLocalRandom.current().nextInt(left,right+1)`. Phân hoạch ba miền theo khóa pivot, và trả kết quả chỉ khi hạng đích đã xác định.
- `topKLargestHeap` dùng `PriorityQueue<Integer>` mặc định là min-heap. Khi k>0, `peek` luôn có giá trị ở thời điểm heap đã đủ k; dùng `>` thay vì `>=` vẫn đúng cho đa tập các **giá trị**.
- `poll()` lấy **nhỏ nhất** trong heap, nên hàm trả top-k **tăng dần**; muốn giảm dần thì đảo đầu ra sau khi lấy đủ k.
- `fullSort` sao chép rồi gọi `Arrays.sort`. `topKFromFullSort` lấy đoạn đuôi dài k; nếu `k=0`, đoạn đuôi rỗng.
- Phần tử lớn thứ ba được đổi sang hạng nhỏ thứ `n-3+1`, tức hạng 5 trong ví dụ, trả `7`.
- Cả ba chiến lược đều xử lý được giá trị trùng. Không cần tiền điều kiện mảng nguồn đã sắp.

Phần thời gian thực của `PriorityQueue` trong Java còn có overhead boxing và cấp phát; không lấy một lần chạy nhỏ để khẳng định chênh lệch thời gian. Muốn đánh giá tốc độ, phải đo nhiều kích thước n/k, kiểu dữ liệu và loại tải.

## 13. Chứng minh tính đúng ngắn gọn

**Quét max:** sau mỗi tiền tố đã duyệt, biến `best` là phần tử lớn nhất của tiền tố ấy. Khi nhận giá trị mới, lấy max của nó và `best`. Sau n bước, bất biến cho max toàn mảng.

**Quickselect ba miền:** sau phân hoạch, các giá trị trước `less` nhỏ hơn pivot, trong `[less,greater]` bằng pivot, sau `greater` lớn hơn pivot. Vì các miền được xác định tương đối theo thứ tự toàn dãy, hạng đích ở miền bằng thì giá trị cần trả bằng pivot; nếu không, một phía có thể bỏ an toàn. Miền chưa xử lý ngắn lại nên thuật toán dừng.

**Heap top-k:** sau i phần tử đầu, heap chứa đúng `min(i,k)` lần xuất hiện lớn nhất. Với ứng viên mới không vượt phần tử yếu nhất trong nhóm, bỏ ứng viên không thể làm mất một giá trị cần thiết của top-k. Nếu lớn hơn, thay phần tử yếu nhất giữ bất biến. Sau khi duyệt n phần tử, heap chứa top-k; lấy ra từng min cho dãy tăng dần.

**Full sort rồi cắt:** sau khi mảng được sắp tăng, k phần tử cuối không nhỏ hơn bất kỳ phần tử nào trước chúng. Do đó đoạn đuôi có đúng k lần xuất hiện lớn nhất.

Những chứng minh trên chỉ xét **giá trị**. Để chứng minh tính ổn định trên bản ghi, phải thêm điều kiện về comparator và thứ tự đồng hạng.

## 14. Những lỗi thường gặp

1. **Sắp toàn bộ để lấy max hoặc một hạng k** mà không xét quét/selection.
2. **Nhầm hạng k với chỉ số k**: hạng 1-based k tương ứng `aSorted[k-1]`.
3. **Nhầm top-k với k-th**: top-k cần k phần tử, k-th chỉ cần một giá trị.
4. **Nhầm top-k không thứ tự với top-k đã sắp**: heap không tự sắp đầy đủ.
5. **Dùng min-heap cho top-k nhỏ nhất** mà không đổi hướng so sánh; trường hợp đó thường cần max-heap.
6. **Coi Quickselect luôn `O(n)` worst-case**; bảo đảm tuyến tính thông dụng là kỳ vọng khi pivot ngẫu nhiên.
7. **Quên sao chép nếu không được thay input**: nhiều thuật toán phân hoạch làm thay đổi vị trí phần tử.
8. **Bỏ qua phần tử trùng**, làm sai thứ hạng hoặc số phần tử trong top-k.
9. **Lọc toàn bộ khóa `>=threshold`** rồi tưởng chắc chắn nhận đúng k bản ghi khi có hòa.
10. **Bỏ qua chính sách tie-breaker** nếu hai bản ghi bằng điểm nhưng khác id.
11. **Dùng k không hợp lệ**: k-th cần `1≤k≤n`; top-k có thể quy ước `0≤k≤n`.
12. **Đánh đồng mọi overload `Arrays.sort`** với cùng một cấu trúc nội bộ và cùng cận worst-case.
13. **Chỉ nhìn công tìm vị trí mà quên chi phí xuất kết quả**: top-k có chi phí ghi đầu ra ít nhất `\Omega(k)`.
14. **Bỏ qua số truy vấn**: chọn k phần tử một lần khác với phục vụ hàng triệu câu hỏi thứ hạng trên một mảng không đổi.

## 15. Kiểm thử kết quả và trường hợp biên

| Input / yêu cầu | Kết quả đúng |
| --- | --- |
| `[]`, top-0 | `[]` |
| `[]`, k-th hạng 1 | Không hợp lệ |
| `[5]`, k-th hạng 1 | `5` |
| `[5]`, top-1 | `[5]` |
| `[3,3,3]`, top-2 đếm trùng | `[3,3]` |
| `[-5,-1,-9]`, top-2 lớn nhất theo thứ tự tăng | `[-5,-1]` |
| `[-5,-1,-9]`, nhỏ thứ hai | `-5` |
| `[7,2,9,2,5,9,1]`, nhỏ thứ ba | `2` |
| `[7,2,9,2,5,9,1]`, top-3 tăng | `[7,9,9]` |
| `k<0` hay `k>n` cho top-k | Không hợp lệ |
| `rank=0` hoặc `rank>n` cho k-th 1-based | Không hợp lệ |

Đối với thử nghiệm trên mảng nhỏ, có thể dùng `Arrays.sort` trên **bản sao** như **oracle** kiểm thử:

1. Tạo nhiều mảng: tăng sẵn, đảo ngược, nhiều trùng, mọi phần tử bằng nhau, số âm, cực trị `Integer.MIN_VALUE` và `Integer.MAX_VALUE`.
2. Sắp một bản sao thành `sorted`.
3. Với mọi `rank=1..n`, so `kthSmallest(a,rank)` với `sorted[rank-1]`.
4. Với mọi `k=0..n`, so `topKLargestHeap(a,k)` với đoạn cuối `sorted[n-k..n)` theo cùng thứ tự tăng.
5. Kiểm tra input trước/sau không đổi khi đó là hợp đồng API.
6. Với các bản ghi đồng khóa, thử các trường hợp có nhiều người bằng điểm ở ranh giới k để kiểm tra tie-breaker.

Đối chiếu với full sort giúp phát hiện lỗi trong nhiều test, nhưng **không thay thế chứng minh** đúng đắn hoặc bảo đảm độ phức tạp cho mọi đầu vào.

## 16. Bài tập tự kiểm tra

**Bài 1.** Với `a=[7,2,9,2,5,9,1]`, tìm phần tử lớn thứ ba, nhỏ thứ ba và top-3 lớn nhất giảm dần. Có bài nào bắt buộc sắp **toàn bộ** hay không?

**Bài 2.** Với `a=[4,4,4,8,8,1]`, “lớn thứ hai đếm cả trùng” và “lớn phân biệt thứ hai” có kết quả gì?

**Bài 3.** Mô phỏng min-heap top-3 khi duyệt `7,2,9,2,5,9,1`. Sau giá trị 5 và sau giá trị 9 thứ hai, heap giữ những giá trị nào?

**Bài 4.** Khi phân hoạch ba miền trong Quickselect, vì sao hạng k nằm trong miền bằng pivot thì có thể dừng? Nếu hạng đích ở phía phải thì xử lý tiếp miền nào?

**Bài 5.** Với `k=10` và n rất lớn, heap top-k có lợi thế nào so với sắp toàn bộ? Khi `k=n`, kết luận thay đổi ra sao?

**Bài 6.** Bốn bản ghi `A:95, B:90, C:90, D:85` cần top-2. Kết quả là gì theo (a) đúng 2 người và ưu tiên đến trước; (b) lấy mọi người cùng điểm ở ngưỡng?

**Bài 7.** So sánh cách làm q lần Quickselect kỳ vọng `O(qn)` với sắp một lần `O(n log n+q)`. Điều kiện nào làm sắp một lần đáng giá hơn?

**Bài 8.** Thiết kế hợp đồng `topKLargest` trả đúng k lần xuất hiện, đã sắp tăng, giữ nguyên mảng nguồn; cho phép k=0. Những tiền điều kiện và hậu điều kiện chính là gì?

### Đáp án gợi ý

1. Lớn thứ ba `7`; nhỏ thứ ba `2`; top-3 giảm `[9,9,7]`. Không yêu cầu nào bắt buộc sắp toàn bộ n phần tử.
2. Lớn thứ hai đếm trùng `8`, lớn phân biệt thứ hai `4`.
3. Sau 5: `{5,7,9}`; sau số 9 thứ hai: `{7,9,9}`.
4. Toàn miền giữa bằng pivot và chiếm đúng khoảng thứ hạng; nếu `target>greater` thì xét miền `[greater+1,right]`.
5. Heap chỉ cần `O(k)` bộ nhớ và `O(n log(k+1))` thời gian. Với `k=n`, heap phải giữ n phần tử và xuất theo thứ tự có chi phí bậc `n log n` nên lợi thế ít đi.
6. (a) `[A,B]`; (b) `[A,B,C]`.
7. Khi q lớn và mảng không đổi, chi phí sắp một lần được phân bổ cho nhiều truy vấn `O(1)`. Khi dữ liệu liên tục cập nhật, phải phân tích lại.
8. Yêu cầu `input!=null` và `0≤k≤n`. Kết quả dài đúng k, không giảm, mang đúng k lần xuất hiện có giá trị cao nhất; khi `k>0`, mọi giá trị không được chọn không lớn hơn giá trị nhỏ nhất được chọn; đầu vào không đổi; k=0 trả `[]`.

## Ghi nhớ

- **Chỉ cần min/max:** quét một lượt, `Θ(n)` thời gian và `O(1)` bộ nhớ phụ.
- **Chỉ cần giá trị hạng k:** Quickselect ngẫu nhiên có **thời gian kỳ vọng `O(n)`**, nhưng trường hợp xấu có thể bậc hai; lựa chọn worst-case `O(n)` cần thuật toán chuyên dụng.
- **Cần top-k, k nhỏ hoặc dữ liệu luồng:** heap kích thước k có `O(k)` bộ nhớ và không cần giữ toàn bộ dữ liệu.
- **Cần top-k đã sắp:** có thể chọn trước rồi chỉ sắp k phần tử; phải làm rõ thứ tự xuất và cách xử lý đồng hạng.
- **Cần toàn bộ thứ tự hoặc nhiều lần truy vấn thứ hạng trên mảng tĩnh:** sắp một lần có thể là lựa chọn tốt hơn.
- **Luôn đặc tả rõ** k 0-based/1-based, cách đếm trùng, số phần tử đầu ra, chính sách hòa, dữ liệu tĩnh/luồng và có được sửa input hay không.
