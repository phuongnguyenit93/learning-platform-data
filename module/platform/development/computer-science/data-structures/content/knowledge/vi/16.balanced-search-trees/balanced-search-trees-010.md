# So sánh AVL với đỏ–đen theo tra cứu, cập nhật và thông tin phụ

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả **bất biến AVL** và **bất biến Red–Black Tree (cây đỏ–đen)**, chỉ ra chúng cùng bảo đảm chiều cao **O(log n)** nhưng không áp đặt cùng mức cân bằng.
- Phân biệt độ phức tạp **tiệm cận trong trường hợp xấu nhất** với số phép so sánh, phép quay, lần đổi màu và chi phí truy cập bộ nhớ trong thực tế.
- So sánh thao tác **tìm chính xác, tìm cận, duyệt theo thứ tự, truy vấn khoảng, chèn, xóa và cập nhật khóa** trên hai cây.
- Giải thích vì sao **AVL thường có đường tìm ngắn hơn về mặt giới hạn chiều cao**, còn **Red–Black Tree có giới hạn số phép quay khi cập nhật thuận lợi trong các thuật toán chuẩn**, nhưng **không có cấu trúc luôn nhanh hơn** trên mọi tải công việc.
- Liệt kê thông tin phụ cần lưu ở mỗi nút: **chiều cao/hệ số cân bằng** với AVL, **màu đỏ/đen** với Red–Black; phân biệt metadata bắt buộc với các trường **`parent`, `size`, min/max, giá trị tổng hợp** tùy thiết kế.
- Xây dựng một thí nghiệm so sánh công bằng, có chỉ số theo dõi **so sánh khóa, phép quay, số nút, chiều cao, tính đúng đắn và bộ nhớ**, tránh suy diễn từ Big O.
- Lựa chọn cấu trúc phù hợp cho chỉ mục bài học, danh mục có thứ tự và các mẫu đọc/ghi khác nhau.

## 1. Vấn đề: cùng là BST cân bằng, tại sao phải so sánh?

Trong nền tảng học cấu trúc dữ liệu, giả sử danh mục bài học cần ba loại truy vấn:

1. Tìm một bài theo **mã khóa có thứ tự**.
2. Liệt kê các bài có thời lượng trong khoảng từ 20 đến 45 phút.
3. Thêm bài mới, gỡ bài cũ và chỉnh sửa thời lượng thường xuyên.

Một **cây tìm kiếm nhị phân (BST)** duy trì điều kiện: mọi khóa trong cây con trái nhỏ hơn khóa tại nút, mọi khóa cây con phải lớn hơn khóa tại nút. Nếu chỉ sử dụng BST thường, chuỗi khóa tăng dần có thể tạo ra cây lệch một phía:

```text
Chèn 10, 20, 30, 40 vào BST thường:

10
  \
   20
     \
      30
        \
         40
```

Khi đó tìm một khóa có thể phải đi qua **O(n)** nút trong trường hợp xấu nhất.

**AVL** và **Red–Black Tree (RB Tree)** đều là những cách hiện thực **ordered Set/Map** bằng BST có thêm bất biến để khống chế chiều cao. Cả hai có thể giữ thời gian **O(log n) trường hợp xấu nhất** cho tìm, chèn và xóa. Tuy nhiên, chúng khác nhau ở:

- **Mức độ cân bằng hình dạng:** AVL kiểm soát chênh lệch chiều cao **trực tiếp**, RB Tree dùng **màu và black-height**.
- **Công việc sửa sau cập nhật:** AVL cập nhật chiều cao và quay; RB Tree đổi màu và quay.
- **Thông tin phụ mỗi nút:** một số đo chiều cao/BF so với một trạng thái màu.
- **Chi phí thực tế:** số bước đọc nút, truy cập bộ nhớ, cache, bộ cấp phát, giá của phép so sánh khóa và chi phí duy trì nhiều chỉ mục.

> Câu hỏi chọn AVL hay RB Tree là câu hỏi về **mẫu thao tác, bảo đảm cần có và chi phí triển khai**, không thể trả lời chỉ bằng “cả hai đều O(log n)”.

## 2. Điểm chung: bất biến thứ tự BST và tập thao tác

Nếu khóa phân biệt và dùng phép so sánh có thứ tự toàn phần nhất quán, cả hai cây đều hỗ trợ:

```text
                    40
                  /    \
                20      60
               /  \    /  \
              10  30  50  70

Tìm 50: 40 -> 60 -> 50.
Tìm 25: 40 -> 20 -> 30 -> nhánh rỗng.
Inorder: 10, 20, 30, 40, 50, 60, 70.
```

Những thao tác cốt lõi có cùng ý tưởng:

| Thao tác | Quy tắc BST dùng chung | Điều kiện cần để nhanh |
| --- | --- | --- |
| `find(k)` | So sánh tại nút, đi trái/phải | Chiều cao nhỏ |
| `min/max` | Đi hết sang trái/phải | Đường gốc–lá ngắn |
| `lower_bound(k)` | Tìm khóa nhỏ nhất ≥ `k`, giữ ứng viên khi rẽ trái | Chiều cao nhỏ |
| `upper_bound(k)` | Tìm khóa nhỏ nhất > `k` | Chiều cao nhỏ |
| `successor/predecessor` | Tìm khóa kế tiếp/trước đó theo thứ tự | Có thể đi lên tổ tiên hoặc tìm từ gốc |
| `range(lo, hi)` | Tìm cận dưới rồi duyệt khóa trong khoảng | Có thứ tự + đường tìm ngắn |
| `insert(k)` | Chèn lá theo vị trí khóa | Sau chèn phải khôi phục cân bằng |
| `delete(k)` | Xóa lá, nối một con, hoặc thay bằng successor/predecessor | Sau xóa phải khôi phục cân bằng |

Với `n` nút và `k` khóa được trả về, cả AVL lẫn RB Tree hợp lệ có thể thực hiện:

\[
\text{find/insert/delete/lower\_bound}=O(\log n),\qquad
\text{range}=O(\log n+k).
\]

Kết quả khoảng O(log n + k) giả định sử dụng **bộ duyệt có khả năng đi tới phần tử kế tiếp** qua ngăn xếp hoặc `parent`, không thực hiện lại tìm từ gốc cho từng kết quả. Nếu lọc bằng duyệt toàn bộ cây, chi phí có thể là O(n), dù cây vẫn cân bằng.

**Không** có cấu trúc nào bảo đảm tra cứu mọi khóa bằng O(1) trường hợp xấu nhất chỉ từ hai bất biến cân bằng này. Nếu không cần thứ tự, **bảng băm** là lựa chọn khác với O(1) kỳ vọng cho tìm theo khóa, đổi lại không tự hỗ trợ `lower_bound` và duyệt khóa tăng dần.

## 3. AVL: ràng buộc chiều cao chặt

### 3.1. Bất biến AVL

Quy ước chiều cao **theo số nút**:

\[
h(\varnothing)=0,\qquad
h(v)=1+\max(h(v.left),h(v.right)).
\]

Đặt hệ số cân bằng:

\[
BF(v)=h(v.left)-h(v.right).
\]

Cây AVL hợp lệ khi **mọi nút** thỏa:

\[
BF(v)\in\{-1,0,+1\}.
\]

```text
Ví dụ AVL hợp lệ:

             30 (h=3, BF=+1)
            /   \
       20(h=2)  40(h=1)
         /
      10(h=1)

Nhánh trái cao 2, nhánh phải cao 1: gốc vẫn hợp lệ.
```

AVL **không yêu cầu mọi nhánh cao bằng nhau**. Nó cho phép chênh lệch tối đa một mức tại từng nút, khác với khái niệm cây nhị phân hoàn hảo.

### 3.2. Vì sao giới hạn chiều cao chặt hơn?

Gọi `N(h)` là **số nút tối thiểu** của một AVL chiều cao `h` (đếm số nút trên đường dài nhất):

\[
N(0)=0,\quad N(1)=1,\quad
N(h)=1+N(h-1)+N(h-2)\quad(h\ge2).
\]

Để chiều cao của cây đạt `h` với ít nút nhất, một nhánh có chiều cao `h-1`, nhánh còn lại `h-2`; chênh lệch lớn hơn sẽ vi phạm AVL. Dãy này tăng theo **Fibonacci**:

\[
N(h)=F_{h+2}-1,
\]

với `F_0=0`, `F_1=1`. Do `F_m` tăng theo `\varphi^m` với `\varphi=(1+\sqrt5)/2`, suy ra:

\[
h_{\mathrm{AVL}}=O(\log n).
\]

Một cận trên hữu ích để hình dung là `h_{\mathrm{AVL}}\lesssim1{,}44\log_2(n+2)` khi chiều cao tính theo số nút; đây là **cận xấp xỉ**, không phải số mức đúng của mọi cây.

**Ý nghĩa thực tiễn:** AVL kiểm soát chênh lệch độ cao **tại mỗi nút**, nên các đường tìm có **giới hạn chiều dài chặt** hơn cận của RB Tree. Nhưng “cận chặt hơn” **không đồng nghĩa** mọi lần tìm trong AVL đều đi ít nút hơn cùng một RB Tree bất kỳ.

## 4. Red–Black Tree: cân bằng bằng màu và black-height

### 4.1. Các bất biến màu

RB Tree là BST thỏa các điều kiện theo quy ước phổ biến:

1. Mỗi nút thật có màu **RED** hoặc **BLACK**.
2. Gốc màu **BLACK** nếu cây không rỗng.
3. Mọi vị trí thiếu con được xem là **lá `NIL` màu BLACK**.
4. Không có nút **RED** có con **RED**.
5. Từ một nút đến mọi lá `NIL` hậu duệ đều có **cùng số nút đen**, với một cách đếm thống nhất.

