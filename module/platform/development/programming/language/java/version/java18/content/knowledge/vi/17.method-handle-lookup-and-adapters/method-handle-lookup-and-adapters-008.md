# IllegalAccessException và NoSuchMethodException: phân biệt quyền, chữ ký và member không tồn tại

> **Phạm vi:** Chương **Lookup và adapter**, module `JAVA_VERSION_JAVA18`. Các API `java.lang.invoke.MethodHandles.Lookup`, `MethodType` và `MethodHandle` vẫn được sử dụng trên JDK hiện đại. Bài tập trung vào cách phân loại `NoSuchMethodException` và `IllegalAccessException` khi **tạo method handle**, đồng thời phân biệt chúng với `WrongMethodTypeException` hoặc lỗi của code mục tiêu khi **gọi handle**. Java 18 có JEP 416 tái triển khai core reflection dựa trên method handles; đây là thay đổi nội bộ, không thay hợp đồng API công khai. Chỉ dùng kiến thức và API còn áp dụng, không sử dụng lớp nội bộ hoặc cơ chế legacy.

## 1. Câu hỏi cốt lõi: không tìm thấy member hay không được quyền dùng member?

Giả sử ứng dụng muốn lấy handle cho method:

~~~java
MethodHandles.Lookup lookup = MethodHandles.publicLookup();

MethodHandle handle = lookup.findVirtual(
        Service.class,
        "process",
        MethodType.methodType(String.class, String.class));
~~~

Có hai câu hỏi độc lập:

1. **Đúng member không?** `Service` có một instance method tên `process` với chữ ký tương ứng không?
2. **Lookup có quyền truy cập không?** Lớp chứa member, bản thân member và các kiểu trong chữ ký có khả dụng với `Lookup` đó không?

Nếu tên hoặc chữ ký không tồn tại, API có thể ném **`NoSuchMethodException`**. Nếu member có tồn tại nhưng yêu cầu truy cập không hợp lệ, API có thể ném **`IllegalAccessException`**.

Theo Javadoc `MethodHandles.Lookup`, access check chủ yếu diễn ra **khi tạo handle**, không được làm lại như một access check tổng quát mỗi lần gọi handle. Vì vậy, việc tạo handle thành công thường nghĩa là lookup đã có quyền tạo capability tương ứng.

~~~text
Request: refc + name + MethodType + loại lookup
                    │
                    ▼
           MethodHandles.Lookup
                    │
          ┌─────────┼─────────────┐
          │         │             │
    Không thấy    Có member    Có member và
    member theo   nhưng thiếu  đủ quyền
    chữ ký        quyền/loại
          │         │             │
          ▼         ▼             ▼
NoSuchMethod-  IllegalAccess-   MethodHandle
Exception      Exception           │
                                   ▼
                         invokeExact / invoke
                                   │
                                   ▼
                        Call-site/target errors
~~~

**Đừng gộp mọi thất bại thành “method không tồn tại”.** Một lỗi quyền truy cập cần sửa thiết kế module hoặc quyền của lookup; một lỗi chữ ký cần sửa tên, return type, parameter types hoặc loại member được yêu cầu.

## 2. MethodType phải đúng tên, kiểu trả về và tham số

`MethodType` là descriptor chứa **return type** và danh sách **parameter types có thứ tự**:

~~~java
import java.lang.invoke.MethodType;

MethodType textToText =
        MethodType.methodType(String.class, String.class);

MethodType intToText =
        MethodType.methodType(String.class, int.class);

MethodType integerToText =
        MethodType.methodType(String.class, Integer.class);
~~~

Ba loại method trên có descriptor khác nhau:

~~~text
(String)String
(int)String
(Integer)String
~~~

Cú pháp `methodType(returnType, parameterTypes...)` có **return type ở đầu**. Khi `Lookup.findVirtual` hoặc `findStatic` tìm method bình thường, phần `MethodType` phải mô tả đúng method được tìm.

Ví dụ một class có:

~~~java
public String format(String value) { return "text:" + value; }
public String format(int value)    { return "number:" + value; }
~~~

Bảng:

| Yêu cầu lookup | Kết quả với class ví dụ |
|---|---|
| `format`, `(String)String` | Tìm được method public nhận `String`. |
| `format`, `(int)String` | Tìm được overload nhận `int`. |
| `format`, `(Integer)String` | `NoSuchMethodException`; không có overload nhận `Integer`. |
| `format`, `(String)Object` | `NoSuchMethodException` trong class ví dụ; return type không khớp descriptor. |
| `missing`, `()void` | `NoSuchMethodException`; tên method không tồn tại. |

