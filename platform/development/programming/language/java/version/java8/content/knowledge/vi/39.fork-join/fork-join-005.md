# Pending count và truyền tín hiệu hoàn tất trong Fork/Join với CountedCompleter (Java 8)

## 1. Vấn đề: tác vụ đã chạy hết compute() nhưng kết quả tổng vẫn chưa được phép hoàn tất

Giả sử một tác vụ Fork/Join chia mảng thành nhiều phần, mỗi phần được xử lý song song. Tác vụ cha có thể **kết thúc phần công việc của chính nó** trước các tác vụ con. Nếu đánh dấu task cha hoàn tất ngay lúc `compute()` trở về, người gọi `invoke()` hoặc `join()` trên task gốc có thể nhận thông báo sớm, khi kết quả của các nhánh khác vẫn chưa được ghi xong.

Java cung cấp `java.util.concurrent.CountedCompleter<T>`, một lớp con của `ForkJoinTask<T>`, dùng **pending count** và các tín hiệu **completion** để điều phối các công việc có quan hệ *completer*. Nó đặc biệt hữu ích cho các cấu trúc chia nhỏ/duyệt tập dữ liệu mà không nhất thiết phải `join()` từng nhánh con như `RecursiveTask`.

Một quy tắc dễ bị hiểu sai:

> **Pending count bằng 0 không tự động có nghĩa task đã completed.** Khi `tryComplete()` được gọi lúc count **khác 0**, nó chỉ giảm count; khi `tryComplete()` được gọi lúc count **đã bằng 0**, nó mới chạy `onCompletion(...)` và tiếp tục truyền tín hiệu lên completer.

Chẳng hạn một root được đặt `pendingCount = 2` cần **ba lời gọi `tryComplete()` tới root** trong mô hình đơn giản, không có callback nào làm thay đổi count:

```text
Lúc đầu: pending = 2, root chưa complete
Tín hiệu 1: tryComplete() thấy 2 -> giảm còn 1; chưa complete
Tín hiệu 2: tryComplete() thấy 1 -> giảm còn 0; chưa complete
Tín hiệu 3: tryComplete() thấy 0 -> onCompletion(root/caller)
                            -> root hoàn thành
```

Đó là **cơ chế đếm tín hiệu**, không phải bộ đếm danh sách task do ForkJoinPool tự duy trì. Người viết `CountedCompleter` có trách nhiệm đặt số pending và phát **đúng số tín hiệu**.

Bài này tập trung vào đề tài **“Pending count và truyền tín hiệu hoàn tất”** trong nhóm **Fork/Join** của module **Java 8**. Ta sẽ đi từ `CountedCompleter`, `getPendingCount`/`setPendingCount`/`addToPendingCount`, mô hình `tryComplete` và `propagateCompletion`, callback `onCompletion`, `complete`/`quietlyCompleteRoot`, phép duyệt `firstComplete`/`nextComplete`, cơ chế lỗi `onExceptionalCompletion`, đến ví dụ fork thực tế và kiểm thử chống treo. Các API đều tồn tại trong Java 8 và vẫn được hỗ trợ trên Java hiện đại. Sáu chương trình Java độc lập đã được biên dịch ở mức Java 8 và chạy xác minh stdout.

## 2. CountedCompleter đứng ở đâu trong Fork/Join?

Trong hệ sinh thái `java.util.concurrent`:

- `ForkJoinPool` quản lý các worker thực thi task, có khả năng *work stealing*.
- `ForkJoinTask<T>` là đơn vị công việc hỗ trợ `fork()`, `join()`, `invoke()` và trạng thái completed.
- `RecursiveTask<T>` thường tính giá trị rồi `join` các task con để tổng hợp.
- `RecursiveAction` thực hiện công việc không trả giá trị, thường phối hợp `invokeAll`.
- `CountedCompleter<T>` dùng **completion dependencies**, số tín hiệu pending và một liên kết tới **completer cha** để cho phép completion lan theo cấu trúc mà không buộc từng task con được join trực tiếp.

Đây không phải sự thay thế mặc định cho mọi bài toán. `CountedCompleter` linh hoạt nhưng ít trực giác hơn `RecursiveTask`, và các bug lệch pending count có thể khiến root **hoàn tất quá sớm** hoặc **không bao giờ hoàn tất**. Chỉ chọn khi thật sự cần mô hình phối hợp/ghép tín hiệu mà nó cung cấp.

### Các thành phần của một CountedCompleter

Một lớp kế thừa thường có:

```java
// Khung minh họa, chưa phải chương trình độc lập.
final class Work extends CountedCompleter<Void> {
    Work(CountedCompleter<?> parent) {
        super(parent);
    }

    @Override public void compute() {
        // Đăng ký các nhánh chờ, fork và xử lý phần việc.
        tryComplete(); // hoặc propagateCompletion(), tùy hợp đồng.
    }

    @Override public void onCompletion(CountedCompleter<?> caller) {
        // Tùy chọn: tổng hợp kết quả khi đủ tín hiệu.
    }
}
```

Constructor `super(parent)` tạo liên kết **completer**, không phải tự đăng ký child vào parent. Nếu parent cần chờ tín hiệu từ task mới tạo, code cần **tự cập nhật pending count trước khi công bố/fork task**.

`CountedCompleter<Void>` thích hợp khi kết quả nằm trong mảng, accumulator hoặc state khác thay vì một giá trị trả về trực tiếp. Mặc định `getRawResult()` cho loại task này trả `null`. Nếu muốn `CountedCompleter<T>` thực sự trả một giá trị T từ `invoke()/join()`, cần thiết kế trạng thái kết quả và thường override `getRawResult()` phù hợp.

## 3. Ý nghĩa chính xác của pending count

Pending count là **một số nguyên nội bộ gắn với mỗi CountedCompleter**, ban đầu bằng 0 nếu không khởi tạo khác. Nó được thay bằng các phương thức như `setPendingCount(int)` hoặc tăng bằng `addToPendingCount(int)`.

Điều cần nhớ:

1. **Count không biết task nào đang chờ.** Nó không lưu identity của các child tasks.
2. **Count không tự tăng khi gọi fork().** Code phải đăng ký tín hiệu còn chờ.
3. **Count không tự giảm khi một child return từ compute().** Child phải phát tín hiệu qua `tryComplete()`/`propagateCompletion()` hoặc một đường completion tương ứng.
4. **Count không phải con số worker đang chạy**, cũng không phải chỉ số tiến độ được bảo đảm.
5. **Count=0 chưa đủ để đánh dấu done**: còn cần lời gọi completion phù hợp.
6. **Giảm count bằng API điều chỉnh count không thay thế việc phát tín hiệu**: `setPendingCount(0)` đơn lẻ không hoàn tất task.
7. Số count cần khớp với **mô hình tín hiệu thực tế**, không đơn thuần là chiều dài danh sách subtasks.

### Ngữ nghĩa của tryComplete: quan sát count trước khi hành động

Theo hợp đồng API:

```text
tryComplete() trên task X
    |
    +-- pending(X) != 0
    |      -> giảm pending(X) đi 1
    |      -> dừng tại X
    |
    +-- pending(X) == 0
           -> gọi X.onCompletion(caller)
           -> nếu có completer P: tiếp tục thử hoàn tất P
           -> nếu không có completer: mark root hoàn tất
```

Trong một lời gọi thực tế, `tryComplete()` có thể đi dọc qua **nhiều tầng completer** khi các tầng gặp pending count 0. Nếu gặp một pending count dương ở một ancestor, nó chỉ giảm count đó rồi dừng. Mọi thay đổi count được thực hiện bằng cơ chế đồng bộ/atomic của lớp, nhưng **không tự phát sinh thêm tín hiệu**.

### Đừng đồng nhất pending count với số child

Có nhiều pattern hợp lệ:

- Parent fork N child và **tự phát tín hiệu hoàn tất công việc của parent**: có thể khởi tạo pending N, vì còn N child signals cộng một self-signal, tổng N+1 lời gọi tới parent.
- Parent **không tự phát self-signal** nhưng nhận đúng N child signals: có thể khởi tạo pending N−1 để tín hiệu cuối khi count 0 kích hoạt completion.
- Một task xử lý nhiều nhánh bằng vòng lặp, mỗi lần fork một nhánh và tự xử lý phần còn lại: có thể `addToPendingCount(1)` cho mỗi lần fork, rồi một lần `tryComplete` cho phần việc trực tiếp của nó. Đây là pattern phổ biến trong JavaDoc.

