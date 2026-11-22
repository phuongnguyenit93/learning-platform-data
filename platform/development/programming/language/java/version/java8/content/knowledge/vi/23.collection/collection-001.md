# Iterable.forEach và Iterator.forEachRemaining trong Java 8

> **Chủ đề:** Collection. `Iterable.forEach(Consumer)` và `Iterator.forEachRemaining(Consumer)` được bổ sung từ Java 8 và vẫn là API hiện hành. Bài học tập trung vào cơ chế duyệt, trạng thái con trỏ, mutation an toàn, exception và cách chọn API. Các ví dụ dùng cú pháp Java 8, tương thích JDK 17+.

## 1. Hai interface, hai mục đích

`Iterable<T>` mô tả một **nguồn có thể cung cấp iterator** thông qua `iterator()`. `List`, `Set` và nhiều collection là `Iterable`. Nó cũng cung cấp default method:

```java
default void forEach(Consumer<? super T> action);
```

Default implementation có ý nghĩa tương đương với:

```java
for (T element : this) {
    action.accept(element);
}
```

Nghĩa là thực hiện hành động trên các phần tử của `Iterable`, theo thứ tự duyệt nếu thứ tự ấy được định nghĩa. Ngoại lệ từ action được chuyển cho caller. `forEach` trả `void`, không tạo collection mới và không tự trả một giá trị tổng hợp.

`Iterator<E>` quản lý **một con trỏ của một lượt duyệt**:

```java
boolean hasNext();
E next();
default void forEachRemaining(Consumer<? super E> action);
default void remove();
```

`hasNext` cho biết còn phần tử; `next` trả phần tử kế tiếp và dịch con trỏ. `forEachRemaining` chỉ thực hiện action trên **phần chưa tiêu thụ**. Default implementation tương đương về ý nghĩa:

```java
while (hasNext()) {
    action.accept(next());
}
```

Một implementation có thể override hai default method để tối ưu, nên không phụ thuộc chi tiết vòng lặp thực thi bên trong ngoài hợp đồng công khai.

## 2. Điểm khác nhau quan trọng nhất: bắt đầu từ đâu?

```java
List<String> colors = Arrays.asList("red", "green", "blue");

// Duyệt collection:
colors.forEach(System.out::println);
// red
// green
// blue

// Duyệt phần còn lại của một iterator đã có:
Iterator<String> it = colors.iterator();
String first = it.next(); // first = "red"
it.forEachRemaining(System.out::println);
// green
// blue

System.out.println(it.hasNext()); // false
```

`Iterable.forEach` làm việc trên nguồn; với `ArrayList` thông thường, mỗi lượt duyệt có thể có iterator mới. `Iterator.forEachRemaining` dùng chính instance iterator hiện tại và **không đọc lại phần đã lấy bằng `next()`**.

Sơ đồ:

```text
Iterable<List<String>>
     |-- forEach(action) ----------------> toàn bộ các phần tử được duyệt
     |
     |-- iterator() --> Iterator cursor
                              |
                              |-- next() --> tiêu thụ "red"
                              |
                              |-- forEachRemaining(action)
                                            --> "green", "blue"
```

Một iterator đã duyệt hết không thể “reset” bằng cách gọi `forEachRemaining` lần nữa. Với `ArrayList`, hãy gọi `list.iterator()` để có một lượt duyệt mới. Tuy nhiên, interface `Iterable` **không bảo đảm mọi nguồn đều có thể phát lại cùng dữ liệu nhiều lần**; một nguồn dữ liệu tùy chỉnh có thể chỉ dùng một lượt.

## 3. Bảng so sánh nhanh

| Đặc điểm | `Iterable.forEach` | `Iterator.forEachRemaining` |
| --- | --- | --- |
| Nơi khai báo | `java.lang.Iterable` | `java.util.Iterator` |
| Đối tượng nhận lệnh | Iterable, ví dụ `List` | Iterator cụ thể đã được lấy từ nguồn |
| Điểm bắt đầu | Các phần tử của Iterable trong lượt gọi | Vị trí hiện tại của iterator |
| Có thể xử lý sau một lệnh `next()`? | Không phụ thuộc cursor bên ngoài đó | Có; chỉ xử lý phần còn lại |
| Tham số | `Consumer<? super T>` | `Consumer<? super E>` |
| Trả về | `void` | `void` |
| Thứ tự | Theo iteration order nếu được định nghĩa | Theo iteration order của iterator nếu được định nghĩa |
| Khi action ném exception | Chuyển exception ra caller | Chuyển exception; trạng thái sử dụng iterator tiếp theo **không được quy định** |
| Được sửa nguồn từ action không? | Không, trừ khi implementation quy định chính sách riêng | Không; kể cả gọi `iterator.remove()` trong action, trừ chính sách riêng |
| Mặc định chạy song song? | Không | Không |

