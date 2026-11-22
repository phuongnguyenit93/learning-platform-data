# LCA qua duyệt Euler và truy vấn cực tiểu

**LCA** (*Lowest Common Ancestor – tổ tiên chung gần nhất*) của hai đỉnh u,v trong một **cây có gốc** là **đỉnh sâu nhất** đồng thời là tổ tiên của u và v. Bài toán LCA xuất hiện khi tính khoảng cách giữa hai đỉnh, tìm nơi hai nhánh gặp nhau, xử lý truy vấn trên cây, quan hệ tổ tiên, đường đi và nhiều thuật toán cấu trúc dữ liệu.

Một kỹ thuật đặc biệt hữu ích là chuyển LCA thành **RMQ** (*Range Minimum Query – truy vấn cực tiểu trên một đoạn mảng*) bằng **duyệt Euler**:

1. Duyệt DFS từ gốc, ghi một đỉnh vào dãy Euler **khi đi vào** và **sau mỗi lần quay về từ con**.
2. Ghi đồng thời **độ sâu** tương ứng với từng vị trí Euler.
3. Với mỗi đỉnh v, lưu `first[v]` là **vị trí xuất hiện đầu tiên** của v trong dãy.
4. Trả lời `LCA(u,v)` bằng **đỉnh có độ sâu nhỏ nhất** trong dãy Euler trên đoạn nối `first[u]` và `first[v]`.

Câu hỏi “tổ tiên chung gần nhất nằm ở đâu?” được chuyển thành “độ sâu nhỏ nhất trên một khoảng chỉ số là bao nhiêu, và thuộc đỉnh nào?”. Để trả lời RMQ nhanh, có thể dùng **Sparse Table** (tiền xử lý O(N log N), mỗi truy vấn O(1)) hoặc **Segment Tree** (xây O(N), mỗi truy vấn O(log N)). Ở đây N là số đỉnh; dãy Euler có chiều dài \(M=2N-1\).

Bài học trình bày cơ sở toán học, cách ghi Euler đúng, chứng minh quy về RMQ, hai cấu trúc truy vấn, chương trình **Java 17+ chạy độc lập**, kiểm thử và các giới hạn khi dùng cho cây lớn hoặc thay đổi gốc.

## 1. Định nghĩa tổ tiên và LCA trên cây có gốc

Cho một cây vô hướng, liên thông, không chu trình, gồm N đỉnh, chọn một **gốc** r. Mỗi đỉnh v khác gốc có **cha** `parent[v]`, là đỉnh ngay trước v trên đường từ r đến v.

- **Tổ tiên** của v gồm v, cha của v, cha của cha, ... cho tới r.
- Theo quy ước thường dùng, **mỗi đỉnh là tổ tiên của chính nó**.
- **Độ sâu** `depth[v]` là số cạnh từ r tới v: `depth[r]=0`; với v khác r, `depth[v]=depth[parent[v]]+1`.
- Một **tổ tiên chung** của u và v là đỉnh vừa nằm trên đường r→u vừa nằm trên đường r→v.
- **LCA(u,v)** là tổ tiên chung có độ sâu **lớn nhất**. Trên một cây có gốc, LCA của mọi cặp đỉnh tồn tại và duy nhất.

Ví dụ:

~~~text
          0
        /   \
       1     2
      / \   / \
     3   4 5   6
    / \  | |
   7   8 9 10
~~~

Các đỉnh được đánh số 0..10, gốc là 0.

- `LCA(7,8)=3`: cả 7 và 8 là con của 3.
- `LCA(7,9)=1`: hai nhánh qua 3 và 4 gặp nhau ở 1.
- `LCA(7,10)=0`: hai nhánh nằm ở hai phía gốc.
- `LCA(5,6)=2`: hai nhánh trong cây con của 2.
- `LCA(9,9)=9`: một đỉnh là tổ tiên của chính nó.
- `LCA(1,8)=1`: một đỉnh là tổ tiên của đỉnh còn lại.

**LCA phụ thuộc vào gốc.** Nếu đổi gốc, quan hệ cha–con và “tổ tiên” có thể thay đổi, dù đồ thị vô hướng giữ nguyên các cạnh. Mọi mảng `depth`, `first` và dãy Euler phải được hiểu **theo đúng gốc đã chọn**.

### Nếu đầu vào là rừng thay vì cây?

Trong một **rừng** có nhiều thành phần liên thông, hai đỉnh ở hai thành phần khác nhau **không có tổ tiên chung** nếu chưa định nghĩa một siêu gốc. Có thể xử lý mỗi cây độc lập và trả “không tồn tại” khi `componentId[u]!=componentId[v]`.

Ví dụ Java trong bài nhận **một cây liên thông** (N≥1, đúng N−1 cạnh vô hướng, không chu trình) và **từ chối** đầu vào không phải cây; nó không lén thêm siêu gốc. Vì vậy mọi cặp đỉnh hợp lệ đều có LCA.

## 2. Duyệt Euler nào được dùng cho LCA?

Có nhiều khái niệm “Euler tour” trong thuật toán. **Euler tour trên cây để tìm LCA** ở đây không phải bài **đường đi Euler** đi qua mỗi cạnh đúng một lần, và cũng không phải chỉ là dãy thời điểm vào `tin[v]` trong DFS.

Ta cần một **dãy đỉnh theo sự kiện DFS**:

1. **Ghi u khi lần đầu đi vào u**.
2. Với mỗi con v của u, duyệt toàn bộ cây con v.
3. **Ngay sau khi quay lại u từ v, ghi lại u một lần**.
4. Lặp lại cho mọi con.

Mã giả:

~~~text
eulerDfs(u, parent, depth):
    first[u] = euler.size
    euler.add(u)
    eulerDepth.add(depth)

    for v in adj[u]:
        if v == parent:
            continue
        eulerDfs(v, u, depth + 1)
        euler.add(u)          // Ghi khi quay về u.
        eulerDepth.add(depth)
~~~

**Mỗi cạnh cây được đi qua hai chiều** trong quá trình DFS (đi xuống và quay lên). Với N≥1 đỉnh, dãy chứa một lần ghi đầu tiên cho gốc và **hai sự kiện cho mỗi cạnh**:

\[
\boxed{M=2(N-1)+1=2N-1.}
\]

Một đỉnh lá chỉ xuất hiện một lần. Một đỉnh có k người con xuất hiện k+1 lần: một lần lúc đi vào và một lần sau mỗi con.

### Euler tour khác thứ tự khám phá DFS

Thứ tự **khám phá** chỉ ghi mỗi đỉnh đúng một lần, dài N. Nhưng dãy **Euler cho LCA** phải ghi cả lần quay về, dài \(2N-1\).

Ví dụ cây gốc 0 có hai con 1 và 2:

~~~text
    0
   / \
  1   2
~~~

Dãy chỉ ghi lúc vào: `[0,1,2]`, độ sâu `[0,1,1]`. Lấy min đoạn từ 1 đến 2 sẽ có độ sâu 1, **không cho LCA(1,2)=0**. Dãy Euler đúng phải là:

~~~text
Euler:   [0,1,0,2,0]
Depth:   [0,1,0,1,0]
first:    0 1   3
~~~

