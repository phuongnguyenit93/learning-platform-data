# Điều kiện bậc và liên thông trước khi dựng đường đi Euler

## 1. Đường đi Euler là gì, và vì sao cần kiểm tra trước?

Trong lý thuyết đồ thị, **đường đi Euler (Euler trail)** là một hành trình đi qua **mỗi cạnh đúng một lần**. Hành trình có thể đi qua **một đỉnh nhiều lần**, miễn là không dùng lại cùng một cạnh.

Nếu hành trình Euler **bắt đầu và kết thúc tại cùng một đỉnh**, ta gọi đó là **chu trình Euler (Euler circuit / Euler tour)**. Một số tài liệu dùng “đường đi Euler” như tên bao trùm, còn “đường đi Euler mở” khi hai đầu mút khác nhau. Bài này dùng:

- **Euler trail:** mỗi cạnh đúng một lần, đầu và cuối có thể khác nhau.
- **Euler circuit:** Euler trail có đầu và cuối trùng nhau.
- **Open Euler trail:** Euler trail có đầu và cuối khác nhau.

Ví dụ đồ thị vô hướng có ba cạnh `0--1`, `1--2`, `2--0`:

```text
0 -- 1
 \  /
  2

Đi Euler: 0 -> 1 -> 2 -> 0.
Ba cạnh vật lý đều được dùng đúng một lần;
đỉnh 0 xuất hiện hai lần, điều đó hoàn toàn hợp lệ.
```

Điểm khác biệt với **đường đi Hamilton**: Hamilton quan tâm đi qua **mỗi đỉnh** đúng một lần, còn Euler quan tâm dùng **mỗi cạnh** đúng một lần. Không được dùng tiêu chuẩn bậc của Euler để kết luận bài toán Hamilton.

Trước khi chạy thuật toán dựng đường đi như **Hierholzer**, ta nên kiểm tra **điều kiện bậc** và **liên thông**. Hai nhóm điều kiện kết hợp mới xác định liệu tất cả cạnh có thể nằm trên một hành trình liên tục hay không.

Đặc biệt:

> **Điều kiện bậc đúng nhưng các cạnh thuộc nhiều thành phần tách rời thì không có một đường đi Euler chứa hết các cạnh.**

Một chương trình chỉ đếm số đỉnh bậc lẻ hoặc chỉ so `inDegree`/`outDegree`, rồi lập tức chạy Hierholzer, có thể trả một tuyến đi chỉ bao phủ một thành phần và bỏ quên các cạnh khác.

Bài học phân biệt chính xác **đồ thị vô hướng** và **đồ thị có hướng**, cùng các trường hợp **đỉnh cô lập, cạnh song song và khuyên**. Cuối bài có chương trình **Java 17**: kiểm tra điều kiện trước, sau đó dựng và xác minh kích thước hành trình Euler; có lời giải vét cạn làm đối chứng trên đồ thị nhỏ.

## 2. Định nghĩa dữ liệu và quy ước về cạnh

Giả sử có `n` đỉnh `V=\{0,1,\ldots,n-1\}` và `m` **cạnh vật lý**. Trong cài đặt, mỗi lần xuất hiện cạnh có một **ID riêng**, kể cả hai cạnh cùng nối cùng cặp đỉnh.

### 2.1. Đồ thị vô hướng

Cạnh vô hướng `\{u,v\}` có thể được đi qua theo cả hai chiều. Nếu có hai cạnh vật lý khác nhau cùng nối `u` và `v`, ta phải dùng **cả hai cạnh** đúng một lần; chúng không được gộp vì cùng hai đầu mút.

**Bậc của đỉnh** `deg(u)` là số đầu mút cạnh gắn với `u`, tính theo số lần xuất hiện:

- Cạnh `\{u,v\}` với `u\ne v` cộng `1` vào `deg(u)` và `1` vào `deg(v)`.
- **Khuyên (self-loop)** `\{u,u\}` đóng góp **2** vào `deg(u)`, dù chỉ là **một cạnh vật lý**.
- Hai cạnh song song `\{u,v\}` đóng góp tổng `2` vào bậc của mỗi đầu.

Định lý bắt tay:

\[
\sum_{u\in V}\deg(u)=2m.
\]

Do vậy, số đỉnh có bậc lẻ luôn là **số chẵn**.

### 2.2. Đồ thị có hướng

Cạnh có hướng `u\to v` chỉ được đi theo chiều từ `u` tới `v`. Ta có:

- `outDegree(u)`: số cạnh đi **ra** từ `u`.
- `inDegree(u)`: số cạnh đi **vào** `u`.
- Một khuyên `u\to u` cộng **1 vào inDegree** và **1 vào outDegree** của `u`.

Trên toàn đồ thị:

\[
\sum_{u\in V}outDegree(u)
=\sum_{u\in V}inDegree(u)=m.
\]

Khác với vô hướng, không thể chỉ đếm bậc lẻ/chẵn. Điều cần xét là **độ lệch bậc có hướng**:

\[
\Delta(u)=outDegree(u)-inDegree(u).
\]

Mỗi cạnh làm tổng độ lệch toàn đồ thị không đổi, vì vậy:

\[
\sum_{u\in V}\Delta(u)=0.
\]

### 2.3. Đỉnh cô lập

Một đỉnh **cô lập đối với các cạnh Euler** là:

- Trong đồ thị vô hướng: `deg(u)=0`.
- Trong đồ thị có hướng: `inDegree(u)+outDegree(u)=0`.

Khi `m>0`, đỉnh cô lập **không cần nằm trên hành trình**, vì không có cạnh nào ở đó để đi qua. Khi kiểm tra tính liên thông cho Euler, ta chỉ yêu cầu **các đỉnh có ít nhất một cạnh** thuộc cùng thành phần thích hợp.

Ví dụ, đồ thị gồm chu trình `0--1--2--0` và đỉnh `3` cô lập vẫn có chu trình Euler `0,1,2,0`. Kiểm tra toàn bộ `V` rồi từ chối vì `3` không tới được sẽ tạo **false negative**.

### 2.4. Đồ thị không có cạnh

Khi `m=0`, không có cạnh nào cần dùng. Theo **quy ước của bài và mã mẫu**:

- Nếu `n>0`, tồn tại hành trình Euler tầm thường **`[0]`** (độ dài `0` cạnh), đồng thời là chu trình đóng tầm thường.
- Nếu `n=0`, dùng **danh sách đỉnh rỗng `[]`** để biểu diễn hành trình rỗng và trả `exists=true` theo quy ước xử lý của API.
- Không cố gọi BFS/DFS từ một đỉnh không tồn tại.

Một số đề thi quy ước “chu trình” phải chứa **ít nhất một cạnh**. Khi ấy hãy thay đổi chính sách của trường hợp `m=0` theo đúng đề; các điều kiện và chứng minh bên dưới tập trung vào `m>0`.

## 3. Đồ thị vô hướng: điều kiện cần và đủ cho Euler

Xét một **đa đồ thị vô hướng** hữu hạn, có thể có cạnh song song và khuyên, với `m>0`.

Đặt `V_+=\{u\mid deg(u)>0\}`. Xét đồ thị con trên `V_+`, cùng các cạnh gắn với chúng.

### Định lý vô hướng

Một **Euler circuit** tồn tại **khi và chỉ khi**:

1. Mọi đỉnh trong `V_+` nằm trong **cùng một thành phần liên thông**.
2. **Tất cả** đỉnh có bậc **chẵn**.

Một **Euler trail mở** tồn tại **khi và chỉ khi**:

1. Mọi đỉnh trong `V_+` nằm trong **cùng một thành phần liên thông**.
2. Có **đúng 2 đỉnh bậc lẻ**. Hành trình phải bắt đầu tại một đỉnh bậc lẻ và kết thúc tại đỉnh bậc lẻ còn lại.

Hệ quả khi chỉ hỏi **có tồn tại Euler trail (kể cả đóng)**:

\[
\boxed{\text{Liên thông trên }V_+
\quad\land\quad
\#\{u:\deg(u)\text{ lẻ}\}\in\{0,2\}.}
\]

| Số đỉnh bậc lẻ | Liên thông trên các đỉnh có cạnh? | Kết luận |
|---:|---|---|
| 0 | Có | Có **Euler circuit** |
| 2 | Có | Có **Euler trail mở** từ đỉnh lẻ thứ nhất tới đỉnh lẻ thứ hai |
| 4, 6, ... | Bất kỳ | **Không** có Euler trail |
| 0 hoặc 2 | Không | **Không** có Euler trail chứa mọi cạnh |

### 3.1. Vì sao mọi đỉnh trung gian phải có bậc chẵn?

Trong một hành trình đi qua mỗi cạnh đúng một lần, mỗi lần đến một **đỉnh trung gian** theo một cạnh chưa đi phải tiếp tục rời nó theo **một cạnh khác**. Các cạnh gắn với đỉnh trung gian vì vậy được ghép thành **cặp vào–ra**, tổng số cạnh incident là **chẵn**.

Nếu đầu và cuối khác nhau:

- Ở đỉnh bắt đầu, có một lần **ra** không cần ghép với lần **vào** trước đó, nên bậc lẻ.
- Ở đỉnh kết thúc, có một lần **vào** không cần ghép với lần **ra** sau đó, nên bậc lẻ.
- Mọi đỉnh khác đều chẵn.

Nếu hành trình đóng, đầu và cuối trùng nhau; mọi lần rời/đến cũng ghép thành cặp nên **mọi đỉnh bậc chẵn**.

Một khuyên gắn vào cùng đỉnh hai lần, nên đóng góp **2** và không làm thay đổi tính chẵn/lẻ. Nó vẫn phải được đi qua đúng **một lần** theo ID cạnh.

### 3.2. Vì sao phải liên thông trên các đỉnh có cạnh?

Một hành trình là một chuỗi liên tục. Nếu nó dùng được **mọi cạnh**, mọi đỉnh incident với cạnh đều xuất hiện trong hành trình, và từ một vị trí trên hành trình có thể đi theo chuỗi cạnh (bỏ qua hướng, vì đồ thị vô hướng) tới các vị trí khác. Vậy tất cả đỉnh có cạnh phải liên thông với nhau.

Điều kiện bậc **một mình** không thể bảo đảm điều này.

**Phản ví dụ:** có hai tam giác rời nhau:

```text
Thành phần A: 0--1, 1--2, 2--0
Thành phần B: 3--4, 4--5, 5--3

Mỗi đỉnh đều có bậc 2 (chẵn).
Nhưng không có cạnh nối giữa hai tam giác.
Không thể có một hành trình dùng hết 6 cạnh.
```

### 3.3. Vì sao các điều kiện cũng đủ?

Trường hợp **mọi bậc chẵn** và phần có cạnh liên thông:

1. Bắt đầu từ một đỉnh có cạnh chưa dùng.
2. Mỗi khi tới một đỉnh khác đỉnh bắt đầu qua một cạnh chưa dùng, số cạnh chưa dùng incident tại đỉnh đó vẫn cho phép tiếp tục thoát ra, trừ khi đã đi hết theo chu trình.
3. Ta có thể đi cho tới khi quay lại điểm xuất phát, thu một chu trình dùng các cạnh chưa dùng.
4. Nếu còn cạnh chưa dùng, vì phần có cạnh liên thông, tồn tại một đỉnh trên chu trình đã dựng còn cạnh chưa dùng; bắt đầu một chu trình bổ sung ở đó và **ghép (splice)** chu trình mới vào chu trình cũ.
5. Lặp đến khi hết cạnh.

Đây chính là tư tưởng của **Hierholzer**: xây và ghép các chu trình con; thuật toán với stack cho cùng kết quả mà không cần thao tác ghép tường minh.

Khi có **đúng hai đỉnh bậc lẻ** `s,t`, tưởng tượng **thêm một cạnh tạm** nối `s` và `t`. Khi đó cả hai đỉnh đổi từ bậc lẻ thành bậc chẵn, còn tính liên thông vẫn giữ. Ta có một chu trình Euler trong đồ thị mở rộng. **Bỏ cạnh tạm** khỏi chu trình và cắt chu trình tại vị trí cạnh ấy sẽ thu được một Euler trail từ `s` tới `t` trong đồ thị gốc.

Vậy điều kiện bậc và liên thông là **cần và đủ**, không chỉ là heuristic.

## 4. Ví dụ vô hướng: cùng bậc nhưng kết luận khác nhau

### 4.1. Đường Euler mở

```text
Cạnh: 0--1, 1--2

deg(0)=1 (lẻ)
deg(1)=2 (chẵn)
deg(2)=1 (lẻ)

Các đỉnh có cạnh thuộc cùng thành phần.
Euler trail mở: [0, 1, 2].
```

Bắt đầu từ `1` sẽ không phù hợp để dựng **một Euler trail mở dùng tất cả các cạnh**: đi một cạnh tới `0` hoặc `2` rồi không thể dùng nốt cạnh còn lại nếu vẫn không lặp cạnh. Với đúng hai đỉnh lẻ, hãy chọn **một trong hai đỉnh lẻ** làm đầu.

### 4.2. Chu trình Euler có đỉnh cô lập

```text
n=4
Cạnh: 0--1, 1--2, 2--0
Đỉnh 3 cô lập.

deg = [2,2,2,0]
Liên thông trên {0,1,2}: đúng.
Chu trình Euler: [0,1,2,0].
```

Không được yêu cầu BFS thăm cả đỉnh `3`.

### 4.3. Có đúng bốn đỉnh lẻ

```text
Cạnh: 0--1, 0--2, 0--3

deg = [3,1,1,1]
Có bốn đỉnh lẻ -> không có Euler trail.
```

Đồ thị liên thông nhưng vẫn **không đủ** vì điều kiện bậc sai.

### 4.4. Cạnh song song và khuyên

```text
n=2
ID 0: khuyên 0--0
ID 1: cạnh 0--1
ID 2: cạnh 0--1 (song song với ID 1)

deg(0)=2+1+1=4
deg(1)=1+1=2

Euler circuit: 0 -> 0 -> 1 -> 0
Dùng lần lượt edge ID 0, ID 1, ID 2.
```

Nếu chỉ lưu `Set<Integer>` hàng xóm của `0`, hai cạnh `0--1` bị gộp thành một, làm sai **số cạnh**, **bậc** và khả năng dùng mỗi cạnh đúng một lần.

## 5. Đồ thị có hướng: phải xét in-degree và out-degree

Với đồ thị có hướng, mỗi cạnh `u\to v` phải được dùng **đúng chiều**. Vì thế, ngoài liên thông, ta cần kiểm tra cân bằng số lần **vào/ra** của mỗi đỉnh.

Đặt:

\[
\Delta(u)=outDegree(u)-inDegree(u).
\]

### Định lý có hướng khi m>0

**Euler circuit** tồn tại **khi và chỉ khi**:

1. Mọi đỉnh có `inDegree(u)+outDegree(u)>0` thuộc cùng một thành phần khi **bỏ hướng tất cả cạnh** (gọi là **liên thông yếu** trên phần có cạnh).
2. Với **mọi** đỉnh: `inDegree(u)=outDegree(u)`, tức `\Delta(u)=0`.

**Euler trail mở** từ `s` đến `t` tồn tại **khi và chỉ khi**:

1. Các đỉnh có ít nhất một cạnh **liên thông yếu** với nhau.
2. Có đúng **một** đỉnh `s` với `\Delta(s)=+1` (đầu).
3. Có đúng **một** đỉnh `t` với `\Delta(t)=-1` (cuối).
4. Mọi đỉnh còn lại có `\Delta(u)=0`.

Nói gọn, với đồ thị có hướng và `m>0`:

\[
\boxed{
\text{liên thông yếu trên phần có cạnh}
\;\land\;
\begin{cases}
\Delta(u)=0\ \forall u,&\text{Euler circuit};\\
\Delta(s)=1,\ \Delta(t)=-1,\ \Delta(u)=0\text{ với }u\notin\{s,t\},&
\text{Euler trail mở}.
\end{cases}
}
\]

**Điều kiện này không yêu cầu toàn bộ đồ thị phải liên thông mạnh trước khi kiểm tra.** Đặc biệt một Euler trail **mở** như `0\to1\to2` là hoàn toàn hợp lệ dù không có đường đi từ `2` quay lại `0`.

### 5.1. Vì sao lệch bậc đúng bằng +1/-1?

Trên hành trình có hướng, mỗi lần tới một đỉnh trung gian bằng một cạnh **đi vào**, ta phải rời nó bằng một cạnh **đi ra**. Số lần vào và ra vì vậy bằng nhau tại các đỉnh trung gian.

Với hành trình mở từ `s` đến `t`:

- Tại `s`, có một lần đi ra ban đầu không có lần vào tương ứng: `outDegree(s)=inDegree(s)+1`.
- Tại `t`, có một lần đi vào cuối cùng không có lần ra tương ứng: `inDegree(t)=outDegree(t)+1`.
- Tại các đỉnh khác: `inDegree=outDegree`.

Nếu hành trình đóng, mọi lần vào đều ghép với một lần ra, nên tất cả các đỉnh đều cân bằng.

**Khuyên `u\to u`** tăng `inDegree(u)` và `outDegree(u)` mỗi loại một, nên `\Delta(u)` không đổi.

### 5.2. Liên thông yếu nghĩa là gì?

Ta bỏ chiều của từng cạnh `u\to v`, tạm xem thành cạnh vô hướng `u--v`, rồi BFS/DFS từ một đỉnh có ít nhất một cạnh.

Chỉ cần kiểm tra rằng **mọi đỉnh có `in+out>0`** được thăm. Các đỉnh có `in+out=0` được bỏ qua.

**Quan trọng:** “liên thông yếu” **một mình** không đủ. Nó phải đi **đồng thời** với điều kiện cân bằng lệch bậc. Nhưng khi các điều kiện lệch bậc nói trên đã thỏa, liên thông yếu trên phần có cạnh là điều kiện đủ; không phải thêm một điều kiện liên thông mạnh độc lập cho trail mở.

### 5.3. Vì sao cân bằng + liên thông yếu là đủ cho circuit?

Xét đồ thị có hướng có `in=out` tại mọi đỉnh và tất cả đỉnh có cạnh liên thông yếu.

Nếu chia các đỉnh có cạnh thành các **thành phần liên thông mạnh (SCC)**, đồ thị co mỗi SCC thành một đỉnh là một **DAG**. Trong DAG đó, giả sử có hơn một SCC. Vì phần có cạnh liên thông yếu, tồn tại một SCC nguồn không có cạnh từ SCC khác đi vào nhưng có ít nhất một cạnh đi ra.

Cộng `outDegree-inDegree` trên tất cả đỉnh thuộc SCC nguồn: các cạnh nội bộ triệt tiêu, cạnh đi vào từ ngoài bằng `0`, còn cạnh đi ra ngoài dương. Tổng độ lệch phải **dương**, mâu thuẫn `in=out` tại từng đỉnh.

Vậy không thể có nhiều SCC chứa cạnh; các đỉnh có cạnh thực sự thuộc cùng một SCC. Khi đã có cân bằng bậc và khả năng di chuyển theo cạnh có hướng, Hierholzer dựng được **Euler circuit**.

Chứng minh này giải thích vì sao một phép **BFS/DFS vô hướng để kiểm tra liên thông yếu** là đủ **sau khi** đã kiểm tra cân bằng bậc. Không được bỏ điều kiện cân bằng.

### 5.4. Vì sao trường hợp có một start/end cũng đủ?

Giả sử có đúng `s` với `\Delta(s)=+1`, `t` với `\Delta(t)=-1`, các đỉnh khác cân bằng và phần có cạnh liên thông yếu.

Ta **thêm một cạnh có hướng tạm `t\to s`**. Khi ấy:

- `outDegree(t)` tăng `1` nên `\Delta(t)` từ `-1` thành `0`.
- `inDegree(s)` tăng `1` nên `\Delta(s)` từ `+1` thành `0`.
- Các đỉnh khác không đổi.
- Liên thông yếu vẫn đúng.

Theo chứng minh cho trường hợp cân bằng, đồ thị mở rộng có **Euler circuit**. Trong chu trình đó, bỏ cạnh tạm `t\to s` và mở chu trình tại chỗ bị cắt, ta được một **Euler trail từ `s` tới `t`** dùng mỗi cạnh gốc đúng một lần.

Đây là chứng minh cấu trúc cho điều kiện đủ, không dựa trên việc “thử chạy Hierholzer thấy hợp lý”.

## 6. Ví dụ có hướng và những điều kiện dễ nhầm

### 6.1. Euler circuit có hướng

```text
Cạnh: 0->1, 1->2, 2->0

in  = [1,1,1]
out = [1,1,1]
Delta = [0,0,0]

Đồ thị liên thông yếu trên {0,1,2}.
Euler circuit: [0,1,2,0].
```

### 6.2. Euler trail mở không liên thông mạnh

```text
Cạnh: 0->1, 1->2

Delta(0)=+1
Delta(1)=0
Delta(2)=-1

Liên thông yếu: đúng.
Euler trail mở: [0,1,2].
```

Không có đường đi `2\to0`, nhưng điều đó **không cản trở** một hành trình Euler mở từ `0` tới `2`.

### 6.3. Hai vùng có cạnh nhưng không nối nhau

```text
Cạnh: 0->1, 1->0, 2->3, 3->2

Mọi đỉnh có in=out=1.
Nhưng {0,1} và {2,3} là hai thành phần yếu tách rời.
Không tồn tại một Euler trail dùng hết bốn cạnh.
```

Cũng như đồ thị vô hướng, **chỉ kiểm tra bậc** là không đủ.

### 6.4. Độ lệch sai

```text
Cạnh: 0->1, 0->2

Delta(0)=+2
Delta(1)=-1
Delta(2)=-1

Đồ thị liên thông yếu.
Nhưng có đỉnh lệch +2, nên không có Euler trail.
```

Không thể bắt đầu tại `0` và dùng hai cạnh ra mà không có cách quay lại `0` giữa hai lần rời đi.

### 6.5. Cạnh song song và khuyên

```text
Cạnh có ID:
0: 0->0
1: 0->1
2: 1->0

in(0)=2, out(0)=2
in(1)=1, out(1)=1

Euler circuit: [0,0,1,0].
```

Nếu có hai cạnh song song `0\to1`, chúng là **hai lần** tăng out-degree của `0` và in-degree của `1`, và phải được sử dụng đúng hai lần.

## 7. Bảng tổng hợp để kiểm tra trước khi dựng

| Tiêu chí | Vô hướng | Có hướng |
|---|---|---|
| Đại lượng bậc | `deg(u)`, khuyên tính **2** | `inDegree(u)` và `outDegree(u)`, khuyên đóng góp **1 cho mỗi loại** |
| Euler circuit | **0 đỉnh bậc lẻ** | `in=out` tại mọi đỉnh |
| Euler trail mở | **2 đỉnh bậc lẻ** | **1 đỉnh `out-in=+1`**, **1 đỉnh `out-in=-1`**, còn lại `0` |
| Đầu hợp lệ khi mở | Một trong hai đỉnh bậc lẻ | Đỉnh lệch `+1` |
| Cuối hợp lệ khi mở | Đỉnh bậc lẻ còn lại | Đỉnh lệch `-1` |
| Liên thông | Liên thông vô hướng trên đỉnh có `deg>0` | **Liên thông yếu** trên đỉnh có `in+out>0`, khi đã thỏa điều kiện bậc |
| Đỉnh cô lập | Không bắt buộc đưa vào đường nếu `m>0` | Không bắt buộc đưa vào đường nếu `m>0` |
| Cạnh vật lý | Không gộp cạnh song song; dùng ID cạnh | Không gộp cạnh song song; dùng ID cạnh |
| Dựng đường sau khi kiểm tra | Hierholzer | Hierholzer theo **hướng cạnh** |

**Trình tự thực hành khuyến nghị:**

1. Đọc và kiểm tra `n`, danh sách cạnh, miền chỉ số đỉnh.
2. Tính các bậc, theo đúng quy tắc về khuyên và cạnh song song.
3. Nếu `m=0`, xử lý riêng theo quy ước đề bài.
4. Kiểm tra **mẫu bậc** Euler (0/2 đỉnh lẻ hoặc 0 hay 1 cặp lệch `+1/-1`).
5. Tìm đỉnh bắt đầu hợp lệ.
6. Kiểm tra liên thông **chỉ trên các đỉnh có cạnh**.
7. Chỉ khi hai nhóm điều kiện đều đúng mới chạy **Hierholzer**.
8. Xác minh hành trình dùng đủ `m` cạnh, độ dài đỉnh đúng `m+1`, và đầu/cuối theo yêu cầu.

Nếu một điều kiện sai, trả **không tồn tại** thay vì thử dựng một hành trình rồi đoán lý do.

## 8. Hierholzer: dựng đường bằng stack và ID cạnh

Sau khi điều kiện tồn tại đã qua kiểm tra, thuật toán **Hierholzer** dựng Euler trail/circuit trong **`O(V+E)`** bằng cách đi theo các cạnh chưa dùng và quay lui khi không thể đi tiếp.

Thay vì nối chu trình con bằng cấu trúc phức tạp, ta dùng một **stack đỉnh đang đi**:

```text
stack.push(start)

while stack chưa rỗng:
    u = stack.top()

    tìm cạnh có ID chưa dùng, hợp lệ để đi từ u

    nếu tồn tại cạnh u->v hoặc u--v chưa dùng:
        đánh dấu ID cạnh đã dùng
        stack.push(v)
    ngược lại:
        reversedPath.add(stack.pop())

đảo ngược reversedPath thành đường Euler thực sự
```

Tại bước “không còn cạnh chưa dùng từ `u`”, đỉnh `u` được thêm vào **thứ tự ra**. Đảo danh sách đã hoàn thiện cho hành trình đúng chiều.

### 8.1. Vì sao cần ID cạnh?

Một cạnh vô hướng `\{u,v\}` thường được lưu **hai lần trong danh sách kề**: một mục ở `u` và một mục ở `v`. Hai mục đó phải mang **cùng một ID**. Khi dùng cạnh từ một đầu, đánh dấu `used[id]=true` để lần quét từ đầu kia không dùng lại chính cạnh đó.

Với hai **cạnh song song**, mỗi cạnh có một ID **khác nhau**; nếu gộp chúng theo cặp đỉnh, hành trình bị thiếu cạnh.

Với khuyên `u--u`, cùng ID có thể xuất hiện **hai lần trong danh sách kề của chính `u`** (vì mỗi đầu mút đều nằm ở `u`). Cờ `used[id]` bảo đảm khuyên chỉ được dùng **một lần**, dù gặp hai mục trong danh sách.

### 8.2. Đồ thị có hướng: chỉ thêm cạnh vào danh sách đi ra

Đối với cạnh có hướng `u\to v`:

- Thêm ID vào **danh sách cạnh ra `adj[u]`**.
- Khi đang đứng tại `u`, chỉ được đi tới `v`.
- **Không** thêm cạnh đảo chiều vào `adj[v]` cho thuật toán dựng đường.
- Có thể thêm kết nối hai chiều vào một cấu trúc **riêng `weakNeighbors`** chỉ để BFS/DFS kiểm tra liên thông yếu.

Nhầm lẫn hai loại adjacency này sẽ cho phép Hierholzer đi cạnh **ngược hướng**, tạo hành trình không hợp lệ dù mẫu bậc đúng.

### 8.3. Con trỏ để tránh quét lại cạnh

Nếu ở mỗi lượt cứ quét danh sách kề từ đầu để tìm một cạnh chưa dùng, các cạnh đã đi có thể bị kiểm tra nhiều lần, làm hiệu năng kém.

Dùng `cursor[u]` để giữ vị trí kế tiếp cần xem trong danh sách kề `adj[u]`. Khi gặp ID đã dùng, tăng con trỏ. Mỗi mục kề được duyệt qua tối đa một lần.

- Vô hướng: có khoảng **`2m` mục kề** (khuyên cũng có thể được thêm hai lần).
- Có hướng: có đúng **`m` mục cạnh đi ra**.
- Tổng di chuyển con trỏ và thao tác stack là **`O(V+E)`**.

### 8.4. Không được chỉ tin rằng có một đường “trông đúng”

Sau khi dựng từ một đỉnh bất kỳ trên đồ thị không Euler, Hierholzer có thể sinh ra một đường đi qua một **phần** cạnh. Nếu bỏ điều kiện liên thông và không kiểm tra số cạnh đã dùng, chương trình có thể trả kết quả không bao phủ toàn đồ thị.

Bởi vậy sau khi dựng, với `m>0`, tối thiểu kiểm tra:

- `usedEdges==m`.
- `path.size()==m+1`.
- `path[0]==start`.
- `path[m]==start` nếu cần circuit, hoặc `path[m]==end` nếu trail mở.

Đối chứng kỹ hơn còn kiểm tra **các cạnh được dùng tương ứng từng bước** với đúng ID, bảo đảm không đi ngược hướng hoặc dùng cạnh hai lần.

## 9. Java 17+ hoàn chỉnh: kiểm tra điều kiện rồi mới chạy Hierholzer

Chương trình sau có hai API độc lập:

- `undirectedEuler(n,edges)`: cho đa đồ thị **vô hướng**, có khuyên/cạnh song song.
- `directedEuler(n,edges)`: cho đa đồ thị **có hướng**, có khuyên/cạnh song song.

Cả hai API trả:

```text
Result(
    exists,   // có tồn tại Euler trail (mở hoặc đóng) không?
    circuit,  // nếu exists=true, hành trình có đóng không?
    path,     // danh sách đỉnh; m>0 thì đúng m+1 đỉnh
    reason    // "ok", "no edges" hoặc lý do điều kiện không đạt
)
```

Nếu không tồn tại, trả `exists=false`, `circuit=false` và `path=[]`. Nếu không có cạnh, dùng quy ước mục 2.4.

Chương trình:

1. **Validate** chỉ số đỉnh; nếu không hợp lệ thì ném `IllegalArgumentException`.
2. Tính bậc và tạo adjacency với **ID cạnh**.
3. Kiểm tra mẫu bậc, sau đó liên thông yếu/vô hướng trên các đỉnh có cạnh.
4. Nếu hợp lệ, chọn `start` và chạy chung một triển khai Hierholzer (chỉ khác cách đọc đầu bên kia của cạnh).
5. Xác minh số ID đã dùng, độ dài và hai đầu mút.
6. Không sửa danh sách cạnh đầu vào, không cố sinh đường khi điều kiện tồn tại sai.

**Tên tệp:** `EulerPreconditionsDemo.java`.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Deque;
import java.util.List;
import java.util.Objects;

public final class EulerPreconditionsDemo {
    private EulerPreconditionsDemo() {
    }

    // Với đồ thị vô hướng, from/to chỉ là hai đầu của một cạnh.
    // Với đồ thị có hướng, from -> to là chiều bắt buộc.
    public record Edge(int from, int to) {
    }

    public record Result(
            boolean exists,
            boolean circuit,
            List<Integer> path,
            String reason) {
        public Result {
            path = List.copyOf(path);
        }
    }

    private static void checkInput(int n, List<Edge> edges) {
        Objects.requireNonNull(edges, "edges");
        if (n < 0) {
            throw new IllegalArgumentException(
                "number of vertices must be nonnegative"
            );
        }
        for (Edge e : edges) {
            Objects.requireNonNull(e, "edge");
            if (e.from() < 0 || e.from() >= n
                    || e.to() < 0 || e.to() >= n) {
                throw new IllegalArgumentException(
                    "edge endpoint is out of range"
                );
            }
        }
    }

    private static List<List<Integer>> emptyAdj(int n) {
        List<List<Integer>> result = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            result.add(new ArrayList<>());
        }
        return result;
    }

    // BFS bỏ qua đỉnh cô lập; degree là deg (vô hướng)
    // hoặc in+out (có hướng). Các cạnh weak là VÔ HƯỚNG.
    private static boolean connectedOnEdges(
            int[] degree,
            List<List<Integer>> weak, int start) {
        boolean[] seen = new boolean[degree.length];
        Deque<Integer> queue = new ArrayDeque<>();
        seen[start] = true;
        queue.addLast(start);

        while (!queue.isEmpty()) {
            int u = queue.removeFirst();
            for (int v : weak.get(u)) {
                if (!seen[v]) {
                    seen[v] = true;
                    queue.addLast(v);
                }
            }
        }

        for (int u = 0; u < degree.length; u++) {
            if (degree[u] > 0 && !seen[u]) {
                return false;
            }
        }
        return true;
    }

    // Mỗi ID là đúng MỘT cạnh vật lý.
    // undirected=true: có thể đi theo cả hai chiều.
    // undirected=false: bắt buộc đi from[id] -> to[id].
    private static List<Integer> hierholzer(
            int n, int[] from, int[] to,
            List<List<Integer>> adj,
            boolean undirected, int start) {
        boolean[] used = new boolean[from.length];
        int[] cursor = new int[n];
        int usedEdges = 0;

        Deque<Integer> stack = new ArrayDeque<>();
        List<Integer> reversed = new ArrayList<>();
        stack.push(start);

        while (!stack.isEmpty()) {
            int u = stack.peek();
            List<Integer> ids = adj.get(u);

            while (cursor[u] < ids.size()
                    && used[ids.get(cursor[u])]) {
                cursor[u]++;
            }

            if (cursor[u] == ids.size()) {
                reversed.add(stack.pop());
            } else {
                int edgeId = ids.get(cursor[u]++);
                if (used[edgeId]) {
                    continue;
                }

                used[edgeId] = true;
                usedEdges++;

                int v = undirected
                    ? (from[edgeId] == u
                        ? to[edgeId] : from[edgeId])
                    : to[edgeId];
                stack.push(v);
            }
        }

        Collections.reverse(reversed);
        if (usedEdges != from.length
                || reversed.size() != from.length + 1) {
            throw new IllegalStateException(
                "Euler prerequisites were not sufficient"
            );
        }
        return List.copyOf(reversed);
    }

    public static Result undirectedEuler(
            int n, List<Edge> edges) {
        checkInput(n, edges);
        if (edges.isEmpty()) {
            return new Result(
                true, true, n == 0 ? List.of() : List.of(0),
                "no edges"
            );
        }

        int m = edges.size();
        int[] from = new int[m];
        int[] to = new int[m];
        int[] degree = new int[n];
        List<List<Integer>> adj = emptyAdj(n);
        List<List<Integer>> weak = emptyAdj(n);

        for (int id = 0; id < m; id++) {
            Edge e = edges.get(id);
            int u = e.from(), v = e.to();
            from[id] = u;
            to[id] = v;

            degree[u]++;
            degree[v]++; // Khuyên u==v làm bậc tăng 2.

            adj.get(u).add(id);
            adj.get(v).add(id); // Cùng ID cho hai đầu.

            weak.get(u).add(v);
            weak.get(v).add(u);
        }

        int oddCount = 0;
        int firstOdd = -1;
        int secondOdd = -1;
        int firstIncident = -1;

        for (int u = 0; u < n; u++) {
            if (degree[u] > 0 && firstIncident == -1) {
                firstIncident = u;
            }
            if ((degree[u] & 1) != 0) {
                oddCount++;
                if (firstOdd == -1) {
                    firstOdd = u;
                } else if (secondOdd == -1) {
                    secondOdd = u;
                }
            }
        }

        if (oddCount != 0 && oddCount != 2) {
            return new Result(
                false, false, List.of(),
                "odd degree count=" + oddCount
            );
        }

        boolean circuit = oddCount == 0;
        int start = circuit ? firstIncident : firstOdd;
        int end = circuit ? start : secondOdd;

        if (!connectedOnEdges(degree, weak, start)) {
            return new Result(
                false, false, List.of(),
                "non-isolated vertices disconnected"
            );
        }

        List<Integer> path = hierholzer(
            n, from, to, adj, true, start
        );
        if (path.get(0) != start
                || path.get(path.size() - 1) != end) {
            throw new IllegalStateException(
                "Euler endpoint invariant failed"
            );
        }
        return new Result(true, circuit, path, "ok");
    }

    public static Result directedEuler(
            int n, List<Edge> edges) {
        checkInput(n, edges);
        if (edges.isEmpty()) {
            return new Result(
                true, true, n == 0 ? List.of() : List.of(0),
                "no edges"
            );
        }

        int m = edges.size();
        int[] from = new int[m];
        int[] to = new int[m];
        int[] in = new int[n];
        int[] out = new int[n];
        int[] totalDegree = new int[n];
        List<List<Integer>> outgoing = emptyAdj(n);
        List<List<Integer>> weak = emptyAdj(n);

        for (int id = 0; id < m; id++) {
            Edge e = edges.get(id);
            int u = e.from(), v = e.to();
            from[id] = u;
            to[id] = v;

            out[u]++;
            in[v]++;
            totalDegree[u]++;
            totalDegree[v]++;

            outgoing.get(u).add(id); // KHÔNG thêm chiều ngược.
            weak.get(u).add(v);
            weak.get(v).add(u);
        }

        int plusCount = 0;
        int minusCount = 0;
        int start = -1;
        int end = -1;
        int firstOutgoing = -1;
        boolean badDelta = false;

        for (int u = 0; u < n; u++) {
            if (out[u] > 0 && firstOutgoing == -1) {
                firstOutgoing = u;
            }
            int delta = out[u] - in[u];
            if (delta == 1) {
                plusCount++;
                start = u;
            } else if (delta == -1) {
                minusCount++;
                end = u;
            } else if (delta != 0) {
                badDelta = true;
            }
        }

        boolean circuit = !badDelta
            && plusCount == 0 && minusCount == 0;
        boolean open = !badDelta
            && plusCount == 1 && minusCount == 1;

        if (!circuit && !open) {
            return new Result(
                false, false, List.of(),
                "in/out degree imbalance"
            );
        }

        if (circuit) {
            start = firstOutgoing;
            end = start;
        }
        if (!connectedOnEdges(totalDegree, weak, start)) {
            return new Result(
                false, false, List.of(),
                "non-isolated vertices disconnected"
            );
        }

        List<Integer> path = hierholzer(
            n, from, to, outgoing, false, start
        );
        if (path.get(0) != start
                || path.get(path.size() - 1) != end) {
            throw new IllegalStateException(
                "Euler endpoint invariant failed"
            );
        }
        return new Result(true, circuit, path, "ok");
    }

    private static void show(String label, Result result) {
        System.out.println(
            label
            + ": exists=" + result.exists()
            + " circuit=" + result.circuit()
            + " path=" + result.path()
            + " reason=" + result.reason()
        );
    }

    public static void main(String[] args) {
        show("U triangle", undirectedEuler(
            3, List.of(
                new Edge(0, 1), new Edge(1, 2),
                new Edge(2, 0)
            )
        ));
        show("U open", undirectedEuler(
            3, List.of(
                new Edge(0, 1), new Edge(1, 2)
            )
        ));
        show("U loop parallel", undirectedEuler(
            2, List.of(
                new Edge(0, 0), new Edge(0, 1),
                new Edge(0, 1)
            )
        ));
        show("U isolated vertex", undirectedEuler(
            4, List.of(
                new Edge(0, 1), new Edge(1, 2),
                new Edge(2, 0)
            )
        ));
        show("U disconnected", undirectedEuler(
            6, List.of(
                new Edge(0, 1), new Edge(1, 2),
                new Edge(2, 0), new Edge(3, 4),
                new Edge(4, 5), new Edge(5, 3)
            )
        ));
        show("U four odd", undirectedEuler(
            4, List.of(
                new Edge(0, 1), new Edge(0, 2),
                new Edge(0, 3)
            )
        ));
        show("D triangle", directedEuler(
            3, List.of(
                new Edge(0, 1), new Edge(1, 2),
                new Edge(2, 0)
            )
        ));
        show("D open", directedEuler(
            3, List.of(
                new Edge(0, 1), new Edge(1, 2),
                new Edge(2, 1)
            )
        ));
        show("D loop parallel", directedEuler(
            2, List.of(
                new Edge(0, 0), new Edge(0, 1),
                new Edge(1, 0)
            )
        ));
        show("D disconnected", directedEuler(
            4, List.of(
                new Edge(0, 1), new Edge(1, 0),
                new Edge(2, 3), new Edge(3, 2)
            )
        ));
        show("D bad degree", directedEuler(
            3, List.of(
                new Edge(0, 1), new Edge(0, 2)
            )
        ));
        show("D DAG open", directedEuler(
            3, List.of(
                new Edge(0, 1), new Edge(1, 2)
            )
        ));
        show("U no edges", undirectedEuler(
            3, List.of()
        ));
        show("D zero vertices", directedEuler(
            0, List.of()
        ));

        boolean rejected = false;
        try {
            undirectedEuler(
                3, List.of(new Edge(0, 3))
            );
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("Invalid endpoint rejected: " + rejected);
    }
}
```

Lưu tệp bằng UTF-8, biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 EulerPreconditionsDemo.java
java EulerPreconditionsDemo
```

**Đầu ra chuẩn** (đường đi cố định theo thứ tự edge ID đã liệt kê):

```text
U triangle: exists=true circuit=true path=[0, 1, 2, 0] reason=ok
U open: exists=true circuit=false path=[0, 1, 2] reason=ok
U loop parallel: exists=true circuit=true path=[0, 0, 1, 0] reason=ok
U isolated vertex: exists=true circuit=true path=[0, 1, 2, 0] reason=ok
U disconnected: exists=false circuit=false path=[] reason=non-isolated vertices disconnected
U four odd: exists=false circuit=false path=[] reason=odd degree count=4
D triangle: exists=true circuit=true path=[0, 1, 2, 0] reason=ok
D open: exists=true circuit=false path=[0, 1, 2, 1] reason=ok
D loop parallel: exists=true circuit=true path=[0, 0, 1, 0] reason=ok
D disconnected: exists=false circuit=false path=[] reason=non-isolated vertices disconnected
D bad degree: exists=false circuit=false path=[] reason=in/out degree imbalance
D DAG open: exists=true circuit=false path=[0, 1, 2] reason=ok
U no edges: exists=true circuit=true path=[0] reason=no edges
D zero vertices: exists=true circuit=true path=[] reason=no edges
Invalid endpoint rejected: true
```

### Giải thích các dòng đáng chú ý

- **U triangle:** mọi bậc chẵn và phần có cạnh liên thông, nên có Euler circuit.
- **U open:** hai đỉnh lẻ `0,2`, nên chọn `0` làm đầu và `2` làm cuối.
- **U loop parallel:** khuyên đóng góp `2` vào bậc; hai cạnh song song có ID khác nhau. Đường `0,0,1,0` dùng đủ **ba cạnh vật lý**.
- **U isolated vertex:** đỉnh `3` không có cạnh nhưng không cản trở việc đi hết ba cạnh của tam giác.
- **U disconnected:** tất cả bậc đều chẵn nhưng có hai thành phần có cạnh, nên không tồn tại đường Euler toàn đồ thị.
- **D open:** `0` có `out-in=+1`, `1` có `-1` và `2` cân bằng; đường `0,1,2,1` dùng cả ba cạnh đúng chiều.
- **D loop parallel:** self-loop được tính đồng thời vào `in`/`out` và được dùng một lần.
- **D disconnected:** điều kiện cân bằng bậc đúng, liên thông yếu sai.
- **D bad degree:** đỉnh `0` lệch `+2`, nên không thể có hành trình Euler.
- **D DAG open:** chỉ có đường `0\to1\to2`; dù không liên thông mạnh, Euler trail mở vẫn tồn tại.
- **No edges:** kết quả tuân theo quy ước hành trình rỗng đã nêu, không phụ thuộc tính liên thông của các đỉnh cô lập.

### Vì sao mã sử dụng `List<Edge>` thay vì ma trận kề?

Mỗi phần tử trong `List<Edge>` có ID chính là **chỉ số trong danh sách**. Hai cạnh song song là **hai phần tử khác nhau**, nên có hai ID và hai lần sử dụng riêng. Với khuyên, một phần tử cũng vẫn là **một cạnh duy nhất**.

Ma trận kề boolean chỉ ghi “có/không có cạnh giữa hai đỉnh”, dễ làm mất thông tin về số cạnh song song. Nếu dùng ma trận kề để xử lý đa đồ thị, phải lưu **số lượng cạnh** và quản lý lượt sử dụng thật cẩn thận.

### Vì sao kiểm tra trước rồi mới dựng?

Trong `undirectedEuler`, mã trả sớm nếu số đỉnh lẻ khác `0` và `2`, hoặc nếu các đỉnh có cạnh không liên thông. Trong `directedEuler`, mã trả sớm nếu độ lệch bậc không thuộc một trong hai mẫu hợp lệ, hoặc nếu phần có cạnh không liên thông yếu.

Chỉ khi đã có **chứng minh tồn tại** theo định lý, mã mới gọi `hierholzer`. Việc kiểm tra `usedEdges==m` và `path.size()==m+1` ở cuối là **lớp bảo vệ bổ sung cho lỗi triển khai**, không thay thế chứng minh điều kiện tồn tại.

## 10. Chứng minh Hierholzer dựng đúng đường sau khi kiểm tra

Ta cần hai phần: **cạnh không bị dùng lại** và **mọi cạnh được dùng hết trong một hành trình hợp lệ**.

### 10.1. Mỗi cạnh vật lý được dùng nhiều nhất một lần

Khi chọn cạnh ID `id`, mã lập tức đặt `used[id]=true`. Mọi mục adjacency có cùng ID về sau đều bị bỏ qua.

Vì vậy:

- Một cạnh vô hướng dù xuất hiện hai lần trong danh sách kề vẫn chỉ dùng một lần.
- Hai cạnh song song được dùng độc lập vì ID khác nhau.
- Một khuyên không được dùng lại chỉ vì có hai mục cùng ID ở một danh sách.

Do mỗi lần đẩy stack qua cạnh đều đánh dấu một ID chưa dùng, không bao giờ có hai bước đi dùng cùng cạnh.

### 10.2. Vì sao các cạnh được dùng hết?

Với đồ thị vô hướng có mọi bậc chẵn và phần có cạnh liên thông, mỗi khi bước vào một đỉnh trên một nhánh đi hiện tại, sự cân bằng theo cặp cạnh cho phép tiếp tục cho tới khi khép chu trình; nếu còn cạnh ở đâu đó, tính liên thông bảo đảm có thể mở rộng qua một đỉnh đã đi trong hệ thống các chu trình. Stack của Hierholzer mô phỏng việc ghép này: đỉnh chỉ được đưa vào `reversed` khi không còn cạnh chưa dùng incident tại nó.

Với hai đỉnh lẻ, chọn một đỉnh lẻ làm đầu; có thể chứng minh tương tự bằng cách **thêm cạnh tạm giữa hai đỉnh lẻ**, tạo bài toán mọi bậc chẵn, rồi bỏ cạnh tạm. Với đồ thị có hướng, lập luận tương tự sau khi **thêm cạnh tạm từ đỉnh cuối về đỉnh đầu**, cân bằng `in/out`.

Vì các điều kiện bậc và liên thông đã chứng minh tồn tại một đường đi Euler, cấu trúc stack của Hierholzer có thể dùng hết tất cả cạnh. Nếu một chương trình thực tế không dùng hết, đó là dấu hiệu **lỗi tính bậc, liên thông, ID, hướng hoặc trạng thái con trỏ**.

### 10.3. Vì sao đảo `reversed` thành một hành trình?

Khi `u` trên đỉnh stack **hết cạnh chưa dùng**, nó được đưa vào danh sách kết quả tạm. Những cạnh đi sâu hơn đã được xử lý trước; trình tự các đỉnh được hoàn tất là **thứ tự ngược** của hành trình Euler cuối cùng.

Đảo toàn bộ danh sách `reversed` tạo chuỗi đỉnh, mỗi cặp liên tiếp tương ứng với một cạnh đã được lấy từ stack và được đặt đúng vị trí theo quá trình hoàn tất. Phương pháp này tương đương ghép những chu trình con theo thứ tự xuất hiện.

Trong mã, số cạnh đã dùng được đếm và độ dài đường được kiểm tra:

\[
|\text{path}|=m+1.
\]

Với `m>0`, nếu một hành trình có `m` bước cạnh thì phải có đúng `m+1` lần ghi đỉnh (tính cả đầu và cuối). Kết hợp với cờ dùng cạnh và chứng minh Hierholzer, đây là kiểm tra nhất quán quan trọng.

### 10.4. Hai đầu mút và tính đóng

- Vô hướng, `0` đỉnh lẻ: đường bắt đầu và kết thúc cùng một đỉnh có cạnh.
- Vô hướng, `2` đỉnh lẻ: bắt đầu ở một đỉnh lẻ, kết thúc ở đỉnh lẻ còn lại.
- Có hướng, mọi `in=out`: đường đóng, đầu và cuối trùng nhau.
- Có hướng, một `+1` và một `-1`: đầu ở đỉnh `+1`, cuối ở đỉnh `-1`.

Chương trình chọn đầu theo những điều kiện này trước khi dựng, sau đó kiểm tra lại cuối đường. Nếu yêu cầu **một đầu mút cụ thể do đề bài cho**, cần thêm bước xác nhận đầu mút yêu cầu trùng với đỉnh bắt đầu hợp lệ; không mặc nhiên dùng đỉnh nhỏ nhất có bậc khác không.

## 11. Phân biệt kiểm tra có tồn tại với in đúng một đường Euler

Có thể có **nhiều** đường Euler khác nhau trong cùng một đồ thị. Thứ tự cạnh kề quyết định đường mà Hierholzer tạo ra. Một lời giải không nên giả định có một thứ tự duy nhất nếu đề chỉ yêu cầu “bất kỳ đường Euler nào”.

Ví dụ với tam giác vô hướng:

```text
0->1->2->0
0->2->1->0
```

Đó là hai cách đi hợp lệ trên cùng tập ba cạnh vật lý; nếu không cố định hướng khởi hành thì hai kết quả đều đúng.

Tương tự, với cạnh song song, **chuỗi đỉnh** có thể giống nhau nhưng **thứ tự edge ID** khác nhau. Nếu đề yêu cầu xuất **ID cạnh** hoặc thứ tự chính xác của các cạnh, chỉ lưu đường đỉnh có thể không đủ để phân biệt hai cạnh song song. Khi ấy sửa `hierholzer` để lưu **cả ID cạnh đã chọn** trong khung stack và đưa ID vào kết quả theo thứ tự hoàn tất tương ứng.

### Kiểm tra đầu vào có hay không có cạnh

- Nếu `m>0`, đầu hành trình phải là một đỉnh có cạnh (không phải đỉnh cô lập).
- Nếu `m=0`, tùy quy ước đề, có thể trả một đỉnh bất kỳ, đường rỗng hoặc báo không có “chu trình không tầm thường”.
- Nếu `n=0,m>0`, đầu vào vô lý vì không thể có cạnh hợp lệ; phải báo lỗi chỉ số.
- Nếu `n=0,m=0`, tránh truy cập `adj[0]` hoặc dùng `start=0` khi đỉnh `0` không tồn tại.

### Đồ thị có hướng và yêu cầu circuit

Nếu đề chỉ hỏi **có Euler circuit hay không**, trường hợp một `+1` và một `-1` **không đáp ứng** dù có Euler trail mở. Khi thiết kế API hoặc làm bài thi, đừng trả cùng một boolean cho hai yêu cầu mà không phân biệt loại đường.

Trong chương trình, `result.exists()` chỉ **có trail mở hoặc đóng**, còn `result.circuit()` nói rõ có đường đóng.

## 12. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Chỉ kiểm tra bậc mà không kiểm tra liên thông | Hai chu trình rời nhau đều chẵn/cân bằng nhưng không có một đường Euler | Kiểm tra thành phần của tất cả đỉnh **có cạnh** |
| Bắt mọi đỉnh, kể cả đỉnh cô lập, cùng liên thông | Từ chối nhầm đồ thị Euler hợp lệ có đỉnh cô lập | Chỉ kiểm tra `deg>0` hoặc `in+out>0` |
| Đếm khuyên vô hướng là bậc `1` | Sai chẵn/lẻ bậc | Khuyên `u--u` cộng **2** vào `deg(u)` |
| Đếm khuyên có hướng chỉ vào `in` hoặc chỉ vào `out` | Tạo chênh lệch bậc giả | Khuyên tăng cả `in` và `out` mỗi loại `1` |
| Gộp cạnh song song theo cặp đỉnh | Thiếu cạnh và thay đổi bậc | Lưu **mỗi cạnh một ID** |
| Nhầm Euler với Hamilton | Kiểm tra sai đối tượng “mỗi cạnh” vs “mỗi đỉnh” | Đọc chính xác yêu cầu hành trình |
| Vô hướng có 2 đỉnh lẻ nhưng bắt đầu ở đỉnh chẵn | Dễ mắc kẹt trước khi đi hết cạnh | Bắt đầu ở một trong hai đỉnh lẻ |
| Có hướng chỉ đếm tổng bậc chẵn | Không bảo đảm số lần vào/ra | Kiểm tra `out-in` tại từng đỉnh |
| Có hướng có một `+1` nhưng không có đúng một `-1` | Mẫu bậc không hợp lệ | Cần **đúng một cặp `+1/-1`** |
| Có hướng yêu cầu mạnh liên thông trước khi chấp nhận trail mở | Từ chối nhầm đường `0\to1\to2` | Kiểm tra **liên thông yếu + điều kiện bậc** |
| Có hướng chỉ kiểm tra liên thông yếu mà không xét bậc | Nhận nhầm đồ thị không Euler | Hai điều kiện phải đi cùng nhau |
| Dựng đồ thị có hướng bằng adjacency hai chiều | Đi ngược hướng cạnh thật | Tách adjacency **đi ra** và adjacency **yếu** |
| Khuyên được thêm hai mục nhưng không có `used[edgeId]` | Dùng cùng khuyên hai lần | Đánh dấu theo ID cạnh vật lý |
| Duyệt mọi cạnh từ đầu mỗi lần đứng ở đỉnh | Có thể bị quét lại nhiều lần, chậm | Dùng `cursor[u]` |
| Không kiểm tra `path.size()==m+1` | Có thể trả đường chỉ qua một thành phần | Đối chiếu số cạnh đã dùng và độ dài |
| Tin rằng kiểm tra độ dài tự nó chứng minh hướng mỗi cạnh | Có thể dùng cạnh đảo chiều sai | Xác nhận xây adjacency đúng và xét ID/hướng |
| Bắt buộc một đường duy nhất theo thứ tự cụ thể khi đề không yêu cầu | Nhận sai những đường Euler hợp lệ khác | Chấp nhận bất kỳ đường dùng mỗi cạnh đúng một lần |
| Quên trường hợp `m=0` | Không có đỉnh bắt đầu, lỗi truy cập mảng | Chốt quy ước riêng cho đường tầm thường |
| Trả một circuit khi chỉ có trail mở | Sai yêu cầu đầu/cuối trùng nhau | Phân biệt `exists` và `circuit` |
| Dùng số nguyên quá hẹp khi đếm cạnh/độ dài | Có thể tràn và sai mẫu bậc | Chọn kiểu số phù hợp với giới hạn đầu vào |
| Tính BFS trên hướng cạnh thật cho điều kiện “yếu” | Kiểm tra sai liên thông yếu | Tạo adjacency tạm bỏ hướng |
| Giả định bậc đúng thì mọi nhánh Hierholzer đều thành công mà không kiểm thử | Lỗi mã ID/con trỏ vẫn có thể xảy ra | Đối chứng với vét cạn trên đồ thị nhỏ |

## 13. Kiểm thử đối chứng bằng vét cạn trên đồ thị nhỏ

Vì định lý Euler liên quan hai điều kiện tương đối dễ cài sai, cách kiểm tra tốt là dùng một **oracle độc lập** trên đồ thị có ít cạnh:

> **Thử tất cả đường đi có thể tạo bằng cách chọn một cạnh chưa dùng tiếp theo.** Nếu có một hành trình dùng đúng `m` ID cạnh, tồn tại Euler trail.

### 13.1. Oracle vô hướng

Với `m\le10`:

1. Thử mỗi đỉnh `s` có ít nhất một cạnh làm đầu.
2. Duyệt đệ quy `dfs(u, usedMask)`.
3. Ở đỉnh `u`, thử **mọi ID cạnh chưa dùng** incident với `u`.
4. Với cạnh `\{u,v\}`, đi tới đầu còn lại, đánh dấu ID, rồi đệ quy.
5. Nếu số ID đã dùng bằng `m`, đã có một Euler trail.

Không dùng điều kiện bậc/định lý Euler trong oracle này; nó kiểm tra **trực tiếp định nghĩa đường đi**, nên có cấu trúc kiểm chứng khác với phương pháp chính.

### 13.2. Oracle có hướng

Tương tự, nhưng tại `u` chỉ thử ID cạnh có **nguồn `from==u`**. Nếu cạnh có hướng `v\to u` với `v\ne u`, ta **không được** dùng để rời `u`.

Để kiểm tra circuit riêng, yêu cầu đỉnh cuối bằng đỉnh bắt đầu sau khi dùng hết cạnh. Với mục tiêu “có Euler trail bất kỳ”, không bắt buộc hai đầu trùng.

### 13.3. Kiểm tra một đường được dựng

Nếu thuật toán trả `exists=true` và `m>0`, kiểm tra:

1. `path.length=m+1`.
2. Mỗi cặp liên tiếp trong `path` tương ứng **một cạnh vật lý chưa dùng**.
3. Đánh dấu ID cạnh vừa khớp; không khớp lại ID đã dùng.
4. Vô hướng: chấp nhận một trong hai chiều của cạnh vật lý.
5. Có hướng: chỉ chấp nhận đúng chiều `from\to to`.
6. Cuối cùng dùng **đúng `m` ID**, không bỏ sót.
7. Nếu `circuit=true`, đầu và cuối trùng; nếu `circuit=false` và `m>0`, đầu cuối khác nhau.

**Với cạnh song song**, khi kiểm tra chuỗi đỉnh, có thể chọn bất kỳ ID chưa dùng nào có đúng hai đầu mút/hướng tương ứng. Các cạnh song song hoàn toàn hoán đổi được theo chuỗi đỉnh, nhưng vẫn phải dùng đủ **số lượng ID**.

### 13.4. Các ca bắt buộc

```text
Đồ thị rỗng: n=0, m=0
Nhiều đỉnh nhưng không cạnh: n>0, m=0
Một cạnh vô hướng: 0--1
Một cạnh có hướng: 0->1
Tam giác vô hướng/hướng
Hai tam giác/chu trình tách rời
Một khuyên ở một đỉnh
Hai khuyên cùng đỉnh
Hai cạnh song song giữa cùng hai đỉnh
Bốn đỉnh bậc lẻ
Một đỉnh cô lập nằm ngoài thành phần có cạnh
Có hướng: cân bằng toàn bộ nhưng yếu không liên thông
Có hướng: một +1/-1 nhưng không liên thông yếu
Có hướng: một đỉnh lệch +2
Có hướng: Euler trail mở nhưng không có đường quay về đầu
```

Khi kiểm thử ngẫu nhiên, giữ seed, số đỉnh, thứ tự và ID của các cạnh. Nếu kết quả phân tích điều kiện không khớp oracle, in lại **bậc, thành phần liên thông và mảng cạnh** để tìm phản ví dụ nhỏ.

## 14. Độ phức tạp

Gọi `n=|V|` và `m=|E|`, đếm mỗi cạnh vật lý một lần:

- Kiểm tra miền chỉ số đỉnh: `O(m)`.
- Tính bậc và xây adjacency: `O(n+m)`.
- Kiểm tra mẫu bậc: `O(n)`.
- BFS/DFS liên thông trên phần có cạnh: `O(n+m)`.
- Hierholzer với `cursor[]` và `used[]`: `O(n+m)`.
- Kiểm tra độ dài/đầu cuối: `O(1)` ngoài dữ liệu đã xây.

Tổng thời gian:

\[
\boxed{O(n+m)}.
\]

Bộ nhớ phụ trong chương trình:

- Mảng bậc, `cursor[]`, visited: `O(n)`.
- Danh sách kề theo edge ID: `O(n+m)`.
- Danh sách hàng xóm dùng kiểm tra liên thông yếu: `O(n+m)`.
- Stack và đường Euler: tối đa `O(m+1)` phần tử (nếu có cạnh).

Vì thế tổng bộ nhớ phụ là:

\[
\boxed{O(n+m)}.
\]

Nếu đầu vào đã ở dạng adjacency cần thiết, có thể tái sử dụng một số cấu trúc; tuy nhiên trường hợp có hướng vẫn cần làm rõ cách kiểm tra liên thông **yếu** và cách duyệt cạnh **đúng chiều**.

### Có phải cứ đủ điều kiện là đường Euler duy nhất?

Không. Điều kiện tồn tại chỉ nói **ít nhất một** hành trình hợp lệ. Hierholzer có thể tạo các đường khác nhau khi thứ tự ID cạnh thay đổi. Việc tìm **đường đi Euler nhỏ nhất theo từ điển** hoặc **đếm số đường Euler** là những bài toán khác, có ràng buộc và kỹ thuật riêng.

## 15. Bài tập tự luyện

**Bài 1 — Đường mở hay chu trình?** Đồ thị vô hướng có các cạnh `0--1,1--2`. Có Euler trail không? Có Euler circuit không?

*Đáp án:* có trail mở từ `0` tới `2`; không có circuit vì `deg(0)=deg(2)=1`.

**Bài 2 — Bậc đúng nhưng liên thông sai.** Hai tam giác rời nhau có toàn đỉnh bậc `2`. Có một Euler circuit dùng cả sáu cạnh không?

*Đáp án:* không, vì các đỉnh có cạnh thuộc hai thành phần liên thông khác nhau.

**Bài 3 — Đỉnh cô lập.** Đồ thị `n=4` có tam giác trên `\{0,1,2\}` và đỉnh `3` cô lập. Có chu trình Euler không?

*Đáp án:* có, `[0,1,2,0]`. Không cần đi qua đỉnh `3` vì `3` không gắn với cạnh nào.

**Bài 4 — Khuyên.** Đồ thị vô hướng một đỉnh `0` có một khuyên `0--0`. `deg(0)` bằng bao nhiêu? Đường Euler?

*Đáp án:* `deg(0)=2`. Euler circuit là `[0,0]`, dùng đúng một cạnh khuyên.

**Bài 5 — Cạnh song song.** Hai đỉnh `0,1` có hai cạnh vật lý song song. Đếm bậc và nêu đường Euler.

*Đáp án:* cả hai bậc bằng `2`, Euler circuit `[0,1,0]`, dùng mỗi ID cạnh một lần.

**Bài 6 — Điều kiện có hướng.** Với `0\to1,1\to2`, tính `\Delta` và kết luận.

*Đáp án:* `\Delta(0)=+1`, `\Delta(1)=0`, `\Delta(2)=-1`; các đỉnh có cạnh liên thông yếu. Euler trail mở `[0,1,2]`, không có circuit.

**Bài 7 — Có hướng nhưng không mạnh liên thông.** Vì sao đường `0\to1\to2` vẫn là Euler trail dù không thể đi từ `2` về `0`?

*Đáp án:* một trail **mở** không yêu cầu quay về đầu. Điều kiện đủ là mẫu `+1/-1` và liên thông yếu trên đỉnh có cạnh.

**Bài 8 — Sai độ lệch.** Với `0\to1,0\to2`, tại sao không có Euler trail?

*Đáp án:* `\Delta(0)=+2`. Một hành trình liên tục không thể rời `0` hai lần nếu không có cạnh nào quay lại nó.

**Bài 9 — Tại sao thêm cạnh tạm?** Khi có đúng hai đỉnh lẻ `s,t` (vô hướng), thêm cạnh `s--t` giúp chứng minh điều gì?

*Đáp án:* cả hai đỉnh thành chẵn, nên đồ thị mở rộng có Euler circuit. Bỏ cạnh tạm khỏi circuit thu Euler trail mở trong đồ thị ban đầu.

**Bài 10 — Thêm cạnh tạm có hướng.** Với một `s` lệch `+1` và một `t` lệch `-1`, phải thêm cạnh tạm theo chiều nào?

*Đáp án:* thêm `t\to s`, giúp giảm `\Delta(s)` một đơn vị và tăng `\Delta(t)` một đơn vị, khiến tất cả cân bằng.

**Bài 11 — Hai adjacency khác nhau.** Đồ thị có cạnh `2\to5`. Vì sao adjacency dùng cho kiểm tra yếu có thể thêm cả `2--5`, nhưng adjacency dùng để dựng Euler chỉ được thêm `2\to5`?

*Đáp án:* kiểm tra yếu bỏ chiều để xem các đỉnh có cạnh thuộc cùng thành phần không; dựng đường phải đi **đúng hướng thật** của từng cạnh.

**Bài 12 — Đường đi có bao nhiêu đỉnh?** Nếu một Euler trail dùng đúng `m=17` cạnh và có cạnh trong đồ thị, danh sách đỉnh phải dài bao nhiêu?

*Đáp án:* `18` phần tử, vì mỗi bước cạnh bổ sung một đỉnh vào chuỗi hành trình.

**Bài 13 — Đếm kiểu số.** Nếu có rất nhiều cạnh song song, tại sao không thể lưu `boolean hasEdge[u][v]` rồi suy ra bậc?

*Đáp án:* boolean không giữ **số lần xuất hiện** của cạnh; hai cạnh song song bị gộp thành một, làm sai bậc và số ID cần dùng.

**Bài 14 — Thiết kế kiểm thử.** Hãy viết oracle vét cạn cho đồ thị nhỏ, duyệt các chuỗi cạnh chưa dùng theo ID. Vì sao oracle không nên dùng cùng công thức kiểm tra bậc để quyết định kết quả?

*Đáp án:* mục đích của oracle là đối chứng **độc lập** với định lý/cài đặt kiểm tra điều kiện; dùng lại cùng công thức có thể khiến cả hai cùng sai mà không phát hiện.

## 16. Checklist trước khi kết luận có Euler trail

Trước khi nhấn nút chạy Hierholzer, hãy tự trả lời:

1. **Bài yêu cầu dùng mỗi cạnh một lần hay mỗi đỉnh một lần?** Đó là Euler hay Hamilton?
2. **Đồ thị có hướng hay vô hướng?** Bậc cần kiểm tra tương ứng là `deg` hay `in/out`.
3. **Có khuyên và cạnh song song không?** Khuyên vô hướng phải cộng bậc `2`; mỗi cạnh có ID riêng.
4. **Có đỉnh cô lập không?** Khi có cạnh, chỉ kiểm tra liên thông trên các đỉnh incident với cạnh.
5. **Nếu vô hướng:** số đỉnh bậc lẻ có là `0` hoặc `2` không?
6. **Nếu có hướng:** tất cả `\Delta` bằng `0` hoặc đúng một `+1` và một `-1`?
7. **Liên thông thích hợp đã đúng chưa?** Vô hướng liên thông trên phần có cạnh, có hướng liên thông **yếu** trên phần có cạnh.
8. **Điểm bắt đầu có hợp lệ không?** 2 đỉnh lẻ thì bắt đầu ở đỉnh lẻ; có hướng mở thì bắt đầu ở `+1`; circuit có thể bắt đầu tại đỉnh bất kỳ có cạnh.
9. **Trường hợp `m=0` đã có quy ước chưa?** Không truy cập đỉnh không tồn tại.
10. **Hierholzer có dùng từng ID một lần và đúng hướng không?** Kiểm tra `usedEdges==m`, `path.size()==m+1`, đầu/cuối phù hợp.

## Ghi nhớ

Với đồ thị **vô hướng**, điều kiện cần và đủ để có Euler trail khi có cạnh là:

\[
\boxed{\text{Liên thông trên các đỉnh có cạnh}\ \land\
\text{số đỉnh bậc lẻ bằng }0\text{ hoặc }2.}
\]

**0 đỉnh lẻ** cho Euler circuit; **2 đỉnh lẻ** cho Euler trail mở.

Với đồ thị **có hướng**, cần liên thông **yếu** trên các đỉnh có cạnh và:

- Hoặc `inDegree(u)=outDegree(u)` tại mọi đỉnh ⇒ Euler circuit.
- Hoặc đúng một đỉnh có `out-in=+1`, đúng một đỉnh có `out-in=-1`, các đỉnh khác cân bằng ⇒ Euler trail mở từ `+1` tới `-1`.

Sau khi điều kiện đã đúng, dùng **Hierholzer với ID cạnh, con trỏ danh sách kề và stack**, đạt **`O(V+E)`** thời gian. Đừng nhầm **liên thông yếu** với mạnh liên thông trong bài có hướng mở, đừng đếm sai khuyên, đừng gộp cạnh song song và đừng yêu cầu đỉnh cô lập phải nằm trên hành trình. **Điều kiện bậc và liên thông phải được chứng minh cùng nhau, trước khi dựng đường.**
