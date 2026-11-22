# Hợp đồng kết hợp của hàm hợp nhất khi xử lý song song

## 1. Bối cảnh: Collector bản đồ trong Java 10

`Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction)`, được bổ sung từ **Java 10**, gom phần tử của một `Stream` thành một **`Map` không thể sửa đổi**. Khi nhiều phần tử nguồn tạo ra **cùng một key**, `mergeFunction` quyết định cách kết hợp những value xung đột.

Với Stream tuần tự, ta dễ hình dung các value được xử lý lần lượt. Nhưng **parallel Stream** có thể phân chia dữ liệu thành nhiều nhánh, tích lũy các map trung gian rồi hợp nhất các nhánh. Nếu `mergeFunction` phụ thuộc cách nhóm phép tính, số thread hoặc một trạng thái mutable bên ngoài, kết quả có thể khác nhau giữa cách chạy tuần tự và song song.

**Ý chính:** Để kết quả gộp value theo từng key tương thích với hợp đồng của `Collector`, hàm gộp nên **kết hợp được** (*associative*), **không phụ thuộc trạng thái ngoài**, và thỏa chính sách về thứ tự, null, miền giá trị của ứng dụng.

Sau bài này, bạn sẽ:

- Hiểu chữ ký `toUnmodifiableMap` ba đối số và vai trò `BinaryOperator<U>`.
- Phân biệt `mergeFunction` xử lý value cùng key với `Collector.combiner` hợp nhất **hai container tích lũy**.
- Kiểm tra tính **kết hợp**, phân biệt với tính **giao hoán** (*commutativity*).
- Giải thích vì sao phép trừ, trung bình từng đôi, cộng `double` có thể không bảo đảm kết quả khi chia nhiều partition.
- Viết merger thuần, an toàn với parallel stream; chọn `Integer::sum`, `Integer::max`, `BigDecimal::add` đúng hoàn cảnh.
- Hiểu `Map.merge`, xử lý duplicate key, null và các giới hạn của unmodifiable map.
- Chạy chương trình Java 17+ có stdout chính xác và những phép thử kiểm tra hợp đồng.

Bài chỉ dùng kiến thức **vẫn áp dụng trong Java hiện đại**, không sử dụng API lỗi thời hoặc chi tiết triển khai JDK làm quy tắc ngôn ngữ.

## 2. Cú pháp chính xác của collector

Chữ ký tổng quát:

~~~java
public static <T, K, U> Collector<T, ?, Map<K, U>> toUnmodifiableMap(
        Function<? super T, ? extends K> keyMapper,
        Function<? super T, ? extends U> valueMapper,
        BinaryOperator<U> mergeFunction)
~~~

| Đối số | Chức năng | Ví dụ |
| --- | --- | --- |
| `keyMapper` | Tạo key kiểu `K` từ mỗi phần tử nguồn `T`. | `Sale::category` |
| `valueMapper` | Tạo value kiểu `U` từ phần tử nguồn. | `Sale::quantity` |
| `mergeFunction` | Kết hợp **hai value cùng key**, trả về một value kiểu `U`. | `Integer::sum` |

Ví dụ minh họa đặt `record` ở vị trí định nghĩa kiểu hợp lệ:

~~~java
record Sale(String category, int quantity) {}

// Trong một phương thức:
var sales = java.util.List.of(
        new Sale("books", 4),
        new Sale("games", 8),
        new Sale("books", 3)
);

var totals = sales.stream().collect(
        java.util.stream.Collectors.toUnmodifiableMap(
                Sale::category, Sale::quantity, Integer::sum
        )
);

System.out.println(totals.get("books")); // 7
System.out.println(totals.get("games")); // 8
~~~

`"books"` xuất hiện hai lần, nên hai value `4` và `3` được gộp bằng `Integer::sum`.

Đừng nhầm hai overload:

~~~java
// Bản 2 tham số: key trùng sẽ gây IllegalStateException.
Collectors.toUnmodifiableMap(keyMapper, valueMapper);

// Bản 3 tham số: key trùng được xử lý bằng mergeFunction.
Collectors.toUnmodifiableMap(keyMapper, valueMapper, mergeFunction);
~~~

Trong cả hai trường hợp, kết quả cuối là `Map` không thể sửa đổi qua API của chính nó. Việc Map không sửa được **không chứng minh** merger đã đáp ứng tính kết hợp.

## 3. Vì sao parallel reduction cần hợp nhất kết quả từng phần?

### 3.1. Tích lũy tuần tự

Giả sử ba giao dịch cùng key `"books"` có value `10`, `5`, `2`. Một quá trình tuần tự có thể hình dung:

~~~text
Map rỗng
  nhận (books,10)  -> books = 10
  nhận (books,5)   -> books = merge(10, 5)
  nhận (books,2)   -> books = merge(merge(10,5),2)
~~~

Điểm khác biệt là parallel reduction **không nhất thiết** gộp đúng theo cách đặt ngoặc của ví dụ tuần tự này.

### 3.2. Phân đoạn khi chạy song song

~~~text
Đầu vào:       (books,10)    (books,5)    (books,2)
                   |            \          /
Partition A:  {books=10}    Partition B: {books=merge(5,2)}
                   \                /