Từ vị trí `first[1]=1` tới `first[2]=3`, độ sâu nhỏ nhất là 0 ở vị trí 2, tương ứng đỉnh **0**. Ghi lại đỉnh cha khi quay về là điều **không thể bỏ** trong phép quy LCA→RMQ này.

### Dãy Euler có lặp đỉnh là bình thường

Dãy Euler chứa nhiều lần cùng một đỉnh, nhưng `first[u]` chỉ lưu **lần xuất hiện đầu tiên**. Không được thay `first[u]` bằng vị trí xuất hiện cuối cùng hoặc lưu mọi vị trí mà không có quy tắc rõ ràng. Phép quy chuẩn được chứng minh trên **first occurrence**.

**Độ sâu ở vị trí i** là `depth[euler[i]]`; hai vị trí khác nhau chứa cùng đỉnh phải có cùng độ sâu gốc. Mỗi bước liên tiếp của Euler thay đổi độ sâu đúng **+1** (đi xuống một cạnh) hoặc **−1** (quay lên một cạnh), trừ trường hợp dãy chỉ có một phần tử.

## 3. Ví dụ Euler tour hoàn chỉnh trên cây 11 đỉnh

Dùng cây trong phần 1, với danh sách cạnh được thêm theo thứ tự:

~~~text
0-1, 0-2, 1-3, 1-4, 2-5, 2-6,
3-7, 3-8, 4-9, 5-10
~~~

DFS duyệt hàng xóm **theo thứ tự thêm vào** và bỏ qua cha khi duyệt graph vô hướng. Dãy Euler thu được:

~~~text
Index:   0  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20
Vertex:  0  1  3  7  3  8  3  1  4  9  4  1  0  2  5 10  5  2  6  2  0
Depth:   0  1  2  3  2  3  2  1  2  3  2  1  0  1  2  3  2  1  2  1  0
~~~

Dạng mảng:

~~~text
euler     = [0,1,3,7,3,8,3,1,4,9,4,1,0,2,5,10,5,2,6,2,0]
tourDepth = [0,1,2,3,2,3,2,1,2,3,2,1,0,1,2,3,2,1,2,1,0]
first     = [0,1,13,2,8,14,18,3,5,9,15]
~~~

Ở đây `first` được xếp theo **ID đỉnh**: `first[0]=0`, `first[1]=1`, `first[2]=13`, `first[3]=2`, v.v.

### Truy vấn LCA(7,9)

- `first[7]=3`, `first[9]=9`.
- Đoạn Euler từ chỉ số 3 tới 9: `[7,3,8,3,1,4,9]`.
- Dãy độ sâu tương ứng: `[3,2,3,2,1,2,3]`.
- Giá trị nhỏ nhất **1** ở đỉnh **1** ⇒ `LCA(7,9)=1`.

### Truy vấn LCA(7,10)

- `first[7]=3`, `first[10]=15`.
- Trên đoạn Euler `[3,15]`, DFS phải quay về **gốc 0** trước khi chuyển sang cây con chứa 10.
- Vị trí 12 có `euler[12]=0`, `tourDepth[12]=0`.
- Vì không độ sâu nào âm, min trên đoạn là 0 ⇒ `LCA(7,10)=0`.

### Truy vấn LCA(9,9)

Cả hai mốc `first[9]` đều là **9**, nên đoạn RMQ chỉ gồm **một vị trí**, trả đỉnh 9. Không cần xử lý trường hợp u=v bằng một thuật toán khác.

### Truy vấn LCA(1,8)

Đỉnh 1 là tổ tiên của 8. Đoạn từ `first[1]=1` tới `first[8]=5` chứa đỉnh 1 ở đầu đoạn với độ sâu 1; DFS chưa thể đi ra khỏi cây con của 1 rồi khám phá 8 trước khi quay lại vùng chứa 8. Vì vậy min đoạn là 1 và LCA bằng 1.

## 4. Vì sao LCA là cực tiểu độ sâu trên một đoạn Euler?

Đặt:

\[
l=\min(first[u],first[v]),\quad r=\max(first[u],first[v]).
\]

Giả sử không mất tính tổng quát `first[u] <= first[v]`, và w là **LCA thật** của u,v.

**Nhận xét 1.** Trong lúc DFS đi từ lần đầu tới u cho tới lần đầu tới v, đường đi đang hoạt động phải đi từ u **lên tới w** (có thể u=w), rồi mới đi xuống các nhánh cần thiết tới v. Vì u,v nằm trong hai nhánh khác nhau dưới w, hoặc một đỉnh là tổ tiên của đỉnh kia, dãy Euler trên đoạn này có **ít nhất một lần xuất hiện của w**.

**Nhận xét 2.** Trước khi khám phá v lần đầu, DFS chưa thể rời khỏi toàn bộ cây con của w để đi lên một tổ tiên thật sự của w rồi quay lại cây con ấy: một khi DFS đã hoàn tất cây con w và quay lên trên, nó **không khám phá lại** một đỉnh chưa thăm trong chính cây con w. Vì vậy trên đoạn `[l,r]`, DFS không lên tới một đỉnh có độ sâu **nhỏ hơn depth[w]**.

Hai nhận xét cho:

\[
\boxed{\min_{i=l}^{r} tourDepth[i]=depth[w].}
\]

Ở độ sâu bằng `depth[w]` trong khoảng đó, đỉnh xuất hiện là **w**, bởi trong cây con w chỉ có một đỉnh có độ sâu này là chính w. Do đó:

\[
\boxed{LCA(u,v)=euler[\operatorname{argmin}_{i\in[l,r]}tourDepth[i]].}
\]

**Quan trọng:** RMQ không chỉ trả **giá trị độ sâu nhỏ nhất**, mà cần trả **vị trí (index) đạt cực tiểu**, để ánh xạ ngược ra đỉnh trong Euler. Nếu chỉ lưu giá trị min 1, ta không biết đỉnh cần trả là 1 hay một đỉnh khác có cùng độ sâu ngoài đoạn.

### Nếu nhiều vị trí có cùng độ sâu nhỏ nhất?

Có thể có nhiều vị trí Euler cùng biểu diễn **đỉnh LCA w**, như đoạn quay về w sau hai nhánh. Chọn **vị trí cực tiểu bên trái nhất** hoặc vị trí bên phải nhất đều trả **cùng một đỉnh w** trong phép quy LCA chuẩn. Chương trình dùng tie-break **vị trí bên trái nhất** để kết quả RMQ xác định.

Không được chọn đỉnh có ID nhỏ nhất trên đoạn thay cho đỉnh có **depth nhỏ nhất**; thứ tự ID và mức tổ tiên không có quan hệ toán học bắt buộc.

## 5. RMQ là bài toán gì?

**Range Minimum Query (RMQ)** trên một mảng A trả phần tử nhỏ nhất của **đoạn chỉ số** \([l,r]\). Với LCA, mảng A là `tourDepth`, nhưng cần trả **index của phần tử min**.

Có nhiều cấu trúc phù hợp:

| Giải pháp RMQ | Tiền xử lý / xây dựng | Thời gian mỗi truy vấn | Bộ nhớ |
|---|---:|---:|---:|
| Quét tuyến tính đoạn `[l,r]` | O(1) ngoài Euler | O(M) xấu nhất | O(1) ngoài Euler |
| Sparse Table cho min | **O(M log M)** | **O(1)** | **O(M log M)** |
| Segment Tree | **O(M)** | **O(log M)** | **O(M)** |
| Sqrt decomposition | O(M) | O(√M) | O(√M) |
| RMQ tuyến tính chuyên dụng | Có thể O(M) | Có thể O(1) | O(M) |

