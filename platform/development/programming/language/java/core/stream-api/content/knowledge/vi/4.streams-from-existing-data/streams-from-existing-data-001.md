# Tạo Stream từ Collection bằng stream() và parallelStream()

Khi dữ liệu đã nằm trong một `Collection`, Java Stream API cung cấp hai cách trực tiếp để xây dựng pipeline: `collection.stream()` và `collection.parallelStream()`. Cả hai giúp xử lý dữ liệu theo phong cách khai báo với `filter`, `map`, `reduce`, `collect` và nhiều phép toán khác. Khác biệt chính là **chế độ thực thi tuần tự hay có khả năng song song** khi pipeline được tiêu thụ.

Bài học thuộc chương **Tạo Stream từ dữ liệu có sẵn** của module **JAVA_STREAM_API**. Việc hiểu cách tạo Stream từ Collection là nền tảng trước khi tiếp cận grouping, collector tùy chỉnh, `Spliterator`, xử lý song song và các phép toán nâng cao như Stream Gatherers. Đặc biệt, cần phân biệt **nguồn dữ liệu**, **thời điểm chạy**, **thứ tự kết quả**, **an toàn khi xử lý song song** và **chi phí hiệu năng**.

## 1. Hai phương thức có sẵn trên Collection

Từ Java 8, giao diện `java.util.Collection<E>` cung cấp các phương thức:

```java
Stream<E> stream();
Stream<E> parallelStream();
```

Theo hợp đồng API, `stream()` trả về **Stream tuần tự**, còn `parallelStream()` trả về **Stream có thể xử lý song song**. Cách thức và mức độ song song thực tế phụ thuộc vào nguồn, phép toán, môi trường thực thi và khả năng chia tách dữ liệu.

Các lớp triển khai `Collection` như `ArrayList`, `LinkedList`, `HashSet`, `LinkedHashSet`, `TreeSet` thường dùng được cả hai phương thức thông qua giao diện `Collection`:

```java
List<String> names = Arrays.asList("An", "Binh", "Chi");
Stream<String> sequential = names.stream();
Stream<String> parallel = names.parallelStream();
```

Trong đó, `Stream<String>` là **luồng mô tả việc xử lý các phần tử**, không phải danh sách mới. Hai lời gọi tạo ra **hai Stream riêng biệt** từ cùng Collection; chúng không chuyển đổi hay xóa dữ liệu của `names`.

| Nguồn đã có | Cách tạo Stream | Ghi chú |
| --- | --- | --- |
| `List<String>`, `ArrayList<String>` | `list.stream()` hoặc `list.parallelStream()` | List thông thường có thứ tự phần tử xác định. |
| `Set<String>`, `HashSet<String>` | `set.stream()` hoặc `set.parallelStream()` | HashSet không bảo đảm thứ tự duyệt. |
| `LinkedHashSet<String>` | `set.stream()` | Giữ thứ tự chèn khi duyệt phần tử. |
| `TreeSet<String>` | `set.stream()` | Duyệt theo thứ tự sắp xếp của Set. |
| `Map<K, V>` | `map.entrySet().stream()`, `map.keySet().stream()`, `map.values().stream()` | `Map` **không phải** `Collection`; tạo Stream từ collection view phù hợp. |
| Mảng `String[]` | `Arrays.stream(array)` | Mảng không phải Collection nên không gọi trực tiếp `array.stream()`. |

Mỗi Stream có **kiểu phần tử** của nguồn tương ứng. Từ `Map.entrySet()`, phần tử là `Map.Entry<K, V>`; từ `Map.values()`, phần tử là `V`. Kiểu này quyết định những phép biến đổi có thể viết ở bước tiếp theo.

## 2. Ví dụ chạy được: từ List đến kết quả

Ví dụ hoàn chỉnh sau tương thích Java 8 trở lên:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