```text
                  20(B)
                 /     \
              10(R)   30(R)
              /   \   /   \
             NIL NIL NIL NIL

B = đen; R = đỏ; mọi NIL cũng màu đen.
```

Cây trên hợp lệ dù hai con của gốc đều **đỏ**. Quy tắc cấm là **đỏ–đỏ trực tiếp**, không phải “mọi con của nút đen đều đen”.

### 4.2. Chiều cao đen

Đặt `bh(v)` là **số nút đen trên đường từ ngay sau `v` tới lá `NIL`**, **không tính chính `v` nhưng tính `NIL` cuối đường**.

Với mỗi đường, số nút đỏ không thể tăng tùy ý vì không được có hai nút đỏ liên tiếp. Đồng thời black-height đồng đều buộc cây có đủ số nút ở các nhánh.

Đặt `h_{\mathrm{RB}}` là chiều cao theo **số cạnh** tới nút thật sâu nhất. Cận quen thuộc là:

\[
h_{\mathrm{RB}}\le2\log_2(n+1).
\]

Nếu tính theo **số nút** trên đường dài nhất, cộng thêm một cho cây không rỗng:

\[
h_{\mathrm{RB,nodes}}\le2\log_2(n+1)+1.
\]

Như vậy RB Tree cũng giữ `O(\log n)`, nhưng cho phép **nhiều hình dạng hợp lệ hơn** AVL. Trong những hình dạng xấu nhất, đường tìm của RB Tree có thể dài hơn về cận trên.

### 4.3. Không nhầm độ cao với black-height

| Khái niệm | AVL | RB Tree |
| --- | --- | --- |
| `height` | Chiều dài đường dài nhất; thường lưu ở mỗi nút | Có thể tính, nhưng **không bắt buộc phải lưu** |
| `BF` | Chênh chiều cao trái–phải; phải trong `{-1,0,+1}` | **Không dùng** làm bất biến sửa cân bằng |
| `color` | Không bắt buộc | RED/BLACK; bắt buộc trong biểu diễn màu |
| `black-height` | Không có vai trò trong bất biến AVL | Số nút đen trên các đường; thường **không lưu riêng** |

Một RB Tree đúng màu **không nhất thiết** thỏa `|BF|\le1` tại mọi nút. Ngược lại, một AVL có thể không được tô màu theo bất kỳ quy tắc RB nào nếu chưa xây dựng một cách tô màu thích hợp. Hai thuật toán sửa **không hoán đổi trực tiếp** cho nhau.

## 5. So sánh tra cứu: chiều cao, số lần rẽ nhánh và truy vấn khoảng

### 5.1. Tìm chính xác và tìm cận

Một lần `find(k)` thực hiện tối đa một số lần so sánh tỷ lệ với **số nút ghé qua** trên đường gốc–lá. Vì cả hai cây có chiều cao O(log n), cùng đạt **O(log n) trường hợp xấu nhất**.

Nếu chọn AVL để tối ưu đọc nhiều, lợi thế lý thuyết là **giới hạn chiều cao chặt hơn**. Nhưng độ trễ thực tế còn chịu ảnh hưởng bởi:

- Cấu trúc hình thành từ **thứ tự chèn/xóa đã xảy ra**, không chỉ số lượng khóa.
- Mức độ **trúng cache** của những nút trên đường tìm.
- Phép so sánh khóa (số nguyên, chuỗi, khóa ghép nhiều trường).
- Cách cấp phát nút, sự phân mảnh bộ nhớ và cách đóng gói `color`/`height`.
- Trình biên dịch, runtime, con trỏ `parent` và chất lượng thư viện.

Vì vậy chỉ nên nói: **AVL có thể phù hợp với tải đọc nặng vì cân bằng chặt**, không nói “AVL chắc chắn tìm nhanh hơn RB Tree” nếu chưa đo trên dữ liệu tương ứng.

### 5.2. Duyệt có thứ tự

Cả hai cấu trúc đều cho **dãy inorder tăng dần**. Nếu đã đến phần tử đầu tiên trong khoảng, có thể dùng ngăn xếp hoặc liên kết cha để tiến tới các phần tử tiếp theo với **O(k)** công việc duyệt tổng cộng, cộng O(log n) để tìm điểm bắt đầu.

Ví dụ cần tìm mọi bài có thời lượng từ 20 đến 45 phút:

```text
Khóa sắp xếp (phút, ID):

(15, "ds-intro")
(20, "ds-array")
(30, "ds-queue")
(30, "ds-stack")
(45, "ds-graph")
(60, "ds-tree")

range [20,45] -> trả đúng 4 khóa trong khoảng.
```

Cần dùng khóa ghép `(duration_minutes, lesson_id)` thay vì chỉ `duration_minutes` nếu mỗi nút đại diện **một bài duy nhất**: hai bài cùng 30 phút không được coi là một khóa trùng nhau khi dữ liệu cần giữ cả hai.

### 5.3. Tìm nhỏ nhất/lớn nhất và lấy hàng xóm

`min`/`max` đi theo một đường trái/phải, nên mất O(log n) xấu nhất cho cả hai. Nếu có một nút và tham chiếu `parent`, tìm successor có thể tiến từ cây con phải hoặc leo lên cha; một bước successor có thể tốn O(log n) xấu nhất, nhưng **duyệt nhiều phần tử kế tiếp theo thứ tự có tổng chi phí tuyến tính theo số nút đã đi qua**.

Không nên gán toàn bộ sự khác biệt hiệu năng của duyệt khoảng cho màu hay BF: cách thiết kế bộ duyệt và truy cập bộ nhớ có thể quan trọng hơn một vài mức chiều cao.

## 6. So sánh chèn: AVL quay theo BF, RB đổi màu theo cha–chú–ông

### 6.1. Quy trình chèn AVL

1. Tìm vị trí chèn theo BST và tạo nút lá.
2. Đi ngược lên các tổ tiên, tính lại `height` và `BF`.
3. Nếu một tổ tiên `z` có `BF(z)=+2` hoặc `-2`, nhận diện **LL, RR, LR, RL**.
4. Thực hiện **một quay đơn hoặc một quay kép** tại **tổ tiên mất cân bằng thấp nhất**.
5. Nối gốc cây con mới trở lại cha, giữ các cây con ở giữa đúng khoảng khóa.

```text
AVL: chèn 30, 20, 10

Trước sửa:                     Sau quay phải tại 30:

        30 (BF=+2)                      20
        /                              /   \
      20 (BF=+1)                      10   30
      /
    10
```

Trong **một lần chèn vào AVL đang hợp lệ**, thuật toán chuẩn cần **tối đa hai phép quay đơn** (một quay kép được tính là hai quay đơn). Sau khi sửa tại điểm lệch đầu tiên, chiều cao cây con quay thường trở lại như trước chèn, nên không có nhu cầu quay tiếp ở những tổ tiên cao hơn chỉ do lần chèn ấy.

**Dù tối đa hai quay, chèn AVL vẫn O(log n)**: tìm vị trí và cập nhật các tổ tiên tốn O(log n).

### 6.2. Quy trình chèn Red–Black

1. Chèn như BST nhưng tô **nút mới màu đỏ**; hai con là `NIL` đen.
2. Nếu cha đen, kết thúc mà không quay.
3. Nếu cha đỏ, xét **chú**:
   - **Chú đỏ:** tô cha/chú đen, ông đỏ, **đẩy vi phạm lên ông**.
   - **Chú đen:** dùng một hoặc hai phép quay theo hình dạng thẳng/gấp và đổi màu.
4. Tô gốc đen ở cuối.

```text
RB: chèn 10, 20, 30

Trước sửa:                      Sau quay trái và đổi màu:

     10(B)                               20(B)
        \                                /    \
        20(R)                          10(R)  30(R)
           \
           30(R)
```

Trong thuật toán chèn Red–Black chuẩn, một lần chèn cũng cần **tối đa hai phép quay đơn**, nhưng có thể có **nhiều lần đổi màu liên tiếp qua các tổ tiên**. Vì vậy:

- **Số quay** không đủ để khẳng định thời gian chèn là O(1).
- **Đổi màu** không phải lúc nào đồng nghĩa một phép quay.
- **Độ dài đường tìm** vẫn là O(log n).

### 6.3. Trường hợp cùng dữ liệu nhưng sửa khác nhau

Chèn lần lượt `10, 5, 15, 1`:

- Với **RB Tree**, `10(B)` có hai con `5(R),15(R)`; chèn `1(R)` dưới `5(R)` tạo cha đỏ và **chú đỏ `15(R)`**. Có thể **đổi màu** `5,15` thành đen, `10` đỏ rồi tô gốc đen: **không cần quay**.
- Với **AVL**, sau các khóa đó, một hình dạng hợp lệ có `10` ở gốc, `5` ở trái, `15` ở phải, `1` ở trái của `5`; BF gốc +1, BF ở `5` +1, nên **cũng không cần quay**.

Ví dụ cho thấy một phép chèn có thể **không quay ở cả hai cấu trúc**, nhưng lý do kiểm tra bất biến khác nhau. Không thể suy từ “một RB Tree đổi màu” rằng “AVL chắc chắn phải quay”.

## 7. So sánh xóa: sự khác biệt thường rõ hơn lúc chèn

### 7.1. Cả hai bắt đầu bằng xóa BST

Nếu cần xóa khóa `k`:

- **Không có con thật:** bỏ nút lá.
- **Có một con thật:** nối con duy nhất lên vị trí nút bị xóa.
- **Có hai con thật:** dùng **successor/predecessor** hoặc một chiến lược chuyển nút vật lý tương đương, rồi xóa vị trí thay thế cũ.

