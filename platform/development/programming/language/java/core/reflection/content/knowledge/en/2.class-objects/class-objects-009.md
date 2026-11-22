# Không tạo `Class` bằng constructor thông thường

## 1. Vấn đề nằm ở đâu?

Trong Java Reflection, `java.lang.Class<T>` là **đối tượng mô tả một kiểu tại runtime**: tên kiểu, modifier, superclass, interface, method, field, constructor, annotation, v.v. Mỗi biến kiểu `Class<?>` giữ một tham chiếu đến metadata của kiểu, không phải một đối tượng nghiệp vụ thuộc kiểu đó.

Ví dụ, ba biểu thức dưới đây có ý nghĩa khác nhau:

```java
Person person = new Person();        // Tạo một instance Person
Class<Person> type = Person.class;    // Lấy đối tượng Class mô tả Person
Class<?> runtimeType = person.getClass(); // Lấy Class của instance có sẵn
```

Nếu viết:

```java
Class<?> type = new Class<>(); // Lỗi biên dịch
```

thì Java không cho phép. **`java.lang.Class` không cung cấp constructor `public` để mã ứng dụng tự tạo một đối tượng `Class` bằng `new`.** JVM quản lý các đối tượng này trong quá trình nạp/định nghĩa kiểu. Tự tạo một `Class` tùy ý sẽ phá vỡ mối liên hệ giữa metadata và định nghĩa kiểu mà JVM thực sự biết, kiểm tra và thực thi.

Đây là điểm khác biệt quan trọng: **không được `new Class(...)`** không có nghĩa là **không được `new Person(...)`**. Ta vẫn khởi tạo instance của một lớp bình thường bằng constructor của chính lớp đó khi constructor cho phép.

## 2. Vì sao JVM quản lý đối tượng `Class`?

Khi runtime cần biết một kiểu, JVM sử dụng cơ chế nạp, liên kết và (khi điều kiện thích hợp xảy ra) khởi tạo lớp. Đối tượng `Class` là cửa ngõ phản ánh định nghĩa kiểu mà runtime đã nhận diện.

- `Class` biểu diễn **kiểu**, còn `new Person()` tạo **instance** của kiểu `Person`.
- Mã nguồn không thể tự cung cấp các thông tin nội bộ và tính hợp lệ của kiểu bằng cách gọi `new Class()`.
- Với cùng một kiểu được định nghĩa bởi cùng một **defining class loader**, các cách lấy `Class` thông thường tham chiếu cùng một đối tượng `Class`. Hai class loader khác nhau có thể định nghĩa hai kiểu riêng biệt dù cùng tên nhị phân.
- Nạp lớp (*loading*), liên kết (*linking*) và khởi tạo lớp (*initialization*) là các bước khác nhau; việc nhận được `Class` không luôn đồng nghĩa static initializer của kiểu đã chạy.

Hãy hiểu cụm “`Class` không có constructor thông thường” theo hợp đồng API: **không có constructor công khai cho ứng dụng gọi**. Không cần dựa vào số lượng hoặc chữ ký constructor nội bộ của implementation JDK để giải thích cơ chế này.

## 3. Các cách hợp lệ để lấy một đối tượng `Class`

| Cách | Ví dụ | Khi nào dùng? |
| --- | --- | --- |
| Class literal | `Person.class` | Đã biết kiểu tại thời điểm biên dịch; an toàn và rõ ràng. |
| `Object.getClass()` | `person.getClass()` | Đã có đối tượng và cần kiểu runtime thực tế của nó. |
| `Class.forName(String)` | `Class.forName("com.example.Person")` | Chỉ có tên nhị phân của kiểu dưới dạng chuỗi, thường gặp ở cấu hình/plugin; có thể ném `ClassNotFoundException`. |
| `Class.forName(String, boolean, ClassLoader)` | `Class.forName(name, false, loader)` | Cần chọn class loader và kiểm soát việc khởi tạo lớp. |
| `ClassLoader.loadClass(String)` | `loader.loadClass(name)` | Muốn yêu cầu class loader đã chọn tìm/nạp kiểu; thông thường không chủ động khởi tạo lớp ở bước này. |

Cần phân biệt:

- `Person.class` là **class literal**, không phải lời gọi constructor, không tạo `Person` và bản thân biểu thức đó không kích hoạt khởi tạo `Person`.
- `person.getClass()` trả về kiểu runtime thực sự. Với `Person` có subclass, giá trị này có thể khác `Person.class`. Nếu `person == null`, lời gọi gây `NullPointerException`.
- `Class.forName(String)` dùng tên nhị phân (*binary name*) và mặc định yêu cầu khởi tạo lớp được tìm thấy; tùy trường hợp có thể phát sinh lỗi nạp/khởi tạo. Dạng ba tham số với `initialize = false` tránh yêu cầu khởi tạo tại lời gọi đó.
- `ClassLoader.loadClass` và `Class.forName` xử lý tên kiểu và loader; chúng **không gọi constructor instance** của lớp được mô tả.
- Khi biết kiểu qua chuỗi, cần xử lý trường hợp không tìm thấy lớp; không suy luận rằng một tên chuỗi bất kỳ đều hợp lệ.

