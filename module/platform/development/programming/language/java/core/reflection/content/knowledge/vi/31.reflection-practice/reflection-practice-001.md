# Thực hành: Xây dựng trình in cấu trúc một Class theo thứ tự ổn định bằng Java Reflection

## 1. Bài toán và tiêu chí hoàn thành

Viết một chương trình Java 17+ nhận một đối tượng `Class<?>` và xuất cấu trúc lớp theo thứ tự **xác định và lặp lại được**, đủ để đọc, so sánh hoặc lưu thành tài liệu cấu trúc. Chương trình sẽ in:

1. Tên đầy đủ và modifiers của class.
2. Superclass trực tiếp (nếu có).
3. Danh sách interface được khai báo trực tiếp, sắp xếp theo tên.
4. Fields được khai báo trực tiếp: modifier, kiểu và tên; sắp xếp theo khóa rõ ràng.
5. Constructors được khai báo trong class: modifiers và danh sách kiểu tham số; sắp xếp theo signature.
6. Methods được khai báo trực tiếp: modifiers, kiểu trả về, tên, danh sách kiểu tham số; sắp xếp theo signature và các khóa phụ khi cần.

**Điểm cốt lõi:** Theo Java Reflection API, **thứ tự phần tử trong các mảng trả về từ `getDeclaredFields()`, `getDeclaredConstructors()`, `getDeclaredMethods()` không được bảo đảm**. Vì vậy không được chỉ duyệt rồi in nguyên thứ tự mảng mà gọi đó là “ổn định”. Cần **sắp xếp dữ liệu trước khi in** và quy định khóa sắp xếp một cách công khai.

Kết quả ổn định ở đây được hiểu là: với cùng một cấu trúc lớp, cùng quy tắc hiển thị và cùng thông tin Reflection nhìn thấy, chương trình tạo chuỗi đầu ra giống nhau, bất kể thứ tự các phần tử trong mảng Reflection. Đây không phải cam kết rằng bytecode do mọi compiler, phiên bản JDK hoặc cơ chế instrument khác nhau sẽ luôn cho **cùng cấu trúc metadata**; các phần tử synthetic/bridge có thể thay đổi theo quá trình biên dịch.

## 2. Chọn phạm vi: “declared” khác “inherited”

Có hai nhóm API Reflection thường bị trộn lẫn:

| Thông tin | API lựa chọn | Phạm vi |
|---|---|---|
| Fields trong đúng class hiện tại | `getDeclaredFields()` | Gồm public, protected, package-private, private; không tự lấy field kế thừa |
| Fields public có thể thấy | `getFields()` | Có thể bao gồm field public kế thừa |
| Methods trong đúng class hiện tại | `getDeclaredMethods()` | Không tự lấy method kế thừa; có thể có bridge/synthetic methods |
| Methods public có thể thấy | `getMethods()` | Gồm method public kế thừa, ví dụ từ superclass/interfaces |
| Constructors của class | `getDeclaredConstructors()` | Gồm public và non-public constructors được khai báo |
| Constructors public | `getConstructors()` | Chỉ public constructors; constructor không được kế thừa |
| Superclass trực tiếp | `getSuperclass()` | Có thể là `null` với `Object`, interface, primitive, `void` |
| Interfaces trực tiếp | `getInterfaces()` | Các interface class khai báo trực tiếp; không tự trộn vào các interface kế thừa gián tiếp |

**Quyết định thiết kế của bài:** Dùng nhóm `getDeclared...` để in một lát cắt cấu trúc **do class sở hữu**, rồi in riêng superclass và interfaces. Cách này tránh một method được thừa kế xuất hiện như thể nó được khai báo trực tiếp bởi class hiện tại. Các công cụ thực tế có thể thêm chế độ “public API including inherited”, nhưng phải xác định phạm vi và quy tắc xử lý override riêng; **không trộn hai chế độ trong một bản in**.

Trong chương trình mẫu, `Sample` kế thừa `Base` và thực thi `Runnable, AutoCloseable`. Các method `run()` và `close()` được khai báo trực tiếp trong `Sample`, nên xuất hiện ở phần `METHODS`. Những method kế thừa từ `Object` như `wait`, `hashCode` không được thêm vào danh sách `getDeclaredMethods()`.

## 3. Thiết kế khóa sắp xếp theo từng nhóm

