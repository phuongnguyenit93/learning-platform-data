# Phép toán kết thúc ngắn mạch và khả năng dừng pipeline

Trong Java Stream API, một pipeline thường gồm **nguồn dữ liệu → các phép toán trung gian → một phép toán kết thúc**. Các phép toán trung gian như `filter` và `map` được thực thi *lazy*: chúng mô tả cách xử lý, còn việc duyệt dữ liệu chỉ bắt đầu khi có phép toán kết thúc. Một số phép toán kết thúc có thể trả lời đúng mà **không cần xét hết phần tử đầu vào**. Đó là *phép toán kết thúc ngắn mạch* (*short-circuiting terminal operation*).

Đây là phần quan trọng của **hợp đồng và vòng đời pipeline**: cần phân biệt việc đã có đủ kết quả để dừng xử lý với việc tài nguyên đã được đóng, và phân biệt *có thể* dừng sớm với *chắc chắn* chỉ xử lý một số lượng phần tử cố định.

## 1. Kết thúc thông thường và kết thúc ngắn mạch

Mọi terminal operation đều **kết thúc việc sử dụng stream đó**: sau khi gọi `collect`, `reduce`, `forEach`, `count` hay `findFirst`, không được tái sử dụng cùng đối tượng `Stream` cho pipeline thứ hai. Tuy nhiên, không phải terminal operation nào cũng có khả năng ngắn mạch.

| Loại | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Trung gian lazy | `filter`, `map`, `peek` | Chưa tạo ra kết quả cuối cùng; thường xử lý khi downstream yêu cầu phần tử. |
| Trung gian có khả năng ngắn mạch | `limit`, `takeWhile` | Có thể giới hạn số phần tử downstream cần nhận. |
| Kết thúc ngắn mạch | `anyMatch`, `allMatch`, `noneMatch`, `findFirst`, `findAny` | Có thể trả kết quả khi mới xem một phần nguồn. |
| Kết thúc thường | `collect`, `reduce`, `forEach`, `toArray` | Thường cần xử lý toàn bộ đầu vào còn lại để cho kết quả đúng. |

Ví dụ, với danh sách số nguyên có thứ tự:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = List.of(3, 5, 8, 10, 12);

boolean hasEven = numbers.stream()
    .filter(n -> n > 4)
    .anyMatch(n -> n % 2 == 0);

System.out.println(hasEven); // true, vì tìm thấy 8
```

Về mặt logic, kết quả `true` đã được xác định khi gặp `8`; không cần kiểm tra `10` hay `12`. Trong pipeline tuần tự, trường hợp đơn giản này có thể dừng tại `8`. Đừng dựa vào số lần gọi `filter` hoặc `map` để tạo hiệu ứng phụ: đặc tả Stream cho phép tối ưu và bỏ qua những lời gọi không cần để tính kết quả; trong thực thi song song, một số phần tử khác có thể đã được xử lý đồng thời.

## 2. Năm phép toán kết thúc ngắn mạch

| Phép toán | Câu hỏi cần trả lời | Khi nào đủ thông tin để dừng? | Kết quả với stream rỗng |
| --- | --- | --- | --- |
| `anyMatch(p)` | Có **ít nhất một** phần tử thỏa `p`? | Tìm thấy phần tử thỏa `p`. | `false` |
| `allMatch(p)` | **Mọi** phần tử đều thỏa `p`? | Tìm thấy phần tử **không** thỏa `p`. | `true` |
| `noneMatch(p)` | Có phải **không phần tử nào** thỏa `p`? | Tìm thấy phần tử thỏa `p`. | `true` |
| `findFirst()` | Phần tử đầu tiên theo *encounter order* là gì? | Xác định được phần tử đầu tiên. | `Optional.empty()` |
| `findAny()` | Có thể lấy một phần tử bất kỳ không? | Xác định được một phần tử bất kỳ. | `Optional.empty()` |

Ba phép toán `*Match` trả về `boolean` và nhận một `Predicate<T>`. Hai phép toán `find*` trả về `Optional<T>`, vì stream có thể rỗng. Với `allMatch` và `noneMatch`, kết quả `true` trên stream rỗng là đúng theo định nghĩa logic: không có phần tử nào làm sai điều kiện.

```java
import java.util.List;

