# Tính lười và thời điểm pipeline thực sự được thực thi

Trong Java Stream API, một pipeline thường có ba phần: **nguồn dữ liệu (source)**, các **phép toán trung gian (intermediate operations)** và một **phép toán kết thúc (terminal operation)**. Điểm quyết định cách Stream hoạt động là **tính lười (laziness)**: phần lớn công việc xử lý từng phần tử được trì hoãn cho đến khi có nhu cầu lấy kết quả.

Chủ đề này thuộc chương **Hợp đồng và vòng đời pipeline** của **JAVA_STREAM_API**. Nắm được thời điểm thực thi giúp ta viết các chuỗi `filter`, `map`, `reduce` và `collect` đúng ý nghĩa, tận dụng khả năng dừng sớm, tránh tác dụng phụ khó đoán và quản lý tài nguyên an toàn.

## 1. Khai báo pipeline khác với chạy pipeline

Xét biểu thức:

```java
Stream<String> pipeline = names.stream()
    .filter(name -> name.length() >= 3)
    .map(String::toUpperCase);
```

Tại thời điểm gán biến `pipeline`, Java đã tạo các đối tượng mô tả pipeline. Tuy nhiên, **`filter` và `map` chưa phải xử lý lần lượt tất cả phần tử trong `names`**. Chúng là các phép toán trung gian trả về một Stream để có thể ghép thêm bước tiếp theo.

Đến khi viết:

```java
List<String> result = pipeline.collect(Collectors.toList());
```

`collect` là phép toán kết thúc, yêu cầu kết quả và kéo dữ liệu đi qua các bước trước đó. Với một Stream tuần tự thông thường, quá trình này thường xử lý từng phần tử qua các bước có thể kết hợp, thay vì tạo một danh sách tạm sau mỗi `filter` hay `map`.

| Thành phần | Ví dụ | Khi gọi, điều gì xảy ra? |
| --- | --- | --- |
| Nguồn | `list.stream()`, `Stream.of(...)`, `Files.lines(...)` | Tạo nguồn cho pipeline; có thể khởi tạo tài nguyên hoặc đánh giá đối số ngay tại đây. |
| Trung gian không trạng thái | `filter`, `map`, `flatMap` | Ghép thêm quy tắc biến đổi/lọc; thường chưa duyệt phần tử. |
| Trung gian có trạng thái | `sorted`, `distinct` | Ghép thêm bước cần quan sát hoặc lưu thông tin về các phần tử; khi chạy có thể cần bộ đệm. |
| Trung gian giới hạn luồng | `limit`, `skip`, `takeWhile` | Mô tả cách chọn phạm vi phần tử; một số có thể góp phần dừng sớm khi tiêu thụ. |
| Kết thúc | `collect`, `reduce`, `sum`, `forEach`, `findFirst`, `count` | Kích hoạt việc đánh giá cần thiết để cho ra kết quả hoặc tác dụng của phép toán. |

> **Phân biệt quan trọng:** “Lười” không có nghĩa là mọi biểu thức Java ở bước tạo nguồn đều bị hoãn. Chẳng hạn, trong `Stream.of(expensiveCall())`, Java gọi `expensiveCall()` để tính đối số *trước* khi tạo Stream. Tương tự, `Files.lines(path)` có thể mở tệp ngay lúc tạo Stream, dù việc duyệt các dòng diễn ra về sau.

## 2. Quan sát chính xác thời điểm thực thi

