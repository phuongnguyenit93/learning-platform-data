# Weakly consistent iteration và snapshot semantics trong Java Concurrent Collections

## 1. Khi collection bị thay đổi trong lúc đang duyệt

Một collection không chỉ được dùng để lưu dữ liệu; rất nhiều xử lý đồng thời phải **duyệt** dữ liệu: gửi thông báo cho người đang kết nối, thu thập metric, quét cache, tìm task chờ xử lý, hoặc tạo báo cáo. Khi một thread duyệt, thread khác có thể `add`, `remove` hoặc `put`.

Ba câu hỏi cần phân biệt:

1. Iterator có **ném lỗi** khi collection bị thay đổi hay không?
2. Iterator có **thấy các thay đổi** xảy ra sau khi được tạo hay không?
3. Các phần tử iterator thấy có tạo thành **một trạng thái nhất quán tại cùng một thời điểm** hay không?

Không thể suy từ câu trả lời thứ nhất rằng câu trả lời thứ ba cũng là “có”. Một iterator không ném `ConcurrentModificationException` **không đồng nghĩa** nó cung cấp một snapshot nguyên tử.

Trong Java, các cơ chế cần hiểu bao gồm:

- **Fail-fast iterator**: nhiều collection thông thường, như `ArrayList` và `HashMap`, có iterator cố gắng phát hiện sửa đổi cấu trúc không phù hợp khi đang duyệt.
- **Weakly consistent iterator**: nhiều concurrent collection, như `ConcurrentHashMap`, `ConcurrentLinkedQueue` và `ConcurrentSkipListMap`, cho phép duyệt đồng thời với cập nhật, có thể phản ánh một phần thay đổi và không hứa snapshot tại một thời điểm.
- **Snapshot iterator**: `CopyOnWriteArrayList` và `CopyOnWriteArraySet` dùng một ảnh chụp cấu trúc tại **thời điểm iterator được tạo**, nên các cập nhật cấu trúc sau đó không xuất hiện trong lượt duyệt ấy.
- **Explicit snapshot**: chương trình chủ động tạo bản sao có bảo đảm phù hợp với bất biến của dữ liệu. Chỉ copy một concurrent collection **không tự động** làm bản sao thể hiện một thời điểm nguyên tử của toàn collection.

Bài tập trung vào **Java concurrency và Concurrent Collections nói chung**, không đi vào framework.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích chính xác fail-fast, weak consistency và snapshot semantics.
2. Biết vì sao `ConcurrentHashMap` duyệt được khi có update nhưng không bảo đảm nhìn mọi cập nhật.
3. Dùng `CopyOnWriteArrayList` khi khối lượng đọc/duyệt nhiều hơn cập nhật, hiểu chi phí copy-on-write và giới hạn mutable elements.
4. Phân biệt snapshot có cấu trúc ổn định với snapshot **nhất quán nhiều trường/nhiều khóa**.
5. Dùng khóa chung, immutable state hoặc protocol versioning khi báo cáo cần nhìn trạng thái tổng thể nhất quán.
6. Thiết kế test có output xác định thay vì giả định thứ tự scheduling hoặc thứ tự duyệt concurrent.
7. Chọn collection dựa trên workload, độ chính xác, performance và semantics của dữ liệu.

## 2. Bảng so sánh nhanh

| Cơ chế | Ví dụ Java | Sửa đổi đồng thời khi duyệt | Có thể thấy update mới? | Một snapshot cấu trúc cố định? |
| --- | --- | --- | --- | --- |
| Fail-fast | `ArrayList`, `HashMap` | Không được hỗ trợ tự do theo iterator thông thường; có thể ném `ConcurrentModificationException` | Không có contract duyệt đồng thời ổn định | Không |
| Weakly consistent | `ConcurrentHashMap` | Được thiết kế để duyệt cùng lúc với update | **Có thể**, không bảo đảm thấy tất cả | **Không** |
| Weakly consistent | `ConcurrentLinkedQueue` | Được hỗ trợ | Có thể | Không |
| Weakly consistent, có thứ tự khóa | `ConcurrentSkipListMap` | Được hỗ trợ | Có thể | Không |
| Snapshot iterator | `CopyOnWriteArrayList` | Update cấu trúc sau khi tạo iterator không làm thay đổi lượt duyệt | Không, đối với cấu trúc array đã chụp | **Có**, snapshot của array |
| Snapshot iterator | `CopyOnWriteArraySet` | Tương tự copy-on-write list | Không, đối với cấu trúc tập đã chụp | **Có**, snapshot cấu trúc |
| External synchronization | `Collections.synchronizedList` và lock chung | Phải tự giữ monitor khi duyệt | Không thay đổi trong lúc giữ lock nếu mọi writer tuân thủ | Có thể dựng snapshot dưới lock |
| Immutable copy | `List.copyOf` / `Map.copyOf` | Bản sao không cho cập nhật cấu trúc | Không thay đổi cấu trúc sau khi tạo | Có, **nếu nguồn được chụp nhất quán** |

Ở đây, “snapshot cấu trúc” không có nghĩa object phần tử bên trong bất biến. Ví dụ list đã copy chứa một `Box` mutable thì `Box.value` vẫn có thể thay đổi dù iterator vẫn chỉ trỏ tới cùng các `Box` ban đầu.

**Điểm quyết định:** chọn loại iterator theo câu hỏi nghiệp vụ cần trả lời, không đơn giản theo mong muốn “không ném exception”.

## 3. Fail-fast iterator: phát hiện lỗi, không phải giao thức đồng bộ

Nhiều collection không concurrent ghi nhận một bộ đếm thay đổi cấu trúc. Iterator có thể so sánh trạng thái mong đợi với trạng thái thực tế và ném `ConcurrentModificationException` khi phát hiện thay đổi không phù hợp.

Ví dụ rủi ro:

~~~java
// Minh họa không an toàn; không phải chương trình độc lập.
List<String> list = new ArrayList<>(List.of("A", "B"));
for (String item : list) {
    if (item.equals("A")) {
        list.add("C");  // Sửa cấu trúc list ngoài Iterator.remove().
    }
}
~~~

Với `ArrayList` thường gặp, điều này có thể gây `ConcurrentModificationException` tại thao tác iterator kế tiếp. Tuy nhiên **Javadoc nhấn mạnh fail-fast là best effort**: không thể bảo đảm mọi trường hợp race đều phát hiện được. Vì thế **đừng dùng exception đó như cơ chế correctness hoặc tín hiệu đồng bộ**.

