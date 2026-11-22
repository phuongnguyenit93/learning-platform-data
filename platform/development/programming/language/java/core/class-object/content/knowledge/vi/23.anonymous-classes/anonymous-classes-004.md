# Khởi tạo trường và khối khởi tạo khi lớp vô danh không có hàm khởi tạo có tên

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích `new Interface() { ... }` hoặc `new Base(args) { ... }` tạo **anonymous class** (*lớp vô danh*) và instance của lớp đó, thay vì chỉ tạo một object của interface hoặc đúng lớp Base.
- Hiểu vì sao anonymous class **không được khai báo constructor tường minh**, nhưng Java compiler vẫn tạo **anonymous constructor ngầm** để gọi constructor phù hợp của superclass.
- Dùng **instance field initializers** (`int value = expression;`) và **instance initializer blocks** (`{ ... }`) để thiết lập state, chạy validation và thực hiện bước khởi tạo cần thiết.
- Phân biệt instance initializer block với method body, constructor body, static initializer và lambda body.
- Nắm thứ tự thực thi: đánh giá qualifier/constructor arguments khi có, cấp phát object và gán mặc định fields, gọi superclass constructor, rồi thực hiện field initializers cùng initializer blocks của anonymous class theo **thứ tự xuất hiện trong source**.
- Dự đoán stdout khi xen kẽ nhiều field initializers/blocks, khi tạo nhiều instances và khi superclass constructor gọi method được anonymous class override.
- Khởi tạo `final` instance fields bằng expression hoặc block theo quy tắc definite assignment; biết tại sao không thể đặt logic đó trong một constructor **mang tên anonymous class**.
- Hiểu captured local variables (final/effectively final), outer instance references, `this` và `super` trong anonymous class initializer.
- Xử lý checked/unchecked exceptions từ anonymous class instance initializers, trong đó checked exceptions có thể được compiler liệt kê qua anonymous constructor ngầm.
- Nhận diện lỗi phổ biến: forward field reference, dùng field trước khi được set, method override được gọi trong superclass constructor, `this` escape khi chưa xây xong, nhầm static context và interface-target type.
- So sánh initializer với factory method, named subclass, lambda và object composition để chọn thiết kế dễ đọc, dễ kiểm thử trong Java 17+.
- Biên dịch/chạy các chương trình độc lập; đọc stdout, phân biệt code minh họa không chạy độc lập và test behavior có thể xác minh.

## 1. Lớp vô danh là gì và vì sao không có constructor có tên?

Một anonymous class được định nghĩa và tạo instance trong **cùng một class instance creation expression**:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
~~~

`Runnable` là interface; expression trên tạo **một class không đặt tên ở source** triển khai interface rồi tạo một instance của class đó. Code gọi phương thức qua biến `Runnable task`.

Ví dụ khác, với một class làm superclass:

~~~java
abstract class Work {
    abstract String message();
}

Work w = new Work() {
    @Override
    String message() {
        return "ready";
    }
};
~~~

Đây là các **mảnh minh họa cần đặt trong scope/file phù hợp**. Anonymous subclass của Work được tạo và override `message()`.

Để viết một **constructor declaration** trong Java, cần **tên class** của constructor. Anonymous class không có simple name bạn có thể đưa vào declaration; vì thế:

~~~java
Runnable bad = new Runnable() {
    // Runnable() { }  // Không phải constructor hợp lệ ở đây.
    // SomeName() { }  // Cũng không có anonymous class name để dùng.
    @Override
    public void run() {
    }
};
~~~

Anonymous class **không thể khai báo constructor tường minh**. Theo JLS §15.9.5.1, compiler cung cấp **anonymous constructor ngầm**, đưa parameters hợp lệ đến constructor của superclass và xử lý checked exceptions liên quan.

> Không có constructor **tường minh, có tên** không có nghĩa object **không được khởi tạo**. Anonymous instance vẫn trải qua toàn bộ các bước tạo instance Java; bạn có field initializers, instance initializer blocks, superclass constructors và (khi thích hợp) phương thức factory ở bên ngoài.

## 2. Hai công cụ thay cho constructor body trong anonymous class

### 2.1. Field initializer

Đặt expression ở declaration của instance field:

~~~java
Runnable task = new Runnable() {
    private int count = 3;
    private final String name = "job";

    @Override
    public void run() {
        System.out.println(name + ":" + count);
    }
};
~~~

Mỗi **instance mới** của anonymous class có các instance fields của nó. `count = 3` và `name = "job"` thực hiện khởi tạo khi object được tạo (sau superclass constructor).

### 2.2. Instance initializer block

Đặt một block **không có tên method/constructor và không có modifier** trong anonymous class body:

~~~java
Runnable task = new Runnable() {
    private int count;

    {
        count = 3;
        if (count < 0) {
            throw new IllegalArgumentException("count");
        }
    }

    @Override
    public void run() {
        System.out.println(count);
    }
};
~~~

Block `{ count = 3; ... }` là **instance initializer**, chạy tự động trong quá trình khởi tạo object. Nó **không phải** method `run()`, không đợi đến lúc caller gọi `run()`.

Trong Java 17, anonymous class có thể khai báo các instance fields, methods và initializer blocks như class body hợp lệ; phải tuân thủ access, definite assignment và exception rules.

### 2.3. Dùng cái nào?

- Một expression đủ rõ để tính initial value: dùng `private final int limit = Math.max(...);`.
- Cần vài statements, validation hoặc gán một `final` field sau khi xử lý: dùng instance initializer block.
- Cần phối hợp nhiều paths, dependencies, resource lifetime, error handling phức tạp: thường nên dùng **named class** hoặc **factory method** thay vì làm anonymous block quá dài.

## 3. Chương trình đầu tiên: field initializer rồi block rồi method

Lưu **`AnonymousSimpleInitializerDemo.java`**:

~~~java
public class AnonymousSimpleInitializerDemo {
    public static void main(String[] args) {
        Runnable action = new Runnable() {
            private int counter = 2;

            {
                System.out.println("initial block");
                counter *= 3;
            }

            @Override
            public void run() {
                System.out.println("run counter=" + counter);
            }
        };

        System.out.println("object ready");
        action.run();
        action.run();
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac AnonymousSimpleInitializerDemo.java
java AnonymousSimpleInitializerDemo
~~~

**Stdout:**

~~~text
initial block
object ready
run counter=6
run counter=6
~~~

Đọc thứ tự:

1. `new Runnable() { ... }` bắt đầu tạo anonymous instance.
2. Field `counter` mặc định là 0 khi memory được cấp; sau superclass constructor (`Object()`) field initializer gán 2.
3. Instance block in `initial block` và nhân counter lên 6.
4. Expression `new ...` hoàn thành; caller in `object ready`.
5. Hai calls `run()` chỉ chạy method body, **không** chạy lại initializer. Counter vẫn 6 vì `run` không thay nó.

**Quy tắc nhớ:** **initializer chạy trong lúc tạo object, method chạy khi được gọi**.

## 4. Trình tự khởi tạo toàn diện

Xem một expression tổng quát:

~~~java
Base object = new Base(arg1, arg2) {
    int a = initA();

    {
        initializeMore();
    }

    int b = initB();

    @Override
    void work() {
    }
};
~~~

Đây chỉ là **sơ đồ code**; cần khai báo Base và helper methods để biên dịch. Với một anonymous subclass, về logic Java 17:

1. Đánh giá receiver/qualifier liên quan và các constructor argument expressions theo thứ tự của Java.
2. Cấp phát object instance và đặt instance fields về default values: `0`, `false`, `null`, ...
3. Thiết lập enclosing/captured state mà compiler cần theo semantics; không dựa vào thứ tự/synthetic field names như một public API.
4. Chạy constructor chain của superclass (kể cả ancestors). Nếu constructor cấp cha ném exception, anonymous field/instance initializers **không chạy**.
5. Trong anonymous class, chạy **instance variable initializers** và **instance initializer blocks** xen kẽ, **từ trái sang phải/theo thứ tự xuất hiện trong class body**.
6. Anonymous class không có **explicit constructor body** của chính nó chạy sau các blocks. Constructor ngầm hoàn thành rồi expression trả reference nếu thành công.

Đây là áp dụng JLS §12.5 (*Creation of New Class Instances*) và §15.9.5.1 (*Anonymous Constructors*). Không được tráo “khởi tạo field” lên trước superclass constructor chỉ vì field declaration đặt ở đầu anonymous body.

### 4.1. Bảng thứ tự dễ so sánh

| Sự kiện | Khi nào xảy ra? | Có lặp khi gọi method không? |
| --- | --- | --- |
| Constructor argument expressions | Khi đánh giá `new` | Không |
| Default values của instance fields | Trước constructor chain | Không |
| Superclass constructor | Trong khởi tạo object | Không |
| Anonymous field initializer | Sau superclass constructor; theo source order | Không |
| Anonymous instance initializer block | Sau superclass constructor; xen kẽ theo source order | Không |
| Anonymous overridden method body | Khi được gọi hoặc bị dispatch bởi code khác | Có thể nhiều lần |
| Static initializer của một class | Theo class initialization rules | Không theo mỗi instance |

**Ngoại lệ quan trọng:** nếu superclass constructor gọi một overridable method và override trong anonymous class được dispatch **ngay lúc đó**, method có thể chạy **trước** field/initializer blocks của anonymous class. Điều này không vi phạm thứ tự: method dispatch phát sinh từ superclass constructor đang chạy.

## 5. Chương trình: xen kẽ nhiều field initializers và blocks

Lưu **`AnonymousInitializerOrderDemo.java`**:

~~~java
public class AnonymousInitializerOrderDemo {
    static int log(String step, int value) {
        System.out.println(step + "=" + value);
        return value;
    }

    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private int first = log("field-first", 1);

            {
                System.out.println("block-one=" + first);
                first += 4;
            }

            private int second = log("field-second", first * 2);

            {
                System.out.println("block-two=" + second);
                second++;
            }

            @Override
            public void run() {
                System.out.println("run=" + first + "," + second);
            }
        };

        System.out.println("after-new");
        task.run();
    }
}
~~~

Chạy:

~~~bash
javac AnonymousInitializerOrderDemo.java
java AnonymousInitializerOrderDemo
~~~

Output:

~~~text
field-first=1
block-one=1
field-second=10
block-two=10
after-new
run=5,11
~~~

Phân tích không cần đoán compiler:

- Field `first` được khởi tạo giá trị 1.
- Block-one đọc 1 rồi cộng thêm 4 → `first = 5`.
- Field `second` tính `first * 2 = 10`.
- Block-two thấy 10 và tăng `second` lên 11.
- Sau khi object sẵn sàng, `run()` in 5 và 11.

Nếu đổi **vị trí** block-one sau `second`, kết quả sẽ khác. Chính **source order** của các field/instance initializer quan trọng, không phải thứ tự tên hay kiểu declaration.

## 6. Constructor của lớp cha chạy trước anonymous initializers

Anonymous class có thể kế thừa **một superclass có constructor parameters**:

~~~java
abstract class Job {
    Job(String name) {
        System.out.println("base constructor: " + name);
    }

    abstract void execute();
}
~~~

Khi tạo `new Job("A") { ... }`, `"A"` được dùng để chọn và gọi constructor `Job(String)`. Anonymous class không khai báo constructor tên riêng và không được thêm `super("A")` trong một constructor không tồn tại.

### 6.1. Chương trình runnable

Lưu **`AnonymousSuperclassOrderDemo.java`**:

~~~java
public class AnonymousSuperclassOrderDemo {
    static abstract class Job {
        Job(String name) {
            System.out.println("super=" + name);
        }

        abstract void execute();
    }

    static int printAndReturn(String label, int value) {
        System.out.println(label + "=" + value);
        return value;
    }

    public static void main(String[] args) {
        Job job = new Job("REPORT") {
            private int size = printAndReturn("field-size", 3);

            {
                System.out.println("block-size=" + size);
                size += 2;
            }

            @Override
            void execute() {
                System.out.println("execute-size=" + size);
            }
        };

        System.out.println("created");
        job.execute();
    }
}
~~~

Chạy:

~~~bash
javac AnonymousSuperclassOrderDemo.java
java AnonymousSuperclassOrderDemo
~~~

Output:

~~~text
super=REPORT
field-size=3
block-size=3
created
execute-size=5
~~~

Constructor lớp cha chạy trước **field-size**, rồi initializer block. Dòng `created` xuất hiện khi expression `new` đã hoàn tất. Anonymous initializer không phải lựa chọn để **chạy trước superclass constructor**.

### 6.2. Nếu superclass constructor dùng arguments có side effects?

Java đánh giá các constructor argument expressions trước khi gọi constructor; nếu `log("arg", x)` in log thì việc in đó có thể xảy ra trước log trong superclass constructor. Nhưng đừng lẫn **đánh giá argument** với **khởi tạo instance fields của anonymous subclass**, vốn vẫn chạy sau superclass constructor.

## 7. Dùng instance initializer để gán `final` field

Một instance field có `final` phải được gán đúng theo Java definite assignment rules. Anonymous class **không thể viết constructor tường minh**, nhưng có thể dùng field initializer:

~~~java
private final int limit = 10;
~~~

hoặc **blank final** được gán trong instance initializer block:

~~~java
private final int limit;

{
    int base = 2;
    limit = base * 5;
}
~~~

Không được gán lại `limit` khi nó đã được gán. Một local variable `int base` trong block chỉ phục vụ tính toán, không tự biến thành field.

### 7.1. Chương trình: blank final field

Lưu **`AnonymousFinalFieldDemo.java`**:

~~~java
public class AnonymousFinalFieldDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private final int threshold;
            private final String label;

            {
                int units = 4;
                threshold = units * 3;
                label = "T-" + threshold;

                if (threshold <= 0) {
                    throw new IllegalArgumentException("threshold");
                }
            }

            @Override
            public void run() {
                System.out.println(label);
                System.out.println("threshold=" + threshold);
            }
        };

        task.run();
    }
}
~~~

Chạy:

~~~bash
javac AnonymousFinalFieldDemo.java
java AnonymousFinalFieldDemo
~~~

Output:

~~~text
T-12
threshold=12
~~~

`threshold` và `label` được gán đúng một lần trong block, trước khi method `run` được gọi. Nếu code muốn sửa final field sau đó, compiler sẽ từ chối theo Java assignment rules.

### 7.2. Validation không thay thế constructor contract

Kiểm tra invariant trong block có thể hữu ích, nhưng một anonymous class có logic tạo object quá nhiều dòng thường khó đọc. Với public/domain object có validation phức tạp, **named class constructor hoặc static factory** giúp API và unit tests rõ hơn.

## 8. Captured local variables trong field/instance initializer

Anonymous class là inner class; code trong anonymous class body có thể dùng **final/effectively final** local variables từ enclosing method, khi thỏa các quy tắc Java capture.

~~~java
int factor = 4; // effectively final

Runnable task = new Runnable() {
    private final int result = factor * 3;

    @Override
    public void run() {
        System.out.println(result);
    }
};
~~~

Field initializer lấy giá trị của `factor` để xây state. Java không cho anonymous class capture một local variable được gán lại theo cách phá effectively-final constraint.

### 8.1. Chương trình kết hợp capture với block

Lưu **`AnonymousCapturedInputDemo.java`**:

~~~java
public class AnonymousCapturedInputDemo {
    static Runnable create(int input) {
        int adjustment = 5; // Effectively final.

        return new Runnable() {
            private final int result = input + adjustment;

            {
                System.out.println("built result=" + result);
            }

            @Override
            public void run() {
                System.out.println("run result=" + result);
            }
        };
    }

    public static void main(String[] args) {
        Runnable first = create(7);
        Runnable second = create(10);

        first.run();
        second.run();
    }
}
~~~

Chạy:

~~~bash
javac AnonymousCapturedInputDemo.java
java AnonymousCapturedInputDemo
~~~

Output:

~~~text
built result=12
built result=15
run result=12
run result=15
~~~

Hai method calls tạo hai anonymous instances, với các captured values riêng. `input` là method parameter nhưng không bị gán lại, còn `adjustment` là effectively final local.

**Quan trọng:** một `final` reference tới mutable object vẫn có thể trỏ tới object bị sửa qua alias khác. Capture một list hay array reference không biến object đó thành immutable.

## 9. Không dùng instance initializer để “khai báo constructor”

So sánh ba cấu trúc:

~~~java
Runnable task = new Runnable() {
    private int value = 1;  // Field initializer.

    {                        // Instance initializer block.
        value++;
    }

    private void update() {  // Method, chỉ chạy nếu được gọi.
        value++;
    }

    @Override
    public void run() {
        update();
        System.out.println(value);
    }
};
~~~

`value` sẽ là 2 sau construction, tăng thành 3 khi `run()` gọi `update()`.

**Không hợp lệ:**

~~~java
Runnable task = new Runnable() {
    // Task() { }          // Không có tên anonymous type để khai constructor.
    // Runnable() { }      // Không được khai constructor có tên interface.
    // { return; }         // return không được xuất hiện trong instance initializer.
    @Override
    public void run() {
    }
};
~~~

Các dòng sai được comment. Một **instance initializer** không thể chứa `return` statement; JLS §8.6 cũng yêu cầu initializer **có thể hoàn thành bình thường** theo quy tắc reachability, dù nó có thể throw exception trên một số paths.

**Không nhầm** với code trong `run()`: method có thể `return;` vì là method `void`.

## 10. Gọi method riêng từ initializer

Anonymous class có thể khai báo helper method, rồi gọi nó từ field initializer hoặc instance block. Nhưng nếu helper **đọc fields khác chưa khởi tạo**, rất dễ thấy default values.

~~~java
Runnable task = new Runnable() {
    private int left = compute();

    private int right = 9;

    private int compute() {
        return right + 1;
    }

    @Override
    public void run() {
        System.out.println(left + "," + right);
    }
};
~~~

Theo thứ tự source này, `left` initializer gọi `compute()` **trước** khi initializer `right = 9` thực hiện. Vì vậy `right` lúc đó vẫn có giá trị mặc định 0, và `left = 1`. Sau đó `right = 9`.

### 10.1. Chương trình runnable

Lưu **`AnonymousMethodIndirectionDemo.java`**:

~~~java
public class AnonymousMethodIndirectionDemo {
    public static void main(String[] args) {
        Runnable task = new Runnable() {
            private int first = readSecond();
            private int second = 9;

            private int readSecond() {
                return second + 1;
            }

            @Override
            public void run() {
                System.out.println("first=" + first);
                System.out.println("second=" + second);
            }
        };

        task.run();
    }
}
~~~

Chạy:

~~~bash
javac AnonymousMethodIndirectionDemo.java
java AnonymousMethodIndirectionDemo
~~~

Output:

~~~text
first=1
second=9
~~~

Method `readSecond` được gọi khi field initializer thực thi, không tự làm mọi fields “đã khởi tạo”. Để tránh bug, ưu tiên khai báo dependencies **trước những fields dùng chúng** hoặc tính dependency bằng explicit values sẵn có.

## 11. Forward reference: tên đơn và truy cập qua `this`

Java có quy tắc riêng cho việc dùng một field **trước declaration** trong initializer:

~~~java
Runnable task = new Runnable() {
    // int first = second;  // Lỗi simple-name forward reference.
    private int first = this.second;
    private int second = 7;

    @Override
    public void run() {
        System.out.println(first + "," + second);
    }
};
~~~

Ở đây `this.second` là qualified field access nên tránh chính lỗi **simple-name forward reference** của JLS §8.3.3, nhưng **không làm initialization xảy ra sớm**. `second` lúc tính `first` vẫn là 0, nên `first = 0`; sau đó `second = 7`.

**Đừng dùng `this.second` như mẹo để che một thứ tự init sai.** Compiler cho phép không đồng nghĩa state đã sẵn sàng.

### 11.1. Chương trình chứng minh

Lưu **`AnonymousForwardReferenceDemo.java`**:

~~~java
public class AnonymousForwardReferenceDemo {
    public static void main(String[] args) {
        Runnable action = new Runnable() {
            private int first = this.second;
            private int second = 7;

            @Override
            public void run() {
                System.out.println("first=" + first);
                System.out.println("second=" + second);
            }
        };

        action.run();
    }
}
~~~

Chạy:

~~~bash
javac AnonymousForwardReferenceDemo.java
java AnonymousForwardReferenceDemo
~~~

Output:

~~~text
first=0
second=7
~~~

**Khuyến nghị:** đặt field `second` trước field `first` nếu `first` cần giá trị đã khởi tạo của `second`:

~~~java
private int second = 7;
private int first = second;
~~~

Đây là snippet hợp lệ **bên trong một class body**, không phải standalone Java file.

## 12. Superclass constructor gọi method bị override quá sớm

Một lỗi tinh vi của kế thừa: superclass constructor có thể gọi một instance method có thể override. Java dispatch theo **runtime class của object**, vì thế override trong anonymous subclass có thể chạy **trước** khi field/instance initializers của anonymous class thực hiện.

### 12.1. Chương trình stdout cố ý thấy field mặc định

Lưu **`AnonymousEarlyDispatchDemo.java`**:

~~~java
public class AnonymousEarlyDispatchDemo {
    static class Parent {
        Parent() {
            System.out.println("super sees=" + value());
        }

        int value() {
            return -1;
        }
    }

    public static void main(String[] args) {
        Parent child = new Parent() {
            private int number = 5;

            {
                System.out.println("block number=" + number);
            }

            @Override
            int value() {
                return number;
            }
        };

        System.out.println("after construction=" + child.value());
    }
}
~~~

Chạy:

~~~bash
javac AnonymousEarlyDispatchDemo.java
java AnonymousEarlyDispatchDemo
~~~

Output:

~~~text
super sees=0
block number=5
after construction=5
~~~

**Giải thích cặn kẽ:**

1. Object anonymous subclass đã được cấp memory; field `number` có default 0.
2. `Parent()` chạy và gọi virtual method `value()`.
3. Runtime dispatch chọn **override của anonymous subclass**.
4. `number = 5` chưa chạy nên method thấy 0.
5. Parent constructor hoàn thành; anonymous initializer `number = 5` rồi block in 5.
6. Sau khi tạo xong, gọi `value()` lần nữa trả 5.

Đây không phải do field initializer bị bỏ qua; nó chạy **sau** superclass constructor. Bài học thiết kế: **tránh gọi overridable methods từ constructors** khi logic subclass có thể cần state chưa sẵn sàng. Lỗi tương tự xảy ra cả với named subclasses, không riêng anonymous class.

## 13. `this` trong anonymous block trỏ tới ai?

Trong anonymous class initializer, `this` là **anonymous instance**, không phải enclosing outer object. Nếu expression xuất hiện trong instance method của Outer, `Outer.this` có thể là reference tới enclosing instance khi hợp lệ.

~~~java
class Outer {
    private int id = 10;

