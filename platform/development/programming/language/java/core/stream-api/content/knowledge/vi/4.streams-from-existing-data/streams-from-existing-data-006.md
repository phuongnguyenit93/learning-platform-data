# Chuyển Optional thành Stream bằng Optional.stream

## 1. Vấn đề: có thể có một giá trị hoặc không có giá trị

Trong chương **Tạo Stream từ dữ liệu có sẵn** của **JAVA_STREAM_API**, không phải mọi nguồn dữ liệu đều là danh sách, tập hợp hay mảng. Một phương thức truy vấn có thể trả về `Optional<T>` để biểu diễn **có đúng một giá trị hoặc không có giá trị**. Khi muốn kết hợp kết quả truy vấn đó với pipeline khai báo của Java Stream API, `Optional.stream()` là cầu nối trực tiếp.

Ví dụ, một hệ thống tra cứu khách hàng có thể tìm thấy hoặc không tìm thấy số điện thoại. Với một khách hàng, ta có một `Optional<String>`. Với nhiều khách hàng, ta có thể có `Stream<Optional<String>>` và muốn nhận về `Stream<String>` chỉ gồm các số thực sự tồn tại.

~~~text
Optional<T>
  ├── Optional.of(value) ──► stream() ──► Stream<T> chứa 1 phần tử
  └── Optional.empty() ────► stream() ──► Stream<T> rỗng

Stream<Optional<T>>
  └── flatMap(Optional::stream) ─────────► Stream<T>
                                           (bỏ các Optional rỗng)
~~~

**Ý nghĩa chính:** `Optional.stream()` trả về một Stream tuần tự có **0 hoặc 1 phần tử**. Phương thức này được giới thiệu từ **Java 9**. Bài học dùng thêm `Stream.toList()` (có từ Java 16), vì vậy các ví dụ có thể chạy với **Java 17+**.

## 2. Cú pháp và hành vi cơ bản

Chữ ký của phương thức:

~~~java
public Stream<T> stream()
~~~

`Optional<T>.stream()` biến một đối tượng Optional thành một Stream với hai khả năng:

| Optional đầu vào | Kết quả `stream()` | Kết quả `toList()` |
| --- | --- | --- |
| `Optional.of("An")` | Một phần tử `"An"` | `["An"]` |
| `Optional.empty()` | Không có phần tử | `[]` |
| `Optional.ofNullable(null)` | Không có phần tử | `[]` |

Ví dụ:

~~~java
import java.util.List;
import java.util.Optional;

public class BasicOptionalStreamDemo {
    public static void main(String[] args) {
        Optional<String> found = Optional.of("An");
        Optional<String> missing = Optional.empty();

        List<String> one = found.stream().toList();
        List<String> none = missing.stream().toList();

        System.out.println(one);  // [An]
        System.out.println(none); // []
    }
}
~~~

Ở đây không cần gọi `isPresent()` hay `get()` để lấy giá trị trước khi tạo Stream. `Optional.stream()` tự xử lý trường hợp rỗng. Không có phần tử `null` nào được sinh ra khi Optional rỗng.

Một đối tượng `Optional` **không chứa nhiều giá trị**: khi cần một luồng nhiều phần tử, giá trị đó phải đến từ các nguồn khác (ví dụ `List`, `Set`, `Stream.of(...)` hoặc một hàm chuyển một giá trị thành nhiều giá trị). `Optional.stream()` chỉ làm nhiệm vụ nối trường hợp 0–1 phần tử với cơ chế pipeline.

## 3. Ứng dụng quan trọng nhất: làm phẳng Stream của nhiều Optional

Giả sử có danh sách kết quả tra cứu; một số kết quả có giá trị, một số rỗng.

~~~java
import java.util.List;
import java.util.Optional;

List<Optional<String>> maybeNames = List.of(
    Optional.of("An"),
    Optional.empty(),
    Optional.of("Bình"),
    Optional.empty(),
    Optional.of("Chi")
);

List<String> names = maybeNames.stream()
    .flatMap(Optional::stream)
    .toList();

System.out.println(names); // [An, Bình, Chi]
~~~