M=2N−1, nên các cận được viết theo N tương đương ở bậc lớn.

**Với cây tĩnh và rất nhiều truy vấn**, Sparse Table thường là lựa chọn thực dụng: O(N log N) tiền xử lý và O(1) cho mỗi LCA. **Với hạn chế bộ nhớ** hoặc muốn công cụ RMQ có cấu trúc tổng quát hơn, Segment Tree O(N) bộ nhớ và O(log N) truy vấn có thể phù hợp.

Đối với RMQ **min**, kết quả được phép ghép từ **hai đoạn có chồng lên nhau** khi dùng Sparse Table: min là phép kết hợp **idempotent** (\(\min(x,x)=x\)). Không thể tùy tiện dùng cách hai đoạn chồng nhau cho bài tính **tổng**, vì phần giao sẽ bị đếm hai lần.

## 6. Sparse Table: tiền xử lý một lần, LCA O(1)

Mảng `euler` dài M. Định nghĩa:

\[
st[k][i]=\text{chỉ số Euler có tourDepth nhỏ nhất trên đoạn }[i,i+2^k-1].
\]

**Khởi tạo** cho mọi `0<=i<M`:

\[
st[0][i]=i.
\]

**Quy hoạch động:** đoạn dài \(2^k\) được chia thành hai nửa liên tiếp dài \(2^{k-1}\):

\[
st[k][i]=
\operatorname{better}(st[k-1][i],st[k-1][i+2^{k-1}]).
\]

Hàm `better(a,b)` trả vị trí có `tourDepth` nhỏ hơn; nếu độ sâu bằng nhau, trả vị trí có **index nhỏ hơn**. Điều này bảo đảm kết quả xác định ở mọi cấp.

Bảng chỉ xây ở những i thỏa \(i+2^k\le M\), tránh truy cập mảng ngoài giới hạn.

### Truy vấn `RMQ(l,r)`

Đặt \(L=r-l+1\), \(k=\lfloor\log_2 L\rfloor\). Chọn hai đoạn độ dài \(2^k\):

- \([l,l+2^k-1]\)
- \([r-2^k+1,r]\)

Hai đoạn **phủ toàn bộ \([l,r]\)** và có thể chồng lên nhau. Trả:

\[
\boxed{better(st[k][l], st[k][r-2^k+1]).}
\]

Cần bảng `log2[len]` hoặc phép tính integer log cho mỗi truy vấn. Trong Java, tiền tính `log2[i]=log2[i/2]+1` cho i≥2 cho O(1) truy cập.

Ví dụ độ dài đoạn `[3,9]` là 7, nên \(k=2\), \(2^k=4\). Hai đoạn dùng để truy vấn là `[3,6]` và `[6,9]` (chồng tại index 6), cùng phủ đoạn từ 3 tới 9. Min của hai RMQ là min của toàn đoạn, không đếm sai vì đây là toán tử **min**.

### Độ phức tạp

Mỗi cấp k có O(M) vị trí, số cấp O(log M). Tiền xử lý cần **O(M log M)** thời gian và **O(M log M)** bộ nhớ. Mỗi truy vấn dùng một log2 lookup và hai ô bảng, nên **O(1)**.

Sau Euler tour O(N), tổng để xử lý Q truy vấn LCA bằng Sparse Table:

\[
\boxed{O(N\log N+Q)\text{ thời gian},\qquad O(N\log N)\text{ bộ nhớ}.}
\]

Sparse Table chuẩn này dành cho **mảng tĩnh**. Nếu cây đổi cạnh hoặc thay đổi gốc mà không tính lại Euler, `first` và dãy độ sâu có thể không còn hợp lệ; các truy vấn trên dữ liệu mới sẽ sai.

## 7. Segment Tree: xây O(N), mỗi LCA O(log N)

**Segment Tree** lưu cực tiểu độ sâu của mỗi đoạn Euler trong một cây nhị phân. Lá ứng với một **vị trí Euler**. Mỗi nút trong chứa index tốt hơn của hai con.

Có thể cài cây đoạn kiểu đệ quy hoặc dùng **cây lặp với kích thước lá lũy thừa 2**. Với base là lũy thừa 2 nhỏ nhất ≥M:

- `seg[base+i]=i` cho vị trí Euler thật i.
- Các lá dư được đặt `-1` (không chứa dữ liệu).
- Với các nút i từ `base-1` về 1: `seg[i]=better(seg[2*i],seg[2*i+1])`.
- Hàm `better` biết bỏ qua index `-1`.

Để RMQ đoạn [l,r], chuyển sang chỉ số lá `l+=base`, `r+=base`. Mỗi vòng lặp:

1. Nếu l là con **bên phải**, đưa `seg[l]` vào kết quả và tăng l.
2. Nếu r là con **bên trái**, đưa `seg[r]` vào kết quả và giảm r.
3. Chuyển cả hai biên lên cha bằng phép chia 2.

Số vòng lặp tối đa O(log M), mỗi vòng so sánh O(1). Do đó:

\[
\boxed{O(M)\text{ xây dựng},\quad O(\log M)\text{ mỗi RMQ},\quad O(M)\text{ bộ nhớ}.}
\]

Để LCA, ta chỉ lấy `l=min(first[u],first[v])`, `r=max(...)`, truy vấn segment tree rồi ánh xạ index Euler trả lại đỉnh.

**Segment Tree không tự làm thay đổi đúng–sai của phép quy LCA→RMQ.** Sai sót thường nằm ở cách ghi Euler, mảng first hoặc phép so sánh theo độ sâu, chứ không phải do chọn sparse hay segment.

### Có nên cập nhật giá trị RMQ nếu cây thay đổi?

Segment Tree thường hỗ trợ cập nhật giá trị tại một ô. Nhưng trong bài LCA, **Euler tour là cấu trúc phụ thuộc hình dạng cây**. Nếu **thêm/xóa cạnh hoặc đổi gốc**, không thể chỉ cập nhật một hoặc hai ô độ sâu rồi mặc nhiên giữ mảng Euler cũ; nhiều vị trí và quan hệ tổ tiên có thể thay đổi.

Vì vậy mã ví dụ xử lý **cây tĩnh**. Bài **LCA động** (thêm/xóa cạnh, đổi gốc liên tục) cần kỹ thuật khác hoặc tiền xử lý lại theo tình huống; không được gọi Segment Tree là giải pháp LCA động chỉ vì nó hỗ trợ point update.

## 8. Java 17+: tạo Euler tour, Sparse Table và Segment Tree

Chương trình **EulerLcaRmqDemo.java** có thể biên dịch/chạy trực tiếp. Nó dùng DFS **lặp với stack frame** để tạo Euler tour, tránh `StackOverflowError` do đệ quy quá sâu, rồi xây hai cấu trúc RMQ.

**Hợp đồng đầu vào:**

