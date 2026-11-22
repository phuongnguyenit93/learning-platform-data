# Đổi tên, obfuscation và thay đổi nội bộ có thể làm hỏng liên kết theo chuỗi trong Java Reflection

Một điểm mạnh của Java Reflection là có thể tìm lớp, field, constructor hoặc method **theo tên khi chương trình chạy**. Ví dụ `Class.forName("com.example.OrderService")` và `type.getMethod("submit", String.class)` cho phép cấu hình linh hoạt mà không cần tham chiếu trực tiếp đến mọi implementation khi biên dịch.

Điểm yếu tương ứng là **chuỗi tên trở thành một hợp đồng ngầm ở runtime**. Đổi tên lớp, chuyển package, đổi tên method, thay chữ ký, rút gọn/obfuscate bytecode hoặc sửa cấu trúc nội bộ có thể khiến cấu hình cũ ngừng hoạt động. Compiler thường không biết một chuỗi trong JSON, YAML, database hoặc annotation tùy ý đang được dùng để tham chiếu đến phần tử Java nào, nên lỗi chỉ xuất hiện **khi đường chạy Reflection được thực thi**.

Bài học tập trung vào việc nhận diện hợp đồng ngầm đó, giải thích cơ chế lỗi và thiết kế cách liên kết ổn định hơn.

## 1. Liên kết theo kiểu ở compile time và liên kết theo chuỗi ở runtime

### Gọi có kiểm tra kiểu

```java
OrderService service = new OrderService();
service.submit("A-100");
```

Đây là đoạn minh họa giả định `OrderService` có method `submit(String)`. Compiler phải resolve kiểu và chữ ký. Nếu đổi method từ `submit` sang `placeOrder` nhưng chưa sửa nơi gọi, lỗi thường xuất hiện ngay khi biên dịch lại mã nguồn.

### Gọi qua Reflection với chuỗi

```java
Class<?> type = Class.forName("com.example.OrderService");
Object service = type.getDeclaredConstructor().newInstance();
Method method = type.getMethod("submit", String.class);
method.invoke(service, "A-100");
```

Đây là **đoạn minh họa**, không phải một chương trình độc lập; mã thật cần import, xử lý exception và kiểm tra quyền truy cập. Chuỗi `"com.example.OrderService"` và `"submit"` được kiểm tra tại runtime. Nếu lớp đổi thành `com.example.orders.OrderProcessor` hoặc method đổi thành `placeOrder`, compiler **không nhất thiết phát hiện** các chuỗi đã lỗi thời.

Sơ đồ:

```text
Mã/config có chuỗi "com.example.OrderService" + "submit"
                         |
                         v
               Runtime Reflection
                  Class.forName
                   getMethod
                     invoke
                         |
             +-----------+-----------+
             |                       |
     Tên/chữ ký vẫn đúng      Tên/chữ ký đã đổi
             |                       |
       Gọi thành công         Lỗi khi chạy:
                         ClassNotFoundException
                         NoSuchMethodException
                         ... 
```

**Không phải mọi thao tác Reflection đều phụ thuộc chuỗi.** `SomeType.class`, `obj.getClass()` và `Method` đã lấy sẵn không bắt đầu bằng việc tra cứu tên chuỗi. Tuy nhiên, các kiểu đó vẫn phải thỏa yêu cầu tương thích runtime nếu phần implementation/bytecode bị thay đổi.

## 2. Những thay đổi nào làm liên kết dễ gãy?

| Thay đổi | Điểm dễ hỏng | Hậu quả thường gặp |
|---|---|---|
| Đổi tên class | `Class.forName("pkg.OldType")` | `ClassNotFoundException` |
| Di chuyển package | Chuỗi tên nhị phân cũ `pkg.OldType` | Không tìm được lớp, trừ khi có lớp tương thích giữ tên cũ |
| Đổi tên method | `getMethod("oldName", ...)` | `NoSuchMethodException` |
| Đổi kiểu hoặc số tham số | `getMethod("run", String.class)` | Không resolve được chữ ký cũ |
| Đổi constructor | `getDeclaredConstructor(...)` | `NoSuchMethodException` hoặc lỗi instantiation |
| Đổi tên field | `getDeclaredField("oldField")` | `NoSuchFieldException` |
| Chuyển field/method lên superclass | `getDeclaredField`/`getDeclaredMethod` trên lớp cũ | Không còn phần tử **declared** tại nơi tra cứu |
| Đổi mức visibility | `getMethod` chỉ tra cứu public method; `invoke` còn chịu kiểm tra truy cập | Không tìm được hoặc không có quyền gọi |
| Đổi tên sau obfuscation | Metadata runtime đổi thành tên đã bị biến đổi | Chuỗi gốc không khớp với tên runtime |
| Shrink/loại bỏ code hoặc metadata | Plugin/annotation/method chỉ được truy cập động | Thành viên vắng mặt hoặc annotation không còn quan sát được |
| Thay đổi module/package accessibility | Method còn tồn tại nhưng reflection bị ràng buộc | `IllegalAccessException` / `InaccessibleObjectException` |

