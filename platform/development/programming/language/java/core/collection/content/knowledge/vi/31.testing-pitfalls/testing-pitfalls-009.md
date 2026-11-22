# Kiểm thử tính nguyên tử, ảnh chụp và nhất quán yếu khi chạy đồng thời

> **Phạm vi:** Java Core Collections — Kiểm thử và lỗi. Bài này tập trung vào cách thiết kế phép thử và chọn tiêu chí đúng/sai cho collection bị đọc, ghi đồng thời. Ví dụ dùng Java 17 trở lên.

## 1. Ba hợp đồng khác nhau cần kiểm thử

Một collection hỗ trợ truy cập đồng thời không có nghĩa là mọi chuỗi thao tác của chương trình đều nguyên tử, cũng không có nghĩa việc duyệt nó sẽ thấy đúng một trạng thái cố định. Trước khi viết test, hãy xác định chính xác hợp đồng mà API hứa hẹn.

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ | Tiêu chí kiểm thử |
| --- | --- | --- | --- |
| **Tính nguyên tử (atomicity)** | Một thao tác có diễn ra như một đơn vị không thể bị xen vào hay không? | `ConcurrentHashMap.merge` cập nhật một key | Tổng số lần cập nhật không bị mất khi mọi tác vụ hoàn tất |
| **Ảnh chụp (snapshot)** | Người đọc có nhìn thấy một phiên bản cố định trong suốt lần duyệt không? | Iterator của `CopyOnWriteArrayList` | Iterator cũ không thấy phần tử thêm sau khi tạo iterator |
| **Nhất quán yếu (weak consistency)** | Khi có ghi đồng thời, iterator được phép phản ánh những thay đổi nào? | Iterator của `ConcurrentHashMap` | Không lỗi do sửa đổi đồng thời; mỗi mục quan sát được thỏa bất biến, nhưng không ép danh sách chính xác |

**Điểm mấu chốt:** một thao tác nguyên tử trên từng key không tạo ra snapshot nguyên tử của toàn map. Một iterator duyệt an toàn cũng không đồng nghĩa iterator trả về trạng thái của map tại một thời điểm duy nhất.

## 2. Nền tảng: data race, happens-before và linearizability

- **Data race:** nhiều luồng truy cập cùng dữ liệu có ít nhất một thao tác ghi mà thiếu cơ chế đồng bộ phù hợp; kết quả có thể phụ thuộc lịch chạy và tính hiển thị bộ nhớ. `HashMap`, `ArrayList` thông thường không cung cấp hợp đồng an toàn cho việc sửa đồng thời không đồng bộ.
- **Happens-before:** quan hệ đảm bảo thứ tự và hiển thị giữa các hành động. Chẳng hạn, các thao tác trước `CountDownLatch.countDown()` có quan hệ happens-before với tác vụ vượt qua `await()` tương ứng; tác vụ kết thúc có quan hệ happens-before với hành động sau `Future.get()` thành công trong luồng chờ. Dùng các cơ chế này để test đọc kết quả cuối một cách hợp lệ.
- **Atomicity / linearizability:** một phép thao tác nguyên tử có thể được lý giải như xảy ra tại một điểm giữa lúc gọi và lúc trả về. Khi nhiều lời gọi chồng lấn, thứ tự quan sát được phải phù hợp với một trình tự hợp lệ theo hợp đồng của chính phép thao tác. Không suy rộng điều này cho nhiều lệnh riêng biệt.
- **Visibility khác atomicity:** `volatile` có thể giúp thấy giá trị cập nhật nhưng không biến `x++` thành phép cộng nguyên tử. `synchronized` chỉ bảo vệ toàn bộ giao dịch nếu mọi đường đọc/ghi liên quan dùng cùng một khóa.

Ví dụ không nguyên tử:

```java
Integer old = counts.get("java");
counts.put("java", old + 1);
```

`ConcurrentHashMap.get` và `put` đều an toàn khi gọi riêng, nhưng hai luồng vẫn có thể cùng đọc `0` rồi cùng ghi `1`. Muốn tăng bộ đếm cùng một key, dùng `merge` hoặc `compute` trên `ConcurrentHashMap`, hoặc dùng biến đếm riêng như `AtomicInteger`/`LongAdder` khi mô hình dữ liệu thích hợp.

