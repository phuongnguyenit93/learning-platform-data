# Supplier để trì hoãn tạo giá trị hoặc thông báo trong Java

## 1. `Supplier<T>` là gì và vì sao nó hữu ích?

`java.util.function.Supplier<T>` là một **functional interface** biểu diễn hành vi **không nhận đối số và cung cấp một kết quả kiểu `T`** khi được gọi. Phương thức trừu tượng duy nhất (*SAM*) của nó là:

~~~java
T get();
~~~

Ví dụ:

~~~java
Supplier<String> greeting = () -> "Xin chào";
String text = greeting.get();
~~~

Ở đây, `Supplier<String>` là **một công thức để lấy chuỗi**, chứ bản thân việc tạo đối tượng lambda không có nghĩa chuỗi phải được tính ngay. Điều này hữu ích khi việc tạo giá trị có chi phí, khi giá trị chỉ cần ở một nhánh xử lý, hoặc khi muốn tạo thông báo log/lỗi **chỉ lúc cần hiển thị**.

**Điểm mấu chốt:** `Supplier` hỗ trợ **trì hoãn việc đánh giá** (*deferred evaluation*) bằng cách đóng gói công việc thành hành vi để gọi sau. Nhưng **không tự động** quyết định lúc nào cần gọi, không tự cache kết quả và không tự bảo đảm chỉ chạy một lần. Người gọi hoặc API nhận `Supplier` quyết định liệu và khi nào thực hiện `get()`.

So sánh nhanh:

| Biểu thức | Khi nào công việc diễn ra? | Ý nghĩa |
|---|---|---|
| `String value = expensive();` | Ngay khi thực thi phép gán | Tạo giá trị trực tiếp, *eager* |
| `Supplier<String> s = () -> expensive();` | Công việc trong thân lambda chỉ chạy khi `s.get()` được gọi | Đóng gói công việc để trì hoãn |
| `String result = s.get();` | Ngay tại lời gọi `get()` | Yêu cầu thực hiện công việc |
| `Supplier<String> s = this::expensive;` | Lời gọi `expensive()` được trì hoãn đến `get()` | Method reference làm rõ phương thức sẽ chạy |

`expensive()` chỉ là tên minh họa cho một phương thức có sẵn. Với method reference dạng `this::expensive`, biểu thức receiver `this` được xác định khi tạo reference, nhưng **thân `expensive()` chưa chạy** cho đến khi gọi `get()`.

## 2. Cấu trúc và kiểu đích của `Supplier`

Một `Supplier<T>` có **không tham số** và **có kết quả**:

~~~text
                  get()
Supplier<T>  ───────────────► T
             không có input
~~~

Các dạng tạo supplier phổ biến:

~~~java
// Đoạn mã minh họa trong phương thức, đã import các kiểu cần thiết.
Supplier<String> constant = () -> "ready";
Supplier<StringBuilder> builderFactory = StringBuilder::new;
Supplier<Long> timestamp = System::nanoTime;
Supplier<List<String>> listFactory = ArrayList::new;
~~~

- `constant.get()` luôn trả chuỗi `"ready"` theo logic trên; chi phí tính giá trị không đáng kể.
- `builderFactory.get()` gọi constructor và tạo một `StringBuilder` tại mỗi lần gọi, không phải tự tạo ngay khi gán.
- `timestamp.get()` gọi `System.nanoTime()` tại mỗi lần `get()`; số trả về có ý nghĩa đo khoảng thời gian tương đối, không phải timestamp lịch.
- `listFactory.get()` tạo một `ArrayList` mới mỗi lần. Mỗi kết quả có thể là một object khác.

`Supplier` không có tham số generic kiểu primitive. Nếu dùng `Supplier<Integer>`, kết quả là reference `Integer`. Khi muốn lấy primitive và tránh boxing, Java có các interface chuyên biệt:

| Functional interface | SAM | Kết quả |
|---|---|---|
| `Supplier<T>` | `T get()` | Object kiểu `T` |
| `IntSupplier` | `int getAsInt()` | `int` |
| `LongSupplier` | `long getAsLong()` | `long` |
| `DoubleSupplier` | `double getAsDouble()` | `double` |
| `BooleanSupplier` | `boolean getAsBoolean()` | `boolean` |

