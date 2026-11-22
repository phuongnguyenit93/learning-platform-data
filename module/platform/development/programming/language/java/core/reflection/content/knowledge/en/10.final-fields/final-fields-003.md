# Static final: không thể ghi bằng cách mở quyền Reflection thông thường

## 1. Câu hỏi cốt lõi

Trong Java, một field khai báo `static final` là **field thuộc về class** (hoặc interface) và **tham chiếu/giá trị của field không được gán lại sau khi được khởi tạo** theo quy tắc của ngôn ngữ. Khi dùng Reflection, kể cả khi `Field.setAccessible(true)` hoặc `Field.trySetAccessible()` đã cho phép truy cập member vốn là private, các API ghi thông thường như `Field.set(...)`, `Field.setInt(...)` vẫn **không được cấp quyền ghi vào `static final`**.

Ví dụ:

~~~java
class Config {
    private static final int PORT = 8080;
}
~~~

Lệnh `Config.class.getDeclaredField("PORT")` có thể lấy được metadata về field; nếu quyền module cho phép thì `setAccessible(true)` có thể cho đọc `PORT`. Tuy nhiên, gọi `field.setInt(null, 9090)` sẽ ném `IllegalAccessException`. Đừng nhầm việc lấy được `Field` hoặc bật được quyền truy cập với quyền **sửa** field đó.

Quy tắc quan trọng trong JDK 17+ (và tiếp tục trong API JDK 26): **mọi `static final` được khai báo trong class hoặc interface là *non-modifiable final fields* đối với `java.lang.reflect.Field`**. Chính `AccessibleObject.setAccessible` và `Field.set` định nghĩa giới hạn này; không có sự khác biệt cho phép ghi chỉ vì field có `private`, `public`, kiểu primitive, `String` hay một kiểu object.

## 2. Hiểu đúng ba lớp kiểm tra

Với field `private static final`, có ba câu hỏi khác nhau:

1. **Có tìm được khai báo field?** `getDeclaredField("name")` tìm field khai báo trong class, bất kể `public` hay `private`. Nó có thể ném `NoSuchFieldException` nếu tên sai.
2. **Có được truy cập member đó không?** `setAccessible(true)` yêu cầu nới kiểm tra ngôn ngữ Java; `trySetAccessible()` trả về `true`/`false` tuỳ quyền. Java Platform Module System (JPMS) vẫn có thể từ chối deep reflection khi package không mở cho caller.
3. **Field có cho phép ghi không?** Dù câu 2 thành công, field `static final` vẫn là *non-modifiable final field*. Gọi các setter Reflection thông thường sẽ ném `IllegalAccessException`.

Các cơ chế hoạt động ở những tầng khác nhau. `setAccessible(true)` **không xóa modifier `final`**, cũng không cho phép ứng dụng bỏ qua quy tắc ghi của `Field.set`.

| Thao tác | Trên field `static final` |
| --- | --- |
| `Class.getDeclaredField("X")` | Lấy metadata thành công nếu field tồn tại; không mặc định cấp quyền đọc/ghi. |
| `Field.getModifiers()` | Có thể kiểm tra `Modifier.isStatic(...)` và `Modifier.isFinal(...)`. |
| `Field.setAccessible(true)` | Có thể thành công nếu caller có quyền mở truy cập; chỉ hỗ trợ đọc nếu field là *non-modifiable final*. |
| `Field.trySetAccessible()` | Có thể trả `true`; kết quả này **không** có nghĩa được phép ghi. |
| `Field.get(null)` / `getInt(null)` | Đọc nếu được phép; đối số đối tượng bị bỏ qua đối với field static. |
| `Field.set(null, value)` / `setInt(null, value)` | Ném `IllegalAccessException` vì không có quyền ghi `static final`, ngay cả sau khi mở quyền truy cập. |