### 3.1. “Không ném CME” không chứng minh an toàn

Nếu chạy code sai trên `ArrayList` nhiều lần mà không thấy `ConcurrentModificationException`, chương trình vẫn có thể có data race, quan sát dữ liệu không nhất quán hoặc gặp kết quả không xác định. Ngược lại, `ConcurrentHashMap` không ném CME khi duyệt đồng thời **vì nó có hợp đồng iterator khác**, chứ không phải vì biến mọi thao tác nhiều phần tử thành nguyên tử.

Một tập hợp các thao tác `get`/`put` trên map thread-safe cũng chưa đủ để bảo vệ invariant của nhiều key. “Thread-safe collection” không đồng nghĩa “thread-safe workflow”.

### 3.2. Cập nhật thông qua iterator

Với một số iterator của collection thông thường, `Iterator.remove()` là cách hợp lệ để xóa phần tử hiện tại. Nhưng quyền hỗ trợ `remove()` phụ thuộc implementation. Ví dụ snapshot iterator của `CopyOnWriteArrayList` **không hỗ trợ** `remove()`, `set()` hay `add()` và sẽ ném `UnsupportedOperationException`.

Không áp dụng một mẫu xóa iterator chung cho mọi collection; hãy xem contract của loại iterator thực sự đang dùng.

## 4. Weakly consistent iteration là gì?

Iterator weakly consistent cho phép tiến triển khi collection có update đồng thời mà không có cùng fail-fast behavior như `ArrayList`. Nó thường:

- Duyệt được cùng lúc với thread khác thêm, xóa hoặc thay giá trị.
- Không ném `ConcurrentModificationException` chỉ vì collection được thay đổi đồng thời.
- Có thể thấy một số trạng thái từ lúc iterator được tạo **và** một số thay đổi sau đó.
- Không hứa thấy toàn bộ thay đổi, hoặc rằng mọi phần tử được trả ra thuộc cùng một trạng thái tại một thời điểm.
- Không tự khóa cả collection để cung cấp point-in-time snapshot.

Từ **weakly** nói về bảo đảm quan sát khi duyệt, **không** đồng nghĩa bộ lưu trữ underlying “không thread-safe”. `ConcurrentHashMap.get/put/compute` có các hợp đồng thread-safety và atomicity riêng cho thao tác cụ thể. Chỉ iterator toàn map là không cho một giao dịch đọc nhiều key nhất quán tại một điểm thời gian.

### 4.1. Một lịch xen kẽ có thể khiến kết quả trộn thời điểm

~~~text
Thời điểm       Thread reader                      Thread writer
t0              Tạo iterator trên map
t1              Đọc key A và value cũ
t2                                                 Thay A, thêm C, xóa B
t3              Đọc một số entry khác
t4              Iterator hoàn thành
~~~

Kết quả của reader có thể chứa một phần value cũ và một phần value mới, có thể thấy C hoặc không. Không được diễn giải nó như “trạng thái map ở đúng t0” hoặc “trạng thái map ở đúng t4”.

Để audit/report yêu cầu một thời điểm cắt rõ ràng, cần snapshot protocol mạnh hơn. Để quan sát gần đúng danh sách kết nối hay metric, weak iteration có thể rất phù hợp.

## 5. ConcurrentHashMap: các thao tác atomic không biến iterator thành snapshot

`ConcurrentHashMap<K,V>` được thiết kế để nhiều thread cập nhật và đọc map đồng thời. `keySet()`, `values()`, `entrySet()` cung cấp các view có iterator **weakly consistent**. Iterator và spliterator không ném CME khi map thay đổi đồng thời.

### 5.1. Không có một khóa toàn map mà iterator giữ suốt thời gian duyệt

Một iterator có thể lần lượt quan sát nhiều bucket/entry ở những thời điểm khác nhau. Vì thế:

~~~java
// Minh họa trong method, không phải chương trình độc lập.
for (Map.Entry<String, Integer> e : concurrentMap.entrySet()) {
    audit(e.getKey(), e.getValue());
}
~~~

Đoạn này có thể phù hợp để **đọc gần đúng** hoặc làm công việc có thể chịu cập nhật đồng thời. Nó không phù hợp nếu audit bắt buộc chính xác 100% tại một timestamp chung, ví dụ tổng tài sản nhiều tài khoản phải bằng bất biến.

### 5.2. `size()`, `mappingCount()` và aggregate

Khi có update concurrent, các phép tổng hợp như `size()`, `mappingCount()`, `isEmpty()` hay các bulk reductions không nên được coi là snapshot giao dịch toàn map. `mappingCount()` trả `long` để có khả năng biểu diễn kích thước vượt giới hạn `int`, nhưng vẫn có thể chỉ là **ước lượng khi đang sửa đồng thời**.

Không viết workflow:

~~~java
// Sai nếu coi size và nội dung là một transaction.
int expected = map.size();
for (var e : map.entrySet()) {
    process(e);
}
assert processedExactly(expected);
~~~

Map có thể thay đổi giữa lời gọi `size()` và lần đọc từng entry. Số phần tử nhìn thấy cũng có thể thay đổi khi đang duyệt.

### 5.3. `compute`/`merge` chỉ giúp atomic ở đúng phạm vi

`ConcurrentHashMap.compute(key, ...)` hay `merge` có bảo đảm atomic cho cập nhật mapping của **key tương ứng** theo contract. Một chuỗi thay đổi `keyA` rồi `keyB` vẫn có thể bị reader chen vào giữa. Không suy luận tính nguyên tử tổng thể từ việc từng thao tác riêng là thread-safe.

### 5.4. Không có thứ tự iteration giống insertion order

Không dùng `ConcurrentHashMap` như `LinkedHashMap` để suy ra thứ tự insertion. Ngay cả khi iterator chạy không có writer, thứ tự duyệt không phải hợp đồng “theo thời gian put”; khi có writer, càng không dùng thứ tự đầu ra làm lịch sử giao dịch.

Nếu cần thứ tự key, cân nhắc `ConcurrentSkipListMap` với các semantics riêng; nhưng **sort order vẫn không đồng nghĩa point-in-time snapshot**.

## 6. Ví dụ 1 — weak iterator chấp nhận cập nhật (Java 17+)