List<Integer> scores = List.of(72, 85, 91);

boolean hasExcellent = scores.stream().anyMatch(s -> s >= 90); // true
boolean allPassed    = scores.stream().allMatch(s -> s >= 50); // true
boolean noNegative   = scores.stream().noneMatch(s -> s < 0); // true

boolean anyEmpty  = List.<Integer>of().stream().anyMatch(s -> s > 0);  // false
boolean allEmpty  = List.<Integer>of().stream().allMatch(s -> s > 0);  // true
boolean noneEmpty = List.<Integer>of().stream().noneMatch(s -> s > 0); // true
```

**Chọn đúng phép toán theo yêu cầu nghiệp vụ:** để kiểm tra “có đơn hàng trễ hạn hay không”, dùng `anyMatch`; để xác nhận “tất cả giao dịch hợp lệ”, dùng `allMatch`; để xác nhận “không có mã trùng điều kiện cấm”, dùng `noneMatch`. Chúng trả kết quả trực tiếp và thể hiện rõ ý định hơn việc gom toàn bộ phần tử vào danh sách rồi mới kiểm tra.

### `findFirst()` so với `findAny()`

```java
import java.util.List;
import java.util.Optional;

List<String> names = List.of("An", "Binh", "Chi", "Dung");

Optional<String> firstLongName = names.stream()
    .filter(name -> name.length() >= 4)
    .findFirst();

System.out.println(firstLongName.orElse("Không có")); // Binh

Optional<String> anyLongName = names.parallelStream()
    .filter(name -> name.length() >= 4)
    .findAny();
// Có thể là Binh hoặc Dung; không được giả định kết quả ổn định.
```

`findFirst` tôn trọng **thứ tự gặp phần tử** (*encounter order*) nếu nguồn/pipeline có thứ tự, như `List.stream()`. Nếu stream không có thứ tự, `findFirst` không bảo đảm trả về phần tử mà ta gọi là “đầu tiên” theo một thứ tự bên ngoài. `findAny` cố ý cho phép chọn bất kỳ phần tử nào, phù hợp khi chỉ cần tìm *một* kết quả, nhất là trong pipeline song song. Không dùng `findAny` nếu nghiệp vụ yêu cầu phần tử sớm nhất.

Không gọi `.get()` trực tiếp trên `Optional` khi chưa kiểm tra giá trị. Có thể dùng `orElse`, `orElseGet`, `ifPresent`, hoặc `orElseThrow`. Ngoài ra, `findFirst` và `findAny` không hỗ trợ việc chọn phần tử `null` làm kết quả: nếu phần tử được chọn là `null`, chúng ném `NullPointerException`.

## 3. Phép toán trung gian cũng ảnh hưởng khả năng dừng

Khả năng ngắn mạch của terminal operation chịu ảnh hưởng của **những phép toán nằm trước nó**. Hai phép toán trung gian cần nhận diện là:

- `limit(n)` giữ tối đa `n` phần tử. Đây là phép toán trung gian có khả năng ngắn mạch; khi đã nhận đủ `n` phần tử theo yêu cầu, downstream không cần thêm phần tử.
- `takeWhile(p)` (Java 9+) lấy **tiền tố liên tiếp** các phần tử thỏa `p` đối với stream có thứ tự, và dừng lấy khi gặp phần tử đầu tiên không thỏa `p`.

```java
import java.util.List;

List<Integer> values = List.of(2, 4, 7, 8, 10);

System.out.println(values.stream().filter(n -> n % 2 == 0).toList());
// [2, 4, 8, 10] — xét điều kiện trên mọi phần tử cần thiết

System.out.println(values.stream().takeWhile(n -> n % 2 == 0).toList());
// [2, 4] — dừng lấy tiền tố khi gặp 7; không lấy 8 và 10

