# Không ép `int[]` thành `Object[]` trong Java Reflection

## Mục tiêu học tập

Sau bài này, bạn có thể giải thích vì sao mảng số nguyên nguyên thủy `int[]` là một đối tượng Java nhưng không phải `Object[]`; nhận biết lỗi tại thời điểm biên dịch và lỗi `ClassCastException` khi ép kiểu; thao tác với mảng chưa biết kiểu phần tử thông qua `java.lang.reflect.Array`; và chủ động chuyển dữ liệu sang `Integer[]` khi một API thực sự yêu cầu mảng đối tượng.

## 1. Hiểu đúng kiểu mảng

Trong Java, **mọi mảng đều là đối tượng**: dù chứa phần tử nguyên thủy hay tham chiếu, mỗi mảng đều có kiểu runtime, thuộc tính `length`, kế thừa các hành vi của `Object` và triển khai `Cloneable`, `Serializable`. Tuy nhiên, “là một `Object`” không đồng nghĩa “là một `Object[]`”.

- `int[]` chứa các giá trị `int` nguyên thủy. Kiểu thành phần (component type) là `int`; các phần tử không phải đối tượng `Integer`.
- `Integer[]`, `String[]` và `Object[]` là **mảng tham chiếu**: mỗi vị trí giữ một tham chiếu đến đối tượng (hoặc `null`).
- `Object[]` chỉ đại diện cho mảng có **kiểu thành phần là kiểu tham chiếu** thích hợp. Nó không đại diện chung cho tất cả các loại mảng.
- `Object` có thể tham chiếu tới cả `int[]`, `long[]`, `String[]`, `Integer[]` và `int[][]`.

| Giá trị runtime | Gán vào `Object` | Gán vào `Object[]` | Kiểu phần tử |
| --- | --- | --- | --- |
| `new int[3]` | Có | Không | `int` nguyên thủy |
| `new Integer[3]` | Có | Có | `Integer` |
| `new String[3]` | Có | Có | `String` |
| `new Object[3]` | Có | Có | `Object` |
| `new int[2][3]` | Có | Có, ở **mảng ngoài** | `int[]` (kiểu tham chiếu) |

Điểm cuối dễ gây nhầm: `int[][]` là mảng của các `int[]`; mảng ngoài giữ **tham chiếu** đến các mảng con. Vì vậy `int[][]` có thể xem là `Object[]`, nhưng từng `int[]` bên trong vẫn **không** phải `Object[]`.

### Sơ đồ kiểu

~~~text
Object
├── int[]              (mảng phần tử nguyên thủy)
├── long[]             (mảng phần tử nguyên thủy)
├── Object[]           (mảng phần tử tham chiếu)
│   ├── String[]
│   ├── Integer[]
│   └── int[][]       (phần tử của mảng ngoài là int[])
└── ...
~~~

Sơ đồ thể hiện quan hệ gán kiểu có ích cho bài này; nó không phải khai báo `extends` viết được trong mã nguồn Java.

## 2. Hai dạng lỗi ép kiểu cần phân biệt

### 2.1. Lỗi biên dịch khi biết trước kiểu là `int[]`

~~~java
int[] numbers = {10, 20, 30};

Object anyArray = numbers;             // Hợp lệ: mọi mảng đều là Object.
Object[] refs = numbers;               // LỖI BIÊN DỊCH.
Object[] casted = (Object[]) numbers;   // VẪN LỖI BIÊN DỊCH.
~~~

Đây là **đoạn cố ý chứa lỗi** để nhận diện kiểu; không đưa nguyên đoạn vào chương trình cần biên dịch. Trình biên dịch biết `numbers` có kiểu tĩnh `int[]` và không có phép chuyển kiểu hợp lệ sang `Object[]`. Thêm phép cast tường minh không thể biến giá trị `int` nguyên thủy thành phần tử tham chiếu.

### 2.2. Biên dịch được qua `Object`, nhưng lỗi lúc chạy

File `ArrayCastPitfall.java`:

