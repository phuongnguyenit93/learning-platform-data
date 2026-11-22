# ConstantBootstraps và các bootstrap dùng sẵn trong Java 11

**Chủ đề cha:** Hằng số động  
**Trọng tâm:** `java.lang.invoke.ConstantBootstraps` — các bootstrap method dựng sẵn cho `CONSTANT_Dynamic`, cơ chế JVM resolution, sử dụng đúng `Lookup`/`name`/`type`, tham số tĩnh, các lỗi thường gặp và tình huống nên dùng. Bài chỉ tập trung kiến thức **vẫn còn áp dụng hiện nay** và các API thực sự có ở Java 11; ví dụ được biên dịch với `javac --release 11`, không dùng `jdk.internal.*` hoặc API nội bộ dễ bị thay đổi.

Java 11 bổ sung `CONSTANT_Dynamic` (thường gọi **condy**) qua JEP 309. Khác với hằng số được biểu diễn trực tiếp trong constant pool bằng giá trị có sẵn, một dynamic constant được mô tả bởi **tên, field descriptor, một bootstrap method và các bootstrap arguments**. Khi JVM cần sử dụng hằng số, nó gọi bootstrap để tạo ra giá trị, kiểm tra kiểu và giữ giá trị được chọn như một constant đã resolve trong run-time constant pool. Điều này phục vụ chủ yếu **compiler, bytecode generator, runtime ngôn ngữ trên JVM và thư viện infrastructure**, chứ không phải cú pháp mới để người viết Java ứng dụng thay mọi `static final`.

`ConstantBootstraps` là lớp công khai trong `java.lang.invoke`, cung cấp những bootstrap có sẵn như `nullConstant`, `primitiveClass`, `enumConstant`, `getStaticFinal`, `invoke` và các bộ tạo `VarHandle`. Dùng các phương thức này giúp tool phát sinh classfile giảm lượng boilerplate bootstrap riêng và tận dụng kiểm tra quyền truy cập của `MethodHandles.Lookup`.

## 1. Mục tiêu

Sau bài này bạn có thể:

1. Mô tả `CONSTANT_Dynamic` (tag **17**, class file major **55**) và sự khác nhau với `CONSTANT_InvokeDynamic` (tag **18**).
2. Giải thích vai trò của `BootstrapMethods` attribute, `bootstrap_method_attr_index`, `CONSTANT_NameAndType`, field descriptor và lệnh `ldc`/`ldc_w`/`ldc2_w`.
3. Hiểu ba đối số JVM truyền đầu tiên khi resolve condy: `MethodHandles.Lookup`, `String name` và `Class<?> type`; các static arguments xuất hiện sau đó.
4. Liệt kê và áp dụng **đúng các bootstrap có sẵn của Java SE 11**: `nullConstant`, `primitiveClass`, `enumConstant`, hai overload `getStaticFinal`, `invoke`, `fieldVarHandle`, `staticFieldVarHandle`, `arrayVarHandle`.
5. Phân biệt lời gọi trực tiếp `ConstantBootstraps.foo(...)` với **resolution/cache** do JVM thực hiện qua entry `CONSTANT_Dynamic`.
6. Dự đoán lỗi khi descriptor sai, enum name sai, field thiếu/không `final`, lookup không đủ quyền, bootstrap trả sai kiểu hoặc ném exception.
7. Chạy một demo thuần Java 11 gọi bootstrap trực tiếp và một demo **tạo classfile thật** chứa các entry `CONSTANT_Dynamic` mà không cần thư viện nội bộ.
8. Thiết kế bootstrap an toàn khi nhiều thread chạy lần đầu: không dựa vào tác dụng phụ “chính xác một lần” dưới tranh chấp resolution.
9. Xác định lúc nên dùng condy và lúc nên dùng `static final`, `enum`, `MethodHandle` hay API Java đơn giản hơn.

## 2. Hằng số động hoạt động ở lớp nào?

Một class file Java 11 có thể chứa cấu trúc:

```text
constant_pool:
  CONSTANT_Dynamic_info {
      u1 tag = 17
      u2 bootstrap_method_attr_index
      u2 name_and_type_index
  }

BootstrapMethods attribute:
  bootstrap_methods[bootstrap_method_attr_index]:
      bootstrap_method_ref  -> CONSTANT_MethodHandle
      bootstrap_arguments[] -> các loadable constants

CONSTANT_NameAndType:
  name_index       -> tên symbolic constant
  descriptor_index -> FIELD descriptor, ví dụ Ljava/lang/String;
```

Trước khi giá trị được dùng, JVM resolve symbolic reference đó, chuyển descriptor thành kiểu `Class<?>` và gọi bootstrap được chỉ định:

```java
// Pseudocode về ý nghĩa, KHÔNG phải một lệnh Java compiler sinh condy:
Object value = bootstrap(lookupForReferencingClass, name, expectedType,
                         resolvedStaticArg1, resolvedStaticArg2);
```

Dữ liệu từ bootstrap phải tương thích với kiểu được khai báo trong `CONSTANT_NameAndType`. Sau khi resolution thành công, JVM dùng giá trị được **chọn và cache** cho entry symbolic constant đó. Vì thế “dynamic” chỉ nói **giá trị được tính khi runtime**, không nói “được tính lại mỗi lần `ldc` chạy”.

### 2.1 So sánh condy, static final và invokedynamic

| Cơ chế | Đối tượng được tạo/resolve | Cách sử dụng | Tính chất |
|---|---|---|---|
| Literal `"hello"`, integer constant | Giá trị có sẵn trong pool | `ldc` | Không cần bootstrap condy |
| `static final` field Java | Giá trị field do Java initialization/`ConstantValue` quy định | `getstatic` hoặc literal được compiler inline | Là thành viên lớp, không mặc nhiên là `CONSTANT_Dynamic` |
| `CONSTANT_Dynamic` (tag 17) | **Một giá trị có kiểu field descriptor** | `ldc`, `ldc_w`, `ldc2_w` hoặc bootstrap static argument | Resolve, chọn kết quả và cache |
| `CONSTANT_InvokeDynamic` (tag 18) | **Một `CallSite`** phù hợp method descriptor | `invokedynamic` | Link dynamic call site rồi invoke target |
| `MethodHandle` | Đối tượng biểu diễn method/field access | `invokeExact`, `invoke` hoặc static arg | Không tự là dynamic constant nếu chưa đặt vào entry condy |
| `VarHandle` | Đối tượng thao tác biến/field/array element | `get/set/compareAndSet` | Là handle, không phải snapshot dữ liệu ở field |

Điểm phân biệt quan trọng: **`invokedynamic` resolve `CallSite`**, còn **`CONSTANT_Dynamic` resolve một giá trị**. Một string, enum, class mirror, MethodHandle, VarHandle hay object khác có thể là giá trị condy nếu descriptor/loại hợp lệ. Không ghi mọi thứ liên quan đến bootstrap là `invokedynamic`.

### 2.2 Dùng ldc, ldc_w hay ldc2_w?

- `ldc` và `ldc_w` tải một giá trị từ constant pool (điểm khác là độ rộng operand index). Với `CONSTANT_Dynamic` kiểu tham chiếu, `int`, `float` hoặc các giá trị một slot khác, dùng hình thức phù hợp `ldc`/`ldc_w`.
- `ldc2_w` dành cho `long`/`double` dynamic constant có hai slot.
- Dynamic constant descriptor là **field descriptor** như `Ljava/lang/String;`, `Ljava/lang/Class;`, `I`, `J`; không phải method descriptor `()Ljava/lang/Object;`. Method descriptor dùng cho tham chiếu tới chính bootstrap method.
- Một entry condy có thể được dùng như **static argument của một bootstrap khác**, tạo cấu trúc lồng nhau. Cần tránh chu trình bootstrap args/constant resolution.

