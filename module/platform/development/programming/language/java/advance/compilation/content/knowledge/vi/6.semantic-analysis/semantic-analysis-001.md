# Kiểm tra quyền truy cập và tính hợp lệ của tham chiếu kiểu trong Java

## 1. Kiểm tra ngữ nghĩa diễn ra sau khi mã đã đúng cú pháp

Một chương trình có thể viết đúng cú pháp Java nhưng vẫn bị trình biên dịch từ chối. Ví dụ, câu lệnh `new Hidden()` có thể đúng ngữ pháp, song class `Hidden` không hiện diện hoặc không thể truy cập từ vị trí gọi. Tương tự, một biến kiểu `List<String>` có cú pháp hợp lệ, nhưng khai báo `List<int>` là không hợp lệ vì đối số kiểu của generic phải là kiểu tham chiếu.

Ở giai đoạn phân tích ngữ nghĩa, `javac` cần giải quyết một chuỗi vấn đề:

1. **Phân giải tên:** định danh `User`, `api.User` hoặc `List` đang chỉ tới khai báo nào? Khai báo có nằm trong phạm vi nhìn thấy (scope) và nguồn/classpath/module path không?
2. **Kiểm tra khả năng truy cập:** khai báo class, interface, constructor, field hoặc method có được phép sử dụng từ ngữ cảnh hiện tại theo `public`, `protected`, package-private, `private` và ranh giới module không?
3. **Kiểm tra tính đúng đắn của kiểu:** cách tham chiếu có đúng loại kiểu, số lượng/giới hạn generic arguments, tính tương thích của phép gán, ép kiểu, tham số method và ngữ cảnh `static` không?
4. **Lựa chọn hành vi tại thời điểm compile:** phương thức overload nào áp dụng, thành viên nào có thể được gọi, giá trị `null`/lambda/method reference có đúng target type không?

Chỉ khi các điều kiện cần thiết được thỏa mãn, compiler mới tạo bytecode. **Một kiểu tìm thấy được chưa chắc truy cập được; một kiểu truy cập được chưa chắc dùng đúng về mặt type checking.**

Ví dụ lỗi có bản chất khác nhau:

~~~java
// Minh họa lỗi, không phải chương trình Java độc lập.
UnknownType a;             // Không phân giải được tên kiểu.
java.util.List<int> b;     // Generic argument không được là primitive.
String s = 42;             // Hai kiểu không tương thích.
~~~

Không nên “sửa” các lỗi này bằng cast tùy tiện hay tăng phạm vi truy cập tất cả thành `public`. Cần tìm đúng bước thất bại trong chuỗi phân giải tên → kiểm tra truy cập → kiểm tra kiểu.

## 2. Bảng quyền truy cập: type và member

Java có bốn mức truy cập quen thuộc đối với **thành viên của class**. Mức không có từ khóa truy cập thường được gọi là *package-private*.

| Modifier | Cùng class | Cùng package | Subclass khác package | Mã khác package không kế thừa |
| --- | --- | --- | --- | --- |
| `public` | Có | Có | Có | Có, nếu type/module cho phép |
| `protected` | Có | Có | Có, với điều kiện riêng | Không |
| Không modifier (package-private) | Có | Có | Không | Không |
| `private` | Có | Không, ngoại trừ quy tắc nestmate | Không, ngoại trừ quy tắc nestmate | Không |

Bảng là tóm tắt **kiểm tra quyền truy cập ở mức mã nguồn**. Có các chi tiết cần đọc kèm:

- Một **top-level class/interface** chỉ được khai báo `public` hoặc package-private; không khai báo top-level `private` hay `protected`.
- Một **nested class/interface** có thể có modifier phù hợp với nơi khai báo; muốn dùng `Outer.Inner` thì cần xét cả khả năng truy cập `Outer` lẫn `Inner`.
- Các thành viên `private` của hai nested class cùng *nest* có thể được phép truy cập lẫn nhau theo quy tắc Java, nên không thể giản lược rằng “khác class nào cũng không được”. Đây là phạm vi nestmate, không có nghĩa tất cả class cùng package đều được truy cập private.
- `protected` ở package khác **không tương đương** “mọi đối tượng kiểu base class đều truy cập được”; có thêm điều kiện về subclass và kiểu của biểu thức qualifier.
- Quyền `public` của class chưa đủ khi dùng Java Platform Module System (JPMS): package còn phải được export và module phụ thuộc phải đọc được module cung cấp.
- **Khả năng truy cập của kiểu chứa** cũng cần hợp lệ: một public method không làm cho một enclosing class không truy cập được trở thành truy cập được.

