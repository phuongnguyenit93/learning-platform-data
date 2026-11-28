# Primitive, wrapper và Object: nhận diện khác biệt dù giá trị dữ liệu trông giống nhau

> **Phạm vi:** Bài thuộc chương **MethodHandle** của module `JAVA_VERSION_JAVA18`. Java 18 (JEP 416) thay đổi cách triển khai core reflection dựa trên method handles, nhưng bài này sử dụng các API công khai `java.lang.invoke.MethodHandle`, `MethodType` và `MethodHandles` vẫn còn áp dụng trên JDK hiện đại. Mục tiêu là đọc đúng kiểu **primitive**, **wrapper** và **Object** trong chữ ký handle, phân biệt `invokeExact` với `invoke`/`asType` và chẩn đoán lỗi khi dữ liệu runtime trông giống nhau nhưng kiểu tại call site không tương thích. Không dùng API nội bộ, cách gọi hoặc kỹ thuật legacy.

## 1. Cùng giá trị 42 không có nghĩa cùng kiểu

Ba đoạn Java sau có thể cùng in ra `42`:

~~~java
int raw = 42;
Integer boxed = Integer.valueOf(42);
Object erased = Integer.valueOf(42);

System.out.println(raw);    // 42
System.out.println(boxed);  // 42
System.out.println(erased); // 42
~~~

Nhưng chúng có **kiểu tại compile time** khác nhau:

| Biến | Kiểu tĩnh | Giá trị khi chạy | Điểm khác biệt |
|---|---|---|---|
| `raw` | `int` | Primitive 42 | Không phải object; không thể giữ `null`. |
| `boxed` | `Integer` | Wrapper chứa 42 | Là reference; có thể là `null`. |
| `erased` | `Object` | Thực tế đang tham chiếu `Integer(42)` | Kiểu tĩnh không nói chắc object là `Integer`. |

Các phép gán có thể được Java tự boxing/unboxing hoặc widening reference, nhưng **`MethodHandle.invokeExact` không tự áp dụng các chuyển đổi đó để sửa chữ ký call site**.

~~~text
Giá trị hiển thị:          42            42                42
Kiểu compile time:         int           Integer           Object
MethodType tương ứng:      (int)int      (Integer)Integer   (Object)Object
                                 \          |                /
                                Bằng nhau về dữ liệu không đồng nghĩa
                                bằng nhau về chữ ký JVM.
~~~

Cần luôn tách ba điều: **giá trị**, **kiểu tĩnh của biểu thức tại call site** và **`MethodType` của target handle**.

## 2. MethodType là hợp đồng của MethodHandle

Mỗi `MethodHandle` có một `MethodType` xác định **kiểu trả về** và **danh sách kiểu tham số theo thứ tự**.

~~~java
import java.lang.invoke.MethodType;

MethodType primitive =
        MethodType.methodType(int.class, int.class);
MethodType wrapper =
        MethodType.methodType(Integer.class, Integer.class);
MethodType generic =
        MethodType.methodType(Object.class, Object.class);
~~~

Tham số **đầu tiên** của `MethodType.methodType` là **return type**, các tham số tiếp theo là **parameter types**. Ba mô tả trên lần lượt được biểu diễn:

~~~text
(int)int
(Integer)Integer
(Object)Object
~~~

Bảng so sánh:

| `MethodType` | Tham số | Kiểu trả về | Có primitive? |
|---|---|---|---|
| `(int)int` | `int` | `int` | Có |
| `(Integer)Integer` | `Integer` | `Integer` | Không |
| `(Object)Object` | `Object` | `Object` | Không |
| `(int)Object` | `int` | `Object` | Có |

`MethodType.equals` so sánh cả kiểu trả về lẫn **từng kiểu tham số**, không so sánh giá trị dữ liệu.

~~~java
System.out.println(primitive.equals(wrapper)); // false
System.out.println(wrapper.equals(generic));   // false
System.out.println(primitive.equals(generic)); // false
~~~

