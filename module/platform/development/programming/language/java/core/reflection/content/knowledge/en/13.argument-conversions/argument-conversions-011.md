# Mảng primitive không thay thế mảng wrapper trong Java Reflection

## 1. Bản chất: boxing từng phần tử không biến đổi kiểu của cả mảng

Trong Java, các kiểu mảng `int[]` và `Integer[]` là **hai kiểu runtime khác nhau**:

- `int[]` lưu các phần tử **primitive `int`**, có giá trị mặc định `0`.
- `Integer[]` lưu **tham chiếu tới đối tượng `Integer`**, có thể chứa `null` và có giá trị mặc định `null`.
- Java hỗ trợ **boxing/unboxing từng giá trị** giữa `int` và `Integer`, nhưng **không tự động chuyển nguyên mảng** `int[]` thành `Integer[]` hoặc ngược lại.
- Vì khác kiểu mảng, chúng **không thể thay thế nhau** trong tham số, biến gán, kiểu trường dữ liệu hoặc chữ ký tra cứu Reflection.

```java
int value = 7;
Integer boxedValue = value; // Boxing phần tử: hợp lệ.
int unboxedValue = boxedValue; // Unboxing phần tử: hợp lệ.

int[] primitives = {1, 2, 3};
Integer[] wrappers = {1, 2, 3}; // Từng phần tử literal được boxing.

// MÃ MINH HỌA KHÔNG BIÊN DỊCH ĐƯỢC:
// Integer[] wrong1 = primitives;
// int[] wrong2 = wrappers;
```

Không có quy tắc Java nào cho phép `Integer[] wrappers = primitives` bằng một chuyển đổi boxing ngầm định ở cấp mảng. Kể cả ép kiểu thông qua `Object` cũng không thể biến đổi dữ liệu:

```java
// Ví dụ minh họa: câu lệnh này biên dịch nhưng thất bại lúc chạy.
// Integer[] invalid = (Integer[]) (Object) primitives;
// Runtime: ClassCastException.
```

Đặc biệt trong Reflection, việc tìm đúng tên phương thức nhưng truyền **kiểu mảng sai** thường dẫn tới `NoSuchMethodException` lúc tra cứu hoặc `IllegalArgumentException` lúc gọi.

## 2. Nhận diện hai kiểu bằng Class

```java
Class<?> primitiveArrayType = int[].class;
Class<?> wrapperArrayType = Integer[].class;

System.out.println(primitiveArrayType.getTypeName()); // int[]
System.out.println(wrapperArrayType.getTypeName());   // java.lang.Integer[]
System.out.println(primitiveArrayType.isArray());     // true
System.out.println(wrapperArrayType.isArray());       // true
System.out.println(primitiveArrayType.getComponentType().isPrimitive()); // true
System.out.println(wrapperArrayType.getComponentType().isPrimitive());   // false
```

Đây là **đoạn minh họa trong một phương thức Java**, không phải chương trình chạy độc lập. So sánh `primitiveArrayType.equals(wrapperArrayType)` trả `false`. Cần lưu ý rằng **bản thân `int[]` là một kiểu tham chiếu** (do đó `int[].class.isPrimitive()` là `false`), còn **kiểu thành phần** `int.class` mới là primitive.

| Kiểu | `Class.getTypeName()` | `getComponentType()` | Chứa `null` như một phần tử? |
| --- | --- | --- | --- |
| `int[]` | `int[]` | `int.class` | Không |
| `Integer[]` | `java.lang.Integer[]` | `Integer.class` | Có |
| `long[]` | `long[]` | `long.class` | Không |
| `Long[]` | `java.lang.Long[]` | `Long.class` | Có |
| `boolean[]` | `boolean[]` | `boolean.class` | Không |
| `Boolean[]` | `java.lang.Boolean[]` | `Boolean.class` | Có |

Mọi cặp primitive/wrapper tương ứng đều có cùng nguyên tắc: `double[]` khác `Double[]`, `char[]` khác `Character[]`, v.v.

`Class.getName()` dùng định dạng tên nội bộ khác với `getTypeName()`, ví dụ `int[].class.getName()` trả `"[I"`, còn `Integer[].class.getName()` trả `"[Ljava.lang.Integer;"`. Dùng `getTypeName()` để hiển thị dễ đọc; không suy diễn hai mảng tương thích chỉ vì tên thành phần có vẻ tương ứng.

