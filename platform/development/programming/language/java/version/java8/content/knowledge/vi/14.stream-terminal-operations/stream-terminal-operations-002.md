# forEachOrdered và bảo toàn encounter order trong Java Stream

## 1. Bài toán và vị trí trong Stream

`forEachOrdered(Consumer<? super T> action)` là **terminal operation** của `Stream<T>` (cũng có ở `IntStream`, `LongStream`, `DoubleStream`): nó thực hiện một hành động cho từng phần tử rồi kết thúc pipeline, trả về `void`. Điểm khác biệt quan trọng với `forEach` là: **nếu stream có encounter order, các lời gọi action của `forEachOrdered` diễn ra theo đúng encounter order đó, kể cả khi pipeline chạy song song**.

Ví dụ một danh sách lưu các bước `[load, validate, save]`. Ta có thể tính toán các bước trung gian song song, nhưng nếu cần in kết quả cuối theo `load → validate → save` thì `forEachOrdered` phù hợp. Ngược lại, nếu thứ tự không quan trọng, `forEach` thường cho phép thực thi song song linh hoạt hơn.

Cần phân biệt ba khái niệm:

- **Encounter order:** thứ tự phần tử *được định nghĩa bởi nguồn và các phép biến đổi của stream*, không phải thứ tự CPU bắt đầu hoặc hoàn tất xử lý.
- **Processing order:** thứ tự các thao tác trung gian như `map`, `filter` được thực thi; trong parallel stream, các thao tác này có thể chạy khác thứ tự encounter order.
- **Action order:** thứ tự chạy `Consumer` ở terminal operation; `forEachOrdered` ràng buộc thứ tự này theo encounter order nếu encounter order tồn tại.

## 2. Khi nào stream có encounter order?

Thứ tự phụ thuộc vào **nguồn** và **intermediate operations**:

| Nguồn hoặc phép xử lý | Encounter order |
| --- | --- |
| `List.stream()`, `List.parallelStream()`, `Arrays.stream(array)`, `Stream.of(...)` | Có; theo thứ tự các phần tử trong nguồn. |
| `LinkedHashSet.stream()` | Có; theo thứ tự duyệt của `LinkedHashSet` (thường là thứ tự thêm vào). |
| `TreeSet.stream()` | Có; theo thứ tự sắp xếp của tập hợp. |
| `HashSet.stream()` | Không có bảo đảm về encounter order; đừng suy ra thứ tự từ lần chạy cụ thể. |
| `filter(...)`, `map(...)` trên một ordered stream | Giữ encounter order của các phần tử còn lại / kết quả tương ứng. |
| `sorted()` | Thiết lập thứ tự sắp xếp cho kết quả, kể cả khi nguồn ban đầu unordered. |
| `unordered()` | Bỏ ràng buộc encounter order; **không có nghĩa là đảo ngẫu nhiên** dữ liệu. |

`parallel()` **không tự loại bỏ encounter order**. Chẳng hạn, `list.parallelStream()` vẫn là một ordered stream; `forEach` có thể phớt lờ thứ tự khi thực hiện action, còn `forEachOrdered` vẫn phải tôn trọng.

Với `limit(n)` trên ordered stream, ý nghĩa là chọn **n phần tử đầu theo encounter order**; nếu chủ động chuyển sang unordered stream, không thể đòi hỏi chúng là n phần tử đầu của danh sách gốc. Đừng gọi `unordered()` khi kết quả phải giữ thứ tự nghiệp vụ.

## 3. Hợp đồng của forEachOrdered so với forEach

| Khía cạnh | `forEach(action)` | `forEachOrdered(action)` |
| --- | --- | --- |
| Loại thao tác | Terminal, trả `void` | Terminal, trả `void` |
| Parallel + ordered stream | Không bảo đảm thứ tự gọi action | Bảo đảm action theo encounter order |
| Unordered stream | Không có thứ tự để bảo toàn | Cũng không thể tạo ra thứ tự |
| Thread chạy action | Có thể thuộc các thread khác nhau | Cũng có thể thuộc các thread khác nhau |
| Quan hệ giữa các action liên tiếp | Không có bảo đảm thứ tự tương ứng | Action của phần tử trước **happens-before** action của phần tử sau |
| Tính linh hoạt khi thực thi song song | Thường cao hơn | Có thể tốn đồng bộ, lưu đệm hoặc làm giảm lợi ích parallel |

