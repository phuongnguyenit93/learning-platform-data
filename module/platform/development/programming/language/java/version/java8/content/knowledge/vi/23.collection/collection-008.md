# Fail-fast và giới hạn bảo đảm khi có cập nhật đồng thời trong Java Collection

## 1. Mục tiêu và điều quan trọng nhất

Khi duyệt một `Collection`, có thể xảy ra tình huống chương trình thay đổi cấu trúc của collection trước khi việc duyệt kết thúc. Nhiều iterator của Java Collections Framework, ví dụ iterator của `ArrayList` và `HashMap`, được mô tả là **fail-fast**: nếu phát hiện kiểu sửa đổi không được phép, chúng có thể ném `ConcurrentModificationException` (viết tắt **CME**) để báo rằng cách duyệt đang không còn hợp lệ.

**Fail-fast không phải cơ chế đồng bộ và không có bảo đảm phát hiện mọi cập nhật đồng thời.** Javadoc của `ArrayList` quy định việc ném CME chỉ là **best effort**. Chương trình đúng **không được phụ thuộc** vào việc CME có xuất hiện để xác định dữ liệu đã an toàn hay chưa. <https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayList.html>

Đến cuối bài, bạn có thể:

1. Giải thích fail-fast, structural modification và vì sao CME có thể xảy ra **ngay trong một thread**.
2. Phân biệt fail-fast với **weakly consistent iteration** của các collection concurrent và **snapshot iteration** của `CopyOnWriteArrayList`.
3. Hiểu giới hạn của visibility, atomicity, synchronization và Java Memory Model khi collection có nhiều thread đọc/ghi.
4. Chọn các biện pháp phù hợp: `Iterator.remove()`, `removeIf(...)`, khóa bảo vệ quá trình duyệt, snapshot bất biến hoặc collection chuyên dụng.
5. Tránh các lỗi thường gặp khi dùng `Collections.synchronizedList(...)`, `ConcurrentHashMap`, `stream()` và `parallelStream()`.
6. Kiểm tra những tình huống biên mà không biến ngoại lệ CME thành điều kiện logic nghiệp vụ.

Các API được trình bày đều **còn sử dụng trong Java hiện đại**. Các ví dụ chạy đầy đủ dùng Java 17+ để có `List.of`, `List.copyOf` và `Stream.toList`; các cơ chế `Iterator`, CME, `Collections.synchronizedList` và `java.util.concurrent` vẫn là kiến thức thiết yếu trên các JDK hiện hành.

## 2. Fail-fast là gì?

**Iterator** giữ một vị trí duyệt trên collection. Với một số collection mutable thông thường, iterator phát hiện những thay đổi **cấu trúc** mà nó không quản lý và báo lỗi sớm bằng `ConcurrentModificationException`.

Ví dụ thay đổi cấu trúc:

- Thêm phần tử bằng `list.add(...)`.
- Xóa phần tử bằng `list.remove(...)` hoặc `list.clear()`.
- Thêm/xóa mapping trong `HashMap` khi đang duyệt các view `keySet()`/`values()`/`entrySet()`.

Một phép thay đổi **không nhất thiết là thay đổi cấu trúc**: với `ArrayList`, thay thế giá trị tại chỉ số đã có bằng `list.set(index, element)` không làm thay đổi số phần tử hoặc cấu trúc danh sách. Tương tự, sửa thuộc tính bên trong một object phần tử không có nghĩa collection đã thêm/xóa phần tử. Tuy nhiên, sự thay đổi thuộc tính có thể tạo **data race** nếu xảy ra giữa các thread và không có quy tắc đồng bộ.

Javadoc dùng khái niệm **structural modification** cho những thay đổi có thể ảnh hưởng việc duyệt. Đừng suy luận rằng mọi lệnh gán giá trị đều kích hoạt CME, hoặc mọi thay đổi nguy hiểm đều tạo CME.

### 2.1. `ConcurrentModificationException` không chứng minh có nhiều thread

Tên ngoại lệ chứa chữ *Concurrent*, nhưng “concurrent modification” có thể là hai hoạt động **xen kẽ trong cùng một thread**: iterator được tạo, sau đó mã khác sửa collection, rồi iterator tiếp tục duyệt.

