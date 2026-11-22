# Cây tìm kiếm nhị phân tối ưu

**Cây tìm kiếm nhị phân tối ưu** (*Optimal Binary Search Tree – OBST*) là bài toán **quy hoạch động cấu trúc**: với một tập khóa đã sắp thứ tự và tần suất/xác suất tìm kiếm tương ứng, hãy xây một **cây tìm kiếm nhị phân (BST)** sao cho **chi phí tìm kiếm kỳ vọng là nhỏ nhất**.

BST đúng về mặt chức năng chưa chắc tốt về chi phí tìm kiếm. Một khóa ở gần gốc được kiểm tra sớm; một khóa ở sâu phải đi qua nhiều nút trước khi tìm thấy. Nếu khóa thường được hỏi nằm sâu, tổng chi phí tăng. Nhưng chỉ đưa khóa có tần suất lớn nhất lên gốc cũng **không luôn tối ưu**, vì khi chọn gốc còn ảnh hưởng đến độ sâu của **tất cả khóa và khoảng tìm kiếm thất bại** ở hai bên.

OBST minh họa đầy đủ những ý tưởng cốt lõi của DP trên cấu trúc:

1. **Định nghĩa bài toán con bằng đoạn khóa có thứ tự**.
2. **Thử mọi lựa chọn nút gốc của đoạn**.
3. **Tách thành hai cây con bắt buộc chứa những khoảng khóa tương ứng**.
4. **Cộng chi phí của việc đẩy mọi phần tử xuống sâu thêm một mức**.
5. **Lưu nút gốc tối ưu cho từng đoạn để dựng lại cây**, chứ không chỉ tính giá trị.
6. Phân biệt rõ **tìm kiếm thành công** và **tìm kiếm thất bại**.

Bài học dùng mô hình OBST kinh điển có trọng số cho cả tìm thành công và thất bại, có công thức `e/w/root`, bảng tính ví dụ, chứng minh tính đúng, phân tích **O(n³)** và tối ưu hóa Knuth **O(n²)** khi đủ điều kiện. Chương trình Java 17+ cuối bài tính đúng toàn bộ bảng, dựng hình cây và kiểm tra những trường hợp biên.

## 1. Nhắc lại BST và chi phí tìm kiếm

Một **binary search tree** thỏa bất biến thứ tự ở mọi nút:

- Mọi khóa trong cây con trái đều **nhỏ hơn** khóa của nút.
- Mọi khóa trong cây con phải đều **lớn hơn** khóa của nút.
- Hai cây con tiếp tục là BST.

Trong bài OBST, giả định các khóa **phân biệt** và đã sắp tăng:

```text
k1 < k2 < ... < kn
```

Do đó một cây có gốc `kr` bắt buộc chứa:

```text
Bên trái: k1, k2, ..., k(r-1)
Gốc:      kr
Bên phải: k(r+1), ..., kn
```

Không thể tự ý đặt khóa lớn hơn gốc vào bên trái để giảm chi phí, vì như vậy phá điều kiện BST.

Nếu gốc có **độ sâu 1**, một khóa ở độ sâu d cần d lần so sánh với khóa của các nút trên đường đi, tính cả nút chứa khóa.

Ví dụ cùng ba khóa 10, 20, 30:

```text
Cây lệch phải:          Cây cân bằng:

      10                       20
        \                     /  \
         20                  10  30
           \
            30

Số so sánh khóa 10,20,30:
Cây lệch phải: 1,2,3
Cây cân bằng:  2,1,2
```

Nếu các khóa được hỏi với tần suất khác nhau, mục tiêu không phải “mọi khóa đều cùng sâu” hay “cây có chiều cao nhỏ nhất”, mà là **tối thiểu tổng độ sâu có trọng số**. Một cây hơi lệch đôi khi có chi phí kỳ vọng thấp hơn cây cân bằng nếu phân bố truy vấn rất lệch.

## 2. Mô hình xác suất/trọng số: tìm thấy và tìm không thấy

Gọi:

- `p_i >= 0`: tần suất hoặc xác suất tìm **thành công** khóa `k_i`, với i=1..n.
- `q_j >= 0`: tần suất hoặc xác suất tìm **thất bại** vào **khoảng trống d_j**, với j=0..n.

Các khoảng trống giữa khóa:

```text
d0:          x < k1
d1: k1 < x < k2
d2: k2 < x < k3
...
d(n-1): k(n-1) < x < kn
dn:          x > kn
```

BST có n khóa sẽ có n+1 **vị trí con rỗng**. Theo mô hình OBST, mỗi vị trí rỗng là một **lá giả** (*dummy leaf*) d_j, biểu diễn tìm thất bại ở khoảng tương ứng.

**Ví dụ:**

```text
Khóa:        10       20       30
            /  \     /  \     /  \
Khoảng:  d0     d1  d1  d2  d2     d3

Dữ liệu có thể cho:
p = [3, 3, 1]
q = [2, 1, 1, 1]
```

Sơ đồ trên chỉ cho thấy các khoảng khái niệm; **trong một cây BST cụ thể, mỗi d_j chỉ xuất hiện đúng một lần** tại một con rỗng. Không coi hai nhãn d1 ở hai minh họa lân cận là hai lá thật. Một biểu diễn chính xác của cây cân bằng sẽ xuất hiện ở phần sau.

Với dữ liệu p và q là **tần suất nguyên**, tổng số quan sát:

```text
T = sum(p_i) + sum(q_j)
```

Khi T>0, xác suất thực sự của mỗi loại truy vấn bằng trọng số của nó chia cho T. Nếu p,q đã là xác suất, thường tổng bằng 1. **Nhân tất cả trọng số với cùng một hằng số dương không làm thay đổi cây tối ưu**, vì chỉ nhân tổng chi phí lên cùng hệ số.

### Mô hình độ sâu và số lần so sánh

Trong công thức OBST chuẩn, ta đếm:

- Khóa thành công k_i có độ sâu d(k_i), gốc ở độ sâu 1.
- Lá giả d_j có độ sâu d(d_j), **cũng theo quy ước lá giả ở sau các nút thật**.

Chi phí **độ sâu có trọng số**:

```text
E_depth =
    sum_i p_i * depth(k_i)
  + sum_j q_j * depth(d_j)
```

**Quan trọng:** Một tìm kiếm thất bại đi qua các **nút khóa thật** trước khi tới liên kết null. Nếu đếm **chỉ số lần so sánh với khóa thật**, chi phí của truy vấn thất bại d_j là `depth(d_j)-1`, vì lá giả không chứa khóa thật để so sánh.

Vì vậy tổng số lần so sánh với **khóa thật**, tính theo trọng số, là:

```text
E_compare = E_depth - sum_j q_j
```

Khoản chênh `sum q_j` là **hằng số đối với mọi cây** cùng p,q, nên tối thiểu E_depth cũng tối thiểu E_compare. Hai đại lượng dẫn đến **cùng cây tối ưu**, nhưng **không nên công bố chúng là cùng một con số**.

Nếu T>0:

```text
E[depth]            = E_depth / T
E[real comparisons] = E_compare / T
```