Đối với những kiểu khác như `float` hoặc `short`, không có bộ primitive supplier chuyên biệt tương ứng trong `java.util.function`; có thể dùng một kiểu gần phù hợp hoặc kiểu wrapper tùy API.

Một lambda không có kiểu đích độc lập: `var s = () -> "ready";` **không hợp lệ** vì trình biên dịch chưa có functional interface để gán lambda. Khai báo `Supplier<String> s = () -> "ready";` hoặc cast sang kiểu đích tương ứng sẽ hợp lệ.

## 3. Ví dụ hoàn chỉnh: tạo giá trị khi thật sự cần

Lưu thành **`SupplierEvaluationDemo.java`**:

~~~java
import java.util.Locale;
import java.util.function.Supplier;

public class SupplierEvaluationDemo {
    private static int builds = 0;

    static String build(String value) {
        builds++;
        System.out.println("build:" + value + "#" + builds);
        return value.toUpperCase(Locale.ROOT);
    }

    static void printWhen(boolean enabled, Supplier<String> message) {
        if (enabled) {
            System.out.println("message=" + message.get());
        }
    }

    public static void main(String[] args) {
        Supplier<String> deferred = () -> build("deferred");

        System.out.println("created, builds=" + builds);
        printWhen(false, deferred);
        System.out.println("afterDisabled=" + builds);
        printWhen(true, deferred);
        printWhen(true, deferred);
        System.out.println("end=" + builds);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac SupplierEvaluationDemo.java
java SupplierEvaluationDemo
~~~

Kết quả stdout:

~~~text
created, builds=0
afterDisabled=0
build:deferred#1
message=DEFERRED
build:deferred#2
message=DEFERRED
end=2
~~~

**Giải thích chính xác thứ tự:**

1. `() -> build("deferred")` tạo một `Supplier<String>` nhưng **không gọi `build`** ngay. Do đó dòng đầu in `builds=0`.
2. `printWhen(false, deferred)` đi qua nhánh không bật nên **không gọi `message.get()`**, giữ số lần tạo giá trị bằng `0`.
3. `printWhen(true, deferred)` gọi `get()`, lần đầu thực thi `build`, in `build:deferred#1` rồi nhận `DEFERRED`.
4. Gọi thêm lần nữa lại thực thi `build` và tăng bộ đếm lên `2`. `Supplier` **không tự ghi nhớ `DEFERRED`**.
5. API ở đây định nghĩa rõ **điều kiện kích hoạt công việc**. Tính trì hoãn đến từ sự phối hợp giữa `Supplier` và việc chỉ gọi `get()` khi cần.

Nếu viết `printWhen(false, () -> build("deferred"))`, công việc cũng chưa chạy; nhưng nếu API nhận `String` và caller truyền `build("deferred")` thì lời gọi sẽ được đánh giá trước khi API xử lý cờ `enabled`.

## 4. Trì hoãn thông báo log và thông báo lỗi

### 4.1. Tại sao không nên tạo chuỗi log đắt đỏ quá sớm?

Khi ghi log, một số thông báo cần format dữ liệu lớn, serialize object hoặc tính thống kê. Nếu mức log đang tắt, ta thường không muốn trả chi phí đó.

~~~java
// Giả sử details() là một phép tính đắt và logger đã được khai báo.
logger.fine("details=" + details());          // details() chạy trước lời gọi fine.
logger.log(Level.FINE, () -> "details=" + details());
~~~

Trong cách thứ hai, `java.util.logging.Logger.log(Level, Supplier<String>)` nhận một supplier tạo thông báo. Logger chỉ yêu cầu tạo thông báo khi thông điệp cần được ghi theo cơ chế kiểm tra mức log; khi `FINE` bị vô hiệu hóa, phần thân supplier **không cần được thực hiện**.

Đoạn trên mang tính minh họa; để biên dịch trong chương trình thực tế cần một biến `logger` kiểu `java.util.logging.Logger`, `import java.util.logging.Level;` và phương thức `details()`.

Một API log có hỗ trợ supplier không hoàn toàn giống một API nhận `String`. Nếu API chỉ nhận `String`, viết `logger.fine(expensiveMessage())` vẫn tính thông báo trước lời gọi; bản thân việc log có bị bỏ qua hay không không đảo ngược được chi phí đã phát sinh.

**Không lạm dụng tác dụng phụ trong supplier log:** một biểu thức như `() -> updateCounterAndBuildMessage()` không nên được dùng để thực hiện thao tác bắt buộc, vì khi log bị tắt, thân supplier có thể hoàn toàn không chạy. Nội dung supplier nên chủ yếu **tạo chuỗi mô tả**, không thay đổi kết quả nghiệp vụ.

### 4.2. Thông báo lỗi khi kiểm tra `null`

Java 8+ có overload:

~~~java
Objects.requireNonNull(object, Supplier<String> messageSupplier)
~~~

Khi `object` khác `null`, thông báo lỗi **không cần được tính**. Khi `object == null`, overload này gọi supplier để lấy thông báo cho `NullPointerException`.

Ví dụ:

~~~java
// Minh họa; có import java.util.Objects và java.util.function.Supplier.
String username = "alice";
String safe = Objects.requireNonNull(
        username,
        () -> "username must not be null"
);
~~~

Ở đây giá trị `safe` là `"alice"` và lambda thông báo không được gọi. Với trường hợp null, thông báo được tạo tại nhánh ném ngoại lệ.

Sự trì hoãn này có giá trị nếu việc tạo thông báo cần truy vấn metadata, tổng hợp trạng thái hoặc tạo chuỗi dài. Với chuỗi literal rẻ tiền, overload nhận `String` cũng có thể đơn giản và rõ ràng hơn. Đừng đổi mọi thông báo cố định sang `Supplier` một cách máy móc.

### 4.3. Chương trình hoàn chỉnh: thông báo chỉ tạo khi thất bại

Lưu thành **`SupplierMessageDemo.java`**:

~~~java
import java.util.Objects;

public class SupplierMessageDemo {
    private static int messagesBuilt = 0;

    static String makeMessage() {
        messagesBuilt++;
        System.out.println("construct message #" + messagesBuilt);
        return "value is required";
    }

    public static void main(String[] args) {
        String valid = Objects.requireNonNull("ok", SupplierMessageDemo::makeMessage);
        System.out.println("valid=" + valid + "; messages=" + messagesBuilt);

        try {
            Objects.requireNonNull(null, SupplierMessageDemo::makeMessage);
        } catch (NullPointerException ex) {
            System.out.println("error=" + ex.getMessage());
        }

        System.out.println("final messages=" + messagesBuilt);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SupplierMessageDemo.java
java SupplierMessageDemo
~~~

Stdout:

~~~text
valid=ok; messages=0
construct message #1
error=value is required
final messages=1
~~~

`SupplierMessageDemo::makeMessage` là method reference đến phương thức `static` không nhận tham số, trả `String` — khớp SAM của `Supplier<String>`. Nó là một **công thức tạo thông báo**, không phải chuỗi thông báo đã tạo.

Nếu thông báo có nội dung nhạy cảm, cần kiểm soát dữ liệu được đưa vào log/lỗi. Trì hoãn tạo thông báo giảm công việc dư thừa nhưng **không** tự giải quyết vấn đề bảo mật, escaping hoặc chính sách hiển thị lỗi.

## 5. `Optional.orElse` và `Optional.orElseGet`: bẫy eager/lazy thường gặp

Sự khác biệt giữa hai phương thức:

~~~java
T orElse(T other)
T orElseGet(Supplier<? extends T> supplier)
~~~

- `orElse(other)` nhận **giá trị** `other`. Nếu viết `orElse(expensiveFallback())`, Java đánh giá `expensiveFallback()` **trước khi gọi `orElse`**, ngay cả khi `Optional` đã có giá trị.
- `orElseGet(supplier)` nhận **hành vi tạo giá trị**. Supplier chỉ được gọi khi `Optional` **rỗng**.
- Khi fallback rẻ, không có tác dụng phụ và đã có sẵn, `orElse(constant)` có thể đơn giản hơn; không cần coi `orElse` luôn sai.

### Ví dụ Java 17 chạy độc lập

Lưu thành **`SupplierFallbackDemo.java`**:

~~~java
import java.util.Objects;
import java.util.Optional;

public class SupplierFallbackDemo {
    private static int fetches = 0;

    static String fetchBackup() {
        fetches++;
        System.out.println("fetch #" + fetches);
        return "backup-" + fetches;
    }

    public static void main(String[] args) {
        Optional<String> found = Optional.of("primary");

        String eager = found.orElse(fetchBackup());
        System.out.println("eager=" + eager);

        String lazy = found.orElseGet(SupplierFallbackDemo::fetchBackup);
        System.out.println("lazy=" + lazy);

        String missing = Optional.<String>empty()
                .orElseGet(SupplierFallbackDemo::fetchBackup);
        System.out.println("missing=" + missing);

        String present = Objects.requireNonNullElseGet(
                "set", SupplierFallbackDemo::fetchBackup);
        System.out.println("present=" + present);

        String fallback = Objects.requireNonNullElseGet(
                null, SupplierFallbackDemo::fetchBackup);
        System.out.println("fallback=" + fallback);
        System.out.println("fetches=" + fetches);
    }
}
~~~

Chạy:

~~~bash
javac SupplierFallbackDemo.java
java SupplierFallbackDemo
~~~

Stdout:

~~~text
fetch #1
eager=primary
lazy=primary
fetch #2
missing=backup-2
present=set
fetch #3
fallback=backup-3
fetches=3
~~~

**Phân tích từng nhánh:**

1. `found.orElse(fetchBackup())` gọi `fetchBackup()` ngay, tạo `backup-1` dù `found` đang chứa `primary`. `orElse` vẫn trả `primary` và bỏ qua giá trị fallback đã tính.
2. `found.orElseGet(SupplierFallbackDemo::fetchBackup)` không gọi phương thức tạo fallback vì `found` có dữ liệu.
3. `Optional.empty().orElseGet(...)` gọi supplier để tạo `backup-2` vì không có giá trị.
4. `Objects.requireNonNullElseGet("set", supplier)` trả `"set"` và không gọi supplier; overload này có từ Java 9.
5. `Objects.requireNonNullElseGet(null, supplier)` gọi supplier, tạo `backup-3`; khác `Optional.orElseGet`, phương thức `requireNonNullElseGet` yêu cầu giá trị được cung cấp khi fallback cũng **không được null**, nếu không sẽ ném `NullPointerException`.

`Optional.orElseGet` là ví dụ rõ ràng về **API chủ động quyết định khi nào gọi `get()`**. Không có phép màu “lazy” trong mọi phương thức chỉ vì tham số là lambda: hành vi cụ thể phụ thuộc hợp đồng của API nhận supplier.

## 6. Trì hoãn tạo object: factory không tham số

Một ứng dụng hữu ích khác là cung cấp một **factory** để API có thể tạo object theo nhu cầu:

~~~java
Supplier<List<String>> factory = ArrayList::new;

List<String> first = factory.get();
List<String> second = factory.get();
~~~

Đoạn minh họa này cần import `java.util.function.Supplier`, `java.util.List` và `java.util.ArrayList`. Hai lần gọi factory tạo ra **hai danh sách mutable mới**. `Supplier` không có nghĩa lúc khai báo phải tạo danh sách rỗng rồi trả lại mãi một đối tượng.

Phân biệt hai thiết kế:

~~~java
List<String> shared = new ArrayList<>();
Supplier<List<String>> sameList = () -> shared;
Supplier<List<String>> newList = ArrayList::new;
~~~

- `sameList.get()` trả **cùng một danh sách** ở mỗi lần gọi.
- `newList.get()` tạo danh sách mới ở mỗi lần gọi.
- Cả hai đều là `Supplier<List<String>>`, nên chỉ nhìn vào kiểu **không thể biết** giá trị có mới, bất biến, cache hay thread-safe không. Phải đọc **hợp đồng và cách triển khai**.

Cách này phù hợp khi ta muốn trì hoãn khởi tạo buffer, đối tượng chiến lược, hoặc tài nguyên chỉ cần trong một nhánh. Nếu object quản lý tài nguyên như connection, stream hoặc file handle, đừng dùng supplier để che giấu vòng đời đóng tài nguyên; vẫn phải có try-with-resources hoặc cơ chế quản lý vòng đời phù hợp.

## 7. Phân biệt trì hoãn, tính lười của stream, bất đồng bộ và caching

Bốn ý tưởng dễ bị trộn lẫn nhưng **không giống nhau**:

| Ý tưởng | Cách hoạt động | Ví dụ |
|---|---|---|
| Trì hoãn tạo giá trị | Đóng gói công việc, thực hiện khi có lời gọi `get()` hoặc API kích hoạt | `Supplier<T>` |
| Stream lazy | Các bước trung gian của stream thường chỉ chạy khi có terminal operation | `stream.map(...).filter(...).toList()` |
| Bất đồng bộ | Công việc có thể chạy ở thread khác, không nhất thiết chờ `get()`/`join()` mới chạy | `CompletableFuture.supplyAsync(supplier)` |
| Ghi nhớ kết quả (*memoization*) | Tính một lần rồi trả lại kết quả đã lưu theo chính sách cache | Supplier được bọc bằng lớp cache tự thiết kế |

`CompletableFuture.supplyAsync(supplier)` nhận `Supplier<T>` nhưng **sắp lịch chạy công việc** khi phương thức được gọi. Công việc có thể bắt đầu ngay trên executor, **không** chờ ai gọi `future.join()` mới thực hiện. `Supplier` chỉ biểu diễn công việc không tham số, còn chính API quy định cơ chế thời gian.

### 7.1. `Stream.generate` có thể gọi supplier nhiều lần

~~~java
Supplier<String> next = () -> "x";
List<String> values = Stream.generate(next).limit(3).toList();
~~~

Với stream tuần tự trong ví dụ này, `generate` tạo ra phần tử thông qua supplier khi có terminal operation `toList()`, và kết quả là `[x, x, x]`. Nó không tạo nguồn dữ liệu vô hạn ngay lúc khai báo. Cũng không nên giả định supplier chỉ chạy đúng một lần: API sử dụng nó như một **nguồn sinh nhiều phần tử**.

Đoạn trên minh họa, cần import `java.util.function.Supplier`, `java.util.List` và `java.util.stream.Stream`.

### 7.2. Không mặc định có memoization

~~~java
Supplier<Long> clock = System::nanoTime;
long first = clock.get();
long second = clock.get();
~~~

Hai lần gọi có thể trả giá trị khác nhau. Nhưng kể cả supplier trả cùng giá trị mỗi lần, điều đó **không chứng minh có cache**. Chẳng hạn `() -> "constant"` không thực hiện công việc đáng kể, song supplier vẫn có thể được gọi nhiều lần.

Muốn tính tối đa một lần, cần thiết kế riêng một wrapper cache và định nghĩa rõ có cache `null` không, có cache lỗi không, xử lý đồng thời thế nào, khi nào làm mới dữ liệu. Một biến `final Supplier<T>` cũng **không** có nghĩa kết quả được lưu; `final` chỉ ngăn gán lại biến/tham chiếu.

## 8. Hợp đồng lỗi, `null` và thread safety

### 8.1. Có thể trả `null` hoặc ném unchecked exception

`Supplier<T>.get()` không cấm trả `null`. Cần kiểm tra hợp đồng của API tiêu thụ supplier:

- `Optional.orElseGet(supplier)` có thể nhận kết quả null và trả null khi Optional rỗng.
- `Objects.requireNonNullElseGet(value, supplier)` không cho phép kết quả fallback là null khi `value` bằng null; nếu không sẽ ném `NullPointerException`.
- `Objects.requireNonNull(obj, messageSupplier)` có thể nhận thông báo null cho `NullPointerException`; không nên dựa vào chuỗi thông báo trong mã nghiệp vụ.

`Supplier.get()` không khai báo `throws` checked exception. Nếu logic tạo giá trị cần I/O ném `IOException`, ta phải xử lý trong lambda, bọc thành unchecked exception nếu phù hợp, hoặc định nghĩa functional interface riêng có `throws` được chấp nhận bởi API của mình. Không thể viết lambda để checked exception thoát ra từ `Supplier.get()` một cách tùy ý.

### 8.2. Không bảo đảm thread-safe

Nếu nhiều thread gọi cùng một supplier, thân lambda có thể chạy đồng thời, đặc biệt khi supplier capture state hoặc được dùng trong API bất đồng bộ. `Supplier<T>` không quy định điều kiện chỉ một thread chạy, không khóa, không retry an toàn và không hạn chế tác dụng phụ.

Ví dụ trong ứng dụng nhiều thread, `() -> ++counter` với `counter` là trường có thể thay đổi không tự động trở thành thao tác nguyên tử chỉ nhờ kiểu `Supplier<Integer>`. Tùy yêu cầu, cân nhắc `AtomicInteger`, đồng bộ hóa, dữ liệu bất biến hoặc factory stateless.

### 8.3. Capture và thời điểm quan sát dữ liệu

Lambda có thể capture biến cục bộ là `final` hoặc **effectively final**:

~~~java
String prefix = "id:";
Supplier<String> id = () -> prefix + 42;
~~~

Nếu gán lại `prefix` sau khi định nghĩa lambda, compiler báo lỗi vì biến không còn effectively final. Nhưng nếu supplier capture **một object mutable**, nội dung object đó có thể thay đổi trước lúc `get()` được gọi. Vì vậy, “trì hoãn” còn mang ý nghĩa giá trị được tính theo **trạng thái ở thời điểm gọi**, chứ không tự động tạo snapshot lúc khai báo.

Điều này rất quan trọng với logging: không nên trì hoãn tham chiếu đến một đối tượng có thể biến đổi rồi giả định thông báo sau này sẽ phản ánh chính xác trạng thái lúc xảy ra sự kiện.

## 9. Thiết kế API nhận hành vi `Supplier`

Khi thiết kế phương thức, có thể dùng `Supplier<T>` để diễn tả rõ “tôi chưa cần giá trị, hãy cho tôi cách lấy giá trị nếu cần”.

Ví dụ, phương thức sau dùng fallback khi một phép kiểm tra không đạt:

~~~java
static <T> T choose(boolean usePrimary, T primary, Supplier<? extends T> fallback) {
    return usePrimary ? primary : fallback.get();
}
~~~

Đây là **đoạn minh họa phương thức** cần import `java.util.function.Supplier`. `choose(true, primary, fallback)` không gọi supplier; `choose(false, primary, fallback)` gọi một lần theo thân phương thức hiện tại.

**Lưu ý quan trọng về API:** `primary` là **giá trị**, nên nếu caller viết `choose(true, computePrimary(), fallback)`, `computePrimary()` đã chạy trước lời gọi `choose`. Nếu muốn trì hoãn cả hai nhánh, API phải nhận hai supplier:

~~~java
static <T> T chooseLazy(
        boolean usePrimary,
        Supplier<? extends T> primary,
        Supplier<? extends T> fallback) {
    return usePrimary ? primary.get() : fallback.get();
}
~~~

Lúc gọi:

~~~java
// Giả sử computePrimary/computeFallback trả String và các phương thức đã tồn tại:
String result = chooseLazy(
        condition,
        () -> computePrimary(),
        () -> computeFallback()
);
~~~

Phương thức chỉ gọi một trong hai supplier, tùy `condition`. Đây là thiết kế **lazy branch selection**, tránh tính toán một nhánh rồi bỏ kết quả.

Không nên ép mọi API nhận `Supplier`. Khi giá trị luôn cần ngay, rẻ và không có điều kiện bỏ qua, tham số kiểu `T` trực tiếp thường dễ đọc hơn. Supplier có thêm một tầng gián tiếp và có thể khiến thời điểm tính toán khó đoán nếu API không mô tả rõ.

## 10. Thêm ví dụ API chuẩn sử dụng `Supplier`

| API Java | Supplier dùng để làm gì? | Khi nào công việc được yêu cầu? |
|---|---|---|
| `Optional.orElseGet(Supplier<? extends T>)` | Tạo giá trị dự phòng | Khi Optional rỗng |
| `Optional.or(Supplier<? extends Optional<? extends T>>)` | Tạo Optional thay thế | Khi Optional rỗng |
| `Objects.requireNonNull(T, Supplier<String>)` | Tạo thông báo lỗi | Khi đối tượng là null |
| `Objects.requireNonNullElseGet(T, Supplier<? extends T>)` | Tạo fallback khác null | Khi giá trị đầu vào là null |
| `java.util.logging.Logger.log(Level, Supplier<String>)` | Tạo thông báo log | Khi logger quyết định thông báo cần được ghi |
| `Stream.generate(Supplier<? extends T>)` | Tạo phần tử stream | Trong quá trình tiêu thụ stream |
| `ThreadLocal.withInitial(Supplier<? extends T>)` | Khởi tạo giá trị ban đầu của mỗi thread | Khi thread cần giá trị lần đầu qua `get()` |
| `CompletableFuture.supplyAsync(Supplier<U>)` | Cung cấp công việc tạo kết quả bất đồng bộ | Khi task được executor thực thi sau khi được sắp lịch |

Bảng này cũng cho thấy cùng một `Supplier<T>` nhưng **hợp đồng kích hoạt khác nhau**. Không thể suy luận “mọi supplier chỉ chạy khi cần” mà không biết API định nghĩa thế nào: ở `Stream.generate` có thể chạy nhiều lần; ở `Optional.orElseGet` có thể không chạy lần nào; ở `supplyAsync` có thể chạy dù caller chưa chờ kết quả.

## 11. Lỗi phổ biến và cách sửa

### Lỗi 1: Tính fallback trước rồi mới bọc thành supplier

~~~java
// Bọc giá trị đã được tính, không còn trì hoãn công việc.
String alreadyBuilt = expensiveFallback();
Supplier<String> ineffective = () -> alreadyBuilt;

// Trì hoãn lời gọi thực sự:
Supplier<String> deferred = () -> expensiveFallback();
~~~

Nếu `expensiveFallback()` được gọi ở dòng đầu thì chi phí đã xảy ra. Supplier thứ nhất chỉ trì hoãn **việc trả giá trị có sẵn**, không trì hoãn **việc tạo giá trị**.

### Lỗi 2: Tưởng rằng `get()` chỉ chạy một lần

~~~java
Supplier<String> value = () -> expensiveFallback();
value.get();
value.get();
~~~

Cách viết trên gọi thân lambda **hai lần**. Nếu cần một giá trị dùng chung, phải lấy một lần và lưu vào biến, hoặc sử dụng cache được thiết kế rõ.

### Lỗi 3: Nhầm `Supplier<T>` với `Function<T,R>`

~~~java
Supplier<String> message = () -> "ready";                // Không tham số.
Function<Integer, String> label = n -> "id-" + n;        // Có một tham số.
~~~

Dùng `Supplier` cho công việc cần đầu vào sẽ khiến thiết kế phải capture dữ liệu bên ngoài. Nếu giá trị thay đổi theo tham số mỗi lần gọi, `Function` thường phù hợp hơn.

### Lỗi 4: Giữ tác dụng phụ bắt buộc trong supplier thông báo

Nếu logic bắt buộc như ghi audit hoặc cập nhật đơn hàng nằm trong `() -> buildLogMessageAndSaveOrder()`, nhánh log không chạy sẽ bỏ qua luôn logic. Hãy thực hiện logic nghiệp vụ độc lập rồi chỉ sử dụng supplier để tạo **phần mô tả**.

### Lỗi 5: Cho rằng phương thức nhận supplier luôn gọi đúng một lần

`Supplier` là kiểu, **không phải lời hứa về số lần gọi**. Đọc contract của `logIf`, `orElseGet`, `Stream.generate`, `supplyAsync` hoặc phương thức tự viết để biết khả năng gọi 0, 1 hoặc nhiều lần.

### Lỗi 6: Đo tính hiệu năng chỉ từ ký hiệu lambda

Lambda có chi phí tạo/lưu callback và gọi gián tiếp trong một số ngữ cảnh; đồng thời có thể tránh công việc nặng khi nhánh không sử dụng. Với công việc tạo giá trị rất rẻ và luôn cần, supplier có thể không mang lại lợi ích. **Đo bằng profiler/benchmark** khi hiệu năng là mục tiêu, không kết luận rằng `() -> x` luôn nhanh hơn truyền `x`.

### Lỗi 7: Dùng kết quả từ supplier đã hết hạn hoặc không an toàn

Nếu supplier trả object có vòng đời ngắn (connection, stream), gọi `get()` nhiều lần có thể tạo thêm tài nguyên hoặc trả tài nguyên đã đóng, tùy triển khai. Không thể suy ra bảo đảm quản lý tài nguyên chỉ từ kiểu `Supplier<T>`.

### Lỗi 8: Quên chính sách lỗi ở fallback

`orElseGet` có thể không gọi fallback khi có sẵn giá trị, nhưng nếu fallback thực sự chạy và ném unchecked exception, exception đó vẫn thoát ra. Supplier không tự retry hoặc nuốt ngoại lệ. API của bạn cần xác định rõ lỗi được chuyển tiếp, chuyển dạng hay xử lý.

## 12. Checklist thực hành cho lazy value và lazy message

Khi cân nhắc truyền `Supplier<T>`, hãy tự kiểm tra:

1. Công việc tạo giá trị **có thể được bỏ qua** ở một số nhánh không?
2. Supplier đang đóng gói **công việc thật sự** hay chỉ trả một giá trị đã tính?
3. **Ai** sẽ gọi `get()` và vào thời điểm nào?
4. Có thể gọi **0, 1 hoặc nhiều lần** không? Có thể gọi song song không?
5. Có cần **cache** kết quả hay mỗi lần phải tạo mới?
6. Dữ liệu được capture có thể thay đổi giữa lúc tạo supplier và lúc `get()` không?
7. Nếu supplier trả `null` hoặc ném exception, API nhận có xử lý đúng không?
8. Với log/error, có tác dụng phụ bắt buộc nào bị đặt nhầm vào callback không?
9. Với fallback, có nên dùng `orElseGet` thay `orElse` vì fallback đắt hoặc có tác dụng phụ không?
10. Test đã xác minh **số lần gọi** ở cả nhánh dùng và không dùng chưa?

Một kỹ thuật test đơn giản là cho supplier tăng bộ đếm hoặc ghi dấu khi `get()` chạy. Kỳ vọng của API phải được viết rõ: nhánh không cần dữ liệu thì bộ đếm không tăng; nhánh cần dữ liệu thì tăng đúng số lần đã cam kết.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** `Supplier<String> s = () -> load();` có gọi `load()` ngay lúc khai báo không?

**Câu 2.** Vì sao `Optional.of("x").orElse(expensive())` vẫn gọi `expensive()`, còn `Optional.of("x").orElseGet(() -> expensive())` thì không?

**Câu 3.** Nếu gọi cùng một supplier hai lần, Java có tự cache giá trị ở lần đầu không?

**Câu 4.** Khi nào `Objects.requireNonNull(value, () -> buildMessage())` cần tạo thông báo lỗi?

**Câu 5.** Vì sao không nên đặt logic cập nhật dữ liệu bắt buộc vào supplier chỉ dùng cho log?

**Câu 6.** Hai supplier `() -> sharedList` và `ArrayList::new` có cùng một hợp đồng về danh sách được trả hay không?

**Câu 7.** `CompletableFuture.supplyAsync(supplier)` có chờ đến `join()` mới bắt đầu gọi supplier không?

**Câu 8.** Nếu `Supplier<String>` trả `null`, điều đó có luôn vi phạm giao diện `Supplier` không?

**Đáp án gợi ý:** (1) Không, chỉ gọi khi `get()`/API tiêu thụ kích hoạt. (2) Vì đối số của `orElse` được đánh giá trước lời gọi, còn `orElseGet` nhận callback và chỉ gọi khi rỗng. (3) Không; muốn cache cần cơ chế riêng. (4) Khi `value == null`. (5) Vì log có thể bị tắt và callback không chạy. (6) Không: cái đầu có thể trả cùng object, cái sau thường tạo mới theo constructor. (7) Không; task có thể được sắp lịch và thực thi trước `join()`. (8) Không; `Supplier` cho phép kết quả là reference null, nhưng API sử dụng có thể cấm.

## 14. Tài liệu chính thức

- [Java SE 17 API — Supplier<T>](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Supplier.html): hợp đồng `T get()`.
- [Java SE 17 API — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): `orElse`, `orElseGet` và `or`.
- [Java SE 17 API — Objects](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html): `requireNonNull` và `requireNonNullElseGet`.
- [Java SE 17 API — Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): overload `log(Level, Supplier<String>)`.
- [Java SE 17 API — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `generate` và tính chất lazy của pipeline.
- [Java SE 17 API — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `supplyAsync`.

**Ghi nhớ:** `Supplier<T>` nghĩa là **“hãy cho tôi cách tạo/lấy `T` khi cần”**, không phải “hãy tạo `T` ngay”. Lợi ích lớn nhất xuất hiện ở **fallback đắt**, **thông báo chỉ cần khi log/lỗi được kích hoạt** và **factory tạo đối tượng theo nhu cầu**. Muốn đúng, phải hiểu **API nào gọi `get()`, lúc nào và bao nhiêu lần**; supplier không tự cache, không tự bất đồng bộ và không tự bảo đảm thread safety.