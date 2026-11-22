# Gọi phương thức ghi đè khi đối tượng chưa khởi tạo xong trong Java

Khi tạo object thuộc một **subclass**, Java phải thực hiện quá trình khởi tạo theo chuỗi từ superclass đến subclass. Một điểm dễ gây lỗi là **constructor của superclass có thể gọi một instance method được subclass ghi đè (*override*)**. Java vẫn thực hiện **dynamic dispatch** theo lớp thực tế của object, ngay cả khi quá trình khởi tạo object đó **chưa hoàn tất**.

Hệ quả: method override của subclass có thể chạy **trước khi field initializers, instance initializer blocks và constructor body của subclass thực thi**. Những instance fields thuộc subclass lúc ấy có thể còn mang giá trị mặc định như `null`, `0` hoặc `false`, kể cả khi mã nguồn đã khai báo initializer hoặc `final` field sẽ được gán trong constructor. Điều này có thể làm sai invariant, đọc state chưa hợp lệ, ném `NullPointerException` hoặc gây ra các tác dụng phụ rất khó tìm nguyên nhân.

**Nguyên tắc thiết kế:** **không gọi method có thể override từ constructor hoặc instance initializer khi hành vi của method phụ thuộc vào trạng thái của subclass chưa khởi tạo xong**. Ưu tiên constructor chỉ validate/gán state của chính lớp đó, dùng helper `private`/`final` thích hợp, hoặc tách thao tác đa hình sang giai đoạn **sau khi object được xây dựng hoàn chỉnh**.

Bài học Java 17+ này giải thích thứ tự khởi tạo, dynamic dispatch trong constructor, sự khác nhau giữa field initializer và giá trị mặc định, các lời gọi trực tiếp/gián tiếp, ví dụ lỗi chạy được, sửa thiết kế bằng API an toàn, constructor chaining, `final`/`private`/`static`, `this` escape, ảnh hưởng của record và concurrency, cùng checklist rà soát.

## 1. Vì sao cùng một method lại nguy hiểm trong constructor nhưng hợp lệ sau đó?

Xét hai class:

~~~java
class Parent {
    Parent() {
        describe(); // Có thể dispatch vào subclass
    }

    void describe() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    private String name = "Ready";

    @Override
    void describe() {
        System.out.println("Child name = " + name);
    }
}
~~~

Đây là **đoạn khai báo minh họa**, chưa có `main` chạy độc lập.

Nếu thực thi `new Child()`, constructor `Parent()` sẽ gọi `describe()`. Object đang được tạo **thật sự thuộc class Child**, nên invocation của method overridable có thể chạy `Child.describe()`. Nhưng initializer `name = "Ready"` **chưa chạy**, bởi constructor superclass chưa hoàn tất. Vì thế method override có thể in:

~~~text
Child name = null
~~~

Sau khi `Parent()` trở về, phần khởi tạo instance của Child mới chạy, `name` mới nhận `"Ready"`. Nếu gọi `child.describe()` **sau khi `new Child()` hoàn tất**, kết quả lại là:

~~~text
Child name = Ready
~~~

**Hai lời gọi dùng cùng implementation `Child.describe()` nhưng chạy tại hai thời điểm khác nhau của vòng đời object.** Không phải Java ngẫu nhiên chọn superclass lúc đầu và subclass lúc sau: **dynamic dispatch vẫn chọn subclass implementation**, còn state của subclass mới khác nhau.

### 1.1. Đây là lỗi thiết kế vòng đời, không chỉ là lỗi cú pháp

Các class có thể **biên dịch thành công** dù constructor gọi method overridable. Java không cấm tuyệt đối kiểu lời gọi này ở compile time. Tuy nhiên, compiler không bảo đảm override của các subclasses tương lai sẽ chỉ đọc những field đã khởi tạo.

Một subclass do thư viện hoặc developer khác viết có thể thay đổi behavior, dùng dependencies, đăng ký listener, phát thông báo hoặc truy cập một field `final` chưa được gán. Vì vậy, vấn đề chính là **contract của constructor và extension point**, không phải chỉ một ngoại lệ đặc biệt của ví dụ.

## 2. Thứ tự khởi tạo instance trong Java 17

Khi tạo một instance bằng `new Child(...)`, xét một superclass chain đơn giản `Object → Parent → Child`, Java thực hiện các bước khái niệm sau:

1. Cấp phát object có runtime type **Child**; các instance fields của toàn bộ object bắt đầu với **giá trị mặc định** theo kiểu Java.
2. Thực thi chuỗi constructor superclass (cuối cùng đi qua `Object`) theo quy tắc explicit/implicit constructor invocations.
3. Trong quá trình khởi tạo **Parent**, thực thi instance field initializers và instance initializer blocks của Parent theo thứ tự nguồn thích hợp, rồi constructor body Parent.
4. Sau khi đường khởi tạo Parent thành công, thực thi **instance field initializers và instance initializer blocks của Child**, theo thứ tự khai báo tương ứng.
5. Thực thi phần còn lại của **Child constructor body** sau lời gọi superclass/constructor chaining.
6. Nếu các bước hoàn tất bình thường, lời gọi `new Child(...)` mới trả tham chiếu cho caller.

Quy tắc trên nhằm giải thích đường khởi tạo bình thường; các trường hợp `this(...)` constructor chaining có thêm quy tắc tránh khởi tạo instance initializers hai lần, và exceptions có thể chấm dứt quá trình trước khi hoàn tất.

~~~text
new Child(...)
    |
    v
Object được cấp phát, tất cả instance fields có default values
    |
    v
Object / superclass constructor chain
    |
    v
Parent field initializers + Parent instance initializers
    |
    v
Parent constructor body
    |       |
    |       +--> gọi virtualMethod()
    |                  |
    |                  +--> dispatch tới Child.override()
    |                              Child fields vẫn có thể null / 0
    |
    v
Child field initializers + Child instance initializers
    |
    v
Child constructor body
    |
    v
new Child(...) hoàn tất bình thường
~~~

**Quan trọng:** class Child đã là **runtime class** của object từ lúc được tạo. Không có một Parent object riêng rồi sau đó “biến hình” thành Child object. Constructor Parent chạy **trên cùng object đang được xây dựng**, nhưng phần khởi tạo của Child chưa thực thi.

### 2.1. Phân biệt static initialization

Static field initializers/static initializer blocks thuộc quá trình **class initialization**, không phải từng instance. Khi dùng class theo những điều kiện active use, JVM khởi tạo class và superclass theo quy tắc liên quan. Không nên trộn “static initializer chạy một lần theo runtime class” với “instance initializer của Child chỉ chạy sau Parent constructor”.

Bài này tập trung vào **trạng thái instance của subclass**. Một static field đã sẵn sàng không chứng minh final/instance fields của một Child object đã được khởi tạo.

### 2.2. Giá trị mặc định lúc cấp phát

