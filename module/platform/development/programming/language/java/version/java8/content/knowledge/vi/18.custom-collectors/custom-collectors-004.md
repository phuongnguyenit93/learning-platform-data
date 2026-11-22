# IDENTITY_FINISH, UNORDERED và CONCURRENT trong Java Collector tùy biến

## 1. Vì sao Collector có Characteristics?

Trong Java Stream, `collect(Collector)` là **terminal operation** thực hiện phép *mutable reduction*: duyệt các phần tử rồi tích lũy chúng vào một hoặc nhiều container. Một `Collector<T, A, R>` mô tả cách thực hiện quá trình này thông qua:

- `T`: kiểu phần tử đi vào.
- `A`: kiểu container tích lũy trung gian, đôi khi không lộ ra cho caller.
- `R`: kiểu kết quả cuối mà `collect` trả về.
- `supplier()`: tạo container rỗng.
- `accumulator()`: đưa một phần tử `T` vào container `A`.
- `combiner()`: hợp nhất hai container `A`, đặc biệt khi chạy parallel.
- `finisher()`: chuyển `A` thành `R` sau khi tích lũy xong.

Ngoài bốn hàm, collector có `characteristics()` trả về tập `Set<Collector.Characteristics>`. Các đặc tính này cho Stream framework biết **collector cam kết hành vi gì** và cho phép chọn chiến lược reduction thích hợp. Chúng **không phải chú thích trang trí hoặc cờ bật chế độ tự động**.

Từ Java 8 đến các JDK hiện hành, có đúng **ba enum value** cần học trong `Collector.Characteristics`:

| Characteristic | Cam kết cốt lõi |
| --- | --- |
| `IDENTITY_FINISH` | Finisher thực chất là phép đồng nhất: `A` có thể dùng trực tiếp như `R`, nên framework được phép **bỏ qua bước finisher**. |
| `UNORDERED` | Collector **không cam kết** bảo toàn *encounter order* của các phần tử đầu vào khi xác định kết quả. |
| `CONCURRENT` | Accumulator có thể được gọi **đồng thời từ nhiều thread trên cùng một container `A`** mà vẫn đúng. |

Mỗi cờ là một **hợp đồng với implementation**, không phải một lựa chọn “thử xem có nhanh hơn không”. Khai báo sai có thể khiến mã chạy được trên dữ liệu nhỏ nhưng mất phần tử, trả thứ tự sai, bỏ qua phép biến đổi hoặc phát sinh race condition trên parallel stream.

## 2. Chu trình tích lũy và ý nghĩa của các cờ

Đối với một stream **sequential**, có thể hình dung:

~~~text
supplier() -> container A
  -> accumulator(A, x1)
  -> accumulator(A, x2)
  -> ...
  -> finisher(A) -> kết quả R
~~~

Khi chạy **parallel**, framework có thể tạo nhiều container riêng để các tác vụ xử lý những phần đầu vào, sau đó kết hợp chúng:

~~~text
supplier -> A1    +    supplier -> A2
    |                       |
accumulate nhóm 1      accumulate nhóm 2
    |                       |
    +--- combiner(A1,A2) ---+
                 |
             finisher
                 |
                 R
~~~

Với collector có đặc tính `CONCURRENT` và điều kiện thứ tự phù hợp, implementation **được phép** cho nhiều thread đưa phần tử vào **cùng một container** thay vì tạo và merge nhiều container. Framework không bắt buộc phải dùng chiến lược đó trong mọi lần chạy.

**Hai luật nền tảng không được bỏ qua:**

1. **Identity constraint của combiner:** kết hợp một kết quả đã tích lũy với container rỗng phải cho kết quả tương đương.
2. **Associativity constraint:** cách chia dữ liệu thành các phần và kết hợp các phần không được thay đổi ý nghĩa phép giảm. Với ordered collector, kết quả phải tương đương khi giữ encounter order; với unordered collector, khác biệt chỉ do thứ tự có thể được chấp nhận.

Ví dụ, cộng các số có thể kết hợp theo nhiều cách; còn “lấy phần tử cuối dựa trên ai chạy xong trước” thường **không đáp ứng** quy tắc kết hợp và tính xác định cần có.

## 3. IDENTITY_FINISH: không cần biến đổi container cuối

