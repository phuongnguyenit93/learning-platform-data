# Giải 2-SAT qua đồ thị suy diễn và thành phần liên thông mạnh

**2-SAT (2-satisfiability)** là bài toán xác định có tồn tại cách gán giá trị **true/false** cho các biến Boolean để **mọi mệnh đề (clause)** trong một công thức logic cùng đúng, với điều kiện **mỗi mệnh đề chứa tối đa hai literal**. Đây là một trường hợp đặc biệt quan trọng của SAT: SAT tổng quát khó hơn nhiều, nhưng **2-SAT giải được trong thời gian tuyến tính** theo số biến và mệnh đề, nhờ **đồ thị suy diễn (implication graph)** và **thành phần liên thông mạnh (Strongly Connected Components – SCC)**.

Ý tưởng cốt lõi:

1. Chuyển mỗi mệnh đề `(a ∨ b)` thành hai suy diễn `¬a → b` và `¬b → a`.
2. Xem mỗi literal `x` và `¬x` như **hai đỉnh riêng biệt** của một đồ thị có hướng.
3. Tính SCC bằng **Kosaraju** hoặc **Tarjan**.
4. Công thức **vô nghiệm** khi và chỉ khi có biến `x` mà hai đỉnh `x` và `¬x` thuộc **cùng một SCC**.
5. Nếu không có mâu thuẫn trên, ta có thể khôi phục một phép gán thỏa công thức từ **thứ tự topo của DAG các SCC**.

Bài học thuộc nhóm **Cấu trúc đồ thị**, tập trung vào mô hình hóa đúng logic thành cạnh có hướng, hiểu vì sao SCC phát hiện được mâu thuẫn, thứ tự đánh số SCC ảnh hưởng đến công thức gán như thế nào, và triển khai **Java 17+ dùng DFS lặp** để tránh phụ thuộc độ sâu call stack. Chương trình đầy đủ có kiểm thử độc lập bằng vét cạn mọi phép gán trên **8.580 công thức nhỏ**, trong đó có cả công thức có nghiệm và vô nghiệm.

## 1. Từ Boolean SAT tới 2-SAT

Một **biến Boolean** `x_i` nhận đúng một trong hai giá trị `true` hoặc `false`. Một **literal** là:

- Literal dương `x_i`: đúng khi biến `x_i=true`;
- Literal âm `¬x_i`: đúng khi biến `x_i=false`.

Một **mệnh đề** là phép OR của các literal; mệnh đề `(a∨b)` đúng nếu **ít nhất một** trong `a` hoặc `b` đúng. Một công thức dạng **CNF (Conjunctive Normal Form)** là phép AND của nhiều mệnh đề.

Ví dụ công thức 2-CNF:

```text
F = (x1 ∨ x2)
  ∧ (¬x1 ∨ x2)
  ∧ (x1 ∨ ¬x2)
  ∧ (¬x2 ∨ ¬x3)
```

Ta yêu cầu **cả bốn mệnh đề** cùng đúng; chỉ cần một mệnh đề sai là toàn bộ công thức sai.

Trong ví dụ này, một phép gán thỏa là:

```text
x1 = true
x2 = true
x3 = false
```

Kiểm tra:

| Mệnh đề | Giá trị dưới phép gán | Kết quả |
| --- | --- | --- |
| `x1 ∨ x2` | `true ∨ true` | Đúng |
| `¬x1 ∨ x2` | `false ∨ true` | Đúng |
| `x1 ∨ ¬x2` | `true ∨ false` | Đúng |
| `¬x2 ∨ ¬x3` | `false ∨ true` | Đúng |

Thực tế, ba mệnh đề đầu buộc `x1=true` và `x2=true`, mệnh đề cuối buộc `x3=false`; phép gán này là **duy nhất**. Tuy nhiên, **bài toán 2-SAT thông thường chỉ hỏi có tồn tại nghiệm hay không**, và nếu có thì đưa ra **một** phép gán. Thuật toán SCC không tự đếm tất cả nghiệm.

### “Tối đa hai literal” bao gồm những gì?

- Mệnh đề hai literal: `(x1∨¬x2)`;
- Mệnh đề một literal `(x1)` có thể mã hóa thành `(x1∨x1)`;
- Mệnh đề lặp `(a∨a)` tương đương một literal;
- Mệnh đề hằng đúng `(x1∨¬x1)` không hạn chế nghiệm;
- Công thức không có mệnh đề là **đúng với mọi phép gán**; nếu cũng không có biến thì có một phép gán rỗng.

**Không được tùy tiện áp 2-SAT cho công thức có một mệnh đề ba literal** như `(x1∨x2∨x3)`. Nó không phải mệnh đề 2-CNF, và không thể đơn giản “cắt thành hai mệnh đề hai literal” mà giữ nguyên tập nghiệm nếu không có biến phụ cùng một phép biến đổi được chứng minh.

## 2. Phép suy diễn tương đương với một mệnh đề OR

Điểm mấu chốt là đẳng thức logic:

```text
(a ∨ b) ≡ (¬a → b) ≡ (¬b → a)
```

Vì vậy, một mệnh đề `(a∨b)` tương đương với **cả hai** suy diễn:

```text
¬a -> b
¬b -> a
```

### Kiểm tra theo bảng chân trị

| `a` | `b` | `a∨b` | `¬a→b` | `¬b→a` |
| --- | --- | --- | --- | --- |
| False | False | False | False | False |
| False | True | True | True | True |
| True | False | True | True | True |
| True | True | True | True | True |

Do đó ta có thể thay `(a∨b)` bằng **hai cạnh suy diễn** mà không làm thay đổi những phép gán nào thỏa công thức.

**Đừng đảo chiều suy diễn:** Với `a∨b`, hai cạnh đúng là `¬a→b` và `¬b→a`; không phải `a→b` và `b→a`. Nếu chuyển sai cạnh, đồ thị không còn mô tả đúng mệnh đề.

### Ý nghĩa khi duyệt đồ thị

Một cạnh có hướng `u→v` nói rằng:

> Nếu literal `u` đúng thì literal `v` **phải đúng**.

Nếu `u` sai, cạnh không bắt buộc `v` phải đúng hay sai. Vì vậy **sự tồn tại cạnh không phải phép gán Boolean**, mà là một ràng buộc mà mọi phép gán thỏa công thức phải tôn trọng.

Một đường đi có hướng:

```text
u -> p -> q -> v
```

đại diện cho suy diễn bắc cầu: nếu `u` đúng thì `v` cũng phải đúng.

### Ví dụ chuyển mệnh đề

Mệnh đề:

```text
(x1 ∨ ¬x2)
```

tạo hai cạnh:

```text
¬x1 -> ¬x2
 x2 ->  x1
```

Nếu `x2=true` thì `x1` phải true, bởi nếu `x1=false`, cả hai literal trong mệnh đề đều sai. Mặt khác, nếu `x1=false` thì `x2` phải false. Hai hướng là dạng **phản vị (contrapositive)** của cùng một điều kiện.

## 3. Hai đỉnh cho mỗi biến: ánh xạ literal chính xác

Với `n` biến `x1,...,xn`, đồ thị suy diễn có đúng **`2n` đỉnh**, vì mỗi biến cần đỉnh cho hai literal trái dấu.

Quy ước của chương trình Java:

```text
x1 = true  -> node 1
x1 = false -> node 0  (literal ¬x1)

x2 = true  -> node 3
x2 = false -> node 2  (literal ¬x2)

...
xi = false -> node 2*(i-1)
xi = true  -> node 2*(i-1)+1
```

Với đánh số biến `i=1..n`, ta dùng **literal số nguyên có dấu**:

- `+i` đại diện `x_i`;
- `−i` đại diện `¬x_i`;
- `0` là **không hợp lệ**, vì không có biến `x0` trong quy ước.

Ví dụ:

| Literal | Số nguyên | Đỉnh |
| --- | ---: | ---: |
| `¬x1` | −1 | 0 |
| `x1` | +1 | 1 |
| `¬x2` | −2 | 2 |
| `x2` | +2 | 3 |
| `¬x3` | −3 | 4 |
| `x3` | +3 | 5 |

Nếu `node` là mã của một literal, mã của **literal phủ định** chính là:

```java
int negatedNode = node ^ 1;
```

Điều này đúng vì hai node của cùng biến là cặp số liên tiếp **chẵn/lẻ**: `0↔1`, `2↔3`, ... . XOR với 1 chỉ đảo bit thấp nhất.

### Tại sao phải nhất quán một quy ước?

Có nhiều cách ánh xạ hợp lệ. Một số lời giải dùng `2*i` cho **true** và `2*i+1` cho **false**, một số khác đảo lại. Cả hai đều được nếu **toàn bộ chương trình nhất quán**.

Trong bài này:

```text
nodeFalse(i) = 2*i
nodeTrue(i)  = 2*i+1

i là chỉ số biến 0-based trong Java.
```

Vì vậy:

```java
int node = 2 * (absLiteral - 1)
         + (literal > 0 ? 1 : 0);
```

**Đừng copy nửa đầu ánh xạ từ một tutorial và nửa cuối phép khôi phục nghiệm từ tutorial khác.** Một dấu `>` hoặc `<` ở công thức khôi phục nghiệm có thể phụ thuộc cách đánh số SCC và cách map true/false.

### Tránh lỗi `Math.abs(Integer.MIN_VALUE)`

`Math.abs(Integer.MIN_VALUE)` khi làm việc trên `int` vẫn có thể cho kết quả âm do tràn. Để xác thực literal một cách an toàn, chuyển sang `long` trước:

```java
long index = Math.abs((long) literal);
if (index < 1 || index > variableCount) {
    throw new IllegalArgumentException("literal out of range");
}
```

Sau khi biết `index≤n` với n đã kiểm tra giới hạn cấp phát, mới ép kiểu `int` để tính node.

## 4. Tạo đồ thị suy diễn và đồ thị đảo cạnh

Với mỗi mệnh đề `(a∨b)`:

1. Lấy node của `a` và `b`.
2. Thêm cạnh `neg(a)→b`.
3. Thêm cạnh `neg(b)→a`.

Một mệnh đề có thể sinh **hai cạnh giống nhau**, ví dụ `(x1∨x1)` tạo `¬x1→x1` hai lần. Điều này không làm sai thuật toán SCC; nó chỉ làm nhiều mục cạnh hơn. Có thể khử trùng nếu tối ưu bộ nhớ, nhưng không cần thiết cho tính đúng.

Giả sử có `m` mệnh đề (mỗi mệnh đề hai literal, cho phép hai literal bằng nhau). Đồ thị có:

```text
V = 2*n nút
E = 2*m cạnh được thêm, tính cả cạnh có thể trùng
```

Cả **Kosaraju** và **Tarjan** tìm SCC trong **`O(V+E)=O(n+m)`** với danh sách kề.

### Đồ thị đảo (*transpose graph*)

Để chạy Kosaraju, ngoài graph gốc `G` cần đồ thị `Gᵀ` có **mọi cạnh đảo chiều**:

```text
Nếu G chứa u -> v
thì Gᵀ chứa v -> u.
```

Khi thêm một cạnh `u→v`, ta có thể đồng thời:

```java
graph.get(u).add(v);
reversed.get(v).add(u);
```

Đảo cạnh **không có nghĩa phủ định literal**. Đây là hai phép toán hoàn toàn khác:

- `node ^ 1`: đổi `x` thành `¬x` hoặc ngược lại;
- `Gᵀ`: giữ nguyên node nhưng đảo **hướng của mọi cạnh**.

Nhầm hai phép này là lỗi rất thường gặp.

### Tính phản vị của các cạnh

Với mệnh đề `a∨b`, cạnh `¬a→b` luôn đi cùng cạnh `¬b→a`. Hai cạnh đó có quan hệ:

```text
u -> v  đi cùng  ¬v -> ¬u.
```

Quan hệ này là một điều kiện cấu trúc quan trọng của đồ thị suy diễn 2-SAT. Nó góp phần bảo đảm rằng khi ta chọn literal theo thứ tự SCC, phép gán thu được tôn trọng **mọi suy diễn**.

## 5. Thành phần liên thông mạnh: công cụ để phát hiện mâu thuẫn

Trong đồ thị có hướng, hai đỉnh `u` và `v` thuộc cùng một **SCC** khi:

```text
Có đường đi có hướng từ u tới v
và
có đường đi có hướng từ v tới u.
```

Một SCC là tập lớn nhất thỏa tính **đi tới được lẫn nhau**.

Đặc biệt, nếu `x` và `¬x` cùng một SCC, tồn tại cả hai đường:

```text
x  -> ... -> ¬x
¬x -> ... ->  x
```

Nếu chọn `x=true`, đường đầu buộc `¬x=true`, mâu thuẫn. Nếu chọn `x=false` (tức `¬x=true`), đường thứ hai buộc `x=true`, cũng mâu thuẫn.

Vậy:

```text
Nếu SCC(x) == SCC(¬x)
thì công thức không có phép gán thỏa.
```

Và định lý đầy đủ của 2-SAT cho biết chiều ngược cũng đúng:

```text
F là 2-CNF satisfiable
    khi và chỉ khi
với mọi biến x_i:
    SCC(x_i) != SCC(¬x_i)
```

Phần “nếu không trùng SCC thì có thể gán được” không phải điều hiển nhiên chỉ từ một ví dụ; nó cần tính chất **thứ tự của DAG các SCC**. Chúng ta sẽ chứng minh và dùng để dựng nghiệm ở mục 7–9.

### Ví dụ vô nghiệm chỉ có một biến

Công thức:

```text
(x1 ∨ x1) ∧ (¬x1 ∨ ¬x1)
```

tương đương:

```text
x1 ∧ ¬x1
```

Đồ thị có hai loại cạnh:

```text
¬x1 -> x1
 x1 -> ¬x1
```

Hai literal nằm cùng SCC. Dù thử true hay false, luôn có một mệnh đề sai. Kết quả thuật toán là **UNSAT**.

### Cạnh tự thân không đồng nghĩa mâu thuẫn

Mệnh đề `(x1∨¬x1)` là **hằng đúng**. Nó tạo các cạnh tự thân:

```text
x1  -> x1
¬x1 -> ¬x1
```

Đây là các self-loop trên **hai node khác nhau**, **không** tạo đường `x1↔¬x1`. SCC của literal và phủ định có thể vẫn khác nhau; công thức này **SAT**.

**Đừng coi bất kỳ chu trình nào trong đồ thị suy diễn là UNSAT.** Chu trình giữa các literal khác nhau chỉ nói rằng chúng tương đương theo suy diễn. UNSAT xảy ra chính xác khi **một literal và phủ định của chính nó** bị gom chung SCC.

## 6. Kosaraju: hai lượt DFS để phân rã SCC

Kosaraju là một thuật toán SCC gồm hai lượt DFS:

1. Chạy DFS trên **đồ thị gốc `G`**, ghi danh sách các đỉnh **theo thứ tự kết thúc** (*finish order/postorder*).
2. Đảo thứ tự finish order, rồi chạy DFS trên **đồ thị đảo `Gᵀ`**. Mỗi lần bắt đầu DFS từ node chưa được gán SCC sẽ tìm đúng **một SCC mới**.