**Lưu ý:** `Map.forEach` và `Stream.forEach` là các API khác, dù cùng có chữ `forEach`.

## 4. Lambda, method reference và thứ tự duyệt

```java
List<String> names = Arrays.asList("An", "Binh", "Chi");

names.forEach(name -> System.out.println(name));
names.forEach(System.out::println);
```

`System.out::println` là method reference phù hợp với `Consumer<String>`. `Consumer.accept` không trả về giá trị nghiệp vụ. JavaDoc yêu cầu các action thực hiện theo iteration order **nếu nguồn có quy định thứ tự đó**.

| Nguồn | Có thể dựa vào thứ tự gì? |
| --- | --- |
| `ArrayList` và `LinkedList` | Thứ tự của List |
| `LinkedHashSet` | Thứ tự lặp được collection xác định |
| `TreeSet` | Thứ tự theo comparator hoặc tự nhiên |
| `HashSet` | Không có thứ tự lặp được cam kết |
| `CopyOnWriteArrayList` iterator | Thứ tự của snapshot tại thời điểm tạo |
| `ConcurrentLinkedQueue` iterator | Weakly consistent khi có update đồng thời |

Không được viết unit test dựa vào thứ tự `HashSet.toString()` vì nó tình cờ giống nhau qua nhiều lần chạy.

### `return` trong callback không phải `break`

```java
names.forEach(name -> {
    if ("Binh".equals(name)) {
        return; // Chỉ kết thúc lần gọi lambda hiện tại.
    }
    System.out.println(name);
});
// In "An", rồi "Chi".
```

Muốn dừng toàn bộ khi gặp `Binh`, dùng vòng lặp:

```java
for (String name : names) {
    if ("Binh".equals(name)) break;
    System.out.println(name);
}
// Chỉ in "An".
```

Không dùng `RuntimeException` làm “mẹo break” cho xử lý bình thường. Chọn cấu trúc điều khiển diễn đạt đúng ý định.

## 5. Khi nào `Iterator.forEachRemaining` đặc biệt hữu ích?

Một trường hợp thực tế là cần xử lý riêng header hoặc record đầu tiên:

```java
List<String> lines = Arrays.asList("HEADER", "row-1", "row-2");
Iterator<String> cursor = lines.iterator();

if (!cursor.hasNext()) {
    throw new IllegalArgumentException("Missing header");
}
String header = cursor.next();
if (!"HEADER".equals(header)) {
    throw new IllegalArgumentException("Invalid header");
}

cursor.forEachRemaining(row -> System.out.println("Process " + row));
// Process row-1
// Process row-2
```

Bản chất của API: “Tôi **đã có** một iterator đang ở một vị trí cụ thể; hãy xử lý hết phần còn lại.” Nếu gọi `lines.forEach` thay thế, header sẽ bị xử lý lại từ đầu.

Nếu iterator đã hết, `forEachRemaining` không gọi action nữa. Nếu gọi `next()` khi đã hết, `Iterator.next` có thể ném `NoSuchElementException`.

## 6. Chương trình Java hoàn chỉnh

Chương trình sau kiểm tra đủ hành vi duyệt toàn bộ, duyệt phần còn lại, tạo lượt mới, xóa bằng Iterator, xóa theo predicate và snapshot iterator. Không có race giữa các thread, vì vậy stdout là xác định.

