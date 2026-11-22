# Kiểm thử dữ liệu bị từ chối và dừng xử lý an toàn

Khi lọc dữ liệu tuần tự, hai yêu cầu thường bị nhầm lẫn là **từ chối một phần tử** và **dừng toàn bộ quá trình duyệt**. `Stream.filter()` giải quyết yêu cầu thứ nhất: phần tử không thỏa predicate bị loại khỏi kết quả, nhưng stream tiếp tục xét các phần tử sau. Nếu nghiệp vụ yêu cầu dừng ngay khi gặp phần tử đầu tiên không hợp lệ, cần dùng một thao tác short-circuit như `takeWhile()` hoặc một vòng lặp có `break`.

Kiểm thử phải xác nhận đúng hợp đồng đó. Một test chỉ kiểm tra danh sách kết quả có thể bỏ sót việc pipeline đã xử lý thêm dữ liệu sau điểm cần dừng. Ngược lại, một test kỳ vọng `filter()` dừng ở phần tử bị từ chối đang kiểm tra sai semantics của API.

## 1. Stream tuần tự và quá trình xử lý lazy

`Collection.stream()` tạo một stream tuần tự theo encounter order của collection có thứ tự, chẳng hạn `List`. Pipeline gồm các intermediate operation như `filter`, `map`, `takeWhile` và một terminal operation như `toList`, `collect`, `findFirst` hoặc `count`.

Intermediate operation là lazy: chúng mô tả cách xử lý, nhưng phần tử chỉ được duyệt khi terminal operation bắt đầu tiêu thụ stream. Một stream đã dùng terminal operation thì không thể tái sử dụng; nếu cần chạy hai phép kiểm tra độc lập, hãy tạo hai stream mới từ nguồn.

Với `list.stream()`, các phần tử được xử lý tuần tự theo encounter order. Có thể gọi `.sequential()` để yêu cầu pipeline tuần tự nếu stream trước đó có thể đang ở chế độ parallel. Chủ đề này dựa trên stream tuần tự có thứ tự; không suy rộng kết quả của một test dùng `parallelStream()` sang pipeline tuần tự.

## 2. `filter()` từ chối phần tử nhưng vẫn tiếp tục

`filter(predicate)` giữ lại phần tử khi predicate trả về `true`. Khi predicate trả về `false`, phần tử hiện tại không đi tiếp xuống các stage phía sau. Stream vẫn xét phần tử tiếp theo cho đến khi nguồn kết thúc hoặc một terminal operation short-circuit.

```java
List<Integer> values = List.of(2, 4, -1, 6, 0, 8);

List<Integer> accepted = values.stream()
        .filter(value -> value > 0)
        .toList();

// accepted = [2, 4, 6, 8]
```

Ở ví dụ này, `-1` và `0` bị loại. Các giá trị `6` và `8` vẫn được xét và được giữ lại. `filter()` không có nghĩa là “gặp phần tử sai thì dừng”; nó chỉ loại từng phần tử riêng lẻ.

Predicate nên là hàm không có side effect, không sửa nguồn dữ liệu và cho cùng một kết quả với cùng một đầu vào trong suốt quá trình duyệt. Không dùng predicate để ghi database, tăng bộ đếm nghiệp vụ hoặc phát sự kiện; các thao tác đó có thể gây khó khăn khi pipeline bị short-circuit hoặc thay đổi cách thực thi.

## 3. Lưu cả dữ liệu được chấp nhận và bị từ chối

`filter()` chỉ tạo ra luồng phần tử được giữ lại. Nếu cần kiểm thử hoặc báo cáo cả hai nhóm, `Collectors.partitioningBy()` phân chia dữ liệu theo một predicate trong cùng một lần duyệt:

```java
Map<Boolean, List<Integer>> groups = values.stream()
        .collect(Collectors.partitioningBy(value -> value > 0));

List<Integer> accepted = groups.get(Boolean.TRUE);
List<Integer> rejected = groups.get(Boolean.FALSE);
```