| Loại field instance | Giá trị mặc định trước initializer/constructor assignment |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` tương ứng kiểu |
| `float`, `double` | `0.0` tương ứng kiểu |
| `boolean` | `false` |
| `char` | ký tự `'\u0000'` |
| Reference như `String`, `List<?>`, class khác, mảng | `null` |

Field có initializer như `int size = 10;` **không nhận 10 ngay tại thời điểm cấp phát object trước mọi constructor**. Nó bắt đầu với giá trị mặc định rồi mới được gán bởi instance initialization tương ứng.

Đây là nguyên nhân method override được gọi từ constructor lớp cha có thể nhìn thấy **`0` thay vì 10** hoặc **`null` thay vì chuỗi khởi tạo trong mã nguồn**.

## 3. Dynamic dispatch vẫn xảy ra trong superclass constructor

Instance methods thông thường có thể override được gọi thông qua receiver. Trong constructor Parent, receiver ngầm định của `describe()` là **`this`**, chính object đang được khởi tạo.

~~~java
class Base {
    Base() {
        announce();      // Invocation có receiver ngầm định this
        this.announce(); // Cùng ý nghĩa receiver, nếu code chọn gọi lần nữa
    }

    void announce() {
        System.out.println("Base");
    }
}
~~~

Nếu object đang tạo thuộc subclass `Derived` và Derived override `announce()`, **cả hai invocation hợp lệ trên đều có thể dispatch đến Derived implementation**. `this` ở constructor Base không phải một Base object riêng; nó là reference tới **object runtime thực tế**, có thể là Derived.

### 3.1. Không nhầm compile-time checking với runtime implementation

Compiler xác nhận `announce()` là member có thể gọi từ vị trí constructor Base. Sau đó, với virtual instance method call, JVM chọn implementation thích hợp dựa trên runtime class của receiver. Constructor được viết trong Base **không ép virtual call luôn chạy Base.announce()**.

Điều này bảo đảm polymorphism nhất quán ở nhiều nơi, nhưng tạo một **giai đoạn nguy hiểm** khi đối tượng chưa xây dựng xong.

### 3.2. Từ ngữ chính xác

- **Overridable instance method:** method có thể được subclass override hợp lệ, tùy visibility và các modifiers như `final`, `private`, `static`.
- **Override:** subclass cung cấp implementation cho method đã được kế thừa theo quy tắc Java.
- **Dynamic dispatch:** chọn implementation của overridable method theo runtime receiver.
- **Partially initialized object:** object đang được xây dựng, một phần initialization code chưa hoàn tất.
- **Invariant:** điều kiện state mà object cam kết duy trì khi được sử dụng theo hợp đồng.

Lỗi ở đây xảy ra khi **method override kỳ vọng invariant của Child đã được thiết lập**, nhưng lời gọi diễn ra khi invariant ấy chưa có.

## 4. Chương trình chạy được: thấy `null` và `0` dù subclass có initializer

Tạo tệp **`PrematureOverrideDemo.java`**:

~~~java
public class PrematureOverrideDemo {
    static class Parent {
        Parent() {
            System.out.println("1. Parent constructor");
            showState();
            System.out.println("3. Parent constructor done");
        }

        void showState() {
            System.out.println("Parent.showState");
        }
    }

    static final class Child extends Parent {
        private final String name;
        private int count = initializeCount();

        private int initializeCount() {
            System.out.println("4. Child field initializer");
            return 7;
        }

        {
            System.out.println("5. Child instance initializer");
        }

        Child(String name) {
            this.name = name;
            System.out.println("6. Child constructor");
        }

        @Override
        void showState() {
            System.out.println("2. Child.showState name="
                    + name + ", count=" + count);
        }

        String summary() {
            return "name=" + name + ", count=" + count;
        }
    }

    public static void main(String[] args) {
        Child child = new Child("Lan");
        System.out.println("7. Ready: " + child.summary());
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 PrematureOverrideDemo.java
java PrematureOverrideDemo
~~~

**Stdout chính xác:**

~~~text
1. Parent constructor
2. Child.showState name=null, count=0
3. Parent constructor done
4. Child field initializer
5. Child instance initializer
6. Child constructor
7. Ready: name=Lan, count=7
~~~

Đọc từng bước:

1. `new Child("Lan")` bắt đầu xây dựng object runtime type Child. `name` mặc định `null` và `count` mặc định `0`.
2. Constructor Parent in dòng số 1, sau đó gọi `showState()`.
3. `Child.showState()` được chọn **do overriding**, dù Child constructor chưa chạy. Dòng số 2 đọc `name=null` và `count=0`.
4. Constructor Parent in dòng số 3 rồi kết thúc.
5. Instance field initializer của Child gọi `initializeCount()`, in dòng số 4 rồi gán `count=7`.
6. Instance initializer block của Child chạy, in dòng số 5.
7. Child constructor gán blank final field `name = "Lan"` rồi in dòng số 6.
8. Sau khi constructor hoàn tất, `child.summary()` quan sát `name=Lan, count=7`, in dòng số 7.

### 4.1. `final` không tự ngăn đọc giá trị mặc định lúc khởi tạo dở dang

`name` là `private final String` và Java compiler chấp nhận vì Child constructor gán nó đúng theo definite assignment khi hoàn tất bình thường. Tuy nhiên, **override `showState()` chạy sớm** và có thể quan sát `name=null` trước phép gán này.

Sự khác biệt rất quan trọng:

- **Definite assignment** buộc quá trình khởi tạo final field đi tới giá trị hợp lệ trước khi constructor hoàn tất bình thường.
- Nó **không bảo đảm** mọi virtual call giữa chừng khi xây dựng object đều chỉ quan sát giá trị sau cùng.
- Những bảo đảm của **Java Memory Model về final fields** cũng dựa vào điều kiện xây dựng object đúng, và không đồng nghĩa mọi hành vi trước khi constructor hoàn tất đều an toàn.

**Không “sửa” lỗi này chỉ bằng cách thêm `final` vào field của subclass.** Hãy sửa nơi gọi method hoặc hợp đồng vòng đời.

## 5. Biểu thức initializer trong subclass chưa chạy thì field vẫn mặc định

Một lỗi lý luận phổ biến:

~~~java
class Child extends Parent {
    private String label = "READY";

    @Override
    void printLabel() {
        System.out.println(label.length());
    }
}
~~~

Có người cho rằng `label` chắc chắn khác null vì **dòng khai báo đã ghi `= "READY"`**. Nhưng initializer của Child chạy **sau** khi constructor Parent kết thúc. Nếu Parent constructor gọi `printLabel()`, dynamic dispatch vào Child.printLabel có thể xảy ra trong khi `label == null`.

Điều đó có thể dẫn đến `NullPointerException`, chứ không chỉ in nhãn sai. Không nên dựa vào initializer ngay tại khai báo để bảo vệ overriding method bị gọi sớm.

### 5.1. Giá trị mặc định là cơ chế khởi tạo JVM, không phải “giá trị hợp lệ của nghiệp vụ”

Trong Java, object fields có default values trong quá trình khởi tạo. Nhưng class domain có thể quy định invariant mạnh hơn:

- `title` không null và không blank.
- `count` phải dương.
- `dependency` phải sẵn sàng.
- `items` phải là một danh sách đã tạo.
- `clock` phải được inject.
- `config` đã được validation.

Một virtual method sử dụng các invariant đó **trước khi subclass khởi tạo xong** có thể chạy trên state chưa hợp lệ dù Java vẫn cho phép lời gọi ở mức ngôn ngữ.

## 6. Chương trình chạy được: constructor thất bại vì override gọi trên field null

Tạo tệp **`ConstructorNpeDemo.java`**:

~~~java
import java.util.Objects;

public class ConstructorNpeDemo {
    static abstract class Component {
        Component() {
            printLength(); // Nguy hiểm: gọi abstract/overridable method
        }

        abstract void printLength();
    }

    static final class TextComponent extends Component {
        private final String text;

        TextComponent(String text) {
            this.text = Objects.requireNonNull(text, "text");
        }

        @Override
        void printLength() {
            System.out.println(text.length());
        }
    }

    public static void main(String[] args) {
        try {
            new TextComponent("Java");
        } catch (NullPointerException ex) {
            System.out.println("Caught NullPointerException");
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConstructorNpeDemo.java
java ConstructorNpeDemo
~~~

**Stdout chính xác:**

~~~text
Caught NullPointerException
~~~

### 6.1. Vì sao truyền `"Java"` mà vẫn ném NPE?

Caller truyền một String không null vào constructor TextComponent. Nhưng theo thứ tự khởi tạo:

1. Memory của TextComponent object được tạo, field `text` ban đầu có giá trị mặc định `null`.
2. Constructor của superclass `Component` chạy trước phần thân TextComponent constructor.
3. `Component()` gọi `printLength()`.
4. JVM dispatch tới `TextComponent.printLength()`, vì object runtime type là TextComponent.
5. Method override gọi `text.length()` khi `text` vẫn null → `NullPointerException`.
6. Exception thoát ra khỏi constructor superclass, nên **dòng `this.text = Objects.requireNonNull(...)` trong TextComponent constructor không được chạy**.
7. `new TextComponent("Java")` thất bại; caller bắt NPE và in một thông báo đã định.

**Ngay cả `final String text` cũng chưa giúp gì:** việc gán final ở constructor TextComponent chỉ xảy ra *sau* khi constructor Component hoàn tất bình thường. Vì Parent/Component constructor đã ném, tiến trình không tới bước gán.

### 6.2. Tại sao compiler không bắt lỗi này?

Compiler chấp nhận `TextComponent.printLength()` đọc field `text` vì đó là instance method thông thường; definite assignment của final field được kiểm tra theo constructor, chứ không thực hiện chứng minh toàn bộ **call graph và dynamic dispatch** rằng mọi method call trong lúc khởi tạo đều an toàn.

Một linter/static analysis có thể cảnh báo về “overridable method call in constructor”, nhưng chuẩn Java không biến mọi lời gọi dạng này thành lỗi biên dịch. Đây là lý do **code có thể compile nhưng thất bại ngay lúc `new`**.

## 7. Không chỉ gọi trực tiếp: constructor có thể đi qua method trung gian

Điều nguy hiểm không chỉ xuất hiện khi constructor viết thẳng `hook()`:

~~~java
class Base {
    Base() {
        prepare();
    }

    private void prepare() {
        // Private method này không bị subclass override,
        // nhưng nó gọi một method có thể override:
        validate();
    }

    void validate() {
    }
}

class Child extends Base {
    private String token = "ready";

    @Override
    void validate() {
        System.out.println(token);
    }
}
~~~

Đây là đoạn khai báo minh họa, chưa có `main`. `Base.prepare()` là **private** nên không bị override. Nhưng khi nó gọi `validate()`, lời gọi **vẫn có thể dispatch tới Child.validate()`**. Trong quá trình Base constructor chạy, `Child.token` vẫn null.

