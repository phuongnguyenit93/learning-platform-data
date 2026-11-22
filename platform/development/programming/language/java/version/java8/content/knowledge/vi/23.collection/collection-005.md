# Collection.stream(), parallelStream() và spliterator()

## 1. Mục tiêu bài học

`Collection<E>` là giao diện chung của các cấu trúc dữ liệu như `List`, `Set` và `Queue` trong Java. Từ Java 8, giao diện này có ba phương thức đặc biệt quan trọng:

- **`stream()`**: lấy một `Stream<E>` **tuần tự** để lọc, biến đổi và tổng hợp dữ liệu.
- **`parallelStream()`**: lấy một `Stream<E>` **có thể song song** để runtime có cơ hội phân chia việc xử lý.
- **`spliterator()`**: lấy một `Spliterator<E>`, đối tượng mức thấp dùng để **duyệt** và, nếu nguồn hỗ trợ, **tách** công việc trên collection.

Đây đều là API còn được hỗ trợ trong Java hiện đại; không phải kỹ thuật legacy. Ví dụ trong bài dùng JDK 17 trở lên và ghi rõ những API có từ Java 8.

Khi có danh sách khách hàng, ba phương thức trả lời ba nhu cầu khác nhau:

1. Lọc khách hàng đủ điều kiện và lấy email? Dùng `customers.stream()`.
2. Xử lý lượng lớn dữ liệu độc lập, thuần CPU, và đã chứng minh song song có lợi? Cân nhắc `customers.parallelStream()`.
3. Xây dựng nguồn Stream tùy biến, chủ động lấy từng phần tử hoặc phân chia nguồn? Dùng `customers.spliterator()`.

**Nguyên tắc:** Hầu hết code nghiệp vụ nên bắt đầu từ `stream()`. `parallelStream()` không phải “cách viết nhanh hơn” theo mặc định; `spliterator()` là công cụ mức thấp và không cần dùng trực tiếp chỉ để lọc hoặc cộng dữ liệu.

## 2. Chữ ký API và quan hệ giữa ba phương thức

Ba phương thức được định nghĩa trong `java.util.Collection<E>`:

```java
// Chữ ký API để học, không phải chương trình độc lập.
default Stream<E> stream();

default Stream<E> parallelStream();

default Spliterator<E> spliterator();
```

`Stream` thuộc `java.util.stream`, còn `Spliterator` thuộc `java.util`.

| Phương thức | Kiểu trả về | Mục đích | Các phương thức dùng tiếp |
| --- | --- | --- | --- |
| `collection.stream()` | `Stream<E>` | Pipeline tuần tự | `filter`, `map`, `collect`, `count`... |
| `collection.parallelStream()` | `Stream<E>` | Pipeline có thể xử lý song song | Các operation giống `Stream`, nhưng cần lưu ý concurrency |
| `collection.spliterator()` | `Spliterator<E>` | Cursor duyệt/phân chia nguồn | `tryAdvance`, `forEachRemaining`, `trySplit`... |

Ví dụ:

```java
// Mã minh họa, trong chương trình đã import các kiểu tương ứng.
List<String> names = Arrays.asList("An", "Binh", "Chi");

Stream<String> seq = names.stream();
Stream<String> par = names.parallelStream();
Spliterator<String> cursor = names.spliterator();
```

Một `Collection` **không bị biến thành** Stream sau lời gọi này; nó vẫn là collection nguồn. `Stream` cũng không tự sao chép toàn bộ phần tử để tạo một list mới.

### 2.1. Quan hệ với Spliterator

Có thể hình dung:

```text
                     Collection<E>
                           |
                    spliterator()
                           v
                     Spliterator<E>
                      /            \
       StreamSupport.stream(s, false)
                                    StreamSupport.stream(s, true)
                      |                      |
              sequential Stream         parallel-mode Stream

Collection.stream() và Collection.parallelStream()
cung cấp đường vào đơn giản hơn cho nhu cầu thông thường.
```

**Default implementation** của `Collection.stream()` tạo sequential Stream từ spliterator; default implementation của `Collection.parallelStream()` tạo parallel Stream từ spliterator. Collection cụ thể có thể override cách triển khai nếu contract nguồn cần điều đó.

Điểm tinh tế trong Javadoc: `parallelStream()` trả **possibly parallel Stream**; implementation **được phép trả một sequential Stream**. Vì vậy không có hợp đồng chung rằng mọi collection đều trả `isParallel() == true` từ `parallelStream()`.

## 3. stream(): xử lý một collection bằng pipeline tuần tự

`stream()` phù hợp để biểu diễn chuỗi xử lý:

1. **Source:** collection nguồn.
2. **Intermediate operations:** `filter`, `map`, `distinct`, `sorted`... Thường được đánh giá **lazy**.
3. **Terminal operation:** `collect`, `reduce`, `sum` trên primitive stream, `count`, `findFirst` hoặc `forEach`.

Ví dụ:

```java
// Mã minh họa; users là List<String>.
List<String> normalized = users.stream()
    .map(String::trim)
    .filter(s -> s.length() >= 3)
    .map(s -> s.toUpperCase(Locale.ROOT))
    .collect(Collectors.toList());
```