public class CollectionStreamDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList(
            "An", "Binh", " Chi ", "Dung", "Minh", "  "
        );

        List<String> normalized = names.stream()
            .map(String::trim)
            .filter(name -> name.length() >= 3)
            .map(name -> name.toUpperCase(Locale.ROOT))
            .collect(Collectors.toList());

        System.out.println(normalized);
        // [BINH, CHI, DUNG, MINH]

        long count = names.parallelStream()
            .map(String::trim)
            .filter(name -> name.length() >= 3)
            .count();

        System.out.println(count);
        // 4
    }
}
```

Pipeline được đọc từ trái sang phải:

1. `names.stream()` lấy `List<String>` làm nguồn và tạo Stream tuần tự.
2. `map(String::trim)` mô tả việc bỏ khoảng trắng ở đầu và cuối mỗi tên.
3. `filter(...)` giữ các tên có ít nhất ba ký tự sau khi chuẩn hóa.
4. `map(...toUpperCase...)` mô tả phép đổi thành chữ hoa.
5. `collect(Collectors.toList())` tiêu thụ các phần tử còn lại và tạo kết quả dưới dạng `List`.

Pipeline thứ hai tạo nguồn bằng `parallelStream()`; giá trị `count` vẫn là `4` vì cả hai pipeline cùng áp dụng quy tắc lọc. Với dữ liệu nhỏ như ví dụ, xử lý song song thường không có lợi thế và có thể tốn thêm chi phí điều phối.

> Hai lời gọi `stream()` và `parallelStream()` không yêu cầu copy Collection. `collect(...)` mới là bước tạo cấu trúc dữ liệu kết quả. Bản chất “view của quá trình tính toán” này giúp hạn chế các danh sách tạm sau mỗi bước trung gian.

## 3. Stream mang tính lười: tạo pipeline chưa duyệt dữ liệu

`filter` và `map` là các phép toán trung gian (*intermediate operations*). Chúng thường chỉ nối thêm quy tắc vào pipeline; phép toán kết thúc (*terminal operation*) như `count`, `collect` hoặc `findFirst` mới yêu cầu dữ liệu được xử lý.

```java
List<Integer> numbers = Arrays.asList(1, 2, 3, 4);

Stream<Integer> pipeline = numbers.stream()
    .filter(n -> {
        System.out.println("Đang lọc: " + n);
        return n % 2 == 0;
    });

System.out.println("Đã tạo pipeline");
long result = pipeline.count();
System.out.println("Số phần tử chẵn: " + result);
```

Trong pipeline tuần tự này, `Đã tạo pipeline` xuất hiện trước khi các lần lọc diễn ra. `count()` cần xác định số phần tử sau `filter` nên pipeline đánh giá bộ lọc cho các số trong danh sách.

**Một Stream chỉ có một lượt tiêu thụ.** Sau `pipeline.count()`, không được gọi tiếp `pipeline.collect(...)` trên chính đối tượng `pipeline`. Muốn xử lý lại Collection thì tạo Stream mới:

```java
long evenCount = numbers.stream().filter(n -> n % 2 == 0).count();
int evenSum = numbers.stream()
    .filter(n -> n % 2 == 0)
    .mapToInt(Integer::intValue)
    .sum();
// evenCount = 2; evenSum = 6
```

Đừng coi tác dụng phụ trong `peek`, `map` hoặc các bước trung gian là thao tác được bảo đảm sẽ chạy đúng một lần cho mỗi phần tử. Một số terminal có thể dừng sớm hoặc bỏ qua các phép toán không cần thiết khi tối ưu hóa, ví dụ `count()` trên nguồn có kích thước biết trước.

## 4. Điều gì khác nhau giữa stream() và parallelStream()?

| Khía cạnh | `collection.stream()` | `collection.parallelStream()` |
| --- | --- | --- |
| Chế độ khởi tạo | Tuần tự | Có thể song song |
| Cách thực thi điển hình | Phần tử được xử lý trên đường đi tuần tự | Công việc có thể được chia thành nhiều phần và thực thi đồng thời |
| Thứ tự **thực thi lambda** | Dễ quan sát hơn với nguồn có thứ tự và bước không trạng thái | Không bảo đảm theo thứ tự nguồn |
| Thứ tự **kết quả** | Tuân theo hợp đồng nguồn và terminal | Vẫn có thể bảo toàn encounter order qua terminal thích hợp |
| Chi phí | Ít điều phối, thường hợp với tập nhỏ | Có chi phí chia việc, ghép kết quả và đồng bộ nếu cần |
| Rủi ro khi lambda thay đổi trạng thái chia sẻ | Có thể gây lỗi logic | Có thêm rủi ro race condition, kết quả thiếu hoặc không ổn định |

Java sử dụng thông tin của nguồn thông qua `Spliterator` để duyệt và, khi phù hợp, chia phần tử thành các phần có thể xử lý độc lập. `parallelStream()` **không có nghĩa** mọi phần tử sẽ được xử lý trên một luồng riêng, cũng không hứa số lượng luồng cố định.

Có thể kiểm tra và chuyển chế độ của một pipeline **chưa bị tiêu thụ**:

```java
Stream<Integer> a = numbers.stream();
System.out.println(a.isParallel()); // false

Stream<Integer> b = numbers.parallelStream();
System.out.println(b.isParallel()); // true với các Collection thông dụng

