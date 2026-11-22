# Ánh xạ giả mã sang kiểu dữ liệu và giao diện hàm

**Ánh xạ giả mã sang chương trình** không chỉ là đổi `FOR` thành `for`, `IF` thành `if`. Người lập trình phải quyết định những khái niệm trừu tượng trong thuật toán — “mảng đã sắp”, “vị trí”, “đoạn”, “đỉnh”, “không tìm thấy”, “đường đi”, “đáp án” — được biểu diễn bằng **kiểu dữ liệu nào**, các hàm nhận/trả **giá trị gì**, các ràng buộc đầu vào được kiểm tra ở đâu, liệu hàm có được sửa input không, và phải chứng minh/kiểm thử thế nào.

Bài thuộc **Cài đặt và kiểm thử** trong Computer Science Algorithms, tập trung vào **“Ánh xạ giả mã sang kiểu dữ liệu và giao diện hàm”**. Tài liệu xây dựng quy trình từ đặc tả tới Java 17+, giải thích cách chọn `int[]`, `long`, `List`, `record`, `OptionalInt`, quy ước đoạn nửa mở, tính bất biến, lỗi chỉ số và overflow. Hai ví dụ chạy xuyên suốt là **binary search lower/upper bound** và **BFS đường đi ngắn nhất trên đồ thị không trọng số**. Mỗi ví dụ có chữ ký hàm, tiền/hậu điều kiện, chứng minh, chương trình Java độc lập, stdout và phép kiểm thử bằng oracle khác thuật toán.

## 1. Từ giả mã tới hợp đồng hàm

Cho giả mã:

~~~text
LOWER_BOUND(A, x):
    l = 0
    r = length(A)
    while l < r:
        m = floor((l+r)/2)
        if A[m] < x:
            l = m+1
        else:
            r = m
    return l
~~~

Trước khi dịch, cần trả lời:

1. `A` là mảng truy cập ngẫu nhiên hay luồng chỉ đọc tuần tự?
2. `A` đã sắp tăng **không giảm** hay hàm phải tự sắp?
3. Các vị trí đánh số từ 0 hay 1?
4. `r` là chỉ số phần tử hay **biên phải không bao gồm**?
5. Khi x không xuất hiện, trả kết quả gì?
6. Có giá trị lặp lại không? Khi có, muốn phần tử đầu hay bất kỳ phần tử nào?
7. Mảng rỗng có hợp lệ không?
8. Có được thay đổi mảng input không?
9. Độ phức tạp mong đợi là O(log n) hay O(n)?
10. Input sai là trường hợp hợp lệ không có kết quả hay là lỗi hợp đồng?

Chỉ sau khi đã định nghĩa các câu trả lời, việc dịch từng bước sang Java mới không mơ hồ.

### Năm lớp cài đặt

| Lớp | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Biểu diễn | Dữ liệu được lưu dưới dạng nào? | `int[]` cho dãy, danh sách kề cho đồ thị |
| API | Nhận những tham số gì, trả kiểu nào? | `int lowerBound(int[],int)` |
| Hợp đồng | Tiền điều kiện, hậu điều kiện, ngoại lệ, quyền sửa input? | Mảng đã sort, không mutate |
| Bất biến | Điều nào đúng sau mỗi bước? | Đáp án nằm trong [lo,hi] |
| Kiểm chứng | Làm sao phát hiện lệch khỏi giả mã? | Oracle quét tuyến tính/Floyd–Warshall |

**Một chương trình biên dịch được chưa chứng minh nó biểu diễn đúng bài toán.**

## 2. Chọn kiểu dữ liệu theo miền và thao tác

| Khái niệm | Java 17+ | Lưu ý |
| --- | --- | --- |
| Chỉ số mảng, số đỉnh thông thường | `int` | Chỉ số hợp lệ 0..n−1 |
| Số nguyên một phần tử | `int` hoặc `long` | Xét miền đầu vào |
| Tổng nhiều phần tử int | `long` | Tránh overflow int |
| Tổng vượt long | `BigInteger` | Đúng số học nguyên tùy ý |
| Dãy số cố định | `int[]`, `long[]` | Truy cập O(1), mutable |
| Dãy động | `ArrayList<T>` | Boxing với `Integer` và chi phí chèn/xóa |
| Hàng đợi FIFO | `ArrayDeque<T>` | Phù hợp BFS |
| Heap ưu tiên | `PriorityQueue<T>` | Không thay được FIFO khi thuật toán cần FIFO |
| Tập có mặt | `HashSet<T>` | Trung bình O(1), không cam kết thứ tự duyệt |
| Bảng ánh xạ | `HashMap<K,V>` | Phân biệt key không tồn tại |
| Kết quả nhiều trường | `record` hoặc lớp riêng | Có tên trường, giảm lẫn vị trí |
| Có thể không có một chỉ số | `OptionalInt` | Phân biệt “vắng mặt” với index=0 |
| Khoảng chỉ số | `record IndexRange` | Bảo vệ ràng buộc l≤r |
| Đồ thị thưa | `List<List<Integer>>` | Danh sách kề O(V+E) |
| Trạng thái thuật toán | Mảng, record/lớp chuyên biệt | Không lộ sentinel nhầm nghĩa |

**Không tối đa hóa số lượng class** nếu chỉ cần một số nguyên, nhưng cũng không ép một kết quả nhiều ý nghĩa thành `int[][]` với những hàng đánh số bí ẩn.

## 3. Chỉ số 0-based và đoạn nửa mở [l,r)

Trong mã này mọi mảng có chỉ số phần tử `0..n−1`, còn đoạn [l,r) hợp lệ nếu:

\[
0\le l\le r\le n.
\]

Đoạn chứa l nhưng không chứa r; độ dài là r−l.

| n=6, dãy [1,2,2,2,5,9] | Diễn giải |
| --- | --- |
| [0,6) | Toàn bộ sáu phần tử |
| [1,4) | Ba phần tử bằng 2 |
| [3,3) | Đoạn rỗng |
| [6,6) | Đoạn rỗng cuối mảng |
| [0,7) | Không hợp lệ vì r>n |
| [4,2) | Không hợp lệ vì l>r |

Đặc biệt, **n là biên phải hợp lệ nhưng không phải chỉ số phần tử hợp lệ**. Trong binary search, hi=n có thể xuất hiện và kết quả trả n có thể đúng; nhưng truy cập `a[n]` là lỗi.

Nếu đề bài dùng đoạn đóng [l,r], cần chuyển sang [l,r+1) một cách nhất quán và đảm bảo r<n. Không đổi quy ước giữa code, output và oracle.

### Record cho khoảng

`record IndexRange(int fromInclusive,int toExclusive)` có thể kiểm `from≥0`, `to≥from` và cung cấp method `length()`. Nhưng record không biết n của mảng cụ thể, nên hàm dùng nó vẫn phải kiểm `to≤n`.

Đây là ví dụ về việc **đặt ràng buộc ở đúng tầng**: kiểm tính hợp lệ độc lập dữ liệu trong constructor, kiểm phụ thuộc dữ liệu tại method tiêu thụ.