Có thể nhớ theo hai trục: *khai báo nào đang được truy cập* (top-level type, nested type, constructor, field, method) và *ngữ cảnh thực hiện truy cập* (package, subclass, qualifier, module).

## 3. Public, package-private và private qua ví dụ package

Xét ba khai báo minh họa sau, mỗi đoạn nằm trong file được ghi rõ.

Tệp `src/api/java/api/PublicApi.java`:

~~~java
package api;

public class PublicApi {
    private int secret = 13;
    int packageCode = 5;

    public int getSecret() {
        return secret;
    }
}
~~~

Tệp `src/api/java/api/Helper.java`:

~~~java
package api;

class Helper {
    static String label() {
        return "internal";
    }
}
~~~

Tệp `src/client/java/client/Client.java`:

~~~java
package client;

import api.PublicApi;

public class Client {
    public static void main(String[] args) {
        PublicApi api = new PublicApi();
        System.out.println(api.getSecret());
    }
}
~~~

Lời gọi `api.getSecret()` hợp lệ: `PublicApi` và method đều `public`, `getSecret()` được tự đọc field `private` trong class sở hữu. Không có câu lệnh ở `client.Client` nào trực tiếp đụng tới `secret`, `packageCode` hay `Helper`.

Các dòng dưới đây **cố ý sai**, chỉ dùng để phân tích, không được thêm vào file đang compile:

~~~java
// Trong client.Client (khác package api):
System.out.println(api.secret);       // secret là private.
System.out.println(api.packageCode);  // packageCode là package-private.
api.Helper h;                         // api.Helper là top-level package-private.
~~~

Import một tên không cấp thêm quyền. `import api.Helper;` vẫn không cho package `client` dùng `api.Helper`. Hai class khai báo cùng package có thể truy cập thành viên package-private của nhau theo quy tắc package, dù nằm trong hai source root khác nhau; đường dẫn thư mục chỉ là cách tổ chức nguồn, **khai báo package** mới định nghĩa quan hệ package ở ngôn ngữ Java (kết hợp ranh giới module khi có).

Với `private`, class chứa có thể cung cấp một public accessor có kiểm soát thay vì mở field. Không cần tự động tạo getter cho mọi field; cung cấp API phù hợp với bất biến của class.

## 4. Trường hợp quan trọng: protected giữa các package

`protected` cho phép truy cập trong cùng package; bên ngoài package, một subclass chỉ được truy cập thành viên protected theo các điều kiện thêm của Java Language Specification.

Tạo đúng các tệp sau trong một ví dụ độc lập. Dùng ba thư mục source, output mô tả bằng đường dẫn thực tế; không cần thư viện ngoài.

### 4.1. `src/api/java/api/Parent.java`

~~~java
package api;

public class Parent {
    protected int number = 7;
    private int secret = 13;

    public int readSecret() {
        return secret;
    }
}
~~~

`Parent` là public. `number` là protected instance field; `secret` là private. Do không tự khai báo constructor, class có public default constructor phù hợp với quyền của top-level public class.

### 4.2. `src/client/java/client/Child.java`

~~~java
package client;

import api.Parent;

public class Child extends Parent {
    public int total(Child peer) {
        return this.number + peer.number;
    }
}
~~~

`Child` được phép đọc `this.number` vì nó là subclass của `Parent`. Ở package khác, `peer.number` cũng hợp lệ trong method của `Child` vì kiểu tĩnh của qualifier `peer` là `Child`, một kiểu con phù hợp.

Ngược lại, đoạn sau **không thể biên dịch** khi đặt vào `Child`:

~~~java
// Sai: định nghĩa minh họa, không chèn vào class chạy được.
public int invalid(Parent other) {
    return other.number;
}
~~~