Nếu T=0 (mọi tần suất bằng 0), **không có phân bố truy vấn để lấy trung bình**. Mọi cây có tổng chi phí có trọng số bằng 0; ta vẫn có thể dựng một cây hợp lệ theo quy tắc hòa, nhưng phải ghi **expected average không xác định**, không chia 0.

## 3. Tại sao cần tối ưu cấu trúc, không chỉ chọn gốc phổ biến nhất?

Một quy tắc dễ nghĩ đến là: “Chọn khóa có p_i lớn nhất làm gốc”. Quy tắc ấy có vẻ hợp lý vì khóa đó được so sánh ngay ở lần đầu.

Tuy nhiên, chọn gốc còn làm tăng độ sâu của **toàn bộ những khóa khác**. Gốc là phần tử trong dãy có thứ tự, nên lựa chọn gốc quyết định các khoảng trái/phải, đôi khi khiến một phía có cấu trúc sâu tốn kém.

**Phản ví dụ chỉ có tìm thành công** (đặt toàn bộ q=0):

```text
Khóa:       10   20   30
p:           2    2    3
```

Khóa 30 có tần suất lớn nhất p3=3, nhưng:

| Gốc được ép | Tổng độ sâu có trọng số tốt nhất với gốc ấy |
| --- | ---: |
| 10 | 14 |
| 20 | **12** |
| 30 | 13 |

Nếu chọn gốc **20**, cây `(20, 10, 30)` có chi phí:

```text
k20 ở sâu 1: 2*1 = 2
k10 ở sâu 2: 2*2 = 4
k30 ở sâu 2: 3*2 = 6
Tổng = 12
```

Nếu ép khóa 30 lên gốc, cây con trái tốt nhất chứa 10 và 20, tổng tối ưu chỉ đạt **13**. Vậy **gốc tối ưu không nhất thiết là khóa có tần suất lớn nhất**. Đây là lý do phải so sánh chi phí **hai cây con** và **các tầng sâu phát sinh**, chứ không dùng một luật tham lam không được chứng minh.

Tương tự, “chọn trung vị để cây cân bằng chiều cao” cũng **không bảo đảm tối ưu chi phí kỳ vọng** nếu p và q rất lệch.

## 4. Bài toán con là một đoạn khóa liên tiếp

Một cây con BST chứa các khóa:

```text
ki, k(i+1), ..., kj
```

phải chứa một **đoạn liên tiếp theo thứ tự khóa**, bởi các so sánh với tổ tiên đã xác định một khoảng giá trị. Vì vậy trạng thái DP tự nhiên là **hai chỉ số biên** `(i,j)`, không phải một tập con tùy ý.

Định nghĩa ba bảng:

- **`e[i][j]`:** chi phí độ sâu có trọng số **nhỏ nhất** của một cây con chứa các khóa `ki..kj`, tính độ sâu **cục bộ** của gốc cây con là 1 và gồm cả các lá giả tương ứng.
- **`w[i][j]`:** tổng trọng số của các khóa và các khoảng thất bại thuộc cây con đó.
- **`root[i][j]`:** chỉ số r của khóa `kr` được chọn làm gốc cho **một** cây con tối ưu trên đoạn [i,j].

Tại đoạn [i,j] có i≤j, các truy vấn tương ứng là:

```text
Khóa thành công:  pi, p(i+1), ..., pj
Khoảng thất bại: q(i-1), qi, ..., qj
```

Do đó:

```text
w[i][j] = (pi + ... + pj) + (q(i-1) + ... + qj)
```

Lưu `w` giúp không phải tính lại tổng trọng số của cùng một đoạn mỗi khi thử một gốc. Ta có thể tính w bằng quy hoạch động hoặc prefix sums, thay vì cộng bằng một vòng quét riêng trong vòng lựa chọn gốc.

### Đoạn rỗng cũng là một bài toán con

Khi i=j+1, đoạn **không có khóa thật** nhưng có đúng **một lá giả d(j)** nằm trong khoảng trống ấy.

Quy ước:

```text
e[i][i-1] = q(i-1)
w[i][i-1] = q(i-1)
```

Điều này rất quan trọng. Trong mô hình tính độ sâu của lá giả, cây rỗng vẫn có **một lá giả ở độ sâu cục bộ 1** và có trọng số q, nên chi phí cục bộ là q, không phải 0.

Nếu bài **chỉ xét các truy vấn tìm thành công**, ta có thể đặt **tất cả q_j=0**. Khi đó các trạng thái rỗng tự có chi phí bằng 0, trở thành phiên bản DP quen thuộc với riêng p_i.

## 5. Suy ra công thức quy hoạch động OBST

Giả sử đoạn [i,j] không rỗng và ta thử một khóa `kr` với i≤r≤j làm gốc.

- Cây con trái bắt buộc dùng `ki..k(r-1)`.
- Cây con phải bắt buộc dùng `k(r+1)..kj`.
- Khóa kr ở gốc có độ sâu 1.
- Mọi khóa/lá giả trong hai cây con sẽ có **độ sâu lớn hơn 1** so với độ sâu cục bộ trước khi gắn vào gốc mới.

Vì một nút gốc mới làm **mọi truy vấn của đoạn** tăng thêm một đơn vị độ sâu so với chi phí cục bộ hai cây con, ta được:

```text
COST(i,j,r) =
      e[i][r-1]
    + e[r+1][j]
    + w[i][j]
```

Trong đó `w[i][j]` đã bao gồm trọng số khóa kr cùng toàn bộ khóa và lá giả ở hai phía. Ta không cộng thêm riêng p_r, vì làm vậy sẽ tính trùng.

**Công thức chính:**

```text
e[i][i-1] = q(i-1)

e[i][j] =
    min over r=i..j {
        e[i][r-1] + e[r+1][j] + w[i][j]
    }                          với i <= j

root[i][j] = một chỉ số r đạt min đó
```

**Tổng trọng số cập nhật nhanh:**

```text
w[i][i-1] = q(i-1)
w[i][j] = w[i][j-1] + pj + qj
```

Công thức này dùng đúng các trọng số đã được tính ở đoạn [i,j−1]. Nó không cần quét toàn bộ [i,j] để tính lại w cho mỗi gốc.

**Giá trị cần trả:** `e[1][n]` là chi phí độ sâu có trọng số tối thiểu của toàn cây; `root[1][n]` cho khóa gốc. Nếu n=0, toàn cây chỉ có d0 và `e[1][0]=q0`.

## 6. Thử công thức với một khóa

Có một khóa k1 với trọng số thành công `p1=5`, hai trọng số tìm thất bại `q0=1, q1=2`.

Cây có dạng:

```text
      k1
     /  \
    d0   d1
```

Khóa k1 ở độ sâu 1, cả hai lá giả ở độ sâu 2.

```text
w[1][1] = q0 + p1 + q1 = 1 + 5 + 2 = 8

e[1][0] = q0 = 1
e[2][1] = q1 = 2

e[1][1] = 1 + 2 + 8 = 11
```

Tính trực tiếp theo độ sâu:

```text
E_depth = 5*1 + 1*2 + 2*2 = 11
E_compare = 11 - (1+2) = 8
T = 5 + 1 + 2 = 8

Số lần so sánh khóa thật trung bình = 8/8 = 1.
```