### Lượt 1: thứ tự kết thúc

Ví dụ DFS đệ quy:

```text
dfs1(u):
    visited[u] = true
    for v in G[u]:
        if not visited[v]:
            dfs1(v)
    finishOrder.add(u)   // Sau khi xử lý mọi cạnh đi ra

for u = 0..2n-1:
    if not visited[u]:
        dfs1(u)
```

**Không phải thứ tự phát hiện.** Nếu thêm node vào finish order ngay khi vào DFS, thuật toán Kosaraju có thể nhóm SCC sai. Phải thêm sau khi mọi lời gọi con kết thúc.

### Lượt 2: đồ thị đảo, duyệt ngược finish order

```text
component[0..2n-1] = -1
componentCount = 0

for u in reverse(finishOrder):
    if component[u] != -1:
        continue

    dfs2(G_transpose, u):
        gán mọi node tới được chưa gán
        cùng component ID = componentCount

    componentCount++
```

Chú ý lượt 2 dùng **cạnh đã đảo**, không tiếp tục dùng graph gốc. Nếu chạy hai lượt trên cùng graph, kết quả không còn là phân hoạch SCC của Kosaraju.

### Vì sao lượt 2 không kéo sang SCC khác một cách sai?

Co mỗi SCC của `G` thành một siêu đỉnh, thu được **đồ thị ngưng tụ SCC (condensation graph)**. Đồ thị này luôn là DAG: nếu giữa các SCC có chu trình thì các SCC đó thực ra reachable hai chiều và phải gộp thành một SCC.

Lượt DFS đầu tạo thứ tự kết thúc giúp lượt hai (trên đồ thị đảo) xét các SCC theo một thứ tự không cho phép DFS thứ hai “tràn” sang SCC chưa được gán khác. Mỗi nhóm thu được vì thế là một SCC.

Với chính **quy ước của chương trình dưới đây** — lượt một DFS **trên G**, lượt hai trên **Gᵀ** theo finish giảm dần, đánh số SCC từ 0 tăng dần — ID của SCC đi theo một thứ tự tô-pô **từ nguồn tới đích** trong condensation graph của G:

```text
Nếu có cạnh u -> v nối hai SCC khác nhau:
    component[u] < component[v]
```

Đây là chi tiết cực kỳ quan trọng khi khôi phục phép gán. Nếu bạn đổi thứ tự hai lượt Kosaraju, hoặc dùng Tarjan với chính sách đánh số khác, dấu bất đẳng thức trong công thức chọn true/false có thể phải **đảo lại**.

### Vì sao dùng DFS lặp trong Java?

Đồ thị suy diễn có thể có hàng trăm nghìn đỉnh. Nếu nó chứa đường DFS rất dài, lời gọi đệ quy Java có thể gây `StackOverflowError`. Ví dụ chọn:

```text
x1 -> x2 -> x3 -> ... -> xN
```

Một DFS đệ quy từ `x1` có độ sâu gần N.

Mã mẫu dùng:

- **Frame(vertex, nextIndex)** cho DFS lượt 1 để biết chính xác lúc kết thúc node;
- **ArrayDeque<Integer>** cho lượt 2 trên đồ thị đảo, vì lượt này chỉ cần gom thành phần, không cần finish order mới.

Cả hai vẫn có độ phức tạp tuyến tính `O(n+m)`, nhưng stack do chương trình quản lý trên heap thay vì dựa vào call stack JVM.

## 7. Từ SCC sang phép gán Boolean

Sau khi tính SCC, kiểm tra mọi biến `i`:

```text
falseNode = 2*i
trueNode  = 2*i+1

Nếu component[falseNode] == component[trueNode]:
    UNSAT
```

Nếu không mâu thuẫn, ta cần chọn true hoặc false cho từng biến để thỏa **tất cả cạnh suy diễn**.

Với cách đánh số component của Kosaraju ở mục 6 (ID nhỏ ở phía nguồn, ID lớn ở phía đích), phép gán hợp lệ là:

```java
values[i] = component[2 * i + 1] > component[2 * i];
```

Nghĩa là chọn **literal nằm trong SCC có ID lớn hơn** của cặp `x_i`/`¬x_i` làm literal đúng.

### Ví dụ với một unit clause

Công thức `(x1∨x1)` tạo cạnh `¬x1→x1`. Hai SCC khác nhau, và vì cạnh từ phủ định tới literal dương:

```text
component[¬x1] < component[x1]
```

Nên `component[x1]>component[¬x1]`, thuật toán gán `x1=true` như yêu cầu.

Ngược lại, công thức `(¬x1∨¬x1)` tạo `x1→¬x1`; component của phủ định lớn hơn, thuật toán gán `x1=false`.

### Vì sao công thức này không chỉ là mẹo?

Trong SCC condensation DAG, chọn literal thuộc SCC có thứ tự topo **muộn hơn** của cặp phủ định. Nếu phép gán làm một cạnh `u→v` bị vi phạm, nghĩa là `u=true` nhưng `v=false`.

Do quy tắc chọn “SCC ID lớn hơn”:

```text
component[u]  > component[¬u]
component[¬v] > component[v]
```

Vì hai cạnh phản vị luôn cùng tồn tại:

```text
u  -> v
¬v -> ¬u
```

Và theo topo của SCC:

```text
component[u]  <= component[v]
component[¬v] <= component[¬u]
```

Gộp các bất đẳng thức:

```text
component[u] > component[¬u]
             >= component[¬v]
             > component[v]
             >= component[u]
```

Vô lý. Vậy **không có cạnh nào bị vi phạm**, nên mọi mệnh đề (tương đương với các cạnh của nó) đều đúng.

Đây là lập luận xây dựng được một nghiệm mỗi khi **không có cặp literal/phủ định nằm chung SCC**, hoàn tất chứng minh chiều ngược của định lý 2-SAT.

**Lưu ý:** Bất đẳng thức giữa hai SCC được phép dùng `≤` trong chứng minh khi cạnh nối hai đỉnh trong cùng SCC; với cạnh nối SCC khác nhau thì thứ tự là nghiêm ngặt. Mâu thuẫn vẫn đúng.

## 8. Ví dụ tính đồ thị suy diễn từ đầu tới cuối

Xét lại công thức ba biến:

```text
F = ( x1 ∨  x2)
  ∧ (¬x1 ∨  x2)
  ∧ ( x1 ∨ ¬x2)
  ∧ (¬x2 ∨ ¬x3)
```

Ánh xạ node:

```text
¬x1:0, x1:1, ¬x2:2, x2:3, ¬x3:4, x3:5
```

Các cạnh suy diễn cho từng mệnh đề:

| Mệnh đề | Cạnh 1 | Cạnh 2 |
| --- | --- | --- |
| `x1∨x2` | `¬x1→x2` (0→3) | `¬x2→x1` (2→1) |
| `¬x1∨x2` | `x1→x2` (1→3) | `¬x2→¬x1` (2→0) |
| `x1∨¬x2` | `¬x1→¬x2` (0→2) | `x2→x1` (3→1) |
| `¬x2∨¬x3` | `x2→¬x3` (3→4) | `x3→¬x2` (5→2) |

Ta có:

- `x1` và `x2` thuộc cùng SCC, vì `x1→x2` và `x2→x1`.
- `¬x1` và `¬x2` thuộc cùng SCC, vì `¬x1→¬x2` và `¬x2→¬x1`.
- Các cạnh từ SCC phủ định tới SCC dương, và từ `x2` tới `¬x3`, buộc `x1=true`, `x2=true`, `x3=false`.