### 3.1. Khi nào được đánh dấu?

`IDENTITY_FINISH` có nghĩa finisher là phép đồng nhất và có thể được bỏ qua. Nếu đặt đặc tính này, phép ép kiểu không kiểm tra từ `A` sang `R` phải thành công theo hợp đồng Java.

Ví dụ phù hợp:

- `A = List<String>`, `R = List<String>`, container đã là kết quả cần trả.
- `A = Set<Integer>`, `R = Set<Integer>`, không cần tạo loại kết quả khác.
- Factory `Collector.of(supplier, accumulator, combiner)` **tự gắn `IDENTITY_FINISH`** cho dạng ba thành phần đó.

Ví dụ `Collector.of` xây dựng một collector gom thành danh sách:

~~~java
Collector<String, List<String>, List<String>> toList =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
~~~

Đây là **mã minh họa bên trong lớp đã import `Collector`, `ArrayList`, `List`**. `supplier` tạo List rỗng; `accumulator` thêm chuỗi; `combiner` ghép hai list theo thứ tự left rồi right; kết quả cuối chính là List tích lũy, nên không cần finisher chuyển kiểu. Trên nguồn ordered, cách ghép đó giữ encounter order, kể cả khi Stream chia phần để chạy parallel.

### 3.2. Khi nào KHÔNG được đánh dấu?

Nếu container trung gian cần được chuyển sang kiểu khác, collector không có identity finish.

Ví dụ lưu `count` và `sum` vào `long[2]` rồi trả chuỗi báo cáo:

~~~java
Collector<Integer, long[], String> report = Collector.of(
        () -> new long[2],
        (a, n) -> {
            a[0]++;
            a[1] += n;
        },
        (a, b) -> {
            a[0] += b[0];
            a[1] += b[1];
            return a;
        },
        a -> "count=" + a[0] + ", sum=" + a[1],
        Collector.Characteristics.UNORDERED);
~~~

Đây là **đoạn minh họa có import phù hợp**. `A = long[]`, `R = String`: finisher thật sự tạo chuỗi, nên **không được** khai báo `IDENTITY_FINISH`. `UNORDERED` hợp lệ ở đây vì số lượng và tổng không phụ thuộc thứ tự phần tử, giả định không có overflow hay các tác dụng phụ ngoài phép tính.

Nếu khai báo `IDENTITY_FINISH` sai, framework có thể bỏ qua `finisher` và trả thẳng container trung gian; chương trình có thể nhận kiểu sai và gặp `ClassCastException`. Đừng dùng finisher chỉ để ghi log bắt buộc: với identity finish, nó được phép **không được gọi**.

### 3.3. collectingAndThen và finisher

`Collectors.collectingAndThen(downstream, finisher)` bọc một collector rồi áp dụng phép chuyển đổi cuối. Kết quả của collector bọc **không được giả định còn `IDENTITY_FINISH`**, dù downstream có đặc tính đó.

~~~java
Collector<String, ?, List<String>> readOnlyCollector =
        Collectors.collectingAndThen(
                Collectors.toList(),
                Collections::unmodifiableList);
~~~

Đây là **đoạn minh họa** dùng API Java 8. Phép bọc cuối tạo một view không cho sửa qua kết quả trả về. Với custom collector, một bước chốt kết quả, đóng băng cấu trúc hoặc chuyển sang DTO là lý do bình thường để giữ finisher thật sự và **không gắn `IDENTITY_FINISH`**.

**Ghi nhớ:** “`A` và `R` có vẻ cùng tên kiểu” chưa đủ để kết luận identity finish. Cần xem finisher có thực hiện chuyển đổi hoặc tạo đối tượng/giá trị mới quan trọng hay không. Nếu có, không đánh dấu đặc tính đó.

## 4. UNORDERED: chấp nhận bỏ ràng buộc encounter order

### 4.1. Encounter order là gì?

Nhiều nguồn Stream có *encounter order*: `List.stream()` và `Stream.of(...)` thường đưa các phần tử theo thứ tự xác định. Với pipeline ordered, collector cho kết quả là List phải có ngữ nghĩa phù hợp với thứ tự này.

Đặc tính `UNORDERED` nói rằng **collector không cam kết giữ encounter order đầu vào**. Nó có thể phù hợp với:

