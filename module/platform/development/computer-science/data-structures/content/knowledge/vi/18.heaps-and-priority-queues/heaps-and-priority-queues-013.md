# Heap ghép cặp (pairing heap) và cách ghép các cây con

**Pairing heap** (*heap ghép cặp*) là một cấu trúc cài đặt **hàng đợi ưu tiên** (*priority queue*) bằng **cây nhiều nhánh có thứ tự heap**. Thay vì duy trì hình dạng cây gần đầy đủ như **binary heap** hoặc một rừng gồm các cây có bậc được kiểm soát như **binomial heap**, pairing heap dựa vào một thao tác rất ngắn: **ghép hai cây bằng cách so sánh khóa ở gốc** (*meld/link*). Khi lấy phần tử ưu tiên nhất ra, những cây con của gốc cũ được ghép lại theo một quy trình **hai lượt** (*two-pass pairing*).

Pairing heap thường được đánh giá cao vì thiết kế thực dụng: **xem min O(1)**, **ghép hai heap O(1)** và **thêm phần tử O(1)** trong mô hình liên kết nút cơ bản. Tuy nhiên, việc xóa min có thể phải xử lý nhiều cây con; vì thế cần phân biệt **độ phức tạp của một lần gọi trong trường hợp xấu nhất** với **độ phức tạp khấu hao** của một chuỗi thao tác. Không có bất biến cân bằng cứng nào bảo đảm mọi cây luôn thấp.

Bài thuộc chương **Heap và hàng đợi ưu tiên** của mô-đun **COMPUTER_SCIENCE_DATA_STRUCTURES**, xây dựng nền tảng cấu trúc dữ liệu qua các bất biến, thao tác, thời gian và bộ nhớ. Trọng tâm là **cách ghép các cây con khi extract-min**, cơ chế meld, những tình huống biên, và sự khác biệt với binary heap/binomial heap.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả pairing heap như **một cây nhiều nhánh** có bất biến **cha ≤ con** đối với min-heap.
- Phân biệt **cây ghép cặp** với **binary heap** và **binomial heap** về hình dạng, bậc nút và cách lưu trữ.
- Giải thích thao tác **meld** hai gốc và cách biến cây thua thành **con đầu tiên** của cây thắng.
- Hiểu tại sao **push** có thể cài bằng meld với một cây một nút.
- Mô phỏng chính xác **extract-min hai lượt**: ghép các cây con liền kề từ trái qua phải, rồi hợp nhất các kết quả từ phải qua trái.
- Phân tích trường hợp số cây con **chẵn, lẻ, 0 hoặc 1**; bảo đảm không bỏ sót cây cuối.
- Viết mã Python dùng các liên kết **parent, first_child, next_sibling** cho phép chuyển cây mà không sao chép từng entry.
- Phát biểu bất biến về **thứ tự heap, cấu trúc cây không có chu trình, quyền sở hữu nút và size**.
- Chứng minh **meld bảo toàn min-heap** và explain vì sao hai lượt không làm mất entry.
- Phân biệt thời gian **O(1)** của meld/insert, **O(n) trường hợp xấu nhất một lần** của extract-min và **O(log n) khấu hao** cho two-pass pairing heap tiêu chuẩn.
- Nhận diện các điều kiện bổ sung khi triển khai **decrease-key, delete theo ID/handle, khóa trùng và tính ổn định**.
- Lựa chọn pairing heap khi các thao tác meld/peek/insert chiếm tỷ trọng lớn.

## 2. Nhắc lại ADT hàng đợi ưu tiên và khóa ưu tiên

Một **min-priority queue** quản lý các entry có **khóa ưu tiên**; entry có khóa nhỏ nhất được phục vụ trước.

Các thao tác cơ bản:

| Thao tác | Ý nghĩa |
| --- | --- |
| **push(key, payload)** | Thêm một entry mới |
| **peek_min()** | Xem entry có khóa nhỏ nhất, không xóa |
| **pop_min() / extract_min()** | Xóa và trả entry có khóa nhỏ nhất |
| **meld(H1, H2)** | Hợp nhất hai hàng đợi, giữ tất cả entry |
| **decrease_key(handle, key_mới)** | Giảm khóa của entry đã có, nếu API hỗ trợ |
| **delete(handle)** | Xóa một entry cụ thể, nếu API hỗ trợ |

*Payload* là dữ liệu công việc đi kèm; **khóa** mới là giá trị quyết định ưu tiên. Nếu payload không có phép so sánh hợp lệ, implementation không được vô tình so sánh payload để quyết định cây nào thắng.

Với **max-priority queue**, thay quan hệ “khóa nhỏ nhất” bằng “khóa lớn nhất”. Bài này trình bày **min-pairing heap**, sau đó chỉ ra điều kiện cần đảo để tạo max-pairing heap.

## 3. Pairing heap thực chất là một cây nhiều nhánh

Một pairing heap không rỗng gồm **một cây có gốc**; mỗi nút có thể có **0, 1, 2 hoặc nhiều con trực tiếp**. Cây **không** bắt buộc là cây nhị phân, cây nhị phân gần đầy đủ hay cây cân bằng.

Bất biến quan trọng nhất với min-pairing heap:

\[
key(parent)\le key(child)
\]

cho **mọi** cạnh cha–con.

Ví dụ:

~~~text
                  1
             /    |    \       \
            4     9     7       3
           / \          |
          8  12         10

Gốc = 1.
Các con trực tiếp của gốc = 4, 9, 7, 3.
Nút 4 có hai con trực tiếp = 8, 12.
Nút 7 có một con trực tiếp = 10.
~~~

Cấu trúc hợp lệ vì mỗi cha không lớn hơn các con trực tiếp của nó. Không có yêu cầu 4 ≤ 9 ≤ 7 ≤ 3 và cũng không có quy tắc BST kiểu “mọi khóa nhánh trái nhỏ hơn mọi khóa nhánh phải”.

### 3.1. Tại sao gốc là min?

Xét đường từ gốc tới một nút bất kỳ:

~~~text
root → child → ... → target
~~~

Vì mọi cạnh đều thỏa **cha ≤ con**, tính bắc cầu cho ta **key(root) ≤ key(target)**. Do đó **gốc chứa một entry có khóa nhỏ nhất toàn heap**.

Nếu có nhiều entry bằng khóa nhỏ nhất, gốc có thể là **một** trong chúng. Pairing heap cơ bản không bảo đảm phần tử được thêm trước sẽ được pop trước.

### 3.2. Những điều pairing heap không bảo đảm

Pairing heap chuẩn **không** bắt buộc:

- Mỗi nút có tối đa hai con.
- Các mức trước mức cuối phải đầy.
- Chiều cao cây luôn O(log n).
- Mỗi bậc nút chỉ xuất hiện một lần.
- Danh sách các con phải có khóa tăng dần.
- Duyệt cây trả entry theo thứ tự đã sắp.
- Tìm một khóa bất kỳ nhanh hơn O(n) nếu không có chỉ mục phụ.

Số con của một nút có thể lớn, vì nhiều lần **meld** có thể liên tục gắn các cây mới làm con trực tiếp của một gốc đang thắng.

### 3.3. Một trường hợp cực đoan: cây hình sao

Nếu gốc luôn có khóa 1 và lần lượt thêm các khóa lớn hơn:

~~~text
push: 1, 8, 3, 7, 9, 4

            1
        / / | \ \
       4 9  7  3 8
~~~

Gốc có **5 con trực tiếp**, dù cây chỉ có **hai mức**. Một lần pop-min phải thu gom và xử lý cả **5 cây con**.

Cây có thể rộng mà thấp, hoặc sâu mà ít con ở nhiều mức. Do đó phân tích chỉ dựa trên chiều cao của binary heap **không áp dụng tự động** cho pairing heap.

## 4. Cách lưu cây: con đầu tiên và anh em kế tiếp

Trong Python, có thể biểu diễn một cây nhiều nhánh bằng các trường:

~~~text
PairingNode:
    key
    payload
    parent         # None nếu là gốc
    first_child    # con trực tiếp đầu tiên; None nếu là lá
    next_sibling   # con trực tiếp kế tiếp cùng cha; None nếu cuối dãy

PairingHeap:
    root           # gốc duy nhất hoặc None
    size           # số entry trong cây
~~~

Với cây:

~~~text
           1
         / | \
        4  9  7
          / \
         10  12
~~~

Các con trực tiếp của 1 tạo chuỗi:

~~~text
root(1).first_child → 4 → 9 → 7 → None
                         (next_sibling)
~~~

Những con trực tiếp của nút 9 cũng có chuỗi riêng:

~~~text
node(9).first_child → 10 → 12 → None
~~~

**Không nên coi next_sibling là cạnh cha–con.** Đó là liên kết giữa **các con cùng một cha**. Khi kiểm tra bất biến thứ tự, cần so sánh từng con với **parent**, không phải so sánh hai sibling với nhau.

### 4.1. Bất biến tham chiếu

Một heap hợp lệ cần các điều kiện:

1. Heap rỗng khi và chỉ khi **root is None** và **size = 0**.
2. Heap không rỗng có **một gốc duy nhất** với **root.parent is None**.
3. **root.next_sibling is None**: gốc không là anh em của nút nào.
4. Mỗi nút khác gốc có **một cha thực**; các nút cùng chuỗi next_sibling đều có cùng parent.
5. Không có chu trình trong các liên kết con/anh em.
6. Mỗi nút thuộc heap **đúng một lần**, và số nút tới được từ gốc đúng bằng size.
7. Mọi liên kết cha–con thỏa **parent.key ≤ child.key**.

Khi meld hoặc tách cây con, việc xóa/cập nhật liên kết cũ quan trọng ngang với việc so sánh khóa.

## 5. Meld: ghép hai cây chỉ bằng một lần so sánh gốc

**Meld** là thao tác nền tảng của pairing heap. Đầu vào là **hai cây min-heap rời nhau** A và B (có thể một cây rỗng); đầu ra là **một cây min-heap** chứa toàn bộ nút của cả hai.

### 5.1. Quy tắc chọn gốc

Nếu:

\[
key(root_A)\le key(root_B),
\]

ta **giữ root_A làm gốc**, đưa **toàn bộ cây B** thành **con đầu tiên** của root_A. Nếu khóa root_B nhỏ hơn, đổi vai trò A và B.

Ví dụ:

~~~text
Cây A:               Cây B:

      3                    5
    /   \                /   \
   8     9              7     6

Meld A và B:

             3
          /  |  \
         5   8   9
        / \
       7   6
~~~

Cây B được chuyển **nguyên vẹn** thành cây con của gốc 3. Không cần chuyển hay so sánh từng nút 5, 7, 6; chỉ cần so sánh khóa **3 và 5**.

### 5.2. Pseudocode

~~~text
meld_min(a, b):
    nếu a rỗng: trả b
    nếu b rỗng: trả a

    yêu cầu a, b là hai gốc của hai cây rời nhau
    yêu cầu parent/sibling của cả hai gốc đang rỗng

    nếu a.key > b.key:
        hoán đổi a và b

    b.parent = a
    b.next_sibling = a.first_child
    a.first_child = b

    trả a
~~~

Các phép gán chỉ thay đổi liên kết ở **gốc hai cây** và một vị trí **first_child**. Trong mô hình nút liên kết với so sánh khóa O(1):

- **Thời gian meld hai cây:** Θ(1).
- **Bộ nhớ phụ:** O(1).
- **Tổng số nút sau meld:** size(A) + size(B).

### 5.3. Tại sao meld đúng?

Giả sử A và B ban đầu đều là min-heap:

- Mọi cạnh bên trong A và B đã đúng, và không thay đổi.
- Chỉ tạo **một cạnh mới** từ gốc thắng tới gốc thua.
- Gốc thắng có khóa **≤** gốc thua, nên cạnh mới hợp lệ.
- Gốc thắng tiếp tục ≤ tất cả nút bên trong cây thua, nhờ tính bắc cầu.
- Hai cây rời nhau được nối bằng một cạnh, nên không sinh chu trình.

Vì vậy, toàn bộ cây sau meld là một min-heap hợp lệ.

### 5.4. Khi hai gốc có khóa bằng nhau

Nếu khóa hai gốc bằng nhau, có thể giữ gốc thứ nhất làm cha để giảm những lần thay đổi không cần thiết. Nhưng điều đó **không đồng nghĩa FIFO** cho toàn bộ hàng đợi: các lần meld và extract-min về sau vẫn có thể đổi thứ tự giữa những entry có khóa bằng nhau.

Nếu ứng dụng cần FIFO trong nhóm cùng priority, dùng **khóa so sánh phụ** như (priority, sequence) với sequence **duy nhất trong cả hai heap** khi được hợp nhất.

## 6. Push và peek: hai thao tác trở nên đơn giản

### 6.1. Thêm một phần tử bằng meld

Một entry mới tạo thành **cây một nút**:

~~~text
push(2, payload):

    2
~~~

Sau đó, lấy gốc cũ của heap và gốc mới **meld** với nhau.

~~~text
Trước:
       3
     / | \
    5  6  7

Thêm khóa 2:
       2
       |
       3
     / | \
    5  6  7
~~~

Do chỉ cần một nút mới và **một phép meld**:

- **Push:** Θ(1) thời gian cho liên kết và so sánh khóa (giả định cấp phát nút O(1)).
- **Bộ nhớ thêm cho entry:** O(1) đối với nút mới.
- **Hình dạng cây:** Không phải giữ complete shape hay tính chỉ số cha như binary heap.

Nếu khóa mới lớn hơn hoặc bằng gốc cũ, nút mới sẽ được gắn làm **con đầu tiên** của gốc cũ, thay vì lên gốc.

### 6.2. Xem min

Vì gốc là min:

~~~text
peek_min() = (root.key, root.payload)
~~~

- **Thời gian:** Θ(1).
- **Không sửa** bất cứ liên kết nào.
- Trên heap rỗng, cần trả kết quả thiếu hoặc báo lỗi theo hợp đồng API.

### 6.3. Meld hai đối tượng heap và quyền sở hữu

Nếu ta có hai đối tượng **H1** và **H2**, một API an toàn có thể định nghĩa **meld_move(H2)**:

- Ghép hai **root** bằng thao tác meld O(1).
- Cập nhật **H1.size = H1.size + H2.size**.
- Làm **H2.root = None**, **H2.size = 0**.
- Không sao chép các nút cũ.

Việc làm rỗng nguồn giúp tránh trường hợp **hai đối tượng heap cùng sở hữu một cây** rồi chỉnh sửa độc lập, gây hỏng parent/sibling. Phải **từ chối H1.meld_move(H1)**, vì không thể ghép một cây với chính nó mà vẫn giữ cấu trúc cây không chu trình.

## 7. Vấn đề của extract-min: những cây con trở thành các heap riêng

Giả sử pairing heap có gốc 1 và năm con trực tiếp:

~~~text
                    1
               / /  |  \ \
              4 9   7   3 8
~~~

Khi **extract-min**:

1. Đọc và giữ entry (1, payload).
2. Xóa gốc 1 khỏi cây.
3. Các cây con trực tiếp **4, 9, 7, 3, 8** trở thành **năm heap độc lập**.
4. Phải **ghép lại thành một cây duy nhất** để tiếp tục làm priority queue.

Không thể chỉ chọn một cây con làm gốc rồi bỏ các cây còn lại. Cũng không thể chỉ nối các gốc bằng next_sibling rồi gọi đó là một pairing heap: kết quả không có một gốc chung và không bảo đảm bất biến parent/sibling.

### 7.1. Cách đơn giản nhưng không phải quy tắc hai lượt

