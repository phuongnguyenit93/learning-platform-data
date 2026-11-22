# Phân biệt đối tượng `Class` với instance của kiểu được mô tả trong Java

## 1. Hai khái niệm liên quan nhưng không đồng nhất

Trong Java, một **instance (đối tượng thể hiện)** là đối tượng được tạo ra từ một lớp hoặc một kiểu cụ thể ở thời gian chạy. Nó mang trạng thái riêng qua các trường instance và có thể thực hiện hành vi được định nghĩa bởi kiểu đó. Ví dụ, `new Person("An")` tạo một đối tượng `Person`.

Một **đối tượng `Class`** là đối tượng thuộc kiểu `java.lang.Class`, được JVM cung cấp để **mô tả một kiểu ở thời gian chạy**: tên kiểu, superclass, interface, constructor, field, method, annotation, v.v. Ví dụ, `Person.class` là đối tượng `Class<Person>` đại diện cho kiểu `Person`. Nó không phải là một `Person` và không chứa trạng thái `name` riêng của từng `Person`.

Ba tầng cần phân biệt:

- **Khai báo kiểu:** `class Person { ... }` trong mã nguồn quy định cấu trúc và hành vi.
- **Đối tượng `Class` của kiểu:** `Person.class` là thông tin mô tả kiểu `Person` mà chương trình có thể truy vấn khi chạy.
- **Instance của kiểu:** `new Person("An")` hoặc `new Person("Bình")` là các đối tượng `Person` cụ thể, có trạng thái độc lập.

Tên `Class` dễ gây nhầm lẫn: `Person.class` là **một đối tượng Java**, nhưng **không phải instance của `Person`**; bản thân nó là instance của `java.lang.Class`. Biểu thức `Class.class` lại là đối tượng `Class` mô tả chính kiểu `java.lang.Class`.

| Tiêu chí | Đối tượng `Class` mô tả `Person` | Instance `Person` |
| --- | --- | --- |
| Ví dụ | `Person.class`, `person.getClass()` | `new Person("An")` |
| Kiểu của bản thân đối tượng | `java.lang.Class` | `Person` (hoặc lớp con cụ thể) |
| Nó biểu diễn gì? | Một kiểu được JVM nhận biết | Một đối tượng dữ liệu cụ thể |
| Trạng thái | Thông tin/khả năng truy vấn cấu trúc kiểu | Giá trị trường instance, ví dụ `name` |
| Số lượng | Cùng một kiểu do cùng class loader định nghĩa thường dùng chung một `Class` | Có thể tạo nhiều instance của cùng kiểu |
| Cách lấy | `T.class`, `obj.getClass()`, `Class.forName(...)` | `new`, factory method, reflection, v.v. |
| Dùng để | Kiểm tra kiểu, tìm constructor/method/field, hỗ trợ reflection | Gọi hành vi và làm việc với dữ liệu cụ thể |

**Chốt phân biệt:** `Class` trả lời “đối tượng này thuộc **kiểu nào**, kiểu ấy được mô tả ra sao?”; instance trả lời “**đối tượng cụ thể nào**, đang mang dữ liệu gì?”. Hai instance khác nhau có thể tham chiếu đến cùng một đối tượng `Class`.

## 2. Ví dụ Java 17+ chạy được

Lưu đúng tên tệp `ClassVsInstanceDemo.java`:

```java
import java.lang.reflect.Method;

public class ClassVsInstanceDemo {
    public static class Person {
        private final String name;

        public Person(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<Person> type = Person.class;
        Person an = new Person("An");
        Person binh = new Person("Bình");
        Class<? extends Person> runtimeType = an.getClass();

        System.out.println(type == runtimeType);
        System.out.println(an == binh);
        System.out.println(type.isInstance(an));
        System.out.println(type.isInstance("An"));
        System.out.println(type.getSimpleName());
        System.out.println(type.getClass() == Class.class);

        Method nameMethod = type.getMethod("name");
        System.out.println(nameMethod.invoke(an));
        System.out.println(nameMethod.invoke(binh));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ClassVsInstanceDemo.java
java ClassVsInstanceDemo
```

