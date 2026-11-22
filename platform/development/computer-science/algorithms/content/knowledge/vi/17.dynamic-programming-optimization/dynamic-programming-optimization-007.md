# Tối ưu Knuth và các điều kiện bắt buộc

**Tối ưu Knuth** (*Knuth optimization*) là một kỹ thuật giảm số vị trí phân hoạch/nút gốc phải thử trong một lớp **quy hoạch động trên đoạn** (*interval dynamic programming*). Ở những bài thỏa đúng điều kiện toán học, kỹ thuật này giảm thời gian từ **O(n³)** xuống **O(n²)** mà vẫn giữ **O(n²)** bộ nhớ. Ví dụ kinh điển là **cây tìm kiếm nhị phân tối ưu** (*Optimal Binary Search Tree – OBST*).

Điểm khó nhất không phải thay vòng `for`, mà là chứng minh **có thể giới hạn vị trí lựa chọn tối ưu** vào một khoảng rất hẹp. Nếu làm theo “mẹo” mà không kiểm tra dạng chuyển trạng thái, tính đơn điệu của trọng số đoạn và **bất đẳng thức tứ giác** (*quadrangle inequality*), ta có thể **bỏ sót đáp án tối ưu**. Có những bài chỉ khác nhau một khoản phí tùy gốc hoặc có trọng số đoạn tùy ý mà giới hạn Knuth không còn đúng.

Bài học giải thích:

1. Nhận diện **dạng DP đoạn** có thể xét Knuth.
2. Phát biểu đúng **các điều kiện đủ** và phân biệt chúng với tính chất “ngẫu nhiên đúng trên một bộ dữ liệu”.
3. Hiểu **đơn điệu vị trí tối ưu** `opt[i][j−1] ≤ opt[i][j] ≤ opt[i+1][j]`.
4. Biết **khi nào dùng được**, **khi nào không** và **cách tạo phản ví dụ**.
5. Cài đặt cả **DP cơ bản O(n³)** và **DP Knuth O(n²)** bằng Java 17+, so sánh kết quả và số lần xét ứng viên.
6. Chứng minh chi phí O(n²) bằng **tổng độ rộng khoảng ứng viên triệt tiêu dạng telescoping**, thay vì chỉ khẳng định mỗi đoạn thử O(1) gốc.

## 1. Bối cảnh: nhiều bài DP đoạn tốn O(n³) ở bước chọn gốc

Giả sử dữ liệu có thứ tự `1,2,...,n`. Mỗi trạng thái `dp[i][j]` trả chi phí tối ưu cho đoạn **đóng** [i,j]. Khi cần chọn một vị trí `k` làm gốc hoặc một vị trí quyết định bên trong đoạn, ta thường xét:

```text
for length = 1 .. n:
    for i = 1 .. n-length+1:
        j = i+length-1
        for k = i .. j:
            thử chi phí nếu chọn k làm gốc
```

Có Θ(n²) đoạn [i,j] và mỗi đoạn có tối đa Θ(n) ứng viên k. Tổng:

```text
sum(length * (n-length+1), length=1..n)
= n(n+1)(n+2)/6
= Θ(n³)
```

Nếu mỗi ứng viên được tính O(1) nhờ lưu kết quả bài toán con, tổng thời gian là **O(n³)**; bảng `dp` và `opt` tốn **O(n²)** bộ nhớ.

**Mục tiêu của Knuth:** Không thay đổi ý nghĩa của `dp[i][j]`, không bỏ trạng thái nào, không giả định một vị trí gốc cố định. Chỉ thay **miền duyệt k** từ toàn đoạn sang một khoảng nhỏ **được chứng minh còn chứa gốc tối ưu**.

Không phải bài nào có ba vòng lặp cũng áp dụng được. Bước đầu tiên luôn là **viết chính xác công thức chuyển** và làm rõ điều kiện toán học.

## 2. Dạng truy hồi tiêu biểu của Knuth

Dạng dùng trong cây tìm kiếm nhị phân tối ưu:

```text
dp[i][j] = W(i,j)
         + min over k = i..j {
               dp[i][k-1] + dp[k+1][j]
           }

opt[i][j] = một k đạt giá trị nhỏ nhất

Trạng thái rỗng dp[i][i-1] có giá trị cơ sở phù hợp.
```

Ở đây:

- `i,j` là hai biên của đoạn **theo thứ tự cố định**.
- `k` là vị trí được chọn làm **gốc** của đoạn.
- `dp[i][k−1]` và `dp[k+1][j]` là hai phần con nhỏ hơn.
- `W(i,j)` là **chi phí cộng thêm phụ thuộc vào đoạn [i,j]**, **không phụ thuộc trực tiếp vào k**.
- `opt[i][j]` lưu **vị trí gốc tối ưu**, không lưu giá trị tối ưu; giá trị đã nằm ở dp.

Đây là **dạng root-inclusive**, trong đó gốc k **không nằm trong cây con trái hoặc phải**. Có những cách viết DP khác dùng phân hoạch giữa k và k+1:

```text
dp[i][j] = W(i,j)
         + min over k = i..j-1 {
               dp[i][k] + dp[k+1][j]
           }
```

Dạng thứ hai dùng **biên và công thức khác**, vì vậy **không được áp dụng nguyên xi các chỉ số opt[i][j−1], opt[i+1][j] nếu chưa chuyển đổi/kiểm tra định lý đúng cho dạng đó**. Bài này ưu tiên dạng **chọn gốc k ∈ [i,j]** và đoạn rỗng `[i,i−1]`.

### Vì sao W không được tùy ý phụ thuộc k?

Nếu chi phí là `W(i,j,k)` hoặc có khoản phạt phụ thuộc vị trí gốc, phép chuyển không còn đúng cùng dạng chuẩn. Một số bài vẫn có tính đơn điệu của lựa chọn tối ưu nhờ định lý riêng, nhưng **không thể mặc định Knuth áp dụng**.

Ví dụ, nếu chọn gốc k còn bị phạt thêm theo chiều cao cây bên trái hoặc số lượng nút sâu hơn một ngưỡng, việc thay gốc ảnh hưởng đến chi phí theo cách không thể tóm tắt chỉ bằng W(i,j). Khi đó có thể cần trạng thái mới, chứng minh khác hoặc thuật toán khác.

## 3. Kết quả then chốt: tính đơn điệu của vị trí tối ưu

Với những lớp bài thỏa giả thiết của định lý Knuth, các vị trí gốc tối ưu có tính chất:

```text
opt[i][j-1] <= opt[i][j] <= opt[i+1][j]
```

với đoạn [i,j] dài ít nhất 2. Hai đoạn [i,j−1] và [i+1,j] ngắn hơn một phần tử, nên bảng DP được tính theo **độ dài đoạn tăng dần** đã biết cả hai giá trị opt trước khi tính [i,j].

Từ tính chất này, thay vì:

```text
for k = i .. j:
    thử k
```

ta chỉ cần:

```text
left  = opt[i][j-1]
right = opt[i+1][j]

for k = left .. right:
    thử k
```

**Khoảng [left,right] là đóng**, gồm cả hai đầu. Dùng `k < right` thay vì `k <= right` có thể bỏ gốc tối ưu ở biên phải.

**Đối với đoạn chỉ có một khóa**, gốc duy nhất là chính khóa ấy:

```text
opt[i][i] = i
```