**Lưu ý về return type:** `Lookup.findVirtual` nhận `MethodType` có kiểu trả về, khác với `Class.getDeclaredMethod(name, parameterTypes)` của core reflection (API đó không nhận return type). Bytecode Java có thể chứa bridge methods hoặc method có descriptor đặc biệt liên quan đến generic/covariant returns; khi debug, cần kiểm tra method thực sự trong class, không suy luận chỉ từ overload theo tên trong source.

**Không có boxing tự động ở giai đoạn tìm kiếm.** Một method nhận `int` không mặc nhiên được tìm bằng descriptor có `Integer`. Nếu muốn chuyển đổi kiểu khi **gọi**, hãy tìm đúng handle trước rồi sử dụng `asType(...)` hoặc `invoke(...)` trong giới hạn cho phép.

## 3. Lookup khác nhau mang quyền khác nhau

`MethodHandles.Lookup` không phải một bộ tìm kiếm không giới hạn. Nó mang **lookup class** và access modes, được dùng khi kiểm tra quyền đối với member.

Các cách thường gặp:

~~~java
MethodHandles.Lookup local = MethodHandles.lookup();
MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
~~~

| Lookup | Ý nghĩa |
|---|---|
| `MethodHandles.lookup()` | Mang quyền của **class đang gọi `lookup()`** theo quy tắc Java/JPMS. Có thể truy cập member không public nếu lookup class thực sự có quyền. |
| `MethodHandles.publicLookup()` | Hạn chế vào member public của các type public trong package được export phù hợp. Không dùng để lấy private member. |
| `MethodHandles.privateLookupIn(Target.class, callerLookup)` | Tạo lookup mang quyền private đối với `Target` **nếu** caller lookup và ranh giới module cho phép deep reflection. |
| `lookup.in(Other.class)` | Chuyển lookup class theo quy tắc mất/giảm quyền tương ứng; không phải công cụ tự động nâng cấp quyền. |

Ví dụ, `publicLookup` không thể lấy private `secret()` của một class public, ngay cả khi tên và MethodType của method đó đúng. Trong trường hợp ấy, chẩn đoán đúng là **`IllegalAccessException`**, không phải sửa chữ ký hay giả định method thiếu.

### Access check xảy ra khi tạo handle

~~~java
MethodHandle publicHandle = publicOnly.findVirtual(
        Service.class,
        "process",
        MethodType.methodType(String.class, String.class));
~~~

Nếu `findVirtual` thành công, `publicHandle` có thể được gọi theo đúng kiểu. Không dùng `asType` để “thử tăng quyền”: adapter chỉ đổi cách truyền/nhận giá trị, không tạo capability để truy cập một member mà lookup ban đầu không được phép lấy.

Đây là khác biệt quan trọng với `java.lang.reflect.Method.invoke`, nơi việc thực thi reflection còn chịu hợp đồng kiểm tra truy cập của core reflection. `MethodHandles.Lookup` buộc quyền vào **khả năng tạo handle**, còn handle được trao cho code khác là một capability cần được quản lý cẩn thận.

## 4. Sai loại lookup: method tồn tại nhưng vẫn IllegalAccessException

Một trường hợp rất dễ nhầm là dùng `findStatic` để lấy instance method, hoặc `findVirtual` để lấy static method.

Javadoc `MethodHandles.Lookup` quy định rõ:

- `findStatic` có thể ném `IllegalAccessException` nếu method tìm được **không phải static**.
- `findVirtual` có thể ném `IllegalAccessException` nếu method tìm được **là static**.

Ví dụ class:

~~~java
public String format(String s) { return s; }
public static int sum(int a, int b) { return a + b; }
~~~

| Lookup | Kỳ vọng | Nguyên nhân |
|---|---|---|
| `findVirtual(Service.class, "format", (String)String)` | Thành công nếu đủ quyền | Method instance đúng loại. |
| `findStatic(Service.class, "format", (String)String)` | `IllegalAccessException` | `format` có tồn tại nhưng không phải static. |
| `findStatic(Service.class, "sum", (int,int)int)` | Thành công nếu đủ quyền | Method static đúng loại. |
| `findVirtual(Service.class, "sum", (int,int)int)` | `IllegalAccessException` | `sum` có tồn tại nhưng là static. |

