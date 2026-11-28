# Phân biệt heap với BST và với một dãy đã sắp xếp

**Heap nhị phân (binary heap)**, **cây tìm kiếm nhị phân (binary search tree — BST)** và **dãy đã sắp xếp (sorted sequence)** đều liên quan đến thứ tự giữa các khóa. Nhưng chúng **không lưu cùng một loại thông tin về thứ tự** và cũng không tối ưu cho cùng những thao tác.

Một **min-heap** đặt khóa nhỏ nhất ở gốc và chỉ ràng buộc **cha ≤ con**. Một **BST** đặt mọi khóa trong **cây con trái** trước khóa gốc và mọi khóa trong **cây con phải** sau khóa gốc. Một **dãy tăng dần** yêu cầu **từng cặp phần tử liền kề** trong dãy theo thứ tự không giảm. Vì thế, heap thường phù hợp để **liên tục lấy phần tử ưu tiên nhất**, BST cân bằng phù hợp với **tìm kiếm và truy vấn theo thứ tự**, còn mảng đã sắp xếp phù hợp để **tra cứu nhị phân, truy cập theo vị trí và duyệt có thứ tự**.

Bài nằm trong chương **Heap và hàng đợi ưu tiên** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Theo mục tiêu của mô-đun, chúng ta sẽ xuất phát từ **bất biến**, suy ra thao tác được hỗ trợ, thời gian/bộ nhớ và cách lựa chọn cấu trúc cho từng bài toán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phát biểu chính xác bất biến của **min-heap**, **max-heap**, **BST** và **dãy đã sắp xếp**.
- Vẽ ba cách tổ chức **cùng một tập khóa**, rồi giải thích ý nghĩa từng hình vẽ.
- Nhận ra **mảng dùng để lưu heap không đồng nghĩa với mảng đã sắp xếp**.
- Giải thích tại sao **BST có thể tìm kiếm bằng cách rẽ trái/phải**, còn heap thông thường không thể áp dụng cùng quy tắc.
- Phân biệt **heap luôn có chiều cao O(log n)** với **BST thường có thể cao O(n)** nếu không cân bằng.
- So sánh **peek min/max, lấy cực trị, chèn, xóa, tìm khóa bất kỳ, truy vấn khoảng và duyệt theo thứ tự**.
- Phân biệt dãy đã sắp xếp lưu bằng **mảng động** với dãy đã sắp xếp lưu bằng **danh sách liên kết**.
- Sử dụng Python để kiểm tra bất biến và minh họa tìm kiếm trong ba cấu trúc.
- Nhận biết yêu cầu bổ sung như **khóa trùng, tính ổn định, cập nhật khóa, ID và truy vấn top-k**.
- Chọn cấu trúc phù hợp cho hàng đợi ưu tiên, danh bạ tìm kiếm, bảng tra cứu tĩnh và những tập dữ liệu có cập nhật thường xuyên.

## 2. Ba cấu trúc cùng quan tâm đến thứ tự, nhưng theo cách khác nhau

Để so sánh công bằng, xét cùng bảy khóa phân biệt:

~~~text
Tập khóa: {1, 2, 3, 4, 5, 6, 7}
~~~

Ta có thể tổ chức chúng thành:

**Min-heap:**

~~~text
             1
            / \
           3   2
          / \ / \
         7  6 5  4

Mảng biểu diễn heap theo thứ tự mức:
[1, 3, 2, 7, 6, 5, 4]
~~~

**BST cân bằng:**

~~~text
             4
            / \
           2   6
          / \ / \
         1  3 5  7

Duyệt trung thứ tự (in-order):
[1, 2, 3, 4, 5, 6, 7]
~~~

**Mảng tăng dần:**

~~~text
index:  0  1  2  3  4  5  6
value: [1, 2, 3, 4, 5, 6, 7]
~~~

Ba cấu trúc đều chứa **đúng bảy khóa**, nhưng:

- Heap có **gốc 1**, BST có **gốc 4**, mảng tăng dần không có khái niệm **gốc**.
- Mảng heap có thứ tự **[1, 3, 2, 7, 6, 5, 4]**, không tăng dần.
- Duyệt **in-order** của BST được một dãy tăng dần, nhưng duyệt theo mức của BST thì không.
- Với mảng tăng dần, thứ tự của **mọi phần tử theo chỉ số** đã được cố định.
- Không được áp dụng chung một thuật toán tìm kiếm cho cả ba cấu trúc chỉ vì chúng đều chứa số nguyên.

**Điều cần hỏi trước tiên:** Ứng dụng chỉ cần biết **ai nhỏ nhất/lớn nhất**, hay cần biết **khóa x đang ở đâu**, hay cần **liệt kê một khoảng khóa theo thứ tự**?

## 3. Heap: quan hệ giữa cha và con, không phải giữa hai nhánh

Trong **binary min-heap**, ta cần đồng thời:

1. **Hình dạng:** cây nhị phân **gần đầy đủ** (*complete binary tree*): các mức trước mức cuối đều đầy; mức cuối lấp từ trái qua phải.
2. **Thứ tự heap:** với mỗi nút khác gốc, **khóa cha ≤ khóa nút đó**.

Với **max-heap**, quan hệ thứ tự đảo thành **khóa cha ≥ khóa con**, còn yêu cầu về hình dạng vẫn giữ nguyên.

### 3.1. Ví dụ kiểm tra theo cạnh

~~~text
             1
            / \
           3   2
          / \ / \
         7  6 5  4
~~~

Trong min-heap trên:

~~~text
1 <= 3; 1 <= 2
3 <= 7; 3 <= 6
2 <= 5; 2 <= 4
~~~

Mọi cạnh cha–con đều hợp lệ.

**Không có yêu cầu** 3 ≤ 2 hoặc 7 ≤ 6; cũng không có yêu cầu mọi phần tử ở nhánh trái nhỏ hơn mọi phần tử ở nhánh phải.

### 3.2. Vì sao phần tử nhỏ nhất ở gốc?

Trên đường từ gốc tới bất kỳ nút v, ta liên tiếp gặp các cạnh **cha ≤ con**. Theo tính bắc cầu của phép so sánh:

\[
key(root)\leq key(v).
\]

Do đó, **gốc chứa một phần tử có khóa nhỏ nhất** của min-heap. Với max-heap, gốc chứa một phần tử có khóa lớn nhất.

Nhưng mệnh đề này **không đủ để tìm nhanh một khóa bất kỳ**: biết gốc nhỏ nhất không cho biết một khóa 6 nằm ở nhánh trái hay nhánh phải.

### 3.3. Heap lưu bằng mảng như thế nào?

Một binary heap thường được lưu trong mảng 0-based. Với nút chỉ số i:

~~~text
parent(i) = (i - 1) // 2, nếu i > 0
left(i)   = 2*i + 1, nếu 2*i + 1 < n
right(i)  = 2*i + 2, nếu 2*i + 2 < n
~~~

Với mảng **[1, 3, 2, 7, 6, 5, 4]**, nút 3 ở chỉ số 1 có hai con tại 3 và 4, mang khóa 7 và 6. Mảng chỉ là **cách biểu diễn cây**: chỉ số tăng từ trái sang phải theo từng mức, **không** có nghĩa giá trị tăng theo chỉ số.

**Độ cao của binary heap** luôn O(log n) vì hình dạng gần đầy đủ; điều này không phụ thuộc vào thứ tự thêm các khóa.

## 4. BST: quan hệ giữa toàn bộ cây con trái và cây con phải

Một **cây tìm kiếm nhị phân** (*binary search tree — BST*) dùng quy tắc thứ tự mạnh hơn theo **phân vùng khóa**:

- Mọi khóa trong **cây con trái** của nút x đều **nhỏ hơn khóa x**.
- Mọi khóa trong **cây con phải** của nút x đều **lớn hơn khóa x**.
- Mỗi cây con lại phải tuân theo quy tắc đó.

Ở phần minh họa này, các khóa là **phân biệt**. Nếu cho phép khóa trùng, BST phải quy định cách lưu chúng (ví dụ đếm tần suất ở một nút hoặc chọn một chính sách gán khóa bằng nhau vào một phía).

### 4.1. Bất biến áp dụng cho mọi hậu duệ, không chỉ con trực tiếp

~~~text
             4
            / \
           2   6
          / \ / \
         1  3 5  7
~~~

Với gốc 4, **tất cả** khóa bên trái {1, 2, 3} đều < 4 và **tất cả** khóa bên phải {5, 6, 7} đều > 4. Điều kiện ấy tiếp tục đúng tại nút 2 và nút 6.

Một cây có thể thỏa **con trái < cha < con phải** tại từng cạnh riêng lẻ nhưng vẫn **không phải BST** nếu một hậu duệ vi phạm ranh giới của tổ tiên.

Ví dụ sai:

~~~text
             10
            /  \
           5    15
            \
             12
~~~

Nút 12 là con phải của 5 nên 12 > 5, nhưng nó lại nằm trong **cây con trái của 10**, phải < 10. Vì 12 > 10, cấu trúc sai bất biến BST mặc dù mỗi cặp cha–con tại vị trí ấy có vẻ hợp lý.

### 4.2. Vì sao BST tìm khóa theo một đường?

Giả sử tìm khóa **6** trong BST cân bằng ở đầu bài:

~~~text
So sánh với gốc 4:
6 > 4 → bỏ qua toàn bộ cây con trái, đi phải.

Tới nút 6:
6 == 6 → tìm thấy.
~~~

Mỗi lần so sánh cho phép **loại bỏ cả một cây con**. Nếu chiều cao cây là h, tìm kiếm mất **O(h)**, không nhất thiết phải xem mọi nút.

### 4.3. Chiều cao BST có thể lớn

**BST thường không bảo đảm cân bằng.** Chèn các khóa tăng dần 1, 2, 3, 4, 5 vào một BST đơn giản, không xoay cân bằng, có thể tạo:

~~~text
1
 \
  2
   \
    3
     \
      4
       \
        5
~~~

Cây này có chiều cao **n − 1**. Tìm kiếm, chèn, xóa theo đường đi có thể tốn **Θ(n)** trong trường hợp xấu nhất.

Với **BST tự cân bằng** như AVL hoặc red-black tree, chiều cao được duy trì **O(log n)**, nhờ đó các thao tác tìm kiếm/chèn/xóa có **O(log n)** trong mô hình chuẩn.

**Không nên viết “BST luôn tìm kiếm O(log n)” mà bỏ điều kiện về chiều cao/cân bằng.** Trong khi đó, binary heap chuẩn có chiều cao O(log n) nhờ bất biến hình dạng.

## 5. Dãy đã sắp xếp: quan hệ theo vị trí liên tiếp

Một **dãy đã sắp xếp tăng dần** có khóa:

\[
a[0]\leq a[1]\leq \cdots\leq a[n-1].
\]

Nó không yêu cầu một cây gốc hay những liên kết cha–con. Ý nghĩa của cấu trúc còn phụ thuộc **cách lưu dãy**.

### 5.1. Dãy đã sắp xếp lưu bằng mảng động

~~~text
index:  0  1  2  3  4  5  6
value: [1, 2, 3, 4, 5, 6, 7]
~~~

Vì có truy cập ngẫu nhiên **a[mid]** trong O(1), ta dùng **binary search** để tìm một khóa trong **O(log n)**.

Ưu điểm khác:

- Truy cập phần tử ở chỉ số k: **O(1)**.
- Lấy khóa nhỏ nhất/lớn nhất trong dãy tăng dần: **a[0]** và **a[-1]**, đều **O(1)** khi không rỗng.
- Duyệt tăng dần: chỉ việc đi qua các ô mảng từ trái sang phải, **Θ(n)**.

Đánh đổi là **chèn hoặc xóa ở giữa/đầu mảng** thường phải dịch nhiều phần tử, tốn **O(n)** trong trường hợp xấu nhất, dù đã tìm được vị trí bằng binary search.

Ví dụ chèn khóa 0:

~~~text
Trước: [1, 2, 3, 4, 5, 6, 7]
Sau:   [0, 1, 2, 3, 4, 5, 6, 7]
~~~

Nếu giữ dãy tăng dần, tất cả bảy phần tử cũ phải dịch sang phải một vị trí.

### 5.2. Dãy đã sắp xếp lưu bằng danh sách liên kết

Một danh sách đơn có thể lưu:

~~~text
head → 1 → 2 → 3 → 4 → 5 → 6 → 7 → None
~~~

Dữ liệu vẫn **đã sắp xếp**, nhưng không có truy cập ngẫu nhiên O(1) tới phần tử giữa. Muốn tới vị trí k phải đi qua các nút trước đó.

Vì vậy:

- Tìm một khóa bằng duyệt tuần tự: **O(n)** trong trường hợp xấu nhất, dù có thể dừng sớm khi vượt khóa cần tìm.
- Sau khi **đã biết nút trước vị trí chèn**, sửa liên kết chèn có thể **O(1)**.
- Nếu chỉ biết khóa cần chèn, phải **tìm nút trước đó**, thường O(n).
- Nếu min ở head, lấy/xóa đầu là **O(1)** khi cấu trúc giữ head.

**Điểm then chốt:** “Dãy đã sắp xếp” mô tả **thứ tự dữ liệu**; còn mảng và danh sách liên kết quyết định **chi phí truy cập và di chuyển**. Không được áp dụng O(log n) của binary search trên mảng cho một danh sách liên kết đơn thông thường.

## 6. Đối chiếu cùng một tập khóa bằng ba hình ảnh

Sử dụng các khóa 1 đến 7 để xem từng loại đang bảo đảm điều gì:

| Câu hỏi | Min-heap | BST cân bằng | Mảng đã sắp xếp |
| --- | --- | --- | --- |
| Phần tử nhỏ nhất nằm ở đâu? | **Gốc: 1** | **Nút trái nhất: 1** | **Đầu mảng: 1** |
| Phần tử lớn nhất nằm ở đâu? | Có thể ở một trong các lá | Nút phải nhất | Cuối mảng |
| Có quy tắc rẽ trái/phải để tìm x? | **Không** | **Có** | Dùng nửa trái/phải theo chỉ số |
| Duyệt theo thứ tự mức có sắp không? | Không | Không | Không áp dụng |
| Duyệt in-order có luôn sắp không? | **Không** | **Có** (theo chính sách khóa trùng) | Không cần cây |
| Có bảo đảm dạng cây gần đầy đủ? | **Có** | Không bắt buộc | Không có cây |
| Có thể chứa khóa trùng? | Có | Có nếu định nghĩa chính sách | Có |
| Mục tiêu nổi bật | Lấy cực trị liên tục | Tìm và truy vấn theo thứ tự | Tìm nhị phân và duyệt/truy cập theo chỉ số |

### 6.1. In-order của heap không tự tăng dần

Với heap:

~~~text
             1
            / \
           3   2
          / \ / \
         7  6 5  4
~~~

Duyệt **trái → gốc → phải** cho:

~~~text
[7, 3, 6, 1, 5, 2, 4]
~~~

Kết quả **không được sắp**. In-order chỉ trả kết quả tăng dần khi **bất biến BST** có hiệu lực, không phải chỉ vì cấu trúc là cây nhị phân.