**Quan trọng:** `Class.getMethod(name, parameterTypes...)` tìm **public method** (kể cả thành viên được kế thừa theo API), trong khi `getDeclaredMethod(...)` tìm method khai báo ngay trên class, kể cả non-public. Hai hàm không tương đương. Chữ ký tra cứu khớp chính xác các kiểu tham số qua `Class<?>`: `int.class` và `Integer.class` khác nhau; `String.class` và `Object.class` cũng khác nhau.

Giả sử method gốc:

```java
public void execute(String id) {}
```

Sau refactor:

```java
public void execute(Object id) {}
```

Một lời gọi `getMethod("execute", String.class)` vẫn thất bại dù `String` là một `Object`; Reflection không dùng quy tắc overload resolution từ mã nguồn để tự tìm `execute(Object)`.

## 3. Obfuscation và shrinking thực sự làm gì?

Các công cụ như ProGuard/R8 hoặc các bộ biến đổi bytecode khác có thể, tùy cấu hình:

- **Đổi tên** class, package, field, method thành tên ngắn hoặc khó đọc.
- **Loại bỏ** class/method bị xem là không được dùng.
- **Biến đổi hoặc loại bỏ metadata/attributes** mà Reflection hoặc framework dựa vào.
- Áp dụng quy tắc **keep** cho lớp và thành viên cần giữ tên/hình dạng; một số công cụ có khả năng thích nghi các chuỗi tên trong trường hợp hỗ trợ, nhưng không thể mặc định mọi chuỗi cấu hình/database đều được cập nhật.

Ví dụ trước obfuscation có `com.example.plugins.ReportPlugin` với method `generate()`. Sau biến đổi, binary name có thể thành `a.b.C`, method có thể thành `a()`. Khi chạy mã:

```java
Class.forName("com.example.plugins.ReportPlugin");
```

runtime tìm **tên được truyền vào**; nó không tự suy ra `a.b.C` là hậu thân của tên cũ.

Phân biệt ba yếu tố:

1. **Bytecode đang được chạy:** chứa tên runtime thực tế sau khi transform.
2. **Chuỗi/metadata sử dụng để tìm:** có thể vẫn là tên cũ trong file cấu hình, annotation, dữ liệu lưu lâu dài hay literal.
3. **Mapping/keep rules của build:** chỉ dẫn công cụ biến đổi giữ hoặc ánh xạ những phần nhất định.

Vì vậy, câu “thư viện bị obfuscate thì Reflection luôn hỏng” là quá mạnh. Nó **có thể vẫn hoạt động** nếu tên cần tìm được giữ nguyên, metadata cần thiết được bảo toàn hoặc các liên kết được cập nhật đúng theo khả năng của công cụ. Ngược lại, việc ứng dụng chạy bình thường ở build debug **không chứng minh** build release đã shrink/obfuscate vẫn hoạt động.

**Các dạng metadata khác cũng cần xét:** annotation phục vụ discovery phải có `@Retention(RetentionPolicy.RUNTIME)` mới được đọc ở runtime; shrinker phải bảo toàn lớp/thành viên và metadata cần thiết theo đúng cấu hình cụ thể. Parameter name (nếu ứng dụng dựa vào) còn phụ thuộc cách biên dịch như `-parameters` và metadata sau biến đổi; không được coi nó là ID nghiệp vụ bền vững.

## 4. Ví dụ Java 17+: refactor method làm hỏng lookup cũ, ID ổn định vẫn dùng được

Ví dụ này giả định một phiên bản cũ có `OldInvoiceService.charge(int)`. Sau refactor, implementation hiện tại đổi thành `InvoiceService.capture(int)`. Ta vẫn có thể biên dịch mã nguồn mới vì tên cũ chỉ nằm trong chuỗi, nhưng tra cứu bằng chuỗi cũ sẽ thất bại tại runtime.

