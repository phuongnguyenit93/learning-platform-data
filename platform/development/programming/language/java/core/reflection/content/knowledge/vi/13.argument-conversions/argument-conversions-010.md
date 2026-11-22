# Chuyển đổi giá trị trả về và ClassCastException ở mã gọi khi dùng Java Reflection

## 1. Phân biệt kiểu khai báo, giá trị runtime và kiểu ở mã gọi

Khi dùng Java Reflection để gọi phương thức, API trung tâm là `java.lang.reflect.Method.invoke(Object receiver, Object... args)`. Dù phương thức đích có khai báo trả về `int`, `String`, `Number`, `List<String>` hay `void`, **kiểu trả về tĩnh của `Method.invoke` vẫn là `Object`**.

Đây là nguồn gốc của một số lỗi chuyển đổi:

- **Declared return type**: kiểu trong chữ ký phương thức, đọc qua `Method.getReturnType()`. Ví dụ `int.class` hoặc `String.class`.
- **Runtime result type**: lớp thực của đối tượng do `Method.invoke` trả về. Phương thức trả primitive `int` sẽ được boxing thành `Integer`; phương thức khai báo `Object` có thể thực sự trả `String` hoặc `Integer`.
- **Expected type của caller**: kiểu mã gọi muốn nhận khi ép kiểu, chẳng hạn `(String) result`, `(Long) result` hay `(List<String>) result`. Cast tham chiếu chỉ thành công nếu đối tượng thực tương thích.

Đề bài này tập trung vào **chuyển đổi giá trị trả về**, nguyên nhân và vị trí `ClassCastException` ở mã gọi, cách phân biệt với `InvocationTargetException`, xử lý primitive/`void`/`null`/generic, cùng chiến lược kiểm tra kiểu an toàn.

Một ví dụ ngắn:

```java
Method method = service.getClass().getMethod("count");
Object raw = method.invoke(service);     // count() khai báo int, trả 12
Integer boxed = (Integer) raw;          // Đúng: raw là Integer
long widened = boxed.longValue();      // Chuyển đổi số hợp lệ
// Long wrong = (Long) raw;            // ClassCastException
```

Đoạn trên là **minh họa bên trong phương thức** có `service`, có xử lý/khai báo ngoại lệ Reflection và import `java.lang.reflect.Method`; không phải chương trình Java độc lập.

## 2. Method.invoke thực sự trả lại loại giá trị gì?

| Return type khai báo của method đích | Giá trị `Method.invoke` trả về khi thành công | Lưu ý |
| --- | --- | --- |
| `String` | `String` hoặc `null` | Chỉ cast sang `String` khi runtime object phù hợp |
| `Object`, superclass hoặc interface | Object thuộc subtype cụ thể, hoặc `null` | Kiểu khai báo không nói chắc runtime subtype |
| `int` | `Integer` | Primitive được boxing |
| `long` | `Long` | Không chuyển `Integer` thành `Long` theo mong muốn của caller |
| `boolean` | `Boolean` | Wrapper đại diện primitive |
| `byte`, `short`, `char` | `Byte`, `Short`, `Character` | Wrapper tương ứng |
| `float`, `double` | `Float`, `Double` | Wrapper tương ứng |
| `void` | `null` | Method vẫn chạy và có thể tạo side effect |
| Kiểu tham chiếu trả `null` | `null` | Nhìn result đơn lẻ chưa biết method khai báo `void` hay return null |
| Mảng như `String[]` | Đối tượng mảng phù hợp | Không chuyển mảng thành danh sách hoặc tách thành nhiều giá trị |

`Method.getReturnType()` trả về `Class<?>` mô tả return type **khai báo sau type erasure**. Nếu cần chữ ký generic, dùng `getGenericReturnType()` trả về `Type`; metadata generic không tự kiểm chứng kiểu phần tử của dữ liệu runtime.

Một quy tắc quan trọng: phép cast tham chiếu `(TargetType) value` **không biến đổi dữ liệu**. Nếu `value` là `Integer`, `(String) value` không gọi `toString()` mà ném `ClassCastException`. Nếu `value` là `null`, cast sang một kiểu tham chiếu hợp lệ trả `null`; lỗi thường xuất hiện khi code tiếp tục dereference hoặc unbox.

## 3. Ví dụ Java 17+ hoàn chỉnh