## 3. Lược đồ resolution

```text
classfile version >=55
         |
constant_pool entry tag 17
         |
CONSTANT_NameAndType(name, FIELD descriptor)
         |
BootstrapMethods[0-based index]
         | -> bootstrap MethodHandle
         | -> static args (nếu có)
         v
JVM giải quyết lookup, name, Class<?> type, static args
         |
MethodHandle.invoke(adapted arguments)
         |
       +-----------------------+
       |                       |
  Kết quả hợp lệ           Lỗi / giá trị sai kiểu
       |                       |
  Chọn & cache value      bootstrap resolution failure
       |                  BootstrapMethodError hoặc Error
       v                       |
ldc trả cached value      lần sau gặp lại cached error
```

**Khi nào bootstrap chạy?** Theo tài liệu Java SE 11, condy được resolve ngay trước **lần sử dụng đầu tiên**, chẳng hạn khi một `ldc` đẩy nó lên operand stack hoặc khi nó làm static argument của bootstrap khác. Việc chỉ nạp/định nghĩa class chưa phải lý do để khẳng định tất cả condy đã chạy.

**Bao nhiêu lần?** Ở đường chạy đơn luồng tuần tự, sau khi thành công, cùng entry không cần bootstrap nữa. Tuy nhiên nếu nhiều thread đồng thời gặp first-use, JVM **có thể gọi bootstrap nhiều lần**, rồi chỉ cài đặt **một kết quả được chọn** vào pool; các kết quả khác bị bỏ qua. Vì vậy bootstrap phải không phụ thuộc side effect “đúng một lần”, không tạo tài nguyên không thể giải phóng ở lần thua, và phải an toàn dưới concurrency. Caching áp dụng theo **symbolic reference trong runtime constant pool/class loader context**, không phải một cache toàn cầu cho mọi class.

**Lỗi cũng được nhớ:** nếu resolution thất bại, các lần truy cập sau tiếp tục thất bại theo quy tắc JVM; bootstrap không được thực hiện lại chỉ để “thử vận may”. Dùng class loader/khuôn class khác hoặc sửa chương trình là câu chuyện khác, không phải reset một condy đã resolve lỗi.

## 4. Ba đối số bootstrap đầu tiên: Lookup, name, type

Chữ ký khái quát của bootstrap cho condy:

```java
public static Object bootstrap(
        MethodHandles.Lookup lookup,
        String name,
        Class<?> type,
        /* các static arguments tùy chọn */) {
    // Trả giá trị tương thích với type.
}
```

Đây là **mẫu signature minh họa**: Java không chấp nhận cú pháp dấu phẩy/biến đổi parameter comment như một class runnable hoàn chỉnh, cần tự định nghĩa class và giá trị trả về. Các bootstrap có sẵn dùng kiểu trả về cụ thể hơn khi phù hợp.

- `lookup`: lookup context liên quan class đang tham chiếu tới condy. Quyền truy cập được JVM/`MethodHandles` kiểm tra, không phải token “superuser”.
- `name`: tên symbolic constant từ `CONSTANT_NameAndType`; có bootstrap sử dụng (ví dụ tên enum/field), có bootstrap cố ý bỏ qua.
- `type`: `Class<?>` biểu diễn **kiểu kết quả yêu cầu** từ field descriptor, khác với `MethodType` của `invokedynamic`.
- `static arguments`: những loadable constant phụ thêm được lưu trong `BootstrapMethods`. Ví dụ class khai báo field, loại phần tử field, `MethodHandle` cần gọi, số, chuỗi, hoặc condy được resolve lồng nhau.
- JVM có quy tắc thích nghi đối số/kiểu trả về tương ứng với `MethodHandle.invoke`. Không suy rằng Java compiler sẽ tự “đóng hộp” mọi descriptor sai; phải test contract cụ thể.

Trong một class file có condy tham chiếu `java.lang.invoke.ConstantBootstraps`, owner của BSM handle là `java/lang/invoke/ConstantBootstraps`, method handle thường có `REF_invokeStatic`; descriptor JVM dùng dạng `Ljava/lang/invoke/MethodHandles$Lookup;` cho đối số đầu. Ở method reference type của BSM, chữ `$` là tên nhị phân của nested class, không phải cách viết Java source import.

## 5. Toàn bộ nhóm bootstrap có sẵn trong Java SE 11

Theo Javadoc Java 11, `ConstantBootstraps` có **tám tên phương thức public static**, trong đó `getStaticFinal` có hai overload, thành **chín chữ ký**.

| Method | Giá trị tạo ra | Dữ liệu thiết yếu |
|---|---|---|
| `nullConstant(lookup,name,type)` | `null` | `type` phải là reference type |
| `primitiveClass(lookup,name,type)` | `Class<?>` của primitive | `name` là field descriptor như `I`; `type == Class.class` |
| `enumConstant(lookup,name,type)` | Hằng enum | `name` là tên enum chính xác; `type` là enum class |
| `getStaticFinal(lookup,name,type,declaringClass)` | Giá trị của field `static final` | `name` field, `type` field type, `declaringClass` chứa field |
| `getStaticFinal(lookup,name,type)` | Giá trị `static final` trong class thích hợp | `type` là class chứa constant cùng kiểu, hoặc wrapper cho primitive |
| `invoke(lookup,name,type,handle,args...)` | Kết quả gọi `MethodHandle` | `handle` và static args phải thích nghi được với kiểu đã yêu cầu |
| `fieldVarHandle(lookup,name,VarHandle.class,declaringClass,fieldType)` | `VarHandle` instance field | Lookup có quyền truy cập và field đúng kiểu |
| `staticFieldVarHandle(lookup,name,VarHandle.class,declaringClass,fieldType)` | `VarHandle` static field | Lookup có quyền truy cập và field đúng kiểu |
| `arrayVarHandle(lookup,name,VarHandle.class,arrayClass)` | `VarHandle` phần tử mảng | `arrayClass` là array type hợp lệ |

Không tự lấy danh sách phương thức từ Javadoc Java mới hơn rồi cho rằng **mọi API ở đó đã có trên Java 11**. Ví dụ `ConstantBootstraps.explicitCast` có trong một số Java đời sau, nhưng **không** thuộc danh sách Java SE 11 ở đây; mọi mã chạy bằng `--release 11` trong bài chỉ dùng đúng các API Java 11.

### 5.1 nullConstant — tạo null typed constant

Chữ ký:

```java
public static Object nullConstant(
        MethodHandles.Lookup lookup, String name, Class<?> type)
```

Nó trả `null` khi `type` là reference type, không thể tạo null của `int`/`long`/`boolean`. Đây là cách biểu diễn null như một dynamic constant typed reference, không nên nhầm với `aconst_null` bytecode truyền thống. Khi gọi trực tiếp `nullConstant(..., int.class)`, API báo `IllegalArgumentException`; khi xảy ra trong quá trình condy resolution, lỗi được áp dụng theo quy tắc bootstrap resolution.

### 5.2 primitiveClass — `Class` mirror từ field descriptor

`primitiveClass(lookup, "I", Class.class)` trả `int.class`; tên `"I"` là descriptor kiểu primitive `int` theo JVMS, không phải chuỗi `"int"`. Những descriptor thông dụng khác: `Z` (boolean), `B` (byte), `S` (short), `C` (char), `J` (long), `F` (float), `D` (double). Kết quả có kiểu `Class<?>`, vì thế condy descriptor phù hợp là `Ljava/lang/Class;`.

Không tạo `primitiveClass(..., "java.lang.Integer", Class.class)`; đây không phải primitive field descriptor. Với reference class, các cơ chế class constants thông thường có thể phù hợp hơn.