Pipeline có tác dụng tạo **kết quả**; nó không thay đổi các chuỗi trong collection nguồn. Nếu mapper tạo object khác, kết quả chứa object đó; nếu mapper chỉ chuyển tham chiếu đến đối tượng mutable hiện có, kết quả không mặc nhiên là deep copy.

### Ví dụ 1 — CollectionStreamDemo.java

Tạo file **CollectionStreamDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class CollectionStreamDemo {
    public static void main(String[] args) {
        List<String> users = Arrays.asList(
            "an", " Binh ", "Chi", "Dung"
        );

        List<String> normalized = users.stream()
            .map(String::trim)
            .filter(s -> s.length() >= 3)
            .map(s -> s.toUpperCase(Locale.ROOT))
            .collect(Collectors.toList());

        System.out.println("normalized=" + normalized);

        System.out.println("sequential=" +
            users.stream().isParallel());

        System.out.println("parallel=" +
            users.parallelStream().isParallel());

        List<Integer> nums = Arrays.asList(2, 4, 6);
        int sum = nums.stream()
            .mapToInt(Integer::intValue)
            .sum();

        System.out.println("sum=" + sum);
    }
}
```

```bash
javac CollectionStreamDemo.java
java CollectionStreamDemo
```

Đầu ra với `Arrays.asList(...)` trong JDK được dùng:

```text
normalized=[BINH, CHI, DUNG]
sequential=false
parallel=true
sum=12
```

Giải thích:

- Chuỗi `"an"` chỉ có hai ký tự nên bị loại.
- `" Binh "` được trim, rồi chuyển thành `"BINH"`.
- `stream().isParallel()` trả `false`; `parallelStream().isParallel()` trả `true` ở implementation danh sách trong ví dụ. Không dùng kết quả này để khẳng định mọi custom Collection luôn trả parallel Stream.
- `List<Integer>.stream()` có kiểu `Stream<Integer>`. `mapToInt(Integer::intValue)` tạo `IntStream`, giúp dùng `sum()` trên primitive mà không cần accumulator boxed tùy biến.

### 3.1. Stream là một lượt xử lý, không phải collection

Một đối tượng Stream chỉ được dùng để thực hiện **một pipeline terminal**. Sau khi gọi `count()`, `collect()` hoặc `findFirst()`, không gọi terminal operation khác trên **cùng instance Stream**. Nếu muốn tính một chỉ số khác, gọi `collection.stream()` lần nữa để tạo Stream mới từ nguồn.

Ví dụ:

```java
// Đoạn minh họa.
long count = users.stream().count();

List<String> upper = users.stream()
    .map(s -> s.toUpperCase(Locale.ROOT))
    .collect(Collectors.toList());
```

Hai lần `stream()` tạo hai Stream độc lập; bản thân `users` vẫn là collection có thể duyệt lại nếu nguồn cho phép.

### 3.2. Dữ liệu không được sao chép tự động

`users.stream()` không chụp snapshot bất biến của collection. Nếu cần snapshot, phải tạo bản sao chủ động theo yêu cầu và hiểu tính chất **shallow copy**. Chẳng hạn, `new ArrayList<>(users)` tạo container mới nhưng không clone các object mutable ở trong.

Không thay đổi collection nguồn trong lúc pipeline đang tiêu thụ nó nếu nguồn không hỗ trợ thao tác như vậy; nguyên tắc này quan trọng với cả tuần tự lẫn song song.

## 4. parallelStream(): khả năng chia và thực thi song song

`parallelStream()` tạo một pipeline có thể chạy phần công việc trên nhiều task. Runtime thường dùng khả năng phân chia nguồn (qua Spliterator) để chia các phần tử, xử lý rồi kết hợp kết quả.

**Không suy từ “parallel” ra “nhanh hơn”.** Chi phí tạo/chia/gộp task, barrier của các operation như `sorted` và `distinct`, kích thước dữ liệu, cạnh tranh CPU và công việc trên mỗi phần tử đều ảnh hưởng hiệu năng.

Một số điều **không được bảo đảm**:

- Không bảo đảm một thread cho mỗi phần tử.
- Không bảo đảm mapper chạy theo đúng encounter order.
- Không bảo đảm `parallelStream()` luôn tạo parallel Stream đối với mọi implementation của `Collection`.
- Không bảo đảm tốt hơn `stream()` với các bài toán nhỏ.
- Không bảo đảm code sửa một biến mutable dùng chung sẽ an toàn.

Các behavioral parameters của Stream (lambda, predicate, mapper) nên **non-interfering** và nhìn chung **stateless**. Điều này giúp runtime tự thay đổi cách phân chia mà kết quả không đổi.

### 4.1. Chuyển chế độ trên Stream

Hai phương thức của Stream liên quan:

```java
// Đoạn minh họa; items là một Collection<String>.
Stream<String> a = items.stream().parallel();
Stream<String> b = items.parallelStream().sequential();
```

- `parallel()` đặt chế độ song song cho pipeline.
- `sequential()` đặt chế độ tuần tự.
- `isParallel()` kiểm tra chế độ hiện tại.
- `unordered()` là khái niệm **khác**: bỏ ràng buộc encounter order nếu có, không trực tiếp bật/tắt chế độ parallel.

Với các collection chuẩn, `collection.stream().parallel()` thường biểu diễn ý định gần với `collection.parallelStream()`. Tuy nhiên, đừng phụ thuộc vào việc mọi implementation có cách xây pipeline giống hệt nhau.

## 5. Ví dụ 2 — tổng hợp song song mà không sửa state dùng chung

Tạo file **ParallelAggregationDemo.java**:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelAggregationDemo {
    public static void main(String[] args) {
        List<Integer> values = IntStream.rangeClosed(1, 10)
            .boxed()
            .collect(Collectors.toList());

        int seqSum = values.stream()
            .mapToInt(Integer::intValue)
            .sum();

        int parSum = values.parallelStream()
            .mapToInt(Integer::intValue)
            .sum();

        List<Integer> evenSquares = values.parallelStream()
            .filter(n -> n % 2 == 0)
            .map(n -> n * n)
            .collect(Collectors.toList());

        Map<String, Integer> groupSums = values.parallelStream()
            .collect(Collectors.groupingBy(
                n -> n % 2 == 0 ? "even" : "odd",
                TreeMap::new,
                Collectors.summingInt(Integer::intValue)
            ));

        System.out.println("sequentialSum=" + seqSum);
        System.out.println("parallelSum=" + parSum);
        System.out.println("evenSquares=" + evenSquares);
        System.out.println("groupSums=" + groupSums);
    }
}
```

