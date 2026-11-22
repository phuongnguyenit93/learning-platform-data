# Phân giải tên, phạm vi và liên kết tới khai báo trong quá trình biên dịch Java

Trong mã Java, các tên như `count`, `Account`, `List`, `println` hay `com.example.app.Main` chỉ là chuỗi ký tự cho đến khi trình biên dịch **phân giải tên** (name resolution): xác định chúng chỉ đến biến, trường, kiểu, phương thức, package hoặc khai báo nào trong ngữ cảnh cụ thể. Kết quả phụ thuộc vào **phạm vi nhìn thấy** (scope), import, kế thừa, kiểu của biểu thức, quy tắc nạp chồng (overloading) và quyền truy cập.

Đây là một phần quan trọng trong xử lý ngữ nghĩa của `javac`. Compiler phải xác định tên tham chiếu đến khai báo thích hợp và kiểm tra kiểu trước khi sinh bytecode. Cần phân biệt bước này với việc JVM tìm, xác minh và liên kết các class ở **thời điểm chạy**.

## 1. Bốn thuật ngữ cần phân biệt

| Thuật ngữ | Câu hỏi mà nó trả lời | Ví dụ |
| --- | --- | --- |
| Declaration (khai báo) | Tên được giới thiệu ở đâu? | `int size = 3;` khai báo biến `size` |
| Scope (phạm vi) | Trong vùng mã nào tên có thể được dùng như một tên nhìn thấy được? | Biến cục bộ thường trong phần còn lại của block chứa nó |
| Name resolution (phân giải tên) | Ở vị trí sử dụng này, tên nói đến khai báo nào? | `size` trong `println(size)` chỉ đến một biến cụ thể |
| Binding (liên kết tên với khai báo) | Compiler đã gắn tham chiếu với ký hiệu/khai báo nào và dùng kiểu/chữ ký nào? | Lời gọi `sum(1, 2)` liên kết với overload nhận hai `int` |

**Scope không đồng nghĩa với khả năng truy cập hợp lệ ở mọi tình huống.** Một thành viên có thể tồn tại trong phạm vi tra cứu nhưng vẫn bị quy tắc `private`, `protected` hoặc module `exports` chặn truy cập. Một biến cục bộ có tên trong scope nhưng chưa được **definitely assigned** (chắc chắn gán giá trị) cũng không được đọc.

Ba lớp vấn đề thường bị trộn lẫn:

1. **Có khai báo nào phù hợp với tên này?** Nếu không, compiler thường báo `cannot find symbol` hoặc `package ... does not exist`.
2. **Khai báo tìm được có thể sử dụng ở đây không?** Kiểm tra quyền truy cập, khả năng gán, kiểu và ngữ cảnh static/instance.
3. **Nếu có nhiều ứng viên, ứng viên nào được chọn?** Ví dụ nạp chồng phương thức dựa trên kiểu đối số tại **thời điểm biên dịch**; một lời gọi mơ hồ có thể báo `reference to ... is ambiguous`.

Một chú ý về thuật ngữ: Java còn có khái niệm **linking** của JVM (verification, preparation, resolution của tham chiếu tượng trưng). Đó là bước khác với việc compiler gắn tên trong mã nguồn với khai báo. Hai quá trình liên quan nhưng không nên dùng cùng một ý nghĩa cho mọi lần xuất hiện của từ “liên kết”.

## 2. Phân giải tên nằm ở đâu trong quá trình javac?

Khái quát một luồng biên dịch thường gặp:

~~~text
Mã nguồn .java
    |
    v
Lexing / Parsing
  - Tách token và xây cây cú pháp
    |
    v
Thu thập khai báo, xây bảng ký hiệu và môi trường
  - Package, import, top-level type, thành viên
    |
    v
Phân tích ngữ nghĩa
  - Phân giải tên, xác định kiểu
  - Kiểm tra scope, accessibility, overload
  - Kiểm tra gán chắc chắn, chuyển đổi kiểu, v.v.
    |
    v
Chuyển đổi AST / sinh bytecode
    |
    v
Tệp .class (mang các tham chiếu symbolic)
    |
    v
JVM tải, liên kết và thực thi khi cần
~~~

Đây là **sơ đồ khái niệm**, không phải cam kết thứ tự chính xác của mọi internal pass trong mọi phiên bản `javac`. Trong thực tế các thao tác enter/attribute/analyze/generate, phân giải kiểu và phương thức có thể đan xen với các lượt duyệt cây cú pháp.

Ví dụ, compiler đọc:

~~~java
import java.util.List;

List<String> names = List.of("A", "B");
~~~

Để kiểm tra đoạn mã, compiler cần hiểu `List` là kiểu `java.util.List`, `String` là `java.lang.String`, `List.of` là một phương thức static phù hợp với đối số, và phép gán có kiểu tương thích với `List<String>`. Khi không tìm được khai báo kiểu hoặc thư viện phụ thuộc, compiler không thể tiếp tục xác minh ngữ nghĩa hợp lệ.