Với một stream tuần tự có encounter order, thứ tự phần tử trong từng danh sách được giữ theo thứ tự nguồn. `partitioningBy()` là phép thu thập toàn bộ nguồn; nó không dừng khi gặp phần tử đầu tiên bị từ chối.

Nếu cần lý do từ chối thay vì chỉ một cờ boolean, hãy biểu diễn kết quả kiểm tra bằng một kiểu dữ liệu riêng, ví dụ `ValidationResult<T>` gồm giá trị đầu vào, trạng thái hợp lệ và mã/lý do lỗi. Cách này giúp test lý do từ chối mà không phải tạo side effect trong predicate.

## 4. Dừng tại phần tử đầu tiên không thỏa điều kiện bằng `takeWhile()`

`takeWhile(predicate)` là intermediate operation short-circuit. Với một ordered sequential stream, nó giữ **đoạn prefix dài nhất** mà mọi phần tử đều thỏa predicate. Khi gặp phần tử đầu tiên trả về `false`, phần tử đó và phần còn lại của nguồn không được chuyển xuống các stage phía sau.

```java
List<Integer> prefix = values.stream()
        .takeWhile(value -> value > 0)
        .toList();

// prefix = [2, 4]
```

Với nguồn `[2, 4, -1, 6, 0, 8]`, phần tử `-1` là điểm dừng. Kết quả chỉ chứa `[2, 4]`; `6`, `0` và `8` không được xét tiếp bởi pipeline `takeWhile`.

`takeWhile()` có từ Java 9. Khi dùng Java 17+, có thể kết hợp với `Stream.toList()` để thu kết quả thành danh sách không sửa đổi. Nếu cần tương thích với Java 9, dùng `collect(Collectors.toList())` thay cho `toList()`.

### Phân biệt `takeWhile()` và `dropWhile()`

- `takeWhile(predicate)` giữ prefix thỏa điều kiện rồi dừng khi gặp phần tử đầu tiên không thỏa.
- `dropWhile(predicate)` bỏ prefix thỏa điều kiện, sau đó chuyển phần tử đầu tiên không thỏa và toàn bộ phần còn lại xuống pipeline.

`dropWhile()` không phải thao tác dừng xử lý. Nếu mục tiêu là dừng tại phần tử đầu tiên bị từ chối, dùng `takeWhile()` hoặc vòng lặp có `break`.

## 5. Các terminal operation có thể short-circuit

Ngoài `takeWhile`, một số terminal operation có thể kết thúc duyệt sớm khi đã đủ thông tin:

| Operation | Điều kiện có thể dừng sớm |
| --- | --- |
| `findFirst()` | Tìm được phần tử đầu tiên |
| `findAny()` | Tìm được một phần tử bất kỳ |
| `anyMatch(p)` | Có phần tử đầu tiên thỏa `p` |
| `allMatch(p)` | Gặp phần tử đầu tiên không thỏa `p` |
| `noneMatch(p)` | Gặp phần tử đầu tiên thỏa `p` |
| `limit(n)` | Đã lấy đủ `n` phần tử |
| `takeWhile(p)` | Gặp phần tử đầu tiên không thỏa `p` trong ordered stream |

Ví dụ, `values.stream().filter(this::isValid).findFirst()` dừng sau khi tìm được phần tử hợp lệ đầu tiên. Nó không xử lý phần còn lại sau khi đã tìm thấy kết quả. Tuy nhiên, nếu không có phần tử nào hợp lệ trong một nguồn hữu hạn, pipeline phải duyệt hết nguồn để xác nhận không có kết quả.

`filter()` tự nó không phải short-circuit operation. Một pipeline `filter(...).count()` thường phải xét toàn bộ nguồn để tính số phần tử còn lại. Một pipeline `filter(...).findFirst()` có thể dừng sớm vì terminal operation `findFirst()` short-circuit.

## 6. Thứ tự stage làm thay đổi ý nghĩa

Khi yêu cầu dừng tại phần tử đầu tiên không hợp lệ, đặt thao tác kiểm tra điều kiện dừng trước các stage có thể loại bỏ phần tử đó.

