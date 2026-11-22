# Xử lý kết quả vắng mặt bằng ifPresent và orElseThrow

## 1. Vì sao kết quả Stream có thể vắng mặt?

Trong **Java Stream API**, pipeline mô tả việc đọc dữ liệu từ nguồn, lọc bằng `filter`, biến đổi bằng `map` rồi kết thúc bằng các thao tác như `findFirst`, `findAny`, `min`, `max` hoặc `reduce`. Một số thao tác kết thúc không thể bảo đảm luôn tìm được giá trị: nguồn có thể rỗng, hoặc mọi phần tử đã bị lọc bỏ.

Ví dụ, tìm đơn hàng đầu tiên đã thanh toán:

```java
import java.util.List;
import java.util.Optional;

record Order(String id, boolean paid) {}

List<Order> orders = List.of(
        new Order("O-01", false),
        new Order("O-02", true)
);

Optional<Order> found = orders.stream()
        .filter(Order::paid)
        .findFirst();

System.out.println(found); // Optional[Order[id=O-02, paid=true]]
```

Nếu không có đơn nào thỏa `Order::paid`, `findFirst()` trả về **`Optional.empty()`**. Nó không trả về một đối tượng `Order` hợp lệ và cũng không yêu cầu tự tạo giá trị `null` để thể hiện sự vắng mặt.

`Optional<T>` là kiểu bao chứa **có thể có một giá trị `T` hoặc không có giá trị**. Trong chương **Optional trong kết quả Stream**, hai thao tác trung tâm của bài này là:

- `ifPresent(Consumer)`: **có giá trị thì thực hiện một hành động**, vắng mặt thì không thực hiện hành động đó.
- `orElseThrow(...)`: **có giá trị thì lấy giá trị**, vắng mặt thì ném ngoại lệ theo chính sách đã chọn.

Đây là hai cách xử lý kết quả mang ý nghĩa nghiệp vụ khác nhau: một hành động có thể bỏ qua khi không có dữ liệu, hoặc một yêu cầu bắt buộc phải có dữ liệu để tiếp tục.

**Mục tiêu bài học:** nhận diện kết quả Stream nào là Optional, sử dụng đúng `ifPresent`, `ifPresentOrElse` và `orElseThrow`, phân biệt chúng với `orElse`/`orElseGet`, xử lý `OptionalInt`/`OptionalLong`/`OptionalDouble`, và tránh lỗi `null`, tác dụng phụ hay giả định sai khi pipeline chạy song song.

Các ví dụ hoàn chỉnh sử dụng **Java 17+**. `Optional.ifPresent` và `Optional.orElseThrow(Supplier)` đã có từ Java 8; `ifPresentOrElse` có từ Java 9; `Optional.orElseThrow()` không tham số có từ Java 10. `Stream.toList()` có từ Java 16.

## 2. Những terminal operation trả về Optional

`Optional` xuất hiện khi kết quả có thể không tồn tại một cách hợp lệ:

| Terminal operation | Kiểu trả về | Khi nào rỗng? |
| --- | --- | --- |
| `findFirst()` | `Optional<T>` | Stream không còn phần tử nào. |
| `findAny()` | `Optional<T>` | Stream không còn phần tử nào. |
| `min(comparator)` | `Optional<T>` | Stream rỗng. |
| `max(comparator)` | `Optional<T>` | Stream rỗng. |
| `reduce(BinaryOperator<T>)` | `Optional<T>` | Stream rỗng, không có identity. |
| `IntStream.min()` / `max()` | `OptionalInt` | Primitive stream rỗng. |
| `LongStream.min()` / `max()` | `OptionalLong` | Primitive stream rỗng. |
| `DoubleStream.average()` | `OptionalDouble` | Không có phần tử nào để tính trung bình. |

Ngược lại, không phải mọi terminal operation đều trả về Optional. Ví dụ `count()` luôn trả về `long` (bằng `0` nếu rỗng); `collect(Collectors.toList())` tạo danh sách, có thể là danh sách rỗng; `reduce(identity, accumulator)` trả về một giá trị với `identity` làm điểm khởi đầu.