Không nên truy cập `opt[i][i−1]` hoặc `opt[i+1][i]` rồi coi nó là gốc của đoạn rỗng; những trạng thái ấy không có khóa thực.

### Tại sao lại so với hai đoạn lệch nhau một vị trí?

Ở đoạn [i,j], ta đã biết tối ưu của hai đoạn con:

- [i,j−1]: bỏ khóa cuối bên phải.
- [i+1,j]: bỏ khóa đầu bên trái.

Định lý nói rằng khi mở rộng đoạn từ hai hướng theo cấu trúc chi phí thích hợp, **vị trí gốc tối ưu không thể nhảy ra ngoài hai mốc ấy**. Đây là kết quả của các tính chất về chi phí đoạn và sự giao nhau của lựa chọn tối ưu; **không phải điều đúng với mọi bài quy hoạch động có gốc**.

### Có nhiều gốc đạt cùng chi phí nhỏ nhất

Một số đoạn có nhiều lựa chọn k đồng tối ưu. Phải quy ước **chọn một gốc tối ưu nhất quán**, chẳng hạn **chỉ số nhỏ nhất trong các gốc đạt min**:

```java
if (chosen == 0 || candidate < best) {
    best = candidate;
    chosen = k;
}
```

Nếu duyệt k tăng và chỉ cập nhật khi chi phí **nhỏ hơn nghiêm ngặt**, gốc có chỉ số nhỏ nhất được giữ khi hòa. Với OBST chuẩn, quy tắc này tương thích tính đơn điệu của gốc và thuận lợi cho việc so sánh kết quả bản O(n³) và bản Knuth.

**Lưu ý:** Nếu cố ý thay chính sách hòa ở mỗi trạng thái mà không kiểm tra tính đơn điệu cho các đại diện được chọn, chỉ việc biết “có một gốc tối ưu nào đó trong khoảng” chưa đủ để khẳng định cách lưu opt đang dùng thỏa định lý cho mọi trạng thái. Một cách đơn giản là giữ chính sách chọn gốc trái nhất nhất quán.

## 4. Hai điều kiện đủ quan trọng trên trọng số đoạn

Với một lớp DP đoạn chuẩn có phí `W(i,j)` và trường hợp cơ sở thích hợp, định lý Knuth có thể suy ra tính đơn điệu của vị trí tối ưu từ hai tính chất nổi bật của chi phí đoạn.

### 4.1. Tính đơn điệu theo phép bao hàm đoạn

Nếu đoạn [b,c] nằm bên trong [a,d], với `a ≤ b ≤ c ≤ d`, yêu cầu:

```text
W(b,c) <= W(a,d)
```

Nói cách khác, khi mở rộng đoạn và chỉ thêm những phần tử/truy vấn có trọng số **không âm**, tổng trọng số không thể giảm.

Ví dụ W là **tổng trọng số không âm** của các phần tử/truy vấn thuộc đoạn. Khi thêm phần tử, W tăng hoặc giữ nguyên, nên điều kiện đúng.

Ngược lại, với W là hàm thưởng/phạt bất kỳ theo chiều dài đoạn, W của đoạn lớn **có thể nhỏ hơn** W của đoạn con. Khi đó không được mặc định tính đơn điệu.

### 4.2. Bất đẳng thức tứ giác (quadrangle inequality, QI)

Với mọi bộ chỉ số thỏa `a ≤ b ≤ c ≤ d` trong miền hợp lệ:

```text
W(a,c) + W(b,d) <= W(a,d) + W(b,c)
```

Đây là bất đẳng thức kiểu **Monge** cho hàm phí trên đoạn. Nó kiểm soát cách chi phí thay đổi khi dịch hoặc mở rộng hai biên.

Đừng nhầm nó với bất đẳng thức tam giác của khoảng cách hình học; đây là **bốn đoạn có biên xen nhau**, không nói rằng khoảng cách ngắn nhất giữa hai điểm ≤ tổng đường đi.

Đối với W là **tổng các trọng số trên một đoạn**, cả hai vế thường bằng nhau, vì phần thuộc vùng giao bị đếm hai lần ở hai vế và phần ngoài vùng giao bị đếm một lần. Đó là trường hợp rất thuận lợi để áp dụng định lý.

### 4.3. Cần đúng cả **dạng DP** lẫn **giả thiết của định lý**

Checklist trước khi áp dụng Knuth:

- **Dạng chuyển:** Chọn gốc k, chia thành hai đoạn con và cộng phí đoạn W(i,j) **không phụ thuộc gốc k**.
- **Miền lựa chọn:** Mỗi k cần thử trong một **đoạn liên tục**; công thức và các trường hợp cơ sở khớp mô hình định lý.
- **Phí đoạn:** Chứng minh điều kiện **đơn điệu theo bao hàm** và **QI** trên miền chỉ số.
- **Không âm/miền số:** Nếu W là tổng tần suất/xác suất, các trọng số cơ sở **không âm**, dữ liệu có thứ tự hợp lệ.
- **Quy tắc hòa:** Lưu đại diện gốc đồng tối ưu theo một chính sách nhất quán, ví dụ **chỉ số nhỏ nhất**.
- **Thứ tự tính:** Hai opt làm biên phải được tính trước; thường duyệt độ dài đoạn từ 1 lên n.
- **Tính đầy đủ:** Khi Knuth hợp lệ, khoảng [opt[i][j−1],opt[i+1][j]] phải được lấy **bao gồm hai đầu**, và vẫn nằm trong i..j.
- **Không nhầm kết luận:** Đủ giả thiết để áp dụng một định lý là một chuyện; “mọi bài vi phạm một điều kiện đều chắc chắn không có gốc đơn điệu” lại là kết luận sai.

**Phân biệt “điều kiện bắt buộc để dùng định lý chuẩn” với “điều kiện cần tuyệt đối của mọi dữ liệu”:** Tính đơn điệu W và QI là **điều kiện đủ thường dùng để chứng minh** giới hạn Knuth cho lớp truy hồi chuẩn, **không phải điều kiện logic cần cho từng bộ dữ liệu cụ thể**. Một dữ liệu ngoài lớp này có thể tình cờ vẫn có gốc tối ưu đơn điệu. Nhưng nếu không có chứng minh hoặc bảo đảm cấu trúc, **không được bỏ ứng viên** dựa trên suy đoán.

## 5. Ví dụ chính: cây tìm kiếm nhị phân tối ưu

Có n khóa tăng nghiêm ngặt:

```text
k1 < k2 < ... < kn
```

Gọi:

- `p_i ≥ 0`: trọng số/tần suất tìm **thành công** khóa ki, i=1..n.
- `q_j ≥ 0`: trọng số/tần suất tìm **thất bại** trong khoảng giữa các khóa, j=0..n.

Một BST có n khóa có n+1 vị trí con rỗng, biểu diễn bằng các **lá giả** d0..dn (*dummy leaves*).

Định nghĩa:

```text
e[i][j] = chi phí độ sâu có trọng số nhỏ nhất
          của BST trên các khóa ki..kj và các lá giả tương ứng.

w[i][j] = tổng trọng số của:
          p_i, ..., p_j
          q_(i-1), ..., q_j

root[i][j] = chỉ số gốc của một BST tối ưu trên [i,j]
```

Đoạn rỗng `[i,i−1]` chỉ có dummy d(i−1):

