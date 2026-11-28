# Kết hợp Optional, kiểu kết quả và ngoại lệ đúng ngữ nghĩa

> **Phạm vi:** Java 27 — chương **Ngoại lệ và vòng đời tài nguyên**. Bài học phân biệt ba cách biểu diễn kết quả: `Optional<T>` cho **giá trị có thể vắng mặt**, kiểu kết quả có cấu trúc cho **thành công/thất bại dự kiến theo nghiệp vụ**, và exception cho **lỗi hoặc việc vi phạm hợp đồng cần được truyền lên**. Ví dụ sử dụng API Java đang được hỗ trợ, không phụ thuộc tính năng preview hay thư viện legacy.

## 1. Vì sao cần phân biệt ba cơ chế?

Giả sử một ứng dụng tra cứu đơn hàng theo mã. Có ít nhất ba tình huống:

1. Tra cứu thành công và **tìm thấy** đơn hàng.
2. Tra cứu thành công nhưng **không tìm thấy** đơn hàng.
3. Tra cứu **không hoàn tất** vì database mất kết nối, timeout hoặc dữ liệu nguồn hỏng.

Nếu cả tình huống (2) và (3) đều được chuyển thành `Optional.empty()`, caller không thể biết liệu đơn hàng thực sự không tồn tại hay hệ thống đang gặp sự cố. Ngược lại, nếu việc “không tồn tại” là tình huống bình thường mà luôn ném exception, luồng xử lý phải dùng exception cho một nhánh nghiệp vụ có thể dự đoán.

Nguyên tắc nền tảng:

- **Optional:** hàm thực thi bình thường, nhưng giá trị trả về **có thể không tồn tại**.
- **Result/outcome type:** hàm hoàn tất xử lý ở cấp nghiệp vụ với **một trong nhiều kết quả có ý nghĩa**, thường gồm thành công và lỗi dự kiến.
- **Exception:** hàm không thể thực hiện đúng hợp đồng hiện tại, đầu vào vi phạm tiền điều kiện, hoặc hệ thống có lỗi cần caller xử lý/truyền lên.

Không có một quy tắc duy nhất áp dụng cho mọi phần mềm: việc “không tìm thấy” là bình thường trong màn hình tìm kiếm, nhưng có thể là vi phạm invariant trong quy trình đã được cam kết rằng đơn hàng phải tồn tại. Điều quan trọng là **định nghĩa hợp đồng API trước**.

## 2. Bảng quyết định nhanh

| Tình huống | Cơ chế thường phù hợp | Lý do |
| --- | --- | --- |
| Tìm tùy chọn cấu hình có thể không được khai báo | `Optional<Config>` | Vắng mặt là kết quả bình thường |
| Tìm phần tử đầu phù hợp điều kiện | `Optional<T>` | Tập dữ liệu có thể không có phần tử phù hợp |
| Kiểm tra yêu cầu đặt hàng: hết hàng, hạn mức, không đủ số lượng | Kiểu kết quả `Accepted/Rejected` | Caller cần xử lý các nhánh dự kiến có mã/lý do |
| Parse một biểu thức mà lỗi cú pháp là dữ liệu cần phản hồi chi tiết | `Result<Value, ParseError>` tự thiết kế | Lỗi có vị trí, loại và nội dung để hiển thị |
| Đối số có `id <= 0` dù contract yêu cầu ID dương | `IllegalArgumentException` | Caller vi phạm tiền điều kiện của API |
| Trạng thái đối tượng không cho phép thao tác hiện tại | `IllegalStateException` | Vi phạm trạng thái/hợp đồng |
| Không đọc được tệp bắt buộc vì I/O | `IOException` hoặc exception có cause | Thao tác hệ thống thất bại |
| File cấu hình **tùy chọn** không tồn tại | Có thể trả `Optional.empty()` cho **đúng lỗi “file không tồn tại”** | Sự vắng mặt là chính sách hợp lệ |
| File tồn tại nhưng không đọc được do permission | Exception | Không nên giả vờ rằng file vắng mặt |
| Network timeout / database connection failure | Exception, hoặc kết quả kỹ thuật có kiểu riêng theo contract | Cần giữ thông tin thất bại và chính sách retry |

**Đừng** định nghĩa `Optional.empty()` là “mọi thứ đều thất bại” hoặc tự tạo một `Result` chỉ vì hàm trả `String` rỗng. Chọn abstraction từ ý nghĩa nghiệp vụ.

## 3. Optional<T> là gì trong Java 27?

`java.util.Optional<T>` là một **container có thể chứa hoặc không chứa một giá trị khác `null`**. Đây là lớp có sẵn của Java, chủ yếu được thiết kế để dùng làm **kiểu trả về** khi có nhu cầu biểu diễn “không có kết quả”.

~~~java
import java.util.Optional;

Optional<String> present = Optional.of("Java");
Optional<String> absent = Optional.empty();

System.out.println(present.isPresent()); // true
System.out.println(absent.isEmpty());     // true
~~~

Một `Optional<T>` **không nên tự là `null`**. Các trạng thái hợp lệ của nó là “present với một giá trị không null” hoặc “empty”, không phải “null Optional”.

`Optional` là **value-based class**. Không đồng bộ hóa bằng `synchronized(optional)`, không dùng `==` để kiểm tra Optional rỗng và không phụ thuộc identity của instance. Dùng các method của Optional và `equals` khi cần so sánh giá trị container.

### 3.1. Ba factory quan trọng

| Factory | Đầu vào | Kết quả |
| --- | --- | --- |
| `Optional.of(value)` | `value != null` | Present |
| `Optional.of(value)` | `value == null` | Ném `NullPointerException` |
| `Optional.ofNullable(value)` | Bất kỳ, kể cả null | Present nếu khác null, empty nếu null |
| `Optional.empty()` | Không có đầu vào | Empty |

~~~java
import java.util.Optional;

String name = "Mai";
String nickname = null;