Lưu thành `FailFastSingleThreadDemo.java`:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class FailFastSingleThreadDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>(
                List.of("An", "Binh", "Chi"));

        Iterator<String> it = names.iterator();
        System.out.println("first = " + it.next());

        names.add("Dung"); // Thay đổi cấu trúc ngoài iterator.

        try {
            System.out.println("next = " + it.next());
        } catch (ConcurrentModificationException ex) {
            System.out.println("detected = " +
                    ex.getClass().getSimpleName());
        }

        System.out.println("size = " + names.size());
    }
}
```

Biên dịch và chạy:

```bash
javac FailFastSingleThreadDemo.java
java FailFastSingleThreadDemo
```

Đầu ra trên implementation `ArrayList` của JDK hiện hành:

```text
first = An
detected = ConcurrentModificationException
size = 4
```

Ở ví dụ này **chỉ có một thread**. Sau khi iterator đọc phần tử `An`, chương trình thêm `Dung` trực tiếp vào `names`. Khi đọc tiếp, iterator của `ArrayList` trong JDK phát hiện cấu trúc thay đổi và ném CME.

**Giới hạn kết luận:** Đây là chương trình minh họa có điều kiện thực thi được kiểm soát và đúng với implementation `ArrayList`; không được dùng việc quan sát CME ở ví dụ này để khẳng định rằng *mọi* cập nhật giữa các thread sẽ luôn tạo CME. Trong môi trường đa luồng, việc quan sát có thể còn bị ảnh hưởng bởi lịch chạy và vấn đề visibility.

## 3. Vì sao fail-fast chỉ là best effort?

Trong một số implementation của JDK, iterator duy trì thông tin về phiên bản cấu trúc dự kiến; khi một thao tác kiểm tra phát hiện phiên bản nguồn đã thay đổi, nó báo CME. Ví dụ `ArrayList` có chi tiết triển khai liên quan tới `modCount`/`expectedModCount`.

Nhưng **đây là một cách triển khai**, không phải lời hứa rằng:

- Mọi lần truy cập `hasNext()` đều kiểm tra thay đổi.
- Mọi luồng ghi đều lập tức thấy được từ luồng đang đọc.
- CME sẽ xuất hiện ngay tại đúng dòng gây sửa đổi.
- Mọi collection đều dùng cùng bộ đếm, cùng thời điểm kiểm tra hay cùng chiến lược fail-fast.
- Không thấy CME đồng nghĩa dữ liệu được duyệt là chính xác hoặc nhất quán.

Điều kiện sửa đổi **không đồng bộ** của nhiều collection thường không có ràng buộc *happens-before* thích hợp giữa các thread. Java Memory Model không bắt buộc một thread ngay lập tức thấy mọi cập nhật từ thread khác khi không có synchronization. Vì thế, khả năng phát hiện sai lệch chỉ theo best effort. Bên cạnh đó, ngay cả khi tất cả thao tác đều quan sát được, implementation có thể không kiểm tra ở mọi điểm.

> **Quy tắc thiết kế:** CME chỉ hỗ trợ phát hiện lỗi lập trình. Nó không phải transaction rollback, memory fence, mutex, công cụ xác nhận dữ liệu toàn vẹn hay cơ chế thử lại (retry) đáng tin cậy.

Việc bắt `ConcurrentModificationException` rồi chạy lại iterator cũng **không đủ** nếu không loại bỏ nguyên nhân: collection có thể tiếp tục bị sửa giữa các lần thử; chương trình có thể đọc dữ liệu không nhất quán hoặc lặp vô hạn. Nếu nghiệp vụ cần snapshot hoặc kiểm soát thứ tự thao tác, hãy chọn một thiết kế có hợp đồng rõ ràng.

### 3.1. Không nhầm `ConcurrentModificationException` với `IllegalStateException`

`Iterator.remove()` có thể ném `IllegalStateException` nếu gọi trước `next()` hoặc gọi hai lần liên tiếp sau một lần `next()`. Đó là lỗi **trạng thái sử dụng Iterator**.

`ConcurrentModificationException` thường liên quan tới việc iterator phát hiện một thay đổi không phù hợp của nguồn. Hai ngoại lệ có nguyên nhân và hướng sửa khác nhau; không nên viết một `catch (RuntimeException)` chung để che giấu chúng.

## 4. Thay đổi an toàn khi duyệt: `Iterator.remove()`

Đối với iterator có hỗ trợ xóa, **chính iterator** có thể xóa phần tử nó vừa trả về bằng `Iterator.remove()`. Thao tác này là một **optional operation**: một số iterator không cho phép xóa và ném `UnsupportedOperationException`.

Lưu `IteratorRemoveSafeDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class IteratorRemoveSafeDemo {
    public static void main(String[] args) {
        List<String> tags = new ArrayList<>(
                List.of("keep", "drop-A", "keep2", "drop-B"));

        Iterator<String> it = tags.iterator();
        while (it.hasNext()) {
            String tag = it.next();
            if (tag.startsWith("drop-")) {
                it.remove();
            }
        }
        System.out.println("after iterator = " + tags);

        tags.removeIf("keep2"::equals);
        System.out.println("after removeIf = " + tags);
    }
}
```

```bash
javac IteratorRemoveSafeDemo.java
java IteratorRemoveSafeDemo
```

```text
after iterator = [keep, keep2]
after removeIf = [keep]
```

Giải thích:

1. `it.next()` xác định phần tử hiện tại.
2. `it.remove()` yêu cầu iterator xóa phần tử vừa trả về và cập nhật trạng thái duyệt tương ứng theo hợp đồng của nó.
3. `tags.removeIf(...)` là API cấp collection (từ Java 8), rõ ràng hơn khi mục đích chỉ là xóa mọi phần tử khớp điều kiện và nguồn có hỗ trợ chỉnh sửa.

**Phạm vi an toàn:** đây là các cách thao tác đúng khi không có nguồn ghi khác can thiệp trái phép. Chúng **không biến một `ArrayList` thành concurrent collection**. Nếu thread khác có thể sửa cùng danh sách, vẫn cần synchronization hoặc thiết kế ownership phù hợp.

### 4.1. Cách sai thường gặp trong `for-each`

`for (T x : list)` sử dụng iterator của collection trong nhiều trường hợp. Vì vậy, xóa trực tiếp từ danh sách trong thân vòng lặp có thể làm iterator không hợp lệ:

```java
// MẪU SAI: không thực thi đoạn này trong ứng dụng.
// for (String tag : tags) {
//     if (tag.startsWith("drop-")) {
//         tags.remove(tag); // Sửa list ngoài iterator đang duyệt.
//     }
// }
```

*Đoạn trên là pseudocode được comment để chỉ lỗi, không phải ví dụ đầy đủ.* Sử dụng `removeIf(...)`, `Iterator.remove()` (khi được hỗ trợ) hoặc tạo danh sách mới qua `stream().filter(...)`. Việc xóa có gây CME ở một lần chạy cụ thể hay không không phải tiêu chí để kết luận mã đúng.

### 4.2. `ListIterator.add()` và `set()`

`ListIterator` mở rộng `Iterator` để hỗ trợ (khi list cho phép) `add`, `set` và duyệt hai chiều. Khi cần thêm phần tử tại vị trí đang duyệt của một danh sách mutable, dùng chính `ListIterator.add()` thay vì `list.add()` bên ngoài. Nhưng đó vẫn là thao tác trên một collection không tự thread-safe.

## 5. Sửa phần tử khác sửa cấu trúc

Lưu `NonStructuralChangeDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class NonStructuralChangeDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(
                List.of("A", "B", "C"));

        Iterator<String> it = values.iterator();
        values.set(1, "B2");

        List<String> seen = new ArrayList<>();
        it.forEachRemaining(seen::add);

        System.out.println("seen = " + seen);
        System.out.println("values = " + values);
    }
}
```

```bash
javac NonStructuralChangeDemo.java
java NonStructuralChangeDemo
```

```text
seen = [A, B2, C]
values = [A, B2, C]
```

Với `ArrayList`, `set` thay phần tử ở một index đã có nhưng không thay đổi kích thước danh sách, nên không bị xem là structural modification. Đây là một chương trình tuần tự có hành vi xác định.

**Không suy ra “set là an toàn giữa hai thread”.** Nếu thread A đang đọc các object trong list, thread B gọi `set` hoặc sửa trường mutable của object mà không có synchronization, chương trình vẫn có thể có data race, nhìn thấy giá trị cũ/mới không nhất quán hoặc vi phạm invariant của ứng dụng. CME không phát hiện tất cả những trường hợp đó.

Tương tự, đối với `Map`, cập nhật value gắn với key đã có và thêm/xóa mapping mới là hai trường hợp khác nhau về cấu trúc. Chi tiết fail-fast cụ thể cần theo tài liệu của implementation, không coi mọi thao tác `put` đều giống nhau.

## 6. Ba mô hình duyệt cần phân biệt

| Loại duyệt | Nguồn tiêu biểu | Khi nguồn thay đổi lúc duyệt | Có bảo đảm là snapshot không? |
| --- | --- | --- | --- |
| **Fail-fast** | `ArrayList`, `HashMap` (view iterator), `LinkedList` | Có thể báo CME theo best effort nếu sửa không được phép | **Không** |
| **Weakly consistent** | `ConcurrentHashMap`, `ConcurrentLinkedQueue` | Cho phép tiếp tục duyệt trong lúc cập nhật; có thể phản ánh **một số** cập nhật | **Không** |
| **Snapshot iterator** | `CopyOnWriteArrayList` | Iterator nhìn vào ảnh chụp mảng tại thời điểm tạo iterator; cập nhật sau không làm thay đổi các phần tử tham chiếu đang duyệt | **Có snapshot cấu trúc/tham chiếu**, không phải deep copy |

Không gom mọi collection thread-safe vào một loại duyệt. Ví dụ:

- `Collections.synchronizedList(new ArrayList<>())` là một **synchronized wrapper**, nhưng việc duyệt vẫn cần khóa thủ công trên wrapper.
- `ConcurrentHashMap` cho phép thao tác read/write đồng thời với weakly consistent iteration; nó không cung cấp một ảnh chụp nguyên tử của toàn bộ map cho iterator.
- `CopyOnWriteArrayList` thích hợp khi số lượt đọc/duyệt lớn hơn nhiều so với số lần cập nhật. Mỗi cập nhật tạo bản sao mảng nội bộ, nên chi phí ghi và bộ nhớ có thể cao.
- `List.of(...)` tạo collection không cho thay đổi cấu trúc qua API; đây không phải cùng khái niệm với một “view” không cho sửa nhưng nguồn gốc vẫn có thể bị sửa.

Các API này đều hiện hành. Chọn theo **yêu cầu quan sát dữ liệu** và tỷ lệ đọc/ghi, không chỉ dựa trên việc chúng có ném CME hay không.

## 7. `ConcurrentHashMap`: weakly consistent, không phải fail-fast

`ConcurrentHashMap<K,V>` là map thiết kế cho truy cập đồng thời. Iterator, Spliterator và Enumeration của các view như `keySet()`/`entrySet()` không ném `ConcurrentModificationException` do thao tác cập nhật hợp lệ trên map. Chúng **weakly consistent**: có thể thấy một phần cập nhật xảy ra trong thời gian duyệt, nhưng không hứa rằng mọi entry mới sẽ xuất hiện hoặc iterator đại diện cho một trạng thái toàn bộ map tại một thời điểm duy nhất.

Một vài giới hạn cần nhớ:

1. **Không giả định snapshot:** iterator không phải ảnh chụp nhất quán của cả map.
2. **Không giả định thứ tự:** `ConcurrentHashMap` không cam kết encounter order theo key.
3. **Không điều khiển cùng iterator từ nhiều thread:** chính iterator được thiết kế để một thread sử dụng tại một thời điểm.
4. **Các phép tổng hợp như `size()`, `isEmpty()`, `containsValue()`** có giá trị quan sát hữu ích nhất khi không có thay đổi đồng thời; đừng dùng `size` trong lúc ghi nhiều để thực hiện kiểm tra transaction.
5. **Không có null key/null value:** nếu dữ liệu nghiệp vụ thiếu, chọn biểu diễn khác thay vì truyền null.

Ví dụ sau dùng một thay đổi sau khi tạo iterator; ta **không in nội dung iterator** vì kết quả duyệt có thể khác theo thời điểm hoặc triển khai. Lưu `ConcurrentMapTraversalDemo.java`:

```java
import java.util.Iterator;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.IntStream;

public class ConcurrentMapTraversalDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map =
                new ConcurrentHashMap<>();
        map.put("alpha", 1);

        Iterator<String> keys = map.keySet().iterator();
        map.put("beta", 2);

        while (keys.hasNext()) {
            keys.next();
        }
        System.out.println("weak iterator completed");
        System.out.println("final map = " + new TreeMap<>(map));

        ConcurrentHashMap<String, Integer> counts =
                new ConcurrentHashMap<>();
        IntStream.range(0, 1000).parallel().forEach(i ->
                counts.merge("hits", 1, Integer::sum));
        System.out.println("hits = " + counts.get("hits"));
    }
}
```

```bash
javac ConcurrentMapTraversalDemo.java
java ConcurrentMapTraversalDemo
```

```text
weak iterator completed
final map = {alpha=1, beta=2}
hits = 1000
```

- Phần đầu minh họa iterator có thể tiếp tục duyệt dù map được cập nhật. **Không thể suy ra** từ stdout rằng iterator đã thấy `beta`.
- `new TreeMap<>(map)` được thực hiện sau khi chương trình đã hoàn tất cập nhật, nhằm in key theo thứ tự xác định; nếu có writer khác chạy song song thì một lần copy cũng không tạo ảnh chụp nguyên tử của toàn bộ `ConcurrentHashMap`.
- `merge("hits", 1, Integer::sum)` là phép cập nhật atomic theo khóa do `ConcurrentHashMap` hỗ trợ, nên 1.000 cập nhật song song mang lại tổng `1000` sau khi pipeline kết thúc.

**Lưu ý về độ tuyến tính (linearizability):** Hợp đồng của cập nhật/tra cứu theo từng key không đồng nghĩa một phép quét nhiều entry thấy tất cả key tại cùng một thời điểm. Nếu nghiệp vụ cần bản ghi báo cáo nhất quán theo transaction, cần cơ chế snapshot/lock/version ở tầng thích hợp hoặc khả năng transaction của database.

### 7.1. `ConcurrentLinkedQueue` và khả năng quan sát phần tử mới

`ConcurrentLinkedQueue` cũng có iterator weakly consistent, thường thích hợp cho hàng đợi không chặn. Nó không cung cấp một snapshot cố định để logic phân tích dữ liệu toàn cục; iterator có thể thấy hoặc không thấy các phần tử mới thêm trong khi đang duyệt. Nếu cần xử lý các phần tử theo giao thức queue, dùng `poll`/`offer` và các cơ chế handoff thích hợp thay vì dựa vào một vòng lặp iterator như một transaction.

## 8. `CopyOnWriteArrayList`: iterator snapshot, nhưng không phải “đông cứng object”

`CopyOnWriteArrayList` duy trì mảng nội bộ theo chiến lược copy-on-write. Khi tạo iterator, iterator gắn với một snapshot của mảng **tại thời điểm tạo**. Thay đổi list sau đó không làm thay đổi tập tham chiếu mà iterator cũ đang duyệt.

Lưu `CopyOnWriteSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class CopyOnWriteSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArrayList<String> list =
                new CopyOnWriteArrayList<>(
                        List.of("A", "B"));

        Iterator<String> snapshot = list.iterator();
        list.add("C");
        list.remove("A");

        List<String> oldView = new ArrayList<>();
        snapshot.forEachRemaining(oldView::add);

        System.out.println("snapshot = " + oldView);
        System.out.println("current = " + list);

        try {
            snapshot.remove();
        } catch (UnsupportedOperationException ex) {
            System.out.println("iterator remove unsupported");
        }
    }
}
```

```bash
javac CopyOnWriteSnapshotDemo.java
java CopyOnWriteSnapshotDemo
```

```text
snapshot = [A, B]
current = [B, C]
iterator remove unsupported
```

Những điều ví dụ chứng minh:

- Iterator cũ nhìn vào `A`, `B` dù current list đã là `B`, `C`.
- `CopyOnWriteArrayList` iterator **không hỗ trợ `remove`, `set` hoặc `add`** thông qua chính iterator/listIterator.
- Các thay đổi được lưu vào collection mới về mặt mảng chứa tham chiếu, nhưng không tạo deep copy từng object. Nếu phần tử là một `Account` mutable và thread khác sửa trường của Account, snapshot iterator có thể nhìn thấy state mới của object đó. “Snapshot” ở đây là **snapshot cấu trúc/tham chiếu**, không bảo đảm một ảnh chụp sâu, bất biến của toàn bộ object graph.

Chi phí của copy-on-write thường chấp nhận được khi **đọc thường xuyên, ghi hiếm** (chẳng hạn danh sách listener hoặc cấu hình thay đổi ít). Nếu ghi liên tục hoặc list rất lớn, chi phí copy sẽ tăng; cân nhắc concurrent collection phù hợp hoặc mô hình lưu trữ khác.

## 9. `Collections.synchronizedList`: vẫn cần khóa khi duyệt

`Collections.synchronizedList(...)` trả một wrapper đồng bộ cho các operation riêng lẻ. Tuy nhiên, **đi qua toàn bộ iterator không phải một operation duy nhất**: giữa các lần gọi `hasNext` và `next`, thread khác có thể thay đổi list nếu không bảo vệ toàn bộ chuỗi duyệt bằng cùng một lock.

Tài liệu Oracle yêu cầu **tự đồng bộ trên chính wrapper** khi duyệt qua `Iterator`, `Spliterator` hoặc `Stream`. Mọi thread cũng phải truy cập collection nền thông qua wrapper hoặc cùng một cơ chế khóa. <https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html>

Lưu `SynchronizedTraversalDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public class SynchronizedTraversalDemo {
    public static void main(String[] args)
            throws InterruptedException {
        List<Integer> shared = Collections.synchronizedList(
                new ArrayList<>(List.of(1, 2, 3)));
        CountDownLatch startWrite = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            try {
                startWrite.await();
                shared.add(4); // Dùng wrapper, tôn trọng khóa.
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });
        writer.start();

        List<Integer> observed = new ArrayList<>();
        synchronized (shared) {
            Iterator<Integer> it = shared.iterator();
            startWrite.countDown();
            while (it.hasNext()) {
                observed.add(it.next());
            }
        }

        writer.join();
        System.out.println("observed = " + observed);
        System.out.println("after = " + shared);
    }
}
```

```bash
javac SynchronizedTraversalDemo.java
java SynchronizedTraversalDemo
```

```text
observed = [1, 2, 3]
after = [1, 2, 3, 4]
```

Lời giải thích không phụ thuộc timing:

1. `main` giữ monitor của `shared` trong **toàn bộ thời gian iterator chạy**.
2. `startWrite.countDown()` giải phóng thread ghi đang chờ, nhưng `shared.add(4)` phải lấy monitor của synchronized wrapper. Nó không thể thực hiện cập nhật cho đến khi `main` rời khối `synchronized(shared)`.
3. `writer.join()` bảo đảm thread ghi đã hoàn thành trước khi in `after`.

Kết quả: vòng duyệt thấy ba phần tử ban đầu; phép ghi chỉ hoàn thành sau khi lock được giải phóng. Nếu các writer bỏ qua wrapper và gọi trực tiếp collection nền, ví dụ `backing.add(...)`, bảo đảm khóa của wrapper bị phá vỡ.

**Không nhầm:** đồng bộ khi duyệt không cho phép code bên trong khối khóa tự ý thay đổi cấu trúc list bằng `shared.add(...)` ngoài iterator rồi mong vẫn duyệt hợp lệ. Mutual exclusion xử lý **cạnh tranh giữa thread**; quy tắc không phá hỏng iterator vẫn phải được tuân thủ trong từng thread.

### 9.1. Với `Collections.synchronizedMap` và các view

Đối với `Map` đã được bọc bằng `Collections.synchronizedMap(rawMap)`, khi duyệt `map.keySet()`/`entrySet()`, phải khóa trên **`map` wrapper**, không phải trên riêng view `keySet()`. Ví dụ:

```java
Map<String, Integer> map =
        Collections.synchronizedMap(new HashMap<>());
