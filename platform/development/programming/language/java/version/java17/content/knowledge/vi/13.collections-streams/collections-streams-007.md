# Đánh giá lười, một lần sử dụng và tác dụng phụ trong pipeline Stream — Java 17

Stream API trong Java giúp xử lý dữ liệu theo một chuỗi thao tác như lọc, biến đổi, sắp xếp, giới hạn và tổng hợp. Khi đọc một pipeline, có thể thấy nhiều lời gọi nối tiếp nhau:

```java
List<String> result = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .sorted()
        .toList();
```

Tuy nhiên, các thao tác trong pipeline không nhất thiết chạy ngay khi được gọi. Phần lớn **intermediate operation** (thao tác trung gian) được đánh giá lười: chúng chỉ mô tả công việc cần làm. Việc duyệt dữ liệu thường bắt đầu khi có **terminal operation** (thao tác kết thúc) như `toList()`, `collect()`, `forEach()` hoặc `count()`.

Một Stream cũng được thiết kế để **sử dụng một lần**. Sau khi đã thực hiện terminal operation hoặc đóng stream, không được dùng lại stream đó cho một pipeline khác. Cuối cùng, các hàm truyền vào pipeline nên hạn chế tác dụng phụ để kết quả dễ dự đoán, đặc biệt khi stream chạy song song.

Bài học tập trung vào ba đặc tính cần hiểu khi làm việc với Collection và Stream trong Java 17:

1. **Đánh giá lười:** khi nào các thao tác thực sự chạy.
2. **Một lần sử dụng:** vì sao một stream không thể được duyệt lại.
3. **Tác dụng phụ trong pipeline:** vì sao nên dùng các phép biến đổi và tổng hợp thay cho việc sửa trạng thái bên ngoài từ bên trong lambda.

## 1. Pipeline Stream gồm những phần nào?

Một pipeline Stream thông thường gồm ba phần:

- **Nguồn dữ liệu (source):** Collection, array, generator hoặc một nguồn dữ liệu khác.
- **Các intermediate operation:** tạo pipeline mới bằng cách mô tả thao tác như `filter`, `map`, `sorted`, `distinct`, `limit`.
- **Terminal operation:** kích hoạt xử lý và tạo kết quả, tác dụng phụ cuối cùng hoặc một giá trị tổng hợp.

Ví dụ:

```java
List<String> names = List.of("An", "Binh", "Chi", "Dung");

List<String> result = names.stream()       // Source
        .filter(name -> name.length() > 2) // Intermediate
        .map(String::toUpperCase)          // Intermediate
        .toList();                         // Terminal

System.out.println(result);
```

Kết quả:

```text
[BINH, DUNG]
```

Có thể hình dung:

```text
Collection / Array
       |
       v
   stream()
       |
       v
 filter(predicate)      Intermediate operation
       |
       v
 map(function)          Intermediate operation
       |
       v
 toList()               Terminal operation
       |
       v
 Kết quả được tạo ra
```

Các lời gọi `filter` và `map` trả về một Stream khác, cho phép nối tiếp pipeline. Chúng không tạo ra một Collection trung gian mới sau mỗi bước. Terminal operation mới yêu cầu stream xử lý dữ liệu để tạo kết quả.

## 2. Đánh giá lười là gì?

**Lazy evaluation** có nghĩa là một thao tác trung gian không thực hiện toàn bộ công việc ngay tại thời điểm gọi nó. Thay vào đó, Stream ghi nhận thao tác cần thực hiện và đợi terminal operation kích hoạt pipeline.

Ví dụ:

```java
import java.util.List;
import java.util.stream.Stream;

public class LazyDemo {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh", "Chi");

        Stream<String> pipeline = names.stream()
                .filter(name -> {
                    System.out.println("filter: " + name);
                    return name.length() > 2;
                })
                .map(name -> {
                    System.out.println("map: " + name);
                    return name.toUpperCase();
                });

        System.out.println("Pipeline đã được tạo");

        List<String> result = pipeline.toList();

        System.out.println("Kết quả: " + result);
    }
}
```

Đầu ra theo thứ tự thực thi:

```text
Pipeline đã được tạo
filter: An
filter: Binh
map: Binh
filter: Chi
map: Chi
Kết quả: [BINH, CHI]
```

Khi gọi `stream()`, `filter()` và `map()`, chương trình chỉ xây dựng pipeline. Các lambda bên trong chưa chạy. Sau khi gọi `toList()`, stream bắt đầu duyệt nguồn và thực hiện các bước cần thiết.

Lưu ý thứ tự log: với pipeline không yêu cầu sắp xếp toàn cục, các thao tác có thể được thực hiện theo từng phần tử: kiểm tra một phần tử, nếu đạt thì biến đổi ngay phần tử đó, rồi chuyển sang phần tử tiếp theo. Không nên mặc định rằng Stream sẽ chạy hết toàn bộ `filter` trên mọi phần tử rồi mới chạy toàn bộ `map`.