Combiner:            {books=merge(10,merge(5,2))}
                               |
                          Map cuối
~~~

Một phân đoạn khác có thể dẫn tới:

~~~text
books = merge(merge(10,5),2)
~~~

Java Stream API có quyền quyết định cách phân đoạn và gộp phù hợp với collector; nó không hứa một cây reduction cố định. Vì thế, **các cách nhóm hợp lệ cần cho kết quả tương đương**.

### 3.3. `mergeFunction` và `combiner()` không giống nhau

`Collector<T,A,R>` có bốn hàm chính:

1. **`supplier()`** tạo container tích lũy tạm.
2. **`accumulator()`** thêm một phần tử nguồn vào container.
3. **`combiner()`** gộp hai container đã tích lũy.
4. **`finisher()`** chuyển container thành kết quả.

Trong `toUnmodifiableMap`:

- `mergeFunction` do bạn cung cấp gộp **hai value `U` khi key trùng**.
- `combiner()` của collector hợp nhất **hai map trung gian**. Khi cả hai map có một key, việc hợp nhất value cần tuân theo chính sách merger.

Điều này có nghĩa `mergeFunction` có thể nhận **hai value tổng hợp đã gộp từ nhiều bản ghi**, chứ không nhất thiết là đúng hai value gốc từ `valueMapper`. Một merger chỉ đúng với hai bản ghi đơn lẻ nhưng sai với các kết quả trung gian không thích hợp để song song hóa.

## 4. Tính kết hợp: hợp đồng toán học của phép gộp

Một `BinaryOperator<U> op` được gọi là **có tính kết hợp** nếu với mọi bộ ba giá trị hợp lệ `a`, `b`, `c`:

~~~text
op(op(a,b),c) = op(a,op(b,c))
~~~

Đây là yêu cầu **tương đương về kết quả**, không phải bắt buộc dùng cùng một tham chiếu object trong bộ nhớ.

### 4.1. Phép cộng số nguyên: ví dụ kết hợp

~~~java
java.util.function.BinaryOperator<Integer> sum = Integer::sum;

int left = sum.apply(sum.apply(10, 5), 2);  // 17
int right = sum.apply(10, sum.apply(5, 2)); // 17
~~~

Phép cộng `int` của Java có tính kết hợp trong số học `int` 32 bit (giá trị có thể wrap nếu tràn), dù **không cam kết tổng toán học chính xác khi vượt phạm vi `int`**.

Nếu cần phát hiện overflow, có thể dùng `Math.addExact` với chính sách xử lý ngoại lệ; nếu cần tổng không giới hạn, dùng `BigInteger` hoặc miền số thích hợp. Tính kết hợp của phép cộng không đồng nghĩa kết quả không bị tràn.

### 4.2. `min` và `max`

~~~java
java.util.function.BinaryOperator<Integer> max = Integer::max;

int left = max.apply(max.apply(4, 9), 3);  // 9
int right = max.apply(4, max.apply(9, 3)); // 9
~~~

`Integer::max` và `Integer::min` kết hợp được. Chúng thường thích hợp khi cần giá trị lớn nhất/nhỏ nhất theo mỗi key.

### 4.3. Nối chuỗi theo thứ tự

~~~java
java.util.function.BinaryOperator<String> join =
        (a, b) -> a + "|" + b;

String left = join.apply(join.apply("A", "B"), "C");
String right = join.apply("A", join.apply("B", "C"));

// Cả hai là "A|B|C".
~~~

Phép nối chuỗi với delimiter `"|"` là **kết hợp**: nhóm khác nhau không làm thay đổi chuỗi cuối, nếu thứ tự các value vẫn giữ nguyên. Nhưng nó **không giao hoán** vì `"A|B"` khác `"B|A"`.

## 5. Kết hợp khác giao hoán: khi nào thứ tự quan trọng?

Hai khái niệm:

~~~text
Kết hợp:  op(op(a,b),c) = op(a,op(b,c))
Giao hoán: op(a,b)    = op(b,a)
~~~

| Phép gộp | Kết hợp | Giao hoán | Lưu ý |
| --- | --- | --- | --- |
| `Integer::sum` | Có trong số học `int` | Có | Coi chừng overflow nếu muốn tổng chính xác. |
| `Integer::max` | Có | Có | Chọn giá trị lớn nhất. |
| `Integer::min` | Có | Có | Chọn giá trị nhỏ nhất. |
| `BigInteger::add` | Có | Có | Cộng số nguyên chính xác. |
| `BigDecimal::add`, không làm tròn mỗi bước | Có về giá trị | Có | Cộng thập phân chính xác. |
| `(a,b) -> a + "|" + b` | Có | **Không** | Chỉ giữ chuỗi đúng thứ tự khi nguồn/collector có hợp đồng thứ tự. |
| `(a,b) -> a - b` | **Không** | Không | Phân đoạn khác có thể ra giá trị khác. |
| `(a,b) -> (a+b)/2` | **Không** | Có | Không đại diện đúng phép tính trung bình cả nhóm. |
| `Double::sum` | **Không luôn có** | Không đủ để bảo đảm kết quả | Floating-point rounding có thể làm các nhóm khác nhau cho kết quả khác. |

