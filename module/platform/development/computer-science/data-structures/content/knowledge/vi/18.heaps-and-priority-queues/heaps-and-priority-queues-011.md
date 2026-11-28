# Heap nhị thức và phép hợp nhất các cây theo bậc

Một **hàng đợi ưu tiên** (*priority queue*) không chỉ cần thêm phần tử và lấy phần tử có khóa ưu tiên nhất. Trong một số hệ thống, còn thường xuyên phải **hợp nhất hai hàng đợi ưu tiên đã có**: chẳng hạn gộp hai hàng chờ công việc hoặc kết hợp hai nhóm sự kiện. Nếu luôn lấy từng phần tử từ hàng đợi thứ hai để chèn vào hàng đợi thứ nhất, ta bỏ lỡ cơ hội tận dụng cấu trúc đã xây dựng.

**Heap nhị thức** (*binomial heap*) được thiết kế xoay quanh thao tác **hợp nhất** (*meld/union*). Thay vì chỉ có một cây nhị phân gần đầy đủ như **binary heap**, nó là **một rừng các cây nhị thức**, mỗi cây có một **bậc** (*degree*) riêng. Hai cây có **cùng bậc** có thể được nối với nhau bằng một thao tác O(1), tạo ra cây có bậc lớn hơn một. Vì thế, hợp nhất hai heap giống như **cộng hai số nhị phân có nhớ**.

Bài thuộc chương **Heap và hàng đợi ưu tiên** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**. Đúng với mục tiêu của mô-đun, chúng ta sẽ phân tích **bất biến, thao tác và độ phức tạp về thời gian/bộ nhớ** để hiểu khi nào nên chọn heap nhị thức thay cho heap nhị phân, mảng đã sắp xếp hoặc cấu trúc khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Định nghĩa cây nhị thức **B₀, B₁, ..., Bₖ** và phép tạo **Bₖ₊₁** từ hai cây Bₖ.
- Chứng minh cây **Bₖ có 2ᵏ nút**, gốc có **bậc k**, chiều cao k và có các cây con Bₖ₋₁, ..., B₀.
- Giải thích vì sao rừng của binomial heap chỉ có **tối đa một cây ở mỗi bậc**.
- Liên hệ các bậc cây với **biểu diễn nhị phân** của tổng số phần tử n.
- Thực hiện thao tác **link** hai cây cùng bậc bằng cách so sánh hai khóa gốc.
- Mô phỏng phép **meld** có các lượt **carry** khi xuất hiện nhiều cây cùng bậc.
- Mô tả rõ điều gì xảy ra với **nguồn, đích và quyền sở hữu nút** khi hợp nhất bằng chuyển cây.
- Phân tích các thao tác **insert, find-min, extract-min, decrease-key, delete** và hợp nhất.
- Cài đặt một **min-binomial heap** bằng Python, sử dụng liên kết **parent/child/sibling** và danh sách các gốc.
- Kiểm tra bất biến **bậc, kích thước cây, thứ tự heap, liên kết cha/con và tổng size**.
- So sánh chi phí hợp nhất của heap nhị thức với cách hợp nhất hai binary heap.
- Nhận biết những lỗi thường gặp với **khóa trùng, bậc cây, danh sách con, carry và việc dùng chung nút**.

## 2. Cây nhị thức Bₖ là gì?

Một **cây nhị thức bậc k**, ký hiệu **Bₖ**, được xác định đệ quy:

1. **B₀** chỉ có **một nút**.
2. **Bₖ₊₁** được tạo bằng cách lấy **hai cây Bₖ**, chọn một gốc làm gốc mới và biến gốc còn lại thành **một nút con trực tiếp** của nó.

Định nghĩa này là về **hình dạng**; khi dùng trong **min-binomial heap**, ta còn phải chọn **gốc có khóa nhỏ hơn hoặc bằng** làm cha để giữ thứ tự min-heap.

### 2.1. Các cây nhỏ nhất

~~~text
B0: một nút

   ○

Số nút: 1
Bậc gốc: 0
~~~

~~~text
B1: ghép hai B0

   ○
   |
   ○

Số nút: 2
Bậc gốc: 1
~~~

~~~text
B2: ghép hai B1

      ○
     / \
    ○   ○
    |
    ○

Số nút: 4
Bậc gốc: 2
~~~

~~~text
B3: ghép hai B2

          ○
        / | \
       ○  ○  ○
      / \ |
     ○   ○ ○
     |
     ○

Số nút: 8
Bậc gốc: 3
~~~

Trong sơ đồ, các nhánh được vẽ để thể hiện quan hệ cha–con, không phải vị trí trái/phải cố định của **binary heap**. Gốc của **B₃ có ba con trực tiếp**; cây nhị thức **không phải cây nhị phân theo nghĩa mỗi nút chỉ có tối đa hai con**.

Một cách hình dung chính xác hơn là ghi tên **cây con** của gốc:

~~~text
B3:

                 root
              /    |    \
            B2     B1    B0

B2 gồm 4 nút; B1 gồm 2 nút; B0 gồm 1 nút.
Tổng: 1 + 4 + 2 + 1 = 8 nút.
~~~

### 2.2. Bậc (*degree*) là gì?

**Bậc của một nút** là **số con trực tiếp** của nút đó, không phải số hậu duệ trong toàn bộ cây con.

- Gốc B₀ có bậc 0.
- Gốc B₁ có bậc 1.
- Gốc B₂ có bậc 2.
- Gốc B₃ có bậc 3.

Trong một cây B₃, gốc có **7 hậu duệ**, nhưng bậc của nó vẫn là **3**, không phải 7.

**Bậc không phải khóa ưu tiên**. Một cây B₂ có thể có gốc mang khóa 3 hoặc 100; điều quyết định bậc là cấu trúc nút, còn khóa quyết định thứ tự min/max-heap.

## 3. Những tính chất quan trọng của Bₖ

| Cây | Số nút | Bậc gốc | Chiều cao (số cạnh tối đa) | Bậc các con trực tiếp của gốc |
| --- | ---: | ---: | ---: | --- |
| B₀ | 1 | 0 | 0 | Không có |
| B₁ | 2 | 1 | 1 | 0 |
| B₂ | 4 | 2 | 2 | 1, 0 |
| B₃ | 8 | 3 | 3 | 2, 1, 0 |
| B₄ | 16 | 4 | 4 | 3, 2, 1, 0 |
| Bₖ | **2ᵏ** | **k** | **k** | k−1, ..., 1, 0 |

### 3.1. Vì sao cây Bₖ có 2ᵏ nút?

Quy nạp theo k:

- **Cơ sở k = 0:** B₀ có một nút, bằng 2⁰.
- **Bước quy nạp:** Giả sử Bₖ có 2ᵏ nút. Bₖ₊₁ được ghép từ **hai** bản Bₖ rời nhau, nên có:

\[
|B_{k+1}|=2\cdot 2^k=2^{k+1}.
\]

Vậy mọi Bₖ có **2ᵏ nút**.

### 3.2. Vì sao gốc Bₖ có đúng k con?

Mỗi lần ghép hai Bₖ để tạo Bₖ₊₁, **một gốc Bₖ trở thành con trực tiếp mới** của gốc còn lại. Bậc của gốc thắng tăng từ k lên **k + 1**. B₀ bắt đầu với bậc 0, nên quy nạp cho ra gốc Bₖ có bậc k.

Hơn nữa, nếu gốc thắng của Bₖ trước đó có các cây con **Bₖ₋₁, ..., B₀**, khi nhận thêm một cây Bₖ làm con, gốc của Bₖ₊₁ sẽ có các cây con:

\[
B_k,\ B_{k-1},\ldots,B_1,\ B_0.
\]

Tổng số nút cũng có thể kiểm tra bằng:

\[
1+\sum_{j=0}^{k-1}2^j
=1+(2^k-1)=2^k.
\]

### 3.3. Chiều cao và số cây con

Bₖ có chiều cao **k** vì ở mỗi bước từ Bₖ₋₁ lên Bₖ, đường đi dài nhất có thể tăng thêm một cạnh. Mỗi gốc có **k cây con trực tiếp**, nhưng tổng số nút trong những cây con là **2ᵏ − 1**.

Những con số này rất quan trọng khi **extract-min**: nếu xóa gốc của một cây Bₖ, ta nhận được **k cây nhị thức nhỏ hơn**, đúng các bậc từ **0 đến k − 1**, chứ không phải k cây cùng bậc.

## 4. Binomial heap là một rừng cây, không phải một cây duy nhất

Một **min-binomial heap** là một **rừng các cây nhị thức** thỏa hai bất biến:

1. **Bất biến bậc:** Trong danh sách gốc có **tối đa một cây Bₖ ở mỗi bậc k**.
2. **Bất biến thứ tự min-heap:** Trong **mỗi** cây, khóa ở nút cha không lớn hơn khóa ở các con trực tiếp.

Vì các cạnh trong từng cây đều thỏa quan hệ min-heap, **gốc mỗi cây là khóa nhỏ nhất trong cây ấy**. Muốn biết khóa nhỏ nhất toàn rừng, ta so sánh **các gốc của các cây**, không cần duyệt từng nút.

### 4.1. Biểu diễn nhị phân của n quyết định các bậc cây

