# CopyOnWriteArraySet và tính chất snapshot của iterator khi có ghi trong Java

## 1. Bài toán: đọc Set trong khi thread khác thêm hoặc xóa

Một ứng dụng Java có thể giữ tập hợp các listener, subscriber, policy đang hoạt động hoặc một nhóm giá trị cấu hình. Một thread cần **duyệt tất cả phần tử**, trong khi thread khác có thể **đăng ký mới hoặc gỡ bỏ** một phần tử.

Nếu dùng `HashSet` và sửa đồng thời không có đồng bộ, chương trình không thread-safe. Nếu duyệt một `HashSet`/`ArrayList` thông thường mà có thay đổi cấu trúc sau khi iterator được tạo, iterator **có thể** ném `ConcurrentModificationException` theo cơ chế fail-fast. Đó không phải công cụ đồng bộ và không phải cách đáng tin để phát hiện mọi race.

Java cung cấp `java.util.concurrent.CopyOnWriteArraySet<E>` cho những tình huống **đọc/duyệt thường xuyên, ghi ít**, nơi caller chấp nhận rằng một lượt duyệt nhìn thấy **ảnh chụp tập phần tử tại thời điểm tạo iterator**, thay vì những thay đổi mới nhất.

Ý tưởng:

```text
Thời điểm t0: Set hiện tại = [A, B, C]
                       |
               reader tạo iterator I
                       |
                       v
          I giữ tham chiếu tới snapshot [A, B, C]

Thời điểm t1: writer add(D)
             Set hiện tại = [A, B, C, D]
             I vẫn duyệt    [A, B, C]

Thời điểm t2: writer remove(B)
             Set hiện tại = [A, C, D]
             I vẫn duyệt    [A, B, C]

Thời điểm t3: reader tạo iterator J
             J duyệt        [A, C, D]
```

**Điểm cốt lõi:** iterator được tạo ở t0 không phải “kết quả truy vấn sống” tự thay đổi ở t1, t2. Nó là **snapshot iterator**.

Bài này thuộc **Concurrent Collections** của **Java concurrency nói chung**, sử dụng API Java 17+, không phụ thuộc framework.

## 2. CopyOnWriteArraySet là gì?

`CopyOnWriteArraySet<E>` là một tập hợp `Set` được triển khai dựa trên `CopyOnWriteArrayList`.

Các đặc điểm chính:

1. **Không chứa hai phần tử bằng nhau theo `equals()`.** Nếu thêm một phần tử bằng phần tử đã có, `add` trả `false`.
2. **Thread-safe** cho các thao tác công khai của collection khi nhiều thread thêm, xóa, đọc hoặc duyệt theo hợp đồng của lớp.
3. Các thao tác ghi làm thay đổi tập phần tử thường phải tạo **mảng backing mới** (copy-on-write), thay vì sửa mảng backing mà iterator cũ đang tham chiếu.
4. Iterator giữ snapshot cấu trúc tập phần tử **tại thời điểm iterator được tạo**. Những lần ghi sau không đổi danh sách phần tử mà iterator cũ sẽ duyệt.
5. Iterator không hỗ trợ `remove()`, `set()` hoặc `add()` như một số kiểu iterator/list iterator khác; cố gọi thao tác sửa qua iterator có thể ném `UnsupportedOperationException`.
6. `CopyOnWriteArraySet` **cho phép phần tử `null`**, khác `ConcurrentHashMap.newKeySet()`.
7. Không cung cấp thứ tự sắp xếp theo comparator. Các phần tử được duyệt theo thứ tự lưu trong backing list — thường phản ánh thứ tự thêm phần tử — **không phải theo thứ tự từ điển hay hash**.
8. Vì phải tìm phần tử bằng cách so sánh tuyến tính, `contains`, tìm phần tử trùng và nhiều phép Set có chi phí phụ thuộc số phần tử; không nên coi đây là hash set có tra cứu `O(1)`.

Nên hiểu đúng tên:

- **Copy:** thao tác ghi cần copy backing array khi thực sự thay đổi nội dung.
- **On write:** phép đọc và việc tạo iterator thường không cần copy toàn bộ mảng.
- **ArraySet:** đặc tính Set được duy trì trên một cấu trúc giống mảng/list, không phải bảng băm.

Không có nghĩa mỗi lời gọi `add` chắc chắn tạo mảng mới: ví dụ thêm phần tử **đã tồn tại** không cần tạo một bản sao chứa dữ liệu y hệt. Trọng tâm là **khi nội dung tập thay đổi, thay mảng backing thay vì sửa mảng cũ đang được các iterator tham chiếu**.

## 3. Cơ chế mảng backing được công bố an toàn

Một cách hình dung cấp khái niệm:

```text
Reader I ----> backing array v1: [A, B]

Writer add(C):
  tạo mảng mới v2: [A, B, C]
  công bố v2 là backing array hiện hành

Reader I ----> v1: [A, B]           (không đổi)
Reader J ----> v2: [A, B, C]        (được tạo sau update)
```

Trong `CopyOnWriteArrayList` bên dưới, mảng hiện hành được công bố qua cơ chế đồng bộ/visibility thích hợp; các phép ghi được phối hợp để không làm mất thay đổi cấu trúc. Iterator lấy tham chiếu tới **mảng hiện hành tại lúc khởi tạo** và giữ tham chiếu đó cho đến khi iterator không còn được sử dụng.

Hệ quả:

- Reader có thể duyệt mảng snapshot mà không cần giữ một monitor khóa suốt cả vòng lặp.
- Writer có thể thay đổi collection hiện hành mà không chỉnh sửa mảng snapshot của reader.
- Iterator cũ **không cần restart** và **không ném `ConcurrentModificationException` chỉ vì Set được sửa**.
- Sau khi writer công bố mảng mới, iterator **được tạo sau đó** có thể nhìn thấy tập mới theo hợp đồng của collection.
- Mảng cũ vẫn có thể được giữ trong bộ nhớ khi iterator cũ còn tham chiếu tới nó.

Đây không phải cơ chế “copy cho từng reader”. Một iterator mới thường chỉ **chụp tham chiếu tới mảng hiện hành**, nên tạo iterator/duyệt nhanh khi không có nhiều ghi. Chi phí copy chủ yếu xuất hiện ở phía **ghi làm thay đổi cấu trúc**.

## 4. Ví dụ 1: snapshot được tạo trước khi ghi