## 3. Intermediate operation và terminal operation

Phân biệt hai nhóm thao tác giúp biết khi nào pipeline thực sự chạy.

### 3.1. Intermediate operation

Intermediate operation nhận một Stream và trả về một Stream khác. Chúng thường có tính lazy.

Một số thao tác phổ biến:

| Thao tác | Vai trò | Có lazy không? |
| --- | --- | --- |
| `filter(predicate)` | Giữ phần tử thỏa điều kiện. | Có |
| `map(function)` | Biến đổi từng phần tử. | Có |
| `flatMap(function)` | Biến mỗi phần tử thành một stream con rồi làm phẳng. | Có |
| `distinct()` | Loại bỏ phần tử trùng theo `equals()`. | Có |
| `sorted()` | Sắp xếp các phần tử. | Có; cần xử lý dữ liệu để xác định thứ tự |
| `limit(n)` | Giới hạn số phần tử đầu ra. | Có, là short-circuiting intermediate operation |
| `skip(n)` | Bỏ qua một số phần tử đầu. | Có |
| `peek(action)` | Thực hiện hành động khi phần tử đi qua pipeline. | Có; không nên dùng làm nơi chứa logic nghiệp vụ có tác dụng phụ |

Một thao tác trung gian không kích hoạt pipeline chỉ vì nó được gọi. Có thể tạo nhiều bước nối tiếp trước khi quyết định lấy kết quả.

### 3.2. Terminal operation

Terminal operation kết thúc pipeline hiện tại và kích hoạt xử lý.

| Thao tác | Kết quả |
| --- | --- |
| `toList()` | Danh sách kết quả không cho sửa (Java 16+). |
| `collect(collector)` | Thu thập kết quả theo Collector, ví dụ `Collectors.toList()`. |
| `forEach(action)` | Thực hiện hành động với từng phần tử. |
| `forEachOrdered(action)` | Thực hiện hành động theo encounter order nếu nguồn có thứ tự. |
| `count()` | Đếm số phần tử. |
| `min(comparator)` / `max(comparator)` | Tìm phần tử nhỏ nhất/lớn nhất. |
| `reduce(...)` | Kết hợp phần tử thành một kết quả. |
| `anyMatch(predicate)` | Kiểm tra có ít nhất một phần tử khớp. |
| `allMatch(predicate)` | Kiểm tra mọi phần tử có khớp. |
| `noneMatch(predicate)` | Kiểm tra không có phần tử nào khớp. |
| `findFirst()` / `findAny()` | Tìm một phần tử. |

Sau terminal operation, stream đã được tiêu thụ và không thể dùng để tạo một pipeline khác.

### 3.3. Ví dụ nhận diện điểm kích hoạt

```java
Stream<Integer> stream = List.of(1, 2, 3, 4).stream()
        .filter(number -> number % 2 == 0)
        .map(number -> number * 10);

// Đến đây pipeline mới được mô tả.
// Chưa có terminal operation nên chưa duyệt phần tử.

long count = stream.count(); // Terminal: kích hoạt pipeline.

System.out.println(count); // 2
```

Không có kết quả danh sách nào được tạo bởi riêng lời gọi `filter` hoặc `map`. Chỉ khi `count()` được gọi, pipeline mới được thực thi để xác định kết quả.

## 4. Lazy không có nghĩa là mọi thao tác đều xử lý từng phần tử theo cùng một cách

Một số thao tác có thể xử lý phần tử theo luồng, một số thao tác cần thông tin rộng hơn về dữ liệu.

- `filter` và `map` thường có thể xử lý từng phần tử khi phần tử đi qua pipeline.
- `limit` có thể ngừng yêu cầu phần tử mới khi đã nhận đủ số lượng.
- `sorted` cần xác định thứ tự của các phần tử liên quan trước khi phát kết quả theo thứ tự đã sắp xếp.
- `distinct` cần theo dõi các giá trị đã gặp để loại bỏ trùng lặp.

Ví dụ:

```java
List<Integer> result = List.of(8, 2, 5, 1, 4).stream()
        .filter(number -> number % 2 == 0)
        .sorted()
        .limit(2)
        .toList();

System.out.println(result);
```

Kết quả:

```text
[2, 4]
```

Pipeline chỉ xuất tối đa hai phần tử sau sắp xếp. Tuy nhiên, để biết hai số chẵn nhỏ nhất, thao tác `sorted()` cần xem xét các phần tử đầu vào đủ để xác định thứ tự. Không nên cho rằng `limit(2)` luôn khiến Stream chỉ đọc đúng hai phần tử nguồn.

**Lazy evaluation không đồng nghĩa mọi pipeline đều có thể dừng sớm.** Khả năng dừng phụ thuộc loại thao tác, thứ tự pipeline và terminal operation.