Đúng như ta mong đợi: dù tìm thấy hay không, với một khóa thật ta chỉ cần kiểm tra khóa ấy **một lần** rồi quyết định đi tới con rỗng.

Ví dụ này giúp tránh nhầm `e[i][i−1]=q` với “không có so sánh nào”. `e` trong công thức chuẩn là **độ sâu lá giả có trọng số**, còn số phép so sánh với khóa thật phải trừ tổng q.

## 7. Ví dụ đầy đủ với ba khóa: điền bảng e, w và root

Giả sử:

```text
keys = [10, 20, 30]
p    = [ 3,  3,  1]
q    = [2, 1, 1, 1]
T    = 3+3+1+2+1+1+1 = 12
```

Gán chỉ số khóa từ 1 đến 3. Đầu tiên:

```text
e[1][0]=w[1][0]=q0=2
e[2][1]=w[2][1]=q1=1
e[3][2]=w[3][2]=q2=1
e[4][3]=w[4][3]=q3=1
```

Sau đó xét mọi đoạn theo **độ dài tăng dần**:

| Đoạn [i,j] | w[i][j] | e[i][j] tối ưu | root[i][j] |
| --- | ---: | ---: | ---: |
| [1,1] | 6 | 9 | 1 (khóa 10) |
| [2,2] | 5 | 7 | 2 (khóa 20) |
| [3,3] | 3 | 5 | 3 (khóa 30) |
| [1,2] | 10 | 19 | 1 (khóa 10) |
| [2,3] | 7 | 13 | 2 (khóa 20) |
| **[1,3]** | **12** | **26** | **2 (khóa 20)** |

**Thử ba gốc cho đoạn [1,3]:**

```text
Chọn r=1 (khóa 10):
  e[1][0] + e[2][3] + w[1][3]
= 2 + 13 + 12 = 27

Chọn r=2 (khóa 20):
  e[1][1] + e[3][3] + w[1][3]
= 9 + 5 + 12 = 26        <-- nhỏ nhất

Chọn r=3 (khóa 30):
  e[1][2] + e[4][3] + w[1][3]
= 19 + 1 + 12 = 32
```

Vậy chọn **khóa 20 làm gốc**, cây trái chứa khóa 10, cây phải chứa khóa 30. Biểu diễn kèm lá giả:

```text
                20
               /  \
             10    30
            / \    / \
           d0 d1  d2 d3
```

Chi phí tính trực tiếp:

```text
Khóa thành công:
  p1*depth(10)=3*2=6
  p2*depth(20)=3*1=3
  p3*depth(30)=1*2=2
  Cộng = 11

Tìm thất bại:
  mọi dummy đều ở độ sâu 3
  (q0+q1+q2+q3)*3 = 5*3 = 15

E_depth = 11+15 = 26.
E_compare = 26 - sum(q)=26-5=21.
Trung bình so sánh khóa thật = 21/12 = 1,75.
```

Nếu ai đó viết “chi phí trung bình là 26/12 lần so sánh khóa thật” theo đúng mô hình trên thì **thiếu chính xác**: 26/12 là độ sâu có tính bước tới lá giả, còn 21/12 mới là số so sánh với **khóa thực**.

## 8. Cách điền bảng bottom-up đúng thứ tự phụ thuộc

Trạng thái [i,j] phụ thuộc những đoạn **ngắn hơn**:

- Đoạn trái [i,r−1] có độ dài r−i.
- Đoạn phải [r+1,j] có độ dài j−r.

Vì vậy cần đi từ các đoạn rỗng đến độ dài 1, 2, ..., n.

Giả mã chuẩn:

```text
OPTIMAL-BST(p[1..n], q[0..n]):
    for i = 1..n+1:
        e[i][i-1] = q[i-1]
        w[i][i-1] = q[i-1]

    for length = 1..n:
        for i = 1..n-length+1:
            j = i + length - 1
            w[i][j] = w[i][j-1] + p[j] + q[j]

            best = +infinity
            for r = i..j:
                candidate = e[i][r-1]
                          + e[r+1][j]
                          + w[i][j]
                if candidate < best:
                    best = candidate
                    root[i][j] = r

            e[i][j] = best

    return e[1][n], root
```

**Quy ước chỉ số:** Giả mã dùng chỉ số 1..n cho p/keys và 0..n cho q. Java có mảng 0-based nên tại công thức `p[j]` trong giả mã sẽ trở thành `hits[j-1]` trong mã chạy được. Không được trộn hai quy ước: đây là một trong những lỗi nhiều nhất khi lập trình OBST.

**Giá trị vô cùng:** Có thể dùng `Long.MAX_VALUE` cho biến best khi tìm min, nhưng phải tránh làm phép cộng với giá trị “không thể đạt”. Trong bài chuẩn mọi đoạn rỗng đã có chi phí q hợp lệ, và mọi gốc r đều tạo cây hợp lệ nên ta có thể khởi tạo best bằng giá trị ứng viên đầu hoặc dùng cờ “chưa có gốc”. Mã Java bên dưới dùng **cờ gốc chưa chọn** để không bỏ sót trường hợp chi phí tối ưu bằng `Long.MAX_VALUE` đúng theo kiểu long.

## 9. Dựng lại cây tối ưu từ bảng root

Tính mỗi `e[i][j]` chỉ cho **giá trị tốt nhất**; nếu bài yêu cầu **cấu trúc cây**, ta phải lưu lựa chọn `root[i][j]`.

Thuật toán dựng cây:

1. Với đoạn [i,j] rỗng (i>j), trả **lá giả d(i−1)**.
2. Nếu không rỗng, đặt `r=root[i][j]`; tạo nút khóa `kr`.
3. Dựng đệ quy cây trái từ [i,r−1].
4. Dựng đệ quy cây phải từ [r+1,j].
5. Gắn hai cây con vào nút kr.

Một biểu diễn tiền tự (*preorder*) tiện để in cây:

```text
TREE(i,j):
    if i > j: return "d" + (i-1)
    r = root[i][j]
    return "(" + key[r] + " "
               + TREE(i,r-1) + " "
               + TREE(r+1,j) + ")"
```

Với ví dụ ba khóa:

```text
(20 (10 d0 d1) (30 d2 d3))
```

Biểu diễn này chứa đủ thông tin **gốc, cây trái, cây phải** và vị trí các lá thất bại. Nếu chỉ cần BST chứa khóa thật, có thể không lưu dummy vào đối tượng cây mà dùng liên kết null; tuy vậy khi phân tích q_j phải biết null ấy tương ứng **khoảng thất bại nào**.

**Nhiều cây tối ưu:** Có thể có các lựa chọn r cho cùng chi phí min. Chương trình chọn **gốc có chỉ số nhỏ nhất** trong số các gốc đạt min, vì duyệt r tăng và chỉ cập nhật khi candidate **nhỏ hơn nghiêm ngặt** best. Chính sách hòa này tạo output tái lập được, nhưng không có nghĩa cây tối ưu luôn duy nhất.

## 10. Chứng minh công thức tối ưu đúng

### 10.1. Bất biến thứ tự BST