Một khóa phải phản ánh đủ sự khác biệt cần thiết và được dựng từ dữ liệu có thứ tự ổn định:

| Nhóm | Khóa chính và phụ trong bài |
|---|---|
| Interfaces | Tên kiểu hiển thị sau chuẩn hóa qua `typeName`, thứ tự từ điển |
| Fields | Tên field → kiểu field → modifiers |
| Constructors | Danh sách kiểu tham số → modifiers |
| Methods | Tên method → danh sách kiểu tham số → kiểu trả về → modifiers → `isBridge` → `isSynthetic` |

Ví dụ methods có overload:

~~~text
describe(int)
describe(java.lang.String)
~~~

Nếu chỉ sắp xếp bằng tên method, hai phần tử có tên `describe` vẫn có thể giữ thứ tự tương đối từ mảng Reflection ban đầu; chúng có thể bị đổi chỗ. Vì vậy **overload cần thêm khóa theo danh sách kiểu tham số**. Kiểu trả về cũng nên có khóa riêng: JVM có thể chứa bridge methods hoặc các method có bytecode signature khác dù có cùng tên và danh sách tham số.

**Không dùng `Method.toString()` hoặc `Class.toString()` làm khóa sắp xếp duy nhất** khi thiết kế công cụ: chuỗi hiển thị không phải một giao ước “sort key” do API cam kết; tốt hơn là chọn chính các thuộc tính bạn muốn so sánh. Bài này tạo chuỗi tham số từ `getParameterTypes()` theo thứ tự tham số đã khai báo, rồi dùng comparator explicit.

**Thứ tự trong một lớp metadata không phải “source order”.** Reflection không cam kết fields/methods giữ thứ tự viết trong file Java, nên printer không hứa tái dựng nguyên văn mã nguồn. Comparator trong bài cố ý tạo thứ tự *mới* và giải thích được.

### Chuẩn hóa tên kiểu

`Class.getSimpleName()` quá ngắn khi có nhiều kiểu `User` khác package. `Class.getName()` dùng ký pháp nhị phân với `$` cho nested types, ví dụ `StableClassPrinter$Sample`. `Class.getCanonicalName()` dễ đọc hơn với nested class thông thường, ví dụ `StableClassPrinter.Sample`, nhưng có thể trả `null` cho local/anonymous classes và một số kiểu khác.

Hàm dùng trong bài:

~~~java
private static String typeName(Class<?> type) {
    String canonical = type.getCanonicalName();
    return canonical != null ? canonical : type.getTypeName();
}
~~~

Đây là **mảnh trích nằm trong class `StableClassPrinter`** ở mục 4. `getTypeName()` cung cấp fallback khi không có canonical name, ví dụ anonymous classes. Các trường hợp kiểu mảng và primitive cũng được Java API hiển thị có nghĩa, như `int[]` và `java.lang.String[]`. Chọn một quy tắc duy nhất cho **cả sort keys và text output** để tránh một cách nhìn khi sắp xếp, một cách nhìn khác khi in.

## 4. Chương trình Java 17+ hoàn chỉnh, có thể chạy ngay

