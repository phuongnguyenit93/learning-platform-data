# Hiểu kết quả đối sánh khi Stream rỗng

Trong Java Stream API, các phương thức `anyMatch`, `allMatch` và `noneMatch` trả lời ba câu hỏi khác nhau về một tập phần tử. Điểm dễ gây nhầm lẫn là: **khi Stream rỗng, `allMatch` và `noneMatch` đều trả về `true`, trong khi `anyMatch` trả về `false`**. Đây là ngữ nghĩa có chủ đích của các phép lượng hóa logic, không phải lỗi của Java.

Bài học thuộc chương **Duyệt, tìm kiếm và đối sánh** của mô-đun **JAVA_STREAM_API**. Hiểu rõ trường hợp Stream rỗng giúp viết pipeline `filter`, `map`, các phép tìm kiếm và tổng hợp đúng nghiệp vụ, đặc biệt với dữ liệu đầu vào rỗng hoặc bị lọc hết. Đây cũng là nền tảng để đánh giá tác động của tính **lazy**, dừng sớm (*short-circuit*), xử lý song song, trạng thái chia sẻ và hiệu năng trong Java Stream API.

## 1. Ba phép đối sánh và kết quả trên Stream rỗng

Một phép đối sánh áp dụng một `Predicate<T>` (hàm trả về `boolean`) lên các phần tử của `Stream<T>`. Cả ba đều là **terminal operation**: chúng tiêu thụ Stream và trả về một giá trị `boolean`.

| Phương thức | Câu hỏi về các phần tử | Có phần tử thỏa điều kiện mới trả về `true`? | Stream rỗng |
| --- | --- | --- | --- |
| `anyMatch(predicate)` | **Có ít nhất một** phần tử thỏa điều kiện không? | Có | **`false`** |
| `allMatch(predicate)` | **Mọi** phần tử đều thỏa điều kiện không? | Không bắt buộc Stream phải có phần tử | **`true`** |
| `noneMatch(predicate)` | **Không có phần tử nào** thỏa điều kiện phải không? | Không; chỉ cần không có trường hợp thỏa | **`true`** |

Ví dụ nhỏ nhất:

```java
import java.util.stream.Stream;

public class EmptyMatchBasics {
    public static void main(String[] args) {
        boolean anyPositive = Stream.<Integer>empty()
            .anyMatch(number -> number > 0);

        boolean allPositive = Stream.<Integer>empty()
            .allMatch(number -> number > 0);

        boolean nonePositive = Stream.<Integer>empty()
            .noneMatch(number -> number > 0);

        System.out.println(anyPositive);  // false
        System.out.println(allPositive);  // true
        System.out.println(nonePositive); // true
    }
}
```

Ở đây sử dụng **ba Stream mới**, vì mỗi Stream chỉ được thực hiện terminal operation một lần. `Stream.<Integer>empty()` tạo một nguồn rỗng có kiểu phần tử xác định. Không có số nào được đưa vào các lambda kiểm tra `number > 0`.

### Điều gì làm kết quả trông bất thường?

Một cách đọc quá nhanh có thể dẫn tới hai nhận định sai:

- “`allMatch` trả về `true` nghĩa là có những phần tử hợp lệ.” Thực tế, nó **không xác nhận có phần tử**.
- “`noneMatch` trả về `true` nghĩa là tất cả phần tử đều không hợp lệ.” Thực tế, nó chỉ xác nhận **không có phần tử phù hợp với điều kiện đã đưa vào**.

Ví dụ, nếu danh sách đăng ký rỗng thì các phát biểu “tất cả đăng ký đều đạt chuẩn” và “không có đăng ký nào đạt chuẩn” cùng được xem là đúng theo logic lượng hóa. Chúng không mâu thuẫn, vì tập đăng ký không có thành viên để làm phản ví dụ cho phát biểu thứ nhất hay ví dụ thuận cho phát biểu thứ hai.

## 2. Hiểu theo logic toán học: tính đúng rỗng (*vacuous truth*)

