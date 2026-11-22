# Trạng thái dùng lại, dữ liệu đầu vào bị sửa và khả năng gọi nhiều lần

Một thuật toán có thể cho đáp án đúng khi chạy **một lần**, nhưng lại sai khi dùng **cùng một đối tượng để gọi lần thứ hai**, khi người gọi **chỉnh sửa mảng đầu vào**, hoặc khi **hai luồng gọi đồng thời**. Đây là nhóm lỗi rất phổ biến trong cài đặt thuật toán: trạng thái `visited` không reset, bộ đệm dùng lại chứa dữ liệu cũ, cache không gắn với phiên bản input, đối tượng giữ tham chiếu tới mảng của người gọi, thao tác sort âm thầm thay đổi input, hoặc một hàm trả về chính mảng nội bộ để caller tùy ý sửa.

Bài Knowledge thuộc nhóm **Cài đặt và kiểm thử** của **Computer Science Algorithms**, với trọng tâm **trạng thái dùng lại, dữ liệu đầu vào bị sửa và khả năng gọi nhiều lần**. Người học sẽ hiểu:
- Phân biệt **trạng thái của một lần gọi**, trạng thái **của đối tượng**, trạng thái **static/toàn cục**, **cache** và trạng thái thuộc **dữ liệu đầu vào**.
- Cách quản lý **aliasing**, **shallow copy**, **deep copy**, **snapshot bất biến** và hợp đồng **in-place**.
- Tại sao các hàm DFS/BFS, DP, DSU, prefix sum, memoization có thể trả sai sau khi được gọi lại hoặc khi input thay đổi.
- Phân biệt **repeatability (gọi nhiều lần)**, **reentrancy (lời gọi chồng lấn)**, **thread safety** và **idempotency**; đây không phải bốn từ đồng nghĩa.
- Thiết kế **bộ kiểm thử có chủ đích**, không chỉ thử một trường hợp: gọi lặp, đổi thứ tự lời gọi, sửa input trước/sau khi xây đối tượng, sửa kết quả trả về, xen kẽ nhiều instance, gọi song song, kiểm tra nguồn dữ liệu không bị tác động, kiểm tra biên và so với oracle độc lập.

Bài có một chương trình **Java 17 chạy độc lập**, so sánh hai lỗi điển hình với cách sửa, rồi kiểm thử toàn bộ **33.867 đồ thị vô hướng nhỏ** (kể cả self-loop), tổng cộng **135.468 lời gọi lặp** và **33.864 tình huống chỉnh sửa ma trận đầu vào sau khi tạo bản chụp**. Các kết quả thuật toán được đối chiếu với một **oracle DSU độc lập**. Ví dụ được giải thích theo hợp đồng API, không khuyến khích cố tình làm sai input ngoài contract của thư viện.

## 1. Trước khi viết hàm, xác định hợp đồng trạng thái

Hãy đặt bốn câu hỏi:

1. **Input do ai sở hữu?** Hàm được phép sửa dữ liệu truyền vào không?
2. **Kết quả có phụ thuộc lịch sử lời gọi trước không?** Cùng input và cùng điều kiện phải cho cùng kết quả chứ?
3. **Input thay đổi sau khi tạo đối tượng thì điều gì phải xảy ra?** Đối tượng đại diện một **snapshot cố định** hay một **live view** đang thay đổi?
4. **Có thể gọi đồng thời không?** Nếu nhiều thread gọi cùng instance, có trạng thái mutable chia sẻ không?

Ví dụ contract dễ hiểu cho một bộ phân tích đồ thị:

> Tạo `SafeGraph` từ một ma trận kề vô hướng. Constructor chụp **bản sao sâu** của dữ liệu tại thời điểm khởi tạo. `components()` không thay đổi ma trận gốc và có thể gọi bao nhiêu lần cũng được, mỗi lần trả số thành phần của **bản chụp đã lưu**. Người gọi sửa ma trận gốc sau khi xây đối tượng không làm thay đổi kết quả của đối tượng cũ. Các lời gọi `components()` đồng thời trên cùng `SafeGraph` được phép vì mỗi lời gọi tạo bộ đệm tạm riêng.

Đây là một hợp đồng rõ ràng. Một hợp đồng khác — chẳng hạn `MutableGraph.addEdge/removeEdge` và `components()` phản ánh phiên bản **hiện tại** — cũng hợp lệ, nhưng phải quản lý **cập nhật + vô hiệu hóa cache + đồng bộ**. Lỗi nảy sinh khi code làm một kiểu mà người gọi hiểu kiểu kia.

### Bảng chọn hợp đồng

| Mô hình | Ý nghĩa | Điều người dùng có thể mong đợi |
| --- | --- | --- |
| Hàm thuần (*pure*) | Không thay đổi trạng thái quan sát được và phụ thuộc chỉ vào đối số | Cùng input bất biến ⇒ cùng output |
| In-place | Chủ động thay đổi cấu trúc được truyền vào | Tên/API phải nói rõ và test mutation |
| Snapshot | Sao chép thông tin cần thiết khi xây đối tượng | Caller sửa input cũ ⇒ kết quả snapshot giữ nguyên |
| Live view | Tham chiếu dữ liệu caller đang sở hữu | Kết quả có thể thay đổi; cần quy tắc về sửa đồng thời |
| Instance có scratch | Tái sử dụng bộ đệm trong một instance | Reset đủ mỗi lần, kiểm thread safety |
| Cached/memoized | Dùng lại kết quả đã tính | Key/version phải phân biệt các input hợp lệ |
| Static/global state | Trạng thái chung mọi instance | Phải kiểm test order, isolation, concurrency |

**Đầu vào cùng object không có nghĩa dữ liệu không đổi.** Ngược lại, hai mảng khác object nhưng có nội dung giống nhau có thể được xem là cùng input theo hợp đồng so sánh **bằng giá trị**. Phải chọn rõ cách định nghĩa “cùng đầu vào”.

## 2. Phân biệt state cục bộ, state của instance và state dùng chung

### 2.1. State cục bộ của mỗi lần gọi

Một hàm BFS có thể cấp phát `boolean[] visited = new boolean[n]` ở **bên trong** hàm. Mảng này là của lời gọi hiện tại, mỗi lần gọi có state độc lập:

~~~java
int countComponents() {
    boolean[] visited = new boolean[n]; // moi loi goi mot mang moi
    // BFS/DFS...
}
~~~

Ưu điểm: dễ chứng minh **không rò state giữa các lần gọi** và an toàn hơn khi nhiều thread cùng đọc dữ liệu bất biến. Nhược điểm: tạo bộ đệm mới mỗi lần, tăng allocation khi truy vấn liên tục trên đồ thị lớn.

### 2.2. State lưu trong đối tượng

~~~java
class ComponentCounter {
    boolean[] visited;
    int total;
    // countComponents() su dung visited va total
}
~~~

Nếu `visited` không được reset, lần gọi hai có thể thấy tất cả đỉnh đã thăm và trả **0 thành phần**. Nếu `total` là field mà không đặt về 0, lần gọi hai lại có thể bị **cộng dồn** thành phần sai.

Với state trong instance, cần mô tả vòng đời:
- Khởi tạo một lần trong constructor, rồi chỉ đọc;
- Reset hoàn toàn tại đầu lời gọi;
- Tái dùng có đồng bộ;
- Hoặc từ chối tái dùng bằng một hợp đồng **single-use** rõ ràng.

### 2.3. State static/toàn cục

Một `static boolean[] visited`, `static Map<Key,Value> memo`, `static int answer` hoặc singleton mutable sẽ được chia sẻ **giữa các instance**. Một test chạy riêng có thể pass, nhưng khi test suite chạy nhiều ca liên tiếp, ca sau nhận dữ liệu cũ.

Static **constant bất biến** thường ổn; static **mutable** cần lifecycle, isolation và đồng bộ rất cẩn thận. Không lấy `static` làm giải pháp “tiết kiệm tạo array” rồi bỏ qua test nhiều lần.

### 2.4. Cache không phải dữ liệu gốc