Kết quả chuẩn:

```text
true
false
true
false
Person
true
An
Bình
```

Giải thích lần lượt:

1. `type == runtimeType` là `true`: `Person.class` và `an.getClass()` trả cùng đối tượng `Class` khi `an` thực sự thuộc `Person`.
2. `an == binh` là `false`: hai lần `new` tạo hai instance khác nhau; cả hai đều được mô tả bởi kiểu `Person`.
3. `type.isInstance(an)` là `true`, còn `type.isInstance("An")` là `false`: đây là phép kiểm tra một **giá trị đối tượng** có thuộc kiểu được mô tả hay không.
4. `getSimpleName()` trả `Person`, là thuộc tính của kiểu; nó không đọc dữ liệu `name` của instance.
5. `type.getClass() == Class.class` là `true`: đối tượng `type` thuộc lớp `Class`, dù nó đang mô tả lớp `Person`.
6. `getMethod("name")` tìm mô tả method chung của kiểu. `invoke(an)` và `invoke(binh)` thực thi method ấy trên **hai receiver khác nhau**, nên trả `An` và `Bình`.

Trong ví dụ, `Class<Person>` giúp biểu thị đối tượng `Class` dành cho `Person` ở thời gian biên dịch. `Class<? extends Person>` dành cho `getClass()` vì một tham chiếu kiểu `Person` cũng có thể trỏ đến instance của lớp con; kiểu thực tế khi chạy được quyết định bởi đối tượng, không chỉ bởi khai báo biến.

## 3. Lấy đối tượng `Class` theo nhu cầu

| Tình huống | Cách lấy | Điều quan trọng |
| --- | --- | --- |
| Biết sẵn kiểu trong source | `Person.class` | Không cần tạo `Person` chỉ để đọc metadata. |
| Có một instance | `person.getClass()` | Phản ánh lớp runtime thực tế; `null` gây `NullPointerException`. |
| Chỉ có tên kiểu ở runtime | `Class.forName("demo.Person")` | Cần binary name, loader phù hợp, xử lý lỗi nạp; dạng một tham số yêu cầu khởi tạo. |

Ví dụ `Object value = "hello";` thì `value.getClass() == String.class` là `true`, còn `value.getClass() == Object.class` là `false`: kiểu khai báo biến không thay lớp runtime của instance. Đối với `int` hay `void`, có thể lấy `int.class`/`void.class` dù không có instance đối tượng tương ứng.

Mọi đường trên đều lấy metadata về kiểu; chúng không mang dữ liệu riêng của các instance. Cách chọn giữa class literal, `getClass()` và `Class.forName` được thực hành riêng ở những bài tương ứng.

## 4. `Class` mô tả kiểu; thao tác dữ liệu vẫn cần instance

Reflection thường đi theo hai bước: **tìm thành viên qua `Class`**, rồi **thao tác trên receiver cụ thể** nếu đó là thành viên instance.

- `Person.class.getDeclaredFields()` tìm các field được **khai báo trực tiếp** trong `Person` (không tự động gồm field kế thừa). Mỗi `Field` là mô tả một thành viên, không phải giá trị field của từng `Person`.
- `Person.class.getMethod("name")` tìm một method `public` phù hợp, kể cả method `public` kế thừa. `getDeclaredMethod(...)` chỉ tìm method được khai báo trong chính lớp, bất kể mức truy cập.
- `Method.invoke(person)` cần một receiver `person` phù hợp cho method instance; receiver khác có thể tạo kết quả khác. Với method static, không có receiver instance.
- `Person.class.getConstructor(String.class)` tìm constructor công khai. Khi thực sự cần tạo instance bằng reflection, có thể gọi `getConstructor(String.class).newInstance("Chi")`, với xử lý ngoại lệ và quyền truy cập thích hợp. Đối tượng `Class` tự nó không biến thành instance `Person`.