**Kết hợp** xử lý vấn đề **cách nhóm** phép toán; **giao hoán** xử lý vấn đề **đổi thứ tự** các giá trị.

Với `List.parallelStream()` có encounter order, một collector giữ thứ tự có thể gộp chuỗi theo thứ tự phần tử, dù bên trong được thực thi song song. Nếu nguồn **unordered** (ví dụ `HashSet`) hoặc pipeline có `unordered()`, không nên dựa vào thứ tự đưa value vào merger; với phép nối chuỗi, kết quả có thể thay đổi theo thứ tự.

**Bản thân Map kết quả không cam kết thứ tự duyệt các entry.** Đừng lấy `map.toString()` làm căn cứ kiểm thử thứ tự; hãy kiểm tra value của key cụ thể hoặc sắp xếp key trước khi in.

## 6. Phép trừ là phản ví dụ trực quan

~~~java
java.util.function.BinaryOperator<Integer> subtract =
        (a, b) -> a - b;

int left = subtract.apply(subtract.apply(10, 5), 2);
int right = subtract.apply(10, subtract.apply(5, 2));

System.out.println(left);  // 3
System.out.println(right); // 7
~~~

Vì:

~~~text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
~~~

nên `subtract` **không kết hợp**. Dùng merger như sau có thể tạo kết quả phụ thuộc cây phân đoạn:

~~~java
var result = java.util.List.of(10, 5, 2)
        .parallelStream()
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                ignored -> "total",
                value -> value,
                (a, b) -> a - b
        ));
~~~

Không thể bảo đảm giá trị tại `"total"` luôn là `3` hoặc `7` trong mọi cách chạy và implementation. Không dùng một lần chạy tình cờ cho kết quả mong muốn để chứng minh phép trừ là một merger song song đúng.

Nếu nghiệp vụ cần **chênh lệch giữa các tổng**, hãy tạo các tổng của từng nhóm bằng một phép gộp kết hợp trước, rồi thực hiện phép trừ một lần tại bước có ý nghĩa rõ ràng. Nếu quy trình thực sự là một chuỗi thao tác tuần tự không kết hợp, hãy mô hình hóa nó rõ ràng thay vì kỳ vọng parallel reduction giữ nguyên cách tính trái sang phải.

**Thêm `synchronized` không chữa được tính không kết hợp.** Mutex chỉ giới hạn truy cập đồng thời, không làm thay đổi đẳng thức toán học.

## 7. Cộng `double` không bảo đảm kết hợp tuyệt đối

Ở số thực toán học, phép cộng là kết hợp. Nhưng `double` sử dụng dấu phẩy động hữu hạn: **mỗi phép cộng có thể làm tròn**, làm cho cách nhóm ảnh hưởng kết quả.

~~~java
java.util.function.BinaryOperator<Double> add = Double::sum;

double left = add.apply(
        add.apply(1.0e16, -1.0e16), 1.0);
double right = add.apply(
        1.0e16, add.apply(-1.0e16, 1.0));

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
~~~

Giải thích:

- Nhóm trái: `(1e16 + -1e16) + 1` → `0 + 1` → `1.0`.
- Nhóm phải: `1e16 + (-1e16 + 1)` → phép cộng `-1e16 + 1` bị mất phần đơn vị do giới hạn độ chính xác, kết quả cuối là `0.0`.

Vì vậy, một Map chứa tổng `double` theo mỗi key thu được từ parallel reduction có thể khác vài đơn vị làm tròn so với tính tuần tự. Sai khác đôi khi nhỏ, nhưng phải được hiểu trong các ứng dụng cần tính toán chính xác.

Các lựa chọn:

- Thống kê chấp nhận sai số: dùng dung sai có lý do rõ ràng trong kiểm thử.
- Tính toán tiền tệ/decimal chính xác: `BigDecimal` với nguồn decimal phù hợp, dùng `BigDecimal::add` **không áp dụng `MathContext` làm tròn từng bước**.
- Tính toán số thực lớn: chọn thuật toán số phù hợp, tránh khẳng định `Double::sum` luôn cho kết quả bit-for-bit giống tuần tự.

`BigDecimal` cũng không tự sửa mọi bài toán nếu bạn tạo nó từ `double` đã sai biểu diễn; với giá trị tiền tệ, thường nên đọc từ chuỗi decimal hoặc từ số nguyên biểu diễn đơn vị nhỏ nhất theo thiết kế.

## 8. Không dùng merger có side effect hoặc shared mutable state

Stream API giả định các hành vi trong pipeline phù hợp với **stateless, non-interfering**. Với merger, nên ưu tiên hàm thuần:

- Cùng hai value đầu vào → cùng kết quả về giá trị.
- Không phụ thuộc thời gian, thread ID, scheduler, biến toàn cục, counter hoặc Random không kiểm soát.
- Không sửa nguồn Stream hay một Map chia sẻ từ bên ngoài.
- Không mutate trực tiếp các value của bản ghi khác nếu không có thiết kế quyền sở hữu chặt chẽ.
- Không coi số lần gọi merger là một chỉ số nghiệp vụ xác định.

