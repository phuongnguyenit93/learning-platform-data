# Chọn top-k bằng phân hoạch và sắp xếp phần cần trả

**Top-k** là bài toán chọn **đúng k phần tử nhỏ nhất hoặc lớn nhất** từ một dãy n phần tử. Trong nhiều ứng dụng, kết quả còn phải được **trả về theo thứ tự** (ví dụ k số nhỏ nhất theo thứ tự tăng, hoặc k số lớn nhất theo thứ tự giảm). Ta không nhất thiết phải sắp xếp toàn bộ n phần tử để làm điều đó.

Một chiến lược rất hiệu quả là:

1. Dùng **phân hoạch** và **quickselect** để đưa đúng nhóm k giá trị cần lấy sang một phía của mảng, không yêu cầu nhóm này đã sắp thứ tự nội bộ.
2. **Chỉ sắp xếp nhóm k phần tử sẽ trả về**, không sắp cả n phần tử.
3. Trả một mảng kết quả có **đúng k** phần tử.

Khi chọn pivot ngẫu nhiên và phân hoạch phù hợp, quickselect có thời gian **O(n) kỳ vọng**; sắp xếp k phần tử thường tốn **O(k log k)**. Như vậy tổng thời gian thường được mô tả là **O(n + k log k) kỳ vọng**, so với O(n log n) nếu sắp xếp toàn bộ dãy bằng thuật toán so sánh. Trường hợp xấu của quickselect vẫn có thể là **O(n²)** nếu liên tục chọn pivot lệch.

Bài học này nằm trong nhóm **chọn và thứ tự**: cần phân biệt **tìm nhóm top-k** với **sắp thứ tự cho chính nhóm đó**, xử lý chính xác các giá trị trùng ở ngưỡng k và chọn chiến lược phù hợp với dữ liệu.

## 1. Xác định hợp đồng bài toán

Cho mảng số nguyên `a` độ dài n và `k`, với **0 ≤ k ≤ n**.

- **k nhỏ nhất (smallest k):** Lấy đúng k phần tử nhỏ nhất **tính cả số lần xuất hiện**. Trả chúng theo thứ tự tăng không giảm.
- **k lớn nhất (largest k):** Lấy đúng k phần tử lớn nhất **tính cả số lần xuất hiện**. Trả chúng theo thứ tự giảm không tăng.
- Nếu `k = 0`, kết quả là mảng rỗng.
- Nếu `k = n`, kết quả chứa toàn bộ dãy theo thứ tự yêu cầu.
- Nếu `k < 0` hoặc `k > n`, đầu vào không hợp lệ.
- Với mảng rỗng, chỉ `k = 0` hợp lệ.
- Bài này trả về **giá trị**, không trả chỉ số gốc hoặc danh tính bản ghi. Nếu cần thêm những thông tin ấy, phải xác định quy tắc chọn khi có nhiều khóa bằng nhau.

Ví dụ:

```text
a = [9, 1, 5, 3, 5, 7, 1, 8, 2]

k=4, nhỏ nhất theo thứ tự tăng: [1, 1, 2, 3]
k=4, lớn nhất theo thứ tự giảm: [9, 8, 7, 5]
k=5, lớn nhất theo thứ tự giảm: [9, 8, 7, 5, 5]
```

Hai số 1 là **hai lần xuất hiện** nên đều có thể được chọn; hai số 5 cũng vậy. Top-k ở đây không có nghĩa là k **giá trị phân biệt**. Nếu yêu cầu “k khóa phân biệt lớn nhất”, cần loại trùng và đó là một bài toán khác.

### Quy tắc hòa tại ranh giới top-k

Giả sử `a = [9,8,5,5,5,1]`, yêu cầu **3 số lớn nhất**. Kết quả theo giá trị là `[9,8,5]`: chỉ cần **một** trong ba bản sao bằng 5 để đủ đúng 3 phần tử. Nếu mảng chứa các đối tượng có ID riêng, cần thêm quy tắc hòa rõ ràng để biết chọn bản ghi 5 nào.

Nếu đề yêu cầu “trả **tất cả** bản ghi có khóa ít nhất bằng khóa của phần tử đứng thứ k” thì số phần tử có thể **lớn hơn k**. Không nên tự đổi yêu cầu này thành “đúng k”.

## 2. Những cách giải có thể dùng

| Cách làm | Ý tưởng | Thời gian điển hình | Bộ nhớ/phù hợp |
| --- | --- | --- | --- |
| Sắp xếp toàn bộ | `sort(a)` rồi lấy k đầu/cuối | O(n log n) với sort so sánh thích hợp | Dễ làm, phù hợp khi gần như cần toàn bộ thứ tự |
| Duy trì heap kích thước k | Quét n phần tử, giữ k ứng viên tốt nhất; sắp xếp k ứng viên khi trả | O(n log k + k log k) khi 1 ≤ k ≤ n | Thường O(k), tốt cho luồng và k nhỏ |
| **Quickselect + sắp xếp k phần tử** | Chọn ranh giới thứ hạng bằng phân hoạch; chỉ sort nhóm cần trả | **O(n + k log k) kỳ vọng** | Tốt khi có mảng trong bộ nhớ và chỉ cần một kết quả top-k |
| Chọn tuyến tính trường hợp xấu + sort k | Dùng thuật toán chọn có bảo đảm O(n), ví dụ median-of-medians | O(n + k log k) theo thuật toán sort có bảo đảm | Bảo đảm mạnh nhưng hiện thực phức tạp hơn |

