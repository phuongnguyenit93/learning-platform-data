# Tính bất biến của đối tượng kết quả và đối tượng đầu vào trong Java

## 1. Mục tiêu: biến đổi dữ liệu mà không gây thay đổi ngoài ý muốn

Trong Java functional programming, các lambda và thao tác Stream thường được dùng để **nhận đầu vào → biến đổi → tạo kết quả**. Chúng giúp giảm phụ thuộc vào mutable state, nhưng **không tự động biến dữ liệu thành bất biến**. Đặc biệt, cần phân biệt hai thuộc tính:

- **Không sửa đối tượng đầu vào**: hàm không thay đổi trạng thái của object được truyền đến, không thêm/xóa phần tử, không gọi setter hay sửa các trường mutable trong input.
- **Đối tượng kết quả bất biến**: sau khi tạo, trạng thái của kết quả không thể bị thay đổi qua những reference mà API cung cấp, kể cả các thành phần lồng nhau được công khai.

Hai thuộc tính này độc lập. Một hàm có thể không sửa đầu vào nhưng trả ra **chính object mutable đầu vào**, khiến thay đổi về sau vẫn tác động lên kết quả. Ngược lại, một hàm có thể làm hỏng đầu vào bằng mutation rồi trả một `String` bất biến: đầu ra bất biến **không sửa được** hậu quả tác dụng phụ đã xảy ra.

~~~java
// Minh họa trong một phương thức, đã import List.
StringBuilder source = new StringBuilder("A");

List<StringBuilder> shared = List.of(source);  // Chia sẻ reference.
List<String> detached = List.of(source.toString()); // Chuỗi immutable.

source.append("B");
System.out.println(shared.get(0));   // AB
System.out.println(detached.get(0)); // A
~~~

Trong cả hai trường hợp, các list bên ngoài không cho sửa cấu trúc, nhưng `shared` vẫn giữ reference đến một `StringBuilder` mutable. `detached` chứa một giá trị `String` được tạo tại thời điểm biến đổi.

**Quy tắc nền tảng:** Không đánh giá tính bất biến chỉ bằng tên kiểu outer collection hoặc việc code có dùng `map()`, `record`, `final` hay không. Hãy xem **toàn bộ trạng thái có thể quan sát, aliasing và cách sao chép dữ liệu**.

## 2. Các khái niệm dễ bị trộn lẫn

| Khái niệm | Diễn giải | Ví dụ |
|---|---|---|
| **Mutable object** | Có trạng thái có thể đổi sau khi tạo | `StringBuilder`, `ArrayList`, mảng `int[]` |
| **Immutable object** | Trạng thái quan sát được không thay đổi sau khi tạo | `String`, `Integer`, value object được thiết kế phù hợp |
| **Unmodifiable collection** | Không cho thay đổi cấu trúc qua API của collection đó | `Stream.toList()`, `List.of()` |
| **Shallow copy** | Tạo cấu trúc mới nhưng có thể giữ reference tới các object con | `new ArrayList<>(source)` |
| **Deep immutability** | Các thành phần mutable có thể truy cập đều được bảo vệ khỏi thay đổi từ bên ngoài | DTO gồm value immutable và danh sách được copy |
| **Aliasing** | Nhiều biến cùng tham chiếu một object | `a.get(0) == b.get(0)` có thể true |
| **Side effect** | Thay đổi bên ngoài giá trị trả về hoặc hành vi quan sát được khác | Ghi log, mutate input, cập nhật counter |
| **Pure function** | Kết quả phụ thuộc đầu vào và không gây observable side effect | Một phép chuẩn hóa String xác định |

**Immutability không đồng nghĩa purity.** Một hàm trả về chuỗi immutable nhưng đọc giờ hiện tại hoặc cập nhật một biến static vẫn không thuần khiết. Ngược lại, một hàm có thể nhận reference tới object mutable nhưng chỉ đọc nó để tạo giá trị mới; tuy không gây mutation, hàm vẫn cần biết input có bị thay đổi bởi thread khác hay không.

**Unmodifiable không đồng nghĩa immutable sâu.** Không gọi được `list.add(...)` không có nghĩa không gọi được `list.get(0).setName(...)`.

## 3. Đầu vào bất biến và không mutate đầu vào

### 3.1. Cách viết dễ suy luận: tạo giá trị mới

