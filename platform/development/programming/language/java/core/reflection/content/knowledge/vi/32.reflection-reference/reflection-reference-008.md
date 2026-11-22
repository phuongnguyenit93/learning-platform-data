# Tra cứu Javadoc và quy tắc ngôn ngữ theo từng thao tác Java Reflection

## 1. Vì sao phải tra cứu theo *thao tác cụ thể*?

Reflection không phải một API duy nhất với một bộ quy tắc đơn giản. Trong Java 17+, các thao tác **tìm một lớp**, **liệt kê thành viên**, **tìm chữ ký method**, **kiểm tra quyền truy cập**, **gọi method**, **đọc generic/annotation**, hay **tạo dynamic proxy** có quy tắc và loại lỗi riêng. Khi kết quả trái với trực giác, cần xác định chính xác thao tác đang làm gì, rồi đọc tài liệu phù hợp.

Nguồn tra cứu có vai trò khác nhau:

- **API Javadoc (Java SE 17):** hợp đồng của một API cụ thể như `Class.getDeclaredMethod`, `Method.invoke` hoặc `AccessibleObject.trySetAccessible`: tham số, giá trị trả về, điều kiện, exception và khác biệt với API gần tên.
- **Java Language Specification (JLS):** các quy tắc của *ngôn ngữ Java*: member access, method overloading/overriding, invocation conversions, generics/type erasure, annotation và class initialization.
- **Java Virtual Machine Specification (JVMS):** định nghĩa *runtime/bytecode*: class loading, linking, initialization, resolution, field/method descriptors, generic `Signature` attribute và dispatch ở tầng JVM.
- **Mã thử Java tối thiểu trên JDK mục tiêu:** xác nhận một giả thuyết có thể tái hiện. Kết quả thực nghiệm là kiểm chứng cho trường hợp đó, **không thay thế hợp đồng chính thức**.

Một trường hợp điển hình: `getMethod("process", Integer.class)` ném `NoSuchMethodException` dù class khai báo `process(int)`. Trực giác về **autoboxing khi gọi Java bình thường** không thể thay thế Javadoc của **reflection lookup**. Tương tự, gọi `Method.invoke` trên một `Method` đã tìm được lại có quy tắc chuyển đổi đối số riêng.

## 2. Bộ liên kết chính thức nên đánh dấu

Tất cả liên kết dưới đây chỉ đến tài liệu **Java SE / JDK 17** để đọc cùng một mốc phiên bản khi kiểm tra ví dụ trong bài.

| Nhu cầu | Tài liệu chính thức | Phần nên đọc |
| --- | --- | --- |
| Khám phá class, field, method, constructor | [`java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) | `forName`, `getMethod`, `getDeclaredMethod`, `getMethods`, `getDeclaredMethods`, `getField`, `getDeclaredField` |
| Lấy/đặt field | [`java.lang.reflect.Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html) | `get`, `set`, `getType`, `getGenericType` |
| Gọi method/đọc signature | [`java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html) | `invoke`, `getReturnType`, `getGenericReturnType`, `getParameterTypes` |
| Gọi constructor | [`java.lang.reflect.Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html) | `newInstance` và ngoại lệ khi constructor ném exception |
| Kiểm soát quyền reflection | [`AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html) | `canAccess`, `trySetAccessible`, `setAccessible` |
| Generic metadata | [`java.lang.reflect.Type`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html) | `ParameterizedType`, `TypeVariable`, `WildcardType` |
| Runtime annotations | [`AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html) | `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType` |
| Tạo dynamic proxy | [`Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html) và [`InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html) | `newProxyInstance`, `invoke`, phương thức `Object` |
| Kiểm tra overload/override | [JLS `15.12 — Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12) và [JLS `8.4 — Method Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4) | Các bước chọn method khi viết code Java, overriding, signature |
| Phạm vi access của ngôn ngữ | [JLS `6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6) | `public`, `protected`, package-private, `private` |
| Type erasure | [JLS `4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6) | Erasure của `T`, `List<String>`, bounds |
| Class loading/linking/init | [JVMS Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) | ``5.3` loading, ``5.4` linking, ``5.5` initialization |
| Generic `Signature` trong class file | [JVMS `4.7.9 — The Signature Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.9) | Bytecode descriptor khác metadata generic |