Lưu ý rằng chi phí của `Arrays.sort(int[])` cụ thể phụ thuộc thuật toán hiện thực trong JDK. Khi phân tích tổng quát, nên viết **O(n) kỳ vọng + T_sort(k)**; với một cách sắp xếp k phần tử mất O(k log k) thì suy ra O(n + k log k) kỳ vọng. Không biến các bảo đảm kỳ vọng thành bảo đảm trường hợp xấu.

## 3. Phân hoạch: không sắp toàn mảng nhưng tách được hai phía

**Partition** nhận một đoạn và pivot p, rồi dời phần tử để nhóm **nhỏ hơn** nằm bên trái và nhóm **lớn hơn** nằm bên phải. Để xử lý tốt nhiều khóa trùng, ta dùng **phân hoạch ba phía** (*Dutch National Flag*):

```text
[ < pivot | = pivot | > pivot ]
  lo..lt-1   lt..gt   gt+1..hi
```

Trong quá trình xử lý đoạn đóng `[lo,hi]`, duy trì ba chỉ số `lt, i, gt`:

```text
[ < pivot | = pivot | chưa biết | > pivot ]
  lo..lt-1   lt..i-1   i..gt    gt+1..hi
```

Khởi tạo `lt=lo, i=lo, gt=hi` và chọn một giá trị pivot thuộc đoạn. Trong khi `i <= gt`:

- Nếu `a[i] < pivot`, hoán đổi `a[i]` với `a[lt]`, rồi tăng **lt và i**.
- Nếu `a[i] > pivot`, hoán đổi `a[i]` với `a[gt]`, rồi **giảm gt nhưng giữ nguyên i**.
- Nếu `a[i] == pivot`, chỉ tăng i.

Giữ nguyên i sau nhánh `> pivot` là bắt buộc: phần tử mới được đổi từ gt vào i vốn nằm trong vùng chưa phân loại, nên cần kiểm tra lại.

**Kết thúc phân hoạch** trả `lt, gt`, xác định khoảng bằng pivot. Tất cả phần tử trước lt đều nhỏ hơn p; tất cả sau gt đều lớn hơn p. Các phần tử trong từng vùng **không nhất thiết đã được sắp tăng**.

Đoạn mã Java cốt lõi (phần chương trình hoàn chỉnh sẽ có phương thức `swap`):

```java
int lt = lo, i = lo, gt = hi;
while (i <= gt) {
    if (a[i] < pivot) {
        swap(a, lt++, i++);
    } else if (a[i] > pivot) {
        swap(a, i, gt--); // Không tăng i
    } else {
        i++;
    }
}
```

**Bất biến:** Ở đầu mỗi vòng, mọi phần tử trước lt đều nhỏ hơn p, đoạn [lt,i) bằng p, đoạn [i,gt] chưa được phân loại và phần sau gt lớn hơn p. Các nhánh chuyển đúng một phần tử từ vùng chưa biết vào một vùng đã biết mà vẫn giữ bất biến.

**Chứng minh kết thúc:** Số phần tử chưa biết `gt-i+1` không âm khi vòng còn chạy và **giảm 1 sau mỗi lượt**: hoặc i tăng, hoặc gt giảm. Phân hoạch một đoạn có m phần tử mất **Θ(m)** thời gian và **O(1)** bộ nhớ phụ.

## 4. Quickselect: chỉ tìm ranh giới thứ hạng cần thiết

Giả sử ta đánh số thứ hạng tăng từ **0 đến n−1**: thứ hạng 0 là giá trị nhỏ nhất, thứ hạng n−1 là lớn nhất. **Quickselect** tìm vị trí thứ hạng `r` mà không sắp hoàn toàn mảng.

Thuật toán lặp:

1. Giữ đoạn cần xét `[lo,hi]` ban đầu bằng toàn mảng.
2. Chọn **một pivot ngẫu nhiên** trong đoạn.
3. Phân hoạch ba phía để lấy vùng bằng `[lt,gt]`.
4. Nếu `r < lt`, chỉ cần tiếp tục bên trái: `hi = lt−1`.
5. Nếu `r > gt`, chỉ cần tiếp tục bên phải: `lo = gt+1`.
6. Nếu `lt ≤ r ≤ gt`, thứ hạng r rơi vào vùng bằng pivot: **dừng**.

Khác với quicksort, quickselect **chỉ đi tiếp một phía**, không sắp đệ quy cả hai phía. Sau khi quickselect dừng với thứ hạng r, phần tử tại r thuộc giá trị có thứ hạng r của dãy đã sắp, và ta có tính chất ngưỡng:

```text
mọi a[0 .. r-1] <= a[r]
mọi a[r+1 .. n-1] >= a[r]
```

Các phần tử trong đoạn trái và đoạn phải **vẫn có thể lộn xộn**. Tính chất đủ để chọn top-k nhưng chưa đủ để trả kết quả theo thứ tự mong muốn.

### Minh họa một bước chọn

Xét `[8, 2, 5, 1, 5, 4, 9]`, muốn k=3 số nhỏ nhất. Nếu chọn pivot=5 và phân hoạch ba phía, một kết quả hợp lệ là:

```text
[2, 1, 4 | 5, 5 | 8, 9]
   < 5      = 5      > 5
```

Ta cần **r = k−1 = 2** (giá trị nhỏ thứ ba). Vùng bằng có chỉ số 3..4, nên r=2 nằm **bên trái**. Chỉ tiếp tục quickselect trên ba phần tử `[2,1,4]`. Khi tìm được r, ba phần tử đầu chắc chắn là ba giá trị nhỏ nhất, nhưng có thể vẫn ở thứ tự `[2,1,4]`; phải sắp riêng ba phần tử đó để trả `[1,2,4]`.

Tương tự, muốn k=3 số lớn nhất, cần ngưỡng tại thứ hạng `r = n−k = 4`. Sau quickselect, ba vị trí từ `n−k` đến `n−1` chứa đúng ba phần tử lớn nhất; sau đó chỉ sắp riêng đoạn đó theo thứ tự giảm.

### Vai trò của phần bằng pivot

Nếu có nhiều bản sao bằng nhau, vùng `[lt,gt]` có thể chứa nhiều phần tử. Khi r nằm trong vùng này, **không cần phân hoạch thêm để xác định giá trị ngưỡng**. Với yêu cầu đúng k phần tử, mảng đã phân hoạch sẽ có đúng r phần tử trước r và n−r−1 phần tử sau; các bản sao bằng ngưỡng có thể nằm cả hai bên r nhưng điều đó không làm sai **đa tập giá trị** của top-k.

Với đối tượng có ID và cùng điểm số, thuật toán không tự bảo đảm bản ghi nào trong nhóm cùng điểm được lấy. Nếu đề bài cần quy tắc hòa, hãy định nghĩa một thứ tự toàn phần, chẳng hạn **điểm giảm, rồi ID tăng**, và dùng comparator ấy trong mọi bước chọn/sắp xếp.

## 5. Chọn đúng k phần tử nhỏ nhất rồi sắp xếp

Giả sử `1 ≤ k < n` và muốn trả về k phần tử nhỏ nhất **theo thứ tự tăng**.

**Bước A — Chọn ngưỡng:** Quickselect tại thứ hạng `r=k−1`. Sau đó `a[0..k−1]` chứa **đúng k giá trị nhỏ nhất** dưới dạng một đa tập, dù chưa theo thứ tự.

**Bước B — Trích phần cần trả:** Sao chép `a[0..k)` ra mảng kết quả độ dài k (hoặc sắp trực tiếp vùng đầu nếu chấp nhận sửa mảng đầu vào).

**Bước C — Sắp xếp:** Sắp mảng kết quả k phần tử theo thứ tự tăng. Không làm thêm việc sắp n−k phần tử còn lại.

```text
Đầu vào:       [9, 1, 5, 3, 5, 7, 1, 8, 2], k=4
Sau chọn:      [1, 2, 1, 3 | các phần tử còn lại theo thứ tự bất kỳ]
                  4 số nhỏ nhất (chưa sắp)

Sắp phần trả:  [1, 1, 2, 3]
```

Đây là **minh họa một trạng thái hợp lệ**, không phải thứ tự trung gian cố định của code dùng pivot ngẫu nhiên.

**Trường hợp k=0:** Trả mảng rỗng; không được gọi quickselect ở thứ hạng -1. **Trường hợp k=n:** Không cần chọn ngưỡng vì toàn bộ phần tử đều được lấy; chỉ sao chép và sắp toàn bộ n giá trị.

## 6. Chọn đúng k phần tử lớn nhất rồi sắp xếp

Nếu muốn k phần tử **lớn nhất theo thứ tự giảm**:

1. Đặt **r = n−k**, tương ứng vị trí đầu tiên trong nhóm k phần tử lớn nhất khi toàn dãy được sắp tăng.
2. Quickselect tại thứ hạng r; sau đó `a[r..n)` chứa đúng k giá trị lớn nhất, kể cả bản sao.
3. Sao chép phần đuôi ấy, sắp tăng k phần tử rồi **đảo chiều** để trả theo thứ tự giảm.

Ví dụ:

```text
a = [9, 1, 5, 3, 5, 7, 1, 8, 2]
n = 9, k = 4, r = 5

Phần đuôi sau chọn chứa (thứ tự chưa cố định): [5, 9, 7, 8]
Sắp tăng: [5, 7, 8, 9]
Đảo chiều: [9, 8, 7, 5]
```