Vì **Bₖ có 2ᵏ nút** và mỗi bậc xuất hiện tối đa một lần, số phần tử n có thể được viết:

\[
n=\sum_{k\in D}2^k,
\]

trong đó **D** là tập bậc của các cây đang có.

Đây chính là biểu diễn **nhị phân** của n: bit thứ k bằng 1 nếu rừng chứa Bₖ, bằng 0 nếu không.

Ví dụ:

~~~text
n = 13 = 8 + 4 + 1

Biểu diễn nhị phân: 1101₂

Các cây đang có: B3, B2, B0

Danh sách gốc tăng theo bậc:
[B0, B2, B3]
~~~

Rừng này có tổng số nút **1 + 4 + 8 = 13**. Không có B₁ vì bit thứ 1 của 13 bằng 0.

### 4.2. Bảng ví dụ

| Tổng số nút n | Nhị phân | Các bậc cây | Tổng kích thước |
| ---: | --- | --- | --- |
| 0 | 0 | Không có | 0 |
| 1 | 1 | B₀ | 1 |
| 2 | 10 | B₁ | 2 |
| 3 | 11 | B₀, B₁ | 1 + 2 |
| 4 | 100 | B₂ | 4 |
| 5 | 101 | B₀, B₂ | 1 + 4 |
| 7 | 111 | B₀, B₁, B₂ | 1 + 2 + 4 |
| 8 | 1000 | B₃ | 8 |
| 13 | 1101 | B₀, B₂, B₃ | 1 + 4 + 8 |
| 20 | 10100 | B₂, B₄ | 4 + 16 |

### 4.3. Rừng có bao nhiêu cây?

Tổng số cây bằng **số bit 1** trong biểu diễn nhị phân của n, còn gọi là **popcount(n)**.

Với n > 0, số vị trí bit của n là **⌊log₂ n⌋ + 1**, nên:

\[
\#\text{cây}\le\lfloor\log_2 n\rfloor+1=O(\log n).
\]

Hệ quả:

- **find-min** có thể quét tối đa O(log n) gốc.
- **meld** chỉ cần xử lý O(log n) cây gốc và các lần ghép.
- **extract-min** đưa tối đa O(log n) cây con của gốc bị xóa trở lại rừng.

**Đừng hiểu sai:** Số cây là O(log n), nhưng tổng số **nút** vẫn là n; các cây bậc lớn chứa rất nhiều phần tử.

## 5. Bất biến cấu trúc và cách lưu liên kết

Khác với binary heap thường lưu trực tiếp trong một mảng duy nhất, binomial heap cần biểu diễn **nhiều cây có nút nhiều con**.

Một cách lưu thông dụng dùng các trường:

~~~text
BinomialNode:
    key        khóa ưu tiên
    payload    dữ liệu kèm theo
    degree     số con trực tiếp
    parent     cha, hoặc None nếu là gốc cây
    child      con đầu tiên, hoặc None
    sibling    con kế tiếp cùng cha, hoặc None

BinomialHeap:
    roots      danh sách các gốc Bk
    size       tổng số entry trong toàn rừng
~~~

Trong mã Python cuối bài, **roots** là một **list chứa các gốc**, sắp theo bậc **tăng dần**. Mỗi nút dùng **child/sibling** để tạo danh sách liên kết những con trực tiếp.

### 5.1. Minh họa danh sách các gốc

~~~text
Heap n = 13:

roots:
  [B0] → [B2] → [B3]
   bậc0   bậc2   bậc3

Đây là ba cây riêng, không có cạnh cha–con giữa các gốc.
~~~

Trong cách cài đặt này, mũi tên giữa các gốc **minh họa thứ tự của list roots**, không phải thuộc tính sibling của một nút gốc. Nút gốc có **parent = None** và **sibling = None**; sibling chỉ dùng cho các nút cùng cha bên trong một cây.

### 5.2. Danh sách con theo bậc giảm dần

Khi tạo một cây Bₖ₊₁ bằng cách gắn gốc một cây Bₖ thành **con đầu tiên** của gốc thắng:

~~~text
Trước khi link, gốc thắng Bk có các con:
B(k-1) → B(k-2) → ... → B0

Gắn cây Bk vào đầu danh sách:
Bk → B(k-1) → B(k-2) → ... → B0
~~~

Vì thế, đối với mỗi nút có **degree = d**, danh sách các con trực tiếp đi theo sibling có các bậc:

~~~text
d-1, d-2, ..., 1, 0
~~~

Đây là bất biến cài đặt hữu ích. Khi tách các con của một gốc bị xóa, ta có thể **đảo danh sách con** để thu được các gốc tăng dần theo bậc.

### 5.3. Không được dùng chung nút giữa hai heap độc lập

Khi hợp nhất bằng **chuyển cây**, heap nguồn nhường các nút cho heap đích. Sau thao tác:

- Heap đích sở hữu toàn bộ nút của hai heap ban đầu.
- Heap nguồn trở thành rỗng: không còn gốc, **size = 0**.
- Không cấp phát lại các nút dữ liệu; **danh tính đối tượng nút** giữ nguyên.
- Hai heap không được tiếp tục cùng trỏ vào cùng một cây để sửa độc lập.

Nếu muốn giữ cả hai heap gốc không đổi, cần định nghĩa một API **sao chép**, khác với thao tác meld_move của bài này.

## 6. Phép link: hai cây cùng bậc tạo cây bậc kế tiếp

Đây là thao tác cơ bản nhất của binomial heap.

**Tiền điều kiện:**

- Hai cây **Bₖ khác nhau và không dùng chung nút**.
- Hai gốc có **cùng degree = k**.
- Mỗi cây đang thỏa thứ tự min-heap.
- Cả hai gốc hiện không có cha.

**Mục tiêu:** Tạo một cây **Bₖ₊₁**, giữ bất biến min-heap.

### 6.1. Quy tắc chọn cha

Giả sử ta có hai B₂:

~~~text
Cây A: B2, gốc khóa 3   (4 nút)
Cây B: B2, gốc khóa 8   (4 nút)
~~~

Vì **3 ≤ 8**, giữ gốc 3 làm cha, đưa **toàn bộ B₂ gốc 8** vào **đầu danh sách con trực tiếp** của gốc 3.

~~~text
Trước:
A (B2, root=3)       B (B2, root=8)

Sau:
      3                  B3, 8 nút
    / | \
   8  B1 B0
   |
  cây B2 cũ gốc 8
~~~

Sơ đồ trên chỉ biểu diễn quan hệ **các cây con**: con đầu tiên có gốc khóa 8 và là cây B₂ nguyên vẹn; hai cây con cũ của gốc 3 có bậc 1 và 0.

Gốc 3 có bậc mới **3**; gốc 8 nay có **parent = gốc 3**.

### 6.2. Pseudocode link

~~~text
link_min(A, B):
    yêu cầu A.degree == B.degree

    nếu A.key <= B.key:
        parent = A
        child  = B
    ngược lại:
        parent = B
        child  = A

    child.parent  = parent
    child.sibling = parent.child
    parent.child  = child
    parent.degree = parent.degree + 1

    trả parent
~~~

**Quan trọng:** Không nối từng nút của cây thua. Ta chỉ sửa một số **liên kết ở hai gốc**; phần còn lại của hai cây được giữ nguyên.

### 6.3. Chứng minh đúng

- Hai cây có số nút **2ᵏ** mỗi cây, nên sau link có **2ᵏ + 2ᵏ = 2ᵏ⁺¹** nút.
- Gốc thắng đang có k con trực tiếp và nhận thêm một con, nên bậc tăng thành **k + 1**.
- Cây mới có các cây con Bₖ, Bₖ₋₁, ..., B₀, đúng hình dạng **Bₖ₊₁**.
- Vì gốc thắng có khóa ≤ gốc thua và mỗi cây cũ đã là min-heap, cạnh mới cũng thỏa **cha ≤ con**. Những cạnh cũ không thay đổi.

Do đó, thao tác link tạo **một cây nhị thức hợp lệ** trong **Θ(1) thời gian và O(1) bộ nhớ phụ**, khi đã có tham chiếu tới hai gốc.

### 6.4. Vì sao không được link hai cây khác bậc?

Nếu lấy B₁ nối với B₃ rồi chỉ tăng degree lên một, cây nhận được không có cấu trúc B₄ hoặc B₂ theo định nghĩa nhị thức, và số nút cũng không phải lũy thừa hai phù hợp. Vì vậy, **chỉ link các gốc cùng bậc**.

### 6.5. Khi hai khóa gốc bằng nhau

Nếu A.key = B.key, chọn một trong hai làm cha vẫn giữ **min-heap**. Nhưng quyết định ấy **không tự bảo đảm** các entry cùng khóa được lấy ra theo đúng thứ tự thêm. Nếu cần **FIFO khi hòa ưu tiên**, phải có khóa phụ như **sequence** và nhất quán khi hợp nhất.

## 7. Phép meld như cộng nhị phân có nhớ

Giả sử hai binomial heap A và B có **các tập nút rời nhau**. Mục tiêu là tạo một rừng chứa toàn bộ nút, đồng thời chỉ giữ **một cây cho mỗi bậc**.

Mỗi cây Bₖ đại diện cho một bit có giá trị **2ᵏ**. Nếu ở bậc k có hai cây, ta **link** chúng thành một Bₖ₊₁ — giống như phép cộng:

\[
2^k+2^k=2^{k+1}.
\]

Cây vừa tạo là một **carry (nhớ)** sang bậc kế tiếp.

### 7.1. Quy tắc tại từng bậc

Khi xét một bậc k, có thể gặp những cây từ heap A, heap B và **carry** từ bậc k−1.

| Số cây Bₖ tại bậc k | Giữ lại ở bậc k | Chuyển sang bậc k+1 |
| ---: | --- | --- |
| 0 | Không có | Không có |
| 1 | Giữ một Bₖ | Không có |
| 2 | Không giữ | Link hai Bₖ thành một Bₖ₊₁ |
| 3 | Giữ một Bₖ | Link hai Bₖ còn lại thành một Bₖ₊₁ |

Với 3 cây, ta có:

\[
3\cdot 2^k=2^k+2^{k+1}.
\]

Đây là cách xử lý **1 + 1 + carry = 3** trong phép cộng nhị phân.

### 7.2. Không thể chỉ nối hai danh sách gốc

Giả sử:

~~~text
Heap A có rừng: [B0, B2]
Heap B có rừng: [B0, B1]

Nối danh sách đơn thuần:
[B0, B0, B1, B2]
~~~

Có **hai cây B₀**, trái bất biến “mỗi bậc tối đa một cây”. Phải link chúng thành B₁, rồi có thể lại xảy ra trùng bậc với B₁ đã có; carry có thể tiếp tục lên nhiều bậc.

### 7.3. Hai giai đoạn điển hình

Một cách hiện thực chuẩn:

1. **Gộp hai danh sách gốc** theo thứ tự bậc tăng dần; số gốc của mỗi heap là O(log n).
2. **Xử lý trùng bậc**, liên tục link những cây cùng bậc, đưa carry lên bậc tiếp theo cho tới khi mỗi bậc chỉ có một cây.

Ta cũng có thể dùng một **mảng slot theo bậc**, coi mỗi vị trí slots[k] là ô giữ một cây Bₖ. Khi một cây mới đến và ô đã có cây, link để tạo carry ở slots[k+1]. Mã Python ở phần sau dùng cách này vì dễ theo dõi và ít trường hợp con trỏ root-list phức tạp.

## 8. Mô phỏng: hợp nhất hai heap kích thước 13 và 7

Giả sử:

~~~text
Heap A: nA = 13 = 1101₂
Các cây: B0, B2, B3

Heap B: nB = 7  = 0111₂
Các cây: B0, B1, B2

Tổng n = 13 + 7 = 20 = 10100₂
Kết quả kỳ vọng: B2, B4
~~~

Theo dõi từng bậc:

| Bậc k | Cây của A | Cây của B | Carry đi vào | Cây giữ ở bậc k | Carry đi ra |
| ---: | --- | --- | --- | --- | --- |
| 0 | B₀ | B₀ | Không | Không | **B₁** |
| 1 | Không | B₁ | B₁ | Không | **B₂** |
| 2 | B₂ | B₂ | B₂ | **Một B₂** | **B₃** |
| 3 | B₃ | Không | B₃ | Không | **B₄** |
| 4 | Không | Không | B₄ | **B₄** | Không |

Nhìn vào kết quả:

~~~text
Rừng sau meld:
  [B2, B4]

Số nút:
  2² + 2⁴ = 4 + 16 = 20
~~~

**Điểm dễ nhầm:** Ở bậc 2 xuất hiện **ba** cây B₂. Không được link cả ba thành một cây chỉ bằng một thao tác. Ta **giữ một B₂** và **link hai B₂** thành carry B₃. Tổng số nút được bảo toàn.

### 8.1. Hợp nhất có làm mất phần tử không?

Không. Mỗi phép link chỉ thay quan hệ cha/con giữa hai cây và giữ nguyên toàn bộ các nút. Nếu heap ban đầu có 13 và 7 nút khác nhau, heap đích sau meld có đúng **20 nút**, không ít hơn và cũng không nhiều hơn.

Bất biến kích thước:

\[
size_{\text{đích sau}}=size_A+size_B.
\]

Nếu API là **meld_move(A, B)**, heap B nhường các cây nên **size_B sau = 0** và danh sách gốc B rỗng. Tổng nút được quản lý bởi hai đối tượng vẫn không đổi.

### 8.2. Nhiều carry nối tiếp

Với A có 7 nút (**B₀, B₁, B₂**) và B có 1 nút (**B₀**):

~~~text
7  = 0111₂
1  = 0001₂
--------------
8  = 1000₂
~~~

Link B₀ + B₀ tạo B₁; B₁ mới gặp B₁ đã có tạo B₂; B₂ mới gặp B₂ đã có tạo B₃. Cuối cùng chỉ còn **một cây B₃** có 8 nút.

Đó chính là lý do một lần meld/insert có thể gây **chuỗi link từ bậc thấp lên bậc cao**.

## 9. Insert và find-min trong binomial heap

### 9.1. Thêm một entry (insert/push)

Một phần tử đơn lẻ chính là cây **B₀**:

~~~text
Entry mới:
  key = 2, payload = "Công việc X"

Cây mới:
  B0 chứa một nút có khóa 2
~~~

Ta có thể tạo một binomial heap một nút rồi **meld** nó vào heap hiện tại.

- Nếu heap chưa có B₀, chỉ thêm B₀.
- Nếu đã có B₀, link thành B₁.
- Nếu đã có cả B₁, tiếp tục carry tới B₂.
- Dừng khi gặp bậc chưa có cây.

**Worst-case:** O(log n) lần xử lý/link, vì số bậc tới gốc lớn nhất O(log n).

Trong một số cách cài đặt tối ưu và phân tích khấu hao, **insert** có thể đạt O(1) *amortized* bằng lập luận số carry tương tự bộ đếm nhị phân. Tuy nhiên, **không được tự gán O(1) amortized cho mọi mã nguồn**: nếu một cài đặt luôn sao chép/quét danh sách O(log n) gốc khi thêm, chính phần quét ấy đã tốn O(log n). Mã Python dùng slots ở phần sau ưu tiên tính rõ ràng và có **O(log n)** thời gian worst-case cho push.

### 9.2. Xem phần tử nhỏ nhất (find-min/peek)

Trong mỗi cây min-binomial, gốc nhỏ nhất của cây. Vì vậy, phần tử nhỏ nhất toàn rừng phải là **một trong các gốc**.

~~~text
roots:
  B0 (root key=9)
  B2 (root key=3)
  B3 (root key=5)

Min của cả heap = 3
~~~

Chỉ cần quét **danh sách gốc**, số lượng O(log n), nên:

- **peek-min:** O(log n) với cài đặt **không lưu con trỏ min**.
- Nếu duy trì **tham chiếu tới gốc nhỏ nhất**, có thể peek O(1), nhưng phải cập nhật tham chiếu đúng sau meld, extract-min và những thao tác làm thay đổi gốc.

Mã Python trong bài **quét các gốc** để tránh thêm metadata, do đó peek-min của mã minh họa là **O(log n)**, không phải O(1).

### 9.3. Vì sao không cần xem các nút con?

Bất biến min-heap của từng cây bảo đảm **không có nút hậu duệ nào có khóa nhỏ hơn gốc cây ấy**. Nếu khóa gốc B₂ là 3, mọi nút bên trong B₂ có khóa ≥ 3. Do vậy, chỉ cần so sánh các gốc để tìm min toàn heap.


## 10. Extract-min: xóa gốc nhỏ nhất và hợp nhất các cây con

**Extract-min** trả về và loại bỏ entry có khóa nhỏ nhất. Khác với binary heap chỉ có một gốc, min-binomial heap có **một rừng**; trước tiên phải tìm gốc nhỏ nhất giữa các cây.

### 10.1. Quy trình

Giả sử gốc nhỏ nhất thuộc cây **Bₖ**:

1. **Quét các gốc**, chọn cây có khóa gốc nhỏ nhất.
2. **Tách toàn bộ Bₖ** này khỏi danh sách gốc của heap.
3. **Xóa riêng gốc** của Bₖ; còn lại **k cây con** Bₖ₋₁, ..., B₁, B₀.
4. **Tháo liên kết của những gốc con** với nút vừa xóa: gán parent = None, tách sibling để mỗi cây là một gốc độc lập.
5. **Hợp nhất các cây con** trở lại rừng còn lại, link những cặp cùng bậc khi cần.
6. Tổng số nút giảm đúng **một**; trả về entry ở gốc đã xóa.

### 10.2. Ví dụ một cây B₃

~~~text
Trước khi extract-min:

          root key=1
         /    |    \
        B2    B1    B0

1 + 4 + 2 + 1 = 8 nút.

Xóa riêng root key=1:
   B2 (4 nút)   B1 (2 nút)   B0 (1 nút)

Tổng còn lại: 4 + 2 + 1 = 7 nút.
~~~

Cây B₃ với 8 nút trở thành rừng có bậc **2, 1, 0** và tổng 7 nút. Nếu heap còn những cây khác, việc đưa các cây con trở lại có thể tạo **trùng bậc**, nên cần chạy **meld**.

### 10.3. Vì sao phải đảo danh sách con?

