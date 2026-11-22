# Không can thiệp vào nguồn đang xử lý — Stream Non-interference (Java 8)

## 1. Vấn đề cần giải quyết

Trong Java Stream API, một **stream pipeline** lấy phần tử từ **nguồn dữ liệu** (như `List`, `Set`, mảng, generator hoặc nguồn I/O), cho các phần tử đi qua các phép xử lý như `filter`, `map`, rồi chạy **terminal operation** như `collect`, `count`, `sum` hoặc `forEach`.

Quy tắc cốt lõi của bài là **non-interference**: các hàm xử lý được truyền vào một stream thông thường **không được sửa hoặc gây ra việc sửa nguồn dữ liệu của stream trong thời gian pipeline đang được thực thi**. Quy tắc này áp dụng **cả stream tuần tự lẫn song song**, không chỉ `parallelStream()`.

Ví dụ **sai về thiết kế**:

```java
List<String> names = new ArrayList<>(Arrays.asList("An", "Binh"));
names.stream().forEach(name -> names.add(name)); // ĐỪNG LÀM.
```

Đây là đoạn code **cố ý sai**, dùng để phân tích chứ không phải một chương trình mẫu được khuyến nghị chạy. Khi duyệt một `ArrayList`, callback lại sửa cấu trúc của chính `ArrayList` nguồn; chương trình có thể ném `ConcurrentModificationException`, cho kết quả không đúng hoặc biểu hiện khác tùy triển khai và thời điểm. **Không được xem một exception cụ thể là kết quả được đảm bảo.**

Mục tiêu của bài học:

1. Xác định **nguồn stream** và ranh giới thực thi pipeline.
2. Hiểu chính xác non-interference và sự khác biệt với **statelessness**, **side effects** và **immutability**.
3. Biết tại sao sửa nguồn trong callback `map`, `filter`, `peek`, `forEach` là nguy hiểm.
4. Phân biệt **thay đổi nguồn trước**, **trong** và **sau** terminal operation; hiểu lazy traversal và late-binding.
5. Hiểu ngoại lệ của những stream source concurrent có `Spliterator.CONCURRENT`, nhưng không suy luận rằng mọi collection synchronized đều an toàn.
6. Chọn cách thay thế đúng: **pipeline thuần**, `collect`, `groupingBy`, `removeIf` ngoài stream, tạo **snapshot** hoặc quản lý đồng bộ/hợp đồng nguồn.
7. Biết đọc kết quả đúng khi dùng parallel stream, short-circuit, `forEach`, `peek`.
8. Kiểm thử và debug stream để tránh race conditions, mutation bất ngờ và giả định sai về `ConcurrentModificationException`.

**Phạm vi:** các quy tắc của Java 8 vẫn được duy trì trong Java hiện đại. Bài dùng kiến thức và API đang áp dụng, không dùng cơ chế lỗi thời hoặc đã legacy. Chương trình hoàn chỉnh bên dưới biên dịch được với `--release 8` trên JDK có hỗ trợ target này và chạy được với JDK 17+.

## 2. Phân biệt nguồn và pipeline

Ví dụ:

```java
List<String> source = new ArrayList<>(Arrays.asList("a", "bb", "ccc"));
Stream<Integer> lengths = source.stream()
        .filter(s -> s.length() >= 2)
        .map(String::length);
List<Integer> result = lengths.collect(Collectors.toList());
```

Đây là đoạn code minh họa trong một method, với các import phù hợp từ `java.util` và `java.util.stream`.

- **`source`** là collection **nắm giữ dữ liệu**.
- **`source.stream()`** tạo stream có nguồn là collection đó.
- **`filter`**, **`map`** là *intermediate operations*, xây pipeline **lazy**.
- **`collect`** là *terminal operation* và xây **collection kết quả**, trong ví dụ này gồm `[2,3]`.

Gọi `filter` hoặc `map` không tự sửa collection nguồn. Nhưng callback do bạn cung cấp vẫn là Java code bình thường và **có khả năng sửa dữ liệu nếu bạn viết như vậy**. Stream API không biến callback thành hàm thuần một cách tự động.

**Định nghĩa làm việc:** với nguồn thông thường không có đặc tính concurrent, một callback **interfering** nếu nó sửa hoặc gây ra việc sửa dữ liệu nguồn khi stream đang thực thi. Ví dụ `source.remove(...)` trong `filter` là interfering; gọi một method khác dẫn tới `source.add(...)` cũng là interfering.

## 3. Chính xác khoảng thời gian nào cần giữ nguồn ổn định?

Với stream pipeline thông thường, **thời gian thực thi** bắt đầu khi **terminal operation** được gọi và kết thúc khi terminal operation hoàn thành. Hai "escape-hatch" `iterator()` và `spliterator()` chuyển quyền điều khiển traversal cho caller, nên thời gian truy cập cần được xem xét theo cách duyệt đó.

```text
Collection / array / source
        │
        ├── stream()       Tạo stream
        ├── filter(...)    Định nghĩa stage, lazy
        └── map(...)       Định nghĩa stage, lazy
                 │
                 ▼
          terminal operation
             BẮT ĐẦU
        [nguồn không-concurrent
         không được sửa khi duyệt]
             KẾT THÚC
                 │
                 ▼
           Kết quả đã tạo
```

**Cần phân biệt ba mốc:**

