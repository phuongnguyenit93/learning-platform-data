# Phân biệt phạm vi tên và quyền truy cập trong Java

## Mục tiêu

Sau bài học, bạn có thể:

- Trả lời độc lập hai câu hỏi: **“Tên này dùng được ở vị trí nào?”** (*scope/name resolution*) và **“Code này có quyền truy cập khai báo đó không?”** (*accessibility*).
- Nhận diện phạm vi của biến cục bộ, tham số, biến vòng lặp, field, method, nested class và tên kiểu.
- Dự đoán tác dụng của `this.field`, `Outer.this.field`, `super.field` và shadowing khi có nhiều khai báo trùng tên.
- Áp dụng đúng `private`, package-private (không có modifier), `protected`, `public` cho class, member và constructor.
- Biết vì sao `import` không cấp thêm quyền, `public` không tự vượt giới hạn của class/module chứa member, và subclass khác package gặp quy tắc đặc biệt với `protected`.
- Phân biệt lỗi về scope, accessibility, static context, definite assignment, type checking và lỗi xảy ra khi chạy.
- Hiểu nested classes có thể truy cập private members trong cùng nest và vì sao hai top-level classes đặt chung file không tự có quyền private access của nhau.
- Viết ví dụ Java 17+, kiểm tra stdout chính xác và chọn cách thiết kế API đóng gói trạng thái phù hợp.

## 1. Scope và accessibility không phải một khái niệm

Trong mã nguồn Java, có hai vấn đề thường xuất hiện cùng nhau nhưng không được nhập làm một:

**Scope (phạm vi của khai báo tên):** Một khai báo về biến, tham số, field, method, type parameter, class hay interface có những vùng mã nguồn mà tên của nó có thể được dùng/phân giải theo quy tắc Java. Scope phụ thuộc cấu trúc class, method, block, vòng lặp, khai báo, import và che khuất tên.

**Accessibility (khả năng truy cập):** Mã tại một vị trí có được phép sử dụng một kiểu, field, method hay constructor không, xét các quy tắc Java về lớp chứa, modifier, package, subclass, nest và module.

Bảng đối chiếu:

| Câu hỏi | Scope / name resolution | Accessibility |
| --- | --- | --- |
| Mục tiêu | Tìm **khai báo nào** tương ứng với tên đang dùng | Kiểm tra **có quyền dùng** khai báo đó không |
| Ví dụ | Biến `x` nằm ngoài block nên không thể dùng | Field `secret` có tồn tại nhưng `private` cấm caller truy cập |
| Cơ sở chính | Lexical nesting, vị trí khai báo, import, shadowing | Modifier `private`/package-private/`protected`/`public` và ngữ cảnh caller |
| Biến local | Có scope theo block/method | Không khai báo `public`/`private` như class members |
| Field/method | Có tên, quy tắc phân giải tên và receiver | Có thể bị chặn bởi access checks |
| Sửa lỗi | Di chuyển khai báo, truyền parameter, dùng tên đúng/qualification | Thiết kế API, dùng quyền truy cập đúng, sửa caller/package |

Ví dụ, hai lỗi sau **không cùng nguyên nhân**:

~~~java
static void demo() {
    if (true) {
        int local = 5;
    }
    // System.out.println(local); // Sai: local đã ngoài scope.
}
~~~

và:

~~~java
class User {
    private int pin = 1234;
}

class Other {
    void read(User user) {
        // System.out.println(user.pin); // Sai: private access.
    }
}
~~~

Các đoạn này là **minh họa**; dòng cố ý sai được comment để phần còn lại có thể biên dịch. Trong ví dụ đầu, `local` không còn nằm trong phạm vi tên. Trong ví dụ thứ hai, field `User.pin` **có tồn tại** nhưng `Other` không có quyền truy cập trực tiếp.

**Điểm cốt lõi:** một tên **được nhận diện** chưa chắc **được quyền dùng**; ngược lại, một member là `public` cũng không khiến một biến local cùng tên bỗng có scope rộng hơn.

## 2. Phạm vi của local variables và parameters

### 2.1. Tham số có phạm vi trong method

~~~java
static int total(int price, int quantity) {
    int subtotal = price * quantity;
    return subtotal;
}
~~~

Trong method:

- `price` và `quantity` là **parameters**. Code trong thân method sử dụng được tên của chúng.
- `subtotal` là **local variable** khai báo trong block thân method.
- Code bên ngoài method **không tự tham chiếu** được các tên `price`, `quantity` hoặc `subtotal`.
- Đó không phải vì chúng là `private`: parameter/local variable không có access modifiers như field.

Nếu method khác cũng khai báo parameter `price`, đây là **một biến riêng của method khác**, không phải cùng một biến.

### 2.2. Block scope