Các bước của pipeline:

1. `maybeNames.stream()` tạo `Stream<Optional<String>>`.
2. `Optional::stream` gọi phương thức `stream()` trên từng `Optional<String>`, sinh luồng 0 hoặc 1 phần tử.
3. `flatMap(...)` nối các luồng con thành một `Stream<String>` duy nhất.
4. `toList()` là terminal operation thu thập các giá trị hiện diện.

Mô phỏng:

~~~text
[Some("An"), Empty, Some("Bình"), Empty, Some("Chi")]
       │       │         │       │        │
       ▼       ▼         ▼       ▼        ▼
     ["An"]   []     ["Bình"]    []     ["Chi"]
       └───────┴─────────┴───────┴────────┘
                  flatMap
                     ▼
             ["An", "Bình", "Chi"]
~~~

Với nguồn có **encounter order** như `List`, `flatMap(Optional::stream)` bảo toàn thứ tự tương đối của các phần tử còn lại. Nếu nguồn ban đầu không có thứ tự thì kết quả cũng không tự có bảo đảm về thứ tự.

### Vì sao phải dùng `flatMap` thay vì `map`?

~~~java
// Mỗi Optional được đổi thành một Stream con:
var nested = maybeNames.stream()
    .map(Optional::stream); // Stream<Stream<String>>

// Các Stream con được nối thành một Stream các giá trị:
var flattened = maybeNames.stream()
    .flatMap(Optional::stream); // Stream<String>
~~~

`map` ánh xạ **một phần tử đầu vào thành một phần tử đầu ra**: ở đây phần tử đầu ra lại là một `Stream<String>`. `flatMap` vừa ánh xạ sang Stream con vừa làm phẳng chúng. Vì vậy, dạng thường gặp là:

~~~java
Stream<Optional<T>> input = /* nhiều kết quả Optional */;
Stream<T> output = input.flatMap(Optional::stream);
~~~

Ví dụ này mang tính mẫu; mỗi biến `input` cần được khởi tạo bằng nguồn dữ liệu thực tế. Không nên viết `map(Optional::stream).toList()` nếu mục tiêu là lấy danh sách các giá trị `T`, bởi cách đó tạo một danh sách **các Stream con**.

## 4. Kết hợp với `map`, `filter` và `collect` trong bài toán thực tế

Giả sử một khách hàng có thể chưa cung cấp email. Ta muốn tạo danh sách email hợp lệ từ dữ liệu đang có.

~~~java
import java.util.List;
import java.util.Optional;

record Customer(String name, String email) {}

List<Customer> customers = List.of(
    new Customer("An", " an@example.com "),
    new Customer("Bình", null),
    new Customer("Chi", " "),
    new Customer("Dung", "dung@example.com")
);

List<String> emails = customers.stream()
    .map(customer -> Optional.ofNullable(customer.email())
        .map(String::trim)
        .filter(email -> !email.isBlank()))
    .flatMap(Optional::stream)
    .toList();

System.out.println(emails);
// [an@example.com, dung@example.com]
~~~

Ở bước `map`, mỗi `Customer` sinh một `Optional<String>`. Email `null` trở thành `Optional.empty()` nhờ `ofNullable`; email chỉ có khoảng trắng cũng bị loại nhờ `filter` trên Optional. Tiếp theo, `flatMap(Optional::stream)` bỏ Optional rỗng và đưa các giá trị còn lại vào cùng pipeline.

Ta cũng có thể đưa việc tra cứu vào một hàm riêng. Điều này giúp phân biệt **quy tắc chọn dữ liệu** với **cách ghép kết quả**:

~~~java
import java.util.Optional;

static Optional<String> normalizedEmail(Customer customer) {
    return Optional.ofNullable(customer.email())
        .map(String::trim)
        .filter(email -> !email.isBlank());
}

// Trong phương thức sử dụng danh sách customers:
List<String> emails = customers.stream()
    .map(customer -> normalizedEmail(customer))
    .flatMap(Optional::stream)
    .toList();
~~~

