# Sắp xếp tô-pô bằng bậc vào

**Sắp xếp tô-pô** (*topological sorting*) là việc tạo một thứ tự tuyến tính của các đỉnh trong **đồ thị có hướng** sao cho **mọi cung u → v đều có u xuất hiện trước v**. Bài toán xuất hiện khi một công việc phải hoàn thành trước công việc khác: đăng ký môn tiên quyết, lập lịch build phần mềm, thực hiện tác vụ phụ thuộc, sắp xếp các bước xử lý dữ liệu và triển khai các giai đoạn công việc.

Thuật toán dùng **bậc vào** (*indegree*) thường được gọi là **thuật toán Kahn**. Tư tưởng chính: ở mỗi thời điểm, chọn một đỉnh **không còn cung đi vào từ các đỉnh chưa xử lý**; đưa đỉnh ấy vào kết quả; coi các cung đi ra từ nó đã được loại bỏ; cập nhật bậc vào của các đỉnh đích. Nếu cuối cùng xử lý đủ mọi đỉnh, ta có một thứ tự tô-pô. Nếu còn đỉnh nhưng **không còn đỉnh nào có bậc vào bằng 0**, đồ thị chứa chu trình có hướng và **không tồn tại thứ tự tô-pô đầy đủ**.

Bài học tập trung vào **định nghĩa và điều kiện tồn tại, cơ chế bậc vào động, BFS/hàng đợi, phát hiện chu trình, chứng minh tính đúng, phân tích O(V+E), nhiều thứ tự hợp lệ, chọn thứ tự nhỏ nhất bằng heap, trường hợp biên và cài đặt Java 17+**. Các thuật ngữ và giả thiết được trình bày từ đầu; không cần đọc bài khác để hiểu hay chạy ví dụ.

## 1. Đồ thị có hướng và ý nghĩa của một cung

Cho đồ thị có hướng `G=(V,E)`:

- `V` là tập đỉnh, có thể là các môn học, gói phần mềm, công việc hoặc các bước quy trình.
- `E` là tập cung có hướng. Cung `u → v` nghĩa là **u phải xuất hiện trước v**.
- Với `n=|V|`, chương trình minh họa đánh số đỉnh từ `0` đến `n−1`.
- Nếu u là điều kiện tiên quyết của v, cung đúng hướng là `u → v`, **không phải** `v → u`.

Một thứ tự `order=[v0,v1,...,v(n−1)]` hợp lệ phải đáp ứng:

1. Chứa **đúng n đỉnh phân biệt**, mỗi đỉnh đúng một lần.
2. Với mọi cung `u → v`, vị trí của u trong order **nhỏ hơn** vị trí của v.

Công thức kiểm tra:

```text
position[order[i]] = i

Với mọi cung (u,v) trong E:
    position[u] < position[v]
```

Ví dụ:

```text
0 ---> 2 ---> 3
 \           ^
  \-> 1 -----|

Cung: (0,2), (0,1), (2,3), (1,3)
```

Hai thứ tự `[0,1,2,3]` và `[0,2,1,3]` đều hợp lệ. Không có cung yêu cầu 1 xuất hiện trước 2 hoặc ngược lại, nên cả hai vị trí tương đối đều được phép.

**Sắp xếp tô-pô không phải sắp theo trọng số, tên hay số đỉnh.** Tên và chỉ số chỉ có thể dùng để phá hòa giữa nhiều lựa chọn cùng hợp lệ, không được vi phạm ràng buộc cung.

### Khi nào tồn tại thứ tự tô-pô?

**Một đồ thị có hướng hữu hạn có thứ tự tô-pô đầy đủ khi và chỉ khi nó không có chu trình có hướng**, tức là một **DAG** (*directed acyclic graph*).

Nếu có chu trình:

```text
a -> b -> c -> a
```

thứ tự hợp lệ sẽ đòi a trước b, b trước c và c trước a. Những điều kiện này mâu thuẫn với trật tự tuyến tính, nên không thể tồn tại kết quả đầy đủ.

Ngược lại, một DAG hữu hạn không rỗng luôn có ít nhất một đỉnh không có cung đi vào. Nếu mọi đỉnh đều có ít nhất một cung đi vào, cứ lần theo một cung đi ngược lại từ một đỉnh bất kỳ; vì số đỉnh hữu hạn, sẽ có đỉnh lặp lại và tạo chu trình, trái với giả thiết DAG. Đây là nền tảng toán học của thuật toán Kahn.

## 2. Bậc vào (indegree) là gì?

**Bậc vào** của đỉnh v là số cung có đích là v:

```text
indegree[v] = số cung u -> v trong đồ thị đang xét
```

Ví dụ:

```text
0 ---> 2 ---> 3
1 ---------> 3

Các cung: (0,2), (2,3), (1,3)

indegree[0]=0
indegree[1]=0
indegree[2]=1
indegree[3]=2
```

Đỉnh 0 và 1 có thể thực hiện ngay vì không cần đỉnh nào khác đi trước. Đỉnh 2 cần xử lý 0 trước. Đỉnh 3 cần xử lý **cả 1 và 2** trước.

**Bậc vào động**, không chỉ bậc vào ban đầu: Khi đã xử lý một đỉnh u, ta **xóa về mặt logic** những cung `u → v` khỏi phần đồ thị còn lại. Với mỗi cung như vậy, giảm:

```text
indegree[v]--
```

Khi `indegree[v]` giảm xuống **đúng 0**, v đã hoàn thành tất cả các điều kiện tiên quyết trong mô hình này và được đưa vào hàng đợi ứng viên.

**Không được giảm indegree của u khi đi qua một cung u→v.** Đỉnh bị ảnh hưởng là **đích v**, vì ta đã loại một yêu cầu đối với v.

### Bậc vào bằng 0 chỉ có nghĩa gì?

Ở đầu thuật toán, indegree[v]=0 nghĩa là v không có cung đi vào trong đồ thị ban đầu. Ở những bước sau, indegree[v]=0 nghĩa là **không còn cung đi vào từ những đỉnh chưa xử lý**. Nó **không** có nghĩa v chưa từng có tiền nhiệm; các tiền nhiệm có thể đã được lấy ra khỏi đồ thị.

Đỉnh đã lấy ra được coi như đã xử lý xong, nên không cần đưa vào hàng đợi lần nữa.

## 3. Thuật toán Kahn từng bước

Thuật toán gồm bốn giai đoạn:

1. **Xây danh sách kề cung đi ra và đếm indegree ban đầu.**
2. **Đưa tất cả đỉnh indegree=0 vào hàng đợi.**
3. **Lặp:** Lấy một đỉnh ra, ghi vào kết quả, giảm bậc vào của từng đỉnh ở cuối các cung đi ra; khi bậc vào của một đỉnh bằng 0, đưa nó vào hàng đợi.
4. **Kiểm tra số đỉnh đã xử lý.** Nếu bằng n → tồn tại thứ tự tô-pô; nếu ít hơn n → có chu trình.

Giả mã:

```text
TOPOLOGICAL-SORT(n, edges):
    adjacency = danh sách các đỉnh v có cung u -> v
    indegree[0..n-1] = 0

    for each (u,v) in edges:
        adjacency[u].add(v)
        indegree[v] += 1

    ready = empty FIFO queue
    for v = 0..n-1:
        if indegree[v] == 0:
            ready.add(v)

    order = empty list

    while ready is not empty:
        u = ready.remove()
        order.add(u)

        for each v in adjacency[u]:
            indegree[v] -= 1
            if indegree[v] == 0:
                ready.add(v)

    if order.size == n:
        return DAG, order
    else:
        return CYCLE_DETECTED, partial_order=order
```