| Thời điểm thay đổi nguồn | Đánh giá |
| --- | --- |
| **Trước terminal operation**, khi pipeline chưa duyệt | Với những nguồn *well-behaved* như các stream từ collection thông thường của JDK, sửa nguồn trước lúc terminal bắt đầu **có thể được phản ánh** trong dữ liệu mà stream duyệt. Không coi mọi stream là snapshot sớm. |
| **Trong lúc terminal operation đang chạy** | Với nguồn thông thường không-concurrent, **vi phạm non-interference** và có thể gây lỗi hoặc kết quả không đáng tin. |
| **Sau khi terminal operation hoàn thành** | Có thể sửa nguồn theo contract của collection; kết quả đã materialize không tự cập nhật, và muốn xử lý nguồn mới thì tạo **stream mới**. |

Ví dụ từ đặc tả Java cho một nguồn JDK collection có cơ chế *late binding*:

```java
List<String> items = new ArrayList<>(Arrays.asList("one", "two"));
Stream<String> stream = items.stream();
items.add("three"); // Trước terminal; với nguồn này có thể được quan sát.
String joined = stream.collect(Collectors.joining(" "));
System.out.println(joined); // one two three
```

Đây là code minh họa **trong method**, với import `List`, `ArrayList`, `Arrays`, `Stream`, `Collectors`. **Không suy ra rằng mọi stream tự động snapshot source tại `stream()`**. Trường hợp file stream, custom spliterator, cache hoặc concurrent source có thể có đặc điểm khác; hãy đọc contract của nguồn.

Quan trọng hơn: **không vì nguồn có late binding mà được sửa nguồn trong terminal operation**. Khoảng thời gian được phép thay đổi và thời điểm pipeline lấy dữ liệu là hai chuyện khác nhau.

## 4. Những dạng interference phổ biến

### 4.1. Thêm phần tử ngay khi đang duyệt

```java
List<Integer> list = new ArrayList<>(Arrays.asList(1, 2, 3));
list.stream().forEach(n -> list.add(n)); // Sai: sửa chính list nguồn.
```

`forEach` vẫn là terminal operation; nó không cấp quyền chỉnh sửa một source `ArrayList` trong lúc đang duyệt. Ngay cả khi chương trình chỉ có một thread, vẫn có thể vi phạm quy tắc.

### 4.2. Xóa phần tử trong `filter`

```java
List<String> source = new ArrayList<>(Arrays.asList("A", "B"));
source.stream()
        .filter(s -> {
            if (s.equals("A")) source.remove(s); // Sai.
            return true;
        })
        .count();
```

Đây cũng là ví dụ **sai cố ý**. Một vấn đề nữa là `count()` được phép tối ưu pipeline trong những tình huống phù hợp, nên **không có bảo đảm callback `filter` với side effect sẽ luôn được gọi nếu nó không cần thiết để tính kết quả**. Không dùng side effect của một intermediate operation để thực hiện mutation bắt buộc.

### 4.3. Sửa source gián tiếp qua một method khác

```java
source.stream().map(s -> {
    auditAndAddToSource(s); // Nếu method này sửa source: interfering.
    return s.toUpperCase();
}).collect(Collectors.toList());
```

Đoạn này là **pseudocode minh họa**, có method giả định `auditAndAddToSource`; không phải Java độc lập. Non-interference quan tâm đến **hậu quả đối với nguồn**, không chỉ tên API mà callback gọi trực tiếp.

### 4.4. Thread khác sửa nguồn trong lúc stream chạy

Ngay cả nếu callback thuần, một thread khác gọi `source.add(...)` trong lúc thread hiện tại đang duyệt `ArrayList` cũng gây interference. Dữ liệu race hoặc inconsistent traversal không biến mất chỉ vì mã stream dùng `map(String::trim)` sạch.

**Nguyên tắc:** với nguồn không-concurrent, các tác nhân có thể chỉnh sửa nguồn đều phải tuân thủ **ranh giới thời gian duyệt**, chứ không chỉ lambda nằm trong pipeline.

## 5. Điều gì có thể xảy ra nếu vi phạm?

Java Stream không hứa "cứ sửa nguồn trong pipeline thì chắc chắn ném `ConcurrentModificationException`". Với nguồn không-concurrent, những khả năng được tài liệu nêu gồm:

- Ném `ConcurrentModificationException` hoặc exception khác.
- Bỏ sót hoặc lặp dữ liệu dẫn tới kết quả sai.
- Quan sát dữ liệu không nhất quán do race hoặc thời điểm cập nhật.
- Không có exception nhưng hành vi vẫn vi phạm contract.
- Với source/pipeline đặc biệt, các tối ưu có thể làm callback có side effect **không được gọi**.

`ConcurrentModificationException` thường xuất hiện nhờ cơ chế *fail-fast* của các collection/iterator nhất định, nhưng đó là một **công cụ phát hiện lỗi theo best-effort**, không phải synchronization và cũng không phải bảo đảm an toàn. Đừng dựa vào:

```java
try {
    source.stream().forEach(...);
} catch (ConcurrentModificationException e) {
    // "Kiểm soát" concurrency bằng exception: thiết kế sai.
}
```

Đây là **mẫu phản ví dụ**, không phải cách xử lý hợp lệ. Nếu cần consistency, hãy dùng thiết kế dữ liệu/synchronization đúng, không dùng exception như bộ khóa.

