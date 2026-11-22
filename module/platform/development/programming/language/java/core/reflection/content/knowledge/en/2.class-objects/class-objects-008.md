# Vì sao `int.class` khác `Integer.class`?

Trong Java, `int` là **kiểu nguyên thủy** (primitive type), còn `Integer` là **lớp tham chiếu** (reference type) dùng để biểu diễn một giá trị số nguyên dưới dạng đối tượng. Vì vậy, `int.class` và `Integer.class` trả về **hai đối tượng `Class` khác nhau**, mô tả hai kiểu Java khác nhau. Cơ chế tự động đóng hộp (autoboxing) không biến chúng thành cùng một kiểu.

## 1. `.class` thực sự đại diện cho điều gì?

Trong Java, biểu thức `TênKiểu.class` là *class literal*: nó trả về đối tượng `java.lang.Class` đại diện cho kiểu được nêu. Cú pháp này áp dụng được cả cho lớp, interface, mảng và kiểu nguyên thủy.

- `int.class`: đối tượng `Class` đại diện cho **kiểu nguyên thủy `int`**. Dù tên API là `Class`, `int` không phải một lớp thông thường, không có đối tượng kiểu `int`, không có constructor hay superclass.
- `Integer.class`: đối tượng `Class` đại diện cho **lớp `java.lang.Integer`**. `Integer` là một lớp `final` kế thừa `Number`, dùng với các đối tượng và cung cấp phương thức như `parseInt`, `valueOf`, `compare`.
- Cả hai có kiểu biểu thức tương thích với `Class<?>`, nhưng mỗi đối tượng `Class` lưu thông tin về **một kiểu được biểu diễn riêng biệt**.

Điều này tương tự việc `String.class` khác `Object.class`: cùng được biểu diễn bằng API `Class` không có nghĩa là cùng một kiểu.

## 2. So sánh qua Reflection

| Phép kiểm tra | `int.class` | `Integer.class` |
| --- | --- | --- |
| Kiểu Java được mô tả | `int` nguyên thủy | `java.lang.Integer` tham chiếu |
| `getName()` | `"int"` | `"java.lang.Integer"` |
| `isPrimitive()` | `true` | `false` |
| `getSuperclass()` | `null` | `Number.class` |
| `isInstance(Integer.valueOf(10))` | `false` | `true` |
| Có thể dùng làm kiểu đối tượng trong `List<T>` | Không: `List<int>` không hợp lệ | Có: `List<Integer>` hợp lệ |
| Dùng trong chữ ký phương thức | Tham số/giá trị trả về `int` | Tham số/giá trị trả về `Integer` |

Một chi tiết thường gây nhầm lẫn là hằng `Integer.TYPE`: **`Integer.TYPE == int.class`**, trong khi **`Integer.TYPE != Integer.class`**. Trường `TYPE` của các lớp wrapper lưu đối tượng `Class` của kiểu nguyên thủy tương ứng; nó không phải một bí danh của `Integer.class`.

### Ví dụ Java 17+ chạy độc lập

Lưu toàn bộ mã sau trong tệp `IntVsIntegerClass.java`:

~~~java
import java.lang.reflect.Method;

public class IntVsIntegerClass {
    public static void accept(int value) {
    }

    public static void accept(Integer value) {
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> primitive = int.class;
        Class<?> wrapper = Integer.class;

        System.out.println(primitive == wrapper);
        System.out.println(primitive.getName());
        System.out.println(wrapper.getName());
        System.out.println(primitive.isPrimitive());
        System.out.println(wrapper.isPrimitive());
        System.out.println(primitive.getSuperclass());
        System.out.println(wrapper.getSuperclass().getName());
        System.out.println(Integer.TYPE == primitive);
        System.out.println(wrapper.isInstance(Integer.valueOf(10)));
        System.out.println(primitive.isInstance(Integer.valueOf(10)));

        Method primitiveMethod =
                IntVsIntegerClass.class.getMethod("accept", int.class);
        Method wrapperMethod =
                IntVsIntegerClass.class.getMethod("accept", Integer.class);

        System.out.println(primitiveMethod.equals(wrapperMethod));
        System.out.println(primitiveMethod.getParameterTypes()[0].getName());
        System.out.println(wrapperMethod.getParameterTypes()[0].getName());
    }
}
~~~