Một lượt Kosaraju với thứ tự node tăng và danh sách cạnh giữ theo thứ tự thêm trong code cho mảng SCC:

```text
Node index:       [0, 1, 2, 3, 4, 5]
Literal:          [¬x1,x1,¬x2,x2,¬x3,x3]
Component ID:     [1, 2, 1, 2, 3, 0]
```

So sánh:

```text
x1: component[true]=2 > component[false]=1 -> true
x2: component[true]=2 > component[false]=1 -> true
x3: component[true]=0 < component[false]=3 -> false
```

Đó là phép gán:

```text
[true, true, false]
```

**ID SCC chỉ là số thứ tự nội bộ**, không phải nhãn toán học cố định của thành phần. Nếu đổi thứ tự DFS hoặc adjacency, ID và thứ tự các SCC không ràng buộc có thể khác, trong khi phép gán trả về vẫn đúng. Chương trình mẫu giữ cùng thứ tự thêm cạnh để có output xác định.

## 9. Chứng minh đầy đủ, đúng đắn và tính kết thúc

### Mệnh đề A — đồ thị mã hóa chính xác 2-CNF

Với từng clause `(a∨b)`, nó sai chỉ khi `a=false` và `b=false`. Trong trường hợp đó, `¬a=true` nhưng `b=false`, nên cạnh `¬a→b` bị vi phạm; tương tự cho cạnh còn lại. Nếu clause đúng, cả hai suy diễn tương đương đều đúng.

Vậy **một phép gán thỏa mọi clause khi và chỉ khi nó tôn trọng mọi cạnh của implication graph**.

### Mệnh đề B — SCC chứa `x` và `¬x` dẫn đến UNSAT

Cùng SCC nghĩa là có hai đường suy diễn `x⇒¬x` và `¬x⇒x`. Mọi phép gán chọn một trong `x` và `¬x` là true; đường tương ứng sẽ buộc literal đối lập true, mâu thuẫn. Do đó không tồn tại phép gán.

### Mệnh đề C — không có cặp mâu thuẫn thì SAT

Đồ thị SCC ngưng tụ là DAG. Dưới cách đánh số Kosaraju được quy định, mọi cạnh giữa SCC hướng từ ID nhỏ sang ID lớn. Chọn true cho literal trong SCC có ID lớn hơn của mỗi cặp đối lập. Chứng minh phản chứng ở mục 7 cho thấy **không cạnh suy diễn nào** có nguồn true và đích false. Theo mệnh đề A, mọi clause đều đúng.

### Mệnh đề D — thuật toán kết thúc

- Đồ thị có hữu hạn `2n` node và `2m` cạnh.
- Trong DFS lượt 1, mỗi node được đánh dấu visited **trước khi đưa vào stack**, nên không push lại.
- Trong lượt 2, mỗi node được gán component ID **trước khi push**, nên không gán hoặc push lại.
- Mỗi frame duyệt hữu hạn hàng xóm và được pop sau khi xét hết.
- Vòng kiểm tra cuối cùng duyệt đúng `n` cặp literal.

Do đó hai lượt DFS và bước dựng nghiệm đều kết thúc.

### Bốn loại kết quả cần phân biệt