### 5.3 enumConstant — enum theo tên symbolic

`enumConstant(lookup, "SECONDS", TimeUnit.class)` trả `TimeUnit.SECONDS`. Tên phân biệt hoa/thường và phải trùng **tên enum constant**, không phải tên label hiển thị. Bootstrap chịu các quy tắc kiểm tra loại enum và accessibility; không xem enum key không hợp lệ là một hằng số default ngầm.

Có thể dùng constant dynamic cho giá trị enum do bytecode generator muốn link theo tên và kiểu. Còn ở code Java bình thường, viết trực tiếp `TimeUnit.SECONDS` là rõ ràng, không cần tạo condy.

### 5.4 getStaticFinal — đọc đúng field và yêu cầu final

Dạng đầy đủ:

```java
ConstantBootstraps.getStaticFinal(
        lookup, "MARKER", String.class, Holder.class);
```

Dạng rút gọn:

```java
ConstantBootstraps.getStaticFinal(
        lookup, "MAX_VALUE", int.class);
```

Dạng rút gọn hoạt động vì field primitive `int` có thể được tìm trong wrapper `Integer.class` như ví dụ `Integer.MAX_VALUE`. Dạng đầy đủ có tham số `declaringClass`, dùng khi cần chỉ rõ class chứa field. Cả hai phải tìm field `static final` theo quyền truy cập, tên và kiểu; field không `final` có thể gây `IncompatibleClassChangeError`, field không tồn tại có thể gây `NoSuchFieldError`, không đủ quyền có thể gây `IllegalAccessError`.

Đừng dùng `getStaticFinal` để đọc field thay đổi theo thời gian. Hãy nhớ giá trị mà condy resolve thành công sẽ được **cache**; nếu field chứa một reference tới object mutable, **reference** được giữ lại, nội dung object vẫn có thể đổi.

### 5.5 invoke — gọi MethodHandle bằng static arguments

`ConstantBootstraps.invoke(lookup, name, desiredType, handle, args...)` gọi một `MethodHandle` được truyền như static argument và thích nghi kiểu trả về theo quy tắc API. Phù hợp khi muốn tạo giá trị runtime qua factory, ví dụ chuỗi bất biến, object cấu hình bất biến hoặc method/field handle được tính một lần.

**Ví dụ trực tiếp:**

```java
MethodHandle mh = MethodHandles.lookup().findStatic(
        Demo.class, "buildLabel",
        MethodType.methodType(String.class));
Object value = ConstantBootstraps.invoke(
        MethodHandles.lookup(), "ignored", String.class, mh);
```

Đây là **trích đoạn**, class `Demo` cần có static method `buildLabel()` và các import. Nếu method handle không thích nghi được về số/kiểu đối số, có thể gặp `WrongMethodTypeException` hoặc `ClassCastException`; bootstrap có thể ném mọi `Throwable` do target invocation ném.

Đừng dùng bootstrap như hook có side effect bắt buộc (gửi email, ghi DB, increment counter nghiệp vụ) vì concurrency first-use có thể kích hoạt nhiều lần; bootstrap result được chọn mới là thứ JVM cache, không phải mọi side effect được rollback.

### 5.6 fieldVarHandle — handle cho instance field

`fieldVarHandle(lookup,"value",VarHandle.class,Holder.class,int.class)` trả VarHandle đến một instance field tên `value` kiểu `int` trong `Holder`. Khi dùng:

```java
VarHandle handle = ConstantBootstraps.fieldVarHandle(
        lookup, "value", VarHandle.class, Holder.class, int.class);
handle.set(holder, 42);
int current = (int) handle.get(holder);
```

Đây là **trích đoạn** có `lookup`, `holder` cần được tạo; field phải truy cập được và không `final` nếu muốn set. `VarHandle` là con đường truy cập field có kiểm tra kiểu/quyền; nếu handle đã resolve thành condy và cache, các lần `get` vẫn đọc **giá trị field hiện tại**, không phải giá trị field bị đóng băng.

### 5.7 staticFieldVarHandle — handle cho static field

`staticFieldVarHandle(lookup,"counter",VarHandle.class,Holder.class,int.class)` trả handle đến static field. Khi gọi `set(18)` với field không `final`, field thay đổi. Với field `final`, tập phương thức truy cập có thể bị giới hạn, không lách mutability chỉ vì handle được tạo qua condy.

Không bỏ qua concurrency/memory semantics: với shared field, chọn `getVolatile`, `setVolatile`, CAS hay operation phù hợp theo hợp đồng `VarHandle`; bản thân việc tạo handle **không tự khiến mọi truy cập là atomic read-modify-write**.

### 5.8 arrayVarHandle — handle đến phần tử mảng

`arrayVarHandle(lookup,"ignored",VarHandle.class,int[].class)` trả VarHandle cho phần tử `int[]`. Tên symbolic constant của bootstrap này **không dùng**. Khi gọi `arrayHandle.get(array,index)` hoặc `set`, truyền tọa độ gồm array reference và vị trí phần tử. Bounds check và component type vẫn được áp dụng.

### 5.9 Lưu ý đặc biệt về null, kiểu và quyền

Javadoc quy định các bootstrap method trong `ConstantBootstraps` nhìn chung ném `NullPointerException` nếu reference argument không được phép null, trừ những tham số được ghi rõ là **unused** hoặc cho phép null. Không diễn giải `name="unused"` thành một “magic value”; chỉ là tên minh họa cho method không sử dụng giá trị đó.

Các bootstrap thao tác field/enum/VarHandle dùng **`Lookup` do JVM cấp** để thực thi access control. Không cấp `MethodHandles.Lookup.IMPL_LOOKUP` hoặc sử dụng reflection deep-access trái module system; các API nội bộ của JDK không cần thiết cho bài này.

## 6. Demo chạy được 1 — gọi trực tiếp tất cả bootstrap Java 11

Ví dụ này minh họa cách dùng API thường trước khi đi vào format class file. Nó gọi trực tiếp **đầy đủ các chữ ký ConstantBootstraps chính trong Java 11**. Vì gọi như method Java bình thường, kết quả không tự trở thành `CONSTANT_Dynamic` và **không được JVM cache theo entry condy**; mục đích là học hành vi, tên, kiểu và lỗi.

Lưu thành **`ConstantBootstrapsDirectDemo.java`**:

```java
import java.lang.invoke.ConstantBootstraps;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.util.concurrent.TimeUnit;

public class ConstantBootstrapsDirectDemo {
    public static final class Holder {
        public static final String MARKER = "stable";
        public static int counter = 10;
        public int value = 7;
    }

    public static String shout(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        Object absent = ConstantBootstraps.nullConstant(
                lookup, "unused", String.class);
        System.out.println("null-reference=" + (absent == null));

        Class<?> primitive = ConstantBootstraps.primitiveClass(
                lookup, "I", Class.class);
        System.out.println("primitive-I=" + (primitive == int.class));

        TimeUnit unit = ConstantBootstraps.enumConstant(
                lookup, "SECONDS", TimeUnit.class);
        System.out.println("enum-seconds=" + (unit == TimeUnit.SECONDS));

        Object marker = ConstantBootstraps.getStaticFinal(
                lookup, "MARKER", String.class, Holder.class);
        Object max = ConstantBootstraps.getStaticFinal(
                lookup, "MAX_VALUE", int.class);
        System.out.println("static-final=" + marker);
        System.out.println("wrapper-primitive-final=" + max);

        MethodHandle method = lookup.findStatic(
                ConstantBootstrapsDirectDemo.class, "shout",
                MethodType.methodType(String.class, String.class));
        Object invoked = ConstantBootstraps.invoke(
                lookup, "unused", String.class, method, "java");
        System.out.println("invoke=" + invoked);

        VarHandle field = ConstantBootstraps.fieldVarHandle(
                lookup, "value", VarHandle.class, Holder.class, int.class);
        Holder holder = new Holder();
        field.set(holder, 13);
        System.out.println("instance-field=" + holder.value);

        VarHandle statik = ConstantBootstraps.staticFieldVarHandle(
                lookup, "counter", VarHandle.class, Holder.class, int.class);
        statik.set(18);
        System.out.println("static-field=" + Holder.counter);

        VarHandle array = ConstantBootstraps.arrayVarHandle(
                lookup, "ignored", VarHandle.class, int[].class);
        int[] items = {1, 2, 3};
        array.set(items, 1, 99);
        System.out.println("array-element=" + items[1]);

        try {
            ConstantBootstraps.nullConstant(lookup, "no", int.class);
            throw new AssertionError("Primitive null unexpectedly accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("primitive-null-rejected=true");
        }

        try {
            ConstantBootstraps.enumConstant(
                    lookup, "NOT_A_UNIT", TimeUnit.class);
            throw new AssertionError("Missing enum unexpectedly accepted");
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid-enum-rejected=true");
        }

        try {
            ConstantBootstraps.getStaticFinal(
                    lookup, "counter", int.class, Holder.class);
            throw new AssertionError("Non-final field accepted");
        } catch (IncompatibleClassChangeError expected) {
            System.out.println("nonfinal-rejected=true");
        }
    }
}
```

Chạy:

```bash
javac --release 11 -encoding UTF-8 ConstantBootstrapsDirectDemo.java
java ConstantBootstrapsDirectDemo
```

**Stdout đã biên dịch/chạy kiểm chứng:**

```text
null-reference=true
primitive-I=true
enum-seconds=true
static-final=stable
wrapper-primitive-final=2147483647
invoke=JAVA
instance-field=13
static-field=18
array-element=99
primitive-null-rejected=true
invalid-enum-rejected=true
nonfinal-rejected=true
```

**Giải thích kết quả quan trọng:**

1. `null-reference=true` cho thấy reference-typed null được hỗ trợ; `primitive-null-rejected=true` minh họa primitive không thể null.
2. `primitive-I=true`: name `I` là primitive field descriptor cho `int.class`. Kiểu result của bootstrap là `Class.class`.
3. `enum-seconds=true`: `"SECONDS"` chính xác là enum constant của `TimeUnit`.
4. `static-final=stable` dùng overload có `declaringClass`; `wrapper-primitive-final=2147483647` dùng overload rút gọn để lấy `Integer.MAX_VALUE` qua `int.class`.
5. `invoke=JAVA`: `MethodHandle` tìm phương thức `shout(String)` bằng `MethodHandles.lookup().findStatic` và bootstrap `invoke` gọi handle với một static-like argument.
6. `instance-field`, `static-field` và `array-element` cho thấy cả ba VarHandle factories trả handle có thể truy cập/đổi những biến được phép ghi.
7. `invalid-enum-rejected=true` và `nonfinal-rejected=true` cho thấy API không chấp nhận enum sai tên hoặc field static không phải final.

**Không suy ra** ví dụ này đã kiểm thử lazy resolution. Để kiểm chứng lazy/caching phải tạo **thật** một `CONSTANT_Dynamic` trong classfile.

## 7. Demo chạy được 2 — tạo class file Java 11 chứa CONSTANT_Dynamic thật

Thông thường người viết Java source không viết được một khai báo `static final` rồi tự chọn `CONSTANT_Dynamic`/bootstrap. Đây là **cơ chế classfile/JVM**. Bytecode generator có thể tạo entry tag 17 và attribute `BootstrapMethods`. Để ví dụ chạy độc lập, không phụ thuộc ASM hay API nội bộ JDK, chương trình dưới đây viết một classfile nhỏ bằng `DataOutputStream` và dùng API public `MethodHandles.lookup().defineClass(byte[])` có trên Java 11.

### 7.1 Những gì chương trình tạo

Class `CondyGenerated263` được tạo trong bộ nhớ với classfile **major 55** (Java 11). Nó có bảy static methods:

| Method trên class được sinh | BSM đã gắn | Hành vi khi gọi |
|---|---|---|
| `nullValue()` | `ConstantBootstraps.nullConstant` | Trả reference `null` |
| `primitive()` | `ConstantBootstraps.primitiveClass` | Trả `int.class` từ name `"I"` |
| `enumValue()` | `ConstantBootstraps.enumConstant` | Trả `TimeUnit.DAYS` |
| `staticFinal()` | `ConstantBootstraps.getStaticFinal` | Trả `Settings.LABEL` qua Class static argument |
| `invokedValue()` | `ConstantBootstraps.invoke` | Gọi MethodHandle `makeLabel`, nhận string |
| `custom()` | `CondyClassFileDemo.customBootstrap` | Trả object mới và test **cached identity** |
| `failure()` | `CondyClassFileDemo.failingBootstrap` | Ném exception, dẫn đến **BootstrapMethodError** và cached failure |

Mỗi method trên được phát sinh bằng cùng mẫu bytecode:

```text
ldc_w #constant_pool_index   // opcode 0x13
areturn                       // opcode 0xb0
```

Đoạn `ldc_w` trỏ đến **entry tag 17**, không phải `CONSTANT_String`. Entry đó trỏ tiếp qua `BootstrapMethods` để chọn BSM và static arguments. Chương trình dùng `MethodHandles.lookup().defineClass` để định nghĩa class cùng package với lớp chủ, sau đó reflection gọi từng method. Không có Java field `static final` nào chứa các giá trị condy được sinh.