Không nên “luôn đặt pending = số child”, “luôn đặt N−1” hay “luôn gọi tryComplete N lần” mà không xác định chính xác luồng tín hiệu của thuật toán.

## 4. Completion liên kết cha/con hoạt động ra sao?

Khi tạo child bằng constructor nhận completer:

```java
Child child = new Child(parent);
```

child được liên kết tới `parent` qua `getCompleter()`. Lúc child gọi `tryComplete()` với pending count 0, nó có thể gọi `onCompletion` của chính child, sau đó tiếp tục xử lý tín hiệu ở parent.

```text
Root (pending=2)
 |
 +--- Leaf A (pending=0) -> LeafA.tryComplete()
 |                              |
 |                              v
 |                           Root: 2 -> 1
 |
 +--- Leaf B (pending=0) -> LeafB.tryComplete()
 |                              |
 |                              v
 |                           Root: 1 -> 0
 |
 +--- Root tự kết thúc phần trực tiếp -> Root.tryComplete()
                                |
                                v
                     Root đã ở 0 -> onCompletion()
                                        -> done
```

**Sơ đồ chỉ minh họa một thứ tự tín hiệu.** Trong chạy song song, root self-signal và hai child signals có thể tới theo các thứ tự khác nhau. Tuy nhiên, nếu tất cả được đăng ký đúng và từng nhánh phát tín hiệu đúng một lần, kết quả cuối vẫn là một lần root hoàn tất sau đủ nghĩa vụ.

### Compute return không tự làm CountedCompleter done

Với `CountedCompleter`, không nên cho rằng return khỏi `compute()` đồng nghĩa root đã được mark done. Lớp này dùng giao thức completion riêng; nhiều triển khai cần gọi `tryComplete()` cuối compute. Nếu quên, `ForkJoinPool.invoke(root)` có thể chờ mãi dù mọi phương thức compute đã return.

Trong JavaDoc, phương thức `compute()` của lớp con **thường gọi `tryComplete()` trước khi trả về**. Không phải vì compiler yêu cầu, mà vì đó là một phần giao thức liveness của thiết kế.

## 5. Chương trình 1 — hai child, một self-signal và đúng một root completion

Tệp **`PendingLifecycleDemo.java`** dùng `CountedCompleter<Void>` trong một `ForkJoinPool` riêng. Root đặt pending=2, fork hai leaf rồi phát self-signal. Mỗi leaf ghi nhận đã làm xong và `tryComplete()`.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class PendingLifecycleDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class Root extends CountedCompleter<Void> {
        final AtomicInteger leavesDone = new AtomicInteger();
        final AtomicInteger completionCalls = new AtomicInteger();

        @Override public void compute() {
            setPendingCount(2);
            new Leaf(this).fork();
            new Leaf(this).fork();
            tryComplete();
        }

        @Override public void onCompletion(CountedCompleter<?> caller) {
            completionCalls.incrementAndGet();
        }
    }

    static final class Leaf extends CountedCompleter<Void> {
        final Root root;

        Leaf(Root root) {
            super(root);
            this.root = root;
        }

        @Override public void compute() {
            root.leavesDone.incrementAndGet();
            tryComplete();
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        Root root = new Root();

        try {
            pool.invoke(root);

            check(root.isDone(), "root completion");
            check(root.leavesDone.get() == 2, "two leaves");
            check(root.completionCalls.get() == 1,
                  "root onCompletion exactly once");
            check(root.getPendingCount() == 0,
                  "remaining pending count");

            System.out.println("leavesDone=" + root.leavesDone.get());
            System.out.println("rootOnCompletionCalls="
                + root.completionCalls.get());
            System.out.println("rootPending=" + root.getPendingCount());
            System.out.println("rootDone=" + root.isDone());
            System.out.println("PASS");
        } finally {
            pool.shutdown();
        }
    }
}
```

Chạy trên JDK 8:

```bash
javac -encoding UTF-8 PendingLifecycleDemo.java
java PendingLifecycleDemo
```

Hoặc dùng JDK mới, bảo đảm chỉ API Java 8:

```bash
javac --release 8 -encoding UTF-8 PendingLifecycleDemo.java
java PendingLifecycleDemo
```

**Stdout đã chạy và kiểm chứng:**

```text
leavesDone=2
rootOnCompletionCalls=1
rootPending=0
rootDone=true
PASS
```

**Vì sao kết quả không phụ thuộc thứ tự scheduling?**

- Root tăng pending **trước khi fork** hai child.
- Mỗi child chỉ phát một completion signal sau khi xử lý xong.
- Root phát một self-signal sau khi đã fork.
- Tổng có **ba tín hiệu tới root** cho pending ban đầu bằng 2.
- Một tín hiệu giảm 2→1, tín hiệu khác giảm 1→0, tín hiệu cuối thấy 0 và kích hoạt onCompletion. Thứ tự ba tín hiệu có thể khác nhau, nhưng số lượng phải đúng.
- `onCompletion` của root được gọi đúng một lần, và chỉ khi nghĩa vụ đã được xử lý theo giao thức này.
- `AtomicInteger` đảm bảo việc tăng số leaf hoàn thành an toàn trong môi trường song song.

**Không dựa vào caller==this trong callback này.** Nếu root self-signal đến cuối, `caller` có thể là root; nếu leaf-signal đến cuối, `caller` có thể là child. Thứ tự thực thi song song không cố định, nên không in/khẳng định identity của caller ở ví dụ này.

## 6. Pattern quan trọng: addToPendingCount(1) **trước** fork()

Một pattern chia việc được JavaDoc dùng là **fork một nửa, tiếp tục xử lý nửa còn lại**:

```java
// Minh họa trong compute() của một CountedCompleter.
while (hi - lo > THRESHOLD) {
    int mid = (lo + hi) >>> 1;

    addToPendingCount(1);  // ĐĂNG KÝ trước
    new Child(this, array, mid, hi).fork();

    hi = mid;              // chính task hiện tại làm nửa trái
}
processDirectly(lo, hi);
tryComplete();             // phát tín hiệu của phần việc trực tiếp
```

**Vì sao cần tăng pending trước fork?** Một child có thể được worker khác thực thi rất nhanh. Nếu parent fork trước rồi mới tăng count, child có thể đã gọi `tryComplete()`, làm parent xử lý tín hiệu trên count cũ. Root có thể bị mark complete quá sớm, trong khi công việc mới thậm chí chưa đăng ký.

**Vì sao mỗi lần fork chỉ cộng 1?** Mỗi nhánh mới là một nghĩa vụ bổ sung. Parent vẫn tự xử lý nửa trái bằng chính task của nó, rồi phát self-signal. Nếu parent fork k nhánh theo pattern này, pending được tăng k lần và có tổng k child signals + 1 self-signal cần tới parent.

**Không gọi `join()` cho từng child** nếu thuật toán đang dựa vào propagation từ `CountedCompleter`. Completion của root được điều khiển bởi pending count và các lời gọi tryComplete; việc join child không phải bước bắt buộc, thậm chí có thể làm giảm song song hoặc gây chờ sai khi child không tự mark completed.

### Tại sao đơn vị "một nhánh" không luôn bằng "một thread"?

Nhiều child task có thể chạy trên cùng một worker; một worker cũng có thể xử lý nhiều task. Pending count là **các completion obligations logic**, không phải số worker đang hoạt động. `ForkJoinPool.getParallelism()` và số tác vụ pending là hai khái niệm khác nhau.

## 7. Chương trình 2 — tính tổng 1..16 bằng cách fork nhánh phải, xử lý nhánh trái

Tệp **`ForkedRangeSumDemo.java`** tách khoảng số thành bốn đoạn kích thước 4, xử lý song song và dùng `tryComplete()` để hoàn tất cây. Kết quả tổng được lưu trong `AtomicInteger`, vì các leaf chạy đồng thời.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class ForkedRangeSumDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class SumRange extends CountedCompleter<Void> {
        final AtomicInteger total;
        final AtomicInteger leafChunks;
        final AtomicInteger rootCompletions;
        int lo, hi;

        SumRange(CountedCompleter<?> parent, AtomicInteger total,
                 AtomicInteger leafChunks, AtomicInteger rootCompletions,
                 int lo, int hi) {
            super(parent);
            this.total = total;
            this.leafChunks = leafChunks;
            this.rootCompletions = rootCompletions;
            this.lo = lo;
            this.hi = hi;
        }

        @Override public void compute() {
            while (hi - lo > 4) {
                int mid = (lo + hi) >>> 1;
                addToPendingCount(1);

                new SumRange(this, total, leafChunks, rootCompletions,
                             mid, hi).fork();
                hi = mid;
            }

            for (int i = lo; i < hi; i++) {
                total.addAndGet(i);
            }
            leafChunks.incrementAndGet();
            tryComplete();
        }

        @Override public void onCompletion(CountedCompleter<?> caller) {
            if (getCompleter() == null)
                rootCompletions.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        AtomicInteger total = new AtomicInteger();
        AtomicInteger chunks = new AtomicInteger();
        AtomicInteger rootCompletions = new AtomicInteger();

        SumRange root = new SumRange(
            null, total, chunks, rootCompletions, 1, 17);
        ForkJoinPool pool = new ForkJoinPool(3);

        try {
            pool.invoke(root);
            check(total.get() == 136, "sum 1 through 16");
            check(chunks.get() == 4, "split into 4 chunks");
            check(rootCompletions.get() == 1,
                  "completion notification");
            check(root.isDone(), "root done");

            System.out.println("sum1to16=" + total.get());
            System.out.println("leafChunks=" + chunks.get());
            System.out.println("rootOnCompletionCalls="
                + rootCompletions.get());
            System.out.println("rootDone=" + root.isDone());
            System.out.println("PASS");
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 ForkedRangeSumDemo.java
java ForkedRangeSumDemo
```