Đồng thời, ta dùng annotation `@Operation(id = "invoice.charge")` như **ID logic ổn định**, tách contract công khai khỏi tên Java của implementation.

Lưu toàn bộ chương trình thành **`StringBindingDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.HashMap;
import java.util.Map;

public class StringBindingDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Operation {
        String id();
    }

    public static class InvoiceService {
        @Operation(id = "invoice.charge")
        public String capture(int amount) {
            return "Captured " + amount;
        }
    }

    static Map<String, Method> discover(Class<?> type) {
        Map<String, Method> registry = new HashMap<>();

        for (Method method : type.getDeclaredMethods()) {
            Operation metadata = method.getAnnotation(Operation.class);
            if (metadata == null) {
                continue;
            }

            if (!Modifier.isPublic(method.getModifiers())
                    || method.getParameterCount() != 1
                    || method.getParameterTypes()[0] != int.class
                    || method.getReturnType() != String.class) {
                throw new IllegalArgumentException(
                        "Invalid operation signature: " + method.getName());
            }

            if (registry.putIfAbsent(metadata.id(), method) != null) {
                throw new IllegalArgumentException(
                        "Duplicate operation ID: " + metadata.id());
            }
        }

        return Map.copyOf(registry);
    }

    public static void main(String[] args) throws Exception {
        InvoiceService service = new InvoiceService();

        // Kiểm tra kiểu khi biên dịch: tên mới được tham chiếu trực tiếp.
        System.out.println("Typed: " + service.capture(150));

        // Chuỗi method từ phiên bản cũ vẫn biên dịch được, nhưng lookup hỏng.
        try {
            InvoiceService.class.getMethod("charge", int.class);
        } catch (NoSuchMethodException e) {
            System.out.println("Old method: NoSuchMethodException");
        }

        // Chuỗi binary name cũ trong cấu hình cũng không được tự đổi.
        try {
            Class.forName("StringBindingDemo$OldInvoiceService");
        } catch (ClassNotFoundException e) {
            System.out.println("Old class: ClassNotFoundException");
        }

        // API công khai tham chiếu ID logic, không cần biết tên method.
        Method action = discover(InvoiceService.class).get("invoice.charge");
        if (action == null) {
            throw new IllegalStateException("Missing operation");
        }

        System.out.println("Stable ID: " + action.invoke(service, 150));
        System.out.println("Resolved method: " + action.getName());
    }
}
```

Biên dịch và chạy (Java 17+):

```bash
javac --release 17 -encoding UTF-8 StringBindingDemo.java
java StringBindingDemo
```

**Stdout kỳ vọng:**

```text
Typed: Captured 150
Old method: NoSuchMethodException
Old class: ClassNotFoundException
Stable ID: Captured 150
Resolved method: capture
```

**Giải thích:**

1. Lời gọi `service.capture(150)` được compiler kiểm tra theo API mới. Nếu bạn lại viết `service.charge(150)`, mã nguồn mới sẽ không biên dịch vì method đã đổi tên.
2. Chuỗi `"charge"` vẫn là literal hợp lệ nên compiler không cảnh báo. `getMethod` chỉ tìm member theo đúng tên/chữ ký runtime và ném `NoSuchMethodException`.
3. Tên `StringBindingDemo$OldInvoiceService` không còn tồn tại: `Class.forName` không biết một lớp đã được đổi tên từ phiên bản trước.
4. Discovery tìm method theo annotation có ID logic `"invoice.charge"`; tên Java thật là `capture`. Hai tên phục vụ **hai mục đích** khác nhau.
5. ID trong annotation không phải “phép thuật chống obfuscation”: mã trên vẫn cần method/annotation được giữ lại và discover thành công sau quá trình biến đổi bytecode.

**Giới hạn của ví dụ:** Registry mới chỉ chứng minh liên kết qua ID, không tự cấp quyền gọi method. Ứng dụng thật cần kiểm soát quyền, schema input, target instance, phiên bản API và tính tương thích của ID. Mã ví dụ chạy trong unnamed module/classpath với method public và class public; các module có encapsulation chặt hơn cần cấu hình truy cập phù hợp.

## 5. Các giải pháp giảm phụ thuộc vào chuỗi tên nội bộ

