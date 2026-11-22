# Độ sâu đệ quy, ngăn xếp và cách chuyển sang lặp

Trong nhiều bài toán thuật toán, đệ quy (*recursion*) đem lại mô tả tự nhiên: “giải bài toán con”, “duyệt các đỉnh kề”, “chia đoạn rồi ghép kết quả”. Nhưng mỗi lần gọi hàm đệ quy lại cần giữ **trạng thái của lời gọi đang dở**: tham số, biến cục bộ, vị trí tiếp tục sau lời gọi con và thông tin điều khiển. Các trạng thái ấy thường nằm trong **call stack** (ngăn xếp lời gọi) của thread.

Khi đường đi đệ quy quá sâu, chương trình Java có thể ném `StackOverflowError`. Độ sâu an toàn không có một con số chung cho mọi JVM và mọi hàm: nó còn phụ thuộc kích thước stack của thread, tùy chọn runtime, kích thước frame, tối ưu hóa của JIT, native calls và môi trường chạy.

Một cách xử lý bền vững là **chuyển đệ quy sang lặp** (*recursion-to-iteration transformation*) bằng cách tự quản lý trạng thái trên ngăn xếp tường minh (*explicit stack*). Tuy nhiên, chuyển đổi chính xác **không phải** lúc nào cũng chỉ là thay lời gọi bằng `while`: ta phải giữ thứ tự thực thi trước/sau lời gọi con, biến cục bộ và điều kiện kết thúc.

Bài học thuộc nhóm **Cài đặt và kiểm thử** và tập trung vào:

1. Phân biệt số lời gọi, **độ sâu đệ quy cực đại**, kích thước call stack và tổng độ phức tạp.
2. Hiểu `StackOverflowError`, rủi ro của đệ quy sâu, và vì sao Java **không bảo đảm** tối ưu hóa lời gọi đuôi.
3. Chuyển **đệ quy đuôi** sang vòng lặp lưu một trạng thái.
4. Chuyển **DFS đệ quy** sang `ArrayDeque<Frame>` với đỉnh và **chỉ số cạnh đang xét**, giữ **đúng cả preorder và postorder**.
5. Xử lý graph có cạnh trùng, self-loop, chu trình và đỉnh không tới được.
6. Chứng minh tính tương đương bằng bất biến mô phỏng call stack; phân tích O(n+m), O(depth), chi phí RAM và khả năng hết heap.
7. Cung cấp một chương trình **Java 17+ độc lập** với stdout xác định, kiểm trên toàn bộ 512 đồ thị có hướng nhỏ, 400 đồ thị có hướng ngẫu nhiên và một đường dài **50.000 đỉnh chỉ duyệt bằng bản lặp**.

Trọng tâm không phải “loại bỏ đệ quy bằng mọi giá”, mà là **chọn hình thức cài đặt đúng với giới hạn dữ liệu, thứ tự duyệt và yêu cầu an toàn**.

## 1. Đệ quy thực sự lưu lại điều gì?

Xét hàm cộng các số nguyên từ 1 đến n:

~~~java
static long sumRecursive(int n) {
    if (n == 0) {
        return 0L;
    }
    return n + sumRecursive(n - 1);
}
~~~

Nếu n=4, chuỗi lời gọi là:

~~~text
sumRecursive(4)
    sumRecursive(3)
        sumRecursive(2)
            sumRecursive(1)
                sumRecursive(0)
~~~

Đến lời gọi n=0, hàm trả 0; các lời gọi trước đó lần lượt **quay lui** (*unwind*) để cộng 1, 2, 3, 4.

Khi `sumRecursive(4)` đang đợi `sumRecursive(3)`, runtime phải ghi nhớ rằng kết quả trả về của lời gọi con sẽ được **cộng với 4**. Nếu có nhiều biến cục bộ hoặc vòng lặp, nó còn cần trạng thái tương ứng.

Một **stack frame** (khung ngăn xếp) của lời gọi thường gắn với:

- Các tham số của hàm.
- Các biến cục bộ và giá trị trung gian cần giữ.
- Thông tin điều khiển để tiếp tục thực thi sau lời gọi con.
- Các chi tiết runtime/JIT khác tùy JVM.

Đây là mô hình khái niệm, không phải khẳng định một layout byte-by-byte cố định cho mọi JVM.

### Độ sâu không phải tổng số lần gọi

Với một cây nhị phân đầy đủ có nhiều triệu nút, DFS đệ quy có thể gọi hàm **hàng triệu lần**, nhưng nếu chiều cao cây chỉ khoảng 20 thì số frame đang hoạt động đồng thời trên một đường đi chỉ khoảng 21.

Ngược lại, một danh sách liên kết hay đồ thị hình đường có n đỉnh có thể tạo **một nhánh đệ quy dài n**, dù mỗi lời gọi chỉ thực hiện O(1) công việc.

Do đó:

\[
\boxed{\text{Tổng lời gọi}\ne\text{độ sâu lời gọi cực đại}.}
\]

Số lời gọi ảnh hưởng đến **tổng thời gian**; số frame đồng thời ảnh hưởng đến **bộ nhớ call stack** và nguy cơ tràn ngăn xếp.

## 2. Định nghĩa độ sâu đệ quy

**Độ sâu đệ quy tại một thời điểm** là số lời gọi của chuỗi đệ quy đang hoạt động trên thread đó. Có thể quy ước lời gọi gốc có độ sâu 1; lời gọi con trực tiếp có độ sâu 2.

Gọi \(D\) là độ sâu cực đại. Nếu mỗi frame sử dụng xấp xỉ c byte, bộ nhớ call stack bổ sung theo mô hình đơn giản là:

\[
\boxed{O(D)\text{ frame},\quad O(Dc)\text{ byte}.}
\]

Trong thực tế c **không phải hằng số phổ quát** giữa các phương thức và môi trường; stack còn có giới hạn và overhead khác.

Ví dụ:

| Thuật toán/hình dạng dữ liệu | Độ sâu thường gặp | Lưu ý |
|---|---:|---|
| Binary search đệ quy | O(log n) | Mỗi lần giảm nửa miền |
| Merge sort đệ quy | O(log n) | Nhiều lời gọi tổng cộng, ít frame đồng thời |
| DFS trên cây cân bằng | O(height)≈O(log n) | Nếu cân bằng thực sự |
| DFS trên cây suy biến | O(n) | Mỗi nút chỉ có một con |
| DFS trên đồ thị hình đường | O(n) | Một đường dài liên tiếp |
| Quicksort chọn pivot kém | O(n) trường hợp xấu | Phân hoạch lệch liên tục |
| Fibonacci đệ quy ngây thơ | O(n) | Tổng lời gọi lại có thể tăng theo cấp số mũ |
| Backtracking | O(độ dài nhánh lựa chọn) | Không phải số nghiệm hoặc số nhánh |

### Độ sâu của đồ thị không nhất thiết bằng đường đi ngắn nhất

Với DFS, độ sâu có thể gần bằng số đỉnh reachable R, kể cả khi khoảng cách ngắn nhất từ nguồn tới một đỉnh khá nhỏ. DFS đi theo thứ tự cạnh, không theo tầng khoảng cách như BFS.

Trong một đồ thị có chu trình, nếu không có `visited`, đệ quy có thể đi lại vô hạn. Độ sâu khi đó không còn bị chặn bởi số đỉnh theo nghĩa thuật toán đã dự định.

## 3. StackOverflowError trong Java

Khi không còn đủ không gian stack cho một lời gọi mới, Java có thể ném:

~~~text
java.lang.StackOverflowError
~~~

Đây là một `Error`, không phải một `Exception` thông thường. Trong hệ thống vận hành, nó thường phản ánh lỗi vòng gọi vô hạn hoặc độ sâu đầu vào vượt khả năng của thiết kế.

Các nguồn gốc phổ biến:

- Không có điều kiện dừng (*base case*).
- Điều kiện dừng có nhưng tham số không tiến gần nó.
- Hai hoặc nhiều hàm gọi vòng tròn (*mutual recursion*) mà không tiến triển.
- Dữ liệu tạo đường rất sâu: linked list, cây suy biến, DFS hình đường.
- Quicksort phân hoạch lệch và vẫn đệ quy trên phần lớn.
- Lời gọi đệ quy nằm trong đường xử lý một dữ liệu độc hại hoặc bất thường.