Tạo tệp `CopyOnWriteSnapshotBasicsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;

public class CopyOnWriteSnapshotBasicsDemo {
    static List<String> collect(Iterator<String> iterator) {
        List<String> values = new ArrayList<>();
        iterator.forEachRemaining(values::add);
        return values;
    }

    public static void main(String[] args) {
        CopyOnWriteArraySet<String> set =
                new CopyOnWriteArraySet<>(
                        List.of("A", "B", "C"));

        Iterator<String> oldIterator = set.iterator();

        set.add("D");
        set.remove("B");
        set.add("E");

        System.out.println("old snapshot="
                + collect(oldIterator));
        System.out.println("current="
                + new ArrayList<>(set));
        System.out.println("new snapshot="
                + collect(set.iterator()));
    }
}
```

Biên dịch/chạy trên **JDK 17+**:

```bash
javac CopyOnWriteSnapshotBasicsDemo.java
java CopyOnWriteSnapshotBasicsDemo
```

Kết quả:

```text
old snapshot=[A, B, C]
current=[A, C, D, E]
new snapshot=[A, C, D, E]
```

Tại thời điểm gọi `set.iterator()` đầu tiên, tập có A, B, C. Sau đó:

- `add("D")` công bố tập có D.
- `remove("B")` gỡ B khỏi tập hiện hành.
- `add("E")` thêm E.
- Nhưng `oldIterator` vẫn giữ snapshot của tập cũ nên **vẫn trả B**, đồng thời **không trả D hay E**.
- Iterator mới được tạo sau các thay đổi duyệt tập hiện tại.

**Một hiểu nhầm:** gọi `oldIterator.next()` **lần đầu sau khi writer đã ghi** không có nghĩa nó sẽ đọc Set hiện hành. Snapshot được cố định khi gọi **`iterator()`**, không phải khi gọi `next()`.

## 5. Ví dụ 2: thật sự có một writer thread

Một ví dụ một thread có thể minh họa hợp đồng, nhưng để hiểu đúng concurrency, hãy tạo iterator **trước khi một thread khác cập nhật**, rồi dùng `Thread.join()` để biết writer đã hoàn tất.

Tạo tệp `ConcurrentSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;
import java.util.concurrent.CountDownLatch;

public class ConcurrentSnapshotDemo {
    static List<String> readAll(Iterator<String> iterator) {
        List<String> result = new ArrayList<>();
        iterator.forEachRemaining(result::add);
        return result;
    }

    public static void main(String[] args) throws InterruptedException {
        CopyOnWriteArraySet<String> set =
                new CopyOnWriteArraySet<>(
                        List.of("alpha", "beta"));

        Iterator<String> beforeWrite = set.iterator();
        CountDownLatch start = new CountDownLatch(1);

        Thread writer = new Thread(() -> {
            try {
                start.await();
                set.add("gamma");
                set.remove("alpha");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "writer");

        writer.start();
        start.countDown();
        writer.join();

        System.out.println("before write="
                + readAll(beforeWrite));
        System.out.println("after write="
                + readAll(set.iterator()));
    }
}
```

```bash
javac ConcurrentSnapshotDemo.java
java ConcurrentSnapshotDemo
```

Kết quả khi không có interrupt ngoài ý muốn:

```text
before write=[alpha, beta]
after write=[beta, gamma]
```

Điểm quan trọng:

- Main tạo `beforeWrite` trước khi writer bắt đầu `add/remove`.
- Writer thay collection; main đợi `join()` rồi quan sát tập hiện hành.
- Iterator cũ vẫn trả phần tử của snapshot đã giữ.
- Hai lượt duyệt là hai **phiên bản có chủ đích**, không phải kết quả ngẫu nhiên phụ thuộc lịch chạy.

Nếu bỏ `writer.join()` và tạo iterator mới đồng thời với các cập nhật, iterator mới có thể nhìn thấy phiên bản trước, giữa hoặc sau chuỗi ghi, tùy thời điểm tạo. **Mỗi iterator vẫn nhất quán với đúng một phiên bản của backing array**, nhưng không được kỳ vọng nó luôn là phiên bản mới nhất khi nhiều writer đang tiếp tục hoạt động.

## 6. Iterator snapshot khác iterator fail-fast như thế nào?

Ba nhóm hành vi dễ nhầm:

| Kiểu collection/iterator | Khi collection bị sửa sau khi tạo iterator | Điều phải lưu ý |
| --- | --- | --- |
| `HashSet`, `ArrayList` thông thường | Iterator thường fail-fast và **có thể** ném `ConcurrentModificationException` | Fail-fast là best-effort, không làm collection thread-safe |
| `CopyOnWriteArraySet` | Iterator duyệt **snapshot cố định**; không bị thay đổi bởi ghi sau đó | Có thể thấy phần tử đã bị gỡ, không thấy phần tử mới |
| `ConcurrentHashMap.newKeySet()` | Iterator **weakly consistent**; có thể thấy một số thay đổi đồng thời | Không phải snapshot bất biến của một thời điểm |
| `Collections.synchronizedSet(...)` | Cần **đồng bộ bên ngoài** khi duyệt iterator theo tài liệu API | Không tự cho iterator snapshot không cần khóa |

**Không dùng `ConcurrentModificationException` để điều khiển chương trình.** Một iterator fail-fast phát hiện sửa đổi ở mức best-effort; sự vắng mặt của exception không chứng minh code đọc/ghi đồng thời là an toàn.

### Snapshot vs weakly consistent

Snapshot iterator của `CopyOnWriteArraySet` có tập phần tử rõ tại **lúc tạo iterator**. Nếu writer thêm X sau thời điểm ấy, snapshot cũ không có X.

Iterator weakly consistent như iterator của một số concurrent collection khác có thể phản ánh **một phần** thay đổi khi duyệt. Nó hữu ích cho các workload có nhiều writer, nhưng không đưa ra cam kết “chính xác tất cả phần tử tại thời điểm iterator khởi tạo”.

Hãy chọn semantics dựa trên nhu cầu của caller:

- Muốn **mỗi lượt xử lý có danh sách đối tượng cố định** → snapshot iterator.
- Muốn xử lý một lượng dữ liệu lớn, ghi thường xuyên, chấp nhận iteration không phản ánh toàn cục tức thời → concurrent key set / collection thích hợp.
- Muốn snapshot thật sự của nhiều cấu trúc liên quan → có thể cần một giao thức đồng bộ/đóng băng dữ liệu riêng; không phải chỉ chọn iterator bất kỳ.

## 7. Iterator cũ không cho phép `remove()`

Điểm khác một số iterator của collection thường: iterator của `CopyOnWriteArraySet` **không hỗ trợ chỉnh collection thông qua iterator**. Nếu muốn xóa một phần tử, gọi phương thức trên **Set**, không gọi `iterator.remove()`.

Tạo tệp `SnapshotIteratorRemoveDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;

public class SnapshotIteratorRemoveDemo {
    public static void main(String[] args) {
        CopyOnWriteArraySet<String> set =
                new CopyOnWriteArraySet<>(List.of("one", "two"));

        Iterator<String> iterator = set.iterator();
        System.out.println("first=" + iterator.next());

        try {
            iterator.remove();
        } catch (UnsupportedOperationException e) {
            System.out.println("iterator.remove unsupported=true");
        }

        System.out.println("after iterator.remove="
                + new ArrayList<>(set));

        set.remove("one");
        System.out.println("after set.remove="
                + new ArrayList<>(set));
    }
}
```

```bash
javac SnapshotIteratorRemoveDemo.java
java SnapshotIteratorRemoveDemo
```

Output:

```text
first=one
iterator.remove unsupported=true
after iterator.remove=[one, two]
after set.remove=[two]
```

`iterator.remove()` ném `UnsupportedOperationException`. Trong khi đó `set.remove("one")` là thao tác hợp lệ, có thể tạo mảng backing mới. Iterator cũ không bị thay đổi vì việc xóa qua Set này.

Trong những trường hợp cần lọc nhiều phần tử, có thể dùng phương thức hỗ trợ của collection như `removeIf` hoặc một chiến lược thay toàn bộ snapshot. Nhưng hãy cân nhắc chi phí copy/write và cách ứng dụng muốn điều phối thay đổi, thay vì gọi `remove` từng phần tử trên một Set lớn có nhiều writer.

## 8. Snapshot giữ cấu trúc tập phần tử, không deep-copy đối tượng

Đây là một ranh giới rất quan trọng.

`CopyOnWriteArraySet` snapshot **mảng tham chiếu phần tử**. Nó không tự clone từng object. Nếu một phần tử là mutable object, cả iterator cũ và collection hiện hành vẫn có thể giữ **cùng tham chiếu** đến object đó.

```text
snapshot array v1: [ reference -> Item(id=1, name="old") ]
current  array v2: [ reference -> Item(id=1, name="old"), Item2 ]

Nếu Item.name bị sửa thành "new":
snapshot v1 vẫn chứa Item(id=1), nhưng quan sát Item.name có thể là "new".
```

Vì vậy:

- Snapshot bảo vệ **thành viên của Set ở một thời điểm**.
- Snapshot **không bảo vệ trạng thái mutable bên trong mỗi thành viên**.
- Nếu object được sửa từ thread khác mà không có đồng bộ, vẫn có thể có **data race/visibility problem** ở fields của object đó.
- Muốn view thực sự bất biến, ưu tiên element immutable hoặc bản sao sâu phù hợp, và công bố chúng an toàn.

### Ví dụ 3: mutable element thay đổi cả trong snapshot cũ

Tạo tệp `MutableElementSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;

public class MutableElementSnapshotDemo {
    static final class Item {
        final int id;
        String name;

        Item(int id, String name) {
            this.id = id;
            this.name = name;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Item item && id == item.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }

        @Override
        public String toString() {
            return id + ":" + name;
        }
    }

    static List<String> describe(Iterator<Item> iterator) {
        List<String> result = new ArrayList<>();
        iterator.forEachRemaining(
                item -> result.add(item.toString()));
        return result;
    }

    public static void main(String[] args) {
        Item first = new Item(1, "old");
        CopyOnWriteArraySet<Item> set =
                new CopyOnWriteArraySet<>();
        set.add(first);

        Iterator<Item> snapshot = set.iterator();

        first.name = "new";
        set.add(new Item(2, "second"));

        System.out.println("old snapshot=" + describe(snapshot));
        System.out.println("current=" + describe(set.iterator()));
    }
}
```

```bash
javac MutableElementSnapshotDemo.java
java MutableElementSnapshotDemo
```

Output:

```text
old snapshot=[1:new]
current=[1:new, 2:second]
```

Ví dụ này sửa field `name` **tuần tự trong một thread**, nên không có race về visibility. Nó cho thấy snapshot cũ vẫn giữ cùng object `first`, vì vậy `name` có thể đổi từ `old` thành `new` ngay trong lúc membership snapshot không đổi.

Ở hệ thống nhiều thread, nếu thật sự cần sửa name đồng thời, phải có `volatile`, lock, immutable replacement hoặc cơ chế đồng bộ phù hợp. **Không lấy copy-on-write của Set làm bảo đảm an toàn cho mọi trường của Item.**

## 9. Tính duy nhất theo equals(), không phải theo hash bucket

`CopyOnWriteArraySet` tuân thủ semantics của `Set`: các phần tử trùng nhau theo `equals()` không được thêm lần thứ hai. Không giống `HashSet`, nó không dựa vào bảng băm để thực hiện mọi lookup, mà kiểm tra phần tử trong backing array/list.

Do đó:

- `new String("Java")` và một `String` có cùng nội dung đã lưu thường được coi là phần tử trùng.
- Thứ tự phần tử không phải thứ tự của `hashCode()`.
- `contains(element)` có chi phí tuyến tính theo số phần tử trong trường hợp chung.
- Nếu `equals()` đắt, các lần add/contains cũng có thể đắt.
- Nếu `equals()` không ổn định vì các trường mutable bị sửa, logic duy nhất của Set có thể không còn đúng như mong muốn.

### Ví dụ 4: duplicate, null và thứ tự duyệt

Tạo tệp `CopyOnWriteSetEqualityDemo.java`:

```java
import java.util.ArrayList;
import java.util.concurrent.CopyOnWriteArraySet;

public class CopyOnWriteSetEqualityDemo {
    public static void main(String[] args) {
        CopyOnWriteArraySet<String> set =
                new CopyOnWriteArraySet<>();

        boolean first = set.add("apple");
        boolean duplicate = set.add(new String("apple"));
        boolean nullFirst = set.add(null);
        boolean nullAgain = set.add(null);

        System.out.println("first=" + first);
        System.out.println("duplicate=" + duplicate);
        System.out.println("null first=" + nullFirst);
        System.out.println("null again=" + nullAgain);
        System.out.println("elements=" + new ArrayList<>(set));
    }
}
```

```bash
javac CopyOnWriteSetEqualityDemo.java
java CopyOnWriteSetEqualityDemo
```

Output:

```text
first=true
duplicate=false
null first=true
null again=false
elements=[apple, null]
```

Hai `String` khác instance nhưng bằng nhau theo `equals()`, nên lần thêm thứ hai trả false. `null` được cho phép **một lần** trong `CopyOnWriteArraySet`. Điều này khác `ConcurrentHashMap.newKeySet()`, vì Map bên dưới không cho key null.

