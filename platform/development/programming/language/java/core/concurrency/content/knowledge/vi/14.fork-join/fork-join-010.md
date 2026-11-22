# Task dependency và nguy cơ chờ vòng trong Fork/Join

## 1. Mục tiêu

`ForkJoinPool` là một executor chuyên xử lý nhiều tác vụ có thể phân rã thành các subtasks. Thuật toán điển hình chia vấn đề lớn thành những nhánh độc lập, chạy các nhánh đó khi có workers, rồi ghép kết quả bằng `join()`. Cơ chế **work-stealing** giúp workers tìm thêm việc từ những worker khác.

Điểm giới hạn quan trọng: **work-stealing không tự phát hiện hoặc chữa được vòng chờ logic**. Nếu tác vụ A chỉ hoàn tất khi B hoàn tất, còn B lại cần A, thì A→B→A là dependency cycle. Thêm workers không tạo ra thứ tự hoàn tất hợp lệ. Javadoc `ForkJoinTask` khuyến nghị các phụ thuộc completion của `join()` phải **không có chu trình** — tức là một **DAG (Directed Acyclic Graph)**.

Bài học này giúp bạn:
- Biết phân biệt `fork()`, `compute()`, `join()`, `ForkJoinPool.invoke()`, `ForkJoinTask.invokeAll()` và `Future.get()`.
- Vẽ và đọc đồ thị phụ thuộc của tác vụ, phát hiện self-join và vòng chờ A→B→C→A.
- Dùng mẫu `fork một nhánh → compute nhánh còn lại → join` để tạo cấu trúc chia để trị rõ ràng.
- Nhận diện deadlock từ resource locks, permits, external I/O hoặc một completion signal không bao giờ xuất hiện.
- Hiểu tác dụng và giới hạn của `ForkJoinPool.ManagedBlocker` khi worker chờ những hoạt động không thuộc Fork/Join.
- Lựa chọn giữa `RecursiveTask`, `RecursiveAction`, `CountedCompleter` và các phối hợp DAG theo giai đoạn.
- Thực hành ba chương trình Java 17+ độc lập: tổng mảng, ghép các nhánh và kiểm tra graph có cycle trước khi submit.
- Có checklist code review, quan sát thread dumps và trả lời các tình huống thực tế.

**Phạm vi:** Java SE concurrency nói chung, không dùng framework.

## 2. Fork, compute, join là ba hành vi khác nhau

`fork()` đặt một `ForkJoinTask` vào luồng xử lý bất đồng bộ thích hợp; task trở thành ứng viên được workers thực thi. `compute()` là logic trực tiếp của subclass, còn `join()` chờ task được nhắc đến hoàn tất và trả kết quả.

~~~java
@Override
protected Integer compute() {
    if (isSmall()) {
        return calculateDirectly();
    }

    PartTask left = new PartTask(leftInput());
    PartTask right = new PartTask(rightInput());

    left.fork();
    int rightValue = right.compute();
    int leftValue = left.join();
    return leftValue + rightValue;
}
~~~

Đây là **pseudocode Java-like** trong một subclass `RecursiveTask<Integer>`, với `isSmall`, `calculateDirectly` và constructors do ứng dụng định nghĩa. Không phải chương trình độc lập.

Luồng phụ thuộc:

~~~text
          Parent
          /    \
        Left   Right
         |      |
     fork()   compute() tại worker hiện tại
         |      |
       kết quả kết quả
          \    /
         left.join()
              |
          ghép kết quả
~~~

Lý do thường dùng pattern này:
1. Parent chỉ fork một nhánh, cho phép worker khác nhận nhánh đó khi có capacity.
2. Worker hiện tại tự làm nhánh còn lại, thay vì fork cả hai và chỉ chờ.
3. Chỉ khi kết quả của hai nhánh đã sẵn sàng mới ghép.
4. Child không đợi ngược lại parent, nên không tạo vòng chờ theo cấu trúc cây.
5. Có thể đặt ngưỡng `THRESHOLD` để không tạo task cho phần việc quá nhỏ.

Đừng mặc định `fork()` nghĩa là task lập tức bắt đầu trên một thread khác. Pool có thể không có worker rảnh; cùng một worker cũng có thể tham gia thực thi các tasks qua cơ chế Fork/Join. Tính đúng không được phụ thuộc vào tên worker hay lịch chạy cụ thể.