~~~java
static void run() {
    int outer = 5;

    {
        int inner = 7;
        System.out.println(outer + inner);
    }

    System.out.println(outer);
    // System.out.println(inner); // Không hợp lệ ở đây.
}
~~~

Tên `outer` vẫn dùng được bên trong nested block, nhưng tên `inner` không còn dùng được khi block chứa nó kết thúc. **Scope khác lifetime của object**: một object tạo trong block có thể vẫn sống sau block nếu còn tham chiếu reachable từ nơi khác.

### 2.3. Phạm vi biến `for`

~~~java
for (int i = 0; i < 2; i++) {
    System.out.println(i);
}
// System.out.println(i); // Ngoài scope của i.
~~~

`i` được khai báo trong phần initialization của `for`. Sau cấu trúc vòng lặp, khai báo này không dùng được theo tên nữa.

Trong enhanced `for`:

~~~java
for (String element : new String[] {"A", "B"}) {
    System.out.println(element);
}
// System.out.println(element); // Ngoài phạm vi.
~~~

Tương tự, biến `element` nằm trong vùng phù hợp của vòng lặp, không tự trở thành field của class.

### 2.4. Không thể khai báo local trùng tên trong scope chồng lấn

~~~java
static void example() {
    int count = 1;
    {
        // int count = 2; // Sai: khai báo local trùng tên đang nằm trong scope.
        int other = 2;
        System.out.println(count + other);
    }
}
~~~

Đây là lỗi về **khai báo tên**, không có gì liên quan `public` hay `private`. Nhưng một **parameter** trùng tên field của class là trường hợp khác: parameter có thể **shadow** field.

### 2.5. Scope khác definite assignment

~~~java
static int sample(boolean flag) {
    int result;
    if (flag) {
        result = 10;
    }

    // return result; // Sai: có đường thực thi mà result chưa được gán.
    return 0;
}
~~~

`result` thuộc phạm vi thân method tại vị trí `return`, nhưng compiler vẫn ngăn đọc biến local chưa **definitely assigned**. Điều này là quy tắc **khởi tạo trước khi đọc**, không phải access control. Không thể sửa bằng cách viết `public int result` trong method.

## 3. Field, parameter và local cùng tên: shadowing

Một instance field thuộc **đối tượng**; parameter/local variable thuộc phạm vi của lời gọi hoặc block. Chúng có thể mang cùng tên mà không trở thành cùng một biến.

Ví dụ:

~~~java
class Counter {
    private int value = 5;

    void set(int value) {
        this.value = value;
    }

    int current() {
        return value;
    }
}
~~~

Trong `set(int value)`:

- `value` không tiền tố chỉ parameter khi nó shadow field.
- `this.value` chỉ field của object `Counter` hiện tại.
- `this.value = value;` gán **giá trị parameter** vào **instance field**.
- Vì `set` nằm trong class khai báo field, code có quyền truy cập private member. `this` làm rõ **đích tham chiếu**, không phải “đặc quyền vượt qua private”.

Nếu viết `value = value;`, bạn chỉ gán parameter cho chính nó, thường là bug logic.

### 3.1. Chương trình Java 17 hoàn chỉnh về scope và shadowing

Lưu **`ScopeAndShadowingDemo.java`**:

~~~java
public class ScopeAndShadowingDemo {
    private String label = "FIELD";

    void show(String label) {
        System.out.println("parameter=" + label);
        System.out.println("field=" + this.label);

        {
            String blockValue = "BLOCK";
            System.out.println("block=" + blockValue);
        }

        for (int i = 0; i < 2; i++) {
            System.out.println("loop=" + i);
        }

        // blockValue và i không dùng được tại đây.
        System.out.println("field again=" + this.label);
    }