## 4. Tiền điều kiện, hậu điều kiện, bất biến

**Tiền điều kiện:** những gì caller phải đảm bảo trước khi gọi hàm. Lower bound yêu cầu mảng **đã sắp không giảm**.

**Hậu điều kiện:** điều được đảm bảo khi trả về thành công. Với p=lowerBound(a,key):

\[
0\le p\le n,\quad
a[i]<key\ (i<p),\quad
a[i]\ge key\ (i\ge p).
\]

Vậy p là chỉ số đầu tiên có giá trị ≥key, hoặc n nếu không có.

**Bất biến vòng lặp:** sau từng vòng của binary search, đáp án vẫn thuộc đoạn ứng viên [lo,hi]; mỗi bước giảm hi−lo nên vòng lặp kết thúc.

### Có nên kiểm “đã sort” ở mỗi lời gọi?

Kiểm đủ từng cặp a[i]≤a[i+1] tốn O(n), làm mất độ phức tạp O(log n). Một API hiệu quả có thể ghi **precondition** và tin vào caller. Nếu muốn tự bảo đảm, cung cấp `sortedCopy(input)` O(n log n) trước khi tìm kiếm nhiều lần. Không lặng lẽ thêm quét O(n) vào một hàm được hứa O(log n).

## 5. Vị trí chèn khác với phần tử đã tìm thấy

Giả sử:

`sorted=[1,2,2,2,5,9]`.

**Lower bound**: chỉ số đầu có giá trị ≥key.

- key=2 → 1.
- key=3 → 4, **dù 3 không xuất hiện**.
- key=−5 → 0.
- key=99 → 6=n.

**Upper bound**: chỉ số đầu có giá trị >key.

- key=2 → 4.
- key=3 → 4.
- key=99 → 6.

**Equal range** của key=2 là [1,4), gồm ba phần tử.

**First occurrence** phải báo “không có phần tử” khi key=3 hoặc 99. Cần một hợp đồng khác:

`OptionalInt firstOccurrence(int[] sorted,int key)`.

Nếu không có key, trả `OptionalInt.empty()`. Nếu có key ở index0, trả `OptionalInt.of(0)`. Không lấy 0 làm sentinel vì 0 là chỉ số hợp lệ. Sentinel −1 có thể dùng trong API đơn giản nếu ghi rõ, nhưng `OptionalInt` làm ý nghĩa vắng mặt hiển nhiên hơn.

### So sánh đúng là một phần của đặc tả

Trong lower bound điều kiện là `a[mid]<target`. Nếu đổi thành `a[mid]<=target` thì kết quả trở thành **upper bound**. Một ký tự nhỏ có thể thay toàn bộ ý nghĩa API khi có giá trị trùng.

Mid nên viết:

`int mid=lo+(hi-lo)/2;`

thay vì `(lo+hi)/2` để tránh khả năng cộng hai chỉ số lớn gây tràn int.

## 6. Bất biến và chứng minh lower bound

Bắt đầu lo=0, hi=n. Xét vị trí p đầu tiên mà a[p]≥target, hoặc p=n.

- Ban đầu p∈[0,n].
- Nếu a[mid]<target, mọi vị trí i≤mid đều có a[i]<target vì mảng không giảm. Vậy p≥mid+1, gán lo=mid+1 không loại đáp án.
- Nếu a[mid]≥target, đáp án p≤mid, gán hi=mid không loại đáp án.
- Khi lo<hi, mid nằm trong [lo,hi−1], nên đoạn ứng viên giảm.
- Khi lo=hi, p=lo và hàm trả đúng vị trí.

Không cần mảng có các phần tử khác nhau. Các phần tử bằng nhau chính là nơi lower và upper bound thể hiện sự khác biệt.

## 7. Ownership và đột biến dữ liệu

Giả mã “SORT(A)” không nói rõ liệu A có bị sửa. Java `Arrays.sort(int[])` **sort tại chỗ**, đổi thứ tự input. Nếu caller cần giữ bản gốc, cài:

~~~java
static int[] sortedCopy(int[] input) {
    Objects.requireNonNull(input);
    int[] copy = input.clone();
    Arrays.sort(copy);
    return copy;
}
~~~

Với `input=[9,2,2,1,5,2]`, `sortedCopy(input)` trả `[1,2,2,2,5,9]` nhưng input vẫn y nguyên.

`int[] alias=input;` **không phải copy**: hai biến trỏ vào cùng mảng. Với danh sách lồng nhau, sao chép chỉ danh sách ngoài là **shallow copy**; các danh sách trong vẫn có thể sửa nếu chưa được bảo vệ.

Chữ ký hàm nên ghi rõ **đọc input**, **mutate input**, hay **trả snapshot**. API trả dữ liệu mutable mà không nêu quyền sở hữu là nguồn gây lỗi khó tìm, đặc biệt khi test liên tiếp hoặc nhiều luồng dùng chung.

## 8. Mã số cho kết quả rỗng khác lỗi input

| Tình huống | Là lỗi không? | Kết quả/hành vi hợp lý |
| --- | --- | --- |
| Tìm key không tồn tại trong mảng đã sort | Không | `OptionalInt.empty()` |
| LowerBound lớn hơn mọi phần tử | Không | n |
| Tổng đoạn hợp lệ [n,n) | Không | 0 |
| BFS không đến được đỉnh đích | Không | Khoảng cách empty, đường đi [] |
| BFS tới chính source | Không | Khoảng cách 0, đường đi [source] |
| Chỉ số source=n | Có | `IllegalArgumentException` |
| Đoạn [l,r) có l>r | Có | `IllegalArgumentException` |
| Cạnh trỏ tới vertex ngoài 0..n−1 | Có | `IllegalArgumentException` |
| Input array null | Có | `Objects.requireNonNull` |

Không chuyển mọi thứ về 0: 0 có thể là tổng rỗng hợp lệ, chỉ số hợp lệ và khoảng cách từ source tới chính nó.

## 9. Chọn long cho tổng, không chỉ nhìn kiểu phần tử

Với:

`[2147483647,2147483647]`

tổng chính xác là:

\[
2\times2{,}147{,}483{,}647
=4{,}294{,}967{,}294,
\]

lớn hơn `Integer.MAX_VALUE`. Vì vậy dùng accumulator `long`:

~~~java
long sum = 0L;
for (int x : values) sum += x;
~~~

Nếu tính tích hai `int` rồi gán sang long, cần ép kiểu **trước** phép nhân:

`long product=(long)a*b;`

không phải `long product=a*b;` vì phép nhân int có thể tràn trước khi được gán.

`long` cũng có giới hạn. Nếu dữ liệu có thể vượt 64 bit, dùng `BigInteger` hoặc chính sách kiểm overflow rõ ràng. Với Java, `Math.addExact` và `Math.multiplyExact` phát hiện tràn và ném ngoại lệ, nhưng phải xử lý phù hợp hợp đồng.

## 10. Ánh xạ giả mã BFS sang cấu trúc graph

Giả mã:

~~~text
BFS(G, source):
    for each vertex v:
        distance[v] = unknown
        parent[v] = none
    distance[source] = 0
    Q.pushBack(source)
    while Q not empty:
        v = Q.popFront()
        for u in neighbors(v):
            if distance[u] is unknown:
                distance[u] = distance[v]+1
                parent[u] = v
                Q.pushBack(u)
    return distance, parent
~~~

Các quyết định triển khai phải được làm rõ:

- Đỉnh là `int`, đánh số 0..V−1.
- Graph trong ví dụ **có hướng, không trọng số**.
- Input builder nhận `int[][] edges`, mỗi hàng đúng hai endpoint.
- Graph thuật toán dùng `List<List<Integer>>`, tức danh sách kề.
- Hàng xóm được giữ **đúng thứ tự các cạnh nguồn**.
- Được phép có self-loop và duplicate edge.
- BFS dùng `ArrayDeque<Integer>` làm **FIFO queue**.
- `distance[v]=−1` nội bộ biểu thị chưa được thăm/không reachable.
- `parent[v]=−1` với source hoặc unreachable.
- Bên ngoài cung cấp `OptionalInt distanceTo(v)`, `List<Integer> pathTo(v)`.

### Vì sao chọn adjacency list?

Với V đỉnh và E cạnh, danh sách kề cần O(V+E) bộ nhớ; khi BFS xử lý một đỉnh, chỉ duyệt những neighbor thật sự của nó. Ma trận kề V×V cần O(V²) bộ nhớ và có thể phải quét V cột để tìm neighbor. Danh sách cạnh thuần O(E) nhưng nếu mỗi lần tìm neighbor lại duyệt toàn bộ E cạnh, thời gian BFS có thể tăng đáng kể.

### Có hướng không tự thành vô hướng

Nếu có cạnh `0→1`, graph có hướng không tự có cạnh `1→0`. Với đồ thị vô hướng, builder phải thêm cả hai chiều hoặc input đã liệt kê hai chiều đầy đủ. Không được thay đổi ngữ nghĩa loại đồ thị khi chuyển giả mã sang code.

## 11. BfsResult: kết quả nhiều trường có ý nghĩa

Chữ ký:

`BfsResult bfs(List<List<Integer>> adjacency,int source)`.

Record chứa:

- `source`: đỉnh xuất phát.
- `distance[]`: khoảng cách số cạnh, hoặc −1 khi unreachable.
- `parent[]`: một cây đường đi ngắn nhất theo thứ tự BFS.

Public API:

`OptionalInt distanceTo(int target)`

`List<Integer> pathTo(int target)`

**Không dùng `int[][]` không giải thích** với hàng 0 là distance, hàng 1 là parent. Dùng record có tên trường giúp IDE và người đọc hiểu đúng nghĩa.

### Đường đi hợp lệ

Nếu target tới được, `pathTo(target)` trả danh sách đỉnh từ source tới target, **bao gồm hai đầu**, với:

\[
\operatorname{path.size()}=\operatorname{distance}[target]+1.
\]

Nếu không tới được, trả `List.of()`. Với target=source, trả `[source]`, không rỗng.

Parent chain của một đỉnh reachable giảm distance đi 1 ở mỗi cạnh; vì thế kết thúc tại source, không thể chứa chu trình.

### Phòng vệ chống mutate kết quả

Record chứa mảng vẫn có dữ liệu mutable. Mã minh họa clone `distance` và `parent` trong constructor, đồng thời clone ở accessor; vì vậy:

~~~java
int[] copy = result.distance();
copy[0] = 999;
~~~

không sửa giá trị mà `result.distanceTo(0)` nhìn thấy. `pathTo` trả `List.copyOf` không thể chỉnh sửa từ caller.

**Chi phí:** lấy cả mảng qua accessor là O(V) vì sao chép; lấy một khoảng cách qua `distanceTo` O(1). Có thể thiết kế API khác cho ứng dụng hiệu năng cao, nhưng phải công bố rõ vấn đề ownership.

## 12. Tiền điều kiện và hậu điều kiện BFS

Tiền điều kiện:

1. Graph không null.
2. Mọi danh sách kề khác null.
3. Mọi endpoint hợp lệ 0..V−1; không có neighbor null.
4. Source hợp lệ.
5. Graph không bị sửa đồng thời trong khi BFS chạy.

BFS trên graph rỗng không có source hợp lệ, nên `bfs(empty,0)` phải báo lỗi. Nhưng builder `directedGraph(0,new int[0][2])` hoàn toàn có thể trả một graph rỗng hợp lệ.

Hậu điều kiện:

- `distance[source]=0`.
- Mọi đỉnh reachable có distance bằng số cạnh tối thiểu.
- Đỉnh unreachable có distance/parent nội bộ bằng −1.
- Đỉnh reachable khác source có parent là một đỉnh có cạnh dẫn tới nó và distance(parent)=distance(v)−1.
- Đường đi trả ra chỉ dùng cạnh thật và có số cạnh bằng distance.

### Chứng minh BFS đúng

FIFO queue khiến các đỉnh được thăm theo các **lớp khoảng cách**. Source thuộc lớp0; mọi neighbor mới của một đỉnh lớp d sẽ thuộc lớp d+1. Nếu có đường đi ngắn hơn tới một đỉnh, đỉnh đó đã phải được phát hiện từ một lớp trước. Vì vậy gán distance **lần đầu khi enqueue** là tối ưu.

Đánh dấu ngay lúc enqueue, không đợi lúc dequeue, ngăn cùng một đỉnh được đưa vào queue nhiều lần qua các cạnh khác nhau.

Với adjacency list, mỗi đỉnh được dequeue tối đa một lần và mỗi cạnh được xem tối đa một lần, cho thời gian O(V+E), bộ nhớ phụ O(V). Nếu validate toàn bộ adjacency trước khi chạy, phần kiểm tra cũng O(V+E).

## 13. Ví dụ BFS có đường đi không duy nhất

Graph gồm sáu đỉnh và các cạnh có hướng:

~~~text
0 -> 1
0 -> 2
1 -> 3
2 -> 3
3 -> 4
5 -> 5
~~~

Từ source=0:

`distance=[0,1,1,2,3,-1]`.

`parent=[-1,0,0,1,3,-1]`.

- Từ 0 tới 4 có đường đi `[0,1,3,4]`, dài ba cạnh.
- Đỉnh 5 không reachable, distanceTo(5)=empty, pathTo(5)=[].
- Đường đi tới source 0 là `[0]`, dài 0 cạnh.

Graph cũng có đường ngắn nhất `[0,2,3,4]`. Nếu đổi thứ tự neighbor của 0, BFS có thể chọn parent[3]=2 thay vì 1; **cả hai hợp lệ**. Không nên viết test khẳng định mảng parent phải giống một oracle duy nhất khi không có yêu cầu về tie-breaking.

Từ source=5 chỉ đi được tới chính 5 vì có self-loop, nên distance là `[-1,-1,-1,-1,-1,0]` và pathTo(5)=[5].

