# Gộp dữ liệu bằng Gatherers.fold

## 1. Vấn đề: muốn gộp cả luồng thành một kết quả, nhưng vẫn ở trong pipeline

Trong **Java Stream API**, một pipeline thường bắt đầu từ `Collection.stream()`, áp dụng `filter`, `map` rồi kết thúc bằng `reduce` hoặc `collect`. Những thao tác kết thúc tạo ra một kết quả nhưng cũng **tiêu thụ Stream**: không thể gọi tiếp một thao tác trung gian trên chính Stream đã kết thúc.

Từ **Java 24**, API **Stream Gatherers** có thêm cách diễn đạt một phép tích lũy như **thao tác trung gian**:

```java
Stream<Integer> resultStream = Stream.of(2, 3, 4)
        .gather(Gatherers.fold(
                () -> 0,
                Integer::sum
        ));

System.out.println(resultStream.toList()); // [9]
```

`Gatherers.fold` nhận một giá trị bắt đầu và một hàm gộp phần tử mới vào kết quả đang xây dựng. Nó duyệt các phần tử, cập nhật trạng thái tích lũy và **phát đúng một giá trị tổng hợp khi hết đầu vào** nếu quá trình hoàn thành bình thường và downstream nhận kết quả.

```text
Stream nguồn:       2       3       4
                     \      |      /
                        Gatherers.fold
                  initial = 0
                  0 + 2 = 2
                  2 + 3 = 5
                  5 + 4 = 9
                          |
                        [9]
                          |
                map / filter / findFirst / toList
```

Kết quả `[9]` là **một Stream chứa một phần tử**, không phải một số nguyên trả trực tiếp từ `gather`. Vì vậy, ta có thể tiếp tục `map`, `filter` hoặc các Gatherer khác trước terminal operation.

Bài thuộc chương **Stream Gatherer** của module `JAVA_STREAM_API`. Bên cạnh `fold`, module còn đề cập tới pipeline lazy, `reduce`/`collect`, xử lý song song và các Gatherer có trạng thái; đây là bài học chuyên sâu về **phép gộp toàn bộ đầu vào theo thứ tự**.

**Mục tiêu:** sau bài này bạn có thể:

1. Đọc đúng chữ ký và hợp đồng của `Gatherers.fold`.
2. Phân biệt `initial`, `folder`, đầu ra duy nhất và cách xử lý luồng rỗng.
3. So sánh `fold` với `reduce`, `collect` và `Gatherers.scan`.
4. Viết phép gộp phụ thuộc thứ tự như tính số lần chuyển trạng thái.
5. Chọn accumulator bất biến hoặc mutable với vòng đời an toàn.
6. Kết hợp `fold` với các bước khác, xử lý nguồn hữu hạn, dừng sớm, I/O và giới hạn song song.

## 2. Phiên bản Java và vị trí API

**Stream Gatherers được hoàn thiện thành API chính thức trong JDK 24** (JEP 485). `Stream.gather` và `java.util.stream.Gatherers.fold` không có sẵn dưới dạng API chuẩn ở JDK 17/21. Gatherers từng xuất hiện ở giai đoạn preview trong các JDK trước đó; các ví dụ trong bài sử dụng **JDK 24+** và không cần `--enable-preview`.

Các import chính:

```java
import java.util.stream.Stream;
import java.util.stream.Gatherer;
import java.util.stream.Gatherers;
```

`Stream.gather(...)` nhận một `Gatherer` và trả về **Stream mới**. `Gatherers` là lớp cung cấp những Gatherer thường dùng, bao gồm `fold`, `scan`, `windowFixed`, `windowSliding` và `mapConcurrent`.

Ví dụ từ `List`:

```java
List<Integer> values = List.of(3, 5, 7);

int total = values.stream()
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .findFirst()
        .orElseThrow();

System.out.println(total); // 15
```

`findFirst` ở đây là terminal operation đọc **một kết quả cuối** mà `fold` phát ra. Nếu nghiệp vụ chỉ cần tổng số, `mapToInt(Integer::intValue).sum()` hoặc `reduce` thường ngắn và đơn giản hơn. Điểm đặc biệt của `fold` là **kết quả tích lũy vẫn đi qua một pipeline Stream trước khi kết thúc**.

## 3. Chữ ký và hợp đồng của Gatherers.fold

Chữ ký chính thức:

```java
public static <T, R> Gatherer<T, ?, R> fold(
        Supplier<R> initial,
        BiFunction<? super R, ? super T, ? extends R> folder
);
```

Ý nghĩa các thành phần:

| Thành phần | Kiểu | Vai trò |
| --- | --- | --- |
| `T` | Kiểu đầu vào | Mỗi phần tử được lấy từ Stream nguồn. |
| `R` | Kiểu tích lũy và đầu ra | Trạng thái tổng hợp đã được xây dựng đến thời điểm hiện tại. |
| `initial` | `Supplier<R>` | Cung cấp giá trị tích lũy ban đầu cho lượt đánh giá. |
| `folder` | `BiFunction<R, T, R>` về mặt ý nghĩa | Nhận kết quả tích lũy hiện tại và một phần tử mới, trả kết quả tích lũy tiếp theo. |
| Kết quả `fold` | `Gatherer<T, ?, R>` | Được đưa vào `Stream.gather(...)`, tạo `Stream<R>`. |

`fold` là **ordered, reduction-like gatherer**: nó xử lý phép tích lũy theo trình tự khi nguồn có encounter order, phù hợp với những phép gộp không có combiner dễ định nghĩa hoặc vốn phụ thuộc vào thứ tự.

Nếu không xảy ra lỗi trong quá trình xử lý, `fold` **chỉ phát một phần tử đầu ra**. Quan trọng hơn, khi đầu vào rỗng, kết quả phát ra chính là **giá trị được cung cấp bởi `initial`**.

```java
List<Integer> oneResult = Stream.of(1, 2, 3)
        .gather(Gatherers.fold(() -> 10, Integer::sum))
        .toList();

List<Integer> emptySourceResult = Stream.<Integer>empty()
        .gather(Gatherers.fold(() -> 10, Integer::sum))
        .toList();

System.out.println(oneResult);         // [16]
System.out.println(emptySourceResult);  // [10]
```

