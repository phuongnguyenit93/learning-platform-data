# Lấy đối tượng `Class` bằng class literal trong Java

## 1. Class literal là gì?

Trong Java, **class literal** là biểu thức `TênKiểu.class`, dùng để lấy đối tượng `java.lang.Class` đại diện cho **một kiểu đã biết ngay trong mã nguồn**. Nó mô tả một lớp, interface, enum, annotation, kiểu nguyên thủy hoặc kiểu mảng. Toán tử `.class` không tạo instance của lớp.

```java
Class<String> stringClass = String.class;
Class<Integer> integerClass = Integer.class;
Class<?> primitiveClass = int.class;
Class<?> arrayClass = String[].class;
```

Với cùng một kiểu do cùng class loader định nghĩa, JVM sử dụng cùng một đối tượng `Class`. Class literal hữu ích khi cần truyền một kiểu đã biết cho API, thay vì tìm lớp từ chuỗi ký tự tại runtime.

- `new String("Java")` tạo **đối tượng dữ liệu** thuộc lớp `String`.
- `String.class` lấy **đối tượng mô tả kiểu** `String`; không tạo `String` mới.
- `text.getClass()` lấy **kiểu runtime của instance `text`**; cần `text` không phải `null`.

## 2. Cú pháp và loại kiểu có thể dùng

| Biểu thức | Kiểu được mô tả | Lưu ý |
| --- | --- | --- |
| `String.class` | Lớp `java.lang.String` | Gán cho `Class<String>`. |
| `Runnable.class` | Interface `Runnable` | Interface cũng có đối tượng `Class`. |
| `Override.class` | Annotation `Override` | Annotation là kiểu interface đặc biệt. |
| `Thread.State.class` | Enum `Thread.State` | Áp dụng cho kiểu enum và kiểu lồng. |
| `int.class`, `boolean.class` | Kiểu nguyên thủy | Khác wrapper `Integer.class`, `Boolean.class`. |
| `void.class` | Kiểu `void` | Dùng để biểu diễn kiểu trả về `void`. |
| `String[].class` | Mảng `String[]` | Khác kiểu phần tử `String.class`. |
| `int[][].class` | Mảng hai chiều `int[][]` | Mỗi số chiều là một kiểu mảng khác nhau. |
| `java.util.List.class` | Interface `List` | Không mang tham số generic `String`. |

**Không hợp lệ:** `List<String>.class`, vì đối số kiểu generic không tạo một `Class` riêng ở runtime. Dùng `List.class`; nếu cần mô tả tham số `String`, cần cơ chế `Type`/`ParameterizedType` tương ứng, không thể lấy từ `List.class` đơn thuần.

Cũng không thể dùng `myObject.class` để lấy kiểu của biến. Dùng `myObject.getClass()` đối với instance, hoặc `MyType.class` khi biết tên kiểu từ trước.

## 3. Phân biệt class literal với cách lấy `Class` khác

| Cách lấy `Class` | Kiểu được quyết định khi nào? | Cần instance? | Đặc điểm |
| --- | --- | --- | --- |
| `Animal.class` | Lúc biên dịch | Không | Luôn là `Animal`, đúng kiểu ghi trong source. |
| `animal.getClass()` | Lúc chạy | Có | Có thể là lớp con `Dog` nếu `animal` đang trỏ đến `Dog`. |
| `Class.forName("pkg.Animal")` | Lúc chạy, theo tên chuỗi | Không | Có thể ném `ClassNotFoundException`; bản một tham số mặc định yêu cầu khởi tạo lớp. |

Với `Animal animal = new Dog();`, `Animal.class` đại diện `Animal`, còn `animal.getClass()` đại diện `Dog`. Chúng đều là đối tượng `Class`, nhưng chỉ trường hợp thứ hai phụ thuộc instance thực tế.

