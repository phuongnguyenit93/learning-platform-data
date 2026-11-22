# Kiểm thử generic record pattern (Java 21+)

## 1. Kiểm thử điều gì?

**Generic record pattern** là record pattern áp dụng cho một kiểu `record` có tham số kiểu, ví dụ `Box<T>` hoặc `Pair<L, R>`. Khi record pattern khớp, Java phân rã các record component và tạo biến mẫu. Với generic record, kiểu của các biến này còn phụ thuộc vào **kiểu tĩnh của biểu thức đang được kiểm tra** và kiểu của component pattern.

~~~java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}

Pair<String, Integer> pair = new Pair<>("item", 3);
if (pair instanceof Pair(var name, var quantity)) {
    String upper = name.toUpperCase(); // name được suy ra là String
    int twice = quantity * 2;         // quantity được suy ra là Integer
}
~~~

Đây là **đoạn minh họa**, giả sử hai record được khai báo trong phạm vi phù hợp. Cú pháp record pattern được chuẩn hóa ở **Java 21**; không cần `--enable-preview` trên JDK 21+.

Một bộ kiểm thử tốt phải phân biệt hai việc:

1. **Kiểm tra ở thời điểm biên dịch**: Java có suy luận đúng kiểu từ generic record và chấp nhận/loại bỏ những cách dùng biến mẫu không an toàn không?
2. **Kiểm tra lúc chạy**: mẫu có khớp đúng kiểu record, đúng kiểu giá trị component, đúng cấu trúc lồng nhau và các trường hợp `null` không?

Không thể chỉ thấy một phép `instanceof` trả về `true` rồi kết luận rằng Java đã kiểm chứng được mọi tham số generic ở runtime. Do **type erasure** (xóa thông tin tham số kiểu), cần thiết kế riêng các ca kiểm thử giá trị component.

## 2. Mô hình dữ liệu và kỳ vọng kiểu

Dùng ba record sau làm dữ liệu mẫu:

~~~java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}
record Envelope<T>(String id, Box<T> payload) {}
~~~

Ba mẫu tiêu biểu:

~~~java
// Nguồn có kiểu tĩnh Pair<String, Integer>:
Pair<String, Integer> a = new Pair<>("item", 3);
if (a instanceof Pair(var text, var number)) {
    String label = text.toUpperCase();
    int doubled = number * 2;
}

// Nguồn có kiểu tĩnh Envelope<Integer>, record lồng nhau:
Envelope<Integer> b = new Envelope<>("unit", new Box<>(7));
if (b instanceof Envelope(var id, Box(var count))) {
    Integer value = count; // suy ra Integer qua hai tầng record
}

// Nguồn chỉ có kiểu tĩnh Object:
Object c = new Pair<>("tag", 4);
if (c instanceof Pair(String tag, Integer count)) {
    System.out.println(tag + ":" + count);
}
~~~

Ở hai trường hợp đầu, kiểu tĩnh của biểu thức cho phép Java suy ra tham số kiểu của record pattern và các biến `var` bên trong. Ở trường hợp thứ ba, ta **không thể giả định** rằng `Object` đang mang các tham số generic cụ thể; các component pattern `String tag` và `Integer count` được dùng để **kiểm tra từng giá trị thành phần thực tế**.

Ví dụ:

~~~java
Object unknown = new Box<>("hello");
if (unknown instanceof Box(var value)) {
    // value có kiểu tĩnh Object; cần kiểm tra thêm trước khi coi là String.
    if (value instanceof String text) {
        System.out.println(text.toUpperCase());
    }
}
~~~

Đừng diễn giải `var` là “kiểu thực tế được nhận diện tự động và luôn truy cập như String”. Với `unknown` có kiểu tĩnh `Object`, thông tin generic `Box<String>` của biểu thức khởi tạo không tự biến `value` thành biến có kiểu tĩnh `String` tại chỗ sử dụng.

## 3. Ma trận kiểm thử cần có