```java
// Dừng khi gặp phần tử đầu tiên không hợp lệ.
List<Integer> prefix = values.stream()
        .takeWhile(this::isValid)
        .filter(this::needsProcessing)
        .toList();

// Pipeline này loại phần tử không hợp lệ trước.
// takeWhile phía sau không còn nhìn thấy chúng để dừng.
List<Integer> filteredFirst = values.stream()
        .filter(this::isValid)
        .takeWhile(this::isValid)
        .toList();
```

Trong pipeline thứ hai, `filter()` đã bỏ các phần tử không hợp lệ. `takeWhile()` phía sau chỉ nhìn thấy những phần tử còn lại, vì vậy nó không thể phát hiện điểm từ chối ban đầu và thường tiếp tục đến hết nguồn.

Nếu điều kiện dừng và điều kiện xử lý khác nhau, hãy đặt chúng đúng thứ tự theo hợp đồng nghiệp vụ. Có thể dùng `takeWhile(isValid).filter(needsProcessing)` để dừng ở invalid đầu tiên nhưng chỉ xử lý các phần tử hợp lệ cần thiết.

## 7. Kiểm thử cả kết quả và ranh giới dừng

Một test tốt nên kiểm tra ít nhất hai điều:

1. Những phần tử nào được chấp nhận hoặc bị từ chối.
2. Phần tử nào là điểm dừng và có phần tử nào sau điểm đó bị pipeline tiếp tục tiêu thụ hay không.

Chỉ assert danh sách kết quả của `takeWhile()` chưa đủ để chứng minh phần tử phía sau không được duyệt. Trong test, có thể ghi nhận các phần tử đã đi qua ranh giới bằng `peek()` để quan sát traversal. Đây chỉ là instrumentation cho test; không dựa vào side effect của `peek()` để thực hiện logic nghiệp vụ.

Với nguồn `[2, 4, -1, 6, 0, 8]`, predicate của `takeWhile()` được kiểm tra đến `-1`. Phần tử dừng được tiêu thụ để đánh giá predicate, nhưng không đi xuống các stage sau `takeWhile`; `6`, `0` và `8` không được lấy từ nguồn cho pipeline đó.

## 8. Ví dụ hoàn chỉnh: kiểm tra dữ liệu bị từ chối và dừng an toàn

Chương trình sau kiểm tra ba hợp đồng: `filter()` loại phần tử không hợp lệ nhưng tiếp tục; `partitioningBy()` lưu cả hai nhóm; `takeWhile()` dừng tại phần tử đầu tiên bị từ chối. Test dùng assertion rõ ràng và trả mã lỗi bằng `AssertionError` nếu kết quả sai.

Tạo tệp `SequentialFilterSafetyDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class SequentialFilterSafetyDemo {
    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(2, 4, -1, 6, 0, 8);

        List<Integer> accepted = input.stream()
                .filter(value -> value > 0)
                .toList();

        Map<Boolean, List<Integer>> partitioned = input.stream()
                .collect(Collectors.partitioningBy(value -> value > 0));

        List<Integer> visited = new ArrayList<>();
        List<Integer> prefix = input.stream()
                .peek(visited::add)
                .takeWhile(value -> value > 0)
                .toList();

        check(accepted.equals(List.of(2, 4, 6, 8)),
                "filter must continue after rejected elements");
        check(partitioned.get(Boolean.FALSE).equals(List.of(-1, 0)),
                "partition must retain rejected values");
        check(prefix.equals(List.of(2, 4)),
                "takeWhile must return the prefix before the first rejection");
        check(visited.equals(List.of(2, 4, -1)),
                "takeWhile must stop at the first rejected value");

        System.out.println("Accepted: " + accepted);
        System.out.println("Rejected: " + partitioned.get(Boolean.FALSE));
        System.out.println("Prefix before first rejection: " + prefix);
        System.out.println("Visited through stopping value: " + visited);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all SequentialFilterSafetyDemo.java
java SequentialFilterSafetyDemo
```

Kết quả stdout:

```text
Accepted: [2, 4, 6, 8]
Rejected: [-1, 0]
Prefix before first rejection: [2, 4]
Visited through stopping value: [2, 4, -1]
```

