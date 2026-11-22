# Object là lớp gốc và các phương thức dùng chung trong Java

## 1. Tổng quan: tại sao phải hiểu `java.lang.Object`?

Trong Java, **`java.lang.Object` là superclass gốc của các class thông thường**. Nếu một class không khai báo `extends` một superclass khác, nó có `Object` là superclass trực tiếp theo quy tắc của ngôn ngữ. Nếu nó `extends` một class khác, chuỗi superclass cuối cùng cũng dẫn tới `Object`, trừ chính `Object`.

Bởi vậy, các Java objects thuộc các reference class thông thường có những **hành vi nền tảng** được khai báo ở `Object`: so sánh bằng nhau (`equals`), lấy hash (`hashCode`), biểu diễn văn bản (`toString`), lấy runtime class (`getClass`), thao tác monitor/đồng bộ (`wait`, `notify`, `notifyAll`), cùng cơ chế clone (`clone`) và legacy finalization (`finalize`). Không phải tất cả chúng đều nên được override hay gọi trực tiếp trong code ứng dụng.

~~~java
class Book {
    private final String title;

    Book(String title) {
        this.title = title;
    }
}
~~~

Đoạn class này **không khai báo `extends Object`**, nhưng một `Book` object vẫn có các instance methods phù hợp từ `Object`. Ví dụ:

~~~java
Book book = new Book("Java");
System.out.println(book.getClass().getSimpleName());
System.out.println(book.toString());
~~~

Đây là **fragment**, đặt trong method thích hợp. Dòng đầu in `Book`. Dòng thứ hai dùng implementation `Object.toString()` nếu Book không override; chuỗi mặc định thường có dạng tên class + `@` + chữ số hexadecimal của hash code, **không có giá trị cố định để đưa vào expected stdout**.

**Quan trọng:** `Object` mang những hợp đồng Java-level cụ thể, nhưng nó không phải nơi phù hợp để đặt mọi nghiệp vụ. Một biến kiểu `Object` chỉ cung cấp API chung; muốn diễn tả hợp đồng `pay()`, `render()` hoặc `getPrice()`, nên dùng class/interface mang ý nghĩa domain.

### 1.1. Phạm vi bài học

Bài Knowledge README này dành cho **Java 17+**, thuộc nhóm *Java Core → Class/Object → Lớp Object*, trình bày:

- `Object` trong hệ thống kiểu: class, interface, array, enum, record, primitive, null và boxing.
- Các methods do `Object` khai báo, accessibility và khi nào nên/không nên override.
- Reference identity so với logical/value equality.
- Hợp đồng `equals/hashCode` và tác động tới `HashMap`, `HashSet`.
- `toString`, `getClass` và runtime polymorphism.
- `clone`, `Cloneable`, shallow copy và lựa chọn copy constructor.
- Object monitor, `synchronized`, `wait`, `notify`, `notifyAll` và điều kiện dùng an toàn.
- `finalize` đã deprecated; quản lý tài nguyên bằng `AutoCloseable`.
- Lỗi phổ biến, case study, chương trình Java chạy độc lập, bài tập có đáp án.

Đừng nhầm **lớp Object** với **tư tưởng lập trình hướng đối tượng**: từ `Object` trong `java.lang.Object` là **tên một class cụ thể**, còn từ “object” có thể chỉ bất kỳ một instance reference type tương ứng.

## 2. `Object` nằm ở đâu trong class hierarchy?

Sơ đồ ví dụ:

~~~text
java.lang.Object
    |
    +-- Vehicle
    |      |
    |      +-- Car
    |
    +-- java.lang.Number
    |      |
    |      +-- java.lang.Integer
    |
    +-- java.lang.Enum<T>
    |      |
    |      +-- các enum types
    |
    +-- java.lang.Record
           |
           +-- các record classes
~~~

Đây là **sơ đồ khái niệm, không phải tất cả classes trong JDK**.

~~~java
class Vehicle {
}

class Car extends Vehicle {
}
~~~

- `Vehicle` có superclass trực tiếp `Object`.
- `Car` có superclass trực tiếp `Vehicle`, và superclass gián tiếp `Object`.
- `Car` là subtype của `Vehicle` và `Object`.
- Một object có runtime class Car có thể được giữ trong biến kiểu `Car`, `Vehicle` hoặc `Object` khi phép gán hợp lệ.

~~~java
Car car = new Car();
Vehicle vehicle = car;
Object any = car;
~~~

**Không có ba objects.** Ba reference variables trỏ đến cùng một Car object; upcasting không sao chép object, không gọi constructor thêm và không “xóa” state của Car.

### 2.1. Class không viết `extends` thì sao?

~~~java
class Plain {
}
~~~

Về ngữ nghĩa inheritance, `Plain` có direct superclass là `Object`. Không cần viết:

~~~java
class Plain extends Object {
}
~~~

vì `extends Object` tường minh thường không mang thêm ý nghĩa.

Riêng `Object` không có superclass. Không thể tạo một class hợp lệ nằm “trên” Object bằng `extends` thông thường.

### 2.2. `Object` và interface khác nhau

Interface **không khai báo `extends Object` như một class superclass**. Interfaces có cơ chế thừa kế superinterfaces riêng. Tuy vậy, một object cụ thể triển khai interface vẫn là instance của một class, và class ấy có quan hệ tới `Object`.

~~~java
interface Printable {
    void print();
}

class Invoice implements Printable {
    @Override
    public void print() {
        System.out.println("Invoice");
    }
}
~~~

`Invoice` là subtype của `Printable` và `Object`. Một biến kiểu `Printable` có thể gọi những public instance methods liên quan tới `Object` theo quy tắc interface/type lookup (như `toString()`), nhưng không có nghĩa `Printable extends Object` theo cú pháp class inheritance.

**Mấu chốt:** superclass quan hệ giữa **classes** khác với superinterface quan hệ giữa **interfaces**. `Object` là superclass gốc, không phải một interface nghiệp vụ chung.

### 2.3. Mảng cũng là objects

Mảng trong Java là **reference types và là objects**. Ví dụ:

~~~java
int[] numbers = {1, 2, 3};
Object value = numbers;
System.out.println(value instanceof Object); // true
~~~

Mảng có runtime class riêng, dùng các methods phù hợp của Object và có field đặc biệt `length`. Mảng của kiểu nguyên thủy vẫn là object, dù **phần tử** của chúng là primitive values.

Một điểm quan trọng: `int[]` không có equals nội dung giống `Arrays.equals` theo mặc định. Hai mảng riêng biệt có cùng phần tử thường **không bằng nhau** nếu dùng method `equals` inherited from Object. Để so nội dung, dùng `java.util.Arrays.equals` (hoặc `Arrays.deepEquals` cho cấu trúc object arrays lồng nhau phù hợp).

### 2.4. Primitive values không phải Objects

Các primitive types `int`, `long`, `double`, `boolean`, `char`... **không kế thừa Object**, vì chúng không phải reference class types.

~~~java
int count = 5;
// count.toString(); // Không hợp lệ: primitive int không có method.
~~~

Nhưng Java có **autoboxing** khi chuyển primitive sang reference wrapper:

~~~java
Object value = 5; // int được boxing thành Integer.
System.out.println(value.getClass().getSimpleName()); // Integer
~~~

Điều này không có nghĩa primitive `int` đột nhiên là subtype của Object. **Integer object** là reference object, còn `int` là primitive value.

### 2.5. `null` không phải một Object instance

~~~java
Object value = null;
System.out.println(value instanceof Object); // false
~~~

`null` là một giá trị đặc biệt có thể gán cho reference variables thích hợp, nhưng **không là instance của Object hoặc bất kỳ class nào**. `value.toString()` hay `value.getClass()` khi `value == null` ném `NullPointerException`.

## 3. Bảng những phương thức quan trọng của `Object`

