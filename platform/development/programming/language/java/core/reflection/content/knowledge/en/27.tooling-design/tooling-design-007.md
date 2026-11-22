# Xác thực kiểu và khả năng truy cập trước khi chạy hàng loạt bằng Java Reflection

Một công cụ batch dùng Reflection có thể nhận nhiều class/method từ cấu hình. Nếu vừa tìm thấy đã `invoke`, mục thứ bảy sai chữ ký có thể bị phát hiện **sau khi sáu mục trước đã tạo side effect**. Bài này xây bước **preflight toàn lô**: kiểm tra contract, receiver, chữ ký, quyền truy cập và đầu vào; tạo kế hoạch đã xác thực rồi mới chạy.

Preflight chỉ chặn những lỗi có thể phát hiện sớm. Nó không bảo đảm method đích không ném lỗi, không tự cung cấp transaction hay rollback và không thay thế authorization tại thời điểm thực thi. Các phần dưới tập trung vào độ chính xác của kiểm tra `isAssignableFrom`, `canAccess`, và cách giữ plan/caller nhất quán.

## 1. Bài toán: tránh thực thi nửa chừng vì lỗi có thể phát hiện trước

Giả sử một batch nhận ba bước:

1. `TextNormalizer.normalize(String)` trả về `String`.
2. `EmailValidator.validate(String)` trả về `String`.
3. `ReportExporter.export(int)` nhưng runner sẽ truyền `String`.

Cách thực thi ngay khi duyệt:

```text
for từng mục:
    tìm method từ metadata
    gọi method ngay
    nếu lỗi thì dừng
```

Khi mục thứ ba sai chữ ký, chương trình mới phát hiện lỗi sau khi hai mục đầu đã chạy. Hậu quả có thể là gửi email, ghi file, thay đổi DB hoặc phát sinh sự kiện mà không thể đảo ngược dễ dàng.

Cách **lập kế hoạch trước khi gọi**:

```text
[Input/cấu hình]
       |
       v
[Tra cứu class, method, constructor]
       |
       v
[Kiểm tra kiểu + chữ ký + receiver + quyền truy cập]
       |
       +---- Có lỗi? ----> [Từ chối cả lô, báo mục lỗi, chưa invoke]
       |
       v
[Tạo danh sách lời gọi đã xác thực]
       |
       v
[Thực thi theo chính sách: tuần tự / song song / retry / transaction]
       |
       v
[Thu thập kết quả và xử lý lỗi runtime]
```

**Nguyên tắc:** lỗi cấu hình hoặc mismatch Reflection có thể biết trước nên được phát hiện trước lời gọi đầu tiên. Lỗi bên trong code người dùng, race condition, I/O, timeout hoặc thay đổi hệ thống vẫn phải xử lý ở pha thực thi.

## 2. Các tầng kiểm tra cần có

| Tầng | Điều cần chứng minh | API gợi ý | Nếu sai |
| --- | --- | --- | --- |
| Kiểu đầu vào | Giá trị không `null`; class thuộc nhóm được phép | `Objects.requireNonNull`, `Class.isInstance`, allowlist | Từ chối item |
| Quan hệ kế thừa / interface | Class là một implementation của contract cần thiết | `RequiredType.class.isAssignableFrom(candidateClass)` | Từ chối item |
| Metadata thành viên | Method/constructor tồn tại và được chọn duy nhất | `getMethod`, `getDeclaredMethod`, `getDeclaredMethods`, `getDeclaredConstructor` | Thiếu/trùng thì từ chối |
| Chữ ký | Số lượng và kiểu tham số, return type, static/instance, varargs khớp contract | `getParameterTypes`, `getReturnType`, `Modifier`, `isVarArgs` | Từ chối trước `invoke` |
| Quyền truy cập | Caller có thể gọi method với receiver thực tế không? | `Method.canAccess(receiver)` | Từ chối hoặc áp dụng chính sách mở quyền có kiểm soát |
| Quy tắc nghiệp vụ | Class, package, annotation, hành động có được phép chạy không? | allowlist, registry, annotation được giữ tại runtime, quyền người dùng | Từ chối dù Java reflection có thể gọi |
| Kế hoạch thực thi | Mọi mục được xác thực trước khi side effect bắt đầu | danh sách bất biến chứa `target` và `Method` | Không tạo kế hoạch nếu có lỗi |