Không suy ra rằng mọi concurrent Set đều cho phép null. Luôn xem **contract của implementation được chọn**, đặc biệt khi chuyển từ `CopyOnWriteArraySet` sang một concurrent set khác.

## 10. Mutation của phần tử ảnh hưởng tới equals()

Một loại lỗi khó hơn deep-snapshot issue: khi một phần tử `Item` sử dụng **trường mutable trong `equals()`**, việc sửa trường đó có thể làm thay đổi quan hệ bằng nhau đối với các phần tử khác.

Ví dụ lớp có `equals()` dựa vào `name`, đưa `Item("A")` vào Set rồi sửa `name` thành `"B"`:

- Kết quả `contains(new Item("A"))` có thể chuyển từ true thành false.
- `contains(new Item("B"))` có thể chuyển từ false thành true.
- Nếu đã có một phần tử khác `Item("B")`, Set có thể rơi vào trạng thái có hai object hiện **bằng nhau** về logic dù được thêm hợp lệ ở thời điểm khác nhau.
- Nếu thread khác sửa trường đó không đồng bộ, kiểm tra equality còn có data race.

**Khuyến nghị:** dùng phần tử có định danh/equality **ổn định** khi nằm trong Set. Với record chỉ chứa `String`, primitive hoặc value object bất biến, việc giữ ngữ nghĩa `equals()` ổn định thường đơn giản hơn.

Cẩn trọng với record chứa `List`/array mutable: record không tự bảo đảm **deep immutability** của toàn bộ object graph. Nếu element thay đổi về nội dung, snapshot chỉ còn là ảnh chụp **tham chiếu**.

## 11. Ví dụ thực tế: danh sách listener/event subscriber

Một tập listener nhỏ, ít đăng ký/hủy đăng ký nhưng được duyệt rất nhiều lần là tình huống phù hợp với copy-on-write.

Giả sử một hệ thống nhận sự kiện và mỗi lần nhận cần gọi những listener **thuộc snapshot của lượt dispatch đó**. Nếu listener A gỡ B và thêm C ngay trong lúc dispatch, lựa chọn semantics rõ ràng là:

- Lượt hiện tại vẫn xử lý A, B theo snapshot cũ.
- C chỉ xuất hiện ở **lượt dispatch kế tiếp**.
- Việc B được xóa khỏi Set **không hủy callback đang nằm trong snapshot**.

### Ví dụ 5: thay đổi Set ngay trong một vòng duyệt

Tạo tệp `ListenerSnapshotDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArraySet;

public class ListenerSnapshotDemo {
    public static void main(String[] args) {
        CopyOnWriteArraySet<String> listeners =
                new CopyOnWriteArraySet<>(List.of("A", "B"));

        List<String> firstRound = new ArrayList<>();

        for (String listener : listeners) {
            firstRound.add(listener);
            if (listener.equals("A")) {
                listeners.remove("B");
                listeners.add("C");
            }
        }

        List<String> secondRound = new ArrayList<>();
        for (String listener : listeners) {
            secondRound.add(listener);
        }

        System.out.println("first round=" + firstRound);
        System.out.println("second round=" + secondRound);
    }
}
```

```bash
javac ListenerSnapshotDemo.java
java ListenerSnapshotDemo
```

Output:

```text
first round=[A, B]
second round=[A, C]
```

Vòng `for-each` đầu tiên tạo iterator một lần khi bắt đầu. Dù code trong vòng xóa B và thêm C, iterator của vòng này vẫn duyệt snapshot `[A, B]`. Vòng thứ hai lấy snapshot mới nên duyệt `[A, C]`.

Đây là một lợi thế lớn khi listener có quyền đăng ký/hủy đăng ký trong callback mà bạn không muốn giữ khóa trong suốt quá trình gọi người đăng ký.

### Giới hạn của pattern listener

- `unsubscribe(B)` **không đảm bảo B không còn được gọi ở lượt dispatch đã bắt đầu**.
- Nếu phải đảm bảo “xóa xong thì chắc chắn không có callback B nào đang chạy”, cần thêm giao thức quản lý **in-flight callbacks**, state/cancel/acknowledgment. Copy-on-write Set riêng lẻ không cung cấp cam kết đó.
- Nếu callback ném exception, phải quyết định có tiếp tục các listener khác không; Set không tự xử lý exception.
- Một callback chạy lâu làm vòng dispatch chậm; Set chỉ giải quyết cách **duyệt và cập nhật membership**, không lên lịch callback.
- Nếu listener giữ resource ngoài JVM (socket, file), việc xóa khỏi Set không tự đóng resource đó.

## 12. Snapshot iterator và điểm nhìn “mới nhất”

Một iterator cung cấp **tập phần tử đã tồn tại tại thời điểm tạo**. Nó không phải API lấy “tập mới nhất bất kể writer đang làm gì”.

Có hai trường hợp khác nhau:

**A. Writer đã hoàn tất và được phối hợp rõ:** nếu thread A thực hiện các update, thread B đợi A bằng `join()`/latch rồi mới gọi `set.iterator()`, B lấy snapshot của tập hiện hành **sau chuỗi update đó** (giả sử không có writer thứ ba cạnh tranh).

**B. Reader tạo iterator đồng thời với writer:** thứ tự giữa việc chụp tham chiếu mảng và việc công bố mảng mới quyết định iterator nhìn thấy phiên bản trước hay sau. Không được dự đoán dựa trên `Thread.sleep(...)` hoặc tên thread.

**C. Nhiều writer liên tục:** iterator tạo tại một điểm có thể nhìn thấy một phiên bản trung gian giữa các thao tác add/remove riêng rẽ. Ví dụ cập nhật A rồi B không trở thành một giao dịch nguyên tử chung chỉ vì sử dụng CopyOnWriteArraySet.

Lời khuyên: nếu nhiều thay đổi phải xuất hiện **cùng một lúc theo invariant nghiệp vụ**, có thể xây một immutable snapshot toàn bộ mới và công bố nó qua một `AtomicReference` hoặc áp dụng một giao thức khóa/transaction phù hợp. Nhiều lời gọi `set.add` / `set.remove` liên tiếp vẫn là **nhiều** thay đổi riêng.

## 13. Độ phức tạp thời gian và bộ nhớ

Một bảng chi phí xấp xỉ với tập có `n` phần tử:

| Thao tác | Chi phí thường gặp | Lý do |
| --- | --- | --- |
| `iterator()` | `O(1)` để nhận tham chiếu snapshot | Không copy toàn mảng khi chỉ tạo iterator |
| Duyệt toàn bộ `n` phần tử | `O(n)` | Đi qua từng phần tử của snapshot |
| `contains(x)` | `O(n)` | Tìm tuyến tính bằng equality |
| `add(x)` khi chưa có | `O(n)` | Kiểm tra trùng và tạo/copy backing array mới |
| `add(x)` khi đã có | `O(n)` worst-case cho tìm kiếm | Không cần thêm/copy để cài phần tử mới |
| `remove(x)` khi có | `O(n)` | Tìm phần tử rồi tạo array mới thiếu phần tử |
| `size()` | Thường `O(1)` | Dựa vào độ dài mảng hiện hành |
| Mỗi iterator còn sống | Giữ tham chiếu tới mảng snapshot | Có thể trì hoãn GC của các mảng cũ |

Bảng mô tả hình thái cơ bản, không phải cam kết cứng về từng nano giây hoặc mọi implementation/JDK. Các phép toán bulk và tối ưu nội bộ có thể có chi phí khác.

**Về bộ nhớ:** nếu Set có `n` tham chiếu, một lần thay đổi membership thường cần tạo backing array `O(n)`. Nếu nhiều iterator cũ còn sống, nhiều phiên bản array có thể cùng tồn tại trong heap. Các element object có thể được nhiều array version tham chiếu, nhưng nếu một element đã bị xóa khỏi Set hiện hành mà vẫn nằm trong snapshot cũ, nó **vẫn được giữ sống** cho tới khi snapshot/iterator không còn tham chiếu.

Không nhầm “copy mảng tham chiếu” với “clone tất cả element object”: chi phí cấp phát array là đáng kể nhưng không phải tạo bản sao sâu của mọi object.

## 14. Khi ghi thường xuyên, chi phí copy tích lũy

Giả sử có `n = 100_000` phần tử và mỗi giây thêm/xóa hàng chục nghìn phần tử. Với copy-on-write:

- Mỗi thay đổi thành viên có thể copy một mảng hàng chục/hàng trăm nghìn tham chiếu.
- Nhiều phiên bản mảng tạm làm tăng lượng allocation và áp lực GC.
- Writer phải phối hợp trong cơ chế nội bộ, không phải các thao tác ghi nào cũng chạy đồng thời độc lập.
- Nếu ghi liên tục, lợi ích reader không cần khóa có thể không bù chi phí writer.

Đây là lý do `CopyOnWriteArraySet` thường phù hợp:

- Ít phần tử hoặc kích thước vừa phải.
- **Đọc/duyệt nhiều, ghi rất ít**.
- Mỗi lượt duyệt muốn membership ổn định.
- Ưu tiên tính đơn giản của iteration và chấp nhận eventual visibility theo lượt snapshot.

Và thường **không phù hợp**:

- Cập nhật membership liên tục với tần suất cao.
- Set rất lớn và nhiều writer.
- Bài toán cần độ trễ thấp nhất cho mỗi lần add/remove.
- Workload cần một “live view” phản ánh phần tử mới ngay trong lượt duyệt hiện tại.

Không nên kết luận chỉ từ tên “concurrent” rằng collection này phù hợp cho mọi tình huống nhiều thread.

## 15. So sánh với ConcurrentHashMap.newKeySet()

Một lựa chọn khác là:

```java
Set<String> names = ConcurrentHashMap.newKeySet();
```

Đây là đoạn minh họa, cần import `java.util.Set` và `java.util.concurrent.ConcurrentHashMap`.

### Khác biệt chính

| Tiêu chí | `CopyOnWriteArraySet` | `ConcurrentHashMap.newKeySet()` |
| --- | --- | --- |
| Cấu trúc nền | Mảng copy-on-write | Bảng băm concurrent |
| Tìm kiếm `contains` | Tuyến tính theo số phần tử | Thường hiệu quả gần hằng số, phụ thuộc phân bố hash |
| Thêm/xóa thường xuyên | Tốn copy mảng, không lý tưởng cho n lớn | Thường thích hợp hơn cho workload update nhiều |
| Iterator | **Snapshot**, cố định membership tại lúc tạo | **Weakly consistent**, có thể phản ánh một số thay đổi |
| Thứ tự duyệt | Theo backing list/thứ tự thêm trong tình huống thông thường | Không đảm bảo thứ tự |
| `null` | **Cho phép** một phần tử null | **Không cho phép** null |
| Chi phí đọc/duyệt lặp lại | Không cần khóa dài của reader; snapshot ổn định | Iterator ít overhead của full copying, nhưng semantics khác |
| Phù hợp điển hình | Listener/config nhỏ, đọc nhiều ghi ít | Set nhiều key, truy cập/ghi đồng thời với số lượng lớn |

Không nói `ConcurrentHashMap.newKeySet()` “luôn nhanh hơn”. Với Set rất nhỏ, việc phải hash/đi qua cấu trúc khác có thể không mang lợi ích rõ; và nếu bắt buộc có snapshot cố định, dùng weakly consistent iterator có thể đòi thêm cơ chế snapshot riêng.

Vấn đề không chỉ hiệu năng mà là **ngữ nghĩa lặp (iteration semantics)**: cần thấy tập ở thời điểm bắt đầu hay một tập có thể phản ánh cập nhật đồng thời?

## 16. So sánh với Collections.synchronizedSet()

Có thể tạo:

```java
Set<String> set =
        Collections.synchronizedSet(new HashSet<>());
```

Đây là đoạn minh họa, cần import `java.util.*`. Wrapper cung cấp đồng bộ cho nhiều phép toán của Set; tuy nhiên **iterator không tự có snapshot semantics**. Tài liệu Java yêu cầu đồng bộ thủ công khi duyệt iterator của synchronized collection:

```java
synchronized (set) {
    for (String value : set) {
        use(value);
    }
}
```

Đây là đoạn minh họa, `use` là hàm ứng dụng. Việc dùng monitor của `set` suốt vòng duyệt chỉ đúng khi **mọi đường sửa qua cùng wrapper và cùng giao thức đồng bộ**. Nếu caller giữ iterator nhưng rời synchronized block sớm, hoặc có code bypass wrapper để sửa HashSet gốc, bảo đảm bị phá.

Khác biệt vận hành:

- `synchronizedSet` có thể khiến writer **đợi đến khi vòng duyệt dài hoàn thành** vì reader giữ monitor.
- `CopyOnWriteArraySet` cho phép writer thay backing array trong khi reader vẫn duyệt snapshot cũ, không cần khóa suốt lượt duyệt.
- `synchronizedSet` thường tránh copy toàn mảng cho từng lần add/remove, nhưng có overhead locking.
- Cả hai có thể đúng; hãy chọn theo tần suất đọc/ghi, thời gian duyệt, yêu cầu snapshot và mức contention.