**Happens-before** ở đây là quan hệ thứ tự/hiển thị bộ nhớ giữa các lần thực hiện action liên tiếp của chính `forEachOrdered`; **không có nghĩa** toàn bộ `map`, `filter` hay các công việc ngoài pipeline chạy trên cùng một thread hoặc theo thứ tự đó. Mỗi action có thể được Java thực hiện bằng một thread khác, nhưng các action của `forEachOrdered` được xử lý lần lượt.

Ở stream tuần tự lấy từ một `List`, `forEach` thường cho ta thứ tự đang duyệt. Tuy nhiên, nếu mã phải **đảm bảo thứ tự action**, đặc biệt khi chuyển thành parallel sau này, hãy thể hiện ý định bằng `forEachOrdered` hoặc dùng phép gom kết quả có bảo toàn thứ tự.

## 4. Ví dụ 1 — kết quả có thứ tự ngay cả khi parallel

Lưu chương trình dưới tên **ForEachOrderedDemo.java**:

```java
import java.util.Arrays;
import java.util.List;

public class ForEachOrderedDemo {
    public static void main(String[] args) {
        List<String> steps = Arrays.asList("A", "B", "C", "D");

        System.out.print("sequential: ");
        steps.stream().forEachOrdered(System.out::print);
        System.out.println();

        System.out.print("parallel: ");
        steps.parallelStream()
             .filter(step -> !step.equals("B"))
             .forEachOrdered(System.out::print);
        System.out.println();
    }
}
```

Chạy bằng JDK hiện đại (chương trình cũng dùng được với Java 8):

```bash
javac ForEachOrderedDemo.java
java ForEachOrderedDemo
```

Đầu ra xác định:

```text
sequential: ABCD
parallel: ACD
```

Giải thích:

1. Danh sách `steps` có encounter order `A, B, C, D`.
2. `filter` loại `B` nhưng giữ thứ tự tương đối của các phần tử còn lại: `A, C, D`.
3. `parallelStream()` có thể xử lý các phần tử trên nhiều thread; `forEachOrdered` vẫn gọi `System.out.print` lần lượt theo `A, C, D`.
4. Nếu thay `forEachOrdered` bằng `forEach` ở nhánh parallel, chuỗi ký tự in ra **không có thứ tự được bảo đảm**. Một lần chạy trùng `ACD` không chứng minh `forEach` bảo toàn encounter order.

Khi muốn nhìn thấy khác biệt mà không dựa vào một kết quả ngẫu nhiên cụ thể:

```java
// Đoạn minh họa: thứ tự dòng in ra có thể khác nhau mỗi lần chạy.
java.util.stream.IntStream.rangeClosed(1, 8)
    .parallel()
    .forEach(i -> System.out.print(i + " "));
```

Đây chỉ là đoạn minh họa, không phải chương trình Java độc lập. Mọi số từ 1 đến 8 đều được xử lý, nhưng **không có stdout cố định để khẳng định thứ tự**. Đổi sang `forEachOrdered` sẽ in `1 2 3 4 5 6 7 8 ` theo thứ tự (có dấu cách cuối do biểu thức in).

## 5. Ví dụ 2 — forEachOrdered không tự sắp xếp HashSet

Giả sử dữ liệu bắt đầu từ `HashSet`. Thứ tự duyệt của `HashSet` không phải cam kết của API, vì vậy:

```java
// Chỉ là đoạn minh họa: kết quả không có thứ tự xác định.
java.util.Set<String> codes =
    new java.util.HashSet<>(java.util.Arrays.asList("C", "A", "B"));
codes.parallelStream().forEachOrdered(System.out::print);
```