Quan trọng: **“có thể truy cập theo ngôn ngữ Java” không đồng nghĩa “được phép chạy theo nghiệp vụ”**. Một method `public` có thể hợp lệ với Reflection nhưng vẫn nguy hiểm nếu nhận từ cấu hình không đáng tin cậy. Phải xác thực cả quyền và danh sách chức năng được cho phép.

## 3. Xác thực kiểu: hiểu đúng `isInstance`, `isAssignableFrom` và chữ ký

### 3.1. Kiểu đối tượng thực tế

- `Expected.class.isInstance(value)` kiểm tra một **đối tượng** có phải instance của kiểu yêu cầu không; với `null` kết quả là `false`.
- `Expected.class.isAssignableFrom(Candidate.class)` kiểm tra một **kiểu** có thể gán vào biến khai báo `Expected` hay không, kể cả quan hệ extends/implements.
- Hướng gọi không được đảo: `Runnable.class.isAssignableFrom(MyRunnable.class)` có thể đúng, nhưng `MyRunnable.class.isAssignableFrom(Runnable.class)` thường sai.
- Khi chỉ cần kiểm tra một đối tượng theo interface có sẵn, `value instanceof MyInterface` hoặc `Expected.class.isInstance(value)` thường rõ nghĩa hơn.

Ví dụ:

```java
interface Task {}
class EmailTask implements Task {}

boolean a = Task.class.isAssignableFrom(EmailTask.class); // true
boolean b = EmailTask.class.isAssignableFrom(Task.class); // false
boolean c = Task.class.isInstance(new EmailTask());       // true
```

Khi định chạy nhiều plugin, hãy định nghĩa contract ổn định như interface marker, base class hoặc registry, rồi kiểm tra contract trước khi tìm thành viên động. Trường hợp API nghiệp vụ đã có interface với phương thức phù hợp, **gọi trực tiếp qua interface thường đơn giản và an toàn kiểu hơn Reflection**; chỉ dùng Reflection cho phần khám phá/cấu hình động thật sự cần.

### 3.2. Kiểu tham số và return type

Phương thức cùng tên không nhất thiết cùng chữ ký:

```java
void process(String text) {}
void process(Integer number) {}
String process(String text, int retry) { return text; }
```

Đoạn trên chỉ minh họa overload hợp lệ; runner yêu cầu `process(String)` trả `String` thì phải kiểm tra **cả parameter types lẫn return type**, bởi Reflection không tự buộc kiểu kết quả cho kế hoạch:

```java
// Giả sử method là java.lang.reflect.Method đã tìm được.
boolean takesExactlyOneString =
        java.util.Arrays.equals(
                method.getParameterTypes(),
                new Class<?>[]{String.class});
boolean returnsString = method.getReturnType() == String.class;
```

Trong contract có chữ ký **chính xác**, so sánh `Class<?>` bằng `==` là đúng vì đối tượng `Class` đại diện cho runtime type; điều này khác so sánh nội dung đối tượng dữ liệu.

Trong contract cho phép kiểu con, sử dụng `isAssignableFrom` theo chiều phù hợp và xét cả primitive, boxing/unboxing, `null`, varargs. Đừng dùng `String.class.isAssignableFrom(paramType)` một cách vô thức: API nhận `CharSequence` vẫn có thể tiếp nhận chuỗi `String`, dù hướng kiểm tra đó trả `false`.

Với generic như `List<String>`, `getParameterTypes()` nhìn thấy `List.class` do **type erasure**. Nếu batch cần ràng buộc generic, có thể xem `getGenericParameterTypes()` nhưng metadata generic **không tự kiểm tra từng phần tử lúc runtime**; cần validator riêng.

### 3.3. Static / instance, receiver và varargs

`Method.invoke` có cách truyền receiver khác nhau:

| Dạng thành viên | Receiver cho `invoke` / `canAccess` | Cần kiểm tra |
| --- | --- | --- |
| Instance method | Một object đúng kiểu declaring class hoặc subtype | Receiver không `null`, `declaringClass.isInstance(receiver)` |
| Static method | `null` | `Modifier.isStatic(method.getModifiers())` |
| Constructor | Không dùng `Method.invoke`; dùng `Constructor.newInstance` | Kiểu, đối số và quyền constructor |
| Varargs method | Có tham số mảng cuối | `method.isVarArgs()` và chính sách đóng gói đối số |