Nếu `use(value)` gọi I/O chậm bên trong synchronized block, writer có thể chờ lâu. Đây là một lý do mẫu listener thường thích snapshot iterator.

## 17. So sánh với ConcurrentSkipListSet

`ConcurrentSkipListSet` cung cấp một concurrent sorted/navigable set, thường hữu ích khi ứng dụng yêu cầu:

- Duyệt phần tử **theo comparator/thứ tự tự nhiên**.
- Tìm phần tử gần nhất (`lower`, `higher`, `floor`, `ceiling`).
- Xử lý các range view có thứ tự.

Nó dùng cấu trúc skip list đồng thời, không phải backing array copy-on-write. Iterator của nó thuộc loại **weakly consistent**, khác snapshot iterator của `CopyOnWriteArraySet`; thông thường không cho phép phần tử null.

Nếu bài toán cần “danh sách listener theo thứ tự đăng ký” và ít thay đổi, `CopyOnWriteArraySet` có thể tiện. Nếu bài toán cần “tất cả key tăng dần và thao tác range” dưới concurrent updates, `ConcurrentSkipListSet` thường phù hợp hơn.

Đừng chọn `CopyOnWriteArraySet` rồi kỳ vọng `sort()` hay comparator có tác dụng tự động lên Set — nó không phải `SortedSet`.

## 18. Quy tắc về `add`, `remove` và return value

`CopyOnWriteArraySet` vẫn tuân theo các hợp đồng `Set` cơ bản:

- `add(e)` trả `true` nếu Set thay đổi vì thêm phần tử chưa có.
- `add(e)` trả `false` khi đã có phần tử bằng e.
- `remove(e)` trả `true` nếu có và xóa được phần tử.
- `remove(e)` trả `false` nếu không có phần tử phù hợp.
- `contains(e)` kiểm tra membership tại một thời điểm của collection.
- `size()` cho kích thước tập hiện hành lúc gọi.

Có thể dùng return value của `add` để tránh thực hiện side effect ở caller thua **trong một cuộc đua đăng ký**:

```java
if (listeners.add(listener)) {
    reportNewRegistration(listener);
}
```

Đây là đoạn minh họa. Nhưng hãy hiểu giới hạn: việc `add` và việc báo cáo là **hai thao tác riêng**. Nếu thread khác `remove`/`add` cùng listener ở giữa, hoặc báo cáo thất bại, không thể suy ra exactly-once side effect trong mọi tình huống.

Nếu nghiệp vụ cần exactly-once registration ngoài JVM, hãy định nghĩa ID, transaction/idempotency và protocol phù hợp; copy-on-write chỉ xử lý membership trong một Set tại JVM.

## 19. Mảng snapshot cũ có thể giữ object đã bị xóa

Điểm thường bị bỏ qua ở production là **retained memory**. Giả sử:

1. Có Set chứa 10.000 listener object.
2. Thread A tạo iterator rồi giữ nó trong một tác vụ chờ rất lâu.
3. Thread B gỡ 9.000 listener.
4. Set hiện hành chỉ còn 1.000 listener, nhưng iterator của A vẫn giữ **mảng snapshot với 10.000 tham chiếu cũ**.
5. Các listener đã gỡ có thể **chưa được GC** nếu còn được snapshot cũ giữ và không có tham chiếu khác.

Vì vậy:

- Tránh giữ iterator/snapshot quá lâu mà không cần thiết.
- Tránh cho iterator escape khỏi scope/lifecycle dự kiến khi nó chứa tham chiếu tới object lớn.
- Không mặc định `set.remove(e)` đồng nghĩa object `e` lập tức có thể thu gom.
- Nếu có rất nhiều iterator sống đồng thời cùng những lần ghi lớn, allocation và retained heap có thể tăng.

Đây là tradeoff của snapshot semantics. Nó không phải memory leak vô hạn trong mọi trường hợp; khi các iterator cũ không còn được tham chiếu, mảng cũ và element đã bị gỡ có thể được GC theo các điều kiện còn lại.

## 20. Kết hợp CopyOnWriteArraySet với immutable element

Một pattern đơn giản và đáng tin:

```java
record Subscriber(String id, String channel) {}
CopyOnWriteArraySet<Subscriber> subscribers =
        new CopyOnWriteArraySet<>();
```

Đây là đoạn minh họa. `Subscriber` chứa hai `String` bất biến, record component là final, nên từng element không bị sửa tại chỗ.

Khi muốn đổi channel:

```java
Subscriber oldValue = new Subscriber("u-1", "news");
Subscriber newValue = new Subscriber("u-1", "alerts");

subscribers.remove(oldValue);
subscribers.add(newValue);
```

Đây là đoạn minh họa **không phải transaction**: giữa remove và add, observer có thể thấy tạm thời không có old/new, còn snapshot cũ vẫn giữ old. Nếu membership phải chuyển **nguyên tử qua nhiều bước**, không nên kỳ vọng hai lời gọi Set là một thao tác duy nhất; có thể thay cả immutable aggregate qua một `AtomicReference` hoặc dùng cơ chế điều phối khác.

**Bẫy về equals:** record `Subscriber(id, channel)` so sánh cả id và channel. Nếu nghiệp vụ xem **id là định danh duy nhất**, hai record cùng id nhưng khác channel không bằng nhau, nên Set có thể chứa cả hai. Cần chọn mô hình định danh phù hợp: custom equals/hashCode chỉ theo id, Map theo id, hoặc một value aggregate mà key là id.

Đây là một lỗi semantic, không phải race condition: collection chỉ có thể giữ tính duy nhất theo **equals() mà element định nghĩa**, không theo quy tắc nghiệp vụ nằm ngoài equals.

## 21. Thread safety và Java Memory Model

`CopyOnWriteArraySet` thuộc `java.util.concurrent` và sử dụng cơ chế công bố backing array an toàn. Các hành động trong thread trước khi đặt một object vào concurrent collection có quan hệ visibility phù hợp đối với thread khác sau khi lấy/quan sát object đó qua collection, theo hợp đồng memory consistency của các concurrent collection.

Thực tế:

- Một thread xây xong phần tử rồi `set.add(item)`.
- Thread khác tạo iterator mới, lấy đúng `item` đó từ snapshot.
- Thread đọc có cơ sở visibility để thấy những state đã khởi tạo **trước khi phần tử được công bố**.

