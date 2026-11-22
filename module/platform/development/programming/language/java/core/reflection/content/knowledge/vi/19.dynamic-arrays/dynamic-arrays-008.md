# Chẩn đoán lỗi mảng động: chỉ số, kích thước âm và đầu vào không phải mảng

## 1. Mỗi lỗi chỉ đúng một loại vi phạm

`java.lang.reflect.Array` thao tác trên mảng thật ở runtime, kể cả khi caller chỉ có biến `Object`. Cùng một hệ thống có thể nhận kiểu mảng từ cấu hình, tạo mảng, rồi đọc/ghi phần tử. Lỗi sẽ có ý nghĩa khác nhau tùy **bước thất bại**:

| Bước | Đầu vào sai | Exception gốc của API |
| --- | --- | --- |
| Cấp phát `Array.newInstance` | Kích thước âm ở một chiều | `NegativeArraySizeException` |
| Tạo mảng | `componentType == null` | `NullPointerException` |
| Tạo mảng | `void.class`, không có chiều, hoặc tổng rank vượt 255 | `IllegalArgumentException` |
| `Array.getLength`/`get`/`set` | Tham chiếu array là `null` | `NullPointerException` |
| `Array.getLength`/`get`/`set` | Object khác `null` nhưng không phải mảng | `IllegalArgumentException` |
| `Array.get`/`set` | Index âm hoặc `index >= length` | `ArrayIndexOutOfBoundsException` |
| `Array.set` | Giá trị không tương thích với component type | `IllegalArgumentException` |

Từ bảng này, có thể nhớ ba trường hợp trọng tâm:

- **`ArrayIndexOutOfBoundsException`:** đối tượng mảng đã tồn tại, nhưng chỉ số vượt biên.
- **`NegativeArraySizeException`:** thông số cấp phát một chiều hoặc nhiều chiều là số âm.
- **`IllegalArgumentException` do non-array:** API nhận object nhưng object ấy không phải một đối tượng mảng.

`null` là trường hợp khác: `Array.getLength(null)` gây `NullPointerException`; `new int[0]` vẫn là mảng hoàn toàn hợp lệ. Hãy dựa vào **API đã gọi và dữ liệu tại bước đó**, vì một tên exception có thể biểu thị nhiều nguyên nhân khác nhau.

## 2. Kiểm tra độ dài trước khi tạo

`Array.newInstance(Class<?> componentType, int length)` tạo một mảng dài `length`; overload `int... dimensions` tạo nhiều chiều theo thứ tự ngoài vào trong.

~~~java
Array.newInstance(int.class, 0);         // int[0], hợp lệ.
Array.newInstance(int.class, -1);        // NegativeArraySizeException.
Array.newInstance(String.class, 2, -1);  // NegativeArraySizeException.
Array.newInstance(void.class, 1);        // IllegalArgumentException.
Array.newInstance(int.class, new int[0]); // IllegalArgumentException.
~~~

Đây là các lời gọi minh họa có import `java.lang.reflect.Array`; những lời gọi gây lỗi không nên chạy liên tiếp ngoài `try/catch`.

Một **chiều bằng 0** vẫn hợp lệ, khác với **không truyền chiều nào**. `Array.newInstance(String.class, 2, 0)` cấp phát hai mảng con rỗng, còn `Array.newInstance(String[].class, 2)` chỉ cấp phát mảng ngoài và để hai mảng con `null`.

Nếu component type vốn là array class, tổng số chiều kết quả bằng rank đã có cộng số chiều truyền thêm. Java giới hạn rank kiểu mảng ở 255, nên `Array.newInstance(int[][].class, new int[254])` đòi 256 chiều và bị từ chối. Để học chi tiết hình dạng mảng, xem bài tạo mảng nhiều chiều trong cùng chương; khi chẩn đoán lỗi, trước hết xác định **rank đích** và **từng kích thước**.

### Dữ liệu kích thước từ bên ngoài