### Không có “ngưỡng an toàn 10.000 lần” chung

Một method chỉ có vài biến cục bộ có thể chịu độ sâu khác method có nhiều trạng thái. Tùy chọn JVM như `-Xss` có thể ảnh hưởng kích thước stack thread trên nhiều runtime, nhưng không nên coi việc tăng `-Xss` là sửa lỗi thuật toán và cũng không có ngưỡng stack chung cho mọi hệ.

Nguy hiểm nhất là viết:

~~~java
try {
    recursiveDfs(hugeGraph, source);
} catch (StackOverflowError e) {
    // Continue using partially modified visited, parent, output...
}
~~~

Một phép duyệt bị ngắt giữa chừng có thể đã sửa **một phần** trạng thái; bắt lỗi không biến nó thành kết quả đúng hoặc giúp các frame chưa hoàn tất tự tiếp tục.

**Cách thực tế:** nếu độ sâu tiềm ẩn lớn và không có bảo đảm về stack, ưu tiên thuật toán lặp thích hợp; nếu cần cấu hình stack thì vẫn phải đo và đặt giới hạn tài nguyên.

## 4. Đệ quy đuôi và cách chuyển đơn giản nhất

Một lời gọi là **tail call** khi kết quả của lời gọi con được trả trực tiếp mà không phải làm thêm thao tác nào sau đó.

Ví dụ với accumulator:

~~~java
static long sumTail(int n, long acc) {
    if (n == 0) {
        return acc;
    }
    return sumTail(n - 1, acc + n);
}
~~~

Lời gọi đệ quy ở đây là hành động cuối; sau khi lời gọi con trả kết quả, lời gọi hiện tại không còn việc nào khác.

Có thể chuyển trực tiếp thành:

~~~java
static long sumIterative(int n) {
    if (n < 0) {
        throw new IllegalArgumentException("n must be >= 0");
    }
    long acc = 0L;
    long remaining = n;
    while (remaining > 0L) {
        acc = Math.addExact(acc, remaining);
        remaining--;
    }
    return acc;
}
~~~

Bất biến vòng lặp:

\[
acc+\sum_{i=1}^{remaining}i
=\sum_{i=1}^{n}i.
\]

Ban đầu acc=0 và remaining=n. Mỗi bước chuyển `remaining` sang `remaining-1`, đồng thời cộng số vừa bỏ vào acc. Kết thúc remaining=0, `acc` là tổng cần tìm.

### Java có tự tối ưu hóa tail recursion không?

**Không được dựa vào một bảo đảm tối ưu hóa tail calls của ngôn ngữ Java.** Tùy JVM/JIT có thể có các tối ưu khác nhau, nhưng một method Java đệ quy đuôi vẫn có thể tiêu hao call stack theo độ sâu.

Nếu mục tiêu là tránh stack sâu một cách đáng tin cậy, **chuyển thành `while`** như trên thay vì chỉ đổi cú pháp thành tail-recursive.

### Đệ quy không đuôi khác gì?

~~~java
return n + sumRecursive(n - 1);
~~~

Sau khi `sumRecursive(n-1)` trả về vẫn còn phép **cộng n** chờ thực hiện, nên đó **không phải** tail call. Để chuyển sang loop, ta đổi bài toán thành duy trì accumulator, hoặc mô phỏng những phép cộng đang chờ trong một ngăn xếp tường minh.

## 5. Tư duy chung: mô phỏng call stack bằng một stack tường minh

Đối với đệ quy không đơn giản là tail call, hãy xác định một **frame logic** bao gồm:

1. **Đầu vào của lời gọi:** đỉnh/đoạn/trạng thái đang giải.
2. **Con trỏ tiến trình:** đã xử lý lời gọi con nào, đang chờ lời gọi con nào?
3. **Biến cục bộ cần giữ** sau khi lời gọi con hoàn tất.
4. **Trạng thái trả về hoặc dữ liệu tích lũy** để ghép kết quả.
5. **Dấu mốc trước/sau:** thao tác xảy ra khi mới vào hàm, giữa các lời gọi con, hoặc trước khi trả về.

Sau đó thay đổi một trong ba trạng thái:

~~~text
ENTER(frame):
    thực hiện hành động trước lời gọi con
    đặt con trỏ tiến trình

SUSPEND(frame):
    giữ frame hiện tại trên stack
    push frame của lời gọi con

RETURN(frame):
    thực hiện hành động sau lời gọi con
    pop frame và quay lại frame cha
~~~

Các frame trong `ArrayDeque<Frame>` thực hiện đúng vai trò của các lời gọi đang hoạt động, nhưng chúng là **đối tượng trên heap** do chương trình quản lý, không tiêu tốn một frame call stack Java cho mỗi đỉnh.

### Nguyên tắc chuyển đổi

**Đừng chỉ lưu tên lời gọi — phải lưu cả “đang làm dở đến đâu”.** Với vòng `for` trong DFS, đó là chỉ số hàng xóm tiếp theo. Với một thuật toán chia để trị, frame có thể cần pha “chưa gọi con trái / đã có kết quả con trái / đã gọi con phải / đang ghép”.

Không có một hàm `push/pop` duy nhất phù hợp mọi thuật toán mà không phân tích trạng thái.

## 6. DFS đệ quy trên đồ thị

Đồ thị có danh sách kề `graph[u]`. Một DFS cơ bản là:

~~~java
static void dfsRecursive(int u, int[][] graph, boolean[] seen,
                         List<Integer> preorder,
                         List<Integer> postorder) {
    seen[u] = true;
    preorder.add(u);

    for (int v : graph[u]) {
        if (!seen[v]) {
            dfsRecursive(v, graph, seen, preorder, postorder);
        }
    }

    postorder.add(u);
}
~~~

Có hai thời điểm quan trọng:

- **Preorder:** ghi u **ngay khi bước vào** hàm.
- **Postorder:** ghi u **khi đã xử lý xong mọi cạnh đi ra và mọi lời gọi con**.

Dùng `visited` từ lúc **vào** đỉnh ngăn DFS quay vòng trên self-loop/chu trình.

### Ví dụ đồ thị có hướng

~~~text
0 -> [1,2,1]
1 -> [3,4]
2 -> [2,4,5]
3 -> [5]
4 -> [6,4]
5 -> [6]
6 -> []
7 -> [7]
~~~

Nguồn 0 không thể đi tới đỉnh 7.

Theo **thứ tự adjacency được liệt kê**, DFS đệ quy cho:

~~~text
Preorder:  [0, 1, 3, 5, 6, 4, 2]
Postorder: [6, 5, 3, 4, 1, 2, 0]
~~~

Đường gọi sâu nhất xuất hiện khi đi:

~~~text
0 -> 1 -> 3 -> 5 -> 6
~~~

nên **số frame đồng thời cực đại bằng 5** nếu tính lời gọi gốc độ sâu 1.

Đỉnh 7 không xuất hiện trong kết quả vì nó unreachable từ 0. Self-loop ở 2, 4 và 7 không khiến chương trình lặp vô hạn; cạnh 0→1 được liệt kê hai lần nhưng chỉ có một lần khám phá 1.

## 7. Vì sao một stack chứa mỗi đỉnh thường chưa đủ để tái tạo DFS đệ quy?

Một ý tưởng phổ biến:

~~~text
stack.push(source)
while stack not empty:
    u = stack.pop()
    if visited[u]:
        continue
    visited[u] = true
    for neighbors in reverse order:
        stack.push(neighbor)
~~~

Cách này có thể duyệt được **tập đỉnh reachable** và, với điều kiện phù hợp, tạo một thứ tự tiền tự hữu dụng. Nhưng nó **không tự lưu thời điểm quay lui sau từng lời gọi con**, nên không tái tạo trực tiếp **postorder của DFS đệ quy**.

Nếu lại **đánh dấu visited ngay khi push tất cả hàng xóm**, preorder cũng có thể lệch so với DFS đệ quy.

Ví dụ:

~~~text
0 -> [1,2]
1 -> [2,3]
2 -> []
3 -> []
~~~

DFS đệ quy:

~~~text
Preorder = [0,1,2,3]
~~~