Với setter Reflection cho field static, đối số đối tượng thường truyền `null` vì không gắn với instance. Với field instance, phải truyền đối tượng đúng kiểu. Đối số `null` **không phải nguyên nhân** khiến ghi `static final` bị từ chối.

## 3. Ví dụ đầy đủ, chạy với Java 17 trở lên

Lưu đoạn sau vào file `StaticFinalDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.List;

class Settings {
    private static final int LIMIT = 10;
    private static final List<String> TAGS = new ArrayList<>(List.of("A"));
    private static int count = 1;

    static List<String> tags() {
        return TAGS;
    }
}

public class StaticFinalDemo {
    public static void main(String[] args) throws Exception {
        Field limit = Settings.class.getDeclaredField("LIMIT");
        System.out.println("static final: "
                + (Modifier.isStatic(limit.getModifiers())
                && Modifier.isFinal(limit.getModifiers())));
        System.out.println("accessible: " + limit.trySetAccessible());
        System.out.println("LIMIT: " + limit.getInt(null));

        try {
            limit.setInt(null, 20);
        } catch (IllegalAccessException e) {
            System.out.println("change LIMIT: " + e.getClass().getSimpleName());
        }

        Field tags = Settings.class.getDeclaredField("TAGS");
        tags.setAccessible(true);
        try {
            tags.set(null, new ArrayList<>(List.of("X")));
        } catch (IllegalAccessException e) {
            System.out.println("replace TAGS: " + e.getClass().getSimpleName());
        }

        Settings.tags().add("B");
        System.out.println("mutate TAGS object: " + Settings.tags());

        Field count = Settings.class.getDeclaredField("count");
        count.setAccessible(true);
        count.setInt(null, 2);
        System.out.println("change non-final static: " + count.getInt(null));
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac --release 17 StaticFinalDemo.java
java StaticFinalDemo
~~~

Stdout đã được kiểm tra với chương trình biên dịch ở chế độ tương thích Java 17:

~~~text
static final: true
accessible: true
LIMIT: 10
change LIMIT: IllegalAccessException
replace TAGS: IllegalAccessException
mutate TAGS object: [A, B]
change non-final static: 2
~~~

**Giải thích từng kết quả:**

- `LIMIT` có đồng thời cờ `static` và `final`. `trySetAccessible()` trả `true` bởi mã ví dụ chạy trên class path: class `Settings` thuộc unnamed module có package mở cho reflection. Điều đó cho phép đọc `10`.
- `limit.setInt(null, 20)` không được phép ghi vì field là `static final`. `IllegalAccessException` là kết quả phải xử lý, dù lệnh nới quyền trước đó thành công.
- `TAGS` là một **final reference** tới `ArrayList`. `tags.set(null, new ArrayList<>(...))` cố thay **tham chiếu field**, nên cũng thất bại.
- `Settings.tags().add("B")` thay **trạng thái object** đã được field tham chiếu, không gán lại chính field. Vì object là `ArrayList` có thể thay đổi, thao tác thành công và in `[A, B]`.
- `count` được khai báo `static` nhưng **không `final`**, nên Reflection có thể sửa field sau khi mở quyền. Kết quả `2` cho thấy hạn chế ghi ở trên gắn với `final`.

Bài học này không phụ thuộc vào mẹo can thiệp nội bộ JVM. Khả năng mở quyền đến từ việc mã ví dụ nằm trong unnamed module; với class trong **named module** không mở package cho caller, `trySetAccessible()` có thể trả `false` ngay trước bước đọc.

## 4. `final` giữ nguyên tham chiếu, không làm object bất biến

Xét:

~~~java
private static final List<String> ITEMS = new ArrayList<>();
~~~

Hai hành động khác bản chất:

- **Thay field:** `ITEMS = new ArrayList<>();` bị trình biên dịch chặn sau khi khởi tạo; `Field.set(null, anotherList)` cũng không được phép với `static final`.
- **Thay trạng thái object:** `ITEMS.add("x")` vẫn có thể chạy vì `ArrayList` là cấu trúc mutable. Lúc này field vẫn trỏ tới cùng object.

Tương tự, `static final StringBuilder BUILDER = new StringBuilder("A");` cho phép `BUILDER.append("B")` dù không cho phép `BUILDER = new StringBuilder("C")`. Ngược lại, `String` là immutable nên không có thao tác thay đổi nội dung của chính đối tượng `String`.

Để có collection chỉ đọc ở cấp API, cân nhắc `List.of(...)` hay bản sao bất biến `List.copyOf(...)`. Dù vậy, cần xét khả năng mutability của **các phần tử** nếu chúng là object phức tạp; `final` và collection không hỗ trợ thay đổi cấu trúc không bảo đảm deep immutability của cả đồ thị object.

## 5. Compile-time constant và field được khởi tạo tại runtime

Một số field `static final` là **constant variables** theo Java Language Specification: chúng có kiểu primitive hoặc `String`, được khai báo `final` và khởi tạo bằng *constant expression*. Ví dụ:

~~~java
public static final int TIMEOUT = 30;
public static final String MODE = "safe";
~~~

Khi mã khác tham chiếu các hằng này, trình biên dịch có thể ghi giá trị hằng trực tiếp vào bytecode của mã sử dụng (*inlining*). Thay đổi giá trị trong thư viện nhưng **không biên dịch lại** mã sử dụng có thể khiến chương trình tiếp tục thấy giá trị cũ. Vì thế, đừng thiết kế lại cấu hình runtime bằng cách tìm cách sửa field constant.

Field sau cũng là `static final` nhưng giá trị được quyết định khi class khởi tạo:

~~~java
public static final int STARTED_AT_SECOND =
        java.time.LocalTime.now().getSecond();
~~~

Đây **không phải** constant variable có giá trị xác định tại compile time. Tuy nhiên, nó **vẫn không thể bị ghi bởi setter Reflection thông thường**, vì `static final` nào cũng thuộc nhóm không cho phép ghi. Quy tắc về *inlining* và quy tắc về quyền ghi Reflection là hai điều riêng biệt.

Một field `static final` có thể được gán trong static initializer:

~~~java
static final int VALUE;

static {
    VALUE = 42;
}
~~~

Cách gán này hợp lệ **trong quá trình khởi tạo class** theo quy tắc Java source. Nó không mở ra quyền dùng Reflection gán lại sau khi khởi tạo.

## 6. So với các loại `final` khác

| Loại field | `Field.set` sau khi `setAccessible(true)` thành công | Lưu ý |
| --- | --- | --- |
| `static final` trong class/interface | **Không thể ghi.** | Không phụ thuộc kiểu field là primitive hay reference. |
| `final` instance trong class thông thường | Ở Java 17–25 có thể được Reflection cho ghi trong các điều kiện được tài liệu cho phép. | Không nên dùng ngoài các tình huống khởi tạo/tái dựng đối tượng đặc thù; code/JIT có thể tiếp tục quan sát giá trị cũ. |
| `final` instance thuộc `record` | **Không thể ghi bằng cơ chế nới quyền thông thường.** | Record được bảo vệ bởi quy tắc *non-modifiable final field*. |
| `final` thuộc hidden class | **Không thể ghi bằng cơ chế nới quyền thông thường.** | Không được coi như final instance của class thông thường. |
| `static` nhưng không `final` | Có thể ghi nếu quyền truy cập và kiểu giá trị hợp lệ. | Ví dụ `count` trong chương trình ở trên. |

Các giới hạn Reflection dành cho `final` instance đang tiếp tục được thắt chặt: **JDK 26** theo JEP 500 bắt đầu cảnh báo các lần ghi *final instance field* bằng deep reflection, có tùy chọn kiểm soát riêng (như `--illegal-final-field-mutation`). Hành vi ghi này được định hướng sẽ bị chặn mặc định trong phiên bản tương lai. Điểm quan trọng với bài này: **quy tắc cấm ghi `static final` đã có từ trước; các cờ cho phép final-field mutation của JDK mới không chuyển `static final` thành field ghi được.**

Không nên dựa vào việc từng sửa được `final instance field` ở một JDK cũ để suy ra `static final` có thể sửa theo cách tương tự.

## 7. Các API và ngoại lệ liên quan

### `Field.setAccessible(true)` và `trySetAccessible()`

- `setAccessible(true)` yêu cầu nới kiểm tra truy cập Java. Nó có thể ném `InaccessibleObjectException` nếu caller không được phép mở member theo JPMS.
- `trySetAccessible()` trả `false` nếu không thể bật quyền truy cập, thay vì ném `InaccessibleObjectException` cho tình huống quyền thông thường đó.
- **Cả hai không tạo quyền ghi** cho `static final`. Do đó chương trình ở phần 3 vẫn nhận `IllegalAccessException` tại setter sau khi `trySetAccessible()` trả `true`.

### `Field.get(...)` và `Field.set(...)`

`Field.get(null)` và các getter kiểu primitive như `Field.getInt(null)` đọc field static nếu quyền truy cập cho phép. `Field.set(null, value)` và các setter primitive phải vượt qua **kiểm tra quyền ghi**, nên `static final` bị từ chối. Các vấn đề khác như kiểu truyền sai, unboxing/narrowing không hợp lệ có thể gây `IllegalArgumentException`; chúng không phải bằng chứng rằng đang sửa được `final`.

### `VarHandle` có thay được kết luận không?

Không. Với một `VarHandle` trỏ tới `final field`, các *write access modes* như `set` không được hỗ trợ và sẽ ném `UnsupportedOperationException` khi gọi. Việc lấy handle hoặc đọc giá trị không tự cấp chế độ ghi cho `static final`. `MethodHandles.Lookup` có các quy tắc quyền truy cập riêng; không nên xem nó như cửa hậu cho phép bỏ qua bất biến của `final`.

### `Modifier.FINAL` không phải công tắc runtime

`Modifier.isFinal(field.getModifiers())` cho biết modifier. Việc tìm kiếm hoặc sửa dữ liệu nội bộ của `Field` để “gỡ bit final”, hay can thiệp bộ nhớ bằng API không được hỗ trợ, **không thuộc API ghi Reflection thông thường** và không bảo đảm tương thích các JDK. Các cách đó còn có thể xung đột với compiler optimization, class initialization và mô hình bộ nhớ. Tránh thiết kế hệ thống phụ thuộc vào chúng.

## 8. Thiết kế đúng khi thật sự cần thay đổi giá trị

Nếu giá trị phải thay đổi khi chương trình đang chạy, đừng đặt nó vào một field `static final` rồi dựa vào Reflection để sửa.

**Lựa chọn 1 — field có thể thay đổi:** Sử dụng field không `final`, giới hạn quyền truy cập và cập nhật bằng API do class cung cấp. Trong chương trình đa luồng, cân nhắc `volatile` hoặc cơ chế đồng bộ thích hợp, thay vì mặc định một setter bất kỳ sẽ bảo đảm visibility.

~~~java
final class RuntimeSettings {
    private static volatile int timeoutSeconds = 30;

    static int timeoutSeconds() {
        return timeoutSeconds;
    }

    static void updateTimeoutSeconds(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("timeout must be positive");
        }
        timeoutSeconds = value;
    }
}
~~~

Đây là **đoạn class để minh họa thiết kế**, không có `main` nên không tự tạo output. `volatile` hỗ trợ visibility và ordering đối với field đó; nó không thay thế mọi nhu cầu atomicity của logic nhiều bước.

**Lựa chọn 2 — final reference tới một vùng trạng thái có API cập nhật:** Có thể giữ reference cố định nhưng thay dữ liệu trong đối tượng được tham chiếu qua API thread-safe, chẳng hạn `AtomicReference<Configuration>`. Ở đây `static final` bảo vệ **identity của container**, còn `container.set(newConfig)` thay **trạng thái container** theo contract của nó. Dùng mô hình này chỉ khi thật sự cần trạng thái chia sẻ có thể cập nhật và hiểu tác động đồng thời.

~~~java
import java.util.concurrent.atomic.AtomicReference;

final class ConfigStore {
    static final AtomicReference<String> CURRENT =
            new AtomicReference<>("development");

    static void switchTo(String value) {
        CURRENT.set(value);
    }

    static String read() {
        return CURRENT.get();
    }
}
~~~

Đây cũng là class minh họa không có `main`. Mặc dù `CURRENT` là `static final`, không có chỗ nào ghi lại **tham chiếu field `CURRENT`**; mã chỉ gọi method cập nhật của object.

**Lựa chọn 3 — dependency injection hoặc cấu hình khi khởi tạo:** Nếu cấu hình đáng lẽ cố định suốt vòng đời object, truyền nó qua constructor và khởi tạo instance mới khi thay cấu hình. Giải pháp này làm rõ sở hữu và chu kỳ sống của dữ liệu, tránh Reflection sửa cấu trúc runtime.

## 9. Lỗi thường gặp và câu hỏi tự kiểm tra

1. **“`setAccessible(true)` thành công nghĩa là ghi được.”** Sai: khi field là `static final`, chỉ có thể mở quyền đọc; setter vẫn không có write access.
2. **“Lỗi do truyền `null` cho `Field.setInt(null, x)`.”** Sai: đối với static field, đối số instance bị bỏ qua.
3. **“Chỉ `static final int` mới bị khóa vì compile-time constant.”** Sai: `static final List<?>` cũng không được gán lại bằng Reflection; field có giá trị runtime cũng bị khóa.
4. **“`static final List` nghĩa là danh sách không thể thêm phần tử.”** Sai: `final` cố định reference; tính mutable của List quyết định khả năng thay nội dung.
5. **“Truy cập được `private static final` trong module khác nếu bật accessible.”** Chưa chắc: JPMS có thể từ chối cả deep reflection khi package chưa `opens`; và nếu mở được thì vẫn không được ghi.
6. **“`Field.set` báo `IllegalAccessException` nên phải dùng `--add-opens` là sẽ sửa được.”** `--add-opens` chỉ xử lý hàng rào module trong trường hợp phù hợp, không cấp quyền ghi vào non-modifiable final.
7. **“Các tùy chọn final-field mutation mới sẽ mở được `static final`.”** Sai: chúng liên quan ghi `final` instance trong điều kiện được hỗ trợ, không loại bỏ hạn chế với static final.

**Tự kiểm tra:**

- Thay `TAGS` trong ví dụ thành `List.of("A")`. Theo bạn lời gọi `Settings.tags().add("B")` sẽ ném ngoại lệ gì? *Gợi ý:* tính bất biến của object khác với modifier `final` của field.
- Nếu bỏ `final` khỏi `LIMIT`, giữ nguyên tên và câu lệnh `setInt(null, 20)`, kết quả sẽ khác thế nào?
- Tại sao field `static final int LIMIT = 10` có thêm rủi ro liên quan inlining nhưng field `static final List<String> TAGS` không phải là constant variable?
- Nếu `trySetAccessible()` trả `false`, nên kiểm tra quyền mở package hoặc module nào trước khi thử đọc? Tại sao kể cả sau khi mở package vẫn không thể ghi `static final`?

## Tài liệu tham khảo

- [Java SE 17 API — `Field.set(Object, Object)` và `Field.setInt(Object, int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 17 API — `AccessibleObject.setAccessible(boolean)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Java SE 17 API — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Java Language Specification §4.12.4 — final Variables / constant variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4)
- [JEP 500 — Prepare to Make Final Mean Final (JDK 26)](https://openjdk.org/jeps/500)
- [Java SE 26 Migration Guide — Preparing for Final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