## 5. Short-circuiting: dừng khi đã đủ thông tin

Một số thao tác có thể kết thúc việc duyệt sớm khi đã biết kết quả.

### 5.1. Terminal operation short-circuiting

Các terminal operation sau có khả năng short-circuit:

- `anyMatch`: dừng khi tìm thấy phần tử khớp.
- `allMatch`: dừng khi tìm thấy phần tử không khớp.
- `noneMatch`: dừng khi tìm thấy phần tử khớp.
- `findFirst` và `findAny`: dừng khi đã tìm được phần tử phù hợp.

Ví dụ:

```java
import java.util.List;

public class ShortCircuitDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 3, 4, 7, 9);

        boolean found = numbers.stream()
                .filter(number -> {
                    System.out.println("Kiểm tra: " + number);
                    return number % 2 == 0;
                })
                .anyMatch(number -> number > 2);

        System.out.println("Found: " + found);
    }
}
```

Đầu ra:

```text
Kiểm tra: 1
Kiểm tra: 3
Kiểm tra: 4
Found: true
```

Sau khi tìm được số 4 thỏa cả điều kiện lọc và `anyMatch`, terminal operation đã biết kết quả là `true`. Các phần tử 7 và 9 không cần được xử lý.

### 5.2. Intermediate operation short-circuiting

`limit(n)` là một short-circuiting intermediate operation: nó giới hạn số phần tử được chuyển tiếp xuống phần sau pipeline.

```java
List<Integer> firstThree = Stream.iterate(1, number -> number + 1)
        .filter(number -> number % 2 == 1)
        .limit(3)
        .toList();

System.out.println(firstThree);
```

Kết quả:

```text
[1, 3, 5]
```

`Stream.iterate` tạo một nguồn vô hạn. Pipeline vẫn có thể hoàn tất vì `limit(3)` chỉ cho ba phần tử đi tiếp và `toList()` thu thập số phần tử hữu hạn đó.

Nếu bỏ `limit(3)` rồi gọi `toList()` trên stream vô hạn, thao tác sẽ không hoàn tất bình thường và có thể tiếp tục tiêu thụ tài nguyên.

## 6. Stream chỉ được sử dụng một lần

Stream không phải Collection. Nó là một pipeline dùng để xử lý dữ liệu từ một nguồn.

Ví dụ:

```java
List<String> names = List.of("An", "Binh", "Chi");

Stream<String> stream = names.stream();

long count = stream.count();

// Không được dùng lại stream đã tiêu thụ:
List<String> result = stream.toList(); // Sai
```

Sau khi gọi `count()`, stream đã được sử dụng. Gọi tiếp `toList()` trên cùng stream là không hợp lệ. Việc dùng lại stream đã tiêu thụ có thể dẫn đến `IllegalStateException`; không nên phụ thuộc vào việc mọi implementation luôn phát hiện và báo lỗi theo cùng một cách.

### Cách đúng: tạo stream mới từ nguồn

Nếu cần thực hiện hai phép xử lý độc lập, hãy gọi `stream()` lại trên Collection:

```java
List<String> names = List.of("An", "Binh", "Chi");

long count = names.stream().count();

List<String> upperNames = names.stream()
        .map(String::toUpperCase)
        .toList();

System.out.println(count);
System.out.println(upperNames);
```

Kết quả:

```text
3
[AN, BINH, CHI]
```

Collection vẫn có thể tạo nhiều stream độc lập. Mỗi stream mới là một pipeline riêng, có thể được tiêu thụ một lần.

### Nếu cần dùng kết quả nhiều lần, lưu kết quả thay vì lưu Stream

Ví dụ:

```java
List<String> names = List.of("An", "Binh", "Chi");

List<String> normalized = names.stream()
        .map(String::toUpperCase)
        .toList();

long count = normalized.size();
boolean hasAn = normalized.contains("AN");

System.out.println(count);
System.out.println(hasAn);
```

Kết quả đã thu thập là một Collection có thể được đọc nhiều lần. Trong ví dụ Java 17, `Stream.toList()` trả danh sách không thể sửa; nếu cần danh sách có thể thay đổi, dùng `collect(Collectors.toCollection(ArrayList::new))` hoặc một Collector phù hợp.

## 7. Không phải mọi nguồn Stream đều có thể tạo lại

Collection thường có thể gọi `stream()` nhiều lần. Nhưng một số nguồn được thiết kế để tiêu thụ một lần hoặc gắn với tài nguyên bên ngoài.

