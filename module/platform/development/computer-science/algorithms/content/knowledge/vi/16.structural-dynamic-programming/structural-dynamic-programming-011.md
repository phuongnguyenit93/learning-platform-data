# Tách trạng thái cấu trúc khỏi trạng thái tài nguyên

Trong **quy hoạch động trên cấu trúc** (*structural dynamic programming*), một bài toán con thường được xác định bởi hai nhóm thông tin khác nhau:

- **Trạng thái cấu trúc**: ta đang giải bài toán tại **vị trí, đỉnh, cây con, đoạn hoặc phần cấu trúc nào**?
- **Trạng thái tài nguyên**: ta đã dùng hoặc còn **bao nhiêu ngân sách, bước đi, lựa chọn, dung lượng hay quyền thao tác**?

Thay vì gộp hai ý nghĩa vào một biến khó hiểu, ta mô hình hóa rõ ràng một **trạng thái tích**:

\[
dp[\text{structuralState}][\text{resourceState}].
\]

Ví dụ `dp[u][k]` có thể là kết quả tốt nhất **bên trong cây con gốc u** khi chọn **đúng k đỉnh**. Ở một bài khác, `dp[v][t]` có thể là điểm số tốt nhất khi đến **đỉnh v** sau **đúng t cạnh**. Hai chiều này phối hợp khi chuyển trạng thái nhưng phải được định nghĩa độc lập, rõ đơn vị và phạm vi.

**Tách chiều trạng thái không có nghĩa hai chiều không tương tác.** Kết quả tại `dp[u][k]` vẫn phụ thuộc vào cách phân bổ k cho những cây con của u; điểm lợi là ta có thể mô tả và kiểm tra rành mạch **cấu trúc nào đã xử lý**, **tài nguyên đã tiêu hao bao nhiêu**, rồi thiết kế phép gộp đúng.

Bài học trình bày phương pháp phân tách, chứng minh tính đúng, ví dụ **tree knapsack** có ràng buộc chọn tổ tiên, mô hình **đồ thị với giới hạn số bước**, thứ tự phụ thuộc, tối ưu bộ nhớ, phản ví dụ và chương trình **Java 17+** chạy độc lập.

## 1. Vì sao một chỉ số cấu trúc thường chưa đủ?

Xét cây có mỗi đỉnh mang một giá trị. Ta muốn chọn một số đỉnh sao cho tập chọn **liên thông và chứa gốc 0**, đồng thời số đỉnh chọn **không vượt quá B**. Mục tiêu là tối đa tổng giá trị.

Nếu chỉ định nghĩa:

\[
best[u]=\text{tổng giá trị tốt nhất trong cây con gốc u},
\]

ta **chưa nói đã dùng bao nhiêu đỉnh**. Khi ghép các cây con, ta không thể biết chọn cả lời giải tốt nhất ở mỗi bên có vượt ngân sách B hay không. Một lời giải dùng 3 đỉnh và một lời giải dùng 1 đỉnh không thể so sánh và ghép tùy tiện nếu mục tiêu tổng cho phép nhiều nhất 3 đỉnh.

Cần ghi thêm số lượng:

\[
dp[u][k]=\text{giá trị tốt nhất tại cây con u khi dùng đúng k đỉnh}.
\]

Lúc này:

- `u` trả lời **“ở cây con nào?”**.
- `k` trả lời **“đã dùng bao nhiêu đỉnh?”**.
- Giá trị `dp[u][k]` trả lời **“được tổng giá trị tối đa là bao nhiêu?”**.

Phân tách giúp **không trộn một đơn vị tài nguyên với một vị trí cấu trúc**. Nó cũng làm rõ điều kiện chuyển: nếu lời giải tại u đã dùng a đỉnh, còn lời giải được chọn trong cây con v dùng b đỉnh, tổng tài nguyên mới là **a+b**, không phải `a+v` hay một chỉ số tùy ý.

### Một số cặp chiều thường gặp

| Bài toán | Chiều cấu trúc | Chiều tài nguyên | Ý nghĩa trạng thái |
|---|---|---|---|
| Chọn đỉnh trong cây với ngân sách số lượng | Gốc cây con `u` | Số đỉnh đã chọn `k` | Tổng giá trị lớn nhất |
| Đường đi bị giới hạn số cạnh | Đỉnh `v` | Số cạnh đã đi `t` | Điểm số tốt nhất |
| Chọn phần tử của dãy với giới hạn số lần chọn | Chỉ số `i` | Số lựa chọn `k` | Tổng lợi ích/chi phí |
| Bài toán mang năng lượng trên đồ thị | Vị trí `v` | Năng lượng còn lại `e` | Kết quả tối ưu theo ràng buộc |
| DP theo đoạn có giới hạn thao tác | Hai biên `[l,r]` | Số thao tác `k` | Lợi ích tối ưu trên đoạn |
| Ghép nhiều nhánh cây có số nhóm tối đa | Đỉnh/cây con `u` | Số nhóm hoặc số đơn vị ngân sách | Kết quả có thể đạt |

**Không phải cứ thêm một chiều là đúng.** Định nghĩa phải bảo đảm rằng mọi lời giải có cùng cặp trạng thái đều có **cùng thông tin cần cho tương lai**. Nếu việc tiếp tục còn phụ thuộc một yếu tố khác (ví dụ những đỉnh đặc biệt nào đã đi qua), chỉ `(v,t)` có thể chưa đủ. Đó là yêu cầu **tính đầy đủ của trạng thái**.

## 2. Chọn quy ước “dùng đúng” hay “dùng tối đa” trước khi lập công thức

Có hai định nghĩa khác nhau:

\[
exact[u][k]=\text{giá trị tốt nhất dùng \textbf{đúng} k đơn vị tài nguyên},
\]

\[
atMost[u][k]=\text{giá trị tốt nhất dùng \textbf{không quá} k đơn vị}.
\]

Chúng liên hệ qua:

\[
\boxed{atMost[u][k]=\max_{0\le j\le k}exact[u][j]}
\]

nếu mọi trạng thái `exact[u][j]` hợp lệ được xem là ứng viên và cho phép dùng 0 tài nguyên.

**“Đúng k” thường thuận tiện hơn khi ghép tài nguyên**, vì tổng lượng dùng là phép cộng chính xác `a+b=k`. Sau khi đã tính bảng exact, có thể trả truy vấn “không quá k” bằng cách lấy max các giá trị có tài nguyên nhỏ hơn hoặc bằng k.

Cần phân biệt hai điều:

- **Không thể đạt** đúng k đơn vị: đó là trạng thái **không hợp lệ**, không phải điểm 0.
- **Đạt được và có điểm 0**: đó là một lời giải hợp lệ, khác với không thể đạt.

Nếu cho phép giá trị âm, nhầm “không thể đạt” với 0 sẽ cực kỳ nguy hiểm. Ví dụ chỉ có một đỉnh gốc giá trị **-5**:

- Chọn **đúng 1** đỉnh: đáp án **-5**.
- Chọn **không quá 1** đỉnh và cho phép chọn rỗng: đáp án **0**.

Nếu điền 0 vào mọi ô DP chưa xét, thuật toán có thể bỏ qua một trạng thái âm hợp lệ hoặc sử dụng một trạng thái không tồn tại như thể nó có giá trị 0.

Trong Java, ví dụ sẽ dùng **`Long` bằng `null`** cho trạng thái **không đạt được**. `0L` mang nghĩa chính xác là **tổng giá trị bằng 0 của một phương án hợp lệ**; hai tình huống không bị nhập nhằng.

## 3. Ví dụ chính: chọn cây con liên thông với ngân sách k đỉnh

Cho một **cây có gốc 0**. Mỗi đỉnh u có giá trị `value[u]`, có thể âm. Cần chọn một tập đỉnh `S` thỏa:

1. `S` rỗng; hoặc nếu không rỗng thì **S chứa gốc 0**.
2. `S` **liên thông** theo các cạnh của cây.
3. Số đỉnh chọn `|S|` không quá ngân sách B.
4. Tổng giá trị các đỉnh được chọn là lớn nhất.

Điều kiện liên thông và chứa gốc tương đương: **nếu chọn một đỉnh thì cũng phải chọn tất cả tổ tiên của nó trên đường về gốc**. Không thể chọn một đỉnh cháu mà bỏ qua cha của nó.

Xét cây:

~~~text
                 0 (5)
                /     \
             1 (4)    2 (-2)
             /   \        \
          3 (7)  4 (3)    5 (6)
~~~

Bảng dữ liệu:

| Đỉnh | Cha | Giá trị |
|---:|---:|---:|
| 0 | -1 (gốc) | 5 |
| 1 | 0 | 4 |
| 2 | 0 | -2 |
| 3 | 1 | 7 |
| 4 | 1 | 3 |
| 5 | 2 | 6 |

Với ngân sách **B=3**, có thể chọn `{0,1,3}` để được \(5+4+7=16\). Không được chọn ba giá trị lớn nhất `7,6,5` (tổng 18), vì chọn đỉnh 3 yêu cầu đỉnh 1, còn chọn đỉnh 5 yêu cầu đỉnh 2. Tập `{0,3,5}` không thỏa ràng buộc kết nối/tổ tiên.

Vì vậy, **cấu trúc cây** quyết định những tổ hợp có thể chọn, còn **ngân sách B** quyết định số đỉnh cho phép. Bài toán đòi hỏi lưu đồng thời hai chiều này.

### 3.1. Định nghĩa trạng thái vừa đủ

Đặt:

\[
F_u[k]=\text{tổng giá trị lớn nhất khi chọn đúng k đỉnh trong cây con gốc u},
\]

với hợp đồng bổ sung:

- Nếu **k=0**, chọn **không đỉnh nào** của cây con, nên \(F_u[0]=0\).
- Nếu **k>0**, tập chọn phải **liên thông và chứa đỉnh u**.
- Nếu không có lựa chọn nào thỏa yêu cầu, \(F_u[k]=\text{UNREACHABLE}\).

Chính câu **“k>0 thì bắt buộc chứa u”** làm công thức ghép cây con đúng. Nếu chỉ nói “chọn k đỉnh liên thông ở đâu đó trong cây con u”, một lời giải con có thể chọn các cháu mà không chứa u, khiến việc ghép với cây cha không tự động liên thông.

Tập trạng thái của cây con u có tối đa:

\[
0\le k\le\min(B,\ size[u]),
\]

trong đó `size[u]` là số đỉnh của cây con u. Không cần cấp phát hàng nghìn ô cho một cây con chỉ có hai đỉnh.

### 3.2. Cơ sở

Khi mới xét riêng u, chưa ghép con nào:

\[
F_u[0]=0,\qquad F_u[1]=value[u].
\]

Mọi \(F_u[k]\) với \(k>1\) lúc này chưa hợp lệ. Nếu B=0, chỉ cần trạng thái k=0.

Đối với một đỉnh lá, đây cũng là trạng thái cuối của nó: chọn rỗng hoặc chọn chính lá. Nếu `value[u]` âm, trạng thái k=1 **vẫn hợp lệ** và phải giữ giá trị âm.

### 3.3. Ghép lần lượt từng cây con

Giả sử ta đã xử lý một số con của u và giữ mảng `current[a]`. Bây giờ muốn ghép cây con của v, có mảng `F_v[b]` đã tính xong.

Để chọn tổng cộng **a+b** đỉnh, ta có:

- Chọn **a** đỉnh từ phần đã xử lý thuộc u.
- Chọn **b** đỉnh từ cây con v.
- Nếu b=0, bỏ toàn bộ cây con v.
- Nếu b>0, `F_v[b]` **chứa v** và được nối với u qua cạnh u-v, với điều kiện **a>0** để u đã được chọn.

Chuyển:

\[
next[a+b]=\max\bigl(next[a+b],current[a]+F_v[b]\bigr)
\]

cho mọi cặp **a>0**, **b≥0**, cả hai trạng thái hợp lệ và \(a+b\le B\).

Giữ riêng:

\[
next[0]=0.
\]

**Không cho a=0, b>0.** Nếu làm vậy, ta sẽ chọn đỉnh từ cây con v trong khi không chọn u; kết quả `F_u[k]` có thể không chứa u, trái với định nghĩa trạng thái và điều kiện gắn với cha.

Mã giả:

~~~text
solve(u):
    current[0] = 0
    current[1] = value[u]     // nếu B >= 1
    những k khác: UNREACHABLE

    for từng con v của u:
        child = solve(v)
        next[*] = UNREACHABLE
        next[0] = 0

        for a = 1 .. số đỉnh hợp lệ đã xử lý:
            if current[a] không hợp lệ: continue
            for b = 0 .. số đỉnh hợp lệ của v:
                if child[b] không hợp lệ: continue
                if a+b > B: continue
                next[a+b] = max(next[a+b],
                                current[a] + child[b])

        current = next

    return current
~~~

**Trật tự phụ thuộc:** phải tính mảng DP của **mọi con v trước khi tính xong u**. Đây là **duyệt hậu thứ tự** (*postorder*) trên cây. Trong phạm vi mỗi u, lần lượt gộp các con; không được lấy `F_v[b]` từ con chưa xử lý.

## 4. Mô phỏng tree knapsack

Trong cây ví dụ:

- Cây con gốc **1** gồm các đỉnh `1,3,4` với giá trị `4,7,3`.
- Cây con gốc **2** gồm các đỉnh `2,5` với giá trị `-2,6`.

Các trạng thái:

| k | \(F_1[k]\) | Lý do |
|---:|---:|---|
| 0 | 0 | Bỏ toàn bộ cây con 1 |
| 1 | 4 | Chỉ chọn đỉnh 1 |
| 2 | 11 | Chọn 1 và 3 |
| 3 | 14 | Chọn 1,3,4 |

Tương tự:

| k | \(F_2[k]\) | Lý do |
|---:|---:|---|
| 0 | 0 | Bỏ toàn bộ cây con 2 |
| 1 | -2 | Chỉ chọn đỉnh 2 |
| 2 | 4 | Chọn 2 và 5, tổng -2+6 |

Bây giờ ghép hai con với gốc 0 (giá trị 5). Với ngân sách tối đa **4**:

| Số đỉnh k chính xác | \(F_0[k]\) | Một tập đỉnh đạt giá trị |
|---:|---:|---|
| 0 | 0 | Tập rỗng |
| 1 | 5 | {0} |
| 2 | 9 | {0,1} |
| 3 | **16** | {0,1,3} |
| 4 | **19** | {0,1,3,4} |

Ví dụ với k=3:

\[
\begin{aligned}
F_0[3]&=\max(\text{các cách ghép hợp lệ với tổng 3 đỉnh})\\
&=\max(5+11,\ 5+4,\ 5+4+(-2),\ldots)\\
&=16.
\end{aligned}
\]

Cách chọn **đỉnh 5** phải trả thêm chi phí cấu trúc là **đỉnh 2**. Vì thế tập `{0,2,5}` dùng đúng 3 đỉnh nhưng có giá trị \(5-2+6=9\), không thể giả vờ dùng giá trị 6 mà không tốn tài nguyên chọn đỉnh 2.

**Truy vấn “đúng 4 đỉnh”** trả \(F_0[4]=19\). **Truy vấn “không quá 3 đỉnh”** trả \(\max(F_0[0],F_0[1],F_0[2],F_0[3])=16\). Không được thay hai yêu cầu này bằng nhau khi có giá trị âm hoặc ràng buộc chọn đủ số lượng.

## 5. Bất biến ghép cây và chứng minh tính đúng

### 5.1. Bất biến trong một đỉnh u

Giả sử đã gộp xong một tập các cây con đầu tiên của u. Với mọi k>0, `current[k]` là giá trị lớn nhất của một tập **chứa u, liên thông, dùng đúng k đỉnh**, chỉ được lấy từ u và những cây con đã gộp. `current[0]=0` đại diện cho tập rỗng. Các trạng thái không thể đạt được phải giữ **UNREACHABLE**.

**Cơ sở:** trước khi ghép con, `current[0]=0`, `current[1]=value[u]`. Đây chính xác là các tập có thể chọn từ một đỉnh u.

**Bước ghép con v:** Mọi tập chọn hợp lệ sau khi thêm v thuộc một trong hai loại:

1. **Không chọn đỉnh của cây con v:** b=0; giữ lời giải hiện tại với a đỉnh.
2. **Chọn một số đỉnh trong cây con v:** phải chọn v và phần chọn trong cây con v liên thông, đồng thời đã chọn u ở phần hiện tại. Phần tại v dùng b>0 đỉnh và có giá trị tốt nhất \(F_v[b]\), phần tại u dùng a>0 đỉnh và có giá trị tốt nhất `current[a]`.

Hai phần nằm trong **những cây con rời nhau**, nên số lượng và tổng giá trị cộng được: a+b, `current[a]+F_v[b]`. Lấy max qua mọi cách chia k cho a,b là đủ và không bỏ sót lời giải hợp lệ.

**Kết luận:** Sau khi gộp mọi con, `F_u[k]` đúng cho cây con u. Duyệt cây từ lá lên gốc cho phép dùng giả thiết quy nạp rằng mọi `F_v[b]` của con đã đúng. Từ đó `F_0[k]` đúng cho toàn cây.

### 5.2. Tại sao cùng một đơn vị tài nguyên không bị tính hai lần?

Mỗi đỉnh cây thuộc đúng **một** cây con trực tiếp của u, ngoại trừ chính u. Các tập đỉnh của những con khác nhau **không giao nhau**. Khi ghép con v vào phần đã xử lý, ta phân bổ tài nguyên **a** và **b** cho hai phần rời nhau; không có đỉnh nào xuất hiện ở cả hai bên.

Điều này phụ thuộc vào giả thiết **cấu trúc là cây**. Trong một DAG tổng quát, hai nhánh có thể chia sẻ một hậu duệ. Nếu mượn nguyên công thức ghép cây con và cộng số đỉnh của hai nhánh đó, một đỉnh chung có thể bị **đếm hai lần**. Khi đó cần đổi định nghĩa trạng thái, tách phần giao, dùng decomposition phù hợp hoặc thuật toán khác. Không phải mọi DAG đều có các cây con độc lập.

## 6. Thứ tự tính: cấu trúc trước, phân bổ tài nguyên sau

Tại mỗi đỉnh u, quan hệ phụ thuộc là:

~~~text
Kết quả của con v
      |
      v
Bảng F_v[b] đã hoàn tất
      |
      v
Ghép từng con vào current[a] của u
      |
      v
Bảng F_u[k] hoàn tất
~~~

Từ đó có hai tầng thứ tự:

- **Tầng cấu trúc:** các đỉnh con phải xong trước cha ⇒ **postorder**.
- **Tầng tài nguyên:** tại một phép ghép, xét **cặp (a,b)** và ghi kết quả vào **mảng next mới**.

Tạo `next` riêng giúp tránh đọc một giá trị đã cập nhật từ **cùng cây con v** rồi vô tình dùng cây con đó nhiều lần. Nếu cập nhật `current` tại chỗ mà duyệt không đúng, có thể biến một phép ghép 0/1 thành phép ghép cho phép chọn lại cùng nhánh.

Đối với tree knapsack, cách dễ chứng minh nhất là **hai mảng current và next** cho mỗi phép ghép con. Có thể tối ưu cấp phát hoặc nén thêm nhưng phải chứng minh rằng mỗi cây con chỉ được ghép **một lần**.

### Tại sao cần cả u và k?

- Nếu chỉ lưu **u**: không thể phân biệt lời giải dùng 1 đỉnh với lời giải dùng 4 đỉnh; khó chia ngân sách giữa con.
- Nếu chỉ lưu **k**: mất thông tin cây con nào được phép chọn, không thể biết lựa chọn cần tổ tiên gì.
- Nếu lưu **(u,k)**: nhận dạng đúng bài toán con và lượng tài nguyên, sau đó phép chuyển mới quyết định cách ghép những phần cấu trúc.

Mấu chốt không phải tăng số chiều cho đẹp: **hai chiều lưu đúng hai loại thông tin không thể suy ra từ nhau**.

## 7. Ví dụ thứ hai: đỉnh đồ thị và số cạnh đã đi

