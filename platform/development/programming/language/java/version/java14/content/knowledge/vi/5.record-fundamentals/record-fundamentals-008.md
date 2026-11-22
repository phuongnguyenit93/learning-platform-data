# Giới hạn kế thừa và triển khai interface của Java record

## 1. Record là một class, nhưng có hợp đồng kế thừa cố định

Một `record` là **một dạng class đặc biệt** dành cho dữ liệu được xác định rõ bằng danh sách *record components*. Ví dụ:

~~~java
record Product(String id, long priceCents) {}
~~~

Java tự tạo các thành phần thiết yếu: field `private final` cho `id` và `priceCents`, các accessor `public id()` và `public priceCents()`, constructor tương ứng, cùng `equals`, `hashCode` và `toString`. Về mặt mô hình kiểu, `record` vẫn là class, vẫn có thể chứa phương thức instance, khai báo phương thức `static` và **triển khai interface**. Tuy nhiên, nó **không tham gia kế thừa class thông thường**.

Các quy tắc đang áp dụng trong Java hiện đại:

- Mỗi record class có **superclass trực tiếp, cố định** là `java.lang.Record`; `java.lang.Record` kế thừa `java.lang.Object`. Đây là quan hệ được Java tự thiết lập.
- Cú pháp khai báo record **không có mệnh đề `extends`**. Không thể tự viết `extends BaseClass`, `extends Record` hay `extends Object`.
- Mỗi record class **ngầm là `final`**. Không một class hay record nào được phép kế thừa từ record đó. Có thể viết `final record ...` nhưng từ khóa `final` là thừa.
- Một record **không được khai báo `abstract`, `sealed` hoặc `non-sealed`**. Lý do thực tế: bản thân record là class cụ thể, không có subclass để hoàn thành các phương thức chưa triển khai hay mở rộng trạng thái.
- Record **được viết `implements`** để triển khai một hoặc nhiều interface, kể cả interface generic hoặc sealed interface nếu thỏa điều kiện `permits`.

Record trở thành tính năng ổn định từ **Java 16**; các ví dụ thực hành bên dưới dùng **Java 17+**, không phụ thuộc cú pháp preview cũ. Mặc dù chương học nằm trong module Java 14, các quy tắc được trình bày là quy tắc còn áp dụng hiện nay.

Bảng quyết định nhanh:

| Khai báo hoặc quan hệ | Hợp lệ? | Giải thích |
| --- | --- | --- |
| `record Point(int x, int y) {}` | Có | Record class thông thường |
| `final record Point(int x, int y) {}` | Có | `final` được phép ghi tường minh nhưng không cần |
| `record Point(int x, int y) implements Printable {}` | Có, nếu đáp ứng giao diện | Record có thể triển khai interface |
| `record Point(int x, int y) implements A, B {}` | Có, nếu đáp ứng cả A và B | Java cho phép nhiều interface |
| `record Child(int x) extends Parent {}` | Không | Cú pháp record không có `extends` |
| `record Child(int x) extends Record {}` | Không | Superclass `Record` đã được cố định ngầm, không khai báo tường minh |
| `class Child extends Point {}` | Không | `Point` là `final` |
| `abstract record Point(int x) {}` | Không | Record không được `abstract` |
| `sealed record Point(int x) {}` | Không | Record không được `sealed` |
| `record Success(String id) implements Result {}` với `sealed interface Result permits Success` | Có | Record là kiểu triển khai cuối nhánh, ngầm `final` |

Các ví dụ tên `Printable`, `A`, `B` và `Result` trong bảng giả định đã có khai báo interface tương ứng.

## 2. Phân biệt superclass với superinterface

Giả sử có khai báo:

~~~java
interface Coded {
    String code();
}

interface Displayable extends Coded {
    default String label() {
        return "Code=" + code();
    }
}

record Ticket(String code) implements Displayable {}
~~~

Ở đây:

1. `Ticket` có **superclass trực tiếp `java.lang.Record`**, không phải `Displayable`.
2. `Ticket implements Displayable`; vì `Displayable extends Coded`, một đối tượng `Ticket` đồng thời là `Displayable` và `Coded`.
3. Record tự sinh accessor `public String code()`. Phương thức này đáp ứng hợp đồng `String code()` của `Coded` mà không cần khai báo lại.
4. `label()` là phương thức `default` trong interface `Displayable`, được record kế thừa và có thể gọi `code()`.
5. `Ticket` vẫn là subtype của `Record` và `Object`. Có thể dùng `instanceof Record`, `getClass()` và các phương thức kế thừa thích hợp từ `Object`.

Có thể mô tả quan hệ kiểu như sau:

~~~text
java.lang.Object
    ↑ superclass
java.lang.Record
    ↑ superclass (ngầm, cố định)
Ticket  —— implements ——> Displayable —— extends ——> Coded
    (final)
~~~

Mũi tên `implements` mô tả hợp đồng interface và không làm thay đổi superclass. Đừng nhầm “không được `extends` một class” với “không có quan hệ subtype”: record có thể sử dụng tính đa hình qua interface bình thường.

## 3. Record có thể triển khai nhiều interface

Java cho phép record khai báo nhiều interface bằng dấu phẩy trong `implements`, ví dụ:

~~~java
record Purchase(String code, int priceCents)
        implements Displayable, Priced, Comparable<Purchase> {
    @Override
    public int compareTo(Purchase other) {
        return Integer.compare(this.priceCents, other.priceCents);
    }
}
~~~

Đây là **một khai báo minh họa**, với điều kiện `Displayable` và `Priced` đã được định nghĩa phù hợp; chương trình đầy đủ xuất hiện ở phần 5.

Mỗi interface yêu cầu một điều khác nhau:

- `Displayable` yêu cầu `code()` thông qua `Coded`, và có sẵn `default label()`. Record component `String code` đã tạo accessor đáp ứng yêu cầu.
- `Priced` yêu cầu `int priceCents()`. Component `int priceCents` tạo đúng accessor nên không cần viết lại.
- `Comparable<Purchase>` đòi hỏi `compareTo(Purchase)`. Không có record component nào tự tạo `compareTo`, vì vậy phải cài đặt cụ thể, ví dụ dùng `Integer.compare` tránh phép trừ so sánh có thể tràn số.

Dù record ngầm `final`, biến kiểu interface vẫn có thể trỏ đến đối tượng record:

~~~java
Displayable display = new Purchase("P-01", 1200);
Priced priced = (Priced) display;
Comparable<Purchase> order = (Comparable<Purchase>) display;
~~~

Đoạn này là ví dụ đặt trong cùng phạm vi có các interface và record đã định nghĩa, **không phải chương trình độc lập**. Cast hợp lệ khi đối tượng thực sự triển khai interface đích. Trong chương trình thực tế, chọn khai báo biến trực tiếp với interface phù hợp khi có thể, tránh cast không cần thiết.

Không có giới hạn “chỉ một interface” cho record. Giới hạn là các hợp đồng interface phải đồng thời tương thích: chữ ký phương thức, kiểu trả về, phương thức trừu tượng, và xung đột giữa các phương thức `default` đều phải được giải quyết.

## 4. Generated accessor có thể đáp ứng interface, nhưng không đoán tên hộ bạn

Mỗi record component `T property` sinh ra accessor `public T property()`, ví dụ:

~~~java
record User(String name, int age) {}
~~~

Record này tự có `name()` và `age()`. Nếu interface khai báo `String name()`, thì `User` chỉ cần `implements HasName` là đủ (giả sử `HasName` chỉ yêu cầu phương thức này).

Nhưng nếu interface yêu cầu `String getName()`, accessor `name()` **không phải cùng chữ ký**. Record phải tự bổ sung `getName()`:

~~~java
interface HasDisplayName {
    String getName();
}