Theo quy ước lưu child/sibling ở mục 5, danh sách con của một gốc Bₖ có thứ tự bậc **giảm dần**:

~~~text
B(k-1) → B(k-2) → ... → B1 → B0
~~~

Trong khi danh sách gốc **roots** được quy ước **tăng dần** theo bậc. Khi tách, ta thu thập các con rồi đảo thứ tự:

~~~text
[B0, B1, ..., B(k-2), B(k-1)]
~~~

Nếu thiết kế dùng quy ước khác cho danh sách con, cách tách có thể khác, nhưng phải bảo đảm rừng sau cùng vẫn chỉ có một cây ở mỗi bậc.

### 10.4. Độ phức tạp

Với n phần tử:

- Quét các gốc: **O(log n)**.
- Tách tối đa k = O(log n) cây con: **O(log n)**.
- Meld các cây con với rừng còn lại: **O(log n)**.

Vậy **extract-min O(log n) thời gian xấu nhất**. Nó không sao chép những nút còn lại; phép link chỉ thay vài liên kết của các gốc.

## 11. Cài đặt Python hoàn chỉnh: binomial min-heap

Ví dụ dùng Python 3.10 trở lên. Để dễ theo dõi, cấu trúc sử dụng:

- **roots:** một list các gốc có **degree tăng dần**, không trùng bậc.
- **parent/child/sibling:** các liên kết của những nút trong cùng cây.
- **child:** trỏ tới con trực tiếp có bậc **lớn nhất**; những con còn lại nối theo **sibling** với bậc giảm dần.
- **slots[d]:** ô tạm chứa một cây B_d khi meld. Hai cây gặp nhau ở cùng ô được link thành carry B_(d+1).
- **meld_move:** chuyển quyền sở hữu toàn bộ nút của heap khác và làm heap ấy rỗng.
- **peek_min:** quét danh sách gốc; không duy trì metadata min riêng.

Mã bao gồm push, peek_min, meld_move, extract_min và một hàm kiểm chứng bất biến để sử dụng khi học tập.

~~~python
from __future__ import annotations


class BinomialNode:
    def __init__(self, key: int, payload=None):
        self.key = key
        self.payload = payload
        self.degree = 0
        self.parent: BinomialNode | None = None
        self.child: BinomialNode | None = None
        self.sibling: BinomialNode | None = None


class BinomialHeap:
    def __init__(self):
        self.roots: list[BinomialNode] = []
        self.size = 0

    def __len__(self) -> int:
        return self.size

    def is_empty(self) -> bool:
        return self.size == 0

    def root_degrees(self) -> list[int]:
        """Các bậc cây gốc theo thứ tự tăng dần."""
        return [root.degree for root in self.roots]

    @staticmethod
    def _link(a: BinomialNode, b: BinomialNode) -> BinomialNode:
        """Liên kết hai cây cùng bậc thành cây bậc kế tiếp."""
        assert a is not b
        assert a.degree == b.degree
        assert a.parent is None and b.parent is None
        assert a.sibling is None and b.sibling is None

        if a.key <= b.key:
            parent, child = a, b
        else:
            parent, child = b, a

        # Đưa toàn bộ cây thua thành con đầu tiên của gốc thắng.
        child.parent = parent
        child.sibling = parent.child
        parent.child = child
        parent.degree += 1
        return parent

    def meld_move(self, other: BinomialHeap) -> None:
        """Hợp nhất cây từ other vào self, rồi làm other rỗng."""
        if self is other:
            raise ValueError("Không thể hợp nhất heap với chính nó")

        if other.size == 0:
            return

        # Tối đa một cây B_d ở mỗi ô; chỉ giữ các tham chiếu gốc.
        slots: list[BinomialNode | None] = []

        for root in self.roots + other.roots:
            carry = root

            while True:
                degree = carry.degree

                while len(slots) <= degree:
                    slots.append(None)

                existing = slots[degree]
                if existing is None:
                    slots[degree] = carry
                    break

                slots[degree] = None
                carry = self._link(existing, carry)

        self.roots = [root for root in slots if root is not None]
        self.size += other.size
        other.roots = []
        other.size = 0

    def push(self, key: int, payload=None) -> None:
        """Một entry mới là một cây B0."""
        one = BinomialHeap()
        one.roots = [BinomialNode(key, payload)]
        one.size = 1
        self.meld_move(one)

    def peek_min(self):
        """Đọc min trong O(log n), không xóa."""
        if not self.roots:
            raise IndexError("Heap rỗng")

        minimum = min(self.roots, key=lambda root: root.key)
        return minimum.key, minimum.payload

    def extract_min(self):
        """Xóa gốc min; các cây con được đưa trở lại rừng."""
        if not self.roots:
            raise IndexError("Heap rỗng")

        pos = min(
            range(len(self.roots)),
            key=lambda index: self.roots[index].key,
        )
        minimum = self.roots.pop(pos)

        # B_k có 2^k nút. Gỡ cả B_k khỏi heap trước.
        tree_size = 1 << minimum.degree
        self.size -= tree_size

        children = []
        current = minimum.child

        while current is not None:
            next_sibling = current.sibling
            current.parent = None
            current.sibling = None
            children.append(current)
            current = next_sibling

        # Danh sách con ban đầu B_(k-1), ..., B0.
        # Danh sách gốc mới cần B0, ..., B_(k-1).
        children.reverse()

        detached = BinomialHeap()
        detached.roots = children
        detached.size = tree_size - 1

        minimum.child = None
        minimum.degree = 0

        # (size cũ - 2^k) + (2^k - 1) = size cũ - 1.
        self.meld_move(detached)
        return minimum.key, minimum.payload

    def check_invariants(self) -> set[int]:
        """Kiểm thử O(n) thời gian và bộ nhớ, không thuộc meld cơ bản."""
        assert self.size >= 0

        if self.size == 0:
            assert self.roots == []
            return set()

        assert self.roots
        degrees = [root.degree for root in self.roots]
        assert degrees == sorted(set(degrees))
        assert sum(1 << d for d in degrees) == self.size

        visited: set[int] = set()

        def visit(node: BinomialNode, expected_parent):
            assert id(node) not in visited, "Nút lặp trong rừng"
            visited.add(id(node))
            assert node.parent is expected_parent

            children = []
            sibling_seen: set[int] = set()
            child = node.child

            while child is not None:
                assert id(child) not in sibling_seen, "Vòng sibling"
                sibling_seen.add(id(child))
                assert child.parent is node
                assert node.key <= child.key
                children.append(child)
                child = child.sibling

            # B_d có d con trực tiếp bậc d-1, ..., 0.
            assert len(children) == node.degree
            assert [c.degree for c in children] == list(
                range(node.degree - 1, -1, -1)
            )

            count = 1
            for c in children:
                count += visit(c, node)

            assert count == 1 << node.degree
            return count

        total = 0
        for root in self.roots:
            assert root.parent is None
            assert root.sibling is None
            total += visit(root, None)

        assert total == self.size
        assert len(visited) == self.size
        return visited


# 5 = 101₂: gốc B0 và B2.
left = BinomialHeap()
for key in [4, 9, 1, 7, 3]:
    left.push(key)

# 3 = 11₂: gốc B0 và B1.
right = BinomialHeap()
for key in [8, 2, 6]:
    right.push(key)

assert len(left) == 5
assert left.root_degrees() == [0, 2]
assert len(right) == 3
assert right.root_degrees() == [0, 1]
assert not (left.check_invariants() & right.check_invariants())

# 5 + 3 = 8 = 1000₂ => một cây B3.
left.meld_move(right)
assert len(left) == 8
assert left.root_degrees() == [3]
assert len(right) == 0
assert right.root_degrees() == []
assert left.peek_min() == (1, None)
left.check_invariants()
right.check_invariants()

# Lấy lần lượt sẽ cho thứ tự tăng dần của các khóa.
output = []
while not left.is_empty():
    key, _payload = left.extract_min()
    output.append(key)
    left.check_invariants()

assert output == [1, 2, 3, 4, 6, 7, 8, 9]
assert left.is_empty()

# Rỗng, một nút và chuyển quyền sở hữu.
empty = BinomialHeap()
other_empty = BinomialHeap()
empty.meld_move(other_empty)
assert empty.is_empty() and other_empty.is_empty()

single = BinomialHeap()
single.push(-5, "urgent")
empty.meld_move(single)
assert single.is_empty()
assert empty.peek_min() == (-5, "urgent")
assert empty.extract_min() == (-5, "urgent")
assert empty.is_empty()

# Payload không cần hỗ trợ so sánh.
class Task:
    def __init__(self, title):
        self.title = title


task_a = Task("A")
task_b = Task("B")
equal_keys = BinomialHeap()
equal_keys.push(2, task_a)
equal_keys.push(2, task_b)
popped = [equal_keys.extract_min(), equal_keys.extract_min()]

assert [entry[0] for entry in popped] == [2, 2]
assert {entry[1] for entry in popped} == {task_a, task_b}
equal_keys.check_invariants()

# Không cho phép tự meld.
try:
    empty.meld_move(empty)
except ValueError:
    pass
else:
    raise AssertionError("Phải từ chối self-meld")

try:
    empty.peek_min()
except IndexError:
    pass
else:
    raise AssertionError("Peek trên heap rỗng phải báo lỗi")
~~~