Lưu đúng nội dung sau vào tệp **`StableClassPrinter.java`**. Chương trình tạo class mẫu `Sample`, sắp xếp mọi danh sách và in kết quả. Mã không cần dependency bên ngoài JDK.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class StableClassPrinter {
    public static class Base {}

    public static final class Sample extends Base
            implements Runnable, AutoCloseable {
        public String name;
        private final int id;

        public Sample(int id) {
            this.id = id;
        }

        public Sample(String name, int id) {
            this.name = name;
            this.id = id;
        }

        public String describe(String text) {
            return text;
        }

        public String describe(int number) {
            return Integer.toString(number);
        }

        @Override
        public void run() {}

        @Override
        public void close() {}
    }

    private static String typeName(Class<?> type) {
        String canonical = type.getCanonicalName();
        return canonical != null ? canonical : type.getTypeName();
    }

    private static String parameterTypes(Class<?>[] types) {
        return Arrays.stream(types)
                .map(StableClassPrinter::typeName)
                .collect(Collectors.joining(", "));
    }

    private static String modifiers(int value) {
        String text = Modifier.toString(value);
        return text.isEmpty() ? "" : text + " ";
    }

    public static String describe(Class<?> type) {
        StringBuilder result = new StringBuilder();
        result.append("CLASS ")
                .append(modifiers(type.getModifiers()))
                .append(typeName(type)).append('\n');

        Class<?> parent = type.getSuperclass();
        result.append("SUPER ")
                .append(parent == null ? "<none>" : typeName(parent))
                .append('\n');

        String interfaces = Arrays.stream(type.getInterfaces())
                .map(StableClassPrinter::typeName)
                .sorted()
                .collect(Collectors.joining(", "));
        result.append("INTERFACES ")
                .append(interfaces.isEmpty() ? "<none>" : interfaces)
                .append('\n');

        Field[] fields = type.getDeclaredFields();
        Arrays.sort(fields, Comparator.comparing(Field::getName)
                .thenComparing(f -> typeName(f.getType()))
                .thenComparingInt(Field::getModifiers));
        result.append("FIELDS\n");
        for (Field field : fields) {
            result.append("  ")
                    .append(modifiers(field.getModifiers()))
                    .append(typeName(field.getType())).append(' ')
                    .append(field.getName()).append('\n');
        }

        Constructor<?>[] constructors = type.getDeclaredConstructors();
        Arrays.sort(constructors,
                Comparator.comparing((Constructor<?> c) ->
                        parameterTypes(c.getParameterTypes()))
                        .thenComparingInt(Constructor::getModifiers));
        result.append("CONSTRUCTORS\n");
        for (Constructor<?> constructor : constructors) {
            result.append("  ")
                    .append(modifiers(constructor.getModifiers()))
                    .append(typeName(type)).append('(')
                    .append(parameterTypes(constructor.getParameterTypes()))
                    .append(")\n");
        }

        Method[] methods = type.getDeclaredMethods();
        Arrays.sort(methods, Comparator.comparing(Method::getName)
                .thenComparing(m -> parameterTypes(m.getParameterTypes()))
                .thenComparing(m -> typeName(m.getReturnType()))
                .thenComparingInt(Method::getModifiers)
                .thenComparing(Method::isBridge)
                .thenComparing(Method::isSynthetic));
        result.append("METHODS\n");
        for (Method method : methods) {
            result.append("  ")
                    .append(modifiers(method.getModifiers()))
                    .append(typeName(method.getReturnType())).append(' ')
                    .append(method.getName()).append('(')
                    .append(parameterTypes(method.getParameterTypes()))
                    .append(')');
            if (method.isBridge()) {
                result.append(" [bridge]");
            }
            if (method.isSynthetic()) {
                result.append(" [synthetic]");
            }
            result.append('\n');
        }
        return result.toString();
    }

    public static void main(String[] args) {
        System.out.print(describe(Sample.class));
    }
}
~~~

Trong thư mục chứa tệp, chạy:

~~~bash
javac --release 17 -encoding UTF-8 StableClassPrinter.java
java StableClassPrinter
~~~

**Stdout chính xác được kiểm chứng bằng biên dịch và chạy chương trình:**

~~~text
CLASS public static final StableClassPrinter.Sample
SUPER StableClassPrinter.Base
INTERFACES java.lang.AutoCloseable, java.lang.Runnable
FIELDS
  private final int id
  public java.lang.String name
CONSTRUCTORS
  public StableClassPrinter.Sample(int)
  public StableClassPrinter.Sample(java.lang.String, int)
METHODS
  public void close()
  public java.lang.String describe(int)
  public java.lang.String describe(java.lang.String)
  public void run()
~~~

Quan sát:

- `AutoCloseable` đứng trước `Runnable` vì tên interface đã được sort; thứ tự viết sau `implements` không được dùng làm thứ tự hiển thị.
- `id` đứng trước `name` vì field sort theo tên; vị trí field trong source không quyết định output.
- Constructor nhận `int` đứng trước constructor nhận `String, int` vì sort theo chuỗi kiểu tham số.
- Method `describe(int)` đứng trước `describe(String)` vì key tham số `int` đứng trước `java.lang.String`.
- `close()`, `describe(...)`, `run()` xuất hiện theo thứ tự tên method. Chương trình không in methods kế thừa từ `Object`.
- `Modifier.toString(...)` chuyển bitmask của modifier thành chuỗi theo quy tắc Java, ví dụ `private final`, `public static final`. Khi không có modifier, hàm `modifiers` trả chuỗi rỗng để tránh thêm một dấu cách thừa.