long total = numbers.stream()
    .parallel()
    .mapToLong(Integer::longValue)
    .sum();

long sequentialTotal = numbers.parallelStream()
    .sequential()
    .mapToLong(Integer::longValue)
    .sum();
```

`parallel()` và `sequential()` là các phép cấu hình chế độ cho pipeline, **không tự khởi chạy xử lý**. Ở các Collection thông dụng như `ArrayList`, `parallelStream()` trả về Stream đánh dấu song song; API `Collection` chỉ cam kết một Stream *có thể* song song, nên tránh coi đây là bảo đảm về mức độ sử dụng CPU.

## 5. Thứ tự dữ liệu và thứ tự thực thi là hai khái niệm

**Encounter order** là thứ tự phần tử do nguồn cung cấp cho Stream, nếu nguồn có thứ tự. Ví dụ, `List` thường cung cấp thứ tự theo chỉ số, `LinkedHashSet` theo thứ tự chèn, `TreeSet` theo quy tắc sắp xếp; `HashSet` không cam kết thứ tự.

Từ một `List` có thứ tự, một phép biến đổi song song vẫn có thể cho **kết quả có thứ tự**:

```java
List<Integer> source = Arrays.asList(1, 2, 3, 4, 5, 6);

List<Integer> squared = source.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());

System.out.println(squared); // [1, 4, 9, 16, 25, 36]
```

Điều đó **không chứng minh** lambda `n -> n * n` đã chạy theo thứ tự `1, 2, 3, 4, 5, 6`. Bộ thu thập thích hợp ghép kết quả theo encounter order của nguồn.

So sánh hai terminal sau:

```java
source.parallelStream().forEach(System.out::println);
// Thứ tự in có thể khác nhau giữa các lần chạy.

source.parallelStream().forEachOrdered(System.out::println);
// Với List có thứ tự: in 1, 2, 3, 4, 5, 6.
```

`forEachOrdered` giữ thứ tự quan sát được nhưng có thể khiến việc xử lý tốn thêm chi phí. `findFirst()` ưu tiên phần tử đầu theo encounter order; `findAny()` có thể chọn phần tử bất kỳ, nhất là khi chạy song song. Không áp đặt khái niệm “đầu tiên” theo thứ tự chèn lên `HashSet`.

Với các nguồn không có encounter order, terminal không thể tạo ra một cam kết thứ tự nguồn vốn không tồn tại. Nếu yêu cầu kết quả được sắp xếp theo tiêu chí riêng, hãy dùng `sorted(...)` và nhận thức chi phí sắp xếp.

## 6. Không dùng trạng thái chia sẻ để tích lũy kết quả song song

Một lỗi điển hình là sử dụng `forEach` để thêm phần tử trực tiếp vào `ArrayList` bên ngoài:

```java
List<Integer> source = Arrays.asList(1, 2, 3, 4, 5, 6);

List<Integer> unsafe = new ArrayList<>();
source.parallelStream().forEach(n -> unsafe.add(n * n)); // Sai!
```

`ArrayList` không an toàn cho nhiều luồng thêm phần tử đồng thời. Kết quả có thể thiếu, sai hoặc phát sinh lỗi; đôi khi chạy đúng chỉ là tình cờ. Thay bằng phép thu thập có hợp đồng rõ ràng:

```java
List<Integer> safe = source.parallelStream()
    .map(n -> n * n)
    .collect(Collectors.toList());
```

Collector được thư viện phối hợp với cơ chế chia việc và kết hợp kết quả khi chạy song song. **Không cần** biến đích dùng chung trong lambda. Cách này cũng hoạt động với Stream tuần tự.

Tương tự, để tính tổng số lượng, sử dụng phép giảm phù hợp:

```java
long sum = source.parallelStream()
    .mapToLong(Integer::longValue)
    .sum(); // 21
```

Nếu tự dùng `reduce(identity, accumulator, combiner)` trên Stream song song, các phép kết hợp phải thỏa tính **kết hợp (associativity)**, identity trung lập và các yêu cầu tương thích của hợp đồng `reduce`. Với thao tác phụ thuộc thứ tự như phép trừ, không thể tùy tiện gom các tổng phụ rồi trừ để mong nhận cùng kết quả như một vòng lặp tuần tự.

Ví dụ grouping, một tác vụ thường gặp trong module:

```java
Map<Integer, Long> countByLength = Arrays.asList("An", "Binh", "Chi", "Dung")
    .parallelStream()
    .collect(Collectors.groupingBy(String::length, Collectors.counting()));