Ví dụ sau chạy được với các API Stream có từ Java 8:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class LazyPipelineDemo {
    public static void main(String[] args) {
        List<String> names = Arrays.asList("An", "Binh", "Chi", "Dung");

        Stream<String> pipeline = names.stream()
            .filter(name -> {
                System.out.println("filter: " + name);
                return name.length() >= 3;
            })
            .map(name -> {
                System.out.println("map: " + name);
                return name.toUpperCase();
            });

        System.out.println("Pipeline đã được khai báo");
        List<String> result = pipeline.collect(Collectors.toList());
        System.out.println("Kết quả: " + result);
    }
}
```

Đầu ra với pipeline tuần tự và danh sách có thứ tự:

```text
Pipeline đã được khai báo
filter: An
filter: Binh
map: Binh
filter: Chi
map: Chi
filter: Dung
map: Dung
Kết quả: [BINH, CHI, DUNG]
```

Có hai điều cần chú ý:

1. Dòng “Pipeline đã được khai báo” xuất hiện **trước** mọi dòng `filter`/`map`. Việc khai báo các phép toán trung gian chưa duyệt danh sách.
2. `filter: Binh` được theo sau ngay bởi `map: Binh`, chứ không phải đợi lọc hết bốn tên rồi mới chạy `map`. Đây là cách các bước **không trạng thái** thường được kết hợp khi Stream tuần tự được tiêu thụ. `map` cũng không chạy với `An` vì phần tử này bị loại ở `filter`.

Không nên suy ra rằng mọi pipeline đều có thứ tự gọi hàm giống hệt ví dụ. `sorted`, `distinct`, xử lý song song và các tối ưu hóa của terminal operation có thể làm thay đổi cách phần tử được yêu cầu hoặc được đệm.

## 3. Terminal operation yêu cầu bao nhiêu dữ liệu?

Một phép toán kết thúc **bắt đầu quá trình đánh giá**, nhưng không nhất thiết buộc Stream duyệt hết nguồn. Nhu cầu thực tế phụ thuộc vào phép toán và các bước trước nó.

| Phép toán kết thúc | Nhu cầu thông thường | Lưu ý |
| --- | --- | --- |
| `collect(Collectors.toList())` | Thu thập tất cả phần tử còn lại | Pipeline có thể đã bị giới hạn bằng `limit` hoặc `takeWhile`. |
| `reduce(...)`, `sum()`, `max()` | Thường cần xem toàn bộ phần tử phù hợp | Kết quả tổng hợp phụ thuộc vào dữ liệu chưa xem. |
| `findFirst()` | Dừng khi xác định được phần tử đầu tiên theo encounter order | Có thể phải đọc nhiều phần tử nếu các bước lọc chưa cho kết quả. |
| `findAny()` | Có thể dừng khi tìm thấy một phần tử bất kỳ | Đặc biệt hữu ích với nguồn song song; không hứa phần tử đầu tiên. |
| `anyMatch(...)`, `allMatch(...)`, `noneMatch(...)` | Có khả năng dừng sớm khi kết quả đã chắc chắn | `anyMatch` gặp một phần tử đúng là đủ; `allMatch` gặp một phần tử sai là đủ. |
| `count()` | Trả về số phần tử của pipeline | Có thể tối ưu bằng kích thước nguồn và bỏ qua duyệt; xem mục 5. |

Ví dụ:

```java
import java.util.stream.IntStream;

int firstEven = IntStream.rangeClosed(1, 100)
    .peek(n -> System.out.println("Đã lấy: " + n))
    .filter(n -> n % 2 == 0)
    .findFirst()
    .orElse(-1);

System.out.println("Số chẵn đầu tiên: " + firstEven);
```

Với pipeline **tuần tự** trên, đầu ra chỉ gồm `Đã lấy: 1`, `Đã lấy: 2` rồi `Số chẵn đầu tiên: 2`. `findFirst` có kết quả ngay sau khi gặp `2` nên không cần kiểm tra tiếp các số từ `3` đến `100`.

`limit` là **phép toán trung gian** nhưng cũng có thể cho phép dừng sớm:

```java
List<Integer> firstTwoEvens = IntStream.rangeClosed(1, 10)
    .filter(n -> n % 2 == 0)
    .limit(2)
    .boxed()
    .collect(Collectors.toList()); // [2, 4]
```

`limit(2)` ở đây lấy **hai phần tử đã vượt qua `filter`**, nên pipeline phải xem đến số `4`. Nếu chuyển `limit(2)` lên trước `filter`, chỉ hai số đầu `1` và `2` được đưa qua bộ lọc, kết quả sẽ là `[2]`:

```java
List<Integer> different = IntStream.rangeClosed(1, 10)
    .limit(2)
    .filter(n -> n % 2 == 0)
    .boxed()
    .collect(Collectors.toList()); // [2]