Không nên lấy `r=k−1` cho bài chọn lớn nhất, trừ khi đã sửa định nghĩa thứ hạng theo thứ tự giảm. Cách viết ở đây dùng **duy nhất thứ hạng tăng** để tránh lẫn lộn.

Cũng như trường hợp nhỏ nhất, nếu k=n chỉ cần sắp toàn bộ phần sao chép theo thứ tự giảm; nếu k=0 trả rỗng.

## 7. Vì sao hai bước cho kết quả đúng?

### Bổ đề 1 — Phân hoạch ba phía đúng

Bốn vùng trong phần 3 có bất biến rõ ràng. Mỗi vòng phân loại một phần tử, không thay đổi đa tập vì chỉ hoán đổi. Khi vùng chưa biết rỗng, đoạn được chia thành ba nhóm <, =, > pivot. Do đó mọi phần tử ở bên trái vùng bằng không lớn hơn bất kỳ phần tử ở vùng bằng/phải, và ngược lại đối với phía phải.

### Bổ đề 2 — Quickselect tìm đúng thứ hạng

Gọi r là thứ hạng cần chọn, tính từ 0. Mỗi lần phân hoạch:

- Nếu r nằm **bên trái vùng bằng**, mọi phần tử trong vùng bằng/phải đều không thể là giá trị nhỏ thứ r+1; ta có thể loại phần đó.
- Nếu r nằm **bên phải vùng bằng**, toàn bộ vùng trái/bằng có thứ hạng nhỏ hơn hoặc bằng các phần tử phía phải, nên chỉ cần tìm tiếp bên phải.
- Nếu r nằm **trong vùng bằng**, giá trị pivot chính là **giá trị ngưỡng thứ hạng r** (kể cả khi có trùng), nên có thể dừng.

Những vùng đã loại luôn đứng đúng phía của ngưỡng do quan hệ phân hoạch. Thuật toán lặp cho đến khi r nằm trong vùng bằng và lúc ấy các giá trị ở **bên trái r không lớn hơn giá trị tại r**, các giá trị bên phải r không nhỏ hơn giá trị tại r. Mỗi lần không dừng, đoạn `[lo,hi]` bị thu nhỏ nghiêm ngặt, nên quickselect kết thúc.

### Bổ đề 3 — Trích đúng k phần tử

- Với **k nhỏ nhất**, chọn r=k−1. Các chỉ số `0..k−1` chứa k giá trị nhỏ nhất (tính cả số lần xuất hiện). Không có giá trị nào ở ngoài nhóm này **nhỏ hơn** một giá trị trong nhóm được giữ.
- Với **k lớn nhất**, chọn r=n−k. Các chỉ số `n−k..n−1` chứa k giá trị lớn nhất. Không có giá trị nào ở ngoài nhóm này **lớn hơn** một giá trị trong nhóm được giữ.

Trường hợp bằng nhau ở ngưỡng không phá chứng minh: nếu đổi một phần tử có giá trị bằng ngưỡng ở trong nhóm với một phần tử bằng ngưỡng ở ngoài nhóm, **đa tập giá trị kết quả không đổi**.

### Định lý — Sắp chỉ phần trả là đủ

Việc quickselect đã đảm bảo **đúng tập đa giá trị** cần lấy. Bước sắp xếp trên k phần tử chỉ **thay đổi thứ tự** trong tập này, không thêm hoặc mất phần tử. Vì vậy sau sắp tăng hoặc giảm, kết quả vừa có đúng k giá trị top-k, vừa có thứ tự yêu cầu. Không cần sắp xếp những phần tử bị loại.

## 8. Phân tích thời gian và bộ nhớ

Với n phần tử, k trong [0,n], và giả định so sánh/hoán đổi hai số nguyên có chi phí O(1):

| Giai đoạn | Thời gian |
| --- | --- |
| Sao chép n phần tử để không sửa đầu vào | O(n) |
| Quickselect với pivot ngẫu nhiên và phân hoạch ba phía | **O(n) kỳ vọng**, **O(n²)** trường hợp xấu |
| Sao chép k phần tử được chọn | O(k) |
| Sắp xếp riêng k phần tử | `T_sort(k)`, thường O(k log k) với thuật toán so sánh |
| Đảo chiều k phần tử (k lớn nhất) | O(k) |
| **Tổng điển hình** | **O(n + k log k) kỳ vọng** nếu sort k là O(k log k) |
| **Tổng trong tình huống quickselect xấu** | **O(n² + T_sort(k))** |

**Tại sao quickselect kỳ vọng O(n)?** Mỗi lần phân hoạch quét m phần tử trong đoạn đang xét và chọn ngẫu nhiên pivot. Trung bình, đoạn cần xét sau phân hoạch giảm đủ nhanh để tổng kích thước các lượt quét có cấp O(n). Không phải mọi chuỗi pivot đều tốt: nếu liên tục chọn phần tử gần cực trị, các lượt xử lý có thể có kích thước n, n−1, n−2, ... và tổng tăng đến Θ(n²).