Ta có thể meld tất cả các cây con lần lượt:

~~~text
result = cây đầu tiên
for mỗi cây còn lại từ trái sang phải:
    result = meld(result, cây)
~~~

Cách này vẫn **bảo toàn bất biến heap**, nhưng **khác** thuật toán **two-pass pairing** tiêu chuẩn. Trình tự ghép là một phần quan trọng của thiết kế và những phân tích khấu hao.

Không nên khẳng định mọi thứ tự meld tùy ý đều có cùng bảo đảm hiệu năng khấu hao như thuật toán hai lượt.

## 8. Two-pass pairing: hai lượt ghép cây con

Đây là nội dung trung tâm của bài.

Sau khi tách gốc min, giả sử các cây con trực tiếp theo thứ tự **trái sang phải** là:

~~~text
T0, T1, T2, T3, T4, ..., T(k-1)
~~~

### 8.1. Lượt 1 — ghép từng cặp kề nhau từ trái qua phải

Ghép:

~~~text
P0 = meld(T0, T1)
P1 = meld(T2, T3)
P2 = meld(T4, T5)
...
~~~

Nếu **k lẻ**, cây con cuối cùng không có bạn ghép thì **giữ nguyên** làm một phần tử trong danh sách kết quả của lượt 1.

Ví dụ năm cây con:

~~~text
Trước:
[T0, T1, T2, T3, T4]

Ghép cặp:
  meld(T0, T1) → P0
  meld(T2, T3) → P1
  T4 giữ nguyên

Sau lượt 1:
[P0, P1, T4]
~~~

### 8.2. Lượt 2 — hợp nhất các kết quả từ phải sang trái

Bắt đầu từ **phần tử cuối** danh sách kết quả của lượt 1, rồi lần lượt meld với phần tử đứng ngay bên trái:

~~~text
result = T4
result = meld(P1, result)
result = meld(P0, result)
~~~

Khi hết danh sách, chỉ còn **một cây** — gốc mới của pairing heap.

Lược đồ tổng quát:

~~~text
pair_groups = các nhóm sau lượt 1
result = cây cuối trong pair_groups

for group từ áp chót về đầu:
    result = meld(group, result)

root_mới = result
~~~

**Thứ tự cần nhớ:**

- Lượt 1: **trái → phải**, ghép **cặp kề nhau**.
- Lượt 2: **phải → trái**, lần lượt ghép các **kết quả đã hình thành**.

Trong cài đặt với liên kết, việc “trái/phải” chỉ **thứ tự trên chuỗi next_sibling**, không có nghĩa pairing heap là cây nhị phân.

### 8.3. Pseudocode đầy đủ cho extract-min

~~~text
extract_min(heap):
    nếu heap rỗng: báo lỗi

    old_root = heap.root
    answer = entry của old_root

    children = []
    cursor = old_root.first_child

    while cursor != None:
        next_cursor = cursor.next_sibling
        cursor.parent = None
        cursor.next_sibling = None
        thêm cursor vào children
        cursor = next_cursor

    # Lượt 1: ghép từng cặp kề nhau.
    pairs = []
    i = 0
    while i < len(children):
        nếu i + 1 < len(children):
            thêm meld(children[i], children[i+1]) vào pairs
            i = i + 2
        ngược lại:
            thêm children[i] vào pairs
            i = i + 1

    # Lượt 2: từ phải qua trái.
    result = None
    for group trong pairs theo thứ tự ngược:
        result = meld(group, result)

    heap.root = result
    heap.size = heap.size - 1
    trả answer
~~~

**Lưu ý:** Việc gán **cursor.next_sibling = None** trước khi meld là thiết yếu: mỗi cây con phải trở thành **một gốc độc lập**. Nếu để lại liên kết sibling từ danh sách con cũ, một gốc có thể vô tình kéo theo cả chuỗi gốc khác khi gắn vào cây thắng.

## 9. Mô phỏng cụ thể: năm cây con và hai lượt meld

Xét heap trước khi lấy min:

~~~text
                  1
              / / | \ \
             4 9  7  3 8

Thứ tự các con trực tiếp:
[4, 9, 7, 3, 8]

Để tập trung vào phép ghép, giả sử cả năm nút con
đều là các cây một nút.
~~~

Ta gọi **pop_min()**, giữ kết quả **1** và thu được năm cây gốc có khóa 4, 9, 7, 3, 8.

### 9.1. Lượt 1: trái sang phải

Cặp thứ nhất:

~~~text
meld(4, 9)

  4
  |
  9

P0 có gốc 4.
~~~

Cặp thứ hai:

~~~text
meld(7, 3)

  3
  |
  7

P1 có gốc 3.
~~~

Cây cuối **8** không có cặp, được giữ nguyên.

~~~text
Sau lượt 1:
[ P0(root=4), P1(root=3), T4(root=8) ]
~~~

### 9.2. Lượt 2: phải sang trái

Bắt đầu từ cây cuối gốc **8**:

~~~text
result = 8
~~~

Ghép với P1 gốc 3:

~~~text
meld(3, 8) → gốc 3

      3
     / \
    8   7
~~~

Ghép tiếp với P0 gốc 4:

~~~text
meld(4, result_gốc_3) → gốc 3

        3
       /|\
      4 8 7
      |
      9
~~~

Cây cuối vẫn có đủ năm entry **{3, 4, 7, 8, 9}**, gốc là 3 — khóa nhỏ nhất sau khi bỏ 1.

### 9.3. Bảng truy vết

| Bước | Những cây được ghép | Gốc thắng | Số cây ở mức đang xét |
| --- | --- | --- | ---: |
| Tách gốc 1 | Các gốc 4, 9, 7, 3, 8 | Chưa có | 5 |
| Lượt 1, cặp 1 | 4 và 9 | 4 | 4 |
| Lượt 1, cặp 2 | 7 và 3 | 3 | 3 |
| Lượt 1, cây lẻ | Giữ riêng 8 | 8 | 3 |
| Lượt 2, bước 1 | P1(gốc 3) và 8 | 3 | 2 |
| Lượt 2, bước 2 | P0(gốc 4) và cây gốc 3 | 3 | 1 |

Đếm số phép meld: với **k = 5 cây con**, cuối cùng cần đúng **k − 1 = 4** phép meld để tạo lại một cây. Hai lượt chỉ quy định **thứ tự ghép**, chứ không tạo thêm hay mất bớt entry.

### 9.4. Điều gì xảy ra khi mỗi cây con có cả một cây con riêng?

Một gốc con có thể đại diện cho **hàng trăm nút**. Khi meld hai cây, ta chỉ so sánh **hai khóa ở gốc** và chỉnh một số liên kết; toàn bộ nút nằm dưới hai gốc vẫn ở nguyên cây cũ.

Đó là lý do trong bước two-pass, chi phí trực tiếp phụ thuộc chủ yếu vào **số cây con của gốc bị xóa**, không phải việc phải duyệt lại từng entry trong mọi cây con.


## 10. Các trường hợp biên khi ghép cây con

Gọi **k** là số con trực tiếp của gốc bị xóa, không phải tổng số nút n trong heap.

| Số cây con k | Lượt 1 | Lượt 2 | Số phép meld |
| ---: | --- | --- | ---: |
| 0 | Không có | Gốc mới = None | 0 |
| 1 | Giữ T₀ | Gốc mới = T₀ | 0 |
| 2 | Ghép T₀, T₁ | Giữ kết quả | 1 |
| 3 | Ghép T₀,T₁; giữ T₂ | Ghép kết quả với T₂ | 2 |
| 4 | Ghép T₀,T₁ và T₂,T₃ | Ghép hai kết quả | 3 |
| 5 | Ghép T₀,T₁ và T₂,T₃; giữ T₄ | Ghép từ phải sang trái | 4 |
| k bất kỳ | Ghép ⌊k/2⌋ cặp; giữ cây dư | Ghép các kết quả ngược chiều | k−1 khi k≥1 |

