# Chọn vòng lặp khi phép biến đổi có nhiều nhánh khó đọc

## 1. Mục tiêu: làm rõ luồng xử lý dữ liệu

Trong Java, `Stream` phù hợp để mô tả các phép biến đổi và tổng hợp rõ ràng như `filter` → `map` → `toList`. Nhưng khi một phần tử phải đi qua **nhiều nhánh điều kiện, nhiều quy tắc từ chối, các điểm bỏ qua và việc báo lỗi có ngữ cảnh**, nhồi tất cả logic vào một chuỗi lambda có thể khiến mã khó đọc và khó kiểm thử.

Khi đó, một vòng lặp `for`/`for-each` với `if`, `switch`, `continue` và các thao tác được đặt tên rõ ràng thường giúp người đọc nhìn thấy **dòng nào đi tiếp, dòng nào bị bỏ qua và vì sao**. Đây là lựa chọn về khả năng diễn đạt, không phải quy tắc rằng “vòng lặp luôn tốt hơn Stream”.

Mục tiêu của bài học:

1. Nhận diện thời điểm pipeline nhiều `map`/`filter` và lambda lồng nhau làm logic bị che khuất.
2. Chuyển đổi thành vòng lặp với các nhánh rõ ràng mà vẫn bảo toàn hành vi.
3. Thiết kế kết quả `Accepted`, `Rejected` và `Skipped` để tránh âm thầm xóa dữ liệu lỗi.
4. Duy trì khả năng kiểm thử, không tạo tác dụng phụ khó kiểm soát.
5. Biết khi nào nên giữ Stream bằng cách trích logic nhiều nhánh thành hàm riêng.

## 2. Stream đọc tốt khi các bước đơn giản và nhất quán

Ví dụ sau biểu diễn một phép biến đổi tuyến tính:

```java
List<String> cleaned = names.stream()
        .map(String::strip)
        .filter(name -> !name.isEmpty())
        .map(String::toUpperCase)
        .toList();
```

Giả sử `names` là `List<String>` không chứa `null`, ta đọc tuần tự: cắt khoảng trắng, loại chuỗi rỗng, đổi thành chữ hoa, thu thập kết quả. Mỗi dòng có một trách nhiệm và chuỗi xử lý không cần nhiều luồng điều khiển phụ.

Nhưng một yêu cầu khác có thể gồm:

- Nếu dòng `null` hoặc rỗng, bỏ qua và ghi rõ lý do.
- Nếu là comment bắt đầu bằng `#`, bỏ qua.
- Nếu dữ liệu không có đủ trường, đánh dấu từ chối.
- Nếu mã kênh không được hỗ trợ, đánh dấu từ chối.
- Nếu số lượng không phải số nguyên, trả lỗi dữ liệu kèm vị trí.
- Nếu số lượng nằm ngoài giới hạn, từ chối.
- Nếu hợp lệ, biến đổi theo kênh và thêm nhãn riêng cho đơn hàng số lượng lớn.

Việc đưa toàn bộ logic này vào một lambda trong `map` sẽ tạo nhiều nhánh `if`, các giá trị tạm, xử lý ngoại lệ và kết quả thuộc nhiều loại. Khi đó cú pháp Stream không còn khiến logic đơn giản hơn.

## 3. Dấu hiệu nên cân nhắc vòng lặp

