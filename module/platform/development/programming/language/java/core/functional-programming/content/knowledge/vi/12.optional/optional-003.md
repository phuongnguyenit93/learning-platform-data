# `map()`, `flatMap()` và `filter()` trên `Optional` trong Java

`Optional<T>` biểu diễn một kết quả **có thể có hoặc không có giá trị**. Thay vì liên tục kiểm tra `null` rồi gọi phương thức trên giá trị bên trong, Java cung cấp ba thao tác quan trọng để xây dựng luồng xử lý theo kiểu hàm:

- `map(...)`: **biến đổi** giá trị có mặt từ `T` sang `U`.
- `flatMap(...)`: **biến đổi và làm phẳng** khi hàm xử lý đã trả về một `Optional<U>`.
- `filter(...)`: **giữ lại hoặc loại bỏ** giá trị dựa vào một điều kiện.

Ba thao tác đều chỉ áp dụng hàm đã cung cấp **khi Optional đang có giá trị**. Nếu `Optional.empty()`, kết quả vẫn là empty và mapper/predicate không được gọi. Chúng trả về một `Optional` khác, giúp ghép nhiều bước mà không phải truy cập trực tiếp vào dữ liệu vắng mặt.

## 1. Nền tảng: trạng thái có giá trị và không có giá trị

`java.util.Optional<T>` là một lớp container giá trị, thường dùng như **kiểu trả về** của phương thức có thể không tìm thấy kết quả. Ví dụ:

~~~java
Optional<String> a = Optional.of("Java");       // Có giá trị
Optional<String> b = Optional.empty();         // Không có giá trị
Optional<String> c = Optional.ofNullable(null); // Không có giá trị
~~~

Đoạn mã cần `import java.util.Optional;` và đặt trong một phương thức.

Phân biệt các factory method:

| Cách tạo | Hành vi |
| --- | --- |
| `Optional.of(value)` | `value` phải khác `null`; `null` khiến lời gọi ném `NullPointerException` |
| `Optional.ofNullable(value)` | Nếu `value == null` thì trả `Optional.empty()`, ngược lại có giá trị |
| `Optional.empty()` | Tạo `Optional` rỗng |

`Optional` không phải một collection nhiều phần tử; nó chỉ có tối đa **một** giá trị. Nó cũng **không được thiết kế để chứa `null`**: `Optional.empty()` biểu diễn sự vắng mặt, còn `Optional.of(null)` là sai. Khi một pipeline kết thúc, ta có thể dùng `orElse(...)`, `orElseGet(...)`, `orElseThrow(...)` hoặc `ifPresent(...)` tùy cách ứng dụng tiêu thụ kết quả.

Về mặt kiểu, `Optional<T>` mang cả trạng thái có/không có giá trị. Các bước `map`, `flatMap` và `filter` vẫn truyền trạng thái này qua chuỗi, giúp diễn đạt rõ mục đích và giảm các nhánh `if (x != null)`.

## 2. `map()`: biến đổi nội dung nếu có

Chữ ký tổng quát của phương thức instance:

~~~java
<U> Optional<U> map(Function<? super T, ? extends U> mapper)
~~~

`Function` là functional interface có phương thức `U apply(T value)`. Nếu Optional chứa `T`, `map` gọi mapper đúng một lần trên giá trị đó rồi bọc kết quả thành `Optional<U>`. Nếu đầu vào empty, mapper **không được gọi**, kết quả là empty.

Ví dụ:

~~~java
Optional<String> source = Optional.of("  java  ");

Optional<Integer> length = source
        .map(String::trim)    // Optional<String> chứa "java"
        .map(String::length); // Optional<Integer> chứa 4
~~~

`String::trim` là method reference tương đương `s -> s.trim()`; `String::length` tương đương `s -> s.length()`. `map` không chỉ thay dữ liệu mà còn cho phép đổi kiểu `Optional<String>` sang `Optional<Integer>`.

### Khi mapper trả về null

Điểm dễ nhầm: `Optional.map` **chấp nhận mapper tạo kết quả `null`**, và sẽ chuyển kết quả đó thành `Optional.empty()` (về hành vi giống dùng `ofNullable` với giá trị mapper trả về).

~~~java
Optional<String> result = Optional.of("x")
        .map(value -> (String) null);
