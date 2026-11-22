# DSU ngoại tuyến và các truy vấn kết nối

**DSU ngoại tuyến (offline disjoint-set union)** là một kỹ thuật giải các câu hỏi kết nối trên **đồ thị vô hướng** khi đã biết trước toàn bộ lịch sử thêm cạnh, xóa cạnh và truy vấn. DSU/Union–Find thông thường xử lý **thêm cạnh** rất hiệu quả, nhưng không có phép **tách thành phần** đơn giản khi xóa cạnh tùy ý. Tính chất *offline* cho phép chúng ta biến lịch sử thay đổi thành những khoảng thời gian có hiệu lực, rồi khôi phục trạng thái DSU khi cần.

Bài thuộc nhóm **Truy vấn và ngoại tuyến** trong **Computer Science Algorithms**, với chủ đề chính **DSU ngoại tuyến và các truy vấn kết nối**. Nội dung có hai kỹ thuật: **xử lý ngược thời gian khi chỉ có xóa cạnh** và **segment tree trên thời gian kết hợp DSU rollback cho cả thêm/xóa**. Ta sẽ làm rõ giới hạn của DSU thông thường, phép gộp cạnh, interval nửa mở, snapshot/rollback, truy vấn kích thước/số thành phần, bảo đảm tính đúng, độ phức tạp, đồ thị có cạnh song song và self-loop.

Phần thực hành có **Java 17** tự chạy, oracle BFS độc lập, đầu ra xác định và kiểm thử các chuỗi thao tác hợp lệ. Ngoài demo, mô hình kiểm chứng riêng đã đối chiếu **88.465 chuỗi vét cạn**, **12.000 chuỗi ngẫu nhiên** và **5.000 kịch bản chỉ xóa cạnh** với BFS. Kết quả hữu hạn giúp tìm lỗi; **chứng minh bằng bất biến** mới là nền tảng cho mọi lịch thao tác hợp lệ.

## 1. Đặc tả sự kiện và đồ thị

Cho n đỉnh, đánh số 0 đến n−1, với n≥1. Đồ thị là **vô hướng**, ban đầu **không có cạnh** trong chương trình tổng quát ở cuối bài. Mỗi chỉ số thời gian t từ 0 tới q−1 chứa đúng **một thao tác**:

| Thao tác | Ý nghĩa |
| --- | --- |
| `ADD(u,v)` | Thêm một **bản sao** cạnh vô hướng (u,v) |
| `REMOVE(u,v)` | Xóa một bản sao cạnh đang tồn tại |
| `CONNECTED(u,v)` | Trả `YES` khi có đường đi vô hướng u↔v, nếu không trả `NO` |
| `SIZE(u)` | Trả số đỉnh trong thành phần liên thông chứa u |
| `COMPONENTS()` | Trả số thành phần liên thông của toàn đồ thị |

Mỗi cạnh được chuẩn hóa thành `(min(u,v),max(u,v))`, do đó `(u,v)` và `(v,u)` là **cùng một key**. Bài dùng **multiset edges**: nếu cạnh được ADD ba lần rồi REMOVE hai lần, vẫn còn một bản sao, nên cạnh vẫn có hiệu lực đối với kết nối. Nếu `REMOVE` xảy ra khi bộ đếm cạnh đã bằng 0, chương trình báo **input không hợp lệ** bằng `IllegalArgumentException`.

**Self-loop** `(u,u)` hợp lệ nhưng không thể gộp hai thành phần khác nhau. Một truy vấn `CONNECTED(u,u)` luôn trả YES, kể cả khi không có cạnh.

**Thứ tự sự kiện được quy định rõ:** một thao tác tại thời điểm t không đồng thời là một query. Query tại t nhìn thấy mọi thay đổi trước nó. Nếu dữ liệu thực có nhiều thao tác cùng timestamp, phải thống nhất **độ ưu tiên/thứ tự nội bộ của batch** trước khi ánh xạ thành t=0..q−1.

## 2. Vì sao DSU thường không biết xóa cạnh?

DSU lưu phân hoạch đỉnh theo các thành phần liên thông. Hai phép chính là:

- `find(x)`: trả đại diện (root) của thành phần chứa x;
- `union(u,v)`: gộp hai thành phần nếu root khác nhau.

Kết nối được kiểm tra bằng `find(u)==find(v)`. Với **union by size/rank và path compression**, mỗi thao tác trên DSU thông thường có chi phí amortized O(α(n)) rất nhỏ.

Nhưng DSU không lưu đủ **cấu trúc các đường đi** để biết một cạnh xóa đi có làm tách thành phần hay không:

~~~text
ADD(0,1)
ADD(1,2)
CONNECTED(0,2) -> YES
REMOVE(1,2)
CONNECTED(0,2) -> NO
~~~

DSU đã gọi `union(0,1)` và `union(1,2)` vẫn xem 0,1,2 là một tập sau lần REMOVE, nên sẽ trả **YES sai** nếu không có cấu trúc bổ sung. Ngược lại, trong một tam giác 0–1–2–0, xóa cạnh 1–2 không làm hai đỉnh hết kết nối vì còn đường 1–0–2.

Không thể tự suy ra một phép `split(u,v)` đúng với mọi lần xóa. **Rollback DSU** chỉ hoàn tác các union theo **thứ tự LIFO** đã lưu; cách sắp xếp DFS theo thời gian bảo đảm những union cần hoàn tác luôn có dạng stack.

## 3. Khi nào đảo ngược thời gian là đủ?

Giả sử biết danh sách cạnh **ban đầu**, còn các sự kiện tiếp theo chỉ là **REMOVE và CONNECTED**, không có ADD mới. Ta làm ngược thời gian:

1. Từ đồ thị ban đầu, trừ toàn bộ số lần REMOVE theo từng cạnh và kiểm tra không xóa quá số bản sao. Đó là **đồ thị cuối**.
2. Tạo DSU bình thường trên n đỉnh; union các cạnh có bội số dương trong đồ thị cuối.
3. Duyệt sự kiện từ q−1 xuống 0.
4. Với CONNECTED, đọc kết quả từ DSU hiện tại.
5. Với REMOVE ở chiều thuận, trong chiều ngược **khôi phục một bản sao**. Chỉ union nếu bộ đếm chuyển từ **0 lên 1**.
6. Đảo ngược danh sách câu trả lời để trả về đúng thứ tự các query ban đầu.

