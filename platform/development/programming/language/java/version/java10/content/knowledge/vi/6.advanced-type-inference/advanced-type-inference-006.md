# Quan hệ giữa kiểu suy luận và khả năng truy cập thành viên trong Java (Java 10+)

## 1. Mục tiêu: `var` thay đổi cách viết khai báo, không thay đổi luật truy cập thành viên

Với Java 10 trở lên, `var` cho phép trình biên dịch **suy ra kiểu tĩnh của một biến cục bộ** từ biểu thức khởi tạo. Kiểu tĩnh đó quyết định những **field, phương thức và thành viên** nào mà mã Java được phép truy cập tại thời điểm biên dịch.

Ví dụ dễ thấy:

~~~java
var text = "Java 10";        // Kiểu suy ra: String
System.out.println(text.length()); // Hợp lệ vì String có length()

Object broad = "Java 10";    // Kiểu tĩnh: Object
// broad.length();           // Lỗi biên dịch: Object không khai báo length()
~~~

Cả `text` và `broad` đều có thể trỏ tới một đối tượng `String`, nhưng **kiểu tĩnh của hai biến khác nhau**. Với `var`, trình biên dịch sử dụng kiểu của **biểu thức bên phải**; với `Object`, lập trình viên chủ động khai báo kiểu rộng.

Bài học giúp bạn:
- Phân biệt **kiểu được suy luận**, **kiểu tĩnh đã khai báo** và **lớp đối tượng thực tế lúc chạy**.
- Hiểu vì sao `var` có thể giúp gọi thêm phương thức khi initializer có kiểu cụ thể, nhưng không thể vượt qua các quy tắc truy cập của Java.
- Giải thích cách **interface/lớp cha**, factory method, ép kiểu, generic và phương thức overload ảnh hưởng đến khả năng gọi thành viên.
- Nắm sự khác nhau giữa **kiểm tra lời gọi theo kiểu tĩnh** và **chọn phương thức override theo kiểu runtime**.
- Nhận biết trường hợp đặc biệt: `var` có thể giữ kiểu của **anonymous class** và cho phép dùng thành viên chỉ có ở lớp vô danh đó.

Các ví dụ chạy độc lập trong bài dùng JDK 17 trở lên. Những quy tắc này vẫn hữu ích trong Java hiện đại; không cần tính năng preview.

## 2. Nguyên tắc nền tảng: kiểu tĩnh quyết định thành viên có thể gọi

Trong Java, một biểu thức có **kiểu tĩnh** tại thời điểm biên dịch. Khi viết `reference.method()` hoặc `reference.field`, trình biên dịch thực hiện kiểm tra theo kiểu tĩnh của `reference`:

1. Kiểu đó có thành viên cần gọi không (trực tiếp hoặc kế thừa)?
2. Thành viên có thể truy cập ở vị trí hiện tại không, theo `public`, `protected`, package-private hay `private`?
3. Đối số và kiểu trả về có tương thích theo quy tắc của Java không?
4. Nếu là phương thức overload, chữ ký nào áp dụng tại compile time?

Chỉ sau khi lời gọi hợp lệ, với **phương thức instance có thể override**, Java mới dùng cơ chế *dynamic dispatch* để chạy phần triển khai phù hợp với lớp thực tế của đối tượng. Sự lựa chọn runtime này **không biến một phương thức không có trong kiểu tĩnh trở thành hợp lệ**.

Hãy nhớ: `var` không có nghĩa là “biến này luôn biết tất cả phương thức của đối tượng runtime”. Nó chỉ giúp trình biên dịch viết hộ kiểu tĩnh từ initializer.

## 3. Dùng `var` với constructor cụ thể: giữ được API của lớp cụ thể

Giả sử có lớp `Dog` thực thi interface `Pet`:

~~~java
interface Pet {
    String sound();
}

class Dog implements Pet {
    @Override
    public String sound() {
        return "woof";
    }

    public String fetch() {
        return "ball";
    }
}
~~~

*Đây là phần định nghĩa kiểu minh họa, chưa phải một tệp có `main` độc lập. Mục 8 có chương trình hoàn chỉnh.*

So sánh:

~~~java
var dog = new Dog();  // Kiểu tĩnh được suy ra là Dog
Pet pet = new Dog();  // Kiểu tĩnh được khai báo là Pet