// result = Optional.empty()
~~~

Điều này **không** có nghĩa `null` là một giá trị hợp lệ bên trong Optional. Nếu kết quả mapper là null, pipeline chuyển thành empty; các `map` tiếp theo không chạy mapper.

Phân biệt: bản thân tham số `mapper` của `map(null)` là không hợp lệ và gây `NullPointerException`. Khi Optional đang empty, mapper hợp lệ được bỏ qua, không bị chạy để tạo giá trị mới.

### Lấy thuộc tính của đối tượng

Giả sử có `record Account(String name, String email, boolean active) {}` và phương thức `findAccount(id)` trả `Optional<Account>`:

~~~java
Optional<String> displayName = findAccount("a")
        .map(Account::name);

String visibleName = displayName.orElse("Guest");
~~~

Đây là **đoạn mã minh họa**, không phải chương trình độc lập. Toàn bộ ví dụ chạy được với `record Account` và `findAccount` được cung cấp ở mục 5. `map` chỉ đọc tên khi có Account; nếu không tìm thấy tài khoản, `displayName` empty và `orElse("Guest")` cung cấp giá trị mặc định.

## 3. `filter()`: giữ hoặc loại bỏ giá trị

Chữ ký:

~~~java
Optional<T> filter(Predicate<? super T> predicate)
~~~

`Predicate<T>` có SAM `boolean test(T value)`. Với Optional có giá trị:

- Predicate trả `true` → Optional **giữ nguyên** giá trị hiện có.
- Predicate trả `false` → trả `Optional.empty()`.
- Predicate ném ngoại lệ → ngoại lệ được truyền ra; `filter` không tự biến lỗi thành empty.

Với Optional rỗng, predicate không chạy và kết quả vẫn rỗng.

Ví dụ:

~~~java
Optional<String> accepted = Optional.of("Java")
        .filter(s -> s.length() >= 4); // Optional[Java]

Optional<String> rejected = Optional.of("Java")
        .filter(s -> s.length() > 10); // Optional.empty
~~~

`filter` **không biến đổi** `String` thành một `String` khác. Nó là bước kiểm tra để quyết định có giữ giá trị. Nếu muốn sửa chuỗi, dùng `map`; nếu muốn kiểm tra chuỗi rồi loại bỏ, dùng `filter`.

Có thể kết hợp các điều kiện theo chuỗi:

~~~java
Optional<String> validCode = Optional.of(" ab-123 ")
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .filter(s -> s.startsWith("ab-"));
// validCode chứa "ab-123"
~~~

Ở đây `map` làm sạch giá trị, `filter` thứ nhất loại chuỗi rỗng, `filter` thứ hai giữ chuỗi đúng tiền tố. Nếu một filter trả false, các hàm sau đó không chạy vì Optional đã rỗng.

## 4. `flatMap()`: tránh `Optional<Optional<U>>` khi kết quả cũng là Optional

Chữ ký:

~~~java
<U> Optional<U> flatMap(
        Function<? super T, ? extends Optional<? extends U>> mapper)
~~~

`flatMap` dùng khi mapper đã thể hiện **khả năng vắng mặt** bằng một `Optional<U>`. Nó lấy Optional mà mapper trả về và trả lại dưới dạng một Optional phẳng, không bọc thêm một lớp Optional mới.

Giả sử:

~~~java
static Optional<String> normalizedEmail(Account account) {
    return Optional.ofNullable(account.email())
            .map(String::trim)
            .filter(email -> !email.isBlank())
            .map(email -> email.toLowerCase(Locale.ROOT));
}
~~~

`normalizedEmail` được đặt trong lớp có `record Account` ở chương trình mục 5; cần import `java.util.Optional` và `java.util.Locale`. Hàm trả về `Optional<String>` vì email có thể là null hoặc chuỗi trắng.

Khi xuất phát từ `Optional<Account>`:

~~~java
Optional<Account> account = findAccount("a");

Optional<Optional<String>> nested =
        account.map(OptionalPipelineDemo::normalizedEmail);

Optional<String> flat =
        account.flatMap(OptionalPipelineDemo::normalizedEmail);
~~~