## 3. Phụ thuộc là quan hệ bắt buộc hoàn tất trước

Trong bài, quy ước **A → B** nghĩa là **A cần kết quả hoặc completion của B trước khi A hoàn tất**.

### Trường hợp an toàn: DAG

~~~text
              Root
             /    \
            A      B
           / \    / \
          C   D  E   F

Root → A, B
A → C, D
B → E, F

C, D, E, F tự tính xong được.
A và B chỉ ghép sau các children.
Root chỉ ghép sau A và B.
Không có đường quay lại một ancestor.
~~~

Đồ thị có thứ tự topo hợp lệ: leaves trước, intermediate nodes sau, root cuối. Các leaves độc lập có thể chạy song song; runtime không cam kết một thứ tự thực thi duy nhất.

### Trường hợp lỗi: vòng hai node

~~~text
Task A: đợi B.join()
Task B: đợi A.join()

Đồ thị:
A ─────► B
▲        │
└────────┘

A chỉ xong sau B; B chỉ xong sau A.
Không có node nào có thể tự hoàn tất.
~~~

Thêm số worker từ 2 lên 16 không phá được ràng buộc. Đó là **dependency cycle**, không đơn thuần là “chạy chưa đủ nhanh”.

### Vòng dài hơn hoặc self-join

~~~text
A → B → C → A   (vòng gián tiếp)
D → D           (self-dependency)
E → F → G       (không có cycle trong phần này)
~~~

Nếu một node đứng ngoài cycle nhưng phụ thuộc vào node trong cycle, nó cũng có thể chờ mãi. Ví dụ `Root → A → B → C → B`: Root không nằm trong cycle nhưng bị kẹt vì không thể nhận kết quả của A.

### Một đoạn mã sai nên nhận diện, không thực thi

~~~java
@Override
protected Integer compute() {
    return this.join(); // SAI: task đợi chính mình
}
~~~

Đây là fragment trong subclass `RecursiveTask<Integer>`, cố ý sai. Chạy main dùng đoạn này có thể treo vô hạn. Bài không cung cấp demo thực thi vòng join sai để tránh khiến người học hoặc CI bị kẹt.

## 4. Tại sao work-stealing không giải quyết được vòng chờ?

Mỗi worker có thể nhận tasks từ queue nội bộ và steal tasks đang chờ từ worker khác. Khi một task Fork/Join gọi `join()`, runtime có cơ chế giúp thực thi những tasks có thể làm tiến triển computation. Nhưng **cơ chế scheduling và sự tồn tại một đường completion hợp lệ là hai vấn đề khác nhau**.

- Nếu child chưa được xử lý nhưng đã có đường thực thi độc lập, worker khác hoặc chính worker gọi join có thể trợ giúp.
- Nếu child đã chạy nhưng lại đợi parent, **nó không có đường để trả kết quả** theo logic hiện tại.
- Nếu child cần một khóa mà parent đang giữ tới khi join xong, scheduler không tự thả khóa đó.
- Nếu child đang đợi một `CountDownLatch` mà không task nào còn đường countDown, thêm worker không tạo tín hiệu.
- Nếu child bị kẹt bởi remote I/O không có timeout, work-stealing có thể làm các công việc khác nhưng không bảo đảm child thoát.

**Kết luận:** `join()` hữu ích cho dependency **acyclic**, không phải primitive phát hiện deadlock.

## 5. Ví dụ chạy được 1: tính tổng mảng theo cây không có vòng

Lưu thành **ForkJoinSumDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinSumDemo {
    static class SumTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 2;

        private final long[] numbers;
        private final int from;
        private final int to;

        SumTask(long[] numbers, int from, int to) {
            this.numbers = numbers;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            if (to - from <= THRESHOLD) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += numbers[i];
                }
                return sum;
            }

            int middle = from + (to - from) / 2;
            SumTask left = new SumTask(numbers, from, middle);
            SumTask right = new SumTask(numbers, middle, to);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        long[] numbers = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            long answer = pool.invoke(
                    new SumTask(numbers, 0, numbers.length));
            System.out.println("sum=" + answer);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ForkJoinSumDemo.java
java ForkJoinSumDemo
~~~

Stdout:

~~~text
sum=36
~~~