- Kết quả kiểu Set mà bài toán chỉ quan tâm sự hiện diện/phân biệt phần tử.
- Phép tổng hợp giao hoán như **đếm, cộng, thống kê không phụ thuộc thứ tự**.
- Concurrent set, concurrent map dùng để lưu kết quả theo khóa mà thứ tự đầu vào không có ý nghĩa.

Ngược lại, một collector tạo danh sách `["a", "b", "c"]` theo encounter order **không nên đánh dấu `UNORDERED`** nếu caller yêu cầu đúng thứ tự này.

### 4.2. UNORDERED không có nghĩa tự xáo trộn

- `UNORDERED` không bắt framework đảo thứ tự phần tử; một lần chạy vẫn có thể tình cờ cho cùng thứ tự đầu vào.
- `UNORDERED` không tự kích hoạt `parallel()`.
- `stream.unordered()` là thao tác khai báo stream không cần giữ encounter order; đây là quyết định ở **phía pipeline**, khác với characteristic của **collector**.
- `Set` không bảo đảm có thứ tự duyệt chỉ vì output in ra có vẻ ổn định trong một lần chạy. Nếu cần thứ tự duyệt xác định theo nghiệp vụ, chọn collection thích hợp và **không gắn UNORDERED cho phép giảm vốn cần bảo toàn thứ tự**.

Một ví dụ trực quan:

~~~java
// Có yêu cầu giữ thứ tự: không khai báo UNORDERED.
List<String> names = Stream.of("B", "A", "C")
        .parallel()
        .collect(Collectors.toList());

// Chỉ cần các tên phân biệt, không yêu cầu giữ thứ tự:
Set<String> distinctNames = Stream.of("B", "A", "C")
        .parallel()
        .collect(Collectors.toSet());
~~~

Đây là **mã minh họa**. `names` giữ `[B, A, C]` vì nguồn có encounter order; `distinctNames` là Set có ba phần tử, nhưng không cam kết thứ tự khi duyệt.

## 5. CONCURRENT: an toàn khi accumulator cùng ghi một container

### 5.1. Ý nghĩa chính xác

`CONCURRENT` là lời hứa rằng **nhiều thread được phép đồng thời gọi `accumulator(A, t)` trên cùng một container `A`**. Vì vậy:

- Container `A` và mọi thao tác mà accumulator dùng phải hỗ trợ concurrency đúng cách.
- Không có mutable state bên ngoài thiếu đồng bộ (ví dụ biến đếm thông thường, `ArrayList` chia sẻ).
- `combiner` vẫn phải được triển khai đúng: framework vẫn có thể chọn tạo container riêng và merge.
- Collector phải tuân thủ cả identity/associativity, có xử lý kết hợp dữ liệu song song hợp lệ.

**`parallelStream()` không yêu cầu collector mang `CONCURRENT`.** Collector thông thường (ví dụ tích lũy vào `ArrayList` trong mỗi tác vụ) vẫn có thể được dùng an toàn khi framework tách container riêng cho từng tác vụ rồi kết hợp.

**`CONCURRENT` không đồng nghĩa cứ chạy parallel là luôn dùng một container chung.** Đó là khả năng mà collector cho phép; framework quyết định chiến lược khi chạy.

### 5.2. Điều kiện framework có thể thực hiện concurrent reduction

Theo tài liệu `java.util.stream` của Java hiện hành, việc tích lũy đồng thời vào **cùng container** chỉ phù hợp khi đồng thời có:

1. Pipeline đang chạy **parallel**.
2. Collector có characteristic **`CONCURRENT`**.
3. **Hoặc** stream là **unordered**, **hoặc** collector có characteristic **`UNORDERED`**.

~~~text
Concurrent reduction có thể xảy ra
    = parallel stream
      AND collector.CONCURRENT
      AND (stream unordered OR collector.UNORDERED)
~~~

| Trường hợp | Có thể dùng một container để accumulator chạy đồng thời? |
| --- | --- |
| Sequential stream + collector CONCURRENT/UNORDERED | Không có hoạt động parallel để tận dụng |
| Parallel ordered stream + collector không CONCURRENT | Không; framework có thể chia container rồi combiner |
| Parallel ordered stream + collector chỉ CONCURRENT | Không nên concurrent reduction khi cần giữ encounter order |
| Parallel unordered stream + collector CONCURRENT | Có thể; không bắt buộc |
| Parallel ordered stream + collector CONCURRENT **và** UNORDERED | Có thể; collector chấp nhận không giữ encounter order |