**Khi tất cả khóa bằng nhau:** Phân hoạch ba phía tạo một vùng bằng chứa **toàn bộ n phần tử**; r thuộc vùng đó và quickselect kết thúc sau một lượt O(n). Sau đó thuật toán vẫn sắp k phần tử để đáp ứng yêu cầu sắp đầu ra. Nếu biết chắc mọi khóa bằng nhau, có thể bỏ cả bước sort, nhưng chương trình mẫu không tự thêm đường tắt này.

**Bộ nhớ cần phân biệt:**

- Phần phân hoạch + quickselect **tại chỗ** dùng **O(1)** biến phụ (chưa tính bộ nhớ bên ngoài).
- Chương trình ví dụ **chủ động sao chép toàn mảng** để không sửa đầu vào, nên dùng **O(n)** bộ nhớ cho `work`.
- Kết quả được cấp phát thêm **O(k)** ô.
- Hàm sort k phần tử có thể có thêm bộ nhớ/stack nội bộ tùy API và kiểu dữ liệu; không nên khẳng định mọi hiện thực sort đều hoàn toàn O(1) bộ nhớ.

Nếu được phép sửa mảng đầu vào, có thể chạy quickselect trực tiếp trên nó và giảm phần sao chép O(n). Tuy nhiên bản chất **tại chỗ** của phân hoạch không có nghĩa toàn bộ hàm trả một mảng kết quả là O(1) bộ nhớ: riêng đầu ra k phần tử đã cần O(k).

**Khi k gần n:** Bước sort k gần như sắp cả n phần tử; lợi thế so với sắp toàn bộ giảm. Với k=n, chương trình bỏ quickselect và sắp cả bản sao. Khi k rất nhỏ, phần sort k rẻ và phần chọn kỳ vọng O(n) thường chiếm ưu thế.

## 9. Chương trình Java 17+ hoàn chỉnh

Chương trình sắp xếp đúng k **giá trị**, không sửa mảng truyền vào. Nó dùng quickselect lặp để tránh stack sâu trong bước chọn và **phân hoạch ba phía** để không mất công chọn lại nhiều giá trị trùng. Pivot được chọn ngẫu nhiên bằng `Random`; seed cố định chỉ giúp tái lập quá trình chọn khi thử nghiệm, **không làm thay đổi kết quả đã sắp**, và không tạo bảo đảm thời gian trường hợp xấu.

Lưu file **`TopKPartitionSort.java`**:

```java
import java.util.Arrays;
import java.util.Objects;
import java.util.Random;

public class TopKPartitionSort {
    static void swap(int[] a, int i, int j) {
        int tmp = a[i];
        a[i] = a[j];
        a[j] = tmp;
    }

    // Chon gia tri co thu hang rank (0-based, theo thu tu tang).
    // Khi dung, moi phan tu truoc rank <= a[rank],
    // moi phan tu sau rank >= a[rank].
    static void selectRank(int[] a, int rank, Random random) {
        int lo = 0;
        int hi = a.length - 1;

        while (lo <= hi) {
            int pivot = a[lo + random.nextInt(hi - lo + 1)];
            int lt = lo;
            int i = lo;
            int gt = hi;

            while (i <= gt) {
                if (a[i] < pivot) {
                    swap(a, lt, i);
                    lt++;
                    i++;
                } else if (a[i] > pivot) {
                    swap(a, i, gt);
                    gt--; // i giu nguyen: gia tri moi chua biet
                } else {
                    i++;
                }
            }

            if (rank < lt) {
                hi = lt - 1;
            } else if (rank > gt) {
                lo = gt + 1;
            } else {
                return;
            }
        }
        throw new AssertionError("rank must be valid");
    }

    static void checkK(int[] input, int k) {
        Objects.requireNonNull(input, "input must not be null");
        if (k < 0 || k > input.length) {
            throw new IllegalArgumentException(
                    "k must be between 0 and n");
        }
    }

    public static int[] smallestSorted(int[] input, int k) {
        checkK(input, k);
        if (k == 0) {
            return new int[0];
        }

        int[] work = input.clone();
        if (k < work.length) {
            selectRank(work, k - 1, new Random(2026L));
        }
        int[] result = Arrays.copyOf(work, k);
        Arrays.sort(result);
        return result;
    }

    public static int[] largestSorted(int[] input, int k) {
        checkK(input, k);
        if (k == 0) {
            return new int[0];
        }

        int[] work = input.clone();
        int boundary = work.length - k;
        if (boundary > 0) {
            selectRank(work, boundary, new Random(2026L));
        }

        int[] result = Arrays.copyOfRange(
                work, boundary, work.length);
        Arrays.sort(result);
        for (int left = 0, right = result.length - 1;
                left < right; left++, right--) {
            swap(result, left, right);
        }
        return result;
    }

    public static void main(String[] args) {
        int[] input = {9, 1, 5, 3, 5, 7, 1, 8, 2};

        System.out.println("Top 4 smallest: "
                + Arrays.toString(smallestSorted(input, 4)));
        System.out.println("Top 4 largest: "
                + Arrays.toString(largestSorted(input, 4)));
        System.out.println("Top 5 largest: "
                + Arrays.toString(largestSorted(input, 5)));
        System.out.println("k=0: "
                + Arrays.toString(smallestSorted(input, 0)));
        System.out.println("k=n smallest: "
                + Arrays.toString(
                        smallestSorted(input, input.length)));
        System.out.println("all equal k=3: "
                + Arrays.toString(
                        smallestSorted(new int[]{4, 4, 4, 4}, 3)));

        int[] extreme = {
            Integer.MIN_VALUE, 0, Integer.MAX_VALUE, -1
        };
        System.out.println("extreme smallest: "
                + Arrays.toString(smallestSorted(extreme, 2)));
        System.out.println("extreme largest: "
                + Arrays.toString(largestSorted(extreme, 2)));

        System.out.println("input unchanged: "
                + Arrays.toString(input));

        try {
            smallestSorted(input, -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid k: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac TopKPartitionSort.java
java TopKPartitionSort
```