**Dấu hiệu phát hiện chu trình là số đỉnh đã lấy ra**, không phải số cung còn lại có thể đếm nhầm, cũng không phải việc một nhánh BFS kết thúc sớm.

Khi còn đỉnh nhưng không có ứng viên bậc vào 0, một chu trình nằm trong phần đồ thị chưa xử lý. Kết quả `order` lúc đó chỉ là **tiền tố đã xử lý**, **không phải thứ tự tô-pô của toàn đồ thị**.

### Tại sao không cần thật sự xóa cạnh khỏi danh sách kề?

Trong code, khi xử lý cung u→v, ta thực hiện `indegree[v]--`. Như vậy trạng thái số cung đi vào còn lại được cập nhật chính xác mà không cần xóa phần tử khỏi danh sách kề. Danh sách kề được giữ nguyên để duyệt các cung đúng một lần khi u được lấy ra.

Đây là một ví dụ của kỹ thuật **mô phỏng phép xóa bằng bộ đếm**. Hình dung “xóa cung” giúp hiểu thuật toán, còn triển khai thực tế chủ yếu thay đổi mảng indegree.

## 4. Mô phỏng một DAG nhiều nhánh

Xét đồ thị có sáu đỉnh với các cung:

```text
5 -> 2
5 -> 0
4 -> 0
4 -> 1
2 -> 3
3 -> 1
```

Bậc vào ban đầu:

| Đỉnh | 0 | 1 | 2 | 3 | 4 | 5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| indegree | 2 | 2 | 1 | 1 | 0 | 0 |

Bắt đầu có hai đỉnh sẵn sàng: **4 và 5**. Với hàng đợi FIFO khởi tạo bằng cách duyệt chỉ số 0..5, hàng đợi ban đầu là `[4,5]`.

Mô phỏng theo đúng thứ tự cung đã liệt kê:

| Bước | Lấy ra | Cập nhật bậc vào | Hàng đợi sau bước | Kết quả |
| ---: | ---: | --- | --- | --- |
| 1 | 4 | indegree[0]:2→1; indegree[1]:2→1 | [5] | [4] |
| 2 | 5 | indegree[2]:1→0; indegree[0]:1→0 | [2,0] | [4,5] |
| 3 | 2 | indegree[3]:1→0 | [0,3] | [4,5,2] |
| 4 | 0 | Không có cung ra | [3] | [4,5,2,0] |
| 5 | 3 | indegree[1]:1→0 | [1] | [4,5,2,0,3] |
| 6 | 1 | Không có cung ra | [] | [4,5,2,0,3,1] |

Kết quả FIFO:

```text
[4, 5, 2, 0, 3, 1]
```

Kiểm tra từng cung:

```text
5 trước 2 và 0
4 trước 0 và 1
2 trước 3
3 trước 1
```

Tất cả đều đúng.

### Vì sao không cần một kết quả duy nhất?

Tại bước 2, hàng đợi xuất hiện cùng lúc 2 và 0; hai đỉnh này không ràng buộc thứ tự tương đối. Nếu chọn 0 trước 2, vẫn có thể hoàn thành một thứ tự hợp lệ:

```text
[4, 5, 0, 2, 3, 1]
```

**Sắp xếp tô-pô có thể có nhiều đáp án đúng**. Nếu đề bài không yêu cầu thứ tự nhỏ nhất theo từ điển, không nên đánh giá một kết quả là sai chỉ vì nó khác danh sách của một ví dụ nào đó.

## 5. Tại sao thuật toán này đôi khi được gọi là BFS?

Kahn thường được viết bằng **queue** nên nhiều tài liệu đặt nó cạnh BFS hoặc gọi là “BFS-based topological sort”. Tuy nhiên, mục tiêu không phải tính khoảng cách ngắn nhất hay thăm các đỉnh theo khoảng cách từ một nguồn.

Khác biệt:

| Khía cạnh | BFS truyền thống | Kahn theo bậc vào |
| --- | --- | --- |
| Tiêu chí đưa đỉnh vào queue | Được khám phá lần đầu từ đỉnh đang thăm | **Mọi tiền nhiệm chưa xử lý đã được giải phóng**, indegree bằng 0 |
| Khởi tạo | Thường từ một nguồn s | **Tất cả đỉnh có bậc vào 0**, có thể nhiều nguồn |
| Kết quả | Thứ tự thăm, khoảng cách/lớp BFS | **Một thứ tự phù hợp với toàn bộ cung** |
| Có bắt buộc DAG? | Không | Có để hoàn thành tất cả đỉnh |
| Cơ chế cập nhật | Trạng thái đã thăm | **Giảm indegree của đỉnh đích** |

Một đỉnh có nhiều tiền nhiệm **không được đưa vào queue chỉ vì đã nhìn thấy từ một tiền nhiệm đầu tiên**. Nó phải chờ cho **tất cả cung đi vào còn lại** bị giảm về 0.

Ví dụ:

```text
0 -> 3
1 -> 3
2 -> 3
```

Không thể đưa 3 vào ngay sau khi xử lý 0, vì còn hai điều kiện 1 và 2 chưa xong. Bậc vào của 3 đi từ 3 xuống 2, rồi 1, rồi 0; **chỉ khi đạt 0** mới thêm vào queue.

## 6. Độ phức tạp O(V+E) khi dùng danh sách kề

Gọi n=|V| và m=|E|:

- Tạo danh sách kề gồm n danh sách rỗng: **O(n)**.
- Duyệt m cung để thêm vào danh sách kề và tăng bậc vào: **O(m)**.
- Duyệt n đỉnh để khởi tạo queue: **O(n)**.
- Mỗi đỉnh được thêm vào queue **nhiều nhất một lần**, vì indegree chỉ giảm và đạt 0 tối đa một lần: tổng **O(n)** thao tác thêm/lấy.
- Mỗi cung u→v được duyệt đúng một lần khi u được lấy khỏi queue: tổng **O(m)** thao tác giảm indegree.

Vì vậy:

```text
Thời gian:  O(V + E)
Bộ nhớ:    O(V + E)
```

Bộ nhớ bao gồm danh sách kề O(V+E), indegree O(V), queue O(V), kết quả O(V). Code minh họa còn giữ mảng dấu đỉnh đã xử lý O(V) để in danh sách đỉnh chưa xử lý.

**Điều kiện của kết luận tuyến tính:** Hàm lấy một phần tử từ queue FIFO phải có độ phức tạp O(1) khấu hao/đúng loại cấu trúc. Trong Java, dùng `ArrayDeque<Integer>` cho thao tác ở hai đầu. Nếu dùng `ArrayList.remove(0)`, mỗi lần xóa đầu có thể phải dời phần tử O(V), làm mất bảo đảm O(V+E).

Nếu dùng **ma trận kề** n×n rồi mỗi lần lấy u phải quét hết n khả năng cung đi ra, thời gian trở thành **O(n²)** ngay cả trên đồ thị rất thưa. Nếu đồ thị thưa, danh sách kề thường hợp lý hơn.

### “Tuyến tính” có nghĩa là gì với đồ thị dày?

Với đồ thị có hướng đơn, m có thể gần n(n−1), nên O(V+E) tương đương O(n²) trên đồ thị rất dày. Đó vẫn là **tuyến tính theo kích thước biểu diễn danh sách kề**, vì bản thân input đã chứa Θ(n²) cung.

## 7. Phát hiện chu trình bằng số đỉnh đã xử lý