Không nhầm `Field`, `Method`, `Constructor` (các đối tượng mô tả thành viên) với giá trị hoặc hoạt động diễn ra trên một instance. Quyền truy cập Java/module vẫn áp dụng khi truy cập phản chiếu; tìm thấy metadata không bảo đảm gọi hay đọc/ghi được mọi thành viên.

**Trường static là trường hợp riêng:** dữ liệu static gắn với lớp trong ngữ cảnh runtime của nó, không có một bản sao cho mỗi instance. Điều này không biến `Person.class` thành một `Person`, cũng không làm cho các field instance trở thành dữ liệu của `Class`.

## 5. Kiểm tra kiểu: `==`, `isInstance`, `isAssignableFrom`

Ba câu hỏi khác nhau dẫn đến ba phép kiểm tra khác nhau:

| Biểu thức | Hỏi điều gì? | Ví dụ kết quả |
| --- | --- | --- |
| `a.getClass() == b.getClass()` | Hai instance có **cùng kiểu runtime chính xác** không? | Có thể `true` dù `a != b` |
| `type.isInstance(obj)` | `obj` có thuộc kiểu được `type` mô tả, kể cả subtype, không? | `Number.class.isInstance(Integer.valueOf(7))` → `true` |
| `parent.isAssignableFrom(child)` | Giá trị của kiểu `child` có thể gán cho biến kiểu `parent` không? | `Number.class.isAssignableFrom(Integer.class)` → `true` |

`==` giữa hai đối tượng `Class` kiểm tra **định danh của kiểu runtime**; `==` giữa hai instance kiểm tra **định danh đối tượng**. `isInstance` làm việc với một giá trị/instance, còn `isAssignableFrom` làm việc với hai đối tượng mô tả **kiểu**. Với kiểu tham chiếu, `isInstance(obj)` thường tương ứng ý nghĩa với `obj instanceof SomeType` (khi `SomeType` biết sẵn trong mã).

Ví dụ khác: một `ArrayList` là instance của `List` theo quan hệ interface, nhưng `list.getClass() == List.class` là `false` vì `getClass()` trả về lớp triển khai thực tế, không phải interface. Vì vậy, dùng `getClass() == T.class` khi cần *đúng kiểu chính xác*; dùng `instanceof` hoặc `isInstance` khi muốn chấp nhận cả kiểu con/kiểu triển khai.

## 6. Các trường hợp dễ gây nhầm lẫn

### Một `Class` có thể đại diện cho kiểu không tạo được instance thông thường

`int.class` và `void.class` là đối tượng `Class`, nhưng không tồn tại instance đối tượng Java tương ứng với `int` hay `void` theo nghĩa dùng `new`. Nếu autoboxing xảy ra, `Integer.valueOf(5).getClass()` trả `Integer.class`, **không phải** `int.class`.

Mảng là một kiểu tham chiếu với đối tượng mảng thực sự: `new String[2].getClass() == String[].class` là `true`. Interface/abstract class cũng có đối tượng `Class` dù không được khởi tạo trực tiếp. Enum, record và annotation type đều có đối tượng `Class` mô tả kiểu.

### “Một `Class` cho mỗi lớp” cần hiểu kèm class loader

Trong cùng một định nghĩa runtime, các instance cùng kiểu chia sẻ đối tượng `Class` của định nghĩa ấy. Nhưng JVM có thể nạp **cùng tên nhị phân** qua **các class loader định nghĩa khác nhau**, tạo ra các kiểu runtime khác nhau và các đối tượng `Class` khác nhau. Vì thế, **tên lớp bằng nhau chưa đủ để khẳng định hai `Class` là cùng một kiểu runtime**. Ngược lại, số instance tăng lên không tạo thêm một đối tượng `Class` mới cho mỗi instance.