### 11.1. Vì sao slots xử lý được tình huống ba cây cùng bậc?

Mỗi lần đưa một cây vào **slots[d]**, hoặc ô trống và nhận cây, hoặc ô đang chứa một cây cùng bậc. Khi ô có hai cây, ta link chúng thành **carry B_(d+1)** và đưa carry lên một slot cao hơn.

Nếu ban đầu có **ba** cây B_d, hai cây đầu sẽ tạo carry, còn cây thứ ba có thể giữ ở bậc d. Kết quả đúng quy tắc:

\[
3\cdot 2^d=2^d+2^{d+1}.
\]

Không bao giờ cần “ghép ba cây thành một” trong một phép link.

### 11.2. Tại sao sau meld roots luôn hợp lệ?

Mỗi slot chứa **tối đa một gốc của bậc đúng với chỉ số slot**. Khi trùng bậc, _link tạo cây B_(d+1) đúng bất biến. Cuối cùng, duyệt slots tăng dần và lọc những slot không rỗng sẽ tạo ra danh sách gốc **không trùng bậc**, **sắp tăng**.

Những nút trong các cây cũ không bị tạo lại hoặc bị mất; tổng size được cập nhật bằng tổng size hai heap trước hợp nhất.

### 11.3. Vì sao cần tách từng cây con khi xóa min?

Những gốc con của cây bị xóa vẫn đang trỏ **parent** về nút bị xóa và nối **sibling** với nhau. Muốn coi chúng là các gốc độc lập để meld, phải bỏ hai loại liên kết ấy rồi khôi phục thứ tự bậc mong muốn.

Nếu quên làm sạch **parent**, heap có thể có gốc nhưng parent không phải None. Nếu quên làm sạch **sibling**, một cây mới đưa vào có thể còn trỏ tới gốc khác qua đường sibling, khiến nút bị duyệt hoặc sở hữu sai.

### 11.4. Tính ổn định và khóa trùng

Hàm _link chỉ so sánh **key**. Nếu hai gốc bằng khóa, chọn gốc thứ nhất làm cha vẫn hợp lệ nhưng **không bảo đảm FIFO** của các entry cùng khóa.

Các payload Task trong ví dụ không định nghĩa toán tử so sánh thứ tự. Mã vẫn hoạt động theo hợp đồng bởi payload **không tham gia so sánh**, còn hai entry cùng key được giữ như hai lần xuất hiện riêng biệt.

### 11.5. Tại sao check_invariants không nằm trong chi phí của push?

Hàm kiểm tra duyệt tất cả các nút, giữ tập visited, đếm bậc và đối chiếu tổng kích thước. Chi phí của nó là **Θ(n) thời gian, O(n) bộ nhớ phụ** trên heap hợp lệ.

Nếu ứng dụng luôn gọi nó sau push, phép đo thời gian của ứng dụng sẽ bao gồm cả **O(n) kiểm chứng**, không còn phản ánh riêng chi phí O(log n) của thao tác push.

Các assertion trong bài là tài liệu để kiểm tra sau này; theo giới hạn của STEP 4, worker không chạy Python hay vòng QA học thuật ở giai đoạn soạn bài.


## 12. Phân tích thời gian và bộ nhớ theo đúng cách cài đặt

Với n > 0, số cây gốc của binomial heap bằng **số bit 1** của n và không vượt quá **⌊log₂ n⌋ + 1**. Đây là cơ sở của nhiều chi phí logarit.

| Thao tác | Thời gian xấu nhất | Lý do |
| --- | --- | --- |
| Tạo heap rỗng | **O(1)** | Chỉ tạo metadata |
| Link hai Bₖ khi đã có gốc | **Θ(1)** | Một số phép gán liên kết và degree |
| Meld hai heap n và m entry | **O(log(n + m + 1))** | Xử lý O(log(n + m)) gốc/carry |
| Push một B₀ vào heap | **O(log(n + 1))** | Chuỗi carry có thể lan tới bậc cao |
| Peek-min không có min pointer | **O(log(n + 1))** | Quét các gốc |
| Peek-min có min pointer hợp lệ | **O(1)** | Chỉ đọc metadata |
| Extract-min | **O(log(n + 1))** | Tìm gốc min, tách con, meld |
| Decrease-key với tham chiếu nút/handle đúng | **O(log(n + 1))** | Có thể đi lên tối đa chiều cao cây |
| Delete với handle và kỹ thuật phù hợp | **O(log(n + 1))** | Đưa entry cần xóa lên rồi extract |
| Tìm một entry bất kỳ theo payload, không có chỉ mục | **O(n)** | Có thể phải duyệt tất cả |
| Duyệt n entry | **Θ(n)** | Mỗi nút phải được thăm |
| Kiểm chứng tất cả bất biến | **Θ(n)** | Duyệt và đếm từng nút |

Với n = 0 hoặc n = 1, các thao tác hợp lệ đơn giản thường chỉ tốn hằng số. Biểu thức **log(n+1)** giúp tránh nhầm log 0; trong phần giải thích thông thường có thể viết ngắn O(log n) khi n đủ lớn.

### 12.1. Vì sao meld là logarit?

Giả sử hai heap có n, m entry; tổng số gốc đầu vào là O(log(n+1) + log(m+1)). Trong cách xử lý các slot:

- Mỗi gốc đầu vào được đưa qua một lần.
- Mỗi lần **link** giảm **tổng số cây đang tồn tại** đi một.
- Bậc cao nhất của cây sau meld không thể vượt quá O(log(n+m+1)).
- Số lần mở rộng slots và số vị trí cuối cùng phải xét cũng O(log(n+m+1)).

Vì vậy, tổng thời gian của cách meld dùng slots trong bài là **O(log(n+m+1))**.

**Không thể kết luận thời gian là O(1)** chỉ từ việc link riêng hai cây bằng O(1). Có thể phải xử lý nhiều bậc khi carry đi xuyên qua một chuỗi cây.

### 12.2. Bộ nhớ phụ của ví dụ Python

Mã Python trong bài dùng:

- Một list **self.roots + other.roots** cho những tham chiếu gốc.
- Một list **slots** để gom các cây theo bậc.
- Khi extract-min, một list **children** và một heap tạm **detached**.

Số gốc và số con trực tiếp của một gốc đều O(log n), nên:

- **Meld:** O(log(n+m+1)) bộ nhớ phụ trong mã minh họa.
- **Extract-min:** O(log(n+1)) bộ nhớ phụ.
- **Tổng bộ nhớ của n nút:** vẫn O(n); meld không tạo lại các nút dữ liệu.
- **check_invariants:** riêng nó dùng O(n) bộ nhớ phụ cho visited và các nhóm con tạm.

Một cách cài đặt dùng **danh sách liên kết gốc** và phép xử lý trực tiếp có thể giảm vùng chứa tạm, nhưng chi phí phụ trợ phải phân tích theo thiết kế thực tế. **Không sao chép nút dữ liệu** không đồng nghĩa **mọi dạng meld đều dùng O(1) bộ nhớ phụ**.

### 12.3. Insert và phân tích khấu hao

Một số tài liệu phân tích **insert trong binomial heap** bằng cách xem các link như **carry của bộ đếm nhị phân**. Khi tăng n từ 0 lần lượt từng đơn vị, một số lần insert không cần link, đôi lúc nhiều carry xảy ra cùng lúc. Với một cách cài đặt phù hợp, có thể đạt **O(1) khấu hao** cho insert dù trường hợp xấu nhất vẫn O(log n).

Nhưng mã **meld_move** ở mục 11 luôn xây lại list slots và duyệt các gốc hiện có, nên **không được gán O(1) khấu hao cho mã đó chỉ vì số link trung bình nhỏ**. Tổng chi phí một lời gọi vẫn có thể O(log n) do phần quét/cấp phát slots, ngay cả khi gần như không cần link.

### 12.4. Đầu vào có khóa so sánh tốn chi phí

Phân tích ở bảng giả định **so sánh khóa O(1)**. Nếu khóa là chuỗi dài hoặc một đối tượng có phép so sánh phức tạp, chi phí phải cộng thêm thời gian so sánh ấy.

Tương tự, nếu cần thực hiện meld đồng thời với các luồng khác, **đồng bộ và cập nhật quyền sở hữu** là trách nhiệm hệ thống; bản thân các phép gán con trỏ không tự bảo đảm thao tác nguyên tử.

## 13. Decrease-key, delete và các giới hạn của handle

Heap nhị thức thường được trình bày với những thao tác nâng cao như **giảm khóa** (*decrease-key*) và **xóa theo handle** (*delete*). Chúng giải thích vì sao cấu trúc có liên kết **parent**, nhưng cũng có các tiền điều kiện quan trọng.

### 13.1. Giảm khóa trong min-heap

Giả sử một entry đang có khóa **17**, cần đổi thành **5** vì công việc trở nên khẩn cấp hơn.

Nếu biết trực tiếp **nút vật lý** đang lưu entry:

1. Đổi khóa entry thành 5.
2. Trong khi khóa của entry **nhỏ hơn khóa cha**, hoán đổi **toàn bộ entry** với entry ở cha.
3. Tiếp tục đi lên cho tới khi gặp cha không lớn hơn entry hoặc tới một gốc.