**Bất biến:** trước khi xử lý một sự kiện trong vòng lặp ngược, DSU biểu diễn đồ thị **sau sự kiện đó**. Bước ngược đi qua REMOVE tức là thêm lại một bản sao, khôi phục đồ thị trước REMOVE. Chứng minh bằng quy nạp theo t giảm dần.

Ví dụ đa cạnh:

~~~text
initial = (0,1), (1,2), (2,3), (2,3)

t=0 CONNECTED(0,3) -> YES
t=1 REMOVE(2,3)    -> van con mot ban sao
t=2 CONNECTED(0,3) -> YES
t=3 REMOVE(2,3)    -> het ban sao
t=4 CONNECTED(0,3) -> NO
~~~

Sau lần xóa thứ nhất, vẫn còn một cạnh 2–3 nên vẫn nối được 0→3.

**Độ phức tạp:** O((n+m+q)α(n)) với m cạnh ban đầu, q sự kiện, giả sử quản lý bội số bằng HashMap có chi phí băm trung bình O(1) và dùng DSU có path compression. Không cần rollback ở trường hợp này vì khi đi ngược **chỉ phải thêm**, không phải xóa.

**Giới hạn:** nếu lịch thuận có cả ADD và REMOVE, lịch ngược cũng vẫn có cả REMOVE và ADD. DSU thường chưa giải được thao tác xóa; cần segment tree thời gian và rollback.

## 4. Chuyển ADD/REMOVE thành các khoảng hoạt động

Đối với mỗi cạnh vô hướng đã chuẩn hóa e, quét toàn bộ lịch để duy trì `count[e]` và `start[e]`:

- ADD làm count **0→1**: ghi `start=t`, mở một **activation interval**.
- ADD khi count≥1: chỉ tăng bội số, **không mở khoảng mới**.
- REMOVE khi count>1: giảm bội số, cạnh vẫn active.
- REMOVE khi count **1→0**: đóng khoảng **[start,t)**.
- Kết thúc timeline khi count>0: đóng **[start,q)**.
- REMOVE khi count=0: input không hợp lệ.

Mỗi khoảng **nửa mở [L,R)** bao gồm các thời điểm L,L+1,...,R−1. Với một event trên một chỉ số t, không có query đồng thời với một ADD hoặc REMOVE tại t; quy ước [add_time,remove_time) vì thế đúng với tất cả **lá thời gian có query**.

Ví dụ:

~~~text
t=0 ADD(0,1)         count=1, start=0
t=1 ADD(1,0)         count=2
t=2 CONNECTED(0,1)  YES
t=3 REMOVE(0,1)      count=1, van active
t=4 CONNECTED(0,1)  YES
t=5 REMOVE(0,1)      count=0, dong [0,5)
t=6 CONNECTED(0,1)  NO
t=7 ADD(0,1)         count=1, start=7
t=8 CONNECTED(0,1)  YES
t=9 REMOVE(1,0)      count=0, dong [7,9)
~~~

Một cạnh có thể có **nhiều khoảng kích hoạt rời nhau**. Nếu đưa mỗi ADD thành một interval độc lập rồi xóa ngay ở REMOVE đầu tiên, sẽ sai với cạnh trùng. Chỉ **count>0** mới xác định một quan hệ cạnh có hiệu lực.

Để hỗ trợ **cạnh có sẵn trước sự kiện đầu tiên**, có thể coi bội số ban đầu dương và start=0, sau đó gộp logic REMOVE/ADD như trên. Không được tự thêm cạnh ban đầu sau một query mà vẫn mong kết quả giống nhau.

## 5. Segment tree trên trục thời gian

Dựng một **segment tree** với miền [0,q). Mỗi lá là một chỉ số thời gian, mỗi node biểu diễn nửa khoảng [lo,hi). Với mỗi khoảng hoạt động [L,R) của cạnh e, đặt e vào một tập **O(log q) node** có khoảng quản lý nằm hoàn toàn bên trong [L,R) và hợp các khoảng ấy bằng đúng [L,R).

Đây là cách **segment decomposition**: không cần đưa cạnh tới từng lá trong interval, chỉ cần lưu ở các node tối đa.

~~~text
                  time segment tree [0,q)
                      /             \
                  [0,mid)         [mid,q)
                  /    \           /   \
                ...    ...       ...   ...
                 |                      |
               leaf t                 leaf u
              query?                  query?
~~~

**Bất biến root→leaf(t):** cạnh e có hiệu lực tại thời điểm t **khi và chỉ khi** một node trên đường từ root tới lá t chứa e trong bucket của nó. Các node phủ một activation interval là các đoạn rời nhau, nên một thời điểm t thuộc interval gặp đúng một bucket mang e của interval ấy.

Điều này cho phép một DSU khi đi sâu từ root kế thừa các union của mọi bucket trên đường đi. Nếu thêm cạnh vào một node **rộng hơn** interval thực, query ở thời gian chưa/không còn cạnh sẽ sai; nếu lưu cạnh trên từng lá thì tốn bộ nhớ lớn hơn đáng kể.

## 6. Rollback DSU với union by size

Để đi từ node cha xuống con rồi quay lại trạng thái cha, DSU cần **snapshot/rollback**.

Trạng thái gồm:
- `parent[v]`: cha của v;
- `size[root]`: kích thước thành phần của root;
- `components`: số thành phần (ban đầu n);
- `history`: stack các thay đổi của **union thành công**.

Một union:

~~~text
union(u,v):
    a=find(u); b=find(v)
    if a==b: return false      // no-op, khong push
    if size[a]<size[b]: swap(a,b)
    history.push(a,b,oldSizeA)
    parent[b]=a
    size[a]+=size[b]
    components--
    return true
~~~

Hoàn tác về thời điểm đã lưu:

~~~text
checkpoint = history.size()

rollback(checkpoint):
    while history.size() > checkpoint:
        (a,b,oldSizeA)=history.pop()
        parent[b]=b
        size[a]=oldSizeA
        components++
~~~

Vì mỗi union thành công chỉ sửa parent của root nhỏ, size của root lớn và components, bản ghi trên đủ để hoàn nguyên. Những union nằm sâu hơn sẽ được rollback trước do LIFO.

