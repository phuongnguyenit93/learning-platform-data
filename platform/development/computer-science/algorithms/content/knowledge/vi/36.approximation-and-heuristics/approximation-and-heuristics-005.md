# Xấp xỉ người du lịch trong trường hợp thỏa bất đẳng thức tam giác

## Mục tiêu học tập

Trong phần **Xấp xỉ và kinh nghiệm**, bài toán người du lịch (*Traveling Salesperson Problem — TSP*) là ví dụ kinh điển cho việc phân biệt **tìm tối ưu chính xác**, **thuật toán kinh nghiệm (*heuristic*)** và **thuật toán xấp xỉ có bảo đảm (*approximation algorithm*)**.

Bài toán TSP tổng quát rất khó: không có thuật toán đa thức giải tối ưu chính xác nào được biết cho mọi trường hợp, và phiên bản quyết định của TSP là NP-complete theo các kết quả chuẩn của lý thuyết độ phức tạp. Tuy nhiên, khi khoảng cách giữa các thành phố thỏa **bất đẳng thức tam giác**, ta có thể xây một chu trình với chi phí **không vượt quá hai lần chi phí tối ưu** bằng một **cây khung nhỏ nhất (MST)**.

Bảo đảm cơ bản:

\[
\boxed{\operatorname{cost}(\text{tour xấp xỉ})\le 2\,\operatorname{OPT}.}
\]

Đây là thuật toán **2-approximation**, không phải tuyên bố rằng nó luôn tìm được nghiệm tối ưu.

Sau bài này, bạn cần:

1. Phát biểu chính xác **symmetric metric TSP**: đồ thị đầy đủ, vô hướng, trọng số không âm, đối xứng và thỏa bất đẳng thức tam giác.
2. Hiểu vì sao **MST là cận dưới** của chi phí tour tối ưu.
3. Xây thuật toán **double-tree / MST preorder**: MST → duyệt cây → bỏ lượt thăm lặp → khép chu trình.
4. Chứng minh không tăng chi phí khi **shortcut** nhờ bất đẳng thức tam giác.
5. Chứng minh toàn bộ bất đẳng thức `cost ≤ 2 MST ≤ 2 OPT` đúng điều kiện.
6. Cài đặt Java 17+ dùng **Prim O(n²)** trên ma trận khoảng cách và DFS preorder lặp, tránh tràn tổng bằng `BigInteger`.
7. Kiểm chứng trên ví dụ có tour xấp xỉ chi phí **18** và tối ưu chính xác **14**.
8. Nhận diện phản ví dụ cho **trọng số không thỏa tam giác**, nơi bảo đảm 2 lần có thể thất bại.
9. Nắm mở rộng **Christofides** với tỉ lệ **3/2** trong trường hợp TSP metric đối xứng.
10. Phân biệt bảo đảm lý thuyết với heuristic như **nearest neighbor**, **2-opt** và dữ liệu kiểm thử ngẫu nhiên.

---

## 1. Phát biểu bài toán người du lịch

Cho n thành phố đánh số:

\[
V=\{0,1,\ldots,n-1\}.
\]

Có một hàm chi phí:

\[
d:V\times V\to\mathbb R_{\ge0}.
\]

Một **tour** bắt đầu ở một thành phố, thăm **mỗi thành phố đúng một lần**, sau đó quay về thành phố khởi đầu.

Với thứ tự thăm là hoán vị:

\[
\pi=(\pi_0,\pi_1,\ldots,\pi_{n-1}),
\]

chi phí tour:

\[
\boxed{
C(\pi)=
\sum_{i=0}^{n-2}d(\pi_i,\pi_{i+1})
+d(\pi_{n-1},\pi_0).
}
\]

Mục tiêu:

\[
\boxed{\operatorname{OPT}=\min_\pi C(\pi).}
\]

Vì tour là một chu trình nên trong TSP đối xứng, thay đổi điểm bắt đầu chỉ xoay vòng thứ tự, còn đảo chiều tour cũng không đổi chi phí. Để tiện cho chương trình và kiểm thử, bài này luôn bắt đầu/kết thúc tại thành phố **0**.

### 1.1. TSP tổng quát và TSP metric khác nhau

Ở TSP trọng số tùy ý, có thể tồn tại:

\[
d(a,c)>d(a,b)+d(b,c).
\]

Nghĩa là đi thẳng từ a đến c **đắt hơn** đi qua b. Khi ấy thao tác bỏ b khỏi một hành trình có thể **làm tăng chi phí**. Bảo đảm MST 2-approx ở bài này sẽ không được chứng minh.

Với **metric TSP**, điều kiện tam giác bảo đảm đi thẳng không đắt hơn một đường đi có chặng trung gian. Đây chính là điểm tạo nên thuật toán xấp xỉ có chứng minh.

### 1.2. Bản quyết định và bản tối ưu

- **Phiên bản quyết định:** có một tour với chi phí ≤K không?
- **Phiên bản tối ưu:** tìm tour có chi phí nhỏ nhất.

Bài này giải phiên bản **tối ưu theo nghĩa xấp xỉ**: xuất một tour hợp lệ có chi phí bị chặn so với `OPT`, không nhất thiết tìm `OPT`.

---

## 2. Giả thiết của symmetric metric TSP

Ta xét đồ thị **đầy đủ vô hướng** có trọng số khoảng cách `d(u,v)`.

Những điều kiện chính:

### 2.1. Không âm

\[
\boxed{d(u,v)\ge0.}
\]

Giá trị 0 giữa hai thành phố khác nhau có thể xuất hiện nếu hai thành phố có cùng tọa độ hoặc trong khoảng cách ngắn nhất trên đồ thị có cạnh trọng số 0. Khi cho phép điều này, tên gọi chính xác về toán học có thể là **pseudometric**; chứng minh 2-approx vẫn hoạt động với các điều kiện không âm, đối xứng, `d(u,u)=0` và tam giác.

### 2.2. Đối xứng

\[
\boxed{d(u,v)=d(v,u).}
\]

Cạnh u–v và v–u có cùng chi phí.

**Không được tự áp dụng chứng minh MST double-tree cho asymmetric TSP (ATSP)**, ngay cả khi dữ liệu có một dạng bất đẳng thức tam giác có hướng.

### 2.3. Tự khoảng cách bằng 0

\[
\boxed{d(u,u)=0.}
\]

Chương trình dùng ma trận `long[][]` và kiểm tra chính xác điều kiện này.

### 2.4. Bất đẳng thức tam giác

Với mọi ba thành phố u,v,w:

\[
\boxed{d(u,w)\le d(u,v)+d(v,w).}
\]

Ta có thể lặp nhiều lần để suy ra:

\[
d(v_0,v_k)\le
\sum_{i=0}^{k-1}d(v_i,v_{i+1}).
\]

Đây là **bất đẳng thức chuỗi**: đi thẳng từ điểm đầu đến cuối không đắt hơn một đường đi nhiều chặng.

### 2.5. Đồ thị đầy đủ

Mọi cặp thành phố phân biệt đều có khoảng cách, để việc **đi thẳng giữa hai thành phố** sau shortcut luôn hợp lệ.

Nếu mạng đường ban đầu thưa, có thể xét **metric closure**: trọng số giữa hai thành phố là độ dài **đường đi ngắn nhất** giữa chúng trong một mạng liên thông vô hướng có trọng số không âm. Khoảng cách đường đi ngắn nhất là đối xứng và thỏa tam giác.

Chú ý một cạnh của metric closure có thể tương ứng với **một đường đi qua các đỉnh trung gian** của mạng đường gốc. Phải phân biệt tour trong metric closure với hành trình vật lý triển khai thành đường đi trên mạng ban đầu.

### 2.6. Ví dụ metric hợp lệ

**Khoảng cách Euclid 2D:**

\[
d(i,j)=\sqrt{(x_i-x_j)^2+(y_i-y_j)^2}.
\]

**Khoảng cách Manhattan:**

\[
d(i,j)=|x_i-x_j|+|y_i-y_j|.
\]

Cả hai đều không âm, đối xứng và thỏa tam giác. Java demo dùng **ma trận khoảng cách Manhattan nguyên** để tránh vấn đề làm tròn khi xác minh bất đẳng thức tam giác.

---

## 3. Tại sao phải xấp xỉ?

Với một thành phố xuất phát cố định là 0, ta có khoảng:

\[
(n-1)!
\]

thứ tự thăm cần cân nhắc theo cách vét cạn ngây thơ.

Với TSP đối xứng, một tour và tour đảo ngược tương đương về chi phí, nên có thể loại bớt một nửa các thứ tự ở n≥3, nhưng số trường hợp vẫn tăng **giai thừa**.

Các thuật toán chính xác như quy hoạch động Held–Karp có cận:

\[
O(n^2 2^n)
\]

về thời gian theo triển khai chuẩn, tốt hơn vét cạn về bậc nhưng vẫn **hàm mũ**. Chúng phù hợp hơn khi n nhỏ/vừa và cần tối ưu chính xác.

Với n lớn, có thể ưu tiên:

- Thuật toán xấp xỉ có **tỉ lệ được chứng minh**.
- Heuristic chất lượng tốt trong thực nghiệm.
- Thuật toán chính xác kết hợp cận, nhánh và cận, hoặc solver tối ưu chuyên dụng nếu tài nguyên cho phép.

### 3.1. "2-approximation" nghĩa là gì?

Với một bài toán **tối thiểu hóa** có chi phí không âm, thuật toán ρ-approximation thỏa:

\[
\boxed{
\operatorname{OPT}
\le C_{\mathrm{alg}}
\le \rho\,\operatorname{OPT}
}
\]

với mọi đầu vào thuộc phạm vi giả thiết.

Ở đây `\rho=2`. Nếu OPT=0, cách nói "tỉ lệ" `C_{\mathrm{alg}}/\operatorname{OPT}` không xác định; phải dùng dạng **bất đẳng thức chi phí**. Dạng `C_{\mathrm{alg}}\le2\operatorname{OPT}` vẫn có nghĩa và buộc `C_{\mathrm{alg}}=0` khi OPT=0.

### 3.2. Chứng minh xấp xỉ không nhất thiết biết OPT

Trong bài toán thực tế, ta thường **không biết OPT** vì tính nó rất khó. Tuy nhiên có thể chứng minh:

\[
C_{\mathrm{alg}}\le2\operatorname{OPT}
\]

bằng cách liên hệ với một **cận dưới tính được nhanh**. Cận dưới ấy là **chi phí MST**.

---

## 4. MST: cận dưới của tour tối ưu

**Cây khung** (*spanning tree*) nối tất cả n đỉnh mà không có chu trình, gồm n−1 cạnh khi n≥1.

**Cây khung nhỏ nhất** (*minimum spanning tree, MST*) là cây khung có tổng trọng số cạnh nhỏ nhất.

Gọi:

\[
W=\operatorname{weight}(\mathrm{MST}).
\]

### 4.1. Chứng minh W≤OPT

Lấy một tour TSP tối ưu trên n≥2 đỉnh. Nó đi qua tất cả các đỉnh và quay về điểm xuất phát.

**Bỏ một cạnh** khỏi chu trình ấy sẽ để lại một đường đi nối tất cả n đỉnh, tức một cây khung với n−1 cạnh.

Vì trọng số cạnh không âm, tổng trọng số của cây này **không lớn hơn** chi phí tour đã bỏ cạnh.

MST là cây khung nhẹ nhất, vì thế:

\[
\boxed{
W\le\operatorname{cost}(\text{tour bỏ một cạnh})
\le\operatorname{OPT}.
}
\]

Với n=1, theo quy ước chi phí MST và tour đều 0; kết luận vẫn đúng.

### 4.2. MST chưa phải tour TSP

MST chỉ có n−1 cạnh, có thể có nhiều lá hoặc đỉnh bậc lớn. Nó **không nhất thiết là một chu trình**.

Ví dụ một cây hình sao có nhiều lá: muốn đi từ lá này sang lá khác dọc theo cây phải đi qua tâm nhiều lần, vi phạm điều kiện tour TSP "thăm mỗi thành phố đúng một lần" theo thứ tự.

Do đó không thể chỉ xuất MST rồi tuyên bố đã giải TSP. Ta cần biến cây thành một hành trình kín, sau đó **shortcut** các lần thăm lặp.

### 4.3. MST là cận dưới chứ không phải đáp án

Nếu `W=10` và thuật toán tìm tour `C=18`, ta biết:

\[
10\le\operatorname{OPT}\le18.
\]

Nếu còn chứng minh 2-approx, ta có:

\[
18\le2\operatorname{OPT}.
\]

Thông tin này không cho biết OPT chính xác là 10, 14 hay 18 nếu chưa giải bài toán tối ưu.

---

## 5. Ý tưởng double-tree: nhân đôi các cạnh của MST

Từ MST có tổng trọng số W:

1. Nhân đôi **mỗi cạnh** của MST.
2. Nhận một **đa đồ thị** liên thông trong đó mỗi bậc đỉnh là số chẵn.
3. Đa đồ thị liên thông có mọi bậc chẵn có **chu trình Euler**.
4. Đi theo chu trình Euler; mỗi cạnh MST đã được nhân đôi nên tổng chi phí hành trình đúng:

\[
\boxed{2W}.
\]

Hành trình Euler đi qua các đỉnh có thể **nhiều lần**. Nhưng trong TSP ta chỉ muốn ghi một lần mỗi thành phố trước khi về điểm bắt đầu.

Ta cần **shortcut** để bỏ những lượt thăm lặp.

### 5.1. Thao tác shortcut

Giả sử trong hành trình có đoạn:

```text
a -> b -> c
```

nhưng b đã được ghé trước đó và ta không muốn ghi lại b.

Ta thay đoạn này bằng:

```text
a -> c
```

Bất đẳng thức tam giác:

\[
d(a,c)\le d(a,b)+d(b,c)
\]

đảm bảo đoạn mới **không đắt hơn** đoạn cũ.

Nếu phải bỏ liên tiếp nhiều đỉnh đã ghé, áp dụng bất đẳng thức tam giác lặp lại:

\[
d(a,z)\le
d(a,v_1)+d(v_1,v_2)+\cdots+d(v_k,z).
\]

Khi đồ thị đầy đủ, cạnh trực tiếp a–z luôn tồn tại.

### 5.2. Vì sao không thể làm điều đó với trọng số tùy ý?

Nếu:

\[
d(a,b)=1,\quad d(b,c)=1,\quad d(a,c)=100,
\]

đi qua b tốn 2, còn shortcut đi trực tiếp a→c tốn 100. **Chi phí tăng**, nên không có lập luận "shortcut không làm tăng chi phí".

Đây là lý do giả thiết **tam giác** là thiết yếu trong chứng minh.

---

## 6. Thuật toán MST preorder

Ta có thể cài phiên bản 2-approx **không cần xây rõ đa đồ thị nhân đôi và chu trình Euler**.

### 6.1. Mối liên hệ với DFS preorder

Chọn một gốc của MST, ví dụ thành phố 0. Duyệt cây bằng DFS và **ghi mỗi đỉnh ngay khi lần đầu gặp** (preorder).

Chuỗi thứ tự gặp đầu tiên:

\[
v_0=0,v_1,\ldots,v_{n-1}
\]

chứa **mỗi thành phố đúng một lần**.

Xuất tour:

\[
\boxed{
0\to v_1\to\cdots\to v_{n-1}\to0.
}
\]

Đường đi vòng quanh các cạnh cây theo DFS thực tế sẽ đi qua một số đỉnh nhiều lần. Nhưng nếu bỏ hết các lần ghé lặp trong hành trình đó, chuỗi còn lại đúng là **preorder**. Do shortcut không tăng chi phí:

\[
C_{\mathrm{preorder}}\le2W.
\]

### 6.2. Giả mã

```text
METRIC_TSP_2_APPROX(d):
    require complete, symmetric, nonnegative,
            d[i][i]=0, triangle inequality

    T = minimum_spanning_tree(d)

    preorder = DFS_PREORDER(T, root=0)

    tour = preorder + [0]

    return tour, tourCost(tour)
```

**Chú ý:** "require triangle inequality" là một **tiền điều kiện toán học** của bảo đảm xấp xỉ. Không phải cài đặt nào cũng kiểm tra hết ba chỉ số để xác thực điều kiện này, vì kiểm tra toàn bộ tam giác bằng cách ngây thơ tốn O(n³).

### 6.3. Vì sao DFS preorder tạo tour hợp lệ?

MST là một cây liên thông chứa đủ n thành phố. DFS trên cây từ gốc 0 gặp được tất cả đỉnh. Mỗi đỉnh được ghi đúng lúc lần đầu nên preorder không lặp. Thêm 0 ở cuối tạo một hành trình khép kín.

Vì bài đang xét **đồ thị đầy đủ**, mỗi cặp thành phố liên tiếp trong preorder đều có cạnh. Do đó chuỗi ấy tạo một tour hợp lệ.

### 6.4. Có thể chọn DFS hoặc BFS không?

Bảo đảm double-tree gắn với **thứ tự đi quanh cây** và việc shortcut từ **hành trình đi mỗi cạnh của cây hai lần**. DFS preorder có cấu trúc ấy.

Thứ tự BFS bất kỳ **không mặc nhiên** là shortcut của một hành trình đi đúng hai lần mỗi cạnh, nên không thể chuyển nguyên chứng minh 2W cho BFS tùy ý. Muốn khẳng định BFS cũng có một bảo đảm cụ thể, phải có chứng minh riêng.

---

## 7. Chứng minh tỉ lệ xấp xỉ 2

Gọi `T^*` là tour tối ưu và:

\[
\operatorname{OPT}=\operatorname{cost}(T^*).
\]

Gọi `W` là trọng số MST, `E` là hành trình Euler trên các cạnh MST nhân đôi, `H` là tour sau shortcut (hoặc preorder).

### Bước 1: MST không nặng hơn tour tối ưu

Bỏ một cạnh của T* để tạo cây khung, nên:

\[
\boxed{W\le\operatorname{OPT}.}
\]

### Bước 2: Nhân đôi MST cho hành trình có chi phí 2W

Trong đa đồ thị nhân đôi MST, mỗi cạnh có hai bản sao, tổng trọng số:

\[
\boxed{\operatorname{cost}(E)=2W.}
\]

Mọi bậc chẵn và đồ thị liên thông, nên chu trình Euler tồn tại.

### Bước 3: Shortcut không làm tăng chi phí

Với mọi lượt ghé một đỉnh đã xuất hiện trước đó, thay chuỗi nhiều chặng bằng cạnh trực tiếp. Nhờ bất đẳng thức tam giác:

\[
\boxed{\operatorname{cost}(H)\le\operatorname{cost}(E)=2W.}
\]

