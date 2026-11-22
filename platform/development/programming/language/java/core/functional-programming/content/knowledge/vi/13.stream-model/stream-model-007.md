# Thứ tự gặp phần tử và thứ tự thực thi thao tác trong Java Stream

Khi dùng `Stream`, đặc biệt với `parallelStream()`, cần phân biệt **thứ tự gặp phần tử** (*encounter order*) với **thứ tự thực thi thao tác** (*execution order*). Hai khái niệm này liên quan nhưng không đồng nhất: một pipeline có thể xử lý nhiều phần tử song song, không theo thứ tự ban đầu, mà vẫn tạo ra **kết quả có thứ tự**.

Bài này tập trung vào mô hình Stream trong Java 17+: thứ tự đến từ đâu, thao tác nào bảo toàn hoặc thay đổi thứ tự, hành vi của terminal operation và cách tránh phụ thuộc vào lịch chạy của các luồng.

## 1. Hai loại thứ tự cần phân biệt

**Thứ tự gặp phần tử (encounter order)** là thứ tự logic mà nguồn stream hoặc các bước trung gian xác định cho những phần tử khi đi qua pipeline. Ví dụ, với `List.of("A", "B", "C")`, encounter order là `A → B → C`, kể cả khi xử lý bằng parallel stream.

**Thứ tự thực thi thao tác (execution order)** là thời điểm và thứ tự thực tế mà các hàm như `map`, `filter`, `peek` hoặc `Consumer` được gọi khi pipeline thực thi. Với parallel stream, các hàm xử lý phần tử có thể chạy trên những luồng khác nhau và theo thứ tự không cố định.

```text
Encounter order của List:   A --------> B --------> C --------> D

Một lịch xử lý song song:    C thực hiện
                              A thực hiện
                              D thực hiện
                              B thực hiện

Kết quả toList() có thứ tự: [A, B, C, D]  (nếu pipeline còn ordered)
```

Sơ đồ giữa chỉ là **một lịch thực thi có thể xảy ra**, không phải lịch Java cam kết. `Stream` có thể tính toán và kết hợp kết quả sao cho tuân thủ encounter order mà không bắt từng callback thực hiện lần lượt theo thứ tự đó.

Cần phân biệt thêm:

- **Ordered stream**: stream có encounter order xác định.
- **Unordered stream**: stream không bị ràng buộc bởi một encounter order; kết quả có thể xuất hiện theo nhiều thứ tự tùy nguồn, thao tác và cách thực thi.
- **Sequential stream**: các bước thực thi theo chế độ tuần tự.
- **Parallel stream**: việc thực thi có thể phân chia sang nhiều luồng.

`ordered/unordered` nói về **ngữ nghĩa thứ tự**; `sequential/parallel` nói về **chế độ thực thi**. Vì vậy `parallel` không đồng nghĩa với `unordered`, và `unordered` không tự động bật xử lý song song.

## 2. Nguồn nào tạo encounter order?

| Nguồn hoặc thao tác | Encounter order |
| --- | --- |
| `List.stream()`, `List.parallelStream()` | Có; theo thứ tự phần tử của list |
| `Arrays.stream(array)` | Có; theo thứ tự chỉ số trong mảng |
| `LinkedHashSet.stream()` | Có; theo thứ tự duyệt do `LinkedHashSet` định nghĩa |
| `HashSet.stream()` | Không được bảo đảm có encounter order |
| `Stream.of(a, b, c)` | Có; theo thứ tự các đối số |
| `stream.sorted()` | Áp đặt thứ tự sắp xếp cho stream đi tiếp |
| `stream.unordered()` | Bỏ ràng buộc encounter order, nếu có |

Đừng suy ra thứ tự cố định từ những dữ liệu nhìn thấy khi chạy thử `HashSet` hoặc `Set.of(...)`: cách triển khai có thể cho một thứ tự duyệt tại thời điểm quan sát nhưng không có hợp đồng bảo đảm thứ tự đó.

Ví dụ:

```java
List<String> names = List.of("Bình", "An", "Chi");
List<String> result = names.parallelStream()
        .map(String::toUpperCase)
        .toList();
// result có encounter order: [BÌNH, AN, CHI]
```

Đây là đoạn minh họa bên trong một phương thức Java, với `import java.util.List;`. Do `List` có thứ tự và `map` không đổi encounter order, `Stream.toList()` đưa các phần tử vào list theo đúng thứ tự gặp, dù callback `toUpperCase` có thể chạy song song.

