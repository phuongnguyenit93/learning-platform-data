# Java luôn truyền tham trị: mô hình bản sao giá trị đối số

Trong Java, **mọi lời gọi phương thức và constructor đều truyền đối số theo giá trị (*pass by value*)**. Điều đó đúng cho cả `int`, `double`, `boolean` lẫn đối tượng như `Student`, `List` và mảng. Sự khác biệt nằm ở **giá trị nào được sao chép**: với kiểu nguyên thủy là chính giá trị số/logic; với kiểu tham chiếu là **giá trị tham chiếu tới đối tượng**, không phải bản sao toàn bộ đối tượng.

Quy tắc này giải thích ba hiện tượng tưởng như mâu thuẫn:

- Thay đổi một tham số kiểu `int` **không** thay đổi biến `int` của bên gọi.
- Gán lại tham số kiểu `Student` để nó trỏ sang object mới **không** đổi biến `Student` của bên gọi.
- Gọi `student.setName(...)` qua tham số có thể **làm thay đổi object** mà bên gọi vẫn đang tham chiếu.

Bài này trình bày cơ chế bản sao giá trị đối số, các ví dụ Java 17+ chạy được, ảnh hưởng của alias, mảng, `String`, wrapper, `final`, varargs, cách trả kết quả và những lỗi thường gặp.

## 1. Tách bốn khái niệm: biến, giá trị, tham chiếu, đối tượng

Trước hết phân biệt:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Biến (*variable*) | `int n`, `Box box` | Vị trí có kiểu dùng để chứa một giá trị |
| Giá trị nguyên thủy | `7`, `true` | Giá trị của một kiểu primitive |
| Giá trị tham chiếu | Giá trị đang nằm trong `Box box` | Tham chiếu tới một object, hoặc `null` |
| Đối tượng (*object*) | Kết quả của `new Box(10)` | Thực thể có trạng thái instance riêng |

Ví dụ:

~~~java
int n = 7;
Box first = new Box(10);
Box alias = first;
~~~

Đây là đoạn minh họa giả định có lớp `Box`. Biến `n` chứa giá trị số nguyên `7`. Biến `first` chứa **một giá trị tham chiếu** đến object được tạo. Phép gán `alias = first` sao chép tham chiếu; nó **không tạo một Box mới**.

Khi gọi `f(n)` hoặc `g(first)`, Java đánh giá biểu thức đối số rồi chuyển **giá trị thu được** sang một biến tham số mới trong lời gọi. **Không có quy tắc truyền trực tiếp “biến của caller” vào để callee gán lại nó.**

Một cách nói chính xác: *Java pass-by-value, including reference values*. Không phải “primitive pass-by-value còn object pass-by-reference” theo nghĩa truyền biến của người gọi bằng tham chiếu.

## 2. Mô hình bản sao giá trị khi gọi phương thức

Xét một phương thức:

~~~java
static void examine(int number, Box item) {
    // number và item là các biến tham số của lời gọi hiện tại.
}
~~~

Và lời gọi:

~~~java
int score = 7;
Box current = new Box(10);
examine(score, current);
~~~

Đây là các đoạn minh họa, chưa phải chương trình độc lập. Mô hình khái niệm:

~~~text
BÊN GỌI                       BÊN ĐƯỢC GỌI
-----------------------       -------------------------
score  [giá trị int: 7] ----> number  [bản sao int: 7]

current [tham chiếu R] ------> item    [bản sao tham chiếu R]
                  |                             |
                  +------------+----------------+
                               |
                               v
                       Một object Box
                       [value = 10]
~~~

**Điều được sao chép** là giá trị đang nằm trong biến hoặc kết quả biểu thức. Hai biến tham chiếu `current` và `item` là **hai biến khác nhau**, nhưng có thể chứa **cùng giá trị tham chiếu R**, tức cùng chỉ tới **một object**.

Vì thế cần tách hai thao tác:

1. **Gán lại biến tham số:** `item = new Box(20)` chỉ thay đổi giá trị tham chiếu chứa trong **biến `item`** của callee.
2. **Thay đổi object qua tham chiếu:** `item.add(5)` truy cập object mà `item` chỉ đến và sửa field bên trong object ấy; caller có thể nhìn thấy sự thay đổi khi vẫn giữ tham chiếu tới cùng object.

Mô hình này là **ngữ nghĩa Java**, không khẳng định cách JVM cụ thể bố trí biến/tham chiếu trong thanh ghi hay bộ nhớ vật lý.

## 3. Với kiểu nguyên thủy: tham số là biến riêng

Tạo tệp hoàn chỉnh **`PrimitiveValueDemo.java`**:

~~~java
public class PrimitiveValueDemo {
    static void change(int number) {
        System.out.println("inside before=" + number);
        number = 99;
        System.out.println("inside after=" + number);
    }

    static void flip(boolean enabled) {
        enabled = !enabled;
        System.out.println("inside flag=" + enabled);
    }