## 6. Non-interference khác statelessness và side effect

Ba khái niệm thường bị gộp nhầm:

| Khái niệm | Yêu cầu/cảnh báo | Ví dụ |
| --- | --- | --- |
| **Non-interference** | Callback không sửa nguồn stream không-concurrent trong lúc xử lý | Không gọi `source.add` từ `filter` hoặc `forEach` |
| **Stateless behavioral parameter** | Kết quả callback không phụ thuộc vào **shared mutable state** thay đổi trong lúc pipeline chạy | `n -> n * n` thay vì dùng biến đếm shared |
| **Side effect** | Callback tác động ra bên ngoài phép tính, ví dụ log, I/O, sửa biến hoặc object | `System.out.println(n)`, `counter.incrementAndGet()` |

Một callback có side effect **không nhất thiết** là interfering nếu nó chỉ ghi log mà không sửa **source**. Nhưng side effects vẫn tiềm ẩn vấn đề về thread safety, ordering và việc callback có thật sự được gọi hay không.

Ví dụ **không sửa nguồn nhưng vẫn có shared mutable state**:

```java
List<Integer> seen = new ArrayList<>();
numbers.parallelStream()
        .filter(n -> {
            seen.add(n); // Không nhất thiết sửa numbers, nhưng race trên seen.
            return true;
        })
        .count();
```

Đây là **mẫu sai cố ý**. `seen` không phải source `numbers`, nên lỗi này còn thuộc về **statefulness/thread safety**, không chỉ định nghĩa interference. `ArrayList` không an toàn cho nhiều thread ghi đồng thời; thêm nữa, `count()` có thể tối ưu mà không gọi mọi callback.

**Giải pháp:** nếu cần tạo kết quả, dùng `collect`; nếu cần đếm, dùng `count`; nếu cần tổng hợp, dùng `reduce`, `sum` hoặc một collector phù hợp.

## 7. Cách viết đúng: để Stream tạo kết quả, không sửa nguồn

### 7.1. Chuyển đổi sang collection mới

```java
List<String> transformed = source.stream()
        .filter(s -> s.length() > 2)
        .map(String::toUpperCase)
        .collect(Collectors.toList());
```

Đây là snippet trong method, với `source` là `List<String>`. Pipeline không xóa hay thêm phần tử trong `source`. `collect` materialize **collection kết quả**. `Collectors.toList()` **không cam kết** loại List cụ thể hoặc khả năng sửa, dù một implementation có thể trả `ArrayList`.

Nếu cần một `ArrayList` mới cụ thể:

```java
List<String> copy = source.stream()
        .map(String::trim)
        .collect(Collectors.toCollection(ArrayList::new));
```

Đây là collector được thiết kế để tạo collection đích, không phải callback tự viết `source.add` trong lúc xử lý.

### 7.2. Tính toán tổng hợp bằng collector

```java
Map<String, Long> counts = people.stream()
        .collect(Collectors.groupingBy(Person::department, Collectors.counting()));
```

Đây là snippet trong method với class `Person` và method `department()` **giả định**. Nó cho thấy cách grouping tạo map kết quả thay vì `forEach` tùy tiện chỉnh sửa một `HashMap` shared, đặc biệt khi stream song song.

Nếu cần một cấu trúc map có thứ tự cụ thể, có thể cung cấp map factory như `TreeMap::new`, phù hợp chữ ký của `groupingBy`. Đừng dựa vào iteration order của `HashMap` nếu không có contract.

### 7.3. Muốn chỉnh sửa chính collection nguồn thì làm ngoài stream

Nếu yêu cầu nghiệp vụ là **xóa phần tử khỏi List nguồn**, hãy dùng API collection trực tiếp:

```java
List<String> names = new ArrayList<>(Arrays.asList("An", "", "Binh"));
names.removeIf(String::isEmpty); // Xóa ngoài stream traversal.
```

`Collection.removeIf` là API được hỗ trợ từ Java 8 và còn dùng hiện nay. Nó là **mutation operation của Collection**, khác với việc tự `remove` trong một callback của `names.stream()`. Đừng chạy `removeIf` đồng thời với một pipeline đang duyệt chính collection nguồn.

Tương tự, nếu muốn thay đổi từng phần tử List tại chỗ, xem `List.replaceAll` theo contract của List, hoặc dùng vòng lặp/iterator được thiết kế hỗ trợ mutation khi phù hợp; không dùng Stream pipeline như một API sửa cấu trúc nguồn.

## 8. Snapshot: tách dữ liệu đang đọc khỏi dữ liệu có thể thay đổi

Khi có các luồng xử lý/sửa nguồn độc lập nhau, một giải pháp đơn giản là tạo **snapshot** rồi xử lý snapshot đó:

```java
List<String> snapshot = new ArrayList<>(source);
List<String> output = snapshot.stream()
        .filter(s -> !s.isEmpty())
        .map(String::toUpperCase)
        .collect(Collectors.toList());
```

Đây là snippet trong method. Sau khi tạo `snapshot`, việc thêm/xóa phần tử ở `source` không đổi **cấu trúc** của `snapshot`.

**Giới hạn quan trọng:**