| Dấu hiệu | Tác hại khi cố ghép lambda dài | Vòng lặp giúp gì? |
| --- | --- | --- |
| Nhiều điều kiện rẽ nhánh | `map` lồng các `if`/toán tử ba ngôi | Thể hiện điểm chuyển nhánh trực tiếp |
| Có nhiều trường hợp `skip` | Dễ trả `null` rồi `filter(nonNull)` | Dùng `continue`, đồng thời ghi `Skipped` nếu nghiệp vụ cần |
| Nhiều lỗi cần lý do riêng | Một `Optional.empty()` dễ làm mất nguyên nhân | Trả kết quả `Rejected(line, reason)` rõ ràng |
| Cần biến tạm có tên | Lambda dài hoặc lồng nhau | Khai báo giá trị trung gian ngay gần nơi sử dụng |
| Có thứ tự bước kiểm tra quan trọng | Khó nhìn nhận lỗi đầu tiên bị bắt | `if` guard sắp xếp theo quy tắc nghiệp vụ |
| Cần `break` khi đạt điều kiện | Nhiều thao tác kết thúc và cờ trạng thái | `break` nêu rõ điểm dừng của vòng lặp |
| Cần cập nhật kết quả nhiều loại | Side effect hoặc collect phức tạp | Tập hợp kết quả trong một cấu trúc có chủ đích |

Đây là **dấu hiệu cân nhắc**, không phải tiêu chuẩn đo bằng số lượng `if` hay độ dài dòng. Một pipeline vẫn dễ đọc nếu logic nhánh phức tạp được trích thành phương thức có tên rõ. Cũng có vòng lặp rất khó đọc nếu quá nhiều biến chia sẻ và điều kiện lồng sâu.

## 4. Ví dụ một bước chuyển đổi có quá nhiều nhánh

Giả sử dữ liệu nhập theo định dạng đơn giản:

```text
KÊNH,TÊN_SẢN_PHẨM,SỐ_LƯỢNG
```

Các kênh hỗ trợ: `WEB`, `STORE`, `APP`. Quy tắc minh họa:

- Chuỗi `null`, dòng trống và comment `#...`: `Skipped` với lý do.
- Dòng nghiệp vụ phải có đúng ba trường, tách bằng dấu phẩy.
- Tên sản phẩm không được rỗng và chỉ gồm chữ cái Latin ASCII sau khi chuẩn hóa chữ hoa.
- Kênh phải thuộc ba giá trị nêu trên.
- Số lượng phải là số nguyên trong khoảng `1..10`.
- Kênh `WEB` được ghi là `ONLINE`, `STORE` giữ nguyên, `APP` thành `MOBILE`.
- Số lượng từ `5` trở lên được thêm hậu tố ` [BULK]`.
- Mỗi dòng đầu vào cho đúng một `Outcome`: được chấp nhận, bị từ chối hoặc được bỏ qua theo quy tắc.

Nếu cố ép mọi thứ thành `Stream<String>` rồi trả `null` khi gặp dữ liệu hỏng, chẳng hạn:

```java
// Phản ví dụ về thiết kế: mô phỏng cách âm thầm loại lỗi.
// Cần có List<String> rows và các import java.util.*.
List<String> labels = rows.stream()
        .map(raw -> {
            if (raw == null || raw.isBlank()) {
                return null;
            }
            String[] fields = raw.split(",");
            if (fields.length != 3) {
                return null;
            }
            try {
                int quantity = Integer.parseInt(fields[2].strip());
                return fields[1].strip() + " x" + quantity;
            } catch (NumberFormatException ignored) {
                return null;
            }
        })
        .filter(java.util.Objects::nonNull)
        .toList();
```

Đoạn trên **chưa thực hiện đầy đủ quy tắc nghiệp vụ** và là ví dụ điều cần tránh, không phải lời giải. Nó làm mất vị trí, lý do từ chối và nhiều điều kiện hợp lệ. Nếu bổ sung mọi nhánh khác vào cùng lambda thì nó lại càng khó hiểu. Khi không thấy lỗi trong kết quả, ta không biết có phải không có lỗi thật hay lỗi đã bị loại thầm lặng.

Ta sẽ dùng vòng lặp với kết quả tường minh để kiểm tra được từng nhánh.

## 5. Phân loại đầu ra trước khi viết vòng lặp

Thay vì trả `String` hoặc `null`, hãy dùng một kiểu kết quả có ba nhánh:

```text
Dòng thứ i
    │
    ├── null/rỗng/comment ──────────────> Skipped(i, reason)
    │
    ├── sai cấu trúc/kênh/số lượng ─────> Rejected(i, reason)
    │
    └── hợp lệ ─────────────────────────> Accepted(i, label)
```

Trong Java 17, `sealed interface` và `record` mô tả hợp đồng ngắn gọn:

```java
sealed interface Outcome permits Accepted, Rejected, Skipped {}

record Accepted(int line, String label) implements Outcome {}
record Rejected(int line, String reason) implements Outcome {}
record Skipped(int line, String reason) implements Outcome {}
```

Đây là một **đoạn khai báo minh họa**, được đặt đầy đủ trong class của chương trình ở phần tiếp theo. Các `record` tự cung cấp accessor, `equals`, `hashCode` và `toString` dựa trên thành phần; nhờ vậy test so sánh được các kết quả mà không phải viết nhiều mã phụ trợ.

Không nhất thiết luôn cần ba nhánh: nếu dữ liệu rỗng là lỗi, hãy trả `Rejected` thay vì `Skipped`. Điều quan trọng là hợp đồng nghiệp vụ phân biệt được “được bỏ qua theo quy tắc” và “đã thất bại”.

## 6. Chương trình Java 17 hoàn chỉnh: vòng lặp nhiều nhánh nhưng rõ ràng