```text
e[i][i-1] = q_(i-1)
w[i][i-1] = q_(i-1)
```

Công thức trọng số:

```text
w[i][j] = w[i][j-1] + p_j + q_j
```

Công thức chọn gốc:

```text
e[i][j] = w[i][j] +
    min_{r=i..j} (
        e[i][r-1] + e[r+1][j]
    )
```

Như vậy OBST **khớp đúng dạng root-inclusive**. Phí thêm w[i][j] phụ thuộc **toàn đoạn**, không trực tiếp phụ thuộc lựa chọn r.

### Vì sao có khoản +w[i][j]?

Khi chọn gốc r, các khóa và dummy của hai cây con bị đẩy sâu hơn **một mức** so với khi chúng đứng riêng trong cây con; gốc mới cũng có độ sâu 1. Tổng tăng chi phí chính là **tổng trọng số của mọi truy vấn thuộc đoạn**, tức w[i][j]. Vì vậy:

```text
chi phí nếu chọn r = e_left + e_right + w_whole
```

**Không cộng thêm p_r lần nữa**: nó đã nằm trong w_whole.

### W của OBST thỏa tính đơn điệu đoạn

Vì mọi p_i, q_j đều **không âm**, nếu mở rộng [b,c] thành [a,d] với a≤b≤c≤d, ta chỉ thêm các trọng số không âm. Do đó:

```text
w[b][c] <= w[a][d]
```

### W của OBST thỏa quadrangle inequality

Với a≤b≤c≤d, do w là tổng các trọng số gắn vào đoạn:

```text
w[a][c] + w[b][d]
= w[a][d] + w[b][c]
```

Vế trái và phải đếm đúng cùng các trọng số, chỉ có vùng giao [b,c] bị tính hai lần. Do đó QI không chỉ đúng mà còn **đúng với dấu bằng** đối với các đoạn tương ứng của OBST.

Từ dạng DP chuẩn, base case có dummy và các giả thiết trên, có thể dùng định lý Knuth để giới hạn vị trí gốc tối ưu.

## 6. Ví dụ ba khóa và tính bảng root

Giả sử:

```text
keys = [10, 20, 30]
p    = [ 3,  3,  1]
q    = [2, 1, 1, 1]
```

Có 3 khóa, 4 khoảng tìm thất bại; tổng trọng số 12. Dùng chỉ số khóa 1..3 cho bảng.

**Cơ sở:**

```text
e[1][0] = w[1][0] = q0 = 2
e[2][1] = w[2][1] = q1 = 1
e[3][2] = w[3][2] = q2 = 1
e[4][3] = w[4][3] = q3 = 1
```

**Các trạng thái sau khi tối ưu:**

| Đoạn [i,j] | w[i][j] | e[i][j] | root[i][j] |
| --- | ---: | ---: | ---: |
| [1,1] | 6 | 9 | 1 |
| [2,2] | 5 | 7 | 2 |
| [3,3] | 3 | 5 | 3 |
| [1,2] | 10 | 19 | 1 |
| [2,3] | 7 | 13 | 2 |
| [1,3] | 12 | **26** | **2** |

Với đoạn [1,3], phiên bản O(n³) thử mọi r=1,2,3:

```text
r=1: e[1][0] + e[2][3] + w[1][3]
   = 2 + 13 + 12 = 27

r=2: e[1][1] + e[3][3] + w[1][3]
   = 9 + 5 + 12 = 26   <-- tối ưu

r=3: e[1][2] + e[4][3] + w[1][3]
   = 19 + 1 + 12 = 32
```

Tối ưu Knuth dùng:

```text
left  = root[1][2] = 1
right = root[2][3] = 2

Chỉ thử r=1 và r=2,
bỏ r=3 nhưng vẫn không bỏ mất nghiệm tối ưu r=2.
```

Cây tối ưu:

```text
       20
      /  \
    10    30
   / \    / \
  d0 d1  d2 d3

Dạng tiền tự: (20 (10 d0 d1) (30 d2 d3))
```

Chi phí độ sâu có trọng số = **26**. Nếu chỉ đếm số so sánh với **khóa thật**, không tính một bước đến dummy cuối mỗi truy vấn thất bại, tổng so sánh có trọng số bằng:

```text
26 - (2+1+1+1) = 21
```

Vì tổng trọng số = 12, kỳ vọng số so sánh với khóa thật là 21/12 = 1,75.

**Lưu ý về số ứng viên:** Với n=3, DP toàn bộ thử 1+1+1+2+2+3 = **10** gốc. Knuth thử **9** gốc trên dữ liệu này, không phải chỉ thử một gốc cho mọi đoạn. Lợi thế tiệm cận xuất hiện rõ khi n lớn.

## 7. Khi Knuth không áp dụng: phản ví dụ có trọng số đoạn không âm

Không được suy luận rằng **chỉ cần mọi W(i,j)≥0** là đủ cho Knuth. Ta có thể dựng một DP có **cùng dạng chọn gốc** và chi phí W **không âm**, nhưng W **không thỏa điều kiện đơn điệu/QI**, khiến giới hạn tìm kiếm loại mất đáp án.

Cho n=3, base đoạn rỗng = 0, và W tùy ý:

| Đoạn | W |
| --- | ---: |
| [1,1] | 0 |
| [2,2] | 1 |
| [3,3] | 2 |
| [1,2] | 2 |
| [2,3] | 0 |
| [1,3] | 0 |

Công thức vẫn là:

```text
dp[i][j] = W(i,j)
         + min_{r=i..j} (
               dp[i][r-1] + dp[r+1][j]
           )

dp[i][i-1] = 0
```

**Tính thật mọi ứng viên:**

```text
Đoạn [1,2]:
  r=1: dp[2,2] + W[1,2] = 1+2=3
  r=2: dp[1,1] + W[1,2] = 0+2=2
  opt[1,2]=2, dp[1,2]=2.

Đoạn [2,3]:
  r=2: dp[3,3] + W[2,3] = 2+0=2
  r=3: dp[2,2] + W[2,3] = 1+0=1
  opt[2,3]=3, dp[2,3]=1.

Đoạn [1,3]:
  r=1: dp[2,3] + W[1,3] = 1+0=1  <-- tối ưu duy nhất
  r=2: dp[1,1]+dp[3,3]+W = 0+2=2
  r=3: dp[1,2] + W = 2+0=2
  opt[1,3]=1, dp[1,3]=1.
```

Nếu áp dụng Knuth **bất hợp lệ**:

```text
left  = opt[1,2] = 2
right = opt[2,3] = 3

Chỉ thử r=2,3:
  trả dp[1,3] = 2    <-- SAI
Trong khi tối ưu thật là 1 khi r=1.
```

Tính đơn điệu gốc bị phá:

```text
opt[1,2] <= opt[1,3]  ?
   2     <=    1       SAI.
```

Bất đẳng thức tứ giác cũng sai ở a=1,b=2,c=2,d=3:

```text
W(1,2)+W(2,3) = 2+0 = 2
W(1,3)+W(2,2) = 0+1 = 1

2 <= 1 ? SAI.
```

Tính bao hàm cũng sai, chẳng hạn W(2,3)=0 < W(3,3)=2 dù [3,3] nằm trong [2,3].

