# Bắt giữ biến final và effectively final trong lớp vô danh Java

> **Ngữ cảnh:** Java Core → Class/Object → Lớp vô danh (*anonymous classes*).  
> **Áp dụng:** Java 17+; nguyên tắc capture cũng liên quan local classes và lambda, nhưng trọng tâm của bài là **anonymous class**.

## 1. Điều cốt lõi cần hiểu

Một **anonymous class** có thể dùng các local variables và parameters thuộc phạm vi bao quanh ngay trong phần thân class. Khi một local variable hoặc parameter được tham chiếu từ anonymous class, biến đó phải **`final` hoặc *effectively final*** theo quy tắc ngôn ngữ Java.

- **`final` tường minh:** variable được khai báo với modifier `final`, không thể được gán lại ngoài những trường hợp initial assignment hợp lệ.
- **Effectively final:** không có modifier `final`, nhưng theo cách variable được gán trong source code, nó đáp ứng những điều kiện tương đương về việc không bị thay đổi sau khi khởi tạo/definite assignment phù hợp.
- **Capture:** anonymous-class object có thể giữ và sử dụng **giá trị của variable** ở enclosing scope, ngay cả khi method tạo object đã trả về.
- **Kiểu primitive:** captured value là primitive value như `int` hay `boolean`.
- **Kiểu tham chiếu:** captured value là **reference** trỏ đến object, không phải bản deep copy của object.
- **`final` / effectively final không làm mutable object bất biến.** Có thể gọi `list.add(...)`, `builder.append(...)` hay sửa array element dù reference variable được capture không thể bị gán lại.

Ví dụ hợp lệ:

~~~java
void demo() {
    int prefix = 7;
    StringBuilder text = new StringBuilder("A");

    Runnable action = new Runnable() {
        @Override
        public void run() {
            System.out.println(prefix + ":" + text);
        }
    };

    text.append("B"); // Sửa object, không gán lại biến text.
    action.run();      // In: 7:AB
}
~~~

Đây là **method fragment**, không phải standalone Java file. `prefix` và `text` không bị gán lại nên đều *effectively final*. Nhưng mutable StringBuilder object mà `text` trỏ tới vẫn được thay đổi.

Nếu thêm dòng `text = new StringBuilder("C");` vào method, capture sẽ không hợp lệ; compiler báo lỗi vì `text` không còn effectively final, kể cả phép gán xảy ra **sau** khi khai báo anonymous class.

**Chốt lại:** Quy tắc capture ràng buộc **giá trị biến cục bộ**, không tự ràng buộc **trạng thái đối tượng được biến tham chiếu**. Đây là nền tảng để hiểu closures, callbacks, listeners và asynchronous tasks trong Java.

## 2. Anonymous class là gì và được tạo thế nào?

Anonymous class là một class **không có tên khai báo ở source code**, được định nghĩa và khởi tạo ngay trong một **class instance creation expression**. Nó thường được dùng để:

1. Triển khai nhanh một interface.
2. Kế thừa một class và override methods.
3. Tạo một callback/handler ngắn có state hoặc logic riêng.
4. Kết hợp behaviors được đóng gói ngay tại chỗ với dữ liệu từ lexical scope.

Ví dụ:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("Hello");
    }
};
~~~

`new Runnable() { ... }` tạo instance của một **anonymous class implements Runnable**, không phải trực tiếp tạo instance của interface Runnable. Variable `task` có declared type Runnable; runtime object là instance của class vô danh do compiler tạo.

### 2.1. Anonymous class có thể extends class

~~~java
abstract class Message {
    abstract String content();
}

Message message = new Message() {
    @Override
    String content() {
        return "ready";
    }
};
~~~

Đây là declaration fragment. Anonymous class có thể kế thừa một concrete/abstract superclass hoặc implement một interface tương ứng với syntax `new SomeType(...) { ... }`. Nó không đồng thời có source-level `extends A implements B` list riêng giống named-class declaration; base type nằm ở construction expression.

### 2.2. Anonymous class không có source-level simple name

Bạn không viết `new AnonymousClassName()` từ một nơi khác, và không trực tiếp viết constructor đặt tên cho anonymous class như với named class. Instance initialization có thể được viết bằng instance initializer block hoặc field initializers, và call chain dùng constructor của base class khi là superclass phù hợp.

### 2.3. So với local class

Một **local class** có tên khai báo trong một block:

~~~java
class Task implements Runnable {
    public void run() {
        System.out.println("Hello");
    }
}
Runnable task = new Task();
~~~

Anonymous class rút khai báo và tạo object vào một expression. Cả local và anonymous inner classes đều dùng quy tắc capture local variables/parameters final hoặc effectively final, nhưng anonymous class không có tên local để khởi tạo một object thứ hai bằng `new Task()`.

## 3. Local variable, field và parameter là ba loại khác nhau

Chúng đều có thể xuất hiện trong anonymous-class code, nhưng **quy tắc effectively final chỉ gắn với local variables/parameters được capture**:

| Dữ liệu được dùng | Quy tắc khi anonymous class tham chiếu | Có thể thay đổi theo thời gian? |
| --- | --- | --- |
| Local primitive `int count` | Phải final/effectively final | Không reassign được nếu capture |
| Local reference `List<String> list` | Reference variable phải final/effectively final | Referent List có thể mutable |
| Method parameter `String label` | Parameter phải final/effectively final | Không reassign parameter nếu capture |
| Enclosing instance field `this.count` | Không áp dụng effectively final như với local | Có thể thay nếu field mutable |
| Static field `Config.mode` | Không phải captured local variable | Có thể thay theo field semantics |
| Anonymous-class instance field `this.calls` | Thuộc anonymous object | Có thể thay nếu field mutable |
| Captured immutable value `String` | Reference variable final/effectively final | Nội dung String không đổi |

**Không nhầm access rule với assignment rule.** Được phép truy cập một private outer instance field theo nested lexical access rules không đồng nghĩa static context tự có enclosing instance; và field mutable không tự trở thành local captured variable.

## 4. `final` tường minh

Khai báo:

~~~java
final int multiplier = 3;

Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(multiplier * 2);
    }
};
~~~

`multiplier` là local primitive final. Compiler cho anonymous class dùng nó.

Nếu thêm `multiplier = 4;` sẽ lỗi vì final variable không được gán lại sau khi đã khởi tạo.

### 4.1. Final reference vẫn có thể trỏ mutable object