Đây không phải ví dụ để kết luận “mọi lookup sai đều là IllegalAccessException”. Nếu tên hoặc `MethodType` không khớp một method tồn tại, vẫn có thể là `NoSuchMethodException`. **Cô lập một điều kiện sai trong mỗi ca test** để nhận diện đúng nguyên nhân.

### Receiver không nằm trong MethodType truyền vào findVirtual

~~~java
MethodHandle virtual = lookup.findVirtual(
        Service.class,
        "format",
        MethodType.methodType(String.class, String.class));
~~~

`MethodType` yêu cầu tìm là `(String)String` — kiểu của **method gốc, chưa tính receiver**. Khi tạo handle, `findVirtual` thêm `Service` làm tham số đầu:

~~~text
MethodType yêu cầu:    (String)String
MethodHandle trả về:  (Service,String)String
                           ^ receiver
~~~

Với `findStatic`, không có receiver được thêm:

~~~text
MethodType yêu cầu:    (int,int)int
MethodHandle trả về:  (int,int)int
~~~

Nếu nhầm lẫn và thêm `Service.class` vào `MethodType` truyền cho `findVirtual`, lookup có thể đi tìm **một overload khác không tồn tại**, rồi ném `NoSuchMethodException`.

## 5. Kiểm chứng riêng trường hợp private và quyền module

Giả sử `Service` là class public có private method:

~~~java
public static final class Service {
    private String secret() {
        return "classified";
    }
}
~~~

Lookup public không thể tạo handle cho private method:

~~~java
MethodHandles.Lookup publicOnly =
        MethodHandles.publicLookup();

publicOnly.findVirtual(
        Service.class,
        "secret",
        MethodType.methodType(String.class));
// IllegalAccessException.
~~~

Nếu code **thực sự được phép** deep reflection, dùng `privateLookupIn`:

~~~java
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(
                Service.class,
                MethodHandles.lookup());

MethodHandle handle = privateLookup.findVirtual(
        Service.class,
        "secret",
        MethodType.methodType(String.class));
~~~

Trong ví dụ đơn giản có `Service` ở cùng module, cách trên có thể hợp lệ. Với hai named modules khác nhau, `privateLookupIn` đòi hỏi điều kiện về quyền `PRIVATE`/`MODULE`, khả năng đọc module đích và package đích được `opens` cho module caller.

Ví dụ:

~~~java
// module-info.java của module chứa Service:
module example.services {
    exports example.services.api;
    opens example.services.internal to example.consumer;
}
~~~

Điểm phân biệt:

- `exports` cho phép client dùng các public types/members trong package được export.
- `opens` cho phép deep reflection theo đúng phạm vi package/module được chỉ định.
- `publicLookup()` không tự có quyền vào private member chỉ vì package được `opens`.
- `privateLookupIn` không vượt qua chính sách module nếu module đích chưa mở package tương ứng.

Không nên khuyến nghị mở mọi package của JDK hoặc dùng các công tắc vô hiệu hóa encapsulation. Thay vì bypass quyền, ưu tiên thiết kế public API hoặc mở đúng package thật sự cần thiết.

### Cẩn trọng với nestmates

Trên JDK hiện đại, nested class và enclosing class có thể là **nestmates** với quyền truy cập private theo JVMS. Vì vậy, một phép thử dùng `MethodHandles.lookup()` từ enclosing class đối với private method của nested class có thể **thành công**.

Để kiểm chứng ca **thiếu quyền** một cách ổn định, ví dụ ở phần sau cố ý dùng `publicLookup()`. Không dùng `MethodHandles.lookup()` từ cùng nest rồi khẳng định private member bắt buộc bị từ chối.

## 6. Ví dụ Java 18+: phân loại lookup failures bằng một chương trình

Ví dụ sau độc lập, không cần thư viện ngoài, không phụ thuộc DNS, không cần mở module và không dùng preview feature. Nó bao phủ:

- Thành công với instance, static và constructor.
- `NoSuchMethodException` khi sai tên, sai parameter type hoặc return type.
- `IllegalAccessException` khi private method không được phép truy cập.
- `IllegalAccessException` khi chọn sai `findStatic`/`findVirtual`.
- Thành công với private member khi dùng `privateLookupIn` được cấp quyền hợp lệ.
- `WrongMethodTypeException` **sau khi lookup thành công** nếu call site `invokeExact` không khớp.
- Adapter `bindTo`/`asType` chỉ được áp dụng sau khi có handle hợp lệ.