```bash
javac ParallelAggregationDemo.java
java ParallelAggregationDemo
```

Stdout:

```text
sequentialSum=55
parallelSum=55
evenSquares=[4, 16, 36, 64, 100]
groupSums={even=30, odd=25}
```

**Vì sao đúng khi parallel?**

1. `filter` và `map` không thay đổi nguồn hay biến ngoài.
2. `sum()` có cơ chế tổng hợp phù hợp với phép cộng; các giá trị trong ví dụ không gây overflow.
3. `Collectors.toList()` được thư viện phối hợp qua các container tích lũy trung gian và combiner thích hợp. Không cần một `ArrayList` dùng chung cho nhiều thread.
4. Nguồn `List` có encounter order, nên kết quả collector danh sách giữ thứ tự giá trị mặc dù mapper có thể chạy theo thứ tự khác.
5. `groupingBy(..., TreeMap::new, ...)` tạo bản đồ tổng theo hai khóa `even` và `odd`, đồng thời dùng `TreeMap` để hiển thị khóa theo thứ tự xác định.

Với số `1..10`, số chẵn có tổng `30`, số lẻ có tổng `25`. Việc `parallelSum` bằng `sequentialSum` thể hiện tính đúng đắn của phép tổng trong trường hợp cụ thể, **không phải bằng chứng** rằng phiên bản song song nhanh hơn.

### Anti-pattern: mutable result dùng chung trong forEach

```java
// SAI: ví dụ minh họa, không chạy trên dữ liệu thật.
List<Integer> result = new ArrayList<>();

values.parallelStream().forEach(n -> result.add(n * n));
```

`ArrayList` không phải cấu trúc cho phép nhiều thread thêm phần tử đồng thời không có đồng bộ hóa. Mã có thể bị race, bỏ sót phần tử hoặc hỏng trạng thái.

Thay thế:

```java
// Đoạn minh họa; values đã được khai báo.
List<Integer> result = values.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
```

Nếu cần chính xác một `ArrayList`, dùng `Collectors.toCollection(ArrayList::new)`. Với Java 16+, `Stream.toList()` trả danh sách không chỉnh sửa được; `Collectors.toList()` đã có từ Java 8 nhưng không cam kết một kiểu concrete/mutability nhất định.

## 6. spliterator(): duyệt và phân chia ở mức thấp

`Spliterator<E>` đại diện cho một phạm vi phần tử có thể duyệt. Nó không phải một collection mới hay một snapshot tự động.

Các phương thức quan trọng:

| API | Vai trò | Trả về |
| --- | --- | --- |
| `tryAdvance(action)` | Xử lý **tối đa một** phần tử kế tiếp; nếu hết thì không gọi action | `boolean` |
| `forEachRemaining(action)` | Xử lý **toàn bộ phần tử còn lại** của cursor | `void` |
| `trySplit()` | Thử tách một phần công việc chưa xử lý sang Spliterator mới | `Spliterator<E>` hoặc `null` |
| `estimateSize()` | Ước lượng số phần tử còn lại | `long` |
| `getExactSizeIfKnown()` | Số lượng chính xác nếu biết theo `SIZED`; không biết thì `-1` | `long` |
| `characteristics()` | Bitmask của các đặc tính nguồn | `int` |
| `hasCharacteristics(mask)` | Kiểm tra các characteristic được yêu cầu | `boolean` |

### 6.1. tryAdvance và forEachRemaining dùng chung vị trí duyệt