Ở phần ví dụ chính, mọi phần tử có khóa đủ để tạo thứ tự xác định. Với những kiểu phức tạp hơn có thể có metadata trùng khóa, xem mục 7 về việc hoàn thiện một canonical fingerprint và xử lý metadata đặc biệt.

## 5. Phân tích từng phần của printer

### 5.1. Class header, superclass và interfaces

~~~java
result.append("CLASS ")
        .append(modifiers(type.getModifiers()))
        .append(typeName(type)).append('\n');
Class<?> parent = type.getSuperclass();
~~~

`getModifiers()` trả bitmask; `Modifier.toString` định dạng modifiers thông dụng. `getSuperclass()` trả superclass trực tiếp hoặc `null` trong những trường hợp không có superclass tương ứng. Thay vì giả định mọi loại `Class<?>` đều mô tả một class bình thường, mã hiển thị `<none>` khi không có superclass.

`getInterfaces()` trả một mảng; Java không cam kết đó là thứ tự tối ưu để tạo output canonical. Vì vậy dùng:

~~~java
Arrays.stream(type.getInterfaces())
        .map(StableClassPrinter::typeName)
        .sorted()
        .collect(Collectors.joining(", "));
~~~

Đây là **mảnh trích** của chương trình hoàn chỉnh. `sorted()` sắp xếp chuỗi tên theo natural ordering (thứ tự so sánh `String`), độc lập locale mặc định của hệ điều hành. Công cụ có thể chọn comparator riêng cho yêu cầu xuất dữ liệu, nhưng cần thống nhất và tài liệu hóa.

### 5.2. Fields

~~~java
Field[] fields = type.getDeclaredFields();
Arrays.sort(fields, Comparator.comparing(Field::getName)
        .thenComparing(f -> typeName(f.getType()))
        .thenComparingInt(Field::getModifiers));
~~~

Mảnh mã được trích từ method `describe`. Comparator đảm bảo field khác tên luôn theo thứ tự tên. Các khóa phụ làm quy tắc rõ hơn nếu gặp metadata có tên giống nhau nhưng phân biệt bởi kiểu hoặc modifiers. Khi in, gọi `field.getType()` trả `Class<?>` cho kiểu đã khai báo, **không truy cập giá trị field**. Không cần `setAccessible(true)` vì chỉ đọc metadata.

`getDeclaredFields()` có thể chứa synthetic fields do compiler tạo. Nếu mục tiêu là bản in **đầy đủ ở mức Reflection**, nên giữ và đánh dấu synthetic để biết chúng tồn tại. Nếu mục tiêu là mô tả API do người dùng viết, có thể bỏ qua `field.isSynthetic()`, nhưng phải nói rõ đó là **projection đã lọc**, không còn là toàn bộ declared fields. Mã mẫu giữ mọi field và không tạo synthetic field đặc biệt trong ví dụ.

### 5.3. Constructors

Constructor không có kiểu trả về và không được kế thừa. `Constructor.getParameterTypes()` trả danh sách kiểu tham số theo đúng thứ tự khai báo, còn mảng constructors trả về phải được sort:

~~~java
Arrays.sort(constructors,
        Comparator.comparing((Constructor<?> c) ->
                parameterTypes(c.getParameterTypes()))
                .thenComparingInt(Constructor::getModifiers));
~~~

Mảnh này trích từ chương trình. `getDeclaredConstructors()` có thể bao gồm constructor private/protected/package-private. **Đọc metadata** không có nghĩa là **được phép gọi constructor**; nếu gọi bằng `newInstance(...)`, phải xử lý accessibility và exception do code đích ném.

Với non-static inner class, compiler có thể thêm tham số receiver/enclosing instance vào bytecode constructor; với enum hoặc một số loại do compiler sinh, signature Reflection cũng có khác biệt so với chữ ký hiển thị trong source. Printer này chủ ý hiển thị những kiểu tham số Reflection thực sự báo, không cố tái tạo Java source constructor verbatim.

### 5.4. Methods và overloads

`Method.getName()` một mình chưa đủ làm khóa sắp xếp. Comparator dùng:

~~~java
Comparator.comparing(Method::getName)
        .thenComparing(m -> parameterTypes(m.getParameterTypes()))
        .thenComparing(m -> typeName(m.getReturnType()))
        .thenComparingInt(Method::getModifiers)
        .thenComparing(Method::isBridge)
        .thenComparing(Method::isSynthetic)