Lưu tệp `LookupFailureDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class LookupFailureDemo {

    public static final class Service {
        public Service() {
        }

        public String format(String value) {
            return "text:" + value;
        }

        public String format(int value) {
            return "number:" + value;
        }

        public static int sum(int left, int right) {
            return left + right;
        }

        private String secret() {
            return "private-ok";
        }
    }

    @FunctionalInterface
    private interface CheckedAction {
        void run() throws Throwable;
    }

    // Bắt Throwable CHỈ trong harness để phân loại lỗi cụ thể.
    private static void expect(
            String label,
            Class<? extends Throwable> expected,
            CheckedAction action) {
        try {
            action.run();
            throw new AssertionError("Expected " + expected.getName());
        } catch (Throwable failure) {
            if (!expected.isInstance(failure)) {
                throw new AssertionError(
                        "Unexpected failure for " + label, failure);
            }
            System.out.println(label + ": "
                    + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup publicOnly =
                MethodHandles.publicLookup();

        MethodType formatTextType =
                MethodType.methodType(String.class, String.class);
        MethodType sumType =
                MethodType.methodType(int.class, int.class, int.class);

        // 1. Lookup thành công: method instance và static.
        MethodHandle format = publicOnly.findVirtual(
                Service.class, "format", formatTextType);

        MethodHandle sum = publicOnly.findStatic(
                Service.class, "sum", sumType);

        MethodType expectedFormatHandleType = MethodType.methodType(
                String.class, Service.class, String.class);

        if (!format.type().equals(expectedFormatHandleType)
                || !sum.type().equals(sumType)) {
            throw new AssertionError("Unexpected handle type");
        }

        Service service = new Service();
        System.out.println("INSTANCE_OK="
                + (String) format.invokeExact(service, "hi"));
        System.out.println("STATIC_OK="
                + (int) sum.invokeExact(3, 4));

        // 2. Member không tồn tại hoặc signature không khớp.
        expect("NO_NAME", NoSuchMethodException.class,
                () -> publicOnly.findVirtual(
                        Service.class,
                        "missing",
                        MethodType.methodType(void.class)));

        expect("NO_PARAMETER_SIGNATURE", NoSuchMethodException.class,
                () -> publicOnly.findVirtual(
                        Service.class,
                        "format",
                        MethodType.methodType(
                                String.class, Integer.class)));

        expect("NO_RETURN_SIGNATURE", NoSuchMethodException.class,
                () -> publicOnly.findVirtual(
                        Service.class,
                        "format",
                        MethodType.methodType(
                                Object.class, String.class)));

        // 3. Thành viên private tồn tại nhưng lookup không có quyền.
        expect("PRIVATE_DENIED", IllegalAccessException.class,
                () -> publicOnly.findVirtual(
                        Service.class,
                        "secret",
                        MethodType.methodType(String.class)));

        // 4. Sai loại: method tồn tại nhưng không khớp static/virtual.
        expect("INSTANCE_AS_STATIC", IllegalAccessException.class,
                () -> publicOnly.findStatic(
                        Service.class, "format", formatTextType));

        expect("STATIC_AS_INSTANCE", IllegalAccessException.class,
                () -> publicOnly.findVirtual(
                        Service.class, "sum", sumType));

        // 5. Quyền private được lấy hợp lệ trong cùng module.
        MethodHandles.Lookup privateForService =
                MethodHandles.privateLookupIn(
                        Service.class, MethodHandles.lookup());

        MethodHandle secret = privateForService.findVirtual(
                Service.class,
                "secret",
                MethodType.methodType(String.class));

        System.out.println("PRIVATE_ALLOWED="
                + (String) secret.invokeExact(service));

        // 6. Constructor có lookup API riêng, yêu cầu void return.
        MethodHandle constructor = publicOnly.findConstructor(
                Service.class, MethodType.methodType(void.class));

        Service newService = (Service) constructor.invokeExact();
        System.out.println("CONSTRUCTOR_OK=" + (newService != null));

        expect("NO_CONSTRUCTOR", NoSuchMethodException.class,
                () -> publicOnly.findConstructor(
                        Service.class,
                        MethodType.methodType(void.class, int.class)));

        // 7. Handle tạo thành công nhưng call-site invokeExact sai return.
        expect("WRONG_CALL_SITE", WrongMethodTypeException.class,
                () -> {
                    Object unused =
                            (Object) format.invokeExact(service, "hi");
                });

        // 8. Adapter chỉ dùng sau lookup thành công.
        MethodHandle bound = format.bindTo(service);
        System.out.println("BOUND_OK="
                + (String) bound.invokeExact("bound"));

        MethodHandle generic = bound.asType(
                MethodType.methodType(Object.class, Object.class));

        Object adapted =
                (Object) generic.invokeExact((Object) "adapted");
        System.out.println("ADAPTER_OK=" + adapted);
    }
}
~~~

Biên dịch và chạy với JDK 18+:

~~~shell
javac LookupFailureDemo.java
java LookupFailureDemo
~~~

Kết quả dự kiến:

~~~text
INSTANCE_OK=text:hi
STATIC_OK=7
NO_NAME: NoSuchMethodException
NO_PARAMETER_SIGNATURE: NoSuchMethodException
NO_RETURN_SIGNATURE: NoSuchMethodException
PRIVATE_DENIED: IllegalAccessException
INSTANCE_AS_STATIC: IllegalAccessException
STATIC_AS_INSTANCE: IllegalAccessException
PRIVATE_ALLOWED=private-ok
CONSTRUCTOR_OK=true
NO_CONSTRUCTOR: NoSuchMethodException
WRONG_CALL_SITE: WrongMethodTypeException
BOUND_OK=text:bound
ADAPTER_OK=text:adapted
~~~

Đây là **kết quả mong đợi theo hợp đồng**, không phải log của một lần chạy thực tế. Theo yêu cầu STEP_4, ví dụ chỉ được soạn, chưa chạy build, test hoặc vòng Content QA chuyên môn.

## 7. Phân tích từng nhóm lỗi từ ví dụ

### 7.1. NoSuchMethodException: sai tên hoặc MethodType

Ba phép thử:

~~~java
findVirtual(Service.class, "missing", methodType(void.class));
findVirtual(Service.class, "format",
        methodType(String.class, Integer.class));
findVirtual(Service.class, "format",
        methodType(Object.class, String.class));
~~~

đều yêu cầu member **không có descriptor tương ứng trong ví dụ**, dù `Service` vẫn có các method `format` khác.

Hướng xử lý: kiểm tra tên, overload, `int.class` so với `Integer.class`, return type và số lượng/thứ tự tham số. Không thay `publicLookup` bằng lookup nhiều quyền hơn để “chữa” một descriptor sai.

### 7.2. IllegalAccessException: không đủ quyền

~~~java
publicOnly.findVirtual(
        Service.class, "secret",
        MethodType.methodType(String.class));
~~~

Tên và descriptor của private `secret` là đúng; vấn đề là `publicLookup()` không có quyền. Hướng xử lý: xác định đúng lookup class và chính sách package/module. Nếu deep reflection thật sự cần thiết và được cho phép, dùng `privateLookupIn` trong phạm vi phù hợp.

**Không tự động chuyển `IllegalAccessException` thành `NoSuchMethodException` để che lỗi.** Hai thông tin này rất hữu ích khi chẩn đoán, dù thông báo gửi ra ngoài cho người dùng cuối có thể cần hạn chế lộ chi tiết member nội bộ.

### 7.3. IllegalAccessException: sai loại static/instance

~~~java
publicOnly.findStatic(
        Service.class, "format",
        MethodType.methodType(String.class, String.class));

publicOnly.findVirtual(
        Service.class, "sum",
        MethodType.methodType(int.class, int.class, int.class));
~~~

Trong hai trường hợp, method tồn tại, nhưng factory yêu cầu **kiểu gọi không phù hợp**. Javadoc chỉ rõ nhánh lỗi thuộc `IllegalAccessException`.

Hướng xử lý: chọn `findVirtual` cho instance method, `findStatic` cho static method. Với constructor dùng `findConstructor`, không dùng tên JVM nội bộ `"<init>"` qua `findVirtual`.

### 7.4. WrongMethodTypeException: lookup đã xong, lỗi ở invoke

~~~java
MethodHandle format = publicOnly.findVirtual(
        Service.class,
        "format",
        MethodType.methodType(String.class, String.class));

// Handle type: (Service,String)String
Object wrong = (Object) format.invokeExact(new Service(), "hi");
~~~

`findVirtual` đã thành công. `WrongMethodTypeException` xảy ra **khi gọi `invokeExact`** vì call site yêu cầu return type `Object`, trong khi handle trả `String`. Đây không phải lỗi thiếu member, không phải lỗi quyền.

Có thể dùng `invoke` hoặc adapter `asType` khi cần các chuyển đổi hợp lệ, nhưng adapter không giải quyết việc `Lookup` ban đầu thiếu quyền.

## 8. Constructor, special lookup và field lookup

`Lookup` có các factory khác nhau, không nên áp dụng một quy tắc lỗi cho tất cả:

| API | Yêu cầu | Lỗi khi member không tồn tại | Lỗi khi không đủ quyền |
|---|---|---|---|
| `findVirtual` | Instance method, `MethodType` không chứa receiver. | `NoSuchMethodException` | `IllegalAccessException` |
| `findStatic` | Static method, `MethodType` đúng method. | `NoSuchMethodException` | `IllegalAccessException` |
| `findConstructor` | Constructor với `MethodType` có **return `void`**. | `NoSuchMethodException` | `IllegalAccessException` |
| `findSpecial` | Call kiểu `invokespecial` với `specialCaller` và quyền bổ sung. | `NoSuchMethodException` | `IllegalAccessException` |
| `findGetter`, `findSetter` | Instance field và field type. | `NoSuchFieldException` | `IllegalAccessException` |
| `findStaticGetter`, `findStaticSetter` | Static field và field type. | `NoSuchFieldException` | `IllegalAccessException` |

### Constructor có return type đặc biệt

~~~java
MethodHandle ctor = publicOnly.findConstructor(
        Service.class,
        MethodType.methodType(void.class));

System.out.println(ctor.type()); // ()Service
~~~

Factory nhận `void.class` vì đó là kiểu descriptor của constructor JVM. **Handle được trả về** lại trả `Service` — đối tượng vừa tạo. Dùng `MethodType.methodType(Service.class)` làm kiểu đầu vào cho `findConstructor` là sai hợp đồng, không phải cách yêu cầu handle trả `Service`.

### findSpecial có quy tắc access riêng

`findSpecial(refc, name, type, specialCaller)` được thiết kế cho lời gọi kiểu `invokespecial` (ví dụ gọi triển khai super mà bỏ qua dynamic dispatch thông thường). Ngoài quyền thấy member, nó còn yêu cầu quan hệ và quyền của `specialCaller`/`Lookup` phù hợp.

Vì vậy `findSpecial` có thể ném `IllegalAccessException` **ngay cả khi method là public**, nếu yêu cầu special caller không hợp lệ. Không dùng `findSpecial` như giải pháp chung để né `IllegalAccessException` của `findVirtual`.

## 9. Adapter không thay đổi kết quả access check

Sau khi tạo được handle `(Service,String)String`:

~~~java
MethodHandle bound = format.bindTo(service);
// bound.type(): (String)String

MethodHandle generic = bound.asType(
        MethodType.methodType(Object.class, Object.class));
// generic.type(): (Object)Object
~~~

Hai thao tác:

- `bindTo(service)` cố định receiver hợp lệ vào handle, nên handle mới không còn tham số receiver.
- `asType(...)` tạo view có chữ ký khác, với chuyển đổi reference/primitive phù hợp theo hợp đồng.

Không có thao tác nào yêu cầu `Lookup` mới hay thực hiện lại access check. Nhưng điều đó cũng có nghĩa là code giữ một handle đã được cấp quyền có thể sử dụng capability đó theo kiểu được adapter cho phép. **Không chia sẻ handle đến private member với code không đáng tin** nếu không muốn trao quyền thực thi member ấy.

### Lỗi ở tầng adapter và call site

| Lỗi | Khi nào | Có phải lỗi tìm member? |
|---|---|---|
| `WrongMethodTypeException` | `invokeExact` sai descriptor, hoặc `invoke`/`asType` không thích ứng được kiểu. | Không. |
| `ClassCastException` | Adapter có thể tạo nhưng object runtime sai kiểu khi cast/unbox. | Không. |
| `NullPointerException` | Unboxing `null` hoặc receiver/argument bắt buộc không null. | Không. |
| Throwable của target | Method thực sự chạy rồi ném lỗi. | Không. |

MethodHandle không tự bọc throwable từ target bằng `InvocationTargetException` như `Method.invoke` của core reflection. Để chẩn đoán, ghi rõ giai đoạn **lookup**, **adapter**, **invocation** và **target execution**.

## 10. Trình tự chẩn đoán khi gặp lỗi

Dùng quy trình dưới đây thay vì retry ngẫu nhiên:

1. **Xác định factory:** `findVirtual`, `findStatic`, `findConstructor`, `findSpecial` hay field lookup?
2. **Kiểm tra owner/refc:** đúng `Class<?>` hay chưa? Có class loader khác nạp một type cùng tên không?
3. **Kiểm tra member name và descriptor:** đủ số lượng, đúng thứ tự và đúng primitive/wrapper? Với method, đã đúng return type chưa?
4. **Kiểm tra static/instance:** factory có khớp loại member không?
5. **Kiểm tra quyền của Lookup:** `lookup.lookupClass()`, `lookup.lookupModes()`, public/package/private/protected/module phù hợp?
6. **Kiểm tra JPMS:** package đã được export cho public access? Nếu cần private, module đích có mở package cho caller?
7. **Nếu lookup thành công:** in `handle.type()`, rồi so với descriptor của `invokeExact` hoặc `invoke` tại call site.
8. **Nếu adapter được tạo:** kiểm tra dữ liệu runtime, `null`, cast/boxing/unboxing. Nếu target đã chạy, xem lỗi của target.

Ví dụ ghi log hỗ trợ:

~~~java
System.out.println("lookupClass=" + lookup.lookupClass().getName());
System.out.println("lookupModes=" + lookup.lookupModes());

MethodHandle handle = lookup.findVirtual(
        Service.class, "format",
        MethodType.methodType(String.class, String.class));

System.out.println("handle.type=" + handle.type());
~~~

Không log dữ liệu nhạy cảm hoặc toàn bộ private member metadata ra log công khai. Thông tin quyền và tên member có thể hữu ích cho người vận hành nhưng cũng có thể làm lộ cấu trúc nội bộ.

### Đừng phụ thuộc vào thứ tự kiểm tra nếu có nhiều lỗi đồng thời

Nếu một method vừa private vừa bị yêu cầu với return type sai, hoặc class vừa không public vừa không có member đúng tên, không nên giả định mọi JDK luôn chọn cùng lỗi đầu tiên. Cách kiểm thử tốt nhất là **mỗi ca chỉ vi phạm một điều kiện**.

## 11. Ca kiểm thử thực tế cần bao phủ

| Ca kiểm thử | Điều kiện cô lập | Kết quả kỳ vọng |
|---|---|---|
| Đúng public instance method | Public class, đúng `MethodType`, `findVirtual`. | Có handle `(Receiver,...)Return`. |
| Đúng public static method | Đúng `MethodType`, `findStatic`. | Có handle `(...)Return`. |
| Sai tên | Public class, tên không tồn tại. | `NoSuchMethodException`. |
| Sai parameter type | Overload nhận `int`, hỏi `Integer`. | `NoSuchMethodException`. |
| Sai return type | Hỏi `Object` khi chỉ có method trả `String` trong class test. | `NoSuchMethodException`. |
| Private method, publicLookup | Member tồn tại, `publicLookup` không đủ quyền. | `IllegalAccessException`. |
| Instance method qua findStatic | Member tồn tại, sai loại. | `IllegalAccessException`. |
| Static method qua findVirtual | Member tồn tại, sai loại. | `IllegalAccessException`. |
| Private method với privateLookupIn hợp lệ | Cùng module hoặc package mở hợp lệ. | Tạo handle thành công. |
| Constructor public không tham số | `findConstructor` với `()void`. | Handle trả instance class. |
| Constructor không có signature | `findConstructor` với `(int)void` nhưng class chỉ có `()void`. | `NoSuchMethodException`. |
| Handle được tạo nhưng invokeExact sai return type | Descriptor lookup đúng, descriptor call site sai. | `WrongMethodTypeException`. |
| Handle đã bindTo/asType | Tạo adapter sau lookup hợp lệ. | Chữ ký adapter mới được áp dụng. |

## 12. Sai lầm thường gặp

| Nhầm lẫn | Hậu quả | Cách sửa |
|---|---|---|
| “Không gọi được tức là member không tồn tại.” | Đổi sai tên hoặc overload trong khi thực ra thiếu quyền. | Phân biệt `NoSuchMethodException` với `IllegalAccessException`. |
| Quên return type trong MethodType | Descriptor không khớp member. | Ghi rõ `methodType(returnType, parameterTypes...)`. |
| Nhầm `int.class` và `Integer.class` | Tra sai overload. | Dùng kiểu chính xác; chuyển đổi ở adapter sau lookup. |
| Thêm receiver vào MethodType của findVirtual | Tìm nhầm chữ ký method. | Receiver chỉ có trong **handle trả về**. |
| Dùng findStatic cho instance method | `IllegalAccessException` dù method có tồn tại. | Chọn đúng factory. |
| Dùng publicLookup cho private member | `IllegalAccessException`. | Dùng public API hoặc privateLookupIn khi được cấp quyền. |
| Giả định opens = exports | Sai mô hình quyền JPMS. | Phân biệt public API với deep reflection. |
| Nghĩ lookup.in(...) tự nâng quyền | Vẫn bị access checks từ lookup mới. | Hiểu lookupClass, lookupModes và quyền bị hạn chế. |
| Dùng findSpecial để bypass quyền | Có thể bị từ chối vì specialCaller không hợp lệ. | Chọn factory đúng mục đích. |
| Dùng asType để chữa IllegalAccessException | Không thể tạo handle ban đầu. | Sửa quyền/thiết kế trước, adapter sau. |
| Gọi invokeExact sai return type rồi bắt NoSuchMethodException | Bắt sai tầng lỗi. | Chẩn đoán `WrongMethodTypeException` ở call site. |
| Dùng JVM internal reflection để mở private | Dễ lỗi khi JDK đổi implementation. | Dùng API công khai và JPMS đúng phạm vi. |

## 13. Câu hỏi tự đánh giá

1. Vì sao một method private có tên và chữ ký đúng vẫn có thể làm `publicLookup.findVirtual` ném `IllegalAccessException`?
2. `NoSuchMethodException` có thể phát sinh nếu chỉ sai **return type** không?
3. Với `findVirtual`, tại sao `MethodType` đầu vào không chứa receiver?
4. Một instance method được yêu cầu qua `findStatic` sẽ báo lỗi gì theo Javadoc?
5. Vì sao `MethodHandles.lookup()` từ enclosing class có thể thấy private member của nested class trên JDK hiện đại?
6. `privateLookupIn` cần điều kiện gì khi target ở named module khác?
7. `exports` và `opens` giải quyết hai loại nhu cầu nào?
8. Khi nào `WrongMethodTypeException` xuất hiện dù `findVirtual` đã thành công?
9. `bindTo` và `asType` có tăng quyền truy cập private không?
10. `findConstructor` nhận return type nào và handle trả về kiểu nào?
11. Tại sao không nên tự động bắt cả hai exception rồi trả `null`?
12. Nếu method vừa private vừa có tên sai, vì sao cần tách hai ca test thay vì phụ thuộc thứ tự JVM báo lỗi?

**Ghi nhớ:** `MethodHandles.Lookup` kiểm tra quyền lúc **tạo** handle. `NoSuchMethodException` chủ yếu chỉ ra member theo tên và `MethodType` không tồn tại; `IllegalAccessException` chỉ ra lookup không có quyền, hoặc factory yêu cầu sai loại method static/instance theo Javadoc. Sau khi đã có handle, các lỗi như `WrongMethodTypeException`, `ClassCastException` hay throwable của target thuộc **giai đoạn gọi/adapter**, không phải lỗi tìm member. Chọn đúng factory, kiểm tra đầy đủ descriptor và tôn trọng access rules/JPMS trên JDK đang dùng.

## Tài liệu tham khảo chính thức

- [Java SE 26: `MethodHandles.Lookup` – các factory, kiểm tra quyền và ngoại lệ](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html).
- [Java SE 26: `MethodHandles` – `lookup`, `publicLookup`, `privateLookupIn`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- [Java SE 26: `MethodType` – return type và parameter types](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodType.html).
- [Java SE 26: `MethodHandle` – `invokeExact`, `invoke` và `asType`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [OpenJDK JEP 416 – Reimplement Core Reflection with Method Handles (Java 18)](https://openjdk.org/jeps/416).
- [Java Language Specification, Chapter 6 – Names, access control và member accessibility](https://docs.oracle.com/javase/specs/jls/se26/html/jls-6.html).