**Stdout đã kiểm chứng:**

```text
sum1to16=136
leafChunks=4
rootOnCompletionCalls=1
rootDone=true
PASS
```

**Diễn giải:**

1. Khoảng [1,17) gồm đúng 16 số từ 1 đến 16; mỗi lần chia đôi cho đến độ dài tối đa 4.
2. Mỗi khi fork nhánh phải, parent gọi `addToPendingCount(1)` **trước**.
3. Parent tiếp tục xử lý nhánh trái, không chờ nhánh phải bằng join.
4. Mỗi đoạn cơ sở cộng các số vào AtomicInteger, tăng số chunk và gọi `tryComplete()`.
5. Các tín hiệu đi qua liên kết completer; root chỉ được đánh dấu hoàn tất khi giao thức đếm được thỏa.
6. `onCompletion` của root ghi nhận một lần callback, không tính lại tổng vì accumulator đã được ghi atomically từ các leaf.
7. Tổng 136, 4 chunks và callback 1 là kết quả ổn định, không phụ thuộc thứ tự worker xử lý từng chunk.

**Có thể dùng một `int` thông thường thay AtomicInteger ở đây không?** Không an toàn nếu nhiều leaf trực tiếp cập nhật cùng biến đó mà không đồng bộ, vì có lost update. Đối với tổng phân đoạn có cấu trúc, một phương án khác là lưu kết quả vào các vùng/slot riêng rồi combine trong `onCompletion`, có kiểm soát việc publish và vị trí dữ liệu. Bài này dùng AtomicInteger để tập trung vào pending count.

## 8. onCompletion(caller): callback khi đủ tín hiệu

`onCompletion(CountedCompleter<?> caller)` là phương thức có thể override. Nó chạy trong đường **normal completion** khi `tryComplete()` gặp pending count 0, hoặc khi gọi `complete(T)` vô điều kiện.

Tham số `caller` là **task vừa gọi vào bước completion tại tầng đó**, có thể:

- Bằng `this`, nếu task tự gọi tryComplete đúng lúc pending đã 0.
- Là một subtask, nếu tín hiệu từ child làm cha đi vào nhánh completion.
- Là một caller ở cấp dưới trong traversal; không nên suy thứ tự cố định khi có chạy song song.

Trong cây có kết quả con, có thể dùng `caller` để tìm nhánh đã hoàn thành và kết hợp kết quả, theo protocol đã thiết kế.

### Callback không được coi là một worker riêng biệt

`onCompletion` chạy trong quá trình hoàn tất của một task, có thể trên thread của child cuối cùng hoặc thread thực thi self-signal. Không phụ thuộc thread cụ thể, thời điểm cụ thể hoặc thứ tự arrival trong logic nghiệp vụ. Callback nên ngắn và an toàn với concurrency.

Một sự kiện đáng lưu ý: theo JavaDoc, nếu pending counts được sử dụng đúng, `onCompletion` có thể đọc kết quả của các task đã hoàn tất mà không cần thêm synchronization chỉ để đảm bảo kết quả của các task đó, nhờ protocol completion. Điều đó **không miễn trách nhiệm** thread-safety cho state bị nhiều task đồng thời ghi vào cùng chỗ, hoặc cho những callback tự tạo side effect phức tạp.

### Một lần callback cho mỗi CountedCompleter?

Trong một cây được lập trình đúng, normal completion của mỗi task không nên bị kích hoạt lặp bằng nhiều tín hiệu sai. Nếu đếm thiếu hoặc gọi thừa tryComplete, có thể dẫn tới callback/propagation bất thường hoặc completion sớm. **Đừng dùng onCompletion như nơi bất kỳ thread nào cũng có thể gọi tùy ý**; nó phải là một phần của giao thức duy nhất.

## 9. Kết quả trả về: CountedCompleter<Void> và CountedCompleter<T>

Nhiều thuật toán CountedCompleter hoạt động theo side-effect có kiểm soát lên mảng hoặc accumulator, vì vậy lớp thường khai báo `CountedCompleter<Void>`. Khi đó `invoke()`/`join()` trên root **không trả kết quả tính toán**: chúng thường trả `null`; việc nhận kết quả diễn ra từ state riêng của task hoặc cấu trúc đã xử lý.

Nếu cần một `CountedCompleter<Integer>` hoặc `CountedCompleter<Result>` trả giá trị, cần định nghĩa rõ cách cung cấp result, thường override:

```java
// Snippet minh họa trong một lớp CountedCompleter<Integer>.
private int result;

@Override public Integer getRawResult() {
    return result;
}
```

`setRawResult(T)` mặc định không tự lưu một giá trị hữu ích trong CountedCompleter; đừng gọi `complete(value)` rồi mặc định cho rằng `getRawResult()` của lớp không override đã trở thành value. Chọn giữa giá trị trả về và external accumulator theo yêu cầu bài toán; không ghép nhầm hợp đồng của `RecursiveTask<T>` lên CountedCompleter.

## 10. API thay đổi pending count: tác động vào count chứ không tự phát tín hiệu

Những phương thức:

| Phương thức | Ý nghĩa |
| --- | --- |
| `getPendingCount()` | Đọc pending count hiện tại |
| `setPendingCount(int count)` | Đặt count mới |
| `addToPendingCount(int delta)` | Cộng delta atomically vào count |
| `compareAndSetPendingCount(int expected, int next)` | Đổi count bằng CAS nếu hiện tại bằng expected |
| `decrementPendingCountUnlessZero()` | Nếu count khác 0, giảm atomically; trả về **giá trị cũ** |
| `tryComplete()` | **Tín hiệu hoàn tất**: giảm count nếu dương, hoặc callback/propagate khi count đã 0 |

Điểm đặc biệt của `decrementPendingCountUnlessZero`: trả về **giá trị trước khi giảm**, không phải giá trị sau. Nếu cũ là 5 thì kết quả trả là 5, còn count sau lời gọi là 4.

### setPendingCount(0) không phải complete()

Đoạn mã:

```java
task.setPendingCount(0);
```

chỉ thay số, không gọi `onCompletion` và không mark task done. Tương tự, có thể gọi `addToPendingCount(-1)` để chỉnh số nhưng **không có thông báo completion tự phát**. Không thay `tryComplete` bằng thao tác giảm count tùy ý trong các protocol chuẩn.

**Lưu ý:** `setPendingCount` dưới concurrent modifications phải được phối hợp rất cẩn thận; nếu có nhiều thread tác động count, thiết kế đúng thường dùng atomic increment/CAS theo thứ tự đăng ký rõ ràng. Không lấy `getPendingCount()` rồi tự `setPendingCount(old+1)` giữa các thread, vì nó có thể gây lost update ở cấp logic.

## 11. Chương trình 3 — set, add, CAS và giảm count không tự done

Tệp **`PendingCounterApiDemo.java`** cô lập pending count API trong một task không fork, để quan sát chính xác các kết quả và việc phải có tín hiệu `tryComplete()` cuối cùng.