**Hãy phân biệt nguồn rỗng với Stream kết quả rỗng.** Sau khi `fold` hoàn tất trên một nguồn rỗng, nó vẫn phát giá trị bắt đầu. Đây là khác biệt rất quan trọng so với `Stream.reduce(BinaryOperator)` không có identity, vốn trả `Optional.empty()` trên nguồn rỗng.

Cả hai tham số `initial` và `folder` phải khác `null`; truyền một trong hai bằng `null` gây `NullPointerException` theo hợp đồng API.

## 4. Luồng dữ liệu bên trong một phép fold

Lấy ví dụ chuỗi số `[4, 2, 3]` và bộ gộp `(sum, value) -> sum + value`.

| Bước | Giá trị trước | Phần tử vào | Folder trả về | Đã phát xuống downstream? |
| --- | ---: | ---: | ---: | --- |
| Khởi tạo | — | — | `0` từ `initial` | Chưa |
| 1 | 0 | 4 | 4 | Chưa |
| 2 | 4 | 2 | 6 | Chưa |
| 3 | 6 | 3 | 9 | Chưa |
| Kết thúc | 9 | Hết nguồn | 9 | **Phát `9`** |

```java
List<Integer> output = Stream.of(4, 2, 3)
        .gather(Gatherers.fold(
                () -> 0,
                (sum, value) -> sum + value
        ))
        .toList();

System.out.println(output); // [9]
```

Đặc điểm quan trọng:

- `folder` chạy theo từng phần tử **khi terminal operation bắt đầu tiêu thụ pipeline**.
- `folder` không phát một phần tử xuống downstream sau mỗi lần cộng; nó cập nhật trạng thái nội bộ.
- Giá trị tích lũy cuối được phát sau khi không còn phần tử đầu vào để xử lý.
- Một `fold` có thể tổng hợp một nguồn lớn thành **một** giá trị mà không cần giữ một List chứa toàn bộ nguồn, tùy cấu trúc `R`.

`Gatherers.fold` **không phải `map`**: `map` thường biến mỗi phần tử đầu vào thành một đầu ra; `fold` có tính **many-to-one** và cần đi đến cuối nguồn để xác định giá trị cuối.

## 5. initial là Supplier, không phải một accumulator toàn cục

Tham số đầu tiên là `Supplier<R>` chứ không phải một đối tượng `R` được truyền trực tiếp:

```java
Gatherer<Integer, ?, Integer> foldSum =
        Gatherers.fold(() -> 0, Integer::sum);
```

Thiết kế này cho phép Gatherer lấy trạng thái ban đầu phù hợp với **lượt đánh giá**. `Supplier` đặc biệt quan trọng khi accumulator là một đối tượng mutable như `StringBuilder`, `StringJoiner` hoặc một class chứa nhiều trường.

### Đúng: tạo trạng thái mới

```java
Gatherer<String, ?, StringJoiner> joinerGatherer =
        Gatherers.fold(
                () -> new StringJoiner(" | "),
                (joiner, word) -> joiner.add(word)
        );
```

Mỗi lần tạo trạng thái, supplier trả một `StringJoiner` **mới**. `StringJoiner.add` cập nhật đối tượng và trả lại chính nó; vì thế folder phù hợp với chữ ký `BiFunction<R,T,R>`.

### Sai: trả về cùng trạng thái mutable đã dùng chung

```java
StringJoiner shared = new StringJoiner(" | ");

Gatherer<String, ?, StringJoiner> unsafe =
        Gatherers.fold(
                () -> shared,       // Không tạo đối tượng mới.
                (acc, word) -> acc.add(word)
        );
```

`shared` có thể giữ lại dữ liệu từ lần đánh giá trước, hoặc bị phần khác của ứng dụng sửa. Cách trên tạo ra một **điểm chia sẻ trạng thái** không cần thiết, khiến kết quả phụ thuộc lịch sử sử dụng object.

**Quy tắc:** nếu dùng accumulator mutable, hãy để `initial` tạo một instance mới; nếu dùng accumulator bất biến, có thể trả về một giá trị bắt đầu bất biến.

Không gắn tác dụng phụ nghiệp vụ vào `initial` rồi giả định supplier luôn được gọi đúng một số lần cố định. Hãy coi nó là cơ chế tạo trạng thái, không phải nơi gửi thông báo hay ghi dữ liệu.

## 6. Ví dụ đơn giản: tính tổng, tích và chuỗi kết quả

### Tổng số

```java
int total = Stream.of(1, 2, 3, 4)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .findFirst()
        .orElseThrow();

System.out.println(total); // 10
```

### Tích số

```java
long product = Stream.of(2L, 3L, 4L)
        .gather(Gatherers.fold(() -> 1L, (a, b) -> a * b))
        .findFirst()
        .orElseThrow();

System.out.println(product); // 24
```

Ở đây `0` là giá trị trung tính của phép cộng, `1` là giá trị trung tính của phép nhân. Việc đặt `initial` không phù hợp sẽ thay đổi kết quả:

```java
int withInitialTen = Stream.of(1, 2, 3)
        .gather(Gatherers.fold(() -> 10, Integer::sum))
        .findFirst()
        .orElseThrow();

System.out.println(withInitialTen); // 16, không phải 6
```

### Nối các token theo thứ tự

```java
import java.util.StringJoiner;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

String joined = Stream.of("an", "bình", "chi")
        .gather(Gatherers.<String, StringJoiner>fold(
                () -> new StringJoiner(" -> "),
                (builder, token) -> builder.add(token)
        ))
        .map(StringJoiner::toString)
        .findFirst()
        .orElseThrow();

System.out.println(joined); // an -> bình -> chi
```

Ví dụ nối chuỗi thể hiện một phép **gộp có thứ tự**: đổi thứ tự phần tử có thể đổi cả kết quả. Nếu chỉ cần nối chuỗi, `Collectors.joining(" -> ")` ở terminal operation thường ngắn hơn; dùng `fold` khi muốn chèn một phép gộp vào **giữa** các bước xử lý Stream.

## 7. So sánh fold, reduce, collect và scan