### A. Dùng lời gọi và tham chiếu có kiểm tra kiểu

Khi không cần plugin động, ưu tiên API thường:

```java
InvoiceService service = new InvoiceService();
String output = service.capture(150);
```

Hoặc dùng method reference với functional interface:

```java
java.util.function.IntFunction<String> action = service::capture;
String output = action.apply(150);
```

Đây là **đoạn minh họa** dùng kiểu `InvoiceService` từ ví dụ trên. Compiler kiểm tra method đang tồn tại và chữ ký tương thích khi build. Refactor IDE thường có thể cập nhật usage được nhận diện như symbol; chuỗi tự do trong YAML/database vẫn cần migration riêng.

### B. Tách ID công khai ổn định khỏi tên implementation

Thay vì để cấu hình ghi tên nội bộ:

```yaml
# Liên kết giòn: đổi tên class hoặc method sẽ làm hỏng cấu hình
handlerClass: "com.example.billing.InvoiceService"
handlerMethod: "capture"
```

Một registry nội bộ có thể cung cấp ID:

```yaml
# Liên kết theo hợp đồng ứng dụng, do registry quyết định implementation
operationId: "invoice.charge"
```

Ứng dụng dịch `invoice.charge` thành handler được đăng ký. Người bảo trì có thể đổi tên hoặc cấu trúc class bên trong mà vẫn giữ ID này. **Điều kiện** là ID thực sự được quản trị như một contract ổn định, registry được dựng/kiểm tra đúng và không bị xóa/mất metadata sau khi đóng gói.

Các ID nghiệp vụ cũng có thể cần version như `invoice.charge.v2` nếu input/output hoặc ngữ nghĩa thay đổi không tương thích; đừng cố giữ một ID duy nhất khi nghĩa của action đã thay đổi căn bản.

### C. Dùng interface hoặc ServiceLoader khi phù hợp

Một interface Java công khai tạo contract có kiểm tra kiểu:

```java
public interface InvoiceOperation {
    String capture(int amount);
}
```

Đây là mảnh mã mô tả interface riêng, không phải phần bổ sung cần dán vào file demo ở trên. Với nhiều provider, `ServiceLoader<InvoiceOperation>` có thể khám phá implementations thông qua cấu hình provider/module đúng quy ước. Cơ chế này vẫn có **hợp đồng tên và packaging** trong provider configuration, nên cấu hình `META-INF/services` hoặc khai báo `provides ... with ...` cần được giữ/cập nhật đúng khi refactor và obfuscation.

### D. Keep rules và mapping khi bắt buộc dùng Reflection

Nếu framework yêu cầu tra cứu theo binary name hoặc tên method, cần ghi rõ những symbol/attributes là contract của Reflection; cấu hình shrinker/obfuscator cho **đúng phiên bản công cụ** để giữ chúng. Không nên giả định một quy tắc keep của công cụ này áp dụng y hệt sang công cụ khác.

Khi lưu class name hoặc method name ra database, file cấu hình hay event message, hãy lên kế hoạch migration và tương thích ngược: alias cho ID cũ, chuyển cấu hình, version schema hoặc thời gian chuyển tiếp. Giữ mapping obfuscation phục vụ phân tích stack trace và đối chiếu release, nhưng **mapping không tự sửa các chuỗi cũ** trong cơ sở dữ liệu.

## 6. Tên lớp, method và chữ ký: các bẫy riêng

### Binary name của nested class

Đối với nested class, tên mã nguồn dạng `Outer.Inner` có thể khác binary name `Outer$Inner`. Ví dụ:

```java
Class<?> type = Class.forName("StringBindingDemo$InvoiceService");
```

Trong ví dụ không có package, tên trên hợp lệ. Nếu chuyển class sang package, cần thêm package vào chuỗi. Chèn dấu `$` vào mọi dấu chấm là sai vì dấu chấm phân cách package vẫn phải giữ.

### Method overload và chữ ký

`getMethod("process", String.class)` và `getMethod("process", Object.class)` là **hai lookup khác nhau**. `getMethod` không chọn overload bằng khả năng tự động chuyển đổi tham số như lời gọi Java thông thường. Ngoài ra Reflection lookup không dùng **kiểu trả về** trong danh sách tham số tra cứu; thay đổi return type có thể cần kiểm tra thêm trước khi `invoke`/cast kết quả.

### Inherited, private và module