Cache là một **trạng thái dẫn xuất**: prefix sums, DP table, memoized transitions, distances, số thành phần, sorted index... Nó chỉ đúng với **input và cấu hình mà nó được tính từ đó**. Nếu dữ liệu đổi, các giá trị cache có thể **stale**, dù bản thân code truy xuất cache không có data race.

## 3. Lỗi kinh điển: quên reset visited trong DFS/BFS

Giả sử đồ thị có bốn đỉnh và hai cạnh `(0,1)`, `(2,3)`. Có hai thành phần liên thông:

~~~text
0 --- 1       2 --- 3
components = 2
~~~

Một bộ đếm có field `visited` tái sử dụng nhưng không reset:

~~~java
class Buggy {
    private final boolean[] visited;
    int components() {
        int result = 0;
        for (int u = 0; u < n; u++) {
            if (visited[u]) continue;
            result++;
            dfs(u); // danh dau visited
        }
        return result;
    }
}
~~~

Lần đầu trả `2`. Tất cả `visited[u]` sau đó là true. Lần gọi thứ hai trên cùng instance trả **0**, dù đồ thị không đổi! Đây là **state leak** giữa các lời gọi, không phải lỗi BFS hay định nghĩa thành phần.

Các phương án đúng:

1. **Local state:** tạo `visited` mới trong mỗi lời gọi.
2. **Reset scratch:** dùng `Arrays.fill(visited,false)` trước khi duyệt mọi đỉnh; cũng reset mọi accumulator khác.
3. **Timestamp trick:** giữ mảng `seenEpoch[]` và tăng `epoch` cho mỗi lần gọi; một đỉnh đã thăm nếu `seenEpoch[v] == epoch`. Phải xử lý **epoch overflow** và thread safety; không được dùng epoch=0 mâu thuẫn với giá trị mặc định.
4. **Immutable precomputation:** nếu đồ thị là snapshot bất biến và truy vấn chỉ hỏi số thành phần, tính một lần ở constructor và lưu một con số immutable. Nếu đồ thị có thể thay đổi, phải cập nhật hoặc invalidate.

**Lưu ý hiệu năng:** `Arrays.fill` tốn O(n) mỗi lời gọi; timestamp có thể tránh reset O(n) ở các bài chỉ thăm một phần nhỏ. Nhưng với `countComponents` vốn duyệt mọi đỉnh, reset O(n) thường không thay đổi bậc độ phức tạp.

## 4. Aliasing: sửa một mảng làm thay đổi đối tượng nào?

Java **truyền giá trị của tham chiếu** tới object. Khi truyền một mảng vào constructor, không có bản sao tự động:

~~~java
class UnsafeHolder {
    final boolean[][] matrix;
    UnsafeHolder(boolean[][] input) {
        this.matrix = input; // cung ma tran voi caller
    }
}
~~~

`final` ngăn gán lại **tham chiếu field**, không đóng băng nội dung mảng. Caller vẫn có thể sửa `input[1][2]`, và thuật toán đọc field `matrix` sẽ thấy giá trị mới. Với một đồ thị vô hướng, caller cần sửa cả `input[1][2]` và `input[2][1]`; nếu sửa một phía sẽ phá invariant đối xứng.

**Giữ tham chiếu không mặc nhiên sai.** Nó hợp lệ nếu API công bố đây là **live view** với quy tắc owner/synchronization rõ. Vấn đề xảy ra khi API **ngụ ý snapshot** nhưng thực chất chỉ alias đầu vào.

### 4.1. Copy một chiều không đủ cho mảng hai chiều

~~~java
boolean[][] shallow = original.clone(); // chi copy mang NGOAI
shallow[0][1] = true;                    // sua ca original[0][1]
~~~

Mảng 2D Java là **mảng các tham chiếu tới mảng hàng**. Clone mảng ngoài không clone từng hàng. Bản sao sâu cho ma trận primitive:

~~~java
boolean[][] copy = new boolean[original.length][];
for (int i = 0; i < original.length; i++) {
    copy[i] = original[i].clone();
}
~~~

Cần validate không có `null` row, đúng hình dạng và điều kiện đối xứng **trước** khi dùng cho thuật toán đồ thị vô hướng.

### 4.2. Bản sao có tính thời điểm

Nếu `SafeGraph` tạo deep-copy lúc t0, caller sửa `input` ở t1:

~~~text
t0: external graph co 2 components
t0: SafeGraph snapshot chot 2 components
t1: caller them (1,2) vao external graph
t2: SafeGraph cu van tra 2
t2: new SafeGraph(external) tra 1
~~~

Cả hai kết quả **đều đúng** theo hợp đồng snapshot. Sai là trả lời không nhất quán hoặc không giải thích có cần dựng lại object sau mutation hay không.

### 4.3. Shallow, read-only view và immutable sâu khác nhau

- `Arrays.copyOf`/`clone` trên `int[]` sao chép đầy đủ **các giá trị primitive**.
- `matrix.clone()` trên `int[][]` chỉ sao chép **mảng ngoài**.
- `new ArrayList<>(list)` và `List.copyOf(list)` sao chép cấu trúc danh sách nhưng **không clone mọi object phần tử**; đối tượng bên trong vẫn có thể mutable.
- `Collections.unmodifiableList(list)` tạo **view không cho sửa qua wrapper**, nhưng **list gốc** vẫn có thể bị sửa và wrapper sẽ nhìn thấy cập nhật ấy.
- `List.copyOf` tạo danh sách không cho sửa cấu trúc và không theo thay đổi cấu trúc từ list nguồn, nhưng nếu phần tử là `MutableRecord`, mutate record vẫn quan sát được qua phần tử chia sẻ.
- `final` và `record` không mặc nhiên là **deeply immutable** nếu field trỏ tới array/list/map mutable.

**Ví dụ:** `record Path(int[] nodes) {}` vẫn chứa array có thể bị sửa. Muốn snapshot đúng, defensive-copy trong constructor và cả accessor nếu trả array.

## 5. Trả kết quả cũng có thể làm lộ state

Một phương thức trả về trực tiếp mảng nội bộ:

~~~java
int[] distances() {
    return cachedDistances;  // caller sua duoc state noi bo!
}
~~~

Khi caller làm `distances()[0] = -123`, lần gọi sau đọc cache có thể sai. Có ba lựa chọn tùy hợp đồng:
- Trả **bản sao** `cachedDistances.clone()`;
- Trả kiểu thật sự read-only/immutable, lưu ý phần tử bên trong;
- Công bố và giới hạn quyền truy cập một **view mutable** có kiểm soát, ví dụ thông qua method update làm thay đổi version.

Dùng immutable primitive result/record chứa các số nguyên scalar thường đơn giản. Với object phức tạp, ranh giới ownership cần thể hiện ở cả **đầu vào và đầu ra**.

**Defensive copy phải có ở hai hướng:** copy lúc nhận input để không bị caller sửa source về sau; copy lúc xuất output để caller không đổi state nội bộ.

## 6. In-place hay out-of-place: phải nói rõ

Một số thuật toán được thiết kế để sửa input, ví dụ `Arrays.sort(int[])`, partition của quicksort, reverse array, thao tác matrix rotation, sắp xếp cạnh trước Kruskal. Điều này không xấu nếu hợp đồng nói rõ.

~~~java
static int[] sortedCopy(int[] input) {
    int[] result = input.clone();
    Arrays.sort(result);
    return result;
}

static void sortInPlace(int[] input) {
    Arrays.sort(input);
}
~~~

Với input `[3,1,2]`:
- `sortedCopy(input)` trả `[1,2,3]` nhưng input **vẫn `[3,1,2]`**;
- Sửa array **được trả về** cũng không làm input đổi, vì chúng là hai array khác nhau;
- `sortInPlace(input)` chủ động đổi input thành `[1,2,3]`.

Với `int[][]`, cần copy từng hàng nếu sorting hoặc thuật toán sửa nội dung hàng. Dùng `matrix.clone()` sẽ **không** đủ.

### 6.1. Mutation do iterator, sorting comparator hoặc backtracking

