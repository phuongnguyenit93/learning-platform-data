# Primitive parameter type khác wrapper parameter type khi tra cứu thành viên bằng Reflection

## 1. Vấn đề cốt lõi

Trong Java, một tham số kiểu nguyên thủy (*primitive*) và một tham số kiểu lớp bao (*wrapper*) có **kiểu khai báo khác nhau**, dù mã Java thông thường có thể tự động boxing/unboxing khi gọi phương thức.

Ví dụ, hai khai báo sau là **hai overload hợp lệ**:

```java
public void handle(int count) { /* ... */ }
public void handle(Integer count) { /* ... */ }
```

Khi tra cứu bằng Reflection, chữ ký tham số được đối chiếu theo đối tượng `Class` tương ứng:

| Kiểu khai báo | Biểu diễn Reflection | `getTypeName()` | `isPrimitive()` |
| --- | --- | --- | --- |
| `int` | `int.class` | `int` | `true` |
| `Integer` | `Integer.class` | `java.lang.Integer` | `false` |
| `boolean` | `boolean.class` | `boolean` | `true` |
| `Boolean` | `Boolean.class` | `java.lang.Boolean` | `false` |
| `long` | `long.class` | `long` | `true` |
| `Long` | `Long.class` | `java.lang.Long` | `false` |

**Bất biến cần nhớ:** `int.class != Integer.class`. Thuật toán tìm thành viên theo danh sách `parameterTypes` không tự boxing/unboxing, không tự mở rộng kiểu số và không tự chọn overload tương tự trình biên dịch Java.

`Integer.TYPE` là hằng `Class<Integer>` đại diện cho kiểu primitive `int`, vì vậy `Integer.TYPE == int.class` là `true`. Tuy nhiên `Integer.TYPE` **không phải** `Integer.class`.

## 2. API nào chịu ảnh hưởng?

| API | Loại thành viên được tra cứu | Quy tắc với tham số |
| --- | --- | --- |
| `type.getMethod(name, parameterTypes...)` | Phương thức `public`, kể cả được kế thừa | Các `Class` tham số phải khớp chính xác |
| `type.getDeclaredMethod(name, parameterTypes...)` | Phương thức khai báo trực tiếp trong lớp, kể cả `private` | Khớp chính xác; không tìm ở lớp cha |
| `type.getConstructor(parameterTypes...)` | Constructor `public` của lớp | Khớp chính xác |
| `type.getDeclaredConstructor(parameterTypes...)` | Constructor khai báo trong lớp, kể cả không `public` | Khớp chính xác |

Giả sử lớp chỉ có `void onlyInt(int value)`:

```java
Example.class.getMethod("onlyInt", int.class);      // Tìm thấy
Example.class.getMethod("onlyInt", Integer.class);  // NoSuchMethodException
Example.class.getMethod("onlyInt", short.class);    // NoSuchMethodException
```

Không thể dùng việc Java cho phép truyền một `Integer` vào lời gọi `onlyInt(5)` hoặc có thể chuyển `short` thành `int` để suy ra rằng tra cứu Reflection sẽ tìm được phương thức.

## 3. Ví dụ hoàn chỉnh, chạy được trên Java 17+

Lưu mã sau thành tệp `PrimitiveVsWrapperReflection.java`:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

public class PrimitiveVsWrapperReflection {
    public static class Example {
        public Example(int initialValue) {
        }

        public void handle(int count) {
            System.out.println("int: " + count);
        }

        public void handle(Integer count) {
            System.out.println("Integer: " + count);
        }

        public void onlyInt(int count) {
        }