Khi dùng phiên bản JDK khác, đổi **cả Javadoc, JLS/JVMS và JDK thực thi** sang cùng phiên bản nếu hành vi mới là vấn đề. Không chọn ngẫu nhiên tài liệu mới nhất rồi chạy chương trình cũ mà không xét `@since`, `@Deprecated`, giới hạn module hoặc thay đổi API.

## 3. Cách đọc một trang Javadoc đúng trình tự

Với API cần tra cứu, nên đi theo chuỗi câu hỏi sau:

1. **Đúng loại/thao tác chưa?** Ví dụ `Class.getMethod` so với `Class.getDeclaredMethod`, `Method.invoke` so với `Constructor.newInstance`.
2. **Đúng phiên bản và chữ ký chưa?** Xem dạng khai báo đầy đủ, generic parameter, varargs, static/instance, overload của chính API JDK.
3. **Đầu vào có nghĩa gì?** Với `getMethod`, mảng `Class<?>... parameterTypes` biểu diễn **kiểu tham số khai báo**; với `Method.invoke`, `args` là **giá trị truyền khi gọi**.
4. **Phạm vi kết quả là gì?** `public` hay declared, kế thừa hay không; `getDeclaredMethods()` có thể chứa synthetic/bridge; `getDeclaredFields()` không trả field kế thừa.
5. **Có kiểm tra quyền truy cập không?** Tìm được metadata không có nghĩa được gọi private method hoặc đọc private field; `trySetAccessible` chịu ràng buộc module.
6. **Đường lỗi là gì?** `NoSuchMethodException` khác `IllegalAccessException`, `IllegalArgumentException` và `InvocationTargetException`. Nếu có `throws`, đọc điều kiện *đúng lúc thao tác đó*.
7. **Javadoc có dẫn tới JLS/JVMS không?** Hãy mở phần đặc tả tương ứng khi điều bạn hỏi thuộc compiler/JVM hơn là hợp đồng thư viện.

Đọc cả **Method Detail** (mô tả và điều kiện) chứ không chỉ tên trong Method Summary; các chú thích `Since`, `See Also`, `Throws` và cảnh báo hành vi đặc biệt thường nằm dưới phần chi tiết.

## 4. Bảng tra cứu: tình huống nào mở tài liệu nào trước?

| Thao tác đang làm | API ưu tiên | Câu hỏi cần kiểm chứng | Nhầm lẫn phổ biến |
| --- | --- | --- | --- |
| Biết tên `"pkg.Foo"`, muốn lấy `Class<?>` | `Class.forName`/`ClassLoader.loadClass` | Loader nào? Có yêu cầu initialization không? | Cho rằng mọi loader đều tìm cùng phạm vi; `Class.forName("int")` sẽ trả `int.class` |
| Có object, hỏi class runtime | `obj.getClass()`, `Class.isInstance` | Kiểu runtime là class nào? | Mong `List<String>` tồn tại như một runtime class riêng |
| Liệt kê public methods | `Class.getMethods()` | Có inherited public methods không? | Hiểu là chỉ gồm method khai báo trực tiếp |
| Liệt kê method khai báo trực tiếp | `Class.getDeclaredMethods()` | Có private/bridge/synthetic? | Mong thứ tự trả về giống thứ tự source và tự có inherited method |
| Tìm method chính xác | `getMethod`/`getDeclaredMethod` | Tên + danh sách **kiểu tham số đúng** là gì? | Mong reflection tự chọn overload, tự boxing kiểu truyền vào `getMethod` |
| Tìm field hoặc constructor | `getDeclaredField`, `getDeclaredConstructor` | Field/constructor trực tiếp hay public; exact parameter types? | Dùng `getMethods` để tìm constructor; tin constructor kế thừa |
| Đọc private field | `Field.get`, `canAccess`, `trySetAccessible` | Caller có quyền và module có mở package không? | Tưởng `getDeclaredField` đồng nghĩa có quyền đọc |
| Gọi method bằng reflection | `Method.invoke` | Receiver, actual args, boxing/widening, exception target? | Nghĩ `invoke` giải quyết overload lại từ đầu |
| Đọc annotation lúc chạy | `AnnotatedElement`/`Retention` | Annotation có `RUNTIME` không, có trực tiếp/kế thừa không? | Mong `RetentionPolicy.CLASS` hiển thị bằng `getAnnotation` |
| Đọc `List<String>` trong chữ ký | `getGeneric...`, `Type`, classfile `Signature` | Metadata generic có được lưu trong classfile không? | Tưởng mọi instance giữ type argument riêng |
| Sinh interface proxy | `Proxy`, `InvocationHandler` | Handler xử lý method và `equals`/`hashCode`/`toString` thế nào? | Tưởng proxy tự làm delegation/equality theo target |
| Thiếu class hoặc static init lỗi | `Class.forName`, JVMS Ch. 5 | Lookup thất bại hay class linkage/initialization thất bại? | Đồng nhất `ClassNotFoundException` với `NoClassDefFoundError` |