Mọi cây BST có tập khóa ki..kj phải chọn một trong các khóa kr (i≤r≤j) làm gốc. Những khóa nhỏ hơn kr **bắt buộc** nằm ở cây con trái, những khóa lớn hơn **bắt buộc** nằm ở cây con phải. Đây là phân hoạch theo **giá trị khóa**, không phải tùy ý chia đôi theo kích thước.

Vì các lá giả d(i−1)..dj là các khoảng tìm thất bại giữa các khóa, khi chọn r, các lá giả cũng chia đúng thành:

- Trái: `d(i−1), d(i), ..., d(r−1)`.
- Phải: `dr, d(r+1), ..., dj`.

Không có lá giả nào xuất hiện hai lần hoặc bị bỏ.

### 10.2. Cấu trúc con tối ưu

Giả sử có một BST tối ưu của [i,j] với gốc kr, nhưng cây con trái [i,r−1] **không tối ưu** cho chính đoạn ấy. Ta có thể thay cây con trái bằng một cây BST khác trên **cùng tập khóa và các khoảng thất bại**, có chi phí cục bộ thấp hơn. Phép thay không thay đổi gốc, cây phải hoặc bất biến tìm kiếm của BST; do đó làm giảm chi phí toàn cây, mâu thuẫn với giả thiết tối ưu.

Lập luận tương tự cho cây con phải. Vậy trong một cây tối ưu có gốc r, **hai cây con cũng phải tối ưu cho các đoạn tương ứng**.

### 10.3. Vì sao phải cộng w[i][j]?

Trong cây con, mọi khóa và lá giả đều có độ sâu cục bộ. Khi gắn cây con bên dưới một gốc mới, mọi độ sâu tăng **một đơn vị**, nên tổng chi phí của các nút/lá giả thuộc cây con tăng đúng **tổng trọng số của chúng**. Gốc kr mới có độ sâu 1 và đóng góp p_r. Tổng các trọng số được cộng thêm đúng bằng `w[i][j]`.

Từ đó, với gốc r bất kỳ, chi phí tốt nhất bằng:

```text
e[i][r-1] + e[r+1][j] + w[i][j]
```

Không thiếu đóng góp của root, cũng không tính lặp hai cây con.

### 10.4. Quy nạp theo độ dài đoạn

**Cơ sở:** Đoạn rỗng [i,i−1] chỉ có lá giả d(i−1) ở độ sâu cục bộ 1, nên chi phí đúng là q(i−1).

**Giả thiết:** Mọi đoạn ngắn hơn độ dài L đã được tính đúng chi phí tối ưu và gốc của một cây tối ưu.

**Bước quy nạp:** Đoạn [i,j] độ dài L có gốc r thuộc i..j. Theo cấu trúc con tối ưu, hai cây con phải là các lời giải tối ưu của đoạn ngắn hơn. Theo giả thiết, chi phí chúng là e[i][r−1] và e[r+1][j]. Chi phí toàn cây với gốc r là tổng hai chi phí ấy cộng w[i][j]. Thử **mọi** r và lấy min nên không bỏ sót cây BST tối ưu nào, đồng thời mỗi phương án được xét đều là một cây hợp lệ. Vì vậy e[i][j] đúng.

Từ quy nạp, e[1][n] đúng cho toàn bộ tập khóa. Truy vết root[i][j] dựng chính xác một cây đạt chi phí đó.

### 10.5. Thuật toán kết thúc

Các vòng `length,i,r` đều có khoảng hữu hạn; đệ quy dựng cây luôn chia đoạn [i,j] thành hai đoạn ngắn hơn, tới các đoạn rỗng. Không có chu trình giữa những trạng thái, và bảng được điền theo thứ tự độ dài tăng nên mọi phụ thuộc đã có trước khi dùng.

## 11. Độ phức tạp thời gian và bộ nhớ

Có khoảng:

```text
n(n+1)/2 = Θ(n²)
```

đoạn khóa [i,j] không rỗng.

Mỗi đoạn có độ dài L thử **L gốc khác nhau**. Tổng số phép thử:

```text
sum_{L=1..n} (n-L+1) * L
= n(n+1)(n+2) / 6
= Θ(n³)
```

Việc tính w[i][j] theo công thức tăng một khóa chỉ O(1) cho mỗi đoạn, tổng O(n²); chi phí chi phối là số gốc được thử.

| Thành phần | Thời gian | Bộ nhớ |
| --- | --- | --- |
| Kiểm tra n khóa và trọng số | O(n) | O(1) phụ nếu chỉ duyệt |
| Khởi tạo đoạn rỗng | O(n) | Bảng có sẵn |
| Tính w cho mọi đoạn | O(n²) | O(n²) cho w |
| Thử mọi gốc, tính e/root | **O(n³)** | O(n²) cho e và root |
| Dựng biểu diễn cây từ root | O(n) nút, chưa tính chi phí nối chuỗi tùy cách cài đặt | O(h) stack, tối đa O(n) |
| **DP cơ bản** | **O(n³)** | **O(n²)** |

Trong Java, dùng `StringBuilder` hoặc cấu trúc cây rõ ràng nếu xây chuỗi rất dài, vì nối nhiều chuỗi trong đệ quy bằng toán tử + có thể phát sinh thêm chi phí sao chép. Mã minh họa tối ưu về **DP** chứ không tuyên bố cách in hình cây là tối ưu về allocation cho n rất lớn.

**Với dữ liệu đã có xác suất p,q:** Việc biết xác suất tổng bằng 1 không làm số trạng thái giảm. Vẫn cần thử vị trí gốc của các đoạn nếu không có cấu trúc đặc biệt hay tối ưu hóa phù hợp.

## 12. Tối ưu hóa Knuth: từ O(n³) xuống O(n²)

Đối với OBST chuẩn với các trọng số **không âm** và chi phí có cấu trúc như công thức ở trên, có thể sử dụng tính **đơn điệu của gốc tối ưu** (*Knuth optimization*). Khi sử dụng quy tắc chọn gốc phù hợp trong trường hợp hòa, ta có:

```text
root[i][j-1] <= root[i][j] <= root[i+1][j]
```

cho những đoạn có ít nhất hai khóa, với các gốc của những đoạn nhỏ hơn đã được tính. Vì vậy, thay vì thử toàn bộ:

```text
r = i, i+1, ..., j
```

ta chỉ cần thử:

```text
r = root[i][j-1], ... , root[i+1][j]
```

Ví dụ một đoạn dài 20 khóa có thể chỉ cần xét một số gốc rất nhỏ nếu hai gốc của các đoạn con liền kề đã gần nhau.

**Điều kiện áp dụng:** Đây là một tính chất toán học của một lớp DP đoạn thỏa các điều kiện về **đơn điệu/Monge/quadrangle inequality**, trong đó OBST với trọng số không âm là ví dụ kinh điển. Không nên áp dụng tùy tiện cho **mọi** công thức phân đoạn kiểu “chọn gốc” hoặc khi đã thêm hình phạt tùy ý khiến điều kiện không còn đúng.

### Các bước triển khai Knuth an toàn

1. Khởi tạo đoạn một khóa: `root[i][i]=i`.
2. Điền bảng theo chiều độ dài tăng dần như trước.
3. Với L≥2, xác định khoảng r từ `root[i][j−1]` đến `root[i+1][j]`.
4. Tìm min chỉ trong khoảng ấy, lưu e và root.
5. Giữ nguyên công thức w và giá trị của các đoạn rỗng.