~~~java
public class ArrayCastPitfall {
    public static void main(String[] args) {
        int[] numbers = {10, 20, 30};
        Object unknown = numbers;

        System.out.println(unknown instanceof Object);
        System.out.println(unknown instanceof Object[]);
        System.out.println(
                unknown.getClass().getComponentType().getTypeName()
        );

        try {
            Object[] wrong = (Object[]) unknown;
            System.out.println(wrong.length); // Không chạy tới đây.
        } catch (ClassCastException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac ArrayCastPitfall.java
java ArrayCastPitfall
~~~

Kết quả chuẩn:

~~~text
true
false
int
ClassCastException
~~~

Biến `unknown` có **kiểu khai báo** là `Object`, nên trình biên dịch cho phép thử cast xuống `Object[]`. Nhưng đối tượng thật được tạo bằng `new int[]{...}`, có kiểu runtime `int[]`; JVM kiểm tra và từ chối cast bằng `ClassCastException`. Một phép cast chỉ kiểm tra/chuyển cách nhìn về kiểu tương thích; **nó không chuyển đổi hoặc boxing từng phần tử**.

Kiểm tra `instanceof Object[]` trước khi cast chỉ giúp tránh ngoại lệ. Nó không khiến `int[]` trở thành mảng tham chiếu.

## 3. Vì sao vấn đề xuất hiện khi dùng Reflection?

Reflection thường xử lý một đối tượng mảng mà **chưa biết trước kiểu phần tử tại thời điểm biên dịch**. Chẳng hạn `Field.get(instance)` có thể trả về `int[]`, `String[]` hoặc kiểu mảng khác dưới dạng `Object`. Một hàm tiện ích nhận `Object array` rồi ép vô điều kiện thành `Object[]` sẽ hỏng ngay khi gặp mảng nguyên thủy.

Không nên viết:

~~~java
// Sai nếu field chứa int[], long[], boolean[] hoặc mảng nguyên thủy khác.
Object value = field.get(instance);
Object[] elements = (Object[]) value;
~~~

Đây là **đoạn minh họa rời**: `field` và `instance` phải được khai báo trong ngữ cảnh Reflection thực tế. Sai lầm nằm ở phép cast, không ở `Field.get`.

Java cung cấp `java.lang.reflect.Array` để thao tác với **cả mảng nguyên thủy và mảng tham chiếu** khi chỉ có biến `Object`:

| Nhu cầu | API thích hợp |
| --- | --- |
| Xác định một đối tượng có phải mảng | `value != null && value.getClass().isArray()` |
| Lấy kiểu thành phần runtime | `value.getClass().getComponentType()` |
| Nhận biết kiểu thành phần nguyên thủy | `componentType.isPrimitive()` |
| Lấy số phần tử | `Array.getLength(value)` |
| Đọc phần tử tại chỉ số `i` | `Array.get(value, i)` |
| Ghi phần tử tương thích | `Array.set(value, i, element)` |
| Tạo mảng theo kiểu phần tử xác định lúc chạy | `Array.newInstance(componentType, length)` |

`Array.get` trả về `Object`; khi đọc phần tử từ `int[]`, giá trị `int` được **boxing thành `Integer`**. Các phương thức chuyên biệt như `Array.getInt` và `Array.setInt` làm việc với giá trị nguyên thủy theo quy tắc tương thích kiểu của chúng, tránh boxing ở vị trí phù hợp. `Array.getLength` và `Array.get` yêu cầu đối số là mảng; truyền `null`, đối tượng thường hoặc chỉ số không hợp lệ sẽ gây ngoại lệ tương ứng.

## 4. Ví dụ đầy đủ: tạo và duyệt mảng động bằng Reflection

“Mảng động” ở đây nghĩa là **tạo/kiểm tra mảng khi kiểu thành phần được quyết định lúc chạy** qua Reflection. Mảng Java sau khi tạo có `length` cố định; nó không tự mở rộng kích thước như `ArrayList`.

File `ReflectiveArrayDemo.java`:

~~~java
import java.lang.reflect.Array;
import java.util.StringJoiner;

public class ReflectiveArrayDemo {
    public static void main(String[] args) {
        // Tạo int[3]; Array.newInstance trả về Object.
        Object ints = Array.newInstance(int.class, 3);
        Array.setInt(ints, 0, 7);
        Array.setInt(ints, 1, 14);
        Array.setInt(ints, 2, 21);
        printArray(ints);

        // Tạo String[2] bằng kiểu thành phần runtime.
        Object words = Array.newInstance(String.class, 2);
        Array.set(words, 0, "Java");
        Array.set(words, 1, "Reflection");
        printArray(words);

        // Chỉ mảng tham chiếu tương thích mới cast sang Object[].
        if (words instanceof Object[] refs) {
            System.out.println(refs[0]);
        }
    }

    private static void printArray(Object array) {
        if (array == null || !array.getClass().isArray()) {
            throw new IllegalArgumentException("Expected an array");
        }

        Class<?> componentType = array.getClass().getComponentType();
        int length = Array.getLength(array);
        StringJoiner joined = new StringJoiner(", ", "[", "]");

        for (int i = 0; i < length; i++) {
            joined.add(String.valueOf(Array.get(array, i)));
        }

        System.out.println(
                componentType.getTypeName() + "[" + length + "] = " + joined
        );
    }
}
~~~

Chạy:

~~~bash
javac ReflectiveArrayDemo.java
java ReflectiveArrayDemo
~~~

Kết quả chuẩn:

~~~text
int[3] = [7, 14, 21]
java.lang.String[2] = [Java, Reflection]
Java
~~~

Giải thích: `Array.newInstance(int.class, 3)` thực sự tạo `int[]`; `Array.newInstance(String.class, 2)` tạo `String[]`. Cả hai được giữ trong biến `Object`, và `printArray` duyệt qua `Array.getLength`/`Array.get` nên không cần ép sang `Object[]`. Với mảng `String[]`, kiểm tra `instanceof Object[]` đúng và cast hợp lệ. Lúc gọi `Array.get` trên `int[]`, các số được boxing phục vụ thao tác generic.

Có thể kiểm tra trước khi tạo hoặc xử lý mảng:

~~~java
Class<?> arrayClass = ints.getClass();
System.out.println(arrayClass.isArray());                       // true
System.out.println(arrayClass.getComponentType().isPrimitive()); // true
~~~

Đây là **đoạn bổ sung** dùng biến `ints` đã khai báo trong `main` ở ví dụ trên.

## 5. Khi API bắt buộc nhận `Object[]`: chuyển đổi thực sự

Nếu cần giao tiếp với API có chữ ký `consume(Object[] values)`, chỉ ép kiểu là không đủ. Phải **tạo mảng tham chiếu mới** rồi boxing từng phần tử, hoặc dùng stream để tạo `Integer[]`.

File `BoxArrayDemo.java`:

~~~java
import java.util.Arrays;

public class BoxArrayDemo {
    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};

        Integer[] boxed = Arrays.stream(numbers)
                .boxed()
                .toArray(Integer[]::new);
        Object[] refs = boxed; // Hợp lệ: Integer[] là mảng tham chiếu.

        System.out.println(Arrays.toString(refs));

        refs[0] = 99;
        System.out.println(numbers[0]); // Mảng int[] gốc không đổi.
        System.out.println(boxed[0]);   // Mảng Integer[] mới đã đổi.

        int[] backToPrimitives = Arrays.stream(boxed)
                .mapToInt(Integer::intValue)
                .toArray();
        System.out.println(Arrays.toString(backToPrimitives));
    }
}
~~~

Chạy:

~~~bash
javac BoxArrayDemo.java
java BoxArrayDemo
~~~

Kết quả chuẩn:

~~~text
[1, 2, 3]
1
99
[99, 2, 3]
~~~

`boxed()` biến mỗi `int` thành đối tượng `Integer`; `toArray(Integer[]::new)` tạo **mảng mới**. Phép gán `Object[] refs = boxed` hợp lệ, nhưng mảng mới không chia sẻ các ô phần tử với `numbers`. Việc boxing có thêm chi phí bộ nhớ và thao tác đối tượng; khi tính toán số học thuần túy, thường nên tiếp tục dùng `int[]` hoặc `IntStream`.

### Chuyển mọi loại mảng thành `Object[]` khi cần

Phương thức dưới đây là **helper đặt bên trong một class**, không phải chương trình độc lập. Nó tạo bản sao một chiều; các phần tử nguyên thủy được boxing:

~~~java
import java.lang.reflect.Array;

static Object[] copyElements(Object source) {
    if (source == null || !source.getClass().isArray()) {
        throw new IllegalArgumentException("Expected an array");
    }

    int length = Array.getLength(source);
    Object[] result = new Object[length];
    for (int i = 0; i < length; i++) {
        result[i] = Array.get(source, i);
    }
    return result;
}
~~~

Ví dụ `copyElements(new int[]{4, 5})` trả về `Object[]` chứa hai `Integer`; `copyElements(new String[]{"a"})` trả về `Object[]` chứa `String`. Đây là **chuyển đổi và sao chép dữ liệu**, không phải cast `int[]`. Với mảng nhiều chiều, hàm chỉ sao chép **tầng ngoài**, không sao chép sâu các mảng con.

Nếu API hỗ trợ `Collection<Integer>`, Java 17 có thể dùng `Arrays.stream(numbers).boxed().toList()`; kết quả là danh sách không thể sửa cấu trúc qua `add`/`set`. Nếu cần tự tăng giảm số phần tử, cân nhắc `ArrayList<Integer>` thay vì trông đợi mảng Java đổi được `length`.

## 6. Bẫy liên quan thường gặp

### 6.1. `Arrays.asList(int[])` không boxing từng số

~~~java
int[] numbers = {1, 2, 3};

java.util.List<int[]> oneElement = java.util.Arrays.asList(numbers);
System.out.println(oneElement.size()); // 1

java.util.List<Integer> eachNumber =
        java.util.Arrays.stream(numbers).boxed().toList();
System.out.println(eachNumber.size()); // 3
~~~

`Arrays.asList` nhận các phần tử có **kiểu tham chiếu** qua varargs kiểu generic. Với `int[]`, nó xem toàn bộ mảng là **một đối tượng phần tử**, chứ không tách thành ba `Integer`. Đoạn trên là minh họa đặt trong một phương thức, không phải một class hoàn chỉnh.

### 6.2. Mảng hai chiều vẫn cần xét từng tầng

~~~java
int[][] matrix = {{1, 2}, {3, 4}};
Object[] outer = matrix; // Hợp lệ: phần tử ở tầng ngoài là int[].

System.out.println(outer.length);                 // 2
System.out.println(outer[0] instanceof Object[]); // false
~~~

Tầng ngoài là mảng tham chiếu; mỗi phần tử bên trong có runtime type `int[]`. Không thể dùng `(Object[]) outer[0]` để đọc các số trong mảng con. Muốn duyệt an toàn, gọi `Array.getLength(outer[0])` và `Array.get(outer[0], i)`, hoặc cast về đúng `int[]` nếu biết chắc kiểu.

### 6.3. Nhầm lẫn giữa covariance và boxing

Trong Java, `String[]` có thể gán cho `Object[]` do **array covariance**. Nhưng nếu gán một đối tượng không phải `String` qua tham chiếu `Object[]` này, JVM ném `ArrayStoreException`. Quy tắc covariance chỉ áp dụng cho **kiểu phần tử tham chiếu**, không biến `int[]` thành `Object[]`; cơ chế này cũng **không tự boxing** nguyên một mảng.

### 6.4. Dùng mảng nguyên thủy chỉ để in dữ liệu

Để in `int[]`, dùng trực tiếp `Arrays.toString(numbers)` vì thư viện đã có overload nhận `int[]`. Không cần tạo `Object[]`, không cần Reflection và không cần boxing cả mảng. `System.out.println(numbers)` tự nó không in danh sách giá trị phần tử.

## 7. Chọn giải pháp đúng theo ngữ cảnh

| Tình huống | Nên dùng | Tránh |
| --- | --- | --- |
| Truyền/giữ bất kỳ mảng nào mà chưa cần duyệt | `Object` | Tuyên bố mọi mảng là `Object[]` |
| Duyệt mảng có component type chỉ biết lúc chạy | `Array.getLength`, `Array.get` | Cast thẳng `(Object[]) array` |
| Biết chắc dữ liệu là mảng số nguyên nguyên thủy | `int[]`, `Arrays.stream(int[])` | Boxing không cần thiết |
| API buộc nhận mảng tham chiếu | `Integer[]` hoặc `Object[]` tạo từ dữ liệu đã boxing | Cast `int[]` |
| Cần danh sách có thể thay đổi kích thước | `ArrayList<Integer>` | Mong `int[]` tự tăng `length` |
| Chỉ cần in nội dung `int[]` | `Arrays.toString(int[])` | Cast để gọi `Arrays.toString(Object[])` |

## 8. Tự kiểm tra

1. Tại sao `Object a = new int[4]` hợp lệ nhưng `Object[] a = new int[4]` không hợp lệ? Vì mọi mảng là đối tượng, còn `Object[]` đòi mảng có phần tử thuộc kiểu tham chiếu.
2. Vì sao `(Object[]) (Object) new int[4]` vẫn thất bại? Kiểu tĩnh trung gian `Object` cho phép thử cast, nhưng kiểu runtime vẫn là `int[]`; JVM ném `ClassCastException`.
3. Muốn đọc giá trị thứ ba từ một `Object x` được xác định là mảng, cần gì? Dùng `Array.getLength(x)` kiểm tra chỉ số rồi `Array.get(x, 2)`; nếu thật sự là `int[]`, có thể cast sang `int[]` và đọc `[2]`.
4. Vì sao `Integer[]` tạo từ `int[]` không phản ánh thay đổi của mảng gốc? Vì đã tạo mảng khác và boxing các giá trị, không có các ô dữ liệu dùng chung.

**Ghi nhớ:** `int[]` là một `Object`, **không phải** `Object[]`. Trong Reflection, làm việc trực tiếp với `java.lang.reflect.Array` khi kiểu phần tử chưa biết; chỉ tạo `Integer[]`/`Object[]` mới khi yêu cầu API thực sự cần kiểu mảng tham chiếu.