Lưu toàn bộ chương trình dưới đây vào **`ReturnConversionDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ReturnConversionDemo {
    static class Api {
        public String name() {
            return "Ada";
        }

        public int count() {
            return 12;
        }

        public long total() {
            return 100L;
        }

        public void ping() {
            System.out.println("ping invoked");
        }

        public Object payload() {
            return Integer.valueOf(42);
        }

        public String explode() {
            throw new IllegalStateException("bad state");
        }
    }

    public static void main(String[] args) throws Exception {
        Api api = new Api();

        Method name = Api.class.getMethod("name");
        System.out.println("name declared: "
                + name.getReturnType().getSimpleName());
        String nameValue = (String) name.invoke(api);
        System.out.println("name value: " + nameValue);

        Method count = Api.class.getMethod("count");
        Object countResult = count.invoke(api);
        System.out.println("count declared: "
                + count.getReturnType().getSimpleName());
        System.out.println("count runtime: "
                + countResult.getClass().getSimpleName());

        Number number = (Number) countResult;
        System.out.println("count as long: " + number.longValue());

        try {
            Long bad = (Long) countResult;
        } catch (ClassCastException ex) {
            System.out.println("wrong wrapper: ClassCastException");
        }

        Object longResult = Api.class.getMethod("total").invoke(api);
        System.out.println("total runtime: "
                + longResult.getClass().getSimpleName());

        Method payload = Api.class.getMethod("payload");
        Object unknown = payload.invoke(api);
        System.out.println("payload declared: "
                + payload.getReturnType().getSimpleName());
        System.out.println("payload runtime: "
                + unknown.getClass().getSimpleName());

        try {
            String wrong = (String) unknown;
        } catch (ClassCastException ex) {
            System.out.println("payload wrong String: ClassCastException");
        }
        System.out.println("payload matches String: "
                + String.class.isInstance(unknown));

        Object resultOfVoid = Api.class.getMethod("ping").invoke(api);
        System.out.println("void returns null: " + (resultOfVoid == null));

        try {
            int countValue = (Integer) resultOfVoid;
        } catch (NullPointerException ex) {
            System.out.println("null unboxing: NullPointerException");
        }

        try {
            Api.class.getMethod("explode").invoke(api);
        } catch (InvocationTargetException ex) {
            System.out.println("target threw: "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac ReturnConversionDemo.java
java ReturnConversionDemo
```

Output:

```text
name declared: String
name value: Ada
count declared: int
count runtime: Integer
count as long: 12
wrong wrapper: ClassCastException
total runtime: Long
payload declared: Object
payload runtime: Integer
payload wrong String: ClassCastException
payload matches String: false
ping invoked
void returns null: true
null unboxing: NullPointerException
target threw: IllegalStateException
```

### Giải thích từng đoạn

1. `name()` khai báo `String`, nên `Method.getReturnType()` là `String.class`. `name.invoke(api)` trả đối tượng `String` thực sự; phép `(String)` hợp lệ.
2. `count()` khai báo primitive `int`, nhưng `invoke` đưa kết quả vào `Object` nên boxing thành `Integer`. `getReturnType()` vẫn trả `int.class`, còn `countResult.getClass()` là `Integer.class`.
3. `Number number = (Number) countResult` đúng do `Integer extends Number`. `number.longValue()` trả `12L`. Ngược lại `(Long) countResult` đòi đối tượng là `Long`, trong khi nó là `Integer`: `ClassCastException` xảy ra **ở caller**.
4. `total()` khai báo `long` và result runtime là `Long`. Wrapper phải tương ứng với primitive đã trả, không theo yêu cầu tùy ý của mã gọi.
5. `payload()` khai báo `Object` nhưng trả `Integer(42)`. Đây là return value hoàn toàn hợp lệ. Khi caller ép `(String) unknown`, cast mới thất bại; `String.class.isInstance(unknown)` giúp phát hiện trước.
6. `ping()` thực hiện side effect in dòng `ping invoked`, sau đó `Method.invoke` trả `null` do return type là `void`. Ép `(Integer) null` hợp lệ, nhưng unboxing tiếp sang `int` làm phát sinh `NullPointerException`.
7. `explode()` ném `IllegalStateException` **bên trong method đích**. `Method.invoke` chuyển lỗi này thành `InvocationTargetException`, và caller lấy nguyên nhân bằng `getCause()`.

