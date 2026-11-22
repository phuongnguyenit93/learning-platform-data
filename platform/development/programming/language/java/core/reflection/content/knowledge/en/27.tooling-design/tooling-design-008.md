# Ánh xạ giá trị đầu vào theo quy tắc chuyển đổi tường minh

## 1. Bài toán trong công cụ dùng Java Reflection

Một công cụ gọi phương thức bằng reflection có thể nhận đầu vào từ CLI, HTTP request, cấu hình hoặc biểu mẫu. Nguồn dữ liệu thường đưa cho công cụ **chuỗi** (ví dụ `"3"`, `"true"`, `"2026-10-24"`), nhưng phương thức Java cần các kiểu thực tế như `int`, `boolean`, `LocalDate` hoặc enum.

Ví dụ phương thức đích:

```java
public String create(int count, boolean urgent, LocalDate due,
                     Priority priority, BigDecimal budget) {
    // Xử lý nghiệp vụ.
}
```

Công cụ không thể chỉ đưa các chuỗi thẳng vào `Method.invoke`:

```java
// SAI nếu method nhận int, boolean, LocalDate, Priority, BigDecimal:
method.invoke(target, "3", "true", "2026-10-24", "HIGH", "125.50");
```

`Method.invoke` **không có chức năng parse chuỗi thành kiểu nghiệp vụ**. Với đối số được cung cấp, reflection có thể áp dụng một số **unboxing/widening** primitive phù hợp, nhưng không tự biết `"3"` nghĩa là số nguyên, `"HIGH"` nghĩa là enum hay một chuỗi ngày phải theo định dạng nào. Để hệ thống đoán ngầm làm hành vi khó kiểm tra, khó báo lỗi và dễ thiếu an toàn.

**Mục tiêu bài học:** xây dựng cơ chế chuyển đổi rõ ràng từ **giá trị đầu vào** sang **kiểu tham số đích**, kiểm tra và báo lỗi trước khi thực sự gọi method. Đây là kỹ thuật thiết kế công cụ reflection, không phải hướng dẫn ghi đè hệ thống chuyển đổi của Java.

Sau bài học, bạn có thể:

- Lấy kiểu tham số bằng `Method.getParameterTypes()`, kiểm tra số lượng và thứ tự.
- Khai báo bảng quy tắc chuyển đổi được cho phép (allowlist), thay vì đoán bằng chuỗi tên lớp.
- Phân biệt dữ liệu `null`, chuỗi rỗng, chuỗi `"null"` và giá trị đã được parse.
- Tách **lỗi chuyển đổi** khỏi **ngoại lệ do nghiệp vụ ném**.
- Xử lý phạm vi phức tạp hơn như overloaded methods, varargs, generic, enum và phân quyền gọi phương thức.
- Thiết kế kết quả và lỗi có thể kiểm thử, dễ mở rộng mà không tạo những phép chuyển đổi khó đoán.

## 2. Quy trình ánh xạ: từ input đến tham số Method

Một pipeline rõ ràng nên có các bước:

```text
Input thô (chuỗi hoặc dữ liệu đã parse)
        |
        v
Xác định phương thức được phép gọi
        |
        v
Method.getParameterTypes() -> kiểu theo từng vị trí
        |
        v
Kiểm tra số lượng đối số, null và quy tắc cho từng kiểu
        |
        v
Chuyển đổi + kiểm tra lỗi có ngữ cảnh
        |
        v
Object[] đã chuyển đổi
        |
        v
Method.invoke(target, convertedArgs)
```

Mỗi vị trí `i` tương ứng đúng một `parameterTypes[i]` và một giá trị đầu vào `rawValues[i]`. Trong Java, vị trí tham số bắt đầu từ **0**. Nếu ứng dụng muốn hiển thị “tham số thứ nhất”, có thể chuyển `i + 1` khi tạo thông điệp.

Hai API cần biết:

```java
Class<?>[] types = method.getParameterTypes();
int count = method.getParameterCount();
```