Ví dụ `Files.lines(path)` trả một Stream đọc các dòng của file và cần đóng sau khi sử dụng. Không nên giữ stream đó rồi cố dùng lại.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class FileLinesDemo {
    public static void main(String[] args) throws IOException {
        Path path = Path.of("notes.txt");

        try (var lines = Files.lines(path)) {
            List<String> nonBlank = lines
                    .filter(line -> !line.isBlank())
                    .toList();

            System.out.println(nonBlank);
        }
    }
}
```

Try-with-resources đóng stream và tài nguyên file liên quan sau khi hoàn tất.

Nếu cần xử lý file nhiều lần, hãy mở một stream mới trong mỗi lần xử lý:

```java
long lineCount;

try (var lines = Files.lines(path)) {
    lineCount = lines.count();
}

List<String> matchingLines;

try (var lines = Files.lines(path)) {
    matchingLines = lines
            .filter(line -> line.contains("Java"))
            .toList();
}
```

Mỗi lần `Files.lines(path)` tạo một stream mới. Không dùng lại stream đã đóng hoặc đã tiêu thụ.

## 8. Tác dụng phụ trong lambda là gì?

Một hàm có **tác dụng phụ (side effect)** khi ngoài việc tính và trả về kết quả, nó còn thay đổi trạng thái bên ngoài hoặc thực hiện hành động quan sát được khác.

Ví dụ các tác dụng phụ:

- Thay đổi biến bên ngoài lambda.
- Thêm/xóa phần tử trong một Collection khác.
- Ghi file hoặc database.
- Gửi request mạng.
- Ghi log hoặc in ra console.
- Thay đổi đối tượng mutable được chia sẻ.

Stream có thể gọi lambda để xử lý từng phần tử, nhưng việc nhúng quá nhiều tác dụng phụ vào `map` hoặc `filter` khiến pipeline khó hiểu và dễ lỗi.

### Ví dụ không nên làm: sửa biến bên ngoài trong map

```java
List<String> names = List.of("An", "Binh", "Chi");
List<String> result = new ArrayList<>();

names.stream()
        .map(name -> {
            result.add(name.toUpperCase());
            return name;
        })
        .toList();
```

Ở đây `map` được dùng để thêm dữ liệu vào danh sách bên ngoài, trong khi giá trị trả về của `map` không phục vụ mục đích đó. Pipeline có thể viết trực tiếp hơn:

```java
List<String> result = names.stream()
        .map(String::toUpperCase)
        .toList();
```

Phép biến đổi thuần túy nhận một giá trị và trả giá trị mới, không cần thay đổi trạng thái bên ngoài.

### Ví dụ không nên làm: sửa Collection nguồn trong khi stream đang duyệt

```java
List<String> names = new ArrayList<>(
        List.of("An", "Binh", "Chi")
);

names.stream()
        .filter(name -> {
            if (name.isBlank()) {
                names.remove(name); // Không nên sửa nguồn đang được duyệt.
            }
            return !name.isBlank();
        })
        .toList();
```

Việc sửa cấu trúc nguồn trong khi pipeline đang duyệt có thể gây `ConcurrentModificationException` hoặc tạo hành vi không xác định theo hợp đồng nguồn/stream. Stream yêu cầu hành vi tham số không can thiệp (non-interfering) vào nguồn trong quá trình xử lý.

Nếu muốn tạo danh sách mới chỉ chứa phần tử hợp lệ, hãy dùng `filter` và thu kết quả:

```java
List<String> nonBlank = names.stream()
        .filter(name -> !name.isBlank())
        .toList();
```

Nếu mục tiêu thật sự là xóa phần tử khỏi Collection, có thể dùng API của Collection như `removeIf` với predicate phù hợp, hoặc tạo bản sao trước khi thay đổi. Không sửa nguồn trong lúc chính stream của nguồn đó đang hoạt động.

## 9. Behavioral parameter nên stateless và non-interfering

Stream API mô tả hai yêu cầu quan trọng đối với các hàm được truyền vào pipeline:

- **Non-interfering:** hàm không sửa đổi nguồn dữ liệu của stream trong quá trình pipeline đang chạy.
- **Stateless:** kết quả của hàm không phụ thuộc vào trạng thái có thể thay đổi trong lúc xử lý các phần tử khác.

Ví dụ hàm thuần:

```java
int length = "Java".length();

List<Integer> lengths = List.of("Java", "Stream", "API")
        .stream()
        .map(String::length)
        .toList();
```

Mỗi phần tử được xử lý độc lập. Kết quả không phụ thuộc phần tử nào đã chạy trước.

Ví dụ hàm phụ thuộc trạng thái bên ngoài:

```java
int[] counter = {0};

List<Integer> indexes = List.of("A", "B", "C")
        .stream()
        .map(value -> counter[0]++)
        .toList();
