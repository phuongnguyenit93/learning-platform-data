# Primitive return được boxing và `void` trả về `null` khi dùng `Method.invoke`

Trong Java Reflection, `java.lang.reflect.Method.invoke(Object obj, Object... args)` có **kiểu trả về `Object`**, dù phương thức thực tế được khai báo trả về `int`, `boolean`, `String`, `Integer` hay `void`. Vì vậy, khi gọi phương thức bằng Reflection, cần phân biệt **kiểu trả về được khai báo** với **đối tượng mà `invoke` trả lại**.

Hai quy tắc trọng tâm:

1. Nếu phương thức được gọi **trả về một giá trị primitive** (`int`, `boolean`, `double`...), `Method.invoke` **boxing** giá trị ấy thành đối tượng wrapper tương ứng (`Integer`, `Boolean`, `Double`...) trước khi trả về.
2. Nếu phương thức được khai báo **`void`**, `Method.invoke` **trả về `null` khi lời gọi kết thúc bình thường**. `null` ở đây là kết quả theo hợp đồng của Reflection, không phải giá trị do một phương thức `void` tự `return`.

Ngoài ra, một phương thức có **kiểu trả về tham chiếu** (`String`, `Integer`, một object bất kỳ) có thể thực sự trả về `null`. Bởi vậy, **chỉ nhìn `result == null` không thể biết phương thức gốc là `void` hay là một phương thức trả về tham chiếu đang có giá trị `null`**. Phải đọc metadata bằng `Method.getReturnType()`.

## 1. `Method.invoke` làm gì với giá trị trả về?

Chữ ký rút gọn:

```java
Object result = method.invoke(receiver, arguments);
```

- `method`: đối tượng `Method` mô tả một phương thức cụ thể đã được tìm bằng Reflection.
- `receiver`: instance dùng để gọi instance method; với static method, có thể truyền `null` vì không cần instance.
- `arguments`: các đối số đầu vào; phải phù hợp số lượng và kiểu tham số của phương thức.
- `result`: kết quả của lời gọi dưới dạng `Object` hoặc `null`. Nếu code bên trong phương thức ném exception, việc gọi không tạo ra một giá trị trả về bình thường.

`Method.invoke` không thay đổi kiểu trả về **được khai báo** của phương thức. Nó chỉ cần biểu diễn một kết quả có thể thuộc nhiều kiểu Java khác nhau qua **một kiểu trả về duy nhất của API**: `Object`.

| Phương thức khai báo | Giá trị logic sau khi method chạy | Kết quả từ `Method.invoke` |
|---|---|---|
| `int count()` | `7` | `Integer.valueOf(7)` dưới dạng `Object` |
| `long total()` | `30L` | Một `Long` có giá trị `30` |
| `boolean enabled()` | `false` | `Boolean.FALSE` dưới dạng `Object` |
| `char letter()` | `'A'` | Một `Character` có giá trị `'A'` |
| `double rate()` | `2.5` | Một `Double` có giá trị `2.5` |
| `String name()` | `"Lan"` | Tham chiếu tới `String` chứa `"Lan"` |
| `String missing()` | `null` | `null` |
| `Integer nullable()` | `null` | `null` |
| `void update()` | Không có giá trị trả về | `null` |

Các ví dụ trên giả định phương thức hoàn tất **bình thường** và caller có quyền truy cập phương thức. Nếu method ném exception, `invoke` thường báo `InvocationTargetException`, không trả về `null` như kết quả thông thường.

### Boxing áp dụng cho đủ tám primitive

| Primitive return | Wrapper trong kết quả Reflection |
|---|---|
| `boolean` | `java.lang.Boolean` |
| `byte` | `java.lang.Byte` |
| `short` | `java.lang.Short` |
| `char` | `java.lang.Character` |
| `int` | `java.lang.Integer` |
| `long` | `java.lang.Long` |
| `float` | `java.lang.Float` |
| `double` | `java.lang.Double` |

Giá trị primitive `0`, `false` hay `'\u0000'` **không** trở thành `null`. Reflection vẫn tạo hoặc trả về wrapper biểu diễn giá trị đó. Việc JVM dùng cache wrapper cho một số giá trị hay tạo object mới là chi tiết không nên dựa vào: kiểm tra **giá trị bằng `equals` hoặc bằng phép so sánh primitive**, không so sánh danh tính wrapper bằng `==`.

