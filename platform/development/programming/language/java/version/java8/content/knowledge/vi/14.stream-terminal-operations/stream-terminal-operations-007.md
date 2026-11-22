# Short-circuit và nguồn hữu hạn, vô hạn trong Java Stream (Java 8)

## 1. Hiểu đúng bài toán: khi nào một Stream kết thúc?

Một pipeline Stream gồm **nguồn dữ liệu → các thao tác trung gian → thao tác kết thúc (terminal operation)**. Các thao tác trung gian như `filter`, `map`, `limit` được thiết lập theo cơ chế *lazy*: chúng chưa duyệt dữ liệu khi ta chỉ khai báo pipeline. Việc tiêu thụ dữ liệu bắt đầu khi gọi thao tác kết thúc, chẳng hạn `count`, `collect`, `findFirst` hoặc `anyMatch`.

Có ba ý khác nhau cần phân biệt:

- **Nguồn hữu hạn (finite source):** có một số lượng phần tử hữu hạn; nếu pipeline xử lý bình thường và không bị chặn, thao tác cần duyệt hết dữ liệu có thể hoàn thành.
- **Nguồn vô hạn (infinite/unbounded source):** có thể tiếp tục sinh phần tử không giới hạn; muốn có kết quả trong thời gian hữu hạn, pipeline phải có cách dừng phù hợp.
- **Short-circuit:** thao tác có thể trả kết quả mà không cần tiêu thụ hết toàn bộ nguồn. Đây là tính chất của thao tác, **không phải cam kết rằng mọi pipeline chứa thao tác đó đều kết thúc**.

Trong ngữ cảnh “Kết thúc Stream”, *terminal operation* chỉ có nghĩa là thao tác kích hoạt và hoàn tất một lần sử dụng pipeline. Nó **không đồng nghĩa** với “chắc chắn dừng trên nguồn vô hạn”, cũng không đồng nghĩa với `close()` để giải phóng tài nguyên I/O.

## 2. Nhận diện nguồn hữu hạn và vô hạn

| Nguồn trong Java 8 | Loại nguồn | Ý nghĩa |
| --- | --- | --- |
| `List.stream()`, `Set.stream()`, `Arrays.stream(array)`, `Stream.of(...)` | Hữu hạn | Đọc từ tập phần tử có giới hạn; không nên sửa nguồn trong lúc duyệt. |
| `IntStream.range(1, 6)` | Hữu hạn | Sinh 1, 2, 3, 4, 5; cận trên không bao gồm. |
| `IntStream.rangeClosed(1, 5)` | Hữu hạn | Sinh 1, 2, 3, 4, 5; cận trên có bao gồm. |
| `Files.lines(path, charset)` | Thông thường hữu hạn | Duyệt các dòng của một tệp; phải đóng stream vì nguồn gắn với tài nguyên I/O. |
| `Stream.iterate(seed, next)` | Vô hạn theo hợp đồng Java 8 | Sinh `seed`, `next(seed)`, …; nguồn **có thứ tự (ordered)**. |
| `Stream.generate(supplier)` | Vô hạn theo hợp đồng Java 8 | Gọi supplier để sinh tiếp phần tử; nguồn **không có encounter order được bảo đảm (unordered)**. |
| `new Random().ints()` | Vô hạn | Sinh luồng giá trị `int`; phải đặt giới hạn hoặc dùng điều kiện dừng thích hợp nếu cần kết quả hữu hạn. |

**Lưu ý:** “Vô hạn” mô tả khả năng cung cấp phần tử liên tục, không có nghĩa Java cấp phát trước một danh sách vô hạn trong bộ nhớ. Stream xử lý lười và chỉ yêu cầu phần tử khi pipeline cần. Ngược lại, việc gọi `collect` để gom toàn bộ nguồn vô hạn có thể chạy mãi và tăng bộ nhớ không giới hạn.

Hai nguồn thường dùng để học cơ chế:

~~~java
Stream<Integer> ordered = Stream.iterate(1, n -> n + 1);
Stream<Integer> unordered = Stream.generate(() -> 1);
~~~

Đây là **đoạn khai báo minh họa**, chưa có terminal operation nên chưa yêu cầu duyệt nguồn. Trong Java 8, `Stream.iterate` dùng hàm chuyển phần tử và `Stream.generate` dùng `Supplier`; không có điểm dừng nội tại trong hai overload này.