### 6.2. Mảng heap theo thứ tự mức cũng không tăng dần

Mảng biểu diễn cùng heap:

~~~text
[1, 3, 2, 7, 6, 5, 4]
~~~

Dù khóa nhỏ nhất ở đầu, các phần tử sau đó **không theo thứ tự ưu tiên toàn cục**. Đây là lỗi suy luận thường gặp khi thấy heap được lưu trong mảng.

### 6.3. Có thể có nhiều heap hợp lệ cho cùng một tập khóa

Ví dụ, cả hai mảng sau có thể là min-heap của cùng tập khóa:

~~~text
[1, 3, 2, 7, 6, 5, 4]
[1, 2, 3, 4, 5, 6, 7]
~~~

Mảng thứ hai tình cờ tăng dần **và** thỏa min-heap, nhưng điều này **không bắt buộc**. Thuật toán heapify chỉ cần tạo một hoán vị thỏa bất biến cha ≤ con.

## 7. Tìm một khóa bất kỳ: vì sao heap không hỗ trợ binary search?

Giả sử cần tìm khóa **6**.

### 7.1. Trong min-heap

~~~text
a = [1, 3, 2, 7, 6, 5, 4]
                     ▲
                  khóa 6 ở i=4
~~~

Chỉ biết gốc 1 ≤ 6 **không cho biết** 6 nằm ở nhánh trái hay phải. Các khóa bên trái và bên phải **không được phân vùng như BST**.

Nếu không có chỉ mục phụ, cách đơn giản là quét mảng từ đầu đến cuối, tốn **O(n)** trong trường hợp xấu nhất.

**Có thể cắt tỉa một số nhánh:** Trong min-heap, nếu đang tìm khóa x và một nút có khóa **> x**, toàn bộ hậu duệ của nút đó cũng **≥ khóa nút > x**; có thể bỏ qua nhánh ấy. Tuy nhiên, khi nhiều nút có khóa ≤ x, thuật toán vẫn có thể phải thăm **Θ(n)** nút. Cắt tỉa không biến tìm kiếm tổng quát thành O(log n).

### 7.2. Trong BST cân bằng

~~~text
Tìm 6:
4 → 6
~~~

Vì 6 > 4, ta bỏ hẳn cây con trái của gốc. Với cây cân bằng chiều cao O(log n), tìm kiếm tốn **O(log n)**.

Nếu BST bị lệch thành một chuỗi, vẫn có thể phải đi qua Θ(n) nút.

### 7.3. Trong mảng tăng dần

~~~text
a = [1, 2, 3, 4, 5, 6, 7]
     0  1  2  3  4  5  6  (chỉ số)

mid = 3, a[3] = 4 < 6 → giữ nửa phải
mid = 5, a[5] = 6     → tìm thấy
~~~

Truy cập được phần tử giữa trong O(1) và loại bỏ một nửa khoảng mỗi lượt, nên **binary search O(log n)**. Nếu chỉ có danh sách liên kết thay vì mảng, việc đi tới nút ở giữa mất thời gian; không thể mặc nhiên đạt cùng chi phí.

## 8. Truy cập cực trị: heap phát huy thế mạnh

### 8.1. Xem phần tử nhỏ nhất

| Cấu trúc | Cách tìm min | Thời gian |
| --- | --- | --- |
| Min-heap | Đọc gốc a[0] | **Θ(1)** |
| BST cân bằng | Đi liên tục sang trái | **O(log n)** |
| Mảng tăng dần | Đọc a[0] | **Θ(1)** |
| Danh sách liên kết tăng dần | Đọc head | **Θ(1)** |

BST có thể giữ thêm con trỏ tới nút nhỏ nhất để hỗ trợ peek min O(1), nhưng đó là **metadata bổ sung**, phải được duy trì khi chèn/xóa.

### 8.2. Lấy và xóa phần tử nhỏ nhất

Trong **min-heap**:

1. Lưu entry gốc làm kết quả.
2. Đưa entry cuối mảng lên gốc và xóa ô cuối.
3. Dùng **sift-down** để khôi phục thứ tự heap.

Độ phức tạp **O(log n)** theo mô hình heap.

Ví dụ:

~~~text
Trước: [1, 3, 2, 7, 6, 5, 4]
pop min → trả 1

Đưa 4 cuối lên gốc:
[4, 3, 2, 7, 6, 5]

Sift-down chọn con 2:
[2, 3, 4, 7, 6, 5]

Sau: [2, 3, 4, 7, 6, 5]
~~~

Trong **BST cân bằng**, xóa min đi theo đường tới **nút trái nhất**, nối lại cây rồi cân bằng nếu cần: **O(log n)**.

Trong **mảng tăng dần** với min ở đầu, thao tác loại bỏ phần tử đầu phải dịch các phần tử còn lại sang trái, **Θ(n)**. Nếu lưu dãy **giảm dần** để min ở cuối, xóa min tại cuối có thể O(1); tuy nhiên, những thao tác chèn vào vị trí giữa và các cực trị khác cần được phân tích lại theo quy ước này.

Trong **danh sách liên kết tăng dần**, min ở head nên xóa đầu có thể **O(1)**.

### 8.3. Xem max trong min-heap

Min-heap bảo đảm **min ở gốc**, **không** bảo đảm max có một vị trí xác định dễ truy cập. Max có thể xuất hiện ở một lá, nhưng nếu không có chỉ mục khác, để tìm max phải xét các ứng viên ở các lá, tốn **O(n)** trong trường hợp xấu nhất.

BST cân bằng có thể tìm max bằng cách đi theo nhánh phải trong O(log n); mảng tăng dần đọc phần tử cuối O(1). Nếu công việc chủ yếu cần max, cân nhắc **max-heap** thay vì min-heap.

## 9. Thêm phần tử: ba cách trả giá cho việc giữ thứ tự

Giả sử đang có các khóa 1 đến 7 và cần thêm khóa **0**.

### 9.1. Push vào min-heap: O(log n)

~~~text
Trước:
[1, 3, 2, 7, 6, 5, 4]

Append cuối:
[1, 3, 2, 7, 6, 5, 4, 0]

Sift-up: đổi 0 với 7 (cha i=3):
[1, 3, 2, 0, 6, 5, 4, 7]

Đổi 0 với 3 (cha i=1):
[1, 0, 2, 3, 6, 5, 4, 7]

Đổi 0 với 1 (gốc):
[0, 1, 2, 3, 6, 5, 4, 7]
~~~

Sau thao tác, heap vẫn gần đầy đủ và mọi cha ≤ con. **Sift-up** đi tối đa O(log n) mức; số entry tăng đúng một.

### 9.2. Chèn vào BST cân bằng: O(log n)

Để thêm 0 vào BST, so sánh từ gốc 4, đi trái tới 2, tiếp tục trái tới 1 rồi chèn 0 vào bên trái 1. Một BST tự cân bằng có thể cần **xoay hoặc tái cân bằng** sau chèn, nhưng độ cao và thời gian thao tác vẫn O(log n).

Nếu dùng BST thường không cân bằng, một lần chèn có thể tốn Θ(n) ở cây dạng chuỗi.

### 9.3. Chèn vào mảng tăng dần: O(n)

Đầu tiên có thể tìm vị trí chèn bằng binary search O(log n), sau đó phải dịch các phần tử:

~~~text
Trước: [1, 2, 3, 4, 5, 6, 7]
Sau:   [0, 1, 2, 3, 4, 5, 6, 7]
~~~

Có bảy phần tử cũ phải dịch sang phải. Vì vậy tổng thời gian trường hợp xấu nhất vẫn **Θ(n)**.