- **Heap một nút:** pop trả phần tử duy nhất, gốc mới là None và size = 0.
- **Gốc có một con:** cây con duy nhất thành gốc mới, cần gán parent = None.
- **k lẻ:** cây cuối không có cặp phải được giữ để tham gia lượt hai; không được bỏ sót.
- **Các cây con có hàng nghìn nút:** mỗi meld chỉ xem khóa của **hai gốc**, không duyệt toàn bộ hậu duệ.
- **Khóa gốc bằng nhau:** một gốc bất kỳ có thể thắng mà vẫn thỏa min-heap, nhưng FIFO khi hòa khóa không được bảo đảm.

## 11. Chứng minh tính đúng đắn của two-pass pairing

Giả sử trước pop-min, heap gồm một cây hợp lệ với n entry, không có chu trình, và mọi cạnh cha–con đều thỏa khóa cha ≤ con.

### 11.1. Bỏ gốc không phá bất biến trong các cây con

Bỏ gốc cũ chỉ bỏ các cạnh từ gốc ấy đến các con trực tiếp. Mọi cạnh nội bộ trong mỗi cây con vẫn đúng. Sau khi đặt parent/next_sibling của các gốc con về None, ta thu được k **min-heap rời nhau**, bảo toàn tất cả entry trừ gốc bị lấy.

### 11.2. Mỗi phép meld giữ đủ entry và bất biến

Meld hai cây rời có kích thước a và b bằng cách giữ gốc nhỏ hơn làm cha, gắn cây còn lại dưới cha ấy. Cạnh mới thỏa cha ≤ con, các cạnh cũ không đổi, nên tạo một min-heap có **a+b** entry. Số cây giảm đúng một.

### 11.3. Hai lượt luôn đưa về một cây

- Đầu lượt một, tất cả cây Tᵢ hợp lệ và rời nhau.
- Mỗi Pᵢ sau khi ghép cặp cũng là một min-heap hợp lệ.
- Cây dư khi k lẻ vẫn hợp lệ.
- Lượt hai tiếp tục ghép các min-heap rời từ phải sang trái.

Với k ≥ 1 cây con, cần **k−1 phép meld** để còn một cây, không mất hoặc nhân đôi entry. Vì xóa đúng một gốc ban đầu:

\[
size_{\text{sau}}=size_{\text{trước}}-1.
\]

Gốc cuối cùng là một entry có khóa nhỏ nhất trong toàn bộ phần còn lại; không cần sắp các anh em theo thứ tự khóa.

## 12. Python tự chứa: min-pairing heap ghép hai lượt

Ví dụ cho Python 3.10 trở lên. Mã chỉ so sánh **key**, không so sánh payload. Các nút lưu **parent, first_child, next_sibling**, còn heap lưu **root và size**.

Giao diện gồm **push**, **peek_min**, **meld_move**, **pop_min**, **root_child_keys** và **check_invariants**. Chưa hỗ trợ decrease-key hay delete theo handle.

~~~python
from __future__ import annotations


class PairingNode:
    def __init__(self, key, payload=None):
        self.key = key
        self.payload = payload
        self.parent: PairingNode | None = None
        self.first_child: PairingNode | None = None
        self.next_sibling: PairingNode | None = None


class PairingHeap:
    def __init__(self):
        self._root: PairingNode | None = None
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def is_empty(self) -> bool:
        return self._size == 0

    @staticmethod
    def _meld(
        a: PairingNode | None,
        b: PairingNode | None,
    ) -> PairingNode | None:
        """Hai cây độc lập, gốc không có parent hoặc sibling."""
        if a is None:
            return b
        if b is None:
            return a

        assert a is not b
        assert a.parent is None and a.next_sibling is None
        assert b.parent is None and b.next_sibling is None

        if a.key > b.key:
            a, b = b, a

        # Gắn toàn bộ cây b làm con đầu tiên của a.
        b.parent = a
        b.next_sibling = a.first_child
        a.first_child = b
        return a

    @staticmethod
    def _two_pass(
        first_child: PairingNode | None,
    ) -> PairingNode | None:
        """Ghép cặp trái->phải, rồi hợp nhất phải->trái."""
        if first_child is None:
            return None

        # Tách mọi cây con khỏi chuỗi sibling cũ.
        children: list[PairingNode] = []
        current = first_child

        while current is not None:
            next_child = current.next_sibling
            current.parent = None
            current.next_sibling = None
            children.append(current)
            current = next_child

        # Lượt 1: cặp kề nhau, giữ cây cuối nếu số lẻ.
        groups: list[PairingNode] = []
        i = 0

        while i < len(children):
            if i + 1 < len(children):
                root = PairingHeap._meld(children[i], children[i + 1])
                assert root is not None
                groups.append(root)
                i += 2
            else:
                groups.append(children[i])
                i += 1

        # Lượt 2: gom từ phải sang trái.
        result: PairingNode | None = None
        for tree in reversed(groups):
            result = PairingHeap._meld(tree, result)

        return result

    def meld_move(self, other: PairingHeap) -> None:
        """Chuyển tất cả nút của other vào self; other thành rỗng."""
        if self is other:
            raise ValueError("Không được tự meld heap")

        if other._root is None:
            return

        self._root = self._meld(self._root, other._root)
        self._size += other._size

        other._root = None
        other._size = 0

    def push(self, key, payload=None) -> None:
        node = PairingNode(key, payload)
        self._root = self._meld(self._root, node)
        self._size += 1

    def peek_min(self):
        if self._root is None:
            raise IndexError("Heap rỗng")
        return self._root.key, self._root.payload

    def pop_min(self):
        if self._root is None:
            raise IndexError("Heap rỗng")

        removed = self._root
        answer = removed.key, removed.payload

        self._root = self._two_pass(removed.first_child)
        self._size -= 1

        # Không để nút đã bị xóa còn giữ liên kết đến cây mới.
        removed.first_child = None
        removed.parent = None
        removed.next_sibling = None
        return answer

    def root_child_keys(self):
        """Quan sát danh sách khóa con trực tiếp, từ trái qua phải."""
        if self._root is None:
            return []

        result = []
        child = self._root.first_child
        while child is not None:
            result.append(child.key)
            child = child.next_sibling
        return result

    def check_invariants(self) -> set[int]:
        """Kiểm chứng toàn bộ cây: O(n) thời gian, bộ nhớ."""
        if self._root is None:
            assert self._size == 0
            return set()

        assert self._size > 0
        assert self._root.parent is None
        assert self._root.next_sibling is None

        visited: set[int] = set()
        stack = [(self._root, None)]

        while stack:
            node, expected_parent = stack.pop()
            node_id = id(node)

            assert node_id not in visited, "Trùng nút hoặc chu trình"
            visited.add(node_id)
            assert node.parent is expected_parent

            child = node.first_child
            siblings_seen = set()

            while child is not None:
                child_id = id(child)
                assert child_id not in siblings_seen, "Vòng sibling"
                siblings_seen.add(child_id)
                assert child.parent is node
                assert node.key <= child.key
                stack.append((child, node))
                child = child.next_sibling

        assert len(visited) == self._size
        return visited


# Ví dụ two-pass với 5 con [4, 9, 7, 3, 8].
heap = PairingHeap()
heap.push(1)
for key in [8, 3, 7, 9, 4]:
    heap.push(key)
    heap.check_invariants()

assert len(heap) == 6
assert heap.peek_min() == (1, None)
assert heap.root_child_keys() == [4, 9, 7, 3, 8]

assert heap.pop_min() == (1, None)
assert heap.peek_min() == (3, None)
assert heap.root_child_keys() == [4, 8, 7]
heap.check_invariants()

values = []
while not heap.is_empty():
    values.append(heap.pop_min()[0])
    heap.check_invariants()

assert values == [3, 4, 7, 8, 9]


# Meld hai heap độc lập, không sao chép nút.
left = PairingHeap()
right = PairingHeap()