## 14. Kiểm thử độc lập thay vì chép thuật toán làm oracle

### Binary search

Oracle dùng **quét tuyến tính**:

~~~text
linearLower(a, key):
    i=0
    while i<n and a[i]<key:
        i++
    return i

linearUpper(a, key):
    i=0
    while i<n and a[i]<=key:
        i++
    return i
~~~

Hai oracle không dùng vòng chia đôi, giảm rủi ro cùng mắc lỗi mid hay off-by-one. Trong test, so `lowerBound`/`upperBound` với oracle trên những mảng **đã sort**.

### Range sum

Oracle cộng từng phần tử [l,r), dùng long. Không chỉ so hai phiên bản cùng công thức dùng chung hàm trợ giúp nếu đang kiểm tra chính hàm trợ giúp ấy.

### BFS

Oracle trên graph nhỏ dùng **Floyd–Warshall**:

1. d[i][i]=0, các cặp khác INF.
2. Với cạnh u→v, gán `d[u][v]=min(d[u][v],1)`.
3. Với mọi k,i,j, thử đường i→k→j.
4. So hàng d[source][v] với distance của BFS.

**Lưu ý tự vòng:** self-loop v→v phải giữ khoảng cách 0; vì thế **min** rất quan trọng. Gán cứng d[v][v]=1 là lỗi oracle, không phải lỗi BFS.

Đối với đường đi, kiểm:

- Nếu unreachable, path rỗng.
- Nếu reachable, đầu path=source, cuối path=target.
- Mỗi cặp đỉnh liên tiếp là cạnh hợp lệ.
- Số cạnh trên path bằng distance tối ưu.

Không bắt buộc một parent array cụ thể khi nhiều shortest paths đồng độ dài.

## 15. Bảng ánh xạ giả mã → Java API

| Ý nghĩa | Giao diện Java | Hợp đồng |
| --- | --- | --- |
| Tạo bản sao đã sắp | `int[] sortedCopy(int[])` | Không sửa input |
| Vị trí đầu có giá trị ≥key | `int lowerBound(int[],int)` | Input đã sort; trả 0..n |
| Vị trí đầu có giá trị >key | `int upperBound(int[],int)` | Input đã sort; trả 0..n |
| Dải các giá trị bằng key | `IndexRange equalRange(int[],int)` | [lower,upper) |
| Vị trí xuất hiện đầu tiên | `OptionalInt firstOccurrence(int[],int)` | Rỗng khi không có |
| Tổng một đoạn | `long rangeSum(int[],IndexRange)` | Dãy không sửa, r≤n |
| Tạo đồ thị có hướng | `List<List<Integer>> directedGraph(int,int[][])` | Input cạnh hợp lệ, snapshot |
| Khoảng cách BFS và cha | `BfsResult bfs(List<List<Integer>>,int)` | Source hợp lệ, graph chỉ đọc |
| Khoảng cách tới một đỉnh | `OptionalInt distanceTo(int)` | Unreachable → empty |
| Một đường đi ngắn nhất | `List<Integer> pathTo(int)` | Unreachable → [] |

Những chữ ký này là một quyết định thiết kế **cụ thể**, không phải cách duy nhất. Một dự án có thể dùng sealed result types, wrapper graph hoặc generic types. Điều cần giữ là **ngữ nghĩa rõ và kiểm thử được**.

## 16. Java 17+ — chương trình đầy đủ

Lưu đoạn code dưới đây với tên **`PseudocodeToJavaDemo.java`**. Chương trình chỉ dùng JDK, có thể chạy bằng Java 17 trở lên. Các hàm thuật toán không đọc `System.in` hoặc in `System.out`; tầng `main` mới định dạng kết quả. Nhờ đó test có thể gọi trực tiếp từng hàm.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.OptionalInt;
import java.util.Random;

public class PseudocodeToJavaDemo {

    record IndexRange(int fromInclusive, int toExclusive) {
        IndexRange {
            if (fromInclusive < 0 || toExclusive < fromInclusive)
                throw new IllegalArgumentException("Invalid range");
        }

        int length() {
            return toExclusive - fromInclusive;
        }

        String compact() {
            return "[" + fromInclusive + ","
                    + toExclusive + ")";
        }
    }

    static void checkVertex(int vertex, int count) {
        if (vertex < 0 || vertex >= count)
            throw new IllegalArgumentException("Invalid vertex");
    }

    static int[] sortedCopy(int[] input) {
        Objects.requireNonNull(input, "input");
        int[] copy = input.clone();
        Arrays.sort(copy);
        return copy;
    }