Sau bước cấu trúc, AVL kiểm soát **chiều cao**, RB Tree kiểm soát **màu và số nút đen trên đường đi**.

### 7.2. Xóa AVL có thể quay qua nhiều cấp

Xóa có thể làm chiều cao một cây con **giảm một mức**, khiến `BF` ở cha chuyển từ ±1 thành ±2. Sau khi quay đúng, chiều cao của cây con **có thể tiếp tục giảm**, làm tổ tiên cao hơn cũng lệch.

```text
Trước xóa tại tổ tiên p:

    h(p.left) = 3
    h(p.right) = 4
    BF(p) = -1 (hợp lệ)

Sau xóa sâu trong cây trái:

    h(p.left) = 2
    h(p.right) = 4
    BF(p) = -2 (cần sửa).
```

Một lần **xóa AVL** có thể cần **O(log n) phép quay đơn tính cả các quay kép** trên nhiều tổ tiên. Dù vậy, mỗi quay O(1), tổng toàn thao tác vẫn **O(log n)**.

**Chú ý trường hợp BF của con nặng bằng 0:** trong xóa AVL, nếu `BF(z)=+2` và `BF(z.left)=0`, quay phải đơn là phù hợp; nếu `BF(z)=-2` và `BF(z.right)=0`, quay trái đơn. Không áp dụng mù quáng điều kiện chỉ dùng cho chèn.

### 7.3. Xóa Red–Black có thể truyền “thiếu đen” lên trên

Nếu nút thật sự bị loại khỏi vị trí cấu trúc là **đỏ**, black-height thường không mất nút đen. Nếu nó **đen** và nút thay thế là **đỏ**, có thể **tô nút thay thế thành đen**. Nếu cả vị trí bỏ và nút thay thế đều đen (kể cả `NIL`), một nhánh có thể **thiếu một nút đen**.

Thuật toán sửa xóa thường xét **anh/em `w`** của nút thay thế `x`:

| Tình trạng anh/em | Hành động điển hình | Hệ quả |
| --- | --- | --- |
| Anh/em **đỏ** | Đổi màu và quay ở cha | Biến sang trường hợp anh/em đen để xét tiếp |
| Anh/em **đen**, hai con đen | Tô anh/em đỏ, đưa thiếu đen lên cha | Có thể lan qua nhiều tổ tiên |
| Anh/em **đen**, con gần đỏ, con xa đen | Quay tại anh/em và đổi màu | Chuyển sang trường hợp con xa đỏ |
| Anh/em **đen**, con xa đỏ | Đổi màu và quay tại cha | Khôi phục black-height tại cụm và kết thúc sửa |

Trong thuật toán sửa xóa Red–Black tiêu chuẩn kiểu CLRS, **số phép quay trong một lần xóa bị chặn bởi 3**, dù việc đổi màu hoặc chuyển thiếu đen lên cha vẫn có thể xảy ra O(log n) lần.

Điểm mạnh về số phép quay **không đồng nghĩa** Red–Black luôn xóa nhanh hơn trong mọi môi trường. Nếu một phép quay đắt vì cập nhật các liên kết/ngữ cảnh hoặc CPU cache, khác biệt này có thể quan trọng; nhưng khi thao tác so sánh khóa, cấp phát hay đồng bộ chiếm phần lớn chi phí, lợi ích có thể không đáng kể.

### 7.4. Cùng O(log n), nhưng đặc tính thao tác khác

| Thành phần xóa | AVL | Red–Black |
| --- | --- | --- |
| Việc phát hiện lỗi | `height` và `BF` | Màu nút rời vị trí, `black-height` |
| Sửa chính | Quay, cập nhật chiều cao | Quay, đổi màu, xử lý thiếu đen |
| Điều có thể lan lên | Cây con giảm chiều cao | Một đơn vị đen thiếu |
| Số quay sau **một lần xóa** | **O(log n)** xấu nhất | **Tối đa 3** với thuật toán chuẩn kiểu CLRS |
| Chi phí thời gian toàn thao tác | **O(log n)** | **O(log n)** |
| Rủi ro triển khai | BF, metadata cũ, nối gốc sau quay | Sentinel `NIL`, màu gốc successor, parent, các trường hợp đối xứng |

Với ứng dụng chứa bản ghi có **tham chiếu trực tiếp đến nút**, lựa chọn “chép khóa của successor vào nút bị xóa” hay “chuyển successor vật lý” còn ảnh hưởng **danh tính nút**. Đây là một quyết định giao diện/thiết kế riêng, không phải một tính chất mặc định tốt hơn của AVL hay RB Tree.

## 8. Thông tin phụ (metadata): phần khác nhau rõ ràng nhất

### 8.1. Những trường dữ liệu chung

Một nút có thể chứa:

```text
key          Khóa định vị phần tử
value        Giá trị gắn với khóa
left         Tham chiếu cây con trái
right        Tham chiếu cây con phải
parent?      Tham chiếu cha (có thể có hoặc không)
```

`key`, `left` và `right` thuộc thông tin thiết yếu của BST nhị phân; `value` tùy cấu trúc Set/Map. Trường `parent` **không bắt buộc về mặt lý thuyết**: có thể dùng đệ quy hoặc ngăn xếp đường đi thay thế.

### 8.2. Metadata của AVL

Một cài AVL thường lưu **một trong hai lựa chọn**:

1. **`height` ở từng nút**, để tính `BF(v)=h(left)-h(right)` trong O(1).
2. **`balance`/`BF`** trực tiếp, dưới dạng `−1,0,+1` trong trạng thái hợp lệ; thuật toán cập nhật phải bảo vệ trường này sau chèn/xóa/quay.

```python
class AVLNode:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None
        self.height = 1  # Hoặc dùng balance theo thiết kế khác.
```

**Không bắt buộc lưu cả `height` và `BF`.** Nếu lưu cả hai, dữ liệu dễ dư thừa và phải cập nhật nhất quán. Khi so sánh bộ nhớ, cần biết **cách cài đặt cụ thể** chứ không suy rằng mọi AVL luôn lưu một số nguyên lớn.

### 8.3. Metadata của Red–Black

Một cài Red–Black cần phân biệt ít nhất **hai trạng thái màu**:

```python
class RBNode:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None
        self.parent = None  # Chỉ khi chọn cách triển khai này.
        self.color = "RED"
```

Theo mô hình lý thuyết, màu cần **một bit thông tin**. Có cài đặt tối ưu gói bit màu vào trường con trỏ hoặc byte cờ, nhưng **không thể kết luận kích thước nút thực tế chỉ tăng đúng một bit**: căn lề bộ nhớ, runtime, đối tượng Python, con trỏ cha và cách biểu diễn chuỗi `"RED"`/`"BLACK"` đều có chi phí.

RB Tree **không cần lưu `black-height` ở mỗi nút**: thuật toán chèn/xóa chuẩn duy trì bất biến đó **gián tiếp bằng quy tắc màu và quay**.

### 8.4. So sánh bộ nhớ từng nút

| Loại thông tin | AVL | Red–Black | Điều cần lưu ý |
| --- | --- | --- | --- |
| Khóa và giá trị | Có | Có | Cùng yêu cầu nghiệp vụ |
| `left/right` | Có | Có | Hai cấu trúc đều là BST nhị phân |
| `parent` | Tùy chọn | Tùy chọn | Nhiều mã xóa RB dùng `parent` để dễ sửa, nhưng không phải bắt buộc |
| Chiều cao nút | **Thường lưu** | Không bắt buộc | AVL cũng có thể chỉ lưu BF |
| Hệ số cân bằng | Có thể lưu **thay `height`** | Không phải bất biến RB | Không cần đồng thời cả height và BF |
| Màu đỏ/đen | Không bắt buộc | **Bắt buộc về thông tin** | Có thể đóng gói |
| `size` cây con | Tùy chọn | Tùy chọn | Phục vụ rank/select |
| Tổng, min/max hoặc thống kê cây con | Tùy chọn | Tùy chọn | Phục vụ truy vấn tăng cường |
| Tổng không gian cho `n` phần tử | **O(n)** | **O(n)** | Hằng số phụ thuộc triển khai |

**Kết luận bộ nhớ hợp lý:** Nếu chỉ xét thông tin cân bằng tối thiểu, RB cần trạng thái màu đơn giản; AVL cần chiều cao hoặc BF. Nhưng cả hai đều có **O(1) metadata trên mỗi nút**, nên tổng bộ nhớ **O(n)**. Không có bảo đảm rằng một RB Tree trong Python sẽ nhẹ hơn một AVL chỉ nhờ “một bit màu”.

### 8.5. Sentinel `NIL` dùng chung và bộ nhớ

RB Tree thường biểu diễn mọi lá rỗng bằng **một sentinel đen dùng chung**, hoặc đơn giản `None` được hiểu là đen. Nếu dùng sentinel chung, cần xử lý `parent` theo **vị trí xóa đang xét**; một đối tượng sentinel không có một cha cố định đúng cho tất cả vị trí rỗng.

AVL thường dùng `None` cho cây con rỗng với `height(None)=0`, nhưng có thể dùng sentinel nếu thiết kế muốn. **Sentinel là lựa chọn biểu diễn**, không phải nguyên nhân làm một họ cây tốt hơn về mọi mặt.

## 9. Thông tin phụ tăng cường: rank, select và thống kê khoảng

Hai cấu trúc đều có thể giữ thêm **`subtree_size`**, tức số nút thật trong cây con:

\[
\operatorname{size}(v)=1+
\operatorname{size}(v.left)+
\operatorname{size}(v.right),\quad
\operatorname{size}(\varnothing)=0.
\]

Nhờ vậy, với khóa phân biệt và metadata đúng:

- **`rank(k)`:** đếm số khóa nhỏ hơn `k` bằng cách đi một đường gốc–lá, cộng số nút ở cây con trái khi rẽ phải.
- **`select(i)`:** tìm khóa có thứ hạng `i` bằng cách so với kích thước cây con trái.
- **`count_range(lo,hi)`:** tính từ hai phép đếm thứ hạng cận.

Mỗi thao tác có thể đạt **O(log n)** trên **cả AVL và RB Tree**, nếu thông tin `size` được cập nhật sau **chèn, xóa, quay và đổi cấu trúc**.

```text
                  40 [size=7]
                /             \
           20 [size=3]       60 [size=3]
          /   \             /   \
        10    30          50    70

rank(50) = 4 (các khóa 10,20,30,40).
select(4) theo chỉ số 0 = 50.
```

Ở ví dụ này, `rank` đếm số khóa **nhỏ hơn** đối số, còn `select` dùng **chỉ số bắt đầu từ 0**. Hai hợp đồng phải thống nhất khi cài đặt.

### 9.1. Cập nhật metadata tăng cường sau quay

Một phép quay thay đổi **những nút nào nằm trong cây con của nhau**, nên `subtree_size` của nút đi xuống và đi lên phải được tính lại từ con mới:

```python
def refresh_size(node):
    if node is None:
        return 0
    left_size = 0 if node.left is None else node.left.size
    right_size = 0 if node.right is None else node.right.size
    node.size = 1 + left_size + right_size
    return node.size
```

Khi quay trái ở `x` và đưa `y=x.right` lên, cần cập nhật `size(x)` **trước** `size(y)`. Những yêu cầu tương tự áp dụng cho metadata tổng/giá trị cực trị.

**Lỗi thường gặp:** cho rằng RB Tree chỉ lưu màu, nên khi tăng cường bằng `size` sẽ “mất tính RB”; điều đó không đúng. Cả hai họ cây đều có thể tăng cường nếu các phép quay và cập nhật giữ đúng bất biến của metadata mới.

## 10. Chọn cấu trúc theo tải công việc, không theo khẩu hiệu

### 10.1. Tải đọc nặng, cập nhật ít

Nếu phần lớn thao tác là `find`, `lower_bound`, `upper_bound` và duyệt các khoảng khóa:

- **AVL là lựa chọn đáng cân nhắc** vì bất biến độ cao chặt hơn có thể giúp giảm giới hạn số nút ghé qua.
- Red–Black vẫn có **O(log n) xấu nhất**; trên một tập dữ liệu cụ thể, hình dạng của nó có thể gần với AVL và kết quả đo có thể rất gần nhau.
- Nếu dữ liệu gần như tĩnh, **mảng đã sắp** có thể tốt nhờ tính liên tục bộ nhớ, dù cập nhật giữa dãy tốn O(n).

**Không có quy tắc chắc chắn “đọc nhiều thì AVL luôn thắng”.** Cần đo trên khóa, kích thước và phần cứng thật.

### 10.2. Tải ghi nặng, thường xuyên chèn/xóa

Nếu liên tục thay đổi tập khóa:

- RB Tree đáng cân nhắc vì **số phép quay bị chặn hằng số** cho cả chèn và xóa trong thuật toán chuẩn, trong khi AVL có thể cần **O(log n) phép quay khi xóa**.
- RB Tree có thể dành nhiều bước **đổi màu**, vẫn O(log n); phép so sánh khóa, phân bổ nút và đồng bộ có thể áp đảo chi phí quay.
- AVL vẫn đạt **O(log n)** cho cập nhật và có thể rất cạnh tranh ở các tải thực tế.

Không nên biến “ít quay hơn” thành khẳng định “ít thao tác CPU hơn”: một lần đổi màu, một lần ghi `height` và một lần truy cập bộ nhớ có chi phí không hoàn toàn tương đương.

### 10.3. Tải hỗn hợp và ràng buộc API

Trong sản phẩm thật, một **thư viện ordered Map/Set được kiểm chứng tốt** thường có giá trị hơn việc tự cài lại thuật toán chỉ để chọn tên cấu trúc. Cần xét:

- Ngôn ngữ và API đang dùng có sẵn cấu trúc tìm kiếm cân bằng nào.
- Phải hỗ trợ **truy vấn khoảng, tìm cận, iterator, xóa theo iterator, khóa trùng, thứ tự tùy biến** hay không.
- Có cần **con trỏ/iterator ổn định**, thao tác đồng thời hoặc sao chép phiên bản dữ liệu không.
- Có cần thêm metadata như `subtree_size`, tổng hoặc min/max của cây con không.
- Có cần **đảm bảo độ trễ xấu nhất** thay vì chỉ kỳ vọng trung bình không.

Một bảng băm có thể thích hợp hơn nếu mục tiêu duy nhất là **tra ID chính xác**; AVL/RB nên được chọn khi **thứ tự** và **cập nhật** cùng là yêu cầu quan trọng.

### 10.4. Bảng quyết định theo mục tiêu

| Bối cảnh | Cấu trúc nên thử trước | Lý do và lưu ý |
| --- | --- | --- |
| Chỉ tìm bản ghi theo ID | **Bảng băm** | O(1) kỳ vọng, không bảo đảm thứ tự |
| Tìm cận, range query, đọc nhiều, cập nhật ít | **AVL hoặc thư viện ordered Map phù hợp** | Cân bằng chặt có thể giảm đường tìm |
| Tìm cận, thêm/xóa nhiều | **RB Tree hoặc AVL** | RB có giới hạn số lần quay xóa thuận lợi; vẫn cần đo |
| Tập khóa gần như bất biến, truy cập tuần tự lớn | **Mảng đã sắp** | Dữ liệu liên tiếp, tìm nhị phân; cập nhật giữa dãy O(n) |
| Truy vấn `rank/select` | **AVL/RB tăng cường `size`** | O(log n) nếu metadata được cập nhật đúng |
| Lấy min liên tục, không cần tìm khóa tùy ý | **Heap** | Ưu tiên cực trị; không thay cho ordered Map |
| Chỉ mục nằm trên trang đĩa hoặc SSD | **B-tree/B+ tree** | Nhiều khóa mỗi nút giảm số trang truy cập |
| Cần chuyển đổi thường xuyên giữa hai biểu diễn | **Đánh giá chi phí chuyển đổi** | Dựng lại cả cây là O(n), không miễn phí |

## 11. Thiết kế thí nghiệm so sánh công bằng

Muốn đưa ra nhận định hiệu năng có cơ sở, nên phân biệt **hai nhóm chỉ số**:

1. **Chỉ số logic** phản ánh thuật toán: số nút ghé qua, chiều cao, phép quay, lần đổi màu và kiểm tra bất biến.
2. **Chỉ số hệ thống** phản ánh triển khai: thời gian chạy, lượng bộ nhớ thực tế, phân bổ đối tượng, cache, GC và đồng bộ.

Chỉ một trong hai nhóm thường chưa đủ giải thích kết quả.

### 11.1. Những tập khóa nên thử

| Tập dữ liệu | Mục đích | Điều cần chú ý |
| --- | --- | --- |
| Khóa tăng dần | Gây BST thường lệch một phía | Cả AVL/RB vẫn phải đạt O(log n) |
| Khóa giảm dần | Kiểm tra tính đối xứng trái/phải | Lỗi quay đối xứng thường lộ ra |
| Khóa xáo trộn cố định | Mô phỏng thứ tự cập nhật đa dạng | Ghi **seed** để tái lập |
| Khóa phân bố theo khoảng | Kiểm tra truy vấn `lower_bound/range` | Không chỉ tìm khóa có sẵn |
| Khóa trùng | Kiểm tra chính sách Map/Set | Không âm thầm tăng số nút |
| Chuỗi chèn rồi xóa | Kiểm tra rebalance sau xóa | Đừng so sánh mã chỉ có `insert` với mã có `delete` |
| Tải theo tỷ lệ đọc/ghi khác nhau | Đánh giá lựa chọn thực tế | Tách độ trễ đọc, chèn và xóa |

Các phép đo thời gian cần làm **ngoài bộ kiểm thử toàn cây**, hoặc ghi riêng chi phí validator. Nếu gọi `validate()` O(n) sau **mỗi chèn**, phép đo tổng chương trình có thể bị chi phối bởi kiểm chứng mà không phản ánh lõi chèn O(log n).

### 11.2. Giữ điều kiện so sánh giống nhau

Để tránh kết luận sai:

1. Hai cây phải nhận **cùng một tập khóa và cùng thứ tự cập nhật**.
2. Phải dùng **cùng một hợp đồng khóa trùng**, ví dụ cập nhật giá trị của Map và không tăng số nút.
3. Đếm **cùng một đại lượng**. “Số nút ghé qua” khác “số toán tử `<` và `>` được thực hiện”.
4. Thực hiện cả **tìm thành công và tìm thất bại**, vì chúng có thể đi những đường khác nhau.
5. Kiểm tra **kết quả, thứ tự inorder, chiều cao, metadata** và bất biến màu trước khi tin số đo.
6. Với số đo thời gian, cân nhắc **warm-up**, số lần lặp, môi trường chạy và nhiễu máy. Trình thông dịch Python có chi phí đối tượng khác mã C/C++.
7. Không so sánh một cài đặt AVL lưu `parent` với một cài RB không có `parent` rồi kết luận mức tiêu thụ bộ nhớ **chỉ** do `height` so với `color`.
8. Khi thử xóa, kiểm tra **sau nhiều lần xóa liên tiếp**, bao gồm xóa gốc, xóa đến cây rỗng và xóa một khóa không tồn tại.

### 11.3. Mẫu báo cáo, không tự điền kết quả giả