Nhưng một cài đặt stack đơn giản đánh dấu cả 1 và 2 ngay khi push từ 0 sẽ bỏ qua cạnh 1→2 (vì 2 đã được đánh dấu), rồi có thể xử lý đỉnh 3 trước 2:

~~~text
Preorder = [0,1,3,2]
~~~

Tập đỉnh visited vẫn đúng, nhưng **thứ tự và cây DFS** không khớp.

Do đó, nếu bài toán chỉ cần reachability, stack đỉnh có thể đủ. Nếu cần tái lập **semantics của DFS đệ quy**, đặc biệt postorder, hãy lưu thêm **con trỏ cạnh đang xét** trong từng frame.

## 8. Frame cho DFS: đỉnh và chỉ số hàng xóm

Đối với DFS đệ quy ở mục trước, mỗi lời gọi đang hoạt động tương ứng:

~~~text
Frame {
    vertex: đỉnh hiện tại
    nextNeighborIndex: cạnh kề kế tiếp chưa xét
}
~~~

Khi **mới vào** một đỉnh u:

1. `seen[u] = true`.
2. Ghi u vào preorder.
3. Push `Frame(u,0)`.

Khi đọc frame đỉnh trên cùng của stack:

- Nếu `nextNeighborIndex` vẫn nhỏ hơn số hàng xóm của u, lấy hàng xóm v tại chỉ số đó và **tăng chỉ số ngay**.
- Nếu v chưa seen, đánh dấu, ghi preorder và push frame mới của v. Frame u vẫn ở dưới stack, **đúng vị trí chờ sau lời gọi con**.
- Nếu v đã seen, bỏ qua cạnh và tiếp tục xử lý frame u.
- Nếu u không còn hàng xóm để xét, ghi u vào **postorder** rồi pop frame.

Mã giả:

~~~text
seen[source] = true
preorder.append(source)
stack.push(Frame(source, next=0))

while stack not empty:
    f = stack.peek()

    if f.next == degree(f.vertex):
        postorder.append(f.vertex)
        stack.pop()
        continue

    v = adjacency[f.vertex][f.next]
    f.next++                 // ghi lại vị trí tiếp tục

    if not seen[v]:
        seen[v] = true
        preorder.append(v)
        stack.push(Frame(v, next=0))
~~~

Đây là mô phỏng **một-một trạng thái lời gọi** chứ không chỉ mô phỏng danh sách “đỉnh cần thăm”.

### Tại sao next++ phải làm trước khi push con?

Frame cha sẽ bị tạm ngừng trong khi con được xử lý. Khi quay lại, nó phải bắt đầu tại **hàng xóm kế tiếp**. Nếu quên tăng chỉ số trước khi push, cha có thể xét lại cùng cạnh vô hạn hoặc lặp công việc.

### Tại sao đánh dấu visited ngay khi push frame mới?

Đó là thời điểm tương đương **vào lời gọi dfsRecursive(v)**. Khi một cạnh khác dẫn tới v trong lúc frame của v chưa hoàn tất, ta đã biết v đang được xử lý và phải **bỏ qua**, giống bản đệ quy.

### Tại sao postorder được thêm lúc pop?

Trong bản đệ quy, `postorder.add(u)` nằm **sau vòng for tất cả hàng xóm**. Ở bản lặp, điều kiện `nextNeighborIndex==degree(u)` chính là thời điểm lời gọi đệ quy sẽ quay về caller.

## 9. Chứng minh DFS lặp với frame tương đương DFS đệ quy

Xét bản DFS đệ quy chạy theo thứ tự từng phần tử của adjacency array. Giả sử đồ thị bất biến trong lúc duyệt và cả hai bản dùng chung quy ước **đánh dấu visited khi vào đỉnh**.

Ta xây bất biến mô phỏng:

> Các frame trong explicit stack, từ đáy đến đỉnh, tương ứng đúng với chuỗi lời gọi DFS đang hoạt động. Với mỗi frame, `nextNeighborIndex` là vị trí mà vòng lặp hàng xóm của lời gọi tương ứng sẽ tiếp tục khi frame trên cùng hoàn tất.

**Cơ sở:** sau khởi tạo, explicit stack chỉ có `Frame(source,0)`, giống lời gọi dfs(source) vừa vào hàm. Cả hai đặt `seen[source]=true` và ghi cùng preorder.

**Bước xử lý một cạnh:** cả hai xét cùng `graph[u][nextNeighborIndex]`, rồi chuyển con trỏ sang hàng xóm kế. Nếu v đã visited, cùng bỏ qua. Nếu v chưa visited, cùng đánh dấu v, ghi preorder và bắt đầu DFS(v). Bản đệ quy tạo call frame, bản lặp push explicit Frame(v,0).

**Bước kết thúc lời gọi:** khi con trỏ đã tới cuối adjacency[u], bản đệ quy thực hiện `postorder.add(u)` rồi return, bản lặp thực hiện `postorder.add(u)` rồi pop. Cả hai quay lại cùng caller/vị trí tiếp tục.

Theo quy nạp trên từng bước xử lý frame, ta có:

\[
\boxed{pre_{\text{iterative}}=pre_{\text{recursive}}}
\]

\[
\boxed{post_{\text{iterative}}=post_{\text{recursive}}}
\]

và số frame đồng thời cực đại ở explicit stack bằng độ sâu lời gọi DFS đệ quy theo quy ước cùng nguồn độ sâu 1.

Điều này **khác** khẳng định mọi DFS dùng stack đều có cùng thứ tự. Chỉ cấu trúc frame và quy tắc thực thi **mô phỏng chính xác vòng for** mới cho bảo đảm đó.

## 10. Thời gian và bộ nhớ: call stack sang heap

Với n đỉnh, m cạnh trong danh sách kề, và R đỉnh reachable từ nguồn:

- Mỗi đỉnh reachable được vào đúng một lần.
- Mỗi cạnh đi ra khỏi đỉnh reachable được xét đúng một lần.
- Mỗi frame chỉ được push và pop một lần.

Do vậy, **riêng phần DFS** có thời gian:

\[
\boxed{O(R+E_R)\subseteq O(n+m),}
\]

trong đó \(E_R\) là số cạnh đi ra khỏi tập reachable.

Bản Java còn **kiểm tính hợp lệ của toàn bộ graph** trước mỗi lượt duyệt, tốn O(n+m). Tổng thời gian vẫn O(n+m).

### Bộ nhớ đệ quy

- `seen[]`: O(n).
- Preorder/postorder: O(R) phần tử mỗi danh sách.
- **Call stack DFS:** O(D) frame, với D≤R.

Tổng bộ nhớ phụ theo bậc là O(n+R+D)=O(n), không kể graph, nhưng phần O(D) này nằm trong **stack thread hữu hạn**.

### Bộ nhớ lặp tường minh

- `seen[]`: O(n).
- Preorder/postorder: O(R).
- `ArrayDeque<Frame>`: tối đa D frame, **trên heap**.
- Call stack Java của vòng lặp: O(1) độ sâu đối với thuật toán DFS lặp.

Tổng cũng O(n), nhưng cấu trúc sử dụng **vùng nhớ khác** và không đòi một lời gọi Java lồng nhau cho mỗi cạnh trên đường sâu.

### Có thể hết bộ nhớ heap không?

**Có.** Explicit stack không loại bỏ chi phí lưu trạng thái; nó chỉ đưa trạng thái từ call stack của thread sang heap do ứng dụng quản lý. Với dữ liệu đủ lớn, `ArrayDeque`, các Frame object, visited, output và graph vẫn có thể gây `OutOfMemoryError`.

Vậy “iterative DFS không stack overflow” cần hiểu là **không tạo call stack sâu theo số đỉnh**, chứ không phải “không bao giờ hết RAM”.

## 11. Ví dụ đường dài 50.000 đỉnh

Xét đồ thị có 50.000 đỉnh:

~~~text
0 -> 1 -> 2 -> 3 -> ... -> 49999
~~~

Có n=50.000 và m=49.999 cạnh. Đi từ nguồn 0, DFS có một đường sâu dài 50.000 đỉnh.

Nếu dùng DFS đệ quy, số lời gọi đồng thời cực đại có thể bằng 50.000; tùy stack thread, chương trình **có thể** gặp StackOverflowError. Không nên viết bài test gây tràn stack cố ý rồi coi đó là tính năng bình thường.

