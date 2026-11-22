# Kết nối mô hình đối tượng với `MethodHandle`

`MethodHandle` là một tham chiếu có kiểu mạnh đến một thao tác có thể gọi được. Trong mô hình đối tượng Java, thao tác đó có thể là phương thức instance, phương thức static, phương thức interface, constructor hoặc getter/setter của field. `MethodHandles.Lookup` tìm và kiểm tra quyền truy cập đến thành viên; `MethodType` mô tả chữ ký; `MethodHandle` giữ thao tác đã được liên kết để có thể gọi lại.

Kết nối này cho phép framework và ứng dụng xây dựng lời gọi động dựa trên lớp, đối tượng và kiểu dữ liệu mà vẫn giữ được kiểm tra kiểu ở runtime. Sau khi tìm được handle, mã có thể truyền, lưu, kết hợp, điều chỉnh hoặc gắn receiver vào handle thay vì phải tìm lại thành viên theo tên ở mỗi lần gọi.

## 1. Từ mô hình đối tượng đến một lời gọi có kiểu

Mô hình đối tượng Java có các thành phần chính:

- **Class:** khai báo field, method, constructor và quan hệ kế thừa.
- **Object:** một instance có trạng thái riêng; lời gọi phương thức instance thường cần receiver là object đó.
- **Static member:** thuộc về lớp, không cần receiver instance.
- **Inheritance và overriding:** lớp con có thể thay thế cách triển khai một phương thức virtual.
- **Interface:** mô tả hợp đồng phương thức mà các lớp triển khai.
- **Encapsulation:** field và method có thể là private, protected, package-private hoặc public.

`MethodHandle` kết nối trực tiếp với các thành phần đó. Một handle có chữ ký xác định, chẳng hạn `(Person, String)String`, có thể biểu diễn lời gọi `Person.greet(String)` trên một đối tượng `Person` cụ thể hoặc một subclass của nó.

```text
Class + member + access rights
              |
              v
     MethodHandles.Lookup
              | findVirtual / findStatic / findConstructor / findGetter ...
              v
         MethodHandle
              | typed invocation / bindTo / asType / composition
              v
       Java object behavior
```

Điểm quan trọng là handle không chỉ là tên phương thức dạng chuỗi. Nó là tham chiếu thực thi đã được phân giải với kiểu tham số, kiểu trả về và quyền truy cập cụ thể.

## 2. Ba thành phần cần hiểu

### `MethodHandles.Lookup` — quyền tìm thành viên

`Lookup` đại diện cho quyền của mã đang thực hiện việc tìm thành viên. Tạo lookup tại lớp gọi bằng:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
```

Lookup có thể tìm thành viên public và các thành viên khác mà lớp gọi có quyền truy cập. Với thành viên private, cần lookup có quyền private phù hợp, thường được tạo bên trong lớp sở hữu hoặc bằng `privateLookupIn` khi module access cho phép.

Không thể dùng `Lookup` như một cách bỏ qua encapsulation. Quyền tìm thành viên chịu ảnh hưởng của access modifier và Java Platform Module System; `exports` và `opens` vẫn có ý nghĩa riêng.

### `MethodType` — chữ ký của thao tác

`MethodType` mô tả kiểu trả về và danh sách kiểu tham số:

```java
MethodType greetType =
    MethodType.methodType(String.class, String.class);
```

Đoạn trên mô tả một phương thức nhận `String` và trả `String`. Với instance method, receiver không được ghi trong `MethodType` truyền vào `findVirtual`; receiver sẽ trở thành tham số đầu tiên của handle được tạo.

### `MethodHandle` — thao tác đã phân giải

`MethodHandle` là tham chiếu bất biến đến thao tác có thể gọi. Có thể xem chữ ký thực tế bằng `handle.type()`, sau đó gọi handle nhiều lần với các đối tượng phù hợp.

```java
System.out.println(handle.type());
```

Việc tìm handle có thể thất bại ngay khi tên, kiểu hoặc quyền truy cập không hợp lệ. Việc gọi handle có thể thất bại nếu kiểu tại call site hoặc object runtime không tương thích.

## 3. Ánh xạ thành viên đối tượng sang MethodHandle

Các factory `Lookup` thường dùng:

| Thành viên trong Java | Cách tìm | Kiểu handle thu được |
| --- | --- | --- |
| Instance method virtual | `findVirtual(C.class, name, type)` | `(C, args...)Return` — receiver là tham số đầu. |
| Interface method | `findVirtual(I.class, name, type)` | `(I, args...)Return` — lời gọi vẫn dispatch theo object thực tế. |
| Static method | `findStatic(C.class, name, type)` | `(args...)Return` — không có receiver. |
| Constructor | `findConstructor(C.class, type)` | `(args...)C` — MethodType tìm constructor có return type `void`. |
| Instance field getter | `findGetter(C.class, name, fieldType)` | `(C)FieldType`. |
| Instance field setter | `findSetter(C.class, name, fieldType)` | `(C, FieldType)void`. |
| Static field getter | `findStaticGetter(C.class, name, fieldType)` | `()FieldType`. |
| Static field setter | `findStaticSetter(C.class, name, fieldType)` | `(FieldType)void`. |

Với field `final`, setter handle không thể được tạo như một thao tác ghi thông thường. Với private member, lookup phải có quyền phù hợp.

## 4. Instance method và receiver

Ví dụ một lớp có phương thức instance:

```java
class Person {
    public String greet(String prefix) {
        return prefix + "person";
    }
}
```

Tìm handle:

```java
MethodHandle greet = lookup.findVirtual(
    Person.class,
    "greet",
    MethodType.methodType(String.class, String.class));