Lưu thành **`CondyClassFileDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationTargetException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CondyClassFileDemo {
    public static final AtomicInteger BOOTSTRAP_CALLS = new AtomicInteger();
    public static final AtomicInteger FAILURE_CALLS = new AtomicInteger();

    public static final class Settings {
        public static final String LABEL = "ready";
    }

    public static Object customBootstrap(
            MethodHandles.Lookup lookup, String name, Class<?> type) {
        BOOTSTRAP_CALLS.incrementAndGet();
        return new Object();
    }

    public static Object failingBootstrap(
            MethodHandles.Lookup lookup, String name, Class<?> type) {
        FAILURE_CALLS.incrementAndGet();
        throw new IllegalStateException("expected-failure");
    }

    public static String makeLabel() {
        return "made-by-handle";
    }

    interface Writer {
        void write(DataOutputStream out) throws IOException;
    }

    static byte[] binary(Writer writer) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);
            writer.write(out);
            out.flush();
            return bytes.toByteArray();
        } catch (IOException error) {
            throw new IllegalStateException(error);
        }
    }

    static final class MethodInfo {
        final String name;
        final int constant;
        int nameIndex;

        MethodInfo(String name, int constant) {
            this.name = name;
            this.constant = constant;
        }
    }

    static final class ClassFile {
        final List<byte[]> cp = new ArrayList<>();
        final List<int[]> bootstraps = new ArrayList<>();
        final List<MethodInfo> methods = new ArrayList<>();

        int entry(Writer writer) {
            cp.add(binary(writer));
            return cp.size();
        }

        int utf8(String value) {
            return entry(out -> {
                out.writeByte(1);
                byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
                out.writeShort(bytes.length);
                out.write(bytes);
            });
        }

        int clazz(String binaryName) {
            int name = utf8(binaryName);
            return entry(out -> {
                out.writeByte(7);
                out.writeShort(name);
            });
        }

        int nameAndType(String name, String descriptor) {
            int n = utf8(name), d = utf8(descriptor);
            return entry(out -> {
                out.writeByte(12);
                out.writeShort(n);
                out.writeShort(d);
            });
        }

        int methodRef(String owner, String name, String descriptor) {
            int c = clazz(owner), nt = nameAndType(name, descriptor);
            return entry(out -> {
                out.writeByte(10);
                out.writeShort(c);
                out.writeShort(nt);
            });
        }

        int staticHandle(String owner, String name, String descriptor) {
            int ref = methodRef(owner, name, descriptor);
            return entry(out -> {
                out.writeByte(15);
                out.writeByte(6); // REF_invokeStatic
                out.writeShort(ref);
            });
        }

        int bootstrap(int handle, int... args) {
            int[] info = new int[args.length + 1];
            info[0] = handle;
            System.arraycopy(args, 0, info, 1, args.length);
            bootstraps.add(info);
            return bootstraps.size() - 1; // 0-based BootstrapMethods index
        }

        int dynamic(int bootstrap, String name, String descriptor) {
            int nt = nameAndType(name, descriptor);
            return entry(out -> {
                out.writeByte(17); // CONSTANT_Dynamic
                out.writeShort(bootstrap);
                out.writeShort(nt);
            });
        }

        void method(String name, int dynamicCpIndex) {
            methods.add(new MethodInfo(name, dynamicCpIndex));
        }

        byte[] build() {
            int self = clazz("CondyGenerated263");
            int parent = clazz("java/lang/Object");
            int codeName = utf8("Code");
            int bootsName = utf8("BootstrapMethods");
            int objectGetterDescriptor = utf8("()Ljava/lang/Object;");
            for (MethodInfo method : methods) {
                method.nameIndex = utf8(method.name);
            }
            byte[] bootstrapData = binary(out -> {
                out.writeShort(bootstraps.size());
                for (int[] bsm : bootstraps) {
                    out.writeShort(bsm[0]);
                    out.writeShort(bsm.length - 1);
                    for (int i = 1; i < bsm.length; i++) {
                        out.writeShort(bsm[i]);
                    }
                }
            });
            return binary(out -> {
                out.writeInt(0xCAFEBABE);
                out.writeShort(0);
                out.writeShort(55); // Java 11 class file
                out.writeShort(cp.size() + 1);
                for (byte[] item : cp) out.write(item);
                out.writeShort(0x0021); // public + super
                out.writeShort(self);
                out.writeShort(parent);
                out.writeShort(0); // interfaces
                out.writeShort(0); // fields
                out.writeShort(methods.size());
                for (MethodInfo method : methods) {
                    out.writeShort(0x0009); // public static
                    out.writeShort(method.nameIndex);
                    out.writeShort(objectGetterDescriptor);
                    out.writeShort(1); // one Code attribute
                    out.writeShort(codeName);
                    out.writeInt(16);
                    out.writeShort(1); // max_stack
                    out.writeShort(0); // max_locals
                    out.writeInt(4);
                    out.writeByte(0x13); // ldc_w
                    out.writeShort(method.constant);
                    out.writeByte(0xb0); // areturn
                    out.writeShort(0); // exception_table_length
                    out.writeShort(0); // code attributes_count
                }
                out.writeShort(1); // one class attribute
                out.writeShort(bootsName);
                out.writeInt(bootstrapData.length);
                out.write(bootstrapData);
            });
        }
    }

    static Object call(Class<?> cls, String method) throws Exception {
        return cls.getMethod(method).invoke(null);
    }

    public static void main(String[] args) throws Exception {
        ClassFile bytes = new ClassFile();
        String prefix = "java/lang/invoke/";
        String owner = prefix + "ConstantBootstraps";
        String bsmPrefix =
                "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;"
                + "Ljava/lang/Class;";

        int bsmNull = bytes.bootstrap(bytes.staticHandle(
                owner, "nullConstant", bsmPrefix + ")Ljava/lang/Object;"));
        int bsmPrimitive = bytes.bootstrap(bytes.staticHandle(
                owner, "primitiveClass", bsmPrefix + ")Ljava/lang/Class;"));
        int bsmEnum = bytes.bootstrap(bytes.staticHandle(
                owner, "enumConstant", bsmPrefix + ")Ljava/lang/Enum;"));

        int bsmStaticFinal = bytes.bootstrap(bytes.staticHandle(
                owner, "getStaticFinal",
                bsmPrefix + "Ljava/lang/Class;)Ljava/lang/Object;"),
                bytes.clazz("CondyClassFileDemo$Settings"));

        int labelMethod = bytes.staticHandle(
                "CondyClassFileDemo", "makeLabel", "()Ljava/lang/String;");
        int bsmInvoke = bytes.bootstrap(bytes.staticHandle(
                owner, "invoke", bsmPrefix
                + "Ljava/lang/invoke/MethodHandle;"
                + "[Ljava/lang/Object;)Ljava/lang/Object;"),
                labelMethod);

        int bsmCustom = bytes.bootstrap(bytes.staticHandle(
                "CondyClassFileDemo", "customBootstrap",
                bsmPrefix + ")Ljava/lang/Object;"));
        int bsmFail = bytes.bootstrap(bytes.staticHandle(
                "CondyClassFileDemo", "failingBootstrap",
                bsmPrefix + ")Ljava/lang/Object;"));

        bytes.method("nullValue", bytes.dynamic(
                bsmNull, "UNUSED", "Ljava/lang/String;"));
        bytes.method("primitive", bytes.dynamic(
                bsmPrimitive, "I", "Ljava/lang/Class;"));
        bytes.method("enumValue", bytes.dynamic(
                bsmEnum, "DAYS", "Ljava/util/concurrent/TimeUnit;"));
        bytes.method("staticFinal", bytes.dynamic(
                bsmStaticFinal, "LABEL", "Ljava/lang/String;"));
        bytes.method("invokedValue", bytes.dynamic(
                bsmInvoke, "UNUSED", "Ljava/lang/String;"));
        bytes.method("custom", bytes.dynamic(
                bsmCustom, "TOKEN", "Ljava/lang/Object;"));
        bytes.method("failure", bytes.dynamic(
                bsmFail, "BROKEN", "Ljava/lang/Object;"));

        byte[] classFile = bytes.build();
        Class<?> generated = MethodHandles.lookup().defineClass(classFile);
        System.out.println("class-major=55");
        System.out.println("custom-calls-before-first-use="
                + BOOTSTRAP_CALLS.get());

        System.out.println("null-condy=" +
                (call(generated, "nullValue") == null));
        System.out.println("primitive-condy=" +
                (call(generated, "primitive") == int.class));
        System.out.println("enum-condy=" +
                (call(generated, "enumValue") == TimeUnit.DAYS));
        System.out.println("static-final-condy=" +
                call(generated, "staticFinal"));
        System.out.println("invoke-condy=" +
                call(generated, "invokedValue"));

        Object first = call(generated, "custom");
        Object second = call(generated, "custom");
        System.out.println("custom-same-reference=" + (first == second));
        System.out.println("custom-bootstrap-calls="
                + BOOTSTRAP_CALLS.get());

        for (int i = 0; i < 2; i++) {
            try {
                call(generated, "failure");
                throw new AssertionError("Invalid constant was accepted");
            } catch (InvocationTargetException expected) {
                if (!(expected.getCause() instanceof BootstrapMethodError)) {
                    throw expected;
                }
                System.out.println("failed-resolution-" + (i + 1)
                        + "=BootstrapMethodError");
            }
        }
        System.out.println("failure-bootstrap-calls="
                + FAILURE_CALLS.get());
    }
}
```

Chạy (không cần `--add-exports` hoặc thư viện ngoài):

```bash
javac --release 11 -encoding UTF-8 CondyClassFileDemo.java
java CondyClassFileDemo
```