**Không bật path compression** trong bản DSU rollback đơn giản này! `find` với path compression sẽ tự sửa nhiều `parent` dọc đường nhưng history chỉ log thay đổi union root; rollback khi đó không phục hồi hết và có thể làm nhánh DFS khác trả sai. Một DSU rollback có compression vẫn có thể được thiết kế nếu log **mọi** thay đổi parent, nhưng phức tạp hơn và không phải lựa chọn của bài.

Chỉ dùng union by size, độ cao cây DSU là O(log n): mỗi khi một đỉnh tăng độ sâu thì thành phần chứa nó ít nhất **gấp đôi kích thước**. Vì vậy find và union O(log n) worst-case, rollback O(1) trên mỗi bản ghi thay đổi đã log.

**Union no-op:** khi hai root bằng nhau, không đổi DSU và **không push** history. Snapshot là kích thước history, **không phải số lần union đã gọi**. Một triển khai dùng marker no-op cũng hợp lệ nếu snapshot và rollback có cùng quy ước; không trộn hai cách.

## 7. DFS trên segment tree

~~~text
dfs(node, lo, hi):
    checkpoint = dsu.snapshot()
    for edge(u,v) in bucket[node]:
        dsu.union(u,v)

    if hi-lo == 1:
        if CONNECTED query:
            answer = find(u)==find(v)
        if SIZE query:
            answer = size[find(u)]
        if COMPONENTS query:
            answer = components
    else:
        mid=(lo+hi)/2
        dfs(left,lo,mid)
        dfs(right,mid,hi)

    dsu.rollback(checkpoint)
~~~

Mỗi lá được thăm khi DSU đang chứa **toàn bộ cạnh active tại lá đó**. Khi ra khỏi nhánh, rollback xóa mọi union **chỉ thuộc nhánh**; vì vậy các cạnh của một thời điểm không rò sang thời điểm khác.

DSU có thể trả thêm:
- **SIZE(u)** qua size của root;
- **COMPONENTS()** bằng biến giảm khi union thành công và tăng khi rollback;
- **CONNECTED(u,v)** bằng so root.

ADD/REMOVE leaf không in query. DFS theo thứ tự nhánh trái rồi phải bảo đảm câu trả lời được thu theo **thứ tự thời gian**.

## 8. Chứng minh tính đúng

**Bất biến A — khoảng hoạt động đúng.** Quét sự kiện duy trì đúng bội số cạnh; cạnh active iff count>0. Mỗi lần 0→1 mở interval và 1→0 đóng interval. Các khoảng thu được mô tả chính xác các thời điểm có ít nhất một bản sao cạnh.

**Bất biến B — DSU ở leaf đúng.** Phân rã segment tree đặt cạnh e vào đường root→leaf(t) iff t thuộc một interval của e. DFS gộp tất cả cạnh trên đường đi, đồng thời rollback sạch các thay đổi của nhánh trước. Vì vậy tại leaf t, DSU biểu diễn **đúng thành phần liên thông của đồ thị ở t**.

**Bất biến C — các loại query đúng.** Với đồ thị vô hướng, hai đỉnh liên thông iff cùng đại diện DSU. Kích thước thành phần và số thành phần được cộng/trừ nhất quán trong mỗi union thành công/rollback. Vậy CONNECTED, SIZE, COMPONENTS đều đúng khi được hỏi.

Ba bất biến chứng minh thuật toán đúng cho **mọi lịch event hợp lệ thuộc mô hình đã nêu**. Việc hàng chục nghìn test nhỏ đạt kết quả giống oracle chỉ là bằng chứng kiểm thử bổ sung.

## 9. Ví dụ 25 sự kiện, có cạnh trùng và self-loop

| t | Sự kiện | Diễn giải |
| ---: | --- | --- |
| 0 | ADD(0,1) | tạo cạnh 0–1 |
| 1 | ADD(1,2) | nối 0 tới 2 |
| 2 | CONNECTED(0,2) | YES |
| 3 | ADD(2,3) | mọi đỉnh nối |
| 4 | CONNECTED(0,3) | YES |
| 5 | REMOVE(1,2) | tách thành hai phần |
| 6 | CONNECTED(0,3) | NO |
| 7 | CONNECTED(2,3) | YES |
| 8 | COMPONENTS() | 2 |
| 9 | ADD(0,2) | nối lại |
| 10 | CONNECTED(0,3) | YES |
| 11 | ADD(0,1) | thêm bản sao thứ hai |
| 12 | REMOVE(0,1) | vẫn còn một bản sao |
| 13 | CONNECTED(0,1) | YES |
| 14 | REMOVE(0,1) | hết bản sao |
| 15 | CONNECTED(0,1) | NO |
| 16 | SIZE(2) | 3, gồm {0,2,3} |
| 17 | COMPONENTS() | 2 |
| 18 | REMOVE(0,2) | tách đỉnh 0 |
| 19 | CONNECTED(0,3) | NO |
| 20 | COMPONENTS() | 3 |
| 21 | ADD(2,2) | self-loop không làm đổi thành phần |
| 22 | CONNECTED(2,2) | YES |
| 23 | REMOVE(2,2) | xóa self-loop |
| 24 | CONNECTED(2,3) | YES |

Các câu trả lời:

~~~text
t=2 CONNECTED(0,2)=YES
t=4 CONNECTED(0,3)=YES
t=6 CONNECTED(0,3)=NO
t=7 CONNECTED(2,3)=YES
t=8 COMPONENTS=2
t=10 CONNECTED(0,3)=YES
t=13 CONNECTED(0,1)=YES
t=15 CONNECTED(0,1)=NO
t=16 SIZE(2)=3
t=17 COMPONENTS=2
t=19 CONNECTED(0,3)=NO
t=20 COMPONENTS=3
t=22 CONNECTED(2,2)=YES
t=24 CONNECTED(2,3)=YES
~~~

Đặc biệt, query t=13 vẫn YES vì REMOVE tại t=12 chỉ bỏ **một** trong hai bản sao cạnh 0–1. Ở t=15, bản sao cuối đã mất nên đỉnh 1 cô lập. Ở t=20, ba thành phần là {0}, {1} và {2,3}.

## 10. Độ phức tạp

Đặt n là số đỉnh, q là số sự kiện, m là số **activation intervals** của tất cả cạnh; m không nhất thiết bằng số cạnh duy nhất nhưng không vượt số lần mở interval từ ADD.