## 3. Kiểm thử lỗi mất cập nhật bằng lịch chạy có kiểm soát

Chỉ khởi chạy hai luồng hàng nghìn lần rồi hy vọng lỗi xuất hiện là phép thử yếu: race có thể không xảy ra trong máy thử. Ta tạo lịch chạy để **cả hai luồng bắt buộc đọc cùng giá trị cũ** trước khi cho phép ghi. Sau đó so sánh với phép `merge` đúng.

Lưu file `LostUpdateDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LostUpdateDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        counts.put("java", 0);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        try {
            List<Future<?>> jobs = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                jobs.add(pool.submit(() -> {
                    int old = counts.get("java");
                    bothRead.countDown();
                    allowWrite.await();
                    counts.put("java", old + 1);
                    return null;
                }));
            }

            if (!bothRead.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Không đủ hai lượt đọc");
            }
            allowWrite.countDown();
            for (Future<?> job : jobs) {
                job.get(5, TimeUnit.SECONDS);
            }
            System.out.println("get + put = " + counts.get("java"));

            counts.put("java", 0);
            jobs.clear();
            for (int i = 0; i < 2; i++) {
                jobs.add(pool.submit(() -> {
                    counts.merge("java", 1, Integer::sum);
                    return null;
                }));
            }
            for (Future<?> job : jobs) {
                job.get(5, TimeUnit.SECONDS);
            }
            System.out.println("merge = " + counts.get("java"));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
javac LostUpdateDemo.java
java LostUpdateDemo
```

Kết quả khi tác vụ hoàn tất bình thường:

```text
get + put = 1
merge = 2
```

Giải thích:

1. `bothRead` bảo đảm hai tác vụ đã đọc giá trị `0`. `allowWrite` chỉ mở sau cả hai lần đọc, nên hai `put` ghi cùng `1`: mất một lượt cập nhật **một cách tái lập**.
2. `merge("java", 1, Integer::sum)` trên `ConcurrentHashMap` cập nhật nguyên tử cho key `java`; hai phép tăng hoàn tất thì giá trị phải bằng `2`.
3. `Future.get` làm lỗi trong tác vụ nổi lên tại luồng kiểm thử và thiết lập thứ tự cần thiết trước khi kiểm tra giá trị cuối. Dùng giới hạn thời gian để test không treo vô hạn.
4. `shutdownNow` nằm trong `finally` nhằm giải phóng executor kể cả khi test thất bại. Khi ứng dụng thực cần chờ dừng êm, ưu tiên `shutdown` rồi `awaitTermination` phù hợp.

**Chú ý về hợp đồng:** phép `merge` ở trên bảo đảm cập nhật *một key*. Nó không biến việc đọc hai key rồi chuyển số dư thành một giao dịch nguyên tử. Nếu phải kiểm tra bất biến trải trên nhiều key, cần thiết kế khóa/giao dịch/trạng thái bất biến thống nhất cho cả thao tác.

### Khi kiểm thử một bộ đếm lớn

Nếu có `T` luồng, mỗi luồng gọi `merge` `N` lần cho cùng key, sau khi **mọi `Future` hoàn thành thành công**, bất biến cuối là `count == T * N`. Cần kiểm tra tràn số với kiểu `int`; dùng `long` hoặc `LongAdder` tùy bài toán. `LongAdder.sum()` không phải snapshot nguyên tử trong lúc vẫn có cập nhật; chỉ so chính xác sau khi các luồng ghi đã dừng. Không dùng `ConcurrentHashMap.size()` hay `isEmpty()` làm chứng cứ trạng thái tức thời chính xác khi map đang biến đổi đồng thời.

## 4. Kiểm thử snapshot: đối tượng được duyệt là phiên bản nào?

Snapshot là một bản nhìn ổn định trong giới hạn hợp đồng. Iterator của `CopyOnWriteArrayList` giữ tham chiếu tới mảng tại **thời điểm iterator được tạo**, nên thêm/xóa phần tử sau đó không đổi nội dung lần duyệt ấy. Iterator này không hỗ trợ `remove`, `add` hay `set`.