Một bài toán tương tự nhưng có **chuyển trạng thái theo cạnh** thay vì ghép cây con: cho đồ thị có hướng và mỗi cạnh mang một điểm số, tìm **tổng điểm tối đa** của một hành trình bắt đầu tại s, đến đỉnh v và dùng **đúng t cạnh**.

Đặt:

\[
D[t][v]=\text{tổng điểm lớn nhất của một hành trình từ s tới v, dùng đúng t cạnh}.
\]

Ở đây:

- **Chiều cấu trúc:** đỉnh **v** đang đứng.
- **Chiều tài nguyên:** **t** cạnh đã dùng.
- **Giá trị trạng thái:** điểm lớn nhất, có thể âm; `UNREACHABLE` nếu không có hành trình đúng t cạnh.

Cơ sở:

\[
D[0][s]=0,\qquad D[0][v\ne s]=\text{UNREACHABLE}.
\]

Với cạnh \(u\to v\) có điểm \(w(u,v)\), khi t≥1:

\[
\boxed{D[t][v]=\max_{u\to v}
\bigl(D[t-1][u]+w(u,v)\bigr)}
\]

chỉ xét những `D[t-1][u]` hợp lệ.

### Tại sao t phải tăng?

Mỗi trạng thái lớp t **chỉ phụ thuộc lớp t-1**, nên thứ tự tính phải là **t=0,1,2,...,K**. Trong mỗi lớp, ta có thể quét toàn bộ danh sách cạnh; không được dùng giá trị của lớp t vừa cập nhật để tạo thêm một cạnh ngay trong **cùng** lớp, vì như vậy tài nguyên “số cạnh đã đi” sẽ bị ghi sai.

Mã giả:

~~~text
D[*][*] = UNREACHABLE
D[0][source] = 0

for t = 1 .. K:
    for mỗi cạnh (u -> v, score):
        if D[t-1][u] hợp lệ:
            D[t][v] = max(D[t][v],
                          D[t-1][u] + score)
~~~

Điều thú vị: khi tính **hành trình có đúng t cạnh**, mở rộng trạng thái bằng t khiến **đồ thị trạng thái (v,t)** là DAG theo chiều t tăng, **ngay cả nếu đồ thị vị trí gốc có chu trình**. Mỗi chuyển trạng thái tăng t một đơn vị nên không thể quay về một trạng thái cũ có cùng t.

Nhưng phải chốt từ ngữ: với đồ thị có chu trình, cách trên đếm/tối ưu **walks** (hành trình có thể lặp lại đỉnh hoặc cạnh), **không bảo đảm đường đi đơn không lặp đỉnh**. Nếu đề yêu cầu đường đi đơn, trạng thái (v,t) có thể **không đủ**, vì cần biết những đỉnh đã thăm hoặc áp dụng cấu trúc/thuật toán phù hợp. Với DAG, mọi hành trình theo chiều cạnh tự động không lặp đỉnh.

### Ví dụ có giới hạn cạnh

Xét DAG:

~~~text
0 --4--> 1 --5--> 3
 \        |
  2       1
   \      v
    >---- 2 --3--> 3
~~~

Bảng cạnh chính xác:

| Cạnh | Điểm |
|---|---:|
| 0 → 1 | 4 |
| 0 → 2 | 2 |
| 1 → 3 | 5 |
| 2 → 3 | 3 |
| 1 → 2 | 1 |

Nguồn s=0, đích v=3:

- Dùng **đúng 1 cạnh:** không có cạnh trực tiếp 0→3 ⇒ **không thể đạt**.
- Dùng **đúng 2 cạnh:** chọn `0→1→3`, điểm **9**.
- Dùng **đúng 3 cạnh:** chọn `0→1→2→3`, điểm **8**.
- Dùng **không quá 3 cạnh:** chọn giá trị tốt nhất trong các lớp 0..3 ⇒ **9**.

Giới hạn “không quá K” được trả bằng cách xét **tất cả lớp t≤K** ở đích, không chỉ đọc `D[K][target]`. Trong ví dụ, đọc đúng lớp 3 cho 8, còn yêu cầu không quá 3 phải trả 9.

So với tree knapsack, chiều tài nguyên ở đây chỉ tăng **một** mỗi lần đi qua cạnh, nên không cần chia ngân sách giữa nhiều cây con. **Công thức chuyển khác nhau vì cấu trúc khác nhau**, dù mô hình chung vẫn là tách **địa điểm** khỏi **mức tiêu hao**.

## 8. Java 17+: một chương trình cho tree knapsack và DP giới hạn cạnh

Mã Java sau minh họa **hai loại cấu trúc khác nhau** với cùng tư duy tách chiều trạng thái.

**Phần cây:**

- Cây được cho bằng mảng `parent`, gốc là đỉnh 0 và `parent[0] = -1`.
- `bestTreeExact[k]` giữ **giá trị lớn nhất khi chọn đúng k đỉnh**, thỏa điều kiện liên thông chứa gốc nếu k>0.
- `null` biểu thị trạng thái không thể đạt. `0L` ở k=0 là tập rỗng hợp lệ.
- Duyệt cây **không đệ quy**, lấy thứ tự rồi đảo để mọi con được xử lý trước cha; tránh phụ thuộc vào độ sâu call stack.
- Ghép từng con bằng **mảng mới** để không dùng nhầm một cây con nhiều lần.

**Phần đồ thị:**

- `byEdges[t][v]` là điểm lớn nhất khi đến v bằng đúng t cạnh.
- Mỗi lớp t chỉ đọc **lớp t-1**; giá trị âm và trạng thái chưa tới được được xử lý riêng.
- Phương thức này tối ưu **walks** với giới hạn cạnh; ví dụ đầu vào được chọn là DAG.