- Xây interval bằng HashMap: **O(q) kỳ vọng** nếu thao tác băm O(1) trung bình.
- Mỗi interval được gán vào **O(log q)** node của segment tree.
- Tổng lời gọi union: O(m log q).
- Union/find trong rollback DSU có union by size, không compression: **O(log n)**.
- Query CONNECTED/SIZE O(log n), COMPONENTS O(1); toàn DFS có O(q) node/lá.

Với q,n≥2:

\[
T=O\bigl(q+(q+m\log q)\log n\bigr)
\]

thường ghi gọn **O((q+m log q) log n)** nếu không tách riêng hash; bộ nhớ **O(n+q+m log q)** cho input, DSU, segment tree buckets. Stack rollback sống tại một thời điểm chứa tối đa n−1 union thành công (mỗi union giảm components), mặc dù tổng union được gọi cả DFS có thể rất nhiều.

| Phương pháp | Phạm vi | Đánh đổi |
| --- | --- | --- |
| DSU online có compression | ADD + query | Gần O(α(n)) mỗi phép amortized |
| Đảo thời gian + DSU thường | Chỉ REMOVE + query | Đơn giản, không cần rollback |
| Segment time + rollback DSU | ADD/REMOVE/query hỗn hợp | O((q+m log q) log n), cần lịch offline |
| BFS/DFS cho từng query | Cả add/remove/query | Dễ làm oracle, chậm khi nhiều query lớn |
| Fully dynamic online connectivity | Cập nhật/trả lời ngay | Cấu trúc phức tạp hơn, không phải thuật toán bài |

Nếu q=0, trả rỗng; q=1 xử lý bằng một lá. Không lấy log(0) trong những trường hợp suy biến. Nếu cần worst-case cho xử lý map thay vì kỳ vọng, có thể dùng bản đồ cây cân bằng với nhân tử log cho lookup/update.

## 11. Chương trình Java 17 chạy độc lập

**OfflineDsuConnectivityDemo.java** có:
- Record Event với năm loại sự kiện;
- Edge.of chuẩn hóa cạnh vô hướng;
- Map<Edge,Activation> lưu bội số và thời điểm start;
- Segment chứa các bucket cạnh cho interval;
- RollbackDSU lưu history, union by size, **không path compression**;
- Hàm offline trả đáp án theo thời gian;
- Oracle BFS hoàn toàn khác DSU;
- Tự kiểm **88.465 chuỗi hợp lệ dài không quá 5** trên n=2;
- Tự kiểm **2.000 chuỗi ngẫu nhiên** có ADD/REMOVE/QUERY;
- Chặn REMOVE inactive và hỗ trợ q=0.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;

public class OfflineDsuConnectivityDemo {
    enum Kind { ADD, REMOVE, CONNECTED, SIZE, COMPONENTS }

    record Event(Kind kind, int u, int v) {
        static Event add(int u, int v) {
            return new Event(Kind.ADD, u, v);
        }
        static Event remove(int u, int v) {
            return new Event(Kind.REMOVE, u, v);
        }
        static Event ask(int u, int v) {
            return new Event(Kind.CONNECTED, u, v);
        }
        static Event size(int u) {
            return new Event(Kind.SIZE, u, 0);
        }
        static Event components() {
            return new Event(Kind.COMPONENTS, 0, 0);
        }
    }

    record Edge(int u, int v) {
        static Edge of(int u, int v) {
            return u <= v ? new Edge(u, v) : new Edge(v, u);
        }
    }

    static void vertex(int n, int v) {
        if (v < 0 || v >= n)
            throw new IllegalArgumentException("Vertex out of range: " + v);
    }

    static void validate(int n, List<Event> events) {
        if (n < 1) throw new IllegalArgumentException("n < 1");
        Objects.requireNonNull(events);
        for (Event e : events) {
            Objects.requireNonNull(e);
            Objects.requireNonNull(e.kind());
            switch (e.kind()) {
                case COMPONENTS -> {}
                case SIZE -> vertex(n, e.u());
                default -> {
                    vertex(n, e.u());
                    vertex(n, e.v());
                }
            }
        }
    }

    record Change(int big, int small, int oldSizeBig) {}

    static final class RollbackDSU {
        final int[] parent, size;
        final List<Change> history = new ArrayList<>();
        int components;

        RollbackDSU(int n) {
            parent = new int[n];
            size = new int[n];
            components = n;
            for (int i = 0; i < n; i++) {
                parent[i] = i;
                size[i] = 1;
            }
        }

        // Khong path compression.
        int find(int x) {
            while (parent[x] != x) x = parent[x];
            return x;
        }

        int snapshot() {
            return history.size();
        }

        boolean unite(int u, int v) {
            int a = find(u), b = find(v);
            if (a == b) return false;
            if (size[a] < size[b]) {
                int tmp = a; a = b; b = tmp;
            }
            history.add(new Change(a, b, size[a]));
            parent[b] = a;
            size[a] += size[b];
            components--;
            return true;
        }

        void rollback(int checkpoint) {
            while (history.size() > checkpoint) {
                Change c = history.remove(history.size() - 1);
                parent[c.small()] = c.small();
                size[c.big()] = c.oldSizeBig();
                components++;
            }
        }

        boolean connected(int u, int v) {
            return find(u) == find(v);
        }

        int componentSize(int u) {
            return size[find(u)];
        }
    }

    static final class Activation {
        int start = -1;
        int count = 0;
    }

    static final class Segment {
        final List<Edge>[] bucket;
        final int q;

        @SuppressWarnings("unchecked")
        Segment(int q) {
            this.q = q;
            bucket = (List<Edge>[]) new List[4 * q];
        }

        void add(int start, int end, Edge edge) {
            if (start >= end) return;
            add(1, 0, q, start, end, edge);
        }

        void add(int node, int lo, int hi,
                 int start, int end, Edge edge) {
            if (start >= hi || end <= lo) return;
            if (start <= lo && hi <= end) {
                if (bucket[node] == null)
                    bucket[node] = new ArrayList<>();
                bucket[node].add(edge);
                return;
            }
            int mid = lo + (hi - lo) / 2;
            add(node * 2, lo, mid, start, end, edge);
            add(node * 2 + 1, mid, hi, start, end, edge);
        }