Các phương thức này đều có thể liên quan tới tích lũy, nhưng **vị trí trong pipeline** và **số đầu ra** khác nhau:

| Công cụ | Là thao tác nào? | Đầu ra trên `[2,3,4]` với tổng bắt đầu 0 | Khi nào phù hợp? |
| --- | --- | --- | --- |
| `reduce(0, Integer::sum)` | Terminal | Giá trị `9` | Chỉ cần một giá trị tổng và phép giảm đúng hợp đồng. |
| `collect(...)` | Terminal | Ví dụ một Collection hoặc một đối tượng tổng hợp | Cần mutable reduction, grouping hoặc collector có sẵn. |
| `gather(Gatherers.fold(...))` | Intermediate | Một Stream chứa `[9]` | Cần tích lũy theo thứ tự nhưng vẫn muốn nối tiếp pipeline. |
| `gather(Gatherers.scan(...))` | Intermediate | Stream `[2,5,9]` | Cần **mọi giá trị tích lũy trung gian**. |

### reduce

```java
int reduced = Stream.of(2, 3, 4)
        .reduce(0, Integer::sum);

System.out.println(reduced); // 9
```

`reduce` kết thúc Stream và trả kết quả trực tiếp. Trên Stream song song, identity, accumulator và combiner phải tương thích với hợp đồng reduction; những phép không có tính kết hợp có thể cho kết quả không mong muốn khi chia dữ liệu.

### fold

```java
List<Integer> folded = Stream.of(2, 3, 4)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .map(sum -> sum * 10)
        .toList();

System.out.println(folded); // [90]
```

`fold` **giữ kết quả trong thế giới Stream**: có thể `map` tiếp, kết hợp một Gatherer khác hoặc xử lý theo một API chỉ nhận Stream. Nếu không cần những bước nối tiếp, `reduce` thường dễ đọc hơn.

### scan

```java
List<Integer> scanned = Stream.of(2, 3, 4)
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();

System.out.println(scanned); // [2, 5, 9]
```

`scan` phát giá trị sau **mỗi lần** cập nhật, vì vậy tạo ba kết quả cho ba phần tử. `fold` không phát `2` hay `5` ra downstream, chỉ phát `9` cuối cùng.

Với nguồn rỗng, sự khác biệt rõ hơn:

```java
System.out.println(
        Stream.<Integer>empty()
                .gather(Gatherers.fold(() -> 0, Integer::sum))
                .toList()
); // [0]

System.out.println(
        Stream.<Integer>empty()
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList()
); // []

System.out.println(
        Stream.<Integer>empty()
                .reduce(Integer::sum)
); // Optional.empty
```

### collect

```java
long count = Stream.of("A", "B", "C")
        .collect(Collectors.counting());

System.out.println(count); // 3
```

`collect` là terminal operation. Nếu muốn tần suất theo khóa hoặc một cấu trúc nhiều nhóm, các collector như `groupingBy`, `toMap` và `summarizingLong` thường phù hợp hơn việc tự xây một fold riêng.

## 8. Phép gộp phụ thuộc thứ tự: đếm lần chuyển trạng thái

Một điểm mạnh của `fold` là xử lý dữ liệu **theo trình tự** và mang trạng thái từ phần tử trước sang phần tử sau. Bài toán: đếm số lần trạng thái của một thiết bị đổi trong chuỗi:

```text
NEW, NEW, RUNNING, RUNNING, DONE, RUNNING
         |               |      |
         +---- đổi ------>+-- đổi +-- đổi

Số lần chuyển trạng thái = 3
Trạng thái cuối = RUNNING
```

Muốn đếm số lần chuyển, phải nhớ **trạng thái ngay trước đó**. Chỉ `sum` hoặc `count` trên từng phần tử độc lập không đủ để hiểu cặp phần tử kề nhau.

Định nghĩa accumulator bất biến:

```java
record TransitionState(
        boolean started,
        String last,
        long changes
) {}
```

Cờ `started` phân biệt trạng thái ban đầu "chưa thấy phần tử" với một `last` không có giá trị. Điều này an toàn hơn dùng `last == null` làm dấu hiệu khởi tạo nếu dữ liệu nghiệp vụ cho phép khóa null.

Áp dụng `fold`:

```java
List<String> statuses = List.of(
        "NEW", "NEW", "RUNNING", "RUNNING", "DONE", "RUNNING"
);

TransitionState transitions = statuses.stream()
        .gather(Gatherers.<String, TransitionState>fold(
                () -> new TransitionState(false, null, 0),
                (state, current) -> {
                    if (!state.started()) {
                        return new TransitionState(true, current, 0);
                    }

                    long nextChanges = state.changes()
                            + (Objects.equals(state.last(), current) ? 0 : 1);
                    return new TransitionState(
                            true, current, nextChanges
                    );
                }
        ))
        .findFirst()
        .orElseThrow();

System.out.println(transitions.changes()); // 3
System.out.println(transitions.last());    // RUNNING
```

Mỗi bước trả một `TransitionState` **mới**, không sửa một trạng thái global. Đây là cách diễn đạt dễ suy luận cho một state nhỏ. Việc cấp phát một record mỗi bước có chi phí; nếu dữ liệu cực lớn và đo thấy tốn kém, có thể cân nhắc một accumulator mutable **được tạo mới riêng cho mỗi lần đánh giá**.

### Tại sao không dùng reduction song song với phép trừ hoặc so sánh cặp?

Một phép tính phụ thuộc vào **phần tử đứng ngay trước** thường không thể ghép hai kết quả từng phần bằng một phép cộng đơn giản nếu không mang theo thông tin về ranh giới. `fold` xử lý theo thứ tự cho phép viết logic trực tiếp. Nếu muốn một reduction có thể chia song song, phải thiết kế accumulator chứa đủ thông tin về **phần tử đầu/cuối và số chuyển trạng thái** để tạo combiner kết hợp đúng.

## 9. Gộp nhiều chỉ số nghiệp vụ trong một lần đi qua dữ liệu

Một dạng sử dụng khác của `fold` là tạo ra **một đối tượng tổng hợp** thay vì chỉ một số:

```java
record Invoice(String id, long amountCents, boolean paid) {}

record SalesSummary(
        long paidCount,
        long paidAmountCents,
        long unpaidCount
) {}
```

Với mỗi `Invoice`, accumulator tạo một `SalesSummary` mới:

```java
List<Invoice> invoices = List.of(
        new Invoice("I01", 1_200, true),
        new Invoice("I02", 700, false),
        new Invoice("I03", 400, true),
        new Invoice("I04", 300, false)
);

SalesSummary summary = invoices.stream()
        .gather(Gatherers.<Invoice, SalesSummary>fold(
                () -> new SalesSummary(0, 0, 0),
                (state, invoice) -> {
                    if (invoice.paid()) {
                        return new SalesSummary(
                                state.paidCount() + 1,
                                Math.addExact(
                                        state.paidAmountCents(),
                                        invoice.amountCents()
                                ),
                                state.unpaidCount()
                        );
                    }
                    return new SalesSummary(
                            state.paidCount(),
                            state.paidAmountCents(),
                            state.unpaidCount() + 1
                    );
                }
        ))
        .findFirst()
        .orElseThrow();

System.out.println(summary);
// SalesSummary[paidCount=2, paidAmountCents=1600, unpaidCount=2]
```

`Math.addExact` phát hiện tràn số khi cộng tiền dạng `long`; các bộ đếm cũng có thể cần bảo vệ tràn khi dữ liệu cực lớn. Ví dụ xem số tiền ở **đơn vị nhỏ nhất** (cent) và giả định đầu vào đã được validate.

Phương án dùng record bảo đảm **accumulator đầu ra bất biến nông**: các trường đều là số nguyên thủy. Khi dữ liệu có List/Map mutable bên trong, một record không tự biến mọi thành phần thành bất biến sâu.

Nếu chỉ cần tổng tiền, `mapToLong(Invoice::amountCents).sum()` (hoặc cộng có kiểm soát overflow) gọn hơn. `fold` hợp lý hơn khi **nhiều thông tin trạng thái tương tác nhau**, hoặc kết quả phải được chuyển tiếp qua các bước Stream tiếp theo.

## 10. Accumulator mutable: khi nào dùng và cần tránh điều gì?

Một `folder` có thể **sửa một đối tượng tích lũy rồi trả về chính nó**:

```java
String joined = Stream.of("A", "B", "C")
        .gather(Gatherers.<String, StringJoiner>fold(
                () -> new StringJoiner(","),
                (joiner, part) -> joiner.add(part)
        ))
        .map(StringJoiner::toString)
        .findFirst()
        .orElseThrow();

System.out.println(joined); // A,B,C
```

Đây là accumulator có trạng thái **nội bộ** của một lần đánh giá, không phải một `StringJoiner` được nhiều pipeline cùng sửa. Với chuỗi dài, cách này thường tránh được nhiều đối tượng String trung gian so với:

```java
String result = Stream.of("A", "B", "C")
        .gather(Gatherers.fold(
                () -> "",
                (text, part) -> text.isEmpty() ? part : text + "," + part
        ))
        .findFirst()
        .orElseThrow();
```

Phép nối String theo từng bước có thể tạo nhiều bản sao, khiến chi phí tăng đáng kể với chuỗi dài. Tuy nhiên, với bài toán chỉ nối chuỗi, `Collectors.joining(",")` vẫn là lựa chọn tiêu chuẩn đơn giản hơn.

### Rủi ro khi xuất bản accumulator mutable

`fold` phát chính giá trị `R` cuối cùng. Nếu `R` là một `ArrayList`, `StringBuilder` hoặc Map mutable và được đưa trực tiếp ra ngoài, người nhận có thể thay đổi nó. Nếu yêu cầu kết quả không cho sửa, chuyển trạng thái thành một giá trị bất biến **trước khi công bố**:

```java
List<String> snapshot = Stream.of("A", "B", "C")
        .gather(Gatherers.<String, ArrayList<String>>fold(
                ArrayList::new,
                (list, item) -> {
                    list.add(item);
                    return list;
                }
        ))
        .map(List::copyOf)
        .findFirst()
        .orElseThrow();

System.out.println(snapshot); // [A, B, C]
// snapshot.add("D"); // UnsupportedOperationException
```

`List.copyOf` tạo List không cho sửa cấu trúc và **từ chối phần tử null**. Đây là bản sao nông: nếu phần tử là object mutable, nó vẫn có thể bị đổi từ nơi khác.

**Không nên chọn fold để gom List nếu chỉ muốn một List tất cả phần tử.** `Stream.toList()` hoặc `Collectors.toCollection(ArrayList::new)` là giải pháp rõ ràng hơn, còn có cơ hội tận dụng đặc tính xử lý song song của phép thu thập chuẩn.

## 11. Kết hợp fold với các thao tác Stream khác

Vì `fold` là **Gatherer trung gian**, có thể ghép với `filter`, `map`, `windowFixed` và các bước hậu xử lý. Cần phân biệt **thao tác trước fold** với **thao tác sau fold**.

### Lọc trước khi gộp

```java
List<Integer> totals = Stream.of(1, 2, 3, 4, 5, 6)
        .filter(n -> n % 2 == 0)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

System.out.println(totals); // [12] từ 2 + 4 + 6
```

`filter` chạy trên **các phần tử gốc**, rồi fold gộp những phần tử còn lại.

### Lọc sau khi gộp

```java
List<Integer> acceptedTotal = Stream.of(1, 2, 3)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .filter(sum -> sum >= 10)
        .toList();

System.out.println(acceptedTotal); // []
```

Ở đây `filter` chỉ thấy **một số tổng** là `6`, không lọc từng phần tử nguồn. Nếu điều kiện là "tổng ít nhất 10" thì đặt sau fold đúng; nếu điều kiện là "chỉ cộng số ít nhất 10" thì phải lọc trước.

### Gộp sau khi chia cửa sổ

`Gatherers.windowFixed` tạo các cửa sổ liên tiếp, rồi `fold` có thể tích lũy một đại lượng từ **danh sách cửa sổ**:

```java
List<Integer> totalWindowSizes = Stream.of(1, 2, 3, 4, 5, 6)
        .gather(Gatherers.windowFixed(3))
        .gather(Gatherers.<List<Integer>, Integer>fold(
                () -> 0,
                (count, window) -> count + window.size()
        ))
        .toList();

System.out.println(totalWindowSizes); // [6]
```

Đầu vào của fold lúc này không còn là `Integer` mà là `List<Integer>`. Cần đọc kỹ kiểu dữ liệu ở **ranh giới mỗi bước** trong pipeline.

### scan rồi fold

```java
List<Integer> sumOfPrefixes = Stream.of(1, 2, 3)
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

System.out.println(sumOfPrefixes); // [10] = 1 + 3 + 6
```

Đây là **tổng của các tổng tiền tố**, không phải tổng ban đầu `1 + 2 + 3 = 6`. Khi xếp nhiều Gatherer, mỗi bước nhận **đầu ra của bước trước**, nên việc ghép đúng kiểu chưa chắc đã đúng yêu cầu nghiệp vụ.

## 12. Dừng sớm, nguồn vô hạn và hiệu ứng lên pipeline

`Gatherers.fold` chỉ biết kết quả cuối cùng sau khi **tiêu thụ hết đầu vào được giao**. Bởi vậy:

```java
int total = Stream.of(1, 2, 3, 4)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .findFirst()
        .orElseThrow();

System.out.println(total); // 10
```

Mặc dù terminal operation là `findFirst()`, nó **không thể lấy kết quả của fold sau phần tử đầu**. Đầu ra đầu tiên của fold chính là kết quả được phát khi tích lũy hoàn tất.

### limit trước fold: giới hạn số phần tử đầu vào

```java
List<Integer> limitedInput = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

System.out.println(limitedInput); // [15]
```

`limit(5)` nằm **trước** fold, nên Gatherer chỉ nhìn thấy 5 phần tử đầu. Đây là một cách biến nguồn vô hạn thành một phần hữu hạn có thể gộp.

### limit sau fold: giới hạn đầu ra, không giới hạn dữ liệu tích lũy

```java
List<Integer> limitedOutput = Stream.of(1, 2, 3, 4, 5)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .limit(1)
        .toList();

System.out.println(limitedOutput); // [15]
```

`limit(1)` chỉ áp dụng lên **Stream kết quả sau fold**, vốn có tối đa một phần tử. Nó không cắt đầu vào thành một phần tử.

**Cảnh báo nguồn vô hạn:** nếu nguồn không bao giờ kết thúc, một `fold` thông thường **không thể phát tổng cuối**, vì không có thời điểm "đã hết đầu vào". Những pipeline như sau không nên được dùng nếu thực sự muốn nhận kết quả:

```java
// Không chạy thử nếu không có điều kiện dừng:
// Stream.iterate(1L, n -> n + 1)
//         .gather(Gatherers.fold(() -> 0L, Long::sum))
//         .findFirst();
```

Với dữ liệu vô hạn hoặc dữ liệu thời gian thực, hãy chọn **`scan` cho kết quả tích lũy từng bước**, hoặc đóng dữ liệu thành cửa sổ hữu hạn rồi tổng hợp theo từng cửa sổ. Không đợi một kết quả "cuối cùng" của nguồn không có điểm kết thúc.

## 13. Thứ tự nguồn và xử lý song song

Tài liệu API mô tả `fold` như một phép gộp **ordered** và **reduction-like**, phù hợp cho trường hợp phép gộp phụ thuộc vào trình tự hoặc không có combiner rõ ràng.

### Có encounter order

```java
String text = List.of("A", "B", "C")
        .parallelStream()
        .gather(Gatherers.fold(
                () -> "",
                (acc, part) -> acc + part
        ))
        .findFirst()
        .orElseThrow();

System.out.println(text); // ABC
```

Nguồn `List` có encounter order; dù upstream có thể được xử lý song song, bước fold phải tôn trọng **ngữ nghĩa tích lũy theo thứ tự**. `fold` không phải cách để biến một phép gộp vốn cần tuần tự thành phép gộp hiệu quả song song.

### Không có encounter order

```java
Set<String> set = new HashSet<>(List.of("A", "B", "C"));

String text = set.stream()
        .gather(Gatherers.fold(
                () -> "",
                (acc, part) -> acc + part
        ))
        .findFirst()
        .orElseThrow();

// Không khẳng định kết quả là "ABC".
```

`HashSet` không cam kết encounter order, nên phép nối chuỗi không có thứ tự nghiệp vụ ổn định. Nếu thứ tự quan trọng, dùng nguồn ordered hoặc `sorted()` với comparator phù hợp **trước fold**:

```java
String sortedText = set.stream()
        .sorted()
        .gather(Gatherers.fold(() -> "", (acc, part) -> acc + part))
        .findFirst()
        .orElseThrow();

System.out.println(sortedText); // ABC
```

### Fold có combiner không?

`Gatherers.fold` không cung cấp combiner để chia và ghép phép tích lũy theo nhiều phần nguồn như một phép reduction song song chuẩn. Khi một Gatherer không có combiner, **giai đoạn gather đó không được thực thi song song theo cách chia/gộp trạng thái**; những phần khác của pipeline có thể có chiến lược thực thi riêng. Đừng suy luận rằng thêm `parallel()` sẽ làm chính `fold` nhanh hơn.

Nếu phép tính là một phép tổng, đếm hoặc cực trị **có kết hợp**, `reduce`, primitive `sum` hoặc collector chuẩn có thể phù hợp hơn với parallel Stream. Nếu phép tính phụ thuộc trạng thái ngay trước đó, `fold` tuần tự thường diễn đạt đúng hơn một combiner được viết vội.

## 14. Non-interference, lỗi số học và null

### Không sửa nguồn trong folder

`folder` nên tính trạng thái mới từ giá trị tích lũy và phần tử hiện tại, không sửa collection đang được duyệt:

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

