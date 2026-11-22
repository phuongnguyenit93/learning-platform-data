# Thực hành: Viết công cụ gọi phương thức từ một hợp đồng đã xác thực

## 1. Bài toán và kết quả cần đạt

Một công cụ dùng Java Reflection có thể nhận yêu cầu dạng `(tên thao tác, danh sách giá trị đầu vào)` rồi chuyển chúng thành lời gọi phương thức. Ví dụ:

```text
sum   ["7", "5"] -> 12
label ["go", "3"] -> "gogogo"
```

Tuy nhiên, công cụ **không được** suy ra class, tên method hay chữ ký tùy ý từ input rồi gọi ngay. Nó cần một **hợp đồng đã được khai báo và xác minh trước**: thao tác nào được phép, phương thức Java nào xử lý, chính xác kiểu tham số/kiểu trả về, quy tắc parse/validation, đối tượng đích và chính sách lỗi.

Sau bài này, bạn có thể:

1. Thiết kế **registry/allowlist** ánh xạ tên lệnh công khai thành một method được tin cậy.
2. Xác minh hợp đồng lúc khởi tạo bằng `Class.getMethod(name, parameterTypes)`, kiểu trả về và class khai báo.
3. Ánh xạ input dạng chuỗi thành `Object[]` theo **parser tường minh cho từng tham số**.
4. Kiểm tra số lượng, phạm vi dữ liệu và điều kiện nghiệp vụ; phân loại lỗi trước/sau lời gọi.
5. Gọi target bằng `Method.invoke(target, args)` và mở `InvocationTargetException` đúng cách.
6. Kiểm thử đường đi thành công, input không hợp lệ, thao tác bị cấm, thiếu đối số và lỗi từ target.

Bài sử dụng **Java 17+**, chỉ cần JDK. Hợp đồng “đã xác thực” ở đây nghĩa là **metadata và quy tắc gọi đã được chương trình kiểm chứng ở quá trình khởi tạo**. Việc này không tự thay thế xác thực danh tính hoặc phân quyền người dùng nếu công cụ được đưa ra HTTP/RPC.

## 2. Thiết kế một hợp đồng có thể kiểm tra

Một hợp đồng gọi phương thức nên mô tả tối thiểu:

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| **Alias** | Tên thao tác công khai được chấp nhận | `sum` |
| **Target class** | Lớp dịch vụ chứa hành vi cho phép | `Service.class` |
| **Java method name** | Phương thức triển khai cố định | `sum` |
| **Parameter types** | Danh sách kiểu tham số **đúng thứ tự** | `int.class, int.class` |
| **Return type** | Kiểu trả về cần có | `int.class` |
| **Argument parsers** | Luật chuyển từng input thành đối tượng Java | `Integer.parseInt` + kiểm tra miền |
| **Allowed target** | Instance được tạo/quản lý bởi ứng dụng | `new Service()` |
| **Error policy** | Phân biệt lỗi request, contract và nghiệp vụ | `IllegalArgumentException` / exception từ target |

Luồng thực hiện:

```text
Đăng ký hợp đồng TIN CẬY tại startup
  -> resolve Method theo tên + kiểu tham số xác định trước
  -> xác minh class, quyền public, kiểu trả về và số parser
  -> lưu Method vào registry bất biến

Nhận request: alias + raw arguments
  -> tìm trong allowlist
  -> kiểm tra số lượng đối số
  -> dùng parser từng vị trí; kiểm tra cú pháp, miền giá trị
  -> tạo Object[] đã chuyển đổi
  -> Method.invoke(target, converted)
  -> trả kết quả hoặc phân loại exception
```

Có hai biên giới tin cậy phải tách rời:

- **Định nghĩa hợp đồng** do mã ứng dụng hoặc cấu hình quản trị đã kiểm tra quyết định. Nó quy định những gì hệ thống *có khả năng* thực thi.
- **Yêu cầu của caller** chỉ được chọn alias trong danh sách và cung cấp dữ liệu. Caller không được tự thêm method, chọn class tùy ý, đặt `setAccessible(true)` hay định nghĩa parser bằng code truyền vào từ request.

Nếu caller đến từ mạng hoặc có nhiều vai trò, cần **kiểm tra quyền của caller đối với alias** trước khi invoke; allowlist không tự xác định ai được dùng thao tác.

## 3. Vì sao phải xác minh Method trước khi gọi?

Java hỗ trợ tra cứu chính xác bằng:

```java
Method method = Service.class.getMethod("sum", int.class, int.class);
```