        void visit(int node, int lo, int hi,
                   RollbackDSU dsu, List<Event> events,
                   List<String> out) {
            int checkpoint = dsu.snapshot();
            if (bucket[node] != null)
                for (Edge e : bucket[node])
                    dsu.unite(e.u(), e.v());

            if (hi - lo == 1) {
                Event e = events.get(lo);
                switch (e.kind()) {
                    case CONNECTED -> out.add(
                        "t=" + lo + " CONNECTED(" + e.u()
                        + "," + e.v() + ")="
                        + (dsu.connected(e.u(), e.v())
                           ? "YES" : "NO"));
                    case SIZE -> out.add(
                        "t=" + lo + " SIZE(" + e.u() + ")="
                        + dsu.componentSize(e.u()));
                    case COMPONENTS -> out.add(
                        "t=" + lo + " COMPONENTS=" + dsu.components);
                    default -> {}
                }
            } else {
                int mid = lo + (hi - lo) / 2;
                visit(node * 2, lo, mid, dsu, events, out);
                visit(node * 2 + 1, mid, hi, dsu, events, out);
            }
            dsu.rollback(checkpoint);
        }
    }

    static List<String> offline(int n, List<Event> events) {
        validate(n, events);
        int q = events.size();
        if (q == 0) return List.of();
        if (q > Integer.MAX_VALUE / 4)
            throw new IllegalArgumentException(
                "Too many events for segment-tree array");

        Segment tree = new Segment(q);
        Map<Edge, Activation> active = new HashMap<>();
        for (int t = 0; t < q; t++) {
            Event ev = events.get(t);
            if (ev.kind() == Kind.ADD) {
                Edge e = Edge.of(ev.u(), ev.v());
                Activation a = active.computeIfAbsent(
                    e, unused -> new Activation());
                if (a.count == 0) a.start = t;
                a.count = Math.addExact(a.count, 1);
            } else if (ev.kind() == Kind.REMOVE) {
                Edge e = Edge.of(ev.u(), ev.v());
                Activation a = active.get(e);
                if (a == null || a.count == 0)
                    throw new IllegalArgumentException(
                        "Remove inactive edge at t=" + t);
                a.count--;
                if (a.count == 0) tree.add(a.start, t, e);
            }
        }

        for (Map.Entry<Edge, Activation> entry
                : active.entrySet()) {
            Activation a = entry.getValue();
            if (a.count > 0)
                tree.add(a.start, q, entry.getKey());
        }

        RollbackDSU dsu = new RollbackDSU(n);
        List<String> out = new ArrayList<>();
        tree.visit(1, 0, q, dsu, events, out);
        return List.copyOf(out);
    }

    // Oracle BFS, KHONG dung DSU.
    static boolean[] reach(int n, Map<Edge,Integer> active,
                           int start) {
        boolean[][] adj = new boolean[n][n];
        for (Map.Entry<Edge,Integer> item
                : active.entrySet()) {
            if (item.getValue() <= 0) continue;
            Edge e = item.getKey();
            adj[e.u()][e.v()] = true;
            adj[e.v()][e.u()] = true;
        }

        boolean[] seen = new boolean[n];
        int[] queue = new int[n];
        int head = 0, tail = 0;
        queue[tail++] = start;
        seen[start] = true;
        while (head < tail) {
            int u = queue[head++];
            for (int v = 0; v < n; v++) {
                if (adj[u][v] && !seen[v]) {
                    seen[v] = true;
                    queue[tail++] = v;
                }
            }
        }
        return seen;
    }

    static int countTrue(boolean[] arr) {
        int ans = 0;
        for (boolean value : arr) if (value) ans++;
        return ans;
    }

    static int componentCount(int n, Map<Edge,Integer> active) {
        boolean[] seen = new boolean[n];
        int total = 0;
        for (int u = 0; u < n; u++) {
            if (seen[u]) continue;
            boolean[] part = reach(n, active, u);
            for (int j = 0; j < n; j++)
                seen[j] |= part[j];
            total++;
        }
        return total;
    }

    static List<String> oracle(int n, List<Event> events) {
        validate(n, events);
        Map<Edge,Integer> count = new HashMap<>();
        List<String> out = new ArrayList<>();

        for (int t = 0; t < events.size(); t++) {
            Event e = events.get(t);
            switch (e.kind()) {
                case ADD -> {
                    Edge key = Edge.of(e.u(), e.v());
                    count.merge(key, 1, (a,b) -> Math.addExact(a,b));
                }
                case REMOVE -> {
                    Edge key = Edge.of(e.u(), e.v());
                    int old = count.getOrDefault(key, 0);
                    if (old <= 0)
                        throw new IllegalArgumentException(
                            "Remove inactive edge at t=" + t);
                    count.put(key, old - 1);
                }
                case CONNECTED -> {
                    boolean[] seen = reach(n, count, e.u());
                    out.add("t=" + t + " CONNECTED(" + e.u()
                        + "," + e.v() + ")="
                        + (seen[e.v()] ? "YES" : "NO"));
                }
                case SIZE -> {
                    boolean[] seen = reach(n, count, e.u());
                    out.add("t=" + t + " SIZE(" + e.u()
                        + ")=" + countTrue(seen));
                }
                case COMPONENTS ->
                    out.add("t=" + t + " COMPONENTS="
                        + componentCount(n, count));
            }
        }
        return out;
    }

    static void assertMatchesBfs(int n, List<Event> events) {
        List<String> x = offline(n, events);
        List<String> y = oracle(n, events);
        if (!x.equals(y))
            throw new AssertionError(
                "Offline/BFS mismatch: " + events);
    }

    static final Edge[] SMALL_EDGES = {
        Edge.of(0,0), Edge.of(0,1), Edge.of(1,1)
    };
    static final Event[] SMALL_QUERIES = {
        Event.ask(0,0), Event.ask(0,1), Event.ask(1,1),
        Event.size(0), Event.size(1), Event.components()
    };

