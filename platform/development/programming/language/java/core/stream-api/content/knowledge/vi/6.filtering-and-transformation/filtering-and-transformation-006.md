# Làm phẳng Optional và loại bỏ kết quả không tồn tại

Trong Java Stream API, không phải phép biến đổi nào cũng trả về một giá trị hợp lệ. Khi tra cứu tài khoản, phân tích chuỗi số, đọc cấu hình hoặc chọn bản ghi thỏa điều kiện, một phần tử đầu vào có thể cho ra **một kết quả** hoặc **không có kết quả**. `Optional<T>` mô tả trường hợp đó mà không buộc người đọc mã phải xem `null` là tín hiệu vắng mặt.

Bài học thuộc chương **Lọc và biến đổi phần tử** của module `JAVA_STREAM_API`. Trọng tâm là kết hợp pipeline lazy với `Optional`: ánh xạ từng phần tử thành `Optional<T>`, làm phẳng các kết quả tồn tại bằng `flatMap(Optional::stream)` và tiếp tục xử lý qua `filter`, `map`, `reduce` hoặc `collect`. Ngoài cú pháp, cần nắm rõ số lượng phần tử sau biến đổi, thứ tự, vòng đời pipeline, phiên bản JDK và ranh giới giữa dữ liệu không tồn tại với dữ liệu không hợp lệ.

## 1. Vì sao cần làm phẳng Optional trong Stream?

Giả sử có ba chuỗi `"12"`, `"không-phải-số"` và `"7"`. Hàm chuyển chuỗi thành số nguyên có thể trả về `Optional<Integer>`:

- `Optional.of(12)` khi phân tích thành công;
- `Optional.empty()` khi chuỗi không phải số;
- `Optional.of(7)` khi phân tích thành công.

Nếu dùng `map` để gọi hàm, ta nhận được **Stream chứa các Optional**, tức `Stream<Optional<Integer>>`. Đây vẫn là ba phần tử, kể cả phần tử biểu diễn thất bại. Muốn bỏ các Optional rỗng để tiếp tục xử lý số nguyên, cần biến mỗi Optional thành một Stream có **0 hoặc 1** phần tử rồi làm phẳng:

```text
Stream<String>
 ["12", "không-phải-số", "7"]
            │ map(parseInteger)
            ▼
Stream<Optional<Integer>>
 [Optional[12], Optional.empty, Optional[7]]
            │ flatMap(Optional::stream)
            ▼
Stream<Integer>
 [12, 7]
            │ filter / map / collect / sum ...
            ▼
Kết quả chỉ chứa giá trị tồn tại
```

`Optional.stream()`, có từ **Java 9**, là chiếc cầu nối này. Nếu Optional chứa giá trị, nó trả Stream gồm đúng giá trị đó; nếu Optional rỗng, nó trả Stream rỗng.

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<String> present = Optional.of("hello");
Optional<String> absent = Optional.empty();

System.out.println(present.stream().count()); // 1
System.out.println(absent.stream().count());  // 0
```

Bảng phân biệt các thao tác:

| Biểu thức | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| `Stream<T>.map(T -> Optional<R>)` | `Stream<Optional<R>>` | Mỗi đầu vào vẫn sinh một Optional |
| `Optional<R>.stream()` | `Stream<R>` | Một Optional chuyển thành 0 hoặc 1 phần tử |
| `Stream<Optional<R>>.flatMap(Optional::stream)` | `Stream<R>` | Bỏ các Optional rỗng và lấy giá trị hiện diện |
| `Stream<T>.flatMap(T -> Stream<R>)` | `Stream<R>` | Mỗi đầu vào có thể sinh 0, 1 hoặc nhiều phần tử |
| `Optional<T>.flatMap(T -> Optional<R>)` | `Optional<R>` | Kết hợp phép biến đổi **bên trong một Optional**, tránh lồng Optional |

Hai phương thức cùng tên `flatMap` có đối tượng nhận khác nhau: `Stream.flatMap` làm phẳng các Stream con, còn `Optional.flatMap` làm phẳng Optional con.

## 2. Ví dụ từ đầu đến cuối: phân tích các chuỗi số

Trước hết viết một hàm chuyển đổi an toàn. Đây là ví dụ cho trường hợp **chuỗi không phải số hợp lệ được coi là không có kết quả**, không phải lỗi hệ thống.

```java
import java.util.Optional;

