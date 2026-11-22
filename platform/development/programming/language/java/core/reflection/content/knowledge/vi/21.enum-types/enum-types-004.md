# `Enum.valueOf()` với `Class` của enum

`Enum.valueOf()` chuyển một **tên khai báo của hằng** thành hằng thuộc **một kiểu enum cụ thể**. Tham số `Class` cho biết cần tra cứu trong enum nào. Đây là công cụ hữu ích khi viết bộ đọc cấu hình, bộ chuyển đổi dữ liệu hoặc mã hạ tầng dùng chung cho nhiều enum.

Ví dụ, chuỗi `"FAST"` chưa đủ để xác định một đối tượng: nhiều enum có thể cùng khai báo tên đó. Cặp `RunMode.class` và `"FAST"` mới xác định yêu cầu tìm `RunMode.FAST`. Khi việc chọn enum diễn ra lúc chạy, `Class` chính là thông tin nối giữa tên dạng chuỗi và kiểu Java cần xử lý.

Bài này phân biệt hai tình huống: đã có `Class<E>` với kiểu enum cụ thể, và chỉ có `Class<?>` lấy được từ cơ chế khám phá kiểu.

## 1. Chữ ký và ý nghĩa của tham số kiểu

Chữ ký API:

```java
public static <T extends Enum<T>> T valueOf(
        Class<T> enumClass, String name)
```

Đây là chữ ký để đọc, không phải phương thức bạn cần tự cài đặt. Ràng buộc `<T extends Enum<T>>` gắn kiểu trả về với chính kiểu enum mà `enumClass` đại diện.

Với `RunMode` đã được khai báo, lời gọi có thể viết như sau:

```java
RunMode mode = Enum.valueOf(RunMode.class, "FAST");
```

`RunMode.class` có kiểu `Class<RunMode>`, nên kết quả được kiểm tra kiểu là `RunMode`. Không cần ép từ `Object` về enum sau lời gọi.

Lời gọi tìm **hằng đã tồn tại**, không tạo một hằng mới. Trong thí nghiệm bên dưới, kết quả so sánh `mode == RunMode.FAST` là `true`.

