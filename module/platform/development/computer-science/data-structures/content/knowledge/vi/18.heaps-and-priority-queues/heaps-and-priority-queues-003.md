# Heap nhị phân bằng mảng và quan hệ cha–con theo chỉ số

**Heap nhị phân** (*binary heap*) là một cấu trúc dữ liệu thường dùng để cài đặt **hàng đợi ưu tiên** (*priority queue*). Điểm nổi bật của heap nhị phân không chỉ là quan hệ ưu tiên giữa nút cha và các nút con, mà còn là khả năng lưu **toàn bộ cây trong một mảng liên tiếp**, không cần mỗi nút có hai con trỏ left và right.

Trong một heap có n phần tử, chỉ số của nút xác định trực tiếp vị trí **cha**, **con trái** và **con phải**. Vì cây có hình dạng **nhị phân gần đầy đủ**, các phép tính đó chính xác mà không cần tìm kiếm. Khi kết hợp hình dạng cây với bất biến thứ tự heap, ta có thể xem phần tử ưu tiên nhất ở gốc trong O(1) và duy trì heap khi thêm hoặc lấy gốc qua nhiều nhất O(log n) mức.

Bài thuộc chương **Heap và hàng đợi ưu tiên** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Mô-đun xây dựng nền tảng về cấu trúc dữ liệu, bất biến, thao tác và độ phức tạp thời gian/bộ nhớ để lựa chọn cấu trúc phù hợp. Trọng tâm ở đây là **biểu diễn heap nhị phân bằng mảng và suy luận chính xác các quan hệ cha–con theo chỉ số**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích hai đặc trưng của binary heap: **cây nhị phân gần đầy đủ** và **quan hệ ưu tiên giữa cha với con**.
- Vẽ cây từ một mảng heap và đọc lại mảng từ cây theo thứ tự từng mức.
- Tính chỉ số cha, con trái và con phải trong **mảng bắt đầu từ 0**.
- Phân biệt công thức chỉ số **0-based** với **1-based**.
- Kiểm tra một chỉ số con có nằm trong phạm vi từ 0 đến n − 1 hay không.
- Xác định vị trí **nút lá**, **nút trong**, số mức và chiều cao heap.
- Phân biệt bất biến **min-heap** với **max-heap**, đồng thời nhận ra heap **không phải mảng sắp xếp** và **không phải cây tìm kiếm nhị phân**.
- Mô phỏng sift-up, sift-down, heapify dựa trên phép tính chỉ số.
- Cài đặt một binary min-heap bằng Python với thao tác push, peek, pop và kiểm tra bất biến.
- Phân tích độ phức tạp thời gian/bộ nhớ và xử lý các trường hợp biên khi n bằng 0, 1, 2 hoặc số lẻ/chẵn.

## 2. Hai bất biến tạo nên binary heap

Một **binary heap** thường cần đồng thời hai điều kiện độc lập:

1. **Bất biến hình dạng (shape property):** cây nhị phân là **cây gần đầy đủ** (*complete binary tree*): mọi mức trừ mức cuối đều lấp đầy, các nút ở mức cuối được điền **liên tiếp từ trái sang phải**, không có khoảng trống.
2. **Bất biến thứ tự heap (heap-order property):** với **min-heap**, khóa của mỗi cha không lớn hơn khóa các con của nó; với **max-heap**, khóa của mỗi cha không nhỏ hơn khóa các con.

**Chỉ một điều kiện không đủ**. Một cây tuân theo quan hệ cha ≤ con nhưng có nhiều lỗ ở mức trên không phải binary heap theo định nghĩa chuẩn. Ngược lại, một cây gần đầy đủ mà cha lớn hơn một con cũng không phải min-heap.

### 2.1. Ví dụ min-heap hợp lệ

~~~text
              1                 mức 0
            /   \
           3     2              mức 1
          / \   /
         8   4 6                mức 2
~~~

Quan hệ ưu tiên:

~~~text
1 <= 3, 1 <= 2
3 <= 8, 3 <= 4
2 <= 6
~~~

Mức cuối có các nút 8, 4, 6 lấp từ trái sang phải; chỗ con phải của 2 còn trống **chỉ sau những vị trí đã được lấp**, nên cây gần đầy đủ.

### 2.2. Ví dụ hình dạng sai

~~~text
       1
      / \
     3   2
      \
       4
~~~

Nút 3 thiếu con trái nhưng lại có con phải 4. Dù 1 ≤ 3, 1 ≤ 2 và 3 ≤ 4, hình dạng không phải cây gần đầy đủ. Không thể dùng công thức mảng heap chuẩn để biểu diễn hình dạng này mà không xuất hiện chỗ trống.

### 2.3. Ví dụ thứ tự sai

~~~text
       1
      / \
     7   2
    /
   3
~~~

Hình dạng gần đầy đủ nhưng **7 > 3**, nên không thỏa min-heap. Việc phần tử 1 ở gốc là nhỏ nhất **chưa đủ**; phải kiểm tra **tất cả** các cặp cha–con.

## 3. Từ cây nhị phân gần đầy đủ sang mảng

Vì các nút được lấp lần lượt theo mức, từ trái sang phải, ta gán chỉ số mảng như sau:

~~~text
Cây có 6 nút:

             (0) 1
             /   \
        (1) 3     (2) 2
           / \      /
      (3) 8 (4) 4 (5) 6

Mảng, chỉ số từ 0:

Chỉ số:  0   1   2   3   4   5
Giá trị: 1   3   2   8   4   6

a = [1, 3, 2, 8, 4, 6]
~~~

Đây là cách đánh số **theo thứ tự mức** (*level-order* hoặc breadth-first order). Mỗi nút có **một ô mảng**, và các ô được dùng liên tiếp từ chỉ số 0 đến n − 1.

Một heap có **n phần tử** lưu trong mảng:

- Gốc luôn ở **a[0]**, nếu n > 0.
- Không có ô “nút khuyết” nằm xen giữa các nút hiện có.
- Một nút không cần lưu trường left, right hoặc parent.
- Quan hệ cha/con được tính bằng **phép toán trên chỉ số**.
- Phần tử thêm tiếp theo sẽ được đặt ở **cuối mảng a[n]** trước khi sửa thứ tự heap.

### Tại sao dùng mảng tiết kiệm hơn con trỏ?

Trong cây nhị phân liên kết truyền thống, mỗi nút thường phải lưu tham chiếu đến con trái, con phải, đôi khi cả cha. Binary heap bằng mảng không cần các trường này: biết chỉ số i là có thể suy ra các chỉ số liên quan.