Đoạn mã là phần mở rộng của ví dụ `Customer` phía trên: hàm `normalizedEmail` cần được khai báo trong lớp chứa code sử dụng nó. Khi một phương thức đã trả về Optional, tổ hợp `map(...).flatMap(Optional::stream)` giúp tránh những khối `if` lồng nhau.

### So sánh với cách dùng `isPresent()` và `get()`

Trước Java 9, một cách viết thường gặp là:

~~~java
List<String> names = maybeNames.stream()
    .filter(Optional::isPresent)
    .map(Optional::get)
    .toList();
~~~

Cách này có thể cho ra cùng kết quả nếu mọi phần tử của Stream đều là Optional khác `null`, nhưng có hai bước riêng và gọi `get()`. Từ Java 9, có thể viết rõ mục tiêu hơn:

~~~java
List<String> names = maybeNames.stream()
    .flatMap(Optional::stream)
    .toList();
~~~

Không nên gọi `get()` mà chưa kiểm tra tính hiện diện; với Optional rỗng, `get()` ném `NoSuchElementException`.

## 5. Pipeline hoàn chỉnh: lọc mã đầu vào và tính tổng

Một trường hợp phổ biến là chuyển dữ liệu chuỗi không đáng tin cậy thành giá trị số. Hàm parse trả `Optional<Integer>` vì một chuỗi có thể không hợp lệ hoặc không đạt điều kiện.

Ví dụ sau là chương trình có thể biên dịch và chạy độc lập bằng Java 17+:

~~~java
import java.util.List;
import java.util.Optional;