Optional<String> first = Optional.of(name);
Optional<String> second = Optional.ofNullable(nickname);
Optional<String> third = Optional.empty();

System.out.println(first.orElse("anonymous")); // Mai
System.out.println(second.orElse("anonymous")); // anonymous
System.out.println(third.isEmpty()); // true
~~~

Dùng `of` khi `null` là **vi phạm hợp đồng** và bạn muốn phát hiện lỗi sớm. Dùng `ofNullable` khi hệ thống **thực sự** cho phép dữ liệu nguồn null để biểu diễn không có giá trị.

### 3.2. Ví dụ repository: không tìm thấy là bình thường

~~~java
import java.util.Map;
import java.util.Optional;

record Customer(long id, String name) {}

final class InMemoryCustomers {
    private final Map<Long, Customer> customers = Map.of(
            1L, new Customer(1L, "An"),
            2L, new Customer(2L, "Bình"));

    public Optional<Customer> findById(long id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        return Optional.ofNullable(customers.get(id));
    }
}
~~~

Hợp đồng hàm là:

- ID dương và có dữ liệu → `Optional.of(customer)`.
- ID dương nhưng không tồn tại → `Optional.empty()`.
- ID không hợp lệ → `IllegalArgumentException`.

Với database thực, lỗi kết nối phải được truyền theo cơ chế lỗi phù hợp; **không** catch rồi trả empty để mô phỏng “không tìm thấy”.

## 4. Đọc giá trị Optional đúng cách

### 4.1. orElse, orElseGet và orElseThrow

~~~java
import java.util.Optional;

Optional<String> label = Optional.empty();

System.out.println(label.orElse("not set")); // not set
System.out.println(label.orElseGet(() -> "generated")); // generated
~~~

Sự khác nhau quan trọng:

- `orElse(fallback)` nhận một **giá trị đã được tính** khi gọi method.
- `orElseGet(supplier)` chỉ gọi supplier khi Optional **empty**.
- `orElseThrow()` lấy giá trị, hoặc ném `NoSuchElementException` nếu empty.
- `orElseThrow(exceptionSupplier)` cho phép chọn exception phản ánh contract.

Ví dụ minh họa tính eager/lazy:

~~~java
static String expensiveDefault() {
    System.out.println("create default");
    return "fallback";
}

Optional<String> value = Optional.of("ready");

String eager = value.orElse(expensiveDefault());
// Vẫn in "create default"

String lazy = value.orElseGet(() -> expensiveDefault());
// Không gọi expensiveDefault() vì value đã present
~~~

Khi fallback gây I/O, tính toán lớn hoặc side effect, cần đặc biệt tránh gọi nó không cần thiết. Đây là lý do nên dùng `orElseGet` trong trường hợp fallback thực sự chỉ cần khi empty.

### 4.2. Chuyển vắng mặt thành exception tại đúng ranh giới

~~~java
Customer customer = repository.findById(requestedId)
        .orElseThrow(() -> new CustomerNotFoundException(
                "Customer " + requestedId + " not found"));
~~~

`repository` và `requestedId` là các biến nghiệp vụ giả định. Nếu tầng ứng dụng **bắt buộc** có customer để tiếp tục, có thể nâng “không tồn tại” thành exception tại **tầng đó**.

Một custom exception đơn giản:

~~~java
public final class CustomerNotFoundException
        extends RuntimeException {

    public CustomerNotFoundException(String message) {
        super(message);
    }
}
~~~

Không phải mọi “not found” đều cần exception. Một endpoint tìm kiếm thường dùng empty để biểu diễn không có kết quả; một thao tác cập nhật yêu cầu đối tượng phải tồn tại có thể cần thông báo lỗi cụ thể.

### 4.3. ifPresent và ifPresentOrElse

~~~java
import java.util.Optional;

Optional<String> lookup = Optional.of("Mai");

lookup.ifPresent(System.out::println);

lookup.ifPresentOrElse(
        value -> System.out.println("Found: " + value),
        () -> System.out.println("No value"));
~~~

Hai method này thích hợp khi mục đích là **thực hiện hành động** thay vì trả một giá trị mới. Nếu muốn tiếp tục tính toán thuần, dùng `map` hoặc `flatMap` thường dễ kết hợp hơn.

## 5. map, flatMap, filter và or trong Optional pipeline

### 5.1. map: biến đổi giá trị nếu có

~~~java
import java.util.Optional;

record Profile(String displayName) {}

Optional<Profile> profile = Optional.of(new Profile("  Hoa  "));

Optional<String> name = profile
        .map(Profile::displayName)
        .map(String::strip);

System.out.println(name.orElse("unknown")); // Hoa
~~~

Nếu Optional empty, các mapper không chạy. Nếu mapper trả `null`, `Optional.map` biến kết quả thành **empty**, theo quy tắc tương tự `ofNullable`. Vì vậy, `map` có thể che giấu một lỗi thiết kế nếu mapper đáng lẽ không bao giờ được phép trả null; hãy kiểm tra invariant khi cần.

### 5.2. flatMap: tránh Optional lồng Optional

Giả sử một API đã trả Optional:

~~~java
import java.util.Optional;

public class AccountExample {
    record Account(String alias) {}

    static Optional<Account> findAccount(String alias) {
        return alias.isBlank()
                ? Optional.empty()
                : Optional.of(new Account(alias));
    }

    public static void main(String[] args) {
        Optional<String> input = Optional.of("mai");

        Optional<Account> result =
                input.flatMap(AccountExample::findAccount);
        System.out.println(result.orElseThrow().alias()); // mai
    }
}
~~~

Nếu dùng `map(AccountExample::findAccount)`, kiểu sẽ là `Optional<Optional<Account>>`. `flatMap` “làm phẳng” một tầng và có kiểu kết quả `Optional<Account>`.

**Lưu ý:** `flatMap` yêu cầu mapper trả về một `Optional` không null; mapper trả null là lỗi và ném `NullPointerException`, không biến thành empty.