```

Ở stream tuần tự, đoạn mã có thể cho kết quả tăng dần như mong đợi. Nhưng kết quả của lambda phụ thuộc trạng thái thay đổi ngoài pipeline. Khi chuyển sang parallel stream, thứ tự thực thi và truy cập trạng thái chung có thể không còn như giả định ban đầu.

Một pipeline dễ kiểm soát hơn là dùng phép biến đổi có kết quả phụ thuộc trực tiếp vào dữ liệu đầu vào, hoặc dùng các thao tác tổng hợp được thiết kế cho Stream.

## 10. Vì sao side effect nguy hiểm hơn trong parallel stream?

Có thể chuyển stream tuần tự sang song song bằng `parallelStream()` hoặc `parallel()`. Khi chạy song song, nhiều phần tử có thể được xử lý trên nhiều thread.

Nếu các lambda cùng sửa một biến hoặc Collection mutable dùng chung, chương trình có thể gặp race condition, mất cập nhật hoặc kết quả không xác định.

**Sai — dùng ArrayList chung trong parallel stream:**

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

List<Integer> results = new ArrayList<>();

numbers.parallelStream()
        .forEach(number -> results.add(number * 2));
```

`ArrayList` không thread-safe. Nhiều thread thêm phần tử cùng lúc có thể làm hỏng trạng thái nội bộ hoặc cho kết quả sai.

**Đúng — dùng collect để Stream quản lý việc tổng hợp:**

```java
List<Integer> results = numbers.parallelStream()
        .map(number -> number * 2)
        .toList();
```

Ở đây `map` biến đổi từng phần tử, còn terminal operation thu kết quả theo cơ chế của Stream. Không cần tự chia sẻ danh sách mutable cho các thread.

Nếu cần Collector có kết quả mutable:

```java
List<Integer> results = numbers.parallelStream()
        .map(number -> number * 2)
        .collect(Collectors.toList());
```

Collector được thiết kế để kết hợp các phần kết quả từ quá trình xử lý. Không nên tự thay bằng một Collection chia sẻ chung bên ngoài.

## 11. Dùng reduce hoặc collect thay vì biến đếm bên ngoài

Khi cần tổng hợp, hãy chọn operation thể hiện đúng mục đích.

### Đếm phần tử

**Không nên:**

```java
int[] count = {0};

names.stream()
        .filter(name -> !name.isBlank())
        .forEach(name -> count[0]++);
```

**Nên:**

```java
long count = names.stream()
        .filter(name -> !name.isBlank())
        .count();
```

### Tính tổng

**Không nên:**

```java
int[] total = {0};

numbers.stream()
        .forEach(number -> total[0] += number);
```

**Nên:**

```java
int total = numbers.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

Hoặc dùng `reduce`:

```java
int total = numbers.stream()
        .reduce(0, Integer::sum);
```

Với phép cộng số nguyên, hai cách cho cùng kết quả trong miền giá trị không tràn. `mapToInt().sum()` thể hiện rõ ý định tổng hợp số học; `reduce` hữu ích cho phép kết hợp tổng quát hơn.

### Nhóm dữ liệu

Thay vì sửa một `Map` bên ngoài trong `forEach`, dùng Collector:

```java
Map<Integer, List<String>> namesByLength = names.stream()
        .collect(Collectors.groupingBy(String::length));
```

Collector mô tả kết quả cần tạo và cách nhóm dữ liệu. Cách viết này thường an toàn hơn khi thay đổi chiến lược xử lý giữa tuần tự và song song.

## 12. `forEach` có phải luôn là side effect xấu?

Không. `forEach` là terminal operation được thiết kế để thực hiện một hành động cho mỗi phần tử. Side effect có thể là mục tiêu chính của một pipeline, ví dụ gửi từng thông báo hoặc ghi từng dòng kết quả.

Tuy nhiên, cần phân biệt:

- Dùng `forEach` làm **điểm cuối để thực hiện hành động** có chủ đích.
- Dùng `map` hoặc `filter` để lén thay đổi trạng thái bên ngoài trong khi giá trị trả về của chúng không có ý nghĩa.

Ví dụ hành động cuối:

```java
names.stream()
        .filter(name -> !name.isBlank())
        .forEach(System.out::println);
```

Pipeline lọc dữ liệu rồi in từng kết quả. Đây là cách sử dụng hợp lệ khi mục tiêu là xuất dữ liệu.

Nếu cần thứ tự encounter order, có thể dùng `forEachOrdered`:

```java
names.parallelStream()
        .filter(name -> !name.isBlank())
        .forEachOrdered(System.out::println);
```

`forEachOrdered` bảo đảm hành động được thực hiện theo encounter order của nguồn có thứ tự. Điều đó không đồng nghĩa mọi bước trước đó đều chạy tuần tự; các phần tử vẫn có thể được xử lý song song trước khi hành động được sắp theo thứ tự.

Nếu hành động ghi vào file, gửi mạng hoặc cập nhật database, hãy cân nhắc quản lý lỗi, transaction, giới hạn tốc độ và tính lặp lại. Stream không tự biến những side effect đó thành thao tác nguyên tử.

## 13. Không dựa vào `peek` để thực hiện nghiệp vụ

`peek` được thiết kế chủ yếu để quan sát các phần tử đi qua pipeline, thường dùng hỗ trợ debug:

```java
List<String> result = names.stream()
        .filter(name -> !name.isBlank())
        .peek(name -> System.out.println("Sau filter: " + name))
        .map(String::toUpperCase)
        .toList();