Ví dụ, `canAccess(null)` không hợp lệ với một instance method. Đối với static method, `canAccess(nonNullReceiver)` cũng sai. Hãy xác định loại thành viên trước khi gọi kiểm tra quyền.

**Varargs** cần thiết kế rõ: ở Reflection, `Method.invoke` có tham số varargs của chính API đó, và method đích có thể là varargs. Nếu runner không hỗ trợ, hãy từ chối `isVarArgs() == true`; nếu có hỗ trợ thì chủ động đóng gói thành mảng đúng kiểu để tránh truyền sai.

### 3.4. Kiểm tra một hay nhiều method khi quét annotation

Đối với công cụ quét `@BatchAction`:

- `getDeclaredMethods()` chỉ lấy method **khai báo trực tiếp trên class đó**; bao gồm non-public, không tự tìm inherited methods.
- `getMethods()` trả các method `public` (kể cả được kế thừa), theo chính sách khác.
- Khi quét annotation, cần quyết định áp dụng annotation trên declared hay inherited method, xử lý overload ra sao, có cho nhiều entry point trên cùng class không.
- Chú ý method `synthetic` hoặc `bridge` do compiler sinh, nhất là class generic. Có thể loại bỏ bằng `isSynthetic()`/`isBridge()` khi quét entry point.
- Annotation dùng để tra cứu tại runtime phải được khai báo `@Retention(RetentionPolicy.RUNTIME)`; mặc định không giữ đủ cho kiểu quét này.

Nếu contract yêu cầu **đúng một** method có annotation, cần xác nhận `count == 1` trước khi thực thi. Không chọn ngẫu nhiên “method đầu tiên” vì thứ tự `getDeclaredMethods()` không phải contract có thứ tự ổn định.

## 4. Xác thực khả năng truy cập: `canAccess` và giới hạn JPMS

Tìm được metadata không có nghĩa là gọi được member.

### 4.1. `public` là điều kiện đơn giản, chưa phải toàn bộ câu chuyện

`Modifier.isPublic(method.getModifiers())` chỉ nhìn access modifier của method. Với method thực tế, khả năng gọi còn phụ thuộc declaring class, package, module và caller.

`Method.canAccess(receiver)` hỏi quyền truy cập **từ class đang gọi API kiểm tra đó**, với receiver cụ thể. Nên gọi nó trong cùng lớp/tầng executor sau này thực hiện `invoke`:

```java
// Giả sử method là instance method và target đã xác minh đúng kiểu.
if (!method.getDeclaringClass().isInstance(target)
        || !method.canAccess(target)) {
    throw new IllegalArgumentException("Method không truy cập được");
}
```

Không nên áp dụng `canAccess` của một helper ở module khác rồi mặc nhiên cho rằng executor có quyền như vậy. Với phương thức static, phải truyền `null`. `canAccess` không chạy nội dung method đích.

### 4.2. `getMethod` và `getDeclaredMethod` khác nhau

- `getMethod("run", String.class)` tìm method `public` theo tên và kiểu tham số, bao gồm method phù hợp được kế thừa.
- `getDeclaredMethod("run", String.class)` tìm method khai báo trong class hiện tại, bất kể private/protected/package-private/public; **không** tự bao gồm inherited.
- Cả hai có thể ném `NoSuchMethodException`; nên chuyển thành lỗi cấu hình có ngữ cảnh rõ “class nào, method nào, chữ ký nào”.

Dùng `getDeclaredMethod` để tìm private method **không cấp thêm quyền** để gọi nó.

### 4.3. `trySetAccessible`, `setAccessible` và module

`trySetAccessible()` có thể bật chế độ bỏ qua access checks **nếu** môi trường/module cho phép; nếu không cho phép, thường trả `false`. `setAccessible(true)` có thể ném `InaccessibleObjectException` khi không thể mở quyền. Đây không phải các API để “phá” mọi ranh giới module.

Với module có tên (Java Platform Module System):