**Phạm vi của `Class<?>`:** Có `SomeClass.class` là đủ để introspect chính kiểu ấy; nó không cho phép tự động liệt kê mọi class trong một package. Classpath scanning là một bài toán nguồn class/resource khác, không phải `Class.getDeclaredClasses()`.

## 5. Bài toán mẫu: “`getMethod` không tìm thấy dù gọi trực tiếp được”

Ví dụ một class có hai overload:

```java
// Minh họa nằm trong thân class, không phải chương trình chạy độc lập.
public String choose(int n) { return "primitive"; }
public String choose(Integer n) { return "wrapper"; }
```

Khi biết chính xác điều cần hỏi, đường tra cứu là:

1. Mở Javadoc `Class.getMethod(String, Class<?>...)` và `getDeclaredMethod`.
2. Đọc rằng tham số cuối biểu diễn **kiểu tham số của method cần tìm**; chọn `int.class` cho `choose(int)`, `Integer.class` cho `choose(Integer)`.
3. Nếu muốn hiểu lời gọi nguồn `choose(1)` và `choose(Integer.valueOf(1))` được compiler chọn ra sao, mở **JLS `15.12.2**; đó là vấn đề **overload resolution của ngôn ngữ**, không phải một overload resolver được `getMethod` cung cấp.
4. Nếu đã tìm `Method chooseInt` rồi gọi `chooseInt.invoke(receiver, Integer.valueOf(1))`, mở Javadoc **`Method.invoke`** để xem unboxing/primitive widening cho actual arguments.
5. Nếu `getMethod("choose", Long.class)` thất bại dù có overload `choose(Number)`, đó là đúng với lookup chữ ký: `Long.class` không phải `Number.class`.

**Phân biệt hai giai đoạn:** khi *tra cứu*, `Class<?>` phải khớp declared parameter type; khi *invoke*, actual argument object được kiểm tra và có thể chuyển đổi theo quy tắc reflection, nhưng không chọn method khác.

JLS `15.12` còn quy định các pha xử lý strict/loose/varargs và most-specific cho method invocation expression trong mã nguồn. Không tự sao chép các pha ấy vào ý nghĩa của `getMethod`.

## 6. Bài toán mẫu: “`getDeclaredMethod` thấy method, nhưng `invoke` lỗi”

Giả sử method `private` được tìm được:

```java
// Minh họa, không độc lập.
Method m = SomeType.class.getDeclaredMethod("secret");
Object result = m.invoke(instance);
```

`getDeclaredMethod` trả metadata của method được khai báo trực tiếp, bất kể public/private nếu tìm thấy chữ ký. Nhưng `m.invoke` vẫn kiểm tra quyền truy cập. Cần đọc **`AccessibleObject`**:

- `m.canAccess(instance)` hỏi quyền hiện tại của caller đối với reflected member, với receiver phù hợp.
- `m.trySetAccessible()` trả `true` khi có thể cho phép bỏ qua kiểm tra access theo các điều kiện JDK; không cam kết thành công trong mọi module/package.
- `m.setAccessible(true)` có thể thất bại bằng `InaccessibleObjectException` nếu module không cho phép mở quyền truy cập.
- `IllegalAccessException` của `Method.invoke` thường phản ánh caller không có quyền; khác `InvocationTargetException`, loại bao **exception do chính method đích ném ra**.

Muốn biết tại sao nguồn Java truy cập được hay không, tham khảo JLS `6.6`. Muốn biết khi nào reflective access được suppress, xem Javadoc `AccessibleObject` và yêu cầu `exports`/`opens` của Java Platform Module System. **Đọc metadata không phải bằng chứng được phép truy cập member**.

Trường hợp field tương tự: `getDeclaredField` có thể lấy `Field` cho field private, nhưng `Field.get(instance)` vẫn kiểm tra access. Khi đưa vào công cụ thực tế, nên ưu tiên public API/hợp đồng module rõ ràng, và chỉ mở private access ở ranh giới được phép.

## 7. Bài toán mẫu: generic erasure và metadata classfile

Khi method khai báo `List<String> find()`:

- `getReturnType()` trả `List.class` vì kiểu trả về erased/runtime là `List`.
- `getGenericReturnType()` có thể trả `ParameterizedType` biểu diễn `java.util.List<java.lang.String>` nếu classfile còn `Signature` metadata hợp lệ.
- Việc một method mô tả `List<String>` không có nghĩa từng list object chứa đầy đủ generic type argument tại runtime.

Đọc **JLS `4.6`** để hiểu erasure; đọc **JVMS `4.7.9`** để hiểu classfile `Signature`; đọc Javadoc `Method.getGenericReturnType` để biết API biểu diễn metadata bằng `Type` và các ngoại lệ có thể xảy ra khi signature hỏng/thiếu kiểu.

Với khai báo parameter `List<String>`, muốn gọi `getMethod("accept", ...)` cần truyền `List.class`, **không phải `ArrayList.class`** dù truyền một instance `ArrayList<String>` vào `Method.invoke` có thể hợp lệ.

Đừng nhầm một chuỗi mô tả kiểu `"java.util.List<java.lang.String>"` với tên lớp có thể truyền cho `Class.forName`. Java không tạo class runtime `List<String>` riêng cho mỗi type argument.

## 8. Bài toán mẫu: annotation có trong source nhưng không thấy bằng reflection

Annotation được dùng để đọc lúc chạy phải xét **`@Retention`**:

- `RetentionPolicy.SOURCE`: chỉ dành cho xử lý nguồn; không giữ như annotation runtime trong classfile.
- `RetentionPolicy.CLASS`: có thể tồn tại trong classfile nhưng không hiển thị qua API runtime reflection thường dùng.
- `RetentionPolicy.RUNTIME`: annotation được giữ để API reflection như `getAnnotation`/`isAnnotationPresent` đọc được.

`@Target` chỉ quy định annotation áp dụng lên những loại phần tử nào (field/method/class...), **không tự thực thi một quy tắc validation**. `@Inherited` có ngữ nghĩa riêng đối với annotation trên class; không khiến field/method ở superclass tự trở thành field/method khai báo trực tiếp của subclass.

Vì vậy khi `field.getAnnotation(MyAnnotation.class)` trả `null`, trước tiên kiểm tra định nghĩa annotation có `@Retention(RUNTIME)` hay không, field lấy từ **đúng class và đúng loader** hay không, annotation có gắn trực tiếp trên phần tử đang hỏi không. Chỉ sau đó mới điều tra classfile transformation, phiên bản build hoặc annotation package trùng tên ở loader khác.

Nguồn: Javadoc **`AnnotatedElement`**, `Retention` và quy tắc annotation trong JLS `9.6`.

## 9. Bài toán mẫu: class loading/initialization và lỗi khi introspect

`Class.forName("pkg.Plugin")` không chỉ yêu cầu tìm binary name: dạng một tham số còn yêu cầu class được khởi tạo khi thành công. Nếu chỉ muốn lấy `Class<?>` mà chưa yêu cầu initialization, dạng ba tham số `Class.forName(name, false, loader)` là một lựa chọn, nhưng vẫn không bảo đảm không có lỗi loading/linking.

Hãy phân biệt:

- **`ClassNotFoundException`:** API tìm tên class (như `Class.forName`) không tìm ra class theo loader được yêu cầu.
- **`NoClassDefFoundError`:** JVM không thể có định nghĩa class dùng được khi resolve/link một phụ thuộc, hoặc lớp ở trạng thái lỗi sau initialization thất bại; đôi lúc cause chứa `ClassNotFoundException`.
- **`ExceptionInInitializerError`:** static initialization ném exception thông thường trong lần khởi tạo; lần dùng tiếp theo của class đã lỗi có thể dẫn đến `NoClassDefFoundError`.
- **`InaccessibleObjectException` hoặc `IllegalAccessException`:** vấn đề quyền reflective access, không phải bằng chứng class không tồn tại.
- **`NoSuchMethodException`:** không tìm được chữ ký method; hoàn toàn khác class loader không tìm ra class.

Khi stack trace chứa nhiều tầng `Caused by`, đừng dừng ở lớp lỗi ngoài. Dựa vào thao tác đang gọi và **nguyên nhân đầu tiên** để mở Javadoc chính xác rồi đối chiếu **JVMS Ch. 5** về loading/linking/initialization. Một `Class<?>` đã được lấy thành công không đảm bảo các type phụ thuộc trong chữ ký method sẽ luôn resolve được khi introspect sâu.

## 10. Ví dụ Java 17+ chạy được: tra cứu và đối chiếu từng thao tác

Chương trình dưới đây dùng các API đã nêu và in kết quả ổn định. Nó không tự quét classpath và không cần thư viện bên ngoài.

Tạo file `JavadocLookupDemo.java` trong một thư mục trống, không khai báo `package`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Action {}

class LibraryBase {
    public String inherited() {
        return "base";
    }
}

class LibrarySample extends LibraryBase {
    private final String secret;

    public LibrarySample(String secret) {
        this.secret = secret;
    }

    public String choose(int value) {
        return "primitive:" + value;
    }

    public String choose(Integer value) {
        return "wrapper:" + value;
    }

    @Action
    public List<String> labels() {
        return List.of("a", "b");
    }

    public void fail() {
        throw new IllegalStateException("boom");
    }
}

public class JavadocLookupDemo {
    public static void main(String[] args) throws Exception {
        Class<LibrarySample> type = LibrarySample.class;
        Constructor<LibrarySample> ctor =
                type.getConstructor(String.class);
        LibrarySample sample = ctor.newInstance("key");

        System.out.println("Created: "
                + sample.getClass().getSimpleName());

        Method inherited = type.getMethod("inherited");
        System.out.println("Inherited declaring class: "
                + inherited.getDeclaringClass().getSimpleName());

        boolean inheritedDeclaredHere = true;
        try {
            type.getDeclaredMethod("inherited");
        } catch (NoSuchMethodException expected) {
            inheritedDeclaredHere = false;
        }
        System.out.println("Declared inherited method: "
                + inheritedDeclaredHere);

        Method primitive = type.getMethod("choose", int.class);
        Method wrapper = type.getMethod("choose", Integer.class);
        System.out.println("Primitive lookup: "
                + primitive.getParameterTypes()[0].getTypeName());
        System.out.println("Wrapper lookup: "
                + wrapper.getParameterTypes()[0].getTypeName());
        System.out.println("Primitive invocation: "
                + primitive.invoke(sample, Integer.valueOf(7)));
        System.out.println("Wrapper invocation: "
                + wrapper.invoke(sample, Integer.valueOf(7)));

        boolean missingLong = false;
        try {
            type.getMethod("choose", Long.class);
        } catch (NoSuchMethodException expected) {
            missingLong = true;
        }
        System.out.println("Long lookup missing: " + missingLong);

        Field field = type.getDeclaredField("secret");
        System.out.println("Private field accessible before: "
                + field.canAccess(sample));
        System.out.println("Private access enabled: "
                + field.trySetAccessible());
        System.out.println("Private field value: " + field.get(sample));

        Method labels = type.getMethod("labels");
        System.out.println("Erased return: "
                + labels.getReturnType().getTypeName());
        System.out.println("Generic return: "
                + labels.getGenericReturnType().getTypeName());
        System.out.println("Runtime annotation: "
                + labels.isAnnotationPresent(Action.class));

        try {
            type.getMethod("fail").invoke(sample);
        } catch (InvocationTargetException e) {
            System.out.println("Target exception: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 JavadocLookupDemo.java
java JavadocLookupDemo
```