Giả sử nguồn có các phần tử `["A","B","C","D"]`:

```text
cursor ban đầu: A | B | C | D

tryAdvance(print)    -> in A, trả true
forEachRemaining     -> in B, C, D; trả void
tryAdvance(print)    -> không còn gì, trả false
```

`forEachRemaining` không quay về đầu. Một Spliterator đã hết không có `reset()` chung. Muốn duyệt lại, lấy một Spliterator mới từ collection nguồn khi điều đó được phép.

### 6.2. trySplit chỉ chia công việc còn lại

Nếu nguồn có `ORDERED`, `trySplit()` khi thành công tạo một Spliterator cho **prefix** của phạm vi chưa duyệt; cursor gốc quản lý phần còn lại. Nếu không thể tách, nó trả `null`.

Không có bảo đảm rằng mỗi lần tách chia đúng đôi hoặc một Spliterator tương ứng một thread. `trySplit()` **không tự chạy song song**; nó chỉ cung cấp khả năng cho một scheduler hoặc Stream runtime.

## 7. Ví dụ 3 — quan sát thứ tự, kích thước và chia nguồn

Tạo file **SpliteratorInspectionDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Spliterator;

public class SpliteratorInspectionDemo {
    public static void main(String[] args) {
        List<String> items = Arrays.asList("A", "B", "C", "D");
        Spliterator<String> cursor = items.spliterator();

        System.out.println("ordered=" +
            cursor.hasCharacteristics(Spliterator.ORDERED));

        System.out.println("sized=" +
            cursor.hasCharacteristics(Spliterator.SIZED));

        System.out.println("initialEstimate=" +
            cursor.estimateSize());

        boolean first = cursor.tryAdvance(
            s -> System.out.println("first=" + s)
        );

        System.out.println("advanced=" + first);
        System.out.println("remainingEstimate=" +
            cursor.estimateSize());

        Spliterator<String> prefix = cursor.trySplit();
        List<String> remaining = new ArrayList<>();

        if (prefix != null) {
            prefix.forEachRemaining(remaining::add);
        }

        cursor.forEachRemaining(remaining::add);

        System.out.println("remaining=" + remaining);
        System.out.println("exhausted=" +
            cursor.tryAdvance(x ->
                System.out.println("unreachable=" + x)));
    }
}
```

```bash
javac SpliteratorInspectionDemo.java
java SpliteratorInspectionDemo
```

Stdout:

```text
ordered=true
sized=true
initialEstimate=4
first=A
advanced=true
remainingEstimate=3
remaining=[B, C, D]
exhausted=false
```

Đầu tiên, `tryAdvance` đã tiêu thụ `A`. Phần còn lại là `B,C,D`. Nếu `trySplit()` thành công, mã duyệt prefix trước, suffix sau; nếu thất bại, cursor vẫn chứa toàn bộ phần còn lại. Với nguồn có encounter order, cả hai trường hợp đều đưa ra `[B,C,D]`.

`SIZED` giúp biết số lượng phần tử còn lại của nguồn này. Nhưng **không suy ra mọi Spliterator đều SIZED**; `estimateSize` có thể chỉ là một ước lượng tùy implementation.

### 7.1. Một Spliterator không tự là multi-threaded

Gọi `forEachRemaining` chỉ duyệt các phần tử còn lại theo contract. Muốn phân phối các phần việc cho nhiều thread, ứng dụng phải có cơ chế quản lý. Trong nghiệp vụ phổ biến, để `parallelStream()` điều phối thường đơn giản hơn việc tự gọi `trySplit` và quản lý các task.

Không chia sẻ cùng một Spliterator thông thường cho nhiều thread đồng thời gọi `tryAdvance` nếu implementation không công bố khả năng hỗ trợ.

## 8. Encounter order: không đồng nghĩa với chế độ parallel

**Encounter order** là thứ tự duyệt có ý nghĩa của nguồn (ví dụ thứ tự vị trí trong `List`); chế độ **parallel** là cách tổ chức thực thi.

Một pipeline có thể **ordered và parallel cùng lúc**. Đối với `List`, `parallelStream().map(...).collect(Collectors.toList())` vẫn trả các phần tử theo encounter order. Nhưng `parallelStream().forEach(...)` **không bảo đảm thứ tự các hành động**.

Khi cần các action theo thứ tự, `forEachOrdered` tôn trọng encounter order nếu nguồn có định nghĩa thứ tự. Điều đó không có nghĩa toàn bộ pipeline chạy trong một thread hoặc vẫn có lợi về hiệu năng song song.

### Ví dụ 4 — List, HashSet và LinkedHashSet

Tạo file **EncounterOrderDemo.java**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.Spliterator;
import java.util.StringJoiner;
import java.util.stream.Collectors;

public class EncounterOrderDemo {
    public static void main(String[] args) {
        List<String> words = Arrays.asList("a", "b", "c", "d");

        List<String> collected = words.parallelStream()
            .map(s -> s.toUpperCase(Locale.ROOT))
            .collect(Collectors.toList());

        StringJoiner joined = new StringJoiner(",");
        words.parallelStream()
            .map(s -> s.toUpperCase(Locale.ROOT))
            .forEachOrdered(joined::add);

        Set<String> hash = new HashSet<>(words);
        Set<String> linked = new LinkedHashSet<>(words);

        System.out.println("collected=" + collected);
        System.out.println("orderedAction=" + joined);

        System.out.println("hashSetOrdered=" +
            hash.spliterator()
                .hasCharacteristics(Spliterator.ORDERED));

        System.out.println("linkedHashSetOrdered=" +
            linked.spliterator()
                  .hasCharacteristics(Spliterator.ORDERED));
    }
}
```

