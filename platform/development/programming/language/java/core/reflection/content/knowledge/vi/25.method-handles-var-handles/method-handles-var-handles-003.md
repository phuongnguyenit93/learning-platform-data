# `findVirtual`, `findStatic`, `findConstructor` và `findSpecial` trong Java MethodHandle

## 1. Bốn cách tìm lời gọi và mô hình tư duy

`java.lang.invoke.MethodHandle` là một đối tượng đại diện cho thao tác có thể gọi bằng Java: gọi phương thức instance, phương thức static, tạo đối tượng hoặc gọi một phương thức theo ngữ nghĩa đặc biệt. Ta không gọi trực tiếp tên phương thức qua `MethodHandle`; trước tiên dùng `MethodHandles.Lookup` để **tra cứu** thao tác hợp lệ, sau đó gọi handle.

Một `MethodHandle` có kiểu chạy được mô tả bởi `MethodType`: danh sách kiểu tham số và kiểu kết quả. Kiểu này phải được hiểu chính xác, bởi kiểu của handle sau tra cứu **có thể khác** kiểu khai báo của phương thức Java. Đặc biệt, handle cho phương thức instance có thêm **receiver** (đối tượng nhận lời gọi) ở vị trí tham số đầu tiên; handle constructor nhận tham số constructor nhưng trả về đối tượng mới, mặc dù khi tra cứu phải khai báo kiểu trả về `void`.

Bốn lời gọi được học ở đây đều nằm trên `MethodHandles.Lookup`:

| API | Tìm thao tác | `MethodType` truyền vào | Kiểu handle nhận được | Điểm phân biệt |
| --- | --- | --- | --- | --- |
| `findVirtual(refc, name, type)` | Phương thức instance | Kiểu kết quả và tham số **không gồm receiver** | `(Receiver, tham_số...)Kết_quả` | Dùng cơ chế dispatch instance phù hợp khi gọi |
| `findStatic(refc, name, type)` | Phương thức `static` | Đúng kiểu kết quả và tham số đã khai báo | `(tham_số...)Kết_quả` | Không có receiver |
| `findConstructor(refc, type)` | Constructor | **`void`** và tham số constructor | `(tham_số...)refc` | Tạo và trả về instance mới |
| `findSpecial(refc, name, type, specialCaller)` | Gọi instance theo ngữ nghĩa `invokespecial` | Kiểu kết quả và tham số **không gồm receiver** | `(specialCaller, tham_số...)Kết_quả`, theo quy tắc truy cập | Có thể gọi phiên bản ở lớp cha mà bỏ qua override, nếu lookup đủ quyền |

Trong bảng, `refc` là lớp hoặc interface dùng để phân giải thành viên; `name` là tên phương thức; `type` có kiểu `MethodType`. `specialCaller` là ngữ cảnh lớp đặc biệt được phép thực hiện `invokespecial`, không phải một chuỗi tên tùy ý. Java kiểm tra quyền truy cập tại thời điểm tìm handle; quyền đó không tự nhiên được nâng lên chỉ vì ta dùng API động.

## 2. `MethodType` và `Lookup`: chuẩn bị đúng trước khi tìm

`MethodType.methodType(returnType, parameterTypes...)` mô tả kiểu phương thức **được tìm**. Ví dụ:

```java
MethodType.methodType(String.class, int.class)          // (int)String
MethodType.methodType(void.class, String.class)          // (String)void
MethodType.methodType(boolean.class)                     // ()boolean
```

- `MethodHandles.lookup()` cấp lookup gắn với **lớp gọi nó** và các quyền hiện có của lớp đó. Trong một lớp có quyền truy cập phù hợp, lookup có thể nhìn thấy cả thành viên không public.
- `MethodHandles.publicLookup()` chỉ dành cho những truy cập public mà lookup công khai cho phép; không thể dùng nó để tự do gọi thành viên private hoặc package-private.
- `MethodHandles.privateLookupIn(Target.class, lookup)` có thể tạo lookup mang quyền private của `Target` **khi** lookup đầu vào, module và quy tắc mở package cho phép. Đây không phải cách vượt mọi rào cản `private`/module.
- Signature của phương thức và kiểu receiver phải chính xác. `MethodHandle.type()` giúp xem kiểu handle **sau** khi tìm, rất hữu ích khi chẩn đoán `WrongMethodTypeException`.