- `new ArrayList<>(source)` chỉ tạo **shallow copy**: các phần tử object có thể vẫn là **cùng tham chiếu**. Nếu một thread khác sửa state của một object phần tử, snapshot List không tự bảo đảm dữ liệu object bất biến.
- Tạo snapshot từ một collection đang bị sửa đồng thời **cũng cần thiết kế synchronization/consistency phù hợp**. Không mặc nhiên an toàn chỉ vì constructor nhận Collection.
- Nếu muốn snapshot thực sự ổn định, nên dùng **immutable element values** hoặc deep copy theo domain contract và chụp dữ liệu tại một điểm nhất quán.
- Một List view như `Collections.unmodifiableList(source)` chỉ chặn mutation **qua view**, không ngăn chủ sở hữu gốc sửa `source`; đây **không phải snapshot**.
- `List.copyOf` (Java 10+) tạo một List unmodifiable với semantics riêng; nó **không tự deep-copy** các object phần tử. Khi viết code đích Java 8, dùng các API Java 8 thích hợp.

**Chọn chiến lược:** nếu cần đọc ổn định trong lúc nguồn tiếp tục thay đổi, quyết định xem có thể dừng cập nhật để copy, có thể dùng immutable snapshot, có thể thiết kế event/queue, hoặc cần nguồn concurrent có contract rõ.

## 9. Chương trình hoàn chỉnh đã kiểm chứng