    Runnable make() {
        return new Runnable() {
            private int id = 3;

            {
                id += 1; // Anonymous field.
            }

            public void run() {
                System.out.println(id);
                System.out.println(Outer.this.id);
            }
        };
    }
}
~~~

Các snippets thuộc cùng class context trên. `this.id` trong anonymous class là field `id` của anonymous class; `Outer.this.id` là field của enclosing Outer. Đừng viết `Outer.this` trong static context không có Outer instance.

### 13.1. Chương trình minh họa

Lưu **`AnonymousThisDemo.java`**:

~~~java
public class AnonymousThisDemo {
    private final int outerValue = 20;

    Runnable newAction() {
        return new Runnable() {
            private int innerValue = 2;

            {
                innerValue += 3;
            }

            @Override
            public void run() {
                System.out.println("inner=" + this.innerValue);
                System.out.println("outer=" +
                        AnonymousThisDemo.this.outerValue);
            }
        };
    }

    public static void main(String[] args) {
        AnonymousThisDemo owner = new AnonymousThisDemo();
        Runnable task = owner.newAction();
        task.run();
    }
}
~~~

Chạy:

~~~bash
javac AnonymousThisDemo.java
java AnonymousThisDemo
~~~

Output:

~~~text
inner=5
outer=20
~~~

Anonymous class không có tên source nên bạn không thể viết `new AnonymousThisDemo.Anonymous()` hoặc khai báo một constructor cho nó. Nhưng code vẫn có quyền đọc enclosing instance state theo inner class rules.

### 13.2. Khác với lambda

Một lambda đặt trong instance method dùng `this` theo **lexical context** (thường là outer object). Trong anonymous class, `this` là **anonymous object**. Lambda cũng không có class body nơi bạn đặt instance field initializer/initializer block theo cú pháp anonymous class.

## 14. Với interface: constructor arguments luôn rỗng

Khi tạo anonymous class implement interface:

~~~java
Runnable action = new Runnable() {
    {
        System.out.println("initialized");
    }

    @Override
    public void run() {
    }
};
~~~

`Runnable` là interface, không có constructor để bạn gọi với arguments. `new Runnable() { ... }` dùng empty parentheses. Anonymous class có Object làm direct superclass và triển khai Runnable.

**Không hợp lệ:**

~~~java
// Runnable action = new Runnable(42) {
//     public void run() { }
// };
~~~

Không được truyền `42` như argument của một constructor Runnable. Nếu muốn sử dụng giá trị từ caller, dùng **captured effectively final local variable**, hoặc tạo named class/constructor nhận giá trị, hay factory trả Runnable.

Với **class làm superclass**, `new Base(args) { ... }` có thể có arguments phù hợp constructors của Base.

## 15. Chương trình: superclass arguments và anonymous initializer

Lưu **`AnonymousArgumentDemo.java`**:

~~~java
public class AnonymousArgumentDemo {
    static abstract class Report {
        private final String title;

        Report(String title) {
            this.title = title;
            System.out.println("base title=" + title);
        }

        String title() {
            return title;
        }

        abstract String render();
    }

    public static void main(String[] args) {
        int extra = 4;

        Report report = new Report("Sales") {
            private final int count = extra + 1;

            {
                System.out.println("anonymous count=" + count);
            }

            @Override
            String render() {
                return title() + ":" + count;
            }
        };

        System.out.println("render=" + report.render());
    }
}
~~~

Chạy:

~~~bash
javac AnonymousArgumentDemo.java
java AnonymousArgumentDemo
~~~

Output:

~~~text
base title=Sales
anonymous count=5
render=Sales:5
~~~

- Constructor `Report(String)` xử lý `"Sales"`.
- Anonymous class tự khởi tạo `count` từ captured local `extra`.
- Anonymous initializer block chỉ in count sau khi superclass constructor đã hoàn tất.
- `render()` có thể đọc method `title()` được kế thừa và anonymous field `count`.

Không có chỗ hợp lệ để thêm `Report(String) { ... }` bên trong anonymous class nhằm “ghi đè constructor”.

## 16. Instance initializer có thể chạy validation và ném exception

Một anonymous initializer block có thể kiểm tra invariants:

~~~java
Runnable job = new Runnable() {
    private final int amount = 5;

    {
        if (amount < 0) {
            throw new IllegalArgumentException("negative");
        }
    }

    @Override
    public void run() {
    }
};
~~~

Nếu validation thất bại và block ném exception, creation expression **không trả một object đã khởi tạo thành công** cho caller. Những initializers nằm sau exception **không được chạy**.

### 16.1. Chương trình fail-fast có stdout xác định

Lưu **`AnonymousInitializerFailureDemo.java`**:

~~~java
public class AnonymousInitializerFailureDemo {
    static Runnable create(int input) {
        return new Runnable() {
            private final int amount = input;

            {
                System.out.println("checking=" + amount);
                if (amount < 0) {
                    throw new IllegalArgumentException(
                            "amount must be nonnegative");
                }
                System.out.println("validated");
            }

            @Override
            public void run() {
                System.out.println("run amount=" + amount);
            }
        };
    }