**Lưu ý:** Kiểu trả về cũng là một phần của descriptor. `(int)int` và `(int)Object` **khác nhau** mặc dù đều nhận một `int`.

### wrap(), unwrap() và generic() chỉ tạo MethodType mới

`MethodType` cung cấp các helper:

~~~java
MethodType p = MethodType.methodType(int.class, int.class);

System.out.println(p.wrap());     // (Integer)Integer
System.out.println(p.generic());  // (Object)Object
System.out.println(p.wrap().unwrap().equals(p)); // true
~~~

- `wrap()` thay các primitive bằng wrapper tương ứng.
- `unwrap()` chuyển wrapper tương ứng về primitive.
- `generic()` đưa tham số và return type về `Object`.
- Các thao tác này **chỉ tạo/biến đổi đối tượng MethodType**, không tự thay đổi handle đang có.

Muốn một handle có kiểu khác cần dùng adapter như `asType(...)` và tuân thủ quy tắc chuyển đổi của API.

## 3. Tạo ba handle tương ứng bằng MethodHandles.identity

`MethodHandles.identity(type)` tạo handle nhận một tham số `type` và trả về chính tham số đó.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;

MethodHandle primitive = MethodHandles.identity(int.class);
MethodHandle wrapper = MethodHandles.identity(Integer.class);
MethodHandle generic = MethodHandles.identity(Object.class);

System.out.println(primitive.type()); // (int)int
System.out.println(wrapper.type());   // (Integer)Integer
System.out.println(generic.type());   // (Object)Object
~~~

`identity(int.class)` không “giống hệt” `identity(Integer.class)` ở cấp MethodHandle. Cả hai có thể trả giá trị in ra `42`, nhưng một handle có primitive `int`, handle còn lại có reference `Integer`.

Trong ứng dụng thực tế, chữ ký tương tự được tạo bởi `MethodHandles.Lookup.findStatic`, `findVirtual` hoặc `unreflect`. Vì `identity` không phụ thuộc phương thức của ứng dụng, nó phù hợp để cô lập và kiểm chứng hành vi chuyển đổi kiểu.

## 4. invokeExact: chữ ký tại call site phải trùng hoàn toàn

Theo Javadoc, `invokeExact` là phương thức **signature-polymorphic**. JVM so khớp descriptor được biên dịch tại call site với `MethodHandle.type()`:

- Kiểu và số lượng tham số phải trùng.
- **Kiểu trả về** cũng phải trùng.
- Không có boxing, unboxing hoặc ép kiểu reference tự động để sửa một descriptor không khớp.
- Sai descriptor sẽ gây `WrongMethodTypeException` trước khi hành vi của target được gọi.

Các lời gọi **đúng**:

~~~java
MethodHandle p = MethodHandles.identity(int.class);
MethodHandle w = MethodHandles.identity(Integer.class);
MethodHandle o = MethodHandles.identity(Object.class);

int n = (int) p.invokeExact(42);

Integer boxed = (Integer)
        w.invokeExact(Integer.valueOf(42));

Object ref = (Object)
        o.invokeExact((Object) Integer.valueOf(42));
~~~

Ở dòng thứ ba, object runtime có thể là `Integer`, nhưng lời gọi được ép tĩnh thành `Object` để khớp handle `(Object)Object`.

Các lời gọi **không khớp**:

~~~java
// Handle (int)int; call site là (Integer)Integer:
Integer wrongArg = (Integer)
        p.invokeExact(Integer.valueOf(42));

// Handle (int)int; call site là (int)Object:
Object wrongReturn = (Object)
        p.invokeExact(42);

// Runtime value là Integer nhưng biến có kiểu tĩnh Object.
// Handle cần int, call site là (Object)int:
Object value = Integer.valueOf(42);
int wrongStaticType = (int) p.invokeExact(value);
~~~