```java
List<Integer> values = List.of();

Optional<Integer> max = values.stream()
        .max(Integer::compareTo);
long count = values.stream().count();
int sumWithIdentity = values.stream()
        .reduce(0, Integer::sum);

System.out.println(max);             // Optional.empty
System.out.println(count);           // 0
System.out.println(sumWithIdentity); // 0
```

Mỗi lần gọi `values.stream()` tạo một Stream mới. **Một Stream đã chạy terminal operation không thể sử dụng lại**; chính đối tượng `Optional` được tạo ra sau terminal operation thì có thể được kiểm tra hoặc xử lý nhiều lần khi cần.

## 3. ifPresent: có kết quả mới thực hiện hành động

Chữ ký:

```java
void ifPresent(Consumer<? super T> action)
```

`ifPresent` nhận một `Consumer`, tức hàm **nhận giá trị nhưng không trả về kết quả**. Nếu Optional có giá trị, consumer được gọi với giá trị đó; nếu rỗng, consumer không được gọi.

```java
List<String> codes = List.of("A-01", "B-02", "A-03");

codes.stream()
        .filter(code -> code.startsWith("B-"))
        .findFirst()
        .ifPresent(code -> System.out.println("Đã tìm thấy: " + code));

// Đã tìm thấy: B-02
```

Nếu thay điều kiện bằng `code.startsWith("X-")`, không có dòng nào được in ra và **không có ngoại lệ** chỉ vì kết quả rỗng.

### Lưu Optional trong biến để đọc ý định

Với logic không quá ngắn, tách việc tìm kiếm và việc xử lý thường dễ bảo trì:

```java
Optional<String> firstMatching = codes.stream()
        .filter(code -> code.startsWith("A-"))
        .findFirst();

firstMatching.ifPresent(code -> {
    System.out.println("Mã phù hợp: " + code);
    // Có thể ghi nhận một sự kiện hoặc thông báo nếu nghiệp vụ cho phép.
});
```

`ifPresent` phù hợp khi **không tìm thấy cũng là trạng thái chấp nhận được**, ví dụ chỉ gửi thông báo nếu có kết quả, chỉ cập nhật giao diện nếu có một lựa chọn hoặc chỉ ghi log khi tìm được bản ghi.

### Không thể dùng ifPresent để trả về giá trị

Vì kiểu trả về là `void`, đoạn mã sau **không biên dịch**:

```java
// SAI: ifPresent trả về void.
// String id = firstMatching.ifPresent(System.out::println);
```

Nếu cần lấy một giá trị để trả về từ phương thức, hãy dùng `orElseThrow`, `orElse`, `orElseGet` hoặc giữ Optional trong kiểu trả về để lớp gọi quyết định. Nếu muốn **biến đổi** giá trị đang có, dùng `Optional.map` thay vì cố gắng gán biến bên ngoài từ consumer.

## 4. ifPresentOrElse: xử lý cả hai nhánh

`ifPresent` không có hành động khi rỗng. Nếu phải phản hồi cho cả hai trường hợp, từ **Java 9** có thể dùng:

```java
void ifPresentOrElse(Consumer<? super T> action, Runnable emptyAction)
```

Ví dụ:

```java
Optional<String> code = codes.stream()
        .filter(value -> value.startsWith("X-"))
        .findFirst();

code.ifPresentOrElse(
        value -> System.out.println("Tìm thấy " + value),
        () -> System.out.println("Không tìm thấy mã yêu cầu")
);

// Không tìm thấy mã yêu cầu
```

Nhánh đầu là `Consumer<String>`, nhận giá trị tìm được. Nhánh sau là `Runnable`, không nhận giá trị; nó chỉ chạy khi Optional rỗng.

| Phương thức | Khi có giá trị | Khi không có giá trị | Có trả về giá trị không? |
| --- | --- | --- | --- |
| `ifPresent(action)` | Gọi `action(value)` | Không làm gì | Không, `void` |
| `ifPresentOrElse(action, emptyAction)` | Gọi `action(value)` | Gọi `emptyAction.run()` | Không, `void` |
| `orElseThrow()` | Trả về `value` | Ném `NoSuchElementException` | Có, `T` |
| `orElseThrow(exceptionSupplier)` | Trả về `value` | Ném ngoại lệ do supplier tạo | Có, `T` |