Tên phương thức có phân biệt chữ hoa/chữ thường; overload được phân biệt bằng danh sách tham số và kiểu trả về thích hợp. Với constructor, không có tên phương thức vì API chỉ nhận `refc` và `type`.

## 3. `findVirtual` — tìm phương thức instance

Chữ ký:

```java
MethodHandle handle = lookup.findVirtual(
    SomeClass.class,
    "methodName",
    MethodType.methodType(ReturnType.class, ParamType.class)
);
```

Cho phương thức Java `String greet(String prefix)` của `Person`:

- Kiểu **tìm** là `(String)String`.
- Kiểu **handle** là `(Person,String)String`, vì `Person` là receiver.
- Khi gọi, truyền instance của `Person` trước chuỗi `prefix`.

Đối với phương thức instance có thể override, dispatch vẫn dựa trên đối tượng nhận lời gọi: handle tìm qua lớp cha có thể thực thi override của lớp con. Đừng hiểu “virtual” là lời hứa override cho mọi phương thức: `final` không thể override; private có các quy tắc gọi riêng.

`findVirtual` không được dùng để tìm constructor hay phương thức `static`. Nhầm loại thành viên sẽ khiến tra cứu thất bại, thay vì tự chuyển sang `findStatic`.

## 4. `findStatic` — tìm phương thức cấp lớp

Chữ ký:

```java
MethodHandle handle = lookup.findStatic(
    Utility.class,
    "parse",
    MethodType.methodType(int.class, String.class)
);
```

Một hàm `static int parse(String text)` có kiểu tìm và kiểu handle đều là `(String)int`. **Không truyền đối tượng `Utility`** khi gọi handle. Tên lớp trong `refc` phục vụ tra cứu, không biến thành tham số runtime.

Đừng lẫn `static` với việc gọi một phương thức instance qua biến tham chiếu lớp: chỉ phương thức thực sự khai báo `static` mới phù hợp với `findStatic`. Các kiểm tra quyền truy cập cũng áp dụng như đối với `findVirtual`.

## 5. `findConstructor` — tạo đối tượng có kiểm soát kiểu

Chữ ký:

```java
MethodHandle ctor = lookup.findConstructor(
    Person.class,
    MethodType.methodType(void.class, String.class)
);
```

Giả sử `Person(String name)` là constructor. Phần `MethodType` khi **tra cứu** có kiểu `(String)void`, vì constructor trong bytecode không khai báo kiểu trả về. Nhưng `ctor.type()` có kiểu `(String)Person` và khi gọi sẽ trả về instance `Person` mới.

Điểm cần nhớ:

- Không viết `MethodType.methodType(Person.class, String.class)` vào `findConstructor`: tham số `type` bắt buộc trả về `void`.
- Không có đối tượng receiver khi tạo object; constructor handle trả về instance mới.
- Nếu lớp không thể khởi tạo hoặc constructor không tồn tại/không truy cập được theo điều kiện tương ứng, quá trình tra cứu hoặc lời gọi sẽ thất bại. Ví dụ một lớp trừu tượng không thể được khởi tạo bằng cách dùng handle này.

## 6. `findSpecial` — gọi phiên bản “đặc biệt” theo quyền của lớp gọi

Chữ ký:

```java
MethodHandle handle = lookup.findSpecial(
    Parent.class,
    "methodName",
    MethodType.methodType(String.class),
    Child.class
);
```

`findSpecial` phản ánh cách JVM thực hiện một số lời gọi `invokespecial`, ví dụ lời gọi `super.method()` hợp lệ trong ngữ cảnh lớp con. Nó **không** chỉ là biến thể có thêm một tham số của `findVirtual`.