Đây là **phản ví dụ toán học trực tiếp**, không phụ thuộc lỗi code. Nó chứng minh việc thiếu giả thiết có thể gây **sai kết quả**, không chỉ chậm hơn. Tuy nhiên, một bộ dữ liệu không thỏa QI **không nhất thiết** đều tạo sai khi thử giới hạn Knuth; bài học là **không có bảo đảm**, chứ không phải “mọi trường hợp vi phạm luôn thất bại”.

## 8. Chứng minh tại sao chỉ còn O(n²) ứng viên

Độ khó của Knuth không chỉ nằm ở việc khoảng [L,R] “có vẻ ngắn”. Trong trường hợp xấu, một khoảng cụ thể vẫn có thể dài O(n). Để khẳng định **tổng thời gian O(n²)**, phải tính tổng độ rộng các khoảng trên mỗi lớp độ dài.

Gọi đoạn [i,j] dài ℓ≥2, trong đó `j=i+ℓ−1`.

Số ứng viên được xét ở đoạn:

```text
count(i,j)
  = opt[i+1][j] - opt[i][j-1] + 1
```

Tổng khi i chạy từ 1 đến n−ℓ+1:

```text
Sum_count(ℓ)
  = sum_{i=1..n-ℓ+1}
       (opt[i+1][i+ℓ-1]
        - opt[i][i+ℓ-2]
        + 1)

  = opt[n-ℓ+2][n]
    - opt[1][ℓ-1]
    + (n-ℓ+1)
```

Các hạng trung gian **triệt tiêu nhau (telescoping)** sau khi đổi chỉ số ở tổng thứ nhất. Vì mọi opt là chỉ số gốc nằm trong 1..n, hiệu hai opt ở biên có độ lớn tối đa O(n). Do đó:

```text
Sum_count(ℓ) = O(n)
```

Có O(n) lớp độ dài, nên tổng ứng viên:

```text
O(n) lớp × O(n) ứng viên/lớp = O(n²)
```

Cộng chi phí O(1) để tính trọng số đoạn W và lưu e/root ở mỗi trạng thái, ta được:

- **Thời gian:** O(n²).
- **Bộ nhớ:** O(n²) cho dp, W, opt.
- **Số trạng thái:** vẫn Θ(n²), không giảm.

**Điểm cần nhớ:** Không được lý giải “Knuth O(n²) vì mỗi trạng thái chỉ xét O(1) gốc”; mệnh đề đó **không đúng trong từng trạng thái**. Chính **tổng số ứng viên trên mỗi lớp** mới được chặn O(n).

## 9. Phác thảo lý do định lý đơn điệu gốc đúng

Có hai tầng chứng minh riêng biệt:

### 9.1. Từ giả thiết về W đến cấu trúc chi phí tốt

Tính đơn điệu theo bao hàm đảm bảo mở rộng đoạn không làm phí W giảm bất thường. Bất đẳng thức tứ giác kiểm soát cách tổng chi phí thay đổi khi hai biên dịch chuyển.

Với dạng truy hồi chuẩn, các tính chất đó lan truyền qua phép cộng và phép lấy min ở những đoạn con theo một **định lý chuyên biệt** cho DP đoạn có cấu trúc Knuth. Sự lan truyền không hiển nhiên chỉ từ việc “cây con tối ưu”; nó cần **lập luận so sánh bốn đoạn và hoán đổi các vị trí gốc**. Kết quả là có thể chọn các đại diện gốc tối ưu **không nghịch chiều** khi mở rộng đoạn theo một trong hai phía.

### 9.2. Dùng tính đơn điệu để giới hạn gốc

Khi đã có định lý:

```text
opt[i][j-1] <= opt[i][j] <= opt[i+1][j]
```

ta biết chắc có **một gốc tối ưu thuộc khoảng đóng** giữa hai opt ngắn hơn. Do đó không cần thử những gốc ngoài khoảng. Khi duyệt mọi gốc trong khoảng và lấy min, ta vẫn tính đúng dp[i][j], rồi lưu opt[i][j] phù hợp.

Chứng minh tính đúng của bản Knuth được chia thành:

1. **Định lý giới hạn:** Tồn tại đại diện gốc tối ưu trong khoảng.
2. **Quy nạp theo độ dài:** Hai bảng con và hai mốc opt đã đúng; ta thử mọi gốc trong khoảng chứa nghiệm tối ưu, vì vậy thu được cùng giá trị min như thử toàn đoạn.
3. **Kết thúc:** Mọi đoạn con trong chuyển ngắn hơn; tất cả đã được tính trước trong thứ tự độ dài tăng.

Đây là **phác thảo áp dụng định lý**, không thay cho một chứng minh hình thức đầy đủ của định lý Monge/Knuth trên mọi lớp DP. Trong lập trình thi đấu và kỹ thuật, dùng đúng định lý đã được xác lập cho dạng truy hồi phù hợp là hợp lệ; không nên gán sai tên “chứng minh” cho việc chỉ chạy vài test thấy gốc đơn điệu.

## 10. Quy trình áp dụng Knuth có kiểm chứng

### Bước 1: Viết định nghĩa trạng thái có ý nghĩa

Chẳng hạn: `e[i][j]` là **chi phí độ sâu có trọng số tối thiểu** trên đoạn khóa [i,j], gồm cả truy vấn thất bại q. Không chọn kiểu “dp[i][j] là đáp án” mơ hồ; nếu không rõ ý nghĩa sẽ khó xác định phí W đúng.

### Bước 2: Viết công thức chuyển và base case

Cho biết chính xác:

- Vị trí k có thuộc [i,j] hay không.
- Hai phần con [i,k−1] và [k+1,j] hay [i,k] và [k+1,j].
- Chi phí W(i,j) có độc lập k không.
- Đoạn rỗng được phép không và có chi phí bao nhiêu.

Sai một chỉ số có thể khiến tối ưu hóa nhị phân dùng một khoảng hoàn toàn sai.

### Bước 3: Kiểm tra điều kiện toán học

Chứng minh W đơn điệu theo bao hàm và thỏa QI. Đối với OBST, chỉ cần lập luận W là tổng trọng số không âm của các khóa và khoảng thất bại; QI trở thành đẳng thức trên đoạn giao nhau.

Nếu W có trọng số âm, phụ thuộc k, phụ thuộc chiều cao, hoặc thay đổi theo gốc con, phải **xét lại từ đầu**. Không lấy mô tả “interval DP” làm chứng minh.

### Bước 4: Cài đặt bản O(n³) đúng trước

Dùng thử tất cả k=i..j; đối chiếu một vài ví dụ tính tay, trường hợp rỗng, n=1, cùng trọng số, nhiều gốc hòa. Bản cơ bản làm **oracle** kiểm thử trên dữ liệu nhỏ.

### Bước 5: Thêm bảng opt và giới hạn vòng gốc

Với đoạn một phần tử, gán opt[i][i]=i. Với độ dài ≥2:

```text
for k = opt[i][j-1] .. opt[i+1][j]:
    candidate = dp[i][k-1]
              + dp[k+1][j]
              + W(i,j)
    cập nhật min và opt[i][j]
```

Luôn giữ biên bao gồm hai đầu và lưu chính sách hòa rõ ràng.

### Bước 6: Kiểm thử phân biệt lỗi và chứng minh

So sánh với bản O(n³) cho nhiều mảng p/q không âm, gồm:

- Mọi trọng số bằng 0 (nhiều nghiệm hòa).
- Tần suất rất lệch.
- Một khóa và không có khóa.
- Có nhiều q_j lớn.
- Tổng p/q lớn nhưng vẫn nằm trong kiểu số.
- Dữ liệu ngẫu nhiên nhỏ.

Các phép thử giúp **phát hiện lỗi chỉ số/tie-break**, nhưng **không phải bằng chứng đủ để bỏ qua định lý**. Một phản ví dụ cho dạng W tùy ý như phần 7 cho thấy bản tối ưu có thể sai ngay cả khi công thức DP nhìn giống nhau.

## 11. Java 17+: hai bản cài đặt và đối chiếu chính xác

Chương trình có hai phương thức:

- `solveCubic` thử **mọi gốc** r=i..j.
- `solveKnuth` thử gốc trong **[root[i][j−1],root[i+1][j]]** khi đoạn dài ≥2.

Cả hai dùng **cùng định nghĩa e/w/root**, cùng chi phí đoạn, cùng quy tắc hòa lấy gốc trái nhất. Mỗi kết quả chứa tổng độ sâu có trọng số, tổng so sánh khóa thật có trọng số, tần suất tổng, khóa gốc, biểu diễn cấu trúc cây và **số ứng viên gốc đã thử**. Hàm hiển thị đối chiếu chi phí và hình cây của hai thuật toán trước khi in.

Dữ liệu đầu vào:

- `keys` là `int[]` tăng nghiêm ngặt, **không trùng**.
- `hits` là `long[]` chứa n trọng số không âm cho tìm thành công.
- `misses` là `long[]` chứa n+1 trọng số không âm cho khoảng thất bại.
- Mảng được đọc **không sửa**; tần suất không cần tổng bằng 1 vì có thể là số đếm.

**Lưu tệp `KnuthOptimizationDemo.java`:**

```java
import java.util.Objects;

public class KnuthOptimizationDemo {
    record Result(long depthCost,
                  long comparisonWeight,
                  long totalWeight,
                  String rootKey,
                  String tree,
                  long candidates) {}

    static Result solveCubic(
            int[] keys, long[] hits, long[] misses) {
        return solve(keys, hits, misses, false);
    }

    static Result solveKnuth(
            int[] keys, long[] hits, long[] misses) {
        return solve(keys, hits, misses, true);
    }

    private static Result solve(
            int[] keys, long[] hits, long[] misses,
            boolean optimized) {
        Objects.requireNonNull(keys, "keys must not be null");
        Objects.requireNonNull(hits, "hits must not be null");
        Objects.requireNonNull(misses, "misses must not be null");

        int n = keys.length;
        if (hits.length != n || misses.length != n + 1) {
            throw new IllegalArgumentException(
                    "hits must have n entries; misses n+1");
        }
        for (int i = 1; i < n; i++) {
            if (keys[i - 1] >= keys[i]) {
                throw new IllegalArgumentException(
                        "keys must be strictly increasing");
            }
        }

        long total = 0;
        long missTotal = 0;
        for (long weight : hits) {
            if (weight < 0) {
                throw new IllegalArgumentException(
                        "weights must be nonnegative");
            }
            total = Math.addExact(total, weight);
        }
        for (long weight : misses) {
            if (weight < 0) {
                throw new IllegalArgumentException(
                        "weights must be nonnegative");
            }
            total = Math.addExact(total, weight);
            missTotal = Math.addExact(missTotal, weight);
        }

        long[][] e = new long[n + 2][n + 1];
        long[][] w = new long[n + 2][n + 1];
        int[][] root = new int[n + 2][n + 1];

        // Doan rong [i, i-1] chi co dummy d(i-1).
        for (int i = 1; i <= n + 1; i++) {
            e[i][i - 1] = misses[i - 1];
            w[i][i - 1] = misses[i - 1];
        }

        long candidates = 0;

        for (int length = 1; length <= n; length++) {
            for (int i = 1; i <= n - length + 1; i++) {
                int j = i + length - 1;
                w[i][j] = Math.addExact(
                        Math.addExact(w[i][j - 1], hits[j - 1]),
                        misses[j]);

                int from = i;
                int to = j;
                if (optimized && length >= 2) {
                    from = root[i][j - 1];
                    to = root[i + 1][j];
                }

                long best = Long.MAX_VALUE;
                int selected = 0; // 0: chua chon root

                for (int r = from; r <= to; r++) {
                    candidates++;
                    long cost = Math.addExact(
                            Math.addExact(e[i][r - 1],
                                          e[r + 1][j]),
                            w[i][j]);

                    // Duyet r tang; khi hoa giu root ben trai.
                    if (selected == 0 || cost < best) {
                        best = cost;
                        selected = r;
                    }
                }

                if (selected == 0) {
                    throw new AssertionError(
                            "empty candidate interval");
                }
                e[i][j] = best;
                root[i][j] = selected;
            }
        }

        long depthCost = e[1][n]; // n=0: q0
        long comparisons = Math.subtractExact(
                depthCost, missTotal);
        String rootKey = n == 0
                ? "none"
                : Integer.toString(keys[root[1][n] - 1]);
        String tree = buildTree(keys, root, 1, n);

        return new Result(depthCost, comparisons,
                          total, rootKey, tree, candidates);
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

    static void show(String title,
                     int[] keys, long[] hits, long[] misses) {
        Result cubic = solveCubic(keys, hits, misses);
        Result knuth = solveKnuth(keys, hits, misses);

        if (cubic.depthCost() != knuth.depthCost()
                || cubic.comparisonWeight()
                        != knuth.comparisonWeight()
                || cubic.totalWeight() != knuth.totalWeight()
                || !cubic.tree().equals(knuth.tree())) {
            throw new AssertionError(
                    "cubic/Knuth mismatch");
        }

        String average = knuth.totalWeight() == 0
                ? "undefined"
                : knuth.comparisonWeight()
                        + "/" + knuth.totalWeight();

        System.out.println(title
                + ": cost=" + knuth.depthCost()
                + ", comparisons=" + average
                + ", root=" + knuth.rootKey()
                + ", candidates=" + cubic.candidates()
                + "->" + knuth.candidates());
        System.out.println("  tree=" + knuth.tree());
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

        show("All zero",
                new int[]{10, 20, 30},
                new long[]{0, 0, 0},
                new long[]{0, 0, 0, 0});

        show("Equal hits",
                new int[]{10, 20, 30, 40},
                new long[]{1, 1, 1, 1},
                new long[]{0, 0, 0, 0, 0});

        show("Large gaps",
                new int[]{10, 20, 30},
                new long[]{1, 2, 1},
                new long[]{9, 3, 5, 9});

        try {
            solveKnuth(new int[]{20, 10},
                    new long[]{1, 1},
                    new long[]{0, 0, 0});
        } catch (IllegalArgumentException ex) {
            System.out.println("Bad keys: " + ex.getMessage());
        }

        try {
            solveKnuth(new int[]{10},
                    new long[]{-1},
                    new long[]{0, 0});
        } catch (IllegalArgumentException ex) {
            System.out.println("Bad weights: " + ex.getMessage());
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac KnuthOptimizationDemo.java
java KnuthOptimizationDemo
```

**Stdout chính xác:**