`Class.getMethod` lấy method `public` có tên và dãy kiểu tham số tương ứng; khác với chỉ tìm theo tên. Method overloaded có thể cùng tên nhưng khác parameter types, vì vậy một hợp đồng chỉ theo tên không đủ.

Nên kiểm tra thêm:

```java
if (method.getDeclaringClass() != Service.class
        || method.getReturnType() != int.class
        || !Modifier.isPublic(method.getModifiers())) {
    throw new IllegalStateException("Contract mismatch");
}
```

Hai đoạn trên là **mảnh code minh họa** đặt trong ngữ cảnh có `Service`, `Method`, `Modifier` và imports phù hợp; chương trình chạy hoàn chỉnh nằm ở mục 5.

Trong thiết kế cố định ở đây, yêu cầu `getDeclaringClass() == Service.class` nhằm từ chối method được kế thừa không chủ đích. Ứng dụng khác có thể **chủ ý** cho phép inherited method nếu ghi điều đó trong hợp đồng. Các ràng buộc này cũng phải phù hợp với cách đăng ký interface, generic bridge method hoặc proxy của framework nếu dùng chúng.

Không nên gọi `clazz.getMethods()` rồi chọn method đầu tiên trùng tên: thứ tự từ API không phải cơ chế giải quyết overload đáng tin cậy, và có thể lộ ra hành vi chưa được cho phép.

Một điểm dễ bỏ qua: `getMethod` có thể trả về method `public` của lớp không được phép gọi trong ngữ cảnh module/accessibility. Trong thực tế, **khả năng tìm Method** không bảo đảm **có thể invoke** với mọi module/target. Ví dụ này đặt class/method `public`, trong cùng ứng dụng, nên không cần phá đóng gói bằng `setAccessible`.

## 4. Chuyển đổi đối số theo vị trí bằng quy tắc rõ ràng

Input dạng `List<String>` hoặc `String[]` cần được parse sang kiểu Java đã khai báo, ví dụ:

| Tham số | Input thô | Kiểu đích | Quy tắc |
| --- | --- | --- | --- |
| `left` | `"7"` | `int` | `Integer.parseInt` và miền `0..1000` |
| `right` | `"5"` | `int` | Như `left` |
| `text` | `"go"` | `String` | Không null/rỗng/trắng; độ dài tối đa 20 |
| `times` | `"3"` | `int` | `Integer.parseInt` và miền `1..3` |

Parser xử lý đầu vào, còn reflection chịu trách nhiệm đưa các giá trị đã parse vào method. Khi gọi `Method.invoke`, kiểu `int` ở `Object[]` được biểu diễn bằng `Integer`; reflection có thể unbox hợp lệ khi tham số phương thức là `int`. Nhưng nó **không tự** parse chuỗi `"7"` thành số nguyên.

Chính sách cần nói rõ:

- `null` khác chuỗi `"null"` hoặc `""`; không tự thay bằng giá trị mặc định khi không được yêu cầu.
- `Integer.parseInt` có thể ném `NumberFormatException`, một subclass của `IllegalArgumentException`, cho cú pháp sai hoặc số ngoài phạm vi `int`.
- Một giá trị đã parse thành `int` **vẫn có thể vi phạm nghiệp vụ**, ví dụ tổng lớn hơn ngưỡng cho phép.
- Không tự trim, đổi chữ hoa/thường, áp locale hay parse định dạng khác nếu contract không cho phép.
- Converter nên có giới hạn dữ liệu và báo **vị trí tham số + kiểu mong đợi**, tránh trả raw input nhạy cảm trực tiếp trong thông báo lỗi.

## 5. Chương trình Java 17+ hoàn chỉnh

Tạo tệp `ContractInvocationDemo.java`. Ví dụ không phụ thuộc thư viện ngoài. Nó dùng một `Map<String, Plan>` bất biến chứa hai lệnh `sum` và `label`; một `Plan` lưu Method đã kiểm tra và parser tương ứng từng vị trí.

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.List;
import java.util.Map;

public final class ContractInvocationDemo {
    @FunctionalInterface
    interface Parser {
        Object parse(String raw);
    }

    static final class BusinessRuleException extends RuntimeException {
        BusinessRuleException(String message) {
            super(message);
        }
    }

    public static final class Service {
        public int sum(int left, int right) {
            int total = Math.addExact(left, right);
            if (total > 1_500) {
                throw new BusinessRuleException("sum exceeds 1500");
            }
            return total;
        }