Set<String> keys = map.keySet();
synchronized (map) {
    for (String key : keys) {
        // Truy cập các mapping dưới cùng monitor map.
    }
}
```

*Đây là snippet minh họa, cần import `Map`, `HashMap`, `Set` và `Collections` nếu đặt trong chương trình. Các sửa đổi đồng thời phải nhất quán dùng cùng wrapper/khóa.*

Đối với các sorted/navigable view hoặc submap, quy tắc khóa cũng phải tuân theo wrapper gốc như Javadoc hướng dẫn. Không tự suy đoán rằng `synchronized(view)` bảo vệ đầy đủ map gốc.

## 10. Snapshot thực sự và sự khác biệt với unmodifiable view

Khi cần xử lý một tập dữ liệu **ổn định tại thời điểm lấy mẫu**, có thể tạo **bản sao riêng** trong khi đã giữ khóa cần thiết (nếu nguồn đang được chia sẻ) rồi duyệt bản sao mà không giữ khóa lâu.

Với một `List` được dùng tuần tự:

- `Collections.unmodifiableList(backing)` chỉ là **view không cho sửa thông qua view**. Nếu ai đó sửa `backing`, nội dung quan sát từ view có thể đổi.
- `List.copyOf(backing)` (từ Java 10) tạo danh sách không sửa được theo hợp đồng và không bị thay đổi cấu trúc do chỉnh sửa về sau của `backing`. API có thể tái sử dụng instance nếu nguồn đã là list không sửa được phù hợp.
- `List.of(...)` (Java 9+) là collection không sửa được, không nhận phần tử `null` và không cho thêm/xóa thông qua API.
- Những giải pháp trên chỉ sao chép hoặc giữ **tham chiếu phần tử**; không tự sao chép sâu đối tượng mutable.

Lưu `UnmodifiableVsSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> backing = new ArrayList<>(
                List.of("one", "two"));

        List<String> view =
                Collections.unmodifiableList(backing);
        List<String> copy = List.copyOf(backing);

        backing.add("three");

        System.out.println("view = " + view);
        System.out.println("copy = " + copy);

        try {
            copy.add("four");
        } catch (UnsupportedOperationException ex) {
            System.out.println("copy cannot be modified");
        }
    }
}
```

```bash
javac UnmodifiableVsSnapshotDemo.java
java UnmodifiableVsSnapshotDemo
```

```text
view = [one, two, three]
copy = [one, two]
copy cannot be modified
```

**Rất quan trọng với cập nhật đồng thời:** gọi `List.copyOf(sharedArrayList)` trong khi thread khác sửa `sharedArrayList` **không tự trở thành thao tác snapshot an toàn**. Đầu vào vẫn phải được đọc dưới quy tắc đồng bộ thích hợp, hoặc dùng cấu trúc có snapshot/transaction contract riêng.

Nếu nguồn là `Collections.synchronizedList(...)` và mục tiêu là tạo snapshot cấu trúc, có thể:

```java
List<String> snapshot;
synchronized (shared) {
    snapshot = List.copyOf(shared);
}
// Duyệt snapshot sau khi đã thả khóa.
```

*Đoạn trên là snippet: `shared` phải là một synchronized list được khai báo ở bên ngoài. Tất cả writer phải tuân thủ cùng khóa; các phần tử mutable bên trong không được deep copy.*

## 11. Streams, Spliterators và cập nhật đồng thời

`Collection.stream()` và `parallelStream()` dựa trên nguồn duyệt, thường là `Spliterator`. Với các nguồn không hỗ trợ concurrent modification, các thao tác trong pipeline cần **non-interfering**: không tự ý sửa nguồn đang được duyệt.

Ví dụ có rủi ro:

```java
// Sai thiết kế: sửa nguồn từ chính pipeline.
// List<Integer> values = new ArrayList<>(List.of(1, 2, 3));
// values.stream().forEach(x -> values.add(x + 10));
```

*Các dòng đã comment chỉ để minh họa lỗi, không phải code nên chạy.* Tùy implementation và thời điểm, chương trình có thể ném CME hoặc có những hành vi khác không đúng kỳ vọng. Đừng thử sửa bằng cách đổi `stream()` sang `parallelStream()`; parallel còn tăng phức tạp do interleaving giữa các nhánh.

Trong code thực tế, nếu mục tiêu là **tạo một kết quả khác** dựa trên dữ liệu gốc, dùng `map`/`filter`/`collect` hoặc `Stream.toList()`, không mutate chính nguồn trong pipeline.

Lưu `SafeStreamSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SafeStreamSnapshotDemo {
    public static void main(String[] args) {
        List<Integer> original = new ArrayList<>(
                List.of(1, 2, 3, 4, 5));

        List<Integer> snapshot = List.copyOf(original);
        List<Integer> evenSquares = snapshot.parallelStream()
                .filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .sorted()
                .toList();

        original.add(6);

        System.out.println("evenSquares = " + evenSquares);
        System.out.println("original = " + original);
        System.out.println("snapshot = " + snapshot);
    }
}
```

```bash
javac SafeStreamSnapshotDemo.java
java SafeStreamSnapshotDemo
```

```text
evenSquares = [4, 16]
original = [1, 2, 3, 4, 5, 6]
snapshot = [1, 2, 3, 4, 5]
```

Ở ví dụ này không có thread ghi đồng thời lên `original` khi đang tạo snapshot. `parallelStream` chỉ đọc một nguồn không sửa được, các lambda là stateless/non-interfering và kết quả được `sorted()` theo thứ tự rõ ràng. `Stream.toList()` có từ Java 16; nó trả list không sửa được. Nếu mục tiêu yêu cầu chạy **Java 8**, dùng `collect(Collectors.toList())` nhưng hãy kiểm tra hợp đồng danh sách kết quả theo nhu cầu.

### 11.1. `parallelStream().forEach(sharedList::add)` là lỗi khác CME

Một lỗi riêng biệt là cập nhật **kết quả chung** bằng `ArrayList` trong các task parallel:

```java
// Sai: nhiều worker thêm vào cùng ArrayList không thread-safe.
// List<Integer> result = new ArrayList<>();
// numbers.parallelStream().forEach(result::add);
```

Đây là **data race trên kết quả**, không chỉ là vấn đề fail-fast của nguồn. Có thể mất phần tử hoặc phá invariant. Thay bằng phép `collect(Collectors.toList())` cho phép thư viện quản lý các container trung gian. Khi cần concurrent aggregation, chọn collector/concurrent data structure có contract phù hợp.

### 11.2. `Spliterator.CONCURRENT` không làm mọi thao tác an toàn

Một `Spliterator` có characteristic `CONCURRENT` mô tả **nguồn dữ liệu** cho phép cập nhật đồng thời theo chính sách đã công bố. Nó không bảo đảm một Spliterator object an toàn nếu hai thread cùng gọi `tryAdvance` trên chính object đó, cũng không biến toàn bộ phép tính thành transaction. Với `Spliterator.IMMUTABLE`, nguồn không được sửa cấu trúc khi traversal; hai cờ có ý nghĩa khác nhau.

## 12. Atomicity và visibility: những gì không thể giải quyết bằng CME

Để thiết kế truy cập nhiều thread đúng, cần tách các khái niệm:

| Thuộc tính | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Thread safety** | Cấu trúc dữ liệu có giữ invariant khi nhiều thread thao tác hợp lệ không? | `ConcurrentHashMap.put`, `CopyOnWriteArrayList.add` |
| **Atomicity** | Một thao tác gồm các bước có được xem là không bị xen giữa theo contract? | `ConcurrentHashMap.merge` cho một khóa |
| **Visibility** | Thread đọc có quan sát các cập nhật đã được publish theo quy tắc đồng bộ không? | Khóa `synchronized` hoặc các quan hệ happens-before phù hợp |
| **Snapshot consistency** | Nhiều phần tử/key trong một lượt đọc có thuộc cùng một thời điểm logic không? | Snapshot/transaction/lock bảo vệ toàn bộ lượt đọc |
| **Fail-fast detection** | Có thông báo nghi ngờ cấu trúc nguồn bị sửa sai cách không? | CME của iterator `ArrayList` theo best effort |

Các hàng này không thay thế lẫn nhau. Có một `ConcurrentHashMap` thread-safe không có nghĩa truy vấn `size()` và sau đó duyệt toàn bộ map là **một transaction atomic**. Có một `Collections.synchronizedList` cũng không có nghĩa mọi tổ hợp `if (!contains) add` đều atomic nếu không giữ khóa cho **toàn bộ** điều kiện và cập nhật.

Ví dụ mẫu sai:

```java
// Hai thao tác riêng có thể bị xen giữa:
// if (!map.containsKey(key)) {
//     map.put(key, value);
// }
```

Khi nhiều thread chạy đoạn trên, có thể cả hai đều thấy key chưa tồn tại và cùng thử ghi. Trên `ConcurrentMap`, dùng `putIfAbsent` hoặc `computeIfAbsent` theo hợp đồng API. Trên map thông thường, dùng một khóa bao bọc cả kiểm tra và cập nhật hoặc thay bằng cấu trúc phù hợp.

Không coi thêm `volatile` vào tham chiếu `List` là cách biến mọi phép thay đổi cấu trúc bên trong list thành thread-safe. `volatile` cho tham chiếu không tự bảo vệ thao tác `add/remove` hay tạo snapshot của phần tử.

## 13. Cập nhật số đếm đồng thời đúng cách: `merge` và `LongAdder`

`ConcurrentHashMap.merge(key, value, remappingFunction)` hỗ trợ cập nhật atomic cho một key. Với lượng cập nhật lớn, một `LongAdder` cho mỗi khóa có thể giảm tranh chấp ở bộ đếm. Sau khi **tất cả tác vụ đã hoàn thành**, `LongAdder.sum()` cho kết quả tích lũy đã có; nếu vẫn có thread đang tăng, `sum()` không phải snapshot atomic của mọi lần tăng đồng thời.

Lưu `ConcurrentCounterDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.IntStream;