~~~

Đây là **mảnh expression** nằm trong `Arrays.sort` ở ví dụ. Danh sách tham số tạo signature cho các overloads. Kiểu trả về tách biệt các biến thể mà compiler có thể sinh ra (ví dụ bridge methods). `isBridge()` và `isSynthetic()` còn phục vụ gắn nhãn trong output để công cụ không âm thầm bỏ qua method compiler-generated.

Các flag này **không có nghĩa cứ là bridge/synthetic thì phải xóa khỏi bản in**. Chọn giữ hay lọc phụ thuộc mục đích. Nếu giữ chúng, in thêm nhãn rõ; nếu lọc, làm trước khi sort và mô tả lý do lọc. Với tài liệu API do người dùng viết, nhiều công cụ lọc synthetic/bridge; với bài phân tích bytecode hoặc chẩn đoán runtime dispatch, giữ chúng lại có thể quan trọng.

## 6. Kiểm tra tính ổn định bằng test, không chỉ nhìn kết quả một lần

Một bản in “trông như đã sắp” không phải bằng chứng đủ. Hãy kiểm tra **nhiều lần, cùng input** và kiểm tra khóa sắp xếp.

### Test 1: Output của hàm là chuỗi không có side effects

Method `describe(Class<?>)` trả về `String`. Vì vậy test có thể so sánh output trực tiếp mà không cần bắt `System.out`:

~~~java
String first = StableClassPrinter.describe(
        StableClassPrinter.Sample.class);
String second = StableClassPrinter.describe(
        StableClassPrinter.Sample.class);

if (!first.equals(second)) {
    throw new AssertionError("Unstable class description");
}
~~~

Đây là **đoạn test minh họa** cho cùng project, không phải tệp Java độc lập. Gọi hai lần mà so sánh chuỗi giúp phát hiện sai biệt nội bộ trong một tiến trình; tuy nhiên nếu JVM thường trả mảng cùng thứ tự, test vẫn có thể pass dù bạn quên sort. Vì vậy phải đọc comparator và kiểm thử bằng dữ liệu có nhiều method overload / nhiều fields như `Sample`.

### Test 2: So khớp snapshot/golden output

Chạy chương trình, lưu output vào `expected.txt`, sau đó so sánh byte-for-byte hoặc chuỗi Unicode với kết quả hiện tại. Tệp snapshot phải được cập nhật **có chủ đích** khi contract hiển thị đổi. Để có file chuẩn UTF-8 trong shell hỗ trợ chuyển hướng:

~~~bash
java StableClassPrinter > actual.txt
~~~

Sau đó dùng công cụ diff/test của project để so `actual.txt` với `expected.txt`. Lưu ý encoding và kiểu xuống dòng (LF/CRLF) khác nhau giữa hệ điều hành; nếu snapshot cần dùng đa nền tảng, có thể chuẩn hóa newline trước khi so, **nhưng không thay đổi quy tắc sort**.

### Test 3: Thêm dữ liệu để thử comparator

- Đổi vị trí khai báo `name` và `id` trong mã nguồn, rồi biên dịch lại. Thứ tự fields trong stdout phải vẫn dựa trên tên.
- Đổi vị trí hai phương thức `describe` trong source. Thứ tự methods vẫn theo tên + kiểu tham số.
- Đổi thứ tự `implements Runnable, AutoCloseable` thành `implements AutoCloseable, Runnable`. Thứ tự output vẫn giữ `java.lang.AutoCloseable` trước `java.lang.Runnable`.
- Thêm overload `describe(long)`. Comparator phải đưa nó vào đúng vị trí từ điển theo tên tham số kiểu, không phụ thuộc thứ tự viết code.

Không khẳng định mọi thay đổi sẽ có bytecode hoàn toàn giống nhau: kiểm thử ở đây xác nhận **quy tắc thứ tự hiển thị**, không xác nhận compiler phát sinh cùng một thứ tự metadata thô.

## 7. Những giới hạn cần nêu trước khi dùng trong hệ thống thật

### 7.1. Reflection metadata không phải cú pháp source