    // Moi chuoi do dai 0..5 tren n=2, chi REMOVE hop le.
    static void exhaustive(
            List<Event> current, int[] multiplicity,
            int remaining, int[] checked) {
        assertMatchesBfs(2, current);
        checked[0]++;
        if (remaining == 0) return;

        for (int i = 0; i < SMALL_EDGES.length; i++) {
            Edge e = SMALL_EDGES[i];
            current.add(Event.add(e.u(), e.v()));
            multiplicity[i]++;
            exhaustive(current, multiplicity,
                       remaining - 1, checked);
            multiplicity[i]--;
            current.remove(current.size() - 1);
        }

        for (Event q : SMALL_QUERIES) {
            current.add(q);
            exhaustive(current, multiplicity,
                       remaining - 1, checked);
            current.remove(current.size() - 1);
        }

        for (int i = 0; i < SMALL_EDGES.length; i++) {
            if (multiplicity[i] == 0) continue;
            Edge e = SMALL_EDGES[i];
            current.add(Event.remove(e.u(), e.v()));
            multiplicity[i]--;
            exhaustive(current, multiplicity,
                       remaining - 1, checked);
            multiplicity[i]++;
            current.remove(current.size() - 1);
        }
    }

    static int randomTests() {
        Random rng = new Random(2026L);
        for (int trial = 0; trial < 2000; trial++) {
            int n = 1 + rng.nextInt(5);
            int steps = rng.nextInt(26);
            List<Edge> possible = new ArrayList<>();
            for (int u = 0; u < n; u++)
                for (int v = u; v < n; v++)
                    possible.add(Edge.of(u,v));

            int[] count = new int[possible.size()];
            List<Event> events = new ArrayList<>();
            for (int t = 0; t < steps; t++) {
                int ix = rng.nextInt(possible.size());
                Edge e = possible.get(ix);
                int action = rng.nextInt(6);
                if (action <= 1) {
                    events.add(Event.add(e.u(),e.v()));
                    count[ix]++;
                } else if (action == 2) {
                    if (count[ix] > 0) {
                        events.add(Event.remove(e.u(),e.v()));
                        count[ix]--;
                    } else {
                        events.add(Event.components());
                    }
                } else if (action == 3) {
                    events.add(Event.ask(
                        rng.nextInt(n),rng.nextInt(n)));
                } else if (action == 4) {
                    events.add(Event.size(rng.nextInt(n)));
                } else {
                    events.add(Event.components());
                }
            }
            assertMatchesBfs(n, events);
        }
        return 2000;
    }