dog.sound();          // Hợp lệ: Dog có sound()
dog.fetch();          // Hợp lệ: Dog có fetch()
pet.sound();          // Hợp lệ: Pet khai báo sound()
// pet.fetch();       // Lỗi biên dịch: Pet không khai báo fetch()
~~~

Biến `pet` vẫn trỏ đến đối tượng `Dog`, nhưng **không thể gọi `fetch()` qua kiểu tĩnh `Pet`**. Muốn gọi thành viên riêng của `Dog`, cần một tham chiếu có kiểu tĩnh thích hợp hoặc thu hẹp kiểu an toàn.

`var dog = new Dog();` cũng khác với `Pet dog = new Dog();` về mặt thiết kế: cách thứ hai thể hiện một **hợp đồng interface**, giúp mã phụ thuộc ít hơn vào lớp triển khai.

## 4. `var` suy ra kiểu biểu thức, không suy ra lớp đối tượng thực tế

Kết quả suy luận phụ thuộc vào **kiểu trả về đã khai báo** của phương thức, kiểu của biến nguồn hoặc kiểu của biểu thức ép kiểu.

Ví dụ (giả sử đã có `Pet`, `Dog` như trên):

~~~java
static Pet createPet() {
    return new Dog();
}

// Bên trong một phương thức:
var fromFactory = createPet(); // Kiểu suy ra: Pet
// fromFactory.fetch();        // Lỗi: Pet không có fetch()

Pet interfaceRef = new Dog();
var copied = interfaceRef;     // Kiểu suy ra: Pet
// copied.fetch();             // Cũng lỗi: kiểu nguồn là Pet

var direct = new Dog();        // Kiểu suy ra: Dog
direct.fetch();                // Hợp lệ

var widened = (Pet) new Dog(); // Kiểu suy ra: Pet
// widened.fetch();            // Lỗi
~~~

**Mấu chốt:** Dù `createPet()` luôn trả về `new Dog()` trong ví dụ, chữ ký `static Pet createPet()` quy định biểu thức gọi có kiểu `Pet`. Trình biên dịch không mở thân phương thức rồi dùng lớp runtime để suy kiểu biến `fromFactory`.

Những hệ quả thường gặp:
- API trả về `List<String>` thì `var items = api.getItems();` có kiểu tĩnh `List<String>`, dù implementation có thể là `ArrayList<String>`.
- Biến nguồn khai báo `Object` thì `var next = source;` suy ra `Object`, bất kể `source` đang chứa `String`.
- Ép kiểu ở initializer có thể làm kiểu được suy ra rộng hơn: `var value = (CharSequence) "Java";` suy ra `CharSequence`, cho phép `length()` nhưng không gọi trực tiếp `toUpperCase()` của `String`.

`var` không lưu “kiểu gốc” của đối tượng trước khi bị nhìn qua interface, lớp cha hoặc phép ép kiểu. Kiểu suy ra chỉ là kiểu của **biểu thức khởi tạo** được Java xác định.

## 5. Runtime polymorphism không thay thế kiểm tra kiểu tĩnh

Khi interface hoặc lớp cha khai báo một phương thức, một lớp con có thể **override** phương thức đó. Biến kiểu interface/lớp cha vẫn gọi được phương thức chung, và Java thực thi bản override ở runtime.

~~~java
Pet pet = new Dog();
System.out.println(pet.sound()); // woof, gọi implementation của Dog

// pet.fetch(); // Lỗi biên dịch: Pet không khai báo fetch()
~~~

Việc `sound()` chạy bản của `Dog` không có nghĩa biến `pet` có kiểu tĩnh `Dog`. **Điều kiện được phép gọi** và **phần triển khai được chạy** là hai quyết định khác nhau.

Nếu muốn truy cập chức năng riêng của `Dog`, Java 17+ hỗ trợ pattern matching với `instanceof`:

~~~java
Pet pet = new Dog();
if (pet instanceof Dog dog) {
    System.out.println(dog.fetch()); // ball
}
~~~

Biến `dog` trong nhánh `if` có kiểu tĩnh `Dog`, nhờ đó `fetch()` hợp lệ. Biến `pet` bên ngoài **vẫn** là `Pet` và không tự đổi kiểu. Cách này đặc biệt hữu ích khi thực sự cần xử lý hành vi riêng của một implementation, nhưng không nên lạm dụng nếu có thể khai báo hành vi chung ở interface.