## 3. Reflection tra cứu phương thức: chữ ký phải đúng loại mảng

Giả sử lớp có:

```java
public static int sum(int[] values) {
    return java.util.Arrays.stream(values).sum();
}
```

Cách tra cứu chính xác:

```java
// Phần minh họa trong chương trình có lớp Target.
java.lang.reflect.Method sum =
        Target.class.getMethod("sum", int[].class);
```

Cách sai:

```java
// Ném NoSuchMethodException: method sum(Integer[]) không tồn tại.
Target.class.getMethod("sum", Integer[].class);
```

`getMethod(name, Class<?>... parameterTypes)` và `getDeclaredMethod(...)` khớp **chính xác từng `Class` của tham số đã khai báo**. Khi tham số là `int[]`, Reflection yêu cầu `int[].class`; không phân tích phần tử rồi áp dụng boxing thành `Integer[].class`. Ngược lại, với phương thức nhận `Integer[]`, phải tra bằng `Integer[].class`.

Tham số đa chiều cũng tương tự: `int[][].class` khác `Integer[][].class`; không tra cứu `process(int[][])` bằng `Integer[][].class`.

### Phân biệt lookup với Method.invoke

Sau khi lấy được `Method`, đoạn gọi đúng là:

```java
int[] values = {1, 2, 3};
Object answer = sum.invoke(null, (Object) values); // Phương thức static.
```

Ở đây `(Object) values` bảo đảm `values` là **một đối số duy nhất** của phương thức đích vì `Method.invoke(Object, Object...)` chính nó là API varargs. Với một `Integer[]` không được cast thành `Object`, Java có thể xử lý mảng `Object[]` ấy như danh sách đối số varargs, gây ra lỗi số lượng đối số ngoài lỗi kiểu. Cast rõ ràng giúp tách biệt hai vấn đề.

Nếu dùng `Integer[] wrappers = {1, 2, 3}` rồi gọi:

```java
// Có Method sum đại diện cho sum(int[]).
sum.invoke(null, (Object) wrappers); // IllegalArgumentException.
```

**Không có chuyển đổi cả mảng** ở bước `invoke`: dù `Integer` có thể unbox thành `int` khi một tham số trực tiếp là `int`, tham số `int[]` không nhận `Integer[]`. `invoke` không tự chọn overload khác và không tự dựng mảng mới.

## 4. Constructor và Field cũng không đổi mảng primitive thành wrapper

Quy tắc tương tự áp dụng khi Reflection làm việc với constructor và trường dữ liệu.

### Constructor

```java
public Target(int[] values) {
    this.primitiveField = values;
}
```

Tra cứu:

```java
Constructor<Target> constructor =
        Target.class.getConstructor(int[].class); // Đúng.
```

Dùng `Target.class.getConstructor(Integer[].class)` sẽ ném `NoSuchMethodException` nếu không có constructor `(Integer[])`. Sau khi tìm đúng, `constructor.newInstance((Object) new int[] {1, 2})` hợp lệ. Truyền `Integer[]` vào constructor nhận `int[]` sẽ ném `IllegalArgumentException` do đối số sai kiểu.

### Field

Giả sử:

```java
public int[] primitiveField;
```

`Field.getType()` trả `int[].class`. Lệnh `field.set(target, new int[] {4, 5})` hợp lệ nếu caller được quyền ghi field đó, nhưng `field.set(target, new Integer[] {4, 5})` không hợp lệ và ném `IllegalArgumentException`. Reflection không thể gán mảng wrapper vào slot chứa mảng primitive.

Trong chương trình ở phần tiếp theo, cả tra cứu Method, Constructor và gán Field đều được minh họa bằng một lớp `Target` duy nhất.

## 5. Chương trình hoàn chỉnh Java 17+: đối chiếu các trường hợp

Lưu nguyên mã vào tệp **`PrimitiveWrapperArraysDemo.java`**:

```java
import java.lang.reflect.Array;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;

public class PrimitiveWrapperArraysDemo {
    public static class Target {
        public int[] primitiveField;

        public Target(int[] input) {
            primitiveField = input;
        }

        public static int sum(int[] values) {
            return Arrays.stream(values).sum();
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("same class: "
                + int[].class.equals(Integer[].class));
        System.out.println("int[]: " + int[].class.getTypeName());
        System.out.println("Integer[]: " + Integer[].class.getTypeName());
        System.out.println("int component primitive: "
                + int[].class.getComponentType().isPrimitive());
        System.out.println("Integer component primitive: "
                + Integer[].class.getComponentType().isPrimitive());
        System.out.println("Object[] accepts int[]: "
                + Object[].class.isAssignableFrom(int[].class));

        int[] ints = {1, 2, 3};
        Integer[] wrappers = {1, 2, 3};
        Method method = Target.class.getMethod("sum", int[].class);

        System.out.println("method: "
                + method.getParameterTypes()[0].getTypeName());
        System.out.println("sum(int[]): "
                + method.invoke(null, (Object) ints));

        try {
            Target.class.getMethod("sum", Integer[].class);
        } catch (NoSuchMethodException e) {
            System.out.println("lookup Integer[]: NoSuchMethodException");
        }
        try {
            method.invoke(null, (Object) wrappers);
        } catch (IllegalArgumentException e) {
            System.out.println("invoke Integer[]: IllegalArgumentException");
        }

        Constructor<Target> constructor =
                Target.class.getConstructor(int[].class);
        Target target =
                constructor.newInstance((Object) new int[] {4, 5});
        System.out.println("constructor: "
                + Arrays.toString(target.primitiveField));
        try {
            Target.class.getConstructor(Integer[].class);
        } catch (NoSuchMethodException e) {
            System.out.println(
                    "constructor Integer[]: NoSuchMethodException");
        }

        Field field = Target.class.getField("primitiveField");
        try {
            field.set(target, wrappers);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "field.set(Integer[]): IllegalArgumentException");
        }
        field.set(target, ints);
        System.out.println("field after set(int[]): "
                + Arrays.toString(target.primitiveField));

        System.out.println("Array.get int[] element class: "
                + Array.get(ints, 0).getClass().getSimpleName());
        Array.set(ints, 0, Integer.valueOf(9));
        System.out.println("Array.set int[] from Integer: "
                + Arrays.toString(ints));
        try {
            Array.set(ints, 0, Long.valueOf(9));
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "Array.set int[] from Long: IllegalArgumentException");
        }

        System.out.println("Array.newInstance int[]: "
                + Array.newInstance(int.class, 2).getClass().getTypeName());
        System.out.println("Array.newInstance Integer[]: "
                + Array.newInstance(Integer.class, 2)
                        .getClass().getTypeName());

        Integer[] boxed =
                Arrays.stream(ints).boxed().toArray(Integer[]::new);
        System.out.println("boxed: " + Arrays.toString(boxed));
        int[] unboxed =
                Arrays.stream(boxed).mapToInt(Integer::intValue).toArray();
        System.out.println("unboxed: " + Arrays.toString(unboxed));

        wrappers[0] = null;
        try {
            Arrays.stream(wrappers)
                    .mapToInt(Integer::intValue).toArray();
        } catch (NullPointerException e) {
            System.out.println("unbox null: NullPointerException");
        }

        Number[] numbers = new Integer[1];
        try {
            numbers[0] = Double.valueOf(2.5);
        } catch (ArrayStoreException e) {
            System.out.println("covariance: ArrayStoreException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac PrimitiveWrapperArraysDemo.java
java PrimitiveWrapperArraysDemo
```

Stdout chính xác trong môi trường Java 17+ thông thường:

```text
same class: false
int[]: int[]
Integer[]: java.lang.Integer[]
int component primitive: true
Integer component primitive: false
Object[] accepts int[]: false
method: int[]
sum(int[]): 6
lookup Integer[]: NoSuchMethodException
invoke Integer[]: IllegalArgumentException
constructor: [4, 5]
constructor Integer[]: NoSuchMethodException
field.set(Integer[]): IllegalArgumentException
field after set(int[]): [1, 2, 3]
Array.get int[] element class: Integer
Array.set int[] from Integer: [9, 2, 3]
Array.set int[] from Long: IllegalArgumentException
Array.newInstance int[]: int[]
Array.newInstance Integer[]: java.lang.Integer[]
boxed: [9, 2, 3]
unboxed: [9, 2, 3]
unbox null: NullPointerException
covariance: ArrayStoreException
```