System.out.println(values.stream().limit(3).toList());
// [2, 4, 7]
```

`filter(p)` **không đồng nghĩa** với `takeWhile(p)`: `filter` có thể giữ cả phần tử thỏa điều kiện xuất hiện *sau* một phần tử không thỏa, còn `takeWhile` chỉ giữ tiền tố. Với stream không có encounter order, `takeWhile` được phép lấy một tập con phù hợp của các phần tử thỏa điều kiện; không thể dựa vào một “tiền tố” xác định.

Hai phép toán dễ bị nhầm với ngắn mạch:

- `dropWhile(p)` (Java 9+) bỏ tiền tố liên tiếp thỏa `p`, rồi **tiếp tục** đưa các phần tử phía sau xuống downstream; vì vậy bản thân nó không kết thúc sớm toàn bộ quá trình duyệt.
- `skip(n)` bỏ qua `n` phần tử ban đầu nhưng không giới hạn số phần tử còn phải duyệt sau đó.

> Các ví dụ dùng `List.of()` và `takeWhile()` cần Java 9 trở lên; `Stream.toList()` cần Java 16 trở lên. Trên Java 8, có thể dùng `Arrays.asList(...)` và `collect(Collectors.toList())`, nhưng `takeWhile`/`dropWhile` chưa có trong API chuẩn.

## 4. Stream vô hạn: có ngắn mạch chưa chắc sẽ kết thúc

Stream có thể có nguồn *không giới hạn* như `Stream.iterate` hoặc `Stream.generate`. Khả năng kết thúc phụ thuộc vào việc pipeline có gặp điều kiện dừng hay không và những bước trước nó có cần đọc toàn bộ nguồn hay không.

```java
import java.util.stream.Stream;

boolean found = Stream.iterate(1, n -> n + 1)
    .anyMatch(n -> n == 100);
System.out.println(found); // true; gặp 100 thì đủ kết luận

long firstFiveCount = Stream.generate(() -> "event")
    .limit(5)
    .count();
System.out.println(firstFiveCount); // 5
```

Ngược lại, hai pipeline sau **không có cách trả kết quả cuối cùng** khi nguồn tiếp tục cung cấp phần tử mãi mãi:

```java
// KHÔNG CHẠY: mọi phần tử luôn bằng 1 nên allMatch không gặp phản ví dụ.
// Stream.generate(() -> 1).allMatch(n -> n == 1);

// KHÔNG CHẠY: không có phần tử nào lớn hơn 1 nên findFirst không có kết quả.
// Stream.generate(() -> 1).filter(n -> n > 1).findFirst();
```

`allMatch` là short-circuiting terminal operation vì **có thể** dừng nếu gặp phản ví dụ, nhưng không tự tạo ra điều kiện dừng khi tất cả phần tử đều hợp lệ. Tương tự, `anyMatch` sẽ không trả `false` trên một nguồn vô hạn chỉ sinh phần tử không khớp.

Khi phải xử lý nguồn mở hoặc không biết độ dài, hãy thiết kế một ranh giới rõ ràng: `limit`, `takeWhile` (khi đúng ngữ nghĩa), hoặc nguồn hữu hạn như `Stream.iterate(seed, hasNext, next)` (Java 9+). Ví dụ:

```java
long count = Stream.iterate(1, n -> n <= 100, n -> n + 1)
    .filter(n -> n % 10 == 0)
    .count();

System.out.println(count); // 10
```

## 5. Vì sao có `findFirst()` mà vẫn phải duyệt gần hết nguồn?

Short-circuiting **không hứa** độ phức tạp O(1). Chi phí phụ thuộc vị trí phần tử thỏa điều kiện và các phép toán trung gian. Chẳng hạn:

```java
import java.util.List;

List<Integer> data = List.of(9, 2, 5, 1);

System.out.println(data.stream().sorted().limit(2).toList());
// [1, 2] — phải xét toàn bộ nguồn để biết hai số nhỏ nhất

