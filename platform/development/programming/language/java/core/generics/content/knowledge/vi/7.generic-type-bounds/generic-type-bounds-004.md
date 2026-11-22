# Quy tắc lớp đứng trước và các giới hạn phải tương thích trong Java Generics

## 1. Mục tiêu bài học

Trong Java Generics, **giới hạn kiểu** (*type bound*) cho biết một tham số kiểu được phép đại diện cho những kiểu nào và có thể sử dụng những phương thức nào. Một tham số kiểu T có thể có **nhiều cận trên** (*multiple upper bounds*), nhưng danh sách này phải tuân thủ những quy tắc bắt buộc:

1. Nếu có **cận là class**, class đó **phải đứng đầu** danh sách.
2. Một type parameter không thể khai báo **hai class bounds độc lập**.
3. Những cận còn lại sau class bound phải là **interface types**; chúng được nối bằng dấu **&**, không phải dấu phẩy.
4. Các cận phải **tương thích với nhau**: phải tuân thủ luật kế thừa của Java, không được gây xung đột giữa những specialization không thể cùng tồn tại hay những phương thức không có chữ ký tương thích.
5. Mỗi đối số kiểu thực tế phải đáp ứng **tất cả** các cận đã khai báo.
6. **Cận đầu tiên** có vai trò đặc biệt trong **type erasure**; thay đổi thứ tự bounds có thể có hệ quả về binary compatibility.

Ví dụ đúng:

~~~java
static <T extends Number & Comparable<T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

T phải vừa là subtype của Number, vừa thực thi Comparable<T>. Một Integer thỏa cả hai điều kiện; một Number tổng quát không tự bảo đảm thực thi Comparable<Number>.

Bài tập trung vào **quy tắc khai báo, tính tương thích và tác động kỹ thuật của nhiều bounds**, không thay thế cho toàn bộ chương về wildcard, PECS hoặc variance.

## 2. Cú pháp giới hạn kiểu

Cú pháp chung:

~~~text
<T extends FirstBound & Interface2 & Interface3>
~~~

Trong đó:

- **T** là type parameter được khai báo.
- **extends** là từ khóa dùng cho **mọi upper bound**, dù bound đó là class hay interface.
- **FirstBound** có thể là một class hoặc một interface.
- Nếu có một class bound, nó **bắt buộc là bound đầu tiên**.
- Sau bound đầu tiên, những bound thêm vào phải là interface types.
- **&** nối các cận thuộc **cùng một** type parameter.

Ví dụ:

~~~java
class NumericValue<T extends Number> {
    T value;
}

class SortedNumber<T extends Number & Comparable<T>> {
    T value;
}

class Exportable<T extends Number & Comparable<T> & java.io.Serializable> {
    T value;
}
~~~

Các khai báo trên đều hợp lệ. Trong SortedNumber, T vừa có các phương thức của Number như doubleValue(), vừa có compareTo(T) của Comparable<T>.

Một dấu phẩy có ý nghĩa **khác** dấu &: 

~~~java
class Pair<A extends Number, B extends CharSequence> {
    A first;
    B second;
}
~~~

**<A extends Number, B extends CharSequence>** khai báo **hai type parameters** có giới hạn riêng. Nó không tương đương **<T extends Number & CharSequence>**, vốn khai báo **một T** phải đáp ứng cả Number lẫn CharSequence.

| Cú pháp | Ý nghĩa |
| --- | --- |
| **<T>** | T có cận trên ngầm định Object |
| **<T extends Number>** | Một T, cận class Number |
| **<T extends Runnable>** | Một T, cận interface Runnable |
| **<T extends Number & Comparable<T>>** | Một T, vừa là Number vừa Comparable<T> |
| **<T extends Runnable & AutoCloseable>** | Một T, đáp ứng hai interface |
| **<A extends Number, B extends CharSequence>** | Hai tham số kiểu độc lập A và B |

## 3. Nếu có class bound, class phải đứng đầu

Java quy định rằng trong một intersection của các bounds khai báo cho type parameter, một class chỉ có thể xuất hiện ở **vị trí đầu tiên**. Ví dụ:

~~~java
// Hợp lệ:
class Good<T extends Number & Comparable<T>> {}
~~~

Sai khi đảo hai cận để đưa class về phía sau:

~~~java
// Minh họa lỗi biên dịch:
class Wrong<T extends Comparable<T> & Number> {}
~~~

**Comparable<T>** là interface; **Number** là class và lại xuất hiện sau dấu &. Đây là lỗi cú pháp/cấu trúc bounds, không phải lỗi chỉ xuất hiện lúc sử dụng type argument.

Giải pháp là đổi thứ tự:

~~~java
class Correct<T extends Number & Comparable<T>> {}
~~~

Cũng không thể viết:

~~~java
// Minh họa lỗi biên dịch:
class TwoClasses<T extends Number & Thread> {}
~~~

Number và Thread đều là class. Việc Java không hỗ trợ một class kế thừa đồng thời hai superclass độc lập cũng thể hiện ở cách quy định type bounds: **không có danh sách hai class bounds**.

**Lưu ý quan trọng:** nếu **không có class bound**, interface có thể đứng đầu. Dạng sau hợp lệ:

~~~java
class WorkItem<T extends Runnable & AutoCloseable> {
    T task;
}
~~~