Đây là **bubble-up** theo chuỗi cha của một cây nhị thức. Mỗi cây Bₖ có chiều cao k = O(log n), nên chi phí O(log n).

**Chú ý:** Nếu chỉ đổi trường key nhưng không đổi payload tương ứng, dữ liệu công việc có thể bị gắn với khóa của công việc khác. Cần hoán đổi đầy đủ **(key, payload và metadata nhận diện)** theo hợp đồng.

### 13.2. Handle có thể trở nên sai khi hoán đổi entry

Một **handle** có thể là ID logic của entry hoặc một tham chiếu tới nút. Nếu decrease-key được cài bằng **hoán đổi nội dung giữa hai nút**, sau swap một tham chiếu tới **nút cũ** có thể **không còn chứa cùng công việc logic**.

Có hai hướng thiết kế:

- Duy trì **bảng ánh xạ ID/handle → nút hiện đang giữ entry**, cập nhật ánh xạ sau mỗi swap.
- Dùng cơ chế cập nhật liên kết/nút khác có hợp đồng handle rõ ràng, phức tạp hơn.

**Không mặc định rằng tham chiếu tới nút luôn đại diện cùng payload** trong một cài đặt có swap nội dung.

### 13.3. Xóa một entry đã biết

Một kỹ thuật lý thuyết với min-heap là:

1. **Decrease-key** của entry cần xóa xuống một khóa **nhỏ hơn nghiêm ngặt mọi khóa hợp lệ khác**.
2. Entry ấy được đẩy lên một gốc.
3. Gọi **extract-min** để xóa đúng entry.

Tổng chi phí O(log n) nếu đã có handle đúng và phép giảm khóa có chi phí O(log n).

Tuy nhiên, cách này cần **giá trị đánh dấu ưu tiên thấp nhất** hoặc cơ chế so sánh xác định rõ. Nếu một entry khác có cùng khóa đánh dấu, hoặc giá trị khóa không hỗ trợ sentinel ấy, không được giả định extract-min sẽ xóa đúng mục tiêu. API thực tế nên dùng **handle được kiểm soát** và quy tắc tie-breaking thích hợp.

### 13.4. Tìm vị trí không tự là O(log n)

Nếu yêu cầu chỉ là “xóa công việc có ID X” nhưng heap chỉ được sắp theo **priority**, việc xác định nút nào chứa ID X có thể tốn **O(n)** nếu không có chỉ mục phụ.

Vì vậy, phát biểu “delete O(log n)” thường giả định **handle đã được cung cấp** hoặc cấu trúc duy trì được ánh xạ từ ID sang nút. Tính chi phí thao tác phải bao gồm bước tìm nếu API chỉ nhận ID mà không có chỉ mục.

### 13.5. Đổi khóa theo hướng ngược

Trong min-heap, **decrease-key** có thể đẩy một entry lên. Nếu **tăng khóa**, entry có thể kém ưu tiên hơn các con, nên phải sửa theo hướng xuống hoặc thiết kế API riêng. Không được áp dụng mù quáng bubble-up cho mọi thay đổi khóa.

## 14. Đối chiếu binomial heap với binary heap

### 14.1. Hình dạng và lưu trữ

**Binary heap:**

- Một cây **nhị phân gần đầy đủ**.
- Thường lưu bằng một mảng 0-based.
- Quan hệ cha/con suy ra bằng chỉ số.
- Gốc của min-heap ở a[0].

**Binomial heap:**

- Một **rừng cây nhị thức Bₖ**.
- Mỗi nút có thể có **nhiều hơn hai con trực tiếp**.
- Thường lưu bằng các tham chiếu parent/child/sibling.
- Có **O(log n) gốc**, không phải một gốc duy nhất.

### 14.2. Khi nào meld là lợi thế?

Một cách gộp hai **binary heap độc lập** có n và m entry là:

1. Nối/copy n + m entry vào một mảng.
2. Chạy **bottom-up heapify** trên mảng đó.

Chi phí xây lại là **Θ(n+m)**.

Với hai **binomial heap hợp lệ**, chỉ có O(log n) và O(log m) cây gốc cần xét. Các cây được **chuyển nguyên vẹn**, link khi trùng bậc, nên meld mất **O(log(n+m))** thời gian khi tổng số entry dương.

Nếu hệ thống **thường xuyên hợp nhất các hàng đợi lớn**, binomial heap có lợi thế tiềm năng. Nếu chỉ push/pop và hiếm khi meld, binary heap bằng mảng thường đơn giản hơn và có khả năng tận dụng tính cục bộ bộ nhớ tốt.

### 14.3. Bảng tóm tắt

| Đặc điểm | Binary min-heap | Binomial min-heap |
| --- | --- | --- |
| Cấu trúc | Một cây nhị phân gần đầy đủ | Rừng các Bₖ bậc khác nhau |
| Số gốc | 1 khi không rỗng | O(log n) |
| Bất biến ưu tiên | Cha ≤ con | Cha ≤ con trong từng cây |
| Peek-min | **O(1)** | **O(log n)** nếu không cache min |
| Push | O(log n) | O(log n) worst-case |
| Extract-min | O(log n) | O(log n) |
| Meld hai heap độc lập | Thường Θ(n+m) bằng nối + heapify | **O(log(n+m))** |
| Biểu diễn thường gặp | Mảng | Nút liên kết |
| Độ phức tạp triển khai | Tương đối đơn giản | Nhiều bất biến link/degree/forest |
| Khả năng tìm ID tùy ý | Không nhanh nếu thiếu chỉ mục | Không nhanh nếu thiếu chỉ mục |

### 14.4. Phân biệt với Fibonacci heap

**Fibonacci heap** cũng hỗ trợ meld và decrease-key, nhưng dùng những bất biến cùng kỹ thuật hoãn việc hợp nhất cây khác với binomial heap. Nó có những bảo đảm khấu hao tốt trong mô hình thuật toán chuẩn, đổi lại phức tạp cài đặt cao hơn.

**Không phải mọi heap nhiều cây đều là binomial heap**. Đặc trưng của binomial heap là cấu trúc Bₖ đệ quy, **mỗi bậc tối đa một cây**, và cách **link hai cây cùng bậc** để thực hiện phép cộng nhị phân.

## 15. Những bất biến cần kiểm tra sau mỗi thao tác

Các phép gán liên kết rất ngắn, nhưng một lỗi nhỏ có thể làm hỏng toàn bộ rừng. Sau push, meld hoặc extract-min, có thể kiểm tra:

1. **Kích thước:** size bằng số nút khác nhau đi tới được từ tất cả gốc.
2. **Các bậc gốc:** tăng dần, không lặp; mỗi bậc xuất hiện tối đa một lần.
3. **Khớp số bit:** tổng **2^degree(root)** của tất cả gốc đúng bằng size.
4. **Cha gốc:** mọi root.parent là None.
5. **Không có liên kết sibling giữa các gốc** nếu dùng mô hình roots là Python list.
6. **Liên kết cha/con:** với mọi con c của nút p, c.parent chính là p.
7. **Thứ tự min-heap:** p.key ≤ c.key.
8. **Số con trực tiếp:** degree của nút bằng số con thật trong danh sách child/sibling.
9. **Bậc con:** nếu node.degree = d thì những con trực tiếp có bậc d−1, ..., 0.
10. **Kích thước cây:** cây gốc bậc d chứa chính xác **2ᵈ nút**.
11. **Không lặp nút:** một đối tượng nút không được đi tới từ hai đường sở hữu khác nhau; không có vòng trong các chuỗi sibling.
12. **Quyền sở hữu khi meld:** heap nguồn đã rỗng sau meld_move; heap đích nhận toàn bộ nút.

Các kiểm tra sâu này có thể tốn O(n) thời gian/bộ nhớ. Chúng phù hợp với **unit test và chẩn đoán**, không phải điều bắt buộc phải thực hiện sau mỗi thao tác O(log n) trong hệ thống chạy thật.

### Trường hợp biên cần thử

| Trường hợp | Kết quả đúng |
| --- | --- |
| Meld hai heap rỗng | Heap đích và nguồn đều rỗng |
| Meld heap có nút vào heap rỗng | Đích nhận toàn bộ cây; nguồn rỗng |
| Meld heap rỗng vào heap có nút | Đích giữ nguyên cấu trúc hợp lệ |
| Meld chính heap với nó | API **từ chối trước khi sửa** |
| Hợp nhất B₀ + B₀ | Một cây B₁ có 2 nút |
| Hợp nhất 7 + 1 nút | Một cây B₃ có 8 nút |
| Hợp nhất 13 + 7 nút | Hai cây B₂ và B₄ có 20 nút |
| Peek heap rỗng | Báo lỗi theo hợp đồng, ví dụ IndexError |
| Extract-min heap một nút | Trả entry, heap thành rỗng |
| Extract-min cây B₃ | Bỏ một gốc; tách B₂/B₁/B₀ và meld |
| Các khóa bằng nhau | Giữ đủ số lần xuất hiện, không tự đảm bảo FIFO |
| Payload không so sánh được | Vẫn xử lý nếu chỉ so sánh key |


## 16. Lỗi thường gặp khi link, meld và extract-min