Điều kiện trên giải thích vì sao một collection hỗ trợ concurrency chưa đủ: **thứ tự** cũng quyết định framework có thể đưa nhiều phần tử vào cùng container đồng thời hay không.

### 5.3. Ví dụ collector concurrent an toàn

`ConcurrentHashMap.newKeySet()` tạo một Set hỗ trợ thêm phần tử đồng thời. Collector bên dưới lưu các chuỗi khác nhau mà **không cần giữ thứ tự**:

~~~java
Collector<String, Set<String>, Set<String>> concurrentSet =
        Collector.of(
                () -> ConcurrentHashMap.<String>newKeySet(),
                Set::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED);
~~~

Đây là **đoạn minh họa**; mã chạy hoàn chỉnh nằm ở mục 7. Dùng overload `Collector.of` **không có finisher tường minh**, nên nó tự thêm `IDENTITY_FINISH`. Ta khai báo thêm `CONCURRENT` và `UNORDERED` vì:

- Container thật sự là concurrent Set, `Set::add` tương ứng hỗ trợ nhiều thread trên chính container đó.
- Set đáp ứng bài toán duy nhất, thứ tự gặp không quan trọng.
- Kết quả tích lũy vốn là `Set<String>` cần trả, không chuyển kiểu.

Như mọi cấu trúc dựa trên `ConcurrentHashMap`, ví dụ này **không nhận phần tử `null`**. Điều kiện đầu vào là các chuỗi không null; không nên sao chép collector này vào dữ liệu có null mà không xử lý trước.

## 6. Code chạy được: ba collector với các bộ đặc tính khác nhau

Tạo tệp **CollectorCharacteristicsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class CollectorCharacteristicsDemo {
    public static void main(String[] args) {
        List<String> input = Arrays.asList("b", "a", "c", "a");

        // A = R = List<String>: hợp đồng giữ encounter order.
        Collector<String, List<String>, List<String>> orderedList =
                Collector.of(
                        ArrayList::new,
                        List::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        });

        List<String> ordered = input.parallelStream().collect(orderedList);
        System.out.println("ordered = " + ordered);
        System.out.println("list identity = " + orderedList.characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("list unordered = " + orderedList.characteristics()
                .contains(Collector.Characteristics.UNORDERED));
        System.out.println("list concurrent = " + orderedList.characteristics()
                .contains(Collector.Characteristics.CONCURRENT));

        // A = long[2], R = String: cần finisher và phép cộng không phụ thuộc thứ tự.
        Collector<Integer, long[], String> report =
                Collector.of(
                        () -> new long[2],
                        (state, n) -> {
                            state[0]++;
                            state[1] += n;
                        },
                        (left, right) -> {
                            left[0] += right[0];
                            left[1] += right[1];
                            return left;
                        },
                        state -> "count=" + state[0] + ", sum=" + state[1],
                        Collector.Characteristics.UNORDERED);

        String stats = Arrays.asList(2, 3, 4, 5)
                .parallelStream().collect(report);
        System.out.println("stats = " + stats);
        System.out.println("report identity = " + report.characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("report unordered = " + report.characteristics()
                .contains(Collector.Characteristics.UNORDERED));
        System.out.println("report concurrent = " + report.characteristics()
                .contains(Collector.Characteristics.CONCURRENT));

        // Concurrent Set: thêm đồng thời, không phụ thuộc thứ tự.
        Collector<String, Set<String>, Set<String>> concurrentSet =
                Collector.of(
                        () -> ConcurrentHashMap.<String>newKeySet(),
                        Set::add,
                        (left, right) -> {
                            left.addAll(right);
                            return left;
                        },
                        Collector.Characteristics.CONCURRENT,
                        Collector.Characteristics.UNORDERED);

        Set<String> unique = input.parallelStream().collect(concurrentSet);
        // Dùng TreeSet chỉ để in kết quả xác định, không suy ra thứ tự của unique.
        System.out.println("unique sorted = " + new TreeSet<>(unique));
        System.out.println("set identity = " + concurrentSet.characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));
        System.out.println("set unordered = " + concurrentSet.characteristics()
                .contains(Collector.Characteristics.UNORDERED));
        System.out.println("set concurrent = " + concurrentSet.characteristics()
                .contains(Collector.Characteristics.CONCURRENT));

        // Finisher biến List thành view không sửa được:
        // collector bọc không có IDENTITY_FINISH.
        Collector<String, ?, List<String>> readOnly =
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        Collections::unmodifiableList);
        List<String> view = Arrays.asList("x", "y")
                .stream().collect(readOnly);
        System.out.println("view = " + view);
        System.out.println("view identity = " + readOnly.characteristics()
                .contains(Collector.Characteristics.IDENTITY_FINISH));
    }
}
~~~