### Phản mẫu: thêm counter vào merger

~~~java
// PHẢN MẪU: dùng side effect để đếm invocation.
var calls = new java.util.concurrent.atomic.AtomicInteger();
java.util.function.BinaryOperator<Integer> bad =
        (a, b) -> {
            calls.incrementAndGet();
            return a + b;
        };
~~~

Dù `AtomicInteger.incrementAndGet()` là thao tác atomic, merger **không còn thuần**. Số lần và thời điểm gọi có thể phụ thuộc phân đoạn hoặc cách triển khai. Nếu biến counter tham gia quyết định kết quả, logic càng không ổn định. Dùng `Integer::sum` cho giá trị nghiệp vụ, quan sát metrics ở lớp riêng.

### Phản mẫu: mutate `StringBuilder` được chia sẻ

~~~java
// PHẢN MẪU khi không chứng minh được ownership và tính an toàn:
(a, b) -> {
    a.append(b);
    return a;
}
~~~

Một mutable value có thể bị các nhánh truy cập hoặc được tái sử dụng ở nơi khác. Nếu tự thiết kế mutable reduction, phải bảo đảm container tách biệt, combiner đúng, không rò rỉ trạng thái. Với nối chuỗi dữ liệu nhỏ, một phép merge tạo value immutable `(a,b) -> a + "|" + b` dễ kiểm tra hơn.

Không nhầm **kết quả cuối là Map unmodifiable** với việc **mọi hoạt động trung gian và các value đều thread-safe**.

## 9. Identity constraint thuộc Collector, không phải một value giả cho merger

Theo `Collector` JavaDoc, hai tính chất quan trọng là:

1. **Identity constraint:** kết hợp một kết quả tích lũy với một container rỗng không làm đổi ý nghĩa kết quả.
2. **Associativity constraint:** chia công việc thành nhiều phần rồi gộp phải tương đương với việc không chia.

Mô tả identity:

~~~text
combine(partialMap, emptyMap) ≈ partialMap
~~~

Với Map collector, phần tử trung hòa của container là **map rỗng**, không phải một value `U` bắt buộc như `0` cho mọi phép merge. Do đó bạn không cần tìm một “value identity” cho `Integer::max` khi dùng `toUnmodifiableMap`.

Một key được tạo khi có value đầu tiên; `mergeFunction` giải quyết các lần va chạm value. Điều quan trọng là **kết quả Map sau nhiều cách tích lũy và gộp tương đương**, không phải merger luôn được gọi từ value trung hòa.

Sự tương đương của các Map thông thường nên kiểm tra bằng `Map.equals`, không bằng reference identity hay thứ tự duyệt.

## 10. Chính sách duplicate, null và `Map.merge`

### 10.1. Duplicate key

~~~java
var numbers = java.util.List.of(1, 2, 3);

// Có merger:
var sum = numbers.stream().collect(
        java.util.stream.Collectors.toUnmodifiableMap(
                value -> "total",
                value -> value,
                Integer::sum
        ));
System.out.println(sum.get("total")); // 6
~~~

Nếu bỏ `Integer::sum` và dùng overload hai mapper, key `"total"` bị trùng; collector ném **`IllegalStateException`**. Một mapper tạo key không duy nhất cần chính sách gộp rõ ràng.

### 10.2. Mapped key/value `null` bị từ chối

`toUnmodifiableMap` tạo Map không cho `null` làm key hoặc value. Nếu `keyMapper` hay `valueMapper` trả `null`, thao tác collect ném **`NullPointerException`**. Điều này khác với Map thông thường có thể cho key/value `null` tùy implementation.

Dữ liệu thiếu cần xử lý tại mapper/pipeline hoặc validation có chủ đích. Đừng lặng lẽ biến mọi `null` thành chuỗi rỗng nếu như thế làm mất khác biệt nghiệp vụ.

### 10.3. Merger trả về `null` có ý nghĩa đặc biệt

Theo hợp đồng `Map.merge`, nếu remapping function trả về `null`, mapping hiện tại **bị xóa**. Một merger cho `null` vì muốn “tạm thời chưa có kết quả” có thể làm mất key rồi các value đến sau có thể thêm key lại.

Trong phép tổng hợp số học, **nên dùng merger trả về value khác `null`** trên miền giá trị hợp lệ. Không nên lợi dụng xóa mapping do null nếu chưa chứng minh quy tắc đó kết hợp được và phù hợp với cách parallel combiner hoạt động.

### 10.4. Không đoán số lần gọi merger

Một key chỉ xuất hiện một lần thì không nhất thiết có lời gọi merger. Với parallel Stream, một key có thể được gộp trong từng partition và lại được gộp khi combiner hợp nhất Map. Số lần gọi, thread gọi và thứ tự thực thi callback không nên là một phần của logic nghiệp vụ.

## 11. Ordered/unordered và Map kết quả

Ví dụ nối nhãn theo thứ tự đầu vào:

~~~java
record LogEvent(String category, String label) { }

var logs = java.util.List.of(
        new LogEvent("books", "A"),
        new LogEvent("books", "B"),
        new LogEvent("books", "C")
);

