# Tính chất lát cắt và cạnh an toàn

## Mục tiêu học tập

**Tính chất lát cắt** (*cut property*) là nền tảng để chứng minh nhiều thuật toán tìm **cây khung nhỏ nhất** (*minimum spanning tree — MST*) là đúng. Nó trả lời một câu hỏi rất quan trọng:

> Khi đã chọn một số cạnh mà vẫn muốn hoàn thành một cây khung có tổng trọng số nhỏ nhất, **cạnh nào có thể thêm vào mà không làm mất khả năng tối ưu**?

Câu trả lời không đơn giản là “luôn lấy cạnh nhẹ nhất chưa chọn”. Phải xác định **một lát cắt không cắt qua các cạnh đã chọn**, rồi chọn **cạnh nhẹ nhất đi qua lát cắt ấy**. Khi những điều kiện của định lý được thỏa, cạnh được chọn là **cạnh an toàn** (*safe edge*): có ít nhất một MST chứa cả tập cạnh đã chọn và cạnh mới.

Trong bài này, bạn sẽ:

1. Nắm vững đồ thị vô hướng có trọng số, cây khung, MST và **rừng khung nhỏ nhất** khi đồ thị không liên thông.
2. Định nghĩa chính xác **lát cắt `(S,V\setminus S)`**, cạnh **băng qua lát cắt**, **cạnh nhẹ (light edge)** và **lát cắt tôn trọng tập A (respects A)**.
3. Phân biệt **“cạnh an toàn đối với A”** với “cạnh thuộc mọi MST” và “cạnh nhẹ nhất toàn đồ thị”.
4. Chứng minh định lý lát cắt bằng kỹ thuật **thêm cạnh — tạo chu trình — bỏ cạnh** (*exchange argument*).
5. Thực hiện từng bước **Kruskal** bằng DSU/Union–Find và **Prim** bằng hàng đợi ưu tiên.
6. Hiểu vì sao thuật toán vẫn đúng với **trọng số bằng nhau, trọng số 0 và trọng số âm**, nhưng không áp dụng trực tiếp cho đồ thị có hướng.
7. Biết khi nào một cạnh **không an toàn**, kể cả khi nó nối hai thành phần khác nhau hoặc là cạnh nhẹ nhất của một lát cắt **không tôn trọng A**.
8. Phân biệt định lý lát cắt với **tính chất chu trình (cycle property)**, kết luận về tính duy nhất khi có hòa và cạnh cầu.
9. Chạy chương trình **Java 17+** độc lập gồm Kruskal, Prim, kiểm tra tính liên thông và in đầu ra chính xác.
10. Phân tích độ phức tạp, chứng minh tính đúng và tự kiểm thử bằng những đồ thị biên.

---

## 1. Từ cây khung đến tối ưu hóa tổng trọng số

Xét đồ thị vô hướng:

\[
G=(V,E,w)
\]

trong đó V là tập đỉnh, E là tập cạnh, và `w(e)` là trọng số của cạnh e. Trọng số có thể biểu thị **chi phí nối cáp**, chiều dài đường, phí xây dựng, lượng vật liệu hoặc một tiêu chí cộng được.

### 1.1. Cây là gì?

Một đồ thị vô hướng là **cây** khi nó:

- **Liên thông**: giữa hai đỉnh bất kỳ có một đường đi.
- **Không có chu trình**.

Với n đỉnh (n≥1), cây có đúng `n-1` cạnh. Một cách tương đương: trong cây có đúng **một đường đi đơn** giữa mọi cặp đỉnh.

### 1.2. Cây khung là gì?

Một **cây khung** của đồ thị vô hướng liên thông G là một tập cạnh `T⊆E` sao cho:

1. T kết nối **tất cả đỉnh** của G.
2. T không tạo chu trình.
3. Vì vậy `|T|=|V|-1`.

Đồ thị có thể có rất nhiều cây khung khác nhau. Mục tiêu của MST là tìm cây khung có **tổng trọng số nhỏ nhất**:

\[
\operatorname{MST}(G)
=\arg\min_{T\text{ là cây khung}}\sum_{e\in T}w(e).
\]

Ký hiệu trên nói đến một **tập cạnh** tối ưu; khi có nhiều MST cùng tổng trọng số, ta chỉ cần trả một cây nếu đề không yêu cầu tất cả.

### 1.3. Cây khung khác đường đi ngắn nhất

Hai bài toán khác nhau:

- **MST:** chọn n−1 cạnh nối mọi đỉnh sao cho **tổng trọng số các cạnh được chọn** nhỏ nhất.
- **Shortest-path tree từ s:** với mỗi đỉnh v, đường đi từ s tới v trên cây phải là một đường ngắn nhất trong graph gốc.

Một MST **không bảo đảm** các đường từ một nguồn tới mọi đỉnh là ngắn nhất. Một cây đường đi ngắn nhất cũng **không nhất thiết** có tổng trọng số các cạnh nhỏ nhất.

Ví dụ tam giác:

```text
A --1-- B
 \      /
  2    1
   \  /
     C
```

Nếu nguồn là A, đường trực tiếp A→C có chi phí 2, bằng đường A→B→C có chi phí 2; nhưng trong đồ thị khác với trọng số khác, đường ngắn nhất có thể không nằm trên MST. Không dùng kết quả Prim/Kruskal để trả khoảng cách đường đi nếu đề hỏi Dijkstra.

### 1.4. Đồ thị không liên thông

Nếu đồ thị không liên thông, **không tồn tại một cây khung nối tất cả V**. Ta có thể tìm **rừng khung nhỏ nhất** (*minimum spanning forest — MSF*): mỗi thành phần liên thông nhận một MST riêng.

Ví dụ:

```text
A --(-2)-- B     C --5-- D     E (cô lập)
```

Rừng có ba cây/thành phần: `{A,B}`, `{C,D}` và `{E}`; tổng trọng số các cạnh là `-2+5=3`. Không được gọi toàn bộ rừng này là “một MST của đồ thị năm đỉnh” vì đồ thị không liên thông.

---

## 2. Lát cắt (cut) là gì?

Chọn một tập đỉnh S là **tập con thực sự, không rỗng** của V:

\[
\varnothing\ne S\subsetneq V.
\]

Lát cắt `(S,V\setminus S)` chia tập đỉnh thành **hai phía**:

- Phía 1: S.
- Phía 2: các đỉnh còn lại `V\setminus S`.

Một cạnh vô hướng `e=\{u,v\}` **băng qua lát cắt** (*crosses the cut*) nếu một đầu ở S và đầu kia ở ngoài S:

\[
u\in S,\quad v\notin S
\quad\text{hoặc ngược lại}.
\]

Tập những cạnh băng qua lát cắt thường ký hiệu `\delta(S)`:

\[
\delta(S)
=\{\{u,v\}\in E:\;u\in S,\ v\notin S\}.
\]

### 2.1. Ví dụ đơn giản

Graph:

```text
A --4-- B
|       |
3       2
|       |
C --4-- D
```

Chọn `S=\{A,C\}`. Cạnh AB có một đầu A ở S, B bên ngoài → băng qua lát cắt. Cạnh CD cũng băng qua. Cạnh AC nằm hoàn toàn trong S, còn cạnh BD nằm hoàn toàn bên ngoài S; hai cạnh ấy **không băng qua**.

**Lát cắt là cách chia các đỉnh, không phải cách “cắt đồ thị ra thành hai thành phần có sẵn”.** Ta có thể chọn nhiều tập S khác nhau; các cạnh băng qua S vẫn có thể nối hai phía trong graph gốc.

### 2.2. Cạnh nhẹ của một lát cắt

Một cạnh e là **cạnh nhẹ** (*light edge*) qua lát cắt S nếu:

\[
e\in\delta(S),\qquad
w(e)=\min_{f\in\delta(S)}w(f).
\]

Nói cách khác: **e có trọng số nhỏ nhất trong tất cả cạnh băng qua lát cắt ấy**.

Có thể có nhiều cạnh cùng đạt giá trị nhỏ nhất. Khi đó **mỗi cạnh đồng hạng đều là light edge**; thuật toán cần quy tắc phá hòa nếu muốn đầu ra xác định, nhưng định lý vẫn đúng.

Ví dụ cạnh băng qua S có trọng số 3, 3, 8. Có **hai** light edge trọng số 3. Cạnh 8 không phải light edge dù có thể là cạnh hợp lệ nối hai phía.

### 2.3. Phải có cạnh băng qua

Trên đồ thị liên thông, mọi lát cắt hợp lệ đều có ít nhất một cạnh băng qua; nếu không, hai phía không thể kết nối với nhau.

Trên đồ thị không liên thông, có thể chọn S là một hoặc nhiều thành phần liên thông trọn vẹn, khi đó `\delta(S)=\varnothing`. **Không thể lấy minimum trên tập rỗng** hoặc nói “cạnh nhẹ nhất của lát cắt” nếu không có cạnh nào băng qua.

Trong MSF, áp dụng lập luận theo **từng thành phần liên thông** có đủ các cạnh để xây cây bên trong thành phần đó.

---

## 3. Tập cạnh A và điều kiện “lát cắt tôn trọng A”

Khi đang xây MST, gọi **A** là tập cạnh đã chọn. Thuật toán muốn duy trì bất biến:

\[
\boxed{\text{Có ít nhất một MST chứa toàn bộ các cạnh của A.}}
\]

A **không nhất thiết** đã nối hết các đỉnh. Thông thường A là một **rừng** — chưa có chu trình — vì nó là tập con của một cây.