Ví dụ sử dụng đúng chữ ký API thực; phần output được đối chiếu bằng thực thi Java 17+.

## 4. ClassCastException ở caller xuất hiện sau khi invoke hoàn thành

Xem hai câu lệnh:

```java
Object raw = method.invoke(receiver);
String text = (String) raw;
```

Giả sử phương thức đích trả về `Integer.valueOf(42)`. Câu lệnh **đầu tiên đã thực thi thành công**: method chạy, Reflection trả lại một `Integer` dưới kiểu tĩnh `Object`. Câu lệnh thứ hai mới ném `ClassCastException` vì JVM kiểm tra object thực khi thực hiện ép kiểu tham chiếu.

Nếu viết gọn:

```java
String text = (String) method.invoke(receiver);
```

thì thứ tự vẫn như vậy: gọi method → nhận `Object` → cast sang `String`. Phép cast là phần mã do **caller** yêu cầu. Trong bytecode, compiler thường sinh `checkcast` tại điểm nhận giá trị.

Đừng kết luận lỗi thuộc thư viện Reflection chỉ vì stack trace chỉ đến dòng có `invoke` và cast chung một biểu thức. Tách thành hai câu lệnh để biết chính xác ranh giới.

### Cast không đồng nghĩa chuyển đổi

```java
Object raw = Integer.valueOf(42);

Number asNumber = (Number) raw; // Thành công
Integer asInteger = (Integer) raw; // Thành công
// String bad = (String) raw;   // ClassCastException
String text = raw.toString();     // Chuỗi biểu diễn "42"
```

`toString()` là chuyển đổi thành representation dạng chuỗi, có thể có hành vi tùy kiểu và không dùng được trực tiếp với `null`. `String.valueOf(raw)` hỗ trợ `null` nhưng trả chuỗi chữ `"null"`, không phải giá trị tham chiếu `null`. Một API mong đợi **đúng đối tượng String** không nên tự tiện thay bằng chuỗi biểu diễn của object khác.

## 5. Primitive boxing, unboxing và widening

Khi gọi phương thức thông thường:

```java
int small = api.count();
long bigger = small;
```

compiler có thể widening primitive `int` sang `long` khi gán. Nhưng sau Reflection:

```java
Object raw = countMethod.invoke(api);
```

giá trị `raw` là `Integer`. Vì `Integer` và `Long` là hai class không có quan hệ kế thừa, `Long result = (Long) raw` thất bại.

Các cách đúng khi `raw` chứa `Integer`:

```java
Integer boxed = (Integer) raw;
int n = boxed;
long widened = n;

long alsoWidened = (Integer) raw; // Unbox int rồi widen long
long viaNumber = ((Number) raw).longValue();
```

Đây là các đoạn code minh họa bên trong một method có `raw` đã được nhận và bảo đảm khác `null`.

**Không đồng nhất các cách chuyển đổi:** `Number.longValue()` được hỗ trợ bởi nhiều kiểu số, nhưng với kiểu có phần thập phân hoặc số vượt khoảng biểu diễn, kết quả có thể bị cắt/mất chính xác. Cần định nghĩa cách xử lý overflow và precision nếu dữ liệu runtime không chắc chắn.

Một lỗi tương tự là cast `Double` sang `Integer` chỉ vì cả hai đại diện cho số: `(Integer) Double.valueOf(1.5)` không hợp lệ. Muốn chuyển giá trị, dùng API số hoặc converter có quy tắc cụ thể.

### Primitive return và Class.cast

Khi kiểm tra result được boxing qua `Class.cast`, dùng wrapper:

```java
Integer count = Integer.class.cast(countMethod.invoke(api));
```

`int.class.cast(result)` **không** tương đương, vì `int.class` biểu diễn primitive type, không phải loại object boxed có thể được kiểm tra bằng cast tham chiếu.

## 6. Void, null và NullPointerException

Hai trường hợp khác nhau cùng cho `raw == null`:

- Method khai báo `void`: `Method.invoke` luôn trả `null` sau khi method chạy thành công.
- Method khai báo kiểu tham chiếu như `String`: bản thân method có thể trả `null`.

Nếu muốn phân biệt, hãy đọc metadata:

```java
if (method.getReturnType() == void.class) {
    // Method không khai báo trả về một giá trị.
}
```

Còn nếu caller cần chuyển result sang primitive thì phải xử lý null trước:

```java
Object raw = method.invoke(receiver);
if (raw == null) {
    throw new IllegalStateException("Expected a non-null number");
}
if (!(raw instanceof Number number)) {
    throw new IllegalArgumentException("Expected Number");
}
int value = number.intValue();
```

Đoạn trên là mẫu minh họa trong phương thức với `method`, `receiver` hợp lệ. `(Integer) null` tự nó trả `null`, nhưng việc gán vào `int` gọi unboxing và ném `NullPointerException`. Đó là **lỗi khác `ClassCastException`**.

Không gọi `raw.getClass()` khi raw có thể bằng null. Khi chuẩn đoán, dùng `raw == null ? "null" : raw.getClass().getName()`.

## 7. Phân biệt lỗi ở caller và InvocationTargetException

Các lỗi quanh Reflection xảy ra ở những giai đoạn khác nhau:

| Tình huống | Nơi phát sinh | Ngoại lệ |
| --- | --- | --- |
| `getMethod` không tìm được chữ ký | Tra cứu metadata | `NoSuchMethodException` |
| Không có quyền gọi phương thức | Kiểm tra truy cập | Thường `IllegalAccessException` |
| Đối số truyền cho `invoke` không phù hợp | Giai đoạn chuẩn bị thực thi | Thường `IllegalArgumentException` |
| Method đích tự ném `IllegalStateException` | Bên trong method đích | `InvocationTargetException` bọc nguyên nhân |
| Method đích tự ném `ClassCastException` | Bên trong method đích | `InvocationTargetException` bọc nguyên nhân |
| Cast `(String) raw` sau khi `invoke` trả `Integer` | Mã gọi sau khi method trả về | `ClassCastException` trực tiếp |
| Unboxing result `null` thành `int` | Mã gọi sau khi method trả về | `NullPointerException` |

Điểm cần nhớ: **`InvocationTargetException` chỉ biểu diễn exception/error thoát ra từ code của method đích** (trong ngữ cảnh invocation). Nếu caller tự cast sai **sau khi** method đã trả về, Reflection không thể quay lại bọc lỗi đó.

Một cách phân tách trách nhiệm:

```java
Object raw;
try {
    raw = method.invoke(receiver);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable targetCause = ex.getCause();
    throw new IllegalStateException("Target method failed", targetCause);
}

// Sau khi invoke thành công, chuyển đổi là trách nhiệm caller.
if (!(raw instanceof String text)) {
    throw new IllegalArgumentException("Expected a String result");
}
System.out.println(text);
```

Đây là **đoạn minh họa**, đặt trong một phương thức đã xử lý hoặc khai báo các exception khác như `IllegalAccessException`. Chính sách ở ví dụ yêu cầu String khác null; hệ thống cho phép return null phải có nhánh riêng.

### Hai ví dụ dễ bị đánh đồng

- `Integer actual = ...; String text = (String) (Object) actual;` gây `ClassCastException` trực tiếp trong mã thực hiện cast.
- Nếu method đích chứa cast sai tương tự rồi bị gọi bằng `Method.invoke`, caller sẽ thấy `InvocationTargetException` với `getCause() instanceof ClassCastException`.

Nhìn **stack trace và chuỗi nguyên nhân** để xác định nơi lỗi xuất phát.

## 8. Kiểu khai báo không phải kiểu runtime

Xét:

```java
class Base {
    public Object value() { return "base"; }
}
class Derived extends Base {
    @Override
    public String value() { return "derived"; }
}
```

Một đoạn trong phương thức có xử lý ngoại lệ:

```java
Method m = Base.class.getMethod("value");
Object raw = m.invoke(new Derived());

System.out.println(m.getReturnType().getSimpleName()); // Object
System.out.println(raw.getClass().getSimpleName());    // String
```

`Method.getReturnType()` mô tả metadata của method được lấy từ `Base`; runtime thực hiện dispatch theo instance `Derived` nên kết quả là `String`. Cast sang `String` hợp lệ vì **đối tượng thực** là String, mặc dù return type khai báo ở `Base` là `Object`.