    // Precondition: sorted is nondecreasing.
    static int lowerBound(int[] sorted, int target) {
        Objects.requireNonNull(sorted, "sorted");
        int lo = 0, hi = sorted.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (sorted[mid] < target) lo = mid + 1;
            else hi = mid;
        }
        return lo;
    }

    static int upperBound(int[] sorted, int target) {
        Objects.requireNonNull(sorted, "sorted");
        int lo = 0, hi = sorted.length;
        while (lo < hi) {
            int mid = lo + (hi - lo) / 2;
            if (sorted[mid] <= target) lo = mid + 1;
            else hi = mid;
        }
        return lo;
    }

    static IndexRange equalRange(int[] sorted, int target) {
        return new IndexRange(
                lowerBound(sorted, target),
                upperBound(sorted, target));
    }

    static OptionalInt firstOccurrence(int[] sorted, int target) {
        int index = lowerBound(sorted, target);
        if (index < sorted.length
                && sorted[index] == target)
            return OptionalInt.of(index);
        return OptionalInt.empty();
    }

    static String show(OptionalInt value) {
        return value.isPresent()
                ? Integer.toString(value.getAsInt()) : "empty";
    }

    static long rangeSum(int[] values, IndexRange range) {
        Objects.requireNonNull(values, "values");
        Objects.requireNonNull(range, "range");
        if (range.toExclusive() > values.length)
            throw new IllegalArgumentException(
                    "Range exceeds array length");
        long sum = 0L;
        for (int i = range.fromInclusive();
                i < range.toExclusive(); i++)
            sum += values[i];
        return sum;
    }

    // Create directed adjacency lists and freeze both levels.
    static List<List<Integer>> directedGraph(
            int vertexCount, int[][] edges) {
        if (vertexCount < 0)
            throw new IllegalArgumentException(
                    "Negative vertex count");
        Objects.requireNonNull(edges, "edges");

        List<List<Integer>> mutable =
                new ArrayList<>(vertexCount);
        for (int v = 0; v < vertexCount; v++)
            mutable.add(new ArrayList<>());

        for (int[] edge : edges) {
            if (edge == null || edge.length != 2)
                throw new IllegalArgumentException("Bad edge");
            checkVertex(edge[0], vertexCount);
            checkVertex(edge[1], vertexCount);
            mutable.get(edge[0]).add(edge[1]);
        }

        List<List<Integer>> frozen =
                new ArrayList<>(vertexCount);
        for (List<Integer> neighbors : mutable)
            frozen.add(List.copyOf(neighbors));
        return List.copyOf(frozen);
    }

    // Defensive copies prevent the caller changing BFS results.
    record BfsResult(int source, int[] distance, int[] parent) {
        BfsResult {
            Objects.requireNonNull(distance, "distance");
            Objects.requireNonNull(parent, "parent");
            if (distance.length != parent.length)
                throw new IllegalArgumentException("Bad result arrays");
            distance = distance.clone();
            parent = parent.clone();
        }

        @Override
        public int[] distance() {
            return distance.clone();
        }

        @Override
        public int[] parent() {
            return parent.clone();
        }

        OptionalInt distanceTo(int target) {
            checkVertex(target, distance.length);
            return distance[target] < 0
                    ? OptionalInt.empty()
                    : OptionalInt.of(distance[target]);
        }

        List<Integer> pathTo(int target) {
            checkVertex(target, distance.length);
            if (distance[target] < 0)
                return List.of();

            List<Integer> reversed = new ArrayList<>();
            for (int v = target; v != -1; v = parent[v])
                reversed.add(v);
            Collections.reverse(reversed);
            return List.copyOf(reversed);
        }
    }

    static BfsResult bfs(
            List<List<Integer>> adjacency, int source) {
        Objects.requireNonNull(adjacency, "adjacency");
        int n = adjacency.size();
        checkVertex(source, n);

        for (List<Integer> neighbors : adjacency) {
            if (neighbors == null)
                throw new IllegalArgumentException(
                        "Null adjacency row");
            for (Integer u : neighbors) {
                if (u == null)
                    throw new IllegalArgumentException(
                            "Null neighbor");
                checkVertex(u, n);
            }
        }

        int[] distance = new int[n];
        int[] parent = new int[n];
        Arrays.fill(distance, -1);
        Arrays.fill(parent, -1);

        ArrayDeque<Integer> queue = new ArrayDeque<>();
        distance[source] = 0;
        queue.addLast(source);

        while (!queue.isEmpty()) {
            int v = queue.removeFirst();
            for (int u : adjacency.get(v)) {
                if (distance[u] >= 0) continue;
                distance[u] = distance[v] + 1;
                parent[u] = v;
                queue.addLast(u);
            }
        }
        return new BfsResult(source, distance, parent);
    }

    static int edgeCount(List<List<Integer>> graph) {
        int result = 0;
        for (List<Integer> neighbors : graph)
            result += neighbors.size();
        return result;
    }

    // Independent linear oracles for binary search.
    static int linearLower(int[] sorted, int target) {
        int i = 0;
        while (i < sorted.length && sorted[i] < target)
            i++;
        return i;
    }

    static int linearUpper(int[] sorted, int target) {
        int i = 0;
        while (i < sorted.length && sorted[i] <= target)
            i++;
        return i;
    }

    static long bruteSum(int[] a, int l, int r) {
        long result = 0L;
        for (int i = l; i < r; i++)
            result += a[i];
        return result;
    }

    static void randomSearchTests(Random random) {
        for (int trial = 0; trial < 700; trial++) {
            int n = random.nextInt(101);
            int[] data = new int[n];
            for (int i = 0; i < n; i++)
                data[i] = random.nextInt(501) - 250;
            int[] backup = data.clone();
            int[] sorted = sortedCopy(data);
            if (!Arrays.equals(data, backup))
                throw new AssertionError(
                        "sortedCopy changed input");

            for (int query = 0; query < 25; query++) {
                int target = random.nextInt(601) - 300;
                int lo = lowerBound(sorted, target);
                int hi = upperBound(sorted, target);
                if (lo != linearLower(sorted, target)
                        || hi != linearUpper(sorted, target))
                    throw new AssertionError(
                            "Binary search mismatch");

                OptionalInt found = firstOccurrence(
                        sorted, target);
                boolean exists = lo < n
                        && sorted[lo] == target;
                if (found.isPresent() != exists
                        || (exists && found.getAsInt() != lo))
                    throw new AssertionError(
                            "First occurrence mismatch");

                IndexRange equal = equalRange(sorted, target);
                if (equal.fromInclusive() != lo
                        || equal.toExclusive() != hi)
                    throw new AssertionError(
                            "Equal range mismatch");

                int l = random.nextInt(n + 1);
                int r = l + random.nextInt(n - l + 1);
                if (rangeSum(sorted, new IndexRange(l, r))
                        != bruteSum(sorted, l, r))
                    throw new AssertionError(
                            "Range sum mismatch");
            }
        }
        System.out.println(
                "searchRandom=PASS (700 datasets, 17500 queries)");
    }

    // Independent Floyd-Warshall oracle on small graphs.
    static int[][] floydDistances(int n, int[][] edges) {
        final int INF = 1_000_000;
        int[][] d = new int[n][n];
        for (int i = 0; i < n; i++) {
            Arrays.fill(d[i], INF);
            d[i][i] = 0;
        }
        for (int[] edge : edges) {
            int u = edge[0], v = edge[1];
            // Preserve d[v][v]=0 if the edge is a self-loop.
            d[u][v] = Math.min(d[u][v], 1);
        }
        for (int k = 0; k < n; k++)
            for (int i = 0; i < n; i++)
                for (int j = 0; j < n; j++)
                    d[i][j] = Math.min(
                            d[i][j], d[i][k] + d[k][j]);
        return d;
    }

    static void randomGraphTests(Random random) {
        final int INF = 1_000_000;
        for (int trial = 0; trial < 350; trial++) {
            int n = 1 + random.nextInt(30);
            int m = random.nextInt(100);
            int[][] edges = new int[m][2];
            for (int i = 0; i < m; i++) {
                edges[i][0] = random.nextInt(n);
                edges[i][1] = random.nextInt(n);
            }

            List<List<Integer>> graph = directedGraph(n, edges);
            int source = random.nextInt(n);
            BfsResult result = bfs(graph, source);
            int[][] oracle = floydDistances(n, edges);

            for (int v = 0; v < n; v++) {
                int expected = oracle[source][v] == INF
                        ? -1 : oracle[source][v];
                if (result.distanceTo(v).orElse(-1) != expected)
                    throw new AssertionError(
                            "BFS distance mismatch");

                List<Integer> path = result.pathTo(v);
                if (expected < 0) {
                    if (!path.isEmpty())
                        throw new AssertionError(
                                "Unreachable has path");
                    continue;
                }

                if (path.size() != expected + 1
                        || path.get(0) != source
                        || path.get(path.size() - 1) != v)
                    throw new AssertionError(
                            "Wrong path endpoints or length");

                for (int i = 1; i < path.size(); i++) {
                    if (!graph.get(path.get(i - 1))
                            .contains(path.get(i)))
                        throw new AssertionError(
                                "Path uses missing edge");
                }

                if (v != source) {
                    int predecessor = result.parent()[v];
                    if (predecessor < 0
                            || !graph.get(predecessor).contains(v)
                            || result.distanceTo(predecessor)
                                    .orElse(-1) != expected - 1)
                        throw new AssertionError(
                                "Wrong parent relation");
                }
            }
        }
        System.out.println(
                "graphRandom=PASS (350 graphs)");
    }

    public static void main(String[] args) {
        int[] original = {9, 2, 2, 1, 5, 2};
        int[] sorted = sortedCopy(original);
        System.out.println("original="
                + Arrays.toString(original));
        System.out.println("sorted="
                + Arrays.toString(sorted));

        for (int key : new int[]{2, 3, -5, 99}) {
            IndexRange range = equalRange(sorted, key);
            System.out.println("key=" + key
                    + " lower=" + range.fromInclusive()
                    + " upper=" + range.toExclusive()
                    + " range=" + range.compact()
                    + " count=" + range.length()
                    + " first="
                    + show(firstOccurrence(sorted, key)));
        }

        int[] empty = new int[0];
        System.out.println("empty lower="
                + lowerBound(empty, 7)
                + " range=" + equalRange(empty, 7).compact()
                + " sum=" + rangeSum(
                        empty, new IndexRange(0, 0)));

        System.out.println("range="
                + new IndexRange(1, 4).compact()
                + " sum=" + rangeSum(
                        sorted, new IndexRange(1, 4)));
        System.out.println("wide sum=" + rangeSum(
                new int[]{Integer.MAX_VALUE, Integer.MAX_VALUE},
                new IndexRange(0, 2)));

        int[][] edges = {
            {0, 1}, {0, 2}, {1, 3},
            {2, 3}, {3, 4}, {5, 5}
        };
        List<List<Integer>> graph = directedGraph(6, edges);
        BfsResult result = bfs(graph, 0);
        System.out.println("graph vertices=" + graph.size()
                + " edges=" + edgeCount(graph));
        System.out.println("bfs source=0 distance="
                + Arrays.toString(result.distance())
                + " parent=" + Arrays.toString(result.parent()));
        System.out.println("bfs to4 distance="
                + show(result.distanceTo(4))
                + " path=" + result.pathTo(4));
        System.out.println("bfs to5 distance="
                + show(result.distanceTo(5))
                + " path=" + result.pathTo(5));

        BfsResult from5 = bfs(graph, 5);
        System.out.println("bfs from5 distance="
                + Arrays.toString(from5.distance())
                + " pathTo5=" + from5.pathTo(5));

        int[] snapshot = result.distance();
        snapshot[0] = 999;
        System.out.println("snapshot distance0="
                + show(result.distanceTo(0)));

        try {
            rangeSum(sorted, new IndexRange(0, 7));
            throw new AssertionError("Expected range error");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidRange=rejected");
        }

        try {
            bfs(graph, 6);
            throw new AssertionError("Expected vertex error");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidVertex=rejected");
        }

        try {
            directedGraph(2, new int[][]{{0, 2}});
            throw new AssertionError("Expected edge error");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalidEdge=rejected");
        }

        Random random = new Random(5352026L);
        randomSearchTests(random);
        randomGraphTests(random);
    }
}
~~~

