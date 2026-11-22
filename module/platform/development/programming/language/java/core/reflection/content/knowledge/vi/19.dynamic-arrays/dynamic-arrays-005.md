# Boxing khi đọc mảng primitive bằng `Array.get` trong Java Reflection

## 1. Tình huống cần hiểu

`java.lang.reflect.Array.get(Object array, int index)` có kiểu trả về **`Object`**, kể cả khi phần tử của mảng là primitive như `int` hoặc `double`. Với mảng primitive, Reflection phải biểu diễn giá trị vừa đọc bằng wrapper tương ứng; với mảng tham chiếu, nó trả lại chính reference đang nằm ở ô đó.

~~~java
int[] scores = {42};
Object item = java.lang.reflect.Array.get(scores, 0);

System.out.println(item);                    // 42
System.out.println(item.getClass().getName()); // java.lang.Integer
~~~

Hình dung luồng dữ liệu:

~~~text
int[] -- đọc một ô --> int 42 -- boxing --> Integer(42) -- trả về Object
Integer[] -- đọc một ô --> reference Integer(42) --------> trả về Object
~~~

Hai trường hợp có thể cùng cho kết quả quan sát là một đối tượng `Integer`, nhưng **nguồn gốc khác nhau**: trong `int[]`, số nằm dưới dạng primitive; trong `Integer[]`, mảng lưu một reference tới object `Integer` đã có. Bài này tập trung vào ý nghĩa đó, khả năng gặp `null`, cách phân biệt nguồn và lúc nào nên dùng getter primitive chuyên biệt.

## 2. Quy tắc dựa vào component type trực tiếp

Bảng dưới mô tả **kiểu phần tử trực tiếp** của mảng và kiểu object trả về từ `Array.get`:

| Kiểu mảng | Component type | Kết quả khi đọc phần tử hợp lệ |
| --- | --- | --- |
| `boolean[]` | `boolean` | `Boolean` |
| `byte[]` | `byte` | `Byte` |
| `short[]` | `short` | `Short` |
| `char[]` | `char` | `Character` |
| `int[]` | `int` | `Integer` |
| `long[]` | `long` | `Long` |
| `float[]` | `float` | `Float` |
| `double[]` | `double` | `Double` |
| `Integer[]` | `Integer` | Reference `Integer` hoặc `null` |
| `String[]` | `String` | Reference `String` hoặc `null` |
| `int[][]` | `int[]` | Reference tới một `int[]` hoặc `null` |

Để kiểm tra *cơ chế đọc*, dùng:

~~~java
Object unknown = new int[] {42};
Class<?> component = unknown.getClass().getComponentType();

System.out.println(component == int.class);  // true
System.out.println(component.isPrimitive()); // true
~~~

`getComponentType()` chỉ bỏ **một tầng**. Chẳng hạn, `int[][].class.getComponentType() == int[].class`; vì `int[]` cũng là object, `int[][].class.getComponentType().isPrimitive()` trả `false`. Đọc tầng ngoài bằng `Array.get` cho một mảng con `int[]`; khi tiếp tục đọc **trong mảng con** thì mới boxing một số `int` thành `Integer`.

## 3. Khi hai object giống nhau về class nhưng khác ngữ nghĩa

~~~java
Object primitiveArray = new int[] {7};
Object wrapperArray = new Integer[] {7};

Object a = java.lang.reflect.Array.get(primitiveArray, 0);
Object b = java.lang.reflect.Array.get(wrapperArray, 0);

System.out.println(a.getClass() == b.getClass()); // true
System.out.println(a.equals(b));                  // true
~~~

Các kết quả trên **không cho phép kết luận** cả hai mảng có cùng loại. Kiểm tra thành phần sẽ cho `int.class` và `Integer.class`. Điều này quan trọng với serializer hoặc bộ ánh xạ dữ liệu: một mảng primitive không thể có phần tử `null`, trong khi một mảng wrapper có thể.

~~~java
int[] primitive = new int[1];
Integer[] reference = new Integer[1];

System.out.println(java.lang.reflect.Array.get(primitive, 0)); // 0
System.out.println(java.lang.reflect.Array.get(reference, 0)); // null
~~~

Không gọi `getClass()` trực tiếp trên một phần tử chưa kiểm tra `null`. Ngoài ra, **`Character` và `Boolean` không kế thừa `Number`**. Nếu công cụ phân loại kết quả với `item instanceof Number`, nó bỏ sót hai wrapper này. Khi cần hỗ trợ đủ tám primitive, hãy dựa vào **component type của mảng nguồn**, rồi chọn chính sách chuyển đổi phù hợp.