**Không suy rộng thành bảo đảm deep immutable**:

- Nếu writer tiếp tục sửa `item.name` sau khi đã add, phải có đồng bộ riêng cho state mutable.
- Nếu một phần tử chứa `List` mutable, việc copy array của Set không copy cấu trúc list bên trong.
- Nếu một method đọc `set.contains(x)` rồi dùng state mutable của `x` không đồng bộ, Map/Set thread-safe không bảo vệ phép đọc fields đó.
- Một iterator cũ vẫn thấy member của snapshot cũ ngay cả khi Set hiện hành đã remove member.
- Các lần `add`/`remove` riêng biệt không tạo transaction nhiều phần tử.

Nên ưu tiên element immutable và thiết kế rõ ai sở hữu việc thay đổi membership.

## 22. “Snapshot” có phải snapshot của toàn ứng dụng không?

Không. Nó chỉ là snapshot cấu trúc của **chính CopyOnWriteArraySet đó**.

Ví dụ một service có:

```text
CopyOnWriteArraySet<Listener> listeners
ConcurrentHashMap<String, Config> configs
AtomicInteger version
```

Một lượt `listeners.iterator()` không tạo ảnh chụp nhất quán cùng thời điểm của `configs` hoặc `version`. Nếu một nghiệp vụ cần “listeners và configs cùng phiên bản”, phải thiết kế đơn vị snapshot ở tầng cao hơn, có thể bằng một immutable record chứa cả hai và công bố qua một reference duy nhất.

Đừng trộn:

- **Snapshot iterator:** tập reference element được cố định khi iterator hình thành.
- **Snapshot element:** mọi field/đồ thị bên trong element bất biến theo version.
- **Snapshot transaction:** nhiều cấu trúc dữ liệu được đọc/cập nhật theo một điểm nhất quán.

Chúng là ba khái niệm khác nhau. CopyOnWriteArraySet trực tiếp giải quyết khái niệm **đầu tiên**, hai khái niệm sau đòi hỏi thiết kế dữ liệu và protocol bổ sung.

## 23. Những lỗi thường gặp

### 23.1. Nghĩ iterator cũ nhìn thấy mọi `add` mới

Sai. Snapshot cố định khi `iterator()` được tạo. Để nhận membership mới nhất, tạo iterator mới ở thời điểm phù hợp.

### 23.2. Nghĩ `remove(e)` khiến iterator cũ không còn trả e

Sai. Iterator cũ vẫn có thể trả e nếu e có trong snapshot tại lúc tạo, dù Set hiện hành đã xóa e.

### 23.3. Gọi `iterator.remove()`

Không được hỗ trợ; ném `UnsupportedOperationException`. Xóa qua Set hoặc chọn cấu trúc khác nếu cần khả năng sửa iterator.

### 23.4. Mong iterator tự cung cấp deep-copy

Sai. Nó giữ tham chiếu phần tử. Element mutable có thể thay đổi nội dung ngay trong snapshot cũ.

### 23.5. Dùng CopyOnWriteArraySet cho hàng triệu phần tử với ghi liên tục

Có thể gây chi phí copy mảng, allocation và GC lớn. Xem xét concurrent hash-backed set, cấu trúc partition hoặc thiết kế khác.

### 23.6. Nghĩ `contains` có độ phức tạp O(1) như HashSet

CopyOnWriteArraySet dùng backing list, kiểm tra equality tuyến tính. Với Set lớn và nhiều lookup, chi phí có thể đáng kể.

### 23.7. Dùng key/element có equality mutable

Nếu element thay đổi trường dùng cho equals, tính duy nhất và membership có thể không còn phản ánh thiết kế nghiệp vụ.

### 23.8. Dùng `Collections.synchronizedSet` nhưng không synchronized suốt vòng iterator

Wrapper synchronized không tự làm iteration thành snapshot. Theo hợp đồng, phải giữ monitor phù hợp trong suốt thời gian duyệt.

### 23.9. Dùng weakly consistent iterator rồi tưởng có snapshot

`ConcurrentHashMap.newKeySet()` có iterator với semantics khác. Nó có thể phản ánh một số thay đổi trong lúc duyệt; không cam kết tập phần tử cố định từ lúc tạo.

### 23.10. Nghĩ hủy đăng ký listener lập tức dừng mọi callback

Không. Một dispatch đã chụp snapshot có thể tiếp tục gọi listener đã được remove. Cần protocol quản lý in-flight nếu yêu cầu.

### 23.11. Duy trì iterator quá lâu

Snapshot cũ giữ backing array và references, có thể làm retention object cũ lâu hơn mong muốn.

### 23.12. Nghĩ nhiều lần add/remove là một transaction

Mỗi thao tác có thể là một thay đổi nguyên tử riêng. Một reader tạo snapshot giữa hai lời gọi có thể thấy trạng thái trung gian.

### 23.13. Dùng `null` không kiểm tra contract giữa các Set

CopyOnWriteArraySet cho phép null, nhưng không phải concurrent set nào cũng cho phép, ví dụ `ConcurrentHashMap.newKeySet()` không cho phép null.

### 23.14. Bỏ qua ngoại lệ/timeout của callback

Iterator ổn định không đồng nghĩa callback trong vòng lặp luôn thành công. Nếu xử lý sự kiện lỗi, cần quyết định tiếp tục listener sau, dừng dispatch, retry hoặc ghi nhận outcome.

### 23.15. Benchmark chỉ có một lần chạy

Hiệu năng phụ thuộc kích thước Set, tỷ lệ đọc/ghi, số writer, phân bố element và thời gian sống iterator. Benchmark JVM cần warm-up và nhiều lần đo; không kết luận chỉ từ microbenchmark không kiểm soát.

## 24. Khi nào nên dùng CopyOnWriteArraySet?

**Rất phù hợp khi:**

- Tập listener/subscriber hoặc danh sách observer tương đối nhỏ.
- Vòng đọc/duyệt xảy ra cực kỳ thường xuyên.
- Đăng ký/hủy đăng ký ít xảy ra.
- Mỗi lượt dispatch muốn danh sách đối tượng **cố định từ đầu đến cuối**.
- Không muốn giữ một lock chung trong cả callback dài.
- Element bất biến hoặc có synchronization riêng cho state mutable.

**Nên cân nhắc cách khác khi:**

- Nhiều writer thay đổi Set liên tục hoặc số lượng phần tử rất lớn.
- Cần lookup `contains` rất nhanh trên tập có nhiều key.
- Muốn iterator có thể phản ánh một phần thay đổi đang xảy ra thay vì snapshot cũ.
- Cần thứ tự sắp xếp tự nhiên/comparator và range queries.
- Muốn thay đổi nhiều element cùng một transaction.
- Cần hỗ trợ xóa trực tiếp bằng iterator.