var labels = logs.parallelStream().collect(
        java.util.stream.Collectors.toUnmodifiableMap(
                LogEvent::category,
                LogEvent::label,
                (a, b) -> a + "|" + b
        ));
System.out.println(labels.get("books")); // A|B|C
~~~

Với Stream từ List có thứ tự và collector giữ encounter order, value được kết hợp theo chuỗi ban đầu cho mỗi key. Nhưng khi nguồn không có encounter order hoặc gọi `unordered()`, không thể giả định `A` sẽ đến trước `B`. Nếu yêu cầu độc lập thứ tự, cần phép merge giao hoán hoặc sắp xếp dữ liệu trước.

Ngoài ra, **Map unmodifiable không đồng nghĩa Map có thứ tự duyệt**. Đối với `Collectors.toUnmodifiableMap`, không nên yêu cầu `map.keySet().iterator().next()` trả một key cụ thể. Khi cần kiểm tra, gọi `map.get(key)` hoặc sắp xếp entry trước khi hiển thị.

## 12. Parallel Stream không đồng nghĩa concurrent collector

| Khái niệm | Ý nghĩa |
| --- | --- |
| `parallelStream()` | Cho phép chia pipeline thành các công việc song song. |
| `Collector.combiner()` | Hợp nhất kết quả trung gian thành kết quả cuối. |
| `Collectors.toUnmodifiableMap(...)` | Tạo Map không sửa đổi; sử dụng merger để xử lý key trùng. |
| `Collectors.toConcurrentMap(...)` | Collector cho mục tiêu concurrent accumulation, có hợp đồng khác. |
| `Collections.unmodifiableMap(existing)` | View chặn sửa qua view nhưng có thể theo thay đổi của backing map. |

Parallel reduction với collector không concurrent thường sử dụng **container riêng cho từng nhánh** rồi kết hợp bằng combiner. Nó không có nghĩa bạn có quyền ghi vào một `HashMap` hoặc `ArrayList` toàn cục từ mọi lambda song song.

Không nên thay `toUnmodifiableMap` bằng `toConcurrentMap` chỉ vì thêm `parallel()`. Hãy chọn dựa trên yêu cầu đầu ra: Map không sửa được hay Map hỗ trợ cập nhật đồng thời; đồng thời xem xét ordering và các đặc tính collector.

**Tính đúng đắn trước hiệu năng:** với số lượng phần tử nhỏ hoặc merge map tốn chi phí, parallel có thể chậm hơn tuần tự. Nếu hiệu năng quan trọng, đo bằng benchmark trên dữ liệu thực tế.

## 13. Chọn chiến lược gộp theo bài toán

### 13.1. Đếm số lượng theo từng key

~~~java
var counts = events.parallelStream().collect(
        Collectors.toUnmodifiableMap(
                Event::category,
                ignored -> 1,
                Integer::sum
        )
);
~~~

Đây là đoạn minh họa khi lớp `Event`/biến `events` đã tồn tại. Với miền đếm nhỏ trong `int`, `Integer::sum` là merger gọn, kết hợp, không có side effect. Với số phần tử vượt giới hạn `int`, chọn miền rộng hơn hoặc cơ chế đếm chính xác.

### 13.2. Lấy max/min theo key

~~~java
var maximum = sales.parallelStream().collect(
        Collectors.toUnmodifiableMap(
                Sale::category,
                Sale::quantity,
                Integer::max
        )
);
~~~

Nếu value là object nghiệp vụ và cần chọn object lớn nhất theo điểm, hãy định nghĩa **tie-break** rõ ràng khi hai object có cùng điểm; nếu không, bạn có thể nhận một trong nhiều object “cùng lớn nhất” mà không mong muốn.

### 13.3. Tổng decimal chính xác

~~~java
var totals = payments.parallelStream().collect(
        Collectors.toUnmodifiableMap(
                Payment::currency,
                Payment::amount,        // BigDecimal
                java.math.BigDecimal::add
        )
);
~~~

Đoạn này giả định domain `Payment.amount()` trả `BigDecimal` hợp lệ, không null. `BigDecimal::add` không áp dụng làm tròn mỗi bước là phép cộng chính xác phù hợp. Với dữ liệu tiền tệ, nên dùng chuỗi decimal hoặc lượng đơn vị nhỏ nhất, tránh tạo `BigDecimal` từ giá trị `double` đã không chính xác.

### 13.4. Tính trung bình: không dùng trung bình từng đôi

~~~text
merge(a,b) = (a+b)/2

merge(merge(2,4),10) = merge(3,10) = 6.5
merge(2,merge(4,10)) = merge(2,7) = 4.5
~~~

Vì vậy đây **không** là merger đúng cho mean cả nhóm. Cách đúng là lưu trạng thái trung gian **`(sum,count)`**, kết hợp hai trạng thái bằng phép cộng `sum` và `count`, rồi tính `sum/count` ở bước cuối. Nếu phù hợp, có thể sử dụng collector thống kê có sẵn (`averagingInt`/`averagingLong` trong grouping), hiểu chính sách floating-point của kết quả.

## 14. Kiểm thử hợp đồng một cách có hệ thống

Một phép thử đơn giản cho bộ ba:

~~~java
static <T> boolean associative(
        java.util.function.BinaryOperator<T> op,
        T a, T b, T c) {
    T left = op.apply(op.apply(a, b), c);
    T right = op.apply(a, op.apply(b, c));
    return java.util.Objects.equals(left, right);
}
~~~

Ví dụ:

~~~java
System.out.println(associative(Integer::sum, 10, 5, 2)); // true
System.out.println(associative((a, b) -> a - b, 10, 5, 2)); // false
~~~

Phép thử trên chỉ **phát hiện một phản ví dụ**, không chứng minh kết hợp cho mọi value. Hãy mở rộng bằng các bộ dữ liệu nhiều kích thước, giá trị biên, âm, 0, số lớn, trường hợp null, duplicate key và các tổ hợp ordered/unordered mà ứng dụng hỗ trợ.

Đối với một merger đã được thiết kế đúng:

~~~java
var seq = sales.stream().collect(
        Collectors.toUnmodifiableMap(
                Sale::category, Sale::quantity, Integer::sum));

var par = sales.parallelStream().collect(
        Collectors.toUnmodifiableMap(
                Sale::category, Sale::quantity, Integer::sum));

System.out.println(seq.equals(par)); // true
~~~

`Map.equals` kiểm tra các ánh xạ key/value chứ không phụ thuộc thứ tự entry. Nếu dùng phép gộp không kết hợp, việc `seq.equals(par)` tình cờ đúng ở một lần chạy **không** chứng minh merger an toàn.

Các kiểm tra tốt khác:

- **Associativity** với nhiều bộ ba `a,b,c`.
- Hàm mapper/merger không mutate source hay state dùng chung.
- Xử lý rõ `null` và ngoại lệ.
- Nếu value chứa cấu trúc mutable, bảo đảm quyền sở hữu và bất biến ở mức mong muốn.
- Không giả định tốc độ, lớp runtime hay thứ tự duyệt Map.
- Nếu dùng số thực, nêu rõ độ chính xác/dung sai hoặc dùng kiểu tính toán phù hợp.

## 15. Chương trình Java 17+ hoàn chỉnh, đã kiểm chứng