Kết quả chứng minh `filter()` vẫn xét `6` và `8` sau khi loại `-1`; `partitioningBy()` giữ cả `-1` và `0` trong nhóm từ chối; `takeWhile()` chỉ tiêu thụ đến `-1` rồi dừng. `peek()` được dùng riêng để quan sát trong test, không phải để ghi log nghiệp vụ hoặc cập nhật trạng thái production.

## 9. Khi cần ghi nhận phần tử gây dừng, dùng vòng lặp tường minh

`takeWhile()` loại phần tử đầu tiên không thỏa khỏi kết quả. Nếu nghiệp vụ cần lưu chính phần tử đó, tạo thông báo lỗi chi tiết hoặc giải phóng tài nguyên ngay tại điểm dừng, một vòng lặp tuần tự thường dễ hiểu hơn:

```java
Integer rejected = null;
List<Integer> processed = new ArrayList<>();

for (Integer value : values) {
    if (value <= 0) {
        rejected = value;
        break;
    }
    processed.add(value);
}
```

Vòng lặp thể hiện rõ điểm dừng và giữ lại giá trị bị từ chối. Nó cũng phù hợp khi mỗi phần tử cần nhiều bước có thể thất bại, cần cập nhật trạng thái hoặc phải đóng một tài nguyên cụ thể. Không cần ép mọi logic tuần tự vào Stream API nếu vòng lặp cho hợp đồng dễ kiểm tra hơn.

## 10. Dừng an toàn khi nguồn sở hữu tài nguyên

Một số stream được tạo từ tài nguyên bên ngoài, ví dụ `Files.lines(path)`. Terminal operation như `findFirst()` hoặc `takeWhile()` có thể dừng tiêu thụ sớm, nhưng điều đó không tự đóng stream nguồn.

Dùng try-with-resources để đóng nguồn cả khi pipeline kết thúc sớm hoặc ném exception:

```java
try (Stream<String> lines = Files.lines(path)) {
    List<String> prefix = lines
            .takeWhile(line -> !line.equals("STOP"))
            .toList();
}
```

Ở đây, dòng `STOP` là điểm dừng và không được đưa vào prefix. Khi rời khỏi block, `lines.close()` được gọi. Nếu terminal operation ném exception, try-with-resources vẫn đóng stream và giữ exception theo semantics của Java.

Stream trong bộ nhớ như `List.stream()` thường không cần đóng. Với stream bọc file, socket hoặc resource khác, hãy đọc hợp đồng API và quản lý vòng đời bằng try-with-resources. Không giả định terminal operation tự động gọi `close()`.

## 11. Exception không phải cách thông thường để từ chối dữ liệu

Nếu predicate ném exception, terminal operation sẽ kết thúc bằng exception thay vì tiếp tục như khi predicate trả `false`. Đây là cách biểu thị lỗi thực thi hoặc trạng thái không thể tiếp tục, không nên dùng cho dữ liệu không hợp lệ thông thường.

Phân biệt ba trường hợp:

- **Từ chối một phần tử:** predicate trả `false`; `filter()` loại phần tử và tiếp tục.
- **Dừng theo điều kiện:** dùng `takeWhile()`, terminal short-circuit hoặc `break` để ngừng duyệt.
- **Lỗi xử lý:** exception được ném và truyền tới caller; tài nguyên phải được đóng trong `finally` hoặc try-with-resources.

Nếu đã thực hiện side effect trước khi phát hiện dữ liệu lỗi, việc dừng pipeline không tự hoàn tác những side effect đó. Với xử lý cần all-or-nothing, hãy validate trước khi commit, dùng transaction hoặc thiết kế thao tác có thể retry/compensate.

## 12. Nguồn vô hạn và điều kiện kết thúc

Với stream hữu hạn, một terminal operation không short-circuit thường kết thúc khi nguồn cạn. Với stream vô hạn như `Stream.iterate()` hoặc `Stream.generate()`, pipeline chỉ kết thúc nếu có giới hạn hoặc điều kiện short-circuit phù hợp.