Tuy `Child` là subclass, kiểu tĩnh của biểu thức `other` vẫn là `Parent`. Khi truy cập instance field/method `protected` của superclass qua một biểu thức trong package khác, kiểu qualifier phải là subclass đang thực hiện truy cập (hoặc subtype thích hợp của subclass ấy); biểu thức có kiểu `Parent` không đạt điều kiện này. Quy tắc nhằm bảo vệ quyền truy cập qua các đối tượng superclass không thuộc miền subclass hiện tại.

Một class khác trong package `client` nhưng **không** kế thừa `Parent` cũng không được dùng `child.number` chỉ vì nó ở cùng package với `Child`: package sở hữu khai báo `number` là `api`.

Đối với constructor `protected`, quy tắc truy cập khác với field/method: trong subclass khác package có thể gọi constructor superclass qua `super(...)` theo các quy tắc constructor invocation, nhưng không được mặc định suy ra rằng có thể gọi `new Parent(...)` ở mọi vị trí.

### 4.3. `src/client/java/client/Main.java`

~~~java
package client;

import api.Parent;

public class Main {
    public static void main(String[] args) {
        Parent parent = new Parent();
        Child child = new Child();

        System.out.println(parent.readSecret());
        System.out.println(child.total(new Child()));
    }
}
~~~

Để chạy Java 17+, mở terminal tại thư mục gốc chứa `src/`. Với Bash trên Linux/macOS/Git Bash:

~~~bash
mkdir -p out/api out/client
javac --release 17 -encoding UTF-8 -d out/api src/api/java/api/Parent.java
javac --release 17 -encoding UTF-8 -cp out/api -d out/client src/client/java/client/Child.java src/client/java/client/Main.java
java -cp out/api:out/client client.Main
~~~

Stdout dự kiến chính xác:

~~~text
13
14
~~~

Trên Windows/PowerShell, tạo hai thư mục output bằng lệnh phù hợp (ví dụ `New-Item -ItemType Directory -Force out/api, out/client`) và dùng dấu `;` ngăn cách classpath:

~~~powershell
java -cp 'out/api;out/client' client.Main
~~~

Đây là ví dụ có đủ class được khai báo, file/class name khớp và đường biên dịch tách hai package. Lệnh `javac` không có output khi thành công. Các đoạn lỗi được chú thích ở trên là **minh họa không độc lập**, không đưa vào ba file của ví dụ chạy.

## 5. Quyền truy cập của constructor, nested type và interface

Kiểm tra quyền không chỉ áp dụng cho field:

- **Constructor:** muốn `new T(...)`, cả class `T` lẫn constructor phù hợp phải truy cập được. Một class public có constructor private vẫn không thể bị khởi tạo từ class ngoài theo cách thông thường.
- **Method:** method có thể `public` hoặc `protected`, nhưng kiểu của receiver, method overload được chọn và ngữ cảnh gọi vẫn phải hợp lệ. `import` không mở quyền member.
- **Nested type:** `Outer.Inner` phải thỏa quy tắc truy cập cho từng cấp. Một `private static class Inner` không dùng trực tiếp được từ nơi ngoài nest, kể cả khi `Outer` là public.
- **Interface:** field trong interface mặc định `public static final`; nested type trong interface mặc định có tính `public static`; method interface có quy tắc modifier riêng, bao gồm public abstract/default/static và private helper method từ Java 9. Đừng áp bảng modifier của class cho mọi vị trí interface một cách máy móc.
- **Top-level type:** `public class Account` ở tệp nguồn thông thường phải đặt trong `Account.java`, và một compilation unit không thể có nhiều public top-level type có tên đòi tên file khác nhau.

Ví dụ sử dụng factory với constructor private, một chương trình Java độc lập tên `TokenDemo.java`:

~~~java
public class TokenDemo {
    public static void main(String[] args) {
        Token token = Token.of("abc");
        System.out.println(token.value());
    }
}

final class Token {
    private final String value;

    private Token(String value) {
        this.value = value;
    }

    public static Token of(String value) {
        return new Token(value);
    }

