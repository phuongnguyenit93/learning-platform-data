# Tính chất chu trình và cạnh có thể loại bỏ trong cây khung

## 1. Đặt vấn đề: bỏ cạnh nào mà không làm hỏng cây khung nhỏ nhất?

Cho một đồ thị vô hướng có trọng số. Ta muốn giữ các đỉnh liên thông với nhau bằng một tập cạnh có tổng trọng số nhỏ nhất. Đó là bài toán **cây khung nhỏ nhất (Minimum Spanning Tree, MST)**.

Một cách suy nghĩ tự nhiên là: **nếu thấy chu trình, ta có thể bỏ một cạnh mà vẫn giữ kết nối**. Nhưng cần phân biệt hai mục tiêu rất khác nhau:

1. **Giữ đồ thị liên thông:** loại một cạnh bất kỳ trên chu trình đều không làm mất tính liên thông.
2. **Giữ trọng số MST tối ưu:** không được tùy tiện chọn cạnh trên chu trình để bỏ. Cần dựa vào **trọng số**, đặc biệt là **tính chất chu trình (cycle property)**.

Ví dụ tam giác có trọng số:

```text
0 ---1--- 1
 \       /
  9     2
   \   /
     2

Các cạnh: 0--1 (1), 1--2 (2), 0--2 (9).
```

Bỏ bất kỳ một cạnh nào, ba đỉnh vẫn liên thông. Tuy nhiên:

- Bỏ cạnh trọng số **9**: giữ các cạnh **1** và **2**, tổng MST bằng **3**.
- Bỏ cạnh trọng số **1**: giữ các cạnh **2** và **9**, tổng bằng **11**; đồ thị vẫn liên thông nhưng **không còn cây khung trọng số 3**.
- Bỏ cạnh trọng số **2**: giữ các cạnh **1** và **9**, tổng bằng **10**, cũng không tối ưu.

Do đó, “cạnh thuộc một chu trình” là điều kiện để **bỏ mà không làm mất liên thông**; để **bỏ mà không làm tăng trọng số cây khung tối ưu**, phải dùng kết quả mạnh hơn.

Bài học trình bày định nghĩa, định lý chu trình, chứng minh bằng đổi cạnh, quan hệ với tính chất lát cắt, Kruskal và **reverse-delete** (xóa cạnh từ nặng xuống nhẹ). Một chương trình **Java 17** hoàn chỉnh sẽ so sánh các cách dựng MST và kiểm chứng bằng vét cạn.

## 2. Định nghĩa chính xác: cây khung và MST

Xét đồ thị vô hướng `G=(V,E)` với `n=|V|\ge1`. Mỗi cạnh vật lý `e` có hai đầu `u,v` và trọng số `w(e)`.

**Cây khung (spanning tree)** là tập cạnh `T\subseteq E` sao cho:

- Mọi đỉnh thuộc `V` đều được giữ.
- Đồ thị `(V,T)` **liên thông**.
- Đồ thị `(V,T)` **không chứa chu trình**.

Tương đương, khi `n\ge1`, một đồ thị vô hướng là cây khi liên thông và có đúng **`n-1` cạnh**. Vì vậy mọi cây khung đều dùng **đúng `n-1` cạnh**.

Trọng số của cây khung:

\[
W(T)=\sum_{e\in T}w(e).
\]

Một **cây khung nhỏ nhất** là cây khung `T^*` có:

\[
W(T^*)=\min_{\substack{T\subseteq E\\(V,T)\text{ là cây}}}W(T).
\]

**Điều kiện tồn tại:** đồ thị vô hướng phải liên thông (bỏ qua khuyên vì khuyên không nối thêm đỉnh khác). Nếu đồ thị không liên thông, không có **một MST cho toàn bộ `V`**. Ta có thể tìm **rừng khung nhỏ nhất (Minimum Spanning Forest, MSF)** cho từng thành phần, nhưng phải gọi đúng tên bài toán.

### Các tình huống vẫn hợp lệ

- **Trọng số âm:** MST vẫn có nghĩa; các chứng minh chỉ dùng so sánh trọng số, không yêu cầu trọng số dương.
- **Trọng số bằng nhau:** có thể có **nhiều MST khác nhau** cùng tổng tối ưu.
- **Cạnh song song:** hai cạnh vật lý cùng nối `u,v` vẫn là **hai cạnh khác nhau**, có thể tạo chu trình độ dài hai trong đa đồ thị.
- **Khuyên:** cạnh `u--u` là chu trình độ dài một và **không nằm trong bất kỳ cây khung nào**, bất kể trọng số.
- **Một đỉnh `n=1`:** cây khung rỗng là hợp lệ, có tổng trọng số `0`. Mọi khuyên đều được bỏ.
- **Đồ thị có hướng:** MST vô hướng không áp dụng nguyên xi. Những bài về **arborescence/cây khung có hướng** có định nghĩa và thuật toán riêng.

Trong bài này, **ID cạnh** là vị trí của cạnh trong danh sách đầu vào. Hai cạnh song song luôn có ID khác nhau; không được gộp chúng vào một cạnh boolean.

## 3. Mối quan hệ giữa chu trình và cầu: khi nào bỏ cạnh vẫn liên thông?

Một **chu trình** trong đồ thị vô hướng là một hành trình khép kín dùng các cạnh phân biệt, đi qua các đỉnh không lặp trừ đầu/cuối theo định nghĩa chu trình đơn. Trong đa đồ thị, hai cạnh song song tạo được chu trình độ dài hai; một khuyên là chu trình độ dài một.

Một **cầu (bridge)** là cạnh mà khi xóa nó, số thành phần liên thông của đồ thị **tăng lên**.

### Định lý 1: một cạnh bỏ được về mặt liên thông khi và chỉ khi nó không phải cầu

Với một cạnh vật lý `e=\{u,v\}` của đồ thị vô hướng:

\[
\boxed{G-e\text{ không có nhiều thành phần hơn }G
\iff e\text{ nằm trên một chu trình}.}
\]

Nếu `G` ban đầu liên thông, có thể viết ngắn:

\[
\boxed{G-e\text{ vẫn liên thông}
\iff e\text{ nằm trên một chu trình}.}
\]

### Chứng minh chiều “nằm trên chu trình ⇒ bỏ được”

Giả sử `e=\{u,v\}` nằm trên chu trình `C`. Phần còn lại của `C` (bỏ `e`) vẫn cung cấp một đường đi từ `u` tới `v`, sử dụng những cạnh khác.

Mọi đường đi trong đồ thị có dùng `e` có thể thay bước qua `e` bằng đoạn đi vòng trên `C-e`. Nhờ thế, sau khi xóa `e`, các đỉnh trước đây có liên thông vẫn liên thông. Số thành phần không tăng.

**Khuyên:** `u=v`; xóa khuyên không ảnh hưởng khả năng đi từ hai đỉnh khác nhau, nên nó luôn bỏ được.

### Chứng minh chiều “bỏ được ⇒ nằm trên chu trình”

Giả sử xóa `e=\{u,v\}` mà `u` và `v` vẫn nối được bằng một đường đi trong `G-e`. Đường đi này cộng với cạnh `e` tạo thành một chu trình chứa `e`.

Nếu `u=v`, chính `e` là khuyên, vốn được xem là chu trình độ dài một.

Vậy hai chiều đều đúng.

### Phân biệt với phép xóa cạnh khỏi một cây

**Mọi cạnh của một cây đều là cầu trong chính cây đó**. Vì cây không có chu trình, xóa một cạnh sẽ chia cây thành hai thành phần.

Cạnh `e` có thể nằm trên chu trình của **đồ thị gốc `G`** và có thể xóa khỏi `G` mà vẫn liên thông, nhưng nếu `e` đã nằm trong một **cây khung `T`** thì không thể chỉ xóa `e` khỏi `T` rồi tuyên bố vẫn có cây khung. Muốn thay `e`, phải thêm một cạnh khác nối hai thành phần của `T-e`.

Đây là chỗ tính chất **đổi cạnh (exchange)** xuất hiện.

## 4. Tính chất chu trình của MST: cạnh nặng nhất có thể loại thế nào?

Xét một chu trình `C` của đồ thị vô hướng có trọng số. Gọi `e` là **một cạnh có trọng số lớn nhất trên `C`**:

\[
w(e)=\max_{f\in C}w(f).
\]

Cần phân biệt **nặng nhất duy nhất** và **đồng hạng nặng nhất**.

### Định lý 2A — nặng nhất duy nhất: không thuộc bất kỳ MST nào

Nếu `e` là cạnh có trọng số **lớn hơn nghiêm ngặt mọi cạnh khác** trong **một chu trình `C`**, thì:

\[
\boxed{e\text{ không xuất hiện trong bất kỳ MST nào}.}
\]

Chỉ cần tồn tại **một chu trình** mà `e` là cạnh nặng nhất **duy nhất**, không cần kiểm tra mọi chu trình của đồ thị.

Ví dụ: tam giác với trọng số `1,2,9`. Cạnh `9` nặng nhất duy nhất trong chu trình ba cạnh, nên không có MST nào chứa nó.

### Định lý 2B — đồng hạng nặng nhất: có một MST không chứa cạnh đó