Giả sử có record:

~~~java
record Product(String code, int price) {}
~~~

Các component `String` và `int` phù hợp với mô hình value bất biến. Khi cần tăng giá:

~~~java
List<Product> updated = products.stream()
        .map(p -> new Product(p.code(), p.price() + 10))
        .toList();
~~~

Đây là đoạn minh họa bên trong một phương thức có `products` kiểu `List<Product>`. Mỗi `Product` trong kết quả được tạo mới, còn các phần tử gốc không bị sửa. Lợi ích là có thể so sánh bản cũ và bản mới, viết test đơn giản, tránh thay đổi dữ liệu ở một thành phần khác đang giữ reference tới bản cũ.

### 3.2. Cách viết có side effect bị giấu trong map

~~~java
// MÃ CẢNH BÁO: giả sử MutableProduct có getPrice/setPrice.
List<MutableProduct> changed = products.stream()
        .map(p -> {
            p.setPrice(p.getPrice() + 10);
            return p;
        })
        .toList();
~~~

Dù code gọi `map`, nó vẫn **sửa object đầu vào**. Nhiều reference khác có thể quan sát giá mới. Nếu pipeline chạy lại trên cùng các object, giá có thể bị cộng thêm lần nữa. Trong parallel stream, nếu cùng object được chia sẻ, tình huống có thể phức tạp hơn vì race condition.

Không phải mọi mutation đều bị cấm. Với entity persistence cần cập nhật thật, hãy làm rõ thao tác ở tầng nghiệp vụ (vòng lặp hoặc command với transaction), thay vì khiến một phép biến đổi kỳ vọng tạo giá trị mới lại có tác dụng phụ ẩn.

## 4. Chương trình Java 17: kết quả chia sẻ đối tượng và kết quả tách rời