Kết quả stdout chính xác:

```text
Top 4 smallest: [1, 1, 2, 3]
Top 4 largest: [9, 8, 7, 5]
Top 5 largest: [9, 8, 7, 5, 5]
k=0: []
k=n smallest: [1, 1, 2, 3, 5, 5, 7, 8, 9]
all equal k=3: [4, 4, 4]
extreme smallest: [-2147483648, -1]
extreme largest: [2147483647, 0]
input unchanged: [9, 1, 5, 3, 5, 7, 1, 8, 2]
invalid k: k must be between 0 and n
```

**Giải thích kết quả:**

- Tập giá trị `[9,1,5,3,5,7,1,8,2]` chứa hai số 1 và hai số 5. Top 4 nhỏ nhất gồm cả hai số 1; top 5 lớn nhất gồm cả hai số 5.
- Khi k=0, không thực hiện quickselect và trả mảng rỗng.
- Khi k=n, không cần quickselect vì mọi phần tử đều được chọn; chỉ sort bản sao.
- Mảng toàn giá trị 4 có vùng bằng pivot rất lớn, quickselect không cần phân nhánh tìm kiếm nhiều lần.
- Giá trị âm, `Integer.MIN_VALUE` và `Integer.MAX_VALUE` đều xử lý được vì mã so sánh trực tiếp, không lấy hiệu có thể tràn.
- Dữ liệu đầu vào vẫn giữ nguyên vì cả hai hàm đều gọi `input.clone()` trước khi phân hoạch.
- `k=-1` bị từ chối trước khi cấp phát hay truy cập phần tử; k>n cũng bị từ chối tương tự.

**Lưu ý mã:** `selectRank` là phương thức dùng nội bộ. Nó chỉ được gọi khi **0 ≤ rank < a.length**; hai hàm công khai đã đảm bảo điều kiện ấy. Kết quả của `selectRank` không phải mảng được sắp toàn bộ; đó chỉ là một **phân hoạch theo ngưỡng thứ hạng**. `Arrays.sort(result)` mới tạo thứ tự cuối cùng cho k phần tử được trả.

## 10. Kiểm tra trường hợp biên và tính đúng đầu ra

| Dữ liệu/điều kiện | Kết quả phù hợp |
| --- | --- |
| `n=0, k=0` | Trả `[]` |
| `n=0, k>0` | Ném `IllegalArgumentException` |
| `k=0` | Không chọn và không sort, trả `[]` |
| `k=1` | Trả min hoặc max tương ứng dưới dạng mảng 1 phần tử |
| `k=n` | Sắp toàn bộ n phần tử theo chiều yêu cầu |
| `k<0` hoặc `k>n` | Ném `IllegalArgumentException` |
| Mọi giá trị bằng nhau | Lấy đúng k bản sao có cùng giá trị |
| Nhiều giá trị trùng ở ngưỡng | Chọn **đúng k** phần tử, có thể chỉ lấy một số bản sao của ngưỡng |
| Có cả âm và dương | Dùng phép so sánh số nguyên trực tiếp, vẫn đúng |
| Mảng đầu vào `null` | Mã minh họa ném `NullPointerException` thông qua `Objects.requireNonNull` |
| Cần giữ thứ tự ban đầu của các bản ghi đồng điểm | Phải thêm quy tắc hòa/giải pháp ổn định; mã sắp int không cung cấp tính chất đó |

### Cẩn trọng với bản ghi có khóa và ID

Nếu đầu vào là danh sách `(score, id)` thay vì `int[]`, **các bản ghi đồng điểm không còn hoán đổi tự do** khi yêu cầu là “trả đúng k bản ghi”. Cần xác định, ví dụ:

- Ưu tiên score cao hơn.
- Nếu score bằng, ưu tiên ID nhỏ hơn.
- Nếu score và ID cùng bằng, chọn theo chỉ số đầu vào.