```

`MethodType` truyền vào chỉ chứa tham số khai báo của `greet`: `(String)String`. Nhưng kiểu handle sau khi tìm được có dạng `(Person, String)String`, vì receiver `Person` được thêm ở đầu.

```java
Person person = new Person();
String result = (String) greet.invokeExact(person, "Hello ");
```

Receiver chính là đối tượng mà lời gọi phương thức sẽ tác động lên. Một handle chưa bind có thể được dùng với nhiều instance tương thích.

## 5. Kế thừa và dynamic dispatch

`findVirtual` liên kết với phương thức virtual được tìm trên kiểu tham chiếu, nhưng khi gọi handle, JVM vẫn áp dụng dynamic dispatch theo lớp thực tế của receiver. Vì vậy, một handle tìm từ lớp cha có thể gọi implementation override của lớp con.

```java
class Employee extends Person {
    @Override
    public String greet(String prefix) {
        return prefix + "employee";
    }
}

Person employee = new Employee();
String result = (String) greet.invokeExact(employee, "Hello ");
```

Handle `greet` vẫn có receiver type `Person`, nên biến có kiểu khai báo `Person` được truyền trực tiếp. Object thực tế là `Employee`, vì vậy implementation override của `Employee` được gọi.

Đây là điểm nối giữa MethodHandle và mô hình đa hình Java: handle giữ cách tìm và kiểu lời gọi, còn virtual dispatch vẫn dựa trên object receiver.

## 6. Interface method và implementation thực tế

Có thể tìm phương thức trên interface:

```java
MethodHandle label = lookup.findVirtual(
    Named.class,
    "label",
    MethodType.methodType(String.class));

Named value = new Employee("Binh", 25);
String text = (String) label.invokeExact(value);
```

Kiểu handle là `(Named)String`. Khi receiver là một implementation cụ thể, lời gọi được dispatch đến phương thức tương ứng của lớp đó.

Không cần tạo một handle riêng cho mỗi implementation nếu tất cả đều tuân theo cùng chữ ký interface. Điều này hữu ích khi xây dựng bộ xử lý dựa trên interface hoặc plugin.

## 7. Static method và constructor

### Static method

Static method không có receiver. Chữ ký handle tương ứng trực tiếp với các tham số của method:

```java
MethodHandle category = lookup.findStatic(
    Person.class,
    "category",
    MethodType.methodType(String.class, int.class));

String result = (String) category.invokeExact(20);
```

Kiểu handle là `(int)String`.

### Constructor

Constructor được tìm bằng `findConstructor`. MethodType dùng để tìm constructor phải có kiểu trả về `void`, nhưng handle thu được trả về object vừa tạo:

```java
MethodHandle constructor = lookup.findConstructor(
    Person.class,
    MethodType.methodType(void.class, String.class, int.class));

Person person = (Person) constructor.invokeExact("An", 20);
```

Kiểu handle thu được là `(String, int)Person`. Điều này cho phép framework tạo instance từ metadata lớp và chữ ký constructor mà không phải gọi constructor theo một nhánh code riêng cho từng class.

## 8. Field getter và setter kết nối với trạng thái object

MethodHandle cũng có thể đại diện cho thao tác đọc hoặc ghi field. Với field instance, receiver là tham số đầu tiên.

```java
MethodHandle getter = privateLookup.findGetter(
    Person.class, "age", int.class);