```bash
javac EncounterOrderDemo.java
java EncounterOrderDemo
```

Stdout:

```text
collected=[A, B, C, D]
orderedAction=A,B,C,D
hashSetOrdered=false
linkedHashSetOrdered=true
```

`HashSet` không hứa thứ tự duyệt, dù khi in đôi khi có vẻ ổn định. `LinkedHashSet` giữ thứ tự duyệt theo contract của lớp. `List` cũng có encounter order rõ ràng. Trong ví dụ, `StringJoiner` được cập nhật qua `forEachOrdered`, nơi các action được phối hợp theo thứ tự; **không thay thành `parallel().forEach(joined::add)`**, vì cập nhật đồng thời vào `StringJoiner` không an toàn.

Để nối chuỗi thông thường, dùng `Collectors.joining(",")` thường gọn hơn và không phải quản lý mutable object bên ngoài.

## 9. Những characteristic quan trọng của Spliterator

Một collection có thể cung cấp Spliterator với các cờ khác nhau tùy bản chất nguồn:

| Cờ | Cam kết có ý nghĩa gì? | Không có nghĩa gì? |
| --- | --- | --- |
| `ORDERED` | Có encounter order xác định | Mọi `forEach` song song đều chạy đúng thứ tự |
| `SIZED` | Kích thước chính xác theo contract ở thời điểm phù hợp | Mọi nguồn phải biết trước số lượng |
| `SUBSIZED` | Spliterator tạo ra bằng chia tiếp cũng có `SIZED` | Mọi lần chia đều bằng nhau |
| `DISTINCT` | Phần tử được báo là không trùng theo tiêu chí của API | Mọi `List` đều DISTINCT |
| `SORTED` | Phần tử được sắp theo comparator hoặc natural order phù hợp | Mọi nguồn ORDERED đều SORTED |
| `NONNULL` | Phần tử không null | Mọi collection cấm null |
| `IMMUTABLE` | Nguồn không thể bị sửa cấu trúc theo contract | Luôn có snapshot deep-copy |
| `CONCURRENT` | Nguồn được thiết kế cho thay đổi cấu trúc đồng thời theo contract | Tất cả thao tác trên phần tử và cursor đều thread-safe |

Các cờ thuộc về **Spliterator**, không phải một biến điều khiển để “tăng tốc”. Người viết custom Spliterator phải chỉ khai báo đặc tính mà nguồn thực sự bảo đảm.

### 9.1. Collection cụ thể ảnh hưởng đến Stream và Spliterator

| Nguồn | Thứ tự thường được bảo đảm | Lưu ý |
| --- | --- | --- |
| `ArrayList`, `LinkedList`, `Arrays.asList` | Theo vị trí phần tử | Phù hợp khi cần encounter order |
| `LinkedHashSet` | Theo thứ tự duyệt theo contract của lớp | Kết quả ordered khi xử lý đúng |
| `TreeSet` | Theo thứ tự sắp xếp | Có thể có characteristic `SORTED` |
| `HashSet` | Không bảo đảm | Không dựa vào thứ tự lần chạy |
| Concurrent collections | Theo contract từng lớp | Có thể có ngữ nghĩa duyệt khác với snapshot |

Không suy ra tất cả collection đều có `ORDERED`, `SIZED` hay `CONCURRENT`. Khi thực sự cần biết, đọc contract của implementation và kiểm tra `hasCharacteristics(...)`.

## 10. Sửa nguồn khi Stream đang hoạt động: non-interference

Một nguyên tắc quan trọng của Stream là **không can thiệp vào nguồn** trong khi pipeline đang thực thi nếu nguồn không được thiết kế để hỗ trợ thay đổi đồng thời.

Mẫu nguy hiểm:

```java
// SAI: minh họa anti-pattern trên ArrayList.
List<Integer> source = new ArrayList<>(
    Arrays.asList(1, 2, 3, 4)
);

source.stream().forEach(n -> {
    if (n % 2 == 0) {
        source.remove(n);
    }
});
```

Thay đổi cấu trúc `ArrayList` trong lúc Stream duyệt có thể gây `ConcurrentModificationException` hoặc hành vi không mong muốn. Cơ chế fail-fast chỉ giúp phát hiện một số thay đổi sai, **không phải** cách bảo đảm an toàn luồng.