| Chỉ số cần ghi | AVL | Red–Black |
| --- | --- | --- |
| Số phần tử còn lại | Đếm từ cây | Đếm từ cây |
| Chiều cao theo số nút | Tính lại từ cây | Tính lại từ cây |
| Số nút ghé trong các lần `find` | Đếm thực tế | Đếm thực tế |
| Tổng phép quay khi chèn | Đếm ở hàm quay | Đếm ở hàm quay |
| Tổng đổi màu khi chèn | Không áp dụng | Đếm khi màu thay đổi |
| Số phép quay khi xóa | Đếm khi có cài `delete` | Đếm khi có cài `delete` |
| Kết quả validator | Pass/fail theo AVL/BST/metadata | Pass/fail theo RB/BST/màu/NIL |
| Thời gian tìm/chèn/xóa | Đo riêng từng nhóm | Đo riêng từng nhóm |
| Bộ nhớ cho cùng số nút | Đo theo cách cài cụ thể | Đo theo cách cài cụ thể |

**Không suy ra tốc độ nhanh/chậm từ bảng trống.** Nội dung học thuật ở đây cung cấp tiêu chí so sánh và các giới hạn; muốn xác nhận trên một sản phẩm phải đo dữ liệu thực tế.

## 12. Các ví dụ quyết định có lời giải

### Ví dụ 1 — Chỉ mục bài học cần tra cứu theo thứ tự

Hệ thống giữ 100.000 bài, mỗi bài có ID duy nhất và thời lượng. Yêu cầu mới là “lấy 50 bài đầu tiên có thời lượng ít nhất 30 phút”.

**Phân tích:** Đây là `lower_bound((30, ...))` kết hợp duyệt theo thứ tự `k=50` phần tử. Cả AVL và RB Tree có thể đạt **O(log n+50)**. Chỉ dùng bảng băm theo ID sẽ không có sẵn thứ tự thời lượng; phải bổ sung chỉ mục có thứ tự hoặc lọc/sắp kết quả.

**Lựa chọn:** Nếu hệ thống đã có thư viện ordered Map được kiểm chứng, nên ưu tiên tận dụng thư viện; nếu tự triển khai và đọc rất nhiều, AVL đáng thử. Không đủ dữ kiện để khẳng định một cây nhanh hơn cây kia.

### Ví dụ 2 — Danh mục thay đổi nhiều lần mỗi phút

Một dịch vụ thường xuyên chèn, xóa và chuyển khóa thời lượng của bài học; số lần đọc và ghi đều lớn.

**Phân tích:** Cả hai cây vẫn O(log n), nhưng số lần quay **sau xóa** có giới hạn thuận lợi ở thuật toán RB chuẩn; AVL có thể phải cập nhật chiều cao/quay qua nhiều tổ tiên. Trong hệ thống có khóa truy cập đồng thời, thời gian giữ khóa có thể quan trọng, nhưng không thể suy từ số quay rằng thời gian giữ khóa chắc chắn nhỏ hơn.

**Lựa chọn:** RB Tree là một ứng viên đáng đánh giá, song phải đo tổng thời gian chèn/xóa/tìm trên đúng tải và thư viện được dùng.

### Ví dụ 3 — Tập dữ liệu chỉ đọc và cần quét tuần tự

Danh sách mã bài không thay đổi hàng ngày, chủ yếu tìm kiếm nhị phân rồi duyệt dài theo thứ tự.

**Phân tích:** Một **mảng đã sắp** có thể tận dụng bộ nhớ liên tiếp, ít con trỏ và CPU cache tốt. Cả AVL và RB Tree vẫn O(log n) tìm, nhưng mỗi nút cây thường cấp phát riêng, tạo overhead tham chiếu.

**Lựa chọn:** Cân nhắc mảng đã sắp thay vì mặc định chọn một trong hai cây, vì yêu cầu cập nhật thường xuyên không còn là yếu tố chính.

### Ví dụ 4 — Tính thứ hạng bài học theo điểm

Người học muốn biết “bài có điểm cao thứ `i`” và “có bao nhiêu bài dưới ngưỡng `k`”.

**Phân tích:** Cả AVL và RB có thể thêm `subtree_size` và hỗ trợ `rank/select` O(log n). Việc chọn họ cây không tự giải quyết bài toán: **phải cài đúng metadata ở các phép quay và xóa**.

**Lựa chọn:** Ưu tiên cấu trúc đã hỗ trợ order statistics hoặc có thiết kế tăng cường dễ kiểm chứng, thay vì dựa riêng vào chênh chiều cao hay màu.

### Ví dụ 5 — Giới hạn bộ nhớ cho thiết bị nhúng

Giả sử yêu cầu tối thiểu hóa bộ nhớ của một chỉ mục nhỏ nhưng phải hỗ trợ tìm cận.

**Phân tích:** RB có thể mã hóa màu rất gọn; AVL có thể mã hóa BF bằng vài trạng thái nhỏ, không nhất thiết lưu một số nguyên kích thước lớn. Nhưng cách căn lề bộ nhớ, con trỏ cha và bố trí nút quan trọng hơn nhiều so với một trường riêng lẻ.

**Lựa chọn:** Đo **kích thước nút thực tế** của các cài đặt phù hợp, bao gồm cấp phát và con trỏ phụ. Không kết luận trước rằng Red–Black luôn ít bộ nhớ hơn.

## 13. Ví dụ Python: so sánh hai cài đặt có cùng hợp đồng

Phần thực hành dưới đây tập trung vào **`put` (chèn/cập nhật giá trị), `get` (tìm) và kiểm tra bất biến** của hai cấu trúc. Để giữ ví dụ rõ ràng và không giả lập kết quả hiệu năng, mã chỉ **minh họa các thao tác đã cài**. Phần xóa được phân tích ở mục 7; **chưa có phương thức `delete`** trong hai lớp Python này, nên không được dùng chương trình dưới đây để khẳng định kết quả benchmark xóa.

**Hợp đồng thống nhất**:

- Khóa là **`int` thật sự**, loại trừ `bool` (trong Python, `True == 1` có thể gây nhầm khóa).
- Thêm khóa mới tạo **một nút**; thêm khóa trùng chỉ **cập nhật giá trị** và trả về `False`.
- `get(k)` trả giá trị hoặc `None` nếu không tìm thấy. Trong giao diện thực tế cho phép lưu `None`, cần thêm `contains` hoặc sentinel kết quả riêng để phân biệt hai tình huống.
- Hai lớp cùng đếm **`node_visits`** khi ghé một nút thật trong `put/get`, và **`rotations`** là số **phép quay đơn**. Đây là bộ đếm **đường đi**, không phải số toán tử so sánh máy chính xác.
- RB còn đếm **`recolors`** khi màu một nút thật thay đổi. AVL giữ **`height`** và kiểm tra lại sau khi quay.

Các khối mã mục 13.1, 13.2 và 13.3 nên được **ghép theo thứ tự vào một chương trình Python** để chạy độc lập. Không cần cài thư viện ngoài Python tiêu chuẩn.

### 13.1. Cây AVL: chiều cao và phép quay

```python
class AVLNode:
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None
        self.height = 1


class AVLIndex:
    def __init__(self):
        self.root = None
        self.size = 0
        self.node_visits = 0
        self.rotations = 0

    @staticmethod
    def _height(node):
        return 0 if node is None else node.height

    def _refresh(self, node):
        node.height = 1 + max(
            self._height(node.left), self._height(node.right)
        )

    def _balance(self, node):
        return self._height(node.left) - self._height(node.right)

    def _rotate_left(self, x):
        y = x.right
        assert y is not None
        between = y.left

        y.left = x
        x.right = between
        self._refresh(x)  # Nút đi xuống trước.
        self._refresh(y)
        self.rotations += 1
        return y

    def _rotate_right(self, y):
        x = y.left
        assert x is not None
        between = x.right

        x.right = y
        y.left = between
        self._refresh(y)  # Nút đi xuống trước.
        self._refresh(x)
        self.rotations += 1
        return x

    def put(self, key, value):
        if type(key) is not int:
            raise TypeError("Khóa phải là số nguyên")

        original_size = self.size

        def add(node):
            if node is None:
                self.size += 1
                return AVLNode(key, value)

            self.node_visits += 1
            if key < node.key:
                node.left = add(node.left)
            elif key > node.key:
                node.right = add(node.right)
            else:
                node.value = value
                return node

            self._refresh(node)
            bf = self._balance(node)

            if bf > 1:
                # LL hoặc LR.
                if self._balance(node.left) < 0:
                    node.left = self._rotate_left(node.left)
                return self._rotate_right(node)

            if bf < -1:
                # RR hoặc RL.
                if self._balance(node.right) > 0:
                    node.right = self._rotate_right(node.right)
                return self._rotate_left(node)

            return node

        self.root = add(self.root)
        return self.size != original_size

    def get(self, key):
        if type(key) is not int:
            raise TypeError("Khóa phải là số nguyên")

        current = self.root
        while current is not None:
            self.node_visits += 1
            if key == current.key:
                return current.value
            current = (
                current.left if key < current.key else current.right
            )
        return None

    def items(self):
        def walk(node):
            if node is not None:
                yield from walk(node.left)
                yield (node.key, node.value)
                yield from walk(node.right)
        return walk(self.root)

    def validate(self):
        """Trả (số nút, chiều cao thật) và kiểm tra mọi BF."""
        seen = set()

        def visit(node, low, high):
            if node is None:
                return 0, 0  # (số nút, chiều cao thật)

            marker = id(node)
            assert marker not in seen, "Chu trình hoặc trùng nút"
            seen.add(marker)
            if low is not None:
                assert low < node.key, "Sai cận dưới BST"
            if high is not None:
                assert node.key < high, "Sai cận trên BST"

            ln, lh = visit(node.left, low, node.key)
            rn, rh = visit(node.right, node.key, high)
            actual_height = 1 + max(lh, rh)

            assert node.height == actual_height, "height bị lỗi"
            assert abs(lh - rh) <= 1, "Nút vi phạm AVL"
            return 1 + ln + rn, actual_height

        result = visit(self.root, None, None)
        assert result[0] == self.size
        return result
```