Bỏ lần lặp không làm mất thành phố nào vì lần đầu của mỗi thành phố vẫn được giữ. Đồ thị đầy đủ đảm bảo cạnh đi tắt tồn tại.

### Bước 4: Ghép hai cận

Từ W≤OPT:

\[
\boxed{
\operatorname{cost}(H)\le2W\le2\operatorname{OPT}.
}
\]

Đây là định lý 2-approx.

### 7.1. Những giả thiết dùng ở từng bước

| Bước | Giả thiết quan trọng |
| --- | --- |
| MST≤OPT | Tour qua tất cả đỉnh, cạnh không âm |
| Nhân đôi MST | Đồ thị vô hướng, cây liên thông |
| Có Euler tour | Đa đồ thị liên thông, mọi bậc chẵn |
| Shortcut không tăng | **Bất đẳng thức tam giác** |
| Shortcut vẫn có cạnh | **Đồ thị đầy đủ** / metric closure |
| Chi phí đi ngược như đi xuôi | **Đối xứng** |
| Tour hợp lệ | Giữ lần xuất hiện đầu của từng đỉnh rồi về gốc |

Không được bỏ bất đẳng thức tam giác hoặc đối xứng rồi lặp lại nguyên chứng minh.

### 7.2. Bảo đảm xấu nhất và kết quả thực tế

2-approx là bảo đảm **trên mọi instance hợp lệ**. Trong một instance cụ thể, tour có thể:

- Bằng OPT.
- Tốt hơn đáng kể so với cận 2×OPT.
- Gần cận trên trong một số cấu hình.

Không được viết "thuật toán luôn trả đúng gấp 2 OPT". **Bất đẳng thức** cho phép nó trả chính xác OPT hoặc bất kỳ giá trị nào ở giữa.

---

## 8. Ví dụ năm thành phố Manhattan: kết quả 18, tối ưu 14

Chọn năm thành phố (tọa độ nguyên):

| Thành phố | Tọa độ |
| ---: | --- |
| 0 | (0,0) |
| 1 | (2,0) |
| 2 | (4,0) |
| 3 | (1,3) |
| 4 | (3,3) |

Dùng khoảng cách Manhattan:

\[
d(i,j)=|x_i-x_j|+|y_i-y_j|.
\]

Ma trận:

\[
D=
\begin{bmatrix}
0&2&4&4&6\\
2&0&2&4&4\\
4&2&0&6&4\\
4&4&6&0&2\\
6&4&4&2&0
\end{bmatrix}.
\]

Ma trận đối xứng, không âm, đường chéo 0 và thỏa tam giác vì được dựng từ khoảng cách Manhattan.

### 8.1. Chọn MST bằng Prim từ đỉnh 0

Với cách giải quyết hòa là chọn đỉnh có ID nhỏ hơn và chỉ cập nhật khóa khi có cạnh **nhỏ hơn nghiêm ngặt**, Prim tìm cây:

```text
0
|-- 1 (trong so 2)
|   |-- 2 (trong so 2)
|
|-- 3 (trong so 4)
    |-- 4 (trong so 2)
```

Các cạnh:

| Cạnh cây | Trọng số |
| --- | ---: |
| 0–1 | 2 |
| 1–2 | 2 |
| 0–3 | 4 |
| 3–4 | 2 |
| **Tổng MST** | **10** |

Mảng cha theo ID:

```text
parent = [-1, 0, 1, 0, 3]
```

Nút 0 là gốc nên parent[0]=-1.

### 8.2. DFS preorder

Khi duyệt các con theo ID tăng dần:

```text
preorder = [0, 1, 2, 3, 4]
```

Tour:

```text
0 -> 1 -> 2 -> 3 -> 4 -> 0
```

Chi phí từng chặng:

\[
d(0,1)=2,
\]

\[
d(1,2)=2,
\]

\[
d(2,3)=6,
\]

\[
d(3,4)=2,
\]

\[
d(4,0)=6.
\]

Tổng:

\[
\boxed{C_{\mathrm{preorder}}=2+2+6+2+6=18.}
\]

### 8.3. Bảo đảm lý thuyết

Vì W=10:

\[
C_{\mathrm{preorder}}=18\le 2W=20.
\]

Để thấy OPT của ví dụ nhỏ, dùng oracle vét cạn; một tour tối ưu là:

```text
0 -> 1 -> 2 -> 4 -> 3 -> 0
```

Chi phí:

\[
2+2+4+2+4=\boxed{14}.
\]

Vét cạn mọi thứ tự thăm với điểm xuất phát cố định xác nhận:

\[
\boxed{\operatorname{OPT}=14.}
\]

Tỉ lệ thực tế:

\[
\frac{C_{\mathrm{preorder}}}{\operatorname{OPT}}
=\frac{18}{14}
=\frac97
\approx\boxed{1.285714}.
\]

Chuỗi bất đẳng thức:

\[
\boxed{18\le20\le28=2\cdot14}.
\]

Kết luận: thuật toán 2-approx **không nhất thiết đạt tối ưu** nhưng trong ví dụ này tốt hơn đáng kể so với cận xấu nhất.

### 8.4. Vì sao ví dụ này hữu ích?

Nó tránh hai cách hiểu sai:

- "Đã dùng MST thì tour luôn tối ưu" — **sai**, 18>14.
- "2-approx luôn trả đúng 2×OPT" — **sai**, 18<28.

Nó cũng minh họa việc một cạnh shortcut như 2→3 có trọng số 6, dù trên MST đường đi 2→1→0→3 có trọng số 2+2+4=8, nên cạnh trực tiếp **không đắt hơn** đường đi theo cây.

---

## 9. Phản ví dụ khi không có bất đẳng thức tam giác

Xét bốn thành phố với ma trận đối xứng:

\[
D=
\begin{bmatrix}
0&1&1&1\\
1&0&99&2\\
1&99&0&2\\
1&2&2&0
\end{bmatrix}.
\]

Ta có:

\[
d(1,2)=99>1+1=d(1,0)+d(0,2),
\]

nên **không phải metric**.

### 9.1. MST

Prim chọn cây hình sao:

```text
0--1 (1)
0--2 (1)
0--3 (1)
```

Do đó:

\[
\boxed{W=3}.
\]

### 9.2. Preorder từ gốc 0

Với thứ tự con [1,2,3]:

```text
0 -> 1 -> 2 -> 3 -> 0
```

Chi phí:

\[
1+99+2+1=\boxed{103}.
\]

Trong khi:

\[
2W=6.
\]

Bất đẳng thức:

\[
C_{\mathrm{preorder}}\le2W
\]

đã **thất bại**.

### 9.3. Tour tốt hơn rất nhiều

Một tour là:

```text
0 -> 1 -> 3 -> 2 -> 0
```

Chi phí:

\[
1+2+2+1=\boxed{6}.
\]

Oracle vét cạn xác nhận OPT=6. Tỉ lệ ở ví dụ này:

\[
\frac{103}{6}\approx17.1667,
\]

**lớn hơn 2** rất nhiều.

Nếu tăng trọng số d(1,2)=M mà giữ các cạnh khác, với M>2, preorder có chi phí M+4 trong khi vẫn có tour chi phí 6. Tỉ lệ có thể tăng **không bị chặn bởi một hằng số** khi M tăng. Đây là phản ví dụ rõ ràng cho việc áp dụng bảo đảm 2-approx ở TSP **không metric**.

### 9.4. Chỉ có đối xứng chưa đủ

Ma trận phản ví dụ vẫn đối xứng và không âm. Vì vậy chỉ kiểm tra:

```text
d[i][j] == d[j][i]
d[i][j] >= 0
```

không đủ để khẳng định metric; còn phải bảo đảm **tam giác**.

---

## 10. Java 17+: MST preorder, kiểm tra metric và oracle

Chương trình sau là ví dụ **độc lập có thể biên dịch/chạy**, tập trung vào tính đúng:

- Đầu vào là ma trận `long[][]`, đại diện chi phí nguyên không âm.
- Kiểm tra kích thước vuông, đường chéo 0, không âm và **đối xứng** ở mức O(n²).
- Cung cấp phép **kiểm tra tam giác riêng** O(n³) bằng `BigInteger` để tránh tràn khi cộng hai trọng số rất lớn.
- Dựng MST bằng **Prim O(n²)** trên ma trận đầy đủ, có xử lý cạnh trọng số `Long.MAX_VALUE` mà không dùng giá trị ấy làm sentinel "vô cực".
- Duyệt DFS preorder **dùng ngăn xếp**, tránh stack overflow khi cây rất sâu.
- Tạo tour khép kín và cộng trọng số bằng `BigInteger`, tránh tràn khi nhiều cạnh lớn.
- Cung cấp oracle TSP **vét cạn hàm mũ**, chỉ cho n≤10 để kiểm tra ví dụ nhỏ.
- Minh họa trường hợp một thành phố, hai thành phố, khoảng cách 0 giữa các thành phố khác nhau, trọng số cực đại, dữ liệu không metric, dữ liệu không đối xứng/âm.

**Tệp: `MetricTspApproximationDemo.java`**