Nếu chèn vào **cuối** mảng tăng dần (khóa mới lớn nhất), append có thể O(1) khấu hao; nhưng không phải mọi lần chèn đều nằm cuối.

### 9.4. Chèn vào danh sách liên kết tăng dần

Nếu đã có tham chiếu tới **nút đứng trước vị trí chèn**, phần sửa next có thể O(1). Tuy nhiên, nếu chỉ biết khóa 0, phải xác định vị trí thích hợp. Trường hợp chèn đầu có thể O(1), còn trường hợp xấu nhất khi duyệt tìm vị trí là **O(n)**.

**Kết luận:** Heap thường cân bằng chi phí push/pop cực trị; BST cân bằng thích hợp khi còn cần tìm kiếm; mảng tăng dần thích hợp khi việc đọc/tra cứu nhiều hơn việc sửa ở giữa.

## 10. Duyệt theo thứ tự tăng dần: ba cách khác nhau

### 10.1. Min-heap

Nếu duyệt các ô trong mảng heap hoặc duyệt in-order cây heap, kết quả **không chắc tăng dần**.

Để lấy tất cả khóa theo thứ tự tăng dần, có thể:

1. Xây min-heap bằng **heapify Θ(n)** nếu đầu vào chưa là heap.
2. Lặp **n lần pop min**.
3. Mỗi lần pop O(log n), nên tổng O(n log n).

Cách pop trực tiếp sẽ **làm rỗng heap**; nếu cần giữ heap gốc, phải tạo bản sao (O(n) bộ nhớ bổ sung) hoặc dùng thuật toán không phá hủy có quy tắc riêng.

### 10.2. BST

Duyệt **in-order** (*trái → nút → phải*) của BST tạo ra dãy khóa tăng dần theo chính sách khóa trùng.

~~~text
             4
            / \
           2   6
          / \ / \
         1  3 5  7

In-order:
1, 2, 3, 4, 5, 6, 7
~~~

Duyệt đủ n nút có chi phí **Θ(n)**. Nếu đệ quy, ngăn xếp cần O(h) bộ nhớ, với h là chiều cao cây; trên BST cân bằng h = O(log n), nhưng trên BST lệch có thể O(n).

### 10.3. Mảng tăng dần

Chỉ cần đi từ a[0] đến a[n − 1], chi phí **Θ(n)** thời gian, O(1) bộ nhớ phụ nếu xử lý từng phần tử và không tạo bản sao kết quả.

Nếu đây là danh sách liên kết tăng dần, duyệt theo next từ head cũng Θ(n).

**Không nhầm lẫn:** BST đảm bảo **in-order tăng dần**, heap đảm bảo **gốc cực trị**, còn mảng đã sắp xếp đảm bảo **thứ tự vị trí trong dãy**.

## 11. Truy vấn khoảng, predecessor/successor và thứ hạng

Nhu cầu “lấy phần tử nhỏ nhất” khác rất xa nhu cầu “liệt kê mọi khóa từ 20 đến 40”.

### 11.1. Truy vấn khoảng khóa

Cho khoảng **[lo, hi]** và giả sử kết quả có k entry:

- **Min-heap:** Không tổ chức toàn bộ các khóa theo khoảng hay trái/phải; trong trường hợp xấu nhất phải xét Θ(n) entry. Có thể cắt tỉa nhánh khi khóa gốc nhánh > hi, nhưng không có bảo đảm O(log n + k) tổng quát.
- **BST cân bằng:** Có thể đi tới vị trí thấp nhất rồi duyệt có thứ tự, bỏ qua những cây con ngoài khoảng. Thời gian điển hình **O(log n + k)**.
- **Mảng tăng dần:** Tìm vị trí đầu tiên ≥ lo bằng binary search O(log n), rồi đọc liên tục k phần tử, tổng **O(log n + k)**.
- **Danh sách liên kết tăng dần:** Nếu không có chỉ mục bổ sung, thường phải đi từ head tới điểm bắt đầu, O(n) trường hợp xấu nhất, sau đó đọc k phần tử.

### 11.2. Predecessor và successor

Với khóa x:

- **Predecessor:** khóa lớn nhất **< x**.
- **Successor:** khóa nhỏ nhất **> x**.

BST cân bằng và mảng tăng dần hỗ trợ tìm các giá trị này trong O(log n) với thuật toán thích hợp. Heap không có quan hệ thứ tự trái/phải đủ mạnh; nếu không thêm chỉ mục, truy vấn tổng quát có thể mất O(n).

### 11.3. Phần tử nhỏ thứ k

Mảng tăng dần trả phần tử ở chỉ số k − 1 trong **O(1)** (nếu k hợp lệ và có truy cập ngẫu nhiên).

BST **không tự động** hỗ trợ truy vấn phần tử nhỏ thứ k trong O(log n); cần bổ sung **số nút của mỗi cây con** (*order-statistic tree*) hoặc dùng cách duyệt tốn thời gian hơn.

Min-heap cũng **không tự động** trả phần tử nhỏ thứ k trong O(1). Có thể lấy k lần pop, dùng thuật toán lựa chọn khác hoặc thêm cấu trúc hỗ trợ.

## 12. Chiều cao và hình dạng cây: khác biệt thiết kế quyết định chi phí

### 12.1. Heap nhị phân luôn gần đầy đủ

Dù bạn thêm khóa tăng dần, giảm dần hay theo thứ tự ngẫu nhiên, binary heap lưu mảng luôn lấp các vị trí của cây theo thứ tự mức.

Với n ≥ 1, chiều cao tính theo số cạnh là:

\[
h=\lfloor\log_2 n\rfloor.
\]

Sift-up/sift-down chỉ đi dọc một đường, nên có O(log n) mức.

### 12.2. BST thường không tự cân bằng

BST chỉ quy định **thứ tự khóa giữa các cây con**, không ép cây phải gần đầy đủ. Một cây gồm n nút có thể có chiều cao từ Θ(log n) đến Θ(n).

Ví dụ chuỗi tăng dần khi chèn vào BST thường:

~~~text
1 → 2 → 3 → 4 → 5 → 6 → 7
    (liên kết con phải liên tiếp)
~~~

Cây vẫn là BST hợp lệ nhưng tìm khóa 7 phải đi qua bảy nút.

**BST tự cân bằng** bổ sung bất biến chiều cao/độ cân bằng và dùng phép xoay để giữ h = O(log n). Đây là sự khác biệt giữa **ADT/search-order** và một cài đặt cân bằng cụ thể.

### 12.3. Mảng đã sắp xếp không có chiều cao

Mảng tăng dần không phải cây, nên không có khái niệm chiều cao hoặc xoay nút. Nó khai thác **truy cập ngẫu nhiên O(1)** để binary search, nhưng phải **dịch entry** khi sửa một vị trí giữa.

**Cùng một kết quả O(log n) khi tìm kiếm không có nghĩa cấu trúc giống nhau:** BST cân bằng thu hẹp một **cây con**, còn binary search trên mảng thu hẹp một **khoảng chỉ số**.

## 13. Bảng so sánh chi phí trong mô hình chuẩn

Giả định có n entry; phép so sánh khóa mất O(1); **BST trong bảng là BST tự cân bằng**. Với dãy đã sắp xếp, tách riêng **mảng động tăng dần** và **danh sách liên kết đơn tăng dần** để tránh nhập nhằng.

