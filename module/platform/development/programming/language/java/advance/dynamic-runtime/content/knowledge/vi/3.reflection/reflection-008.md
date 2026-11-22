# 3.8 Xử lý varargs và phân biệt một đối số mảng với nhiều đối số phản chiếu

Khi gọi một phương thức bằng Reflection, `Method.invoke` nhận **một danh sách đối số của phương thức đích**, được truyền dưới dạng `Object[]`. Nếu phương thức đích lại nhận mảng hoặc khai báo varargs (`String...`, `int...`, `Object...`), ta phải phân biệt rõ hai cấp độ mảng. Nhầm lẫn thường gây `IllegalArgumentException: wrong number of arguments` dù tên phương thức và kiểu dữ liệu tưởng như chính xác.

Đây là lỗi hay gặp ở trình nạp plugin, bộ điều phối lệnh, công cụ gọi API bằng tên, framework kiểm thử và cơ chế tạo đối tượng động. Mục tiêu của bài là hiểu cách Java đóng gói varargs ở **vị trí gọi**, cách `Method.invoke` và `Constructor.newInstance` nhận tham số, cách truyền **một đối số kiểu mảng** mà không vô tình trải các phần tử thành **nhiều đối số phản chiếu**, cùng cách xây adapter an toàn khi số lượng đối số được biết lúc chạy.

## 1. Hai tầng varargs khác nhau

Giả sử phương thức đích được khai báo:

```java
public static void show(String... items) {
    System.out.println(java.util.Arrays.toString(items));
}
```

Đây là đoạn khai báo minh họa, không phải chương trình độc lập. Ở mức ngôn ngữ, hai lời gọi trực tiếp sau đều hợp lệ:

```java
show("A", "B");                     // Compiler tạo String[] chứa "A", "B".
show(new String[] {"A", "B"});      // Truyền nguyên String[] đã tạo.
```

Một tham số khai báo `String...` được biểu diễn thành **một tham số `String[]`** trong method descriptor và trong Reflection:

- `getParameterCount()` trả về `1`, không phụ thuộc số phần tử được truyền ở những lần gọi khác nhau.
- `getParameterTypes()[0] == String[].class`.
- `isVarArgs() == true` khi khai báo là `String...`; với phương thức khai báo `String[]` thông thường, `isVarArgs() == false`.
- Để tìm đúng phương thức: `SomeClass.class.getMethod("show", String[].class)`. Không tìm bằng `getMethod("show", String.class, String.class)`.
- Ở class file, descriptor của `void show(String... items)` là `([Ljava/lang/String;)V`; cùng descriptor với `void show(String[] items)`. Hai khai báo này **không thể cùng tên để overload trong một lớp** chỉ bằng cách đổi `[]` thành `...`.

Bây giờ xét chữ ký **API phản chiếu**:

```java
Object Method.invoke(Object receiver, Object... args)
```

`receiver` là đối tượng nhận lời gọi (dùng `null` cho phương thức `static`); `args` là **mảng chứa từng đối số thực tế** của phương thức đích. Chính `Method.invoke` cũng là một phương thức varargs, nhưng cấp này **khác** cấp `String...` trong `show`:

```text
Method.invoke(receiver, Object... args)
                        |
                        +-- Object[]: DANH SÁCH đối số của lời gọi phản chiếu
                             |
                             +-- args[0] = String[]: MỘT đối số mảng của show(...)
```

Nếu Reflection đã chọn `show(String[])`, danh sách đối số gửi xuống cần có **đúng một phần tử**, và phần tử đó phải là `String[]` (hoặc `null`). `Method.invoke` **không tự chuyển hai `String` riêng lẻ thành một `String[]`** chỉ vì `show.isVarArgs()` là `true`.

## 2. Một mảng hay nhiều đối số: các lời gọi dễ nhầm