~~~java
final StringBuilder output = new StringBuilder();

Runnable task = new Runnable() {
    @Override
    public void run() {
        output.append("X");
    }
};

task.run();
task.run();
System.out.println(output); // XX
~~~

Hai lần chạy thay cùng StringBuilder. Biến `output` vẫn giữ nguyên reference. **Final không đồng nghĩa immutable**.

### 4.2. Final không đồng nghĩa mọi dữ liệu đều là compile-time constant

~~~java
final int number = Integer.parseInt("17");
~~~

`number` final, nhưng initializer được đánh giá tại runtime và không phải constant expression. Anonymous class vẫn capture được number, vì yêu cầu là final/effectively final chứ không phải compile-time constant.

### 4.3. Có lúc không cần viết final

Từ Java 8, các effectively final locals/parameters có thể được capture bởi inner classes. Trong Java 17, phần lớn ví dụ không cần modifier `final` nếu biến thực sự không bị gán lại.

## 5. Effectively final được xác định như thế nào?

Một local variable không khai báo `final` là *effectively final* nếu nó không bị assigned lại theo những quy tắc trong Java Language Specification, kể cả definite-assignment cases.

Hợp lệ:

~~~java
int base = 10;

Runnable job = new Runnable() {
    @Override
    public void run() {
        System.out.println(base + 5);
    }
};
~~~

`base` chỉ có initial assignment. Không có thay đổi variable sau đó.

Không hợp lệ:

~~~java
int base = 10;

Runnable job = new Runnable() {
    @Override
    public void run() {
        System.out.println(base + 5);
    }
};

base = 20; // LỖI: base không effectively final.
~~~

Đây là **mã cố ý không biên dịch**. Việc assignment nằm sau declaration anonymous class **không cứu được**; compiler xét assignments trong scope liên quan.

### 5.1. `++`, `--` và compound assignment cũng là thay biến

Nếu `base` được capture:

~~~java
base++;
++base;
base += 1;
base -= 2;
base = base * 2;
~~~

mỗi thao tác đều cập nhật **chính local variable**. Chúng không hợp lệ trong tình huống khiến `base` mất effectively final.

Ngược lại:

~~~java
builder.append("x");
list.add("y");
array[0]++;
box.value++;
map.put("k", "v");
~~~

là cập nhật **state của referent hoặc field/array element**, không phải gán lại local reference variable tương ứng. Chúng có thể hợp lệ về capture, dù có thể vi phạm API contract/concurrency constraints khác.

### 5.2. Một initial assignment trên mỗi definite-assignment path

~~~java
int chosen;
if (flag) {
    chosen = 10;
} else {
    chosen = 20;
}

Runnable job = new Runnable() {
    @Override
    public void run() {
        System.out.println(chosen);
    }
};
~~~

Đây là **fragment** giả định `flag` đã khai báo. Theo rules về definite assignment và effectively final, `chosen` có thể được capture: nó được gán khi trước đó definitely unassigned trên các paths và được definite-assigned trước chỗ sử dụng. Không có yêu cầu mọi biến capture phải có initializer ngay trong declaration.

### 5.3. Các assignments không reachable và flow analysis

Việc kiểm tra effectively final có các quy tắc chi tiết theo JLS, không thể thay bằng mẹo “đếm dấu =”. Trong những tình huống flow phức tạp, dùng compiler/JLS để xác định chính xác, hoặc viết lại thành một immutable local snapshot rõ ràng thay vì cố tận dụng các góc cạnh khó đọc.

### 5.4. Không phải constant variable mới capture được

`final/effectively final` khác **constant variable**. Một local `int n = readFromInput();` không được reassigned vẫn có thể capture, dù giá trị chỉ biết tại runtime.

## 6. Chương trình hoàn chỉnh 1: final và effectively final

Tạo tệp **`AnonymousCaptureBasicsDemo.java`**:

~~~java
public class AnonymousCaptureBasicsDemo {
    public static void main(String[] args) {
        final int base = 10;
        int addition = 7;
        StringBuilder label = new StringBuilder("A");

        Runnable task = new Runnable() {
            @Override
            public void run() {
                System.out.println("Number = " + (base + addition));
                System.out.println("Label = " + label);
            }
        };

        task.run();

        label.append("B");
        task.run();

        System.out.println("After mutation = " + label);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 AnonymousCaptureBasicsDemo.java
java AnonymousCaptureBasicsDemo
~~~

**Stdout chính xác:**

~~~text
Number = 17
Label = A
Number = 17
Label = AB
After mutation = AB
~~~

**Giải thích:**

- `base` được khai báo final.
- `addition` không final tường minh, nhưng effectively final vì không gán lại.
- `label` là reference variable effectively final, vẫn trỏ cùng StringBuilder sau `append`.
- Task đọc primitive sum hai lần, đều 17.
- StringBuilder state đổi từ A sang AB, nên lần hai in AB.

**Không có StringBuilder copy ngầm định** khi anonymous class capture `label`.

## 7. Bản chất capture: primitive value, reference value và aliasing

Java variables chứa values. Với primitives, đó là primitive values. Với reference types, đó là reference values tới objects, không phải bản thân contents của objects.

### 7.1. Primitive capture

~~~java
int number = 5;
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(number);
    }
};
~~~

`number` phải effectively final. Anonymous class dùng value 5.

Không có một mutable int object nằm sau `number` để caller sửa qua một alias.

### 7.2. Reference capture

~~~java
StringBuilder first = new StringBuilder("A");
StringBuilder second = first;

Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println(first);
    }
};

second.append("B");
task.run(); // AB
~~~

`first` effectively final; `second` là một local reference variable khác trỏ cùng object. Sửa object qua `second` làm anonymous class nhìn thấy AB.

### 7.3. Capture reference không tạo snapshot

Một anonymous class capture `List`, `Date`, mutable domain object, array hoặc StringBuilder **không tự đóng băng contents** ở thời điểm tạo instance. Nếu API yêu cầu snapshot, phải dùng một immutable representation hoặc defensive copy tại boundary.

### 7.4. Lý do ngôn ngữ yêu cầu effectively final

Anonymous class object có thể thoát khỏi method và sống lâu hơn activation đã tạo nó. Thay vì cho phép truy cập một local stack variable có thể liên tục được reassigned từ nhiều scopes, Java dùng semantics capture những variable values hợp lệ. Điều này ngăn kiểu code lầm tưởng anonymous callback “tự động nhìn thấy reassignment của local variable”.