```text
Sample: cost=26, comparisons=21/12, root=20, candidates=10->9
  tree=(20 (10 d0 d1) (30 d2 d3))
Classic: cost=290, comparisons=245/105, root=40, candidates=35->28
  tree=(40 (20 (10 d0 d1) (30 d2 d3)) (50 d4 d5))
Greedy trap: cost=12, comparisons=12/7, root=20, candidates=10->10
  tree=(20 (10 d0 d1) (30 d2 d3))
Single: cost=11, comparisons=8/8, root=10, candidates=1->1
  tree=(10 d0 d1)
Empty: cost=9, comparisons=0/9, root=none, candidates=0->0
  tree=d0
All zero: cost=0, comparisons=undefined, root=10, candidates=10->9
  tree=(10 d0 (20 d1 (30 d2 d3)))
Equal hits: cost=8, comparisons=8/4, root=20, candidates=20->16
  tree=(20 (10 d0 d1) (30 d2 (40 d3 d4)))
Large gaps: cost=84, comparisons=58/30, root=20, candidates=10->10
  tree=(20 (10 d0 d1) (30 d2 d3))
Bad keys: keys must be strictly increasing
Bad weights: weights must be nonnegative
```

### Đọc và kiểm tra output

- **Sample:** Hai bản cho cùng chi phí 26 và cây gốc 20; số lần xét ứng viên giảm 10→9.
- **Classic:** Năm khóa, chi phí chuẩn 290, gốc tối ưu khóa 40; số ứng viên giảm từ 35 xuống 28. Đây là ví dụ có cả tìm thành công lẫn thất bại.
- **Greedy trap:** Khóa 30 có trọng số thành công 3 lớn nhất nhưng gốc 20 với tổng chi phí 12 tốt hơn gốc 30. Knuth vẫn xét 10 ứng viên; **Knuth không cam kết ít ứng viên hơn trên mọi input nhỏ**.
- **Single:** Một gốc duy nhất và hai lá giả. Cả hai bản thử đúng một ứng viên.
- **Empty:** Không có khóa, chỉ có lá giả d0. DP có chi phí độ sâu q0=9 nhưng số so sánh với khóa thật là 0. Không có ứng viên gốc nào.
- **All zero:** Có rất nhiều nghiệm hòa và tổng trọng số truy vấn bằng 0. Quy tắc chọn gốc trái nhất cho kết quả xác định; trung bình số so sánh **không xác định**, vì không thể chia cho 0.
- **Equal hits:** Kiểm tra kết quả có nhiều gốc đối xứng/hòa, và việc chọn gốc nhất quán.
- **Large gaps:** Trọng số thất bại lớn cũng tác động đến tổng chi phí; không chỉ p_i mới quan trọng.

### Mã này tối ưu phần nào?

Trong `solve`, khác biệt duy nhất về tập gốc:

```java
int from = i;
int to = j;
if (optimized && length >= 2) {
    from = root[i][j - 1];
    to = root[i + 1][j];
}
```

Phần còn lại giống nhau: hai bảng DP có cùng base, cùng W và cùng công thức cộng chi phí; chỉ **thu hẹp khoảng r** khi giả thiết Knuth đã được bảo đảm bởi mô hình OBST và trọng số không âm.

Bởi vậy khi so sánh, nếu hai bản cho kết quả khác nhau thì đó là **tín hiệu lỗi cài đặt hoặc vi phạm giả thiết**, không phải hai mục tiêu tối ưu khác nhau. Đoạn kiểm tra ở `show` so cả giá trị chi phí và cấu trúc cây với chính sách hòa cố định.

**Lưu ý đo tốc độ:** Số ứng viên là chỉ số dễ phân tích và có tính tái lập hơn thời gian thực thi từng lần trong demo. Trên đầu vào nhỏ, overhead Java có thể che mất lợi thế. Ở n lớn, khác biệt O(n³) và O(n²) mới là yếu tố quan trọng. Đừng lấy một phép đo đơn lẻ trên n=3 để kết luận Knuth “nhanh gấp bao nhiêu lần”.

## 12. Vì sao mã xử lý cả tìm kiếm thất bại?

OBST chuẩn thường cung cấp tần suất tìm thành công p_i và tìm thất bại q_j. Một truy vấn thất bại sau khi đi qua các khóa thật đến liên kết null; mô hình DP tính độ sâu dummy ở mức sau nút thật cuối.

Do đó:

```text
weightedDepthCost  = sum(p_i * depth(key_i))
                   + sum(q_j * depth(dummy_j))

comparisonWeight   = weightedDepthCost - sum(q_j)
```

Khi tổng tần suất T>0, kỳ vọng số so sánh với **khóa thật** = `comparisonWeight/T`. Chênh lệch `sum q_j` là hằng số không phụ thuộc hình dạng cây, nên **tối ưu cả hai đại lượng cho cùng cấu trúc**. Nhưng nếu in số, phải ghi rõ đang đếm **độ sâu gồm dummy** hay **so sánh khóa thật**.

Đối với bài **chỉ tìm thành công**, đặt tất cả q_j=0. Khi đó base đoạn rỗng bằng 0 và công thức vẫn hoạt động:

```text
dp[i][j] =
    sum(p_i..p_j)
    + min_r(dp[i][r-1] + dp[r+1][j])
```

Nếu các khóa có trọng số âm do muốn “thưởng” cho truy vấn, đó không còn là tần suất/xác suất hợp lệ và không được áp dụng lập luận **trọng số không âm** của OBST.

## 13. Knuth khác các tối ưu DP phổ biến nào?

| Kỹ thuật | Dạng phụ thuộc điển hình | Điều kiện cần chứng minh | Kết quả thường gặp |
| --- | --- | --- | --- |
| **Knuth optimization** | DP đoạn chọn gốc, hai đoạn con + phí đoạn W | Đơn điệu vị trí tối ưu; thường suy ra từ W đơn điệu bao hàm + QI | O(n³) → O(n²) |
| **Divide and conquer DP optimization** | DP theo lớp `dp[t][j]=min_{k≤j}(dp[t−1][k]+C(k,j))` | Chỉ số quyết định tối ưu đơn điệu theo j, theo dạng bài | Giảm số ứng viên trên các lớp |
| **Convex hull trick / Li Chao tree** | Min/max của các hàm tuyến tính theo tham số truy vấn | Dạng tuyến tính/điều kiện truy vấn và cấu trúc thích hợp | Đánh giá min/max nhanh hơn |
| **Monotone queue optimization** | Chuyển trạng thái lấy min/max trên cửa sổ trượt | Cửa sổ có thứ tự di chuyển, tiêu chí deque phù hợp | O(n) trên nhiều bài cửa sổ |

Không được nhầm **Knuth** với mọi trường hợp “opt đơn điệu”: định lý và khoảng ứng viên của từng kỹ thuật khác nhau. Ví dụ, dạng `dp[t][j]` theo số nhóm/tầng có thể phù hợp **divide-and-conquer optimization** chứ không dùng nguyên khoảng root[i][j−1]..root[i+1][j].

Mặt khác, một bài DP có **quadrangle inequality** cho C(k,j) chưa chắc tự động rơi vào công thức **root-inclusive** của Knuth. Phải đối chiếu miền k, số chiều/trạng thái, base case và kết quả định lý cụ thể.

## 14. Những dấu hiệu cho thấy KHÔNG được dùng Knuth ngay

### Chi phí phụ thuộc gốc

Ví dụ:

```text
dp[i][j] = min_k(
    dp[i][k-1] + dp[k+1][j] + penalty(i,j,k)
)
```