Lưu file `SnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicReference;

public class SnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> shared =
                new CopyOnWriteArrayList<>(List.of("A", "B"));

        Iterator<String> oldIterator = shared.iterator();
        shared.add("C");

        List<String> observed = new ArrayList<>();
        oldIterator.forEachRemaining(observed::add);

        System.out.println("Iterator cũ: " + observed);
        System.out.println("Danh sách mới: " + shared);

        AtomicReference<List<String>> published =
                new AtomicReference<>(List.of("A", "B"));
        List<String> before = published.get();

        published.updateAndGet(current -> {
            List<String> next = new ArrayList<>(current);
            next.add("C");
            return List.copyOf(next);
        });

        System.out.println("Snapshot cũ: " + before);
        System.out.println("Snapshot mới: " + published.get());
    }
}
```

```bash
javac SnapshotDemo.java
java SnapshotDemo
```

```text
Iterator cũ: [A, B]
Danh sách mới: [A, B, C]
Snapshot cũ: [A, B]
Snapshot mới: [A, B, C]
```

Hai cách giải quyết nhu cầu khác nhau:

- **`CopyOnWriteArrayList`:** mỗi lần sửa tạo phiên bản mảng mới. Iterator đang dùng thấy mảng cũ, thích hợp với tình huống đọc/duyệt nhiều, sửa ít. Chi phí ghi và cấp phát bộ nhớ tăng theo kích thước list.
- **`AtomicReference<List<T>>` với danh sách bất biến:** người đọc lấy một reference duy nhất và giữ nó cho cả tác vụ. Writer tạo danh sách mới rồi thay reference nguyên tử; `updateAndGet` có thể thử lại lambda khi tranh chấp, nên lambda phải không có tác dụng phụ. `List.copyOf` chỉ bất biến về cấu trúc danh sách, không tự biến từng phần tử mutable bên trong thành bất biến.

**Đừng đánh đồng snapshot với “copy bất kỳ”.** `new ArrayList<>(sharedArrayList)` hoặc `List.copyOf(sharedArrayList)` không đảm bảo ảnh chụp nhất quán nếu một `ArrayList` thông thường vẫn bị sửa đồng thời không đồng bộ. Nếu dùng `Collections.synchronizedList`, hãy sao chép **trong cùng khóa** mà mọi writer dùng:

```java
// Mảnh mã minh họa: shared được tạo và dùng nhất quán qua wrapper.
List<String> shared = java.util.Collections.synchronizedList(
        new java.util.ArrayList<>());

// Các luồng ghi dùng shared.add/remove, không đụng backing list riêng.
List<String> stable;
synchronized (shared) {
    stable = List.copyOf(shared);
}
// Duyệt stable ngoài khóa: cấu trúc danh sách không đổi.
```

Việc giữ khóa khi tạo snapshot có thể tạm chặn writer. Nếu duyệt trực tiếp `shared.iterator()`, phải giữ khóa trên `shared` **trong toàn bộ lần duyệt** theo hợp đồng của wrapper. Iterator trả về từ `synchronizedList` tự nó không được biến thành snapshot.

### Bộ test snapshot nên chứng minh

1. Tạo iterator/snapshot tại thời điểm đã định.
2. Thêm, xóa hoặc thay đổi cấu trúc bộ sưu tập **sau** thời điểm đó.
3. Duyệt iterator/snapshot cũ và so với phiên bản ban đầu.
4. Lấy iterator/snapshot mới và kiểm tra nó thấy trạng thái sau cập nhật.
5. Tách rõ “ổn định về danh sách phần tử” và “bất biến sâu”: nếu chính đối tượng phần tử có state mutable bị sửa, snapshot cấu trúc không tự bảo vệ state của đối tượng ấy.

Không nên chờ thread khác “chạy đủ lâu” để tạo thời điểm chụp; hãy dùng `CountDownLatch`, `Phaser` hoặc barrier để điều khiển chính xác thứ tự tạo iterator → ghi → duyệt khi kịch bản đòi hỏi tính tất định.

## 5. Kiểm thử iterator nhất quán yếu

`ConcurrentHashMap` có iterator **weakly consistent**: có thể quan sát vài cập nhật xảy ra trong khi duyệt, không buộc thấy tất cả, và không ném `ConcurrentModificationException` chỉ vì map được sửa đồng thời. Những entry nhìn thấy phản ánh trạng thái ở những thời điểm khác nhau. Vì vậy, test kiểu “iterator phải trả về đúng [1, 2, 3, 4] khi writer chạy” là sai hợp đồng.