for key in [5, 2, 9]:
    left.push(key)
for key in [7, 1, 8]:
    right.push(key)

left_ids = left.check_invariants()
right_ids = right.check_invariants()
assert not (left_ids & right_ids)

left.meld_move(right)
assert len(left) == 6
assert right.is_empty()
assert right.check_invariants() == set()
assert left.peek_min() == (1, None)
assert left.check_invariants() == left_ids | right_ids

result = []
while not left.is_empty():
    result.append(left.pop_min()[0])
assert result == [1, 2, 5, 7, 8, 9]


# Rỗng, một nút và khóa bằng nhau.
empty = PairingHeap()
single = PairingHeap()
single.push(-7, "khẩn")
empty.meld_move(single)

assert single.is_empty()
assert empty.peek_min() == (-7, "khẩn")
assert empty.pop_min() == (-7, "khẩn")
assert empty.is_empty()


class Task:
    def __init__(self, name):
        self.name = name


a = Task("A")
b = Task("B")
ties = PairingHeap()
ties.push(2, a)
ties.push(2, b)
ties.check_invariants()

popped = [ties.pop_min(), ties.pop_min()]
assert [item[0] for item in popped] == [2, 2]
assert {item[1] for item in popped} == {a, b}


# Từ chối thao tác không hợp lệ.
try:
    empty.meld_move(empty)
except ValueError:
    pass
else:
    raise AssertionError("Tự meld phải bị từ chối")

try:
    empty.pop_min()
except IndexError:
    pass
else:
    raise AssertionError("Pop trên heap rỗng phải báo lỗi")
~~~

### 12.1. Đọc phép meld theo các liên kết

Ba phép gán cốt lõi là:

~~~python
b.parent = a
b.next_sibling = a.first_child
a.first_child = b
~~~

Chúng đặt cây b làm con đầu tiên của cây a. Không cần sao chép payload hoặc duyệt các nút bên trong hai cây.

### 12.2. Đọc hàm two-pass

Trước khi ghép các cây con, cần đặt **parent = None** và **next_sibling = None** ở từng gốc con. Phải lưu biến next_child **trước khi xóa sibling**, nếu không sẽ mất đường tới các cây còn lại.

Lượt một ghép từng cặp kề nhau, giữ cây dư nếu k lẻ. Lượt hai dùng **reversed(groups)** để meld từ phải sang trái. Với một cây con, meld(cây, None) trả cây ấy; với không cây con, kết quả là None.

### 12.3. Kiểm tra sâu không thuộc chi phí push

Hàm **check_invariants** duyệt tất cả n nút, dùng tập visited và stack, nên tốn **Θ(n) thời gian và O(n) bộ nhớ phụ**. Nó chỉ phục vụ kiểm chứng; không được cộng vào thuật toán cốt lõi rồi vẫn báo toàn bộ lời gọi là O(1).

Các assertion là ví dụ để bước kiểm thử và QA chuyên môn tiếp theo đối chiếu. Theo giới hạn STEP 4, worker không chạy mã Python hoặc vòng QA học thuật trong lúc soạn bài.

### 12.4. Phạm vi của lớp

Lớp này chưa có **decrease-key theo handle**, **delete theo ID** hoặc chỉ mục ID → nút. Những thao tác đó cần quản lý liên kết cắt nút và quyền sở hữu chặt chẽ hơn.


## 13. Độ phức tạp: worst-case và amortized không giống nhau

Gọi **n** là số entry trong heap trước thao tác và **d** là số con trực tiếp của gốc được xóa.

### 13.1. Các thao tác chỉ nhìn vào gốc

Trong mô hình thao tác con trỏ và so sánh khóa O(1):

| Thao tác | Thời gian của mã Python | Bộ nhớ phụ |
| --- | --- | --- |
| Tạo heap rỗng | **Θ(1)** | O(1) |
| Meld hai cây rời | **Θ(1)** | O(1) |
| meld_move hai heap | **Θ(1)** | O(1) |
| Push một nút mới | **Θ(1)**, giả sử cấp phát nút O(1) | O(1) ngoài nút mới |
| Peek min | **Θ(1)** | O(1) |
| Đọc d khóa con trực tiếp của gốc | **Θ(d)** | O(d) cho kết quả |
| Kiểm tra toàn bộ bất biến | **Θ(n)** | O(n) |

Điểm mạnh của pairing heap là **meld** không cần duyệt toàn bộ hai heap. Một cây có rất nhiều nút vẫn có thể trở thành con của gốc thắng bằng cách đổi vài con trỏ.

### 13.2. Chi phí của một lần pop-min

Với d cây con:

- Tách d con khỏi gốc cũ: **Θ(d)**.
- Lượt một thực hiện **⌊d/2⌋** phép meld.
- Lượt hai hoàn tất phần còn lại.
- Tổng số phép meld nếu d ≥ 1 là **d − 1**.

Vì vậy, số thao tác liên kết trong **một lời gọi pop-min** là:

\[
\Theta(d+1).
\]

Pairing heap không buộc d = O(log n). Một gốc có thể có **d = n − 1**, nên **thời gian xấu nhất của một lần pop-min là Θ(n)**.

**Dãy ví dụ đạt cực đoan:** Thêm khóa 1 trước, rồi thêm n−1 khóa lớn hơn 1. Gốc 1 luôn thắng và nhận thêm một con trực tiếp sau mỗi push. Khi xóa gốc 1, phải xử lý n−1 cây con.

### 13.3. Two-pass pairing có bảo đảm khấu hao

Với **pairing heap hai lượt tiêu chuẩn**, kết quả phân tích khấu hao của thuật toán cho **extract-min O(log n) khấu hao** trong mô hình cấu trúc liên kết thông thường.

Đọc kết quả đó đúng cách:

- **Worst-case một lần:** có thể Θ(n), do d lớn.
- **Amortized trên một chuỗi thao tác:** chi phí của các lần delete-min được phân bổ theo sự thay đổi cấu trúc để đạt O(log n) khấu hao theo kết quả phân tích tiêu chuẩn.
- **Không phải kỳ vọng xác suất:** không cần giả định đầu vào ngẫu nhiên.
- **Không phải cam kết độ trễ mỗi lời gọi:** nếu hệ thống bắt buộc từng pop không vượt ngưỡng logarit, cận amortized không đủ.

Chứng minh định lý khấu hao đầy đủ cho pairing heap phức tạp hơn việc chỉ đếm số con của một nút. Bài này phân biệt rõ **kết luận amortized đã được biết** với **chứng minh cục bộ** chỉ bảo đảm tính đúng đắn và chi phí Θ(d) của một lời gọi.

### 13.4. Bộ nhớ của phiên bản dùng list

Lớp PairingHeap dùng hai list tạm **children** và **groups** trong thao tác two-pass. Chúng chứa **tham chiếu tới các cây**, không sao chép nút/payload.

- **Bộ nhớ phụ của pop-min:** **O(d)**, trường hợp xấu nhất O(n).
- **Bộ nhớ lưu n entry:** O(n) cho n nút, mỗi nút có một số trường hằng số.
- **Push:** thêm đúng một nút, O(1) bộ nhớ mới.
- **Meld:** không sao chép các nút, O(1) bộ nhớ phụ.
- **Kiểm chứng bằng visited:** O(n) bộ nhớ phụ, tách khỏi chi phí cốt lõi.

Một cài đặt two-pass theo con trỏ có thể giảm cấp phát list tạm, nhưng phải phân tích chi phí và kiểm tra việc cắt liên kết đúng theo chính phiên bản ấy.

### 13.5. Không được dùng công thức bậc của binomial heap

Trong **binomial heap**, mỗi bậc xuất hiện tối đa một cây Bₖ; số gốc O(log n). Trong **pairing heap**, một gốc đơn lẻ có thể nhận n−1 con. Không có bất biến **mỗi bậc một cây** để giới hạn d.