// SAI: can thiệp chính nguồn khi Stream đang duyệt.
// source.stream().gather(Gatherers.fold(
//         () -> 0,
//         (acc, item) -> {
//             source.add(item);
//             return acc + item;
//         }
// )).toList();
```

Thao tác trên có thể làm nguồn sai cấu trúc hoặc gây `ConcurrentModificationException`. Tách xử lý dữ liệu khỏi cập nhật nguồn hoặc chuẩn bị một snapshot ổn định trước khi tính.

### Tràn số

`Integer::sum` và `Long::sum` không báo lỗi tràn theo cách bạn có thể dựa vào cho nghiệp vụ tài chính. Khi cần phát hiện overflow:

```java
long safeSum = Stream.of(1_000_000L, 2_000_000L)
        .gather(Gatherers.fold(() -> 0L, Math::addExact))
        .findFirst()
        .orElseThrow();

System.out.println(safeSum); // 3000000
```

Nếu vượt phạm vi `long`, `Math.addExact` ném `ArithmeticException`. Với tiền tệ thập phân hoặc tính toán cần độ chính xác cao, cân nhắc `BigDecimal` và quy tắc làm tròn rõ ràng.

### Null

Hai tham số hàm `initial` và `folder` không được null. Với **phần tử đầu vào null**, folder phải có chính sách cụ thể; một method reference như `Integer::sum` sẽ không thể xử lý null.

```java
List<Integer> nullable = Arrays.asList(1, null, 3);

int nonNullSum = nullable.stream()
        .filter(Objects::nonNull)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .findFirst()
        .orElseThrow();

System.out.println(nonNullSum); // 4
```

Với **kết quả tích lũy null**, downstream như `findFirst` không thể đóng gói null vào `Optional` và có thể ném `NullPointerException`. Thiết kế trạng thái kết quả không-null, hoặc dùng `Optional`/đối tượng giá trị để biểu diễn thiếu dữ liệu.

### Ngoại lệ trong folder

Nếu `initial`, `folder` hoặc bước downstream ném ngoại lệ, terminal operation có thể thất bại; `fold` không tự rollback những tác dụng phụ đã xảy ra trong hàm. Vì thế tránh gửi email, ghi dữ liệu hoặc thanh toán bên trong folder chỉ để tận dụng vòng lặp.

## 15. Ví dụ Java 24+ hoàn chỉnh: tổng hợp đơn hàng và chuyển trạng thái

Ví dụ sau dùng `fold` để tính một đối tượng báo cáo bất biến và một phép gộp **phụ thuộc thứ tự**. Chương trình dùng Java 24+ và không cần thư viện ngoài.

Lưu dưới tên `FoldGathererDemo.java`:

```java
import java.util.List;
import java.util.Objects;
import java.util.StringJoiner;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class FoldGathererDemo {
    record Invoice(String id, long amountCents, boolean paid) {
        Invoice {
            Objects.requireNonNull(id, "id");
            if (amountCents < 0) {
                throw new IllegalArgumentException("amountCents < 0");
            }
        }
    }

    record SalesSummary(
            long paidCount,
            long paidAmountCents,
            long unpaidCount
    ) {}

    record TransitionState(
            boolean started,
            String last,
            long changes
    ) {}

    static SalesSummary summarize(List<Invoice> invoices) {
        return invoices.stream()
                .gather(Gatherers.<Invoice, SalesSummary>fold(
                        () -> new SalesSummary(0L, 0L, 0L),
                        (state, invoice) -> {
                            if (invoice.paid()) {
                                return new SalesSummary(
                                        Math.addExact(state.paidCount(), 1L),
                                        Math.addExact(
                                                state.paidAmountCents(),
                                                invoice.amountCents()
                                        ),
                                        state.unpaidCount()
                                );
                            }
                            return new SalesSummary(
                                    state.paidCount(),
                                    state.paidAmountCents(),
                                    Math.addExact(state.unpaidCount(), 1L)
                            );
                        }
                ))
                .findFirst()
                .orElseThrow();
    }

    static TransitionState countTransitions(List<String> statuses) {
        return statuses.stream()
                .gather(Gatherers.<String, TransitionState>fold(
                        () -> new TransitionState(false, null, 0L),
                        (state, current) -> {
                            Objects.requireNonNull(current, "current");
                            if (!state.started()) {
                                return new TransitionState(
                                        true, current, 0L
                                );
                            }
                            boolean changed = !Objects.equals(
                                    state.last(), current
                            );
                            return new TransitionState(
                                    true,
                                    current,
                                    Math.addExact(
                                            state.changes(),
                                            changed ? 1L : 0L
                                    )
                            );
                        }
                ))
                .findFirst()
                .orElseThrow();
    }

    public static void main(String[] args) {
        List<Invoice> invoices = List.of(
                new Invoice("I01", 1_200L, true),
                new Invoice("I02", 700L, false),
                new Invoice("I03", 400L, true),
                new Invoice("I04", 300L, false)
        );

        SalesSummary summary = summarize(invoices);
        SalesSummary emptySummary = summarize(List.of());

        List<String> statuses = List.of(
                "NEW", "NEW",
                "RUNNING", "RUNNING",
                "DONE", "RUNNING"
        );
        TransitionState transitions = countTransitions(statuses);
        TransitionState emptyTransitions = countTransitions(List.of());

        List<Integer> folded = Stream.of(2, 3, 4)
                .gather(Gatherers.fold(() -> 0, Integer::sum))
                .toList();

        List<Integer> scanned = Stream.of(2, 3, 4)
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList();

        String joined = statuses.stream()
                .gather(Gatherers.<String, StringJoiner>fold(
                        () -> new StringJoiner(" -> "),
                        (builder, item) -> builder.add(item)
                ))
                .map(StringJoiner::toString)
                .findFirst()
                .orElseThrow();

        if (!summary.equals(new SalesSummary(2, 1_600L, 2))) {
            throw new AssertionError("Sai tổng hợp đơn hàng");
        }
        if (!emptySummary.equals(new SalesSummary(0, 0, 0))) {
            throw new AssertionError("Fold nguồn rỗng không trả initial");
        }
        if (!transitions.equals(
                new TransitionState(true, "RUNNING", 3))) {
            throw new AssertionError("Sai số lần đổi trạng thái");
        }
        if (!emptyTransitions.equals(
                new TransitionState(false, null, 0))) {
            throw new AssertionError("Sai trạng thái trên nguồn rỗng");
        }
        if (!folded.equals(List.of(9))
                || !scanned.equals(List.of(2, 5, 9))) {
            throw new AssertionError("Sai ngữ nghĩa fold/scan");
        }

        System.out.println("Summary: " + summary);
        // Summary: SalesSummary[paidCount=2, paidAmountCents=1600,
        //                       unpaidCount=2]
        System.out.println("Transitions: " + transitions);
        // Transitions: TransitionState[started=true, last=RUNNING,
        //                              changes=3]
        System.out.println("Fold: " + folded); // [9]
        System.out.println("Scan: " + scanned); // [2, 5, 9]
        System.out.println("Trace: " + joined);
        System.out.println("PASS");
    }
}
```

Biên dịch và chạy:

```text
javac FoldGathererDemo.java
java FoldGathererDemo
```

### Những gì ví dụ chứng minh

1. **Khởi tạo đúng:** `SalesSummary` và `TransitionState` có giá trị bắt đầu rõ ràng.
2. **Nguồn rỗng:** `fold` vẫn trả một kết quả `initial`, không bắt buộc `orElseThrow` thất bại.
3. **Folder có trạng thái nhưng không ghi ra ngoài:** mỗi lần xử lý tạo record tổng hợp mới.
4. **Thứ tự có ý nghĩa:** `countTransitions` xét trạng thái ngay trước, khác phép đếm trạng thái toàn cục.
5. **Một đầu ra so với nhiều đầu ra:** `folded` là `[9]`, `scanned` là `[2,5,9]`.
6. **Mutable accumulator riêng:** `StringJoiner` được tạo bởi supplier và biến thành `String` trước khi trả kết quả.
7. **Kiểm tra xác định:** các điều kiện `if` + `throw` phát hiện sai khác mà không phụ thuộc cờ `-ea` của JVM.

Không chạy Gradle hoặc vòng Content QA trong bước viết bài. Khi triển khai thật, hãy biên dịch với **JDK 24+**, bổ sung test của dự án và kiểm tra yêu cầu xử lý dữ liệu riêng.

## 16. Bài tập thực hành và lời giải tham khảo

### Bài 1 — Fold tổng và trường hợp nguồn rỗng

**Dữ liệu:** `[5, 10, 20]`. Hãy gộp thành một tổng bằng `Gatherers.fold`, rồi thử với `Stream.empty()`. Kết quả cần là `[35]` và `[0]`.

```java
List<Integer> sums = Stream.of(5, 10, 20)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