Tạo tệp `BranchingTransformationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class BranchingTransformationDemo {
    sealed interface Outcome permits Accepted, Rejected, Skipped {}

    record Accepted(int line, String label) implements Outcome {}
    record Rejected(int line, String reason) implements Outcome {}
    record Skipped(int line, String reason) implements Outcome {}

    static List<String> sampleRows() {
        // Arrays.asList cho phép chứa null để kiểm tra dữ liệu thiếu.
        return Arrays.asList(
                "# daily export",
                " WEB,alpha,3 ",
                "STORE,beta,0",
                "APP,gamma,5",
                "OTHER,delta,2",
                "WEB,epsilon,not-a-number",
                "WEB,zeta,12",
                null,
                "STORE,eta,1",
                "WEB,,2",
                "");
    }

    static List<Outcome> transform(List<String> rows) {
        Objects.requireNonNull(rows, "rows");
        List<Outcome> outcomes = new ArrayList<>();

        for (int index = 0; index < rows.size(); index++) {
            int line = index + 1;
            String raw = rows.get(index);

            // Guard 1: trường hợp được phép bỏ qua.
            if (raw == null) {
                outcomes.add(new Skipped(line, "missing line"));
                continue;
            }

            String trimmed = raw.strip();
            if (trimmed.isEmpty()) {
                outcomes.add(new Skipped(line, "blank"));
                continue;
            }

            if (trimmed.startsWith("#")) {
                outcomes.add(new Skipped(line, "comment"));
                continue;
            }

            // Guard 2: kiểm tra cấu trúc trường đầu vào.
            String[] fields = trimmed.split(",", -1);
            if (fields.length != 3) {
                outcomes.add(new Rejected(line, "expected 3 fields"));
                continue;
            }

            String channel = fields[0].strip()
                    .toUpperCase(Locale.ROOT);
            String product = fields[1].strip()
                    .toUpperCase(Locale.ROOT);
            String quantityText = fields[2].strip();

            if (product.isEmpty()) {
                outcomes.add(new Rejected(line, "missing product"));
                continue;
            }
            if (!product.matches("[A-Z]+")) {
                outcomes.add(new Rejected(line, "invalid product"));
                continue;
            }

            // Guard 3: xác định cách hiển thị theo kênh.
            String channelLabel;
            if (channel.equals("WEB")) {
                channelLabel = "ONLINE";
            } else if (channel.equals("STORE")) {
                channelLabel = "STORE";
            } else if (channel.equals("APP")) {
                channelLabel = "MOBILE";
            } else {
                outcomes.add(new Rejected(line, "unsupported channel"));
                continue;
            }

            // Guard 4: chỉ bắt ngoại lệ parse dự kiến.
            int quantity;
            try {
                quantity = Integer.parseInt(quantityText);
            } catch (NumberFormatException cause) {
                outcomes.add(new Rejected(line, "invalid quantity"));
                continue;
            }

            if (quantity < 1 || quantity > 10) {
                outcomes.add(new Rejected(line, "quantity out of range"));
                continue;
            }

            // Nhánh thành công nằm ở cuối, không bị lồng nhiều cấp.
            String suffix = quantity >= 5 ? " [BULK]" : "";
            String label = channelLabel + ":" + product
                    + " x" + quantity + suffix;
            outcomes.add(new Accepted(line, label));
        }

        return List.copyOf(outcomes);
    }

    static void check(Object expected, Object actual, String description) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    description + ": expected=" + expected
                            + ", actual=" + actual);
        }
    }

    static void runTests() {
        List<Outcome> actual = transform(sampleRows());
        List<Outcome> expected = List.of(
                new Skipped(1, "comment"),
                new Accepted(2, "ONLINE:ALPHA x3"),
                new Rejected(3, "quantity out of range"),
                new Accepted(4, "MOBILE:GAMMA x5 [BULK]"),
                new Rejected(5, "unsupported channel"),
                new Rejected(6, "invalid quantity"),
                new Rejected(7, "quantity out of range"),
                new Skipped(8, "missing line"),
                new Accepted(9, "STORE:ETA x1"),
                new Rejected(10, "missing product"),
                new Skipped(11, "blank"));

        check(expected, actual, "all outcomes and positions");
        check(sampleRows().size(), actual.size(), "one result per input");

        long accepted = actual.stream()
                .filter(Accepted.class::isInstance).count();
        long rejected = actual.stream()
                .filter(Rejected.class::isInstance).count();
        long skipped = actual.stream()
                .filter(Skipped.class::isInstance).count();

        check(3L, accepted, "accepted count");
        check(5L, rejected, "rejected count");
        check(3L, skipped, "skipped count");

        check(List.of(), transform(List.of()), "empty input");
        check(List.of(new Rejected(1, "expected 3 fields")),
                transform(List.of("WEB,alpha")), "missing field");
        check(List.of(new Rejected(1, "invalid product")),
                transform(List.of("WEB,alpha-1,2")), "product rule");
        check(actual, transform(sampleRows()), "repeatable result");
    }

    public static void main(String[] args) {
        runTests();
        System.out.println("tests=PASS");

        List<Outcome> outcomes = transform(sampleRows());
        for (Outcome outcome : outcomes) {
            if (outcome instanceof Accepted accepted) {
                System.out.println("OK " + accepted.line()
                        + ": " + accepted.label());
            } else if (outcome instanceof Rejected rejected) {
                System.out.println("ERROR " + rejected.line()
                        + ": " + rejected.reason());
            } else if (outcome instanceof Skipped skipped) {
                System.out.println("SKIP " + skipped.line()
                        + ": " + skipped.reason());
            }
        }

        long accepted = outcomes.stream()
                .filter(Accepted.class::isInstance).count();
        long rejected = outcomes.stream()
                .filter(Rejected.class::isInstance).count();
        long skipped = outcomes.stream()
                .filter(Skipped.class::isInstance).count();
        System.out.println("accepted=" + accepted
                + " rejected=" + rejected
                + " skipped=" + skipped);
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac BranchingTransformationDemo.java
java BranchingTransformationDemo
```

Stdout dự kiến:

```text
tests=PASS
SKIP 1: comment
OK 2: ONLINE:ALPHA x3
ERROR 3: quantity out of range
OK 4: MOBILE:GAMMA x5 [BULK]
ERROR 5: unsupported channel
ERROR 6: invalid quantity
ERROR 7: quantity out of range
SKIP 8: missing line
OK 9: STORE:ETA x1
ERROR 10: missing product
SKIP 11: blank
accepted=3 rejected=5 skipped=3
```