Mặc dù dùng `forEachOrdered`, đoạn này **không được phép kỳ vọng** `ABC`, `CAB` hay một thứ tự cụ thể. Nếu nghiệp vụ yêu cầu thứ tự chữ cái, hãy **tạo thứ tự trước khi dùng terminal operation**.

Lưu **EncounterOrderDemo.java**:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class EncounterOrderDemo {
    public static void main(String[] args) {
        Set<String> codes =
            new HashSet<>(Arrays.asList("C", "A", "B"));

        System.out.print("sorted: ");
        codes.parallelStream()
             .sorted()
             .forEachOrdered(System.out::print);
        System.out.println();
    }
}
```

```bash
javac EncounterOrderDemo.java
java EncounterOrderDemo
```

Đầu ra xác định:

```text
sorted: ABC
```

`sorted()` xác lập thứ tự `A, B, C`; `forEachOrdered` bảo toàn thứ tự đó ở đầu ra. Nếu cần thứ tự khác chữ cái mặc định, dùng `sorted(Comparator)` với quy tắc so sánh phù hợp. Cần nhớ thứ tự các phần tử so sánh bằng nhau có thể cần xem xét riêng nếu nguồn là unordered.

## 6. Chọn forEachOrdered, forEach hay collect?

Chọn theo **kết quả nghiệp vụ** chứ không chỉ theo việc có gọi `parallel()`:

- Dùng **`forEachOrdered`** khi action thật sự cần tác dụng phụ theo đúng thứ tự phần tử: hiển thị thông báo tuần tự, xuất các bản ghi theo một trình tự đã xác định, hoặc gọi một API ngoại vi mà thứ tự lời gọi là yêu cầu.
- Dùng **`forEach`** khi action độc lập với thứ tự, ví dụ cập nhật một bộ đếm thread-safe hoặc tác động đến các phần tử độc lập, và không cần đầu ra có thứ tự. Với parallel stream, vẫn phải tự bảo đảm thread safety cho trạng thái dùng chung.
- Dùng **`collect(...)`** khi mục tiêu là **tạo giá trị hoặc bộ sưu tập kết quả**. Đừng dùng `forEachOrdered` chỉ để lắp ghép chuỗi/đẩy phần tử vào danh sách bên ngoài pipeline.
- Nếu **cả các bước tính toán trung gian** cũng phải chạy tuần tự vì có ràng buộc phụ thuộc, cân nhắc `stream()` hoặc `sequential()`; `forEachOrdered` chỉ bảo đảm thứ tự action terminal.

Ví dụ gom chuỗi theo đúng encounter order mà không cần thay đổi trạng thái bên ngoài. Lưu **CollectInsteadOfPrint.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class CollectInsteadOfPrint {
    public static void main(String[] args) {
        List<String> stages = Arrays.asList("read", "check", "write");

        String result = stages.parallelStream()
                              .map(String::toUpperCase)
                              .collect(Collectors.joining(" -> "));

        System.out.println(result);
    }
}
```

```bash
javac CollectInsteadOfPrint.java
java CollectInsteadOfPrint
```

Đầu ra xác định:

```text
READ -> CHECK -> WRITE
```

`Collectors.joining` ghép các phần tử theo encounter order của ordered stream trong ví dụ này. Với kết quả kiểu danh sách, có thể dùng `collect(Collectors.toList())`; cả hai đều thuộc Stream API vẫn dùng tốt hiện nay và có từ Java 8.

## 7. Lỗi thường gặp và giới hạn cần hiểu đúng

**Lỗi 1 — nghĩ `parallelStream()` đồng nghĩa mất thứ tự.** Không đúng: ordered source vẫn có encounter order; thứ tự xử lý nội bộ và thứ tự action của `forEach` là chuyện khác. `forEachOrdered` có thể giữ đúng thứ tự action dù xử lý song song.