Tổng độ rộng các khoảng tìm kiếm trên mỗi lớp có cấu trúc telescoping, dẫn tới **O(n²)** thời gian cho toàn bộ DP, vẫn **O(n²)** bộ nhớ.

**Không có gì mâu thuẫn với ví dụ O(n³):** Đó là độ phức tạp của **phiên bản liệt kê mọi gốc**. Knuth là một tối ưu hóa nâng cao có **chứng minh riêng**; không được ghi O(n²) cho một chương trình vẫn chạy vòng r từ i tới j ở mọi trạng thái.

**Phạm vi bài:** Chương trình Java 17 ở phần tiếp theo cố ý dùng **O(n³)** để hiển thị trực tiếp công thức cơ bản và dễ kiểm chứng. Khi n lớn và p,q đáp ứng giả thiết, có thể nâng cấp vòng thử gốc sang Knuth sau khi kiểm tra đúng cả những trường hợp hòa.

## 13. Chương trình Java 17+ hoàn chỉnh

Chương trình nhận:

- `int[] keys`: khóa phân biệt, **tăng nghiêm ngặt**.
- `long[] hits`: n tần suất tìm thành công theo từng khóa.
- `long[] misses`: n+1 tần suất tìm thất bại theo khoảng d0..dn.

Tất cả tần suất phải **không âm**. Mã dùng `Math.addExact` để phát hiện khi tổng số truy vấn hoặc chi phí có trọng số vượt `long`; điều này tránh trả một số âm vì tràn. Các bảng `e, w, root` sử dụng quy ước khóa 1-based trong công thức, dù mảng keys và hits là 0-based của Java.

Kết quả gồm:

- `weightedDepthCost`: chi phí độ sâu có trọng số chuẩn e[1][n].
- `comparisonWeight`: tổng so sánh với khóa thật theo trọng số, bằng weightedDepthCost − sum(misses).
- `totalFrequency`: tổng p và q.
- `rootLabel`: khóa gốc hoặc "none" khi không có khóa.
- `shape`: biểu diễn cây tiền tự bao gồm các lá giả d0..dn.

**Các bảng chỉ dùng trong lúc giải**, không được làm rò rỉ ra ngoài API. Mảng đầu vào không bị sửa. Trong trường hợp mọi tần suất bằng 0, in `comparisons=undefined` vì không thể lấy trung bình khi mẫu số bằng 0; cây vẫn được dựng theo quy tắc hòa chọn gốc trái nhất.

Lưu file **`OptimalBSTDemo.java`**:

```java
import java.util.Objects;

public class OptimalBSTDemo {
    record Answer(long weightedDepthCost,
                  long comparisonWeight,
                  long totalFrequency,
                  String rootLabel,
                  String shape) {}

    static Answer solve(
            int[] keys, long[] hits, long[] misses) {
        Objects.requireNonNull(keys, "keys must not be null");
        Objects.requireNonNull(hits, "hits must not be null");
        Objects.requireNonNull(misses, "misses must not be null");

        int n = keys.length;
        if (hits.length != n || misses.length != n + 1) {
            throw new IllegalArgumentException(
                    "hits length must be n, misses length n+1");
        }

        for (int i = 1; i < n; i++) {
            if (keys[i - 1] >= keys[i]) {
                throw new IllegalArgumentException(
                        "keys must be strictly increasing");
            }
        }

        long total = 0;
        long missTotal = 0;
        for (long frequency : hits) {
            if (frequency < 0) {
                throw new IllegalArgumentException(
                        "frequencies must be nonnegative");
            }
            total = Math.addExact(total, frequency);
        }
        for (long frequency : misses) {
            if (frequency < 0) {
                throw new IllegalArgumentException(
                        "frequencies must be nonnegative");
            }
            missTotal = Math.addExact(missTotal, frequency);
            total = Math.addExact(total, frequency);
        }

        // e[i][j], w[i][j], root[i][j], voi keys i..j
        // theo chi so 1-based trong cong thuc.
        long[][] e = new long[n + 2][n + 1];
        long[][] w = new long[n + 2][n + 1];
        int[][] root = new int[n + 2][n + 1];

        // Doan rong [i, i-1] chi co dummy d(i-1).
        for (int i = 1; i <= n + 1; i++) {
            e[i][i - 1] = misses[i - 1];
            w[i][i - 1] = misses[i - 1];
        }

        for (int length = 1; length <= n; length++) {
            for (int i = 1; i <= n - length + 1; i++) {
                int j = i + length - 1;
                w[i][j] = Math.addExact(
                        Math.addExact(w[i][j - 1], hits[j - 1]),
                        misses[j]);

                long bestCost = Long.MAX_VALUE;
                int bestRoot = 0; // 0: chua chon goc

                for (int r = i; r <= j; r++) {
                    long candidate = Math.addExact(
                            Math.addExact(e[i][r - 1],
                                          e[r + 1][j]),
                            w[i][j]);

                    // Khi hoa, giu r nho nhat (duyet tang).
                    if (bestRoot == 0 || candidate < bestCost) {
                        bestCost = candidate;
                        bestRoot = r;
                    }
                }

                e[i][j] = bestCost;
                root[i][j] = bestRoot;
            }
        }

        long depthCost = e[1][n]; // n=0: e[1][0] = q0
        long comparisonCost = Math.subtractExact(
                depthCost, missTotal);
        String rootLabel = n == 0
                ? "none"
                : Integer.toString(keys[root[1][n] - 1]);
        String shape = buildTree(keys, root, 1, n);

        return new Answer(
                depthCost, comparisonCost, total,
                rootLabel, shape);
    }

    private static String buildTree(
            int[] keys, int[][] root, int i, int j) {
        if (i > j) {
            return "d" + (i - 1);
        }
        int r = root[i][j];
        return "(" + keys[r - 1]
                + " " + buildTree(keys, root, i, r - 1)
                + " " + buildTree(keys, root, r + 1, j)
                + ")";
    }

    private static void show(
            String label,
            int[] keys, long[] hits, long[] misses) {
        Answer a = solve(keys, hits, misses);
        String averageComparisons =
                a.totalFrequency() == 0
                ? "undefined"
                : a.comparisonWeight() + "/"
                        + a.totalFrequency();

        System.out.println(label
                + ": depthCost=" + a.weightedDepthCost()
                + ", comparisons=" + averageComparisons
                + ", root=" + a.rootLabel());
        System.out.println("  tree=" + a.shape());
    }

    public static void main(String[] args) {
        show("Sample",
                new int[]{10, 20, 30},
                new long[]{3, 3, 1},
                new long[]{2, 1, 1, 1});

        show("Classic",
                new int[]{10, 20, 30, 40, 50},
                new long[]{15, 10, 5, 10, 20},
                new long[]{5, 10, 5, 5, 10, 10});

        show("Greedy trap",
                new int[]{10, 20, 30},
                new long[]{2, 2, 3},
                new long[]{0, 0, 0, 0});

        show("Single",
                new int[]{10},
                new long[]{5},
                new long[]{1, 2});

        show("Empty",
                new int[0],
                new long[0],
                new long[]{9});

        show("Zero frequencies",
                new int[]{10, 20},
                new long[]{0, 0},
                new long[]{0, 0, 0});

        try {
            solve(new int[]{20, 10},
                    new long[]{1, 1},
                    new long[]{0, 0, 0});
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Invalid keys: " + ex.getMessage());
        }

        try {
            solve(new int[]{10},
                    new long[]{-1},
                    new long[]{0, 0});
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Invalid weight: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac OptimalBSTDemo.java
java OptimalBSTDemo
```