Không chỉ phép gán `a[i]` mới tính là mutation. Những thao tác dưới đây cũng cần được kiểm toán:
- `Collections.sort(list)` đổi thứ tự list nguồn;
- `PriorityQueue.poll()` làm thay đổi queue; dùng chung queue qua nhiều lời gọi có thể cạn dữ liệu;
- `StringBuilder.append` làm thay đổi buffer, và builder dùng lại phải reset với `setLength(0)`;
- `Map.computeIfAbsent` chèn cache key mới;
- Đệ quy backtracking `path.add(x)` phải `path.remove(path.size()-1)` khi trở lui; quên pop làm nhánh sau nhìn thấy state của nhánh trước;
- DSU `union` có mutation bền vững; không thể reuse cùng DSU cho một bộ graph mới mà không rebuild/rollback;
- Biến `static` đếm số node DFS được thăm có thể tích lũy qua lần gọi, dù output chính nhìn có vẻ đúng.

## 7. Prefix sum và cache stale sau khi input thay đổi

Prefix sum trên dãy `a`:

\[
prefix[0]=0,\qquad
prefix[i+1]=prefix[i]+a[i].
\]

Tổng đoạn nửa mở `[l,r)`:

\[
sum(l,r)=prefix[r]-prefix[l],\quad 0\le l\le r\le n.
\]

Nếu tạo `PrefixSumSnapshot` từ một mảng rồi giữ chỉ **prefix đã tính** (và không lưu tham chiếu input), đây là **snapshot bất biến theo input lúc xây dựng**.

~~~text
input=[2,-1,4,3]
prefix=[0,2,1,5,8]
sum(1,3)=(-1)+4=3

caller sua input[1]=99
input moi=[2,99,4,3]

PrefixSumSnapshot cu: sum(1,3)=3
PrefixSumSnapshot moi: sum(1,3)=103
~~~

Không thể gọi kết quả `3` là lỗi nếu contract snapshot; **sai** nếu API tuyên bố tự động phản ánh dữ liệu mới mà không rebuild/update. Cách xử lý:
- Immutable snapshot + dựng lại khi input mới;
- Mutable structure có phương thức `update(index,value)` và cập nhật Fenwick/segment tree cùng version;
- Cache key bao gồm phiên bản input, không chỉ `System.identityHashCode` hay tham chiếu object.

### 7.1. Cache key sai vì bỏ sót input

Giả sử memoization `Map<Integer,Long> memo` lưu đáp án `solve(x)` nhưng nội dung thực lại phụ thuộc thêm `graph`, `limit`, `mod`, `locale` hoặc chiến lược sắp xếp. Reuse memo qua hai lời gọi với graph khác dẫn đến **cache hit giả**.

Nếu `solve(graph,source,limit)` dùng cache, key đúng phải phân biệt mọi tham số có ảnh hưởng: graph snapshot/version, source, limit, cấu hình thuật toán và cả quan hệ thứ tự nếu cần. Nếu dữ liệu mutable và không có version đáng tin, lựa chọn an toàn là **xóa cache khi input đổi** hoặc dựng lại một memo scope riêng cho mỗi lời gọi.

**Hash của đối tượng mutable** trong HashMap cũng nguy hiểm nếu field tham gia `equals`/`hashCode` bị sửa sau khi chèn: tra lại key có thể thất bại. Ưu tiên key immutable theo giá trị.

## 8. Repeatability, reentrancy, thread safety và idempotency

Bốn khái niệm liên quan nhưng khác nhau:

| Thuật ngữ | Câu hỏi kiểm tra | Ví dụ |
| --- | --- | --- |
| **Repeatability** | Gọi cùng API nhiều lần trên dữ liệu không đổi có đúng như hợp đồng không? | `components()` lần 1 và lần 2 đều trả 2 |
| **Reentrancy** | Một lời gọi có thể bị gọi chồng lấn/cắt ngang bởi lời gọi khác mà không phá state không? | Mỗi lời gọi BFS có visited cục bộ |
| **Thread safety** | Các lời gọi từ nhiều thread có tránh data race và đáp ứng contract đồng bộ không? | SafeGraph immutable, mỗi query cấp scratch riêng |
| **Idempotency** | Thực hiện phép biến đổi trạng thái hai lần có cùng hiệu ứng như một lần không? | `set(value)` có thể idempotent; `increment()` thường không |

Ví dụ, `sortInPlace(a)` với cùng comparator là thao tác **idempotent về nội dung sau khi đã sắp**: sort thêm lần nữa không đổi thứ tự giá trị. Nhưng nó vẫn **mutates input**, và không đồng nghĩa thread-safe nếu hai thread cùng sort một mảng.

Một `synchronized int countComponents()` có thể **thread-safe** nhờ chỉ một thread vào tại một thời điểm, song không phải cấu trúc **cho phép các lời gọi thực sự chạy song song** trên cùng scratch; hơn nữa, nếu lời gọi tự gọi lại cùng phương thức trong lúc scratch chưa được phục hồi, còn phải xét trạng thái tái nhập. Một hàm dùng **local visited** và đọc **snapshot immutable** dễ làm nhiều lời gọi chồng lấn độc lập hơn.

**Đặc biệt:** `volatile` trên cờ hoặc tham chiếu không biến một chuỗi `check-then-act` thành thao tác atomic; `synchronized`, lock, immutable state, atomic classes hoặc cấu trúc concurrent phù hợp cần được chọn theo invariant. Và defensive copy khi **caller đang sửa source đồng thời trong lúc copy** cũng không tự bảo đảm snapshot nhất quán; cần **không mutate đồng thời** hoặc một giao thức snapshot/lock/version riêng.

## 9. Tái sử dụng scratch thế nào cho đúng?

Đôi khi hiệu năng đòi tái dùng mảng `visited`, queue, DP buffers thay vì tạo mới. Có thể dùng:

~~~java
final boolean[] seen = new boolean[n];
final int[] queue = new int[n];

synchronized int components() {
    Arrays.fill(seen, false);
    int answer = 0;
    // Xu ly va ghi cac gia tri vao seen/queue;
    // khong de state trung gian anh huong lan goi sau.
    return answer;
}
~~~

**Tính đúng sequential:** mọi field ảnh hưởng tới output phải được reset hoặc được **ghi đè hoàn toàn** trước khi đọc. Không nhất thiết mọi byte phải zero nếu thuật toán đảm bảo không đọc byte cũ; nhưng chứng minh và test điều đó khó hơn.

**Tính đúng khi exception:** nếu một lời gọi ném lỗi giữa chừng và để scratch dở dang, lần gọi tiếp phải reset trước khi đọc hoặc dùng `try/finally` khôi phục state. Với `synchronized`, JVM tự nhả monitor khi thoát vì exception, nhưng **không tự reset field** của bạn.

**Giới hạn hiệu năng:** `synchronized` làm các call trên **cùng instance** phải lần lượt; tăng thread không giúp song song phần xử lý này. Nếu cần đọc song song thực sự, dùng local scratch hoặc cấu trúc per-worker/per-thread. `ThreadLocal` cũng có lifecycle và nguy cơ giữ bộ nhớ trong thread pool nếu dữ liệu lớn, nên không được coi là giải pháp miễn phí.

### 9.1. Dùng generation counter để giảm reset

Thay `boolean[] seen`, có thể có `int[] lastSeenEpoch`:

~~~text
startCall:
    epoch++
    if overflow / collision:
        Arrays.fill(lastSeenEpoch,0)
        epoch=1

visited(v)  <=> lastSeenEpoch[v] == epoch
mark(v): lastSeenEpoch[v] = epoch
~~~

Mỗi call dùng một epoch mới. Ưu điểm là không reset O(n) khi chỉ thăm vài đỉnh. Nhưng **epoch vẫn là shared mutable state**, không thread-safe tự động; phải đồng bộ hoặc cấp epoch riêng. Cũng phải xử lý overflow/giá trị mặc định cẩn thận.

## 10. Bộ kiểm thử phải tạo ra điều kiện gây lỗi

