# Phân biệt bắt giữ giá trị biến với thay đổi trạng thái đối tượng được tham chiếu

**Module:** Java Core – class/object  
**Nhóm:** Lớp cục bộ (*local classes*)  
**Môi trường ví dụ:** Java 17+.

## 1. Kết luận cốt lõi trước khi học chi tiết

Khi một local class dùng một biến cục bộ hoặc tham số của phạm vi bao quanh, biến được **capture** phải là `final` hoặc **effectively final**. Với primitive variable, local class sử dụng primitive value. Với reference variable, local class sử dụng **giá trị reference trỏ đến object**. Không có quy tắc nào nói rằng object được tham chiếu phải immutable.

Bởi vậy, hai thao tác sau khác bản chất:

~~~java
StringBuilder text = new StringBuilder("A");

class Reader {
    String read() {
        return text.toString();
    }
}

text.append("B");             // HỢP LỆ: sửa object.
 // text = new StringBuilder("C"); // Không hợp lệ nếu bỏ chú thích.
~~~

Đây là **đoạn mã minh họa trong một method**, chưa phải chương trình độc lập. `text.append("B")` thay nội dung object nhưng không gán lại local variable `text`. Nếu bỏ chú thích phép gán `text = ...`, `text` mất tính effectively final và compiler không cho Reader capture.

Quy tắc cần ghi nhớ:

**Không gán lại biến cục bộ được local class capture** là một giới hạn ngôn ngữ.  
**Không thay đổi trạng thái object được tham chiếu** là một yêu cầu khác, chỉ có khi object/API/thiết kế ứng dụng quy định.

Bài học giải thích cơ chế capture qua primitive/reference, effectively final, aliasing, object lifetime, fields của outer class, arrays và collections, snapshot so với live reference, anonymous class/lambda, loops, concurrency, kiểm tra compile errors và những ví dụ chạy độc lập.

## 2. Local class là gì?

Local class là class được khai báo trong một block, thường gặp trong một method hoặc constructor:

~~~java
class Report {
    String format(String value) {
        String prefix = "Result";

        class Formatter {
            String render() {
                return prefix + ": " + value;
            }
        }

        return new Formatter().render();
    }
}
~~~

Đây là một **class fragment**, không có `main`. `Formatter` là local class. Nó sử dụng `prefix` (local variable) và `value` (method parameter). Cả hai không bị gán lại sau khi nhận giá trị, nên effectively final.

Local class:

- Có tên trong local lexical scope, không phải top-level public type.
- Có thể có instance fields, constructors, methods và methods triển khai interfaces.
- Có thể sử dụng những locals/parameters đủ điều kiện capture từ phạm vi bao quanh.
- Có thể tồn tại sau khi method khai báo nó trả về, nếu một instance còn reachable.
- Không tự tạo immutable snapshot của tất cả objects nó tham chiếu.
- Khác với **non-static member inner class**, class được khai báo trực tiếp ở member level; và khác với **static nested member class**.

Việc local class còn dùng được thông tin sau khi enclosing method kết thúc không có nghĩa JVM phải giữ nguyên stack frame của method. Compiler/runtime có thể hiện thực các captured values theo cách riêng; code phải dựa vào **semantics**, không dựa vào tên synthetic fields.

## 3. Java variable, value và object identity

Với reference variables:

~~~java
StringBuilder a = new StringBuilder("A");
StringBuilder b = a;
b.append("B");
System.out.println(a); // AB
~~~

Hai biến `a` và `b` có cùng **giá trị tham chiếu** và trỏ vào cùng một object:

~~~text
a ──┐
    ├──> StringBuilder object "A" ── append ──> "AB"
b ──┘
~~~

Phép gán `b = a` sao chép reference value, không sao chép object. Điều này là **aliasing**.

Với primitive:

~~~java
int a = 4;
int b = a;
b++;
System.out.println(a); // 4
System.out.println(b); // 5
~~~

Primitive variables `a` và `b` có các giá trị độc lập. Không có một `int object` chung để `b++` làm thay đổi `a`.

### 3.1. Ý nghĩa khi capture

Nếu local class capture `int offset = 4`, nó có thể sử dụng giá trị 4 khi chạy method của mình. Nếu local class capture `StringBuilder text`, nó giữ reference đến cùng mutable StringBuilder object mà caller hoặc code bao quanh có thể tiếp tục sửa.

Do đó một giá trị reference được giữ ổn định **không có nghĩa trạng thái referent luôn ổn định**.

### 3.2. `final` không đồng nghĩa immutable

~~~java
final StringBuilder builder = new StringBuilder("A");
builder.append("B");       // Hợp lệ.
builder.setCharAt(0, 'C');  // Hợp lệ.
// builder = new StringBuilder(); // Không hợp lệ.
~~~

`final` cấm gán lại local variable `builder`. Nó không cấm methods của StringBuilder sửa internal character sequence.

Điều tương tự áp dụng với:

- `final List<String> list = new ArrayList<>();` rồi `list.add(...)`.
- `final int[] numbers = {1};` rồi `numbers[0]++`.
- `final Map<String,Integer> map = new HashMap<>();` rồi `map.put(...)`.
- `final MutableBox box = new MutableBox(1);` rồi `box.value = 2`.

Với local class, biến có thể không khai báo từ khóa `final` nhưng vẫn **effectively final** nếu thỏa các rules về assignments.

## 4. Định nghĩa effectively final

Một local variable hoặc method/constructor parameter là *effectively final* khi theo rules Java, biến không bị gán lại trái điều kiện sau khi được khởi tạo phù hợp. Compiler xét cả flow của chương trình, không chỉ vài dòng trước local class.

Hợp lệ:

~~~java
int base = 10;

class Adder {
    int add(int x) {
        return x + base;
    }
}
~~~

`base` được gán một lần và không bị thay, nên Adder đọc được.

Cố ý **không biên dịch**:

~~~java
int base = 10;

class Adder {
    int add(int x) {
        return x + base;
    }
}

base = 20; // Mất effectively final.
~~~

Dù gán sau declaration class, việc reassignment làm captured variable không còn effectively final. Không có ngoại lệ “chỉ gán sau khi tạo local-class object thì được”.

Các phép `base++`, `++base`, `base += 1` hoặc `base = base + 1` đều thay chính local variable và có thể khiến capture bị compiler từ chối.

### 4.1. Không cần compile-time constant

~~~java
int base = Integer.parseInt("7");

class Adder {
    int add(int x) {
        return x + base;
    }
}
~~~

Hợp lệ nếu base không bị gán lại. Kết quả của `Integer.parseInt` được tính lúc chạy, không phải constant expression; *effectively final* khác với *compile-time constant*.

### 4.2. Một số biến chưa có initializer vẫn có thể effectively final

~~~java
int selected;
if (flag) {
    selected = 10;
} else {
    selected = 20;
}

class Reader {
    int read() {
        return selected;
    }
}
~~~

Đây là **fragment** giả định `flag` đã được khai báo. Các paths gán selected phù hợp trước khi dùng; theo rules về definite assignment/effectively final, cách này có thể hợp lệ. Đừng suy rằng chỉ biến có initializer ngay tại declaration mới capture được.

### 4.3. Capture không làm biến reference chuyển thành immutable object

~~~java
List<String> values = new ArrayList<>();

class Reader {
    int size() {
        return values.size();
    }
}

values.add("A");   // Hợp lệ.
 // values = new ArrayList<>(); // Không hợp lệ nếu bỏ chú thích.
~~~

Thay nội dung List không giống gán lại `values`.

## 5. Chương trình hoàn chỉnh 1 — captured primitive và mutable reference

Tệp **`CaptureValuesDemo.java`**:

~~~java
public class CaptureValuesDemo {
    public static void main(String[] args) {
        int version = 17;
        StringBuilder text = new StringBuilder("A");

        class Reader {
            String read() {
                return "version=" + version + ", text=" + text;
            }
        }

        Reader reader = new Reader();
        System.out.println("Before = " + reader.read());

        text.append("B");
        System.out.println("After append = " + reader.read());

        StringBuilder alias = text;
        alias.append("C");
        System.out.println("After alias = " + reader.read());

        System.out.println("Same reference = " + (alias == text));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CaptureValuesDemo.java
java CaptureValuesDemo
~~~

**Stdout chính xác:**

~~~text
Before = version=17, text=A
After append = version=17, text=AB
After alias = version=17, text=ABC
Same reference = true
~~~

**Giải thích:**

1. `version` là int effectively final. Reader dùng 17.
2. `text` là reference effectively final, không bị gán lại.
3. `text.append("B")` thay mutable object.
4. `alias = text` tạo reference variable thứ hai tới cùng object.
5. `alias.append("C")` tiếp tục thay object mà Reader đọc.
6. `alias == text` true vì cùng identity; local class không tự tạo bản sao StringBuilder.

Nếu cần chụp nội dung text đúng tại thời điểm Reader được tạo, phải tạo String snapshot hoặc một representation khác phù hợp, không chỉ dựa vào effectively final.

## 6. Chương trình hoàn chỉnh 2 — shared List được sửa từ hai phía

Tệp **`LocalListSharingDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LocalListSharingDemo {
    public static void main(String[] args) {
        int id = 7;
        List<String> tags = new ArrayList<>(List.of("red"));

        class TagReader {
            String read() {
                return id + ":" + tags;
            }

            void add(String value) {
                tags.add(value);
            }
        }

        TagReader reader = new TagReader();

        System.out.println("Initial = " + reader.read());

        tags.add("blue");
        System.out.println("Outside mutation = " + reader.read());

        reader.add("green");
        System.out.println("Inside mutation = " + reader.read());
        System.out.println("Original list = " + tags);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LocalListSharingDemo.java
java LocalListSharingDemo
~~~

**Stdout chính xác:**

~~~text
Initial = 7:[red]
Outside mutation = 7:[red, blue]
Inside mutation = 7:[red, blue, green]
Original list = [red, blue, green]
~~~

`tags` không bị gán lại nên capture hợp lệ. Nhưng List vẫn mutable. `tags.add` bên ngoài và `reader.add` bên trong local class sửa **chính cùng một List**, nên nội dung ở cả hai nơi đều cập nhật.

### 6.1. Nếu List unmodifiable thì sao?

~~~java
List<String> tags = List.of("red");

class Reader {
    void add() {
        tags.add("blue");
    }
}
~~~

Đây là fragment có thể **biên dịch**, bởi tags effectively final. Nhưng nếu gọi Reader.add, method `List.of`-created List sẽ ném `UnsupportedOperationException` khi gọi `add`. Đây là **runtime API behavior**, không phải compile error về capture.

### 6.2. `final` có bảo vệ nội dung List không?

Không. `final` và effectively final kiểm soát việc gán lại variable; tính mutable/unmodifiable của List do List object và API quyết định.

## 7. So sánh biểu thức gán lại biến và thay đổi object

| Biểu thức | Gán lại captured local variable? | Kết luận khi variable bị capture |
| --- | --- | --- |
| `int count = 1;` | Khởi tạo biến | Có thể capture nếu không gán lại |
| `count++;` | Có | Không hợp lệ với captured local |
| `count += 1;` | Có | Không hợp lệ với captured local |
| `list = new ArrayList<>();` | Có | Không hợp lệ nếu list không effectively final |
| `list.add("x");` | Không | Hợp lệ về capture; tùy mutability List |
| `builder.append("x");` | Không | Hợp lệ về capture |
| `builder = new StringBuilder();` | Có | Không hợp lệ với capture đó |
| `array[0]++;` | Không gán lại array variable | Hợp lệ nếu index/type hợp lệ |
| `array = new int[3];` | Có | Không hợp lệ với captured local |
| `box.value++;` | Không gán lại box variable | Hợp lệ nếu field accessible/mutable |
| `map.put(key, value);` | Không gán lại map variable | Hợp lệ nếu Map hỗ trợ put |
| `owner.counter++;` | Đổi một object field | Không chịu local-capture rule của owner reference |

Một điểm thực hành: nhìn vào **đích được cập nhật**. `box.value++` cập nhật field, còn `box++` không phải cách hợp lệ với object reference; `number++` cập nhật chính primitive local variable. Syntax và loại dữ liệu đều ảnh hưởng.

## 8. Local class instance có thể sống lâu hơn method

Một local class có thể implement interface và được trả về qua interface reference. Method tạo class kết thúc rồi object vẫn sử dụng được captured values.

Tệp **`CaptureLifetimeDemo.java`**:

~~~java
public class CaptureLifetimeDemo {
    static Runnable create(String label, StringBuilder buffer) {
        int lengthAtCreation = buffer.length();

        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(
                        label + "|" + lengthAtCreation + "|" + buffer);
            }
        }

        return new Task();
    }

    public static void main(String[] args) {
        StringBuilder source = new StringBuilder("A");
        Runnable task = create("job", source);

        source.append("B");
        task.run();

        source.append("C");
        task.run();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CaptureLifetimeDemo.java
java CaptureLifetimeDemo
~~~

**Stdout chính xác:**

~~~text
job|1|AB
job|1|ABC
~~~

### 8.1. Phân tích ba captured values

- `label` là reference parameter đến immutable String `"job"`.
- `lengthAtCreation` là primitive int value 1 được xác định trước khi create trả về.
- `buffer` là reference parameter tới mutable StringBuilder mà `source` của caller cũng tham chiếu.

Sau khi create kết thúc, lengthAtCreation vẫn được Task sử dụng như 1. Nhưng buffer vẫn trỏ tới object mà source đang mutate, nên text chuyển từ AB sang ABC.

### 8.2. Lifetime của đối tượng được capture

Một Task còn reachable có thể tiếp tục giữ StringBuilder (và những mutable child objects reachable từ nó) sống lâu hơn thời gian method create chạy. Garbage collector xét object reachability, không chỉ thời điểm local method kết thúc.

Đây là lý do cần cẩn thận khi capture một List rất lớn, một domain aggregate chứa nhiều objects hoặc resource owner có lifecycle đặc biệt.

### 8.3. Không phụ thuộc compiler-generated fields

Compiler có thể lưu captured values bằng synthetic fields/constructor arguments trong class được sinh. Những chi tiết như tên field không phải public contract cho application. Điều cần dựa là Task có thể sử dụng những values đã capture mà không cần stack frame gốc còn hoạt động.

## 9. Outer instance fields không bị giới hạn như captured locals

Một local class định nghĩa trong instance method có thể truy cập fields của enclosing instance nếu phạm vi và access cho phép. Những fields này **không phải local variables**, nên có thể thay đổi mà không làm compiler báo lỗi effectively final.

Tệp **`OuterFieldCaptureDemo.java`**:

~~~java
public class OuterFieldCaptureDemo {
    static final class CounterOwner {
        private int count;

        Runnable createTask() {
            int step = 2;

            class Task implements Runnable {
                @Override
                public void run() {
                    count += step;
                    System.out.println("Count = " + count);
                }
            }

            return new Task();
        }

        int current() {
            return count;
        }
    }

    public static void main(String[] args) {
        CounterOwner owner = new CounterOwner();
        Runnable task = owner.createTask();

        task.run();
        task.run();

        System.out.println("Owner state = " + owner.current());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 OuterFieldCaptureDemo.java
java OuterFieldCaptureDemo
~~~

**Stdout chính xác:**

~~~text
Count = 2
Count = 4
Owner state = 4
~~~

`step` là captured local primitive, không bị gán lại. `count` là field của CounterOwner object. `count += step` thay **instance field**, không thay local variable step. Hai Task.run calls cùng làm thay đổi owner.count từ 0 đến 2 rồi 4.

### 9.1. Instance context so với static context

Local class trong instance method có thể sử dụng outer instance state theo rules. Local class trong static method **không có một enclosing outer instance tự động**; muốn thao tác instance field, phải có object reference tường minh.

### 9.2. Static fields cũng không phải captured locals

Một static field thuộc runtime class, không bị ràng buộc effectively final như local variable của enclosing method. Nhưng static mutable state có scope và concurrency behavior khác; không nên đổi một local variable thành static chỉ để tránh compile error.

## 10. Holder object để state thay đổi: hợp lệ nhưng có trade-off

Muốn một counter thay đổi theo các lần local class method chạy, có thể dùng mutable holder:

~~~java
int[] counter = {0};

class Task {
    int next() {
        return ++counter[0];
    }
}
~~~

`counter` effectively final vì nó giữ một array reference không đổi. `counter[0]` là một array element có thể sửa. Cách làm này tuân capture rule nhưng có **shared mutable state**.

Tệp **`CapturedHolderDemo.java`**:

~~~java
public class CapturedHolderDemo {
    public static void main(String[] args) {
        int[] counter = {0};
        StringBuilder log = new StringBuilder();

        class Counter {
            int next() {
                int value = ++counter[0];
                log.append(value).append(";");
                return value;
            }
        }

        Counter counterObject = new Counter();

        System.out.println("First = " + counterObject.next());
        System.out.println("Second = " + counterObject.next());
        System.out.println("Counter = " + counter[0]);
        System.out.println("Log = " + log);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CapturedHolderDemo.java
java CapturedHolderDemo
~~~

**Stdout chính xác:**

~~~text
First = 1
Second = 2
Counter = 2
Log = 1;2;
~~~

**Lưu ý:** mảng một phần tử không tự thread-safe, không tạo synchronization và thường kém rõ nghĩa hơn một state object có API được đặt tên. Nếu counter thuộc về một object, field của object đó có thể là lựa chọn tốt hơn. Nếu cần atomic counter giữa threads, xem `AtomicInteger`.

## 11. Captured reference không đồng nghĩa snapshot nội dung

Giả sử local class cần in danh sách **theo trạng thái tại lúc tạo task**, trong khi nguồn có thể thay đổi.

Nếu capture mutable List trực tiếp, task nhìn thấy thay đổi sau đó. Nếu chụp một immutable structural snapshot, task có thể dùng trạng thái ban đầu.

Tệp **`CaptureSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CaptureSnapshotDemo {
    public static void main(String[] args) {
        List<String> live = new ArrayList<>(List.of("A"));
        List<String> snapshot = List.copyOf(live);

        class Observer {
            void print() {
                System.out.println("Live = " + live);
                System.out.println("Snapshot = " + snapshot);
            }
        }

        Observer observer = new Observer();

        live.add("B");
        observer.print();

        System.out.println("Same object = " + (live == snapshot));

        try {
            snapshot.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("Snapshot unmodifiable");
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 CaptureSnapshotDemo.java
java CaptureSnapshotDemo
~~~

**Stdout chính xác:**

~~~text
Live = [A, B]
Snapshot = [A]
Same object = false
Snapshot unmodifiable
~~~

### 11.1. Hai biến đều effectively final

`live` và `snapshot` không bị gán reference mới, nên Observer capture cả hai. Khác biệt là **object mà mỗi variable trỏ tới**:

- `live` là mutable ArrayList còn tiếp tục được sửa.
- `snapshot` là unmodifiable structural snapshot do `List.copyOf` tạo.

### 11.2. `List.copyOf` không deep-copy elements

Trong chương trình, List chứa String immutable nên snapshot phù hợp. Nếu List chứa MutablePerson, snapshot List vẫn có thể chia sẻ các MutablePerson objects; người khác sửa một Person sẽ ảnh hưởng dữ liệu quan sát qua snapshot.

Khi muốn snapshot sâu hơn, phải copy mutable elements hoặc dùng immutable value DTO.

### 11.3. Unmodifiable view không nhất thiết snapshot

`Collections.unmodifiableList(live)` trả một view không sửa được qua chính view đó, nhưng vẫn có thể phản ánh thêm/xóa trên backing `live`. Đừng đồng nhất unmodifiable view với structural snapshot độc lập. `List.copyOf(live)` đáp ứng mục tiêu trong ví dụ nếu null/elements phù hợp.

### 11.4. Snapshot StringBuilder

Nếu muốn capture text tại thời điểm tạo task:

~~~java
StringBuilder builder = new StringBuilder("A");
String fixedText = builder.toString();

class Reader {
    String read() {
        return fixedText;
    }
}
~~~

Bây giờ sửa builder sau đó không đổi fixedText vì String immutable. Không cần copy toàn bộ StringBuilder nếu chỉ quan tâm nội dung String lúc tạo.

## 12. Capture trong vòng lặp

Một tình huống phổ biến là tạo nhiều local class objects trong vòng lặp.

### 12.1. Basic-for index không effectively final khi có `i++`

~~~java
for (int i = 0; i < 3; i++) {
    class Job {
        int index() {
            return i; // Cố ý không biên dịch.
        }
    }
}
~~~

`i` bị tăng mỗi iteration, nên không effectively final.

Cách đúng là tạo local variable riêng trong mỗi iteration:

~~~java
for (int i = 0; i < 3; i++) {
    final int index = i;

    class Job {
        int index() {
            return index;
        }
    }

    tasks.add(new Job());
}
~~~

Đây là fragment giả định `tasks` đã được khai báo với type phù hợp. Mỗi `index` trong một lần chạy loop body được gán một lần và có value của iteration đó.

### 12.2. Enhanced-for variable

Enhanced-for iteration variable có semantics per iteration; nếu không bị reassign trong body, có thể được local class capture. Đừng suy ra basic-for `i` và enhanced-for `item` có cùng assignment rules.

### 12.3. Chương trình hoàn chỉnh — captured values riêng từng iteration

Tệp **`LoopCaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class LoopCaptureDemo {
    interface Printable {
        void print();
    }

    public static void main(String[] args) {
        List<Printable> tasks = new ArrayList<>();

        for (int i = 0; i < 3; i++) {
            final int index = i;

            class IndexPrinter implements Printable {
                public void print() {
                    System.out.println("Index = " + index);
                }
            }

            tasks.add(new IndexPrinter());
        }

        for (String color : List.of("red", "blue")) {
            class ColorPrinter implements Printable {
                public void print() {
                    System.out.println("Color = " + color);
                }
            }

            tasks.add(new ColorPrinter());
        }

        for (Printable printer : tasks) {
            printer.print();
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 LoopCaptureDemo.java
java LoopCaptureDemo
~~~

**Stdout chính xác:**

~~~text
Index = 0
Index = 1
Index = 2
Color = red
Color = blue
~~~

Mỗi IndexPrinter object giữ một index riêng từ iteration tạo nó. ColorPrinter cũng dùng giá trị enhanced-for variable trong iteration tương ứng. Java demo này không có hiện tượng mọi IndexPrinter cùng đọc basic-loop `i = 3` sau khi vòng lặp kết thúc, vì `i` không được capture trực tiếp.

## 13. Local class, anonymous class và lambda

Cả ba hình thức có thể dùng local/parameter values từ enclosing scope, với ràng buộc final/effectively final:

~~~java
int factor = 2;
StringBuilder text = new StringBuilder("A");
~~~

**Local class:**

~~~java
class Printer implements Runnable {
    public void run() {
        System.out.println(factor + ":" + text);
    }
}
~~~

**Anonymous class:**

~~~java
Runnable anonymous = new Runnable() {
    public void run() {
        System.out.println(factor + ":" + text);
    }
};
~~~

**Lambda:**

~~~java
Runnable lambda = () ->
        System.out.println(factor + ":" + text);
~~~

Ba fragments dùng chung enclosing scope phù hợp. Không hình thức nào tự deep-copy StringBuilder. Nếu text.append("B") trước khi chạy, tất cả có thể in `2:AB`.

### 13.1. Khác biệt `this`

- Trong instance method của local/anonymous class, `this` chỉ inner-class instance đang thực thi.
- Trong lambda, `this` có lexical semantics của enclosing context; không có một lambda-specific `this` như anonymous class.
- Trong static enclosing context, không có implicit enclosing instance this để tham chiếu tự do.

Khác biệt này ảnh hưởng khi code vừa đọc captured locals vừa thao tác outer instance fields. Nhưng **final/effectively final restriction của captured local variables** vẫn là điểm chung.

## 14. Chương trình hoàn chỉnh — ba hình thức quan sát cùng object

Tệp **`LocalAnonymousLambdaDemo.java`**:

~~~java
public class LocalAnonymousLambdaDemo {
    public static void main(String[] args) {
        int factor = 2;
        StringBuilder shared = new StringBuilder("A");

        class LocalTask implements Runnable {
            @Override
            public void run() {
                System.out.println("Local = " + factor + ":" + shared);
            }
        }

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println("Anonymous = " + factor
                        + ":" + shared);
            }
        };

        Runnable lambda = () ->
                System.out.println("Lambda = " + factor + ":" + shared);

        shared.append("B");

        new LocalTask().run();
        anonymous.run();
        lambda.run();
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 LocalAnonymousLambdaDemo.java
java LocalAnonymousLambdaDemo
~~~

**Stdout chính xác:**

~~~text
Local = 2:AB
Anonymous = 2:AB
Lambda = 2:AB
~~~

Cả ba giữ primitive factor và cùng StringBuilder reference. Mutation append làm shared object có nội dung AB; không có reassignment của captured variable.

## 15. Concurrency: effectively final không đồng nghĩa thread-safe

Nếu một local class capture mutable object và task chạy ở threads khác, việc local reference không bị gán lại **không bảo vệ các mutations** của object.

Ví dụ:

~~~java
int[] counter = {0};

class Task implements Runnable {
    public void run() {
        counter[0]++;
    }
}
~~~

Nếu nhiều threads chạy cùng Task hoặc nhiều Tasks capture cùng array, phép `counter[0]++` là read-modify-write không atomic, có thể bị mất updates. `counter` effectively final chỉ ổn định reference value.

### 15.1. AtomicInteger có operations phù hợp

Tệp **`AtomicCaptureDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCaptureDemo {
    public static void main(String[] args)
            throws InterruptedException {
        int step = 2;
        AtomicInteger total = new AtomicInteger();

        class Worker implements Runnable {
            @Override
            public void run() {
                total.addAndGet(step);
            }
        }

        Runnable task = new Worker();
        Thread one = new Thread(task);
        Thread two = new Thread(task);

        one.start();
        two.start();

        one.join();
        two.join();

        System.out.println("Total = " + total.get());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AtomicCaptureDemo.java
java AtomicCaptureDemo
~~~

**Stdout chính xác:**

~~~text
Total = 4
~~~

`total` là reference effectively final tới AtomicInteger. Hai threads dùng `addAndGet(2)`, operation atomic theo API; main chờ cả hai bằng `join` trước khi đọc. Kết quả 4 không phụ thuộc thread nào chạy trước.

### 15.2. Atomic state khác biến local có thể reassign

`AtomicInteger` cho phép thay đổi **state của object theo API thread-safe**, không có nghĩa Java cho phép gán lại local `total` sau capture.

### 15.3. Vấn đề còn lại

Một object phức tạp với nhiều fields có invariant chung có thể vẫn cần locking, immutable state replacement hoặc protocol khác. `AtomicInteger` không tự biến toàn bộ object graph thành thread-safe. `volatile` hay `final` reference cũng không tự bảo đảm mọi mutable child fields có memory-visibility phù hợp.

## 16. Parameter capture và reassignment

Method parameters dùng từ local class phải effectively final theo rules giống captured locals.

Hợp lệ:

~~~java
static Runnable create(String label) {
    class Task implements Runnable {
        public void run() {
            System.out.println(label);
        }
    }
    return new Task();
}
~~~

Cố ý không biên dịch:

~~~java
static Runnable invalid(String label) {
    class Task implements Runnable {
        public void run() {
            System.out.println(label);
        }
    }
    label = label.trim(); // Thay parameter đã capture.
    return new Task();
}
~~~

Cách dễ đọc là tạo snapshot/normalized local mới:

~~~java
static Runnable normalized(String input) {
    String value = input.trim();

    class Task implements Runnable {
        public void run() {
            System.out.println(value);
        }
    }
    return new Task();
}
~~~

Những đoạn trên là **method fragments**, không phải standalone files.

Với reference parameter như `List<String> items`, `items.add("X")` thay object nhưng **không gán lại parameter items**; class capture items được nếu variable vẫn effectively final. Cần xem List có mutable và API cho phép add không.

## 17. Shadowing: đọc biến nào khi trùng tên?

Local class có thể khai báo field cùng tên với local variable của method. Name lookup trong class body có thể chọn field, không phải local được kỳ vọng.

~~~java
void demo() {
    int initial = 10;

    class Reader {
        int current = 20;

        int sum() {
            return initial + current;
        }
    }

    System.out.println(new Reader().sum()); // 30
}
~~~

Đây là method fragment dùng hai tên riêng nên rõ nghĩa: `initial` là captured local, `current` là instance field.

Nếu cả hai đều tên `value`, biểu thức `value` trong class có thể trỏ field của chính class do shadowing. Không có cú pháp `method.this.value` để biến local variable của method thành một outer field. `Outer.this` chỉ định một enclosing **instance** khi hợp lệ, không phải local activation record. Đặt tên rõ ràng hoặc tạo alias effectively final với tên khác là phương án dễ bảo trì.

## 18. Các lỗi thường gặp cần phân biệt đúng loại

1. **Gán lại local đã capture:** lỗi compile-time effectively final.
2. **Mutate List được capture:** có thể hợp lệ về capture, nhưng nếu List unmodifiable thì ném UnsupportedOperationException ở runtime.
3. **Gán lại method parameter đã capture:** lỗi compile-time nếu parameter không effectively final.
4. **`counter++` trên captured local primitive:** lỗi capture; khác `box.value++`.
5. **`array[0] = ...`:** mutate array element, không đổi local reference; có thể hợp lệ.
6. **Dùng static field chỉ để né quy tắc:** code có thể compile nhưng scope/lifetime và concurrency semantics đổi.
7. **Tưởng final reference là immutable object:** mutable referent vẫn thay.
8. **Tưởng local class copy object khi capture:** Java không tự deep-copy object.
9. **Tưởng List.copyOf deep-copy elements:** nó copy cấu trúc, elements mutable vẫn có thể chia sẻ.
10. **Dùng Collections.unmodifiableList(source) làm snapshot:** đó là view có thể phản ánh source mutation.
11. **Capture basic-for i có i++:** i không effectively final; dùng per-iteration snapshot.
12. **Cho task chạy sau method rồi nghĩ captured values mất:** task vẫn có thể dùng values đã capture.
13. **Không xét GC lifetime:** returned closure-like object có thể giữ mutable graph reachable.
14. **Không đồng bộ mutable shared state giữa threads:** effectively final không cung cấp atomicity của referent.
15. **Nhầm outer instance field với local captured variable:** field có thể thay mà không vi phạm effectively final rule.
16. **Trộn shadowed fields với locals:** đọc nhầm một field thay vì captured variable.
17. **Suy đoán compiler tạo field synthetic có tên cụ thể:** đó không phải ổn định public API.
18. **Nhầm lambda lexical this với anonymous-class this:** semantics khác dù capture rules tương đồng.
19. **Coi live sharing luôn là bug:** có thể là thiết kế đúng với owner/contract rõ.
20. **Coi snapshot luôn cần deep copy mọi thứ:** immutable values có thể được chia sẻ an toàn.

## 19. Bài tập tự kiểm tra có đáp án

**Câu 1.** Local class có thể capture biến không khai báo `final` không?

**Đáp án:** Có nếu biến effectively final và đáp ứng scope/definite assignment rules.

**Câu 2.** Khi StringBuilder variable bị capture, `append` có được không?

**Đáp án:** Có; append sửa object, không gán lại captured variable.

**Câu 3.** Khi StringBuilder variable bị capture, gán nó sang `new StringBuilder()` có được không?

**Đáp án:** Không nếu làm variable mất effectively final.

**Câu 4.** Với `final List<String> names = new ArrayList<>()`, gọi `names.add` có bị final cấm không?

**Đáp án:** Không; final cấm reassign reference, không cấm List mutation.

**Câu 5.** Local class có thể tăng một captured local `int counter` bằng `counter++` không?

**Đáp án:** Không; thay local primitive variable vi phạm effectively final.

**Câu 6.** Local class có thể tăng `holder[0]` nếu holder là captured int[] không?

**Đáp án:** Có về capture vì sửa array element, không gán lại holder variable; thread-safety riêng.

**Câu 7.** Copy `StringBuilder` reference vào biến khác có tạo StringBuilder object mới không?

**Đáp án:** Không; nó tạo alias tới cùng object.

**Câu 8.** Primitive int được copy giữa hai variables có share một mutable object không?

**Đáp án:** Không; int là primitive value.

**Câu 9.** Local class returned từ method có còn đọc được captured parameter không?

**Đáp án:** Có; object giữ captured value theo Java semantics.

**Câu 10.** Nếu parameter reference tới mutable StringBuilder, caller sửa nó sau method return thì local class có thấy không?

**Đáp án:** Có thể thấy vì cùng referent; capture không tạo snapshot.

**Câu 11.** Outer instance field có cần effectively final để local class sửa không?

**Đáp án:** Không; quy tắc capture locals/parameters khác việc truy cập instance fields.

**Câu 12.** Vì sao `count += step` trong CounterOwner hợp lệ?

**Đáp án:** count là owner instance field, step là captured local effectively final.

**Câu 13.** Local class trong static method tự có Outer.this không?

**Đáp án:** Không, không có implicit outer instance.

**Câu 14.** List mutable được capture có luôn in nội dung tại thời điểm capture không?

**Đáp án:** Không. Nó có thể phản ánh mutations sau đó vì cùng object reference.

**Câu 15.** `List.copyOf(source)` bảo vệ gì?

**Đáp án:** Một unmodifiable structural snapshot; không deep-copy arbitrary mutable elements.

**Câu 16.** `Collections.unmodifiableList(source)` luôn tách khỏi source không?

**Đáp án:** Không; thường là view phản ánh biến đổi source qua alias.

**Câu 17.** `List.of("A").add("B")` thất bại vì capture hay vì collection?

**Đáp án:** Vì unmodifiable collection API, thường ném UnsupportedOperationException khi chạy add.

**Câu 18.** Có thể capture directly basic-for index `i` trong `for (int i=0; i<3; i++)` không?

**Đáp án:** Không vì i bị increment, không effectively final.

**Câu 19.** Cách capture index mỗi iteration là gì?

**Đáp án:** Tạo `final int index = i` trong loop body rồi capture index.

**Câu 20.** Enhanced-for variable có thể capture không?

**Đáp án:** Có khi không reassign trong body và thỏa Java rules cho từng iteration.

**Câu 21.** Lambda và local class có cùng constraint về effectively final captured locals không?

**Đáp án:** Có; chúng khác ở các semantics khác như this.

**Câu 22.** `this` trong lambda có giống anonymous class this không?

**Đáp án:** Không; lambda có lexical this semantics, anonymous class có own instance this.

**Câu 23.** Captured int[] có tự thread-safe không?

**Đáp án:** Không. `counter[0]++` không tự atomic.

**Câu 24.** Captured AtomicInteger có thể dùng concurrent increment không?

**Đáp án:** Có qua API atomic như addAndGet, nhưng không vì captured variable effectively final.

**Câu 25.** Vì sao captured mutable object có thể sống lâu hơn enclosing method?

**Đáp án:** Local-class object còn reachable có thể tiếp tục giữ reference tới mutable referent.

**Câu 26.** Có nên dùng static counter chỉ để vượt compiler capture rule không?

**Đáp án:** Thường không; static state mang scope, lifetime và concurrency khác.

**Câu 27.** Khi field và local cùng tên, unqualified identifier luôn chỉ local được capture không?

**Đáp án:** Không; field shadowing/name resolution có thể chọn field.

**Câu 28.** Khi muốn task dùng text của StringBuilder tại thời điểm tạo, nên capture gì?

**Đáp án:** Capture immutable String snapshot từ `builder.toString()`.

**Câu 29.** Khi muốn task luôn đọc List mới nhất, có thể capture gì?

**Đáp án:** Mutable List reference nếu live-sharing là contract mong muốn và ownership/thread-safety được quản lý.

**Câu 30.** Phân biệt cốt lõi của bài là gì?

**Đáp án:** Captured local variable phải giữ giá trị variable không bị reassignment; còn mutable object mà reference trỏ tới vẫn có thể thay state qua aliases.

## 20. Checklist review code

1. Local class được khai báo trong scope nào?
2. Những local variables/parameters nào được capture?
3. Chúng có final hoặc effectively final không?
4. Có reassignment/`++`/`+=` lên chính captured local không?
5. Captured type là primitive hay reference?
6. Nếu reference, object có mutable không?
7. Có alias khác có thể sửa object không?
8. Muốn live updates hay snapshot cố định?
9. Nếu snapshot, đã defensive-copy ở boundary chưa?
10. Nested mutable elements có cần deep copy không?
11. Có dùng unmodifiable view nhầm với snapshot không?
12. Có dùng String/Instant hoặc immutable value types để giảm copy không?
13. Có local-class object returned khỏi method và kéo dài lifetime data không?
14. Có outer instance field bị hiểu nhầm là captured local không?
15. Static context có thiếu enclosing instance không?
16. Basic-for indices có được snapshot per iteration không?
17. Enhanced-for variable có bị reassign không?
18. Có shadowed field/local names không?
19. Có holder array chỉ để né compiler nhưng tạo hidden mutable state không?
20. Captured mutable object có chạy qua nhiều threads không?
21. Có atomic/locking/safe-publication protocol cần thiết không?
22. Có phân biệt compile-time capture error với runtime collection error không?
23. Tests có sửa object sau capture rồi đọc từ local class không?
24. Tests có chứng minh snapshot không đổi khi source đổi không?
25. Có tài liệu hóa ownership, live state và object lifetime rõ không?

## Kết luận

Local class của Java **bắt giữ giá trị của một local variable/parameter**, không tự đóng băng mọi object mà biến tham chiếu tới. Với primitive, giá trị được capture là primitive value; với reference type, giá trị được capture là một reference tới object. Quy tắc `final`/*effectively final* kiểm soát **reassignment của biến cục bộ**, không ngăn những method như `list.add`, `builder.append` hoặc assignment đến field/array element sửa state của referent.

Nếu ứng dụng cần cập nhật state qua local class, hãy dùng một owner/holder với mutation contract rõ và xử lý concurrency nếu cần. Nếu cần state cố định tại thời điểm tạo task, hãy snapshot thành immutable values hoặc defensive copies phù hợp. Luôn phân biệt **biến**, **reference value**, **object identity**, **mutable state** và **lifetime**; đây là chìa khóa để hiểu đúng capture của local class, anonymous class và lambda trong Java 17+.