MethodHandle setter = privateLookup.findSetter(
    Person.class, "age", int.class);

setter.invokeExact(person, 21);
int age = (int) getter.invokeExact(person);
```

Getter có kiểu `(Person)int`; setter có kiểu `(Person, int)void`. Đây là cách liên kết trực tiếp với trạng thái của object mà vẫn giữ kiểu dữ liệu rõ ràng.

Với field static, dùng `findStaticGetter` và `findStaticSetter`; handle không nhận receiver. Không dùng setter cho field `final` hoặc field mà lookup không có quyền ghi.

## 9. Gắn receiver bằng `bindTo`

Khi một handle instance được dùng lặp lại trên cùng một object, có thể bind receiver:

```java
MethodHandle personGreet = greet.bindTo(person);
String result = (String) personGreet.invokeExact("Welcome ");
```

Trước khi bind, kiểu handle là `(Person, String)String`. Sau khi bind, tham số receiver đầu tiên được cố định và kiểu còn lại là `(String)String`.

`bindTo` chỉ bind tham số đầu tiên khi tham số đó là kiểu tham chiếu phù hợp. Với các trường hợp cần chèn giá trị vào vị trí khác, có thể dùng `MethodHandles.insertArguments`.

Binding làm cho handle gắn với object cụ thể. Nếu cần xử lý nhiều instance, giữ handle chưa bind và truyền receiver ở mỗi lần gọi.

## 10. `invokeExact`, `invoke` và `asType`

Các phương thức gọi handle có quy tắc kiểu khác nhau.

### `invokeExact`

`invokeExact` yêu cầu kiểu tĩnh tại call site khớp chính xác với kiểu handle, bao gồm kiểu tham số, thứ tự và kiểu trả về. Phương thức có tính signature-polymorphic, vì vậy kiểu biểu thức Java tại vị trí gọi rất quan trọng.

```java
String result = (String) greet.invokeExact(person, "Hello ");
```

Cast kết quả về `String` giúp call site có đúng kiểu trả về. Nếu để kiểu trả về hoặc kiểu đối số khác descriptor của handle, runtime có thể ném `WrongMethodTypeException`.

### `invoke`

`invoke` cho phép các chuyển đổi kiểu mà cơ chế MethodHandle hỗ trợ, tương tự việc thích ứng một handle. Các chuyển đổi có thể gồm boxing/unboxing, widening primitive và reference cast phù hợp. Nó không có nghĩa là mọi kiểu dữ liệu đều tự động chuyển đổi được.

### `asType`

`asType` tạo một handle mới có kiểu đích bằng cách thích ứng kiểu của handle gốc:

```java
MethodHandle genericGreet = greet.asType(
    MethodType.methodType(Object.class, Object.class, Object.class));

Object result = (Object) genericGreet.invokeExact(
    (Object) person, (Object) "Dynamic ");