Kiểm tra `length >= 0` là cần nhưng chưa đủ. Một giá trị dương rất lớn có thể gây `OutOfMemoryError` hoặc gặp giới hạn cấp phát của JVM. Nếu độ dài tính qua phép cộng/nhân, tràn `int` có thể biến đầu vào dương thành số âm hoặc số không đúng. Hãy đặt giới hạn nghiệp vụ và dùng `Math.addExact`/`multiplyExact` khi cần phát hiện overflow.

Ví dụ helper với chính sách tối đa 10.000 phần tử tầng ngoài:

~~~java
static Object newBoundedArray(Class<?> type, int length) {
    if (type == null || type == void.class) {
        throw new IllegalArgumentException("Invalid component type");
    }
    if (length < 0 || length > 10_000) {
        throw new IllegalArgumentException("Unsupported length: " + length);
    }
    return java.lang.reflect.Array.newInstance(type, length);
}
~~~

`IllegalArgumentException` trên là **do helper tự chọn** để trả lỗi cấu hình sớm, không phải `NegativeArraySizeException` của `Array.newInstance`. Giới hạn 10.000 cũng là ví dụ chính sách ứng dụng, **không phải giới hạn của Java**.

## 3. Kiểm tra mảng thật trước khi đo độ dài

`Array.getLength(Object)` nhận **một đối tượng mảng**, chẳng hạn `new int[]{1}`, `new String[0]` hoặc `new int[2][3]`. Nó không nhận `String`, `List` hay chính đối tượng `Class` mô tả kiểu mảng.

~~~java
Object actual = new int[] {1, 2};
Object metadata = int[].class;

System.out.println(actual.getClass().isArray());   // true
System.out.println(metadata.getClass().isArray()); // false
System.out.println(Array.getLength(actual));       // 2
// Array.getLength(metadata); // IllegalArgumentException.
~~~

Đoạn trên dùng `Array` đã import. `int[].class.isArray()` đúng vì token ấy **mô tả kiểu mảng**, nhưng `int[].class` vẫn là đối tượng `Class` chứ không phải một instance `int[]`.

Mẫu bảo vệ đầu vào:

~~~java
static int requireLength(Object candidate) {
    if (candidate == null) {
        throw new IllegalArgumentException("Array is required");
    }
    if (!candidate.getClass().isArray()) {
        throw new IllegalArgumentException(
                "Not an array: " + candidate.getClass().getTypeName());
    }
    return java.lang.reflect.Array.getLength(candidate);
}
~~~

Helper chủ động trả `IllegalArgumentException` cho cả `null` lẫn non-array. Đây là **hợp đồng của ứng dụng**; API nguyên thủy vẫn phân biệt `NullPointerException` cho `null` và `IllegalArgumentException` cho object không phải mảng.

Không quy ước `0` nghĩa là “không phải mảng”. `new int[0]` là mảng thật, có length 0 và không chứa index hợp lệ.

## 4. Kiểm tra chỉ số trên đúng mảng đang truy cập

Với mảng cụ thể dài `n`, điều kiện để đọc/ghi là:

\[0 \leq index < n\]

Nếu `n == 0` thì **không có index hợp lệ**. `Array.get(new int[0], 0)` ném `ArrayIndexOutOfBoundsException` dù việc tạo mảng rỗng đã thành công.

Có thể kiểm tra:

~~~java
static Object checkedGet(Object array, int index) {
    if (array == null || !array.getClass().isArray()) {
        throw new IllegalArgumentException("Expected an array");
    }
    int length = java.lang.reflect.Array.getLength(array);
    if (index < 0 || index >= length) {
        throw new IndexOutOfBoundsException(
                "index=" + index + ", length=" + length);
    }
    return java.lang.reflect.Array.get(array, index);
}
~~~

Helper dùng `IndexOutOfBoundsException` của ứng dụng để giải thích lỗi, còn `Array.get` trực tiếp dùng subtype `ArrayIndexOutOfBoundsException`. `Objects.checkIndex(index, length)` cũng giúp kiểm tra biên nhưng không cam kết đúng subclass do Reflection ném. Khi chẩn đoán, cần biết **exception phát ra từ API nào**.

### Mảng nhiều chiều có biên riêng ở từng tầng

~~~java
int[][] rows = {{1, 2, 3}, {}, null, {4}};
~~~