Biên dịch và chạy trong terminal có JDK 17 trở lên:

~~~bash
javac IntVsIntegerClass.java
java IntVsIntegerClass
~~~

Kết quả chuẩn:

~~~text
false
int
java.lang.Integer
true
false
null
java.lang.Number
true
true
false
false
int
java.lang.Integer
~~~

Giải thích những dòng trọng tâm:

1. `primitive == wrapper` là `false` vì hai đối tượng `Class` biểu diễn hai kiểu khác nhau.
2. `isPrimitive()` chỉ đúng cho `int.class`; `Integer.class` mô tả một lớp đối tượng thực sự.
3. `getSuperclass()` của kiểu nguyên thủy trả `null`; superclass trực tiếp của `Integer` là `Number`.
4. `isInstance(Object)` kiểm tra liệu **đối tượng truyền vào** có là instance của kiểu được mô tả hay không. Một đối tượng `Integer` không thể là instance của một kiểu nguyên thủy, nên `int.class.isInstance(...)` trả `false`.
5. Reflection tìm hai phương thức `accept` khác nhau: một nhận `int`, một nhận `Integer`. Chúng không trùng chữ ký.

## 3. Vì sao autoboxing không làm hai `Class` bằng nhau?

**Autoboxing** cho phép trình biên dịch chuyển một giá trị `int` thành một tham chiếu `Integer` khi ngữ cảnh cần kiểu wrapper; **unboxing** chuyển ngược lại thành giá trị nguyên thủy. Ví dụ:

~~~java
int number = 42;
Integer boxed = number;      // autoboxing, tương đương về ý nghĩa với Integer.valueOf(number)
int again = boxed;           // unboxing, tương đương boxed.intValue()
~~~

Đây là **phép chuyển đổi giá trị khi biên dịch/thực thi**, không phải quan hệ kế thừa, không tạo sự đồng nhất giữa hai kiểu và không thay đổi đối tượng `Class`. Bởi vậy:

- `int.class == Integer.class` vẫn là `false`.
- `Integer.class.isAssignableFrom(int.class)` là `false` và `int.class.isAssignableFrom(Integer.class)` cũng là `false`; API này kiểm tra khả năng gán theo quan hệ kiểu tham chiếu, không xem autoboxing là kế thừa.
- Biến `int` không có phương thức `getClass()`; viết `number.getClass()` khi `number` là `int` gây lỗi biên dịch. Muốn truy vấn kiểu nguyên thủy, dùng `int.class` hoặc `Integer.TYPE`.
- Khi `boxed` là một đối tượng `Integer`, `boxed.getClass() == Integer.class` là `true` (nếu `boxed` khác `null`).

Cần chú ý `Integer` có thể chứa `null`, còn `int` không thể. Unboxing giá trị `null` ném `NullPointerException`:

~~~java
Integer missing = null;
// int value = missing; // Nếu thực thi sẽ ném NullPointerException.
~~~

Ví dụ chú thích ở trên minh họa rủi ro, không phải một chương trình riêng.

## 4. Tác động trực tiếp khi dùng Reflection

### 4.1. Tra cứu method phải dùng đúng kiểu tham số đã khai báo

`Class.getMethod(String, Class<?>...)` và `Class.getDeclaredMethod(String, Class<?>...)` tra cứu **đúng chữ ký tham số**. Nếu có phương thức `process(int)`, lời gọi `getMethod("process", Integer.class)` không tự chuyển sang `getMethod("process", int.class)`.

Trong ví dụ độc lập ở mục 2, hai cách tìm dưới đây trỏ đến hai overload riêng:

~~~java
Method primitiveMethod =
        IntVsIntegerClass.class.getMethod("accept", int.class);
Method wrapperMethod =
        IntVsIntegerClass.class.getMethod("accept", Integer.class);
~~~

Nếu lớp chỉ khai báo overload `accept(int)`, truy vấn bằng `Integer.class` sẽ ném `NoSuchMethodException`. Quy tắc tương tự áp dụng khi so kiểu trả về bằng `Method.getReturnType()`, kiểu trường bằng `Field.getType()` và kiểu tham số bằng `Method.getParameterTypes()`.