Biên dịch trên JDK 17+ và yêu cầu API/bytecode tương thích Java 8:

~~~bash
javac --release 8 CollectorCharacteristicsDemo.java
java CollectorCharacteristicsDemo
~~~

**Stdout kỳ vọng (không phụ thuộc lịch thực thi parallel):**

~~~text
ordered = [b, a, c, a]
list identity = true
list unordered = false
list concurrent = false
stats = count=4, sum=14
report identity = false
report unordered = true
report concurrent = false
unique sorted = [a, b, c]
set identity = true
set unordered = true
set concurrent = true
view = [x, y]
view identity = false
~~~

**Vì sao kết quả đáng tin cậy?**

- Collector List **không khai báo UNORDERED**, combiner ghép `left` trước `right` nên kết quả của ordered stream giữ encounter order.
- Collector thống kê đếm và cộng; kết quả không phụ thuộc chia phần hay hoán đổi thứ tự (với dữ liệu nhỏ không gây overflow). Vì dùng overload có finisher và không truyền IDENTITY_FINISH, `report identity` là `false`.
- Collector Set cho phép tích lũy đồng thời. `TreeSet` chỉ được tạo **sau khi collect hoàn tất** để trình bày kết quả theo alphabet; thứ tự của `unique` bản thân nó không được cam kết.
- Overload `Collector.of(supplier, accumulator, combiner, characteristics...)` tự đánh dấu IDENTITY_FINISH, ngoài hai cờ truyền vào ở ví dụ concurrent Set.
- `collectingAndThen` thực hiện phép biến đổi cuối, nên `view identity` là `false`. View không sửa được về **cấu trúc**, nhưng không tự làm các object được chứa bên trong trở nên bất biến sâu.

## 7. Phân biệt đặc tính Collector với kiểu collection

### 7.1. List, Set, Map không quyết định toàn bộ characteristics

Loại kết quả chỉ là một yếu tố. Một custom collector có thể tạo List nhưng vẫn `UNORDERED` **nếu hợp đồng của chính collector không hứa thứ tự phần tử**. Ngược lại, tạo Set như `LinkedHashSet` để giữ thứ tự chèn có ý nghĩa nghiệp vụ thì **không nên** đánh dấu `UNORDERED` nếu kết quả bắt buộc phải phản ánh encounter order.

`CONCURRENT` nói về **an toàn của accumulator trên một container**, không chỉ nhìn vào tên class. Ví dụ:

- `ArrayList` + `add` không an toàn khi nhiều thread cùng sửa trên một container: **không gắn CONCURRENT**.
- `ConcurrentHashMap.newKeySet()` + `add` đúng cách: có thể gắn `CONCURRENT`.
- `Map<K, List<V>>` mà Map hỗ trợ concurrent **chưa chứng minh** các List giá trị cũng hỗ trợ chỉnh sửa đồng thời.

### 7.2. Các collector có sẵn

| Collector/API | Điều cần biết về characteristics |
| --- | --- |
| `Collectors.toList()` | Hợp đồng giữ encounter order nếu nguồn có thứ tự; đừng tự suy diễn lớp List hay khả năng sửa |
| `Collectors.toSet()` | Collector **UNORDERED**; đừng suy diễn thứ tự Set |
| `Collectors.toCollection(LinkedHashSet::new)` | Chọn kiểu Set giữ thứ tự chèn; không cần ép UNORDERED |
| `Collectors.groupingBy(key)` | Không phải concurrent collector; khi parallel thường tích lũy từng Map rồi merge |
| `Collectors.groupingByConcurrent(key)` | Concurrent **và** unordered collector; trả `ConcurrentMap`, nhưng **List giá trị không được bảo đảm thread-safe sau khi trả về** |
| `Collectors.toConcurrentMap(...)` | Họ collector concurrent, unordered khi phù hợp với bài toán khóa/giá trị; xử lý khóa trùng bằng merge function khi cần |

