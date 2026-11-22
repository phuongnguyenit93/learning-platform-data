# Giá trị trả về khi `Optional.orElseThrow()` có dữ liệu

**Chủ đề:** `Optional.orElseThrow` — Java 10 trở lên.

Khi một `Optional<T>` **có giá trị**, lời gọi `orElseThrow()` trả về **chính giá trị kiểu `T` được chứa bên trong**, không ném ngoại lệ, không trả về một `Optional<T>` khác, không tự thay bằng giá trị mặc định và không tạo bản sao của đối tượng. Đây là hành vi cốt lõi của overload **không tham số** được bổ sung ở **Java 10** và vẫn được dùng trong Java hiện đại.

Bài học đi từ quy tắc trả về, cách suy luận kiểu, ví dụ tham chiếu object, đến so sánh với overload nhận `Supplier`, xử lý pipeline `map/flatMap/filter` và những tình huống dễ nhầm với `orElse`, `orElseGet` hoặc `get`. Mọi chương trình độc lập bên dưới đều đã được kiểm tra theo nguồn Java 10 bằng `javac --release 10`.

## 1. Hợp đồng chính xác của `orElseThrow()`

Lớp `java.util.Optional<T>` mô tả sự hiện diện hoặc vắng mặt của một **giá trị khác `null`**. Với overload không tham số:

~~~java
public T orElseThrow()
~~~

Quy tắc là:

| Trạng thái `Optional<T>` | Kết quả của `orElseThrow()` |
| --- | --- |
| Có giá trị (*present*) | Trả về giá trị hiện có, kiểu tĩnh là `T` |
| Rỗng (*empty*) | Ném `java.util.NoSuchElementException` |

Hai dòng ngắn nhất:

~~~java
String name = Optional.of("Java").orElseThrow(); // nhận "Java"
String missing = Optional.<String>empty().orElseThrow(); // ném NoSuchElementException
~~~

Đây là **các dòng minh họa bên trong một phương thức**, giả sử đã import `java.util.Optional`. Dòng thứ hai **không** gán `null` cho biến `missing`: ngoại lệ xảy ra trước khi phép gán hoàn thành.

**Giá trị được trả về là `T`, không phải `Optional<T>`.** Vì thế:

~~~java
Optional<String> wrapped = Optional.of("Java");
String unwrapped = wrapped.orElseThrow(); // hợp lệ
// Optional<String> wrong = wrapped.orElseThrow(); // lỗi biên dịch
~~~

Giá trị không cần được chuyển từ một kiểu mơ hồ về `Object`. Generic `T` của `Optional<T>` cho trình biên dịch biết kiểu trả về: `Optional<String>` trả `String`, `Optional<Integer>` trả `Integer`, `Optional<List<String>>` trả `List<String>`.

`orElseThrow()` chỉ **lấy ra giá trị đã có**, không thực hiện phép chuyển đổi hay kiểm tra nghiệp vụ khác trên giá trị đó. Nếu muốn chuẩn hóa hoặc validate, dùng bước trước khi mở gói, như `map` và `filter`.

## 2. Giá trị trả về và suy luận kiểu khi viết `var`

Với Java 10+, `var` suy luận kiểu của **biến cục bộ** từ biểu thức khởi tạo. Vì `orElseThrow()` trả `T`, mã sau tương đương về kiểu tĩnh:

~~~java
Optional<String> label = Optional.of("Java");

String explicit = label.orElseThrow();
var inferred = label.orElseThrow(); // inferred có kiểu String
~~~

Có thể gọi phương thức của `String` ngay sau đó:

~~~java
int length = label.orElseThrow().length(); // length = 4
~~~

Khi kiểu `T` là một lớp khác, kết quả có kiểu khác:

~~~java
Integer boxed = Optional.of(42).orElseThrow(); // Integer
int count = Optional.of(42).orElseThrow();     // unboxing Integer -> int
~~~

Trong ví dụ `int count`, `orElseThrow()` trả về `Integer`; **autounboxing** chuyển thành `int` để gán. `orElseThrow()` không tự thay đổi generic type thành primitive.