Tương tự, khi return type là interface hoặc superclass, có thể nhận subtype hợp lệ. Vì vậy, nếu mục tiêu là cast xuống subtype cụ thể, luôn xem xét `instanceof` hoặc `Class.isInstance`.

### Bridge method và generic return

Với generic hoặc covariant return, compiler có thể sinh bridge method; Reflection có thể liệt kê các method này. `Method.isBridge()` và `Method.isSynthetic()` cho biết trường hợp tương ứng. Khi có nhiều method cùng tên, không chọn bừa phần tử đầu tiên từ `getDeclaredMethods()`: thứ tự không được bảo đảm, và chữ ký hoặc return metadata có thể khác.

Nếu method đích hoặc bridge tự cast sai, lỗi đi qua cơ chế wrapper của `Method.invoke`; nếu caller cast kết quả sai, lỗi nằm sau lời gọi. Phân biệt bằng stack trace và `InvocationTargetException.getCause()`.

## 9. ClassCastException và generic type erasure

Một method có thể khai báo `List<String>` và `getGenericReturnType()` mô tả được generic signature, nhưng runtime không tự xác minh tất cả phần tử thực sự là String.

Ví dụ đoạn code minh họa:

```java
Object raw = method.invoke(receiver);

if (raw instanceof java.util.List<?> list) {
    System.out.println("Items: " + list.size());
}
```

Cách kiểm tra trên biết `raw` thực sự là List, nhưng không bảo đảm mỗi item là String. Không thể viết `raw instanceof List<String>` vì parameterized type đó không reifiable tại runtime.

Một cast không kiểm tra phần tử có thể thành công ban đầu rồi lỗi xuất hiện muộn:

```java
@SuppressWarnings("unchecked")
java.util.List<String> values =
        (java.util.List<String>) raw;

// Khi đọc phần tử, compiler có thể chèn cast thành String.
String first = values.get(0);
```

Nếu phần tử đầu tiên thực là Integer, lỗi `ClassCastException` có thể xuất hiện ở dòng nhận `first`, **không phải** ở phép cast nguyên List. Vì thế với dữ liệu từ plugin, JSON mapper hoặc API runtime, nên dùng `List<?>` rồi validate từng phần tử khi cần bảo đảm kiểu.

## 10. Generic helper trả T chưa chắc kiểm tra T

Hàm tiện ích sau trông có vẻ trả đúng kiểu:

```java
@SuppressWarnings("unchecked")
static <T> T call(Method method, Object target)
        throws ReflectiveOperationException {
    return (T) method.invoke(target);
}
```

Nhưng type erasure khiến `T` không được kiểm tra như `String` ở thân hàm. Nếu mã gọi viết:

```java
String result = call(method, target);
```

compiler có thể đưa phép `checkcast String` ở **vị trí mã gọi sử dụng kết quả**. Khi method trả Integer, `ClassCastException` vẫn có thể xảy ra phía caller, bất chấp generic helper đã return.

Một thiết kế rõ ràng hơn là truyền cả runtime type token:

```java
static <T> T callAs(
        Method method, Object target, Class<T> expected)
        throws ReflectiveOperationException {
    Object raw = method.invoke(target);
    return expected.cast(raw);
}
```

Mẫu này yêu cầu caller chọn type cụ thể, ví dụ `String.class` hoặc `Integer.class` (đối với primitive int đã boxing). `Class.cast(null)` vẫn trả null; nếu không chấp nhận null thì thêm kiểm tra riêng. Nếu object có generic parameter như `List<String>`, chỉ một `Class<List>` không kiểm tra được toàn bộ phần tử.

## 11. Kiểm tra kiểu an toàn bằng instanceof và Class.cast

### 11.1. Pattern matching cho instanceof (Java 17)

```java
static String requireString(Object raw) {
    if (raw instanceof String text) {
        return text;
    }
    throw new IllegalArgumentException(
            "Expected String; actual="
                    + (raw == null ? "null" : raw.getClass().getName()));
}
```

Đây là một phương thức tiện ích đầy đủ về cú pháp Java khi đặt trong một class. Nó coi null là không hợp lệ theo chủ ý. Một API cho phép null cần quy tắc khác.

### 11.2. Class.isInstance và Class.cast