Một điểm quan trọng: **chỉ tham chiếu `SomeType.class` không kích hoạt khởi tạo lớp**, nên không chạy `static initializer` chỉ vì lấy literal. Những hành động khác, như gọi phương thức `static`, có thể kích hoạt khởi tạo lớp. Phân biệt ba việc: lấy metadata kiểu, khởi tạo lớp và tạo instance.

## 4. Ví dụ Java 17+ biên dịch/chạy độc lập

Lưu mã sau thành `ClassLiteralDemo.java`:

```java
import java.util.List;

public class ClassLiteralDemo {
    static class Animal {}

    static class Dog extends Animal {}

    static class Lazy {
        static {
            System.out.println("Lazy đã khởi tạo");
        }

        static void ping() {}
    }

    public static void main(String[] args) {
        Animal animal = new Dog();

        Class<Animal> declaredType = Animal.class;
        Class<?> runtimeType = animal.getClass();

        System.out.println("declared=" + declaredType.getSimpleName());
        System.out.println("runtime=" + runtimeType.getSimpleName());
        System.out.println("isInstance=" + declaredType.isInstance(animal));
        System.out.println("assignable="
                + declaredType.isAssignableFrom(Dog.class));

        System.out.println("string=" + (String.class == "Java".getClass()));
        System.out.println("primitive=" + (int.class == Integer.TYPE));
        System.out.println("wrapper=" + (int.class == Integer.class));
        System.out.println("array=" + String[][].class.getTypeName());
        System.out.println("interface=" + List.class.getTypeName());

        Class<?> lazyType = Lazy.class;
        System.out.println("literal=" + lazyType.getSimpleName());
        Lazy.ping();
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac ClassLiteralDemo.java
java ClassLiteralDemo
```

Stdout dự kiến:

```text
declared=Animal
runtime=Dog
isInstance=true
assignable=true
string=true
primitive=true
wrapper=false
array=java.lang.String[][]
interface=java.util.List
literal=Lazy
Lazy đã khởi tạo
```

Giải thích:

1. `declared=Animal` và `runtime=Dog` chứng minh `.class` chỉ rõ kiểu ở source, còn `getClass()` phản ánh lớp runtime của instance.
2. `isInstance=true`: đối tượng `Dog` là một `Animal`. `isAssignableFrom=true`: một `Dog` có thể gán cho biến kiểu `Animal`. Luôn chú ý hướng `Animal.class.isAssignableFrom(Dog.class)`.
3. `String.class == "Java".getClass()` là `true` vì cùng đại diện `String`.
4. `int.class == Integer.TYPE` là `true` vì `TYPE` đại diện primitive `int`. Nhưng `int.class == Integer.class` là `false`, bởi primitive khác wrapper.
5. `String[][].class.getTypeName()` mô tả kiểu mảng hai chiều; `List.class` mô tả interface `List`.
6. `Lazy.class` chưa chạy khối `static`. Dòng `Lazy đã khởi tạo` chỉ xuất hiện sau khi gọi `Lazy.ping()`.

## 5. Tính an toàn kiểu: `Class<T>` và `Class<?>`

`Class<T>` ghi nhận kiểu `T` ở mức khai báo, còn `Class<?>` thích hợp khi kiểu cụ thể chưa biết hoặc không cần ràng buộc.

```java
Class<String> exact = String.class;
Class<?> unknown = int[].class;
Class<? extends Number> numeric = Integer.class;

// Lỗi biên dịch vì kiểu không tương thích:
// Class<String> wrong = Integer.class;
```

Ví dụ `Class<String>` giúp compiler ngăn gán nhầm metadata của `Integer` cho biến muốn đại diện `String`.

**Bẫy primitive:** về generic, Java gán cho `int.class` kiểu `Class<Integer>` ở compile time, nhưng đối tượng đó **vẫn đại diện primitive `int`**. Vì vậy `int.class` và `Integer.class` không phải cùng `Class`. Có thể phân biệt bằng `int.class.isPrimitive()` (`true`) và `Integer.class.isPrimitive()` (`false`).

## 6. Ứng dụng khi dùng API reflection