Tạo tệp `IterationActionsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class IterationActionsDemo {
    public static void main(String[] args) {
        List<String> colors = new ArrayList<>(
                Arrays.asList("red", "green", "blue"));

        List<String> all = new ArrayList<>();
        colors.forEach(all::add);

        Iterator<String> cursor = colors.iterator();
        String consumed = cursor.next();
        List<String> remaining = new ArrayList<>();
        cursor.forEachRemaining(remaining::add);
        boolean exhausted = !cursor.hasNext();

        List<String> fresh = new ArrayList<>();
        colors.forEach(fresh::add);

        List<Integer> odds = new ArrayList<>(
                Arrays.asList(1, 2, 3, 4, 5, 6));
        Iterator<Integer> removing = odds.iterator();
        while (removing.hasNext()) {
            if (removing.next() % 2 == 0) {
                removing.remove();
            }
        }

        List<Integer> removeIfExample = new ArrayList<>(
                Arrays.asList(1, 2, 3, 4, 5, 6));
        removeIfExample.removeIf(n -> n % 2 == 0);

        CopyOnWriteArrayList<String> cow =
                new CopyOnWriteArrayList<>(Arrays.asList("A", "B"));
        Iterator<String> snapshot = cow.iterator();
        cow.add("C");
        List<String> snapshotValues = new ArrayList<>();
        snapshot.forEachRemaining(snapshotValues::add);

        List<String> nulls = Arrays.asList("a", null, "b");
        List<String> nullSafe = new ArrayList<>();
        nulls.forEach(x -> nullSafe.add(x == null ? "(null)" : x));

        System.out.println("Iterable.forEach: " + all);
        System.out.println("Consumed first: " + consumed);
        System.out.println("Iterator remaining: " + remaining);
        System.out.println("Cursor exhausted: " + exhausted);
        System.out.println("Fresh traversal: " + fresh);
        System.out.println("Iterator.remove odds: " + odds);
        System.out.println("removeIf odds: " + removeIfExample);
        System.out.println("Snapshot traversal: " + snapshotValues);
        System.out.println("CopyOnWrite current: " + cow);
        System.out.println("Null-safe traversal: " + nullSafe);

        if (!all.equals(Arrays.asList("red", "green", "blue"))
                || !consumed.equals("red")
                || !remaining.equals(Arrays.asList("green", "blue"))
                || !exhausted || !fresh.equals(all)
                || !odds.equals(Arrays.asList(1, 3, 5))
                || !removeIfExample.equals(Arrays.asList(1, 3, 5))
                || !snapshotValues.equals(Arrays.asList("A", "B"))
                || !cow.equals(Arrays.asList("A", "B", "C"))
                || !nullSafe.equals(Arrays.asList("a", "(null)", "b"))) {
            throw new AssertionError("Unexpected traversal result");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch bằng JDK 17+ với kiểm tra tương thích Java 8:

```bash
javac --release 8 IterationActionsDemo.java
java IterationActionsDemo
```

Stdout đã kiểm chứng trên OpenJDK 24:

```text
Iterable.forEach: [red, green, blue]
Consumed first: red
Iterator remaining: [green, blue]
Cursor exhausted: true
Fresh traversal: [red, green, blue]
Iterator.remove odds: [1, 3, 5]
removeIf odds: [1, 3, 5]
Snapshot traversal: [A, B]
CopyOnWrite current: [A, B, C]
Null-safe traversal: [a, (null), b]
Checks passed.
```

Đọc kết quả:

- `all` chứa ba màu; `cursor` đã lấy `red` bằng `next` nên chỉ đưa `green` và `blue` cho `forEachRemaining`.
- Sau khi duyệt hết, `cursor.hasNext()` bằng `false`. Một lượt `colors.forEach` mới trên `ArrayList` lại trả đủ ba phần tử.
- `Iterator.remove` và `removeIf` tạo các danh sách số lẻ giống nhau; chúng có phạm vi sử dụng khác nhau.
- Iterator `CopyOnWriteArrayList` chụp dữ liệu `[A,B]` tại thời điểm tạo. Collection sau khi sửa là `[A,B,C]`, nhưng snapshot cũ không thay đổi.
- `null` là dữ liệu có thể có trong một số List. Action ở đây quy định hiển thị `"(null)"` thay vì gọi method trên null.

## 7. Sửa nguồn trong khi duyệt: điều KHÔNG nên làm

### 7.1. Không mutate collection trong `Iterable.forEach`

```java
List<Integer> values = new ArrayList<>(
        Arrays.asList(1, 2, 3, 4));