| Thao tác | Min-heap nhị phân | BST cân bằng | Mảng tăng dần | Danh sách liên kết tăng dần |
| --- | --- | --- | --- | --- |
| Xem khóa nhỏ nhất | **O(1)** | O(log n) | **O(1)** | **O(1)** nếu min ở head |
| Lấy/xóa min | O(log n) | O(log n) | **O(n)** vì dịch ô | **O(1)** xóa head |
| Thêm một khóa | O(log n) | O(log n) | **O(n)** trường hợp xấu nhất | **O(n)** để tìm vị trí |
| Tìm khóa x bất kỳ | **O(n)** | **O(log n)** | **O(log n)** | **O(n)** |
| Tìm min và max | Min O(1), max O(n) | Cả hai O(log n) | Cả hai O(1) | Min O(1), max O(n) nếu không lưu tail |
| Truy vấn khoảng, trả k entry | O(n) trường hợp xấu nhất | O(log n + k) | O(log n + k) | O(n + k) trường hợp xấu nhất |
| Duyệt n entry theo thứ tự tăng | O(n log n) bằng pop | **Θ(n)** in-order | **Θ(n)** | **Θ(n)** |
| Truy cập entry tại chỉ số k đã biết | O(1) đọc ô k, **không có thứ hạng k** | O(log n) nếu tăng cường size cây con | **O(1)**, đúng thứ hạng | **O(k + 1)** |
| Xây từ n khóa chưa sắp | **Θ(n)** heapify | O(n log n) bằng n chèn cân bằng | O(n log n) trường hợp xấu nhất bằng sort so sánh | O(n log n) bằng merge sort liên kết |
| Bộ nhớ lưu n entry | O(n) | O(n) | O(n) | O(n) |

**Cách đọc bảng:** Các mức O(n) là cận trên/trường hợp xấu nhất cho thao tác tương ứng; một trường hợp cụ thể có thể dừng sớm. Với mảng động, append và việc thay đổi sức chứa có chi phí **khấu hao**, nên mô hình O(log n) của push heap giả định append O(1) khấu hao.

### 13.1. Một số điều kiện cần ghi rõ

- Với **BST thường không cân bằng**, thay O(log n) bằng **O(h)**, trong đó h có thể đạt Θ(n).
- Với **BST có con trỏ tới min/max được duy trì**, peek cực trị có thể O(1), nhưng chèn/xóa phải cập nhật metadata.
- Với **mảng được sắp giảm dần**, min ở cuối và xóa min có thể O(1), còn các chi phí khác tùy thao tác và quy ước; bảng dùng **mảng tăng dần**.
- Với **danh sách liên kết**, sau khi đã có tham chiếu đúng tới nút trước vị trí chèn/xóa, sửa liên kết có thể O(1), nhưng **tìm vị trí** không tự là O(1).
- Với **heap**, nếu ứng dụng duy trì một **bảng băm ID → vị trí**, truy cập entry theo ID có thể nhanh hơn, nhưng phải cập nhật bảng mỗi lần heap hoán đổi.
- Nếu dữ liệu **đã sắp xếp sẵn**, có thể xây BST cân bằng từ dãy đã sắp trong **Θ(n)** và mảng không cần chạy sort lại.

## 14. Ví dụ Python tự chứa: kiểm tra ba bất biến

Phần này dùng khóa nguyên **phân biệt**, để minh họa BST với quy tắc trái < gốc < phải. Các lớp và hàm bên dưới dùng được với Python 3.10 trở lên.

### 14.1. Phát hiện min-heap và mảng tăng dần

~~~python
def is_min_heap(a: list[int]) -> bool:
    """Mảng a có thỏa bất biến cha <= con không?"""
    for i in range(1, len(a)):
        parent = (i - 1) // 2
        if a[parent] > a[i]:
            return False
    return True


def is_sorted_ascending(a: list[int]) -> bool:
    """Dãy không giảm, cho phép khóa bằng nhau."""
    for i in range(1, len(a)):
        if a[i - 1] > a[i]:
            return False
    return True


heap_array = [1, 3, 2, 7, 6, 5, 4]
sorted_array = [1, 2, 3, 4, 5, 6, 7]

assert is_min_heap(heap_array)
assert not is_sorted_ascending(heap_array)

assert is_min_heap(sorted_array)
assert is_sorted_ascending(sorted_array)

assert is_min_heap([])
assert is_sorted_ascending([])
assert is_min_heap([7])
assert is_sorted_ascending([7])
~~~

Ví dụ trên còn chứng minh một điều dễ gây nhầm lẫn: **mảng đã tăng dần cũng có thể thỏa min-heap**, nhưng không vì thế mà **mọi min-heap đều tăng dần**. Điều kiện heap yếu hơn điều kiện sắp tăng dần theo chỉ số.

### 14.2. Xây một BST cân bằng từ dãy tăng dần

~~~python
class BSTNode:
    def __init__(self, key: int):
        self.key = key
        self.left: BSTNode | None = None
        self.right: BSTNode | None = None


def build_balanced_bst(keys: list[int]) -> BSTNode | None:
    """Yêu cầu keys tăng nghiêm ngặt (khóa phân biệt)."""
    def build(lo: int, hi: int) -> BSTNode | None:
        if lo >= hi:
            return None

        mid = (lo + hi) // 2
        root = BSTNode(keys[mid])
        root.left = build(lo, mid)
        root.right = build(mid + 1, hi)
        return root

    return build(0, len(keys))


def bst_inorder(root: BSTNode | None) -> list[int]:
    result = []

    def visit(node):
        if node is None:
            return
        visit(node.left)
        result.append(node.key)
        visit(node.right)

    visit(root)
    return result


def is_valid_bst(root: BSTNode | None) -> bool:
    """Kiểm tra toàn bộ miền khóa tổ tiên, không chỉ con trực tiếp."""
    def valid(node, low, high):
        if node is None:
            return True
        if low is not None and node.key <= low:
            return False
        if high is not None and node.key >= high:
            return False

        return (
            valid(node.left, low, node.key)
            and valid(node.right, node.key, high)
        )

    return valid(root, None, None)


root = build_balanced_bst([1, 2, 3, 4, 5, 6, 7])

assert root is not None and root.key == 4
assert root.left.key == 2
assert root.right.key == 6
assert is_valid_bst(root)
assert bst_inorder(root) == [1, 2, 3, 4, 5, 6, 7]

# Một ví dụ vi phạm ranh giới của tổ tiên.
bad_root = BSTNode(10)
bad_root.left = BSTNode(5)
bad_root.left.right = BSTNode(12)
assert not is_valid_bst(bad_root)
~~~

Hàm xây BST ở đây nhận **dãy đã tăng nghiêm ngặt**, chọn phần tử giữa làm gốc rồi tạo hai cây con. Vì không sao chép các lát cắt trong lúc đệ quy, xây **n nút trong Θ(n) thời gian**, dùng **O(n) bộ nhớ cho nút** và O(log n) ngăn xếp đệ quy khi cây cân bằng. Mã chỉ dùng để minh họa: đây không phải một lớp BST tự cân bằng sau những lần chèn/xóa tùy ý.

## 15. Python: so sánh tìm kiếm theo khóa

Ba hàm sau dùng các cấu trúc ở mục trước.

~~~python
from bisect import bisect_left


def search_heap_array(a: list[int], target: int):
    """Quét đơn giản; trả (index hoặc None, số entry đã xem)."""
    checked = 0
    for index, value in enumerate(a):
        checked += 1
        if value == target:
            return index, checked
    return None, checked


def search_sorted_array(a: list[int], target: int):
    """Yêu cầu a tăng dần; tìm vị trí đầu tiên của target."""
    index = bisect_left(a, target)
    if index < len(a) and a[index] == target:
        return index
    return None


def search_bst(root: BSTNode | None, target: int):
    """Trả (node hoặc None, số nút đã xem)."""
    current = root
    checked = 0

    while current is not None:
        checked += 1
        if target == current.key:
            return current, checked

        if target < current.key:
            current = current.left
        else:
            current = current.right

    return None, checked