Một test duy nhất kiểu `assertEquals(2,components(graph))` chỉ kiểm lần gọi đầu. Test tốt cần thay đổi **lịch sử lời gọi** và **ownership** một cách có chủ đích.

| Nhóm test | Chuỗi thao tác nên thử | Lỗi có thể phát hiện |
| --- | --- | --- |
| **Repeat call** | `f(x); f(x); f(x)` | visited/total/stack chưa reset |
| **A–B–A** | `f(A); f(B); f(A)` trên cùng service/cache | Key cache thiếu input, state leak |
| **Multi-instance** | Tạo hai instance, gọi xen kẽ | static/global shared state |
| **Input mutation** | Snapshot từ x; sửa x; hỏi snapshot cũ | Shallow copy, alias, stale-contract |
| **Output mutation** | Lấy result; sửa result; gọi lại | Lộ internal array/list |
| **Permutation of test order** | Đảo thứ tự các test case | Global state làm suite phụ thuộc thứ tự |
| **Empty / singleton** | n=0, n=1, input rỗng | Sai khởi tạo/reset, chia 0 |
| **Duplicate / self-loop** | Cạnh tự nối, cạnh trùng | Giả định sai về hình dạng input |
| **Concurrent invocation** | Nhiều thread gọi cùng snapshot | Race trên scratch/cache |
| **Failure recovery** | Invalid input hoặc exception rồi gọi case đúng | State không được khôi phục |
| **Boundary / overflow** | Tổng lớn, negative values, chỉ số sai | Integer overflow, range |
| **Differential oracle** | So BFS với DSU/DFS độc lập | Thuật toán tính toán sai |
| **Mutation assertion** | Chụp input trước/sau | Hàm không được sửa input nhưng đã sửa |
| **Contract-specific updates** | Cập nhật qua API rồi query | Cache không invalidate/version |

**Đừng chỉ kiểm stdout một lần.** Cần kiểm invariant: input không đổi, snapshot vẫn đúng sau khi caller sửa, các lời gọi thứ hai/ba đúng, và kết quả không phụ thuộc thứ tự test.

### 10.1. Khi nào nên random và khi nào vét cạn?

- **Vét cạn miền nhỏ:** tất cả graph nhỏ, mọi mảng ngắn hay mọi chuỗi thao tác ngắn; dễ tìm phản ví dụ và replay chính xác.
- **Randomized differential tests:** tăng độ đa dạng về n, shape, mutation, call order, thread count; nên dùng seed xác định để tái hiện.
- **Property-based tests:** kiểm quan hệ như `components(graph)` không đổi sau **gọi lặp**, snapshot không đổi sau external mutation, hoặc số component giảm tối đa 1 khi thêm một cạnh.
- **Concurrency stress tests:** hữu ích để tìm race nhưng một lần pass **không chứng minh** thread safety; cần phân tích cấu trúc chia sẻ và memory model.
- **Static review:** tìm alias, static state, missing reset, raw-array return và mutation không công bố.

Các test hữu hạn có thể phát hiện bug; **chứng minh bằng bất biến** xác nhận nguyên lý hoạt động với mọi input hợp lệ theo contract.

## 11. Java 17: minh họa lỗi và bản cài đặt an toàn

Chương trình **StateReuseAndInputSafetyDemo.java** gồm:

1. `BuggyGraph` giữ **cùng ma trận đầu vào** và không reset `visited`: lần thứ hai sai.
2. `SafeGraph` **deep-copy** ma trận và dùng **visited/queue cục bộ**: gọi lặp, sửa input bên ngoài, gọi đồng thời đều giữ kết quả cho snapshot.
3. `ScratchGraph` cũng deep-copy nhưng tái dùng `seen` và `queue`: reset đúng mỗi call, dùng `synchronized` để không xảy ra tranh chấp giữa các call cùng instance.
4. `PrefixSumSnapshot`: chụp prefix sums bằng `long[]`, kiểm chỉ số, dùng `Math.addExact`/`subtractExact` phát hiện tràn thay vì wrap.
5. `sortedCopy` và `sortInPlace`: minh họa input ownership.
6. Oracle **DSU khác thuật toán BFS** để kiểm toàn bộ 33.867 ma trận đồ thị nhỏ.
7. Kiểm thử nhiều lần, thay đổi caller input, invalid matrix, tương tác nhiều instance và gọi đồng thời.