Nếu nhánh vắng mặt phải **dừng luồng xử lý vì dữ liệu bắt buộc thiếu**, `orElseThrow` diễn đạt mục đích rõ hơn một consumer có tác dụng phụ.

## 5. orElseThrow: yêu cầu bắt buộc phải có dữ liệu

Có hai dạng thường gặp trên `Optional<T>`:

```java
T orElseThrow() // Java 10+

<X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X
```

### 5.1. orElseThrow() không tham số

`orElseThrow()` trả về `T` nếu có giá trị; nếu rỗng, nó ném `NoSuchElementException`:

```java
List<String> names = List.of("An", "Bình", "Chi");

String firstLongName = names.stream()
        .filter(name -> name.length() >= 4)
        .findFirst()
        .orElseThrow();

System.out.println(firstLongName); // Bình
```

Nếu thay điều kiện thành `name.length() > 20`, không có tên phù hợp và terminal operation `findFirst` trả về Optional rỗng; khi xử lý Optional, `orElseThrow()` sẽ ném `NoSuchElementException`.

Với dự án cần hỗ trợ Java 8 hoặc Java 9, có thể dùng dạng có supplier:

```java
String required = names.stream()
        .filter(name -> name.equals("Bình"))
        .findFirst()
        .orElseThrow(NoSuchElementException::new);
```

Đoạn trên cần `import java.util.NoSuchElementException;`.

### 5.2. orElseThrow(Supplier) với ngoại lệ mang ý nghĩa nghiệp vụ

Khi cần thông báo rõ dữ liệu nào bị thiếu, hãy cung cấp hàm tạo ngoại lệ:

```java
String requestedCode = "X-01";

String foundCode = codes.stream()
        .filter(code -> code.equals(requestedCode))
        .findFirst()
        .orElseThrow(() -> new NoSuchElementException(
                "Không tìm thấy mã: " + requestedCode
        ));
```

Đoạn trên sẽ ném `NoSuchElementException` với thông điệp `"Không tìm thấy mã: X-01"`. Nếu hệ thống có ngoại lệ chuyên biệt như `OrderNotFoundException` hoặc `CustomerNotFoundException`, có thể tạo loại ngoại lệ đó để tầng gọi xử lý thích hợp.

**Supplier chỉ được gọi khi Optional rỗng.** Trường hợp có giá trị, phương thức trả về giá trị mà không tạo đối tượng ngoại lệ. Vì vậy, ta có thể đặt thông tin ngữ cảnh trong thông điệp lỗi mà không phải trả chi phí xây dựng lỗi ở nhánh thành công.

### Ngoại lệ checked và unchecked

Chữ ký generic của `orElseThrow(Supplier)` cho phép ném cả ngoại lệ **checked** và **unchecked**. Nếu supplier tạo ngoại lệ checked, phương thức gọi phải khai báo hoặc bắt ngoại lệ đó theo quy tắc Java:

```java
import java.io.FileNotFoundException;
import java.util.Optional;

static String requirePath(Optional<String> path)
        throws FileNotFoundException {
    return path.orElseThrow(
            () -> new FileNotFoundException("Thiếu đường dẫn đầu vào")
    );
}
```

Chỉ nên dùng ngoại lệ checked khi API nghiệp vụ muốn yêu cầu bên gọi xử lý rõ ràng. Với một bản ghi không tồn tại trong ứng dụng, nhiều hệ thống chọn ngoại lệ unchecked riêng để tầng dịch vụ hoặc HTTP quyết định phản hồi.

## 6. Chọn ifPresent hay orElseThrow theo ý nghĩa nghiệp vụ

Không có một phương thức luôn đúng cho mọi Optional. Hãy quyết định **vắng mặt có phải lỗi hay không**:

| Tình huống | Cách xử lý gợi ý | Lý do |
| --- | --- | --- |
| Tìm mã khuyến mãi tùy chọn để in thông báo | `ifPresent` | Không có khuyến mãi thì có thể tiếp tục. |
| Hiển thị trạng thái tìm kiếm, kể cả không có kết quả | `ifPresentOrElse` | Hai nhánh đều có hành động hiển thị. |
| Đọc cấu hình bắt buộc trước khi khởi chạy | `orElseThrow` | Thiếu cấu hình phải làm luồng xử lý thất bại. |
| Tìm đơn hàng theo ID để thực hiện giao dịch | `orElseThrow(() -> ...)` | Thiếu đơn hàng cần lỗi có thông điệp/loại rõ ràng. |
| Tính trung bình số liệu có thể rỗng | Xử lý `OptionalDouble` rõ ràng | Vắng mẫu là trường hợp dữ liệu hợp lệ cần định nghĩa. |
| API dịch vụ cho phép không có bản ghi | Trả về `Optional<T>` | Bên gọi có đủ ngữ cảnh để chọn hành vi. |

Ví dụ cùng một nguồn nhưng khác nghiệp vụ:

```java
Optional<String> maybeCoupon = List.of("WELCOME", "VIP").stream()
        .filter(code -> code.equals("VIP"))
        .findFirst();

// Mã tùy chọn: có thì áp dụng.
maybeCoupon.ifPresent(code ->
        System.out.println("Áp dụng khuyến mãi: " + code));

// Mã bắt buộc: thiếu thì dừng.
String requiredCoupon = maybeCoupon.orElseThrow(
        () -> new IllegalStateException("Thiếu mã khuyến mãi bắt buộc")
);
```

Ở đây cả hai cách đều hoạt động vì Optional có giá trị. Nhưng sự khác biệt sẽ thể hiện ngay khi mã `VIP` không tồn tại.

## 7. orElseThrow khác gì với get, orElse và orElseGet?

`Optional.get()` cũng lấy giá trị hoặc ném `NoSuchElementException` nếu rỗng. Tuy nhiên, `orElseThrow()` truyền đạt rõ hơn rằng vắng mặt là một trạng thái đã được cân nhắc, còn `orElseThrow(Supplier)` cho phép mô tả lỗi chính xác.

Ba phương thức được dùng khi cần giá trị:

```java
Optional<String> optional = Optional.of("primary");

String required = optional.orElseThrow();          // "primary"
String fallback = optional.orElse("default");      // "primary"
String computed = optional.orElseGet(() -> "fallback"); // "primary"
```

Khác biệt chính là **chiến lược khi Optional rỗng**:

| Cách dùng | Có giá trị | Rỗng |
| --- | --- | --- |
| `orElseThrow()` | Trả về giá trị | Ném `NoSuchElementException` |
| `orElseThrow(() -> new X(...))` | Trả về giá trị | Tạo và ném ngoại lệ `X` |
| `orElse(fallback)` | Trả về giá trị | Trả về `fallback` |
| `orElseGet(supplier)` | Trả về giá trị | Gọi supplier để tạo giá trị dự phòng |

### Khác biệt về thời điểm tạo giá trị dự phòng

Đối số của `orElse(...)` là biểu thức Java thông thường, nên **được đánh giá ngay khi gọi phương thức**, ngay cả khi Optional đã có giá trị:

```java
static String slowFallback() {
    System.out.println("Tạo giá trị dự phòng");
    return "fallback";
}

// Ví dụ bên trong cùng lớp:
Optional<String> present = Optional.of("ready");

String a = present.orElse(slowFallback());
// In ra "Tạo giá trị dự phòng" dù a vẫn là "ready".

String b = present.orElseGet(() -> slowFallback());
// Không gọi slowFallback() khi Optional có giá trị.

String c = present.orElseThrow(
        () -> new IllegalStateException("Không có dữ liệu"));
// Không tạo ngoại lệ trong nhánh có giá trị.
```

Vì `orElseGet` và `orElseThrow(Supplier)` dùng supplier, phần xử lý dự phòng hoặc tạo ngoại lệ chạy **theo nhu cầu**. Đừng chọn `orElseThrow` khi nghiệp vụ cho phép dùng giá trị mặc định; ngược lại, đừng gán giá trị mặc định để che giấu việc thiếu dữ liệu bắt buộc.

## 8. Kết hợp filter, map và Optional trước khi xử lý kết quả

`Optional` có `filter` và `map` riêng để tiếp tục kiểm tra hoặc biến đổi **một giá trị có thể vắng mặt**, không phải để khởi động lại Stream:

```java
record Customer(String id, String email, boolean active) {}

List<Customer> customers = List.of(
        new Customer("C-01", "an@example.com", false),
        new Customer("C-02", " binh@example.com ", true),
        new Customer("C-03", "chi@example.com", true)
);

String email = customers.stream()
        .filter(Customer::active)
        .findFirst()                    // Optional<Customer>
        .map(Customer::email)           // Optional<String>
        .map(String::strip)
        .filter(value -> !value.isEmpty())
        .orElseThrow(() -> new IllegalStateException(
                "Không có email hợp lệ của khách đang hoạt động"
        ));

System.out.println(email); // binh@example.com
```

Diễn giải từng bước:

1. `filter(Customer::active)` lọc Stream khách hàng.
2. `findFirst()` là terminal operation và trả về `Optional<Customer>`.
3. `Optional.map(Customer::email)` chỉ chạy nếu có khách; nó tạo `Optional<String>`.
4. `Optional.map(String::strip)` chuẩn hóa email; `Optional.filter` loại chuỗi rỗng.
5. `orElseThrow` chỉ ném lỗi nếu bất kỳ giai đoạn nào dẫn đến Optional rỗng.

Một điểm cần hiểu: khi mapper của **`Optional.map`** trả về `null`, kết quả là `Optional.empty()`. Ngược lại, **`Stream.map`** có thể sinh phần tử `null`; các terminal operation `findFirst` hoặc `findAny` có thể ném `NullPointerException` nếu phần tử được chọn là `null`.

Nếu dữ liệu nguồn Stream có thể chứa `null`, hãy quy định cách xử lý trước khi tìm kiếm:

```java
import java.util.Arrays;
import java.util.Objects;

List<String> rawNames = Arrays.asList(null, " An ", "Bình");

Optional<String> firstValid = rawNames.stream()
        .filter(Objects::nonNull)
        .map(String::strip)
        .filter(name -> !name.isBlank())
        .findFirst();

firstValid.ifPresent(System.out::println); // An
```

`Optional.of(null)` ném `NullPointerException`. `Optional.ofNullable(null)` tạo `Optional.empty()`, nhưng **không cần bọc lại bằng `ofNullable` một kết quả đã có kiểu `Optional<T>`**.

## 9. OptionalInt, OptionalLong và OptionalDouble

Các primitive stream dùng dạng Optional chuyên biệt để không phải boxing những số nguyên thủy thành `Integer`, `Long` hoặc `Double`:

```java
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.OptionalDouble;
import java.util.stream.IntStream;
import java.util.stream.LongStream;
import java.util.stream.DoubleStream;

OptionalInt smallest = IntStream.of(7, 3, 9).min();
OptionalLong largest = LongStream.of(2L, 8L, 5L).max();
OptionalDouble average = DoubleStream.of(2.0, 4.0, 6.0).average();

smallest.ifPresent(value -> System.out.println("Nhỏ nhất: " + value));
largest.ifPresent(value -> System.out.println("Lớn nhất: " + value));
average.ifPresent(value -> System.out.println("Trung bình: " + value));

int minRequired = smallest.orElseThrow();        // 3
long maxRequired = largest.orElseThrow();        // 8
double averageRequired = average.orElseThrow();  // 4.0
```

Với `OptionalInt`, `OptionalLong` và `OptionalDouble`, `ifPresent` lần lượt nhận `IntConsumer`, `LongConsumer`, `DoubleConsumer`. Các dạng `orElseThrow()` **không tham số** có từ Java 10 và ném `NoSuchElementException` khi rỗng.

Chúng **không có overload `orElseThrow(exceptionSupplier)`** như `Optional<T>`. Nếu cần lỗi chuyên biệt từ một kết quả primitive, có thể chuyển sang đối tượng Optional hoặc xử lý trạng thái rỗng trong API có ý nghĩa nghiệp vụ.

Ví dụ muốn ném lỗi theo ngữ cảnh:

```java
OptionalInt quantity = IntStream.empty().max();

int requiredQuantity = quantity.stream()
        .boxed()
        .findFirst()
        .orElseThrow(() -> new IllegalStateException(
                "Không có số lượng để chọn"
        ));
```

Đoạn minh họa chuyển qua `OptionalInt.stream()` (Java 9), `boxed()` rồi `Optional<Integer>` để sử dụng overload có supplier; cách làm này có chi phí boxing nhỏ. Khi không cần loại ngoại lệ đặc biệt, dùng thẳng `quantity.orElseThrow()` đơn giản hơn.