`getParameterTypes()` trả về các kiểu **sau type erasure**. Ví dụ `List<String>` và `List<Integer>` đều có kiểu tham số runtime là `List.class`. `getGenericParameterTypes()` có thể giúp đọc khai báo generic ở mức metadata, nhưng không tự parse hoặc kiểm chứng nội dung generic.

`method.getParameters()` có thể cung cấp metadata về tham số. Tuy nhiên, tên có ý nghĩa trong source thường chỉ sẵn có nếu biên dịch với `-parameters`; nếu không, tên như `arg0` có thể xuất hiện. Công cụ không được phụ thuộc mù quáng vào tên tham số khi chưa xác nhận metadata.

## 3. Quy tắc chuyển đổi phải được khai báo rõ

Đầu tiên hãy quyết định **loại input hỗ trợ**. Ví dụ minh họa dưới đây nhận `String[]` từ nguồn dữ liệu dạng text. Đây là lựa chọn có chủ đích; nếu nhận JSON, công cụ cần phân biệt token number/boolean/null của JSON với chuỗi JSON trước khi ánh xạ.

Bảng chính sách mẫu:

| Kiểu đích | Quy tắc được phép | Ví dụ hợp lệ | Ví dụ bị từ chối |
| --- | --- | --- | --- |
| `String` | Giữ nguyên văn bản, không tự trim | `"  A  "` | Không tự đổi định dạng |
| `int` / `Integer` | `Integer.valueOf(raw)`; kiểm tra phạm vi `int` | `"3"`, `"-8"` | `"3.5"`, số vượt miền |
| `long` / `Long` | `Long.valueOf(raw)`; kiểm tra phạm vi `long` | `"9876543210"` | Giá trị vượt `long` |
| `boolean` / `Boolean` | Chỉ chấp nhận **chính xác** `"true"` hoặc `"false"` | `"true"` | `"yes"`, `"TRUE"` |
| `LocalDate` | `LocalDate.parse(raw)` theo ISO-8601 mặc định | `"2026-10-24"` | `"24/10/2026"` |
| Một enum được cho phép, ví dụ `Priority` | `Priority.valueOf(raw)`; khớp tên constant | `"HIGH"` | `"High"` |
| `BigDecimal` | `new BigDecimal(raw)` theo cú pháp số thập phân Java | `"125.50"` | `"12,50"` với dấu phẩy |

Đây là **chính sách mẫu**, không phải giới hạn của Java. Ứng dụng có thể chọn quy tắc khác như không phân biệt hoa thường hoặc chấp nhận dấu cách, nhưng phải ghi rõ, kiểm tra và áp dụng thống nhất. Với tiền tệ, `BigDecimal` thường thích hợp hơn `double` để tránh sai số nhị phân trong nhiều phép toán thập phân; các quy định về scale, làm tròn và tiền tệ cần được xác định riêng ở tầng nghiệp vụ.

**Tránh các chuyển đổi đoán ngầm:**

- Không gọi `String.valueOf(x)` trên mọi dữ liệu để rồi đoán lại kiểu.
- Không coi bất kỳ chuỗi ngoài `"true"` là `false`. `Boolean.parseBoolean("yes")` trả `false`, nên không đáp ứng chính sách strict của bài.
- Không tự parse ngày với nhiều định dạng mà không có thứ tự ưu tiên rõ ràng.
- Không tạo mọi lớp bằng `Class.forName(raw)` hay gọi mọi phương thức theo tên do người dùng tùy ý cung cấp.
- Không lấy “có thể cast” làm đồng nghĩa với “ngữ nghĩa đúng”; ví dụ chuyển `long` sang `int` có thể mất dữ liệu.

## 4. Ví dụ Java 17+ hoàn chỉnh: chuyển đổi tường minh và gọi Method

Tạo tệp `ExplicitMappingDemo.java`:

```java
import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Locale;

public class ExplicitMappingDemo {
    enum Priority { LOW, HIGH }

    public static class TaskService {
        public String create(int count, boolean urgent, LocalDate due,
                             Priority priority, BigDecimal budget) {
            return String.format(Locale.ROOT,
                    "count=%d urgent=%s due=%s priority=%s budget=%s",
                    count, urgent, due, priority, budget.toPlainString());
        }
    }

    static Object[] mapArguments(Method method, String[] rawValues) {
        Class<?>[] types = method.getParameterTypes();
        if (rawValues.length != types.length) {
            throw new IllegalArgumentException(
                    "expected " + types.length + " arguments, got " + rawValues.length);
        }

        Object[] converted = new Object[types.length];
        for (int i = 0; i < types.length; i++) {
            try {
                converted[i] = convert(rawValues[i], types[i]);
            } catch (IllegalArgumentException | DateTimeParseException ex) {
                throw new IllegalArgumentException(
                        "argument " + i + " must be " + types[i].getTypeName(), ex);
            }
        }
        return converted;
    }

    static Object convert(String raw, Class<?> type) {
        if (raw == null) {
            if (type.isPrimitive()) {
                throw new IllegalArgumentException("primitive cannot be null");
            }
            return null;
        }
        if (type == String.class) return raw;
        if (type == int.class || type == Integer.class) return Integer.valueOf(raw);
        if (type == long.class || type == Long.class) return Long.valueOf(raw);
        if (type == boolean.class || type == Boolean.class) {
            if (raw.equals("true")) return true;
            if (raw.equals("false")) return false;
            throw new IllegalArgumentException("boolean must be true or false");
        }
        if (type == LocalDate.class) return LocalDate.parse(raw);
        if (type == Priority.class) return Priority.valueOf(raw);
        if (type == BigDecimal.class) return new BigDecimal(raw);
        throw new IllegalArgumentException("unsupported type: " + type.getTypeName());
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Method method = TaskService.class.getMethod("create",
                int.class, boolean.class, LocalDate.class,
                Priority.class, BigDecimal.class);
        String[] raw = {"3", "true", "2026-10-24", "HIGH", "125.50"};
        Object result = method.invoke(new TaskService(), mapArguments(method, raw));
        System.out.println(result);

        try {
            mapArguments(method,
                    new String[]{"3", "yes", "2026-10-24", "HIGH", "125.50"});
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }

        try {
            mapArguments(method, new String[]{null, "true", "2026-10-24", "HIGH", "125.50"});
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac ExplicitMappingDemo.java
java ExplicitMappingDemo
```

Stdout **đã được kiểm chứng bằng chạy chương trình Java**:

```text
count=3 urgent=true due=2026-10-24 priority=HIGH budget=125.50
rejected: argument 1 must be boolean
rejected: argument 0 must be int
```

Phân tích:

1. `getMethod("create", int.class, boolean.class, LocalDate.class, Priority.class, BigDecimal.class)` định vị **một chữ ký chính xác** trên lớp `TaskService`, tránh đoán overload từ các chuỗi người dùng.
2. `getParameterTypes()` trả năm kiểu đúng theo thứ tự khai báo; `rawValues.length` phải bằng năm.
3. `convert` có nhánh riêng theo **`Class<?>` đích**, không dựa vào tên class dạng chuỗi.
4. `"3"` được parse thành `Integer`; khi `Method.invoke` gọi phương thức nhận `int`, wrapper được unbox hợp lệ.
5. Boolean chỉ nhận `"true"/"false"`; `"yes"` bị báo lỗi tại tham số có index `1`, trước khi gọi business method.
6. `LocalDate.parse` xử lý ngày ISO; `Priority.valueOf` nhận một enum constant cụ thể; `BigDecimal` lưu giá trị `125.50` và `toPlainString()` giữ cách hiển thị thập phân.
7. Tham số đầu tiên kiểu `int` không thể nhận `null`; lỗi được phát hiện trước reflection invocation.