Một cách quyết định thực tế: xác định **read/write ratio**, kích thước n, thời gian duyệt, yêu cầu membership snapshot, độ trễ ghi có chấp nhận được và lượng bộ nhớ cho old snapshots. Chọn collection theo **semantics và workload**, không chỉ vì nó có tên “Concurrent”.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Một Set chứa A,B. Tạo iterator I. Sau đó add C, remove A. I sẽ duyệt gì?

**Đáp án:** I vẫn duyệt snapshot ban đầu A,B. Iterator mới được tạo sau cập nhật sẽ nhìn thấy B,C, giả sử không có writer khác.

**Câu 2.** Gọi `I.next()` lần đầu sau các thay đổi có làm I chụp snapshot mới không?

**Đáp án:** Không. Snapshot được cố định khi gọi `set.iterator()`, không phải khi gọi `next()`.

**Câu 3.** Tại sao iterator không ném ConcurrentModificationException chỉ vì writer add/remove?

**Đáp án:** Nó duyệt mảng snapshot không bị writer sửa; writer thay backing array mới. Không có thay đổi cấu trúc ngay trong mảng snapshot của iterator.

**Câu 4.** Có thể gọi `iterator.remove()` để xóa phần tử vừa duyệt không?

**Đáp án:** Không. Iterator của CopyOnWriteArraySet không hỗ trợ remove, sẽ ném UnsupportedOperationException.

**Câu 5.** Nếu một element mutable có `name` bị sửa sau khi iterator được tạo, snapshot có giữ được name cũ không?

**Đáp án:** Không. Snapshot giữ reference element, không deep-copy object. Nếu sửa đồng thời, còn cần đồng bộ cho field đó.

**Câu 6.** `CopyOnWriteArraySet` có cho phép null không?

**Đáp án:** Có. Set vẫn chỉ cho phép một phần tử null theo semantics của Set.

**Câu 7.** CopyOnWriteArraySet là một hash set có lookup O(1) không?

**Đáp án:** Không. Nó dựa trên CopyOnWriteArrayList; contains và kiểm tra equality nói chung cần tìm tuyến tính.

**Câu 8.** Vì sao chi phí add/remove có thể cao với Set lớn?

**Đáp án:** Khi thay đổi membership, writer thường phải tạo/copy backing array mới cỡ O(n), đồng thời có chi phí tìm phần tử.

**Câu 9.** Iterator của ConcurrentHashMap.newKeySet() giống snapshot iterator của CopyOnWriteArraySet không?

**Đáp án:** Không. Nó weakly consistent, có thể phản ánh một số thay đổi đồng thời, không chụp cố định membership ngay lúc tạo.

**Câu 10.** Một listener bị remove trong lúc dispatch đang duyệt snapshot. Có chắc nó không còn được gọi trong lượt đó không?

**Đáp án:** Không. Nếu listener đã có trong snapshot, lượt dispatch vẫn có thể gọi nó. Muốn bảo đảm hủy cả in-flight callback phải có protocol bổ sung.

**Câu 11.** Tại sao synchronizedSet cần synchronized thủ công khi duyệt?

**Đáp án:** Iterator không tự giữ monitor cho toàn vòng duyệt; nếu muốn ngăn concurrent structural modifications qua cùng wrapper, caller phải khóa theo hợp đồng của collection.

**Câu 12.** Snapshot có làm hai thao tác add(A) và remove(B) thành transaction không?

**Đáp án:** Không. Một iterator tạo giữa hai thao tác có thể thấy trạng thái trung gian.

**Câu 13.** Vì sao một iterator lâu sống có thể làm heap giữ phần tử đã xóa?

**Đáp án:** Nó còn giữ mảng snapshot cũ chứa reference tới các phần tử ấy; GC chỉ có thể thu hồi khi không còn tham chiếu sống thích hợp.

**Câu 14.** Có cần copy cả Set mỗi lần tạo iterator để được snapshot không?

**Đáp án:** Không. CopyOnWriteArraySet thường chụp reference tới backing array hiện hành; chi phí copy chủ yếu ở ghi thay đổi membership.

**Câu 15.** Nếu hai listener có cùng id nhưng khác channel và record equals xét cả hai field, Set có đảm bảo chỉ một listener theo id không?

**Đáp án:** Không. Tính duy nhất theo `equals()` của element, không theo id riêng. Cần thiết kế equality/key theo nghiệp vụ.

## 26. Tổng kết

**`CopyOnWriteArraySet` phù hợp với tập phần tử tương đối nhỏ, được đọc/duyệt rất nhiều và ít thay đổi.** Khi writer thêm hoặc xóa phần tử, collection có thể tạo backing array mới; iterator đã tồn tại tiếp tục duyệt **mảng snapshot cũ**, không phản ánh thay đổi mới và không bị `ConcurrentModificationException` do các thao tác ghi trên Set.

Những quy tắc cần nhớ:

1. **Snapshot xuất hiện tại `iterator()`**, không phải ở lần gọi `next()` đầu tiên.
2. Ghi sau đó **không thêm/xóa phần tử trong iterator cũ**.
3. `iterator.remove()` không được hỗ trợ; hãy sửa collection qua API của Set.
4. Snapshot chỉ giữ **tham chiếu thành viên**, **không deep-copy element** và không tự làm field mutable thread-safe.
5. Add/remove làm thay đổi membership thường tốn `O(n)` cho copy mảng; contains cũng tìm tuyến tính.
6. Iterator cũ có thể giữ mảng và object đã bị gỡ lâu hơn dự kiến; tránh giữ snapshot quá lâu.
7. So với `ConcurrentHashMap.newKeySet()` có iterator weakly consistent, CopyOnWriteArraySet trả **một danh sách membership cố định cho cả lượt duyệt**.
8. Khi nghiệp vụ cần in-flight cancellation, transaction nhiều phần tử hoặc snapshot nhiều cấu trúc, phải có giao thức ở tầng ứng dụng.

Một ví dụ sử dụng phù hợp là **listener registry**: rất nhiều lượt dispatch nhưng rất hiếm lượt đăng ký/hủy đăng ký. Khi hiểu rõ thời điểm chụp snapshot, giới hạn của mutable elements và chi phí mỗi lần ghi, bạn có thể dùng CopyOnWriteArraySet đúng như công cụ chuyên biệt của **Java Concurrent Collections**, thay vì coi nó là một Set concurrent “tốt nhất cho mọi trường hợp”.