List<Integer> emptySums = Stream.<Integer>empty()
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

System.out.println(sums);      // [35]
System.out.println(emptySums); // [0]
```

### Bài 2 — Thống kê count và sum trong một accumulator

**Dữ liệu:** `[3, 7, 10]`. Hãy tạo một record có `count` và `sum`, sau đó dùng fold.

```java
record CountSum(long count, long sum) {}

CountSum data = Stream.of(3, 7, 10)
        .gather(Gatherers.<Integer, CountSum>fold(
                () -> new CountSum(0, 0),
                (state, n) -> new CountSum(
                        state.count() + 1,
                        state.sum() + n
                )
        ))
        .findFirst()
        .orElseThrow();

System.out.println(data); // CountSum[count=3, sum=20]
```

**Mở rộng:** khi `count==0`, không thể định nghĩa trung bình bằng `sum/count`. Hãy trả `OptionalDouble.empty()` hoặc một biểu diễn "không có dữ liệu" rõ ràng.

### Bài 3 — Phân biệt fold và scan

**Yêu cầu:** với `[4, 1, 5]`, dự đoán đầu ra của hai pipeline sau:

```java
List<Integer> a = Stream.of(4, 1, 5)
        .gather(Gatherers.fold(() -> 0, Integer::sum))
        .toList();

List<Integer> b = Stream.of(4, 1, 5)
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();
```

**Đáp án:** `a = [10]`, `b = [4, 5, 10]`. `fold` phát một tổng cuối; `scan` phát các tổng tiền tố.

### Bài 4 — Đếm thay đổi giá trị liên tiếp

**Dữ liệu:** `[A, A, B, A, A, C]`. Hãy đếm số lần đổi giá trị, không phải số giá trị khác nhau.

```java
List<String> values = List.of("A", "A", "B", "A", "A", "C");

TransitionState s = countTransitions(values);

System.out.println(s.changes()); // 3
System.out.println(s.last());    // C
```

**Giải thích:** có ba lần đổi `A → B`, `B → A`, `A → C`. Nếu dùng `distinct().count()` thì chỉ có ba giá trị khác nhau, một đại lượng **khác** với số lần chuyển. Nếu cần bảo toàn thứ tự lịch sử, không gọi `unordered()` hoặc sắp xếp trước fold.

### Bài 5 — Dừng nguồn trước khi gộp

**Yêu cầu:** tạo một Stream số tự nhiên sinh vô hạn, chỉ cộng **10 phần tử đầu**. Vì sao `limit(10)` phải nằm trước `gather(fold(...))`?

```java
long tenNumbers = Stream.iterate(1L, n -> n + 1)
        .limit(10)
        .gather(Gatherers.fold(() -> 0L, Math::addExact))
        .findFirst()
        .orElseThrow();

System.out.println(tenNumbers); // 55
```

`limit(10)` làm **nguồn của fold hữu hạn**. Đặt `limit(1)` sau fold chỉ giới hạn số đầu ra của Gatherer, không giúp nó tìm thấy cuối một nguồn vô hạn.

### Bài 6 — Fold mutable: lỗi chia sẻ trạng thái

**Yêu cầu:** giải thích vì sao `() -> sharedList` (với `sharedList` tạo bên ngoài) không phải supplier tốt cho `fold`. Hãy sửa để trả về một List snapshot không cho sửa.

```java
List<String> safe = Stream.of("X", "Y", "Z")
        .gather(Gatherers.<String, ArrayList<String>>fold(
                ArrayList::new,
                (acc, value) -> {
                    acc.add(value);
                    return acc;
                }
        ))
        .map(List::copyOf)
        .findFirst()
        .orElseThrow();