**Phân biệt lúc tra cứu với lúc gọi:** `Method.invoke` có thể tự unbox một đối tượng `Integer` để truyền cho tham số `int` (và thực hiện một số chuyển đổi primitive hợp lệ) khi gọi phương thức đã tìm thấy. Điều đó không làm thay đổi chữ ký hay kết quả của `getMethod`.

### 4.2. Không dùng `Class.forName("int")` để lấy kiểu nguyên thủy

`Class.forName("java.lang.Integer")` tra cứu được lớp wrapper theo tên đầy đủ. Nhưng `Class.forName("int")` không nhận tên nguyên thủy theo cách đó và ném `ClassNotFoundException`. Khi cần `Class` của primitive, hãy lấy trực tiếp bằng `int.class` hoặc `Integer.TYPE`. Khi đọc một kiểu từ Reflection, dùng `isPrimitive()` để phân biệt.

### 4.3. Kiểu mảng cũng không giống nhau

`int[].class` và `Integer[].class` đều có `isArray() == true`, nhưng là hai lớp mảng khác nhau. `getComponentType()` lần lượt cho `int.class` và `Integer.class`. Một mảng `int[]` chứa phần tử primitive; một mảng `Integer[]` chứa tham chiếu đến các đối tượng `Integer` (có thể có phần tử `null`).

Không thể chuyển trực tiếp `int[]` thành `Integer[]` bằng autoboxing; muốn đổi phải chuyển từng phần tử.

## 5. Cách chọn đúng `Class` trong mã thực tế

- **Chữ ký khai báo primitive** (ví dụ `void setAge(int age)`, `int getCount()`, `Field` có kiểu `int`): dùng `int.class` khi so hoặc tra cứu qua Reflection.
- **Chữ ký khai báo wrapper** (ví dụ `void setAge(Integer age)`, `Integer findCount()`, trường có kiểu `Integer`): dùng `Integer.class`.
- **Framework/mapper xử lý cả hai dạng:** có thể viết logic quy đổi chủ động từ `int.class` sang `Integer.class` (và ngược lại) nếu bài toán muốn xem chúng tương ứng; đừng mặc định `Class.equals` hoặc `isAssignableFrom` thực hiện việc quy đổi này.
- **Cấu trúc dữ liệu generic:** dùng `Integer` vì type argument của generics phải là kiểu tham chiếu. Với dữ liệu số nguyên lớn cần tránh overhead đối tượng, mảng `int[]` có thể phù hợp hơn `Integer[]`; chọn theo yêu cầu về `null`, API và hiệu năng thực tế.

## 6. Lỗi thường gặp và cách tự kiểm tra

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`int.class` là `Integer.class` sau boxing.” | Boxing chuyển **giá trị**, không thay danh tính kiểu. |
| “`Integer.TYPE` là `Integer.class`.” | `Integer.TYPE` chính là `int.class`. |
| “`getMethod` tự áp dụng boxing để tìm overload.” | Phải chỉ rõ `int.class` hoặc `Integer.class` theo chữ ký đã khai báo. |
| “Mọi giá trị `int` đều có `getClass()`.” | Primitive không phải object; dùng class literal. |
| “`isAssignableFrom` trả true vì Java tự boxing.” | Kiểm tra này không coi boxing là quan hệ gán kiểu tham chiếu. |
| “`int[].class` và `Integer[].class` giống nhau.” | Thành phần lần lượt là primitive và wrapper; hai loại mảng độc lập. |

Hãy tự dự đoán trước khi thử trên Java 17:

~~~java
System.out.println(int.class == Integer.TYPE);              // true
System.out.println(int.class.isPrimitive());                // true
System.out.println(Integer.class.isPrimitive());            // false
System.out.println(int[].class.getComponentType() == int.class); // true
System.out.println(Integer.class.isAssignableFrom(int.class));  // false
~~~

Đoạn cuối là các lệnh minh họa để đặt **bên trong một phương thức** (như `main`); nó không phải tệp Java độc lập.

**Ghi nhớ:** `int.class` nói về **kiểu giá trị nguyên thủy `int`**; `Integer.class` nói về **lớp đối tượng `Integer`**. Java hỗ trợ chuyển đổi giữa giá trị của chúng trong một số ngữ cảnh, nhưng Reflection vẫn phân biệt chính xác hai kiểu.