Tạo tệp **`ParallelMapMergeDemo.java`** với nội dung:

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelMapMergeDemo {
    record Sale(String category, int quantity, String label) {}

    static <T> void check(String name, T left, T right) {
        if (!left.equals(right)) {
            throw new AssertionError(
                    name + " not equivalent: " + left + " vs " + right);
        }
        System.out.println(name + "=equivalent");
    }

    public static void main(String[] args) {
        var sales = List.of(
                new Sale("books", 4, "A"),
                new Sale("games", 8, "X"),
                new Sale("books", 3, "B"),
                new Sale("books", 2, "C"));

        var sequential = sales.stream().collect(
                Collectors.toUnmodifiableMap(
                        Sale::category, Sale::quantity, Integer::sum));
        var parallel = sales.parallelStream().collect(
                Collectors.toUnmodifiableMap(
                        Sale::category, Sale::quantity, Integer::sum));
        check("sum", sequential, parallel);
        System.out.println("books=" + parallel.get("books"));
        System.out.println("games=" + parallel.get("games"));

        try {
            parallel.put("bonus", 1);
        } catch (UnsupportedOperationException ex) {
            System.out.println("map update blocked");
        }

        var max = sales.parallelStream().collect(
                Collectors.toUnmodifiableMap(
                        Sale::category, Sale::quantity, Integer::max));
        System.out.println("max books=" + max.get("books"));

        var names = sales.parallelStream().collect(
                Collectors.toUnmodifiableMap(
                        Sale::category, Sale::label, (a, b) -> a + "|" + b));
        System.out.println("labels books=" + names.get("books"));

        BinaryOperator<Integer> subtract = (a, b) -> a - b;
        System.out.println("subtract left=" +
                subtract.apply(subtract.apply(10, 5), 2));
        System.out.println("subtract right=" +
                subtract.apply(10, subtract.apply(5, 2)));

        BinaryOperator<Double> sumDouble = Double::sum;
        System.out.println("double left=" +
                sumDouble.apply(sumDouble.apply(1.0e16, -1.0e16), 1.0));
        System.out.println("double right=" +
                sumDouble.apply(1.0e16, sumDouble.apply(-1.0e16, 1.0)));

        var countItems = IntStream.range(0, 1000).parallel()
                .boxed()
                .collect(Collectors.toUnmodifiableMap(
                        i -> i % 2 == 0 ? "even" : "odd",
                        i -> 1,
                        Integer::sum));
        System.out.println("even=" + countItems.get("even")
                + ", odd=" + countItems.get("odd"));

        var big = List.of(
                new BigDecimal("10000000000000000000"),
                new BigDecimal("2"),
                new BigDecimal("3")).parallelStream()
                .collect(Collectors.toUnmodifiableMap(
                        ignored -> "total",
                        item -> item,
                        BigDecimal::add));
        System.out.println("exact=" + big.get("total"));

        try {
            sales.parallelStream().collect(
                    Collectors.toUnmodifiableMap(
                            Sale::category, Sale::quantity));
        } catch (IllegalStateException ex) {
            System.out.println("duplicate key rejected");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 ParallelMapMergeDemo.java
java ParallelMapMergeDemo
~~~

**Stdout chính xác:**

~~~text
sum=equivalent
books=9
games=8
map update blocked
max books=4
labels books=A|B|C
subtract left=3
subtract right=7
double left=1.0
double right=0.0
even=500, odd=500
exact=10000000000000000005
duplicate key rejected
~~~

### 15.1. Giải thích kết quả

1. **`sum=equivalent`**: `sequential.equals(parallel)` đúng với dữ liệu và `Integer::sum`; kiểm tra theo Map value, không theo thứ tự duyệt.
2. **`books=9`, `games=8`**: `books` cộng `4+3+2`; `games` có một value `8`.
3. **`map update blocked`**: `toUnmodifiableMap` chặn `put` bằng `UnsupportedOperationException`.
4. **`max books=4`**: phép chọn cực đại có tính kết hợp và không phụ thuộc cách nhóm.
5. **`labels books=A|B|C`**: phép nối chuỗi kết hợp nhưng không giao hoán; nguồn `List` có thứ tự.
6. **`subtract left=3` và `subtract right=7`**: phản ví dụ không kết hợp, được tính trực tiếp thay vì dựa vào một partition parallel không ổn định.
7. **`double left=1.0` và `double right=0.0`**: làm tròn floating-point làm kết quả phụ thuộc cách nhóm.
8. **`even=500, odd=500`**: song song với 1000 phần tử và merger `Integer::sum` tạo kết quả đếm đúng.
9. **`exact=10000000000000000005`**: phép `BigDecimal::add` không làm tròn cho giá trị decimal chính xác.
10. **`duplicate key rejected`**: overload hai mapper không chấp nhận va chạm key.

Để giữ stdout ổn định, chương trình **không in** một phép trừ được thực hiện bằng parallel map collector hay thứ tự duyệt Map kết quả. Nó chỉ in các điều kiện thuộc hợp đồng hoặc giá trị phản ví dụ được tính tường minh.

## 16. Sai lầm thường gặp

| Sai lầm | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Merger có hai tham số là mặc nhiên an toàn parallel | Không chứng minh tính kết hợp. | Kiểm tra `op(op(a,b),c) == op(a,op(b,c))`. |
| Dùng phép trừ trong `mergeFunction` rồi tin kết quả luôn đúng | Cách nhóm có thể đổi kết quả. | Gộp các tổng bằng phép cộng, trừ ở bước cuối có ý nghĩa. |
| Dùng `(a+b)/2` để tính mean nhiều bản ghi | Không kết hợp; bỏ trọng số của các phần. | Gộp `sum/count` rồi chia một lần. |
| Dùng `Double::sum` mà yêu cầu kết quả bit-for-bit bất biến | Rounding phụ thuộc nhóm. | Xác định dung sai hoặc dùng mô hình chính xác khác. |
| Đồng nhất kết hợp với giao hoán | Nối chuỗi kết hợp nhưng nhạy thứ tự. | Dùng ordered stream khi cần, hoặc phép giao hoán. |
| Giả định merger chỉ nhận value ban đầu | Parallel combiner có thể gộp các tổng trung gian. | Thiết kế merger chấp nhận mọi kết quả tích lũy hợp lệ. |
| Merger ghi counter/Map ngoài để “ghi log” nghiệp vụ | Side effect phụ thuộc cách chạy. | Hàm thuần và metrics riêng. |
| Merger trả `null` để “bỏ qua” | `Map.merge` có thể xóa key. | Chính sách loại bỏ rõ ràng, tránh null mơ hồ. |
| Quên overload ba đối số khi key trùng | `IllegalStateException`. | Xác định merge policy khi có duplicate. |
| Nghĩ Map unmodifiable làm tất cả value immutable | Value mutable vẫn bị sửa được. | Thiết kế value bất biến/defensive copy. |
| So sánh Map bằng `toString()` | Thứ tự key không cam kết. | Dùng `Map.equals`, `get(key)`. |
| Cho rằng parallel luôn nhanh hơn | Phân đoạn/gộp map có chi phí. | Benchmark theo workload thực tế. |

## 17. Bài tập và đáp án

**Câu 1.** Hai merger sau có tính kết hợp không?

~~~java
BinaryOperator<Integer> plus = Integer::sum;
BinaryOperator<Integer> minus = (a, b) -> a - b;
~~~

**Đáp án:** `plus` có tính kết hợp trong số học `int` Java (dù có thể overflow về giá trị). `minus` không, với bộ ba `10,5,2` đã cho kết quả `3` và `7`.

**Câu 2.** `(a,b)->a+"|"+b` có kết hợp và giao hoán không?

**Đáp án:** Có tính kết hợp nhưng không giao hoán. Muốn chuỗi theo thứ tự nguồn, cần contract encounter order của pipeline/collector. Với unordered source, không nên đoán thứ tự các giá trị.

**Câu 3.** Vì sao `mergeFunction` có thể nhận một value đã tổng hợp nhiều bản ghi?

**Đáp án:** Parallel Stream tạo các map trung gian theo partition, rồi `Collector.combiner` hợp nhất chúng. Value của một key trong map trung gian có thể đã qua nhiều lần merge.

**Câu 4.** Có cần khai báo một value identity bằng 0 khi dùng `Integer::max` không?

**Đáp án:** Không. `toUnmodifiableMap` tích lũy trên container Map, với map rỗng là trạng thái trung hòa ở mức container; merger giải quyết va chạm value, không nhận identity value tường minh.

**Câu 5.** Vì sao `Double::sum` không bảo đảm cùng kết quả khi thay cây reduction?

**Đáp án:** Floating-point làm tròn theo từng phép cộng. `(1e16-1e16)+1` và `1e16+(-1e16+1)` có thể lần lượt là `1.0` và `0.0`.

**Câu 6.** Có nên dùng `AtomicInteger` trong merger để quyết định ưu tiên bản ghi theo số lần gọi không?

**Đáp án:** Không. Atomic chỉ giúp thao tác cập nhật counter an toàn, còn số lần gọi/thứ tự gọi không thuộc hợp đồng reduction.

**Câu 7.** Khi mapped key trùng và không truyền merger vào `toUnmodifiableMap` thì sao?

**Đáp án:** Collector hai tham số ném `IllegalStateException`. Nếu key trùng hợp lệ, chọn overload ba đối số và merger có tính kết hợp.

**Câu 8.** Nếu merger trả `null` thì value `null` được ghi vào Map kết quả không?

**Đáp án:** Không. Theo ngữ nghĩa `Map.merge`, `null` từ remapping function có thể xóa mapping; không nên dùng như một cách “giữ value null” trong Map unmodifiable.

**Câu 9.** Kiểm tra nào đúng khi đối chiếu tuần tự/song song?

**Đáp án:** `seq.equals(par)` và kiểm tra từng key/value, kèm property tests cho associativity. Không so sánh chuỗi hiển thị Map hoặc reference identity.

**Câu 10.** Vì sao `parallelStream()` không đồng nghĩa phải dùng `toConcurrentMap`?

**Đáp án:** Parallel reduction có thể dùng container độc lập rồi gọi combiner; collector concurrent có hợp đồng khác. Nếu yêu cầu kết quả Map unmodifiable, `toUnmodifiableMap` vẫn phù hợp miễn merger đúng.

## 18. Checklist áp dụng vào dự án

- [ ] Tôi đã chọn overload ba tham số khi mapped keys có thể trùng.
- [ ] Merger nhận được **hai value trung gian**, không chỉ các bản ghi gốc.
- [ ] Tôi đã kiểm tra tính **kết hợp** trong miền dữ liệu hợp lệ.
- [ ] Tôi phân biệt **kết hợp** với **giao hoán** và hiểu yêu cầu encounter order.
- [ ] Key/value mappers và merger không có side effect nguy hiểm, không sửa Stream source.
- [ ] Tôi không dựa vào số lần gọi merger, thread hay thứ tự scheduling.
- [ ] Tôi biết các giá trị `null` bị từ chối và `Map.merge` xử lý null do merger trả về ra sao.
- [ ] Tôi có chính sách cho integer overflow và floating-point rounding.
- [ ] Tôi biết Map kết quả không sửa được nhưng các value mutable vẫn có thể thay đổi.
- [ ] Tôi không dùng thứ tự duyệt Map hay `toString()` làm test kết quả.
- [ ] Nếu cần exact decimal, tôi xem xét `BigDecimal` và tránh làm tròn ở từng lần merge.
- [ ] Tôi đã thử cả tuần tự và song song với dữ liệu nhiều duplicate key, giá trị biên.
- [ ] Tôi chỉ dùng parallel sau khi kiểm tra correctness và đo hiệu năng trên dữ liệu phù hợp.

## 19. Tài liệu tham khảo chính thức (còn hiệu lực)

- [Java SE 26 — `Collectors.toUnmodifiableMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): overload ba tham số, duplicate key, mergeFunction và chính sách null; API ra đời từ Java 10.
- [Java SE 25 — `Collector`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collector.html): supplier, accumulator, combiner, finisher; identity và associativity constraints.
- [Java SE 26 — Stream package, Associativity](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/package-summary.html#Associativity): lý do reduction cần tính kết hợp để phân đoạn song song.
- [Java SE 26 — `Map.merge`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#merge(K,V,java.util.function.BiFunction)): hợp đồng merge và trường hợp merger trả về null.
- [Java SE 26 — `Stream`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html): encounter order, parallel, stateless/non-interfering.
- [Java SE 26 — `BigDecimal`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html): arithmetic exact decimal và MathContext khi cần.
- [Java SE 26 — `Collectors.toConcurrentMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html): collector concurrent với mục đích khác Map unmodifiable.

**Ghi nhớ:** Trong Collector bản đồ của Java, parallel Stream được phép **chia rồi kết hợp** các kết quả trung gian. Một `mergeFunction` đáng tin phải **kết hợp được**, không có side effect gây phụ thuộc lịch chạy, xử lý đúng thứ tự khi cần và tuân thủ chính sách `null`/duplicate/kiểu số. Đừng coi một lần chạy có kết quả đúng là bằng chứng hợp đồng gộp đã đúng.