### 13.2. Red–Black: màu, liên kết cha và đổi màu

Mã Red–Black dùng **một sentinel `NIL` màu đen** chia sẻ bởi các vị trí rỗng và con trỏ `parent` ở mỗi nút. Vì chỉ triển khai **chèn**, sentinel có thể tự trỏ tới chính nó qua `left, right, parent`.

```python
RED = "RED"
BLACK = "BLACK"


class RBNode:
    def __init__(self, key=None, value=None, color=RED):
        self.key = key
        self.value = value
        self.color = color
        self.left = None
        self.right = None
        self.parent = None


class RBIndex:
    def __init__(self):
        self.nil = RBNode(color=BLACK)
        self.nil.left = self.nil
        self.nil.right = self.nil
        self.nil.parent = self.nil
        self.root = self.nil
        self.size = 0
        self.node_visits = 0
        self.rotations = 0
        self.recolors = 0

    def _paint(self, node, color):
        # Sentinel dùng chung không bao giờ được tô đỏ.
        if node is self.nil:
            assert color == BLACK
            return

        if node.color != color:
            node.color = color
            self.recolors += 1

    def _rotate_left(self, x):
        y = x.right
        assert y is not self.nil

        x.right = y.left
        if y.left is not self.nil:
            y.left.parent = x

        y.parent = x.parent
        if x.parent is self.nil:
            self.root = y
        elif x is x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y

        y.left = x
        x.parent = y
        self.rotations += 1

    def _rotate_right(self, y):
        x = y.left
        assert x is not self.nil

        y.left = x.right
        if x.right is not self.nil:
            x.right.parent = y

        x.parent = y.parent
        if y.parent is self.nil:
            self.root = x
        elif y is y.parent.left:
            y.parent.left = x
        else:
            y.parent.right = x

        x.right = y
        y.parent = x
        self.rotations += 1

    def put(self, key, value):
        if type(key) is not int:
            raise TypeError("Khóa phải là số nguyên")

        parent = self.nil
        current = self.root

        while current is not self.nil:
            self.node_visits += 1
            parent = current
            if key == current.key:
                current.value = value
                return False
            current = (
                current.left if key < current.key else current.right
            )

        z = RBNode(key, value, RED)
        z.left = self.nil
        z.right = self.nil
        z.parent = parent

        if parent is self.nil:
            self.root = z
        elif key < parent.key:
            parent.left = z
        else:
            parent.right = z

        self.size += 1
        self._fix_insert(z)
        return True

    def _fix_insert(self, z):
        while z.parent.color == RED:
            grandparent = z.parent.parent

            if z.parent is grandparent.left:
                uncle = grandparent.right
                if uncle.color == RED:
                    # Cha/chú đỏ: đổi màu, có thể đưa lỗi lên.
                    self._paint(z.parent, BLACK)
                    self._paint(uncle, BLACK)
                    self._paint(grandparent, RED)
                    z = grandparent
                else:
                    if z is z.parent.right:
                        # LR -> LL trước khi sửa tại ông.
                        z = z.parent
                        self._rotate_left(z)
                    self._paint(z.parent, BLACK)
                    self._paint(z.parent.parent, RED)
                    self._rotate_right(z.parent.parent)
            else:
                uncle = grandparent.left
                if uncle.color == RED:
                    self._paint(z.parent, BLACK)
                    self._paint(uncle, BLACK)
                    self._paint(grandparent, RED)
                    z = grandparent
                else:
                    if z is z.parent.left:
                        # RL -> RR.
                        z = z.parent
                        self._rotate_right(z)
                    self._paint(z.parent, BLACK)
                    self._paint(z.parent.parent, RED)
                    self._rotate_left(z.parent.parent)

        self._paint(self.root, BLACK)
        self.root.parent = self.nil

    def get(self, key):
        if type(key) is not int:
            raise TypeError("Khóa phải là số nguyên")

        current = self.root
        while current is not self.nil:
            self.node_visits += 1
            if key == current.key:
                return current.value
            current = (
                current.left if key < current.key else current.right
            )
        return None

    def items(self):
        def walk(node):
            if node is not self.nil:
                yield from walk(node.left)
                yield (node.key, node.value)
                yield from walk(node.right)
        return walk(self.root)

    def validate(self):
        """Trả (số nút, chiều cao thật, số đen gồm gốc và NIL)."""
        nil = self.nil
        assert nil.color == BLACK
        assert nil.left is nil and nil.right is nil
        assert nil.parent is nil

        if self.root is nil:
            assert self.size == 0
            return (0, 0, 1)

        assert self.root.color == BLACK
        assert self.root.parent is nil
        seen = set()

        def visit(node, expected_parent, low, high):
            if node is nil:
                return (0, 0, 1)

            marker = id(node)
            assert marker not in seen, "Chu trình hoặc trùng nút"
            seen.add(marker)
            assert node.parent is expected_parent, "Sai parent"
            assert node.color in (RED, BLACK)
            assert node.left is not None and node.right is not None

            if low is not None:
                assert low < node.key, "Sai cận dưới BST"
            if high is not None:
                assert node.key < high, "Sai cận trên BST"

            if node.color == RED:
                assert node.left.color == BLACK, "Đỏ-đỏ trái"
                assert node.right.color == BLACK, "Đỏ-đỏ phải"

            ln, lh, lb = visit(node.left, node, low, node.key)
            rn, rh, rb = visit(node.right, node, node.key, high)
            assert lb == rb, "Black-height không đồng đều"
            black_here = 1 if node.color == BLACK else 0

            return (
                1 + ln + rn,
                1 + max(lh, rh),
                lb + black_here,
            )

        result = visit(self.root, nil, None, None)
        assert result[0] == self.size
        return result
```

**Tại sao có bộ đếm màu riêng?** Việc tô `RED→BLACK` hoặc `BLACK→RED` làm thay đổi metadata mà **không cần phép quay**. Khi đo, nên phân biệt `recolors` với `rotations` thay vì gộp chung hai đại lượng thành “số lần tái cân bằng”.

**Lưu ý về so sánh bộ nhớ:** mã ví dụ AVL không lưu `parent`, còn mã Red–Black có `parent`. Do đó, **không được lấy trực tiếp kích thước các đối tượng Python này** để kết luận sự khác biệt bộ nhớ là do màu so với chiều cao. Muốn so sánh bộ nhớ công bằng, phải chuẩn hóa cùng một chính sách con trỏ cha và cùng cách cấp phát.

### 13.3. Bộ thử đối chiếu, không tự dựng kết quả benchmark

Sau khi định nghĩa hai lớp ở mục 13.1 và 13.2:

```python
from random import Random


# Bốn tình huống nhỏ để kiểm tra phép quay đơn/kép khi chèn.
rotation_cases = {
    "LL": [30, 20, 10],
    "RR": [10, 20, 30],
    "LR": [30, 10, 20],
    "RL": [10, 30, 20],
}

for name, keys in rotation_cases.items():
    avl = AVLIndex()
    rb = RBIndex()
    for key in keys:
        assert avl.put(key, f"lesson-{key}"), name
        assert rb.put(key, f"lesson-{key}"), name
        avl.validate()
        rb.validate()

    assert avl.root.key == 20, name
    assert rb.root.key == 20, name
    assert avl.validate() == (3, 2), name
    assert rb.validate() == (3, 2, 2), name
    assert list(avl.items()) == list(rb.items()), name


# Các khóa giống nhau nhưng thứ tự chèn khác nhau.
ascending = list(range(1, 32))
descending = list(reversed(ascending))
shuffled = ascending.copy()
Random(2026).shuffle(shuffled)

datasets = {
    "tang_dan": ascending,
    "giam_dan": descending,
    "xao_tron_seed_2026": shuffled,
}

for name, keys in datasets.items():
    avl = AVLIndex()
    rb = RBIndex()

    for key in keys:
        assert avl.put(key, f"lesson-{key}")
        assert rb.put(key, f"lesson-{key}")

    avl_count, avl_height = avl.validate()
    rb_count, rb_height, rb_black_count = rb.validate()
    expected_items = [
        (key, f"lesson-{key}") for key in sorted(set(keys))
    ]

    assert avl_count == rb_count == len(keys)
    assert list(avl.items()) == expected_items
    assert list(rb.items()) == expected_items

    # Tách lượt ghé nút của tìm kiếm khỏi lượt ghé khi chèn.
    avl_before = avl.node_visits
    rb_before = rb.node_visits
    for query in [1, 7, 15, 31, 32, 100]:
        expected = (
            f"lesson-{query}" if query in keys else None
        )
        assert avl.get(query) == expected
        assert rb.get(query) == expected

    avl_search_visits = avl.node_visits - avl_before
    rb_search_visits = rb.node_visits - rb_before

    # Khóa trùng cập nhật value, không thêm phần tử mới.
    assert not avl.put(15, "updated")
    assert not rb.put(15, "updated")
    assert avl.size == rb.size == len(keys)
    assert avl.get(15) == rb.get(15) == "updated"
    avl.validate()
    rb.validate()

    print({
        "dataset": name,
        "nodes": len(keys),
        "height_avl_nodes": avl_height,
        "height_rb_nodes": rb_height,
        "avl_rotations": avl.rotations,
        "rb_rotations": rb.rotations,
        "rb_recolors": rb.recolors,
        "avl_search_node_visits": avl_search_visits,
        "rb_search_node_visits": rb_search_visits,
        "rb_black_count_including_root_nil": rb_black_count,
    })
```