Nếu `order.length == n`, mọi đỉnh đã được lấy ra khỏi queue, và thứ tự đầy đủ tồn tại.

Nếu `order.length < n`, có đỉnh còn chưa xử lý nhưng queue đã hết. Trong phần đồ thị còn lại, mỗi đỉnh đều có ít nhất một cung đi vào từ một đỉnh chưa xử lý; nếu có đỉnh indegree=0, nó đã được đưa vào queue. Một đồ thị có hướng hữu hạn mà mọi đỉnh đều có bậc vào ít nhất một **phải chứa chu trình**. Vì vậy không thể có thứ tự tô-pô đầy đủ.

Ví dụ chu trình ba đỉnh:

```text
0 -> 1 -> 2 -> 0

indegree = [1,1,1]
ready ban đầu = []
order = []
processed count = 0 < 3
=> có chu trình, không có topological order đầy đủ.
```

### Có chu trình nhưng vẫn xử lý được một phần

Xét:

```text
0 -> 1
1 -> 2
2 -> 1
2 -> 3
```

Đỉnh 0 có bậc vào 0, nên được xử lý trước. Nhưng các đỉnh 1 và 2 tạo chu trình 1→2→1. Đỉnh 3 nhận cung từ 2, nên cũng chưa thể xử lý.

Kahn trả:

```text
partial order = [0]
unresolved    = [1,2,3]
dag           = false
```

**Lưu ý quan trọng:** Đỉnh 3 trong danh sách unresolved **không thuộc chu trình 1↔2**; nó chỉ bị chặn bởi chu trình. Vì vậy **danh sách đỉnh chưa xử lý không phải danh sách chính xác các đỉnh thuộc chu trình**.

Muốn liệt kê một chu trình cụ thể, cần thêm thuật toán truy vết chu trình (ví dụ DFS với trạng thái xám hoặc các thành phần liên thông mạnh), hoặc xử lý riêng phần đồ thị chưa hoàn thành. Kahn cơ bản cho biết **có chu trình hay không**, không tự cung cấp chứng cứ chu trình dưới dạng dãy đỉnh.

### Self-loop là một chu trình

Cung `u→u` tạo chu trình độ dài 1. Nếu giữ self-loop trong input, indegree[u] được tăng 1 và không thể giảm về 0 trước khi u được xử lý; nhưng u lại không thể được xử lý khi indegree>0. Kahn phát hiện đúng rằng không có topo order đầy đủ.

Vì vậy code mẫu **cho phép self-loop như một cạnh đầu vào hợp lệ của đồ thị có hướng**, rồi trả `dag=false`, thay vì coi đó là lỗi định dạng. Đây là lựa chọn API có chủ đích và được kiểm thử.

## 8. Khi nào thứ tự tô-pô là duy nhất?

Giả sử đồ thị đã được xác nhận là **DAG**. Ta xét số lựa chọn sẵn sàng tại từng bước của Kahn.

- Nếu **ở mọi bước** queue chứa **đúng một đỉnh**, thứ tự chọn luôn bị ép, nên topo order là **duy nhất**.
- Nếu **có bước** queue chứa **ít nhất hai đỉnh** khác nhau u,v, cả hai hiện đều có indegree=0. Ta có thể chọn u trước v hoặc v trước u, và sau đó hoàn thiện DAG thành thứ tự tô-pô hợp lệ. Vậy tồn tại **ít nhất hai** thứ tự tô-pô khác nhau.

Tiêu chí:

```text
unique = DAG && (số đỉnh sẵn sàng ở mọi bước == 1)
```

Chỉ cần một biến boolean:

```java
boolean forcedAtEveryStep = true;

while (!ready.isEmpty()) {
    if (ready.size() > 1) {
        forcedAtEveryStep = false;
    }
    int u = ready.remove();
    // Xử lý các cung đi ra...
}
```

Nếu kết thúc mà `processed<n`, câu hỏi “unique topological order” không có đáp án true vì **không tồn tại bất kỳ thứ tự tô-pô đầy đủ nào**. Code trả `unique=false` cho trường hợp này.

### Tại sao có hai ứng viên thì đổi thứ tự không gây lỗi?

Nếu u và v cùng có indegree=0 trong phần đồ thị chưa xử lý:

- Không thể có cung trực tiếp u→v, vì khi ấy indegree[v]>0.
- Không thể có cung v→u tương tự.
- Cũng không thể có đường có hướng u⇝v hoặc v⇝u chỉ qua các đỉnh chưa xử lý, vì khi đó đỉnh đích sẽ có tiền nhiệm chưa xử lý.

Do đó chúng không ràng buộc nhau theo thứ tự. Chọn một trước không khiến đỉnh còn lại mất tính sẵn sàng, vì các thao tác chỉ **giảm** indegree. Sau khi chọn cả hai, có thể tiếp tục hoàn thành DAG. Hai lựa chọn dẫn tới hai thứ tự khác nhau.

**Chú ý cách đếm queue:** Kiểm tra kích thước queue **ngay trước khi lấy u ra**, không phải sau khi lấy rồi cập nhật. Đó là thời điểm có bao nhiêu lựa chọn hợp lệ hiện tại.

## 9. Lấy thứ tự nhỏ nhất theo từ điển bằng priority queue

Trong nhiều bài lập trình, đề bài yêu cầu nếu có nhiều topo order thì trả thứ tự có **giá trị từ điển nhỏ nhất** (*lexicographically smallest order*). Với đỉnh được đánh số 0..n−1, ở mỗi bước cần chọn **đỉnh có chỉ số nhỏ nhất trong tập đang sẵn sàng**.

Cách làm:

- Giữ cùng mảng indegree và danh sách kề.
- Thay `FIFO queue` bằng **min-heap/priority queue**.
- Mỗi lần lấy đỉnh nhỏ nhất từ heap, rồi cập nhật các cung đi ra như cũ.

Trong Java:

```java
Queue<Integer> ready = new PriorityQueue<>();
```

**Lý do tham lam lấy nhỏ nhất là đúng:** Ở một thời điểm, các đỉnh có indegree=0 là **chính xác những đỉnh có thể đứng tiếp theo** trong một topo order của phần còn lại. Để được dãy nhỏ nhất theo từ điển, vị trí hiện tại phải chọn giá trị nhỏ nhất trong số các lựa chọn hợp lệ. Sau khi chọn, giải tương tự trên đồ thị còn lại.

Với ví dụ sáu đỉnh phần 4:

```text
FIFO:
[4,5,2,0,3,1]

Min-heap:
[4,5,0,2,3,1]
```

Ở một thời điểm, 0 và 2 đều đã có indegree=0; min-heap ưu tiên 0 dù 2 được đưa vào tập sẵn sàng trước.

### Chi phí của heap

Mỗi đỉnh vào heap tối đa một lần và được lấy ra tối đa một lần. Mỗi thao tác heap O(log V), mỗi cung vẫn được duyệt một lần. Do đó:

```text
FIFO Kahn:        O(V + E) thời gian
Min-heap Kahn:    O(V + E + V log V) thời gian

Bộ nhớ cả hai:    O(V + E)
```

Có thể viết cận rộng hơn `O((V+E) log V)`, nhưng công thức O(V+E+VlogV) thể hiện rõ rằng **không có một thao tác heap riêng trên từng cung**; ta chỉ thực hiện thao tác heap khi một đỉnh chuyển sang indegree=0.

Min-heap không làm thay đổi **tính tồn tại hay tính duy nhất** của topo order. Nó chỉ chọn một đại diện có thứ tự nhỏ nhất khi có nhiều đáp án.