Cả ba trường hợp đều dẫn đến `WrongMethodTypeException`. Đây là lỗi **chữ ký**, không phải vì giá trị `42` sai về toán học.

### Kiểu trả về phụ thuộc ngữ cảnh của lời gọi

Vì `invokeExact` là signature-polymorphic, kiểu ở phía **trái phép gán**, ép kiểu ngay trên expression hoặc ngữ cảnh dùng kết quả ảnh hưởng descriptor mà compiler ghi vào bytecode.

~~~java
// Đúng: caller mong đợi int.
int answer = (int) p.invokeExact(42);

// Sai: caller mong đợi Object, target trả int.
Object answerAsObject = (Object) p.invokeExact(42);
~~~

`(Object)` ở ví dụ sai không phải “hãy boxing kết quả int” theo cơ chế của `invokeExact`; nó khiến call site mô tả return type `Object` và mismatch `(int)int`.

Tương tự, nếu bỏ hẳn kết quả:

~~~java
p.invokeExact(42); // Call site được xem như trả void; không khớp (int)int.
~~~

**Mẹo khi đọc stack trace:** kiểm tra `handle.type()` và các kiểu tĩnh tại dòng `invokeExact`, bao gồm return type. Đừng chỉ kiểm tra kiểu runtime của đối tượng chứa giá trị.

## 5. invoke: cho phép chuyển đổi như asType khi hợp lệ

`MethodHandle.invoke` cũng signature-polymorphic, nhưng linh hoạt hơn `invokeExact`. Nếu descriptor tại call site khác `handle.type()`, JVM có thể điều chỉnh **như thể** áp dụng `handle.asType(callSiteType)` rồi gọi theo kiểu chính xác.

Ví dụ, handle `(int)int` có thể được gọi qua các dạng:

~~~java
MethodHandle primitive = MethodHandles.identity(int.class);

// (int)int: trùng trực tiếp.
int direct = (int) primitive.invoke(42);

// (Integer)Integer: unbox tham số, box giá trị trả về.
Integer boxed = (Integer)
        primitive.invoke(Integer.valueOf(42));

// (Object)Object: cast/unbox object đầu vào;
// box int đầu ra thành Integer rồi xem như Object.
Object generic = (Object)
        primitive.invoke((Object) Integer.valueOf(42));
~~~

Cả ba có thể tạo giá trị `42`, nhưng đường đi chuyển đổi khác nhau.

| Call site của `invoke` | Handle gốc | Chuyển đổi bắt buộc |
|---|---|---|
| `(int)int` | `(int)int` | Không cần adapter. |
| `(Integer)Integer` | `(int)int` | `Integer → int` (unbox); `int → Integer` (box). |
| `(Object)Object` với runtime `Integer` | `(int)int` | `Object → int` (cast/unbox); `int → Integer → Object`. |

Khả năng điều chỉnh **không đồng nghĩa chấp nhận mọi giá trị**:

~~~java
Object wrong = (Object) "42";

// Không tự parse "42" thành int:
Object failed = (Object) primitive.invoke(wrong);
~~~

Ở ví dụ trên, kiểu tĩnh `Object` cho phép tạo adapter `(Object)Object`, nhưng giá trị runtime là `String`, không phải wrapper số phù hợp. Khi cố unbox, conversion thất bại với `ClassCastException`.

Với `null`:

~~~java
Object missing = null;
Object failed = (Object) primitive.invoke(missing);
// NullPointerException khi adapter cần unbox thành int.
~~~

Nếu không tồn tại phép chuyển đổi phù hợp về mặt **kiểu**, `invoke` hoặc `asType` thất bại bằng `WrongMethodTypeException`. Nếu adapter tạo được nhưng **giá trị runtime** không dùng được, lỗi thường là `ClassCastException` hoặc `NullPointerException`.