Tương tự, việc một thread khác sửa `ArrayList` trong khi pipeline đang chạy cũng nguy hiểm. Nếu nguồn là concurrent collection, cần xem ngữ nghĩa duyệt riêng của loại đó; không suy rộng rằng mọi collection có cùng cơ chế nhất quán.

### Ví dụ 5 — hoàn tất xử lý, rồi mới sửa nguồn

Tạo file **SourceSafetyDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class SourceSafetyDemo {
    public static void main(String[] args) {
        List<Integer> source = new ArrayList<>(
            Arrays.asList(1, 2, 3, 4)
        );

        List<Integer> doubled = source.stream()
            .map(n -> n * 2)
            .collect(Collectors.toList());

        // Stream ở trên đã hoàn tất; giờ mới sửa source.
        source.removeIf(n -> n % 2 == 0);

        System.out.println("sourceAfter=" + source);
        System.out.println("collected=" + doubled);
        System.out.println("newStreamCount=" +
            source.stream().count());
    }
}
```

```bash
javac SourceSafetyDemo.java
java SourceSafetyDemo
```

Stdout:

```text
sourceAfter=[1, 3]
collected=[2, 4, 6, 8]
newStreamCount=2
```

`doubled` là collection kết quả riêng. Sau terminal operation, việc `removeIf` xóa số chẵn khỏi `source` không tự xóa các giá trị đã collect. Lần `source.stream()` cuối tạo Stream mới, nên `count()` là `2`.

Nếu các phần tử là **object mutable**, `collect(toList())` chỉ tạo container kết quả; nó không tự deep-copy các object. Muốn snapshot độc lập hoàn toàn cần chiến lược sao chép phù hợp.

## 11. Tạo Stream trực tiếp từ Spliterator với StreamSupport

`StreamSupport.stream(spliterator, parallel)` là công cụ nối một Spliterator với Stream API:

```java
// Đoạn minh họa; spliterator có kiểu Spliterator<T>.
Stream<T> seq = StreamSupport.stream(spliterator, false);
```

- `false` yêu cầu sequential Stream.
- `true` yêu cầu chế độ parallel.
- Stream tiêu thụ Spliterator được cung cấp; không đồng thời duyệt cùng cursor ở chỗ khác.
- Nếu Spliterator không thể chia được, yêu cầu parallel không tự biến nó thành nguồn chia hiệu quả.

### Ví dụ 6 — StreamSupportDemo.java

Tạo file **StreamSupportDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.StreamSupport;

public class StreamSupportDemo {
    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(4, 5, 6);

        int fromCollection = numbers.stream()
            .mapToInt(Integer::intValue)
            .sum();

        int fromSpliterator = StreamSupport.stream(
                numbers.spliterator(),
                false
            )
            .mapToInt(Integer::intValue)
            .sum();

        System.out.println("collectionSum=" + fromCollection);
        System.out.println("spliteratorSum=" + fromSpliterator);
    }
}
```

```bash
javac StreamSupportDemo.java
java StreamSupportDemo
```

Stdout:

```text
collectionSum=15
spliteratorSum=15
```

Hai cách cho cùng kết quả ở ví dụ này. Với `List` thông thường, `numbers.stream()` rõ ràng hơn. `StreamSupport` đặc biệt có giá trị khi bạn **đã có Spliterator** hoặc đang xây nguồn dữ liệu/custom Collection.

### 11.1. Khi tự triển khai Collection

Javadoc `Collection` có lưu ý rằng `stream`/`parallelStream` nên được override khi `spliterator()` không thể trả Spliterator thích hợp về `IMMUTABLE`, `CONCURRENT` hoặc *late-binding*. Đây là trách nhiệm của **người triển khai custom Collection**, không phải điều người dùng `ArrayList` cần làm để lọc một danh sách.

Các quyết định về cách spliterator ràng buộc nguồn và xử lý thay đổi cấu trúc phải tuân thủ contract cụ thể. Không khai báo `IMMUTABLE` hoặc `CONCURRENT` giả chỉ để Stream có vẻ tối ưu hơn.

## 12. Map, primitive streams và các loại nguồn

### 12.1. Map không phải Collection

`Map<K,V>` không mở rộng `Collection`, vì thế không có `map.stream()` trực tiếp. Muốn xử lý một collection view, hãy chọn:

```java
// Đoạn minh họa: map đã khai báo là Map<String, Integer>.
map.keySet().stream();
map.values().stream();
map.entrySet().stream();
```

Khi cần cả khóa và giá trị, `entrySet().stream()` phù hợp hơn việc stream trên key rồi truy vấn lại value. Các view này vẫn có đặc tính và quy tắc can thiệp nguồn tùy implementation Map.

### 12.2. List<Integer>.stream không trả IntStream

`List<Integer>.stream()` là `Stream<Integer>`. Nếu tính toán số nguyên theo primitive API:

```java
// Đoạn minh họa.
int sum = numbers.stream()
    .mapToInt(Integer::intValue)
    .sum();
```

Dùng `IntStream` giúp tránh boxing/unboxing không cần thiết ở nhiều bước. Nếu nguồn có `null`, method reference `Integer::intValue` có thể ném `NullPointerException`; xử lý null theo quy tắc dữ liệu, không âm thầm xem thiếu giá trị là 0.