### Trường hợp không có số nào

```java
OptionalDouble noAverage = IntStream.empty().average();

noAverage.ifPresentOrElse(
        value -> System.out.println("Trung bình: " + value),
        () -> System.out.println("Chưa có mẫu để tính trung bình")
);

// Chưa có mẫu để tính trung bình
```

`OptionalInt`, `OptionalLong` và `OptionalDouble` cũng có `ifPresentOrElse` từ Java 9. Chọn phản hồi phù hợp với nghiệp vụ: trung bình không tồn tại khác với trung bình bằng `0`.

## 10. findFirst, findAny, thứ tự và xử lý song song

Kết quả có hay không có giá trị là một khía cạnh; **giá trị nào được chọn** là khía cạnh khác.

```java
List<Integer> numbers = List.of(2, 4, 6, 8);

Optional<Integer> first = numbers.stream()
        .filter(n -> n > 3)
        .findFirst(); // Optional[4]

Optional<Integer> any = numbers.parallelStream()
        .filter(n -> n > 3)
        .findAny();  // Có thể là 4, 6 hoặc 8.
```

Với Stream có encounter order như `List.stream()`, `findFirst` tìm phần tử đầu tiên trong thứ tự đó. `findAny` được phép chọn một phần tử bất kỳ; đặc biệt khi chạy song song, **không được dựa vào một phần tử cố định**.

`orElseThrow` chỉ quyết định điều gì xảy ra **khi Optional rỗng**, không thay đổi quy tắc chọn giá trị của `findAny`. Nếu nghiệp vụ yêu cầu ưu tiên theo ngày, giá trị lớn nhất hay mã nhỏ nhất, cần định nghĩa thứ tự hoặc comparator thích hợp trước:

```java
int smallestGreaterThanThree = numbers.stream()
        .filter(n -> n > 3)
        .min(Integer::compareTo)
        .orElseThrow(); // 4
```

`ifPresent` được gọi **sau khi terminal operation trả về Optional**; bản thân consumer trên Optional không phải là thao tác xử lý song song từng phần tử Stream. Đừng đặt cập nhật nguồn hoặc logic dựa trên thứ tự gọi lambda ngay trong `filter`/`map` của pipeline song song.

## 11. Ví dụ hoàn chỉnh: tìm giao dịch và phản hồi theo nghiệp vụ

Một dịch vụ quản lý giao dịch có hai nhu cầu:

- **Tùy chọn:** nếu có giao dịch đã hoàn tất của khách, in thông báo về giao dịch mới tìm được.
- **Bắt buộc:** khi xử lý một yêu cầu tra cứu giao dịch cụ thể, phải có giao dịch phù hợp; nếu thiếu, ném lỗi mang ngữ cảnh.

Ví dụ Java 17+:

```java
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.Comparator;

public class OptionalStreamResultDemo {
    record Payment(String id, String customerId, long cents, boolean successful) {}

    static Optional<Payment> findAnySuccessfulForCustomer(
            List<Payment> payments, String customerId) {
        return payments.stream()
                .filter(Payment::successful)
                .filter(payment -> payment.customerId().equals(customerId))
                .findFirst();
    }

    static Payment requireSuccessfulPayment(
            List<Payment> payments, String paymentId) {
        return payments.stream()
                .filter(payment -> payment.id().equals(paymentId))
                .filter(Payment::successful)
                .findFirst()
                .orElseThrow(() -> new NoSuchElementException(
                        "Không tìm thấy giao dịch thành công: " + paymentId
                ));
    }

    public static void main(String[] args) {
        List<Payment> payments = List.of(
                new Payment("P01", "C01", 120_000L, true),
                new Payment("P02", "C02", 75_000L, false),
                new Payment("P03", "C01", 50_000L, true)
        );

        // Tùy chọn: không có kết quả thì bỏ qua thông báo.
        findAnySuccessfulForCustomer(payments, "C01")
                .ifPresent(payment -> System.out.println(
                        "Có giao dịch: " + payment.id()
                ));
        // Có giao dịch: P01

        // Hai nhánh hiển thị khi cần biết cả trường hợp không tồn tại.
        findAnySuccessfulForCustomer(payments, "C03")
                .ifPresentOrElse(
                        payment -> System.out.println(payment.id()),
                        () -> System.out.println("Khách C03 chưa có giao dịch")
                );
        // Khách C03 chưa có giao dịch

        // Bắt buộc: trả về Payment hoặc ném NoSuchElementException.
        Payment required = requireSuccessfulPayment(payments, "P03");
        System.out.println("Số tiền: " + required.cents()); // 50000

        // Một kết quả khác có thể rỗng: giao dịch thành công có số tiền lớn nhất.
        payments.stream()
                .filter(Payment::successful)
                .max(Comparator.comparingLong(Payment::cents))
                .ifPresent(payment -> System.out.println(
                        "Giao dịch cao nhất: " + payment.id()
                ));
        // Giao dịch cao nhất: P01
    }
}
```

