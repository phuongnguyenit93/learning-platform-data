# Xây heap từ dưới lên với chi phí tuyến tính

Giả sử có một mảng gồm rất nhiều công việc, mỗi công việc mang một **khóa ưu tiên**. Ta muốn chuyển mảng ấy thành **heap nhị phân** (*binary heap*) để xem nhanh công việc ưu tiên nhất và lấy nó ra hiệu quả. Cách dễ nghĩ đến là bắt đầu với heap rỗng rồi thêm từng phần tử bằng **sift-up**. Tuy nhiên, nếu **toàn bộ dữ liệu đã có sẵn**, ta có thể xây heap nhanh hơn trong trường hợp xấu nhất: **bottom-up heapify**, hay **xây heap từ dưới lên**.

Điểm đáng chú ý là một lần **sift-down** có thể mất O(log n), nhưng khi gọi sift-down trên các nút theo đúng thứ tự **từ nút trong cuối cùng về gốc**, tổng thời gian lại chỉ là **Θ(n)**. Lý do là phần lớn các nút nằm gần lá nên không thể di chuyển xuống nhiều mức.

Bài thuộc chương **Heap và hàng đợi ưu tiên** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, theo định hướng học bất biến, thao tác và chi phí thời gian/bộ nhớ để chọn cấu trúc dữ liệu phù hợp. Trọng tâm bài là **xây min-heap/max-heap từ một mảng bất kỳ**, chứng minh chi phí tuyến tính và phân biệt rõ việc xây heap với việc sắp xếp mảng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhắc lại hai bất biến của heap nhị phân: **cây gần đầy đủ** và **quan hệ thứ tự cha–con**.
- Tìm nút trong cuối cùng bằng **n // 2 − 1** khi đánh số mảng từ 0.
- Mô tả và cài đặt thao tác **sift-down** với tiền điều kiện hai cây con đã là heap.
- Xây min-heap bằng cách xử lý các nút từ **n // 2 − 1** tới **0**.
- Giải thích bất biến vòng lặp và chứng minh toàn bộ mảng trở thành heap.
- Mô phỏng những lần hoán đổi và nhận diện trường hợp nút chỉ có một con.
- Chứng minh **Θ(n)** bằng cách cộng chi phí theo **chiều cao các nút**, không nhân n với log n một cách máy móc.
- So sánh bottom-up heapify với xây heap bằng n lần push.
- Phân biệt **heapify tại chỗ** (O(1) bộ nhớ phụ) và heapify trên bản sao (O(n) bộ nhớ bổ sung).
- Dùng Python tự viết heapify, kiểm tra bất biến và so sánh với **heapq.heapify**.
- Xử lý trường hợp rỗng, một nút, khóa trùng, min-heap, max-heap và payload có khóa ưu tiên.
- Chọn phương án xây heap cho các tình huống nạp dữ liệu theo lô.

## 2. Bất biến và biểu diễn bằng mảng

**Binary heap** là một cây nhị phân gần đầy đủ (*complete binary tree*) có thứ tự heap (*heap-order property*).

**Bất biến hình dạng:** mọi mức trước mức cuối đều đầy, mức cuối được điền liên tục từ trái qua phải. Khi lưu các nút vào mảng theo **thứ tự mức** (*level-order*), chúng nằm ở các chỉ số liên tiếp **0, 1, ..., n − 1** mà không có lỗ trống.

**Bất biến thứ tự:**

- **Min-heap:** với mỗi nút khác gốc, khóa của cha **≤** khóa nút đó.
- **Max-heap:** với mỗi nút khác gốc, khóa của cha **≥** khóa nút đó.

Ví dụ mảng chưa phải min-heap:

~~~text
a = [9, 5, 7, 3, 8, 4]

                     (0) 9
                     /   \
                 (1) 5   (2) 7
                 /   \      /
             (3) 3 (4) 8 (5) 4

index:  0  1  2  3  4  5
value: [9, 5, 7, 3, 8, 4]
~~~

Hình dạng gần đầy đủ đã đúng; nhưng **9 > 5**, **5 > 3**, **7 > 4** nên có những cạnh vi phạm thứ tự min-heap.

Với chỉ số 0-based:

| Quan hệ | Công thức | Điều kiện |
| --- | --- | --- |
| Gốc | **0** | n > 0 |
| Cha của i | **(i − 1) // 2** | i > 0 |
| Con trái của i | **2i + 1** | Chỉ tồn tại nếu 2i + 1 < n |
| Con phải của i | **2i + 2** | Chỉ tồn tại nếu 2i + 2 < n |
| Nút trong cuối | **n // 2 − 1** | n ≥ 2 |
| Các nút lá | **i ≥ n // 2** | 0 ≤ i < n |

Công thức này **khác** công thức cho mảng đánh số từ 1. Trong toàn bài dùng chỉ số 0-based.

**Ghi nhớ:** Heap **không phải mảng được sắp xếp toàn cục**. Khi min-heap hợp lệ, gốc chứa khóa nhỏ nhất, nhưng hai nút ở hai nhánh khác nhau có thể không theo thứ tự tăng dần.

## 3. Hai chiến lược xây heap từ n phần tử

### 3.1. Chèn lần lượt bằng sift-up

Một cách triển khai trực quan:

~~~text
heap = rỗng
for x trong mảng đầu vào:
    heap.push(x)        # append rồi sift-up
~~~

Khi heap đã có k phần tử, một lần push có thể đi lên **O(log(k + 1))** mức. Tổng n lần push có **cận trên O(n log n)**; tồn tại đầu vào khiến tổng chi phí đạt **Θ(n log n)**.

Cách này tự nhiên nếu phần tử đến **từng lúc** hoặc hệ thống đã có API push. Nhưng với một mảng n phần tử có sẵn, nó chưa tận dụng được tính chất các nút lá.

### 3.2. Sửa từ lá lên gốc bằng sift-down

Ý tưởng bottom-up:

1. Dùng **chính mảng đầu vào** làm biểu diễn cây gần đầy đủ.
2. Các nút lá đã là heap vì không có con để vi phạm thứ tự.
3. Từ **nút trong cuối cùng**, gọi **sift-down** để sửa cây con tại nút đó.
4. Đi tới nút có chỉ số nhỏ hơn; các cây con của nó đã được xử lý trước.
5. Dừng sau khi sửa gốc 0.

~~~text
for i = n // 2 - 1, n // 2 - 2, ..., 0:
    sift_down(a, i)
~~~

Kết quả bảo toàn toàn bộ các entry đầu vào, chỉ thay **vị trí** của chúng trong mảng.

| Tiêu chí | Push từng entry | Bottom-up heapify |
| --- | --- | --- |
| Đầu vào | Dữ liệu được thêm dần | Mảng n phần tử sẵn có |
| Hướng sửa | **Sift-up** | **Sift-down** |
| Thứ tự | Theo thứ tự entry đến | Các nút trong từ cuối về gốc |
| Thời gian xấu nhất | **Θ(n log n)** | **Θ(n)** |
| Có tạo mảng đã sắp? | Không | Không |
| Có thể sửa mảng hiện có tại chỗ? | Có thể, tùy API/dung lượng | **Có** |

Sift-up và sift-down có cùng chiều cao giới hạn O(log n), nhưng cách **phân bố công việc** khác nhau nên tổng chi phí khác nhau.

## 4. Sift-down và tiền điều kiện quan trọng

**Sift-down** sửa cây con có gốc ở vị trí **i**, với giả định **cả hai cây con trực tiếp của i đã là min-heap**.

Trong min-heap, ta:

1. Tính **left = 2i + 1**, **right = 2i + 2**.
2. Nếu left ≥ n, i không có con; dừng.
3. Chọn **con có khóa nhỏ hơn** trong những con tồn tại.
4. Nếu **a[i] ≤ a[con nhỏ hơn]**, i đã thỏa thứ tự; dừng.
5. Nếu a[i] lớn hơn con nhỏ hơn, **hoán đổi** và tiếp tục sift-down tại chỉ số con vừa chọn.

~~~text
sift_down_min(a, start):
    i = start
    n = len(a)

    lặp:
        left  = 2*i + 1
        right = 2*i + 2

        nếu left >= n: dừng

        smaller = left
        nếu right < n và a[right] < a[left]:
            smaller = right

        nếu a[i] <= a[smaller]: dừng

        hoán đổi a[i], a[smaller]
        i = smaller
~~~

**Chọn con nhỏ hơn là bắt buộc** trong trường hợp cả hai con đều tồn tại. Nếu cha 9 có con 3 và 4, đổi với 4 sẽ khiến cha mới 4 vẫn lớn hơn con 3 còn lại. Đổi với 3 mới có thể khôi phục bất biến ở vị trí cha.

Ví dụ, với cây:

~~~text
          9
         / \
        3   4
       / \
      5   8

Mảng: [9, 3, 4, 5, 8]
~~~

Hai cây con gốc 3 và 4 đã là heap. Sift-down gốc 9:

~~~text
[9, 3, 4, 5, 8]
       |
       v
[3, 9, 4, 5, 8]   (đổi 9 với 3)
       |
       v
[3, 5, 4, 9, 8]   (đổi 9 với 5)
~~~

Nút 9 chuyển tới lá, toàn bộ cây thành min-heap.

**Tiền điều kiện không được bỏ qua:** nếu những cây con của i chưa hợp lệ, một lần sift-down từ i **không đủ bảo đảm** toàn bộ cây con gốc i thành heap. Đó chính là lý do phải xử lý **từ dưới lên**.

## 5. Vì sao bắt đầu từ n // 2 − 1?

Một nút i có **con trái** nếu:

\[
2i+1<n.
\]

Vì chỉ số nguyên, các nút có con là:

\[
0,\ 1,\ \ldots,\left\lfloor\frac n2\right\rfloor-1.
\]

Vậy nút trong cuối cùng có chỉ số:

\[
\boxed{\left\lfloor\frac n2\right\rfloor-1}.
\]

Mọi nút ở chỉ số **n // 2** đến **n − 1** là lá. Lá không cần sửa vì cây con một nút luôn hợp lệ.

Với n = 6:

~~~text
index:      0  1  2  3  4  5
loại nút:   I  I  I  L  L  L

I = nút trong; L = lá
n // 2 - 1 = 2

Các lượt gọi sift-down: 2 → 1 → 0
~~~

Trong Python, cách viết chính xác là:

~~~python
for i in range(len(a) // 2 - 1, -1, -1):
    sift_down_min(a, i)
~~~

**Lỗi dễ gặp:** dùng range(len(a) // 2 - 1, 0, -1) sẽ **không xử lý i = 0** vì điểm dừng của range không được bao gồm.

### Trường hợp rỗng, một và hai nút

| n | Mảng | Giá trị n // 2 − 1 | Các lượt sift-down |
| ---: | --- | ---: | --- |
| 0 | [] | -1 | Không có |
| 1 | [7] | -1 | Không có |
| 2 | [9, 1] | 0 | i = 0 |
| 3 | [5, 3, 4] | 0 | i = 0 |
| 6 | [9, 5, 7, 3, 8, 4] | 2 | 2, 1, 0 |

Vòng range trên tự xử lý đúng các trường hợp này, không cần đặc biệt hóa một nhánh cho n = 0 hoặc n = 1.

## 6. Mô phỏng đầy đủ: xây min-heap từ sáu phần tử

Cho:

~~~text
a = [9, 5, 7, 3, 8, 4]

             9
            / \
           5   7
          / \  /
         3  8 4
~~~

Nút trong cuối cùng là **i = 2**.

### Lượt 1: i = 2

Nút i = 2 chứa 7. Con trái i = 5 chứa 4; con phải i = 6 không tồn tại:

~~~text
7 > 4: đổi i = 2 với i = 5.

[9, 5, 7, 3, 8, 4]
          ↓        ↑
[9, 5, 4, 3, 8, 7]
~~~

Nút 7 ở lá; cây con gốc i = 2 đã hợp lệ.

### Lượt 2: i = 1

Nút i = 1 chứa 5. Hai con i = 3 và i = 4 có khóa 3, 8:

~~~text
Chọn con nhỏ hơn là 3.
5 > 3: đổi i = 1 với i = 3.

[9, 3, 4, 5, 8, 7]
~~~

Nút 5 xuống lá; cây con gốc i = 1 đã hợp lệ.

### Lượt 3: i = 0

Bây giờ hai cây con của gốc đã là heap. Gốc chứa 9, hai con chứa 3 và 4:

~~~text
9 > 3: đổi i = 0 với i = 1.
[3, 9, 4, 5, 8, 7]

Tiếp tục tại i = 1:
9 > 5: đổi i = 1 với i = 3.
[3, 5, 4, 9, 8, 7]
~~~

Nút 9 ở lá, kết thúc.

### Heap sau xây

~~~text
             3
            / \
           5   4
          / \  /
         9  8 7

a = [3, 5, 4, 9, 8, 7]
~~~

Các cạnh đều thỏa:

~~~text
3 <= 5; 3 <= 4
5 <= 9; 5 <= 8
4 <= 7
~~~

Bảng theo dõi:

| Chỉ số xử lý | Trước | Sau | Số lần đổi |
| ---: | --- | --- | ---: |
| 2 | [9, 5, 7, 3, 8, 4] | [9, 5, 4, 3, 8, 7] | 1 |
| 1 | [9, 5, 4, 3, 8, 7] | [9, 3, 4, 5, 8, 7] | 1 |
| 0 | [9, 3, 4, 5, 8, 7] | [3, 5, 4, 9, 8, 7] | 2 |

**Heap không phải mảng đã sắp:** kết quả [3, 5, 4, 9, 8, 7] là min-heap hợp lệ, dù 5 đứng trước 4.

## 7. Ví dụ khác: có lượt không đổi chỗ

Xét:

~~~text
a = [12, 3, 17, 8, 34, 25, 1, 5, 9]
n = 9
n // 2 - 1 = 3
~~~

Các lượt xử lý **3, 2, 1, 0**:

| Nút i | Điều xảy ra | Mảng sau lượt |
| ---: | --- | --- |
| Ban đầu | Chưa sửa | [12, 3, 17, 8, 34, 25, 1, 5, 9] |
| 3 | Đổi 8 với con 5 | [12, 3, 17, 5, 34, 25, 1, 8, 9] |
| 2 | Đổi 17 với con 1 | [12, 3, 1, 5, 34, 25, 17, 8, 9] |
| 1 | Cha 3 ≤ hai con 5, 34 | [12, 3, 1, 5, 34, 25, 17, 8, 9] |
| 0 | Đổi 12 với con 1 rồi dừng | [1, 3, 12, 5, 34, 25, 17, 8, 9] |

Sau khi 12 xuống i = 2, hai con của nó là 25 và 17. Vì **12 ≤ 17**, sift-down dừng tại đó, không cần đẩy tới lá.

Điều này nhấn mạnh rằng **O(log n)** là chi phí *xấu nhất* của một lượt sift-down, không phải số bước cố định mà mọi nút luôn phải làm.

## 8. Bất biến và chứng minh tính đúng đắn

**Giả định:** mảng đầu vào dài n chứa các khóa có quan hệ thứ tự nhất quán. Các nút được biểu diễn theo đúng công thức chỉ số của cây gần đầy đủ.

Bất biến của vòng xây dựng:

> **Trước khi xử lý nút i**, mọi nút có chỉ số lớn hơn i là **gốc của một cây con heap hợp lệ**. Vì các con của i có chỉ số lớn hơn i, **hai cây con của i đã là heap**.

### 8.1. Khởi tạo

Vòng bắt đầu ở **i = n // 2 − 1**. Các chỉ số lớn hơn i đều là **lá**; mỗi lá tự là heap. Vậy bất biến đúng trước lần xử lý đầu.

### 8.2. Duy trì

Giả sử bất biến đúng trước khi sửa i:

1. Các cây con trái/phải của i đã hợp lệ.
2. Sift-down tại i lựa chọn con nhỏ hơn và đưa entry không đúng thứ tự xuống một đường.
3. Vì các cây con đã là heap, quá trình sửa tạo ra **một heap hợp lệ ở toàn cây con gốc i**.
4. Các cây con khác đã xử lý vẫn đúng.

Sau đó giảm i đi một: tất cả cây con có gốc lớn hơn i mới vẫn đã là heap. Bất biến được duy trì.

### 8.3. Kết thúc

Sau khi xử lý **i = 0**, **toàn bộ cây con gốc 0** đã là heap, tức toàn bộ mảng là min-heap.

Quá trình:

- Không thêm hay xóa nút.
- Chỉ **hoán vị các entry** trong mảng, bảo toàn số lượng và giá trị.
- Không làm mất hình dạng cây gần đầy đủ.
- Đảm bảo tất cả cạnh cha–con thỏa quan hệ sau bước cuối.

### 8.4. Vì sao không làm ngược từ gốc xuống?

Nếu các cây con chưa là heap, sift-down gốc trước có thể tạo kết quả sai. Ví dụ với mảng ban đầu:

~~~text
[9, 5, 7, 3, 8, 4]

Chỉ sift-down gốc trước:
[5, 9, 7, 3, 8, 4]
[5, 3, 7, 9, 8, 4]
~~~

Kết quả **vẫn sai**: 5 > 3 và 7 > 4. Sift-down cần tiền điều kiện **các cây con đã là heap**; chỉ khi xử lý từ dưới lên mới bảo đảm điều kiện ấy tại mỗi lượt.

## 9. Tại sao tổng thời gian là Θ(n)?

Nếu chỉ lấy **O(log n)** của một lần sift-down rồi nhân với n nút, ta được **O(n log n)** — một cận trên thô, **không chặt**. Thực tế đa số nút **không thể đi xuống nhiều mức**.

### 9.1. Phân bố chiều cao nút

**Chiều cao của nút** là số cạnh trên đường dài nhất từ nút xuống một lá trong cây con ấy:

- Nút lá có chiều cao **0**, không cần sift-down.
- Nút có con là lá có chiều cao **1**, đi xuống tối đa một mức.
- Một số ít nút gần gốc có chiều cao lớn tới **⌊log₂ n⌋**.

Với cây nhị phân gần đầy đủ:

- Khoảng **n/2** nút là lá.
- Khoảng **n/4** nút có thể đi xuống khoảng một mức.
- Khoảng **n/8** nút có thể đi xuống khoảng hai mức.
- Những nút có cây con cao hơn ngày càng ít.

Tổng công việc vì thế nhỏ hơn rất nhiều so với việc giả sử **mọi nút** đều đi sâu log n mức.

### 9.2. Tổng cấp số nhân theo chiều cao

Số nút có chiều cao h được chặn ở mức **O(n/2^{h+1})**, và mỗi nút ấy đi xuống tối đa **h** mức. Do đó:

\[
T(n)
=O(n)+O\left(
n\sum_{h=0}^{\lfloor\log_2 n\rfloor}
\frac{h}{2^{h+1}}
\right).
\]

Tổng vô hạn hội tụ:

\[
\sum_{h=0}^{\infty}\frac{h}{2^{h+1}}=1.
\]

Suy ra:

\[
T(n)=O(n).
\]

### 9.3. Chứng minh trực quan bằng đếm các mức có thể đi xuống

Một nút có chiều cao h thực hiện tối đa h lượt đi xuống. Tổng chiều cao các nút được viết lại thành:

\[
\sum_{\text{nút }v} height(v)
=\sum_{k=1}^{\lfloor\log_2 n\rfloor}
\#\{v: height(v)\ge k\}.
\]

Trong cây gần đầy đủ, số nút có thể đi xuống **ít nhất k mức** không vượt quá:

\[
\left\lfloor\frac{n}{2^k}\right\rfloor.
\]

Vì thế:

\[
\sum_{\text{nút }v} height(v)
\le\sum_{k=1}^{\lfloor\log_2 n\rfloor}
\left\lfloor\frac{n}{2^k}\right\rfloor
<n\left(\frac12+\frac14+\frac18+\cdots\right)=n.
\]

Như vậy, **tổng số mức có thể đi xuống trong tất cả các lượt sift-down nhỏ hơn n**; cộng O(1) công việc cho khoảng n/2 nút trong, ta có **O(n)**.

### 9.4. Vì sao là Θ(n)?

Vòng xây dựng phải xét **n // 2 nút trong**, và việc xây heap từ đầu vào n entry cần xử lý dữ liệu với chi phí tối thiểu tuyến tính trong mô hình thông thường. Vì vậy, có cận dưới **Ω(n)**. Kết hợp cận trên **O(n)**:

\[
\boxed{T(n)=\Theta(n)}.
\]

Đây là kết luận cho **toàn bộ quá trình xây heap**: không có nghĩa từng lượt sift-down là O(1), cũng không có nghĩa mỗi entry chỉ được so sánh một lần.

## 10. Bộ nhớ: xây tại chỗ hay trên bản sao?

Cụm từ **xây heap trong Θ(n) thời gian** thường đi kèm nhận xét **O(1) bộ nhớ phụ**, nhưng nhận xét ấy chỉ đúng nếu được phép **sửa trực tiếp mảng đã có**.

### 10.1. Xây tại chỗ

~~~text
input a: [9, 5, 7, 3, 8, 4]
heapify_min_in_place(a)
sau đó a: [3, 5, 4, 9, 8, 7]
~~~

Số phần tử không đổi; thuật toán chỉ dùng một số biến cục bộ cho chỉ số, so sánh và hoán đổi.

- **Thời gian:** Θ(n).
- **Bộ nhớ phụ:** O(1) ngoài chính mảng chứa n entry.
- **Tác dụng phụ:** thứ tự các entry trong **a** thay đổi.

### 10.2. Xây trên bản sao

Nếu phải giữ nguyên danh sách đầu vào, có thể làm:

~~~python
working = list(original)
heapify_min_in_place(working)
~~~

Tạo bản sao list có chi phí **Θ(n) thời gian và O(n) bộ nhớ bổ sung**, sau đó heapify Θ(n). Toàn quá trình vẫn **Θ(n) thời gian**, nhưng không được báo O(1) bộ nhớ phụ đối với **toàn lời gọi**.

### 10.3. Giả định khi phân tích

Phép tính chỉ số và so sánh khóa được giả định mất O(1). Nếu so sánh khóa là một thao tác tốn k thời gian (chẳng hạn chuỗi dài hoặc đối tượng có logic phức tạp), tổng chi phí phải tính đến k. Việc ghi nhật ký/sao chép mảng sau mỗi lượt cũng tạo thêm chi phí, không thuộc thuật toán heapify cơ bản.

Khi entry chứa cả **priority** và **payload**, nên định nghĩa rõ khóa so sánh. Không nên bất ngờ so sánh hai payload không hỗ trợ thứ tự khi priority bằng nhau.

## 11. Cài đặt Python tự chứa: min-heapify tại chỗ

Mã sau dùng Python 3.10 trở lên, triển khai trực tiếp công thức chỉ số 0-based. **Không cần thư viện heapq** để thực hiện thao tác xây heap.

~~~python
from __future__ import annotations


def sift_down_min(a: list[int], start: int) -> None:
    """Sửa cây con gốc start khi hai cây con đã là min-heap."""
    n = len(a)
    i = start

    while True:
        left = 2 * i + 1
        right = 2 * i + 2

        if left >= n:
            return  # Không còn con trái: đã ở lá.

        smaller = left
        if right < n and a[right] < a[left]:
            smaller = right

        if a[i] <= a[smaller]:
            return  # Cha <= con nhỏ hơn, cũng <= con còn lại.

        a[i], a[smaller] = a[smaller], a[i]
        i = smaller


def heapify_min_in_place(a: list[int]) -> None:
    """Xây min-heap ngay trong a: Theta(n), O(1) bộ nhớ phụ."""
    for i in range(len(a) // 2 - 1, -1, -1):
        sift_down_min(a, i)


def is_min_heap(a: list[int]) -> bool:
    """Kiểm tra mọi quan hệ cha <= con."""
    for i in range(1, len(a)):
        p = (i - 1) // 2
        if a[p] > a[i]:
            return False
    return True


numbers = [9, 5, 7, 3, 8, 4]
original_id = id(numbers)
heapify_min_in_place(numbers)

assert id(numbers) == original_id  # Không thay đối tượng list.
assert numbers == [3, 5, 4, 9, 8, 7]
assert is_min_heap(numbers)
assert sorted(numbers) == [3, 4, 5, 7, 8, 9]

# Mô phỏng chín nút.
values = [12, 3, 17, 8, 34, 25, 1, 5, 9]
heapify_min_in_place(values)
assert values == [1, 3, 12, 5, 34, 25, 17, 8, 9]
assert is_min_heap(values)

# Mảng rỗng và một nút.
empty = []
single = [42]
heapify_min_in_place(empty)
heapify_min_in_place(single)
assert empty == []
assert single == [42]
assert is_min_heap(empty) and is_min_heap(single)

# Chỉ có hai nút.
pair = [9, 1]
heapify_min_in_place(pair)
assert pair == [1, 9]

# Cho phép khóa bằng nhau.
duplicates = [4, 4, 4, 4, 4]
heapify_min_in_place(duplicates)
assert duplicates == [4, 4, 4, 4, 4]
assert is_min_heap(duplicates)

# Khóa âm cũng hoạt động bình thường.
negative = [-1, -7, 0, 3, 5]
heapify_min_in_place(negative)
assert negative == [-7, -1, 0, 3, 5]
assert is_min_heap(negative)
~~~

### Đọc mã theo bất biến

Trong heapify_min_in_place, vòng lặp bắt đầu tại nút trong cuối cùng và đi về gốc. Vì các cây con tại vị trí có chỉ số lớn hơn đã hợp lệ, mỗi lần gọi sift_down_min đúng tiền điều kiện.

Trong sift_down_min:

- Nếu **left ≥ n**, không có con, nên dừng.
- Nếu cả hai con tồn tại, chọn khóa nhỏ hơn.
- Nếu **a[i] ≤ a[smaller]**, i không lớn hơn bất kỳ con nào, nên dừng.
- Nếu không, đổi chỗ và tiếp tục sửa cây con ở vị trí vừa chuyển xuống.

Hàm **is_min_heap** là phép kiểm tra Θ(n) thời gian, O(1) bộ nhớ phụ. Nó phù hợp khi học hoặc viết unit test, nhưng **không phải chi phí bắt buộc** trong mỗi lần xây hoặc mỗi lần push/pop.

### Nếu dữ liệu là đối tượng thì sao?

Thuật toán vẫn đúng nếu thay toán tử so sánh số nguyên bằng so sánh một **khóa ưu tiên** có quan hệ thứ tự nhất quán. Khi hoán đổi, phải hoán đổi **toàn bộ entry**, không chỉ riêng giá trị priority. Nếu không, priority sẽ không còn gắn với đúng payload.

## 12. Từ heap đã xây đến một priority queue

Sau khi heapify, mảng có thể được dùng để triển khai **min-priority queue**:

- **peek:** đọc gốc a[0], thời gian Θ(1).
- **push:** append entry rồi sift-up, thời gian O(log n) theo mô hình heap.
- **pop_min:** lấy gốc, đưa entry cuối lên thay và sift-down, thời gian O(log n).

Ví dụ lớp sau sử dụng ba hàm **sift_down_min**, **heapify_min_in_place** và **is_min_heap** đã định nghĩa ở mục 11.

~~~python
class MinPriorityQueue:
    def __init__(self, values=()):
        self._data = list(values)       # Bản sao, giữ nguyên đầu vào.
        heapify_min_in_place(self._data)

    def __len__(self):
        return len(self._data)

    def peek(self):
        if not self._data:
            raise IndexError("Hàng đợi rỗng")
        return self._data[0]

    def push(self, value):
        self._data.append(value)
        i = len(self._data) - 1

        while i > 0:
            p = (i - 1) // 2
            if self._data[p] <= self._data[i]:
                break
            self._data[p], self._data[i] = (
                self._data[i], self._data[p]
            )
            i = p

    def pop_min(self):
        if not self._data:
            raise IndexError("Hàng đợi rỗng")

        result = self._data[0]
        last = self._data.pop()

        if self._data:
            self._data[0] = last
            sift_down_min(self._data, 0)

        return result

    def heap_array(self):
        return list(self._data)


original = [9, 5, 7, 3, 8, 4]
queue = MinPriorityQueue(original)

assert original == [9, 5, 7, 3, 8, 4]   # Constructor đã copy.
assert is_min_heap(queue.heap_array())
assert queue.peek() == 3 and len(queue) == 6

queue.push(2)
assert queue.peek() == 2 and len(queue) == 7

result = []
while len(queue) > 0:
    result.append(queue.pop_min())

assert result == [2, 3, 4, 5, 7, 8, 9]

try:
    queue.pop_min()
except IndexError:
    pass
else:
    raise AssertionError("Pop hàng đợi rỗng phải báo lỗi")
~~~

**Lưu ý:** Khối mã này phụ thuộc vào các hàm trong mục 11; khi chạy trong một tệp Python, cần đặt mã mục 11 **trước** lớp ở mục 12.

Constructor sao chép n entry rồi heapify một lần: tổng **Θ(n) thời gian và O(n) bộ nhớ** dành cho bản sao. Nếu ứng dụng cho phép thay đổi chính mảng đầu vào thì có thể tránh bản sao và gọi trực tiếp heapify_min_in_place.

## 13. Xây max-heap từ dưới lên

Max-heap giữ bất biến **cha ≥ con**. Hình dạng cây, công thức cha/con và trình tự duyệt từ nút trong cuối về gốc **không đổi**; chỉ hướng so sánh của sift-down thay đổi:

1. Chọn **con lớn hơn** trong các con tồn tại.
2. Nếu cha đã **≥** con lớn hơn, dừng.
3. Nếu cha nhỏ hơn, hoán đổi và tiếp tục xuống.

~~~python
def sift_down_max(a: list[int], start: int) -> None:
    n = len(a)
    i = start

    while True:
        left = 2 * i + 1
        right = 2 * i + 2
        if left >= n:
            return

        larger = left
        if right < n and a[right] > a[left]:
            larger = right

        if a[i] >= a[larger]:
            return

        a[i], a[larger] = a[larger], a[i]
        i = larger


def heapify_max_in_place(a: list[int]) -> None:
    for i in range(len(a) // 2 - 1, -1, -1):
        sift_down_max(a, i)


def is_max_heap(a: list[int]) -> bool:
    return all(
        a[(i - 1) // 2] >= a[i]
        for i in range(1, len(a))
    )


numbers = [2, 7, 4, 9, 1, 6]
heapify_max_in_place(numbers)

assert numbers == [9, 7, 6, 2, 1, 4]
assert is_max_heap(numbers)
assert numbers[0] == 9

empty = []
heapify_max_in_place(empty)
assert empty == [] and is_max_heap(empty)
~~~

Ở đây max-heapify vẫn dùng **Θ(n) thời gian và O(1) bộ nhớ phụ** khi xử lý tại chỗ. Các khóa bằng nhau được phép vì quan hệ sử dụng **≥**, không phải >.

## 14. So sánh với thư viện heapq của Python

Python có thư viện chuẩn **heapq** để thao tác với min-heap trên list. Hàm **heapq.heapify(a)** thay đổi trực tiếp list và xây min-heap trong **Θ(n)** thời gian.

~~~python
import heapq

a = [9, 5, 7, 3, 8, 4]
heapq.heapify(a)

assert len(a) == 6
assert a[0] == 3
assert all(a[(i - 1) // 2] <= a[i] for i in range(1, len(a)))

# Pop toàn bộ mới tạo dãy được sắp theo ưu tiên.
result = [heapq.heappop(a) for _ in range(len(a))]
assert result == [3, 4, 5, 7, 8, 9]
assert a == []
~~~

**Không ép mảng nội bộ phải đúng một hoán vị cụ thể**: cùng một tập giá trị có thể tạo ra nhiều min-heap hợp lệ. Một cài đặt có thể dùng hoán đổi, cài đặt khác có thể dời entry để giảm phép gán; với khóa bằng nhau, quy tắc chọn con cũng có thể khác. Hãy kiểm tra **bất biến cha ≤ con** hoặc kết quả pop, không dựa vào một ảnh chụp nội bộ duy nhất.

### Khóa ưu tiên, dữ liệu và tính ổn định

Trong ứng dụng thực tế, mỗi entry có thể là:

~~~text
(priority, sequence, payload)
~~~

Trong đó sequence là số thứ tự duy nhất để phân xử trường hợp priority bằng nhau:

~~~python
import heapq

tasks = [
    (2, 0, "Thông báo A"),
    (1, 1, "Khắc phục dịch vụ"),
    (2, 2, "Thông báo B"),
]

heapq.heapify(tasks)

assert heapq.heappop(tasks) == (1, 1, "Khắc phục dịch vụ")
assert heapq.heappop(tasks) == (2, 0, "Thông báo A")
assert heapq.heappop(tasks) == (2, 2, "Thông báo B")
~~~

Sequence duy nhất giúp duy trì thứ tự **FIFO trong các entry cùng priority** và tránh yêu cầu so sánh payload không hỗ trợ thứ tự. Nếu chỉ dùng (priority, payload), hai payload không so sánh được có thể gây **TypeError** khi priority bằng nhau.

Heapify không tự cập nhật heap khi trường priority của một đối tượng bị sửa. Thao tác đổi khóa phải khôi phục bất biến bằng phương án phù hợp hoặc thay entry cũ bằng một entry mới theo chính sách của ứng dụng.

## 15. Heapify khác với sắp xếp

Xét:

~~~text
Đầu vào:
[9, 5, 7, 3, 8, 4]

Sau min-heapify minh họa:
[3, 5, 4, 9, 8, 7]

Sau sort tăng dần:
[3, 4, 5, 7, 8, 9]
~~~

Min-heap chỉ bảo đảm **khóa ở gốc là nhỏ nhất** và mọi quan hệ cha–con đúng. Thứ tự giữa các nhánh không được sắp toàn cục.

Nếu muốn lấy toàn bộ n phần tử theo thứ tự tăng dần:

1. Xây min-heap: **Θ(n)**.
2. Gọi pop min **n lần**, mỗi lần O(log n).
3. Tổng chi phí **O(n log n)**; trong trường hợp xấu nhất của cách làm này, chi phí là Θ(n log n).

Nếu lưu kết quả vào một mảng khác, cần thêm O(n) bộ nhớ cho mảng kết quả. Một **heapsort tại chỗ** có thể dùng max-heap và vùng cuối mảng đã sắp, đạt O(1) bộ nhớ phụ ngoài mảng, nhưng đó là thuật toán khác với việc chỉ heapify.

**Heapify Θ(n) không có nghĩa là đã sắp xếp n phần tử bất kỳ trong Θ(n) bằng so sánh.**

## 16. Ứng dụng và lựa chọn chiến lược

### 16.1. Nạp công việc theo lô

Nếu có sẵn hàng nghìn công việc, một hệ thống lập lịch có thể dựng min-heap theo khóa ưu tiên:

~~~text
Mảng công việc có sẵn
       |
       v
Bottom-up heapify: Θ(n)
       |
       v
Min-priority queue:
    peek O(1)
    push O(log n)
    pop  O(log n)
~~~

Đây là trường hợp điển hình của chi phí khởi tạo tốt hơn so với n lần push trong trường hợp xấu nhất.

### 16.2. Mô phỏng sự kiện

Nếu một bộ mô phỏng đã có n sự kiện với **timestamp**, heapify có thể dựng hàng đợi sự kiện ban đầu trong Θ(n). Sau đó hệ thống lấy sự kiện sớm nhất bằng pop và thêm sự kiện mới bằng push.

Khi nhiều sự kiện có cùng timestamp và yêu cầu thứ tự quyết định trước, nên thêm **sequence** vào khóa trước khi heapify.

### 16.3. Nối hai lô dữ liệu

Nếu có hai **mảng entry** với tổng n + m phần tử, có thể nối chúng thành một mảng và heapify một lượt, tốn **Θ(n + m)** thời gian cho pha xây trên mảng đã nối. Việc tạo mảng gộp có thể cần O(n + m) bộ nhớ nếu phải sao chép.

**Nối trực tiếp hai mảng vốn riêng rẽ là heap không bảo đảm mảng lớn cũng là heap.** Các quan hệ cha–con mới có thể vi phạm, nên cần sửa lại hoặc chọn thuật toán gộp thích hợp.

### 16.4. Thuật toán đồ thị

Dijkstra và Prim thường dùng priority queue, có thể triển khai bằng heap. Heapify giải quyết **pha khởi tạo** với nhiều entry; nhưng việc cập nhật khoảng cách hoặc khóa theo ID cần cơ chế khác (handle/index hoặc thêm entry mới và bỏ qua entry cũ). Không nên coi heapify là lời giải cho toàn bộ nghiệp vụ cập nhật khóa.

**Khi không nên heapify toàn bộ:** nếu chỉ có một vài entry mới đến so với heap đang sử dụng, push riêng lẻ có thể phù hợp hơn. Việc chọn giữa sửa tăng dần và xây lại phụ thuộc số lượng entry mới cùng tần suất các thao tác khác.

## 17. Lỗi thường gặp

| Sai sót | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Gọi n lần sift-up và gọi đó là bottom-up heapify | Nhầm thuật toán và chi phí | Bottom-up dùng **sift-down** từ nút trong cuối về gốc |
| Bắt đầu tại i = n − 1 | Sửa cả lá không cần thiết | Bắt đầu ở **n // 2 − 1** |
| Xử lý i tăng từ gốc với một sift-down mỗi nút | Hai cây con có thể chưa là heap | Xử lý i **giảm dần** |
| Viết range(n // 2 − 1, 0, −1) | Bỏ qua gốc 0 | Dùng range(n // 2 − 1, -1, -1) |
| Dùng chỉ số con 1-based cho list 0-based | Đọc sai nút, tạo heap sai | Con trái **2i + 1**, con phải **2i + 2** |
| Không kiểm tra con phải tồn tại | IndexError khi một nút chỉ có con trái | Kiểm tra right < n |
| Chọn con lớn hơn trong min-sift-down | Cha mới có thể lớn hơn con còn lại | Chọn **con nhỏ hơn** |
| Chọn con nhỏ hơn trong max-sift-down | Cha mới có thể nhỏ hơn con còn lại | Chọn **con lớn hơn** |
| Quên i = smaller/larger sau hoán đổi | Không tiếp tục sửa vị trí đúng | Cập nhật i theo vị trí mới của entry |
| Cho rằng heapify trả mảng tăng dần | Hiểu sai kết quả | Kiểm tra **cha–con**, không phải sort |
| Nhân mọi nút với O(log n) rồi kết luận Θ(n log n) | Bỏ qua cấu trúc gần đầy đủ | Cộng theo **chiều cao của từng nút** |
| Heapify trên bản sao nhưng báo O(1) bộ nhớ tổng | Bỏ qua bước copy | Phân biệt tại chỗ và trên bản sao |
| Chỉ kiểm tra gốc nhỏ nhất | Bỏ qua cạnh sai sâu trong heap | Kiểm tra mọi i > 0 với cha của nó |
| Thay priority của entry trực tiếp | Phá bất biến mà không tự sửa | Dùng thao tác cập nhật/reheapify |
| So sánh payload của các entry khóa trùng | Sai thứ tự hoặc TypeError | So sánh key và dùng sequence khi cần |
| Ép kết quả heapq.heapify phải giống hệt mảng ví dụ | Phụ thuộc chi tiết cài đặt | Kiểm tra bất biến và kết quả pop |
| Gọi validate Θ(n) sau mọi push nhưng báo tổng O(log n) | Đánh giá thiếu thời gian | Cộng chi phí kiểm tra nếu thật sự chạy |

Để tự gỡ lỗi, thử mảng **0, 1, 2, 5, 6, 7, 9** phần tử. Đánh dấu nút trong cuối, theo dõi i giảm dần; sau mỗi sift-down, kiểm tra cây con i và cuối cùng kiểm tra mọi cạnh.

## 18. Bài tập tự luyện có đáp án

**Bài 1 — Nút trong cuối.** Với n = 14, heapify bắt đầu ở chỉ số nào?

*Đáp án:* **14 // 2 − 1 = 6**; các chỉ số 7 tới 13 là lá.

**Bài 2 — Thứ tự xử lý.** Với n = 8, thứ tự i để sift-down là gì?

*Đáp án:* **3, 2, 1, 0**.

**Bài 3 — Heap rỗng.** Bottom-up heapify của [] gọi sift-down bao nhiêu lần?

*Đáp án:* **0 lần**; vẫn trả cấu trúc rỗng hợp lệ.

**Bài 4 — Một nút.** Heapify [42] tạo ra gì?

*Đáp án:* **[42]**; gốc là lá, không cần đổi chỗ.

**Bài 5 — Hai nút.** Min-heapify [9, 1] xử lý đâu và cho mảng gì?

*Đáp án:* Chỉ xử lý **i = 0**, đổi 9 với 1, thành **[1, 9]**.

**Bài 6 — Sáu nút.** Xây min-heap từ [9, 5, 7, 3, 8, 4] bằng thuật toán chọn con nhỏ hơn.

*Đáp án:* Xử lý **i = 2, 1, 0** và được **[3, 5, 4, 9, 8, 7]**.

**Bài 7 — Chỉ một con.** Với n = 6, nút ở i = 2 có mấy con?

*Đáp án:* Chỉ có con trái ở **i = 5**; con phải ở i = 6 không tồn tại.

**Bài 8 — Chọn con.** Nút 9 có hai con 3 và 4. Trong min-sift-down cần chọn con nào?

*Đáp án:* **3**, vì con nhỏ hơn phải lên để cha mới không lớn hơn con còn lại.

**Bài 9 — Bất biến.** Khi chuẩn bị xử lý i trong vòng bottom-up, biết điều gì về các cây con của i?

*Đáp án:* Các cây con đã **là heap hợp lệ**, vì chúng có gốc ở chỉ số lớn hơn i và đã được sửa hoặc là lá.

**Bài 10 — Không được đi từ gốc trước?** Chỉ gọi sift-down ở gốc của [9, 5, 7, 3, 8, 4] có đủ không?

*Đáp án:* Không. Có thể nhận [5, 3, 7, 9, 8, 4], vẫn sai vì 5 > 3 và 7 > 4.

**Bài 11 — Mỗi nút đi bao xa?** Vì sao đa số nút không cần O(log n) lượt đổi?

*Đáp án:* Đa số ở gần lá, có chiều cao 0 hoặc 1. Chỉ ít nút gần gốc có cây con sâu.

**Bài 12 — Tổng vô hạn.** Giá trị của \(\sum_{h=0}^{\infty}h/2^{h+1}\) bằng bao nhiêu?

*Đáp án:* **1**. Tổng hữu hạn này khiến chi phí cộng theo chiều cao bị chặn bởi O(n).

**Bài 13 — Độ phức tạp chính xác.** Heapify từ dưới lên có chi phí O(n) hay Θ(n)?

*Đáp án:* **Θ(n)** trong mô hình chuẩn, vì có cận trên O(n) và cận dưới Ω(n).

**Bài 14 — So sánh push.** Cách nào có cận thời gian xây xấu nhất tốt hơn khi n entry đã có sẵn?

*Đáp án:* Bottom-up heapify **Θ(n)**; n lần push có thời gian xấu nhất **Θ(n log n)**.

**Bài 15 — Heap khác sort.** [3, 5, 4, 9, 8, 7] đã sắp tăng dần chưa?

*Đáp án:* **Chưa**, vì 5 > 4; nhưng đó là min-heap hợp lệ.

**Bài 16 — Pop sau xây.** Heapify n entry, sau đó pop hết n entry thì tổng thời gian cỡ nào?

*Đáp án:* **O(n log n)**; mỗi pop có thể O(log n).

**Bài 17 — Bộ nhớ.** Khi nào heapify dùng O(1) bộ nhớ phụ, khi nào O(n)?

*Đáp án:* **O(1)** nếu sửa chính mảng đầu vào; **O(n)** thêm nếu tạo list bản sao để giữ nguyên đầu vào.

**Bài 18 — Max-heap.** Thứ tự các nút i có đổi khi chuyển từ min-heap sang max-heap không?

*Đáp án:* **Không**, vẫn từ nút trong cuối về gốc; chỉ đổi thành chọn con **lớn hơn**.

**Bài 19 — Khóa trùng.** Heapify có tự bảo đảm FIFO với nhiều entry cùng priority không?

*Đáp án:* **Không**; phải gắn sequence làm khóa phụ nếu cần tính ổn định.

**Bài 20 — Gốc nhỏ nhất có đủ?** Nếu a[0] là khóa nhỏ nhất, a chắc chắn là min-heap chưa?

*Đáp án:* **Chưa**. Mọi cặp cha–con đều phải thỏa cha ≤ con.

**Bài 21 — Cận tổng chiều cao.** Vì sao \(\sum_{k\ge1}\lfloor n/2^k\rfloor<n\) hữu ích?

*Đáp án:* Đó là cận trên cho tổng số mức có thể đi xuống của các nút, nên tổng công việc sift-down là **O(n)**.

**Bài 22 — Ghép theo lô.** Có hai mảng n và m entry. Nếu tạo mảng gộp rồi heapify, chi phí xây là bao nhiêu?

*Đáp án:* **Θ(n + m)** thời gian cho heapify trên mảng gộp. Nếu cần tạo mảng gộp mới, có thêm O(n + m) bộ nhớ.

**Bài 23 — Kiểm tra heapq.** Có nên đòi heapq.heapify luôn tạo đúng một mảng cụ thể của giáo trình không?

*Đáp án:* **Không**. Nhiều hoán vị khác nhau có thể cùng thỏa bất biến heap; hãy kiểm tra cha–con hoặc thứ tự pop.

**Bài 24 — Lỗi range.** Đoạn sau bỏ sót điều gì?

~~~python
for i in range(len(a) // 2 - 1, 0, -1):
    sift_down_min(a, i)
~~~

*Đáp án:* Bỏ qua **gốc i = 0**, vì range không bao gồm 0. Phải dùng **range(len(a) // 2 - 1, -1, -1)**.

**Ghi nhớ:** **Bottom-up heapify** dùng mảng đã có để giữ hình dạng cây gần đầy đủ, rồi gọi **sift-down** từ **nút trong cuối n // 2 − 1** về **gốc 0**. Khi xử lý i, các cây con của i đã là heap; sau khi sửa i, cả cây con ấy trở thành heap. Dù một sift-down có thể O(log n), đa số nút ở gần lá nên tổng chi phí chỉ là **Θ(n)**. Cách làm dùng **O(1) bộ nhớ phụ** nếu được sửa mảng tại chỗ; việc tạo bản sao tốn thêm O(n). Heapify tạo **heap**, không sắp xếp toàn bộ mảng.