public class ConcurrentCounterDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, LongAdder> counters =
                new ConcurrentHashMap<>();

        IntStream.range(0, 3_000).parallel().forEach(i ->
                counters.computeIfAbsent("ok",
                        key -> new LongAdder()).increment());

        System.out.println("ok = " +
                counters.get("ok").sum());
        System.out.println("keys = " + counters.size());
    }
}
```

```bash
javac ConcurrentCounterDemo.java
java ConcurrentCounterDemo
```

```text
ok = 3000
keys = 1
```

Trong ví dụ, `computeIfAbsent` an toàn khi nhiều thread cùng cần tạo counter cho key `ok`; sau đó mỗi task cập nhật `LongAdder`. `parallel().forEach(...)` là terminal operation, khi lời gọi trở về thì các action của pipeline đó đã kết thúc. Lúc này lấy `sum()` cho giá trị chính xác 3.000 trong ví dụ.

**Không lấy nguyên tắc này làm cớ cho mọi side effect trong Stream:** phép cập nhật ở đây có thiết kế concurrent/atomic rõ ràng và bài toán cần cập nhật trạng thái chung. Với việc chỉ tổng hợp số từ dữ liệu, `mapToInt(...).sum()` hoặc một collector chuẩn vẫn thường đơn giản và dễ review hơn.

## 14. Không có CME không có nghĩa có thứ tự hoặc đúng nghiệp vụ

Ba trường hợp dễ gây hiểu lầm:

1. **Weakly consistent iterator hoàn thành:** không có exception, nhưng số entry hoặc giá trị nó đọc được có thể không phù hợp cho báo cáo cần nhất quán.
2. **Snapshot iterator hoàn thành:** nó đọc cấu trúc tại thời điểm tạo iterator, nên có thể **không thấy** cập nhật mới mà nghiệp vụ muốn hiển thị tức thời.
3. **Iterator của `ArrayList` không ném CME:** cũng không chứng minh không có thread nào đã can thiệp; nó chỉ chứng minh lần chạy cụ thể không phát hiện sửa đổi theo điều kiện đang quan sát.

Nếu cần đọc “tất cả đơn hàng đã hoàn thành tại thời điểm T”, bạn phải định nghĩa rõ T và cơ chế lấy ảnh chụp/transaction. Nếu cần tiêu thụ công việc đến liên tục, nên dùng queue/protocol dành cho concurrent processing. Chỉ thay `ArrayList` bằng `CopyOnWriteArrayList` hoặc `ConcurrentHashMap` không thể tự bảo đảm tất cả yêu cầu nghiệp vụ.

### 14.1. Bộ dữ liệu “không cho sửa” chưa chắc bất biến sâu

`List.of(accountA, accountB)` không cho thêm/xóa phần tử qua list, nhưng `accountA.setBalance(...)` (nếu object mutable) vẫn có thể sửa đối tượng mà các thread đọc qua danh sách. Danh sách không sửa được không biến tất cả phần tử bên trong thành immutable object; vẫn cần thiết kế value object, safe publication hoặc synchronization phù hợp.

## 15. Chọn chiến lược theo yêu cầu

| Tình huống | Gợi ý | Lý do/giới hạn |
| --- | --- | --- |
| Duyệt/xóa theo điều kiện trong một thread | `Iterator.remove()` hoặc `removeIf(...)` | Thay đổi được thực hiện theo API hợp lệ; không làm nguồn tự thread-safe |
| Đọc/ghi có cùng monitor, cần iteration nhất quán | `Collections.synchronizedList` + `synchronized(wrapper)` cho toàn bộ duyệt | Tất cả đường truy cập phải tuân thủ cùng khóa; có thể chặn writer |
| Nhiều thread cập nhật/truy vấn map | `ConcurrentHashMap` | Atomic cho nhiều operation theo key; iterator weakly consistent |
| Danh sách chủ yếu đọc, rất ít cập nhật | `CopyOnWriteArrayList` | Iterator snapshot cấu trúc; ghi tốn chi phí copy |
| Cần xử lý tập phần tử cố định | Snapshot được tạo an toàn (ví dụ `List.copyOf` dưới lock) | Chỉ snapshot nông; việc tạo snapshot cũng cần an toàn |
| Cần kết quả mới từ dữ liệu không bị thay đổi | `stream().filter(...).toList()` / collector | Tách nguồn và kết quả; không sửa source trong pipeline |
| Cần tổng hợp tại một thời điểm transaction | Snapshot/transaction/khóa được thiết kế riêng | Iterator concurrent thông thường không bảo đảm snapshot đa khóa |
| Cần nhiều tác vụ tăng counter cùng key | `ConcurrentHashMap.merge` hoặc `LongAdder` | Dùng đúng API atomic; `sum()` khi có writer vẫn đang chạy không phải snapshot |

Để đưa ra lựa chọn chính xác, hãy xác định hai câu hỏi: **“Nguồn có thể thay đổi lúc đọc không?”** và **“Mỗi lượt đọc cần bảo đảm mức nhất quán nào?”**. Nếu câu trả lời thứ hai là “phải thấy toàn bộ cập nhật theo một thời điểm”, một iterator weakly consistent không phù hợp, dù nó không bao giờ ném CME.

## 16. Kiểm thử đúng: không chờ CME để xác nhận safety

### 16.1. Test tuần tự cho vi phạm API

Trường hợp `ArrayList` có thể kiểm thử dễ bằng một thread như chương trình `FailFastSingleThreadDemo`: tạo iterator, thay đổi cấu trúc ngoài iterator, sau đó gọi `next()`. Đây là test để hiểu implementation/hành vi điển hình. Nhưng **không** viết unit test kết luận “code an toàn” chỉ vì một lần chạy không ném exception.

### 16.2. Test concurrency có ràng buộc quan sát rõ

Hãy kiểm thử **invariant** của ứng dụng: không mất dữ liệu, không trùng xử lý, không sai số đếm, đáp ứng điều kiện khóa/snapshot. Dùng `CountDownLatch`, `ExecutorService`, `Future` hoặc cơ chế phối hợp phù hợp để tạo lịch chạy có kiểm soát; không chỉ dùng `Thread.sleep(...)` để cầu mong hai thread đụng nhau.

Ví dụ `SynchronizedTraversalDemo` dùng `CountDownLatch` để đảm bảo writer chỉ cố cập nhật sau khi thread đọc đã nắm monitor, nên stdout xác định. Test số đếm `ConcurrentCounterDemo` đảm bảo tác vụ kết thúc trước khi so tổng.

Các kỹ thuật stress test/race detector có thể tìm ra lỗi, nhưng **không chứng minh mọi lịch chạy đều đúng**. Đọc contract của kiểu collection cùng Java Memory Model vẫn là điều bắt buộc khi thiết kế đồng thời.

### 16.3. Đừng kiểm thử số lần hoặc thời điểm ném CME

Đừng viết logic dạng:

```java
// Thiết kế không đúng:
// try {
//     process(list.iterator());
// } catch (ConcurrentModificationException ex) {
//     // Giả sử vừa phát hiện một writer, rồi tự retry mãi.
// }
```

*Đây là snippet minh họa lỗi, không phải chương trình runnable.* Vì không có bảo đảm CME xuất hiện với mọi thay đổi, cách dùng exception để làm tín hiệu synchronization/retry không đúng. Nếu cần retry do thay đổi phiên bản, dùng versioning/locking/transaction hoặc giao thức optimistic concurrency riêng, có điều kiện kiểm tra atomic và quy tắc retry hữu hạn.

## 17. Bài tập áp dụng

**Bài 1 — Structural modification:** Một `ArrayList` có `[A, B, C]`; tạo iterator rồi gọi `list.set(1, "B2")`. Thao tác có thay đổi cấu trúc không? Tại sao kết quả khác với `list.add("D")`?

**Bài 2 — Chọn đúng API:** Cần xóa các phần tử có tên bắt đầu bằng `temp-` trên một `ArrayList` chỉ dùng trong một thread. Hãy viết lời giải bằng `removeIf` và bằng `Iterator.remove`.

**Bài 3 — Nhiều thread truy cập Map:** Nhiều thread đếm số event theo key; vì sao `ConcurrentHashMap.merge(key, 1, Integer::sum)` phù hợp hơn `HashMap.put(key, map.getOrDefault(key, 0) + 1)`?

**Bài 4 — Snapshot hay cập nhật mới:** Một màn hình cần liệt kê tất cả listener tại thời điểm bắt đầu phát sự kiện. Tại sao `CopyOnWriteArrayList` có thể phù hợp? Khi có listener mới được thêm trong lúc phát, nó có nằm trong iterator đã tạo trước đó không?

**Bài 5 — Giới hạn bảo đảm:** Nếu iterator của `ConcurrentHashMap` không ném CME khi writer đang cập nhật, liệu có thể dùng kết quả duyệt để báo cáo tổng tiền chính xác tại một thời điểm? Giải thích.

Lời giải thực hành cho bài 2–3, lưu `FailFastPractice.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.IntStream;

