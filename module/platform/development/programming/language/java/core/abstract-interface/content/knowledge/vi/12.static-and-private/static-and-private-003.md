# Static method không được kế thừa bởi interface con hoặc lớp triển khai

Một static method khai báo trong interface thuộc về interface đó. Quan hệ `extends` giữa các interface và `implements` giữa class với interface **không làm static method trở thành thành viên được kế thừa**. Quy tắc này khác với static method của class, vốn có thể được class con kế thừa và che khuất theo các quy tắc riêng.

## 1. Interface con kế thừa default method nhưng không kế thừa static method

~~~java
interface ParentApi {
    static String version() {
        return "parent";
    }

    default String greet() {
        return "hello";
    }
}

interface ChildApi extends ParentApi {
    static String version() {
        return "child";
    }
}

final class ApiImpl implements ChildApi {
    static String version() {
        return "class";
    }
}

public class Main {
    public static void main(String[] args) {
        System.out.println(ParentApi.version());
        System.out.println(ChildApi.version());
        System.out.println(ApiImpl.version());

        ParentApi api = new ApiImpl();
        System.out.println(api.greet());
    }
}
~~~

Biên dịch trên JDK 8 trở lên bằng `javac -encoding UTF-8 --release 8 Main.java` rồi chạy `java Main`. Stdout:

~~~text
parent
child
class
hello
~~~

`ChildApi.version` là một static method mới do `ChildApi` khai báo; nó không override `ParentApi.version`. Tương tự, `ApiImpl.version` là method của class, độc lập với các static method của interface. Ba lời gọi được chọn theo tên kiểu ở bên trái dấu chấm.

Ngược lại, `greet` là default instance method được kế thừa từ `ParentApi`. Lời gọi `api.greet()` hợp lệ vì nó đi qua một đối tượng triển khai interface.

Nếu `ChildApi` không tự khai báo `version`, biểu thức `ChildApi.version()` sẽ không hợp lệ. Phải gọi `ParentApi.version()` bằng đúng tên interface khai báo method.

## 2. Class implements không phải triển khai static method

Class triển khai chỉ phải cung cấp các abstract instance method còn thiếu. Static method của interface không tạo ra nghĩa vụ implementation, cũng không được class kế thừa như một method của chính class.

~~~java
interface Codec {
    static String encode(String value) {
        return "[" + value + "]";
    }

    String decode(String text);
}

final class BracketCodec implements Codec {
    @Override
    public String decode(String text) {
        return text.substring(1, text.length() - 1);
    }
}
~~~

`Codec.encode("Java")` hợp lệ. Các lời gọi sau không hợp lệ nếu `BracketCodec` không tự khai báo method tương ứng:

~~~java
// BracketCodec.encode("Java");
// new BracketCodec().encode("Java");
// Codec codec = new BracketCodec();
// codec.encode("Java");
~~~

Đừng nhầm lỗi ở `BracketCodec.encode` với lỗi quyền truy cập: method `Codec.encode` là public, nhưng vẫn không được kế thừa vào class. Quyền truy cập và quy tắc kế thừa là hai vấn đề khác nhau.

## 3. Static method cùng tên không phải override

Một subinterface hoặc class triển khai có thể tự khai báo static method trùng tên với static method của interface cha nếu không xung đột với một instance method được kế thừa. Các khai báo static này độc lập. Không dùng `@Override` để đánh dấu chúng.

~~~java
interface Root {
    static int parse(String value) {
        return Integer.parseInt(value);
    }
}

interface StrictRoot extends Root {
    static int parse(String value) {
        return Root.parse(value) + 1;
    }
}
~~~

`Root.parse("10")` trả về `10`, còn `StrictRoot.parse("10")` trả về `11`. Method ở interface con tự định nghĩa hành vi của nó; nó không thay thế method ở interface cha.

Có một ranh giới quan trọng: nếu interface cha đã có default hoặc abstract instance method với một chữ ký, interface con không thể khai báo static method cùng chữ ký để thay thế method instance được kế thừa. Static và instance method không thể được trộn như thể chúng là cùng một extension point.

## 4. So sánh với static method của class

~~~java
class Base {
    static String kind() {
        return "base";
    }
}

class Derived extends Base {
}
~~~

`Derived.kind()` hợp lệ vì class con có thể kế thừa static method phù hợp từ superclass. Nếu class con khai báo một static method tương ứng, đó là *method hiding*, không phải overriding đa hình.

Với interface, static method không được kế thừa xuống subinterface hoặc class implements. Cũng đừng khái quát rằng mọi thành viên static đều có cùng quy tắc: field của interface là `public static final` và có thể được kế thừa theo quy tắc áp dụng cho field, trong khi static method thì không.

| Trường hợp | Quy tắc |
|---|---|
| Class con kế thừa static method của class cha | Có thể; method cùng chữ ký ở class con có thể che khuất method cha |
| Interface con kế thừa static method của interface cha | Không |
| Class implements kế thừa static method của interface | Không |
| Interface con kế thừa default instance method | Có, theo quy tắc kế thừa và xử lý xung đột |
| Class implements phải override static method của interface | Không |

**Tự kiểm tra**

- `ChildApi.version()` có gọi được method chỉ được khai báo trong `ParentApi` không? **Không.**
- Class triển khai có phải implement static method của interface không? **Không.**
- Nếu subtype tự khai báo static method trùng tên, nó có override method của interface cha không? **Không; đó là khai báo riêng.**