Ba phép đối sánh tương ứng với ba loại mệnh đề:

- `anyMatch(p)` là **tồn tại** phần tử `x` để `p(x)` đúng (ký hiệu `∃x: p(x)`).
- `allMatch(p)` là **với mọi** phần tử `x`, `p(x)` đúng (ký hiệu `∀x: p(x)`).
- `noneMatch(p)` là **không tồn tại** phần tử `x` để `p(x)` đúng (ký hiệu `¬∃x: p(x)`).

Nếu tập dữ liệu rỗng:

- Không tồn tại phần tử nào, nên `anyMatch(p)` là `false`.
- Không có phần tử nào **vi phạm** điều kiện, nên `allMatch(p)` là `true`.
- Không có phần tử nào **đáp ứng** điều kiện, nên `noneMatch(p)` là `true`.

Phát biểu “mọi phần tử của tập rỗng đều đạt điều kiện” được gọi là *vacuously true* (đúng rỗng). Cách hiểu gần gũi hơn: `allMatch` đang đi tìm **một phản ví dụ** khiến mệnh đề “tất cả đều đúng” bị bác bỏ; trong Stream rỗng, không thể tìm ra phản ví dụ.

Với một tập hữu hạn, có thể xem các phép đối sánh như sau:

```text
anyMatch(p)   = có ít nhất 1 phần tử với p(x) == true
allMatch(p)   = không có phần tử với p(x) == false
noneMatch(p)  = không có phần tử với p(x) == true

Số phần tử = 0
  ├── anyMatch  → false
  ├── allMatch  → true
  └── noneMatch → true
```

Đây là ngữ nghĩa của các phép lượng hóa trong Java, bất kể điều kiện truyền vào đơn giản hay phức tạp.

## 3. Bảng chân trị theo số lượng phần tử phù hợp

Giả sử `p` là “số lớn hơn 0”. Bảng dưới cho thấy kết quả khi đầu vào thay đổi:

| Stream dữ liệu | Số phần tử | Phần tử thỏa `p` | `anyMatch(p)` | `allMatch(p)` | `noneMatch(p)` |
| --- | ---: | ---: | :---: | :---: | :---: |
| `[]` | 0 | 0 | `false` | **`true`** | **`true`** |
| `[1]` | 1 | 1 | `true` | `true` | `false` |
| `[-1]` | 1 | 0 | `false` | `false` | `true` |
| `[1, 2]` | 2 | 2 | `true` | `true` | `false` |
| `[1, -2]` | 2 | 1 | `true` | `false` | `false` |
| `[-1, -2]` | 2 | 0 | `false` | `false` | `true` |

Nhìn vào bảng, đặc biệt chú ý:

1. Khi có **ít nhất một** phần tử, `anyMatch` và `noneMatch` không thể cùng đúng.
2. Khi tập rỗng, `allMatch` và `noneMatch` cùng đúng là hoàn toàn hợp lệ.
3. Nếu mọi phần tử thỏa điều kiện trên một tập **không rỗng**, `allMatch` và `anyMatch` cùng đúng.
4. `anyMatch(p)` chỉ cần một ví dụ thỏa điều kiện; `allMatch(p)` chỉ cần một phản ví dụ là sai.

Bạn có thể chạy ví dụ sau để đối chiếu:

```java
import java.util.List;

List<Integer> numbers = List.of(1, -2);

System.out.println(numbers.stream().anyMatch(n -> n > 0));  // true
System.out.println(numbers.stream().allMatch(n -> n > 0));  // false
System.out.println(numbers.stream().noneMatch(n -> n > 0)); // false
```

## 4. Stream có thể rỗng ở nhiều giai đoạn khác nhau

“Stream rỗng” không chỉ có nghĩa là danh sách đầu vào ban đầu rỗng. Trong ứng dụng thực tế, dữ liệu có thể bị loại hết ở các bước trung gian.

### 4.1. Nguồn dữ liệu không có phần tử