Output trong môi trường classpath thông thường, chạy từ cùng thư mục:

```text
Created: LibrarySample
Inherited declaring class: LibraryBase
Declared inherited method: false
Primitive lookup: int
Wrapper lookup: java.lang.Integer
Primitive invocation: primitive:7
Wrapper invocation: wrapper:7
Long lookup missing: true
Private field accessible before: false
Private access enabled: true
Private field value: key
Erased return: java.util.List
Generic return: java.util.List<java.lang.String>
Runtime annotation: true
Target exception: IllegalStateException
```

**Phân tích chính theo Javadoc:**

1. `getConstructor(String.class)` tìm public constructor với chữ ký cụ thể; `newInstance` tạo object. Constructor không phải inherited method.
2. `getMethod("inherited")` tìm public method kế thừa từ `LibraryBase`, còn `getDeclaredMethod("inherited")` không tìm thấy vì `LibrarySample` không tự khai báo nó.
3. `choose(int)` và `choose(Integer)` là hai overload; truyền `int.class` và `Integer.class` vào `getMethod` cho hai kết quả khác nhau. `invoke` trên method primitive chấp nhận boxed `Integer`.
4. Tra cứu `Long.class` không tự chọn overload `Integer` hay `int`; không có chữ ký đúng nên xuất hiện `NoSuchMethodException`.
5. Class `LibrarySample` được khai báo ở phạm vi top-level không phải nestmate của `JavadocLookupDemo`, nên private field chưa được quyền truy cập trực tiếp. `trySetAccessible` trong môi trường classpath minh họa có thể bật và cho phép `Field.get`; **đây không phải cam kết với mọi named module**.
6. `getReturnType()` chỉ thấy erased type `List`, còn `getGenericReturnType()` đọc generic Signature metadata do compiler giữ cho khai báo `List<String>`.
7. Annotation `@Action` có `RUNTIME` nên được tìm thấy.
8. `fail()` ném `IllegalStateException`, nhưng qua `Method.invoke` exception được bọc trong `InvocationTargetException`; đọc `getCause()` giúp biết lỗi gốc.