- `getMethod` trả public member theo hợp đồng API, có thể là method kế thừa.
- `getDeclaredMethod` tìm method khai báo trực tiếp; chuyển logic lên superclass có thể làm lookup này thất bại.
- `getDeclaredMethod` nhìn thấy method private nhưng không bảo đảm gọi được. `setAccessible(true)` có thể không được cho phép bởi module encapsulation, và không nên dùng như chiến lược sửa mọi lỗi thiết kế.

### Binary compatibility khác source compatibility

Một thư viện có thể được cập nhật trong khi client vẫn chạy bytecode **đã biên dịch trước đó**. Nếu xóa hoặc đổi tên method mà bytecode cũ vẫn tham chiếu trực tiếp đến method đó, lỗi linkage như `NoSuchMethodError` có thể xuất hiện (tùy thay đổi và quá trình resolve), khác với `NoSuchMethodException` do Reflection tra cứu bằng chuỗi.

Một bản sửa làm compile lại toàn bộ mã nguồn thành công **chưa đủ** để bảo đảm plugin, dữ liệu hoặc binary client phiên bản cũ còn chạy.

## 7. Kiểm thử bắt buộc ở đúng artifact runtime

Với thành phần có liên kết bằng chuỗi, unit test chỉ chạy trên mã nguồn chưa obfuscate thường bỏ sót lỗi. Một quy trình kiểm tra hiệu quả:

1. **Liệt kê các điểm liên kết động:** `Class.forName`, `getMethod`, `getDeclaredField`, tên provider, tên handler trong YAML/JSON/database, annotation-based discovery và serialization mapping.
2. **Phân loại contract:** symbol nào là chi tiết nội bộ có thể đổi, tên/ID nào được công bố cho plugin hoặc dữ liệu đã lưu.
3. **Refactor an toàn:** cập nhật tham chiếu kiểu; tìm trong configuration, resource và dữ liệu triển khai, không chỉ Java source. Với dữ liệu đã lưu, thực hiện migration có kiểm tra.
4. **Kiểm tra bản build sau shrink/obfuscation:** dùng chính JAR/AAB/artifact deploy, không chỉ debug build. Thực hiện discovery và gọi một tập hợp action đại diện.
5. **Kiểm tra chữ ký:** tên, parameter types, return type, visibility, annotation runtime, constructor, module access và các ngoại lệ.
6. **Kiểm tra tương thích:** chạy config/plugin/binary client ở phiên bản đã hỗ trợ; nếu có thay đổi contract thì đưa ra version/migration/alias rõ ràng.
7. **Theo dõi lỗi runtime:** log action ID, phiên bản artifact và nguyên nhân được phân loại, không log dữ liệu nhạy cảm hay giả định mọi lỗi Reflection đều là `ClassNotFoundException`.

Ví dụ assertion trong integration test (đoạn minh họa):

```java
Class<?> type = Class.forName("com.example.billing.InvoiceService");
Method method = type.getMethod("capture", int.class);
assert method.getReturnType() == String.class;
```

`assert` trong Java **mặc định có thể bị tắt** nếu JVM không chạy với `-ea`. Trong test thực tế hãy dùng assertion của JUnit và phải kiểm tra trên artifact đã biến đổi/đóng gói; chuỗi tên ở ví dụ chỉ là placeholder cho class của dự án.

## 8. Chẩn đoán sự cố khi liên kết theo chuỗi hỏng

| Lỗi | Gợi ý chẩn đoán |
|---|---|
| `ClassNotFoundException` | Binary name sai, package đổi, class loader không thấy lớp, class bị shrink/obfuscate |
| `NoSuchMethodException` | Sai tên, parameter types, dùng nhầm `getMethod` với `getDeclaredMethod`, method bị đổi/xóa |
| `NoSuchFieldException` | Field đổi tên hoặc không được khai báo tại class đang dùng `getDeclaredField` |
| `IllegalAccessException` | Method hiện diện nhưng caller không có quyền invoke theo luật access |
| `InaccessibleObjectException` | Không thể mở quyền truy cập phản chiếu do module encapsulation hoặc giới hạn khác |
| `InvocationTargetException` | Lookup thành công, nhưng **code được gọi** đã ném exception; đọc `getCause()` |
| `NoSuchMethodError` | Lỗi linkage của bytecode client/runtime không tương thích, khác lỗi lookup Reflection |
| `NullPointerException` khi tìm annotation | Có thể annotation vắng do retention không phải RUNTIME, metadata bị strip hoặc tra cứu sai chỗ; xác minh từng nguyên nhân |
| `ClassCastException` | Lookup có thể thành công nhưng kiểu instance hoặc return value không còn phù hợp |