## 2. `void` khác `Void` và khác phương thức trả về tham chiếu `null`

Ba khai báo sau có ngữ nghĩa khác nhau:

```java
public void log() {
    System.out.println("logged");
}

public String findName() {
    return null;
}

public Void noResultObject() {
    return null;
}
```

Đây là ba method minh họa, chưa phải chương trình có class và `main`. Khi gọi qua Reflection:

- `log()` chạy side effect là in ra `logged`; `Method.invoke` trả **`null`** vì kiểu trả về là `void`.
- `findName()` trả tham chiếu **`null`** do chính method trả về.
- `noResultObject()` khai báo **`java.lang.Void`** (một lớp tham chiếu) và trả `null`. `Void` thường được dùng trong API generic để biểu diễn không có giá trị kết quả; nó **khác** từ khóa `void`.

Không có “wrapper object” được Reflection tạo ra cho kết quả `void`. Giá trị `null` của `invoke` trong trường hợp này **không phải** `new Void()` và cũng không phải một instance `Void`.

Mặc dù ba lời gọi trên đều có thể trả `null` từ `invoke`, metadata của chúng khác nhau:

```java
Method log = Example.class.getMethod("log");
Method findName = Example.class.getMethod("findName");
Method noResultObject = Example.class.getMethod("noResultObject");

System.out.println(log.getReturnType() == void.class);               // true
System.out.println(findName.getReturnType() == String.class);        // true
System.out.println(noResultObject.getReturnType() == Void.class);    // true
```

Đây là **đoạn minh họa**; giả sử `Example` là class public chứa ba method public trên, và đoạn code nằm trong một phương thức có khai báo `throws ReflectiveOperationException` hoặc xử lý `NoSuchMethodException`.

Vì vậy, để phân biệt **không có return value theo chữ ký** với **một return value đang là null**, luôn đọc kiểu khai báo bằng `getReturnType()`.

## 3. Ví dụ Java 17+ hoàn chỉnh

Lưu thành **`MethodReturnDemo.java`**:

```java
import java.lang.reflect.Method;

public class MethodReturnDemo {
    public static class Service {
        public int count() { return 7; }
        public boolean active() { return false; }
        public char initial() { return 'A'; }
        public long total() { return 30L; }
        public void touch() { System.out.println("touch body"); }
        public String missing() { return null; }
        public Integer nullable() { return null; }
        public Integer boxed() { return 17; }
        public static double rate() { return 2.5; }
        public void fail() { throw new IllegalStateException("broken"); }
    }

    public static void main(String[] args) throws Exception {
        Service service = new Service();
        Class<Service> type = Service.class;

        Method count = type.getMethod("count");
        Object countValue = count.invoke(service);
        System.out.println("count return type: " + count.getReturnType().getName());
        System.out.println("count value: " + countValue + " / " + countValue.getClass().getSimpleName());

        Object active = type.getMethod("active").invoke(service);
        System.out.println("active value: " + active + " / " + active.getClass().getSimpleName());
        Object initial = type.getMethod("initial").invoke(service);
        System.out.println("initial value: " + initial + " / " + initial.getClass().getSimpleName());
        Object total = type.getMethod("total").invoke(service);
        System.out.println("total value: " + total + " / " + total.getClass().getSimpleName());

        Method touch = type.getMethod("touch");
        Object voidResult = touch.invoke(service);
        System.out.println("touch return type: " + touch.getReturnType().getName());
        System.out.println("touch result is null: " + (voidResult == null));

        Method missing = type.getMethod("missing");
        System.out.println("missing return type: " + missing.getReturnType().getName());
        System.out.println("missing result is null: " + (missing.invoke(service) == null));

        Method nullable = type.getMethod("nullable");
        Object nullableValue = nullable.invoke(service);
        System.out.println("nullable return type: " + nullable.getReturnType().getName());
        System.out.println("nullable result is null: " + (nullableValue == null));

        Object boxedValue = type.getMethod("boxed").invoke(service);
        System.out.println("boxed value: " + boxedValue + " / " + boxedValue.getClass().getSimpleName());

        Object rateValue = type.getMethod("rate").invoke(null);
        System.out.println("static rate: " + rateValue + " / " + rateValue.getClass().getSimpleName());

        int converted = (Integer) count.invoke(service);
        System.out.println("converted int: " + converted);

        try {
            int invalid = (Integer) nullableValue;
            System.out.println(invalid);
        } catch (NullPointerException ex) {
            System.out.println("nullable unboxing: " + ex.getClass().getSimpleName());
        }

        try {
            type.getMethod("fail").invoke(service);
        } catch (java.lang.reflect.InvocationTargetException ex) {
            System.out.println("method threw: " + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp (JDK 17 hoặc mới hơn):

```bash
javac MethodReturnDemo.java
java MethodReturnDemo
```

**Stdout đã được đối chiếu bằng JDK 21:**

```text
count return type: int
count value: 7 / Integer
active value: false / Boolean
initial value: A / Character
total value: 30 / Long
touch body
touch return type: void
touch result is null: true
missing return type: java.lang.String
missing result is null: true
nullable return type: java.lang.Integer
nullable result is null: true
boxed value: 17 / Integer
static rate: 2.5 / Double
converted int: 7
nullable unboxing: NullPointerException
method threw: IllegalStateException
```

### Phân tích theo thứ tự thực thi

1. `Service.count()` khai báo trả `int`; `Method.getReturnType().getName()` là `int`, nhưng object nhận từ `invoke` thuộc lớp runtime `Integer`. Hai thông tin cùng đúng vì **primitive được boxing ở ranh giới Reflection**.
2. `active()` trả primitive `false` nên `invoke` đưa ra `Boolean(false)`; `initial()` trả primitive `'A'` nên có `Character`; `total()` trả `30L` nên có `Long`.
3. `touch()` vẫn chạy nội dung và in `touch body`. Sau khi hoàn tất, kết quả `Method.invoke` là `null` bởi phương thức khai báo `void`. `getReturnType()` của method vẫn là `void.class`.
4. `missing()` và `nullable()` khai báo kiểu **tham chiếu** nên có thể trả `null` từ logic của chính chúng. Kết quả của `invoke` cũng bằng `null`, nhưng **không đồng nghĩa** hai method này là `void`.
5. `boxed()` trả kiểu khai báo `Integer` với giá trị `17`. `invoke` trả chính tham chiếu kết quả, không thực hiện một bước boxing `int` bổ sung do Reflection: phần `return 17` đã được Java boxing theo ngữ nghĩa của method.
6. `rate()` là `static`, nên `invoke(null)` dùng receiver `null` hợp lệ. Nó trả primitive `double`, và Reflection biểu diễn bằng `Double`. **Receiver `null`** khác hẳn **return `null`**.
7. `(Integer) count.invoke(service)` ép kiểu object về `Integer` rồi tự unbox khi gán cho `int`. Việc unbox một tham chiếu `null` của `nullable()` gây `NullPointerException`.
8. `fail()` ném `IllegalStateException` bên trong phương thức thực. Reflection **không trả về `null`**; `invoke` ném `InvocationTargetException`, và `getCause()` chính là `IllegalStateException`.

Chỉ có **một file public class** (`MethodReturnDemo.java`); nested class `Service` giúp chương trình chạy độc lập, không phụ thuộc thư viện bên ngoài.

## 4. Kiểm tra kiểu trả về bằng `getReturnType()`

`Method.getReturnType()` trả một đối tượng `Class<?>` biểu diễn **kiểu trả về khai báo**. Nó không gọi method, không đọc giá trị thực tế và không boxing loại khai báo thành wrapper.

| Khai báo | `method.getReturnType()` | `getReturnType().getName()` |
|---|---|---|
| `int read()` | `int.class` | `int` |
| `boolean ok()` | `boolean.class` | `boolean` |
| `void reset()` | `void.class` | `void` |
| `Integer readBoxed()` | `Integer.class` | `java.lang.Integer` |
| `String name()` | `String.class` | `java.lang.String` |
| `int[] values()` | `int[].class` | JVM binary name `[I` |

Nếu một method trả **mảng primitive**, chẳng hạn `int[]`, bản thân mảng là **reference type**. `Method.invoke` trả tham chiếu tới **mảng**, không boxing từng phần tử `int` thành `Integer`. Bạn có thể dùng `getReturnType().isArray()` và `getReturnType().getComponentType()` để kiểm tra loại mảng.

Một cách phân loại kết quả trong code generic:

```java
// Đây là đoạn minh họa nằm trong một hàm đã có biến:
// Method method, Object receiver, Object[] arguments.
Class<?> declaredType = method.getReturnType();
Object result = method.invoke(receiver, arguments);

if (declaredType == void.class) {
    System.out.println("Method has no return value");
} else if (declaredType.isPrimitive()) {
    System.out.println("A primitive was boxed: " + result.getClass().getName());
} else if (result == null) {
    System.out.println("Reference return type, actual value is null");
} else {
    System.out.println("Reference result: " + result.getClass().getName());
}
```

**Lý do kiểm tra `void.class` trước:** `void` có cách xử lý kết quả đặc biệt. Không được truy cập `result.getClass()` khi method trả `void` vì `result == null`. Đoạn code giả định invocation hoàn tất bình thường và các exception đã được xử lý ở tầng gọi thích hợp.

### `getGenericReturnType()` khác gì?

`getReturnType()` trả kiểu runtime sau *type erasure*, dưới dạng `Class<?>`. `getGenericReturnType()` trả `java.lang.reflect.Type`, có thể giữ thông tin `List<String>`, `T` hoặc các kiểu generic khác trong chữ ký metadata.

Ví dụ `List<String> names()` có `getReturnType() == List.class`; `getGenericReturnType()` có thể mô tả `List<String>`. Dù vậy, **một `List<String>` là kiểu tham chiếu**, không nằm trong trường hợp boxing primitive. Với `void` và kiểu primitive thuần, logic của `Method.invoke` vẫn như đã giải thích.

## 5. Unboxing kết quả Reflection đúng cách

Vì `Method.invoke` trả `Object`, không thể gán trực tiếp nó cho biến `int` mà không chuyển đổi kiểu tương ứng:

```java
// Giả sử m là Method cho public int count() và receiver hợp lệ.
Object raw = m.invoke(receiver);
Integer boxed = (Integer) raw;
int count = boxed;
```

- `(Integer) raw` là ép kiểu tham chiếu từ `Object` về wrapper thực tế.
- `int count = boxed` dùng **unboxing** do Java thực hiện.
- Nếu `raw` là `null`, phép unboxing sẽ gây `NullPointerException`.
- Nếu `raw` là wrapper không tương thích (ví dụ `Long` nhưng ép `Integer`), phép cast sẽ gây `ClassCastException`.

Khi method thực sự khai báo `int` và hoàn tất bình thường, kết quả `Method.invoke` là `Integer` **không null**. Tuy nhiên, code Reflection tổng quát thường không biết trước phương thức được truyền vào; do đó không nên ép tất cả kết quả sang `Integer`.

Một `Number` có thể được dùng để xử lý nhiều wrapper số (`Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`), nhưng các phương thức `intValue()`, `longValue()`... có thể **mất độ chính xác** khi thu hẹp số hoặc chuyển số thực sang số nguyên. Không áp dụng `Number` cho `Boolean` và `Character`. Nếu hợp đồng method yêu cầu đúng kiểu, kiểm tra `getReturnType()` trước khi chuyển đổi, không âm thầm biến mọi số thành cùng một kiểu.

## 6. Phân biệt ba loại `null` thường gặp

Từ `null` có thể xuất hiện ở **receiver**, **đối số đầu vào** và **kết quả trả về**:

| Vị trí | Ví dụ | Ý nghĩa |
|---|---|---|
| Receiver trong `invoke` | `staticMethod.invoke(null)` | Hợp lệ: static method không cần một instance |
| Receiver trong `invoke` | `instanceMethod.invoke(null)` | Sai: instance method cần object hợp lệ; có thể ném `NullPointerException` |
| Argument trong `invoke` | `method.invoke(obj, (Object) null)` | Truyền **một đối số null** vào method có một tham số tham chiếu tương thích; không đồng nghĩa method trả null |
| Giá trị kết quả | `Object result = voidMethod.invoke(obj)` | `null` là kết quả chuẩn khi phương thức gốc có kiểu `void` và thực thi bình thường |
| Giá trị kết quả | `Object result = stringMethod.invoke(obj)` | Có thể `null` vì method kiểu tham chiếu thực sự trả `null` |

Đặc biệt, `Method.invoke` là một **varargs method** có kiểu tham số `Object... args`. Nếu cần truyền **đúng một đối số `null`** cho phương thức có một tham số tham chiếu, cách viết rõ ràng là:

```java
method.invoke(receiver, (Object) null);
```

Nếu method khai báo **không tham số**, gọi:

```java
method.invoke(receiver);
```

Đối với nhiều tham số, truyền các arguments theo thứ tự. Đừng tùy ý truyền `null` vào primitive parameter: lời gọi cần unboxing giá trị đầu vào nhưng `null` không có giá trị primitive tương ứng, nên Reflective invocation không thể hoàn tất như một lời gọi hợp lệ.

Ví dụ `method.invoke(receiver, (Object) null)` chỉ liên quan đến **input**. Kiểu trả về method vẫn quyết định việc kết quả `invoke` được boxing hay `null` khi hoàn tất bình thường.

## 7. Khi phương thức ném exception thì có trả `null` không?

**Không.** Nếu code thực thi trong method ném exception, lời gọi `Method.invoke` thường ném `InvocationTargetException` bọc exception gốc:

```java
try {
    Object result = method.invoke(receiver);
    System.out.println("Completed with result: " + result);
} catch (java.lang.reflect.InvocationTargetException ex) {
    Throwable original = ex.getCause();
    System.err.println("Method failed: " + original.getClass().getName());
}
```

Đây là **đoạn minh họa**, biến `method` và `receiver` có từ môi trường gọi. Khi method trả `void` **và chạy thành công**, biến `result` nhận `null`. Khi method `void` **ném exception**, lệnh gán `result` không hoàn tất bình thường; không có kết quả `null` để kiểm tra.

Cũng cần tách exception xảy ra **trước khi method được gọi**:

- `NoSuchMethodException`: không tìm thấy method tại `Class.getMethod`/`getDeclaredMethod`.
- `IllegalAccessException`: Reflection không được phép gọi member theo access rules.
- `IllegalArgumentException`: sai kiểu/số lượng đối số, receiver sai kiểu hoặc các điều kiện invocation không hợp lệ.
- `NullPointerException`: receiver là `null` cho instance method hoặc tình huống lỗi null ở caller; với method bên trong tự ném `NullPointerException`, lỗi ấy thường là **cause của `InvocationTargetException`**.
- `ExceptionInInitializerError` và các lỗi khởi tạo lớp có thể xuất hiện khi thực sự dùng một static method mà class chưa khởi tạo thành công.

Không nên dùng `result == null` để kết luận lời gọi thất bại: đó có thể là kết quả **bình thường** của `void` hoặc của method tham chiếu.

## 8. Ứng dụng trong công cụ gọi method động

Một bộ gọi API/plugin hoặc framework có thể không biết trước return type của các method mà nó xử lý. Để biểu diễn chính xác, nên giữ **cả metadata và giá trị**:

```java
// Đoạn minh họa; method/receiver/arguments được cung cấp từ caller.
Class<?> returnType = method.getReturnType();
Object value = method.invoke(receiver, arguments);

if (returnType == void.class) {
    // Thành công nhưng không có giá trị trả về theo chữ ký.
} else if (value == null) {
    // Phương thức kiểu tham chiếu đã trả về null.
} else {
    // Có đối tượng kết quả: wrapper cho primitive,
    // hoặc object tham chiếu trả về từ phương thức.
}
```

Trong một API kết quả tổng quát, có thể biểu diễn “không có giá trị trả về theo chữ ký” bằng một trạng thái riêng, và “có kiểu trả về tham chiếu nhưng giá trị null” bằng trạng thái khác. Không nên đưa cả hai trường hợp vào cùng nhãn `null` nếu người dùng API cần phân biệt.

Nếu hệ thống serialization nhận giá trị từ `invoke`:

- Với primitive return, wrapper `Integer`/`Boolean`/... có thể được serializer xử lý như một giá trị bình thường.
- Với `void`, không có payload theo chữ ký; ứng dụng có thể biểu diễn thành công bằng response không có body, status hoặc thông tin tác vụ riêng.
- Với reference return `null`, một hợp đồng API có thể cho phép payload nullable, thiếu field hoặc thông điệp lỗi tùy ý nghĩa nghiệp vụ. Reflection **không** tự quyết định ngữ nghĩa này.

**Lưu ý hiệu năng:** boxing/unboxing và chi phí reflective dispatch có thể đáng quan tâm trong vòng lặp rất nóng. Trước hết hãy đo thực tế và thiết kế theo nhu cầu; đừng diễn giải việc thấy `Integer` ở kết quả `invoke` là bằng chứng luôn có object mới được cấp phát ở mỗi lời gọi.

## 9. Lỗi tư duy phổ biến

1. **“Phương thức trả `int` thì `invoke` cũng trả `int`.”** Sai: API `invoke` trả `Object`, primitive được boxing thành wrapper.
2. **“`void` được boxing thành `Void`.”** Sai: `void` không có giá trị và `invoke` trả **`null`**, không tạo instance `Void`.
3. **“Kết quả `invoke` là `null` thì method phải là `void`.”** Sai: một method có return type tham chiếu cũng có thể thực sự trả `null`.
4. **“Method kiểu primitive có thể trả `null` khi giá trị bằng 0.”** Sai: `0`, `false` và các giá trị primitive khác vẫn được boxing bình thường.
5. **“`getReturnType()` trả `Integer.class` nếu method khai báo `int`.”** Sai: `getReturnType()` là `int.class`, còn đối tượng kết quả `invoke` là `Integer`.
6. **“`Void.class` và `void.class` giống nhau.”** Sai: `Void` là reference type; `void` là từ khóa biểu diễn không có return value.
7. **“`touch()` là `void` nên không chạy code khi Reflection gọi nó.”** Sai: code vẫn chạy và có thể gây side effect; chỉ không có giá trị trả về.
8. **“`null` từ method trả `Integer` unbox thành 0.”** Sai: unboxing một tham chiếu `null` ném `NullPointerException`.
9. **“Method ném exception thì `invoke` trả `null`.”** Sai: invocation không hoàn tất bình thường; thường nhận `InvocationTargetException`.
10. **“Receiver `null` nghĩa là method trả `null`.”** Sai: receiver `null` hợp lệ với static method và hoàn toàn độc lập với return value.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Method khai báo `public double price() { return 1.5; }`. `Method.invoke(obj)` trả object kiểu gì?

**Đáp án:** `Double` chứa `1.5`, dưới dạng `Object`. `getReturnType()` vẫn là `double.class`.

**Câu 2.** `public void save() { System.out.println("saved"); }` được gọi qua `invoke`. Có chạy lệnh in không, và `invoke` trả gì?

**Đáp án:** Có, method thực sự chạy và in `saved`. Nếu hoàn tất bình thường, `invoke` trả `null`.

**Câu 3.** `public String lookup() { return null; }` và `public void clear() { }` đều khiến `invoke` trả `null`. Làm sao biết trường hợp nào không có return value theo chữ ký?

**Đáp án:** Dùng `method.getReturnType() == void.class`. Với `lookup`, return type là `String.class` và giá trị thực tế bằng `null`; với `clear`, return type là `void.class`.

**Câu 4.** `getReturnType()` của phương thức khai báo `Integer count()` là gì, và `invoke` có chắc khác `null` không?

**Đáp án:** `Integer.class`. Không chắc: `Integer` là reference type nên method có thể trả `null`.

**Câu 5.** Khi gọi `public int compute() { throw new IllegalStateException(); }` bằng Reflection, kết quả có phải là một `Integer` chứa giá trị mặc định không?

**Đáp án:** Không. Vì method ném exception, lời gọi thất bại; `Method.invoke` ném `InvocationTargetException` với cause là `IllegalStateException`. Không có giá trị trả về bình thường để boxing.

**Câu 6.** Tại sao không gọi `result.getClass()` ngay sau mọi `invoke`?

**Đáp án:** Vì `result` có thể bằng `null` cho method `void` hoặc method trả kiểu tham chiếu với giá trị null. Khi đó `result.getClass()` gây `NullPointerException`; cần kiểm tra `result == null` và `getReturnType()` trước.

## Tài liệu Java chuẩn

- Java SE API — `java.lang.reflect.Method.invoke(Object, Object...)`: cách gọi method, boxing primitive return, kết quả `null` cho `void`, và `InvocationTargetException`.
- Java SE API — `java.lang.reflect.Method.getReturnType()`, `getGenericReturnType()`: metadata của kiểu trả về.
- Java Language Specification — §5.1.7 *Boxing Conversion*, §5.1.8 *Unboxing Conversion*, §8.4.5 *Method Result*, §14.17 *The return Statement*.
- Java SE API — `java.lang.Void`: lớp tham chiếu biểu diễn kiểu `void` trong một số API dùng `Class` hoặc generic.

**Ghi nhớ:** `Method.invoke` luôn có kiểu trả về **`Object`**. Primitive return được **boxing thành wrapper**; method `void` chạy bình thường thì **`invoke` trả `null`**. Method trả tham chiếu cũng có thể trả `null`; hãy dùng **`getReturnType()`** để phân biệt hai trường hợp, và xử lý exception riêng với kết quả trả về.