Cũng không thể lấy chiều cao O(log n) của **binary heap** áp cho pairing heap vì pairing heap **không có bất biến complete binary tree**.

## 14. Decrease-key và delete: vì sao cần thiết kế thêm liên kết?

Các thuật toán đồ thị và lập lịch đôi khi cần thay khóa ưu tiên của một entry **đã tồn tại**. Đây là bài toán khó hơn push vì phải biết **entry nằm ở đâu trong cây**.

### 14.1. Ý tưởng decrease-key ở min-heap

Giả sử một entry có khóa 8 được giảm thành 2:

~~~text
Cha có khóa 5, con có khóa 8:
       5
       |
       8

Sau đổi khóa thành 2:
       5
       |
       2    (vi phạm 5 <= 2)
~~~

Một hướng thường dùng với pairing heap:

1. Thay khóa entry bằng khóa mới nhỏ hơn hoặc bằng cũ.
2. Nếu entry không phải gốc, **cắt cả cây con gốc entry** khỏi danh sách con của cha.
3. Đặt parent/next_sibling của entry thành None.
4. **Meld cây vừa cắt với gốc heap**.

Sau meld, min-heap được khôi phục vì liên kết cũ gây vi phạm đã bị bỏ và cạnh mới được tạo bằng cách chọn gốc nhỏ hơn.

### 14.2. Handle tới nút vẫn chưa bảo đảm cut O(1)

Trong lớp của bài, nút chỉ có:

~~~text
parent
first_child
next_sibling
~~~

Nếu entry cần cắt là **con thứ tư** của cha, ta không có con trỏ tới **anh em ngay trước nó**. Để tháo nút khỏi chuỗi sibling, có thể phải duyệt từ **parent.first_child**, tốn tới O(số con của cha), mà số đó có thể Θ(n).

Một biến thể hỗ trợ cut O(1) cần thêm **prev_sibling** hoặc một **back-pointer** có quy tắc cập nhật chặt chẽ. Nếu dùng bảng ID → nút để tìm entry, cũng phải duy trì nó khi thao tác làm thay đổi cây hoặc nội dung entry.

**Meld O(1) không tự suy ra decrease-key O(1)** nếu vẫn phải tìm hoặc cắt nút trước đó.

### 14.3. Giới hạn amortized của decrease-key

Những kết quả về decrease-key trong các biến thể pairing heap **phụ thuộc chi tiết thuật toán và mô hình phân tích**. Không nên mặc định mọi pairing heap đạt **O(1) amortized decrease-key** chỉ bởi vì thao tác cut+meld nhìn có vẻ ngắn.

Lớp Python ở mục 12 **chưa triển khai decrease-key**. Vì thế, không được gán cho nó một độ phức tạp thực thi của thao tác chưa được cung cấp.

### 14.4. Delete theo ID và delete theo handle khác nhau

- **Delete theo ID:** Nếu cây được tổ chức theo priority, tìm một ID tùy ý có thể mất O(n) nếu không có chỉ mục phụ.
- **Delete theo handle:** Có thể bỏ qua bước tìm ID nhưng phải bảo đảm handle còn hợp lệ và chỉ đúng nút thuộc heap; cắt nút và duy trì liên kết vẫn cần xử lý.
- **Delete bằng sentinel ưu tiên thấp nhất:** Có thể giảm khóa mục tiêu thành một khóa đặc biệt nhỏ nhất rồi pop; phải bảo đảm sentinel thực sự ưu tiên hơn mọi khóa khác và chọn đúng entry nếu khóa trùng.

Khi thiết kế API thực tế, luôn ghi rõ **handle là gì, do ai sở hữu, thay đổi thế nào sau meld hoặc pop, và những thao tác nào làm handle không còn hợp lệ**.

## 15. Khóa bằng nhau, tính ổn định và payload

### 15.1. Min-heap cho phép khóa bằng nhau

Bất biến là **cha ≤ con**, không phải cha < con. Hai entry có key = 2 đều hợp lệ. Nhưng pairing heap cơ bản **không bảo đảm FIFO** giữa các entry cùng khóa.

Việc hàm meld chọn đối số thứ nhất khi khóa bằng nhau chỉ giải quyết một phép link cục bộ; nó không thể bảo đảm thứ tự đến sau một chuỗi push, meld và pop.

### 15.2. Dùng khóa kép khi cần FIFO theo ưu tiên

Một cách phổ biến là:

~~~text
(priority, sequence_number)
~~~

Trong đó sequence tăng theo thứ tự đến, duy nhất **trên toàn bộ những heap có thể hợp nhất**.

Với Python, tuple được so sánh theo thứ tự từ trái qua phải. Ví dụ dùng lớp PairingHeap ở mục 12:

~~~python
queue = PairingHeap()
queue.push((2, 0), "Công việc A")
queue.push((1, 1), "Công việc khẩn")
queue.push((2, 2), "Công việc B")

assert queue.pop_min() == ((1, 1), "Công việc khẩn")
assert queue.pop_min() == ((2, 0), "Công việc A")
assert queue.pop_min() == ((2, 2), "Công việc B")
~~~

Payload chỉ được **trả về**, không được so sánh. Nếu hai heap tự cấp sequence từ 0 một cách độc lập rồi meld, có thể xảy ra **trùng sequence**; để đảm bảo FIFO toàn cục cần phối hợp bộ đếm hoặc thêm một khóa phụ khác.

### 15.3. Khóa phải có quan hệ so sánh nhất quán

Nếu khóa là số, tuple hoặc đối tượng tùy chỉnh, thao tác meld phải so sánh chúng theo một **quan hệ thứ tự nhất quán**. Trộn kiểu dữ liệu không hỗ trợ so sánh trong Python 3 có thể dẫn tới TypeError.

Không nên dùng payload để phân xử khóa hòa nếu payload không có ý nghĩa thứ tự nghiệp vụ.

## 16. So sánh với binary heap và binomial heap

| Tính chất | Binary min-heap | Binomial min-heap | Pairing min-heap |
| --- | --- | --- | --- |
| Hình dạng | Một cây nhị phân gần đầy đủ | Rừng các cây Bₖ theo bậc | Một cây nhiều nhánh tự điều chỉnh |
| Biểu diễn thường dùng | Mảng theo mức | Parent/child/sibling | First-child/next-sibling |
| Bất biến | Cha ≤ con | Cha ≤ con trong từng cây | Cha ≤ con |
| Peek min | **O(1)** | O(log n) nếu quét các gốc | **O(1)** |
| Insert | O(log n) | O(log n) worst-case | **O(1)** |
| Meld hai heap độc lập | Thường Θ(n+m) bằng nối và heapify | **O(log(n+m))** | **O(1)** |
| Extract min | O(log n) theo mô hình heap | O(log n) worst-case | **O(log n) khấu hao**, worst-case một lần Θ(n) |
| Số con của một nút | Tối đa 2 | Theo hình dạng Bₖ | **Không giới hạn cố định** |
| Tìm ID tùy ý | Cần chỉ mục phụ | Cần chỉ mục phụ | Cần chỉ mục phụ |
| Chi phí triển khai | Thường thấp | Phải quản lý bậc và carry | Meld đơn giản; cut và two-pass cần cẩn thận |

Bảng mô tả những cách cài đặt tiêu chuẩn. Binary heap dùng mảng động có thể tốn thêm chi phí cấp phát lại trong một lời gọi append cụ thể; cận O(log n) của push là theo mô hình heap hoặc phân tích khấu hao cấp phát mảng.

Binomial heap có thể giữ thêm con trỏ min để peek O(1), nhưng phải cập nhật nó sau meld/extract-min. Tương tự, các biến thể heap nâng cao có những chi phí khác tùy bất biến và metadata.

### 16.1. Lựa chọn theo tải công việc