**Stdout đã kiểm chứng:**

```text
class-major=55
custom-calls-before-first-use=0
null-condy=true
primitive-condy=true
enum-condy=true
static-final-condy=ready
invoke-condy=made-by-handle
custom-same-reference=true
custom-bootstrap-calls=1
failed-resolution-1=BootstrapMethodError
failed-resolution-2=BootstrapMethodError
failure-bootstrap-calls=1
```

**Đọc kết quả theo từng mốc:**

1. `class-major=55`: classfile dùng phiên bản Java 11, nơi `CONSTANT_Dynamic` bắt đầu được JVM chấp nhận.
2. `custom-calls-before-first-use=0`: chỉ `defineClass` chưa chạy bootstrap tùy biến của entry `TOKEN`.
3. Năm kết quả `null-condy` đến `invoke-condy` lần lượt chứng minh các BSM dựng sẵn thực sự được JVM dùng để resolve constant thông qua classfile.
4. `custom-same-reference=true` chứng minh hai lần gọi method `custom()` cùng tham chiếu tới **một object được chọn và giữ trong runtime constant pool**. Đây không phải hai lần cấp phát object.
5. `custom-bootstrap-calls=1` là kết quả của **test tuần tự**. Trong test đa luồng chạy đồng thời lần đầu, JDK/JVMS cho phép bootstrap có thể chạy nhiều hơn một lần trước khi chọn một kết quả; không coi 1 là contract của mọi lịch thread.
6. `failed-resolution-1/2=BootstrapMethodError`: bootstrap ném `IllegalStateException`, resolution chuyển thành lỗi bootstrap ở nơi gọi. Sau thất bại, cùng entry không tự được thử lại.
7. `failure-bootstrap-calls=1` chứng minh việc lặp lại hai lần **tuần tự** không gọi lại bootstrap thất bại. Đây là trạng thái đã được JVM ghi nhớ cho entry đó.

### 7.2 Phân tích cấu trúc class file trong demo

`ClassFile.entry(...)` thêm phần tử CP và trả index **bắt đầu từ 1**. `ClassFile.bootstrap(...)` thêm một mục trong `BootstrapMethods` và trả index **bắt đầu từ 0**. Đây là một chỗ dễ tạo lỗi lệch một đơn vị:

```text
constant_pool indexes:        1, 2, 3, ...
BootstrapMethods array index: 0, 1, 2, ...
```

`methodRef(owner,name,descriptor)` tạo `CONSTANT_Methodref`; `staticHandle` gắn MethodHandle kind **6 = REF_invokeStatic**; `dynamic` tạo tag **17** chứa index tới bootstrap và NameAndType; `method` sinh code ngắn `ldc_w + areturn`.

`BootstrapMethods` là attribute **cấp class**, không phải attribute riêng của mỗi method. Dữ liệu của attribute là `u2 num_bootstrap_methods` theo sau các record chứa `u2 bootstrap_method_ref`, `u2 num_bootstrap_arguments` và danh sách CP indices cho static arguments.

Với `getStaticFinal`, demo truyền `Settings.class` làm **một static argument** từ `CONSTANT_Class`. Với `invoke`, static argument là `CONSTANT_MethodHandle` trỏ tới `makeLabel()`. Đây là cách một bytecode generator lắp được những constant tùy biến mà không cần định nghĩa bootstrap Java riêng cho từng pattern.

**Lưu ý phạm vi của byte writer:** classfile assembler viết tay này chỉ dùng để **giải thích cơ chế và kiểm thử**: cố ý không hỗ trợ toàn bộ UTF-8 modified, exception table, stack map frames phức tạp, interface, annotation, module metadata hay trường hợp classfile sản phẩm. Không đưa nó thành bytecode framework production. Dùng bytecode library được duy trì, hiểu classfile level và có test verifier phù hợp; tránh `jdk.internal.org.objectweb.asm` vì không phải API công khai.

### 7.3 Vì sao không thể thay demo bằng static final?

`static final String LABEL = "ready";` thường được Java compiler biểu diễn như compile-time constant và có thể được inline. Nó **không đồng nghĩa** ConstantDynamic. Demo tự tạo `CONSTANT_Dynamic` trong pool để JVM gọi bootstrap đúng lúc resolution. Vì vậy việc quan sát `CondyClassFileDemo` là kiểm thử trực tiếp tính năng **JEP 309**, không phải chỉ ví dụ method helper giả lập.

### 7.4 Liên hệ với class loader

`defineClass` gắn class được phát sinh với lookup/package/module context được phép. Hai class khác nhau hoặc hai class loader khác nhau có **runtime constant pool riêng**, nên “cache một constant” không phải “một singleton toàn bộ JVM”. Đừng dùng Condy làm nơi cất token/secret theo suy đoán vì value vẫn có thể tồn tại dài bằng vòng đời class loader.

## 8. Những lỗi và ngoại lệ thường gặp

| Tình huống | Nguyên nhân gốc | Điều cần làm |
|---|---|---|
| `nullConstant` với `int.class` | Primitive không nhận null | Dùng reference descriptor hoặc kiểu khác |
| `primitiveClass` với `"int"` | Sai field descriptor | Dùng `"I"`, `"J"`, ... theo JVMS |
| `primitiveClass` yêu cầu result không phải `Class.class` | Type contract sai | Dùng descriptor `Ljava/lang/Class;` |
| `enumConstant` với tên sai | Enum constant không tồn tại/case sai | Dùng tên constant chính xác |
| `getStaticFinal` field không tồn tại | Tên/declaringClass/field type không khớp | Kiểm tra type descriptor và owner |
| `getStaticFinal` field không `final` | BSM chỉ nhận field `static final` | Dùng VarHandle hoặc code đọc field theo nghiệp vụ |
| `getStaticFinal` field không truy cập được | Lookup thiếu quyền | Tôn trọng module/package access, không phá encapsulation |
| `invoke` với sai tham số | Handle không thích nghi kiểu/số đối số | Kiểm tra MethodType và static args |
| `fieldVarHandle` dùng owner/type sai | Không tìm được field đúng | Kiểm tra declaring class và field descriptor |
| `staticFieldVarHandle` dùng instance field | Sai hình thức truy cập | Dùng `fieldVarHandle` cho instance field |
| `arrayVarHandle` không phải array class | Sai kind | Truyền array Class, ví dụ `int[].class` |
| Condy trả object không tương thích descriptor | JVM type validation fail | BSM trả đúng kiểu yêu cầu |
| BSM ném RuntimeException | Resolution failure, thường `BootstrapMethodError` | Sửa bootstrap; không mong retry tự động cùng CP entry |
| Bootstrap recursion/self-reference | Chu trình resolution | Bỏ vòng phụ thuộc giữa dynamic constants |
| Nạp classfile 55 trên JVM trước Java 11 | Version không được hỗ trợ | Chạy trên Java 11+ |
| Coi mọi bootstrap chạy một lần tuyệt đối | Race first-use có thể gọi nhiều BSM | Thiết kế side effects idempotent/an toàn |
| Giá trị condy là mutable object | Cached reference không đồng nghĩa immutable state | Trả immutable object hoặc kiểm soát ownership |
| Lưu state theo singleton BSM | Reuse giữa nhiều classloader gây nhầm cache | Gắn ownership theo runtime context |

### 8.1 Xử lý lỗi của JVM

Nếu bootstrap ném một exception không phải `Error`, JVM có thể bọc nó thành `BootstrapMethodError` theo luật resolution. Nếu lỗi đã là subclass `Error`, nó có thể được ném theo loại lỗi đó. Các lỗi resolution ban đầu khác cũng tuân theo quy tắc JVMS; **không** viết catch chỉ dựa vào một loại exception Java duy nhất cho mọi lỗi classfile.