System.out.println(safe); // [X, Y, Z]
```

`ArrayList::new` cấp bộ đệm riêng cho lần đánh giá, còn `List.copyOf` tạo snapshot không cho sửa trước khi công bố. Nếu chỉ cần List này, có thể thay tất cả bằng `Stream.of("X", "Y", "Z").toList()`; bài tập nhằm luyện hợp đồng của `initial` và `folder`.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Không biên dịch được `Stream.gather` trên JDK 17/21 | Gatherers chưa là API chuẩn ở phiên bản đó | Dùng JDK 24+ hoặc giải pháp `reduce`/`collect` tương thích. |
| Mong fold trả trực tiếp một `R` | `gather` là intermediate operation, trả `Stream<R>` | Tiêu thụ bằng `findFirst`, `toList` hoặc terminal phù hợp. |
| Kỳ vọng thấy mọi tổng tiền tố | Nhầm `fold` với `scan` | Dùng `Gatherers.scan` nếu cần kết quả sau từng phần tử. |
| Nguồn rỗng lại thu được một phần tử | `fold` phát giá trị `initial` trên nguồn rỗng | Định nghĩa giá trị bắt đầu và phân biệt với `reduce(BinaryOperator)`. |
| `findFirst` sau fold không dừng ở phần tử đầu | Fold chưa phát kết quả cho tới khi hết nguồn | Giới hạn đầu vào bằng `limit`/`takeWhile` **trước** fold. |
| Fold trên nguồn vô hạn không có đầu ra | Không bao giờ có điểm kết thúc để phát tổng | Dùng `scan` hoặc phân đoạn/cửa sổ hữu hạn. |
| Kết quả bị mang từ lượt chạy trước | `initial` trả về accumulator mutable dùng chung | Tạo một instance mới bằng supplier. |
| Kết quả có thứ tự sai | Nguồn unordered hoặc gọi `unordered()` trước fold | Xác lập encounter order và comparator đúng nghiệp vụ. |
| Thêm `parallel()` nhưng fold không nhanh hơn | Fold không có combiner chia/gộp trạng thái | Dùng reduction/collector song song khi phép tính cho phép. |
| Tràn số khi cộng nhiều giá trị | Dùng `Integer::sum`/`Long::sum` vượt phạm vi | Dùng `Math.addExact` hoặc kiểu số phù hợp. |
| `NullPointerException` với `findFirst` | Kết quả fold null hoặc folder không xử lý phần tử null | Dùng accumulator không-null và chính sách xử lý null rõ ràng. |
| Side effect trong folder gây dữ liệu sai | Sửa nguồn/biến bên ngoài trong quá trình tính | Giữ folder thuần về input và state nội bộ, không can thiệp nguồn. |
| Kết quả mutable bị sửa sau khi trả | Công bố chính accumulator có thể thay đổi | Chuyển thành record bất biến hoặc snapshot phù hợp. |
| Dùng fold để giải bài toán nhóm phức tạp | Không tận dụng collector chuyên dụng | Cân nhắc `groupingBy`, `toMap`, `summarizingLong`. |

## 18. Checklist chọn và triển khai Gatherers.fold

1. **JDK:** môi trường có Java 24+ và hỗ trợ `Gatherers.fold` chính thức không?
2. **Bài toán:** cần một tổng hợp cuối, không phải danh sách mọi giá trị trung gian?
3. **Pipeline:** có lợi ích khi giữ phép gộp ở dạng intermediate operation trước terminal khác không?
4. **Giá trị bắt đầu:** `initial` có thể hiện đúng trạng thái khi nguồn rỗng không?
5. **Hàm gộp:** `folder` nhận đúng kiểu `R` và `T`, trả đúng `R` không?
6. **Trạng thái:** nếu mutable, supplier có tạo instance mới, không chia sẻ global không?
7. **Bất biến:** có cần snapshot/deep-copy trước khi công bố kết quả không?
8. **Thứ tự:** phép gộp có phụ thuộc encounter order không? Nguồn đã có thứ tự nghiệp vụ chưa?
9. **Song song:** đã tránh kỳ vọng `fold` tự có combiner song song chưa?
10. **Dừng sớm:** `limit`/`takeWhile` áp dụng **trước fold** nếu cần giới hạn nguồn?
11. **Nguồn vô hạn:** đã có điều kiện kết thúc hoặc đã chọn `scan`/cửa sổ thay thế?
12. **Null:** nguồn, giá trị đầu ra và folder có chính sách null rõ ràng không?
13. **Số học:** đã xét overflow, sai số và quy tắc làm tròn chưa?
14. **I/O:** Stream dựa vào tệp/connection có được đóng bằng `try-with-resources` không?
15. **Kiểm thử:** đã kiểm nguồn rỗng, một phần tử, nhiều phần tử, thứ tự khác nhau và kết quả bất biến chưa?

## Ghi nhớ

**`Gatherers.fold(initial, folder)`** là Gatherer tích lũy dữ liệu **theo thứ tự** và phát **một giá trị tổng hợp khi đầu vào kết thúc**. `initial` cung cấp trạng thái ban đầu, `folder` nhận giá trị tích lũy và một phần tử mới rồi trả giá trị tích lũy tiếp theo. Ngay cả khi nguồn rỗng, fold vẫn phát giá trị từ `initial`.

`fold` là **thao tác trung gian** nên kết quả vẫn là `Stream<R>`, khác với terminal `reduce`/`collect`. Nó cũng khác `scan`, vốn phát **mỗi giá trị tích lũy trung gian**. `fold` phù hợp khi phép gộp có phụ thuộc thứ tự, chẳng hạn đếm chuyển trạng thái, nhưng không phải công cụ tự động tăng tốc xử lý song song.

Thiết kế supplier tạo trạng thái đúng vòng đời, giữ folder không can thiệp nguồn, tránh công bố accumulator mutable ngoài ý muốn, xác định encounter order và bảo đảm đầu vào có điểm kết thúc. Với tổng/đếm/nhóm đơn giản chỉ cần kết quả cuối, ưu tiên `sum`, `reduce` hoặc `collect` khi chúng diễn đạt trực tiếp hơn.

### Tài liệu API

- [Oracle JDK 24 — Gatherers.fold](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html)
- [Oracle JDK 24 — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html)