// SAI: sửa cấu trúc collection đang là nguồn cho chính phép duyệt.
values.forEach(n -> {
    if (n % 2 == 0) {
        values.remove(n);
    }
});
```

Đối với `ArrayList`, điều này vi phạm chính sách duyệt và có thể gây `ConcurrentModificationException` hoặc hành vi không xác định. Không dựa vào việc “chạy một lần chưa thấy lỗi”.

Nếu chỉ cần xóa theo điều kiện:

```java
values.removeIf(n -> n % 2 == 0);
// [1, 3]
```

`Collection.removeIf(Predicate)` được giới thiệu từ Java 8 và vẫn là lựa chọn phù hợp cho mục tiêu xóa các phần tử thỏa điều kiện, nếu collection hỗ trợ mutation.

### 7.2. Không gọi `iterator.remove` bên trong action `forEachRemaining`

```java
Iterator<Integer> it = values.iterator();

// SAI: không sửa collection/iterator từ callback forEachRemaining.
it.forEachRemaining(n -> {
    if (n % 2 == 0) {
        it.remove();
    }
});
```

JavaDoc của `Iterator.forEachRemaining` nói hành vi **không được quy định** nếu action sửa collection, **kể cả gọi `remove` hoặc mutator khác của iterator**, trừ khi implementation có chính sách sửa đổi đồng thời riêng.

Dùng vòng lặp có con trỏ được quản lý trực tiếp:

```java
Iterator<Integer> it = values.iterator();
while (it.hasNext()) {
    int n = it.next();
    if (n % 2 == 0) {
        it.remove();
    }
}
```

`Iterator.remove` là **optional operation**; không phải iterator nào cũng hỗ trợ. Một lần `next()` chỉ cho phép gọi `remove()` hợp lệ một lần trước `next()` tiếp theo. `Arrays.asList(...)` có danh sách kích thước cố định, còn iterator snapshot của `CopyOnWriteArrayList` không hỗ trợ `remove`.

**Đặc biệt:** Tài liệu `Iterator.remove` còn nói hành vi không được quy định nếu gọi `remove()` **sau** `forEachRemaining()`. Đừng cố gọi `remove` sau khi duyệt xong để xóa phần tử cuối cùng.

## 8. Exception và phần tử null

Hai method đều nhận `Consumer`; action ném exception thì exception đi ra bên gọi, và các side effect đã thực hiện **không tự được rollback**.

```java
List<String> words = Arrays.asList("A", "B", "C");
List<String> seen = new ArrayList<>();

try {
    words.forEach(word -> {
        if ("B".equals(word)) {
            throw new IllegalStateException("Stop");
        }
        seen.add(word);
    });
} catch (IllegalStateException ex) {
    System.out.println(ex.getMessage());
}
// Với nguồn List này, seen đã chứa "A"; không có rollback.
```

**Điểm khác quan trọng:** Khi action trong `Iterator.forEachRemaining` ném exception, **hành vi dùng tiếp iterator là không được quy định**. Không giả định `it.next()` chắc chắn là phần tử ngay sau phần tử gây lỗi; hãy thiết kế lại quy trình với vòng `while` và checkpoint rõ ràng nếu cần recover từng record.

### 8.1. Action null và phần tử null là hai chuyện khác

```java
List<String> data = Arrays.asList("a", null, "b");

// data.forEach(null);                    // NullPointerException.
// data.iterator().forEachRemaining(null); // NullPointerException.

// Phần tử null được xử lý theo quy tắc nghiệp vụ.
data.forEach(s -> System.out.println(
        s == null ? "(missing)" : s.toUpperCase()));