Tuy vậy, object ở heap mà captured reference chỉ tới vẫn có thể thay state theo ownership/concurrency contract.

## 8. Chương trình hoàn chỉnh 2: tham số và definite assignment

Tạo tệp **`AnonymousParameterCaptureDemo.java`**:

~~~java
public class AnonymousParameterCaptureDemo {
    static Runnable create(boolean premium, String customer) {
        int points;

        if (premium) {
            points = 20;
        } else {
            points = 5;
        }

        Runnable task = new Runnable() {
            @Override
            public void run() {
                System.out.println(customer + ":" + points);
            }
        };

        return task;
    }

    public static void main(String[] args) {
        Runnable first = create(true, "Lan");
        Runnable second = create(false, "Minh");

        first.run();
        second.run();
        first.run();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AnonymousParameterCaptureDemo.java
java AnonymousParameterCaptureDemo
~~~

**Stdout chính xác:**

~~~text
Lan:20
Minh:5
Lan:20
~~~

### 8.1. Vì sao `points` effectively final?

`points` được khai báo nhưng không initialized ngay. Mỗi path của if/else gán points một lần khi còn definitely unassigned, rồi variable không được thay nữa. Anonymous class được tạo sau khi points đã được khởi tạo trong mọi path.

### 8.2. Vì sao `customer` được capture?

Method parameter `customer` không bị assigned lại trong create. Nó effectively final và là String reference đến immutable String. Mỗi invocation tạo anonymous-class object có captured values của invocation đó.

### 8.3. Hai invocation không dùng chung biến primitive

`create(true, "Lan")` và `create(false, "Minh")` có parameter/local values riêng. Hai Runnable objects dùng những captured values tương ứng, không có một global `points` chung.

### 8.4. Nếu `customer = customer.trim()` trong method thì sao?

Nếu customer bị capture như trong code này, reassignment của parameter làm nó không effectively final, bất kể diễn ra trước hay sau expression tạo anonymous class.

Thay vì reassign captured parameter, tạo:

~~~java
String normalizedCustomer = customer.trim();
~~~

rồi capture `normalizedCustomer` nếu biến đó không bị assigned lại.

## 9. Phân biệt reassignment và mutation bằng bảng

| Biểu thức | Đổi chính captured local variable? | Kết luận |
| --- | --- | --- |
| `int n = 1;` | Initial assignment | Capture được nếu effectively final |
| `n++;` | Có | Không được khi n đã được capture |
| `n += 1;` | Có | Tương tự |
| `list = new ArrayList<>();` | Có | Không được với captured list |
| `list.add("x");` | Không | Hợp lệ về capture, nếu List mutable |
| `builder.append("x");` | Không | Hợp lệ về capture |
| `builder = new StringBuilder();` | Có | Không được nếu builder bị capture |
| `array[0] = 9;` | Không gán lại array variable | Có thể hợp lệ |
| `array = new int[3];` | Có | Không được với captured array |
| `box.value++;` | Không gán lại box reference | Có thể hợp lệ nếu field mutable |
| `map.put("k", v);` | Không gán lại map reference | Có thể hợp lệ nếu map mutable |
| `outer.count++;` | Thay outer field | Không phải reassignment captured local |

**Hãy xác định l-value thực sự bị ghi.** `box.value++` ghi vào field trên object; `n++` ghi vào local primitive variable.

### 9.1. Khi call mutator không được phép vì API

Một `List.of("A")` object là unmodifiable. Anonymous class capture reference tới List này hoàn toàn có thể compile, nhưng khi gọi `add` sẽ ném `UnsupportedOperationException`. Đây là **runtime collection contract**, không phải compiler check final/effectively final.

### 9.2. Khi referent là immutable

Một `String` object không có method thay contents; capture reference tới String là an toàn đối với chuyện mutation của chính String. Không cần `new String(oldValue)` chỉ để phòng vệ.

## 10. Chương trình hoàn chỉnh 3: mutable List và array

Tạo tệp **`AnonymousMutableReferentDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousMutableReferentDemo {
    public static void main(String[] args) {
        List<String> tags = new ArrayList<>(List.of("A"));
        int[] counter = {0};

        Runnable task = new Runnable() {
            @Override
            public void run() {
                counter[0]++;
                tags.add("T" + counter[0]);
                System.out.println("Task tags = " + tags);
            }
        };

        tags.add("outside");

        task.run();
        task.run();

        System.out.println("Final tags = " + tags);
        System.out.println("Count = " + counter[0]);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousMutableReferentDemo.java
java AnonymousMutableReferentDemo
~~~

**Stdout chính xác:**

~~~text
Task tags = [A, outside, T1]
Task tags = [A, outside, T1, T2]
Final tags = [A, outside, T1, T2]
Count = 2
~~~

`tags` và `counter` là reference variables, không bị assigned lại. Task có thể sửa ArrayList và phần tử `counter[0]` vì đây là mutable referents.

Một mảng một phần tử thường được dùng như “holder” cho counter trong closure-like code. Cách này hợp lệ về syntax, nhưng không đồng nghĩa thiết kế luôn tốt: dễ tạo hidden mutable state và không có atomicity khi nhiều threads gọi run.

## 11. Anonymous class có thể sống lâu hơn method tạo nó

Một phương thức factory có thể trả về Runnable từ anonymous class. Method kết thúc, nhưng Runnable object còn reachable vẫn sử dụng được captured values.

Tạo tệp **`AnonymousLifetimeDemo.java`**:

~~~java
public class AnonymousLifetimeDemo {
    static Runnable create(String title, StringBuilder text) {
        int lengthAtCreation = text.length();

        return new Runnable() {
            @Override
            public void run() {
                System.out.println(
                        title + "|" + lengthAtCreation + "|" + text);
            }
        };
    }

    public static void main(String[] args) {
        StringBuilder data = new StringBuilder("A");
        Runnable task = create("job", data);

        data.append("B");
        task.run();

        data.append("C");
        task.run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousLifetimeDemo.java
java AnonymousLifetimeDemo
~~~

**Stdout chính xác:**

~~~text
job|1|AB
job|1|ABC
~~~

### 11.1. Ba captured values có vai trò khác nhau

- `title` là parameter String; immutable String contents.
- `lengthAtCreation` là primitive int 1, được tính ngay khi create chạy.
- `text` là parameter reference tới cùng StringBuilder mà caller giữ trong `data`.

Sau khi create trả về, captured int vẫn là 1; StringBuilder contents có thể tiếp tục thay A→AB→ABC qua alias của caller.

### 11.2. Object lifetime và GC

Returned anonymous-class object có thể giữ captured referents **reachable**. Nếu nó capture một List lớn hoặc domain aggregate, object graph đó có thể tồn tại lâu hơn method tạo callback. Đây là vấn đề ownership và resource lifetime, không phải Java tự sao chép toàn bộ data vào class.

### 11.3. Không dựa vào compiler implementation details

Compiler có thể dùng các synthetic fields/constructor parameters để lưu captured values, nhưng tên/thứ tự fields synthetic không phải contract ứng dụng. Hãy dựa vào semantics quan sát qua code, không kiểm tra tên field cụ thể.

## 12. `this` trong anonymous class và enclosing `Outer.this`

Trong anonymous class instance method:

- `this` là **anonymous-class instance**.
- `Outer.this` trong phạm vi lexical instance phù hợp là **enclosing Outer instance**.
- Một local variable có tên giống field có thể dẫn đến shadowing/name resolution khác trực giác.
- `this` trong lambda lại có **lexical this semantics**, không tạo lambda-instance this như anonymous class.

### 12.1. Chương trình hoàn chỉnh 4: ai sở hữu field?

Tạo tệp **`AnonymousThisDemo.java`**:

~~~java
public class AnonymousThisDemo {
    private final String name;

    AnonymousThisDemo(String name) {
        this.name = name;
    }

    Runnable build(String label) {
        return new Runnable() {
            private final String name = "anonymous";

            @Override
            public void run() {
                System.out.println("Captured = " + label);
                System.out.println("Anonymous this = " + this.name);
                System.out.println("Outer this = "
                        + AnonymousThisDemo.this.name);
            }
        };
    }

    public static void main(String[] args) {
        AnonymousThisDemo outer = new AnonymousThisDemo("outer");
        Runnable task = outer.build("local");
        task.run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousThisDemo.java
java AnonymousThisDemo
~~~

**Stdout chính xác:**

~~~text
Captured = local
Anonymous this = anonymous
Outer this = outer
~~~

### 12.2. Giải thích

`label` là method parameter effectively final, được capture. `this.name` là **field của anonymous object**. `AnonymousThisDemo.this.name` là **field của enclosing outer object**. Chúng không đồng nghĩa với captured parameter.

Nếu anonymous class được tạo trong **static method**, không có enclosing AnonymousThisDemo instance để dùng `AnonymousThisDemo.this`. Nếu cần instance state, truyền outer reference hoặc tạo trong instance context.

### 12.3. Fields không bắt buộc effectively final

Một outer instance field có thể mutable và được anonymous class đọc nhiều lần. Điều kiện effectively final của **captured locals/parameters** không áp dụng trực tiếp lên outer object fields. Điều này là nguyên nhân phổ biến khiến người học nhầm “biến nào cũng phải final” khi nhìn code anonymous class.

## 13. Các local scopes, definite assignment và shadowing

Không phải mọi identifier trùng tên đều resolve tới một captured local. Anonymous class có thể khai báo field trùng tên và làm **shadow** tên local variable trong enclosing scope.

~~~java
int base = 10;

Runnable task = new Runnable() {
    int base = 20;

    @Override
    public void run() {
        System.out.println(base);
    }
};
~~~

Đây là fragment. `base` trong run trỏ đến **field của anonymous class**, nên in 20, không nhất thiết capture outer local base.

### 13.1. Đặt tên rõ

~~~java
int capturedBase = 10;

Runnable task = new Runnable() {
    int ownBase = 20;

    @Override
    public void run() {
        System.out.println(capturedBase + ownBase);
    }
};
~~~

Kết quả là 30 nếu task.run được gọi. Đặt tên riêng cho captured values và anonymous fields thường dễ hiểu hơn shadowing.

### 13.2. Không có cú pháp `method.this.local`

`Outer.this` chỉ định enclosing instance của một class type trong ngữ cảnh phù hợp; method local variables không phải fields của một `Method.this` object. Nếu tên local bị shadow khiến không còn accessible theo cách mong đợi, tạo một alias khác có tên rõ trước anonymous-class expression.

### 13.3. Variable phải được definite-assigned trước khi dùng

~~~java
int result;
Runnable task = new Runnable() {
    public void run() {
        System.out.println(result); // Không definite-assigned.
    }
};
result = 3;
~~~

Đây là đoạn **cố ý không biên dịch**: variable bị capture nhưng chưa được definite-assigned tại chỗ dùng theo rules; cũng cần thỏa effectively final. Không dùng cách “sẽ gán trước khi gọi task.run” để lách static definite-assignment analysis.

## 14. Vòng lặp: vì sao basic-for index thường không capture được?

Xem:

~~~java
for (int i = 0; i < 3; i++) {
    Runnable task = new Runnable() {
        public void run() {
            System.out.println(i); // Cố ý không biên dịch.
        }
    };
}
~~~

`i++` làm basic-for loop variable `i` không effectively final. Java từ chối capture trực tiếp.

### 14.1. Tạo snapshot mỗi iteration

~~~java
for (int i = 0; i < 3; i++) {
    final int index = i;

    Runnable task = new Runnable() {
        public void run() {
            System.out.println(index);
        }
    };

    tasks.add(task);
}
~~~

Đây là **fragment**, giả định `tasks` là collection có type phù hợp. Mỗi iteration tạo một local variable `index` riêng, gán một lần và được capture vào Runnable object của lượt đó.

### 14.2. Enhanced-for variable

Với enhanced-for:

~~~java
for (String name : names) {
    Runnable task = new Runnable() {
        public void run() {
            System.out.println(name);
        }
    };
}
~~~

Nếu `name` không bị assigned lại trong body, enhanced-for iteration variable có thể được capture theo rules của từng iteration. Đây khác basic-for index `i` bị tăng trong update clause.

## 15. Chương trình hoàn chỉnh 5: anonymous class capture qua loops

Tạo tệp **`AnonymousLoopCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousLoopCaptureDemo {
    public static void main(String[] args) {
        List<Runnable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            final int index = i;

            tasks.add(new Runnable() {
                @Override
                public void run() {
                    System.out.println("Index = " + index);
                }
            });
        }

        for (String color : List.of("red", "blue")) {
            tasks.add(new Runnable() {
                @Override
                public void run() {
                    System.out.println("Color = " + color);
                }
            });
        }

        for (Runnable task : tasks) {
            task.run();
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousLoopCaptureDemo.java
java AnonymousLoopCaptureDemo
~~~

**Stdout chính xác:**

~~~text
Index = 0
Index = 1
Index = 2
Color = red
Color = blue
~~~

Mỗi anonymous object trong basic-for giữ captured int `index` của lượt mà nó được tạo. Trong enhanced-for, mỗi object giữ iteration variable `color` của lượt tương ứng. Không có chuyện mọi objects tự động đọc chung `i = 3` sau vòng lặp, bởi direct capture của biến i không được compiler cho phép.

## 16. Snapshot so với live reference

Một anonymous callback có thể được chạy muộn sau khi dữ liệu nguồn thay đổi. Bạn cần xác định business requirement:

- **Live reference:** callback nên quan sát state hiện tại của một object mutable.
- **Snapshot:** callback nên dùng giá trị tại thời điểm được tạo hoặc đăng ký.
- **Immutable value:** có thể chia sẻ reference trực tiếp nếu object thực sự immutable.
- **Defensive copy:** tạo dữ liệu độc lập nếu cần tránh external alias mutation.

### 16.1. Capture mutable List trực tiếp

~~~java
List<String> source = new ArrayList<>(List.of("A"));

Runnable task = new Runnable() {
    public void run() {
        System.out.println(source);
    }
};

source.add("B");
task.run(); // [A, B]
~~~

Không phải “capture lúc A nên luôn in A”. Anonymous class giữ reference tới **cùng ArrayList**.

### 16.2. Capture snapshot List

~~~java
List<String> source = new ArrayList<>(List.of("A"));
List<String> snapshot = List.copyOf(source);

Runnable task = new Runnable() {
    public void run() {
        System.out.println(snapshot);
    }
};

source.add("B");
task.run(); // [A]
~~~

`List.copyOf` tạo unmodifiable **structural snapshot** phù hợp với `List<String>`. String elements immutable nên không cần copy sâu hơn trong tình huống này.

### 16.3. Unmodifiable view khác snapshot

`Collections.unmodifiableList(source)` tạo view chặn mutation qua view nhưng vẫn có thể phản ánh mutations ở underlying `source` qua alias khác. Đừng nhầm với `List.copyOf` snapshot.

### 16.4. Mutable elements trong snapshot

`List.copyOf(List<MutableItem>)` không deep-copy MutableItem objects. Nếu source có một element mutable, và caller giữ alias để sửa nó, callback capture snapshot List vẫn có thể thấy state element đổi. Khi cần snapshot sâu, chuyển elements thành immutable DTOs hoặc copy them theo contract.

## 17. Chương trình hoàn chỉnh 6: live state và immutable snapshot

Tạo tệp **`AnonymousSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        List<String> snapshot = List.copyOf(source);

        Runnable observer = new Runnable() {
            @Override
            public void run() {
                System.out.println("Live = " + source);
                System.out.println("Snapshot = " + snapshot);
            }
        };

        source.add("B");
        observer.run();

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Snapshot unmodifiable");
        }

        System.out.println("Source after attempt = " + source);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousSnapshotDemo.java
java AnonymousSnapshotDemo
~~~

**Stdout chính xác:**

~~~text
Live = [A, B]
Snapshot = [A]
Snapshot unmodifiable
Source after attempt = [A, B]
~~~

**Điều đáng nhớ:** cả `source` và `snapshot` đều effectively final variables, nhưng **một referent mutable** và **một referent unmodifiable snapshot**. Chính object semantics giải thích output, không phải biến nào có modifier final.

## 18. Reassignment của parameters cũng bị cấm khi capture

Method parameter có thể được anonymous class capture khi final/effectively final.

~~~java
static Runnable create(String title) {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println(title);
        }
    };
}
~~~

Hợp lệ, vì `title` không reassigned.

Không hợp lệ:

~~~java
static Runnable broken(String title) {
    Runnable task = new Runnable() {
        @Override
        public void run() {
            System.out.println(title);
        }
    };
    title = title.trim(); // Parameter đã capture mất effectively final.
    return task;
}
~~~

Đây là **method fragment cố ý không biên dịch**.

### 18.1. Chuẩn hóa input mà vẫn capture được

~~~java
static Runnable normalized(String input) {
    String value = input.trim();

    return new Runnable() {
        @Override
        public void run() {
            System.out.println(value);
        }
    };
}
~~~

`value` được khởi tạo một lần; `input` không bị capture trong anonymous class. Đây là pattern rõ nghĩa hơn việc muốn mutate cùng parameter variable sau khi capture.

### 18.2. Nếu parameter là mutable object reference

`List<String> items` có thể effectively final dù gọi `items.add("X")` trong enclosing method hoặc anonymous callback. Nhưng state List sẽ được chia sẻ nếu không copy.

## 19. Anonymous-class instance fields và state riêng của callback

Anonymous class có thể có fields của chính instance:

~~~java
Runnable task = new Runnable() {
    private int calls;

    @Override
    public void run() {
        calls++;
        System.out.println(calls);
    }
};
~~~

`calls` là **instance field của anonymous object**, không phải local variable được capture. Nó có thể được thay ở các lần chạy.

Tệp **`AnonymousOwnStateDemo.java`**:

~~~java
public class AnonymousOwnStateDemo {
    public static void main(String[] args) {
        int step = 2;

        Runnable first = new Runnable() {
            private int count;

            @Override
            public void run() {
                count += step;
                System.out.println("First count = " + count);
            }
        };

        Runnable second = new Runnable() {
            private int count = 100;

            @Override
            public void run() {
                count += step;
                System.out.println("Second count = " + count);
            }
        };

        first.run();
        second.run();
        first.run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousOwnStateDemo.java
java AnonymousOwnStateDemo
~~~

**Stdout chính xác:**

~~~text
First count = 2
Second count = 102
First count = 4
~~~

`step` là captured primitive, không thay. `count` là field riêng của từng anonymous object. `first` và `second` có class implementations khác nhau trong source và mỗi object có state riêng. Không cần mutable holder local cho mục đích counter riêng của callback.

### 19.1. Vì sao đây không vi phạm effectively final?

Effectively final quy định các **local variables/parameters được capture** từ enclosing scope. `count++`/`count += step` trong anonymous class thay **field count** thuộc object, không thay local `step`.

### 19.2. Đừng dùng field để che giấu shared-state bugs

Nếu callback được chia sẻ giữa nhiều threads, anonymous-instance `count++` vẫn không atomic. Tính hợp lệ về scope không phải thread safety.

## 20. Anonymous class so với lambda: cùng ràng buộc capture nhưng khác semantics

Lambda và anonymous class đều có thể dùng local variables/parameters final/effectively final. Tuy nhiên:

| Đặc điểm | Anonymous class | Lambda |
| --- | --- | --- |
| Khai báo implementation | `new Interface() { ... }` | `(...) -> ...` |
| Có body của một class mới | Có | Không phải anonymous class |
| `this` | Anonymous object instance | Lexical enclosing `this` |
| Instance fields riêng trong body | Có thể khai báo | Không khai báo fields trong lambda expression |
| Captured local variables | Final/effectively final | Final/effectively final |
| Captured mutable referent | Vẫn có thể thay | Vẫn có thể thay |
| Cách chọn interface methods | Có thể implement/override theo class body | Target phải là functional interface phù hợp |
| Dễ giữ nhiều mutable fields callback | Có | Dùng external holder/owner nếu cần |

Không suy rằng lambda “capture live variable” còn anonymous class “capture copy”, hoặc ngược lại. Cả hai không cho reassign local variable đã capture theo rules.

### 20.1. Ví dụ so sánh

~~~java
int factor = 2;
StringBuilder buffer = new StringBuilder("A");

Runnable anon = new Runnable() {
    @Override
    public void run() {
        System.out.println(factor + ":" + buffer);
    }
};

Runnable lambda = () -> System.out.println(factor + ":" + buffer);

buffer.append("B");
anon.run();    // 2:AB
lambda.run();  // 2:AB
~~~

Chỉ referent StringBuilder đổi.

### 20.2. Không coi lambda là anonymous class

Lambda có type tương ứng functional interface và runtime translation do JVM/compiler xử lý; không nên phụ thuộc vào tên class runtime/identity hoặc synthetic implementation details của lambda. Khác biệt `this` và scope cũng là lý do khi thay anonymous class bằng lambda cần review hành vi, không chỉ xóa boilerplate.

## 21. Chương trình hoàn chỉnh 7: anonymous và lambda cùng capture

Tạo tệp **`AnonymousVsLambdaCaptureDemo.java`**:

~~~java
public class AnonymousVsLambdaCaptureDemo {
    public static void main(String[] args) {
        int factor = 2;
        StringBuilder shared = new StringBuilder("A");

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("Anonymous = "
                        + factor + ":" + shared);
            }
        };

        Runnable lambda = () ->
                System.out.println("Lambda = "
                        + factor + ":" + shared);

        shared.append("B");

        anonymous.run();
        lambda.run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousVsLambdaCaptureDemo.java
java AnonymousVsLambdaCaptureDemo
~~~

**Stdout chính xác:**

~~~text
Anonymous = 2:AB
Lambda = 2:AB
~~~

Không có StringBuilder copy tự động ở cả hai. `factor` không thay, `shared` reference không bị assigned lại, nhưng StringBuilder contents đổi.

## 22. Concurrency: captured reference không làm object thread-safe

Một callback có thể được chạy từ một thread pool, timer, event bus hoặc UI event dispatcher. Với anonymous class dùng shared mutable object:

~~~java
int[] total = {0};

Runnable action = new Runnable() {
    @Override
    public void run() {
        total[0]++;
    }
};
~~~

`total` effectively final, nhưng `total[0]++` **không phải atomic increment** khi nhiều threads cùng chạy action. Có thể mất updates.

### 22.1. Chọn `AtomicInteger` khi cần atomic counter

Tệp **`AnonymousAtomicCaptureDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AnonymousAtomicCaptureDemo {
    public static void main(String[] args)
            throws InterruptedException {
        int amount = 3;
        AtomicInteger total = new AtomicInteger();

        Runnable task = new Runnable() {
            @Override
            public void run() {
                total.addAndGet(amount);
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);

        a.start();
        b.start();

        a.join();
        b.join();

        System.out.println("Total = " + total.get());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AnonymousAtomicCaptureDemo.java
java AnonymousAtomicCaptureDemo
~~~

**Stdout chính xác:**

~~~text
Total = 6
~~~

`amount` là primitive effectively final. `total` là AtomicInteger reference effectively final. Hai tasks atomic-add 3 vào cùng AtomicInteger; main thread `join` cả hai rồi đọc nên kết quả xác định 6, không phụ thuộc thứ tự hai threads.

### 22.2. `AtomicInteger` không phải giải pháp cho mọi graph mutable

Nếu anonymous class tham chiếu nhiều fields hoặc một List/Map mutable, một AtomicInteger đơn lẻ không làm các operations khác atomic hoặc consistent. Dùng lock, concurrent collection, immutable snapshots, safe publication hoặc dedicated owner service tùy yêu cầu.

### 22.3. `final` reference không đồng nghĩa child fields `volatile`

Ngay cả khi compiler/captured field reference ổn định, mutable state bên dưới có thể là đối tượng của data races. Muốn thấy những cập nhật cross-thread đúng theo Java Memory Model, cần các **happens-before** relationships hoặc đồng bộ tương thích.

## 23. Lưu ý đặc biệt về UI/event listeners và callbacks

Anonymous classes xuất hiện trong event listeners:

~~~java
StringBuilder state = new StringBuilder("initial");

button.addActionListener(new ActionListener() {
    @Override
    public void actionPerformed(ActionEvent event) {
        System.out.println(state);
    }
});
~~~

Đây là **fragment** mang tính minh họa (cần các types/biến Swing tương ứng), không phải standalone program. Local variable `state` effectively final, nhưng contents của StringBuilder có thể thay trước khi user click button. Listener đọc **current state** của referent, không bắt buộc đọc text ban đầu.

Câu hỏi khi thiết kế listener:

1. Listener muốn **live model** hay **snapshot lúc đăng ký**?
2. Data có mutable/immutable không?
3. Event thread có đọc state do thread khác mutate không?
4. Listener được unregister khi không còn cần chưa?
5. Captured references có vô tình giữ một UI object graph lớn không?

### 23.1. Đừng capture heavy resource vô thời hạn

Nếu một long-lived listener capture service, session hoặc UI object, object có thể tồn tại lâu hơn dự kiến do listener còn được đăng ký. GC dựa trên reachability. Cần quản lý lifecycle/unsubscribe khi thích hợp.

### 23.2. Captured mutable request/context có thể dẫn đến race

Một request callback chạy async không nên mặc định capture một mutable Map request parameters rồi để caller sửa Map sau khi enqueue. Nếu muốn semantics “giá trị tại thời điểm scheduling”, copy sang immutable snapshot khi tạo callback.

## 24. Những lỗi thường gặp và cách sửa

### Lỗi 1 — gán lại local được capture

~~~java
int retry = 1;
Runnable task = new Runnable() {
    public void run() {
        System.out.println(retry);
    }
};
retry++; // Cố ý không biên dịch.
~~~

**Sửa:** xác định giá trị final/effectively final cần capture hoặc chuyển state thực sự mutable vào một owner object phù hợp.

### Lỗi 2 — reassign captured parameter sau khi tạo callback

~~~java
Runnable create(String name) {
    Runnable task = new Runnable() {
        public void run() {
            System.out.println(name);
        }
    };
    name = name.trim(); // Cố ý không biên dịch.
    return task;
}
~~~

**Sửa:** tạo `String normalized = name.trim();` rồi capture normalized.

### Lỗi 3 — cho rằng final List không thể add

~~~java
final List<String> items = new ArrayList<>();
items.add("A"); // Hợp lệ.
~~~

**Sửa tư duy:** final biến khác immutable List.

### Lỗi 4 — dùng `List.of` và nghĩ lỗi là do capture

~~~java
List<String> items = List.of("A");
Runnable task = new Runnable() {
    public void run() {
        items.add("B"); // Compile được, run ném UOE.
    }
};
~~~

**Sửa:** không gọi mutators trên unmodifiable collection; dùng mutable List nếu cần hoặc immutable update tạo List mới.

### Lỗi 5 — capture một mutable List rồi kỳ vọng snapshot

~~~java
List<String> items = new ArrayList<>(List.of("A"));
Runnable task = new Runnable() {
    public void run() {
        System.out.println(items);
    }
};
items.add("B");
~~~

Task sẽ có thể in [A, B] nếu chạy sau mutation trên cùng thread. Muốn [A], capture `List.copyOf(items)` với String elements.

### Lỗi 6 — tưởng mảng holder tự thread-safe

`int[] counter = {0};` rồi `counter[0]++` không atomic khi concurrency. Nếu cần thread-safe counter, dùng `AtomicInteger` hoặc lock/owner phù hợp.

### Lỗi 7 — capture basic-for `i` trực tiếp

`i++` làm i không effectively final. **Sửa:** tạo final/effectively final snapshot `index = i` mỗi iteration.

### Lỗi 8 — nhầm captured locals với anonymous fields

Một anonymous object có `int count` field, và run có thể tăng count. Điều đó không phản chứng rule final/effectively final vì count **không phải outer local được capture**.

### Lỗi 9 — nhầm anonymous `this` với outer `this`

Trong anonymous-class method, `this` là anonymous instance. Dùng `OuterClass.this` khi cần enclosing instance và context cho phép.

### Lỗi 10 — quên callback có lifetime dài

Anonymous-class object có thể giữ referents lớn sống lâu, gây memory retention. Review registration/unregistration và chỉ capture dữ liệu cần thiết.

### Lỗi 11 — coi lambda là anonymous class hoàn toàn tương đương

Capture rule tương đồng nhưng `this` và class semantics có khác biệt; khi refactor cần kiểm tra behavior.

### Lỗi 12 — phụ thuộc synthetic fields

Tên các compiler-generated captured fields không phải API, có thể thay theo compiler/version. Không dùng reflection dựa trên các tên đó cho application logic.

## 25. Checklist trước khi dùng anonymous-class capture

1. Anonymous class được tạo ở instance hay static context?
2. Nó capture những local variables/parameters nào?
3. Mỗi captured variable có final/effectively final không?
4. Có assignments, `++`/`--`, compound assignments làm mất tính đó không?
5. Các variables có definite-assigned trước khi được dùng không?
6. Captured type là primitive hay reference?
7. Referent mutable hay immutable?
8. Có aliases ở caller có thể sửa referent không?
9. Callback cần live value hay snapshot?
10. Nếu snapshot, đã dùng immutable projection/defensive copying chưa?
11. List copy có mutable elements cần copy sâu hơn không?
12. Có nhầm unmodifiable view với snapshot không?
13. Có biến outer instance field bị hiểu nhầm là captured local không?
14. Anonymous-class own instance field có ownership rõ không?
15. Có shadowing tên field và local variable không?
16. Basic-for index có snapshot mỗi iteration chưa?
17. Enhanced-for variable có bị gán lại không?
18. Anonymous object có thể sống lâu hơn method tạo nó không?
19. Captured object graph có làm tăng lifetime/memory retention không?
20. Callback có được gọi từ nhiều threads không?
21. Mutable operations có synchronization/atomicity phù hợp không?
22. Có dùng `this` đúng nghĩa anonymous vs enclosing instance không?
23. Nếu chuyển sang lambda, behavior `this`/method resolution có thay không?
24. Có phân biệt compile-time capture error với runtime collection errors không?
25. Có code tests chứng minh mutation/snapshot và output như mong muốn không?

## 26. Bài tập có đáp án

**Câu 1.** Anonymous class có được capture local variable không khai báo `final`?

**Đáp án:** Có nếu variable *effectively final* và thỏa definite-assignment/scope rules.

**Câu 2.** `final StringBuilder text` có cấm gọi `text.append` không?

**Đáp án:** Không; chỉ cấm gán lại reference variable, không cấm mutator của StringBuilder.

**Câu 3.** Gán `text = new StringBuilder()` sau declaration anonymous class đã capture text có hợp lệ không?

**Đáp án:** Không nếu variable mất effectively final. Vị trí reassignment sau expression không tạo ngoại lệ.

**Câu 4.** Nếu captured primitive int không thay, callback có luôn in cùng một giá trị primitive đó không?

**Đáp án:** Nếu method chỉ in chính captured primitive thì có; nhưng expression tổng thể vẫn có thể phụ thuộc mutable fields/objects khác.

**Câu 5.** Captured reference có tạo deep copy object không?

**Đáp án:** Không. Nó dùng reference value, và các aliases tới referent vẫn có thể thay state.

**Câu 6.** Một local `int[] counts = {0}` được capture; `counts[0]++` có compile không?

**Đáp án:** Có về capture: array element thay chứ không phải local reference; thread safety là vấn đề riêng.

**Câu 7.** `counts = new int[]{1}` có hợp lệ khi counts đã capture không?

**Đáp án:** Không, vì đó là reassignment of local reference variable.

**Câu 8.** Parameter không khai báo final nhưng không reassign có capture được không?

**Đáp án:** Có, nếu effectively final.

**Câu 9.** Parameter đã capture được trim bằng `parameter = parameter.trim()` không?

**Đáp án:** Không nếu gán lại làm parameter không effectively final. Tạo local normalized để capture.

**Câu 10.** Nếu captured List là ArrayList mutable, caller add sau khi đăng ký callback, callback có thấy không?

**Đáp án:** Có thể nhìn thấy mới nếu cùng object, theo execution/concurrency behavior; capture không snapshot nội dung.

**Câu 11.** `List.copyOf(source)` có tạo structural snapshot phù hợp không?

**Đáp án:** Có với contents không null theo contract, nhưng nó không deep-copy mutable elements.

**Câu 12.** `Collections.unmodifiableList(source)` có luôn tách biệt source không?

**Đáp án:** Không; view vẫn có thể phản ánh source mutations qua alias khác.

**Câu 13.** Vì sao anonymous-class object vẫn dùng được values sau method return?

**Đáp án:** Object giữ captured values theo Java semantics; không cần method stack frame tiếp tục hoạt động.

**Câu 14.** Capture một large mutable object có thể kéo dài lifetime của nó không?

**Đáp án:** Có nếu anonymous object còn reachable và giữ object qua captured reference.

**Câu 15.** `this` trong anonymous class có trỏ outer class không?

**Đáp án:** Không; `this` là anonymous instance. Dùng qualified `Outer.this` ở instance lexical context thích hợp.

**Câu 16.** Anonymous class instance field có cần effectively final không?

**Đáp án:** Không theo capture-local rule. Nó là field của anonymous object; mutability theo field declaration.

**Câu 17.** Enclosing outer instance field có phải final để anonymous class thay được không?

**Đáp án:** Không; final/effectively final restriction ở đây áp dụng captured locals/parameters, không outer instance fields.

**Câu 18.** Basic-for loop index tăng bằng i++ có capture trực tiếp được không?

**Đáp án:** Không, vì i không effectively final. Snapshot `index = i` mỗi iteration.

**Câu 19.** Enhanced-for iteration variable không bị reassign có capture được không?

**Đáp án:** Có theo rules của enhanced-for từng iteration.

**Câu 20.** Hai Runnable tạo bởi hai invocations của cùng factory method có chia sẻ primitive parameter value không?

**Đáp án:** Không mặc định; mỗi invocation có argument values riêng được capture. Chúng có thể cùng trỏ một object nếu caller đưa cùng reference vào.

**Câu 21.** Capture `AtomicInteger` là nguyên nhân increment atomic?

**Đáp án:** Không; atomicity đến từ AtomicInteger API.

**Câu 22.** Có thể dùng `int[] holder` và nghĩ dữ liệu được tự bảo vệ giữa threads không?

**Đáp án:** Không. Array update không tự atomic.

**Câu 23.** Lambda và anonymous class có cùng final/effectively final rule đối với captured locals không?

**Đáp án:** Có, nhưng semantics `this` và class body khác.

**Câu 24.** Vì sao không nên tin `equals` khi hỏi hai references có cùng object identity không?

**Đáp án:** `equals` có thể so value, còn `==` so identity cho compatible references.

**Câu 25.** Thay `list.add("x")` bằng `list = otherList` thay điều gì?

**Đáp án:** Biểu thức đầu mutate referent; biểu thức sau reassign captured local variable và có thể bị compiler từ chối.

**Câu 26.** Mutable List được capture có làm anonymous object chính nó mutable không?

**Đáp án:** Mutable referent có thể làm output/observable behavior của callback thay theo thời gian, dù reference variable được giữ cố định; cần xác định contract.

**Câu 27.** Nếu cần text ở thời điểm tạo callback, capture StringBuilder hay String?

**Đáp án:** Thường capture String snapshot từ `builder.toString()`, vì String immutable.

**Câu 28.** Nếu field anonymous class và outer local cùng tên, identifier unqualified trong anonymous body chắc chắn là outer local không?

**Đáp án:** Không; shadowing có thể làm field được chọn. Dùng tên riêng rõ ràng.

**Câu 29.** Một field static có bị final/effectively final capture rule như local không?

**Đáp án:** Không; static field là class state, có scope và concurrency rules riêng.

**Câu 30.** Ý chính quan trọng nhất của bài?

**Đáp án:** Anonymous class chỉ được capture local variables/parameters final hoặc effectively final; với reference variable, đó là reference value tới object — **không tự cấm mutation của object**.

## 27. Tóm tắt và ứng dụng

Khi anonymous class tham chiếu đến biến/parameter bên ngoài, hỏi theo đúng thứ tự:

1. Đây có phải **local variable/parameter** hay là **instance/static field**?
2. Nếu là local/parameter, compiler có xác định được rằng nó **final/effectively final**?
3. Nếu type là reference, referent có thể mutate hoặc có aliases khác không?
4. Callback được chạy ngay hay có thể được giữ lại, gọi sau/ở thread khác?
5. API yêu cầu **live state** hay **snapshot state**?
6. Có cần defensive copy, immutable value, ownership policy hoặc synchronization?

Nguyên tắc áp dụng: dùng `final` hoặc effectively final để có capture hợp lệ; dùng **immutable values và snapshots** nếu muốn dữ liệu không thay; dùng **shared mutable objects với API/concurrency contract** nếu chủ đích muốn trạng thái cập nhật. Tránh biến static/global state hay mảng holder chỉ để lách compiler nếu điều đó tạo thêm coupling.

**Phân biệt giữa “giá trị của biến được capture” và “trạng thái object được reference trỏ tới” là chìa khóa của anonymous classes Java.** Nắm rõ ranh giới này giúp viết listeners, callbacks, workers, GUI handlers và asynchronous operations đúng cả lúc biên dịch lẫn lúc chạy.