**Đừng ép kiểu mù quáng**:

~~~java
// Dog dog = (Dog) somePet; // Có thể ném ClassCastException nếu đối tượng không là Dog
~~~

Pattern matching `instanceof` kiểm tra trước khi sử dụng; việc chọn phép ép kiểu phải dựa trên điều kiện thực tế, không dựa vào `var`.

## 6. Field và phương thức: truy cập khác nhau khi dùng lớp cha

Thành viên có cùng tên ở lớp cha và lớp con có thể tạo ra hai cơ chế khác nhau:
- **Phương thức instance được override**: Java chọn implementation theo lớp runtime sau khi xác định lời gọi hợp lệ.
- **Field bị che khuất (field hiding)**: việc tham chiếu tên field được quyết định theo **kiểu tĩnh của biểu thức bên trái dấu chấm**, không theo lớp runtime.

Tạo tệp **VarMemberResolutionDemo.java**:

~~~java
public class VarMemberResolutionDemo {
    static class Parent {
        String label = "parent";

        String say() {
            return "parent method";
        }
    }

    static class Child extends Parent {
        String label = "child";

        @Override
        String say() {
            return "child method";
        }

        String onlyChild() {
            return "child only";
        }
    }

    public static void main(String[] args) {
        var concrete = new Child(); // Kiểu tĩnh Child
        Parent view = concrete;     // Kiểu tĩnh Parent
        var inferred = view;        // Kiểu suy ra Parent

        System.out.println("concrete label = " + concrete.label);
        System.out.println("view label = " + view.label);
        System.out.println("inferred label = " + inferred.label);
        System.out.println("view say = " + view.say());
        System.out.println("inferred say = " + inferred.say());
        System.out.println("concrete extra = " + concrete.onlyChild());

        // inferred.onlyChild(); // Lỗi biên dịch: Parent không có onlyChild()
    }
}
~~~

Chạy:

~~~bash
javac VarMemberResolutionDemo.java
java VarMemberResolutionDemo
~~~

**Đầu ra chính xác:**

~~~text
concrete label = child
view label = parent
inferred label = parent
view say = child method
inferred say = child method
concrete extra = child only
~~~

Ở ví dụ này:
1. `concrete` có kiểu tĩnh `Child`, nên nhìn thấy `Child.label` và `onlyChild()`.
2. `view` có kiểu tĩnh `Parent`, nên `view.label` lấy field `Parent.label` ngay cả khi đối tượng thực tế là `Child`.
3. `inferred` được khai báo bằng `var` nhưng initializer là `view` có kiểu `Parent`; do đó `inferred.label` cũng lấy field của `Parent`.
4. `view.say()` và `inferred.say()` đều chạy bản override của `Child`, vì lời gọi `say()` đã hợp lệ theo `Parent`.

**Gợi ý thiết kế:** không dựa vào field hiding để biểu diễn đa hình. Nếu muốn một hành vi thay đổi theo implementation, định nghĩa một phương thức chung có thể override sẽ rõ ràng hơn.

## 7. Generic và kiểu phần tử cũng quyết định thành viên được gọi

`var` giữ kiểu generic của biểu thức khởi tạo khi đủ thông tin. Vì vậy khả năng gọi phương thức trên phần tử collection phụ thuộc vào generic **đã suy ra**, không chỉ vào lớp runtime của từng phần tử.

~~~java
var words = new java.util.ArrayList<String>();
words.add("Java");
System.out.println(words.get(0).length()); // 4
~~~

Kiểu suy ra của `words` là `ArrayList<String>`; `words.get(0)` có kiểu tĩnh `String`, nên `length()` hợp lệ.

So sánh:

~~~java
var values = new java.util.ArrayList<>();
values.add("Java");
values.add(10);

// values.get(0).length(); // Lỗi biên dịch: get(0) có kiểu Object
Object first = values.get(0);
System.out.println(first.getClass().getSimpleName()); // String
~~~

Trong trường hợp `new ArrayList<>()` không có target type và không có dữ liệu constructor, diamond suy luận `Object`; `var values` được suy ra `ArrayList<Object>`. Lệnh `add("Java")` sau khai báo **không làm trình biên dịch suy lại `String`**.