    public String value() {
        return value;
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TokenDemo.java
java TokenDemo
~~~

Stdout:

~~~text
abc
~~~

`TokenDemo` truy cập được top-level package-private class `Token` vì cả hai ở unnamed package của cùng source file, và gọi được public static factory. Nhưng nếu thay `Token.of("abc")` bằng `new Token("abc")` trong `TokenDemo`, `javac` từ chối vì constructor của `Token` là private. Sự tồn tại của method public không làm private constructor thành public.

Lưu ý ví dụ package mặc định chỉ phù hợp để học bằng một file. Trong mã dự án thực, nên khai báo package rõ ràng.

## 6. Phân giải tên kiểu: tên đơn, tên đầy đủ, scope và import

Khi thấy `List`, `Outer.Inner` hoặc `api.PublicApi`, compiler phải biết chúng chỉ đúng một khai báo hợp lệ. Cần phân biệt:

- **Tên đầy đủ:** `java.util.List` chỉ rõ package và tên type, giúp tránh trùng tên trong code.
- **Single-type import:** `import java.util.List;` cho phép dùng tên đơn `List` khi không có xung đột theo quy tắc của Java.
- **Import-on-demand:** `import java.util.*;` làm các type public thích hợp có thể được xét; nó **không** import mọi package con như `java.util.concurrent`.
- **Member/nested type import:** `import java.util.Map.Entry;` cho phép dùng `Entry` trực tiếp nếu hợp lệ; import static dùng cho static members hoặc static nested types theo cú pháp riêng.
- **Scope và shadowing:** một type variable, local class, member type hoặc type cùng package có thể làm thay đổi kết quả tên đơn được phân giải. Import hai type có tên đơn xung đột có thể gây lỗi ambiguity.
- **Không tồn tại / chưa có trên đường tìm:** thiếu dependency trong classpath/module path hoặc source root sai dẫn tới lỗi symbol/package, dù identifier viết đúng.

Ví dụ minh họa ambiguity:

~~~java
// Sai nếu dùng tên List không được giải quyết duy nhất.
import java.awt.*;
import java.util.*;

class Ambiguous {
    List names;
}
~~~

Cả `java.awt.List` và `java.util.List` đều có thể được xem xét khi dùng import-on-demand, nên tên `List` không rõ nghĩa. Giải quyết bằng `import java.util.List;` hoặc dùng `java.util.List` đầy đủ. **Thêm import không giúp vượt qua access modifier**: nếu type bị chặn do private/package-private/module exports, phải sửa cách sử dụng hoặc API.

Một tên kiểu còn có thể nằm ngoài **scope** của type parameter: ví dụ `T` khai báo tại method generic chỉ tồn tại trong phạm vi khai báo đó, không thể dùng tùy ý ở method khác.

## 7. Tính hợp lệ của tham chiếu kiểu: generic arguments và bounds

Không phải tên type hợp lệ là có thể dùng với mọi type arguments. Java kiểm tra *arity* (số lượng tham số kiểu), *bounds* và khả năng hình thành parameterized type.

Ví dụ hợp lệ:

~~~java
import java.util.List;

public class GenericDemo {
    static <T extends Number> T first(List<T> values) {
        return values.get(0);
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(4, 5);
        Number firstNumber = first(numbers);
        System.out.println(firstNumber);
    }
}
~~~

Lưu file `GenericDemo.java` và chạy:

~~~bash
javac --release 17 GenericDemo.java
java GenericDemo
~~~

Stdout:

~~~text
4
~~~

`List<Integer>` là hợp lệ vì `List` nhận một type argument, `Integer` là reference type, và `Integer` đáp ứng bound `T extends Number` của method `first`. Giá trị trả về được gán cho `Number` nhờ quan hệ subtype.

Các đoạn sau cố ý **không hợp lệ** (minh họa, không thêm vào `GenericDemo.java` đang chạy):

~~~java
java.util.List<int> values;           // int là primitive, không là type argument.
java.util.Map<String> index;          // Map cần hai type arguments.
java.util.List<String> words = java.util.List.of("a");
Number n = first(words);              // T phải extends Number; String không thỏa.
java.util.List<String> names = java.util.List.of(1); // Kiểu phần tử không tương thích.
~~~

Autoboxing hỗ trợ phép truyền giá trị primitive trong những ngữ cảnh thích hợp (chẳng hạn `List.of(1)` suy ra `Integer`) nhưng **không** làm `List<int>` trở thành một khai báo đúng. Java generic bất biến theo type argument: `List<Integer>` không phải subtype của `List<Number>`, dù `Integer` là subtype của `Number`.

Wildcard cũng có giới hạn sử dụng:

~~~java
java.util.List<? extends Number> readable = java.util.List.of(1, 2);
Number firstValue = readable.get(0);       // Hợp lệ.
~~~

Với `List<? extends Number>`, không thể tùy ý thêm một `Integer` vào list: kiểu phần tử thực tế có thể là một subtype khác của `Number`. Dùng `List<? super Integer>` khi cần thêm `Integer` phù hợp với vai trò consumer. Đây là **kiểm tra an toàn kiểu ở compile time**, không phải kiểm tra quyền truy cập.

Các phép tham chiếu kiểu còn phải tôn trọng giới hạn của generic ở runtime; ví dụ `new java.util.ArrayList<String>[2]` bị cấm vì generic array creation, và `instanceof java.util.List<String>` không hợp lệ vì parameterized type đó không reifiable cho phép kiểm tra như vậy. `instanceof java.util.List<?>` là dạng kiểm tra có thể sử dụng.

## 8. Tính tương thích khi gán, gọi method và ép kiểu

Phân tích ngữ nghĩa không dừng ở khả năng truy cập:

- **Gán:** biểu thức bên phải có tương thích phép gán với kiểu bên trái không? `Object obj = "text";` hợp lệ; `String text = new Object();` không hợp lệ.
- **Tham số method:** kiểu đối số có phù hợp với phương thức được chọn không? Ví dụ `Integer.parseInt("12")` hợp lệ, `Integer.parseInt(12)` không phù hợp overload nhận String.
- **Overload:** compiler xác định phương thức áp dụng và chọn phương thức cụ thể nhất theo quy tắc; có trường hợp các overload cùng phù hợp gây ambiguity, chẳng hạn gọi `m(null)` khi tồn tại `m(String)` và `m(Integer)`.
- **Casts:** phép cast chỉ được chấp nhận khi ngôn ngữ cho phép chuyển kiểu theo quy tắc tương ứng. Cast được compile **không đảm bảo** chuyển kiểu sẽ thành công ở runtime; có thể phát sinh `ClassCastException`.
- **Kiểu generic:** compiler kiểm tra bounds, inference, wildcard capture và unchecked conversion. Raw types có thể chỉ gây cảnh báo thay vì lỗi, nhưng đánh mất một phần bảo đảm kiểu.
- **Context:** một instance member không thể được tham chiếu như static member từ ngữ cảnh static thiếu instance; `new` không thể khởi tạo abstract class/interface trực tiếp; `void` không thể là kiểu của biến.

Ví dụ hợp lệ trong file `TypeCheckDemo.java`:

~~~java
public class TypeCheckDemo {
    static String twice(String value) {
        return value + value;
    }

    public static void main(String[] args) {
        Object value = "java";
        String text = (String) value;
        System.out.println(twice(text));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TypeCheckDemo.java
java TypeCheckDemo
~~~

Stdout:

~~~text
javajava
~~~

Nếu `value` thực chất là `Integer`, phép cast sang `String` trong ví dụ tương đương sẽ có thể **biên dịch** vì kiểu tĩnh `Object` cho phép kiểm tra kiểu ở runtime, nhưng sẽ ném `ClassCastException`. Điều đó khác với trường hợp compiler chứng minh được hai kiểu không liên quan và không cho phép phép chuyển.

## 9. JPMS thêm kiểm tra readability và exports

Trong ứng dụng không đặt tên module (unnamed module/classpath), nhiều người quen với suy nghĩ “class public trong JAR thì class khác dùng được”. Với Java Platform Module System từ Java 9, cần kiểm tra thêm cả **module graph**.

Khi một named module muốn sử dụng public type trong module khác, thông thường:

1. Module bên sử dụng phải **đọc được (read)** module cung cấp; ví dụ khai báo `requires api.module;` trong `module-info.java`.
2. Package chứa public type phải được module cung cấp **export** cho module bên sử dụng: `exports api;` hoặc export có chọn lọc `exports api to client.module;`.
3. Bản thân type/member vẫn phải truy cập được theo các modifier Java.

`opens` là cơ chế phục vụ deep reflection trong module system; chỉ `opens` package không tương đương với `exports` cho truy cập Java thông thường tại compile time.

Ví dụ độc lập, bố trí file như sau:

~~~text
modulesrc/
├── api.module/
│   ├── module-info.java
│   └── api/Message.java
└── client.module/
    ├── module-info.java
    └── client/Main.java
~~~

Tệp `modulesrc/api.module/module-info.java`:

~~~java
module api.module {
    exports api;
}
~~~

Tệp `modulesrc/api.module/api/Message.java`:

~~~java
package api;

public final class Message {
    public static String text() {
        return "MODULE OK";
    }
}
~~~

Tệp `modulesrc/client.module/module-info.java`:

~~~java
module client.module {
    requires api.module;
}
~~~

Tệp `modulesrc/client.module/client/Main.java`:

~~~java
package client;

import api.Message;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Message.text());
    }
}
~~~

Trên Bash từ thư mục chứa `modulesrc/`:

~~~bash
mkdir -p out/modules
javac --release 17 --module-source-path modulesrc -d out/modules -m api.module,client.module
java --module-path out/modules -m client.module/client.Main
~~~

Stdout:

~~~text
MODULE OK
~~~

Nếu bỏ `exports api;` nhưng giữ `requires api.module;`, package `api` không được module client truy cập theo Java source code; public modifier của `Message` không tự phá được ranh giới module. Nếu bỏ `requires api.module;`, module client thiếu readability dù API module có export package. Đây là hai lỗi khác nhau. Với các tùy chọn `--add-reads` hoặc `--add-exports`, compiler/runtime có thể được mở rộng quan hệ trong môi trường cụ thể, nhưng code module chuẩn nên khai báo chính xác hợp đồng qua `module-info.java`.

## 10. Chẩn đoán lỗi: phân loại thay vì đọc một câu báo lỗi

Thông báo của `javac` có thể thay đổi tùy JDK và vị trí lỗi. Hãy nhận diện nhóm lỗi, không dựa vào việc luôn nhận cùng một chuỗi chữ.

| Triệu chứng | Ý nghĩa ngữ nghĩa thường gặp | Nên kiểm tra |
| --- | --- | --- |
| `cannot find symbol` | Không giải được tên khai báo | Chính tả, package, import, source/class/module path, scope |
| `package ... does not exist` | Không tìm được package theo đường compile | Dependency, source roots và cấu hình module |
| `... is not public ...; cannot be accessed from outside package` | Type hoặc member package-private bị tham chiếu sai package | API cần public thật không, hay caller sai vị trí? |
| `... has private access` | Caller truy cập thành viên/constructor private | Dùng API public phù hợp hoặc thiết kế lại phạm vi |
| `... has protected access` | Caller không đạt quy tắc protected | Package khai báo, subclass, qualifier type |
| `incompatible types` | Gán/cast/argument không đúng type | Expected type và actual type, generic arguments |
| `type argument ... is not within bounds` | Generic bound bị vi phạm | Khai báo `extends`, kiểu cụ thể truyền vào |
| `wrong number of type arguments` | Arity generic không đúng | Số tham số kiểu của khai báo |
| `reference to ... is ambiguous` | Nhiều overload/tên phù hợp không phân định được | Imports, khai báo overload, kiểu tĩnh của đối số |
| `non-static ... cannot be referenced from a static context` | Dùng instance member khi không có instance phù hợp | Tạo/nhận instance, hoặc sửa thiết kế static |
| `package ... is not visible` trong named modules | Module chưa đọc hoặc package chưa export | `requires` và `exports` trong module-info |

Không mọi lỗi truy cập đều có cùng thông điệp; compiler có thể báo lỗi tại dòng `import`, tại kiểu trong signature, tại `new`, hoặc tại phép gọi. Một lỗi về dependency ban đầu cũng có thể kéo theo nhiều lỗi symbol khác. Sửa lỗi gốc trước và build lại.

Một quy trình điều tra thực tế:

1. Xác định **tên đầy đủ** của kiểu cần sử dụng và nơi khai báo, bao gồm package/module.
2. Kiểm tra compiler đã tìm thấy definition chưa: file nguồn có thuộc source set hoặc class/JAR có nằm trong compile classpath/module path không?
3. Nếu tìm thấy, xác định **ngữ cảnh truy cập**: class gọi nằm ở package nào, là subclass của ai, kiểu tĩnh qualifier là gì, module có đọc/export đúng không?
4. Kiểm tra từng kiểu của **receiver, argument, return, generic bound, cast** và ràng buộc `static`/constructor.
5. Chạy lại biên dịch trong output sạch để loại file `.class` cũ; nếu cần, dùng `javac -verbose` để xem compiler đọc file/class từ đâu. Kết quả verbose phụ thuộc JDK, không có stdout cố định.

## 11. Những nhầm lẫn thường dẫn đến “sửa sai chỗ”

**Nhầm 1 — `import` cấp quyền.** Import chỉ giúp tham chiếu tên; access control do modifier và module system quyết định. Không thể import một top-level package-private class từ package khác để làm nó public.

**Nhầm 2 — Bất kỳ subclass nào cũng chạm được field protected của mọi instance base class.** Với instance member protected ở package khác, kiểu qualifier bị giới hạn. `Child` có thể dùng `this.number` hoặc `peer.number` khi `peer` là `Child`; không thể đọc `other.number` với `other` là `Parent` theo ví dụ.

**Nhầm 3 — Tăng tất cả thành public sẽ “chữa” vấn đề type checking.** Quyền truy cập và tính tương thích kiểu là các điều kiện riêng. Public `List` vẫn không chấp nhận `List<int>` hoặc `Map<String>`.

**Nhầm 4 — `ClassCastException` là lỗi của compiler.** Compiler chặn những chuyển đổi không hợp lệ về mặt ngôn ngữ, nhưng một cast được phép về mặt tĩnh có thể vẫn thất bại ở runtime; cần kiểm tra kiểu thực tế khi cast.

**Nhầm 5 — Compiler cho qua nghĩa là API có thể dùng trên mọi module.** Named modules cần readability và exports. Public API trong package không export vẫn bị chặn khi compile client module.

**Nhầm 6 — Một member public có thể được truy cập qua mọi kiểu chứa.** Trước khi xét member, phải xét type chứa, enclosing types, package/module, rồi mới đến modifier của member và tính đúng đắn của phép gọi.

**Nhầm 7 — Cảnh báo unchecked giống lỗi compile.** Dùng raw generic type có thể chỉ báo warning. Không nên vô hiệu hóa warning để che giấu rủi ro, nhưng cũng không nói mọi raw conversion đều bị compiler từ chối.

## 12. Checklist tự kiểm tra kiến thức

Với một tham chiếu `x.method(arg)`, `new T(...)`, `Outer.Inner` hoặc `List<T>`, hãy trả lời lần lượt:

- Tên type/member giải ra khai báo nào? Import, package và scope có gây nhầm/ambiguity không?
- Type chứa có truy cập được không? Top-level type có package-private không? Nested type có modifier riêng không?
- Member/constructor có truy cập được từ vị trí gọi không? Với protected khác package, qualifier có kiểu tĩnh hợp lệ không?
- Nếu có JPMS, module client có readability và package provider có export phù hợp không?
- Type arguments có đúng arity, reference type và bounds không? Generic inference/wildcard có tương thích không?
- Expression có phù hợp kiểu yêu cầu khi gán, gọi overload, return hoặc cast không?
- Chương trình đang dùng instance member trong ngữ cảnh có instance phù hợp hay không?
- Các class/JAR cần thiết có thực sự thuộc đường biên dịch, và kết quả có tái lập từ output sạch không?

**Bài thực hành:** biên dịch ví dụ `Parent`/`Child`/`Main` trong phần 4; ghi lại stdout `13` và `14`. Thử thêm method `invalid(Parent other)` vào `Child` để quan sát lỗi protected, rồi bỏ method ấy. Tiếp đó thử `java.util.List<int>` trong một file thử nghiệm và so sánh lỗi generic với lỗi access. Cuối cùng, dùng ví dụ named modules, bỏ `exports api;` để quan sát lỗi module visibility. Mỗi lần thử chỉ thay **một nguyên nhân**, giúp phân biệt chính xác tên không tìm thấy, truy cập bị chặn và tham chiếu kiểu không hợp lệ.