### Lệnh biên dịch và chạy

~~~bash
javac -encoding UTF-8 PseudocodeToJavaDemo.java
java PseudocodeToJavaDemo
~~~

### Đầu ra dự kiến

~~~text
original=[9, 2, 2, 1, 5, 2]
sorted=[1, 2, 2, 2, 5, 9]
key=2 lower=1 upper=4 range=[1,4) count=3 first=1
key=3 lower=4 upper=4 range=[4,4) count=0 first=empty
key=-5 lower=0 upper=0 range=[0,0) count=0 first=empty
key=99 lower=6 upper=6 range=[6,6) count=0 first=empty
empty lower=0 range=[0,0) sum=0
range=[1,4) sum=6
wide sum=4294967294
graph vertices=6 edges=6
bfs source=0 distance=[0, 1, 1, 2, 3, -1] parent=[-1, 0, 0, 1, 3, -1]
bfs to4 distance=3 path=[0, 1, 3, 4]
bfs to5 distance=empty path=[]
bfs from5 distance=[-1, -1, -1, -1, -1, 0] pathTo5=[5]
snapshot distance0=0
invalidRange=rejected
invalidVertex=rejected
invalidEdge=rejected
searchRandom=PASS (700 datasets, 17500 queries)
graphRandom=PASS (350 graphs)
~~~

### Ý nghĩa kết quả

- **original/sorted:** input giữ [9,2,2,1,5,2], bản sao đã sort là [1,2,2,2,5,9].
- **key=2:** lower=1, upper=4, equalRange dài 3 và first=1.
- **key=3:** vị trí chèn là 4, nhưng first=empty vì key không có.
- **key=−5/99:** vị trí chèn nằm đầu/cuối mảng, không phải lỗi.
- **empty:** input rỗng và đoạn [0,0) đều hợp lệ.
- **range:** tổng ba số 2 ở [1,4) là 6.
- **wide sum:** hai `Integer.MAX_VALUE` cho tổng 4.294.967.294 khi dùng long.
- **graph:** sáu đỉnh, sáu cạnh có hướng, bao gồm self-loop 5→5.
- **bfs source=0:** khoảng cách [0,1,1,2,3,−1], parent [−1,0,0,1,3,−1].
- **bfs to4:** ba cạnh, path [0,1,3,4]. **bfs to5:** unreachable nên distance empty và path [].
- **bfs from5:** chỉ tới được đỉnh5, distanceTo(5)=0, pathTo(5)=[5].
- **snapshot:** sửa mảng clone không phá record nội bộ, nên distance0 vẫn 0.
- **invalidRange/invalidVertex/invalidEdge:** phân biệt rõ input sai với kết quả hợp lệ rỗng.
- **searchRandom:** 700 dataset, mỗi dataset 25 target và 25 đoạn, so binary search/tổng với oracle quét trực tiếp.
- **graphRandom:** 350 graph, so BFS với Floyd–Warshall và kiểm cạnh, độ dài, hai đầu mỗi path.

**Lưu ý:** các dòng PASS chứng minh cài đặt phù hợp trên những input đã thử, không tự thay thế lập luận bất biến và các tiền/hậu điều kiện.

## 17. Bảng truy vết đặc tả ↔ kiểu ↔ test

| Ý trong giả mã | Hợp đồng Java | Test phải có |
| --- | --- | --- |
| A đã sắp | `int[] sorted` là tiền điều kiện | Trùng, âm, cực trị; input không được lặng lẽ sort |
| Vị trí đầu ≥x | `lowerBound` trả 0..n | Oracle linearLower |
| Vị trí đầu >x | `upperBound` trả 0..n | Oracle linearUpper |
| X không tồn tại | `OptionalInt.empty()` | Key absent ở đầu/giữa/cuối |
| Đoạn [l,r) | `IndexRange`, `r≤n` | l=r, r=n, l>r, r>n |
| Tổng có thể lớn | `long` | Hai Integer.MAX_VALUE |
| Graph có hướng | Chỉ thêm from→to | Không tạo chiều ngược |
| BFS khoảng cách tối thiểu | FIFO queue, dist[] | Floyd oracle |
| Unreachable | Internal −1, API Optional | Đỉnh cô lập |
| Nhiều đường đi ngắn nhất | Path hợp lệ, không ép parent duy nhất | Graph hình thoi |
| Không sửa kết quả | Defensive copies | Sửa snapshot rồi đọc lại |