Tại sao:
- Node gốc xử lý [0,8); nó phân rã thành [0,4) và [4,8).
- Các leaf tính phần tổng trên những khoảng **không chồng lấn**.
- Mỗi parent chỉ ghép hai giá trị sau khi subtask cần thiết đã hoàn tất.
- Không child nào đợi ancestor; graph là cây hợp lệ.
- Input mảng chỉ được đọc, không bị thread nào sửa đồng thời trong ví dụ.
- Dù workers có thể lấy tasks theo nhiều lịch chạy khác nhau, phép cộng trên dữ liệu này cho kết quả 36.

Ngưỡng 2 chỉ giúp minh họa. Với mảng lớn hoặc thao tác rẻ, ngưỡng quá nhỏ làm overhead tạo task, scheduling và work-stealing lớn hơn lợi ích. Cần benchmark để chọn ngưỡng; không dùng 2 làm công thức tối ưu.

## 6. Ví dụ chạy được 2: ghép dữ liệu độc lập theo DAG

Công việc `BuildReport` cần hai kết quả `ReadPart(3)` và `ReadPart(4)`. Cả hai độc lập; kết quả được ghép thành chuỗi sau khi hoàn tất.

~~~text
            BuildReport
            /         \
        ReadPart 3   ReadPart 4
            \         /
           combine(9,16)
               |
          "total=25"
~~~