**Đọc kết quả theo từng cơ chế:**

1. `int[].class.equals(Integer[].class)` trả `false`, và `getComponentType().isPrimitive()` phân biệt hai phần tử.
2. `getMethod("sum", int[].class)` đúng; `getMethod("sum", Integer[].class)` không tìm thấy chữ ký.
3. `Method.invoke` nhận `int[]` làm một đối số nhưng từ chối `Integer[]`, không unbox toàn bộ mảng.
4. Constructor nhận `int[]` và field khai báo `int[]` cũng từ chối thay thế bằng `Integer[]`.
5. `Array.get(ints, 0)` **boxing giá trị phần tử riêng lẻ** thành `Integer`; `Array.set(ints, 0, Integer.valueOf(9))` có thể unbox phần tử rồi ghi vào mảng `int[]`.
6. `Array.set(ints, 0, Long.valueOf(9))` không thực hiện chuyển đổi **narrowing `long` sang `int`**. Hỗ trợ boxing/unboxing ở **vị trí phần tử** không chứng minh có khả năng đổi kiểu của **toàn bộ mảng**.
7. `Array.newInstance(int.class, 2)` tạo `int[]`; `Array.newInstance(Integer.class, 2)` tạo `Integer[]`. Loại phần tử đưa vào quyết định loại mảng được tạo.
8. `IntStream.boxed()` và `Stream.mapToInt(...)` là hai cách **chuyển từng phần tử có chủ đích** để tạo mảng mới.
9. Mảng wrapper có thể chứa `null`, nên unbox `null` có thể ném `NullPointerException`.

## 6. Vì sao Array.get và Array.set có vẻ “boxing được”?

API `java.lang.reflect.Array` thao tác trên **phần tử**, không đổi loại mảng:

```java
int[] values = {3, 4};

Object element = Array.get(values, 0); // Integer(3) do boxing.
Array.set(values, 1, Integer.valueOf(7)); // Unbox Integer thành int.
```

`Array.get` trả `Object` nên phần tử primitive phải được boxing thành wrapper phù hợp; các phương thức `Array.getInt`, `Array.getLong`, `Array.setInt`, ... cung cấp các thao tác chuyên biệt cho primitive, với các quy tắc chuyển đổi widening được hỗ trợ. `Array.set` nhận đối tượng phần tử và có thể unbox/widen khi tương thích; nó **không chấp nhận mọi wrapper** và không tự làm narrowing tùy ý.

Các trường hợp cần tách biệt:

| Thao tác | Kết quả |
| --- | --- |
| `Array.get(new int[] {5}, 0)` | Một `Integer` biểu diễn `5` |
| `Array.set(intArray, 0, Integer.valueOf(5))` | Hợp lệ |
| `Array.set(intArray, 0, Short.valueOf((short) 5))` | Hợp lệ: unbox `short`, widening sang `int` |
| `Array.set(intArray, 0, Long.valueOf(5L))` | `IllegalArgumentException` vì không narrowing `long` về `int` |
| `Array.set(intArray, 0, null)` | `IllegalArgumentException` vì `int` không thể chứa `null` |
| `Array.set(integerArray, 0, null)` | Hợp lệ: `Integer[]` có thể chứa `null` |
| `Array.set(integerArray, 0, Long.valueOf(5L))` | `IllegalArgumentException`: `Long` không gán được cho `Integer` |

**Kết luận của phần này:** phần tử có thể được boxing/unboxing theo quy tắc API, còn **`int[]` và `Integer[]` vẫn là hai đối tượng mảng thuộc hai lớp khác nhau**.

## 7. Chuyển mảng đúng cách khi cần tương tác với API khác

Nếu bên cung cấp trả `int[]` nhưng API nhận `Integer[]`, hãy **chuyển đổi tường minh** bằng cách tạo mảng mới và boxing từng phần tử.

### Từ int[] sang Integer[]

```java
int[] source = {10, 20, 30};
Integer[] boxed = java.util.Arrays.stream(source)
        .boxed()
        .toArray(Integer[]::new);
```