```

Khi pipeline thực sự duyệt phần tử, hành động của `peek` có thể được gọi với phần tử tương ứng. Nhưng không nên dùng `peek` để thực hiện nghiệp vụ bắt buộc như gửi email, ghi database hoặc cập nhật trạng thái.

Một lý do quan trọng: Stream implementation có thể tối ưu pipeline và bỏ qua việc thực thi một số behavioral parameter nếu điều đó không ảnh hưởng đến kết quả của terminal operation. Ví dụ, với một nguồn có kích thước đã biết và pipeline chỉ có thao tác không làm thay đổi số lượng, `count()` có thể lấy trực tiếp kích thước mà không duyệt phần tử; khi đó hành động trong `peek` có thể không được gọi.

Ví dụ không được dùng để đảm bảo log:

```java
long count = List.of("A", "B", "C").stream()
        .peek(System.out::println)
        .count();
```

Kết quả `count` vẫn là 3, nhưng không nên dựa vào việc ba dòng được in ra. Implementation được phép tính số phần tử từ nguồn mà không thực hiện `peek` nếu việc bỏ qua không làm thay đổi kết quả của pipeline.

Nếu cần log để quan sát khi debug, có thể dùng `peek` nhưng phải chấp nhận đây không phải điểm thực thi nghiệp vụ được bảo đảm. Nếu cần thực hiện một hành động cho từng phần tử, hãy đặt nó ở thao tác terminal phù hợp hoặc thiết kế một bước xử lý rõ ràng.

## 14. Tác dụng phụ và thứ tự thực thi

Không nên giả định lambda được gọi theo thứ tự bạn đọc code, hoặc đúng một lần cho mỗi phần tử trong mọi pipeline.

Với stream tuần tự, encounter order của nguồn có thứ tự thường được giữ ở những operation có quy định bảo toàn thứ tự. Nhưng:

- Các operation có thể được tối ưu hóa.
- Short-circuiting có thể khiến một số phần tử không được xử lý.
- Một số thao tác có thể thay đổi thứ tự, ví dụ `unordered()`.
- Parallel stream có thể xử lý các phần tử trên nhiều thread và theo thứ tự khác nhau.
- Hành vi side effect của lambda không được bảo đảm chạy đúng một lần cho mỗi phần tử nếu pipeline/terminal operation không yêu cầu điều đó.

Ví dụ `findAny()`:

```java
Optional<Integer> found = numbers.parallelStream()
        .filter(number -> number > 10)
        .findAny();
```

`findAny()` có thể trả về bất kỳ phần tử nào thỏa điều kiện. Không nên viết side effect trong `filter` với giả định một phần tử cụ thể sẽ luôn được xét đầu tiên.

Nếu cần phần tử đầu tiên theo encounter order, dùng `findFirst()` trên nguồn có thứ tự:

```java
Optional<Integer> first = numbers.stream()
        .filter(number -> number > 10)
        .findFirst();
```

Nếu cần thứ tự khi thực hiện hành động, dùng terminal operation phù hợp như `forEachOrdered`. Đừng dùng thứ tự log của một lần chạy để suy ra cam kết thứ tự của mọi cách thực thi.

## 15. Stream pipeline không nên can thiệp vào nguồn

Một pipeline nên đọc nguồn ổn định trong khi nó đang chạy. Việc thêm hoặc xóa phần tử khỏi nguồn trong một behavioral parameter vi phạm nguyên tắc non-interference.

**Sai:**

```java
List<Integer> values = new ArrayList<>(List.of(1, 2, 3, 4));

values.stream()
        .filter(value -> {
            if (value % 2 == 0) {
                values.remove(value);
            }
            return true;
        })
        .toList();
```

**Đúng — tạo kết quả mới:**

```java
List<Integer> oddValues = values.stream()
        .filter(value -> value % 2 != 0)
        .toList();
```

**Đúng — nếu mục tiêu là xóa trực tiếp khỏi Collection, dùng API Collection:**

```java
values.removeIf(value -> value % 2 == 0);
```

`removeIf` thực hiện việc loại bỏ theo predicate trên Collection. Sau khi thay đổi nguồn xong, có thể tạo một stream mới để xử lý tiếp.

## 16. Nguồn dữ liệu mutable và thời điểm lấy dữ liệu

Stream từ Collection thường phản ánh dữ liệu của nguồn khi terminal operation bắt đầu, miễn là nguồn không bị can thiệp trong quá trình pipeline chạy. Vì vậy, nếu tạo pipeline rồi sửa Collection trước khi terminal operation được gọi, dữ liệu quan sát được có thể khác với lúc pipeline được tạo.

Ví dụ:

```java
List<String> names = new ArrayList<>(List.of("An", "Binh"));