Không dựa vào lớp cụ thể hay thứ tự Map trả về nếu Javadoc không hứa. Đối với collector tùy biến, **kiểm tra bằng `collector.characteristics()`** và quan trọng hơn là chứng minh các hàm của chính collector đáp ứng đặc tính đã khai báo.

### 7.3. ConcurrentMap không đồng nghĩa mọi giá trị đều an toàn để sửa

Ví dụ minh họa có đủ import:

~~~java
Map<String, List<String>> byFirstChar = words.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                s -> s.substring(0, 1)));
~~~

Đây là **đoạn minh họa**; `words` là `Collection<String>` không có chuỗi null/rỗng. Bản thân kết quả API là `ConcurrentMap`, nhưng các `List` trong value **không có bảo đảm thread-safe để nhiều thread cùng chỉnh sửa sau khi collect**. Không dùng đặc tính `CONCURRENT` của collector để suy ra deep thread safety của toàn bộ object graph.

## 8. Các trường hợp khai báo sai dễ gây lỗi

### Lỗi 1. Gắn CONCURRENT cho ArrayList

~~~java
// KHÔNG dùng: ArrayList.add không an toàn khi cùng một List bị nhiều thread sửa.
Collector<Integer, List<Integer>, List<Integer>> wrong =
        Collector.of(
                ArrayList::new,
                List::add,
                (a, b) -> {
                    a.addAll(b);
                    return a;
                },
                Collector.Characteristics.CONCURRENT,
                Collector.Characteristics.UNORDERED);
~~~

Đây là **mã minh họa cách khai báo sai, không đưa vào production hoặc chạy benchmark**. Vì hai cờ đều được bật, parallel stream có thể gọi accumulator trên **cùng một ArrayList** từ nhiều thread, làm mất dữ liệu hoặc hỏng trạng thái. Nếu cần giữ thứ tự, dùng collector List thông thường không concurrent; nếu cần concurrent và không cần thứ tự, dùng container concurrent thực sự.

### Lỗi 2. Gắn IDENTITY_FINISH cho collector chuyển kiểu

~~~java
// KHÔNG khai báo kiểu này: A = StringBuilder, R = String.
Collector<String, StringBuilder, String> wrong =
        Collector.of(
                StringBuilder::new,
                StringBuilder::append,
                (a, b) -> a.append(b),
                StringBuilder::toString,
                Collector.Characteristics.IDENTITY_FINISH);
~~~

Đoạn này **minh họa lỗi hợp đồng**; không chạy. Nếu framework bỏ finisher, kết quả vẫn là `StringBuilder`, trong khi caller kỳ vọng `String`. Dù hai kiểu `StringBuilder` và `String` đều có cách hiển thị chuỗi, chúng **không** tương đương về kiểu.

### Lỗi 3. Gắn UNORDERED khi cần thứ tự

Nếu xử lý chuỗi log hoặc dựng danh sách có thứ tự, mọi phép merge phải tôn trọng encounter order. Đừng khai báo `UNORDERED` cho phép giảm mà thứ tự là ý nghĩa nghiệp vụ; framework được phép thay đổi thứ tự xử lý khi làm vậy.

### Lỗi 4. Combiner bỏ dữ liệu hoặc thiếu tính kết hợp

~~~java
// Sai: làm mất toàn bộ phần tử của container bên phải.
(left, right) -> left
~~~

Đây là **biểu thức lambda minh họa**, không phải chương trình Java hoàn chỉnh. Ở sequential có thể tình cờ không dùng combiner, nhưng parallel có thể mất nhiều phần tử. Collector muốn chạy đúng phải đáp ứng identity/associativity cả khi framework chia nguồn thành nhiều phần.

### Lỗi 5. Nhầm “collector có CONCURRENT” với “input source thread-safe”