| Nhóm | Giá trị hoặc tình huống | Kỳ vọng |
| --- | --- | --- |
| Suy luận kiểu tĩnh | `Pair<String, Integer>` với `Pair(var, var)` | Biến thứ nhất dùng như `String`, biến thứ hai như `Integer`; biên dịch thành công. |
| Record generic lồng nhau | `Envelope<Integer>(..., Box<Integer>)` | Mẫu `Envelope(var, Box(var))` khớp và biến trong cùng được suy ra là `Integer`. |
| Kiểu component runtime phù hợp | `Object` chứa `Pair("tag", 4)` | `Pair(String, Integer)` khớp. |
| Thứ tự/kiểu component sai | `Object` chứa `Pair(4, "tag")` | `Pair(String, Integer)` không khớp. |
| Sai kiểu record | `Object` chứa `Box("tag")` | Mẫu `Pair(...)` không khớp. |
| Giá trị ngoài cùng `null` | `null instanceof Pair(...)` | Không khớp. |
| Record lồng nhau `null` | `Envelope("unit", null)` | Mẫu `Envelope(var, Box(...))` không khớp. |
| Component của record chứa `null` | `Box<String>(null)` | `Box(var value)` có thể khớp với `value == null`; `Box(String text)` không khớp. |
| Sai kiểu bên trong mẫu lồng | `Envelope("unit", Box("seven"))` | Mẫu con `Box(Integer n)` không khớp. |
| Guard của `switch` | `Integer` dương, bằng 0 và kiểu khác | Đi đúng `case`, kể cả nhánh dự phòng. |
| Tính nhất quán | Phân rã các `Pair` đã biết | Giá trị biến mẫu đúng bằng giá trị trả về từ accessor `left()`, `right()`. |

Ma trận này có cả **ca dương** (phải khớp), **ca âm** (phải bị từ chối), **biên `null`** và **kiểm tra hợp đồng kiểu**. Kiểm thử chỉ một `Pair("a", 1)` thành công chưa đủ để bảo vệ chương trình khỏi thay đổi kiểu dữ liệu hoặc thứ tự component.

## 4. Bộ kiểm thử Java hoàn chỉnh, không cần thư viện ngoài

Tạo tệp **`GenericRecordPatternTest.java`** với toàn bộ mã sau. Bộ kiểm thử dùng một hàm `check` luôn hoạt động, ném `AssertionError` khi kết quả sai. Cách này không phụ thuộc cờ `-ea` của lệnh `java`.

~~~java
public class GenericRecordPatternTest {
    record Box<T>(T value) {}
    record Pair<L, R>(L left, R right) {}
    record Envelope<T>(String id, Box<T> payload) {}

    private static int passed = 0;

    private static void check(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
        passed++;
        System.out.println("PASS " + name);
    }

    private static void typeInference() {
        Pair<String, Integer> pair = new Pair<>("item", 3);

        if (pair instanceof Pair(var item, var quantity)) {
            String upper = item.toUpperCase();
            int doubled = quantity * 2;
            check(upper.equals("ITEM") && doubled == 6,
                    "inferred types");
        } else {
            throw new AssertionError("typed pair pattern did not match");
        }

        Envelope<Integer> envelope =
                new Envelope<>("unit", new Box<>(7));

        if (envelope instanceof Envelope(var id, Box(var count))) {
            Integer typedCount = count;
            check(id.equals("unit") && typedCount == 7,
                    "nested inference");
        } else {
            throw new AssertionError("nested pattern did not match");
        }
    }

    private static void runtimeMatching() {
        Object correct = new Pair<>("tag", 4);
        check(correct instanceof Pair(String tag, Integer amount)
                        && tag.equals("tag") && amount == 4,
                "runtime component types");

        Object swapped = new Pair<>(4, "tag");
        check(!(swapped instanceof Pair(String tag, Integer amount)),
                "swapped components rejected");

        Object other = new Box<>("tag");
        check(!(other instanceof Pair(String tag, Integer amount)),
                "wrong record type rejected");

        Object nullTop = null;
        check(!(nullTop instanceof Pair(var first, var second)),
                "null input rejected");

        Object nullInner = new Envelope<Integer>("unit", null);
        check(!(nullInner instanceof Envelope(var id, Box(var value))),
                "null nested record rejected");

        Object nullValue = new Box<String>(null);
        check(nullValue instanceof Box(var value) && value == null,
                "null component accepted by var");
        check(!(nullValue instanceof Box(String text)),
                "null component rejected by type pattern");

        Object wrongInner = new Envelope<>(
                "unit", new Box<>("seven"));
        check(!(wrongInner instanceof Envelope(var id, Box(Integer n))),
                "wrong nested component rejected");
    }