public class ParseIdsWithOptionalStream {
    static Optional<Integer> parsePositiveId(String raw) {
        if (raw == null) {
            return Optional.empty();
        }

        try {
            int id = Integer.parseInt(raw.trim());
            return id > 0 ? Optional.of(id) : Optional.empty();
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<String> rawIds = List.of("12", "abc", "-5", " 7 ", "0", "30");

        List<Integer> validIds = rawIds.stream()
            .map(ParseIdsWithOptionalStream::parsePositiveId)
            .flatMap(Optional::stream)
            .toList();

        int total = validIds.stream()
            .mapToInt(Integer::intValue)
            .sum();

        System.out.println(validIds); // [12, 7, 30]
        System.out.println(total);    // 49
    }
}
~~~

Trong bài toán này:

- `map` chuyển từng chuỗi thành một kết quả tra cứu/chuyển đổi có thể vắng mặt.
- `flatMap(Optional::stream)` giữ lại các số nguyên dương được parse thành công.
- `toList` trả về danh sách kết quả; `mapToInt(...).sum()` tính tổng qua phép toán terminal riêng.

Nếu chỉ cần tổng, có thể giữ tất cả trong **một pipeline**:

~~~java
int total = rawIds.stream()
    .map(ParseIdsWithOptionalStream::parsePositiveId)
    .flatMap(Optional::stream)
    .mapToInt(Integer::intValue)
    .sum(); // 49
~~~

Tùy yêu cầu nghiệp vụ, một kết quả parse thất bại có thể cần được ghi nhận thành lỗi thay vì tự động bị bỏ qua. Khi đó, không nên dùng `Optional.stream()` để âm thầm loại tất cả giá trị vắng mặt; hãy thiết kế kiểu kết quả chứa nguyên nhân lỗi hoặc xử lý dữ liệu không hợp lệ trước khi thu thập.

## 6. Phân biệt `Optional.stream()` với `Stream.ofNullable()` và `Optional.flatMap()`

Ba phương thức đều hữu ích khi xử lý dữ liệu có thể vắng mặt, nhưng **đầu vào và đầu ra khác nhau**.

| Phương thức | Áp dụng lên | Kết quả | Sử dụng khi |
| --- | --- | --- | --- |
| `Optional<T>.stream()` | Một `Optional<T>` | `Stream<T>` chứa 0 hoặc 1 phần tử | Muốn đưa Optional vào pipeline Stream. |
| `Stream.ofNullable(value)` | Một tham chiếu `T` có thể là `null` | `Stream<T>` chứa 0 hoặc 1 phần tử | Nguồn dữ liệu trực tiếp có thể là `null`. |
| `Optional<T>.flatMap(f)` | Một `Optional<T>` | `Optional<U>` | Muốn ghép các phép tra cứu trả về Optional và **vẫn giữ kết quả dạng Optional**. |
| `Stream<T>.flatMap(f)` | Một `Stream<T>` | `Stream<U>` | Muốn nối nhiều Stream con thành một Stream. |

### `Stream.ofNullable` dành cho một tham chiếu có thể là `null`

~~~java
import java.util.List;
import java.util.stream.Stream;

String nickname = null;

List<String> values = Stream.ofNullable(nickname).toList();
// []
~~~

`Stream.ofNullable` cũng có từ Java 9. Phương thức này rất phù hợp khi API cũ trả về `null`, nhưng nếu đã có `Optional<String>` thì `optional.stream()` diễn đạt trực tiếp hơn và không cần `orElse(null)`.

### `Optional.flatMap` giữ kiểu Optional

~~~java
import java.util.List;
import java.util.Optional;

record Profile(Optional<String> phone) {}

Optional<Profile> maybeProfile = Optional.of(
    new Profile(Optional.of("0900000000"))
);

Optional<String> maybePhone = maybeProfile.flatMap(Profile::phone);
// Optional chứa "0900000000"

List<String> phones = maybePhone.stream().toList();
// ["0900000000"]
~~~

Ở đây `Optional.flatMap` không tạo Stream: nó nối hai phép tính có kết quả là Optional. Chỉ khi cần chuyển sang pipeline Stream mới sử dụng `Optional.stream()`.

## 7. Optional của kiểu nguyên thủy cũng có `stream()`

Java có ba kiểu Optional chuyên biệt: `OptionalInt`, `OptionalLong`, `OptionalDouble`. Từ Java 9, các kiểu này cũng hỗ trợ `stream()`, nhưng trả về primitive stream tương ứng.

| Đầu vào | Phương thức | Kiểu trả về |
| --- | --- | --- |
| `OptionalInt` | `stream()` | `IntStream` |
| `OptionalLong` | `stream()` | `LongStream` |
| `OptionalDouble` | `stream()` | `DoubleStream` |

Ví dụ gom các phép đo có thể bị thiếu:

~~~java
import java.util.List;
import java.util.OptionalInt;

List<OptionalInt> readings = List.of(
    OptionalInt.of(15),
    OptionalInt.empty(),
    OptionalInt.of(27),
    OptionalInt.of(8)
);

int sum = readings.stream()
    .flatMapToInt(OptionalInt::stream)
    .sum();

System.out.println(sum); // 50
~~~

Dùng `flatMapToInt` thay vì `flatMap` vì các Stream con có kiểu `IntStream`. Cùng nguyên tắc, `Stream<OptionalLong>` có thể dùng `flatMapToLong(OptionalLong::stream)` và `Stream<OptionalDouble>` có thể dùng `flatMapToDouble(OptionalDouble::stream)`. Cách này giữ dữ liệu ở dạng primitive, tránh phải đóng hộp từng phần tử thành `Integer`, `Long` hoặc `Double`.

## 8. Kết hợp với pipeline lazy, terminal operation và thứ tự phần tử

`Optional.stream()` tạo ra một Stream, nên các quy tắc vòng đời của Stream API vẫn áp dụng:

- `filter`, `map` và `flatMap` là intermediate operations; pipeline thường được xử lý **lazily** khi có terminal operation.
- `toList`, `collect`, `count`, `sum` và `findFirst` là những terminal operations thường gặp.
- Một Stream đã dùng terminal operation thì không được tái sử dụng; nếu cần một phép tính khác, hãy tạo Stream mới từ nguồn hoặc giữ kết quả trong collection.
- `findFirst`, `anyMatch` và các phép toán short-circuit khác có thể kết thúc sớm; đừng dùng tác dụng phụ trong hàm ánh xạ Optional để đếm chắc chắn số phần tử đã xử lý.

Ví dụ tìm email hợp lệ đầu tiên từ danh sách ở mục 4:

~~~java
Optional<String> firstEmail = customers.stream()
    .map(customer -> Optional.ofNullable(customer.email())
        .map(String::trim)
        .filter(email -> !email.isBlank()))
    .flatMap(Optional::stream)
    .findFirst();

// Optional chứa "an@example.com".
~~~

`findFirst()` trả về `Optional<String>` vì pipeline có thể không còn email nào sau khi loại các Optional rỗng. Với nguồn có encounter order như `List`, kết quả là giá trị đầu tiên thỏa mãn theo thứ tự đó. Việc Stream được phép dừng sớm là lý do không nên dựa vào số lần gọi của bước `map` để ghi nhận hoạt động nghiệp vụ.

### Tài nguyên và thực thi song song

Bản thân `Optional.stream()` không mở file hoặc kết nối, và chỉ chứa tối đa một giá trị. Nhưng nếu nguồn bên ngoài pipeline là một Stream từ file hay tài nguyên I/O, trách nhiệm đóng tài nguyên đó vẫn còn; dùng `try-with-resources` khi API nguồn yêu cầu.

Nếu Stream bên ngoài chạy song song, các phép tra cứu tạo Optional phải tuân thủ hợp đồng **không can thiệp** và **không trạng thái** của các lambda dùng trong Stream API. Việc `Optional.stream()` tạo luồng 0–1 phần tử không biến lời gọi I/O, cập nhật cơ sở dữ liệu hay ghi biến dùng chung thành an toàn để song song hóa. Chỉ dùng parallel stream khi công việc đủ lớn, độc lập và đã đo được lợi ích.

## 9. Các lỗi và hiểu nhầm thường gặp

### Lỗi 1: tưởng `Optional.stream()` tự làm phẳng cả collection

~~~java
List<Optional<Integer>> items = List.of(
    Optional.of(1), Optional.empty(), Optional.of(3)
);

// SAI MỤC TIÊU: tạo Stream<Stream<Integer>>.
var nested = items.stream().map(Optional::stream);

// ĐÚNG: tạo Stream<Integer>, sau đó có thể collect.
List<Integer> values = items.stream()
    .flatMap(Optional::stream)
    .toList(); // [1, 3]
~~~

### Lỗi 2: trả về `null` thay cho `Optional.empty()`

~~~java
// Không viết hàm kiểu này:
// Optional<String> lookup(int id) {
//     return id > 0 ? Optional.of("ok") : null;
// }

// Hàm trả Optional phải trả chính Optional:
static Optional<String> lookup(int id) {
    return id > 0 ? Optional.of("ok") : Optional.empty();
}
~~~

`Optional.stream()` xử lý **Optional rỗng**, không xử lý một tham chiếu **Optional bằng null**. Nếu phần tử của `Stream<Optional<T>>` là `null`, `flatMap(Optional::stream)` sẽ ném `NullPointerException` khi gọi phương thức trên phần tử đó. Giải pháp đúng ở tầng API là duy trì hợp đồng trả về Optional thực sự.

### Lỗi 3: coi thiếu dữ liệu và dữ liệu lỗi là tương đương

`flatMap(Optional::stream)` loại bỏ cả những kết quả `Optional.empty()`. Đây là hành vi đúng khi nghiệp vụ cho phép bỏ giá trị thiếu (ví dụ chỉ lấy những email đã được cung cấp). Tuy nhiên, nếu việc thiếu giá bắt buộc phải báo lỗi để ngăn thanh toán, thì tự động lọc bỏ dòng đơn hàng là sai logic.

Ví dụ, khi không tìm được giá sản phẩm cần **dừng xử lý**:

~~~java
import java.util.Map;

Map<String, Long> prices = Map.of(
    "BOOK", 100_000L,
    "PEN", 10_000L
);

List<String> skus = List.of("BOOK", "UNKNOWN", "PEN");

// Ở bài toán này, thiếu giá là lỗi thay vì một giá trị được phép bỏ:
List<Long> requiredPrices = skus.stream()
    .map(sku -> Optional.ofNullable(prices.get(sku))
        .orElseThrow(() -> new IllegalArgumentException("Thiếu giá: " + sku)))
    .toList();

// Ném IllegalArgumentException tại SKU "UNKNOWN".
~~~

Vì vậy, trước khi flatten, hãy hỏi: **Optional rỗng có nghĩa là phần tử này được phép bỏ qua không?** Nếu câu trả lời là không, cần xử lý lỗi ở nơi phát sinh hoặc giữ thông tin thiếu để báo cáo.

### Lỗi 4: mong đợi `toList()` là danh sách có thể chỉnh sửa

Từ Java 16, `Stream.toList()` trả danh sách không sửa đổi được. Vì vậy:

~~~java
List<String> selected = maybeNames.stream()
    .flatMap(Optional::stream)
    .toList();

// selected.add("Dung"); // UnsupportedOperationException.
~~~

Nếu cần chỉnh sửa kết quả, dùng collector tạo collection có thể thay đổi:

~~~java
import java.util.ArrayList;
import java.util.stream.Collectors;

ArrayList<String> mutable = maybeNames.stream()
    .flatMap(Optional::stream)
    .collect(Collectors.toCollection(ArrayList::new));

mutable.add("Dung"); // Hợp lệ.
~~~

## 10. Nên sử dụng `Optional.stream()` khi nào?

| Tình huống | Cách viết phù hợp | Lý do |
| --- | --- | --- |
| Một truy vấn có thể không trả kết quả | `maybeValue.stream()` | Đưa trường hợp 0–1 giá trị vào Stream. |
| Danh sách `Optional<T>` | `list.stream().flatMap(Optional::stream)` | Thu các giá trị hiện diện về một Stream. |
| Mỗi phần tử cần tra cứu một giá trị tùy chọn | `source.stream().map(this::lookup).flatMap(Optional::stream)` | Kết hợp truy vấn và loại giá trị vắng mặt. |
| Một tham chiếu Java có thể bằng `null` | `Stream.ofNullable(value)` | Tạo Stream 0–1 trực tiếp từ tham chiếu. |
| Kết quả là `OptionalInt` | `flatMapToInt(OptionalInt::stream)` | Xử lý số nguyên bằng primitive stream. |
| Giá trị thiếu là lỗi nghiệp vụ | `orElseThrow(...)` hoặc kiểu kết quả có lỗi | Không âm thầm loại dữ liệu bắt buộc. |

## 11. Câu hỏi tự kiểm tra

1. **`Optional.empty().stream().count()` trả bao nhiêu?** Trả `0` vì Stream không có phần tử.
2. **`Optional.of(42).stream().findFirst()` trả kiểu gì?** Trả `Optional<Integer>` chứa `42`.
3. **Vì sao `map(Optional::stream)` không đủ để thu các giá trị?** Vì kết quả của `map` là `Stream<Stream<T>>`; dùng `flatMap` để nối các Stream con.
4. **Khi nào dùng `flatMapToInt(OptionalInt::stream)`?** Khi đầu vào là `Stream<OptionalInt>` và muốn một `IntStream` để tính toán bằng kiểu nguyên thủy.
5. **Có nên dùng `Optional.stream()` để bỏ bản ghi thanh toán không tìm thấy giá?** Không, nếu thiếu giá là lỗi cần thông báo; flatten sẽ loại bản ghi đó khỏi kết quả mà không mang theo nguyên nhân.
6. **Dùng `Optional.stream()` có nghĩa là source Stream sẽ tự đóng tài nguyên I/O không?** Không; vẫn cần quản lý vòng đời của nguồn có tài nguyên, ví dụ với `try-with-resources`.

**Ghi nhớ:** `Optional.stream()` nối mô hình **0 hoặc 1 giá trị** của Optional với mô hình **0 đến nhiều phần tử** của Stream. Với nhiều Optional, công thức quan trọng nhất là `streamOfOptionals.flatMap(Optional::stream)`. Khi kết hợp với `filter`, `map`, `reduce` hoặc `collect`, công thức này làm pipeline khai báo rõ ràng và chỉ giữ những giá trị thực sự hiện diện, với điều kiện nghiệp vụ cho phép bỏ giá trị vắng mặt.