Theo [hợp đồng `Enum.valueOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)), tên phải khớp chính xác với tên hằng được khai báo. Không tìm thấy thì ném `IllegalArgumentException`; tham số lớp hoặc tên là `null` thì ném `NullPointerException`.

### Khác gì `RunMode.valueOf("FAST")`?

Mỗi enum có phương thức tĩnh `valueOf(String)` được khai báo ngầm. Vì vậy, khi đã biết enum, `RunMode.valueOf("FAST")` thường dễ đọc hơn. Dạng `Enum.valueOf(enumType, name)` hữu ích cho hàm tổng quát nhận `Class<E>`. Quy tắc khai báo phương thức này được mô tả trong [JLS về thành viên enum](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9.3).

Cả hai dạng đều tra cứu tên hằng; đổi cách gọi không biến nó thành bộ phân tích nhãn hiển thị hay mã nghiệp vụ.

## 2. Tên khai báo, nhãn hiển thị và mã nghiệp vụ

Giả sử hằng `FAST` có nhãn `Fast execution` và mã `fast-code`. Ba chuỗi này phục vụ những mục đích khác nhau:

| Giá trị | Vai trò trong thí nghiệm | `Enum.valueOf(RunMode.class, ...)` |
| --- | --- | --- |
| `"FAST"` | Tên khai báo của hằng | Tìm thấy `RunMode.FAST` |
| `"Fast execution"` | Kết quả `toString()` dùng làm nhãn | Không phải tên cần tra cứu |
| `"fast-code"` | Mã nghiệp vụ do ứng dụng định nghĩa | Không tự được nhận diện |
| `"1"` | Chuỗi biểu diễn một số | Không được hiểu thành `ordinal()` |

`valueOf` không tự cắt khoảng trắng, đổi hoa thường, đọc thuộc tính `code`, gọi `toString()` để so sánh hay suy ra số thứ tự. Ví dụ bên dưới kiểm chứng từng trường hợp bằng các lời gọi độc lập.

## 3. Ví dụ Java 17+ đầy đủ

Chương trình có ba hàm phục vụ ba hợp đồng rõ ràng:

- `parseTyped`: tra cứu chính xác khi đã có `Class<E>`.
- `parseNormalized`: chính sách riêng, chủ động bỏ khoảng trắng đầu cuối và đổi chữ hoa.
- `parseRuntime`: nhận `Class<?>`, xác minh là khai báo enum rồi tra cứu và trả `Enum<?>`.

Lưu toàn bộ vào **`EnumValueOfDemo.java`**:

```java
import java.util.Locale;
import java.util.Objects;

public class EnumValueOfDemo {
    enum RunMode {
        SAFE("safe-code", "Safe execution"),
        FAST("fast-code", "Fast execution"),
        TURBO("turbo-code", "Turbo execution") {
            @Override
            public String toString() {
                return "Turbo custom label";
            }
        };

        private final String code;
        private final String label;

        RunMode(String code, String label) {
            this.code = code;
            this.label = label;
        }

        public String code() {
            return code;
        }

        @Override
        public String toString() {
            return label;
        }
    }

    public static <E extends Enum<E>> E parseTyped(
            Class<E> enumType, String name) {
        return Enum.valueOf(enumType, name);
    }

    public static <E extends Enum<E>> E parseNormalized(
            Class<E> enumType, String text) {
        Objects.requireNonNull(text, "text");
        String normalized = text.strip().toUpperCase(Locale.ROOT);
        return Enum.valueOf(enumType, normalized);
    }

    public static Enum<?> parseRuntime(Class<?> type, String name) {
        Objects.requireNonNull(type, "type");
        Objects.requireNonNull(name, "name");
        if (!type.isEnum()) {
            throw new IllegalArgumentException(
                    "Expected an enum declaration: " + type.getTypeName());
        }
        return parseCheckedClass(type, name);
    }

    @SuppressWarnings("unchecked")
    private static <E extends Enum<E>> E parseCheckedClass(
            Class<?> checkedType, String name) {
        Class<E> enumType = (Class<E>) checkedType;
        return Enum.valueOf(enumType, name);
    }

    private static void attempt(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + " -> success");
        } catch (RuntimeException ex) {
            System.out.println(label + " -> " + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        RunMode typed = parseTyped(RunMode.class, "FAST");
        System.out.println("Typed name = " + typed.name());
        System.out.println("Same constant = " + (typed == RunMode.FAST));
        System.out.println("Generated valueOf agrees = "
                + (RunMode.valueOf("FAST") == typed));
        System.out.println("Display label = " + typed);
        System.out.println("Business code = " + typed.code());
        System.out.println("Normalized name = "
                + parseNormalized(RunMode.class, " fast ").name());

        Class<?> discovered = Class.forName("EnumValueOfDemo$RunMode");
        Enum<?> dynamic = parseRuntime(discovered, "TURBO");
        System.out.println("Runtime enum type = "
                + dynamic.getDeclaringClass().getSimpleName());
        System.out.println("Runtime name = " + dynamic.name());
        System.out.println("Runtime display = " + dynamic);

        attempt("wrong case", () -> parseTyped(RunMode.class, "fast"));
        attempt("extra spaces", () -> parseTyped(RunMode.class, " FAST "));
        attempt("display label", () -> parseTyped(RunMode.class, "Fast execution"));
        attempt("business code", () -> parseTyped(RunMode.class, "fast-code"));
        attempt("ordinal text", () -> parseTyped(RunMode.class, "1"));
        attempt("missing name", () -> parseTyped(RunMode.class, "UNKNOWN"));
        attempt("null name", () -> parseTyped(RunMode.class, null));
        attempt("not an enum", () -> parseRuntime(String.class, "FAST"));
        attempt("null class", () -> parseRuntime(null, "FAST"));

        Enum<?> selected = RunMode.TURBO;
        attempt("constant runtime class",
                () -> parseRuntime(selected.getClass(), "SAFE"));
        System.out.println("From declaring class = "
                + parseRuntime(selected.getDeclaringClass(), "SAFE").name());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 -Xlint:all -Werror EnumValueOfDemo.java
java EnumValueOfDemo
```

Kết quả:

```text
Typed name = FAST
Same constant = true
Generated valueOf agrees = true
Display label = Fast execution
Business code = fast-code
Normalized name = FAST
Runtime enum type = RunMode
Runtime name = TURBO
Runtime display = Turbo custom label
wrong case -> IllegalArgumentException
extra spaces -> IllegalArgumentException
display label -> IllegalArgumentException
business code -> IllegalArgumentException
ordinal text -> IllegalArgumentException
missing name -> IllegalArgumentException
null name -> NullPointerException
not an enum -> IllegalArgumentException
null class -> NullPointerException
constant runtime class -> IllegalArgumentException
From declaring class = SAFE
```

Hàm `attempt()` chỉ phục vụ quan sát các trường hợp lỗi trong thí nghiệm: in tên ngoại lệ rồi tiếp tục thử trường hợp kế tiếp. Nó không phải mẫu để bỏ qua mọi `RuntimeException` trong mã ứng dụng.

## 4. Đọc luồng tra cứu có kiểu rõ ràng

`parseTyped` có tham số `Class<E>` và trả về `E`. Khi truyền `RunMode.class`, bên sử dụng nhận trực tiếp `RunMode`:

1. `Enum.valueOf` tìm `FAST` trong đúng tập hằng của `RunMode`.
2. Biến `typed` nhận hằng đó; so sánh với `RunMode.FAST` cho `true`.
3. `RunMode.valueOf("FAST")` cũng cho cùng hằng.
4. In `typed.name()` được `FAST`, nhưng in trực tiếp `typed` được `Fast execution` vì enum đã ghi đè `toString()`.

Điều này lý giải vì sao dùng nhãn hiển thị làm đầu vào cho `valueOf` không khớp với chính sách tra cứu. Nếu dữ liệu bên ngoài sử dụng `fast-code`, ứng dụng cần một phép tra cứu theo mã riêng và quy định cách xử lý mã không tồn tại.

Cũng không nên đổi tên hằng tùy tiện nếu tên đó đã được dùng trong cấu hình hoặc dữ liệu trao đổi. Chuỗi cũ không tự biến thành tên mới chỉ vì enum đã được cập nhật.

## 5. Khi chỉ có `Class<?>` lúc chạy

Trong chương trình, `Class.forName("EnumValueOfDemo$RunMode")` trả `Class<?>`. Tên chứa `$` vì `RunMode` là enum lồng trong `EnumValueOfDemo`; đây là tên nhị phân dùng để tìm đúng lớp trong ví dụ.

Mặc dù đối tượng `Class` thực tế đại diện cho `RunMode`, biến `discovered` không giữ thông tin `Class<RunMode>` ở mức kiểu tĩnh. Do đó, đoạn sau **chủ đích không biên dịch**:

```java
Class<?> discovered = RunMode.class;
// Lỗi biên dịch: Class<?> chưa đáp ứng ràng buộc Class<T> với T extends Enum<T>.
Enum<?> value = Enum.valueOf(discovered, "FAST");
```

`if (discovered.isEnum())` kiểm tra điều kiện lúc chạy, nhưng không tự đổi kiểu tĩnh của biến thành `Class<RunMode>`. Đây là khác biệt giữa **xác minh giá trị metadata** và **chứng minh quan hệ kiểu cho trình biên dịch**.

### Ranh giới động trong hàm mẫu

`parseRuntime` xử lý sự khác biệt này theo một ranh giới hẹp:

1. Từ chối `null` cho cả lớp và tên.
2. Dùng `isEnum()` để bảo đảm lớp là một khai báo enum, không phải lớp thông thường hoặc lớp riêng của một hằng.
3. Chỉ sau kiểm tra mới gọi hàm riêng `parseCheckedClass`.
4. Hàm riêng cô lập phép ép kiểu chưa thể kiểm chứng đầy đủ lúc biên dịch, sau đó gọi `Enum.valueOf`.
5. Bên ngoài chỉ nhận `Enum<?>`, vì bên gọi chưa biết kiểu enum cụ thể.

`@SuppressWarnings("unchecked")` nằm ở đúng hàm có phép ép kiểu; nó **không thực hiện xác minh** và không khiến một lớp sai trở nên hợp lệ. Điều kiện `isEnum()` cùng việc chỉ gọi hàm riêng từ nhánh đã kiểm tra mới là căn cứ của thiết kế mẫu.

Không công khai hàm riêng đó như một phương thức cho phép bên gọi tùy ý chọn `E`. Nếu một người gọi được phép yêu cầu `E` khác với lớp truyền vào, kiểu trả về sẽ tạo ra một lời hứa sai. Hợp đồng công khai `Enum<?> parseRuntime(...)` tránh lời hứa đó.

Nếu lớp enum vẫn được biết trong phần lớn mã ứng dụng, hãy giữ `Class<E>` và dùng hàm có kiểu rõ ràng. Chỉ đưa phép ép kiểu vào nơi thật sự phải tiếp nhận `Class<?>`.

### Phân biệt lỗi tìm lớp và lỗi tìm hằng

`Class.forName` có thể ném `ClassNotFoundException` trước khi tìm được đối tượng `Class`. `Enum.valueOf` lại xử lý bước tìm hằng bên trong kiểu đã xác định. Trong ví dụ, `main` khai báo `throws ClassNotFoundException` vì bước khám phá lớp; không phải vì `Enum.valueOf` ném ngoại lệ đó.

Không cần tìm phương thức `valueOf` bằng `Method.invoke` chỉ để thực hiện phép tra cứu này. API `Enum.valueOf` đã nhận trực tiếp đối tượng `Class`.

## 6. Cần truyền lớp khai báo enum

`RunMode.TURBO` có phần thân riêng để ghi đè `toString()`. Vì vậy, lớp thực tế từ `selected.getClass()` là một lớp vô danh của hằng, không phải chính khai báo `RunMode`.

Trong thí nghiệm, `parseRuntime(selected.getClass(), "SAFE")` bị từ chối bởi `isEnum()`. Nhưng `parseRuntime(selected.getDeclaringClass(), "SAFE")` thành công. Với một giá trị `Enum<?>`, `getDeclaringClass()` trả lớp enum sở hữu hằng. [API `Class.isEnum()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#isEnum()) nêu rõ sự khác biệt này.

Không thay kiểm tra bằng việc chỉ hỏi lớp có kế thừa `Enum` hay không: lớp riêng của hằng vẫn kế thừa enum nhưng không phải khai báo enum cần dùng để tra cứu toàn bộ tập hằng.

## 7. Chuẩn hóa đầu vào là chính sách của ứng dụng

`parseTyped(RunMode.class, " fast ")` không được làm cho thành công một cách ngầm định. Hàm `parseNormalized` trong chương trình tạo ra hợp đồng khác:

```java
String normalized = text.strip().toUpperCase(Locale.ROOT);
return Enum.valueOf(enumType, normalized);
```

Đây là đoạn trích từ hàm đã có trong chương trình, không phải chương trình độc lập. `Locale.ROOT` giúp việc đổi hoa thường không phụ thuộc ngôn ngữ mặc định của máy; đó là mục đích của [locale gốc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Locale.html#ROOT).

Trong thí nghiệm, quy ước tên hằng là chữ hoa, nên `" fast "` được đổi thành `"FAST"` rồi tra cứu thành công. Bạn phải lựa chọn chính sách này theo định dạng dữ liệu đang xử lý.

Không áp dụng chuẩn hóa một cách phổ quát: nếu một định dạng yêu cầu tên chính xác, khoảng trắng hoặc hoa thường sai cần được báo lỗi. Tên hằng Java cũng không bị bắt buộc phải là chữ hoa; một quy tắc đổi hoa có thể làm mất khác biệt giữa những tên mà ứng dụng muốn phân biệt.

Chuẩn hóa tên vẫn không biến `fast-code` thành `FAST`, và cũng không biến nhãn nhiều từ thành tên hằng. Những ánh xạ đó cần một hợp đồng riêng.

## 8. Xử lý lỗi và lỗi thường gặp

| Tình huống | Hành vi hoặc cách xử lý |
| --- | --- |
| Tên không tồn tại, sai hoa thường hoặc có khoảng trắng thừa | `IllegalArgumentException` từ tra cứu chính xác |
| Tên là `null` | `NullPointerException` |
| Lớp là `null` | `NullPointerException` |
| `parseRuntime` nhận lớp không phải khai báo enum | Chủ động ném `IllegalArgumentException` trước khi ép kiểu |
| Chỉ có `Class<?>` nhưng gọi trực tiếp `Enum.valueOf` | Lỗi biên dịch do chưa thỏa ràng buộc kiểu |
| Truyền `String.class` vào lời gọi có kiểu chặt chẽ | Trình biên dịch không chấp nhận đó như một lớp enum |
| Dùng nhãn hiển thị, mã nghiệp vụ hoặc chuỗi số | Không tự được hiểu như tên khai báo |

Khi dữ liệu do người dùng cung cấp, hãy xử lý lỗi tra cứu ở ranh giới chuyển đổi và báo rõ giá trị không được hỗ trợ trong trường dữ liệu nào. Đừng tự chọn hằng đầu tiên làm mặc định chỉ để tránh lỗi: điều đó có thể đổi ý nghĩa yêu cầu mà bên sử dụng không biết.

Nếu ứng dụng muốn có kết quả dạng tùy chọn hoặc một kết quả chứa thông tin lỗi, hãy định nghĩa một hàm bao có hợp đồng đó. Bản thân `Enum.valueOf` không trả `null` hoặc `Optional.empty()` để báo tên không tồn tại.

Chỉ bắt ngoại lệ bạn thực sự biết cách xử lý. Lỗi do truyền lớp sai vào một bộ chuyển đổi nội bộ thường cần được sửa ở cấu hình hoặc mã gọi; nó không nên bị giấu chung với lỗi nhập sai tên hằng.

### Tự kiểm tra

1. Vì sao cần truyền cả `Class` lẫn tên hằng, thay vì chỉ truyền chuỗi `"FAST"`?
2. Vì sao `RunMode.class` dùng được trực tiếp nhưng biến `Class<?>` cần thêm xử lý?
3. Nếu đổi `toString()` thành một nhãn khác, lời gọi với `"FAST"` có bị đổi ý nghĩa không?
4. Vì sao `isEnum()` trả `true` không tự thay đổi kiểu tĩnh của biến?
5. Với một hằng có phần thân riêng, nên lấy `Class` bằng phương thức nào để tra cứu hằng cùng enum?
6. Khi nào việc tự cắt khoảng trắng và đổi chữ hoa là hợp đồng đúng, và khi nào nên báo đầu vào không hợp lệ?

Cần nhớ ba thông tin khi áp dụng: **đúng lớp khai báo enum, đúng tên khai báo của hằng, và đúng ranh giới giữa thông tin kiểu tĩnh với metadata lúc chạy**.