```java
import java.math.BigInteger;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public final class MetricTspApproximationDemo {

    public record Result(
            int[] tour,
            int[] parent,
            BigInteger mstWeight,
            BigInteger tourCost) {
    }

    // O(n^2) structural validation; does NOT prove triangle inequality.
    public static void validateBasic(long[][] d) {
        if (d == null || d.length == 0) {
            throw new IllegalArgumentException(
                    "Need at least one city");
        }

        int n = d.length;

        for (int i = 0; i < n; i++) {
            if (d[i] == null || d[i].length != n) {
                throw new IllegalArgumentException(
                        "Distance matrix must be square");
            }
            if (d[i][i] != 0L) {
                throw new IllegalArgumentException(
                        "Diagonal distances must be zero");
            }
        }

        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                if (d[i][j] < 0L || d[j][i] < 0L) {
                    throw new IllegalArgumentException(
                            "Distances must be nonnegative");
                }

                if (d[i][j] != d[j][i]) {
                    throw new IllegalArgumentException(
                            "Distances must be symmetric");
                }
            }
        }
    }

    // Optional full metric audit: O(n^3) time, not part of
    // the O(n^2) approximation routine itself.
    public static void validateMetric(long[][] d) {
        validateBasic(d);

        int n = d.length;

        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                for (int k = 0; k < n; k++) {
                    BigInteger viaK =
                            BigInteger.valueOf(d[i][k])
                            .add(BigInteger.valueOf(d[k][j]));

                    if (BigInteger.valueOf(d[i][j])
                            .compareTo(viaK) > 0) {
                        throw new IllegalArgumentException(
                                "Triangle inequality violated");
                    }
                }
            }
        }
    }

    // 2-approximation IF the caller guarantees a symmetric
    // nonnegative metric. Basic structure is checked here;
    // the cubic triangle audit is deliberately not automatic.
    public static Result approximateAssumingMetric(long[][] d) {
        validateBasic(d);

        int n = d.length;
        boolean[] used = new boolean[n];
        boolean[] hasKey = new boolean[n];
        long[] key = new long[n];
        int[] parent = new int[n];

        Arrays.fill(parent, -1);
        hasKey[0] = true;
        key[0] = 0L;

        BigInteger mstWeight = BigInteger.ZERO;

        // Prim on a dense complete graph: O(n^2).
        for (int step = 0; step < n; step++) {
            int u = -1;

            for (int v = 0; v < n; v++) {
                if (!used[v] && hasKey[v]
                        && (u == -1 || key[v] < key[u])) {
                    u = v;
                }
            }

            if (u == -1) {
                throw new IllegalArgumentException(
                        "No spanning tree");
            }

            used[u] = true;

            if (u != 0) {
                mstWeight = mstWeight.add(
                        BigInteger.valueOf(key[u]));
            }

            for (int v = 0; v < n; v++) {
                if (!used[v]
                        && (!hasKey[v] || d[u][v] < key[v])) {
                    hasKey[v] = true;
                    key[v] = d[u][v];
                    parent[v] = u;
                }
            }
        }

        // Children are inserted in ascending vertex ID.
        List<List<Integer>> children = new ArrayList<>();

        for (int i = 0; i < n; i++) {
            children.add(new ArrayList<>());
        }

        for (int v = 1; v < n; v++) {
            children.get(parent[v]).add(v);
        }

        // Iterative DFS preorder; push children in reverse
        // so that smaller IDs are visited first.
        int[] preorder = new int[n];
        int visitedCount = 0;

        ArrayDeque<Integer> stack = new ArrayDeque<>();
        stack.push(0);

        while (!stack.isEmpty()) {
            int u = stack.pop();
            preorder[visitedCount++] = u;

            List<Integer> child = children.get(u);

            for (int i = child.size() - 1; i >= 0; i--) {
                stack.push(child.get(i));
            }
        }

        if (visitedCount != n) {
            throw new IllegalStateException(
                    "MST preorder did not visit all cities");
        }

        // Close the tour at city 0.
        int[] tour = Arrays.copyOf(preorder, n + 1);
        tour[n] = 0;

        BigInteger tourCost = BigInteger.ZERO;

        for (int i = 0; i < n; i++) {
            tourCost = tourCost.add(
                    BigInteger.valueOf(d[tour[i]][tour[i + 1]]));
        }

        return new Result(tour, parent, mstWeight, tourCost);
    }

    // Exponential exact oracle for SMALL inputs (n <= 10).
    // NOT part of the polynomial approximation algorithm.
    public static BigInteger bruteOptimal(long[][] d) {
        validateBasic(d);

        if (d.length > 10) {
            throw new IllegalArgumentException(
                    "Brute force is limited to 10 cities");
        }

        boolean[] visited = new boolean[d.length];
        visited[0] = true;

        BigInteger[] best = {null};

        search(d, visited, 0, 1, BigInteger.ZERO, best);

        return best[0];
    }

    private static void search(
            long[][] d,
            boolean[] visited,
            int last,
            int count,
            BigInteger partialCost,
            BigInteger[] best) {

        if (count == d.length) {
            BigInteger closed = partialCost.add(
                    BigInteger.valueOf(d[last][0]));

            if (best[0] == null
                    || closed.compareTo(best[0]) < 0) {
                best[0] = closed;
            }
            return;
        }

        // Safe pruning because every remaining edge >= 0.
        if (best[0] != null
                && partialCost.compareTo(best[0]) >= 0) {
            return;
        }

        for (int next = 1; next < d.length; next++) {
            if (!visited[next]) {
                visited[next] = true;

                search(
                        d,
                        visited,
                        next,
                        count + 1,
                        partialCost.add(
                                BigInteger.valueOf(d[last][next])),
                        best);

                visited[next] = false;
            }
        }
    }

    public static void main(String[] args) {
        long[][] metric = {
                {0, 2, 4, 4, 6},
                {2, 0, 2, 4, 4},
                {4, 2, 0, 6, 4},
                {4, 4, 6, 0, 2},
                {6, 4, 4, 2, 0}
        };

        validateMetric(metric);
        System.out.println("Metric valid: true");

        Result a = approximateAssumingMetric(metric);
        BigInteger optimal = bruteOptimal(metric);

        System.out.println(
                "MST parent: " + Arrays.toString(a.parent()));
        System.out.println(
                "MST weight: " + a.mstWeight());
        System.out.println(
                "Approx tour: " + Arrays.toString(a.tour()));
        System.out.println(
                "Approx cost: " + a.tourCost());
        System.out.println(
                "Exact optimum: " + optimal);

        double ratio = a.tourCost().doubleValue()
                / optimal.doubleValue();

        System.out.printf(
                Locale.ROOT,
                "Approx / optimum: %.6f%n",
                ratio);

        BigInteger doubleMst = a.mstWeight()
                .multiply(BigInteger.valueOf(2));

        System.out.println(
                "2*MST bound: " + doubleMst);

        boolean boundsHold =
                a.tourCost().compareTo(doubleMst) <= 0
                && a.mstWeight().compareTo(optimal) <= 0;

        System.out.println(
                "Both bounds hold: " + boundsHold);

        Result two = approximateAssumingMetric(
                new long[][] {
                        {0, 7},
                        {7, 0}
                });

        System.out.println(
                "Two-city tour: "
                        + Arrays.toString(two.tour()));
        System.out.println(
                "Two-city cost: " + two.tourCost());

        Result one = approximateAssumingMetric(
                new long[][] { {0} });

        System.out.println(
                "One-city tour: "
                        + Arrays.toString(one.tour()));
        System.out.println(
                "One-city cost: " + one.tourCost());

        long[][] zeroEdges = {
                {0, 0, 5},
                {0, 0, 5},
                {5, 5, 0}
        };

        validateMetric(zeroEdges);

        System.out.println("Zero-edge metric valid: true");
        System.out.println(
                "Zero-edge cost: "
                        + approximateAssumingMetric(
                                zeroEdges).tourCost());

        long huge = Long.MAX_VALUE;

        Result extreme = approximateAssumingMetric(
                new long[][] {
                        {0, huge},
                        {huge, 0}
                });

        System.out.println(
                "Long max cost: " + extreme.tourCost());

        long[][] nonmetric = {
                {0, 1, 1, 1},
                {1, 0, 99, 2},
                {1, 99, 0, 2},
                {1, 2, 2, 0}
        };

        boolean nonmetricRejected = false;

        try {
            validateMetric(nonmetric);
        } catch (IllegalArgumentException ex) {
            nonmetricRejected = true;
        }

        System.out.println(
                "Nonmetric rejected: " + nonmetricRejected);

        // For teaching only: run without the metric guarantee.
        System.out.println(
                "Nonmetric preorder cost: "
                        + approximateAssumingMetric(
                                nonmetric).tourCost());
        System.out.println(
                "Nonmetric optimum: " + bruteOptimal(nonmetric));

        boolean asymmetricRejected = false;

        try {
            approximateAssumingMetric(
                    new long[][] {
                            {0, 2},
                            {3, 0}
                    });
        } catch (IllegalArgumentException ex) {
            asymmetricRejected = true;
        }

        System.out.println(
                "Asymmetric rejected: " + asymmetricRejected);

        boolean negativeRejected = false;

        try {
            approximateAssumingMetric(
                    new long[][] {
                            {0, -1},
                            {-1, 0}
                    });
        } catch (IllegalArgumentException ex) {
            negativeRejected = true;
        }

        System.out.println(
                "Negative rejected: " + negativeRejected);
    }
}
```

### 10.1. Lệnh chạy

Yêu cầu JDK 17 trở lên:

```bash
javac MetricTspApproximationDemo.java
java MetricTspApproximationDemo
```

**Stdout kỳ vọng:**