Nếu phương thức có kiểu trả về `Optional<User>`, thì `optionalUser.orElseThrow()` cho một `User`. Nó **không** tự động gọi getter, chuyển thành chuỗi hoặc trả giá trị bên trong một field của `User`. Mọi biến đổi muốn có phải được khai báo tường minh.

## 3. Chương trình hoàn chỉnh 1 — Khi có dữ liệu, nhận lại đúng giá trị

Lưu thành tệp **`PresentOptionalDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class PresentOptionalDemo {
    static Optional<String> findLabel(int id) {
        return id == 7 ? Optional.of("Java") : Optional.empty();
    }

    public static void main(String[] args) {
        Optional<String> found = findLabel(7);
        String label = found.orElseThrow();
        System.out.println("label=" + label);
        System.out.println("length=" + found.orElseThrow().length());
        System.out.println("present=" + found.isPresent());

        var original = new ArrayList<>(List.of("alpha"));
        Optional<List<String>> wrapped = Optional.of(original);
        List<String> unwrapped = wrapped.orElseThrow();
        System.out.println("same-reference=" + (original == unwrapped));
        unwrapped.add("beta");
        System.out.println("original-list=" + original);

        int count = Optional.of(42).orElseThrow();
        System.out.println("count=" + count);
    }
}
~~~

Biên dịch và chạy bằng JDK hiện đại có hỗ trợ `--release 10`:

~~~bash
javac --release 10 PresentOptionalDemo.java
java PresentOptionalDemo
~~~

**Stdout chính xác:**

~~~text
label=Java
length=4
present=true
same-reference=true
original-list=[alpha, beta]
count=42
~~~

Các quan sát:

1. `findLabel(7)` trả `Optional.of("Java")` nên `orElseThrow()` trả `"Java"`.
2. `found.orElseThrow().length()` hoạt động vì giá trị trả về có kiểu `String`. Dòng `present=true` xác nhận dữ liệu hiện diện, nhưng không cần gọi `isPresent()` trước `orElseThrow()` để sử dụng khi đã chấp nhận quy tắc “thiếu thì ném”.
3. `wrapped` chứa reference đến `original`, một `ArrayList` có thể sửa. `unwrapped` là **cùng đối tượng danh sách**, thể hiện qua `same-reference=true`.
4. Khi gọi `unwrapped.add("beta")`, danh sách gốc cũng chứa `beta`. `Optional` không sao chép sâu hay tự biến object thành immutable.
5. `Optional.of(42).orElseThrow()` trả một `Integer`; phép gán sang `int` sử dụng autounboxing.

Điều cần phân biệt: **không nên so sánh identity của chính các instance `Optional` như một giao ước** (đây là một value-based class). Nhưng việc lấy ra giá trị tham chiếu bằng `orElseThrow()` là một thao tác thông thường; ví dụ so sánh `original == unwrapped` nhằm minh họa **giá trị được chứa là cùng reference**, không phải identity của wrapper `Optional`.

## 4. Khi có dữ liệu, overload nhận `Supplier` cũng trả đúng giá trị

Ngoài overload không tham số, `Optional` còn có:

~~~java
public <X extends Throwable> T orElseThrow(
        Supplier<? extends X> exceptionSupplier) throws X
~~~

Overload này tồn tại từ trước Java 10 và cho phép tạo **ngoại lệ tùy chọn khi rỗng**. Nhưng ở **nhánh có dữ liệu**, nó vẫn trả **giá trị `T` đang có**.

~~~java
Optional<String> result = Optional.of("ready");
String text = result.orElseThrow(
        () -> new IllegalStateException("missing")); // text = "ready"
~~~

Đây là đoạn minh họa trong method. Quan trọng hơn: khi `result` có dữ liệu, **`exceptionSupplier` không được gọi**. Lý do là không cần tạo ngoại lệ để ném.

Sự phân biệt này quan trọng nếu Supplier tạo một exception có thông báo/stack trace tốn kém hoặc có side effect. Ta truyền một Supplier để đối tượng exception chỉ được tạo khi Optional rỗng:

~~~java
// ĐÚNG: lambda chỉ tạo exception khi Optional rỗng
result.orElseThrow(() -> new IllegalStateException("missing"));
~~~

Dòng trên **là cách dùng lazy đúng**: lambda chỉ được thực thi khi `Optional` rỗng. Bản thân việc tạo **biểu thức lambda** không tạo đối tượng `IllegalStateException` bên trong nó.

Khi cần code dễ đọc, thường dùng constructor reference:

~~~java
String text = result.orElseThrow(IllegalStateException::new);
~~~

`IllegalStateException::new` chỉ được gọi khi thiếu dữ liệu. Trong cả hai hình thức, khi `result` chứa `"ready"` thì vẫn lấy ra `"ready"` và không ném lỗi.

### Chương trình hoàn chỉnh 2 — Kiểm chứng Supplier không chạy khi present

Lưu **`ExceptionSupplierDemo.java`**:

~~~java
import java.util.NoSuchElementException;
import java.util.Optional;

public class ExceptionSupplierDemo {
    private static int calls;

    static IllegalStateException createError() {
        calls++;
        return new IllegalStateException("not-found");
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("ready");

        System.out.println("no-arg-present=" + present.orElseThrow());
        System.out.println("supplier-present=" +
                present.orElseThrow(ExceptionSupplierDemo::createError));
        System.out.println("calls-after-present=" + calls);

        try {
            Optional.<String>empty()
                    .orElseThrow(ExceptionSupplierDemo::createError);
        } catch (IllegalStateException expected) {
            System.out.println("supplier-empty=" + expected.getMessage());
        }

        System.out.println("calls-after-empty=" + calls);

        try {
            Optional.<String>empty().orElseThrow();
        } catch (NoSuchElementException expected) {
            System.out.println("no-arg-empty=" +
                    expected.getClass().getSimpleName());
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 10 ExceptionSupplierDemo.java
java ExceptionSupplierDemo
~~~

**Stdout chính xác:**

~~~text
no-arg-present=ready
supplier-present=ready
calls-after-present=0
supplier-empty=not-found
calls-after-empty=1
no-arg-empty=NoSuchElementException
~~~

Ý nghĩa:

- Cả hai overload đều trả `"ready"` khi present.
- `createError()` không chạy khi present; vì vậy bộ đếm vẫn là 0.
- Khi empty, overload có Supplier gọi `createError()` đúng một lần rồi ném `IllegalStateException("not-found")`.
- Khi empty, overload **không tham số** ném `NoSuchElementException`.
- Hai overload **khác nhau ở nhánh rỗng**, không khác nhau ở giá trị trả về lúc có dữ liệu.

Trong code nghiệp vụ, nên chọn overload nhận Supplier khi muốn giải thích lỗi bằng một exception domain phù hợp, như `new IllegalArgumentException("Unknown id")` hoặc `new IllegalStateException("Missing configuration")`. Nếu chỉ muốn quy tắc “phải có kết quả” và không cần thông báo riêng, overload không tham số thường ngắn gọn hơn.

## 5. `orElseThrow()` luôn lấy giá trị ở trạng thái cuối của pipeline

Điểm cần nhớ: `orElseThrow()` chỉ đọc **giá trị của Optional đang nhận lời gọi**, tức là kết quả **sau các bước `map`, `flatMap` hoặc `filter`**. Nó không tự lấy lại giá trị gốc nếu pipeline đã biến đổi hoặc làm rỗng dữ liệu.

Ví dụ:

~~~java
String normalized = Optional.of("  java  ")
        .map(String::trim)
        .map(String::toUpperCase)
        .orElseThrow();
~~~

Ở đây giá trị ban đầu là `"  java  "`, nhưng kết quả được trả ra là **`"JAVA"`** vì đã được biến đổi trước khi mở gói. Chỉ khi Optional cuối cùng có giá trị thì `orElseThrow()` mới trả ra.

- `map` áp dụng phép biến đổi khi present, và tạo `Optional` mang giá trị mới. Nếu mapper trả `null` thì `Optional.map` cho kết quả **empty**.
- `filter` giữ dữ liệu nếu predicate đúng; nếu sai, nó trả `Optional.empty()`. Do đó một Optional ban đầu có dữ liệu vẫn có thể trở thành rỗng.
- `flatMap` dùng khi mapper **đã trả một Optional**, tránh tạo `Optional<Optional<T>>`; sau đó `orElseThrow()` mở gói kết quả.
- Khi Optional đang empty, các bước biến đổi bình thường không tạo ra giá trị mới; `orElseThrow()` sẽ ném trừ khi pipeline có bước fallback phù hợp trước đó.

### Chương trình hoàn chỉnh 3 — Trả giá trị đã biến đổi

Lưu **`OptionalPipelineDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;