**Truyền type token cho API.** Một hàm nhận `Class<T>` để biết rõ kiểu kết quả có thể được gọi bằng `String.class`, `User.class`, v.v. Compiler kiểm tra tên lớp, IDE hỗ trợ điều hướng và đổi tên.

Ví dụ dưới đây chỉ minh họa cách dùng `Class.cast` để kiểm tra/ép kiểu đối tượng đã phù hợp; đây **không phải** bộ chuyển đổi dữ liệu giữa hai kiểu bất kỳ:

```java
static <T> T asType(Object value, Class<T> targetType) {
    return targetType.cast(value);
}

// Đặt trong một phương thức khi sử dụng:
String result = asType("Java", String.class);
```

Nếu `value` không tương thích với `targetType`, `cast` ném `ClassCastException`. Ví dụ trên có minh họa từng đoạn, **không phải** một chương trình `main` độc lập.

**Kiểm tra quan hệ kiểu và metadata.** Sau khi có `Class`, bạn có thể gọi:

- `SomeType.class.isInstance(object)` để kiểm tra một instance thuộc kiểu hoặc kiểu con phù hợp.
- `Base.class.isAssignableFrom(Sub.class)` để kiểm tra kiểu `Sub` có thể gán cho biến kiểu `Base`.
- `SomeType.class.getDeclaredMethods()` để lấy các phương thức khai báo trực tiếp trong lớp, không mặc định gồm phương thức kế thừa.

Class literal cung cấp **đối tượng mô tả kiểu**; các API sử dụng nó để thực hiện tra cứu hay kiểm tra. Các kỹ thuật truy cập thành viên và thực thi reflection chi tiết thuộc các bài khác.

## 7. Lỗi hay gặp

- **Nhầm `.class` với `new`:** `Person.class` không gọi constructor, không tạo `Person` mới.
- **Nhầm kiểu khai báo với kiểu runtime:** `Base.class` không thay đổi theo instance được gán vào biến `Base`; `base.getClass()` thì có.
- **Nhầm primitive và wrapper:** `int.class != Integer.class` dù `Integer.TYPE == int.class`.
- **Dùng tham số generic trong literal:** `List<String>.class` không hợp lệ; `List.class` chỉ mô tả `List` chưa mang `<String>`.
- **Gọi `getClass()` trên `null`:** phát sinh `NullPointerException`; `SomeType.class` không cần instance.
- **Suy luận tên mảng từ `getName()`:** `String[].class.getName()` cho dạng JVM `[Ljava.lang.String;`, còn `getTypeName()` cho `java.lang.String[]`.
- **So sánh tên mà bỏ qua class loader:** danh tính class trong JVM phụ thuộc tên nhị phân **và class loader định nghĩa**. Hai loader khác nhau có thể định nghĩa hai class khác nhau cùng tên.
- **Tưởng class literal chạy khối `static`:** lấy `SomeType.class` không tự khởi tạo lớp.

## 8. Tự kiểm tra

**Câu 1.** Với `Object value = "abc";`, `Object.class` và `value.getClass()` có giống nhau không?

**Đáp án:** Không. Cái thứ nhất đại diện `Object`, cái thứ hai là `String`.

**Câu 2.** `int[].class == int.class` trả về `true` hay `false`?

**Đáp án:** `false`, vì mảng `int[]` và primitive `int` là hai kiểu khác nhau.

**Câu 3.** Vì sao không thể viết `List<String>.class`?

**Đáp án:** Class literal mô tả `Class` của một kiểu được biểu diễn trực tiếp tại runtime; tham số generic `<String>` không tạo lớp runtime riêng vì type erasure. Dùng `List.class` và cơ chế `Type` khi cần thông tin tham số hóa.

**Ghi nhớ:** Dùng `TênKiểu.class` khi **biết sẵn tên kiểu trong mã nguồn** và cần metadata của chính kiểu đó. Dùng `instance.getClass()` khi cần **kiểu runtime thực tế của đối tượng**.