Muốn danh sách có phần tử `String`, có thể viết:

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
var directNames = new java.util.ArrayList<String>();
var copiedNames = new java.util.ArrayList<>(
        java.util.List.of("An", "Binh"));
~~~

- `names`: kiểu tĩnh `List<String>`, vì vế trái cho biết generic và interface mong muốn.
- `directNames`: kiểu tĩnh `ArrayList<String>`, vì constructor ghi rõ `String`.
- `copiedNames`: kiểu tĩnh `ArrayList<String>` vì constructor lấy đối số `List<String>`.

Cả ba đều cho phép gọi các phương thức của `String` trên phần tử lấy ra bằng `get`. Nhưng `names` chỉ thấy các phương thức được định nghĩa ở interface `List`, còn biến có kiểu `ArrayList` có thể gọi thêm các phương thức riêng của implementation.

**Khái quát:** suy luận sai generic có thể làm **mất khả năng truy cập API trên phần tử** ngay tại compile time. Không nên dùng `Object` hoặc ép kiểu tràn lan để che đi việc thiếu thông tin generic ở initializer.

## 8. Chương trình đầy đủ: `var`, interface, factory, overload và anonymous class

Tạo tệp **InferredMemberAccessDemo.java**:

~~~java
import java.util.ArrayList;

public class InferredMemberAccessDemo {
    interface Speaker {
        String speak();
    }

    static final class Dog implements Speaker {
        @Override
        public String speak() {
            return "woof";
        }

        String fetch() {
            return "ball";
        }
    }

    static Speaker createSpeaker() {
        return new Dog();
    }

    static String describe(String value) {
        return "String";
    }

    static String describe(Object value) {
        return "Object";
    }