`map` bọc kết quả của mapper trong Optional mới nên kiểu nhận được là **`Optional<Optional<String>>`**. `flatMap` trả thẳng Optional do mapper tạo, vì vậy kiểu là **`Optional<String>`**.

Để thấy các lớp bọc:

~~~text
map:     Optional<Account> -> Optional<Optional<String>>
flatMap: Optional<Account> -> Optional<String>
~~~

Ví dụ cụ thể với dữ liệu ở mục 5:

~~~text
map:     Optional[Optional[an@example.com]]
flatMap: Optional[an@example.com]
~~~

Khi giá trị đầu vào empty, `flatMap` không gọi mapper và trả empty. Khi mapper trả `Optional.empty()`, `flatMap` trả empty. **Khi mapper thực sự trả `null`**, `flatMap` ném `NullPointerException`. Điều này khác với `map`, nơi **giá trị kết quả null** được chuyển thành empty. Nếu nguồn dữ liệu cũ có thể trả null, bọc giá trị bằng `Optional.ofNullable(...)` trong mapper thay vì trả null.

### Quy tắc chọn `map` hay `flatMap`

Hãy nhìn **kiểu trả về của hàm**:

| Hàm được truyền vào | Dùng phương thức | Kiểu kết quả từ `Optional<T>` |
| --- | --- | --- |
| `T -> U` | `map` | `Optional<U>` |
| `T -> Optional<U>` | `flatMap` | `Optional<U>` |
| `T -> boolean` | `filter` | `Optional<T>` |

Ví dụ, `Account::name` trả `String`, dùng `map(Account::name)`. Còn `OptionalPipelineDemo::normalizedEmail` trả `Optional<String>`, dùng `flatMap(...)`. Việc nhìn đúng chữ ký giúp tránh tình trạng phải gọi `orElseThrow()` hai lần chỉ để mở hai lớp Optional không cần thiết.

Lưu ý: `flatMap` của `Optional` làm phẳng **một tầng Optional được mapper trả về**. Nó không có cùng ý nghĩa với `Stream.flatMap`: với Stream, một phần tử có thể tạo ra nhiều phần tử đầu ra, còn với Optional vẫn chỉ có tối đa một giá trị.

## 5. Ví dụ đầy đủ: map → filter → flatMap, Java 17+