**Do đó, thay `hook()` bằng `privateHelper()` không tự đủ an toàn** nếu private helper lại gọi một overridable method sâu hơn. Cần rà soát **toàn bộ đường gọi có thể dẫn đến virtual dispatch** trong quá trình khởi tạo.

### 7.1. Lời gọi gián tiếp qua API phổ biến

Các tình huống thường bị bỏ sót:

- Constructor gọi một logger với `this` hoặc nối chuỗi khiến `toString()` của object được dùng.
- Constructor gọi `Objects.toString(this)`.
- Constructor đưa `this` vào collection, rồi collection/sort/comparator/callback truy cập method của object.
- Constructor đăng ký listener nhận `this` và listener được kích hoạt ngay.
- Constructor gọi một hook trong base class để “kiểm tra trạng thái subclass”.
- Constructor gọi một public method mà body bên trong gọi overridable protected method.
- Constructor bắt đầu một task/thread dùng `this` trước khi subclass fields được khởi tạo.

Không phải mọi API trên đều **luôn** gọi method override ở mọi trường hợp; rủi ro phụ thuộc call path và hành vi cụ thể. Điều chung là **constructor không nên đưa object chưa xây dựng hoàn chỉnh vào một đường thực thi có thể gọi hành vi đa hình dựa trên subclass state**.

## 8. `toString()`, `equals()` và `hashCode()` cũng là những methods có thể override

Ba methods quen thuộc của `Object` đều có thể được subclass override (theo quy tắc hợp lệ). Một superclass constructor viết:

~~~java
class Base {
    Base() {
        System.out.println(this);
    }
}
~~~

Lời gọi `println(Object)` cuối cùng cần biểu diễn object; trong con đường thông thường này, việc chuyển object thành chuỗi có thể gọi `toString()` của runtime subclass.

~~~java
class Named extends Base {
    private final String name;

    Named(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return "Named(" + name + ")";
    }
}
~~~

Nếu `new Named("Lan")`, dòng in từ Base constructor có thể là:

~~~text
Named(null)
~~~

vì `Named.toString()` chạy trước phép gán final field `name`. Ở đây không cần gọi `toString()` tường minh trong Base; việc in `this` đã tạo con đường gián tiếp.

**Hướng an toàn:** log các **constructor parameters** đã validate hoặc fields thuộc chính Base đã khởi tạo đúng, không dùng `this` như một object hoàn chỉnh để dump toàn bộ trạng thái subclass ngay trong superclass constructor.

Với `equals()` và `hashCode()`, rủi ro có thể xuất hiện nếu object chưa khởi tạo bị đưa vào hash-based structure hoặc một operation có sử dụng equality/hash behavior. Không coi việc đăng ký object vào Map/Set giữa constructor là vô hại.

## 9. `private`, `final` và `static` ảnh hưởng thế nào tới dispatch?

Không phải mọi lời gọi method trong constructor đều có cùng khả năng bị override.

| Method được gọi | Có thể bị subclass override như instance method không? | Điều cần chú ý |
| --- | --- | --- |
| `private void check()` khai báo trong Base | Không | Nhưng body vẫn có thể gọi virtual method khác |
| `final void check()` | Không | Body có thể gọi overridable hook khác |
| `static void check()` | Không thực hiện instance overriding; có thể bị hiding | Static không có `this` receiver |
| `void check()` package-private | Phụ thuộc quan hệ package/khả năng override | Không nên dựa vào package-private như một chiến lược an toàn tổng quát |
| `protected void check()` | Có, nếu subclass override hợp lệ | Rất thường dùng làm hook, nguy hiểm khi gọi lúc khởi tạo |
| `public void check()` | Có, nếu không final và có thể override | Client subclass có thể đổi behavior |
| `super.check()` trong instance method | Chọn superclass implementation theo cú pháp super | Không đồng nghĩa mọi nested call bên trong superclass implementation đều không dispatch |

**Quy tắc thực hành:** với công việc chỉ thuộc nội bộ constructor, ưu tiên logic **không thể bị override** (`private`/`final` thích hợp) và không gián tiếp gọi overridable methods.

### 9.1. `private` method an toàn về override trực tiếp

~~~java
class Parent {
    Parent() {
        checkOwnFields();
    }

    private void checkOwnFields() {
        // Chỉ đọc state Parent đã được khởi tạo hợp lệ.
    }
}
~~~

`checkOwnFields` không thể bị Child override để thay behavior của chính lời gọi này. Tuy vậy, nó chỉ an toàn nếu bản thân nó không chuyển điều khiển đến overridable methods/callbacks phụ thuộc subclass state.

### 9.2. `final` method ngăn overriding của chính method đó

~~~java
class Parent {
    Parent() {
        checkOwnFields();
    }

    final void checkOwnFields() {
        // Không thể bị subclass override.
    }
}
~~~

`final` hữu ích khi constructor cần một helper kế thừa được nhưng không muốn subclasses sửa logic. Một `final` method vẫn có thể gọi method ảo bên trong; kiểm tra sâu call graph trước khi kết luận an toàn.

### 9.3. Static method có thể giúp loại bỏ receiver ngầm định

~~~java
class Parent {
    private final String id;

    Parent(String id) {
        this.id = validate(id);
    }

    private static String validate(String candidate) {
        if (candidate == null || candidate.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        return candidate;
    }
}
~~~

`validate` nhận data tường minh và không có `this` của Parent để vô tình gọi overridable instance method. Cách viết này thường rõ ràng hơn khi validation chỉ phụ thuộc constructor arguments.

Nhưng static method **vẫn có thể làm việc với object tường minh**; nếu truyền chính `this` của object chưa hoàn tất vào static helper rồi helper gọi virtual methods, rủi ro vẫn tồn tại. `static` không phải lá chắn an toàn tự động.

## 10. Constructor chaining: `this(...)` không giải quyết việc gọi override quá sớm

Một subclass có thể có nhiều constructors:

~~~java
class Child extends Parent {
    private final String name;

    Child() {
        this("Anonymous");
    }