```

**Thứ tự các phép toán là một phần của ý nghĩa bài toán**; việc hoán đổi bước để “tối ưu” có thể đổi kết quả.

## 4. Tính lười không loại bỏ chi phí của phép toán có trạng thái

Một phép toán trung gian có thể được *khai báo* một cách lười nhưng khi bắt đầu chạy lại cần tiêu thụ nhiều dữ liệu trước khi đưa ra kết quả đầu tiên.

Ví dụ với `sorted`:

```java
List<Integer> smallestTwo = Stream.of(9, 1, 8, 2, 7)
    .sorted()
    .limit(2)
    .collect(Collectors.toList()); // [1, 2]

List<Integer> firstTwoSorted = Stream.of(9, 1, 8, 2, 7)
    .limit(2)
    .sorted()
    .collect(Collectors.toList()); // [1, 9]
```

Trong biểu thức thứ nhất, để biết hai phần tử nhỏ nhất, bước `sorted` của Stream tuần tự phải tiếp nhận toàn bộ năm giá trị rồi mới có thể phát ra dữ liệu theo thứ tự đã sắp xếp. Trong biểu thức thứ hai, `limit` chỉ đưa hai giá trị ban đầu vào `sorted`.

Một vài hệ quả:

- `sorted` thường cần lưu nhiều phần tử, nên `sorted().findFirst()` không có khả năng dừng sớm như `filter().findFirst()` trên nguồn có thứ tự.
- `distinct` cần ghi nhận các giá trị đã gặp để loại trùng; tùy pipeline và encounter order, nó có thể phát kết quả dần nhưng vẫn có chi phí trạng thái.
- Với nguồn **vô hạn**, `Stream.iterate(0, n -> n + 1).sorted().findFirst()` không thể hoàn tất theo cách đánh giá thông thường vì `sorted` phải nhận hết đầu vào. Đặt một giới hạn hữu hạn **trước** `sorted` khi bài toán thực sự chỉ xét một số phần tử đầu.

Từ Java 9, `takeWhile` có thể dừng khi gặp phần tử đầu tiên **không thỏa điều kiện** trên Stream có encounter order; `dropWhile` loại phần đầu thỏa điều kiện rồi tiếp tục truyền phần còn lại. Chúng cũng cần được đặt đúng vị trí trong pipeline.

## 5. Có terminal nhưng không phải lambda nào cũng được gọi

Một điểm dễ gây lỗi là cho rằng sau khi gọi `count()` thì mọi `map` hoặc `peek` chắc chắn sẽ chạy. Điều này **không thuộc hợp đồng của Stream**.

```java
long size = Stream.of("A", "BB", "CCC")
    .peek(System.out::println)
    .count();

System.out.println("Số phần tử: " + size); // 3
```

Nguồn `Stream.of(...)` biết sẵn có ba phần tử; `peek` không thay đổi số lượng. Trên các bản JDK có tối ưu hóa `count` (từ Java 9), việc duyệt nguồn và gọi `peek` có thể bị bỏ qua hoàn toàn. Vì vậy **không được dựa vào tác dụng phụ trong `peek`, `map` hay lambda trung gian để bảo đảm một hành động quan trọng đã xảy ra**.

Khác với ví dụ trên, `filter` có thể thay đổi số phần tử:

```java
long longerThanOne = Stream.of("A", "BB", "CCC")
    .filter(s -> s.length() > 1)
    .count(); // 2
