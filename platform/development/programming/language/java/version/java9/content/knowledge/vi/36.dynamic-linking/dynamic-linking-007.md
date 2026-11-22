# Phân biệt API liên kết động với một bộ thực thi ngôn ngữ cụ thể

## Mục tiêu

Java cung cấp các API cấp thấp trong `java.lang.invoke` để hỗ trợ liên kết và gọi phương thức động trên JVM. Các thành phần chính gồm `MethodHandle`, `MethodType`, `MethodHandles.Lookup`, `CallSite` và cơ chế bytecode `invokedynamic`.

Những API này là **cơ chế nền tảng**, không phải một bộ thực thi ngôn ngữ động hoàn chỉnh. Một language runtime như runtime của Groovy, JRuby hoặc một ngôn ngữ riêng chạy trên JVM phải tự định nghĩa ngữ nghĩa của ngôn ngữ: cách tìm phương thức, truy cập thuộc tính, chuyển kiểu, chọn overload, xử lý toán tử, báo lỗi và cache kết quả phân giải.

Cần phân biệt ba lớp:

1. **JVM:** cung cấp instruction, quy tắc liên kết, kiểm tra kiểu của call site và thực thi target.
2. **Dynamic-linking API:** cung cấp các đối tượng và công cụ để xây dựng target có kiểu, kết hợp method handle và quản lý call site.
3. **Language implementation/runtime:** quyết định một biểu thức của ngôn ngữ có nghĩa gì và target nào phải được gọi.

API liên kết động cho phép xây dựng một runtime; bản thân API không thay thế runtime đó.

## 1. Dynamic linking trong JVM là gì?

Liên kết động là quá trình xác định hành vi của một điểm gọi tại thời điểm chạy. Với bytecode `invokedynamic`, mỗi vị trí instruction có một dynamic call site riêng.

Khi JVM gặp một `invokedynamic` chưa được liên kết, JVM gọi bootstrap method được khai báo cho instruction đó. Bootstrap method nhận thông tin về bên gọi, tên thao tác và kiểu lời gọi, rồi trả về một `CallSite` chứa target `MethodHandle`.

Trình tự khái quát:

~~~text
Bytecode có invokedynamic
          |
          v
Call site chưa được liên kết
          |
          v
JVM gọi bootstrap method
          |
          +--> MethodHandles.Lookup của caller
          +--> Tên thao tác
          +--> MethodType của lời gọi
          +--> Các static bootstrap arguments (nếu có)
          |
          v
Bootstrap tạo MethodHandle target
          |
          v
Bootstrap trả về CallSite
          |
          v
JVM kiểm tra kiểu target và liên kết call site
          |
          v
Các lần gọi sau dùng target của CallSite
~~~

Một call site có kiểu được xác định bởi descriptor trong bytecode. Kiểu target của CallSite phải khớp chính xác với kiểu lời gọi đó. Nếu bootstrap không trả về CallSite hợp lệ hoặc target sai kiểu, quá trình liên kết thất bại và JVM báo `BootstrapMethodError`.

JVM cung cấp cơ chế liên kết và thực thi target. JVM không tự suy luận rằng một lời gọi có nghĩa là gọi method theo duck typing, tìm property động hay áp dụng quy tắc overload riêng của một ngôn ngữ.

## 2. Các thành phần của API java.lang.invoke

| Thành phần | Vai trò |
|---|---|
| `MethodType` | Mô tả kiểu trả về và danh sách kiểu tham số của lời gọi |
| `MethodHandle` | Tham chiếu có kiểu đến method, constructor, getter, setter hoặc thao tác tương tự; có thể gọi trực tiếp |
| `MethodHandles.Lookup` | Tạo MethodHandle sau khi kiểm tra quyền truy cập theo ngữ cảnh lookup |
| `MethodHandles` | Cung cấp factory và combinator để tìm, biến đổi hoặc ghép MethodHandle |
| `CallSite` | Giữ target MethodHandle gắn với một điểm gọi động |
| `invokedynamic` | Bytecode instruction dùng bootstrap method để liên kết call site |
| `SwitchPoint` | Hỗ trợ vô hiệu hóa một nhánh target đã được bảo vệ khi điều kiện cache thay đổi |