    public static void main(String[] args) {
        Runnable valid = create(2);
        valid.run();

        try {
            create(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("creation rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac AnonymousInitializerFailureDemo.java
java AnonymousInitializerFailureDemo
~~~

Output:

~~~text
checking=2
validated
run amount=2
checking=-1
creation rejected
~~~

Dòng `validated` **không** in cho lần tạo thứ hai vì exception dừng khởi tạo. Không có `run amount=-1` vì creation expression không hoàn thành bình thường.

### 16.2. Tránh biến initializer thành workflow có side effects lớn

Nếu block mở resource, đăng ký listener hoặc ghi trạng thái toàn cục rồi thất bại ở bước sau, có nguy cơ để lại side effects dù object creation thất bại. Dùng factory/try-with-resources/cleanup transaction nếu initialization không còn là chuyện đơn giản.

## 17. Checked exceptions: trường hợp đặc biệt của anonymous initializer

Đây là điểm dễ nhầm với named classes.

JLS §11.2.3 cho phép **instance variable initializer hoặc instance initializer của anonymous class** phát sinh checked exceptions. Compiler sinh **anonymous constructor ngầm với `throws` thích hợp**, do đó nơi viết `new ... { ... }` phải catch hoặc declare checked exception.

Không đúng khi khẳng định “initializer block không bao giờ được throw IOException vì anonymous class không có constructor `throws`”. Chính **anonymous constructor ngầm** giải quyết ràng buộc này.

### 17.1. Chương trình: checked exception từ field initializer

Lưu **`AnonymousCheckedExceptionDemo.java`**:

~~~java
import java.io.IOException;

public class AnonymousCheckedExceptionDemo {
    static String load(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("simulated input failure");
        }
        return "loaded";
    }

    static Runnable create(boolean fail) throws IOException {
        return new Runnable() {
            private final String text = load(fail);

            {
                System.out.println("initialized=" + text);
            }

            @Override
            public void run() {
                System.out.println("run=" + text);
            }
        };
    }

    public static void main(String[] args) {
        try {
            Runnable good = create(false);
            good.run();
        } catch (IOException unexpected) {
            System.out.println("unexpected input failure");
        }

        try {
            create(true);
        } catch (IOException expected) {
            System.out.println("creation failed with IOException");
        }
    }
}
~~~

Chạy:

~~~bash
javac AnonymousCheckedExceptionDemo.java
java AnonymousCheckedExceptionDemo
~~~

Output:

~~~text
initialized=loaded
run=loaded
creation failed with IOException
~~~

`load(true)` ném IOException khi **field initializer** đang thực thi. Block in `initialized=...` nằm sau field đó nên không được chạy trong nhánh thất bại. Method `create` khai báo `throws IOException` để compiler cho phép propagation của checked exception từ expression tạo anonymous class.

### 17.2. Checked exception từ block cũng hợp lệ

Ví dụ snippet:

~~~java
Runnable job = new Runnable() {
    {
        if (someFailureCondition()) {
            throw new java.io.IOException("failed");
        }
    }

    @Override
    public void run() {
    }
};
~~~

Đây là **snippet có placeholder method `someFailureCondition()` chưa được định nghĩa**, nhằm minh họa vị trí throw; nếu đưa vào code thực hãy thay bằng một boolean/condition hợp lệ và xử lý IOException tại creation site. Anonymous block **không cần** khai báo `throws` vì block không có method/constructor signature tường minh.

Cần nhớ khác biệt: `Runnable.run()` không cho override method `run() throws IOException` vì hợp đồng interface, nhưng checked exception trong **initializer lúc tạo object** là một chuyện khác với checked exception trong **method `run`**.

## 18. Lỗi superclass constructor làm initializer không chạy

Nếu constructor của superclass throw trước khi hoàn tất, anonymous subclass instance initializers **không thực thi**.

### 18.1. Chương trình kiểm tra

Lưu **`AnonymousSuperFailureDemo.java`**:

~~~java
public class AnonymousSuperFailureDemo {
    static abstract class Base {
        Base(boolean fail) {
            System.out.println("base constructor");
            if (fail) {
                throw new IllegalStateException("base failure");
            }
        }

        abstract void run();
    }

    public static void main(String[] args) {
        try {
            Base item = new Base(true) {
                private final int value = printValue();

                private int printValue() {
                    System.out.println("anonymous field");
                    return 1;
                }

                @Override
                void run() {
                    System.out.println(value);
                }
            };

            item.run();
        } catch (IllegalStateException expected) {
            System.out.println("caught base failure");
        }
    }
}
~~~

Chạy:

~~~bash
javac AnonymousSuperFailureDemo.java
java AnonymousSuperFailureDemo
~~~

Output:

~~~text
base constructor
caught base failure
~~~

Không có dòng `anonymous field` vì constructor Base ném exception trước khi bắt đầu anonymous subclass field initializer. Caller không nhận được một instance đã xây dựng thành công.

## 19. Mỗi `new` tạo instance và chạy initializer riêng

Anonymous class được khai báo một lần trong source nhưng có thể được tạo instance **nhiều lần**, ví dụ mỗi lần gọi một factory method. Mỗi instance sẽ có instance fields riêng và thực hiện instance initialization.

### 19.1. Chương trình quan sát hai lần tạo

Lưu **`AnonymousMultipleInstancesDemo.java`**:

~~~java
public class AnonymousMultipleInstancesDemo {
    private static int nextId;

    static Runnable create() {
        return new Runnable() {
            private final int id = ++nextId;

            {
                System.out.println("init id=" + id);
            }

            @Override
            public void run() {
                System.out.println("run id=" + id);
            }
        };
    }

    public static void main(String[] args) {
        Runnable a = create();
        Runnable b = create();

        System.out.println("different instances=" + (a != b));
        a.run();
        b.run();
    }
}
~~~

Chạy:

~~~bash
javac AnonymousMultipleInstancesDemo.java
java AnonymousMultipleInstancesDemo
~~~

Output:

~~~text
init id=1
init id=2
different instances=true
run id=1
run id=2
~~~

`nextId` là static field của enclosing class để demo cấp ID; **không nên** dùng cách ++ không synchronization cho production concurrent counter.

Hai `Runnable` instances khác nhau được tạo bằng **cùng một anonymous class declaration** nhưng mỗi lần field initializer/initializer block chạy riêng.

## 20. Tại sao không dùng static initializer thay constructor?

Trong Java 17, class body của anonymous class có thể chứa static members/initializers theo quy tắc Java 16+ dành cho inner classes; nhiều bài Java 8 cũ mô tả giới hạn khác. Tuy nhiên:

- **Static initialization** là initialization của **class**, không phải của **mỗi instance**.
- Dù khai báo static member có hợp lệ ở source level hiện tại, nó không cấp constructor tường minh cho anonymous class.
- Nếu mục tiêu là kiểm tra/thiết lập **instance state**, dùng field/instance initializer.
- Static mutable state trong anonymous class có thể làm objects phụ thuộc chung một biến, gây coupling và concurrency issues.
- Khi logic static thật sự có ý nghĩa, thường **named static nested class** sẽ dễ đọc và dễ dùng hơn anonymous class.

### 20.1. So sánh ở mức ý tưởng

~~~java
Runnable a = new Runnable() {
    private int count = 1;

    {
        count++; // Theo mỗi instance.
    }

    @Override
    public void run() {
        System.out.println(count);
    }
};
~~~

Đây là snippet có giá trị riêng trong block. Không nhầm `count` là class-level static field; nó thuộc anonymous object `a`.

## 21. Anonymous class không tự được đặt tên để gọi methods mới qua interface

Xét:

~~~java
Runnable task = new Runnable() {
    private int count = 2;

    private void increase() {
        count++;
    }

    @Override
    public void run() {
        increase();
        System.out.println(count);
    }
};
~~~

Caller nhìn biến `task` có kiểu compile-time **Runnable**, nên chỉ các members accessible qua Runnable/Object (và phương thức khác theo type resolution) mới gọi được. Không thể chỉ viết `task.increase()` khi `increase` không thuộc Runnable; hơn nữa nó là private method của anonymous class.

Nếu cần công bố API tùy biến với constructor, fields và methods khác, khai báo một **named class** hoặc interface rõ ràng. Đừng dùng anonymous class như cách “định nghĩa type công khai nhưng không đặt tên”.

### 21.1. `var` trong Java 17 không phải giải pháp API lâu dài

Local variable type inference `var` đôi khi suy ra anonymous type và compiler có thể cho thao tác với members không-private phù hợp, nhưng cách này dễ làm code phụ thuộc anonymous implementation shape và không tạo ra một tên class dùng được ở API khác. Hãy giữ implementation detail kín sau interface nếu chỉ cần behavior qua interface.

## 22. Resource initialization: cần chống thất bại giữa chừng

Instance initializer thường được dùng để cấu hình một small anonymous object. Nhưng nếu block:

1. Đăng ký callback vào một registry.
2. Mở file/socket hoặc thêm listener.
3. Sau đó gặp exception trước khi hoàn tất constructor ngầm.

Thì **side effect ở bước trước có thể đã xảy ra** dù caller chưa được trả về object. Đây là nguy cơ *this escape* và resource leak.

### 22.1. Anti-pattern: cho `this` thoát khỏi initializer

~~~java
java.util.List<Runnable> listeners = new java.util.ArrayList<>();

Runnable callback = new Runnable() {
    private int ready;

    {
        listeners.add(this); // Callback được công bố khi chưa xây xong.
        ready = 1;
    }

    @Override
    public void run() {
        System.out.println(ready);
    }
};
~~~

Đoạn trên là snippet **minh họa anti-pattern**, không nên dùng làm mẫu thiết kế. Nếu registry/event bus gọi callback **ngay lúc add** hoặc ở thread khác, nó có thể quan sát object trước khi `ready` được gán. Java Memory Model cũng có các quy tắc về safe publication; initializer `this` escape làm reasoning khó hơn.

### 22.2. Hướng an toàn hơn

~~~java
Runnable callback = new Runnable() {
    private final int ready = 1;

    @Override
    public void run() {
        System.out.println(ready);
    }
};

listeners.add(callback);
~~~

Đây là snippet cần một biến `listeners` đã được khai báo đúng scope. Ở đây callback được cấu hình trước khi **công bố** vào registry. Nếu registry chạy đa luồng, vẫn cần appropriate thread-safe publication/coordination.

**Bài học:** anonymous initializer thích hợp để thiết lập state nội bộ, không phải để tự động thực hiện mọi side effect liên quan lifecycle.

## 23. Chương trình: publish sau khi anonymous object đã được xây

Lưu **`AnonymousSafeRegistrationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class AnonymousSafeRegistrationDemo {
    public static void main(String[] args) {
        List<Runnable> listeners = new ArrayList<>();

        Runnable listener = new Runnable() {
            private final String label;

            {
                label = "READY";
                System.out.println("initialized " + label);
            }

            @Override
            public void run() {
                System.out.println("callback " + label);
            }
        };

        listeners.add(listener);
        System.out.println("registered=" + listeners.size());

        for (Runnable callback : listeners) {
            callback.run();
        }
    }
}
~~~

Chạy:

~~~bash
javac AnonymousSafeRegistrationDemo.java
java AnonymousSafeRegistrationDemo
~~~

Output:

~~~text
initialized READY
registered=1
callback READY
~~~

Thông qua thứ tự output, callback được cấu hình trước khi đăng ký. Trong Java thực tế, cần quản lý cả **unregister/dispose/close** nếu registry giữ callback lâu hơn vòng đời owner.

## 24. Khởi tạo giá trị từ mutable input: snapshot hay live reference?

Anonymous class có thể có field initializer:

~~~java
final String title = builder.toString();
~~~

Nếu `builder` là captured effectively-final StringBuilder reference, `title` là một **String snapshot** tại thời điểm tạo object. Ngược lại:

~~~java
final StringBuilder shared = builder;
~~~

`shared` là cùng mutable StringBuilder object; code ở ngoài mutate builder có thể thay kết quả sau đó.

Cả hai đều là field initializers hợp lệ nhưng có **ownership semantics** khác. Từ khóa `final` bảo đảm không gán lại field reference sau initialization, không làm mutable referent trở thành bất biến.

### 24.1. Chương trình snapshot và live

Lưu **`AnonymousCaptureSnapshotDemo.java`**:

~~~java
public class AnonymousCaptureSnapshotDemo {
    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");

        Runnable task = new Runnable() {
            private final String snapshot = source.toString();
            private final StringBuilder live = source;

            @Override
            public void run() {
                System.out.println("snapshot=" + snapshot);
                System.out.println("live=" + live);
            }
        };

        source.append("B");
        task.run();
    }
}
~~~

Chạy:

~~~bash
javac AnonymousCaptureSnapshotDemo.java
java AnonymousCaptureSnapshotDemo
~~~

Output:

~~~text
snapshot=A
live=AB
~~~

Field `snapshot` giữ String immutable được tạo trong object initialization, còn `live` giữ reference tới StringBuilder mutable. Dù cả hai fields đều final, observability khác nhau.

## 25. Instance initializers và method overrides: không gọi behavior quá sớm

Superclass constructor gọi overridable method là nguy cơ đã thấy ở mục 12. Bên trong **anonymous initializer block**, bạn cũng nên tránh gọi overridable methods không kiểm soát, vì:

- Có thể gọi methods đã được override theo kế thừa.
- Phương thức có thể đọc fields chưa khởi tạo phía sau block.
- Có thể publish `this` qua callbacks.
- Nếu method thay external state/throw exception, object creation không còn dễ quản lý.

Với anonymous class đơn giản chỉ override một interface method, initializer có thể tính final fields và validate; để business behavior phức tạp chạy **sau khi creation hoàn tất** sẽ rõ hơn.

### 25.1. Bảng đánh giá

| Nhu cầu | Vị trí hợp lý | Vì sao |
| --- | --- | --- |
| Tính một giá trị đơn | Field initializer | Ít boilerplate, rõ dependency |
| Gán blank `final` từ vài bước | Instance initializer block | Thực hiện khi object được tạo |
| Kiểm tra input đơn giản | Field/helper + block | Fail-fast, lỗi phát sinh tại creation |
| Cần superclass state | Constructor arguments/methods superclass accessible | Đúng constructor chain |
| Gọi operation tùy business | Method override hoặc factory sau creation | Tránh side effect lúc init |
| Đăng ký listener với bus | Sau `new` trong owner/factory | Tránh `this` escape; lifecycle rõ |
| Resource cần cleanup nếu failure | Named class/factory/try-with-resources | Exception safety dễ hơn |
| Cần constructor overloads | Named subclass | Anonymous constructor không khai báo được |

## 26. Anonymous class có được tạo qua nhiều interface không?

Một anonymous class expression chỉ nêu **một superclass type hoặc một interface type** sau `new`. Nó không có phần `implements I1, I2` tùy ý như named class declaration.

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
    }
};
~~~

Nếu cần implement nhiều interfaces, chọn named class hoặc một superclass/interface đã hợp nhất contract phù hợp. Điều này không làm thay đổi quy tắc instance initialization: field initializers và instance blocks vẫn là cách thiết lập state cho anonymous object.

## 27. Ví dụ: anonymous subclass với superclass có final field

Superclass có thể có constructor đặt immutable state, rồi anonymous subclass có field riêng:

~~~java
class Base {
    final int id;

    Base(int id) {
        this.id = id;
    }
}
~~~

Anonymous subclass:

~~~java
Base value = new Base(7) {
    private final int twice = id * 2;
};
~~~

`id` đã được superclass constructor gán trước, vì vậy field initializer `twice` đọc 7 và tính 14. Tuy nhiên caller giữ `Base` reference không tự truy cập `twice` nếu Base không công bố accessor tương ứng.

### 27.1. Chương trình runnable với method override

Lưu **`AnonymousInheritedStateDemo.java`**:

~~~java
public class AnonymousInheritedStateDemo {
    static class Base {
        protected final int id;

        Base(int id) {
            this.id = id;
        }

        int score() {
            return id;
        }
    }

    public static void main(String[] args) {
        Base instance = new Base(7) {
            private final int twice = id * 2;

            @Override
            int score() {
                return twice;
            }
        };

        System.out.println("id=" + instance.id);
        System.out.println("score=" + instance.score());
    }
}
~~~

Chạy:

~~~bash
javac AnonymousInheritedStateDemo.java
java AnonymousInheritedStateDemo
~~~

Output:

~~~text
id=7
score=14
~~~

Lớp cha quản lý `id` qua constructor, anonymous initializer tính `twice` sau đó. Đây là ví dụ hai lớp chia trách nhiệm khởi tạo, không cần anonymous constructor tường minh.

## 28. Checked exception vs unchecked exception: bảng xử lý

| Nguồn lỗi | Exception | Có cần khai báo/catch checked exception? |
| --- | --- | --- |
| Field initializer anonymous gọi `load() throws IOException` | `IOException` (checked) | Có, ở expression `new`/method bao ngoài |
| Instance block anonymous `throw new IOException(...)` | `IOException` (checked) | Có, compiler ghi vào anonymous constructor ngầm |
| Field initializer thực hiện `1 / 0` ở runtime | `ArithmeticException` (unchecked) | Không bắt buộc khai báo |
| Validation block ném `IllegalArgumentException` | Unchecked | Không bắt buộc khai báo |
| Superclass constructor declared `throws IOException` | Checked | Có, ở `new Base(args){...}` |
| Overridden `Runnable.run()` cố `throws IOException` | Signature error | Không được thêm checked exception rộng hơn method gốc |

**Điểm chính:** checked exception trong **anonymous initialization** có thể được pháp luật ngôn ngữ hỗ trợ **qua constructor ngầm**, nhưng caller vẫn có trách nhiệm xử lý. Checked exception trong **overridden method** phải tuân riêng quy tắc overriding.

## 29. Testing: kiểm tra initializer chạy đúng một lần

Dùng counter/giao diện đơn giản để tự kiểm tra:

- Mỗi `new` làm initializer chạy đúng một lần nếu creation hoàn thành.
- `run()` nhiều lần không tái thực thi initializer.
- Superclass constructor hoàn thành trước anonymous initializers.
- Field dependencies theo source order.
- Validation failure dừng initialization.
- Checked exception được catch ở creation site.
- Fields được gán qua `final` không bị mutate.
- Không `this` escape trước khi hoàn tất.
- Không nhầm prototype/type name của anonymous class với Runtime class metadata.

### 29.1. Chương trình contract test

Lưu **`AnonymousInitializerContractTest.java`**:

~~~java
public class AnonymousInitializerContractTest {
    private static int initialized;

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    static Runnable make() {
        return new Runnable() {
            private final int value;

            {
                value = 10;
                initialized++;
            }

            @Override
            public void run() {
                check(value == 10, "value");
            }
        };
    }

    public static void main(String[] args) {
        Runnable first = make();
        check(initialized == 1, "first initialization");

        first.run();
        first.run();
        check(initialized == 1, "run does not reinitialize");

        Runnable second = make();
        check(initialized == 2, "second initialization");
        check(first != second, "distinct instances");

        second.run();
        System.out.println("anonymous initializer checks passed");
    }
}
~~~

Chạy:

~~~bash
javac AnonymousInitializerContractTest.java
java AnonymousInitializerContractTest
~~~

Output:

~~~text
anonymous initializer checks passed
~~~

Ở đây method `check` luôn thực thi, không phụ thuộc Java `assert` (bị tắt mặc định khi không dùng `-ea`). Không dựa vào garbage collection, reflection compiler synthetic names hay thứ tự luồng chạy.

## 30. So sánh nhanh với named subclass và lambda

### 30.1. Named class

~~~java
final class NamedJob implements Runnable {
    private final int limit;

    NamedJob(int limit) {
        if (limit <= 0) {
            throw new IllegalArgumentException("limit");
        }
        this.limit = limit;
    }

    @Override
    public void run() {
        System.out.println(limit);
    }
}
~~~

Đây là named class snippet hợp lệ trong một source file phù hợp. Với named class, constructor tường minh có signature `NamedJob(int)`, có thể overload, khai báo `throws`, gọi `super(...)` theo constructor rules và được test trực tiếp.

### 30.2. Anonymous class

~~~java
int limit = 10;

Runnable job = new Runnable() {
    private final int configured;

    {
        configured = limit;
    }

    @Override
    public void run() {
        System.out.println(configured);
    }
};
~~~

Ở đây không có constructor declaration tên riêng. State được cấu hình bằng captured effectively final value và initializer block.

### 30.3. Lambda

~~~java
int limit = 10;
Runnable job = () -> System.out.println(limit);
~~~

Lambda gọn hơn khi chỉ cần triển khai **functional interface behavior** và capture một vài local values. Nó không cho phép body dạng class declaration với field initializer/instance initializer block như anonymous class.

**Chọn đúng công cụ:** nếu cần nhiều fields riêng, instance initialization và override vài methods, anonymous class có thể hợp lý; nếu cần constructor API phức tạp, named class thường tốt hơn; nếu chỉ có một function behavior, lambda thường rõ nhất.

## 31. Những lỗi hiểu sai phổ biến

| Hiểu sai | Cách hiểu đúng |
| --- | --- |
| “Anonymous class không có constructor nên không có init.” | Có anonymous constructor **ngầm**, field/instance initializers vẫn chạy. |
| “Có thể khai `Runnable() { ... }` trong anonymous body.” | Không được khai constructor tường minh. |
| “Block `{...}` chỉ chạy khi `run()`.” | Instance initializer chạy khi tạo object. |
| “Field initializers chạy trước superclass constructor.” | Ngược lại: superclass constructor hoàn thành trước anonymous initializers. |
| “Mọi field initializer chạy hết rồi mới tới các blocks.” | Field initializers và blocks chạy **xen kẽ theo source order**. |
| “Mỗi lần gọi method, initializer chạy lại.” | Chỉ chạy khi tạo instance mới. |
| “`final` fields luôn phải gán ngay tại declaration.” | Có thể gán blank final hợp lệ trong instance initializer. |
| “Tạo anonymous từ interface có thể truyền constructor args.” | Không; interface không có constructor nhận args. |
| “Tạo anonymous subclass không thể gọi superclass constructor có args.” | Có thể viết `new Base(args){...}` nếu constructor hợp lệ. |
| “Anonymous initializer không thể ném checked exception.” | JLS cho phép; compiler sinh anonymous constructor `throws` tương ứng. |
| “Checked exception của init giống checked exception trong Runnable.run().” | Không; overriding method throws rules áp dụng riêng. |
| “`this` bên trong anonymous initializer là enclosing Outer.” | `this` là anonymous object; Outer dùng `Outer.this` nếu hợp lệ. |
| “Forward reference qua `this.field` nghĩa field đã init.” | Có thể đọc **default value** nếu field initializer chưa chạy. |
| “Gọi helper method sẽ đợi fields ready.” | Helper được gọi ngay khi initializer gọi; có thể đọc defaults. |
| “Superclass gọi method override thì fields của subclass sẵn.” | Có thể dispatch sớm trước anonymous initializers. |
| “Static initializer thay được constructor của mỗi anonymous instance.” | Static init là class-level; instance initializers mới chạy per-instance. |
| “Class vô danh không tạo object mới.” | Mỗi successful `new` tạo instance mới. |
| “Final reference đến StringBuilder làm builder immutable.” | Final khóa reference, mutable referent vẫn thay được. |
| “Có thể công bố `this` trong block mà luôn an toàn.” | Có thể làm object escape lúc chưa fully constructed. |
| “Caller dùng biến Runnable có thể gọi mọi method private trong anonymous.” | Chỉ members accessible qua compile-time type; private helper không lộ. |
| “`var` làm anonymous class có tên ổn định để dùng ngoài method.” | Không tạo public class name/API. |
| “Throwable từ initializer luôn có stack trace cố định.” | Không; test exception type/behavior, đừng dựa vào message/trace không cam kết. |

## 32. Checklist kiểm tra code anonymous initialization

1. Supertype là interface hay class? Có constructor arguments hợp lệ không?
2. Có vô tình khai constructor tường minh trong anonymous body không?
3. Những fields nào cần initialization expression và fields nào cần block?
4. Có `final` field chưa được gán đúng trên mọi normal path không?
5. Có nhiều instance blocks/field initializers? Thứ tự source đã đúng dependency chưa?
6. Có field nào được đọc trước initializer, đặc biệt qua `this.field`/helper method không?
7. Superclass constructor có gọi overridable method mà anonymous override cần state chưa khởi tạo không?
8. Có captured local không còn effectively final không?
9. Có outer `this`/anonymous `this` bị nhầm lẫn không?
10. Đối với IOException/checked exception từ initializer, creation site có catch/throws hợp lệ không?
11. Nếu superclass constructor throw, code có giả định anonymous block vẫn chạy không?
12. Có method `run()` được gọi nhầm khi construction chưa xong không?
13. Có `return` statement xuất hiện trực tiếp trong initializer block không?
14. Có initializer không thể complete normally do unconditional throw/loop không?
15. Có resource/registry/listener side effects trong init không? Nếu thất bại, cleanup thế nào?
16. Có `this` escape đến một thread/registry trong lúc init không?
17. Nếu field initializer capture mutable object, cần live reference hay snapshot?
18. Code có dựa synthetic class name/field name thay vì public semantics không?
19. Anonymous implementation đủ nhỏ để dễ đọc chưa, hay cần named class/factory?
20. Tests có phân biệt thời điểm creation với thời điểm method invocation không?

## 33. Câu hỏi ôn tập và đáp án

**Câu 1.** Anonymous class có được khai constructor tên `Runnable` hay `Base` trong body không?  
**Đáp án:** Không. Constructor của anonymous class luôn được khai báo **ngầm**.

**Câu 2.** Nếu muốn gán `int count=3` cho mỗi instance thì dùng gì?  
**Đáp án:** Instance field initializer, hoặc instance initializer block hợp lệ.

**Câu 3.** `{ count++; }` trực tiếp trong anonymous class body chạy khi nào?  
**Đáp án:** Trong quá trình tạo mỗi instance, sau superclass constructor theo source order.

**Câu 4.** `run()` được gọi ba lần có chạy instance initializer ba lần không?  
**Đáp án:** Không, trừ khi bạn tạo ba objects riêng; gọi method không tái khởi tạo.

**Câu 5.** Superclass constructor hay anonymous field initializer chạy trước?  
**Đáp án:** Superclass constructor.

**Câu 6.** Hai instance blocks có chạy theo thứ tự source không?  
**Đáp án:** Có, xen kẽ với field initializers theo thứ tự khai báo trong anonymous body.

**Câu 7.** Blank final field có thể gán trong instance initializer không?  
**Đáp án:** Có, phải tuân thủ definite assignment/không gán lại.

**Câu 8.** `new Runnable(5){...}` có hợp lệ không?  
**Đáp án:** Không; interface Runnable không có constructor nhận arguments.

**Câu 9.** `new Base("X"){...}` có hợp lệ không?  
**Đáp án:** Có nếu Base class có accessible constructor phù hợp và các quy tắc subclassing hợp lệ.

**Câu 10.** Nếu superclass constructor throw thì anonymous block chạy không?  
**Đáp án:** Không chạy nếu superclass constructor chưa hoàn thành bình thường.

**Câu 11.** Tại sao method override gọi từ superclass constructor có thể thấy field = 0?  
**Đáp án:** Java dynamic dispatch xảy ra trước anonymous field initializer, nên field còn default.

**Câu 12.** `int first=this.second; int second=7;` có thể cho first bao nhiêu?  
**Đáp án:** `first=0`, vì field second chưa được gán 7 tại thời điểm đọc.

**Câu 13.** `int first=second; int second=7;` dùng simple name trước declaration có hợp lệ không?  
**Đáp án:** Bị giới hạn bởi JLS §8.3.3; trường hợp này là compile-time forward-reference error.

**Câu 14.** Gọi method `readSecond()` từ field initializer có tự hoàn tất mọi initializers chưa?  
**Đáp án:** Không. Method có thể đọc default values của các fields còn lại.

**Câu 15.** Anonymous initializer có thể throw IOException không?  
**Đáp án:** Có. Compiler đưa checked exception vào `throws` của anonymous constructor ngầm.

**Câu 16.** Ai phải catch/declare IOException từ initializer?  
**Đáp án:** Creation expression context/caller method theo exception-checking rules.

**Câu 17.** Có thể khai `public void run() throws IOException` khi implement Runnable không?  
**Đáp án:** Không, vì vượt checked exceptions được phép bởi `Runnable.run()`.

**Câu 18.** `this` trong anonymous class là Outer object không?  
**Đáp án:** Không; `this` là anonymous object.

**Câu 19.** Đọc enclosing Outer field khi hợp lệ bằng cú pháp nào?  
**Đáp án:** `Outer.this.field` hoặc resolution phù hợp, nếu có enclosing Outer instance.

**Câu 20.** `final StringBuilder builder` bảo vệ builder khỏi mutation không?  
**Đáp án:** Không. Nó cố định reference nhưng builder object vẫn mutable.

**Câu 21.** Đưa `this` vào registry trong initializer có thể gây rủi ro gì?  
**Đáp án:** Object có thể bị quan sát trước khi khởi tạo hoàn tất; cần hạn chế escape.

**Câu 22.** Có thể viết `return;` trực tiếp trong instance initializer block không?  
**Đáp án:** Không, JLS §8.6 cấm return statement.

**Câu 23.** Anonymous block có thể chỉ gồm một `throw` luôn xảy ra không?  
**Đáp án:** Nếu block không thể hoàn thành bình thường theo compile-time reachability, bị từ chối.

**Câu 24.** Nếu cần nhiều constructor overloads và public API, anonymous class hay named class?  
**Đáp án:** Named class thường phù hợp.

**Câu 25.** Nếu chỉ cần callback đơn giản, có field initializer/instance block cần thiết không?  
**Đáp án:** Thường có thể dùng lambda và captured values; không bắt buộc anonymous.

**Câu 26.** Tại sao log `after-new` in sau initializer logs?  
**Đáp án:** Expression tạo object phải hoàn tất trước khi statement tiếp theo chạy.

**Câu 27.** Mỗi lần gọi factory tạo anonymous instance có chạy initializer không?  
**Đáp án:** Có, mỗi lần thực hiện `new` thành công.

**Câu 28.** Vì sao type của biến `Runnable action` không công khai private fields của anonymous class?  
**Đáp án:** Compile-time type của biến là Runnable và private members không thuộc interface API.

**Câu 29.** Có thể đăng ký listener sau khi object đã build xong không?  
**Đáp án:** Có, và thường an toàn hơn khi initializer không làm `this` escape.

**Câu 30.** Thứ tự tổng quát cần thuộc lòng?  
**Đáp án:** **Constructor arguments → cấp phát/defaults → superclass constructor → anonymous field/instance initializers theo source order → hoàn tất creation → caller sử dụng object**.

## 34. Tài liệu tham khảo

- Java Language Specification (Java SE 17), [§15.9.5 — Anonymous Class Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5): khai báo anonymous class và class body được phép.
- Java Language Specification, [§15.9.5.1 — Anonymous Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5.1): implicit constructor, superclass arguments và checked exception list.
- Java Language Specification, [§12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): thứ tự constructor/instance field initializers và blocks.
- Java Language Specification, [§8.3.2 — Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): field initializer semantics.
- Java Language Specification, [§8.3.3 — Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3): self/forward references.
- Java Language Specification, [§8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): initializer blocks và hạn chế return.
- Java Language Specification, [§11.2.3 — Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3): checked exception đặc biệt của anonymous instance initializers.
- Java Language Specification, [§15.9.3 — Choosing Constructor and Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.3): chọn constructor của superclass.
- Java Language Specification, [§15.9.4 — Run-Time Evaluation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.4): cách đánh giá creation expression.
- Java Language Specification, [§8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): anonymous class là inner class.
- Java Language Specification, [§4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): final local variables/fields.
- Java Language Specification, [§16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): blank final fields.

## Tổng kết

**Anonymous class không có constructor tường minh mang tên**, nhưng vẫn được Java compiler cấp một **anonymous constructor ngầm** để tạo object và gọi constructor của superclass. Trong anonymous class body, lập trình viên có thể dùng **instance field initializers** và **instance initializer blocks** để thiết lập fields, gán `final` state, validation và thực hiện các bước khởi tạo hợp lệ.

Thứ tự khởi tạo quyết định kết quả: superclass constructor chạy trước, sau đó field initializers/instance blocks của anonymous class chạy **theo thứ tự xuất hiện**. Nếu superclass constructor gọi method được override quá sớm, override có thể quan sát fields còn giá trị mặc định. Nếu initializer throw exception, creation không thành công; checked exceptions vẫn được compiler xử lý qua anonymous constructor ngầm và creation site phải catch/declare.

Hãy giữ initializer **nhỏ, rõ dependency, không công bố `this` trước khi xây xong**. Với logic resource/constructor phức tạp, ưu tiên named class hoặc factory. Với callback đơn giản, lambda có thể gọn hơn. Hiểu đúng **constructor ngầm + field initializer + instance block + superclass order** là chìa khóa đọc và viết anonymous classes chính xác trong Java 17+.