```

Ở đây, bộ lọc cần được đánh giá để xác định số phần tử còn lại, trừ khi có một tối ưu hóa khác bảo toàn đúng ngữ nghĩa mà việc cài đặt áp dụng.

**Quy tắc sử dụng:** coi `map`, `filter` và `peek` là các bước biểu diễn phép tính. Nếu mục đích là tạo một kết quả, dùng terminal phù hợp; nếu mục đích là thực hiện hành động có tác dụng phụ, cần làm rõ hành động đó tại ranh giới tiêu thụ thay vì “giấu” trong `peek`. `peek` hữu ích để quan sát khi gỡ lỗi, nhưng không phải một cơ chế kiểm toán chắc chắn.

## 6. Vòng đời: pipeline chỉ được tiêu thụ một lần

Sau khi pipeline đã được dùng cho một phép toán kết thúc, không thể dùng lại chính Stream đó để thực hiện truy vấn khác:

```java
Stream<Integer> values = Stream.of(10, 20, 30);

long count = values.count(); // 3

// Không hợp lệ: Stream đã được tiêu thụ.
// int first = values.findFirst().orElse(-1);
```

Lần gọi thứ hai thường gây `IllegalStateException`. Việc phát hiện tái sử dụng không được bảo đảm cho mọi cách xây pipeline, vì vậy phải luôn tuân thủ quy tắc **một pipeline, một lượt tiêu thụ**.

Khi cần hai phép tính độc lập trên cùng dữ liệu có thể duyệt lại, hãy tạo hai Stream mới từ nguồn:

```java
List<Integer> numbers = Arrays.asList(10, 20, 30);

long count = numbers.stream().count();
int total = numbers.stream().mapToInt(Integer::intValue).sum();
```

Khi nguồn gắn với tài nguyên, việc kết thúc terminal operation **không đồng nghĩa Stream tự đóng tài nguyên**. Ví dụ, `Files.lines` mở tài nguyên liên quan đến tệp, cần đóng bằng `try-with-resources`:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static long countNonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .filter(line -> !line.trim().isEmpty())
            .count();
    }
}
```

Khối `try` đảm bảo gọi `close()` kể cả khi xử lý ném ngoại lệ. Với nguồn trong bộ nhớ như `List.stream()`, thông thường không có tài nguyên ngoài cần đóng.

> **Ngoại lệ về thời điểm duyệt:** `iterator()` và `spliterator()` được phân loại là terminal operation vì chúng kết thúc khả năng ghép thêm bước pipeline, nhưng chúng trả về một đối tượng để duyệt; phần tử có thể chỉ thực sự được kéo qua các bước trung gian khi đối tượng đó được sử dụng. Vì vậy, phát biểu chính xác là terminal operation **kích hoạt hoặc thiết lập việc tiêu thụ**, không phải mọi terminal đều duyệt hết dữ liệu ngay trong lời gọi.

## 7. Khi chuyển sang parallel stream, không dựa vào lịch chạy

Tính lười vẫn tồn tại khi gọi `parallel()`; việc ghép pipeline chưa tự thực thi trên nhiều luồng. Tuy nhiên, lúc terminal operation tiêu thụ dữ liệu, các phần tử có thể được xử lý đồng thời, không bảo đảm các thông báo từ `peek` hoặc thao tác bên trong `map` xuất hiện theo thứ tự nguồn.

```java
List<Integer> result = IntStream.rangeClosed(1, 8)
    .parallel()
    .map(n -> n * 2)
    .boxed()
    .collect(Collectors.toList());

// Với nguồn có encounter order, kết quả vẫn theo thứ tự: [2, 4, ..., 16].
// Không suy ra các lời gọi map đã diễn ra theo thứ tự 1, 2, ..., 8.
```

`findFirst` bảo toàn khái niệm “đầu tiên” trên nguồn có encounter order, còn `findAny` được phép trả về phần tử bất kỳ. `forEach` trên Stream song song không đảm bảo thứ tự; `forEachOrdered` bảo đảm encounter order khi thứ tự tồn tại, nhưng có thể giảm lợi ích song song. Các bước có trạng thái và ràng buộc thứ tự (chẳng hạn `sorted`, `distinct`, `limit` trên nguồn có thứ tự) cũng có thể làm chi phí đồng bộ/bộ đệm tăng lên.