Ta có thể áp dụng quickselect với **comparator thống nhất** ở cả phân hoạch lẫn sort phần trả, nhưng thuật toán phân hoạch tại chỗ **không ổn định** theo nghĩa giữ nguyên thứ tự ban đầu. Nếu yêu cầu “giữ thứ tự gốc trong kết quả”, cần thiết kế rõ bước chọn, sắp và cách xử lý hòa.

### Trả top-k không sắp thứ tự thì sao?

Nếu chỉ cần **một nhóm đúng k giá trị** mà không yêu cầu thứ tự, có thể bỏ `Arrays.sort(result)`. Khi đó thời gian kỳ vọng của thuật toán chọn chỉ là **O(n)**, cộng O(k) để sao chép kết quả (đã được bao trong O(n) vì k≤n). Đây là lý do phải đọc kỹ đề: “chọn” và “chọn rồi sắp phần cần trả” có chi phí khác nhau.

## 11. Khi nào nên dùng heap, quickselect hoặc full sort?

**Quickselect + sort phần trả** hợp lý khi dữ liệu đã có đầy đủ trong bộ nhớ, chỉ cần làm một lần hoặc một ít truy vấn top-k trên mảng, và k nhỏ hơn nhiều so với n. Nó tiết kiệm việc tạo thứ tự cho n−k phần tử bị loại.

**Heap kích thước k** hợp lý khi dữ liệu đi vào dạng luồng, không muốn giữ toàn bộ n phần tử, hoặc cần cập nhật top-k liên tục. Ví dụ giữ k giá trị lớn nhất thì dùng **min-heap** gồm k phần tử: phần tử nhỏ nhất trong heap là ngưỡng loại; gặp giá trị lớn hơn ngưỡng thì thay thế. Sau một lần quét, nếu cần thứ tự giảm, sắp riêng k phần tử trong heap. Thời gian khoảng O(n log k + k log k), bộ nhớ O(k).

**Sắp toàn bộ** phù hợp khi cũng cần thứ tự của các phần tử còn lại, cần nhiều loại truy vấn sau đó, hoặc k gần n khiến việc sort riêng k phần tử không tiết kiệm được bao nhiêu. Ngoài ra, thư viện sort thường đã được tối ưu kỹ và có thể nhanh hơn trên dữ liệu nhỏ dù Big O chưa phải tốt nhất về mặt lý thuyết.

**Sắp top-k bằng cấu trúc có bảo đảm trường hợp xấu** cần được cân nhắc nếu độ trễ tệ nhất là yêu cầu bắt buộc. Randomized quickselect chỉ có bảo đảm kỳ vọng O(n); nếu cần bảo đảm O(n) cho bước chọn có thể dùng thuật toán chọn xác định như median-of-medians, đổi lại độ phức tạp triển khai và hằng số thời gian.

## 12. Lỗi thường gặp và cách tránh

1. **Sắp toàn bộ mặc định dù chỉ trả k phần tử.** Nếu không cần thứ tự cho phần bị loại, quickselect + sort k có thể ít thao tác hơn.
2. **Nghĩ quickselect đã sắp k phần tử.** Nó chỉ đảm bảo nhóm đúng phía ngưỡng; cần `sort` phần trả nếu yêu cầu thứ tự.
3. **Sai thứ hạng 0-based:** k nhỏ nhất chọn `r=k−1`; k lớn nhất chọn `r=n−k`. K=0 phải xử lý riêng.
4. **Nhầm phân hoạch hai phía với ba phía:** Với nhiều bản sao bằng pivot, phân hoạch ba phía có thể kết thúc ngay khi rank rơi trong vùng bằng; không cần loại từng bản sao một.
5. **Tăng i ngay sau khi đổi với gt:** Phần tử đổi vào vị trí i chưa biết, phải xét lại. Tăng i lúc này có thể khiến phân hoạch sai.
6. **Quên ngăn tràn khi tính pivot index/rank:** Chỉ chọn ngẫu nhiên trong đoạn hợp lệ; `random.nextInt(hi-lo+1)` yêu cầu `hi>=lo` và chiều dài dương.
7. **Cho rằng randomized quickselect luôn O(n).** Chỉ kỳ vọng tuyến tính; trường hợp xấu vẫn O(n²).
8. **Không tính bộ nhớ do clone.** Code minh họa có mảng work O(n) và kết quả O(k), dù phân hoạch riêng lẻ chỉ O(1) bộ nhớ phụ.
9. **Giữ toàn bộ phần bằng ngưỡng dù đề yêu cầu đúng k.** Nếu có nhiều bản sao đồng điểm ở biên, kết quả phải đủ **đúng k**. Yêu cầu “tất cả đồng điểm” là bài toán khác.
10. **Đổi chiều sort mà không đổi cách chọn.** Chọn k nhỏ nhất rồi sort giảm **không** thành k lớn nhất; trước hết phải chọn đúng phần tử theo ngưỡng tương ứng.
11. **Sử dụng phép trừ để so sánh int.** `a[i]-pivot` có thể tràn ở giá trị cực trị; dùng `<`, `>` trực tiếp.
12. **Tự giả định tính ổn định.** Các phép swap trong phân hoạch không giữ thứ tự gốc của bản ghi có khóa bằng nhau.
13. **Dùng `Arrays.sort` trên cả mảng work thay vì result.** Nếu sort toàn bộ work sau khi chọn, ta đã vô tình trả lại chi phí sắp toàn bộ và bỏ mất lợi thế của bài toán.
14. **Dùng heap nhưng không sort phần trả khi đề yêu cầu:** Heap chỉ đảm bảo quan hệ cha-con, không phải toàn bộ k phần tử đã có thứ tự.
15. **Bỏ qua hợp đồng lỗi:** n=0, k=0, k>n, null và k=n nên có xử lý rõ ràng, tránh truy cập rank không hợp lệ.