## 3. Hai nhóm thao tác short-circuit

### 3.1. Short-circuit trung gian

- `limit(n)`: chỉ cho phép **tối đa n phần tử đi qua**; đây là thao tác trung gian *stateful* có tính short-circuit. Với `n = 0`, kết quả rỗng; `n < 0` gây `IllegalArgumentException`.
- `limit` chỉ có tác dụng khi **một terminal operation thật sự tiêu thụ pipeline**. Đặt `limit` không tự chạy chương trình hay tự trả kết quả.
- Với nguồn vô hạn và các thao tác phía trước có thể tạo đủ `n` phần tử trong thời gian hữu hạn, `limit(n)` làm phần còn lại của pipeline có số phần tử hữu hạn.

Ví dụ ý tưởng: `iterate(1, n -> n + 1).filter(n -> n % 2 == 0).limit(3)` đưa ba giá trị `2, 4, 6` sang downstream, rồi dừng yêu cầu thêm phần tử từ nguồn khi terminal operation lấy đủ ba giá trị.

### 3.2. Short-circuit kết thúc

| Terminal operation | Có thể dừng ngay khi… | Kiểu kết quả |
| --- | --- | --- |
| `findFirst()` | Tìm được phần tử đầu tiên theo encounter order, nếu stream có thứ tự | `Optional<T>`, hoặc biến thể `OptionalInt`/`OptionalLong`/`OptionalDouble` |
| `findAny()` | Tìm được một phần tử bất kỳ | `Optional<T>` hoặc biến thể primitive |
| `anyMatch(predicate)` | Có **ít nhất một** phần tử thỏa điều kiện | `boolean` |
| `allMatch(predicate)` | Có **ít nhất một** phần tử **không** thỏa điều kiện | `boolean` |
| `noneMatch(predicate)` | Có **ít nhất một** phần tử thỏa điều kiện | `boolean` |

Các thao tác trên **có khả năng** kết thúc sớm. Chúng vẫn có thể phải duyệt hết nguồn hữu hạn, hoặc không kết thúc trên nguồn vô hạn, nếu điều kiện đủ để trả lời không xuất hiện.

Các thao tác như `filter`, `map` và `skip` **không phải** short-circuit chỉ vì chúng xử lý từng phần tử. Các terminal operation như `count`, `collect`, `forEach`, `reduce` thông thường cần tiêu thụ toàn bộ các phần tử còn lại của pipeline; chúng không tự tạo điểm dừng cho nguồn vô hạn.

## 4. Cơ chế dừng thực tế và logic của ba phép match

Với pipeline **sequential**, có thể hình dung terminal operation lần lượt yêu cầu phần tử; mỗi phần tử đi qua các bước trung gian, và terminal quyết định có cần yêu cầu thêm hay không. Đây là mô hình để hiểu luồng xử lý, **không nên dùng số lần gọi lambda hoặc tác dụng phụ để suy diễn kết quả** trên mọi cách thực thi, đặc biệt khi chuyển sang parallel.

Giả sử stream lần lượt phát `1, 2, 3, 4, …`:

- `filter(n -> n % 4 == 0).limit(3).collect(toList())`: lấy `4`, `8`, `12` rồi kết thúc; nguồn gốc vẫn vô hạn nhưng downstream đã bị giới hạn.
- `filter(n -> n % 7 == 0).findFirst()`: trả `Optional[7]` sau khi tìm thấy giá trị đầu tiên thỏa điều kiện.
- `anyMatch(n -> n == 5)`: trả `true` khi gặp `5`.
- `allMatch(n -> n < 5)`: trả `false` khi gặp `5`.
- `noneMatch(n -> n == 5)`: trả `false` khi gặp `5`.

Bảng logic tổng quát:

| Phép kiểm tra | Điều kiện đủ để trả sớm | Nếu duyệt **hết nguồn hữu hạn** mà không gặp điều kiện đó | Trên nguồn vô hạn |
| --- | --- | --- | --- |
| `anyMatch(p)` | Gặp phần tử có `p = true` → `true` | `false` | Có thể không dừng nếu không bao giờ có `p = true` |
| `allMatch(p)` | Gặp phần tử có `p = false` → `false` | `true` | Có thể không dừng nếu mọi phần tử đều thỏa `p` |
| `noneMatch(p)` | Gặp phần tử có `p = true` → `false` | `true` | Có thể không dừng nếu không phần tử nào thỏa `p` |