```

Không phải collection nào cũng chấp nhận phần tử null. Nếu việc thiếu dữ liệu phải báo lỗi thay vì bỏ qua, hãy kiểm tra và xử lý rõ ràng.

## 9. Concurrent modification, fail-fast và snapshot

`ArrayList` iterator được mô tả là **fail-fast**: khi collection bị sửa cấu trúc sau khi iterator được tạo, ngoài các thao tác được phép qua iterator, nó cố phát hiện vi phạm và có thể ném `ConcurrentModificationException`. **Fail-fast chỉ là best-effort**; trong cuộc đua dữ liệu giữa các thread, Java không cam kết exception luôn xuất hiện. Ngoại lệ cũng có thể xảy ra trong một thread duy nhất khi sửa trực tiếp collection lúc duyệt.

**Không thấy CME không có nghĩa đã thread-safe.** Nếu có writer đồng thời, cần đồng bộ hóa nguồn, tạo snapshot theo cơ chế phối hợp phù hợp hoặc dùng collection concurrent có consistency đáp ứng bài toán.

`CopyOnWriteArrayList` là một ví dụ snapshot: Iterator của nó nhìn thấy cấu trúc mảng tại thời điểm tạo. Trong lúc đó có thể cập nhật collection; iterator cũ không quan sát phần tử mới. Snapshot chỉ chụp mảng tham chiếu, **không deep-copy các object mutable**.

Những collection như `ConcurrentLinkedQueue` cung cấp iterator **weakly consistent**: có thể duyệt trong sự hiện diện của các cập nhật hợp lệ, nhưng không bảo đảm ảnh chụp nguyên tử của toàn bộ nguồn. Nếu cần báo cáo chính xác tại một thời điểm, phải thiết kế snapshot/transaction/lock tương ứng.

## 10. Phân biệt với `Stream.forEach` và `Map.forEach`

```java
List<String> names = Arrays.asList("A", "B", "C");

names.forEach(System.out::println);                   // Iterable.forEach
names.parallelStream().forEach(System.out::println);  // Stream.forEach
names.parallelStream().forEachOrdered(System.out::println);
```

`Iterable.forEach` là default method của Iterable (có thể được override). `Stream.forEach` là terminal operation; trên parallel stream **không cam kết encounter order**. `Stream.forEachOrdered` giữ encounter order của Stream nếu có, nhưng điều đó không làm toàn bộ pipeline upstream chạy tuần tự.

`Map<K,V>` không kế thừa `Iterable`. `Map.forEach` nhận `BiConsumer<K,V>`:

```java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("A", 10);
scores.put("B", 20);

scores.forEach((key, value) ->
        System.out.println(key + "=" + value));

// Entry-set là Collection nên có thể dùng Iterable.forEach:
scores.entrySet().forEach(entry ->
        System.out.println(entry.getKey() + "=" + entry.getValue()));
```

Không nhầm lambda hai tham số của `Map.forEach` với Consumer một tham số của `Iterable.forEach`.

## 11. Chọn API cho yêu cầu thực tế

| Yêu cầu | API nên cân nhắc |
| --- | --- |
| Duyệt và thực hiện action trên toàn collection | `Iterable.forEach` hoặc enhanced `for` |
| Đã lấy một vài phần tử của iterator, muốn xử lý phần còn lại | `Iterator.forEachRemaining` |
| Muốn `break`/`continue`, dừng sớm hoặc điều khiển cursor tinh tế | `for` / `while(hasNext())` |
| Cần xóa phần tử trong khi duyệt iterator có hỗ trợ | `next` + `Iterator.remove` trong vòng `while` |
| Cần xóa mọi phần tử theo điều kiện | `Collection.removeIf` |
| Cần biến đổi thành collection mới | `Stream.map/filter/collect` hoặc vòng lặp |
| Cần xử lý song song có điều kiện | `parallelStream` với action/collector thread-safe và logic phù hợp |
| Cần giữ thứ tự action trên parallel Stream ordered | `forEachOrdered` |
| Cần snapshot hoặc tính nhất quán khi writer chạy | Nguồn/snapshot/locking có hợp đồng riêng |

Ví dụ biến đổi thành danh sách khác thay vì side effect trong `forEach`:

```java
List<String> raw = Arrays.asList(" a ", " b ", " c ");
List<String> trimmed = raw.stream()
        .map(String::trim)
        .collect(Collectors.toList());