public class FailFastPractice {
    public static void main(String[] args) {
        List<String> first = new ArrayList<>(
                List.of("temp-a", "keep", "temp-b", "done"));
        first.removeIf(name -> name.startsWith("temp-"));

        List<String> second = new ArrayList<>(
                List.of("temp-a", "keep", "temp-b", "done"));
        Iterator<String> it = second.iterator();
        while (it.hasNext()) {
            if (it.next().startsWith("temp-")) {
                it.remove();
            }
        }

        ConcurrentHashMap<String, Integer> eventCount =
                new ConcurrentHashMap<>();
        IntStream.range(0, 200).parallel().forEach(i ->
                eventCount.merge("login", 1, Integer::sum));

        System.out.println("removeIf = " + first);
        System.out.println("iteratorRemove = " + second);
        System.out.println("login = " + eventCount.get("login"));
    }
}
```

```bash
javac FailFastPractice.java
java FailFastPractice
```

```text
removeIf = [keep, done]
iteratorRemove = [keep, done]
login = 200
```

Đáp án bài 1: `set` thay thế phần tử tại index đã có và không đổi cấu trúc `ArrayList`; `add` thêm phần tử và thay đổi cấu trúc. Bài 4: iterator snapshot của `CopyOnWriteArrayList` không thấy phần tử thêm sau thời điểm tạo iterator. Bài 5: không; weakly consistent traversal không phải atomic snapshot của nhiều entry.

## 18. Checklist để review code Collection

- Tôi có đang sửa cấu trúc nguồn `ArrayList`/`HashMap` trong lúc iterator/stream vẫn duyệt không?
- Thay đổi được thực hiện qua iterator hợp lệ, `removeIf` hay một API khác đúng contract?
- Có nhiều thread đọc/ghi cùng collection không? Nếu có, synchronization/ownership nằm ở đâu?
- Tôi có đang dùng `ConcurrentModificationException` như tín hiệu đảm bảo đồng bộ, kiểm thử an toàn hoặc trigger retry không?
- Tôi có nhầm cập nhật phần tử với structural modification hoặc nhầm “không có CME” với “không có data race”?
- `Collections.synchronizedList` đã được khóa khi **duyệt cả iterator**, và mọi writer có tuân thủ cùng wrapper không?
- `ConcurrentHashMap` có phù hợp với yêu cầu visibility per-key nhưng không yêu cầu snapshot toàn map không?
- `CopyOnWriteArrayList` có đáp ứng tỷ lệ đọc/ghi, và tôi có hiểu snapshot chỉ nông?
- Nếu tạo `List.copyOf`/snapshot từ nguồn đang cập nhật, tôi đã bảo vệ **quá trình tạo bản sao** chưa?
- Stream/parallelStream có tránh side effect gây non-interference và shared mutable state?
- Kiểm thử có xác nhận invariant, completion/visibility/atomicity thay vì chỉ mong CME?
- Dữ liệu báo cáo có thật sự cần transaction hoặc consistency mạnh hơn hợp đồng iterator?

## 19. Tài liệu API Oracle hiện hành

- Java SE 26 — `ArrayList`, fail-fast chỉ là best effort: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayList.html
- Java SE 26 — `ConcurrentModificationException`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ConcurrentModificationException.html
- Java SE 26 — `Iterator`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Iterator.html
- Java SE 26 — `Collection`, chính sách synchronization do implementation quyết định: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collection.html
- Java SE 26 — `Collections.synchronizedList` / `synchronizedMap`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html
- Java SE 26 — `ConcurrentHashMap`, weakly consistent iteration: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html
- Java SE 26 — `CopyOnWriteArrayList`, snapshot iterator: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html
- Java SE 26 — `java.util.concurrent`, memory consistency và concurrent collection: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/package-summary.html
- Java SE 26 — `java.util.stream`, non-interference với nguồn: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html

**Ghi nhớ:** fail-fast là **cảnh báo lỗi theo best effort**, không phải một cam kết đồng bộ. Khi có cập nhật đồng thời, hãy xác định mức nhất quán cần thiết và sử dụng đúng collection/khóa/snapshot/transaction. Iterator weakly consistent có thể cho phép duyệt khi cập nhật nhưng không cho snapshot nguyên tử; iterator snapshot giữ cấu trúc cũ nhưng không phải deep copy. Tính đúng đắn đến từ hợp đồng và cách thiết kế, không đến từ việc một lần chạy có ném `ConcurrentModificationException` hay không.