**Trường hợp stream rỗng:** `anyMatch` trả `false`, `allMatch` trả `true`, `noneMatch` trả `true`. Hai kết quả `true` sau là đúng theo logic “mọi phần tử đều thỏa” và “không phần tử nào thỏa” khi không có phần tử nào để phản ví dụ.

`findFirst()` và `findAny()` trả `Optional.empty()` khi stream hữu hạn không có phần tử (hoặc pipeline tạo ra stream rỗng). Với stream có encounter order, `findFirst` phải tôn trọng phần tử đầu tiên theo thứ tự đó; `findAny` không hứa chọn phần tử nào, nhất là khi chạy parallel. Nguồn `Stream.generate` trong Java 8 là unordered, nên không nên gán ý nghĩa nghiệp vụ cho chữ “first” nếu không tạo ra thứ tự xác định.

## 5. Ví dụ hoàn chỉnh: chạy được với Java 8 API

Tạo tệp **StreamTerminationDemo.java**:

~~~java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamTerminationDemo {
    public static void main(String[] args) {
        long finiteCount = Stream.of("A", "B", "C").count();
        System.out.println("finiteCount = " + finiteCount);

        List<Integer> firstFourEvens = Stream.iterate(1, n -> n + 1)
                .filter(n -> n % 2 == 0)
                .limit(4)
                .collect(Collectors.toList());
        System.out.println("firstFourEvens = " + firstFourEvens);

        int firstMultipleOfSeven = Stream.iterate(1, n -> n + 1)
                .filter(n -> n % 7 == 0)
                .findFirst()
                .orElse(-1);
        System.out.println("firstMultipleOfSeven = " + firstMultipleOfSeven);

        boolean any = IntStream.rangeClosed(1, 10).anyMatch(n -> n > 8);
        boolean all = IntStream.rangeClosed(1, 10).allMatch(n -> n < 4);
        boolean none = IntStream.rangeClosed(1, 10).noneMatch(n -> n < 0);
        System.out.println("anyMatch = " + any);
        System.out.println("allMatch = " + all);
        System.out.println("noneMatch = " + none);

        System.out.println("emptyAny = "
                + Stream.<Integer>empty().anyMatch(n -> n > 0));
        System.out.println("emptyAll = "
                + Stream.<Integer>empty().allMatch(n -> n > 0));
        System.out.println("emptyNone = "
                + Stream.<Integer>empty().noneMatch(n -> n > 0));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ (mã chỉ dùng các API có từ Java 8):

~~~bash
javac StreamTerminationDemo.java
java StreamTerminationDemo
~~~

Kết quả chính xác:

~~~text
finiteCount = 3
firstFourEvens = [2, 4, 6, 8]
firstMultipleOfSeven = 7
anyMatch = true
allMatch = false
noneMatch = true
emptyAny = false
emptyAll = true
emptyNone = true
~~~

Giải thích: `count` hoàn thành vì nguồn ban đầu có ba phần tử. Hai pipeline dùng `iterate` đều bắt đầu từ nguồn vô hạn, nhưng một pipeline được chặn bằng `limit(4)`, pipeline còn lại dừng khi `findFirst` gặp bội số đầu tiên của 7. Ba pipeline `rangeClosed` hữu hạn cho phép trả kết quả boolean chắc chắn; các phép trên stream rỗng minh họa logic đặc biệt ở mục 4.

## 6. Khi có short-circuit mà vẫn không kết thúc

**Có thao tác short-circuit là điều kiện cần, nhưng chưa đủ, để một pipeline trên nguồn vô hạn kết thúc.** Phải xét cả dữ liệu được sinh ra, thứ tự các thao tác và khả năng mỗi thao tác tạo phần tử tiếp theo.

### 6.1. Không bao giờ tìm thấy phần tử phù hợp

Các đoạn dưới đây **chỉ để phân tích, không chạy thử nguyên trạng**:

~~~java
// Nguồn chỉ sinh ra số 1; filter không bao giờ tạo đầu ra.
Stream.generate(() -> 1)
        .filter(n -> n == 2)
        .limit(1)
        .count();

// Không bao giờ tìm thấy điều kiện đúng.
Stream.generate(() -> 1)
        .anyMatch(n -> n == 2);

// Không bao giờ gặp phản ví dụ.
Stream.generate(() -> 1)
        .allMatch(n -> n == 1);

// Không bao giờ có phần tử để phủ định noneMatch.
Stream.generate(() -> 1)
        .noneMatch(n -> n == 2);
~~~

Cả bốn pipeline đều không có điều kiện hoàn tất sau số hữu hạn bước theo dữ liệu đã cho. `limit(1)` ở ví dụ đầu **chỉ đếm phần tử qua được filter**; nó không giới hạn số phần tử nguồn cần kiểm tra.

Ngược lại, trên cùng nguồn chỉ sinh `1`, `anyMatch(n -> n == 1)` có thể trả `true` và `allMatch(n -> n == 2)` có thể trả `false` ngay khi kiểm tra được phần tử đầu.

### 6.2. Đặt `limit` sau thao tác cần toàn bộ nguồn

`sorted()` là thao tác trung gian *stateful*. Để sắp xếp đúng toàn bộ dữ liệu, nó phải biết các phần tử trong phạm vi cần sắp xếp. Hãy so sánh hai đoạn **minh họa bên trong một phương thức có các import cần thiết**:

~~~java
// Hữu hạn trước khi sorted: kết thúc, kết quả [5, 4, 3, 2, 1].
Stream.iterate(1, n -> n + 1)
        .limit(5)
        .sorted(java.util.Comparator.reverseOrder())
        .collect(Collectors.toList());

// Không chạy: sorted phải chờ hết nguồn vô hạn trước limit.
Stream.iterate(1, n -> n + 1)
        .sorted()
        .limit(5)
        .collect(Collectors.toList());
~~~

Di chuyển `limit` lên trước `sorted` **thay đổi ý nghĩa bài toán**: ta đang sắp xếp *năm phần tử đầu*, không tìm “năm phần tử nhỏ nhất trong mọi phần tử của nguồn vô hạn”.

Tương tự, `distinct()` cần nhớ giá trị đã thấy và có thể gặp khó khăn về bộ nhớ hoặc không tạo đủ số giá trị khác nhau. Ví dụ `Stream.generate(() -> 1).distinct().limit(2).count()` không thể tìm được giá trị phân biệt thứ hai nên không hoàn thành.

### 6.3. Parallel, thứ tự và tác dụng phụ

- Với `parallel()`, số phần tử thực tế được xử lý có thể lớn hơn ngưỡng tối thiểu trước khi pipeline hoàn tất. Không dùng bộ đếm phụ, log trong `peek` hay thao tác cập nhật biến ngoài để phụ thuộc vào “chính xác bao nhiêu lambda đã chạy”.
- `findFirst` giữ ý nghĩa encounter order khi nguồn có thứ tự, có thể tốn thêm chi phí trên parallel. `findAny` cho phép chọn bất kỳ phần tử phù hợp nào và thường thích hợp hơn khi thứ tự không cần thiết.
- `limit(n)` với pipeline parallel **có thứ tự** có thể tốn chi phí hơn vì phải giữ đúng `n` phần tử đầu theo thứ tự. Chỉ bỏ ràng buộc thứ tự bằng `unordered()` khi yêu cầu nghiệp vụ cho phép.
- Các lambda trong stream nên **stateless**, **non-interfering**: không sửa collection nguồn, không dùng tác dụng phụ để quyết định tính đúng đắn; cùng một stream chỉ nên dùng cho một terminal operation.

## 7. Cách thiết kế pipeline để có khả năng hoàn thành

1. **Xác định nguồn**: số phần tử đã biết hay có thể sinh liên tục? `range`, array và collection là nguồn hữu hạn; `iterate`/`generate` mặc định vô hạn trong Java 8.
2. **Xác định mục đích**: cần toàn bộ kết quả (`collect`, `count`, `reduce`), một kết quả (`findFirst`/`findAny`), hay một kết luận điều kiện (`anyMatch`/`allMatch`/`noneMatch`)?
3. **Chứng minh điểm dừng**: nếu dùng `limit(k)` sau `filter`, có chắc sẽ tồn tại ít nhất `k` phần tử thỏa điều kiện trong thời gian hữu hạn không? Nếu dùng match, có chắc sẽ xuất hiện điều kiện chứng minh được câu trả lời không?
4. **Kiểm tra thứ tự thao tác**: mọi phép phải gom/xem toàn bộ dữ liệu như `sorted` có đứng **trước** bước giới hạn không? Có bước nào chỉ sinh hữu hạn kết quả trong khi phải đọc vô hạn input không?
5. **Kiểm tra tài nguyên**: có đang gom vô hạn phần tử vào bộ nhớ không? Nguồn I/O đã có cơ chế đóng đúng lúc kể cả khi terminal trả sớm chưa?
6. **Chọn sequential khi cần truy vết hoặc thứ tự ổn định**; dùng parallel khi công việc thật sự có lợi và không phụ thuộc vào thứ tự kiểm tra/phần tử được chọn.

### Với nguồn tệp: short-circuit vẫn phải đóng tài nguyên

`Files.lines` tạo stream gắn với tài nguyên I/O. Dù `anyMatch` có thể dừng khi gặp dòng phù hợp, nguồn vẫn phải được đóng bằng `try-with-resources`:

~~~java
// Đoạn minh họa: yêu cầu tệp data.txt có thật, không có stdout cố định.
try (java.util.stream.Stream<String> lines = java.nio.file.Files.lines(
        java.nio.file.Paths.get("data.txt"),
        java.nio.charset.StandardCharsets.UTF_8)) {
    boolean containsError = lines.anyMatch(line -> line.contains("ERROR"));
    System.out.println(containsError);
}
~~~

Kết thúc traversal, kết quả terminal, và gọi `close()` là ba khái niệm liên quan nhưng khác nhau. Stream tạo từ collection thông thường không cần đóng; stream từ nguồn I/O thường cần đóng.

## 8. Bài tập tự kiểm tra và đáp án

**Câu 1.** `Stream.iterate(1, n -> n + 1).filter(n -> n % 3 == 0).limit(4).count()` trả bao nhiêu?

**Đáp án:** `4`. Các phần tử đưa qua `limit` là `3, 6, 9, 12`; sau đó `count` duyệt bốn phần tử hữu hạn.

**Câu 2.** `Stream.generate(() -> 1).noneMatch(n -> n == 1)` có kết thúc không?

**Đáp án:** Có. Nó trả `false` sau khi gặp phần tử `1`; một phần tử thỏa điều kiện đã đủ phủ định “không phần tử nào thỏa”.

**Câu 3.** `Stream.generate(() -> 1).noneMatch(n -> n == 2)` có kết thúc không?

**Đáp án:** Không, theo nguồn đã mô tả. Không có phần tử nào thỏa điều kiện, và nguồn không bao giờ cạn để phép kiểm tra có thể khẳng định `true`.

**Câu 4.** `Stream.iterate(1, n -> n + 1).sorted().findFirst()` có bảo đảm hoàn thành không?

**Đáp án:** Không. `sorted` nằm trước terminal operation và cần duyệt hết nguồn vô hạn. `findFirst` phía sau không cứu được pipeline.

**Câu 5.** Vì sao đổi `findFirst` sang `findAny` có thể làm kết quả khác khi chạy parallel?

**Đáp án:** `findFirst` tôn trọng encounter order nếu có; `findAny` có thể trả bất kỳ phần tử nào, nên kết quả có thể thay đổi giữa các lần chạy hoặc cách chia tác vụ.

## 9. Ghi nhớ

- **Hữu hạn/vô hạn là thuộc tính của nguồn hoặc số phần tử còn lại sau biến đổi**; “terminal” là vị trí kết thúc pipeline API, không phải bảo đảm kết thúc về thời gian.
- **`limit` là short-circuit trung gian**; **`findFirst`, `findAny`, `anyMatch`, `allMatch`, `noneMatch` là short-circuit terminal** trong Java 8.
- **Nguồn vô hạn chỉ kết thúc khi có điều kiện dừng thực sự đạt được**; `filter` không tạo được giá trị phù hợp, `sorted` đặt sai vị trí hoặc `distinct` không tìm đủ giá trị đều có thể làm chương trình không hoàn thành.
- **Không phụ thuộc side effect hoặc số lần đánh giá chính xác**, nhất là khi parallel; đóng stream I/O đúng cách dù kết quả được trả sớm.

### Tài liệu chính thức (Java 8 API, các nguyên tắc vẫn áp dụng)

- [Oracle Java SE 8 — java.util.stream package](https://docs.oracle.com/javase/8/docs/api/java/util/stream/package-summary.html)
- [Oracle Java SE 8 — Stream API](https://docs.oracle.com/javase/8/docs/api/java/util/stream/Stream.html)