- `exports p` cho phép API public trong package `p` được truy cập thông thường bởi module đọc nó.
- `opens p` hoặc `opens p to other.module` cho phép các cơ chế deep reflection phù hợp trên package đó.
- `privateLookupIn` với `MethodHandles.Lookup` cũng phải tuân theo các điều kiện access/module; không có quyền tự động chỉ vì biết tên method.

Với **công cụ chạy batch**, mặc định nên từ chối nếu `canAccess` trả `false`, và mô tả cách sửa bằng public API, module descriptor hoặc plugin contract. Chỉ cân nhắc `trySetAccessible` khi đó là chính sách đã được chủ động phê duyệt, đối tượng nằm trong phạm vi được tin cậy, và có kiểm soát quyền rõ ràng.

## 5. Ví dụ Java 17+: xác thực cả lô rồi mới thực thi

Ví dụ tạo một batch runner đọc danh sách object theo contract `Job`, tìm đúng **một** method `@BatchAction` trên mỗi class, yêu cầu chữ ký chính xác `public String execute(String)` và chỉ thực thi **sau khi mọi bước đã được xác minh**.

Đặc điểm thiết kế:

- `preflight` chỉ kiểm tra metadata và tạo `List<Invocation>`; **không gọi** business method.
- Một method có return type `int` sẽ bị từ chối trước khi bất kỳ `execute` nào chạy.
- `List.copyOf` tạo danh sách kế hoạch bất biến về cấu trúc; điều này **không** làm các object mục tiêu trở thành immutable.
- `runs` minh chứng rõ lô sai không có side effect từ business method.

Tạo file **`BatchPreflightDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class BatchPreflightDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface BatchAction {}

    public interface Job {}

    public static class Upper implements Job {
        @BatchAction
        public String execute(String text) {
            runs++;
            return text.toUpperCase(Locale.ROOT);
        }
    }

    public static class Prefix implements Job {
        @BatchAction
        public String execute(String text) {
            runs++;
            return "OK: " + text;
        }
    }

    public static class Wrong implements Job {
        @BatchAction
        public int execute(String text) {
            runs++;
            return text.length();
        }
    }

    private record Invocation(Object target, Method method) {}
    private static int runs;

    private static List<Invocation> preflight(List<?> targets) {
        List<Invocation> plan = new ArrayList<>();
        for (Object target : targets) {
            if (target == null) {
                throw new IllegalArgumentException("Đối tượng null");
            }
            Class<?> type = target.getClass();
            if (!Job.class.isAssignableFrom(type)) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + " không implements Job");
            }
            List<Method> methods = Arrays.stream(type.getDeclaredMethods())
                    .filter(m -> m.isAnnotationPresent(BatchAction.class))
                    .toList();
            if (methods.size() != 1) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + " phải có đúng một @BatchAction");
            }
            Method method = methods.get(0);
            if (!Modifier.isPublic(method.getModifiers())
                    || Modifier.isStatic(method.getModifiers())
                    || method.isSynthetic()
                    || method.isBridge()
                    || method.isVarArgs()) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + ".execute phải là instance method public hợp lệ");
            }
            if (!Arrays.equals(method.getParameterTypes(),
                    new Class<?>[]{String.class})) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + ".execute phải nhận String");
            }
            if (method.getReturnType() != String.class) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + ".execute phải trả về String");
            }
            if (!method.getDeclaringClass().isInstance(target)
                    || !method.canAccess(target)) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + ".execute không thể truy cập");
            }
            plan.add(new Invocation(target, method));
        }
        return List.copyOf(plan);
    }

    private static void execute(List<Invocation> plan, String input)
            throws IllegalAccessException {
        for (Invocation step : plan) {
            try {
                String result = (String) step.method().invoke(
                        step.target(), input);
                System.out.println(step.target().getClass().getSimpleName()
                        + " -> " + result);
            } catch (InvocationTargetException ex) {
                throw new IllegalStateException("Lỗi khi thực thi "
                        + step.target().getClass().getSimpleName(),
                        ex.getCause());
            }
        }
    }

    public static void main(String[] args) throws IllegalAccessException {
        try {
            List<Invocation> invalid =
                    preflight(List.of(new Upper(), new Wrong()));
            execute(invalid, "xin chào");
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối lô: " + ex.getMessage());
        }
        System.out.println("Số lần đã chạy: " + runs);

        List<Invocation> valid =
                preflight(List.of(new Upper(), new Prefix()));
        System.out.println("Preflight: " + valid.size() + " bước hợp lệ");
        execute(valid, "xin chào");
        System.out.println("Số lần đã chạy: " + runs);
    }
}
```