    private static String classify(Object input) {
        return switch (input) {
            case Envelope(var id, Box(Integer n))
                    when n > 0 -> id + ":positive:" + n;
            case Envelope(var id, Box(Integer n)) ->
                    id + ":nonpositive:" + n;
            case Envelope(var id, Box(var rest)) ->
                    id + ":other";
            case null -> "null";
            default -> "unknown";
        };
    }

    private static void switchCases() {
        check(classify(new Envelope<>("e", new Box<>(7)))
                        .equals("e:positive:7"),
                "guard true");
        check(classify(new Envelope<>("e", new Box<>(0)))
                        .equals("e:nonpositive:0"),
                "guard false");
        check(classify(new Envelope<>("e", new Box<>("text")))
                        .equals("e:other"),
                "different nested type");
        check(classify(new Envelope<>(
                "e", new Box<>((Object) null))).equals("e:other"),
                "null nested value");
        check(classify(new Envelope<Integer>("e", null))
                        .equals("unknown"),
                "null nested record switch");
        check(classify(null).equals("null"),
                "null switch input");
    }

    private static void accessorConsistency() {
        for (int i = 0; i < 3; i++) {
            Pair<String, Integer> pair = new Pair<>("item-" + i, i);

            if (pair instanceof Pair(var name, var number)) {
                check(name.equals(pair.left())
                                && number.equals(pair.right()),
                        "accessors " + i);
            } else {
                throw new AssertionError("unexpected failure");
            }
        }
    }