record User(String name, int age) implements HasDisplayName {
    @Override
    public String getName() {
        return name;
    }
}
~~~

Đây là đoạn mã độc lập về mặt khai báo kiểu, không có phương thức `main`. `@Override` giúp compiler kiểm tra chính xác rằng phương thức thật sự cài đặt hợp đồng. Java không tự động suy ra `getName()` từ component `name`.

Nếu interface yêu cầu kiểu trả về không tương thích, record sẽ lỗi biên dịch. Ví dụ `interface Named { String name(); }` không thể được đáp ứng bằng `record WrongAccessor(int name) implements Named {}` vì accessor được sinh là `int name()`. Không thể tự định nghĩa thêm một `String name()` khác chỉ để khác kiểu trả về, vì Java không overload phương thức bằng return type. Cần thiết kế lại component hoặc hợp đồng interface.

Cũng cần lưu ý: một record có thể **tự khai báo accessor** cho component, nhưng accessor đó vẫn phải tuân theo các quy tắc của record (ví dụ kiểu trả về phải đúng kiểu component, phạm vi truy cập phù hợp). Record không được tự tạo instance field mới để “hỗ trợ” việc implement một interface; state của từng instance phải được mô tả bằng component.

## 5. Chương trình chạy được: interface thường, interface generic và sealed interface

Tạo tệp **`RecordInterfaceDemo.java`**. Chương trình dùng các kiểu nested bên trong lớp `RecordInterfaceDemo` để chỉ cần một tệp; các record nested là `static` ngầm định.

~~~java
import java.util.Objects;

public class RecordInterfaceDemo {
    interface Coded {
        String code();
    }

    interface Displayable extends Coded {
        default String label() {
            return "Code=" + code();
        }
    }

    interface Priced {
        int priceCents();
    }

    record Purchase(String code, int priceCents)
            implements Displayable, Priced, Comparable<Purchase> {
        Purchase {
            Objects.requireNonNull(code, "code");
            if (priceCents < 0) {
                throw new IllegalArgumentException("priceCents < 0");
            }
        }

        @Override
        public int compareTo(Purchase other) {
            return Integer.compare(this.priceCents, other.priceCents);
        }
    }

    sealed interface Outcome permits Accepted, Declined {
        String status();
    }

    record Accepted(String reference) implements Outcome {
        @Override
        public String status() {
            return "OK";
        }
    }

    record Declined(String reason) implements Outcome {
        @Override
        public String status() {
            return "ERROR";
        }
    }