| Method / nhóm | Chức năng chính | Có được override? |
| --- | --- | --- |
| `public boolean equals(Object obj)` | So sánh equality theo hợp đồng của class | Có |
| `public int hashCode()` | Sinh hash code tương ứng hợp đồng equality | Có |
| `public String toString()` | Biểu diễn object dạng văn bản | Có |
| `public final Class<?> getClass()` | Lấy runtime class của object | **Không**, vì final |
| `protected Object clone() throws CloneNotSupportedException` | Tạo shallow copy theo cơ chế Cloneable/arrays | Có thể override trong giới hạn ngôn ngữ |
| `public final void wait()` | Chờ trên monitor của receiver | **Không**, final |
| `public final void wait(long timeoutMillis)` | Chờ có timeout theo quy tắc wait | **Không**, final |
| `public final void wait(long timeoutMillis, int nanos)` | Biến thể thời gian chờ | **Không**, final |
| `public final void notify()` | Đánh thức một thread đang wait trên monitor receiver | **Không**, final |
| `public final void notifyAll()` | Đánh thức tất cả threads đang wait trên monitor receiver | **Không**, final |
| `protected void finalize() throws Throwable` | Legacy finalization hook | Có thể override trong Java 17, **nhưng deprecated và không nên dùng** |

Ngoài các methods, `Object` có một **public no-argument constructor**, tham gia constructor chaining của classes trực tiếp mở rộng Object. Constructor không phải method được kế thừa như `toString()`.

**Lưu ý:** `equals` và `hashCode` là cặp thường cần thiết kế cùng nhau; `wait/notify` chỉ đúng khi có monitor ownership; `clone` bị hạn chế access và có nhiều vấn đề thiết kế; `finalize` không phải một destructor đáng tin cậy.

## 4. Chương trình hoàn chỉnh 1: các hành vi mặc định và runtime class

Tạo tệp **`ObjectBasicsDemo.java`**:

~~~java
public class ObjectBasicsDemo {
    static final class Ticket {
        private final String code;

        Ticket(String code) {
            this.code = code;
        }

        String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        Object original = new Ticket("T-1");
        Object same = original;
        Object another = new Ticket("T-1");

        System.out.println("Same ref = " + (original == same));
        System.out.println("Different ref = " + (original == another));
        System.out.println("Default equals same = "
                + original.equals(same));
        System.out.println("Default equals another = "
                + original.equals(another));

        System.out.println("Runtime class = "
                + original.getClass().getSimpleName());
        System.out.println("Ticket type = "
                + (original instanceof Ticket));

        Object primitiveArray = new int[]{1, 2};
        System.out.println("Array is Object = "
                + (primitiveArray instanceof Object));

        Object boxed = 42;
        System.out.println("Boxed class = "
                + boxed.getClass().getSimpleName());
    }
}
~~~

Biên dịch và chạy (JDK 17+):

~~~bash
javac -encoding UTF-8 ObjectBasicsDemo.java
java ObjectBasicsDemo
~~~

**Stdout chính xác:**

~~~text
Same ref = true
Different ref = false
Default equals same = true
Default equals another = false
Runtime class = Ticket
Ticket type = true
Array is Object = true
Boxed class = Integer
~~~

### 4.1. Tại sao `Default equals another = false` dù cùng code?

`Ticket` không override `equals`. Implementation `Object.equals` mặc định xét **identity**: chỉ true khi hai reference chỉ đến **cùng object**.

- `same = original`: hai biến trỏ cùng Ticket instance → `==` true, `equals` true.
- `another = new Ticket("T-1")`: object mới dù chứa cùng String code → `==` false, inherited `equals` false.
- `getClass()` trả **runtime class** Ticket, dù biến `original` khai báo kiểu `Object`.
- `Object boxed = 42` boxing primitive thành Integer, nên runtime class Integer.

Chương trình cố ý **không in `original.toString()` hay `hashCode()` mặc định**, vì giá trị mặc định có thể khác giữa các lần chạy và các JVMs; dùng những giá trị này làm expected output cố định là sai.

### 4.2. Nếu muốn hai Tickets có cùng code được coi là bằng nhau?

Bạn cần định nghĩa rõ **value equality contract** và override `equals` cùng `hashCode`, hoặc chọn một record/value object phù hợp. Đó là chủ đề phần tiếp theo.

## 5. `==`, `equals` và object identity

Với hai reference variables:

~~~java
Object a = new Object();
Object b = new Object();
Object c = a;
~~~

- `a == b` là false với hai lần `new Object()` riêng biệt.
- `a == c` là true vì cùng reference identity.
- `a.equals(c)` true.
- `a.equals(b)` false theo implementation mặc định của Object.

Toán tử `==` khi áp dụng cho hai reference expressions tương thích kiểm tra **reference identity**; nó không gọi method `equals`. Do đó không thể override `==` trong Java.

### 5.1. Vì sao `equals` lại có thể khác `==`?

Một class có thể override `equals` để định nghĩa **logical equality**. Ví dụ hai chuỗi String có cùng nội dung:

~~~java
String a = new String("java");
String b = new String("java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
~~~

Ở đây hai lần `new String(...)` tạo String objects riêng, nhưng `String.equals` so sánh nội dung ký tự. Không nên dựa vào **string interning** để thay `equals` bằng `==` trong so sánh nội dung.

### 5.2. `Objects.equals` để so sánh an toàn với null

~~~java
String a = null;
String b = null;

System.out.println(java.util.Objects.equals(a, b)); // true
~~~

`Objects.equals(a,b)` áp dụng quy tắc null-safe: nếu cả hai null thì true; nếu một null thì false; còn lại gọi `a.equals(b)`. Nó giúp tránh NPE khi giá trị tham chiếu có thể null.

Nhưng **`Objects.equals` không tự deep-compare arrays**: nếu class/object chỉ dùng inherited equals, nó vẫn so identity; với arrays cần `Arrays.equals` hoặc `Arrays.deepEquals` khi đúng nhu cầu.

### 5.3. Không dùng `getClass() == ...` thay `equals` một cách máy móc

Một số equality implementations chọn `getClass()` để yêu cầu hai runtime classes giống hệt. Số khác dùng `instanceof` để hỗ trợ subtype equality. Lựa chọn tùy contract và inheritance design; cả hai có trade-off.

Với **final value class**, `instanceof` thường đơn giản và không có subclass phá symmetry. Với hierarchy mở rộng có state mới, kế thừa equality có thể phức tạp; đôi khi nên dùng **composition**, `final class` hoặc record.

## 6. `equals(Object)`: lời hứa bình đẳng logic

`Object.equals(Object)` mặc định so **cùng instance**, nhưng class có thể override để định nghĩa **bằng nhau về giá trị hoặc miền nghiệp vụ**. Khi override, compiler chỉ kiểm tra chữ ký; lập trình viên chịu trách nhiệm về hợp đồng:

| Tính chất | Nghĩa |
| --- | --- |
| Phản xạ | `x.equals(x)` true nếu x không null |
| Đối xứng | `x.equals(y)` và `y.equals(x)` cùng kết quả |
| Bắc cầu | Nếu x bằng y và y bằng z thì x bằng z |
| Nhất quán | Không tự đổi kết quả nếu dữ liệu dùng so sánh không đổi |
| Khác null | `x.equals(null)` false nếu x không null |

Chữ ký override chính xác là `public boolean equals(Object other)`. Viết `equals(MyClass)` chỉ tạo **overload** chứ không thay Object.equals; dùng `@Override` để compiler giúp phát hiện. Nếu khác kiểu hoặc null, implementation thường trả false; đừng ép kiểu chưa kiểm tra.

**Vai trò trong chương:** bài tổng quan chỉ giới thiệu vì sao mọi object có method này. Bài *danh tính so với giá trị* xây dựng ngữ nghĩa equality theo domain; bài *hợp đồng equals/hashCode* kiểm tra symmetry/transitivity, code và edge cases bằng các ví dụ riêng.

## 7. `hashCode()`: gắn chặt với quyết định equality

`hashCode()` trả số nguyên `int`; collections như `HashMap` và `HashSet` sử dụng nó cùng với `equals()`. Quy tắc không được phá:

> Nếu `a.equals(b)` true thì `a.hashCode() == b.hashCode()` phải true.

**Không có chiều ngược lại:** hai objects khác nhau có thể trùng hash; đó là collision hợp lệ. Hash không phải memory address, unique ID, cryptographic digest hay persistent key. Nếu override `equals()` theo các fields `id`, `kind` thì triển khai `hashCode()` phải phản ánh **cùng lựa chọn equality**.

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hash(id, kind);
}
~~~

Đây là method fragment cần `id` và `kind` trong class, không phải chương trình độc lập. `Objects.hash` tiện dụng nhưng không bắt buộc; một công thức hash khác cũng hợp lệ nếu giữ hợp đồng.

