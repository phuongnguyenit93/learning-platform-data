# Defensive copy và snapshot bất biến trong Java concurrency

## 1. Vấn đề cần giải quyết: cùng giữ một tham chiếu mutable

Trong chương trình Java nhiều thread, lỗi có thể xuất hiện khi hai thành phần vô tình dùng chung một đối tượng có thể thay đổi (*mutable object*). Một thành phần nghĩ mình đã lưu một cấu hình ổn định, nhưng thread khác vẫn giữ tham chiếu đến cấu hình ban đầu và sửa nó. Ngay cả khi không xảy ra lỗi đồng thời tức thời, thiết kế đó làm mất quyền kiểm soát đối với trạng thái và khiến việc chứng minh thread safety khó khăn.

Hai kỹ thuật quan trọng:

- **Defensive copy (sao chép phòng vệ):** tạo một bản sao thích hợp ở ranh giới nhận/trả dữ liệu để bên ngoài không thể thay đổi trạng thái nội bộ thông qua tham chiếu được chia sẻ.
- **Immutable snapshot (ảnh chụp bất biến):** biểu diễn trạng thái tại một thời điểm bằng một giá trị bất biến sau khi tạo; người đọc có thể giữ snapshot đó trong khi người ghi tạo và công bố phiên bản mới.

Tính **bất biến** của một snapshot giúp tránh race trên *nội dung* của snapshot. Nhưng **việc công bố tham chiếu snapshot sang thread khác vẫn cần đúng Java Memory Model**, ví dụ thông qua trường `volatile`, `AtomicReference`, monitor lock hoặc các cơ chế truyền dữ liệu có bảo đảm happens-before.

Bài học tập trung vào Java nói chung: các collection, object, record, lock, volatile và atomic API trong JDK. Không cần framework để áp dụng các nguyên tắc này.

### Mục tiêu sau bài

1. Phân biệt sao chép độc lập, unmodifiable view, immutable value, shallow copy và deep copy.
2. Biết phải copy khi **nhận dữ liệu** và khi **trả dữ liệu** ở đúng ranh giới sở hữu.
3. Dùng `List.copyOf`, `Set.copyOf`, `Map.copyOf`, constructor bất biến và defensive getter một cách đúng đắn.
4. Tạo snapshot nhất quán từ trạng thái nhiều biến và công bố snapshot an toàn cho reader.
5. Hiểu giới hạn: bản sao collection không tự sao chép các phần tử mutable, unmodifiable không có nghĩa thread-safe, snapshot có chi phí bộ nhớ và có thể cũ theo thời gian.

## 2. Lỗi aliasing: hai tham chiếu trỏ đến cùng object

**Aliasing** xảy ra khi hai biến trỏ đến một object. Với object mutable, tác động từ một biến có thể được nhìn thấy qua biến còn lại:

~~~java
// Minh họa trong một phương thức Java, không phải chương trình độc lập.
List<String> original = new ArrayList<>();
original.add("read");

List<String> alias = original;  // Không copy.
alias.add("write");

// original giờ chứa ["read", "write"].
~~~

Khi đưa `original` vào constructor rồi giữ nguyên tham chiếu, caller có thể sửa nội bộ đối tượng thông qua biến ban đầu. Nếu getter trả thẳng một `ArrayList` bên trong, caller cũng có thể sửa trạng thái sau khi nhận object.

Trong ứng dụng nhiều thread, hai đường sửa đó đặc biệt nguy hiểm:

- Một reader đang duyệt collection, writer sửa đồng thời có thể gây kết quả không nhất quán, exception hoặc data race tùy loại collection.
- Một component định nghĩa invariant như “cấu hình luôn chứa một tập quyền đã kiểm tra”, nhưng caller thêm/bớt phần tử sau khi validation.
- Một luồng công bố cấu hình, luồng khác đọc nhiều trường ở những thời điểm khác nhau và ghép thành một trạng thái chưa từng tồn tại.

Giải pháp bắt đầu từ **quyền sở hữu**: ai được sửa dữ liệu, ai chỉ đọc, và tại ranh giới nào cần sao chép hoặc truyền một giá trị bất biến.

## 3. Unmodifiable view khác defensive copy

Một *unmodifiable view* chặn thao tác sửa **qua view**, nhưng có thể vẫn phản ánh thay đổi ở backing collection. Trong khi đó, `List.copyOf` tạo một danh sách không thể sửa qua giao diện danh sách và không còn bị ảnh hưởng bởi **thay đổi cấu trúc** của nguồn mutable sau lúc copy.