    public static void main(String[] args) {
        int score = 7;
        boolean active = true;

        change(score);
        System.out.println("outside number=" + score);

        flip(active);
        System.out.println("outside flag=" + active);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 PrimitiveValueDemo.java
java PrimitiveValueDemo
~~~

**Stdout chính xác:**

~~~text
inside before=7
inside after=99
outside number=7
inside flag=false
outside flag=true
~~~

`change(score)` truyền giá trị `7` vào biến tham số `number`. Trong phương thức, `number = 99` chỉ sửa **tham số**; nó không sửa `score`.

Tương tự, `flip(active)` nhận bản sao `true`, đổi tham số thành `false` và in giá trị mới. Biến `active` bên gọi vẫn là `true`.

Đây không phải “Java ngăn mọi phương thức thay đổi dữ liệu bên ngoài”: phương thức vẫn có thể cập nhật trường của object được truyền vào, trường `static`, tệp hoặc database. Ví dụ chỉ chứng minh **phép gán lại tham số nguyên thủy không làm thay đổi biến đối số của caller**.

## 4. Với kiểu tham chiếu: sao chép tham chiếu, không sao chép object

Tạo tệp độc lập **`ReferenceValueDemo.java`**:

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void add(int amount) {
        value = Math.addExact(value, amount);
    }

    int value() {
        return value;
    }
}

public class ReferenceValueDemo {
    static void mutate(Counter counter) {
        counter.add(5);
        System.out.println("inside mutate=" + counter.value());
    }

    static void replace(Counter counter) {
        counter = new Counter(100);
        counter.add(1);
        System.out.println("inside replace=" + counter.value());
    }

    static void clear(Counter counter) {
        counter = null;
        System.out.println("inside clear=" + counter);
    }