### Boxing không có nghĩa mảng đã được chuyển đổi

Dù `Array.get(new int[]{7}, 0)` trả `Integer`, đối tượng mảng nguồn vẫn là `int[]`. Nó không trở thành `Integer[]` và không thể ép sang `Object[]`. Nếu API thực sự cần một mảng reference, phải **cấp phát mảng mới và copy/boxing từng giá trị**. Một phép cast không thực hiện chuyển đổi toàn bộ mảng.

## 4. Chương trình độc lập: so sánh bốn trường hợp

Lưu thành `ArrayBoxingFocusDemo.java`, chạy bằng JDK 17+:

~~~java
import java.lang.reflect.Array;

public class ArrayBoxingFocusDemo {
    static void describe(String name, Object source, int index) {
        Class<?> component = source.getClass().getComponentType();
        Object item = Array.get(source, index);
        System.out.println(name
                + ": component=" + component.getTypeName()
                + ", primitive=" + component.isPrimitive()
                + ", value=" + (item instanceof int[] ? "int[]" : item)
                + ", resultType=" + (item == null
                        ? "null" : item.getClass().getTypeName()));
    }

    public static void main(String[] args) {
        describe("primitive", new int[] {42}, 0);
        describe("wrapper", new Integer[] {42}, 0);
        describe("empty-reference", new Integer[1], 0);
        describe("nested", new int[][] {{42}}, 0);

        Object row = Array.get(new int[][] {{42}}, 0);
        describe("nested-leaf", row, 0);

        System.out.println("getInt(byte[])="
                + Array.getInt(new byte[] {7}, 0));
        System.out.println("getLong(int[])="
                + Array.getLong(new int[] {7}, 0));

        try {
            Array.getInt(new Integer[] {7}, 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("getInt(wrapperArray)=rejected");
        }
    }
}
~~~

~~~bash
javac --release 17 ArrayBoxingFocusDemo.java
java ArrayBoxingFocusDemo
~~~

Kết quả:

~~~text
primitive: component=int, primitive=true, value=42, resultType=java.lang.Integer
wrapper: component=java.lang.Integer, primitive=false, value=42, resultType=java.lang.Integer
empty-reference: component=java.lang.Integer, primitive=false, value=null, resultType=null
nested: component=int[], primitive=false, value=int[], resultType=int[]
nested-leaf: component=int, primitive=true, value=42, resultType=java.lang.Integer
getInt(byte[])=7
getLong(int[])=7
getInt(wrapperArray)=rejected
~~~

Khi chạy, hãy đối chiếu `primitive` và `wrapper`: `resultType` giống nhau, nhưng `component` và `primitive` khác. Ở `nested`, giá trị đọc được là mảng con, chưa phải một số; `nested-leaf` mới đọc giá trị primitive. Kết quả `null` của `empty-reference` là hợp lệ, không phải lỗi Reflection.

## 5. Vì sao `getInt` khác `get`?

Các getter chuyên biệt (`getBoolean`, `getByte`, `getShort`, `getChar`, `getInt`, `getLong`, `getFloat`, `getDouble`) có kiểu trả về **primitive** trên chữ ký API. Chẳng hạn:

~~~java
int[] source = {10};
Object boxed = Array.get(source, 0);   // Object tham chiếu Integer.
int exact = Array.getInt(source, 0);   // Giá trị int.
long wider = Array.getLong(source, 0); // int -> long hợp lệ.
~~~

Đoạn trên cần import `java.lang.reflect.Array` và được đặt bên trong một method.

Typed getter cho phép **identity hoặc widening primitive** từ component type của mảng **sang kiểu trả về**. `getInt` nhận `byte[]`, `short[]`, `char[]`, `int[]`, nhưng không đọc `long[]` vì đó là narrowing. `getDouble` nhận các mảng primitive số hợp lệ (không nhận `boolean[]`), tuy widening `long -> double` vẫn có thể mất độ chính xác. Typed getter **không tự unbox reference array**: `Array.getInt(new Integer[]{10}, 0)` bị từ chối.

Để tìm đầy đủ chiều conversion cho mọi getter/setter, xem bài `Array.get, Array.set và các biến thể primitive`; ở đây cần giữ một quy tắc: **`get` đóng hộp theo kiểu phần tử thực, còn `getXxx` trả primitive theo đường widening mà API cho phép**.

## 6. Khi nào boxing có tác động thực tế?

**API tổng quát:** Một inspector/serializer xử lý `Object unknownArray` có thể dùng `Array.get` để nhận phần tử dưới dạng `Object` mà không cần biết trước kiểu số. Đây là cách đơn giản, nhưng phải phân biệt wrapper vừa boxing với object tham chiếu vốn đã tồn tại.

**Hot loop:** Nếu mã biết nguồn là `int[]` và cần cộng hàng triệu số, truy cập `typedArray[i]` thường hợp lý hơn việc đọc thành `Object`, cast/unbox rồi cộng. `Array.getInt` làm rõ kiểu trả về `int`, song chi phí thực tế còn phụ thuộc JVM, JIT và cách người gọi sử dụng kết quả. Không suy đoán số object được cấp phát chỉ từ cú pháp; hãy đo ở đúng môi trường khi có vấn đề hiệu năng.

**So sánh:** Không dựa vào `==` giữa hai kết quả boxing; wrapper có thể được tái sử dụng/cached và việc đồng nhất object không phải hợp đồng để so giá trị mảng. So sánh giá trị bằng `equals` hoặc unbox với kiểu phù hợp; đừng ép mọi phần tử sang `Integer` khi nguồn có thể là `long[]` hay `char[]`.

**Đọc và ghi:** Khi `Array.set` ghi vào mảng primitive, `Object value` được xem xét theo wrapper nguồn, unboxing và widening hợp lệ trước khi lưu. Hướng conversion đó **khác hướng đọc** của `getXxx`; một giá trị `Integer` không tự chuyển thành object `Long` để ghi vào `Long[]`. Bài về điều kiện widening khi gán giải thích sâu phần này.

## 7. Ranh giới lỗi nên phân biệt

| Tình huống | Hậu quả | Bài học |
| --- | --- | --- |
| `Array.get(new int[]{7}, 0)` | `Integer` | Boxing đúng kiểu primitive |
| `Array.get(new Integer[]{null}, 0)` | `null` | Mảng reference cho phép phần tử null |
| `(Integer) Array.get(new long[]{7}, 0)` | `ClassCastException` | Kết quả thật là `Long` |
| `Array.getInt(new Integer[]{7}, 0)` | `IllegalArgumentException` | Typed getter không dùng cho reference array |
| `Array.get(new int[0], 0)` | `ArrayIndexOutOfBoundsException` | Mảng hợp lệ nhưng không có chỉ số 0 |
| `Array.get(null, 0)` | `NullPointerException` | Không có đối tượng mảng |
| `Array.get("text", 0)` | `IllegalArgumentException` | Đối tượng không phải mảng |

Nếu nhận đầu vào không rõ kiểu, kiểm tra `array != null`, `array.getClass().isArray()` và `Array.getLength(array)` trước khi truy cập phần tử. Sau đó kiểm tra `component.isPrimitive()` hoặc `item == null` trước khi xử lý kết quả. Việc này bảo vệ ranh giới dữ liệu nhưng không thay thế bước kiểm tra kiểu trong logic nghiệp vụ.

## 8. Câu hỏi tự kiểm tra

1. Vì sao `Array.get(new int[]{1}, 0)` và `Array.get(new Integer[]{1}, 0)` đều trả `Integer` nhưng có nguồn gốc khác nhau?
2. Vì sao đọc tầng ngoài `int[][]` qua `Array.get` **không boxing `int`**?
3. Kết quả của `Array.get(new boolean[]{false}, 0)` là wrapper nào? Tại sao `instanceof Number` không nhận diện được nó?
4. `Array.getLong(new int[]{10}, 0)` có hợp lệ không? `Array.getInt(new long[]{10}, 0)` thì sao?
5. Tại sao `getInt` không làm việc với `Integer[]`, dù phần tử đầu đang chứa `Integer(10)`?
6. Trong framework tổng quát, tại sao kiểm tra `component.isPrimitive()` đáng tin cậy hơn đoán nguồn mảng qua class của đối tượng trả về từ `Array.get`?

**Đáp án cốt lõi:** Quyết định boxing của `Array.get` phụ thuộc **component type trực tiếp của mảng**. Getter primitive chuyên biệt trả primitive qua identity/widening hợp lệ; một mảng reference vẫn là mảng reference, bất kể nó lưu wrapper gì.

Tài liệu chuẩn: [Java SE 17 — `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html), [JLS §5.1.7 — Boxing](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.7).