Bảng truy vết này làm rõ vì sao mỗi case test tồn tại. Nếu thay đổi một hợp đồng, phải xem lại cả **dạng trả về**, **mã thuật toán** và **oracle**.

## 18. Độ phức tạp phải bao gồm cả chi phí API

| Method | Thời gian | Bộ nhớ bổ sung |
| --- | --- | --- |
| `sortedCopy` | O(n log n) | O(n) do clone, chưa tính stack |
| `lowerBound/upperBound` | O(log n) | O(1) |
| `equalRange/firstOccurrence` | O(log n) | O(1) |
| `rangeSum` | O(r−l) | O(1) |
| `directedGraph` | O(V+E) | O(V+E) |
| `bfs` | O(V+E) | O(V) ngoài graph |
| `distanceTo` | O(1) | O(1) |
| `pathTo` | O(L), L là số đỉnh trong path | O(L) |
| `BfsResult.distance()` | O(V) vì clone | O(V) |
| `floydDistances` | O(V³) | O(V²) |

`rangeSum` trong ví dụ cố ý là thuật toán tuyến tính để minh họa kiểu trả về và hợp đồng đoạn; nếu cần nhiều truy vấn tổng, có thể dùng prefix sums, Fenwick tree hoặc segment tree phù hợp.

`floydDistances` cố ý chậm hơn BFS; nó là **oracle độc lập trên input nhỏ**, không phải đề xuất dùng Floyd để giải BFS quy mô lớn.

## 19. Những điều cần kiểm tra trong Java trước khi tối ưu

### Kiểu số và overflow

Giả mã dùng số nguyên toán học có thể không nêu giới hạn. Java `int` và `long` đều có giới hạn cố định. Không có phép chuyển kiểu sau một phép toán đã tràn để khôi phục đáp án đúng.

### Quyền sửa dữ liệu

`Arrays.sort(a)` làm thay a. `a.clone()` tạo bản sao riêng. `List.copyOf` chỉ làm bất biến cấu trúc list và không deep-copy object mutable bên trong. Nếu input là object mutable, phải có ownership và snapshot policy.

### Null và empty

Mảng null khác mảng rỗng. Graph n=0 là một dữ liệu hợp lệ để biểu diễn, nhưng không có source hợp lệ để bắt đầu BFS. Đầu vào thiếu trường quan trọng nên có exception hoặc kiểu lỗi rõ.

### Trạng thái “không có”

Index0, distance0 và tổng0 có thể là giá trị thật. Không lấy chúng làm mã lỗi. Dùng Optional hoặc sentinel nằm ngoài miền hợp lệ với hợp đồng nhất quán.

### Data structure đúng thao tác

BFS cần FIFO. `ArrayDeque.removeFirst()` có O(1) amortized; `ArrayList.remove(0)` dịch các phần tử O(n). `PriorityQueue.poll()` chọn theo priority, không giữ FIFO; thay vào BFS sẽ biến đổi giả mã.

### Tie breaking và tính đúng

Nếu có nhiều đường đi ngắn nhất, BFS có thể trả nhiều parent tree hợp lệ. Chỉ so khoảng cách và tính hợp lệ của path, trừ khi đề yêu cầu rõ cách phá hòa.

## 20. Checklist test ranh giới

**Mảng:** rỗng; một phần tử; tất cả phần tử bằng nhau; số âm; min/max int; key nhỏ/lớn hơn mọi phần tử; nhiều duplicate; đoạn [0,n), [i,i), [n,n); input không bị mutate.

**Đồ thị:** một đỉnh; không cạnh; đỉnh cô lập; self-loop; duplicate edge; chu trình; nhiều shortest paths; cạnh một chiều; source unreachable tới một số đỉnh; source sai; neighbor ngoài miền; pathTo(source) có đúng một đỉnh.

**Kết quả:** sửa mảng clone và xác nhận BfsResult không đổi; invalid range và invalid edge ném exception; key không có cho OptionalInt.empty chứ không trả “giá trị 0 giả”.

**Property-based testing:** sinh input ngẫu nhiên có seed cố định để tái lập lỗi; nếu test fail, in seed, n và các input tối thiểu hóa được. Có thể thêm phép biến đổi **metamorphic** như thêm một đỉnh cô lập không làm thay khoảng cách giữa các đỉnh cũ, hoặc thêm bản sao của cạnh cũ không làm giảm khoảng cách ngắn nhất.

## 21. Lỗi thường gặp khi ánh xạ giả mã

1. Dịch từng câu lệnh mà không xác định tiền điều kiện.
2. Biến một vị trí chèn thành kết quả “đã tìm thấy”.
3. Dùng chỉ số 0 làm sentinel vắng mặt.
4. Nhầm 0-based và 1-based.
5. Dùng đoạn đóng [l,r] nhưng lặp i<r.
6. Dùng đoạn nửa mở nhưng vẫn truy cập a[r].
7. Lấy `(lo+hi)/2` khi hai biên có thể overflow.
8. Đổi `<` thành `<=` trong lower bound.
9. Không test duplicate keys.
10. Tin rằng Java `Arrays.sort` không sửa input.
11. Viết `int[] alias=input` rồi tưởng đã copy.
12. Dùng int cho tổng có thể vượt 32 bit.
13. Nhân `int*int` rồi mới gán long.
14. Dùng comparator `a-b` với int cực trị gây overflow.
15. Tạo record chứa array nhưng trả accessor mảng nội bộ.
16. Gọi shallow copy là deep copy.
17. Dùng null và empty giống nhau.
18. Dùng một `int[][]` không có tên trường cho kết quả nhiều ý nghĩa.
19. Đưa graph vô hướng vào builder có hướng mà không nói rõ.
20. Không validate endpoint của cạnh.
21. Dùng PriorityQueue thay ArrayDeque cho BFS.
22. Đánh dấu visited khi dequeue, đưa một đỉnh vào queue nhiều lần.
23. Dùng distance=0 cho unreachable.
24. Path tới source trả [].
25. Path tới đỉnh unreachable lại trả [target].
26. Kiểm một parent array duy nhất khi có nhiều shortest paths.
27. Dùng cùng thuật toán để tạo expected output và gọi đó là oracle độc lập.
28. Gán self-loop u→u thành d[u][u]=1 trong Floyd.
29. Không thử n=0, n=1 hoặc r=n.
30. Chỉ test “không ném exception” mà không đối chiếu hậu điều kiện.
31. Chỉ đo thời gian hàm core mà quên chi phí clone và chuyển đổi dữ liệu.
32. Lẫn lộn lỗi hợp đồng với kết quả hợp lệ không tồn tại.

## 22. Bài tập có lời giải

**Bài 1.** Vì sao không chỉ đổi cú pháp giả mã? **Đáp án:** cần xác định kiểu, hợp đồng, bất biến và ngữ nghĩa trả về.