Để tránh đoán “iterator có thấy phần tử vừa put hay không”, ví dụ chỉ in những điều có thể kiểm tra chắc chắn. Ta tạo iterator, đọc một phần tử, cập nhật map ở một thread khác, rồi hoàn tất lượt duyệt.

Tạo tệp `WeakIteratorDemo.java`:

~~~java
import java.util.Iterator;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class WeakIteratorDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<Integer, String> map =
            new ConcurrentHashMap<>();

        map.put(1, "one");
        map.put(2, "two");
        map.put(3, "three");

        Iterator<Map.Entry<Integer, String>> iterator =
            map.entrySet().iterator();

        if (iterator.hasNext()) {
            iterator.next();
        }

        Thread writer = new Thread(() -> {
            map.put(4, "four");
            map.remove(2);
        }, "map-writer");

        writer.start();
        writer.join();

        int visitedAfterUpdate = 0;
        while (iterator.hasNext()) {
            iterator.next();
            visitedAfterUpdate++;
        }

        System.out.println("iteration completed = true");
        System.out.println("map has key 4 = " + map.containsKey(4));
        System.out.println("map has key 2 = " + map.containsKey(2));

        // Không in visitedAfterUpdate thành một hằng số:
        // weak iterator có thể thấy một tập entry tùy thời điểm.
        if (visitedAfterUpdate < 0) {
            throw new AssertionError("Impossible count");
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac WeakIteratorDemo.java
java WeakIteratorDemo
~~~

Stdout:

~~~text
iteration completed = true
map has key 4 = true
map has key 2 = false
~~~

Ở đây writer hoàn tất trước khi main đọc hai điều kiện `containsKey`, nên trạng thái cuối của map rõ ràng. Nhưng **tập entry mà iterator đã thấy** không được cố định trong output: không nên khẳng định nó chắc chắn đã thấy key 4 hoặc không thấy key 2.

Chương trình không bắt `ConcurrentModificationException` vì không cần “dập lỗi”; chính iterator của `ConcurrentHashMap` được thiết kế cho mẫu duyệt concurrent. Lưu ý ví dụ sắp đặt thay đổi sau khi iterator được tạo và trước khi lượt duyệt kết thúc; nó không chứng minh một lịch thực thi duy nhất mà mọi JVM phải chọn.

### Khi nào weak iteration là lựa chọn tốt?

- Quét session/cache phục vụ **tác vụ best-effort**; một session vừa tham gia có thể được xử lý trong lượt sau.
- Thu thập metric xấp xỉ, dashboard không cần một thời điểm chốt sổ.
- Quét để dọn entry cũ với điều kiện xóa atomic phù hợp, ví dụ `remove(key, expectedValue)` khi cần tránh xóa nhầm entry đã được thay thế.
- Danh sách tài nguyên thay đổi thường xuyên, miễn tính đúng đắn của mỗi hành động không dựa vào việc lượt duyệt nhìn **đủ mọi entry**.

**Không phù hợp** nếu một lần duyệt phải duy nhất/đủ mọi giao dịch tính đến cutoff, hoặc kết quả là nguồn xác định chính thức cho đối soát.

## 7. ConcurrentLinkedQueue và ConcurrentSkipListMap

### 7.1. ConcurrentLinkedQueue

`ConcurrentLinkedQueue<E>` là queue concurrent không chặn, triển khai dựa trên các thao tác nguyên tử thích hợp. Iterator của nó **weakly consistent**: có thể cùng tồn tại với `offer`/`poll` của thread khác và không ném CME chỉ vì queue được thay đổi.

Nhưng một lượt duyệt queue không phải phép “lấy từng phần tử để xử lý đúng một lần”. Nếu muốn một worker **nhận quyền sở hữu** một công việc, nên dùng `poll()`/`remove()` hoặc `BlockingQueue.take()` theo mô hình queue, không chỉ for-each rồi giả định task đã được claim.

`size()` của `ConcurrentLinkedQueue` có thể phải duyệt phần tử và kết quả có thể không chính xác nếu queue bị thay đổi khi đếm. Không dùng `size()` của queue đó như reservation counter hay phương pháp backpressure chính xác.

### 7.2. ConcurrentSkipListMap

`ConcurrentSkipListMap` cung cấp map concurrent có **sorted key order** theo comparator/natural order. Iterator của nó cũng weakly consistent, không tạo snapshot nguyên tử của tất cả key/value.

Có key order không có nghĩa có **time order** của update. Khi tập key thay đổi trong lúc quét, tính đúng đắn vẫn phải được xác định theo contract của thao tác riêng. Muốn audit theo mốc thời gian, bạn cần transaction/snapshot/versioning, không chỉ một sorted concurrent map.

### 7.3. Weakly consistent không phải tính ngữ nghĩa giống nhau cho mọi class

Đừng áp dụng “có thể thấy một số cập nhật” thành lời cam kết cụ thể rằng iterator nào cũng phải thấy ít nhất một cập nhật sau khi tạo. Mỗi collection có chi tiết traversal, ordering, removal hỗ trợ và race contract riêng.

Đọc Javadoc chính xác của collection cụ thể. Chúng có thể cùng được xếp vào nhóm “weakly consistent” nhưng khác nhau về thứ tự key, hỗ trợ null, chi phí đếm hoặc chức năng remove.

## 8. Snapshot iterator của CopyOnWriteArrayList

`CopyOnWriteArrayList<E>` giữ các phần tử trong một array, cập nhật cấu trúc bằng cách **tạo/công bố array mới**. Khi tạo iterator, nó gắn với **array tại thời điểm iterator được tạo**.

Nếu thread khác thêm, xóa hoặc thay một vị trí trong list sau đó, iterator cũ vẫn đi trên array mà nó đã lấy lúc đầu. Nó không ném CME do thay đổi cấu trúc đồng thời, nhưng **khác weakly consistent iterator**: nó không quan sát các cập nhật cấu trúc về sau trong lượt duyệt đó.

### 8.1. Ví dụ 2 — snapshot của iterator ổn định (Java 17+)

Tạo tệp `CopyOnWriteSnapshotDemo.java`:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> list =
            new CopyOnWriteArrayList<>(List.of("A", "B"));

        Iterator<String> before = list.iterator();

        list.add("C");
        list.set(0, "X");

        System.out.print("iterator snapshot = [");
        boolean first = true;
        while (before.hasNext()) {
            if (!first) {
                System.out.print(", ");
            }
            System.out.print(before.next());
            first = false;
        }
        System.out.println("]");
        System.out.println("current list = " + list);

        try {
            list.iterator().remove();
        } catch (UnsupportedOperationException expected) {
            System.out.println("iterator remove unsupported");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CopyOnWriteSnapshotDemo.java
java CopyOnWriteSnapshotDemo
~~~

Stdout:

~~~text
iterator snapshot = [A, B]
current list = [X, B, C]
iterator remove unsupported
~~~

**Tại sao?**

1. Iterator `before` chụp tham chiếu tới array chứa A, B tại thời điểm được tạo.
2. `add("C")` và `set(0, "X")` tạo/công bố cấu trúc list mới; iterator `before` vẫn dùng array cũ.
3. Lời gọi `iterator().remove()` không được hỗ trợ, vì iterator snapshot không phải một view chỉnh sửa cấu trúc hiện tại.
4. Không có thread phụ nên stdout xác định. Khi có nhiều thread, thuộc tính snapshot của iterator vẫn áp dụng, nhưng thời điểm tạo iterator so với update do scheduler quyết định.

**Lưu ý:** `set(0, ...)` trong `CopyOnWriteArrayList` vẫn là một thao tác cập nhật list theo cơ chế của implementation; snapshot của iterator cũ không tự thay đổi.

### 8.2. Vì sao CopyOnWriteArrayList thích hợp khi nhiều đọc, ít ghi?

- Đọc/duyệt có thể chạy trên array snapshot mà không phải giữ lock của writer trong suốt lượt duyệt.
- Lượt duyệt phản ánh một cấu trúc ổn định, dễ suy luận cho danh sách listener/configuration bất biến về mặt membership.
- Thêm/xóa/sửa cấu trúc thường đòi **copy array**, làm tăng allocations và chi phí theo kích thước list.
- Nhiều cập nhật trong lúc list lớn tạo write amplification, áp lực GC và tốn bộ nhớ tạm cho những iterator cũ còn giữ array cũ.
- Không phù hợp khi mutation cực nhiều hoặc dữ liệu quá lớn mà phải copy liên tục.
- Iterator snapshot không nhất thiết phản ánh listener vừa thêm ngay tức thì; thiết kế cần chấp nhận độ trễ nhìn thấy ở các lượt duyệt tiếp theo.

### 8.3. Snapshot iterator không cho deep immutability

Một array snapshot có thể giữ các **tham chiếu tới object mutable**. Những object được trỏ tới có thể tiếp tục bị sửa thông qua tham chiếu khác. Vì vậy snapshot ổn định về **membership và vị trí reference**, không tự đóng băng trạng thái bên trong từng phần tử.

Đây là khác biệt quan trọng khi một list chứa `Account` hoặc `Session` mutable. Lượt duyệt có thể thấy cùng tập account, nhưng số dư/thuộc tính bên trong mỗi account có thể thay đổi giữa các lần đọc.

## 9. Ví dụ 3 — immutable structural copy vẫn shallow (Java 17+)

Tạo tệp `ShallowSnapshotDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ShallowSnapshotDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Box box = new Box(1);
        List<Box> original = new ArrayList<>();
        original.add(box);

        List<Box> snapshot = List.copyOf(original);

        original.add(new Box(2));
        box.value = 9;

        System.out.println(
            "snapshot size = " + snapshot.size()
        );
        System.out.println(
            "snapshot first value = " + snapshot.get(0).value
        );
        System.out.println(
            "original size = " + original.size()
        );
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ShallowSnapshotDemo.java
java ShallowSnapshotDemo
~~~

Stdout:

~~~text
snapshot size = 1
snapshot first value = 9
original size = 2
~~~

`List.copyOf(original)` tạo một list unmodifiable có **cấu trúc độc lập** với những thay đổi add/remove sau này của `original`. Nhưng cả hai list vẫn tham chiếu cùng `Box` ban đầu; khi `box.value` đổi từ 1 sang 9, snapshot đọc 9.

Để có **deep snapshot** khi cần, chuyển phần tử sang một value type bất biến (record chứa các field primitive/immutable) hoặc sao chép sâu theo đúng ownership. Cần tránh chỉ copy lớp ngoài và tuyên bố toàn bộ object graph đã bất biến.

### 9.1. `List.copyOf` và null

`List.copyOf` không chấp nhận phần tử `null`. Nếu nguồn có null, nó ném `NullPointerException`. Không thay `new ArrayList<>(source)` bằng `List.copyOf(source)` trong một hệ thống cho phép null mà không kiểm tra contract.

### 9.2. `Map.copyOf` / `Set.copyOf`

`Map.copyOf` và `Set.copyOf` cũng tạo collection unmodifiable, có yêu cầu riêng về null. Nhưng **chỉ vì copy đã xong và kết quả không sửa được không có nghĩa dữ liệu nguồn được đọc trong một transaction nguyên tử** nếu writer vẫn thay đổi nguồn trong lúc copy.

## 10. Sự khác nhau giữa snapshot copy và một snapshot nhất quán tại một thời điểm

Có ít nhất ba mức độ người ta cùng gọi là “snapshot”:

1. **Snapshot về membership/reference**: iterator duyệt tập reference ổn định, như `CopyOnWriteArrayList.iterator()`.
2. **Snapshot bản sao cấu trúc**: có một `List`/`Map` mới không thay đổi khi nguồn add/remove sau này, nếu quá trình copy đã thành công.
3. **Snapshot nhất quán về bất biến**: tất cả field/entry liên quan cùng mô tả một trạng thái nghiệp vụ hợp lệ tại **một thời điểm logic**; không trộn phần cũ và phần mới.

Mức 1 và mức 2 **không tự động suy ra mức 3**.

### 10.1. Vì sao `new HashMap<>(concurrentMap)` có thể chưa đủ?

`ConcurrentHashMap` cho phép các thao tác lấy từng entry khi writer còn hoạt động. Constructor copy có thể đi qua nguồn bằng traversal mà không giữ giao dịch đọc toàn map. Bản sao kết quả có cấu trúc độc lập, nhưng có thể chứa một tập entry được quan sát ở nhiều thời điểm khác nhau.

Một snapshot **bất biến sau khi tạo** vẫn có thể đã **không nhất quán tại thời điểm tạo**. Hai thuộc tính này khác nhau.

### 10.2. CopyOnWriteArrayList có thể snapshot cấu trúc mà vẫn có dữ liệu mutable

Nếu list lưu các record bất biến chứa toàn bộ dữ liệu cần báo cáo, snapshot iterator rất mạnh về membership. Nhưng nếu list lưu mutable object tham chiếu ngoài, bản thân những object đó có thể đổi. Một ảnh chụp các con trỏ không đồng nghĩa ảnh chụp toàn bộ giá trị sâu.

## 11. Ví dụ 4 — đọc hai key ConcurrentHashMap tạo kết quả không có ở bất kỳ thời điểm nào (Java 17+)

Ví dụ này **ép một interleaving có kiểm soát** bằng latch để chứng minh sự khác biệt giữa atomic operation theo key và atomic snapshot nhiều key. Không phụ thuộc timing hay scheduler may rủi.

Ban đầu A=60, B=40, tổng =100. Writer đổi A thành 40 rồi đổi B thành 60. Reader cố tình đọc A **trước** hai update và đọc B **sau** hai update:

~~~text
Ban đầu       A = 60, B = 40, tổng = 100
Reader        đọc A = 60
Writer        ghi A = 40     -> tổng thực tế tạm thời = 80
Writer        ghi B = 60     -> tổng thực tế = 100
Reader        đọc B = 60
Reader        ghép A+B = 120 (không phải trạng thái map tại bất kỳ mốc trên)
~~~

Tạo tệp `NonAtomicSnapshotDemo.java`:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;

public class NonAtomicSnapshotDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentHashMap<String, Integer> map =
            new ConcurrentHashMap<>();
        map.put("A", 60);
        map.put("B", 40);

        CountDownLatch firstRead = new CountDownLatch(1);
        CountDownLatch writerDone = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            try {
                firstRead.await();
                map.put("A", 40);
                map.put("B", 60);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                writerDone.countDown();
            }
        }, "balance-writer");

        writer.start();

        int oldA = map.get("A");
        firstRead.countDown();
        writerDone.await();
        writer.join();

        int newB = map.get("B");

        System.out.println("mixed total = " + (oldA + newB));
        System.out.println(
            "final total = " + (map.get("A") + map.get("B"))
        );
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac NonAtomicSnapshotDemo.java
java NonAtomicSnapshotDemo
~~~

Stdout khi không có interrupt ngoại lai:

~~~text
mixed total = 120
final total = 100
~~~

Kết quả không có nghĩa `ConcurrentHashMap` hỏng thread-safety. Mọi `get`/`put` riêng lẻ tuân theo contract, nhưng **một chuỗi nhiều lời gọi get không phải một transaction**. Nếu thay hai `get` bằng quá trình copy map trong lúc có writer, không có bảo đảm snapshot toàn map sẽ là trạng thái nguyên tử nhất quán.

Đây là bài học về **rủi ro của aggregate read**. Dữ liệu nghiệp vụ yêu cầu tổng luôn bằng 100 còn cần **atomic update của cặp số dư** ở phía writer; ở ví dụ writer thực hiện hai `put` riêng nên trong khoảng giữa cũng có một trạng thái tổng tạm thời 80. Cả read protocol lẫn write protocol đều cần thiết kế nếu phải giữ invariant xuyên nhiều key.

## 12. Tạo snapshot nhất quán bằng cùng một khóa

Khi mọi writer và reader tuân theo một **khóa chung**, một thao tác tạo copy có thể chạy trong cùng critical section mà không bị writer can thiệp. Đó là khác biệt so với việc chỉ gọi `List.copyOf` không khóa trên nguồn đang thay đổi.

### 12.1. Synchronized collection vẫn cần khóa khi duyệt

`Collections.synchronizedList(...)` biến các method riêng lẻ thành synchronized theo wrapper. Nhưng khi thực hiện phép duyệt nhiều bước, **caller phải đồng bộ hóa thủ công trên wrapper đó**:

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
List<String> shared =
    Collections.synchronizedList(new ArrayList<>());

List<String> snapshot;
synchronized (shared) {
    snapshot = List.copyOf(shared);
}

// Dùng snapshot ngoài khóa.
for (String item : snapshot) {
    use(item);
}
~~~

Mã cần import `java.util.List`, `java.util.Collections` và `java.util.ArrayList`. Điều kiện then chốt là **mọi writer đi qua cùng wrapper**, không giữ và sửa underlying `ArrayList` từ bên ngoài. Nếu reference tới backing list bị lộ và có writer dùng khóa khác hoặc không khóa, bảo đảm nhất quán vẫn bị phá.

`Collections.unmodifiableList(shared)` thì khác: nó chỉ chặn chỉnh sửa **qua reference của view đó** và vẫn phản ánh update từ `shared`. Nó không tạo snapshot. `List.copyOf` tạo bản sao cấu trúc độc lập khi nguồn được đọc an toàn.

### 12.2. Ví dụ 5 — copy dưới monitor và giữ snapshot ổn định (Java 17+)

Tạo tệp `LockedSnapshotDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class LockedSnapshotDemo {
    public static void main(String[] args) {
        List<Integer> shared =
            Collections.synchronizedList(
                new ArrayList<>(List.of(1, 2))
            );

        List<Integer> snapshot;
        synchronized (shared) {
            snapshot = List.copyOf(shared);
        }

        shared.add(3);

        System.out.println("snapshot = " + snapshot);
        System.out.println("current = " + shared);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac LockedSnapshotDemo.java
java LockedSnapshotDemo
~~~

Stdout:

~~~text
snapshot = [1, 2]
current = [1, 2, 3]
~~~

Vì lấy `snapshot` trong `synchronized (shared)`, mọi update đồng thời thực hiện qua wrapper phải đợi lock nhả. Sau đó `shared.add(3)` thay đổi nguồn, nhưng cấu trúc của snapshot vẫn giữ [1, 2]. Ví dụ dùng số nguyên immutable, nên không có vấn đề phần tử mutable bị đổi sau khi snapshot tạo.

**Hiệu năng:** Copy chiếm thời gian và bộ nhớ tỉ lệ số phần tử; trong lúc copy, writer phải chờ. Nếu cần snapshot rất thường xuyên trên list lớn, mô hình này có thể gây contention; chọn giải pháp khác tùy SLA.

### 12.3. Có thể dùng ReadWriteLock không?

Có. Một `ReadWriteLock` cho phép nhiều reader đồng thời giữ read lock và ngăn writer giữ write lock khi reader đang copy. Nhưng **mọi thay đổi** cần dùng đúng write lock, mọi snapshot reader cần giữ read lock trong suốt lần đọc toàn trạng thái. Không được lock chỉ quanh từng `get` riêng lẻ rồi unlock giữa các phần của snapshot.

Cần chú ý writer starvation, fairness, lock ordering và chi phí giữ lock quá lâu. Nếu dữ liệu là immutable snapshot, đôi khi một `AtomicReference` đơn giản hơn.

## 13. Snapshot nhất quán bằng immutable state + AtomicReference

Một mô hình khác là tạo một **object bất biến chứa toàn bộ trạng thái cần nhất quán**, sau đó thay **một reference duy nhất** một cách nguyên tử. Reader chỉ lấy reference một lần, nên luôn có một state đầy đủ nhất quán.

Ví dụ hai số dư luôn có tổng 100:

~~~java
// Hình dung cấu trúc Java record:
record State(int a, int b) {}
AtomicReference<State> current =
    new AtomicReference<>(new State(60, 40));
~~~

Writer tính state mới rồi dùng `compareAndSet` hoặc `updateAndGet` để thay cả cặp. Reader lấy `current.get()` một lần; các field trong record là final primitive và không thay đổi sau khi tạo.

### 13.1. Ví dụ 6 — coherent immutable snapshot (Java 17+)

Tạo tệp `AtomicStateSnapshotDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicStateSnapshotDemo {
    record State(int left, int right) {
        State {
            if (left < 0 || right < 0 || left + right != 100) {
                throw new IllegalArgumentException("Invalid state");
            }
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        AtomicReference<State> current =
            new AtomicReference<>(new State(60, 40));

        Thread first = new Thread(() ->
            current.updateAndGet(s ->
                new State(s.left() - 10, s.right() + 10)
            )
        );

        Thread second = new Thread(() ->
            current.updateAndGet(s ->
                new State(s.left() - 20, s.right() + 20)
            )
        );

        first.start();
        second.start();
        first.join();
        second.join();

        State snapshot = current.get();

        System.out.println("left = " + snapshot.left());
        System.out.println("right = " + snapshot.right());
        System.out.println(
            "snapshot total = "
                + (snapshot.left() + snapshot.right())
        );
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AtomicStateSnapshotDemo.java
java AtomicStateSnapshotDemo
~~~

Stdout:

~~~text
left = 30
right = 70
snapshot total = 100
~~~

Dù hai thread cập nhật theo thứ tự nào, mỗi hàm giảm left và tăng right cùng amount (10 hoặc 20). `AtomicReference.updateAndGet` dùng cơ chế cập nhật atomic và có thể **gọi lại hàm biến đổi** khi cạnh tranh; hàm lambda ở ví dụ thuần túy, không có side effect ngoài việc dựng `State` mới. Khi hai cập nhật hoàn tất, left = 60 - 10 - 20 = 30, right = 40 + 10 + 20 = 70.

Mỗi record `State` tạo ra có invariant tổng 100; reader giữ **một reference bất biến** nên không thể trộn left của state cũ với right của state mới như ví dụ map.

**Cảnh báo:** `record` chỉ làm các field của record là final; nếu field của record là reference tới `List` hoặc một object mutable, record **không tự deep-immutable**. Cần copy phòng vệ cho các field mutable.

### 13.2. Tại sao AtomicReference tốt cho snapshot ít write?

Khi write tạo một object immutable mới rồi thay reference, reader có thể đọc nhanh mà không cần giữ khóa khi duyệt state đã lấy. Nhưng mỗi update phải cấp phát state mới, tăng áp lực GC. CAS có thể retry và hàm cập nhật có thể chạy nhiều lần, vì thế **không đặt side effect** như gửi mạng/trừ tiền ở trong lambda `updateAndGet`.

Nếu state rất lớn hoặc write cực thường xuyên, chi phí copy sẽ lớn. Cần đo và cân nhắc partitioning, lock hoặc thiết kế ownership phù hợp.

## 14. Snapshot với versioning và retry: dùng khi nào?

Một giao thức nâng cao là đọc **version**, đọc dữ liệu, rồi đọc version lần nữa; nếu version thay đổi thì retry. Ví dụ ý tưởng:

~~~text
reader:
  v1 = version
  data = readAll()
  v2 = version
  if v1 != v2: retry
~~~

Tuy nhiên **đoạn này chưa đủ để trở thành một protocol đúng**:

- Nếu writer có thể bắt đầu update mà version chưa thay đổi, reader có thể quan sát state dở nhưng hai version bằng nhau.
- Cần quy định version **đánh dấu cả lúc bắt đầu và kết thúc write**, thường phân biệt trạng thái “đang ghi” với “ổn định”.
- Cần memory-ordering phù hợp để ngăn reorder/hide update.
- Mọi writer phải tuân thủ protocol; nếu có writer khác sửa dữ liệu mà không đổi version, snapshot có thể sai.
- Reader retry vô hạn dưới contention gây starvation; cần deadline/backoff/fallback lock.
- Nếu dữ liệu gồm field có data race, một kiểu seqlock tự viết trong Java có thể sai JMM dù thuật toán trông hợp lý.

Vì vậy, với dữ liệu nghiệp vụ quan trọng, **ưu tiên primitive đã có contract rõ**: cùng khóa cho toàn bộ snapshot hoặc immutable object được publish bằng `AtomicReference`. Chỉ tự làm versioned snapshot khi đã phân tích memory model và test kỹ.

## 15. Iterator weak và snapshot ảnh hưởng performance ra sao?

### 15.1. Chi phí duyệt của ConcurrentHashMap

Weak iteration cho phép không block writer trên toàn map trong lúc duyệt. Nó hữu ích khi writer cập nhật liên tục và reader có thể chấp nhận kết quả không phải point-in-time.

Nhưng nếu reader liên tục quét toàn bộ map lớn để đếm/sort, công việc vẫn tốn CPU và cấp phát ngoài. Nếu cần metric tần suất cao, có thể dùng accumulator/counter riêng với semantics phù hợp; không nên quét toàn map chỉ vì concurrent iterator “không khóa”.

### 15.2. Chi phí của CopyOnWriteArrayList

Với list có N phần tử, thêm/xóa/sửa cấu trúc thường copy array, chi phí thường tăng theo N. Iterator snapshot rẻ khi tạo và duyệt mà không cần khóa writer lâu, nhưng array cũ có thể bị giữ trong bộ nhớ bởi iterator sống lâu.

Mẫu phù hợp: tập **listener/subscriber** ít thay đổi nhưng được duyệt rất thường xuyên, mỗi listener là reference được quản lý hợp lý.

Mẫu không phù hợp: queue dữ liệu thay đổi hàng nghìn lần mỗi giây, list rất lớn, hoặc cập nhật cấu trúc liên tục trong lúc duyệt.

### 15.3. Copy snapshot dưới lock

Một snapshot copy dưới lock thường có chi phí O(N) cho một list N phần tử. Nếu phải tạo snapshot liên tục, writer có thể bị khóa trong lúc copy. Khi cần báo cáo tức thời hiếm hoi và tính nhất quán là bắt buộc, đây vẫn là giải pháp rất rõ ràng và dễ chứng minh.

### 15.4. Snapshot immutable bằng CAS

Reader có thể rất rẻ (đọc một reference rồi làm việc trên state bất biến). Writer chịu chi phí dựng state mới, CAS và retry dưới contention. Nếu đọc rất nhiều và ghi ít/không nhiều, lựa chọn này đáng cân nhắc.

**Không có “collection nhanh nhất” cho mọi bài toán.** Phải đo throughput, latency, allocation/GC, contention, dữ liệu dài hạn, thời gian giữ iterator và yêu cầu nhất quán.

## 16. Một số khái niệm dễ nhầm

### 16.1. Linearizability của một thao tác không biến nhiều thao tác thành transaction

Một `ConcurrentHashMap.put(key, value)` có thể có điểm hiệu lực nguyên tử của **một mapping**. Nhưng đọc A rồi B là **hai thao tác**; writer có thể chen giữa. Không có bảo đảm linearizability của một snapshot nhiều key nếu protocol không cung cấp.

### 16.2. Weakly consistent không đồng nghĩa eventually consistent theo nghĩa hệ phân tán

Weakly consistent iterator nói về **traversal concurrent trong cùng JVM**, không phải cam kết về replication, lag, eventual convergence hoặc phân tán đa máy. Nó không tự bảo đảm “nếu chờ đủ lâu, iterator hiện tại sẽ thấy mọi update”. Một iterator đơn có thể kết thúc trước khi update đến.

### 16.3. Snapshot iterator không đồng nghĩa snapshot toàn object graph

`CopyOnWriteArrayList` chụp array reference; các phần tử mutable bên trong vẫn có thể thay đổi. Muốn deep snapshot cần dữ liệu immutable/defensive copy sâu thích hợp.

### 16.4. Unmodifiable view khác independent copy

~~~java
// Minh họa, không phải chương trình độc lập.
List<Integer> source = new ArrayList<>(List.of(1, 2));
List<Integer> view = Collections.unmodifiableList(source);
List<Integer> copy = List.copyOf(source);

source.add(3);

// view thấy [1, 2, 3]; copy vẫn [1, 2].
~~~

`Collections.unmodifiableList` là view không cho chỉnh sửa **qua view**; nó vẫn sống cùng backing list. `List.copyOf` là copy unmodifiable có cấu trúc độc lập. Trên nguồn đang bị sửa concurrent, **cả việc duyệt view và việc copy** vẫn cần giao thức đồng bộ phù hợp.

### 16.5. Immutable snapshot có thể “cũ” nhưng vẫn đúng

Một snapshot được tạo ở t0 và dùng tới t2 có thể đã **stale** so với trạng thái hiện tại. Điều đó không có nghĩa nó không coherent: nó có thể đại diện chính xác cho **một thời điểm hợp lệ**. Ngược lại, một lượt đọc gần đây từ nhiều key có thể “fresh hơn” từng phần nhưng tạo một tổ hợp **chưa từng tồn tại**.

Hai yêu cầu độc lập:

- **Freshness:** dữ liệu mới đến mức nào?
- **Consistency:** dữ liệu có cùng thuộc một trạng thái hợp lệ tại một thời điểm logic không?

Ứng dụng phải quyết định cần cả hai hay chỉ một trong hai, cùng deadline và dung sai phù hợp.

## 17. Kiểm thử concurrent iteration đúng cách

### 17.1. Đừng hardcode thứ tự key không được API bảo đảm

Test sau không hợp lệ nếu map đang bị cập nhật đồng thời:

~~~java
// SAI về kỳ vọng; chỉ minh họa.
assertEquals(List.of("A", "B", "C"),
             new ArrayList<>(concurrentMap.keySet()));
~~~

Kết quả weak iterator có thể thiếu/thấy update mới tùy thời điểm; thứ tự key của `ConcurrentHashMap` cũng không phải insertion order. Test nên xác nhận những **invariant được contract bảo đảm**, không áp một thứ tự ngẫu nhiên.

### 17.2. Dùng CountDownLatch để điều phối các thời điểm quan trọng

Muốn chứng minh có thể đọc dữ liệu trộn thời điểm, ví dụ `NonAtomicSnapshotDemo` dùng latch để ép reader đọc A cũ trước khi writer cập nhật, rồi đọc B mới sau đó. Nhờ vậy output kiểm chứng được mà không trông chờ race ngẫu nhiên.

Muốn kiểm thử snapshot iterator, tạo iterator trước khi update và duyệt sau update; `CopyOnWriteSnapshotDemo` hoàn toàn xác định vì không cần scheduler.

### 17.3. Phân loại test

| Mục tiêu | Phép kiểm tra |
| --- | --- |
| Weak iterator không fail-fast khi update | Chạy traversal cùng update; không cố định tập phần tử đã thấy |
| Correctness mỗi map operation | Test contract `put/get/compute/remove(key,value)` |
| Snapshot iterator cố định cấu trúc | Tạo iterator, update list, xác minh iterator còn nội dung cũ |
| Snapshot element immutability | Thay đổi mutable element qua alias; xác nhận cần deep copy |
| Coherent snapshot đa trường | Test invariant dưới concurrent writer |
| Cancellation khi quét | Thêm deadline/interrupt ở workflow thực tế |
| Performance | Đo read/write mix, copy allocation, GC, duration |
| Không bỏ sót xử lý task | Dùng queue ownership/poll/ack, không chỉ weakly iterate |

Một bài test chạy thành công không chứng minh mọi interleaving an toàn; cần lập luận từ API và Java Memory Model. Với workload mà việc bỏ sót một phần tử có hậu quả, đừng dựa vào iterator weak để làm cơ chế phân phối công việc.

## 18. Checklist lựa chọn

| Yêu cầu thực tế | Cách tiếp cận phù hợp |
| --- | --- |
| Map nhiều writer/reader, lượt quét gần đúng là đủ | `ConcurrentHashMap` weak iteration |
| Queue nhiều producer/consumer, mỗi item cần một owner xử lý | `BlockingQueue.take` hoặc `ConcurrentLinkedQueue.poll` |
| Duyệt danh sách listener rất thường, thay đổi danh sách hiếm | `CopyOnWriteArrayList` |
| Duyệt với key được sắp thứ tự nhưng update concurrent | `ConcurrentSkipListMap`, chấp nhận weak consistency |
| Snapshot của list phải độc lập với nguồn | `List.copyOf` sau khi đọc nguồn an toàn |
| Cần snapshot nhiều field luôn giữ invariant | Lock chung hoặc `AtomicReference<ImmutableState>` |
| Iterator không muốn thấy update sau khi tạo | Snapshot iterator, nếu semantics shallow phù hợp |
| Cần trạng thái cực mới và nhất quán tại deadline | Giao thức transaction/snapshot riêng có điểm hiệu lực rõ |
| Nguồn dữ liệu mutable và copy không có khóa | **Không** mặc định coi copy là point-in-time |
| Phải process đủ, đúng một lần mỗi task | Ownership/ack protocol, không dựa vào traversal |

### Câu hỏi tự kiểm tra

**1.** Duyệt `ConcurrentHashMap.entrySet()` trong lúc writer thêm key mà không ném `ConcurrentModificationException`. Có thể kết luận iterator đã thấy tất cả key mới không?

Không. Iterator weakly consistent có thể quan sát một số cập nhật nhưng không hứa thấy toàn bộ; kết quả cũng không phải một snapshot nguyên tử.

**2.** `CopyOnWriteArrayList.iterator()` được tạo trước khi `add("C")`. Iterator đó có thấy C không?

Không. Snapshot iterator dùng array tại thời điểm tạo iterator, nên update cấu trúc sau đó không được phản ánh trong lượt duyệt ấy.

**3.** Có thể gọi `iterator.remove()` trên snapshot iterator của `CopyOnWriteArrayList` không?

Không. Nó ném `UnsupportedOperationException`; iterator không phải một cursor để sửa array hiện tại.

**4.** `List.copyOf` có đóng băng mọi object mutable trong phần tử không?

Không. Nó copy cấu trúc và giữ reference; muốn giữ nguyên dữ liệu sâu cần immutable element hoặc deep copy đúng nghĩa.

**5.** Hai thao tác `ConcurrentHashMap.get("A")` và `get("B")` đều thread-safe. Có đảm bảo cặp kết quả là snapshot cùng thời điểm không?

Không. Writer có thể thay đổi state giữa hai lần get; ví dụ trong bài tạo tổng 120 dù các mốc thực tế là 100, 80, 100.

**6.** Vì sao `Collections.unmodifiableList` không phải snapshot?

Vì đó là view trên backing list, vẫn phản ánh update qua reference khác. Nó chỉ cấm mutation thông qua view, không tạo bản sao độc lập.

**7.** `ConcurrentSkipListMap` có sorted key order. Có vì thế mà snapshot nhiều key nguyên tử không?

Không. Sorted traversal và point-in-time consistency là hai tính chất khác nhau.

**8.** Nếu cần snapshot nhất quán của hai biến thay đổi cùng nhau, có những cách nào?

Dùng cùng lock bao trùm **cả cập nhật lẫn đọc snapshot**, hoặc thay một immutable object chứa cả hai biến bằng một `AtomicReference`. Mọi đường writer/reader phải tuân thủ giao thức.

**9.** Một immutable snapshot có thể cũ không?

Có. Tính nhất quán nói snapshot có đại diện cho một state hợp lệ hay không; độ mới nói nó gần hiện tại đến mức nào. Snapshot nhất quán có thể stale.

**10.** Có nên dùng weak iterator để phân phát mỗi task đúng một lần?

Không chỉ dựa vào iteration. Nên có cơ chế **claim/ownership** qua queue `poll/take` hoặc trạng thái atomic và acknowledgment.

**11.** Khi nào copy-on-write dễ gây vấn đề hiệu năng?

Khi list lớn và cập nhật cấu trúc thường xuyên. Mỗi lần update có thể phải copy array; các snapshot cũ còn được iterator giữ cũng có thể gây áp lực bộ nhớ.

**12.** Lời gọi `size()` rồi duyệt `ConcurrentHashMap` có bảo đảm số item duyệt đúng bằng size đọc trước đó không?

Không khi có update concurrent. `size()` và lượt duyệt là những lần quan sát khác nhau, không tạo transaction.

## 19. Tài liệu API và kết luận

Các hợp đồng chính thức của JDK nên đối chiếu theo phiên bản Java đang sử dụng:

- [ConcurrentHashMap — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [ConcurrentLinkedQueue — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedQueue.html)
- [ConcurrentSkipListMap — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html)
- [CopyOnWriteArrayList — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)
- [Collections.synchronizedList — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html)
- [List.copyOf — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html)

**Ghi nhớ:**

~~~text
Fail-fast iterator:
  Phát hiện sửa đổi cấu trúc không phù hợp theo best effort.
  Không phải cơ chế phối hợp thread.

Weakly consistent iterator:
  Có thể duyệt song song với update.
  Không bảo đảm thấy tất cả update.
  Không phải point-in-time snapshot.

CopyOnWriteArrayList snapshot iterator:
  Giữ cấu trúc array tại lúc tạo iterator.
  Không thấy thay đổi cấu trúc sau đó.
  Không deep-copy các object mutable.

Coherent business snapshot:
  Cần giao thức nhiều field/key (lock chung, immutable state, ...).
  Đúng invariant và có điểm quan sát nhất quán.
~~~

**Kết luận:** Một collection thread-safe có thể cho phép iterator duyệt đồng thời với writer, nhưng **tính thread-safe của từng thao tác** không đồng nghĩa **nhất quán của cả một báo cáo**. Chọn giữa weak iteration, snapshot cấu trúc và snapshot nghiệp vụ dựa vào mức độ chấp nhận dữ liệu cũ, yêu cầu invariant và chi phí cập nhật/copy của hệ thống.