Bản Java minh họa:

- Tạo graph dạng `int[][]` cho 50.000 đỉnh.
- **Chỉ chạy bản iterative** trên graph này.
- Xác nhận preorder chứa đủ 50.000 đỉnh.
- Xác nhận phần tử cuối preorder là 49.999.
- Xác nhận số frame cực đại của explicit stack là 50.000.
- Không gọi bản recursive trên graph sâu ấy.

Đây là một minh chứng rõ ràng rằng **độ sâu logic của thuật toán** vẫn 50.000, nhưng call stack Java không phải giữ 50.000 lời gọi DFS đồng thời.

## 12. Từ DFS sang những thuật toán đệ quy khác

Không phải mọi bài đệ quy đều là DFS. Nhưng cách phân tích frame áp dụng rộng rãi.

### A. Duyệt cây nhị phân

Một hàm:

~~~text
visit(node):
    preorder(node)
    visit(node.left)
    visit(node.right)
    postorder(node)
~~~

có thể chuyển thành frame:

~~~text
(node, phase)
phase=0: vừa vào, xử lý preorder, chuẩn bị left
phase=1: left xong, chuẩn bị right
phase=2: right xong, xử lý postorder rồi pop
~~~

`phase` đóng vai trò **program counter** của frame. Nếu chỉ muốn inorder, cần đặt thao tác ghi node **giữa hai pha left và right**.

### B. Chia để trị và ghép kết quả

Với merge sort, frame có thể chứa:

~~~text
(l, mid, r, phase)
~~~

để mô tả đang chuẩn bị nửa trái, nửa phải, hay ghép. Tuy vậy, thay đệ quy bằng một merge sort **bottom-up** thường đơn giản hơn:

~~~text
width = 1
while width < n:
    merge adjacent runs of length width
    width *= 2
~~~

Cách bottom-up thay đổi **thứ tự giải các bài toán con**, nhưng vẫn đúng nếu giữ bất biến các run đang được sắp xếp và hợp nhất hợp lệ.

### C. Quay lui (*backtracking*)

Trong quay lui:

~~~text
choose candidate
recurse
undo candidate
~~~

bản iterative phải ghi nhớ **phần việc undo** hoặc state khôi phục trong frame. Chỉ push các lựa chọn mà không hoàn tác có thể làm các nhánh ảnh hưởng lẫn nhau.

### D. Quy hoạch động có ghi nhớ

Một hàm memoized recursion có thể được chuyển sang **bottom-up DP** nếu có thứ tự tính thỏa quan hệ phụ thuộc; không nhất thiết cần explicit stack. Nhưng phải xác nhận mọi trạng thái cần thiết đã được tính trước khi sử dụng.

### E. Thuật toán với giá trị trả về từ nhiều con

Nếu lời gọi cha cần kết hợp hai kết quả `leftResult` và `rightResult`, frame phải lưu **kết quả tạm** hoặc có chỗ để nhận giá trị trả về của lời gọi con. DFS chỉ xuất preorder/postorder nên không phải quản lý kiểu kết quả này.

**Kết luận:** có thể chuyển bằng **mô phỏng call stack**, **viết lại bottom-up**, hoặc **tối ưu đệ quy đuôi thành vòng lặp**. Chọn cách đơn giản nhất giữ đúng bất biến và yêu cầu output.

## 13. Khi nào đệ quy vẫn là lựa chọn tốt?

Không phải thuật toán nào cũng cần đổi thành iterative.

Đệ quy thường phù hợp khi:

- Độ sâu được bảo đảm O(log n), ví dụ binary search, merge sort, chia để trị cân bằng.
- Dữ liệu có chiều cao cây nhỏ hoặc giới hạn sâu đáng tin.
- Lời giải đệ quy ngắn, rõ ràng và dễ chứng minh.
- Chi phí call stack phù hợp môi trường chạy thực tế.
- Bài toán thực sự gắn với thứ tự vào/ra mà đệ quy tự nhiên biểu đạt.

Iterative đáng cân nhắc khi:

- Độ sâu có thể O(n) và n rất lớn.
- Input có thể cố tình tạo chuỗi dài (malformed/deeply nested).
- Cần kiểm soát vùng nhớ và lỗi tài nguyên rõ ràng.
- Muốn dừng/tiếp tục, checkpoint hoặc bước thực thi từng phần.
- Có thể dùng topological order/bottom-up DP đơn giản.
- Cần tránh phụ thuộc vào kích thước stack mặc định của JVM/thread.

**Không nên đổi đệ quy sang lặp chỉ vì cảm giác “vòng lặp luôn nhanh hơn”.** Việc chuyển có thể tăng độ phức tạp mã, overhead Frame object hoặc nguy cơ lỗi thứ tự. Hãy đo và kiểm chứng theo trường hợp sử dụng.

## 14. Java 17+: chương trình đầy đủ so sánh DFS đệ quy và DFS lặp

Lưu nguyên chương trình thành **RecursionDepthAndIterativeDfsDemo.java**. Nó bao gồm:

- `sumRecursive` và `sumIterative` để minh họa bài toán đơn giản; chỉ gọi đệ quy với n nhỏ.
- `recursiveDfs` thực hiện DFS đệ quy, ghi preorder, postorder và độ sâu cực đại; **chỉ chạy trên graph nhỏ**.
- `iterativeDfs` dùng `ArrayDeque<Frame>`, `Frame(vertex,nextNeighborIndex)`, ghi **hai thứ tự giống hệt DFS đệ quy**.
- `validateGraph` kiểm n≥1, nguồn trong phạm vi, không có adjacency null/neighbor sai.
- `verifySameAndReachability` so kết quả recursive/iterative và kiểm tập visited bằng **BFS queue độc lập**.
- `exhaustiveTinyGraphs` xét 512 đồ thị có hướng trên ba đỉnh, với cả ba nguồn.
- `randomGraphs` xét 400 đồ thị có hướng ngẫu nhiên từ seed 540, cho phép cạnh trùng, self-loop, chu trình và đỉnh unreachable.
- `longPathTest` tạo đường 50.000 đỉnh và **chỉ chạy iterative DFS**.

Mã dùng **Java 17+ standard library**, không phụ thuộc thư viện ngoài.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.List;
import java.util.Random;

public class RecursionDepthAndIterativeDfsDemo {

    record Traversal(
        List<Integer> preorder,
        List<Integer> postorder,
        int maximumDepth
    ) {}

    // Simulates one suspended recursive DFS call.
    static final class Frame {
        final int vertex;
        int nextNeighborIndex;

        Frame(int vertex) {
            this.vertex = vertex;
            this.nextNeighborIndex = 0;
        }
    }

    static void validateGraph(int[][] graph, int source) {
        if (graph == null || graph.length == 0) {
            throw new IllegalArgumentException(
                "graph must have at least one vertex"
            );
        }
        if (source < 0 || source >= graph.length) {
            throw new IllegalArgumentException(
                "source index out of range"
            );
        }
        for (int u = 0; u < graph.length; u++) {
            if (graph[u] == null) {
                throw new IllegalArgumentException(
                    "null adjacency row"
                );
            }
            for (int v : graph[u]) {
                if (v < 0 || v >= graph.length) {
                    throw new IllegalArgumentException(
                        "neighbor index out of range"
                    );
                }
            }
        }
    }