Giả sử `Child extends Parent` và override `label()`:

- Gọi thông thường `child.label()` chạy `Child.label()`.
- Nếu mã trong ngữ cảnh `Child` có quyền tra cứu đặc biệt với `Parent.class` và `specialCaller = Child.class`, handle phù hợp có thể chạy `Parent.label()` trên chính `Child` đó mà không dispatch sang override.
- Đối số đầu tiên khi gọi handle này là receiver kiểu `Child`; `specialCaller` ảnh hưởng đến **ngữ nghĩa và kiểm soát truy cập** chứ không phải tham số tùy chọn khi invoke.
- Tạo lookup từ lớp không có special-caller access phù hợp thường dẫn đến `IllegalAccessException`; không thể tùy tiện chọn một lớp bất kỳ làm `specialCaller`.

`findSpecial` cũng xuất hiện trong các tình huống gọi phương thức private/default interface theo ngữ nghĩa đặc biệt, nhưng chi tiết quyền truy cập phụ thuộc lớp, interface và module. Với mục tiêu gọi instance thông thường, dùng `findVirtual`; chỉ dùng `findSpecial` khi cần và được phép giữ rõ ngữ nghĩa gọi từ lớp cụ thể.

## 7. Ví dụ đầy đủ chạy được trên Java 17+