    public static void main(String[] args) {
        Counter original = new Counter(10);
        Counter alias = original;

        System.out.println("before=" + original.value());

        mutate(original);
        System.out.println("after mutate=" + original.value());

        replace(original);
        System.out.println("after replace=" + original.value());

        clear(original);
        System.out.println("caller nonnull=" + (original != null));
        System.out.println("same instance=" + (original == alias));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ReferenceValueDemo.java
java ReferenceValueDemo
~~~

**Stdout:**

~~~text
before=10
inside mutate=15
after mutate=15
inside replace=101
after replace=15
inside clear=null
caller nonnull=true
same instance=true
~~~

Ba phương thức làm những việc rất khác nhau:

### `mutate(original)`: sửa object được chia sẻ

Khi `mutate` bắt đầu, tham số `counter` là một biến mới nhưng chứa **tham chiếu tới cùng Counter** mà `original` đang trỏ đến. `counter.add(5)` sửa field `value` của object đó từ 10 thành 15. Vì vậy sau khi trở về `main`, `original.value()` là 15.

Đây là **tác dụng phụ lên object được tham chiếu**, không phải truyền biến `original` theo tham chiếu.

### `replace(original)`: chỉ thay tham chiếu của tham số

Trong `replace`:

~~~java
counter = new Counter(100);
counter.add(1);
~~~

Đây là trích đoạn từ phương thức ở trên. Dòng đầu tạo một object mới và gán **biến tham số `counter`** sang nó. Object mới tăng thành 101, nhưng biến `original` của `main` vẫn trỏ đến **object cũ** có giá trị 15. Vì vậy hai dòng output lần lượt là `inside replace=101` và `after replace=15`.

### `clear(original)`: gán null cho tham số, caller vẫn giữ object

`counter = null;` chỉ thay đổi tham số cục bộ của lời gọi; `original` không tự bị gán null. `original == alias` vẫn là `true` vì hai biến ở `main` vẫn giữ tham chiếu ban đầu.

**Kết luận:** một callee có thể **thay đổi trạng thái của object được chia sẻ**, nhưng không thể **gán lại chính biến tham chiếu ở caller** bằng việc gán lại tham số thông thường.

## 5. Sơ đồ trước–sau: mutate khác reassign

Trước lời gọi:

~~~text
main()
  original ------+
                 +----> Counter #1, value = 10
  alias ---------+

mutate(counter)
  counter ------------> Counter #1, value = 10
                           |
                           +-- add(5) --> value = 15
~~~

Sau `mutate`, cả `original` và `alias` nhìn thấy `Counter #1` có `value = 15`.

Trong `replace(counter)`:

~~~text
main()                              replace()
  original -----+                   counter -----+
                |                                 |
  alias --------+----> Counter #1, value = 15      |
                                                   |
                             counter = new Counter(100)
                                                   |
                                  counter --------+----> Counter #2
                                                         value = 100
                                  counter.add(1)        value = 101
~~~

Khi `replace` kết thúc, biến tham số không còn được sử dụng ở caller; `original` và `alias` vẫn chỉ tới `Counter #1`. Đối tượng #2 trong ví dụ có thể trở thành ứng viên garbage collection nếu không còn tham chiếu sống nào khác giữ nó; **không có bảo đảm JVM thu hồi ngay lập tức**.

Nhớ quy tắc:

- **Sao chép tham chiếu** không tạo bản sao object.
- **Gán lại một biến tham chiếu** không tự đổi các biến khác.
- **Sửa field qua một tham chiếu** có thể được nhìn thấy qua các alias cùng trỏ object đó.

## 6. Vì sao “object được truyền theo tham chiếu” là cách diễn đạt dễ sai?

Người học đôi khi nói “Java truyền object theo tham chiếu”, vì quan sát thấy bên gọi nhìn thấy thay đổi từ `counter.add(5)`. Cách diễn đạt này dễ dẫn tới suy luận sai rằng `counter = new Counter(...)` trong callee cũng đổi biến `original` của caller.

Trong thuật ngữ truyền tham số:

- **Pass by value**: callee nhận một **giá trị** trong biến tham số của mình.
- **Pass by reference** theo nghĩa biến của người gọi được truyền như một alias gán được: callee có thể đổi **chính biến bên gọi** bằng phép gán qua tham số.
- **Java áp dụng pass by value**. Với object, giá trị được truyền là **reference value**, không phải một object được sao chép.

Ví dụ phản chứng đơn giản:

~~~java
static void reset(Counter c) {
    c = null;
}
~~~

Nếu đây là truyền biến caller theo tham chiếu, gán `c = null` sẽ làm biến ở caller trở thành `null`; nhưng Java **không** có hành vi đó. Vì thế nói **“bản sao của giá trị tham chiếu”** là chính xác hơn.

Một số ngôn ngữ dùng thuật ngữ “call by sharing” để mô tả hệ quả hai phía chia sẻ object. Thuật ngữ đó có thể giúp trực giác, nhưng **không thay đổi cơ chế truyền đối số theo giá trị của Java**.

## 7. Mảng cũng là object: có thể sửa phần tử, không thể gán lại biến caller

Mảng trong Java là **object**. Khi truyền `int[]`, tham số nhận bản sao **tham chiếu tới mảng** chứ không sao chép mọi phần tử.

Tạo tệp **`ArrayValueDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayValueDemo {
    static void editFirst(int[] items) {
        items[0] = 42;
    }

    static void replaceArray(int[] items) {
        items = new int[] {9, 9, 9};
        System.out.println("inside replacement=" + Arrays.toString(items));
    }

    static void appendText(String text) {
        text = text + "!";
        System.out.println("inside text=" + text);
    }

    static void appendBuilder(StringBuilder builder) {
        builder.append("!");
    }

    public static void main(String[] args) {
        int[] values = {1, 2};
        editFirst(values);
        System.out.println("after edit=" + Arrays.toString(values));

        replaceArray(values);
        System.out.println("after replacement=" + Arrays.toString(values));

        String message = "Java";
        appendText(message);
        System.out.println("outside text=" + message);

        StringBuilder builder = new StringBuilder("Java");
        appendBuilder(builder);
        System.out.println("outside builder=" + builder);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ArrayValueDemo.java
java ArrayValueDemo
~~~

**Stdout:**

~~~text
after edit=[42, 2]
inside replacement=[9, 9, 9]
after replacement=[42, 2]
inside text=Java!
outside text=Java
outside builder=Java!
~~~

Giải thích:

1. `editFirst(values)` nhận một bản sao tham chiếu tới **cùng mảng** và gán `items[0] = 42`. Caller thấy `[42, 2]`.
2. `replaceArray(values)` tạo một mảng mới rồi gán cho **biến `items` bên trong**. Mảng của `values` ở caller không bị thay thế.
3. `String` là **bất biến**. `text = text + "!"` tạo/nhận một giá trị chuỗi mới để gán lại biến tham số, không sửa nội dung object `String` mà `message` trỏ tới.
4. `StringBuilder` là **mutable**. `builder.append("!")` sửa chính object mà cả caller và callee đang cùng tham chiếu; caller đọc được `Java!`.

**Không nên nói Java “copy cả mảng khi truyền tham số”.** Sao chép mảng phải là một thao tác riêng, chẳng hạn `Arrays.copyOf`, `clone()` trên mảng hoặc một chiến lược sao chép phù hợp.

## 8. Trường hợp `String`: truyền tham trị không có ngoại lệ

`String` thường gây bối rối vì có kiểu tham chiếu nhưng hành xử giống “giá trị” khi ghép chuỗi:

~~~java
static void makeLoud(String message) {
    message = message.toUpperCase();
}
~~~

Đây là đoạn phương thức minh họa. Nếu caller viết:

~~~java
String title = "java";
makeLoud(title);
System.out.println(title); // java
~~~

thì `title` vẫn là `"java"`. Phương thức `toUpperCase()` trả một `String` thích hợp, còn phép gán lại `message` chỉ thay **tham số**. Không thể chỉnh nội dung của một `String` đã tồn tại bằng cách thay trường ký tự của nó qua API chuẩn, vì `String` bất biến.

Nếu muốn caller nhận kết quả, hãy **trả giá trị về**:

~~~java
static String makeLoud(String message) {
    return message.toUpperCase();
}

// Ở caller:
String title = "java";
title = makeLoud(title);
System.out.println(title); // JAVA
~~~

Hai ví dụ khai báo `makeLoud` trên là **hai phiên bản thay thế để so sánh**, không được đặt cùng lúc trong cùng lớp vì chỉ đổi kiểu trả về không tạo overload hợp lệ. Đoạn sau thể hiện quy tắc: **caller chủ động gán lại biến của chính mình bằng kết quả trả về**.

Đây không phải cách “lách” pass-by-value; nó là giao tiếp rõ ràng giữa phương thức và nơi gọi thông qua `return`.

## 9. Wrapper và autoboxing: phép gán lại vẫn chỉ xảy ra trong callee

Wrapper như `Integer`, `Long`, `Boolean` là **kiểu tham chiếu**, và các instance biểu diễn giá trị của chúng là **bất biến** theo API. Xét:

~~~java
static void increase(Integer value) {
    value++;
}
~~~

Đây là đoạn minh họa. Nếu có:

~~~java
Integer count = Integer.valueOf(10);
increase(count);
System.out.println(count); // 10
~~~

`value++` bao gồm thao tác **unboxing**, tăng giá trị và **boxing** kết quả rồi gán lại biến tham số `value`; không chỉnh sửa object wrapper ban đầu và không gán lại biến `count` của caller.

Trong thực tế, tránh dùng wrapper chỉ để kỳ vọng nó đóng vai trò “tham số đầu ra”. Wrapper `Integer` còn có thể `null`, và unboxing một giá trị null gây `NullPointerException`.

Lưu ý `Integer x = 5;` khi truyền sang tham số kiểu `int` có thể được unbox trong quá trình tương thích đối số; tham số nhận **giá trị nguyên thủy** sau chuyển đổi. Các chuyển đổi boxing/unboxing không làm biến caller trở thành alias có thể gán lại.

## 10. Vì sao viết hàm `swap(a,b)` không đổi được hai biến tham chiếu ở caller?

Một phép thử ngắn cho quy tắc truyền tham trị:

~~~java
static void swap(Object left, Object right) {
    Object temporary = left;
    left = right;
    right = temporary;
}
~~~

Nếu caller có hai biến `a` và `b` đang trỏ hai object khác nhau, gọi `swap(a, b)` **không đảo hai biến caller**. Hai tham số `left`, `right` là **bản sao của hai giá trị tham chiếu**; ba phép gán chỉ hoán đổi hai biến cục bộ trong callee.

Hãy vẽ hai cột: biến caller (`a`, `b`) và biến callee (`left`, `right`). Sau mỗi phép gán, cột caller giữ nguyên. Muốn sửa hai slot của mảng/list chung thì có thể đổi **phần tử của container**; muốn đổi hai local variables thì chính caller phải gán lại từ kết quả.

Bài chuyên sâu về hoán đổi tham chiếu trong chương sẽ truy vết từng dòng và so sánh các giải pháp array, list, holder, record kết quả. Ở bài tổng quan, chỉ cần nắm quy tắc: **gán lại tham số không gán lại biến của caller**.

## 11. Nếu muốn kết quả làm thay đổi biến caller, phải làm thế nào?

Khi API muốn gửi về một giá trị mới, thường nên **return** kết quả để nơi gọi quyết định gán:

~~~java
static int doubled(int value) {
    return Math.multiplyExact(value, 2);
}

// Bên gọi:
int score = 7;
score = doubled(score); // score trở thành 14
~~~

Đây là đoạn minh họa trong lớp; `Math.multiplyExact` sẽ ném `ArithmeticException` nếu phép nhân nguyên tràn số.

Với kiểu tham chiếu:

~~~java
static String addSuffix(String source) {
    return source + "!";
}

// Bên gọi:
String name = "An";
name = addSuffix(name); // caller gán lại biến của chính nó
~~~

Nếu phương thức cần trả **nhiều kết quả**, cân nhắc tạo kiểu kết quả rõ ràng như một `record`:

~~~java
record DivisionResult(int quotient, int remainder) {
}

static DivisionResult divide(int a, int b) {
    return new DivisionResult(a / b, a % b);
}
~~~

Hai khai báo thuộc ngữ cảnh lớp thích hợp; `divide` giả định `b != 0`, nếu bằng 0 sẽ ném `ArithmeticException`. Java 17 hỗ trợ `record` như một cách ngắn gọn biểu diễn nhiều giá trị kết quả.

Các API có thể chủ ý **sửa một object mutable truyền vào**, chẳng hạn `List.add`, `Collections.sort`, hoặc một `StringBuilder`. Hãy mô tả rõ tác dụng phụ trong hợp đồng, không sử dụng mutable holder chỉ để giả lập truyền biến theo tham chiếu khi một giá trị trả về sẽ đơn giản hơn.

## 12. Dùng object chứa kết quả: có thể sửa nội dung, không thay biến caller

Nếu thật sự cần cho callee cập nhật một đối tượng chứa dữ liệu, caller có thể tạo container:

~~~java
class IntHolder {
    int value;

    IntHolder(int value) {
        this.value = value;
    }
}

static void increment(IntHolder holder) {
    holder.value++;
}
~~~

Đây là những khai báo minh họa đặt trong cấu trúc Java hợp lệ. Bên gọi:

~~~java
IntHolder holder = new IntHolder(10);
increment(holder);
System.out.println(holder.value); // 11
~~~

Điều này hoạt động vì phương thức sửa **field `value` của cùng object**. Nó **không chứng minh Java đã chuyển sang pass-by-reference**: biến tham số `holder` vẫn là bản sao tham chiếu và nếu callee gán `holder = new IntHolder(0)` thì caller không tự trỏ tới object mới.

Một wrapper chuyên dùng như `AtomicInteger` có API cập nhật giá trị và quy tắc đồng thời riêng, nhưng không phải “tham số số nguyên truyền theo tham chiếu” của Java. Chỉ chọn container khi thiết kế API thật sự cần identity, chia sẻ trạng thái hoặc cơ chế cập nhật của nó.

## 13. Constructor cũng nhận bản sao giá trị đối số

Quy tắc pass-by-value áp dụng khi gọi **constructor**, không chỉ method:

~~~java
class Student {
    private final String name;
    private final int grade;

    Student(String name, int grade) {
        this.name = name;
        this.grade = grade;
    }
}
~~~

Đây là lớp minh họa. Với `new Student(title, level)`, các tham số constructor `name` và `grade` nhận giá trị đối số theo cùng cơ chế như method. `this.name = name` và `this.grade = grade` là phép gán **vào field của object đang khởi tạo**, không phải gán lại biến `title` hay `level` bên caller.

Nếu một constructor lưu thẳng tham chiếu mutable:

~~~java
class Scores {
    private final int[] points;

    Scores(int[] points) {
        this.points = points;
    }
}
~~~

thì field `this.points` nhận **bản sao giá trị tham chiếu** tới **cùng mảng** mà caller đã truyền. Caller còn giữ mảng và có thể sửa phần tử của mảng đó. `final` ở field chỉ ngăn **gán lại tham chiếu field**, không tạo bản sao nội dung mảng.

Nếu class cần sở hữu dữ liệu độc lập, hãy cân nhắc sao chép phòng vệ:

~~~java
Scores(int[] points) {
    this.points = java.util.Arrays.copyOf(points, points.length);
}
~~~

Đây là **phiên bản constructor thay thế**, không thể cùng tồn tại với constructor `Scores(int[])` phía trên trong một lớp. Nó sao chép các phần tử `int` sang mảng mới; với mảng chứa object mutable, sao chép phần tử chỉ là **shallow copy** trừ khi còn sao chép từng object con.

## 14. `final` ở tham số không làm thay đổi cơ chế truyền

Có thể khai báo:

~~~java
static void show(final Counter counter) {
    System.out.println(counter.value());
    // counter = new Counter(10); // Lỗi compile: không gán lại tham số final.
}
~~~

`final` **ngăn gán lại chính biến tham số**, nhưng vẫn có thể gọi `counter.add(1)` nếu tham chiếu khác null và API cho phép. Nó không làm object trở thành bất biến, cũng không chuyển cách truyền tham số sang pass-by-reference.

Ví dụ:

~~~java
static void increment(final Counter counter) {
    counter.add(1); // Hợp lệ: không gán lại biến counter.
}
~~~

Trường `final`, biến cục bộ `final`, tham số `final` đều có quy tắc không gán lại tương ứng; chúng không tự sao chép đối tượng được tham chiếu.

**Nhận xét thiết kế:** đôi khi đánh dấu tham số `final` giúp phát hiện việc gán lại nhầm trong thân phương thức. Nhưng việc dùng hay không dùng `final` thường là quy ước mã nguồn, không phải sự khác biệt về ngữ nghĩa truyền tham số.

## 15. `null` cũng là một giá trị tham chiếu được truyền theo giá trị

Khi viết:

~~~java
static void set(Counter counter) {
    counter = new Counter(5);
}

Counter ref = null;
set(ref);
System.out.println(ref == null); // true
~~~

Đây là đoạn minh họa trong ngữ cảnh có lớp `Counter`. Giá trị của `ref` khi gọi là `null`; tham số `counter` nhận **bản sao null**. Phương thức tạo object và gán biến tham số, không gán lại `ref` của caller.

Ngược lại:

~~~java
static void use(Counter counter) {
    counter.add(1);
}
~~~

Nếu caller truyền `null`, `counter.add(1)` ném `NullPointerException` khi cố gọi instance method qua tham chiếu null. Đây là vấn đề **precondition và xử lý null**, không phải bằng chứng về một cơ chế truyền đối số khác.

Để API rõ ràng, có thể dùng `Objects.requireNonNull(counter)` hoặc một quy tắc hợp lệ khác trước khi truy cập object; cần thống nhất chuyện null là đầu vào sai hay một trạng thái hợp lệ.

## 16. Varargs cũng hoạt động theo giá trị: tham số là một mảng

Khai báo:

~~~java
static int sum(int... numbers) {
    int result = 0;
    for (int number : numbers) {
        result = Math.addExact(result, number);
    }
    return result;
}
~~~

Bên trong, `numbers` là biến tham số kiểu **`int[]`**, và giá trị của nó là **tham chiếu đến mảng**.

Người gọi có thể:

~~~java
sum();                 // Không phần tử: 0.
sum(2, 3);             // Hai phần tử: 5.
sum(new int[] {2, 3}); // Truyền mảng có sẵn: 5.
~~~

Khi gọi bằng các đối số rời `sum(2,3)`, Java xử lý lời gọi variable arity bằng một mảng tham số thích hợp. Khi truyền sẵn mảng có kiểu phù hợp `sum(array)`, lời gọi có thể chuyển trực tiếp **tham chiếu mảng của caller** vào tham số. Trong cả hai trường hợp, **giá trị được truyền cho tham số là một reference value** theo quy tắc Java.

Điểm cần chú ý nếu phương thức sửa `numbers[0]`: với mảng do caller cung cấp, caller có thể nhìn thấy thay đổi; với đối số rời, caller không có biến mảng gốc để quan sát. Nhưng gán `numbers = new int[]{...}` trong callee vẫn **không** thay đổi biến mảng của caller.

Gọi `sum()` tạo một tham số mảng rỗng theo ngữ nghĩa varargs thông thường, **không phải** mặc định truyền `null`. Người gọi vẫn có thể cố ý truyền `sum((int[]) null)`; nếu thân duyệt `numbers` ngay, nó sẽ gặp `NullPointerException`.

## 17. Cách đối số được đánh giá trước khi truyền giá trị

Khi gọi một phương thức, Java cần **đánh giá các biểu thức đối số** để có giá trị thực tế. Theo quy tắc ngôn ngữ, các biểu thức đối số được đánh giá **từ trái sang phải** trong các lời gọi thông thường. Nếu một biểu thức đối số gây tác dụng phụ, tác dụng phụ ấy xảy ra **tại bên gọi trong lúc đánh giá**, không phải vì callee đã được trao biến caller bằng tham chiếu.

Ví dụ tệp độc lập **`ArgumentEvaluationDemo.java`**:

~~~java
public class ArgumentEvaluationDemo {
    static int next(int[] counter) {
        counter[0]++;
        System.out.println("evaluated=" + counter[0]);
        return counter[0];
    }

    static void receive(int first, int second) {
        first = 100;
        System.out.println("received=" + first + "," + second);
    }

    public static void main(String[] args) {
        int[] state = {0};
        receive(next(state), next(state));
        System.out.println("caller state=" + state[0]);
    }
}
~~~

Chạy:

~~~bash
javac ArgumentEvaluationDemo.java
java ArgumentEvaluationDemo
~~~

**Stdout:**

~~~text
evaluated=1
evaluated=2
received=100,2
caller state=2
~~~

Từng bước:

1. Java đánh giá `next(state)` thứ nhất, tăng phần tử `state[0]` thành 1, in `evaluated=1` và cho ra giá trị đối số `1`.
2. Tiếp tục đánh giá `next(state)` thứ hai, tăng `state[0]` thành 2, in `evaluated=2` và cho ra `2`.
3. `receive` nhận **hai giá trị số nguyên đã được đánh giá**, `first=1` và `second=2`. Gán `first=100` chỉ đổi tham số.
4. Bên caller, `state[0]` là 2 vì **hai lời gọi `next` đã sửa mảng** trong lúc đánh giá đối số.

Đây là chi tiết quan trọng: **“pass by value” không có nghĩa đánh giá đối số không gây side effect**. Nó chỉ mô tả cách giá trị sau khi đánh giá được chuyển vào tham số.

Các phép chuyển đổi đối số hợp lệ như widening primitive, boxing/unboxing hoặc xử lý varargs có thể xảy ra theo quy tắc lời gọi; không biến lời gọi thành truyền biến caller bằng tham chiếu.

## 18. Generic method không thay đổi quy tắc này

Ví dụ:

~~~java
static <T> void reassign(T element, T replacement) {
    element = replacement;
}
~~~

Đây là một phương thức generic minh họa. Nếu `T` là `String`, `Student` hoặc `List<String>`, phép gán `element = replacement` chỉ gán lại **biến tham số `element`** trong lời gọi; nó không đổi biến bên caller.

Nếu `T` đại diện cho một object mutable và phương thức gọi hành vi sửa object ấy (qua API phù hợp), tác dụng phụ có thể xuất hiện. Generic chỉ làm cách diễn đạt **kiểu dữ liệu** tổng quát hơn, không đưa vào cơ chế pass-by-reference.

Một lambda hoặc method reference nhận tham số cũng không thay đổi quy tắc: những giá trị argument vẫn được truyền cho các formal parameters theo ngữ nghĩa Java. Nếu lambda giữ tham chiếu tới object bên ngoài, nó có thể chia sẻ object đó; đây là vấn đề **alias và capture**, không phải truyền biến qua tham chiếu có thể gán lại.

## 19. Dùng đối tượng chia sẻ không đồng nghĩa thread-safe

Khi callee và caller cùng giữ tham chiếu tới một object mutable, cả hai có thể thao tác trên state của object. Trong môi trường nhiều luồng, **việc tham chiếu giống nhau không bảo đảm phép đọc/ghi an toàn**.

Ví dụ:

~~~java
class SharedCount {
    int value;

    void increment() {
        value++;
    }
}
~~~

Đây là đoạn lớp minh họa. Nếu hai luồng cùng có tham chiếu tới **một `SharedCount`**, cả hai có thể cập nhật trường `value` trong cùng object. Phép `value++` không phải chuỗi đọc–tính–ghi nguyên tử; có thể mất lần tăng hoặc gặp vấn đề visibility nếu không đồng bộ.

Tránh nhầm:

- **Copy giá trị tham chiếu:** hai tham số/biến có thể cùng trỏ object.
- **Chia sẻ object mutable:** thay đổi có thể được nhìn thấy bởi nhiều người giữ tham chiếu.
- **Memory visibility/thread safety:** muốn đảm bảo cách quan sát/thao tác giữa các luồng, cần cơ chế đồng bộ, atomic hoặc ownership thích hợp.

**Không suy ra từ “Java truyền tham trị” rằng object sẽ được sao chép cho mỗi luồng**. Java không làm như vậy trong lời gọi phương thức thông thường.

## 20. Khi nào nên dùng trả về, khi nào nên cho sửa object?

Hai phong cách API đều hợp lệ nhưng phục vụ mục đích khác nhau:

| Mục tiêu | Hướng thiết kế thường phù hợp | Ví dụ |
| --- | --- | --- |
| Tính một giá trị mới từ dữ liệu đầu vào | Trả kết quả, không sửa input | `int next = doubled(current)` |
| Tạo chuỗi mới | Trả `String` | `name = normalize(name)` |
| Cập nhật trạng thái domain object | Phương thức instance có precondition rõ | `account.deposit(amount)` |
| Thay đổi các phần tử của mảng/list được truyền | Nêu rõ tác dụng phụ trong tên/Javadoc | `sortInPlace(items)` |
| Cần nhiều kết quả | `record`/result object | `DivisionResult` |
| Cần chia sẻ trạng thái có lifecycle rõ | Holder/domain object hợp lý | `Counter` |
| Cần độc lập dữ liệu mutable đầu vào | Sao chép phù hợp rồi lưu/sử dụng | `Arrays.copyOf`, copy constructor |

Với một API nhận object mutable, cần ghi rõ liệu phương thức **chỉ đọc**, **có thể sửa**, **lưu lại tham chiếu**, hay **sao chép nội dung**. Quy tắc pass-by-value không tự quyết định các lựa chọn này.

**Ví dụ hợp đồng:** `void sortInPlace(List<String> items)` nói rõ hàm thay đổi danh sách được truyền; `List<String> sortedCopy(List<String> items)` gợi ý trả kết quả mới và không đổi thứ tự danh sách input. Cần kiểm thử và tài liệu hóa hành vi, không chỉ dựa vào tên.

## 21. Những hiểu nhầm phổ biến

| Hiểu nhầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Primitive truyền tham trị, object truyền tham chiếu” | Dễ ngụ ý callee gán lại biến caller được | **Mọi đối số đều truyền giá trị**; với object là reference value |
| “Truyền object là copy toàn bộ object” | Chỉ tham chiếu được sao chép | Hai bên có thể nhìn cùng object |
| “Gán `param = new Object()` sẽ đổi biến caller” | Chỉ gán lại biến tham số | Caller cần nhận và gán kết quả trả về |
| “Gọi `param.setX(...)` là pass-by-reference” | Là sửa object được chia sẻ | Không phải gán lại biến caller |
| “Mảng tự sao chép khi truyền” | Mảng là object, truyền giá trị tham chiếu | Dùng `Arrays.copyOf` khi muốn mảng khác |
| “String là ngoại lệ và được truyền tham chiếu thật” | String bất biến; biến tham số vẫn độc lập | Trả String mới nếu cần đổi giá trị caller |
| “`Integer++` sẽ làm Integer caller thay đổi” | Unbox/increment/box rồi gán tham số | Wrapper bất biến; dùng return |
| “`final` nghĩa là truyền tham chiếu” | Chỉ ngăn gán lại biến tham số | Không đổi cách truyền |
| “Swap hai tham số object thì swap được hai biến caller” | Chỉ đổi hai biến cục bộ callee | Return kết quả hoặc sửa container chung |
| “Không có side effect khi pass-by-value” | Object/array được chia sẻ vẫn có thể bị sửa | Phân biệt tham số với đối tượng được tham chiếu |
| “`null` là một object để sao chép” | `null` là giá trị tham chiếu đặc biệt | Truyền bản sao null, không tạo object |
| “Pass-by-value đảm bảo an toàn đa luồng” | Cùng object mutable có thể bị chia sẻ | Cần thiết kế concurrency riêng |

Khi một thay đổi không xuất hiện ở bên gọi, hãy hỏi: **Phương thức gán lại biến tham số, hay sửa trạng thái của object mà cả hai cùng trỏ tới?** Khi thay đổi **có** xuất hiện, hãy theo dõi alias và xem bên nào giữ tham chiếu đến object bị sửa.

## 22. Tự kiểm tra kiến thức

**Câu 1 — Primitive.** Với `int x=3;`, gọi `f(x)` mà `f(int x)` gán `x=100`, giá trị `x` ở caller sau lời gọi là bao nhiêu?

**Câu 2 — Tham chiếu.** `Box a=new Box(10);` truyền vào `void update(Box p) { p.add(5); }`. Sau lời gọi, `a` vẫn trỏ cùng object chứ? Giá trị object có đổi không?

**Câu 3 — Reassignment.** Nếu `void reset(Box p) { p=new Box(0); }`, điều gì xảy ra với biến `a` của caller?

**Câu 4 — Null.** Nếu bên gọi có `Box a=null;` và `void init(Box x){x=new Box(1);}`, sau `init(a)`, `a` có còn null không?

**Câu 5 — Mảng.** `int[] nums={1,2};`, gọi `change(nums)` mà `change(int[] a)` thực hiện `a[0]=9`. `nums[0]` là bao nhiêu? Nếu thay thân bằng `a=new int[]{9,9}` thì sao?

**Câu 6 — String.** `String s="A";` và `void edit(String t){t+="B";}`. Sau `edit(s)`, `s` là gì? Muốn nhận `"AB"` phải làm thế nào?

**Câu 7 — Swap.** Tại sao phương thức `swap(Object x,Object y)` chỉ gán `x=y`, `y=temp` không hoán đổi biến ở caller? Truyền `Object[]` vào một phương thức đổi hai phần tử có khác không?

**Câu 8 — Wrapper.** `Integer count=10;` gọi `increase(count)` mà thân `value++`. Vì sao `count` vẫn là 10?

**Câu 9 — final.** Có thể gọi `counter.add(1)` qua tham số `final Counter counter` không? Có thể gán lại `counter = new Counter(0)` không?

**Câu 10 — Đánh giá đối số.** Với `receive(next(state),next(state))` ở chương trình trên, tại sao `state[0]` ở caller tăng 2 dù hai tham số của `receive` là primitive?

**Câu 11 — Sao chép.** Constructor nhận `List<String>` rồi lưu `this.items = items`. Có tạo bản sao list không? Nếu muốn tách list nội bộ khỏi caller cần làm gì?

**Câu 12 — Concurrency.** Hai luồng giữ hai biến tham chiếu riêng nhưng trỏ cùng `Counter`. Có hai bản sao object không? Có thể đồng thời tăng field mà không đồng bộ một cách an toàn không?

### Đáp án và lý do

1. Vẫn là 3: `f` chỉ nhận bản sao giá trị primitive.
2. `a` vẫn trỏ cùng object; `add(5)` sửa object đó, nên giá trị từ 10 thành 15.
3. `a` không đổi tham chiếu; chỉ tham số `p` trỏ object mới.
4. Vẫn null; `init` không thể tự gán lại biến `a`.
5. Với gán phần tử, `nums[0]=9`; với gán lại `a`, `nums[0]` vẫn là 1.
6. Vẫn `"A"`; cần phương thức trả String mới và caller gán `s=edit(s)`.
7. `x`, `y` là hai biến tham số riêng. Sửa phần tử của cùng object mảng thì caller thấy nội dung mảng thay đổi, nhưng các biến tham chiếu khác của caller không tự đổi.
8. `value++` tạo giá trị mới và gán tham số, wrapper `Integer` không bị sửa tại chỗ.
9. Gọi `add(1)` được nếu không null và API cho phép; gán lại `counter` bị compiler từ chối vì `final`.
10. Hai biểu thức `next(state)` sửa object mảng khi **đánh giá đối số**; `receive` chỉ nhận các giá trị nguyên thủy 1 và 2.
11. Không. Field chỉ nhận bản sao tham chiếu tới cùng list; cần sao chép danh sách phù hợp, ví dụ `new ArrayList<>(items)` hoặc `List.copyOf(items)` tùy hợp đồng, đồng thời xét phần tử mutable.
12. Chỉ có **một object được chia sẻ**; các phép cập nhật đồng thời cần thiết kế đồng bộ/atomic phù hợp.

## 23. Tài liệu đối chiếu

- [Java Language Specification 17, §15.12.4 — Run-Time Evaluation of Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4): đánh giá đối số và cách chuyển giá trị vào lời gọi.
- [Java Language Specification 17, §15.12.4.2 — Evaluate Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2): đánh giá biểu thức đối số từ trái sang phải.
- [Java Language Specification 17, §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1): tham số hình thức, varargs và modifier.
- [Java Language Specification 17, §4.12 — Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12): biến, giá trị và kiểu biến.
- [Java Language Specification 17, §10 — Arrays](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html): mảng là object và cách làm việc với mảng.

**Ghi nhớ:** Java **luôn truyền tham trị**. Với primitive, callee nhận **bản sao số/logic**. Với object và mảng, callee nhận **bản sao giá trị tham chiếu**, nên hai phía có thể cùng nhìn và sửa **một object** nhưng **không thể gán lại biến của nhau** chỉ thông qua phép gán tham số. Muốn thay giá trị biến ở caller, hãy trả kết quả để caller gán; muốn sửa trạng thái object dùng chung, hãy thiết kế và tài liệu hóa tác dụng phụ một cách có chủ đích.