- N≥1, ID đỉnh `0..N-1`.
- Danh sách chứa đúng **N−1 cạnh vô hướng**; chương trình từ chối cạnh tự nối, cạnh trùng tạo chu trình và các trường hợp không phải cây.
- Gốc phải là một ID hợp lệ.
- Mảng danh sách kề giữ nguyên **thứ tự cạnh được truyền vào**, vì thứ tự DFS quyết định dãy Euler cụ thể.
- Truy vấn `lcaSparse(u,v)` và `lcaSegment(u,v)` trả cùng LCA.
- `distance(u,v)` trả số cạnh trên đường duy nhất giữa hai đỉnh bằng công thức độ sâu.
- Để minh họa rõ logic, `int[] euler` và `int[] tourDepth` có độ dài đúng \(2N-1\).

**Mã Java 17 đầy đủ:**

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class EulerLcaRmqDemo {
    static final class DisjointSet {
        final int[] parent;
        final int[] size;

        DisjointSet(int n) {
            parent = new int[n];
            size = new int[n];
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        int find(int u) {
            while (parent[u] != u) {
                parent[u] = parent[parent[u]];
                u = parent[u];
            }
            return u;
        }

        boolean unite(int u, int v) {
            u = find(u);
            v = find(v);
            if (u == v) {
                return false;
            }
            if (size[u] < size[v]) {
                int tmp = u;
                u = v;
                v = tmp;
            }
            parent[v] = u;
            size[u] += size[v];
            return true;
        }
    }

    static List<List<Integer>> buildTree(int n, int[][] edges) {
        Objects.requireNonNull(edges, "edges");
        if (n < 1 || edges.length != n - 1) {
            throw new IllegalArgumentException(
                "tree needs n>=1 and n-1 edges"
            );
        }

        List<List<Integer>> graph = new ArrayList<>();
        for (int u = 0; u < n; u++) {
            graph.add(new ArrayList<>());
        }

        DisjointSet dsu = new DisjointSet(n);
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2
                    || edge[0] < 0 || edge[0] >= n
                    || edge[1] < 0 || edge[1] >= n
                    || edge[0] == edge[1]) {
                throw new IllegalArgumentException("invalid tree edge");
            }
            int u = edge[0];
            int v = edge[1];
            if (!dsu.unite(u, v)) {
                throw new IllegalArgumentException(
                    "input contains a cycle"
                );
            }
            graph.get(u).add(v);
            graph.get(v).add(u);
        }
        // n-1 successful unions imply exactly one component.
        return graph;
    }

    static final class Frame {
        final int vertex;
        final int parent;
        int nextNeighbor;

        Frame(int vertex, int parent) {
            this.vertex = vertex;
            this.parent = parent;
        }
    }

    static final class Solver {
        final int n;
        final int root;
        final List<List<Integer>> graph;
        final int[] first;
        final int[] depth;
        final int[] euler;
        final int[] tourDepth;
        final int[] logs;
        final int[][] sparse;
        final int base;
        final int[] segment;
        int tourSize = 0;

        Solver(int n, int[][] edges, int root) {
            // Also prevents overflow in 2*n-1 and segment sizing.
            if (n < 1 || n > 100_000_000) {
                throw new IllegalArgumentException("unsupported n");
            }
            if (root < 0 || root >= n) {
                throw new IllegalArgumentException("invalid root");
            }

            this.n = n;
            this.root = root;
            this.graph = buildTree(n, edges);
            this.first = new int[n];
            this.depth = new int[n];
            Arrays.fill(first, -1);

            int m = 2 * n - 1;
            euler = new int[m];
            tourDepth = new int[m];
            makeEulerTour();
            if (tourSize != m) {
                throw new IllegalStateException("wrong Euler length");
            }

            logs = new int[m + 1];
            for (int i = 2; i <= m; i++) {
                logs[i] = logs[i / 2] + 1;
            }

            int levels = logs[m] + 1;
            sparse = new int[levels][];
            sparse[0] = new int[m];
            for (int i = 0; i < m; i++) {
                sparse[0][i] = i;
            }
            for (int k = 1; k < levels; k++) {
                int half = 1 << (k - 1);
                int width = 1 << k;
                sparse[k] = new int[m - width + 1];
                for (int i = 0; i + width <= m; i++) {
                    sparse[k][i] = better(
                        sparse[k - 1][i],
                        sparse[k - 1][i + half]
                    );
                }
            }

            // Iterative segment tree: leaves represent Euler positions.
            int p = 1;
            while (p < m) {
                p *= 2;
            }
            base = p;
            segment = new int[2 * base];
            Arrays.fill(segment, -1);
            for (int i = 0; i < m; i++) {
                segment[base + i] = i;
            }
            for (int i = base - 1; i >= 1; i--) {
                segment[i] = better(segment[2 * i],
                                    segment[2 * i + 1]);
            }
        }

        private void append(int u) {
            euler[tourSize] = u;
            tourDepth[tourSize] = depth[u];
            tourSize++;
        }

        // Each active frame remembers the next neighbor to inspect.
        // On returning from a child, append its parent again.
        private void makeEulerTour() {
            ArrayDeque<Frame> stack = new ArrayDeque<>();
            depth[root] = 0;
            first[root] = 0;
            append(root);
            stack.push(new Frame(root, -1));

            while (!stack.isEmpty()) {
                Frame f = stack.peek();
                List<Integer> neighbors = graph.get(f.vertex);

                if (f.nextNeighbor == neighbors.size()) {
                    stack.pop();
                    if (!stack.isEmpty()) {
                        append(stack.peek().vertex);
                    }
                    continue;
                }

                int v = neighbors.get(f.nextNeighbor++);
                if (v == f.parent) {
                    continue;
                }
                if (first[v] != -1) {
                    throw new IllegalStateException(
                        "cycle while making Euler tour"
                    );
                }

                depth[v] = depth[f.vertex] + 1;
                first[v] = tourSize;
                append(v);
                stack.push(new Frame(v, f.vertex));
            }
        }

        // Compare EULER POSITIONS by depth, then leftmost position.
        private int better(int a, int b) {
            if (a == -1) {
                return b;
            }
            if (b == -1) {
                return a;
            }
            if (tourDepth[a] != tourDepth[b]) {
                return tourDepth[a] < tourDepth[b] ? a : b;
            }
            return Math.min(a, b);
        }

        private void checkVertex(int u) {
            if (u < 0 || u >= n) {
                throw new IllegalArgumentException("invalid vertex");
            }
        }

        // Return the EULER POSITION of minimum depth on [left,right].
        private int rmqSparse(int left, int right) {
            int k = logs[right - left + 1];
            int a = sparse[k][left];
            int b = sparse[k][right - (1 << k) + 1];
            return better(a, b);
        }

        private int rmqSegment(int left, int right) {
            left += base;
            right += base;
            int result = -1;

            while (left <= right) {
                if ((left & 1) == 1) {
                    result = better(result, segment[left++]);
                }
                if ((right & 1) == 0) {
                    result = better(result, segment[right--]);
                }
                left /= 2;
                right /= 2;
            }
            return result;
        }

        int lcaSparse(int u, int v) {
            checkVertex(u);
            checkVertex(v);
            int left = Math.min(first[u], first[v]);
            int right = Math.max(first[u], first[v]);
            return euler[rmqSparse(left, right)];
        }

        int lcaSegment(int u, int v) {
            checkVertex(u);
            checkVertex(v);
            int left = Math.min(first[u], first[v]);
            int right = Math.max(first[u], first[v]);
            return euler[rmqSegment(left, right)];
        }

        long distance(int u, int v) {
            int ancestor = lcaSparse(u, v);
            return (long) depth[u] + depth[v]
                - 2L * depth[ancestor];
        }
    }

    public static void main(String[] args) {
        int[][] edges = {
            {0, 1}, {0, 2}, {1, 3}, {1, 4},
            {2, 5}, {2, 6}, {3, 7}, {3, 8},
            {4, 9}, {5, 10}
        };
        Solver solver = new Solver(11, edges, 0);

        System.out.println("Euler: "
            + Arrays.toString(solver.euler));
        System.out.println("Euler depths: "
            + Arrays.toString(solver.tourDepth));
        System.out.println("First: "
            + Arrays.toString(solver.first));

        int[][] queries = {
            {7, 8}, {7, 9}, {7, 10}, {5, 6},
            {9, 9}, {1, 8}, {0, 10}
        };
        for (int[] query : queries) {
            int u = query[0];
            int v = query[1];
            System.out.println("LCA(" + u + "," + v + "): "
                + solver.lcaSparse(u, v)
                + " / " + solver.lcaSegment(u, v));
        }

        System.out.println("Distance(7,9): "
            + solver.distance(7, 9));
        System.out.println("Distance(7,10): "
            + solver.distance(7, 10));

        Solver single = new Solver(1, new int[][] {}, 0);
        System.out.println("Single node LCA: "
            + single.lcaSparse(0, 0));

        try {
            new Solver(3, new int[][] {
                {0, 1}, {1, 0}
            }, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Cycle rejected: "
                + ex.getMessage());
        }

        try {
            solver.lcaSparse(-1, 10);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid vertex rejected: "
                + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac EulerLcaRmqDemo.java
java EulerLcaRmqDemo
~~~

**Stdout chính xác cho ví dụ trên:**

~~~text
Euler: [0, 1, 3, 7, 3, 8, 3, 1, 4, 9, 4, 1, 0, 2, 5, 10, 5, 2, 6, 2, 0]
Euler depths: [0, 1, 2, 3, 2, 3, 2, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 1, 2, 1, 0]
First: [0, 1, 13, 2, 8, 14, 18, 3, 5, 9, 15]
LCA(7,8): 3 / 3
LCA(7,9): 1 / 1
LCA(7,10): 0 / 0
LCA(5,6): 2 / 2
LCA(9,9): 9 / 9
LCA(1,8): 1 / 1
LCA(0,10): 0 / 0
Distance(7,9): 4
Distance(7,10): 6
Single node LCA: 0
Cycle rejected: input contains a cycle
Invalid vertex rejected: invalid vertex
~~~

### Vì sao dùng DFS lặp với frame?

Mã giả Euler đệ quy ở phần 2 rất dễ hiểu, nhưng một cây dạng đường dài N đỉnh có **độ sâu DFS N**, dễ gây `StackOverflowError` trên JVM. Bản Java dùng `Frame(vertex,parent,nextNeighbor)` để mô phỏng đúng:

- Khi lần đầu đi vào v: lưu `first[v]`, `depth[v]`, ghi v, đẩy frame(v).
- Khi còn hàng xóm: xét lần lượt theo thứ tự danh sách kề.
- Khi hết hàng xóm: pop frame(v), nếu còn frame cha thì **ghi lại đỉnh cha** như một lần quay về.
- Khi stack rỗng: đã hoàn tất DFS.

Nhờ vậy dãy đúng độ dài \(2N-1\) mà không dựa vào độ sâu call stack của Java.

### Vì sao phải kiểm tra đầu vào là một cây?

Nếu đồ thị có chu trình, dãy Euler kiểu “đi xuống rồi quay về trên cạnh cha” còn có thể chạy DFS tạo ra một **cây DFS**, nhưng LCA của các đỉnh trong đồ thị gốc có chu trình **không được định nghĩa theo cách tổ tiên duy nhất của cây gốc ban đầu**. Ta không thể lấy LCA trên cây DFS rồi coi nó là khái niệm tổ tiên duy nhất của graph tổng quát.

`buildTree` dùng DSU (*Disjoint Set Union*) để từ chối chu trình khi nạp cạnh, kể cả hai cạnh trùng hoặc self-loop; đồng thời yêu cầu đúng N−1 cạnh. Với N−1 cạnh và **không có chu trình**, graph vô hướng chắc chắn liên thông, vì vậy là một cây. Mã không chấp nhận rừng hoặc graph có hướng như một cây hợp lệ.

### Vì sao cả sparse và segment trả cùng kết quả?

Cả hai bảng đều chứa **chỉ số vị trí Euler đạt độ sâu nhỏ nhất**, chứ không chứa ID của đỉnh hoặc giá trị sâu nhất. Mọi phép so sánh dùng chung hàm `better`; khi hòa độ sâu, chọn **vị trí Euler nhỏ hơn**.

Mỗi truy vấn chuẩn hóa đoạn:

~~~text
left  = min(first[u], first[v])
right = max(first[u], first[v])
~~~

Với một đoạn cố định, cả hai RMQ đều lấy vị trí min của cùng mảng `tourDepth`, nên cho cùng `euler[index]`. Kết quả này được chứng minh bằng LCA ở phần 4.

### Lưu ý về kích thước lớn

Chương trình xây **cả Sparse Table lẫn Segment Tree** để minh họa và đối chiếu, nên tiêu tốn tổng bộ nhớ O(N log N). Nếu sản phẩm chỉ cần LCA O(1), có thể bỏ hẳn segment tree. Nếu chỉ muốn LCA O(log N) với ít bộ nhớ hơn, có thể bỏ sparse table.

Bộ giải có giới hạn kiểm tra `n<=100_000_000` nhằm tránh overflow trực tiếp ở phép tính `2*n-1`; đây **không phải lời hứa** rằng máy có thể cấp phát tất cả mảng cho N gần giới hạn đó. Trong ứng dụng thực tế, cần chọn N tối đa dựa trên RAM, giới hạn mảng Java và thời gian tiền xử lý. Đặc biệt với segment tree kiểu lũy thừa 2, cần xét thêm kích thước `2*base` trước khi cấp phát, hoặc dùng cấu trúc kích thước khác cho dữ liệu khổng lồ.

## 9. Công thức khoảng cách trên cây

Với cây **không trọng số** (mỗi cạnh có độ dài 1), đường từ u tới v đi **lên từ u tới LCA**, rồi **xuống từ LCA tới v**. Đặt w=LCA(u,v):

\[
\boxed{dist(u,v)=depth[u]+depth[v]-2\,depth[w].}
\]

Ví dụ:

- `dist(7,9)=3+3-2*1=4`.
- `dist(7,10)=3+3-2*0=6`.
- `dist(7,8)=3+3-2*2=2`.
- `dist(9,9)=0`.

Chỉ cần LCA O(1), ta có khoảng cách theo số cạnh cũng O(1) mỗi truy vấn sau tiền xử lý.

### Cây có trọng số

LCA **không phụ thuộc trọng số cạnh**: nó chỉ phụ thuộc hình dạng cây và gốc. Nếu mỗi cạnh có độ dài (có thể là số âm nếu bài chỉ hỏi tổng trên đường **duy nhất** của cây), tiền xử lý:

\[
rootSum[v]=\sum_{\text{cạnh trên đường }r\leadsto v}w(e).
\]

Sau đó:

\[
\boxed{pathSum(u,v)=rootSum[u]+rootSum[v]-2\,rootSum[LCA(u,v)].}
\]

Nếu trọng số biểu thị độ dài hình học cần không âm, đó là **ý nghĩa dữ liệu**, không phải điều kiện để công thức tổng đường duy nhất hoạt động trên cây. Dùng kiểu số đủ rộng, ví dụ long có kiểm tra overflow nếu trọng số lớn.

### Một ứng dụng khác: so sánh quan hệ tổ tiên

`u` là tổ tiên của `v` theo gốc đã chọn khi và chỉ khi `LCA(u,v)==u`. Sau tiền xử lý sparse table, truy vấn này O(1).

Nếu có rất nhiều truy vấn quan hệ tổ tiên nhưng không cần LCA tổng quát, có thể dùng `tin/tout` của DFS để kiểm tra tổ tiên cũng O(1) với tiền xử lý O(N). Không nên dùng toàn bộ Sparse Table khi một công cụ đơn giản đã đủ đáp ứng hợp đồng.

## 10. Sparse Table và Segment Tree chọn thế nào?

| Yêu cầu | Sparse Table Euler-RMQ | Segment Tree Euler-RMQ |
|---|---|---|
| Cây cố định, rất nhiều truy vấn LCA | **Rất phù hợp**: O(1) mỗi truy vấn | O(log N) mỗi truy vấn |
| RAM bị hạn chế | O(N log N) khá lớn | **O(N)** cho RMQ |
| Cần sửa một phần tử mảng RMQ độc lập | Phải xây lại các bảng liên quan | Hỗ trợ point update O(log N) |
| Muốn dễ giải thích bằng công thức đoạn \(2^k\) | Phù hợp | Phù hợp với chia đoạn nhị phân |
| Cây đổi cạnh hoặc đổi gốc | Phải tính lại Euler | **Cũng phải xử lý lại Euler**, không chỉ update một lá |
| Muốn kiểm thử chéo trong ví dụ học tập | Có thể so với quét đoạn | Có thể so với Sparse Table |

Ngoài ra có một cách tiếp cận **Binary Lifting** không cần dãy Euler RMQ: tiền xử lý \(up[k][v]\) là tổ tiên thứ \(2^k\) của v, rồi đưa hai đỉnh về cùng độ sâu và nâng đồng thời. Cách này thường O(N log N) tiền xử lý và O(log N) truy vấn; hữu ích nếu cũng cần **k-th ancestor**, đi lên k cấp, hoặc quan hệ tổ tiên.

Không nên khẳng định Binary Lifting và Euler-RMQ là **cùng một cấu trúc**: chúng giải LCA bằng cơ chế khác nhau và có những ưu điểm truy vấn khác nhau. Một phương pháp phù hợp sẽ phụ thuộc số đỉnh, số truy vấn và các thao tác khác cần hỗ trợ.

### Có cách LCA O(1) với tiền xử lý O(N) không?

Có những cấu trúc RMQ chuyên biệt và thuật toán LCA tối ưu hơn về lý thuyết (ví dụ các kỹ thuật dựa trên **±1 RMQ** của dãy độ sâu Euler và block decomposition). Chúng có thể đạt O(N) tiền xử lý, O(1) truy vấn, nhưng cài đặt phức tạp hơn Sparse Table.

Điểm đặc biệt của dãy Euler ở đây là **độ sâu hai vị trí liên tiếp chênh nhau đúng 1** trên cây. Một RMQ tổng quát không tự khai thác cấu trúc đó. Với đa số bài thực hành Java có kích thước vừa phải, Sparse Table O(N log N) đã dễ chứng minh và đáng tin cậy.

## 11. Các lỗi dễ làm LCA qua Euler sai hoàn toàn

### 11.1. Chỉ ghi mỗi đỉnh một lần

Nếu dùng DFS preorder dài N thay cho Euler dài 2N−1, khoảng giữa hai đỉnh ở hai nhánh không chắc chứa tổ tiên chung. Ví dụ `[0,1,2]` ở cây hai lá sẽ trả sai LCA(1,2).

**Cách sửa:** sau mỗi DFS con, phải ghi lại đỉnh cha **một lần**.

### 11.2. Ghi sai vị trí first occurrence

`first[v]` phải được gán ngay tại lần đầu ghi v vào Euler. Nếu cứ mỗi lần gặp v lại gán `first[v]=euler.size()`, nó thành vị trí **cuối cùng**, phép quy chuẩn không còn như chứng minh. Mã đặt first khi lần đầu push frame(v).

### 11.3. Dùng min theo ID đỉnh thay cho min theo độ sâu

Một mảng Euler chứa các ID như 7,3,8,1,4,9. Min theo ID trong đoạn có thể tình cờ trùng LCA ở ví dụ nhưng không có bảo đảm tổng quát. **LCA là tổ tiên theo độ sâu**, không phải ID thấp nhất.

Lưu index Euler và so sánh `tourDepth[index]`; sau RMQ mới trả `euler[index]`.

### 11.4. Quên chuẩn hóa trái–phải của khoảng

Với `first[u] > first[v]`, phải đổi thành `left=min(...)`, `right=max(...)`. Không thể truy vấn đoạn có trái lớn hơn phải rồi mong RMQ tự hiểu theo chiều ngược.

### 11.5. Sai quy tắc tie-break

Nếu hai vị trí có cùng độ sâu, trả một trong hai vị trí cực tiểu là hợp lệ cho giá trị min. Trong code cần so sánh **độ sâu trước, index sau** để Sparse Table và Segment Tree cho kết quả ổn định. Không nên xử lý tie bằng phép trừ có thể overflow hoặc bằng cách tùy tiện chọn ID đỉnh.

### 11.6. Dùng Sparse Table hai đoạn chồng cho phép cộng

RMQ min là idempotent nên lấy min từ hai đoạn chồng nhau hợp lệ. Nếu thay toán tử bằng sum, phần giao bị tính hai lần. Công thức truy vấn O(1) hai đoạn chồng **không** áp dụng nguyên dạng cho phép tổng.

### 11.7. Nhầm dãy Euler của LCA với tin/tout

Các thời điểm `tin[u]` và `tout[u]` hữu ích cho kiểm tra tổ tiên. Nhưng một mảng chỉ chứa `tin` của từng đỉnh **không tương đương** với dãy Euler ghi cả lúc quay về được dùng trong RMQ này.

Cũng không được nhầm Euler tour của LCA với bài tìm đường đi qua mỗi cạnh của đồ thị tổng quát đúng một lần. Tên “Euler” được dùng trong nhiều ngữ cảnh.

### 11.8. Áp dụng trực tiếp cho đồ thị có chu trình

LCA không có ý nghĩa tổ tiên duy nhất theo tree-root nếu đầu vào có chu trình và chưa chỉ rõ chọn cây nào. DFS tạo một cây DFS nhưng đó không phải cây gốc vốn có trong đề. Cần kiểm tra đầu vào đúng là cây.

### 11.9. Không xử lý gốc và u=v

Với `u=v`, LCA là u. Với `u=root`, LCA(root,v)=root. Với cây chỉ một đỉnh, dãy Euler dài 1, Sparse Table và Segment Tree phải vẫn hoạt động.

### 11.10. Coi độ sâu là số cạnh có trọng số

`depth[u]` trong LCA Euler là **số cạnh từ gốc**, không phải tổng trọng số. Nếu cây có trọng số âm/dương, vẫn phải dùng độ sâu **theo số cạnh** để so sánh tổ tiên. Tổng trọng số đường đi được tính bằng mảng `rootSum` riêng.

### 11.11. Dùng parent đệ quy sai trên graph vô hướng

Khi xét danh sách kề của u, cạnh u→parent[u] là cạnh quay về cha, **không phải người con mới**. Nếu quên bỏ qua, DFS lặp vô hạn hoặc tính dãy Euler sai. Bản Java đã xác minh đầu vào là cây rồi bỏ qua `v==f.parent`.

### 11.12. Tính sai số vị trí Euler

Với N đỉnh, dãy phải có **2N−1** vị trí nếu ghi vào và sau mỗi con. Nếu dài N, thiếu các lần quay về; nếu dài 2N, có thể đã ghi thêm gốc một lần không đúng quy ước và làm lệch first. Cách thử tự động tốt là kiểm tra độ dài Euler và dãy depth chênh nhau ±1 giữa mọi vị trí liên tiếp.

## 12. Tính đúng và bất biến của chương trình

Có thể phân tách chứng minh thành ba tầng.

**Tầng 1 – Duyệt Euler đúng.** DSU xác minh các cạnh tạo thành một cây; DFS từ gốc đi vào mỗi đỉnh đúng một lần qua một cạnh cha–con. Sau mỗi khi con hoàn tất, frame của cha được ghi lại. Do cây có N−1 cạnh, dãy có đúng 2N−1 vị trí, first[v] là vị trí xuất hiện đầu tiên và depth[v] đúng số cạnh từ gốc tới v.

**Tầng 2 – Quy đổi LCA thành RMQ đúng.** Theo chứng minh phần 4, trên khoảng `[min(first[u],first[v]),max(...)]`, độ sâu nhỏ nhất đúng bằng độ sâu LCA, và vị trí cực tiểu chứa đỉnh LCA.

**Tầng 3 – Cấu trúc RMQ đúng.** Sparse Table lưu index min cho mọi đoạn độ dài \(2^k\) bằng quy nạp từ hai nửa. Truy vấn lấy min hai đoạn phủ [l,r], nên trả index min của toàn đoạn. Segment Tree lưu min của hai con ở mỗi nút; quy trình truy vấn ghép chính xác các đoạn rời phủ [l,r], nên cũng trả index min toàn đoạn. Cả hai ánh xạ qua `euler[index]` thành LCA thật.

Do đó `lcaSparse(u,v)` và `lcaSegment(u,v)` đều trả **đỉnh tổ tiên chung gần nhất** của u,v trên cây đầu vào.

### Bất biến kiểm thử cụ thể

Với ví dụ N=11:

- M=21.
- `first[v]` nằm trong `[0,20]`, và `euler[first[v]]==v`.
- `tourDepth[i]==depth[euler[i]]` cho mọi i.
- `abs(tourDepth[i+1]-tourDepth[i])==1` cho mọi i liền kề.
- `LCA(u,u)==u` cho mọi u.
- `LCA(root,u)==root` cho mọi u.
- Kết quả đối xứng: `LCA(u,v)==LCA(v,u)`.
- Sparse Table và Segment Tree cho cùng kết quả với **mọi cặp** u,v.
- Kết quả khớp phép tìm LCA chậm bằng cách lần cha của mỗi đỉnh trên cây nhỏ.

Một oracle chậm có thể tìm LCA bằng cách nâng đỉnh sâu hơn lên tới khi hai đỉnh cùng độ sâu, rồi nâng đồng thời cho tới khi trùng. Mỗi truy vấn O(chiều cao cây), nhưng đủ để kiểm chứng một bộ dữ liệu nhỏ độc lập với Euler-RMQ.

## 13. Phân tích độ phức tạp tổng thể

Với N đỉnh, Q truy vấn:

**Duyệt và xây Euler:** cây có N−1 cạnh, danh sách kề lưu O(N) mục, DFS đi qua mỗi cạnh cây hai lượt. Euler dài M=2N−1=O(N). Thời gian O(N), không gian O(N).

**Tiền xử lý Sparse Table:** O(M log M)=**O(N log N)** thời gian và bộ nhớ.

**LCA bằng Sparse Table:** mỗi truy vấn dùng hai mốc first, một `log2` và hai ô bảng, rồi so sánh depth: **O(1)**.

**Tiền xử lý Segment Tree:** O(M)=**O(N)** thời gian và bộ nhớ.

**LCA bằng Segment Tree:** O(log M)=**O(log N)**.

Bảng tổng:

| Phương án | Thời gian xử lý Q truy vấn | Bộ nhớ phụ chính |
|---|---:|---:|
| Euler + quét min trực tiếp | O(N+QN) | O(N) |
| Euler + Sparse Table | **O(N log N+Q)** | **O(N log N)** |
| Euler + Segment Tree | **O(N+Q log N)** | **O(N)** |
| Euler + cả hai như demo | O(N log N+Q) nếu truy vấn sparse; O(log N) mỗi lần đối chiếu segment | O(N log N) |
| Binary lifting (đối chiếu) | O(N log N+Q log N) | O(N log N) |

Nếu có **rất ít truy vấn**, chi phí xây bảng lớn có thể không đáng. Nếu **rất nhiều truy vấn** trên một cây tĩnh, Sparse Table thường tiết kiệm thời gian truy vấn đáng kể.

Giới hạn RAM cũng quan trọng: Sparse Table chứa các chỉ số nguyên của khoảng \(M\log_2 M\), trong khi Segment Tree tuyến tính theo M. Với N rất lớn, một phương án O(N log N) có thể tốn bộ nhớ đáng kể ngay cả khi thời gian tính chấp nhận được.

## 14. Trường hợp biên và cách xử lý

| Đầu vào / câu hỏi | Kết quả đúng |
|---|---|
| Cây một đỉnh (N=1) | Euler=[root], first[root]=0, LCA(root,root)=root |
| Hai đỉnh nối một cạnh | Euler=[root,child,root], LCA(root,child)=root |
| Cây dạng đường dài | Euler dài 2N−1; LCA là đỉnh gần gốc hơn trên đường |
| Cây dạng sao | LCA hai lá khác nhau là tâm gốc |
| u=v | LCA=u |
| u=root hoặc v=root | LCA=root |
| u/v ngoài miền ID | Báo lỗi, không truy vấn RMQ ngoài mảng |
| Hai nhánh có độ sâu bằng nhau | Vẫn chọn min độ sâu trên khoảng Euler |
| Cạnh nhập trùng | Nếu gây chu trình, từ chối không coi là hai cạnh cây hợp lệ |
| Cạnh tự nối | Không phải cạnh cây hợp lệ, từ chối |
| Graph N đỉnh có N−1 cạnh nhưng chứa chu trình | Có đỉnh khác bị tách; từ chối qua DSU |
| Graph không liên thông | Không có một cây gốc chứa toàn bộ đỉnh; từ chối hoặc xử lý rừng riêng |
| Gốc đổi sau tiền xử lý | Cần tiền xử lý lại hoặc dùng công thức đổi gốc chuyên biệt |
| Cây có trọng số | LCA theo hình dạng không đổi; dùng rootSum để tính tổng trọng số |
| N=0 | Không có gốc; API minh họa từ chối |
| Số truy vấn lớn | Ưu tiên tiền xử lý Sparse Table một lần |
| Cây rất lớn, RAM hạn chế | Cân nhắc Segment Tree hoặc cấu trúc RMQ chuyên dụng |

### Nếu phải đổi gốc cho từng truy vấn

Giả sử đã tiền xử lý với gốc cố định r0, nhưng truy vấn muốn LCA theo gốc r khác. Không nên chỉ thay trường `root` trong cấu trúc đang giữ rồi dùng `first` cũ.

Trên một cây cố định có một công thức hữu ích:

\[
a=LCA_{r0}(u,v),\quad
b=LCA_{r0}(u,r),\quad
c=LCA_{r0}(v,r).
\]

**LCA theo gốc mới r là đỉnh sâu nhất trong ba đỉnh a,b,c theo độ sâu của gốc cố định r0.** Công thức cho phép trả lời LCA với gốc truy vấn thay đổi bằng ba truy vấn LCA gốc cố định; nếu dùng Sparse Table thì vẫn O(1) mỗi truy vấn (hằng số ba). Tuy nhiên phải **chứng minh và cài riêng** công thức đổi gốc; không phải việc sửa Euler tại chỗ.

## 15. Câu hỏi luyện tập

**Bài 1 — Dãy Euler.** Với cây 0 có hai con 1,2, dãy đúng cho phép quy LCA→RMQ là `[0,1,2]` hay `[0,1,0,2,0]`?

*Đáp án:* **`[0,1,0,2,0]`**. Phải ghi đỉnh cha sau khi quay về từ từng con.

**Bài 2 — Độ dài.** Một cây có N=11 đỉnh sẽ tạo bao nhiêu phần tử Euler theo quy ước bài?

*Đáp án:* **2·11−1=21**.

**Bài 3 — LCA từ đoạn Euler.** Với `first[7]=3`, `first[9]=9`, dãy độ sâu `[3,2,3,2,1,2,3]` trên đoạn tương ứng, LCA(7,9) là gì?

*Đáp án:* Độ sâu min bằng 1, vị trí min tương ứng **đỉnh 1**, nên **LCA=1**.

**Bài 4 — Hai nhánh khác phía gốc.** Trong cây ví dụ, LCA(7,10) là gì?

*Đáp án:* **0**, vì 7 thuộc cây con 1 còn 10 thuộc cây con 2.

**Bài 5 — Cùng đỉnh.** LCA(9,9) theo công thức RMQ là gì?

*Đáp án:* **9**, vì đoạn first[9] tới chính nó chỉ chứa một vị trí Euler.

**Bài 6 — Sparse Table.** Với đoạn dài 7, `k=floor(log2(7))` bằng bao nhiêu? Dùng mấy đoạn?

*Đáp án:* **k=2**, dùng **hai đoạn dài 4** phủ toàn khoảng và có thể chồng nhau.

**Bài 7 — Vì sao min chồng hợp lệ?** Nếu hai đoạn Sparse Table giao nhau tại một vài chỉ số, có làm sai RMQ min không?

*Đáp án:* **Không**. Min có tính idempotent nên một phần tử được xét hai lần cũng không làm thay đổi min. Điều này không đúng cho sum.

**Bài 8 — Trả vị trí hay giá trị?** Nếu RMQ chỉ trả `depth=1`, đã đủ để biết LCA là đỉnh nào chưa?

*Đáp án:* **Chưa**. Phải có **vị trí Euler đạt cực tiểu**, từ đó lấy `euler[index]` thành ID tổ tiên.

**Bài 9 — Khoảng cách.** Với depth[7]=3, depth[9]=3 và LCA(7,9)=1 có depth=1, khoảng cách bao nhiêu?

*Đáp án:* **3+3−2·1=4 cạnh**.

**Bài 10 — Độ sâu và trọng số.** Nếu cạnh trong cây có trọng số 100 hoặc −5, nên dùng tổng trọng số làm `tourDepth` để RMQ không?

*Đáp án:* **Không**. LCA so sánh **độ sâu theo số cạnh**, không phải tổng trọng số. Tổng trọng số đường đi lưu riêng trong rootSum.

**Bài 11 — Cây không liên thông.** Có thể gọi LCA(7,10) nếu 7 và 10 nằm ở hai cây khác nhau của rừng không?

*Đáp án:* Không có **LCA thật** trong một cây gốc chung, trừ khi đã định nghĩa siêu gốc hoặc quy ước khác. Phải kiểm tra componentId hoặc xử lý đầu vào theo đúng đặc tả.

**Bài 12 — So với Binary Lifting.** Nếu truy vấn đòi tổ tiên bậc k của một đỉnh, Euler-RMQ có trả trực tiếp bằng một RMQ min không?

*Đáp án:* **Không trực tiếp**. Binary Lifting thường thuận tiện hơn cho k-th ancestor; Euler-RMQ nhắm vào LCA của một cặp đỉnh.

**Bài 13 — Tính đúng.** Vì sao trên đoạn giữa hai first-occurrence không có đỉnh có depth nhỏ hơn depth của LCA?

*Đáp án:* Vì trước khi đi tới đỉnh thứ hai, DFS chưa thể rời khỏi toàn bộ cây con của LCA rồi quay lại khám phá đỉnh đó trong cây con. Đoạn buộc có LCA nhưng không buộc đi lên trên LCA.

**Bài 14 — Bộ nhớ.** Với cùng cây tĩnh, Sparse Table và Segment Tree khác nhau ra sao về chi phí bộ nhớ RMQ?

*Đáp án:* Sparse Table **O(N log N)**, Segment Tree **O(N)**.

**Bài 15 — Đổi gốc.** Nếu thay gốc sau tiền xử lý, có thể giữ nguyên Euler và chỉ đổi `root` không?

*Đáp án:* **Không.** Quan hệ tổ tiên thay đổi; phải tính lại hoặc áp dụng công thức ba LCA theo gốc cố định được chứng minh.

**Bài 16 — Kiểm thử chéo.** Đâu là ba cách độc lập để kiểm tra tính đúng của LCA-RMQ trên cây nhỏ?

*Đáp án:* Kiểm tra dãy Euler và first, đối chiếu **Sparse Table với Segment Tree**, rồi so với **oracle nâng cha chậm** cho mọi cặp đỉnh.

**Tổng kết:** LCA trên cây có gốc được đưa về RMQ bằng cách duyệt DFS tạo **dãy Euler dài 2N−1**, ghi đỉnh khi đi vào và **khi quay về từ mỗi con**. Lưu `first[u]` và `tourDepth`; `LCA(u,v)` là đỉnh tại vị trí có **độ sâu nhỏ nhất** trên khoảng giữa hai first-occurrence. **Sparse Table** cho O(N log N) tiền xử lý và **O(1) LCA**, còn **Segment Tree** cho O(N) xây dựng và **O(log N) LCA**. Đừng nhầm dãy Euler đầy đủ với DFS preorder, đừng dùng min theo ID, và đừng áp dụng trực tiếp lên đồ thị có chu trình hoặc rừng chưa xử lý thành phần.