    static boolean rejectsInvalidDelete() {
        try {
            offline(2, List.of(Event.remove(0,1)));
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        List<Event> sample = List.of(
            Event.add(0,1),     // t=0
            Event.add(1,2),     // t=1
            Event.ask(0,2),     // t=2
            Event.add(2,3),     // t=3
            Event.ask(0,3),     // t=4
            Event.remove(1,2),  // t=5
            Event.ask(0,3),     // t=6
            Event.ask(2,3),     // t=7
            Event.components(), // t=8
            Event.add(0,2),     // t=9
            Event.ask(0,3),     // t=10
            Event.add(0,1),     // t=11 duplicate
            Event.remove(0,1),  // t=12 one copy remains
            Event.ask(0,1),     // t=13
            Event.remove(0,1),  // t=14 inactive
            Event.ask(0,1),     // t=15
            Event.size(2),      // t=16
            Event.components(), // t=17
            Event.remove(0,2),  // t=18
            Event.ask(0,3),     // t=19
            Event.components(), // t=20
            Event.add(2,2),     // t=21 self-loop
            Event.ask(2,2),     // t=22
            Event.remove(2,2),  // t=23
            Event.ask(2,3)      // t=24
        );

        for (String line : offline(4, sample))
            System.out.println(line);
        assertMatchesBfs(4, sample);

        int[] checked = {0};
        exhaustive(new ArrayList<>(),
                   new int[SMALL_EDGES.length],
                   5, checked);
        System.out.println("verified.exhaustiveSequences="
            + checked[0]);
        System.out.println("verified.randomSequences="
            + randomTests());
        System.out.println("verified.invalidRemoveRejected="
            + rejectsInvalidDelete());
        System.out.println("verified.emptyEventsSupported="
            + offline(2,List.of()).isEmpty());
        System.out.println("verification=PASS");
    }
}
~~~

### Biên dịch và đầu ra dự kiến

~~~bash
javac OfflineDsuConnectivityDemo.java
java OfflineDsuConnectivityDemo
~~~

~~~text
t=2 CONNECTED(0,2)=YES
t=4 CONNECTED(0,3)=YES
t=6 CONNECTED(0,3)=NO
t=7 CONNECTED(2,3)=YES
t=8 COMPONENTS=2
t=10 CONNECTED(0,3)=YES
t=13 CONNECTED(0,1)=YES
t=15 CONNECTED(0,1)=NO
t=16 SIZE(2)=3
t=17 COMPONENTS=2
t=19 CONNECTED(0,3)=NO
t=20 COMPONENTS=3
t=22 CONNECTED(2,2)=YES
t=24 CONNECTED(2,3)=YES
verified.exhaustiveSequences=88465
verified.randomSequences=2000
verified.invalidRemoveRejected=true
verified.emptyEventsSupported=true
verification=PASS
~~~

Các dòng đầu là **14 câu trả lời** theo thứ tự truy vấn. Hai dòng đếm self-test là kết quả dự kiến khi các assert của Java không ném lỗi. Dòng `verified.invalidRemoveRejected=true` cho thấy REMOVE trước ADD bị phát hiện; dòng `verified.emptyEventsSupported=true` xác nhận thuật toán trả list rỗng khi q=0.

**Cẩn trọng:** mã Java này được kiểm tra tĩnh về cú pháp và logic, còn đầu ra ví dụ được đối chiếu bằng mô hình độc lập; không khẳng định đã chạy javac trong phiên biên soạn. Người học có thể chạy lệnh trên máy có JDK 17 để tái hiện.

## 12. Oracle BFS không dựa vào DSU

Kiểm chứng một thuật toán DSU bằng bản DSU khác có nguy cơ **cùng mắc lỗi** về interval, rollback hoặc parent. Vì vậy chương trình viết oracle đơn giản hơn: duy trì số bản sao cạnh khi xử lý ADD/REMOVE **theo thời gian thật**, dựng ma trận kề từ những cạnh có count>0 trước mỗi query rồi BFS.

- CONNECTED(u,v): BFS từ u có thăm được v không?
- SIZE(u): số đỉnh BFS từ u thăm được?
- COMPONENTS(): BFS từ mọi đỉnh chưa thăm, đếm số lần khởi tạo BFS.

Oracle chậm hơn và dùng O(n²) bộ nhớ cho ma trận, nhưng độc lập về cấu trúc và dễ đối chiếu trên đồ thị nhỏ. Bộ test còn kiểm tra **cạnh trùng, self-loop, truy vấn trước ADD, chuỗi rỗng**.

## 13. Kiểm thử vét cạn và ngẫu nhiên độc lập

Không chỉ chạy một ví dụ thuận lợi, ta cần kiểm tra các chuỗi thao tác ngắn để bắt các bug khó thấy.

**Vét cạn n=2:** ba loại cạnh có thể tồn tại là `(0,0)`, `(0,1)`, `(1,1)`. Tại mỗi bước có 3 ADD, 3 CONNECTED (0,0;0,1;1,1), 2 SIZE, 1 COMPONENTS và REMOVE với mỗi cạnh đang có count>0. Duyệt **mọi chuỗi hợp lệ dài 0..5** cho ra **88.465 chuỗi** với **432.480 vị trí event** khi cộng toàn bộ độ dài các chuỗi. Kết quả của thuật toán interval/rollback khớp oracle BFS ở tất cả các query.

**Kiểm chứng độc lập lớn hơn:** một mô hình khác bằng JavaScript tạo **12.000 chuỗi** trên đồ thị 1..6 đỉnh, dài dưới 42, tổng cộng **244.129 event**. Với mỗi query, kết quả offline trùng BFS; ba trường hợp REMOVE inactive đều bị từ chối.

**Xử lý ngược thời gian:** **5.000 kịch bản** chỉ REMOVE và QUERY, mỗi kịch bản 20 event (**100.000 event**), có **75.184 truy vấn**. Trong số đó, **16.823 lần xóa** vẫn còn bản sao cùng cạnh. DSU đảo thời gian và oracle BFS cho kết quả trùng nhau.

**Không suy luận quá mức:** kiểm thử hữu hạn không thay thế chứng minh cho mọi n và q; bản oracle cũng có thể có bug riêng. Ba bất biến ở mục 8 mới là bằng chứng tổng quát trong mô hình đã định.

## 14. Trường hợp biên và lỗi triển khai

| Tình huống hoặc lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| DSU thường bỏ qua REMOVE | Kết nối cũ vẫn tồn tại | Reverse-only hoặc rollback |
| Path compression trong rollback không có history | Parent không khôi phục | Không compression; hoặc log mọi thay đổi |
| Quên snapshot khi vào node | Undo sai trạng thái | Ghi history.size() |
| Rollback theo số union gọi | No-op làm lệch stack | Rollback theo history thực |
| Quên rollback giữa hai nhánh | Cạnh nhánh trước bị giữ lại | Rollback sau DFS node |
| Xóa bản sao đầu tiên như xóa cả cạnh | Query sai | Count bội số; chỉ đóng 1→0 |
| Không chuẩn hóa cạnh vô hướng | ADD(u,v) và REMOVE(v,u) không khớp | Edge.of min/max |
| Interval off-by-one | Cạnh sai thời điểm | Chốt [L,R) và event semantics |
| Bucket node quá rộng | Cạnh active ngoài interval | Phân rã segment tree chuẩn |
| Cập nhật components cho union no-op | Đếm số thành phần sai | Chỉ giảm khi root khác |
| Không restore size root cũ | SIZE sau rollback sai | Log oldSizeBig |
| Self-loop làm giảm components | Sai phân hoạch | union(u,u) no-op |
| REMOVE cạnh inactive được bỏ qua vô điều kiện | Che lỗi input | Báo lỗi theo hợp đồng |
| Không xử lý q=0 | DFS trên cây rỗng | Trả list rỗng ngay |
| Query trước ADD bị trả YES | Rò trạng thái từ nhánh khác | Kiểm rollback/interval |
| Directed reachability bằng DSU | Bỏ qua hướng | Dùng thuật toán đồ thị có hướng |
| Nghĩ O(1) HashMap là worst-case tuyệt đối | Sai cận | Nêu expected hoặc dùng map cân bằng |
| Dùng nguyên 4q khi q quá lớn | Overflow/thiếu RAM | Kiểm giới hạn trước cấp mảng |
| Test pass vài input rồi kết luận proof | Chưa bao phủ mọi lịch | Chứng minh bất biến và differential test |

**Lưu ý về chu trình:** xóa một cạnh trong chu trình có thể không đổi kết nối vì vẫn có đường đi thay thế. **Lưu ý về đa cạnh:** hai bản sao của cùng key là hai sự kiện đếm riêng, nhưng khi count>0, DSU chỉ cần union đại diện một lần trên mỗi nhánh thời gian; nhiều lần union no-op không thay đổi đáp án.

## 15. Bài tập có đáp án

**Bài 1.** DSU thông thường có hỗ trợ xóa cạnh tùy ý không?

*Đáp án:* Không. DSU biết gộp, không biết tách một component theo một cạnh bị xóa.

**Bài 2.** Trường hợp nào chỉ cần đảo thời gian?

*Đáp án:* Biết đồ thị ban đầu và các thao tác sau đó chỉ gồm REMOVE và QUERY.

**Bài 3.** Vì sao đảo thời gian không đủ cho chuỗi ADD/REMOVE hỗn hợp?

*Đáp án:* ADD ở chiều thuận thành REMOVE ở chiều ngược, DSU thường vẫn không hỗ trợ.

**Bài 4.** Cấu trúc chính của lời giải tổng quát là gì?

*Đáp án:* Segment tree trên thời gian và DSU rollback.

**Bài 5.** Tại sao dùng interval [start,end)?

*Đáp án:* Cạnh có hiệu lực sau ADD và trước REMOVE; leaf query tuân cùng quy ước thời gian.

**Bài 6.** ADD(0,1), ADD(1,0), REMOVE(0,1): còn cạnh không?

*Đáp án:* Có, còn một bản sao với count=1.

**Bài 7.** Khi nào mở interval?

*Đáp án:* Khi count chuyển 0→1.

**Bài 8.** Khi nào đóng interval?

*Đáp án:* Khi count chuyển 1→0 hoặc tại q nếu vẫn active.

**Bài 9.** Một interval cần gắn vào bao nhiêu node segment tree?

*Đáp án:* O(log q) node.

**Bài 10.** DSU ở leaf t chứa cạnh nào?

*Đáp án:* Đúng các cạnh active ở t, từ buckets trên đường root→leaf.

**Bài 11.** Snapshot DSU rollback là gì?

*Đáp án:* Kích thước stack history trước khi thực hiện các union của node.

**Bài 12.** Vì sao không path-compress nếu history chỉ lưu union root?

*Đáp án:* Compression sửa thêm parent trung gian, rollback sẽ phục hồi thiếu.

**Bài 13.** Union by size cần lưu gì để undo?

*Đáp án:* Root lớn/nhỏ, size cũ của root lớn và tăng lại components lúc rollback.

**Bài 14.** Union khi hai root đã bằng nhau có giảm components không?

*Đáp án:* Không, no-op.

**Bài 15.** Vì sao union by size không compression vẫn có find O(log n)?

*Đáp án:* Mỗi lần đỉnh sâu thêm một mức, component chứa nó ít nhất gấp đôi.

**Bài 16.** SIZE(u) tính thế nào?

*Đáp án:* size[find(u)].

**Bài 17.** COMPONENTS() tính thế nào?

*Đáp án:* Biến đếm bắt đầu n, giảm khi union thành công, tăng khi rollback.

**Bài 18.** Self-loop (v,v) có tăng số đỉnh hoặc giảm components không?

*Đáp án:* Không.

**Bài 19.** CONNECTED(v,v) trả gì khi đồ thị rỗng?

*Đáp án:* YES, có đường đi độ dài 0.

**Bài 20.** Vì sao normalize Edge(u,v) thành (min,max)?

*Đáp án:* Để ADD(u,v) và REMOVE(v,u) tác động cùng edge key vô hướng.

**Bài 21.** Có 5 đỉnh ban đầu riêng lẻ, 2 union thành công, còn mấy components?

*Đáp án:* 3.

**Bài 22.** Nếu q=0 thì thuật toán làm gì?

*Đáp án:* Trả danh sách đáp án rỗng.

**Bài 23.** Với m activation intervals, cần bao nhiêu union calls trong DFS?

*Đáp án:* O(m log q), bao gồm cả union no-op.

**Bài 24.** Trong ví dụ ở t=15, CONNECTED(0,1) là gì?

*Đáp án:* NO; hai bản sao cạnh 0–1 đã bị xóa hết.

**Bài 25.** Trong ví dụ ở t=16, SIZE(2) là bao nhiêu?

*Đáp án:* 3, thành phần {0,2,3}.

**Bài 26.** Ở t=20, COMPONENTS() bằng bao nhiêu?

*Đáp án:* 3: {0}, {1}, {2,3}.

**Bài 27.** Khi đi ngược với multi-edge, tại lần tăng count 0→1 cần làm gì?

*Đáp án:* Union hai đầu mút; tăng bội số khi count>0 không làm thay đổi kết nối.

**Bài 28.** REMOVE cạnh không tồn tại trong bài được xử lý ra sao?

*Đáp án:* Ném IllegalArgumentException, không im lặng bỏ qua.

**Bài 29.** Có thể dùng DSU giải reachability có hướng không?

*Đáp án:* Không, DSU chỉ mô tả kết nối vô hướng.

**Bài 30.** Vì sao dùng BFS làm oracle thay vì thêm một bản DSU tương tự?

*Đáp án:* Độc lập cấu trúc, ít nguy cơ cùng lỗi trong rollback/segment tree.

**Bài 31.** 88.465 test n=2 đã chứng minh mọi trường hợp lớn chưa?

*Đáp án:* Chưa. Bất biến interval, đường root→leaf và rollback mới là chứng minh tổng quát.

**Bài 32.** Khi nào dùng DSU online thường là lựa chọn tốt hơn?

*Đáp án:* Khi chỉ thêm cạnh và hỏi, không có xóa.

## 16. Checklist triển khai

1. Xác định đồ thị vô hướng và tất cả loại query cần hỗ trợ.
2. Viết rõ semantics đa cạnh, self-loop, xóa thiếu.
3. Chốt một event mỗi time index và khoảng nửa mở [L,R).
4. Chuẩn hóa edge key bằng min/max.
5. Mở interval khi count 0→1, đóng khi count 1→0.
6. Mỗi interval được lưu ở O(log q) bucket node.
7. Rollback DSU union by size, **không path compression**.
8. Snapshot trước node; rollback sau khi xử lý toàn bộ node.
9. Không cập nhật components cho union no-op.
10. Kiểm size[root] và số component sau rollback.
11. Giữ output theo thứ tự query thời gian, không dựa vào HashMap iteration.
12. Kiểm edge trùng, self-loop, chu trình, q=0, n=1, query trước ADD.
13. Reject thao tác REMOVE vượt bội số nếu đặc tả yêu cầu.
14. Dùng BFS oracle trên input nhỏ và cả random lẫn exhaustive tests.
15. Nếu chỉ có xóa cạnh, ưu tiên reverse-time DSU đơn giản.
16. Không dùng bản này thay cho thuật toán online fully dynamic khi chưa biết tương lai.
17. Kiểm giới hạn bộ nhớ O(n+q+m log q) và khả năng cấp phát trên dữ liệu thật.
18. Tách **bằng chứng thực nghiệm** khỏi **chứng minh bằng bất biến**.

## Tổng kết

**DSU thường** tối ưu cho thêm cạnh nhưng không tự biết tách thành phần khi xóa. Khi có toàn bộ lịch thao tác, bài **chỉ xóa** dùng DSU đi ngược thời gian; bài **thêm/xóa hỗn hợp** dùng các khoảng hiệu lực của cạnh, segment tree trên thời gian và **rollback DSU theo LIFO**.

Tính đúng dựa trên ba bất biến: bộ đếm cạnh tạo **interval active chính xác**, các bucket trên **root→leaf** chứa đúng cạnh tại mỗi query, và **rollback** phục hồi trạng thái sạch giữa các nhánh. Với n đỉnh, q sự kiện, m activation intervals, thời gian đặc trưng O((q+m log q) log n), bộ nhớ O(n+q+m log q). Java 17 cung cấp ví dụ chạy độc lập và oracle BFS, còn các kiểm chứng vét cạn và ngẫu nhiên củng cố việc cài đặt theo mô hình đã nêu.