```java
static <T> T checkedCast(Object value, Class<T> expected) {
    if (!expected.isInstance(value)) {
        throw new IllegalArgumentException("Unexpected return type");
    }
    return expected.cast(value);
}
```

Đây là phương thức tiện ích có thể đặt trong class. `expected.isInstance(null)` là false, nên nó cũng từ chối null. `Class.cast` kiểm tra type thực và có thể ném `ClassCastException` khi giá trị không thuộc class mong muốn.

Khi muốn **chuyển đổi** một kiểu số sang kiểu số khác (ví dụ Integer → long), chỉ kiểm tra class không đủ; phải định nghĩa rõ conversion, overflow, null, độ chính xác.

### 11.3. Xử lý String khác biểu diễn String

Nếu hợp đồng yêu cầu chính xác return type String, dùng cast đã kiểm tra. Nếu hợp đồng là “hiển thị thông tin” và chấp nhận bất cứ object nào, dùng converter riêng hoặc `String.valueOf` với hành vi null đã được thống nhất. Không âm thầm biến số, collection hoặc object nghiệp vụ thành String khi phía gọi yêu cầu một thực thể có kiểu.

## 12. Mảng, class loader và các tình huống đặc biệt

### Mảng là object

Method trả `String[]` sẽ làm `Method.invoke` trả một đối tượng mảng `String[]`:

```java
Object raw = arrayMethod.invoke(receiver);
if (raw instanceof String[] values) {
    System.out.println(values.length);
}
```

Đoạn code minh họa giả định method đích phù hợp. Mảng `int[]` không phải `Integer[]`; Reflection không tự boxing toàn bộ phần tử của mảng trả về thành một mảng wrapper mới. Kiểu mảng thực quyết định cast có hợp lệ hay không.

### Hai class cùng tên có thể vẫn không cast được

Trong môi trường plugin, class loader hoặc hot reload, hai class có **cùng binary name** nhưng được load bởi hai class loader định nghĩa khác nhau có thể là hai kiểu runtime không tương thích. `ClassCastException` khi đó không nhất thiết do tên hiển thị khác nhau.

Để chẩn đoán, có thể xem `raw.getClass()`, `raw.getClass().getClassLoader()` và class loader của expected type. Cách sửa là thống nhất ranh giới type/class loader (chẳng hạn API/interface dùng chung), không dùng cast mạnh hơn.

### Method.invoke, Field.get và Constructor.newInstance khác nhau

| API | Giá trị trả về | Ý nghĩa |
| --- | --- | --- |
| `Method.invoke(...)` | `Object` | Primitive method return được boxing; `void` thành null |
| `Field.get(...)` | `Object` | Field primitive được boxing |
| `Field.getInt(...)` | `int` | API đọc primitive chuyên biệt khi chuyển đổi hợp lệ |
| `Constructor<T>.newInstance(...)` | `T` | Tạo object của lớp khai báo khi được phép, không có void return |

Không tổng quát hóa rằng mọi API Reflection có chung quy tắc chuyển đổi. Bài này tập trung vào **return value của Method.invoke**.

## 13. Quy trình chẩn đoán lỗi trong thực tế

1. **Tách lệnh invoke khỏi phép cast** để xác định điểm ném lỗi: `Object raw = method.invoke(target);` rồi mới cast.
2. **Kiểm tra method thực sự được chọn** qua `getDeclaringClass()`, `getName()`, `getParameterTypes()` và `getReturnType()`. Overload hoặc bridge có thể làm caller dùng sai metadata.
3. **Xem giá trị null trước khi gọi getClass()**. Nếu `getReturnType() == void.class`, không mong đợi giá trị.
4. **Nếu khác null, kiểm tra runtime type** và quan hệ subtype/interface với expected type. Với primitive, nhớ wrapper tương ứng.
5. **Nếu cần số kiểu khác, chuyển đổi rõ ràng** thay vì cast wrapper sai. Kiểm soát overflow/precision.
6. **Xem wrapper của exception**. `InvocationTargetException.getCause()` biểu diễn lỗi ở method đích; `ClassCastException` sau phép cast là lỗi caller.
7. **Nếu generic hoặc class loader phức tạp**, kiểm tra element type, bridge method và class loader định nghĩa type.

Ví dụ log chẩn đoán chỉ dựa trên metadata/kiểu (tránh log dữ liệu nhạy cảm):