```java
import java.util.List;

List<String> names = List.of();

boolean anyLongName = names.stream()
    .anyMatch(name -> name.length() > 10);

boolean allNonBlank = names.stream()
    .allMatch(name -> !name.isBlank());

System.out.println(anyLongName); // false
System.out.println(allNonBlank);  // true
```

Ngay cả nếu yêu cầu nghiệp vụ nói “phải có tên hợp lệ”, `allMatch` đơn độc vẫn không phát hiện danh sách trống.

### 4.2. Nguồn có dữ liệu nhưng `filter` loại hết

```java
import java.util.List;

record Order(String id, long amountVnd, boolean paid) {}

List<Order> orders = List.of(
    new Order("O-01", 200_000L, true),
    new Order("O-02", 350_000L, false)
);

// Không đơn nào đạt ngưỡng 1 triệu.
boolean allExpensiveOrdersPaid = orders.stream()
    .filter(order -> order.amountVnd() >= 1_000_000L)
    .allMatch(Order::paid);

System.out.println(allExpensiveOrdersPaid); // true
```

Mặc dù `orders` không rỗng, Stream **sau `filter`** đã rỗng. `allMatch` trả về `true` vì không có đơn giá trị lớn nào chưa thanh toán để bác bỏ điều kiện.

Đây là lý do phải xác định đúng câu hỏi:

- “**Có đơn đắt tiền nào chưa thanh toán không?**” → `anyMatch` trên điều kiện “đắt tiền và chưa thanh toán”.
- “**Mọi đơn đắt tiền đều đã thanh toán?**” → `filter(...).allMatch(Order::paid)`; chấp nhận cả trường hợp không có đơn đắt tiền.
- “**Có ít nhất một đơn đắt tiền và mọi đơn đắt tiền đều đã thanh toán?**” → cần kiểm tra **không rỗng** trên tập *đã lọc*, đồng thời kiểm tra `allMatch`.

Không nên xem một kết quả `true` của `allMatch` là bằng chứng rằng dữ liệu nguồn hoặc dữ liệu được chọn có tồn tại.

### 4.3. Một số thao tác khác cũng tạo đầu ra rỗng

```java
import java.util.stream.IntStream;
import java.util.stream.Stream;

System.out.println(Stream.of("A", "B")
    .limit(0)
    .allMatch(s -> !s.isBlank())); // true

System.out.println(IntStream.range(5, 5)
    .noneMatch(n -> n < 0));       // true

System.out.println(Stream.of("1", "2")
    .filter(s -> s.equals("X"))
    .anyMatch(s -> s.length() > 0)); // false
```

`limit(0)` lấy 0 phần tử; `IntStream.range(5, 5)` là khoảng nửa mở rỗng; `filter` có thể chọn ra tập rỗng. Cả ba tình huống đều tuân theo cùng bảng chân trị của các phép đối sánh.

## 5. Khi nghiệp vụ yêu cầu “có ít nhất một và tất cả đều đạt”

Đây là điểm cần giải quyết rõ ràng nhất trong kiểm tra dữ liệu, phê duyệt, giao dịch hoặc đánh giá chất lượng.

Giả sử yêu cầu: **Phải có ít nhất một đơn hàng giá trị từ 1 triệu VND và tất cả những đơn hàng đó phải được thanh toán.**

Chỉ viết:

```java
boolean approved = orders.stream()
    .filter(order -> order.amountVnd() >= 1_000_000L)
    .allMatch(Order::paid);
```

là **chưa đủ**. Kết quả là `true` nếu không có đơn nào đạt ngưỡng.

### 5.1. Cách rõ ràng: lấy tập ứng viên rồi kiểm tra

```java
import java.util.List;

List<Order> expensiveOrders = orders.stream()
    .filter(order -> order.amountVnd() >= 1_000_000L)
    .toList();

boolean approved = !expensiveOrders.isEmpty()
    && expensiveOrders.stream().allMatch(Order::paid);

System.out.println(approved); // false với danh sách ở mục 4.2
```

Cách này tách hai ý nghĩa thành hai điều kiện:

1. `!expensiveOrders.isEmpty()`: thực sự có ứng viên để xét.
2. `expensiveOrders.stream().allMatch(Order::paid)`: không có ứng viên nào vi phạm yêu cầu.

`&&` đánh giá ngắn mạch: nếu danh sách ứng viên rỗng thì không cần chạy `allMatch`. Cách này phù hợp khi cũng cần sử dụng tập đã lọc cho các bước tiếp theo, nhưng `toList()` sẽ lưu kết quả trong bộ nhớ.

### 5.2. Không lưu danh sách trung gian: hai lượt kiểm tra

Với nguồn là một `List` ổn định trong thời gian kiểm tra, ta có thể dùng hai pipeline độc lập:

```java
boolean hasExpensiveOrder = orders.stream()
    .anyMatch(order -> order.amountVnd() >= 1_000_000L);

boolean allExpensivePaid = orders.stream()
    .filter(order -> order.amountVnd() >= 1_000_000L)
    .allMatch(Order::paid);

boolean approved = hasExpensiveOrder && allExpensivePaid;
```

Cách này không tạo danh sách trung gian nhưng có thể cần duyệt nguồn nhiều lần. Mỗi lời gọi `orders.stream()` tạo **một Stream mới**: không thể tiêu thụ lại cùng Stream. Nếu nguồn thay đổi giữa hai lần kiểm tra hoặc chỉ được đọc một lần (ví dụ luồng từ tệp), cần chiến lược khác để bảo đảm kết quả nhất quán.

Nếu chỉ cần câu hỏi “có ít nhất một đơn **chưa thanh toán** trong nhóm đắt tiền không?”, có thể diễn đạt ngắn hơn:

```java
boolean hasUnpaidExpensiveOrder = orders.stream()
    .anyMatch(order ->
        order.amountVnd() >= 1_000_000L && !order.paid()
    );
```

Nhưng phủ định kết quả này **không** chứng minh có đơn đắt tiền: nếu không có đơn nào đạt ngưỡng thì `hasUnpaidExpensiveOrder` vẫn là `false`. Khi yêu cầu có bằng chứng tồn tại, phải kiểm tra thêm.

### 5.3. Chọn theo ý nghĩa nghiệp vụ, không theo độ dài câu lệnh

| Yêu cầu thực tế | Biểu thức | Khi không có ứng viên |
| --- | --- | --- |
| Có ít nhất một ứng viên đạt điều kiện `p` | `anyMatch(p)` | `false` |
| Không có ứng viên nào vi phạm `p` | `allMatch(p)` | `true` |
| Không có ứng viên nào mang đặc tính bị cấm `p` | `noneMatch(p)` | `true` |
| Phải có ứng viên **và** mọi ứng viên đạt `p` | `!candidates.isEmpty() && candidates.stream().allMatch(p)` | `false` |
| Phải có ứng viên **và** không ứng viên nào vi phạm `p` | `!candidates.isEmpty() && candidates.stream().noneMatch(p.negate())` | `false` |

Trong bảng, `candidates` phải là **tập thực sự được đem ra đối sánh**, có thể là kết quả của `filter`. Kiểm tra `!orders.isEmpty()` trước `filter` không đủ nếu `filter` vẫn loại bỏ hết mọi đơn.

## 6. Quan hệ logic giữa các phép đối sánh

Với một điều kiện `p` thuần, không phụ thuộc trạng thái bên ngoài, các quan hệ sau đúng cả trên Stream rỗng lẫn không rỗng:

```text
noneMatch(p)  tương đương  !anyMatch(p)

allMatch(p)   tương đương  !anyMatch(not p)

noneMatch(p)  tương đương  allMatch(not p)
```

Ví dụ về mặt logic (mỗi biểu thức phải chạy với một Stream mới):

```java
import java.util.List;
import java.util.function.Predicate;

List<Integer> values = List.of();
Predicate<Integer> positive = n -> n > 0;

boolean a = values.stream().noneMatch(positive);
boolean b = !values.stream().anyMatch(positive);

boolean c = values.stream().allMatch(positive);
boolean d = !values.stream().anyMatch(positive.negate());

System.out.println(a == b); // true
System.out.println(c == d); // true
System.out.println(c);      // true, vì values rỗng
```