## 6. asType: tạo một góc nhìn có kiểu khác, không đổi handle gốc

Có thể tạo adapter tường minh:

~~~java
MethodHandle primitive = MethodHandles.identity(int.class);

MethodType boxedType =
        MethodType.methodType(Integer.class, Integer.class);

MethodHandle boxedView = primitive.asType(boxedType);

System.out.println(primitive.type()); // (int)int
System.out.println(boxedView.type()); // (Integer)Integer

Integer result = (Integer)
        boxedView.invokeExact(Integer.valueOf(42));
~~~

Ở đây:

1. `primitive` vẫn có kiểu `(int)int` và không bị thay đổi.
2. `boxedView` công khai kiểu `(Integer)Integer`.
3. Khi gọi `boxedView.invokeExact` với `Integer`, descriptor trùng **adapter**.
4. Adapter thực hiện unboxing trước khi gọi handle gốc và boxing khi trả về.

Cũng có thể tạo adapter generic:

~~~java
MethodType objectType =
        MethodType.methodType(Object.class, Object.class);

MethodHandle objectView = primitive.asType(objectType);

Object result = (Object) objectView.invokeExact(
        (Object) Integer.valueOf(42));
~~~

Adapter này chấp nhận call site `(Object)Object`, nhưng **không bảo đảm mọi object runtime hợp lệ**:

| Giá trị truyền cho `objectView` | Diễn biến |
|---|---|
| `Integer.valueOf(42)` | Unbox được thành `int`, trả về `Integer` trong `Object`. |
| Một wrapper có thể unbox rồi widening phù hợp | Có thể được chấp nhận theo hợp đồng `asType`. |
| `"42"` | `ClassCastException`, vì `String` không phải wrapper có thể unbox thành `int`. |
| `null` | `NullPointerException` khi unbox thành `int`. |

### asType không cho phép mọi chuyển đổi số

`asType` tuân theo các chuyển đổi primitive widening và chuyển đổi boxing/unboxing hợp lệ, **không** thực hiện mọi narrowing hay parse chuỗi.

~~~java
MethodHandle primitive = MethodHandles.identity(int.class);

// Adapter cần nhận long rồi chuyển long -> int: narrowing,
// không được asType tự cho phép.
primitive.asType(MethodType.methodType(int.class, long.class));
// WrongMethodTypeException.
~~~

Nếu thực sự cần chuyển đổi tường minh có semantics khác, xem `MethodHandles.explicitCastArguments` hoặc dựng một adapter chủ động xử lý chuyển đổi dữ liệu, với kiểm thử tràn/narrowing. Đừng mặc định chuyển đổi kiểu nguy hiểm là miễn phí hoặc giữ nguyên thông tin.

## 7. Một chương trình Java 18+ kiểm chứng đầy đủ