**Một lựa chọn có chủ đích:** chương trình cho phép graph kích thước n=0 và trả `components=0` cho graph rỗng; nhưng truy vấn `connected(u,v)` trên graph rỗng bị từ chối vì không có đỉnh hợp lệ.

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class StateReuseAndInputSafetyDemo {

    // Chi cho phep ma tran ke vuong, undirected.
    // Clone tung hang de bo alias voi array cua caller.
    static boolean[][] snapshotMatrix(boolean[][] input) {
        Objects.requireNonNull(input, "matrix");
        int n = input.length;
        for (int i = 0; i < n; i++) {
            if (input[i] == null || input[i].length != n)
                throw new IllegalArgumentException(
                    "Matrix must be square and non-null");
        }
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                if (input[i][j] != input[j][i])
                    throw new IllegalArgumentException(
                        "Undirected adjacency must be symmetric");
            }
        }
        boolean[][] copy = new boolean[n][];
        for (int i = 0; i < n; i++)
            copy[i] = input[i].clone();
        return copy;
    }

    static boolean[][] shallowIndependentCopy(boolean[][] x) {
        boolean[][] result = new boolean[x.length][];
        for (int i = 0; i < x.length; i++)
            result[i] = x[i].clone();
        return result;
    }

    static void vertex(boolean[][] data, int x) {
        if (x < 0 || x >= data.length)
            throw new IllegalArgumentException(
                "Vertex out of range: " + x);
    }

    // HAI LOI: giu alias source + visited dung lai khong reset.
    static final class BuggyGraph {
        final boolean[][] graph;
        final boolean[] visited;

        BuggyGraph(boolean[][] input) {
            graph = input;
            visited = new boolean[input.length];
        }

        int components() {
            int n = graph.length;
            int result = 0;
            int[] queue = new int[n];

            for (int start = 0; start < n; start++) {
                if (visited[start]) continue;
                result++;
                int head = 0, tail = 0;
                queue[tail++] = start;
                visited[start] = true;
                while (head < tail) {
                    int u = queue[head++];
                    for (int v = 0; v < n; v++) {
                        if (graph[u][v] && !visited[v]) {
                            visited[v] = true;
                            queue[tail++] = v;
                        }
                    }
                }
            }
            return result;
        }
    }

    // Immutable by API. graph khong duoc expose.
    // Moi method call tu tao visited/queue rieng.
    static final class SafeGraph {
        private final boolean[][] graph;

        SafeGraph(boolean[][] input) {
            graph = snapshotMatrix(input);
        }

        int components() {
            int n = graph.length;
            boolean[] visited = new boolean[n];
            int[] queue = new int[n];
            int result = 0;

            for (int start = 0; start < n; start++) {
                if (visited[start]) continue;
                result++;
                int head = 0, tail = 0;
                visited[start] = true;
                queue[tail++] = start;
                while (head < tail) {
                    int u = queue[head++];
                    for (int v = 0; v < n; v++) {
                        if (graph[u][v] && !visited[v]) {
                            visited[v] = true;
                            queue[tail++] = v;
                        }
                    }
                }
            }
            return result;
        }

        boolean connected(int from, int to) {
            vertex(graph, from);
            vertex(graph, to);
            int n = graph.length;
            boolean[] visited = new boolean[n];
            int[] queue = new int[n];
            int head = 0, tail = 0;
            visited[from] = true;
            queue[tail++] = from;

            while (head < tail) {
                int u = queue[head++];
                if (u == to) return true;
                for (int v = 0; v < n; v++) {
                    if (graph[u][v] && !visited[v]) {
                        visited[v] = true;
                        queue[tail++] = v;
                    }
                }
            }
            return false;
        }
    }

    // Reuse buffer tiet kiem allocation nhung synchronized serialize call.
    static final class ScratchGraph {
        private final boolean[][] graph;
        private final boolean[] seen;
        private final int[] queue;

        ScratchGraph(boolean[][] input) {
            graph = snapshotMatrix(input);
            seen = new boolean[graph.length];
            queue = new int[graph.length];
        }

        synchronized int components() {
            Arrays.fill(seen, false);
            int result = 0;
            for (int start = 0; start < graph.length; start++) {
                if (seen[start]) continue;
                result++;
                int head = 0, tail = 0;
                seen[start] = true;
                queue[tail++] = start;
                while (head < tail) {
                    int u = queue[head++];
                    for (int v = 0; v < graph.length; v++) {
                        if (graph[u][v] && !seen[v]) {
                            seen[v] = true;
                            queue[tail++] = v;
                        }
                    }
                }
            }
            return result;
        }
    }

    static final class PrefixSumSnapshot {
        private final long[] prefix;

        PrefixSumSnapshot(int[] source) {
            Objects.requireNonNull(source);
            prefix = new long[source.length + 1];
            for (int i = 0; i < source.length; i++) {
                prefix[i + 1] = Math.addExact(prefix[i], source[i]);
            }
        }

        long sum(int left, int rightExclusive) {
            if (left < 0 || rightExclusive < left
                || rightExclusive >= prefix.length)
                throw new IllegalArgumentException("Invalid range");
            return Math.subtractExact(
                prefix[rightExclusive], prefix[left]);
        }
    }

    static int[] sortedCopy(int[] source) {
        Objects.requireNonNull(source);
        int[] out = source.clone();
        Arrays.sort(out);
        return out;
    }

    static void sortInPlace(int[] source) {
        Objects.requireNonNull(source);
        Arrays.sort(source);
    }

    // Independent oracle: DSU union-by-size, khong BFS.
    // Self-loop khong thay doi component.
    static int oracleDsuComponents(boolean[][] matrix) {
        int n = matrix.length;
        int[] parent = new int[n];
        int[] size = new int[n];
        for (int i = 0; i < n; i++) {
            parent[i] = i;
            size[i] = 1;
        }

        int components = n;
        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                if (!matrix[i][j]) continue;
                int a = i, b = j;
                while (parent[a] != a) a = parent[a];
                while (parent[b] != b) b = parent[b];
                if (a == b) continue;
                if (size[a] < size[b]) {
                    int temp = a; a = b; b = temp;
                }
                parent[b] = a;
                size[a] += size[b];
                components--;
            }
        }
        return components;
    }

    static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    static final class Counts {
        long graphs, repeatCalls, callerMutations;
    }

    // All undirected adjacency matrices including loops, n=0..5.
    // There are 2^(n*(n+1)/2) possible symmetric bit patterns.
    static Counts exhaustive() {
        Counts checked = new Counts();

        for (int n = 0; n <= 5; n++) {
            int edgeBits = n * (n + 1) / 2;
            long limit = 1L << edgeBits;
            for (long mask = 0; mask < limit; mask++) {
                boolean[][] matrix = new boolean[n][n];
                int bit = 0;
                for (int i = 0; i < n; i++) {
                    for (int j = i; j < n; j++) {
                        boolean active =
                            ((mask >>> bit) & 1L) != 0L;
                        matrix[i][j] = active;
                        matrix[j][i] = active;
                        bit++;
                    }
                }

                boolean[][] before = shallowIndependentCopy(matrix);
                SafeGraph safe = new SafeGraph(matrix);
                ScratchGraph scratch = new ScratchGraph(matrix);
                int expected = oracleDsuComponents(matrix);
                require(safe.components() == expected,
                    "safe first n=" + n + ",mask=" + mask);
                require(safe.components() == expected,
                    "safe repeat n=" + n + ",mask=" + mask);
                require(scratch.components() == expected,
                    "scratch first n=" + n + ",mask=" + mask);
                require(scratch.components() == expected,
                    "scratch repeat n=" + n + ",mask=" + mask);

                require(Arrays.deepEquals(matrix,before),
                    "Input was mutated by analysis");
                checked.graphs++;
                checked.repeatCalls += 4;

                if (n >= 2) {
                    // Mutate CALLER-owned matrix, not saved snapshot.
                    boolean next = !matrix[0][1];
                    matrix[0][1] = next;
                    matrix[1][0] = next;
                    require(safe.components() == expected,
                        "Snapshot changed unexpectedly");
                    require(scratch.components() == expected,
                        "Scratch snapshot changed");
                    require(new SafeGraph(matrix).components()
                            == oracleDsuComponents(matrix),
                        "Fresh snapshot does not match new input");
                    checked.callerMutations++;
                }
            }
        }

        require(checked.graphs == 33867L,
            "Unexpected number of graphs");
        require(checked.repeatCalls == 135468L,
            "Unexpected number of repeated calls");
        require(checked.callerMutations == 33864L,
            "Unexpected number of mutation cases");
        return checked;
    }

    static boolean invalidMatrixRejected(boolean[][] input) {
        try {
            new SafeGraph(input);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    // Overlapping CALLS on the same immutable SafeGraph.
    // No timing or execution order is asserted.
    static boolean parallelCallsPass(
            SafeGraph graph, int expected) throws Exception {
        ExecutorService service =
            Executors.newFixedThreadPool(3);
        try {
            List<Callable<Integer>> tasks = new ArrayList<>();
            for (int i = 0; i < 120; i++)
                tasks.add(graph::components);

            List<Future<Integer>> futures =
                service.invokeAll(tasks);
            for (Future<Integer> f : futures) {
                if (f.get() != expected) return false;
            }
            return true;
        } finally {
            service.shutdown();
        }
    }

    public static void main(String[] args) throws Exception {
        boolean[][] callerMatrix = {
            {false,true, false,false},
            {true, false,false,false},
            {false,false,false,true },
            {false,false,true, false}
        };
        BuggyGraph buggy = new BuggyGraph(callerMatrix);
        SafeGraph safe = new SafeGraph(callerMatrix);
        ScratchGraph scratch =
            new ScratchGraph(callerMatrix);

        System.out.println("buggy.first=" + buggy.components());
        System.out.println("buggy.second=" + buggy.components());
        System.out.println("safe.first=" + safe.components());
        System.out.println("safe.second=" + safe.components());
        System.out.println("scratch.first=" + scratch.components());
        System.out.println("scratch.second=" + scratch.components());

        // Thay doi input SAU khi tao hai snapshot.
        callerMatrix[1][2] = true;
        callerMatrix[2][1] = true;
        System.out.println("safe.afterCallerMutation="
            + safe.components());
        System.out.println("scratch.afterCallerMutation="
            + scratch.components());
        System.out.println("fresh.afterCallerMutation="
            + new SafeGraph(callerMatrix).components());
        System.out.println("safe.connected(0,3)="
            + safe.connected(0,3));

        int[] numbers = {2,-1,4,3};
        PrefixSumSnapshot pref = new PrefixSumSnapshot(numbers);
        System.out.println("prefix.sum[1,3)=" + pref.sum(1,3));
        numbers[1] = 99;
        System.out.println("prefix.afterCallerMutation="
            + pref.sum(1,3));
        System.out.println("prefix.fresh[1,3)="
            + new PrefixSumSnapshot(numbers).sum(1,3));

        int[] toSort = {3,1,2};
        int[] sorted = sortedCopy(toSort);
        System.out.println("sort.original="
            + Arrays.toString(toSort));
        System.out.println("sort.sortedCopy="
            + Arrays.toString(sorted));
        sorted[0] = 99; // sua output, khong sua source
        System.out.println("sort.originalAfterOutputMutation="
            + Arrays.toString(toSort));
        sortInPlace(toSort);
        System.out.println("sort.inPlace="
            + Arrays.toString(toSort));

        SafeGraph other = new SafeGraph(new boolean[][] {
            {false,true},
            {true,false}
        });
        boolean orderIndependent =
            safe.components() == 2
            && other.components() == 1
            && safe.components() == 2;
        System.out.println("callOrder.independent="
            + orderIndependent);
        System.out.println("sameInstance.parallelCallsPass="
            + parallelCallsPass(safe,2));

        int rejected = 0;
        if (invalidMatrixRejected(new boolean[][] {
                {false,true},{false,false}}))
            rejected++;
        if (invalidMatrixRejected(new boolean[][] {
                {false,true},{false}}))
            rejected++;
        if (invalidMatrixRejected(new boolean[][] {null}))
            rejected++;
        System.out.println("invalidMatricesRejected=" + rejected);

        Counts checked = exhaustive();
        System.out.println("enumerated.graphs=" + checked.graphs);
        System.out.println("enumerated.repeatCalls="
            + checked.repeatCalls);
        System.out.println("enumerated.callerMutations="
            + checked.callerMutations);

        require(rejected == 3
            && orderIndependent, "Contract tests failed");
        System.out.println("verification=PASS");
    }
}
~~~

### Lệnh chạy

Lưu toàn bộ mã trên thành **StateReuseAndInputSafetyDemo.java**. Với JDK 17 trở lên:

~~~bash
javac StateReuseAndInputSafetyDemo.java
java StateReuseAndInputSafetyDemo
~~~

### Đầu ra dự kiến

~~~text
buggy.first=2
buggy.second=0
safe.first=2
safe.second=2
scratch.first=2
scratch.second=2
safe.afterCallerMutation=2
scratch.afterCallerMutation=2
fresh.afterCallerMutation=1
safe.connected(0,3)=false
prefix.sum[1,3)=3
prefix.afterCallerMutation=3
prefix.fresh[1,3)=103
sort.original=[3, 1, 2]
sort.sortedCopy=[1, 2, 3]
sort.originalAfterOutputMutation=[3, 1, 2]
sort.inPlace=[1, 2, 3]
callOrder.independent=true
sameInstance.parallelCallsPass=true
invalidMatricesRejected=3
enumerated.graphs=33867
enumerated.repeatCalls=135468
enumerated.callerMutations=33864
verification=PASS
~~~

**Ý nghĩa các dòng quan trọng:**

- `buggy.first=2` nhưng `buggy.second=0`: một instance giữ `visited` sau khi thăm tất cả đỉnh; lần hai không còn đỉnh nào được tính là “chưa thăm”.
- `safe.first=2`, `safe.second=2`: local visited nên không bị rò trạng thái.
- `scratch.first=2`, `scratch.second=2`: scratch dùng lại nhưng reset hoàn toàn và truy cập có `synchronized`.
- Sau khi caller nối thêm cạnh 1–2, snapshot cũ vẫn 2 thành phần, còn instance mới từ input đã sửa có 1 thành phần.
- `safe.connected(0,3)=false`: SafeGraph vẫn dựa trên snapshot cũ gồm hai thành phần.
- Prefix sum cũ vẫn trả 3 trong khi prefix xây lại từ mảng đã sửa trả 103, thể hiện semantics snapshot rõ ràng.
- `sortedCopy` không sửa source; sửa mảng kết quả cũng không sửa source; `sortInPlace` được chủ động định nghĩa để sửa source.
- `sameInstance.parallelCallsPass=true` là **kiểm một số lời gọi thực tế**, không tự chứng minh chương trình không có race trong mọi lịch thread; bằng chứng thiết kế ở đây là `SafeGraph` chỉ đọc ma trận private snapshot và cấp bộ đệm local.
- Ba ma trận không hợp lệ: một không đối xứng, một không vuông, một có `null` row; cả ba bị từ chối.
- Các thống kê vét cạn là số **input/quan hệ kiểm thử** được chương trình dự kiến tự đếm. Trong quá trình biên soạn, thuật toán đã được kiểm tra bằng mô hình JavaScript độc lập; không ngụ ý đã thực thi `javac` ở đây.

## 12. Vì sao phép kiểm thử 33.867 đồ thị có giá trị?

Đồ thị vô hướng n đỉnh cho phép self-loop có \(\frac{n(n+1)}2\) vị trí cạnh độc lập (n ô đường chéo và n(n−1)/2 cặp ngoài đường chéo). Mỗi vị trí có thể false/true, nên số ma trận đối xứng là:

\[
2^{n(n+1)/2}.
\]

Với n từ 0 đến 5:

| n | Số đồ thị đối xứng |
| ---: | ---: |
| 0 | 1 |
| 1 | 2 |
| 2 | 8 |
| 3 | 64 |
| 4 | 1.024 |
| 5 | 32.768 |
| **Tổng** | **33.867** |

Mỗi đồ thị được kiểm:
1. `SafeGraph.components()` hai lần;
2. `ScratchGraph.components()` hai lần;
3. Cả bốn kết quả đều phải bằng **oracle DSU độc lập**; input không được bị sửa bởi phép đếm;
4. Nếu n≥2, sửa cạnh `(0,1)` trong **ma trận thuộc caller**, giữ đối xứng; hai snapshot cũ phải trả kết quả **như trước**, còn instance mới phải khớp oracle trên ma trận mới.

Từ đó có **33.867 × 4 = 135.468 lần gọi** dùng để kiểm tra khả năng gọi lặp (chưa kể các lần gọi sau mutation). Có **33.864 input** với n≥2 được sửa sau khi chụp snapshot. Mọi phép so trong mô hình độc lập đều đạt.

**Điều gì chưa được chứng minh bằng những con số này?** Không gian n lớn hơn 5, các chương trình sử dụng adjacency list khác contract, các kiểu dữ liệu Java khác, mọi lịch song song, và mọi biến thể cache. Vì vậy test phải đi cùng **proof/ownership contract**, không thay thế chúng.

### 12.1. Bằng chứng tính đúng cho graph snapshot

- Constructor `snapshotMatrix` kiểm shape và đối xứng rồi clone **từng hàng**.
- `graph` trong SafeGraph là private, không có API trả mảng hoặc sửa nó.
- `components()` tạo `visited`/`queue` mới, BFS thăm mỗi đỉnh đúng một lần theo các cạnh đang có trong snapshot.
- Mỗi BFS bắt đầu ở một đỉnh chưa thăm xác định đúng một thành phần liên thông; tổng lần bắt đầu BFS là số thành phần.
- Hai lời gọi khác nhau không chia sẻ scratch, nên lần gọi cũ không thể đánh dấu `visited` của lần gọi mới.
- Caller sửa ma trận ngoài không sửa clone bên trong, vì hai phía không chia sẻ row arrays; snapshot được giữ nguyên.

**Giới hạn concurrent constructor:** nếu caller sửa input **đồng thời ngay trong lúc constructor kiểm tra/copy**, có thể nhận snapshot không nhất quán. API có thể yêu cầu caller **không mutate trong suốt quá trình tạo bản chụp**, hoặc dùng cơ chế copy đồng bộ/copy-on-write bất biến. Bản demo không hứa atomic snapshot từ một nguồn đang được ghi tự do.

## 13. Phân tích độ phức tạp và đánh đổi

Với ma trận kề n×n:
- Sao chép ma trận trong constructor: **O(n²)** thời gian và **O(n²)** bộ nhớ.
- `SafeGraph.components()`: O(n²) thời gian do quét các cột của mỗi đỉnh một lần, O(n) bộ nhớ tạm cho `visited` và `queue`.
- `SafeGraph.connected(u,v)`: O(n²) worst-case thời gian và O(n) bộ nhớ tạm.
- `ScratchGraph.components()`: O(n²) thời gian, O(n) scratch giữ trong instance; `Arrays.fill` O(n) đầu mỗi lời gọi; các call trên cùng instance được serialize bởi `synchronized`.
- Oracle DSU vét cạn: O(n² log n) worst-case với union by size **không path compression** ở bản oracle demo, nhưng test chỉ chạy n≤5; nó dùng cấu trúc khác BFS.
- `PrefixSumSnapshot`: O(n) xây dựng, O(n) bộ nhớ; truy vấn range sum O(1) phép số nguyên sau khi kiểm biên.
- `sortedCopy`: O(n log n) thời gian, O(n) mảng kết quả; `sortInPlace` sắp xếp trực tiếp source, không có bản sao full-size cho input primitive; chi tiết bộ nhớ tạm phụ thuộc triển khai sorting trong JDK.
- `exhaustive()` chỉ dành cho dữ liệu rất nhỏ: số đồ thị đối xứng tăng **theo hàm mũ của n²**, không được chạy cho n lớn.

**Trade-off giữa local scratch và shared scratch:** local scratch O(n) allocation mỗi call nhưng đơn giản và đồng thời tốt; shared scratch tránh allocation lặp nhưng cần reset và cách ly hoặc đồng bộ, có thể làm chậm khi thread contention. Chọn bằng benchmark trên workload thật, không tự giả định “tái sử dụng buffer luôn nhanh hơn”.

## 14. Nhiều test case, nhiều query và vòng đời đối tượng

Trong bài thi lập trình, một hàm `solve()` có thể được gọi một lần trên mỗi test case. Trong thư viện, service hoặc ứng dụng web, cùng instance có thể phục vụ **hàng nghìn request**. Khác biệt lifecycle này dễ biến code đúng ở bài thi thành bug production.

### 14.1. Trạng thái DP bị mang qua case mới

Một `dp[n][state]` lưu kết quả của input cũ nhưng `solve(newInput)` chỉ cập nhật một phần khiến một số ô chưa ghi trong lần mới vẫn có giá trị cũ. Cách khắc phục là xác định các **reachable states** cần khởi tạo, reset đúng miền hoặc tạo DP table theo lần gọi. Nếu dùng memoization, key phải chứa mọi tham số và mọi thuộc tính input có ảnh hưởng đến đáp án.

### 14.2. Graph search và visited

BFS/DFS dùng `visited` có thể phải reset cho từng nguồn tìm kiếm, trừ khi đang cố tình tính reachability từ **tất cả nguồn trong một lần gọi** với cấu trúc riêng. Đừng mang visited của source A sang source B rồi tự coi “đã thăm” là “không cần đi nữa” nếu query mới cần tìm đường khác.

### 14.3. DSU dùng qua nhiều đồ thị

Một DSU đã union cạnh của đồ thị A không thể thay bằng đồ thị B chỉ bằng `union` thêm: các tập đã gộp không tự tách. Nếu đồ thị mới khác, khởi tạo DSU mới hoặc sử dụng cơ chế rollback/persistence theo đúng timeline. Đừng lưu một singleton DSU phục vụ các query về nhiều graph ID mà không phân tách state.

### 14.4. Duy trì prefix sums và sorted index

Các cấu trúc này thường được tính một lần trên snapshot. Nếu source thay đổi qua API update, cần **cập nhật cấu trúc dẫn xuất** tương ứng hoặc invalidate/rebuild. Nếu source tự bị caller sửa “ngoài cửa sau”, hệ thống có thể không biết phải invalidate cache.

### 14.5. Backtracking và mutable stack

Trong backtracking, một nhánh thêm phần tử vào `path` rồi phải pop sau khi xong. Nếu ném exception và cần khôi phục state bất biến giữa các call, `try/finally` hoặc cấu trúc local giúp tránh state dở dang. Khi copy kết quả, phải copy `path`, không chỉ thêm **tham chiếu cùng list** vào danh sách answers; nếu không mọi đáp án cuối có thể trỏ cùng list bị thay đổi.

## 15. Checklist kiểm toán code

1. **Khai báo rõ ownership:** hàm có sửa input hay không, ai giữ quyền mutate?
2. **Xác định state lifecycle:** local, instance, static, ThreadLocal, cache hay external storage.
3. **Dùng local scratch khi có thể** nếu muốn repeatable/reentrant và concurrent reads đơn giản.
4. **Nếu reuse scratch:** reset đủ mọi field, tránh đọc phần tử cũ trước khi ghi mới.
5. **Bảo đảm cleanup sau exception**, đặc biệt với buffer/stack mutable sống qua nhiều lời gọi.
6. **Không tin `final` là deep immutability**; kiểm các phần tử array/list/map lồng nhau.
7. **Copy từng hàng** khi cần snapshot ma trận Java 2D.
8. **Không trả trực tiếp array mutable nội bộ** trừ khi contract cố ý.
9. **Đặt tên API rõ:** `sortInPlace` và `sortedCopy` thay vì một tên `sort` nhập nhằng.
10. **Ghi phiên bản input/cache key** nếu memoization phụ thuộc dữ liệu có thể thay đổi.
11. **Không chia sẻ mutable state giữa case khác nhau** nếu không có isolation.
12. **Phân biệt repeatability, reentrancy, thread safety và idempotency** khi thiết kế test.
13. **Xác nhận shape/biên/giá trị hợp lệ** trước khi thuật toán đọc input.
14. **Kiểm mutation có chủ đích**: assert trước/sau input theo hợp đồng.
15. **Kiểm gọi lặp A–A–A và A–B–A**, xen kẽ nhiều instance và permutation test order.
16. **Kiểm caller sửa source sau constructor**, rồi phân biệt snapshot cũ và instance dựng lại.
17. **Kiểm caller sửa output được trả** có làm state của object đổi không.
18. **Kiểm test đồng thời** trên immutable snapshot; không dựa một lần pass để chứng minh race-free.
19. **Có oracle khác cấu trúc** cho dữ liệu nhỏ, ví dụ BFS so DSU.
20. **Kiểm mô hình overflow, null, empty, ragged matrix, invalid indices và self-loop.**
21. **Tách correctness khỏi tối ưu hóa allocation**; ưu tiên cách dễ chứng minh trước khi reuse buffer.
22. **Benchmark thật khi tối ưu**, đo allocation/GC/CPU và throughput, không chỉ đo một lần chạy.

## 16. Bài tập tự luyện có đáp án

**Bài 1.** Vì sao BFS đúng ở lần đầu nhưng trả 0 ở lần thứ hai khi đồ thị không đổi?

*Đáp án:* `visited` lưu trong instance chưa reset, mọi đỉnh bị coi là đã thăm từ lần trước.

**Bài 2.** Hai cách sửa `visited` phổ biến?

*Đáp án:* Tạo mảng local mỗi lời gọi hoặc reset hoàn toàn mảng dùng lại trước khi đọc.

**Bài 3.** `final int[] a` có ngăn `a[0]++` không?

*Đáp án:* Không. `final` chỉ cố định tham chiếu field/biến, không đóng băng phần tử.

**Bài 4.** `boolean[][] copy = original.clone()` đã deep-copy toàn ma trận chưa?

*Đáp án:* Chưa. Chỉ clone mảng tham chiếu các hàng; cần clone từng `original[i]`.

**Bài 5.** Caller sửa ma trận gốc sau khi tạo snapshot an toàn thì kết quả snapshot cũ nên thế nào?

*Đáp án:* Giữ nguyên vì snapshot đã chốt dữ liệu tại thời điểm xây dựng, nếu caller không ghi đồng thời lúc copy.

**Bài 6.** Nếu muốn API phản ánh cập nhật input ngay, cần gì?

*Đáp án:* Một hợp đồng mutable/live view và cơ chế update/invalidate/cache/version/synchronization rõ ràng.

**Bài 7.** Lỗi khi trả trực tiếp `cachedDistances` là gì?

*Đáp án:* Caller sửa mảng trả về sẽ sửa luôn state nội bộ, có thể làm query sau sai.

**Bài 8.** `sortedCopy` khác `sortInPlace` như thế nào?

*Đáp án:* `sortedCopy` trả array mới và giữ input; `sortInPlace` cố ý sửa input.

**Bài 9.** `List.copyOf(list)` có deep-clone các phần tử mutable không?

*Đáp án:* Không. Nó sao chép cấu trúc và giữ tham chiếu tới các element object.

**Bài 10.** `Collections.unmodifiableList(source)` có tự chụp snapshot source không?

*Đáp án:* Không. Đây là read-only view; thay đổi source vẫn có thể hiện ra qua view.

**Bài 11.** Một cache key chỉ dùng `source` nhưng kết quả còn phụ thuộc `limit` có ổn không?

*Đáp án:* Không. Cache phải phân biệt mọi tham số ảnh hưởng tới kết quả.

**Bài 12.** `solve(A); solve(B); solve(A)` là test cho lỗi gì?

*Đáp án:* Cache dùng lại sai ngữ cảnh, state leak hoặc cách ly instance không đúng.

**Bài 13.** `static visited` có thể khiến test order ảnh hưởng kết quả không?

*Đáp án:* Có. Mọi instance dùng chung state, ca sau có thể thấy dấu thăm của ca trước.

**Bài 14.** Repeatability có đồng nghĩa thread safety không?

*Đáp án:* Không. Hàm có thể đúng khi gọi tuần tự nhiều lần nhưng race khi gọi đồng thời.

**Bài 15.** Reentrancy và thread safety có hoàn toàn đồng nghĩa không?

*Đáp án:* Không. Reentrancy xét các lời gọi chồng lấn không làm hỏng state; thread safety xét hợp đồng khi nhiều thread truy cập và đồng bộ.

**Bài 16.** `synchronized` trên một phương thức reuse scratch đạt điều gì?

*Đáp án:* Ngăn các thread đồng thời đi vào phần method đó trên cùng instance; nó serialize lời gọi, không biến scratch thành immutable.

**Bài 17.** `volatile` trên `boolean[]` có làm từng phần tử và nhiều cập nhật liên quan trở thành atomic không?

*Đáp án:* Không; volatile reference không tự làm compound operations atomic.

**Bài 18.** Snapshot deep-copy một mảng đang được thread khác sửa đồng thời có tự bảo đảm nhất quán không?

*Đáp án:* Không. Cần hợp đồng không sửa đồng thời, lock, phiên bản hoặc cơ chế snapshot nguyên tử thích hợp.

**Bài 19.** Idempotency khác repeated deterministic output thế nào?

*Đáp án:* Idempotency hỏi hiệu ứng áp dụng thao tác hai lần bằng một lần; deterministic output hỏi cùng input cho cùng giá trị.

**Bài 20.** Trong ví dụ hai component `{0,1}`, `{2,3}`, buggy graph trả bao nhiêu ở hai lần gọi?

*Đáp án:* 2 ở lần đầu và 0 ở lần hai, vì visited không reset.

**Bài 21.** Sau khi thêm cạnh `(1,2)` vào ma trận của caller, SafeGraph snapshot cũ trả mấy component?

*Đáp án:* 2.

**Bài 22.** Một instance SafeGraph mới được dựng sau khi thêm `(1,2)` trả mấy component?

*Đáp án:* 1, cả bốn đỉnh đã nối.

**Bài 23.** Prefix sum của `[2,-1,4,3]` có `sum(1,3)` bằng bao nhiêu?

*Đáp án:* −1+4=3, với đoạn nửa mở `[1,3)`.

**Bài 24.** Sau khi caller thay `-1` thành `99`, snapshot prefix cũ và instance mới cho `sum(1,3)` thế nào?

*Đáp án:* Snapshot cũ 3; snapshot mới 103.

**Bài 25.** Vì sao DP table reuse giữa hai input có thể sai?

*Đáp án:* Các ô chưa được tính lại ở input mới vẫn chứa giá trị dẫn xuất từ input cũ.

**Bài 26.** Quên pop khỏi `path` khi backtracking gây hậu quả gì?

*Đáp án:* Nhánh sau kế thừa trạng thái đường đi từ nhánh trước, có thể tạo lời giải sai.

**Bài 27.** Nếu thêm `path` mutable trực tiếp vào `answers` nhiều lần mà không clone thì sao?

*Đáp án:* Nhiều entry có thể tham chiếu cùng một list và bị thay đổi cùng nhau.

**Bài 28.** Một DSU đã union cho graph A có thể được dùng nguyên cho graph B khác không?

*Đáp án:* Không tự động; DSU không tách các union cũ, cần reset/rebuild hoặc rollback đúng thời điểm.

**Bài 29.** Đồ thị vô hướng n đỉnh cho phép self-loop có bao nhiêu cặp cạnh độc lập?

*Đáp án:* `n(n+1)/2` cặp `(i,j)` với `i≤j`.

**Bài 30.** Có bao nhiêu ma trận kề đối xứng n=5 nếu mỗi cạnh/cạnh tự nối là boolean?

*Đáp án:* `2^15=32.768`.

**Bài 31.** Tổng số đồ thị n=0..5 như bài có bao nhiêu?

*Đáp án:* 1+2+8+64+1.024+32.768=33.867.

**Bài 32.** Nếu kiểm bốn lần gọi cho mỗi đồ thị thì có bao nhiêu phép kiểm repeated call?

*Đáp án:* 33.867×4=135.468.

**Bài 33.** Vì sao số ca mutation sau snapshot là 33.864 chứ không phải 33.867?

*Đáp án:* Chỉ sửa cạnh `(0,1)` khi n≥2; loại 1 đồ thị n=0 và 2 đồ thị n=1.

**Bài 34.** Nếu một chương trình vượt qua 33.867 đồ thị nhỏ thì đã chứng minh mọi đồ thị lớn đúng chưa?

*Đáp án:* Chưa. Test hữu hạn bổ sung cho proof về ownership, BFS invariant và reset.

**Bài 35.** Test `result[0]=99` sau khi nhận mảng kết quả giúp phát hiện gì?

*Đáp án:* API trả alias tới input/internal cache hoặc không có defensive copy.

**Bài 36.** `Arrays.deepEquals` dùng để kiểm gì trong demo?

*Đáp án:* Xác nhận ma trận caller không bị thuật toán phân tích sửa trong khi gọi `components()`.

**Bài 37.** Vì sao không nên dùng epoch counter mà không xử lý overflow?

*Đáp án:* Epoch có thể quay vòng trùng dấu thăm cũ, khiến đỉnh bị coi là đã visited trong lời gọi mới.

**Bài 38.** Cache dùng key là object mutable có thể thất bại như thế nào?

*Đáp án:* Nếu field tham gia equals/hashCode bị sửa sau khi chèn, hash bucket tìm lại key có thể không khớp.

**Bài 39.** Một hàm reuse scratch ném exception giữa chừng cần lưu ý gì cho lần gọi sau?

*Đáp án:* Phải reset trước khi dùng lại hoặc cleanup bằng finally; exception không tự reset field.

**Bài 40.** Khi nào nên ưu tiên local visited hơn shared visited?

*Đáp án:* Khi cần correctness đơn giản, có nhiều lời gọi đồng thời, hoặc allocation chưa phải bottleneck đã đo.

## Tổng kết

**Thuật toán đúng không chỉ là trả đúng một lần.** Một API bền vững phải xác định **ai sở hữu input, trạng thái sống bao lâu, state dẫn xuất được cập nhật ra sao và nhiều lời gọi có được chồng lấn không**. Những lỗi như `visited` không reset, static state rò giữa test, deep-copy thiếu ở array lồng nhau, cache stale và kết quả trả về lộ internal buffer thường chỉ lộ ra khi viết test lặp, mutation hoặc multi-instance.

Hướng thiết kế an toàn là **snapshot sâu nếu contract không muốn input thay đổi**, **scratch cục bộ mỗi lời gọi nếu muốn gọi đồng thời**, và **reset có kiểm soát nếu tái sử dụng buffer**. Hàm in-place phải được đặt tên/ghi tài liệu rõ. Cache phải gắn với input version/configuration; snapshot cũ và instance mới sau mutation có thể cho **hai kết quả khác nhau mà đều đúng** theo hợp đồng đã tuyên bố.

Kết hợp **kiểm thử A–A–A, A–B–A, mutation trước/sau, output alias, concurrent calls**, cùng oracle khác cấu trúc và chứng minh bất biến sẽ giúp các thuật toán Java hoạt động tin cậy qua **nhiều test case, nhiều request và nhiều lần gọi** — thay vì chỉ đúng trong lần chạy đầu tiên.