Điều quan trọng hơn là tính **ổn định của lỗi đã resolve**: nếu bootstrap đầu tiên lỗi, các lần sử dụng cùng entry symbolic reference tiếp theo tiếp tục thất bại, không “tự chữa” vì biến môi trường hoặc file cấu hình vừa thay đổi. Đó là lý do các BSM nên được thiết kế ổn định và giảm phụ thuộc vào điều kiện tạm thời.

### 8.2 Security và access control

`MethodHandles.Lookup` mô tả context của class đang resolve, bao gồm quyền truy cập. Bootstrap không được tùy ý bypass private fields, module boundaries hoặc export policy. Mọi input từ bên ngoài tới bytecode generator phải được validate: class owner, descriptor, bootstrap method handle, args, recursion depth và tổng kích thước classfile.

Đừng dùng `ConstantBootstraps.invoke` gọi method handle có tác dụng phụ quan trọng như remote I/O, tạo phiên đăng nhập hoặc ghi sổ kế toán. Lỗi resolution được cache; concurrent first-use có thể gọi dư; và việc chạy bootstrap xảy ra trong đường tải hằng số, có thể làm request latency khó dự đoán.

## 9. Chọn built-in bootstrap nào trong tình huống thực tế?

| Nhu cầu của tool/runtime | Bootstrap nên cân nhắc | Lý do |
|---|---|---|
| Typed null constant trong CP | `nullConstant` | Trả null reference theo descriptor |
| Primitive `Class` mirror khi name có descriptor | `primitiveClass` | Tránh tự xây dispatcher nhận chữ `I`/`J` |
| Enum constant theo symbolic name | `enumConstant` | Kiểm tra type + tên enum |
| Giá trị public/protected accessible `static final` | `getStaticFinal` | Resolution theo field, access check |
| Kết quả factory MethodHandle | `invoke` | Tạo value một lần theo condy result |
| Cached handle đến instance field | `fieldVarHandle` | Giữ handle, field value vẫn động |
| Cached handle đến static field | `staticFieldVarHandle` | Tránh lặp lookup khi thực sự cần handle |
| Cached handle đến phần tử mảng | `arrayVarHandle` | Dùng handle theo component type |
| Constant phức tạp chưa được built-in hỗ trợ | Custom bootstrap (rất thận trọng) | Kiểm soát output type, caching, side effects |

Với ứng dụng nghiệp vụ thông thường, viết `TimeUnit.SECONDS`, `Integer.MAX_VALUE`, `Class<?> cls = int.class` hoặc gọi method bình thường thường rõ ràng hơn. `CONSTANT_Dynamic` đáng học khi làm **bytecode weaving, compilers, code generation, dynamic-language runtime, ahead-of-time tooling** hoặc debug classfile hiện đại.

Nếu codebase chỉ cần một `MethodHandle` hoặc `VarHandle` cho field thông thường, có thể gọi `MethodHandles.lookup().findVarHandle`/`findStaticVarHandle` ngay trong Java source mà không tạo condy.

## 10. Hiệu năng, cache và side effects

**Không có đảm bảo “condy luôn nhanh hơn static field”.** Có chi phí resolution lần đầu, bootstrap invocation và kiểm tra kiểu; sau đó JVM có thể sử dụng cached value. Lợi ích cần benchmark ở bối cảnh compiler/runtime thật.

Phân biệt:

- **Lazy linking**: bootstrap được gọi khi constant cần dùng, không phải eager init tất cả.
- **Cache result**: cùng entry resolved có giá trị dùng lại.
- **Cache error**: lỗi resolution cũng được duy trì theo luật JVM.
- **Concurrency**: trước khi chọn result thắng, có thể có nhiều bootstrap calls. Không dùng BSM làm once-only business side effect.
- **Mutability**: cached `VarHandle` hay mutable reference vẫn có thể quan sát/thay đổi state, không phải “deep immutable”.
- **Class-loader scope**: mỗi class có runtime pool riêng; đừng nhầm cache theo caller hoặc theo class loader là toàn JVM.

Nếu constant phụ thuộc thời gian, config live, network hoặc secret quay vòng, việc cache đến hết vòng đời class loader có thể tạo **stale state**. Trong trường hợp đó, field/service lookup thông thường với quản lý lifecycle rõ có thể phù hợp hơn condy.

### 10.1 Có thể ghép bootstrap lồng nhau?

Có. `BootstrapMethods.bootstrap_arguments[]` có thể chứa entry loadable `CONSTANT_Dynamic` khác; JVM cần resolve các static arguments đó trước khi bootstrap bên ngoài được gọi. Điều này cho phép tạo graph hằng số có cấu trúc, nhưng phụ thuộc vòng/cycle gây lỗi resolution. Hạn chế nesting nếu không cần; thêm các test phát hiện recursion và thiếu type.

### 10.2 Debug cơ chế

Khi có classfile thật trên disk, dùng `javap -v SomeClass.class` để xem `Constant pool`, tag `Dynamic`, `BootstrapMethods` và code `ldc`. Trong demo thứ hai, class được tạo **trong bộ nhớ**, nên không tự có file `CondyGenerated263.class` trên disk để chạy `javap -v`. Nếu muốn thử inspect, bạn có thể điều chỉnh demo ghi `classFile` ra file trong thư mục test trước `defineClass`; đừng nhầm file đó với class nguồn do `javac` sinh.

Không tự giả định code Java:
```java
static final String X = compute();
```
sẽ tạo `CONSTANT_Dynamic`. Kiểm tra bằng `javap -v`; cơ chế khởi tạo field bình thường thường liên quan `<clinit>`, không phải tag17.

## 11. Kiểm thử và QA

| Ca kiểm thử | Kết quả cần xác minh |
|---|---|
| null của reference | `nullConstant` trả null |
| null của primitive | Bị từ chối rõ |
| primitive descriptor `I` | Trả `int.class` |
| Enum name chính xác | Trả đúng enum constant |
| Enum không tồn tại | `IllegalArgumentException` ở lời gọi trực tiếp |
| Static final field | Trả đúng giá trị |
| Field không final | Bị từ chối |
| MethodHandle invocation | Trả result đúng kiểu |
| Instance VarHandle | Lấy/set instance field |
| Static VarHandle | Lấy/set static field |
| Array VarHandle | Lấy/set array element |
| Classfile major 55 | Loader hiểu tag17 |
| Condy null/primitive/enum/staticFinal/invoke | Built-in bootstrap được gọi bởi JVM thật |
| Lazy custom bootstrap | Counter chưa tăng trước first-use |
| Cached result | Hai `ldc` cùng CP entry trả cùng reference |
| Failure caching | Hai lần truy cập cùng entry báo lỗi, không gọi lại bootstrap trong test tuần tự |
| Type mismatch | Bootstrap trả không phù hợp field descriptor thì resolution thất bại |
| Missing BSM | Bytecode không có BootstrapMethods hợp lệ thì verifier/linkage lỗi |
| Recursive static arguments | Có đường báo lỗi rõ, không treo vô hạn |
| Multiple threads first-use | Không dựa vào exactly-once side effects |
| Classloader isolation | Hai class/loader có runtime pools riêng |

Trong demo, `BOOTSTRAP_CALLS == 1` ở đường tuần tự là một quan sát có chủ đích, không phải hợp đồng concurrency. Test sản phẩm nên chạy thêm case đồng thời với latch, nhưng **không** assert “BSM phải chạy đúng một lần” dưới race.

## 12. Những hiểu nhầm hay gặp