public class OptionalPipelineDemo {
    static Optional<String> lookupAlias(String id) {
        return "7".equals(id) ? Optional.of("member") : Optional.empty();
    }

    public static void main(String[] args) {
        Map<String, String> labels = new HashMap<>();
        labels.put("7", "  alice  ");

        String normalized = Optional.ofNullable(labels.get("7"))
                .map(String::trim)
                .filter(text -> !text.isEmpty())
                .map(text -> text.toUpperCase(Locale.ROOT))
                .orElseThrow();
        System.out.println("normalized=" + normalized);

        String alias = Optional.of("7")
                .flatMap(OptionalPipelineDemo::lookupAlias)
                .orElseThrow();
        System.out.println("alias=" + alias);

        var missing = Optional.ofNullable(labels.get("404"));
        System.out.println("missing-present=" + missing.isPresent());
        System.out.println("missing-fallback=" + missing.orElse("guest"));

        try {
            Optional.of(" ")
                    .map(String::trim)
                    .filter(text -> !text.isEmpty())
                    .orElseThrow();
        } catch (NoSuchElementException expected) {
            System.out.println("blank=" + expected.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 OptionalPipelineDemo.java
java OptionalPipelineDemo
~~~

**Stdout chính xác:**

~~~text
normalized=ALICE
alias=member
missing-present=false
missing-fallback=guest
blank=NoSuchElementException
~~~

Giải thích:

1. `Map.get("7")` trả một chuỗi có khoảng trắng. `Optional.ofNullable(...)` tạo Optional có dữ liệu; `trim`, `filter` và `toUpperCase` chuẩn hóa thành `"ALICE"`. `orElseThrow()` trả **giá trị mới đã chuẩn hóa**.
2. `flatMap(OptionalPipelineDemo::lookupAlias)` biến `Optional<String>` ID thành `Optional<String>` alias. Vì có dữ liệu, `orElseThrow()` trả `"member"`.
3. Không có khóa `"404"` nên `Map.get` trả null; `Optional.ofNullable` biến nó thành empty. `isPresent()` là false, còn `orElse("guest")` cho giá trị mặc định.
4. Chuỗi chỉ gồm khoảng trắng trở thành `""`, bị `filter` loại. Khi tới `orElseThrow()`, Optional đã empty nên ném `NoSuchElementException`.

**Hệ quả cho thực tế:** “Ban đầu có dữ liệu” chưa đủ để đảm bảo cuối pipeline còn dữ liệu. Nếu `filter` là bước validation bắt buộc, việc ném exception ở cuối thường là một cách biểu thị “không thỏa điều kiện”.

## 6. So sánh các phương thức kết thúc của `Optional`

| Phương thức | Khi present | Khi empty | Điểm cần chú ý |
| --- | --- | --- | --- |
| `orElseThrow()` (Java 10+) | Trả giá trị `T` | Ném `NoSuchElementException` | Ý định “bắt buộc có” rõ ràng |
| `orElseThrow(exceptionSupplier)` | Trả giá trị `T`, **không gọi supplier** | Gọi Supplier và ném exception được tạo | Dùng khi cần thông báo/loại exception riêng |
| `get()` | Trả giá trị `T` | Ném `NoSuchElementException` | Vẫn tồn tại, nhưng Javadoc khuyên ưu tiên `orElseThrow()` vì rõ nghĩa |
| `orElse(defaultValue)` | Trả giá trị `T` | Trả `defaultValue` | Biểu thức đối số được **đánh giá trước lời gọi**, dù present |
| `orElseGet(supplier)` | Trả giá trị `T`, không gọi supplier | Gọi Supplier để lấy fallback | Dùng khi tạo fallback tốn kém hoặc cần lazy |
| `ifPresent(consumer)` | Gọi consumer với giá trị | Không làm gì | Trả `void`, không dùng để gán kết quả `T` |
| `ifPresentOrElse(action, emptyAction)` (Java 9+) | Gọi action với giá trị | Gọi emptyAction | Trả `void`, phù hợp xử lý hai nhánh bằng hành động |
| `or(supplier)` (Java 9+) | Trả một `Optional<T>` có giá trị | Lấy một `Optional<T>` từ supplier | **Không** mở gói thành `T` |

Mẫu dùng khi **bắt buộc phải có dữ liệu**:

~~~java
User user = findUser(id).orElseThrow(
        () -> new IllegalArgumentException("Unknown user id"));
~~~

Đây là **đoạn minh họa trong ứng dụng**, giả sử `findUser` trả `Optional<User>`, `id` và `User` có sẵn. Khi tìm thấy người dùng, lời gọi trả chính đối tượng `User` từ Optional; không có exception nào được tạo qua lambda. Khi không tìm thấy, ném lỗi có ngữ cảnh.

Mẫu dùng khi **vắng dữ liệu là bình thường**:

~~~java
String displayName = optionalName.orElse("Guest");
~~~

Đây là đoạn trong method, giả sử `optionalName` có kiểu `Optional<String>`. Nếu có tên, `displayName` bằng tên thật; nếu không, nhận `"Guest"` thay vì exception.

Không chọn `orElseThrow()` cho mọi Optional: đôi khi trạng thái empty là hợp lệ và nên xử lý bằng fallback, `ifPresent` hoặc truyền tiếp `Optional` sang tầng khác.

## 7. `orElseThrow` không gọi Supplier khi present; `orElse` thì khác

Một khác biệt quan trọng khi viết chương trình là **đánh giá đối số**:

~~~java
Optional<String> existing = Optional.of("actual");

String a = existing.orElse(expensiveFallback());
String b = existing.orElseGet(() -> expensiveFallback());
String c = existing.orElseThrow(() -> new IllegalStateException());
~~~

Đây là **đoạn minh họa**, `expensiveFallback()` là hàm giả định của ứng dụng. Với `existing` có dữ liệu:

- Cả `a`, `b` và `c` đều là `"actual"`.
- Nhưng **`expensiveFallback()` trong `orElse(expensiveFallback())` vẫn được gọi**, vì Java tính biểu thức đối số trước khi gọi `orElse`.
- `orElseGet` chỉ gọi Supplier khi empty; `orElseThrow(exceptionSupplier)` cũng chỉ gọi Supplier khi empty.
- `orElseThrow()` không có đối số, nên cũng không có fallback hay exception supplier để tính.

### Chương trình hoàn chỉnh 4 — Kiểm chứng đánh giá fallback

Lưu **`FallbackEvaluationDemo.java`**:

~~~java
import java.util.Optional;

public class FallbackEvaluationDemo {
    private static int fallbackCalls;

    static String loadFallback() {
        fallbackCalls++;
        return "default";
    }

    public static void main(String[] args) {
        Optional<String> present = Optional.of("actual");

        System.out.println("orElse=" + present.orElse(loadFallback()));
        System.out.println("calls-after-orElse=" + fallbackCalls);

        System.out.println("orElseGet=" + present.orElseGet(
                FallbackEvaluationDemo::loadFallback));
        System.out.println("calls-after-orElseGet=" + fallbackCalls);

        System.out.println("orElseThrow=" + present.orElseThrow());
        System.out.println("calls-after-orElseThrow=" + fallbackCalls);

        System.out.println("empty-orElseGet=" + Optional.<String>empty()
                .orElseGet(FallbackEvaluationDemo::loadFallback));
        System.out.println("calls-after-empty=" + fallbackCalls);
    }
}
~~~

Chạy:

~~~bash
javac --release 10 FallbackEvaluationDemo.java
java FallbackEvaluationDemo
~~~

Stdout:

~~~text
orElse=actual
calls-after-orElse=1
orElseGet=actual
calls-after-orElseGet=1
orElseThrow=actual
calls-after-orElseThrow=1
empty-orElseGet=default
calls-after-empty=2
~~~

Kết quả chỉ ra `orElse` đã gọi `loadFallback()` **dù Optional có dữ liệu**, trong khi `orElseGet` và `orElseThrow` không gọi fallback trong trường hợp đó. `orElseThrow()` đơn giản trả giá trị sẵn có, không tính thêm gì liên quan đến nhánh rỗng.

**Lưu ý:** Không cố dùng việc tạo exception hoặc fallback có side effect như một phần luồng nghiệp vụ; ví dụ đếm chỉ để quan sát quy tắc đánh giá.

## 8. Điều gì diễn ra khi thiếu dữ liệu?

Đề bài tập trung vào **nhánh present**, nhưng hiểu nhánh empty giúp không suy luận sai rằng `orElseThrow()` luôn trả một giá trị.

Các cách tạo Optional:

~~~java
Optional<String> a = Optional.of("hello");         // có dữ liệu
Optional<String> b = Optional.ofNullable("hello"); // có dữ liệu
Optional<String> c = Optional.ofNullable(null);    // empty
Optional<String> d = Optional.empty();             // empty
~~~

Những dòng này là minh họa trong method với import `Optional`.

- `Optional.of(value)` đòi hỏi value khác null; `Optional.of(null)` ném `NullPointerException` **ngay khi tạo**, không đợi đến `orElseThrow()`.
- `Optional.ofNullable(value)` tạo Optional có dữ liệu nếu value khác null, hoặc empty nếu null.
- `Optional.empty()` luôn biểu diễn vắng mặt.
- `Optional<T>` không biểu diễn trạng thái “present nhưng chứa `null`”; khi present, giá trị là non-null.
- `orElseThrow()` từ Optional empty ném `NoSuchElementException`; nó không trả null, chuỗi rỗng hay một `Optional.empty()` khác.

### Đừng suy ra trạng thái sau lời gọi từ source ban đầu

~~~java
var value = Optional.of("ok")
        .filter(s -> s.length() > 10)
        .orElseThrow(); // ném NoSuchElementException
~~~

Dù `Optional.of("ok")` ban đầu có dữ liệu, `filter` trả empty do điều kiện false. Vì vậy lời gọi cuối vẫn ném exception.

Nếu cần nêu lỗi domain thay vì `NoSuchElementException` mặc định, dùng overload có Supplier:

~~~java
var value = Optional.of("ok")
        .filter(s -> s.length() > 10)
        .orElseThrow(() -> new IllegalArgumentException("Too short"));
~~~

Đây là các đoạn trong method. Cả hai đều không thể trả về giá trị ở nhánh empty; overload thứ hai chỉ thay loại/thông điệp ngoại lệ.

## 9. Cách viết API sử dụng `orElseThrow` rõ ràng

### Khi kết quả phải tồn tại theo hợp đồng

~~~java
static String requiredSetting(Map<String, String> settings, String key) {
    return Optional.ofNullable(settings.get(key))
            .orElseThrow(() -> new IllegalStateException(
                    "Missing setting: " + key));
}
~~~

Đây là **khai báo một phương thức**; cần import `Optional` và `Map`. Khi có giá trị, phương thức trả đúng `String`. Khi không có, thông điệp lỗi có khóa giúp chẩn đoán.

Không cần viết:

~~~java
// Dài hơn, dễ tạo nhánh lặp:
if (maybeValue.isPresent()) {
    return maybeValue.get();
}
throw new NoSuchElementException();
~~~

Đây là đoạn minh họa; `maybeValue` giả sử có kiểu `Optional<T>` và hàm chứa nó trả `T`. Nếu ý nghĩa chỉ là “có thì trả, không thì ném”, `return maybeValue.orElseThrow();` diễn đạt trực tiếp hơn. `get()` không bị loại bỏ khỏi Java, nhưng tài liệu API hiện hành khuyên dùng `orElseThrow()` cho ý nghĩa rõ ràng này.

### Khi muốn tiếp tục làm việc với Optional

Nếu method không muốn áp đặt yêu cầu phải có dữ liệu, giữ nguyên `Optional<T>`:

~~~java
Optional<String> maybe = findLabel(7);
maybe.ifPresent(System.out::println);
~~~

Đây là đoạn minh họa nếu `findLabel` có sẵn như ví dụ ở phần 3. Nếu muốn fallback trong tương lai, để caller quyết định sẽ linh hoạt hơn việc ném từ tầng hạ tầng khi empty vẫn là trạng thái bình thường.

### Khi cần biến đổi trước khi mở gói

~~~java
String result = findLabel(7)
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .orElseThrow();
~~~

Lời gọi trả **giá trị cuối cùng đã qua kiểm tra**, không nhất thiết giống từng ký tự của giá trị ban đầu. Đây là hướng sử dụng phù hợp khi có pipeline xử lý và mỗi bước thể hiện một điều kiện rõ ràng.

## 10. Lỗi thường gặp

| Ngộ nhận / lỗi | Thực tế | Cách tránh |
| --- | --- | --- |
| “`orElseThrow()` luôn ném exception vì tên có `Throw`.” | Khi present, nó **trả đúng giá trị `T`**, không ném | Đọc điều kiện present/empty của API |
| “Kết quả của `orElseThrow()` là `Optional<T>`.” | Kết quả là `T` | Gán cho kiểu `T` hoặc dùng `var` để suy luận |
| “`orElseThrow()` lấy ra một bản sao.” | Nó trả reference đến value object đang chứa | Dùng defensive copy riêng nếu object mutable |
| “Có dữ liệu ban đầu thì sau `filter` chắc vẫn có.” | `filter` có thể tạo Optional empty | Xét trạng thái cuối pipeline trước khi mở gói |
| “`map` trả null thì `orElseThrow()` trả null.” | `Optional.map` chuyển kết quả null thành empty | Tránh mapper null hoặc xử lý empty |
| “Ở nhánh present, `exceptionSupplier` vẫn chạy để tạo lỗi dự phòng.” | Supplier không chạy khi có dữ liệu | Dùng lazy Supplier, không tự tạo exception trước |
| “`orElse(expensive())` chỉ chạy expensive khi empty.” | Biểu thức đối số được tính trước lời gọi | Dùng `orElseGet` khi cần fallback lazy |
| “`Optional.of(null).orElseThrow()` sẽ ném `NoSuchElementException`.” | `Optional.of(null)` ném `NullPointerException` ngay khi tạo | Dùng `ofNullable` khi đầu vào có thể null |
| “`get()` đã bị xóa khỏi Java.” | `get()` vẫn tồn tại, nhưng tài liệu khuyên `orElseThrow()` khi muốn ý nghĩa rõ | Ưu tiên `orElseThrow()` khi rỗng phải ném |
| “`Optional.isEmpty()` chạy ở Java 10.” | `isEmpty()` được thêm ở Java 11 | Với mã `--release 10` dùng `isPresent()` hoặc cách xử lý Optional trực tiếp |

**Một điểm đặc biệt về tham chiếu mutable:** `Optional.of(mutableObject).orElseThrow()` trả object gốc. Nếu caller sửa object đó, trạng thái được quan sát từ các reference khác cũng có thể đổi. `Optional` mô tả có/không có dữ liệu, **không phải cơ chế bảo vệ tính bất biến hoặc an toàn luồng**.

## 11. Checklist kiểm tra code

Khi review một lời gọi `optional.orElseThrow()`, hãy tự hỏi:

1. **Optional có thể empty không?** Nếu đó là trạng thái thường gặp, một exception mặc định có phù hợp không?
2. **Kiểu generic `T` là gì?** Kết quả trả `T`, không phải Optional hay một kiểu tự suy đoán khác.
3. **Pipeline có `map`/`filter`/`flatMap` không?** Các bước này có thể biến đổi hoặc làm rỗng kết quả.
4. **Giá trị là immutable hay mutable?** Nếu mutable, code nhận kết quả có đang vô tình sửa state dùng chung không?
5. **Có cần loại exception riêng?** Nếu cần, dùng overload `orElseThrow(exceptionSupplier)`.
6. **Exception supplier hoặc fallback có công việc tốn kém không?** Supplier của `orElseThrow` không chạy khi present; `orElse(expensiveFallback())` thì đối số vẫn được tính.
7. **Dữ liệu nguồn có thể là null?** `Optional.ofNullable` phù hợp hơn `Optional.of` nếu null là trạng thái đầu vào hợp lệ.
8. **Mức Java dự án là bao nhiêu?** Overload không tham số có từ Java 10; `isEmpty` có từ Java 11, nên không đưa vào mã Java 10.

Không cần gọi `isPresent()` trước `orElseThrow()` chỉ để “làm an toàn hơn” nếu đã xác định thiếu dữ liệu là lỗi và muốn ném. Nếu thiếu dữ liệu có thể xảy ra bình thường, hãy dùng phương án xử lý empty như `orElse`, `orElseGet` hoặc giữ `Optional`.

## 12. Câu hỏi tự kiểm tra

1. `Optional.of("Java").orElseThrow()` trả kiểu gì và giá trị gì?
2. Với `Optional<Integer> n = Optional.of(42);`, biểu thức `n.orElseThrow()` trả `Optional<Integer>`, `Integer` hay `int`?
3. Khi `Optional` có dữ liệu, overload `orElseThrow(() -> new IllegalStateException())` có gọi lambda không?
4. Với `Optional.empty().orElseThrow()`, ngoại lệ nào được ném?
5. `Optional.ofNullable(null).orElseThrow()` khác `Optional.of(null).orElseThrow()` ở **thời điểm và loại ngoại lệ** như thế nào?
6. `Optional.of("  a  ").map(String::trim).orElseThrow()` trả chuỗi nào?
7. `Optional.of("a").filter(s -> s.length() > 3).orElseThrow()` có trả `"a"` không?
8. Nếu `Optional<List<String>>` chứa một `ArrayList`, `orElseThrow()` có tự tạo một ArrayList mới không?
9. Khi Optional present, vì sao `orElse(expensiveFallback())` có thể vẫn tốn công, nhưng `orElseGet(() -> expensiveFallback())` thì không?
10. `get()` có bị deprecated/xóa ở Java hiện nay không, và tài liệu khuyến nghị gì?

**Đáp án:** (1) trả `String` có giá trị `"Java"`; (2) trả `Integer`, có thể được unbox khi gán cho `int`; (3) không, supplier chỉ chạy khi empty; (4) `NoSuchElementException`; (5) `ofNullable(null)` tạo Optional empty rồi `orElseThrow` ném `NoSuchElementException`, còn `of(null)` ném `NullPointerException` ngay khi tạo; (6) `"a"`; (7) không, `filter` trả empty nên ném; (8) không, giá trị là cùng object tham chiếu; (9) Java đánh giá đối số `orElse` trước lời gọi, còn `orElseGet` gọi supplier theo điều kiện; (10) `get()` vẫn tồn tại, Javadoc khuyên ưu tiên `orElseThrow()` để biểu đạt rõ ý định.

## 13. Tài liệu Java chính thức, còn áp dụng hiện nay

- **Oracle Javadoc — `Optional<T>` (Java SE 26):** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Optional.html
- **Oracle Javadoc — `Optional<T>` (Java SE 10, có `orElseThrow()` từ Java 10):** https://docs.oracle.com/javase/10/docs/api/java/util/Optional.html
- **Oracle Javadoc — `NoSuchElementException`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/NoSuchElementException.html
- **Oracle Javadoc — `Supplier<T>`:** https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/function/Supplier.html
- **JEP 286 — Local-Variable Type Inference (Java 10, liên quan ví dụ `var`):** https://openjdk.org/jeps/286

**Kết luận:** Khi `Optional<T>` **có dữ liệu**, `orElseThrow()` trả **giá trị `T` đúng như hiện diện trong Optional**; nó không ném, không tạo bản sao và không tự dùng fallback. Overload có `Supplier` cũng trả cùng giá trị mà **không gọi Supplier** khi present. Chỉ khi Optional **rỗng**, lời gọi mới đi vào nhánh ngoại lệ — `NoSuchElementException` cho overload không tham số, hoặc ngoại lệ do Supplier tạo trong overload có tham số.