Tạo tệp **`StreamNonInterferenceDemo.java`**. Ví dụ dùng một `List<Order>` với **Order immutable về các field đã lưu**, tính toán bằng pipeline không sửa nguồn, lưu snapshot cấu trúc, rồi cập nhật nguồn **sau** khi terminal operations đầu tiên kết thúc. Cuối cùng nó xử lý lại nguồn bằng stream **mới** để thấy kết quả cập nhật.

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class StreamNonInterferenceDemo {
    static final class Order {
        final String customer;
        final int amount;
        Order(String customer, int amount) {
            this.customer = customer;
            this.amount = amount;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = new ArrayList<>(Arrays.asList(
                new Order("An", 20),
                new Order("Binh", 40),
                new Order("An", 30),
                new Order("Chi", 5)));

        List<Order> snapshot = new ArrayList<>(orders);

        List<String> customers = orders.stream()
                .filter(order -> order.amount >= 20)
                .map(order -> order.customer)
                .distinct()
                .sorted()
                .collect(Collectors.toList());

        Map<String, Integer> totals = orders.stream()
                .collect(Collectors.groupingBy(
                        order -> order.customer,
                        TreeMap::new,
                        Collectors.summingInt(order -> order.amount)));

        System.out.println("customers=" + customers);
        System.out.println("totals=" + totals);
        System.out.println("originalSize=" + orders.size());

        // Change the source ONLY after each terminal operation has finished.
        orders.add(new Order("Duy", 10));

        System.out.println("snapshotSize=" + snapshot.size());
        System.out.println("currentSize=" + orders.size());
        System.out.println("snapshotSum=" + snapshot.stream()
                .mapToInt(order -> order.amount).sum());
        System.out.println("currentSum=" + orders.stream()
                .mapToInt(order -> order.amount).sum());
        System.out.println("parallelSum=" + orders.parallelStream()
                .mapToInt(order -> order.amount).sum());
    }
}
```

**Biên dịch và chạy:**

```bash
javac --release 8 StreamNonInterferenceDemo.java
java StreamNonInterferenceDemo
```

`--release 8` khả dụng trong các JDK hiện đại hỗ trợ target Java 8. Nếu toolchain rất mới đưa ra *warning* về một target cũ, đó là compiler warning, không phải stdout của chương trình. Bạn cũng có thể biên dịch bằng `javac StreamNonInterferenceDemo.java` khi mục tiêu là chạy trên JDK đang sử dụng.

**Stdout của chương trình:**

```text
customers=[An, Binh]
totals={An=50, Binh=40, Chi=5}
originalSize=4
snapshotSize=4
currentSize=5
snapshotSum=95
currentSum=105
parallelSum=105
```

### Diễn giải từng dòng

- **`customers=[An, Binh]`**: `filter` giữ order có `amount >= 20`, `map` chọn customer, `distinct` bỏ trùng, `sorted` tạo thứ tự. Tất cả thao tác chỉ đọc các field của Order; không sửa `orders`.
- **`totals={An=50, Binh=40, Chi=5}`**: `groupingBy` và `summingInt` xây Map mới. `TreeMap::new` bảo đảm thứ tự key trong output, tránh phụ thuộc vào thứ tự không được bảo đảm của `HashMap`.
- **`originalSize=4`**: hai pipeline đầu không thêm/xóa phần tử khỏi danh sách nguồn.
- **`snapshotSize=4`**: snapshot cấu trúc được tạo khi nguồn có bốn Order, nên vẫn có bốn phần tử sau khi danh sách gốc được thêm Order mới.
- **`currentSize=5`**: `orders.add` chạy sau các terminal operations đầu; danh sách gốc có thêm Order `Duy`.
- **`snapshotSum=95`**: snapshot vẫn gồm các Order 20 + 40 + 30 + 5.
- **`currentSum=105`**: tạo stream **mới** từ nguồn đã cập nhật; tổng thêm 10.
- **`parallelSum=105`**: `mapToInt` chỉ đọc field immutable, `sum()` là terminal reduction thích hợp; không dùng biến tích lũy shared do callback tự sửa. Ở dữ liệu mẫu, kết quả vẫn 105.

Với dữ liệu nghiệp vụ có số lớn, `int` có thể overflow; chọn `long`/`mapToLong` hoặc kiểu số chính xác tùy contract. Điều này không làm thay đổi quy tắc non-interference.

**Giới hạn kiểm thử:** ví dụ đúng có output xác định. Những ví dụ **vi phạm non-interference** ở mục khác cố ý không được đặt vào `main`, vì không nên hứa một lỗi runtime cố định cho hành vi ngoài contract.

## 10. Nguồn concurrent: ngoại lệ có điều kiện, không phải miễn trừ mọi quy tắc

Tài liệu `java.util.stream` có một ngoại lệ đáng chú ý: stream có nguồn là **concurrent collection** được thiết kế để cho phép concurrent modification. Theo contract Stream, một nguồn concurrent được nhận diện khi **`Spliterator` của nguồn báo characteristic `Spliterator.CONCURRENT`**.

Điều đó có nghĩa:

- Nguồn có thể được **thiết kế** để chịu thay đổi trong lúc traversal theo **consistency semantics riêng**.
- Kết quả thường **không phải snapshot cố định** nếu collection ghi nhận concurrent updates theo cơ chế weak consistency.
- Không được tự suy ra tính deterministic về số phần tử, thứ tự hoặc việc một cập nhật đồng thời có xuất hiện trong kết quả hay không.
- Các lambda vẫn nên **stateless** và tránh shared mutable accumulators; concurrent source **không tự làm mọi callback thread-safe**.
- Nếu ứng dụng cần một ảnh chụp nhất quán hoặc đúng một tập phiên bản dữ liệu, cần cơ chế snapshot/coordination phù hợp thay vì chỉ chọn một collection concurrent.

### `ConcurrentHashMap` khác `HashMap`

Một stream từ các view của `ConcurrentHashMap` có thể có nguồn concurrent và traversal có weak consistency theo contract của collection đó. Ngược lại, stream từ `HashMap` không tự trở thành concurrent chỉ vì `parallelStream()` được gọi.

**Nhớ:** `parallelStream()` thay đổi cách chạy pipeline, **không thay đổi thread-safety của collection nguồn**.

### `Collections.synchronizedList` không đồng nghĩa với `Spliterator.CONCURRENT`

Một `List` được bọc bằng `Collections.synchronizedList` có locking cho các method theo contract của wrapper, nhưng **không vì thế mà mọi stream traversal qua List đó được phép diễn ra cùng lúc với mutation tùy ý**. Với nhu cầu traversal/iteration nhất quán, tài liệu collection thường yêu cầu **đồng bộ ngoài** cho toàn bộ quá trình duyệt bằng lock chung.

Đừng mặc nhiên cho rằng đặt `synchronized` quanh một callback là đủ; khi mutation xảy ra đồng thời từ nơi khác, phải thiết kế cùng cơ chế khóa cho cả reading/traversal và writing. Với parallel stream, phối hợp khóa phức tạp và có thể phá hiệu năng, nên cân nhắc snapshot hoặc cấu trúc dữ liệu có contract concurrent thích hợp.

### Không nên tự mutate source ngay cả với concurrent source nếu không cần

Dù một nguồn cho phép concurrent modification, callback thay đổi ngay chính nguồn đang duyệt có thể tạo logic khó suy luận, ví dụ phát sinh thêm các phần tử mới trong khi đang duyệt hoặc khiến điều kiện kết thúc không rõ. Ngoại lệ theo contract của collection **không biến thiết kế đó thành lựa chọn tốt mặc định**.

## 11. `forEach`, `peek` và side effects: khi nào được phép?

### `forEach` là terminal operation dùng side effect

Ví dụ:

```java
notifications.stream()
        .filter(Notification::isReady)
        .forEach(notification -> sender.send(notification));
```

Đây là **snippet minh họa**, giả sử `Notification` và `sender` được ứng dụng định nghĩa. `sender.send` có side effect bên ngoài (gửi thông báo). Nó **không nhất thiết sửa nguồn `notifications`**, nên không mặc nhiên vi phạm non-interference. Nhưng bạn vẫn phải xử lý:

- duplicate delivery, retry và exception theo contract của ứng dụng;
- thread safety của `sender` khi dùng parallel stream;
- thứ tự: `forEach` song song **không bảo đảm encounter order**;
- việc `sender.send` có gián tiếp sửa collection `notifications` hay không.

Nếu side effect cần exactly-once theo giao dịch, Stream API một mình không cung cấp bảo đảm như vậy; hệ thống cần cơ chế nghiệp vụ thích hợp.

### `peek` chủ yếu để quan sát/debug, không phải nơi thực thi logic bắt buộc

```java
long count = items.stream()
        .peek(System.out::println)
        .count();
```

Đoạn này minh họa trong method. **Không được bảo đảm** `println` chạy cho mọi phần tử: Stream implementation có thể tối ưu `count()` dựa trên kích thước nguồn, loại bỏ stages không cần thiết để tính kết quả. Tài liệu Stream nêu rõ **side effect của behavioral parameters không phải lúc nào cũng được thực thi**, ngoại trừ những bảo đảm riêng mà operation contract cung cấp (ví dụ terminal `forEach`, `forEachOrdered`).

Đừng dùng `peek` để persist, audit bắt buộc hoặc cập nhật biến quyết định nghiệp vụ.

### `forEachOrdered` giải quyết chuyện gì?

`forEachOrdered` thực hiện action theo **encounter order nếu stream có encounter order**, kể cả khi pipeline chạy parallel. Nó có thể tốn chi phí điều phối và vẫn không hợp thức hóa mutation của **source** trong lúc traversal. Nếu yêu cầu là tính một danh sách có thứ tự, `collect` thường dễ kiểm chứng hơn side effects tùy tiện.

## 12. Parallel stream càng cần rõ ranh giới dữ liệu

Với pipeline song song, các callback có thể được thực hiện ở **nhiều thread** và không có guarantee rằng phần tử trải qua các stages trên cùng một thread. Các lỗi về shared mutable state dễ xuất hiện hơn.

Ví dụ nên tránh:

```java
List<Integer> output = new ArrayList<>();
numbers.parallelStream()
        .map(n -> n * 2)
        .forEach(output::add); // Race trên shared ArrayList.
```

Đây là **mẫu sai cố ý**. Mặc dù `output` không nhất thiết là **nguồn** stream (nguồn là `numbers`), cập nhật một `ArrayList` shared từ nhiều thread không an toàn và thứ tự không bảo đảm. Đây là ví dụ **statefulness và race**, cần phân biệt với **source interference**.

Đổi thành:

```java
List<Integer> output = numbers.parallelStream()
        .map(n -> n * 2)
        .collect(Collectors.toList());
```

Đây là snippet thay thế, không ghép cả hai khai báo `output` vào cùng scope. Collector được Stream API quản lý theo contract cho quá trình tích lũy. Khi cần đúng implementation hoặc mutability, dùng collector rõ ràng.

Nếu chỉ cần tổng:

```java
long total = numbers.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();
```

Không cần `AtomicLong` chung để mỗi callback `addAndGet`. Atomic có thể tránh một data race nhất định nhưng còn gây contention và vẫn không giải quyết tự động source interference, ordering hoặc semantic correctness.

**Parallel không mặc nhiên nhanh hơn sequential.** Với dữ liệu nhỏ, overhead splitting/merging cao hơn lợi ích; cần benchmark trên workload thực.

## 13. Object mutable trong nguồn: thêm/xóa khác với thay đổi trạng thái phần tử

Đây là phần nâng cao cần phân biệt cẩn thận.

Giả sử `List<User>` chứa object `User` có field thay đổi được. Hai kiểu mutation có ý nghĩa khác nhau:

1. **Structural mutation của source:** `users.add(...)`, `users.remove(...)`, `users.clear()` trong lúc stream duyệt `users`. Với source `ArrayList` không-concurrent, đây rõ ràng là **interference**.
2. **Mutation của object phần tử:** `user.setName(...)` trong callback. Đây không nhất thiết sửa **cấu trúc collection nguồn**, nhưng vẫn là một **side effect**, có thể phá tính thuần, gây bất ngờ cho nguồn và các bên đang dùng cùng object, tạo race khi song song, và làm kết quả không ổn định nếu các stage khác đọc state đó.

Ví dụ nên tránh nếu ý định là tạo dữ liệu mới:

```java
List<User> normalized = users.stream()
        .peek(user -> user.setName(user.getName().trim()))
        .collect(Collectors.toList());
```

Đây là **pseudocode minh họa** với `User` do ứng dụng định nghĩa. Nó có thể thay đổi state của chính các object trong `users` do result thường chứa **các tham chiếu cũ**, không deep copy. Một thành phần khác đọc `users` có thể quan sát mutation.

Cách rõ hơn là **tạo value object mới** (nếu hợp đồng `User` cho phép):

```java
List<User> normalized = users.stream()
        .map(user -> new User(user.getName().trim()))
        .collect(Collectors.toList());
```

Đây cũng là code minh họa với giả định constructor `User(String)` tồn tại. Mỗi phần tử result là object mới; source vẫn giữ reference cũ. Nhưng muốn một snapshot sâu, phải xem **toàn bộ object graph**, không chỉ một field String.

Khi nghiệp vụ thật sự yêu cầu mutation in-place, viết vòng lặp có policy rõ, bảo đảm không có traversal cạnh tranh, hoặc dùng operation chuyên dụng phù hợp (như `List.replaceAll` ở ngoài stream) thay vì để `peek` giấu side effect.

## 14. Tối ưu hóa `count`, short-circuit và vấn đề test side effects

Ngay cả khi bạn không sửa source, dùng side effect để "chứng minh" số lần callback chạy là một kiểu kiểm thử yếu.

Ví dụ:

```java
AtomicInteger seen = new AtomicInteger();
long count = source.stream()
        .peek(x -> seen.incrementAndGet())
        .count();
```

Đoạn này minh họa trong method, với `AtomicInteger` và `source` phù hợp. **Không kết luận rằng `seen.get() == count` được Java bảo đảm.** Một pipeline có source với kích thước được biết và không có intermediate operation ảnh hưởng số lượng phần tử có thể được tối ưu để trả `count` mà không gọi `peek`.

`findFirst`, `anyMatch`, `noneMatch`, `limit` cũng có thể dừng sớm hoặc thay đổi số phần tử được đưa qua một stage. Đó là hành vi đúng của stream khi tìm kết quả terminal, không phải lỗi "bỏ sót" mà bạn nên vá bằng mutation.

**Test nên xác nhận kết quả**, không dùng side effect không được bảo đảm như chỉ báo rằng từng phần tử đã chạy qua callback. Khi cần side effect bắt buộc trên mỗi phần tử, xem contract của terminal `forEach` hoặc `forEachOrdered` và thiết kế error handling/idempotency/ordering phù hợp.

## 15. Kiểm thử và debug non-interference có hệ thống

Một bộ test nên phân biệt các loại lỗi sau:

| Bài kiểm tra | Cần xác nhận |
| --- | --- |
| Pipeline thuần | Kết quả `filter/map/collect` đúng; source không bị mutation không chủ đích. |
| Re-run sau terminal | Tạo stream **mới** từ source; kết quả phản ánh trạng thái nguồn mới. |
| Snapshot | Snapshot có cấu trúc độc lập; phần tử mutable được kiểm soát đúng. |
| Concurrent modification | Test dưới load/đa thread để tìm race, nhưng **không kết luận không có exception = đúng contract**. |
| Parallel reduction | Kết quả nhất quán với sequential khi operation có semantics associative/appropriate; không dùng shared accumulator. |
| Ordered/unordered | Không dựa vào thứ tự của `forEach` song song nếu contract không hứa. |
| Side-effect optimization | Không kỳ vọng `peek` được gọi đầy đủ trong `count` hoặc short-circuiting pipeline. |
| Resource-backed streams | Với `Files.lines` hoặc I/O, bảo đảm close/try-with-resources, không liên quan trực tiếp đến interference nhưng cần cho correctness. |
| Concurrent source contract | Xem `Spliterator.CONCURRENT`, đặc điểm traversal/visibility; xác định có cần snapshot không. |

### Một checklist review code

Trước khi approve stream pipeline, tự hỏi:

1. **Nguồn là gì?** `List`, `Map`, mảng, file hay nguồn concurrent?
2. **Ai có thể sửa nguồn** khi terminal operation đang chạy? Có code trong callback, listener, thread khác hoặc scheduled task không?
3. **Lambda có sửa captured state hoặc object phần tử không?** Nếu có, đó là side effect được phép/được kiểm soát hay một nguồn race?
4. **Output cần là gì?** List mới, Map grouped, count hay chỉ ghi I/O? Có nên dùng collector thay shared mutable accumulator?
5. **Có yêu cầu snapshot/consistency không?** Nếu có, biên giới copy/synchronization nằm ở đâu?
6. **Source Spliterator có đặc tính `CONCURRENT` không?** Nếu có, behavior weakly consistent có phù hợp nghiệp vụ không?
7. **Test đang kiểm kết quả hay số lần side effect chạy?** Tránh dựa vào callback có thể bị tối ưu lược bỏ.
8. **Có cần parallel không?** Nếu có, callback và dữ liệu đã thread-safe và stateless chưa?

Kiểm tra này đặc biệt hữu ích khi refactor một vòng lặp for sang stream: một vòng lặp trước đó có thể cố ý sửa collection qua iterator hoặc duy trì state giữa các bước; không thể sao chép logic mutation vào `stream().forEach(...)` rồi mong giữ nguyên contract.

## 16. Bảng sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Sửa `ArrayList` trong `stream().forEach` | Vi phạm non-interference trên nguồn không-concurrent | Tạo result bằng `collect`, hoặc mutate list **ngoài traversal** |
| Xóa phần tử trong `filter` | Callback làm thay đổi nguồn đang duyệt | Dùng `filter` để tạo danh sách mới hoặc `removeIf` trực tiếp ngoài stream |
| Nghĩ sequential stream thì mutate an toàn | Non-interference áp dụng cả sequential | Không sửa nguồn trong lúc terminal chạy |
| Nghĩ parallel stream làm collection thread-safe | Parallelism không đổi contract của nguồn | Source concurrent thích hợp, snapshot hoặc phối hợp synchronization |
| Chờ `ConcurrentModificationException` làm bảo vệ | Fail-fast không phải cơ chế consistency/thread safety | Thiết kế mutation boundary và test đúng |
| Tạo stream trước rồi coi đó là snapshot | Các nguồn JDK phổ biến có thể late-bind | Snapshot có chủ đích khi cần |
| Dùng `Collections.unmodifiableList` như snapshot | View không chặn chủ nguồn sửa List | Tạo independent copy theo domain |
| Dùng `new ArrayList<>(source)` rồi giả định deep copy | Phần tử object mutable có thể dùng chung | Immutable values/deep copy thích hợp |
| Dùng `peek` để ghi audit bắt buộc | Side effects có thể bị lược bỏ bởi optimization | Dùng terminal action/transaction hoặc API nghiệp vụ riêng |
| Dùng shared `ArrayList` trong parallel `forEach` | Data race, thiếu ordering | Dùng collector hoặc result structure phù hợp |
| Nghĩ `AtomicInteger` làm mọi pipeline đúng | Atomic chỉ xử lý một kiểu race; không ngăn source interference hay stateful semantics | Stateless operations/reductions |
| Nghĩ concurrent source = stable snapshot | Concurrent traversal có consistency semantics riêng | Xác định cần snapshot/versioning hay weak consistency là đủ |
| Gộp mutation nguồn và result vào `map` | Side effect bị giấu, có thể đổi input cho stage khác | Tách bước biến đổi dữ liệu và bước ghi state |
| Không quản lý stream backed by I/O | Tài nguyên có thể không đóng khi terminal kết thúc | Try-with-resources với nguồn cần close |

## 17. Bài tập tự kiểm tra có đáp án

**1.** `list.stream().map(x -> x * 2).collect(toList())` có tự sửa `list` không?  
**Không.** Pipeline chỉ đọc source và tạo result. Điều này giả định callback thuần như trong ví dụ.

**2.** `list.stream().forEach(x -> list.add(x))` có đúng nếu chỉ dùng một thread?  
**Không.** Non-interference áp dụng với source không-concurrent cả trong sequential stream.

**3.** `ConcurrentModificationException` có luôn ném ra khi sửa List trong stream không?  
**Không.** Không có bảo đảm phát hiện đầy đủ hoặc một dạng lỗi duy nhất.

**4.** Vì sao `peek(log).count()` có thể không gọi log?  
**Vì Java Stream được phép tối ưu phép đếm** khi có đủ thông tin từ nguồn và không cần thực thi các stage không ảnh hưởng result.

**5.** Có thể sửa List sau khi terminal `collect` hoàn tất không?  
**Có**, theo contract List; nhưng thay đổi đó không tự cập nhật result trước đó. Muốn xử lý lại nguồn cần tạo stream mới.

**6.** Có thể sửa source trước terminal operation nếu stream đã được tạo không?  
**Với nguồn well-behaved có late binding, có thể**, và thay đổi được phản ánh khi duyệt. Không suy ra điều này cho mọi custom source.

**7.** `new ArrayList<>(source)` có deep-copy các object phần tử không?  
**Không.** Nó copy collection structure, vẫn có thể chia sẻ object references.

**8.** `Collections.unmodifiableList(source)` có bảo đảm snapshot bất biến không?  
**Không.** View có thể phản ánh mutation của List gốc do chủ sở hữu thực hiện.

**9.** Một `ConcurrentHashMap` có nguồn concurrent nghĩa là kết quả stream chắc chắn thấy mọi cập nhật mới nhất?  
**Không.** Phải đọc consistency contract, có thể có weak consistency và không phải snapshot nguyên tử.

**10.** `parallelStream().forEach(sharedArrayList::add)` có nên dùng để gom kết quả?  
**Không.** Đây là shared mutable accumulator không thread-safe; nên dùng `collect`.

**11.** `forEach(System.out::println)` có vi phạm non-interference không?  
**Không mặc nhiên**, vì in log không sửa source. Nhưng thứ tự và exception/I/O side effects phải được hiểu rõ, nhất là parallel.

**12.** Nếu `map` gọi `user.setName` trên object được chứa trong source, code có chắc làm source immutable không?  
**Không.** Nó sửa state của element object; có thể ảnh hưởng những nơi khác giữ cùng reference, tạo side effects/race.

**13.** Muốn xóa những phần tử trống khỏi List tại chỗ, chọn gì?  
Dùng `list.removeIf(String::isEmpty)` **ngoài stream traversal**, không tự `remove` trong `filter`/`forEach`.

**14.** Muốn tính sum của một List song song mà không dùng biến tích lũy chung, chọn gì?  
`list.parallelStream().mapToLong(...).sum()` hoặc reduction phù hợp với tính chất phép toán.

**15.** Nguồn `Collections.synchronizedList` có tự cho phép mutation đồng thời không giới hạn trong lúc stream duyệt không?  
**Không.** Synchronized wrapper không tự đồng nghĩa với concurrent Spliterator; có thể vẫn cần external synchronization hoặc snapshot.

## 18. Kết luận và nguồn tham khảo

**Non-interference** là điều kiện nền của Stream pipeline: **không sửa hoặc gây ra việc sửa nguồn stream không-concurrent khi pipeline đang thực thi**. Quy tắc này giữ cho Stream API có thể tổ chức traversal, fusion, parallelism và tối ưu theo contract mà không phải đoán cách source bị thay đổi giữa chừng.

Để viết mã an toàn, hãy **giữ callback không can thiệp vào nguồn**, ưu tiên stateless transformations, dùng **`collect`/`reduce`/`sum`** thay shared mutable accumulation, sửa collection bằng API collection ở thời điểm riêng hoặc xử lý một **snapshot** có consistency phù hợp. Phân biệt source interference với side effect trên state khác, và chỉ sử dụng ngoại lệ concurrent source khi biết rõ `Spliterator.CONCURRENT` cùng chính sách consistency của nguồn.

Các nguyên tắc này áp dụng cho Java 8 và vẫn đúng trong Java hiện đại.

**Tài liệu chính thức:**

- [Oracle Java SE — `java.util.stream` package summary](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/package-summary.html): mục *Non-interference*, *Stateless behaviors* và *Side-effects*.
- [Oracle Java SE — `Stream` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): non-interfering parameters, pipeline optimization, `peek`, `count`, `forEach`.
- [Oracle Java SE — `Spliterator` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Spliterator.html): đặc tính `CONCURRENT`, `IMMUTABLE`, `ORDERED` và `SIZED`.
- [Oracle Java SE — `Collection.removeIf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html#removeIf(java.util.function.Predicate)): cách chỉnh sửa Collection ngoài stream traversal.
- [Oracle Java SE — `Collectors` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html): các phép materialize/reduction thay manual shared accumulation.