`Array.getLength(rows)` bằng 4; bốn hàng có độ dài 3, 0, chưa có mảng con, và 1. Muốn lấy `rows[3][0]` bằng Reflection:

1. Xác minh chỉ số hàng 3 trong độ dài mảng ngoài.
2. `Object row = Array.get(rows, 3)` rồi kiểm tra `row != null`.
3. Đo `Array.getLength(row)` bằng 1, xác minh index cột 0.
4. `Array.get(row, 0)` trả một `Integer` chứa 4 vì mảng con có component primitive `int`.

Với hàng 1, index cột 0 vượt biên; với hàng 2, gọi `Array.getLength` trên `null` sẽ gây `NullPointerException`. Hai lỗi khác nhau dù đều xuất hiện khi xử lý một ma trận.

## 5. Chương trình Java 17+ kiểm tra danh tính exception

Tạo file `ReflectArrayFailureAtlas.java`:

~~~java
import java.lang.reflect.Array;

public class ReflectArrayFailureAtlas {
    static void show(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + ": OK");
        } catch (RuntimeException ex) {
            System.out.println(name + ": "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        Object array = Array.newInstance(String.class, 2);
        Array.set(array, 0, "A");
        System.out.println("length=" + Array.getLength(array));

        show("negative", () -> Array.newInstance(int.class, -1));
        show("negative dimension",
                () -> Array.newInstance(int.class, 2, -1));
        show("void", () -> Array.newInstance(void.class, 1));
        show("no dimension",
                () -> Array.newInstance(int.class, new int[0]));

        show("null length", () -> Array.getLength(null));
        show("non-array", () -> Array.getLength("hello"));
        show("class token", () -> Array.getLength(int[].class));

        show("index -1", () -> Array.get(array, -1));
        show("index at length", () -> Array.get(array, 2));
        show("wrong element", () -> Array.set(array, 0, 123));

        Object partial = Array.newInstance(int[].class, 1);
        show("missing subarray",
                () -> Array.getLength(Array.get(partial, 0)));
        show("empty array index", () -> Array.get(new int[0], 0));
    }
}
~~~

~~~bash
javac --release 17 ReflectArrayFailureAtlas.java
java ReflectArrayFailureAtlas
~~~

Kết quả:

~~~text
length=2
negative: NegativeArraySizeException
negative dimension: NegativeArraySizeException
void: IllegalArgumentException
no dimension: IllegalArgumentException
null length: NullPointerException
non-array: IllegalArgumentException
class token: IllegalArgumentException
index -1: ArrayIndexOutOfBoundsException
index at length: ArrayIndexOutOfBoundsException
wrong element: IllegalArgumentException
missing subarray: NullPointerException
empty array index: ArrayIndexOutOfBoundsException
~~~

`show` bắt `RuntimeException` chỉ để **in loại lỗi khi thực hành**. Trong ứng dụng thực, một khối catch rộng như vậy dễ che giấu lỗi lập trình; nên kiểm tra trước, báo đúng dữ liệu sai và bắt lỗi cụ thể ở ranh giới có thể xử lý.

## 6. Không nhầm lỗi phần tử với lỗi đầu vào không phải mảng

`IllegalArgumentException` không chỉ có nghĩa “không phải mảng”. Chẳng hạn:

~~~java
Array.set(new String[1], 0, 42);     // Sai component type.
Array.set(new int[1], 0, 3L);        // long -> int là narrowing.
Array.set(new int[1], 0, null);      // Primitive không nhận null.
~~~

Các thao tác trên đều có **mảng hợp lệ và index hợp lệ**, nhưng giá trị không thể chuyển đổi theo hợp đồng `Array.set`. Với mảng primitive, Reflection có thể unbox wrapper rồi widening hợp lệ; không tự narrowing. Với mảng reference, giá trị phải là `null` hoặc tương thích với component type **runtime** của mảng.

Một khác biệt đáng nhớ:

~~~java
Object[] refs = new String[1];
refs[0] = Integer.valueOf(5); // ArrayStoreException.

Object array = new String[1];
Array.set(array, 0, Integer.valueOf(5)); // IllegalArgumentException.
~~~