Stream<String> stream = names.stream()
        .map(String::toUpperCase);

// Thay đổi xảy ra trước khi terminal operation bắt đầu.
names.add("Chi");

List<String> result = stream.toList();

System.out.println(result);
```

Với Collection thông thường như `ArrayList`, stream được tạo là stream late-binding: nó liên kết với nguồn khi bắt đầu terminal operation. Ví dụ có thể bao gồm phần tử được thêm trước lúc pipeline bắt đầu chạy.

Tuy vậy, không nên biến đặc điểm này thành cách cập nhật nguồn trong lúc xử lý. Một khi terminal operation đang duyệt nguồn, không can thiệp cấu trúc vào Collection đó. Nếu cần snapshot ổn định, tạo bản sao trước khi xây pipeline:

```java
List<String> snapshot = List.copyOf(names);

List<String> result = snapshot.stream()
        .map(String::toUpperCase)
        .toList();
```

`List.copyOf` tạo danh sách không cho sửa và không cho phần tử null. Đây là lựa chọn hữu ích khi cần snapshot các tham chiếu phần tử; nếu các phần tử bản thân là đối tượng mutable, bản sao này không phải deep copy.

## 17. Tách logic tính toán khỏi hành động bên ngoài

Một cách tổ chức rõ ràng là chia thành hai bước:

1. Dùng Stream để lọc, biến đổi và tạo dữ liệu kết quả.
2. Dùng kết quả đó để thực hiện side effect có chủ đích.

Ví dụ, tạo danh sách email hợp lệ rồi gửi:

```java
List<String> recipients = users.stream()
        .filter(User::isActive)
        .map(User::email)
        .filter(email -> email != null && !email.isBlank())
        .distinct()
        .toList();

for (String recipient : recipients) {
    mailService.sendWelcomeMessage(recipient);
}
```

Phần Stream tạo dữ liệu cần dùng. Vòng lặp thực hiện hành động gửi email, nơi dễ đặt retry, log lỗi, giới hạn tốc độ hoặc xử lý thất bại từng người nhận.

Không phải lúc nào cũng cần tách thành hai bước. Nhưng khi side effect quan trọng, có thể thất bại hoặc cần thứ tự/transaction rõ ràng, tách phép tính khỏi hành động giúp code dễ kiểm soát hơn.

## 18. Bảng so sánh cách viết

| Mục tiêu | Cách dễ gây vấn đề | Cách nên ưu tiên |
| --- | --- | --- |
| Chuyển đổi dữ liệu | Sửa Collection ngoài trong `map`. | Trả giá trị mới từ `map`. |
| Lọc dữ liệu | Xóa phần tử nguồn trong `filter`. | Dùng `filter` để tạo kết quả hoặc `removeIf` trước/sau pipeline. |
| Đếm | Tăng biến đếm ngoài trong `forEach`. | Dùng `count()`. |
| Tính tổng | Cộng vào biến mutable dùng chung. | Dùng `mapToInt().sum()` hoặc `reduce()`. |
| Nhóm dữ liệu | Sửa Map ngoài trong lambda. | Dùng `collect(groupingBy(...))`. |
| Tạo danh sách kết quả | Thêm vào ArrayList ngoài từ parallel stream. | Dùng `toList()` hoặc `collect()`. |
| Debug | Dùng `peek` làm logic nghiệp vụ bắt buộc. | Chỉ dùng `peek` để quan sát tạm thời; đặt side effect cần thiết ở bước rõ ràng. |
| Dùng pipeline hai lần | Gọi terminal operation lần hai trên cùng stream. | Tạo stream mới từ nguồn hoặc lưu Collection kết quả. |
| Kiểm tra có phần tử phù hợp | Duyệt hết rồi sửa biến boolean. | Dùng `anyMatch()`. |
| Tìm phần tử đầu tiên | Sửa biến ngoài trong `forEach` rồi cố dừng. | Dùng `findFirst()` trên nguồn có encounter order. |

## 19. Ví dụ tổng hợp: pipeline không side effect và pipeline có hành động cuối

Giả sử có danh sách giao dịch:

```java
import java.math.BigDecimal;

record Transaction(String account, BigDecimal amount, boolean approved) {
}
```

Ta cần tính tổng tiền của giao dịch được duyệt cho một tài khoản.

Cách dùng Stream để tổng hợp:

```java
import java.math.BigDecimal;
import java.util.List;

public class TransactionSummary {