// Có 1 tên dài 2, 1 tên dài 3 và 2 tên dài 4.
// Không nên dựa vào thứ tự duyệt các key trong Map kết quả.
```

`groupingBy` vẫn có thể dùng trong pipeline song song nhờ cơ chế tích lũy và kết hợp của Collector; việc không sử dụng `ConcurrentHashMap` ở ví dụ này không đồng nghĩa là phép thu thập bị race condition. Với nhu cầu nhóm đồng thời và không yêu cầu thứ tự, `groupingByConcurrent` có hợp đồng riêng cần xem xét.

## 7. Collection, Spliterator và chi phí chia việc

`Collection.stream()` và `Collection.parallelStream()` sử dụng `Spliterator` của Collection để hỗ trợ duyệt dữ liệu. `Spliterator` có khả năng báo đặc tính nguồn, chẳng hạn:

- `ORDERED`: nguồn có encounter order.
- `SIZED`: biết kích thước phần dữ liệu đang được biểu diễn.
- `DISTINCT`: các phần tử không trùng nhau theo hợp đồng nguồn.
- `SORTED`: các phần tử tuân theo thứ tự sắp xếp xác định.

Các đặc tính được cung cấp khác nhau tùy Collection và cách xây dựng nguồn. Chúng giúp Stream lựa chọn hoặc tối ưu phép xử lý; chẳng hạn, `count()` có thể lấy kích thước trực tiếp khi biết chắc không có bước nào thay đổi số phần tử.

Hiệu quả của `parallelStream()` phụ thuộc đáng kể vào khả năng chia dữ liệu: `ArrayList` thường dễ phân đoạn theo chỉ số, trong khi cấu trúc liên kết như `LinkedList` có đặc điểm tách và truy cập khác. Đây là lý do cùng một pipeline có thể có hiệu năng rất khác trên những Collection khác nhau.

Tuy nhiên, **phần tử lớn chưa chắc đồng nghĩa xử lý song song nhanh hơn**. Nên cân nhắc:

| Yếu tố | Khi nào xử lý song song đáng xem xét? |
| --- | --- |
| Số lượng phần tử | Đủ lớn để bù chi phí chia và ghép việc. |
| Công việc trên mỗi phần tử | Tốn CPU, các phép tính độc lập, ít đồng bộ. |
| Nguồn | Dễ chia thành các phần tương đối cân bằng. |
| Phép toán | Chủ yếu không trạng thái; không phải giữ nhiều ràng buộc thứ tự. |
| Tài nguyên chung | Không gây nghẽn I/O, khóa hay cạnh tranh CPU với tác vụ khác. |

Không nên mặc định chuyển mọi `stream()` thành `parallelStream()`. Với tập nhỏ, tính toán rất nhẹ hoặc môi trường đã có nhiều tác vụ đồng thời, tuần tự thường rõ ràng và có thể nhanh hơn. Nếu hiệu năng là lý do chuyển chế độ, hãy benchmark trong điều kiện gần thực tế, có warm-up và đo riêng phần tạo dữ liệu, phần xử lý, phần thu kết quả.

## 8. An toàn với dữ liệu nguồn và vòng đời

Tạo Stream từ Collection **không tạo bản sao bất biến** của dữ liệu. Với những Collection thông dụng không hỗ trợ cập nhật đồng thời, sửa cấu trúc Collection khi pipeline đang duyệt có thể dẫn đến `ConcurrentModificationException` hoặc hành vi không được bảo đảm. Không nên dựa vào ngoại lệ đó như cơ chế phát hiện mọi xung đột.

```java
List<String> names = new ArrayList<>(Arrays.asList("An", "Binh", "Chi"));

// Không cập nhật danh sách trong quá trình stream đang đọc nó:
// names.stream().forEach(name -> names.remove(name)); // Sai

List<String> snapshot = new ArrayList<>(names);
List<String> upper = snapshot.stream()
    .map(String::toUpperCase)
    .collect(Collectors.toList());