## 13. Câu hỏi ôn tập có đáp án

**Câu 1.** Cho `a=[7,2,9,2,5,4]`, k=3. Kết quả k nhỏ nhất và k lớn nhất có thứ tự là gì?

**Đáp án:** Nhỏ nhất tăng: `[2,2,4]`. Lớn nhất giảm: `[9,7,5]`.

**Câu 2.** Cho `n=10` và `k=3`. Thứ hạng (0-based theo thứ tự tăng) cần quickselect cho k nhỏ nhất và k lớn nhất?

**Đáp án:** k nhỏ nhất: `r=k−1=2`. K lớn nhất: `r=n−k=7`. Nhóm trả tương ứng là ba phần tử đầu hoặc ba phần tử cuối sau khi chọn ngưỡng.

**Câu 3.** Vì sao kết quả quickselect thường chưa đủ để trả danh sách k nhỏ nhất theo thứ tự tăng?

**Đáp án:** Phân hoạch chỉ đảm bảo tất cả giá trị trong nhóm chọn không lớn hơn các giá trị bị loại; nó không sắp phần tử **bên trong nhóm**. Phải sort k phần tử được chọn nếu đề yêu cầu thứ tự.

**Câu 4.** `a=[10,8,8,8,1]`, k=2 lớn nhất. Kết quả theo giá trị là gì? Có cần lấy cả ba số 8 không?

**Đáp án:** `[10,8]`. Chỉ lấy **một** trong ba bản sao 8 để đủ đúng k=2; không lấy cả ba trừ khi bài toán quy định khác.

**Câu 5.** Nếu bỏ bước sắp xếp kết quả, quickselect ngẫu nhiên có độ phức tạp kỳ vọng là gì?

**Đáp án:** O(n) để chọn ngưỡng (cộng O(k) để trích kết quả, đã không lớn hơn O(n)). Nhưng trường hợp xấu vẫn O(n²).

**Câu 6.** Tại sao thuật toán này có thể cần O(n) bộ nhớ trong ví dụ Java dù phân hoạch tại chỗ chỉ O(1)?

**Đáp án:** Hai hàm đều clone mảng đầu vào dài n, tạo mảng `work` O(n) nhằm không sửa input, rồi cấp phát thêm result O(k). Nếu phân hoạch trực tiếp trên input, có thể bỏ clone nhưng mất tính không thay đổi đầu vào.

**Câu 7.** Khi mọi phần tử đều bằng nhau, phân hoạch ba phía giúp gì?

**Đáp án:** Cả đoạn nằm trong vùng bằng pivot; thứ hạng cần chọn cũng nằm trong vùng này nên quickselect dừng ngay sau một lần phân hoạch O(n), tránh xử lý lặp lại các bản sao.

**Câu 8.** Nếu dữ liệu đến liên tục và không thể giữ toàn bộ n phần tử, chiến lược nào thực tế hơn?

**Đáp án:** Một heap kích thước k thường phù hợp: quét và duy trì k ứng viên tốt nhất với bộ nhớ O(k); khi cần trả có thứ tự mới sắp k phần tử.

**Câu 9.** Yêu cầu là “top 3 sinh viên theo điểm, nếu bằng điểm chọn ID nhỏ hơn”. Cần thay đổi gì?

**Đáp án:** Dùng cặp khóa **điểm giảm và ID tăng** làm quy tắc so sánh xuyên suốt bước chọn và sắp. Không thể dựa vào `int[]` điểm và mong phân hoạch tự chọn đúng ID trong các nhóm đồng điểm.

## Ghi nhớ

Bài toán **top-k có thứ tự** gồm hai việc khác nhau: **chọn đúng k giá trị theo ngưỡng thứ hạng** và **sắp xếp chỉ k giá trị sẽ trả**. Quickselect với phân hoạch ba phía xử lý hiệu quả các giá trị trùng và có thời gian **O(n) kỳ vọng** để chọn; sort k phần tử thường thêm **O(k log k)**. Chọn k nhỏ nhất dùng **rank k−1**, chọn k lớn nhất dùng **rank n−k** (0-based, thứ tự tăng). Phải xử lý k=0/k=n, số lần xuất hiện trùng, bộ nhớ sao chép và sự khác nhau giữa bảo đảm kỳ vọng với trường hợp xấu trước khi áp dụng.