System.out.println(data.stream().limit(2).sorted().toList());
// [2, 9] — chỉ sắp xếp hai phần tử đầu; ý nghĩa kết quả khác
```

`sorted()` cần biết tập phần tử cần sắp xếp trước khi có thể bảo đảm giá trị đầu tiên của kết quả đã sắp thứ tự. Vì vậy, `stream.sorted().findFirst()` trên nguồn hữu hạn thường phải thu thập toàn bộ nguồn trước khi trả phần tử nhỏ nhất. Trên nguồn vô hạn, `sorted()` có thể khiến pipeline không bao giờ tạo được phần tử đầu tiên.

`distinct()` cũng là phép toán có trạng thái: nó cần ghi nhận các giá trị đã gặp. Khi kết hợp `distinct().limit(n)`, pipeline phải đọc đến khi tìm đủ `n` phần tử **khác nhau**; nếu chỉ có ít hơn `n` giá trị khác nhau trong một nguồn vô hạn, quá trình có thể không kết thúc. `filter(p).findFirst()` có thể phải duyệt rất nhiều phần tử trước khi gặp kết quả đầu tiên, hoặc duyệt hết nguồn hữu hạn nếu không có kết quả.

Do đó, hãy tự hỏi: **phép toán nào ở trước điểm ngắn mạch có thể buộc pipeline duyệt thêm phần tử?** Chuyển `limit` lên trước `sorted` hay `distinct` đôi khi cải thiện chi phí nhưng làm thay đổi ý nghĩa; chỉ đổi thứ tự khi yêu cầu nghiệp vụ cho phép.

## 6. Encounter order, song song và giới hạn của việc “dừng ngay”

Trong pipeline tuần tự trên một nguồn có thứ tự, việc tìm được điều kiện quyết định thường chấm dứt yêu cầu lấy thêm phần tử. Nhưng **không được coi đây là bảo đảm rằng mọi lambda chỉ chạy đúng đến phần tử ấy**, đặc biệt khi gọi `parallel()`:

- Nhiều nhánh song song có thể đang xử lý phần tử khác tại thời điểm một nhánh tìm thấy kết quả. Việc hủy phần việc còn lại là phối hợp nội bộ, không phải thao tác ngắt tức thời mọi tác vụ.
- `findFirst()` phải tôn trọng encounter order (nếu có), nên có thể đắt hơn `findAny()` trong trường hợp song song. `findAny()` có thể trả phần tử khác nhau giữa các lần chạy.
- `limit(n)` và `takeWhile(p)` trên stream **có thứ tự** phải giữ đúng ngữ nghĩa vị trí, khiến thực thi song song đôi khi tốn chi phí phối hợp.
- `unordered()` chỉ phù hợp khi thứ tự không có ý nghĩa nghiệp vụ. Nó có thể mở thêm cơ hội tối ưu, nhưng cũng làm thay đổi giá trị có thể được `limit`, `takeWhile` hoặc `findFirst` chọn.

Ví dụ, nếu yêu cầu là “lấy bất kỳ đơn hàng lỗi nào để điều tra”, `parallelStream().filter(...).findAny()` có thể phù hợp. Nếu yêu cầu là “lấy đơn hàng lỗi **sớm nhất theo thời gian**”, cần có thứ tự được xác định rõ (ví dụ dữ liệu đã sắp theo thời gian) và dùng `findFirst()`; không thể thay bằng `findAny()` chỉ để mong nhanh hơn.

Không dùng `peek`, `map` hoặc `filter` cho những hiệu ứng phụ bắt buộc phải thực hiện với **mọi** phần tử (như ghi sổ, gửi thông báo, cập nhật bộ đếm). Ngắn mạch và tối ưu hóa có thể khiến nhiều phần tử không được xử lý; song song còn làm thứ tự và thời điểm hiệu ứng phụ khó dự đoán. Predicate và mapper nên ưu tiên thuần hàm, không sửa trạng thái dùng chung.

## 7. Dừng duyệt không đồng nghĩa đóng stream hoặc tài nguyên

Một phép toán kết thúc ngắn mạch giải quyết câu hỏi về **kết quả**, không bảo đảm đóng tài nguyên bên ngoài. `Stream` từ collection thường không cần đóng; stream gắn với I/O như `Files.lines(Path)` phải được quản lý vòng đời bằng `try-with-resources`.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public static boolean containsError(Path logFile) throws IOException {
    try (Stream<String> lines = Files.lines(logFile, StandardCharsets.UTF_8)) {
        return lines.anyMatch(line -> line.contains("ERROR"));
    } // Đóng stream (và tài nguyên đọc tệp) kể cả khi anyMatch dừng sớm.
}
```