Nếu không tách được `penalty(i,j,k)` thành một W(i,j) **độc lập k** và các phần hợp lệ cho hai đoạn con, dạng chuẩn không áp dụng. Một thuật toán khác có thể tồn tại, nhưng không được tự kết luận root monotonic.

### Trọng số đoạn tùy ý, không thỏa QI

Phản ví dụ phần 7 dùng các W không âm nhưng khiến opt[1,3] nằm **ngoài** khoảng do Knuth dự đoán. Việc dùng cùng công thức `e_left+e_right+W` **không tự bảo vệ** thuật toán.

### Ràng buộc không được mã hóa vào đoạn

Nếu một đoạn [i,j] còn phụ thuộc vào **số nút đã dùng, chiều cao còn lại, số nhóm, trạng thái màu, tài nguyên còn lại**, thì `dp[i][j]` có thể **chưa đủ thông tin tương lai**. Trước khi tối ưu vòng gốc, phải xây **trạng thái đúng**. Knuth không sửa được công thức DP đã bỏ ràng buộc.

### Công thức có dấu max thay vì min

Những định lý về vị trí **argmin** dưới QI không tự suy sang **argmax**. Muốn dùng cho bài cực đại phải xem phép đổi dấu/chuyển đổi chi phí có giữ đúng các điều kiện hay không. Không thay “min” bằng “max” và giữ nguyên khoảng giới hạn mà không chứng minh.

### Dùng trung vị, chia đều hoặc greedily chọn trọng số lớn nhất

Các mẹo này chỉ xét một vài gốc theo trực giác, không liên quan trực tiếp tới định lý Knuth. Knuth có thể chọn gốc lệch hẳn trung vị, miễn gốc thuộc khoảng đã **được bảo đảm** bởi hai đoạn con.

### Dữ liệu không có thứ tự cố định

OBST có các khóa đã sắp; chính thứ tự ấy xác định tập khóa bên trái/phải khi chọn gốc. Nếu có thể hoán vị tùy ý các phần tử ở mỗi trạng thái, các đoạn [i,j] không còn đại diện đúng các bài toán con như công thức ban đầu.

## 15. Các sai lầm phổ biến

1. **Thấy O(n³) là áp dụng Knuth.** Ba vòng lặp chưa đủ; phải có đúng dạng truy hồi và điều kiện toán học.
2. **Cho rằng phí W không âm là đủ.** Phản ví dụ W không âm nhưng không đơn điệu/QI làm kết quả sai.
3. **Không chứng minh QI.** Nhiều phí đoạn tùy ý vi phạm bất đẳng thức tứ giác.
4. **Không chứng minh đơn điệu bao hàm.** Trọng số âm hoặc phí khuyến khích đoạn dài có thể phá điều kiện.
5. **Nhầm điều kiện đủ với điều kiện cần tuyệt đối.** Có dữ liệu tình cờ vẫn monotonic dù không thỏa giả thiết; không có chứng minh thì không an toàn để tối ưu.
6. **Sai dạng chỉ số.** Công thức chọn gốc r∈[i,j] khác công thức tách [i,k] và [k+1,j].
7. **Đưa phí phụ thuộc r vào W(i,j) giả.** Không được giấu chi phí gốc trong một biểu thức được coi là độc lập r.
8. **Truy cập root của đoạn rỗng.** Với độ dài 1, root[i][i]=i; công thức giới hạn cần hai đoạn ngắn hơn **không rỗng**.
9. **Tính đoạn dài trước đoạn ngắn.** opt[i][j−1] và opt[i+1][j] phải sẵn sàng, cũng như chi phí của các cây con khi thử r.
10. **Bỏ đầu phải khi duyệt.** Khoảng k từ left đến right là **đóng**.
11. **Dùng `opt[i−1][j]` thay vì `opt[i+1][j]`.** Đó là đoạn **lớn hơn hoặc khác loại**, không phải giới hạn chuẩn.
12. **Chỉ lưu cost mà không lưu opt.** Không có bảng gốc của các đoạn ngắn thì không biết biên để giới hạn k.
13. **Cập nhật gốc khi hòa một cách không nhất quán.** Quy ước trái nhất hoặc phải nhất cần được giữ thống nhất và phù hợp định lý đã dùng.
14. **Cho rằng mỗi trạng thái chỉ thử O(1) gốc.** Lập luận thời gian phải dựa vào **telescoping tổng số ứng viên trên mỗi lớp**.
15. **Gọi thời gian O(n²) khi code vẫn thử i..j.** Chỉ giới hạn vòng k bằng opt đã chứng minh mới có cải tiến.
16. **Sai base case dummy trong OBST.** e[i][i−1]=q_(i−1), không phải 0 nếu có tìm thất bại.
17. **Sai chỉ số p/q trong w.** Với khóa 1-based, w[i][j]=w[i][j−1]+p_j+q_j.
18. **Quên n+1 khoảng tìm thất bại.** Có n khóa thật thì có n+1 dummy.
19. **Cộng p_root hai lần.** Phí W cả đoạn đã bao gồm trọng số của khóa gốc.
20. **Nhầm chi phí dummy depth với số so sánh khóa thật.** E_compare=E_depth−sum q, không thể gắn nhãn mọi số là “comparisons” như nhau.
21. **Dùng số thực rồi so bằng nhau tuyệt đối không cân nhắc sai số.** Nếu làm việc với xác suất double, thứ tự min gần nhau có thể bị ảnh hưởng bởi làm tròn; cân nhắc thứ tự tính và độ ổn định số.
22. **So sánh khóa bằng phép trừ int.** Khi khóa cực trị có thể tràn; dùng dấu `<`, `>=` trực tiếp.
23. **Không kiểm tra trọng số âm.** Với tần suất/xác suất OBST, âm là không hợp lệ.
24. **Dùng `Long.MAX_VALUE` làm min chưa chọn mà không có cờ.** Nếu cost ứng viên bằng đúng Long.MAX_VALUE, phép kiểm tra `cost<best` không chọn được gốc; dùng cờ selected==0 như mã mẫu.
25. **Bỏ qua tràn số khi cộng chi phí.** Math.addExact có thể báo tràn; không được âm thầm đảo thứ tự min do tràn long.
26. **Không kiểm tra zero-total.** Kỳ vọng so sánh không xác định khi tổng tần suất 0, dù cây vẫn hợp lệ.
27. **Mặc định nghiệm duy nhất.** Nhiều gốc hòa chi phí; cần quy ước nếu muốn tái lập đúng cây.
28. **Không đối chiếu bản thường.** Dễ sai ở biên i,j hoặc trường hợp hòa; bản O(n³) là chuẩn kiểm thử hữu ích cho n nhỏ.
29. **Dùng Knuth trên DP có trạng thái thiếu biến.** Tối ưu vòng lặp không thể biến công thức sai thành đúng.
30. **Quên chi phí bộ nhớ.** Giảm thời gian xuống O(n²) nhưng ba bảng e, w, root vẫn dùng O(n²) không gian.

## 16. Bài tập tự luyện có đáp án

**Bài 1.** Cho công thức `dp[i][j]=W(i,j)+min_{k=i..j}(dp[i][k−1]+dp[k+1][j])`. Viết khoảng ứng viên của Knuth cho đoạn dài ít nhất 2.

**Đáp án:** Nếu các giả thiết định lý đúng và lưu opt nhất quán: thử mọi `k∈[opt[i][j−1],opt[i+1][j]]`, **bao gồm hai đầu**.