**Stdout chính xác:**

```text
Sample: depthCost=26, comparisons=21/12, root=20
  tree=(20 (10 d0 d1) (30 d2 d3))
Classic: depthCost=290, comparisons=245/105, root=40
  tree=(40 (20 (10 d0 d1) (30 d2 d3)) (50 d4 d5))
Greedy trap: depthCost=12, comparisons=12/7, root=20
  tree=(20 (10 d0 d1) (30 d2 d3))
Single: depthCost=11, comparisons=8/8, root=10
  tree=(10 d0 d1)
Empty: depthCost=9, comparisons=0/9, root=none
  tree=d0
Zero frequencies: depthCost=0, comparisons=undefined, root=10
  tree=(10 d0 (20 d1 d2))
Invalid keys: keys must be strictly increasing
Invalid weight: frequencies must be nonnegative
```

### Đọc output từng trường hợp

**Sample:** Có ba khóa 10,20,30 và bốn khoảng tìm thất bại. Gốc 20 cho tổng độ sâu có trọng số 26, tổng so sánh với khóa thật là 21 trên 12 truy vấn quan sát, tức 21/12.

**Classic:** Ví dụ năm khóa, trọng số thành công [15,10,5,10,20] và thất bại [5,10,5,5,10,10], tương ứng một phiên bản số nguyên của dữ liệu OBST kinh điển. Chi phí độ sâu có trọng số là 290; do tổng trọng số thất bại 45, số so sánh khóa thật có trọng số là 245. Gốc tối ưu là khóa 40, không phải khóa có p lớn nhất (khóa 50 có p=20).

**Greedy trap:** Trọng số p=[2,2,3], q=0. Khóa 30 có tần suất lớn nhất nhưng chi phí cây tốt nhất với gốc 30 là 13; gốc 20 cho chi phí 12. Chỉ nhìn p lớn nhất rồi quyết định gốc sẽ bỏ lỡ nghiệm tối ưu.

**Single:** Một khóa thật và hai khoảng trống. Mỗi truy vấn so sánh đúng một lần với khóa thật; average comparisons = 8/8=1. Chi phí độ sâu chuẩn bao gồm hai lá giả nên là 11.

**Empty:** Không có khóa thật nhưng vẫn có khoảng thất bại d0 trọng số 9. Theo mô hình dummy leaf, `e[1][0]=9`; số so sánh với **khóa thật** bằng 0. Vì thế cặp số 9 và 0/9 không mâu thuẫn nhau.

**Zero frequencies:** Mọi p và q bằng 0, nên mọi cây BST hợp lệ có chi phí có trọng số bằng 0. Quy tắc hòa của mã chọn gốc nhỏ nhất trong từng đoạn, cho kết quả cây lệch phải. Trung bình `0/0` không xác định, nên in "undefined".

**Invalid keys/weight:** Mã từ chối khóa không tăng nghiêm ngặt và tần suất âm. Đầu vào `null` hoặc sai số phần tử p/q cũng được xử lý theo các quy tắc kiểm tra của phương thức `solve`.

### Lưu ý về kiểu số và chi phí

Mã dùng `long` cho tần suất và chi phí, `Math.addExact` để phát hiện tràn. Nếu số mẫu hoặc chi phí quá lớn đến mức không vừa long, chương trình ném `ArithmeticException` thay vì âm thầm trả chi phí sai; để đáp ứng yêu cầu lớn hơn, cần dùng kiểu số chính xác phù hợp như `BigInteger`.

Code thực hiện **vòng thử mọi gốc r=i..j**, vì vậy độ phức tạp vẫn **O(n³)**. Đừng căn cứ vào phần giới thiệu Knuth rồi nghĩ chương trình này tự động có O(n²).

## 14. Phiên bản chỉ có tìm kiếm thành công

Trong một số đề, chỉ cho tần suất tìm thấy khóa `p1..pn`, không có xác suất tìm thất bại. Khi ấy đặt **mọi q_j=0** trong công thức chung. Ta thu được dạng đơn giản hơn:

```text
F(i,i-1) = 0

F(i,j) =
    sum(p_i..p_j)
    + min_{r=i..j} (F(i,r-1) + F(r+1,j))
```

Ý nghĩa: mỗi khóa trong đoạn bị đẩy sâu hơn một cấp sau khi gắn dưới gốc được chọn; tổng trọng số thành công là tổng p trên đoạn.

Ví dụ p=[2,2,3] cho ba khóa 10,20,30:

```text
Root 10: chi phí tối ưu 14
Root 20: chi phí tối ưu 12
Root 30: chi phí tối ưu 13

Chọn root 20.
```

**Không cần tự viết một thuật toán riêng:** Có thể gọi `solve(keys,p,qZeros)` với qZeros dài n+1 toàn 0. Các lá giả vẫn xuất hiện trong biểu diễn cấu trúc để minh họa các vị trí tìm thất bại, nhưng trọng số chúng bằng 0 nên không đóng góp vào mục tiêu.

Tuy nhiên, nếu ứng dụng thực tế có nhiều tìm kiếm không thành công, **bỏ qua q chỉ vì đề không ghi rõ** có thể tạo cây không tối ưu cho lưu lượng truy vấn thực. Cần phân biệt “bài toán chỉ thành công” với “không có dữ liệu về thất bại”.

## 15. Các trường hợp biên và yêu cầu thực tế

| Trường hợp | Cách xử lý/mô hình đúng |
| --- | --- |
| `n=0`, q có 1 phần tử | Cây không có khóa; chỉ có d0, e[1][0]=q0 |
| `n=1` | Gốc bắt buộc là khóa duy nhất; hai lá giả d0,d1 |
| Khóa không sắp tăng | Sắp khóa kèm p tương ứng **trước** khi giải, hoặc từ chối như mã mẫu |
| Khóa trùng | Bài toán BST khóa phân biệt không áp dụng nguyên xi; cần quy tắc xử lý khóa trùng |
| p hoặc q âm | Không hợp lệ cho tần suất/xác suất |
| Tất cả trọng số bằng 0 | Mọi cây cùng chi phí 0; average không xác định |
| Có trọng số bằng 0 | Hợp lệ; có thể gây nhiều gốc tối ưu hòa |
| Chỉ quan tâm thành công | Cho q=0, dùng công thức thành công-only |
| Có tần suất thất bại | Phải lưu **n+1 khoảng q0..qn** đúng thứ tự |
| p,q là xác suất thay vì số đếm | Dùng số thực có cân nhắc sai số; cùng công thức, tổng thường bằng 1 |
| p,q là số đếm lớn | Dùng long và phát hiện tràn; có thể cần BigInteger |
| Muốn dựng cây thực có con trái/phải | Truy vết root để cấp đối tượng Node; không chỉ lấy e[1][n] |
| Yêu cầu độ cao tối đa bị giới hạn | Đã thay bài toán; trạng thái có thể cần thêm giới hạn chiều cao |
| Chi phí so sánh khóa không đều | Cần sửa hàm mục tiêu và công thức chuyển tương ứng |
| Có cập nhật/insert/delete thường xuyên | Cây tối ưu tĩnh có thể trở nên lỗi thời; cần cân nhắc cơ chế cân bằng/điều chỉnh động |