Dấu phủ định `!` thay đổi câu hỏi được hỏi, nhưng **không buộc Stream phải có phần tử**. Bởi vậy, thay `allMatch(p)` bằng `!anyMatch(p.negate())` không giải quyết nhu cầu “ít nhất một phần tử”.

Các tương đương trên giả định điều kiện có ý nghĩa ổn định. Nếu `Predicate` có tác dụng phụ, phụ thuộc thời gian, ngẫu nhiên hoặc trạng thái có thể thay đổi, hai pipeline độc lập có thể quan sát dữ liệu khác nhau. Khi đó, nên sửa thiết kế dữ liệu và điều kiện trước khi dựa vào các biến đổi logic.

## 7. Lazy, dừng sớm và số lần đánh giá Predicate

`filter`, `map` và nhiều thao tác trung gian khác có tính **lazy**; điều kiện trong `anyMatch`, `allMatch` hoặc `noneMatch` chỉ được áp dụng khi terminal operation cần kiểm tra phần tử.

Ba phép đối sánh đều **short-circuit**: có thể dừng ngay khi kết quả đã xác định.

| Phương thức | Có thể dừng khi gặp | Lý do |
| --- | --- | --- |
| `anyMatch(p)` | Một phần tử làm `p` trả về `true` | Đã chứng minh “tồn tại”. |
| `allMatch(p)` | Một phần tử làm `p` trả về `false` | Đã tìm được phản ví dụ. |
| `noneMatch(p)` | Một phần tử làm `p` trả về `true` | Đã bác bỏ “không có ai”. |

Trên Stream rỗng, cả ba phép đối sánh trả về kết quả mà **không có lời gọi nào tới `Predicate.test`**. Trên Stream không rỗng, đừng giả định mọi phần tử đều được kiểm tra.

```java
import java.util.List;

List<Integer> numbers = List.of(2, 4, 6, 7, 8);

boolean hasOdd = numbers.stream()
    .anyMatch(n -> n % 2 != 0); // true; có thể dừng ở số 7

boolean allEven = numbers.stream()
    .allMatch(n -> n % 2 == 0); // false; có thể dừng ở số 7

boolean noOdd = numbers.stream()
    .noneMatch(n -> n % 2 != 0); // false; có thể dừng ở số 7
```

Các ví dụ trên là pipeline tuần tự từ `List` có thứ tự. Với `parallelStream()`, số lượng và thứ tự các lần gọi `Predicate` có thể không giống cách chạy tuần tự; kết quả logic vẫn phải giữ đúng nếu `Predicate` thỏa yêu cầu về tính **stateless** và **non-interfering**.

### Vì sao không nên dùng tác dụng phụ trong Predicate?

Không nên dùng `anyMatch` hoặc `allMatch` làm “vòng lặp ngầm” để cập nhật biến bên ngoài:

```java
int[] inspectedCount = {0};

boolean anyPaid = orders.stream()
    .anyMatch(order -> {
        inspectedCount[0]++; // Không đại diện đáng tin cậy cho tổng số đơn.
        return order.paid();
    });
```

Nếu gặp đơn đã thanh toán sớm, `anyMatch` có thể dừng mà không duyệt hết đơn; trên Stream rỗng, `inspectedCount[0]` vẫn bằng 0; trên Stream song song, việc thay đổi mảng dùng chung có thể gây *data race*. Nếu cần đếm toàn bộ phần tử thỏa điều kiện, dùng `filter(...).count()`; nếu cần tìm một phần tử thì dùng `findFirst` hoặc `findAny` với cách xử lý kết quả rõ ràng.

## 8. Phân biệt đối sánh với tìm kiếm và đếm trên Stream rỗng

Các terminal operation liên quan trả về kiểu dữ liệu khác nhau. Bảng sau dùng một Stream thực sự rỗng:

| Thao tác | Kiểu kết quả | Kết quả khi rỗng |
| --- | --- | --- |
| `anyMatch(p)` | `boolean` | `false` |
| `allMatch(p)` | `boolean` | `true` |
| `noneMatch(p)` | `boolean` | `true` |
| `count()` | `long` | `0L` |
| `findFirst()` | `Optional<T>` | `Optional.empty()` |
| `findAny()` | `Optional<T>` | `Optional.empty()` |
| `IntStream.average()` | `OptionalDouble` | Rỗng |
| `IntStream.sum()` | `int` | `0` |

Đoạn minh họa:

```java
import java.util.Optional;
import java.util.stream.IntStream;
import java.util.stream.Stream;

Optional<String> first = Stream.<String>empty().findFirst();
long count = Stream.<String>empty().count();
boolean any = Stream.<String>empty().anyMatch(s -> s.startsWith("A"));
int total = IntStream.empty().sum();

System.out.println(first.isPresent()); // false
System.out.println(count);             // 0
System.out.println(any);               // false
System.out.println(total);             // 0
```

Đừng dùng `findFirst().isPresent()` chỉ để trả lời “có phần tử thỏa `p` không?” nếu `anyMatch(p)` đã mô tả trực tiếp câu hỏi. `findFirst` phù hợp khi cần **lấy phần tử** để xử lý tiếp, còn `anyMatch` phù hợp khi chỉ cần kết quả `boolean`.

Ngược lại, nếu cần phân biệt “không có dữ liệu để đánh giá” với “có dữ liệu, nhưng tất cả đều trượt”, một `boolean` đơn lẻ từ `anyMatch` không đủ. Có thể ghi nhận thêm `count`, giữ tập ứng viên, hoặc thiết kế kiểu kết quả thể hiện riêng trạng thái **không có dữ liệu**.

### Đặc điểm của Primitive Stream

`IntStream`, `LongStream` và `DoubleStream` cũng có `anyMatch`, `allMatch` và `noneMatch`; chúng nhận các functional interface chuyên biệt như `IntPredicate`. Với nguồn rỗng, bộ ba kết quả vẫn là `false, true, true`:

```java
import java.util.stream.IntStream;

boolean any = IntStream.empty().anyMatch(n -> n > 0);
boolean all = IntStream.empty().allMatch(n -> n > 0);
boolean none = IntStream.empty().noneMatch(n -> n > 0);

System.out.println(any + ", " + all + ", " + none);
// false, true, true
```

Đổi từ `Stream<Integer>` sang `IntStream` bằng `mapToInt` không làm thay đổi ngữ nghĩa logic trên tập rỗng.

## 9. Ví dụ thực tế: kiểm tra tập bản ghi thanh toán

Ví dụ Java 17+ sau dùng `record`, tạo một tập đơn đã đến hạn đối soát và áp dụng chính sách **“có ít nhất một đơn đến hạn, và tất cả đơn đó phải đã thanh toán”**.

```java
import java.util.List;

public class EmptyMatchingDemo {
    record Invoice(String id, boolean due, boolean paid) {}

    static boolean approveDueInvoices(List<Invoice> invoices) {
        // Chỉ xem các hóa đơn đã đến hạn.
        List<Invoice> dueInvoices = invoices.stream()
            .filter(Invoice::due)
            .toList();

        // Điều kiện tồn tại tách riêng điều kiện mọi phần tử đạt chuẩn.
        return !dueInvoices.isEmpty()
            && dueInvoices.stream().allMatch(Invoice::paid);
    }

    static boolean everyDueInvoicePaid(List<Invoice> invoices) {
        // Phát biểu logic này cho phép tập hóa đơn đến hạn rỗng.
        return invoices.stream()
            .filter(Invoice::due)
            .allMatch(Invoice::paid);
    }

    public static void main(String[] args) {
        List<Invoice> empty = List.of();

        List<Invoice> notYetDue = List.of(
            new Invoice("I-01", false, false)
        );

        List<Invoice> allPaid = List.of(
            new Invoice("I-02", true, true),
            new Invoice("I-03", true, true)
        );

        List<Invoice> hasUnpaid = List.of(
            new Invoice("I-04", true, true),
            new Invoice("I-05", true, false)
        );

        System.out.println(approveDueInvoices(empty));      // false
        System.out.println(approveDueInvoices(notYetDue));  // false
        System.out.println(approveDueInvoices(allPaid));    // true
        System.out.println(approveDueInvoices(hasUnpaid));  // false

        System.out.println(everyDueInvoicePaid(empty));     // true
        System.out.println(everyDueInvoicePaid(notYetDue)); // true
        System.out.println(everyDueInvoicePaid(hasUnpaid)); // false
    }
}
```