**Giới hạn có chủ đích của ví dụ:** hiện chỉ cho phép `String`, `int/Integer`, `long/Long`, `boolean/Boolean`, `LocalDate`, enum `Priority` và `BigDecimal`. Kiểu khác sẽ bị từ chối. Có thể mở rộng theo chính sách cụ thể, nhưng không nên âm thầm “nhận mọi lớp”. Ví dụ cũng coi `raw == null` là **vắng giá trị thật**; chuỗi `"null"` vẫn là chuỗi có bốn ký tự, không tự biến thành null.

## 5. Kiểu primitive và wrapper: kiểm tra khả năng null

Reflection phân biệt `int.class` với `Integer.class`:

- `int.class.isPrimitive()` cho `true`; không thể truyền `null` vào tham số primitive `int`.
- `Integer.class.isPrimitive()` cho `false`; `null` có thể được dùng ở mức lời gọi, nhưng phương thức nghiệp vụ vẫn có thể từ chối nếu không chấp nhận giá trị vắng.
- `Method.invoke` thường nhận một `Object[]`; giá trị `int` được biểu diễn qua `Integer` ở mảng đó rồi được reflection unbox khi cần.
- Có một số phép **widening primitive** hợp lệ khi reflection invoke, nhưng phép chuyển đổi có ngữ nghĩa nghiệp vụ vẫn nên do lớp ánh xạ quy định. Reflection không thực hiện narrowing tùy ý hoặc parse `String` thành `int`.

Bảng rủi ro:

| Đầu vào | Kiểu đích | Quyết định |
| --- | --- | --- |
| `null` | `int` | Từ chối ngay |
| `null` | `Integer` | Cho phép ở tầng converter ví dụ; nghiệp vụ xác định có hợp lệ không |
| `"0"` | `int` | Parse thành `Integer.valueOf("0")`, unbox lúc gọi |
| `"2147483648"` | `int` | Từ chối do vượt phạm vi |
| `""` | `int` | Parse thất bại, không tự đặt mặc định `0` |
| `""` | `String` | Giữ chuỗi rỗng |
| `"null"` | `String` | Giữ chuỗi đúng nghĩa, không tự biến thành `null` |

Đừng dùng giá trị mặc định `0`, `false` hoặc `LocalDate.now()` để thay thế đầu vào lỗi mà không có hợp đồng yêu cầu; điều đó có thể khiến hệ thống làm sai thao tác.

## 6. Thiết kế lỗi tốt và kiểm thử từng quy tắc

Một converter tốt nên trả về **kết quả thành công có kiểu rõ ràng**, hoặc một lỗi chứa tối thiểu:

- Vị trí tham số (`index`) hay tên tham số đã được xác nhận.
- Kiểu đích yêu cầu (`Class.getTypeName()`).
- Mã lỗi ngắn gọn: sai số lượng, không hỗ trợ kiểu, format không hợp lệ, vượt phạm vi, null không được phép.
- Nguyên nhân gốc được giữ lại (cause) để phục vụ chẩn đoán nội bộ.

Ví dụ sử dụng `IllegalArgumentException` bọc nguyên nhân gốc:

```java
try {
    converted[i] = convert(rawValues[i], types[i]);
} catch (IllegalArgumentException | DateTimeParseException ex) {
    throw new IllegalArgumentException(
            "argument " + i + " must be " + types[i].getTypeName(), ex);
}
```

Đây là mảnh code trích từ ví dụ đầy đủ. Việc giữ `cause` giúp phân biệt `NumberFormatException` với `DateTimeParseException` mà không làm người dùng cuối nhận một stack trace nội bộ.

**Không tự động đưa nội dung đầu vào nhạy cảm vào thông báo lỗi**: công cụ có thể đang xử lý mã truy cập, email hoặc dữ liệu cá nhân. Ghi đủ thông tin vị trí/kiểu, đồng thời áp dụng chính sách log phù hợp.

Nên kiểm thử bằng các nhóm:

| Nhóm | Ca kiểm tra |
| --- | --- |
| Hợp lệ | Giá trị biên của `int/long`, boolean `true/false`, ngày ISO, enum hợp lệ |
| Sai định dạng | `"12.5"` vào `int`, `"yes"` vào boolean, ngày `"31/12/2026"` |
| Ngoài miền | Số lớn hơn `Integer.MAX_VALUE` hoặc nhỏ hơn `Integer.MIN_VALUE` |
| Null/rỗng | `null` sang primitive, chuỗi rỗng sang số, chuỗi `"null"` |
| Sai số lượng | Thiếu/thừa đối số |
| Không hỗ trợ kiểu | `UUID`, `List`, class tự định nghĩa khi chưa đăng ký converter |
| Sai nghiệp vụ | Đã parse đúng kiểu nhưng vi phạm điều kiện như `count < 0` |
| Ngoại lệ từ target | Phương thức đích ném lỗi sau bước chuyển đổi |

Lưu ý `convert` chỉ chịu trách nhiệm kiểm tra kiểu/cú pháp đã quy định; **validation nghiệp vụ** như giá tiền phải dương, số lượng tối đa hay deadline hợp lệ cần một bước riêng. Parse thành công không đồng nghĩa input đã được phép sử dụng.

## 7. Tách lỗi chuyển đổi khỏi lỗi Method.invoke

Sau khi mapper trả về một `Object[]` hợp lệ, lời gọi reflection vẫn có thể thất bại vì:

- Không có quyền truy cập phương thức, phát sinh `IllegalAccessException`.
- Đối tượng `target` không phù hợp với phương thức instance hoặc đối số không tương thích tại lúc gọi, dẫn đến `IllegalArgumentException`.
- Phương thức đích thật sự ném ngoại lệ, được bọc thành `InvocationTargetException`.

Một mảnh code minh họa xử lý ở tầng gọi (cần import `java.lang.reflect.InvocationTargetException` và `Method`):

```java
try {
    Object[] args = mapArguments(method, rawValues);
    return method.invoke(target, args);
} catch (InvocationTargetException ex) {
    // Lỗi từ chính phương thức nghiệp vụ.
    throw ex.getCause();
}
```

Mảnh code này thuộc một phương thức khai báo `throws Throwable`; các ngoại lệ truy cập/chuyển đổi cần được xử lý ở tầng gọi phù hợp. **Đừng coi `InvocationTargetException` là lỗi parse**: target đã chạy và tự ném ngoại lệ. Phân biệt hai loại lỗi giúp xác định nên báo người dùng sửa input hay sửa logic nghiệp vụ.

Trong code sản phẩm, thay vì bắt tất cả `Exception` rồi trả cùng một thông điệp, hãy phân loại lỗi theo mã, ghi log đúng lớp và chỉ hiển thị nội dung phù hợp với người dùng.

## 8. Overload, varargs, enum và generic

### 8.1. Overloaded methods

`getMethod` chọn theo tên và **danh sách kiểu tham số chính xác**:

```java
// Nếu có create(int) và create(String):
Method m = SomeService.class.getMethod("create", int.class);
```

Đừng quyết định overload bằng cách “chọn phương thức đầu tiên có cùng tên” từ `getMethods()`: thứ tự phản hồi không phải hợp đồng để chọn overload, và cùng chuỗi `"123"` có thể hợp lệ với cả `String` và `int`. Nếu buộc phải giải quyết overload động, hãy định nghĩa thứ tự ưu tiên và quy tắc phát hiện mơ hồ; nếu hai phương thức cùng phù hợp mà không có quy tắc rõ, **báo ambiguity** thay vì đoán.

### 8.2. Varargs

Một phương thức `send(String... messages)` có tham số cuối kiểu `String[]` ở cấp reflection. `Method.isVarArgs()` giúp nhận biết declaration, nhưng `getParameterTypes()` vẫn cho mảng ở vị trí cuối.