**Bài 2.** Vì sao `opt[i][i]=i`?

**Đáp án:** Đoạn một khóa chỉ có duy nhất một khóa ki để làm gốc. Không có ứng viên khác nên gốc tối ưu chắc chắn là i, không cần áp dụng công thức giới hạn bằng đoạn rỗng.

**Bài 3.** Nếu W(i,j) là tổng trọng số **không âm** của các khóa và khoảng truy vấn trên đoạn, có tính chất gì?

**Đáp án:** W đơn điệu theo bao hàm vì mở rộng đoạn thêm trọng số không âm; với các đoạn giao nhau đúng cấu trúc tổng, W còn thỏa QI với dấu bằng. Vì vậy trong OBST chuẩn có thể áp dụng định lý Knuth.

**Bài 4.** Tính e[1][3] và gốc tối ưu trong ví dụ keys=[10,20,30], p=[3,3,1], q=[2,1,1,1].

**Đáp án:** e[1][3]=**26**, gốc 2 tương ứng khóa **20**. Các ứng viên r=1,2,3 lần lượt cho chi phí 27,26,32.

**Bài 5.** Trong bài 4, root[1][2]=1 và root[2][3]=2. Bản Knuth thử những gốc nào cho [1,3]?

**Đáp án:** Chỉ thử r=1,2. Nhờ định lý đơn điệu, gốc tối ưu r=2 không nằm ngoài khoảng.

**Bài 6.** Có n=5 khóa. Số lần thử gốc của bản duyệt mọi gốc là bao nhiêu?

**Đáp án:** `n(n+1)(n+2)/6=5×6×7/6=35`. Với dữ liệu Classic trong Java, bản Knuth thử 28 ứng viên.

**Bài 7.** Tại sao không được nói Knuth O(n²) vì “mỗi đoạn thử nhiều nhất 2 gốc”?

**Đáp án:** Khoảng [opt[i][j−1],opt[i+1][j]] có thể dài hơn 2 rất nhiều. O(n²) đến từ tổng chiều rộng các khoảng **trên cùng một lớp độ dài** triệt tiêu, chỉ còn O(n).

**Bài 8.** Nêu một phản ví dụ cho việc dùng Knuth với W không âm nhưng tùy ý.

**Đáp án:** Lấy W11=0,W22=1,W33=2,W12=2,W23=0,W13=0 và base rỗng 0. Ta có opt[1,2]=2, opt[2,3]=3 nhưng opt[1,3]=1. Thu hẹp thành [2,3] bỏ r=1 và trả chi phí 2 thay vì tối ưu thật 1.

**Bài 9.** Kiểm tra QI ở a=1,b=2,c=2,d=3 của phản ví dụ bài 8.

**Đáp án:** W12+W23=2, trong khi W13+W22=1. Điều kiện 2≤1 là sai, nên không có bảo đảm từ định lý Knuth.

**Bài 10.** Điều kiện W đơn điệu/QI là điều kiện **cần tuyệt đối** cho mọi bộ dữ liệu có gốc đơn điệu hay là điều kiện **đủ** thường dùng?

**Đáp án:** Là **điều kiện đủ phổ biến** cho dạng truy hồi chuẩn. Nếu điều kiện không thỏa, gốc của một dữ liệu riêng lẻ vẫn có thể tình cờ đơn điệu; nhưng không được áp dụng Knuth cho cả lớp dữ liệu khi không có một chứng minh khác.

**Bài 11.** Nếu tổng trọng số tìm thất bại bằng 5, chi phí depth chuẩn 26 trên tổng trọng số 12, số so sánh khóa thật trung bình bằng bao nhiêu?

**Đáp án:** `(26−5)/12=21/12=1,75`. Khoản trừ 5 điều chỉnh việc tính lá giả chứ không đổi cây tối ưu.

**Bài 12.** Một bài dp chọn k với phí `penalty(i,j,k)`, không tách thành W(i,j). Có được áp dụng ngay công thức Knuth không?

**Đáp án:** Không. Phải chứng minh một dạng định lý khác hoặc chuyển đổi hợp lệ. Chỉ vì công thức có hai cây con không đủ để kết luận opt đơn điệu.

**Bài 13.** Nếu p và q là tần suất không âm nhưng tổng bằng 0, e và average comparisons có giá trị thế nào?

**Đáp án:** Mọi cây có chi phí có trọng số 0; average không xác định do mẫu số 0. Chọn gốc trái nhất khi hòa vẫn tạo một cây BST hợp lệ.

**Bài 14.** Nếu bản O(n³) và bản Knuth cho **cùng chi phí** nhưng hình cây khác nhau, chắc chắn có lỗi không?

**Đáp án:** Không nhất thiết nếu hai bản dùng **quy tắc hòa khác nhau** hoặc có nhiều cây đồng tối ưu. Trong chương trình mẫu, hai bản dùng cùng chính sách chọn gốc trái nhất nên có thể kiểm tra cả hình cây; trong ứng dụng tổng quát, đối chiếu chi phí và tính hợp lệ là tiêu chí cơ bản, còn dạng cây phụ thuộc tie-break.

**Bài 15.** Tại sao cần tính trạng thái theo độ dài từ 1 tới n?

**Đáp án:** Khi tính [i,j], mọi đoạn con trong phép chuyển đều ngắn hơn và hai biên opt[i][j−1], opt[i+1][j] đã được lưu. Không được truy cập dữ liệu chưa tính.

**Bài 16.** Nếu ràng buộc BST là “chiều cao không vượt H”, có thể giữ nguyên e[i][j] và tối ưu Knuth không?

**Đáp án:** Không thể mặc định. Ràng buộc chiều cao có thể khiến chi phí tối ưu của một đoạn phụ thuộc vào **chiều cao còn được phép**; có thể cần trạng thái e[i][j][h] và chứng minh mới. Không áp dụng trực tiếp bảng root của OBST chuẩn.

## Ghi nhớ

**Knuth optimization** không phải “mẹo thay ba vòng lặp bằng hai vòng”. Nó là hệ quả của **tính đơn điệu vị trí lựa chọn tối ưu** trong một lớp **DP đoạn đặc biệt**. Với truy hồi chọn gốc k∈[i,j] và phí đoạn W(i,j) độc lập k, các giả thiết **W đơn điệu theo bao hàm** và **quadrangle inequality** là những điều kiện đủ tiêu biểu để dùng định lý. Khi hợp lệ, ta thử k từ **opt[i][j−1] đến opt[i+1][j]**, thay vì toàn bộ i..j. Chi phí được giảm từ **O(n³) xuống O(n²)** bởi **tổng số ứng viên mỗi lớp O(n)**, không phải vì mọi đoạn chỉ thử một gốc.

**Trước khi áp dụng:** Xác định đúng trạng thái, base case và công thức, chứng minh W đáp ứng điều kiện, thống nhất tie-break, đối chiếu bản O(n³) trên ca nhỏ và kiểm tra phản ví dụ. Đặc biệt, **W không âm một mình chưa đủ**: một W tùy ý có thể khiến tối ưu Knuth trả lời sai. Ở cây tìm kiếm nhị phân tối ưu với p_i,q_j không âm, W là tổng trọng số đoạn và thỏa các giả thiết chuẩn, nên Knuth là một lựa chọn vững chắc.