Lưu thành **`InputOutputImmutabilityDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class InputOutputImmutabilityDemo {
    public static void main(String[] args) {
        List<StringBuilder> input = new ArrayList<>();
        input.add(new StringBuilder("alpha"));
        input.add(new StringBuilder("beta"));

        List<StringBuilder> shared = input.stream().toList();
        List<String> snapshot = input.stream()
                .map(sb -> sb.toString().toUpperCase(Locale.ROOT))
                .toList();

        input.get(0).append("!");
        input.add(new StringBuilder("gamma"));

        System.out.println("input=" + input);
        System.out.println("shared=" + shared);
        System.out.println("snapshot=" + snapshot);

        try {
            shared.add(new StringBuilder("delta"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("shared.add=blocked");
        }

        shared.get(0).append("?");
        System.out.println("inputAfterEdit=" + input);
        System.out.println("snapshotAfterEdit=" + snapshot);
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac InputOutputImmutabilityDemo.java
java InputOutputImmutabilityDemo
~~~

Stdout:

~~~text
input=[alpha!, beta, gamma]
shared=[alpha!, beta]
snapshot=[ALPHA, BETA]
shared.add=blocked
inputAfterEdit=[alpha!?, beta, gamma]
snapshotAfterEdit=[ALPHA, BETA]
~~~

**Phân tích:**

1. `shared` được lấy bằng `toList()` nên **không sửa được cấu trúc list**, nhưng các `StringBuilder` bên trong vẫn mutable.
2. `snapshot` được tạo bằng `StringBuilder.toString()` và `String.toUpperCase(Locale.ROOT)`, cho các phần tử kiểu `String` bất biến.
3. Khi thêm `gamma` vào list đầu vào sau khi thu thập, hai list đã thu thập không có thêm phần tử. Đây là snapshot về **cấu trúc đã thu thập**.
4. Khi sửa nội dung `StringBuilder` đầu tiên, thay đổi nhìn thấy qua `shared` vì chúng tham chiếu cùng object. `snapshot` giữ giá trị `ALPHA` và không đổi.
5. `shared.add(...)` ném `UnsupportedOperationException`. Nhưng `shared.get(0).append("?")` vẫn hợp lệ vì đang sửa **object phần tử**, không sửa list.
6. Kết quả chứng minh rằng **unmodifiable outer list không làm bất biến các phần tử** và **không sửa input lúc mapping chưa đủ để kết quả độc lập với input mutable**.

Các dòng `System.out.println` ở chương trình nhằm giải thích; chúng không nằm trong mapper và không bị dùng như một cam kết về thứ tự callback trung gian của Stream.

## 5. Một collection không cho sửa có thể vẫn chia sẻ mutable state

Những API thường gặp:

| API | Tính sửa được của outer list | Sâu đến phần tử? |
|---|---|---|
| `Stream.toList()` (Java 16+) | Unmodifiable | Không |
| `Collectors.toUnmodifiableList()` (Java 10+) | Unmodifiable | Không |
| `List.copyOf(source)` | Unmodifiable snapshot cấu trúc | Không |
| `Collections.unmodifiableList(backing)` | Unmodifiable **view** | Không; thay đổi backing vẫn có thể nhìn thấy |
| `Collectors.toCollection(ArrayList::new)` | Mutable `ArrayList` | Không |
| `Collectors.toList()` | Không cam kết loại list hay tính sửa được | Không |

**View so với snapshot cấu trúc:**

~~~java
List<String> backing = new ArrayList<>(List.of("a"));
List<String> view = Collections.unmodifiableList(backing);
List<String> snapshot = List.copyOf(backing);
backing.add("b");

System.out.println(view);     // [a, b]
System.out.println(snapshot); // [a]
~~~

Đây là đoạn code minh họa với imports `java.util.List`, `java.util.ArrayList`, `java.util.Collections`. `Collections.unmodifiableList` chặn thay đổi qua view, nhưng view vẫn phản ánh backing. `List.copyOf` cho một snapshot cấu trúc, không tự cập nhật theo thêm/xóa về sau.

**Copy cấu trúc không phải deep copy:**

~~~java
StringBuilder item = new StringBuilder("draft");
List<StringBuilder> copy = List.copyOf(List.of(item));
item.append("-edited");
System.out.println(copy.get(0)); // draft-edited
~~~

`List.copyOf` không clone object `StringBuilder`; nguồn và kết quả vẫn dùng chung reference. Khi xây API bất biến, phải xem đối tượng phần tử có setter, collection, mảng hoặc state mutable nào không.

## 6. Record và final không tự bảo đảm deep immutability

Record có component được lưu trong field `private final`, nhưng `final` giữ **reference**, không khóa trạng thái object được tham chiếu.

~~~java
record Report(String name, List<Integer> scores) {}

List<Integer> scores = new ArrayList<>(List.of(2, 3));
Report report = new Report("A", scores);
scores.add(99);

System.out.println(report.scores()); // [2, 3, 99]
~~~

Nếu constructor record không copy phòng vệ, caller vẫn sửa được list thông qua reference nguồn. Để bảo vệ ở ranh giới vào:

~~~java
record ScoreSnapshot(String name, List<Integer> scores) {
    public ScoreSnapshot {
        scores = List.copyOf(scores);
    }
}
~~~

`List.copyOf` tạo list unmodifiable và snapshot về các phần tử ở thời điểm copy. Vì `Integer` là immutable, model này không lộ mutable reference ở tầng scores. Nhưng nếu thay `Integer` bằng `MutablePerson` thì các phần tử vẫn có thể đổi; cần chuyển từng phần tử thành immutable DTO.

### 6.1. Chương trình Java 17: defensive copy và đầu ra độc lập

Lưu thành **`DefensiveSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class DefensiveSnapshotDemo {
    record InputGroup(String name, List<Integer> values) {}

    record ResultGroup(String name, List<Integer> values, int total) {
        public ResultGroup {
            values = List.copyOf(values);
        }
    }

    static ResultGroup transform(InputGroup input) {
        List<Integer> copied = List.copyOf(input.values());
        int sum = copied.stream().mapToInt(Integer::intValue).sum();
        return new ResultGroup(input.name(), copied, sum);
    }

    public static void main(String[] args) {
        List<Integer> sourceValues = new ArrayList<>(List.of(2, 3));
        List<InputGroup> source = new ArrayList<>();
        source.add(new InputGroup("A", sourceValues));

        List<ResultGroup> output = source.stream()
                .map(DefensiveSnapshotDemo::transform)
                .toList();

        sourceValues.add(99);
        source.add(new InputGroup("B", List.of(7)));

        System.out.println("sourceValues=" + sourceValues);
        System.out.println("sourceSize=" + source.size());
        System.out.println("outputSize=" + output.size());
        System.out.println("output=" + output);

        try {
            output.get(0).values().set(0, 100);
        } catch (UnsupportedOperationException ex) {
            System.out.println("inner.set=blocked");
        }

        try {
            output.add(new ResultGroup("X", List.of(), 0));
        } catch (UnsupportedOperationException ex) {
            System.out.println("outer.add=blocked");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DefensiveSnapshotDemo.java
java DefensiveSnapshotDemo
~~~

Stdout:

~~~text
sourceValues=[2, 3, 99]
sourceSize=2
outputSize=1
output=[ResultGroup[name=A, values=[2, 3], total=5]]
inner.set=blocked
outer.add=blocked
~~~

**Giải thích chi tiết:**

- `InputGroup` giữ reference đến `sourceValues` mutable; record không chặn caller sửa nguồn.
- `transform` lấy bản copy trước khi tính tổng, rồi trả `ResultGroup` với danh sách phòng vệ. `ResultGroup` còn tự copy trong constructor để bảo vệ những caller khác ngoài pipeline này.
- `sourceValues.add(99)` sau khi thu thập không làm đổi `ResultGroup.values()`; thêm `InputGroup` vào source cũng không thay đổi outer `output`.
- `output` không cho thêm phần tử; danh sách `values` bên trong cũng không cho `set`.
- Với `String` và `Integer` bất biến trong object graph của ví dụ, kết quả có thể xem là immutable theo dữ liệu công khai.
- Việc copy một nguồn **đang bị sửa đồng thời** vẫn cần cơ chế snapshot/synchronization phù hợp; `List.copyOf` không tự tạo transaction snapshot.

## 7. Mảng là mutable: cần copy ở hai chiều

Mảng Java luôn cho thay đổi phần tử, kể cả khi một record chứa trường array `final`:

~~~java
record UnsafePacket(byte[] data) {}

byte[] raw = {1, 2};
UnsafePacket packet = new UnsafePacket(raw);
raw[0] = 9;
System.out.println(packet.data()[0]); // 9
~~~

Đây là đoạn minh họa. `UnsafePacket` giữ reference cũ đến mảng; caller có thể sửa thông qua `raw` hoặc accessor `data()`.

Để ngăn sửa dữ liệu nội bộ từ ngoài:

~~~java
record Packet(byte[] data) {
    public Packet {
        data = data.clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
~~~

Copy ở **constructor** tránh caller sửa trạng thái qua mảng đầu vào. Copy ở **accessor** tránh caller lấy được mảng nội bộ rồi sửa nó. Với kiểu custom chứa `List<MutableItem>`, cũng phải xem cách copy **từng object phần tử** và các collection lồng sâu.

Một chi tiết quan trọng: record chứa mảng vẫn có semantics `equals()/hashCode()` mặc định đối với mảng, vốn **không tự so sánh nội dung phần tử**. Nếu thiết kế value object có equality theo nội dung mảng, cần định nghĩa chính sách equality phù hợp ngoài việc copy phòng vệ.

## 8. Không sửa input vẫn có thể gây side effect

Một mapper có thể tạo `String` mới mà vẫn làm việc ngoài dữ liệu đầu vào:

~~~java
// Minh họa với externalCounter là state của ứng dụng.
List<String> result = names.stream()
        .map(name -> {
            externalCounter.incrementAndGet();
            return name.toUpperCase(Locale.ROOT);
        })
        .toList();
~~~

Ở đây input String không bị sửa và kết quả cũng là String bất biến, nhưng callback **thay đổi externalCounter**, nên không phải pure function. Các nguồn side effect/nondeterminism khác gồm:

- Ghi log, ghi file, gọi database/network.
- Đọc thời gian, random hoặc trạng thái môi trường khiến cùng input có thể tạo output khác.
- Thay đổi cache, static field, mutable collection ngoài pipeline.
- Sửa chính collection nguồn trong lúc stream duyệt.
- Gọi method trông như getter nhưng lại có side effect.

**Lưu ý về Stream:** các callback trung gian như trong `map` hoặc `peek` không nên chứa side effect **bắt buộc phải chạy với mọi phần tử**. Short-circuiting có thể dừng sớm và các tối ưu hóa hợp lệ có thể bỏ qua những callback không cần cho kết quả.

~~~java
// Không dùng như cơ chế audit bắt buộc:
long count = records.stream()
        .peek(this::audit)
        .count();
~~~

Với nguồn có kích thước biết trước, `count()` có thể suy được kết quả mà không duyệt từng phần tử, nên `peek` không chắc được gọi.

### 8.1. Final/effectively final không nghĩa là object bất biến

~~~java
final List<String> log = new ArrayList<>();

List<String> values = List.of("a", "b").stream()
        .map(s -> {
            log.add(s);
            return s.toUpperCase(Locale.ROOT);
        })
        .toList();
~~~

Biến `log` là `final`: không thể gán reference khác cho `log`, nhưng hoàn toàn có thể gọi `log.add`. Vì vậy lambda có capture một biến *effectively final* vẫn có thể **stateful** hoặc tác động mutable state từ ngoài.

Nếu chạy song song, việc cập nhật `ArrayList` chung còn có thể gây race. Ưu tiên stateless, non-interfering callbacks và tránh mutation trong mapper khi bài toán chỉ là biến đổi giá trị.

## 9. Reduce và object kết quả bất biến

Một chương trình tổng hợp dữ liệu có thể dùng accumulator bất biến để tránh chia sẻ mutable state. Với `reduce`, còn phải bảo đảm **identity đúng**, phép gộp có **tính kết hợp**, và accumulator/combiner tương thích.

### 9.1. Chương trình Java 17: không sửa giao dịch hay Summary

Lưu file **`ImmutableReductionDemo.java`**:

~~~java
import java.util.List;

public class ImmutableReductionDemo {
    record Transaction(String code, int amount) {}

    record Summary(long count, long total) {
        Summary plus(Transaction transaction) {
            return new Summary(count + 1, total + transaction.amount());
        }

        Summary combine(Summary other) {
            return new Summary(count + other.count, total + other.total);
        }
    }

    public static void main(String[] args) {
        List<Transaction> source = List.of(
                new Transaction("A", 7),
                new Transaction("B", 5),
                new Transaction("C", -2)
        );

        Summary summary = source.parallelStream()
                .reduce(
                        new Summary(0, 0),
                        Summary::plus,
                        Summary::combine
                );

        List<Transaction> increased = source.stream()
                .map(t -> new Transaction(t.code(), t.amount() + 1))
                .toList();

        System.out.println("source=" + source);
        System.out.println("increased=" + increased);
        System.out.println("summary=" + summary);
    }
}
~~~

Lệnh chạy:

~~~bash
javac ImmutableReductionDemo.java
java ImmutableReductionDemo
~~~

Stdout:

~~~text
source=[Transaction[code=A, amount=7], Transaction[code=B, amount=5], Transaction[code=C, amount=-2]]
increased=[Transaction[code=A, amount=8], Transaction[code=B, amount=6], Transaction[code=C, amount=-1]]
summary=Summary[count=3, total=10]
~~~

**Tại sao mẫu này hợp lý?**

1. `Transaction` gồm `String` và `int`, không có mutable component công khai; mapper tạo các record mới thay vì sửa giao dịch nguồn.
2. `Summary` chỉ chứa hai `long`. `plus` và `combine` luôn tạo `Summary` mới; không mutate shared identity.
3. `new Summary(0,0)` là identity đúng cho phép cộng của `count`/`total`. `Summary::combine` có tính kết hợp và `plus` tương thích với combiner.
4. `parallelStream` có thể chia dữ liệu và gộp kết quả theo nhóm khác nhau, nhưng giá trị logic vẫn là 3 giao dịch và tổng `7+5-2=10`.
5. Immutability hạn chế một số lỗi đa luồng; nó **không tự bảo đảm** shared service, dữ liệu nguồn hoặc side effect ở nơi khác đều thread-safe.
6. Với dữ liệu tài chính hoặc phạm vi số lớn, cần quy định overflow/rounding và cân nhắc `BigDecimal` hoặc đơn vị nguyên nhỏ nhất; ví dụ chỉ minh họa số nguyên nhỏ.

### 9.2. Không mutate identity trong reduce

~~~java
// CẢNH BÁO: tránh dùng mutable StringBuilder chung làm identity.
StringBuilder result = words.parallelStream().reduce(
        new StringBuilder(),
        (builder, word) -> builder.append(word),
        (left, right) -> left.append(right)
);
~~~

Dù có thể viết code kiểu trên, nó không phù hợp với giả định identity/accumulator của `reduce` khi object bị mutate và chia sẻ, đặc biệt trong stream song song. Khi muốn nối chuỗi, ưu tiên `Collectors.joining()`; khi cần thu thập mutable collection, dùng `collect` với collector đúng hợp đồng.

**Phân biệt:** immutable reduction là một cách ghép các **giá trị**. Mutable collection được thu thập theo hợp đồng `collect`, không nên tự dùng `reduce` để lén sửa một object dùng chung.

## 10. Thiết kế DTO bất biến theo từng tầng

Giả sử cần chuyển các entity nguồn có thể sửa thành kết quả công khai:

~~~text
MutableOrder -> OrderView
                 ├── id: String
                 └── lines: List<LineView>
                                 ├── sku: String
                                 └── quantity: int
~~~

Có thể định nghĩa:

~~~java
record LineView(String sku, int quantity) {}

record OrderView(String id, List<LineView> lines) {
    public OrderView {
        lines = List.copyOf(lines);
    }
}
~~~

Nếu các `LineView` là record mới từ mutable line nguồn, `String` và primitive fields đã ổn định, list bên trong được copy và list bên ngoài được thu thập bằng `toList()`, mô hình output có thể đạt mục tiêu bất biến sâu đối với dữ liệu công khai.

~~~java
// Minh họa: inputOrders là List<MutableOrder> với các getter thích hợp.
List<OrderView> result = inputOrders.stream()
        .map(order -> new OrderView(
                order.getId(),
                order.getLines().stream()
                        .map(line -> new LineView(
                                line.getSku(), line.getQuantity()))
                        .toList()
        ))
        .toList();
~~~

Đoạn minh họa chưa có định nghĩa `MutableOrder` nên không phải file chạy độc lập. Nó cho thấy ranh giới chuyển đổi:

1. Không giữ reference trực tiếp đến `MutableOrder` hoặc `MutableLine`.
2. Chuyển dữ liệu từng phần tử sang immutable value object.
3. Copy cấu trúc của danh sách lồng trong constructor của `OrderView`.
4. Thu thập outer list unmodifiable.
5. Validate `null` và điều kiện nghiệp vụ trước khi đưa vào `List.copyOf` (API từ chối phần tử null).

Nếu một field của `LineView` là `byte[]` hay `List<MutableItem>`, phải copy tiếp. Không có hàm `deepCopy()` tổng quát, đúng nghĩa nghiệp vụ, an toàn cho mọi object Java.

## 11. Bất biến và xử lý song song

Trong Stream song song, Java có thể gọi các callback ở nhiều thread và chia nguồn thành các phần. Vì vậy:

- Input value bất biến giảm nguy cơ worker này sửa dữ liệu worker khác đang đọc.
- Mapper tạo object mới giảm aliasing và phụ thuộc thứ tự.
- Accumulator bất biến/associative giúp `reduce` gộp kết quả các nhánh đúng hợp đồng.
- Nhưng callback vẫn có thể dùng cache, database, static field hoặc log mutable bên ngoài, nên code chưa chắc thuần khiết.
- Nếu thread khác đang sửa chính nguồn collection mà không có cơ chế đồng bộ, việc duyệt/copy không tự tạo snapshot nhất quán.
- `Collections.unmodifiableList(backing)` chỉ là unmodifiable view, không ngăn thread khác sửa `backing`.

**Không dùng việc không thay đổi biến capture làm chứng cứ thread safety.** `final List<String> list` vẫn có thể bị sửa qua `list.add`. Nếu nhiều thread cùng dùng list, cần chọn cấu trúc, synchronization hoặc mô hình ownership phù hợp.

Cũng không nên giả định một kết quả immutable có thể được xây dựng từ input đang bị mutate song song mà không có cơ chế đồng bộ hóa. Có thể cần khóa khi chụp snapshot, versioning, hoặc bảo đảm nguồn ổn định trong thời gian biến đổi.

## 12. Khi mutation là nghiệp vụ: tách hiệu ứng khỏi phần biến đổi

Ứng dụng vẫn cần ghi database, gửi sự kiện, cập nhật trạng thái, tạo file. Java functional programming không bắt buộc loại bỏ mọi mutation, nhưng nên **đặt side effect tại ranh giới dễ nhận biết**:

~~~java
// Minh họa với các phương thức đã được định nghĩa trong lớp ứng dụng.
List<OrderView> views = orders.stream()
        .map(this::toImmutableView)
        .toList();

repository.saveAll(views);
~~~

Biến đổi và I/O được tách thành hai bước. `toImmutableView` nên tạo dữ liệu mới mà không sửa nguồn, còn `saveAll` thể hiện thao tác ghi ở nơi có thể kiểm soát transaction và exception.

Nếu cần cập nhật từng entity thật sự, một vòng lặp hoặc command có hợp đồng rõ số lần và thứ tự thao tác có thể dễ đọc hơn việc giấu setter trong `map()`. Đặc biệt, không sử dụng `peek` để đảm bảo một hành động nghiệp vụ bắt buộc với tất cả phần tử: callback của thao tác trung gian có thể bị bỏ qua hoặc pipeline có thể dừng sớm.

## 13. Lỗi phổ biến và cách sửa

| Sai lầm | Vì sao nguy hiểm? | Hướng sửa |
|---|---|---|
| Cho rằng `map` luôn thuần khiết | Mapper vẫn có thể gọi setter/ghi log | Xem thân callback, tránh mutation |
| Dùng `map(x -> x)` rồi mong snapshot độc lập | Cùng reference đầu vào | Tạo DTO/value mới, copy khi cần |
| Tin `Stream.toList()` làm mọi phần tử bất biến | Chỉ chặn sửa cấu trúc outer list | Chuyển phần tử mutable thành immutable |
| Cho rằng `List.copyOf` deep-copy | Chỉ copy cấu trúc, không clone phần tử | Copy từng tầng mutable |
| Cho rằng record/final là bất biến sâu | Field final vẫn trỏ đến object mutable | Defensive copy và accessor an toàn |
| Copy đầu vào mà lộ mảng qua getter | Caller vẫn sửa mảng nội bộ | Copy mảng ở constructor và accessor |
| Không mutate input nên chắc chắn pure | Có thể mutate state ngoài/đọc clock/random | Kiểm soát mọi side effect |
| Dùng captured `ArrayList` trong parallel mapper | Race, thứ tự callback không xác định | Stateless callback/collector đúng hợp đồng |
| Mutate identity trong parallel reduce | Gộp nhóm sai, aliasing | Accumulator bất biến hoặc collector |
| Copy list đang bị sửa đồng thời rồi tin là snapshot giao dịch | Không có bảo đảm nhất quán thời điểm | Đồng bộ hoặc snapshot phù hợp |
| Không validate dữ liệu vì object immutable | Trạng thái ban đầu vẫn có thể sai | Validate trong constructor/rành giới API |
| Dựa vào output unmodifiable để cấm sửa input | Hai object graph có thể chia sẻ alias | Xác định ownership và copy |

### 13.1. Phân biệt cấu trúc bất biến và nội dung được quan sát

Một list `List<StringBuilder>` có thể không cho thêm/xóa phần tử, nhưng `get(0).append` vẫn thay đổi giá trị ở phần tử. Khi cần immutable snapshot, hãy xác định **cụ thể object nào có thể sửa được** và **reference nào còn ở ngoài**. Nếu không phân tích aliasing, hai cấu trúc nhìn giống nhau có thể có semantics rất khác.

### 13.2. Không lạm dụng copy

Copy tất cả graph ở mọi bước có thể tốn CPU/bộ nhớ và khiến quản lý identity/quan hệ object phức tạp. Đặt copy ở **ranh giới ownership và API public** thay vì sao chép tràn lan. Với các immutable leaf như `String`, việc giữ reference không tạo nguy cơ mutation. Còn mutable value như `Date`, mảng, list con hoặc entity có setter cần chính sách copy rõ ràng.

## 14. Checklist review một pipeline

1. Input có object mutable, array, list/map lồng, setter hoặc reference đang được nơi khác giữ không?
2. Mapper có thay đổi input hoặc trạng thái bên ngoài không?
3. Kết quả là object mới hay chính reference cũ?
4. Nếu outer result unmodifiable, các phần tử bên trong có immutable không?
5. Có cần snapshot độc lập cấu trúc nguồn không? Có đang dùng view hay copy?
6. Constructor của DTO/record đã copy các mutable components ở đầu vào chưa?
7. Getter/accessor có lộ reference mutable ra ngoài không?
8. Có tầng nested collection/mutable element nào chưa được bảo vệ không?
9. Dữ liệu có thể bị thay đổi đồng thời trong lúc chuyển đổi không?
10. Callback có phụ thuộc thời gian, random, I/O, counter hay cache không?
11. Có sử dụng Stream parallel, short-circuit hoặc tối ưu hóa terminal khiến side effect khó dự đoán không?
12. Nếu dùng reduce, identity, associativity và combiner có hợp lệ không?
13. Có cần đặt mutation thật ở tầng command/transaction thay vì trong map/filter không?
14. Test đã thử sửa input **sau khi tạo output**, sửa phần tử output và sửa list/mảng qua accessor chưa?

Một kiểm thử hữu ích cho bất biến sâu là: tạo output; đổi các object đầu vào qua mọi reference có sẵn; thử sửa outer collection; thử sửa nested collection; thử sửa mutable leaf; xác nhận output vẫn đúng contract. Test đó xác minh hành vi thay vì dựa vào tên class.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `Stream.toList()` có bảo đảm phần tử `StringBuilder` bất biến không?

**Câu 2.** `map(x -> x)` có tạo snapshot độc lập đối tượng đầu vào không?

**Câu 3.** Hàm không sửa input nhưng ghi log/đọc đồng hồ có chắc là pure function không?

**Câu 4.** Vì sao record có `List<Integer>` vẫn có thể bị thay đổi nếu constructor không copy?

**Câu 5.** `List.copyOf(List.of(new StringBuilder("x")))` có tạo deep immutable graph chưa?

**Câu 6.** `final ArrayList<String>` có ngăn `add` không?

**Câu 7.** Vì sao cần copy `byte[]` ở cả constructor và accessor?

**Câu 8.** Khi nào nên dùng `Collectors.joining()` thay vì `reduce` với identity `StringBuilder` mutable?

**Câu 9.** Nếu tạo snapshot bằng `List.copyOf` lúc thread khác sửa nguồn, Java có tự bảo đảm transaction snapshot không?

**Câu 10.** Cách giữ source mutable ở persistence nhưng trả API output bất biến nên tổ chức ra sao?

**Đáp án ngắn:**

1. Không; chỉ outer list unmodifiable.
2. Không; trả lại chính reference cũ.
3. Không; side effect và nondeterminism phải được xét riêng.
4. Record giữ reference đến list mutable; caller có thể thay đổi list sau đó.
5. Chưa; phần tử `StringBuilder` vẫn mutable và được chia sẻ.
6. Không; final ngăn gán lại reference, không ngăn sửa object.
7. Để tránh caller sửa trạng thái qua mảng đầu vào hoặc mảng lấy từ getter.
8. Khi muốn ghép nhiều chuỗi bằng mutable accumulation đúng hợp đồng, dùng collector phù hợp.
9. Không; cần kiểm soát concurrency và nguồn ổn định khi copy.
10. Chuyển entity qua mapper tạo value DTO mới, copy nested mutable data, trả outer collection theo contract và tách side effect ghi dữ liệu.

## 16. Nguồn tham khảo chính thức

- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `map`, `toList`, `reduce` và giới hạn bảo đảm callback.
- [Java SE 17 — java.util.stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): stateless/non-interfering behavioral parameters, side effects và parallelism.
- [Java SE 17 API — List](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html): `copyOf`, immutable collection factories.
- [Java SE 17 API — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): collector cho mutable accumulation và `joining`.
- [Java SE 17 — Records](https://docs.oracle.com/en/java/javase/17/language/records.html): records, compact constructors và component accessors.

**Ghi nhớ:** Không sửa đối tượng đầu vào và trả kết quả bất biến là **hai bảo đảm riêng**. Một pipeline `map` có thể chia sẻ reference mutable; `Stream.toList()` chỉ chặn chỉnh sửa danh sách bên ngoài. Muốn một kết quả bất biến ổn định, hãy dùng **kiểu giá trị immutable**, tạo object mới theo ý định, **defensive copy mọi tầng mutable cần công khai**, và tránh side effects ẩn trong các callback.