Cả Runnable và AutoCloseable đều là interface. Thứ tự của các interfaces có thể khác nhau về mặt luật “class đứng trước”, nhưng bound đầu tiên vẫn có thể tác động tới erasure và bytecode; do đó đừng tùy tiện thay đổi thứ tự trong public API đã phát hành.

## 4. `extends` vẫn dùng khi bound là interface

Trong khai báo type parameter, Java chỉ dùng `extends`, kể cả khi bound là interface:

~~~java
class Runner<T extends Runnable> {
    private final T task;
    Runner(T task) { this.task = task; }
    void execute() { task.run(); }
}
~~~

Không viết `<T implements Runnable>`: `implements` chỉ dùng khi khai báo một class thực hiện interface, không dùng trong type-parameter bound. Nếu kết hợp class và interface, viết `<T extends Thread & Runnable>` với `Thread` đứng đầu; đây là bound có `Runnable` phần nào dư vì `Thread` đã thực hiện giao diện đó.

Sau khi nhận diện đúng cú pháp, phần đáng đánh giá kỹ hơn là **bộ bounds có thể thỏa đồng thời hay không**. Chẳng hạn `String & Runnable` không có type argument hợp lệ vì `String` là final và không triển khai `Runnable`.

## 5. Các cận phải có kiểu hiện thực đồng thời

Đọc **<T extends A & B>** như một yêu cầu kết hợp:

~~~text
T phải là subtype của A
VÀ
T phải là subtype của B
~~~

Nó **không** có nghĩa T được chọn một trong hai A hoặc B.

Ví dụ:

~~~java
interface Printable {
    String print();
}

interface Identified {
    long id();
}

class Ticket implements Printable, Identified {
    private final long number;

    Ticket(long number) {
        this.number = number;
    }

    @Override
    public String print() {
        return "ticket-" + number;
    }

    @Override
    public long id() {
        return number;
    }
}
~~~

Một generic method có thể yêu cầu cả hai giao diện:

~~~java
static <T extends Printable & Identified> String describe(T item) {
    return item.id() + ":" + item.print();
}
~~~

**Ticket** là type argument hợp lệ vì implement cả Printable và Identified. Một kiểu chỉ implement Printable nhưng không implement Identified không hợp lệ. Mặc dù trong ví dụ không có class bound, compiler vẫn cho phép gọi cả print() lẫn id() trên biến T.

**Khả năng tương thích có hai lớp cần tách biệt:**

- **Tại khai báo bounds:** Các giới hạn không được mâu thuẫn với quy tắc kiểu của Java (ví dụ lặp cùng generic interface bằng hai type arguments khác nhau).
- **Tại nơi áp dụng type argument:** Kiểu cụ thể truyền vào phải thỏa tất cả bounds. Việc một interface tùy ý chưa có class hiện thực ngay ở chỗ khai báo **không tự khiến intersection sai**; về sau một class có thể implement nhiều interface tương thích cùng lúc.

Đừng lẫn “chưa tìm thấy class đáp ứng” với “các bounds tự mâu thuẫn”.

## 6. Ví dụ chạy hoàn chỉnh: kết hợp nhiều interface bounds

Lưu thành **InterfaceBoundsDemo.java**:

~~~java
public class InterfaceBoundsDemo {
    interface Printable {
        String print();
    }

    interface Identified {
        long id();
    }

    static final class Ticket implements Printable, Identified {
        private final long number;

        Ticket(long number) {
            this.number = number;
        }

        @Override
        public String print() {
            return "ticket-" + number;
        }

        @Override
        public long id() {
            return number;
        }
    }

    static <T extends Printable & Identified> String describe(T item) {
        return item.id() + ":" + item.print();
    }