Lưu đoạn sau vào file `LookupDemo.java` theo UTF-8. Chương trình dùng cả bốn API, bao gồm một lời gọi `super` thực sự được giải quyết bằng `findSpecial` ngay trong lớp `Child`.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupDemo {
    static class Person {
        private final String name;

        Person(String name) {
            this.name = name;
        }

        String greet(String prefix) {
            return prefix + ", " + name;
        }

        static String badge(int id) {
            return "ID-" + id;
        }
    }

    static class Base {
        String label() {
            return "Base";
        }
    }

    static class Child extends Base {
        @Override
        String label() {
            return "Child";
        }

        String callBase() throws Throwable {
            // Lookup được tạo bên trong Child: đúng ngữ cảnh special caller.
            MethodHandle parent = MethodHandles.lookup().findSpecial(
                Base.class,
                "label",
                MethodType.methodType(String.class),
                Child.class
            );
            return (String) parent.invokeExact((Child) this);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Constructor: tìm (String)void, nhận handle (String)Person.
        MethodHandle constructor = lookup.findConstructor(
            Person.class,
            MethodType.methodType(void.class, String.class)
        );

        // Virtual: tìm (String)String, nhận (Person,String)String.
        MethodHandle virtual = lookup.findVirtual(
            Person.class,
            "greet",
            MethodType.methodType(String.class, String.class)
        );

        // Static: tìm và nhận (int)String.
        MethodHandle fixed = lookup.findStatic(
            Person.class,
            "badge",
            MethodType.methodType(String.class, int.class)
        );

        Person person = (Person) constructor.invokeExact("Lan");
        System.out.println((String) virtual.invokeExact(person, "Chào"));
        System.out.println((String) fixed.invokeExact(7));

        Child child = new Child();
        System.out.println(child.label());
        System.out.println(child.callBase());
    }
}
```

Biên dịch và chạy trong thư mục có file nguồn:

```bash
javac -encoding UTF-8 LookupDemo.java
java LookupDemo
```

Đầu ra:

```text
Chào, Lan
ID-7
Child
Base
```

Giải thích từng bước:

1. `constructor.invokeExact("Lan")` tạo `Person`, yêu cầu Java compiler thấy kiểu trả về chính xác là `Person`.
2. `virtual.invokeExact(person, "Chào")` truyền receiver trước tham số. Kết quả là lời chào dùng tên của đối tượng.
3. `fixed.invokeExact(7)` chỉ nhận `int` vì `badge` là phương thức static.
4. `child.label()` theo dispatch thông thường cho ra `Child`, nhưng `child.callBase()` tạo handle trong đúng ngữ cảnh `Child` để gọi `Base.label()` và cho ra `Base`.

Ví dụ đặt `Person`, `Base` và `Child` trong cùng lớp bao nên quyền truy cập dễ kiểm soát. Nếu chuyển chúng sang package/module khác, cần xét lại modifier của lớp/phương thức và quyền của `Lookup`, không giả định mọi lookup vẫn hợp lệ.

## 8. `invokeExact`, `invoke` và thay đổi kiểu

Tra cứu thành công mới là bước một; lời gọi handle cần thỏa kiểu.

- `invokeExact` yêu cầu kiểu tham số **và kiểu trả về nhìn từ vị trí gọi** khớp chính xác với `handle.type()`. Với lời gọi có kết quả, ép kiểu tường minh `(String)` hoặc `(Person)` như ví dụ giúp compiler xác lập expected return type. Nếu chữ ký không trùng sẽ có `WrongMethodTypeException` khi thực thi.
- `invoke` cho phép một số phép thích nghi kiểu tương đương `asType` (ví dụ boxing/unboxing hoặc ép kiểu tham chiếu hợp lệ); không có nghĩa là mọi kiểu đều chuyển đổi được.
- `handle.asType(targetType)` tạo handle thích nghi theo quy tắc chuyển đổi cho phép; nó có thể báo `WrongMethodTypeException` nếu không thể thích nghi.
- `invokeWithArguments` hữu ích với danh sách đối số động và có thể thực hiện boxing/chuyển đổi; bù lại, nó không thay thế việc thiết kế chữ ký chính xác khi hiệu năng và an toàn kiểu là ưu tiên.

Ví dụ xử lý lời gọi `virtual` trong chương trình trên:

```java
// virtual.type() là (LookupDemo.Person,String)String
String result = (String) virtual.invokeExact(person, "Chào");

// Với invokeExact, không thể tùy ý bỏ receiver:
// virtual.invokeExact("Chào"); // Sai chữ ký ở vị trí gọi.
```

Đoạn này **chỉ minh họa khi được đặt trong `main` ở ví dụ đầy đủ**, nơi các biến `virtual` và `person` đã tồn tại; không phải file Java độc lập.

## 9. Lỗi thường gặp, nguyên nhân và cách xử lý

| Hiện tượng | Nguyên nhân tiêu biểu | Cách kiểm tra/sửa |
| --- | --- | --- |
| `NoSuchMethodException` lúc `find*` | Sai tên, overload, kiểu tham số/kết quả; nhầm static với instance | Đối chiếu khai báo thực tế và `MethodType`; chọn đúng API |
| `IllegalAccessException` lúc tra cứu | Lookup không có quyền của lớp/thành viên hoặc không có special-caller access | Xét vị trí tạo `lookup()`, modifier, package và module; chỉ dùng `privateLookupIn` khi có quyền |
| `WrongMethodTypeException` khi gọi | Chữ ký ở `invokeExact` khác `handle.type()`, kể cả kiểu kết quả | In `handle.type()`; kiểm tra receiver, `int`/`Integer`, kiểu kết quả và cast |
| `ClassCastException`/lỗi chuyển đổi lúc invoke | Đối số runtime không khớp phép chuyển đổi được yêu cầu | Kiểm tra kiểu runtime, `asType` và đường chuyển đổi thực sự |
| Gọi override thay vì lớp cha | Dùng `findVirtual` nhưng mong hành vi `super` | Dùng `findSpecial` trong special-caller context hợp lệ |
| Constructor lookup thất bại | Đặt return type là lớp thay vì `void`, hoặc nhầm danh sách tham số | Tra cứu constructor bằng `MethodType.methodType(void.class, ...)` |
| Lời gọi thiếu/thừa đối số | Quên receiver của virtual/special hoặc thêm receiver vào static/constructor | So sánh `handle.type()` với bảng ở mục 1 |

Các API tra cứu nêu trên khai báo `NoSuchMethodException` và `IllegalAccessException`. `MethodHandle.invokeExact`/`invoke` có thể ném `Throwable`, nên ví dụ sử dụng `throws Throwable` để dễ quan sát; trong ứng dụng thật hãy chọn cách xử lý ngoại lệ phù hợp.

## 10. Truy cập, kế thừa và module Java

`Lookup` là **capability có kiểm tra quyền**. Một reference đến `Class<?>` hoặc tên phương thức không tự cấp quyền. Vài nguyên tắc thực tế:

1. Tạo `MethodHandles.lookup()` trong đúng lớp/ngữ cảnh cần tra cứu. Di chuyển đoạn code sang helper khác sẽ đổi lớp sở hữu lookup, có thể đổi khả năng truy cập thành viên.
2. Phương thức public của public class chưa chắc đủ khi lớp nằm trong package không được module export cho bên gọi. Truy cập private qua module khác còn liên quan đến package `opens` và các điều kiện của `privateLookupIn`.
3. Với phương thức override, `findVirtual` thường là lựa chọn phản ánh polymorphism. Với `super` có chủ đích, `findSpecial` phải được kiểm tra bằng một case cụ thể trong hệ phân cấp lớp đang dùng.
4. Không dùng `setAccessible(true)` của Reflection như giả định rằng lookup của MethodHandle tự động có cùng quyền. Đây là hai cơ chế truy cập khác nhau.
5. Khi tra cứu thất bại, nên chẩn đoán đúng modifier, module và chữ ký trước khi thay đổi cấu hình JVM; không mở quyền module rộng chỉ để tránh hiểu nguyên nhân.

## 11. Chọn API qua các tình huống

- Gọi `user.getName()` trên nhiều instance: tra `findVirtual(User.class, "getName", methodType(String.class))`; truyền từng `User` làm đối số đầu của handle.
- Gọi hàm tiện ích `Math.max(int,int)`: tra `findStatic(Math.class, "max", methodType(int.class, int.class, int.class))`; truyền trực tiếp hai số nguyên.
- Tạo `new ArrayList<>(initialCapacity)`: tra `findConstructor(ArrayList.class, methodType(void.class, int.class))`; kết quả của handle là một `ArrayList`.
- Gọi phiên bản ở lớp cha dù lớp con có override: cân nhắc `findSpecial` **bên trong đúng ngữ cảnh lớp con được phép**; không dùng nó như lối tắt gọi thành viên tùy ý từ code ngoài lớp.

Một trình tự giải bài thực hành hiệu quả: **xác định loại thành viên → viết chữ ký khai báo → chọn `find*` → in `handle.type()` → kiểm tra quyền lookup → gọi đúng receiver và kiểu kết quả → đối chiếu output**. Nếu người học nắm được sự khác nhau giữa kiểu tìm và kiểu handle, phần lớn lỗi thực tế sẽ trở nên dễ xác định hơn.

## 12. Tự kiểm tra

1. Vì sao `findVirtual` nhận `MethodType` không chứa receiver nhưng handle lại chứa receiver?
2. Tại sao `findConstructor` yêu cầu return type `void` trong lúc handle trả về object?
3. Khi một lớp con override `label()`, làm sao phân biệt lời gọi virtual với lời gọi special đến bản của lớp cha?
4. `WrongMethodTypeException` có thể xảy ra vì kiểu kết quả ở vị trí `invokeExact` khác với handle hay không?
5. Khi cùng một lời tra cứu chạy được trong lớp `Child` nhưng thất bại sau khi chuyển sang một helper ở module khác, cần kiểm tra những quyền nào?

**Kết quả cần đạt:** phân biệt được cả bốn hình thức tra cứu, tự viết đúng `MethodType`, đọc được `MethodHandle.type()`, thực hiện lời gọi và giải thích được các lỗi về chữ ký cũng như quyền truy cập.