Lưu thành **ForkJoinDagDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinDagDemo {
    static final class ReadPart extends RecursiveTask<Integer> {
        private final int input;

        ReadPart(int input) {
            this.input = input;
        }

        @Override
        protected Integer compute() {
            return input * input;
        }
    }

    static final class BuildReport extends RecursiveTask<String> {
        @Override
        protected String compute() {
            ReadPart left = new ReadPart(3);
            ReadPart right = new ReadPart(4);

            left.fork();
            int rightValue = right.compute();
            int leftValue = left.join();

            return "left=" + leftValue
                    + ";right=" + rightValue
                    + ";total=" + (leftValue + rightValue);
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            System.out.println(pool.invoke(new BuildReport()));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac ForkJoinDagDemo.java
java ForkJoinDagDemo
~~~

Stdout:

~~~text
left=9;right=16;total=25
~~~

`ReadPart` không cần parent trước khi trả kết quả. Parent chờ một child qua `join()` và tự tính child kia, nên quan hệ chờ có hướng không tạo chu trình. Dù left hay right hoàn thành trước, giá trị được ghép theo các biến xác định và stdout ổn định.

**Mở rộng thành DAG thực:** nếu A và B đều phụ thuộc vào C, đó là đồ thị hình kim cương. C không nhất thiết cần được tính hai lần. Hãy dùng **một** representation của computation kết quả C, quản lý ownership/schedule rõ ràng, rồi cho A và B chỉ sử dụng kết quả hợp lệ. Không fork nhiều lần cùng một instance `ForkJoinTask` theo cách tùy tiện, đặc biệt khi task đang chạy.

## 7. Phụ thuộc qua shared resource: vòng chờ bị che khuất

Không phải mọi cạnh chờ đều được viết thành `join()`.

Ví dụ:

~~~text
Parent giữ monitor L
   |
   +-- fork Child
   |
   +-- Child cần synchronized(L) trước khi hoàn tất
   |
   +-- Parent gọi Child.join() trong khi vẫn giữ L

Parent chỉ nhả L sau Child.join().
Child chỉ hoàn tất sau khi acquire L.
=> Parent đợi Child, Child đợi resource do Parent giữ.
~~~

Anti-pattern:

~~~java
synchronized (sharedLock) {
    child.fork();
    child.join();
}
~~~

Đây là **fragment minh họa lỗi** trong một method với `sharedLock`, `child` giả định đã định nghĩa. Nó nguy hiểm **nếu child thực sự cần chính monitor đó để có thể hoàn tất**. Nếu child không cần L, đoạn trên không tự động chứng minh deadlock — phải xét dependency của child.

Java intrinsic monitor là reentrant **theo cùng thread**, không cho một thread khác tự vào monitor do parent thread giữ. Fork/Join có thể có cơ chế trợ giúp thực thi task nhưng không được dựa vào đó để che một quan hệ sở hữu resource sai.

### Semaphore cũng có thể tạo vòng

~~~text
A giữ permit cuối cùng của Semaphore S
A fork B rồi join B
B muốn acquire S trước khi hoàn tất
A chỉ release S sau join B
B không lấy được permit, A không lấy được kết quả
~~~

`finally` sẽ release permit nếu code thoát khỏi try, nhưng nếu vòng chờ không thể thoát thì finally **không được thực thi**. Vì vậy phải thiết kế thứ tự acquire/release và các edges của graph, không chỉ thêm cleanup.

### Hướng sửa

1. Lấy snapshot của shared state dưới lock nếu cần.
2. **Nhả lock** trước khi fork/join những subtasks có thể cần lock đó.
3. Tính trên immutable input nếu có thể.
4. Ghép kết quả sau joins.
5. Khi cần commit vào shared state, acquire lock lại và **kiểm tra version/invariant**, vì state có thể đổi trong khi lock được nhả.

Đoạn ý tưởng:

~~~java
Input snapshot;
synchronized (sharedLock) {
    snapshot = copyState();
}

Result answer = pool.invoke(new ComputeTask(snapshot));

synchronized (sharedLock) {
    commitOnlyIfStillValid(answer);
}
~~~

Đây là **pseudocode tích hợp**; `Input`, `Result`, `copyState`, `ComputeTask` và `commitOnlyIfStillValid` là các thành phần ứng dụng phải tự định nghĩa. Không coi việc nhả lock giữa các bước là một transaction nguyên tử; phần commit phải xác nhận dữ liệu đầu vào chưa lỗi thời.

## 8. Deadlock, starvation và slow task khác nhau thế nào?

| Hiện tượng | Ví dụ | Điều cần sửa |
|---|---|---|
| **Dependency cycle** | A join B, B join A | Loại cạnh vòng, tổ chức lại graph |
| **Resource wait cycle** | Parent giữ lock, child cần lock rồi parent join | Thả/đổi thứ tự sở hữu tài nguyên |
| **Thread starvation** | Worker block chờ task con chưa có worker để chạy | Xem lại dependency, executor capacity, blocking strategy |
| **Missing signal** | Child chờ CountDownLatch không ai countDown | Sửa producer của tín hiệu và finally |
| **Slow I/O** | Leaf đợi remote call không timeout | Đặt I/O timeout/cancel theo API |
| **High overhead** | Hàng triệu subtasks nhỏ | Threshold và batching |
| **Valid DAG with few workers** | Leaf độc lập nhưng chỉ có 1 worker | Có thể chậm, không tự đồng nghĩa deadlock |

Một DAG hợp lệ chỉ nói rằng không có **chu trình phụ thuộc**, chưa bảo đảm mọi leaf sẽ hoàn tất: leaf có thể lỗi, chờ external I/O vô hạn hoặc bị resource exhaustion. Do đó thiết kế liveness phải bao gồm **cả graph lẫn tài nguyên**.

## 9. Đừng block tùy tiện trong compute()

`ForkJoinPool` tối ưu cho tính toán chia để trị, nhưng một `compute()` có thể vô tình gọi:
- `Future.get()` trên future do executor khác tạo;
- `CountDownLatch.await()` có bên phát tín hiệu chưa schedule;
- network I/O không có timeout;
- `Thread.sleep()` rất lâu;
- acquire lock/permit trong khi owner đang chờ task hiện tại.

Nếu worker bị block trong thao tác **không phải join được ForkJoinPool quản lý**, pool không nhất thiết bù workers đủ để giữ khả năng tiến triển. JDK có `ForkJoinPool.ManagedBlocker` để báo một số tình huống blocking và cho phép pool **có thể** duy trì parallelism bằng spare threads.

### ManagedBlocker không phải bộ giải deadlock

`ForkJoinPool.managedBlock(blocker)` gọi `isReleasable()` và `block()` của blocker theo contract. Khi chạy từ một ForkJoinPool, runtime có thể thêm/kích hoạt worker khác nếu phù hợp giới hạn và khả năng tài nguyên.

Nó **không**:
- phá quan hệ A→B→A;
- thả lock do parent giữ;
- gọi countDown cho một latch bị quên;
- biến I/O thành interruptible nếu API nền không hỗ trợ;
- bảo đảm thêm worker dưới mọi chính sách hoặc khi tài nguyên hệ thống cạn;
- tự biến một shared mutable object thành thread-safe.

Nếu có cycle, hãy **sửa graph**. Nếu có unmanaged blocking nhưng graph acyclic, ManagedBlocker có thể là một công cụ, cần hiểu rõ trách nhiệm `isReleasable`, `block`, cancellation và kiểm thử workload.

### ForkJoinTask.join và Future.get không giống nhau

`ForkJoinTask.join()` thường trả kết quả khi completed normally, hoặc ném unchecked exception/`Error` khi task hoàn tất bất thường. `ForkJoinTask.get()` tuân hợp đồng `Future` với checked exceptions như `InterruptedException`, `ExecutionException` và `TimeoutException` ở timed overload.

- `join()` **không có tham số timeout**.
- `join()` **không khai báo InterruptedException**.
- `get(timeout, unit)` chỉ giới hạn **thời gian caller chờ**, không phá một cycle.
- `Thread.join()` là API đợi **Thread** kết thúc, khác `ForkJoinTask.join()`.
- `CompletableFuture.join()` có exception semantics riêng, đừng đánh đồng.

## 10. Ví dụ chạy được 3: kiểm tra dependency cycle trước khi tạo tasks

Thay vì chạy ví dụ join có khả năng treo, ta kiểm tra graph bằng **DFS ba màu**:
- 0: chưa thăm.
- 1: đang đi trên recursion stack (VISITING).
- 2: đã duyệt hoàn tất (DONE).

Nếu từ một node ta theo cạnh tới node đang VISITING, có một **back-edge**, tức cycle.

Lưu tệp **TaskDependencyCycleDemo.java**:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class TaskDependencyCycleDemo {
    static boolean hasCycle(Map<String, List<String>> graph) {
        Map<String, Integer> state = new HashMap<>();
        for (String node : graph.keySet()) {
            if (visit(node, graph, state)) {
                return true;
            }
        }
        return false;
    }

    private static boolean visit(
            String node,
            Map<String, List<String>> graph,
            Map<String, Integer> state) {

        int mark = state.getOrDefault(node, 0);
        if (mark == 1) return true;
        if (mark == 2) return false;

        state.put(node, 1);
        for (String dependency : graph.get(node)) {
            if (!graph.containsKey(dependency)) {
                throw new IllegalArgumentException(
                        "Unknown dependency: " + dependency);
            }
            if (visit(dependency, graph, state)) {
                return true;
            }
        }
        state.put(node, 2);
        return false;
    }

    public static void main(String[] args) {
        Map<String, List<String>> valid = Map.of(
                "root", List.of("left", "right"),
                "left", List.of("leaf"),
                "right", List.of("leaf"),
                "leaf", List.of()
        );

        Map<String, List<String>> invalid = Map.of(
                "A", List.of("B"),
                "B", List.of("C"),
                "C", List.of("A")
        );

        System.out.println("validHasCycle=" + hasCycle(valid));
        System.out.println("invalidHasCycle=" + hasCycle(invalid));
    }
}
~~~

Lệnh:

~~~bash
javac TaskDependencyCycleDemo.java
java TaskDependencyCycleDemo
~~~

Stdout:

~~~text
validHasCycle=false
invalidHasCycle=true
~~~

Tại graph đầu, `leaf` không có dependency, các node khác chỉ có cạnh hướng xuống leaf, không có vòng. Graph thứ hai có A→B→C→A, nên DFS quay về A đang VISITING và trả true.

**Giới hạn quan trọng:**
- Đồ thị ở đây **chỉ đọc**, không bị sửa đồng thời; do đó `HashMap` thông thường là đủ.
- Graph có thể thay đổi động trong ứng dụng thật; phải đồng bộ việc bổ sung cạnh và kiểm tra acyclic để không có race.
- Recursion DFS có thể gặp `StackOverflowError` khi graph cực sâu; khi đó dùng DFS iterative hoặc thuật toán Kahn.
- Phát hiện không có cycle **chưa đủ** bảo đảm mọi node hoàn tất; vẫn phải kiểm tra ngoại lệ, missing task, blocking và lifecycle.
- Chương trình không tạo deadlock vì nó **chỉ kiểm tra graph**, không chạy tác vụ vòng chờ.

## 11. DAG chia sẻ prerequisite: cẩn thận với completion ownership

DAG không nhất thiết là một cây. Xét:

~~~text
       Root
       /  \
      A    B
       \  /
        C
~~~

A và B đều phụ thuộc C. Nếu C tốn nhiều CPU, tạo **hai instance** tính cùng một C có thể gây lãng phí. Nếu C có side effects, hai lần thực thi có thể nguy hiểm.

Các nguyên tắc:
1. Quyết định **ai sở hữu** computation của C và khi nào C được schedule.
2. Hai dependents chỉ sử dụng kết quả **sau khi C hoàn tất**.
3. Đừng fork lại cùng instance `ForkJoinTask` đang chạy theo kiểu coi task là một function có thể gọi tùy ý.
4. Nếu C bị lỗi, định nghĩa A/B có fail hay fallback, tránh chúng chờ vô hạn.
5. Nếu việc tạo dependencies diễn ra động, bảo đảm không thêm cạnh B→A đồng thời với A→B làm phát sinh cycle.

Với graph chia sẻ nhiều prerequisite, có thể tổ chức các **giai đoạn theo thứ tự topo**, dùng `CompletableFuture` để diễn đạt dependencies, hoặc áp dụng `CountedCompleter` nếu completion callbacks phù hợp. Không cần ép tất cả graph vào cây `RecursiveTask`.

## 12. Topological order và readiness

Với quy ước A→B là A phụ thuộc B:

~~~text
Root → A
Root → B
A → C
B → C

Thứ tự hợp lệ: C, A, B, Root
hoặc:          C, B, A, Root

Sau C, A và B độc lập, có thể chạy song song.
Root chỉ chạy/ghép khi A và B hoàn tất.
~~~

Một scheduler cho DAG có thể:
- Liệt kê dependency count của mỗi node.
- Chỉ đưa vào hàng đợi những nodes đã đủ prerequisites.
- Khi một node xong, giảm unresolved dependency count ở dependents.
- Đưa các dependents đã sẵn sàng vào queue.
- Trả lỗi rõ ràng nếu không có nodes tiến triển trong khi vẫn còn unresolved graph vì cycle/missing prerequisite.
- Định nghĩa fail-fast hay partial result khi một prerequisite thất bại.

Ý tưởng quan trọng là **đừng chiếm worker chỉ để chờ một task chưa sẵn sàng** nếu có thể quản lý readiness trước khi schedule. Điều này giảm thread-starvation khi graph phức tạp.

## 13. Exception, timeout và cancellation

`ForkJoinTask.join()` có thể ném unchecked exception khi task hoàn tất bất thường. `ForkJoinTask.isDone()` có thể true vì completed normally, exceptionally hoặc cancelled — không đồng nghĩa computation trả kết quả thành công.

Với `ForkJoinTask.get(timeout, unit)`, caller có thể giới hạn pha chờ, nhưng timeout:
- không sửa một cycle;
- không hủy task tự động chỉ vì `get` đã timeout;
- không bảo đảm một worker đang làm I/O đã dừng;
- không làm side effects trước đó rollback.

Một chi tiết dễ nhầm theo Javadoc `ForkJoinTask.cancel(boolean)` Java 17: **tham số `mayInterruptIfRunning` không có tác dụng ở implementation mặc định**, vì ForkJoinTask không dùng interrupts để kiểm soát cancellation theo cách một số `FutureTask` dùng. Vì vậy `task.cancel(true)` không phải cam kết worker đang block lập tức bị interrupt.

Nếu nhiệm vụ cần hủy hợp tác, phải thiết kế tín hiệu/các điểm kiểm tra và cleanup phù hợp. `shutdownNow()` cũng không phải một phép cứu an toàn cho vòng phụ thuộc sai. Không chạy một graph cyclic thật để “đợi xem JVM tự giải quyết không”.

## 14. Quan sát và debug các tác vụ kẹt

Các metrics hữu ích:

| API/công cụ | Ý nghĩa | Giới hạn |
|---|---|---|
| `pool.getParallelism()` | Parallelism mục tiêu | Không phải số tasks đang chạy |
| `pool.getPoolSize()` | Workers hiện có | Có thể thay đổi |
| `pool.getActiveThreadCount()` | Ước lượng workers đang hoạt động | Không phải snapshot transaction |
| `pool.getRunningThreadCount()` | Ước lượng workers đang chạy | Có thể chưa phản ánh mọi block |
| `pool.getQueuedTaskCount()` | Ước lượng tasks trong worker queues | Không mô tả đầy đủ graph |
| `pool.getQueuedSubmissionCount()` | Ước lượng external submissions | Có thể đổi liên tục |
| `pool.getStealCount()` | Thông tin work stealing | Không chứng minh progress/correctness |
| Thread dump / JFR | Call stacks và trạng thái JVM | Chụp tại một thời điểm |
| Logging task IDs | Task đang đợi task nào và giữ resource nào | Cần instrumentation có chủ đích |

Khi thread dumps có nhiều workers ở `join` hay một blocking call, hãy dựng **wait-for graph**:
1. Task nào đang đợi task nào?
2. Task được đợi đã từng được fork/submit chưa?
3. Task đó đang chạy, lỗi, cancelled hay còn chờ trong queue?
4. Có node nào đợi ancestor hay đợi chính nó?
5. Parent có đang giữ lock/permit mà child cần?
6. Có latch/barrier nào không còn bên phát tín hiệu?
7. Nếu graph acyclic, task leaf bị kẹt ở đâu (I/O, lock, resource exhaustion)?
8. Có dependency đòi một task trong cùng pool bị giữ hết workers bởi những parent đang chờ?

Đừng suy `queueSize==0` là công việc đã hoàn tất. Một pool có queues trống vẫn có thể có workers đang chờ nhau mà không tạo tiến triển.

## 15. Lỗi phổ biến khi code review

**Lỗi 1: Self-join.** Task đợi chính task đang compute.

**Lỗi 2: A→B→A.** Hai tasks đợi nhau; thêm workers không tạo completion order.

**Lỗi 3: A→B→C→A.** Vòng gián tiếp khó phát hiện khi dependencies nằm ở nhiều modules.

**Lỗi 4: Parent giữ monitor/permit khi join child cần cùng tài nguyên.** Resource-wait cycle bị ẩn.

**Lỗi 5: Fork task nhưng quên join kết quả cần thiết.** Parent có thể return quá sớm hoặc không xử lý lỗi child.

**Lỗi 6: Join task chưa bao giờ có đường schedule/complete.** Không có cycle rõ ràng nhưng vẫn treo.

**Lỗi 7: Dùng một ForkJoinTask instance làm task reusable, fork tùy tiện nhiều lần.** Không tôn trọng vòng đời completion.

**Lỗi 8: Block I/O/Future.get không có timeout trong compute.** Worker capacity có thể bị starve.

**Lỗi 9: Tưởng ManagedBlocker luôn tạo worker mới.** Nó chỉ hỗ trợ quản lý một số blocking, có ràng buộc.

**Lỗi 10: Tưởng ManagedBlocker giải quyết graph cyclic.** Graph sai phải được sửa.

**Lỗi 11: Task quá nhỏ.** Scheduling overhead vượt lợi ích parallelism.

**Lỗi 12: Dùng Thread.sleep để “đợi child”.** Sleep không đồng bộ completion/visibility của task.

**Lỗi 13: Nhiều tasks sửa cùng một mutable array không chia vùng và thiếu đồng bộ.** Fork/Join không tự làm data race biến mất.

**Lỗi 14: Nghĩ cancel(true) mặc định interrupt ForkJoinTask worker.** Javadoc ForkJoinTask nêu điều ngược lại.

**Lỗi 15: Bỏ qua exceptional completion.** Parent phải hiểu lỗi trong child thay vì coi result hợp lệ.

**Lỗi 16: Xem getQueuedTaskCount bằng 0 là mọi task xong.** Có thể workers đang blocked.

**Lỗi 17: Cập nhật dependency graph động không đồng bộ.** Hai threads cùng thêm edges có thể tạo cycle.

**Lỗi 18: Dùng pool chung cho blocking tasks dài không kiểm soát.** Ảnh hưởng các tác vụ khác trong common pool.

**Lỗi 19: Trộn dependency completion với thứ tự database transaction.** Fork/Join không rollback side effects.

**Lỗi 20: Chạy test deadlock thật mà không có guard.** Có thể làm CI hay JVM treo; hãy kiểm tra graph tĩnh hoặc thiết kế test bounded.

## 16. Checklist thiết kế

- [ ] Hướng mũi tên dependency được định nghĩa nhất quán?
- [ ] Mọi dependencies có **thứ tự hoàn tất hợp lệ** (DAG)?
- [ ] Task không join chính mình, ancestor hoặc task gián tiếp chờ mình?
- [ ] Có kiểm tra cycle khi xây DAG hoặc thêm cạnh động?
- [ ] Mỗi task được schedule đúng ownership, không fork một instance tùy tiện?
- [ ] Parent có join những children cần kết quả?
- [ ] Không giữ lock/permit mà child cần trong lúc join?
- [ ] Các leaf có thể hoàn tất mà không đợi tín hiệu không thể có?
- [ ] Có I/O/blocking API không? Deadline, cancellation và ManagedBlocker có phù hợp?
- [ ] Có giới hạn tasks nhỏ bằng threshold hợp lý?
- [ ] Có cơ chế propagate exception và cleanup khi task lỗi?
- [ ] Có xử lý cancellation không giả định cancel(true) luôn interrupt worker?
- [ ] Shared mutable state có ownership/synchronization?
- [ ] Có task IDs, dependency IDs và metrics để dựng wait-for graph?
- [ ] Có người sở hữu lifecycle của pool và shutdown?
- [ ] Đã so sánh benchmark với thuật toán tuần tự cho workload thật?

## 17. Câu hỏi luyện tập kèm đáp án

**Câu 1.** A gọi `B.join()`, B gọi `A.join()`. Dùng `ForkJoinPool(32)` có sửa được không?

**Đáp án:** Không. Dependency cycle không có thứ tự hoàn tất hợp lệ, bất kể bao nhiêu workers.

**Câu 2.** Vì sao `left.fork(); right.compute(); left.join()` thường được khuyến khích?

**Đáp án:** Worker hiện tại thực hiện một nhánh, nhánh còn lại có thể được worker khác thực hiện; sau đó chỉ đợi kết quả cần thiết. Điều này giảm việc tạo/schedule tasks không cần thiết và giữ graph rõ ràng.

**Câu 3.** Parent giữ lock L rồi join child cần L. Lỗi ở đâu?

**Đáp án:** Parent chỉ release L sau join, child chỉ xong sau khi acquire L: resource-wait cycle. Cần đổi thứ tự sở hữu lock hoặc tách pha xử lý.

**Câu 4.** `ForkJoinTask.join()` có timeout giống `get(1, SECONDS)` không?

**Đáp án:** Không. Join không có overload timeout; get(timeout) chỉ giới hạn pha chờ của caller.

**Câu 5.** `ForkJoinTask.cancel(true)` luôn interrupt worker không?

**Đáp án:** Không. Default implementation không dùng `mayInterruptIfRunning` để điều khiển interruption.

**Câu 6.** ManagedBlocker có phá A→B→A không?

**Đáp án:** Không. Nó có thể giúp bù workers cho blocking, không thay đổi dependency graph.

**Câu 7.** Graph Root→A, Root→B, A→C, B→C là DAG hay cycle?

**Đáp án:** DAG. Node C là shared prerequisite, không có đường quay ngược tạo vòng.

**Câu 8.** Mảng bị thread khác sửa trong lúc SumTask cộng có chắc đúng không?

**Đáp án:** Không. Fork/Join không tự ngăn data race trên dữ liệu đầu vào mutable; cần ownership/snapshot hoặc synchronization.

**Câu 9.** Đồ thị không có cycle có đảm bảo không bao giờ treo không?

**Đáp án:** Không. Một leaf có thể chờ I/O vô hạn, tài nguyên không được release hoặc task chưa được schedule.

**Câu 10.** Tại sao kiểm tra cycle trước khi submit tốt hơn tạo graph sai rồi chờ join?

**Đáp án:** Nó báo lỗi sớm, tránh đưa JVM vào quan hệ chờ bất khả thi và giúp debug rõ ràng.

## 18. Tài liệu chính thức

- **ForkJoinTask (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html
- **ForkJoinPool (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- **RecursiveTask (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html
- **RecursiveAction (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html
- **CountedCompleter (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html
- **CompletableFuture (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **Future (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html

**Ghi nhớ:** Fork/Join phát huy hiệu quả khi có các nhánh tính toán độc lập và quan hệ hoàn tất **acyclic**. Work-stealing trợ giúp scheduling, **không sửa được vòng A→B→A hoặc vòng chờ qua lock/permit**. Thiết kế dependency graph đúng, tránh giữ tài nguyên khi join, giới hạn blocking và kiểm tra cycle trước khi chạy là nền tảng để bảo đảm liveness.