Mảng vẫn cần O(n) không gian để chứa n entry và có thể có dung lượng cấp phát dự phòng khi dùng **mảng động**. Nhưng việc bỏ những con trỏ trên mỗi nút thường giảm overhead và tận dụng tính cục bộ bộ nhớ khi duyệt.

**Chú ý:** Mảng ở đây có thể chứa **entry (priority, payload)** chứ không bắt buộc chỉ chứa số nguyên. Công thức cha/con dựa trên vị trí mảng, độc lập với kiểu dữ liệu của entry; còn bất biến thứ tự dựa trên **khóa ưu tiên**.

## 4. Công thức cha–con với chỉ số bắt đầu từ 0

Gọi **i** là chỉ số của một nút, **n = len(a)** là số nút hiện có.

| Quan hệ | Công thức 0-based | Điều kiện |
| --- | --- | --- |
| Gốc | **0** | Chỉ có nếu n > 0 |
| Cha của i | **(i − 1) // 2** | 1 ≤ i < n |
| Con trái của i | **2i + 1** | Chỉ tồn tại khi 2i + 1 < n |
| Con phải của i | **2i + 2** | Chỉ tồn tại khi 2i + 2 < n |
| Hai con của cùng cha | **2p + 1** và **2p + 2** | Từng chỉ số phải nhỏ hơn n |

Dấu **//** là phép chia nguyên lấy phần nguyên xuống trong Python. Ở công thức cha, chỉ sử dụng với **i ≥ 1**.

### 4.1. Ví dụ tính từ chỉ số

Với n = 6 và a = [1, 3, 2, 8, 4, 6]:

- Nút ở **i = 1** chứa 3. Cha: (1 − 1) // 2 = **0**, chứa 1. Con trái: 2×1 + 1 = **3**, chứa 8. Con phải: 2×1 + 2 = **4**, chứa 4.
- Nút ở **i = 2** chứa 2. Cha: (2 − 1) // 2 = **0**, chứa 1. Con trái: 2×2 + 1 = **5**, chứa 6. Con phải: 2×2 + 2 = **6**, **không tồn tại** vì 6 không nhỏ hơn n = 6.
- Nút ở **i = 4** chứa 4. Cha: (4 − 1) // 2 = **1**, chứa 3. Con trái: 9 và con phải: 10, đều ngoài mảng, nên là **nút lá**.

### 4.2. Lưu ý về ranh giới

Hàm tính chỉ số **không tự chứng minh con tồn tại**. Ví dụ, với i = 2 và n = 6, công thức con phải trả về 6, nhưng chỉ số hợp lệ lớn nhất là 5. Trước khi truy cập **a[child_index]**, phải xác nhận:

~~~python
child_index < len(a)
~~~

Một lỗi phổ biến là dùng **child_index <= len(a)**. Điều kiện này chấp nhận chỉ số bằng n dù Python chỉ có các chỉ số **0, 1, ..., n − 1**, dẫn đến IndexError.

### 4.3. Gốc không có cha

Với i = 0, biểu thức **(i − 1) // 2** trong Python cho ra -1, nhưng đó **không phải chỉ số cha của gốc**. Đặc biệt, Python cho phép **a[-1]** truy cập phần tử cuối mảng, khiến một lỗi tính cha dễ bị che giấu.

Vì thế, thuật toán **sift-up** cần dừng khi **i == 0**, không tiếp tục lấy cha của gốc.

## 5. Vì sao công thức chỉ số đúng?

Sự đúng đắn đến từ cách đánh số **theo từng mức, từ trái sang phải** của cây gần đầy đủ.

Ở mức 0 có gốc chỉ số 0. Mức 1 tiếp theo có các chỉ số 1 và 2; chúng là hai con của nút 0:

~~~text
left(0)  = 2×0 + 1 = 1
right(0) = 2×0 + 2 = 2
~~~

Mức 2 bắt đầu tại 3. Nút 1 có hai con 3 và 4; nút 2 có hai con 5 và 6:

~~~text
left(1)  = 3
right(1) = 4

left(2)  = 5
right(2) = 6
~~~

Tổng quát, các vị trí con của nút p là **hai vị trí liên tiếp** trong mức tiếp theo, nên lần lượt có chỉ số **2p + 1** và **2p + 2**.

Đảo chiều:

- Nếu i là **con trái**, i = 2p + 1; suy ra p = (i − 1)/2.
- Nếu i là **con phải**, i = 2p + 2; suy ra p = (i − 2)/2.

Hai trường hợp được gộp bởi **p = (i − 1) // 2** với i ≥ 1.

### Ví dụ bảng vị trí đầy đủ

| i | Giá trị a[i] | Cha i | Con trái i | Con phải i |
| ---: | ---: | --- | --- | --- |
| 0 | 1 | Không có | 1 (giá trị 3) | 2 (giá trị 2) |
| 1 | 3 | 0 (giá trị 1) | 3 (giá trị 8) | 4 (giá trị 4) |
| 2 | 2 | 0 (giá trị 1) | 5 (giá trị 6) | Không có |
| 3 | 8 | 1 (giá trị 3) | Không có | Không có |
| 4 | 4 | 1 (giá trị 3) | Không có | Không có |
| 5 | 6 | 2 (giá trị 2) | Không có | Không có |

Trong bảng, dấu “Không có” nghĩa là công thức dẫn tới chỉ số **≥ n**, không phải vị trí chứa None trong mảng.

## 6. Nút lá, nút trong và mức của cây

Bởi binary heap là cây gần đầy đủ, nhiều đặc điểm có thể suy ra chỉ từ **n**.

### 6.1. Vị trí nút lá

Một nút i là **nút lá** nếu không có con trái:

\[
2i + 1 \ge n.
\]

Suy ra các chỉ số nút lá là:

\[
i = \left\lfloor \frac{n}{2} \right\rfloor,\ \ldots,\ n-1.
\]

Nói cách khác, nếu n > 0, **mọi chỉ số từ n // 2 đến n − 1 đều là nút lá**.

Ví dụ n = 6:

~~~text
n // 2 = 3

Nút trong: chỉ số 0, 1, 2
Nút lá:   chỉ số 3, 4, 5
~~~

Với n = 7, các nút lá là 3, 4, 5, 6. Với **n = 1**, nút gốc ở chỉ số 0 cũng chính là nút lá. Với **n = 0**, không có nút lá nào.

### 6.2. Vị trí nút trong

Nếu n ≥ 2, nút trong cuối cùng có chỉ số:

\[
\left\lfloor \frac{n}{2} \right\rfloor-1.
\]

Công thức tương đương:

\[
\left\lfloor \frac{n-2}{2} \right\rfloor.
\]

Đây là điểm xuất phát quan trọng của **bottom-up heapify**: bắt đầu từ **n // 2 − 1**, rồi giảm dần về 0. Các nút ở nửa sau mảng đều là lá, vốn tự thỏa quan hệ heap trong cây con một nút.

### 6.3. Mức và chiều cao

Đặt gốc ở **mức 0**. Trong một cây gần đầy đủ, mức d nếu tồn tại có tối đa **2^d** nút, với chỉ số bắt đầu:

\[
2^d-1.
\]

Nếu cả mức d đầy đủ, chỉ số cuối mức đó là:

\[
2^{d+1}-2.
\]

Với n nút thực tế, chỉ số cuối mức d phải cắt tại **n − 1**.

Với **n ≥ 1**:

- **Mức sâu nhất** hay **chiều cao tính theo số cạnh** là **⌊log₂ n⌋**.
- **Số mức** là **⌊log₂ n⌋ + 1**.
- Chiều cao tăng theo **Θ(log n)** khi n tăng.

Ví dụ:

| n | Chỉ số mức cuối | Chiều cao (cạnh) | Số mức |
| ---: | --- | ---: | ---: |
| 1 | 0 | 0 | 1 |
| 2 | 1 | 1 | 2 |
| 3 | 1, 2 | 1 | 2 |
| 4 | 3 | 2 | 3 |
| 6 | 3, 4, 5 | 2 | 3 |
| 7 | 3, 4, 5, 6 | 2 | 3 |
| 8 | 7 | 3 | 4 |

Với n = 0, heap rỗng không có gốc hay mức nào; không nên áp dụng log₂ 0.

## 7. Bất biến min-heap và max-heap theo chỉ số

Với mảng a dài n, **min-heap** thỏa:

\[
a[\operatorname{parent}(i)] \le a[i] \quad \text{với mọi } 1 \le i < n.
\]

Còn **max-heap** thỏa:

\[
a[\operatorname{parent}(i)] \ge a[i] \quad \text{với mọi } 1 \le i < n.
\]

Ta có thể kiểm tra một lần từ chỉ số **1 đến n − 1**. Mỗi nút ngoài gốc được so với cha đúng một lần, nên toàn bộ kiểm tra tốn **Θ(n)** thời gian và **O(1)** bộ nhớ phụ.

### 7.1. Bất biến min-heap không yêu cầu anh em được sắp

Ví dụ:

~~~text
a = [1, 3, 2, 8, 4, 6]
~~~

Mảng này là **min-heap hợp lệ** dù **3 đứng trước 2** và **8 đứng trước 4**. Quan hệ heap chỉ yêu cầu **cha ≤ từng con**, không yêu cầu các nút cùng mức được xếp từ trái sang phải theo thứ tự giá trị.

Tương tự, các nút ở hai nhánh khác nhau không có quan hệ thứ tự toàn cục nào ngoài việc chúng đều không ưu tiên hơn tổ tiên trên đường lên gốc.

### 7.2. Vì sao gốc có khóa nhỏ nhất?

Trong min-heap, với bất kỳ nút i, đường đi từ gốc tới i là chuỗi cha–con:

~~~text
root → ... → parent(i) → i
~~~

Vì từng cạnh đều thỏa **khóa cha ≤ khóa con**, theo tính bắc cầu của phép so sánh, **a[0] ≤ a[i]**. Do đó, gốc chứa **một trong các khóa nhỏ nhất**.

Nếu nhiều entry có khóa bằng nhau, gốc là **một entry có khóa nhỏ nhất**, không nhất thiết là entry được thêm trước; tính ổn định cần chính sách tie-breaking riêng.

Với max-heap, lập luận tương tự cho thấy **gốc có khóa lớn nhất**.

### 7.3. Heap không phải cây tìm kiếm nhị phân

Một **cây tìm kiếm nhị phân (BST)** có quan hệ kiểu “giá trị trong cây con trái nhỏ hơn gốc, giá trị trong cây con phải lớn hơn gốc” theo chính sách khóa trùng. Binary heap **không** yêu cầu quan hệ trái–phải như vậy.

Ví dụ, trong min-heap, nút con trái 3 và con phải 2 là hoàn toàn hợp lệ. Không thể tìm khóa 6 bằng quy tắc “nhỏ hơn đi trái, lớn hơn đi phải” như BST.

**Tìm giá trị bất kỳ** trong binary heap thông thường vẫn cần **O(n)** thời gian trong trường hợp xấu nhất nếu không có thêm chỉ mục phụ.

## 8. Thêm phần tử và di chuyển lên (sift-up)

Khi thêm một khóa mới vào min-heap lưu bằng mảng, ta thực hiện hai giai đoạn:

1. **Giữ hình dạng gần đầy đủ:** thêm phần tử vào cuối mảng (chỉ số n cũ), tức vị trí tiếp theo được lấp từ trái sang phải.
2. **Khôi phục bất biến thứ tự:** nếu khóa mới **nhỏ hơn khóa cha**, hoán đổi nó với cha; lặp lại cho đến khi khóa cha không lớn hơn nó, hoặc nút đã lên gốc.

Giai đoạn 2 gọi là **sift-up**, **bubble-up** hoặc **percolate-up**.

### 8.1. Mô phỏng push(2)

Ban đầu:

~~~text
a = [3, 5, 4, 9, 8, 7]

          3
        /   \
       5     4
      / \   /
     9   8 7
~~~

Thêm 2 ở cuối:

~~~text
Chỉ số: 0  1  2  3  4  5  6
a =    [3, 5, 4, 9, 8, 7, 2]

          3
        /   \
       5     4
      / \   / \
     9   8 7   2
~~~

Nút mới ở i = 6 có cha (6 − 1) // 2 = **2**, chứa 4. Vì 2 < 4, hoán đổi:

~~~text
a = [3, 5, 2, 9, 8, 7, 4]
             ▲
          i = 2
~~~

Bây giờ i = 2, cha là (2 − 1) // 2 = **0**, chứa 3. Vì 2 < 3, hoán đổi tiếp:

~~~text
a = [2, 5, 3, 9, 8, 7, 4]
     ▲
    gốc
~~~

Đã tới gốc, thuật toán dừng. Heap có n = 7 và vẫn gần đầy đủ.

### 8.2. Pseudocode sift-up