// [a, b, c]
```

`Collectors.toList()` có từ Java 8; `Stream.toList()` là API ra đời sau Java 8 nên không dùng trong ví dụ cần biên dịch với `--release 8`.

### Đừng mặc định phương thức nào nhanh hơn

`forEachRemaining` không được tài liệu đảm bảo nhanh hơn `Iterable.forEach`. Hiệu năng phụ thuộc class Collection, action, JIT, kích thước dữ liệu, số lần boxing và cách dữ liệu được lưu. Nếu cần đo, dùng **JMH** với warmup, forks, nhiều iterations và workload tương đương. Đừng kết luận từ một lần `System.nanoTime`. Dù hiệu năng tốt hơn, không đánh đổi tính đúng đắn của iterator state hoặc việc sửa nguồn.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Giải pháp |
| --- | --- |
| Gọi `forEachRemaining` tưởng bắt đầu lại từ phần tử đầu | Tạo iterator mới nếu nguồn cho phép |
| Gọi `next` khi đã hết | Kiểm tra `hasNext` |
| Dùng `return` trong lambda để dừng cả vòng | Dùng `for` hoặc `while` có `break` |
| Sửa nguồn trong `Iterable.forEach` | Dùng `removeIf` hoặc thay đổi sau khi duyệt xong |
| Gọi `iterator.remove` trong callback `forEachRemaining` | Dùng vòng `while` và `remove` sau `next` |
| Gọi `remove` sau `forEachRemaining` | Không dựa vào hành vi này; dùng một vòng iterator phù hợp |
| Giả định mọi Iterator cho phép xóa | `remove` có thể ném `UnsupportedOperationException` |
| Tiếp tục iterator sau action ném exception | Không dựa vào trạng thái tiếp theo; dùng cơ chế recover rõ ràng |
| Dựa vào CME làm công cụ đồng bộ | Fail-fast chỉ best-effort |
| Kiểm thử thứ tự của `HashSet` | Dùng collection ordered hoặc so sánh theo tập |
| Coi `CopyOnWriteArrayList` iterator là live view | Iterator thấy snapshot ở lúc tạo |
| Nhầm `Iterable.forEach` với `Stream.parallel().forEach` | Khác thứ tự/parallel semantics |
| Quên xử lý null trong action | Xác định chính sách xử lý dữ liệu thiếu |
| Cho rằng ngoại lệ rollback các side effect | Cần transaction/idempotency nếu nghiệp vụ yêu cầu |

## 13. Câu hỏi tự kiểm tra

1. `Iterable.forEach` được gọi trên List hay Iterator? — **Trên Iterable**, ví dụ List.
2. Với `["A","B","C"]`, sau `next()` trả `A` thì `forEachRemaining` xử lý gì? — **B và C**.
3. Gọi `forEachRemaining` thêm lần nữa trên iterator đã hết có duyệt lại từ đầu? — **Không**.
4. `return` trong lambda `forEach` có dừng cả phép duyệt không? — **Không**.
5. Muốn xóa các số chẵn khỏi `ArrayList`, nên dùng gì? — **`removeIf`** hoặc vòng Iterator với `remove` đúng quy tắc.
6. Có thể gọi `it.remove()` trong action của `it.forEachRemaining` không? — **Không được dựa vào hành vi đó** trừ chính sách riêng.
7. Sau khi action `forEachRemaining` ném exception, có thể chắc chắn dùng `next` để resume đúng không? — **Không**.
8. Iterator `CopyOnWriteArrayList` có thấy phần tử thêm sau khi tạo iterator không? — **Không**, nó là snapshot.
9. `Iterable.forEach` có tự chuyển sang parallel không? — **Không**.
10. `Map.forEach` có nhận Consumer một tham số không? — **Không**, nó nhận BiConsumer gồm key và value.
11. Không thấy `ConcurrentModificationException` có chứng minh code an toàn không? — **Không**, fail-fast best-effort.

## 14. Tài liệu chính thống còn hiệu lực

- [Oracle Java SE 25 — Iterable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Iterable.html): `forEach` và default implementation.
- [Oracle Java SE 25 — Iterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html): `forEachRemaining`, `hasNext`, `next`, `remove` và quy tắc sau exception.
- [Oracle Java SE 25 — ArrayList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayList.html): fail-fast best-effort.
- [Oracle Java SE 25 — Collection](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html): `removeIf`.
- [Oracle Java SE 25 — CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html): snapshot iterator.
- [Oracle Java SE 25 — Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `forEach` và `forEachOrdered`.
- [OpenJDK — Java Microbenchmark Harness](https://github.com/openjdk/jmh): benchmark có kiểm soát nếu hiệu năng là yêu cầu.

**Điểm cần nhớ:** `Iterable.forEach` duyệt các phần tử của nguồn Iterable; `Iterator.forEachRemaining` tiếp tục từ **con trỏ hiện tại**. Cả hai trả `void`, không phải API xóa và không tự bảo vệ việc sửa collection đồng thời.