### Nếu keys chưa sắp

OBST giả định `k1<...<kn`. Nếu người dùng có cặp (key,frequency), việc sắp trước là hợp lệ **chỉ khi tần suất thành công p di chuyển cùng khóa** và các tần suất thất bại q được **tái định nghĩa theo khoảng sau khi sắp**.

Không thể chỉ sort keys rồi để p giữ nguyên vị trí ban đầu: như vậy ghép sai tần suất cho khóa. Cũng không thể áp dụng một phép hoán vị tùy tiện lên q vì q gắn với **các khoảng trên trục khóa**, không phải gắn một-một với các khóa.

### Nếu phân bố truy vấn thay đổi

OBST là lời giải **tĩnh** tối ưu theo một phân bố p,q được cung cấp. Nếu thống kê truy vấn thay đổi theo thời gian, cây từng tối ưu có thể không còn tối ưu. Tái cấu trúc một BST có thể tốn chi phí di chuyển dữ liệu/con trỏ; không nên tối ưu chỉ dựa trên chi phí tìm kiếm mà bỏ qua chi phí cập nhật.

**So sánh với AVL/Red-Black Tree:** Các cây cân bằng kiểu AVL hoặc Red-Black Tree bảo đảm chiều cao O(log n) và tìm kiếm trường hợp xấu O(log n), hữu ích khi không biết phân bố truy vấn hoặc có cập nhật thường xuyên. OBST tối ưu **chi phí trung bình có trọng số** theo một phân bố tĩnh, nhưng cây tối ưu có thể không cân bằng và không có cùng bảo đảm chiều cao. Đây là **hai tiêu chí tối ưu khác nhau**.

## 16. Lỗi thường gặp và cách tránh

1. **Chỉ chọn khóa có p lớn nhất làm gốc.** Phản ví dụ p=[2,2,3] cho thấy gốc tốt nhất có thể không phải khóa phổ biến nhất.
2. **Luôn chọn trung vị.** Cây cân bằng chiều cao không nhất thiết tối thiểu chi phí trung bình theo trọng số.
3. **Quên n+1 khoảng tìm thất bại.** Với n khóa có n+1 vị trí null; q có độ dài n+1.
4. **Đặt trạng thái đoạn rỗng bằng 0 dù q>0.** Trong mô hình độ sâu chuẩn, đoạn rỗng chứa lá giả có chi phí q.
5. **Cộng p_r hai lần.** Công thức `eLeft+eRight+w` đã tính gốc trong w.
6. **Nhầm độ sâu lá giả với số lần so sánh khóa thật.** Truy vấn thất bại có số so sánh = depth(dummy)−1; E_compare=E_depth−sum q.
7. **Không phân biệt số đếm với xác suất.** Nếu p,q là tần suất, phải chia cho T>0 để báo kỳ vọng trung bình.
8. **Chia cho 0 khi tất cả tần suất bằng 0.** Khi ấy average không xác định, dù tối ưu chi phí tổng bằng 0.
9. **Gán q_i vào sai khoảng.** q0 trước k1, qn sau kn, q_i giữa ki và k(i+1).
10. **Sai cơ sở chỉ số trong Java.** keys/hits là 0-based, công thức e/w/root dùng 1-based; hit ở khóa kj là hits[j−1].
11. **Sử dụng [i,j) ở một nơi và [i,j] ở nơi khác.** Mã đang dùng đoạn đóng khóa 1-based [i,j] và trạng thái rỗng [i,i−1].
12. **Tính bảng theo i tăng mà không đảm bảo các đoạn con đã có.** Cần đi theo chiều độ dài tăng.
13. **Không lưu root khi đề hỏi hình cây.** e chỉ cung cấp giá trị tối ưu, không đủ để dựng cấu trúc.
14. **Truy vết root ở đoạn rỗng.** Khi i>j phải trả dummy ngay, không truy cập root[i][j].
15. **Tự khẳng định mọi cây tối ưu đều duy nhất.** Có thể hòa chi phí; cần quy tắc chọn gốc cụ thể.
16. **Dùng biến best=Long.MAX_VALUE nhưng bỏ trường hợp candidate bằng Long.MAX_VALUE.** Cần cờ chưa chọn gốc hoặc khởi tạo từ ứng viên thực đầu tiên.
17. **Cộng long không kiểm soát tràn.** Một tổng trọng số sai có thể đổi kết quả min; dùng Math.addExact hoặc kiểu chính xác hơn.
18. **Quên kiểm tra keys phân biệt.** Với khóa trùng, bất biến BST strict-left/strict-right và định nghĩa q theo khoảng cần xem lại.
19. **Gọi O(n²) cho code vẫn xét toàn bộ r=i..j.** Chỉ phiên bản dùng tối ưu hóa Knuth đã chứng minh mới đạt O(n²).
20. **Áp dụng Knuth cho bất kỳ interval DP nào.** Phải có tính đơn điệu và giả thiết của công thức chi phí, không suy diễn từ việc có hai biên i,j.
21. **Suy ra cây tối ưu tĩnh cũng tự cân bằng khi có insert/delete.** Mô hình OBST không xử lý động theo mặc định.
22. **Chỉ tối ưu truy vấn thành công trong khi ứng dụng có nhiều miss.** q có thể ảnh hưởng mạnh đến lựa chọn gốc.
23. **Nhầm chi phí trung bình với chiều cao lớn nhất.** Cây có chi phí kỳ vọng tốt nhất có thể có đường đi sâu đối với truy vấn hiếm.
24. **Không lưu số đếm p cùng khóa khi tiền xử lý.** Sort keys riêng lẻ làm lệch thống kê.
25. **Không tính cả q trong w.** Thiếu tần suất thất bại khiến công thức tối ưu sai cho bài chuẩn.
26. **Sai tổng w[i][j] khi nối đoạn.** Đúng là w[i][j−1]+p_j+q_j, vì q(j−1) đã nằm trong đoạn trước.
27. **Đánh giá false negative vì đại lượng chi phí khác nhau.** Hai chương trình có thể dùng mô hình đếm độ sâu dummy hoặc số so sánh thật; cần quy về cùng một quy ước trước khi so số.

## 17. Bài tập tự luyện có đáp án

**Bài 1.** Ba khóa 10, 20, 30 được hỏi với tần suất p=[2,2,3] và không có tìm thất bại. Có nên chọn khóa 30 làm gốc không?

**Đáp án:** Không nếu muốn chi phí tối thiểu. Gốc 30 có chi phí tối ưu 13; chọn gốc 20 được 12. Quy tắc “p lớn nhất làm gốc” không bảo đảm đúng.