Printer không tái tạo generics/annotations/`throws` chính xác như source Java. `Field.getType()` và `Method.getReturnType()` cho kiểu đã erasure ở những tình huống generic; muốn giữ thông tin generic được lưu trong classfile, xem `Field.getGenericType()`, `Method.getGenericReturnType()` và `Executable.getGenericParameterTypes()`. Những API này trả `Type`, không phải luôn `Class<?>`, và cần formatter riêng cho `ParameterizedType`, `TypeVariable`, `GenericArrayType`, `WildcardType`. Cần quy định sắp xếp và serialization của những biểu thức kiểu đó nếu mục tiêu là API signature tương đối đầy đủ.

Chương trình không hiển thị annotation của class/member, exception types (`throws`), generic type parameters, record components, nested classes, enum constants như một mục riêng hay inherited public API. Để mở rộng, thêm **mỗi mục riêng** với chiến lược sort phù hợp; không nên hứa output ở trên là toàn bộ mô hình Java class file.

### 7.2. Không phải mọi `Class<?>` đều là normal class

Với `int.class`, `void.class`, array type, interface, annotation type, enum, record, local/anonymous class, hidden class hoặc dynamic proxy class, metadata có thể khác giả định “class thường”. Ví dụ `getCanonicalName()` có thể trả `null` và `getDeclaredConstructors()` có thể trả mảng rỗng.

Mã `describe(Class<?>)` trong bài có fallback cho tên kiểu và superclass, nên tránh một số NPE; nhưng định dạng đầu ra hiện viết nhãn `CLASS` chung, **không phân biệt đầy đủ category** (interface/enum/record/annotation). Nếu làm công cụ sản phẩm, hãy thêm `isInterface()`, `isAnnotation()`, `isEnum()`, `isRecord()`, `isArray()`, `isPrimitive()`, `isHidden()` và định dạng rõ từng loại.

### 7.3. Một số metadata có thể do compiler/instrumentation sinh

Bridge/synthetic methods, các field trợ giúp, hidden classes và bytecode instrumentation có thể thay đổi metadata theo compiler hoặc cơ chế build. Vì vậy output ổn định là hàm của **class metadata thực tế + quy tắc sort**, không phải một bản snapshot bảo đảm giống hệt giữa mọi JDK/build khác nhau.

Một vấn đề nâng cao: comparator tốt cần xử lý những trường hợp có **khóa hoàn toàn bằng nhau nhưng phần tử vẫn khác nhau theo khía cạnh bạn muốn in**, ví dụ khi bổ sung annotations, generic signatures, `throws` hoặc thông tin synthetic. Khi đó thêm tie-breaker theo chính các trường sẽ in (được chuẩn hóa). Nếu hai entries giống hệt nhau trên toàn bộ nội dung được xuất, đổi chỗ chúng cũng không làm thay đổi chuỗi đầu ra. Không nên dùng `hashCode()` của reflection object làm tie-breaker vì không phải khóa canonical có ý nghĩa ổn định.

### 7.4. Quyền truy cập và bảo mật

Các method `getDeclared...` trong ví dụ chỉ **liệt kê metadata**, không đọc giá trị private fields và không gọi private methods. Printer vì thế **không dùng `setAccessible(true)`**. Tuy nhiên với security policy hoặc môi trường đặc biệt, việc truy vấn metadata vẫn có thể bị hạn chế. Nếu mở rộng thành công cụ “in giá trị field của đối tượng”, đó là một nhiệm vụ khác, cần chính sách quyền riêng tư, redaction, access control và kiểm soát vòng lặp tham chiếu. **Không log giá trị mật khẩu, token hoặc dữ liệu nhạy cảm chỉ vì Reflection nhìn thấy field.**

### 7.5. Nhiều cách “ổn định” khác nhau

Có thể sort theo:

- Tên field/method + signature như bài này: dễ đọc, ổn định và phù hợp tài liệu.
- Chữ ký JVM descriptor: phù hợp phân tích bytecode nhưng ít thân thiện.
- Phân nhóm theo access modifier trước, rồi tên/signature: phù hợp tài liệu API cho người dùng.
- Tên full canonical có normalization versioned: cần khi dùng làm hash hay dữ liệu trao đổi giữa toolchains.

Điều quan trọng không phải chỉ có một comparator “đúng”, mà là **công bố contract, sắp xếp mọi collection không đảm bảo thứ tự, kiểm thử với nhiều overload và giữ contract nhất quán**.

## 8. Những lỗi phổ biến