### 5.3. filter: giữ giá trị đáp ứng điều kiện

~~~java
Optional<String> normalizedCode = Optional.of("  AX-1  ")
        .map(String::strip)
        .filter(s -> !s.isBlank());

System.out.println(normalizedCode.orElse("missing")); // AX-1
~~~

`filter` chỉ nói “giữ hoặc bỏ giá trị”, **không giữ được lý do** vì sao predicate trả false. Nếu lý do rất quan trọng (ví dụ mã hết hạn, định dạng sai, tài khoản bị khóa), dùng kiểu kết quả nghiệp vụ có mã lỗi thay vì gộp tất cả thành empty.

### 5.4. or: dùng một Optional thay thế khi empty

~~~java
import java.util.Optional;

Optional<String> primary = Optional.empty();

Optional<String> selected = primary.or(
        () -> Optional.of("secondary"));

System.out.println(selected.orElse("default")); // secondary
~~~

`Optional.or` nhận supplier trả **Optional**, khác `orElseGet` trả **giá trị T**. Supplier của `or` chỉ chạy khi Optional gốc empty; supplier không được trả null.

### 5.5. Optional.stream và pipeline tập hợp

~~~java
import java.util.List;
import java.util.Optional;

List<Optional<String>> pieces = List.of(
        Optional.of("A"),
        Optional.empty(),
        Optional.of("C"));

List<String> present = pieces.stream()
        .flatMap(Optional::stream)
        .toList();

System.out.println(present); // [A, C]
~~~

`Optional.stream()` tạo stream 0 hoặc 1 phần tử, hữu ích để gom các kết quả tìm kiếm tùy chọn mà không ép `null` thành một phần tử.

## 6. Những điều Optional không biểu diễn được

`Optional.empty()` **chỉ có một trạng thái vắng mặt**. Nó không tự phân biệt:

- Không tồn tại bản ghi.
- Bản ghi bị ẩn theo quyền truy cập.
- Trường dữ liệu chưa được cung cấp.
- Định dạng giá trị không hợp lệ.
- Thao tác bị từ chối do quy tắc nghiệp vụ.
- Hệ thống lỗi mạng, timeout hoặc permission.

Ví dụ thiết kế sai:

~~~java
// Không làm vậy nếu lỗi I/O phải được báo:
Optional<String> badRead(java.nio.file.Path path) {
    try {
        return Optional.of(java.nio.file.Files.readString(path));
    } catch (java.io.IOException ex) {
        return Optional.empty(); // Nuốt mọi lỗi thành "không có dữ liệu"
    }
}
~~~

Chính caller của `badRead` giờ không phân biệt được “file không tồn tại” và “file tồn tại nhưng không đọc được”. Điều này có thể gây lỗi bảo mật, dữ liệu rỗng giả hoặc việc cache một kết quả thất bại như một sự vắng mặt vĩnh viễn.

**Quy tắc thiết kế:** chỉ chuyển một lỗi cụ thể thành empty khi **chính hợp đồng nghiệp vụ** quy định lỗi đó mang nghĩa vắng mặt. Các lỗi còn lại phải được giữ nguyên hoặc chuyển đổi thành lỗi có thông tin đầy đủ.

## 7. Kiểu kết quả (Result/Outcome) là gì?

Java 27 **không có một generic `Result<T,E>` trong `java.util`** tương đương một số ngôn ngữ khác. Ứng dụng có thể tự định nghĩa một kiểu kết quả, thường bằng `sealed interface` và `record`, để biểu diễn các nhánh **được phép xảy ra** theo hợp đồng.

Ví dụ đặt chỗ có hai kết quả nghiệp vụ:

~~~java
import java.util.Objects;
import java.util.UUID;

sealed interface BookingOutcome
        permits BookingOutcome.Accepted, BookingOutcome.Rejected {

    record Accepted(UUID bookingId) implements BookingOutcome {
        public Accepted {
            Objects.requireNonNull(bookingId, "bookingId");
        }
    }

    record Rejected(Reason reason, String detail)
            implements BookingOutcome {
        public Rejected {
            Objects.requireNonNull(reason, "reason");
            Objects.requireNonNull(detail, "detail");
        }
    }

    enum Reason {
        INVALID_QUANTITY,
        INSUFFICIENT_CAPACITY
    }
}
~~~

Các trường hợp:

- `Accepted`: yêu cầu đặt chỗ được chấp nhận.
- `Rejected`: yêu cầu được xử lý nhưng bị từ chối **theo quy tắc dự kiến**, có mã và chi tiết.
- Network/database failure: **không tự động** là `Rejected`; tùy contract, nó vẫn là exception hoặc một nhánh lỗi kỹ thuật riêng.

Sự khác nhau nằm ở ý nghĩa, không nằm ở việc exception “xấu” còn result “tốt”. Hai cơ chế có vai trò khác nhau.

### 7.1. Service trả outcome thay vì ném cho các nhánh dự kiến

~~~java
import java.util.UUID;

final class BookingService {
    static BookingOutcome book(int requested, int available) {
        if (requested <= 0) {
            return new BookingOutcome.Rejected(
                    BookingOutcome.Reason.INVALID_QUANTITY,
                    "Requested quantity must be positive");
        }

        if (requested > available) {
            return new BookingOutcome.Rejected(
                    BookingOutcome.Reason.INSUFFICIENT_CAPACITY,
                    "Not enough capacity");
        }

        return new BookingOutcome.Accepted(UUID.randomUUID());
    }
}
~~~

**Điều kiện của ví dụ:** `available` là giá trị đã được hệ thống xác thực, và không có database/transaction thật. Trong ứng dụng đặt chỗ, kiểm tra rồi trừ tồn kho cần cơ chế đồng bộ hoặc transaction để tránh race condition. Kiểu Result không tự làm thao tác atomic.

### 7.2. Caller xử lý exhaustively bằng switch pattern matching