        private void hidden(long count) {
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("int == Integer: " + (int.class == Integer.class));
        System.out.println("Integer.TYPE == int.class: " + (Integer.TYPE == int.class));

        Method primitiveMethod = Example.class.getMethod("handle", int.class);
        Method wrapperMethod = Example.class.getMethod("handle", Integer.class);

        System.out.println("Primitive parameter: "
                + primitiveMethod.getParameterTypes()[0].getTypeName());
        System.out.println("Wrapper parameter: "
                + wrapperMethod.getParameterTypes()[0].getTypeName());

        Example example = new Example(0);
        primitiveMethod.invoke(example, Integer.valueOf(3));
        wrapperMethod.invoke(example, Integer.valueOf(4));

        try {
            Example.class.getMethod("onlyInt", Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("No method onlyInt(Integer)");
        }

        Constructor<Example> constructor = Example.class.getConstructor(int.class);
        System.out.println("Constructor parameter: "
                + constructor.getParameterTypes()[0].getTypeName());

        try {
            Example.class.getConstructor(Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("No constructor(Integer)");
        }

        Method privateMethod = Example.class.getDeclaredMethod("hidden", long.class);
        System.out.println("Private method parameter: "
                + privateMethod.getParameterTypes()[0].getTypeName());
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac PrimitiveVsWrapperReflection.java
java PrimitiveVsWrapperReflection
```

Kết quả chuẩn:

```text
int == Integer: false
Integer.TYPE == int.class: true
Primitive parameter: int
Wrapper parameter: java.lang.Integer
int: 3
Integer: 4
No method onlyInt(Integer)
Constructor parameter: int
No constructor(Integer)
Private method parameter: long
```

Ý nghĩa từng bước:

1. `int.class` và `Integer.class` là hai đối tượng `Class` không đồng nhất; `Integer.TYPE` chính là `int.class`.
2. Hai lời gọi `getMethod("handle", ...)` trả về hai `Method` khác nhau, vì chữ ký khai báo `(int)` và `(Integer)` khác nhau.
3. `getParameterTypes()` phản ánh **kiểu tham số trong khai báo**, không phản ánh kiểu dữ liệu truyền vào khi gọi.
4. `getMethod("onlyInt", Integer.class)` ném `NoSuchMethodException`; tên có thật nhưng chữ ký `(Integer)` không tồn tại.
5. Constructor `Example(int)` tra được bằng `int.class`, còn `Integer.class` không khớp.
6. `getDeclaredMethod("hidden", long.class)` tìm thấy phương thức `private` khai báo tại lớp; ví dụ chỉ tra cứu metadata, không gọi phương thức riêng tư.

## 4. Phân biệt **tra cứu** và **gọi thực thi**

Đây là hai giai đoạn với quy tắc khác nhau:

```text
Tra cứu: Class.getMethod("handle", int.class)
    → tìm đúng thành viên có tham số khai báo int

Thực thi: Method.invoke(instance, Integer.valueOf(3))
    → sau khi đã tìm thấy Method, đối số Integer có thể được unbox thành int
```

- **Lúc tra cứu:** `getMethod`/`getConstructor` đối chiếu kiểu khai báo chính xác; không boxing/unboxing, không primitive widening (chẳng hạn `short.class` không khớp `int.class`).
- **Lúc `Method.invoke`/`Constructor.newInstance`:** Reflection có thể unbox giá trị wrapper cho tham số primitive và áp dụng **widening primitive** hợp lệ (ví dụ một giá trị `Integer` cho tham số `long`). Không áp dụng narrowing primitive tùy ý (ví dụ `Long` sang `int`).
- **Với tham số wrapper:** `Integer` là kiểu tham chiếu, nhận `null` và các giá trị tham chiếu phù hợp. Nếu khai báo tham số là `int`, truyền `null` tại lúc invoke là không hợp lệ và gây `IllegalArgumentException`. Không có `null` nào thuộc kiểu primitive.
- **Với overload:** sau khi lấy được một đối tượng `Method`, `invoke` thực thi đúng phương thức đã chọn. Nó không tự chọn lại overload `handle(Integer)` chỉ vì đối số runtime là `Integer`.

Vì vậy, lời gọi Java `example.onlyInt(Integer.valueOf(3))` có thể biên dịch nhờ unboxing, nhưng `Example.class.getMethod("onlyInt", Integer.class)` vẫn thất bại.

## 5. Kiểm tra và xây dựng chữ ký đúng

Khi làm việc với code không rõ khai báo, liệt kê và quan sát `Class` của từng tham số:

```java
for (Method method : Example.class.getDeclaredMethods()) {
    if (method.getName().equals("handle")) {
        for (Class<?> parameter : method.getParameterTypes()) {
            System.out.println(parameter.getTypeName()
                    + ", primitive=" + parameter.isPrimitive());
        }
    }
}
```

Hai dòng dữ liệu tương ứng sẽ cho biết một tham số là `int, primitive=true` và tham số còn lại là `java.lang.Integer, primitive=false` (không dựa vào thứ tự của mảng phương thức trả về).

Nếu biết chữ ký nguyên thủy, hãy truyền `int.class` hoặc `Integer.TYPE`; nếu chữ ký dùng wrapper, hãy truyền `Integer.class`. Tương tự với `long.class`/`Long.TYPE` và `Long.class`, `boolean.class`/`Boolean.TYPE` và `Boolean.class`.

Không dùng `Class.forName("int")` để lấy `Class` cho primitive: tên `int` không phải tên nhị phân của lớp có thể nạp bằng cách đó. Dùng trực tiếp `int.class` hoặc `Integer.TYPE`.

## 6. Các tình huống gần giống dễ nhầm

- **Mảng primitive và mảng wrapper:** `int[].class` khác `Integer[].class`; `int[]` không được tự chuyển thành `Integer[]`. Mặc dù bản thân cả hai mảng đều là kiểu tham chiếu, `getComponentType()` của chúng lần lượt là `int.class` và `Integer.class`.
- **Varargs trong khai báo:** `void accept(int... values)` có một tham số kiểu `int[]`; tra cứu bằng `getMethod("accept", int[].class)`, không dùng `int.class`.
- **Kiểu trả về:** `getMethod` không nhận kiểu trả về làm tiêu chí tìm kiếm; `getReturnType()` giúp kiểm tra sau khi tìm thấy phương thức. Phân biệt primitive và wrapper ở đây đang xét **tham số**.
- **Phạm vi truy cập:** đổi từ `getMethod` sang `getDeclaredMethod` chỉ điều chỉnh phạm vi tìm kiếm `public`/khai báo trực tiếp, không làm `Integer.class` tự khớp `int.class`.

## 7. Những lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `NoSuchMethodException` dù thấy `method(int)` trong mã nguồn | Tra bằng `Integer.class` | Dùng `int.class` |
| Không tìm được constructor `Example(int)` | Tra bằng `Integer.class` hoặc `short.class` | Dùng `getConstructor(int.class)` |
| Đã tìm thấy `Method` nhưng `invoke` lỗi đối số | Giá trị runtime không chuyển đổi hợp lệ sang kiểu khai báo; ví dụ `null` cho `int` | Kiểm tra `getParameterTypes()`, giá trị và luật chuyển đổi khi invoke |
| Tra `private void hidden(long)` bằng `getMethod` bị lỗi | `getMethod` chỉ xét thành viên `public` | Dùng `getDeclaredMethod("hidden", long.class)` nếu cần tra cứu khai báo |
| Nhầm `Integer.TYPE` là `Integer.class` | `TYPE` trỏ tới primitive `int` | Phân biệt `Integer.TYPE == int.class` với `Integer.class` |

**Tự kiểm tra:** Với lớp chỉ có `void run(long value)`, cả `getDeclaredMethod("run", Long.class)` lẫn `getDeclaredMethod("run", int.class)` đều không tìm thấy. Chỉ `getDeclaredMethod("run", long.class)` khớp; sau đó, lời gọi `invoke(target, Integer.valueOf(5))` có thể thành công nhờ unboxing `Integer` thành `int` rồi widening thành `long`.

**Ghi nhớ:** Tra cứu Reflection dựa trên **kiểu tham số đã khai báo**, còn chuyển đổi boxing/unboxing của **đối số khi gọi** là một cơ chế khác.