### MethodType

`MethodType` mô tả chữ ký lời gọi, gồm kiểu trả về và kiểu của từng tham số.

~~~java
MethodType type = MethodType.methodType(
        String.class,
        Object.class
);
~~~

Kiểu trên biểu diễn một lời gọi nhận `Object` và trả về `String`, tức `(Object)String`.

Descriptor này là hợp đồng kiểu của call site. Runtime có thể chọn target khác nhau theo đối tượng thực tế, nhưng mọi target được gắn vào cùng call site vẫn phải có kiểu phù hợp với descriptor.

### MethodHandle

`MethodHandle` là một tham chiếu có kiểu, có thể thực thi trực tiếp. Nó khác một chuỗi tên method cần tra cứu mỗi lần gọi.

Có thể tìm một static method bằng Lookup:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle handle = lookup.findStatic(
        TextOperations.class,
        "normalize",
        MethodType.methodType(String.class, String.class)
);
~~~

Lookup thực hiện kiểm tra truy cập tại lúc tạo handle. MethodHandle không phải cơ chế bỏ qua visibility, module boundary hoặc các quy tắc truy cập của Java.

`invokeExact` yêu cầu kiểu lời gọi tại điểm gọi khớp chính xác với MethodHandle. `invoke` cho phép các chuyển đổi kiểu được API hỗ trợ. Khi xây dựng runtime, nên xác định rõ descriptor và chỉ dùng `asType` hoặc các combinator khi thật sự cần chuyển đổi.

### MethodHandles.Lookup

Lookup đại diện cho quyền truy cập gắn với một lớp/ngữ cảnh cụ thể. Bootstrap method nhận Lookup của caller để runtime có thể thực hiện thao tác phân giải theo quyền truy cập được cấp.

Lookup không phải quyền truy cập toàn cục. Nếu runtime cố tìm một thành viên không được phép truy cập, thao tác tìm handle có thể thất bại. Module encapsulation và access control vẫn có hiệu lực.

### CallSite

`CallSite` là đối tượng giữ target MethodHandle. Ba implementation tiêu chuẩn thường gặp:

| Loại | Hành vi target | Khi phù hợp |
|---|---|---|
| `ConstantCallSite` | Target cố định sau khi tạo | Liên kết ổn định, không cần đổi target |
| `MutableCallSite` | Target có thể thay đổi như một field thông thường | Cần relink hoặc cập nhật chiến lược dispatch |
| `VolatileCallSite` | Target có semantics của volatile field | Target thay đổi và cần visibility giữa các thread theo volatile semantics |

Với `MutableCallSite`, thay đổi target bằng `setTarget` không tự bảo đảm mọi thread khác lập tức thấy target mới. Có thể gọi `MutableCallSite.syncAll(...)` khi cần công bố thay đổi cho các thread khác. Nếu cần visibility volatile cho các lần đọc target, xem xét `VolatileCallSite`.

## 3. Bootstrap method làm gì?

Bootstrap method là cầu nối giữa một instruction `invokedynamic` và logic liên kết của runtime.

Một bootstrap method thông dụng có dạng:

~~~java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String operationName,
        MethodType callSiteType
) throws ReflectiveOperationException {
    MethodHandle target = caller.findStatic(
            LanguageRuntime.class,
            operationName,
            callSiteType
    );

    return new ConstantCallSite(target);
}
~~~

Đây là ví dụ minh họa khi method được tìm thấy có thể truy cập từ Lookup của caller và có đúng kiểu `callSiteType`.

Khi instruction `invokedynamic` liên kết, JVM truyền vào:

- Lookup đại diện cho caller class.
- Tên thao tác được ghi trong call-site specifier.
- MethodType của lời gọi.
- Các static bootstrap argument nếu instruction có khai báo.

Bootstrap phải trả về một CallSite có target phù hợp với MethodType. Tên thao tác và các static argument là dữ liệu để runtime quyết định cách phân giải; JVM không tự hiểu ngữ nghĩa của các tên như `getProperty`, `invokeMethod` hay `plus`.