    public static void main(String[] args) {
        Ticket ticket = new Ticket(17);
        System.out.println(describe(ticket));

        Printable asPrintable = ticket;
        System.out.println(asPrintable.print());
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac -encoding UTF-8 InterfaceBoundsDemo.java
java InterfaceBoundsDemo
~~~

Stdout chính xác:

~~~text
17:ticket-17
ticket-17
~~~

Trong describe(T), compiler cho phép gọi **item.id()** và **item.print()** vì T có cả hai interface bounds. Khi biến được khai báo đơn thuần là Printable, phương thức id() không xuất hiện trong hợp đồng của kiểu biến đó; quyền truy cập thành viên tại source code phụ thuộc vào **kiểu tĩnh**, không chỉ vào runtime object.

## 7. Kết hợp class bound với nhiều interface bounds

Một tình huống thực tiễn là muốn thao tác với số, đồng thời so sánh và serialize kiểu số đó:

~~~java
import java.io.Serializable;

class NumericEntry<T extends Number & Comparable<T> & Serializable> {
    private final T number;

    NumericEntry(T number) {
        this.number = number;
    }

    double asDouble() {
        return number.doubleValue();
    }

    boolean isGreaterThan(T other) {
        return number.compareTo(other) > 0;
    }
}
~~~

Giải nghĩa:

- **Number** là class bound, nên đứng đầu.
- **Comparable<T>** là interface bound, cho phép compareTo với T.
- **Serializable** là interface bound bổ sung, không trực tiếp tạo method public mới để gọi trên T.
- **Integer**, **Long**, **Double** là những ví dụ wrapper classes có thể đáp ứng các bound này với type arguments phù hợp.
- **String** không đáp ứng Number dù String có Comparable<String> và Serializable.

Lưu ý **Number bản thân đã implement Serializable**; trong trường hợp cụ thể trên, ghi thêm Serializable là dư về điều kiện cần. Đây là ví dụ có chủ ý để minh họa cú pháp ba bounds; ở API thực tế, cân nhắc bỏ bound dư thừa.

Không nên hiểu một class bound là “chuyển T thành primitive”. **T vẫn là reference type variable**, vì vậy cú pháp **a + b** cho hai biến T không được cho phép như phép cộng số generic. Muốn cộng dưới kiểu double, có thể lấy **a.doubleValue() + b.doubleValue()** rồi chấp nhận hệ quả về độ chính xác số.

Một class abstract cũng có thể làm class bound, và type argument thực tế có thể là concrete subclass tương ứng. Không bắt buộc class bound là một concrete class có constructor không tham số.

## 8. Ví dụ chạy hoàn chỉnh: Number, Comparable và Serializable

Lưu thành **ClassFirstBoundsDemo.java**:

~~~java
import java.io.Serializable;

public class ClassFirstBoundsDemo {
    static final class NumericEntry<T extends Number & Comparable<T> & Serializable> {
        private final T value;

        NumericEntry(T value) {
            this.value = value;
        }

        double twice() {
            return value.doubleValue() * 2.0;
        }

        boolean greaterThan(T other) {
            return value.compareTo(other) > 0;
        }
    }

    static <T extends Number & Comparable<T>> T maximum(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    public static void main(String[] args) {
        NumericEntry<Integer> entry = new NumericEntry<>(8);
        System.out.println(entry.twice());
        System.out.println(entry.greaterThan(3));
        System.out.println(maximum(4, 9));
        System.out.println(maximum(2.5, 1.5));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ClassFirstBoundsDemo.java
java ClassFirstBoundsDemo
~~~

Stdout:

~~~text
16.0
true
9
2.5
~~~

Phân tích:

1. **NumericEntry<Integer>** hợp lệ vì Integer extends Number, implements Comparable<Integer> và Serializable.
2. **twice()** dùng Number.doubleValue(), trả double.
3. **greaterThan(3)** gọi Comparable<Integer>.compareTo với giá trị Integer sau autoboxing.
4. Trong **maximum(4, 9)**, kiểu phù hợp được suy luận là Integer.
5. Trong **maximum(2.5, 1.5)**, kiểu phù hợp là Double; kết quả được in theo định dạng Double thông thường.

Phương thức maximum dùng T ở cả tham số lẫn kết quả để compiler giữ quan hệ kiểu. Các bounds cho phép gọi compareTo; không cần ép kiểu từ Object.

## 9. Thế nào là các bounds không tương thích?

Có một số loại xung đột thật sự cần nhận diện.

### 9.1. Hai class bounds không được phép

~~~java
// Cố ý sai:
class Invalid<T extends Number & Thread> {}
~~~

Đây là vi phạm luật class bound, dù ta có tưởng tượng một kiểu đáp ứng cả hai. Một class bound nếu có phải đứng đầu, và phần còn lại là interface types.

### 9.2. Một class final và một interface không thể cùng thỏa

Ví dụ minh họa:

~~~java
// Cố ý sai:
class Impossible<T extends String & Runnable> {}
~~~

String là **final class** và không implement Runnable. Không có subtype của String nào có thể được tạo để bổ sung Runnable; các bounds này không thể có type argument đáp ứng. Compiler phát hiện mâu thuẫn. Ngược lại, nếu class bound không final, việc bản thân class đó chưa implement một interface chưa nhất thiết khiến khai báo không hợp lệ; một subclass có thể bổ sung interface.

### 9.3. Cùng một generic interface bị yêu cầu với hai specialization khác nhau

Xét:

~~~java
interface TextComparable extends Comparable<String> {}

interface NumberComparable extends Comparable<Integer> {}

// Không hợp lệ:
// class Conflict<T extends TextComparable & NumberComparable> {}
~~~

Một kiểu T vừa thỏa TextComparable vừa thỏa NumberComparable sẽ đồng thời là **Comparable<String>** và **Comparable<Integer>**. Java không cho một subtype kế thừa cùng generic interface với hai type arguments khác nhau. Đây là xung đột về generic supertypes, không thể sửa bằng cast.

Một dạng trực tiếp hơn:

~~~java
// Minh họa lỗi:
class ConflictDirect<T extends Comparable<String> & Comparable<Integer>> {}
~~~

Dấu & không thể dùng để “ghép” hai phiên bản Comparable với type arguments mâu thuẫn.

### 9.4. Những method signatures trùng nhưng return types không tương thích

Hai interface riêng biệt có thể khai báo cùng một chữ ký phương thức nhưng với return types không thể cùng đáp ứng:

~~~java
interface StringReader {
    String read();
}

interface IntegerReader {
    Integer read();
}

// Minh họa bounds xung đột:
// class ImpossibleReader<T extends StringReader & IntegerReader> {}
~~~

Không có một method read() không tham số nào có thể đồng thời trả String và Integer theo hợp đồng override của cả hai, vì String và Integer là những final classes không có quan hệ subtype cần thiết.

Nếu hai interface có phương thức cùng signature và **return types tương thích theo covariance**, chúng có thể cùng được implement bởi một class thích hợp. Chẳng hạn một interface quy định Object read() và interface khác quy định String read(); class triển khai có thể trả String, vì String là subtype của Object.

**Quy tắc thực hành:** khi nhiều bounds đều có methods cùng tên, phải xét **chữ ký sau erasure, return type substitutability, default methods và luật override**. Đừng chỉ nhìn thấy hai interface khác tên rồi kết luận intersection hợp lệ.

### 9.5. Method name clash sau type erasure

Ví dụ về hợp đồng có cùng erasure nhưng type arguments khác:

~~~java
interface Strings {
    void accept(java.util.List<String> values);
}

interface Integers {
    void accept(java.util.List<Integer> values);
}

// Một type parameter cố kết hợp các bounds này không thể
// giả định sẽ có hai overload độc lập tên accept(List<...>).
~~~

Hai phương thức **accept(List<String>)** và **accept(List<Integer>)** có cùng erasure đối với tham số List. Một class hiện thực thường không thể viết hai overload riêng chỉ khác type argument. Tùy quan hệ giữa các declarations, compiler có thể báo name clash hoặc xung đột kế thừa. Khi thiết kế intersection bounds, cần tránh đưa các hợp đồng không thể hiện thực được vào cùng một type parameter.

## 10. “Tương thích” không có nghĩa các interface phải có quan hệ cha–con

Một kiểu có thể implement nhiều interface độc lập:

~~~java
interface Auditable {
    String audit();
}

interface Validatable {
    boolean valid();
}

class Event implements Auditable, Validatable {
    @Override
    public String audit() {
        return "event";
    }

    @Override
    public boolean valid() {
        return true;
    }
}
~~~

Hai interface không bắt buộc cái này extends cái kia. Miễn có type argument đáp ứng đồng thời và không phát sinh xung đột thành viên, khai báo:

~~~java
static <T extends Auditable & Validatable> boolean process(T item) {
    return item.valid() && !item.audit().isEmpty();
}
~~~

là có ý nghĩa và compiler cho phép cả hai thao tác.

Nếu interface A extends B, bound **T extends A & B** có thể dư thừa vì thỏa A đã suy ra thỏa B. Dư thừa không tự làm API sai về mặt cú pháp, nhưng khiến người đọc khó nhận biết đâu là ràng buộc thực sự quan trọng. Hãy tối giản danh sách khi có thể.

## 11. Nếu chỉ có các interface bounds, thứ tự vẫn có ý nghĩa kỹ thuật

Hai khai báo sau cùng yêu cầu kiểu T thỏa cả Serializable và Comparable<T>:

~~~java
class First<T extends java.io.Serializable & Comparable<T>> {}

class Second<T extends Comparable<T> & java.io.Serializable> {}
~~~

Ở cấp độ quan hệ “T phải đáp ứng cả hai”, điều kiện của chúng tương tự. Tuy nhiên, **cận đầu tiên** quyết định type erasure của type variable T (khi bound đầu tiên là interface, erasure là interface đó):

- Trong First, erasure của T là **Serializable**.
- Trong Second, erasure của T là **Comparable**.

Bởi vậy việc đổi thứ tự các interface bounds trong một API đã được biên dịch và phát hành **có thể thay đổi chữ ký bytecode** của các field/method dùng T và ảnh hưởng binary compatibility. Khi thiết kế thư viện công khai, đừng coi việc đảo thứ tự là thay đổi thuần thẩm mỹ.

Ví dụ với class bound:

~~~java
class ClassFirst<T extends Number & Comparable<T>> {
    T item;
}
~~~

Erasure của T là Number, vì bound đầu tiên là Number. Với unbounded T, erasure thường là Object. Với interface-only bound **<T extends Runnable & AutoCloseable>**, bound đầu tiên Runnable quyết định erasure của T là Runnable.

**Quan trọng:** “erasure dùng bound đầu tiên” là quy tắc mô tả ở cấp JVM representation. Tại Java source, compiler vẫn cho phép dùng phương thức được bảo đảm bởi **mọi bounds**, không chỉ bound đầu tiên.

## 12. Ví dụ chạy hoàn chỉnh: thứ tự interface bounds và quyền gọi method

Lưu thành **InterfaceOrderDemo.java**:

~~~java
public class InterfaceOrderDemo {
    interface Named {
        String name();
    }

    interface Scored {
        int score();
    }

    static final class Student implements Named, Scored {
        private final String name;
        private final int score;

        Student(String name, int score) {
            this.name = name;
            this.score = score;
        }

        @Override
        public String name() {
            return name;
        }

        @Override
        public int score() {
            return score;
        }
    }

    static <T extends Named & Scored> String first(T value) {
        return value.name() + ":" + value.score();
    }

    static <T extends Scored & Named> String second(T value) {
        return value.name() + ":" + value.score();
    }

    public static void main(String[] args) {
        Student student = new Student("Lan", 95);
        System.out.println(first(student));
        System.out.println(second(student));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InterfaceOrderDemo.java
java InterfaceOrderDemo
~~~

Stdout:

~~~text
Lan:95
Lan:95
~~~

Cả hai generic methods đều được gọi với Student vì Student implement Named lẫn Scored. **first** có cận đầu tiên Named; **second** có cận đầu tiên Scored. Trình biên dịch vẫn cho cả hai methods gọi name() và score() do các interface bounds hợp lệ. Kết quả runtime giống nhau, nhưng erasure của T ở hai method signatures có thể khác nhau.

## 13. Giới hạn kiểu là giao (intersection), không phải hợp (union)

Hãy hiểu rõ các biểu thức:

~~~java
<T extends Runnable & AutoCloseable>
~~~

Có nghĩa T phải **đồng thời** là Runnable và AutoCloseable. Nó không chấp nhận bất kỳ Runnable *hoặc* bất kỳ AutoCloseable nào.

Dấu & tại đây biểu diễn giao điều kiện. Ví dụ generic method:

~~~java
static <T extends Runnable & AutoCloseable> void executeAndClose(T resource)
        throws Exception {
    try (resource) {
        resource.run();
    }
}
~~~

Ví dụ trên dành cho Java 17+, nơi biến resource là một parameter effectively final trong try-with-resources; parameter là effectively final khi không bị gán lại. AutoCloseable.close có thể ném Exception, nên method khai báo throws Exception. Runnable.run không có checked exception trong chữ ký.

Một object muốn dùng với executeAndClose phải implement cả Runnable và AutoCloseable. Không nên gán nhầm một class chỉ implement Runnable vào method này.

### Không nhầm với intersection cast

Java còn cho phép intersection type trong cast, ví dụ:

~~~java
// Chỉ minh họa một biểu thức cast:
Object source = /* đối tượng phù hợp */ null;
// Runnable task = (Runnable & AutoCloseable) source;
~~~

Cast ở runtime có các kiểm tra tương ứng, có thể ném ClassCastException khi object không thực thi những kiểu yêu cầu. Đây **không phải** cách thiết kế thay thế cho generic bounds khi muốn compiler kiểm tra quan hệ kiểu tại chữ ký method. Nếu không chắc về runtime object, không nên cast chỉ để “đưa nó qua” một API có bounds chặt.

## 14. Một class bound là final: xem khả năng tương thích với interfaces

Nếu class bound là final, không thể có một subtype mới kế thừa nó. Do đó nó phải **tự đáp ứng** các interface bounds bổ sung, nếu không sẽ không có type argument hợp lệ.

Ví dụ hợp lệ:

~~~java
class TextComparable<T extends String & Comparable<String>> {
    T value;
}
~~~

String final nhưng **đã implement Comparable<String>**, nên **String** có thể là type argument. Đây chỉ là ví dụ về bounds hợp lệ, chứ không phải khuyến nghị tạo type parameter T khi kiểu thực tế chỉ có thể là String. Trong trường hợp đó, dùng trực tiếp String thường đơn giản hơn.

Ví dụ không hợp lệ:

~~~java
// String là final và không implement Runnable:
// class TextRunnable<T extends String & Runnable> {}
~~~

Ngược lại, với class bound không final, một subclass có thể thực thi thêm các interfaces tương thích:

~~~java
abstract class BaseJob {
    abstract String label();
}

interface Schedulable {
    void schedule();
}

class ScheduledJob extends BaseJob implements Schedulable {
    @Override
    String label() {
        return "scheduled";
    }

    @Override
    public void schedule() {}
}

class JobHolder<T extends BaseJob & Schedulable> {
    T job;
}
~~~

ScheduledJob thỏa đồng thời class bound BaseJob và interface bound Schedulable. BaseJob không nhất thiết phải implements Schedulable từ trước.

## 15. Generic method áp dụng nhiều bounds cho phương thức riêng

Bounds không chỉ dùng trên generic classes:

~~~java
static <T extends Number & Comparable<T>> T min(T left, T right) {
    return left.compareTo(right) <= 0 ? left : right;
}
~~~

Type parameter T ở đây thuộc **generic method**, không phải một class chứa nó. Bất kỳ nơi gọi nào cũng phải đưa type arguments đáp ứng bounds. Phương thức có thể nằm trong class không generic hoặc class generic.

Nếu một class generic có T không bound, một static method bên trong không thể “mượn T của class” để thêm bounds. Static method cần tự khai báo type parameter của mình:

~~~java
class Holder<T> {
    static <U extends Number & Comparable<U>> U max(U a, U b) {
        return a.compareTo(b) >= 0 ? a : b;
    }
}
~~~

U độc lập với T của Holder. Bất kỳ cách dùng Holder<String> hay Holder<Integer> đều không làm thay đổi contract của static method max.

### Một phương thức dùng nhiều type parameters có bounds khác nhau

~~~java
static <A extends Number, B extends CharSequence> String summarize(A a, B b) {
    return b.length() + ":" + a.doubleValue();
}
~~~

Dấu phẩy tách **A** và **B**, không phải hai cận của cùng tham số. Một lời gọi summarize(3, "abcd") có thể suy luận A = Integer, B = String. Trong thân, compiler cho phép doubleValue() trên A và length() trên B theo đúng bound riêng.

## 16. Giới hạn tương thích còn phụ thuộc vào generic type arguments

Tính tương thích không chỉ xét tên interface. Những type arguments được dùng trong bounds có thể gây mâu thuẫn.

Một ví dụ F-bounded polymorphism hợp lệ:

~~~java
interface HasOrder<T> {
    int compareTo(T other);
}

class OrderedValue<T extends HasOrder<T>> {
    private final T value;

    OrderedValue(T value) {
        this.value = value;
    }

    boolean greaterThan(T other) {
        return value.compareTo(other) > 0;
    }
}
~~~

Cận **T extends HasOrder<T>** yêu cầu T implement chính giao diện dùng T làm type argument. Tham chiếu đến T bên trong bound **không phải lỗi vòng lặp tự động**. Dạng này phổ biến trong Comparable<T>, Enum<E extends Enum<E>>, hoặc API kiểu “self type”.

Một bound phức tạp hơn:

~~~java
class OrderedNumber<T extends Number & Comparable<? super T>> {
    private final T value;

    OrderedNumber(T value) {
        this.value = value;
    }

    int compare(T another) {
        return value.compareTo(another);
    }
}
~~~

**Comparable<? super T>** cho phép T có thể so sánh với T hoặc một supertype phù hợp của T. Đây là cách diễn đạt rộng hơn **Comparable<T>**, nhưng cần hiểu variance và contract thật của Comparable.

Dạng tự tham chiếu hợp lệ không đồng nghĩa với mọi giới hạn vòng tròn đều hợp lệ. Ví dụ **<T extends T>** là một cyclic bound không cung cấp cơ sở hợp lệ, khác với **<T extends Comparable<T>>** nơi bound được xây trên một interface cụ thể.

## 17. Luật trùng erasure của generic interface cần chú ý

Type erasure xóa thông tin type arguments trong nhiều vị trí của bytecode. Vì vậy những interface instantiations như **Comparable<String>** và **Comparable<Integer>** có cùng raw interface sau erasure là Comparable.

Một class không thể thừa kế hai specialization khác nhau của cùng generic interface:

~~~java
interface One extends Comparable<String> {}
interface Two extends Comparable<Integer> {}

// Không hợp lệ:
// class Both implements One, Two {}
~~~

Dạng bounds **<T extends One & Two>** cũng không tạo ra một type argument T có thể thực hiện cả hai đường kế thừa đó.

Tương tự, với lớp hoặc interface đã có hợp đồng generic, hãy tránh những phương thức chỉ khác nhau ở type arguments:

~~~java
// Cố ý sai:
class InvalidOverload {
    // void handle(java.util.List<String> a) {}
    // void handle(java.util.List<Integer> b) {}
}
~~~

Sau erasure, hai overload cùng có tham số List; compiler không thể phân biệt chúng theo chữ ký runtime cần thiết.

Đừng giải quyết bằng raw types: raw type chỉ làm giảm kiểm tra kiểu và có thể tạo unchecked warnings, không làm hai specialization trở thành hợp đồng tương thích.

## 18. Bound đầu tiên, erasure và khả năng tương thích nhị phân

Quy tắc quan trọng của Java: erasure của một type variable là erasure của **bound đầu tiên**; nếu không có bound, erasure thường là Object.

Ví dụ:

~~~java
class A<T> {
    T get() { return null; }
}

class B<T extends Number> {
    T get() { return null; }
}

class C<T extends Runnable & AutoCloseable> {
    T get() { return null; }
}
~~~

Tại mức chữ ký erasure:

| Khai báo | Erasure của T |
| --- | --- |
| A<T> | Object |
| B<T extends Number> | Number |
| C<T extends Runnable & AutoCloseable> | Runnable |

Với **C**, compiler vẫn kiểm tra cả Runnable và AutoCloseable khi dùng một giá trị T. Tuy nhiên chữ ký trong bytecode liên quan đến T dùng erasure Runnable, tức bound đầu tiên.

Điều này có thể tác động tới việc liên kết mã đã biên dịch trước đó nếu public API của một thư viện đổi thứ tự interface bounds và làm thay đổi erased method descriptor. Vì vậy khi bảo trì thư viện, **thay đổi thứ tự bounds phải được xem như một thay đổi tiềm ẩn ảnh hưởng ABI**, không nên chỉ xem như sắp xếp lại câu chữ.

Có thể dùng **javap -p -s** để khảo sát descriptors sau khi biên dịch. Cú pháp generic nhìn trong source và descriptor runtime không hoàn toàn giống nhau. Compiler có thể thêm bridge methods trong các trường hợp override generic để bảo toàn hành vi dispatch; đó là chi tiết liên quan, nhưng không thay đổi luật khai báo “class đứng trước” mà bài này tập trung.

## 19. Ví dụ chạy: AutoCloseable và Runnable đều bắt buộc

Lưu thành **CombinedResourceDemo.java**:

~~~java
public class CombinedResourceDemo {
    static final class Task implements Runnable, AutoCloseable {
        private final String name;

        Task(String name) {
            this.name = name;
        }

        @Override
        public void run() {
            System.out.println("run:" + name);
        }

        @Override
        public void close() {
            System.out.println("close:" + name);
        }
    }

    static <T extends Runnable & AutoCloseable> void execute(T task)
            throws Exception {
        try (task) {
            task.run();
        }
    }

    public static void main(String[] args) throws Exception {
        execute(new Task("compile"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CombinedResourceDemo.java
java CombinedResourceDemo
~~~

Stdout:

~~~text
run:compile
close:compile
~~~

Ở đây **Task** implement cả Runnable và AutoCloseable. Generic method execute biết task có run() và close() nhờ hai bounds. Cấu trúc try-with-resources gọi close() sau khi thân try chạy xong. Vì AutoCloseable.close được phép ném Exception, execute và main khai báo throws Exception.

Chú ý runtime có thể có exception trong run()/close() với những implementations khác, nhưng chương trình demo này in hai dòng xác định và không ném lỗi.

## 20. Các lỗi biên dịch và ngộ nhận phổ biến

### Lỗi 1: Đặt interface trước class bound

~~~java
// Sai:
class Bad<T extends Comparable<T> & Number> {}
~~~

**Sửa:** **class Good<T extends Number & Comparable<T>> {}**.

### Lỗi 2: Khai báo nhiều class bounds

~~~java
// Sai:
class Bad<T extends Number & Thread> {}
~~~

Một type parameter chỉ có thể có tối đa một class bound, và class bound phải đứng đầu.

### Lỗi 3: Dùng dấu phẩy thay cho & để nối nhiều cận của T

~~~java
// Sai về ý nghĩa mong muốn:
// <T extends Number, Comparable<T>>
~~~

Dấu phẩy phân tách type parameters. Muốn một T có hai bounds, viết **<T extends Number & Comparable<T>>**.

### Lỗi 4: Dùng implements trong giới hạn kiểu

~~~java
// Sai:
class Bad<T implements Runnable> {}
~~~

**Sửa:** **class Good<T extends Runnable> {}**.

### Lỗi 5: Giả định thỏa một bound là đủ

~~~java
class Pair<T extends Number & Comparable<T>> {
    T value;
}
~~~

Một subclass của Number **không** implement Comparable phù hợp sẽ không thể dùng làm T. Mọi type argument đều phải thỏa **tất cả** cận.

### Lỗi 6: Dùng class final không đáp ứng interface bổ sung

~~~java
// Sai:
class Bad<T extends String & Runnable> {}
~~~

String final và không implement Runnable. Không có cách tạo subclass String để bổ sung Runnable.

### Lỗi 7: Kết hợp hai đường Comparable khác type arguments

~~~java
// Sai:
// <T extends Comparable<String> & Comparable<Integer>>
~~~

Đây là xung đột cùng generic interface với hai specializations khác nhau.

### Lỗi 8: Cho rằng interfaces khác tên luôn tương thích

Hai interfaces có thể khai báo cùng method nhưng return types mâu thuẫn, hoặc thừa kế cùng generic interface qua type arguments không tương thích. Phải xem **cả hợp đồng kế thừa, signatures và erasure**, không chỉ tên interface.

### Lỗi 9: Tưởng giới hạn Number cho phép phép cộng T

~~~java
// Không hợp lệ:
static <T extends Number> T add(T a, T b) {
    // return a + b;
    return a;
}
~~~

Đoạn được comment vì toán tử **+** số học không được định nghĩa trên type variable T. Thân mẫu chỉ trả a để code hợp lệ nếu đem biên dịch; nó không thực hiện phép cộng. Nếu muốn tính tổng bằng double, dùng **a.doubleValue() + b.doubleValue()** với kiểu trả double và chấp nhận giới hạn độ chính xác.

### Lỗi 10: Coi một bound là bảo đảm non-null

Một T extends Number vẫn có thể là null. Gọi doubleValue() khi receiver null sẽ ném NullPointerException. Bounds kiểm tra **kiểu tĩnh**, không tự ép **giá trị runtime** phải tồn tại.

### Lỗi 11: Nghĩ thứ tự interfaces luôn có thể đổi không hệ quả

Khi không có class bound, interface đầu tiên quyết định erasure của T. Đổi thứ tự có thể đổi erased descriptors, đặc biệt đáng lưu ý với thư viện đã phát hành.

### Lỗi 12: Hiểu & trong generic bound như toán tử bitwise

Ở đây **&** là dấu nối intersection bounds trong khai báo kiểu. Nó khác toán tử bitwise AND trên những giá trị số nguyên và boolean expressions.

### Lỗi 13: Cho rằng một interface bound buộc viết new T()

Bound cho phép truy cập members do bound khai báo; nó **không** bảo đảm một constructor cụ thể hay làm **new T()** hợp lệ. Khi cần tạo object, truyền Supplier<? extends T>, factory hoặc type token với hợp đồng thích hợp.

### Lỗi 14: Dùng lower bound bằng super trong type parameter declaration

~~~java
// Sai:
// class Bad<T super Number> {}
~~~

Từ khóa **super** phù hợp với **lower-bounded wildcard** như **List<? super Integer>**, không phải khai báo type parameter. Với type parameter, sử dụng **extends** cho upper bounds.

## 21. Hướng dẫn thiết kế API với nhiều bounds

Không phải lúc nào khai báo nhiều bounds cũng tốt. Hãy bắt đầu từ những thao tác thực sự cần:

- Nếu chỉ gọi **doubleValue()**, **<T extends Number>** là đủ.
- Nếu cần gọi **compareTo(T)**, cân nhắc **<T extends Comparable<T>>** hoặc biến thể **Comparable<? super T>** phù hợp.
- Nếu cần cả doubleValue và compareTo, **<T extends Number & Comparable<T>>** diễn đạt hợp đồng.
- Nếu cần hai hành vi độc lập, có thể dùng **<T extends InterfaceA & InterfaceB>**.
- Nếu thứ tự/chiến lược hành vi thay đổi theo nơi gọi, đôi khi **truyền Comparator, Function hoặc strategy object** rõ ràng và linh hoạt hơn việc bắt T implement thêm interface.
- Nếu class bound quá chặt làm API không nhận được kiểu khác hữu ích, cân nhắc thiết kế lại quanh một interface chung hoặc một adapter.

Ví dụ thay một yêu cầu Comparable bằng Comparator:

~~~java
static <T extends Number> T greater(
        T first, T second,
        java.util.Comparator<? super T> comparator) {
    return comparator.compare(first, second) >= 0 ? first : second;
}
~~~

Phương thức giữ T extends Number, nhưng hành vi so sánh được truyền vào. Caller có thể chọn comparator mà không buộc chính T phải implement Comparable<T>. Đó là lựa chọn thiết kế, không phải cách “lách” compiler: chữ ký method vẫn thể hiện đầy đủ dữ liệu và hành vi cần thiết.

### Checklist trước khi khai báo multiple bounds

1. T là một type parameter hay bạn thật ra cần nhiều type parameters riêng?
2. Các cận được nối bằng **&** và chỉ có một **extends** sau tên T?
3. Nếu có class bound, nó đã đứng đầu chưa?
4. Có vô tình đưa hai class types vào danh sách không?
5. Những interfaces có trùng các generic supertypes nhưng truyền type arguments khác nhau không?
6. Có method signatures/return types không thể cùng được hiện thực không?
7. Có một class final buộc một giao diện mà nó không implement không?
8. Type argument dự kiến như Integer, Double hay custom class có đáp ứng toàn bộ bounds không?
9. Các cận có dư thừa hoặc làm API khó dùng hơn cần thiết không?
10. Việc thay thứ tự interface bounds có làm đổi erasure của public API hiện tại không?

## 22. Bài thực hành tự kiểm tra

**Câu 1.** Vì sao **<T extends Number & Comparable<T>>** hợp lệ còn **<T extends Comparable<T> & Number>** không?

**Đáp án:** Number là class bound nên phải đứng đầu danh sách. Comparable<T> là interface và có thể đứng sau.

**Câu 2.** Có thể viết **<T extends Runnable & AutoCloseable>** không, khi không có class bound?

**Đáp án:** Có. Đây là hai interface bounds; T phải thực thi cả hai.

**Câu 3.** **<A extends Number, B extends CharSequence>** có bao nhiêu type parameters?

**Đáp án:** Hai: A và B. Dấu phẩy tách hai khai báo; nó không nối multiple bounds của một tham số.

**Câu 4.** Có thể dùng String với **<T extends Number & Comparable<T>>** không?

**Đáp án:** Không. String có Comparable<String>, nhưng không extends Number.

**Câu 5.** Một class extends Number nhưng không implement Comparable<?> có dùng được với T ở câu 4 không?

**Đáp án:** Không. Nó thiếu cận Comparable<T> tương ứng.

**Câu 6.** Nếu **<T extends Runnable & AutoCloseable>**, compiler có cho gọi run() và close() trên T không?

**Đáp án:** Có. Tuy nhiên close() theo AutoCloseable có thể ném Exception và cần được xử lý/khai báo đúng.

**Câu 7.** Vì sao **<T extends String & Runnable>** mâu thuẫn?

**Đáp án:** String final và không implement Runnable; không thể có subtype khác của String để thỏa interface.

**Câu 8.** Một type variable có thể có hai class bounds như Number & Thread không?

**Đáp án:** Không. Java chỉ cho tối đa một class bound, ở vị trí đầu tiên.

**Câu 9.** Hai interface riêng cùng kế thừa Comparable<String> và Comparable<Integer> có thể dùng đồng thời làm bounds không?

**Đáp án:** Không. Một type argument không thể có cùng generic superinterface Comparable với hai specialization khác nhau.

**Câu 10.** Với **<T extends Serializable & Comparable<T>>**, erasure của T là gì?

**Đáp án:** Serializable, vì đó là cận đầu tiên. Nếu đổi Comparable<T> lên trước, erasure thường là Comparable.

**Câu 11.** Với **<T extends Number & Comparable<T>>**, T có phải luôn khác null không?

**Đáp án:** Không. Giới hạn kiểu không bảo đảm non-null; cần kiểm tra hoặc hợp đồng runtime khác.

**Câu 12.** Bound **<T extends Comparable<T>>** có phải lỗi vòng tham chiếu vì T xuất hiện hai lần?

**Đáp án:** Không. Đây là dạng self-referential/F-bound hợp lệ, yêu cầu T có hợp đồng so sánh với T. Không đồng nghĩa với cyclic bound sai như T extends T.

**Câu 13.** Tại sao không nên thay đổi thứ tự interfaces trong một public generic API chỉ vì muốn sắp xếp lại?

**Đáp án:** Bound đầu tiên quyết định erasure, có thể ảnh hưởng chữ ký JVM và khả năng liên kết binary với mã đã biên dịch.

**Câu 14.** Nếu chỉ cần một chiến lược so sánh tùy chọn cho các Number, có nhất thiết phải dùng **<T extends Number & Comparable<T>>** không?

**Đáp án:** Không. Có thể dùng **<T extends Number>** cùng Comparator<? super T> được truyền vào, nếu đó là contract phù hợp hơn.

## 23. Tổng kết

Với nhiều giới hạn kiểu, Java dùng dạng **<T extends ClassBound & InterfaceA & InterfaceB>**. **Class bound, nếu có, bắt buộc đứng đầu; những bound tiếp theo là interface.** Điều kiện giữa các bounds là **AND**, nghĩa type argument phải đáp ứng tất cả.

Các bounds cũng phải **tương thích về hệ thống kiểu**: không được yêu cầu một final class thực hiện interface nó không hỗ trợ, không được kế thừa cùng generic interface với các type arguments mâu thuẫn và không được tạo ra những method contracts không thể cùng hiện thực. Trong source code, compiler cho phép gọi thành viên được bảo đảm bởi mọi bounds; trong bytecode, **bound đầu tiên** quyết định erasure của type variable. Hiểu cả hai tầng này giúp viết generics đúng cú pháp, an toàn kiểu và ổn định khi thiết kế API có kế thừa phức tạp.