**Lỗi 2 — nghĩ `forEachOrdered` tự tạo thứ tự cho nguồn unordered.** Nó chỉ **bảo toàn thứ tự đã tồn tại**. Với `HashSet` hoặc pipeline đã gọi `unordered()`, cần xác lập lại thứ tự nếu nghiệp vụ yêu cầu, chẳng hạn bằng `sorted()`.

**Lỗi 3 — đặt side effect trong `map`/`peek` rồi kỳ vọng thứ tự.** `forEachOrdered` không buộc callback trung gian chạy theo encounter order. Với parallel stream, callback `map`/`filter` có thể được thực thi ở các thời điểm khác nhau; `peek` cũng không phù hợp để dựa vào side effect mang tính nghiệp vụ.

**Lỗi 4 — sửa nguồn đang được duyệt.** Ví dụ thêm/xóa phần tử khỏi một `ArrayList` ngay trong action có thể gây lỗi hoặc hành vi không đáng tin. Action của Stream phải **non-interfering** với nguồn; việc thao tác trên trạng thái chia sẻ cần được thiết kế cẩn thận.

**Lỗi 5 — dùng `parallel().forEach(...)` để ghi vào một `ArrayList` chung.** `ArrayList` không thread-safe, nên có nguy cơ race condition. Nếu muốn một danh sách kết quả, sử dụng collector phù hợp; nếu cần action tuần tự theo thứ tự, `forEachOrdered` ràng buộc các lần gọi action nhưng vẫn không biến mọi side effect khác trong pipeline thành an toàn.

**Lỗi 6 — mặc định `parallel().forEachOrdered(...)` nhanh hơn tuần tự.** Đòi hỏi đầu ra có thứ tự có thể khiến runtime phải chờ và phối hợp giữa các nhánh, thậm chí làm mất lợi ích parallel. Hãy đo hiệu năng trên dữ liệu/tác vụ thực tế; với action nhẹ như in chuỗi, stream tuần tự thường dễ hiểu hơn.

**Lỗi 7 — tái sử dụng stream đã kết thúc.** Sau khi gọi `forEachOrdered` hay terminal operation khác, pipeline đã bị tiêu thụ. Muốn xử lý lần nữa thì tạo stream mới từ nguồn.

## 8. Tự kiểm tra

1. `Arrays.asList("x", "y", "z").parallelStream().forEachOrdered(System.out::print)` in gì? → **`xyz`**: `List` có encounter order, action cuối giữ nguyên thứ tự.
2. Đổi thành `forEach(System.out::print)` trên parallel stream thì sao? → Vẫn xử lý các phần tử, nhưng **không thể cam kết** stdout luôn là `xyz`.
3. Gọi `unordered().forEachOrdered(...)` trên một ordered stream thì sao? → Ta đã bỏ yêu cầu encounter order, nên `forEachOrdered` **không khôi phục** thứ tự ban đầu.
4. Muốn in các giá trị từ `HashSet` theo thứ tự tăng dần? → Dùng `stream().sorted().forEachOrdered(...)`, với các phần tử có quy tắc so sánh xác định.
5. Muốn tạo chuỗi kết quả theo thứ tự thay vì in trực tiếp? → Ưu tiên `collect(Collectors.joining(...))`.

**Ghi nhớ:** `forEachOrdered` bảo đảm **thứ tự action theo encounter order nếu encounter order tồn tại**; nó không bảo đảm mọi thao tác upstream tuần tự, không tự sắp xếp nguồn unordered và không đương nhiên tăng hiệu năng khi dùng parallel stream.

## Tài liệu API tham khảo

- Oracle Java SE 21 — [`Stream.forEachOrdered` và `Stream.forEach`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html).
- Oracle Java SE 21 — [Stream package: ordering, side effects, parallelism](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html).

Các API cốt lõi trong bài (`forEachOrdered`, `forEach`, `parallelStream`, `sorted`, `unordered`, `Collectors.joining`) vẫn đang được hỗ trợ và sử dụng trên các phiên bản Java hiện đại.