Gọi một method tên `bootstrap` trực tiếp từ Java chỉ là một method call bình thường. Bootstrap chỉ được JVM sử dụng theo cơ chế trên khi bytecode có instruction `invokedynamic` trỏ đến bootstrap method đó.

## 4. API liên kết động không phải bộ thực thi ngôn ngữ

Một bộ thực thi ngôn ngữ phải định nghĩa và triển khai các quy tắc riêng của ngôn ngữ. Ví dụ, với biểu thức:

~~~text
receiver.value(argument)
~~~

Một ngôn ngữ động có thể cần quyết định:

1. `receiver` có null hay không và lỗi tương ứng là gì.
2. Property hoặc method `value` được tra cứu trên class, prototype, meta-object hay extension nào.
3. Có method overload nào phù hợp với kiểu runtime của argument.
4. Có cần chuyển kiểu, boxing, unboxing hoặc coercion hay không.
5. Nếu không tìm thấy method, có gọi hook như `methodMissing` hoặc phát sinh lỗi ngôn ngữ hay không.
6. Kết quả phân giải có thể cache cho các lần gọi tiếp theo hay không.
7. Khi class, object shape hoặc meta-class thay đổi, cache cần được vô hiệu hóa thế nào.

`java.lang.invoke` không định nghĩa các quy tắc trên. Runtime của ngôn ngữ quyết định semantics, sau đó dùng MethodHandle, MethodType, CallSite và các combinator để hiện thực hóa quyết định đó.

| Công việc | JVM / dynamic-linking API | Language runtime |
|---|---|---|
| Biểu diễn chữ ký call site | MethodType | Chọn descriptor phù hợp cho thao tác ngôn ngữ |
| Tạo tham chiếu có kiểu để gọi | MethodHandle | Chọn method/operation theo quy tắc ngôn ngữ |
| Kiểm tra quyền truy cập | Lookup và JVM access rules | Áp dụng thêm visibility hoặc object model riêng nếu ngôn ngữ có |
| Liên kết điểm gọi | invokedynamic và bootstrap protocol | Viết bootstrap method và quyết định target |
| Thay target | CallSite, MutableCallSite, VolatileCallSite | Quyết định khi nào relink hoặc invalidate cache |
| Chuyển kiểu và overload | Các chuyển đổi được MethodHandle hỗ trợ | Định nghĩa coercion, overload và dispatch của ngôn ngữ |
| Lỗi ngôn ngữ | JVM truyền exception từ target | Chuyển lỗi thành exception/diagnostic theo semantics ngôn ngữ |

Một runtime có thể dùng `invokedynamic`, nhưng cũng có thể dùng MethodHandle trực tiếp, reflection, interpreter hoặc một tổ hợp nhiều kỹ thuật. Không có yêu cầu rằng mọi ngôn ngữ chạy trên JVM phải dùng cùng một kiến trúc.

## 5. Vai trò của compiler/front-end và runtime

Một language implementation thường có nhiều phần:

- **Parser/front-end:** đọc source, phân tích cú pháp và xây dựng biểu diễn chương trình.
- **Compiler hoặc bytecode generator:** chuyển biểu thức/ngữ nghĩa thành bytecode, có thể phát ra instruction `invokedynamic`.
- **Language runtime:** cung cấp object model, dispatch, conversion, method/property lookup, exception semantics và cache.
- **JVM:** xác minh và thực thi bytecode, liên kết dynamic call site qua bootstrap protocol, quản lý bộ nhớ và thread theo hợp đồng nền tảng.

Các phần này có thể nằm trong cùng một dự án hoặc được tách thành thư viện và module khác nhau. Điểm quan trọng là Java dynamic-linking API chỉ là một bộ công cụ cho phần liên kết và gọi; nó không tự cung cấp parser, compiler, type system hoặc object model của ngôn ngữ.

## 6. Caching và relinking là trách nhiệm của runtime

Tra cứu method/property theo tên và kiểu runtime ở mỗi lần gọi có thể tốn chi phí. Runtime thường cache kết quả phân giải ở call site.

Một cách triển khai phổ biến là tạo target có guard:

~~~text
Nếu receiver thuộc class/shape đã biết:
    gọi MethodHandle đã cache
Ngược lại:
    chạy fallback để phân giải lại
~~~

Các công cụ có thể dùng:

- `MethodHandles.guardWithTest` để tạo chuỗi kiểm tra điều kiện và chọn target.
- `MutableCallSite` để thay target sau khi runtime học được cách dispatch.
- `VolatileCallSite` khi cần semantics visibility volatile cho target thay đổi.
- `SwitchPoint` để bảo vệ cache và chuyển sang fallback sau khi metadata hoặc class state liên quan bị invalidated.

Ví dụ: runtime có thể cache rằng một receiver có class C gọi method `render` bằng handle H. Khi class C hoặc meta-class được mở rộng và quy tắc dispatch thay đổi, runtime vô hiệu hóa cache rồi phân giải lại. Quyết định cache lúc nào, điều kiện guard là gì và khi nào invalidation xảy ra thuộc về runtime, không phải JVM tự đoán.

Không nên dùng `MutableCallSite` như thể mọi cập nhật đều tự động có visibility xuyên thread. Cần thiết kế đồng bộ cho cache và target theo Java Memory Model.

## 7. Ví dụ hoàn chỉnh: xây một runtime nhỏ bằng API liên kết động

Ví dụ sau mô phỏng một ngôn ngữ nhỏ có quy tắc dispatch theo kiểu runtime:

- String được xử lý bằng quy tắc chuỗi.
- Integer được xử lý bằng quy tắc số.
- Kiểu khác đi vào fallback.
- Runtime có thể chuyển sang strict mode, chỉ chấp nhận String.

Ví dụ dùng MethodType, MethodHandle, Lookup, `guardWithTest`, MutableCallSite và `dynamicInvoker()`. Đây là cách sử dụng CallSite API trực tiếp từ Java; mã không tự phát sinh instruction bytecode `invokedynamic`.