    public static void main(String[] args) {
        new ScopeAndShadowingDemo().show("PARAM");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ScopeAndShadowingDemo.java
java ScopeAndShadowingDemo
~~~

Output:

~~~text
parameter=PARAM
field=FIELD
block=BLOCK
loop=0
loop=1
field again=FIELD
~~~

**Phân tích:** parameter `label` shadow field. `this.label` dùng để đọc private field; block variable `blockValue` và loop variable `i` đều kết thúc phạm vi trước câu in cuối. Không có vấn đề access trong chương trình này dù field là `private`.

### 3.2. Field hiding và `super`

Nếu subclass khai báo field cùng tên với superclass:

~~~java
class Parent {
    protected int value = 1;
}

class Child extends Parent {
    int value = 2;

    void show() {
        System.out.println(value);
        System.out.println(this.value);
        System.out.println(super.value);
    }
}
~~~

Đây là đoạn lớp minh họa chưa có `main`. Trong `Child.show()`:

- `value` hoặc `this.value` chọn field của `Child`.
- `super.value` chọn field kế thừa/tương ứng của superclass, nếu truy cập hợp lệ.
- `super` gắn với **inheritance**, không có nghĩa “biến local ở block ngoài”.

Field của superclass vẫn là thành viên khác. Phân giải tên và quyền truy cập là những bước liên quan nhưng tách biệt.

## 4. Bốn mức truy cập thành viên của Java

Thông thường fields, methods và constructors có các access modifiers sau:

| Access level | Khai báo | Quy tắc khái quát |
| --- | --- | --- |
| **private** | `private int secret;` | Code trong class/nest được phép; class không liên quan không tự truy cập |
| **package-private** | `int count;` (không ghi modifier) | Code cùng package có quyền theo quy tắc thông thường |
| **protected** | `protected int value;` | Cùng package; ngoài package có quyền từ ngữ cảnh subclass thích hợp, với giới hạn receiver |
| **public** | `public int value;` | Code bên ngoài có thể truy cập nếu lớp chứa, package/module và biểu thức khác đều hợp lệ |

**Package-private không phải modifier viết ra bằng từ khóa `default`.** Không ghi modifier mới là package-private. `default` có ý nghĩa khác ở interface default methods.

Ở những lớp thư viện thực tế, thường dùng **`private` cho mutable state** và cung cấp public/protected/package-private methods có trách nhiệm rõ ràng thay vì mở mọi field. Điều này bảo vệ **invariants** của object và giúp thay đổi implementation mà không phá caller.

### 4.1. Chỉ modifier chưa đủ để kết luận hợp lệ

Một lời gọi `obj.method()` có thể còn phụ thuộc:

1. `obj` có nằm trong scope, có kiểu tĩnh nào?
2. Kiểu chứa method có accessible không?
3. Caller có quyền truy cập method không?
4. Đây là static hay instance member, có receiver phù hợp không?
5. Method signature có áp dụng cho đối số không?
6. Package có được export từ named module cho module caller hay không?
7. Tại runtime, `obj` có bị `null` hoặc method ném exception không?

Trong đó, (1) thuộc tên/scope; (2)(3)(6) thuộc accessibility; (4)(5) thuộc kiểm tra ngữ cảnh/kiểu; (7) là hành vi runtime.

## 5. Top-level class và nested class có quy tắc khai báo access khác nhau

Đối với **top-level class/interface**, khai báo trực tiếp ở cấp package chỉ dùng `public` hoặc **không có access modifier** (package-private). Không khai báo một top-level class là `private` hoặc `protected`.

Ví dụ trong file **`LibraryType.java`**:

~~~java
public class LibraryType {
    public String label() {
        return "API";
    }
}

class InternalType {
}
~~~

Hai top-level classes hợp lệ trong cùng file, vì chỉ có một top-level class `public` khớp tên file. `InternalType` package-private: mã thuộc package khác không tự truy cập nó bằng tên, dù file nằm chung repository.

Đối với **nested member classes**, có thể dùng các access modifiers khác:

~~~java
public class Container {
    public static class PublicNested { }
    protected static class ProtectedNested { }
    static class PackageNested { }
    private static class PrivateNested { }
}
~~~

Đây là class `Container.java` hợp lệ. `Container` public không làm `PrivateNested` public. Nếu code ở nơi không có quyền truy cập `Container.PrivateNested`, viết tên đầy đủ hơn hoặc thêm `import` không giải quyết vấn đề.

**Lưu ý:** non-static member classes cũng có access modifiers tương ứng. Tính `static`/không `static` quyết định quan hệ enclosing instance, **không trực tiếp thay access level**.

## 6. Ví dụ private: tên field tồn tại nhưng class ngoài không có quyền

Lưu **`PrivateMemberDemo.java`**:

~~~java
public class PrivateMemberDemo {
    private final int secret = 42;

    public int readSecret() {
        return secret;
    }

    public static void main(String[] args) {
        PrivateMemberDemo item = new PrivateMemberDemo();

        System.out.println("same class=" + item.secret);
        System.out.println("external via API=" + Reader.read(item));
    }
}

class Reader {
    static int read(PrivateMemberDemo item) {
        // return item.secret; // Không hợp lệ: private access.
        return item.readSecret();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PrivateMemberDemo.java
java PrivateMemberDemo
~~~

Output:

~~~text
same class=42
external via API=42
~~~

**Tại sao khác nhau?**

- `main` nằm trong chính `PrivateMemberDemo`, có quyền đọc field `secret` của một instance `PrivateMemberDemo`.
- `Reader` là một **top-level class khác**. Dù đặt chung file Java, nó **không** thuộc cùng nest của `PrivateMemberDemo`, nên không có quyền đọc trực tiếp private field.
- `Reader.read` vẫn có thể dùng parameter `item`: **tên parameter đang nằm trong scope**, và public method `item.readSecret()` có thể truy cập được. Dòng comment `item.secret` bị chặn vì **accessibility**, không vì tên `item` bị mất phạm vi.

Đây là một trong những ví dụ dễ phân biệt hai khái niệm nhất: **`item` có scope hợp lệ** nhưng **`secret` là inaccessible member** đối với vị trí gọi.

## 7. Nested classes có thể truy cập private members trong cùng nest

Quy tắc `private` cho phép quyền truy cập giữa những lớp cùng **nest** theo mô hình Java. Inner class có thể dùng field private của enclosing class; outer class có thể dùng private field của inner class khi đáp ứng quan hệ tương ứng.

Lưu **`NestedPrivateAccessDemo.java`**:

~~~java
public class NestedPrivateAccessDemo {
    private final String owner = "OUTER";

    private class Inner {
        private final String value = "INNER";

        void showOwner() {
            System.out.println("inner reads=" +
                    NestedPrivateAccessDemo.this.owner);
        }
    }

    void run() {
        Inner inner = new Inner();
        inner.showOwner();
        System.out.println("outer reads=" + inner.value);
    }

    public static void main(String[] args) {
        new NestedPrivateAccessDemo().run();
    }
}
~~~

Lệnh:

~~~bash
javac NestedPrivateAccessDemo.java
java NestedPrivateAccessDemo
~~~

Output:

~~~text
inner reads=OUTER
outer reads=INNER
~~~

- `Inner` là nested class nằm trong lexical context của outer class.
- `NestedPrivateAccessDemo.this` chỉ **enclosing outer instance**; nó không phải superclass hay static class literal.
- `inner.value` truy cập private field của nested class từ enclosing class theo quy tắc nest access.
- `private` vẫn ngăn **những class bên ngoài quan hệ nest** tùy ý truy cập các fields ấy.

**Không được suy ra rằng hai top-level classes chung file hoặc chung package tự có quyền private của nhau.** Quyền nest không đồng nghĩa quyền theo file.

## 8. Package-private và quyền truy cập cùng package

Package-private được tạo bằng cách **không khai báo access modifier** ở member hoặc top-level class tương ứng.

~~~java
package store;

public class Item {
    int quantity = 5;               // package-private
    protected String type = "BOOK"; // protected
    public String code = "J17";     // public
    private int pin = 12;           // private

    public int showPinForDemo() {
        return pin;
    }
}
~~~

Đây là ví dụ nguồn `store/Item.java`, dùng trong ví dụ ba file sau.

### 8.1. Ví dụ đa tệp có thể chạy độc lập

Tạo cấu trúc:

~~~text
project/
  store/
    Item.java
    Peer.java
  app/
    Main.java
~~~

**`store/Item.java`**:

~~~java
package store;

public class Item {
    int quantity = 5;
    protected String type = "BOOK";
    public String code = "J17";
    private int pin = 12;

    public int showPinForDemo() {
        return pin;
    }
}
~~~

**`store/Peer.java`**:

~~~java
package store;

public class Peer {
    public static String describe(Item item) {
        return item.quantity + "," + item.type + "," +
                item.code + "," + item.showPinForDemo();
    }
}
~~~

**`app/Main.java`**:

~~~java
package app;

import store.Item;
import store.Peer;

public class Main {
    public static void main(String[] args) {
        Item item = new Item();
        System.out.println("public=" + item.code);
        System.out.println("same package helper=" + Peer.describe(item));

        // System.out.println(item.quantity); // package-private: không được.
        // System.out.println(item.type);     // protected: không được từ app.Main.
        // System.out.println(item.pin);      // private: không được.
    }
}
~~~

Đứng tại thư mục `project` và chạy:

~~~bash
javac -d out store/Item.java store/Peer.java app/Main.java
java -cp out app.Main
~~~

**Stdout:**

~~~text
public=J17
same package helper=5,BOOK,J17,12
~~~

**Giải thích:**

1. `Item` là public top-level class, nên `Main` dùng được kiểu khi không có rào cản module khác.
2. `Item.code` là public, có thể đọc trực tiếp từ `app.Main`.
3. `Item.quantity` là package-private: `store.Peer` cùng package đọc được, `app.Main` khác package không được.
4. `Item.type` là protected: `store.Peer` có quyền do cùng package. `app.Main` khác package và không phải subclass, không thể đọc trực tiếp.
5. `Item.pin` là private: ngay cả `store.Peer` cùng package cũng không đọc trực tiếp. Nó phải đi qua public method mà `Item` cố ý cung cấp.
6. Hai dòng `import` ở `app.Main` giúp dùng tên kiểu `Item`, `Peer` ngắn hơn. Chúng **không cấp quyền truy cập mới** vào fields.

**Không nên áp dụng ví dụ tiết lộ PIN này vào hệ thống thật**: public method công bố dữ liệu bí mật chỉ là cách làm rõ access control trong bài học. API nghiệp vụ cần có thiết kế bảo mật độc lập.

### 8.2. Hai package có dấu chấm giống nhau vẫn là hai package khác nhau

`com.demo` và `com.demo.internal` không có “quan hệ thừa kế quyền package-private”. Chúng là **hai packages**. Chỉ dựa vào tên thư mục gần nhau hoặc việc cùng project không thể kết luận các thành viên package-private truy cập được.

## 9. `protected`: khó nhất khi subclass nằm ở package khác

`protected` không đồng nghĩa với “chỉ subclass được phép sử dụng”, vì mã **cùng package** cũng có thể truy cập protected member theo quy tắc thông thường.

Ở **package khác**, protected instance members áp dụng những điều kiện bổ sung: code phải ở **ngữ cảnh subclass phù hợp** và kiểu của **receiver expression** phải thỏa quy tắc Java. Không phải mọi object kiểu superclass đều có thể dùng làm receiver chỉ vì code caller là subclass.

### 9.1. Ví dụ chạy được với hai package

Tạo:

~~~text
project/
  base/
    Base.java
  child/
    Child.java
~~~

**`base/Base.java`**:

~~~java
package base;

public class Base {
    protected int level = 7;

    protected void ping() {
        System.out.println("Base.ping");
    }
}
~~~

**`child/Child.java`**:

~~~java
package child;

import base.Base;

public class Child extends Base {
    void test() {
        System.out.println("this.level=" + this.level);

        Child other = new Child();
        System.out.println("other.level=" + other.level);

        ping();

        Base arbitraryBase = new Base();
        // System.out.println(arbitraryBase.level); // Không được.
        // arbitraryBase.ping(); // Không được.
    }

    public static void main(String[] args) {
        new Child().test();
    }
}
~~~

Đứng tại `project`:

~~~bash
javac -d out base/Base.java child/Child.java
java -cp out child.Child
~~~

**Stdout:**

~~~text
this.level=7
other.level=7
Base.ping
~~~

Giải thích:

- `Child` là subclass của `Base` và nằm ở package khác.
- Từ instance method của `Child`, `this.level` và `ping()` được phép theo quy tắc protected.
- `other` có **kiểu tĩnh `Child`**. Với ngữ cảnh này, `other.level` hợp lệ.
- `arbitraryBase` có kiểu tĩnh `Base`. Dù code viết trong subclass, **receiver kiểu Base tùy ý** không thỏa quy tắc truy cập protected instance member ở khác package.
- `import base.Base` chỉ làm tên Base thuận tiện hơn, không làm `arbitraryBase.level` hợp lệ.

**Trường hợp protected constructor:** constructor có quy tắc chi tiết riêng. Subclass ở package khác có thể sử dụng constructor cha trong constructor invocation `super(...)` được phép; không tự suy rằng protected constructor cho phép mọi caller bên ngoài tạo Base bằng `new Base()`.

Để xác định chính xác các trường hợp kế thừa phức tạp, xem JLS `6.6.2 thay vì chỉ dùng câu “protected = class con”.

## 10. `import` giải quyết tên, không mở khóa thành viên

Import khai báo khả năng sử dụng tên kiểu:

~~~java
import java.util.ArrayList;
~~~

Sau đó bạn có thể viết `ArrayList<String>` thay vì `java.util.ArrayList<String>` khi ngữ cảnh hợp lệ.

Nhưng **import không**:

- Biến top-level package-private class thành public.
- Thay `private`, package-private hay `protected` field thành accessible.
- Đảm bảo public member có receiver hợp lệ.
- Thay đổi class inheritance, nest hoặc package membership.
- Vượt qua package export restrictions của named modules.

Nếu một class thuộc package khác **không public**, đổi `import package.Internal;` thành `package.Internal` không sửa được lỗi accessibility. Fully qualified name chỉ chọn đúng tên kiểu; quyền truy cập vẫn phải được đáp ứng.

Tương tự, wildcard import `import java.util.*;` **không** tự import các subpackages như `java.util.concurrent` và không mở quyền private của bất kỳ class nào.

## 11. `static context` khác accessibility

Một static method thuộc cùng class có quyền đọc **private instance fields** của một object được cấp rõ ràng, nhưng nó không có `this` của object đang gọi theo cách instance method có.

Lưu **`StaticMemberContextDemo.java`**:

~~~java
public class StaticMemberContextDemo {
    private int count = 3;
    private static int global = 10;

    private void increase() {
        count++;
    }

    static void print(StaticMemberContextDemo target) {
        // System.out.println(count); // Sai: thiếu instance receiver.
        System.out.println("before=" + target.count);
        target.increase();
        System.out.println("after=" + target.count);
        System.out.println("global=" + global);
    }

    public static void main(String[] args) {
        StaticMemberContextDemo object = new StaticMemberContextDemo();
        print(object);
    }
}
~~~

Chạy:

~~~bash
javac StaticMemberContextDemo.java
java StaticMemberContextDemo
~~~

Output:

~~~text
before=3
after=4
global=10
~~~

- Private accessibility **được đáp ứng** vì `print` nằm trong chính class.
- Đọc `count` bằng tên đơn giản như một instance field trong static context không có receiver thích hợp, nên lỗi dù field private vẫn accessible về mặt access.
- `target.count` và `target.increase()` hợp lệ vì có receiver `target`.
- `global` là static field nên có thể dùng trong static method mà không có instance receiver.

Nếu `target == null`, code có thể ném `NullPointerException` khi truy cập instance field; **NPE là runtime issue**, không phải compiler báo scope hay private access.

## 12. Constructor và quyền tạo object

Constructor cũng có access modifier, độc lập với khả năng nhìn thấy tên class.

~~~java
public final class Token {
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

Đây là tệp `Token.java` biên dịch được. Caller ngoài quyền private có thể:

~~~java
Token token = Token.of("A");
~~~

nhưng không được tự viết `new Token("A")` vì constructor `Token(String)` là private, dù **kiểu `Token` public** và tên được nhận diện.

**Lưu ý:** một class public có constructor tường minh **không modifier** thì constructor đó là package-private, không tự động public. Khi một class hoàn toàn không khai báo constructor, compiler có quy tắc về implicit default constructor; đó là vấn đề tồn tại/khởi tạo constructor, cần tách với access.

## 13. Field scope, thứ tự khai báo và forward references

Field có scope theo class body, khác local variables có scope theo block. Vì thế các instance methods của cùng class có thể cùng truy cập field:

~~~java
class Counter {
    int total = 5;

    void first() {
        System.out.println(total);
    }

    void second() {
        System.out.println(total);
    }
}
~~~

Tuy vậy, scope **không bảo đảm** mọi cách đọc field trước khai báo đều hợp lệ. Java có **illegal forward reference rules** cho một số trường hợp trong field initializers và initializer blocks.

Ví dụ cố ý sai:

~~~java
// class IllegalForward {
//     int copy = value; // Illegal forward reference.
//     int value = 5;
// }
~~~

Bạn có thể đọc một field trong instance method dù field được khai báo ở phần source phía sau method, nhưng ở **initializer context** những hình thức đọc tên đơn giản sớm có thể bị cấm.

Điều này minh họa thêm các lớp quy tắc ngoài scope/access:

- **Name scope:** member được khai báo trong class body.
- **Forward reference restrictions:** một số vị trí đọc sớm không hợp lệ.
- **Initialization order:** default values và field initializers xảy ra theo thứ tự nhất định khi object được tạo.

Không nên sửa các lỗi đó bằng cách đổi field thành `public`.

## 14. `public` vẫn còn điều kiện class và module

Giả sử:

~~~java
// Trong package service:
class InternalEngine {
    public void execute() { }
}
~~~

`InternalEngine` là top-level **package-private**, dù method `execute()` là `public`. Caller ở package khác **không** tự dùng được tên `InternalEngine` theo cách thông thường.

Trong dự án có JPMS (`module-info.java`), public types ở một package thuộc named module cũng còn phụ thuộc **module readability** và việc package có được **export** cho module caller thích hợp không.

Ví dụ minh họa module declaration:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Điều này export `com.example.api`, không tự export mọi package implementation. `exports` dùng cho khả năng truy cập type/member ở mức module; `opens` liên quan truy cập phản chiếu sâu (*deep reflection*) theo quy tắc JPMS, không phải từ đồng nghĩa.

## 15. Phân biệt scope, access, type và runtime errors

| Tình huống | Nhóm vấn đề chính | Hướng xử lý |
| --- | --- | --- |
| Sử dụng local `x` sau khi ra khỏi block | **Scope** | Đưa khai báo ra block phù hợp, truyền giá trị hoặc trả result |
| Method B sử dụng trực tiếp local variable của method A | **Scope** | Truyền parameter hoặc dùng state có sở hữu rõ |
| Parameter `value` che field cùng tên | **Shadowing** | Dùng `this.value` |
| Top-level class B truy cập private field của A | **Accessibility** | Dùng API công khai thích hợp |
| Class khác package đọc package-private field | **Accessibility** | Giữ đúng ranh giới package, dùng method accessible |
| Subclass khác package đọc protected trên arbitrary Base receiver | **Protected access** | Dùng receiver/ngữ cảnh hợp lệ hoặc public API |
| Static method gọi instance field qua tên đơn giản | **Static/instance context** | Dùng instance receiver |
| Biến local chưa gán nhưng đã được đọc | **Definite assignment** | Gán trên mọi đường thực thi phù hợp |
| Public method nhận int nhưng caller truyền String | **Type checking / overload** | Dùng đối số/chữ ký đúng |
| Instance reference là null khi gọi method | **Runtime NPE** | Kiểm tra hợp đồng giá trị, tránh null không hợp lệ |
| Public class trong package module không export | **Module accessibility** | Thiết kế exports/readability phù hợp |
| Field khai báo sau bị đọc sớm trong initializer | **Forward reference** | Sắp xếp khởi tạo đúng quy tắc |

Một lỗi compiler có thể liên quan **nhiều lớp kiểm tra** cùng lúc. Ví dụ một field `private int count` xuất hiện trong static method của class ngoài: vừa có thể thiếu quyền truy cập vừa có thể thiếu instance receiver. Cách chẩn đoán tốt là kiểm tra từ tên/kiểu tới quyền/ngữ cảnh, thay vì chỉ dựa vào một chuỗi báo lỗi.

## 16. Quy trình phân tích một biểu thức có tên

Khi đọc `object.member` hoặc một tên đơn giản `member`, hãy dùng quy trình:

1. **Xác định khai báo thực sự:** `member` là local, parameter, field, method, type hay một tên package?
2. **Xác định phạm vi:** ở vị trí source này, tên đơn giản có còn trong lexical scope hay được import/phân giải hợp lệ không?
3. **Kiểm tra shadowing/hiding:** có parameter/local/field gần hơn che khai báo cần dùng không? Dùng `this.member`, `Outer.this.member`, `super.member` hoặc tên kiểu tường minh khi đúng ngữ nghĩa.
4. **Kiểm tra loại member:** static hay instance? Có receiver nếu cần không?
5. **Kiểm tra accessibility:** modifier, class chứa, package, nest, subclass và protected receiver rules.
6. **Kiểm tra module:** package có exported cho module caller nếu đang sử dụng JPMS không?
7. **Kiểm tra type:** kiểu tĩnh receiver, overload và kiểu đối số có tương thích không?
8. **Kiểm tra khởi tạo:** local có definitely assigned; field initializer có forward-reference restriction không?
9. **Phân biệt compile/runtime:** code hợp lệ có thể vẫn ném exception khi chạy, ví dụ null receiver.

Thứ tự này giúp tránh những “bản vá” nguy hiểm như đổi mọi fields thành `public` hoặc biến state riêng của từng object thành `static` chỉ để compiler hết báo lỗi.

## 17. Những nhầm lẫn thường gặp

| Nhầm lẫn | Sự thật |
| --- | --- |
| “Scope và access modifier là một.” | Scope và accessibility là hai tập quy tắc khác nhau. |
| “Local variables mặc định private.” | Local variables không có `private/public` như members. |
| “Private field không tồn tại ngoài class.” | Field vẫn tồn tại; mã ngoài quyền không truy cập trực tiếp được. |
| “Import một class sẽ đọc được mọi private fields.” | Import chỉ giúp dùng tên kiểu; access không đổi. |
| “Hai top-level classes chung file truy cập private của nhau.” | Không tự động; cần quan hệ nest phù hợp. |
| “Các class cùng package truy cập mọi private member.” | Không; package-private và private khác nhau. |
| “Protected chỉ cho subclasses, không cho same package.” | Cùng package cũng có protected access theo quy tắc. |
| “Mọi subclass ở package khác có thể đọc protected trên bất cứ Base object.” | Không; có receiver restrictions. |
| “Public field luôn dùng được từ mọi chỗ.” | Cần kiểu chứa, module, receiver và expression hợp lệ. |
| “Static method không thể đụng private instance field.” | Có thể qua object receiver khi access được phép. |
| “Dùng `this.` vượt qua quyền private.” | `this` chọn instance member, không tự mở quyền. |
| “`Outer.this` giống `super`.” | Một cái chỉ enclosing instance, một cái gắn với inheritance. |
| “Scope hợp lệ thì chắc chắn được đọc local.” | Cần definite assignment trước khi đọc. |
| “Tên field có scope class nên mọi forward reference đều hợp lệ.” | Field initializer có restrictions riêng. |
| “`public` sửa được lỗi local ra khỏi block.” | Access modifier không thay đổi lexical scope. |
| “Nếu code đã compile thì member không thể gây lỗi.” | Runtime vẫn có NPE, exceptions hoặc sai invariants. |

## 18. Câu hỏi tự kiểm tra có lời giải

**Câu 1.** Biến `int x` khai báo trong một block nhưng đọc sau dấu đóng block; đây là lỗi gì?  
**Đáp án:** Scope. `x` không còn trong phạm vi sử dụng tại vị trí đó.

**Câu 2.** Parameter `int value` có thể thêm `private` để giảm scope không?  
**Đáp án:** Không. Parameters/local variables không có access modifier như field; scope của parameter do khai báo method quyết định.

**Câu 3.** Trong `void set(int value) { value = value; }`, vì sao field `this.value` không đổi?  
**Đáp án:** Parameter shadow field. Phép gán chỉ tác động parameter; muốn sửa field cần `this.value = value`.

**Câu 4.** Class A có private field `secret`. Class B là top-level class khác cùng file. B đọc trực tiếp `a.secret` được không?  
**Đáp án:** Không tự động. Cùng source file không khiến hai top-level classes có cùng nest/private access.

**Câu 5.** Một class cùng package có được đọc package-private field của class khác không?  
**Đáp án:** Có, khi khai báo và expression phù hợp; khác với private field.

**Câu 6.** `import store.Item;` có làm `Item.quantity` package-private accessible từ package `app` không?  
**Đáp án:** Không. Import chỉ tác động cách phân giải tên kiểu.

**Câu 7.** Một class không là subclass nhưng cùng package có thể truy cập protected field của class khác không?  
**Đáp án:** Có, theo quy tắc protected access trong cùng package.

**Câu 8.** Subclass `Child` ở package khác được dùng `this.level` protected của `Base`, nhưng vì sao `new Base().level` có thể bị cấm?  
**Đáp án:** Protected instance access ở khác package có điều kiện về ngữ cảnh subclass và kiểu receiver; một Base object tùy ý không tự thỏa điều kiện ấy.

**Câu 9.** Static method trong cùng class có thể dùng `target.privateField` không?  
**Đáp án:** Có nếu target có kiểu thích hợp và không null ở runtime. Nhưng không thể dùng instance field bằng tên đơn giản như có `this`.

**Câu 10.** Nested inner class có thể đọc private field của enclosing class bằng `Outer.this.field` không?  
**Đáp án:** Có trong ngữ cảnh enclosing instance/nest hợp lệ; qualified `this` chọn đúng object.

**Câu 11.** `int n; System.out.println(n);` trong method có lỗi gì?  
**Đáp án:** Local variable chưa definitely assigned, không phải thiếu private/public permission.

**Câu 12.** Top-level class package-private có public method. Caller từ package khác có luôn gọi method này bằng `new Internal().method()` không?  
**Đáp án:** Không. Class chứa member có thể inaccessible, dù method là public.

**Câu 13.** Class `public Account` khai báo `Account() { }` không modifier. Caller từ package khác có thể tạo bằng `new Account()` không?  
**Đáp án:** Không: constructor này package-private. Class public không tự biến mọi constructor thành public.

**Câu 14.** Hai package `com.demo` và `com.demo.internal` có chia sẻ package-private access không?  
**Đáp án:** Không. Chúng là hai package khác nhau, dù tên có dạng phân cấp.

**Câu 15.** Named module không export một package chứa public class. Module khác có tự dùng class ấy được không?  
**Đáp án:** Không mặc nhiên. Cần xét readability/exports của JPMS.

**Câu 16.** Một field `count` được khai báo phía sau method dùng nó. Method có nhất thiết lỗi vì khai báo xuất hiện sau không?  
**Đáp án:** Không. Field có scope theo class body. Nhưng các trường hợp đọc sớm trong initializers có forward-reference restrictions riêng.

**Câu 17.** Public method `run(int)` được gọi với `run("text")` và không có overload khác. Đây là access error không?  
**Đáp án:** Không. Method public nhưng lời gọi sai kiểu đối số, thuộc type checking/overload resolution.

**Câu 18.** `this.field` có biến một private field thành public không?  
**Đáp án:** Không. `this.field` là phép chọn instance field; accessibility vẫn được kiểm tra theo vị trí sử dụng.

## Tài liệu tham khảo

- Java Language Specification, [`6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3) — scope của các khai báo.
- Java Language Specification, [`6.4 — Shadowing and Obscuring](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.4) — shadowing/hiding tên.
- Java Language Specification, [`6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6) — quyền truy cập kiểu và thành viên.
- Java Language Specification, [`6.6.2 — Details on protected Access](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6.2) — điều kiện protected với subclass/receiver khác package.
- Java Language Specification, [`8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3) — field và một số ràng buộc về initializers.
- Java Language Specification, [`7 — Packages and Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html) — package/module và ranh giới truy cập.

## Tổng kết

**Phạm vi tên (scope)** trả lời **“tên ở vị trí mã nguồn này có được nhận diện theo khai báo nào?”**. **Quyền truy cập (accessibility)** trả lời **“caller có được phép sử dụng kiểu/thành viên ấy theo Java access control?”**. Một biến local có thể ra khỏi scope dù không mang `private`; một field `private` có thể tồn tại nhưng class khác không được đọc trực tiếp. `import` hỗ trợ tên kiểu, không mở khóa members; `this` phân biệt receiver/field bị che khuất, không làm thay đổi quyền; `protected` ở package khác còn có receiver restrictions.

Hãy kiểm tra riêng **scope → name resolution/shadowing → access modifier/package/nest/subclass → static/instance context → kiểu/khởi tạo → runtime**. Khi hiểu từng lớp quy tắc, bạn sẽ giải thích compiler errors chính xác hơn và thiết kế class-object API vừa dễ dùng, vừa giữ được encapsulation.