    static BigDecimal approvedTotal(
            List<Transaction> transactions,
            String account
    ) {
        return transactions.stream()
                .filter(Transaction::approved)
                .filter(tx -> tx.account().equals(account))
                .map(Transaction::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
```

Các lambda trong pipeline đọc dữ liệu và tạo kết quả. Không có biến tổng mutable nằm ngoài lambda.

Nếu muốn ghi từng giao dịch đã duyệt vào audit log, hãy xem đó là hành động cuối có chủ đích:

```java
transactions.stream()
        .filter(Transaction::approved)
        .filter(tx -> tx.account().equals(account))
        .forEach(auditService::record);
```

Trong trường hợp audit bắt buộc chính xác một lần, cần thiết kế thêm cơ chế transaction, idempotency hoặc lưu bền vững phù hợp. Stream không tự đảm bảo giao dịch bên ngoài chỉ xảy ra đúng một lần nếu có retry, lỗi mạng hoặc chạy lại nghiệp vụ.

## 20. Bài thực hành

### Bài 1 — quan sát lazy evaluation

Tạo pipeline `filter` và `map` có `System.out.println` trong lambda nhưng chưa gọi terminal operation. Quan sát rằng chưa có log. Sau đó gọi `toList()` và ghi lại thứ tự log.

### Bài 2 — short-circuit

Dùng `anyMatch()` với danh sách số có một phần tử đầu tiên thỏa điều kiện. In log trong predicate để xem những phần tử nào được kiểm tra. Giải thích vì sao các phần tử sau có thể không được duyệt.

### Bài 3 — sử dụng stream một lần

Tạo một Stream từ Collection, gọi `count()`, rồi thử gọi `toList()` trên chính stream đó. Quan sát lỗi. Sửa bằng cách gọi `collection.stream()` lần thứ hai.

### Bài 4 — thay side effect bằng reduce

Cho:

```java
List<Integer> numbers = List.of(2, 4, 6, 8);
```

Viết một phiên bản dùng biến mảng bên ngoài để cộng tổng, sau đó viết lại bằng `mapToInt().sum()` hoặc `reduce()`. So sánh độ rõ ràng của hai cách.

### Bài 5 — không sửa nguồn trong pipeline

Cho một `ArrayList` chứa số chẵn và lẻ. Thử viết `filter` nhưng không xóa phần tử khỏi nguồn. Tạo danh sách mới chỉ có số lẻ. Nếu muốn xóa số chẵn khỏi danh sách gốc, dùng `removeIf` riêng.

### Bài 6 — quan sát giới hạn của peek

Tạo pipeline từ một Collection có kích thước đã biết, gọi `peek(System.out::println).count()`. Quan sát kết quả trên JDK đang dùng. Giải thích vì sao không nên dùng `peek` để thực hiện hành động bắt buộc, kể cả khi một lần chạy có in log.

### Bài 7 — parallel stream và trạng thái chung

Thử thêm kết quả từ `parallelStream()` vào một `ArrayList` chung. Sau đó thay bằng `map(...).toList()`. Giải thích vì sao cách thứ hai thể hiện phép biến đổi và thu thập kết quả phù hợp hơn.

## 21. Ghi nhớ nhanh

| Khái niệm | Điều cần nhớ |
| --- | --- |
| Pipeline | Source + intermediate operations + terminal operation. |
| Lazy evaluation | Intermediate operations thường chỉ mô tả công việc; terminal operation kích hoạt xử lý. |
| Terminal operation | Kết thúc stream hiện tại và tiêu thụ stream. |
| Single-use | Không chạy terminal operation lần hai trên cùng stream; tạo stream mới từ nguồn nếu cần. |
| Short-circuit | Có thể dừng sớm khi đã đủ thông tin, như `anyMatch` hoặc `findFirst`. |
| Stateless | Kết quả lambda không phụ thuộc trạng thái thay đổi trong lúc xử lý các phần tử khác. |
| Non-interfering | Không sửa nguồn stream trong lúc pipeline đang chạy. |
| Side effect | Thay đổi trạng thái bên ngoài, I/O hoặc hành động quan sát được khác. |
| Parallel stream | Có thể chạy nhiều phần tử trên nhiều thread; tránh chia sẻ trạng thái mutable không được bảo vệ. |
| `reduce` và `collect` | Dùng để tổng hợp kết quả thay cho biến mutable bên ngoài. |
| `peek` | Hữu ích để quan sát/debug tạm thời; không dùng làm nơi chứa nghiệp vụ bắt buộc. |

**Nguyên tắc cốt lõi:** Hãy xem Stream là một pipeline mô tả cách biến đổi dữ liệu. Các intermediate operation được đánh giá lười, terminal operation kích hoạt pipeline, và mỗi stream chỉ được tiêu thụ một lần. Giữ lambda stateless, non-interfering và hạn chế side effect; dùng `map`, `filter`, `reduce` và `collect` để thể hiện phép tính, còn hành động bên ngoài nên được đặt ở điểm thực thi rõ ràng.