| Sai sót | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi heap nhị thức là một cây nhị phân | Hiểu sai số con trực tiếp của nút | Một Bₖ có gốc bậc k, có thể k > 2 |
| Hiểu degree là số nút trong cây | Tính nhầm bậc và bước carry | Degree là số **con trực tiếp** |
| Link B₂ với B₃ | Cây mới không có dạng Bₖ hợp lệ | Chỉ link **hai cây cùng bậc** |
| Chọn gốc có khóa lớn hơn làm cha trong min-heap | Vi phạm cha ≤ con | Chọn **gốc nhỏ hơn hoặc bằng** |
| Chỉ gán child.parent, quên sửa child/sibling | Cây con không tới được hoặc chuỗi con sai | Cập nhật đủ parent, child, sibling, degree |
| Quên tăng degree của gốc thắng | Bậc không khớp số con/kích thước | Tăng degree đúng một khi link |
| Meld bằng cách chỉ nối hai danh sách root | Có nhiều cây cùng bậc | Xử lý trùng bậc và carry |
| Gặp ba cây cùng bậc rồi cố link cả ba | Không có phép Bₖ + Bₖ + Bₖ → một Bₖ₊₁ | Giữ một Bₖ và link hai cây thành carry |
| Không tiếp tục carry sang bậc kế tiếp | Vẫn có hai gốc cùng degree | Lặp cho tới khi slot được tìm thấy |
| Không sắp roots theo bậc sau meld | Thuật toán dựa vào thứ tự root hoạt động sai | Duyệt slots từ thấp đến cao |
| Không làm rỗng heap nguồn sau meld_move | Hai heap cùng sở hữu một cây | Gán roots nguồn rỗng, size nguồn = 0 |
| Meld một heap với chính nó | Link một cây với chính nó, tạo vòng | Từ chối khi self is other |
| Tìm min bằng cách xem nút gốc đầu tiên | Gốc đầu tiên là Bₖ bậc nhỏ, chưa chắc key nhỏ nhất | Quét **tất cả các gốc** nếu không cache min |
| Chỉ xóa gốc nhỏ nhất mà không đưa các cây con trở lại | Mất các entry còn lại trong cây ấy | Tách con rồi meld trở lại |
| Quên đặt parent = None cho gốc con sau extract-min | Gốc mới vẫn chỉ tới nút đã xóa | Cắt liên kết cha cũ |
| Quên bỏ liên kết sibling khi tách con | Cây gốc mới vô tình trỏ sang cây khác | Lưu next_sibling trước, rồi gán sibling = None |
| Không đảo thứ tự các con theo quy ước | Roots không còn tăng theo bậc | Đảo Bₖ₋₁,...,B₀ thành B₀,...,Bₖ₋₁ |
| Cập nhật size nguồn/đích sai | Size không khớp tổng 2^degree | Dùng đẳng thức bảo toàn số nút |
| Xóa entry theo handle nhưng swap payload không cập nhật handle | Handle chỉ sai công việc logic | Đồng bộ ID → node hoặc định nghĩa handle khác |
| Cho rằng khóa bằng nhau bắt buộc FIFO | Đầu ra có thể khác thứ tự thêm | Dùng tie-breaker như sequence |
| Dùng O(1) link để suy ra O(1) meld | Carry có thể trải qua nhiều bậc | Tính O(log(n+m)) cho toàn meld |
| Dùng kết quả amortized của cài đặt khác cho mã slots | Bỏ qua chi phí quét/cấp phát các slot | Phân tích đúng mã thực tế |
| Gọi validate O(n) sau mỗi push rồi báo tổng O(log n) | Đánh giá thấp chi phí chương trình | Phân biệt thao tác và kiểm chứng |

### Một quy trình gỡ lỗi dễ nhớ

Với bất kỳ lần meld nào, hãy ghi:

1. **Size hai heap** trước khi hợp nhất.
2. **Danh sách bậc của các gốc** trước meld.
3. Mỗi lần link: **bậc hai cây**, **khóa hai gốc**, **gốc thắng** và **bậc sau link**.
4. Sau mỗi carry, bậc vừa được xử lý đã có **tối đa một cây** chưa?
5. Cuối cùng, danh sách bậc có đúng các bit 1 của **n+m** không?
6. Mọi root có parent = None, và mọi cạnh trong cây có thỏa **cha ≤ con** không?
7. Heap nguồn đã nhường hết nút hay chưa?

Nếu size đúng nhưng danh sách bậc sai, thường có lỗi link/carry. Nếu danh sách bậc đúng nhưng min sai, hãy kiểm tra quan hệ khóa và thao tác chọn cha.

## 17. Ứng dụng và lựa chọn cấu trúc

### 17.1. Gộp hai hàng chờ công việc

Hai nhóm xử lý có thể tạo riêng các hàng đợi ưu tiên. Khi cần gộp công việc đang chờ, binomial heap cho phép **chuyển cả cây Bₖ** từ hàng đợi này sang hàng đợi kia, chỉ phải sửa những liên kết gốc cần thiết.

Ví dụ:

~~~text
Hàng chờ nhóm A: 13 công việc → B0, B2, B3
Hàng chờ nhóm B:  7 công việc → B0, B1, B2

Meld:
Hàng chờ chung:  20 công việc → B2, B4
Hàng chờ B: rỗng sau khi chuyển quyền sở hữu
~~~

Đây là lợi thế nếu các hàng chờ **thường xuyên cần hợp nhất**. Tuy nhiên, với ứng dụng đa luồng, phải đồng bộ quá trình meld; các phép cập nhật liên kết không tự nguyên tử.

### 17.2. Hợp nhất các tập sự kiện trong mô phỏng

Giả sử mỗi sự kiện có một **timestamp**. Mỗi bộ mô phỏng con giữ min-binomial heap theo thời gian sự kiện. Khi gộp các luồng sự kiện, meld có thể kết hợp các cây mà không phải dựng lại toàn bộ từ n+m entry.

Nếu cần xử lý theo thứ tự cố định khi nhiều sự kiện có **cùng timestamp**, có thể dùng khóa:

~~~text
(timestamp, sequence_number)
~~~

Trong đó **sequence_number** duy nhất trong phạm vi hợp nhất. Nếu hai heap tạo sequence cục bộ đều bắt đầu từ 0, cần thiết kế thêm cơ chế tránh trùng sequence khi meld để giữ tính ổn định toàn cục.

### 17.3. Thuật toán đồ thị

Các thuật toán như **Dijkstra** hoặc **Prim** thường dùng hàng đợi ưu tiên. Heap nhị thức có thể hỗ trợ decrease-key theo nút/handle khi được cài đặt đầy đủ; điều này có ích khi thuật toán cần giảm một khoảng cách tạm thời.

Tuy nhiên, cấu trúc không tự biết đỉnh nào nằm ở nút nào nếu không có handle hoặc bảng ánh xạ. Cần bảo đảm việc hoán đổi nội dung không làm hỏng định danh đỉnh.

Đặc biệt, với Dijkstra chuẩn, tính đúng đắn còn cần **trọng số cạnh không âm**; chọn binomial heap không thay thế bất biến của thuật toán đồ thị.

### 17.4. Khi nào không nên dùng binomial heap?

Nếu ứng dụng chủ yếu:

- **Push/pop** trên một hàng đợi duy nhất, gần như **không meld**: binary heap trên mảng thường đơn giản và có tính cục bộ bộ nhớ tốt.
- **Tìm khóa bất kỳ, truy vấn khoảng, predecessor/successor**: BST tự cân bằng hoặc mảng đã sắp xếp có thể thích hợp hơn.
- **Cần FIFO tuyệt đối**: một queue thông thường là cấu trúc đúng hơn, trừ khi còn ràng buộc ưu tiên riêng.
- **Cần thường xuyên meld các hàng đợi lớn**: binomial heap là lựa chọn đáng cân nhắc vì meld logarit.

Chọn cấu trúc dựa trên **tập thao tác thực tế** và chi phí của toàn bộ quy trình, không chỉ dựa trên một thao tác nổi bật.

## 18. Bài tập tự luyện có đáp án

**Bài 1 — B₀.** Cây B₀ có bao nhiêu nút, bậc gốc bằng bao nhiêu?

*Đáp án:* **Một nút**, bậc gốc **0**.

**Bài 2 — Số nút của B₅.** Một cây nhị thức B₅ có bao nhiêu nút?

*Đáp án:* **2⁵ = 32 nút**.

**Bài 3 — Bậc và số con.** Gốc B₄ có bao nhiêu con trực tiếp, và những con ấy là gốc của các cây nào?

*Đáp án:* Có **4 con trực tiếp**, lần lượt là gốc các cây **B₃, B₂, B₁, B₀**.

**Bài 4 — Chiều cao.** Cây B₆ có chiều cao tính bằng số cạnh là bao nhiêu?

*Đáp án:* **6**. Chiều cao của Bₖ là k.

**Bài 5 — Hai cây cùng bậc.** Link hai B₂ hợp lệ cho cây mới nào, chứa bao nhiêu nút?

*Đáp án:* Thành **B₃ có 8 nút**. Chọn gốc có khóa ưu tiên hơn làm cha.

**Bài 6 — Khác bậc.** Có được link một B₁ với một B₃ bằng đúng thao tác link chuẩn để tạo B₄ không?

*Đáp án:* **Không**. Link chuẩn chỉ nhận **hai cây cùng bậc**; B₁ + B₃ có 2 + 8 = 10 nút, không bằng kích thước một B₄ (16).