    // Non-tail-recursive example. Call only with SMALL n.
    static long sumRecursive(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be >= 0");
        }
        if (n == 0) {
            return 0L;
        }
        return Math.addExact((long) n, sumRecursive(n - 1));
    }

    // Same result, no nested recursive calls.
    static long sumIterative(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be >= 0");
        }
        long acc = 0L;
        long remaining = n;
        while (remaining > 0L) {
            acc = Math.addExact(acc, remaining);
            remaining--;
        }
        return acc;
    }

    // Recursive DFS, deliberately reserved for SMALL graphs.
    private static void visitRecursive(
        int[][] graph,
        int u,
        boolean[] seen,
        List<Integer> preorder,
        List<Integer> postorder,
        int depth,
        int[] maximumDepth
    ) {
        seen[u] = true;
        preorder.add(u);
        maximumDepth[0] = Math.max(maximumDepth[0], depth);

        for (int v : graph[u]) {
            if (!seen[v]) {
                visitRecursive(
                    graph, v, seen, preorder, postorder,
                    depth + 1, maximumDepth
                );
            }
        }

        postorder.add(u);
    }

    static Traversal recursiveDfs(int[][] graph, int source) {
        validateGraph(graph, source);
        boolean[] seen = new boolean[graph.length];
        List<Integer> preorder = new ArrayList<>();
        List<Integer> postorder = new ArrayList<>();
        int[] maximumDepth = {0};

        visitRecursive(
            graph, source, seen, preorder, postorder,
            1, maximumDepth
        );
        return new Traversal(
            List.copyOf(preorder),
            List.copyOf(postorder),
            maximumDepth[0]
        );
    }

    // Explicit heap-allocated frames preserve recursive semantics.
    static Traversal iterativeDfs(int[][] graph, int source) {
        validateGraph(graph, source);

        boolean[] seen = new boolean[graph.length];
        List<Integer> preorder = new ArrayList<>();
        List<Integer> postorder = new ArrayList<>();

        Deque<Frame> stack = new ArrayDeque<>();
        seen[source] = true;
        preorder.add(source);
        stack.push(new Frame(source));
        int maximumFrames = 1;

        while (!stack.isEmpty()) {
            Frame top = stack.peek();
            int[] neighbors = graph[top.vertex];

            if (top.nextNeighborIndex == neighbors.length) {
                // Equivalent to returning from dfs(top.vertex).
                postorder.add(top.vertex);
                stack.pop();
                continue;
            }

            // Advance the parent's suspended for-loop.
            int v = neighbors[top.nextNeighborIndex];
            top.nextNeighborIndex++;

            if (!seen[v]) {
                // Equivalent to entering dfs(v).
                seen[v] = true;
                preorder.add(v);
                stack.push(new Frame(v));
                maximumFrames = Math.max(
                    maximumFrames, stack.size()
                );
            }
        }

        return new Traversal(
            List.copyOf(preorder),
            List.copyOf(postorder),
            maximumFrames
        );
    }

    // Independent reachability oracle using a FIFO queue.
    static boolean[] reachableWithBfs(
        int[][] graph, int source
    ) {
        validateGraph(graph, source);
        boolean[] reached = new boolean[graph.length];
        int[] queue = new int[graph.length];
        int head = 0;
        int tail = 0;

        reached[source] = true;
        queue[tail++] = source;

        while (head < tail) {
            int u = queue[head++];
            for (int v : graph[u]) {
                if (!reached[v]) {
                    reached[v] = true;
                    queue[tail++] = v;
                }
            }
        }
        return reached;
    }

    // Verifies both orders, maximum stack depth and
    // all visited vertices against a DIFFERENT algorithm.
    static void verifySameAndReachability(
        int[][] graph, int source
    ) {
        Traversal recursive = recursiveDfs(graph, source);
        Traversal iterative = iterativeDfs(graph, source);

        if (!recursive.preorder().equals(iterative.preorder())
                || !recursive.postorder().equals(
                    iterative.postorder()
                )
                || recursive.maximumDepth()
                    != iterative.maximumDepth()) {
            throw new AssertionError(
                "recursive and iterative DFS differ"
            );
        }

        boolean[] reached = reachableWithBfs(graph, source);
        boolean[] inPre = new boolean[graph.length];
        boolean[] inPost = new boolean[graph.length];

        for (int v : iterative.preorder()) {
            if (inPre[v]) {
                throw new AssertionError(
                    "vertex duplicated in preorder"
                );
            }
            inPre[v] = true;
        }
        for (int v : iterative.postorder()) {
            if (inPost[v]) {
                throw new AssertionError(
                    "vertex duplicated in postorder"
                );
            }
            inPost[v] = true;
        }

        if (!Arrays.equals(reached, inPre)
                || !Arrays.equals(reached, inPost)) {
            throw new AssertionError(
                "DFS visited set differs from BFS reachability"
            );
        }
    }

    // All simple directed 3-vertex graphs incl. self-loops.
    static void exhaustiveTinyGraphs() {
        int checked = 0;

        for (int mask = 0; mask < (1 << 9); mask++) {
            int[][] graph = new int[3][];

            for (int u = 0; u < 3; u++) {
                int degree = 0;
                for (int v = 0; v < 3; v++) {
                    if ((mask & (1 << (u * 3 + v))) != 0) {
                        degree++;
                    }
                }

                graph[u] = new int[degree];
                int out = 0;
                for (int v = 0; v < 3; v++) {
                    if ((mask & (1 << (u * 3 + v))) != 0) {
                        graph[u][out++] = v;
                    }
                }
            }

            for (int source = 0; source < 3; source++) {
                verifySameAndReachability(graph, source);
                checked++;
            }
        }

        System.out.println(
            "Exhaustive directed graphs: PASS ("
            + (1 << 9) + " graphs x 3 sources)"
        );
    }

    static void randomGraphs() {
        Random random = new Random(540L);
        int cases = 400;

        for (int test = 0; test < cases; test++) {
            int n = 1 + random.nextInt(28);
            int[][] graph = new int[n][];

            for (int u = 0; u < n; u++) {
                int degree = random.nextInt(n + 1);
                graph[u] = new int[degree];
                for (int i = 0; i < degree; i++) {
                    graph[u][i] = random.nextInt(n);
                }
            }

            int source = random.nextInt(n);
            verifySameAndReachability(graph, source);
        }

        System.out.println(
            "Random directed multigraphs: PASS ("
            + cases + " cases)"
        );
    }

    // Deliberately DO NOT call recursiveDfs on a deep path.
    static void longPathTest() {
        int n = 50_000;
        int[][] graph = new int[n][];

        for (int u = 0; u < n; u++) {
            graph[u] = (u + 1 < n)
                ? new int[] {u + 1}
                : new int[0];
        }

        Traversal iterative = iterativeDfs(graph, 0);

        if (iterative.preorder().size() != n
                || iterative.postorder().size() != n
                || iterative.maximumDepth() != n
                || iterative.preorder().get(0) != 0
                || iterative.preorder().get(n - 1) != n - 1) {
            throw new AssertionError(
                "long path iterative traversal failed"
            );
        }

        System.out.println(
            "Long path visited: " + iterative.preorder().size()
        );
        System.out.println(
            "Long path maximum stack frames: "
            + iterative.maximumDepth()
        );
        System.out.println(
            "Long path last preorder: "
            + iterative.preorder().get(n - 1)
        );
    }

    public static void main(String[] args) {
        int[][] graph = {
            {1, 2, 1}, // 0: duplicate edge to 1
            {3, 4},    // 1
            {2, 4, 5}, // 2: self-loop
            {5},       // 3
            {6, 4},    // 4: self-loop
            {6},       // 5
            {},        // 6
            {7}        // 7: unreachable self-loop
        };

        Traversal a = recursiveDfs(graph, 0);
        Traversal b = iterativeDfs(graph, 0);

        System.out.println(
            "Sample preorder recursive: " + a.preorder()
        );
        System.out.println(
            "Sample preorder iterative: " + b.preorder()
        );
        System.out.println(
            "Sample postorder recursive: " + a.postorder()
        );
        System.out.println(
            "Sample postorder iterative: " + b.postorder()
        );
        System.out.println(
            "Same orders and depth: " + a.equals(b)
        );
        System.out.println(
            "Sample maximum depth: " + b.maximumDepth()
        );

        System.out.println(
            "Recursive sum(10): " + sumRecursive(10)
        );
        System.out.println(
            "Iterative sum(10): " + sumIterative(10)
        );
        System.out.println(
            "Iterative sum(100000): " + sumIterative(100_000)
        );

        longPathTest();

        try {
            iterativeDfs(graph, -1);
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Invalid source rejected: " + e.getMessage()
            );
        }

        try {
            iterativeDfs(new int[0][], 0);
        } catch (IllegalArgumentException e) {
            System.out.println(
                "Empty graph rejected: " + e.getMessage()
            );
        }

        exhaustiveTinyGraphs();
        randomGraphs();
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 RecursionDepthAndIterativeDfsDemo.java
java RecursionDepthAndIterativeDfsDemo
~~~