heap_array = [1, 3, 2, 7, 6, 5, 4]
sorted_array = [1, 2, 3, 4, 5, 6, 7]
bst_root = build_balanced_bst(sorted_array)

heap_position, heap_steps = search_heap_array(heap_array, 6)
bst_node, bst_steps = search_bst(bst_root, 6)

assert heap_position == 4
assert heap_steps == 5           # Quét 1, 3, 2, 7, rồi 6.
assert bst_node is not None and bst_node.key == 6
assert bst_steps == 2            # Đi qua nút 4 rồi nút 6.
assert search_sorted_array(sorted_array, 6) == 5

# Không tìm thấy.
assert search_heap_array(heap_array, 99) == (None, 7)
assert search_bst(bst_root, 99)[0] is None
assert search_sorted_array(sorted_array, 99) is None

# Rỗng.
assert search_heap_array([], 1) == (None, 0)
assert search_bst(None, 1) == (None, 0)
assert search_sorted_array([], 1) is None
~~~

**Phạm vi ví dụ:** Hàm search_heap_array cố ý quét tuần tự để làm rõ độ phức tạp O(n) tổng quát; một số trường hợp có thể tận dụng bất biến min-heap để cắt tỉa nhánh, nhưng không có bảo đảm O(log n).

Hàm search_sorted_array giả định mảng **đã được sắp tăng dần**. Nếu truyền mảng heap chưa sắp vào binary search, kết quả có thể sai hoặc bỏ sót phần tử dù khóa vẫn tồn tại.

## 16. Python: đối chiếu thêm và lấy min

Bản chất hiệu năng khác nhau thể hiện rõ ở các thao tác cập nhật.

~~~python
import heapq
from bisect import insort


initial_heap = [1, 3, 2, 7, 6, 5, 4]
initial_sorted = [1, 2, 3, 4, 5, 6, 7]

heap_copy = initial_heap.copy()
sorted_copy = initial_sorted.copy()

# Thêm khóa 0 vào min-heap.
heapq.heappush(heap_copy, 0)
assert is_min_heap(heap_copy)
assert heap_copy[0] == 0
assert len(heap_copy) == 8

# Thêm khóa 0 vào mảng đang tăng dần.
insort(sorted_copy, 0)
assert sorted_copy == [0, 1, 2, 3, 4, 5, 6, 7]
assert is_sorted_ascending(sorted_copy)

# Hai cấu trúc đều trả min là 0, nhưng bằng cơ chế khác nhau.
assert heapq.heappop(heap_copy) == 0
assert sorted_copy.pop(0) == 0

assert is_min_heap(heap_copy)
assert sorted_copy == initial_sorted
assert sorted(heap_copy) == initial_sorted

# Muốn lấy toàn bộ theo thứ tự từ heap, phải pop lần lượt.
result = [heapq.heappop(heap_copy) for _ in range(len(heap_copy))]
assert result == initial_sorted
assert heap_copy == []
~~~

**Đọc chi phí đúng cách:**

- **heapq.heappush**: sửa trên một đường cha–con O(log n), append mảng động có chi phí O(1) khấu hao.
- **bisect.insort**: tìm vị trí O(log n) nhưng **chèn/dịch phần tử** trong list O(n) trường hợp xấu nhất.
- **heapq.heappop**: sửa heap bằng sift-down O(log n) theo mô hình chuẩn.
- **list.pop(0)**: phải dịch các entry còn lại, **O(n)**.
- **Lấy tất cả bằng n lần heappop**: **O(n log n)**, không phải O(n).

Các ví dụ Python sử dụng **cấu trúc lưu mảng**, không chứng minh rằng mọi BST có thời gian O(log n). Cần phân biệt BST thường và BST tự cân bằng.

## 17. Khóa trùng, ID, tính ổn định và cập nhật khóa

### 17.1. Khóa trùng

Heap cho phép nhiều entry có **cùng khóa ưu tiên**. Min-heap chỉ đòi hỏi **cha ≤ con**, nên hai khóa bằng nhau hợp lệ.

Với BST, chính sách khóa trùng phải được định nghĩa:

- Lưu **số lần xuất hiện** ở một nút.
- Lưu danh sách payload có cùng khóa ở một nút.
- Hoặc quy định đưa khóa bằng nhau về một phía, đồng thời bảo đảm bất biến nhất quán.

Mảng tăng dần cũng có thể lưu nhiều phần tử trùng nhau và dùng **bisect_left/bisect_right** để xác định vùng các khóa bằng nhau.

### 17.2. Tính ổn định khác thứ tự khóa

Trong hàng đợi ưu tiên, hai công việc cùng priority có thể được lấy theo thứ tự bất kỳ nếu ADT không quy định tính ổn định (*stability*).

Nếu muốn **FIFO khi hòa priority**, thường dùng khóa so sánh:

~~~text
(priority, sequence_number, payload)
~~~

Trong đó **sequence_number** là số thứ tự tăng dần và duy nhất cho mỗi lần thêm. Heap so sánh hai thành phần đầu trước; payload không cần so sánh.

BST và dãy đã sắp xếp cũng cần một quy tắc cho **entry có khóa bằng nhau**, nhưng hành vi ổn định của một thao tác sắp xếp hoặc thứ tự lặp không tự động giống hành vi của priority queue.

### 17.3. Tìm một công việc theo ID

Khóa priority cho biết **ai được phục vụ trước**; ID cho biết **đó là công việc nào**. Heap không cho vị trí nhanh của một ID bất kỳ nếu không lưu thêm cấu trúc như **bảng băm ID → chỉ số heap**.

Nếu dùng bảng chỉ số, phải cập nhật nó mỗi lần **sift-up/sift-down** hoán đổi entry. Nếu chỉ sửa priority trong payload mà không tổ chức lại heap, bất biến có thể sai.

BST có thể được đánh chỉ mục theo ID hoặc theo priority tùy nghiệp vụ; nếu cây được sắp theo priority, tìm ID tùy ý cũng **không tự có O(log n)**. Không nên lẫn **khóa dùng tổ chức cấu trúc** với những trường khác của payload.

## 18. Lựa chọn cấu trúc cho từng bài toán

### 18.1. Lập lịch công việc hoặc xử lý sự kiện

Một hệ thống liên tục:

~~~text
thêm công việc mới
      ↓
xem công việc ưu tiên nhất
      ↓
lấy công việc ưu tiên nhất
      ↓
thêm công việc tiếp theo
~~~

Đây là tải công việc phù hợp với **min-heap/max-heap**, vì peek O(1), push/pop O(log n). Nếu có sẵn một lô n công việc, có thể xây binary heap bằng **bottom-up heapify Θ(n)** rồi tiếp tục push/pop.

### 18.2. Danh bạ hoặc tập bản ghi cần tìm theo khóa

Nếu cần liên tục **tìm khóa x, thêm/xóa x, tìm predecessor/successor, liệt kê khóa trong khoảng**, **BST tự cân bằng** là ứng viên phù hợp: tìm kiếm/chỉnh sửa O(log n), truy vấn khoảng O(log n + k).

Không nên dùng heap chỉ vì nó “có cấu trúc cây”; heap thiếu quy tắc phân vùng khóa như BST.

### 18.3. Tập dữ liệu chủ yếu đọc, ít cập nhật

Nếu một bảng khóa ít thay đổi nhưng tra cứu nhiều lần, **mảng tăng dần** có thể rất phù hợp: binary search O(log n), truy cập theo chỉ số O(1), duyệt toàn bộ Θ(n).

Đánh đổi là chèn/xóa giữa mảng O(n). Nếu liên tục thêm/xóa bản ghi, hãy cân nhắc BST cân bằng hoặc cấu trúc khác.