        public String label(String text, int times) {
            return text.repeat(times);
        }
    }

    static final class Plan {
        private final String alias;
        private final Method method;
        private final Parser[] parsers;

        Plan(String alias, String methodName, Class<?> returnType,
             Class<?>[] argumentTypes, Parser[] parsers)
                throws ReflectiveOperationException {
            Method resolved = Service.class.getMethod(methodName, argumentTypes);
            if (resolved.getDeclaringClass() != Service.class
                    || !Modifier.isPublic(resolved.getModifiers())
                    || resolved.getReturnType() != returnType
                    || argumentTypes.length != parsers.length) {
                throw new IllegalStateException("invalid trusted contract: " + alias);
            }
            this.alias = alias;
            this.method = resolved;
            this.parsers = parsers.clone();
        }

        Object execute(Service target, List<String> raw) throws Throwable {
            if (raw.size() != parsers.length) {
                throw new IllegalArgumentException(alias + ": expected "
                        + parsers.length + " args, got " + raw.size());
            }
            Object[] converted = new Object[parsers.length];
            for (int i = 0; i < parsers.length; i++) {
                try {
                    converted[i] = parsers[i].parse(raw.get(i));
                } catch (IllegalArgumentException ex) {
                    throw new IllegalArgumentException(alias + ": argument " + i
                            + " expected " + method.getParameterTypes()[i].getTypeName(), ex);
                }
            }
            try {
                return method.invoke(target, converted);
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        }
    }

    static int parseAmount(String raw) {
        int value = Integer.parseInt(raw);
        if (value < 0 || value > 1_000) {
            throw new IllegalArgumentException("amount out of range");
        }
        return value;
    }

    static int parseTimes(String raw) {
        int value = Integer.parseInt(raw);
        if (value < 1 || value > 3) {
            throw new IllegalArgumentException("times out of range");
        }
        return value;
    }

    static String parseText(String raw) {
        if (raw == null || raw.isBlank() || raw.length() > 20) {
            throw new IllegalArgumentException("invalid text");
        }
        return raw;
    }

    static Map<String, Plan> register() throws ReflectiveOperationException {
        return Map.of(
                "sum", new Plan("sum", "sum", int.class,
                        new Class<?>[]{int.class, int.class},
                        new Parser[]{ContractInvocationDemo::parseAmount,
                                ContractInvocationDemo::parseAmount}),
                "label", new Plan("label", "label", String.class,
                        new Class<?>[]{String.class, int.class},
                        new Parser[]{ContractInvocationDemo::parseText,
                                ContractInvocationDemo::parseTimes}));
    }