**Bài 2.** Với n=4 khóa, cần bao nhiêu tần suất p và q trong bài chuẩn?

**Đáp án:** Có 4 tần suất thành công p1..p4 và **5 tần suất thất bại** q0..q4, tương ứng khoảng trước/giữa/sau các khóa.

**Bài 3.** Vì sao đoạn rỗng [i,i−1] có chi phí e[i][i−1]=q(i−1) trong công thức chuẩn, thay vì 0?

**Đáp án:** Đoạn rỗng vẫn chứa một lá giả đại diện cho tìm thất bại, có độ sâu cục bộ 1. Chi phí độ sâu có trọng số của lá ấy là q(i−1). Nếu bài không tính thất bại, q được đặt 0 và công thức thành 0.

**Bài 4.** Viết công thức chi phí khi chọn kr làm gốc của đoạn [i,j].

**Đáp án:** `e[i][r−1]+e[r+1][j]+w[i][j]`, với `w[i][j]=Σ_{t=i}^j p_t + Σ_{t=i-1}^j q_t`. Thử mọi r trong i..j rồi lấy giá trị nhỏ nhất.

**Bài 5.** Với p=[3,3,1], q=[2,1,1,1], tính e[1][3] và gốc tối ưu.

**Đáp án:** Ba gốc cho chi phí lần lượt 27, 26, 32; chọn r=2 tức khóa 20, `e[1][3]=26`.

**Bài 6.** Dữ liệu bài 5 có tổng tần suất T=12, tổng miss=5. Kỳ vọng số so sánh với khóa thật là bao nhiêu?

**Đáp án:** `(26−5)/12=21/12=1,75`. Con số `26/12` là kỳ vọng độ sâu theo mô hình có thêm lá giả, không phải chỉ đếm phép so sánh với khóa thật.

**Bài 7.** Nếu n=0 và q0=9, đoạn tổng có chi phí độ sâu và chi phí so sánh với khóa thật là bao nhiêu?

**Đáp án:** Chi phí độ sâu chuẩn e[1][0]=9 vì có dummy d0; tổng so sánh với khóa thật =9−9=0. Không có khóa để so sánh.

**Bài 8.** Có n khóa, số lượng bài toán con [i,j] không rỗng là bao nhiêu? Tại sao thuật toán cơ bản O(n³)?

**Đáp án:** Có n(n+1)/2=Θ(n²) đoạn. Mỗi đoạn dài L thử L gốc, tổng số lần thử là n(n+1)(n+2)/6=Θ(n³).

**Bài 9.** Một DP interval tối ưu với O(n²) trạng thái và bảng root, làm sao dựng lại cây?

**Đáp án:** Ở [i,j] lấy r=root[i][j], dựng hai đoạn [i,r−1], [r+1,j] rồi gắn dưới khóa kr. Với đoạn rỗng trả dummy d(i−1). Mỗi khóa/lá giả xuất hiện đúng một lần.

**Bài 10.** Hai nghiệm cùng chi phí min và chọn hai gốc khác nhau thì nghiệm nào được xem là đúng?

**Đáp án:** **Cả hai**, miễn là thỏa BST và cùng chi phí tối ưu. Mã Java chọn gốc chỉ số nhỏ nhất khi hòa để tái lập output; không phải một yêu cầu bắt buộc của OBST.

**Bài 11.** Khi nào có thể dùng Knuth optimization và nó thay đổi phần nào của thuật toán?

**Đáp án:** Với OBST chuẩn có trọng số không âm và cấu trúc chi phí thỏa điều kiện đơn điệu gốc, ta giới hạn r trong [root[i][j−1], root[i+1][j]] thay vì mọi i..j, giảm O(n³) xuống O(n²). Công thức e và cách dựng root không thay đổi.

**Bài 12.** Nếu đề chỉ cho tần suất thành công mà không cho xác suất thất bại, xây một bài OBST đơn giản bằng cách nào?

**Đáp án:** Đặt mọi q_j=0, dùng công thức thành công-only `F(i,j)=Σp + min(Fleft+Fright)`, và lưu root. Đây là một giả thiết về phân bố truy vấn, không có nghĩa tìm thất bại ngoài đời thực không tồn tại.

**Bài 13.** Vì sao không thể chỉ sort mảng keys rồi giữ nguyên p và q khi chúng đã được gán theo dữ liệu ban đầu?

**Đáp án:** p phải đi cùng khóa cụ thể; q phải tương ứng các khoảng giá trị giữa khóa đã sắp. Sort keys riêng làm mất ánh xạ của tần suất và dẫn đến tối ưu cho **một phân bố sai**.

**Bài 14.** Cùng một tập khóa, cây OBST tối ưu có bắt buộc là AVL/Red-Black Tree không?

**Đáp án:** Không. OBST tối ưu kỳ vọng có trọng số theo một phân bố tĩnh; AVL/Red-Black bảo đảm chiều cao logarithmic để có thời gian truy vấn trường hợp xấu. Hai tiêu chí khác nhau.

**Bài 15.** Tất cả p và q bằng 0. Root nào được chọn và kỳ vọng số phép so sánh là bao nhiêu?

**Đáp án:** Mọi cây có chi phí tổng 0, nên root không duy nhất; mã chọn gốc nhỏ nhất khi hòa. Vì T=0, không thể chia cho tổng tần suất để định nghĩa kỳ vọng trung bình. Chương trình in "undefined".

**Bài 16.** Nếu thêm giới hạn cây không được có độ sâu lớn hơn H, công thức e[i][j] của bài chuẩn có còn đủ không?

**Đáp án:** Không chắc. Khi giới hạn chiều cao, lựa chọn cây con phụ thuộc **chiều cao tối đa còn được phép**, nên có thể cần trạng thái `e[i][j][h]` hoặc một cách tối ưu khác. Không dùng lại công thức hai chiều mà không kiểm tra ràng buộc mới.

## Ghi nhớ

**Cây tìm kiếm nhị phân tối ưu** là bài **DP đoạn trên cấu trúc cây**. Đối với khóa đã sắp `k1<...<kn`, tần suất thành công `p1..pn` và n+1 tần suất thất bại `q0..qn`, một bài toán con [i,j] thử mọi khóa kr làm gốc. Công thức trọng tâm là:

```text
e[i][i-1] = q(i-1)
w[i][i-1] = q(i-1)
w[i][j] = w[i][j-1] + pj + qj

e[i][j] = min_r(
    e[i][r-1] + e[r+1][j] + w[i][j]
),  i <= r <= j
```

Lưu `root[i][j]` để dựng lại cây, không chỉ biết chi phí. DP cơ bản có **O(n³) thời gian, O(n²) bộ nhớ**; với giả thiết chuẩn và tính đơn điệu gốc, tối ưu hóa Knuth có thể giảm thời gian xuống **O(n²)**. Trong mô hình có lá giả, chi phí số so sánh với **khóa thật** bằng chi phí độ sâu có trọng số **trừ tổng q**. Quan trọng hơn hết: **đừng nhầm gốc phổ biến nhất hoặc cây cân bằng chiều cao với cây tối ưu chi phí tìm kiếm theo phân bố**.