- **Binary heap:** thường phù hợp khi cần push/pop đơn giản, ít hợp nhất và muốn tận dụng biểu diễn mảng.
- **Binomial heap:** phù hợp khi muốn meld nhanh hơn việc nối dữ liệu rồi heapify, đồng thời có bất biến bậc rõ ràng.
- **Pairing heap:** phù hợp khi cần **meld, push, peek rất nhanh** và chấp nhận phân tích **khấu hao** cho extract-min.
- **BST tự cân bằng hoặc mảng sắp xếp:** phù hợp hơn nếu thường xuyên tìm khóa bất kỳ hoặc truy vấn khoảng, vì heap không có quy tắc phân vùng khóa như BST.


## 17. Ứng dụng và tiêu chí lựa chọn pairing heap

### 17.1. Hợp nhất hàng đợi ưu tiên từ nhiều nhóm

Giả sử dịch vụ A đang giữ 1000 công việc, dịch vụ B giữ 2000 công việc. Nếu mỗi hàng đợi được cài bằng một pairing heap hợp lệ, **meld_move** có thể hợp nhất chúng bằng cách so sánh hai gốc và thay liên kết:

~~~text
A: root key = 3, size = 1000
B: root key = 1, size = 2000

Sau A.meld_move(B):
A: root key = 1, size = 3000
B: root = None,  size = 0
~~~

Không phải sao chép hay heapify lại tất cả 3000 entry. Hợp đồng **move** nghĩa là B nhường các cây, không còn được sửa nút cũ độc lập. Nếu ứng dụng cần giữ hai heap nguồn không đổi, phải dùng bản sao hoặc cấu trúc có ngữ nghĩa chia sẻ dữ liệu được thiết kế riêng.

### 17.2. Hệ thống lập lịch công việc

Một bộ lập lịch có thể liên tục **thêm công việc mới**, **xem công việc ưu tiên nhất**, **lấy công việc ưu tiên nhất** và thỉnh thoảng **ghép các hàng chờ**.

Pairing heap thuận tiện khi push/peek/meld xuất hiện thường xuyên. Tuy nhiên, nếu hệ thống đặt yêu cầu độ trễ chặt cho **từng** lần pop, phải tính tới một lời gọi extract-min có thể tốn Θ(n), dù bảo đảm khấu hao là O(log n).

Heap không tự quy định việc có được **ngắt một tác vụ đang chạy** hay không. Nó chỉ quản lý thứ tự ưu tiên của những entry còn nằm trong hàng đợi.

### 17.3. Mô phỏng sự kiện theo thời gian

Khóa ưu tiên có thể là **timestamp**. Các bộ mô phỏng con giữ những heap độc lập, sau đó meld để tạo một lịch sự kiện chung.

Nếu hai sự kiện có timestamp bằng nhau nhưng cần xử lý theo thứ tự xác định, dùng khóa kép **(timestamp, sequence)** với sequence **duy nhất trên toàn bộ các heap có thể meld**.

### 17.4. Thuật toán đồ thị và decrease-key

Các thuật toán như Dijkstra và Prim thường dùng priority queue. Pairing heap có thể là một cách cài đặt, nhưng nếu thuật toán yêu cầu **giảm khóa của một đỉnh theo ID**, phải bổ sung bảng ánh xạ, handle và thao tác cut có chi phí được chứng minh.

Với Dijkstra chuẩn, tính đúng đắn còn phụ thuộc **trọng số cạnh không âm**, không chỉ phụ thuộc kiểu priority queue được dùng.

### 17.5. Khi nào không nên sử dụng?

Nếu bài toán cần **FIFO thuần túy**, một queue thông thường dễ dùng hơn. Nếu thường xuyên **tìm một khóa bất kỳ hoặc truy vấn khoảng**, BST tự cân bằng có thể phù hợp hơn. Nếu cần push/pop đơn giản mà hầu như không meld, binary heap lưu mảng thường dễ triển khai hơn. Chọn pairing heap khi lợi ích từ **meld và insert hằng số** thực sự quan trọng đối với tải công việc.

## 18. Lỗi thường gặp khi ghép các cây con

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi pairing heap là cây nhị phân | Không biểu diễn được nút nhiều con | Dùng danh sách con/anh em |
| Giả định chiều cao luôn O(log n) | Phân tích sai worst-case | Không có bất biến cân bằng cứng |
| Meld bằng cách duyệt từng entry | Bỏ lợi thế O(1) | Chỉ so sánh khóa của hai gốc |
| Gắn gốc lớn hơn làm cha trong min-heap | Vi phạm cha ≤ con | Giữ gốc có khóa nhỏ hơn làm cha |
| Quên gán child.parent | Liên kết cha/con sai | Cập nhật parent khi meld |
| Quên nối child.next_sibling với con đầu cũ | Làm mất các con cũ | Nối sibling trước khi đổi first_child |
| So sánh sibling với nhau như quan hệ heap | Kiểm tra sai bất biến | Chỉ so sánh **cha với con** |
| Pop xóa gốc nhưng bỏ các cây con | Mất dữ liệu | Thu thập và meld toàn bộ cây con |
| Xóa sibling trước khi lưu next_child | Mất đường đi qua các con kế tiếp | Lưu next_child trước |
| Không gán parent=None khi tách cây con | Gốc mới trỏ tới gốc đã bị xóa | Cắt parent cũ |
| Chỉ meld từng cây từ trái qua phải nhưng gọi là two-pass | Khác thuật toán được phân tích | Lượt một theo cặp, lượt hai từ phải sang trái |
| Bỏ cây dư khi số con lẻ | Mất một cây con | Giữ cây cuối làm nhóm riêng |
| Đưa vào meld hai gốc còn nối sibling | Dễ xuất hiện alias/chu trình | Tách sạch các gốc trước |
| Không cập nhật size sau pop | Size không khớp số nút | Giảm đúng 1 |
| Meld nhưng không làm rỗng heap nguồn | Hai đối tượng cùng sở hữu một cây | Dùng hợp đồng chuyển quyền sở hữu |
| Cho phép tự meld | Có thể tạo chu trình hoặc metadata sai | Từ chối self is other |
| Cho rằng pop O(log n) worst-case | Gốc có thể có n−1 con | Phân biệt Θ(n) worst-call và O(log n) khấu hao |
| Cho rằng phiên bản dùng list phụ trợ O(1) bộ nhớ pop | Hai list tạm tăng theo d | Ghi nhận O(d) bộ nhớ phụ |
| Coi meld O(1) là decrease-key O(1) | Cut có thể phải duyệt sibling | Phân tích riêng cơ chế cắt |
| Gắn priority vào payload sai sau khi đổi khóa | Xử lý sai công việc | Di chuyển nguyên entry/định nghĩa handle rõ |
| Nghĩ khóa trùng tự có FIFO | Thứ tự entry hòa không được bảo đảm | Dùng sequence toàn cục |
| Gọi validate Θ(n) sau mọi push rồi ghi tổng O(1) | Tính thiếu chi phí | Tách kiểm thử khỏi thao tác |

### Cách tự kiểm tra bằng tay

Với một lần pop-min, hãy ghi **size cũ**, **gốc bị xóa**, thứ tự **mọi cây con trực tiếp**, kết quả sau các cặp ở lượt một và kết quả meld từ phải sang trái ở lượt hai. Kiểm tra **parent=None** ở các gốc trước khi ghép, gốc cuối có khóa nhỏ nhất, số nút giảm đúng một và nút cũ không còn được tham chiếu như cha.

Thử các giá trị **k=0,1,2,3,4,5,6** và một trường hợp có **cây con không chỉ một nút**. Việc thử cả số chẵn và số lẻ giúp phát hiện lỗi bỏ sót cây cuối.

## 19. Bài tập tự luyện có đáp án

**Bài 1 — Bất biến.** Một min-pairing heap yêu cầu điều kiện nào trên mọi cạnh?

*Đáp án:* **key(cha) ≤ key(con)**.

**Bài 2 — Hình dạng.** Pairing heap có bắt buộc là cây nhị phân gần đầy đủ không?