### Từ Integer[] sang int[]

```java
Integer[] source = {10, 20, 30};
int[] primitives = java.util.Arrays.stream(source)
        .mapToInt(Integer::intValue)
        .toArray();
```

Hai đoạn trên là **mảnh mã đặt trong phương thức**, không phải chương trình độc lập. Kết quả là **mảng mới** và sao chép giá trị phần tử; không có phép cast thay thế.

Với `Integer[]` có `null`, cần xác định quy tắc rõ ràng: báo lỗi, loại bỏ phần tử hoặc thay bằng giá trị mặc định có ý nghĩa với nghiệp vụ. Ví dụ `mapToInt(Integer::intValue)` sẽ thất bại khi gặp `null`; không nên ngầm biến mọi `null` thành `0` nếu ứng dụng phân biệt hai trạng thái.

Khi dùng Reflection để gọi method nhận `int[]`, hãy chuyển đổi **trước** rồi truyền đúng mảng:

```java
// Minh họa trong phương thức đã có Integer[] source và Method method.
int[] converted = java.util.Arrays.stream(source)
        .mapToInt(Integer::intValue)
        .toArray();
Object result = method.invoke(null, (Object) converted);
```

Đây là lựa chọn có chủ đích và có chi phí phân bổ bộ nhớ/O(n) theo số phần tử; Reflection **không tự động thực hiện** bước này.

## 8. Mảng primitive không có cùng covariance với mảng wrapper

Mảng kiểu tham chiếu trong Java là *covariant*: vì `Integer` extends `Number`, một `Integer[]` có thể gán cho biến `Number[]`. JVM vẫn kiểm tra khi ghi phần tử:

```java
Number[] array = new Integer[1];
array[0] = Double.valueOf(3.14); // ArrayStoreException lúc chạy.
```

Ngược lại:

```java
int[] primitive = {1, 2};

// Không biên dịch:
// Object[] elements = primitive;
// Number[] numbers = primitive;

Object singleObject = primitive; // Hợp lệ: mọi mảng đều là Object.
```

Một `int[]` có thể lưu như **một đối tượng** trong biến `Object` hoặc trong **một phần tử** của `Object[]`, nhưng **bản thân nó không phải `Object[]`**: các giá trị `int` không phải tham chiếu `Object`.

Ví dụ:

```java
Object[] container = {new int[] {1, 2}, new Integer[] {3, 4}};
// container có hai phần tử, mỗi phần tử là một đối tượng mảng.
```

Tương tự, `List<int[]>` là danh sách các mảng `int[]`; nó không tương đương `List<Integer>` và không chuyển thành `Integer[]`.

## 9. Varargs, Arrays.asList và các bẫy liên quan

### 9.1. Parameter `int...` vẫn là `int[]`

```java
public static void printAll(int... numbers) {
    System.out.println(java.util.Arrays.toString(numbers));
}
```

Ở runtime, `int...` là một tham số có kiểu `int[]`; tra cứu:

```java
// Trong ngữ cảnh lớp Example có static method printAll(int...).
Method method = Example.class.getMethod("printAll", int[].class);
```

`getMethod("printAll", Integer[].class)` không khớp. `Method.isVarArgs()` có thể trả `true`, nhưng `Method.invoke` **không tự trải/đóng gói phần tử theo cú pháp gọi Java thông thường**; hãy truyền mảng phù hợp như một đối số.

### 9.2. Arrays.asList khác nhau với primitive và wrapper

```java
int[] ints = {1, 2, 3};
Integer[] wrappers = {1, 2, 3};

var a = java.util.Arrays.asList(ints);
var b = java.util.Arrays.asList(wrappers);

System.out.println(a.size()); // 1: phần tử duy nhất là cả int[].
System.out.println(b.size()); // 3: mỗi Integer là một phần tử.
```

Lý do: `Arrays.asList(T... a)` nhận `T[]` thuộc kiểu tham chiếu; `int[]` không phải mảng `T[]` chứa các đối tượng `Integer`, nên nó được xem như **một đối tượng phần tử**.

### 9.3. System.arraycopy không boxing một mảng