Ở đây, `findAnySuccessfulForCustomer` là tên phương thức nghiệp vụ minh họa sự tồn tại của giao dịch: **bên trong dùng `findFirst`**, nên nếu muốn tên phản ánh chính xác thuật toán, có thể đổi thành `findFirstSuccessfulForCustomer`. Điều quan trọng là hợp đồng trả về `Optional<Payment>` để bên gọi quyết định việc vắng mặt có chấp nhận được không.

Nhận xét:

1. `findFirst` trên danh sách có thứ tự sẽ chọn giao dịch phù hợp đầu tiên, nhưng không mặc nhiên là **mới nhất** nếu danh sách không được sắp theo thời gian.
2. `ifPresent` chỉ phục vụ hành động phụ khi có kết quả; khi khách `C03` chưa có giao dịch thì hành động hiển thị riêng được đặt vào `ifPresentOrElse`.
3. `requireSuccessfulPayment` dùng `orElseThrow` và thông điệp chứa mã giao dịch, nên nơi gọi có thể xử lý ngoại lệ chính xác hơn.
4. `max` trả về Optional vì sau `filter` có thể không còn giao dịch thành công nào.
5. Các pipeline chỉ đọc `payments`, không thêm/xóa phần tử trong khi duyệt. Nếu dữ liệu được cập nhật đồng thời, cần cơ chế đồng bộ hoặc snapshot phù hợp với nghiệp vụ.

Trong ứng dụng thật, không nên xem việc tìm theo `id` là đã đảm bảo quyền truy cập; tầng dịch vụ vẫn cần thực hiện các điều kiện phân quyền và trạng thái giao dịch theo thiết kế hệ thống.

## 12. Lỗi thường gặp và cách sửa

| Lỗi hoặc biểu hiện | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Gọi `get()` rồi gặp `NoSuchElementException` | Không kiểm tra Optional có giá trị. | Dùng `ifPresent` khi tùy chọn, `orElseThrow` khi bắt buộc. |
| Muốn gán biến từ `ifPresent` nhưng không biên dịch | `ifPresent` trả về `void`. | Dùng `map`, `orElseThrow` hoặc trả về Optional. |
| Không thấy thông báo khi dữ liệu vắng mặt | `ifPresent` chỉ xử lý nhánh có giá trị. | Dùng `ifPresentOrElse` nếu cần hai nhánh. |
| Nhánh ngoại lệ bị thực thi ngay cả khi có dữ liệu | Tạo lỗi trước và gây tác dụng phụ trong biểu thức khác. | Đặt tạo lỗi bên trong supplier của `orElseThrow`. |
| `orElse(expensiveMethod())` gọi hàm dù có giá trị | Đối số được đánh giá trước khi gọi `orElse`. | Dùng `orElseGet` cho giá trị dự phòng tính chậm. |
| `findFirst` hoặc `findAny` ném `NullPointerException` | Stream có phần tử `null` được chọn. | Xử lý `null` trước terminal operation, chẳng hạn `filter(Objects::nonNull)`. |
| `findAny` trả về phần tử khác nhau | Không cam kết chọn phần tử cố định, nhất là song song. | Dùng `findFirst` hoặc `min`/`max` theo quy tắc nghiệp vụ. |
| Gọi `orElseThrow(Supplier)` trên `OptionalInt` không biên dịch | Primitive Optional không có overload có supplier. | Dùng `orElseThrow()` hoặc xử lý lỗi chuyên biệt qua Optional đối tượng. |
| Bị hiểu nhầm trung bình vắng mặt là `0` | `average()` có thể trả về `OptionalDouble.empty()`. | Phân biệt chưa có mẫu với kết quả thực bằng 0. |
| Dùng lại Stream sau `findFirst` | Stream đã kết thúc và bị tiêu thụ. | Tạo Stream mới từ nguồn hoặc xử lý kết quả Optional đã có. |