```text
Metric valid: true
MST parent: [-1, 0, 1, 0, 3]
MST weight: 10
Approx tour: [0, 1, 2, 3, 4, 0]
Approx cost: 18
Exact optimum: 14
Approx / optimum: 1.285714
2*MST bound: 20
Both bounds hold: true
Two-city tour: [0, 1, 0]
Two-city cost: 14
One-city tour: [0, 0]
One-city cost: 0
Zero-edge metric valid: true
Zero-edge cost: 10
Long max cost: 18446744073709551614
Nonmetric rejected: true
Nonmetric preorder cost: 103
Nonmetric optimum: 6
Asymmetric rejected: true
Negative rejected: true
```

### 10.2. Phân biệt `validateBasic` và `validateMetric`

`validateBasic` kiểm tra:

- Ít nhất một thành phố.
- Ma trận vuông n×n.
- `d[i][i]=0`.
- Mọi trọng số không âm.
- Đối xứng `d[i][j]=d[j][i]`.

Chi phí kiểm tra là **O(n²)**.

`validateMetric` gọi kiểm tra cấu trúc rồi thử:

\[
d(i,j)\le d(i,k)+d(k,j)
\]

cho mọi bộ ba (i,j,k), nên chi phí **O(n³)**.

Hàm `approximateAssumingMetric` chủ ý **không tự động gọi kiểm tra tam giác O(n³)**, nhằm giữ thời gian chạy chính O(n²) khi đầu vào đã được biết chắc là metric (ví dụ được dựng từ Manhattan hoặc Euclid, hoặc từ shortest-path metric).

**Nếu cần xác minh một ma trận tùy ý**, hãy gọi `validateMetric` trước; toàn bộ quy trình khi ấy tốn O(n³) do bước xác minh, dù bản thân thuật toán MST-preorder vẫn O(n²).

### 10.3. Vì sao dùng `BigInteger`?

Nếu mỗi cạnh có trọng số `long` không âm, tổng n cạnh có thể vượt giới hạn:

\[
2^{63}-1.
\]

Ví dụ hai thành phố cách nhau `Long.MAX_VALUE`:

```text
0 -> 1 -> 0
```

chi phí:

\[
2(2^{63}-1)=
\boxed{18446744073709551614}.
\]

Giá trị ấy không vừa long có dấu. Mã giữ mỗi trọng số trong long nhưng **cộng tổng bằng BigInteger**.

Khi kiểm tra tam giác, việc viết trực tiếp:

```java
d[i][k] + d[k][j]
```

cũng có thể tràn long. Mã chuyển từng số sang BigInteger **trước phép cộng**.

### 10.4. Vì sao Prim dùng `hasKey[]`?

Một triển khai Prim thường khởi tạo:

```java
key[v] = Long.MAX_VALUE;
```

để biểu diễn vô cực. Nhưng trong bài này **cạnh thực sự có thể có trọng số Long.MAX_VALUE**. Nếu chỉ cập nhật khi `weight<key[v]`, một cạnh như vậy có thể bị bỏ qua nhầm.

Mã dùng:

```java
boolean[] hasKey;
long[] key;
```

để tách “chưa có ứng viên” khỏi “ứng viên có trọng số Long.MAX_VALUE”. Đây là kỹ thuật tổng quát giúp tránh sentinel trùng giá trị dữ liệu hợp lệ.

### 10.5. Vì sao duyệt DFS lặp?

MST có thể là một đường thẳng rất sâu. DFS đệ quy với n lớn có thể gây `StackOverflowError` ở Java.

Code dùng:

```java
ArrayDeque<Integer> stack
```

và đẩy con theo thứ tự ngược để khi pop nhận **thứ tự ID tăng dần**.

Vì các con được đưa vào danh sách theo thứ tự vertex ID từ nhỏ đến lớn, cách duyệt này cho đầu ra **xác định** trong ví dụ.

### 10.6. Cách giải quyết hòa trong Prim

Khi có nhiều ứng viên MST cùng trọng số, code:

- Chọn đỉnh nhỏ nhất theo ID khi khóa bằng nhau (do vòng quét tăng dần và chỉ thay khi nhỏ hơn nghiêm ngặt).
- Cập nhật `parent[v]` khi cạnh mới **nhỏ hơn** khóa hiện tại, không cập nhật khi bằng nhau.

Do đó mảng cha và preorder trong ví dụ được xác định. Một thuật toán Prim khác có thể chọn MST khác và tour khác nhưng **vẫn đúng**, miễn tuân các bất biến và điều kiện metric.

### 10.7. Oracle vét cạn tách biệt thuật toán xấp xỉ

`bruteOptimal` có độ phức tạp hàm mũ/giai thừa theo số thành phố, bị giới hạn n≤10. Nó chỉ dùng để biết OPT của các ví dụ nhỏ và kiểm chứng:

\[
C_{\mathrm{alg}}\le2\operatorname{OPT}.
\]

Với n lớn, không nên gọi oracle này để “đảm bảo 2-approx”, vì chứng minh toán học đã cho bảo đảm mà **không cần biết OPT**.

### 10.8. Quy ước n=1 và n=2

Theo định nghĩa chu trình Hamilton đơn trong lý thuyết đồ thị, các trường hợp n<3 có thể được xem là suy biến. Mã dùng quy ước **hành trình khép kín**:

- n=1: `[0,0]`, chi phí 0.
- n=2: `[0,1,0]`, phải đi từ 0 tới 1 rồi quay lại 0.

Quy ước này thuận tiện cho bài toán người du lịch ở dạng thăm thành phố và quay về điểm xuất phát; không nên nhầm với chu trình đơn tối thiểu ba đỉnh trong một số định nghĩa lý thuyết đồ thị.

---

## 11. Phân tích độ phức tạp

Giả sử ma trận d có n hàng và n cột, được cung cấp sẵn và đã biết thỏa metric.

### 11.1. Prim trên đồ thị đầy đủ

Mỗi trong n bước:

- Quét n đỉnh để chọn ứng viên nhẹ nhất.
- Quét n đỉnh để cập nhật khóa.

Chi phí:

\[
\boxed{O(n^2)}.
\]

Không cần hàng đợi ưu tiên cho đồ thị đầy đủ biểu diễn bằng ma trận; Prim O(n²) thường đơn giản và phù hợp.

### 11.2. Duyệt MST

Cây có n−1 cạnh. Dựng danh sách con và DFS preorder:

\[
\boxed{O(n)}.
\]

### 11.3. Tính chi phí tour

Tour chứa n cạnh nếu tính cả chặng quay về gốc (theo quy ước n≥2). Cộng n trọng số:

\[
\boxed{O(n)}
\]

phép cộng số nguyên theo mô hình chi phí đơn vị; dùng BigInteger để tránh tràn số tổng.

### 11.4. Tổng thời gian

Nếu không tính lần kiểm chứng tam giác vì đã biết tiền điều kiện:

\[
\boxed{T(n)=O(n^2).}
\]

Khi gọi `validateMetric` để kiểm tra mọi bộ ba:

\[
\boxed{T_{\mathrm{with\ audit}}(n)=O(n^3).}
\]

Phải nói rõ hai trường hợp, không vừa thực hiện triple-loop O(n³) lại vừa tuyên bố cả chương trình chỉ O(n²).

### 11.5. Bộ nhớ

- Ma trận khoảng cách đầu vào: **O(n²)** ô.
- `used`, `hasKey`, `key`, `parent`, danh sách con, stack DFS, preorder, tour: **O(n)** tổng bộ nhớ phụ.
- `BigInteger` cho tổng có nhiều hơn 64 bit khi n lớn, nhưng với n trọng số long, độ dài kết quả chỉ tăng cỡ O(log n) bit, không thay đổi kết luận O(n) cho các mảng phụ trong mô hình thường dùng.

Vì vậy:

\[
\boxed{
\text{Bộ nhớ phụ của MST-preorder}=O(n)
}
\]

**ngoài ma trận O(n²) được cung cấp**.

Oracle vét cạn có stack và `visited` O(n), nhưng **thời gian hàm mũ** và chỉ dùng n nhỏ.

---

## 12. Christofides: mở rộng với tỉ lệ 3/2

Thuật toán double-tree đạt bảo đảm 2. Với **symmetric metric TSP**, thuật toán **Christofides** (Christofides–Serdyukov) cải thiện cận lên:

\[
\boxed{
C_{\mathrm{Christofides}}\le\frac32\operatorname{OPT}.
}
\]

Ý tưởng vẫn xuất phát từ MST, nhưng thay vì **nhân đôi toàn bộ cạnh cây**, ta chỉ thêm những cạnh cần thiết để mọi đỉnh có bậc chẵn.

### 12.1. Bước 1: Xây MST

Tìm MST T với trọng số W:

\[
W\le\operatorname{OPT}.
\]

### 12.2. Bước 2: Lấy các đỉnh bậc lẻ

Gọi U là tập các đỉnh bậc lẻ của T.

Theo định lý bắt tay:

\[
\sum_{v\in V}\deg(v)=2|E|,
\]

nên số đỉnh bậc lẻ luôn **chẵn**.

### 12.3. Bước 3: Ghép cặp trọng số nhỏ nhất

Tìm **minimum-weight perfect matching** M trên tập U, với khoảng cách d của metric.

Matching ghép mỗi đỉnh trong U vào đúng một cạnh. Sau khi thêm các cạnh M vào T:

- Đỉnh bậc lẻ của T tăng bậc thêm 1 ⇒ bậc chẵn.
- Đỉnh vốn chẵn không bị thêm cạnh matching ⇒ giữ bậc chẵn.

Kết quả là một đa đồ thị liên thông, mọi đỉnh bậc chẵn.