Trong ví dụ, `runTests()` ném `AssertionError` nếu bất kỳ kết quả nào khác kỳ vọng; nó không cần cờ JVM `-ea`. Nếu chương trình in `tests=PASS`, các điều kiện kiểm tra đã chạy qua.

### Vì sao vòng lặp giúp rõ hơn trong ví dụ này?

Mỗi `if` ở đầu vòng lặp là một **guard**: khi điều kiện đúng, thêm một kết quả và `continue` tới dòng tiếp theo. Vì vậy nhánh thành công không bị lồng sâu trong những khối `else`.

Dòng `line = index + 1` giữ vị trí gốc để truy vết, ngay cả khi một dòng được bỏ qua. `split(",", -1)` giữ cả trường trống ở cuối; `split(",")` mặc định bỏ các chuỗi rỗng cuối khiến dữ liệu thiếu trường khó phân biệt. `Locale.ROOT` tránh phụ thuộc locale của máy khi đổi chữ hoa.

`try/catch` bao quanh **duy nhất** `Integer.parseInt`: chuyển đổi thất bại là lỗi dữ liệu dự kiến, được biểu diễn bằng `Rejected`. Không bắt rộng `Exception` để che lỗi lập trình hoặc lỗi hệ thống. Đường thành công chỉ chạy khi đã qua đầy đủ điều kiện.

Lệnh `List.copyOf(outcomes)` tạo danh sách kết quả không thể chỉnh sửa cấu trúc, tiện cho hợp đồng trả về. Các phần tử của danh sách đều là `record` chứa `int` và `String`, nên không có trạng thái mutable nội bộ trong ví dụ này. Đầu vào không bị thay đổi.

Các lời gọi Stream để đếm `Accepted`, `Rejected`, `Skipped` ở cuối lại **rất dễ đọc**, vì mỗi phép xử lý chỉ có một predicate. Có thể sử dụng vòng lặp cho bước phân nhánh và Stream cho bước tổng hợp; không cần chọn một phong cách cho toàn bộ chương trình.

## 7. Đừng dùng `continue` làm mất dữ liệu lỗi

Có hai cách dùng `continue` khác nhau:

```java
// Đáng ngờ nếu hợp đồng yêu cầu báo lỗi:
if (invalid) {
    continue;
}

// Tường minh về lý do:
if (invalid) {
    outcomes.add(new Rejected(line, "invalid input"));
    continue;
}
```

Hai đoạn trên là mã minh họa với biến `invalid`, `outcomes` và `line` đã được khai báo ở ngữ cảnh chứa chúng. Với đoạn thứ nhất, đầu vào không được ghi nhận trong danh sách đầu ra. Điều này chỉ đúng nếu hợp đồng **cho phép loại bỏ hoàn toàn** và không cần truy vết. Với đoạn thứ hai, mỗi dòng vẫn có kết quả tương ứng.

Đừng nhầm ba khái niệm:

- `continue` bỏ phần còn lại của **lần lặp hiện tại** và chuyển sang lần lặp tiếp theo.
- `break` thoát khỏi vòng lặp gần nhất; dùng khi yêu cầu thật sự là dừng xử lý.
- `return` thoát khỏi phương thức chứa nó; đặt trong vòng lặp có thể khiến cả lô dừng sớm.

Trong lambda của Stream, `return` chỉ trả kết quả từ **thân lambda**, không phải `continue` của vòng lặp ngoài hoặc `return` từ phương thức bao quanh. Trộn lẫn các ngữ nghĩa này là nguồn lỗi thường gặp khi cố dịch máy móc một vòng lặp phức tạp sang `map`/`forEach`.

## 8. Khi nào vẫn giữ được Stream bằng cách trích hàm?

Nhiều nhánh không bắt buộc phải làm cho Stream khó đọc. Cách thay thế là đưa quy tắc của **một phần tử** vào phương thức `transformOne(line, raw)` có hợp đồng trả về `Outcome`:

```java
// Minh họa cấu trúc: transformOne cần được triển khai
// với chính các quy tắc nghiệp vụ đã mô tả ở phần 6.
List<Outcome> outcomes = java.util.stream.IntStream
        .range(0, rows.size())
        .mapToObj(i -> transformOne(i + 1, rows.get(i)))
        .toList();
```

Ở đây `rows` là `List<String>`, và `transformOne(int, String)` là phương thức do ứng dụng tự định nghĩa, trả về `Outcome`. Đoạn mã là minh họa cách thiết kế, không phải tệp độc lập. Stream đã trở nên ngắn gọn: nó chỉ duyệt các vị trí và biến mỗi dòng thành một kết quả. Phần logic nhiều nhánh nằm trong hàm có tên, có thể kiểm thử riêng.

Nếu hành vi của pipeline về bản chất là ánh xạ từng phần tử độc lập, cách này thường tốt. Nếu công việc cần **dừng toàn bộ khi gặp một điều kiện**, có nhiều điểm cập nhật trạng thái trong quá trình duyệt hoặc phụ thuộc luồng điều khiển của vòng lặp, `for` vẫn có thể trực tiếp hơn.

Một kỹ thuật hữu ích là trích riêng các bước nhỏ như `parseFields`, `validateQuantity`, `formatLabel`. Đừng tạo hàng chục hàm chỉ để tránh một câu `if` đơn giản; hãy tách khi mỗi hàm có ý nghĩa nghiệp vụ rõ và có thể kiểm tra độc lập.

## 9. Giữ cùng ngữ nghĩa khi đổi từ Stream sang vòng lặp

Khi refactor, kiểm tra các khác biệt quan trọng sau.

| Khía cạnh | Câu hỏi cần kiểm tra |
| --- | --- |
| Thứ tự phần tử | Pipeline cũ có encounter order không? Có dùng `sorted`, `unordered` hoặc parallel Stream không? |
| Lọc dữ liệu | Những phần tử nào bị loại? Có phải giữ dấu vết `Skipped`/`Rejected` không? |
| Giá trị `null` | Stream cũ chấp nhận, loại hay ném lỗi? Vòng lặp phải giữ chính sách được chọn |
| Xử lý lỗi | Ngoại lệ phải lan lên hay trở thành lỗi dữ liệu có ngữ cảnh? |
| Kết quả | `Stream.toList()` cho List unmodifiable; vòng lặp trả `ArrayList` mặc định mutable nếu không bọc |
| Dừng sớm | Có `findFirst`, `anyMatch`, `limit`, `takeWhile` tương đương `break` không? |
| Tính lười | Stream trung gian có thể chưa thực thi; vòng lặp chạy ngay khi được gọi |
| Tác dụng phụ | Có ghi file/DB hoặc log trong lambda không? Thứ tự và retry đã được xác định chưa? |
| Hiệu năng | Có cần tạo collection kết quả? Có thể xử lý từng dòng mà không giữ toàn bộ dữ liệu không? |

Với `Stream.toList()` (Java 16+) kết quả không thể chỉnh sửa. Khi thay bằng `ArrayList`, nếu cần duy trì hợp đồng không thể sửa, hãy trả về `List.copyOf(...)` hoặc một cấu trúc phù hợp. `List.copyOf(...)` không cho phép phần tử null; phải kiểm tra hợp đồng dữ liệu trước khi dùng.

### Không giả định vòng lặp luôn nhanh hơn

Khác biệt tốc độ còn phụ thuộc kiểu dữ liệu, boxing, allocation, tối ưu hóa JIT, tác vụ I/O và chi phí của chính phép biến đổi. Trong pipeline có nhiều regex, parse và kiểm tra lỗi, thời gian có thể bị chi phối bởi các thao tác này thay vì cú pháp lặp. Hãy ưu tiên mã đúng và dễ hiểu; nếu hiệu năng là yêu cầu cụ thể, đo bằng benchmark phù hợp (ví dụ JMH), với workload và dữ liệu gần thực tế.