Java 27 hỗ trợ pattern matching trong `switch` như tính năng chính thức từ Java 21:

~~~java
BookingOutcome outcome = BookingService.book(3, 1);

String message = switch (outcome) {
    case BookingOutcome.Accepted ok ->
            "Created booking: " + ok.bookingId();
    case BookingOutcome.Rejected rejected ->
            "Rejected: " + rejected.reason()
                    + " - " + rejected.detail();
};

System.out.println(message);
// Rejected: INSUFFICIENT_CAPACITY - Not enough capacity
~~~

Vì `BookingOutcome` là sealed và hai record là các nhánh được phép, `switch` có thể liệt kê toàn bộ trường hợp. Khi thêm nhánh mới, compiler hỗ trợ phát hiện những nơi cần cập nhật. Không nhất thiết thêm `default` chỉ để che một trường hợp mà hệ thống chưa xử lý.

### 7.3. Result tổng quát khi nhiều API cần dùng lại

Khi nhiều service có hợp đồng thành công/thất bại cùng hình dạng, có thể định nghĩa kiểu tổng quát:

~~~java
import java.util.Objects;

sealed interface Result<T, E>
        permits Result.Ok, Result.Err {

    record Ok<T, E>(T value) implements Result<T, E> {
        public Ok {
            Objects.requireNonNull(value, "value");
        }
    }

    record Err<T, E>(E error) implements Result<T, E> {
        public Err {
            Objects.requireNonNull(error, "error");
        }
    }
}
~~~

Cách dùng:

~~~java
enum ValidationError { BLANK_NAME }

static Result<String, ValidationError> validateName(String name) {
    if (name == null || name.isBlank()) {
        return new Result.Err<>(ValidationError.BLANK_NAME);
    }
    return new Result.Ok<>(name.strip());
}
~~~

Đây là **kiểu do dự án tự định nghĩa**, không phải API chuẩn `java.util.Result`. Khi đưa vào codebase thật, cần quy định null policy, tên lỗi, generic variance, cách `map/flatMap` result, logging, serialization và versioning. Không tạo abstraction quá tổng quát nếu một outcome riêng cho domain sẽ rõ hơn.

### 7.4. Kết quả có kiểu không tự đảm bảo recoverability

Một `Result.Err` chỉ phản ánh một tình huống lỗi theo hợp đồng. Nó không có nghĩa lỗi chắc chắn an toàn để retry. Ví dụ `PAYMENT_DECLINED` thường khác `NETWORK_TIMEOUT`; timeout có thể xảy ra **sau khi** hệ thống thanh toán đã nhận yêu cầu. Nếu tự động retry mà không có idempotency key, có nguy cơ thanh toán lặp.

Thiết kế lỗi có kiểu nên phân biệt:

- Mã lỗi ổn định cho máy (`ErrorCode`, enum hoặc record).
- Thông điệp hiển thị cho người dùng (không lộ dữ liệu nhạy cảm).
- Nguyên nhân kỹ thuật và correlation ID cho log.
- Chính sách có thể retry/không retry, thuộc transaction/boundary nào.

## 8. Exception: phân biệt lỗi có kiểm tra và không kiểm tra

Trong Java, các ngoại lệ thường được phân nhóm:

| Loại | Ví dụ | Đặc điểm |
| --- | --- | --- |
| **Checked exception** | `IOException`, `SQLException` | Compiler yêu cầu catch hoặc khai báo `throws`, trừ trường hợp đặc biệt do ngôn ngữ quy định |
| **Unchecked exception** | `IllegalArgumentException`, `IllegalStateException`, `NullPointerException` | Kế thừa `RuntimeException`, compiler không bắt buộc khai báo |
| **Error** | `OutOfMemoryError`, `StackOverflowError` | Tình trạng nghiêm trọng của runtime; thường không phải nhánh nghiệp vụ để bắt và phục hồi |

Cả `RuntimeException` và `Error` đều là **unchecked** theo ngữ nghĩa Java; tuy nhiên không nên dùng `Error` để báo lỗi validation hay kết quả dự kiến.

### 8.1. Vi phạm tiền điều kiện

~~~java
static int positivePageSize(int size) {
    if (size <= 0 || size > 1_000) {
        throw new IllegalArgumentException(
                "pageSize must be between 1 and 1000");
    }
    return size;
}
~~~

Ví dụ này giả định contract yêu cầu kích thước trang hợp lệ. Nếu form nhập liệu cần hiển thị lỗi từng trường, service ở **tầng validate** có thể trả `ValidationResult` thay vì ném exception mỗi lần người dùng gõ sai. Quy tắc chọn cơ chế phụ thuộc boundary và cách caller được thiết kế để phản hồi.

### 8.2. Vi phạm trạng thái

~~~java
enum Status { NEW, CLOSED }

final class Session {
    private Status status = Status.NEW;

    void send(String payload) {
        if (status == Status.CLOSED) {
            throw new IllegalStateException("Session is closed");
        }
        // Gửi dữ liệu theo hợp đồng của implementation.
    }

    void close() {
        status = Status.CLOSED;
    }
}
~~~

`IllegalStateException` nói rằng yêu cầu thao tác **không hợp lệ trong trạng thái hiện tại**. Với hành vi domain bình thường như “đơn hàng đã đóng không thể hủy”, một kiểu `CancellationRejected` cũng có thể phù hợp hơn nếu caller thường xuyên phải xử lý tình huống đó.

### 8.3. Checked exception cho lỗi hệ thống có thể được xử lý

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

static String loadRequiredFile(Path path) throws IOException {
    return Files.readString(path, StandardCharsets.UTF_8);
}
~~~

Lời gọi `Files.readString` có thể báo `IOException`; dùng `throws IOException` để chuyển trách nhiệm xử lý lên caller thay vì tự chuyển mọi lỗi thành chuỗi rỗng.