**Bài 7 — Chọn gốc.** Hai min-binomial tree cùng bậc có khóa gốc lần lượt là 12 và 5. Gốc nào thắng?

*Đáp án:* Gốc khóa **5** làm cha, gốc khóa 12 trở thành con trực tiếp của nó.

**Bài 8 — Bảo toàn số nút.** Vì sao phép link không làm tăng hoặc giảm số phần tử?

*Đáp án:* Chỉ thay một số **liên kết giữa hai cây rời nhau**, không tạo hoặc xóa nút; số nút mới là tổng số nút cũ.

**Bài 9 — Heap 13 nút.** Một binomial heap có n = 13 nút phải có những bậc cây gốc nào?

*Đáp án:* **13 = 8 + 4 + 1**, nên các cây **B₀, B₂, B₃**.

**Bài 10 — Heap 31 nút.** Binomial heap có 31 nút chứa tối đa/một cách chính xác những cây bậc nào?

*Đáp án:* **31 = 11111₂**, nên có **B₀, B₁, B₂, B₃, B₄**, tổng cộng 5 cây.

**Bài 11 — Tối đa số gốc.** Tại sao số cây gốc của binomial heap n nút là O(log n)?

*Đáp án:* Mỗi bậc có tối đa một cây, số bậc có thể xuất hiện không vượt số chữ số nhị phân của n, bằng **⌊log₂ n⌋ + 1** khi n > 0.

**Bài 12 — Meld 13 và 7.** Hai heap có 13 và 7 entry. Sau meld, các bậc gốc là gì?

*Đáp án:* **13 + 7 = 20 = 10100₂**, nên **B₂ và B₄**.

**Bài 13 — Tình huống ba cây.** Có ba cây B₂ cùng xuất hiện tại một bậc khi xử lý meld. Phải làm thế nào?

*Đáp án:* **Giữ một B₂**, link hai B₂ còn lại thành **carry B₃**. Không ghép ba cây cùng lúc thành một cây.

**Bài 14 — Carry liên tục.** Heap có 7 nút được thêm một entry mới. Rừng có dạng gì sau khi tất cả carry hoàn tất?

*Đáp án:* **7 + 1 = 8 = 1000₂**; cuối cùng chỉ có **một B₃**.

**Bài 15 — Bậc không phản ánh khóa.** Hai gốc đều có degree = 3 nhưng khóa lần lượt 2 và 99. Chúng có thể link được không?

*Đáp án:* **Có**, vì link yêu cầu **cùng bậc**. Gốc khóa 2 thắng trong min-heap, cây mới là B₄.

**Bài 16 — Tìm min.** Nếu rừng có gốc các cây B₀, B₂, B₃ với khóa gốc lần lượt 8, 3, 5, min toàn heap là bao nhiêu?

*Đáp án:* **3**. Chỉ cần so sánh các gốc, vì gốc mỗi cây là min của cây đó.

**Bài 17 — Peek phức tạp bao nhiêu?** Vì sao peek-min không có min pointer tốn O(log n)?

*Đáp án:* Phải quét tối đa **O(log n) cây gốc**; không cần quét các nút con.

**Bài 18 — Xóa gốc B₄.** Khi xóa gốc nhỏ nhất của một cây B₄, còn lại những cây con nào và tổng bao nhiêu nút?

*Đáp án:* **B₃, B₂, B₁, B₀** với tổng **8 + 4 + 2 + 1 = 15 nút**.

**Bài 19 — Thứ tự danh sách con.** Trong cài đặt child/sibling của bài, các con của B₄ được lưu theo thứ tự bậc nào và tại sao khi extract-min cần đảo?

*Đáp án:* Theo **3, 2, 1, 0**. Danh sách roots yêu cầu tăng dần **0, 1, 2, 3**, nên phải đảo sau khi tách.

**Bài 20 — Kích thước sau extract-min.** Heap có 20 nút, xóa min nằm ở gốc một cây B₄. Sau khi tách và meld lại các con, heap còn bao nhiêu nút?

*Đáp án:* **19 nút**: tháo cây 16 nút khỏi rừng, đưa 15 nút con trở lại, giảm đúng 1.

**Bài 21 — Quyền sở hữu.** Sau khi gọi A.meld_move(B), B có còn được phép sửa trực tiếp những cây đã chuyển đi không?

*Đáp án:* **Không**. Theo hợp đồng move, **B trở thành rỗng** và **A sở hữu các cây**; giữ hai chủ sở hữu sẽ dễ hỏng liên kết.

**Bài 22 — Tự meld.** Vì sao cần từ chối A.meld_move(A)?

*Đáp án:* Một cây có thể bị xử lý hai lần hoặc link với chính nó, gây chu trình/metadata sai; nguồn và đích cũng là một đối tượng nên không thể vừa giữ vừa làm rỗng theo hợp đồng.

**Bài 23 — Binary heap và binomial heap.** Gộp hai binary heap qua nối mảng và heapify tốn bao nhiêu? Binomial heap meld tốn bao nhiêu?

*Đáp án:* Cách binary heap phổ biến tốn **Θ(n+m)**; binomial heap meld hợp lệ tốn **O(log(n+m))** khi n+m dương.

**Bài 24 — Link và meld.** Nếu link hai cây cùng bậc chỉ Θ(1), vì sao toàn bộ meld không nhất thiết Θ(1)?

*Đáp án:* Meld có thể phải link **nhiều cặp cây ở nhiều bậc** do carry lan truyền; cần xử lý O(log(n+m)) bậc.

**Bài 25 — Khóa trùng.** Hai entry có khóa priority = 2. Min-binomial heap có tự giữ thứ tự thêm khi pop không?

*Đáp án:* **Không**. Bất biến chỉ yêu cầu cha ≤ con; nếu cần FIFO khi hòa, phải có tie-breaker như sequence.

**Bài 26 — Decrease-key.** Vì sao giảm khóa một entry trong min-binomial heap thường sửa theo hướng đi lên?

*Đáp án:* Khóa giảm có thể nhỏ hơn cha; cần bubble-up dọc đường cha để khôi phục quan hệ min-heap, tối đa O(log n) mức.

**Bài 27 — Handle.** Nếu decrease-key hoán đổi key/payload giữa các nút, vì sao một tham chiếu tới nút có thể không còn đại diện cùng công việc?

*Đáp án:* Sau swap, **nội dung logic của nút đã đổi**. Phải cập nhật bảng ánh xạ ID → nút hoặc chọn API handle khác.

**Bài 28 — Bộ nhớ phụ.** Mã meld dùng list slots trong bài có O(1) bộ nhớ phụ không?

*Đáp án:* **Không**. Slots và danh sách gốc tạm có kích thước **O(log(n+m+1))**; chỉ các nút dữ liệu là được chuyển nguyên vẹn, không sao chép.

**Bài 29 — Kiểm tra bất biến.** Một heap có roots degree [0, 2, 2]. Vì sao sai dù tổng số nút có thể khớp size?

*Đáp án:* Có **hai cây cùng bậc 2**, vi phạm bất biến “tối đa một cây ở mỗi bậc”. Phải link chúng thành B₃ rồi xử lý carry tiếp.

**Bài 30 — Chọn cấu trúc.** Hệ thống thường xuyên hợp nhất các hàng đợi công việc lớn nhưng cũng cần pop-min. Nên cân nhắc heap nào?

*Đáp án:* **Binomial heap** là ứng viên phù hợp nhờ meld logarit và extract-min logarit. Nếu hiếm khi meld, **binary heap** có thể đơn giản hơn.

## 19. Tổng kết

**Cây nhị thức Bₖ** có **2ᵏ nút**, bậc gốc **k**, chiều cao **k** và các cây con trực tiếp **Bₖ₋₁, ..., B₀**. **Binomial heap** là rừng những cây như vậy, mỗi bậc xuất hiện **tối đa một lần**, nên các bậc gốc đúng bằng **những vị trí bit 1 trong kích thước n**.

Thao tác **link** hai cây Bₖ cùng bậc giữ **gốc ưu tiên hơn** làm cha, chuyển cây còn lại thành một con trực tiếp và tạo Bₖ₊₁ trong **Θ(1)**. Khi meld hai heap, các cây trùng bậc tạo **carry** như phép cộng nhị phân; tổng thời gian là **O(log(n+m))**, không cần sao chép tất cả nút.

Với min-binomial heap **không cache gốc min**, peek-min quét các gốc **O(log n)**. Extract-min tìm gốc nhỏ nhất, xóa gốc ấy, tách các cây con rồi meld lại trong **O(log n)**. Insert bằng meld B₀ cũng có **O(log n) trường hợp xấu nhất**; nếu nói tới phân tích **khấu hao**, phải xét cách cài đặt cụ thể.

**Ghi nhớ:** **Heap nhị thức = rừng Bₖ có bậc không trùng + thứ tự heap trong từng cây + phép hợp nhất theo carry.** Đừng chỉ kiểm tra khóa ở các gốc: phải giữ đúng **degree, parent/child/sibling, size, danh sách bậc và quyền sở hữu nút**. Giá trị nổi bật của cấu trúc là **hợp nhất những hàng đợi ưu tiên đã xây dựng** mà không phải xử lý lại toàn bộ phần tử.