### Ví dụ 1 — view “chỉ đọc” vẫn thay đổi theo nguồn (Java 17+)

Tạo tệp `ViewVsSnapshotDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ViewVsSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("alpha");

        List<String> liveView =
            Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.add("beta");

        System.out.println("view = " + liveView);
        System.out.println("snapshot = " + snapshot);

        try {
            snapshot.add("gamma");
        } catch (UnsupportedOperationException error) {
            System.out.println("snapshot rejects add");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ViewVsSnapshotDemo.java
java ViewVsSnapshotDemo
~~~

Stdout:

~~~text
view = [alpha, beta]
snapshot = [alpha]
snapshot rejects add
~~~

Giải thích:

- `Collections.unmodifiableList(source)` tạo view không cho thêm/xóa qua view; khi `source` được sửa trực tiếp, view thấy nội dung mới.
- `List.copyOf(source)` ghi nhận danh sách phần tử tại thời điểm copy, vì vậy sau khi thêm `beta` vào `source`, cấu trúc danh sách snapshot không đổi.
- Cả hai đối tượng đều từ chối `add` qua giao diện của chúng. Việc cùng từ chối `add` **không chứng minh cùng có snapshot semantics**.
- `List.copyOf` có thể tái sử dụng một danh sách đầu vào vốn đã thuộc họ unmodifiable phù hợp; **không dựa vào việc kết quả luôn có identity khác nguồn**. Điều cần bảo đảm là snapshot không bị thay đổi cấu trúc bởi nguồn mutable sau khi copy.

| Cách tạo | Có sửa qua kết quả được không? | Nguồn thay đổi cấu trúc sau đó có làm kết quả đổi? | Phần tử mutable bên trong có được copy không? |
| --- | --- | --- | --- |
| `alias = source` | Có, nếu nguồn mutable | Có | Không |
| `Collections.unmodifiableList(source)` | Không qua view | **Có**, view phản ánh backing list | Không |
| `new ArrayList<>(source)` | Có, bản sao là mutable | Không (với thao tác cấu trúc trên nguồn sau copy) | Không |
| `List.copyOf(source)` | Không | Không, nếu nguồn là mutable thông thường | **Không**, chỉ copy cấu trúc |
| `List.of("A", "B")` | Không | Không có backing list mutable bên ngoài | Không áp dụng với `String` bất biến |

Bản sao cấu trúc không tự bảo đảm snapshot nhất quán nếu **nguồn đang bị thread khác sửa trong lúc copy**. Cần phối hợp khi thực hiện copy, như khóa, cơ chế snapshot của dữ liệu nguồn hoặc thiết kế công bố bất biến ngay từ đầu.

### Các giới hạn của `copyOf`

- `List.copyOf`, `Set.copyOf` và `Map.copyOf` có trong Java 10+, nên dùng được với Java 17.
- Các factory/copy method này **không chấp nhận phần tử null**; với map, cả key lẫn value null cũng không được chấp nhận. Khi nguồn có null, có thể gặp `NullPointerException`.
- Kết quả là unmodifiable collection ở cấp collection, **không phải deep immutable** nếu phần tử hoặc value vẫn mutable.
- Không phụ thuộc vào identity hay implementation class của kết quả, cũng không dùng kết quả như monitor lock có identity ổn định.
- `Set.copyOf` đối với input collection có phần tử trùng bằng `equals` chỉ giữ một đại diện; **không bảo đảm chọn đại diện nào**. Không dùng nó khi việc giữ đủ bản ghi trùng hoặc thứ tự là yêu cầu nghiệp vụ.
- `Map.copyOf` nhận một `Map` và không biến nested map/list thành bất biến; thứ tự duyệt của map cũng không được mặc định giống bản gốc.

## 4. Copy ở ranh giới vào và ra của đối tượng

Một lớp muốn bảo vệ trạng thái nội bộ thường cần hai phía:

1. **Copy in:** constructor/setter nhận một collection hoặc object mutable từ caller thì copy trước khi lưu.
2. **Copy out:** getter không để caller sửa nội bộ qua reference trả về. Có thể trả trực tiếp **immutable value** đã được bảo đảm an toàn; nếu nội bộ vẫn mutable, phải trả bản sao thích hợp.

### Ví dụ 2 — lớp immutable với copy in và giá trị trả ra an toàn

Tạo tệp `ImmutableConfigDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ImmutableConfigDemo {
    static final class WorkerConfig {
        private final List<String> permissions;

        WorkerConfig(List<String> requestedPermissions) {
            this.permissions = List.copyOf(requestedPermissions);
        }

        List<String> permissions() {
            return permissions;
        }
    }

    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("read");

        WorkerConfig config = new WorkerConfig(input);
        input.add("delete");

        System.out.println("config = " + config.permissions());

        try {
            config.permissions().add("write");
        } catch (UnsupportedOperationException error) {
            System.out.println("getter result is unmodifiable");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ImmutableConfigDemo.java
java ImmutableConfigDemo
~~~

Stdout:

~~~text
config = [read]
getter result is unmodifiable
~~~

Vì `WorkerConfig` giữ một `final List<String>` được tạo bằng `List.copyOf` và phần tử là `String` bất biến, caller không sửa được nội dung qua input hoặc getter. **Getter không nhất thiết cần tạo thêm một bản sao** khi dữ liệu bên trong đã là immutable value có thể chia sẻ an toàn. Copy lặp lại mỗi lần đọc chỉ làm tăng allocation mà không cung cấp bảo vệ bổ sung trong trường hợp này.

Từ khóa `final` bảo đảm **tham chiếu trường không bị gán lại**, nhưng không tự biến object mà nó trỏ tới thành immutable. Nếu lưu thẳng một `ArrayList` mutable vào `final List`, caller vẫn có thể sửa các phần tử và cấu trúc của danh sách đó bằng tham chiếu khác.

### Khi nội bộ cần mutable, getter phải bảo vệ

Ví dụ một lớp lưu `ArrayList` và cập nhật dưới khóa. Getter muốn trả snapshot thì cũng phải copy **khi giữ cùng khóa**:

~~~java
// Minh họa trong cùng một class; không phải chương trình độc lập.
private final List<String> events = new ArrayList<>();

public synchronized void addEvent(String event) {
    events.add(event);
}

public synchronized List<String> snapshotEvents() {
    return List.copyOf(events);
}
~~~

Với đoạn trên, copy được thực hiện khi đã khóa object hiện tại; các thao tác writer trong cùng class cũng phải theo **cùng monitor**. Đây là điều cần thiết để snapshot không bị sửa ở giữa phép copy. Nếu getter trả `Collections.unmodifiableList(events)`, caller sẽ nhận một view luôn thay đổi theo những lần thêm tiếp theo, không phải snapshot.

## 5. Shallow copy không bảo vệ phần tử mutable

`List.copyOf` chỉ sao chép cấu trúc collection. Nếu một phần tử chứa trạng thái mutable, cả nguồn và snapshot vẫn giữ **cùng tham chiếu phần tử**.

~~~java
// Minh họa bên trong phương thức, không phải chương trình độc lập.
StringBuilder item = new StringBuilder("A");
List<StringBuilder> snapshot = List.copyOf(List.of(item));

item.append("B");
// snapshot.get(0).toString() giờ là "AB".
~~~

`snapshot.add(...)` bị chặn, nhưng `snapshot.get(0).append(...)` vẫn sửa object phần tử. Vì vậy snapshot chưa đạt **deep immutability**.

### Ví dụ 3 — chuyển phần tử mutable thành immutable data (Java 17+)

Tạo tệp `DeepCopyBoundaryDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DeepCopyBoundaryDemo {
    static final class MutableLabel {
        private String text;

        MutableLabel(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }

        void rename(String value) {
            text = value;
        }
    }

    static final class LabelSnapshot {
        private final List<String> values;

        LabelSnapshot(List<MutableLabel> input) {
            List<String> copy = new ArrayList<>();
            for (MutableLabel label : input) {
                copy.add(label.text());
            }
            values = List.copyOf(copy);
        }

        List<String> values() {
            return values;
        }
    }

    public static void main(String[] args) {
        MutableLabel label = new MutableLabel("alpha");
        List<MutableLabel> source = new ArrayList<>();
        source.add(label);

        LabelSnapshot snapshot = new LabelSnapshot(source);
        label.rename("beta");
        source.add(new MutableLabel("gamma"));

        System.out.println("snapshot = " + snapshot.values());
        System.out.println("current = " + label.text());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DeepCopyBoundaryDemo.java
java DeepCopyBoundaryDemo
~~~

Stdout:

~~~text
snapshot = [alpha]
current = beta
~~~

Trong constructor, từng `MutableLabel` được **chuyển thành giá trị `String` bất biến**, sau đó danh sách kết quả được tạo bất biến. Vì vậy thay đổi cấu trúc nguồn và thay đổi `label` sau khi constructor chạy đều không ảnh hưởng tới snapshot.

**Quan trọng:** ví dụ minh họa copy khi nguồn không bị sửa đồng thời trong lúc constructor thực thi. Nếu một writer khác đang gọi `rename` ngay trong quá trình copy, bạn cần đồng bộ hoặc giao thức snapshot từ nguồn để có một thời điểm quan sát nhất quán. Deep copy đơn thuần không làm một phép đọc nhiều object trở thành atomic.

### Phân biệt shallow/deep copy

| Nhu cầu | Sao chép phù hợp |
| --- | --- |
| `List<String>` với phần tử bất biến | `List.copyOf` thường đủ |
| `List<MutableOrder>` dùng chung với writer | Copy từng `MutableOrder` thành immutable DTO/snapshot rồi `List.copyOf` |
| Mảng `byte[]` nhận từ bên ngoài | `clone()`/`Arrays.copyOf` khi nhận; copy lại khi trả |
| Mảng object chứa phần tử mutable | Copy mảng **và** từng object mutable bên trong nếu muốn deep copy |
| Record có field `List<MutableThing>` | Record mặc định chỉ bất biến ở reference; phải copy/chuẩn hóa nội dung |

Với graph object có vòng tham chiếu, tài nguyên như socket hoặc file, “deep copy mọi thứ” có thể không khả thi hoặc không có nghĩa. Khi đó thiết kế immutable projection chỉ chứa dữ liệu cần đọc thường rõ ràng hơn sao chép tùy tiện toàn bộ object graph.

## 6. Array, Date, record và các bẫy bất biến thường gặp

### 6.1. Mảng luôn có thể sửa

Trường `private final byte[] key` không có nghĩa nội dung mảng không thể thay đổi. Nếu caller còn giữ tham chiếu mảng, họ có thể sửa `key[0]` sau khi đưa vào constructor.

Một mẫu phòng vệ:

~~~java
// Minh họa trong class chứa byte[]; không phải chương trình độc lập.
private final byte[] bytes;

public Payload(byte[] input) {
    this.bytes = input.clone();
}

public byte[] bytes() {
    return bytes.clone();
}
~~~

`clone()` với mảng primitive tạo bản sao độc lập của các giá trị primitive. Với mảng object, `clone()` chỉ sao chép danh sách tham chiếu, **không clone từng object con**. Khi dùng mảng lưu bí mật, còn phải thiết kế vòng đời dữ liệu, quyền truy cập và chính sách xóa nhạy cảm phù hợp; clone không tự giải quyết quản lý bí mật.

### 6.2. Các kiểu ngày giờ

`java.util.Date` là mutable; trả thẳng `Date` từ getter cho phép caller sửa bằng `setTime(...)`. Có thể copy qua `new Date(original.getTime())` ở ranh giới vào/ra hoặc chuyển sang kiểu bất biến trong `java.time` như `Instant`, `LocalDate` khi đúng ý nghĩa nghiệp vụ.

### 6.3. Record không tự động deep immutable

Java record làm các **component fields** trở thành `private final`, đồng thời sinh accessor, nhưng object được tham chiếu vẫn có thể mutable.

~~~java
// Minh họa Java 17+, không phải chương trình độc lập.
record Batch(List<String> items) {
    Batch {
        items = List.copyOf(items);
    }
}
~~~

Trong compact canonical constructor, tham số `items` được gán lại thành bản sao unmodifiable trước khi lưu vào field được sinh. Với `String` bất biến, record trên tạo value object phù hợp để chia sẻ. Nếu `items` chứa object mutable, phải chuyển/copy phần tử nữa. Nếu record chứa mảng, accessor mặc định trả tham chiếu mảng; có thể cần override accessor để copy out.

Không nên nhầm **immutable class** với “mọi field đều `final`”. Tính bất biến phải được xét đệ quy ở phần **trạng thái có thể quan sát và sửa**.

## 7. Snapshot bất biến và tính nhất quán tại một thời điểm

Một snapshot có ý nghĩa khi nó biểu diễn **một trạng thái hợp lệ** tại một thời điểm chuyển giao. Giả sử trạng thái hệ thống có hai biến `left` và `right`, với invariant `left + right == 100`. Nếu reader đọc `left` rồi writer cập nhật, sau đó reader đọc `right`, reader có thể ghép giá trị từ hai thời điểm thành tổng không bằng 100.

Ngay cả khi cả hai biến đều là `volatile`, việc đọc lần lượt **không tạo snapshot atomic của cả cặp**.

Hai chiến lược thường gặp:

1. **Copy dưới khóa:** reader giữ cùng lock mà writer dùng trong toàn bộ quá trình copy; snapshot phản ánh một trạng thái không bị writer chen vào.
2. **Single immutable state object:** writer tạo một object trạng thái mới hoàn chỉnh rồi công bố cả tham chiếu bằng `volatile` hoặc `AtomicReference`; reader đọc tham chiếu một lần và dùng chính object đó cho mọi field.

Phân biệt **immutability** và **publication**:

- Không sửa object snapshot sau khi tạo giúp reader không đua nhau cập nhật nội dung.
- Công bố tham chiếu qua cơ chế có happens-before giúp reader được bảo đảm thấy trạng thái đã khởi tạo.
- Một reader có thể giữ snapshot phiên bản cũ trong khi writer công bố phiên bản mới; đó là đặc tính mong muốn trong nhiều thiết kế, không phải lỗi visibility.
- Snapshot không có nghĩa đọc “dữ liệu mới nhất ở mọi thời điểm”; nó có nghĩa đọc **một phiên bản nhất quán**.

## 8. Ví dụ 4 — copy snapshot trong synchronized (Java 17+)

Tạo tệp `LockedSnapshotDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LockedSnapshotDemo {
    static final class EventStore {
        private final List<String> events = new ArrayList<>();

        synchronized void add(String value) {
            events.add(value);
        }

        synchronized List<String> snapshot() {
            return List.copyOf(events);
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        EventStore store = new EventStore();
        store.add("created");

        List<String> firstSnapshot = store.snapshot();

        Thread writer = new Thread(() -> {
            store.add("processed");
        }, "event-writer");

        writer.start();
        writer.join();

        System.out.println("old = " + firstSnapshot);
        System.out.println("new = " + store.snapshot());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac LockedSnapshotDemo.java
java LockedSnapshotDemo
~~~

Stdout:

~~~text
old = [created]
new = [created, processed]
~~~

`add` và `snapshot` dùng cùng monitor của `EventStore`, nên không có writer chen vào giữa lúc `snapshot` copy list. `firstSnapshot` giữ trạng thái cũ ngay cả khi writer thêm `processed`. `join()` xác nhận writer đã hoàn tất trước khi chụp snapshot thứ hai.

Điều này khác với việc giữ `Collections.unmodifiableList(events)`: view đó sẽ phản ánh phần tử `processed` trong cả hai lần đọc.

Một snapshot copy đúng dưới khóa vẫn có chi phí: mỗi lần `snapshot()` cần duyệt/cấp phát tỉ lệ với kích thước collection. Nếu reader nhiều hơn writer rất lớn, có thể cân nhắc công bố nguyên khối immutable state để reader chỉ đọc tham chiếu.

## 9. Công bố snapshot qua volatile hoặc AtomicReference

### 9.1. Một reference volatile cho cả state

Ví dụ cấu trúc ý tưởng:

~~~java
// Minh họa trong một class; cấu hình immutable đã được tạo hợp lệ.
private volatile ConfigSnapshot current;

// Writer:
current = newSnapshot;

// Reader:
ConfigSnapshot local = current;
// Tiếp tục đọc tất cả field qua cùng biến local.
~~~

**Gán một reference** là một thao tác nguyên tử; khi dùng `volatile`, nó còn cung cấp ràng buộc visibility/ordering cho việc công bố. Nếu reader đọc `current` một lần rồi đọc các field của `local`, các field đó thuộc **cùng phiên bản**. Nếu reader gọi `current.a()` rồi `current.b()` ở hai lần đọc reference khác nhau, writer có thể thay snapshot giữa hai lần và reader tự ghép hai phiên bản — lỗi ở cách đọc.

`volatile` **không tự tránh lost update khi có nhiều writer** làm read–modify–write theo kiểu “đọc current, tạo bản mới, gán current”. Với nhiều writer tranh chấp, nên dùng khóa hoặc CAS/`AtomicReference.updateAndGet` với logic cập nhật thuần.

### 9.2. Ví dụ 5 — snapshot bất biến cập nhật bằng CAS (Java 17+)

Tạo tệp `AtomicSnapshotDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class AtomicSnapshotDemo {
    record Inventory(int available, int reserved, long version) {
        Inventory {
            if (available < 0 || reserved < 0) {
                throw new IllegalArgumentException("Negative stock");
            }
        }

        int total() {
            return available + reserved;
        }
    }

    public static void main(String[] args) {
        AtomicReference<Inventory> state =
            new AtomicReference<>(new Inventory(10, 0, 0));

        Inventory before = state.get();

        state.updateAndGet(old ->
            new Inventory(
                old.available() - 3,
                old.reserved() + 3,
                old.version() + 1
            )
        );

        Inventory after = state.get();

        System.out.println(
            "before=" + before + ", total=" + before.total()
        );
        System.out.println(
            "after=" + after + ", total=" + after.total()
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AtomicSnapshotDemo.java
java AtomicSnapshotDemo
~~~

Stdout:

~~~text
before=Inventory[available=10, reserved=0, version=0], total=10
after=Inventory[available=7, reserved=3, version=1], total=10
~~~

`Inventory` là record chỉ chứa ba giá trị primitive; sau khi tạo không có trường nội bộ mutable. `AtomicReference.get()` trả về một snapshot có thể chia sẻ, còn `updateAndGet` thử thay thế toàn bộ reference bằng snapshot mới dựa trên giá trị hiện tại. Một reader giữ `before` sẽ tiếp tục thấy phiên bản 0, còn reader lấy `after` thấy phiên bản 1. Tổng `available + reserved` nhất quán ở mỗi phiên bản.

**Giới hạn quan trọng:**

- Hàm truyền vào `updateAndGet` **có thể bị thực thi nhiều lần** nếu tranh chấp; chỉ đặt tính toán thuần bên trong, không gửi request/ghi file/tạo side effect cần chạy đúng một lần.
- Nếu một update có thể làm `available` âm, constructor trong ví dụ ném exception. Trong ứng dụng thực cần kiểm tra điều kiện nghiệp vụ và quyết định kết quả thất bại theo hợp đồng rõ ràng.
- CAS bảo vệ việc thay **cả một reference**, không biến side effect bên ngoài như database write thành giao dịch nguyên tử.
- Giữ bản snapshot cũ lâu sẽ giữ dữ liệu của phiên bản đó trong bộ nhớ đến khi không còn tham chiếu.
- Với trường hợp chỉ có một writer và reader nhiều, có thể dùng `volatile` để công bố snapshot hoàn chỉnh; CAS hữu ích khi nhiều writer phải phối hợp cập nhật trạng thái dựa trên phiên bản hiện tại.

### Luồng đọc và ghi

~~~text
Writer:
  đọc current v1
       |
  tạo state v2 bất biến
       |
  công bố v2 bằng volatile/CAS
       |
Reader A: giữ v1, đọc nhất quán v1
Reader B: lấy v2, đọc nhất quán v2
~~~

Không có yêu cầu writer phải chờ mọi reader hoàn tất trước khi tạo phiên bản mới. Đây là lý do kiểu thiết kế copy-on-write rất hữu ích khi **đọc nhiều, ghi ít**.

## 10. Bảo đảm thread safety khi sao chép

### 10.1. Copy khi nguồn đang bị sửa là một bài toán riêng

Một lỗi thường gặp là:

~~~java
// Minh họa không an toàn nếu source là ArrayList đang bị sửa đồng thời.
List<String> snapshot = List.copyOf(source);
~~~

Nếu một writer khác sửa `source` trong lúc copy, bạn chưa có một snapshot **nhất quán theo thời điểm**. Trên collection không hỗ trợ concurrent modification, quá trình duyệt/copy còn có thể gặp exception hoặc hành vi không phù hợp kỳ vọng.

Cần quy định rõ:

- **Nguồn được sở hữu độc quyền:** không thread nào khác sửa trong lúc copy.
- **Nguồn bảo vệ bằng lock:** writer và snapshot cùng dùng một monitor/lock.
- **Nguồn là immutable state:** reader chỉ chụp lại reference một lần, không phải duyệt collection mutable đang thay đổi.
- **Nguồn là concurrent collection:** phải đọc hợp đồng cụ thể của operation. “Concurrent” không mặc nhiên nghĩa một lần copy phản ánh một khoảnh khắc atomic của toàn bộ collection.

Ví dụ, iterator của `ConcurrentHashMap` thường có tính **weakly consistent**: có thể phản ánh một phần cập nhật đồng thời mà không ném `ConcurrentModificationException` theo kiểu fail-fast. Tạo một `Map.copyOf` từ concurrent map đang đổi không tự bảo đảm snapshot tuyến tính hóa của toàn bộ map nếu yêu cầu nhất quán nhiều entry.

### 10.2. CopyOnWriteArrayList là một lựa chọn chuyên biệt

`CopyOnWriteArrayList` tạo bản sao mảng nền khi có thao tác sửa cấu trúc và cung cấp iterator kiểu **snapshot** không bị tác động bởi cập nhật cấu trúc về sau. Nó hợp với dữ liệu **đọc/duyệt nhiều, ghi ít**, như danh sách listener.

Đổi lại, mỗi lần ghi có thể cần copy mảng nền; khi list lớn hoặc ghi liên tục, chi phí cấp phát, bộ nhớ và CPU có thể cao. Snapshot iterator chỉ bảo vệ nội dung **mảng tham chiếu** tại thời điểm iterator được tạo, không làm các object phần tử mutable trở nên bất biến.

`CopyOnWriteArrayList` là container concurrency, còn immutable snapshot là **một kiểu biểu diễn trạng thái**. Tùy bài toán, một `AtomicReference<List<ImmutableValue>>` được thay trọn gói có thể dễ kiểm soát phiên bản hơn.

### 10.3. Consistency và freshness là hai yêu cầu khác nhau

| Tính chất | Ý nghĩa |
| --- | --- |
| Consistent snapshot | Các trường thuộc cùng một phiên bản hợp lệ |
| Freshness | Snapshot có mới đến mức nào so với writer hiện tại |
| Atomic publication | Reader thấy reference của phiên bản cũ hoặc mới, không có trạng thái xây dựng dở |
| Thread-safe source | Cơ chế đọc/ghi của nguồn không vi phạm quy tắc đồng bộ |
| Deep immutability | Toàn bộ nội dung có thể quan sát không thể bị sửa thông qua alias khác |

Một snapshot cũ có thể hoàn toàn nhất quán nhưng không đủ mới cho yêu cầu nghiệp vụ. Ví dụ giao diện hiển thị cấu hình có thể chấp nhận chậm một phiên bản; kiểm tra tồn kho để đặt hàng có thể cần kiểm tra lại gần thời điểm ghi, phối hợp điều kiện atomically với việc cập nhật.

## 11. Chi phí bộ nhớ, hiệu năng và thiết kế

Defensive copy và immutable snapshot giúp giảm chia sẻ mutable, nhưng mỗi lần copy lớn cần thời gian, bộ nhớ và GC.

**Nên đánh giá:**

1. **Tần suất ghi:** Với nhiều writer, copy toàn bộ collection cho mỗi lần sửa có thể tốn kém. Cân nhắc khóa, phân vùng trạng thái hoặc cấu trúc dữ liệu phù hợp.
2. **Tần suất đọc:** Khi reader rất nhiều và trạng thái ít đổi, công bố immutable snapshot bằng một reference có thể tránh lock trên đường đọc.
3. **Kích thước snapshot:** Copy một list hàng triệu phần tử cho mỗi request là một chi phí lớn; có thể chuyển sang phân trang, snapshot theo phần, persistent data structure hoặc giới hạn scope.
4. **Thời gian giữ phiên bản cũ:** Nhiều reader giữ snapshot cũ làm tăng lượng dữ liệu sống trong heap. Theo dõi heap occupancy và GC pressure.
5. **Chất lượng tính bất biến:** Nếu phần tử vẫn mutable, mọi tối ưu chia sẻ snapshot có thể mất ý nghĩa.
6. **Thời điểm copy:** Copy khi nhận dữ liệu, trước khi công bố hay mỗi lần getter? Trả một immutable value đã được công bố an toàn thường rẻ hơn copy lặp lại.
7. **Yêu cầu phiên bản:** Snapshot có cần `version` hoặc timestamp để người dùng nhận biết độ mới và tránh ghi đè một update của phiên bản khác không?

Không có quy tắc “copy mọi object mọi lúc”. Phương án tốt phụ thuộc vào ownership, mức độ đồng thời, yêu cầu nhất quán và phép đo trên workload thực tế.

## 12. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| `this.items = input` rồi tin rằng caller không sửa | Caller giữ alias | Copy vào hoặc chuyển ownership rõ ràng |
| Getter trả `ArrayList` nội bộ | Caller sửa thẳng state | Trả immutable snapshot hoặc defensive copy |
| `Collections.unmodifiableList(mutableList)` và gọi đó là snapshot | View phản ánh sửa đổi từ backing list | `List.copyOf` tại thời điểm được đồng bộ thích hợp |
| `List.copyOf(List<MutableItem>)` và gọi đó là deep immutable | Phần tử vẫn chia sẻ reference mutable | Copy/project từng phần tử thành immutable value |
| Record có `byte[]` rồi cho rằng record hoàn toàn immutable | Field final nhưng mảng sửa được | Copy mảng trong constructor và accessor |
| Copy collection trong lúc writer sửa không khóa | Snapshot có thể không nhất quán hoặc lỗi | Copy dưới cùng lock hoặc thiết kế immutable source |
| Gán hai field volatile và gọi đó là snapshot nguyên tử | Reader có thể ghép hai phiên bản | Gộp vào một immutable state object và công bố một reference |
| Writer đọc volatile state rồi gán state mới không CAS | Nhiều writer có thể mất update | Dùng lock hoặc `AtomicReference.compareAndSet/updateAndGet` |
| Dùng `AtomicReference` nhưng update function có side effect | CAS retry làm side effect lặp | Hàm biến đổi thuần, side effect sau khi cập nhật thành công |
| Dùng `CopyOnWriteArrayList` cho workload ghi liên tục | Mỗi ghi có chi phí copy cấu trúc | Đo tải, chọn collection/lock khác phù hợp |
| Tin `final` làm object graph immutable | `final` chỉ khóa việc gán tham chiếu | Thiết kế bất biến đệ quy ở dữ liệu quan sát được |
| Dựa vào `Thread.sleep` để chờ snapshot “ổn định” | Sleep không tạo HB/atomicity | Dùng lock, latch, future, volatile/CAS đúng giao thức |

## 13. Checklist review và tự kiểm tra

Khi đánh giá một lớp chia sẻ giữa nhiều thread:

- **Ownership:** Caller nào còn giữ tham chiếu tới object đầu vào? Có thể sửa object đó sau constructor không?
- **Copy in:** Constructor/setter có chụp dữ liệu độc lập trước khi lưu không? Nếu dữ liệu lồng nhau mutable, copy có đủ sâu không?
- **Copy out:** Getter có vô tình trả mutable object nội bộ không? Nếu trả immutable snapshot, các phần tử đã thực sự immutable chưa?
- **Consistency:** Nếu nhiều field phải tuân theo một invariant, snapshot có được tạo dưới cùng lock hoặc từ một immutable state duy nhất không?
- **Publication:** Writer và reader có giao thức happens-before rõ ràng qua `volatile`, CAS, lock, queue, start/join hoặc primitive khác không?
- **Concurrency:** Có writer nào sửa nguồn trong lúc copy mà không phối hợp không?
- **Performance:** Tần suất copy, kích thước snapshot và thời gian giữ phiên bản cũ có phù hợp không?
- **Tests:** Có kiểm tra thay đổi nguồn sau copy, thay đổi phần tử mutable, writer/readers chạy đồng thời và invariant của snapshot không?

### Câu hỏi 1

`List<String> view = Collections.unmodifiableList(source)`. Một thread khác sửa `source`. `view` có còn giữ đúng nội dung lúc tạo không?

**Đáp án:** Không được bảo đảm. `view` là unmodifiable view, phản ánh backing source. Nếu việc sửa và đọc diễn ra đồng thời không đúng giao thức, còn có thể vi phạm thread safety.

### Câu hỏi 2

`List<MutableOrder> snapshot = List.copyOf(orders)`. Có thể khẳng định tất cả `MutableOrder` bên trong không thể thay đổi nữa không?

**Đáp án:** Không. `copyOf` không clone/deep-copy các order. Cần chuyển chúng thành immutable projection hoặc defensive copy từng phần tử theo ownership phù hợp.

### Câu hỏi 3

Reader có thể đọc `current.left()` và ngay sau đó `current.right()`, trong khi `current` là reference volatile trỏ tới state bất biến và writer thay nó được không?

**Đáp án:** Hai lần truy cập `current` riêng biệt có thể lấy **hai phiên bản**. Để được snapshot nhất quán, gán `State local = current` một lần rồi đọc cả `local.left()` và `local.right()`.

### Câu hỏi 4

Vì sao `AtomicReference.updateAndGet` không nên nhận một lambda vừa tạo state mới vừa ghi log nghiệp vụ tính tiền?

**Đáp án:** CAS có thể retry khi tranh chấp, khiến lambda được gọi nhiều lần cho một update thành công. Hàm biến đổi state phải thuần; side effect phải có cơ chế đảm bảo riêng.

### Câu hỏi 5

Nếu một thread giữ một immutable snapshot cũ trong khi writer công bố snapshot mới, có phải thread đó bị data race không?

**Đáp án:** Không, nếu snapshot thực sự bất biến và được công bố an toàn. Reader đang sử dụng phiên bản cũ nhất quán. Yêu cầu đọc bản mới đến đâu là **freshness** nghiệp vụ, cần được xác định riêng.

**Ghi nhớ:** Defensive copy bảo vệ **ranh giới sở hữu dữ liệu**; immutable snapshot bảo vệ **tính nhất quán của phiên bản được đọc**; safe publication bảo đảm **thread khác nhìn thấy phiên bản đã xây dựng hợp lệ**. Muốn đạt thread safety cần kết hợp cả ba khi bài toán yêu cầu, đồng thời đánh giá chi phí và độ mới của snapshot.