Compiler có thể tham chiếu kiểu từ tệp nguồn được chỉ định, từ source path, classpath hoặc module path theo cấu hình. **Import chỉ hỗ trợ đặt tên trong mã nguồn; import không tải dependency.**

## 3. Các loại tên và cách đọc theo ngữ cảnh

| Loại tên | Ví dụ | Nghĩa trong ngữ cảnh |
| --- | --- | --- |
| Tên biến cục bộ / parameter | `total`, `customer` | Một khai báo biến nằm trong scope của khối/phương thức |
| Tên trường (field) | `this.total`, `Counter.count` | Thành viên của một kiểu được truy cập qua receiver thích hợp |
| Tên kiểu (type name) | `String`, `Map.Entry` | Class, interface, enum, record hoặc type variable |
| Tên package | `java.util` | Không gian tên chứa kiểu/package khác |
| Tên phương thức | `println`, `sum` | Một lời gọi phải được xét theo receiver và kiểu đối số |
| Tên đầy đủ | `java.util.ArrayList` | Chỉ định kiểu cùng đường dẫn package hoặc kiểu lồng |
| Tên có định danh receiver | `account.owner()` | Tìm phương thức `owner` trên kiểu compile-time của `account` và các thành viên thừa kế phù hợp |

Cú pháp `x.y` không luôn có nghĩa “biến x có field y”. Tùy ngữ cảnh, `x` có thể là tên package, tên kiểu, tên biến, hoặc một phần của tên đầy đủ. Java có các quy tắc phân loại và tái phân loại tên (name classification/reclassification) trong đặc tả ngôn ngữ.

Chẳng hạn:

~~~java
java.util.List<String> words = java.util.List.of("alpha");
System.out.println(words.size());
~~~

Trong dòng đầu, `java.util.List` là **tên kiểu** đầy đủ; trong dòng sau, `System` là **tên kiểu**, `out` là trường static, và `println(...)` là lời gọi phương thức trên đối tượng `PrintStream`. Cú pháp giống nhau về dấu chấm nhưng các kết quả phân giải khác nhau.

## 4. Ví dụ chạy được: một tên có thể có nhiều khai báo ứng viên

Dùng Java 17 trở lên. Tạo dự án:

~~~text
resolution-lab/
└── src/
    └── com/
        └── example/
            ├── domain/
            │   └── Account.java
            └── app/
                └── ResolutionDemo.java
~~~

**Tệp `src/com/example/domain/Account.java`:**

~~~java
package com.example.domain;

public final class Account {
    private final String owner;

    public Account(String owner) {
        this.owner = owner;
    }

    public String label() {
        return "Account:" + owner;
    }
}
~~~

**Tệp `src/com/example/app/ResolutionDemo.java`:**

~~~java
package com.example.app;

import java.util.List;
import com.example.domain.Account;

public final class ResolutionDemo {
    private static String label = "field";

    private static String pick(int value) {
        return "int:" + value;
    }

    private static String pick(long value) {
        return "long:" + value;
    }

    public static void main(String[] args) {
        String label = "local";
        Account account = new Account("Mai");

        System.out.println(label);
        System.out.println(ResolutionDemo.label);
        System.out.println(account.label());
        System.out.println(List.of("one", "two").size());
        System.out.println(pick(3));
        System.out.println(pick(3L));
    }
}
~~~

Từ thư mục `resolution-lab`:

~~~bash
mkdir out
javac -encoding UTF-8 -d out src/com/example/domain/Account.java src/com/example/app/ResolutionDemo.java
java -cp out com.example.app.ResolutionDemo
~~~