Lưu tệp `PrimitiveWrapperObjectDemo.java`. Ví dụ **không cần thư viện ngoài, DNS hoặc preview feature**; các type và giá trị được lựa chọn để cô lập từng quy tắc.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class PrimitiveWrapperObjectDemo {

    @FunctionalInterface
    private interface ThrowingAction {
        void run() throws Throwable;
    }

    private static void expect(
            String label,
            Class<? extends Throwable> expected,
            ThrowingAction action) throws Throwable {
        try {
            action.run();
            throw new AssertionError(
                    "Expected " + expected.getSimpleName()
                    + " for " + label);
        } catch (Throwable failure) {
            if (!expected.isInstance(failure)) {
                throw new AssertionError(
                        "Unexpected error for " + label, failure);
            }
            System.out.println(label + ": "
                    + failure.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle p = MethodHandles.identity(int.class);
        MethodHandle w = MethodHandles.identity(Integer.class);
        MethodHandle o = MethodHandles.identity(Object.class);

        System.out.println("TYPES: " + p.type()
                + " | " + w.type() + " | " + o.type());

        MethodType pType = MethodType.methodType(int.class, int.class);
        MethodType wType =
                MethodType.methodType(Integer.class, Integer.class);
        MethodType oType =
                MethodType.methodType(Object.class, Object.class);

        if (!p.type().equals(pType)
                || !w.type().equals(wType)
                || !o.type().equals(oType)
                || pType.equals(wType)
                || wType.equals(oType)) {
            throw new AssertionError("MethodType contract mismatch");
        }

        // invokeExact: phải khớp cả parameter và return.
        int exactInt = (int) p.invokeExact(42);
        Integer exactWrapper =
                (Integer) w.invokeExact(Integer.valueOf(42));
        Object exactObject =
                (Object) o.invokeExact((Object) Integer.valueOf(42));

        System.out.println("EXACT_INT=" + exactInt);
        System.out.println("EXACT_INTEGER=" + exactWrapper);
        System.out.println("EXACT_OBJECT=" + exactObject);

        // Wrapper có thể null vì không phải primitive.
        Integer nullable = (Integer) w.invokeExact((Integer) null);
        System.out.println("EXACT_NULL_WRAPPER=" + nullable);

        // invoke: tự thích ứng khi có boxing/unboxing hợp lệ.
        Integer inexactWrapper =
                (Integer) p.invoke(Integer.valueOf(42));
        Object inexactObject =
                (Object) p.invoke((Object) Integer.valueOf(42));

        System.out.println("INVOKE_INTEGER=" + inexactWrapper);
        System.out.println("INVOKE_OBJECT=" + inexactObject);

        // Adapter tường minh: handle gốc vẫn giữ type (int)int.
        MethodHandle boxedView = p.asType(wType);
        MethodHandle objectView = p.asType(oType);

        Integer fromBoxedAdapter =
                (Integer) boxedView.invokeExact(Integer.valueOf(42));
        Object fromObjectAdapter =
                (Object) objectView.invokeExact((Object) Integer.valueOf(42));

        System.out.println("ADAPTED_INTEGER=" + fromBoxedAdapter);
        System.out.println("ADAPTED_OBJECT=" + fromObjectAdapter);

        // invokeWithArguments nhận Object và box primitive return.
        Object viaArguments = p.invokeWithArguments(Integer.valueOf(42));
        System.out.println("WITH_ARGUMENTS=" + viaArguments);

        // Sai argument descriptor: (Integer)Integer != (int)int.
        expect("WRONG_EXACT_ARGUMENT",
                WrongMethodTypeException.class,
                () -> {
                    Integer unused =
                            (Integer) p.invokeExact(Integer.valueOf(42));
                });

        // Sai return descriptor: (int)Object != (int)int.
        expect("WRONG_EXACT_RETURN",
                WrongMethodTypeException.class,
                () -> {
                    Object unused = (Object) p.invokeExact(42);
                });

        // Kiểu tĩnh Object khác int, dù runtime là Integer.
        expect("WRONG_STATIC_TYPE",
                WrongMethodTypeException.class,
                () -> {
                    Object value = Integer.valueOf(42);
                    int unused = (int) p.invokeExact(value);
                });

        // Adapter tồn tại, nhưng runtime object không thể unbox.
        expect("RUNTIME_WRONG_WRAPPER",
                ClassCastException.class,
                () -> {
                    Object unused =
                            (Object) objectView.invokeExact((Object) "42");
                });

        // Adapter tồn tại, nhưng unboxing null -> NPE.
        expect("RUNTIME_NULL_UNBOX",
                NullPointerException.class,
                () -> {
                    Object unused =
                            (Object) objectView.invokeExact((Object) null);
                });

        // asType không tự làm narrowing primitive long -> int.
        expect("NARROWING_NOT_ALLOWED",
                WrongMethodTypeException.class,
                () -> {
                    p.asType(MethodType.methodType(int.class, long.class));
                });
    }
}
~~~

Biên dịch/chạy bằng JDK 18+:

~~~shell
javac PrimitiveWrapperObjectDemo.java
java PrimitiveWrapperObjectDemo
~~~

Kết quả mong đợi:

~~~text
TYPES: (int)int | (Integer)Integer | (Object)Object
EXACT_INT=42
EXACT_INTEGER=42
EXACT_OBJECT=42
EXACT_NULL_WRAPPER=null
INVOKE_INTEGER=42
INVOKE_OBJECT=42
ADAPTED_INTEGER=42
ADAPTED_OBJECT=42
WITH_ARGUMENTS=42
WRONG_EXACT_ARGUMENT: WrongMethodTypeException
WRONG_EXACT_RETURN: WrongMethodTypeException
WRONG_STATIC_TYPE: WrongMethodTypeException
RUNTIME_WRONG_WRAPPER: ClassCastException
RUNTIME_NULL_UNBOX: NullPointerException
NARROWING_NOT_ALLOWED: WrongMethodTypeException
~~~

**Ý nghĩa của ví dụ:** cùng các dòng chứa số `42`, nhưng `MethodHandle.type()` và kiểu ở call site quyết định cách gọi được chấp nhận. Các ca lỗi giúp tách sai **descriptor** khỏi sai **giá trị runtime**.

Trong helper `expect`, `catch (Throwable)` chỉ dùng để **kiểm chứng**, nhằm quan sát chính xác lỗi từ `MethodHandle`. Code ứng dụng nên bắt các lỗi dự kiến theo chính sách cụ thể, không bắt `Throwable` rộng rồi bỏ qua `Error` của JVM.

## 8. Nhận diện lỗi theo giai đoạn thay vì nhìn giá trị

| Quan sát | Tầng xảy ra lỗi | Cần kiểm tra |
|---|---|---|
| `WrongMethodTypeException` khi `invokeExact` | Descriptor call site không trùng `handle.type()`. | Kiểu tĩnh arguments **và return**; số lượng, thứ tự tham số. |
| `WrongMethodTypeException` khi `invoke`/`asType` | Không tạo được adapter phù hợp về mặt kiểu. | Cặp kiểu nguồn/đích; có đang cần narrowing không được hỗ trợ? |
| `ClassCastException` khi chuyển từ `Object` | Adapter có thể tạo được nhưng object runtime không cast/unbox được. | Object thật là kiểu gì? `String` không phải `Integer`. |
| `NullPointerException` khi unboxing | Đối số reference là `null` nhưng target cần primitive. | Nullable data boundary; kiểm tra trước khi gọi. |
| Kết quả `Integer` dù handle trả `int` | Chế độ gọi/adapter có boxing kiểu trả về. | `invoke`, `asType`, `invokeWithArguments`. |
| Handle `(Object)Object` nhận `Integer` bình thường | `Object` là reference supertype; target trả chính reference. | Đừng lầm chấp nhận object với việc thực hiện arithmetic int. |

Một mẹo debug hiệu quả:

~~~java
System.out.println("Target type: " + handle.type());
System.out.println("Argument runtime class: "
        + (arg == null ? "null" : arg.getClass().getName()));
~~~

Để biết **kiểu tĩnh của call site**, phải xem source và cast trên biểu thức `invokeExact`/`invoke`, hoặc descriptor bytecode khi cần điều tra nâng cao. `arg.getClass()` chỉ cho biết kiểu runtime; nó không thay thế kiểu compile time đã được compiler ghi vào call site.

## 9. Boxing, null và dữ liệu từ collection/JSON

Trong ứng dụng thật, dữ liệu từ `Map<String, Object>`, collection hoặc parser JSON thường đi vào API dưới dạng `Object`:

~~~java
Object input = payload.get("quantity"); // Có thể là Integer, Long, String, null...
~~~

Nếu target handle yêu cầu `int`, cần một **ranh giới chuẩn hóa dữ liệu**:

~~~java
static int requireInt(Object value) {
    if (!(value instanceof Integer number)) {
        throw new IllegalArgumentException(
                "quantity must be an Integer");
    }
    return number.intValue();
}

// Target type (int)int, exact call.
int quantity = requireInt(input);
int normalized = (int) intHandle.invokeExact(quantity);
~~~

Đây là lựa chọn hợp lý khi hợp đồng ứng dụng yêu cầu **đúng Integer**. Nếu muốn chấp nhận các `Number` khác, phải định nghĩa rõ quy tắc chuyển đổi, tràn số/narrowing và cách làm tròn. Đừng phụ thuộc `asType` để tự parse chuỗi, tự kiểm tra phạm vi dữ liệu hoặc tự sửa loại giá trị mà JSON parser trả về.

Với handle `(Integer)Integer`, `null` có thể được truyền qua hoặc xử lý bởi code mục tiêu, tùy method. Với handle `(int)int`, giá trị null bắt buộc phải được xử lý **trước khi unbox**; không có primitive `int` null.

## 10. Đừng nhầm MethodHandle với Method.invoke của reflection

`java.lang.reflect.Method.invoke` và `MethodHandle.invokeExact/invoke` **không có cùng hợp đồng gọi**:

| Đặc điểm | `Method.invoke` | `MethodHandle.invokeExact` | `MethodHandle.invoke` |
|---|---|---|---|
| Kiểu arguments ở API | `Object...` | Descriptor call site thực tế | Descriptor call site thực tế |
| Matching descriptor | Theo hợp đồng reflection | Phải **khớp tuyệt đối** `MethodType` | Có thể thích ứng như `asType` |
| Boxing/unboxing | Theo quy tắc invocation của reflection | **Không tự sửa mismatch** | Có thể chuyển đổi khi hợp lệ |
| Lỗi target ném | Thường được bọc trong `InvocationTargetException` | Throwable từ target truyền qua không bị bọc theo cách reflection | Tương tự handle, không tự bọc như reflection |
| Lỗi sai chữ ký | Có thể `IllegalArgumentException` | `WrongMethodTypeException` | `WrongMethodTypeException` nếu không chuyển đổi được |

JEP 416 tái triển khai core reflection bằng method handles nhưng **không xóa các khác biệt API công khai**. Không nên suy ra rằng `Method.invoke` từ Java 18 trở đi có hợp đồng `invokeExact` chỉ vì JVM dùng method handles ở tầng implementation.

## 11. Những lỗi phổ biến

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| “Cùng in ra 42 nên kiểu giống nhau.” | `int`, `Integer`, `Object` có descriptor khác. | In `handle.type()` và xem kiểu tĩnh. |
| Dùng `invokeExact` với biến `Object` cho target `int`. | Call site là `(Object)...`, không khớp `(int)...`. | Chuẩn hóa và ép kiểu trước, hoặc dùng adapter. |
| Chỉ kiểm tra parameter types. | Return type cũng nằm trong `MethodType`. | Kiểm tra cả cast/ngữ cảnh nhận kết quả. |
| Cho rằng `(Object) p.invokeExact(42)` boxing kết quả. | Call site yêu cầu `Object` nhưng handle trả `int`. | Dùng `invoke` hoặc `asType` khi cần boxing. |
| Dùng `asType` để parse `"42"`. | Adapter không tự parse string. | Parse/validate dữ liệu ở tầng ứng dụng. |
| Cho rằng adapter generic chấp nhận mọi object. | Runtime unboxing có thể thất bại. | Kiểm tra `getClass()` và null. |
| Cho rằng wrapper `Integer` không thể null. | Wrapper là reference. | Kiểm tra null khi cần primitive. |
| Nhầm `wrap()` làm thay đổi handle. | `MethodType.wrap()` chỉ trả MethodType khác. | Tạo adapter bằng `handle.asType(...)`. |
| Lấy mọi mismatch làm `WrongMethodTypeException`. | Adapter có thể tạo được rồi runtime ném CCE/NPE. | Phân biệt type adaptation và value conversion. |
| Mặc định chuyển primitive narrowing bằng `asType`. | `asType` không cho mọi narrowing conversion. | Dùng chuyển đổi chủ động, có test về range. |

## 12. Checklist kiểm chứng trên JDK đang dùng

- [ ] In `handle.type()` cho từng target.
- [ ] Đối chiếu `MethodType.methodType`: return type **đứng trước** parameter types.
- [ ] Thử `invokeExact` với `int`, `Integer` và `Object` theo đúng descriptor.
- [ ] Tạo ca sai chỉ **argument type** và ca sai chỉ **return type**.
- [ ] Thử `invoke` để quan sát boxing/unboxing khi `asType` hợp lệ.
- [ ] Tạo `asType((Integer)Integer)` và `asType((Object)Object)` từ handle `(int)int`.
- [ ] Thử `Object` đang giữ `Integer`, `String` và `null`.
- [ ] Phân loại `WrongMethodTypeException`, `ClassCastException` và `NullPointerException`.
- [ ] Thử `invokeWithArguments` để thấy primitive return được boxed.
- [ ] Không suy ra tính đúng từ chuỗi in ra `42`; kiểm tra cả type và exception.
- [ ] Ghi JDK/version trong báo cáo khi so sánh hành vi hoặc hiệu năng.

## 13. Câu hỏi tự đánh giá

1. `int raw = 42`, `Integer boxed = 42` và `Object value = 42` giống nhau ở đâu, khác nhau ở đâu?
2. Vì sao `MethodType.methodType(int.class, int.class)` không bằng `MethodType.methodType(Integer.class, Integer.class)`?
3. Với handle `(int)int`, tại sao `Integer result = (Integer) handle.invokeExact(Integer.valueOf(42))` ném `WrongMethodTypeException`?
4. Tại sao kiểu trả về của biểu thức `invokeExact` quan trọng ngang với kiểu tham số?
5. `invoke` có thể chấp nhận `Integer` cho handle cần `int` bằng cách nào?
6. Nếu handle đã được `asType((Object)Object)`, vì sao truyền `"42"` vẫn có thể ném `ClassCastException`?
7. Vì sao `null` hợp lệ với handle `(Integer)Integer` nhưng thất bại khi adapter phải unbox thành `int`?
8. `MethodType.wrap()` có tự thay đổi handle `(int)int` thành `(Integer)Integer` không?
9. `invokeWithArguments` trả kết quả primitive như thế nào?
10. Vì sao không được suy ra hợp đồng của `Method.invoke` từ implementation nội bộ của JEP 416?

**Ghi nhớ:** MethodHandle được gọi theo **descriptor**, không theo “giá trị nhìn giống nhau”. `invokeExact` đòi khớp tuyệt đối `MethodType` (bao gồm return type); `invoke` có thể thích ứng như `asType`; adapter chỉ chuyển đổi trong giới hạn được cho phép và còn có thể gặp lỗi khi runtime object không phù hợp. `int`, `Integer` và `Object` là ba kiểu khác nhau dù đều có thể biểu diễn/giữ dữ liệu số 42.

## Tài liệu tham khảo chính thức

- [Java SE 26: `MethodHandle` – `invokeExact`, `invoke`, `invokeWithArguments`, `asType`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandle.html).
- [Java SE 26: `MethodType` – descriptor, primitive/wrapper, `wrap()` và `generic()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodType.html).
- [Java SE 26: `MethodHandles` – `identity` và các adapter](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html).
- [Java SE 26: `WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/WrongMethodTypeException.html).
- [OpenJDK JEP 416 – Reimplement Core Reflection with Method Handles (Java 18)](https://openjdk.org/jeps/416).