Có `Method method` trỏ đến `show(String...)` và `String[] words = {"A", "B"};`. Bảng sau mô tả **mảng `args` mà `Method.invoke` thực sự nhận**:

| Lời gọi | Danh sách `args` mà Reflection nhận | Đối với `show(String...)` |
| --- | --- | --- |
| `method.invoke(null, (Object) words)` | `Object[]{words}`: **một `String[]`** | Đúng, in `[A, B]` |
| `method.invoke(null, new Object[]{words})` | Một phần tử, chính là `words` | Đúng, in `[A, B]` |
| `method.invoke(null, (Object[]) words)` | Hai phần tử `"A"`, `"B"` | Sai số lượng: cần một `String[]` |
| `method.invoke(null, words)` | Với `words` kiểu `String[]`, compiler chọn lời gọi nhận `Object[]` | Cũng truyền hai phần tử; có thể cảnh báo biên dịch |
| `method.invoke(null, "A", "B")` | Hai đối số `String` | Sai số lượng, **không tự pack** |
| `method.invoke(null)` | Mảng đối số rỗng (0 phần tử) | Sai số lượng, không tương đương mảng `String[0]` |
| `method.invoke(null, (Object) new String[0])` | Một đối số `String[]` rỗng | Đúng, in `[]` |
| `method.invoke(null, (Object) null)` | Một đối số `null` | Đúng về số lượng; chính `show` quyết định cách xử lý `null` |
| `method.invoke(null, (Object[]) null)` | Mảng danh sách đối số `null`, được xem như 0 đối số | Sai số lượng |

**Tại sao cast sang `Object` lại giải quyết được?** `String[]` là một subtype của `Object[]`; nếu biến `words` được truyền làm tham số thứ hai của `invoke` ở dạng `String[]` hay `Object[]`, compiler có thể chọn lời gọi **fixed arity**, dùng chính mảng đó làm danh sách `args`. Cast `(Object) words` ngăn cách hiểu ấy; compiler phải đóng gói `words` thành **một phần tử** của mảng varargs `Object[]` mới.

Cách khác, viết danh sách tường minh `new Object[]{words}`. Lúc này `Object[]` **ở ngoài** là danh sách đối số, và `String[]` **ở trong** là giá trị của đối số thứ nhất. Hai cách đều đúng, nhưng cần chọn theo điều kiện chương trình:

- Khi bạn đã có **một mảng muốn chuyển làm một đối số**, dùng `(Object) array` hoặc `new Object[]{array}`.
- Khi bạn có **danh sách các đối số đích**, chẳng hạn `Object[] actualArgs`, dùng `method.invoke(receiver, actualArgs)`; từng phần tử `actualArgs[i]` được ghép vào từng tham số của đích.
- Khi phương thức đích nhận **hai `String` riêng biệt**, truyền `method.invoke(receiver, "A", "B")` hoặc `method.invoke(receiver, new Object[]{"A", "B"})` là hợp lý. Lỗi chỉ xuất hiện nếu chữ ký đích đòi **một `String[]`**.

Không có một quy tắc chung kiểu “luôn cast mọi mảng sang `Object`”: làm vậy khi đích thực sự cần nhiều tham số sẽ khiến Reflection thấy **một** đối số mảng và báo sai số lượng.

## 3. Ví dụ Java 17+ đầy đủ: chạy thành công và thấy lỗi có kiểm soát

Tạo tệp `VarargsReflectionDemo.java` sau. Các phương thức đều là `public static` để tập trung vào hình dạng đối số; `null` ở vị trí đầu của `invoke` đại diện cho receiver của phương thức static.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;

public class VarargsReflectionDemo {
    public static class Target {
        public static void array(String[] values) {
            System.out.println("array=" + Arrays.toString(values));
        }

        public static void varargs(String... values) {
            System.out.println("varargs=" + Arrays.toString(values));
        }

        public static void pair(String first, String second) {
            System.out.println("pair=" + first + "+" + second);
        }