Tệp `DynamicLinkingApiDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.util.Locale;

public class DynamicLinkingApiDemo {
    private static final MethodHandles.Lookup LOOKUP = MethodHandles.lookup();
    private static final MethodType CALL_TYPE =
            MethodType.methodType(String.class, Object.class);

    private static final MethodHandle IS_STRING =
            find("isString", MethodType.methodType(boolean.class, Object.class));
    private static final MethodHandle IS_INTEGER =
            find("isInteger", MethodType.methodType(boolean.class, Object.class));
    private static final MethodHandle STRING_RULE = find("stringRule", CALL_TYPE);
    private static final MethodHandle INTEGER_RULE = find("integerRule", CALL_TYPE);
    private static final MethodHandle FALLBACK_RULE = find("fallbackRule", CALL_TYPE);
    private static final MethodHandle STRICT_RULE = find("strictRule", CALL_TYPE);

    private static MethodHandle find(String name, MethodType type) {
        try {
            return LOOKUP.findStatic(DynamicLinkingApiDemo.class, name, type);
        } catch (ReflectiveOperationException error) {
            throw new ExceptionInInitializerError(error);
        }
    }

    private static boolean isString(Object value) {
        return value instanceof String;
    }

    private static boolean isInteger(Object value) {
        return value instanceof Integer;
    }

    private static String stringRule(Object value) {
        return "string:" + ((String) value).toUpperCase(Locale.ROOT);
    }

    private static String integerRule(Object value) {
        return "integer:" + (((Integer) value) + 1);
    }

    private static String fallbackRule(Object value) {
        return "fallback:" + String.valueOf(value);
    }

    private static String strictRule(Object value) {
        if (!(value instanceof String)) {
            throw new IllegalArgumentException("Only strings are accepted");
        }
        return "strict:" + ((String) value).toUpperCase(Locale.ROOT);
    }

    private static final class MiniLanguageRuntime {
        private final MutableCallSite callSite;
        private final MethodHandle invoker;

        MiniLanguageRuntime() {
            MethodHandle integerOrFallback =
                    MethodHandles.guardWithTest(IS_INTEGER,
                            INTEGER_RULE, FALLBACK_RULE);
            MethodHandle dispatcher =
                    MethodHandles.guardWithTest(IS_STRING,
                            STRING_RULE, integerOrFallback);

            callSite = new MutableCallSite(CALL_TYPE);
            callSite.setTarget(dispatcher);
            invoker = callSite.dynamicInvoker();
        }

        String evaluate(Object value) throws Throwable {
            return (String) invoker.invokeExact(value);
        }

        void switchToStrictMode() {
            callSite.setTarget(STRICT_RULE);
            MutableCallSite.syncAll(new MutableCallSite[] { callSite });
        }
    }

    public static void main(String[] args) throws Throwable {
        MiniLanguageRuntime runtime = new MiniLanguageRuntime();

        System.out.println(runtime.evaluate("hello"));
        System.out.println(runtime.evaluate(Integer.valueOf(41)));
        System.out.println(runtime.evaluate(Boolean.TRUE));

        runtime.switchToStrictMode();
        System.out.println(runtime.evaluate("hello"));

        try {
            runtime.evaluate(Integer.valueOf(41));
        } catch (IllegalArgumentException error) {
            System.out.println("strict rejects Integer");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 -Xlint:all DynamicLinkingApiDemo.java
java DynamicLinkingApiDemo
~~~

Kết quả chuẩn:

~~~text
string:HELLO
integer:42
fallback:true
strict:HELLO
strict rejects Integer
~~~

Giải thích:

1. `CALL_TYPE` đặt hợp đồng cho call site là nhận Object và trả String.
2. Lookup tìm các static method và tạo MethodHandle có kiểu tương ứng.
3. `guardWithTest` ghép các điều kiện kiểm tra kiểu với target chuỗi, số và fallback.
4. MutableCallSite giữ dispatcher và `dynamicInvoker()` cung cấp handle gọi target hiện tại.
5. `switchToStrictMode()` thay target bằng quy tắc strict; `syncAll` công bố thay đổi target cho các thread khác.
6. Runtime nhỏ này tự định nghĩa semantics dispatch. JVM/API chỉ cung cấp cách ghép và gọi các target có kiểu.

Trong một language runtime thật, các guard có thể kiểm tra class, object shape, meta-class hoặc version của cache. Fallback sẽ thực hiện tra cứu theo quy tắc ngôn ngữ, sau đó cập nhật call site nếu phù hợp.

## 8. Ví dụ bootstrap method cho một invokedynamic call site

Đây là phần minh họa hợp đồng bootstrap mà bytecode có thể tham chiếu:

~~~java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String operationName,
        MethodType callSiteType
) throws ReflectiveOperationException {
    MethodHandle target = caller.findStatic(
            LanguageRuntime.class,
            operationName,
            callSiteType
    );

    return new ConstantCallSite(target);
}
~~~

Đoạn này giả định method có tên `operationName` là static, có thể truy cập qua Lookup của caller và có chữ ký chính xác bằng `callSiteType`.

Nếu bytecode phát ra một instruction có descriptor `(Object)String`, bootstrap phải trả về CallSite có target kiểu `(Object)String`. Một target `(String)String` không thể được gắn trực tiếp vào call site đó nếu chưa có bước adaptation phù hợp và kết quả cuối cùng vẫn phải đúng descriptor của call site.

Để bootstrap được JVM gọi, compiler hoặc bytecode generator phải tạo constant-pool/bootstrap metadata và instruction `invokedynamic` trỏ đến bootstrap method. Chỉ khai báo method Java với tên `bootstrap` không tự động biến các lời gọi Java thông thường thành dynamic call site.

## 9. Java platform dùng dynamic linking cho những việc nào?

Dynamic-linking API không chỉ dành cho ngôn ngữ động. Nền tảng Java cũng dùng cơ chế này cho một số tính năng:

- Lambda expression và method reference được triển khai thông qua cơ chế bootstrap liên quan đến `LambdaMetafactory`.
- Từ Java 9, chiến lược nối chuỗi của javac dùng `invokedynamic` với `StringConcatFactory` cho các biểu thức nối chuỗi phù hợp.
- Các framework hoặc language runtime có thể dùng MethodHandle và CallSite để xây dựng dispatch linh hoạt.

Các ví dụ này cho thấy `invokedynamic` là cơ chế nền tảng tổng quát. Một bootstrap method của JDK có thể triển khai một tính năng của Java; bootstrap method của một language runtime có thể triển khai semantics của một ngôn ngữ khác. Chúng dùng cùng cơ chế JVM nhưng có mục đích và quy tắc cấp ngôn ngữ khác nhau.

## 10. Lỗi thường gặp và cách tránh

| Hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| Cho rằng invokedynamic tự tìm method theo tên runtime | JVM gọi bootstrap và dùng CallSite mà bootstrap trả về | Runtime tự triển khai tra cứu và dispatch |
| Cho rằng MethodHandle là một ngôn ngữ động hoàn chỉnh | MethodHandle chỉ là tham chiếu có kiểu để gọi thao tác | Xây semantics ở compiler/runtime |
| Cho rằng mọi language runtime đều phải dùng invokedynamic | Runtime có thể dùng interpreter, reflection hoặc cách khác | Chọn kiến trúc theo yêu cầu và đo hiệu năng |
| Cho rằng descriptor của call site thay đổi tùy object | Descriptor của instruction là hợp đồng kiểu cố định | Chọn target phù hợp hoặc dùng descriptor tổng quát như Object |
| Trả về CallSite có target sai MethodType | Target không khớp descriptor sẽ làm linkage thất bại | Kiểm tra MethodType trước khi trả CallSite |
| Cho rằng Lookup bỏ qua module access | Lookup giữ quyền truy cập theo ngữ cảnh và access rules | Xử lý visibility/module đúng thiết kế |
| Dùng MutableCallSite rồi giả định mọi thread thấy target mới ngay | Target mutable có semantics như field thông thường | Dùng syncAll hoặc VolatileCallSite khi phù hợp |
| Cache method mà không có invalidation | Metadata hoặc class behavior có thể thay đổi | Dùng guard, version hoặc SwitchPoint |
| Gọi bootstrap trực tiếp rồi nghĩ đã tạo invokedynamic | Lời gọi Java bình thường không tạo bytecode instruction | Dùng compiler/bytecode generator để phát invokedynamic |
| Đưa quy tắc coercion vào JVM API | Coercion là semantics của ngôn ngữ | Đặt quy tắc ở language runtime |

## 11. Checklist thiết kế một language runtime trên JVM

- Xác định semantics của từng thao tác ngôn ngữ trước khi thiết kế bootstrap.
- Chọn descriptor MethodType ổn định và đủ tổng quát cho từng loại call site.
- Dùng Lookup đúng ngữ cảnh, tôn trọng access control và module boundaries.
- Tạo MethodHandle có kiểu chính xác; chỉ adaptation khi cần.
- Dùng ConstantCallSite nếu target không cần thay đổi.
- Dùng MutableCallSite hoặc VolatileCallSite theo yêu cầu cập nhật và visibility.
- Dùng guard/fallback để cache dispatch khi có lợi.
- Có chiến lược invalidation khi class, object shape hoặc meta-data thay đổi.
- Xác định rõ lỗi linkage, lỗi dispatch và lỗi ngôn ngữ.
- Không nhầm cơ chế liên kết của JVM với parser, compiler hoặc object model của ngôn ngữ.
- Đo hiệu năng bằng workload thực tế; không giả định invokedynamic luôn nhanh hơn mọi phương pháp khác.

## 12. Tài liệu API và đặc tả

- [java.lang.invoke package — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/package-summary.html)
- [MethodHandle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [CallSite — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [MutableCallSite — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html)
- [Java Virtual Machine Specification — invokedynamic](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic)

API liên kết động cung cấp hợp đồng gọi và công cụ liên kết ở cấp JVM. Bộ thực thi ngôn ngữ sử dụng những công cụ đó để triển khai quy tắc của ngôn ngữ như tra cứu, dispatch, chuyển kiểu, cache và xử lý lỗi. Phân biệt rõ hai lớp giúp thiết kế runtime dễ kiểm thử, dễ thay đổi và không gán nhầm trách nhiệm cho JVM.