## 13. Bài tập thực hành

Cho danh sách điểm của học viên:

```java
record Student(String code, int score, boolean active) {}

List<Student> students = List.of(
        new Student("SV01", 8, true),
        new Student("SV02", 4, false),
        new Student("SV03", 9, true)
);
```

Yêu cầu:

1. Tìm học viên đầu tiên đang hoạt động, dùng `ifPresent` in mã học viên nếu tìm được.
2. Tìm học viên có mã `"SV99"`, dùng `ifPresentOrElse` để in một trong hai thông báo.
3. Viết hàm `requireStudent` nhận danh sách và mã học viên, trả về học viên hoặc ném `NoSuchElementException` có thông điệp chứa mã.
4. Tìm điểm cao nhất của học viên đang hoạt động bằng primitive stream; dùng `ifPresent` để in kết quả và `orElseThrow()` khi bài toán bắt buộc phải có điểm.
5. Thử thay `students` bằng danh sách rỗng và giải thích hành vi của từng trường hợp.

**Lời giải tham khảo:**

```java
students.stream()
        .filter(Student::active)
        .findFirst()
        .ifPresent(student -> System.out.println(student.code()));
// SV01

students.stream()
        .filter(student -> student.code().equals("SV99"))
        .findFirst()
        .ifPresentOrElse(
                student -> System.out.println("Có: " + student.code()),
                () -> System.out.println("Không thấy SV99")
        );
// Không thấy SV99

static Student requireStudent(List<Student> source, String code) {
    return source.stream()
            .filter(student -> student.code().equals(code))
            .findFirst()
            .orElseThrow(() -> new NoSuchElementException(
                    "Không tìm thấy học viên " + code
            ));
}

OptionalInt maxScore = students.stream()
        .filter(Student::active)
        .mapToInt(Student::score)
        .max();

maxScore.ifPresent(score -> System.out.println("Điểm cao nhất: " + score));
int requiredMax = maxScore.orElseThrow(); // 9
```

Đoạn lời giải cần các `import` tương ứng từ `java.util` và `java.util.stream`; hàm `requireStudent` đặt ở cấp lớp, không khai báo bên trong phương thức `main`. Với danh sách rỗng, hai đoạn `ifPresent` không có hành động, `ifPresentOrElse` chạy nhánh vắng mặt, còn cả hai dạng `orElseThrow` sẽ ném ngoại lệ nếu được gọi.

**Tự mở rộng:** Nếu API có cả "không thấy học viên" và "học viên đã bị vô hiệu hóa", có nên lọc trạng thái trước `findFirst` hay tìm theo mã trước rồi kiểm tra trạng thái? Hai cách tạo thông báo lỗi khác nhau; hãy chọn dựa trên hợp đồng nghiệp vụ, không chỉ dựa vào sự ngắn gọn của pipeline.

## Ghi nhớ

Khi một terminal operation của Stream có thể không tìm được phần tử, kết quả thường là `Optional<T>` hoặc các dạng `OptionalInt`, `OptionalLong`, `OptionalDouble`. `ifPresent` phù hợp cho **hành động tùy chọn khi có giá trị**; `ifPresentOrElse` phù hợp khi cần phản hồi cả lúc vắng mặt; `orElseThrow` phù hợp khi **bắt buộc phải có giá trị để tiếp tục**. Supplier của `orElseThrow` chỉ tạo ngoại lệ trong nhánh rỗng. Hãy giữ sự khác biệt giữa "không có dữ liệu" và "có giá trị bằng 0", cẩn thận với `null` và encounter order, đồng thời thiết kế ngoại lệ theo ý nghĩa nghiệp vụ thay vì mặc định coi mọi kết quả rỗng là lỗi.