    Child(String name) {
        super();
        this.name = name;
    }
}
~~~

Theo Java 17, explicit constructor invocation `this(...)` hoặc `super(...)` phải là câu lệnh đầu tiên của constructor tương ứng khi được dùng. Việc `Child()` gọi `this("Anonymous")` không làm Child instance fields được gán trước khi superclass constructor chạy.

Chuỗi khái niệm:

~~~text
Child()
   |
   +--> this("Anonymous") -> Child(String)
                                |
                                +--> super() -> Parent()
                                |                |
                                |                +--> có thể gọi override trên Child
                                |                     name vẫn null
                                |
                                +--> Child fields/initializer và body gán name
~~~

Điều cần tránh là **virtual method call từ Parent constructor**. Không phải “thêm một constructor overload cho Child” là đã sửa được vòng đời.

### 10.1. Thứ tự đánh giá constructor arguments không cấp quyền dùng trạng thái subclass chưa có

Bạn có thể truyền constructor parameters đã biết vào `super(...)` theo quy tắc Java, nhưng không được giả định Child instance fields đã được khởi tạo trước super. Trong Java 17, cú pháp explicit constructor invocation còn có các hạn chế về `this` và những instance members chưa thể được tham chiếu theo cách thông thường trước superclass initialization.

Nên chuyển dữ liệu cần cho superclass thành **constructor parameters**, rồi để superclass validate/gán field của nó thay vì gọi hook của subclass để hỏi “hãy tự cung cấp dữ liệu của em ngay bây giờ”.

## 11. Thiết kế an toàn nhất: hoàn tất construction rồi mới gọi hành vi đa hình

Nếu một method thực sự cần state của subclass, hãy gọi nó **sau khi `new Child(...)` hoàn tất thành công**.

~~~java
Child child = new Child(...);
child.start();
~~~

Khi caller chủ động gọi `start()` trên object đã hoàn tất constructor, `Child` fields, instance initializers và constructor body đã có cơ hội thiết lập invariant đầy đủ.

**Tuy nhiên, lời gọi tách sau constructor không tự bảo đảm an toàn tuyệt đối:** code trong `start()` vẫn cần validation và concurrency protocol thích hợp; cần kiểm soát việc gọi nhiều lần hoặc gọi sai thứ tự theo API.

### 11.1. Không yêu cầu subclass phải tự gọi init từ constructor nếu init dùng polymorphism

Một phương án dễ nhầm là bảo subclasses gọi `initialize()` ở cuối mỗi subclass constructor:

~~~java
class Child extends Parent {
    Child() {
        // superclass đã hoàn tất
        initialize(); // Có thể dispatch tới subclass sâu hơn!
    }
}
~~~

Nếu `Child` **chưa final** và một `GrandChild extends Child` override `initialize()`, thì khi Child constructor đang chạy, GrandChild fields vẫn chưa khởi tạo. Rủi ro **được dời xuống một cấp**, chứ chưa bị loại bỏ.

Muốn một hook đa hình chỉ chạy sau khi **toàn bộ runtime object** đã hoàn tất xây dựng, hãy đưa lời gọi ra **ngoài constructor chain** hoặc dùng một cơ chế factory/lifecycle có kiểm soát đúng.

### 11.2. Có thể dùng static factory khi kiểm soát constructor

~~~java
final class Worker {
    private final String name;

    private Worker(String name) {
        this.name = name;
    }

    static Worker create(String name) {
        Worker worker = new Worker(name);
        worker.onReady();
        return worker;
    }