### 12.3. Những API có yêu cầu phiên bản khác Java 8

`Collection.stream()`, `parallelStream()`, `spliterator()`, `Collectors.toList()`, `StreamSupport.stream(...)` đã tồn tại từ Java 8. Trong Java hiện đại có thêm `Stream.toList()` từ Java 16 và các tiện ích khác; đừng dùng các method mới nếu dự án **bắt buộc biên dịch trên JDK 8**, nhưng cũng không bỏ qua những API hiện hành trong dự án JDK 17+.

## 13. Hiệu năng và chọn đúng chiến lược

Khi cân nhắc `parallelStream()`, xem xét:

1. **Độ lớn dữ liệu:** ít phần tử thường không bù được chi phí chia/gộp.
2. **Chi phí mỗi phép xử lý:** phép tính đơn giản khó tận dụng parallelism bằng tác vụ CPU-heavy độc lập.
3. **Khả năng `trySplit` và cân bằng việc:** một Spliterator khó chia có thể hạn chế parallelism.
4. **Encounter order:** giữ thứ tự ở `forEachOrdered` hoặc `limit` trên ordered parallel stream có thể tạo chi phí.
5. **Tính chất phép gộp:** reduction cần đúng contract identity/associativity.
6. **Shared mutable state:** có thể dẫn tới race, contention hoặc khóa làm mất lợi ích.
7. **Blocking I/O:** database/network không tự trở thành nhanh hơn chỉ vì dùng parallel Stream; cần xem mô hình executor và giới hạn đồng thời phù hợp.
8. **Tải chung của ứng dụng:** song song không chỉ ảnh hưởng một phương thức; còn ảnh hưởng các task khác trên máy.

Không kết luận từ một lần đo bằng `System.currentTimeMillis()`. Khi hiệu năng quan trọng, benchmark bằng công cụ đáng tin cậy (như JMH cho microbenchmark) với dữ liệu, JDK và phần cứng tương đương production.

### 13.1. Khi thứ tự là yêu cầu nghiệp vụ

Nếu cần side effect theo thứ tự danh sách (ghi báo cáo, gửi thông báo tuần tự), `stream()` hoặc `forEachOrdered` có thể phù hợp hơn `parallelStream().forEach`. Nhưng với tác vụ biến đổi dữ liệu, cách dễ duy trì nhất thường là **trả về kết quả** qua `map`/`collect`, thay vì gửi side effect trong lambda.

## 14. So sánh lựa chọn thực tế

| Nhu cầu | Lựa chọn khuyến nghị | Giải thích |
| --- | --- | --- |
| Lọc và map danh sách | `list.stream()` | Đơn giản, tuần tự, dễ kiểm thử |
| Tổng hợp CPU-heavy trên nguồn lớn và đã benchmark | `collection.parallelStream()` | Runtime có thể phân việc nếu lợi ích đủ lớn |
| Cần lấy từng phần tử có kiểm soát | `spliterator.tryAdvance(action)` | Mỗi lần thành công xử lý một phần tử |
| Cần xử lý toàn bộ phần còn lại | `spliterator.forEachRemaining(action)` | Không tạo pipeline Stream |
| Cần thử phân chia nguồn | `spliterator.trySplit()` | Tạo prefix khi hỗ trợ |
| Có custom Spliterator và muốn dùng Stream API | `StreamSupport.stream(spl, false/true)` | Kết nối API mức thấp với Stream |
| Cần thứ tự action theo List | `forEachOrdered` hoặc pipeline tuần tự | `forEach` song song không hứa thứ tự |
| Xử lý key/value của Map | `map.entrySet().stream()` | Map không kế thừa Collection |
| Tính tổng boxed Integer | `stream().mapToInt(...).sum()` | Dùng primitive stream phù hợp |

## 15. Những lỗi thường gặp

**Lỗi 1 — nghĩ `parallelStream()` chắc chắn nhanh hơn.** Thực tế phải xét kích thước, công việc trên mỗi phần tử, overhead và nguồn có dễ chia không. Hãy đo.

**Lỗi 2 — nghĩ `parallelStream()` bắt buộc luôn trả parallel Stream.** `Collection` Javadoc cho phép trả possibly parallel, bao gồm sequential Stream.

**Lỗi 3 — ghi vào một `ArrayList` dùng chung từ `parallelStream().forEach(...)`.** Đây là shared mutable state có thể race. Dùng collector đúng hợp đồng.

**Lỗi 4 — nghĩ parallel Stream luôn mất thứ tự.** Có thể vẫn ordered; điều cần phân biệt là encounter order và thứ tự hành động của từng terminal operation.

**Lỗi 5 — dựa vào thứ tự của `HashSet`.** `HashSet` không cam kết thứ tự; dùng nguồn ordered khi thứ tự có ý nghĩa.

**Lỗi 6 — nghĩ `spliterator()` trả `Stream`.** Nó trả `Spliterator<E>`, là đối tượng duyệt/phân chia khác với pipeline.