Sau `anyMatch`, `findFirst` hay bất kỳ terminal operation nào, stream **đã được tiêu thụ** và không thể dùng lại. Nhưng gọi terminal operation không tự động gọi `close()`; `onClose(...)` chỉ chạy khi stream thực sự được đóng. Nếu predicate/mapper ném ngoại lệ, phép toán kết thúc không cung cấp kết quả thành công, và `try-with-resources` vẫn giúp đóng tài nguyên.

```java
import java.util.stream.Stream;

Stream<Integer> stream = Stream.of(1, 2, 3);
boolean hasTwo = stream.anyMatch(n -> n == 2);
// stream.count(); // IllegalStateException: stream đã được vận hành/đóng
```

“Dừng pipeline” còn không có nghĩa “hủy tác vụ bên ngoài” mà lambda đã gọi. Nếu công việc trong predicate có I/O, chờ khóa hoặc tác động ra hệ thống khác, Stream API không cung cấp cơ chế timeout/hủy mạnh cho những thao tác đó; cần thiết kế cơ chế riêng phù hợp với yêu cầu.

## 8. Cách chọn và kiểm tra khả năng dừng

Khi thiết kế pipeline, có thể kiểm tra theo trình tự sau:

1. **Xác định câu hỏi cuối cùng**: tồn tại (`anyMatch`), tất cả (`allMatch`), không tồn tại (`noneMatch`), phần tử đầu tiên (`findFirst`) hay bất kỳ phần tử (`findAny`)? Nếu cần đầy đủ kết quả, dùng terminal operation tương ứng như `collect`.
2. **Xác định thứ tự có quan trọng không**: với yêu cầu “đầu tiên”, phải biết encounter order của nguồn và các bước xử lý; nếu không quan trọng, cân nhắc `findAny`.
3. **Đánh giá nguồn có hữu hạn không**: nếu là nguồn vô hạn, phải có khả năng thực sự gặp điều kiện dừng hoặc giới hạn số phần tử. “Operation hỗ trợ ngắn mạch” chưa đủ để bảo đảm kết thúc.
4. **Rà soát các bước đứng trước terminal**: `sorted`, `distinct`, `filter`, `skip`, `flatMap` hoặc yêu cầu duy trì thứ tự có thể làm tăng lượng công việc; đặc biệt tránh phép toán cần toàn bộ đầu vào trước khi giới hạn nguồn vô hạn.
5. **Quản lý tài nguyên và hiệu ứng phụ**: dùng `try-with-resources` cho stream từ I/O, không dựa vào việc lambda chạy cho mọi phần tử, và không tái sử dụng stream sau terminal operation.

**Ví dụ tổng hợp:** cần biết trong 10.000 bản ghi đầu tiên có bản ghi vi phạm quy tắc hay không:

```java
boolean violationInFirst10000 = records.stream()
    .limit(10_000)
    .anyMatch(record -> violatesRule(record));
```

`limit` định nghĩa phạm vi cần xem; `anyMatch` có thể dừng sớm hơn khi tìm thấy vi phạm. Nếu thay bằng `records.stream().anyMatch(...)`, phạm vi tìm kiếm sẽ là toàn bộ nguồn. Nếu thêm `sorted()` **trước** `limit`, tập “10.000 bản ghi đầu tiên” có thể đổi nghĩa, đồng thời tăng lượng công việc.

Điểm cốt lõi: **ngắn mạch là khả năng trả lời sớm khi đã đủ thông tin**, còn việc kết thúc trên dữ liệu thực phụ thuộc điều kiện dừng, thứ tự, phép toán trung gian và cách thực thi. Hãy chọn phép toán theo ngữ nghĩa trước, rồi đánh giá lợi ích hiệu năng trên dữ liệu và môi trường thực tế.