    public static void main(String[] args) throws Throwable {
        Map<String, Plan> allowlist = register();
        Service target = new Service();

        System.out.println(call(allowlist, target, "sum", List.of("7", "5")));
        System.out.println(call(allowlist, target, "label", List.of("go", "3")));

        try {
            call(allowlist, target, "getClass", List.of());
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        try {
            call(allowlist, target, "sum", List.of("7"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        try {
            call(allowlist, target, "sum", List.of("abc", "5"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        try {
            call(allowlist, target, "label", List.of("go", "9"));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
        try {
            call(allowlist, target, "sum", List.of("900", "900"));
        } catch (BusinessRuleException ex) {
            System.out.println("business: " + ex.getMessage());
        }
    }

    static Object call(Map<String, Plan> allowlist, Service target,
                       String alias, List<String> raw) throws Throwable {
        Plan plan = allowlist.get(alias);
        if (plan == null) {
            throw new IllegalArgumentException("unsupported command");
        }
        return plan.execute(target, raw);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac ContractInvocationDemo.java
java ContractInvocationDemo
```

**Stdout chính xác** (đã kiểm chứng khi chạy chương trình trên JDK):

```text
12
gogogo
rejected: unsupported command
rejected: sum: expected 2 args, got 1
rejected: sum: argument 0 expected int
rejected: label: argument 1 expected int
business: sum exceeds 1500
```

### Đọc code theo đường đi của một request

1. `register()` được gọi lúc khởi tạo, dùng các tên method, kiểu tham số và kiểu trả về **được hard-code bởi ứng dụng**. `Service.class.getMethod` tra cứu đúng chữ ký. Nếu method không tồn tại, `NoSuchMethodException` khiến khởi tạo thất bại. Nếu return/declaring class sai hoặc số parser không khớp, `IllegalStateException` từ chối hợp đồng.
2. `Map.of(...)` tạo map không sửa được, nên caller không thể thêm alias `getClass` sau đó. `Plan` clone mảng parser, giúp tránh mã bên ngoài thay đổi mảng parser sau đăng ký.
3. `call(...)` tìm alias từ allowlist. `"getClass"` không có trong registry dù `Service` kế thừa `Object.getClass`, nên trả `unsupported command`.
4. `execute(...)` kiểm tra arity trước khi parse. Lệnh `sum` với chỉ một giá trị bị từ chối ngay, không cố gán giá trị mặc định.
5. Mỗi `Parser` áp dụng luật cho một tham số. Dữ liệu `"abc"` không parse thành `int`; dữ liệu `"9"` vượt giới hạn số lần lặp cho phép. Hai lỗi được thêm ngữ cảnh alias, vị trí, kiểu đích mà không lộ nguyên chuỗi đầu vào.
6. `method.invoke(target, converted)` gọi **đối tượng dịch vụ thật**, không gọi chính proxy hay phương thức được chọn từ tên người dùng.
7. Nếu `Service.sum` ném `BusinessRuleException` do tổng vượt 1500, reflection bọc nó trong `InvocationTargetException`; handler lấy `getCause()` để caller nhận đúng lỗi nghiệp vụ. Lỗi mapping được xử lý **trước khi target chạy**.

Trong ví dụ, miền `parseAmount` là `0..1000`, do đó `Math.addExact` không tràn `int`; nó vẫn thể hiện cách tránh overflow khi bài toán số học có phạm vi lớn hơn. Mức giới hạn 1500 chỉ dùng minh họa quy tắc nghiệp vụ.

### Hạn chế được tuyên bố của ví dụ

- `List.of(...)` trong `main` không cho phần tử null. Đầu vào thực tế có thể null/missing, nên tầng nhận request phải quyết định chính sách cho hai trường hợp đó trước khi gọi plan.
- Ví dụ nhận request trong code, không mở HTTP endpoint và không xây hệ thống authentication/authorization. Nếu là API nhiều người dùng, phải kiểm tra caller/role và quyền trên từng alias.
- `Plan.execute` không chặn `target == null` hoặc lỗi target không phù hợp, vì code chỉ tạo `Service` đúng kiểu. Công cụ tổng quát cần kiểm tra target trước khi invoke.
- Ví dụ chỉ đăng ký hai method, không xử lý varargs, generic DTO, optional values hay phương thức asynchronous. Những khả năng đó cần hợp đồng và converter riêng.

## 6. Lỗi ở từng giai đoạn và cách phân loại

Đừng gộp tất cả thành một `catch (Exception)` rồi báo “sai dữ liệu”. Phân chia:

| Giai đoạn | Lỗi điển hình | Ý nghĩa |
| --- | --- | --- |
| Startup / xác minh contract | `NoSuchMethodException` | Method không tồn tại với chữ ký đã khai báo |
| Startup / xác minh contract | `IllegalStateException` | Return type, declaring class hoặc số parser không đúng |
| Dispatch | Alias không có trong allowlist | Lệnh không được hỗ trợ hoặc không được cho phép |
| Mapping | Sai arity, số không hợp lệ, null không đúng | Request không phù hợp schema |
| Reflection invocation | `IllegalAccessException`, `IllegalArgumentException` | Quyền truy cập hoặc receiver/argument không phù hợp |
| Business execution | `InvocationTargetException` bọc cause của target | Phương thức đã chạy và tự ném exception |

Chỉ bắt `InvocationTargetException` ở tầng invoke để lấy nguyên nhân nghiệp vụ:

```java
try {
    return method.invoke(target, converted);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
}
```

Đây là một mảnh code nằm trong phương thức khai báo `throws Throwable`. Không giả định mọi `IllegalArgumentException` đều đến từ parser: `Method.invoke` cũng có thể phát sinh `IllegalArgumentException` khi receiver/argument không tương thích. Nếu target ném `IllegalArgumentException`, nó là **cause** trong `InvocationTargetException`, giúp phân biệt nguồn phát sinh.

Với HTTP API, giai đoạn mapping có thể tương ứng response `400 Bad Request`; từ chối vì thiếu quyền thường là `403 Forbidden`; lỗi contract/khởi tạo là lỗi hệ thống. Đây là hướng ánh xạ phụ thuộc thiết kế giao thức, không phải hành vi tự động của Reflection. Không nên gửi nguyên stack trace hoặc giá trị nhạy cảm cho caller.

## 7. Những điểm cần mở rộng khi làm công cụ thực tế

### 7.1. Phân quyền và giới hạn thao tác

Allowlist ràng buộc **những lệnh tồn tại**, còn authorization xác định **ai được chạy lệnh nào**. Trước khi `call`:

```text
Caller identity -> kiểm quyền thao tác alias -> kiểm quota/rate limit
               -> kiểm contract + validate input -> execute
```

Không nhận tên class, đường dẫn package, method name hoặc flag `setAccessible` từ client để tăng quyền. Nếu dùng registry lấy từ database/cấu hình, phải xác minh tính toàn vẹn và nguồn tin cậy của cấu hình trước khi tạo kế hoạch gọi.

Các lời gọi target có side effect (ghi DB, gửi thông báo, xóa dữ liệu) cần idempotency, transaction và authorization tùy hệ thống. Reflection không làm lời gọi trở nên an toàn hoặc có thể tự động retry.

### 7.2. Overload và chọn Method chính xác

Nếu `Service` có `save(int)` và `save(String)`, chỉ tên `"save"` không xác định overload. Hãy đăng ký hợp đồng kèm parameter types **cụ thể**, ví dụ:

```java
Method numericSave = Service.class.getMethod("save", int.class);
```

Đây là mảnh code minh họa giả định `Service` có phương thức `public save(int)`; phương thức đó **không được khai báo trong chương trình ở mục 5**. Nếu muốn chọn overload theo dữ liệu runtime, cần quy tắc ưu tiên và phát hiện trường hợp mơ hồ. Không chọn method đầu tiên từ `getMethods()`.

### 7.3. Generic, varargs, null và validation

- `getParameterTypes()` cung cấp kiểu sau **type erasure**; để parse `List<String>` hoặc DTO generic cần schema hoặc `getGenericParameterTypes()` kèm converter tương ứng.
- Varargs như `send(String... values)` có kiểu tham số cuối là `String[]` ở reflection. Cần dựng mảng đúng kiểu và đưa vào mảng arguments theo vị trí; ví dụ ở trên không tự mở rộng varargs.
- Tham số primitive không thể nhận null. Wrapper/reference có thể nhận null ở mức Reflection nhưng schema hoặc nghiệp vụ có thể cấm. Phải phân biệt **missing**, **null** và chuỗi `"null"`.
- Parse thành công không bảo đảm dữ liệu hợp lệ về nghiệp vụ: ví dụ parse được số lượng âm nhưng schema có thể cấm; `sum` còn có ràng buộc tổng vượt ngưỡng.
- Giới hạn độ dài, số lượng phần tử, độ sâu dữ liệu lồng nhau và timeout tác vụ nếu request không đáng tin.

### 7.4. Không lạm dụng setAccessible hoặc quét tất cả phương thức

Chỉ vì có thể dùng `getDeclaredMethods()` hoặc `setAccessible(true)` không có nghĩa đó là cách hợp lệ để xây công cụ gọi phương thức. Chúng có thể vượt qua thiết kế đóng gói, đụng ranh giới JPMS module, và làm bề mặt thao tác không còn được kiểm soát.

Nếu mục tiêu là một API/plugin có hợp đồng công khai, ưu tiên **interface rõ ràng, registry command** hoặc annotation được xác minh ở startup. Reflection hữu ích khi cần động hóa dispatch, nhưng không thay thế thiết kế API có kiểu và kiểm soát quyền.

## 8. Kế hoạch kiểm thử cho công cụ

Kiểm thử cần bảo đảm **hợp đồng được xác minh**, **mapper không gọi target khi input sai**, và **sai quyền/command không chạy method khác**.

| Ca kiểm thử | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Hợp lệ `sum` | `sum("7", "5")` | `12` |
| Hợp lệ `label` | `label("go", "3")` | `gogogo` |
| Alias không đăng ký | `getClass()` | Từ chối, không thực hiện reflection invoke |
| Sai số lượng | `sum("7")` | Lỗi số tham số; không gọi target |
| Sai format | `sum("abc", "5")` | Lỗi argument 0, expected int |
| Vượt miền parser | `label("go", "9")` | Lỗi argument 1 |
| Lỗi nghiệp vụ | `sum("900", "900")` | Target ném `BusinessRuleException`, giữ cause |
| Hợp đồng sai | `sum` khai báo return `String` | Startup fail trước khi nhận request |
| Method không tồn tại | Tên/signature không khớp | Startup fail bằng `NoSuchMethodException` |
| Kiểu receiver sai | Gọi instance method trên object không phù hợp | Bị ngăn khi kiểm target hoặc reflection báo lỗi |
| Đầu vào null/missing | `null` hoặc thiếu trường | Áp chính sách schema, không thay mặc định ngầm |
| Lỗi bảo mật | Caller không có quyền dùng alias | Bị từ chối trước mapping/invoke |

Có thể ghi log các sự kiện `alias, result status, duration, error code`; hạn chế log raw input và stack trace ở kênh dành cho người dùng. Benchmark và cache Method chỉ nên thực hiện sau khi hành vi đúng và quyền được bảo đảm.

## 9. Bài tập mở rộng

**Bài 1 — Thêm lệnh an toàn.** Thêm `multiply(int,int)`, đăng ký alias `multiply` với hai parser kiểm phạm vi và kiểu trả về `int`. Xác minh cả câu lệnh hợp lệ và lỗi overflow bằng `Math.multiplyExact` nếu muốn minh họa lỗi số học.

**Bài 2 — Kiểm tra quyền.** Tạo map `role -> allowed aliases` rồi chặn trước `call`. Viết test chứng minh user chỉ có quyền `label` không thể chạy `sum` kể cả khi biết alias.

**Bài 3 — Enum và ngày tháng.** Thêm một method nhận `LocalDate` hoặc enum chỉ định; đăng ký converter tường minh. Kiểm thử format ISO đúng/sai và enum constant không tồn tại.

**Bài 4 — Lỗi target.** Tạo method cố tình ném checked exception được khai báo; xác minh caller nhận nguyên nhân nghiệp vụ qua `InvocationTargetException.getCause()`, không nhầm với lỗi parser.

**Bài 5 — Null/missing.** Thay `List.of` bằng lớp request có thể biểu diễn missing/null/string. Định nghĩa rõ required, optional và default, kiểm tra trước reflection invocation.

**Bài 6 — Contract thay đổi.** Đổi kiểu trả về của method nhưng giữ metadata đăng ký cũ, chạy lại ứng dụng. Kết quả đúng là **startup fail**, thay vì đợi request người dùng đầu tiên mới phát hiện hợp đồng lệch.

## 10. Câu hỏi tự kiểm tra

1. **Vì sao không cho caller gửi tên class/method bất kỳ?** Vì như vậy input đang điều khiển tập hành vi được phép gọi; registry tin cậy phải giới hạn thao tác.
2. **Tại sao kiểm tra return type dù `getMethod` chỉ tìm theo parameter types?** Vì hợp đồng có thể yêu cầu một kiểu trả về cụ thể, và method thực tế có thể đã thay đổi.
3. **`Method.invoke` có parse `"7"` thành `int` không?** Không. Parser phải làm việc đó trước, rồi reflection mới có thể unbox `Integer` thành `int`.
4. **Nếu caller chọn alias `getClass` không đăng ký thì sao?** Bị từ chối, dù `getClass()` thực sự tồn tại trên `Object`.
5. **Lỗi từ target và lỗi chuyển đổi khác gì?** Lỗi chuyển đổi xảy ra trước khi invoke; lỗi target chạy qua `InvocationTargetException` và cần lấy cause.
6. **Allowlist có thay thế authentication/authorization không?** Không. Allowlist quyết định các thao tác *được hệ thống hỗ trợ*; quyền caller vẫn phải được kiểm tra riêng.
7. **Tại sao không chọn overload chỉ bằng tên method?** Vì có thể có nhiều chữ ký khác nhau; cần parameter types hoặc quy tắc giải quyết mơ hồ tường minh.

## 11. Điểm cần nhớ

Một công cụ gọi method có kiểm soát nên đi theo trình tự **khai báo hợp đồng tin cậy → xác minh đúng Method → đăng ký alias được phép → kiểm tra quyền caller → parse/validate từng đối số → gọi target → phân loại kết quả/ngoại lệ**.

Reflection cung cấp cơ chế thực thi động; hợp đồng và quy tắc ánh xạ quyết định hành vi nào được phép. Hãy ưu tiên fail-fast ở startup cho hợp đồng sai, trả lỗi rõ ràng cho input sai, bảo toàn nguyên nhân ngoại lệ nghiệp vụ và kiểm thử mọi đường từ chối trước khi đưa công cụ ra hệ thống thật.

Tài liệu Java 17:

- [Class.getMethod](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getMethod(java.lang.String,java.lang.Class...))
- [Method.invoke](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
- [Modifier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html)