## 3. Một ví dụ Java 17+ có đầu ra xác định

Lưu thành `StreamOrderDemo.java`:

```java
import java.util.List;

public class StreamOrderDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(4, 1, 3, 2);

        System.out.println("source = " + numbers);

        List<Integer> mapped = numbers.parallelStream()
                .map(n -> n * 10)
                .toList();
        System.out.println("mapped = " + mapped);

        List<Integer> sorted = numbers.parallelStream()
                .sorted()
                .toList();
        System.out.println("sorted = " + sorted);

        int first = numbers.parallelStream()
                .findFirst()
                .orElseThrow();
        System.out.println("first = " + first);

        numbers.parallelStream()
                .forEachOrdered(n -> System.out.println("ordered = " + n));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac StreamOrderDemo.java
java StreamOrderDemo
```

**Stdout chính xác:**

```text
source = [4, 1, 3, 2]
mapped = [40, 10, 30, 20]
sorted = [1, 2, 3, 4]
first = 4
ordered = 4
ordered = 1
ordered = 3
ordered = 2
```

Giải thích:

1. `numbers` là một `List` với encounter order `4, 1, 3, 2`.
2. `map(n -> n * 10)` có thể chạy với những phần tử theo lịch song song bất kỳ, nhưng `toList()` giữ thứ tự gặp nên kết quả là `[40, 10, 30, 20]`.
3. `sorted()` xác định **thứ tự mới** là `1, 2, 3, 4`; kết quả sau đó được thu thập theo thứ tự này.
4. `findFirst()` lấy phần tử đầu theo encounter order, tức `4`, không phụ thuộc phần tử nào được worker xử lý sớm nhất.
5. `forEachOrdered()` thực hiện hành động in theo encounter order, nên bốn dòng `ordered = ...` luôn có thứ tự như trên.

Quan trọng: đầu ra có thứ tự **không chứng minh** việc tính toán đã chạy tuần tự.

## 4. `forEach()` khác `forEachOrdered()` như thế nào?

Hai terminal operation cùng nhận `Consumer<T>` và không trả về danh sách kết quả, nhưng có hợp đồng thứ tự khác nhau:

| Terminal operation | Ordered stream tuần tự | Ordered parallel stream |
| --- | --- | --- |
| `forEach(action)` | Với thực thi tuần tự thông thường, các action theo thứ tự duyệt | **Không bảo đảm** action chạy theo encounter order |
| `forEachOrdered(action)` | Action theo encounter order | **Bảo đảm** action được thực hiện theo encounter order |
| `toList()` | Thu thập theo encounter order | Vẫn thu thập theo encounter order nếu stream có thứ tự |

Ví dụ sau không có stdout cố định:

```java
List<Integer> numbers = List.of(1, 2, 3, 4);
numbers.parallelStream().forEach(System.out::println);
```

Đây là đoạn minh họa bên trong phương thức và cần `import java.util.List;`. Một lần chạy có thể in `3, 4, 2, 1`; lần khác có thể in `1, 2, 3, 4`. **Không được dựa vào bất kỳ thứ tự nào**. Kể cả khi tình cờ in đúng thứ tự nhiều lần, đó vẫn không phải điều được `forEach` trên parallel stream bảo đảm.

Muốn buộc hành động quan sát được theo encounter order:

```java
numbers.parallelStream().forEachOrdered(System.out::println);
```

Lệnh này sẽ in `1`, `2`, `3`, `4` theo thứ tự, mỗi số một dòng. Với `forEachOrdered`, hành động đối với một phần tử *happens-before* hành động với phần tử tiếp theo trong encounter order, dù các action có thể được thực hiện bởi các luồng khác nhau. Nó **không cam kết** mọi bước trung gian như `map` hay `filter` cũng được gọi tuần tự hoặc theo thứ tự ấy.

Không nhầm `Iterable.forEach` của collection với `Stream.forEach`: `Iterable.forEach` duyệt theo thứ tự iteration nếu iterable có định nghĩa; còn `Stream.forEach` khi thực thi song song không bảo đảm encounter order.

### Vì sao không dùng `forEachOrdered` ở mọi nơi?

Bảo đảm thứ tự khiến các action phải được phối hợp. Nếu mỗi action in console, ghi mạng hoặc chờ tài nguyên, chi phí đồng bộ có thể làm giảm lợi ích song song. Nếu cần **kết quả được sắp theo encounter order** mà không cần tác dụng phụ tại mỗi phần tử, `map(...).toList()` thường diễn đạt mục đích rõ ràng hơn `forEachOrdered` rồi tự ghép một danh sách chia sẻ.