Nếu `e` là **một trong các cạnh nặng nhất** của chu trình (có thể hòa), thì:

\[
\boxed{\text{Tồn tại ít nhất một MST không chứa }e.}
\]

Đây là phát biểu **yếu hơn**: không thể kết luận `e` bị loại khỏi **mọi** MST.

Ví dụ tam giác có trọng số `5,5,5`:

- Bất kỳ hai cạnh nào cũng tạo một MST trọng số `10`.
- Với mỗi cạnh cụ thể `e`, có một MST **không dùng** `e`.
- Đồng thời `e` cũng thuộc **một số MST khác**.

**Câu nói “mọi cạnh nặng nhất trên một chu trình đều không nằm trong MST” là sai khi có hòa trọng số.** Phải nói “có thể bỏ cạnh nặng nhất để vẫn tồn tại ít nhất một MST” hoặc thêm điều kiện “nặng nhất duy nhất” để nói “không thuộc bất kỳ MST nào”.

## 5. Chứng minh tính chất chu trình bằng phép đổi cạnh

Chứng minh sau là cốt lõi của chủ đề. Nó cũng giải thích chính xác tại sao ta được phép xóa cạnh nặng mà không làm xấu kết quả tối ưu.

Giả sử `T` là một MST và `e=\{u,v\}` nằm trên chu trình `C` của đồ thị gốc.

### Bước 1: nếu `e\notin T` thì không cần làm gì

Bản thân `T` đã là một MST không chứa `e`. Vậy ta chỉ cần xét trường hợp `e\in T`.

### Bước 2: xóa `e` khỏi cây `T`

Vì `T` là cây, xóa một cạnh chia nó thành đúng hai thành phần, gọi là `A` và `B`. Hai đầu `u,v` của `e` nằm ở hai phía khác nhau.

Không còn đường đi giữa `A` và `B` trong `T-e`.

### Bước 3: tìm cạnh `f` khác `e` trên chu trình `C` nối hai phía

Chu trình `C` chứa `e` và còn một đường đi từ `u` tới `v` bằng những cạnh **khác `e`**. Đường đi này bắt đầu trong `A` và kết thúc trong `B`, nên phải có ít nhất một cạnh `f` đi từ `A` sang `B`.

Vì `T-e` không còn cạnh nối hai thành phần, `f` **không thể thuộc `T-e`**.

### Bước 4: đổi `e` lấy `f`

Đặt:

\[
T'=(T-\{e\})\cup\{f\}.
\]

Tập `T'` có đúng `n-1` cạnh, nối lại hai thành phần `A,B`, nên là một cây khung.

Vì `e` là cạnh nặng nhất của `C`:

\[
w(f)\le w(e).
\]

Suy ra:

\[
W(T')=W(T)-w(e)+w(f)\le W(T).
\]

Nhưng `T` đã tối ưu, nên không thể có cây khung nào nhẹ hơn `T`. Do đó phải có:

\[
W(T')=W(T).
\]

Vậy `T'` là một MST không chứa `e`. Điều này chứng minh **định lý 2B**, kể cả khi trọng số có hòa.

### Trường hợp nặng nhất duy nhất

Nếu `w(e)>w(f)` với mọi cạnh `f\ne e` trên `C`, ta có:

\[
W(T')<W(T),
\]

mâu thuẫn với tính tối ưu của `T`. Vậy giả thiết `e\in T` là không thể xảy ra: **không có MST nào chứa `e`**. Đây là **định lý 2A**.

### Bất biến cần nhớ

Phép đổi cạnh **không chỉ thay một con số**. Ta phải chứng minh tập cạnh mới:

1. Vẫn gồm đủ mọi đỉnh.
2. Vẫn liên thông.
3. Không tạo chu trình.
4. Có tổng trọng số **không lớn hơn** cây cũ.

Thiếu bước nối lại hai thành phần thì chưa chứng minh được `T'` là một cây khung hợp lệ.

## 6. Ba câu hỏi “có thể loại bỏ cạnh e không?” hoàn toàn khác nhau

Giả sử `G` liên thông và `e` là một cạnh của `G`.

| Câu hỏi | Điều kiện cần và đủ | Ý nghĩa |
|---|---|---|
| **A.** Xóa `e` mà đồ thị vẫn liên thông? | `e` nằm trên một chu trình của `G`, tức không phải cầu | Không quan tâm tổng trọng số |
| **B.** Xóa `e` mà vẫn tồn tại MST có **cùng trọng số tối ưu**? | Tồn tại ít nhất một MST của `G` không chứa `e` | Có thể chọn lời giải tối ưu khác |
| **C.** `e` không thể xuất hiện trong **bất kỳ** MST nào? | Với cạnh không phải khuyên, có đường nối hai đầu `e` bằng các cạnh **nhẹ hơn nghiêm ngặt `e`**; tương đương `e` là cạnh nặng nhất duy nhất trong một chu trình | Mạnh hơn câu B |

Điều kiện C cũng đúng với khuyên nếu xem chính khuyên là chu trình độ dài một; trong cài đặt thực tế có thể xử lý khuyên riêng, không cần nói tới đường giữa hai đầu.

### 6.1. Kiểm tra B bằng trọng số MST sau khi xóa cạnh

Gọi:

\[
M(G)=\text{trọng số một MST của }G.
\]

Nếu `G-e` không liên thông, đặt `M(G-e)` là “không tồn tại”. Khi `G` liên thông:

\[
\boxed{
e\text{ có thể bỏ mà vẫn giữ tối ưu}
\iff M(G-e)=M(G).
}
\]

Giải thích:

- Nếu có một MST `T` không chứa `e`, thì `T` vẫn là cây khung trong `G-e`; trọng số tối ưu ở đó không thể lớn hơn `M(G)` và cũng không thể nhỏ hơn vì `G-e` có ít lựa chọn hơn. Vậy bằng nhau.
- Ngược lại, nếu `G-e` có MST trọng số bằng `M(G)`, chính MST đó là một cây khung tối ưu của `G` không dùng `e`.

Cạnh có tính chất **không thể bỏ mà vẫn giữ tối ưu** được gọi là **critical edge** đối với MST (cạnh thiết yếu): bỏ nó làm đồ thị không còn cây khung hoặc làm trọng số MST tăng.

Điều này khác với **cầu**:

- Mọi cầu đều thiết yếu trong **mọi** cây khung, nên cũng là cạnh critical của MST.
- Nhưng một cạnh không phải cầu **vẫn có thể critical** nếu mọi đường thay thế đều đắt hơn.

### 6.2. Ví dụ cạnh không phải cầu nhưng critical

Tam giác có cạnh:

```text
e0: 0--1, weight 1
e1: 1--2, weight 2
e2: 0--2, weight 9
```

Cả ba cạnh đều không phải cầu, vì bỏ một cạnh tam giác vẫn liên thông.

Tuy nhiên:

- MST gốc dùng `e0,e1`, trọng số `3`.
- Nếu xóa `e0`, cây khung buộc dùng `e1,e2`, trọng số `11>3`: **e0 critical**, dù không phải cầu.
- Nếu xóa `e1`, cây khung trọng số `1+9=10>3`: **e1 critical**.
- Nếu xóa `e2`, MST trọng số vẫn `3`: **e2 loại bỏ được mà không thay đổi tối ưu**.

Đó là lý do không thể chỉ chạy thuật toán tìm cầu rồi kết luận mọi cạnh không phải cầu đều có thể xóa mà giữ nguyên MST.

### 6.3. Kiểm tra B/C bằng đường thay thế theo ngưỡng trọng số

Cho cạnh không phải khuyên `e=\{u,v\}`, xét **những cạnh khác `e`** có trọng số không vượt một ngưỡng.

- `e` **không nằm trong bất kỳ MST nào** nếu và chỉ nếu tồn tại một đường từ `u` tới `v` gồm toàn cạnh có trọng số **nhỏ hơn `w(e)`**.
- `e` **có thể bị bỏ mà vẫn có một MST tối ưu** nếu và chỉ nếu tồn tại một đường từ `u` tới `v` gồm toàn cạnh có trọng số **nhỏ hơn hoặc bằng `w(e)`**.

**Vì sao điều kiện “`\le`” đủ?** Đường thay thế cộng với `e` tạo một chu trình mà `e` là một cạnh nặng nhất, nên định lý 2B bảo đảm tồn tại MST không có `e`.

**Vì sao cũng cần?** Giả sử có MST `T` không chứa `e`. Trên `T` có đường duy nhất từ `u` tới `v`. Nếu đường đó có cạnh `f` nặng hơn `e`, thay `f` bằng `e` sẽ tạo cây khung nhẹ hơn `T`, mâu thuẫn tối ưu. Vậy mọi cạnh trên đường này có trọng số `\le w(e)`.

**Vì sao điều kiện “`<`” tương ứng với không thuộc bất kỳ MST?** Nếu có đường chỉ gồm cạnh nhẹ hơn `e`, `e` là nặng nhất duy nhất trong chu trình, nên bị loại khỏi mọi MST. Ngược lại, nếu không có đường gồm cạnh nhẹ hơn, thành phần liên thông của `u` và `v` trong đồ thị chỉ chứa những cạnh nhẹ hơn là khác nhau. Khi thêm các cạnh trọng số bằng `w(e)`, tồn tại cách chạy Kruskal chọn `e` để nối hai thành phần ấy, nên có ít nhất một MST chứa `e`.

Hai tiêu chuẩn này rất hữu ích khi **phân loại cạnh critical/optional/never-used**, nhưng không bắt buộc phải dựng toàn bộ MST rồi xóa từng cạnh.

### 6.4. Cạnh optional và cạnh không xuất hiện trong MST

Nếu `e` có thể bị xóa mà trọng số tối ưu giữ nguyên, có **hai khả năng**:

- `e` thuộc **một số MST nhưng không thuộc tất cả**: **optional/pseudo-critical** theo cách đặt tên phổ biến.
- `e` **không thuộc MST nào**: cạnh hoàn toàn không cần cho lời giải tối ưu.

Một phép thử “xóa cạnh và so trọng số MST” **không phân biệt** được hai loại này. Muốn biết cạnh có nằm trong **ít nhất một MST** không, dùng tiêu chuẩn đường thay thế **nhẹ hơn nghiêm ngặt** hoặc thử **ép chọn cạnh `e`** rồi tối ưu phần còn lại.

Đừng nhầm:
- “Xóa `e` mà đồ thị vẫn liên thông”;
- “Có MST không chứa `e`”;
- “Không MST nào chứa `e`”.

Ba phát biểu có sức mạnh logic khác nhau.

## 7. Các trường hợp có trọng số bằng nhau, âm, cạnh song song và khuyên

### 7.1. Tam giác đồng trọng số

```text
e0: 0--1 (5)
e1: 1--2 (5)
e2: 0--2 (5)
```

Có ba MST, lần lượt bỏ một trong ba cạnh; tất cả có tổng `10`. Mỗi cạnh **có thể bị loại** mà vẫn có một MST tối ưu, nhưng **không có cạnh nào chắc chắn vắng mặt trong mọi MST**.

Nếu thuật toán **reverse-delete** xử lý `e2` trước, nó có thể bỏ `e2` và giữ `e0,e1`. Nếu đổi tie-break, một MST khác có thể được chọn. **Cùng trọng số tối ưu** không đòi hỏi cùng tập ID.

### 7.2. Trọng số âm không làm sai tính chất chu trình

```text
e0: 0--1 (-5)
e1: 1--2 ( 2)
e2: 0--2 ( 4)
```

Cạnh `e2` trọng số `4` là nặng nhất duy nhất nên không xuất hiện trong MST. MST dùng `e0,e1` với tổng:

\[
-5+2=-3.
\]

Không có yêu cầu rằng MST phải có tổng dương. Cũng không được loại một cạnh chỉ vì trọng số của nó âm/dương; phải so sánh **với các cạnh thay thế trên chu trình hoặc lát cắt**.

### 7.3. Cạnh song song

Giả sử có hai cạnh vật lý:

```text
e0: 0--1 (3)
e1: 0--1 (8)
```

Hai cạnh tạo thành một chu trình độ dài hai trong **đa đồ thị**. `e1` nặng nhất duy nhất, nên không thuộc MST; `e0` là cạnh cần giữ để nối hai đỉnh.

Nếu dùng `HashSet` của cặp đỉnh `(0,1)` và chỉ lưu một cạnh thì có thể vô tình xóa mất cạnh rẻ hơn hoặc hiểu sai chu trình. Mỗi cạnh phải có ID riêng.

### 7.4. Khuyên có trọng số rất âm

```text
e0: 0--0 (-100)
e1: 0--1 (3)
```

Khuyên `e0` không giúp nối các đỉnh khác nhau nên **không nằm trong cây khung**, dù `-100` rất nhỏ. MST của hai đỉnh phải dùng `e1`, tổng `3`.

Điều này cho thấy không thể lấy “`n-1` cạnh nhẹ nhất theo trọng số” một cách mù quáng. Cần kiểm tra cạnh có gây chu trình trong tập chọn không; khuyên tự nó gây chu trình.

### 7.5. MST không nhất thiết duy nhất dù có cạnh critical

Một đồ thị có thể vừa có **cạnh bắt buộc** vừa có **vùng hòa**. Ví dụ nối hai cụm đỉnh bằng một cầu rẻ rồi đặt tam giác đồng trọng số trong mỗi cụm: cầu thuộc **mọi MST**, nhưng trong mỗi tam giác có nhiều cách chọn hai cạnh.

Số MST có thể lớn; mục tiêu thông thường chỉ yêu cầu **một MST** hoặc **trọng số nhỏ nhất**, không yêu cầu liệt kê tất cả. Đừng khẳng định một cạnh không được chọn bởi **một lần chạy Kruskal** thì cạnh đó không thể thuộc bất kỳ MST nào.

## 8. Liên hệ với tính chất lát cắt (cut property)

Một **lát cắt (cut)** chia tập đỉnh thành hai phần khác rỗng `A` và `B=V\setminus A`. **Cạnh băng qua lát cắt** là cạnh có một đầu trong `A` và một đầu trong `B`.

**Tính chất lát cắt:**

> Nếu `e` là **một cạnh nhẹ nhất** băng qua một lát cắt, thì tồn tại **ít nhất một MST** chứa `e`.

Nếu `e` là cạnh **nhẹ nhất duy nhất** băng qua lát cắt, thì `e` nằm trong **mọi MST**.

### Chứng minh đổi cạnh cho lát cắt

Giả sử `T` là MST không chứa `e`. Thêm `e` vào `T` tạo một chu trình, vì `T` vốn là cây. Chu trình này phải có một cạnh `f` khác `e` cũng băng qua lát cắt: bất kỳ chu trình nào đi từ `A` sang `B` phải trở lại `A`.

Xóa `f`, ta lại được cây khung:

\[
T'=(T+\{e\})-\{f\}.
\]

Do `e` nhẹ nhất trên lát cắt, `w(e)\le w(f)`, nên `W(T')\le W(T)`. Nếu `T` tối ưu thì bằng nhau, vậy có MST chứa `e`.

Nếu `e` là nhẹ nhất **duy nhất**, `w(e)<w(f)`; giả thiết `T` không chứa `e` dẫn tới cây nhẹ hơn `T`, mâu thuẫn. Vậy mọi MST phải chứa `e`.

### Hai tính chất bổ sung nhau

- **Chu trình:** cạnh **nặng nhất** là ứng viên **bỏ đi**; nếu nặng nhất duy nhất, bỏ khỏi **mọi MST**.
- **Lát cắt:** cạnh **nhẹ nhất** là ứng viên **giữ lại**; nếu nhẹ nhất duy nhất, thuộc **mọi MST**.

Chúng phản ánh cùng một nguyên lý **đổi cạnh**. Không được đảo nhầm “nặng nhất” thành “nhẹ nhất” trên chu trình hoặc ngược lại trên lát cắt.

### Tất cả trọng số phân biệt thì sao?

Nếu tất cả các cạnh có **trọng số khác nhau**, MST là **duy nhất**. Có thể chứng minh bằng cách giả sử hai MST khác nhau, lấy cạnh nhẹ nhất thuộc một trong hai nhưng không thuộc cây kia, rồi dùng tính chất lát cắt/đổi cạnh tạo mâu thuẫn.

**Chiều ngược lại không đúng:** MST vẫn có thể duy nhất dù có các cạnh bằng trọng số ở vị trí không tạo được lựa chọn thay thế tối ưu.

## 9. Kruskal nhìn dưới tính chất chu trình

**Kruskal** xử lý các cạnh theo **trọng số tăng dần** và chỉ giữ cạnh nối **hai thành phần khác nhau** của tập cạnh đã chọn.

Pseudocode:

```text
sort edges by increasing weight
DSU = mỗi đỉnh là một thành phần
chosen = empty

for each edge e=(u,v,w):
    if DSU.find(u) != DSU.find(v):
        chosen.add(e)
        DSU.union(u,v)
    else:
        bỏ qua e vì thêm e tạo chu trình

nếu chosen.size == n-1:
    chosen là một MST của đồ thị liên thông
ngược lại:
    đồ thị không có cây khung toàn cục
```

### Vì sao bỏ cạnh khi tạo chu trình là an toàn?

Khi Kruskal xét một cạnh `e` có hai đầu đã nằm trong **cùng một thành phần DSU**, tập cạnh đã chọn có một đường đi nối hai đầu `e`.

Tất cả cạnh trên đường này đã được xét và được chọn trước `e` trong thứ tự trọng số **không giảm**, nên:

\[
w(f)\le w(e)
\]

với mọi cạnh `f` trên đường đi đó.

Thêm `e` sẽ tạo chu trình mà `e` là **một cạnh nặng nhất**. Theo tính chất chu trình, tồn tại một MST không cần `e`. Do đó bỏ `e` không làm mất **khả năng đạt trọng số tối ưu**.

Nếu các trọng số hòa nhau, `e` có thể thuộc MST khác; Kruskal chỉ chọn **một** MST phù hợp với quy tắc phá hòa.

### Vai trò của DSU

**Disjoint Set Union (Union–Find)** duy trì các thành phần liên thông của tập cạnh đã chọn. Hai thao tác:

- `find(x)`: tìm đại diện của thành phần chứa `x`.
- `union(u,v)`: gộp hai thành phần; trả false nếu chúng đã chung thành phần.

Với **path compression** và **union by size**, chi phí trung bình khấu hao của mỗi phép toán gần hằng, chặt hơn là `O(\alpha(n))`, với `\alpha` là hàm Ackermann nghịch đảo tăng rất chậm.

Kruskal sắp cạnh `O(m\log m)` rồi xử lý khoảng `m` phép DSU, tổng thường viết:

\[
\boxed{O(m\log m+m\alpha(n))}
\]

với `m=|E|` và `n=|V|`.

### Vì sao Kruskal không bỏ “cạnh nhẹ nhất trên chu trình”?

Giả sử đang có cạnh `0--1` trọng số `1` và `1--2` trọng số `2`. Cạnh `0--2` trọng số `9` đến sau. Nếu giữ `9` rồi bỏ `1` chỉ vì vẫn không còn chu trình, cây thu được nặng hơn. Kruskal chọn cạnh nhỏ trước; khi chu trình xuất hiện, **cạnh đến sau** (một cạnh nặng nhất của chu trình hiện thời) mới bị bỏ.

## 10. Reverse-delete: xóa từ nặng xuống nhẹ

Thuật toán **reverse-delete** là cách thể hiện trực tiếp tính chất chu trình.

Ý tưởng:

1. Ban đầu giữ **tất cả các cạnh** của đồ thị liên thông.
2. Sắp cạnh theo **trọng số giảm dần**.
3. Lần lượt xét cạnh `e` theo thứ tự đó.
4. **Nếu xóa `e` mà đồ thị các cạnh đang giữ vẫn liên thông**, thì xóa `e`.
5. Nếu xóa `e` làm mất liên thông, giữ lại.
6. Khi xét xong, các cạnh còn lại tạo thành một MST.

Pseudocode:

```text
keep[e] = true với mọi cạnh
sort edges by weight descending

for e in sorted edges:
    keep[e] = false
    if graph of kept edges is disconnected:
        keep[e] = true

return all edges with keep[e] == true
```

**Lưu ý:** điều kiện liên thông được kiểm tra trên **đồ thị hiện tại sau các lần xóa trước**, không phải luôn kiểm tra trên đồ thị gốc. Nếu chỉ kiểm tra “cạnh có nằm trong chu trình của đồ thị gốc không” rồi xóa đồng loạt, ta có thể xóa **quá nhiều** cạnh và làm đồ thị mất kết nối.

### 10.1. Vì sao khi xóa được, cạnh đang xét là nặng nhất trong một chu trình còn lại?

Giả sử đang xét `e` và xóa nó không làm mất liên thông. Vậy `e` nằm trên một chu trình trong đồ thị hiện tại.

Mọi cạnh **nặng hơn `e`** đã được xét trước:

- Nếu một cạnh nặng hơn đã bị xóa, nó không còn trong chu trình hiện tại.
- Nếu một cạnh nặng hơn đã được giữ lại, tại thời điểm xét nó là **cầu trong đồ thị đang giữ**. Việc chỉ xóa thêm các cạnh sau này không thể tạo một đường thay thế mới, nên cạnh ấy vẫn là cầu ở mọi thời điểm tiếp theo. Một cầu **không thể** nằm trên chu trình hiện tại.

Vì vậy mọi cạnh khác trên chu trình đang xét có trọng số **không lớn hơn `w(e)`**. Cạnh `e` là một cạnh nặng nhất của chu trình; theo tính chất chu trình, ta có thể bỏ `e` mà vẫn giữ được ít nhất một MST tối ưu.

### 10.2. Bất biến: vẫn có một MST tối ưu trong những cạnh còn giữ

Ban đầu đồ thị gốc chứa ít nhất một MST. Mỗi lần reverse-delete xóa cạnh `e`:

- Cạnh `e` nằm trên một chu trình của đồ thị đang giữ.
- Trong chu trình đó `e` là một cạnh nặng nhất.
- Tính chất chu trình bảo đảm có **một MST** của đồ thị hiện tại không cần `e`, với cùng trọng số tối ưu.

Vậy sau khi xóa, vẫn còn ít nhất một MST với trọng số tối ưu ban đầu. Nếu không xóa, tập cạnh giữ nguyên và bất biến vẫn đúng.

### 10.3. Vì sao cuối cùng không còn chu trình?

Giả sử cuối cùng vẫn còn một chu trình `C`. Xét cạnh `e` của `C` được duyệt **sớm nhất** trong thứ tự reverse-delete. Khi xét `e`, toàn bộ các cạnh của `C` vẫn đang tồn tại (vì cuối cùng chúng đều còn). Do đó xóa `e` vẫn không làm mất liên thông, và thuật toán đáng lẽ phải xóa nó — mâu thuẫn.

Vậy đồ thị cuối **không có chu trình**. Vì reverse-delete luôn duy trì liên thông, kết quả là một cây khung. Theo bất biến, cây ấy có đúng trọng số MST tối ưu.

### 10.4. Vòng lặp và hòa trọng số

Reverse-delete có thể chọn một MST khác Kruskal khi có cạnh đồng trọng số. **Không được coi hai tập edge ID khác nhau là lỗi** nếu cả hai là cây khung và có cùng tổng nhỏ nhất.

Nếu cần đầu ra tái lập, có thể phá hòa theo ID: khi hai cạnh có trọng số bằng nhau, reverse-delete xét ID **lớn trước**. Với quy tắc này, kết quả thường trùng với Kruskal xét ID **nhỏ trước**, nhưng tính đúng **không** phụ thuộc vào việc hai cách chọn giống nhau.

## 11. Java 17+ hoàn chỉnh: Kruskal, reverse-delete, kiểm tra loại cạnh

Chương trình sử dụng:

- `Edge(u,v,weight)`: cạnh vô hướng; ID cạnh là **chỉ số trong `List<Edge>`**.
- `Tree(total,edgeIds)`: tổng trọng số và danh sách các ID thuộc cây khung. `total` là **`BigInteger`** để tránh tràn khi cộng nhiều trọng số kiểu `long`.
- `kruskal`: xây MST bằng DSU, trả `null` nếu đồ thị không liên thông.
- `reverseDelete`: xét cạnh giảm dần, chỉ xóa khi còn liên thông.
- `removableForConnectivity`: kiểm tra một cạnh có thể xóa mà đồ thị vẫn liên thông hay không.
- `removableWithoutCostIncrease`: kiểm tra sau khi xóa cạnh còn MST có **cùng tổng tối ưu** hay không.
- `bruteForce`: chỉ dùng làm oracle cho đồ thị nhỏ; thử mọi tập cạnh kích thước `n-1`, kiểm tra cây và lấy tổng nhỏ nhất.
- `main`: in các ví dụ cân nặng khác nhau, cạnh song song/khuyên, đồ thị không liên thông và chạy kiểm thử ngẫu nhiên có seed.

**Hợp đồng đầu vào:** `n\ge1`; `edges` không null, không chứa phần tử null; mọi đầu mút nằm trong `[0,n-1]`; cho phép trọng số âm, trọng số bằng nhau, khuyên và cạnh song song. Với `n=1`, cây khung rỗng có tổng `0`. Hai API dựng MST trả `null` khi đồ thị không liên thông, thay vì tự động trả một rừng khung rồi gọi nhầm là MST.

**Tên tệp:** `MstCyclePropertyDemo.java`.

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Random;

public final class MstCyclePropertyDemo {
    private MstCyclePropertyDemo() {
    }

    public record Edge(int u, int v, long weight) {
    }

    public record Tree(
            BigInteger total, List<Integer> edgeIds) {
        public Tree {
            Objects.requireNonNull(total, "total");
            edgeIds = List.copyOf(edgeIds);
        }
    }

    private static final class DSU {
        final int[] parent;
        final int[] size;
        int components;

        DSU(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;
            Arrays.fill(size, 1);
            for (int i = 0; i < n; i++) {
                parent[i] = i;
            }
        }

        int find(int x) {
            if (parent[x] != x) {
                parent[x] = find(parent[x]);
            }
            return parent[x];
        }

        boolean union(int a, int b) {
            int ra = find(a);
            int rb = find(b);
            if (ra == rb) {
                return false;
            }
            if (size[ra] < size[rb]) {
                int temp = ra;
                ra = rb;
                rb = temp;
            }
            parent[rb] = ra;
            size[ra] += size[rb];
            components--;
            return true;
        }
    }

    private static void check(
            int n, List<Edge> edges) {
        Objects.requireNonNull(edges, "edges");
        if (n < 1) {
            throw new IllegalArgumentException(
                "this demo requires n >= 1"
            );
        }
        for (Edge e : edges) {
            Objects.requireNonNull(e, "edge");
            if (e.u() < 0 || e.u() >= n
                    || e.v() < 0 || e.v() >= n) {
                throw new IllegalArgumentException(
                    "edge endpoint out of range"
                );
            }
        }
    }

    private static void checkEdgeId(
            List<Edge> edges, int edgeId) {
        if (edgeId < 0 || edgeId >= edges.size()) {
            throw new IllegalArgumentException(
                "invalid edge ID"
            );
        }
    }

    // Kruskal, bỏ một ID nếu forbiddenId >= 0.
    // null nghĩa là không còn cây khung cho toàn bộ n đỉnh.
    private static Tree kruskalSkipping(
            int n, List<Edge> edges, int forbiddenId) {
        List<Integer> order = new ArrayList<>();
        for (int id = 0; id < edges.size(); id++) {
            if (id != forbiddenId) {
                order.add(id);
            }
        }

        order.sort((a, b) -> {
            int cmp = Long.compare(
                edges.get(a).weight(),
                edges.get(b).weight()
            );
            return cmp != 0 ? cmp : Integer.compare(a, b);
        });

        DSU dsu = new DSU(n);
        List<Integer> selected = new ArrayList<>();
        BigInteger total = BigInteger.ZERO;

        for (int id : order) {
            Edge e = edges.get(id);
            if (dsu.union(e.u(), e.v())) {
                selected.add(id);
                total = total.add(
                    BigInteger.valueOf(e.weight())
                );
                if (selected.size() == n - 1) {
                    break;
                }
            }
        }
        if (selected.size() != n - 1) {
            return null;
        }

        Collections.sort(selected);
        return new Tree(total, selected);
    }

    public static Tree kruskal(
            int n, List<Edge> edges) {
        check(n, edges);
        return kruskalSkipping(n, edges, -1);
    }

    // Kết nối khi chỉ dùng các ID còn giữ, trừ bannedId.
    private static boolean connectedKeeping(
            int n, List<Edge> edges,
            boolean[] keep, int bannedId) {
        DSU dsu = new DSU(n);
        for (int id = 0; id < edges.size(); id++) {
            if (keep[id] && id != bannedId) {
                Edge e = edges.get(id);
                dsu.union(e.u(), e.v());
            }
        }
        return dsu.components == 1;
    }

    public static Tree reverseDelete(
            int n, List<Edge> edges) {
        check(n, edges);
        if (kruskalSkipping(n, edges, -1) == null) {
            return null; // Đồ thị không liên thông.
        }

        int m = edges.size();
        boolean[] keep = new boolean[m];
        Arrays.fill(keep, true);

        List<Integer> order = new ArrayList<>();
        for (int id = 0; id < m; id++) {
            order.add(id);
        }

        // Trọng số giảm; hòa trọng số thì ID lớn xét trước.
        order.sort((a, b) -> {
            int cmp = Long.compare(
                edges.get(b).weight(),
                edges.get(a).weight()
            );
            return cmp != 0 ? cmp : Integer.compare(b, a);
        });

        for (int id : order) {
            if (connectedKeeping(n, edges, keep, id)) {
                keep[id] = false;
            }
        }

        List<Integer> selected = new ArrayList<>();
        BigInteger total = BigInteger.ZERO;

        for (int id = 0; id < m; id++) {
            if (keep[id]) {
                selected.add(id);
                total = total.add(
                    BigInteger.valueOf(edges.get(id).weight())
                );
            }
        }
        if (selected.size() != n - 1) {
            throw new IllegalStateException(
                "reverse-delete did not produce a tree"
            );
        }
        return new Tree(total, selected);
    }

    // Câu hỏi A: xóa một cạnh mà đồ thị vẫn liên thông?
    public static boolean removableForConnectivity(
            int n, List<Edge> edges, int edgeId) {
        check(n, edges);
        checkEdgeId(edges, edgeId);
        if (kruskalSkipping(n, edges, -1) == null) {
            throw new IllegalArgumentException(
                "the graph must be connected"
            );
        }

        boolean[] keep = new boolean[edges.size()];
        Arrays.fill(keep, true);
        return connectedKeeping(n, edges, keep, edgeId);
    }

    // Câu hỏi B: còn một MST với đúng trọng số tối ưu?
    public static boolean removableWithoutCostIncrease(
            int n, List<Edge> edges, int edgeId) {
        check(n, edges);
        checkEdgeId(edges, edgeId);
        Tree best = kruskalSkipping(n, edges, -1);
        if (best == null) {
            throw new IllegalArgumentException(
                "the graph must be connected"
            );
        }
        Tree without = kruskalSkipping(n, edges, edgeId);
        return without != null
            && without.total().equals(best.total());
    }

    // Chỉ dùng cho oracle: duyệt mọi tập con có n-1 ID.
    // Không áp dụng để giải bài lớn.
    public static Tree bruteForce(
            int n, List<Edge> edges, int forbiddenId) {
        check(n, edges);
        if (edges.size() > 16) {
            throw new IllegalArgumentException(
                "bruteForce supports at most 16 edges"
            );
        }

        Tree best = null;
        int m = edges.size();
        long limit = 1L << m;

        for (long mask = 0L; mask < limit; mask++) {
            if (Long.bitCount(mask) != n - 1) {
                continue;
            }
            if (forbiddenId >= 0
                    && (mask & (1L << forbiddenId)) != 0L) {
                continue;
            }

            DSU dsu = new DSU(n);
            List<Integer> selected = new ArrayList<>();
            BigInteger total = BigInteger.ZERO;
            boolean acyclic = true;

            for (int id = 0; id < m; id++) {
                if ((mask & (1L << id)) == 0L) {
                    continue;
                }

                Edge e = edges.get(id);
                if (!dsu.union(e.u(), e.v())) {
                    acyclic = false;
                    break;
                }
                selected.add(id);
                total = total.add(
                    BigInteger.valueOf(e.weight())
                );
            }

            if (acyclic && dsu.components == 1
                    && (best == null
                    || total.compareTo(best.total()) < 0)) {
                best = new Tree(total, selected);
            }
        }
        return best;
    }

    private static boolean sameWeight(Tree a, Tree b) {
        if (a == null || b == null) {
            return a == null && b == null;
        }
        return a.total().equals(b.total());
    }

    // Kiểm tra witness là cây thật và tổng trọng số chính xác.
    private static boolean validTree(
            int n, List<Edge> edges, Tree tree) {
        if (tree == null) {
            return false;
        }
        if (tree.edgeIds().size() != n - 1) {
            return false;
        }

        boolean[] seen = new boolean[edges.size()];
        DSU dsu = new DSU(n);
        BigInteger total = BigInteger.ZERO;

        for (int id : tree.edgeIds()) {
            if (id < 0 || id >= edges.size() || seen[id]) {
                return false;
            }
            seen[id] = true;
            Edge e = edges.get(id);
            if (!dsu.union(e.u(), e.v())) {
                return false;
            }
            total = total.add(
                BigInteger.valueOf(e.weight())
            );
        }
        return dsu.components == 1
            && total.equals(tree.total());
    }

    private static void show(String label, Tree tree) {
        if (tree == null) {
            System.out.println(label + ": NO MST");
        } else {
            System.out.println(
                label + ": weight=" + tree.total()
                + " ids=" + tree.edgeIds()
            );
        }
    }

    public static void main(String[] args) {
        List<Edge> triangle = List.of(
            new Edge(0, 1, 1),
            new Edge(1, 2, 2),
            new Edge(0, 2, 9)
        );
        show("Triangle Kruskal",
            kruskal(3, triangle));
        show("Triangle reverse-delete",
            reverseDelete(3, triangle));
        System.out.println(
            "Edge 0 removable for connectivity: "
            + removableForConnectivity(3, triangle, 0)
        );
        System.out.println(
            "Edge 0 preserves MST weight: "
            + removableWithoutCostIncrease(3, triangle, 0)
        );
        System.out.println(
            "Edge 2 preserves MST weight: "
            + removableWithoutCostIncrease(3, triangle, 2)
        );

        List<Edge> tied = List.of(
            new Edge(0, 1, 5),
            new Edge(1, 2, 5),
            new Edge(0, 2, 5)
        );
        show("Tie triangle MST", kruskal(3, tied));
        System.out.println(
            "Tie edge 0 avoidable in an MST: "
            + removableWithoutCostIncrease(3, tied, 0)
        );

        List<Edge> negative = List.of(
            new Edge(0, 1, -5),
            new Edge(1, 2, 2),
            new Edge(0, 2, 4)
        );
        show("Negative triangle MST",
            reverseDelete(3, negative));

        List<Edge> selfLoop = List.of(
            new Edge(0, 0, -100),
            new Edge(0, 1, 3)
        );
        show("Self-loop MST", kruskal(2, selfLoop));

        List<Edge> huge = List.of(
            new Edge(0, 1, Long.MAX_VALUE),
            new Edge(1, 2, Long.MAX_VALUE)
        );
        show("Large exact sum", kruskal(3, huge));

        List<Edge> disconnected = List.of(
            new Edge(0, 1, 1),
            new Edge(2, 3, 1)
        );
        System.out.println(
            "Disconnected MST exists: "
            + (kruskal(4, disconnected) != null)
        );
        show("One vertex empty MST",
            kruskal(1, List.of()));

        Random random = new Random(303L);
        int checked = 0;
        for (int trial = 0; trial < 300; trial++) {
            int n = 1 + random.nextInt(6);
            int m = random.nextInt(10);
            List<Edge> edges = new ArrayList<>();

            for (int id = 0; id < m; id++) {
                int u = random.nextInt(n);
                int v = random.nextInt(n);
                long w = random.nextInt(21) - 10L;
                edges.add(new Edge(u, v, w));
            }

            Tree oracle = bruteForce(n, edges, -1);
            Tree fast = kruskal(n, edges);
            Tree reverse = reverseDelete(n, edges);

            if (!sameWeight(oracle, fast)
                    || !sameWeight(oracle, reverse)) {
                throw new AssertionError(
                    "MST mismatch in trial " + trial
                );
            }
            if (fast != null
                    && (!validTree(n, edges, fast)
                    || !validTree(n, edges, reverse))) {
                throw new AssertionError(
                    "invalid MST witness"
                );
            }

            // Kiểm tra riêng câu hỏi B cho từng edge ID.
            for (int id = 0; id < m; id++) {
                Tree without =
                    bruteForce(n, edges, id);
                Tree predicted =
                    kruskalSkipping(n, edges, id);
                if (!sameWeight(without, predicted)) {
                    throw new AssertionError(
                        "delete-edge mismatch"
                    );
                }
                if (fast != null) {
                    boolean expected =
                        without != null
                        && without.total().equals(fast.total());
                    boolean actual =
                        removableWithoutCostIncrease(
                            n, edges, id
                        );
                    if (actual != expected) {
                        throw new AssertionError(
                            "avoidability mismatch"
                        );
                    }
                }
            }
            checked++;
        }
        System.out.println(
            "Random brute-force checks: " + checked
        );

        boolean rejected = false;
        try {
            kruskal(2, List.of(new Edge(0, 2, 5)));
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println(
            "Invalid endpoint rejected: " + rejected
        );
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 MstCyclePropertyDemo.java
java MstCyclePropertyDemo
```

**Đầu ra chuẩn:**

```text
Triangle Kruskal: weight=3 ids=[0, 1]
Triangle reverse-delete: weight=3 ids=[0, 1]
Edge 0 removable for connectivity: true
Edge 0 preserves MST weight: false
Edge 2 preserves MST weight: true
Tie triangle MST: weight=10 ids=[0, 1]
Tie edge 0 avoidable in an MST: true
Negative triangle MST: weight=-3 ids=[0, 1]
Self-loop MST: weight=3 ids=[1]
Large exact sum: weight=18446744073709551614 ids=[0, 1]
Disconnected MST exists: false
One vertex empty MST: weight=0 ids=[]
Random brute-force checks: 300
Invalid endpoint rejected: true
```

### Giải thích kết quả chương trình

- **Triangle Kruskal / reverse-delete:** hai thuật toán tìm cùng MST trong tam giác trọng số khác nhau.
- **Edge 0 removable for connectivity: true:** `e0` thuộc chu trình, nên xóa nó vẫn còn đường nối `0` tới `1` qua `2`.
- **Edge 0 preserves MST weight: false:** xóa `e0` khiến MST nhẹ nhất còn lại tăng từ `3` lên `11`.
- **Edge 2 preserves MST weight: true:** `e2` là cạnh nặng nhất duy nhất, không cần cho bất kỳ MST nào.
- **Tie triangle:** các cạnh bằng nhau, nên `e0` có thể được thay bởi cạnh khác cùng trọng số. Kết quả Kruskal chỉ đại diện **một** MST.
- **Negative triangle:** số âm hoàn toàn hợp lệ; MST có tổng `-3`.
- **Self-loop:** khuyên rất âm không được chọn, vì nó không nối hai thành phần.
- **Large exact sum:** hai cạnh có trọng số `Long.MAX_VALUE` tạo tổng **`18446744073709551614`**, vượt `long` có dấu; `BigInteger` giữ chính xác.
- **Disconnected:** không có cây khung toàn đồ thị; hàm trả `null`, không cố gọi một rừng khung là MST.
- **One vertex:** cây khung rỗng có tổng `0`.
- **Random brute-force checks:** đối chiếu **300 đồ thị nhỏ**, gồm cả trường hợp không liên thông, khuyên, cạnh song song, hòa và âm.

### Vì sao code không dùng phép trừ hai trọng số để sắp xếp?

Nếu dùng:

```java
// Không nên: có thể tràn ngay trong comparator.
return (int) (a.weight() - b.weight());
```

hai số `long` lớn có thể bị tràn hoặc cắt xuống `int`, khiến thứ tự sắp sai. Mã dùng **`Long.compare`**, xử lý đúng cả `Long.MIN_VALUE` lẫn `Long.MAX_VALUE`.

### Vì sao phải dùng BigInteger cho tổng MST?

Mỗi trọng số riêng lẻ có thể nằm trong `long` nhưng tổng của `n-1` cạnh có thể vượt phạm vi `long`. `BigInteger` bảo toàn tổng chính xác, kể cả khi có nhiều cạnh âm lớn.

Nếu đề thi cam kết tổng nằm trong `long`, có thể dùng `long` cho hiệu năng; nếu không, hoặc phải dùng kiểu rộng hơn, hoặc dùng `Math.addExact` để phát hiện tràn thay vì chấp nhận kết quả sai âm thầm.

### Vì sao không kiểm tra trùng ID bằng cặp đầu mút?

Một đa đồ thị có thể chứa hai `Edge(0,1,5)` **giống hệt nội dung** nhưng vẫn là **hai cạnh vật lý** khác nhau. Vòng qua `id=0..m-1` giữ đúng từng cạnh. `DSU` chỉ kiểm tra thêm cạnh có tạo chu trình trong tập đang chọn hay không, chứ không tự xóa bản sao khỏi dữ liệu gốc.

## 12. Chứng minh tính đúng của hai thuật toán trong mã

### 12.1. Kruskal: giữ một phần của MST ở mỗi bước

Kruskal sắp cạnh tăng dần. Bất biến quan trọng: sau khi xử lý một số cạnh, tập cạnh đã chọn là **rừng** và có thể mở rộng thành **ít nhất một MST**.

Giả sử chọn cạnh `e` nối hai thành phần khác nhau của rừng. Vì `e` là cạnh rẻ nhất đang có thể nối hai thành phần theo thứ tự quét, tính chất lát cắt/đổi cạnh bảo đảm tồn tại MST chứa rừng hiện tại cùng cạnh `e`. Việc chọn `e` không khóa mất mọi lời giải tối ưu.

Nếu `e` nối hai đỉnh đã thuộc cùng thành phần, thêm nó tạo chu trình trong rừng cộng `e`. Tất cả cạnh trên đường của rừng có trọng số không lớn hơn `e`, nên định lý chu trình bảo đảm `e` có thể bị bỏ mà vẫn còn MST tối ưu.

Kết thúc, nếu có `n-1` cạnh, rừng đã liên thông và là MST. Nếu không đủ, đồ thị không liên thông, nên không tồn tại MST toàn đồ thị.

### 12.2. Reverse-delete: xóa nặng trước, vẫn giữ được tối ưu

Reverse-delete bắt đầu từ toàn bộ đồ thị liên thông. Nếu một cạnh không thể xóa vì làm mất liên thông thì giữ; nó là cầu của đồ thị đang giữ. Xóa các cạnh khác trong tương lai **không thể tạo thêm một đường thay thế** cho cầu này, nên nó luôn cần thiết để giữ liên thông về sau.

Nếu có thể xóa `e`, nó nằm trên một chu trình hiện tại. Các cạnh nặng hơn `e` đã xét trước và nếu còn giữ thì là cầu, không thuộc chu trình. Vậy `e` là cạnh nặng nhất (có thể hòa) trên chu trình này, và phép đổi cạnh bảo đảm không làm tăng trọng số MST tối ưu.

Sau khi duyệt tất cả cạnh, nếu có chu trình còn lại thì cạnh được xét sớm nhất trong chu trình lẽ ra đã bị xóa. Mâu thuẫn. Vì thế kết quả liên thông và phi chu trình, là cây khung; bất biến tối ưu cho thấy nó là MST.

### 12.3. Câu hỏi loại bỏ cạnh và kiểm tra bằng MST sau khi xóa

Với `removableWithoutCostIncrease`, chương trình tính một MST của `G` và một MST của `G-e` bằng cùng một thuật toán Kruskal đã chứng minh đúng. Nếu cả hai tồn tại và tổng bằng nhau, tồn tại MST tối ưu không chứa `e`. Nếu `G-e` mất liên thông hoặc trọng số MST lớn hơn, `e` thuộc mọi MST của `G`.

Điểm đáng chú ý là hàm kiểm tra **chỉ yêu cầu tồn tại một MST không chứa `e`**, không kiểm tra `e` xuất hiện trong **những MST khác** hay không. Trường hợp hòa trọng số cần phân biệt đúng.

## 13. Độ phức tạp: Kruskal so với reverse-delete đơn giản

Đặt `n` là số đỉnh, `m` là số cạnh vật lý.

| Thuật toán / thao tác | Thời gian điển hình | Bộ nhớ phụ |
|---|---|---|
| Kruskal + DSU | `O(m\log m+m\alpha(n))` | `O(n+m)` gồm danh sách ID sắp xếp |
| Kiểm tra một cạnh có bỏ được mà vẫn liên thông bằng DSU quét các cạnh còn lại | `O(m\alpha(n)+n)` | `O(n)` |
| Reverse-delete cài trực tiếp, xét `m` cạnh và mỗi lần kiểm tra liên thông bằng DSU | `O(m\log m+m(m\alpha(n)+n))` | `O(n+m)` |
| Kiểm tra một cạnh có xóa được mà vẫn giữ MST tối ưu bằng 2 lần Kruskal | `O(m\log m+m\alpha(n))` | `O(n+m)` |
| Vét cạn mọi tập cạnh làm oracle | Có thể tới `O(2^m\cdot m\alpha(n))` | `O(n+m)` ngoài đầu vào |

Đây là phân tích theo mô hình trọng số và phép toán số học cố định; khi dùng `BigInteger`, chi phí cộng/so sánh còn phụ thuộc số bit của tổng.

**Kruskal** thường phù hợp hơn khi cần một MST hiệu quả. **Reverse-delete** rất trực quan để hiểu tính chất chu trình nhưng bản cài kiểm tra liên thông lại từ đầu sau mỗi lần thử xóa có thể chậm khi `m` lớn.

Để tìm **cầu** của một đồ thị vô hướng, có thể dùng DFS với `tin/low` trong `O(n+m)`, nhưng nếu xóa cạnh nhiều lần thì cấu trúc đồ thị thay đổi; không thể tính cầu **một lần trên đồ thị gốc** rồi dùng mãi trong reverse-delete.

Để **phân loại các cạnh MST theo trọng số**, có những thuật toán nâng cao xử lý cạnh theo từng **nhóm trọng số bằng nhau**, kết hợp DSU và phát hiện cầu trên đồ thị co thành phần. Chúng tránh việc chạy lại Kruskal cho từng cạnh khi `m` lớn. Tuy nhiên phải xử lý **nhóm hòa trọng số đồng thời**, không tùy tiện quyết định ngay một cạnh cùng mức trước tất cả cạnh khác.

## 14. Kiểm thử vét cạn: kiểm tra cả trọng số lẫn cấu trúc cây

Một oracle độc lập cho đồ thị rất nhỏ có thể duyệt tất cả tập cạnh `S\subseteq E`:

1. Chỉ giữ tập `S` có đúng `n-1` ID cạnh.
2. Dùng DSU kiểm tra không có chu trình trong `S`.
3. Kiểm tra sau khi thêm đủ các ID trong `S`, tất cả đỉnh thuộc cùng thành phần.
4. Tính chính xác `W(S)`.
5. Lấy tổng nhỏ nhất của các tập `S` hợp lệ. Nếu không có tập nào, không có MST.

Oracle **không dùng quy tắc nặng nhất trên chu trình để quyết định**, nên có thể phát hiện lỗi triển khai Kruskal/reverse-delete.

### 14.1. Những bất biến cần kiểm tra

Nếu thuật toán báo có MST:

- **Đúng `n-1` cạnh** với **ID phân biệt**.
- **Liên thông** toàn bộ `n` đỉnh.
- **Không có chu trình**, gồm khuyên/cặp song song.
- **Tổng trọng số thực của edge ID** bằng số đã công bố.
- Tổng trọng số bằng giá trị oracle vét cạn.
- Khi hòa, **không bắt buộc tập ID trùng với oracle**; nhiều MST có thể khác nhau.

Nếu thuật toán trả không có MST, oracle cũng không được tìm thấy bất kỳ cây khung nào.

### 14.2. Kiểm thử từng cạnh

Với mỗi ID `e`:

- Xóa `e` khỏi tập đầu vào (hoặc cấm chọn ID này).
- Vét cạn MST của đồ thị còn lại.
- So với kết quả Kruskal cấm ID `e`.
- Nếu trọng số bằng MST gốc, `e` có thể bỏ mà vẫn giữ tối ưu.
- Nếu lớn hơn hoặc không còn cây khung, `e` là cạnh **critical**.

Đây là cách đối chứng trực tiếp với định nghĩa “có thể loại bỏ cạnh mà vẫn giữ MST tối ưu”, không phải chỉ kiểm tra một điều kiện suy luận dựa trên cùng code.

### 14.3. Các ca dễ bóc lỗi

```text
Một đỉnh, không cạnh: MST rỗng, tổng 0.
Một đỉnh, nhiều khuyên âm: MST vẫn rỗng, tổng 0.
Hai đỉnh, một cạnh: cạnh là cầu và critical.
Hai đỉnh, hai cạnh song song bằng nhau: mỗi cạnh optional.
Tam giác trọng số [1,2,9]: cạnh 9 không thuộc MST.
Tam giác trọng số [5,5,5]: có nhiều MST, không có cạnh critical.
Tam giác có một cạnh âm: phép đổi cạnh vẫn đúng.
Hai thành phần rời nhau: không có một MST toàn đồ thị.
Nhiều cạnh cùng trọng số, thứ tự input thay đổi.
Trọng số Long.MIN_VALUE / Long.MAX_VALUE.
Hai cây khung khác ID nhưng cùng tổng tối ưu.
```

**Kiểm thử không thay thế chứng minh.** Vài trăm ca đúng không chứng minh thuật toán đúng với mọi input. Định lý chu trình/lát cắt và bất biến Kruskal/reverse-delete mới là cơ sở bảo đảm. Nhưng test vét cạn rất hữu ích để bắt lỗi code như sắp sai chiều, bỏ qua cạnh song song hoặc tràn số.

## 15. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Thấy cạnh trên chu trình là xóa tùy ý để tìm MST | Có thể giữ liên thông nhưng tăng tổng tối ưu | Ưu tiên xóa cạnh **nặng nhất** theo tính chất chu trình |
| Nói “cạnh nặng nhất trên chu trình không thuộc MST nào” khi hòa | Loại sai cạnh có thể nằm trong MST khác | Chỉ kết luận **không thuộc bất kỳ MST** khi **nặng nhất duy nhất** |
| Dùng điều kiện “không phải cầu” để kết luận “không critical” | Cạnh rẻ trên chu trình vẫn có thể critical | So MST sau khi cấm cạnh hoặc dùng ngưỡng trọng số |
| Xóa cạnh trong một cây mà không thêm cạnh thay thế | Cây mất liên thông | Dùng phép đổi cạnh qua lát cắt |
| Nhầm tính chất lát cắt và chu trình | Giữ cạnh nặng, bỏ cạnh nhẹ | Trên **chu trình** chọn nặng để bỏ; trên **lát cắt** chọn nhẹ để giữ |
| Bỏ nhiều cạnh cùng lúc dựa trên các chu trình của đồ thị gốc | Các lần xóa cộng dồn có thể làm mất liên thông | Kiểm tra **đồ thị đang giữ** tại từng bước |
| Dùng Kruskal theo trọng số giảm dần để tìm MST | Có thể tạo cây khung lớn nhất | Kruskal MST phải xét **tăng dần** |
| Không phân biệt cạnh song song bằng ID | Gộp mất cạnh, sai chu trình và bậc | ID riêng cho mỗi cạnh vật lý |
| Chọn khuyên âm vì “rất rẻ” | Khuyên là chu trình, không nối thêm đỉnh | DSU từ chối `union(u,u)` |
| Dùng `a.weight-b.weight` trong comparator | Có thể tràn `long` | Dùng `Long.compare` |
| Dùng `long` cộng tổng không kiểm tra tràn | Sai tổng MST khi trọng số lớn | `BigInteger` hoặc `Math.addExact` với giới hạn phù hợp |
| Coi hai MST khác edge ID là lỗi | Sai khi trọng số hòa | So **giá trị tối ưu và cấu trúc cây**, không chỉ ID |
| Xem một rừng là MST khi đồ thị không liên thông | Trả sai định nghĩa | Dùng MSF hoặc báo không có MST toàn đồ thị |
| Dùng thuật toán MST vô hướng cho đồ thị có hướng | Không giải đúng bài toán arborescence | Xác định rõ loại đồ thị |
| Nghĩ mọi cạnh nặng hơn 0 đều bỏ được | Sai vì có thể là cầu | Xét kết nối/lát cắt, không chỉ dấu trọng số |
| Nghĩ mọi cạnh âm đều bắt buộc thuộc MST | Sai với khuyên và chu trình cạnh âm | Chứng minh qua chu trình/lát cắt |
| Bỏ mọi cạnh bị Kruskal từ chối rồi kết luận chúng không nằm trong MST nào | Sai với hòa trọng số | Kruskal trả **một** MST, cạnh từ chối có thể ở MST khác |
| Không kiểm tra đầu vào n, ID, endpoint | Lỗi truy cập hoặc thống kê sai | Validate trước thuật toán |
| Bỏ chứng minh tính tối ưu, chỉ thấy cây liên thông có `n-1` cạnh | Cây có thể hợp lệ nhưng không tối ưu | Dựa vào tính chất chu trình/lát cắt và test oracle |

## 16. Bài tập tự luyện và lời giải

**Bài 1 — Phân biệt kết nối và tối ưu.** Tam giác có trọng số `1,2,9`. Bỏ cạnh trọng số `1` có làm đồ thị mất liên thông không? Có giữ MST tối ưu không?

*Đáp án:* vẫn liên thông nhưng MST mới nặng `2+9=11`, lớn hơn tối ưu ban đầu `1+2=3`, nên không giữ tối ưu.

**Bài 2 — Nặng nhất duy nhất.** Trong chu trình có cạnh `[3,5,7,11]`, cạnh `11` có thể xuất hiện trong MST của toàn đồ thị không?

*Đáp án:* không, nếu đây thực sự là một chu trình trong cùng đồ thị. `11` là nặng nhất duy nhất; chứng minh đổi cạnh cho thấy không MST nào chứa nó.

**Bài 3 — Hòa trọng số.** Tam giác có ba cạnh cùng trọng số `4`. Có bao nhiêu MST? Một cạnh cụ thể có bắt buộc bị loại khỏi mọi MST không?

*Đáp án:* có `3` MST, mỗi MST chọn hai trong ba cạnh, tổng `8`. Không có cạnh nào bị cấm khỏi mọi MST; với từng cạnh đều có MST chứa nó và MST không chứa nó.

**Bài 4 — Cầu và critical.** Một cạnh cầu có chắc chắn thuộc mọi MST của đồ thị liên thông không?

*Đáp án:* có. Mọi cây khung đều phải nối hai phía của cầu bằng chính cạnh ấy; bỏ nó làm đồ thị không còn liên thông.

**Bài 5 — Không phải cầu nhưng critical.** Vì sao cạnh trọng số `1` trong tam giác `1,2,9` là critical?

*Đáp án:* bỏ cạnh `1` vẫn liên thông, nhưng buộc dùng `2+9=11` thay cho `1+2=3`. Mọi MST phải chứa cạnh `1`.

**Bài 6 — Cạnh song song.** Hai cạnh nối `0` và `1` có trọng số `3` và `8`. Cạnh nào bị loại khỏi mọi MST?

*Đáp án:* cạnh trọng số `8`, vì nó nặng nhất duy nhất trong chu trình gồm hai cạnh song song.

**Bài 7 — Khuyên âm.** Một khuyên `0--0` có trọng số `-1000` có được chọn vào MST để giảm tổng không?

*Đáp án:* không. Khuyên không nối thêm đỉnh và tự tạo chu trình; cây khung không chứa khuyên.

**Bài 8 — Phép đổi cạnh.** Nếu `e` thuộc MST và nằm trên chu trình của đồ thị gốc, tại sao sau khi xóa `e` ta tìm được một cạnh `f` khác trên chu trình nối hai thành phần?

*Đáp án:* đường đi còn lại của chu trình nối hai đầu `e` ở hai thành phần khác nhau; trên đường đi đó phải có một cạnh đi qua lát cắt giữa hai thành phần.

**Bài 9 — Điều kiện theo ngưỡng.** Cho cạnh `e` trọng số `8`. Sau khi bỏ `e`, hai đầu của nó có đường đi gồm các cạnh trọng số `[2,7,8]`. Có thể loại `e` mà vẫn đạt MST tối ưu không? Có chắc chắn không MST nào chứa `e` không?

*Đáp án:* có thể loại vì mọi cạnh đường thay thế `\le8`. Nhưng không thể kết luận `e` không thuộc bất kỳ MST nào, vì có cạnh thay thế hòa `8`; có thể có MST chọn `e`.

**Bài 10 — Phân loại mạnh hơn.** Nếu sau khi bỏ `e` có đường nối hai đầu chỉ gồm trọng số **nhỏ hơn `w(e)`**, ta kết luận gì?

*Đáp án:* `e` là nặng nhất duy nhất trong chu trình gồm `e` và đường thay thế, nên `e` không thuộc bất kỳ MST nào.

**Bài 11 — Reverse-delete.** Vì sao reverse-delete phải thử xóa **theo trọng số giảm dần**, không thể chỉ xóa tùy ý mọi cạnh không phải cầu?

*Đáp án:* thứ tự giảm bảo đảm cạnh xóa được là một cạnh nặng nhất trong một chu trình còn lại. Xóa tùy ý có thể giữ các cạnh quá đắt và tạo cây không tối ưu.

**Bài 12 — Tính tổng.** Với ba đỉnh và cạnh trọng số `-5,2,4` tạo tam giác, tổng MST là bao nhiêu?

*Đáp án:* `-3`, chọn hai cạnh `-5` và `2`.

**Bài 13 — Hai MST khác nhau.** Nếu Kruskal trả ID `[0,2,4]` và reverse-delete trả ID `[1,2,4]` trên đồ thị có hòa, có đủ cơ sở để báo một thuật toán sai không?

*Đáp án:* chưa. Phải kiểm tra mỗi tập ID là cây khung và cả hai có **trọng số tối ưu**, chẳng hạn đối chiếu với một oracle hoặc chứng minh đúng của thuật toán.

**Bài 14 — Chứng minh độ phức tạp.** Với reverse-delete kiểm tra liên thông bằng DSU từ đầu cho mỗi cạnh, vì sao không đạt thời gian như Kruskal?

*Đáp án:* có tới `m` lần thử xóa; mỗi lần quét tối đa `m` cạnh để kiểm tra liên thông, dẫn tới chi phí gần bậc hai theo `m`, thay vì chỉ một lượt DSU sau sắp xếp như Kruskal.

**Bài 15 — Tự kiểm thử.** Sinh đa đồ thị vô hướng nhỏ, cho phép khuyên, cạnh song song, trọng số âm và hòa. Đối chiếu trọng số MST từ Kruskal, reverse-delete và vét cạn; với mỗi cạnh thử cấm cạnh và đối chiếu lại.

*Đáp án mong đợi:* ba cách đồng ý về **sự tồn tại** và **trọng số tối ưu**. Nếu hai thuật toán chọn ID khác nhau nhưng vẫn là cây khung tối ưu thì cả hai đều hợp lệ.

## 17. Checklist trước khi loại một cạnh

Để không cắt nhầm khi giải bài về MST, hãy tự hỏi:

1. **Đồ thị vô hướng, có trọng số và liên thông chưa?** Nếu không liên thông, có thể cần MSF thay vì MST.
2. **Đang hỏi giữ liên thông hay giữ trọng số MST tối ưu?** Hai mục tiêu không tương đương.
3. **Cạnh là cầu hay nằm trên chu trình?** Nếu là cầu thì mọi cây khung đều cần nó.
4. **Nếu loại để giữ MST tối ưu**, có chu trình mà cạnh ấy là **một cạnh nặng nhất** không, hoặc có MST tối ưu không dùng nó?
5. **Có hòa trọng số không?** Nặng nhất duy nhất mới chắc chắn không thuộc **bất kỳ** MST.
6. **Có thể đổi cạnh sau khi xóa không?** Nêu rõ hai thành phần của `T-e` và cạnh thay thế băng qua lát cắt.
7. **Có cạnh song song/khuyên không?** Dùng ID vật lý, không gộp theo cặp đầu mút.
8. **Đã xử lý trọng số âm và tràn số chưa?** Không dùng phép trừ `long` trong comparator.
9. **Nếu dùng Kruskal:** có sort tăng dần và chỉ union hai thành phần khác nhau?
10. **Nếu dùng reverse-delete:** có sort giảm dần và kiểm tra liên thông trên đồ thị **hiện tại** sau từng phép xóa?
11. **Nếu kết quả khác ID:** có kiểm tra cả hai là cây và có tổng tối ưu chưa?
12. **Đã có một oracle nhỏ độc lập và phản ví dụ cố định để kiểm thử chưa?**

## Ghi nhớ

Trong đồ thị vô hướng liên thông:

\[
\boxed{
e\text{ nằm trên chu trình}
\iff
G-e\text{ vẫn liên thông}.
}
\]

Đó là tiêu chuẩn **chỉ về liên thông**.

Đối với **trọng số MST**:

- Nếu `e` là **một cạnh nặng nhất** trong một chu trình, tồn tại **ít nhất một MST không dùng `e`**.
- Nếu `e` là **cạnh nặng nhất duy nhất** trong một chu trình, `e` **không thuộc bất kỳ MST nào**.
- Nếu cần biết `e` có thể bị xóa mà vẫn giữ trọng số tối ưu hay không, kiểm tra `M(G-e)=M(G)` hoặc tìm một đường thay thế giữa hai đầu `e` chỉ dùng các cạnh có trọng số `\le w(e)`.
- **Cầu** là cạnh bắt buộc của mọi cây khung; cạnh **không phải cầu** vẫn có thể bắt buộc của **mọi MST** khi các lựa chọn thay thế đều đắt hơn.

Kruskal **thêm cạnh nhẹ trước và từ chối cạnh tạo chu trình**. Reverse-delete **xóa cạnh nặng trước nếu liên thông vẫn còn**. Cả hai có thể được chứng minh bằng tính chất chu trình và phép đổi cạnh.

**Điều quan trọng không phải cứ có chu trình là xóa bừa. Phải biết đang bảo toàn tính liên thông hay bảo toàn tính tối ưu, và phải xử lý đúng sự khác biệt giữa nặng nhất duy nhất với hòa trọng số.**