`System.arraycopy(intArray, 0, integerArray, 0, n)` **không** sao chép bằng boxing từng phần tử; do kiểu phần tử primitive và reference không tương thích, nó ném `ArrayStoreException`. Hãy dùng vòng lặp/stream chuyển đổi thật sự khi cần.

### 9.4. Mảng nhiều chiều

`int[][]` là mảng của các `int[]`, trong khi `Integer[][]` là mảng của `Integer[]`. Dù hai loại nhiều chiều đều là mảng các đối tượng ở cấp ngoài, **các mảng con vẫn không thể thay thế nhau**. Việc chuyển đổi phải đi qua từng hàng và từng phần tử, xử lý cả hàng `null` nếu dữ liệu cho phép.

## 10. Các lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `NoSuchMethodException` cho `process(java.lang.Integer[])` | Method thực tế nhận `int[]` | Tra đúng `int[].class` |
| `Method.invoke` ném `IllegalArgumentException` dù số phần tử đúng | Truyền `Integer[]` thay `int[]` | Chuyển từng phần tử thành `int[]`, rồi truyền `(Object) converted` |
| Lệnh `Integer[] array = primitiveArray` không biên dịch | Java không boxing ở cấp mảng | Dùng `Arrays.stream(primitiveArray).boxed().toArray(Integer[]::new)` |
| `Constructor.newInstance` từ chối `Integer[]` | Constructor khai báo tham số `int[]` | Tra/gọi đúng chữ ký `int[].class` và giá trị `int[]` |
| `Field.set` từ chối wrapper array | Field khai báo `int[]` | Kiểm tra `getType()`, tạo đúng loại mảng |
| `Array.get(intArray, 0)` trả `Integer`, tưởng cả mảng là `Integer[]` | API boxing **một phần tử** | Xem `array.getClass()` và `getComponentType()` |
| `mapToInt(Integer::intValue)` ném NPE | `Integer[]` có phần tử `null` | Quy định xử lý `null` trước khi unbox |
| `Arrays.asList(intArray).size()` bằng `1` | Cả `int[]` trở thành một phần tử của list | Dùng `Arrays.stream(intArray).boxed().toList()` để có `List<Integer>` |
| `System.arraycopy` báo `ArrayStoreException` | API không boxing cả mảng khi copy | Chuyển đổi bằng loop hoặc stream |
| Ép `(Integer[]) (Object) intArray` ném `ClassCastException` | Runtime class thật vẫn là `int[]` | Không dùng cast thay conversion |

## 11. Tự kiểm tra

1. **Có thể tra `void handle(int[] values)` bằng `getMethod("handle", Integer[].class)` không?** Không. Phải dùng `int[].class` vì chữ ký được khớp theo kiểu mảng đã khai báo.
2. **Vì sao `Array.get(new int[]{5}, 0)` trả `Integer`?** Vì `Array.get` trả `Object`, nên boxing **phần tử `int`**; điều đó không biến `int[]` thành `Integer[]`.
3. **`Object obj = new int[]{1,2}` có hợp lệ không? Còn `Object[] arr = new int[]{1,2}`?** Câu đầu hợp lệ; câu sau không biên dịch được.
4. **`Integer[]` có thể có `null` trong khi `int[]` có không?** `Integer[]` có, `int[]` không thể chứa `null` như một phần tử.
5. **Cách chuyển đổi tường minh `Integer[]` sang `int[]`?** Xác minh phần tử `null` theo nghiệp vụ, sau đó unbox từng phần tử, ví dụ bằng `Arrays.stream(values).mapToInt(Integer::intValue).toArray()`.
6. **Có thể thay `int[][]` bằng `Integer[][]` trong Reflection không?** Không; kiểu mảng nhiều chiều vẫn khác và không có chuyển đổi boxing cấp mảng.

**Ghi nhớ:** Boxing/unboxing hoạt động với **giá trị phần tử**, không chuyển đổi **kiểu của nguyên mảng**. Trong Reflection, luôn dùng đúng `Class` của tham số/field (`int[].class` hay `Integer[].class`) và thực hiện chuyển đổi mảng tường minh khi thật sự cần.

Tài liệu tham khảo: [Java Language Specification §5 — Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html), [Java SE 17 `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html), [Java SE 17 `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html).