Ví dụ cho thấy hai chính sách khác nhau:

- **`everyDueInvoicePaid`** phát biểu “không có hóa đơn đến hạn nào chưa thanh toán”. Nếu không có hóa đơn đến hạn, mệnh đề vẫn đúng.
- **`approveDueInvoices`** phát biểu “đã có hóa đơn đến hạn để đối soát, và tất cả đều thanh toán”. Nếu thiếu dữ liệu ứng viên, không phê duyệt.

Cả hai cách viết đều có thể đúng, nhưng đúng cho **hai nghiệp vụ khác nhau**. Trong hệ thống thực, điều kiện “không có bản ghi” còn có thể mang nghĩa “chưa đồng bộ dữ liệu” hoặc “không tìm thấy dữ liệu trong khoảng thời gian được yêu cầu”. Khi đó, việc cho phép phê duyệt hay báo trạng thái chưa đủ dữ liệu phải được xác định rõ trước khi chọn phép đối sánh.

## 10. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `allMatch` để kiểm tra “có ít nhất một và tất cả đều đúng” | Stream rỗng vẫn nhận `true` | Thêm điều kiện không rỗng trên tập ứng viên. |
| Kiểm tra `!source.isEmpty()` nhưng quên `filter` có thể loại hết | Có dữ liệu nguồn nhưng tập được xét rỗng | Kiểm tra sau khi lọc hoặc dùng kiểm tra tồn tại cùng điều kiện lọc. |
| Cho rằng `noneMatch(p)` nghĩa là có phần tử không thỏa `p` | Tập rỗng bị diễn giải sai | Hiểu đúng là **không tồn tại phần tử nào thỏa `p`**. |
| Cho rằng `allMatch(p)` và `noneMatch(p)` không thể cùng đúng | Hiểu sai tính đúng rỗng | Cả hai cùng `true` trên tập rỗng. |
| Thay `allMatch(p)` bằng `!anyMatch(!p)` để xử lý tập rỗng | Vẫn `true` trên tập rỗng | Muốn ít nhất một phần tử phải kiểm tra tồn tại riêng. |
| Dùng lại một Stream để gọi `anyMatch` và `allMatch` | `IllegalStateException` do Stream đã bị tiêu thụ | Tạo Stream mới từ nguồn hoặc lưu tập ứng viên nếu cần. |
| Ghi tác dụng phụ vào `Predicate`, giả định duyệt đủ các phần tử | Đếm sai, hành vi khó dự đoán, lỗi khi song song | Dùng `count` để đếm, tránh trạng thái dùng chung trong phép đối sánh. |
| Xem `false` từ `anyMatch` là bằng chứng có dữ liệu nhưng không phần tử nào đạt | Không phân biệt nguồn rỗng với nguồn không có match | Ghi nhận trạng thái tồn tại dữ liệu nếu nghiệp vụ cần. |
| Bật `parallelStream` rồi phụ thuộc thứ tự chạy của predicate | Kết quả phụ khó đoán, có thể mất an toàn luồng | Dùng predicate thuần, không dựa vào thứ tự hay số lần gọi. |

## 11. Bài tập thực hành

### Bài 1: Dự đoán kết quả khi dữ liệu trống

Cho:

```java
List<Integer> values = List.of();
```

Dự đoán kết quả các biểu thức sau rồi giải thích từng kết quả:

```java
values.stream().allMatch(n -> n > 100);
values.stream().anyMatch(n -> n > 100);
values.stream().noneMatch(n -> n > 100);
values.stream().filter(n -> n < 0).allMatch(n -> n % 2 == 0);
```

Gợi ý: hãy xác định Stream **ngay tại thao tác đối sánh** có bao nhiêu phần tử, thay vì chỉ nhìn biểu thức `Predicate`.

### Bài 2: Nguồn không rỗng, ứng viên rỗng

Cho danh sách đơn hàng có các giá trị `100_000L` và `200_000L`. Lọc đơn có giá trị từ `1_000_000L` trở lên rồi kiểm tra `allMatch(Order::paid)`. Tại sao có thể nhận được `true` dù không có đơn đạt ngưỡng? Hãy thêm điều kiện để yêu cầu **có ít nhất một đơn đủ ngưỡng**.

### Bài 3: Viết chính sách hợp lệ cho nhóm sinh viên

Hệ thống đánh giá nhóm dự án yêu cầu: “Nhóm phải có ít nhất một thành viên, và tất cả thành viên phải có điểm tham gia tối thiểu 60”. Viết hàm nhận `List<Student>` và trả về `boolean`. Kiểm thử ba tình huống: nhóm rỗng, nhóm có một sinh viên đạt và nhóm có một sinh viên trượt.

### Bài 4: Bằng chứng không tồn tại

Viết hai biểu thức tương đương để kiểm tra **không có số âm** trong `List<Integer>`:

1. Sử dụng `noneMatch(n -> n < 0)`.
2. Sử dụng `allMatch(n -> n >= 0)`.

Thử với danh sách rỗng. Sau đó viết lại khi nghiệp vụ yêu cầu **danh sách phải không rỗng và không có số âm**.

### Bài 5: Kiểm chứng tính dừng sớm

Cho `List<Integer>` chứa một số âm ở giữa danh sách. Dự đoán `anyMatch(n -> n < 0)` có cần kiểm tra các phần tử phía sau số âm hay không. Vì sao không nên dùng lambda để tăng một bộ đếm chung rồi coi nó là số phần tử của nguồn?

### Bài 6: Thiết kế trạng thái “không có dữ liệu”

Xây dựng một hàm đánh giá chất lượng lô hàng với ba kết quả: `NO_DATA`, `PASS` và `FAIL`. Đầu vào là `List<Item>`, mỗi phần tử có trạng thái kiểm định. Mô tả cách xác định lô rỗng trước khi dùng `allMatch` để kiểm tra. Vì sao trả về một `boolean` duy nhất có thể không đáp ứng đủ yêu cầu?

## 12. Tự kiểm tra kiến thức

- Vì sao `allMatch` trả về `true` trên Stream rỗng?
- Vì sao `noneMatch` cũng trả về `true` trên cùng Stream đó?
- Nguyên nhân nào khiến `anyMatch` trả về `false` khi Stream không có phần tử?
- Nếu `filter` loại hết dữ liệu, các phép đối sánh tiếp theo trả kết quả ra sao?
- Khi yêu cầu “có ít nhất một phần tử và tất cả đều hợp lệ”, cần bổ sung điều kiện gì?
- `allMatch(p)` có tương đương `!anyMatch(p.negate())` trên Stream rỗng không?
- Vì sao không nên suy ra số phần tử hoặc thứ tự duyệt từ số lần gọi `Predicate`?
- Khi nào cần một kết quả ba trạng thái thay cho `boolean`?

**Ghi nhớ:** Trên Stream rỗng, bộ ba kết quả luôn là **`anyMatch = false`, `allMatch = true`, `noneMatch = true`**. Đây là ngữ nghĩa logic của các phép đối sánh. Khi nghiệp vụ yêu cầu **phải có dữ liệu để xét**, hãy kiểm tra sự tồn tại của tập ứng viên một cách tường minh, đặc biệt nếu pipeline có `filter` hoặc những thao tác có thể tạo ra Stream rỗng.