Lưu tệp **StructuralResourceDpDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class StructuralResourceDpDemo {
    record Arc(int from, int to, long gain) {}

    // root = 0; parent[0] = -1.
    // result[k]: best value using exactly k vertices,
    // empty or connected to root, null = unreachable.
    static Long[] bestTreeExact(
        int[] value, int[] parent, int budget
    ) {
        Objects.requireNonNull(value, "value");
        Objects.requireNonNull(parent, "parent");

        int n = value.length;
        if (n == 0 || parent.length != n || budget < 0
                || parent[0] != -1) {
            throw new IllegalArgumentException("invalid tree/budget");
        }

        List<List<Integer>> children = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            children.add(new ArrayList<>());
        }

        for (int v = 1; v < n; v++) {
            int p = parent[v];
            if (p < 0 || p >= n || p == v) {
                throw new IllegalArgumentException("invalid parent");
            }
            children.get(p).add(v);
        }

        // Discovery order: parent appears before each child.
        ArrayDeque<Integer> stack = new ArrayDeque<>();
        List<Integer> order = new ArrayList<>();
        stack.push(0);
        while (!stack.isEmpty()) {
            int u = stack.pop();
            order.add(u);
            for (int v : children.get(u)) {
                stack.push(v);
            }
        }
        if (order.size() != n) {
            throw new IllegalArgumentException("not a rooted tree");
        }

        Long[][] dp = new Long[n][];
        // Reverse discovery order: descendants before parents.
        for (int index = order.size() - 1; index >= 0; index--) {
            int u = order.get(index);

            Long[] current = new Long[Math.min(budget, 1) + 1];
            current[0] = 0L;
            if (budget >= 1) {
                current[1] = (long) value[u];
            }

            for (int v : children.get(u)) {
                Long[] child = dp[v];
                int maxCount = Math.min(
                    budget, (current.length - 1) + (child.length - 1)
                );
                Long[] next = new Long[maxCount + 1];
                next[0] = 0L;

                // a > 0 means the parent u was selected.
                for (int a = 1; a < current.length; a++) {
                    if (current[a] == null) {
                        continue;
                    }
                    for (int b = 0; b < child.length; b++) {
                        if (a + b >= next.length || child[b] == null) {
                            continue;
                        }
                        long candidate = Math.addExact(
                            current[a], child[b]
                        );
                        Long old = next[a + b];
                        if (old == null || candidate > old) {
                            next[a + b] = candidate;
                        }
                    }
                }
                current = next;
            }
            dp[u] = current;
        }
        return dp[0];
    }

    static long bestAtMost(Long[] exact, int limit) {
        Objects.requireNonNull(exact, "exact");
        if (limit < 0 || exact.length == 0) {
            throw new IllegalArgumentException("invalid limit");
        }

        Long best = null;
        for (int k = 0; k < exact.length && k <= limit; k++) {
            Long candidate = exact[k];
            if (candidate != null
                    && (best == null || candidate > best)) {
                best = candidate;
            }
        }
        if (best == null) {
            throw new IllegalStateException("no feasible solution");
        }
        return best;
    }

    // Exact number of edges; walks may repeat vertices if cycles exist.
    static Long[][] bestWalkByEdges(
        int vertices, List<Arc> edges, int source, int maxEdges
    ) {
        Objects.requireNonNull(edges, "edges");
        if (vertices <= 0 || maxEdges < 0
                || source < 0 || source >= vertices) {
            throw new IllegalArgumentException("invalid graph/limit");
        }

        for (Arc arc : edges) {
            Objects.requireNonNull(arc, "arc");
            if (arc.from() < 0 || arc.from() >= vertices
                    || arc.to() < 0 || arc.to() >= vertices) {
                throw new IllegalArgumentException("invalid endpoint");
            }
        }

        Long[][] dp = new Long[maxEdges + 1][vertices];
        dp[0][source] = 0L;

        for (int t = 1; t <= maxEdges; t++) {
            for (Arc arc : edges) {
                Long previous = dp[t - 1][arc.from()];
                if (previous == null) {
                    continue;
                }
                long candidate = Math.addExact(previous, arc.gain());
                Long best = dp[t][arc.to()];
                if (best == null || candidate > best) {
                    dp[t][arc.to()] = candidate;
                }
            }
        }
        return dp;
    }

    static Long bestDestinationAtMost(Long[][] dp, int target) {
        Objects.requireNonNull(dp, "dp");
        if (dp.length == 0 || target < 0 || target >= dp[0].length) {
            throw new IllegalArgumentException("invalid target");
        }

        Long best = null;
        for (Long[] layer : dp) {
            Long candidate = layer[target];
            if (candidate != null
                    && (best == null || candidate > best)) {
                best = candidate;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        int[] value = {5, 4, -2, 7, 3, 6};
        int[] parent = {-1, 0, 0, 1, 1, 2};

        Long[] tree = bestTreeExact(value, parent, 4);
        for (int k = 0; k < tree.length; k++) {
            System.out.println("Tree exact " + k + ": " + tree[k]);
        }
        System.out.println("Tree at most 3: "
            + bestAtMost(tree, 3));

        Long[] negative = bestTreeExact(
            new int[] {-5}, new int[] {-1}, 1
        );
        System.out.println("Negative exact 1: " + negative[1]);
        System.out.println("Negative at most 1: "
            + bestAtMost(negative, 1));

        List<Arc> arcs = List.of(
            new Arc(0, 1, 4),
            new Arc(0, 2, 2),
            new Arc(1, 3, 5),
            new Arc(2, 3, 3),
            new Arc(1, 2, 1)
        );

        Long[][] paths = bestWalkByEdges(4, arcs, 0, 3);
        System.out.println("DAG exact 2 edges: " + paths[2][3]);
        System.out.println("DAG exact 3 edges: " + paths[3][3]);
        System.out.println("DAG at most 3 edges: "
            + bestDestinationAtMost(paths, 3));
        System.out.println("DAG exact 1 edge: "
            + (paths[1][3] == null ? "unreachable" : paths[1][3]));

        try {
            bestTreeExact(new int[] {1, 2},
                new int[] {-1, 1}, 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid tree: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac StructuralResourceDpDemo.java
java StructuralResourceDpDemo
~~~

**Stdout chính xác:**

~~~text
Tree exact 0: 0
Tree exact 1: 5
Tree exact 2: 9
Tree exact 3: 16
Tree exact 4: 19
Tree at most 3: 16
Negative exact 1: -5
Negative at most 1: 0
DAG exact 2 edges: 9
DAG exact 3 edges: 8
DAG at most 3 edges: 9
DAG exact 1 edge: unreachable
Invalid tree: invalid parent
~~~

### Cách đọc và kiểm chứng mã

**Cây:** Mã duyệt từ gốc, thu danh sách theo thứ tự cha trước con, rồi đảo thứ tự để ghép **con trước cha**. Vì mỗi đỉnh khác gốc có đúng một cha, nếu tất cả n đỉnh tới được từ gốc thì dữ liệu tạo thành cây có gốc; nếu không, mã từ chối. Nó không đọc/ghi đè mảng giá trị và mảng cha từ phía gọi.

**Trạng thái không hợp lệ:** `Long[]` giữ `null` cho các mức k không thể đạt; Java không dùng `0` để “giả vờ có” một tập đỉnh. Nhờ thế trạng thái `k=1` giá trị **-5** vẫn tồn tại và được trả đúng khi chọn chính xác 1 đỉnh.

**Cây con chỉ được dùng một lần:** Khi ghép child v, mã chỉ đọc `current` và `dp[v]` cũ, ghi vào `next` mới. Đây là kiểm soát cập nhật tương tự ý tưởng “lớp trước và lớp sau” trong ba lô 0/1.

**Budget rất lớn:** Nếu ngân sách lớn hơn số đỉnh có thể lấy, mảng thực tế chỉ tạo tới số đỉnh của cây con. Nếu muốn truy vấn k vượt kích thước mảng trả về, nó là không thể đạt; không được truy cập chỉ số ngoài mảng.

**Đồ thị:** `paths[t][v]` ở hàng t chỉ đọc `paths[t-1]`, nên không thể sử dụng một cạnh hai lần **trong cùng một đơn vị tài nguyên**. Nó không yêu cầu graph phải là DAG vì mô hình tính hành trình có số cạnh hữu hạn; nếu graph có chu trình, kết quả có thể chứa lặp đỉnh. Mỗi cạnh mang điểm dạng `long`; `Math.addExact` phát hiện tổng bị tràn.

**Kết quả lớp và kết quả gộp:** `paths[3][3]=8` là “đến đỉnh 3 bằng đúng 3 cạnh”; `bestDestinationAtMost(paths,3)=9` là “đến đỉnh 3 bằng không quá 3 cạnh”. Hai con số khác nhau nhưng đều đúng theo hợp đồng tương ứng.

**Nhớ giới hạn cấp phát:** `Long[][]` có overhead của đối tượng boxed `Long`; ví dụ ưu tiên sự rõ ràng của trạng thái. Dữ liệu rất lớn có thể dùng `long[]` kèm `boolean[]` hợp lệ, tối ưu bộ nhớ, hoặc lưu trạng thái thưa. Tránh cấp phát `maxEdges+1` với ngân sách vượt miền int/không đủ RAM; cần áp giới hạn đầu vào thực tế.

## 9. Độ phức tạp: tích số trạng thái chưa đủ để tính thời gian

Với cây n đỉnh và ngân sách tối đa B:

- Có tối đa **\(n(B+1)\)** trạng thái `(u,k)`.
- Mỗi phép **ghép một cây con** có thể xét mọi cặp `(a,b)` với a,b tới B, tức \(O(B^2)\) trong cận trên đơn giản.
- Cây có n-1 cạnh cha-con, mỗi cạnh tương ứng một lần ghép con.

Do đó:

\[
\boxed{T_{\text{tree}}=O(nB^2),\qquad
S_{\text{tree}}=O(nB)}
\]

là các **cận trên** của cách làm minh họa (chưa tính vài hằng số cấp phát). Thực tế nhanh hơn nếu giới hạn `a,b` theo **kích thước cây con** và bỏ các trạng thái null.

**Không được suy ra thời gian chỉ là O(nB)** từ việc có nB ô: mỗi ô `F_u[k]` có thể phải xét **nhiều cách chia ngân sách** giữa các nhánh. Cần đếm cả số **cặp phân bổ (a,b)**, không chỉ số ô.

Với đồ thị `V` đỉnh, `E` cạnh, giới hạn số cạnh K:

- Bảng `D[t][v]` có \((K+1)V\) ô.
- Mỗi lớp t quét E cạnh đúng một lần.
- Thời gian \(O((K+1)V+KE)\), thường viết \(O(K(V+E))\) khi K≥1.
- Bộ nhớ \(O((K+1)V)\), vì mã giữ mọi lớp để trả nhiều truy vấn chính xác theo số cạnh.

Nếu chỉ cần kết quả ở **lớp K**, và phép chuyển chỉ đọc **lớp K-1**, có thể dùng hai mảng `previous` và `current` để giảm bộ nhớ trạng thái xuống **O(V)**. Nếu muốn câu trả lời “không quá K”, có thể duy trì thêm mảng/tổng tối ưu theo tất cả lớp đã tính mà không nhất thiết lưu toàn bộ bảng.

**Quy tắc chung:**

\[
\text{Thời gian DP}
\approx \text{số trạng thái được tính}
+\text{tổng công việc chuyển trạng thái}.
\]

Số chiều giúp đánh giá không gian, nhưng độ phức tạp thời gian còn tùy **mỗi trạng thái được tổng hợp từ bao nhiêu lựa chọn**.

## 10. Chọn biểu diễn trạng thái tài nguyên phù hợp

Bài toán có thể mô tả tài nguyên theo các cách khác nhau:

| Kiểu tài nguyên | Ví dụ | Câu hỏi cần chốt |
|---|---|---|
| **Đã dùng** | Số đỉnh chọn `k`, số bước `t` | “Đúng k” hay “không quá k”? |
| **Còn lại** | Năng lượng `e`, số lượt sửa `r` | Khi chuyển trạng thái thì trừ bao nhiêu? |
| **Ngân sách tối đa** | Dung lượng `B` | Có được để dư ngân sách không? |
| **Số lượt theo lớp** | Thời điểm `t`, số cạnh đã đi | Có trạng thái cơ sở ở lớp t=0 không? |
| **Nhiều tài nguyên** | `dp[v][fuel][coupons]` | Tích số chiều có vượt bộ nhớ/thời gian? |

Một cách định nghĩa nhất quán có thể dùng:

\[
dp[v][used]=\text{điểm tốt nhất đến v sau khi đã dùng đúng used}.
\]

Khi sử dụng thêm c đơn vị:

\[
dp[v][used+c]\leftarrow
\operatorname{best}(dp[v][used+c],dp[u][used]+gain).
\]

Nếu đổi sang **remaining**, chuyển tài nguyên lại thành `remaining-c`. Cả hai cách có thể đúng nhưng **không được thay đổi ý nghĩa ở giữa thuật toán**.

Nếu c=0 hoặc có phép thao tác hoàn lại tài nguyên, một quan hệ phụ thuộc **không tự bảo đảm tài nguyên tăng/giảm nghiêm ngặt**. Khi đó phải xem thêm thứ tự của cấu trúc hoặc một đại lượng tiến triển khác. Chẳng hạn nếu có các cạnh tiêu tốn 0 trên một graph có chu trình, đồ thị trạng thái `(v,resource)` vẫn có thể chứa chu trình; không thể áp dụng một lượt topo mà không kiểm tra.

### Tài nguyên có thực sự cần lưu nguyên giá trị?

Đôi khi có thể **nén** số trạng thái bằng loại bỏ phương án bị **chi phối** (*dominance*): tại cùng trạng thái cấu trúc v, phương án A dùng không nhiều tài nguyên hơn B và có điểm số không kém B thì B có thể vô ích nếu các lựa chọn tương lai phụ thuộc tài nguyên theo cách đơn điệu thích hợp.

Nhưng không được loại bỏ tùy tiện khi:

- Bài toán yêu cầu dùng **đúng k** tài nguyên.
- Mỗi mức tài nguyên cho phép một loại hành động riêng.
- Điều kiện tương lai phụ thuộc cách tiêu hao tài nguyên, không chỉ số lượng còn lại.
- Có ràng buộc không đơn điệu hoặc mục tiêu nhiều chiều.

Trước khi tối ưu bằng dominance, cần chứng minh **loại bỏ trạng thái không làm mất lời giải khả thi hoặc tối ưu**.

## 11. Tránh nhầm lẫn giữa cấu trúc, tài nguyên và giá trị tối ưu

Ba thành phần của một trạng thái DP có vai trò riêng:

~~~text
dp[struct][resource] = optimum
    |        |            |
    |        |            +-- giá trị kết quả (score/cost/count)
    |        +--------------- lượng tài nguyên đã dùng/còn lại
    +------------------------ phần cấu trúc đang xử lý
~~~

Ví dụ:

- `dp[u][k]=17`: u và k là **nhãn trạng thái**; 17 là **giá trị**.
- `dp[v][t]=-4`: v và t là nhãn; -4 là điểm tối ưu âm, **không phải trạng thái không hợp lệ**.
- `dp[v][t]=null`: không có hành trình đúng t cạnh tới v; **không được sử dụng trong phép cộng**.

Lỗi thường gặp là **gộp giá trị tối ưu với số tài nguyên**: ví dụ `dp[u]=số đỉnh tốt nhất` nhưng sau đó cộng nó như thể là tổng giá trị; hoặc `dp[v][k]` lúc đầu có nghĩa “dùng đúng k” nhưng sau một vòng chuyển lại hiểu “dùng không quá k”.

Một cách phát hiện lỗi là thử diễn đạt bằng câu hoàn chỉnh:

> “Tại cấu trúc **X**, với tài nguyên **R** theo quy ước **chính xác/tối đa/còn lại**, `dp[X][R]` là **giá trị tốt nhất của mọi phương án hợp lệ**.”

Nếu không thể viết câu đó nhất quán cho mọi ô, cần sửa định nghĩa trước khi viết code.

## 12. Trường hợp biên và kiểm thử

| Ca kiểm thử | Kỳ vọng |
|---|---|
| Cây một đỉnh, giá trị dương | Exact 0 = 0, exact 1 = giá trị đỉnh |
| Cây một đỉnh, giá trị âm | Exact 1 âm; at-most 1 = 0 nếu cho phép bỏ chọn |
| Budget B=0 | Chỉ có phương án rỗng hợp lệ nếu đề cho phép |
| B lớn hơn số đỉnh | Không có trạng thái chọn đúng nhiều hơn số đỉnh |
| Cây nhiều nhánh | Ghép bằng phép chia ngân sách a+b và giữ kết nối qua cha |
| Chọn cháu mà không chọn cha | **Không hợp lệ** trong tree-knapsack có điều kiện tổ tiên |
| Cây đầu vào có chu trình cha hoặc không kết nối gốc | Báo dữ liệu không phải cây có gốc hợp lệ |
| Nhiều giá trị âm | Không được giả định mọi trạng thái hợp lệ ≥0 |
| DAG nguồn s không có cạnh ra | Chỉ có trạng thái `D[0][s]=0`; lớp t>0 có thể không tới được |
| Đồ thị không có hành trình đúng K cạnh tới đích | `D[K][target]` = không thể đạt, dù at-most K có thể đạt |
| Đồ thị có cạnh điểm âm | Điểm âm là ứng viên hợp lệ, không bị thay bằng 0 |
| Đồ thị có chu trình, K hữu hạn | DP t-layer tính **walks** đúng; không tự đảm bảo đường đi đơn |
| Tài nguyên tiêu hao 0 và chu trình trạng thái | Cần kiểm tra thứ tự phụ thuộc, không chỉ tăng ngân sách |
| Tràn phép cộng `long` | Mã dùng `Math.addExact`; có thể đổi BigInteger/modulo nếu đặc tả yêu cầu |

Để kiểm thử tính đúng, có thể dùng một **oracle vét cạn trên cây rất nhỏ**: liệt kê mọi tập đỉnh, chỉ giữ các tập rỗng hoặc kết nối chứa gốc, tính tổng và số đỉnh, rồi so kết quả tốt nhất của từng k với `F_0[k]`. Với đồ thị nhỏ và K thấp, liệt kê mọi walk có đúng t cạnh rồi so với `D[t][v]`. Không nên dùng vét cạn trên dữ liệu lớn vì số tập/đường đi có thể tăng theo hàm mũ.

Bộ kiểm thử nên tập trung vào **sự khác biệt giữa tầng cấu trúc và tầng tài nguyên**: một phương án có điểm cao nhưng dùng thêm tổ tiên; một lớp t có kết quả tốt hơn lớp t+1; và những mức k/t không thể đạt.

## 13. Những lỗi thường gặp

1. **Chỉ lưu trạng thái cấu trúc** mà quên số lượng tài nguyên đã dùng, làm ghép nhánh vượt ngân sách.
2. **Chỉ lưu tài nguyên** mà quên vị trí/cây con, làm áp dụng những phép chọn không tương thích với cấu trúc.
3. **Định nghĩa trạng thái không đầy đủ:** `dp[u][k]` không nói “đúng k” hay “không quá k”, hoặc không nói chọn u có bắt buộc không.
4. **Nhầm không thể đạt với giá trị 0**, đặc biệt khi giá trị thực có thể âm.
5. **Chọn đỉnh cháu mà bỏ cha** trong bài toán cần tập liên thông chứa gốc.
6. **Cho phép a=0, b>0 khi ghép cây con**, làm lời giải của u không chứa u dù k>0.
7. **Dùng một cây con nhiều lần trong phép ghép** vì cập nhật tại chỗ không có mảng `next` hoặc duyệt sai.
8. **Xử lý cha trước con** trong DP cây khi công thức của cha cần DP hoàn chỉnh của từng con.
9. **Áp nguyên phép cộng ngân sách của cây cho DAG có hậu duệ chung**, làm trùng lặp phần cấu trúc được tính.
10. **Trả `exact[K]` cho câu hỏi “at most K”** mà không lấy max các lớp nhỏ hơn.
11. **Gộp điểm số thành tài nguyên hoặc ngược lại**, khiến giá trị/đơn vị không nhất quán qua các phép chuyển.
12. **Dùng cùng hàng t để cập nhật một đường có thêm cạnh** trong DP đếm bước, làm sai số cạnh đã dùng.
13. **Không xét đủ cạnh khi duyệt lớp t**, làm bỏ sót một đường tới cùng đỉnh từ các tiền nhiệm khác nhau.
14. **Bỏ qua trạng thái nguồn t=0**, khiến toàn bộ DP hành trình không có điểm khởi đầu hợp lệ.
15. **Đồng nhất walk và đường đi đơn** khi graph có chu trình.
16. **Nói time O(nB) chỉ vì có nB trạng thái tree DP**, trong khi ghép các cây con có thể cần O(B²).
17. **Không giới hạn chỉ số tài nguyên** theo budget và kích thước cây con, gây truy cập ngoài mảng hoặc cấp phát thừa.
18. **Quên dữ liệu âm và tràn số**, khiến phép `max` chọn trạng thái giả hoặc số bị overflow.
19. **Nén bộ nhớ quá sớm** và ghi đè dữ liệu của lớp trước mà công thức còn cần.
20. **Thêm nhiều chiều tài nguyên mà không kiểm tra kích thước tích**, làm thuật toán chính xác về toán học nhưng vượt giới hạn bộ nhớ.

## 14. Cách thiết kế trạng thái cho bài toán mới

Khi gặp một bài toán DP vừa có cấu trúc vừa có ràng buộc tài nguyên, hãy làm theo quy trình:

1. **Gọi tên phần cấu trúc**: đỉnh v, cây con u, đoạn [l,r], vị trí i, thành phần cấu trúc nào có thể xử lý độc lập?
2. **Gọi tên tài nguyên**: số đỉnh đã chọn, dung lượng, năng lượng, số bước, số lượt thao tác; đơn vị là gì?
3. **Chốt quy ước**: dùng đúng, dùng tối đa hay còn lại? Có cho phép dùng 0 không?
4. **Định nghĩa tính hợp lệ**: ví dụ ở cây, chọn k>0 bắt buộc có u; ở đồ thị, phải có walk từ s tới v đúng t cạnh.
5. **Viết trạng thái cơ sở**: tập rỗng, nguồn ở t=0, các trường hợp lá hoặc không tới được.
6. **Xác định cạnh phụ thuộc**: con→cha khi ghép cây; lớp t-1→t khi thêm cạnh; các chiều khác phải có lịch tính riêng.
7. **Viết chuyển trạng thái cùng phép tính tài nguyên**: phân bổ a+b khi ghép nhánh; t→t+1 khi đi thêm một cạnh.
8. **Chứng minh không vi phạm cấu trúc**: không chọn cháu thiếu cha, không dùng lại cùng nhánh, không phát sinh walk ngoài định nghĩa.
9. **Chứng minh tối ưu**: mọi lời giải hợp lệ được tách theo cách chuyển, phép max/min chọn đúng lời giải tốt nhất.
10. **Xử lý không thể đạt** bằng sentinel/cờ/nullable rõ ràng, đặc biệt với điểm âm.
11. **Xác định đầu ra theo đúng quy ước**: exact[K] hoặc max over 0..K; trả không thể đạt khi thật sự không có phương án.
12. **Tính chi phí thực**: số trạng thái nhân với số cách chuyển, đồng thời xét chi phí bộ nhớ của tích các chiều.
13. **Thử phản ví dụ**: ngân sách 0, điểm âm, chọn cháu thiếu cha, đồ thị có đường tốt hơn ở lớp t<K, và trạng thái không tới được.

## 15. Bài tập tự kiểm tra

**Bài 1 — Ý nghĩa hai chiều.** Trong `dp[u][k]` của tree knapsack, u và k lần lượt biểu thị gì? Vì sao không thể chỉ giữ `dp[u]`?

*Đáp án:* u xác định **cây con gốc u**; k là **số đỉnh đã chọn chính xác**. Nếu chỉ giữ một giá trị `dp[u]`, ta không thể chia ngân sách giữa các cây con và kiểm soát số đỉnh của lời giải hợp lệ.

**Bài 2 — Chọn cháu.** Cho gốc 0 (giá trị 2), con 1 (giá trị -10), cháu 2 (giá trị 100). Với budget 2 và điều kiện chọn liên thông chứa gốc, có được chọn `{0,2}` để nhận 102 không?

*Đáp án:* **Không.** Muốn chọn 2 phải chọn tổ tiên 1. Với tối đa 2 đỉnh, chỉ có tập rỗng (0), `{0}` (2), `{0,1}` (-8); đáp án **2**. Chọn đủ 3 đỉnh mới nhận \(2-10+100=92\).

**Bài 3 — Tập rỗng và giá trị âm.** Cây có một đỉnh gốc giá trị -5, budget 1. Kết quả “đúng 1” và “không quá 1” khác nhau thế nào?

*Đáp án:* **Đúng 1 = -5**; **không quá 1 = 0** nếu cho phép chọn rỗng. Vì vậy không thể mặc nhiên trả exact[1] cho truy vấn at-most.

**Bài 4 — Ghép nhánh.** Vì sao khi ghép `F_v[b]` vào `current[a]` của u chỉ cho phép b>0 nếu a>0?

*Đáp án:* Khi b>0, phần chọn trong cây con v chứa v. Để nó nối với phần ở u qua cạnh u-v, phải chọn u; điều đó được bảo đảm khi a>0. Nếu a=0, ta sẽ có tập không chứa u, trái định nghĩa `F_u[k>0]`.

**Bài 5 — Mức số cạnh.** Trên DAG ví dụ phần 7, điểm tốt nhất khi dùng đúng 2 cạnh tới đỉnh 3 là 9, còn đúng 3 cạnh là 8. Với giới hạn **không quá 3**, phải trả gì?

*Đáp án:* **9**, là max của các lớp có t≤3. Không được trả 8 chỉ vì K=3.

**Bài 6 — Chu trình.** Tại sao `D[t][v]` với chuyển từ t-1 sang t vẫn có thứ tự tính nếu đồ thị gốc có chu trình?

*Đáp án:* Mỗi phép chuyển làm **số cạnh đã dùng tăng 1**, nên đồ thị **trạng thái mở rộng (v,t)** không thể quay trở lại một trạng thái có cùng t. Tuy nhiên kết quả mô tả **walks có thể lặp đỉnh**, không phải đường đi đơn.

**Bài 7 — Độ phức tạp.** Tree DP có n đỉnh và B+1 mức tài nguyên. Vì sao phép ghép khiến thời gian có cận O(nB²) thay vì O(nB)?

*Đáp án:* Với mỗi lần ghép một con, phải xét nhiều cách chia ngân sách thành hai phần a+b; cận trên số cặp là O(B²). Tổng số phép ghép theo số cạnh cây là O(n), nên O(nB²).

**Bài 8 — Chia sẻ hậu duệ.** Hai nhánh của một DAG dùng chung một hậu duệ x. Có thể cộng số đỉnh chọn từ hai nhánh như ghép các cây con của cây không?

*Đáp án:* **Không được tự động.** Các nhánh DAG có thể **giao nhau** ở x, nên cộng hai số lượng/tổng giá trị có thể đếm x hai lần. Cần mô hình trạng thái/thuật toán xử lý phần giao hoặc cấu trúc decomposition khác.

**Tổng kết:** **Tách trạng thái cấu trúc khỏi trạng thái tài nguyên** giúp DP giữ đồng thời thông tin **đang xử lý phần cấu trúc nào** và **đã dùng bao nhiêu đơn vị ràng buộc**. Tree knapsack dùng `F_u[k]`, duyệt **con trước cha** và **chia ngân sách a+b** khi ghép các nhánh rời nhau; DP đường đi bị giới hạn số cạnh dùng `D[t][v]`, duyệt **t tăng** và chuyển từ **lớp t-1**. Muốn kết quả đúng phải phân biệt **exact / at-most**, **trạng thái không thể đạt / giá trị 0**, và bảo đảm quan hệ phụ thuộc không bị phá khi nén hoặc cập nhật bảng.