**Lỗi 7 — bỏ qua `trySplit() == null`.** Không phải mọi nguồn đều có thể tách được.

**Lỗi 8 — coi `forEachRemaining` là tự động đa luồng.** Phương thức này duyệt phần tử còn lại, không tự tạo scheduler parallel.

**Lỗi 9 — sửa collection nguồn trong lambda của stream.** Có thể gây can thiệp nguồn hoặc `ConcurrentModificationException`. Tách bước đọc và bước cập nhật.

**Lỗi 10 — tái dùng Stream đã tiêu thụ.** Sau terminal operation, tạo Stream mới từ collection.

**Lỗi 11 — mặc định mọi Spliterator có `ORDERED` hoặc `SIZED`.** Các characteristic phụ thuộc nguồn; kiểm tra contract và cờ.

**Lỗi 12 — tạo `map.stream()` trực tiếp trên Map.** Chọn `entrySet()`, `keySet()` hoặc `values()` trước.

**Lỗi 13 — nghĩ `collect(toList())` là deep-copy.** Nó thu thập giá trị/tham chiếu vào một container, không sao chép sâu từng object.

**Lỗi 14 — bật parallel cho blocking I/O mà không kiểm soát tài nguyên.** Điều này có thể tăng contention hoặc áp lực lên hệ thống ngoài.

**Lỗi 15 — dùng `estimateSize()` làm phép kiểm tra chắc chắn có phần tử.** Với nguồn không `SIZED`, đây có thể chỉ là ước lượng; muốn duyệt hãy dùng `tryAdvance`.

## 16. Câu hỏi tự kiểm tra

**Câu 1:** `Collection.stream()` trả kiểu gì?  
**Đáp án:** `Stream<E>` tuần tự.

**Câu 2:** `Collection.parallelStream()` có bắt buộc trả stream chạy song song không?  
**Đáp án:** Không; contract mô tả là *possibly parallel Stream*.

**Câu 3:** `Collection.spliterator()` có trả Stream không?  
**Đáp án:** Không; trả `Spliterator<E>` dùng để duyệt hoặc phân chia nguồn.

**Câu 4:** Vì sao `List` đang parallel vẫn có thể tạo `List` kết quả theo đúng thứ tự?  
**Đáp án:** Encounter order của nguồn vẫn được duy trì khi terminal operation/collector có contract bảo toàn thứ tự.

**Câu 5:** `tryAdvance` trả gì nếu đã hết phần tử?  
**Đáp án:** `false` và không gọi action.

**Câu 6:** `trySplit()` trả `null` có phải lỗi?  
**Đáp án:** Không; việc không chia được là hợp lệ.

**Câu 7:** Có nên dùng `values.parallelStream().forEach(result::add)` khi result là `ArrayList` chung?  
**Đáp án:** Không, vì nhiều thread có thể ghi vào cùng một container không thread-safe.

**Câu 8:** Muốn xử lý cả key và value từ `Map<String,Integer>` bằng Stream, viết gì?  
**Đáp án:** `map.entrySet().stream()`.

**Câu 9:** `LinkedHashSet` và `HashSet` có cùng bảo đảm về thứ tự duyệt không?  
**Đáp án:** Không. `LinkedHashSet` có thứ tự duyệt theo contract; `HashSet` không cam kết.

**Câu 10:** Một Stream đã gọi `count()` có dùng lại để `collect()` được không?  
**Đáp án:** Không; tạo Stream mới từ collection.

**Câu 11:** Nếu `parallelStream()` tạo kết quả đúng, đã đủ lý do dùng nó chưa?  
**Đáp án:** Chưa. Cần kiểm tra tính phù hợp về workload, thứ tự, an toàn tài nguyên và benchmark hiệu năng.

**Câu 12:** `StreamSupport.stream(collection.spliterator(), false)` có bắt buộc phải dùng thay `collection.stream()` không?  
**Đáp án:** Không. Với Collection thông thường, `collection.stream()` dễ đọc và là lựa chọn ưu tiên.

## 17. Tài liệu chính thức

- [Oracle Java SE 25 — Collection](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html): hợp đồng hiện hành của `stream`, `parallelStream` và `spliterator`.
- [Oracle Java SE 25 — Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): lazy pipeline, terminal operations, `forEach` và `forEachOrdered`.
- [Oracle Java SE 25 — Spliterator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html): `tryAdvance`, `forEachRemaining`, `trySplit` và characteristics.
- [Oracle Java SE 25 — StreamSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/StreamSupport.html): tạo Stream từ Spliterator.
- [Oracle Java SE 25 — java.util.stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): non-interference, stateless behavior và encounter order.

**Ghi nhớ:** `Collection.stream()` thích hợp nhất để bắt đầu xử lý dữ liệu thông thường; `Collection.parallelStream()` cho phép runtime song song khi bài toán thực sự có lợi; `Collection.spliterator()` dành cho kiểm soát việc duyệt/chia nguồn ở mức thấp. Cả ba đều cần tôn trọng **đặc tính nguồn**, **thứ tự dữ liệu**, và nguyên tắc **không can thiệp vào collection đang được tiêu thụ**.