```java
Object raw = method.invoke(receiver);
String declared = method.getReturnType().getTypeName();
String actual = raw == null ? "null" : raw.getClass().getName();
System.out.println("declared=" + declared + ", actual=" + actual);
```

Đây là đoạn minh họa trong method đã có biến phù hợp và xử lý ngoại lệ. Nếu kết quả là Integer khi mã cần String, bước sửa nằm ở **hợp đồng kiểu/chuyển đổi của caller**, không nằm ở việc sửa `Method.invoke`.

## 14. Lỗi phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Tin rằng method trả int thì `invoke` trả primitive int | Nhầm wrapper | Chờ Integer và unbox |
| Cast `Integer` sang `Long` để widen | ClassCastException | Unbox rồi widening hoặc dùng Number |
| Cast mọi object thành String | ClassCastException | Kiểm tra instanceof; dùng converter nếu thật sự cần |
| Unbox return của void | NullPointerException | Xét `getReturnType() == void.class` |
| Không kiểm tra null trước `getClass()` | NullPointerException | Nhánh null rõ ràng |
| Chỉ nhìn return type khai báo Object để đoán String | Sai runtime type | Kiểm tra giá trị thực |
| Xem mọi ClassCastException là lỗi của method đích | Chẩn đoán sai | Phân biệt lỗi trực tiếp và cause của InvocationTargetException |
| Dùng `(T)` generic và nghĩ runtime type được validate | ClassCastException muộn ở caller | Dùng runtime type token và kiểm tra |
| Cast thành `List<String>` mà không kiểm tra phần tử | ClassCastException khi đọc phần tử | Dùng `List<?>` và validate |
| Giả định hai class cùng tên luôn cast được | Lỗi với class loader khác nhau | Kiểm tra class identity và loader |

## 15. Câu hỏi tự kiểm tra

**1.** Method `int count()` trả 12. Đối tượng runtime từ `Method.invoke()` có class nào?

**Đáp án:** `Integer.class`. Primitive `int` được boxing vào kết quả kiểu `Object`.

**2.** Tại sao `Long number = (Long) method.invoke(target)` lỗi khi method trả `int`?

**Đáp án:** Runtime value là Integer, không phải Long. Cast tham chiếu giữa hai wrapper không thực hiện widening primitive. Hãy unbox Integer rồi widen sang long.

**3.** Method `void ping()` vẫn in thông báo. `invoke` trả gì?

**Đáp án:** `null`, mặc dù method đã chạy và có side effect.

**4.** Vì sao `int n = (Integer) raw` ném NullPointerException nếu raw bằng null?

**Đáp án:** Cast tham chiếu null sang Integer hợp lệ; lỗi phát sinh ở bước unboxing Integer null thành int.

**5.** Khi nào một `ClassCastException` bị bọc trong `InvocationTargetException`?

**Đáp án:** Khi chính method đích (hoặc code nó gọi) ném ClassCastException và lỗi đó thoát ra trong quá trình invoke. Nếu caller tự cast sai sau khi invoke trả về, lỗi xuất hiện trực tiếp ở caller.

**6.** `Method.getReturnType()` trả Object nhưng `raw.getClass()` trả String. Có mâu thuẫn không?

**Đáp án:** Không. String là subtype của Object, nên object thực có thể cụ thể hơn return type đã khai báo.

**7.** `List<?>` có chứng minh tất cả phần tử là String không?

**Đáp án:** Không. Generic bị erasure; cần kiểm tra từng phần tử hoặc hợp đồng dữ liệu đáng tin cậy.

**8.** Một helper `<T> T call(...)` có bảo đảm giá trị đã được cast đúng String bên trong helper không?

**Đáp án:** Không. T bị type erasure; compiler có thể đặt runtime cast ở điểm caller nhận kết quả. Có thể truyền `Class<T>`, kiểm tra bằng `Class.cast` và xử lý null/generic riêng.

**Ghi nhớ:** `Method.invoke` trả `Object`, boxing primitive và trả null cho void. Java không tự chuyển object sang kiểu caller muốn nhận. `ClassCastException` sau khi invoke trả về thường xuất phát từ **phép cast ở caller**. Hãy đối chiếu declared return type, runtime result type và expected type, đồng thời phân biệt nó với `InvocationTargetException` khi method đích thật sự ném lỗi.