**Cảnh báo về mutation:** thay field tham gia equality/hash khi object đang ở hash collection có thể làm lookup không còn hợp lệ. Bài hợp đồng hash phân tích thiết kế và kiểm thử; bài mutable key theo dõi hậu quả sau thay đổi state.

## 8. Chương trình hoàn chỉnh 2: override `equals/hashCode/toString` đúng hợp đồng

Tạo tệp **`EqualityContractDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class EqualityContractDemo {
    static final class Key {
        private final long id;
        private final String scope;

        Key(long id, String scope) {
            this.id = id;
            this.scope = Objects.requireNonNull(scope, "scope");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof Key key)) {
                return false;
            }
            return id == key.id && scope.equals(key.scope);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, scope);
        }

        @Override
        public String toString() {
            return "Key(" + id + "," + scope + ")";
        }
    }

    record Coordinate(int x, int y) {
    }

    public static void main(String[] args) {
        Key first = new Key(7, "A");
        Key sameValue = new Key(7, "A");
        Key different = new Key(8, "A");

        System.out.println("Same reference = "
                + (first == sameValue));
        System.out.println("Logical equals = "
                + first.equals(sameValue));
        System.out.println("Hash consistent = "
                + (first.hashCode() == sameValue.hashCode()));

        Set<Key> keys = new HashSet<>();
        keys.add(first);

        System.out.println("Contains same value = "
                + keys.contains(sameValue));
        System.out.println("Contains different = "
                + keys.contains(different));
        System.out.println("Display = " + first);

        Coordinate point = new Coordinate(2, 3);
        System.out.println("Record = " + point);
        System.out.println("Record equality = "
                + point.equals(new Coordinate(2, 3)));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 EqualityContractDemo.java
java EqualityContractDemo
~~~

**Stdout chính xác:**

~~~text
Same reference = false
Logical equals = true
Hash consistent = true
Contains same value = true
Contains different = false
Display = Key(7,A)
Record = Coordinate[x=2, y=3]
Record equality = true
~~~

### 8.1. Vì sao code này đúng?

- `Key` là `final class` với hai fields không thay đổi sau construction; không có subclass làm phức tạp symmetry của equality.
- `equals` kiểm tra identity nhanh, sau đó kiểm tra type bằng `instanceof` pattern matching của Java 17, rồi so sánh `id` và `scope`.
- `hashCode` dùng đúng những fields tham gia equality.
- Hai `Key` instances riêng nhưng cùng values có logical equality true, hash equal, nên `HashSet.contains` tìm được key phù hợp.
- `toString` trả chuỗi deterministic hữu ích cho debug/log.
- `Coordinate` là record; Java sinh methods `equals/hashCode/toString` theo record component contract, và `Coordinate[x=2, y=3]` là representation tiêu biểu của record trong Java 17.

### 8.2. Equality của record cũng cần xem mutable components

Một record như `record R(List<String> items) {}` có component reference final, nhưng List có thể mutable. Record-generated equality sẽ dùng component equality, không tự deep-copy hoặc đóng băng mutable List. Nếu muốn value object ổn định làm HashMap key, cần defensive-copy và cân nhắc các thành phần mutable.

### 8.3. Lưu ý về dữ liệu String

`String.equals` so sánh nội dung và String immutable. Với `scope` đã được constructor bảo đảm non-null, `scope.equals(key.scope)` hợp lệ. Nếu field có thể null, có thể dùng `Objects.equals(scope, key.scope)`.

## 9. Cách override `equals` sai thường gặp

### 9.1. Chỉ override `equals`

~~~java
class BadKey {
    private final String id;

    BadKey(String id) {
        this.id = id;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BadKey key && id.equals(key.id);
    }

    // Không override hashCode: vi phạm contract nếu equals true
}
~~~

Đây là minh họa một **thiết kế sai**. Hai BadKey objects có id bằng nhau có thể equals true nhưng sử dụng identity-based inherited hashCode khác nhau. `HashSet.contains(new BadKey("A"))` có thể false dù một BadKey "A" khác đã được thêm. Không dựa vào việc hash ngẫu nhiên có lúc trùng để coi implementation đúng.

### 9.2. Overload nhầm `equals`

~~~java
class Wrong {
    public boolean equals(Wrong other) {
        return true; // Không override Object.equals(Object).
    }
}
~~~

Compiler chấp nhận method overload, nhưng các API hoạt động qua kiểu `Object` vẫn có thể dùng inherited `equals(Object)`. Thêm `@Override` sẽ giúp phát hiện signature không khớp.

### 9.3. Kiểm tra `getClass()` và inheritance không có contract rõ

~~~java
if (other == null || getClass() != other.getClass()) {
    return false;
}
~~~

Đây là một **lựa chọn policy** trong equality, không phải công thức bắt buộc. Nó từ chối các subclasses khác class, có thể giữ symmetry dễ hơn; nhưng nếu superclass API hứa equality qua polymorphic subtypes, nó cũng có thể gây bất ngờ. Với giá trị, cân nhắc `record` hoặc `final` để tránh mở equality hierarchy phức tạp.

### 9.4. So các field bằng `==` khi cần content equality

~~~java
// return this.name == other.name; // Sai nếu muốn so nội dung String.
~~~

Hai String objects có nội dung bằng nhau vẫn có thể không cùng reference. Dùng `name.equals(other.name)` hoặc `Objects.equals(...)` theo null contract.

### 9.5. Tạo `hashCode` từ data mutable

Nếu `Person` equality/hash phụ thuộc `displayName`, sau khi đưa Person vào HashSet rồi đổi tên, key có thể nằm ở bucket không khớp với hash mới. Dùng immutable value keys, stable identity hoặc lifecycle rõ thay vì mutable hash keys.

## 10. `toString()`: biểu diễn object để đọc, log và debug

Implementation mặc định của `Object.toString()` có dạng khái niệm:

~~~text
runtimeClassName@hexHashCode
~~~

Nó không tự liệt kê private fields, không bảo đảm là một ID duy nhất và **không ổn định** khi chạy lại chương trình. Nếu object có ý nghĩa domain, override `toString()` thường hữu ích:

~~~java
@Override
public String toString() {
    return "Order{id='" + id + "', total=" + totalCents + "}";
}
~~~

Đây là **method fragment**; class cần các fields tương ứng.

### 10.1. Khi nào Java tự gọi `toString()`?

Một số thao tác như `System.out.println(object)`, `String.valueOf(object)` hoặc nối chuỗi với một object thường dùng biểu diễn string của object theo API tương ứng.

~~~java
Object value = new Coordinate(1, 2);
System.out.println(value);
~~~

Nếu `Coordinate` là record phù hợp, representation gồm tên record và các components. Với class không override toString, kết quả mặc định chỉ có tên class và hash formatting.

### 10.2. `toString` không phải JSON serialization hay API dữ liệu ổn định

- Nội dung `toString` thường phục vụ **diagnostics**, không phải wire protocol.
- Đừng parse `toString` để trao đổi dữ liệu giữa services.
- Đừng ghi password, token, session secret hoặc thông tin cá nhân nhạy cảm vào toString.
- Cẩn thận với object graph có cycles: nếu Parent.toString gọi Child.toString và ngược lại, có thể đệ quy vô hạn.
- Cẩn thận lazy relationships/ORM: toString có thể kích hoạt truy vấn hoặc loading ngoài ý muốn.
- Cẩn thận log object từ constructor: override `toString` của subclass có thể được gọi khi subclass fields chưa khởi tạo.

### 10.3. `toString` và dynamic dispatch

`Object value = new Child(); System.out.println(value)` có thể gọi `Child.toString()` nếu class Child override. Java dùng runtime receiver trong lời gọi instance method overridable; kiểu tĩnh Object không ép toString luôn dùng implementation của Object.

## 11. `getClass()` trả runtime class

`getClass()` là một **final method** của Object, trả một `Class<?>` đại diện cho runtime class của object. Ví dụ:

~~~java
Object value = "Java";
Class<?> type = value.getClass();
System.out.println(type.getSimpleName()); // String
~~~

Nếu biến khai báo Object nhưng giữ một String, getClass trả String class. `getClass` không tự “trở thành method của Object theo kiểu tĩnh” rồi báo Object.

### 11.1. So sánh `getClass()` với `instanceof`

~~~java
Number number = Integer.valueOf(5);

System.out.println(number instanceof Number);  // true
System.out.println(number instanceof Integer); // true
System.out.println(number.getClass() == Integer.class); // true
~~~

- `instanceof` kiểm tra **type compatibility** với target type, bao gồm subtype/interface implementation phù hợp.
- `getClass() == SomeClass.class` kiểm tra **chính xác runtime class object**, không coi một subclass là đúng bằng superclass class literal.
- `getClass()` ném NPE trên null receiver, còn `null instanceof SomeClass` false.

Không nên điều khiển mọi business behavior bằng chuỗi `if (value.getClass() == X.class)` nếu polymorphic virtual methods hoặc interfaces thể hiện contract rõ hơn.

### 11.2. Runtime class metadata có thể dùng cho reflection

`Class<?>` cung cấp API reflection như `getName()`, `getDeclaredMethods()`, `getSuperclass()`, v.v. Nhưng reflection chịu access/module rules và có overhead/thiết kế riêng. Với code Java Core bình thường, nên ưu tiên gọi methods có kiểu rõ ràng thay vì mỗi lần dùng `getClass()` và reflection để tìm method theo tên.

### 11.3. `getClass()` không được override

Bạn không thể:

~~~java
// @Override
// public Class<?> getClass() { ... } // Lỗi: Object.getClass() là final.
~~~

Nếu một object cần cung cấp **business type** khác runtime class, hãy thêm method riêng như `kind()`, `category()` hoặc một interface thích hợp. Không cố override getClass để giả runtime identity.

## 12. Chương trình hoàn chỉnh 3: `Object` reference vẫn có đa hình

Tạo tệp **`ObjectPolymorphismDemo.java`**:

~~~java
public class ObjectPolymorphismDemo {
    static class Message {
        String render() {
            return "Message";
        }

        @Override
        public String toString() {
            return "Message<" + render() + ">";
        }
    }

    static final class Alert extends Message {
        @Override
        String render() {
            return "Alert";
        }
    }

    public static void main(String[] args) {
        Object value = new Alert();

        System.out.println("Text = " + value);
        System.out.println("Runtime = "
                + value.getClass().getSimpleName());
        System.out.println("Message type = "
                + (value instanceof Message));

        if (value instanceof Alert alert) {
            System.out.println("Render = " + alert.render());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ObjectPolymorphismDemo.java
java ObjectPolymorphismDemo
~~~

**Stdout chính xác:**

~~~text
Text = Message<Alert>
Runtime = Alert
Message type = true
Render = Alert
~~~

### 12.1. Vì sao text là `Message<Alert>`?

1. `Object value = new Alert()` upcast một Alert object thành reference có compile-time type Object.
2. String concatenation dùng `toString()` trên runtime Alert object. Alert không override toString nên dùng `Message.toString()`.
3. Bên trong `Message.toString()`, lời gọi `render()` là virtual instance call và dispatch tới `Alert.render()`.
4. `getClass()` trả runtime class Alert; `instanceof Message` true do inheritance.
5. Java 17 pattern matching `instanceof Alert alert` cho phép gọi subtype-only API khi runtime type phù hợp.

**Đặc biệt:** ngay cả khi implementation `Message.toString()` được kế thừa, lời gọi virtual method bên trong vẫn có thể chọn subclass behavior.

## 13. `clone()` là gì?

`Object` khai báo:

~~~java
protected Object clone()
        throws CloneNotSupportedException
~~~

Mặc định method này có visibility **protected**, nên caller bên ngoài không thể gọi `someObject.clone()` tùy tiện chỉ vì object thuộc một class kế thừa Object.

Đối với một instance class thông thường, cơ chế `Object.clone()` sẽ kiểm tra khả năng clone theo `Cloneable`. Một class muốn dùng phương thức clone inherited tương ứng thường **implements `Cloneable`** và công bố method override với accessibility thích hợp. **`Cloneable` là marker interface**, không khai báo method `clone()` public.

### 13.1. `Object.clone` tạo shallow copy

Một shallow copy thông thường:

- Tạo một object khác với field values được copy từ object gốc.
- Primitive fields được copy giá trị.
- Reference fields được copy **reference values**, nên cả bản gốc và bản clone có thể trỏ tới **cùng mutable object bên trong**.
- Constructor thông thường của class **không được gọi theo cách tạo object bằng `new`** trong `Object.clone`.
- Các fields `final` trong shallow-cloned object cũng giữ copied reference values; final không biến object con thành immutable.

Do đó, `clone()` không phải giải pháp tự động cho deep copy hoặc invariant preservation. Nhiều Java APIs hiện đại ưu tiên **copy constructors, static factories, immutable values hoặc explicit copy methods** để kiểm soát rõ semantics.

### 13.2. Vì sao nhiều người ít dùng `Cloneable`?

API Cloneable/Object.clone có những nhược điểm thường gặp:

- `Cloneable` không công bố method `clone` trong interface.
- Object.clone là protected và khai báo checked exception.
- Shallow copy dễ gây aliasing ngoài ý muốn.
- Cách deep-copy graph gồm collections, mutable children và cycles cần domain-specific policy.
- Constructor/validation không chạy như ordinary new-construction path; có thể tạo inconsistency với invariants nếu không thiết kế cẩn thận.

Không nói rằng clone bị cấm hay luôn sai: arrays và một số thư viện dùng clone hợp lý. Nhưng cần biết chính xác copy contract.

### 13.3. Array cloning

Arrays hỗ trợ `clone()` và clone của một array tạo một **array object mới**. Ví dụ:

~~~java
int[] first = {1, 2};
int[] second = first.clone();

second[0] = 9;
System.out.println(first[0]);  // 1
System.out.println(second[0]); // 9
~~~

Với `Object[][]` hoặc array chứa mutable elements, cloning chỉ copy **mảng ngoài/các phần tử reference** theo shallow-copy semantics; không deep-copy mọi nested object.

## 14. Chương trình hoàn chỉnh 4: shallow clone và copy độc lập

Tạo tệp **`CloneCopyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CloneCopyDemo {
    static final class Tags implements Cloneable {
        private final List<String> values;

        Tags(List<String> source) {
            this.values = new ArrayList<>(source);
        }

        void add(String tag) {
            values.add(tag);
        }

        List<String> snapshot() {
            return List.copyOf(values);
        }

        @Override
        public Tags clone() {
            try {
                return (Tags) super.clone();
            } catch (CloneNotSupportedException ex) {
                throw new AssertionError(ex);
            }
        }

        Tags independentCopy() {
            return new Tags(values);
        }
    }

    public static void main(String[] args) {
        Tags original = new Tags(List.of("A"));
        Tags shallow = original.clone();
        Tags independent = original.independentCopy();

        shallow.add("B");
        independent.add("C");

        System.out.println("Original = " + original.snapshot());
        System.out.println("Shallow = " + shallow.snapshot());
        System.out.println("Independent = " + independent.snapshot());
        System.out.println("Different objects = "
                + (original != shallow));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CloneCopyDemo.java
java CloneCopyDemo
~~~

**Stdout chính xác:**

~~~text
Original = [A, B]
Shallow = [A, B]
Independent = [A, C]
Different objects = true
~~~

### 14.1. Giải thích từng dòng

- `Tags` implements Cloneable, và public override `clone()` gọi `super.clone()`.
- `super.clone()` tạo **Tags object mới** và copy reference `values`; hai Tags objects có **cùng ArrayList instance**.
- `shallow.add("B")` sửa list dùng chung, vì vậy `original.snapshot()` cũng có B.
- `independentCopy()` đi qua constructor `new Tags(values)`; constructor tạo `new ArrayList<>(source)` nên có **list riêng**.
- `independent.add("C")` chỉ sửa list riêng, tạo kết quả `[A, C]`.
- `original != shallow` true: hai Tags objects khác nhau dù share một nested list.

**`final List<String> values` không ngăn share mutable list reference.** Final chỉ giới hạn reassignment của field bên trong một object theo Java language rules.

### 14.2. Copy constructor có phải deep copy vô điều kiện?

Không. Ví dụ constructor `new ArrayList<>(source)` chỉ copy cấu trúc List, **không tự clone từng element mutable**. Chương trình trên dùng String immutable nên snapshot cấu trúc đủ minh họa. Nếu List chứa `MutableCustomer`, cần quyết định có tạo new MutableCustomer cho từng phần tử, chia sẻ immutable ID, hay sử dụng ownership protocol khác.

## 15. `wait()`, `notify()`, `notifyAll()` thuộc `Object`

Đây là những **final instance methods** của `java.lang.Object`, gắn với intrinsic monitor của **đúng object receiver**. Chúng không phải methods của `Thread` và khác `Thread.sleep()`.

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

Đây là snippet cần biến `lock`, `ready` và exception handling phù hợp. Thread gọi `lock.wait()` phải sở hữu monitor **của chính lock**; nếu không có thể ném `IllegalMonitorStateException`. Trong khi chờ, `wait` nhả monitor receiver rồi lấy lại trước khi kết thúc theo luật. `Thread.sleep` không nhả các monitors đã giữ.

`notify()` chọn một waiter, `notifyAll()` thông báo tới tất cả waiters trên cùng receiver, **không lập tức chuyển monitor** cho họ. Notification không phải dữ liệu được tích trữ; điều kiện `ready` mới là state cần bảo vệ. Dùng `while` để kiểm tra lại predicate sau khi tỉnh, kể cả spurious wakeups hoặc khi waiter khác đã tiêu thụ dữ liệu.

Bài này giới thiệu Object API và chương trình nhỏ ở mục 16. Chuyên đề `wait/notify/notifyAll` ở cuối chương phân tích sâu ordering, interrupt, timeout, lost signals, bounded buffers và `java.util.concurrent`.

## 16. Chương trình hoàn chỉnh 5: `wait`/`notifyAll` với condition và monitor đúng

Tạo tệp **`ObjectMonitorDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public class ObjectMonitorDemo {
    static final class Gate {
        private boolean open;

        synchronized void awaitOpen() throws InterruptedException {
            while (!open) {
                wait(); // this.wait(): hiện đang giữ monitor this
            }
        }

        synchronized void open() {
            open = true;
            notifyAll(); // this.notifyAll(), cùng monitor
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Gate gate = new Gate();
        AtomicBoolean passed = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
                passed.set(true);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        worker.start();
        gate.open();
        worker.join();

        System.out.println("Worker passed = " + passed.get());
        System.out.println("Main finished");
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ObjectMonitorDemo.java
java ObjectMonitorDemo
~~~

**Stdout trong việc chạy bình thường (không có interruption bên ngoài):**

~~~text
Worker passed = true
Main finished
~~~

### 16.1. Vì sao ví dụ tránh race thông báo “bị mất”?

Hai trình tự thread scheduling đều đúng:

- **Worker vào `awaitOpen` trước:** thấy `open=false`, gọi `wait()` và nhả Gate monitor. Main vào `open()`, đặt open=true và `notifyAll()`. Worker được đánh thức, lấy lại monitor, thấy open=true rồi rời method.
- **Main mở gate trước khi worker chờ:** Main đặt `open=true`. Worker vào `awaitOpen` sau đó thấy điều kiện đã đúng và **không cần wait**. Không phụ thuộc vào việc notification có “đến trước” hay không.

Trong cả hai trường hợp, condition `open` được truy cập dưới synchronized methods trên cùng Gate object. `worker.join()` làm main chờ worker kết thúc; `AtomicBoolean` ở đây cung cấp cách đơn giản để lưu kết quả thread-safe, mặc dù `join` cũng tham gia quan hệ memory visibility phù hợp.

### 16.2. Tại sao không gọi `notifyAll` mà bỏ gán state?

Nếu chỉ `notifyAll()` nhưng để `open=false`, worker có thể thức dậy rồi quay lại `wait()` vì điều kiện chưa đúng. Đây chính là thiết kế mong muốn: **thông báo không thay thế cập nhật condition**.

### 16.3. Vì sao bắt `InterruptedException` và restore interrupted status?

Trong worker, exception được bắt, sau đó `Thread.currentThread().interrupt()` khôi phục interruption status để code quản lý thread có thể biết thread đã được yêu cầu ngắt. Ứng dụng thật phải xác định policy khi bị interrupt: hủy công việc, cleanup hoặc truyền exception lên. Không nên âm thầm nuốt interruption trong một vòng wait vô hạn.

### 16.4. Có nên dùng Object monitor API trong ứng dụng mới?

Có thể dùng đúng, nhưng với nhiều tình huống concurrency hiện đại, APIs trong `java.util.concurrent` **dễ biểu đạt intent và giảm lỗi hơn**:

- `CountDownLatch`: chờ một số sự kiện hoàn tất.
- `BlockingQueue`: trao đổi dữ liệu producer/consumer.
- `Semaphore`: giới hạn số permit.
- `ReentrantLock` + `Condition`: điều kiện/lock có API tách bạch.
- `CompletableFuture`: biểu đạt asynchronous completion.
- `AtomicInteger`, `AtomicReference`: atomic state theo hợp đồng phù hợp.

Hiểu Object.wait/notify vẫn cần để đọc legacy code, giải thích intrinsic locks và hiểu nguyên lý monitor. Không nên thay bằng busy waiting hay `Thread.sleep` trong vòng lặp khi thực ra cần condition-based coordination.

## 17. `IllegalMonitorStateException`: lỗi monitor phổ biến

Sai:

~~~java
Object lock = new Object();
// lock.wait();      // Lỗi runtime: không giữ monitor lock
// lock.notifyAll(); // Lỗi runtime: không giữ monitor lock
~~~

Các lệnh sai đã comment. Cách đúng:

~~~java
Object lock = new Object();
synchronized (lock) {
    lock.notifyAll();
}
~~~

Nếu không có waiter, `notifyAll` đơn giản không đánh thức thread nào; bản thân lời gọi này không tạo một “notification token” được lưu lại cho tương lai. Vì thế cần condition shared state như `open=true` trong ví dụ Gate.

### 17.1. Khóa nhầm object cũng là lỗi

~~~java
Object lockA = new Object();
Object lockB = new Object();

synchronized (lockA) {
    // lockB.wait(); // Sai: sở hữu lockA không có nghĩa sở hữu lockB.
}
~~~

`wait/notify` gắn với **đúng monitor của receiver object**. Nên dùng một `private final Object lock = new Object();` hoặc synchronized methods với `this` khi lifecycle/access phù hợp. Không đồng bộ trên objects dễ được chia sẻ với code không tin cậy khi không chủ đích, vì code khác có thể làm tăng contention hoặc phá protocol.

### 17.2. Không gọi wait/notify qua một object chỉ vì nó là Object

Mọi object thường có monitor, nhưng **không phải mọi object nên được dùng làm lock**. Ví dụ khóa trên `String` literals hoặc public `Class` objects có thể khiến những đoạn code không liên quan vô tình dùng chung monitor. Một **private lock object** thường giảm coupling hơn khi thiết kế concurrency.

## 18. `Object.finalize()` là legacy API, không dùng làm destructor

Java 17 vẫn có legacy hook `Object.finalize()`, nhưng finalization đã bị **deprecated** và **không thích hợp** để quản lý vòng đời tài nguyên.

Các lý do:

- Không có bảo đảm finalizer sẽ chạy kịp thời.
- Không thể dựa vào thứ tự cleanup của finalizers như destructor đồng bộ.
- Finalization làm tăng complexity, rủi ro resource leak và những vấn đề an toàn.
- Đừng giữ file/socket/database connection chờ GC gọi finalize để đóng.
- Đừng viết business logic dựa vào thời điểm finalize.

**Thay thế thường phù hợp:** implement `AutoCloseable` và dùng **`try-with-resources`**; dùng `Cleaner` trong những trường hợp đặc biệt cần fallback cleanup khi thật sự hiểu giới hạn, nhưng không dùng như thay thế chính của close deterministic.

### 18.1. `AutoCloseable` không phải inherited Object method

`AutoCloseable` là một interface có method `close()`, **không phải** method do `Object` định nghĩa. Một class muốn có lifecycle close tường minh thường implements AutoCloseable:

~~~java
final class Resource implements AutoCloseable {
    private boolean closed;

    void use() {
        if (closed) {
            throw new IllegalStateException("Resource đã đóng");
        }
        System.out.println("Using resource");
    }

    @Override
    public void close() {
        closed = true;
        System.out.println("Resource closed");
    }
}
~~~

Một `try (Resource resource = new Resource()) { resource.use(); }` đảm bảo gọi close theo try-with-resources rules khi thoát scope.

### 18.2. Tài nguyên đóng đúng lúc khác object được GC

`Object` và GC không định nghĩa cho bạn một quy tắc “object không còn dùng thì resource được close ngay”. Với file/socket, ứng dụng phải có policy **ai sở hữu và khi nào close**. `try-with-resources` phù hợp với lexical ownership; resource quản lý lâu dài có thể cần explicit lifecycle manager.

### 18.3. Chương trình hoàn chỉnh 6: cleanup tường minh thay finalization

Tạo tệp **`ResourceLifecycleDemo.java`**:

~~~java
public class ResourceLifecycleDemo {
    static final class Resource implements AutoCloseable {
        private boolean closed;

        void use() {
            if (closed) {
                throw new IllegalStateException("Already closed");
            }
            System.out.println("Using resource");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("Resource closed");
            }
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            resource.use();
            System.out.println("Work finished");
        }
        System.out.println("After scope");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ResourceLifecycleDemo.java
java ResourceLifecycleDemo
~~~

**Stdout chính xác:**

~~~text
Using resource
Work finished
Resource closed
After scope
~~~

**Điều cần nhớ:** `Resource.close()` chạy do **try-with-resources**, không phải vì `Object.finalize()` hoặc GC quyết định ngay lúc ấy. `close()` ở ví dụ idempotent theo code để tránh in hai lần, nhưng idempotency phải được thiết kế theo hợp đồng resource thực tế.

## 19. Các phương thức Object có thể bị override và không thể override

Bảng thiết kế tổng hợp:

| Method | Nguyên tắc thiết kế |
| --- | --- |
| `equals` | Override khi class có một hợp đồng logical equality rõ, duy trì symmetry/transitivity |
| `hashCode` | Override nhất quán với equals nếu override equals |
| `toString` | Override để debug/diagnostics hữu ích, không rò secrets |
| `getClass` | Final; không override. Dùng runtime type metadata nếu thật sự cần |
| `clone` | Cân nhắc kỹ, protected và shallow copy; ưu tiên copy contract tường minh |
| `wait/notify/notifyAll` | Final; không override; dùng đúng monitor/condition protocol |
| `finalize` | Legacy/deprecated; tránh hoàn toàn trong thiết kế mới |

**Không phải tất cả objects cần override `equals`/`hashCode`.** Entity có identity riêng có thể dùng reference identity nếu đó là contract chủ đích. Value objects thường cần value equality; records hỗ trợ sẵn theo components.

### 19.1. Vì sao Object API chỉ là nền tảng?

Giả sử một method nhận `Object data`:

~~~java
void process(Object data) {
    System.out.println(data);
}
~~~

Method có thể gọi `data.toString()` (nếu non-null) vì Object công bố method đó, nhưng compiler không cho gọi `data.validateInvoice()` trừ khi type của data có API đó hoặc bạn cast/check về kiểu phù hợp.

Dùng `Object` cho mọi parameter sẽ làm mất semantic type safety. Nếu method cần `Invoice`, hãy viết `process(Invoice invoice)`. Nếu cần contract chung của nhiều kinds, định nghĩa interface như `Printable`/`Payable`.

## 20. Object identity, equality và hashing trong collections

### 20.1. `HashSet` và `HashMap`

`HashSet` dựa trên hashing/equality để xác định membership. `HashMap` dùng hashing/equality để tra cứu keys. Để keys hoạt động đáng tin:

- Equality contract phải đúng.
- Equal keys có equal hash codes.
- Fields tham gia equality/hash phải ổn định khi key đang ở collection, hoặc có chính sách remove/reinsert phù hợp.
- Không dùng hashCode như unique identifier hay bảo mật.

### 20.2. `IdentityHashMap` dùng reference identity

`java.util.IdentityHashMap` có identity-based semantics cho keys và khác với `HashMap` trong hợp đồng so sánh. Nó có thể hữu ích cho object graph traversal hoặc identity-sensitive use cases, nhưng **không thay HashMap mặc định** nếu nghiệp vụ dùng logical equality.

Không nhầm `System.identityHashCode(obj)` với `obj.hashCode()` đã override. API identityHashCode cung cấp hash theo identity semantics mặc định; **không có bảo đảm nó là mã độc nhất hoặc địa chỉ bộ nhớ**.

### 20.3. `TreeSet`/`TreeMap` dùng thứ tự so sánh

Sorted collections thường dựa vào `Comparator` hoặc `Comparable` để xác định ordering và trong nhiều tình huống cả notion of equivalent keys theo comparator. Điều đó có thể khác `Object.equals` nếu comparator không nhất quán với equality; vì vậy thiết kế comparator contract cũng cần cẩn thận.

### 20.4. Arrays

~~~java
int[] a = {1, 2};
int[] b = {1, 2};

System.out.println(a.equals(b));              // false
System.out.println(java.util.Arrays.equals(a, b)); // true
~~~

Hai arrays là hai object riêng. Array inherited equals từ Object xét identity; `Arrays.equals` so phần tử. Với nested arrays, cần hiểu shallow element equality vs deep array equality.

## 21. `Object` và generic types

Generics của Java hoạt động trên reference types. Ví dụ:

~~~java
java.util.List<String> names = java.util.List.of("Lan");
Object value = names;
~~~

`names` là một List object nên có thể giữ trong Object reference. Nhưng compiler không cho gọi `value.get(0)` nếu `value` có compile-time type Object; cần type có API List hoặc cast có kiểm tra.

### 21.1. Generic erasure và Object

Với unbounded type parameter `T`, các quy tắc **type erasure** có thể dùng Object ở bytecode representation cho một số positions. Nhưng không có nghĩa mọi T value là “Object class instance” theo nghĩa primitive; generic type arguments thông thường phải là reference types, và boxing/unboxing được áp dụng khi dùng primitive values như type-like arguments qua wrappers.

### 21.2. `List<Object>` không là superclass generic container của mọi `List<T>`

~~~java
java.util.List<String> names = java.util.List.of("Java");
// java.util.List<Object> all = names; // Không hợp lệ
~~~

Java generics thông thường **invariant**: `String extends Object` không đồng nghĩa `List<String> extends List<Object>`.

Nếu chỉ cần đọc values dưới kiểu Object:

~~~java
void inspect(java.util.List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}
~~~

Đây là method fragment. `List<?>` dùng wildcard để có thể nhận nhiều parameterized Lists phù hợp; code không được tùy tiện thêm một Object bất kỳ vào nó vì compiler không biết element type cụ thể.

## 22. `Object` và records trong Java 17

Record classes là một cách khai báo data carriers có generated implementations cho:

- `equals` theo record components.
- `hashCode` tương ứng.
- `toString` gồm record name/components.

~~~java
record Point(int x, int y) {
}
~~~

Với `new Point(1, 2)`, `toString` có representation `Point[x=1, y=2]`; hai Points có cùng components có equality true.

Nhưng không suy rộng “record luôn deep immutable”:

~~~java
record Group(java.util.List<String> names) {
    Group {
        names = java.util.List.copyOf(names);
    }
}
~~~

Compact constructor copy structure List. Vì String elements immutable, ví dụ dễ suy luận hơn. Nếu component là mutable object graph, record-generated equals/hashCode có thể quan sát state có thay đổi qua thời gian; cần defensive copying sâu tới mức hợp đồng domain yêu cầu.

Record là subtype của `java.lang.Record` và cuối cùng là Object, nhưng **không thể tự do `extends` một custom superclass khác**. `Record` khai báo những phương thức và contracts đặc thù; không phải mọi Object method có thể override như trong ordinary class hierarchy.

## 23. `Object` và enum

Mỗi enum type có cơ chế superclass đặc biệt qua `java.lang.Enum`, và Enum cuối cùng kế thừa Object. Enums có identity semantics ổn định cho constants; enum `equals` là final trong `Enum` nên không được tùy ý override để dùng logical equality khác. `Enum.hashCode` cũng final theo API.

~~~java
enum Mode {
    SAFE, FAST
}
~~~

`Mode.SAFE == Mode.SAFE` true. Dùng `==` để so enum constants là idiomatic, vì mỗi enum constant là singleton tương ứng trong runtime enum class loading context. Không cần override `equals` để so enum name.

**Không lấy hành vi enum làm ví dụ cho mọi class:** một ordinary value class có thể cần logical equality qua `equals`, trong khi enum identity của constants là một phần thiết kế ngôn ngữ.

## 24. `Object` và inheritance/polymorphism

Một class con có thể override những instance methods của Object được phép override. Ví dụ:

~~~java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return "Person(" + name + ")";
    }
}
~~~

Một `Object ref = new Person("Lan")` vẫn gọi `Person.toString()` khi `ref.toString()` được thực thi. Đây là **dynamic dispatch**, dù reference compile-time type Object.

### 24.1. Access modifier khi override

`equals`, `hashCode`, `toString` đều **public** trong Object. Overriding method không được giảm visibility xuống `protected`/package-private/`private`. Vì vậy chữ ký override:

~~~java
@Override
public String toString() {
    return "Readable";
}
~~~

là phù hợp; `protected String toString()` sẽ không hợp lệ do reducing visibility.

### 24.2. Method Object có `final` không bị override

`getClass()`, `wait(...)`, `notify()` và `notifyAll()` là final. Không thể “tùy chỉnh” cách JVM lấy runtime class hoặc hành vi monitor bằng overriding chúng. Cần abstraction/hành vi riêng nếu domain yêu cầu.

### 24.3. Hạn chế thiết kế: gọi overridable Object methods trong constructor

Superclass constructor có thể vô tình gọi `toString()`, `equals` hoặc `hashCode` trong khi subclass state chưa khởi tạo xong. Java vẫn dynamic-dispatch, khiến override đọc default values/null hoặc gây exceptions.

Ví dụ:

~~~java
class Base {
    Base() {
        System.out.println(this); // Có thể gọi Child.toString quá sớm
    }
}
~~~

Một subclass có `private final String id` gán sau `super()` không nhất thiết sẵn sàng trong `toString()` override lúc ấy. **Tránh gọi overridable methods và tránh công bố `this` quá sớm khi đang construction**.

## 25. `Object` không phải khuôn mẫu thiết kế copy/equality cho mọi domain

Nhiều kiểu object có bản chất khác nhau:

| Kiểu | Equality thường phù hợp | Copy / lifecycle thường phù hợp |
| --- | --- | --- |
| Immutable value object | So values theo thành phần | Tạo mới hoặc chia sẻ vì immutable |
| Entity có stable ID | Theo domain identity, có thể không giống reference identity | Thường không clone ngầm; quản lý lifecycle riêng |
| Mutable collection | Theo API collection như `List.equals` so elements | Copy cấu trúc hoặc immutable snapshot |
| Array | Mặc định reference identity | `clone` shallow / `Arrays.copyOf` |
| Thread/task/resource | Thường identity-based | Explicit lifecycle, không tùy tiện clone |
| Record | Components-based equality | Copy/new record, defensive-copy mutable components |
| Enum | Constant identity | Không tạo arbitrary copies, không clone |
| Proxy/framework entity | Theo contract/framework | Cẩn thận lazy state, transaction, identity |

**Không có công thức chung** như “class nào cũng phải override equals/hashCode/clone”. Trước khi override, cần trả lời:

1. Đây là entity hay value?
2. Người dùng muốn so cùng instance hay cùng nội dung?
3. Những fields tham gia equality có mutable không?
4. Object có thể nằm trong hash-based collection không?
5. Có subclass/proxy không?
6. Nếu copy, mutable parts có được chia sẻ không?
7. Object có resource/identity bên ngoài không thể clone tùy ý không?

## 26. Những nhầm lẫn dễ gặp

1. **“Chỉ class viết `extends Object` mới có Object methods.”** Sai: class thông thường không ghi extends cũng có superclass Object.
2. **“Primitive `int` là subclass của Object.”** Sai: primitive không là reference class; boxing tạo wrapper Integer object.
3. **“Interface extends Object như class.”** Sai về cú pháp; concrete implementing objects vẫn có Object-related members.
4. **“Mảng không phải Object vì có primitive elements.”** Sai: mảng là object dù phần tử primitive.
5. **“`null instanceof Object` true vì Object bao quát mọi thứ.”** Sai: null không là instance, kết quả false.
6. **“`Object.equals` mặc định so mọi fields.”** Sai: nó so reference identity.
7. **“`==` cho String luôn so nội dung.”** Sai: `==` so reference identity; `String.equals` so nội dung.
8. **“Override equals thôi là đủ.”** Sai nếu equality semantics khác identity; cần hashCode nhất quán.
9. **“Cùng hashCode nghĩa là equals true.”** Sai: hash collisions hợp lệ.
10. **“hashCode chính là địa chỉ memory.”** Không có bảo đảm; đừng dựa trên điều đó.
11. **“`toString` mặc định cho ID vĩnh viễn duy nhất.”** Sai; output có thể khác giữa runs và không phải stable ID.
12. **“Mọi `toString` nên in tất cả fields.”** Sai: có thể làm lộ secrets, cycles, lazy loading, performance issues.
13. **“`getClass()` trả kiểu khai báo biến.”** Sai: nó trả runtime class của object.
14. **“Có thể override `getClass()` để fake type.”** Sai: final method.
15. **“`clone()` mặc định deep-copy mọi object con.”** Sai: shallow copy.
16. **“Cloneable công bố public `clone()`.”** Sai: Cloneable là marker interface, Object.clone protected.
17. **“Final field tham chiếu khiến nested list immutable.”** Sai: final chỉ hạn chế reassign field.
18. **“`wait()` có thể gọi ngoài synchronized mà không cần lock.”** Sai: thiếu monitor ownership gây IllegalMonitorStateException.
19. **“`notify()` luôn đánh thức thread mình muốn.”** Sai: không có guarantee thread cụ thể được chọn.
20. **“`notifyAll()` nhả lock ngay lập tức.”** Sai: notifier vẫn giữ monitor cho đến khi unlock.
21. **“`wait()` thức dậy là condition đã đúng.”** Sai: cần kiểm tra lại trong `while`.
22. **“`Thread.sleep()` nhả monitor giống wait.”** Sai.
23. **“finalize() là destructor nên có thể đóng file trong đó.”** Sai: deprecated và không bảo đảm cleanup kịp thời.
24. **“Mọi Object nên override tất cả methods.”** Sai; lựa chọn phụ thuộc semantics của class.
25. **“`List<String>` là subtype của `List<Object>`.”** Sai: generic invariance.
26. **“Record deep-immutable trong mọi trường hợp.”** Sai với mutable reference components.
27. **“Object reference giúp gọi mọi method của runtime object.”** Sai: compiler dựa trên compile-time type khi kiểm tra API.
28. **“Object monitor đồng nghĩa thread-safety tự động.”** Sai: shared state cần synchronization protocol nhất quán.
29. **“`equals(Object)` có thể đổi thành `equals(MyType)` để override.”** Sai: đó là overload.
30. **“Có thể đổi `Object` thành class domain cụ thể chỉ bằng cast bất kể runtime type.”** Sai: không tương thích gây ClassCastException.

## 27. Bài tập tự kiểm tra có đáp án

**Câu 1.** Vì sao `class A {}` vẫn có method `toString()`?

**Đáp án:** Class thông thường không ghi extends có direct superclass `Object` theo Java language rules, nên thừa hưởng những members phù hợp từ Object.

**Câu 2.** `int x = 3;` có phải Object instance không?

**Đáp án:** Không. `int` là primitive; khi dùng `Object ref = x`, Java autoboxing thành Integer reference.

**Câu 3.** `int[] a = {1,2}; Object ref = a;` có hợp lệ không?

**Đáp án:** Có. Mảng là objects/reference types, có thể gán cho Object reference.

**Câu 4.** `new Object().equals(new Object())` trả gì?

**Đáp án:** False, vì đây là hai objects riêng và inherited Object.equals so reference identity.

**Câu 5.** `String a = new String("A"); String b = new String("A");` thì `a==b` và `a.equals(b)` ra sao?

**Đáp án:** `a==b` false do hai instances riêng, `a.equals(b)` true do nội dung String giống nhau.

**Câu 6.** Tại sao overriding `equals` cần overriding `hashCode`?

**Đáp án:** Vì contract bắt buộc equal objects có equal hash codes. Nếu không, HashMap/HashSet có thể tìm key sai.

**Câu 7.** Hai objects khác nhau có thể có cùng hashCode không?

**Đáp án:** Có. Collision hợp lệ; hash equality không đủ để kết luận logical equality.

**Câu 8.** `hashCode()` có thể dùng làm database primary key hoặc bảo mật token ổn định không?

**Đáp án:** Không. Hash code không đảm bảo unique, không ổn định xuyên runs và không phải cryptographic secret.

**Câu 9.** `Object v = new Dog(); v.getClass()` cho Object.class hay Dog.class?

**Đáp án:** Runtime class Dog. `getClass` không báo compile-time declaration type.

**Câu 10.** `v.toString()` có thể gọi implementation Dog dù biến v có type Object không?

**Đáp án:** Có. `toString` là overridable instance method, dynamic dispatch theo runtime object.

**Câu 11.** Có thể override `getClass()` trong subclass không?

**Đáp án:** Không. `Object.getClass()` là final.

**Câu 12.** `Objects.equals(null, null)` có cho true không?

**Đáp án:** Có. Nó là null-safe equality helper.

**Câu 13.** Hai arrays cùng elements, `a.equals(b)` có tự so nội dung không?

**Đáp án:** Không. Arrays thừa hưởng identity-based equals; dùng `Arrays.equals` hoặc `Arrays.deepEquals` theo nhu cầu.

**Câu 14.** Một class implements Cloneable có tự công bố public clone method không?

**Đáp án:** Không. Cloneable là marker interface; Object.clone là protected. Class cần thiết kế/public override nếu muốn expose clone.

**Câu 15.** Shallow clone của object có List field final có tạo List mới không?

**Đáp án:** Không tự động. Reference đến List được copy, nên clone và original có thể cùng dùng một mutable List.

**Câu 16.** Vì sao copy constructor thường rõ hơn clone?

**Đáp án:** Nó cho phép định nghĩa tường minh cần copy fields/objects nào, chạy validation và quyết định ownership/aliasing.

**Câu 17.** Vì sao `lock.wait()` phải ở synchronized(lock)?

**Đáp án:** Thread phải sở hữu monitor của receiver lock; nếu không có thể ném IllegalMonitorStateException.

**Câu 18.** Gọi `notifyAll` có nhả monitor ngay không?

**Đáp án:** Không. Notifier vẫn giữ monitor đến khi synchronized section kết thúc/unlock; waiters phải giành lại monitor để tiếp tục.

**Câu 19.** Khi được notify, waiter có thể giả định condition đúng không?

**Đáp án:** Không. Phải kiểm tra lại condition trong loop do spurious wakeup, cạnh tranh và thay đổi state.

**Câu 20.** Vì sao `Thread.sleep` không dùng thay `Object.wait` trong condition protocol?

**Đáp án:** Sleep không tự nhả monitor; wait đi cùng monitor/condition, nhả monitor theo semantics của wait.

**Câu 21.** `Object.finalize()` có bảo đảm close socket trước khi process kết thúc không?

**Đáp án:** Không. Finalization deprecated, không đảm bảo thời điểm hay việc thực thi kịp; dùng AutoCloseable/try-with-resources.

**Câu 22.** Một record có cần tự viết equals/hashCode/toString thông thường không?

**Đáp án:** Java sinh implementations theo record components; có thể override trong phạm vi ngôn ngữ/hợp đồng khi cần, nhưng không nên làm không nhất quán với giá trị record.

**Câu 23.** `IdentityHashMap` khác HashMap ở đâu?

**Đáp án:** Nó dùng identity semantics cho keys, không thay thế một map dựa trên logical equals/hashCode theo kiểu thông thường.

**Câu 24.** Vì sao key mutable trong HashSet nguy hiểm?

**Đáp án:** Nếu fields tham gia hash/equality thay đổi sau khi insert, lookup/remove có thể không tìm được key ở cấu trúc hash hiện tại.

**Câu 25.** `null.getClass()` có hợp lệ không?

**Đáp án:** Không. Null reference dereference ném NPE; null không là instance Object.

**Câu 26.** Có nên đặt method parameter là Object khi nghiệp vụ chỉ chấp nhận Order?

**Đáp án:** Thường không. Dùng Order hoặc interface cụ thể để compiler kiểm tra API và truyền đạt contract.

**Câu 27.** Có thể override `notify()` để tự tạo cơ chế thông báo riêng không?

**Đáp án:** Không. `Object.notify` là final. Tạo API riêng hoặc dùng java.util.concurrent primitives.

**Câu 28.** `super.toString()` luôn bỏ qua subclass hooks bên trong superclass implementation không?

**Đáp án:** Không. Super-call chọn superclass toString ở entry point, nhưng virtual calls phát sinh sâu hơn vẫn có thể dispatch đến subclass.

**Câu 29.** Nếu class không override equals thì có nhất thiết là thiết kế sai không?

**Đáp án:** Không. Với identity-oriented object, inherited Object.equals có thể đúng hợp đồng.

**Câu 30.** `Object` có thay thế được interface `Runnable` hay `PaymentGateway` không?

**Đáp án:** Không. Object cung cấp behaviors chung của object; interface domain cung cấp contract mà compiler và runtime có thể dùng đa hình một cách có ý nghĩa.

## 28. Checklist khi quyết định dùng Object API

1. **Đây là reference object hay primitive?** Phân biệt boxing và reference types.
2. **Có cần reference identity hay logical/value equality?** Đừng dùng `==` cho String content.
3. **Nếu override equals đã override hashCode nhất quán chưa?**
4. **Có dùng mutable data làm hash key không?** Xem stability.
5. **`toString` có rò secrets, cycles hoặc lazy-loading side effects không?**
6. **Có cần runtime class metadata không?** `getClass` trả concrete runtime type.
7. **Có lạm dụng exact class checks thay vì polymorphism không?**
8. **Nếu muốn copy, shallow copy có đủ không?** Xem nested mutable objects.
9. **Cloneable có thật sự cần không?** Cân nhắc copy constructor/factory.
10. **Có gọi wait/notify trên đúng monitor object và giữ monitor chưa?**
11. **Shared condition được cập nhật dưới synchronization protocol nhất quán không?**
12. **Waiter có dùng `while` để kiểm tra lại condition không?**
13. **Có xử lý interruption theo contract không?**
14. **Có cần CountDownLatch/BlockingQueue/Condition thay wait/notify không?**
15. **Có đang quản lý tài nguyên bằng finalize không?** Thay bằng close deterministic.
16. **Với arrays, có cần Arrays.equals/Arrays.deepEquals không?**
17. **Với records, component references có mutable không?** Cân nhắc defensive copy.
18. **Với enums, có đang lạm dụng equals thay identity comparison `==` không?**
19. **Đang dùng Object type ở chỗ cần domain type/interface cụ thể không?**
20. **Có gọi overridable Object methods trong constructor sớm không?** Tránh quan sát state subclass chưa sẵn sàng.

## 29. Tổng kết

**`java.lang.Object` là nền tảng của class hierarchy Java**, vì các classes thông thường cuối cùng đều kế thừa Object. Điều này mang lại những hợp đồng chung như **`equals`, `hashCode`, `toString`, `getClass`, `clone` và Object monitor methods**. Nhưng phải hiểu **từng method đúng ngữ nghĩa**:

- **`equals` mặc định so identity**, không tự so field values.
- **`hashCode` phải nhất quán với logical equals** nếu định nghĩa value equality; collisions vẫn có thể xảy ra.
- **`toString` giúp biểu diễn/debug**, không tự là stable identifier hay serialization protocol.
- **`getClass` phản ánh runtime class** và không được override.
- **`clone` liên quan shallow copying và Cloneable**, không tự deep-copy object graph.
- **`wait/notify/notifyAll`** là monitor methods, cần đúng lock/condition protocol, khác `Thread.sleep`.
- **`finalize` là cơ chế legacy/deprecated**, không dùng làm destructor; thay bằng **`AutoCloseable` và try-with-resources**.

Hiểu Object đúng giúp bạn dùng **kế thừa, đa hình, Java collections, records, memory semantics và concurrency** một cách vững chắc. Nhưng đừng biến Object thành kiểu tham số mặc định cho mọi business method: **class/interface riêng diễn đạt trách nhiệm và hợp đồng nghiệp vụ tốt hơn**, trong khi Object chỉ cung cấp nền tảng chung của các Java objects.