### 18.4. Cần xuất dữ liệu luôn theo thứ tự

Nếu API thường xuyên trả về **toàn bộ khóa tăng dần**, BST duyệt in-order hoặc mảng tăng dần có thể tự nhiên hơn heap. Heap có thể lấy dần min bằng pop nhưng mỗi lần pop sửa cấu trúc, tổng chi phí cao hơn.

### 18.5. Cần top-k hay cực trị động

Với luồng dữ liệu rất lớn và chỉ cần giữ **k phần tử lớn nhất**, một **min-heap kích thước k** thường hữu ích: phần tử nhỏ nhất trong tập top-k nằm ở gốc, dễ thay thế khi xuất hiện khóa lớn hơn. Chi phí cập nhật theo luồng có thể là O(log k) cho mỗi phần tử cần vào top-k, thay vì giữ toàn bộ dữ liệu luôn sắp xếp.

Nhưng nếu mục tiêu là **tìm một khóa trong khoảng** hoặc **truy vấn thứ hạng bất kỳ**, BST tăng cường metadata hay mảng sắp xếp có thể thuận tiện hơn.

## 19. Những lỗi thường gặp

| Nhầm lẫn | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “Heap là một mảng đã sắp xếp” | Mảng heap chỉ theo thứ tự mức của cây | Chỉ yêu cầu **cha ≤ con** trong min-heap |
| “Gốc BST luôn là min/max” | Gốc phụ thuộc hình dạng cây | Min ở **nút trái nhất**, max ở **nút phải nhất** |
| “Có thể binary search trên mảng heap” | Các khóa không tăng theo chỉ số | Tìm tùy ý có thể O(n) |
| “BST chỉ cần so sánh hai con trực tiếp” | Hậu duệ có thể vi phạm ranh giới tổ tiên | Kiểm tra **toàn bộ cây con** |
| “Duyệt in-order của mọi cây nhị phân sẽ tăng” | Cần bất biến BST | Heap không bảo đảm in-order tăng |
| “BST luôn O(log n)” | BST đơn giản có thể thành chuỗi | Dùng BST tự cân bằng để bảo đảm chiều cao |
| “Heap có thể bị lệch thành chuỗi như BST” | Binary heap ép hình dạng gần đầy đủ | Chiều cao heap luôn O(log n) |
| “Dữ liệu sorted luôn tìm O(log n)” | Danh sách liên kết thiếu truy cập giữa O(1) | O(log n) áp dụng cho **mảng** với binary search |
| “Chèn vào sorted array O(log n)” | Tìm vị trí nhanh nhưng phải dịch ô | Chèn trường hợp xấu nhất O(n) |
| “Lấy min từ sorted array tăng dần O(1)” | Đọc min O(1), xóa đầu phải dịch các phần tử | **Peek O(1)**, **extract O(n)** |
| “Peek min của BST cân bằng luôn O(1)” | Phải đi tới nút trái nhất nếu không giữ con trỏ min | O(log n), trừ khi có metadata |
| “Heap hỗ trợ tìm predecessor nhanh” | Không phân vùng khóa theo hai nhánh | Có thể phải xét nhiều nút |
| “Heapify là sort” | Heapify chỉ dựng bất biến heap | Muốn tăng dần cần thêm pop/sort |
| “Chỉ khóa gốc nhỏ nhất là đủ” | Cặp cha–con sâu có thể sai | Kiểm tra mọi cạnh |
| “Có cùng khóa là cùng một entry” | Priority không phải ID | Dùng ID/handle và chính sách khóa trùng |
| “Heap tự bảo đảm FIFO khi khóa bằng nhau” | Bất biến không quy định thứ tự hòa | Dùng sequence khi cần |
| “Bất cứ BST nào đều cân bằng” | BST có thể cao Θ(n) | Phân biệt BST thường và AVL/red-black |
| “Dùng heap cho mọi truy vấn có thứ tự” | Heap chuyên lấy cực trị, không chuyên khoảng/thứ hạng | Chọn theo tập thao tác cần thiết |

**Quy trình tự kiểm tra:** Với cùng một tập khóa, vẽ min-heap, BST và mảng tăng dần. Tự hỏi (1) hình dạng có đúng không, (2) bất biến nào cho phép bỏ qua dữ liệu, (3) thao tác có phải dịch ô hoặc đi qua nút không, (4) nếu dữ liệu bị cập nhật thì cấu trúc phục hồi bất biến như thế nào.

## 20. Bài tập tự luyện có đáp án

**Bài 1 — Nhận diện min-heap.** Mảng [1, 3, 2, 7, 6, 5, 4] có phải min-heap không? Nó có tăng dần không?

*Đáp án:* **Có** min-heap vì mọi cha ≤ con; **không** tăng dần vì 3 > 2 và 7 > 6.

**Bài 2 — BST có gốc gì?** Với BST cân bằng chứa {1, 2, 3, 4, 5, 6, 7} như ví dụ, gốc là khóa nào?

*Đáp án:* **4**. Min **1** nằm ở nút trái nhất; max **7** ở nút phải nhất.

**Bài 3 — In-order.** In-order của BST ví dụ cho dãy nào? In-order của heap ví dụ có tăng dần không?

*Đáp án:* BST cho **[1, 2, 3, 4, 5, 6, 7]**. Heap cho **[7, 3, 6, 1, 5, 2, 4]**, không tăng dần.

**Bài 4 — Tìm khóa 6.** Vì sao BST có thể chọn ngay nhánh phải từ gốc 4 khi tìm 6, còn heap gốc 1 không cho biết phải chọn nhánh nào?

*Đáp án:* BST quy định **toàn bộ cây con trái < 4 < toàn bộ cây con phải**, nên loại được nửa trái. Heap chỉ quy định **cha ≤ con**, không so sánh toàn bộ hai nhánh.

**Bài 5 — Binary search.** Có được chạy binary search trực tiếp trên mảng heap [1, 3, 2, 7, 6, 5, 4] để tìm 6 không?

*Đáp án:* **Không**. Binary search yêu cầu mảng được sắp theo thứ tự khóa; mảng heap chỉ tuân theo thứ tự cha–con.

**Bài 6 — Mảng tăng dần.** Tìm khóa 6 trong [1, 2, 3, 4, 5, 6, 7] mất bao nhiêu bước so sánh trong ví dụ?

*Đáp án:* **Hai bước**: phần tử giữa 4 rồi phần tử 6 (với cách chọn midpoint đã nêu).

**Bài 7 — Gốc heap.** Với min-heap, gốc là min vì bất biến nào?

*Đáp án:* Bất biến **cha ≤ con** trên mọi cạnh; theo tính bắc cầu, gốc ≤ mọi hậu duệ.

**Bài 8 — Max trong min-heap.** Có thể đọc max của min-heap luôn ở a[n−1] không?

*Đáp án:* **Không**. Max có thể ở một lá nhưng không nhất thiết ở ô cuối; tìm max tổng quát có thể O(n).

**Bài 9 — Chiều cao.** Vì sao heap nhị phân có O(log n) chiều cao dù thêm các khóa theo thứ tự bất kỳ?

*Đáp án:* Vì **hình dạng cây gần đầy đủ** được giữ bởi việc thêm cuối mảng rồi sửa thứ tự; thứ tự khóa không làm cây lệch.

**Bài 10 — BST mất cân bằng.** Chèn 1, 2, 3, 4, 5 vào BST đơn giản có thể tạo cấu trúc gì? Tìm 5 xấu nhất tốn bao nhiêu?

*Đáp án:* Có thể thành **chuỗi con phải**, chiều cao Θ(n); tìm 5 có thể mất Θ(n).