Hai API ghi khác nhau và có hợp đồng báo lỗi khác nhau. Muốn tìm nguyên nhân, ghi rõ hoạt động nào đã xảy ra, kiểu runtime của mảng, component type, index và kiểu của value (nếu khác `null`).

## 7. Quy trình chẩn đoán dành cho mapper hoặc plugin

Khi xử lý dữ liệu không biết trước kiểu, hãy đi theo thứ tự:

1. **Tạo mảng:** component type có khác `null`, khác `void.class`, rank hợp lệ, mọi kích thước không âm và trong ngân sách bộ nhớ không?
2. **Xử lý mảng đã có:** giá trị có khác `null`, runtime class có `isArray() == true` không?
3. **Đọc/ghi:** index có thỏa `0 <= index < Array.getLength(array)` tại đúng tầng không?
4. **Ghi phần tử:** `array.getClass().getComponentType()` là gì, value có `null` không, và có cần conversion riêng (parse chuỗi, thu hẹp số có kiểm soát) trước khi gọi `Array.set` không?
5. **Mảng nhiều chiều:** mảng con hiện tại đã được cấp phát chưa? Nó có thể là `null` dù runtime class mảng ngoài đã có nhiều chiều.
6. **Thông báo lỗi:** nêu tên trường đầu vào, loại thao tác, index, length và component type; giữ thông tin cần thiết để sửa cấu hình nhưng tránh log cả dữ liệu phần tử nhạy cảm.

Đừng coi mọi `RuntimeException` phát sinh trong pipeline là “sai kiểu mảng”. `NegativeArraySizeException` là lỗi tạo, `ArrayIndexOutOfBoundsException` là lỗi vị trí, và `IllegalArgumentException` có thể là input không phải mảng **hoặc** lỗi chuyển đổi phần tử.

### Bảng quyết định nhanh

| Dấu hiệu | Kiểm tra tiếp |
| --- | --- |
| Không tạo được mảng | Dimension âm, số chiều, `void.class`, component `null`, bộ nhớ |
| `getLength` thất bại | Null hay object không phải array? |
| `get`/`set` thất bại | Index thực tế, length của đúng tầng, loại array |
| `set` sai kiểu | Primitive/reference component, kiểu value, widening/narrowing |
| Chỉ thất bại khi đi xuống tầng trong | Mảng con `null`, jagged length, nhầm số chiều |
| Nhầm `ArrayStoreException` với `IllegalArgumentException` | Cú pháp gán trực tiếp hay `Array.set`? |

## 8. Tự kiểm tra

1. `Array.newInstance(int.class, 0)` có lỗi không? `Array.get(new int[0], 0)` thì sao?
2. `Array.newInstance(String.class, 2, -3)` ném gì? Một helper tự ném `IllegalArgumentException` trước khi gọi thì khác thế nào?
3. Vì sao `Array.getLength(int[].class)` sai mặc dù `int[].class.isArray()` là true?
4. Với `int[][] rows = {{1}, null}`, lỗi khi đọc `rows[0][1]` khác gì lỗi đo độ dài `rows[1]`?
5. Vì sao `Array.set(new String[1], 0, Integer.valueOf(1))` không ném cùng exception với gán qua `Object[] alias = new String[1]`?
6. Nếu nguồn gửi một kích thước rất lớn nhưng không âm, việc cấp phát có chắc chắn thành công không?

**Điều cần nhớ:** phân biệt lỗi **cấp phát**, lỗi **nhận dạng mảng**, lỗi **chỉ số** và lỗi **kiểu giá trị** theo bước API đã gọi. Khi có đối tượng mảng hợp lệ, kiểm tra biên ở đúng tầng; khi chỉ có input cấu hình, xác minh component type/kích thước trước khi cấp phát. Không đánh đồng mảng rỗng với `null` và không coi `0` là mã báo “không phải mảng”.

Tài liệu chính thức: [Java SE 17 — `java.lang.reflect.Array`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Array.html), [Java SE 17 — `Class.isArray`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [Java SE 17 — `Objects.checkIndex`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html).