| Nhầm lẫn | Điều đúng |
|---|---|
| `ConstantBootstraps` là cú pháp mới cho `const` | Không; nó là utility bootstrap method công khai cho classfile condy |
| `CONSTANT_Dynamic` giống `invokedynamic` | Condy tạo giá trị; indy tạo CallSite |
| Gọi `nullConstant` trực tiếp đã tạo condy | Không; phải có entry tag17/BootstrapMethods để JVM resolve/cache |
| Condy nghĩa tính lại mỗi `ldc` | Không; result đã resolve được cache |
| BSM luôn chạy đúng một lần | Có thể bị gọi nhiều lần dưới concurrent resolution |
| BSM thất bại sẽ retry lần sau | Resolution error được ghi nhớ |
| `name` luôn không quan trọng | enum/field BSM phụ thuộc name; một số BSM mới bỏ qua |
| `type` của condy là `MethodType` | Đây là `Class<?>` theo field descriptor |
| `getStaticFinal` đọc mọi field static | Yêu cầu `static final` |
| VarHandle constant làm field bất biến | Cache handle, **không** freeze field value |
| Có thể dùng `Class<?>` tùy ý thay primitive descriptor | `primitiveClass` cần name dạng `I`, `J`... |
| `getStaticFinal` có thể bypass private access | Lookup vẫn chịu kiểm tra quyền |
| Field descriptor và bootstrap method descriptor là một | Chúng là hai mô tả khác nhau |
| Dùng `jdk.internal.org.objectweb.asm` là giải pháp ổn định | Đây là API nội bộ, không được cam kết tương thích |
| Runtime Java 10 dùng được classfile 55 | Không, yêu cầu Java 11+ |
| Classfile byte writer minh họa nên dùng ngay ở production | Không, cần parser/writer chuẩn, validation, tooling duy trì |
| Dùng cache condy để giữ config động an toàn | Có thể stale, khó reload; cần lifecycle đúng |
| Mọi method ConstantBootstraps trong JDK mới đều có ở Java 11 | Phải kiểm tra chính xác Javadoc/`--release 11` |

## 13. Bài tập tự luyện có đáp án

**Bài 1.** `CONSTANT_Dynamic` có constant pool tag nào, class file major nào lần đầu hỗ trợ?  
**Đáp án:** tag `17` và classfile major `55` (Java 11).

**Bài 2.** JVM truyền ba tham số nào cho bootstrap của condy?  
**Đáp án:** `MethodHandles.Lookup` của caller, `String name` của NameAndType, `Class<?> type` từ field descriptor; sau đó là static arguments nếu có.

**Bài 3.** Dùng `primitiveClass(lookup,"I",Class.class)` nhận kết quả gì?  
**Đáp án:** `int.class`. Tên `"int"` không phải primitive field descriptor hợp lệ cho bootstrap này.

**Bài 4.** Có thể dùng `nullConstant` để tạo hằng `int` bằng 0 không?  
**Đáp án:** không. `nullConstant` trả null cho reference type; với primitive type sẽ bị từ chối.

**Bài 5.** `enumConstant(lookup,"SECONDS",TimeUnit.class)` khác gì `TimeUnit.valueOf("SECONDS")`?  
**Đáp án:** đều định danh enum constant, nhưng `enumConstant` có chữ ký bootstrap phục vụ condy; dùng trực tiếp trong Java không tự tạo dynamic constant.

**Bài 6.** Trong `getStaticFinal` dạng đầy đủ, tham số `declaringClass` dùng để làm gì?  
**Đáp án:** chỉ định class khai báo field `static final` được tìm theo tên và type. Nếu field không tồn tại/không final/không được truy cập, có lỗi thích hợp.

**Bài 7.** `fieldVarHandle` resolve thành condy một lần, field được set từ 7 sang 13. `VarHandle.get` lần sau đọc gì?  
**Đáp án:** đọc giá trị field hiện tại `13`; cache giữ **handle reference**, không phải snapshot số 7.

**Bài 8.** Bootstrap custom trả object mới mỗi lần được gọi. Hai `ldc` của cùng resolved CP entry cho hai object khác nhau không?  
**Đáp án:** sau resolution thành công, chúng dùng cùng giá trị đã được JVM chọn/cache. Dưới race có thể có nhiều bootstrap executions ban đầu, nhưng JVM chọn một kết quả.

**Bài 9.** Bootstrap ném `IllegalStateException` trong lần resolve đầu, caller sẽ thấy điều gì?  
**Đáp án:** resolution thường tạo `BootstrapMethodError` bọc exception; các lần dùng tiếp entry đó tiếp tục lỗi, không gọi lại bootstrap ở đường tuần tự.

**Bài 10.** Muốn đặt Long value kiểu `J` vào stack bằng condy thì nên dùng `ldc_w` hay `ldc2_w`?  
**Đáp án:** `ldc2_w` cho hai-slot `long/double` dynamic constant.

**Bài 11.** Có thể dùng static argument là một condy khác không?  
**Đáp án:** có. JVM resolve nested dynamic constant trước khi gọi bootstrap chứa argument đó; phải tránh chu trình resolution.

**Bài 12.** `ConstantBootstraps.invoke` có thể gọi một method handle tạo secret token khi bootstrap không?  
**Đáp án:** về mặt kỹ thuật có thể gọi method handle phù hợp, nhưng **không nên** coi condy là nơi giữ secret hoặc chạy side effect quan trọng; resolution có thể cạnh tranh và giá trị cache dài theo classloader.

**Bài 13.** Vì sao ứng dụng Java bình thường thường không nên dùng condy để thay enum literal?  
**Đáp án:** compiler/runtime tầng thấp mới cần tính năng phát sinh bytecode; `TimeUnit.SECONDS` trực tiếp rõ, dễ bảo trì và không có chi phí/linkage phức tạp.

**Bài 14.** Bạn viết `static final String LABEL = "ready";` rồi chạy `javap -v` nhưng không có tag17. Có bất thường không?  
**Đáp án:** không. Java source field constant bình thường không buộc compiler phát sinh `CONSTANT_Dynamic`.

## 14. Tài liệu chuẩn

- [Java SE 11 — ConstantBootstraps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): bảng phương thức có sẵn, chữ ký, kiểu và lỗi.
- [Java SE 11 — java.lang.invoke package](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/package-summary.html): resolution và bootstrap invocation, concurrency/cache/error.
- [Java SE 11 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): access control, `defineClass`, method/VarHandle lookup.
- [Java SE 11 — MethodHandle](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandle.html): adaptation và invocation.
- [Java SE 11 — VarHandle](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/VarHandle.html): get/set, atomic access modes và memory semantics.
- [JVMS SE 11 — `4.4.10`](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.4.10): cấu trúc `CONSTANT_Dynamic_info`.
- [JVMS SE 11 — `4.7.23`](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.23): `BootstrapMethods` attribute.
- [JVMS SE 11 — `5.4.3.6`](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3.6): dynamic constant/call-site resolution, failure và caching.
- [JVMS SE 11 — `6.5 ldc family`](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-6.html#jvms-6.5.ldc): cách load constant.
- [JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309): bối cảnh và mục tiêu bổ sung condy cho Java 11.

**Kết luận:** `ConstantBootstraps` là tập bootstrap dựng sẵn **thực sự có trên Java 11** để JVM có thể resolve `CONSTANT_Dynamic` thành null, primitive `Class` mirror, enum, field constant, factory result hoặc VarHandle. Giá trị được JVM chọn sẽ được cache theo constant-pool entry; lỗi resolve cũng có tính ổn định. Với code ứng dụng, ưu tiên cú pháp Java rõ ràng; với compiler/bytecode tooling, hãy chọn đúng built-in method, descriptor, bootstrap arguments, quyền lookup và xử lý first-use/concurrency để tạo dynamic constant an toàn, có thể kiểm thử, còn phù hợp trên Java hiện đại.