Nếu `out` đã tồn tại, không cần chạy lại `mkdir out`. Cấu trúc đường dẫn trong lệnh dùng dấu `/`, phù hợp Linux/macOS và cũng được Java CLI chấp nhận trong nhiều ngữ cảnh Windows. Có thể dùng dấu `\` trong CMD/PowerShell nếu muốn.

**Stdout chính xác:**

~~~text
local
field
Account:Mai
2
int:3
long:3
~~~

Những quyết định phân giải nổi bật:

1. `String label = "local"` khai báo biến **cục bộ** trùng tên trường static `label`. Tham chiếu không định danh `label` trong `main` chỉ đến biến cục bộ vì nó che khuất trường.
2. `ResolutionDemo.label` dùng tên kiểu để chỉ **trường static**, vượt qua sự che khuất của tên cục bộ.
3. `Account` được tìm từ khai báo `import com.example.domain.Account;`, còn thành viên `label()` được phân giải qua kiểu `Account` của biến `account`.
4. `List` đến từ `import java.util.List;`, và `List.of(...)` chọn phương thức factory thích hợp từ các overload hợp lệ. `size()` được tìm trên kiểu kết quả.
5. `pick(3)` chọn overload `pick(int)`; `pick(3L)` chọn `pick(long)`. Phép chọn dựa vào kiểu đối số biểu thức, không đợi đến runtime mới quyết định số overload.

Ví dụ này cố ý không dùng dependency ngoài JDK để người học có thể tự biên dịch, đọc output và thử thay đổi tên.

## 5. Phạm vi của khai báo: local, parameter, field, type

Trong Java, mỗi loại khai báo có phạm vi riêng. Với các trường hợp thường gặp:

| Khai báo | Phạm vi nhìn thấy điển hình |
| --- | --- |
| Local variable trong block | Từ vị trí khai báo trong block đến hết block chứa nó, tuân theo quy tắc definite assignment |
| Parameter của method/constructor | Thân method/constructor và các vùng nằm trong scope tương ứng |
| Field của class | Trong phạm vi class và nơi truy cập thành viên hợp lệ theo quyền truy cập/kế thừa |
| Member type | Trong phạm vi kiểu bao quanh và nơi có thể tham chiếu hợp lệ |
| Top-level type | Có tên trong package; bên ngoài package có thể tham chiếu qua import hoặc tên đầy đủ khi truy cập được |
| Local class | Vùng sau khai báo của nó trong block phù hợp |
| Type parameter | Trong phạm vi type/method/constructor mà tham số kiểu đó khai báo |
| Pattern variable | Trong vùng chương trình mà pattern match được xác định chắc chắn là thành công |

### Block scope và trường

**Tệp độc lập `ScopeDemo.java`:**

~~~java
public final class ScopeDemo {
    private String name = "field";

    private void show(String name) {
        System.out.println(name);
        System.out.println(this.name);
        {
            int count = 2;
            System.out.println(count);
        }
        // Ở đây không còn được sử dụng count.
    }

    public static void main(String[] args) {
        new ScopeDemo().show("parameter");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ScopeDemo.java
java ScopeDemo
~~~

Output:

~~~text
parameter
field
2
~~~

Ở `show`, parameter `name` che field `name`; `this.name` chỉ rõ trường của instance. `count` chỉ nằm trong block bên trong. Nếu bỏ comment và viết `System.out.println(count);` sau block, compiler sẽ báo lỗi vì tên không còn trong scope.

**Shadowing không có nghĩa là hai biến được hòa làm một.** Field vẫn tồn tại, vẫn có giá trị, và có thể truy cập qua `this` nếu ngữ cảnh cho phép.

### Không thể tái khai báo local trong block lồng còn chồng scope

Đoạn **cố ý sai, không biên dịch được**:

~~~java
void wrong() {
    int value = 1;
    {
        int value = 2; // Lỗi: value đã được khai báo trong scope bao ngoài.
    }
}
~~~

Java không cho phép khai báo một local variable trùng tên với local variable đang trong phạm vi chồng lấn như ở trên. Nhưng **local variable được phép che field** như `label` của `ResolutionDemo`. Đây là hai tình huống khác nhau.

### Scope khác definite assignment

Đoạn sau cũng **cố ý sai**:

~~~java
void wrong(boolean condition) {
    int score;
    if (condition) {
        score = 10;
    }
    System.out.println(score); // Lỗi: score có thể chưa được gán.
}
~~~

`score` nằm trong scope của `println`, nhưng compiler không chứng minh được nó đã được gán trên **mọi** đường đi đến lệnh đọc. Đó là lỗi definite assignment, không phải lỗi không tìm thấy khai báo.

## 6. Quy tắc ưu tiên khi nhiều khai báo cùng tên

Để đọc code, có thể dùng các câu hỏi theo thứ tự thực hành sau:

1. **Tên nằm trong dạng cú pháp nào?** Tên của kiểu, biến, thành viên hay lời gọi phương thức? Có receiver `this`, tên kiểu hoặc một biểu thức ở bên trái dấu chấm không?
2. **Có khai báo local/parameter/type parameter phù hợp trong scope gần nhất không?** Nếu có, xét các quy tắc shadowing và tính hợp lệ.
3. **Đó là thành viên của lớp hiện tại hay lớp cha?** Xem sự che khuất trường, kế thừa, quyền truy cập và ngữ cảnh static/instance.
4. **Có import hay tên kiểu ở cùng package không?** Xem single-type import, import-on-demand, `java.lang`, cùng package và tên đầy đủ.
5. **Nếu là phương thức, có bao nhiêu overload khả dụng?** Xét kiểu compile-time của receiver, kiểu đối số, conversion, varargs và mức độ cụ thể.
6. **Có ràng buộc access, module hoặc type-checking nào chặn lời tham chiếu không?**

Đây là **checklist chẩn đoán**, không phải một thứ tự ưu tiên pháp lý duy nhất cho mọi loại tên. Đặc tả Java có quy tắc khác nhau cho tên kiểu, biến, phương thức, thành viên và import. Ví dụ một local variable có thể che tên trường, nhưng không thể dựa vào cùng quy tắc ấy để giải quyết mọi xung đột giữa các import kiểu.

### Shadowing, hiding và overriding không giống nhau

| Cơ chế | Điều gì xảy ra? | Thời điểm/quy tắc |
| --- | --- | --- |
| Shadowing (che khuất) | Một tên khai báo gần hơn làm tên ở phạm vi ngoài không được tham chiếu bằng simple name | Phân giải theo scope lúc compile |
| Field hiding | Field trong subclass có thể che field cùng tên ở superclass | Truy cập field dựa trên kiểu compile-time của biểu thức |
| Method hiding | Static method của subclass có thể che static method tương ứng của superclass | Không dùng dispatch ảo của instance method |
| Method overriding | Instance method trong subclass triển khai lại phương thức có thể override | Chữ ký/lời gọi được xác định khi compile; implementation được chọn theo runtime receiver khi dispatch ảo |

Tránh gọi mọi trường hợp có cùng tên là overriding. Hai overload khác tham số cũng không phải overriding.

## 7. Import và phân giải tên kiểu

Hãy xem ba kiểu với cùng simple name:

~~~java
java.util.Date utilDate = new java.util.Date();
java.sql.Date sqlDate = new java.sql.Date(0L);
~~~

Cả hai đều có tên ngắn `Date` nhưng là hai class khác nhau. Nếu dùng hai import-on-demand:

~~~java
import java.util.*;
import java.sql.*;

// Trong thân method:
Date today = new Date(); // Cố ý sai: Date mơ hồ.
~~~

Compiler không thể chọn tùy tiện kiểu nào; `Date` từ hai package được import-on-demand là ứng viên mơ hồ.

Một cách đúng là import kiểu muốn dùng nhiều hơn và dùng FQN cho kiểu còn lại:

~~~java
import java.util.Date;

// Trong thân method:
Date utilDate = new Date();
java.sql.Date sqlDate = new java.sql.Date(0L);
~~~

Hoặc dùng tên đầy đủ cho cả hai để rõ ràng. Không có cú pháp alias cho import kiểu như `import java.util.Date as UtilDate;` trong Java.

Một số quy tắc đáng nhớ:

- `import java.util.List;` (single-type import) cho phép dùng simple name `List` ở những vị trí phù hợp.
- `import java.util.*;` là import-on-demand **các kiểu trong đúng package này**, không tự mở rộng sang `java.util.concurrent.*`.
- `java.lang` được import-on-demand ngầm; `String` và `System` không cần import tường minh.
- Mã thuộc package hiện tại có thể dùng các top-level type truy cập được của cùng package mà không cần import.
- `import static java.lang.Math.PI;` cung cấp simple name của thành viên static; nó không import cả lớp như import kiểu thông thường.
- Import không tìm/tải JAR từ Internet. Nếu `javac` không nhìn thấy class tương ứng trên classpath/module path hoặc source path, tên vẫn không resolve được.
- Tên package có tiền tố chung không có quan hệ phạm vi đặc biệt: `com.example` và `com.example.impl` là hai package khác nhau.

### Tên kiểu lồng nhau

Xét kiểu:

~~~java
package com.example.model;

public final class Container {
    public static final class Item {
    }
}
~~~

Trong Java source, tên chuẩn của kiểu lồng là `com.example.model.Container.Item`. Tên nhị phân của nó là `com.example.model.Container$Item` và file class tương ứng thường là `Container$Item.class`. Đây là khác biệt giữa **cách gọi tên kiểu trong mã nguồn** và **tên nhị phân trong JVM**, không phải hai class khác nhau.

## 8. Tên thành viên và receiver: field, static, instance

Xem đoạn chương trình độc lập:

**Tệp `MemberDemo.java`:**

~~~java
class Parent {
    String code = "parent";

    String describe() {
        return "Parent method";
    }
}

class Child extends Parent {
    String code = "child";

    @Override
    String describe() {
        return "Child method";
    }
}

public final class MemberDemo {
    public static void main(String[] args) {
        Parent item = new Child();
        System.out.println(item.code);
        System.out.println(item.describe());
        System.out.println(((Child) item).code);
    }
}
~~~

Chạy:

~~~bash
javac MemberDemo.java
java MemberDemo
~~~

Output:

~~~text
parent
Child method
child
~~~

Giải thích:

- `item.code` chọn **field** theo kiểu compile-time của biến `item`, là `Parent`. Field không được virtual dispatch.
- `item.describe()` được compiler kiểm tra trên kiểu `Parent`; vì `Child` override instance method này, dispatch ảo ở runtime gọi implementation trong `Child`.
- `((Child) item).code` dùng kiểu compile-time của biểu thức đã ép kiểu là `Child` nên chọn field `Child.code`. Trong ví dụ ép kiểu hợp lệ vì object thật sự là một `Child`.

Static method cũng không có override kiểu instance. Chọn tên phương thức static dựa theo quy tắc compile-time (hiding) và nên gọi rõ qua tên kiểu để tránh tạo cảm giác có dynamic dispatch.

## 9. Nạp chồng phương thức: chọn khai báo ở compile-time

Overload là nhiều phương thức có cùng tên nhưng **khác danh sách tham số**. Trình biên dịch phải tìm các ứng viên phù hợp và chọn phương thức thích hợp nhất theo quy tắc Java về overload resolution. Các yếu tố gồm:

- Số lượng và kiểu compile-time của các đối số.
- Khả năng chuyển đổi kiểu: widening primitive/reference, boxing/unboxing, và varargs theo các pha kiểm tra khả dụng.
- Generic type inference khi gọi phương thức generic.
- Quy tắc chọn “most specific” giữa các ứng viên còn lại.
- Tính nhìn thấy và quyền truy cập của các khai báo.

Ví dụ **`OverloadDemo.java`**:

~~~java
public final class OverloadDemo {
    static String choose(int value) {
        return "int";
    }

    static String choose(long value) {
        return "long";
    }

    static String choose(Integer value) {
        return "Integer";
    }

    public static void main(String[] args) {
        System.out.println(choose(5));
        System.out.println(choose(5L));
        Integer boxed = 5;
        System.out.println(choose(boxed));
    }
}
~~~

Chạy:

~~~bash
javac OverloadDemo.java
java OverloadDemo
~~~

Output:

~~~text
int
long
Integer
~~~

`5` có kiểu `int` nên chọn `choose(int)`; `5L` có kiểu `long`; biến `boxed` có kiểu tham chiếu `Integer` nên chọn exact match `choose(Integer)`. Đổi kiểu **khai báo** của biến có thể làm thay đổi overload được chọn dù giá trị số về mặt toán học như nhau.

### Overload không được chọn theo kiểu runtime của biến

**Tệp `OverloadVsOverride.java`:**

~~~java
class Base {
    String action() {
        return "Base action";
    }
}

class Derived extends Base {
    @Override
    String action() {
        return "Derived action";
    }
}

public final class OverloadVsOverride {
    static void execute(Base value) {
        System.out.println("Base overload -> " + value.action());
    }

    static void execute(Derived value) {
        System.out.println("Derived overload -> " + value.action());
    }

    public static void main(String[] args) {
        Base reference = new Derived();
        execute(reference);
        execute((Derived) reference);
    }
}
~~~

Chạy:

~~~bash
javac OverloadVsOverride.java
java OverloadVsOverride
~~~

Output:

~~~text
Base overload -> Derived action
Derived overload -> Derived action
~~~

Lý do:

1. Lời gọi `execute(reference)` được chọn **`execute(Base)`** khi biên dịch vì biến có kiểu khai báo `Base`. Java không chọn overload `Derived` bằng cách chờ xem object runtime.
2. Bên trong `execute(Base)`, lời gọi instance method `value.action()` dispatch tới `Derived.action()` vì object thực sự là `Derived`.
3. Lời gọi `execute((Derived) reference)` có biểu thức đối số với kiểu compile-time `Derived` nên chọn overload `execute(Derived)`.

### Ambiguity khi đối số null

Hai phương thức sau đều hợp lệ nếu được khai báo riêng:

~~~java
static void show(String value) { }
static void show(Integer value) { }
~~~

Nhưng lời gọi `show(null);` là **cố ý sai**: cả `String` và `Integer` đều là kiểu tham chiếu phù hợp; không kiểu nào cụ thể hơn kiểu còn lại theo quan hệ subtype, nên compiler báo lời gọi ambiguous. Có thể viết `show((String) null);` hoặc `show((Integer) null);` để chỉ rõ overload.

Không thể nạp chồng chỉ bằng kiểu trả về:

~~~java
int total() { return 1; }
long total() { return 2L; } // Cố ý sai: cùng danh sách tham số.
~~~

Overload resolution không dùng kiểu trả về để hợp thức hóa hai khai báo có cùng chữ ký phương thức như trên.

## 10. Khai báo trong lambda, nested type và pattern variable

### Lambda và biến được capture

**Tệp `CaptureDemo.java`:**

~~~java
import java.util.function.Supplier;

public final class CaptureDemo {
    public static void main(String[] args) {
        String prefix = "Hello";
        Supplier<String> greeting = () -> prefix + " Java";
        System.out.println(greeting.get());
    }
}
~~~

Chạy:

~~~bash
javac CaptureDemo.java
java CaptureDemo
~~~

Output:

~~~text
Hello Java
~~~

Lambda tham chiếu đến `prefix` ở scope bao ngoài. Để capture local variable, Java yêu cầu biến là `final` hoặc **effectively final** (không bị gán lại sau lần khởi tạo theo quy tắc của ngôn ngữ). Thêm `prefix = "Hi";` sau lệnh khai báo sẽ gây lỗi compile vì biến không còn effectively final khi bị capture.

Lambda không tạo một `this` mới: `this` trong lambda (ở ngữ cảnh instance) là `this` của kiểu bao quanh. Còn anonymous class có instance `this` riêng. Đây là chi tiết quan trọng khi cùng một tên thành viên xuất hiện trong các phạm vi lồng nhau.

### Pattern variable với instanceof (Java 17)

**Tệp `PatternDemo.java`:**

~~~java
public final class PatternDemo {
    static void printIfString(Object input) {
        if (input instanceof String text) {
            System.out.println(text.length());
        }
    }

    public static void main(String[] args) {
        printIfString("Java");
        printIfString(123);
    }
}
~~~

Chạy:

~~~bash
javac PatternDemo.java
java PatternDemo
~~~

Output:

~~~text
4
~~~

`text` chỉ được sử dụng ở vùng mà kết quả pattern match được xác định là đúng. Nếu tham chiếu `text` sau toàn bộ `if` trong ví dụ này, compiler báo tên không thuộc scope ở đó. Phạm vi pattern variable dựa trên phân tích luồng điều khiển, phức tạp hơn block scope thông thường.

### Type parameter và tên kiểu

Trong `class Box<T> { T value; }`, `T` là type parameter có phạm vi của khai báo generic. Nó được compiler phân giải như một **tên kiểu**, không phải biến runtime. Khi biên dịch Java generic, thông tin kiểu thường được xử lý qua **type erasure**, có ảnh hưởng đến chữ ký bytecode và khả năng khai báo overload.

Ví dụ sau **không biên dịch** vì đụng độ sau erasure:

~~~java
void process(java.util.List<String> values) { }
void process(java.util.List<Integer> values) { } // Cố ý sai: name clash.
~~~

Cả hai danh sách tham số có cùng kiểu bị xóa là `List`; không thể tạo hai overload JVM hợp lệ chỉ khác generic type argument theo cách này.

## 11. Truy cập hợp lệ và dependency cũng tham gia quá trình phân giải

Một symbol có thể được tìm thấy nhưng vẫn không thể truy cập:

~~~java
package com.example.domain;

class InternalAccount {
}
~~~

Trong mã thuộc package `com.example.app`, không thể dùng `com.example.domain.InternalAccount` vì top-level class trên có quyền truy cập **package-private**. Việc viết tên đầy đủ không bỏ qua quy tắc truy cập. Tương tự, một thành viên `private` không được dùng từ code không có quyền truy cập tương ứng.

Các trường hợp cần kiểm tra riêng:

- **Package**: `com.example.domain` và `com.example.domain.internal` là hai package độc lập; không chia sẻ quyền package-private do có tiền tố tên chung.
- **Kế thừa**: `protected` có quy tắc phụ thuộc package, quan hệ subclass và hình thức truy cập; không đồng nghĩa với “public cho mọi subclass qua mọi receiver”.
- **Ngữ cảnh static**: không được sử dụng trực tiếp một instance field từ static method nếu không có instance receiver hợp lệ. Ví dụ trong `static void main`, `this.field` là bất hợp lệ.
- **JPMS**: khi biên dịch theo module path, mã ở module khác có thể cần `requires` và package được `exports`. Class tồn tại trong module path chưa đủ để mọi public type đều nhìn thấy được.
- **Dependency**: compiler cần tìm được thông tin kiểu từ mã nguồn hoặc các class/JAR/module tương ứng. Một `import` viết đúng nhưng classpath sai vẫn có thể báo lỗi.

Cần phân biệt **symbol tồn tại**, **symbol được lookup**, **symbol nhìn thấy/truy cập được** và **lời gọi thỏa type checking**. Đây là các điều kiện khác nhau.

## 12. Tên được gắn với khai báo khi compile, JVM vẫn phải liên kết class khi chạy

Khi `javac` đã phân giải `com.example.domain.Account` và chọn một phương thức phù hợp, bytecode có thể chứa tham chiếu dạng symbolic đến tên lớp, tên thành viên và descriptor. Nó không ghi sẵn địa chỉ bộ nhớ của mọi phương thức vào file `.class`.

Ví dụ minh họa (đọc như sơ đồ, không phải disassembly nguyên văn):

~~~text
Java source:
    Account account = new Account("Mai");
    account.label();

Compiler:
    Resolve type     -> com.example.domain.Account
    Resolve method   -> Account.label(): String
    Check access and types
    Emit .class with symbolic references

JVM:
    Load relevant classes as needed
    Verify/prepare/link and resolve symbolic references
    Execute instructions and dispatch suitable instance methods
~~~

**Kết quả của name resolution ở source** được phản ánh vào bytecode, nhưng **JVM resolution** là khâu liên kết tham chiếu tượng trưng với class/field/method thực tế và có thể diễn ra khi cần ở runtime. Java cho phép một số hoạt động linking/resolution diễn ra sớm hay muộn trong giới hạn đặc tả.

Một vài hậu quả thực tế:

| Triệu chứng | Giai đoạn thường phát hiện | Ý nghĩa |
| --- | --- | --- |
| `cannot find symbol` | Compile | Tên không phân giải được thành symbol thích hợp |
| `reference to ... is ambiguous` | Compile | Nhiều ứng viên, không chọn được duy nhất |
| `... has private access` | Compile | Symbol có thể tồn tại nhưng truy cập bị cấm |
| `NoClassDefFoundError` | Runtime | Class đã cần khi linking/executing nhưng JVM không lấy được định nghĩa phù hợp (hoặc khởi tạo lỗi trước đó) |
| `NoSuchMethodError` | Runtime | Bytecode tham chiếu method không còn có định nghĩa phù hợp trong các class runtime, thường do mismatch giữa bản compile/runtime |
| `IncompatibleClassChangeError` | Runtime | Thay đổi class/interface/member không tương thích với bytecode đã compile |
| `ClassNotFoundException` | Runtime theo API | Thường xuất hiện từ các thao tác nạp class theo tên như `Class.forName(...)` khi không tìm được class |

Không nên sửa `NoSuchMethodError` chỉ bằng cách thêm import vào source: import tác động đến tên khi **biên dịch**, còn lỗi này thường liên quan phiên bản thư viện và classpath lúc **chạy**.

## 13. Thực hành với javac: làm tên không còn phân giải được

Từ dự án `resolution-lab` ở mục 4, thực hiện lần lượt các biến đổi nhỏ, compile lại sau mỗi lần, rồi hoàn nguyên để tiếp tục. Các trường hợp dưới đây là **cố ý làm lỗi**, không phải mã phải chạy.

### Thí nghiệm A: xóa import của Account

Trong `ResolutionDemo.java`, xóa:

~~~java
import com.example.domain.Account;
~~~

Trong package `com.example.app`, simple name `Account` không còn được biết đến qua import. Compiler thường báo `cannot find symbol` tại chỗ dùng `Account`. Sửa bằng cách khôi phục import hoặc viết tên đầy đủ `com.example.domain.Account` cho kiểu và constructor.

### Thí nghiệm B: đổi tên field, không đổi tham chiếu

Đổi khai báo `private static String label = "field";` thành `private static String title = "field";` nhưng giữ `ResolutionDemo.label`. Compiler báo không tìm được field `label` của kiểu `ResolutionDemo`, dù local variable tên `label` vẫn tồn tại. Việc tra cứu `ResolutionDemo.label` không quay về local variable, bởi receiver đã chỉ rõ đây là truy cập thành viên của kiểu.

### Thí nghiệm C: sửa kiểu tham số

Đổi `pick(3L)` thành `pick("3")` trong khi chỉ còn các overload `pick(int)` và `pick(long)`. Compiler báo không có method phù hợp cho đối số `String`. Một khai báo trùng **tên phương thức** chưa đủ; danh sách tham số phải phù hợp.

### Thí nghiệm D: bỏ class phụ thuộc khỏi compile inputs

Giữ hai tệp nguồn như cũ nhưng chạy lệnh chỉ rõ `Main`:

~~~bash
javac -encoding UTF-8 -d out src/com/example/app/ResolutionDemo.java
~~~

Lệnh có thể **thất bại** nếu compiler không tìm được `Account` từ source path/classpath đang dùng; cũng **có thể thành công** nếu `Account.class` đã có sẵn trên đường tìm kiếm thích hợp. Vì vậy muốn thử nghiệm sạch, dùng thư mục output mới và cấu hình đường tìm kiếm minh bạch. Để biên dịch chắc chắn từ ví dụ, liệt kê cả hai tệp như mục 4:

~~~bash
javac -encoding UTF-8 -d out src/com/example/domain/Account.java src/com/example/app/ResolutionDemo.java
~~~

Thí nghiệm này cho thấy source path, compile classpath và tệp nguồn đầu vào quyết định **những khai báo compiler có thể nhìn thấy**. Đường dẫn tệp Java và tên symbol là hai lớp thông tin liên quan nhưng không đồng nhất.

## 14. Checklist khi đọc lỗi phân giải tên

Khi `javac` không tìm được hoặc chọn sai khai báo, hãy đi theo thứ tự:

1. **Xác định tên tại vị trí lỗi.** Đó là tên biến, tên kiểu, tên phương thức hay thành viên sau dấu chấm? Có receiver không?
2. **Tìm khai báo thực sự.** Đúng chính tả, đúng chữ hoa/chữ thường, đúng package và đúng danh sách tham số chưa?
3. **Kiểm tra scope.** Có nằm ngoài block, ngoài vùng pattern variable, hoặc bị một khai báo khác che khuất không?
4. **Kiểm tra import.** Kiểu thuộc package nào? Có hai ứng viên cùng simple name? Viết FQN để thử loại bỏ nhập nhằng.
5. **Kiểm tra type.** Receiver có kiểu compile-time gì? Lời gọi thuộc static hay instance? Những overload nào áp dụng với kiểu đối số?
6. **Kiểm tra quyền truy cập.** Có ràng buộc `private`, package-private, `protected`, module `exports`/`requires` không?
7. **Kiểm tra dependency và compiler flags.** Tệp nguồn có trong lệnh `javac` không? Compile classpath/source path/module path có đúng không?
8. **Nếu compile xong nhưng chạy lỗi**, kiểm tra runtime classpath/module path và phiên bản thư viện; phân biệt linking/runtime dispatch với source name resolution.

### Các hiểu lầm cần tránh

- “Tên biến có scope thì có thể đọc ngay”: sai nếu chưa được gán chắc chắn.
- “Cùng simple name nghĩa là cùng kiểu”: sai nếu thuộc package/kiểu bao khác nhau.
- “Import giải quyết mọi lỗi thiếu class”: sai nếu dependency không có trong compile path.
- “Subclass override field”: sai; field có quy tắc hiding, không phải dispatch ảo.
- “Compiler chọn overload dựa vào object runtime”: sai; overload resolution dựa vào kiểu biểu thức ở compile-time.
- “Đã compile thành công thì JVM không bao giờ lỗi liên kết”: sai nếu runtime thiếu class hoặc thư viện không tương thích.
- “Tên đầy đủ luôn bỏ qua quyền truy cập”: sai; access checking vẫn được áp dụng.
- “Mọi tên sau dấu chấm đều là field”: sai; có thể là một phần package/type name hoặc lời gọi phương thức.

## 15. Câu hỏi tự kiểm tra

**1.** Một class có field `int size`; method có parameter `int size`. Trong method, `size` nói đến đâu, `this.size` nói đến đâu?

**Đáp án:** `size` là parameter gần hơn trong scope; `this.size` là instance field của object.

**2.** Có `execute(Base)` và `execute(Derived)`; biến `Base value = new Derived();`. `execute(value)` chọn overload nào?

**Đáp án:** `execute(Base)` tại compile-time. Nếu bên trong có lời gọi instance method override, implementation có thể được chọn theo runtime class khi chạy.

**3.** Hai import-on-demand từ package khác nhau đều có kiểu `Date`. Vì sao `Date d;` lỗi, nhưng `java.util.Date d;` có thể hợp lệ?

**Đáp án:** Simple name không duy nhất trong ngữ cảnh; FQN chỉ rõ kiểu muốn tham chiếu, với điều kiện kiểu khả dụng/truy cập được.

**4.** Biến `int n;` đang trong scope nhưng chỉ được gán bên trong nhánh `if (condition)`. Vì sao đọc `n` sau `if` có thể lỗi?

**Đáp án:** Compiler không chứng minh được rằng giá trị luôn được gán trước khi dùng; đây là definite assignment, không phải thiếu khai báo.

**5.** Vì sao `NoSuchMethodError` có thể xuất hiện sau khi source đã compile thành công?

**Đáp án:** Tên và chữ ký được gắn tại compile-time nhưng class runtime có thể khác phiên bản, khiến JVM không phân giải được tham chiếu method tương ứng.

## Ghi nhớ

- **Khai báo** tạo symbol; **scope** xác định vùng dùng tên; **name resolution** xác định tham chiếu nào trỏ đến khai báo nào; **type/access checking** xác nhận việc dùng đó hợp lệ.
- **Shadowing** ảnh hưởng đến simple name; receiver hay tên đầy đủ có thể làm rõ tên cần dùng khi vẫn có quyền truy cập.
- **Overloading** được chọn dựa trên kiểu ở compile-time; **overriding** của instance method có thể dispatch tới implementation ở runtime.
- Import chỉ hỗ trợ tên trong source; source path/classpath/module path quyết định compiler có thấy các kiểu phụ thuộc hay không.
- Bytecode dùng symbolic references; JVM có quá trình linking/resolution riêng, vì thế lỗi compile và lỗi liên kết runtime cần được chẩn đoán khác nhau.