        public static void numbers(int... values) {
            System.out.println("numbers=" + Arrays.toString(values));
        }

        public static void objects(Object... values) {
            System.out.println("objects=" + Arrays.deepToString(values));
        }

        public static void fails(String... values) {
            throw new IllegalStateException("from target");
        }
    }

    public static class Box {
        private final String[] values;

        public Box(String... values) {
            this.values = values;
        }

        @Override public String toString() {
            return "Box=" + Arrays.toString(values);
        }
    }

    public static void main(String[] args) throws Exception {
        Method array = Target.class.getMethod("array", String[].class);
        Method varargs = Target.class.getMethod("varargs", String[].class);
        Method pair = Target.class.getMethod(
                "pair", String.class, String.class);
        Method numbers = Target.class.getMethod("numbers", int[].class);
        Method objects = Target.class.getMethod("objects", Object[].class);
        String[] words = {"A", "B"};

        System.out.println("array.isVarArgs=" + array.isVarArgs());
        System.out.println("varargs.isVarArgs=" + varargs.isVarArgs());
        System.out.println("varargs.parameters=" + varargs.getParameterCount());
        System.out.println("varargs.parameter0="
                + varargs.getParameterTypes()[0].getTypeName());

        array.invoke(null, (Object) words);         // Một String[].
        varargs.invoke(null, (Object) words);       // Một String[].
        array.invoke(null, new Object[] {words});   // Cũng một String[].
        pair.invoke(null, (Object[]) words);        // Hai String.

        try {
            array.invoke(null, (Object[]) words);
        } catch (IllegalArgumentException e) {
            System.out.println("array expanded="
                    + e.getClass().getSimpleName());
        }
        try {
            varargs.invoke(null, "A", "B");
        } catch (IllegalArgumentException e) {
            System.out.println("varargs expanded="
                    + e.getClass().getSimpleName());
        }

        Object[] mixed = {"A", "B"};
        objects.invoke(null, (Object) mixed);
        try {
            objects.invoke(null, mixed);
        } catch (IllegalArgumentException e) {
            System.out.println("objects expanded="
                    + e.getClass().getSimpleName());
        }

        numbers.invoke(null, new int[] {1, 2});
        varargs.invoke(null, (Object) new String[0]);
        varargs.invoke(null, (Object) null);
        try {
            varargs.invoke(null);
        } catch (IllegalArgumentException e) {
            System.out.println("varargs no args="
                    + e.getClass().getSimpleName());
        }
        try {
            varargs.invoke(null, (Object[]) null);
        } catch (IllegalArgumentException e) {
            System.out.println("varargs null arg list="
                    + e.getClass().getSimpleName());
        }

        Constructor<Box> ctor = Box.class.getConstructor(String[].class);
        System.out.println("constructor.isVarArgs=" + ctor.isVarArgs());
        System.out.println(ctor.newInstance((Object) words));
        try {
            ctor.newInstance("A", "B");
        } catch (IllegalArgumentException e) {
            System.out.println("constructor expanded="
                    + e.getClass().getSimpleName());
        }

        Method fails = Target.class.getMethod("fails", String[].class);
        try {
            fails.invoke(null, (Object) words);
        } catch (InvocationTargetException e) {
            System.out.println("underlying exception="
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy với JDK 17 trở lên:

```bash
javac --release 17 VarargsReflectionDemo.java
java VarargsReflectionDemo
```

`stdout`:

```text
array.isVarArgs=false
varargs.isVarArgs=true
varargs.parameters=1
varargs.parameter0=java.lang.String[]
array=[A, B]
varargs=[A, B]
array=[A, B]
pair=A+B
array expanded=IllegalArgumentException
varargs expanded=IllegalArgumentException
objects=[A, B]
objects expanded=IllegalArgumentException
numbers=[1, 2]
varargs=[]
varargs=null
varargs no args=IllegalArgumentException
varargs null arg list=IllegalArgumentException
constructor.isVarArgs=true
Box=[A, B]
constructor expanded=IllegalArgumentException
underlying exception=IllegalStateException
```

**Đọc kết quả đúng bản chất:**

1. `array` và `varargs` đều nhận một `String[]` ở mức Reflection. Chúng khác nhau ở **cờ varargs** (`false` so với `true`), không khác số tham số.
2. `pair.invoke(null, (Object[]) words)` thành công vì `pair` thực sự cần **hai `String`**, đúng bằng hai phần tử được trải ra từ `words`.
3. `array.invoke(null, (Object[]) words)` và `varargs.invoke(null, "A", "B")` thất bại **trước khi vào body đích** vì danh sách Reflection có hai đối số trong khi chữ ký đích chỉ có một.
4. `objects` nhận `Object...`: khi `mixed` được cast thành `Object`, nó được giữ là **một `Object[]`**, còn truyền trần `mixed` khiến nó trở thành danh sách hai đối số.
5. `numbers.invoke(null, new int[]{1, 2})` hoạt động: `int[]` là `Object` nhưng **không phải `Object[]`**; compiler đóng gói nó thành một đối số. Với `String[]`, vì nó **là `Object[]`**, cần xác định rõ ý định.
6. Mảng `String[0]` là **một đối số mảng rỗng**; không giống **danh sách đối số Reflection rỗng**. `null` cũng có hai tầng ý nghĩa tùy cast.
7. `Constructor.newInstance` gặp tình huống tương tự. `InvocationTargetException` bao lỗi phát sinh **bên trong phương thức đích**, không phải lỗi đóng gói đối số.

Bạn có thể kiểm tra thêm descriptor của hai phương thức đầu bằng:

```bash
javap -s -p 'VarargsReflectionDemo$Target'
```

Cả `array(String[])` và `varargs(String...)` đều có descriptor `([Ljava/lang/String;)V`. Dấu `...` là cú pháp nguồn/cờ metadata, không làm thay đổi kiểu mảng của tham số cuối.

## 4. Các biên khó: null, mảng rỗng, Object[], mảng nhiều chiều

### 4.1. `null` của danh sách đối số khác `null` làm giá trị đối số

| Lời gọi của `Method.invoke` | Số đối số đích | Ý nghĩa |
| --- | --- | --- |
| `invoke(receiver)` | 0 | Không truyền giá trị nào |
| `invoke(receiver, new Object[0])` | 0 | Danh sách đối số rỗng |
| `invoke(receiver, (Object[]) null)` | 0 | Danh sách đối số Reflection là `null`; hợp lệ cho đích không có tham số |
| `invoke(receiver, (Object) null)` | 1 | Có **một** giá trị `null` làm tham số |
| `invoke(receiver, new Object[]{null})` | 1 | Có **một** phần tử `null` trong danh sách |
| `invoke(receiver, (Object) new String[0])` | 1 | Có **một** `String[]` rỗng |

Tránh `invoke(receiver, null)` vì kiểu `null` không biểu lộ mục đích rõ ràng, trình biên dịch có thể cảnh báo “non-varargs call ... with inexact argument type”. Hãy viết tường minh `(Object) null` hay `(Object[]) null` để chọn số đối số.

Đối với `show(String... items)`, hai tình huống **hoàn toàn khác nhau**:

- Truyền `(Object) new String[0]` → code đích nhận mảng dài 0.
- Truyền `(Object) null` → code đích nhận **biến mảng bằng `null`**; truy cập `items.length` sẽ ném `NullPointerException` ở **bên trong phương thức đích** và bị Reflection gói trong `InvocationTargetException`. Ví dụ của `VarargsReflectionDemo` dùng `Arrays.toString` để an toàn khi in null.

### 4.2. `Object[]` là kiểu dễ nhầm nhất

Giả sử đích là `static void consume(Object[] xs)`. Lời gọi `m.invoke(null, new Object[]{"A", "B"})` đưa **hai** phần tử `"A"` và `"B"` vào danh sách Reflection; nó không có nghĩa là truyền nguyên mảng `Object[]{"A", "B"}` làm **một** đối số. Cách đúng:

```java
Object[] data = {"A", "B"};
m.invoke(null, (Object) data);
// Hoặc:
m.invoke(null, new Object[] {data});
```

Đây là đoạn minh họa với `m` đã tra cứu cho `consume(Object[])`. Ngược lại, nếu đích thực sự là `static void consumeTwo(Object a, Object b)`, chính `m.invoke(null, data)` lại là cách truyền hai đối số.

Với mảng hai chiều như `String[][] matrix`, hãy tiếp tục dùng `(Object) matrix` nếu tham số đích là **một `String[][]`**. Mảng hai chiều chứa các mảng con và vẫn là subtype của `Object[]`, nên gọi trần `invoke(receiver, matrix)` có thể bị hiểu thành **nhiều đối số là các hàng của ma trận**.

### 4.3. Mảng nguyên thủy và kiểu phần tử

`int[]`, `double[]`, `boolean[]` không phải subtype của `Object[]`. Với `void read(int[] nums)`, `m.invoke(receiver, new int[]{1, 2})` thường tạo một phần tử trong danh sách Reflection và tương thích đích. Dẫu vậy, khi viết framework, tạo danh sách tường minh `new Object[]{numbers}` để nhất quán, tránh phụ thuộc vào sự khác biệt giữa mảng primitive và mảng tham chiếu.

**Không thay thế `String[]` bằng `Object[]` một cách tùy tiện.** `String[]` được gán được cho `Object[]`, nhưng `Object[]` không tự động chuyển thành `String[]`. Nếu tham số đích là `String[]`, một `Object[]` chứa toàn các `String` vẫn không phải `String[]`. Lỗi tương ứng có thể là `IllegalArgumentException: argument type mismatch` dù số đối số bằng một.

### 4.4. Phản chiếu không tự chọn overload từ giá trị được truyền

`Class.getMethod("send", String[].class)` và `Class.getMethod("send", String.class, String.class)` là **hai cách tra chữ ký khác nhau**. Khi đã có đối tượng `Method`, `invoke` sử dụng phương thức được mô tả bởi đối tượng đó; nó không tự tìm một overload khác cho khớp số đối số.

Ngoài ra, `getMethod` và `getDeclaredMethod` tự có tham số `Class<?>... parameterTypes`: hãy truyền các **kiểu khai báo** thật (`String[].class` cho `String...`), không truyền kiểu của từng phần tử varargs như thể đó là các tham số phương thức riêng.

## 5. Adapter gọi động: phân biệt chế độ EXACT và SPREAD

Khi viết framework nhận một danh sách giá trị tại thời điểm chạy, hãy công khai **hai hợp đồng riêng**:

- **EXACT**: danh sách đã chứa chính xác từng đối số của chữ ký runtime. Nếu tham số cuối là mảng, phần tử cuối của danh sách phải là một mảng đúng kiểu (hoặc `null`).
- **SPREAD**: người gọi cung cấp các tham số cố định trước, rồi nhiều **giá trị phần tử** cho tham số varargs; adapter có trách nhiệm đóng gói phần đuôi thành mảng đúng `componentType` trước khi gọi `Method.invoke`.

Không nên **tự đoán** chế độ dựa trên việc phần tử cuối có phải mảng hay không: một mảng đơn lẻ có thể được người dùng muốn truyền làm *một giá trị*, hoặc là một danh sách cần trải; trường hợp `null` lại càng khó suy đoán. Chế độ phải do hợp đồng API quyết định.

Tạo tệp thứ hai `VarargsAdapterDemo.java`:

```java
import java.lang.reflect.Array;
import java.lang.reflect.Method;
import java.util.Arrays;

public class VarargsAdapterDemo {
    public static String summarize(String prefix, int... numbers) {
        return prefix + Arrays.toString(numbers);
    }

    static Object invokeExact(Method method, Object receiver, Object[] args)
            throws ReflectiveOperationException {
        return method.invoke(receiver, args);
    }

    static Object invokeSpread(Method method, Object receiver, Object[] supplied)
            throws ReflectiveOperationException {
        if (!method.isVarArgs()) {
            throw new IllegalArgumentException("Target is not varargs");
        }
        Class<?>[] types = method.getParameterTypes();
        int fixed = types.length - 1;
        if (supplied.length < fixed) {
            throw new IllegalArgumentException("Missing fixed arguments");
        }

        Object[] packed = new Object[types.length];
        System.arraycopy(supplied, 0, packed, 0, fixed);
        Class<?> component = types[fixed].getComponentType();
        Object tail = Array.newInstance(component, supplied.length - fixed);
        for (int i = fixed; i < supplied.length; i++) {
            Array.set(tail, i - fixed, supplied[i]);
        }
        packed[fixed] = tail;
        return method.invoke(receiver, packed);
    }

    public static void main(String[] args) throws Exception {
        Method method = VarargsAdapterDemo.class.getMethod(
                "summarize", String.class, int[].class);

        System.out.println(invokeSpread(method, null,
                new Object[] {"n=", 1, 2, 3}));
        System.out.println(invokeSpread(method, null,
                new Object[] {"empty="}));
        System.out.println(invokeExact(method, null,
                new Object[] {"array=", new int[] {5, 8}}));
    }
}
```

```bash
javac --release 17 VarargsAdapterDemo.java
java VarargsAdapterDemo
```

`stdout`:

```text
n=[1, 2, 3]
empty=[]
array=[5, 8]
```

**Cơ chế của adapter:**

1. Với `summarize(String, int...)`, `getParameterTypes()` trả về `[String.class, int[].class]`, số tham số cố định là `1`.
2. Ở SPREAD, tạo `Object[2]` cho danh sách đối số cuối cùng. Phần tử thứ nhất là `prefix`, phần tử thứ hai là một `int[]` tạo bằng `Array.newInstance(int.class, size)`.
3. `Array.set` có thể unbox các `Integer` và áp dụng các chuyển đổi nguyên thủy hợp lệ khi đặt vào mảng `int[]`. Giá trị không phù hợp gây lỗi; đây là tín hiệu cần xử lý đầu vào.
4. Khi phần varargs được cung cấp 0 phần tử, vẫn phải tạo `int[0]`. Không bỏ tham số mảng cuối.
5. `method.invoke(receiver, packed)` có `packed` kiểu `Object[]`, nên mỗi phần tử của `packed` tương ứng một tham số thực của đích; **không** cần cast toàn bộ `packed` thành `Object`.

**Giới hạn của ví dụ:** đây là adapter minh họa dành cho phương thức varargs đã tìm được trước đó. Nó không chọn overload, không tự phân tích chuỗi thành số, không xử lý bất kỳ quy tắc chuyển kiểu tùy biến nào và không đóng gói một mảng đã chuẩn bị sẵn trong chế độ SPREAD. Truyền `new Object[]{"n=", new int[]{5, 8}}` cho SPREAD sẽ cố đặt một `int[]` vào một vị trí phần tử `int` và thất bại; hãy chọn EXACT cho trường hợp đó. Muốn hỗ trợ null, ép kiểu, logging và overload trong framework thực tế thì thiết kế rõ chính sách riêng ở lớp biên.

## 6. Constructor, receiver và các API liên quan

### 6.1. `Constructor.newInstance(Object... initargs)`

Constructor cũng nhận một **danh sách `Object[]`**, giống tham số thứ hai của `Method.invoke` nhưng không có receiver. Nếu constructor khai báo `Box(String... values)`, Reflection thấy **một tham số `String[]`**, nên:

```java
Constructor<Box> constructor = Box.class.getConstructor(String[].class);
Box a = constructor.newInstance((Object) new String[]{"A", "B"});
Box b = constructor.newInstance(new Object[]{
        new String[]{"A", "B"}
});
```

Đoạn trên dựa vào lớp `Box` trong ví dụ `VarargsReflectionDemo.java`. Cả `a` và `b` hợp lệ. `constructor.newInstance("A", "B")` không tự gộp hai chuỗi thành `String[]` và sẽ ném `IllegalArgumentException` vì sai số lượng.

### 6.2. Phương thức instance và static

Với `Method.invoke`, **tham số đầu là receiver**, không phải đối số đầu của method đích:

```java
Method method = Account.class.getMethod("setTags", String[].class);
Account account = new Account();
method.invoke(account, (Object) new String[]{"vip", "trial"});
```

Đây là đoạn minh họa, giả định `Account` có constructor công khai và phương thức instance `setTags(String...)`. Nếu đích là `static`, receiver truyền `null`. Nếu đích là instance, truyền đúng đối tượng thuộc lớp khai báo hoặc subtype phù hợp. Lỗi receiver không thể giải quyết bằng cách đổi cast của mảng varargs.

### 6.3. Phân biệt lỗi đóng gói với lỗi bên trong đích

| Kết quả / exception | Nguồn thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `NoSuchMethodException` ở `getMethod` | Tra cứu sai tên hoặc sai danh sách **Class tham số** | Với `String...` dùng `String[].class`; kiểm tra kiểu primitive, overload, phạm vi public/declared |
| `IllegalArgumentException: wrong number of arguments` ở `invoke` | Số phần tử của `Object[] args` khác số tham số khai báo của Method | In `getParameterCount()`, `args.length`, kiểm tra một mảng bị trải thành nhiều đối số |
| `IllegalArgumentException: argument type mismatch` | Đúng số lượng nhưng kiểu của `args[i]` không tương thích kiểu tham số | So sánh `getParameterTypes()` với `args[i].getClass()`; xét mảng `String[]` khác `Object[]` |
| `IllegalAccessException` / `InaccessibleObjectException` | Vấn đề truy cập thành viên hoặc ràng buộc module | Kiểm tra visibility, module exports/opens; không tùy tiện vô hiệu hóa kiểm tra |
| `InvocationTargetException` | Code bên trong phương thức/constructor đã ném exception | Đọc `getCause()` để biết lỗi gốc; có thể là NPE nếu đích không chấp nhận mảng null |
| `NullPointerException` trước khi gọi thân đích | Ví dụ receiver null với method instance, hoặc logic adapter truy cập danh sách null | Xác định null nằm ở **receiver**, **danh sách args** hay **giá trị args[0]** |

`Method.invoke` có thể tự chuyển một số giá trị boxed sang tham số primitive bằng unboxing và widening hợp lệ, nhưng **không** biến `String` thành `String[]`, không tự tạo mảng varargs cho phương thức đích và không thực hiện narrowing không hợp lệ.

Trong ứng dụng thật, logger nên ghi đủ **Method đã chọn**, `isVarArgs()`, `getParameterTypes()`, số phần tử của danh sách đối số và **kiểu runtime của mỗi phần tử**; tuyệt đối tránh in dữ liệu nhạy cảm của tham số. Với tham số mảng, ghi cả kiểu `[Ljava.lang.String;` hay `[I` thường giúp nhận ra sai shape nhanh hơn việc chỉ in `toString()`.

## 7. Quy trình quyết định khi gọi Reflection

1. **Xem chữ ký runtime đích.** Dùng `Method.getParameterCount()` và `getParameterTypes()`; `isVarArgs()` chỉ cho biết khai báo có `...`. Nếu phương thức có hai tham số, nhận hai giá trị; nếu tham số cuối là mảng, phải chuẩn bị một mảng tương thích.
2. **Phân biệt danh sách đối số và giá trị mảng.** `Object[]{String[]}` biểu diễn một tham số mảng; `Object[]{"A", "B"}` biểu diễn hai tham số chuỗi.
3. **Quyết định EXACT hay SPREAD ở biên tích hợp.** EXACT giữ nguyên mảng đã cung cấp; SPREAD gom các phần tử cuối thành mảng đúng kiểu. Không suy đoán từ runtime type một cách mơ hồ.
4. **Xử lý 0 phần tử và null có chủ ý.** Mảng `new String[0]`, một đối số `null` và danh sách đối số rỗng là ba ý nghĩa khác nhau.
5. **Gọi `invoke` với danh sách `Object[]` đúng cấu trúc.** Ví dụ `method.invoke(receiver, new Object[]{stringArray})`, hoặc `method.invoke(receiver, preparedArgs)` khi `preparedArgs` đã chứa một phần tử cho mỗi tham số đích.
6. **Phân loại lỗi trước khi sửa.** Wrong number/type → sửa danh sách đối số; InvocationTargetException → xem lỗi bên trong; NoSuchMethodException → sửa lookup; IllegalAccessException → xem quyền truy cập.

### Ba bài tập tự kiểm tra

**Bài A.** Đích là `static void task(String[] lines)`. Có `String[] data = {"x", "y"};`. Viết lời gọi Reflection truyền cả mảng. **Đáp án:** `method.invoke(null, (Object) data)` hoặc `method.invoke(null, new Object[]{data})`. `method.invoke(null, (Object[]) data)` sẽ thành hai chuỗi và thất bại.

**Bài B.** Đích là `static void task(String first, String second)`, có cùng `data`. **Đáp án:** `method.invoke(null, (Object[]) data)` sẽ truyền hai chuỗi; `method.invoke(null, (Object) data)` lại là một đối số mảng không khớp chữ ký.

**Bài C.** Đích là `static void task(int... ids)`. Muốn gọi với **0** phần tử, làm sao? **Đáp án:** `method.invoke(null, (Object) new int[0])`. Gọi `method.invoke(null)` tạo 0 **đối số Reflection**, trong khi đích vẫn yêu cầu đúng 1 tham số `int[]`.

## Nguồn đối chiếu chuẩn

- JDK 17 `Method.invoke` — chữ ký `Object... args`, quy tắc kiểm tra số lượng/kiểu đối số và `InvocationTargetException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- JDK 17 `Constructor.newInstance` — các đối số khởi tạo và lỗi chuyển đổi: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html
- JDK 17 `Executable.isVarArgs`, `getParameterTypes` và `getParameterCount`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Executable.html
- Oracle Java Tutorial, *Invoking Methods with a Variable Number of Arguments*: https://docs.oracle.com/javase/tutorial/reflect/member/methodInvocation.html
- Oracle Java Tutorial, *IllegalArgumentException from Method.invoke()*: https://docs.oracle.com/javase/tutorial/reflect/member/methodTrouble.html
- Java Language Specification, Java SE 17, `15.12 (*Method Invocation Expressions*) và `8.4.1 (*Formal Parameters*): https://docs.oracle.com/javase/specs/jls/se17/html/

**Ghi nhớ:** `varargs` ở lời gọi `Method.invoke` là cơ chế đóng gói **danh sách đối số phản chiếu** (`Object[]`). `varargs` của phương thức đích là **một tham số mảng** ở runtime. Việc dùng cast `(Object) array` hoặc danh sách `new Object[]{array}` giúp truyền mảng thành **một đối số**; cast `(Object[]) array` đưa các phần tử mảng thành **nhiều đối số**. Chọn đúng cách dựa trên chữ ký đích.