| Sai lầm | Vì sao không ổn | Cách khắc phục |
|---|---|---|
| In thẳng mảng `getDeclaredMethods()` | Javadoc không cam kết thứ tự | `Arrays.sort` hoặc `stream.sorted` với comparator xác định |
| Chỉ sort `Method::getName` | Không tách overload | Thêm parameter type signature và return type |
| Dùng `getMethods()` nhưng ghi nhãn “declared methods” | Bao gồm inherited public methods | Chọn `getDeclaredMethods()` hoặc đổi scope label |
| In danh sách `getInterfaces()` theo thứ tự có sẵn | Mục tiêu canonical cần định nghĩa sort | Map sang tên kiểu rồi sort |
| Gọi `getSimpleName()` cho tất cả | Có thể trùng tên giữa package, rỗng với anonymous types | Ưu tiên canonical name với fallback |
| Coi Reflection là source parser | Không có đủ thông tin về thứ tự source, comment, một số generic details | Dùng AST/compiler model nếu cần thông tin nguồn |
| Vứt hết `synthetic`/`bridge` không giải thích | Bỏ một phần cấu trúc runtime | Có chế độ lọc được công bố; mặc định giữ/đánh dấu nếu làm diagnostics |
| Dùng `setAccessible(true)` để in chữ ký | Không cần, tăng rủi ro và có thể bị JPMS chặn | Chỉ đọc metadata qua Reflection |
| Đưa object identity/hash vào đầu ra | Không phải đặc điểm cấu trúc ổn định giữa các lần chạy | In tên kiểu, signature, flags |
| So stdout bằng mắt một lần | Không phát hiện thiếu tie-breakers | Test snapshot/so sánh với overloads và source reorder |

## 9. Bài tập mở rộng

1. Thêm một field `private boolean enabled` và một method `protected int score(double multiplier)`. Xác định chính xác vị trí của chúng trong output trước khi chạy.
2. Viết method `describe(Class<?> type, boolean includeInherited)`. Khi `includeInherited=true`, dùng nhóm API phù hợp và định nghĩa cách xử lý override. Đừng gọi đó là cùng phạm vi với `getDeclaredMethods()`.
3. Thêm interface `java.io.Serializable` vào `Sample`. Xác minh danh sách interfaces được sort dù thứ tự trong `implements` đảo chiều.
4. Tạo generic base class để compiler phát sinh bridge method. Quan sát `isBridge()`/`isSynthetic()` và sửa cách in nếu muốn chế độ “source-like view”.
5. Thêm cột `throws` bằng `getExceptionTypes()`. Chọn thứ tự danh sách exception sao cho phù hợp mục tiêu “signature view”, không tự ý đổi ý nghĩa thứ tự tham số của method.
6. Thêm section `RECORD_COMPONENTS` dùng `Class.getRecordComponents()` cho `record`; quyết định rõ output là **thứ tự component khai báo** hay **thứ tự canonical do công cụ tự sắp**.
7. Tạo unit test so `describe(Sample.class)` với golden text và lặp 100 lần; rồi hoán đổi thứ tự khai báo methods trong source để chứng minh output không dựa vào thứ tự Reflection trả về.
8. Tạo một wrapper CLI nhận tên class qua `args[0]`, gọi `Class.forName(...)` và in cấu trúc; bổ sung xử lý `ClassNotFoundException` cùng chính sách chỉ nhận những tên class tin cậy. Cẩn trọng vì nạp và khởi tạo lớp có thể gây side effects.

**Ghi nhớ:** Reflection cung cấp metadata, **không cung cấp thứ tự canonical mặc định** cho fields, constructors và methods. Để in cấu trúc lớp ổn định, hãy quyết định rõ phạm vi (`declared` hay `inherited`), định nghĩa một comparator có đủ khóa cho từng collection, chuẩn hóa tên kiểu, không dựa vào object identity và kiểm thử với overloads/bridge/synthetic. Khi cần source-level representation thay vì runtime structure, hãy cân nhắc compiler model hoặc AST thay vì cố suy ngược source từ Reflection.

### Tài liệu tham khảo (Java 17)

- [`Class.getDeclaredFields`, `getDeclaredMethods` và `getDeclaredConstructors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [`Method` và metadata bridge/synthetic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [`Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html)
- [`Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [`Modifier.toString`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Modifier.html#toString(int))
- [`Comparator`, `thenComparing`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html)