Khi dùng `Method.invoke`, cần xây dựng mảng đúng kiểu cho tham số varargs và đặt nó thành **một phần tử** của `Object[]` đối số gọi phương thức. Mapper đơn giản trong ví dụ không tự thu gom nhiều chuỗi thành mảng; nếu cần, phải định nghĩa riêng cách ánh xạ varargs, chặn thiếu tham số bắt buộc và phân biệt một mảng với nhiều đối số.

### 8.3. Enum

`Enum.valueOf(...)` phân biệt hoa thường và ném `IllegalArgumentException` khi không có constant tương ứng. Ví dụ chỉ hỗ trợ `Priority`, nên không mở rộng quyền chuyển đổi sang bất kỳ enum có trong classpath.

Nếu muốn hỗ trợ các enum khác, nên đăng ký những enum được phép và, khi cần, dùng ánh xạ tên thân thiện sang constant thông qua bảng cấu hình rõ ràng. Không nạp lớp hoặc constant tùy tiện theo dữ liệu đầu vào không đáng tin.

### 8.4. Collections và generic

`List<String>` không thể được xác định đầy đủ chỉ từ `getParameterTypes()` vì type erasure. Muốn ánh xạ JSON list vào danh sách các phần tử có kiểu, cần có quy tắc đọc `getGenericParameterTypes()` hoặc schema riêng, kiểm tra từng phần tử, chính sách null và giới hạn kích thước.

Trong thiết kế công cụ thực tế, schema/DTO thường rõ ràng hơn việc suy đoán generic của mọi trường hợp reflection. Đặc biệt, không nên cho phép phản chiếu vào mọi field private chỉ để tạo đối tượng từ input.

## 9. Mở rộng bằng converter registry có kiểm soát

Khi số kiểu hỗ trợ tăng, thay chuỗi `if` bằng registry kết hợp **kiểu đích** và **hàm chuyển đổi**:

```java
// Mảnh code minh họa trong lớp đã import Map, Class, Function.
Map<Class<?>, java.util.function.Function<String, ?>> converters = Map.of(
        String.class, raw -> raw,
        Integer.class, Integer::valueOf,
        Long.class, Long::valueOf,
        LocalDate.class, LocalDate::parse
);
```

Registry minh họa trên chỉ đăng ký kiểu wrapper/reference; khi nhận primitive, phải có bước ánh xạ `int.class -> Integer.class`, `long.class -> Long.class` theo chính sách. Tương tự, enum hoặc converter có tham số bổ sung có thể cần API giàu ngữ cảnh hơn. Đoạn code này **không phải** mapper đầy đủ và chưa xử lý null/boolean/error; ví dụ mục 4 là chương trình chạy độc lập.

Một thiết kế ổn định nên có các thành phần:

1. **Danh sách method/class được phép truy cập** độc lập với converter. Được parse một kiểu không đồng nghĩa được quyền gọi mọi method nhận kiểu đó.
2. **Converter registry** chỉ hỗ trợ những kiểu đã đăng ký, có test riêng và quy tắc format được tài liệu hóa.
3. **Validation layer** kiểm tra ràng buộc nghiệp vụ sau khi parse, trước khi gọi.
4. **Invocation layer** chỉ nhận dữ liệu đã được chuẩn hóa và phân biệt lỗi reflection với lỗi do target ném.
5. **Error reporting** cung cấp vị trí, tên kiểu, mã lỗi và cause để debug, nhưng không lộ dữ liệu nhạy cảm.

Có thể sử dụng schema chung cho command line, request body và cấu hình, nhưng mỗi nguồn vẫn cần parser ban đầu riêng (ví dụ JSON number khác JSON string).

## 10. Các lỗi thiết kế thường gặp