`filter()` trên stream vô hạn có thể tiếp tục mãi nếu không tìm được phần tử thỏa predicate. `filter(...).findFirst()` chỉ kết thúc nếu cuối cùng tìm được một phần tử phù hợp; nếu không có phần tử nào, nó có thể không trả về.

Với nguồn có sentinel hoặc điều kiện dừng, `takeWhile()` có thể giới hạn prefix. Nếu không có bảo đảm sentinel sẽ xuất hiện, hãy thêm giới hạn như `limit()` hoặc dùng cơ chế cancellation phù hợp để tránh xử lý vô hạn.

## 13. Các lỗi kiểm thử thường gặp

- **Kỳ vọng `filter()` dừng ở phần tử sai:** `filter()` loại phần tử hiện tại và tiếp tục; dùng `takeWhile()` nếu cần dừng tại invalid đầu tiên.
- **Đặt `filter()` trước `takeWhile()` khi cần phát hiện invalid:** phần tử invalid đã bị bỏ nên điều kiện dừng không còn nhìn thấy nó.
- **Chỉ kiểm tra danh sách kết quả:** bổ sung quan sát traversal hoặc kiểm tra hành vi downstream để xác nhận không xử lý phần tử sau điểm dừng.
- **Dùng `peek()` làm logic nghiệp vụ:** `peek()` chủ yếu phục vụ quan sát/debug; side effect có thể làm test khó hiểu và phụ thuộc traversal.
- **Dùng exception để biểu diễn một bản ghi bị từ chối:** trả `false` hoặc tạo kết quả validation có lý do cụ thể.
- **Dùng `dropWhile()` để mong dừng:** `dropWhile()` bỏ prefix rồi tiếp tục với phần còn lại.
- **Dùng `forEach()` và tìm cách break:** `forEach()` không có cơ chế break; dùng `takeWhile()` hoặc vòng lặp thường.
- **Quên đóng stream đọc từ tài nguyên:** bọc `Files.lines()` và nguồn resource-backed trong try-with-resources.
- **Dựa vào side effect đã chạy để suy ra mọi phần tử đã được xử lý:** short-circuit có thể kết thúc sớm; kiểm tra đúng ranh giới cần thiết.
- **Không tính đến stream vô hạn:** thêm điều kiện kết thúc hoặc giới hạn số phần tử.

## 14. Quy trình kiểm thử đề xuất

1. Xác định predicate nào quyết định một phần tử được chấp nhận.
2. Xác định phần tử bị từ chối chỉ bị loại riêng lẻ hay phải dừng toàn bộ quá trình.
3. Dùng `filter()` nếu cần bỏ từng phần tử và tiếp tục; dùng `partitioningBy()` nếu cần cả hai nhóm.
4. Dùng `takeWhile()` cho prefix của ordered sequential stream hoặc vòng lặp `break` nếu cần giữ lại phần tử gây dừng.
5. Đặt stage theo đúng thứ tự; không loại sentinel trước khi stage dừng có cơ hội nhìn thấy nó.
6. Test cả danh sách đầu ra, nhóm bị từ chối và ranh giới traversal.
7. Giữ predicate stateless, không can thiệp nguồn và không tạo side effect nghiệp vụ.
8. Với nguồn sở hữu tài nguyên, dùng try-with-resources để đóng kể cả khi short-circuit hoặc exception.
9. Với stream vô hạn, bảo đảm có điều kiện kết thúc hoặc giới hạn.
10. Chọn vòng lặp tường minh khi cần xử lý phần tử lỗi, rollback, cleanup hoặc điều phối phức tạp.

`filter()` và `takeWhile()` giải quyết hai hợp đồng khác nhau: một thao tác loại phần tử và tiếp tục, thao tác còn lại giữ prefix rồi dừng tại phần tử đầu tiên không thỏa. Kiểm thử phải xác nhận cả dữ liệu được giữ, dữ liệu bị từ chối và ranh giới dừng; với nguồn có tài nguyên, luôn quản lý việc đóng nguồn độc lập với short-circuit.