### Generics không tạo kiểu runtime riêng cho mỗi đối số kiểu

`new java.util.ArrayList<String>()` và `new java.util.ArrayList<Integer>()` có cùng lớp runtime là `java.util.ArrayList`. Do **type erasure**, `getClass()` của hai đối tượng không cho biết phần tử là `String` hay `Integer`; thông tin kiểu tổng quát trong một khai báo field, method, superclass... nếu còn được lưu trong metadata cần được kiểm tra bằng API generic reflection tương ứng, chứ không suy ra từ `getClass()` của một `ArrayList`.

### `Class<T>` và instance `T` không thay thế được cho nhau

`Class<Person>` không phải `Person`. Không truyền `Person.class` vào API đang yêu cầu một instance `Person`; cũng không dùng `new Person(...)` ở vị trí yêu cầu đối tượng mô tả kiểu `Class<Person>`. Khi cần ép kiểu một giá trị, `Person.class.cast(obj)` kiểm tra/ép giá trị về `Person` ở runtime và có thể ném `ClassCastException`; nó **không tạo instance**. `Person.class.isInstance(obj)` chỉ kiểm tra và trả boolean.

## 7. Quy trình chọn API đúng khi viết code

1. **Đã biết kiểu ở mã nguồn và cần metadata?** Dùng `Person.class`; không cần tạo `Person` giả chỉ để gọi `getClass()`.
2. **Có một object và cần đúng lớp thực tế của nó?** Dùng `obj.getClass()` sau khi bảo đảm `obj != null`.
3. **Có tên kiểu do cấu hình/plugin cung cấp?** Cân nhắc `Class.forName(...)`, class loader/module và lỗi nạp/khởi tạo.
4. **Cần lấy method/field/constructor?** Tìm metadata qua `Class`; khi thao tác thành viên instance, cung cấp receiver và tuân thủ quyền truy cập.
5. **Cần kiểm tra object có phù hợp một kiểu?** Dùng `instanceof` hoặc `Class.isInstance`; khi cần xét quan hệ giữa hai kiểu, dùng `Class.isAssignableFrom`; khi cần so đúng kiểu runtime, so `Class` bằng `==`.

Tránh các lỗi sau: nghĩ `Person.class` chứa dữ liệu của một người cụ thể; tưởng hai lần `new Person(...)` tạo hai `Class` khác nhau; đánh đồng kiểu khai báo của biến với `getClass()` của giá trị; dùng so sánh `getClass() == Interface.class` để kiểm tra interface; gọi `getClass()` trên `null`; giả định lấy được metadata thì có thể truy cập thành viên private bất chấp module và access control.

## 8. Tự kiểm tra

**Câu 1.** `Person p1 = new Person("A"); Person p2 = new Person("B");` — `p1 == p2` và `p1.getClass() == p2.getClass()` là gì?

**Đáp án:** Lần lượt `false` và `true` (nếu hai biến giữ hai instance `Person` được tạo như trên trong cùng định nghĩa kiểu). Hai đối tượng khác nhau nhưng chung lớp runtime.

**Câu 2.** Vì sao một biến khai báo `Object x = "text";` lại có `x.getClass() == String.class`?

**Đáp án:** `getClass()` trả kiểu **thực tế của instance** (`String`), không trả kiểu khai báo của biến (`Object`).

**Câu 3.** Có thể dùng `Person.class.getMethod("name")` để tìm method và suy ra ngay tên của mọi instance `Person` không?

**Đáp án:** Không. `Method` mô tả method của kiểu. Muốn biết tên từng người phải gọi trên receiver phù hợp, ví dụ `method.invoke(p1)` và `method.invoke(p2)`; kết quả có thể khác nhau.

Khi hiểu rằng **`Class` là đối tượng mô tả kiểu**, còn **instance là đối tượng mang trạng thái và hành vi cụ thể**, các thao tác reflection, kiểm tra kiểu và đa hình trong Java sẽ nhất quán hơn.