Chia sẻ và sửa một `ArrayList` đầu vào trong lúc nguồn đang được Stream duyệt vẫn có thể vi phạm non-interference, kể cả khi collector dùng concurrent Set. Hãy đảm bảo dữ liệu nguồn được sử dụng nhất quán trong thời gian chạy pipeline; đặc tính của đầu ra **không bảo vệ nguồn**.

### Lỗi 6. Tạo mutable state dùng chung ngoài supplier

~~~java
// Sai ý tưởng: cùng một List bị tái sử dụng cho nhiều lần supplier().
List<String> shared = new ArrayList<>();
Collector<String, List<String>, List<String>> wrong =
        Collector.of(
                () -> shared,
                List::add,
                (a, b) -> {
                    a.addAll(b);
                    return a;
                });
~~~

Đây là **mã minh họa không an toàn**. `supplier()` cần cung cấp một container mới, độc lập cho các lần được gọi. Trả về cùng biến toàn cục có thể làm collector sai ngay cả khi không đánh dấu `CONCURRENT`.

### Lỗi 7. Phụ thuộc số lần supplier/combiner/finisher được gọi

Implementation có thể chọn các kế hoạch phân hoạch hoặc tối ưu khác nhau. Đừng dựa vào số lần callback, thứ tự thời gian gọi, thread thực thi hay side effect như log để định nghĩa ý nghĩa kết quả. Đặc tính giúp framework tối ưu; **chúng không định nghĩa lịch trình cố định**.

### Lỗi 8. Bật parallel chỉ vì thấy cờ CONCURRENT

`parallel()` có overhead chia việc, kết hợp, scheduling và contention; không bảo đảm nhanh hơn sequential. Đo bằng dữ liệu/tải thực tế và tránh các accumulator phải khóa toàn cục nếu không cần. Đặc biệt, tính đúng đắn của kết quả cần được chứng minh trước khi tối ưu hiệu năng.

## 9. Kiểm tra một Collector tự viết

Khi thiết kế collector mới, kiểm tra lần lượt:

1. **Kiểu:** `T`/`A`/`R` là gì? Nếu cần chuyển kiểu cuối, không dùng `IDENTITY_FINISH`.
2. **Supplier:** mỗi lần tạo container rỗng độc lập; tránh chia sẻ mutable state vô tình.
3. **Accumulator:** đưa đúng một phần tử vào container. Với `CONCURRENT`, chứng minh thao tác an toàn khi nhiều thread cùng sửa **chính một container**.
4. **Combiner:** hợp nhất đủ dữ liệu, không bỏ nhánh; kết hợp với container rỗng vẫn tương đương kết quả ban đầu.
5. **Associativity:** thay đổi cách chia input/merge không làm đổi ý nghĩa kết quả. Với collector có thứ tự, merge theo đúng thứ tự phần.
6. **UNORDERED:** chỉ bật nếu việc bỏ encounter order không làm sai yêu cầu.
7. **IDENTITY_FINISH:** chỉ bật khi có thể bỏ finisher và ép `A` thành `R` an toàn.
8. **CONCURRENT:** chỉ bật nếu container/accumulator và mọi state liên quan đều thực sự an toàn với truy cập đồng thời.
9. **Nguồn:** thử cả sequential/parallel, ordered/unordered, nguồn rỗng, trùng lặp, nhiều phần tử và các giá trị biên.
10. **Quy tắc bộ nhớ:** phép collect trên nguồn không giới hạn có thể không kết thúc hoặc tiêu thụ nhiều RAM; nếu chỉ cần một câu trả lời ngắn, cân nhắc terminal short-circuit thích hợp.

### Ví dụ bảng quyết định

| Bài toán | IDENTITY_FINISH | UNORDERED | CONCURRENT |
| --- | --- | --- | --- |
| Danh sách giữ đúng encounter order, trả List tích lũy | Có thể **có** | **Không** | Thường **không** với ArrayList |
| Thống kê số lượng/tổng, container mảng rồi chuyển thành String | **Không** | **Có thể có** | **Không** nếu mảng không hỗ trợ cập nhật đồng thời |
| Set concurrent, chỉ quan tâm phần tử duy nhất | **Có** nếu trả container gốc | **Có** | **Có** khi `add` thực sự thread-safe |
| Kết quả qua finisher tạo view/DTO khác | **Không** | Tùy ý nghĩa | Tùy accumulator/container |