**Bài 2.** Tiền điều kiện của lowerBound? **Đáp án:** mảng đã sort không giảm.

**Bài 3.** LowerBound trả giá trị thuộc đoạn nào? **Đáp án:** [0,n], **có thể bằng n**.

**Bài 4.** Với [1,2,2,2,5,9], lowerBound(2)? **Đáp án:** 1.

**Bài 5.** UpperBound(2)? **Đáp án:** 4.

**Bài 6.** EqualRange(2)? **Đáp án:** [1,4).

**Bài 7.** Số lần xuất hiện của key2? **Đáp án:** 4−1=3.

**Bài 8.** LowerBound(3) mặc dù không có 3? **Đáp án:** 4, vị trí chèn.

**Bài 9.** FirstOccurrence(3)? **Đáp án:** OptionalInt.empty().

**Bài 10.** LowerBound(−5)? **Đáp án:** 0.

**Bài 11.** LowerBound(99)? **Đáp án:** 6.

**Bài 12.** Mảng rỗng lowerBound(7)? **Đáp án:** 0.

**Bài 13.** Vì sao 0 không phải sentinel tìm kiếm tốt? **Đáp án:** 0 là index thật hợp lệ.

**Bài 14.** Mid an toàn hơn nên viết thế nào? **Đáp án:** `lo+(hi-lo)/2`.

**Bài 15.** Đoạn [2,5) có mấy phần tử? **Đáp án:** 3.

**Bài 16.** [n,n) có hợp lệ? **Đáp án:** có, đoạn rỗng cuối.

**Bài 17.** [4,2) có hợp lệ? **Đáp án:** không.

**Bài 18.** Arrays.sort(a) có thay a? **Đáp án:** có, sort tại chỗ.

**Bài 19.** Làm sao giữ input chưa sort? **Đáp án:** clone rồi sort bản sao.

**Bài 20.** `int[] b=a` là clone không? **Đáp án:** không, chỉ copy tham chiếu.

**Bài 21.** Tổng hai Integer.MAX_VALUE bằng gì? **Đáp án:** 4294967294, cần long.

**Bài 22.** Nhân int theo miền long như thế nào? **Đáp án:** `(long)a*b`.

**Bài 23.** Dùng kiểu gì cho BFS queue? **Đáp án:** ArrayDeque FIFO.

**Bài 24.** V=6, source=6 có hợp lệ không? **Đáp án:** không.

**Bài 25.** Cạnh 0→1 có tự có 1→0? **Đáp án:** không trong graph có hướng.

**Bài 26.** Khoảng cách source tới chính nó? **Đáp án:** 0.

**Bài 27.** Distance nội bộ cho unreachable? **Đáp án:** −1 theo hợp đồng demo.

**Bài 28.** distanceTo(unreachable) trả gì? **Đáp án:** OptionalInt.empty.

**Bài 29.** pathTo(source) trả gì? **Đáp án:** [source].

**Bài 30.** pathTo(unreachable) trả gì? **Đáp án:** [].

**Bài 31.** Đồ thị có nhiều shortest paths thì parent có duy nhất không? **Đáp án:** không.

**Bài 32.** Trong graph mẫu, distance từ 0 tới 4? **Đáp án:** 3.

**Bài 33.** Một đường đi từ 0 tới 4? **Đáp án:** [0,1,3,4].

**Bài 34.** Từ 0 đến 5 có path? **Đáp án:** không.

**Bài 35.** Vì sao cần clone mảng trong BfsResult? **Đáp án:** caller không thể sửa trạng thái nội bộ.

**Bài 36.** Lấy cả distance[] bằng accessor có chi phí gì? **Đáp án:** O(V) do clone.

**Bài 37.** distanceTo(v) sau khi BFS chạy? **Đáp án:** O(1).

**Bài 38.** BFS dùng danh sách kề tốn bao nhiêu? **Đáp án:** O(V+E).

**Bài 39.** Floyd–Warshall tốn bao nhiêu? **Đáp án:** O(V³).

**Bài 40.** Self-loop v→v làm khoảng cách v đến v thành 1? **Đáp án:** không, vẫn 0.

**Bài 41.** Khi kiểm BFS cần so parent đúng từng vị trí với Floyd? **Đáp án:** không; Floyd kiểm khoảng cách, còn path kiểm tính hợp lệ.

**Bài 42.** Not found và bad input có giống nhau không? **Đáp án:** không; not found hợp lệ, bad input vi phạm hợp đồng.

**Bài 43.** Vì sao nên tách thuật toán khỏi System.in/out? **Đáp án:** dễ gọi trực tiếp và kiểm với oracle.

**Bài 44.** 350 graph random PASS có chứng minh mọi input đúng? **Đáp án:** không; test bổ trợ chứng minh bất biến.

## 23. Checklist trước khi giao mã

1. Đã hiểu nguyên văn mục tiêu và điều kiện của giả mã?
2. Input/output và trạng thái trung gian có kiểu rõ?
3. Chỉ số 0-based hay 1-based đã thống nhất?
4. Khoảng là [l,r) hay [l,r]?
5. Mọi hàm có tiền/hậu điều kiện?
6. Có mô tả tình huống “không tìm thấy”?
7. Kết quả không tồn tại có dùng Optional/sentinel không nhập nhằng?
8. Lỗi input có khác kết quả hợp lệ rỗng?
9. Đã kiểm overflow của sum, product và mid?
10. Có định nghĩa quyền sửa input, clone hay in-place?
11. Có kiểm list snapshot/record array mutable?
12. Độ phức tạp có tính cả API và validation?
13. Binary search có đúng quy tắc lower/upper?
14. Có test duplicate, key ngoài miền và mảng rỗng?
15. Graph có quy ước hướng cạnh, self-loop và duplicate?
16. BFS có dùng FIFO, đánh dấu visited khi enqueue?
17. Unreachable và source self có kết quả đúng?
18. Có test nhiều đường đi ngắn nhất mà không áp một parent duy nhất?
19. Có oracle quét tuyến tính cho lower bound?
20. Có oracle Floyd độc lập trên graph nhỏ?
21. Có test endpoint của đường đi và mọi cạnh liên tiếp?
22. Có test source/index/range không hợp lệ?
23. Có kiểm result object không bị sửa qua accessor?
24. Có tách parse, algorithm core, result và format output?
25. Có đo hiệu năng trên kích thước thực tế?
26. Có hiểu rằng test hữu hạn không thay thế chứng minh?

**Kết luận:** chuyển giả mã thành Java đúng nghĩa là ánh xạ **dữ liệu → kiểu → giao diện → hợp đồng → bất biến → kiểm thử**. Với binary search, cần phân biệt **vị trí chèn** và **phần tử tồn tại**; với BFS, phải định nghĩa rõ graph, source, khoảng cách, parent và path. `IndexRange`, `OptionalInt`, `BfsResult`, kiểu `long` và defensive copies giải quyết nhiều nhập nhằng thường gặp. Oracle độc lập và trường hợp biên xác nhận rằng phần cài đặt vẫn mang đúng ý nghĩa của giả mã ban đầu.