**Cách đọc kết quả**:

- `height_avl_nodes` và `height_rb_nodes` đều đếm **số nút thật** trên đường dài nhất; có thể so sánh trực tiếp.
- `avl_rotations` và `rb_rotations` đếm **quay đơn**, nên quay kép đóng góp 2 đơn vị.
- `rb_recolors` đếm số lần **màu một nút thật thay đổi**, không đếm việc gán lặp cùng màu.
- `avl_search_node_visits` và `rb_search_node_visits` là tổng số **nút thật được ghé** trong sáu lượt `get`; không phải mili giây, cũng không phải số toán tử so sánh của bộ xử lý.
- `rb_black_count_including_root_nil` là số nút đen trên đường có tính gốc và `NIL` theo validator; nó không phải chiều cao thật của cây.

Đoạn mã **không in ra một bộ số đo cố định trong bài**, bởi kết quả cần đến từ lần chạy thực tế và đúng mã được dùng. Nếu mở rộng để đo `delete`, hãy cài **xóa đúng và validator độc lập ở cả hai lớp trước**, rồi mới thêm bộ đếm quay khi xóa.

### 13.4. Diễn giải các thí nghiệm mà không vội kết luận

Nếu trên chuỗi tăng dần một cây có ít phép quay hơn, điều đó **chỉ** chứng tỏ với chuỗi ấy, **định nghĩa phép quay và cách cài đó**, nó đã quay ít hơn. Cần xem thêm chiều cao cuối cùng và số nút truy cập khi tìm, chưa kể chi phí đổi màu.

Nếu hai cây có chiều cao bằng nhau, điều đó **không chứng tỏ cấu trúc hoàn toàn giống nhau**: các khóa có thể ở vị trí khác, đường tìm từng khóa khác, metadata khác và số lần cập nhật cũng khác.

Nếu số lần ghé nút của AVL thấp hơn cho những truy vấn trong bộ thử, chỉ nên kết luận về **bộ truy vấn, thứ tự cập nhật và hai cài đặt đang đo**. Muốn mở rộng kết luận tới tải thực tế phải tăng tập mẫu và kiểm tra tính đại diện.

## 14. Sai lầm phổ biến khi so sánh AVL và Red–Black

### 14.1. Sai về mặt thuật toán

- **“AVL cân bằng hoàn hảo.”** Không đúng: mỗi nút chỉ cần chênh cao không quá một mức.
- **“RB Tree có chiều cao O(1) vì chỉ dùng hai màu.”** Sai: màu là công cụ duy trì chiều cao **O(log n)**, không phải chiều cao hằng số.
- **“Cả hai O(log n) thì mọi thao tác chạy nhanh như nhau.”** Sai: Big O che giấu hằng số, số quay, đường tìm và chi phí hệ thống.
- **“Chiều cao RB luôn lớn hơn AVL nếu có cùng số khóa.”** Sai: bất biến RB **cho phép** cây cao hơn, nhưng một RB Tree cụ thể có thể ngắn bằng hoặc ngắn hơn một AVL Tree cụ thể với các cấu trúc khác nhau.
- **“Mọi nút đỏ có hai con đen thật.”** Sai: con có thể là `NIL` đen, và quy tắc chỉ cấm **con đỏ**.
- **“Chèn AVL và chèn RB dùng chung hàm `rebalance`.”** Sai: một bên dựa vào **BF**, bên kia dựa vào **màu cha/chú/ông**.
- **“Chèn AVL tối đa hai quay, nên thời gian chèn là O(1).”** Sai: còn tìm vị trí và duyệt tổ tiên O(log n).
- **“Xóa RB Tree có tối đa ba quay, nên xóa O(1).”** Sai: còn tìm khóa, successor và đổi màu/lan thiếu đen O(log n).
- **“Xóa AVL nhiều lần quay thì chắc chắn chậm hơn RB.”** Không có kết luận như vậy nếu chưa xét tổng công việc và chi phí bộ nhớ.
- **“RB Tree không có `height` thì không thể tính chiều cao.”** Sai: có thể **tính lại bằng duyệt** O(n), chỉ không cần lưu độ cao ở nút để duy trì bất biến màu.

### 14.2. Sai về metadata và bộ nhớ

- **“AVL bắt buộc lưu cả `height` và `BF`.”** Không: có thể chọn một biểu diễn phù hợp và duy trì nó.
- **“Màu của RB lúc nào cũng chỉ tốn một bit trong RAM.”** Không: **thông tin tối thiểu** là một bit, nhưng biểu diễn đối tượng và căn lề bộ nhớ tùy ngôn ngữ.
- **“RB lúc nào cũng ít bộ nhớ hơn AVL.”** Không bảo đảm: cấu trúc trường `parent`, cấp phát nút, màu và chiều cao có thể làm kết quả đổi chiều.
- **“`parent` chỉ có ở RB Tree.”** Sai: cả hai đều có thể dùng hoặc không dùng trường này.
- **“Lưu `subtree_size` chỉ phù hợp với AVL.”** Sai: cả hai cấu trúc đều có thể tăng cường.
- **“Sau quay, cập nhật metadata tăng cường ở nút nào cũng được.”** Sai: phải tính lại theo quan hệ cha–con mới, thường từ nút **đi xuống trước**.
- **“NIL của RB được tính như một khóa dữ liệu.”** Sai: `NIL` đen chỉ là sentinel/điểm kết thúc.
- **“Khi xóa nút đen, cứ gọi lại hàm sửa sau chèn.”** Sai: sửa sau xóa xử lý **thiếu đen**, không phải chỉ đỏ–đỏ.

### 14.3. Sai về thí nghiệm

- **“Có thể đo thời gian chèn kèm `validate` sau từng bước rồi so với Big O lý thuyết.”** Sai nếu không tách chi phí validator O(n).
- **“Số quay là thước đo duy nhất cho hiệu năng.”** Sai: không phản ánh so sánh khóa, cache và đổi màu.
- **“Một lần chạy ngẫu nhiên đủ kết luận.”** Không: cần seed, lặp, mẫu đọc/ghi và đánh giá tính đại diện.
- **“Đếm `<`/`>` ở một lớp và `node_visits` ở lớp kia để so sánh.”** Sai: hai đại lượng khác nhau.
- **“Cùng thời gian O(log n) nghĩa là bộ nhớ cũng giống nhau.”** Sai: tổng O(n) nhưng hệ số hằng và cách cấp phát có thể khác xa.
- **“Bảng băm là lựa chọn đúng cho mọi tìm kiếm.”** Sai: khi cần `lower_bound`, thứ tự hay duyệt khoảng, bảng băm không có sẵn bất biến thứ tự.

## 15. Bài tập vận dụng

### Bài 1 — Hai loại bất biến

Phát biểu bất biến cân bằng của AVL và bất biến màu của RB Tree. Tại sao một RB Tree có `BF=+2` ở một nút vẫn **có thể** hợp lệ?

*Gợi ý:* AVL cần `|BF|≤1`. RB Tree chỉ cần gốc/NIL đen, không đỏ–đỏ và mọi đường có cùng black-height; chênh chiều cao thật có thể lớn hơn một mức.

### Bài 2 — Phân biệt chiều cao theo cạnh và số nút

Một cây có đường dài nhất chứa 6 nút thật tính cả gốc. Chiều cao theo **số nút** và theo **số cạnh** lần lượt bằng bao nhiêu? Tại sao cần thống nhất quy ước khi so sánh cận AVL và Red–Black?

*Gợi ý:* Lần lượt 6 và 5. Các công thức khác nhau ở hằng số khi dùng hai quy ước; không thể so cận mà bỏ qua định nghĩa.

### Bài 3 — Tính BF trong AVL

Một nút có cây trái cao 4, cây phải cao 2. Tính `BF` theo định nghĩa `h(left)-h(right)`. Đây có phải trạng thái AVL hợp lệ không? Nếu con trái có BF âm thì cần dạng quay nào?

*Gợi ý:* `BF=+2`, không hợp lệ; con trái BF âm gợi ý trường hợp LR, quay trái ở con trái rồi quay phải ở nút.

### Bài 4 — Màu đỏ không làm tăng black-height lúc chèn

Trong RB Tree hợp lệ, vì sao nút mới thường được tạo màu đỏ? Nếu cha mới có màu đỏ và chú cũng màu đỏ, thao tác sửa chính là gì?

*Gợi ý:* Chèn nút đỏ không tăng số nút đen trên đường; khi cha/chú đỏ, đổi hai nút đó thành đen, ông thành đỏ, có thể đưa lỗi lên tổ tiên.

### Bài 5 — So sánh số phép quay khi chèn

Chèn lần lượt `30, 10, 20` vào hai cây rỗng AVL và Red–Black. Hãy vẽ cây cuối, giải thích vì sao nhánh **LR** cần tối đa hai phép quay đơn ở cả hai thuật toán, nhưng kiểm tra bất biến trước khi quay khác nhau.

*Gợi ý:* Kết quả điển hình có gốc `20`, hai con `10` và `30`. AVL xét BF; Red–Black xét cha đỏ/chú đen và đổi màu kết hợp quay.

### Bài 6 — Đổi màu khác quay

Chèn `10, 5, 15, 1` trong RB Tree. Tại sao một lần sửa có thể có **nhiều đổi màu nhưng không quay**? Vì sao không nên tính số phép quay là tổng thời gian cập nhật?

*Gợi ý:* Khi cha/chú đỏ, chỉ đổi màu và có thể đưa vi phạm lên ông. Tìm vị trí và đi lên vẫn tốn công việc.

### Bài 7 — Phân tích xóa AVL