Lưu file `WeakIteratorDemo.java`:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WeakIteratorDemo {
    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<Integer, String> data = new ConcurrentHashMap<>();
        for (int i = 0; i < 1000; i++) {
            data.put(i, "v" + i);
        }

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        try {
            Future<?> writer = pool.submit(() -> {
                start.await();
                for (int i = 1000; i < 2000; i++) {
                    data.put(i, "v" + i);
                }
                return null;
            });

            Future<Integer> reader = pool.submit(() -> {
                start.await();
                int observed = 0;
                for (Map.Entry<Integer, String> entry : data.entrySet()) {
                    String expected = "v" + entry.getKey();
                    if (!expected.equals(entry.getValue())) {
                        throw new AssertionError("Sai bất biến entry");
                    }
                    observed++;
                }
                return observed;
            });

            start.countDown();
            writer.get(5, TimeUnit.SECONDS);
            int observed = reader.get(5, TimeUnit.SECONDS);
            if (data.size() != 2000) {
                throw new AssertionError("Writer chưa ghi đủ");
            }

            System.out.println("Đã duyệt hợp lệ: " + observed);
            System.out.println("Số phần tử cuối: " + data.size());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac WeakIteratorDemo.java
java WeakIteratorDemo
```

Dòng thứ nhất **không có số lượng cố định**; tùy lịch chạy, reader có thể thấy số entry khác nhau. Dòng thứ hai, sau khi `writer.get` trả về thành công và vì không có writer khác, luôn là:

```text
Số phần tử cuối: 2000
```

Điều được kiểm tra là: mỗi entry **thực sự đã quan sát** phải có cặp key/value tương ứng; iterator không thất bại vì việc thêm phần tử; khi các writer đã kết thúc, kiểm tra được trạng thái cuối cùng. Không được lấy số lượng entry đọc trong lúc update làm “kích thước snapshot” hay bắt nó bằng `map.size()` đo cùng thời gian.

Những lưu ý quan trọng:

- Không suy ra rằng mọi thay đổi mới **đều** phải xuất hiện, hoặc tất cả thay đổi **đều** bị ẩn.
- Không dùng `ConcurrentModificationException` làm “đồng hồ phát hiện race”: iterator fail-fast của `ArrayList`/`HashMap` chỉ cố gắng phát hiện sửa đổi, không đảm bảo ném lỗi trong mọi trường hợp; dùng nó dưới data race có thể sai từ bản chất.
- “Không ném exception” là tiêu chí cần nhưng chưa đủ: vẫn phải kiểm tra bất biến dữ liệu, kết quả nghiệp vụ, tính kết thúc và việc không mất cập nhật.
- `ConcurrentHashMap` không cho key/value `null`. Không đưa yêu cầu cho phép null từ `HashMap` sang test của nó.
- Iterator của `ConcurrentHashMap` được thiết kế cho **một luồng sử dụng trên mỗi iterator**; các luồng riêng có thể tạo iterator riêng trên cùng map.

## 6. Thiết kế oracle: khẳng định điều được bảo đảm, không đoán lịch chạy

Một *test oracle* là quy tắc xác định kết quả đúng. Với chương trình đồng thời, nhiều lịch chạy đều hợp lệ; oracle phải mô tả **bất biến** hoặc **tập kết quả hợp lệ** chứ không gắn cứng một lịch tùy ý.

| Bối cảnh | Khẳng định hợp lệ | Khẳng định sai dễ gặp |
| --- | --- | --- |
| Hai luồng `merge` cùng key, đã `get()` mọi `Future` | Giá trị cuối tăng đúng hai | Hai lời gọi nhất thiết chạy theo thứ tự thread 1 rồi thread 2 |
| Iterator `CopyOnWriteArrayList` tạo trước khi thêm `C` | Iterator cũ giữ [A, B] | Iterator cũ thấy C vì list hiện tại có C |
| Iterator `ConcurrentHashMap` và writer thêm key | Mỗi entry đọc được thỏa bất biến; duyệt không lỗi do sửa cấu trúc | Số entry nhìn thấy phải bằng kích thước cuối hoặc một số chính xác bất kỳ |
| Snapshot cấu trúc chứa đối tượng mutable | Danh sách tham chiếu ổn định | Mọi trường bên trong từng object tự động đóng băng |
| `Collections.synchronizedList` | Mọi truy cập qua wrapper, duyệt/copy dưới cùng khóa | Chỉ gọi `iterator()` qua wrapper là đủ |
| `ConcurrentHashMap.size()` khi đang ghi | Chỉ số có thể phù hợp quan sát tạm thời; kiểm tra kết quả chính xác khi đã dừng writer | `size()` là ảnh chụp tuyến tính hóa của toàn bộ map trong lúc ghi |

Nếu yêu cầu nghiệp vụ cần phép đọc nhất quán cả map — ví dụ kiểm tra “tổng tiền của mọi tài khoản luôn bằng hằng số tại đúng một thời điểm” — iterator weakly consistent không cung cấp snapshot đó. Cần thiết kế giao thức đồng bộ hay phiên bản bất biến được publish nguyên tử, hoặc giao dịch ở tầng lưu trữ. Không “sửa” test bằng cách ép kết quả vượt quá hợp đồng API.

## 7. Quy trình lập test đáng tin cậy

1. **Viết rõ invariant và ranh giới nguyên tử** trước khi chạy. Ví dụ “sau khi tất cả 8 writer xong, tổng một key bằng 80.000”, hoặc “iterator snapshot tạo trước append không thấy append”.
2. **Chọn collection đúng hợp đồng.** `ArrayList`/`HashMap` cần đồng bộ ngoài khi đọc-ghi đồng thời; `ConcurrentHashMap` cho truy cập concurrent và iterator weakly consistent; `CopyOnWriteArrayList` cho snapshot iterator; wrapper `synchronizedList` cần khóa khi duyệt.
3. **Điều khiển đúng điểm cạnh tranh.** Dùng latch/barrier để đồng bộ khởi động hoặc tạo lịch interleaving xác định. `Thread.sleep` không là chứng cứ rằng luồng kia đã đến vị trí mong muốn.
4. **Thu tất cả kết quả và lỗi.** Dùng `Future.get(timeout, unit)`, xử lý `ExecutionException`, `InterruptedException`/timeout thích hợp. Chỉ kiểm tra trạng thái cuối sau khi đã xác nhận toàn bộ writer hoàn thành.
5. **Tách test tất định và stress test.** Test có latch làm tái lập một interleaving nguy hiểm; stress chạy nhiều lịch để mở rộng độ phủ nhưng không thể chứng minh vắng mặt race. Khi cần khảo sát interleaving ở mức JVM, xem công cụ `jcstress` của OpenJDK.
6. **Bảo đảm cleanup.** Đóng executor, giải phóng barrier nếu lỗi, tránh rò thread làm cả bộ test treo. Timeout là cơ chế phát hiện test không kết thúc, không phải bằng chứng độc lập cho kết quả đúng.
7. **Giữ kết quả kiểm tra độc lập với tốc độ máy.** Hạn chế đo thời gian để quyết định tính đúng, không suy luận từ thứ tự log `println` của các luồng.

### Mẫu phân loại lỗi

- **Lost update:** tổng cuối nhỏ hơn số thao tác nguyên tử dự kiến → kiểm tra xem code dùng chuỗi `get` rồi `put` hoặc `x++` không đồng bộ.
- **Stale read:** một luồng không quan sát cập nhật đúng khi contract có happens-before → kiểm tra publish/đồng bộ, sau đó mới nghi implementation.
- **Torn hoặc inconsistent snapshot:** báo cáo tổng hợp lẫn state của nhiều thời điểm → có thể dùng live traversal trong khi nghiệp vụ cần snapshot đồng bộ.
- **Flaky assertion:** lúc pass lúc fail vì ép một thứ tự iteration không được bảo đảm → sửa oracle theo hợp đồng.
- **Unexpected exception:** kiểm tra class collection, quyền sửa đồng thời, comparator/key/value, và việc có dùng wrapper bên ngoài khóa hay không.
- **Hang:** barrier thiếu party, đợi hai chiều, quên release/cleanup, deadlock do khóa hoặc lambda remapping làm việc nguy hiểm.

## 8. Bẫy quan trọng khi áp dụng vào code thật

**Atomic map method và side effect:** đối với `ConcurrentHashMap.compute`, `merge` hay `computeIfAbsent`, hàm được truyền phải ngắn, đơn giản, không cập nhật đệ quy vào cùng map, không khóa kéo dài và không dựa vào side effect bên ngoài để tạo một giao dịch lớn hơn. Nếu một invariant trải trên nhiều key thì giải pháp phải bảo vệ invariant ấy ở mức thiết kế.

**Tham chiếu value mutable:** một map concurrent chỉ quản lý sự an toàn của thao tác map theo hợp đồng; việc sửa trường của `MutableValue` đặt trong map cần cơ chế đồng bộ riêng. Snapshot map hoặc `List.copyOf` không tự tạo bản sao sâu của giá trị.

**Synchronized wrapper và backing object:** sau khi bọc `Collections.synchronizedList(backing)`, đừng tiếp tục sửa `backing` từ luồng khác. Mọi đường truy cập phải tuân thủ cùng giao thức khóa; tương tự khi copy hay iterate.

**Fail-fast không phải bảo đảm thread safety:** `ConcurrentModificationException` là chỉ báo lỗi sử dụng collection ở một số tình huống, không phải oracle đầy đủ hay cơ chế đồng bộ.

**Không nhầm consistency với isolation:** weakly consistent traversal hợp lệ cho dashboard, cache, quan sát gần đúng, nơi trạng thái có thể biến động; khi cần snapshot nhất quán cho kiểm toán, đối soát hoặc giao dịch, phải xây dựng ranh giới snapshot thực sự.

## 9. Bài tập tự kiểm chứng

1. Chỉnh `LostUpdateDemo` chạy 8 tác vụ, mỗi tác vụ tăng 10.000 lần bằng `merge`. Chờ đủ mọi `Future` rồi kiểm tra đúng 80.000. Thử thay bằng `get` + `put` để thấy thất bại **có thể** xảy ra trong stress; không giả định test sai luôn thất bại nếu không điều khiển interleaving.
2. Tạo iterator của `CopyOnWriteArrayList` trước một lần `remove`. Kiểm tra iterator cũ vẫn thấy phần tử cũ; iterator mới thấy phiên bản mới. Thử gọi `oldIterator.remove()` và xác nhận ném `UnsupportedOperationException`.
3. Cho một writer liên tục thêm phần tử vào `ConcurrentHashMap`, reader duyệt bằng iterator riêng; ghi số quan sát được để minh họa dao động, nhưng assertion chỉ kiểm tra cặp key/value hợp lệ và trạng thái cuối sau join.
4. Tạo một danh sách bất biến được publish qua `AtomicReference`. Cho nhiều reader nắm snapshot khác nhau và kiểm tra từng reader chỉ thấy phiên bản mình đã nhận; thảo luận chi phí sao chép.
5. Viết lại một test bị flaky vì dùng `Thread.sleep(20)` để chờ writer. Thay bằng latch/`Future.get` và ghi rõ happens-before nào cho phép kiểm tra.

## 10. Ghi nhớ và tài liệu chuẩn

- **Atomicity:** kiểm tra phép cập nhật và invariant ở đúng phạm vi API cam kết; một chuỗi thao tác riêng lẻ không tự nguyên tử.
- **Snapshot:** cố định phiên bản khi tạo iterator hoặc khi publish reference bất biến; kiểm tra thời điểm lấy snapshot.
- **Weak consistency:** chấp nhận nhiều kết quả duyệt hợp lệ, kiểm tra invariant của entry quan sát được; không đòi một snapshot mà API không bảo đảm.
- **Concurrency test tốt:** điều khiển lịch chạy ở các điểm quan trọng, truyền lỗi từ worker, có timeout/cleanup, và chỉ assert kết quả cuối sau đồng bộ hợp lệ.

Tài liệu Java SE 17:

- [`ConcurrentHashMap` — atomic methods và weakly consistent iterators](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [`CopyOnWriteArrayList` — snapshot iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)
- [`Collections` — synchronized wrappers và yêu cầu khóa khi duyệt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)
- [`Future` — memory consistency và chờ kết quả](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