```

Handle mới nhận `Object`, thích ứng receiver và đối số về kiểu cần thiết rồi gọi handle gốc. `asType` không thay đổi handle ban đầu.

Khi kiểu đích không thể thích ứng với kiểu gốc, `asType` hoặc lúc gọi handle thích ứng có thể ném `WrongMethodTypeException`; reference cast với object thực tế không phù hợp có thể ném `ClassCastException`.

## 11. Kết hợp các MethodHandle

MethodHandle không chỉ được gọi độc lập. Lớp `MethodHandles` cung cấp các phép kết hợp để xây dựng pipeline thao tác:

- `filterArguments` chèn bước chuyển đổi hoặc kiểm tra trước khi gọi handle chính.
- `filterReturnValue` biến đổi kết quả sau lời gọi.
- `collectArguments` kết hợp đầu vào từ một handle khác.
- `foldArguments` dùng kết quả của một handle để chuẩn bị lời gọi tiếp theo.
- `guardWithTest` chọn một trong hai handle dựa trên kết quả kiểm tra.
- `insertArguments` cố định một hoặc nhiều đối số tại vị trí xác định.

Ví dụ khái niệm: một handle nhận `String`, một handle kiểm tra chuỗi, và một handle chính xử lý dữ liệu. Có thể kết hợp chúng để tạo một thao tác mới mà không cần viết một lớp adapter riêng cho từng tổ hợp.

Các combinator cũng có chữ ký kiểu rõ ràng. Khi kết hợp, phải kiểm tra `MethodType` đầu vào và đầu ra để bảo đảm các handle tương thích.

## 12. `findSpecial` và lời gọi đặc biệt

`findVirtual` dùng dynamic dispatch. Trong một số trường hợp cần ngữ nghĩa gọi đặc biệt như lời gọi `super` hoặc một default method cụ thể, `Lookup.findSpecial(...)` tạo handle với ngữ nghĩa tương tự bytecode `invokespecial`.

`findSpecial` yêu cầu chỉ định `specialCaller` và chịu các điều kiện truy cập chặt chẽ. Nó không phải cách thay thế chung cho `findVirtual`; chỉ dùng khi cần ngữ nghĩa gọi đặc biệt và caller lookup có quyền hợp lệ.

## 13. Từ MethodHandle đến liên kết động

`MethodHandle` là đích gọi đã phân giải và có kiểu. Khi ứng dụng cần thay đổi đích gọi theo runtime, có thể đặt handle làm target của `CallSite`.

- `ConstantCallSite` giữ target cố định sau khi tạo.
- `MutableCallSite` cho phép cập nhật target; việc công bố thay đổi đến các thread khác cần tuân theo cơ chế đồng bộ của API.
- `VolatileCallSite` cung cấp semantics volatile cho target.

`invokedynamic` sử dụng bootstrap method để tạo `CallSite`; call site cung cấp target MethodHandle cho lệnh gọi động. Đây là lớp liên kết cao hơn: MethodHandle biểu diễn thao tác, còn CallSite quản lý target được sử dụng tại một điểm gọi động.

Không cần dùng CallSite nếu chỉ cần tìm một method handle rồi gọi lại. Dùng nó khi đích gọi của một call site cần được lựa chọn hoặc thay đổi theo trạng thái runtime.

## 14. Quyền truy cập và Java modules

`Lookup` kiểm soát quyền tìm member. MethodHandle không tự động vượt qua `private`, package boundary hay module encapsulation.

- Public member cần các điều kiện truy cập public thông thường, gồm readability và package export khi qua named module.
- Private member cần lookup có quyền private phù hợp.
- `privateLookupIn(targetClass, callerLookup)` có thể tạo private lookup khi caller đủ quyền và điều kiện module được đáp ứng.
- Khi đi qua named module, package đích phải được mở cho caller module; `exports` không thay thế `opens` cho private access.

Nếu `findVirtual`, `findStatic`, `findGetter` hoặc `findSetter` không có quyền phù hợp, thao tác tìm handle có thể ném `IllegalAccessException`. Nếu tên hoặc kiểu thành viên không tồn tại, có thể nhận `NoSuchMethodException` hoặc `NoSuchFieldException`.

## 15. Ví dụ hoàn chỉnh: kết nối class, object và MethodHandle

Chương trình sau minh họa constructor, instance method, override dispatch, interface method, static method, private field getter/setter, receiver binding và kiểu handle tổng quát. Lưu toàn bộ nội dung vào `Main.java`.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class Main {
    interface Named {
        String label();
    }

    static class Person implements Named {
        private final String name;
        private int age;

        Person(String name, int age) {
            this.name = name;
            this.age = age;
        }

        public String greet(String prefix) {
            return prefix + name;
        }

        @Override
        public String label() {
            return "Person:" + name;
        }

        public static String category(int age) {
            return age >= 18 ? "adult" : "minor";
        }
    }

    static final class Employee extends Person {
        Employee(String name, int age) {
            super(name, age);
        }

        @Override
        public String greet(String prefix) {
            return prefix + "Employee " + super.greet("");
        }

        @Override
        public String label() {
            return "Employee";
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        MethodHandle constructor = lookup.findConstructor(
            Person.class,
            MethodType.methodType(void.class, String.class, int.class));
        Person person = (Person) constructor.invokeExact("An", 20);
        System.out.println("constructor handle: " + person.greet("Hello "));

        MethodHandle greet = lookup.findVirtual(
            Person.class,
            "greet",
            MethodType.methodType(String.class, String.class));
        System.out.println("virtual method handle: "
            + (String) greet.invokeExact(person, "Hi "));

        Person employee = new Employee("Binh", 25);
        System.out.println("overridden virtual dispatch: "
            + (String) greet.invokeExact(employee, "Hi "));

        MethodHandle label = lookup.findVirtual(
            Named.class,
            "label",
            MethodType.methodType(String.class));
        Named named = employee;
        System.out.println("interface method handle: "
            + (String) label.invokeExact(named));

        MethodHandle category = lookup.findStatic(
            Person.class,
            "category",
            MethodType.methodType(String.class, int.class));
        System.out.println("static method handle: "
            + (String) category.invokeExact(17));

        MethodHandles.Lookup privateLookup =
            MethodHandles.privateLookupIn(Person.class, lookup);
        MethodHandle getAge = privateLookup.findGetter(
            Person.class, "age", int.class);
        MethodHandle setAge = privateLookup.findSetter(
            Person.class, "age", int.class);
        setAge.invokeExact(person, 21);
        System.out.println("private field handle: "
            + (int) getAge.invokeExact(person));

        MethodHandle boundGreet = greet.bindTo(person);
        System.out.println("bound receiver: "
            + (String) boundGreet.invokeExact("Welcome "));

        MethodHandle genericGreet = greet.asType(
            MethodType.methodType(Object.class, Object.class, Object.class));
        Object genericResult = (Object) genericGreet.invokeExact(
            (Object) person, (Object) "Dynamic ");
        System.out.println("adapted handle: " + genericResult);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Stdout chính xác:

```text
constructor handle: Hello An
virtual method handle: Hi An
overridden virtual dispatch: Hi Employee Binh
interface method handle: Employee
static method handle: minor
private field handle: 21
bound receiver: Welcome An
adapted handle: Dynamic An
```

Ví dụ chứng minh handle tìm từ `Person` vẫn dispatch đến `Employee`; handle interface cũng gọi implementation của object thực tế. Constructor tạo instance, getter/setter kết nối trạng thái private, còn `bindTo` và `asType` thay đổi cách handle được sử dụng.

## 16. Lỗi thường gặp

1. **Quên receiver của instance method.** Kiểu handle từ `findVirtual` có receiver ở tham số đầu tiên; kiểu `MethodType` truyền vào factory không chứa receiver đó.
2. **Thêm receiver cho static method.** `findStatic` không có receiver; truyền thêm đối số làm sai chữ ký.
3. **Dùng sai return type khi tìm constructor.** `findConstructor` nhận MethodType có return type `void`, nhưng handle thu được trả về instance của lớp.
4. **Nhầm `findVirtual` với `findSpecial`.** Virtual method dùng dynamic dispatch; special invocation có ngữ nghĩa riêng như `super`.
5. **Cho rằng handle tìm trên lớp cha bỏ qua override.** Handle virtual vẫn dispatch theo lớp thực tế của receiver.
6. **Gọi `invokeExact` với kiểu tĩnh không khớp.** Kiểu đối số và kiểu trả về tại call site phải đúng descriptor của handle.
7. **Cho rằng `invoke` chấp nhận mọi kiểu.** Chỉ các chuyển đổi mà cơ chế MethodHandle hỗ trợ mới được thực hiện.
8. **Bind nhầm receiver.** `bindTo` cố định tham số tham chiếu đầu tiên; kiểm tra `handle.type()` trước và sau khi bind.
9. **Truy cập private member bằng lookup không đủ quyền.** Dùng lookup có quyền hợp lệ và tuân theo module openness.
10. **Tìm handle lặp lại cho mỗi lần gọi.** Nếu thành viên và kiểu đã biết, giữ handle để tái sử dụng thay vì tìm lại liên tục.
11. **Cho rằng MethodHandle luôn nhanh hơn reflection.** Hiệu năng phụ thuộc JVM, call site, khả năng tối ưu và cách dùng; đo benchmark trên workload thực tế.
12. **Bỏ qua kiểu của handle sau khi kết hợp.** Các combinator và `asType` tạo chữ ký mới; kiểm tra `type()` để phát hiện mismatch.

## 17. Ghi nhớ

1. `Lookup` tìm thành viên và kiểm tra quyền; `MethodType` mô tả chữ ký; `MethodHandle` giữ thao tác đã phân giải.
2. `findVirtual` liên kết instance/interface method và thêm receiver làm tham số đầu của handle.
3. Virtual dispatch vẫn theo lớp thực tế của object, nên override của subclass được gọi.
4. `findStatic` không có receiver; `findConstructor` nhận MethodType trả `void` nhưng handle trả object mới.
5. `findGetter` và `findSetter` kết nối handle với trạng thái field của object.
6. `bindTo` cố định receiver; `asType` tạo handle mới với kiểu đã thích ứng.
7. `invokeExact` cần kiểu call site chính xác; `invoke` cho phép các chuyển đổi được hỗ trợ.
8. MethodHandle có thể được kết hợp bằng các combinator; CallSite quản lý target cho liên kết động khi cần thay đổi đích gọi theo runtime.
9. Quyền truy cập của MethodHandle vẫn tuân theo access modifier và Java module system.