## 5. Intermediate operation có thể làm gì với thứ tự?

Một số intermediate operation **bảo toàn** encounter order của nguồn có thứ tự, một số **tạo** hoặc **nới lỏng** ràng buộc:

| Operation | Với nguồn có encounter order | Ý nghĩa thực tế |
| --- | --- | --- |
| `map(f)` | Giữ thứ tự vị trí logic | Phần tử thứ nhất biến thành kết quả thứ nhất |
| `filter(p)` | Giữ thứ tự tương đối của phần tử được chọn | Không đảo trật tự các phần tử còn lại |
| `flatMap(f)` | Phù hợp thứ tự nguồn và thứ tự của các substream có thứ tự | Có thể xuất nhiều phần tử cho một phần tử đầu vào |
| `distinct()` | Với ordered stream, giữ lần xuất hiện đầu của mỗi giá trị theo `equals` | Ràng buộc ổn định có thể tốn chi phí khi chạy song song |
| `sorted()` | Tạo thứ tự sắp xếp mới | Thường cần phối hợp/buffer trước khi trả kết quả |
| `limit(n)` | Lấy **n phần tử đầu** theo encounter order | Có thể tốn chi phí trên ordered parallel stream |
| `skip(n)` | Bỏ **n phần tử đầu** theo encounter order | Có thể cần phối hợp để biết phần tử nào thuộc prefix |
| `unordered()` | Gỡ ràng buộc encounter order | Có thể mở cơ hội tối ưu nhưng không mang nghĩa “trộn ngẫu nhiên” |

Ví dụ `filter` và `limit`:

```java
List<Integer> values = List.of(7, 2, 4, 9, 6);
List<Integer> result = values.parallelStream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();
// result: [2, 4]
```

Đây là đoạn minh họa bên trong một phương thức, cần `import java.util.List;`. Mặc dù tìm được `6` trước trong lịch xử lý song song là điều có thể xảy ra, `limit(2)` của **ordered stream** vẫn chọn hai số chẵn đầu tiên theo encounter order là `2` và `4`.

### `unordered()` có nghĩa gì?

`unordered()` cho biết các bước sau có thể bỏ qua yêu cầu giữ encounter order. Nó **không** nhất thiết đổi thứ tự vật lý của dữ liệu, cũng không đảm bảo kết quả sẽ được xáo trộn.

```java
List<Integer> picked = List.of(1, 2, 3, 4, 5, 6)
        .parallelStream()
        .unordered()
        .limit(2)
        .toList();
```

Đoạn minh họa này có thể nhận hai phần tử bất kỳ từ tập đầu vào; **không có kết quả cụ thể nào phải cố định**. Bỏ ràng buộc thứ tự thường hữu ích khi chỉ quan tâm đến số lượng hoặc tập giá trị, chẳng hạn xử lý tìm vài phần tử bất kỳ.

Nếu bài toán cần “hai phần tử đầu tiên theo thứ tự nhập”, **không gọi `unordered()`** trước `limit(2)`.

## 6. `findFirst()` và `findAny()`: ưu tiên ngữ nghĩa nào?

- `findFirst()`: lấy phần tử đầu theo encounter order, **nếu stream có encounter order**. Với nguồn unordered, không có một phần tử “đầu” được định nghĩa sẵn.
- `findAny()`: có thể chọn một phần tử bất kỳ, ngay cả khi nguồn có encounter order. Điều này có thể cho phép trả kết quả sớm hơn khi thực thi song song.

```java
List<String> values = List.of("red", "green", "blue");

String first = values.parallelStream()
        .findFirst()
        .orElseThrow(); // Chắc chắn là "red"

String any = values.parallelStream()
        .findAny()
        .orElseThrow(); // Không thể cam kết một giá trị cụ thể
```

Đây là đoạn minh họa bên trong một phương thức, cần `import java.util.List;`. `findAny` **có thể** trả `"red"`, nhưng không nhất thiết. Cả hai đều trả về `Optional` trước khi gọi `orElseThrow()`; với stream rỗng, `orElseThrow()` sẽ ném `NoSuchElementException`.

Để kiểm tra “có tồn tại phần tử thỏa điều kiện không”, thường dùng `anyMatch(predicate)` thay vì `filter(predicate).findFirst()`. `anyMatch` biểu diễn câu hỏi boolean và không đặt ra yêu cầu chọn phần tử đầu tiên.