*Đáp án:* **Không**. Đây là cây nhiều nhánh, không có bất biến complete binary tree.

**Bài 3 — Peek.** Vì sao peek-min là Θ(1)?

*Đáp án:* Gốc luôn là một entry có khóa nhỏ nhất toàn heap; chỉ cần đọc gốc.

**Bài 4 — Meld.** Hai cây hợp lệ có khóa gốc 7 và 2. Gốc nào thắng trong min-heap?

*Đáp án:* **2** làm cha, toàn bộ cây gốc 7 trở thành con trực tiếp của gốc 2.

**Bài 5 — Bảo toàn entry.** Meld một heap 9 entry với heap 4 entry cho bao nhiêu entry?

*Đáp án:* **13 entry**, không có bản sao hoặc entry bị xóa.

**Bài 6 — Push.** Cách thêm một entry trong pairing heap thực hiện qua thao tác nào?

*Đáp án:* Tạo **cây một nút** rồi **meld** với gốc cũ.

**Bài 7 — Gốc hình sao.** Nếu push lần lượt 1, 8, 3, 7, 9, 4 bằng phép gắn cây thua làm con đầu, gốc 1 có bao nhiêu con?

*Đáp án:* **5 con**, thứ tự trực tiếp **[4, 9, 7, 3, 8]**.

**Bài 8 — Xóa gốc.** Sau khi pop 1 ở bài 7, cần xử lý bao nhiêu cây con?

*Đáp án:* **5 cây con**.

**Bài 9 — Lượt một.** Với năm cây T₀,T₁,T₂,T₃,T₄, lượt một ghép thế nào?

*Đáp án:* **meld(T₀,T₁)**, **meld(T₂,T₃)**, giữ **T₄** làm nhóm riêng.

**Bài 10 — Lượt hai.** Nếu sau lượt một có [P₀,P₁,T₄], thứ tự ghép là gì?

*Đáp án:* **meld(P₁,T₄)**, sau đó **meld(P₀,kết quả)**.

**Bài 11 — Gốc mới.** Với năm gốc con [4,9,7,3,8], sau two-pass gốc mới có khóa bao nhiêu?

*Đáp án:* **3**.

**Bài 12 — Các con của gốc mới.** Theo quy tắc gắn cây thua làm con đầu, gốc 3 trong bài 11 có các con nào?

*Đáp án:* **[4, 8, 7]**; trong đó nút 4 còn có con 9.

**Bài 13 — Đếm meld.** Với k=8 cây con, cần bao nhiêu phép meld để còn một cây?

*Đáp án:* **7 phép**, vì mỗi meld giảm số cây đúng một.

**Bài 14 — Heap một nút.** Pop-min trên heap chỉ có khóa 5 tạo trạng thái gì?

*Đáp án:* Trả **5**, heap thành rỗng (root=None, size=0).

**Bài 15 — Gốc một con.** Gốc 2 có con duy nhất 6. Sau pop-min, gốc mới là gì?

*Đáp án:* **6**, với parent=None.

**Bài 16 — Cây dư.** Tại sao không bỏ qua cây thứ năm trong lượt một?

*Đáp án:* Nó vẫn chứa entry; bỏ qua sẽ làm mất một cây và vi phạm size.

**Bài 17 — Cắt sibling.** Vì sao phải lưu next_child trước khi gán current.next_sibling=None?

*Đáp án:* Để còn đường đi tới những cây con tiếp theo trong danh sách cũ.

**Bài 18 — Meld tự thân.** Vì sao phải từ chối H.meld_move(H)?

*Đáp án:* Hai đầu vào không rời nhau; có thể tạo chu trình và không thể thực hiện đúng hợp đồng chuyển quyền sở hữu.

**Bài 19 — Chuyển cây.** Sau A.meld_move(B), B còn sở hữu các nút cũ không?

*Đáp án:* **Không**. B trở thành rỗng; A sở hữu toàn bộ cây hợp nhất.

**Bài 20 — Worst-case.** Nếu gốc có n−1 con, một lần pop-min có thể tốn bao nhiêu thời gian?

*Đáp án:* **Θ(n)**, do phải xử lý từng cây con.

**Bài 21 — Amortized.** O(log n) khấu hao có nghĩa mọi lời gọi pop-min đều O(log n) không?

*Đáp án:* **Không**. Một lời gọi có thể Θ(n); amortized đánh giá chi phí phân bổ của chuỗi thao tác.

**Bài 22 — Bộ nhớ phụ.** Mã Python tạo danh sách children/groups dùng bao nhiêu bộ nhớ phụ khi gốc có d con?

*Đáp án:* **O(d)** tham chiếu, có thể O(n) trong trường hợp xấu nhất.

**Bài 23 — Decrease-key.** Chỉ có next_sibling và parent, vì sao cắt con thứ năm không chắc O(1)?

*Đáp án:* Có thể cần duyệt các sibling từ con đầu để tìm nút ngay trước vị trí cần cắt.

**Bài 24 — Khóa trùng.** Pairing heap có tự bảo đảm FIFO cho hai entry cùng priority không?

*Đáp án:* **Không**. Dùng khóa phụ sequence nếu cần tính ổn định.

**Bài 25 — Max-pairing heap.** Khi chuyển sang max-heap, quy tắc meld thay đổi thế nào?

*Đáp án:* Chọn gốc có **khóa lớn hơn hoặc bằng** làm cha; trình tự ghép cây con hai lượt giữ nguyên.

**Bài 26 — So sánh meld.** Nếu có hai binary heap kích thước n, m và hai pairing heap cùng kích thước, cách meld phổ biến có chi phí gì?

*Đáp án:* Nối hai binary heap rồi heapify tốn **Θ(n+m)**; pairing heap meld bằng thay liên kết gốc tốn **Θ(1)**.

**Bài 27 — Tìm ID.** Pairing heap có tự tìm một ID bất kỳ trong O(1) không?

*Đáp án:* **Không**. Nếu không có chỉ mục phụ có thể phải duyệt tới O(n) nút.

**Bài 28 — Độ trễ nghiêm ngặt.** Hệ thống yêu cầu cận worst-case O(log n) cho mỗi lần xóa min. Có nên dựa duy nhất vào cận khấu hao của pairing heap không?

*Đáp án:* **Không**. Cần cấu trúc và mô hình lưu trữ có bảo đảm worst-case thích hợp cho từng lời gọi.

## 20. Tổng kết

**Pairing heap** là **một cây nhiều nhánh có thứ tự heap**. Với min-heap, mọi cha ≤ con nên gốc có khóa nhỏ nhất; **peek-min Θ(1)**.

**Meld** giữ gốc ưu tiên hơn và chuyển nguyên cây thua thành **con đầu tiên** của gốc thắng trong **Θ(1)**. **Push** chỉ tạo một nút rồi meld, cũng Θ(1) với giả định cấp phát nút O(1).

Khi **pop-min**, bỏ gốc cũ và tách tất cả cây con. Thuật toán **two-pass pairing** ghép **từng cặp kề nhau từ trái sang phải**, giữ cây lẻ nếu có, rồi **meld các kết quả từ phải sang trái** cho tới khi còn một gốc.

Một lần pop-min xử lý d cây con nên có chi phí **Θ(d+1)**; trường hợp xấu nhất của một lời gọi có thể **Θ(n)**. Với two-pass pairing heap chuẩn, **extract-min có O(log n) khấu hao** trên chuỗi thao tác, nhưng không phải cận worst-case cho từng lời gọi.

**Ghi nhớ:** **Pairing heap = cây nhiều nhánh có thứ tự heap + meld hai gốc O(1) + ghép hai lượt khi xóa gốc.** Phải giữ đúng **parent, first_child, next_sibling, size và quyền sở hữu nút**. Muốn hỗ trợ decrease-key, cần tính thêm chi phí tìm/cắt nút và quản lý handle.