**Checked/unchecked không quyết định hoàn toàn mức độ recoverability.** Một `IOException` có thể không thể phục hồi tại tầng hiện tại; một `IllegalArgumentException` có thể được chuyển thành phản hồi 400 ở HTTP boundary. Chọn theo hợp đồng và vị trí xử lý.

## 9. Kết hợp Optional với exception mà không che mất lỗi

Một API đọc file cấu hình **tùy chọn** có thể diễn đạt “file không tồn tại” bằng empty, nhưng vẫn giữ exception khi dữ liệu không đọc được:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.Optional;

static Optional<String> loadOptionalConfig(Path path)
        throws IOException {
    try {
        return Optional.of(
                Files.readString(path, StandardCharsets.UTF_8));
    } catch (NoSuchFileException ex) {
        return Optional.empty();
    }
}
~~~

Hợp đồng ở đây là **thiếu file được xem là không cấu hình**, còn lỗi permission, dữ liệu hỏng hoặc sự cố I/O khác phải được truyền lên. Nếu một ứng dụng không cho phép thiếu thư mục cha hoặc yêu cầu cấu hình bắt buộc, ngay cả `NoSuchFileException` cũng nên được truyền lên, không đổi thành empty.

Việc `readString` trả chuỗi rỗng khi file rỗng là **kết quả có giá trị**, khác với file không tồn tại. `Optional.of("")` là present và không được đổi thành empty trừ khi contract nói “nội dung rỗng tương đương không cấu hình”.

### 9.1. Đừng kiểm tra exists trước rồi mới đọc

Không nên thiết kế như sau:

~~~java
// Dễ gặp time-of-check/time-of-use race:
// if (Files.exists(path)) {
//     return Optional.of(Files.readString(path));
// }
// return Optional.empty();
~~~

File có thể bị xóa, thay thế hoặc thay đổi quyền truy cập giữa hai lời gọi. Xử lý **trực tiếp** lỗi cụ thể phát sinh từ thao tác đọc sẽ phản ánh chính xác hơn kết quả thực tế tại thời điểm thao tác. Trong các hệ thống cần bảo mật hoặc chống race nghiêm ngặt, còn phải xét symlink, quyền truy cập và tính nguyên tử ở cấp filesystem.

### 9.2. Không bắt mọi RuntimeException để trả empty

~~~java
// Anti-pattern:
// try {
//     return Optional.of(service.load());
// } catch (Exception ex) {
//     return Optional.empty();
// }
~~~

Đoạn này biến cả lỗi lập trình, null không mong muốn, timeout và thất bại hệ thống thành “không có dữ liệu”. Phần mềm ở tầng trên có thể ghi đè dữ liệu đúng bằng giá trị mặc định vì hiểu sai trạng thái.

## 10. Result, Optional và exception có thể tồn tại trong cùng một luồng

Một dịch vụ có thể dùng cả ba cơ chế tại **những lớp khác nhau**:

~~~text
HTTP request
    |
    v
Kiểm tra tiền điều kiện API
    |-- sai contract --> IllegalArgumentException hoặc lỗi validate có kiểu
    |
    v
Tìm bản ghi bằng repository
    |-- hoàn tất nhưng không có --> Optional.empty()
    |-- tìm thấy -------------> Optional.of(Entity)
    |-- I/O/DB failure --------> Exception (giữ cause)
    |
    v
Áp dụng quy tắc domain
    |-- được chấp nhận --------> Outcome.Accepted
    |-- từ chối dự kiến -------> Outcome.Rejected(code, detail)
    |
    v
HTTP/CLI/UI boundary
    |-- chuyển thành phản hồi rõ ràng; log lỗi kỹ thuật an toàn
~~~

Ví dụ một search API trả `Optional<User>` nhưng vẫn cho phép lỗi hạ tầng truyền lên:

~~~java
import java.io.IOException;
import java.util.Optional;

record User(long id, String displayName) {}

interface UserRepository {
    Optional<User> findById(long id) throws IOException;
}

static String renderUser(UserRepository repository, long id)
        throws IOException {
    if (id <= 0) {
        throw new IllegalArgumentException("id must be positive");
    }

    return repository.findById(id)
            .map(User::displayName)
            .orElse("(not found)");
}
~~~

Caller của `renderUser` có thể nhận chuỗi `"(not found)"` nếu dữ liệu vắng mặt, nhưng vẫn được thông báo bằng exception khi repository không thể thực thi truy vấn. Việc hiển thị fallback là quyết định của tầng UI; không nhất thiết dùng fallback đó ở các tầng quan trọng như thanh toán hoặc phân quyền.

## 11. Khi cả thành công rỗng và thất bại đều quan trọng

Đôi lúc một API có thể hoàn tất thành công nhưng không có dữ liệu, **và** có thể nhận một lỗi nghiệp vụ dự kiến cần thông điệp riêng. Có ba cách mô hình hóa tùy mức độ phức tạp.

### Cách A: Optional + exception

~~~java
Optional<Order> findOrder(String id) throws IOException;
~~~

Có giá trị / vắng mặt / lỗi I/O được tách tự nhiên. Dùng khi ít biến thể kết quả.

### Cách B: Kiểu outcome có ba hoặc nhiều nhánh

~~~java
sealed interface LookupOutcome
        permits LookupOutcome.Found,
                LookupOutcome.NotFound,
                LookupOutcome.Rejected {

    record Found(String value) implements LookupOutcome {}
    record NotFound() implements LookupOutcome {}
    record Rejected(String code) implements LookupOutcome {}
}
~~~

Dùng khi caller phải phân nhánh cụ thể và có lý do được chuẩn hóa.

### Cách C: Result<Optional<T>, E>

~~~java
Result<Optional<Customer>, LookupError> lookup(...);
~~~

Dòng trên là **chữ ký minh họa**, dùng kiểu `Result<T,E>` tự định nghĩa ở phần 7 và một kiểu `LookupError` do dự án định nghĩa. Nó biểu diễn:

- `Ok(Optional.of(value))`: hoàn tất và tìm thấy.
- `Ok(Optional.empty())`: hoàn tất và không tìm thấy.
- `Err(error)`: thất bại có kiểu.

Cách này chính xác về mặt ngữ nghĩa nhưng dễ dẫn tới cấu trúc lồng khó đọc. Nếu số nhánh ít và mang ý nghĩa domain riêng, sealed outcome ba nhánh có thể rõ hơn. Đừng dùng `Optional<Result<T,E>>` và `Result<Optional<T>,E>` như thể hai kiểu này tương đương; mỗi tầng mang một câu hỏi khác nhau.

## 12. Không chuyển exception thành Result một cách tùy tiện

Có thể hữu ích khi chuyển **một nhóm exception đã dự đoán rõ** thành một nhánh thất bại có kiểu, ví dụ service chuyển `DuplicateKeyException` của database thành `AccountAlreadyExists` ở tầng domain. Nhưng phải tránh:

- Bắt `Throwable` hoặc `Error` rồi coi là thất bại thông thường.
- Dùng một enum `UNKNOWN_ERROR` và loại bỏ stack trace/cause mà không logging.
- Bắt `NullPointerException` do bug rồi coi là “không tìm thấy”.
- Tạo quá nhiều biến thể lỗi mà caller không thể xử lý khác nhau.
- Chuyển timeout thành “bị từ chối nghiệp vụ” nếu kết quả thực tế còn chưa xác định.

Khi cần chuyển đổi ở boundary, hãy giữ thông tin nguyên nhân:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String readOrFail(Path path) {
    try {
        return Files.readString(path);
    } catch (IOException ex) {
        throw new UncheckedIOException(
                "Cannot read required file: " + path, ex);
    }
}
~~~

`UncheckedIOException` phù hợp khi một API không khai báo checked IOException nhưng lỗi đọc vẫn phải truyền lên. Nó **không** biến lỗi thành kết quả nghiệp vụ bình thường. Với file chứa dữ liệu bí mật hoặc đường dẫn nhạy cảm, cần xem xét thông điệp log/exception để tránh lộ thông tin.

### 12.1. Giữ cause khi bọc exception