**Bài 11 — BST tự cân bằng.** AVL/red-black khác BST thường ở bảo đảm quan trọng nào?

*Đáp án:* Duy trì chiều cao **O(log n)** bằng các bất biến cân bằng và thao tác xoay/sửa thích hợp.

**Bài 12 — Chèn khóa 0.** Với heap [1, 3, 2, 7, 6, 5, 4], push 0 tạo mảng gì theo sift-up?

*Đáp án:* **[0, 1, 2, 3, 6, 5, 4, 7]** sau append và ba lần đổi với các tổ tiên.

**Bài 13 — Chèn vào mảng tăng dần.** Với [1, 2, 3, 4, 5, 6, 7], chèn 0 có mất O(log n) tổng thời gian không?

*Đáp án:* **Không**. Tìm vị trí có thể O(log n), nhưng phải dịch bảy entry, O(n).

**Bài 14 — Peek hay pop?** Với mảng tăng dần, đọc min a[0] và xóa min bằng pop(0) có cùng độ phức tạp không?

*Đáp án:* Không. **Peek Θ(1)**; **pop(0) Θ(n)** do dịch các entry còn lại.

**Bài 15 — Danh sách liên kết.** Vì sao một danh sách liên kết tăng dần không mặc nhiên hỗ trợ binary search O(log n)?

*Đáp án:* Không có truy cập ngẫu nhiên O(1) tới phần tử giữa; phải duyệt nút từ head để tới vị trí.

**Bài 16 — Truy vấn khoảng.** Hệ thống thường xuyên cần mọi khóa trong [lo, hi] từ một tập dữ liệu động. Nên cân nhắc cấu trúc nào?

*Đáp án:* **BST tự cân bằng**, có thể trả k kết quả với **O(log n + k)**, hoặc **mảng tăng dần** nếu cập nhật ít; heap không thuận tiện bằng.

**Bài 17 — Duyệt có thứ tự.** Để lấy toàn bộ n phần tử tăng dần, BST và heap thường tốn bao nhiêu?

*Đáp án:* **BST in-order Θ(n)**. Min-heap thường cần **n lần pop O(n log n)** và làm thay đổi heap; nếu giữ nguyên cần bản sao/cách khác.

**Bài 18 — Heapify.** Xây min-heap từ một mảng n khóa có sẵn bằng bottom-up heapify tốn bao nhiêu?

*Đáp án:* **Θ(n)** thời gian và O(1) bộ nhớ phụ nếu sửa ngay trên mảng đó.

**Bài 19 — Khóa trùng.** Có phải BST và heap đều mặc định cấm khóa bằng nhau?

*Đáp án:* Không. Heap cho phép khóa bằng nhau; BST cần chính sách lưu/đếm khóa trùng nhất quán.

**Bài 20 — Tính ổn định.** Hai công việc cùng priority có chắc được heap pop theo FIFO không?

*Đáp án:* **Không**. Nếu cần FIFO khi hòa, hãy bổ sung **sequence** để so sánh theo (priority, sequence).

**Bài 21 — Tìm theo ID.** Nếu heap được tổ chức theo priority, có thể mặc định tìm công việc theo ID trong O(log n) không?

*Đáp án:* **Không**. Priority không phải ID; cần thêm chỉ mục như bảng băm ID → vị trí heap và duy trì chỉ mục sau mọi lần hoán đổi.

**Bài 22 — Thứ hạng.** Muốn đọc phần tử nhỏ thứ 100, mảng tăng dần và heap có lợi thế gì khác nhau?

*Đáp án:* Mảng tăng dần đọc **a[99] trong O(1)** nếu đủ phần tử. Heap không bảo đảm phần tử nhỏ thứ 100 ở chỉ số 99.

**Bài 23 — Khi nào dùng heap?** Một hàng đợi có push và pop phần tử ưu tiên nhất diễn ra liên tục, ít tìm khóa bất kỳ. Chọn gì?

*Đáp án:* **Binary heap** thường phù hợp với peek O(1), push/pop O(log n).

**Bài 24 — Khi nào dùng sorted array?** Dữ liệu gần như bất biến, thường tìm theo khóa và duyệt tăng dần, ít thêm/xóa. Chọn gì?

*Đáp án:* **Mảng tăng dần** là lựa chọn đáng cân nhắc: binary search O(log n), duyệt Θ(n), đọc theo chỉ số O(1).

**Bài 25 — Kiểm chứng BST.** Một cây có gốc 10, con trái 5 và con phải của 5 là 12. Có phải BST không?

*Đáp án:* **Không**. Khóa 12 thuộc cây con trái gốc 10 nhưng lại lớn hơn 10; vi phạm bất biến toàn cây con.

**Bài 26 — Cùng tập khóa, nhiều heap.** Hai mảng [1, 3, 2, 7, 6, 5, 4] và [1, 2, 3, 4, 5, 6, 7] cùng là min-heap được không?

*Đáp án:* **Được**. Cả hai đều thỏa cha ≤ con; heap không yêu cầu một hoán vị duy nhất.

**Bài 27 — Phân biệt bộ nhớ.** Một min-heap trong mảng và một BST n nút đều chứa n entry. Bộ nhớ của mỗi cấu trúc là bậc nào?

*Đáp án:* Cả hai cần **O(n)** không gian lưu dữ liệu. BST thường có overhead con trỏ/nút; heap mảng không cần con trỏ cha/con trong từng entry.

**Bài 28 — Lựa chọn theo ràng buộc.** Một hệ thống cần thêm/xóa theo khóa, truy vấn predecessor/successor và liệt kê khoảng, đồng thời phải bảo đảm chi phí logarit trường hợp xấu nhất. Cấu trúc nào phù hợp nhất trong ba loại đã so sánh?

*Đáp án:* **BST tự cân bằng** như AVL/red-black, không phải BST đơn giản không cân bằng hoặc binary heap.

## 21. Tổng kết: chọn theo bất biến và thao tác

**Min-heap** trả lời tốt câu hỏi **“Phần tử nào nhỏ nhất hiện nay?”**. Cấu trúc này là cây gần đầy đủ, lưu bằng mảng, chỉ yêu cầu **cha ≤ con**. Vì thế, peek min O(1), push/pop min O(log n), heapify từ mảng n entry Θ(n), nhưng tìm khóa bất kỳ hoặc truy vấn khoảng không được bảo đảm nhanh.

**BST** trả lời tốt câu hỏi **“Khóa x nằm bên trái hay phải, có những khóa nào trước/sau x?”**. Bất biến về **toàn bộ cây con** giúp tìm kiếm và duyệt in-order có thứ tự. Tuy nhiên, chỉ **BST tự cân bằng** mới bảo đảm chiều cao O(log n) trong trường hợp xấu nhất.

**Dãy đã sắp xếp** trả lời tốt câu hỏi **“Phần tử ở vị trí k là gì, khóa x nằm ở vùng nào?”** khi lưu bằng mảng có truy cập ngẫu nhiên. Binary search O(log n) và duyệt Θ(n) rất thuận tiện, nhưng chèn/xóa giữa mảng thường O(n). Nếu dãy được lưu bằng danh sách liên kết, chi phí truy cập theo vị trí sẽ khác.

**Ghi nhớ:** **Heap ≠ BST ≠ mảng đã sắp xếp**. Chúng cùng biểu diễn các khóa, nhưng mỗi loại bảo toàn **một bất biến khác nhau**. Hãy xác định tập thao tác thường dùng — **lấy cực trị, tìm khóa, truy vấn khoảng, duyệt theo thứ tự hay cập nhật** — trước khi chọn cấu trúc, và luôn xét chi phí của **toàn bộ thao tác**, không chỉ một bước so sánh hoặc sửa liên kết.