~~~text
sift_up(a, i):
    while i > 0:
        p = (i - 1) // 2
        if a[p] <= a[i]:
            break
        đổi chỗ a[p] và a[i]
        i = p
~~~

**Bất biến trong quá trình sửa:** ngoài đường từ vị trí phần tử mới về gốc, các cây con trước đó vẫn thỏa thứ tự min-heap. Sift-up chỉ cần sửa những cạnh có thể vi phạm do một entry mới được thêm vào.

Chiều dài đường từ một nút tới gốc là **O(log n)**, nên số lần hoán đổi trong sift-up là O(log n). Trường hợp khóa mới đã lớn hơn hoặc bằng cha, không cần đổi chỗ nào.

## 9. Lấy gốc và di chuyển xuống (sift-down)

Đối với min-priority queue được cài bằng min-heap, phần tử ưu tiên nhất nằm ở gốc **a[0]**. Lấy gốc ra cần duy trì cả hình dạng và thứ tự heap.

Các bước:

1. Ghi nhớ entry ở gốc để trả kết quả.
2. Lấy **phần tử cuối mảng** ra.
3. Nếu heap vẫn còn phần tử, đặt phần tử cuối vừa lấy vào **a[0]**.
4. **Sift-down** từ gốc: so với các con tồn tại, hoán đổi với **con có khóa nhỏ hơn** nếu con ấy ưu tiên hơn cha.
5. Dừng khi cha đã ≤ mọi con tồn tại, hoặc tới nút lá.

**Không được chọn bừa một con** khi sift-down. Nếu gốc lớn hơn cả hai con, phải chọn con có khóa nhỏ hơn trong min-heap để giữ thứ tự heap.

### 9.1. Mô phỏng pop từ min-heap

Ban đầu:

~~~text
a = [2, 5, 3, 9, 8, 7, 4]
~~~

Pop trả về khóa **2**. Lấy phần tử cuối là 4 đặt lên gốc:

~~~text
a = [4, 5, 3, 9, 8, 7]
          ▲
         gốc
~~~

Hai con của gốc có khóa 5 và 3. Vì **3 < 4**, đổi gốc với nút con phải ở i = 2:

~~~text
a = [3, 5, 4, 9, 8, 7]
            ▲
           i=2
~~~

Nút i = 2 có con trái ở 5 với khóa 7 và không có con phải (chỉ số 6 ≥ n). Vì **4 ≤ 7**, dừng.

Heap sau pop có n = 6 nút; bất biến min-heap được phục hồi.

### 9.2. Pseudocode sift-down

~~~text
sift_down(a, i):
    n = len(a)
    loop:
        l = 2*i + 1
        r = 2*i + 2

        if l >= n:
            break                  # Không có con: nút lá.

        smaller = l
        if r < n and a[r] < a[l]:
            smaller = r

        if a[i] <= a[smaller]:
            break

        đổi chỗ a[i] với a[smaller]
        i = smaller
~~~

Điều kiện **r < n** là bắt buộc trước khi đọc a[r]. Một nút trong heap gần đầy đủ có thể **chỉ có con trái**, nhưng không bao giờ chỉ có con phải.

Vì sift-down chỉ đi theo một đường từ gốc xuống lá, thời gian là **O(log n)**; số biến tạm là O(1).

## 10. Xây heap từ mảng bất kỳ bằng bottom-up heapify

Giả sử người dùng cung cấp một mảng có n khóa chưa chắc thỏa thứ tự heap. Có hai cách phổ biến để tạo heap:

- **Push từng entry** vào heap trống: tổng thời gian O(n log n) trong trường hợp xấu nhất.
- **Bottom-up heapify:** giữ nguyên hình dạng của mảng, đi từ nút trong cuối cùng về gốc, gọi sift-down để sửa từng cây con.

### 10.1. Tại sao bắt đầu ở n // 2 − 1?

Trong mảng heap, tất cả chỉ số **i ≥ n // 2** là **nút lá**. Mỗi lá một mình đã là một min-heap hợp lệ, nên không cần sift-down.

Vì vậy, nút trong cuối cùng:

~~~python
last_internal = len(a) // 2 - 1
~~~

Và thuật toán:

~~~python
for i in range(len(a) // 2 - 1, -1, -1):
    sift_down(a, i)
~~~

Khi xử lý i từ phải sang trái, các cây con của i đã được sửa thành heap. Sift-down tại i tiếp tục làm cho cả cây con gốc i thành một heap hợp lệ.

### 10.2. Mô phỏng heapify

Mảng ban đầu:

~~~text
a = [9, 5, 7, 3, 8, 4]
n = 6
last_internal = 6//2 - 1 = 2
~~~

Các bước:

| Nút trong i được sửa | Cây con có liên quan | Mảng sau sift-down(i) |
| ---: | --- | --- |
| 2 | Khóa 7 với con 4 | [9, 5, 4, 3, 8, 7] |
| 1 | Khóa 5 với các con 3, 8 | [9, 3, 4, 5, 8, 7] |
| 0 | Khóa 9 và cây con có gốc 3, 4 | [3, 5, 4, 9, 8, 7] |

Mảng cuối là min-heap hợp lệ; **không nhất thiết** có thứ tự tăng dần toàn mảng.

### 10.3. Vì sao heapify từ dưới lên là Θ(n)?

Mỗi sift-down riêng lẻ có **độ phức tạp xấu nhất O(log n)**. Tuy nhiên, không phải tất cả n nút đều phải đi xuống log n mức.

- Khoảng một nửa số nút là lá, không cần sửa.
- Khoảng một phần tư số nút nằm ngay trên lá, có thể phải đi xuống tối đa một mức.
- Số nút có thể đi xuống rất sâu giảm dần theo cấp số nhân.

Một cận trên cho tổng công việc là:

\[
O\left(n\sum_{h=0}^{\infty}\frac{h}{2^h}\right)=O(n).
\]

Do phải xét ít nhất n phần tử để xây heap từ đầu vào n entry, ta có **Θ(n)** thời gian cho bottom-up heapify trong mô hình so sánh khóa O(1).

**Đừng nhầm:** O(n log n) là cận trên có thể suy ra bằng cách nhân sai “n lần sift-down sâu log n”; nó không phản ánh việc phần lớn nút rất gần lá.

## 11. Cài đặt Python: binary min-heap lưu trong list

Ví dụ sau **không dựa vào heapq**, nhằm giúp quan sát trực tiếp công thức chỉ số và thuật toán sift. Mã sử dụng Python 3.10 trở lên, với khóa là số nguyên có thể so sánh bằng các toán tử thông thường.

~~~python
from __future__ import annotations


class BinaryMinHeap:
    def __init__(self, values=None):
        self._data = list(values) if values is not None else []

        # Bottom-up heapify, sửa từ nút trong cuối cùng về gốc.
        for i in range(len(self._data) // 2 - 1, -1, -1):
            self._sift_down(i)

    @staticmethod
    def parent_index(i: int) -> int:
        if i <= 0:
            raise IndexError("Gốc không có cha")
        return (i - 1) // 2

    @staticmethod
    def left_index(i: int) -> int:
        if i < 0:
            raise IndexError("Chỉ số nút phải không âm")
        return 2 * i + 1

    @staticmethod
    def right_index(i: int) -> int:
        if i < 0:
            raise IndexError("Chỉ số nút phải không âm")
        return 2 * i + 2

    def __len__(self) -> int:
        return len(self._data)

    def is_empty(self) -> bool:
        return len(self._data) == 0

    def peek(self) -> int:
        if not self._data:
            raise IndexError("Heap rỗng")
        return self._data[0]

    def children_indices(self, i: int) -> tuple[int | None, int | None]:
        """Trả chỉ số hai con nếu tồn tại, nếu không trả None."""
        if i < 0 or i >= len(self._data):
            raise IndexError("Chỉ số nút ngoài phạm vi")

        left = 2 * i + 1
        right = 2 * i + 2
        n = len(self._data)
        return (
            left if left < n else None,
            right if right < n else None,
        )

    def push(self, value: int) -> None:
        self._data.append(value)   # Đặt vào vị trí n cũ: giữ hình dạng.
        self._sift_up(len(self._data) - 1)

    def _sift_up(self, i: int) -> None:
        while i > 0:
            parent = (i - 1) // 2
            if self._data[parent] <= self._data[i]:
                break

            self._data[parent], self._data[i] = (
                self._data[i], self._data[parent]
            )
            i = parent

    def _sift_down(self, i: int) -> None:
        n = len(self._data)

        while True:
            left = 2 * i + 1
            right = 2 * i + 2

            if left >= n:
                break             # Nút lá, không có con trái.

            smaller = left
            if right < n and self._data[right] < self._data[left]:
                smaller = right

            if self._data[i] <= self._data[smaller]:
                break

            self._data[i], self._data[smaller] = (
                self._data[smaller], self._data[i]
            )
            i = smaller

    def pop(self) -> int:
        if not self._data:
            raise IndexError("Heap rỗng")

        result = self._data[0]
        last = self._data.pop()

        if self._data:            # Sau pop vẫn còn nút.
            self._data[0] = last
            self._sift_down(0)

        return result

    def is_valid_min_heap(self) -> bool:
        """Kiểm tra quan hệ cha <= con cho từng nút khác gốc."""
        for i in range(1, len(self._data)):
            parent = (i - 1) // 2
            if self._data[parent] > self._data[i]:
                return False
        return True

    def as_list(self) -> list[int]:
        """Bản sao để quan sát, không cho sửa mảng nội bộ."""
        return list(self._data)


# Trống, một nút và các chỉ số cha/con.
empty = BinaryMinHeap()
assert len(empty) == 0 and empty.is_empty()
assert empty.is_valid_min_heap()

single = BinaryMinHeap([7])
assert single.peek() == 7
assert single.children_indices(0) == (None, None)
assert single.is_valid_min_heap()

sample = BinaryMinHeap([1, 3, 2, 8, 4, 6])
assert sample.as_list() == [1, 3, 2, 8, 4, 6]
assert sample.children_indices(0) == (1, 2)
assert sample.children_indices(2) == (5, None)
assert sample.children_indices(4) == (None, None)
assert BinaryMinHeap.parent_index(5) == 2
assert sample.is_valid_min_heap()

# Sift-up: khóa 2 đi từ vị trí cuối lên gốc.
trace = BinaryMinHeap([3, 5, 4, 9, 8, 7])
trace.push(2)
assert trace.as_list() == [2, 5, 3, 9, 8, 7, 4]
assert trace.is_valid_min_heap()

# Sift-down: bỏ 2, đưa 4 lên gốc rồi sửa.
assert trace.pop() == 2
assert trace.as_list() == [3, 5, 4, 9, 8, 7]
assert trace.is_valid_min_heap()

# Heapify từ mảng chưa sắp.
heap = BinaryMinHeap([9, 5, 7, 3, 8, 4])
assert heap.is_valid_min_heap()
assert heap.peek() == 3

# Khóa bằng nhau được giữ lại, không bị loại trùng.
heap.push(3)
assert heap.is_valid_min_heap()
result = []
while not heap.is_empty():
    result.append(heap.pop())
assert result == [3, 3, 4, 5, 7, 8, 9]
assert heap.is_empty()
assert heap.is_valid_min_heap()

# API rõ ràng khi rỗng.
try:
    heap.pop()
except IndexError:
    pass
else:
    raise AssertionError("Pop heap rỗng phải báo IndexError")

try:
    BinaryMinHeap.parent_index(0)
except IndexError:
    pass
else:
    raise AssertionError("Không tồn tại cha của gốc")
~~~

### Những điểm cần quan sát trong ví dụ

- **_data** là list Python lưu liên tiếp tất cả các entry; không có đối tượng cây hay con trỏ left/right.
- **push** nối vào cuối list rồi gọi **_sift_up**.
- **pop** giữ giá trị gốc, thay bằng phần tử cuối và gọi **_sift_down** nếu list còn phần tử.
- **children_indices** trả về None cho con không tồn tại sau khi kiểm tra ranh giới.
- **is_valid_min_heap** so sánh từng nút với cha; vì list không có lỗ nên bất biến hình dạng đã được bảo đảm bởi cách lưu.
- **as_list** trả bản sao thay vì cho bên ngoài truy cập và sửa trực tiếp list đang bảo vệ bất biến heap.

Các đoạn assert minh họa cách tự đối chiếu kết quả. Theo quy trình viết bài, mã chỉ là tài liệu học tập; bước thực thi kiểm thử và QA chuyên môn sẽ được thực hiện trong giai đoạn kiểm tra nội dung riêng.

## 12. Nếu đánh số mảng từ 1 thì công thức thay đổi

Một số sách hoặc cài đặt dùng chỉ số **1-based**, đặt gốc ở a[1] và có thể bỏ trống a[0]. Với quy ước này:

| Quan hệ | 0-based (gốc = 0) | 1-based (gốc = 1) |
| --- | --- | --- |
| Chỉ số gốc | 0 | 1 |
| Cha của nút i khác gốc | (i − 1) // 2 | i // 2 |
| Con trái | 2i + 1 | 2i |
| Con phải | 2i + 2 | 2i + 1 |
| Chỉ số nút dữ liệu | 0 đến n − 1 | 1 đến n |
| Điều kiện con còn tồn tại | child < n | child ≤ n |

Ví dụ với cùng cây:

~~~text
Nút:        1, 3, 2, 8, 4, 6

0-based:
index:      0  1  2  3  4  5
a:         [1, 3, 2, 8, 4, 6]

1-based (a[0] bỏ trống):
index:      0     1  2  3  4  5  6
a:         [None, 1, 3, 2, 8, 4, 6]
~~~

Ở 1-based, nút có chỉ số i = 3 (giá trị 2) có cha **3 // 2 = 1** (giá trị 1), con trái ở **2×3 = 6** (giá trị 6), con phải ở **7**, không tồn tại vì n = 6.

**Không được dùng lẫn công thức 0-based và 1-based.** Nếu mảng Python bắt đầu bằng dữ liệu tại a[0] nhưng lại lấy con trái = 2i, thì con trái của gốc sẽ bị tính thành chính gốc, làm thuật toán sai ngay từ bước đầu.

### Có nên dùng a[0] làm sentinel?

Với 1-based, a[0] thường là chỗ bỏ trống để dễ viết công thức. Nó **không tự nhiên là một nút heap**, không được tính vào n và không nên tham gia so sánh khóa. Nếu đặt None ở a[0], đừng để sift-up/sift-down so sánh trực tiếp None với số.

Cách chọn 0-based hay 1-based đều có thể đúng; quan trọng nhất là **nhất quán** trong mọi hàm liên quan.

## 13. Trường hợp biên và giá trị bằng nhau

### 13.1. Heap rỗng (n = 0)

~~~text
a = []
~~~

Không có gốc, cha, con hoặc nút lá. Gọi peek/pop cần xử lý bằng lỗi hoặc hợp đồng kết quả rỗng rõ ràng. Vòng heapify từ nút trong cuối cùng không cần chạy.

### 13.2. Heap một nút (n = 1)

~~~text
a = [42]
~~~

Gốc ở i = 0 cũng là lá, không có cha và con. Peek trả 42. Pop trả 42 rồi heap rỗng; không gọi sift-down trên một phần tử không còn tồn tại.

### 13.3. Heap hai nút (n = 2)

~~~text
     3
    /
   9

a = [3, 9]
~~~

Gốc có **con trái tại i = 1** nhưng không có con phải, vì i = 2 ngoài mảng. Sift-down phải xử lý trường hợp chỉ một con.

### 13.4. Số nút lẻ/chẵn

Với n lẻ lớn hơn 1, nút trong cuối cùng thường có **đủ hai con**; với n chẵn, nút trong cuối cùng có **một con trái**. Điều này xuất phát từ cách lấp nút theo thứ tự mức.

Ví dụ:

~~~text
n = 5:  nút i = 1 có hai con i = 3, 4
n = 6:  nút i = 2 có một con trái i = 5
~~~

Dù vậy, mọi thuật toán đều phải kiểm tra **chỉ số tồn tại** thay vì giả định hai con lúc nào cũng có mặt.

### 13.5. Khóa trùng

Min-heap dùng quan hệ **cha ≤ con**, không yêu cầu cha < con. Vì thế:

~~~text
a = [2, 2, 2, 5, 2]
~~~

là min-heap hợp lệ. Một thao tác pop lấy một entry có khóa 2, nhưng không bắt buộc lấy **entry 2 được thêm sớm nhất** nếu heap không bổ sung chính sách ổn định.

Nếu cần bảo đảm FIFO trong các khóa bằng nhau, có thể so sánh khóa kép **(priority, sequence)**, còn payload được giữ riêng và không tham gia so sánh.

### 13.6. Không thay đổi khóa ngầm

Nếu đang lưu các đối tượng có trường priority và sửa trực tiếp priority bên ngoài mà không chạy phép sửa heap, các quan hệ cha/con có thể bị phá vỡ.

Ví dụ, nếu một nút con đang có khóa 8 và cha có khóa 3, sau khi sửa khóa con thành 1 thì cần **sift-up** hoặc một cơ chế cập nhật tương đương. Heap không tự động biết giá trị đã bị đổi trong đối tượng.

## 14. Độ phức tạp thời gian và bộ nhớ

Giả định heap có n phần tử, phép so sánh khóa và tính toán chỉ số là O(1), dùng cấu trúc mảng động thông thường.

| Thao tác | Thời gian theo thuật toán heap | Bộ nhớ phụ |
| --- | --- | --- |
| Tính cha / con từ một chỉ số | **Θ(1)** | O(1) |
| Đọc khóa ở gốc (peek) | **Θ(1)** | O(1) |
| Kiểm tra heap rỗng / lấy size | **Θ(1)** | O(1) |
| Đọc entry tại chỉ số i đã biết | **Θ(1)** | O(1) |
| Push: append + sift-up | **O(log n)** | O(1) |
| Pop gốc: thay phần tử cuối + sift-down | **O(log n)** | O(1) |
| Bottom-up heapify từ n entry | **Θ(n)** | O(1) nếu sửa mảng tại chỗ |
| Kiểm tra quan hệ cha–con cho tất cả nút | **Θ(n)** | O(1) |
| Tìm một khóa bất kỳ không có chỉ mục phụ | **O(n)** | O(1) |
| Duyệt toàn bộ n entry | **Θ(n)** | O(1) nếu không tạo kết quả |
| Tạo bản sao mảng heap | **Θ(n)** | O(n) |

### Giải thích về push/pop và mảng động

Trong phân tích chuẩn, **push/pop của heap nhị phân** được nói là O(log n) vì số phép so sánh/hoán đổi bằng chiều cao cây. Nếu dùng **mảng động**, một lần **mở rộng vùng nhớ** có thể cần sao chép O(n) entry, nên thời gian **một lần push cụ thể** đôi khi lớn hơn O(log n). Với chính sách tăng dung lượng theo cấp số nhân thông thường, chi phí append được tính **O(1) khấu hao**, và chi phí push **O(log n) khấu hao** vẫn là mô hình phù hợp.

Bản thân thao tác sift-up và sift-down thực hiện ngay trên mảng, không tạo thêm cây hay n nút mới, nên bộ nhớ phụ **O(1)**.

**Heapify Θ(n)** giả định đã có mảng chứa n entry và chỉ sắp đặt lại trong mảng ấy. Nếu hàm khởi tạo cần **tạo bản sao từ dữ liệu đầu vào**, phải tính thêm **Θ(n) bộ nhớ** để chứa bản sao, như lớp Python trong mục 11.

### Vì sao đọc theo chỉ số O(1) không đồng nghĩa tìm theo khóa O(1)?

Mảng hỗ trợ **a[i]** trong O(1) khi đã biết i. Nhưng cấu trúc heap không cho biết khóa k đang ở chỉ số nào nếu chưa có bảng ánh xạ bổ sung. Muốn tìm một khóa bất kỳ có thể phải quét nhiều entry, tốn O(n) trong trường hợp xấu nhất.

Đây là điểm phân biệt **truy cập theo chỉ số** của mảng với **tra cứu theo giá trị** của cấu trúc.

## 15. Ứng dụng thực tế và khi nào nên chọn binary heap

### 15.1. Lập lịch công việc

Giả sử mỗi công việc có khóa ưu tiên. Min-heap lưu các entry với khóa nhỏ nhất ở gốc để hệ thống xem hoặc lấy công việc ưu tiên nhất.

- **peek:** đọc khóa ưu tiên nhất mà chưa lấy ra.
- **push:** thêm công việc mới và sift-up nếu nó quan trọng hơn cha.
- **pop:** lấy công việc ưu tiên nhất và sift-down để khôi phục thứ tự.

Nếu có nhiều công việc cùng khóa, tính ổn định cần **sequence number** hoặc quy tắc tie-breaking riêng; binary heap cơ bản không tự cung cấp FIFO trong nhóm đồng ưu tiên.

### 15.2. Mô phỏng sự kiện

Trong mô phỏng sự kiện rời rạc, khóa thường là **thời điểm sự kiện**. Một min-heap giúp lấy sự kiện có thời điểm nhỏ nhất, sau đó thêm những sự kiện mới được sinh ra trong quá trình mô phỏng.

Cây gần đầy đủ cho phép mảng biểu diễn cây gọn gàng và giúp push/pop theo số mức logarit dù tổng số sự kiện lớn.

### 15.3. Thuật toán đồ thị

Các thuật toán như **Dijkstra** hoặc **Prim** có thể dùng hàng đợi ưu tiên triển khai bằng heap. Trong đó, khóa ưu tiên là khoảng cách tạm thời hoặc trọng số của một ứng viên.

Tuy nhiên, nếu thuật toán cần **decrease-key theo ID**, chỉ biết heap lưu bằng mảng không đủ để tìm nhanh entry theo ID. Có thể cần bảng ánh xạ ID → chỉ số được cập nhật mỗi khi hoán đổi, hoặc chiến lược chèn entry mới và bỏ qua entry lỗi thời.

### 15.4. Khi nào không nên chọn heap?

Nếu bài toán chủ yếu cần **tìm một khóa bất kỳ**, **duyệt tất cả phần tử theo thứ tự đã sắp** hoặc **truy vấn theo khoảng**, heap thường không trực tiếp cung cấp hiệu năng hoặc giao diện mong muốn.

Nếu dữ liệu rất ít, một list đơn giản có thể dễ dùng hơn. Nếu cần cập nhật theo khóa, một cấu trúc cây cân bằng hay một heap kết hợp bảng băm có thể thích hợp tùy tải công việc. Quyết định chọn cấu trúc nên dựa trên tập thao tác thực tế, không chỉ dựa vào việc heap có peek O(1).

## 16. Những lỗi phổ biến khi ánh xạ mảng–cây

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng parent(i) cho i = 0 | Python tính ra -1 và có thể truy cập phần tử cuối | Dừng sift-up tại gốc, không lấy cha gốc |
| Dùng con trái = 2i trong mảng 0-based | Con trái của gốc trở thành chính gốc | Dùng 2i + 1 và 2i + 2 |
| Dùng con trái = 2i + 1 trong mảng 1-based | Lệch vị trí các con | Quy ước chỉ số nhất quán |
| Đọc con chỉ vì công thức cho ra một số | Có thể truy cập ngoài phạm vi | Kiểm tra child < n với 0-based |
| Dùng child <= n thay vì child < n | Chấp nhận chỉ số n không hợp lệ | Dùng bất đẳng thức nghiêm |
| Cho rằng mọi nút trong đều có hai con | Truy cập con phải không tồn tại ở n chẵn | Kiểm tra riêng từng chỉ số |
| Bắt đầu heapify từ n − 1 | Gọi sift-down không cần thiết cho các lá | Bắt đầu ở n//2 − 1 |
| Chọn con lớn hơn khi sift-down min-heap | Có thể phá bất biến cha ≤ con | Chọn con có khóa nhỏ hơn |
| Chỉ kiểm tra gốc nhỏ nhất | Không phát hiện cặp cha–con vi phạm sâu hơn | Kiểm tra mọi i từ 1 đến n−1 |
| Cho rằng mảng heap được sắp tăng dần | Tìm sai phần tử nhỏ thứ hai | Chỉ bảo đảm bất biến cha–con |
| Nhầm heap với BST | Tìm khóa bằng quy tắc rẽ trái/phải sai | Dùng đúng quan hệ của từng cấu trúc |
| Bỏ qua phần tử cuối trước khi pop | Mất hình dạng gần đầy đủ | Đưa phần tử cuối lên gốc rồi sift-down |
| Không xử lý n = 0 hoặc n = 1 | IndexError và sai bất biến | Kiểm tra rỗng và nhánh sau khi pop |
| Dùng khóa không có quan hệ so sánh nhất quán | Heap có thứ tự không xác định | Chuẩn hóa khóa/định nghĩa so sánh rõ |
| Đổi khóa của entry mà không sửa heap | Cha có thể lớn hơn con | Có API cập nhật và sift đúng hướng |
| Nhầm size logic với dung lượng list được cấp phát | Xác định con tồn tại dựa trên capacity | Dùng số entry thực tế len(a) |
| Coi heapify Θ(n) là n lần sift sâu log n | Phân tích quá cao | Phân tích theo chiều cao từng nút |

**Cách kiểm tra bằng tay:** viết hàng chỉ số 0..n−1 bên trên mảng, nối mũi tên từ i đến **2i + 1** và **2i + 2** chỉ khi các chỉ số đó nhỏ hơn n. Sau đó kiểm tra từng cạnh theo quan hệ min-heap hoặc max-heap. Thử cả n = 0, 1, 2, 5, 6 và 7 để lộ lỗi biên.

## 17. Bài tập tự luyện có đáp án

**Bài 1 — Tìm cha.** Với mảng 0-based, nút ở i = 9 có cha ở chỉ số nào?

*Đáp án:* (9 − 1) // 2 = **4**.

**Bài 2 — Tìm hai con.** Nút ở i = 3 có các chỉ số con theo 0-based là gì?

*Đáp án:* Con trái **7**, con phải **8**, nếu chúng nhỏ hơn n.

**Bài 3 — Một con.** Heap có n = 6, nút ở i = 2 có những con nào?

*Đáp án:* Con trái ở **5** tồn tại; con phải ở **6** không tồn tại vì chỉ số hợp lệ là 0..5.

**Bài 4 — Nút lá.** Heap có n = 9. Các chỉ số nút lá là gì?

*Đáp án:* n//2 = 4 nên các lá là **4, 5, 6, 7, 8**.

**Bài 5 — Nút trong cuối cùng.** Với n = 10, nút trong cuối cùng có chỉ số bao nhiêu?

*Đáp án:* 10//2 − 1 = **4**.

**Bài 6 — Mảng và cây.** Cho a = [1, 3, 2, 8, 4, 6]. Giá trị hai con của nút chứa 3 là gì?

*Đáp án:* Nút chứa 3 ở i = 1, hai con ở i = 3 (giá trị **8**) và i = 4 (giá trị **4**).

**Bài 7 — Có phải min-heap?** a = [1, 5, 2, 8, 3, 6] có là min-heap không?

*Đáp án:* **Không**. Nút ở i = 4 chứa 3, cha i = 1 chứa 5; vi phạm **5 ≤ 3**.

**Bài 8 — Heap có cần mảng đã sắp?** a = [1, 3, 2, 8, 4, 6] không tăng dần vì 3 > 2. Nó có thể là min-heap không?

*Đáp án:* **Có**, vì các quan hệ cha ≤ con đều đúng.

**Bài 9 — Chiều cao.** Binary heap có n = 15 nút. Chiều cao tính theo số cạnh là bao nhiêu?

*Đáp án:* **⌊log₂ 15⌋ = 3**, nên có 4 mức (0 đến 3).

**Bài 10 — Push.** Bắt đầu với [3, 5, 4, 9, 8, 7]. Sau push(2), mảng heap là gì theo sift-up đã học?

*Đáp án:* **[2, 5, 3, 9, 8, 7, 4]**. Khóa 2 đổi chỗ lần lượt với 4 và 3.

**Bài 11 — Pop.** Từ [2, 5, 3, 9, 8, 7, 4], pop min trả giá trị gì và heap mới là gì?

*Đáp án:* Trả **2**. Đưa 4 từ cuối lên gốc, đổi với con 3, thu được **[3, 5, 4, 9, 8, 7]**.

**Bài 12 — Chọn con khi sift-down.** Một nút có khóa 10, con trái 7 và con phải 4. Với min-heap, cần đổi với con nào?

*Đáp án:* Đổi với **con phải khóa 4** vì đó là con nhỏ hơn. Đổi với con 7 có thể để cha 7 lớn hơn con 4 còn lại.

**Bài 13 — Heapify.** Với n = 6, bottom-up heapify bắt đầu xử lý ở các chỉ số nào theo thứ tự?

*Đáp án:* **2, 1, 0**. Các chỉ số 3, 4, 5 là lá, không cần sift-down.

**Bài 14 — Chỉ số 1-based.** Nếu gốc ở a[1], nút i = 4 có cha và các con ở đâu?

*Đáp án:* Cha **4//2 = 2**, con trái **8**, con phải **9** nếu còn trong mảng.

**Bài 15 — Vì sao parent(0) nguy hiểm?** Công thức (i − 1)//2 tại i = 0 trả -1. Tại sao không nên dùng kết quả đó trong Python?

*Đáp án:* Gốc **không có cha**; Python cho phép a[-1] đọc phần tử cuối. Thuật toán có thể không báo lỗi mà âm thầm so sánh với sai nút.

**Bài 16 — Khóa bằng nhau.** a = [2, 2, 2, 5, 2] có thỏa min-heap không?

*Đáp án:* **Có**, vì quan hệ cha ≤ con cho phép bằng nhau. Heap không tự bảo đảm thứ tự FIFO giữa các entry cùng khóa.

**Bài 17 — Phân biệt độ phức tạp.** Tại sao push và pop thường có O(log n), còn bottom-up heapify đạt Θ(n)?

*Đáp án:* Push/pop sửa dọc một đường tối đa chiều cao log n. Bottom-up heapify sửa nhiều cây con, nhưng phần lớn nút nằm gần lá và chỉ cần rất ít bước; tổng công việc Θ(n).

**Bài 18 — Tìm kiếm theo khóa.** Có thể dùng a[i] để đọc nhanh một vị trí. Vì sao tìm một khóa bất kỳ trong heap vẫn có thể tốn O(n)?

*Đáp án:* Ta không biết trước khóa cần tìm nằm ở chỉ số nào, và quan hệ heap không sắp xếp toàn bộ mảng như BST hay mảng tăng dần. Nếu không có chỉ mục bổ sung, có thể phải xem gần hết n entry.

**Bài 19 — Hai bất biến.** Một cây thỏa cha ≤ con nhưng không gần đầy đủ có được gọi là binary heap chuẩn không?

*Đáp án:* **Không**. Binary heap chuẩn cần cả **hình dạng cây nhị phân gần đầy đủ** lẫn **quan hệ thứ tự heap**.

**Bài 20 — Min và max.** Với max-heap, điều kiện so sánh giữa cha và con thay đổi thế nào?

*Đáp án:* Cha phải có khóa **≥** từng con. Các công thức chỉ số cha/con **không đổi**, vì hình dạng cây và cách lưu mảng không đổi.

**Ghi nhớ:** Binary heap dùng **mảng theo thứ tự mức** để biểu diễn một **cây nhị phân gần đầy đủ**. Với chỉ số bắt đầu từ 0, **cha = (i − 1)//2**, **con trái = 2i + 1**, **con phải = 2i + 2**, và chỉ đọc con khi chỉ số **nhỏ hơn n**. Trong min-heap, **mỗi cha ≤ các con** nên phần tử nhỏ nhất nằm ở gốc, nhưng mảng heap **không được sắp tăng dần**. Việc thêm/lấy gốc sửa một đường cao O(log n), còn xây heap từ dưới lên đạt Θ(n). Luôn giữ riêng hai bất biến **hình dạng** và **thứ tự** khi phân tích hoặc triển khai.