Đặc tính là **cam kết logic**, không phải tổ hợp cờ mặc định. Trong nhiều bài toán, không cần custom collector: dùng `Collectors.toList()`, `toSet()`, `counting()`, `groupingBy()` hoặc `groupingByConcurrent()` khi hợp đồng của chúng đã khớp.

## 10. Tự kiểm tra

**Câu 1.** Tại sao `Collector.of(ArrayList::new, List::add, combiner)` có `IDENTITY_FINISH`?

**Đáp án:** Vì overload ba thành phần dùng chính container tích lũy làm kết quả cuối, không cần finisher chuyển kiểu. Đây là đặc tính được thêm tự động bởi factory.

**Câu 2.** Nếu `A = long[]` còn `R = String`, có được khai báo `IDENTITY_FINISH` không?

**Đáp án:** Không. Finisher phải chuyển mảng thành String; bỏ qua sẽ không trả đúng kiểu kết quả.

**Câu 3.** `UNORDERED` có bắt buộc Stream phải chạy parallel hoặc hoán đổi thứ tự không?

**Đáp án:** Không. Nó chỉ nói kết quả không cam kết giữ encounter order; một lần chạy có thể tình cờ vẫn giữ thứ tự.

**Câu 4.** Stream ordered, chạy parallel, collector có `CONCURRENT` nhưng không `UNORDERED`: có bảo đảm cùng một container được nhiều thread ghi đồng thời không?

**Đáp án:** Không. Khi cần bảo toàn encounter order, framework không nên dùng concurrent reduction trên nguồn ordered. Nó vẫn có thể chạy parallel bằng nhiều container và combiner.

**Câu 5.** Vì sao `ConcurrentHashMap.newKeySet()` phù hợp để tạo concurrent Set collector hơn `ArrayList`?

**Đáp án:** Vì thao tác thêm trên concurrent key set hỗ trợ ghi đồng thời vào cùng container; `ArrayList.add` không có bảo đảm tương ứng.

**Câu 6.** Nếu một collector có đủ ba characteristic, liệu Map/List sau khi trả về luôn an toàn để nhiều thread cùng sửa hay không?

**Đáp án:** Không. Các cờ mô tả reduction/finisher/order; không tự động chứng minh mọi giá trị bên trong hoặc mọi cách sử dụng kết quả đều thread-safe.

**Câu 7.** Trong custom collector, vì sao không được viết combiner trả về `left` và bỏ `right`?

**Đáp án:** Vì chạy parallel cần hợp nhất tất cả container con; bỏ `right` làm thất lạc dữ liệu và vi phạm associativity/identity của reduction.

## 11. Tổng kết

- **`IDENTITY_FINISH`**: container tích lũy chính là kết quả; finisher có thể bị bỏ qua; không dùng nếu `A` phải được biến đổi thành `R` khác.
- **`UNORDERED`**: collector không cam kết encounter order; không có nghĩa output chắc chắn bị đảo và không tự bật parallel.
- **`CONCURRENT`**: accumulator thật sự an toàn khi nhiều thread ghi trên cùng container; không thể chỉ nhìn tên collection hay gắn cờ cho nhanh.
- **Concurrent reduction** cần parallel stream, collector `CONCURRENT` và ít nhất một trong hai: stream unordered hoặc collector `UNORDERED`.
- **Collector bình thường vẫn chạy parallel hợp lệ** nhờ container độc lập và combiner đúng; `CONCURRENT` là tùy chọn thể hiện khả năng khác.
- **Identity và associativity của combiner** luôn phải đúng. Các characteristic là hợp đồng để framework tối ưu; khai báo sai làm kết quả thiếu an toàn.
- Ba đặc tính này có từ **Java 8** và còn áp dụng trong các JDK hiện hành.

### Tài liệu chính thức

- [Oracle Java SE 8 — Collector.Characteristics](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Collector.Characteristics.html)
- [Oracle Java SE 26 — Collector.Characteristics](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.Characteristics.html)
- [Oracle Java SE 26 — Collector (supplier, accumulator, combiner, finisher, constraints)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collector.html)
- [Oracle Java SE 26 — java.util.stream (Reduction, concurrency, and ordering)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html)
- [Oracle Java SE 26 — Collectors](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html)