    public static void main(String[] args) {
        var concrete = new Dog();
        Speaker speaker = concrete;
        var fromSpeaker = speaker;
        var fromFactory = createSpeaker();

        System.out.println("concrete speak = " + concrete.speak());
        System.out.println("concrete fetch = " + concrete.fetch());
        System.out.println("interface speak = " + fromSpeaker.speak());
        System.out.println("factory speak = " + fromFactory.speak());

        var typed = new ArrayList<String>();
        typed.add("Java");
        System.out.println("typed length = " + typed.get(0).length());

        var broad = new ArrayList<>();
        broad.add("Java");
        Object first = broad.get(0);
        System.out.println("broad runtime = "
                + first.getClass().getSimpleName());

        var text = "Java";
        Object asObject = text;
        System.out.println("overload inferred = " + describe(text));
        System.out.println("overload Object = " + describe(asObject));

        var anonymous = new Object() {
            String label() {
                return "local";
            }
        };
        System.out.println("anonymous label = " + anonymous.label());

        if (fromFactory instanceof Dog dog) {
            System.out.println("narrowed fetch = " + dog.fetch());
        }

        // fromFactory.fetch(); // Không hợp lệ: kiểu tĩnh Speaker
        // fromSpeaker.fetch(); // Không hợp lệ: kiểu tĩnh Speaker
        // broad.get(0).length(); // Không hợp lệ: kiểu phần tử Object
        // asObject.length(); // Không hợp lệ: kiểu tĩnh Object
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac InferredMemberAccessDemo.java
java InferredMemberAccessDemo
~~~

**Đầu ra chính xác:**

~~~text
concrete speak = woof
concrete fetch = ball
interface speak = woof
factory speak = woof
typed length = 4
broad runtime = String
overload inferred = String
overload Object = Object
anonymous label = local
narrowed fetch = ball
~~~

Những điều chương trình chứng minh:
1. `concrete` suy ra kiểu `Dog`, nên gọi được `fetch()`. Hai biến `fromSpeaker` và `fromFactory` suy ra `Speaker`, nên chỉ gọi được các phương thức phù hợp với interface.
2. `typed` giữ generic `String` nên `get(0).length()` hợp lệ; `broad` giữ generic `Object` nên không thể gọi trực tiếp `length()` trên kết quả `get(0)`.
3. Hai overload `describe(String)` và `describe(Object)` được chọn dựa trên **kiểu tĩnh của biểu thức đối số**, dù `text` và `asObject` đều cùng tham chiếu tới một chuỗi.
4. `anonymous` được suy ra kiểu lớp vô danh tạo bởi biểu thức `new Object() { ... }`, nên lời gọi `anonymous.label()` hợp lệ trong phạm vi đó.
5. `instanceof Dog dog` tạo biến pattern có kiểu `Dog` sau kiểm tra, nên gọi `fetch()` hợp lệ. Nó không đổi kiểu tĩnh `Speaker` của biến `fromFactory`.

## 9. Khi có overload, kiểu tĩnh được suy ra tác động ngay đến lời gọi

Overloading là nhiều phương thức cùng tên nhưng có danh sách tham số khác nhau. Trình biên dịch chọn overload phù hợp dựa trên **kiểu tĩnh của đối số** và các quy tắc lựa chọn phương thức.

~~~java
static String choose(String value) { return "String"; }
static String choose(Object value) { return "Object"; }

// Bên trong một phương thức:
var text = "hello";       // String
Object broad = text;      // Object
var inferredBroad = broad; // Object

System.out.println(choose(text));          // String
System.out.println(choose(broad));         // Object
System.out.println(choose(inferredBroad)); // Object
~~~

Đây là đoạn minh họa cần đặt các phương thức `choose` trong cùng lớp và các lệnh `println` trong một phương thức; chương trình đầy đủ ở mục 8 đã thể hiện cơ chế tương tự.

Đừng nhầm với **overriding**: overload được phân giải phần lớn lúc biên dịch; phương thức instance đã được chọn theo chữ ký có thể chạy bản override ở runtime. `var` không đổi những quy tắc sẵn có ấy, nhưng ảnh hưởng đến **kiểu tĩnh mà compiler nhìn thấy**, từ đó ảnh hưởng tới overload khả dụng.

## 10. Anonymous class: trường hợp đặc biệt của khả năng truy cập thành viên

Khi khởi tạo một **anonymous class**, kiểu của biểu thức `new ... { ... }` là kiểu lớp vô danh cụ thể, dù lớp đó không có tên để bạn viết vào khai báo biến theo cách thông thường.

~~~java
var helper = new Object() {
    int answer() {
        return 42;
    }
};

System.out.println(helper.answer()); // 42
~~~

Trong Java 10+, `var` cho biến cục bộ có thể giữ **kiểu được suy ra của anonymous class**, nhờ đó trình biên dịch biết phương thức `answer()` trong phạm vi biến `helper`. Đây là một ví dụ rõ ràng cho thấy **kiểu suy ra có thể cụ thể hơn một kiểu tường minh mà lập trình viên thường chọn**.

So sánh:

~~~java
Object widened = new Object() {
    int answer() {
        return 42;
    }
};

// widened.answer(); // Lỗi: Object không khai báo answer()
~~~

Biến `widened` có kiểu tĩnh `Object`. Dù đối tượng runtime là anonymous class có `answer()`, không thể gọi `answer()` thông qua `Object`.

**Giới hạn cần nhớ:**
- Thành viên vẫn phải tuân thủ quy tắc truy cập và phạm vi của Java.
- Nếu trả đối tượng qua một phương thức có kiểu trả về `Object` hoặc interface, biến `var` ở nơi nhận suy ra kiểu trả về **đã khai báo** và không tự giữ API riêng của anonymous class.
- Không nên cố tình tạo nhiều phương thức chỉ có ở anonymous class để xây dựng API dài hạn. Khi cần hợp đồng tái sử dụng, định nghĩa interface hoặc lớp có tên phù hợp.

## 11. Access modifier vẫn luôn được kiểm tra

`var` chỉ suy luận kiểu, **không nâng quyền truy cập**. Nếu kiểu suy ra là một lớp cụ thể, các thành viên `private` của lớp ấy vẫn không được truy cập từ một lớp bên ngoài không có quyền; `protected` và package-private vẫn tuân thủ quy tắc Java tương ứng.

Ví dụ minh họa bằng hai tệp cùng thư mục nhưng là hai lớp top-level riêng biệt.

**SecretBox.java**:

~~~java
public class SecretBox {
    private String secret = "hidden";

    public String reveal() {
        return secret;
    }
}
~~~

**SecretBoxDemo.java**:

~~~java
public class SecretBoxDemo {
    public static void main(String[] args) {
        var box = new SecretBox();
        System.out.println(box.reveal()); // hidden

        // System.out.println(box.secret);
        // Lỗi nếu bỏ comment: secret là private của SecretBox
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SecretBox.java SecretBoxDemo.java
java SecretBoxDemo
~~~

Đầu ra:

~~~text
hidden
~~~

Ví dụ này minh họa rằng **có kiểu tĩnh `SecretBox` không đồng nghĩa nhìn thấy mọi thành viên**. Quy tắc accessibility là một bước kiểm tra khác bên cạnh quy tắc thành viên tồn tại trong kiểu.

## 12. Các lỗi thường gặp

| Nhận định hoặc đoạn code | Vấn đề | Cách hiểu / cách sửa |
| --- | --- | --- |
| `var pet = createPet(); pet.fetch();` trong khi `createPet(): Pet` | Kiểu suy ra là `Pet`, không có `fetch()` | Dùng API chung ở `Pet`; chỉ thu hẹp kiểu khi thực sự cần |
| `var list = new ArrayList<>(); list.get(0).length();` | Kiểu phần tử suy ra là `Object` | Nêu rõ `String` ở generic hoặc có nguồn dữ liệu mang kiểu |
| `Object text = "abc"; text.length();` | `Object` không khai báo `length()` | Khai báo `String` khi có hợp đồng chuỗi, hoặc kiểm tra `instanceof String` |
| `var x = (CharSequence) "abc"; x.toUpperCase();` | Kiểu tĩnh `CharSequence` không có `toUpperCase()` | Gọi API của `CharSequence` hoặc dùng `String` khi phù hợp |
| Cho rằng `var` bỏ qua `private` | Quy tắc truy cập vẫn được kiểm tra | Dùng API `public` hoặc thiết kế giao diện truy cập thích hợp |
| Cho rằng phương thức override có thể được gọi dù không khai báo ở interface | Dynamic dispatch chỉ diễn ra sau khi lời gọi hợp lệ | Khai báo hành vi chung ở interface hoặc thu hẹp kiểu an toàn |
| Mong `var` chọn overload theo đối tượng runtime | Overload dựa trên kiểu tĩnh khi biên dịch | Kiểm tra kiểu của biểu thức đối số; chọn kiểu phù hợp với mục tiêu |
| Cho rằng khai báo `var` luôn cho phép nhiều API hơn | Nếu initializer có kiểu interface, `var` vẫn suy ra interface | Xem chữ ký trả về hoặc kiểu nguồn, không chỉ tên lớp runtime |

Các lệnh gây lỗi ở đây là **mã minh họa hoặc lệnh không hợp lệ có chủ đích**, không phải chương trình hoàn chỉnh. Kiểm thử ví dụ chạy ở mục 8 và 11 bằng lệnh `javac`/`java` đã nêu.

## 13. Nên chọn `var` hay kiểu tường minh?

| Tình huống | Cách viết thường phù hợp | Lý do |
| --- | --- | --- |
| Biến cục bộ, initializer rõ ràng là lớp cụ thể và cần API cụ thể | `var dog = new Dog();` | Giữ `Dog` mà tránh lặp tên kiểu |
| Muốn giới hạn code ở hợp đồng interface | `Pet pet = new Dog();` | Người đọc thấy ngay mức trừu tượng dự kiến |
| Factory method trả về interface và chỉ dùng API chung | `var pet = createPet();` hoặc `Pet pet = createPet();` | Cả hai có kiểu tĩnh `Pet`; chọn cách dễ hiểu hơn |
| Tạo collection rỗng có kiểu phần tử chính xác | `List<String> names = new ArrayList<>();` | Kiểu đích giúp generic được suy ra rõ ràng |
| Cần dùng API riêng của anonymous class trong phạm vi hẹp | `var local = new Object() { ... };` | `var` giữ kiểu anonymous class |
| Lời gọi overload nhạy với kiểu tham số | Cân nhắc kiểu tường minh hoặc cast có chủ đích | Giúp hành vi được chọn ở compile time dễ đọc và kiểm soát |

Một nguyên tắc tốt: **đừng chọn `var` chỉ để tiết kiệm ký tự**. Nếu cần truyền đạt hợp đồng trừu tượng hoặc đảm bảo khả năng gọi thành viên theo API mong muốn, hãy xem xét kiểu tường minh. `var` phát huy giá trị khi initializer bộc lộ kiểu rõ ràng và không gây bất ngờ cho người đọc.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Cho `var value = "Java";`. Tại sao `value.length()` hợp lệ?

**Trả lời:** Biểu thức khởi tạo có kiểu `String`, nên `value` được suy ra kiểu tĩnh `String`; phương thức `length()` được khai báo ở kiểu này.

**Câu 2.** `var pet = createPet();`, trong đó `createPet()` khai báo trả `Pet` nhưng bên trong tạo `Dog`. Có gọi trực tiếp `pet.fetch()` không?

**Trả lời:** Không, nếu `fetch()` chỉ thuộc `Dog`. Kiểu suy ra từ chữ ký hàm là `Pet`; lớp runtime không mở rộng API hợp lệ cho biến.

**Câu 3.** `var numbers = new ArrayList<Integer>();` so với `var numbers = new ArrayList<>();` khác gì về `numbers.get(0).intValue()`?

**Trả lời:** Ở khai báo thứ nhất, kết quả `get(0)` có kiểu tĩnh `Integer`, có `intValue()`. Ở khai báo thứ hai, kiểu phần tử suy ra `Object`, nên không gọi trực tiếp `intValue()` được.

**Câu 4.** Cùng là một `Child`, tại sao biến kiểu `Parent` có thể gọi bản override của `Child.say()` nhưng không gọi được `Child.onlyChild()`?

**Trả lời:** `Parent` khai báo `say()` nên lời gọi hợp lệ; bản override được chọn theo runtime. `Parent` không khai báo `onlyChild()`, nên lời gọi bị từ chối ngay ở compile time.

**Câu 5.** Vì sao `var anonymous = new Object() { int code() { return 7; } };` gọi được `anonymous.code()`?

**Trả lời:** `var` có thể suy ra kiểu lớp vô danh cụ thể của initializer. Kiểu ấy khai báo `code()`, nên lời gọi trong phạm vi biến hợp lệ. Nếu biến chỉ được khai báo kiểu `Object`, `code()` không nằm trong API khả dụng.

**Câu 6.** `var box = new SecretBox();` có giúp một lớp bên ngoài đọc trực tiếp `box.secret` khi field là `private` không?

**Trả lời:** Không. Kiểu suy ra chỉ xác định kiểu tĩnh; quyền truy cập `private` vẫn được Java kiểm tra đầy đủ.

**Câu 7.** Cho `var text = "Java"; Object obj = text;`, overload `describe(String)` và `describe(Object)` được chọn thế nào?

**Trả lời:** `describe(text)` chọn overload `String`; `describe(obj)` chọn overload `Object`. Lựa chọn dựa vào kiểu tĩnh của biểu thức đối số, không phải lớp runtime.

## 15. Ghi nhớ cốt lõi

1. `var` **suy ra kiểu tĩnh từ initializer**; nó không làm thay đổi luật truy cập thành viên.
2. **Kiểu tĩnh** quyết định thành viên được phép gọi, **access modifier** quyết định thành viên ấy có thể được truy cập tại vị trí đang viết code không.
3. **Kiểu runtime** chỉ có thể quyết định bản override của một lời gọi instance hợp lệ, không tạo ra phương thức mới trong interface/lớp cha.
4. Constructor cụ thể thường giúp `var` giữ API cụ thể; biến nguồn hoặc factory trả interface khiến `var` suy ra interface.
5. Generic được suy luận ảnh hưởng trực tiếp đến kiểu phần tử và phương thức có thể gọi trên phần tử; dùng `Object` khi thiếu thông tin kiểu có thể làm API bị thu hẹp.
6. `var` với anonymous class là trường hợp hữu ích trong phạm vi cục bộ, nhưng không thay thế thiết kế một interface có tên khi cần API lâu dài.

**Tài liệu tham khảo còn áp dụng:**
- [Java Language Specification 17, §14.4 — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4).
- [JLS 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12).
- [JLS 17, §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6).
- [OpenJDK — Local Variable Type Inference Style Guidelines](https://openjdk.org/projects/amber/guides/lvti-style-guide).