**Stdout dự kiến:**

~~~text
Sample preorder recursive: [0, 1, 3, 5, 6, 4, 2]
Sample preorder iterative: [0, 1, 3, 5, 6, 4, 2]
Sample postorder recursive: [6, 5, 3, 4, 1, 2, 0]
Sample postorder iterative: [6, 5, 3, 4, 1, 2, 0]
Same orders and depth: true
Sample maximum depth: 5
Recursive sum(10): 55
Iterative sum(10): 55
Iterative sum(100000): 5000050000
Long path visited: 50000
Long path maximum stack frames: 50000
Long path last preorder: 49999
Invalid source rejected: source index out of range
Empty graph rejected: graph must have at least one vertex
Exhaustive directed graphs: PASS (512 graphs x 3 sources)
Random directed multigraphs: PASS (400 cases)
~~~

### Tại sao stdout có thể xác định?

Chương trình DFS này **đơn luồng** và lần lượt xét adjacency theo đúng thứ tự trong từng mảng. Mô phỏng bằng Frame bảo toàn cả preorder/postorder nên hai danh sách in ra hoàn toàn giống nhau.

Khác với các thuật toán DFS **song song**, chương trình không có race quyết định cạnh được xử lý trước. Chỉ khi caller **thay đổi thứ tự các hàng xóm** hoặc thay đổi graph, thứ tự có thể đổi — nhưng vẫn đúng theo input mới.

### Có nên chạy recursiveDfs trên đường 50.000 đỉnh?

Không. Mục tiêu bài test là **bản iterative** xử lý đường sâu mà không cần call stack Java tăng theo n. Việc bắt buộc thử phiên bản recursive để “so xem nó crash hay không” có thể làm test phụ thuộc máy và gây lỗi không kiểm soát.

## 15. Kiểm thử exhaustive trên đồ thị có hướng nhỏ

Với n=3 có 9 cặp đỉnh có thứ tự \((u,v)\), kể cả self-loop:

\[
3\cdot3=9.
\]

Mỗi cạnh có thể có hoặc không, nên số đồ thị **đơn** có hướng là:

\[
\boxed{2^9=512}.
\]

Mỗi đồ thị được thử với **ba nguồn** 0, 1, 2:

\[
\boxed{512\cdot3=1536\text{ lượt so sánh}.}
\]

Tại từng lượt:

1. Chạy recursive DFS trên graph nhỏ.
2. Chạy iterative DFS với explicit Frame.
3. So **chính xác preorder**, **chính xác postorder**, **maximumDepth**.
4. Chạy BFS queue độc lập để xác nhận mỗi danh sách DFS chứa **đúng tập đỉnh reachable**.
5. Xác minh không đỉnh nào bị lặp trong preorder/postorder.

Số cạnh tối đa của graph n=3 chỉ là 9; đệ quy trên đồ thị này không gây vấn đề độ sâu thông thường. Các self-loop, cạnh quay lại và graph không liên thông đều được bao phủ.

### Test ngẫu nhiên và cạnh trùng

Exhaustive với mỗi cặp cạnh chỉ có/không **không có cạnh trùng**. Vì thế bộ `randomGraphs` sinh 400 graph có thể chứa:

- Một cạnh \((u,v)\) nhiều lần.
- Self-loop.
- Chu trình nhiều đỉnh.
- Nguồn nằm giữa một thành phần liên thông.
- Đỉnh không tới được từ nguồn.

Nguồn được chọn ngẫu nhiên; graph có n từ 1 đến 28 đỉnh. Mỗi graph được kiểm giống quy trình exhaustive.

### Một oracle độc lập không đồng nghĩa kết quả thứ tự giống BFS

BFS được dùng để kiểm **tập reachable**, không được đòi nó có cùng **preorder/postorder** với DFS. Thứ tự BFS và DFS nói chung khác nhau.

Nếu test ép:

~~~text
DFS preorder == BFS visit order
~~~

thì một chương trình DFS đúng cũng có thể bị đánh giá sai. Ta chỉ đối chiếu **tập đỉnh** với BFS, còn đối chiếu **thứ tự** giữa recursive DFS và iterative DFS cùng quy tắc.

## 16. Kiểm thử độ sâu mà không cố làm tràn stack

Một bài test tốt cho rủi ro đệ quy sâu nên:

- Dùng input dài tạo độ sâu logic cao.
- Chạy **bản iterative** trên input ấy.
- Xác nhận số đỉnh xử lý, kết quả và độ sâu frame đúng.
- Không cố kích hoạt `StackOverflowError` như một yêu cầu chức năng.
- Đo RAM/GC/thời gian riêng nếu mục tiêu là đánh giá hiệu năng.

Đường dài 50.000 đỉnh là ví dụ có một đường đi duy nhất nên:

\[
R=50000,\quad m=49999,\quad D=50000.
\]

`iterativeDfs` push một frame mới khi đi tới đỉnh tiếp theo. Ngay trước khi xử lý lá cuối, stack có đủ 50.000 frame. Sau đó từng frame hoàn tất, được pop cho đến khi stack rỗng. `maximumDepth` là 50.000, nhưng **không có 50.000 frame lời gọi Java**.

### Giới hạn heap vẫn tồn tại

Nếu n tăng từ 50.000 lên hàng trăm triệu, ngay bản iterative có thể thất bại do:

- Mảng graph quá lớn.
- Mỗi Frame là một object.
- Boxing `Integer` trong các danh sách.
- Lưu cả preorder và postorder.
- Cần mảng seen n phần tử.

Có thể tối ưu bằng **mảng primitive** chứa `vertex` và `nextIndex`, hoặc thiết kế streaming output khi phù hợp. Nhưng việc giảm overhead không làm thay đổi bản chất O(n) bộ nhớ trong trường hợp phải giữ toàn bộ danh sách duyệt.

## 17. Cách chuyển sang lặp mà không đổi ý nghĩa chương trình

Một checklist thực hành:

1. **Xác định base case** và điều kiện chấm dứt; nếu bản recursive sai thì bản iterative mô phỏng nó cũng có thể sai.
2. **Xác định vị trí tác vụ xảy ra:** trước lời gọi con, giữa hai lời gọi con, sau tất cả lời gọi con.
3. **Xác định trạng thái mỗi frame:** tham số, biến cục bộ, con trỏ vòng lặp, trạng thái trả về.
4. **Chọn cách lưu trạng thái:** biến vòng lặp đơn, stack `Frame`, queue, hoặc bảng DP bottom-up.
5. **Xác định thời điểm đánh dấu visited:** khi mới vào đỉnh, không phải tùy tiện lúc lấy ra khỏi stack.
6. **Đặt chính xác thời điểm push/pop:** tương ứng với call/return.
7. **Chứng minh tương đương** bằng một bất biến mô phỏng hoặc bất biến khác của phiên bản viết lại.
8. **Kiểm dữ liệu có chu trình và duplicate**, vì các trường hợp này bộc lộ sai lầm về visited.
9. **Kiểm ranh giới:** n=0/n=1 khi hợp đồng cho phép, đường dài, cây cân bằng, đồ thị nhiều nhánh.
10. **So bằng oracle độc lập** cho tính chất bên ngoài, tránh hai phiên bản cùng chia sẻ một lỗi.
11. **Phân tích lại bộ nhớ:** call stack biến thành heap không phải biến mất.
12. **Đo hiệu năng theo workload** và JVM cụ thể, tránh mặc định phiên bản iterative luôn nhanh hơn.

### Cảnh giác với thứ tự hàng xóm

Trong DFS, chỉ đổi thứ tự adjacency cũng có thể đổi thứ tự preorder/postorder, dù tập visited vẫn đúng.

Nếu một bài toán phụ thuộc thứ tự duyệt (ví dụ tạo thứ tự DFS cụ thể), quy ước của input phải rõ ràng. Nếu không phụ thuộc, đừng ép một thứ tự duy nhất vào bài kiểm thử.

## 18. Các kỹ thuật giảm độ sâu mà không cần explicit stack

Đôi khi có cách chỉnh thuật toán để hạn chế độ sâu ngay trong bản đệ quy.

### A. Quicksort: đệ quy phía nhỏ hơn, lặp phía lớn hơn