    public static void main(String[] args) {
        Purchase first = new Purchase("P-01", 1200);
        Purchase second = new Purchase("P-02", 900);

        Displayable description = first;
        Priced price = first;
        Comparable<Purchase> comparable = first;

        System.out.println(description.label());
        System.out.println("price=" + price.priceCents());
        System.out.println("compare=" + comparable.compareTo(second));
        System.out.println("accessor=" + first.code());
        System.out.println("record=" + (first instanceof Record));
        System.out.println("super="
            + first.getClass().getSuperclass().getSimpleName());
        System.out.println("value=" + first);

        Outcome outcome = new Accepted("R-1");
        System.out.println("outcome=" + outcome.status());
        System.out.println("outcomeIsRecord=" + (outcome instanceof Record));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 RecordInterfaceDemo.java
java RecordInterfaceDemo
~~~

Stdout chính xác:

~~~text
Code=P-01
price=1200
compare=1
accessor=P-01
record=true
super=Record
value=Purchase[code=P-01, priceCents=1200]
outcome=OK
outcomeIsRecord=true
~~~

Phân tích:

- `description.label()` gọi phương thức `default` của interface, phương thức này dùng accessor `code()` được record tạo ngầm.
- `price.priceCents()` gọi accessor phù hợp với `Priced`.
- `compareTo(second)` được record triển khai tường minh; `Integer.compare(1200, 900)` trả `1`.
- `first instanceof Record` là `true`; `getSuperclass().getSimpleName()` cho `Record`, chứng minh superclass trực tiếp là `java.lang.Record`.
- `toString()` có biểu diễn record mặc định bao gồm tên record và component. Đây là một hành vi do class record cung cấp, không phải do interface `Displayable`.
- `Outcome` là **sealed interface**, chỉ cho các kiểu trong `permits` triển khai trực tiếp. Hai record `Accepted` và `Declined` là các kiểu triển khai được phép. Mỗi record vốn `final` nên không cần và không được tự khai báo `non-sealed`.
- `Purchase` có compact constructor kiểm tra đầu vào và thêm phương thức `compareTo`; việc có phương thức và logic kiểm tra không làm cho record trở thành class có thể được kế thừa.

### Sealed interface không làm record trở thành sealed record

Cần phân biệt hai khai báo:

- **Đúng:** `sealed interface Outcome permits Accepted, Declined`; các record `Accepted` và `Declined` triển khai interface này theo danh sách được phép.
- **Sai:** `sealed record Accepted(String reference) {}`; một record không được mang modifier `sealed`.

Record phù hợp để làm **lá của một phân cấp interface có kiểm soát**. Nếu cần phân cấp cho các nhóm kết quả, dùng sealed interface làm kiểu cha và nhiều record cụ thể làm các phương án dữ liệu. Java 17 hỗ trợ cả records và sealed interfaces ở trạng thái ổn định, không bật preview.

## 6. Interface generic, phương thức default và composition

Khi interface có hợp đồng trừu tượng không trùng tên component, record phải bổ sung phương thức đó. Với `Supplier<T>`, một component `value` sinh `value()`, không sinh `get()`; record phải triển khai `get()`. Nếu hai interface cung cấp hai phương thức `default` có cùng chữ ký và không có quan hệ giải quyết ưu tiên, record phải override để loại xung đột.

Vì record không thể kế thừa một class nghiệp vụ để tái sử dụng state và hành vi, hướng thiết kế thường phù hợp là **composition**: giữ đối tượng dữ liệu chung trong một record component, rồi ủy nhiệm khi cần.

Chương trình sau minh họa cả ba khả năng. Tạo tệp **`RecordAdditionalExamples.java`**:

~~~java
import java.util.function.Supplier;

public class RecordAdditionalExamples {
    interface HasName {
        String name();
    }

    interface HasDisplayName {
        String getName();
    }

    record FullName(String name) implements HasName, HasDisplayName {
        @Override
        public String getName() {
            return name;
        }
    }

    record Box<T>(T value) implements Supplier<T> {
        @Override
        public T get() {
            return value;
        }
    }

    record BaseInfo(String id) {}
    record Details(BaseInfo base, String description) {}

    interface Left {
        default String label() {
            return "Left";
        }
    }

    interface Right {
        default String label() {
            return "Right";
        }
    }

    record Both(String name) implements Left, Right {
        @Override
        public String label() {
            return Left.super.label() + "+" + Right.super.label();
        }
    }

    public static void main(String[] args) {
        HasName named = new FullName("Mai");
        HasDisplayName displayed = new FullName("Mai");
        Supplier<String> box = new Box<>("ready");
        Details details = new Details(new BaseInfo("A-01"), "OK");

        System.out.println("name=" + named.name());
        System.out.println("getter=" + displayed.getName());
        System.out.println("supplier=" + box.get());
        System.out.println("composition=" + details.base().id());
        System.out.println("defaults=" + new Both("sample").label());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 RecordAdditionalExamples.java
java RecordAdditionalExamples
~~~

Stdout chính xác:

~~~text
name=Mai
getter=Mai
supplier=ready
composition=A-01
defaults=Left+Right
~~~

Những gì ví dụ chứng minh:

- `HasName.name()` được đáp ứng bằng accessor sinh tự động từ component `name`, còn `HasDisplayName.getName()` được implement tường minh.
- `Box<T>` là record generic và triển khai `Supplier<T>` hợp lệ. Java không tự tạo `get()` từ `value()`.
- `Details` **chứa** `BaseInfo` làm component; nó không `extends BaseInfo`. Hai record vẫn có thể tổ chức dữ liệu phân tầng mà không cần class inheritance.
- `Left` và `Right` đều có `default label()`. `Both` phải override, và có thể gọi cụ thể từng phương thức bằng `Left.super.label()` và `Right.super.label()`.

Composition không tạo quan hệ subtype: `Details` **không phải** một `BaseInfo`, dù nó có component `BaseInfo base`. Nếu cần các kiểu cùng tuân theo giao diện, cho cả hai `implements` cùng interface, rồi dùng đa hình theo interface.

## 7. Các trường hợp lỗi biên dịch cần nhận biết

Dưới đây là **các ví dụ cố ý sai**, không ghép vào các chương trình runnable ở phần 5 và 6.

### Không được ghi `extends` khi khai báo record

~~~java
class Parent {}
record WrongExtends(int id) extends Parent {} // compile error
~~~

`javac` không chấp nhận cú pháp `extends` sau phần header `record WrongExtends(int id)`. Kể cả thay `Parent` bằng `java.lang.Record` cũng không hợp lệ.

### Không được tạo subclass của record

~~~java
record BaseRecord(int id) {}
class ChildRecord extends BaseRecord {} // compile error
~~~

Thông báo trọng tâm của `javac` là không thể kế thừa từ `final BaseRecord`. Record luôn là lá trong phân cấp class, mặc dù có thể là subtype của các interface.

### Không được để thiếu phương thức abstract của interface

~~~java
interface Action {
    void act();
}
record MissingMethod(int id) implements Action {} // compile error
~~~

Record không thể `abstract` để dành `act()` cho subclass, nên phải tự cài đặt phương thức hoặc không triển khai interface đó:

~~~java
record CompletedAction(int id) implements Action {
    @Override
    public void act() {
        System.out.println("Action id=" + id);
    }
}
~~~

Đoạn thứ hai hợp lệ về mặt khai báo kiểu; khi gọi `act()` trên instance `CompletedAction(3)`, nó in `Action id=3`.

### Interface yêu cầu kiểu trả về khác accessor được sinh

~~~java
interface Named {
    String name();
}
record WrongAccessor(int name) implements Named {} // compile error
~~~

Record tạo `int name()` nhưng hợp đồng interface cần `String name()`. Hai kiểu trả về này không tương thích. Chọn component `String name`, thay đổi hợp đồng interface, hoặc dùng tên phương thức riêng biệt với cách chuyển đổi rõ ràng.

### Không được đánh dấu record là abstract hay sealed

~~~java
abstract record AbstractRecord(int id) {} // compile error
sealed record SealedRecord(int id) {}     // compile error
~~~

Nếu cần một **kiểu gốc trừu tượng** với nhiều implementation cố định, sử dụng interface (có thể `sealed`) và các record cụ thể. Nếu cần **một superclass chứa state chung** mà các class con thực sự phải kế thừa, chọn class thông thường: record không dành cho quan hệ này.

## 8. Thiết kế đúng: khi nào nên dùng record + interface?

**Phù hợp với record** khi kiểu mang tập giá trị cố định, có danh tính dữ liệu rõ ràng qua components và bạn muốn nhiều đối tượng tuân theo cùng interface. Ví dụ một API có `Outcome` gồm `Accepted` và `Declined`, cùng được thao tác qua `Outcome.status()`. Record mặc định giữ các component ở field `private final`, giúp mô hình hóa dữ liệu ít biến đổi.

**Chọn class thường** nếu thiết kế thực sự yêu cầu kế thừa từ một superclass cụ thể, bổ sung state instance riêng ngoài các components, hoặc xây dựng phân cấp class có hành vi được override ở subclass. Không cố tạo một record làm base class rồi tìm cách `extends` nó ở các kiểu khác.

Một vài điểm cần phân biệt:

1. **`final` không đồng nghĩa với bất biến sâu.** Nếu component là `List`, `Map` hay đối tượng mutable, tham chiếu field của record là `final` nhưng đối tượng bên trong vẫn có thể đổi. Khi hợp đồng yêu cầu dữ liệu không đổi, cần copy/phòng vệ dữ liệu mutable trong constructor hoặc accessor.
2. **Interface không thêm instance fields vào record.** Các phương thức `default` có thể cung cấp hành vi chung dựa trên accessor; nhưng các interface không phải nơi lưu trạng thái riêng cho từng instance.
3. **Không suy luận tự động tên accessor theo phong cách getter.** Component `id` tạo `id()`; interface yêu cầu `getId()` thì phải triển khai `getId()` nếu muốn giữ hợp đồng đó.
4. **Đừng đặt phép tính nghiệp vụ dài trong phương thức accessor nếu điều đó làm thay đổi ngữ nghĩa component.** Có thể viết phương thức riêng để diễn đạt hành vi, còn accessor nên thể hiện giá trị thành phần nhất quán với mô hình record.
5. **Thư viện/framework cần superclass riêng có thể không phù hợp với record.** Hãy kiểm tra hợp đồng tích hợp thực tế: record không thể `extends` một abstract base class, kể cả khi framework yêu cầu.
6. **Thứ tự thiết kế tốt:** định nghĩa hợp đồng interface → chọn components đáp ứng dữ liệu cần công khai → xem accessor có tự thỏa phương thức interface không → bổ sung phương thức còn thiếu → giải quyết xung đột default → chọn `sealed interface` khi tập biến thể cần đóng.

## 9. Bài tự kiểm tra nhanh

**Câu 1.** Tại sao `record B(int n) extends A {}` không biên dịch dù `A` là `java.lang.Record`?  
Vì grammar của record không có `extends`; superclass `Record` được gán ngầm.

**Câu 2.** `record User(String id) implements Identified {}` với `interface Identified { String id(); }` có cần viết lại `id()` không?  
Không. Accessor `public String id()` được compiler sinh và đáp ứng đúng hợp đồng interface.

**Câu 3.** `record User(String id) implements Identified {}` với `interface Identified { String getId(); }` có tự hợp lệ không?  
Không. `id()` và `getId()` là hai tên phương thức khác nhau; cần cài đặt `getId()`.

**Câu 4.** Một record được `implements Comparable<RecordType>` không?  
Được, nếu record cài đặt `compareTo(RecordType)` với đúng chữ ký.

**Câu 5.** Một record được `implements sealed interface` không?  
Được, nếu là implementation trực tiếp được `permits` cho phép (hoặc thỏa quy tắc khai báo các subtype được phép trong cùng compilation unit). Record vẫn `final`; không được khai báo record `sealed`.

**Câu 6.** Muốn tái sử dụng dữ liệu từ một record khác, nên dùng `extends` hay một component chứa đối tượng đó?  
Dùng **composition** bằng component hoặc giao diện chung tùy quan hệ thực tế. Chứa dữ liệu không tạo quan hệ kế thừa class.

## Tài liệu đặc tả chính thức

- Java Language Specification (JLS) 26, §8.10 *Record Classes*: giới hạn modifiers, superclass cố định, implement interfaces, components và accessors: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10
- JLS 26, §9.4 *Interface Member Declarations*: phương thức trừu tượng, `default` và quy tắc override: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-9.html#jls-9.4
- JLS 26, §8.1.6 *Permitted Direct Subclasses*: quy tắc lớp triển khai và sealed type: https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.1.6
- OpenJDK JEP 395 *Records* (tính năng ổn định từ Java 16): https://openjdk.org/jeps/395
- OpenJDK JEP 409 *Sealed Classes* (tính năng ổn định từ Java 17): https://openjdk.org/jeps/409