### `parallelStream()` không phải giải pháp thay thế cho vòng lặp nhiều nhánh

Việc chuyển sang parallel có thể làm các side effect khó đoán hơn và không phù hợp nếu quá trình xử lý phụ thuộc thứ tự hoặc trạng thái chia sẻ. Một vòng lặp tuần tự có thứ tự rõ; muốn xử lý đồng thời, cần xác định các phần tử độc lập, thread safety, chính sách lỗi và thứ tự kết quả. Không chọn Stream chỉ vì có `.parallel()`.

## 10. Kiểm thử để chứng minh mã sau khi refactor đúng

Trong ví dụ phần 6, bộ test không chỉ so sánh số lượng thành công; nó so sánh **từng outcome và chỉ số dòng**. Những kiểm tra nên có:

1. **Nhánh hợp lệ của từng kênh**: `WEB`, `STORE`, `APP` có nhãn tương ứng.
2. **Nhánh ưu tiên số lượng lớn**: số lượng `5` có `[BULK]`; số lượng nhỏ hơn không có.
3. **Biên số lượng**: `1` và `10` hợp lệ, `0` và `11` bị từ chối.
4. **Định dạng đầu vào lỗi**: thiếu trường, trường dư, tên sản phẩm trống, ký tự không được phép, số lượng không parse được.
5. **`null` và blank**: tạo `Skipped` như quy định, không ném `NullPointerException` ngẫu nhiên.
6. **Vị trí**: mỗi dòng có đúng một kết quả và dòng lỗi trỏ đúng `line`.
7. **Thứ tự**: kết quả đầu ra giữ thứ tự dữ liệu đầu vào.
8. **Tính lặp lại**: gọi cùng dữ liệu hai lần cho kết quả bằng nhau nếu không có trạng thái ngoài.
9. **Không sửa đầu vào**: các `String` trong danh sách đầu vào không bị thay và không có thao tác xóa phần tử nguồn.
10. **Ngoại lệ ngoài hợp đồng**: nếu lỗi lập trình hoặc hạ tầng xuất hiện, không được che bằng fallback thành công giả.

Một bất biến đáng chú ý trong thiết kế này là:

```text
acceptedCount + rejectedCount + skippedCount == inputCount
```

Bất biến đúng vì mỗi lần lặp chỉ thêm **một** `Outcome` rồi `continue`, hoặc thêm một `Accepted` ở cuối. Nếu thêm nhánh mới mà quên lưu kết quả, một test tổng số sẽ phát hiện sai lệch. Tuy nhiên, chỉ so sánh tổng số chưa đủ: có thể hai kết quả sai loại vẫn khiến tổng đúng; cần kiểm tra nội dung và lý do.

### Kiểm tra các nhánh bị che bởi thứ tự guard

Ví dụ `"OTHER,,abc"` cùng lúc sai tên, sai kênh và sai số lượng. Chương trình phần 6 báo `missing product` trước, bởi guard kiểm tra sản phẩm chạy trước guard kênh và số lượng. Đây là **chính sách chọn lỗi đầu tiên**, không phải thứ tự bất biến của Java.

Nếu nghiệp vụ muốn trả mọi lỗi của một bản ghi, cấu trúc `continue` theo lỗi đầu tiên không đủ: cần một danh sách vi phạm để thu thập nhiều lỗi, hoặc bộ validator tách biệt. Việc chọn vòng lặp chỉ giúp viết chính sách rõ ràng hơn; nó không tự quyết định policy.

## 11. Những lỗi thường gặp khi chuyển sang vòng lặp

**Lỗi 1: thay Stream rối bằng vòng lặp có `if` lồng sâu.** Nếu trong vòng lặp vẫn có năm lớp `if/else`, khả năng đọc không cải thiện. Dùng guard clauses, đặt tên điều kiện và trích phương thức nghiệp vụ.