```java
import java.util.concurrent.*;

public class PendingCounterApiDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class Probe extends CountedCompleter<Void> {
        @Override public void compute() {}
    }

    public static void main(String[] args) {
        Probe task = new Probe();
        task.setPendingCount(2);

        boolean compareSucceeded =
            task.compareAndSetPendingCount(2, 4);
        task.addToPendingCount(1);

        int oldCount = task.decrementPendingCountUnlessZero();
        int nowCount = task.getPendingCount();
        boolean stillIncomplete = !task.isDone();

        task.setPendingCount(0);
        boolean zeroAloneNotComplete = !task.isDone();
        task.tryComplete();

        check(compareSucceeded && oldCount == 5 && nowCount == 4,
              "atomic count adjustments");
        check(stillIncomplete && zeroAloneNotComplete,
              "count operations do not signal completion");
        check(task.isDone(), "tryComplete actually completes");

        System.out.println("casSucceeded=" + compareSucceeded);
        System.out.println("previousCount=" + oldCount);
        System.out.println("remainingAfterDecrement=" + nowCount);
        System.out.println("zeroAloneNotComplete="
            + zeroAloneNotComplete);
        System.out.println("doneAfterTryComplete=" + task.isDone());
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 PendingCounterApiDemo.java
java PendingCounterApiDemo
```

**Stdout đã kiểm chứng:**

```text
casSucceeded=true
previousCount=5
remainingAfterDecrement=4
zeroAloneNotComplete=true
doneAfterTryComplete=true
PASS
```

**Giải thích:** ban đầu count=2; CAS 2→4 thành công; add(1) thành 5; decrement-unless-zero trả **5**, nhưng count mới là 4. Chỉ khi set count 0 rồi gọi tryComplete mới mark done. Đây là demo **API count tách rời completion**, không phải mẫu tự tay set count 0 để sửa một task thực đang đợi child. Trong hệ thống thật, phải phát đủ nghĩa vụ đúng cách, không dùng setPendingCount(0) để cưỡng ép task có child chưa xong.

## 12. So sánh tryComplete, propagateCompletion, complete và quietlyCompleteRoot

Bốn API này đều liên quan hoàn tất, nhưng **không tương đương**.

| Phương thức | Khi pending > 0 | Khi pending = 0 | Có gọi onCompletion? |
| --- | --- | --- | --- |
| `tryComplete()` | Giảm count 1, dừng | Chạy callback rồi đi lên completer hoặc hoàn tất root | **Có**, tại các task được hoàn tất bình thường trong đường đi |
| `propagateCompletion()` | Giảm count 1, dừng | Đi lên completer hoặc hoàn tất root, **bỏ qua callback** | **Không** |
| `complete(T rawResult)` | **Không đợi count về 0** | Hoàn tất task hiện tại, có thể báo completer | **Có** trên task được complete; ancestor qua tryComplete |
| `quietlyCompleteRoot()` | **Bỏ qua count của root** | Đánh dấu root hoàn tất bình thường | **Không** |

### tryComplete()

Phổ biến nhất khi muốn một callback tổng hợp/công bố kết quả theo normal completion.

### propagateCompletion()

Giống đường truyền tín hiệu của tryComplete nhưng **không chạy onCompletion** trên những task đi qua. Hữu ích khi kết quả đã được ghi trực tiếp vào mảng/accumulator và không cần callback ghép ở mỗi tầng. Đừng đổi từ tryComplete sang propagateCompletion nếu bạn cần onCompletion để tổng hợp kết quả, vì callback sẽ không chạy.

### complete(T rawResult)

Đây là **unconditional completion** trên task được gọi, bất kể pending count còn bao nhiêu. Nó gọi onCompletion cho task ấy, mark task completed rồi kích hoạt tryComplete trên completer của nó nếu có. Nó không giảm pending count của chính task.

Hữu ích cho những thuật toán cho phép một kết quả đủ để kết thúc sớm, không phải phương thức “đợi tất cả con” mặc định. Nếu cần kết quả T thực, phải thiết kế getRawResult/setRawResult phù hợp.

### quietlyCompleteRoot()

Dùng `getRoot().quietlyComplete()` để đánh dấu root completed bình thường mà không cần đợi pending count hay gọi onCompletion. Có thể dùng trong các thuật toán *early termination* như tìm thấy một kết quả đủ thỏa. Nhưng **nó không có nghĩa các task còn lại đã dừng hoặc bị cancel**. Chúng vẫn có thể đang chạy và gây side effect; cần thiết kế cơ chế dừng/phân loại kết quả tương ứng.

**Quy tắc:** khi mục tiêu là *wait-all* đúng nghĩa, đừng dùng `complete` hoặc `quietlyCompleteRoot` chỉ để thoát khỏi một root đang bị treo do đếm sai. Hãy sửa pending-count protocol.

## 13. Chương trình 4 — từng phương thức hoàn tất có hành vi riêng