**Lưu ý quan trọng:** tìm **minimum-weight perfect matching** trong đồ thị tổng quát không đồng nghĩa với ghép tham lam các cặp gần nhau nhất. Dùng matching tham lam tùy ý có thể phá bảo đảm 3/2.

### 12.4. Bước 4: Euler và shortcut

Tìm chu trình Euler trên đa đồ thị T∪M. Chi phí:

\[
W+w(M).
\]

Shortcut các đỉnh lặp nhờ tam giác để nhận tour TSP có chi phí:

\[
C\le W+w(M).
\]

### 12.5. Vì sao matching không vượt OPT/2?

Xét tour tối ưu T*. Giữ các đỉnh thuộc U theo thứ tự xuất hiện trên T*, bỏ qua đỉnh không thuộc U bằng shortcut. Ta nhận một chu trình qua tất cả đỉnh của U có tổng chi phí **không vượt OPT**.

Vì |U| chẵn, các cạnh của chu trình này có thể chia thành **hai perfect matchings xen kẽ** trên U.

Tổng chi phí hai matching đó đúng bằng chi phí chu trình trên U. Do đó ít nhất một matching có chi phí:

\[
\le\frac{\operatorname{OPT}}2.
\]

M là **matching nhỏ nhất** trên U, nên:

\[
\boxed{w(M)\le\frac{\operatorname{OPT}}2.}
\]

### 12.6. Ghép cận 3/2

\[
C\le W+w(M)
\le\operatorname{OPT}
+\frac{\operatorname{OPT}}2
=\boxed{\frac32\operatorname{OPT}}.
\]

Đây là cận xấp xỉ **1.5**.

### 12.7. Chi phí cài đặt

Christofides là thuật toán đa thức nếu dùng thuật toán minimum-weight perfect matching tổng quát đúng, nhưng phần matching phức tạp hơn Prim/DFS rất nhiều. Vì vậy bài này cung cấp **mã chạy hoàn chỉnh cho 2-approx**, còn Christofides được trình bày như **mở rộng lý thuyết với chứng minh cận**.

Không nên nói chỉ cần “MST + ghép mỗi đỉnh lẻ với hàng xóm gần nhất” là tự có 1.5-approx.

### 12.8. Giới hạn của kết quả

Cả 2-approx double-tree và 1.5-approx Christofides ở đây dùng giả thiết **đồ thị đầy đủ, không âm, đối xứng, thỏa tam giác**.

Kết quả này không chuyển nguyên vẹn sang **asymmetric TSP** hoặc TSP tùy ý không thỏa tam giác.

---

## 13. Thuật toán xấp xỉ và heuristic có gì khác?

### 13.1. Thuật toán xấp xỉ

Một thuật toán có bảo đảm tỉ lệ ρ nếu đã có chứng minh:

\[
C_{\mathrm{alg}}\le\rho\,\operatorname{OPT}
\]

trên mọi input hợp lệ của lớp đang xét.

Ví dụ:

- MST preorder: 2-approx cho symmetric metric TSP.
- Christofides: 3/2-approx cho symmetric metric TSP.

### 13.2. Nearest neighbor

Heuristic **láng giềng gần nhất**:

1. Bắt đầu từ 0.
2. Chọn thành phố chưa thăm có khoảng cách nhỏ nhất từ thành phố hiện tại.
3. Lặp tới khi thăm đủ.
4. Quay về 0.

Dễ cài, thường nhanh, nhưng **không tự có bảo đảm 2-approx** chỉ vì đang dùng metric. Muốn nói cận nào, phải dựa vào phân tích riêng của heuristic đó.

### 13.3. 2-opt

2-opt là heuristic cải thiện tour bằng cách thay hai cạnh bằng hai cạnh khác tương ứng với việc đảo một đoạn thứ tự tour. Nếu thay đổi làm giảm chi phí thì áp dụng và lặp.

2-opt thường cải thiện lời giải ban đầu trong thực nghiệm, nhưng **bản thân thao tác tìm tour tốt hơn cục bộ không chứng minh bảo đảm 2 lần** nếu ta bắt đầu từ một tour tùy ý.

### 13.4. Kết hợp có bảo đảm và heuristic

Một chiến lược thực tế:

1. Chạy **MST preorder** để có tour H với `C(H)≤2OPT`.
2. Chạy **2-opt chỉ chấp nhận thay đổi không làm tăng chi phí**.
3. Trả tour được cải thiện H'.

Khi đó:

\[
C(H')\le C(H)\le2\operatorname{OPT}.
\]

Vì heuristic chỉ **giảm hoặc giữ nguyên chi phí**, bảo đảm 2-approx của tour khởi tạo **được giữ nguyên**.

Nếu heuristic sau đó có thể làm tour tệ hơn, ta phải giữ lại lời giải tốt nhất hoặc chứng minh lại cận.

### 13.5. Đo chất lượng thực nghiệm

Với n nhỏ biết OPT:

\[
\text{tỉ lệ thực nghiệm}
=
\frac{C_{\mathrm{alg}}}{\operatorname{OPT}}.
\]

Với n lớn không biết OPT, có thể báo:

- Chi phí tour.
- Chi phí MST W là **cận dưới**.
- Tỉ lệ `C_{\mathrm{alg}}/W`, nếu W>0, là một **cận trên có thể tính được cho tỉ lệ thực tế** vì `W≤OPT`.
- Thời gian chạy.
- Thống kê trên nhiều bộ dữ liệu, nhiều seed nếu có ngẫu nhiên.

Không được gọi `C/W` là "tỉ lệ với OPT chính xác", vì W thường nhỏ hơn OPT.

---

## 14. Trường hợp biên và lưu ý triển khai

### 14.1. Một hoặc hai thành phố

Với n=1, mã demo trả hành trình `[0,0]` chi phí 0.

Với n=2, khoảng cách hai chiều d(0,1)=d(1,0)=7, tour `[0,1,0]` có chi phí 14.

Đây là **quy ước hành trình khép kín** trong TSP, không nhất thiết là chu trình Hamilton đơn theo định nghĩa đồ thị thường yêu cầu ít nhất ba đỉnh.

### 14.2. Khoảng cách bằng 0 giữa hai thành phố khác nhau

Ví dụ:

\[
D=
\begin{bmatrix}
0&0&5\\
0&0&5\\
5&5&0
\end{bmatrix}.
\]

Ma trận vẫn có tính không âm, đối xứng, đường chéo 0 và tam giác. MST có tổng 5; tour 0→1→2→0 chi phí 10. Cận:

\[
10\le2\cdot5.
\]

Không được **gộp hai thành phố** chỉ vì khoảng cách giữa chúng bằng 0 nếu bài toán yêu cầu thăm từng ID.

### 14.3. Nhiều MST đồng hạng

Khi có nhiều cây khung nhỏ nhất, Prim có thể tìm một trong số đó. Tour preorder phụ thuộc:

- Cây MST được chọn.
- Gốc.
- Thứ tự duyệt các con.

Các tour có thể khác nhau về chi phí nhưng vẫn **đạt cận 2** nếu giải đúng và input metric.

### 14.4. Trọng số lớn

Với `long`, cộng n cạnh vào một `long` có thể tràn. Dùng `BigInteger` cho tổng chi phí.

Cần phân biệt **so sánh cạnh đơn** trong Prim (long đủ vì từng trọng số là long) và **tổng cả tour** (có thể lớn hơn long).

### 14.5. Dữ liệu đối xứng nhưng không thỏa tam giác

`validateBasic` có thể chấp nhận, nhưng bảo đảm xấp xỉ **không áp dụng**. Nếu đầu vào bất kỳ, cần xác minh tam giác hoặc có chứng minh nó xuất phát từ một hàm khoảng cách metric.

### 14.6. Dữ liệu Euclid double

Nếu tính khoảng cách Euclid từ tọa độ double, có sai số làm tròn; các bất đẳng thức tam giác toán học vẫn đúng nhưng việc kiểm tra từng phép so sánh trên máy có thể bị ảnh hưởng ở những trường hợp rất sát ngưỡng.

Mã demo dùng trọng số long và BigInteger trong kiểm toán tam giác để có ví dụ xác định. Với dữ liệu double, cần chính sách tolerance và số học ổn định thích hợp — không được tự làm tròn thành long nếu thay đổi bài toán.

### 14.7. Đồ thị không đầy đủ

Không thể shortcut từ a sang c nếu cạnh trực tiếp không tồn tại. Một cách tiếp cận là làm việc trên **metric closure** của mạng đường vô hướng liên thông, nơi d(u,v) là đường đi ngắn nhất và mọi cặp có khoảng cách. Nhưng cần quản lý việc mở rộng các cạnh metric thành đường đi thực tế; đoạn đường vật lý có thể đi qua những thành phố trung gian.

### 14.8. Đồ thị có hướng

Đối với TSP bất đối xứng, chu trình Euler của cây vô hướng nhân đôi không tương thích cách tính chi phí các cung có hướng. Không được dùng kết quả 2-approx này cho ATSP nếu chưa có thuật toán và chứng minh riêng.

---

## 15. Những lỗi phổ biến

1. **Áp 2-approx cho mọi TSP**, quên điều kiện metric.
2. **Chỉ kiểm tra không âm/đối xứng**, bỏ bất đẳng thức tam giác.
3. **Áp cho đồ thị không đầy đủ** mà không xử lý metric closure.
4. **Áp cho TSP có hướng** mà không chứng minh riêng.
5. **Nói MST là tour**, trong khi nó chỉ là cây.
6. **Duyệt preorder rồi quên trở về gốc**, tạo đường đi chứ không phải chu trình.
7. **Thăm lặp thành phố trong tour cuối**, không shortcut.
8. **Bỏ lần xuất hiện đầu của một đỉnh**, khiến tour thiếu thành phố.
9. **Dùng thứ tự BFS tùy ý** rồi khẳng định 2-approx từ chứng minh DFS double-tree.
10. **Nói shortcut luôn không tăng chi phí**, quên tam giác.
11. **Cho rằng W=MST=OPT**, sai vì MST chỉ là cận dưới.
12. **Cho rằng tour thuật toán luôn có chi phí đúng 2W**, trong khi shortcut có thể giảm.
13. **Cho rằng 2-approx luôn có chi phí đúng 2OPT**, nhầm cận với đẳng thức.
14. **Không chứng minh cả hai cận `C≤2W` và `W≤OPT`**.
15. **Quên độ dài input là số bit**, nhất là khi trọng số lớn.
16. **Dùng tổng long cho nhiều cạnh**, dẫn đến overflow.
17. **Dùng Long.MAX_VALUE làm sentinel key chưa có**, bỏ sót cạnh hợp lệ có đúng trọng số đó.
18. **Dùng DFS đệ quy với MST sâu**, có thể StackOverflowError.
19. **Nhầm O(n²) của Prim với O(n³) của kiểm toán tam giác**, báo sai thời gian cả pipeline.
20. **Dùng oracle vét cạn để gọi là thuật toán xấp xỉ đa thức**, trong khi oracle chỉ để test.
21. **Thấy cùng đầu ra trên vài test rồi coi là chứng minh 2-approx**, thử nghiệm không thay chứng minh.
22. **Không xử lý tie deterministically khi muốn stdout cố định**, làm test dễ sai giả.
23. **Bỏ tình huống một hoặc hai thành phố**, gây lỗi index/định nghĩa.
24. **Gộp thành phố khi khoảng cách giữa chúng bằng 0**, thay đổi số lần phải ghé.
25. **Nói Christofides dùng greedy matching**, sai với yêu cầu perfect matching trọng số nhỏ nhất.
26. **Nói Christofides 1.5 áp cho asymmetric TSP**, không đúng phạm vi.
27. **Không kiểm tra tính hợp lệ của tour đầu ra**, có thể thiếu hoặc trùng ID.
28. **So kết quả tour từng ID với oracle dù có nhiều tour tối ưu đồng hạng**, nên so chi phí/cấu trúc.
29. **Cho rằng 2-opt tự sinh bảo đảm 2-approx từ tour bất kỳ**, không được suy ra.
30. **Đo chất lượng bằng C/MST rồi gọi đó là C/OPT**, hai đại lượng khác nhau.
31. **Quên đường đi ngắn nhất trong metric closure có thể đi qua đỉnh trung gian**, nhầm lộ trình metric và lộ trình vật lý.
32. **Thực hiện shortcut bằng cách cộng khoảng cách qua đỉnh đã bỏ**, thay vì dùng cạnh trực tiếp d(a,c) của metric.
33. **Không kiểm tra tam giác đúng chiều `d(a,c)≤d(a,b)+d(b,c)`**, đảo bất đẳng thức.
34. **Quên đối xứng khi tính Euler tree traversal**, chiều quay về có thể có chi phí khác.
35. **Tin rằng thuật toán 2-approx đã giải được TSP tối ưu**, mặc dù có ví dụ 18>14.

---

## 16. Kiểm thử độc lập và các bất biến

### 16.1. Tour hợp lệ

Với n≥2, một tour hợp lệ dạng mảng độ dài n+1 phải:

1. Có `tour[0]=0`.
2. Có `tour[n]=0`.
3. `tour[0..n-1]` là hoán vị của `0..n-1`.
4. Không có ID ngoài phạm vi.
5. Chi phí tính từ các cạnh liên tiếp khớp giá trị báo.

Với n=1, quy ước `[0,0]`, chi phí0.

### 16.2. MST hợp lệ

Mảng `parent` phải mô tả cây:

- parent[0]=-1.
- Mỗi v≠0 có đúng một cha trong 0..n−1.
- Không có chu trình trong các cạnh cha.
- Từ gốc0 có thể đến mọi đỉnh.
- Tổng trọng số cạnh cha bằng `mstWeight`.

Với n nhỏ, có thể so trọng số Prim với Kruskal để phát hiện bug MST; hai cây có thể khác nhau khi có cạnh hòa nhưng **trọng số tối ưu bằng nhau**.

### 16.3. Bất đẳng thức kiểm thử

Trên input metric:

\[
\boxed{
W\le OPT\le C_{\mathrm{alg}}\le2W\le2OPT.
}
\]

Trong thực tế, `OPT≤C_{\mathrm{alg}}` đúng vì C_alg là một tour hợp lệ; hai cận chính của chứng minh là `W≤OPT` và `C_alg≤2W`.

Nếu dùng oracle chính xác cho n nhỏ, hãy kiểm tra tất cả các bất đẳng thức ấy.

### 16.4. Oracle vét cạn

Với n≤10, đặt gốc0 và duyệt mọi hoán vị của các thành phố 1..n−1. Với mỗi tour, cộng chi phí các cạnh và cạnh về0, lấy nhỏ nhất.

Khi n lớn, việc thử mọi hoán vị là không thực tế, nhưng chứng minh 2-approx vẫn áp dụng.

### 16.5. Các bộ test định hướng

| Dữ liệu | Kỳ vọng |
| --- | --- |
| Ma trận Manhattan 5 thành phố ở mục 8 | MST10, tour18, OPT14 |
| Hai thành phố cách nhau7 | Tour `[0,1,0]`, chi phí14 |
| Một thành phố | `[0,0]`, chi phí0 |
| Ba đỉnh có cạnh 0 giữa hai ID | Metric hợp lệ, tour chi phí10 |
| Hai thành phố cách nhau `Long.MAX_VALUE` | Tour `2×Long.MAX_VALUE` dưới dạng BigInteger |
| Ma trận không metric mục 9 | Kiểm tra tam giác thất bại; preorder103, OPT6 |
| Ma trận không đối xứng | Từ chối đầu vào |
| Trọng số âm | Từ chối đầu vào |
| Ma trận không vuông | Từ chối đầu vào |
| Đường chéo khác0 | Từ chối đầu vào |
| Có nhiều cạnh cùng trọng số | Tour có thể khác về thứ tự nhưng vẫn hợp lệ và đạt cận |
| Nhiều thành phố trùng tọa độ | Các ID vẫn xuất hiện đúng một lần |

### 16.6. Sinh ngẫu nhiên metric hợp lệ

Thay vì sinh ma trận ngẫu nhiên tùy ý (có thể vi phạm tam giác), hãy:

1. Sinh n điểm 2D nguyên, chẳng hạn tọa độ trong [−10,10].
2. Đặt:
   \[
   d(i,j)=|x_i-x_j|+|y_i-y_j|.
   \]
3. Dựng MST và tour preorder.
4. Kiểm tra tour hợp lệ.
5. Kiểm tra `C≤2W`.
6. Với n≤8, dùng oracle vét cạn để kiểm tra `W≤OPT≤C≤2OPT`.
7. Cho phép điểm trùng tọa độ để kiểm thử trọng số 0.
8. Thử nhiều seed cố định để tái hiện lỗi.

Mô hình Prim–preorder và oracle độc lập đã được đối chiếu trên **1.500 bộ dữ liệu Manhattan ngẫu nhiên** với n từ 2 đến 7; trong mỗi trường hợp, tour là hoán vị hợp lệ và các cận `C≤2W`, `W≤OPT`, `C≤2OPT` đều đạt.

**Quan trọng:** kiểm thử ngẫu nhiên hỗ trợ kiểm tra cài đặt. Nó **không thay thế** chứng minh lý thuyết cho mọi metric input.

### 16.7. Test phá giả thiết

Cố ý tạo ma trận `d(1,2)=99`, còn `d(1,0)=d(0,2)=1`. `validateMetric` phải từ chối.

Nếu cố chạy `approximateAssumingMetric` trên dữ liệu này, nó có thể xuất tour nhưng không còn bảo đảm. Ở ví dụ mục 9, chi phí tour103, OPT6. Đây là test tốt để xác nhận phạm vi áp dụng đã được giải thích rõ.

### 16.8. Test số nguyên cực lớn

Với n=2 và d=Long.MAX_VALUE:

- Prim phải **không** nhầm cạnh hợp lệ với khóa vô cực.
- `mstWeight=9223372036854775807`.
- `tourCost=18446744073709551614`.

Đây là test trực tiếp cho `hasKey[]` và BigInteger.

---

## 17. Câu hỏi thường nhầm

### “Nếu tôi có MST, tại sao không luôn tìm được tour tối ưu?”

MST chỉ là cận dưới và không phải chu trình. Thứ tự preorder có thể buộc dùng những cạnh shortcut chưa tối ưu. Ví dụ n=5, MST10 nhưng tour preorder18, còn OPT14.

### “Tôi có cần nhân đôi cạnh cây trong code?”

Không cần nếu dùng DFS preorder: nó tạo đúng thứ tự những lần gặp đầu tiên từ một hành trình đi quanh cây và áp dụng shortcut. Việc nhân đôi cạnh là **công cụ chứng minh**; preorder là một cách cài đơn giản.

### “Shortcut nghĩa là bỏ qua thành phố chưa thăm?”

**Không.** Chỉ bỏ **lượt xuất hiện lặp**, giữ **lần xuất hiện đầu của mỗi thành phố**. Tour cuối phải thăm đủ n ID.

### “Nếu đồ thị chỉ có đường đi gián tiếp, có thể áp dụng không?”

Có thể áp dụng trên **metric closure** của đồ thị vô hướng liên thông không âm, dùng khoảng cách đường đi ngắn nhất giữa mỗi cặp. Cần phân biệt hành trình metric với lộ trình vật lý triển khai.

### “Nếu trọng số đối xứng và không âm, có đủ cho 2-approx chưa?”

**Chưa.** Phải có bất đẳng thức tam giác. Phản ví dụ bốn đỉnh cho tour103 trong khi OPT6.

### “Christofides có phải chỉ đổi DFS sang BFS?”

**Không.** Christofides bổ sung một **minimum-weight perfect matching trên các đỉnh bậc lẻ của MST** rồi tìm Euler tour, shortcut. BFS không thay thế bước matching.

### “Nếu chạy 2-opt từ tour MST và nó luôn giảm chi phí, mất bảo đảm 2-approx không?”

**Không.** Vì tour mới không đắt hơn tour đã có bảo đảm, cận vẫn được giữ. Nhưng 2-opt không tự cung cấp cận ấy nếu xuất phát từ tour tùy ý.

### “Có thể khẳng định không bao giờ tìm được TSP tối ưu trong thời gian đa thức không?”

Không. Điều đó liên quan các câu hỏi độ phức tạp chưa giải quyết. Ta có thể nói TSP quyết định tổng quát là NP-complete, chưa biết thuật toán đa thức tối ưu cho mọi trường hợp, và có những thuật toán xấp xỉ đa thức khi bổ sung giả thiết metric.

---

## 18. Bài tập tự kiểm tra

### Bài 1
Phát biểu bài toán TSP tối ưu và điều kiện một tour hợp lệ.

### Bài 2
Nêu bốn giả thiết quan trọng của symmetric metric TSP.

### Bài 3
Viết bất đẳng thức tam giác và giải thích ý nghĩa khi shortcut.

### Bài 4
Tại sao đồ thị không đầy đủ gây khó cho việc shortcut?

### Bài 5
Giải thích vì sao MST là cận dưới của tour tối ưu.

### Bài 6
Tại sao MST chưa phải tour TSP?

### Bài 7
Nhân đôi tất cả cạnh MST tạo đồ thị có tính chất bậc đỉnh gì?

### Bài 8
Giải thích vì sao đồ thị MST nhân đôi có Euler tour.

### Bài 9
Vì sao chi phí Euler tour bằng 2W?

### Bài 10
Trình bày các bước MST preorder.

### Bài 11
Vì sao preorder chứa mỗi thành phố đúng một lần?

### Bài 12
Viết hai bất đẳng thức dẫn tới `C≤2OPT`.

### Bài 13
2-approx có nghĩa tour luôn có chi phí đúng 2OPT không?

### Bài 14
Với ma trận Manhattan năm thành phố ở mục 8, tổng MST bằng bao nhiêu?

### Bài 15
Với cùng dữ liệu, tour preorder và chi phí của nó là gì?

### Bài 16
Nêu một tour tối ưu của ví dụ năm thành phố và chi phí.

### Bài 17
Tính tỉ lệ thực nghiệm của tour18 với OPT14.

### Bài 18
Với d(1,2)=99, d(1,0)=d(0,2)=1, giả thiết nào bị vi phạm?

### Bài 19
Với ma trận không metric mục 9, tour preorder và tour tốt có chi phí gì?

### Bài 20
Nếu có n=2 thành phố cách nhau7, tour và chi phí là gì?

### Bài 21
Vì sao cần BigInteger để cộng tour từ các cạnh kiểu long?

### Bài 22
Vì sao không nên dùng Long.MAX_VALUE làm sentinel "chưa có khóa" trong Prim?

### Bài 23
Phân biệt thời gian Prim O(n²) và kiểm tra mọi tam giác O(n³).

### Bài 24
Christofides chọn tập U như thế nào?

### Bài 25
Vì sao số đỉnh bậc lẻ trong cây luôn chẵn?

### Bài 26
Thành phần nào của Christofides phải được tối ưu thật sự, không chỉ tham lam?

### Bài 27
Viết cận trên chi phí matching trong Christofides.

### Bài 28
Từ MST+matching, suy ra bảo đảm 3/2 như thế nào?

### Bài 29
Nếu cải thiện tour 2-approx bằng 2-opt chỉ giảm chi phí, bảo đảm còn giữ không?

### Bài 30
Tại sao cực đại tỉ lệ trong vài nghìn test không phải chứng minh bảo đảm xấu nhất?

### Bài 31
Vì sao metric closure từ đường đi ngắn nhất trên đồ thị vô hướng liên thông không âm thỏa tam giác?

### Bài 32
Nếu W=0, có nên tính `C/W` để ước lượng chất lượng không?

### Đáp án gợi ý

1. Chọn thứ tự thăm mọi thành phố đúng một lần rồi về gốc, sao cho tổng chi phí nhỏ nhất.
2. Đồ thị đầy đủ, trọng số không âm, đối xứng, bất đẳng thức tam giác; thường thêm `d(i,i)=0`.
3. `d(a,c)≤d(a,b)+d(b,c)`; bỏ điểm trung gian không làm tăng tổng chi phí.
4. Có thể không tồn tại cạnh trực tiếp nối hai thành phố sau shortcut.
5. Bỏ một cạnh khỏi tour tối ưu tạo cây khung; MST nhẹ nhất nên `W≤OPT`.
6. Nó là cây không có chu trình, chưa phải hành trình thăm mọi thành phố rồi quay về.
7. Mỗi đỉnh có bậc chẵn vì bậc trong cây được nhân đôi.
8. Liên thông và mọi bậc chẵn nên có chu trình Euler.
9. Mỗi cạnh MST được đi đúng hai lần, tổng là 2W.
10. Tìm MST, chọn gốc0, DFS preorder, nối các thành phố theo thứ tự xuất hiện đầu, quay về0.
11. DFS trên cây liên thông gặp tất cả và ghi mỗi đỉnh lúc gặp đầu tiên.
12. `C≤2W` do shortcut, `W≤OPT` do cận dưới ⇒ `C≤2OPT`.
13. Không, chi phí có thể bằng OPT hoặc nằm giữa OPT và 2OPT.
14. `W=10`.
15. `0→1→2→3→4→0`, `C=18`.
16. `0→1→2→4→3→0`, `OPT=14`.
17. `18/14=9/7≈1.285714`.
18. Bất đẳng thức tam giác vì 99>1+1.
19. Preorder103, tour tốt và OPT6.
20. `0→1→0`, chi phí14.
21. Tổng n trọng số long có thể vượt Long.MAX_VALUE.
22. Cạnh hợp lệ cũng có thể nặng đúng Long.MAX_VALUE, sẽ bị nhầm với vô cực.
23. Prim quét n đỉnh qua n vòng; kiểm toán triple-loop có n³ bộ ba.
24. U là tập các đỉnh có bậc lẻ trong MST.
25. Tổng bậc bằng 2|E| chẵn, nên số bậc lẻ phải chẵn.
26. **Minimum-weight perfect matching** trên U.
27. `w(M)≤OPT/2`.
28. `C≤W+w(M)≤OPT+OPT/2=3OPT/2`.
29. Có, `C_{\mathrm{new}}≤C_{\mathrm{old}}≤2OPT`.
30. Test chỉ xét một tập hữu hạn, không thay chứng minh cho mọi instance.
31. Đường đi ngắn nhất u→w không dài hơn đường ghép u→v và v→w; đồ thị vô hướng làm khoảng cách đối xứng.
32. Không; chia cho 0 không xác định. Dùng bất đẳng thức chi phí `C≤2OPT` thay cho tỉ số.

---

## Ghi nhớ

Trong **symmetric metric TSP**:

\[
\boxed{d(u,w)\le d(u,v)+d(v,w).}
\]

Thuật toán **MST preorder**:

1. Tính MST T và trọng số W.
2. Duyệt DFS preorder T từ một gốc cố định.
3. Ghép các thành phố theo thứ tự gặp đầu tiên.
4. Thêm cạnh về gốc.

Chứng minh:

\[
\boxed{
C_{\mathrm{tour}}
\le2W
\le2\operatorname{OPT}.
}
\]

- **MST** là cận dưới vì bỏ một cạnh của tour tối ưu cho cây khung.
- **2W** là hành trình Euler của MST nhân đôi.
- **Shortcut** không tăng chi phí nhờ **tam giác**.
- **Preorder** tạo tour không lặp thành phố, tương đương shortcut từ hành trình đi quanh cây.

Đây là **bảo đảm xấu nhất ≤2OPT**, không phải thuật toán luôn tối ưu và cũng không phải kết quả đúng cho TSP phi metric hoặc có hướng.

Với symmetric metric TSP, **Christofides** cải thiện thành `3OPT/2` bằng MST + **matching hoàn hảo trọng số nhỏ nhất trên các đỉnh bậc lẻ** + Euler + shortcut. Trong thực hành, có thể dùng heuristic giảm chi phí từ một tour đã có bảo đảm để vừa cải thiện kết quả vừa **giữ nguyên cận xấp xỉ**.