Với quicksort, sau phân hoạch thành hai đoạn, một kỹ thuật là:

- Đệ quy trên **đoạn nhỏ hơn**.
- Tiếp tục bằng vòng lặp với **đoạn lớn hơn**.

Vì đoạn được gọi đệ quy có kích thước tối đa khoảng **một nửa** đoạn hiện tại (khi hai đoạn không rỗng và chọn nhánh nhỏ), độ sâu call stack có thể giới hạn O(log n) cho mẫu tổ chức này, ngay cả khi phân hoạch lệch.

Điều này **không tự sửa trường hợp thời gian O(n²)** do chọn pivot kém; nó chỉ xử lý rủi ro **stack sâu**.

### B. Duyệt cây bằng Morris traversal

Trong một số cây nhị phân có thể thay đổi liên kết tạm thời, **Morris traversal** thực hiện inorder với O(1) bộ nhớ phụ bằng threading tạm các liên kết.

Nhưng nó có giả định và rủi ro riêng: phải **khôi phục** liên kết đúng, không thích hợp khi cấu trúc bất biến/được dùng chung đồng thời, và không thay thế mọi kiểu DFS trên đồ thị.

### C. DP theo thứ tự phụ thuộc

Với một DAG (đồ thị có hướng không chu trình), một phép tính đệ quy có memoization có thể được chuyển thành tính **theo thứ tự topo** hoặc topo ngược tùy chiều phụ thuộc. Lúc ấy không cần mô phỏng toàn bộ call stack DFS cho mỗi trạng thái.

### D. Trampoline

Một kỹ thuật khác là biểu diễn “bước gọi tiếp” thành một đối tượng/hàm không gọi đệ quy ngay, rồi dùng vòng lặp liên tục thực thi bước ấy (*trampoline*). Điều này linh hoạt cho một số mô hình hàm, nhưng trong Java có thể tạo nhiều đối tượng/lambda và chi phí lớn.

**Bài học thực tế:** chọn kỹ thuật chuyển đổi **theo bất biến** và yêu cầu trả kết quả, không chỉ theo từ khóa “đệ quy”.

## 19. Các kiểu lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
|---|---|---|
| Quên điều kiện dừng | Lời gọi không chấm dứt | Chứng minh biến đo tiến triển |
| Đệ quy sâu trên đường dài | Call stack O(n) | Explicit stack hoặc cấu trúc lặp |
| Chỉ push đỉnh mà cần postorder | Mất thời điểm quay lui | Frame có nextIndex/phase |
| Đánh dấu visited quá sớm khi push mọi hàng xóm | DFS order có thể khác | Mark khi **vào frame** mô phỏng lời gọi |
| Quên tăng nextIndex | Xét lại cạnh mãi | Tăng trước khi push con |
| Chỉ ghi preorder | Không biết thời điểm hoàn tất | Ghi postorder lúc pop |
| Đẩy tất cả hàng xóm trước khi xử lý con đầu | Thay đổi semantics DFS | Giữ vòng for đang dở trong frame |
| Dùng `StackOverflowError` làm nhánh chương trình | Trạng thái dở dang | Phòng tránh độ sâu |
| Giả định Java TCO bắt buộc | Phụ thuộc JVM | Chuyển tail recursion sang while |
| Tưởng explicit stack không tốn RAM | Heap vẫn có giới hạn | Phân tích O(D) + overhead |
| Quên visited trên graph có chu trình | Có thể vòng mãi | Mark khi khám phá |
| Dùng `HashSet` rồi giả định thứ tự cố định | Thứ tự duyệt có thể đổi | Dùng adjacency order có hợp đồng rõ |
| So DFS order với BFS order | Hai chiến lược khác nhau | So tập reachable, hoặc so hai DFS đồng quy tắc |
| Đệ quy trong đường thử “stress” không kiểm soát | Test phụ thuộc stack máy | Chỉ chạy bản iterative trên đường sâu |
| Coi mọi DFS stack là tương đương recursive DFS | Sai preorder/postorder | Mô phỏng đúng frame |
| Quên kiểm đầu vào | ArrayIndexOutOfBounds/NullPointer | Validate trước khi duyệt |

### Một số lỗi tinh vi khác

1. **Đếm tổng số lời gọi là độ sâu cực đại**, làm đánh giá bộ nhớ sai.
2. **Bỏ qua frame của lời gọi cơ sở**, dẫn đến quy ước đếm lệch một.
3. **Thử nâng -Xss để chữa vòng đệ quy vô hạn**, chỉ trì hoãn lỗi.
4. **Cho rằng catch StackOverflowError sẽ luôn phục hồi an toàn**, không có bảo đảm trạng thái/đủ stack.
5. **Dùng recursion sâu trong hàm equals/toString của cấu trúc lồng nhau**, lỗi có thể xảy ra ngoài thuật toán chính.
6. **Dùng n quá lớn với `int` ở bộ đếm hoặc chỉ số**, gây tràn khi tăng ở ranh giới.
7. **Chuyển recursion thành while nhưng làm mất tham số accumulator**, kết quả sai.
8. **Không giữ return value của lời gọi con khi cha còn cần kết quả**, biến đổi không tương đương.
9. **Pop frame cha trước khi xử lý xong các con**, postorder sai.
10. **Push con mà không đánh dấu visited**, dễ tạo nhiều frame cho cùng đỉnh.
11. **Mark visited từ khi push tất cả hàng xóm vào một stack đơn giản**, thay đổi cây DFS.
12. **Đọc adjacency[u] khi u không hợp lệ**, tạo lỗi trước khi kiểm input.
13. **Cho phép graph bị sửa trong lúc duyệt**, invalidates nextNeighborIndex/adjacency order.
14. **Không xử lý self-loop và cạnh trùng**, đếm sai số đỉnh.
15. **Gọi DFS từ source nhưng đòi thăm cả các thành phần không tới được**, sai hợp đồng một nguồn.
16. **Nhầm DFS postorder với BFS order hay reverse preorder**, hai thứ tự không tương đương.
17. **Cho rằng bản iterative có O(1) bộ nhớ vì không gọi đệ quy**, quên explicit stack.
18. **Quên tính List<Integer> boxing và Frame object**, RAM thực tế cao hơn mảng primitive.
19. **Dùng recursive DFS làm oracle duy nhất trên input sâu gây tràn**, test thất bại vì oracle.
20. **Đo performance trên một graph cực nhỏ rồi kết luận tuyệt đối**, noise JVM/JIT chiếm ưu thế.
21. **Dùng đệ quy không đuôi nhưng coi là tail call**, chưa có chiến lược giữ phép toán sau lời gọi con.
22. **Chỉ bảo toàn tập visited mà khẳng định postorder đã được bảo toàn**, không đúng.
23. **Không kiểm lỗi input rỗng/nguồn âm**, chương trình chết khó hiểu.
24. **Không kiểm output pre/post có đúng một lần mỗi đỉnh**, có thể không phát hiện duplicate work.
25. **Dùng ArrayDeque mà cố push null làm sentinel**, `ArrayDeque` không chấp nhận phần tử null.
26. **Dùng `int[]` làm frame mutable rồi vô tình dùng chung giữa nhiều vị trí**, các trạng thái chồng lấn.
27. **Thay đổi `nextNeighborIndex` của sai frame sau khi pop**, làm mất vị trí tiếp tục.
28. **Bỏ qua biến cục bộ dùng sau lời gọi con trong các bài backtracking**, khôi phục nhánh sai.
29. **Đặt side effect ở thời điểm push/pop khác bản gốc**, output khác dù visited đúng.
30. **Coi StackOverflowError và OutOfMemoryError là một lỗi**, chúng liên quan đến vùng nhớ/ràng buộc khác nhau.
31. **Dùng ngăn xếp tường minh không giới hạn và để input không đáng tin cậy kiểm soát độ sâu**, vẫn có nguy cơ cạn tài nguyên.
32. **Không phân biệt n đỉnh và m cạnh**, suy luận O(n) cho việc quét mọi adjacency dù m≫n.
33. **Không tính chi phí kiểm tra toàn bộ graph**, có thể là O(n+m).
34. **Không phân biệt traversal một nguồn với full graph traversal**, đặc biệt graph không liên thông.
35. **Đổi cấu trúc recursive sang bottom-up mà không chứng minh thứ tự phụ thuộc**, đọc trạng thái chưa tính.