## 10. Ba biểu diễn đồ thị thường gặp

### 10.1. Danh sách cạnh (edge list)

Input có thể là:

```text
n = 4
edges = [(0,1),(0,2),(1,3),(2,3)]
```

Thuận tiện để đọc input, kiểm tra từng cặp và xây cấu trúc khác. Nhưng nếu cứ quét **toàn bộ danh sách cạnh** để tìm mọi cung từ đỉnh u ở mỗi lần xử lý, có thể tốn O(VE), không còn tuyến tính.

### 10.2. Danh sách kề (adjacency list)

```text
out[0] = [1,2]
out[1] = [3]
out[2] = [3]
out[3] = []
```

Kahn nên dùng biểu diễn này: khi lấy u, duyệt đúng các cung đi ra từ u. Tạo danh sách kề một lần từ danh sách cạnh cho chi phí O(V+E).

### 10.3. Ma trận kề

Ma trận `adj[u][v]` cho biết có cung u→v. Phù hợp với đồ thị nhỏ/dày hoặc cần truy vấn có cung nhanh, nhưng tốn O(V²) bộ nhớ. Nếu dùng ma trận, quét cả hàng để tìm hàng xóm có thể mất O(V) cho mỗi đỉnh.

**Lưu ý về cạnh trùng:** Nếu danh sách đầu vào có hai dòng giống nhau (0,1), đó có thể được hiểu là **hai cung song song** của một đồ thị có hướng đa cung. Chương trình ở phần 13 **giữ nguyên các cung lặp**: mỗi bản sao tăng indegree[1] một lần và khi xử lý 0 thì giảm một lần. Điều kiện thứ tự u trước v không đổi, vì cả hai bản sao cùng áp đặt một ràng buộc thứ tự.

Nếu chọn chuẩn hóa thành đồ thị đơn, có thể loại trùng cung **trước cả hai bước** đếm indegree và xây adjacency. Tuyệt đối không được chỉ khử trùng ở một bước mà giữ ở bước kia; như vậy bộ đếm indegree sẽ không bao giờ khớp số cung thực sự được duyệt.

## 11. Cập nhật bậc vào trên một ví dụ có cạnh song song

Xét:

```text
Cung:
0 -> 1
0 -> 1   (cung thứ hai cùng cặp đỉnh)
1 -> 2

indegree[0] = 0
indegree[1] = 2
indegree[2] = 1
```

Queue ban đầu [0]. Xử lý 0:

```text
Cung 0->1 thứ nhất: indegree[1] 2 -> 1
Cung 0->1 thứ hai:  indegree[1] 1 -> 0
=> bây giờ mới đưa 1 vào queue.
```

Xử lý 1 giảm indegree[2] từ 1 xuống 0, rồi xử lý 2. Thứ tự topo vẫn:

```text
[0,1,2]
```

**Lỗi dễ gặp:** Đếm indegree[1]=2 nhưng khi quét adjacency[0] đã được khử trùng thành chỉ một đỉnh 1, rồi chỉ giảm một lần. Khi đó indegree[1] còn 1, queue rỗng, thuật toán **báo chu trình sai** dù đồ thị không có chu trình.

### Tại sao enqueue khi bậc vào bằng **đúng 0**, không phải nhỏ hơn hoặc bằng 0?

Với dữ liệu được xây nhất quán, bậc vào không bao giờ âm. Đỉnh chỉ được enqueue khi lần giảm cuối cùng làm indegree từ 1 thành 0. Nếu code vô tình giảm nhiều hơn số cung ban đầu, điều kiện `<=0` có thể che lỗi và enqueue trùng. Dùng `==0`, đồng thời giữ bất biến cập nhật đúng mỗi cung một lần.

## 12. Chứng minh tính đúng của Kahn

### 12.1. Bất biến của mảng indegree

Sau khi đã lấy ra một tập đỉnh S:

> Với mỗi đỉnh v chưa xử lý, indegree[v] bằng **số cung từ những đỉnh chưa xử lý tới v**; số cung song song được đếm theo số bản sao nếu input cho phép đa cung.

**Ban đầu:** S rỗng; mảng được đếm theo toàn bộ danh sách cạnh nên bất biến đúng.

**Bước duy trì:** Lấy u khỏi queue. Vì u có indegree=0, không còn cung từ các đỉnh chưa xử lý khác tới u. Ta coi u là đã xử lý, rồi giảm indegree[v] một lần cho **mỗi cung u→v**. Đây đúng là số cung vừa không còn xuất phát từ một đỉnh chưa xử lý. Các đỉnh khác không thay đổi. Vậy bất biến tiếp tục đúng.

**Hệ quả:** Một đỉnh v được enqueue khi và chỉ khi nó không còn tiền nhiệm chưa xử lý, tức có thể đứng tiếp theo trong một thứ tự topo.

### 12.2. Thứ tự sinh ra không vi phạm cung nào

Giả sử thuật toán lấy u rồi về sau lấy v, và có cung u→v. Khi u chưa được lấy, indegree[v] vẫn tính cung này, nên v **không thể** có indegree=0. Do đó v không thể được lấy **trước u**. Khi đã xử lý u, cung đó mới bị giảm khỏi indegree[v].

Vì thế, đối với mọi cung u→v giữa hai đỉnh trong kết quả đầy đủ, u luôn xuất hiện trước v. Nếu xử lý đủ n đỉnh, dãy còn chứa đúng mỗi đỉnh một lần, nên là một topo order hợp lệ.

### 12.3. Nếu queue hết trước khi đủ n đỉnh thì chắc chắn có chu trình

Khi queue rỗng nhưng còn đỉnh chưa xử lý, từ bất biến, mọi đỉnh còn lại có ít nhất một cung đi vào từ một đỉnh chưa xử lý. Chọn một đỉnh bất kỳ rồi liên tục lần ngược theo cung đi vào trong đồ thị còn lại.

Vì tập đỉnh hữu hạn, việc lần ngược vô hạn sẽ lặp một đỉnh, tức tồn tại chu trình có hướng. Vậy đồ thị không phải DAG và không có topo order đầy đủ.

Ngược lại, DAG hữu hạn không rỗng luôn có đỉnh indegree=0; sau khi lấy nó ra, phần còn lại vẫn là DAG, nên lại có đỉnh indegree=0 nếu còn đỉnh. Vì vậy Kahn xử lý được tất cả đỉnh của DAG.

### 12.4. Thuật toán kết thúc

Mỗi vòng lặp lấy ra và đánh dấu thêm đúng một đỉnh chưa xử lý. Một đỉnh chỉ được enqueue khi indegree của nó chuyển tới 0; indegree chỉ giảm và không có cung tự nó trở lại queue sau khi xử lý. Số lần lấy tối đa n. Mỗi adjacency list hữu hạn, nên thuật toán chắc chắn kết thúc.

Tính đúng không phụ thuộc việc lựa chọn FIFO hay min-heap; hai cấu trúc chỉ thay đổi **đỉnh có indegree=0 nào được chọn trước**, không đổi bất biến.

## 13. Chương trình Java 17+ hoàn chỉnh

Chương trình sử dụng **danh sách kề** và hỗ trợ hai chiến lược:

- **FIFO** dùng `ArrayDeque<Integer>`, tổng thời gian O(V+E).
- **LEXICOGRAPHIC** dùng `PriorityQueue<Integer>`, lấy số đỉnh nhỏ nhất trong tập sẵn sàng, tổng thời gian O(V+E+VlogV).

Kết quả là một record:

```text
Result(
    dag,        // true khi có topo order đầy đủ
    order,      // topo order nếu dag, chỉ là prefix nếu có chu trình
    unique,     // true nếu DAG và chỉ có một topo order
    unresolved  // những đỉnh không được xử lý khi có chu trình
)
```

**Thận trọng:** `unresolved` có thể chứa các đỉnh **bị kẹt phía sau chu trình**, không phải tất cả đều nằm trong chu trình.

### Chính sách kiểm tra input

- `vertexCount≥0`; nếu bằng 0, thứ tự rỗng là hợp lệ và duy nhất.
- Mỗi cạnh là một mảng có đúng **hai đầu**; chỉ số đầu/cuối nằm trong 0..n−1.
- Đồ thị là **có hướng**; chỉ thêm cung u→v, không tự thêm v→u.
- Cho phép self-loop và các cung trùng, vì thuật toán có thể xử lý rõ ràng: self-loop sẽ gây chu trình; cung trùng được đếm/giảm cùng số lần.
- Không sửa mảng đầu vào. Mọi bộ đếm indegree được tạo mới trong mỗi lần gọi nên có thể chạy lại với cùng input.

Lưu thành tệp **`KahnIndegreeTopologicalDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;
import java.util.Queue;

public class KahnIndegreeTopologicalDemo {
    enum Strategy {
        FIFO, LEXICOGRAPHIC
    }

    record Result(boolean dag,
                  int[] order,
                  boolean unique,
                  int[] unresolved) {}

    static Result sort(
            int vertexCount, int[][] edges, Strategy strategy) {
        if (vertexCount < 0) {
            throw new IllegalArgumentException(
                    "vertexCount must be nonnegative");
        }
        Objects.requireNonNull(edges, "edges must not be null");
        Objects.requireNonNull(strategy, "strategy must not be null");

        int n = vertexCount;
        List<List<Integer>> outgoing = new ArrayList<>();
        for (int v = 0; v < n; v++) {
            outgoing.add(new ArrayList<>());
        }

        int[] indegree = new int[n];
        for (int[] edge : edges) {
            if (edge == null || edge.length != 2) {
                throw new IllegalArgumentException(
                        "each edge must have two endpoints");
            }
            int u = edge[0];
            int v = edge[1];
            if (u < 0 || u >= n || v < 0 || v >= n) {
                throw new IllegalArgumentException(
                        "vertex index out of range");
            }

            // Co huong: chi them u -> v.
            // Cung trung duoc dem va xu ly tung lan.
            outgoing.get(u).add(v);
            indegree[v]++;
        }

        Queue<Integer> ready =
                strategy == Strategy.FIFO
                        ? new ArrayDeque<>()
                        : new PriorityQueue<>();

        // Duyet chi so tang de co ket qua FIFO xac dinh
        // doi voi cung input co thu tu co dinh.
        for (int v = 0; v < n; v++) {
            if (indegree[v] == 0) {
                ready.add(v);
            }
        }

        int[] all = new int[n];
        boolean[] processed = new boolean[n];
        int count = 0;
        boolean forcedAtEveryStep = true;

        while (!ready.isEmpty()) {
            if (ready.size() > 1) {
                forcedAtEveryStep = false;
            }

            int u = ready.remove();
            processed[u] = true;
            all[count++] = u;

            for (int v : outgoing.get(u)) {
                indegree[v]--;
                if (indegree[v] == 0) {
                    ready.add(v);
                }
            }
        }

        boolean dag = count == n;
        int[] order = Arrays.copyOf(all, count);

        int[] unresolved = new int[n - count];
        int index = 0;
        for (int v = 0; v < n; v++) {
            if (!processed[v]) {
                unresolved[index++] = v;
            }
        }

        return new Result(
                dag, order,
                dag && forcedAtEveryStep,
                unresolved);
    }

    // Kiem tra doc lap dieu kien cua mot TOPO ORDER DAY DU.
    // Khong coi prefix khi co chu trinh la mot dap an dung.
    static boolean validFullOrder(
            int vertexCount, int[][] edges, int[] order) {
        if (order.length != vertexCount) {
            return false;
        }

        int[] position = new int[vertexCount];
        Arrays.fill(position, -1);

        for (int i = 0; i < order.length; i++) {
            int v = order[i];
            if (v < 0 || v >= vertexCount
                    || position[v] != -1) {
                return false;
            }
            position[v] = i;
        }

        for (int[] edge : edges) {
            if (position[edge[0]] >= position[edge[1]]) {
                return false;
            }
        }
        return true;
    }

    static void show(String label, int vertices, int[][] edges) {
        Result fifo = sort(vertices, edges, Strategy.FIFO);
        Result lex = sort(vertices, edges, Strategy.LEXICOGRAPHIC);

        if (fifo.dag() != lex.dag()
                || fifo.unique() != lex.unique()
                || !Arrays.equals(
                        fifo.unresolved(), lex.unresolved())
                || (fifo.dag()
                    && (!validFullOrder(
                              vertices, edges, fifo.order())
                        || !validFullOrder(
                              vertices, edges, lex.order())))) {
            throw new AssertionError(
                    "invalid or inconsistent Kahn results");
        }

        System.out.println(label
                + ": dag=" + fifo.dag()
                + ", fifo=" + Arrays.toString(fifo.order())
                + ", lex=" + Arrays.toString(lex.order())
                + ", unique=" + fifo.unique()
                + ", unresolved="
                + Arrays.toString(fifo.unresolved()));
    }

    public static void main(String[] args) {
        show("Classic DAG", 6, new int[][]{
                {5, 2}, {5, 0}, {4, 0}, {4, 1},
                {2, 3}, {3, 1}
        });

        show("Chain", 5, new int[][]{
                {0, 1}, {1, 2}, {2, 3}, {3, 4}
        });

        show("Diamond", 4, new int[][]{
                {0, 1}, {0, 2}, {1, 3}, {2, 3}
        });

        show("Disconnected", 5, new int[][]{
                {0, 1}, {2, 3}
        });

        show("Parallel edges", 3, new int[][]{
                {0, 1}, {0, 1}, {1, 2}
        });

        show("Simple cycle", 3, new int[][]{
                {0, 1}, {1, 2}, {2, 0}
        });

        show("Cycle downstream", 4, new int[][]{
                {0, 1}, {1, 2}, {2, 1}, {2, 3}
        });

        show("Self-loop", 3, new int[][]{
                {0, 1}, {1, 1}, {1, 2}
        });

        show("No edges", 3, new int[0][]);
        show("Single", 1, new int[0][]);
        show("Empty", 0, new int[0][]);

        show("Two sources", 4, new int[][]{
                {0, 2}, {1, 2}, {2, 3}
        });

        try {
            sort(-1, new int[0][], Strategy.FIFO);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad count: " + ex.getMessage());
        }

        try {
            sort(3, new int[][]{{0, 3}}, Strategy.FIFO);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad endpoint: " + ex.getMessage());
        }

        try {
            sort(2, new int[][]{{0}}, Strategy.FIFO);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Bad shape: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy với **JDK 17 trở lên**:

```bash
javac KahnIndegreeTopologicalDemo.java
java KahnIndegreeTopologicalDemo
```

**Stdout chính xác:**

```text
Classic DAG: dag=true, fifo=[4, 5, 2, 0, 3, 1], lex=[4, 5, 0, 2, 3, 1], unique=false, unresolved=[]
Chain: dag=true, fifo=[0, 1, 2, 3, 4], lex=[0, 1, 2, 3, 4], unique=true, unresolved=[]
Diamond: dag=true, fifo=[0, 1, 2, 3], lex=[0, 1, 2, 3], unique=false, unresolved=[]
Disconnected: dag=true, fifo=[0, 2, 4, 1, 3], lex=[0, 1, 2, 3, 4], unique=false, unresolved=[]
Parallel edges: dag=true, fifo=[0, 1, 2], lex=[0, 1, 2], unique=true, unresolved=[]
Simple cycle: dag=false, fifo=[], lex=[], unique=false, unresolved=[0, 1, 2]
Cycle downstream: dag=false, fifo=[0], lex=[0], unique=false, unresolved=[1, 2, 3]
Self-loop: dag=false, fifo=[0], lex=[0], unique=false, unresolved=[1, 2]
No edges: dag=true, fifo=[0, 1, 2], lex=[0, 1, 2], unique=false, unresolved=[]
Single: dag=true, fifo=[0], lex=[0], unique=true, unresolved=[]
Empty: dag=true, fifo=[], lex=[], unique=true, unresolved=[]
Two sources: dag=true, fifo=[0, 1, 2, 3], lex=[0, 1, 2, 3], unique=false, unresolved=[]
Bad count: vertexCount must be nonnegative
Bad endpoint: vertex index out of range
Bad shape: each edge must have two endpoints
```

### Diễn giải các test quan trọng

**Classic DAG:** FIFO đưa đỉnh 2 vào queue trước đỉnh 0, nên lấy 2 trước 0. Min-heap chọn 0 trước 2 vì 0 nhỏ hơn; cả hai thứ tự đều thỏa mọi cung. Topo order không duy nhất.

**Chain:** Cạnh `0→1→2→3→4` tạo một chuỗi phụ thuộc bắt buộc. Tại mọi bước chỉ có một đỉnh indegree=0, nên `unique=true`.

**Diamond:** 0 phải trước 1 và 2; cả 1 và 2 phải trước 3. Hai đỉnh 1 và 2 không bị ràng buộc thứ tự tương đối nên `unique=false` dù FIFO và heap tình cờ in cùng một dãy.

**Disconnected:** Có hai thành phần 0→1, 2→3 và đỉnh 4 cô lập. FIFO chọn từ hàng đợi theo thời điểm enqueue, cho `[0,2,4,1,3]`; heap luôn lấy nhỏ nhất hiện có, cho `[0,1,2,3,4]`.

**Parallel edges:** Hai cung 0→1 được đếm cả hai lần, rồi cùng bị loại khi xử lý 0. Kết quả vẫn là topo order duy nhất 0,1,2.

**Simple cycle:** Không có đỉnh indegree=0 ban đầu. Queue rỗng, không xử lý được đỉnh nào.

**Cycle downstream:** Xử lý được đỉnh 0 trước khi dừng; 1 và 2 thuộc chu trình, 3 chỉ **bị phụ thuộc vào chu trình**, không nhất thiết thuộc chu trình.

**Self-loop:** Đỉnh 1 có cung tự nối 1→1, nên không thể giải phóng indegree của chính nó. Đỉnh 2 bị chặn bởi đỉnh 1.

**No edges:** Có n=3 đỉnh độc lập. Mọi hoán vị đều hợp lệ, nên topo order **không duy nhất**, dù cả hai chiến lược đều tình cờ chọn `[0,1,2]`.

**Single/Empty:** Đồ thị một đỉnh và đồ thị rỗng có đúng một thứ tự toàn phần hợp lệ theo quy ước, lần lượt [0] và [].

**Two sources:** Đỉnh 0 và 1 đều là nguồn cho đỉnh 2. Có thể chọn 0 hoặc 1 trước; `unique=false`.

**Bad count/endpoint/shape:** Minh họa cách xác thực số đỉnh âm, đỉnh ngoài phạm vi và cạnh không có đúng hai đầu. Đây là **lỗi dữ liệu**, khác với một đồ thị hợp lệ nhưng có chu trình.

## 14. Một số mở rộng thực tế

### 14.1. Lập lịch học các môn tiên quyết

Coi mỗi môn là một đỉnh; nếu phải học A trước B, thêm cung A→B. Kahn trả một thứ tự đăng ký học bảo đảm hoàn thành mọi môn tiên quyết trước môn phụ thuộc.

Nếu queue có nhiều môn, nghĩa là có nhiều lựa chọn môn có thể học tiếp. Đây **không** có nghĩa mọi môn ấy phải học cùng một học kỳ; nếu có giới hạn số môn/học kỳ hoặc chi phí tài nguyên, cần thêm thuật toán lập lịch phù hợp.

Nếu có chu trình tiên quyết, ví dụ A→B→C→A, đề cương không khả thi theo đúng ràng buộc này; không nên dùng một tiền tố đã sắp làm bằng chứng rằng toàn bộ chương trình có thể hoàn thành.

### 14.2. Build dependencies

Nếu gói thư viện L phải build trước ứng dụng A, thêm cung L→A. Kahn tìm thứ tự build hợp lệ. Khi có nhiều đỉnh indegree=0, có thể chạy các tác vụ độc lập song song nếu không có xung đột tài nguyên bên ngoài đồ thị phụ thuộc.

**Cẩn thận khi mô hình hóa:** Topo sort chỉ mô tả ràng buộc phụ thuộc. Nó **không tự xử lý** giới hạn CPU, số tiến trình song song, thời gian tác vụ hay tài nguyên dùng chung. Những yếu tố ấy có thể đòi thuật toán lập lịch bổ sung.

### 14.3. Gắn mức xử lý sớm nhất cho mỗi đỉnh

Với một DAG, có thể dùng thứ tự topo vừa tìm được để tính **độ dài đường đi dài nhất tính theo số cung từ một nguồn bất kỳ**, tương đương mức “lớp phụ thuộc sớm nhất” nếu mỗi cạnh là một đơn vị thời gian:

```text
level[v] = 0 ban đầu cho mọi v