Vì vậy, hãy ưu tiên lambda **không có trạng thái chia sẻ và không phụ thuộc vào thứ tự thực thi**. Đừng đếm số lần chạy lambda hoặc ghi dữ liệu chia sẻ không đồng bộ để suy ra số phần tử đã xử lý.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Gọi `filter` nghĩa là danh sách đã được lọc.” | `filter` thường chỉ thêm một bước vào pipeline; terminal mới yêu cầu dữ liệu. |
| “`map` chạy hết rồi `filter` mới chạy.” | Với các bước không trạng thái trong pipeline tuần tự, xử lý thường được kết hợp theo từng phần tử và theo thứ tự khai báo. |
| “Terminal luôn duyệt hết nguồn.” | Terminal như `findFirst` và `anyMatch` có thể dừng sớm; trung gian `limit` cũng có thể giảm số phần tử cần lấy. |
| “`sorted` vẫn lấy được kết quả đầu tiên ngay.” | Sắp xếp thông thường phải quan sát toàn bộ đầu vào hữu hạn trước khi phát phần tử đầu tiên. |
| “Đã gọi `count` thì `peek` chắc chắn in ra.” | `count` có thể dùng kích thước đã biết và bỏ qua bước trung gian không ảnh hưởng số lượng. |
| “Có thể gọi `count` rồi `collect` trên cùng Stream.” | Stream đã tiêu thụ không được tái sử dụng; tạo Stream mới từ nguồn có thể duyệt lại. |
| “Terminal tự đóng file Stream.” | Phải đóng các Stream gắn với tài nguyên bằng `close` hoặc `try-with-resources`. |

## 9. Tự kiểm tra

**Tình huống A.** Đoạn mã sau in ra gì, và dòng `"map"` xuất hiện vào lúc nào?

```java
Stream<Integer> s = Stream.of(1, 2, 3)
    .map(n -> {
        System.out.println("map " + n);
        return n * 10;
    });
System.out.println("ready");
int value = s.findFirst().orElse(-1);
System.out.println(value);
```

**Đáp án:** Với Stream tuần tự và có thứ tự, in `ready`, `map 1`, `10`. Trước `findFirst()`, bước `map` chưa xử lý phần tử nào. `findFirst()` chỉ cần phần tử đầu tiên, nên không cần ánh xạ `2` và `3`.

**Tình huống B.** Muốn lấy ba số nhỏ nhất từ một danh sách hữu hạn, nên đặt `limit(3)` trước hay sau `sorted()`?

**Đáp án:** Đặt `sorted().limit(3)` để xét toàn bộ đầu vào rồi chọn ba số nhỏ nhất. `limit(3).sorted()` chỉ sắp xếp ba phần tử đầu của nguồn, có thể cho kết quả khác.

**Tình huống C.** Vì sao đoạn `Stream.generate(supplier).limit(5).collect(Collectors.toList())` có thể kết thúc dù nguồn không có điểm dừng tự nhiên?

**Đáp án:** `limit(5)` chỉ cho tối đa năm phần tử đi tiếp; khi terminal đã lấy đủ năm phần tử, pipeline không cần gọi `supplier` thêm. Nếu đặt một bước phải tiêu thụ toàn bộ nguồn, chẳng hạn `sorted()`, **trước** `limit(5)` thì khả năng kết thúc này mất đi.

## Ghi nhớ

Tính lười giúp Java Stream API **khai báo trước cách xử lý, chỉ thực hiện phần cần thiết khi có nhu cầu tiêu thụ**. Để suy luận một pipeline, hãy tự hỏi theo thứ tự: nguồn được tạo khi nào; bước trung gian nào có thể cần trạng thái; terminal cần bao nhiêu dữ liệu; có dừng sớm hoặc tối ưu hóa bỏ qua bước nào không; Stream đã được tiêu thụ hoặc cần đóng tài nguyên chưa. Trả lời được các câu hỏi ấy là nền tảng để dùng `filter`, `map`, `reduce` và `collect` đúng hợp đồng vòng đời của Stream.