## 20. Câu hỏi và bài tập tự luyện

**Bài 1.** Độ sâu đệ quy là gì?

*Đáp án:* Số lời gọi đang hoạt động đồng thời trên một chuỗi gọi, tính theo quy ước lời gọi gốc có độ sâu 1.

**Bài 2.** Có một triệu lời gọi DFS có nhất thiết một triệu frame đồng thời không?

*Đáp án:* Không; phụ thuộc vào độ sâu đường đi đang hoạt động, không phải tổng số đỉnh đã duyệt.

**Bài 3.** Vì sao DFS trên đường dài có thể nguy hiểm với recursion?

*Đáp án:* Độ sâu có thể O(n), tiêu thụ nhiều frame call stack và có thể gây StackOverflowError.

**Bài 4.** `StackOverflowError` là `Exception` thông thường trong Java không?

*Đáp án:* Không; nó là một `Error`.

**Bài 5.** Java có bảo đảm tail-call optimization không?

*Đáp án:* Không có bảo đảm để dựa vào khi thiết kế tránh stack sâu.

**Bài 6.** Tail recursion thường chuyển thành cấu trúc gì?

*Đáp án:* Vòng lặp cập nhật trạng thái hoặc accumulator, không có nested method call.

**Bài 7.** Với n=10, tổng từ 1 đến n bằng bao nhiêu?

*Đáp án:* 55.

**Bài 8.** Với n=100.000, tổng từ 1 đến n bằng bao nhiêu?

*Đáp án:* 5.000.050.000, cần `long` vì lớn hơn `int`.

**Bài 9.** Khác biệt giữa call stack và explicit stack?

*Đáp án:* Call stack do runtime giữ frame lời gọi; explicit stack do chương trình quản lý (thường trên heap).

**Bài 10.** Explicit stack có O(1) bộ nhớ không?

*Đáp án:* Không; nếu sâu D, cần O(D) frame ngoài các cấu trúc khác.

**Bài 11.** Vì sao DFS iterative cần lưu `nextNeighborIndex` khi muốn giữ postorder?

*Đáp án:* Nó lưu vị trí vòng for của lời gọi đang tạm dừng để quay lại đúng chỗ sau khi con hoàn tất.

**Bài 12.** Preorder được ghi khi nào?

*Đáp án:* Khi **bắt đầu** thăm đỉnh, tương đương vào lời gọi đệ quy.

**Bài 13.** Postorder được ghi khi nào?

*Đáp án:* Khi **mọi hàng xóm đã xét xong** và frame sắp pop.

**Bài 14.** Vì sao tăng nextIndex trước khi push frame con?

*Đáp án:* Để frame cha tiếp tục ở hàng xóm kế tiếp sau khi con trả về.

**Bài 15.** Trong ví dụ nguồn 0, preorder là gì?

*Đáp án:* \([0,1,3,5,6,4,2]\).

**Bài 16.** Postorder của ví dụ nguồn 0 là gì?

*Đáp án:* \([6,5,3,4,1,2,0]\).

**Bài 17.** Độ sâu cực đại của ví dụ là bao nhiêu frame?

*Đáp án:* 5.

**Bài 18.** Đỉnh 7 trong ví dụ có xuất hiện không?

*Đáp án:* Không, vì không reachable từ nguồn 0.

**Bài 19.** Self-loop u→u có gây gọi lại dfs(u) khi visited đã đánh dấu từ lúc vào không?

*Đáp án:* Không, điều kiện `!seen[u]` sẽ không thỏa.

**Bài 20.** Cạnh trùng u→v có làm v xuất hiện hai lần trong preorder không?

*Đáp án:* Không, nếu visited được đánh dấu khi lần đầu vào v.

**Bài 21.** DFS iterative dùng frame có cùng preorder/postorder recursive không?

*Đáp án:* Có trong thiết kế đã chứng minh khi graph bất biến và thứ tự adjacency giữ nguyên.

**Bài 22.** Một stack chỉ lưu đỉnh có đủ bảo toàn postorder không?

*Đáp án:* Không mặc định; cần pha quay lui hoặc con trỏ cạnh để tái hiện đúng thời điểm sau khi xử lý mọi con.

**Bài 23.** Độ phức tạp DFS trên danh sách kề là gì?

*Đáp án:* O(n+m) thời gian, với mỗi đỉnh/cạnh reachable xử lý tối đa một lần và nếu validate cả graph thì O(n+m).

**Bài 24.** Mức nhớ phần stack DFS đệ quy là bao nhiêu?

*Đáp án:* O(D) frame call stack, D là độ sâu DFS cực đại.

**Bài 25.** Mức nhớ phần stack DFS iterative là bao nhiêu?

*Đáp án:* O(D) frame explicit stack trên heap.

**Bài 26.** Đường gồm 50.000 đỉnh có độ sâu logic tối đa bao nhiêu?

*Đáp án:* 50.000 frame theo quy ước gốc độ sâu 1.

**Bài 27.** Có nên cố gây StackOverflowError trong test tự động trên mọi JVM không?

*Đáp án:* Không; kết quả phụ thuộc runtime và có thể gây trạng thái dở dang.

**Bài 28.** Vì sao dùng BFS làm oracle kiểm DFS?

*Đáp án:* BFS là cách độc lập để xác nhận **tập đỉnh reachable**, không ép thứ tự duyệt giống nhau.

**Bài 29.** Với n=3 có hướng và cho phép self-loop, có bao nhiêu graph đơn có hướng?

*Đáp án:* \(2^9=512\).

**Bài 30.** Thử cả ba nguồn trên 512 graph tạo bao nhiêu lượt?

*Đáp án:* 1536.

**Bài 31.** Vì sao test thêm cạnh trùng ngẫu nhiên khi đã exhaustive 512 graph?

*Đáp án:* Vì không gian 512 graph có/không mỗi cạnh **không biểu diễn multiplicity**.

**Bài 32.** Khi nào nên dùng bottom-up DP thay vì explicit frames?

*Đáp án:* Khi có thứ tự trạng thái thỏa phụ thuộc và dễ tính trực tiếp không cần mô phỏng call stack.

**Bài 33.** Vì sao không nên dùng `-Xss` thay cho phân tích thuật toán?

*Đáp án:* Nó chỉ ảnh hưởng ngân sách stack trong môi trường cụ thể, không giải quyết độ sâu không bị chặn hay thiếu base case.

**Bài 34.** Nếu đệ quy giải hai bài toán con rồi ghép kết quả, frame iterative cần gì thêm?

*Đáp án:* Pha xử lý và vùng giữ các giá trị trả về trung gian trước lúc ghép.

**Bài 35.** Chuyển recursion sang iteration có luôn giữ nguyên hiệu năng không?

*Đáp án:* Không; overhead call/frame allocation, locality và tối ưu JVM khác nhau, cần benchmark cụ thể.

**Tổng kết:** Độ sâu đệ quy là **số frame lời gọi đang đồng thời hoạt động**, khác với tổng số lời gọi. Đệ quy rất phù hợp khi độ sâu nhỏ và cấu trúc bài toán tự nhiên, nhưng với DFS trên đường sâu D=O(n), Java có thể gặp **StackOverflowError** và không thể dựa vào tối ưu hóa tail call. Chuyển tail recursion thành vòng lặp cập nhật accumulator là trường hợp đơn giản; với DFS cần **mô phỏng đầy đủ frame gồm đỉnh và chỉ số hàng xóm kế tiếp**. Ghi preorder lúc vào frame, postorder lúc pop, đánh dấu visited khi vào, tăng nextIndex trước khi đi con và duy trì bất biến giữa explicit stack và call stack là cách bảo toàn chính xác hành vi đệ quy. Mã Java 17 kiểm trên 512 đồ thị có hướng nhỏ x 3 nguồn, 400 graph ngẫu nhiên và đường dài 50.000 đỉnh được xử lý **chỉ bằng bản lặp**. Explicit stack tránh call stack Java tăng theo D nhưng **không loại bỏ O(D) bộ nhớ**; an toàn và hiệu quả cần được đánh giá theo giới hạn dữ liệu, cấu trúc output và môi trường thực thi.