~~~java
public final class CatalogAccessException
        extends RuntimeException {

    public CatalogAccessException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Bọc một exception có thể giúp tầng trên hiểu context, nhưng `new CatalogAccessException("failed", ex)` phải giữ `ex` làm cause. Việc chỉ tạo `new RuntimeException("failed")` và bỏ exception gốc sẽ khiến việc điều tra lỗi khó khăn.

## 13. Vòng đời tài nguyên và Optional

`Optional` chỉ mô tả **có/không có giá trị**, không sở hữu và không tự đóng tài nguyên. Một `Optional<InputStream>` hoặc `Optional<Stream<String>>` không tự biến tài nguyên bên trong thành an toàn.

Ví dụ nguy hiểm:

~~~java
// API sau giao tài nguyên cho caller nhưng contract sở hữu chưa rõ:
// Optional<InputStream> openMaybe(Path path);
~~~

Nếu trả resource, phải nêu rõ **ai gọi close()**, trường hợp empty, cách xử lý lỗi mở, và liệu caller có được dùng nhiều lần không. Với tài nguyên có vòng đời ngắn, thường dễ thiết kế một phương thức mở, dùng và đóng trong cùng phạm vi hơn.

### 13.1. Try-with-resources và kết quả Optional

Ví dụ lấy dòng đầu tiên không rỗng từ tệp:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

static Optional<String> firstNonBlankLine(Path path)
        throws IOException {
    try (Stream<String> lines =
                 Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
                .map(String::strip)
                .filter(s -> !s.isEmpty())
                .findFirst();
    }
}
~~~

Ở đây có **ba tình huống**:

- File đọc được và có dòng hợp lệ → `Optional.of(line)`.
- File đọc được nhưng không có dòng phù hợp → `Optional.empty()`.
- Không mở hoặc đọc được file → exception.

`findFirst()` là terminal operation nhưng **không tự đóng** Stream; `try-with-resources` bảo đảm gọi `close()`. Lỗi khi traversal của `Files.lines` có thể phát sinh dưới dạng `UncheckedIOException`; `throws IOException` trong chữ ký không loại trừ unchecked exception này. Nếu API muốn chuẩn hóa mọi lỗi đọc thành `IOException`, có thể catch `UncheckedIOException` tại boundary có chủ đích và lấy `getCause()`.

Không trả một lazy Stream được tạo bên trong `try-with-resources` sau khi block đã đóng resource. Cần hoàn tất terminal operation **trước khi rời scope**.

### 13.2. Suppressed exceptions không được quên

Nếu thân `try` ném một exception và `close()` cũng ném exception, Java giữ **exception từ thân try làm exception chính** và đưa lỗi close vào danh sách **suppressed exceptions**:

~~~java
try (Resource resource = openResource()) {
    process(resource); // có thể ném lỗi A
} // close() có thể ném lỗi B, lỗi B sẽ bị suppressed nếu A đã xảy ra
~~~

Đây là **mã giả** vì `Resource`/`openResource`/`process` chưa được định nghĩa. Với đối tượng Throwable thực tế, dùng `getSuppressed()` để xem các exception phụ:

~~~java
static void reportSuppressed(Throwable failure) {
    for (Throwable secondary : failure.getSuppressed()) {
        System.err.println("Suppressed: " + secondary);
    }
}
~~~

Nếu bạn catch một exception rồi chỉ lấy message để trả `Result.Err` hoặc `Optional.empty()`, thông tin **cause** và **suppressed exceptions** có thể bị mất. Khi chuyển đổi lỗi, hãy xác định rõ nơi log/truy xuất lỗi kỹ thuật. Không dùng `finally { return ...; }` vì `return` trong finally có thể che lấp exception từ thân try.

## 14. Phân loại lỗi tại API boundary

Một ứng dụng có các tầng repository → domain → HTTP controller nên quy định nhất quán:

| Tầng | Đầu vào/kết quả | Xử lý phù hợp |
| --- | --- | --- |
| Repository | Tìm bản ghi theo ID | `Optional<T>` cho vắng mặt; exception cho DB/I/O failure |
| Domain service | Điều kiện nghiệp vụ | Outcome/Result cho trạng thái từ chối dự kiến |
| API validator | Request sai định dạng/giới hạn | Validation result có lỗi trường, hoặc exception input contract theo thiết kế |
| HTTP boundary | Chuyển outcome/exception sang HTTP response | Không lộ thông tin nội bộ; giữ log/correlation ID |
| Batch processor | Xử lý nhiều mục | Kiểu kết quả từng mục nếu lỗi từng mục được chấp nhận; exception cho lỗi toàn lô |

Ví dụ mapping phản hồi (mang tính minh họa, không buộc mọi API phải dùng giống nhau):

| Tình huống | HTTP response thường dùng |
| --- | --- |
| Thành công có dữ liệu | 200 |
| Tạo thành công | 201 |
| Không có tài nguyên yêu cầu | 404 |
| Đầu vào sai | 400 hoặc 422 tùy contract |
| Xung đột nghiệp vụ | 409 |
| Dịch vụ phụ trợ tạm không khả dụng | 503 |
| Lỗi không dự đoán được | 500 |

**Đừng** gửi trực tiếp stack trace, nội dung `SQLException`, thông tin kết nối hoặc secret vào HTTP response. Ghi log an toàn có correlation ID, trả mã lỗi công khai ổn định và phân biệt lỗi client/server theo contract.

## 15. Null, Optional và database: các góc cạnh cần nhớ

### 15.1. Optional của Optional thường khó đọc

~~~java
Optional<Optional<String>> nested =
        Optional.of(Optional.empty());
~~~

`nested` là **present** nhưng giá trị bên trong là **empty**. Đây có thể mang ý nghĩa cụ thể trong một vài mô hình ba trạng thái, nhưng không nên tạo tự động chỉ vì dùng `map` thay vì `flatMap`. Nếu ba trạng thái có nghĩa nghiệp vụ, hãy cân nhắc outcome có tên rõ ràng.

### 15.2. Optional làm field hoặc tham số

Javadoc của `Optional` nêu mục đích chủ yếu là **method return type**. Việc dùng `Optional` cho field hoặc tham số không bị Java cấm tuyệt đối, nhưng thường gây nhiều lớp container, tương tác khó với mapper/serialization và khiến caller phải gói những giá trị vốn đã biết có mặt.

Thông thường:

~~~java
// Contract: trả Optional nếu tìm được hoặc không tìm được.
Optional<Customer> findCustomer(long id);

// Contract: tham số bắt buộc; kiểm tra null nếu cần.
void updateCustomer(Customer customer);
~~~

Nếu yêu cầu nhập liệu có ba trạng thái **không truyền trường / truyền null / truyền giá trị**, `Optional<T>` đôi khi vẫn **không đủ** để giữ toàn bộ khác biệt. Hãy dùng DTO/patch type có hợp đồng rõ ràng về field presence.

### 15.3. Optional không tự hỗ trợ Java Object Serialization

`Optional` không triển khai `Serializable`. Nếu dữ liệu cần lưu trữ hoặc truyền qua giao thức, hãy thiết kế một DTO/schema phù hợp thay vì mặc định đưa `Optional` vào field và kỳ vọng Java native serialization hoạt động.

Điều này không có nghĩa một framework JSON không thể hỗ trợ Optional; khả năng hỗ trợ phụ thuộc phiên bản thư viện và cách cấu hình. Không suy ra hợp đồng của một framework từ Java SE API.

### 15.4. Primitive Optional

Java có `OptionalInt`, `OptionalLong` và `OptionalDouble` để biểu diễn giá trị primitive tùy chọn mà không cần gói thành `Integer`/`Long`/`Double`:

~~~java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt firstEven = IntStream.of(1, 3, 6, 8)
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(firstEven.orElse(-1)); // 6
~~~

Các primitive Optional có API tương tự nhưng **không phải** `Optional<Integer>`; lưu ý khi thiết kế generic APIs hoặc ánh xạ giữa primitive/object streams.

## 16. Những lỗi phổ biến khi kết hợp ba cơ chế

| Anti-pattern | Hệ quả | Cách thay thế |
| --- | --- | --- |
| Trả `null` thay cho `Optional.empty()` | Caller phải kiểm tra hai tầng vắng mặt | Bảo đảm Optional bản thân không null |
| Catch `Exception` rồi trả empty | Mất khác biệt giữa không tìm thấy và lỗi hệ thống | Chỉ chuyển lỗi được phép thành empty |
| Dùng `Optional.get()` khắp nơi | Có thể ném `NoSuchElementException` khó kiểm soát | `map/flatMap/orElseThrow` với contract rõ |
| Dùng `isPresent() + get()` cho pipeline đơn giản | Nhiều nhánh và dễ bỏ sót trường hợp empty | `map/filter/flatMap/ifPresentOrElse` |
| `orElse(expensiveFallback())` | Tính fallback dù Optional present | `orElseGet(() -> expensiveFallback())` |
| Dùng `Optional.filter` để validate nhiều lỗi | Mất lý do bị loại | Result/outcome với error code |
| Dùng exception cho mọi lần người dùng nhập sai form | Control flow rối và khó tổng hợp lỗi | Validation outcome cho nhánh dự kiến |
| Trả `Result.Err("something failed")` với mọi lỗi | Thiếu thông tin khắc phục | Error type có mã/lý do rõ |
| Bắt exception rồi ném cái mới không có cause | Mất stack trace nguyên nhân | Exception wrapping với `cause` |
| Catch cả `Throwable` và coi là lỗi nghiệp vụ | Nuốt cả `Error` nghiêm trọng | Bắt đúng kiểu lỗi có thể xử lý |
| Trả `Optional<InputStream>` không ghi contract | Caller dễ rò rỉ tài nguyên | Xác định ownership hoặc xử lý trong try-with-resources |
| Terminal Stream xong tưởng resource tự đóng | File descriptor có thể mở | Dùng try-with-resources |
| Trả Result từ khối try nhưng nuốt lỗi close | Mất thông tin lỗi tài nguyên | Tôn trọng suppressed exceptions; log/propagate có chủ đích |
| Dùng `Optional.empty()` làm “access denied” | Có thể che sai lầm bảo mật hoặc đánh lừa caller | Phân biệt chính sách ẩn tài nguyên với quyền bị từ chối |

## 17. Mẫu kiểm thử nên có

Với API trả `Optional<T>`, kiểm thử cả present và empty; đồng thời kiểm tra lỗi hệ thống **không** bị chuyển nhầm thành empty.

Ví dụ JUnit Jupiter (giả định `InMemoryCustomers` ở phần 3 đã được khai báo):

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class CustomerLookupTest {
    @Test
    void found() {
        var repository = new InMemoryCustomers();
        var result = repository.findById(1L);

        assertTrue(result.isPresent());
        assertEquals("An", result.orElseThrow().name());
    }

    @Test
    void missingIsEmpty() {
        var repository = new InMemoryCustomers();

        assertTrue(repository.findById(99L).isEmpty());
    }

    @Test
    void invalidIdThrows() {
        var repository = new InMemoryCustomers();

        assertThrows(IllegalArgumentException.class,
                () -> repository.findById(0L));
    }
}
~~~

Với kiểu Result:

- Đầu vào hợp lệ → nhánh `Accepted/Ok`.
- Lỗi nghiệp vụ dự kiến → nhánh `Rejected/Err` đúng mã.
- Lỗi hạ tầng → được truyền riêng, không chuyển thành `Rejected` sai nghĩa.
- Đổi/đưa thêm nhánh sealed → cập nhật switch exhaustively.

Với resource:

- Thành công → resource được đóng.
- Thân xử lý ném exception → resource vẫn được đóng.
- `close()` ném exception → suppressed exception được giữ đúng.
- Không tìm thấy dữ liệu trong file hợp lệ → Optional empty; file không đọc được → exception.

## 18. Checklist thiết kế API và review

- [ ] Hợp đồng đã nêu rõ “vắng mặt bình thường”, “từ chối nghiệp vụ” và “lỗi thực thi”.
- [ ] Không gộp lỗi database/network/permission vào `Optional.empty()`.
- [ ] Optional được ưu tiên cho kiểu trả về có thể không có giá trị; bản thân Optional không null.
- [ ] Dùng `of` và `ofNullable` đúng với null policy.
- [ ] Dùng `orElseGet` khi fallback tốn kém hoặc có side effect.
- [ ] Không dùng `map` để che lỗi null nếu null vi phạm invariant.
- [ ] Dùng `flatMap` khi mapper đã trả Optional.
- [ ] Không dùng `filter` làm validation nếu caller cần biết lý do.
- [ ] Kiểu Result/outcome có những nhánh gắn với hành động xử lý thực tế.
- [ ] Sealed outcome và pattern matching switch xử lý đủ các trường hợp.
- [ ] Ngoại lệ vi phạm tiền điều kiện/trạng thái có loại và thông điệp phù hợp.
- [ ] Checked exception được xử lý hoặc truyền lên đúng boundary.
- [ ] Exception được wrap có giữ `cause` khi cần.
- [ ] Không bắt `Error` để coi như lỗi nghiệp vụ bình thường.
- [ ] Resource I/O được đóng bằng try-with-resources; không trả stream đã đóng.
- [ ] Nếu trả resource cho caller, ownership và close contract đã được tài liệu hóa.
- [ ] Lỗi close/suppressed được xem xét trong logging và debugging.
- [ ] Boundary không lộ stack trace, connection details hoặc secret.
- [ ] Bài test có đủ present/empty/rejected/exception/resource failure.

## 19. Nguồn tài liệu chính thức

- [Java SE 27 API — Optional](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Optional.html) — container có thể vắng mặt, `map`/`flatMap`/`orElseGet`/`orElseThrow` và lưu ý value-based class.
- [Java SE 27 API — OptionalInt](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/OptionalInt.html) — Optional chuyên biệt cho primitive `int`.
- [Java SE 27 API — Throwable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Throwable.html) — cause, stack trace và suppressed exceptions.
- [Java SE 27 API — RuntimeException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/RuntimeException.html) — unchecked exception.
- [Java SE 27 API — IOException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/IOException.html) — checked exception cho thao tác I/O thất bại.
- [Java SE 27 API — UncheckedIOException](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/UncheckedIOException.html) — bọc lỗi I/O thành unchecked exception khi hợp đồng cần.
- [Java SE 27 API — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html) — `readString`, `lines`, `NoSuchFileException` và resource lifecycle.
- [Java SE 27 API — AutoCloseable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/AutoCloseable.html) — hợp đồng đóng tài nguyên.
- [JLS Java SE 27 §14.20.3 — try-with-resources](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.20.3) — đóng tài nguyên và suppressed exceptions.
- [JLS Java SE 27 §8.1.1.2 — sealed classes](https://docs.oracle.com/javase/specs/jls/se27/html/jls-8.html#jls-8.1.1.2) — tập subtype được phép.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409) — sealed classes chính thức từ Java 17.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441) — pattern switch chính thức từ Java 21.

**Kết luận:** `Optional<T>` trả lời câu hỏi **“có giá trị hay không?”**; một kiểu `Result/Outcome` trả lời **“thao tác nghiệp vụ kết thúc theo nhánh nào?”**; exception trả lời **“vì sao không thể thực hiện đúng hợp đồng hiện tại?”**. Kết hợp đúng ba cơ chế giúp API rõ ràng, giữ nguyên dấu vết lỗi và quản lý tài nguyên an toàn trong Java 27.