Một AVL có tổ tiên `p` với `h(left)=3`, `h(right)=4`. Xóa một phần tử ở nhánh trái làm chiều cao nhánh trái giảm xuống 2, dù nhánh trái mới đã tự cân bằng. `BF(p)` mới là bao nhiêu? Phải xử lý gì tiếp?

*Gợi ý:* `BF(p)=−2`. Phải xét con phải nặng và quay đơn/kép nếu cần, rồi tiếp tục duy trì metadata tại các tổ tiên.

### Bài 8 — Xóa RB: thiếu đen

Một nút đen bị xóa và nút thay thế là `NIL` đen. Giải thích vì sao có thể phát sinh **thiếu một nút đen** và kể tên bốn nhóm trường hợp sửa theo màu anh/em.

*Gợi ý:* Anh/em đỏ; anh/em đen có hai con đen; anh/em đen có con gần đỏ/con xa đen; anh/em đen có con xa đỏ.

### Bài 9 — Vì sao giới hạn số quay không đồng nghĩa thời gian O(1)?

Trong thuật toán chuẩn, chèn Red–Black cần tối đa 2 quay đơn và xóa Red–Black kiểu CLRS cần tối đa 3 quay. Vì sao hai thao tác vẫn có thời gian O(log n)?

*Gợi ý:* Cần đi qua đường tìm, successor khi xóa và có thể đổi màu/lan thiếu đen qua nhiều tổ tiên.

### Bài 10 — Metadata tối thiểu

Một cài AVL chỉ lưu `BF∈{-1,0,+1}`; một cài RB lưu `color` dạng enum có hai giá trị. Có thể khẳng định ngay Red–Black tốn ít bộ nhớ hơn không? Nêu ít nhất ba yếu tố cần đo.

*Gợi ý:* Không. Hãy xét `parent` có hay không, căn lề và kích thước đối tượng, cách đóng gói BF/màu, cấp phát và bộ quản lý bộ nhớ.

### Bài 11 — Cập nhật chiều cao sau quay

Trong quay trái tại `x` có con phải `y`, sau khi đưa `y` lên và `x` xuống làm con trái, tại sao phải cập nhật chiều cao của `x` trước `y`?

*Gợi ý:* `height(y)` mới phụ thuộc vào `height(x)` sau khi `x` đã nhận cây con giữa mới.

### Bài 12 — `rank` và `select`

Cho các khóa `10,20,30,40,50,60,70`. Tính `rank(50)` (số khóa nhỏ hơn 50) và `select(4)` theo chỉ số bắt đầu 0. Cần thêm metadata gì để thực hiện hai truy vấn O(log n) trong AVL hoặc RB?

*Gợi ý:* `rank(50)=4`, `select(4)=50`. Cần `subtree_size` trên mỗi nút và cập nhật sau mọi thao tác cấu trúc.

### Bài 13 — Chọn cấu trúc cho tập dữ liệu tĩnh

Một danh sách mã bài hầu như không thay đổi nhưng rất thường xuyên tìm nhị phân và duyệt theo thứ tự. Hãy so sánh mảng đã sắp với AVL/RB về độ phức tạp tìm, chèn vào giữa và bố trí bộ nhớ.

*Gợi ý:* Tìm nhị phân O(log n), chèn/xóa giữa mảng O(n); mảng liên tiếp có lợi thế cache, cây có nút và tham chiếu.

### Bài 14 — Chỉ tra cứu chính xác theo ID

Ứng dụng chỉ cần `get(lesson_id)`, không có truy vấn cận hay khoảng. Nên ưu tiên bảng băm hay tự cài AVL/RB? Trường hợp nào khiến quyết định thay đổi?

*Gợi ý:* Bảng băm thường phù hợp với O(1) kỳ vọng. Nếu phát sinh yêu cầu thứ tự, tìm cận hoặc bảo đảm xấu nhất theo mô hình so sánh, cần cân nhắc cấu trúc có thứ tự.

### Bài 15 — Mẫu tải cập nhật nhiều

Một chỉ mục có nhiều thao tác xóa. Dựa vào bảng so sánh, giải thích vì sao RB là ứng viên đáng thử. Sau đó chỉ ra **ít nhất hai lý do** khiến AVL vẫn có thể đạt thời gian thực tế tốt hơn trên một khối lượng cụ thể.

*Gợi ý:* RB có giới hạn số quay xóa thuận lợi; song đường tìm, giá so sánh khóa, bố trí bộ nhớ, cache và cài đặt có thể chiếm ưu thế hơn.

### Bài 16 — Tách chỉ số khi đo

Giả sử kết quả thử nghiệm ghi nhận **40 phép quay AVL** và **25 phép quay RB** sau một chuỗi chèn, nhưng AVL có tổng `node_visits` cho lượt tìm thấp hơn. Có đủ thông tin kết luận cấu trúc nào nhanh hơn về thời gian không?

*Gợi ý:* Không. Số quay và số lần ghé nút là **các chỉ số logic khác nhau**, cần thêm thời gian đo đúng, chi phí đổi màu, khóa và môi trường.

### Bài 17 — Vì sao cần kiểm chứng độc lập?

Một hàm kiểm tra AVL chỉ đọc `node.height` để tính BF mà không tính chiều cao thật từ con; một hàm kiểm tra RB chỉ xác minh inorder tăng. Những lỗi nào có thể lọt qua?

*Gợi ý:* Metadata height sai có thể làm BF nhìn giả đúng; inorder tăng không kiểm tra không đỏ–đỏ hay black-height. Validator cần tính lại các bất biến độc lập.

### Bài 18 — Thực hành Python có seed cố định

Dùng mã mục 13, tạo ba dãy có cùng 31 khóa: tăng, giảm và xáo trộn bằng `Random(2026)`. Sau từng dãy, ghi lại chiều cao, số quay, số lượt ghé nút và số đổi màu; đối chiếu kết quả inorder của hai cây.

*Gợi ý:* Không dự đoán bảng số trước khi chạy. Cần ghi rõ bộ đếm `node_visits` gồm những thao tác nào và không tính `validate` vào chi phí lõi.

### Bài 19 — Tách riêng xóa khỏi bộ thử chèn

Bộ mã mục 13 chưa có `delete`. Hãy đề xuất những bước cần bổ sung để thử nghiệm công bằng hiệu năng xóa trên hai cây. Tại sao **không được** đưa số quay khi chèn vào cột quay khi xóa?

*Gợi ý:* Cài đầy đủ xóa BST và tái cân bằng tương ứng, kiểm tra khóa còn lại/metadata, giữ cùng thứ tự xóa, reset hoặc lưu bộ đếm riêng, và phân biệt hai loại thao tác.

### Bài 20 — Thiết kế một dịch vụ có nhiều chỉ mục

Một danh mục giữ bảng băm `by_id`, cây có thứ tự `by_duration` và đồ thị các bài tiên quyết. Khi sửa thời lượng của một bài, cần bảo vệ những bất biến nào? Việc dùng AVL hay RB có tự giải quyết tính nhất quán giữa các chỉ mục không?

*Gợi ý:* Phải xóa khóa cũ, chèn khóa mới theo `(duration, lesson_id)`, giữ ID và các cạnh còn hợp lệ, bảo đảm bản ghi chính khớp chỉ mục. Cân bằng cây **không tạo giao dịch nguyên tử** cho các cấu trúc khác.

## 16. Tổng kết

**AVL** và **Red–Black Tree** đều là **BST cân bằng**: khi được cài đặt đúng, cả hai bảo đảm **tìm, chèn và xóa O(log n) thời gian xấu nhất**, duyệt toàn bộ O(n) và truy vấn khoảng trả `k` khóa có thể đạt **O(log n+k)**. Điểm khác nhau nằm ở **cách duy trì giới hạn chiều cao**:

- **AVL** kiểm soát trực tiếp `|h(left)-h(right)|≤1` ở mỗi nút, thường lưu `height` hoặc `BF`. Cây có **giới hạn chiều cao chặt hơn**, phù hợp để cân nhắc khi **tra cứu rất thường xuyên**. Chèn AVL dùng tối đa hai phép quay đơn; **xóa có thể quay ở O(log n) mức tổ tiên**.
- **Red–Black** duy trì **màu, không đỏ–đỏ và black-height đồng đều**, cần thông tin màu nhưng không bắt buộc lưu chiều cao tại từng nút. Chèn dùng tối đa **hai phép quay đơn** và có thể đổi màu dọc đường; xóa kiểu chuẩn có **tối đa ba phép quay**, đồng thời có thể lan thiếu đen lên tổ tiên.

Không có bảo đảm **AVL luôn tìm nhanh hơn** hoặc **Red–Black luôn cập nhật nhanh hơn** trong một môi trường cụ thể. Cả hai đều sử dụng **O(n) bộ nhớ toàn cây**; màu, chiều cao/BF, con trỏ cha và metadata tăng cường quyết định hệ số hằng. Khi cần `rank/select`, cả hai có thể bổ sung `subtree_size`; khi chỉ cần tra ID, bảng băm là một phương án khác; khi dữ liệu gần tĩnh, mảng đã sắp có thể đáng dùng.

Để lựa chọn có cơ sở, hãy **xác định mẫu truy vấn và yêu cầu độ trễ**, chọn **hợp đồng khóa và cập nhật nhất quán**, dùng **cài đặt được kiểm chứng**, rồi đo trên **cùng dãy khóa, cùng thứ tự thao tác và cùng định nghĩa chỉ số**. Lựa chọn cấu trúc tốt nhất là cấu trúc giữ đúng **bất biến, hiệu năng, bộ nhớ và tính bảo trì** cho bài toán thật — không phải cấu trúc có tên hay công thức trông ấn tượng hơn.