Tệp **`CompletionModesDemo.java`** sử dụng các task manual không gửi vào pool. Mục đích là kiểm API độc lập với thread scheduling: pending từ 2 cần ba tryComplete; propagate bỏ callback; complete và quietlyCompleteRoot bỏ qua số pending.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class CompletionModesDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class Probe extends CountedCompleter<Void> {
        final AtomicInteger callbacks = new AtomicInteger();

        @Override public void compute() {}

        @Override public void onCompletion(
                CountedCompleter<?> caller) {
            callbacks.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        Probe normal = new Probe();
        normal.setPendingCount(2);

        normal.tryComplete();
        boolean firstStillPending =
            !normal.isDone() && normal.getPendingCount() == 1;

        normal.tryComplete();
        boolean secondStillPending =
            !normal.isDone() && normal.getPendingCount() == 0;

        normal.tryComplete();

        Probe noCallback = new Probe();
        noCallback.setPendingCount(1);
        noCallback.propagateCompletion();
        boolean intermediate =
            !noCallback.isDone()
            && noCallback.getPendingCount() == 0;
        noCallback.propagateCompletion();

        Probe forced = new Probe();
        forced.setPendingCount(3);
        forced.complete(null);

        Probe earlyRoot = new Probe();
        earlyRoot.setPendingCount(5);
        CountedCompleter<Void> child =
            new CountedCompleter<Void>(earlyRoot) {
                @Override public void compute() {}
            };
        child.quietlyCompleteRoot();

        check(firstStillPending && secondStillPending,
              "pending model");
        check(normal.isDone() && normal.callbacks.get() == 1,
              "tryComplete callback");
        check(intermediate && noCallback.isDone()
              && noCallback.callbacks.get() == 0,
              "propagate skips callback");
        check(forced.isDone() && forced.getPendingCount() == 3
              && forced.callbacks.get() == 1,
              "complete bypasses pending count");
        check(earlyRoot.isDone()
              && earlyRoot.getPendingCount() == 5
              && earlyRoot.callbacks.get() == 0,
              "quietlyCompleteRoot bypasses pending count");

        System.out.println("firstTryStillPending="
            + firstStillPending);
        System.out.println("secondTryStillPending="
            + secondStillPending);
        System.out.println("tryCompleteCallbacks="
            + normal.callbacks.get());
        System.out.println("propagateIntermediate=" + intermediate);
        System.out.println("propagateCallbacks="
            + noCallback.callbacks.get());
        System.out.println("forceDoneWithPending="
            + forced.getPendingCount());
        System.out.println("quietRootDoneWithPending="
            + earlyRoot.getPendingCount());
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 CompletionModesDemo.java
java CompletionModesDemo
```

**Stdout đã kiểm chứng:**

```text
firstTryStillPending=true
secondTryStillPending=true
tryCompleteCallbacks=1
propagateIntermediate=true
propagateCallbacks=0
forceDoneWithPending=3
quietRootDoneWithPending=5
PASS
```

**Giải thích từng output:**

- `firstTryStillPending=true`: khi pending 2, lời gọi đầu chỉ giảm thành 1.
- `secondTryStillPending=true`: lời gọi thứ hai giảm thành 0 **nhưng root chưa done**.
- `tryCompleteCallbacks=1`: lời gọi thứ ba khi pending đã 0 kích hoạt callback và hoàn tất root.
- `propagateIntermediate=true`: propagate đầu giảm 1→0, chưa done; propagate tiếp theo khi count=0 làm root done **không callback**.
- `forceDoneWithPending=3`: `complete(null)` đánh dấu task done nhưng **pending count của task vẫn 3**. Không có nghĩa ba child đã kết thúc.
- `quietRootDoneWithPending=5`: child gọi quietlyCompleteRoot làm root done nhưng pending vẫn 5; completion **không tự dừng công việc còn lại**.

Đây là demo về **cơ chế API**, không phải một thuật toán wait-all có thật. Đừng áp các lệnh ép hoàn tất để “vá” số đếm còn thiếu trong nghiệp vụ.

## 14. Completion traversal với firstComplete và nextComplete

Nếu `onCompletion` không phù hợp cho cách tổng hợp của bạn, `CountedCompleter` cung cấp:

- `firstComplete()`: nếu pending của task hiện tại bằng 0, trả **chính task đó** để xử lý; nếu khác 0, giảm count và trả null.
- `nextComplete()`: sau khi đã xử lý một task, thử đi tới completer; nếu ancestor pending dương, giảm count và trả null, nếu ancestor pending 0, trả ancestor để tiếp tục xử lý. Khi tới root không có completer, nó mark root completed và trả null.

Pattern:

```java
// Snippet minh họa bên trong một method của CountedCompleter.
for (CountedCompleter<?> c = firstComplete();
     c != null;
     c = c.nextComplete()) {
    // Xử lý c theo thuật toán riêng.
}
```

**Khác biệt với tryComplete:** đây là traversal để code ứng dụng tự xử lý từng task trả về, **không tự gọi onCompletion** trên mỗi node trong chuỗi. Dùng khi cần custom reduction/traversal. Nếu tự xử lý chưa đúng hoặc count thiếu, root có thể không done như mong muốn.

Một chi tiết quan trọng: việc xử lý node trong traversal không nhất thiết khiến từng leaf được đánh dấu completed như một `RecursiveTask` thông thường; mục tiêu của pattern là **hoàn tất root** qua traversal. Không mặc định join riêng mọi leaf sau khi sử dụng CountedCompleter với cách này.

## 15. Chương trình 5 — duyệt leafA, leafB rồi root

Tệp **`TraversalDemo.java`** minh họa trực tiếp cơ chế firstComplete/nextComplete mà không cần pool: hai leaf có completer root, root pending=1, hai tín hiệu leaf đi lên root.

```java
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class TraversalDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class Node extends CountedCompleter<Void> {
        final String name;
        final AtomicInteger callbackCalls;

        Node(CountedCompleter<?> parent, String name,
             AtomicInteger callbacks) {
            super(parent);
            this.name = name;
            this.callbackCalls = callbacks;
        }

        @Override public void compute() {}

        @Override public void onCompletion(
                CountedCompleter<?> caller) {
            callbackCalls.incrementAndGet();
        }
    }

    static void walk(Node leaf, List<String> visited) {
        for (CountedCompleter<?> cur = leaf.firstComplete();
             cur != null;
             cur = cur.nextComplete()) {
            visited.add(((Node) cur).name);
        }
    }

    public static void main(String[] args) {
        AtomicInteger callbacks = new AtomicInteger();

        Node root = new Node(null, "root", callbacks);
        root.setPendingCount(1);
        Node a = new Node(root, "leafA", callbacks);
        Node b = new Node(root, "leafB", callbacks);

        List<String> visited = new ArrayList<>();

        walk(a, visited);
        boolean rootStillIncomplete = !root.isDone();

        walk(b, visited);
        boolean rootDone = root.isDone();

        check(rootStillIncomplete && rootDone, "traversal");
        check("leafA,leafB,root".equals(
              String.join(",", visited)), "sequence");
        check(callbacks.get() == 0, "no callbacks");

        System.out.println("visited="
            + String.join(",", visited));
        System.out.println("rootIncompleteAfterFirst="
            + rootStillIncomplete);
        System.out.println("rootDoneAfterSecond=" + rootDone);
        System.out.println("onCompletionCalls=" + callbacks.get());
        System.out.println("PASS");
    }
}
```

```bash
javac -encoding UTF-8 TraversalDemo.java
java TraversalDemo
```

**Stdout đã kiểm chứng:**

```text
visited=leafA,leafB,root
rootIncompleteAfterFirst=true
rootDoneAfterSecond=true
onCompletionCalls=0
PASS
```

**Diễn giải:** lần traversal đầu xử lý leafA; khi chuyển lên root, pending root từ 1→0, rồi dừng. Lần traversal thứ hai xử lý leafB, gặp root đã pending=0 nên traversal đi qua root rồi mark root complete. `onCompletion` không được gọi vì đây là đường custom traversal, khác với tryComplete.

Thứ tự `leafA,leafB,root` là **do test gọi walk(a) rồi walk(b) một cách tuần tự**, không phải cam kết scheduling của ForkJoinPool. Trong thuật toán parallel, thứ tự hoàn thành leaf có thể khác.

## 16. Completion khi có exception: onExceptionalCompletion

Normal completion và exceptional completion là **hai đường khác nhau**:

- `onCompletion(caller)` thực hiện callback cho normal completion.
- `onExceptionalCompletion(Throwable ex, CountedCompleter<?> caller)` được dùng khi task hoàn thành ngoại lệ, ví dụ `compute()` ném exception.
- Giá trị boolean trả về của `onExceptionalCompletion` điều khiển việc lỗi có được **tiếp tục lan lên completer** không.
- Mặc định phương thức này trả **true**, cho phép lan truyền exception lên ancestor chưa completed.

Một callback có thể override:

```java
@Override
public boolean onExceptionalCompletion(
        Throwable ex, CountedCompleter<?> caller) {
    // Ghi nhận lỗi hoặc phân loại tại đây.
    return true; // Tiếp tục lan lên completer.
}
```

**Đừng tự mặc định trả false để “nuốt” lỗi.** Nếu bạn chặn propagation mà không có giao thức recovery riêng, root có thể vẫn đang chờ pending signal không bao giờ đến, làm người gọi `invoke()`/`join()` treo. Trả false chỉ nên dùng khi thuật toán có cách xử lý lỗi/phục hồi và hoàn tất các nghĩa vụ còn lại rõ ràng.

### Một exception ở child có thể làm root kết thúc bất thường

Khi child compute ném `IllegalStateException`, callback onExceptionalCompletion của child có thể chạy, sau đó lỗi được truyền tới root nếu trả true. Root có thể ở trạng thái `isCompletedAbnormally()==true` và giữ exception qua `getException()`.

Một điểm dễ nhầm: khi `ForkJoinTask.invoke` quan sát exception từ task chạy trên một thread khác, **message/stack trace ngoại lệ ngoài có thể thay đổi** theo cách runtime rethrow/wrapping; không nên kiểm test dựa vào nguyên văn message của wrapper giữa các JDK. Hãy kiểm loại lỗi, trạng thái và cause theo contract.

### onCompletion không đồng nghĩa finally

Nếu compute hoặc child lỗi, không thể dựa vào `onCompletion` như một `finally` chạy trong mọi tình huống. Đường normal và exceptional khác nhau. Tài nguyên như stream, socket hoặc lock lấy trong compute vẫn cần cleanup đúng nơi bằng `try/finally` hoặc phương án quản lý tài nguyên thích hợp. Không đẩy việc mở khóa vào onCompletion nếu exception có thể khiến callback đó không chạy.

## 17. Chương trình 6 — exception ở child lan lên root

Tệp **`ExceptionalPropagationDemo.java`** có một root fork một leaf. Leaf cố ý ném IllegalStateException; root override cả normal callback và exceptional callback. Mã in ra **các boolean/counter ổn định**, không dựa vào exception message có thể khác khi chuyển thread.

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class ExceptionalPropagationDemo {
    static void check(boolean ok, String label) {
        if (!ok) throw new AssertionError(label);
    }

    static final class Root extends CountedCompleter<Void> {
        final AtomicInteger rootExceptions = new AtomicInteger();
        final AtomicInteger rootSuccessCallbacks = new AtomicInteger();
        final AtomicInteger leafExceptions = new AtomicInteger();

        @Override public void compute() {
            setPendingCount(1);
            new FailingLeaf(this).fork();
            tryComplete();
        }

        @Override public void onCompletion(
                CountedCompleter<?> caller) {
            rootSuccessCallbacks.incrementAndGet();
        }

        @Override public boolean onExceptionalCompletion(
                Throwable ex, CountedCompleter<?> caller) {
            rootExceptions.incrementAndGet();
            return true;
        }

        final class FailingLeaf extends CountedCompleter<Void> {
            FailingLeaf(CountedCompleter<?> parent) {
                super(parent);
            }

            @Override public void compute() {
                throw new IllegalStateException("leaf-failed");
            }

            @Override public boolean onExceptionalCompletion(
                    Throwable ex, CountedCompleter<?> caller) {
                leafExceptions.incrementAndGet();
                return true;
            }
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        Root root = new Root();
        boolean caughtRootFailure = false;

        try {
            try {
                pool.invoke(root);
                throw new AssertionError("root must fail");
            } catch (IllegalStateException ex) {
                caughtRootFailure = true;
            }

            check(caughtRootFailure, "failure observed");
            check(root.isCompletedAbnormally(),
                  "root exceptional");
            check(root.getException() != null,
                  "root exception stored");
            check(root.rootExceptions.get() == 1,
                  "root notification");
            check(root.leafExceptions.get() == 1,
                  "leaf notification");
            check(root.rootSuccessCallbacks.get() == 0,
                  "no normal completion");

            System.out.println("caughtRootFailure="
                + caughtRootFailure);
            System.out.println("rootExceptional="
                + root.isCompletedAbnormally());
            System.out.println("leafExceptionCallbacks="
                + root.leafExceptions.get());
            System.out.println("rootExceptionCallbacks="
                + root.rootExceptions.get());
            System.out.println("normalCompletionCallbacks="
                + root.rootSuccessCallbacks.get());
            System.out.println("PASS");
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac -encoding UTF-8 ExceptionalPropagationDemo.java
java ExceptionalPropagationDemo
```

**Stdout:**

```text
caughtRootFailure=true
rootExceptional=true
leafExceptionCallbacks=1
rootExceptionCallbacks=1
normalCompletionCallbacks=0
PASS
```

**Phân tích:** root đã đăng ký một nghĩa vụ child và phát self-signal. Leaf không gọi tryComplete vì compute ném exception; thay vào đó cơ chế exceptional completion lan từ leaf lên root thông qua các callback trả true. Root kết thúc bất thường, không gọi normal `onCompletion`. Khi quan sát bằng pool.invoke, code nhận lỗi, và phần kiểm tra xác nhận root đã completed exceptionally.

Điều đáng nhớ là **error propagation không tương đương một normal pending signal**. Nếu tùy biến callback exceptional để chặn lỗi, bạn phải chủ động xác định root sẽ hoàn tất, retry hoặc cancel như thế nào; không chỉ thay `return true` bằng `return false`.

## 18. Các lỗi liveness do pending count sai

### 18.1 Quên tryComplete: root có thể đợi vô hạn

```java
// Pseudocode cố ý sai: không chạy thực nghiệm vì có thể treo.
class Broken extends CountedCompleter<Void> {
    @Override public void compute() {
        doWork();
        // thiếu tryComplete();
    }
}
```

Nếu root không nhận tín hiệu completion nào khác, `invoke()` có thể chờ mãi. Việc `compute()` return không cứu giao thức này.

### 18.2 Pending quá lớn: thiếu tín hiệu

Nếu root pending=3 nhưng chỉ có 3 lời gọi tryComplete tới root, count giảm lần lượt 3→2→1→0 và root **vẫn chưa done**. Cần một lời gọi nữa khi pending đã bằng 0; hoặc sửa cách khởi tạo count phù hợp số tín hiệu thực.

### 18.3 Pending quá nhỏ: complete quá sớm

Nếu root pending=1 nhưng thực tế có 4 child signals và self-signal, root có thể được mark done trước khi tất cả child kết thúc. Caller nhận kết quả chưa đầy đủ, các task sau vẫn chạy và có thể cập nhật state ngoài ý muốn.

### 18.4 Fork trước khi đăng ký pending

Nếu child cực nhanh, nó có thể signal parent khi parent chưa tăng count, gây completion/propagation trên trạng thái cũ. Luôn register pending **trước** fork trong pattern dùng addToPendingCount.

### 18.5 Tín hiệu thừa hoặc duplicate

Nếu một child gọi tryComplete hai lần, nó có thể phát nhiều signal lên completer hoặc kích hoạt trạng thái không phù hợp. Mỗi completion obligation cần một giao thức **phát đúng một lần**; tránh gọi tryComplete ở cả hai nhánh `catch` và `finally` một cách vô điều kiện nếu đường exceptional completion đã có logic riêng.

### 18.6 Callback update count tùy tiện

Nếu `onCompletion` của task sửa pending count của chính nó hoặc parent mà không có protocol được chứng minh, có thể sinh race khó theo dõi. Ưu tiên thiết kế count rõ ràng khi đăng ký child; callback chủ yếu kết hợp kết quả hoặc xác nhận một phase đã xong.

### 18.7 Gọi join ở vị trí không cần thiết

Nếu một CountedCompleter parent `join()` chính các child chưa được đánh dấu done theo giao thức của chúng, có thể xảy ra chờ vô hạn hoặc mất tính song song. CountedCompleter được thiết kế để có thể hoàn tất root nhờ propagation mà không bắt buộc join từng leaf. Nếu thuật toán thật cần join con để lấy result, có thể `RecursiveTask` là mô hình dễ hiểu hơn.

## 19. Root completion có phải toàn bộ con đã dừng?

**Chỉ đúng nếu giao thức pending/tín hiệu của bạn đảm bảo điều đó.** Một root được mark done bởi `tryComplete` đúng protocol wait-all có thể đại diện cho toàn bộ việc đã hoàn thành. Nhưng root bị `complete(null)` hoặc `quietlyCompleteRoot()` sớm thì không thể khẳng định các subtasks còn lại đã dừng.

Điều này ảnh hưởng:

- Ghi dữ liệu ra mảng/collection sau `invoke()`.
- Đóng file/socket sau khi root được mark done.
- Shutdown executor và lifecycle tác vụ.
- Công bố giá trị kết quả, phát event và side effects.
- Retry một task thất bại hoặc hủy các nhánh đang chạy.

Nếu bài toán có **early exit**, ví dụ tìm một phần tử thỏa điều kiện, có thể dùng AtomicReference chứa đáp án, đánh dấu root done khi đã tìm thấy, rồi để các nhánh còn lại **kiểm tra cờ dừng** trước khi tiếp tục; nhưng đó là một protocol riêng. `quietlyCompleteRoot` không tự cancel hay interrupt workers.

## 20. Ranh giới giữa CountedCompleter và synchronized/barrier

`CountedCompleter` không phải mutex hay transaction engine. Pending count cho biết khi nào các nghĩa vụ hoàn tất **theo protocol**, không ngăn hai leaf cùng sửa một biến mutable không thread-safe.

Để cập nhật kết quả:

- Nếu các leaf viết vào **các đoạn mảng độc lập**, mỗi leaf có thể xử lý vùng của mình; người gọi đọc sau khi root hoàn tất đúng protocol.
- Nếu mọi leaf cùng tăng accumulator, cần `AtomicInteger`, `LongAdder` hoặc kỹ thuật reduction an toàn.
- Nếu onCompletion combine kết quả của children, cần đảm bảo children đã publish chúng theo liên kết completion và không tiếp tục mutate sau khi đã signal.
- Nếu có nhiều bước ghi database, chỉ biết tất cả tasks xong **không** có nghĩa các bước đã commit nguyên tử hay rollback như một transaction.

Đừng đồng nhất pending count với `CountDownLatch`: latch là primitive đếm tín hiệu cho chờ, còn CountedCompleter tích hợp **traversal lên completer, task graph trong ForkJoinPool, onCompletion và exceptional propagation**. Chúng có thể giải quyết những mục tiêu khác nhau.

## 21. Những quy tắc khi chạy trong ForkJoinPool

1. **Không tạo quá nhiều tác vụ quá nhỏ.** Fork/join có overhead; đặt threshold phù hợp để leaf xử lý đủ công việc.
2. **Đăng ký số tín hiệu trước fork.** Một race completion sớm có thể rất khó tái hiện bằng stress test.
3. **Không block dài trong compute** nếu không thật cần thiết. ForkJoinPool được tối ưu cho task nhỏ có thể hỗ trợ work-stealing; I/O chờ có thể làm giảm parallelism.
4. **Không dùng pending count để đo số luồng.** Worker pool và completion protocol là hai lớp khác nhau.
5. **Xử lý exception rõ ràng.** Callback `onExceptionalCompletion` có thể lan đến root, không qua đường onCompletion bình thường.
6. **Tránh chia sẻ state không đồng bộ.** Completion protocol không biến các phép tăng thông thường thành atomic.
7. **Có chiến lược lifecycle của pool riêng.** Dùng `pool.shutdown()` trong finally khi bạn tạo một pool chuyên dụng và kết thúc công việc.
8. **Không giả định thứ tự callback/leaf.** Nếu output cần thứ tự, sắp xếp hoặc lưu kết quả theo index riêng.
9. **Test trên JDK hiện đại cũng với mức --release 8.** Điều này giúp nhận ra mã vô tình dùng API chỉ có từ Java 9+.
10. **Thiết kế observability hợp lý.** Theo dõi root done/exception, số leaf thật đã xử lý và kết quả/invariant; pending count đơn lẻ không phải chỉ số tiến độ đáng tin cậy.

### Nên dùng common pool hay pool riêng?

`ForkJoinTask.fork()` trong một worker đang chạy trong pool tương ứng có thể đưa task vào hàng đợi của pool đó. Khi entry point được gọi bằng `ForkJoinPool.invoke(root)` trên một pool chuyên dụng, task con thường chạy trong cùng pool. Điều này giúp ví dụ kiểm soát parallelism và cleanup.

Trong hệ thống lớn, dùng common pool có thể gây cạnh tranh với công việc khác. Chọn pool riêng khi cần cách ly workload và có chính sách shutdown, hoặc dùng executor thích hợp cho công việc I/O. Không tạo một pool mới cho mỗi phần tử dữ liệu.

## 22. Bảng quyết định các phương thức completion

| Tình huống | API thường dùng | Lý do |
| --- | --- | --- |
| Một nhánh xử lý xong, cần báo parent chờ | `tryComplete()` | Có callback/propagation khi đủ tín hiệu |
| Một nhánh xong, không cần onCompletion ở các tầng | `propagateCompletion()` | Truyền count, bỏ qua callback |
| Fork thêm một nhánh | `addToPendingCount(1)` **trước fork** | Đăng ký nghĩa vụ mới |
| Muốn set count lúc chưa chạy song song | `setPendingCount(count)` | Khởi tạo protocol |
| Nhiều bên điều chỉnh count đồng thời | `addToPendingCount`/CAS | Atomic adjustments |
| Cần kiểm value count hiện tại | `getPendingCount()` | Chẩn đoán/điều khiển, không phải done flag |
| Cần một root result sớm theo policy | `quietlyCompleteRoot()` | Đánh dấu root done không đợi toàn bộ |
| Cần force-complete một task có raw result | `complete(value)` | Bỏ qua own pending; cần biết side effects |
| Cần tùy chỉnh quá trình đi lên completer | `firstComplete()/nextComplete()` | Manual completion traversal |
| Muốn ghép kết quả child sau khi đủ signals | Override `onCompletion(caller)` | Tổng hợp normal completion |
| Một child ném exception | Override `onExceptionalCompletion` khi cần | Ghi nhận/kiểm soát exceptional propagation |
| Cần đợi tất cả children theo mô hình đơn giản | Cân nhắc `RecursiveTask`/`invokeAll` | Thường trực giác hơn |
| Nhiều service/database records cần atomicity | Transactional datastore | CountedCompleter không có ACID |

## 23. Ma trận kiểm thử để phát hiện count sai

| Trường hợp | Kỳ vọng |
| --- | --- |
| Pending mặc định | 0 |
| `setPendingCount(2)` rồi 1 `tryComplete` | pending=1; chưa done |
| Lời gọi `tryComplete` thứ hai | pending=0; vẫn chưa done |
| Lời gọi `tryComplete` thứ ba | onCompletion; root done |
| `setPendingCount(0)` đơn lẻ | Không tự done |
| `addToPendingCount(1)` | Chỉ tăng count, không fork task |
| `compareAndSetPendingCount` đúng expected | Đổi count atomically |
| `decrementPendingCountUnlessZero` khi count=5 | Trả 5, sau đó count=4 |
| Root fork 2 child + self-signal; pending=2 | root done sau cả 3 obligations |
| Fork phải, xử lý trái; pending increment trước fork | Sum đúng, root complete đúng |
| Thay `tryComplete` bằng `propagateCompletion` | Không chạy onCompletion |
| `complete(null)` với pending=3 | Task done, pending vẫn 3 |
| `quietlyCompleteRoot` với pending=5 | Root done sớm, pending vẫn 5 |
| `firstComplete/nextComplete` với hai leaves | Custom traversal về root |
| Child compute ném IllegalStateException | Exceptional propagation lên root |
| Override onExceptionalCompletion trả false | Phải kiểm protocol recovery, không gây root treo |
| Không gọi tryComplete trên leaf | Có thể chờ vô hạn |
| Fork child trước register pending | Race complete sớm |
| Child báo completion trùng | Có thể hoàn tất sớm/nhầm |
| Callback chỉ dành cho normal completion | Không chạy trên đường lỗi thông thường |
| Nhiều leaf cùng cộng int thường | Lost update có thể xảy ra |
| Dùng AtomicInteger cho accumulator | Tránh race trên phép tăng cộng |
| Root done sau wait-all | Kết quả stable theo protocol |
| Root done do early exit | Các leaf còn lại có thể vẫn chạy |
| Dùng ForkJoinPool.invoke(root) | Caller đợi root completed/exception |
| Có nhiều task rất nhỏ | Benchmark overhead và work-stealing |
| JDK mới với --release 8 | Không dùng API ngoài mức Java 8 |

Để test không bị treo, unit test nên dùng input nhỏ và xác định, có cơ chế giới hạn thời gian ở tầng harness. Nếu cố ý trình diễn trường hợp thiếu tín hiệu, **không gọi invoke() vô hạn** trong chương trình demo. Thay vào đó dùng kiểm thử non-blocking trên trạng thái count/done như `CompletionModesDemo`, hoặc sử dụng timeout của framework test.

## 24. Những sai lầm phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ return khỏi compute() tự done | Root có thể treo | Gọi tryComplete theo protocol |
| Coi pending là số thread đang chạy | Theo dõi sai | Đếm completion obligations |
| Tưởng fork tự tăng pending | Thiếu đăng ký child | Register trước fork |
| Đặt pending=N nhưng chỉ có N signals | Count về 0 nhưng chưa done | Có self-signal hoặc điều chỉnh count |
| Đặt pending quá nhỏ | Hoàn tất sớm | Đếm đúng nghĩa vụ |
| Gọi tryComplete hai lần từ một leaf | Tín hiệu thừa | Quy tắc một signal cho mỗi obligation |
| Giảm count bằng setPendingCount thay tryComplete | Không truyền completion | Dùng đúng API completion |
| Thay tryComplete bằng propagateCompletion bừa | Mất onCompletion | Chỉ khi không cần callback |
| Dùng complete(null) để sửa việc đếm sai | Root/child chưa xong vẫn báo done | Sửa protocol |
| Dùng quietlyCompleteRoot như cancel-all | Các nhánh khác vẫn chạy | Tạo cancellation protocol riêng |
| Gọi join từng leaf trong graph CountedCompleter | Có thể treo/giảm song song | Chờ root theo propagation |
| Bắt onCompletion để dọn tài nguyên cả khi lỗi | Exceptional path khác | Cleanup bằng finally |
| Chặn exception propagation mà không hoàn tất parent | Root có thể chờ mãi | Quy định recovery rõ |
| Không đồng bộ accumulator dùng chung | Lost update | Atomic/reduction |
| Tự tính lại parent count sau khi fork | Race với child nhanh | Increment trước fork |
| Dùng getPendingCount==0 thay isDone | Sai trạng thái hoàn tất | Dùng isDone/invoke/join trên root |
| Dùng số task pending làm progress bar chính xác | Pending không giữ task identity | Theo dõi progress riêng |
| In thứ tự leaf như một kết quả cố định | Scheduler thay đổi | Output deterministic theo index |
| Tạo quá nhiều task quá nhỏ | Overhead cao | Chọn threshold |
| Giữ pool chuyên dụng nhưng không shutdown | Rò rỉ tài nguyên | finally shutdown |
| Tin CountedCompleter đảm bảo DB transaction | Không rollback/durability | Datastore transaction |

## 25. Bài tập thực hành và đáp án

### Bài 1 — ba tín hiệu

**Đề:** một CountedCompleter gốc pending=2. Ba lời gọi `tryComplete()` đến root, không có callback thay count. Sau lời gọi thứ hai root đã done chưa?

**Đáp án:** chưa. Call 1 giảm 2→1, call 2 giảm 1→0, call 3 thấy count 0 mới gọi onCompletion và mark root done.

### Bài 2 — chia hai nhánh

**Đề:** root fork hai child và tự xử lý một phần. Mỗi bên sẽ phát đúng một signal. Đặt pending root bằng bao nhiêu theo mẫu dùng self-signal?

**Đáp án:** 2. Có 3 signals (2 child + root self), nên pending2 cho phép hai lần đầu giảm và lần cuối hoàn tất.

### Bài 3 — không có self-signal

**Đề:** root chỉ nhận đúng 2 tín hiệu từ hai child và không phát self-signal. Theo mô hình đơn giản, pending nên là bao nhiêu để child thứ hai kích hoạt completion?

**Đáp án:** 1. Tín hiệu đầu làm 1→0, tín hiệu sau thấy 0 mới hoàn tất. Phải chắc chắn không có tín hiệu khác xen vào và root đã thiết lập quan hệ đúng.

### Bài 4 — fork trước

**Đề:** parent fork child rồi mới addToPendingCount(1). Rủi ro nào?

**Đáp án:** child có thể complete cực nhanh trước khi parent đăng ký nghĩa vụ, gây tín hiệu trên count cũ và root complete sớm.

### Bài 5 — return khỏi compute

**Đề:** một CountedCompleter không fork gì, compute chỉ cập nhật một field rồi return mà không tryComplete. Liệu root.invoke chắc chắn kết thúc?

**Đáp án:** không. CountedCompleter cần completion protocol riêng; thường phải gọi tryComplete để đánh dấu normal completion.

### Bài 6 — propagateCompletion

**Đề:** thay tất cả `tryComplete` bằng `propagateCompletion` trong một cây cần combine ở `onCompletion`. Có gì sai?

**Đáp án:** propagateCompletion không gọi onCompletion, nên logic combine sẽ bị bỏ qua. Chỉ dùng khi không cần callback.

### Bài 7 — complete(null)

**Đề:** task pending=4 gọi `complete(null)`. Điều đó chứng minh bốn child đã hoàn thành chưa?

**Đáp án:** không. complete bỏ qua own pending, đánh dấu completed; children có thể còn chạy.

### Bài 8 — quietlyCompleteRoot

**Đề:** một nhánh tìm được đáp án sớm, gọi quietlyCompleteRoot. Các nhánh khác có tự bị hủy không?

**Đáp án:** không. Chúng có thể vẫn chạy; cần cờ dừng/cancellation policy riêng nếu muốn giảm công việc thừa.

### Bài 9 — CAS pending

**Đề:** task pending=2; `compareAndSetPendingCount(2,4)` trả true, sau đó `addToPendingCount(1)` và `decrementPendingCountUnlessZero()`. Giá trị trả của decrement và count sau đó là gì?

**Đáp án:** decrement trả **5** (count cũ); count mới là **4**. Chưa có completion signal nếu chỉ gọi những API count.

### Bài 10 — custom traversal

**Đề:** có cần `onCompletion` được gọi tự động ở mỗi node trong vòng `firstComplete()/nextComplete()` không?

**Đáp án:** không. Đây là cơ chế traversal riêng; ứng dụng xử lý từng node được trả về. Callback onCompletion không tự chạy như đường tryComplete.

### Bài 11 — child exception

**Đề:** child compute ném IllegalStateException. Root onCompletion có chắc chắn chạy không?

**Đáp án:** không. Đường lỗi đi qua exceptional completion và có thể tới onExceptionalCompletion ở completer. Cần phân biệt normal và exceptional callback.

### Bài 12 — ngăn propagation lỗi

**Đề:** override `onExceptionalCompletion` trả false để lỗi không lên root. Còn việc gì phải làm?

**Đáp án:** thiết kế cách root tiếp tục hoặc hoàn tất đúng protocol; không chỉ nuốt lỗi rồi để count chờ một tín hiệu không đến.

### Bài 13 — kết quả Void

**Đề:** `CountedCompleter<Void>` tính tổng bằng AtomicInteger. `root.invoke()` có trực tiếp trả tổng không?

**Đáp án:** không; kết quả trả của Void là null. Đọc accumulator sau khi root completed đúng protocol hoặc thiết kế CountedCompleter<T> với getRawResult.

### Bài 14 — khi nào không nên dùng CountedCompleter?

**Đề:** ứng dụng có cấu trúc chia đôi đơn giản, mỗi nhánh trả int và cha join 2 kết quả. Có nhất thiết chọn CountedCompleter?

**Đáp án:** không. `RecursiveTask<Integer>` thường rõ ràng hơn. Chọn CountedCompleter khi cần completion traversal/protocol phù hợp.

## 26. Câu hỏi tự kiểm tra

**1. CountedCompleter kế thừa lớp nào?**  
`ForkJoinTask<T>`.

**2. Pending count mặc định là bao nhiêu?**  
0 nếu không được khởi tạo khác.

**3. Fork một child có tự tăng count của completer không?**  
Không.

**4. Một lời gọi tryComplete thấy count=3 sẽ làm gì?**  
Giảm xuống 2 và dừng tại task đó.

**5. tryComplete thấy count=0 làm gì?**  
Gọi onCompletion rồi tiếp tục xử lý completer hoặc mark root completed.

**6. setPendingCount(0) có tự mark done không?**  
Không.

**7. propagateCompletion khác tryComplete ở đâu?**  
Không gọi onCompletion trên đường truyền.

**8. complete(null) có đợi pending count=0 không?**  
Không; nó bỏ qua own pending.

**9. quietlyCompleteRoot có cancel child không?**  
Không.

**10. onCompletion nhận đối số caller để làm gì?**  
Xác định task đang kích hoạt callback, có thể là self hoặc subtask.

**11. decrementPendingCountUnlessZero trả count cũ hay mới?**  
Count cũ.

**12. firstComplete/nextComplete dùng để làm gì?**  
Custom completion traversal.

**13. Khi child lỗi, callback nào liên quan?**  
`onExceptionalCompletion`.

**14. onExceptionalCompletion mặc định có lan lỗi lên completer không?**  
Có, thông qua giá trị trả true, nếu parent chưa completed.

**15. getRawResult của CountedCompleter<Void> mặc định trả gì?**  
Null.

**16. Có thể dùng pending để đo số worker không?**  
Không.

**17. Đăng ký pending trước hay sau fork?**  
Trước fork.

**18. Khi nào root done thực sự chứng minh hết child?**  
Khi protocol wait-all được thiết kế và thực hiện đúng; không phải chỉ vì đã gọi một phương thức force-complete.

## Tài liệu Java chính thức

- [Java SE 8 — CountedCompleter](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CountedCompleter.html) — pending count, tryComplete, propagateCompletion, complete, firstComplete/nextComplete, onCompletion, onExceptionalCompletion.
- [Java SE 26 — CountedCompleter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CountedCompleter.html) — xác nhận các API này còn hiện hành trong Java mới.
- [Java SE 8 — ForkJoinTask](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ForkJoinTask.html) — trạng thái completion, fork, invoke, join, exceptions.
- [Java SE 8 — ForkJoinPool](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ForkJoinPool.html) — scheduling/work stealing và quản lý executor.
- [Java SE 8 — RecursiveTask](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/RecursiveTask.html) — lựa chọn khác khi muốn join trả kết quả.
- [Java SE 8 — AtomicInteger](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/atomic/AtomicInteger.html) — shared accumulator an toàn.
- [Java SE 8 — CountDownLatch](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CountDownLatch.html) — hỗ trợ xây deterministic concurrency tests.
- [Java SE 8 — CompletionStage](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/CompletionStage.html) — đối chiếu mô hình completion khác khi xây pipeline bất đồng bộ.

**Ghi nhớ:** pending count là **số nghĩa vụ completion theo giao thức**, không phải số task được pool tự theo dõi. `tryComplete()` thấy count dương thì giảm một đơn vị; chỉ khi một signal đến lúc count đã bằng 0 mới kích hoạt onCompletion và truyền tiếp lên completer. Luôn đăng ký pending **trước fork**, phát đúng tín hiệu khi công việc thực sự xong và không coi return khỏi compute là done. `propagateCompletion` bỏ callback; `complete` và `quietlyCompleteRoot` có thể kết thúc sớm mà không đợi all children; `onExceptionalCompletion` điều khiển đường lỗi. Chọn CountedCompleter khi cần giao thức ghép tác vụ kiểu này, và kiểm thử cả đúng kết quả, trạng thái root, số callback lẫn những nhánh thiếu/thừa tín hiệu.