Biên dịch và chạy:

```bash
javac BatchPreflightDemo.java
java BatchPreflightDemo
```

Kết quả chạy:

```text
Từ chối lô: Wrong.execute phải trả về String
Số lần đã chạy: 0
Preflight: 2 bước hợp lệ
Upper -> XIN CHÀO
Prefix -> OK: xin chào
Số lần đã chạy: 2
```

Giải thích:

1. `Wrong.execute(String)` có return type `int`. `getReturnType() != String.class` nên `preflight` ném `IllegalArgumentException` **trước** `execute(invalid, ...)`. Biến `runs` vẫn bằng 0.
2. Lô thứ hai gồm `Upper` và `Prefix`: mỗi class có đúng một method được đánh dấu annotation với signature đã yêu cầu, và `canAccess(target)` trả `true`.
3. Chỉ sau khi `preflight` trả đầy đủ kế hoạch, `execute` mới gọi `Method.invoke` từng bước. Kết quả đúng với chương trình đã biên dịch và chạy bằng JDK.
4. Trường hợp này cố ý dùng các nested class công khai cùng chương trình để ví dụ độc lập, nên không minh họa lỗi truy cập giữa hai named modules. Khi tích hợp plugin thật, hãy xác minh `canAccess` trong môi trường triển khai đó.
5. Ví dụ coi các method có annotation **khai báo trực tiếp** là entry point, không xét method được kế thừa. Nếu muốn hỗ trợ inherited methods, phải thay đổi chính sách tra cứu rõ ràng.

## 6. Khi dữ liệu cấu hình là tên class hoặc tên method

Một số công cụ nhận cấu hình kiểu:

```text
implementation = "com.acme.plugins.ExportJob"
method         = "execute"
parameterType  = "java.lang.String"
```

Đây là **dữ liệu đầu vào cần xác thực**, không phải giấy phép gọi phương thức bất kỳ.

Trình tự gợi ý:

1. **Xác thực người yêu cầu, nguồn cấu hình và allowlist**: chỉ cho những plugin/class/action được chấp nhận; không cho người dùng tùy ý nhập class hệ thống hoặc method nguy hiểm.
2. **Nạp class có kiểm soát**: chọn `ClassLoader` phù hợp; `Class.forName(name, false, loader)` có thể nạp class mà chưa yêu cầu khởi tạo ngay. Đừng hiểu bước nạp class là hoàn toàn không có rủi ro.
3. **Kiểm tra class**: `expectedInterface.isAssignableFrom(candidate)`, không abstract/interface nếu cần tạo instance, loại bỏ class trái chính sách.
4. **Kiểm tra constructor**: tìm chữ ký phù hợp bằng `getDeclaredConstructor(...)`; kiểm tra quyền với `constructor.canAccess(null)`. Nếu tạo instance bằng constructor, cần biết bản thân `newInstance` có thể chạy code và có side effect; tùy công cụ, nên trì hoãn tạo instance tới pha execution hoặc thiết kế nhà máy plugin riêng.
5. **Kiểm tra method**: tên, overload, tham số, return type, modifier, annotation, receiver, quyền truy cập, context module.
6. **Xây dựng kế hoạch**: lưu metadata và đối số đã chuyển đổi/hợp lệ. Đánh dấu nguồn gốc cấu hình để báo lỗi chính xác.
7. **Execute**: chạy theo thứ tự xác định, xử lý failure policy, audit/log, transaction khi cần.

**Lưu ý về constructor:** Nếu muốn thật sự “không side effect trước khi mọi mục qua preflight”, không nên gọi constructor của plugin trong quá trình kiểm tra: constructor hoặc static initializer có thể thực hiện hành vi nghiệp vụ. Ví dụ ở mục 5 nhận **instance đã tạo sẵn** và chỉ bảo đảm chưa gọi method `@BatchAction` trước khi kiểm tra đủ; quá trình tạo những instance ấy nằm ngoài preflight.