static Optional<Integer> parseInteger(String text) {
    try {
        return Optional.of(Integer.parseInt(text));
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
```

`Integer.parseInt` cũng ném `NumberFormatException` khi đầu vào là `null`. Trong ví dụ này, `null` không xuất hiện trong danh sách đầu vào; nếu API có thể nhận `null`, cần quy định rõ đó là lỗi của người gọi hay một đầu vào được phép bỏ qua.

Kết hợp với Stream:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

List<String> inputs = Arrays.asList("12", "x", "-3", "7");

List<Integer> numbers = inputs.stream()
        .map(YourClass::parseInteger)
        .flatMap(Optional::stream)
        .collect(Collectors.toList());

System.out.println(numbers); // [12, -3, 7]
```

`YourClass::parseInteger` là tên lớp ví dụ: đặt `parseInteger` trong lớp của bạn rồi thay `YourClass` bằng tên lớp thực tế, hoặc dùng lambda `text -> parseInteger(text)` trong cùng phạm vi.

Từng bước có vai trò riêng:

1. `inputs.stream()` tạo nguồn có encounter order từ `List`.
2. `map(...)` chuyển **từng chuỗi** thành `Optional<Integer>`; phần tử `"x"` tạo `Optional.empty()`.
3. `flatMap(Optional::stream)` bỏ Optional rỗng và phát ra các số tồn tại.
4. `collect(...)` là terminal operation, kích hoạt việc xử lý, giữ kết quả vào danh sách.

Sau `flatMap`, phần sau của pipeline làm việc trực tiếp với `Integer`, không phải với `Optional<Integer>`. Việc lọc không làm xáo trộn thứ tự gặp phần tử của danh sách đầu vào.

### Chuyển thành Stream số nguyên thủy để tính toán

```java
int total = inputs.stream()
        .map(text -> parseInteger(text))
        .flatMap(Optional::stream)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 16 (12 + -3 + 7)
```

`mapToInt` chuyển `Stream<Integer>` sang `IntStream`, cho phép gọi `sum`, `average`, `summaryStatistics` mà không phải viết `reduce` trên kiểu boxed `Integer`.

Có thể viết gọn hơn khi hàm chuyển đổi nằm cùng lớp:

```java
long countValid = inputs.stream()
        .map(text -> parseInteger(text))
        .flatMap(Optional::stream)
        .count();

System.out.println(countValid); // 3
```

Ở đây `countValid` đếm **số giá trị được phân tích thành công**, không phải số chuỗi ban đầu.

## 3. Kết hợp map và flatMap khi tra cứu dữ liệu

Ví dụ gần với nghiệp vụ: đơn hàng lưu một mã khách hàng; việc tra cứu có thể thất bại vì mã không tồn tại. Hàm repository trả về `Optional<Customer>`:

```java
// record được hỗ trợ chính thức từ Java 16.
record Order(String customerId, long amount) {}
record Customer(String id, String email) {}

interface CustomerRepository {
    Optional<Customer> findById(String id);
}
```

Lấy email của các khách hàng thực sự tồn tại:

```java
List<Order> orders = List.of(
        new Order("c01", 100),
        new Order("unknown", 200),
        new Order("c03", 150)
);

// repo là một CustomerRepository đã được khởi tạo.
List<String> emails = orders.stream()
        .map(order -> repo.findById(order.customerId()))
        .flatMap(Optional::stream)
        .map(Customer::email)
        .toList();
```

Trong ví dụ này:

- `map` biến mỗi `Order` thành `Optional<Customer>`.
- `flatMap` loại bỏ lần tra cứu không thấy khách hàng.
- `map(Customer::email)` chỉ nhận những `Customer` hợp lệ, nên không cần `isPresent()` hoặc `get()`.
- `toList()` có từ **Java 16**, trả danh sách không hỗ trợ thay đổi phần tử. Khi dùng Java 8–15, thay bằng `collect(Collectors.toList())` nếu cần.

Nếu thao tác tra cứu chạm cơ sở dữ liệu cho từng đơn hàng, số lượt gọi vẫn có thể lớn (*N+1 queries*). `flatMap(Optional::stream)` chỉ giải quyết hình dạng dữ liệu; nó **không** tự tối ưu số truy vấn I/O. Với danh sách đơn hàng lớn, nên cân nhắc tải dữ liệu theo lô hoặc join tại nguồn.

### Loại bỏ dữ liệu không tồn tại rồi tiếp tục lọc

Giả sử chỉ cần email của khách hàng có đuôi `@example.org`:

```java
List<String> emails = orders.stream()
        .map(order -> repo.findById(order.customerId()))
        .flatMap(Optional::stream)
        .map(Customer::email)
        .filter(email -> email.endsWith("@example.org"))
        .toList();
```

Thứ tự diễn đạt nghiệp vụ rất rõ: tra cứu → bỏ kết quả vắng mặt → lấy email → lọc email. Đây là lợi ích lớn của việc **làm phẳng sớm**, thay vì kéo `Optional` qua nhiều bước xử lý phía sau.

## 4. Tránh Optional lồng nhau: Optional.flatMap và Stream.flatMap

Hai tầng Optional có thể xuất hiện khi đầu vào đã là `Optional<T>` và hàm biến đổi cũng trả về `Optional<R>`:

```java
Optional<String> raw = Optional.of("42");

// map tạo Optional<Optional<Integer>>:
Optional<Optional<Integer>> nested = raw.map(
        text -> parseInteger(text)
);

// flatMap trên Optional không tạo tầng lồng nhau:
Optional<Integer> parsed = raw.flatMap(
        text -> parseInteger(text)
);
```

`Optional.flatMap` (Java 8) thích hợp khi bạn đang xử lý **một giá trị tùy chọn**. `Stream.flatMap(Optional::stream)` (Java 9+) thích hợp khi bạn có **nhiều giá trị tùy chọn** trong một pipeline.

Kết hợp hai cấp trong bài toán thực tế:

```java
record Profile(Optional<String> phone) {}
record Account(String id, Optional<Profile> profile) {}

List<Account> accounts = List.of(
        new Account("u01", Optional.of(
                new Profile(Optional.of("0900000001"))
        )),
        new Account("u02", Optional.empty()),
        new Account("u03", Optional.of(
                new Profile(Optional.empty())
        ))
);

List<String> phones = accounts.stream()
        .map(Account::profile)                 // Stream<Optional<Profile>>
        .flatMap(Optional::stream)             // Stream<Profile>
        .map(Profile::phone)                   // Stream<Optional<String>>
        .flatMap(Optional::stream)             // Stream<String>
        .toList();

System.out.println(phones); // [0900000001]
```

Khi có nhiều tầng giá trị có thể vắng mặt, lặp lại cặp `map` + `flatMap(Optional::stream)` cho từng tầng sẽ dễ hiểu hơn việc gọi `get()` ở những nơi có thể nhận `Optional.empty()`.

Nếu dữ liệu chỉ là **một** tài khoản thì không cần tạo Stream:

```java
Optional<String> phone = accounts.get(0)
        .profile()
        .flatMap(Profile::phone);
```

Ở đây `Profile::phone` trả `Optional<String>` nên dùng `Optional.flatMap` để không nhận `Optional<Optional<String>>`.

## 5. Phân biệt Optional.empty, null và Stream rỗng

Ba trạng thái dưới đây liên quan nhưng không giống nhau.

| Dạng dữ liệu | Giá trị biểu diễn vắng mặt | Cách xử lý |
| --- | --- | --- |
| `Optional<T>` | `Optional.empty()` | `optional.stream()` cho Stream rỗng |
| `T` cho phép `null` | `null` | `Stream.ofNullable(value)` hoặc `filter(Objects::nonNull)` |
| `Stream<T>` | `Stream.empty()` | Đã là Stream rỗng, có thể nối hoặc làm phẳng trực tiếp |

### Optional.ofNullable xử lý null ở đầu vào

```java
import java.util.Optional;
import java.util.stream.Stream;

String email = null;

Optional<String> maybeEmail = Optional.ofNullable(email);
System.out.println(maybeEmail.isPresent()); // false

long count = maybeEmail.stream().count();
System.out.println(count); // 0
```

`Optional.of(nonNullValue)` tạo Optional có giá trị; `Optional.of(null)` ném `NullPointerException`. `Optional.ofNullable(value)` tạo Optional rỗng khi `value == null`.

Lưu ý: `Optional` bản thân nó phải là một **đối tượng không null**. Không được biểu diễn một Optional rỗng bằng cách trả `null` từ hàm được khai báo là `Optional<T>`. Nếu một Stream thực sự chứa phần tử `null` tại chỗ đáng lẽ phải chứa Optional, biểu thức `flatMap(Optional::stream)` có thể ném `NullPointerException`.

### Khi đầu vào là giá trị nullable, có thể dùng Stream.ofNullable

Từ Java 9, `Stream.ofNullable(value)` trả Stream có một phần tử nếu `value != null`, hoặc Stream rỗng nếu `value == null`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

List<String> names = Arrays.asList("An", null, "Chi");

List<String> presentNames = names.stream()
        .flatMap(Stream::ofNullable)
        .toList();

System.out.println(presentNames); // [An, Chi]
```

Bài toán này không cần tạo một `Optional` cho từng tên; đầu vào hiện đang là giá trị có thể null. Khi API đã công khai trả `Optional<T>`, dùng `Optional::stream` mới khớp hợp đồng.

Nếu chỉ muốn bỏ `null`, cách quen thuộc từ Java 8 là:

```java
import java.util.Objects;

List<String> filtered = names.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

Không nên nhầm `Optional.empty()` với giá trị `null` nằm **trong Stream**. Ví dụ `Stream<Optional<T>>` có một phần tử là `Optional.empty()`; lọc bằng `Objects::nonNull` **không loại bỏ** phần tử đó vì đối tượng Optional vẫn không null.

## 6. Không có Optional.stream trên Java 8 thì làm thế nào?

`Optional` đã có trong **Java 8**, nhưng phương thức `Optional.stream()` chỉ xuất hiện từ **Java 9**. Nếu dự án đang chạy Java 8, có hai cách tương đương để bỏ các Optional rỗng.

**Cách 1: lọc rồi lấy giá trị.**

```java
import java.util.Optional;
import java.util.stream.Collectors;

List<Integer> valid = inputs.stream()
        .map(text -> parseInteger(text))
        .filter(Optional::isPresent)
        .map(Optional::get)
        .collect(Collectors.toList());
```

Mẫu này an toàn vì `get()` chỉ được gọi **sau** điều kiện `isPresent` trên đúng pipeline. Tuy nhiên, nếu tách bước hoặc tái sắp xếp thao tác mà thiếu điều kiện lọc, `get()` sẽ ném `NoSuchElementException` khi gặp Optional rỗng. Từ Java 9, `flatMap(Optional::stream)` ngắn và ít gây nhầm lẫn hơn.

**Cách 2: chuyển Optional thành Stream bằng lambda.**

```java
List<Integer> valid = inputs.stream()
        .map(text -> parseInteger(text))
        .flatMap(opt -> opt
                .map(Stream::of)
                .orElseGet(Stream::empty))
        .collect(Collectors.toList());
```

Đây là cách viết Java 8, tương đương ý tưởng `Optional::stream`: có giá trị thì tạo Stream một phần tử; không có giá trị thì dùng Stream rỗng.

Không viết `.map(Optional::get)` trực tiếp trên `Stream<Optional<T>>` nếu chưa loại các Optional rỗng. Cũng không dùng `.map(Optional::orElse(null))` chỉ để thay kết quả vắng mặt bằng null: như vậy lại tạo nhu cầu xử lý null ở những bước sau.

## 7. OptionalInt, OptionalLong, OptionalDouble và Stream nguyên thủy

Khi xử lý lượng lớn số nguyên, số dài hoặc số thực, Java có các kiểu `OptionalInt`, `OptionalLong` và `OptionalDouble`. Từ Java 9, chúng cũng có `stream()`, trả `IntStream`, `LongStream` và `DoubleStream` tương ứng.

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

static OptionalInt parseNonNegative(String text) {
    try {
        int value = Integer.parseInt(text);
        return value >= 0
                ? OptionalInt.of(value)
                : OptionalInt.empty();
    } catch (NumberFormatException ex) {
        return OptionalInt.empty();
    }
}

int total = Stream.of("10", "bad", "-5", "7")
        .map(text -> parseNonNegative(text))
        .flatMapToInt(OptionalInt::stream)
        .sum();

System.out.println(total); // 17
```

Ở đây `map` tạo `Stream<OptionalInt>`, còn `flatMapToInt` loại các OptionalInt rỗng và sinh `IntStream`. Dùng `flatMapToLong(OptionalLong::stream)` hoặc `flatMapToDouble(OptionalDouble::stream)` theo nguyên tắc tương tự.

Khi nguồn dữ liệu và phép tính có thể ở dạng nguyên thủy xuyên suốt, các Stream nguyên thủy có thể hạn chế việc boxing/unboxing so với `Stream<Integer>` hoặc `Stream<Double>`. Đó là một lựa chọn về kiểu dữ liệu và hiệu năng, không làm thay đổi quy tắc loại bỏ kết quả vắng mặt.

## 8. Lựa chọn thay thế: mapMulti từ Java 16

`Stream.mapMulti`, có từ **Java 16**, cho phép phần tử đầu vào gọi một `Consumer` để phát ra 0, 1 hoặc nhiều phần tử. Với Optional, có thể phát trực tiếp giá trị hiện diện mà không tạo Stream con:

```java
import java.util.Optional;
import java.util.stream.Stream;

List<Integer> numbers = Stream.of(
        Optional.of(3),
        Optional.<Integer>empty(),
        Optional.of(8)
).<Integer>mapMulti((maybe, downstream) ->
        maybe.ifPresent(downstream)
).toList();

System.out.println(numbers); // [3, 8]
```

`mapMulti` đặc biệt hữu ích khi phép biến đổi phát sinh số phần tử nhỏ hoặc phụ thuộc điều kiện và không muốn tạo nhiều Stream con. Tuy nhiên, trong bài toán chỉ cần loại `Optional.empty()`, `flatMap(Optional::stream)` thường là cách diễn đạt ngắn gọn, trực tiếp và dễ nhận diện nhất.

| Kỹ thuật | JDK tối thiểu | Ưu điểm | Khi chọn |
| --- | --- | --- | --- |
| `filter(Optional::isPresent).map(Optional::get)` | 8 | Tương thích dự án cũ | Cần Java 8 |
| `flatMap(opt -> opt.map(Stream::of).orElseGet(Stream::empty))` | 8 | Bảo toàn cách tư duy Stream 0/1 | Cần Java 8 nhưng thích cách làm phẳng |
| `flatMap(Optional::stream)` | 9 | Gọn, đúng ý nghĩa loại Optional rỗng | Lựa chọn thông dụng từ Java 9 |
| `mapMulti((opt, out) -> opt.ifPresent(out))` | 16 | Phát giá trị trực tiếp, linh hoạt | Có Java 16+, cần nhiều nhánh phát phần tử |

Không có quy tắc một kỹ thuật luôn nhanh nhất. Với pipeline xử lý I/O hoặc truy vấn database, thời gian chủ yếu có thể nằm ở nguồn dữ liệu; nên đo đạc trên khối lượng thực tế trước khi tối ưu vì một chi tiết cài đặt.

## 9. Hành vi lazy, thứ tự và các lỗi dễ mắc

`map` và `flatMap` là thao tác trung gian, về nguyên tắc được đánh giá *lazy*: khai báo pipeline không lập tức gọi `parseInteger` cho toàn bộ dữ liệu. Terminal operation kích hoạt xử lý; toán tử ngắn mạch có thể làm ngừng sớm.

```java
List<String> inputs = List.of("bad", "12", "x", "7", "99");

Optional<Integer> firstValid = inputs.stream()
        .map(text -> parseInteger(text))
        .flatMap(Optional::stream)
        .findFirst();

System.out.println(firstValid); // Optional[12]
```

Ở pipeline tuần tự từ `List` có encounter order, `findFirst()` trả số hợp lệ đầu tiên. Những chuỗi sau `"12"` không cần được phân tích để trả kết quả. Tuy nhiên, cách Stream thực thi có thể thay đổi tùy đặc tính nguồn, thao tác có trạng thái và parallel; không dùng hàm biến đổi có tác dụng phụ như tăng biến dùng chung, ghi dữ liệu quan trọng hay thay đổi cấu trúc nguồn.

### Bộ lọc làm biến mất dữ liệu: cần xác định lý do

`Optional.empty()` không phân biệt được giữa “không tìm thấy”, “không hợp lệ” và “không có quyền truy cập” nếu tất cả đều bị ánh xạ thành rỗng. Chỉ dùng Optional rỗng để bỏ phần tử khi việc loại bỏ đó là **hành vi nghiệp vụ dự kiến**.

Ví dụ `parseInteger` coi `NumberFormatException` là chuỗi không hợp lệ, nhưng một lỗi kết nối database khi `findById` không nhất thiết được phép chuyển thành `Optional.empty()`. Nếu cần thống kê hoặc hiển thị nguyên nhân thất bại, nên dùng mô hình kết quả có phân loại lỗi (ví dụ kiểu `Result` riêng), hoặc lưu số lỗi/trường hợp bị bỏ qua theo cách rõ ràng ở bên ngoài pipeline. Không lạm dụng `peek` hay đột biến biến đếm dùng chung như cơ chế ghi nhận chính, nhất là khi xử lý song song.

### Bảng lỗi thường gặp

| Cách viết hoặc giả định | Vì sao sai hoặc dễ gây lỗi | Cách sửa |
| --- | --- | --- |
| `stream.map(parse).map(Optional::get)` | Có thể gọi `get()` trên Optional rỗng | Dùng `flatMap(Optional::stream)` |
| `stream.filter(Objects::nonNull)` với `Stream<Optional<T>>` | Không loại `Optional.empty()` | Làm phẳng Optional |
| `stream.map(Optional::stream)` | Sinh `Stream<Stream<T>>`, chưa phải dữ liệu phẳng | Dùng `flatMap` |
| `opt.map(this::lookup)` với `lookup` trả Optional | Tạo Optional lồng Optional | Dùng `Optional.flatMap` |
| Hàm trả `null` thay vì `Optional.empty()` | Phá hợp đồng trả Optional và có thể gây NPE | Luôn trả Optional không null |
| Dùng `Optional::stream` trên Java 8 | Phương thức chưa có trong Java 8 | Dùng fallback Java 8 |
| Giả định phần tử mất đi là lỗi bị bỏ qua an toàn | Có thể che khuất lỗi nghiệp vụ hoặc hệ thống | Phân biệt vắng mặt dự kiến và thất bại cần xử lý |
| Dùng `forEach` trên parallel và kỳ vọng thứ tự | `forEach` không bảo đảm encounter order | Dùng `forEachOrdered` nếu cần thứ tự |
| Dùng lại một `Stream` sau terminal operation | Pipeline dùng một lần | Tạo Stream mới từ nguồn nếu cần chạy lại |

`flatMap(Optional::stream)` không tự đóng các tài nguyên khác ngoài các Stream con mà chính nó quản lý. Nếu nguồn ngoài là `Files.lines`, `Files.walk` hoặc một Stream I/O cần đóng, vẫn phải dùng `try-with-resources` với **Stream nguồn ngoài**. Thao tác kết thúc như `collect` hoặc `findFirst` không tự đóng tài nguyên nguồn.

## 10. Ví dụ tổng hợp: lọc số lượng hợp lệ và tính tổng

Giả sử một tệp CSV đơn giản chứa cột đầu là số lượng dạng văn bản. Quy tắc của ví dụ: chỉ chấp nhận số nguyên dương; dòng rỗng và dữ liệu khác định dạng sẽ bị loại theo yêu cầu nghiệp vụ. Dưới đây mô phỏng đầu vào bằng `List` để tập trung vào pipeline:

```java
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

static Optional<Integer> positiveInteger(String text) {
    try {
        int value = Integer.parseInt(text.trim());
        return value > 0 ? Optional.of(value) : Optional.empty();
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}

List<String> quantities = List.of(" 6 ", "unknown", "-2", "3", "0", "11");

List<Integer> accepted = quantities.stream()
        .map(text -> positiveInteger(text))
        .flatMap(Optional::stream)
        .collect(Collectors.toList());

int sum = accepted.stream().mapToInt(Integer::intValue).sum();

System.out.println(accepted); // [6, 3, 11]
System.out.println(sum);      // 20
```

`Optional.empty()` được dùng cho một quy tắc lọc có chủ ý: bỏ giá trị không phải số nguyên dương. Khi mục tiêu chỉ là tính tổng, có thể tránh tạo danh sách trung gian:

```java
int total = quantities.stream()
        .map(text -> positiveInteger(text))
        .flatMap(Optional::stream)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 20
```

Nếu cần **cả** danh sách hợp lệ và số tổng, ví dụ đầu tiên lưu `accepted` rồi tính nhiều phép trên `accepted.stream()`; đó là tạo Stream mới từ List cho mỗi lượt dùng, không tái sử dụng pipeline đã tiêu thụ. Nếu nguồn ban đầu là một Stream đọc tệp chỉ duyệt được một lần, hãy cân nhắc thực hiện các phép thống kê trong cùng lượt xử lý hoặc lưu dữ liệu cần thiết với mức bộ nhớ phù hợp.

## 11. Câu hỏi tự kiểm tra

1. `Stream.of(Optional.of(1), Optional.empty(), Optional.of(2)).flatMap(Optional::stream).count()` trả gì? **2**, vì Optional rỗng không sinh phần tử.
2. Tại sao `map(Optional::stream)` không đủ? Vì nó tạo **Stream của Stream**, cần `flatMap` để tạo Stream phẳng.
3. `Optional.flatMap` khác `Stream.flatMap` ở đâu? Một phương thức làm phẳng **Optional bên trong Optional**, phương thức kia làm phẳng **Stream con bên trong Stream**.
4. Có thể dùng `flatMap(Optional::stream)` ở Java 8 không? **Không**; dùng `filter(isPresent).map(get)` hoặc lambda tạo Stream 0/1.
5. `Objects::nonNull` có loại `Optional.empty()` không? **Không**, Optional.empty vẫn là một đối tượng khác null.
6. Sau `flatMap(Optional::stream)`, `findFirst` trả kiểu gì? **Optional<T>**, vì `findFirst` là terminal operation diễn đạt kết quả có thể vắng mặt của cả Stream.
7. Chuyển `Stream<OptionalInt>` sang Stream số nguyên thủy bằng gì? **`flatMapToInt(OptionalInt::stream)`** trên Java 9+.
8. Khi nào nên giữ thông tin lỗi thay vì bỏ qua bằng `Optional.empty()`? Khi người gọi cần biết **vì sao** dữ liệu thất bại hoặc lỗi đòi hỏi can thiệp.

**Nguyên tắc áp dụng:** Khi mỗi đầu vào có thể tạo 0 hoặc 1 kết quả, hãy biểu diễn sự vắng mặt có chủ ý bằng `Optional<T>` và dùng `map(...).flatMap(Optional::stream)` để chuyển `Stream<T>` thành `Stream<R>` chỉ chứa giá trị hợp lệ. Giữ rõ ranh giới giữa dữ liệu vắng mặt, lỗi cần báo và tài nguyên phải đóng; sự rõ ràng đó quan trọng hơn việc rút ngắn một dòng code.