**Đừng “sửa nhanh” bằng cách bắt mọi exception rồi im lặng bỏ qua.** Khi registry không tải được handler thiết yếu, nên báo lỗi tên/ID/phiên bản rõ và dừng cấu hình sai. Một lỗi `InvocationTargetException` cũng không có nghĩa tên method sai: có thể chính nghiệp vụ bị lỗi.

## 9. Cách chọn trong thiết kế lâu dài

| Nhu cầu | Cách ưu tiên |
|---|---|
| Gọi code biết tại compile time | Direct method call, interface, method reference |
| Chọn hành động theo tên nghiệp vụ từ client/config | Registry với **ID công khai ổn định** và schema có version |
| Khám phá plugin implementations | Interface/ServiceLoader hoặc registry rõ ràng, kiểm tra packaging |
| Framework buộc tra cứu tên class/method | Keep rules + runtime integration test với artifact phát hành |
| Dữ liệu cũ chứa tên Java | Migration/alias và kiểm tra tương thích ngược |
| Cần dùng Reflection nhưng tránh khởi tạo class sớm | `Class.forName(name, false, loader)` khi phù hợp, chỉ invoke sau bước kiểm tra |

Một thiết kế tốt giúp **internal refactor** vẫn linh hoạt nhưng có ranh giới rõ với các contract đã công bố ra ngoài. Tên nội bộ chỉ nên trở thành hợp đồng dài hạn khi có lý do chính đáng và có kiểm thử/migration tương ứng.

## 10. Tự kiểm tra

**Câu 1.** Vì sao IDE đổi tên `charge()` thành `capture()` có thể làm chương trình Reflection lỗi dù Java source vẫn biên dịch?

Vì literal `"charge"` được xử lý như dữ liệu chuỗi thông thường. `getMethod("charge", ...)` tra cứu tại runtime; compiler không xác minh chuỗi đó còn trỏ đến method thật.

**Câu 2.** Obfuscator luôn phá Reflection?

**Không.** Nếu symbol được keep, chuỗi được thích nghi đúng hoặc registry không phụ thuộc vào tên nội bộ đã đổi, Reflection vẫn có thể làm việc. Cần kiểm thử chính artifact đã transform.

**Câu 3.** ID `invoice.charge` trong annotation có bảo đảm chạy qua mọi bản build không?

**Không tự động.** Đó là hợp đồng logic do ứng dụng quản lý. Cần đảm bảo annotation runtime, method còn tồn tại, metadata được giữ, registry đăng ký thành công và caller được phân quyền.

**Câu 4.** `getMethod("run", String.class)` có tự tìm `run(Object)` nếu không có overload nhận `String`?

**Không.** Tra cứu dùng đúng kiểu tham số được truyền vào. Chữ ký API đã đổi thì phải cập nhật contract/adapter/config.

**Câu 5.** Vì sao test phải chạy trên bản release obfuscated thay vì chỉ trên classfile do `javac` tạo ra?

Vì chính bước shrink/obfuscation có thể đổi tên hoặc loại bỏ class, method, annotation và metadata, làm hành vi Reflection khác với bản debug.

## Tài liệu chuẩn

- Java SE 17 API: [`Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) — `forName`, `getMethod`, `getDeclaredMethod` và metadata.
- Java SE 17 API: [`Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html) — `invoke`, signature, lỗi truy cập và `InvocationTargetException`.
- Java SE 17 API: [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) — provider discovery dựa trên interface.
- Java Language Specification, chương 13 (Binary Compatibility); JVM Specification, chương 5 (Loading, Linking, Initialization).
- Tài liệu shrinker/obfuscator **đúng phiên bản và hệ sinh thái đang dùng** để xác định keep rules, retention của metadata và khả năng thích nghi resource/string.

**Ghi nhớ:** Liên kết bằng chuỗi trao đổi sự linh hoạt khi chạy lấy rủi ro gãy kết nối khi tên hoặc chữ ký nội bộ thay đổi. Hãy dùng contract có kiểm tra kiểu khi có thể, ID logic ổn định khi cần động, và kiểm thử chính artifact phát hành cùng cấu hình/dữ liệu thật.
