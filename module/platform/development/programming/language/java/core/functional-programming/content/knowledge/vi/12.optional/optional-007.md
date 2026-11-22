# Optional.ifPresent() và ifPresentOrElse() trong Java

## 1. Mục tiêu: xử lý hai trạng thái có giá trị hoặc rỗng

`Optional<T>` trong `java.util` biểu diễn một **container có thể có hoặc không có giá trị kiểu `T`**. Thay vì lấy giá trị bằng `get()` rồi tự xử lý rủi ro `NoSuchElementException`, ta có thể cung cấp một hành động để Java gọi **chỉ khi có giá trị**, hoặc hai hành động để xử lý **cả trường hợp có và không có giá trị**.

Hai phương thức cần nắm vững:

~~~java
void ifPresent(Consumer<? super T> action)

void ifPresentOrElse(Consumer<? super T> action, Runnable emptyAction)
~~~

- **`ifPresent(action)`**: nếu `Optional` chứa giá trị, thực hiện `action.accept(value)`; nếu rỗng thì **không làm gì**.
- **`ifPresentOrElse(action, emptyAction)`**: nếu chứa giá trị, thực hiện `action.accept(value)`; nếu rỗng, thực hiện `emptyAction.run()`. Trong một lời gọi hoàn tất theo cách thông thường, chỉ **một trong hai nhánh** được chọn.
- Cả hai có kiểu trả về **`void`**: chúng dành cho việc **thực hiện hành động**, thường là cập nhật giao diện, in thông báo, logging hoặc gọi một dịch vụ, **không dùng để trả lại giá trị đã biến đổi**.

`ifPresent` có từ **Java 8**. `ifPresentOrElse` được bổ sung từ **Java 9**, nên cả hai đều có sẵn trong **Java 17+**.

**Ý chính:** `ifPresent` diễn đạt “**nếu có, hãy làm việc này**”, còn `ifPresentOrElse` diễn đạt “**nếu có, hãy làm việc này; nếu không có, hãy làm việc kia**”.

## 2. Chữ ký SAM: vì sao nhánh có giá trị nhận đối số còn nhánh rỗng thì không?

`Consumer<T>` là functional interface có SAM:

~~~java
void accept(T value);
~~~

Nó nhận một giá trị nhưng không trả kết quả. Vì vậy `Optional<String>.ifPresent` có thể dùng:

~~~java
Optional<String> name = Optional.of("An");
name.ifPresent(value -> System.out.println("Xin chào " + value));
~~~

Còn `Runnable` là functional interface với SAM:

~~~java
void run();
~~~

Nó không nhận đối số và không trả kết quả. Vì khi `Optional` **rỗng** thì không có giá trị nào để truyền, nhánh thứ hai của `ifPresentOrElse` dùng `Runnable`:

~~~java
Optional<String> name = Optional.empty();
name.ifPresentOrElse(
        value -> System.out.println("Xin chào " + value),
        () -> System.out.println("Không tìm thấy tên")
);
~~~

Các đoạn trong mục này là **minh họa dùng bên trong phương thức**, cần import `java.util.Optional`. Không có `main` nên không phải chương trình chạy độc lập.

**Đối chiếu các kiểu callback:**

| Phần của lời gọi | Kiểu yêu cầu | Cần nhận giá trị của Optional? | Ví dụ |
|---|---|---|---|
| `ifPresent(action)` | `Consumer<? super T>` | Có, một tham số `T` | `value -> save(value)` |
| Nhánh đầu của `ifPresentOrElse` | `Consumer<? super T>` | Có, một tham số `T` | `value -> show(value)` |
| Nhánh rỗng của `ifPresentOrElse` | `Runnable` | Không, không tham số | `() -> showMissing()` |

`<? super T>` cho phép một `Consumer` chấp nhận `T` hoặc kiểu cha phù hợp. Trong trường hợp dùng lambda thông thường, tham số `value` được suy ra từ kiểu `Optional<T>`. `Runnable` không mang generic vì không cần giá trị nào từ `Optional`.

## 3. Khi nào nhánh được thực hiện?

Giả sử:

~~~java
Optional<String> present = Optional.of("Java");
Optional<String> absent = Optional.empty();
~~~

Có bốn tình huống:

| Phương thức | Optional có giá trị | Optional rỗng |
|---|---|---|
| `ifPresent(action)` | Gọi `action` một lần | Không gọi `action` |
| `ifPresentOrElse(action, emptyAction)` | Gọi `action` một lần, không gọi `emptyAction` | Không gọi `action`, gọi `emptyAction` một lần |

Điều này chỉ nói về **lựa chọn callback khi gọi phương thức**. Nếu callback tự gọi nhiều hàm khác, khởi động luồng riêng, hoặc ném ngoại lệ, những hành vi bên trong phải được phân tích riêng.

Với `Optional.ofNullable(null)`, kết quả là `Optional.empty()`. `Optional` bản thân không chứa giá trị `null` để đưa vào nhánh `action`. Muốn tạo Optional có giá trị, dùng `Optional.of(nonNullValue)` hoặc `Optional.ofNullable(possiblyNullValue)`.

Lưu ý: `Optional.of(null)` ném `NullPointerException` **ngay khi tạo Optional**, không phải khi `ifPresent` chạy. Đừng nhầm lỗi tạo Optional với lỗi trong callback.

### 3.1. Program chạy được: quan sát cả hai nhánh

Lưu file **`OptionalBranchDemo.java`**:

~~~java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

public class OptionalBranchDemo {
    public static void main(String[] args) {
        Optional<String> present = Optional.of("  Java  ");
        Optional<String> empty = Optional.empty();

        AtomicInteger presentCalls = new AtomicInteger();
        AtomicInteger emptyCalls = new AtomicInteger();

        present.ifPresent(value -> {
            presentCalls.incrementAndGet();
            System.out.println("ifPresent=" + value.trim());
        });

        empty.ifPresent(value -> {
            presentCalls.incrementAndGet();
            System.out.println("never printed");
        });

        present.ifPresentOrElse(
                value -> {
                    presentCalls.incrementAndGet();
                    System.out.println("present=" + value.trim());
                },
                () -> {
                    emptyCalls.incrementAndGet();
                    System.out.println("never printed");
                }
        );

        empty.ifPresentOrElse(
                value -> {
                    presentCalls.incrementAndGet();
                    System.out.println("never printed");
                },
                () -> {
                    emptyCalls.incrementAndGet();
                    System.out.println("empty fallback");
                }
        );

        System.out.println("calls=" +
                presentCalls.get() + "/" + emptyCalls.get());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac OptionalBranchDemo.java
java OptionalBranchDemo
~~~

Stdout chính xác:

~~~text
ifPresent=Java
present=Java
empty fallback
calls=2/1
~~~

**Phân tích:**

1. `present.ifPresent(...)` gọi action nên bộ đếm `presentCalls` tăng lên `1`.
2. `empty.ifPresent(...)` không gọi action, vì thế dòng `never printed` không xuất hiện.
3. `present.ifPresentOrElse(...)` chạy callback nhận `value`, đưa bộ đếm `presentCalls` lên `2`; không chạy `emptyAction`.
4. `empty.ifPresentOrElse(...)` không có giá trị để đưa vào callback đầu; nó chạy `emptyAction` và tăng `emptyCalls` lên `1`.
5. Dòng cuối là `calls=2/1`, xác nhận nhánh được chọn chứ không phải cả hai nhánh đều chạy.

`AtomicInteger` ở ví dụ chỉ dùng để làm bộ đếm dễ quan sát; **không có yêu cầu** phải dùng atomic để gọi `ifPresent` hoặc `ifPresentOrElse`. Đây là chương trình tuần tự.

## 4. Chọn `ifPresent` khi không cần nhánh “không có”

`ifPresent` thích hợp nếu sự vắng mặt là tình huống bình thường và ứng dụng **không cần hành động nào khác**:

~~~java
// Đoạn code minh họa với các biến đã tồn tại.
maybeUser.ifPresent(user -> auditLogger.record(user));
selectedId.ifPresent(id -> highlightRow(id));
maybeEvent.ifPresent(event -> eventBus.publish(event));
~~~

Các ví dụ phụ thuộc vào `maybeUser`, `selectedId`, `maybeEvent` và các dịch vụ do ứng dụng định nghĩa. Ý nghĩa là: **có giá trị thì thực hiện thao tác; không có thì bỏ qua**.

Khi callback chỉ gọi một phương thức với đối số nhận được, có thể dùng method reference:

~~~java
maybeUser.ifPresent(auditLogger::record);
~~~

Dạng `auditLogger::record` giúp diễn đạt rõ hành động nhưng **không thay đổi** thời điểm callback được kích hoạt, số lần gọi hoặc khả năng có tác dụng phụ.

Đừng dùng `ifPresent` chỉ để che một trường hợp “không tìm thấy” bắt buộc phải xử lý. Nếu vắng mặt cần cảnh báo, lỗi nghiệp vụ, một trạng thái giao diện khác hoặc số liệu thống kê, `ifPresentOrElse` hoặc API phù hợp khác giúp ý định rõ hơn.

### Khi “không làm gì” mới là hành vi đúng

Ví dụ bộ lọc có thể trả về một mục tùy chọn; nếu có, ta hiển thị. Nếu không có, giao diện vốn đã ở trạng thái mặc định và không cần cập nhật. `ifPresent` nói đúng nghiệp vụ mà không tạo ra nhánh `else` rỗng chỉ để thỏa một khuôn mẫu.

Tuy nhiên, nếu hệ thống cần ghi nhận một trường hợp “không thấy kết quả” cho mục đích audit thì bỏ qua âm thầm có thể là lỗi. Hãy quyết định từ yêu cầu nghiệp vụ trước khi chọn API.

## 5. Chọn `ifPresentOrElse` khi cả hai trạng thái cần hành động

Một ứng dụng tìm người dùng có thể cần **hiển thị thông tin nếu tìm thấy** và **hiển thị thông báo riêng nếu không thấy**:

~~~java
lookupUser(id).ifPresentOrElse(
        user -> showUser(user),
        () -> showNotFound(id)
);
~~~

Đây là đoạn code minh họa. `lookupUser` được giả định trả `Optional<User>`; các phương thức `showUser`, `showNotFound` do ứng dụng định nghĩa.

Đối số thứ nhất là `Consumer<User>`: khi có người dùng, callback nhận chính `User` đó. Đối số thứ hai là `Runnable`: khi không có, callback không nhận người dùng; nếu cần thông tin `id`, lambda **capture** `id` từ phạm vi bên ngoài.

Các biến cục bộ capture phải là `final` hoặc *effectively final*. Nếu gán lại `id` sau khi tạo lambda trong cùng phạm vi, mã có thể không biên dịch. Đây là quy tắc capture của lambda, không riêng `Optional`.

### 5.1. Program chạy được: xử lý kết quả tra cứu

Lưu file **`OptionalUserDemo.java`**:

~~~java
import java.util.Optional;
import java.util.OptionalInt;
import java.util.function.Consumer;

public class OptionalUserDemo {
    record User(String name, int points) {}

    public static void main(String[] args) {
        Optional<User> found = Optional.of(new User("Mai", 85));
        Optional<User> missing = Optional.empty();

        Consumer<User> showUser = user ->
                System.out.println(
                        "user=" + user.name() + ",points=" + user.points()
                );

        Runnable showMissing = () ->
                System.out.println("user=not found");

        found.ifPresentOrElse(showUser, showMissing);
        missing.ifPresentOrElse(showUser, showMissing);

        int score = found.map(User::points).orElse(0);
        String selected = missing
                .map(User::name)
                .orElseGet(() -> "guest");

        System.out.println("score=" + score);
        System.out.println("selected=" + selected);

        OptionalInt count = OptionalInt.of(4);
        count.ifPresentOrElse(
                value -> System.out.println("count=" + value),
                () -> System.out.println("no count")
        );
    }
}
~~~

Chạy:

~~~bash
javac OptionalUserDemo.java
java OptionalUserDemo
~~~

Stdout:

~~~text
user=Mai,points=85
user=not found
score=85
selected=guest
count=4
~~~

**Điểm học tập:**

- Cùng một `Consumer<User>` và `Runnable` có thể tái sử dụng cho nhiều `Optional<User>` khác nhau.
- `found.ifPresentOrElse` gọi `showUser.accept(user)`; `missing.ifPresentOrElse` gọi `showMissing.run()`.
- Khi **cần một giá trị**, chương trình chuyển sang `map(...).orElse(...)` hoặc `map(...).orElseGet(...)` thay vì cố lấy kết quả từ `ifPresentOrElse`.
- `OptionalInt` là phiên bản chuyên biệt cho `int` nguyên thủy. `OptionalInt.ifPresentOrElse(IntConsumer, Runnable)` có cách chọn nhánh tương tự, nhưng callback nhận giá trị dùng `IntConsumer` thay vì `Consumer<Integer>`.
- Record `User` được dùng để biểu diễn dữ liệu một cách ngắn gọn; record là tính năng chuẩn trong Java 16+, phù hợp với JDK 17.

## 6. Cả hai phương thức đều trả `void`: đừng dùng để tính kết quả

Đây là điểm phân biệt quan trọng nhất giữa `ifPresent`/`ifPresentOrElse` và các API tạo giá trị.

**Sai:**

~~~java
// CỐ Ý SAI: ifPresentOrElse trả void, không trả String.
// String label = maybeName.ifPresentOrElse(
//         name -> name,
//         () -> "unknown"
// );
~~~

Ngoài việc phương thức trả `void`, lambda ở đây cũng không diễn đạt hành động `Consumer<String>`/`Runnable` đúng mục đích. Nếu cần một chuỗi, hãy dùng API **trả kết quả**:

~~~java
String label = maybeName
        .map(String::trim)
        .orElseGet(() -> "unknown");
~~~

Đoạn trên là minh họa, giả sử `maybeName` là `Optional<String>`. `map` biến đổi giá trị khi có, còn `orElseGet` dùng `Supplier<String>` để cung cấp fallback khi rỗng.

Bảng chọn API:

| Nhu cầu | API phù hợp | Kiểu kết quả |
|---|---|---|
| Có thì thực hiện hành động | `ifPresent(Consumer)` | `void` |
| Có hoặc rỗng đều cần hành động khác nhau | `ifPresentOrElse(Consumer, Runnable)` | `void` |
| Có thì biến đổi giá trị | `map(Function)` | `Optional<U>` |
| Có thì giữ lại nếu thỏa điều kiện | `filter(Predicate)` | `Optional<T>` |
| Lấy giá trị nếu có, rỗng dùng giá trị cố định | `orElse(T)` | `T` |
| Lấy giá trị nếu có, rỗng mới tính fallback | `orElseGet(Supplier<? extends T>)` | `T` |
| Không có giá trị thì ném exception | `orElseThrow()` hoặc `orElseThrow(Supplier<? extends X>)` | `T` |

`ifPresent` và `ifPresentOrElse` là những **thao tác kết thúc một nhánh xử lý bằng hành động**. Vì không trả về `Optional`, chúng không hỗ trợ kiểu chain `optional.ifPresent(...).map(...)`.

Khi chọn API, đặt câu hỏi: “**Tôi cần thực hiện việc gì hay cần nhận một giá trị mới?**” Nếu cần giá trị, tránh lạm dụng mutable holder chỉ để lấy nó ra từ callback.

## 7. Những lỗi thường gặp khi chuyển từ `if/else` sang Optional

### 7.1. Gọi `get()` trước rồi mới kiểm tra

~~~java
// CỐ Ý SAI khi Optional có thể rỗng:
String value = optional.get();
if (value != null) {
    consume(value);
}
~~~

`optional.get()` ném `NoSuchElementException` nếu rỗng, nên điều kiện `value != null` không bảo vệ được. Giả sử `optional` là `Optional<String>` đã có; giải pháp đúng khi chỉ cần hành động là:

~~~java
optional.ifPresent(value -> consume(value));
~~~

Nếu cần hành động nhánh không có:

~~~java
optional.ifPresentOrElse(
        value -> consume(value),
        () -> reportMissing()
);
~~~

Các phương thức `consume` và `reportMissing` do ứng dụng định nghĩa; ba đoạn đều là minh họa, không chạy độc lập.

### 7.2. Dùng `isPresent()` rồi `get()` trong mọi trường hợp

~~~java
if (optional.isPresent()) {
    consume(optional.get());
} else {
    reportMissing();
}
~~~

Cách này **có thể đúng** nhưng thường dài hơn callback của `ifPresentOrElse`. Việc đổi sang callback làm rõ hành động gắn với hai trạng thái và tránh gọi `get()` thủ công.

Tuy nhiên, một câu lệnh `if/else` thuần túy vẫn có thể hợp lý nếu flow phức tạp, cần `return` khỏi **phương thức bao ngoài**, `break`/`continue` trong vòng lặp, hoặc cấu trúc callback làm logic khó đọc. Mục tiêu không phải thay thế tất cả `if` bằng lambda, mà là diễn đạt rõ hành vi.

### 7.3. Nhầm `Runnable` với `Consumer` ở nhánh rỗng

**Sai vì callback rỗng không có đối số:**

~~~java
// CỐ Ý SAI: emptyAction phải là Runnable có 0 tham số.
// optional.ifPresentOrElse(
//         value -> System.out.println(value),
//         missing -> System.out.println(missing)
// );
~~~

Đúng:

~~~java
optional.ifPresentOrElse(
        value -> System.out.println(value),
        () -> System.out.println("empty")
);
~~~

Ở nhánh rỗng, không có `value`. Muốn dùng một dữ liệu bên ngoài như request ID, hãy capture biến đó trong `() -> reportMissing(requestId)`.

### 7.4. Mong lambda tự động chạy cả hai nhánh

Hai đối số callback được **tạo/đánh giá** khi gọi phương thức, nhưng **thân callback** chỉ được thực thi theo nhánh được chọn. Đây là điểm khác biệt quan trọng:

~~~java
// Đúng: chỉ thực hiện công việc đắt đỏ khi không có giá trị.
optional.ifPresentOrElse(
        value -> show(value),
        () -> log(buildExpensiveMessage())
);
~~~

Nếu trước đó viết `String message = buildExpensiveMessage();` rồi chỉ capture `message` trong lambda, việc tạo chuỗi đã xảy ra **trước** khi biết Optional có rỗng hay không.

Method reference gắn receiver như `service::handle` cũng có thể đánh giá biểu thức receiver lúc tạo reference; không nên cho rằng toàn bộ các phần của lời gọi đều tự động được trì hoãn, dù phần thân callback chưa chạy.

### 7.5. Dùng callback để gán vào một biến ngoài

~~~java
// Tránh kiểu thiết kế phức tạp hoặc không hợp lệ:
// String result = null;
// optional.ifPresent(v -> result = v); // Biến local không effectively final.
~~~

Biến cục bộ capture bởi lambda phải `final` hoặc *effectively final*. Việc dùng `AtomicReference` hoặc mảng một phần tử chỉ để đưa kết quả ra ngoài `ifPresent` thường làm code khó hiểu hơn. Nếu bài toán cần trả một giá trị, `orElse`, `orElseGet` hoặc `map` là API đúng mục đích.

### 7.6. Dùng `ifPresent` rồi bỏ quên trường hợp vắng mặt quan trọng

Nếu kết quả rỗng có nghĩa “đơn hàng không tồn tại” và người dùng phải được thông báo, `ifPresent` có thể bỏ sót một nhánh cần thiết. `ifPresentOrElse` làm hai trạng thái hiển thị rõ tại cùng một chỗ.

Ngược lại, nếu nhánh rỗng thật sự không cần làm gì, viết `ifPresentOrElse(action, () -> {})` chỉ làm code thêm nhiễu. Chọn `ifPresent(action)`.

## 8. Khi callback ném ngoại lệ hoặc có tác dụng phụ

### 8.1. Ngoại lệ không tự được nuốt hay chuyển nhánh

`ifPresent` và `ifPresentOrElse` **không phải cơ chế xử lý exception**. Nếu callback được chọn ném một unchecked exception, exception đó truyền ra cho caller; nhánh còn lại **không tự chạy như phần bù**.

~~~java
Optional<String> value = Optional.of("bad");

value.ifPresentOrElse(
        text -> { throw new IllegalStateException("failed:" + text); },
        () -> System.out.println("empty action")
);
~~~

Đây là minh họa. Lời gọi ném `IllegalStateException` và không in `empty action`, vì Optional **có giá trị**. Nếu muốn xử lý lỗi trong callback, phải dùng cấu trúc `try/catch` thích hợp.

Các SAM `Consumer.accept` và `Runnable.run` không khai báo checked exception. Nếu callback làm I/O có thể ném `IOException`, ta cần xử lý checked exception trong lambda hoặc thiết kế một API khác có hợp đồng ngoại lệ phù hợp; không thể để nó tự thoát ra khỏi hai SAM này mà không xử lý.

### 8.2. Thứ tự và số lần tác dụng phụ

Với một Optional thông thường được tạo qua Java API, một lời gọi `ifPresent` hoặc `ifPresentOrElse` chọn callback thích hợp và gọi callback đó một lần. Nhưng **bên trong** callback có thể thay đổi object, ghi log, gọi API hay khởi chạy việc bất đồng bộ.

~~~java
optional.ifPresent(user -> repository.save(user));
~~~

Đoạn minh họa này có thể gây side effect ghi dữ liệu khi có giá trị. `Optional` không khiến thao tác trở nên thuần khiết, không tự bảo vệ transaction, không cung cấp retry hay thread safety.

Không nên dùng callback chỉ để tăng bộ đếm rồi dựa vào nó thay cho một giá trị trả về, nếu có API kiểu giá trị rõ ràng hơn.

## 9. `null` và callback `null`: trường hợp biên cần biết

`Optional.empty()` không chứa `null` như một giá trị được đưa vào `Consumer`. Tuy nhiên, tham số `action` hoặc `emptyAction` **có thể bị truyền null nhầm**.

Theo hợp đồng của API:

- `ifPresent(null)` ném `NullPointerException` **nếu Optional có giá trị** và cần gọi action.
- `ifPresentOrElse(null, someRunnable)` ném `NullPointerException` **nếu Optional có giá trị**.
- `ifPresentOrElse(someConsumer, null)` ném `NullPointerException` **nếu Optional rỗng**.
- Callback của nhánh không được chọn không bị gọi; vì vậy một callback null không nhất thiết gây lỗi ngay khi truyền nếu nhánh đó không chạy. Dù vậy, **không nên truyền null cho callback**: khi thay đổi trạng thái đầu vào, lỗi có thể lộ ra bất ngờ.

Một điều khác là **giá trị đầu vào**:

~~~java
Optional<String> empty = Optional.ofNullable(null);
Optional<String> present = Optional.of("data");
~~~

`empty.ifPresent(v -> ...)` không gọi lambda; `present.ifPresent(v -> ...)` đưa `"data"` vào. Đừng sử dụng `Optional.of(null)` để mô tả Optional rỗng, vì chính lời gọi đó sẽ ném ngoại lệ.

## 10. Có cần `ifPresentOrElse` nếu đang dùng Java 8?

`ifPresentOrElse` chỉ có từ **Java 9**. Trong Java 8, vẫn có thể dùng:

~~~java
if (optional.isPresent()) {
    optional.ifPresent(value -> show(value));
} else {
    showMissing();
}
~~~

Ví dụ này là minh họa, dù cách viết có thể tinh gọn bằng cách lấy giá trị và xử lý trong một cấu trúc `if/else` đơn thuần. Không nên tự tạo callback lồng ghép phức tạp chỉ để giả lập `ifPresentOrElse` trong Java 8.

Nếu ứng dụng chạy Java 17+, `ifPresentOrElse` biểu đạt trực tiếp hai callback và thường là lựa chọn rõ ràng khi cần cả hai hành động. Nếu hỗ trợ Java 8, dùng `if` hoặc cấu trúc khác mà phiên bản đó hỗ trợ.

### Phân biệt `Optional<T>` và Optional primitive

Java có `OptionalInt`, `OptionalLong`, `OptionalDouble`. Chúng có `ifPresent` sử dụng `IntConsumer`, `LongConsumer`, `DoubleConsumer`; ở Java 9+ còn có `ifPresentOrElse` với consumer primitive và `Runnable`.

~~~java
OptionalInt count = OptionalInt.of(3);
count.ifPresentOrElse(
        number -> System.out.println(number * 2),
        () -> System.out.println("no number")
);
~~~

Đoạn minh họa trên in `6` khi chạy và không boxing số nguyên cho tham số `IntConsumer`. Không có sự khác biệt về logic chọn hai nhánh, chỉ khác **kiểu dữ liệu và SAM của consumer**.

## 11. Cách chọn nhanh trong dự án

| Tình huống | Gợi ý | Lý do |
|---|---|---|
| Có dữ liệu thì gửi sự kiện; thiếu thì bỏ qua | `ifPresent` | Chỉ cần một hành động |
| Có người dùng thì hiển thị; thiếu thì thông báo | `ifPresentOrElse` | Hai nhánh hành động rõ ràng |
| Có dữ liệu thì chuyển thành DTO | `map` | Cần biến đổi và giữ kết quả ở dạng Optional |
| Có giá trị thì lấy, rỗng thì dùng chuỗi mặc định | `orElse` hoặc `orElseGet` | Cần một kết quả kiểu `T` |
| Không có giá trị là lỗi nghiệp vụ | `orElseThrow` | Cần giá trị hoặc ngoại lệ |
| Có giá trị thì lưu vào repository | `ifPresent` (nếu phù hợp nghiệp vụ) | Callback biểu diễn side effect |
| Rỗng thì cần gọi dịch vụ tạo fallback, trả về object | `orElseGet` | Supplier tạo giá trị chỉ khi thiếu |
| Không cần lambda, flow phức tạp và yêu cầu return/break | `if/else` thông thường | Dễ kiểm soát flow ở phương thức bao ngoài |

**Kỹ thuật review:** trước khi viết callback, hỏi “tôi cần một **hành động** hay một **giá trị**?”; sau đó hỏi “trạng thái rỗng có cần xử lý không?”. Hai câu hỏi này thường đủ để chọn API chuẩn mà không lạm dụng `Optional`.

## 12. Câu hỏi tự kiểm tra

1. `Optional.empty().ifPresent(action)` có thực hiện `action` không?
2. `Optional.of("x").ifPresentOrElse(action, emptyAction)` thực hiện callback nào?
3. Vì sao `ifPresentOrElse` nhận `Runnable` ở nhánh rỗng thay vì `Consumer<T>`?
4. Khi muốn tạo `String` từ giá trị Optional hoặc fallback, dùng `ifPresentOrElse` có phù hợp không?
5. `ifPresentOrElse` có từ Java mấy? `ifPresent` có từ Java mấy?
6. Nếu callback nhánh có giá trị ném `IllegalStateException`, nhánh rỗng có chạy tiếp không?
7. `Optional.of(null)` có tạo một Optional rỗng không?
8. Nếu Optional có giá trị, việc truyền `null` làm `emptyAction` có chắc ném lỗi ngay ở lời gọi không? Có nên truyền `null` không?
9. `OptionalInt.ifPresentOrElse` sử dụng functional interface gì cho nhánh có giá trị?

**Đáp án gợi ý:**

1. Không, Optional rỗng nên không gọi action.
2. Chỉ `action`, vì có giá trị.
3. Vì không có giá trị kiểu `T` để truyền, nên nhánh rỗng là thao tác không đối số.
4. Không: cả hai phương thức `ifPresent`/`ifPresentOrElse` trả `void`; dùng `map` kết hợp `orElse`/`orElseGet` hoặc `orElseThrow` theo yêu cầu.
5. `ifPresent` từ Java 8; `ifPresentOrElse` từ Java 9.
6. Không; ngoại lệ được truyền ra, không tự chạy fallback.
7. Không; `of(null)` ném `NullPointerException`, dùng `ofNullable(null)`.
8. Không nhất thiết; nhánh rỗng không được chọn. Nhưng truyền callback null là cách dùng không an toàn, cần tránh.
9. `IntConsumer` cho nhánh có số nguyên, `Runnable` cho nhánh rỗng.

## 13. Tài liệu chính thức

- [Java SE 17 API — Optional<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): `ifPresent`, `ifPresentOrElse`, `map`, `orElse`, `orElseGet`.
- [Java SE 17 API — Consumer<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Consumer.html): hợp đồng `void accept(T)`.
- [Java SE 17 API — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html): hợp đồng `void run()`.
- [Java SE 17 API — OptionalInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html): nhánh có giá trị nguyên thủy dùng `IntConsumer`.

**Ghi nhớ:** `ifPresent(Consumer)` xử lý **chỉ khi có giá trị**; `ifPresentOrElse(Consumer, Runnable)` xử lý **một trong hai nhánh có/rỗng**. Cả hai **trả `void`**, vì vậy chỉ dùng khi cần thực hiện hành động. Khi phải tạo hoặc lấy một kết quả, hãy chuyển sang các API như `map`, `orElseGet` hoặc `orElseThrow`.