### Nên kiểm tra trước bao nhiêu?

Preflight nên xác minh các điều kiện **có thể quyết định từ metadata và input**: thiếu method, sai chữ ký, quyền access không phù hợp, input không thể chuyển đổi, plugin chưa đăng ký, cấu hình xung đột, method bị cấm. Nó không thể dự đoán mọi exception của code đích hay tình trạng tài nguyên lúc thực thi.

Nếu batch liên quan file/DB/network, có thể bổ sung bước kiểm tra resource và quyền nghiệp vụ, nhưng đó cũng chỉ là kiểm tra tại một thời điểm. Tài nguyên có thể biến mất ngay sau khi kiểm tra; executor vẫn phải xử lý lỗi đầy đủ.

## 7. Preflight không phải transaction và cũng không loại bỏ mọi lỗi Reflection

### Những gì có thể sai sau khi kiểm tra thành công

- Method có thể ném exception do logic bên trong; `Method.invoke` bọc exception từ target trong `InvocationTargetException`. Muốn xem lỗi gốc dùng `getCause()`.
- Receiver bị thay đổi trạng thái hoặc resource không còn hợp lệ.
- Method `public` vẫn có thể ném `IllegalArgumentException` do đối số truyền tại thời điểm chạy khác với bản đã xác thực.
- Ứng dụng có thể chạy sai thứ tự, bị hủy, timeout hoặc thực thi trùng khi retry.
- Class loader/redeployment tạo ra class cùng tên nhưng **khác identity**; không coi chuỗi tên class là bảo chứng rằng object thuộc đúng `Class<?>` đã kiểm tra.
- Các instance có thể giữ trạng thái nội bộ thay đổi trong lúc chờ. Kế hoạch bất biến chỉ khóa danh sách bước, không khóa thế giới bên ngoài.

Vì vậy, khi batch cập nhật dữ liệu cần có chính sách rõ ràng: **fail-fast**, ghi nhận lỗi từng item, retry có giới hạn, idempotency key, bù trừ (*compensation*) hoặc transaction database nếu thích hợp. Transaction nhiều tài nguyên phân tán không được tạo ra tự động chỉ vì preflight hoàn tất.

### Phân loại lỗi để báo cáo chính xác

| Tại bước nào | Lỗi/API thường gặp | Cách báo phù hợp |
| --- | --- | --- |
| Tìm class | `ClassNotFoundException` hoặc lỗi liên quan class loading | Nêu tên/loader và cấu hình sai |
| Tìm member | `NoSuchMethodException`, `NoSuchFieldException` | Nêu tên và signature mong muốn |
| Quyền truy cập | `canAccess` trả `false`, `IllegalAccessException`, `InaccessibleObjectException` khi xin mở | Nêu class, package, module và contract quyền |
| Gọi sai đối số | `IllegalArgumentException`, `WrongMethodTypeException` khi dùng API method handle | Nêu kiểu thực tế và kiểu yêu cầu |
| Code đích ném lỗi | `InvocationTargetException` | Phân biệt lỗi business, log cause gốc |
| Không thể tạo instance | `InstantiationException`, lỗi constructor, class abstract | Nêu loại instance cần tạo và nguyên nhân |

Không nên in toàn bộ dữ liệu đầu vào nhạy cảm vào log; khi có batch nhiều mục, báo vị trí, mã bước và nguyên nhân đủ để sửa.

## 8. Thiết kế kế hoạch đã kiểm tra cho hệ thống thật

Đối với batch lớn, xây dựng kiểu dữ liệu ghi rõ thông tin của mỗi bước, ví dụ:

```java
// Đoạn phác thảo mô hình, không phải chương trình độc lập.
record CheckedCall(
        String stepId,
        Object target,
        java.lang.reflect.Method method,
        Object[] arguments) {}
```

Mỗi `CheckedCall` có thể mang thêm thông tin về policy, thứ tự, mục tiêu log, context quyền, deadline và kết quả validation. Chỉ đưa vào kế hoạch cuối khi mọi điều kiện hợp lệ. Trường hợp cần xử lý nhiều lỗi cùng lúc, gom tất cả diagnostics trong một lần quét rồi từ chối chạy nếu có ít nhất một lỗi; tránh sửa lỗi từng mục bằng chu kỳ chạy–fail–sửa tốn kém.