**Lỗi 2: dùng `continue` để âm thầm bỏ lỗi.** Nếu không ghi `Rejected`, dữ liệu không hợp lệ có thể biến mất khỏi thống kê. Đừng biến `continue` thành phiên bản vòng lặp của `filter(Objects::nonNull)` che lỗi.

**Lỗi 3: dùng biến mutable dùng chung mà không cần thiết.** Tên biến nên có phạm vi ngắn, tránh lưu trạng thái từ phần tử trước; đặc biệt khi cân nhắc chuyển sang xử lý song song.

**Lỗi 4: gộp lỗi nghiệp vụ vào ngoại lệ quá rộng.** Chỉ `catch NumberFormatException` quanh bước parse khi đó là lỗi dự kiến. Không `catch (Exception ignored)` rồi tiếp tục để giấu bug.

**Lỗi 5: làm thay đổi hợp đồng đầu ra.** Ví dụ chuyển từ `Stream.toList()` sang trả `ArrayList` làm kết quả trở nên chỉnh sửa được. Nếu caller phụ thuộc tính bất biến, đó là thay đổi hành vi cần xem xét.

**Lỗi 6: thay phép toán ngắn mạch bằng duyệt toàn bộ.** Nếu Stream cũ dùng `findFirst` và việc xử lý tốn chi phí, vòng lặp phải cân nhắc `break` khi tìm thấy kết quả. Ngược lại, `findAny` trong parallel Stream không cam kết thứ tự như “phần tử đầu tiên”.

**Lỗi 7: giả định các điều kiện luôn độc lập.** Thứ tự kiểm tra đầu vào, parse, phân loại và định dạng có thể làm thay đổi lỗi được báo. Luôn có test cho dữ liệu sai nhiều quy tắc cùng lúc.

**Lỗi 8: tập trung vào phong cách thay vì hợp đồng.** Không có quy tắc “nếu có ba nhánh thì phải dùng `for`”. Cách tốt nhất là cách người đọc có thể xác định đúng ý định, luồng lỗi và kết quả mà không cần mô phỏng hàng loạt lambda lồng nhau.

## 12. Bài tập vận dụng

1. Bổ sung kênh `PARTNER` với nhãn `EXTERNAL`. Thêm kiểm thử cho kênh mới và xác nhận các kênh cũ không đổi.
2. Cho phép số lượng từ 1 đến 20, nhưng chỉ gắn `[BULK]` với số lượng từ 10 trở lên. Viết test cho các biên 9, 10, 20 và 21.
3. Trích toàn bộ xử lý một dòng thành `static Outcome transformOne(int line, String raw)`. So sánh vòng lặp `for` gọi helper đó với `IntStream.range(...).mapToObj(...)`. Hai phiên bản phải cho cùng danh sách `Outcome`.
4. Đổi chính sách `null` từ `Skipped` thành `Rejected`. Nêu rõ test nào phải đổi và giải thích vì sao đó là thay đổi nghiệp vụ, không đơn thuần refactor.
5. Nếu `raw` chứa dữ liệu nhạy cảm, thiết kế thông báo lỗi chỉ có chỉ số dòng, mã lỗi và lý do, tránh ghi nguyên văn đầu vào vào log.
6. Viết test cho đầu vào có nhiều lỗi cùng lúc, chẳng hạn `"OTHER,,abc"`, và xác định chính sách chọn lỗi đầu tiên có phù hợp hay cần trả danh sách lỗi.

Khi lựa chọn giữa Stream và vòng lặp, hãy tự hỏi: **Người đọc có dễ thấy từng nhánh, vị trí thoát, nguyên nhân thất bại và kết quả cuối cùng không?** Nếu phần lớn câu trả lời là “không”, hãy cân nhắc vòng lặp rõ ràng hoặc trích logic thành hàm nhỏ trước khi giữ pipeline.