Duyệt u theo topo order:
    for mỗi cung u -> v:
        level[v] = max(level[v], level[u] + 1)
```

Với DAG, mọi tiền nhiệm u của v đã được xử lý trước v, nên kết quả chính xác. Một đỉnh nguồn có level 0, đỉnh chỉ được chạy sau chuỗi ba cung có level ít nhất 3.

**Không dùng công thức như một kết quả hợp lệ nếu topo sort báo chu trình.** Khi ấy không có thứ tự phụ thuộc đầy đủ và khái niệm số lớp tiến triển hữu hạn theo các ràng buộc chu trình không còn đơn giản.

### 14.4. Tìm số cách sắp xếp tô-pô

Biết có nhiều thứ tự không đồng nghĩa dễ **đếm chính xác** số thứ tự. Kahn thông thường chỉ tìm **một** thứ tự, hoặc dùng queue size để nhận biết tính **duy nhất**.

Với n nhỏ, có thể dùng DP theo tập con:

```text
ways[mask] = số cách sắp những đỉnh đã có trong mask

ways[0] = 1

Chọn v chưa ở mask và tất cả tiền nhiệm của v đã ở mask:
    ways[mask | (1 << v)] += ways[mask]
```

Nếu xét được mọi mask và các điều kiện đúng, độ phức tạp tăng theo 2ⁿ (thường thêm thừa số n), không còn tuyến tính theo V+E. Nếu chỉ cần một topo order, không nên dùng phương pháp đắt hơn này.

### 14.5. Xử lý nhiều DAG có cùng các đỉnh

Trong một số ứng dụng, mỗi lần đổi vài cung lại cần sắp xếp tô-pô. Thuật toán Kahn chạy lại từ đầu O(V+E) là lựa chọn đơn giản, dễ kiểm chứng. Có các kỹ thuật **duy trì topological order động**, nhưng cập nhật một cung có thể thay đổi thứ tự của nhiều đỉnh và cần cấu trúc dữ liệu phức tạp hơn.

Chương trình Java ở đây dựng mảng indegree **mới mỗi lần gọi**, không sửa đối tượng đồ thị input. Điều này tránh lỗi khá thường gặp: chạy Kahn lần đầu làm indegree về 0 hết, rồi chạy lần hai trên **mảng đã bị phá hủy** khiến thuật toán ra kết quả không đáng tin.

## 15. Khi nào dùng Kahn và khi nào dùng DFS topo?

Có hai cách cơ bản phổ biến:

| Khía cạnh | Kahn (bậc vào) | DFS topo |
| --- | --- | --- |
| Ý tưởng | Liên tục loại đỉnh có indegree 0 | Đưa đỉnh vào kết quả **sau** khi duyệt hết cung đi ra, rồi đảo thứ tự |
| Phát hiện chu trình | Số đỉnh đã lấy ra **nhỏ hơn n** | Gặp cạnh quay về đỉnh **đang trong ngăn xếp DFS** |
| Cấu trúc chính | Indegree + queue/heap + adjacency | Adjacency + 3 trạng thái hoặc stack DFS |
| Độ phức tạp tuyến tính | O(V+E) với queue | O(V+E) |
| Đặc điểm thuận tiện | Thể hiện rõ công việc hiện đã sẵn sàng | Dễ truy vết chu trình với stack khi cài đặt đúng |
| Hạn chế thường gặp | Không tự trả dãy đỉnh cấu thành chu trình | Đệ quy có thể tràn stack trên đường rất dài nếu không dùng DFS lặp |

**Không dùng DFS kiểu “đánh dấu visited rồi đảo thứ tự” mà quên phát hiện back edge.** Trên đồ thị có chu trình, việc chỉ đảo thứ tự hoàn tất DFS có thể in một dãy trông hợp lý nhưng không thỏa mọi cung. Khi cần một topo order của toàn đồ thị, cả Kahn lẫn DFS đều phải **phát hiện và xử lý chu trình**.

Kahn dễ liên hệ với hàng đợi tác vụ sẵn sàng; DFS thích hợp khi đang có khung duyệt sâu và cần truy vết một chu trình cụ thể. Hai cách đều đúng trên DAG nếu cài đặt đầy đủ.

## 16. Những lỗi dễ gặp

1. **Dùng đồ thị vô hướng thay vì có hướng.** Đổi mỗi cạnh thành hai chiều tạo chu trình độ dài 2 và không biểu diễn đúng tiên quyết.
2. **Đảo hướng cung.** Nếu A phải trước B, phải là A→B, không phải B→A.
3. **Chỉ đếm indegree ban đầu mà không giảm sau khi xử lý.** Các đỉnh phụ thuộc không bao giờ được giải phóng.
4. **Giảm indegree của đỉnh nguồn u thay vì đích v.** Làm sai số tiền nhiệm còn lại của v.
5. **Đưa v vào queue ngay khi lần đầu được một tiền nhiệm xử lý.** Phải chờ **tất cả** cung đi vào còn lại được loại.
6. **Enqueue khi indegree <= 0 thay vì == 0.** Có thể che lỗi đếm thiếu/trùng và thêm đỉnh nhiều lần.
7. **Thêm cùng đỉnh vào queue nhiều lần.** Mỗi đỉnh được enqueue khi indegree chuyển từ 1 xuống 0 hoặc ban đầu bằng 0.
8. **Không kiểm tra số đỉnh đã xử lý.** Trả prefix khi gặp chu trình và tưởng là đáp án đầy đủ.
9. **Kết luận mọi unresolved đều thuộc chu trình.** Có thể gồm đỉnh ở phía sau chu trình.
10. **Không xử lý self-loop.** Cung u→u là chu trình và phải khiến phát hiện không DAG.
11. **Không chuẩn hóa cạnh trùng một cách nhất quán.** Giữ trùng trong đếm nhưng khử ở adjacency khiến indegree sai.
12. **Cho rằng đồ thị không liên thông không có topo order.** Có thể sắp mọi thành phần và các đỉnh cô lập.
13. **Cho rằng mọi DAG chỉ có một topo order.** Khi có hai nguồn cùng lúc, có ít nhất hai thứ tự.
14. **Nhầm FIFO cho kết quả từ điển nhỏ nhất.** FIFO phụ thuộc thời điểm enqueue và thứ tự danh sách kề; cần min-heap nếu bắt buộc nhỏ nhất.
15. **Sử dụng heap nhưng vẫn tuyên bố O(V+E) cho code ấy.** Heap có thêm chi phí O(VlogV).
16. **Sử dụng ArrayList.remove(0) thay cho queue O(1).** Phần tử phía sau bị dịch, có thể mất tuyến tính.
17. **Không đặt đủ mọi nguồn ban đầu vào queue.** Bỏ mất những thành phần/đỉnh độc lập.
18. **Đánh dấu visited quá sớm theo cơ chế BFS thường.** Kahn dùng bậc vào để quyết định sẵn sàng, không phải “đã nhìn thấy hàng xóm”.
19. **Tính độ dài đường đi trên thứ tự chưa xác minh DAG.** Khi có chu trình, thứ tự đầy đủ không tồn tại.
20. **Đọc input có đỉnh 1-based rồi dùng trực tiếp mảng 0-based.** Phải đổi quy ước nhất quán.
21. **Truy cập chỉ số đỉnh ngoài [0,n−1].** Cần kiểm tra trước khi thêm cung.
22. **Coi queue rỗng lúc khởi tạo là lỗi trên đồ thị rỗng.** Với n=0, order=[] là topo order hợp lệ.
23. **Nói n=1 luôn có topo order.** Nếu đỉnh duy nhất có self-loop, có chu trình và không có topo order.
24. **Kiểm tra vị trí của một cung mà không kiểm tra order là hoán vị đủ n đỉnh.** Một dãy thiếu đỉnh có thể thỏa vài so sánh vị trí nhưng không phải topo order.
25. **Đếm sai điều kiện duy nhất khi có chu trình.** Không có full topo order thì không thể báo unique=true.
26. **Nhầm cung song song với một chu trình.** Hai cung u→v cùng chiều không tạo chu trình; một cung ngược v→u mới có thể tạo chu trình.
27. **Dùng ma trận kề nhưng tuyên bố bộ nhớ O(V+E).** Ma trận luôn tốn O(V²).
28. **Quên rằng PQ chỉ thay cách chọn, không thay tính đúng của việc giảm indegree.**
29. **Xem topo order là lịch thực thi tối ưu.** Topo order chỉ bảo đảm quan hệ tiên quyết, chưa xét tài nguyên hay thời gian.
30. **Đánh đồng các số đỉnh với mức độ ưu tiên của bài toán.** Màu/tên/chỉ số chỉ dùng phá hòa nếu đề yêu cầu.
31. **Không chạy lại indegree từ đầu khi tái sử dụng dữ liệu.** Mảng indegree đã bị biến đổi không còn là bậc vào ban đầu.
32. **Coi một queue có hai đỉnh là sai.** Đó là tình huống hoàn toàn bình thường trên DAG có nhiều thứ tự hợp lệ.

## 17. Bài tập tự kiểm tra có đáp án

**Bài 1.** Định nghĩa chính xác một thứ tự tô-pô.

**Đáp án:** Một hoán vị đầy đủ của mọi đỉnh của đồ thị có hướng sao cho với mọi cung u→v, u xuất hiện trước v. Nó tồn tại khi và chỉ khi đồ thị không có chu trình có hướng.

**Bài 2.** Vì sao Kahn lấy một đỉnh indegree=0 ở mỗi bước?

**Đáp án:** Đỉnh đó không còn tiền nhiệm chưa xử lý, nên có thể đứng tiếp theo mà không vi phạm cung nào. Sau khi lấy ra, ta giảm indegree của các đích theo các cung đi ra.

**Bài 3.** Với các cung (0,2),(1,2),(2,3), bậc vào của từng đỉnh 0..3 là gì?

**Đáp án:** `[0,0,2,1]`. Queue ban đầu có 0 và 1; đỉnh 2 chỉ trở thành sẵn sàng sau khi xử lý cả 0 và 1.

**Bài 4.** Với DAG sáu đỉnh ở phần 4, đưa ra một thứ tự tô-pô.

**Đáp án:** `[4,5,2,0,3,1]` hoặc `[4,5,0,2,3,1]` đều hợp lệ. Hãy kiểm tra đủ sáu cung đã cho.

**Bài 5.** Nếu một đồ thị có chu trình 0→1→2→0, Kahn xử lý được bao nhiêu đỉnh?

**Đáp án:** Không đỉnh nào trong ba đỉnh đó nếu đồ thị chỉ chứa chu trình ấy, vì indegree ban đầu của mỗi đỉnh đều bằng 1. Queue rỗng, processed=0<n.

**Bài 6.** Có thể có một đồ thị có chu trình nhưng queue ban đầu không rỗng không?

**Đáp án:** Có, ví dụ 0→1,1→2,2→1,2→3. Ban đầu xử lý 0; sau đó kẹt lại ở chu trình 1↔2.

**Bài 7.** Ở ví dụ trên, unresolved=[1,2,3]. Đỉnh 3 có nhất thiết nằm trên chu trình không?

**Đáp án:** Không. Chỉ 1 và 2 nằm trên chu trình; 3 bị chặn vì phụ thuộc vào 2.

**Bài 8.** Nếu có hai đỉnh indegree=0 tại một thời điểm trong DAG, thứ tự topo có duy nhất không?

**Đáp án:** Không. Có thể chọn một trong hai đỉnh trước; cả hai thứ tự đều có thể hoàn thành vì chúng không ràng buộc nhau.

**Bài 9.** Nếu tại mọi bước Kahn luôn có đúng một đỉnh sẵn sàng và xử lý hết n đỉnh, kết luận gì?

**Đáp án:** DAG có **duy nhất một topo order**, vì mọi vị trí trong thứ tự đều bị ép bởi các cung.

**Bài 10.** FIFO và priority queue có bắt buộc cho cùng kết quả không?

**Đáp án:** Không. FIFO chọn theo thời điểm enqueue; min-heap chọn chỉ số nhỏ nhất đang sẵn sàng. Chúng có thể cho hai topo order khác nhau nhưng đều hợp lệ.

**Bài 11.** Độ phức tạp của Kahn dùng danh sách kề và ArrayDeque là gì?

**Đáp án:** Thời gian O(V+E), bộ nhớ O(V+E). Mỗi đỉnh được xử lý tối đa một lần, mỗi cung bị giảm indegree đúng một lần.

**Bài 12.** Nếu thay FIFO bằng PriorityQueue để lấy thứ tự nhỏ nhất theo từ điển, thời gian tăng thành bao nhiêu?

**Đáp án:** O(V+E+VlogV), vì có O(V) thao tác thêm/lấy trong heap, mỗi thao tác O(log V).

**Bài 13.** Hai cung trùng (0,1),(0,1) có tạo chu trình không?

**Đáp án:** Không, nếu cùng hướng và không có đường quay lại 0. Chúng tăng indegree[1] hai lần và khi xử lý 0 phải giảm hai lần; thứ tự 0 trước 1 vẫn hợp lệ.

**Bài 14.** Có n=0 đỉnh và không có cung. Trả lời thế nào?

**Đáp án:** Theo quy ước, `[]` là topo order hợp lệ và duy nhất của đồ thị rỗng. Thuật toán xử lý 0 đỉnh và kết luận dag=true.

**Bài 15.** Một đỉnh duy nhất 0 có cung 0→0. Có topo order không?

**Đáp án:** Không. Đó là chu trình độ dài 1; indegree[0]=1, Kahn không thể lấy nó khỏi queue.

**Bài 16.** Với graph không có cạnh và n=3, có bao nhiêu topo order?

**Đáp án:** Mọi hoán vị của ba đỉnh đều hợp lệ, có 3!=6 thứ tự. Kahn FIFO chỉ trả **một** trong số đó; cờ unique=false.

**Bài 17.** Cho order=[0,2,1,3] với các cung (0,1),(0,2),(1,3),(2,3). Order có hợp lệ không?

**Đáp án:** Có. 0 đứng trước cả 1 và 2, và cả hai đứng trước 3; không có cung giữa 1 và 2.

**Bài 18.** Làm thế nào tự kiểm tra một output của thuật toán topo?

**Đáp án:** Xác minh order chứa đúng mỗi đỉnh một lần; tạo position[v] cho mọi đỉnh; kiểm tra mọi cung (u,v) có position[u]<position[v]. Nếu graph có chu trình, không coi prefix là output thành công.

**Bài 19.** Tại sao không nên dùng DFS thăm bình thường rồi đảo thứ tự nếu không kiểm tra chu trình?

**Đáp án:** Trên đồ thị có chu trình, thứ tự hoàn tất DFS được đảo có thể vẫn được tạo ra, nhưng không thể thỏa hết mọi cung. Phải có phát hiện cạnh tới đỉnh đang trên ngăn xếp hoặc dùng Kahn đếm processed.

**Bài 20.** Muốn tính lớp phụ thuộc sớm nhất của mỗi đỉnh trong DAG sau khi topo sort, làm gì?

**Đáp án:** Khởi tạo level[v]=0 và duyệt u theo topo order; với mỗi cung u→v, cập nhật `level[v]=max(level[v],level[u]+1)`. Vì mọi tiền nhiệm đã được xử lý trước, các giá trị lan truyền đúng.

## Ghi nhớ

**Kahn** là thuật toán sắp xếp tô-pô **bằng bậc vào** cho **đồ thị có hướng**. Đếm `indegree[v]` từ mọi cung u→v; đưa toàn bộ đỉnh indegree=0 vào queue. Mỗi lần lấy u ra, ghi u vào thứ tự, và với mọi cung u→v **giảm indegree[v]**; chỉ khi indegree[v] chuyển về 0 mới thêm v vào queue.

Nếu đã lấy **đúng n đỉnh**, kết quả là một topo order hợp lệ và đồ thị là DAG. Nếu queue hết khi còn đỉnh, **có chu trình**, và phần đã xử lý **chỉ là một prefix**. Với danh sách kề và FIFO, thời gian và bộ nhớ là **O(V+E)**. Với min-heap, có thể tìm topo order **nhỏ nhất theo từ điển** ở thời gian O(V+E+VlogV). Trên DAG, nếu tại **mọi bước chỉ có một lựa chọn sẵn sàng**, thứ tự topo là **duy nhất**; nếu có lúc nhiều lựa chọn, sẽ có nhiều thứ tự hợp lệ. Hiểu đúng **bậc vào động và điều kiện xử lý hết n đỉnh** là chìa khóa để dùng thuật toán an toàn.