## 4. Ví dụ chạy được: ba đường dẫn về cùng metadata

Lưu nội dung sau thành **`ClassMetadataDemo.java`**:

```java
public class ClassMetadataDemo {
    static class Person {
        final String name;

        Person(String name) {
            this.name = name;
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        Class<Person> fromLiteral = Person.class;

        Person person = new Person("Lan");
        Class<?> fromObject = person.getClass();

        // getName() trả về tên nhị phân chính xác,
        // kể cả khi Person là nested class.
        Class<?> fromName = Class.forName(Person.class.getName());

        System.out.println(fromLiteral == fromObject);
        System.out.println(fromLiteral == fromName);
        System.out.println(fromLiteral.getName());
        System.out.println(person.name);
    }
}
```

Biên dịch và chạy bằng Java 17+:

```bash
javac ClassMetadataDemo.java
java ClassMetadataDemo
```

Kết quả chuẩn:

```text
true
true
ClassMetadataDemo$Person
Lan
```

Giải thích theo thứ tự:

1. `Person.class` lấy metadata của `Person`; không thực thi `new Person(...)`.
2. `new Person("Lan")` tạo instance. `person.getClass()` lấy metadata của instance ấy.
3. `Class.forName(Person.class.getName())` tìm đúng kiểu bằng tên nhị phân (`$` phân tách nested class trong tên nhị phân).
4. Ba biến `fromLiteral`, `fromObject` và `fromName` đều tham chiếu cùng một đối tượng `Class` trong ví dụ này, vì cùng kiểu và cùng defining class loader. Toán tử `==` kiểm tra đồng nhất tham chiếu.
5. Dòng cuối đọc trường `name` từ **instance `Person`**, không phải từ `Class<Person>`.

Nếu `Person` được khai báo trong package, tên nhị phân có thêm package ở đầu; dùng `Person.class.getName()` giúp tránh nhầm tên nguồn và tên nhị phân.

## 5. Nhận `Class` không phải là tạo instance của kiểu được mô tả

Reflection cho phép lấy constructor **của kiểu được mô tả** rồi gọi constructor đó để tạo instance, nếu quyền truy cập và kiểu cho phép. Đây là một thao tác hoàn toàn khác với `new Class(...)`.

Lưu thành **`ReflectiveConstructionDemo.java`**:

```java
public class ReflectiveConstructionDemo {
    public static class Greeting {
        public Greeting() {
        }

        public String say() {
            return "Xin chào";
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Greeting> type = Greeting.class;

        // Constructor<Greeting> mô tả constructor của Greeting.
        Greeting instance = type.getDeclaredConstructor().newInstance();

        System.out.println(type.getSimpleName());
        System.out.println(instance.say());
        System.out.println(instance.getClass() == type);
    }
}
```

```bash
javac ReflectiveConstructionDemo.java
java ReflectiveConstructionDemo
```

Kết quả:

```text
Greeting
Xin chào
true
```

Ở đây:

- `Greeting.class` trả về `Class<Greeting>`.
- `getDeclaredConstructor()` lấy metadata của constructor không tham số thuộc `Greeting`.
- `Constructor.newInstance()` tạo **một `Greeting` mới**, không tạo một `Class` mới.
- Ví dụ dùng constructor `public` để không vướng hạn chế truy cập.

Khi áp dụng thực tế, cần có chữ ký constructor phù hợp; constructor có thể không tồn tại, không truy cập được, ném exception, hoặc kiểu có thể không khởi tạo trực tiếp được (chẳng hạn interface/abstract class). Tránh dùng `Class.newInstance()`: API này đã deprecated; dùng `getDeclaredConstructor(...).newInstance(...)` để xử lý constructor và exception rõ ràng hơn.

## 6. Lấy metadata không đồng nghĩa với khởi tạo lớp

Class literal như `LazyType.class` chỉ lấy đối tượng mô tả kiểu; nó không tự chạy static initializer của `LazyType`. Trái lại, `Class.forName(LazyType.class.getName())` yêu cầu khởi tạo lớp nếu chưa khởi tạo. Nếu cần lấy metadata theo tên mà chưa chủ động khởi tạo, dùng `Class.forName(name, false, loader)` với loader phù hợp.

Cả hai cách vẫn trả về **đối tượng `Class`**, và việc khởi tạo lớp (chạy mã `static`) vẫn khác với **tạo instance** bằng `new LazyType()` hoặc gọi constructor qua Reflection. Các trình tự và ngoại lệ khởi tạo thuộc bài riêng về vòng đời lớp.

## 7. `Class` cũng mô tả kiểu không có constructor instance thông thường

`Class` không chỉ dùng cho lớp có thể `new`:

```java
Class<?> primitiveType = int.class;
Class<?> voidType = void.class;
Class<?> arrayType = String[].class;
Class<?> interfaceType = Runnable.class;
```

- `int.class`, `void.class` và `String[].class` đều là các đối tượng `Class` hợp lệ.
- `Runnable.class` mô tả một interface; interface không có instance constructor để gọi bằng `new Runnable()`.
- Không được suy ra từ việc có `Class<?>` rằng kiểu đó có một constructor không tham số hay có thể tạo instance trực tiếp.
- `Class.forName("int")` không phải cách lấy `int.class`; tên primitive không được tìm theo cách đó.
- Do type erasure, `List<String>.class` là cú pháp không hợp lệ; dùng `List.class`. Thông tin type argument cụ thể có thể cần phân tích ở `Type`/`ParameterizedType` trong ngữ cảnh thích hợp, không nằm trong một `Class<List<String>>` riêng biệt.

Điều này càng cho thấy `Class` là đại diện cho **một kiểu runtime**, không phải một lớp do ứng dụng tự dựng bằng constructor.

## 8. Lỗi hay gặp và cách sửa

| Viết sai hoặc hiểu sai | Vấn đề | Cách đúng |
| --- | --- | --- |
| `new Class<>()` | `Class` không có constructor công khai cho ứng dụng. | Dùng `SomeType.class`, `obj.getClass()` hoặc `Class.forName(...)`. |
| Dùng `SomeType.class` rồi mong đã có instance `SomeType` | Class literal chỉ lấy metadata kiểu. | Gọi `new SomeType(...)` hoặc constructor reflection khi cần instance. |
| Dùng `Class.forName("Person")` cho nested/packaged type mà không có tên nhị phân phù hợp | Không tìm thấy class theo tên cung cấp. | Dùng tên nhị phân đầy đủ hoặc lấy `Person.class.getName()`. |
| Gọi `value.getClass()` khi `value` null | `NullPointerException`. | Kiểm tra null hoặc dùng `SomeType.class` nếu biết kiểu. |
| Giả định `Class.forName(...)` luôn an toàn và không có side effect | Bản một tham số có thể kích hoạt khởi tạo lớp và exception liên quan. | Xử lý lỗi, cân nhắc overload ba tham số khi cần kiểm soát initialization. |
| Gọi `getDeclaredConstructor().newInstance()` với mọi `Class<?>` | Có thể không có constructor phù hợp, không đủ quyền truy cập hoặc kiểu không thể được tạo trực tiếp. | Kiểm tra loại kiểu, constructor, quyền truy cập và xử lý `ReflectiveOperationException` thích hợp. |
| Dùng `Class.newInstance()` | API cũ deprecated, kém rõ ràng về constructor và lỗi phát sinh. | Dùng `getDeclaredConstructor(...).newInstance(...)`. |
| Xem cùng tên class là cùng một kiểu ở mọi class loader | Danh tính runtime của kiểu còn phụ thuộc defining class loader. | Kiểm tra loader/kiểu thực tế khi làm plugin, module runtime hoặc custom loading. |

## 9. Cách chọn API trong thực tế

- **Biết trước kiểu**: ưu tiên `Foo.class`; compiler kiểm tra tên kiểu và có generic type phù hợp, ví dụ `Class<Foo>`.
- **Đã có đối tượng**: dùng `obj.getClass()` để biết chính xác runtime type, đặc biệt khi có kế thừa/đa hình.
- **Có tên kiểu từ cấu hình**: dùng `Class.forName(...)`, đồng thời kiểm soát dữ liệu đầu vào, class loader, thời điểm initialization và exception.
- **Cần tạo instance động**: trước hết lấy `Class`, sau đó tìm và gọi constructor **của kiểu được mô tả**; không tìm cách tạo thêm một `Class` bằng `new`.

## 10. Tự kiểm tra

1. Vì sao `Person.class` trả về một `Class<Person>` mà không cần `new Class<Person>()`?
2. `Person.class` và `new Person().getClass()` giống nhau trong điều kiện nào? Khi nào biến kiểu `Person` trỏ tới subclass thì kết quả có thể khác?
3. `Class.forName(String)` khác `Person.class` thế nào về cách xác định tên và khả năng kích hoạt static initialization?
4. Gọi `type.getDeclaredConstructor().newInstance()` tạo đối tượng thuộc kiểu nào?
5. Vì sao `int.class` và `Runnable.class` là giá trị hợp lệ dù không thể gọi constructor instance thông thường?

**Ghi nhớ:** `Class` là đối tượng metadata do JVM/runtime quản lý. Ta **lấy tham chiếu `Class` qua class literal, instance, tên kiểu hoặc class loader**, rồi dùng metadata để tìm hiểu hay thao tác với kiểu. Ta **không tạo đối tượng `Class` bằng constructor thông thường**; constructor reflection (nếu phù hợp) dùng để tạo **instance của kiểu được mô tả**.