## 7. Thứ tự callback không phải nguồn sự thật của dữ liệu

Một lỗi phổ biến là dùng tác dụng phụ trong `map` để suy ra thứ tự xử lý hoặc tạo kết quả:

```java
List<Integer> seen = new java.util.ArrayList<>();

List<Integer> result = List.of(1, 2, 3, 4)
        .parallelStream()
        .map(n -> {
            seen.add(n);  // Sai: sửa ArrayList chung từ nhiều luồng.
            return n * 10;
        })
        .toList();
```

Đây là đoạn mã **minh họa lỗi**, không phải mẫu để chạy trong ứng dụng. `ArrayList` không được đồng bộ hóa cho ghi đồng thời; `seen` có thể chứa dữ liệu không mong đợi hoặc bị hỏng trạng thái. Kể cả nếu thay `seen` bằng collection thread-safe, thứ tự thêm vào `seen` vẫn phản ánh lịch chạy, không nhất thiết bằng encounter order.

Cách đúng khi cần danh sách kết quả theo thứ tự:

```java
List<Integer> result = List.of(1, 2, 3, 4)
        .parallelStream()
        .map(n -> n * 10)
        .toList();
// [10, 20, 30, 40]
```

Đây là đoạn minh họa với `import java.util.List;`. `map` trả về giá trị mới; `toList()` đảm nhận phần kết hợp kết quả theo thứ tự logic.

Ngoài thứ tự, **các tác dụng phụ trong intermediate operation không nên dùng để bảo đảm hành vi nghiệp vụ**. Stream cho phép tối ưu hóa khiến callback ở một số bước có thể không được gọi nếu kết quả terminal vẫn đúng. Chẳng hạn với nguồn `SIZED` và `count()`, Java có thể tính số phần tử trực tiếp mà không duyệt qua `peek`. Mã sau không được dùng để yêu cầu in ra ba dòng:

```java
long count = List.of(1, 2, 3)
        .stream()
        .peek(System.out::println)
        .count();
// count == 3, nhưng có thể không in ra số nào.
```

Đây là đoạn minh họa bên trong một phương thức, cần `import java.util.List;`. `peek` chủ yếu phục vụ quan sát/debug, không thích hợp để thực hiện logic bắt buộc như ghi database, gửi email, thay đổi counter.

**Khuyến nghị:** lambda trong `map`, `filter`, `reduce` nên *non-interfering* (không sửa nguồn stream đang được xử lý) và *stateless* (không phụ thuộc trạng thái thay đổi trong lúc chạy). Điều này giúp pipeline đúng với cả tuần tự lẫn song song.

## 8. Kết quả có thứ tự khác với thời điểm xảy ra tác dụng phụ

Xét một pipeline có `parallelStream().map(this::fetch).toList()`. Nếu `fetch` gọi HTTP, các request có thể được gửi/hoàn tất không theo encounter order, dù list kết quả được xếp đúng thứ tự đầu vào. Vì vậy:

- Thứ tự **kết quả** không đồng nghĩa với thứ tự **gửi request**, **ghi log** hay **ghi bản ghi vào DB**.
- Nếu side effect bắt buộc theo thứ tự, đặt hành động ở ranh giới có kiểm soát (chẳng hạn duyệt tuần tự sau khi tính kết quả); dùng `forEachOrdered` khi mục tiêu đúng là gọi hành động theo encounter order.
- Nếu không đòi hỏi thứ tự, hãy mô tả rõ ràng bất biến cần giữ (tập dữ liệu, số lượng, quan hệ giữa các phần tử), đừng vô tình ràng buộc hệ thống vào lịch thread.
- Khi xảy ra exception trong parallel pipeline, một số phần tử khác có thể đã được xử lý hoặc gây tác dụng phụ. Stream không cung cấp rollback/transaction cho những tác dụng phụ ấy.

Phần lớn thao tác thu thập như `toList()` hoặc `collect(Collectors.toList())` trên **ordered stream** có thể duy trì encounter order. Nhưng `collect(Collectors.toSet())` không hứa hẹn thứ tự iteration của set kết quả; muốn giao diện có thứ tự, hãy chọn kiểu kết quả và collector thích hợp, không chỉ quan sát thứ tự khi chạy thử.

## 9. Khi nào thứ tự ảnh hưởng hiệu năng?

Thứ tự là một phần hợp đồng của phép toán. Trong các parallel pipeline, yêu cầu giữ encounter order có thể khiến hệ thống phải phối hợp công việc giữa các luồng, buffer hoặc chờ phần tử đứng trước. Những thao tác dễ thấy gồm `limit`, `skip`, `distinct`, `findFirst` và `forEachOrdered`.