1. **Dùng `Method.invoke(target, strings...)` rồi chờ JVM parse chuỗi:** reflection không làm điều đó.
2. **Dựa vào `Object.toString()` để chuyển đổi mọi kiểu:** mất cấu trúc dữ liệu và format có thể phụ thuộc locale.
3. **Dùng `Boolean.parseBoolean` cho yêu cầu strict:** giá trị bất kỳ ngoài `"true"` có thể âm thầm thành `false`.
4. **Tự động trim hoặc thay dấu thập phân:** dữ liệu `String` gốc có thể cần giữ nguyên; phép chuẩn hóa phải được khai báo riêng.
5. **Tự chọn overload đầu tiên theo tên:** gây lỗi không ổn định khi thêm overload hoặc chạy JVM khác.
6. **Cho phép `null` vào primitive:** phải phát hiện trước khi invoke.
7. **Không phân biệt parse với validation nghiệp vụ:** `"-1"` có thể parse hợp lệ thành `int`, nhưng `count = -1` vẫn sai.
8. **Đưa trực tiếp raw value vào log lỗi:** có nguy cơ lộ dữ liệu nhạy cảm.
9. **Tự động chấp nhận mọi class/constructor/field có thể truy cập:** biến converter thành điểm mở rộng quá quyền và khó kiểm toán.
10. **Coi generic runtime có đầy đủ type argument:** cần schema hoặc đọc generic metadata có kiểm soát.

## 11. Tự kiểm tra

**Câu 1.** Đích nhận `int`, raw value là `"007"`. Phép chuyển đổi nên diễn ra thế nào? 

Nếu chính sách chọn `Integer.valueOf` như mẫu, chuỗi được parse thành số nguyên `7`; không có phép “giữ số 0 đầu” với `int`. Nếu các số 0 đầu mang ý nghĩa nghiệp vụ, kiểu đích có thể phải là `String`.

**Câu 2.** Vì sao `Boolean.parseBoolean("yes")` không phù hợp với chính sách boolean strict?

Vì nó trả `false` cho giá trị không bằng `"true"` theo cơ chế của API; dữ liệu sai bị hiểu là giá trị hợp lệ. Cần kiểm tra danh sách literal cho phép rồi mới chuyển đổi.

**Câu 3.** Nếu người dùng nhập `"2026-02-30"`, `LocalDate.parse` sẽ ra sao?

Ngày không tồn tại nên parse thất bại (thường là `DateTimeParseException`); mapper phải báo lỗi vị trí/kiểu và không gọi phương thức nghiệp vụ.

**Câu 4.** Hai overload `save(int)` và `save(String)` cùng nhận được chuỗi `"123"` theo hai chính sách. Nên gọi hàm nào?

Không thể quyết định chỉ từ input. Phải có định nghĩa lựa chọn overload; nếu thiếu thì báo ambiguity hoặc yêu cầu người gọi chỉ rõ chữ ký.

**Câu 5.** `getParameterTypes()` cho `List.class`, có đủ để khẳng định phần tử phải là `String`?

Không. Java erasure loại bỏ phần lớn type argument ở cấp `Class<?>`; dùng schema hoặc generic metadata riêng nếu cần.

**Câu 6.** Vì sao phải giữ nguyên cause khi bọc lỗi mapping?

Để phân biệt nguyên nhân như out-of-range integer, sai tên enum hoặc sai cú pháp ngày, nhưng giao diện người dùng vẫn có thể trả thông điệp ổn định không chứa dữ liệu nhạy cảm.

## 12. Ghi nhớ

**Ánh xạ tường minh = biết trước kiểu đích, khai báo phép chuyển đổi được phép, kiểm tra đầu vào, rồi mới gọi reflection.** Công cụ vững chắc không cố “đoán đúng mọi input”; nó cung cấp một hợp đồng chuyển đổi có thể giải thích, kiểm thử và mở rộng. `Method.getParameterTypes()` cung cấp các kiểu tham số tại runtime; converter chịu trách nhiệm parse; validation chịu trách nhiệm ràng buộc nghiệp vụ; `Method.invoke` chỉ thực hiện lời gọi.

Tài liệu JDK 17:

- [Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Method.getParameterTypes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html#getParameterTypes())
- [Integer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Integer.html)
- [Boolean](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Boolean.html)
- [LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html)