1. **SAT, một nghiệm:** đủ để trả lời bài toán quyết định 2-SAT và chứng minh tồn tại.
2. **UNSAT:** có ít nhất một `x` và `¬x` trong cùng SCC.
3. **SAT, nhiều nghiệm:** thuật toán chọn **một** nghiệm nhưng không khẳng định duy nhất.
4. **Đếm tổng số nghiệm:** là bài toán khác. Dù kiểm tra thỏa mãn 2-SAT là đa thức, **đếm số nghiệm (#2-SAT)** khó hơn nhiều nói chung; đừng lấy số SCC hay số biến làm số nghiệm.

Nếu cần biết một biến có bắt buộc true/false, có thể thử thêm đơn vị phủ định hoặc đơn vị khẳng định rồi chạy lại 2-SAT cho công thức đã gia cố. Cụ thể, khi `F` đang SAT, `x` bị buộc true nếu `F∧¬x` UNSAT. Cách này đúng nhưng đắt hơn việc chỉ lấy một nghiệm; không suy ra tính bắt buộc của từng biến chỉ từ phép gán đầu tiên.

## 10. Các mẫu ràng buộc thực tế thành 2-SAT

Giả sử mỗi biến `x_i` biểu diễn một quyết định có/không. Những quy tắc sau mã hóa được trực tiếp bằng các clause tối đa hai literal:

| Yêu cầu | Clause 2-CNF | Ý nghĩa |
| --- | --- | --- |
| Chọn ít nhất một trong A,B | `A∨B` | Không được cả hai false |
| Không được chọn cả A và B | `¬A∨¬B` | At most one |
| A kéo theo B | `¬A∨B` | Nếu A true thì B true |
| A và B phải có cùng giá trị | `(¬A∨B)∧(¬B∨A)` | `A↔B` |
| Chính xác một trong A,B | `(A∨B)∧(¬A∨¬B)` | XOR hai biến |
| Bắt buộc A | `(A∨A)` | Unit clause |
| Bắt buộc không chọn A | `(¬A∨¬A)` | Unit clause |
| A hoặc phủ định A | `(A∨¬A)` | Tautology; không thêm điều kiện hữu ích |

Ví dụ **chính xác một trong hai** khác với “ít nhất một”:

```text
ExactlyOne(A,B)
= (A∨B) ∧ (¬A∨¬B)
```

Công thức có hai nghiệm: `(A=true,B=false)` và `(A=false,B=true)`. Chỉ có `(A∨B)` thì cả `(true,true)` cũng hợp lệ.

### Ràng buộc không tự mã hóa thành một clause 2-SAT

“Ít nhất một trong ba `A∨B∨C`” là mệnh đề ba literal, không phải một clause 2-SAT. “Chọn đúng hai trong mười người” là ràng buộc lực lượng (cardinality) không tự nhiên có biểu diễn trực tiếp bằng một clause hai literal.

Một số ràng buộc có thể được biểu diễn lại bằng **biến phụ** và các công thức đặc biệt, nhưng phải chứng minh phép biến đổi là **tương đương hoặc equisatisfiable** và mọi clause vẫn có độ dài ≤2. Không nên tự tin rằng mọi ràng buộc Boolean đều giải được tuyến tính nhờ thêm các biến.

### 2-SAT và các bài toán sắp lịch

Nếu `x_i=true` nghĩa là chọn ca sáng và `false` nghĩa là ca chiều, mâu thuẫn đôi có thể biểu diễn bằng một clause hai literal. Ví dụ “không được đồng thời chọn A sáng và B chiều” viết:

```text
¬A ∨ B
```

vì `B=false` nghĩa là B chiều. Khi thiết kế, hãy lập **bảng chân trị của biến trước**, rồi diễn đạt quy tắc bằng clause; nhiều lỗi thực tế nằm ở việc trộn “chọn A” với “không chọn A” chứ không nằm ở thuật toán SCC.

## 11. Độ phức tạp và ranh giới sử dụng

Với `n` biến và `m` mệnh đề hai literal:

| Công việc | Thời gian | Bộ nhớ |
| --- | --- | --- |
| Tạo hai node cho mỗi biến | `O(n)` | `O(n)` |
| Thêm hai cạnh cho mỗi clause | `O(m)` | `O(m)` |
| Kosaraju lượt 1 trên graph | `O(n+m)` | `O(n)` phụ |
| Kosaraju lượt 2 trên graph đảo | `O(n+m)` | `O(n)` phụ |
| Kiểm tra cặp phủ định và khôi phục nghiệm | `O(n)` | `O(n)` |
| Tổng | **`O(n+m)`** | **`O(n+m)`** |

Bộ nhớ `O(n+m)` bao gồm cả hai danh sách kề `G` và `Gᵀ` (mỗi đồ thị chứa `2m` mục cạnh, tính cả duplicates), mảng visited, finish order, component, và stack.

**Không nhầm với DFS topo trên graph gốc:** Implication graph có thể **có chu trình** nhưng công thức vẫn SAT, ví dụ `x1↔x2` sinh SCC có nhiều node. Ta không sắp topo **trực tiếp tất cả literal** trong graph có chu trình; ta **tính SCC trước**, sau đó các SCC tạo DAG. Phép khôi phục dựa trên **thứ tự topo của DAG các SCC**, không phải giả định graph nguyên thủy là DAG.

### Với đồ thị lớn trong Java

- Dùng adjacency list, không tạo ma trận `(2n)×(2n)` vì bộ nhớ sẽ thành `O(n²)`.
- Dùng **DFS lặp** nếu đường suy diễn có thể dài, tránh lỗi call stack của DFS đệ quy.
- `ArrayList<Integer>` có boxing và overhead; với vài triệu cạnh, cần cân nhắc mảng cạnh kiểu CSR hoặc `head/to/next`.
- Kiểm tra `2*n` không overflow `int` trước cấp phát, và giới hạn RAM thực tế của ứng dụng.
- Không sort cạnh nếu bài không yêu cầu thứ tự nghiệm xác định: SCC đúng đắn không phụ thuộc thứ tự xét hàng xóm.
- Nếu chỉ muốn SAT/UNSAT, không cần giữ toàn bộ chuỗi suy diễn chứng minh; nếu muốn minh chứng vô nghiệm, có thể dựng hai đường `x⇒¬x` và `¬x⇒x` trong SCC mâu thuẫn, nhưng đó là phần mở rộng cần thêm parent/path.

## 12. Java 17+ hoàn chỉnh: 2-SAT bằng Kosaraju lặp

Tệp **TwoSatSccDemo.java** dưới đây triển khai đúng công thức:

- Mỗi clause là `int[]{a,b}`, literal `±i` với `1≤i≤n`.
- Node chẵn `2i` (biến 0-based) biểu diễn **false**, node lẻ `2i+1` biểu diễn **true**.
- Xây cả implication graph và graph đảo.
- Lượt DFS đầu dùng **stack các frame** để ghi finish order thực sự.
- Lượt DFS hai trên graph đảo gán SCC theo finish giảm.
- Nếu `component[falseNode]==component[trueNode]`, trả `satisfiable=false`.
- Ngược lại, trả phép gán với `component[trueNode]>component[falseNode]`.
- Có hàm `satisfies` kiểm tra phép gán bằng cách **đánh giá từng clause thật**, độc lập với việc duyệt SCC.
- Có brute-force oracle để kiểm tra mọi gán true/false trên input rất nhỏ và một bộ sinh công thức exhaustive.

**Hợp đồng số liệu:** n phải không âm và `2n` còn chứa được trong `int`; literal phải khác 0 và có trị tuyệt đối `1..n`. Hàm không sửa mảng clause đầu vào. Với công thức UNSAT, `values[]` rỗng và `component[]` vẫn chứa phân rã SCC để hỗ trợ chẩn đoán.

### Mã nguồn: TwoSatSccDemo.java

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class TwoSatSccDemo {
    record Answer(
        boolean satisfiable,
        boolean[] values,
        int[] component,
        int componentCount
    ) {}

    record Counts(int formulas, int sat, int unsat) {}

    // Frame cho DFS lượt 1, lưu hàng xóm kế tiếp.
    static final class Frame {
        final int vertex;
        int nextIndex;

        Frame(int vertex) {
            this.vertex = vertex;
        }
    }

    static final class MutableCounts {
        int checked, sat, unsat;

        Counts result() {
            return new Counts(checked, sat, unsat);
        }
    }

    // Literal +i => x_i, -i => ¬x_i, với i=1..n.
    // Node false của x_i = 2*(i-1), true = false+1.
    static int nodeOf(int literal, int n) {
        long index = Math.abs((long) literal);
        if (index < 1 || index > n) {
            throw new IllegalArgumentException(
                "literal outside variables");
        }
        return 2 * ((int) index - 1) + (literal > 0 ? 1 : 0);
    }

    static void addImplication(
            List<List<Integer>> graph,
            List<List<Integer>> reversed,
            int source, int target) {
        graph.get(source).add(target);
        reversed.get(target).add(source);
    }

    static Answer solve(int n, int[][] clauses) {
        if (n < 0 || n > Integer.MAX_VALUE / 2
                || clauses == null) {
            throw new IllegalArgumentException("bad variable count");
        }

        int nodes = 2 * n;
        List<List<Integer>> graph = new ArrayList<>(nodes);
        List<List<Integer>> reversed = new ArrayList<>(nodes);

        for (int i = 0; i < nodes; i++) {
            graph.add(new ArrayList<>());
            reversed.add(new ArrayList<>());
        }

        // (a ∨ b) tương đương (¬a -> b) và (¬b -> a).
        for (int[] clause : clauses) {
            if (clause == null || clause.length != 2) {
                throw new IllegalArgumentException(
                    "each clause needs exactly two literals");
            }
            int a = nodeOf(clause[0], n);
            int b = nodeOf(clause[1], n);
            addImplication(graph, reversed, a ^ 1, b);
            addImplication(graph, reversed, b ^ 1, a);
        }

        // Kosaraju lượt 1: DFS trên graph gốc.
        boolean[] seen = new boolean[nodes];
        List<Integer> finishOrder = new ArrayList<>(nodes);

        for (int root = 0; root < nodes; root++) {
            if (seen[root]) {
                continue;
            }

            ArrayDeque<Frame> stack = new ArrayDeque<>();
            seen[root] = true;
            stack.push(new Frame(root));

            while (!stack.isEmpty()) {
                Frame top = stack.peek();
                List<Integer> out = graph.get(top.vertex);

                if (top.nextIndex == out.size()) {
                    finishOrder.add(top.vertex);
                    stack.pop();
                    continue;
                }

                int v = out.get(top.nextIndex++);
                if (!seen[v]) {
                    seen[v] = true;
                    stack.push(new Frame(v));
                }
            }
        }

        // Kosaraju lượt 2: reverse finishOrder trên graph đảo.
        int[] component = new int[nodes];
        Arrays.fill(component, -1);
        int componentCount = 0;

        for (int i = finishOrder.size() - 1; i >= 0; i--) {
            int root = finishOrder.get(i);
            if (component[root] != -1) {
                continue;
            }

            ArrayDeque<Integer> stack = new ArrayDeque<>();
            component[root] = componentCount;
            stack.push(root);

            while (!stack.isEmpty()) {
                int u = stack.pop();

                for (int v : reversed.get(u)) {
                    if (component[v] == -1) {
                        component[v] = componentCount;
                        stack.push(v);
                    }
                }
            }
            componentCount++;
        }

        // x_i và ¬x_i trong cùng SCC => không thể SAT.
        for (int variable = 0; variable < n; variable++) {
            int falseNode = 2 * variable;
            int trueNode = falseNode + 1;

            if (component[falseNode] == component[trueNode]) {
                return new Answer(
                    false, new boolean[0],
                    component, componentCount);
            }
        }

        // SCC ID tăng theo topo từ nguồn tới đích.
        boolean[] values = new boolean[n];
        for (int variable = 0; variable < n; variable++) {
            values[variable] =
                component[2 * variable + 1]
                    > component[2 * variable];
        }
        return new Answer(true, values, component, componentCount);
    }

    static boolean literalValue(int literal, boolean[] values) {
        int index = (int) Math.abs((long) literal) - 1;
        return literal > 0 ? values[index] : !values[index];
    }

    // Oracle kiểm tra witness: đánh giá clause, không xem graph.
    static boolean satisfies(boolean[] values, int[][] clauses) {
        for (int[] clause : clauses) {
            if (!literalValue(clause[0], values)
                    && !literalValue(clause[1], values)) {
                return false;
            }
        }
        return true;
    }

    // Oracle độc lập: thử hết 2^n gán cho n<=20.
    static boolean bruteSatisfiable(int n, int[][] clauses) {
        if (n < 0 || n > 20) {
            throw new IllegalArgumentException(
                "brute force is only for small n");
        }
        for (int mask = 0; mask < (1 << n); mask++) {
            boolean ok = true;

            for (int[] clause : clauses) {
                int a = clause[0], b = clause[1];
                int ai = (int) Math.abs((long) a) - 1;
                int bi = (int) Math.abs((long) b) - 1;

                boolean av = ((mask & (1 << ai)) != 0) == (a > 0);
                boolean bv = ((mask & (1 << bi)) != 0) == (b > 0);
                if (!av && !bv) {
                    ok = false;
                    break;
                }
            }
            if (ok) {
                return true;
            }
        }
        return false;
    }

    static void checkFormula(
            int n, int[][] clauses, MutableCounts counts) {
        Answer result = solve(n, clauses);
        boolean expected = bruteSatisfiable(n, clauses);

        if (result.satisfiable() != expected) {
            throw new AssertionError(
                "SAT classification differs from brute force");
        }
        if (expected && (result.values().length != n
                || !satisfies(result.values(), clauses))) {
            throw new AssertionError(
                "solver returned invalid assignment");
        }
        if (!expected && result.values().length != 0) {
            throw new AssertionError(
                "UNSAT must return empty values");
        }

        counts.checked++;
        if (expected) {
            counts.sat++;
        } else {
            counts.unsat++;
        }
    }

    static void checkCombinations(
            int n, List<int[]> types,
            int[] selected, int depth,
            int start, MutableCounts counts) {
        if (depth == selected.length) {
            int[][] clauses = new int[selected.length][];
            for (int i = 0; i < selected.length; i++) {
                clauses[i] = types.get(selected[i]);
            }
            checkFormula(n, clauses, counts);
            return;
        }

        int last = types.size() - (selected.length - depth);
        for (int i = start; i <= last; i++) {
            selected[depth] = i;
            checkCombinations(
                n, types, selected, depth + 1, i + 1, counts);
        }
    }

    // Toàn bộ clause (a∨b) không phân biệt thứ tự a,b.
    // n<=2: mọi tập clause; n=3: mọi tập tối đa 4 clause.
    static Counts verifySmallFormulas() {
        MutableCounts counts = new MutableCounts();

        for (int n = 0; n <= 3; n++) {
            List<Integer> literals = new ArrayList<>();
            for (int lit = -n; lit <= n; lit++) {
                if (lit != 0) {
                    literals.add(lit);
                }
            }

            List<int[]> types = new ArrayList<>();
            for (int i = 0; i < literals.size(); i++) {
                for (int j = i; j < literals.size(); j++) {
                    types.add(new int[]{
                        literals.get(i), literals.get(j)
                    });
                }
            }

            if (n <= 2) {
                // n=0: 1 formula, n=1: 2^3,
                // n=2: 2^10 formulas.
                int total = 1 << types.size();
                for (int mask = 0; mask < total; mask++) {
                    List<int[]> selected = new ArrayList<>();
                    for (int i = 0; i < types.size(); i++) {
                        if ((mask & (1 << i)) != 0) {
                            selected.add(types.get(i));
                        }
                    }
                    checkFormula(
                        n, selected.toArray(new int[0][]), counts);
                }
            } else {
                // n=3 có 21 loại clause.
                // Tổ hợp chọn 0..4 loại clause, không lặp.
                for (int k = 0; k <= 4; k++) {
                    checkCombinations(
                        n, types, new int[k], 0, 0, counts);
                }
            }
        }
        return counts.result();
    }

    public static void main(String[] args) {
        int[][] sample = {
            {1, 2}, {-1, 2}, {1, -2}, {-2, -3}
        };
        Answer sat = solve(3, sample);
        System.out.println("SAT: " + sat.satisfiable());
        System.out.println("Assignment: "
                           + Arrays.toString(sat.values()));
        System.out.println("Satisfies clauses: "
                           + satisfies(sat.values(), sample));
        System.out.println("SCC ids: "
                           + Arrays.toString(sat.component()));

        int[][] contradiction = {
            {1, 1}, {-1, -1}
        };
        Answer unsat = solve(1, contradiction);
        System.out.println("Contradiction SAT: "
                           + unsat.satisfiable());
        System.out.println("Opposites same SCC: "
                           + (unsat.component()[0]
                              == unsat.component()[1]));

        int[][] xor = {{1, 2}, {-1, -2}};
        Answer xorResult = solve(2, xor);
        System.out.println("XOR SAT: "
                           + xorResult.satisfiable());
        System.out.println("XOR assignment: "
                           + Arrays.toString(xorResult.values()));
        System.out.println("XOR witness valid: "
                           + satisfies(xorResult.values(), xor));

        Answer free = solve(2, new int[0][]);
        System.out.println("No clauses assignment: "
                           + Arrays.toString(free.values()));

        Answer zero = solve(0, new int[0][]);
        System.out.println("Zero variables SAT: "
                           + zero.satisfiable() + ", values="
                           + Arrays.toString(zero.values()));

        Answer tautology = solve(1, new int[][]{{1, -1}});
        System.out.println("Tautology SAT: "
                           + tautology.satisfiable());

        boolean rejected = false;
        try {
            solve(2, new int[][]{{1, 0}});
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Zero literal rejected: " + rejected);

        Counts checked = verifySmallFormulas();
        System.out.println(
            "Exhaustive 2-SAT formulas n<=3: "
            + checked.formulas() + " OK ("
            + checked.sat() + " SAT, "
            + checked.unsat() + " UNSAT)");
    }
}
```

### Biên dịch và chạy

Cần **JDK 17 trở lên**, bởi ví dụ sử dụng `record`:

```bash
javac -encoding UTF-8 TwoSatSccDemo.java
java TwoSatSccDemo
```

**Stdout dự kiến:**

```text
SAT: true
Assignment: [true, true, false]
Satisfies clauses: true
SCC ids: [1, 2, 1, 2, 3, 0]
Contradiction SAT: false
Opposites same SCC: true
XOR SAT: true
XOR assignment: [false, true]
XOR witness valid: true
No clauses assignment: [false, false]
Zero variables SAT: true, values=[]
Tautology SAT: true
Zero literal rejected: true
Exhaustive 2-SAT formulas n<=3: 8580 OK (6887 SAT, 1693 UNSAT)
```

### Giải thích các kết quả

- **SAT: true** và phép gán `[true,true,false]` thỏa đúng cả bốn mệnh đề trong ví dụ ở mục 1.
- **SCC ids:** mảng `[1,2,1,2,3,0]` tương ứng node `[¬x1,x1,¬x2,x2,¬x3,x3]`. Mỗi biến có literal và phủ định ở **hai SCC khác nhau**.
- **Contradiction SAT: false:** hai unit clause `x1` và `¬x1` trái nhau, nên node 0/1 nằm trong cùng SCC.
- **XOR:** `(x1∨x2)∧(¬x1∨¬x2)` có hai phép gán thỏa; thuật toán trả một phép gán `[false,true]` và hàm kiểm tra clause xác nhận đúng.
- **No clauses:** bất kỳ phép gán nào cũng đúng; ở thứ tự Kosaraju trong code, hai biến tự do nhận `false,false`. Không kết luận chúng bị buộc false.
- **Zero variables:** công thức rỗng có phép gán rỗng hợp lệ, nên trả `SAT=true` với `values=[]`.
- **Tautology:** `(x1∨¬x1)` luôn đúng, không tạo mâu thuẫn giữa hai node.
- **Zero literal rejected:** `0` không mã hóa biến hợp lệ nên bị từ chối, thay vì âm thầm truy cập một node sai.

### Kiểm thử exhaustive 8.580 công thức có nghĩa gì?

Tập test có các **loại clause không phân biệt thứ tự hai literal** (vì `a∨b` và `b∨a` tương đương). Với `n` biến có `2n` literal, số loại clause gồm hai literal có thể trùng là:

```text
T(n) = (2n)*(2n+1)/2
```

Cụ thể:

| Số biến | Loại clause | Công thức được kiểm tra |
| ---: | ---: | ---: |
| `n=0` | 0 | 1 công thức rỗng |
| `n=1` | 3 | Toàn bộ `2³=8` tập clause |
| `n=2` | 10 | Toàn bộ `2¹⁰=1024` tập clause |
| `n=3` | 21 | Mọi tập **tối đa 4 loại clause khác nhau**: `C(21,0)+C(21,1)+...+C(21,4)=7547` |
| **Tổng** | — | **8.580 công thức** |

Trong tập này:

```text
SAT:   6.887
UNSAT: 1.693
Tổng:  8.580
```

Mỗi công thức được xử lý theo **hai cách không dùng chung lõi quyết định**:

1. 2-SAT dựa vào đồ thị suy diễn, Kosaraju và SCC.
2. Brute force thử mọi `2^n` phép gán, trực tiếp đánh giá từng clause bằng phép OR logic.

Nếu hai cách khác kết luận SAT/UNSAT thì kiểm thử dừng với `AssertionError`. Khi solver báo SAT, mã còn kiểm tra **phép gán nó trả về** có thỏa từng clause hay không, chứ không chỉ kiểm cờ SAT.

**Phạm vi kiểm thử:** Với ba biến, bộ sinh chỉ xét các tập **tối đa bốn loại clause phân biệt**, không phải toàn bộ `2²¹` tập clause. Các công thức có clause lặp y hệt không được liệt kê hết như các tổ hợp riêng, nhưng clause lặp **không làm đổi tính thỏa mãn** và code vẫn cho phép duplicate edges. Chứng minh định lý SCC ở mục 5–9 mới là cơ sở tổng quát cho mọi n/m trong giới hạn bộ nhớ.

## 13. Các trường hợp biên phải xử lý đúng

### Không có biến và không có mệnh đề

`n=0`, không có clause nào. Có đúng một phép gán rỗng. Kết quả **SAT**, assignment `[]`. Hai graph (gốc/đảo) đều không có node; Kosaraju hợp lệ và không cần chạy DFS.

### Có biến nhưng không có mệnh đề

Ví dụ `n=2`, `clauses=[]`. Mọi phép gán của hai biến đều thỏa. Thuật toán trả **một** trong bốn nghiệm. Không được tuyên bố nghiệm này là duy nhất hoặc một biến bị ép true/false.

### Unit clause

`(x1)` mã hóa `(x1∨x1)`; buộc x1 true. `(¬x1)` mã hóa `(¬x1∨¬x1)`; buộc x1 false. Nếu có cả hai, công thức UNSAT. Dù hai cạnh suy diễn trùng nhau, Kosaraju vẫn đúng.

### Clause hằng đúng

`(x1∨¬x1)` không ảnh hưởng tập nghiệm. Nó có thể sinh self-loop, nhưng **self-loop trên một literal** không phải mâu thuẫn giữa literal và phủ định.

### Cùng biến ở hai dấu

Clause `(x1∨¬x1)` luôn đúng, còn tập hai clause `(x1∨x1)∧(¬x1∨¬x1)` vô nghiệm. Chỉ nhìn hai dấu xuất hiện trong công thức **không đủ** để kết luận UNSAT; phải xét **sự liên hệ qua suy diễn**.

### Đồ thị suy diễn có nhiều SCC

Một công thức SAT có thể tạo nhiều SCC, có thể có nhiều cặp SCC không có cạnh nối. Việc đánh số phụ thuộc thứ tự DFS và cấu trúc graph; **không được dùng số SCC để tính số nghiệm**.

### Đường suy diễn dài

Nếu chuỗi suy diễn có hàng trăm nghìn node, DFS đệ quy có nguy cơ tràn stack JVM. DFS lặp bằng `ArrayDeque` giải quyết vấn đề **call stack**, nhưng vẫn cần đủ heap để chứa danh sách kề, graph đảo, các frame và mảng trạng thái.

### Trường hợp literal bị tràn trị tuyệt đối

Đừng viết `Math.abs(literal)` trực tiếp với `int` khi literal có thể là `Integer.MIN_VALUE`. Code chuyển sang `long`, xác thực miền biến rồi mới tính node. Nếu biến được đánh số ngoài phạm vi n, chương trình báo lỗi thay vì suy diễn sai.

## 14. Những lỗi thường gặp khi dùng SCC giải 2-SAT

**1. Tạo sai hai cạnh từ clause.** `(a∨b)` phải thành `¬a→b` và `¬b→a`. Sai dấu phủ định làm công thức biến chất.

**2. Dùng một node cho cả `x` và `¬x`.** Phải có **hai node riêng** cho mỗi biến; không thể phát hiện chúng nằm cùng SCC nếu đã gộp từ đầu.

**3. Sai quy tắc node `^1`.** XOR 1 chỉ đúng khi cặp đối lập là hai số chẵn/lẻ liên tiếp. Nếu map khác, phải sửa luôn phép phủ định node.

**4. Dùng `Math.abs(int)` mà không xét `Integer.MIN_VALUE`.** Chuyển sang `long` trước khi lấy abs và xác thực chỉ số.

**5. Nhầm đảo đồ thị với phủ định literal.** `Gᵀ` đảo chiều cạnh; `literal^1` đổi cực tính. Hai thao tác không thay thế nhau.

**6. Chạy Kosaraju lượt hai trên graph gốc.** Lượt một dùng G, lượt hai dùng **Gᵀ** theo finish giảm nếu muốn theo quy ước ở đây.

**7. Ghi finish khi phát hiện, không phải khi kết thúc.** Kosaraju cần **postorder** của DFS, không phải preorder.

**8. Chỉ gọi DFS từ node 0.** Implication graph có thể không liên thông theo nghĩa reachability; phải lặp qua **cả 2n node**, kể cả literal không xuất hiện trong clause nào.

**9. Kiểm tra có chu trình rồi tuyên bố UNSAT.** Chu trình giữa hai literal cùng chiều có thể hoàn toàn hợp lệ. Chỉ **`SCC(x)==SCC(¬x)`** là điều kiện UNSAT.

**10. Dùng `component[true] < component[false]` mà không xét cách đánh số.** Với lượt Kosaraju và ID của code, phép gán đúng là **`component[true]>component[false]`**. Nhiều tutorial dùng quy ước thứ tự SCC ngược, dẫn tới dấu so sánh khác.

**11. Tưởng thành phần SCC tự là phép gán.** Một SCC gồm nhiều literal đồng suy diễn, nhưng phải chọn **giá trị true/false tương thích trên cả DAG SCC**, không chỉ gán mọi SCC true.

**12. Không xử lý clause một literal.** Có thể mã hóa `(a)` thành `(a∨a)`. Không được bỏ qua vì cho rằng 2-SAT chỉ cho đúng hai literal khác nhau.

**13. Dùng SCC count để đếm số nghiệm.** Các SCC có ràng buộc một chiều và quan hệ phủ định; số nghiệm không bằng số SCC hoặc `2^(SCC/2)` nói chung.

**14. Không kiểm phép gán trả về.** Sau khi có assignment, nên kiểm trực tiếp mỗi clause với công thức ban đầu. Điều đó giúp bắt lỗi bất đẳng thức SCC hoặc map node.

**15. Nhầm OR với AND trong clause.** `(a∨b)` cho phép một trong hai đúng; công thức `F=clause1∧clause2∧...` yêu cầu tất cả clause đúng.

**16. Nhầm “at least one” với “exactly one”.** Chính xác một trong A,B cần cả `A∨B` và `¬A∨¬B`.

**17. Cố ép một clause ba literal thành 2-SAT bằng cách bỏ bớt literal.** Điều này thường làm mất nghiệm hợp lệ; không còn bài toán gốc.

**18. Bỏ qua self-loop và cạnh song song khi đánh giá tính đúng.** Self-loop không tự là UNSAT, và cạnh trùng chỉ làm tăng số mục adjacency. SCC vẫn dùng visited để tránh vòng lặp.

**19. Không xác thực input trước cấp phát.** n âm, literal 0, ngoài miền hoặc clause sai kích thước phải báo rõ. Tràn `2*n` trên `int` có thể làm sai kích thước mảng.

**20. Cho rằng mọi công thức vô nghiệm phải chứa một cặp unit clause đối lập.** Mâu thuẫn có thể đi qua **chuỗi suy diễn nhiều biến**; SCC phát hiện được cả các chuỗi đó.

## 15. Bài tập thực hành và checklist

**Bài 1 — Tạo đồ thị:** Với `(x1∨¬x2)`, ghi node của hai literal và hai cạnh suy diễn tương ứng theo quy ước chẵn=false, lẻ=true.

**Bài 2 — Bảng chân trị:** Lập bảng chân trị cho `(a∨b)`, `(¬a→b)` và `(¬b→a)`. Giải thích vì sao ba biểu thức tương đương.

**Bài 3 — Đơn vị:** Mã hóa `(x1)` và `(¬x1)` thành clause hai literal. Dự đoán component order và phép gán khi chỉ có một trong hai clause; khi có cả hai clause kết quả là gì?

**Bài 4 — Tautology:** Với `(x1∨¬x1)`, vẽ hai self-loop suy diễn. Vì sao không được coi là mâu thuẫn của x1 và ¬x1?

**Bài 5 — Same-value:** Biểu diễn điều kiện `x1↔x2` bằng hai clause; tạo graph suy diễn và tìm các SCC. Hai biến có bắt buộc true không, hay có nhiều nghiệm?

**Bài 6 — Exactly-one:** Biểu diễn đúng một trong A,B bằng hai clause 2-SAT. Liệt kê mọi gán và chỉ ra đúng hai gán thỏa.

**Bài 7 — Chuỗi suy diễn:** Tạo các clause sao cho `x1⇒x2⇒x3⇒¬x1` và một đường suy diễn ngược từ `¬x1⇒x1`. Theo điều kiện SCC, kết quả là gì?

**Bài 8 — Kosaraju:** Trên một implication graph nhỏ, ghi finish order ở lượt một, đảo thứ tự, chạy DFS trên graph đảo và đánh số SCC. Tại sao gán theo SCC ID phải biết chính xác thứ tự hai lượt?

**Bài 9 — Truy vết mâu thuẫn:** Nếu `x` và `¬x` cùng SCC, tìm hai đường `x⇒¬x` và `¬x⇒x` bằng DFS/BFS giới hạn trong SCC đó. Ghép chúng thành minh chứng cụ thể rằng công thức vô nghiệm.

**Bài 10 — Brute force oracle:** Với n≤3, sinh các công thức có ít mệnh đề, duyệt mọi phép gán 0..`2^n−1` và so SAT/UNSAT với SCC. Kiểm tra cả assignment thật khi solver báo SAT.

**Bài 11 — Đồ thị lớn:** Tạo chuỗi suy diễn dài có hàng chục nghìn literal. So sánh rủi ro call stack của Kosaraju đệ quy và bản DFS frame lặp; đo bộ nhớ graph và graph đảo.

**Bài 12 — Sắp lịch:** Mỗi biến `x_i` đại diện chọn ca sáng/chiều. Viết clause cho ràng buộc “A sáng kéo theo B chiều”, “A và B không cùng sáng”, rồi thử gộp thành công thức có nghiệm.

**Bài 13 — Tính bắt buộc của biến:** Khi F đang SAT, muốn biết `x1` bị buộc true, hãy thêm clause `(¬x1∨¬x1)` rồi chạy 2-SAT. Diễn giải trường hợp F mới UNSAT.

**Bài 14 — Hai cách đánh số SCC:** Cài Tarjan hoặc một biến thể Kosaraju với thứ tự đánh SCC khác. Tìm quy tắc khôi phục nghiệm tương ứng; đừng sao chép dấu `>` cũ nếu ID đảo chiều.

**Checklist trước khi nộp:**

1. **Đúng loại bài:** Mọi clause có tối đa hai literal, hay có ràng buộc ngoài 2-SAT?
2. **Biến và literal:** Mỗi biến có hai node đối lập, mã hóa dấu âm/dương nhất quán?
3. **Đồ thị:** `(a∨b)` sinh đúng hai cạnh `¬a→b` và `¬b→a`?
4. **Graph đảo:** Đã đảo hướng cạnh, không nhầm với phủ định node?
5. **DFS lượt một:** Có thăm toàn bộ `2n` node và ghi **finish order** thật?
6. **DFS lượt hai:** Có dùng graph đảo và xét thứ tự finish giảm dần?
7. **Kiểm tra mâu thuẫn:** Với mọi biến, `SCC(true)!=SCC(false)`?
8. **Khôi phục nghiệm:** Dấu so sánh ID khớp với **thứ tự đánh SCC của chính code**?
9. **Kết quả SAT:** Assignment thực sự thỏa từng clause của input gốc?
10. **Edge cases:** n=0, không clause, unit clause, tautology, duplicate clause, self-loop, literal ngoài miền?
11. **Tài nguyên:** `O(n+m)` thời gian/bộ nhớ, DFS lặp cho chuỗi suy diễn sâu, tránh ma trận kề `O(n²)`?
12. **Kiểm thử độc lập:** So SAT/UNSAT và witness với vét cạn trên các công thức rất nhỏ, không chỉ so hai thuật toán SCC dùng cùng bug?

**Tiêu chí hoàn thành:** Bạn có thể chuyển 2-CNF sang **đồ thị suy diễn**, tạo đúng hai node cho mỗi biến, tính **SCC bằng Kosaraju**, kiểm tra mâu thuẫn giữa literal và phủ định, khôi phục một phép gán bằng **thứ tự topo của SCC condensation DAG**, giải thích tại sao tiêu chí đó là cần và đủ, và kiểm tra thuật toán Java 17+ bằng brute force độc lập.