    public static void main(String[] args) {
        typeInference();
        runtimeMatching();
        switchCases();
        accessorConsistency();
        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Biên dịch và chạy trên JDK 21 trở lên:

~~~bash
javac --release 21 GenericRecordPatternTest.java
java GenericRecordPatternTest
~~~

Kết quả khi toàn bộ kiểm thử đạt:

~~~text
PASS inferred types
PASS nested inference
PASS runtime component types
PASS swapped components rejected
PASS wrong record type rejected
PASS null input rejected
PASS null nested record rejected
PASS null component accepted by var
PASS null component rejected by type pattern
PASS wrong nested component rejected
PASS guard true
PASS guard false
PASS different nested type
PASS null nested value
PASS null nested record switch
PASS null switch input
PASS accessors 0
PASS accessors 1
PASS accessors 2
ALL PASSED: 19
~~~

Nếu một điều kiện sai, `check` ném `AssertionError` kèm tên ca kiểm thử; chương trình không in `ALL PASSED: 19`. Cơ chế này giúp kết quả thất bại hiển thị rõ và tiến trình Java kết thúc lỗi khi có assertion không được xử lý.

### Cách đọc kết quả

- **`inferred types`**: `item.toUpperCase()` và `quantity * 2` biên dịch được bởi các biến `var` mang kiểu suy ra từ `Pair<String, Integer>`.
- **`nested inference`**: từ `Envelope<Integer>` đi qua component `Box<T>`, mẫu lồng suy ra `count` là `Integer`.
- **`runtime component types`**: biểu thức có kiểu tĩnh `Object` vẫn có thể kiểm tra giá trị component bằng mẫu `String` và `Integer`.
- **`swapped components rejected`**: kiểu và vị trí từng component quan trọng; cùng có `String` và `Integer` nhưng đảo chỗ không khớp.
- **Các phép thử `null`**: phải phân biệt đối tượng ngoài cùng `null`, bản thân record lồng nhau `null`, và giá trị bên trong record bằng `null`.
- **`guard true/false`**: mẫu `Box(Integer n)` tạo biến `n` để dùng trong `when n > 0`; nếu guard sai, `switch` có thể chọn nhánh Integer kế tiếp.
- **`accessors 0..2`**: các component được phân rã đúng thứ tự và đúng giá trị như accessor của record, với ba bộ dữ liệu khác nhau.

## 5. Kiểm thử âm ở thời điểm biên dịch

Không nên chỉ có test runtime. Một số sai lầm generic record pattern phải được phát hiện bởi **trình biên dịch**. Các đoạn dưới đây **cố ý sai**, chỉ dùng làm ví dụ thử biên dịch riêng; đừng chèn chúng vào tệp kiểm thử chạy được ở mục 4.

### Sai lầm A: kiểm tra trực tiếp tham số generic không an toàn từ `Object`

~~~java
Object obj = new Pair<>("tag", 4);

// KHÔNG BIÊN DỊCH: Object không thể được kiểm tra an toàn là
// Pair<String, Integer> theo tham số generic ở runtime.
if (obj instanceof Pair<String, Integer>(var text, var count)) {
    System.out.println(text);
}
~~~

Do xóa kiểu (*type erasure*), dạng `instanceof Pair<String, Integer>(...)` này không an toàn khi đối tượng nguồn chỉ biết là `Object`. Thay vào đó, dùng component pattern có kiểu cụ thể:

~~~java
if (obj instanceof Pair(String text, Integer count)) {
    System.out.println(text + ":" + count);
}
~~~

Cách sau kiểm tra **giá trị từng component** thực sự khớp `String` và `Integer`. Nó không xác thực một cách tổng quát các tham số generic của đối tượng đã được tạo ra, đặc biệt với dữ liệu bị ép kiểu không an toàn ở nơi khác.

### Sai lầm B: cho rằng `var` trong nguồn `Object` tạo kiểu tĩnh `String`

~~~java
Object unknown = new Box<>("hello");

if (unknown instanceof Box(var value)) {
    // String text = value; // KHÔNG BIÊN DỊCH: value có kiểu Object
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
~~~

Phần chạy được của đoạn ví dụ có kiểm tra kiểu `String` bổ sung. Nếu bỏ comment ở dòng gán trực tiếp, đó là **ca biên dịch âm** cần bị từ chối.

Nên duy trì cả test biên dịch dương lẫn âm khi cập nhật phiên bản JDK hoặc khi refactor chữ ký record. Có thể xác minh bằng `javac --release 21` và kiểm tra **mã thoát khác 0** cho tệp ví dụ cố ý sai. Không sử dụng lỗi biên dịch của ví dụ âm làm kết quả thất bại cho bộ test dương độc lập ở mục 4.

## 6. Khi dùng `switch` với generic record pattern

Mẫu `Envelope(var id, Box(Integer n))` trong bộ test có ba tính chất cần kiểm thử riêng:

1. `id` lấy từ component `String id` của `Envelope<T>`; `n` lấy từ giá trị của `Box<T>` lồng bên trong, nếu giá trị đó khớp `Integer`.
2. Sau khi pattern khớp, `when n > 0` quyết định chọn nhánh số dương. Số `0` vẫn là một `Integer` hợp lệ, nhưng không qua guard; nhánh `Integer` kế tiếp nhận nó.
3. Mẫu `Envelope(var id, Box(var rest))` là nhánh tổng quát hơn, vì thế đặt **sau** các nhánh `Integer` cụ thể. Nó khớp với `Box<String>("text")` và `Box<Object>(null)`; ngược lại, `Envelope("e", null)` không khớp mẫu `Box(...)` và đi tới `default`.

Đặc biệt, `case null` ở ví dụ xử lý **chính đối tượng đem vào `switch` là `null`**. Nó không thay cho phép kiểm tra một record đang tồn tại nhưng chứa component `null`.

Khi thêm ca kiểm thử, nên chạy đủ giá trị số dương, bằng `0`, kiểu khác, `null` trong component, record lồng `null` và selector `null`. Chỉ kiểm thử nhánh `when` đúng sẽ bỏ sót lỗi thứ tự nhánh hoặc điều kiện phủ hết các trường hợp.

## 7. Đưa kiểm thử vào dự án dùng JUnit 5

Trong dự án đã cấu hình **JUnit Jupiter**, có thể chuyển hàm `check` sang các assertion của JUnit, đặt test trong `src/test/java` và dùng `@Test`. Ví dụ dưới đây là **đoạn minh họa**, giả sử `Pair` và `Envelope` đã sẵn trong phạm vi lớp test:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GenericPatternJUnitTest {
    record Pair<L, R>(L left, R right) {}

    @Test
    void typedComponentsMatch() {
        Object input = new Pair<>("tag", 4);
        assertTrue(input instanceof Pair(String text, Integer amount)
                && text.equals("tag") && amount == 4);
    }

    @Test
    void wrongComponentOrderDoesNotMatch() {
        Object input = new Pair<>(4, "tag");
        assertFalse(input instanceof Pair(String text, Integer amount));
    }

    @Test
    void nullSelectorDoesNotMatch() {
        Object input = null;
        assertFalse(input instanceof Pair(var left, var right));
    }
}
~~~

Mã JUnit cần dependency `org.junit.jupiter` và bộ chạy test JUnit 5 của dự án; **không** biên dịch chỉ với `javac` của JDK thuần nếu thiếu thư viện. Các test có dữ liệu gần giống nhau nên có thể gom thành kiểm thử tham số hóa (`@ParameterizedTest`), nhưng hãy giữ tên ca kiểm thử rõ ý nghĩa và có đầy đủ các đường đi âm.

Với dự án lớn, nên đặt các phép phân loại record vào một phương thức có đầu ra rõ ràng rồi kiểm thử **kết quả đầu ra**, bên cạnh một vài ca kiểm tra trực tiếp `instanceof`. Như vậy test bảo vệ hành vi của ứng dụng, thay vì chỉ lặp lại cú pháp Java.

## 8. Lỗi kiểm thử phổ biến và cách tránh

**Chỉ kiểm thử một trường hợp khớp thành công.** Nên có cả sai kiểu record, sai vị trí component, sai kiểu component trong record lồng và các ca `null`.

**Cho rằng `Pair<String, Integer>` được nhận diện nguyên vẹn ở runtime.** Generic type arguments không được lưu theo cách có thể kiểm tra tổng quát bằng `instanceof`. Đối với đầu vào kiểu `Object`, dùng component pattern cụ thể và test các kiểu giá trị thực tế.

**Nhầm `var` với kiểu động.** `var` suy luận từ kiểu tĩnh mà Java biết tại vị trí pattern. Test biên dịch nên kiểm tra cả trường hợp nguồn có kiểu generic đầy đủ và trường hợp nguồn chỉ có kiểu `Object`.

**Dùng `assert` nhưng quên bật assertion.** `assert` theo ngôn ngữ Java có thể không được thực thi nếu không chạy với `java -ea`. Bộ test ở mục 4 dùng `throw new AssertionError` để phát hiện lỗi nhất quán; JUnit cũng chủ động chạy các assertion riêng.

**Quên phân biệt các dạng `null`.** Một `Box<String>(null)` vẫn là đối tượng record và `Box(var value)` có thể khớp; nhưng `Box(String text)` không khớp component `null`. Một `Envelope` có `payload == null` lại không khớp `Envelope(var id, Box(...))`.

**Đặt mẫu tổng quát trước mẫu cụ thể trong `switch`.** Mẫu `Envelope(var, Box(var))` có thể khiến nhánh `Envelope(var, Box(Integer))` sau đó bị che khuất. Giữ thứ tự từ cụ thể đến tổng quát và kiểm thử cả guard đúng/sai.

**Không kiểm tra phiên bản Java.** `javac --release 21` giúp kiểm tra mã chỉ dùng tính năng phù hợp Java 21; ví dụ generic record pattern này không cần bật preview trong Java 21.

## 9. Checklist kiểm thử hồi quy

Khi sửa kiểu `record`, thêm component hoặc thay đổi kiểu generic:

1. Biên dịch lại bộ test với mục tiêu Java 21 hoặc phiên bản tối thiểu của dự án.
2. Chạy test dương để xác nhận suy luận kiểu từ `Pair<String, Integer>` và record generic lồng nhau còn đúng.
3. Chạy test âm runtime cho thứ tự component, kiểu giá trị không phù hợp và `null` ở từng tầng.
4. Kiểm tra các nhánh `switch`, đặc biệt thứ tự `case` và guard `when`.
5. Đối chiếu giá trị biến mẫu với accessor nhằm phát hiện lỗi phân rã sai vị trí.
6. Giữ ví dụ biên dịch âm **tách khỏi** bộ test chạy được; lỗi cố ý phải được chấm là *đúng kỳ vọng* khi trình biên dịch từ chối.

**Kết luận:** Kiểm thử generic record pattern cần kết hợp **suy luận kiểu tại compile time**, **kiểm tra cấu trúc và kiểu component tại runtime**, **xử lý `null`**, **nhánh `switch`** và **tính nhất quán với accessor**. Cách này kiểm tra đúng hợp đồng của pattern matching trên generic record, tránh ngộ nhận rằng type erasure cho phép xác thực mọi tham số generic lúc chạy.