Các điểm cần cân nhắc:

- **Snapshot cấu hình**: không cho một thread khác thay danh sách method/arguments sau khi preflight. Nếu argument là object mutable, cần snapshot hoặc biện pháp đồng bộ phù hợp; `List.copyOf` không đóng băng trạng thái object bên trong.
- **Đúng caller của `canAccess`**: kiểm tra quyền tại chính tầng executor (hoặc thiết kế quyền tương đương), vì quyền Java có ngữ cảnh class/module.
- **Sự khác biệt giữa metadata và chính sách**: annotation biểu thị ý định đăng ký, nhưng allowlist/authorization mới quyết định người dùng cụ thể được chạy.
- **Các lời gọi lặp lại**: cache metadata hoặc plan khi thích hợp; vô hiệu hóa cache khi plugin đổi class loader/phiên bản. `Method` có thể tái sử dụng trên nhiều receiver đúng kiểu.
- **Thứ tự xác định**: đừng dựa vào thứ tự phản hồi từ `getDeclaredMethods()`; sắp xếp hoặc lấy thứ tự từ cấu hình rõ ràng.
- **Giới hạn tài nguyên**: xác minh kích thước lô, timeout, độ dài input, số luồng, quyền file/network trước khi chạy.
- **Quan sát và báo lỗi**: diagnostic phải chỉ đúng bước nào, expected/actual signature, quyền truy cập và trạng thái đã/chưa thực thi.

Nếu bài toán chỉ yêu cầu các thao tác chuẩn hóa và kiểm tra qua interface thống nhất, có thể thiết kế `List<Processor>` với lời gọi `process(...)` trực tiếp. Reflection phù hợp hơn khi framework phải **khám phá và ghép nối metadata động**, chứ không phải để thay thế mọi lời gọi có kiểu rõ ràng.

## 9. Checklist trước khi bấm “Run batch”

1. Đã xác thực nguồn cấu hình và giới hạn danh sách class/method được phép?
2. Mọi class/receiver/constructor đúng contract và không có `null` hoặc kiểu sai?
3. Method được tìm theo chính sách rõ ràng (declared/public/inherited, annotation, overload)?
4. Đã kiểm tra **chính xác** số/kiểu tham số, return type, modifier, varargs, bridge/synthetic?
5. Quyền thực sự từ executor đã được xác minh bằng `canAccess` với receiver đúng loại; JPMS có cho phép?
6. Mọi đối số đã được xác thực hoặc chuyển đổi an toàn, không để lỗi có thể phát hiện trước dồn sang execute?
7. Đã kiểm tra **tất cả bước** trước lời gọi nghiệp vụ đầu tiên? Kế hoạch có bị thay đổi sau preflight không?
8. Có xử lý `InvocationTargetException`, timeout, retry, lỗi từng bước và side effects đã xảy ra?
9. Cần transaction, idempotency hoặc rollback/compensation để bảo đảm tính toàn vẹn không?
10. Log có đủ ngữ cảnh để sửa cấu hình và không lộ dữ liệu nhạy cảm?

### Câu hỏi tự kiểm tra

- Vì sao `getDeclaredMethod` tìm được một method private chưa chứng minh `invoke` sẽ được phép?
- `isAssignableFrom` phải gọi theo chiều nào để kiểm tra plugin thực thi một interface?
- Nếu method yêu cầu `String` nhưng runner truyền `Integer`, nên phát hiện ở pha nào?
- `canAccess(null)` phù hợp với static method hay instance method?
- Nếu preflight chạy xong nhưng lời gọi bước thứ 4 ném exception, hệ thống có tự rollback các bước trước không?
- Trường hợp constructor plugin có side effect, tạo instance trong preflight có còn giữ được cam kết “chưa chạy nghiệp vụ” không?

### Tham khảo chính thức

- [`Class` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isInstance`, `isAssignableFrom`, tìm method và constructor.
- [`Method` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): chữ ký, `invoke` và metadata.
- [`AccessibleObject` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible` và giới hạn access.
- [`InvocationTargetException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): lỗi được bọc khi target method hoặc constructor ném exception.
- [Java Language Specification `6.6](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): quy tắc access control.