```

`snapshot` là bản sao nội dung của List tại thời điểm sao chép (đối với đối tượng phần tử có thể thay đổi, đây chỉ là bản sao **nông**). Nếu nhiều luồng cùng sửa `names`, thao tác tạo snapshot cũng cần phối hợp đồng bộ phù hợp. Có các Collection đồng thời với hợp đồng khác, nhưng không nên suy rộng rằng việc đổi sang `parallelStream()` tự biến nguồn thành an toàn đa luồng.

Một số nguyên tắc thực hành:

1. Giữ các hàm truyền cho `map`, `filter` và `reduce` **không sửa nguồn**, không phụ thuộc vào trạng thái có thể bị các luồng khác thay đổi.
2. Tạo Stream mới mỗi lần cần một terminal operation khác; không tái sử dụng Stream sau khi đã tiêu thụ.
3. Các Collection nằm trong bộ nhớ thường không cần `close()` sau `stream()`; nguồn từ tệp hoặc tài nguyên ngoài có quy tắc đóng riêng, ví dụ `Files.lines(...)` cần `try-with-resources`.
4. Đừng dựa vào kết quả thu thập là một `ArrayList` có thể chỉnh sửa: `Collectors.toList()` không hứa loại List cụ thể hoặc khả năng thay đổi. Khi cần đích là `ArrayList`, dùng `collect(Collectors.toCollection(ArrayList::new))`.
5. Chuyển dữ liệu số từ `Collection<Integer>` sang primitive Stream bằng `mapToInt(Integer::intValue)` hoặc `mapToLong(Integer::longValue)` khi thích hợp, giảm thao tác đóng/mở hộp trong các bước tính toán tiếp theo.

## 9. Bài tập vận dụng có đáp án

### Bài 1: Danh sách đơn hàng

Cho các giá trị đơn hàng `List<Integer> amounts = Arrays.asList(120, 50, 300, 80, 150);`. Tính tổng các đơn từ `100` trở lên bằng Stream tuần tự và song song.

```java
List<Integer> amounts = Arrays.asList(120, 50, 300, 80, 150);

long sequential = amounts.stream()
    .filter(amount -> amount >= 100)
    .mapToLong(Integer::longValue)
    .sum();

long parallel = amounts.parallelStream()
    .filter(amount -> amount >= 100)
    .mapToLong(Integer::longValue)
    .sum();

// sequential = parallel = 570
```

**Giải thích:** Cả hai cách lọc ba giá trị `120`, `300`, `150` và cộng bằng phép toán tổng hợp thích hợp. Bài này chưa cần chạy song song để đạt hiệu năng tốt.

### Bài 2: Có bảo đảm thứ tự đầu ra không?

```java
List<String> words = Arrays.asList("cat", "apple", "dog", "banana");
List<String> out = words.parallelStream()
    .filter(s -> s.length() >= 4)
    .map(String::toUpperCase)
    .collect(Collectors.toList());
```

**Đáp án:** `out` là `[APPLE, BANANA]` theo encounter order của List. Thứ tự *thực thi* của các lời gọi `filter` và `map` có thể khác nhau, nhưng `collect(Collectors.toList())` giữ thứ tự phần tử của nguồn có thứ tự.

### Bài 3: Nhận diện lỗi

```java
List<Integer> values = Arrays.asList(1, 2, 3, 4);
List<Integer> shared = new ArrayList<>();
values.parallelStream().filter(n -> n % 2 == 0)
    .forEach(shared::add);
```

**Đáp án:** `shared` là `ArrayList` bị nhiều luồng ghi đồng thời, không an toàn. Viết lại:

```java
List<Integer> evens = values.parallelStream()
    .filter(n -> n % 2 == 0)
    .collect(Collectors.toList()); // [2, 4]
```

### Bài 4: Stream từ Map

Cho `Map<String, Integer> inventory` lưu tên sản phẩm và số lượng tồn. Vì sao `inventory.stream()` không hợp lệ, và làm sao lấy tên các sản phẩm còn hàng?

```java
Map<String, Integer> inventory = new HashMap<>();
inventory.put("book", 12);
inventory.put("pen", 0);
inventory.put("notebook", 3);

List<String> available = inventory.entrySet().stream()
    .filter(entry -> entry.getValue() > 0)
    .map(Map.Entry::getKey)
    .collect(Collectors.toList());
// Bao gồm "book" và "notebook"; thứ tự không được HashMap bảo đảm.
```

**Giải thích:** `Map` không triển khai `Collection`. `entrySet()` trả về một `Set<Map.Entry<String, Integer>>`, nên có thể tạo Stream từ Set này rồi lọc và lấy key.

## Ghi nhớ

`Collection.stream()` là lựa chọn mặc định để xây pipeline tuần tự, dễ dự đoán và thường đủ nhanh. `Collection.parallelStream()` phù hợp khi dữ liệu có thể chia hiệu quả, mỗi phần tử được xử lý độc lập và chi phí tính toán đủ lớn. Cả hai **đều mô tả một pipeline lười, tiêu thụ một lần**, chia sẻ các quy tắc về encounter order, trạng thái của lambda và tính đúng đắn của phép thu thập. Hãy chọn chế độ dựa trên hợp đồng của bài toán và đo đạc thực tế, thay vì cho rằng “song song” tự động nhanh hoặc an toàn hơn.