Lưu chương trình vào tệp **`OptionalPipelineDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Optional;

public class OptionalPipelineDemo {
    record Account(String name, String email, boolean active) {}

    static Optional<Account> findAccount(String id) {
        return switch (id) {
            case "a" -> Optional.of(new Account("An", " AN@EXAMPLE.COM ", true));
            case "b" -> Optional.of(new Account("Binh", null, false));
            default -> Optional.empty();
        };
    }

    static Optional<String> normalizedEmail(Account account) {
        return Optional.ofNullable(account.email())
                .map(String::trim)
                .filter(email -> !email.isBlank())
                .map(email -> email.toLowerCase(Locale.ROOT));
    }

    public static void main(String[] args) {
        Optional<Account> found = findAccount("a");

        String name = found.map(Account::name).orElse("Guest");
        Optional<Optional<String>> nested = found.map(OptionalPipelineDemo::normalizedEmail);
        Optional<String> flattened = found.flatMap(OptionalPipelineDemo::normalizedEmail);
        Optional<String> eligible = found
                .filter(Account::active)
                .flatMap(OptionalPipelineDemo::normalizedEmail);

        System.out.println("name=" + name);
        System.out.println("nested=" + nested);
        System.out.println("flat=" + flattened);
        System.out.println("eligible=" + eligible.orElse("none"));
        System.out.println("inactive=" + findAccount("b")
                .filter(Account::active)
                .flatMap(OptionalPipelineDemo::normalizedEmail)
                .orElse("none"));
        System.out.println("absent=" + findAccount("missing")
                .map(Account::name)
                .orElse("Guest"));

        System.out.println("length=" + Optional.of("Java")
                .map(String::length).orElse(0));
        System.out.println("nullMap=" + Optional.of("x")
                .map(value -> (String) null));
        System.out.println("filtered=" + Optional.of(4)
                .filter(number -> number > 10));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac OptionalPipelineDemo.java
java OptionalPipelineDemo
~~~

**Stdout chính xác trên Java 17+:**

~~~text
name=An
nested=Optional[Optional[an@example.com]]
flat=Optional[an@example.com]
eligible=an@example.com
inactive=none
absent=Guest
length=4
nullMap=Optional.empty
filtered=Optional.empty
~~~

Giải thích:

1. `findAccount("a")` trả một Account đang active, có email được ghi hoa và thừa khoảng trắng.
2. `map(Account::name)` biến `Optional<Account>` thành `Optional<String>`; sau đó `orElse("Guest")` trích ra `"An"`.
3. `map(OptionalPipelineDemo::normalizedEmail)` bọc Optional kết quả thêm một lần, tạo `Optional<Optional<String>>`, còn `flatMap(...)` giữ đúng một tầng.
4. `filter(Account::active)` giữ Account active trước khi lấy email. `findAccount("b")` trả Account inactive nên filter loại bỏ; mapper lấy email không chạy; fallback in `none`.
5. `findAccount("missing")` trả empty nên `Account::name` không được gọi; kết quả `Guest`.
6. `map(String::length)` biến chuỗi `"Java"` thành số `4`, và `map(value -> null)` trả empty; `filter(number -> number > 10)` loại `4`.

Ví dụ cũng thể hiện việc sử dụng `record` và switch expression (đều hỗ trợ trên JDK 17), method reference, lambda và `Locale.ROOT` để chuẩn hóa chữ hoa/thường ổn định cho mã định danh kỹ thuật. Với tên người dùng hoặc văn bản theo ngôn ngữ tự nhiên, cần cân nhắc quy tắc locale riêng.

## 6. Thứ tự chạy, tính ngắn mạch và việc tiêu thụ kết quả

Xét biểu thức:

~~~java
Optional<String> finalEmail = findAccount(id)
        .filter(Account::active)
        .flatMap(OptionalPipelineDemo::normalizedEmail)
        .filter(email -> email.endsWith("@example.com"));
~~~

Đây là đoạn mã đặt trong lớp ví dụ, với `id` là biến `String` đã xác định. Từng bước xử lý theo thứ tự:

1. `findAccount(id)` trả một Optional.
2. `filter(Account::active)` chỉ kiểm tra nếu đã có Account.
3. `flatMap(...)` chỉ chạy nếu Account còn hiện diện, và có thể tạo empty vì email null/trống.
4. `filter(email -> ...)` chỉ chạy nếu email đã chuẩn hóa hiện diện.

**Không có giá trị nào được tự khôi phục** sau khi Optional trở thành empty. Mapper và predicate của các bước sau sẽ được bỏ qua. Muốn cung cấp giá trị thay thế, dùng một thao tác tiêu thụ hoặc thay thế ở cuối như `orElseGet(...)` hoặc `or(...)`.

Một điểm quan trọng: phép toán `Optional.map`/`flatMap`/`filter` trên Optional đang hiện diện thường thực thi hàm **ngay lúc gọi**; chúng không phải pipeline lazy như các phép toán trung gian trên `Stream`. Sự ngắn mạch ở đây có nghĩa **bỏ qua mapper/predicate khi Optional rỗng**, không có nghĩa hoãn toàn bộ xử lý tới khi gọi `orElse`.

Các cách đọc kết quả:

~~~java
String emailOrDefault = finalEmail.orElse("unknown");
String emailOrComputed = finalEmail.orElseGet(() -> computeFallback());
String mustHaveEmail = finalEmail.orElseThrow();
finalEmail.ifPresent(System.out::println);
~~~

Đây là đoạn minh họa trong ngữ cảnh có `finalEmail` và `computeFallback()`. `orElse("unknown")` lấy mặc định đã tính sẵn; `orElseGet(supplier)` **chỉ gọi supplier khi empty**. Nếu `computeFallback()` nặng hoặc có side effect, tránh `orElse(computeFallback())` vì đối số phương thức được đánh giá trước, kể cả khi Optional có giá trị. `orElseThrow()` không tham số ném `NoSuchElementException` nếu empty. `ifPresent(...)` chỉ chạy consumer khi giá trị tồn tại.

Có thể viết:

~~~java
Optional<String> preferred = Optional.<String>empty()
        .or(() -> Optional.of("backup"));
~~~

`or(...)` (Java 9+) nhận supplier trả `Optional<String>` và cung cấp Optional thay thế **chỉ khi empty**. Nó vẫn giữ mô hình Optional thay vì lấy giá trị thô; điều này hữu ích nếu muốn tiếp tục `map` hoặc `filter` ở phía sau.

## 7. So sánh với mã kiểm tra null thủ công

Giả sử `repository.findById(id)` trả `Optional<Account>`, còn `normalizedEmail(Account)` trả `Optional<String>`. Không dùng pipeline, ta phải tự kiểm tra nhiều tầng và quyết định trạng thái mất dữ liệu. Với pipeline:

~~~java
Optional<String> email = repository.findById(id)
        .filter(Account::active)
        .flatMap(this::normalizedEmail)
        .filter(value -> value.endsWith("@example.com"));
~~~

Đây là **mã minh họa trong một instance method**, cần có biến `repository` và phương thức `normalizedEmail` tương ứng; không phải chương trình tự chạy. Dạng pipeline diễn đạt: *tìm tài khoản → chỉ chấp nhận tài khoản active → lấy email tùy chọn → chỉ chấp nhận email thuộc miền yêu cầu*.

Khi không có kết quả, `email` là empty; không phải `null` và cũng không phải một chuỗi rỗng mặc định. Ở ranh giới API, ứng dụng có thể trả HTTP 404, dùng fallback, hoặc ghi nhận không tìm thấy tùy hợp đồng nghiệp vụ. Tránh tự động xem mọi empty là lỗi: filter false và dữ liệu nguồn vắng mặt có thể mang ý nghĩa khác nhau; nếu cần phân biệt lý do, dùng kiểu kết quả giàu thông tin hơn `Optional`, ví dụ sealed result type hoặc exception có chủ đích.

## 8. Lỗi thường gặp và cách sửa

### 8.1. Dùng `map` khi mapper đã trả `Optional`

~~~java
Optional<Optional<String>> nested =
        findAccount("a").map(OptionalPipelineDemo::normalizedEmail);
~~~

Kết quả có hai tầng. Nếu mục tiêu chỉ là `Optional<String>`, hãy dùng `flatMap`:

~~~java
Optional<String> flat =
        findAccount("a").flatMap(OptionalPipelineDemo::normalizedEmail);
~~~

Hai đoạn cần đặt trong phạm vi lớp ví dụ. Không ép kiểu cưỡng bức `Optional<Optional<String>>` thành `Optional<String>` vì sẽ gây lỗi kiểu; cách đúng là chọn toán tử phù hợp.

### 8.2. Dùng `flatMap` cho hàm trả giá trị thường

~~~java
// Sai về kiểu: Account::name trả String, không trả Optional<String>.
// Optional<String> name = findAccount("a").flatMap(Account::name);

// Đúng:
Optional<String> name = findAccount("a").map(Account::name);
~~~

`flatMap` yêu cầu mapper trả chính một `Optional` (không phải giá trị thô). Ngược lại `map` sẽ tự bọc giá trị thô, bao gồm việc chuyển kết quả null thành empty.

### 8.3. Trả null từ mapper dùng với `flatMap`

~~~java
// Sai khi có giá trị: mapper trả null, flatMap ném NullPointerException.
// Optional<String> wrong = Optional.of("a").flatMap(x -> null);

// Đúng: mapper trả Optional không bao giờ null.
Optional<String> safe = Optional.of("a")
        .flatMap(x -> Optional.ofNullable((String) null));
~~~

Đừng nhầm `Optional.ofNullable(null)` với `null`. Cái trước là một Optional hợp lệ đang empty; cái sau không phải Optional.

### 8.4. Gọi `get()` trước khi pipeline xử lý

~~~java
// Rủi ro: nếu không tồn tại account, get() ném NoSuchElementException.
// String unsafe = findAccount("missing").get().name();

// Không cần mở Optional trước:
String safeName = findAccount("missing")
        .map(Account::name)
        .orElse("Guest");
~~~

Dùng `orElseThrow(...)` khi **bắt buộc** có giá trị và muốn lỗi được nêu rõ; dùng `orElseGet(...)` khi cần tính fallback. `isPresent()` rồi `get()` liên tiếp thường làm mất lợi ích của pipeline và lặp lại nhánh điều kiện.

### 8.5. Nhầm `filter` với chuyển đổi dữ liệu

`filter(s -> s.trim())` sẽ không biên dịch vì `Predicate` phải trả `boolean`, không phải `String`. Nếu cần chuẩn hóa rồi kiểm tra, viết:

~~~java
Optional<String> result = Optional.of("  ok ")
        .map(String::trim)
        .filter(s -> !s.isBlank());
~~~

### 8.6. Kỳ vọng mọi ngoại lệ biến thành empty

`Optional` không tự bắt ngoại lệ trong mapper hoặc predicate. Nếu `Integer.parseInt(...)` gặp đầu vào sai định dạng, nó vẫn ném `NumberFormatException`. Cần xử lý lỗi ở lớp chịu trách nhiệm (hoặc cung cấp hàm parse có hợp đồng `Optional<Integer>`), sau đó mới kết hợp với `flatMap`. Không che tất cả lỗi lập trình thành empty một cách tùy tiện.

### 8.7. Thực hiện side effect trong `map` hoặc `filter`

Mục đích chính của `map` là chuyển đổi, `filter` là quyết định giữ/bỏ giá trị. Không nên viết mapper đổi trạng thái ngoài, gửi email hoặc ghi database chỉ để lợi dụng việc pipeline chạy. Side effect có thể khiến hành vi khó hiểu và khó kiểm thử, đặc biệt khi nhiều lời gọi cùng được tái sử dụng. Để thực hiện hành động với giá trị có mặt, `ifPresent(...)` hoặc xử lý tường minh ở ranh giới là lựa chọn rõ ràng hơn.

### 8.8. Mơ hồ khi giá trị không có mặt

Chuỗi `findAccount(id).filter(Account::active)` trả empty cả khi **không có account** lẫn khi account **inactive**. Nếu tầng gọi cần phân biệt "không tồn tại" với "bị khóa", Optional đơn thuần không lưu lý do. Khi đó phải thiết kế kiểu trạng thái hoặc hợp đồng kết quả khác; không thể suy ra nguyên nhân chỉ bằng `isEmpty()`.

### 8.9. Dùng `Optional` sai ranh giới

`Optional` rất phù hợp làm kiểu trả về khi có thể vắng kết quả, nhất là trong API nhận hành vi. Không nhất thiết dùng nó cho mọi field, constructor parameter hay trường JPA: một số framework serialize/bind/persist Optional không như mong đợi; hãy theo quy ước và hợp đồng của API/framework cụ thể. Đừng để phương thức khai báo `Optional<T>` trả về chính `null`: luôn trả `Optional.of(...)`, `ofNullable(...)` hoặc `empty()`.

## 9. Bảng lựa chọn nhanh

| Mong muốn | Ví dụ | Kết quả |
| --- | --- | --- |
| Biến `Optional<String>` thành độ dài | `Optional.of("Java").map(String::length)` | `Optional[4]` |
| Đưa kết quả mapper null về empty | `Optional.of("x").map(x -> (String) null)` | `Optional.empty` |
| Giữ số khi thỏa điều kiện | `Optional.of(4).filter(x -> x > 2)` | `Optional[4]` |
| Loại số khi không thỏa điều kiện | `Optional.of(4).filter(x -> x > 10)` | `Optional.empty` |
| Gọi hàm `T -> Optional<U>` | `findAccount("a").flatMap(OptionalPipelineDemo::normalizedEmail)` | `Optional<String>` |
| Gọi hàm `T -> U` | `findAccount("a").map(Account::name)` | `Optional<String>` |
| Đọc giá trị hoặc fallback | `someOptional.orElse("default")` | `String` |
| Tính fallback chỉ khi empty | `someOptional.orElseGet(() -> computeFallback())` | `String` |

Một pipeline Optional tốt nên diễn đạt rõ: **biến đổi bằng `map`, kết hợp các bước có thể vắng mặt bằng `flatMap`, giữ/lọc bằng `filter`, rồi tiêu thụ Optional theo hợp đồng nghiệp vụ**. Kiểu trả về của hàm được truyền vào là tiêu chí quyết định để chọn đúng toán tử; trạng thái empty sẽ tiếp tục lan truyền mà không cần nhánh null thủ công.