Một lát cắt `(S,V\setminus S)` được gọi là **tôn trọng A** (*respects A*) nếu **không có cạnh nào trong A băng qua lát cắt**:

\[
A\cap\delta(S)=\varnothing.
\]

### 3.1. Trực giác “không cắt đôi cây đã dựng”

Nếu A đã chứa cạnh `B–C`, một lát cắt để B và C ở **hai phía khác nhau** sẽ băng qua một cạnh thuộc A. Lát cắt ấy **không tôn trọng A**.

Nếu A chứa những cây nhỏ, một lát cắt tôn trọng A phải đặt **mỗi thành phần của rừng A hoàn toàn ở một phía**; không được tách đôi một thành phần đã nối bởi A.

### 3.2. Điều kiện này quan trọng vì sao?

Trong chứng minh bằng hoán đổi cạnh, ta sẽ tìm một cạnh f thuộc MST ban đầu để **loại bỏ** sau khi thêm cạnh e. Nếu lát cắt tôn trọng A, mọi cạnh băng qua lát cắt đều **không thuộc A**. Vì thế cạnh f bị loại chắc chắn **không phải** cạnh đã chốt trong A; ta bảo toàn tất cả lựa chọn trước đó.

Nếu lát cắt **không tôn trọng A**, lý lẽ ấy không còn bảo đảm. Một cạnh e có thể là light edge của lát cắt nhưng **không an toàn đối với A** vì thêm nó vào A tạo chu trình hoặc buộc phải bỏ một cạnh đã cam kết giữ.

### 3.3. Mệnh đề “A là rừng” chưa đủ

Nếu A chỉ là một rừng bất kỳ nhưng không nằm trong **bất kỳ MST nào**, không có cách thêm các cạnh để biến nó thành MST; định lý an toàn không thể cứu một lựa chọn sai từ trước.

Điều kiện đầu vào của định lý mạnh hơn:

\[
\exists T\text{ là MST sao cho }A\subseteq T.
\]

Một rừng không có chu trình mới là **cần**, nhưng chưa **đủ** để A còn có thể hoàn tất thành MST.

---

## 4. Cạnh an toàn (safe edge) là gì?

Cho A là tập cạnh đang chọn. Cạnh e được gọi là **an toàn đối với A** nếu:

\[
\boxed{
\exists T'\text{ là MST của }G:
A\cup\{e\}\subseteq T'.
}
\]

Cách hiểu:

- Thêm e vẫn **giữ được cơ hội hoàn thành một MST**.
- Cạnh e không nhất thiết thuộc **mọi** MST.
- Tập `A\cup\{e\}` có thể chưa phải một MST hoàn chỉnh; nó chỉ là **lựa chọn một phần** có thể mở rộng thành MST.
- “An toàn” là tính chất **tương đối với A**, không phải nhãn cố định của cạnh ở mọi thời điểm.

### 4.1. So sánh các khái niệm

| Khái niệm | Ý nghĩa |
| --- | --- |
| Cạnh nhẹ qua S | Trọng số nhỏ nhất trong `\delta(S)` |
| Lát cắt tôn trọng A | Không có cạnh của A băng qua S |
| Cạnh an toàn đối với A | Có ít nhất một MST chứa `A\cup\{e\}` |
| Cạnh thuộc một MST | Có ít nhất một MST chứa cạnh ấy |
| Cạnh thuộc mọi MST | Mọi MST đều chứa cạnh ấy |
| Cạnh nối hai thành phần của A | Hai đầu nằm ở hai cây khác nhau trong rừng A; thêm cạnh không tạo chu trình trong A |

**Nối hai thành phần A** không có nghĩa cạnh ấy **an toàn**: có thể vẫn chọn sai một cạnh quá nặng.

### 4.2. Định lý lát cắt — phát biểu chính xác

Giả sử:

1. G là **đồ thị vô hướng liên thông, có trọng số**.
2. A là tập con của **một MST nào đó**.
3. Lát cắt `(S,V\setminus S)` **tôn trọng A**.
4. e là **một cạnh nhẹ** băng qua lát cắt này.

Khi đó:

\[
\boxed{e\text{ là cạnh an toàn đối với }A.}
\]

Tức:

\[
\exists T'\text{ là MST}:A\cup\{e\}\subseteq T'.
\]

**Điểm quan trọng:** định lý không đòi trọng số **dương**, **phân biệt**, hay graph là đơn đồ thị. Nó vẫn đúng với cạnh trọng số **âm hoặc bằng 0** và cả khi có nhiều cạnh cùng trọng số nhỏ nhất, miễn đang giải MST **vô hướng**.

---

## 5. Chứng minh định lý bằng hoán đổi cạnh (exchange argument)

Đây là chứng minh trung tâm của bài.

### 5.1. Chọn một MST T đang chứa A

Vì giả thiết có ít nhất một MST chứa A, lấy một MST như vậy, gọi là T:

\[
A\subseteq T.
\]

Nếu e đã nằm trong T, ta xong ngay: T chứa `A\cup\{e\}`. Trường hợp đáng phân tích là **e chưa nằm trong T**.

### 5.2. Thêm e vào T tạo đúng một chu trình

Vì T là cây, hai đầu của e đã có **một đường đi duy nhất trong T**. Thêm e tạo **một chu trình duy nhất** C.

Do e băng qua lát cắt S, đường đi trong T nối hai đầu của e cũng phải **đi từ phía S sang phía còn lại ít nhất một lần**. Vì vậy trên đường đi ấy tồn tại một cạnh **f cũng băng qua lát cắt S**.

Đồng thời:

- e là light edge ⇒ `w(e)\le w(f)`.
- Lát cắt tôn trọng A ⇒ không cạnh nào của A băng qua ⇒ **`f\notin A`**.

### 5.3. Bỏ f để lại một cây khung

Đặt:

\[
T'=T\cup\{e\}\setminus\{f\}.
\]

T' vẫn nối mọi đỉnh và không có chu trình:

- Thêm e tạo đúng một chu trình.
- Bỏ f trên chu trình ấy phá chu trình nhưng không làm mất liên thông.

Vì f **không thuộc A**, ta không xóa cạnh nào của A. Do vậy:

\[
A\cup\{e\}\subseteq T'.
\]

### 5.4. Tổng trọng số không tăng

Tính tổng:

\[
w(T')=w(T)+w(e)-w(f)\le w(T).
\]

Nhưng T vốn là **cây khung nhỏ nhất**, nên không cây khung nào được có trọng số **nhỏ hơn** T. Suy ra thực tế:

\[
w(T')=w(T),
\]

và T' cũng là một **MST**.

Đã dựng được MST T' chứa `A\cup\{e\}`; do đó **e an toàn đối với A**. Hết chứng minh.

### 5.5. Điều gì xảy ra khi hai cạnh bằng nhau?

Nếu `w(e)=w(f)`, hoán đổi không đổi tổng trọng số. T' là một MST khác hoặc cùng một cấu trúc cạnh theo trường hợp. Định lý vẫn đúng.

**Không được suy ra** “một light edge luôn có trong mọi MST”. Khi có nhiều cạnh đồng hạng qua lát cắt, ta chỉ được bảo đảm rằng chọn **một** light edge cụ thể có thể dẫn tới **ít nhất một** MST phù hợp với A.

### 5.6. Nếu e là light edge duy nhất của một lát cắt?

Nếu e **nhẹ hơn nghiêm ngặt tất cả cạnh khác băng qua cùng lát cắt**, e nằm trong **mọi MST**. Nếu có một MST T không chứa e, ta áp dụng hoán đổi như trên và chọn f băng qua lát cắt trên đường T. Vì `w(e)<w(f)`, T' có tổng nhỏ hơn T, mâu thuẫn.

Đây là kết luận **mạnh hơn** và cần điều kiện **duy nhất/nhẹ hơn nghiêm ngặt** trên lát cắt ấy.

---

## 6. Ví dụ đồ thị sáu đỉnh: chọn cạnh an toàn từng bước

Xét graph vô hướng với các đỉnh `A,B,C,D,E,F`:

| Cạnh | Trọng số |
| --- | ---: |
| A–B | 4 |
| A–C | 3 |
| B–C | 1 |
| B–D | 2 |
| C–D | 4 |
| C–E | 5 |
| D–E | 2 |
| D–F | 6 |
| E–F | 3 |
| B–E | 4 |
| A–F | 9 |

Đồ thị liên thông, có 6 đỉnh. Bất kỳ cây khung nào đều có đúng `6-1=5` cạnh.

### 6.1. Một chuỗi các lát cắt tôn trọng A

Bắt đầu `A_{\mathrm{selected}}=\varnothing`. Tạm gọi tập đỉnh phía đã nối là S, không nhầm ký hiệu **đỉnh A** với **tập cạnh đã chọn**.

**Lượt 1 — S={A}:**

Các cạnh băng qua S là A–C(3), A–B(4), A–F(9). Light edge là **A–C(3)**. Lát cắt tôn trọng tập đã chọn rỗng, nên A–C an toàn.

Tập cạnh đã chọn: `\{A-C\}`; tập đỉnh đã nối S={A,C}.

**Lượt 2 — S={A,C}:**

Cạnh băng qua gồm B–C(1), A–B(4), C–D(4), C–E(5), A–F(9). Nhẹ nhất là **B–C(1)**.

Cạnh đã chọn A–C nằm **hoàn toàn trong S**, nên lát cắt **tôn trọng** A_selected. Thêm B–C là an toàn.

**Lượt 3 — S={A,B,C}:**

Các cạnh băng qua gồm B–D(2), B–E(4), C–D(4), C–E(5), A–F(9). Nhẹ nhất là **B–D(2)** → an toàn.

**Lượt 4 — S={A,B,C,D}:**

Cạnh băng qua gồm D–E(2), B–E(4), C–E(5), D–F(6), A–F(9). Nhẹ nhất là **D–E(2)** → an toàn.

**Lượt 5 — S={A,B,C,D,E}:**

Các cạnh băng qua gồm E–F(3), D–F(6), A–F(9). Nhẹ nhất là **E–F(3)** → an toàn.

Kết quả:

```text
A-C (3)
B-C (1)
B-D (2)
D-E (2)
E-F (3)
```

Tổng:

\[
3+1+2+2+3=\boxed{11}.
\]

Có đúng 5 cạnh, nối cả 6 đỉnh, không tạo chu trình; mọi bước chọn theo định lý lát cắt ⇒ đây là **MST**.

### 6.2. Một chi tiết đáng chú ý

Thứ tự trọng số được chọn ở chuỗi trên là:

```text
3, 1, 2, 2, 3
```

Nó **không tăng đều**. Điều này không mâu thuẫn với tính đúng: ở lượt 1, B–C(1) **không băng qua lát cắt S={A}**, nên không phải ứng viên của lượt đó.

Đây cũng là điểm khác biệt về cách chọn cạnh của **Prim** so với **Kruskal**: Prim chọn cạnh nhẹ nhất **băng qua lát cắt của cây hiện tại**, chứ không chọn cạnh nhẹ nhất chưa dùng của toàn graph.

### 6.3. Tổng trọng số không đủ để kiểm tra một kết quả

Một danh sách cạnh có tổng 11 chưa chắc là MST: có thể không nối mọi đỉnh hoặc chứa chu trình. Muốn xác minh đầu ra, cần đồng thời kiểm tra:

1. Các cạnh đều có thật trong graph.
2. Chọn đúng `V-1` cạnh khi graph liên thông.
3. Các cạnh được chọn không tạo chu trình.
4. Các cạnh được chọn nối được mọi đỉnh.
5. Có chứng minh hoặc oracle rằng tổng trọng số là tối thiểu.

Số cạnh và tổng trọng số **không thay thế** cho việc kiểm tra tính hợp lệ cấu trúc.

---

## 7. Kruskal: lấy cạnh nhẹ theo thứ tự toàn cục

**Kruskal** bắt đầu với V đỉnh riêng lẻ và A_selected rỗng. Nó:

1. Sắp **toàn bộ các cạnh** theo trọng số tăng dần.
2. Xét từng cạnh theo thứ tự ấy.
3. Nếu hai đầu đang thuộc **hai thành phần khác nhau** của rừng A_selected, **chấp nhận cạnh**.
4. Nếu hai đầu đã trong cùng thành phần, bỏ cạnh vì thêm vào sẽ tạo chu trình.
5. Khi đồ thị liên thông và đã chọn V−1 cạnh, dừng; nếu hết cạnh trước đó thì kết quả là **MSF**.

### 7.1. DSU / Union–Find quản lý thành phần

Để biết hai đỉnh đã nối bởi các cạnh được chọn hay chưa, dùng **Disjoint Set Union (DSU)**:

- `find(v)` trả đại diện thành phần chứa v.
- `union(u,v)` gộp hai thành phần nếu khác nhau, trả về có gộp thật hay không.
- Dùng **path compression** và **union by size/rank** để thao tác gần hằng số thời gian khấu hao, chính xác là `O(\alpha(V))`.

Nếu `find(u)==find(v)`, thêm cạnh u–v tạo một chu trình trong rừng đang chọn → bỏ qua.

### 7.2. Tại sao cạnh Kruskal chọn là an toàn?

Giả sử Kruskal đang định chọn cạnh e=(u,v), với u và v nằm ở **hai thành phần DSU khác nhau**.

Lấy S là **toàn bộ các đỉnh trong thành phần DSU của u**. Mỗi cạnh đã chọn A_selected nằm **trọn trong một thành phần DSU**, nên **không cạnh nào của A_selected băng qua S**. Lát cắt tôn trọng A_selected.

Vì Kruskal xét cạnh theo trọng số tăng dần, e là một **cạnh nhẹ** băng qua lát cắt này. Nếu từng có cạnh nhẹ hơn băng qua S mà đã được xét trước, cạnh ấy không thể bị bỏ do tạo chu trình ở thời điểm đó: một cặp đỉnh đã nối trước thì vẫn nối về sau, trái với việc hiện giờ chúng thuộc hai thành phần khác nhau.

Vậy e là light edge của một cut tôn trọng A_selected ⇒ **e an toàn**.

Lập luận này vẫn đúng khi trọng số hòa: một trong các cạnh nhẹ được chọn trước theo quy tắc phá hòa vẫn an toàn.

### 7.3. Kruskal trên đồ thị sáu đỉnh

Sắp theo trọng số (và nếu hòa, theo thứ tự tên hai đầu để có kết quả xác định):

```text
B-C 1
B-D 2
D-E 2
A-C 3
E-F 3
A-B 4
B-E 4
C-D 4
C-E 5
D-F 6
A-F 9
```

Các cạnh đầu tiên được nhận:

```text
B-C (1)
B-D (2)
D-E (2)
A-C (3)
E-F (3)
```

Sau khi nhận cạnh thứ năm, 6 đỉnh đã nối và không có chu trình, nên dừng. Tổng `1+2+2+3+3=11`.

Điểm khác với Prim: Kruskal chọn B–C(1) **trước** A–C(3), vì nó xét thứ tự toàn cục chứ không phát triển cây từ một gốc cụ thể.

---

## 8. Prim: chọn cạnh nhẹ băng qua cây đang phát triển

**Prim** bắt đầu ở một đỉnh s bất kỳ. Nó duy trì:

- Tập S các đỉnh đã nằm trong cây đang phát triển.
- Tập cạnh A_selected nối các đỉnh trong S thành một cây.
- Các cạnh băng qua lát cắt `(S,V\setminus S)`.

Mỗi lượt Prim chọn **cạnh có trọng số nhỏ nhất với một đầu trong S và đầu còn lại ở ngoài S**, thêm cạnh và mở rộng S.

### 8.1. Lát cắt tự nhiên của Prim

Vì mọi cạnh đã chọn nằm trọn trong S, lát cắt `(S,V\setminus S)` **tự động tôn trọng A_selected**.

Cạnh được chọn là **light edge của lát cắt**, do đó an toàn theo định lý đã chứng minh.

Lặp cho tới khi `S=V` (nếu graph liên thông), Prim thu được một MST.

### 8.2. Prim dùng min-heap

Có thể lưu trong hàng đợi ưu tiên những cạnh nối từ tập đã ghé S tới các đỉnh chưa ghé. Mỗi bước:

1. Poll cạnh nhỏ nhất.
2. Nếu đỉnh đích đã ghé, bỏ mục cũ.
3. Nếu đỉnh đích chưa ghé, chọn cạnh, đánh dấu đích và đưa các cạnh mới của đích vào heap.

Không được đánh dấu một đỉnh **ngay khi cạnh tới nó được push**: có thể còn một cạnh khác rẻ hơn được khám phá trước khi đỉnh ấy được chọn. Đánh dấu khi cạnh được **poll và chấp nhận**.

### 8.3. Prim trên đồ thị sáu đỉnh, bắt đầu A

```text
Chọn A-C (3)
Chọn C-B (1)
Chọn B-D (2)
Chọn D-E (2)
Chọn E-F (3)
```

Tổng cũng là `11`. Hai thuật toán có thể khác **thứ tự** và thậm chí khác **tập cạnh** nếu có nhiều MST bằng nhau, nhưng đều phải đạt tổng nhỏ nhất.

### 8.4. Đồ thị không liên thông

Nếu heap hết cạnh mà còn đỉnh chưa ghé, điều đó chỉ ra cây đang phát triển không thể tới được các đỉnh còn lại. Để tìm **rừng khung nhỏ nhất**, bắt đầu một cây Prim mới tại một đỉnh chưa ghé và lặp lại.

Mỗi lần bắt đầu gốc mới làm tăng **số thành phần** của rừng; không được tự nối hai thành phần bằng một cạnh không có thật.

---

## 9. Trọng số hòa, tính duy nhất và “cạnh thuộc mọi MST”

### 9.1. Nhiều light edge: chọn bất kỳ cạnh nào?

Định lý cho phép chọn **bất kỳ light edge** qua một cut **tôn trọng A**, miễn A đang nằm trong ít nhất một MST.

Ví dụ tam giác:

```text
A--1--B
 \    /
  1  1
   \/
    C
```

Mỗi cây gồm hai trong ba cạnh có tổng bằng 2, nên có **ba MST khác nhau**. Cạnh A–B là light edge của cut `\{A\}` và an toàn với A_selected rỗng, nhưng **không nằm trong mọi MST** (cây A–C, B–C cũng có tổng 2).

**An toàn** nghĩa là tồn tại **ít nhất một** MST chứa cạnh, không phải tất cả MST đều phải chứa cạnh ấy.

### 9.2. Khi nào cạnh bắt buộc xuất hiện trong mọi MST?

Nếu một cạnh e là **cạnh nhẹ nhất duy nhất** băng qua **một lát cắt**, thì e thuộc **mọi MST** của graph liên thông.

Chứng minh hoán đổi: nếu một MST bỏ e, thêm e tạo chu trình, bỏ một cạnh f cũng băng qua cut. Vì e nhỏ hơn f **nghiêm ngặt**, cây mới rẻ hơn, mâu thuẫn tính tối ưu.

### 9.3. Trọng số phân biệt và tính duy nhất

Nếu **mọi cạnh toàn graph có trọng số khác nhau**, MST là **duy nhất**. Có thể chứng minh bằng cách so hai MST khác nhau, chọn cạnh nhẹ nhất thuộc đối xứng sai khác và dùng tính chất lát cắt/hoán đổi.

Nhưng chiều ngược **không đúng**: graph có **một số cạnh bằng trọng số** vẫn có thể có MST duy nhất, nếu những cạnh bằng nhau không tạo ra lựa chọn thay thế giữ nguyên tổng.

Không được kết luận “có hai cạnh cùng trọng số ⇒ có nhiều MST”.

### 9.4. Cạnh cầu

Trong graph vô hướng liên thông, một **cạnh cầu (bridge)** là cạnh mà bỏ nó sẽ làm graph mất liên thông. Mọi cây khung phải chứa nó, nên mọi MST cũng chứa nó, **không phụ thuộc trọng số của cạnh**.

Đây là kết luận cấu trúc, không yêu cầu cạnh cầu có trọng số nhỏ toàn cục. Xét cut được tạo bởi hai thành phần khi bỏ cầu: cầu là **cạnh duy nhất băng qua**.

### 9.5. Các cạnh đồng hạng có thể cho cây khác nhau

Một chương trình có quy tắc phá hòa bằng id đỉnh sẽ cho một MST xác định. Một chương trình khác giữ thứ tự nhập có thể cho MST khác. Khi kiểm thử, nếu graph có nhiều MST, nên so:

- Đủ V−1 cạnh, không chu trình, liên thông.
- Tổng trọng số tối ưu.

Không ép chương trình trả cùng thứ tự hay cùng tập cạnh với một bản tham chiếu nếu đề không chỉ định điều đó.

---

## 10. Phản ví dụ: cạnh nhẹ nhưng lát cắt không tôn trọng A

Đây là điểm cần nhớ để không áp dụng định lý quá rộng.

Dùng tam giác có ba cạnh trọng số 1:

```text
A--1--B
 \    /
  1  1
   \/
    C
```

Giả sử tập cạnh đã chọn là:

\[
A_{\mathrm{selected}}=\{A-B,A-C\}.
\]

Tập này **đã là một MST**. Chọn lát cắt `S=\{A,B\}`, phía còn lại `\{C\}`. Các cạnh băng qua cut:

- A–C(1), **đang thuộc A_selected**.
- B–C(1), **chưa thuộc A_selected**.

Cả hai là light edge. Nếu nhầm “light edge của mọi cut đều an toàn” rồi chọn B–C, tập mới:

```text
A-B, A-C, B-C
```

tạo **chu trình tam giác**. Nó không thể là tập con của bất kỳ cây khung ba đỉnh nào vì một cây chỉ có hai cạnh.

**Vấn đề:** lát cắt S **không tôn trọng A_selected**, vì A–C đã chọn lại băng qua S. Định lý lát cắt **không được áp dụng** cho chọn B–C trong tình huống này.

### 10.1. Tương tự: cạnh nối thành phần chưa chắc an toàn

Xét tam giác:

```text
A-B : 1
A-C : 2
B-C : 3
```

Tập A_selected rỗng, nên ba đỉnh thuộc ba thành phần khác nhau. Cạnh B–C trọng số 3 **nối hai thành phần khác nhau**, không tạo chu trình nếu thêm vào lúc này.

Nhưng MST duy nhất là `\{A-B,A-C\}` tổng 3; bất kỳ cây có B–C đều nặng hơn. Vì vậy B–C **không an toàn** đối với A_selected rỗng.

Lấy cut `S=\{C\}`: cạnh băng qua là A–C(2) và B–C(3). Cạnh nhẹ là **A–C(2)**, không phải B–C(3).

**Kết luận:** “không tạo chu trình” là điều kiện quan trọng để xây cây, nhưng **chưa đủ để bảo đảm tối ưu**. Kruskal kết hợp điều kiện này với **xếp cạnh tăng dần**; Prim kết hợp với **cạnh nhẹ qua cut của cây hiện tại**.

---

## 11. Tính chất chu trình (cycle property) và quan hệ với lát cắt

Định lý lát cắt giúp **chọn** cạnh an toàn. Một định lý đối ngẫu giúp **loại** cạnh chắc chắn không cần thiết.

### 11.1. Phát biểu quan trọng

Nếu một cạnh e có trọng số **lớn hơn nghiêm ngặt mọi cạnh khác** trên **một chu trình** của graph vô hướng, thì:

\[
\boxed{e\text{ không thuộc bất kỳ MST nào}.}
\]

Cạnh e là **cạnh nặng nhất duy nhất** trên chu trình đó.

### 11.2. Chứng minh bằng hoán đổi ngược

Giả sử có một MST T chứa e. Bỏ e khỏi T tạo hai thành phần S và `V\setminus S`.

Chu trình chứa e còn một đường đi giữa hai đầu e **không dùng e**. Trên đường này có ít nhất một cạnh f băng qua cut giữa hai thành phần. Vì e là cạnh nặng nhất **nghiêm ngặt** trên chu trình:

\[
w(f)<w(e).
\]

Thêm f vào `T\setminus\{e\}` tạo cây khung mới rẻ hơn T. Mâu thuẫn. Vậy không MST nào chứa e.

### 11.3. Nếu cạnh nặng nhất bị hòa?

Một cạnh đồng hạng nặng nhất trên chu trình **có thể vẫn thuộc một MST**. Ví dụ tam giác mọi cạnh 1: mỗi cạnh có trọng số lớn nhất (cũng là nhỏ nhất) trên chu trình, nhưng mỗi cạnh thuộc hai trong ba MST.

Không được dùng điều kiện “≥ tất cả cạnh khác” để loại **mọi cạnh đồng hạng lớn nhất** một cách độc lập.

### 11.4. Khi nào dùng tính chất nào?

| Tình huống | Công cụ | Kết luận |
| --- | --- | --- |
| Có cut tôn trọng A, một cạnh nhẹ nhất qua cut | **Cut property** | Cạnh đó an toàn đối với A |
| Có cut với light edge duy nhất | **Cut property mạnh** | Cạnh đó thuộc mọi MST |
| Có cycle với cạnh nặng nhất duy nhất | **Cycle property** | Cạnh đó không thuộc bất kỳ MST nào |
| Một cạnh không tạo chu trình với A | Chỉ kiểm tra cấu trúc rừng | Chưa đủ chứng minh an toàn |
| Một cạnh nhẹ qua cut **không** tôn trọng A | Không đủ giả thiết | Không được suy ra an toàn đối với A |

---

## 12. Trọng số âm và sự khác biệt với Dijkstra

Một số bạn nhầm quy tắc “trọng số không âm” của **Dijkstra** sang **Prim/Kruskal**.

**MST không yêu cầu trọng số không âm.** Tính chất lát cắt chỉ so sánh trọng số tương đối giữa các cạnh băng qua cut, không dựa trên việc một đoạn đường nối thêm phải làm tổng chi phí tăng.

Ví dụ:

```text
A --(-2)-- B     C --5-- D     E cô lập
```

Kruskal chọn A–B(-2) và C–D(5), cho MSF tổng 3. Prim chạy theo từng thành phần cũng chọn đúng hai cạnh ấy.

### 12.1. Vì sao cạnh âm không gây vấn đề như đường đi?

MST chỉ chọn một **tập cạnh không chu trình** nối tất cả đỉnh. Không có chuyện “đi vòng chu trình âm vô hạn lần” vì một cây không chứa chu trình và mỗi cạnh chỉ được chọn hoặc không chọn.

Đối với bài **đường đi ngắn nhất** trên graph có trọng số âm, thêm đoạn đường có thể giảm tổng chi phí, khiến lựa chọn tham lam chốt nhãn của Dijkstra sai. Hai định lý sử dụng **bất biến khác nhau**:

- **Dijkstra:** tối ưu độ dài từ một nguồn; giả thiết `w\ge0` bảo đảm nhãn đã chốt không thể giảm.
- **Prim/Kruskal:** tối ưu tổng trọng số của cây; exchange argument cho **cut property** đúng cả với trọng số âm.

### 12.2. Đồ thị có hướng thì sao?

Cây khung tối thiểu theo định nghĩa ở đây là của **đồ thị vô hướng**. Nếu đề yêu cầu một **arborescence** gốc r trên đồ thị có hướng, đó là bài toán khác (directed MST / minimum arborescence), thường dùng thuật toán Chu–Liu/Edmonds.

Không tự bỏ hướng của các cạnh rồi chạy Kruskal/Prim và gọi kết quả là arborescence tối ưu; các điều kiện đường đi từ gốc và indegree không được bảo toàn bằng thao tác ấy.

---

## 13. Java 17+: Kruskal và Prim cho MST / MSF

Chương trình dưới đây cài cả **Kruskal** và **Prim** cho đồ thị vô hướng.

Đặc điểm:

- Cạnh được biểu diễn bằng `Edge(u,v,weight)`; mỗi cạnh vô hướng chỉ cần khai báo **một lần** trong danh sách input.
- Kruskal dùng **DSU path compression + union by size**.
- Prim dựng danh sách kề hai chiều rồi dùng `PriorityQueue` của các ứng viên `(from,to,weight)`.
- Khi graph không liên thông, cả hai trả **rừng khung nhỏ nhất** và **số thành phần**.
- Trọng số là `long`, tổng dùng `Math.addExact` để **báo lỗi khi tràn** thay vì tạo tổng sai.
- Comparator dùng `comparingLong`, không trừ hai trọng số có thể tràn.
- Các cạnh có cùng trọng số được phá hòa theo id các đỉnh cho đầu ra minh họa xác định.
- Self-loop được phép trong input nhưng không được đưa vào cây; cạnh song song vẫn được xét đúng.
- Không tự sửa dữ liệu input.

Lưu tệp **`MstCutPropertyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public class MstCutPropertyDemo {

    public record Edge(int u, int v, long weight) {
    }

    private record Neighbor(int to, long weight) {
    }

    private record Candidate(int from, int to, long weight) {
    }

    public record ForestResult(
            long totalWeight,
            List<Edge> edges,
            int components) {
    }

    private static final class DSU {
        final int[] parent;
        final int[] size;
        int components;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int x) {
            int root = x;
            while (parent[root] != root) {
                root = parent[root];
            }

            // Path compression without recursive calls.
            while (x != root) {
                int next = parent[x];
                parent[x] = root;
                x = next;
            }
            return root;
        }

        boolean union(int a, int b) {
            a = find(a);
            b = find(b);
            if (a == b) {
                return false;
            }

            if (size[a] < size[b]) {
                int temp = a;
                a = b;
                b = temp;
            }

            parent[b] = a;
            size[a] += size[b];
            components--;
            return true;
        }
    }

    private static void validate(int n, List<Edge> edges) {
        if (n < 0) {
            throw new IllegalArgumentException("negative vertex count");
        }
        Objects.requireNonNull(edges, "edges");

        for (Edge e : edges) {
            if (e == null || e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n) {
                throw new IllegalArgumentException(
                        "invalid edge or vertex");
            }
        }
    }

    // Kruskal: global increasing edge order + DSU.
    public static ForestResult kruskal(
            int n, List<Edge> edges) {
        validate(n, edges);

        List<Edge> sorted = new ArrayList<>(edges);
        sorted.sort(
                Comparator.comparingLong(Edge::weight)
                        .thenComparingInt(Edge::u)
                        .thenComparingInt(Edge::v));

        DSU dsu = new DSU(n);
        List<Edge> chosen = new ArrayList<>();
        long total = 0;

        for (Edge e : sorted) {
            if (dsu.union(e.u(), e.v())) {
                chosen.add(e);
                total = Math.addExact(total, e.weight());

                if (chosen.size() == n - 1) {
                    break; // One spanning tree, if connected.
                }
            }
        }

        return new ForestResult(
                total, List.copyOf(chosen), dsu.components);
    }

    private static void offerOutgoing(
            int from,
            List<List<Neighbor>> adj,
            boolean[] visited,
            PriorityQueue<Candidate> pq) {

        for (Neighbor x : adj.get(from)) {
            if (!visited[x.to()]) {
                pq.offer(
                        new Candidate(from, x.to(), x.weight()));
            }
        }
    }

    // Prim over every connected component: minimum forest.
    public static ForestResult primForest(
            int n, List<Edge> edges) {
        validate(n, edges);

        List<List<Neighbor>> adj = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            adj.add(new ArrayList<>());
        }

        for (Edge e : edges) {
            if (e.u() == e.v()) {
                continue; // Self-loop cannot be a tree edge.
            }
            adj.get(e.u()).add(
                    new Neighbor(e.v(), e.weight()));
            adj.get(e.v()).add(
                    new Neighbor(e.u(), e.weight()));
        }

        PriorityQueue<Candidate> pq =
                new PriorityQueue<>(
                        Comparator.comparingLong(Candidate::weight)
                                .thenComparingInt(Candidate::from)
                                .thenComparingInt(Candidate::to));

        boolean[] visited = new boolean[n];
        List<Edge> chosen = new ArrayList<>();
        int components = 0;
        long total = 0;

        for (int root = 0; root < n; root++) {
            if (visited[root]) {
                continue;
            }

            components++;
            visited[root] = true;
            offerOutgoing(root, adj, visited, pq);

            while (!pq.isEmpty()) {
                Candidate e = pq.poll();

                if (visited[e.to()]) {
                    continue; // Old edge into the grown tree.
                }

                visited[e.to()] = true;
                chosen.add(
                        new Edge(e.from(), e.to(), e.weight()));
                total = Math.addExact(total, e.weight());

                offerOutgoing(e.to(), adj, visited, pq);
            }
        }

        return new ForestResult(
                total, List.copyOf(chosen), components);
    }

    private static String letter(int vertex) {
        return String.valueOf((char) ('A' + vertex));
    }

    private static String showEdges(List<Edge> edges) {
        List<String> names = new ArrayList<>();
        for (Edge e : edges) {
            names.add(
                    letter(e.u()) + "-" + letter(e.v())
                            + "(" + e.weight() + ")");
        }
        return names.toString();
    }

    public static void main(String[] args) {
        // A=0, B=1, C=2, D=3, E=4, F=5.
        List<Edge> graph = List.of(
                new Edge(0, 1, 4),
                new Edge(0, 2, 3),
                new Edge(1, 2, 1),
                new Edge(1, 3, 2),
                new Edge(2, 3, 4),
                new Edge(2, 4, 5),
                new Edge(3, 4, 2),
                new Edge(3, 5, 6),
                new Edge(4, 5, 3),
                new Edge(1, 4, 4),
                new Edge(0, 5, 9));

        ForestResult k = kruskal(6, graph);
        ForestResult p = primForest(6, graph);

        System.out.println(
                "Kruskal edges: " + showEdges(k.edges()));
        System.out.println(
                "Kruskal total: " + k.totalWeight()
                        + ", components: " + k.components());

        System.out.println(
                "Prim edges: " + showEdges(p.edges()));
        System.out.println(
                "Prim total: " + p.totalWeight()
                        + ", components: " + p.components());
        System.out.println(
                "Equal total: "
                        + (k.totalWeight() == p.totalWeight()));

        // Three equal edges -> more than one valid MST.
        List<Edge> triangle = List.of(
                new Edge(0, 1, 1),
                new Edge(0, 2, 1),
                new Edge(1, 2, 1));
        ForestResult t = kruskal(3, triangle);

        System.out.println(
                "Tie triangle total: " + t.totalWeight()
                        + ", edges: " + showEdges(t.edges()));

        // Two small components plus isolated vertex E.
        List<Edge> disconnected = List.of(
                new Edge(0, 1, -2),
                new Edge(2, 3, 5));
        ForestResult f = kruskal(5, disconnected);
        ForestResult fp = primForest(5, disconnected);

        System.out.println(
                "Disconnected forest total: " + f.totalWeight()
                        + ", components: " + f.components());
        System.out.println(
                "Disconnected forest edges: "
                        + showEdges(f.edges()));
        System.out.println(
                "Prim forest agrees: "
                        + (fp.totalWeight() == f.totalWeight()
                                && fp.components() == f.components()));

        System.out.println(
                "Empty graph components: "
                        + kruskal(0, List.of()).components());
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac MstCutPropertyDemo.java
java MstCutPropertyDemo
```

**Đầu ra chuẩn chính xác:**

```text
Kruskal edges: [B-C(1), B-D(2), D-E(2), A-C(3), E-F(3)]
Kruskal total: 11, components: 1
Prim edges: [A-C(3), C-B(1), B-D(2), D-E(2), E-F(3)]
Prim total: 11, components: 1
Equal total: true
Tie triangle total: 2, edges: [A-B(1), A-C(1)]
Disconnected forest total: 3, components: 3
Disconnected forest edges: [A-B(-2), C-D(5)]
Prim forest agrees: true
Empty graph components: 0
```

### 13.1. Giải thích kết quả

- **Kruskal** xét cạnh tăng dần, nhận B–C(1), B–D(2), D–E(2), A–C(3), E–F(3).
- **Prim** bắt đầu tại đỉnh A (id 0) và mở rộng cây lần lượt A–C(3), C–B(1), B–D(2), D–E(2), E–F(3).
- Cả hai cây có 5 cạnh và tổng **11**.
- Tam giác ba cạnh 1 có ba MST; code Kruskal phá hòa theo id nên chọn A–B và A–C, tổng 2.
- Đồ thị năm đỉnh không liên thông có các thành phần `{A,B}`, `{C,D}`, `{E}` nên `components=3`, tổng rừng `-2+5=3`.
- Đồ thị rỗng (V=0) được biểu diễn bằng rừng rỗng với số thành phần **0**. Điều này không có nghĩa một cây khung có thể có nguồn/đỉnh trong đồ thị rỗng.

### 13.2. Vì sao dùng record Java 17?

`Edge`, `Candidate`, `Neighbor` và `ForestResult` dùng cú pháp `record` của Java 17, cung cấp các hàm accessor như `weight()`, `u()` và `edges()`.

`ForestResult` trả:

- `totalWeight`: tổng trọng số các cạnh được chọn.
- `edges`: danh sách cạnh đã chọn, được sao chép vào `List.copyOf`.
- `components`: số thành phần rừng thu được.

Nếu `components==1` (với n≥1), result là một **MST**. Nếu `components>1`, đây là **MSF**, không phải một MST duy nhất của toàn graph.

### 13.3. Vì sao Kruskal dùng DSU?

`DSU.union(u,v)` trả `true` khi hai đầu thuộc hai thành phần khác nhau. Khi đó thêm cạnh vào rừng không tạo chu trình, và số thành phần giảm một.

Nếu `union` trả false, hai đầu đã nối qua một đường đi trong rừng; thêm cạnh sẽ tạo chu trình, nên bỏ cạnh ấy.

**Path compression** rút ngắn chuỗi cha của DSU sau mỗi `find`. **Union by size** luôn nối cây DSU nhỏ vào cây lớn, giúp thao tác có chi phí `O(\alpha(V))` khấu hao.

### 13.4. Vì sao Prim không dùng settled khi push?

Trong Prim, cùng một đỉnh v có thể nhận nhiều cạnh ứng viên từ các đỉnh đã ghé. Nếu đánh dấu v **lúc push ứng viên đầu tiên**, thuật toán có thể bị buộc nhận một cạnh nặng trước khi cạnh nhẹ hơn được đưa vào heap.

Trong code:

```java
Candidate e = pq.poll();
if (visited[e.to()]) {
    continue;
}
visited[e.to()] = true;
```

Đỉnh được đánh dấu **chỉ khi cạnh nhẹ nhất còn hiệu lực được poll và chấp nhận**. Đây là một dạng lazy heap để xử lý những cạnh ứng viên cũ.

### 13.5. Trọng số âm và kiểm soát tràn số

Không có điều kiện `weight>=0` trong `validate` vì MST **cho phép trọng số âm**.

Tổng dùng:

```java
total = Math.addExact(total, e.weight());
```

Nếu tổng vượt miền `long`, Java ném `ArithmeticException` thay vì âm thầm tràn thành một số sai. Trong hệ thống cần hỗ trợ trọng số hoặc tổng vượt 64 bit, có thể dùng `BigInteger`.

Comparator:

```java
Comparator.comparingLong(Edge::weight)
```

không lấy hiệu hai trọng số rồi ép kiểu `int`, tránh lỗi thứ tự do overflow.

### 13.6. Biểu diễn cạnh vô hướng và self-loop

Input ghi mỗi cạnh vô hướng **một lần** dưới dạng `Edge(u,v,w)`. Kruskal dùng danh sách ấy trực tiếp; Prim tự thêm **hai hướng kề**.

Self-loop `u==v` không thể nối hai thành phần khác nhau và không thể là cạnh cây: Kruskal loại qua DSU, Prim bỏ khi dựng danh sách kề. Đa cạnh được chấp nhận; việc chọn cạnh nhẹ hơn trong những cạnh nối cùng cặp đỉnh diễn ra bình thường.

---

## 14. Độ phức tạp thời gian và bộ nhớ

Đặt `V=|V|`, `E=|E|`.

### 14.1. Kruskal

- Sắp E cạnh: `O(E\log(E+1))`.
- Tối đa E thao tác `find/union`, khấu hao `O(\alpha(V))` mỗi thao tác với path compression và union by size.
- Duyệt các cạnh và ghi nhận rừng: `O(E+V)`.

Vì thế:

\[
T_{\mathrm{Kruskal}}
=O(V+E\log(E+1)+E\alpha(V)).
\]

Thường viết gọn là `O(E\log E)` cho các trường hợp E đủ lớn. Trên đồ thị đơn liên thông, `E\le O(V^2)` nên có thể diễn đạt tương đương gần `O(E\log V)`, nhưng trong đa đồ thị có rất nhiều cạnh song song, `\log E` phản ánh đúng chi phí sort hơn.

Bộ nhớ phụ:

- DSU: `O(V)`.
- Bản sao danh sách cạnh để sort: `O(E)`.
- Kết quả tối đa V−1 cạnh khi connected, hoặc `V-c` cạnh với c thành phần: `O(V)`.

Tổng `O(V+E)` bộ nhớ phụ trong cách cài minh họa.

### 14.2. Prim với heap ứng viên cạnh

- Dựng danh sách kề hai chiều: `O(V+E)` thời gian, `O(V+E)` bộ nhớ.
- Mỗi cạnh vô hướng có thể sinh ứng viên khi đầu tiên một đầu được đưa vào cây; số offer là `O(E)`.
- Heap có thể lưu `O(E)` ứng viên, mỗi push/pop `O(\log(E+1))`.

Một cận trên:

\[
T_{\mathrm{Prim,edge\ heap}}
=O(V+E+E\log(E+1)).
\]

Bộ nhớ phụ `O(V+E)` do visited, danh sách kề, heap và kết quả.

Một phiên bản **Prim với heap khóa tốt nhất theo từng đỉnh** và decrease-key có thể giữ heap `O(V)` và đạt `O((V+E)\log V)` bằng binary heap thích hợp.

### 14.3. Prim dùng ma trận kề

Với graph dày, có thể chọn đỉnh chưa trong cây có **khóa nối rẻ nhất** bằng cách quét mảng `O(V)` mỗi lượt, tổng `O(V^2)`. Đây là một lựa chọn khác, không tự mang độ phức tạp `O(E\log E)` như code heap ở trên.

### 14.4. Tổng quát và sai lệch do cấu trúc dữ liệu

Cùng một nguyên lý lát cắt nhưng thời gian thực thi khác nhau theo:

- Số đỉnh và cạnh.
- Graph thưa hay dày.
- Dùng DSU, min-heap, indexed heap hay quét mảng.
- Cách biểu diễn cạnh vô hướng (mỗi cạnh một mục hay hai mục).
- Cách xử lý đa cạnh, self-loop, kiểm tra đầu vào.
- Kiểu số `int/long/BigInteger`.

Không suy ra “MST luôn `O(V+E)`” chỉ vì kết quả có V−1 cạnh. Phần tìm **cạnh nhẹ hợp lệ** mới quyết định phần lớn chi phí.

---

## 15. Chứng minh tính đúng của Kruskal và Prim bằng bất biến cạnh an toàn

### 15.1. Bất biến chung

Gọi A_k là tập cạnh đã chấp nhận sau k bước. Bất biến:

\[
\exists T_k\text{ là một MST}:A_k\subseteq T_k.
\]

**Cơ sở:** `A_0=\varnothing`, là tập con của bất kỳ MST nào.

**Bước quy nạp:** giả sử A_k nằm trong một MST. Thuật toán chọn một light edge e băng qua **một cut tôn trọng A_k**. Theo định lý lát cắt, e **an toàn**; do đó A_{k+1}=A_k∪{e} vẫn nằm trong một MST.

Khi A có `V-1` cạnh, nối mọi đỉnh và không có chu trình, nó đã là một cây khung. Vì A nằm trong một MST có cũng V−1 cạnh, hai tập cạnh phải bằng nhau. Do đó A chính là **MST**.

### 15.2. Áp dụng cho Kruskal

Khi xét cạnh theo thứ tự trọng số tăng, nếu hai đầu thuộc hai thành phần khác nhau của rừng đã chọn, cắt giữa một thành phần ấy và phần còn lại:

- Tôn trọng A vì mọi cạnh A nằm trong các thành phần.
- Cạnh được chấp nhận là một light edge qua cut nhờ thứ tự sort.

Vì vậy từng cạnh Kruskal nhận đều an toàn. Các cạnh bị bỏ do cùng thành phần tạo chu trình, không cần thiết để nối thêm thành phần.

### 15.3. Áp dụng cho Prim

Ở mỗi bước cây Prim bao phủ tập đỉnh S:

- Các cạnh A đã chọn nằm hoàn toàn trong S.
- Cut `(S,V\setminus S)` tôn trọng A.
- Min-heap chọn light edge đi từ S ra ngoài.
- Cạnh ấy an toàn; thêm đỉnh mới mà không tạo chu trình.

Nếu graph liên thông, quá trình có thể mở rộng tới toàn bộ V. Kết thúc ở V−1 cạnh tạo MST.

### 15.4. Chứng minh MSF khi graph không liên thông

Mỗi thành phần liên thông có thể xét như một đồ thị con liên thông riêng. Không có cạnh giữa các thành phần, nên một rừng khung bất kỳ phải có một cây ở mỗi thành phần. Tối ưu tổng trọng số đạt được khi **mỗi cây của từng thành phần** là MST riêng của thành phần ấy.

Kruskal và Prim forest của code chỉ thêm cạnh **bên trong thành phần có thật** và duy trì tính tối ưu trong từng thành phần, nên trả **MSF**.

---

## 16. Cách kiểm tra một cạnh có an toàn không

Có nhiều bài lý thuyết không yêu cầu chạy nguyên Prim/Kruskal mà chỉ hỏi “cạnh e có an toàn không?”

### 16.1. Checklist cho định lý lát cắt

1. Graph có **vô hướng** và đang xét một thành phần liên thông phù hợp không?
2. Tập A đã chọn có phải **tập con của ít nhất một MST** không?
3. Đã chọn một cut `(S,V\setminus S)` cụ thể chưa?
4. Cut có **tôn trọng A** — không cạnh A nào băng qua — không?
5. Cạnh e có **băng qua cut** ấy không?
6. e có là **cạnh nhẹ nhất** trong tất cả cạnh băng qua cut không?
7. Nếu đúng, kết luận e **an toàn đối với A**.

Nếu không chứng minh được 2, 4 hoặc 6 thì **không được lấy định lý này làm bằng chứng**. Điều đó không nhất thiết nghĩa e chắc chắn không an toàn; chỉ có nghĩa phép chứng minh bằng cut đã chọn **chưa đủ**.

### 16.2. Một cạnh có thể an toàn dù không nhẹ ở cut đang xem

“Tồn tại một cut tôn trọng A mà e là light edge” là **điều kiện đủ** cho an toàn. Nếu e không nhẹ ở **một** cut nào đó bạn thử, điều ấy **không tự chứng minh e không an toàn**; có thể tìm một cut khác hoặc dùng lập luận khác.

Đừng nhầm một **tiêu chuẩn chứng minh đủ** với một phép kiểm tra phủ định hoàn chỉnh.

### 16.3. Điều kiện mạnh để loại cạnh

Nếu tìm được một chu trình mà e là **cạnh nặng nhất duy nhất**, ta chứng minh được e **không thuộc bất kỳ MST** nào bằng cycle property. Đây là một bằng chứng loại cạnh, khác với việc “e không nhẹ ở cut tôi vừa chọn”.

---

## 17. Kiểm thử Kruskal/Prim và oracle vét cạn

### 17.1. Các bộ test nên có

| Graph | Kỳ vọng |
| --- | --- |
| 6 đỉnh ở mục 6 | MST có tổng **11**, 5 cạnh |
| Tam giác ba cạnh trọng số 1 | Tổng **2**, nhiều MST |
| Chuỗi `A-B(2),B-C(4),C-D(6)` | Tất cả ba cạnh là cầu, tổng 12 |
| Một đỉnh không cạnh | Một cây 0 cạnh, tổng 0, components=1 |
| Đồ thị rỗng n=0 | Forest rỗng, components=0 |
| Hai thành phần và một đỉnh cô lập | MSF, không tạo cạnh giữa các phần |
| Cạnh âm `A-B(-2)` | MST/MSF được phép chọn cạnh âm |
| Cạnh trọng số 0 | Không được bỏ cạnh vì trọng số 0 |
| Cạnh song song `A-B(2),A-B(5)` | Chọn cạnh 2 nếu cần nối A và B |
| Self-loop `A-A(-100)` | Không chọn self-loop dù rất âm |
| Đỉnh ngoài `[0,n)` | Báo input không hợp lệ |
| Trọng số rất lớn | Math.addExact báo lỗi nếu tổng overflow |

### 17.2. Thuộc tính của kết quả khi graph liên thông

1. Có đúng `n-1` cạnh với n≥1.
2. Các cạnh đều là **cạnh input thật**.
3. Không tạo chu trình.
4. Tất cả n đỉnh thuộc cùng một thành phần khi xét riêng các cạnh được chọn.
5. Tổng các trọng số cạnh đã chọn bằng `totalWeight`.
6. `components=1`.
7. Tổng nhỏ nhất trong mọi cây khung (chứng minh bằng định lý hoặc oracle).

Nếu graph có c thành phần liên thông, MSF có:

\[
|A|=n-c.
\]

Trên kết quả chương trình, có thể kiểm tra:

```text
chosenEdges.size() == n - result.components()
```

và mỗi thành phần input đều được nối đầy đủ trong rừng.

### 17.3. Vét cạn cho graph nhỏ

Với n≤7 và số cạnh m nhỏ, tạo mọi tập con cạnh có kích thước n−1:

```text
BRUTE_MST(n, edges):
    best = +INF

    for mỗi tập con T của edges với |T| = n-1:
        if T không có chu trình
           và T nối được mọi đỉnh:
            best = min(best, sum(weight(e) for e in T))

    return best nếu tìm được
    return "không có MST" nếu graph không liên thông
```

Sau đó so tổng `best` với kết quả Kruskal và Prim. Nếu graph không liên thông, có thể chạy oracle **trên từng thành phần liên thông** và cộng các giá trị để kiểm tra MSF.

Với dữ liệu nhỏ, oracle độc lập là cách rất tốt để tìm các lỗi mà test ví dụ không thấy, đặc biệt **hòa trọng số, cạnh âm, self-loop và đa cạnh**.

### 17.4. Kiểm thử theo bất biến cut

Sau mỗi lần chọn cạnh e trong Kruskal/Prim, trên một graph nhỏ có thể:

1. Lưu lại A trước khi thêm e.
2. Xác định cut dùng để chứng minh an toàn.
3. Kiểm tra không có cạnh A nào băng qua cut.
4. Liệt kê các cạnh băng qua cut, xác định trọng số nhỏ nhất.
5. Xác nhận e có trọng số đúng bằng min đó.
6. Thêm e vào A, xác nhận vẫn không có chu trình.

Kiểm tra này không thay thế chứng minh tổng quát, nhưng giúp phát hiện nhanh lỗi **chọn sai cut, comparator hoặc quản lý visited/DSU**.

### 17.5. Không bắt buộc hai thuật toán trả cùng cạnh

Nếu input có nhiều MST, Kruskal và Prim có thể trả tập cạnh khác nhau dù cùng tổng. Kiểm thử đúng nên kiểm tra **tính hợp lệ + tối ưu**, không cố so `List<Edge>` bằng nhau trừ khi đề quy định thứ tự phá hòa chi tiết.

---

## 18. Lỗi thường gặp

1. **Nhầm MST với đường đi ngắn nhất**, dùng cây Prim/Kruskal để trả dist từ nguồn.
2. **Áp dụng cut property cho đồ thị có hướng** mà không có định lý tương ứng với bài arborescence.
3. **Quên điều kiện A nằm trong một MST**, rồi cố dùng cut property để sửa một rừng đã chọn sai.
4. **Chọn cut không tôn trọng A**, vẫn khẳng định một light edge mới an toàn.
5. **Chỉ kiểm tra cạnh không tạo chu trình** rồi kết luận nó an toàn; điều kiện này chưa đảm bảo tổng tối thiểu.
6. **Chọn cạnh có trọng số thấp nhất toàn graph** ở mọi lượt Prim, dù cạnh ấy không băng qua cut của cây hiện tại.
7. **Dùng cạnh nhẹ nhất đi ra từ một đỉnh đơn lẻ** thay vì light edge qua cả tập S của Prim.
8. **Không xét toàn bộ cạnh băng qua cut**, bỏ sót một cạnh nhẹ hơn.
9. **Cho rằng mọi light edge phải thuộc mọi MST**, sai khi có cạnh hòa.
10. **Cho rằng có hai cạnh cùng trọng số thì MST không duy nhất**, trong khi vẫn có graph MST duy nhất.
11. **Loại tất cả cạnh hòa nặng nhất trên một cycle** bằng điều kiện không nghiêm ngặt, có thể loại mất MST.
12. **Chấp nhận cạnh tạo chu trình** trong Kruskal vì quên kiểm tra DSU.
13. **Union sai** hoặc không nén đường DSU, làm bộ kiểm tra thành phần bị lệch.
14. **Đánh dấu Prim visited lúc push** thay vì lúc cạnh được chấp nhận, có thể giữ một cạnh nặng.
15. **Không bỏ ứng viên Prim có đầu đích đã visited**, dẫn đến chọn cạnh thừa/chu trình.
16. **Quên thêm cả hai hướng kề** khi cài Prim trên đồ thị vô hướng.
17. **Gán hai chiều cạnh ngay ở input rồi lại nhân đôi khi dựng adjacency**, làm khó kiểm tra đếm cạnh, dù có thể không đổi tổng.
18. **Coi đồ thị không liên thông vẫn có một MST toàn graph**, tự thêm cạnh ảo để nối.
19. **Cắt bỏ cạnh có trọng số âm** vì nhầm giả thiết của Dijkstra với MST.
20. **Dùng phép trừ weight trong comparator** khi là long lớn, có nguy cơ overflow.
21. **Cộng trọng số bằng int** khi tổng có thể vượt miền 32 bit.
22. **Không kiểm tra n, id đỉnh hoặc null edge**, dẫn đến lỗi runtime khó truy nguyên.
23. **Suy ra tính tối ưu chỉ từ n−1 cạnh và không chu trình**, trong khi đó mới là điều kiện cấu trúc.
24. **Ép kết quả Kruskal và Prim giống thứ tự/tập cạnh** khi graph có nhiều MST đồng trọng số.
25. **Dùng `O(V+E)` làm độ phức tạp tổng Kruskal** mà bỏ qua việc sort cạnh.
26. **Tưởng rằng một cut được chọn bất kỳ luôn có cạnh băng qua** trên graph không liên thông; cut giữa hai thành phần có thể rỗng.
27. **Bỏ qua self-loop rất âm**, cho rằng cạnh nhẹ tự động hợp lệ trong cây; self-loop không thể băng qua lát cắt hai phía.
28. **Không dùng kiểm thử đồ thị nhỏ có nhiều nghiệm tối ưu**, khiến lỗi về dấu bằng không xuất hiện.

---

## 19. Bài tập tự kiểm tra

### Bài 1 — Định nghĩa cut

Cho `V=\{A,B,C,D\}` và S={A,C}. Cạnh A–B, B–D, C–D, A–C: những cạnh nào băng qua cut `(S,V\setminus S)`?

### Bài 2 — Cạnh nhẹ

Một cut có bốn cạnh băng qua với trọng số `[3,7,3,9]`. Có bao nhiêu light edge? Nếu A_selected rỗng và graph liên thông, ta có thể chọn một cạnh trọng số 3 làm cạnh an toàn không?

### Bài 3 — Cut tôn trọng A

Giả sử `A_selected=\{A-B,C-D\}`. Cut S={A,B} tôn trọng A không? Cut S={A,C} thì sao? Giải thích.

### Bài 4 — Phát biểu định lý

Hãy viết đầy đủ bốn điều kiện để từ một cạnh e có thể kết luận “e an toàn đối với A” bằng định lý lát cắt.

### Bài 5 — Chứng minh hoán đổi

Trong một MST T chứa A, thêm một light edge e qua cut tôn trọng A và chưa nằm trong T. Vì sao có thể tìm một cạnh f khác trên chu trình vừa tạo sao cho f băng qua cut và f không thuộc A?

### Bài 6 — Tổng trọng số sau hoán đổi

Nếu `w(e)=5`, `w(f)=7` và T đã là một MST, điều gì mâu thuẫn? Vì sao tình huống thực tế không thể xảy ra khi e light qua cut tôn trọng A và T là MST chứa A?

### Bài 7 — Prim trên graph sáu đỉnh

Bắt đầu từ A, lần lượt chọn light edge qua cut của cây hiện tại trên graph mục 6. Ghi thứ tự cạnh, S sau từng lượt và tổng cuối.

### Bài 8 — Kruskal trên graph sáu đỉnh

Sắp cạnh theo trọng số tăng và ghi năm cạnh đầu tiên được chấp nhận. Tổng có bằng Prim không?

### Bài 9 — Light edge nhưng không an toàn

Trên tam giác ba cạnh trọng số 1, A_selected={A–B,A–C}. Lấy cut S={A,B}. Tại sao B–C dù là light edge vẫn không an toàn đối với A_selected?

### Bài 10 — Nối hai thành phần chưa đủ

Trên tam giác A–B(1), A–C(2), B–C(3), cạnh B–C có nối hai thành phần của tập chọn rỗng không? Nó có an toàn không? Chứng minh.

### Bài 11 — Trọng số hòa

Trong tam giác ba cạnh 1, có bao nhiêu MST? Cạnh A–B có thuộc mọi MST không?

### Bài 12 — Light edge duy nhất

Nếu một cạnh e có trọng số **nhỏ hơn nghiêm ngặt** mọi cạnh khác băng qua một cut, e có xuất hiện trong mọi MST không? Giải thích bằng hoán đổi.

### Bài 13 — Cycle property

Trên chu trình có trọng số các cạnh `[1,2,5,3]`, cạnh trọng số 5 có thể thuộc MST của graph chứa chu trình ấy không, nếu nó là cạnh nặng nhất duy nhất của chu trình?

### Bài 14 — Trọng số âm

Kruskal/Prim có đúng với cạnh trọng số âm không? Phân biệt với Dijkstra.

### Bài 15 — Rừng khung

Graph có 7 đỉnh chia thành ba thành phần liên thông. MSF có bao nhiêu cạnh? Có một MST nối cả 7 đỉnh không?

### Bài 16 — Cạnh cầu

Một cạnh cầu có trọng số 100, trong khi nhiều cạnh khác trọng số 1. Cạnh cầu có buộc thuộc MST không? Vì sao?

### Bài 17 — DSU

Trong Kruskal, nếu `find(u)==find(v)`, tại sao phải bỏ cạnh u–v dù nó có trọng số 0 hay âm?

### Bài 18 — Prim và visited

Vì sao không được đánh dấu v là visited ngay khi push một ứng viên cạnh tới v vào min-heap? Thời điểm nào mới hợp lệ?

### Bài 19 — Phân tích

Độ phức tạp của Kruskal với sort + DSU là gì? Prim với min-heap cạnh là gì? Khi nào quét mảng `O(V²)` hợp lý?

### Bài 20 — Oracle

Hãy mô tả cách vét cạn các tập cạnh kích thước n−1 trên graph nhỏ để tìm MST và đối chiếu với Kruskal/Prim. Nếu graph không liên thông, cần sửa oracle thế nào?

### Bài 21 — Phát biểu sai

“Một cạnh e không phải light edge của cut S đang xét thì chắc chắn e không thuộc bất kỳ MST.” Phát biểu này đúng không? Nếu sai, chỉ rõ lỗi lập luận.

### Bài 22 — Tính duy nhất

“Graph có hai cạnh cùng trọng số nên chắc chắn có ít nhất hai MST.” Phát biểu đúng không? Hãy nêu yếu tố thực sự quyết định có đường hoán đổi đồng trọng số hay không.

### Đáp án gợi ý

1. A–B và C–D băng qua cut. B–D nằm trọn phía `\{B,D\}`; A–C nằm trọn S.
2. Có hai light edge trọng số 3; với A rỗng, chọn bất kỳ cạnh 3 nào qua cut là an toàn theo định lý.
3. S={A,B} không cắt A–B nhưng **cắt C–D** vì C và D cùng nằm ngoài S? Không: C,D đều ngoài S, nên không cắt C–D. Do đó cut S={A,B} **tôn trọng** A. Cut S={A,C} cắt cả A–B và C–D, nên **không tôn trọng**.
4. G vô hướng liên thông; A nằm trong ít nhất một MST; cut tôn trọng A; e là light edge qua cut. Khi đó tồn tại một MST chứa `A\cup\{e\}`.
5. Đường đi duy nhất trong T giữa hai đầu e phải băng qua cut ít nhất một lần, nên có f trên đường ấy băng qua cut. Vì cut tôn trọng A nên f không thuộc A.
6. Hoán đổi cho cây T' có trọng số nhỏ hơn T là `w(T')=w(T)+5-7`, mâu thuẫn T là MST. Vì thế trong các giả thiết định lý đúng, không thể đồng thời có một f qua cut nặng hơn e trên T mà vẫn giữ T tối ưu; thực chất khi T là MST, hoán đổi phải có trọng số bằng nhau.
7. Thứ tự A–C(3), C–B(1), B–D(2), D–E(2), E–F(3); S mở rộng lần lượt `\{A,C\}`, `\{A,B,C\}`, `\{A,B,C,D\}`, `\{A,B,C,D,E\}`, `V`. Tổng 11.
8. Kruskal: B–C(1), B–D(2), D–E(2), A–C(3), E–F(3). Tổng 11, bằng Prim.
9. Cut S={A,B} cắt cạnh A–C vốn thuộc A_selected nên **không tôn trọng A**. Thêm B–C sẽ tạo chu trình tam giác, không thể là tập con của MST.
10. B–C nối hai đỉnh khác thành phần khi A rỗng, nhưng không an toàn: MST duy nhất A–B(1), A–C(2) tổng 3; cây dùng B–C(3) phải có tổng lớn hơn.
11. Có ba MST, mỗi cây chọn hai trong ba cạnh. A–B không thuộc mọi MST.
12. Có. Nếu một MST bỏ e, hoán đổi cạnh băng qua cut khác bằng e sẽ làm cây rẻ hơn, mâu thuẫn.
13. Không. Đây là cạnh nặng nhất **duy nhất** trên chu trình; cycle property loại nó khỏi mọi MST.
14. Có, MST dựa trên cut/exchange và không yêu cầu w≥0. Dijkstra tìm đường ngắn nhất với lựa chọn tham lam chốt nhãn cần trọng số không âm.
15. MSF có `7-3=4` cạnh; không tồn tại một MST nối cả graph vì không liên thông.
16. Có. Bỏ cầu làm graph không liên thông, nên mọi cây khung đều phải chứa nó, bất kể trọng số.
17. Hai đầu đã có đường đi qua A_selected; thêm cạnh tạo chu trình, bất kể trọng số.
18. Vì cạnh ứng viên đầu tiên tới v chưa chắc rẻ nhất; chỉ đánh dấu khi cạnh min hợp lệ được pop và được chọn để mở rộng cây.
19. Kruskal `O(V+E\log(E+1)+E\alpha(V))`; Prim heap cạnh `O(V+E+E\log(E+1))`. Với V nhỏ hoặc graph dày, Prim quét mảng `O(V²)` có thể thực tế thuận lợi.
20. Vét cạn các tập gồm n−1 cạnh, chỉ giữ tập liên thông, không chu trình, lấy tổng nhỏ nhất. Với graph không liên thông, giải trên từng thành phần rồi cộng.
21. Sai. Không nhẹ ở một cut đang xét chỉ nói rằng **cut đó không chứng minh** e an toàn; e có thể thuộc MST do một cut khác hoặc lý do khác.
22. Sai. Hai trọng số bằng nhau chưa đủ tạo phương án trao đổi bảo toàn tối ưu. Cần xét cấu trúc cycle/cut và khả năng tạo MST thay thế đồng tổng.

---

## Ghi nhớ

**Tính chất lát cắt:** nếu A nằm trong ít nhất một MST và cut `(S,V\setminus S)` **tôn trọng A**, thì **mỗi cạnh nhẹ nhất băng qua cut là một cạnh an toàn đối với A**. Chứng minh bằng cách lấy một MST chứa A, thêm cạnh e tạo chu trình, bỏ cạnh f khác cũng băng qua cut (nên f không thuộc A), và so `w(e)\le w(f)`. Kết quả còn là MST và chứa A cùng e.

**Kruskal** vận dụng điều đó bằng cách chọn cạnh tăng dần nối **hai thành phần DSU khác nhau**. **Prim** vận dụng bằng cách chọn cạnh nhẹ nhất đi **từ cây đang phát triển sang bên ngoài**. Cả hai tạo MST khi graph vô hướng liên thông, hoặc MSF khi graph không liên thông; cả hai vẫn đúng khi **trọng số bằng nhau, bằng 0 hoặc âm**. “Light edge” không đồng nghĩa với “thuộc mọi MST”, và “không tạo chu trình” chưa đủ để chứng minh tối ưu nếu thiếu điều kiện cạnh an toàn.