    private void onReady() {
        System.out.println(name);
    }
}
~~~

Đây là minh họa một factory cho **final class**: factory tạo object hoàn chỉnh rồi gọi `onReady`. `Worker` final, nên không có subclass thêm fields cần khởi tạo sau constructor Worker. Trong thiết kế có inheritance, một factory muốn gọi polymorphic hook phải bảo đảm thực sự đã xây dựng xong **concrete runtime subclass** trước khi gọi hook.

## 12. Chương trình chạy được: khởi tạo an toàn và template method sau constructor

Tạo tệp **`SafeConstructionDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class SafeConstructionDemo {
    static abstract class Component {
        private final String id;

        protected Component(String id) {
            this.id = Objects.requireNonNull(id, "id");
            // Không gọi render(), renderContent() hay hook nào.
        }

        public final void render() {
            System.out.println("Component " + id);
            renderContent();
        }

        protected abstract void renderContent();
    }

    static final class TextComponent extends Component {
        private final String content;

        TextComponent(String id, String content) {
            super(id);
            this.content = Objects.requireNonNull(content, "content");
        }

        @Override
        protected void renderContent() {
            System.out.println(
                    "Content " + content.toUpperCase(Locale.ROOT));
        }
    }

    public static void main(String[] args) {
        TextComponent text =
                new TextComponent("T-1", "Java");

        System.out.println("Construction complete");
        text.render();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 SafeConstructionDemo.java
java SafeConstructionDemo
~~~

**Stdout chính xác:**

~~~text
Construction complete
Component T-1
Content JAVA
~~~

### 12.1. Vì sao thiết kế này an toàn hơn?

- `Component` constructor chỉ validate/gán `id` của nó. Không gọi `renderContent`.
- `TextComponent` constructor chỉ bắt đầu sau khi `Component` constructor hoàn tất; nó validate/gán `content` của subclass.
- `new TextComponent(...)` hoàn tất bình thường rồi biến `text` nhận tham chiếu.
- Caller in `Construction complete`, sau đó gọi `text.render()`. Lúc này `content` đã non-null nếu object xây dựng thành công.
- `render()` là **final** để subclasses không bỏ qua orchestration của Component; nó gọi **abstract hook** `renderContent()`, nhưng chỉ khi caller yêu cầu sau construction.
- `renderContent()` dispatch đến implementation TextComponent và dùng String đã khởi tạo.

Đây là ví dụ tốt về **template method pattern**: superclass có thể định nghĩa một luồng xử lý ổn định và subclass cung cấp bước tùy biến, nhưng **không khởi động bước tùy biến trong constructor**.

**Cần làm rõ contract:** nếu một API khác gọi `render()` trong giai đoạn khởi tạo thông qua `this` thoát ra ngoài, vấn đề vẫn có thể tái xuất hiện. Kiểm soát thời điểm public method được gọi là phần của lifecycle design.

## 13. Nếu superclass thật sự cần dữ liệu subclass lúc khởi tạo, hãy truyền input qua `super(...)`

Một superclass constructor đôi khi cần một giá trị mà subclass biết. Cách không an toàn là **gọi overridable method**:

~~~java
abstract class Base {
    final String label;

    Base() {
        label = createLabel(); // Nguy hiểm: abstract hook!
    }

    abstract String createLabel();
}
~~~

Subclass có thể cần những fields chưa sẵn sàng để tạo label. Thay vào đó, biến yêu cầu thành **constructor parameter**:

~~~java
abstract class Base {
    private final String label;

    protected Base(String label) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("Label trống");
        }
        this.label = label;
    }

    public final String label() {
        return label;
    }
}

final class NamedChild extends Base {
    private final int version;

    NamedChild(String code, int version) {
        super("Child-" + code);
        this.version = version;
    }
}
~~~

Đây là khai báo minh họa. `NamedChild` có thể tính biểu thức từ **constructor parameters** trước khi gọi `super(...)`, không cần dùng fields của chính Child chưa khởi tạo.

### 13.1. Dùng static helper để tính super-argument

Nếu validation/cấu trúc tính toán phức tạp:

~~~java
class Base {
    final String token;

    Base(String token) {
        this.token = java.util.Objects.requireNonNull(token);
    }
}

final class Child extends Base {
    Child(String raw) {
        super(normalize(raw));
    }

    private static String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("raw trống");
        }
        return raw.trim();
    }
}
~~~

`normalize(raw)` là static helper, chỉ xử lý parameter, không truy cập `this`. Đây là cách bảo đảm superclass nhận dữ liệu hợp lệ mà không cần gọi vào virtual subclass behavior trong constructor.

**Đừng dùng `super(this.someValue())` hoặc một instance method của object chưa khởi tạo** để tính superclass argument trong Java 17; ngữ cảnh constructor invocation bị giới hạn và thiết kế ấy đi ngược mục tiêu tránh sử dụng subclass state quá sớm.

## 14. Cẩn thận với ba cấp kế thừa: gọi ở giữa vẫn có thể dispatch xuống dưới

Không chỉ superclass gốc mới có vấn đề. Với chuỗi:

~~~text
GrandParent
    ^
    |
  Parent
    ^
    |
  Child
~~~

Nếu **Parent constructor** gọi overridable method, runtime object vẫn có thể là **Child**, và override của Child có thể chạy trước khi **Child-specific initialization** hoàn tất.

Ví dụ:

~~~java
class Root {
    Root() {
    }
}

class Middle extends Root {
    Middle() {
        onReady();
    }

    void onReady() {
        System.out.println("Middle");
    }
}

class Leaf extends Middle {
    private String ready = "YES";

    @Override
    void onReady() {
        System.out.println("Leaf ready = " + ready);
    }
}
~~~

Nếu tạo `new Leaf()` thì `Middle()` gọi `onReady()` trước field initializer `Leaf.ready`; kết quả có thể là:

~~~text
Leaf ready = null
~~~

Điều quan trọng: ngay cả khi `Middle` constructor bắt đầu **sau** `Root` constructor, thì `Leaf` vẫn chưa hoàn tất. Vì vậy **constructor của bất cứ class nào trong inheritance chain** cũng không nên mặc định rằng mọi runtime subclass state đã sẵn sàng.

### 14.1. Gọi ở cuối constructor của class trung gian vẫn chưa an toàn

Bạn có thể viết:

~~~java
Middle() {
    initializeMiddle();
    onReady(); // Cuối Middle constructor, nhưng trước Leaf initialization
}
~~~

Việc đưa hook xuống cuối Middle constructor không đổi sự thật rằng Leaf initialization chạy **sau** Middle constructor. Nếu ý định là thông báo “toàn bộ runtime object sẵn sàng”, **constructor trung gian không có đủ thông tin để bảo đảm thời điểm ấy** với subclasses tương lai.

## 15. Vì sao `final class` có thể giảm rủi ro nhưng không phải lời giải cho mọi thứ?

Nếu class khai báo **`final`**, nó không thể có subclasses hợp lệ, nên constructor của chính class ấy không thể bất ngờ dispatch vào override của một lớp con chưa khởi tạo.

~~~java
final class FinalCounter {
    private int count;

    FinalCounter() {
        reset();
    }

    void reset() {
        count = 0;
    }
}
~~~

Trong ví dụ này không có subclass của FinalCounter để override `reset()`. Lời gọi từ constructor không đối mặt với **rủi ro polymorphic subclass dispatch** vừa phân tích.

Tuy vậy, vẫn cần xem:

- `reset()` có làm lộ `this` qua callback hay registry không?
- Nó có dựa trên một field khác chưa khởi tạo không?
- Nó có gọi external code ném exception hoặc tạo side effect không?
- Nó có dùng resource chưa sẵn sàng không?
- Class final có thực sự phù hợp nhu cầu extension của API không?

**Không tự động biến mọi class thành final chỉ để “sửa” một constructor đang gọi method không phù hợp.** Nếu thư viện cần cho subclassing, hãy sửa lifecycle và khai báo rõ hooks.

### 15.1. `final method` cũng chỉ giải quyết trực tiếp overriding

Một method `final void check()` không bị subclass override. Nhưng nếu `check()` gọi `hook()` không final, virtual dispatch vẫn có thể xuất hiện gián tiếp. Rà soát toàn bộ call graph trước khi kết luận an toàn.

## 16. `private` method của superclass khác với subclass method cùng tên

Subclass có thể khai báo method cùng tên với private method của superclass, nhưng đó **không phải override** của private superclass method theo cơ chế bình thường:

~~~java
class Base {
    Base() {
        helper();
    }

    private void helper() {
        System.out.println("Base private");
    }
}

class Child extends Base {
    void helper() {
        System.out.println("Child helper");
    }
}
~~~

Nếu `new Child()`, lời gọi `helper()` từ Base constructor chạy **Base.private helper**, chứ không dispatch tới Child.helper. Private superclass method không được kế thừa làm overridable method.

Nhưng nhắc lại: nếu Base.private helper **tiếp tục gọi một overridable method khác**, nguy cơ vẫn xuất hiện. Không dùng từ khóa `private` như một cách che giấu call path không an toàn.

## 17. Vòng đời object và việc phát tán `this` trước khi khởi tạo xong

Gọi virtual method sớm là một biểu hiện của vấn đề lớn hơn: **để object đang khởi tạo bị code bên ngoài hoặc callback nhìn thấy quá sớm** (*this escape*).

~~~java
class EventSource {
    private static java.util.function.Consumer<Object> observer;

    static void setObserver(
            java.util.function.Consumer<Object> next) {
        observer = next;
    }

    static void publish(Object event) {
        if (observer != null) {
            observer.accept(event);
        }
    }
}

class Dangerous {
    private final String id;

    Dangerous(String id) {
        EventSource.publish(this); // Có thể gọi callback với object chưa sẵn sàng!
        this.id = id;
    }

    String id() {
        return id;
    }
}
~~~

Đây là **khai báo minh họa**, không có `main`. Nếu observer gọi `event.toString()`, cast rồi gọi `id()` hoặc khởi động một thread khác sử dụng object, nó có thể quan sát state chưa hoàn tất.

Một số hình thức `this` escape cần tránh từ constructor:

- Đưa `this` vào static collection/registry.
- Đăng ký listener với callback có thể được kích hoạt ngay.
- Gửi `this` tới event bus.
- Bắt đầu một thread/task nắm tham chiếu `this`.
- Truyền `this` vào external code không kiểm soát.
- Gọi overridable method mà subclass có thể công bố `this`.

### 17.1. `final field` và safe publication là vấn đề liên quan nhưng khác nhau

Java Memory Model có những bảo đảm đặc biệt cho final fields khi object được xây dựng đúng cách. Nhưng **nếu `this` escape trước khi constructor hoàn tất**, những giả định về trạng thái hoàn chỉnh có thể bị phá vỡ. Final field không phải bảo hiểm cho mọi đường đọc sớm.

Một hướng tốt hơn: constructor tạo object và thiết lập invariant, sau đó caller/factory **đăng ký object đã hoàn tất** qua một protocol an toàn.

~~~java
Dangerous item = new Dangerous("A");
// Chỉ sau khi constructor đã hoàn tất thành công:
// registry.register(item);
~~~

Đây là fragment mô tả cách sử dụng; cần một API `registry` tương ứng trong ứng dụng. Nếu có nhiều thread, việc **safe publication** vẫn cần tuân thủ concurrency protocol (synchronized/volatile/concurrent data structure hoặc cơ chế phù hợp), chứ không chỉ dựa trên thứ tự hai dòng code trong cùng thread.

## 18. Thứ tự khởi tạo và constructor đối với abstract classes

Một abstract class vẫn có constructor; constructor được chạy khi khởi tạo concrete subclass. **Abstract method có thể được gọi từ abstract superclass constructor**, và invocation sẽ dispatch tới implementation subclass.

~~~java
abstract class AbstractProcessor {
    AbstractProcessor() {
        process(); // Nguy hiểm
    }

    abstract void process();
}

final class ConcreteProcessor extends AbstractProcessor {
    private final String data;

    ConcreteProcessor(String data) {
        this.data = data;
    }

    @Override
    void process() {
        System.out.println("Data length = " + data.length());
    }
}
~~~

Đây là khai báo minh họa. `new ConcreteProcessor("abc")` có thể ném NPE trong `process()` trước khi Child constructor gán `data`.

**Một thiết kế nguy hiểm không trở nên an toàn chỉ vì hook đã khai báo `abstract`.** Trái lại, abstract method *bắt buộc* có subclass implementation, mà superclass constructor không thể biết implementation ấy cần state nào.

Với abstract base class, dùng **constructor parameters** cho state cần ở giai đoạn khởi tạo; dành abstract/protected hooks cho phase sau khi object được tạo.

## 19. Lời gọi method nào từ constructor có thể được xem là an toàn hơn?

Nói “không bao giờ gọi bất kỳ method nào trong constructor” là quá cực đoan. Java cho phép constructor gọi method, và nhiều lời gọi hợp lệ, hữu ích. Cần phân biệt theo **khả năng override và phụ thuộc state**.

### 19.1. Static validation helper xử lý chỉ parameter

~~~java
class UserId {
    private final String value;

    UserId(String raw) {
        this.value = normalize(raw);
    }

    private static String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        return raw.trim();
    }
}
~~~

Helper không cần `this`; nó không đọc subclass fields. Đó là mô hình dễ suy luận, dù logic validation vẫn phải đúng contract.

### 19.2. Private helper chỉ truy cập state base đã sẵn sàng

~~~java
class Base {
    private final int capacity;

    Base(int capacity) {
        this.capacity = capacity;
        validateOwnState();
    }

    private void validateOwnState() {
        if (capacity < 0) {
            throw new IllegalArgumentException("Capacity âm");
        }
    }
}
~~~

`validateOwnState()` không bị subclass override. Nó chỉ đọc field `capacity` mà Base đã gán trước đó. Cách này tránh được **early polymorphic callback** trực tiếp.

Tuy nhiên, có thể validate parameter **trước** khi gán state nếu hợp đồng yêu cầu. Cần xem trường hợp method gọi external code hoặc tự làm lộ `this`.

### 19.3. Final helper kiểm soát invariant được kế thừa

~~~java
class Base {
    Base() {
        establishBaseState();
    }

    final void establishBaseState() {
        // Không được override; không gọi hook ảo.
    }
}
~~~

Đây là pattern có thể phù hợp với một API kế thừa có kiểm soát. Nhưng với internal implementation detail, `private` thường thể hiện chủ đích che giấu rõ hơn. Không nhất thiết mọi final helper phải là public/protected.

## 20. Chương trình chạy được: lời gọi gián tiếp từ constructor vẫn dispatch

Tạo tệp **`IndirectDispatchDemo.java`**:

~~~java
public class IndirectDispatchDemo {
    static class Base {
        Base() {
            log();
        }

        private void log() {
            System.out.println("Base logging");
            System.out.println(describe());
        }

        String describe() {
            return "Base description";
        }
    }

    static final class Child extends Base {
        private String label = "READY";

        @Override
        String describe() {
            return "label=" + label;
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        System.out.println("After = " + child.describe());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 IndirectDispatchDemo.java
java IndirectDispatchDemo
~~~

**Stdout chính xác:**

~~~text
Base logging
label=null
After = label=READY
~~~

**Phân tích:**

1. Base constructor gọi `private void log()`; chính method này không bị override.
2. `log()` gọi `describe()`, một instance method overridable của Base.
3. Runtime object là Child nên lời gọi dispatch tới `Child.describe()`.
4. Field initializer `label = "READY"` của Child chưa chạy, nên lời gọi đầu tiên nhận `label=null`.
5. Sau khi Base constructor kết thúc, Child initializer chạy; lời gọi `child.describe()` từ `main` nhận `label=READY`.

Ví dụ này cho thấy **chỉ nhìn dòng đầu của constructor không đủ**. Một private helper tưởng an toàn có thể ẩn một con đường gọi overridable hook.

## 21. Không nhầm `super.method()` với virtual call trên một receiver tùy ý

Trong subclass instance method:

~~~java
class Base {
    void describe() {
        System.out.println("Base");
    }
}

class Child extends Base {
    @Override
    void describe() {
        super.describe();
        System.out.println("Child");
    }
}
~~~

`super.describe()` chọn superclass implementation thích hợp, không phải một new Base object. Nhưng nếu superclass implementation tiếp tục gọi **một virtual method khác**, lời gọi đó vẫn có thể dispatch xuống runtime subclass.

Ví dụ:

~~~java
class Base {
    void describe() {
        hook(); // Virtual call
    }

    void hook() {
    }
}

class Child extends Base {
    @Override
    void describe() {
        super.describe();
    }

    @Override
    void hook() {
        // Có thể được gọi qua super.describe() -> hook()
    }
}
~~~

Đây là khai báo minh họa. Vì thế `super.describe()` không có nghĩa “mọi lời gọi bên trong method Base đều bị ép thành Base implementation”.

Trong constructor superclass, lời gọi `super(...)` có ý nghĩa **constructor invocation** theo ngữ cảnh khởi tạo; không nên đánh đồng với `super.method()` trong method thường.

## 22. Hạn chế ở API của superclass: đừng yêu cầu subclass sẵn sàng quá sớm

Một superclass thiết kế để mở rộng thường có **protected hook**:

~~~java
abstract class Plugin {
    protected abstract void configure();
}
~~~

Nếu superclass constructor gọi `configure()`, mọi concrete subclass bị buộc chạy hook trước khi constructor của nó hoàn tất. Đây là một contract khó sử dụng an toàn.

API nên thay bằng:

- **Constructor parameters** cho dữ liệu cần để tạo invariant base.
- **Factory hoặc builder** tạo đối tượng hoàn chỉnh.
- **Explicit lifecycle method** `start()`, `initialize()` hoặc `open()` được gọi sau construction.
- **Final template method** điều phối các protected hooks khi object đã sẵn sàng.
- **Composition/injection** khi nhu cầu chỉ là thay strategy, không cần kế thừa.
- **Immutable configuration object** được validate trước khi truyền vào constructor.

### 22.1. Lifecycle có hai trạng thái cần tài liệu hóa

Nếu API dùng `start()`:

~~~text
CREATED -- start() --> STARTED -- close() --> CLOSED
~~~

thì cần quy định:

- Gọi method trước `start()` có được phép không?
- `start()` có được gọi nhiều lần không?
- Khi `start()` thất bại thì object còn hợp lệ ở trạng thái nào?
- Có được gọi `close()` trước `start()` không?
- Khi có nhiều thread, trạng thái được bảo vệ bằng cách nào?

Tách initialization phase khỏi constructor giải quyết thời điểm **subclass chưa xây dựng xong**, nhưng lifecycle phải được thiết kế như một hợp đồng thật, không chỉ chuyển lỗi từ constructor sang một method không có quy tắc.

### 22.2. Không gọi virtual hook từ superclass field initializer

Rủi ro tương tự xảy ra với **instance field initializer hoặc instance initializer block của superclass**:

~~~java
class Base {
    final String description = describe(); // Có thể gọi override quá sớm

    String describe() {
        return "Base";
    }
}
~~~

Nếu object thực tế thuộc Child override `describe()` để đọc Child fields, lời gọi từ initializer Base có thể chạy trước Child initialization. **Tránh gọi overridable instance methods trong toàn bộ đường superclass initialization, không riêng constructor body.**

## 23. Kiểm tra thứ tự bằng debugger mà không biến default values thành invariant

Khi gặp bug “field chắc chắn đã khởi tạo, sao vẫn null?”, cách điều tra hữu ích:

1. Đặt breakpoint ở constructor của superclass.
2. Đặt breakpoint ở method có thể override tại superclass và subclass.
3. Đặt breakpoint ở instance field initializer (hoặc helper được initializer gọi) của subclass.
4. Đặt breakpoint ở constructor body của subclass.
5. Quan sát **call stack**, runtime type của `this` và giá trị field ở từng thời điểm.

Một call stack đại ý:

~~~text
Child.describe()
Base.<init>()
Child.<init>()
Main.main()
~~~

Đây là sơ đồ khái niệm tên frames; debugger/JVM có thể hiển thị một số frames/thao tác compiler khác nhau. Điểm then chốt là **subclass override đang chạy bên trong chuỗi superclass constructor**.

### 23.1. Những gì phải xác minh

- Lời gọi đến override **trực tiếp hay qua private/public helper**?
- Có field initializer `= ...` nhưng chưa thực hiện không?
- Object là runtime subclass nào?
- Một subclass khác sâu hơn có override method không?
- Có xử lý log/toString/callback nhận `this` không?
- Đã gọi method sau khi `new` hoàn tất chưa?
- Có một thread khác quan sát object chưa hoàn tất vì early publication không?

**Đừng chỉ thêm một null-check để xóa NPE mà bỏ qua nguyên nhân lifecycle.** Một override có thể sống sót qua `null` nhưng vẫn sinh dữ liệu sai hoặc side effect trước thời điểm hợp lệ.

## 24. Các cách sửa thường gặp: từ vá triệu chứng đến sửa contract

| Cách xử lý | Có giải quyết gốc rễ không? | Bình luận |
| --- | --- | --- |
| Thêm `if (field == null) return;` trong override | Thường **chưa** | Chặn NPE nhưng có thể bỏ qua việc quan trọng; invariant vẫn chưa có |
| Gán field initializer ở dòng khai báo | **Không đủ** | Initializer subclass vẫn chạy sau superclass constructor |
| Đánh dấu field `final` | **Không đủ** | Blank final vẫn có default value trước assignment; final không sửa timing |
| Đưa hook xuống cuối superclass constructor | **Không đủ** | Subclass constructor vẫn chưa chạy |
| Chuyển superclass call qua `private` helper có gọi hook | **Không** | Call graph cuối vẫn có virtual dispatch |
| Đổi helper trực tiếp thành `private`/`final`, không gọi hooks khác | **Có thể** | Hợp lý nếu chỉ thao tác base state đã sẵn sàng |
| Truyền data cho superclass qua `super(args)` | **Thường có** | Loại nhu cầu query subclass state quá sớm |
| Gọi polymorphic operation sau `new` hoàn tất | **Thường có** | Phải thiết kế lifecycle, exceptions, concurrency |
| Dùng final concrete class khi không cần inheritance | **Có thể** | Loại subclass override path, nhưng còn initialization/escape issues |
| Tách dependency thành interface được inject | **Thường hữu ích** | Kiểm soát extension bằng composition thay vì override constructor-time |

Chọn cách sửa dựa trên **trách nhiệm dữ liệu**:

- Superclass cần dữ liệu để validate/khởi tạo chính nó → constructor arguments.
- Subclass cần làm việc sau khi state của nó sẵn sàng → explicit post-construction operation.
- Superclass cần nội bộ tự kiểm tra → non-overridable helper trên state đã được khởi tạo.
- Hệ thống muốn báo sự kiện object mới sẵn sàng → publish **sau construction**, không từ constructor.

## 25. Tình huống với dependency injection và framework

Các framework có lifecycle callbacks, proxying hoặc dependency injection có thể tác động cách một object được tạo/sử dụng. Nhưng ngữ nghĩa Java cơ bản không đổi:

- Constructor của superclass chạy trước subclass instance initialization thích hợp.
- Overridable instance method có thể dispatch theo runtime subclass.
- Không thể giả định dependency/field do subclass hoặc framework thiết lập ở phase sau đã sẵn sàng trong superclass constructor.
- Không nên gọi overridable business methods từ constructor chỉ vì framework bình thường inject dependencies “sớm”.
- Cần xem tài liệu framework về constructor injection, field injection, post-construction callbacks, proxies và lifecycle.

Ví dụ, nếu dependency được framework gán qua setter/field **sau khi object tạo xong**, thì một constructor gọi method dựa trên dependency đó còn nguy hiểm hơn: field chưa có giá trị ứng dụng. Constructor injection có thể giúp cung cấp dependency khi xây dựng đúng class, nhưng **superclass constructor vẫn không được dựa trên fields subclass chưa gán**.

Nếu sử dụng `@PostConstruct` hoặc callback tương tự trong một môi trường hỗ trợ, cần phân biệt **phase của framework** với Java constructor, và không tự giả định các callbacks đó bảo đảm an toàn đồng thời hoặc chỉ chạy đúng một lần trong mọi công cụ.

## 26. `record`, `final class` và lựa chọn tránh inheritance-driven initialization hazard

Trong Java 17, record classes **implicitly final**. Một record không được subclass như class thông thường:

~~~java
record PersonName(String given, String family) {
    PersonName {
        if (given == null || family == null) {
            throw new IllegalArgumentException("Tên null");
        }
    }

    String fullName() {
        return given + " " + family;
    }
}
~~~

Không có user-defined subclass của record `PersonName` để override `fullName()`. Điều đó loại đi một nhóm lỗi liên quan **superclass constructor gọi override của subclass** trên chính record type.

Tuy nhiên:

- Record constructor vẫn cần validate đúng invariants.
- Record components có thể là mutable references; record không tự deep-freeze.
- Không nên để `this` escape trong constructor.
- Record constructor/canonical/compact constructor có những quy tắc riêng; không suy luận tất cả mechanics như class inheritance thông thường.

Khi dữ liệu là **value object** không cần inheritance, record hoặc final class có thể phù hợp. Khi cần polymorphic behavior, hãy mở rộng bằng interface/composition hoặc abstract class với lifecycle an toàn.

## 27. Những nhầm lẫn phổ biến

1. **“Constructor Parent đang chạy nên `Parent.method()` chắc chắn được gọi.”** Sai đối với overridable instance method: runtime object có thể là Child nên dynamic dispatch chọn override.
2. **“Object chỉ có runtime type Child sau khi Child constructor chạy xong.”** Sai. Object được tạo với runtime type Child ngay từ đầu quá trình khởi tạo.
3. **“Field `String label = "READY"` không bao giờ null.”** Sai trong giai đoạn trước subclass field initializer.
4. **“Field `final` không thể mang default value giữa chừng.”** Sai. Constructor-time virtual call có thể quan sát state chưa gán.
5. **“Compiler sẽ cấm mọi method ảo trong constructor.”** Sai. Nhiều trường hợp biên dịch được nhưng có bug runtime.
6. **“Chỉ constructor trực tiếp gọi hook mới nguy hiểm.”** Sai. Private helper, logging, `toString()` và callbacks có thể dẫn tới hook gián tiếp.
7. **“Chuyển lời gọi xuống dòng cuối superclass constructor là an toàn.”** Sai. Subclass initializers/constructor vẫn chưa chạy.
8. **“Dùng `this(...)` để chain constructor sẽ gán Child fields trước Parent.”** Sai. Chuỗi vẫn tuân thủ superclass-first instance initialization.
9. **“Subclass constructor tự gọi hook ở cuối là luôn đủ.”** Sai nếu còn subclass sâu hơn có override; cần xem toàn bộ runtime class.
10. **“Một private method luôn làm mọi lời gọi bên dưới non-virtual.”** Sai. Body của nó vẫn có thể gọi virtual method.
11. **“Static method có dynamic dispatch giống instance method.”** Sai. Static method không có instance override như virtual method.
12. **“`super.method()` khóa mọi method con mà implementation đó gọi.”** Sai. Bên trong superclass method, virtual calls khác vẫn dispatch bình thường.
13. **“Catch NPE trong constructor là đã khởi tạo đầy đủ object.”** Sai. NPE có thể chấm dứt construction; không nên dùng object nửa vời.
14. **“Null-check trong override là sửa xong mọi bug.”** Sai. Có thể chỉ giấu lỗi state chưa sẵn sàng hoặc bỏ qua hành động.
15. **“Nếu dùng `final class` thì mọi constructor đều an toàn.”** Sai. Không còn subclass override nhưng vẫn có side effects, this escape, field ordering, concurrency và validation.
16. **“Đăng ký listener trong constructor không sao vì caller chưa thấy object.”** Sai. Listener/callback có thể nhìn thấy `this` trước khi caller nhận tham chiếu.
17. **“Java Memory Model cho final fields nên this escape không vấn đề.”** Sai. An toàn khởi tạo có điều kiện; không nên publish trước constructor hoàn tất.
18. **“Mọi method trong constructor đều cấm.”** Sai. Helper không overridable, thuần tham số hoặc chỉ xử lý base state đã sẵn sàng có thể hợp lệ.

## 28. Bài tập tự kiểm tra có đáp án

**Câu 1.** `Base()` gọi `show()`, `Child extends Base` override `show()`. Trong `new Child()` implementation nào có thể chạy?

**Đáp án:** `Child.show()` theo dynamic dispatch của overridable instance method, dù constructor Base đang chạy.

**Câu 2.** `Child` có `private String text = "Java";`, và `Base()` gọi `show()` override đọc text. Vì sao text có thể là null?

**Đáp án:** Instance field initializer của Child chạy sau khi superclass constructor hoàn tất; trước đó field reference có default value null.

**Câu 3.** Nếu `text` là `final String` và được gán trong `Child(...)`, compiler có bảo đảm override không đọc null khi Base constructor gọi sớm không?

**Đáp án:** Không. Definite assignment bảo đảm constructor hoàn tất bình thường có gán field, nhưng không bảo đảm mọi virtual method call giữa chừng chỉ quan sát final value.

**Câu 4.** Nếu override gọi `text.length()` lúc text null, chuyện gì xảy ra?

**Đáp án:** Có thể ném `NullPointerException`, khiến construction dừng bất thường trước khi Child constructor gán field.

**Câu 5.** Nếu Base constructor gọi private `prepare()`, `prepare()` gọi overridable `hook()`, có an toàn hơn chỉ vì `prepare` private không?

**Đáp án:** Không. `hook()` vẫn có thể dispatch tới subclass override trước khi state Child sẵn sàng.

**Câu 6.** `Base()` in `System.out.println(this)` có thể gọi subclass `toString()` không?

**Đáp án:** Có. Chuyển object thành chuỗi thường sử dụng runtime `toString()`, có thể truy cập subclass state chưa khởi tạo.

**Câu 7.** Đổi `Child.field` sang static có phải cách sửa phù hợp không?

**Đáp án:** Thường không. Điều đó đổi quyền sở hữu state sang class; phải sửa timing/lifecycle hoặc truyền constructor parameters phù hợp thay vì thay modifier bừa.

**Câu 8.** Gọi một `private` method của Base từ Base constructor có nguy cơ override trực tiếp không?

**Đáp án:** Private method không bị subclass override trực tiếp. Nhưng body của nó phải tránh indirect virtual dispatch, callback và dùng state chưa sẵn sàng.

**Câu 9.** `final void validate()` ở Base có thể bị Child override không?

**Đáp án:** Không. Nhưng nếu method final gọi một overridable method khác thì rủi ro vẫn có thể xảy ra.

**Câu 10.** Nếu `Child` là `final class`, còn có một subclass `GrandChild extends Child` để hook của Child constructor dispatch xuống không?

**Đáp án:** Không; final class ngăn kế thừa. Tuy nhiên, không vì thế được bỏ qua những vấn đề initialization/lifecycle khác.

**Câu 11.** Cách nào thích hợp khi superclass cần tên do caller cung cấp: hỏi subclass qua overridable `getName()` trong superclass constructor hay truyền `name` vào `super(name)`?

**Đáp án:** Truyền constructor parameter `name` tới `super(name)`. Superclass có thể validate/gán state trực tiếp mà không phụ thuộc subclass chưa sẵn sàng.

**Câu 12.** Nếu một method override cần dependency được Child constructor inject, gọi method đó lúc nào an toàn hơn?

**Đáp án:** Sau khi `new Child(...)` hoàn tất thành công, thông qua operation/lifecycle có hợp đồng rõ và bảo đảm dependency sẵn sàng.

**Câu 13.** Gọi overridable hook ở cuối constructor của một class trung gian có bảo đảm mọi subclass sâu hơn đã khởi tạo không?

**Đáp án:** Không. Các constructors/initializers của subclass sâu hơn vẫn chưa chạy.

**Câu 14.** `this` trong constructor Base đang tạo Child object là object loại nào?

**Đáp án:** Nó tham chiếu tới object runtime type Child đang được xây dựng, không phải một Parent/Base object riêng.

**Câu 15.** Việc Java cho phép method override chạy sớm có phải Java tự chọn Parent implementation trước rồi mới đổi sang Child không?

**Đáp án:** Không. Dynamic dispatch dựa trên runtime class; Child implementation có thể được chọn ngay, chỉ có **state đang thay đổi theo thứ tự khởi tạo**.

**Câu 16.** Một final method có thể gọi abstract hook không?

**Đáp án:** Có; final chỉ ngăn override chính method ấy. Nếu final method được gọi trong constructor và gọi abstract hook, rủi ro early dispatch vẫn tồn tại.

**Câu 17.** Đưa `this` vào registry từ constructor trước khi gán final fields có nguy hiểm không?

**Đáp án:** Có. Object có thể được quan sát trước khi được xây dựng hoàn chỉnh; Java Memory Model final-field guarantees không phải bảo đảm vô điều kiện trong tình huống this escape.

**Câu 18.** Vì sao gọi `render()` sau `new TextComponent(...)` tốt hơn gọi trong `Component()`?

**Đáp án:** Khi caller gọi sau construction, TextComponent field initializers và constructor body đã chạy thành công; override có thể dựa vào state đã được thiết lập.

## 29. Checklist khi thiết kế hoặc review constructor có inheritance

1. **Superclass constructor có gọi instance method nào không?** Nếu có, method ấy có thể override không?
2. **Có call path gián tiếp không?** Rà soát private helpers, logger, formatter, `toString()`, event bus và callbacks.
3. **Có superclass field initializer hoặc instance initializer gọi hook không?** Nó có cùng vấn đề timing.
4. **Runtime subclass state đã sẵn sàng chưa?** Trong superclass constructor, thường **chưa**.
5. **Có những subclass sâu hơn không?** Hook gọi ở cuối constructor class trung gian vẫn có thể dispatch xuống object chưa hoàn tất.
6. **Có đọc blank final field của subclass không?** Nó có thể còn default value trong lúc gọi sớm.
7. **Có non-final field initializer `= ...` trong Child không?** Nó chưa chạy trước superclass constructor.
8. **Có method nào dereference String/List/dependency chưa khởi tạo không?** Xem nguy cơ NPE.
9. **Có side effect khi hook chạy sớm không?** Side effect có thể tồn tại dù construction thất bại.
10. **Có làm `this` escape không?** Không đăng ký observer, thread, registry hoặc callback trước khi xây dựng xong.
11. **Superclass cần dữ liệu gì ngay?** Ưu tiên constructor parameters và helpers không phụ thuộc subclass instance state.
12. **Subclass cần thực hiện hành vi gì sau khi tạo?** Tách thành post-construction method/lifecycle.
13. **Method điều phối có nên final không?** Final template method hữu ích nếu cần bảo vệ protocol; chỉ gọi hooks sau construction.
14. **Có thể dùng final concrete class/record/composition không?** Chỉ khi phù hợp API và yêu cầu extension.
15. **Có framework lifecycle riêng không?** Xem chính xác thời điểm injection/proxy/callback.
16. **Có thread concurrency không?** Phân biệt constructor completion, safe publication và synchronization cho mutable state.
17. **Ví dụ/tệp có chạy đúng với Java 17 không?** Kiểm tra tên public class, package, compile commands, stdout và chú thích dòng cố tình sai.
18. **Khi sửa lỗi, đã loại bỏ early polymorphic call thực sự chưa?** Đừng chỉ che bằng null-check hoặc chuyển field thành static/final.

## 30. Kết luận

Khi constructor của superclass chạy trong quá trình `new Subclass()`, **object có runtime type Subclass ngay từ đầu**, nên **overridable instance method calls vẫn có thể dispatch vào implementation của subclass**. Nhưng instance field initializers và constructor body của subclass **chưa hoàn tất**, nên override có thể nhìn thấy `null`, `0`, `false` hoặc dependencies chưa sẵn sàng. `final` field và initializer ngay tại dòng khai báo không tự xóa được vấn đề này.

Cách thiết kế bền vững là **không gọi overridable methods từ constructors hoặc từ những initializer chạy trước subclass initialization**; cũng tránh đường gọi gián tiếp và việc công bố `this` quá sớm. Hãy **truyền dữ liệu cần thiết qua constructors**, kiểm tra state trong helper không thể override khi phù hợp, và dành polymorphic hooks cho **phương thức/lifecycle được gọi sau khi object đã khởi tạo thành công**. Đây là cách để giữ được sức mạnh kế thừa và dynamic dispatch mà không đánh đổi tính đúng đắn của quá trình tạo object.