Ví dụ một tác vụ chỉ cần **bất kỳ hai phần tử hợp lệ nào**, không cần “hai phần tử đầu”, có thể xem xét `unordered().filter(...).limit(2)`. Nhưng chỉ nên nới lỏng thứ tự sau khi xác nhận kết quả nghiệp vụ chấp nhận mọi cách chọn hợp lệ.

Đừng mặc định `parallelStream()` nhanh hơn `stream()`. Với dữ liệu nhỏ, callback nhẹ, I/O chậm, tranh chấp tài nguyên hoặc xử lý cần giữ thứ tự chặt chẽ, overhead chia việc và phối hợp có thể lớn hơn lợi ích. Hãy đo bằng workload thật nếu cần tối ưu.

## 10. Bảng lựa chọn nhanh

| Mục tiêu | Cách viết phù hợp | Bảo đảm quan trọng |
| --- | --- | --- |
| Biến đổi list nhưng giữ thứ tự gốc | `list.parallelStream().map(f).toList()` | Kết quả theo encounter order của list |
| In từng phần tử theo thứ tự list | `list.parallelStream().forEachOrdered(System.out::println)` | Action thực hiện theo encounter order |
| Thực hiện action mà thứ tự không quan trọng | `list.parallelStream().forEach(action)` | Không dựa vào thứ tự thực thi |
| Lấy phần tử đầu tiên theo thứ tự nguồn | `stream.findFirst()` | Đầu theo encounter order nếu được định nghĩa |
| Lấy phần tử bất kỳ | `stream.findAny()` | Không bảo đảm phần tử đầu |
| Lấy n phần tử đầu | `orderedStream.limit(n)` | Prefix theo encounter order |
| Lấy n phần tử bất kỳ khi thứ tự không cần thiết | `stream.unordered().limit(n)` | Không hứa hẹn prefix đầu |
| Sắp xếp trước khi thu thập | `stream.sorted().toList()` | Thứ tự kết quả theo phép so sánh |
| Quan sát lịch thực thi để debug | Ghi log có đánh dấu luồng, không dùng làm kết quả nghiệp vụ | Log có thể đến không theo encounter order |

## 11. Những lỗi thường gặp cần tránh

1. **“Parallel nghĩa là mất thứ tự”**: sai. Stream có thể xử lý song song và vẫn giữ thứ tự kết quả.
2. **“Output ordered nên từng callback cũng chạy ordered”**: sai. `toList()` có thể phục hồi thứ tự logic sau các callback chạy đồng thời.
3. **“forEachOrdered làm tất cả phép map chạy tuần tự”**: sai. Nó ràng buộc thứ tự action ở terminal, không bắt upstream xử lý lần lượt.
4. **“HashSet có thứ tự vì in ra lần nào cũng giống nhau”**: không có hợp đồng bảo đảm encounter order.
5. **“unordered() là shuffle()”**: sai. Nó chỉ bỏ yêu cầu encounter order, không hứa hẹn đảo hay trộn phần tử.
6. **“findAny() và findFirst() luôn trả như nhau”**: sai, nhất là khi chạy song song.
7. **“peek() luôn chạy một lần cho mỗi phần tử”**: không được bảo đảm trong mọi pipeline và tối ưu hóa.
8. **“Ghi vào List dùng chung trong map song song là an toàn”**: sai; có nguy cơ race và kết quả không theo thứ tự.
9. **“Có thể dùng lại một stream đã chạy terminal”**: stream là pipeline sử dụng một lần; muốn xử lý lại phải tạo stream mới từ nguồn.

## Ghi nhớ

- **Encounter order** là thứ tự logic của dữ liệu; **execution order** là lịch thật sự các thao tác chạy.
- **Parallel không làm mất encounter order một cách tự động**.
- `forEach` trên parallel stream không bảo đảm thứ tự action; `forEachOrdered` bảo đảm thứ tự action theo encounter order nếu có.
- `toList`, `findFirst` và `limit` tôn trọng encounter order khi nó tồn tại; `unordered()` cho phép từ bỏ ràng buộc ấy.
- Đừng xây dựng logic dựa vào thời điểm callback hoặc tác dụng phụ trong intermediate operation. Hãy mô tả kết quả bằng các phép biến đổi stateless, non-interfering và chọn terminal operation theo đúng bảo đảm mà bài toán cần.