## 11. Quy trình 7 bước khi gặp một vấn đề Reflection thật

**Bước 1 — Chỉ rõ API và dòng code đang chạy.** Ghi nguyên lời gọi như `type.getDeclaredMethod(...)` hoặc `method.invoke(...)`, không mô tả chung “reflection lỗi”.

**Bước 2 — Tách dữ liệu đầu vào.** Với lookup: tên method, danh sách `Class<?>` của parameter, class/loader. Với invocation: receiver, actual arguments, phương thức static/instance, quyền truy cập.

**Bước 3 — Đọc Javadoc theo phiên bản runtime.** Kiểm tra `Parameters`, `Returns`, `Throws`, mô tả “public”/“declared”/“inherited” và các điều kiện đặc biệt trong method detail.

**Bước 4 — Mở đặc tả đúng tầng.** Nếu đang so việc compiler chọn overload/override, dùng JLS ``15.12`/`8.4`. Nếu đang điều tra class initialization và linkage, dùng JVMS Ch. 5. Nếu thiếu generic Signature, dùng JLS `4.6` và JVMS `4.7.9`.

**Bước 5 — Viết chương trình tái hiện tối thiểu.** Một file, vài class rõ tên, đầu vào ổn định; in method name, `getParameterTypes()`, `getDeclaringClass()`, class loader nếu phù hợp. Đừng phụ thuộc thứ tự `getDeclaredMethods()`.

**Bước 6 — Kiểm thử cả đường thành công và thất bại.** Ví dụ `getMethod(..., int.class)` thành công, `getMethod(..., Long.class)` thất bại; đọc field private khi chưa có quyền và sau khi được phép; gọi method ném exception để xác nhận `InvocationTargetException`.

**Bước 7 — Tài liệu hóa kết luận kèm phiên bản và điều kiện.** Ví dụ “trên Java 17, với class trong unnamed module và method được khai báo như ví dụ, `getDeclaredMethod` không tìm inherited method”. Đừng biến hành vi phụ thuộc module/compiler/class loader thành mệnh đề không điều kiện.

## 12. Những lỗi nghiên cứu tài liệu phổ biến

| Lỗi khi tra cứu | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tìm toàn bộ bài blog thay vì Javadoc API đang gọi | Trộn quy tắc của các thao tác khác nhau | Đọc method detail của API tương ứng trước |
| Lấy tài liệu Java mới hơn nhưng chạy JDK cũ | Mâu thuẫn `@since` và module behavior | Dùng bộ tài liệu cùng phiên bản JDK |
| Đọc `getMethod` nhưng áp quy tắc `Method.invoke` để suy chữ ký | Tìm sai overload | Tra cứu và invocation là hai giai đoạn riêng |
| Tưởng tìm thấy `Field` là đọc private được | `IllegalAccessException`/`InaccessibleObjectException` | Đọc `AccessibleObject` và các ranh giới module |
| Tưởng `getDeclared...` tự bao gồm inherited members | Bỏ sót superclass | Chọn đúng API, duyệt superclass khi cần |
| Dựa vào thứ tự mảng method/field | Test không ổn định | Lọc theo tên/chữ ký và sắp xếp khi in |
| Nhầm generic metadata với type của instance | Framework suy ra sai kiểu runtime | Phân biệt erasure và `Signature` |
| Bỏ qua `Caused by` của exception | Chữa sai tầng lỗi | Ghi chính xác exception lookup/invocation/target/linkage |
| Tưởng `Class.forName` và `ClassLoader.loadClass` giống hệt nhau | Hiểu sai thời điểm initialize | Đọc Javadoc từng overload và JVMS Ch. 5 |
| Dùng `setAccessible` như cách chữa mọi lỗi | Không giải quyết metadata hoặc linkage; có thể bị module chặn | Chỉ mở access khi hợp lệ; sửa đúng nguyên nhân gốc |

## 13. Bài tự kiểm tra

**Câu 1.** `getMethod("parse", Integer.class)` không thấy `parse(int)`. Mở Javadoc hay JLS trước?

**Đáp án:** Mở Javadoc `Class.getMethod` trước vì đang tra cứu chữ ký. Dùng JLS `15.12` khi muốn biết compiler chọn overload nào cho một lời gọi trong mã nguồn.

**Câu 2.** `getDeclaredMethod` thấy private method nhưng `invoke` thất bại. Nên đọc tài liệu nào?

**Đáp án:** Javadoc `Method.invoke` và `AccessibleObject`, rồi JLS `6.6` nếu cần hiểu quyền ngôn ngữ; kiểm tra `trySetAccessible` cùng module/package.

**Câu 3.** `getGenericReturnType()` thấy `List<String>` nhưng `getReturnType()` chỉ là `List`. Hai API có mâu thuẫn?

**Đáp án:** Không. Một API trả erased runtime type, API còn lại đọc generic metadata khai báo được lưu trong class file nếu có. Tra JLS `4.6` và JVMS `4.7.9`.

**Câu 4.** Với `getDeclaredMethods()`, có thể chọn method đầu tiên là method khai báo sớm nhất trong source không?

**Đáp án:** Không. Thứ tự trả về không được bảo đảm, và compiler có thể thêm bridge/synthetic methods. Kiểm tra `Method.isBridge()`/`isSynthetic()` khi liên quan.

**Câu 5.** `Class.forName` ném `ExceptionInInitializerError` thay vì `ClassNotFoundException`. Có phải Javadoc sai?

**Đáp án:** Không. Class có thể tìm được nhưng static initialization thất bại. Tra overload `Class.forName` rồi JVM initialization rules; phân biệt lỗi lookup với initialization.

**Câu 6.** Annotation có `@Retention(CLASS)` nhưng `getAnnotation` trả `null`. Tài liệu nào trả lời?

**Đáp án:** Javadoc `AnnotatedElement`/`Retention` cùng JLS quy định retention. Annotation lưu trong classfile không đồng nghĩa hiển thị qua runtime reflection.

**Câu 7.** Tài liệu API cho phép truy cập một method ở Java 17 nhưng một dự án named module bị chặn. Có cần xem cả đặc tả module không?

**Đáp án:** Có. `AccessibleObject` giải thích các điều kiện suppress access; JPMS `exports`/`opens` quyết định phạm vi truy cập. Có tên method hoặc class không tự cung cấp quyền private reflection.

**Ghi nhớ:** Với Reflection, hãy đi theo thứ tự **xác định thao tác → đọc Javadoc đúng method/version → đối chiếu JLS/JVMS khi cần → viết test tái hiện → kết luận kèm điều kiện**. Cách này tránh lấy quy tắc của compiler, JVM và Reflection API thay thế lẫn nhau.