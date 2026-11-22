# Thực nghiệm tham chiếu dùng chung, truyền tham trị và sao chép trong Java

## 1. Mục tiêu: nhìn thấy điều gì thực sự được chia sẻ?

Trong Java, một đối tượng (*object*) có thể được truy cập qua **nhiều giá trị tham chiếu** (*reference values*). Hai biến khác tên không nhất thiết là hai objects. Khi truyền một tham chiếu vào phương thức, Java **truyền tham trị**: phương thức nhận một bản sao của **giá trị tham chiếu**, không phải bản sao đối tượng. Khi sao chép một cấu trúc chứa tham chiếu, bản sao có thể sở hữu container riêng nhưng **vẫn chia sẻ các đối tượng thành phần**.

Bốn câu hỏi phải tách biệt:

1. **Có bao nhiêu đối tượng được tạo?** Nhìn vào các phép tạo object/array và hành vi được quan sát; không đếm biến như đếm object.
2. **Những biến nào cùng trỏ một object?** Sử dụng identity `==` và sơ đồ tham chiếu để suy luận.
3. **Phương thức nhận gì?** Bản sao của primitive value hoặc bản sao của reference value.
4. **Sao chép đến mức nào?** Chỉ copy reference, copy container (nông), copy cả mutable children (sâu theo phạm vi), hay chia sẻ vì children bất biến?

Một vài phát biểu nền tảng:

- `Employee b = a;` **không sao chép Employee object**.
- `b.setName(...)` có thể làm `a` quan sát thấy thay đổi nếu `a == b`.
- `b = new Employee(...)` chỉ **đổi tham chiếu của b**, không đổi tham chiếu của a.
- Khi gọi `edit(employee)`, parameter nhận một **bản sao reference**, nhưng có thể sửa **chính object** của caller.
- `new ArrayList<>(oldList)` tạo **list riêng** nhưng thường chia sẻ **các element objects**.
- `array.clone()` tạo array riêng nhưng với array chứa references chỉ sao chép **reference elements**.
- `record` không tự deep-copy array/list mutable components.
- `Object.clone()` mặc định thực hiện **field-wise shallow copy**, không phải deep clone tự động.
- **Deep copy** phải xác định rõ objects nào được tách, những objects nào giữ chia sẻ, cách xử lý alias/cycle và loại trừ resources không thể sao chép.

**Phiên bản:** Ví dụ chạy độc lập trên Java 17+ bằng `javac` và `java`. Mỗi chương trình là một tệp riêng; các tên lớp phụ trợ có thể trùng giữa những ví dụ vì **không ghép tất cả tệp vào một package rồi biên dịch cùng lúc**.

## 2. Sơ đồ nền: biến tham chiếu và đối tượng là hai thứ khác nhau

Ví dụ:

```java
Book a = new Book("Java");
Book b = a;
```

Đây là **mảnh mã minh họa** với class Book giả định.

Sơ đồ:

```text
Biến cục bộ           Đối tượng
    a ───────────┐
                 ├────────> Book { title = "Java" }
    b ───────────┘
```

Có hai biến `a` và `b` nhưng **một Book object** ở hình dung này. Câu `Book b = a` chép giá trị tham chiếu từ a sang b, không gọi constructor mới.

Sửa object qua b:

```java
b.setTitle("Java 17");
```

sẽ làm a quan sát cùng title vì a và b trỏ cùng object.

Gán lại b:

```java
b = new Book("Other");
```

khiến b tham chiếu object khác; a vẫn trỏ Book cũ. Nếu object cũ vẫn reachable qua a, nó không tự biến mất.

**Lưu ý:** Các mũi tên chỉ là mô hình logic, không mô tả địa chỉ bộ nhớ vật lý hay pointer arithmetic mà Java cho phép chương trình thực hiện.

## 3. Thí nghiệm 1 — Một object, hai tên, state thay đổi chung

Tạo **`SharedReferenceDemo.java`**:

```java
final class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void increment() {
        value++;
    }

    int value() {
        return value;
    }
}

public class SharedReferenceDemo {
    public static void main(String[] args) {
        Counter original = new Counter(5);
        Counter alias = original;

        System.out.println(original == alias);

        alias.increment();

        System.out.println(original.value());
        System.out.println(alias.value());
    }
}
```

```bash
javac SharedReferenceDemo.java
java SharedReferenceDemo
```

```text
true
6
6
```

**Giải thích từng bước:**

1. `new Counter(5)` tạo một Counter object.
2. `original` trỏ object đó.
3. `alias = original` sao chép reference value, **không** tạo Counter thứ hai.
4. `original == alias` true vì cùng identity.
5. `alias.increment()` mutate Counter được cả hai tên cùng tham chiếu.
6. Hai lời gọi `value()` đọc cùng field và trả 6.

### Kết luận thực nghiệm

Khi nhiều nơi giữ cùng một mutable object, mọi nơi đều có thể quan sát side effect (theo quy tắc truy cập/concurrency thích hợp). Vì vậy thiết kế API phải nêu rõ **ownership**, có cho share mutable state không, và ai có quyền mutate.

## 4. Thí nghiệm 2 — Gán biến tham chiếu khác với sửa đối tượng

Tạo **`ReassignmentVersusMutationDemo.java`**:

```java
final class Counter {
    int value;

    Counter(int value) {
        this.value = value;
    }
}

public class ReassignmentVersusMutationDemo {
    public static void main(String[] args) {
        Counter a = new Counter(2);
        Counter b = a;

        b.value = 7;
        System.out.println(a.value);

        b = new Counter(99);
        System.out.println(a.value);
        System.out.println(b.value);
        System.out.println(a == b);
    }
}
```

```bash
javac ReassignmentVersusMutationDemo.java
java ReassignmentVersusMutationDemo
```

```text
7
7
99
false
```

Sau `b.value = 7`, một shared object bị mutate. Sau `b = new Counter(99)`, biến b được **gán reference mới**; object của a vẫn có value 7.

`b = a` là thao tác sao chép **reference value**. Nó không là **shallow copy của object**; shallow copy thông thường vẫn cần tạo một object/container mới.

## 5. Thí nghiệm 3 — `null` chỉ đổi một reference

Tạo **`NullAliasDemo.java`**:

```java
final class Note {
    final String text;

    Note(String text) {
        this.text = text;
    }
}

public class NullAliasDemo {
    public static void main(String[] args) {
        Note first = new Note("kept");
        Note second = first;

        first = null;

        System.out.println(first == null);
        System.out.println(second.text);
    }
}
```

```bash
javac NullAliasDemo.java
java NullAliasDemo
```

```text
true
kept
```

`first = null` không “hủy” Note object. `second` vẫn tham chiếu đối tượng đó. Java không gọi destructor tức thì tại phép gán null và không cho ứng dụng chủ động giải phóng object memory như `free()` trong C.

**Đừng thêm phép gán null khắp nơi** với kỳ vọng GC sẽ chạy ngay. Hãy quản lý reference ownership của collections, static caches và listeners theo đúng lifecycle.

## 6. Tham trị nghĩa là gì?

Java **pass-by-value** cho mọi đối số phương thức:

- Primitive `int`: copy **giá trị số**.
- Primitive `boolean`: copy **giá trị boolean**.
- Reference type: copy **giá trị tham chiếu** (trỏ đến object nào đó hoặc null).

Phương thức có **parameter variable riêng**. Gán lại parameter không gán lại biến đối số ở phía gọi. Nhưng nếu parameter copy reference trỏ cùng mutable object, dùng parameter để mutate object sẽ có tác động nhìn thấy ở caller.

### Bảng đối chiếu

| Thao tác trong method | Có đổi biến caller? | Có thể đổi object caller đang trỏ? |
| --- | --- | --- |
| `parameter = 42` với `int` | Không | Không có object liên quan |
| `parameter = new Box(...)` | Không | Không, chỉ gán parameter |
| `parameter = null` | Không | Không |
| `parameter.value = 42` | Không | Có, nếu cùng object |
| `parameter.add(...)` trên List | Không | Có, nếu cùng mutable List |
| `parameter[0] = 42` trên array | Không | Có, nếu cùng array |

**Không gọi Java là pass-by-reference** theo nghĩa biến parameter là alias trực tiếp tới **biến caller**. Hai biến giữ cùng reference value ở lúc gọi, nhưng chúng là **hai biến khác nhau**.

## 7. Thí nghiệm 4 — Truyền tham trị với primitive

Tạo **`PrimitivePassByValueDemo.java`**:

```java
public class PrimitivePassByValueDemo {
    static void update(int number) {
        number = 100;
        System.out.println("inside=" + number);
    }

    public static void main(String[] args) {
        int value = 5;

        update(value);

        System.out.println("outside=" + value);
    }
}
```

```bash
javac PrimitivePassByValueDemo.java
java PrimitivePassByValueDemo
```

```text
inside=100
outside=5
```

`number` là local parameter có giá trị ban đầu được copy từ `value`. Gán 100 cho number không chạm đến biến value trong main.

Thí nghiệm này thường không gây nhầm, nhưng cùng quy tắc **copy argument value** áp dụng với reference types.

## 8. Thí nghiệm 5 — Sửa object qua parameter thì caller thấy

Tạo **`MutableParameterDemo.java`**:

```java
final class Wallet {
    private int coins;

    Wallet(int coins) {
        this.coins = coins;
    }

    void add(int amount) {
        coins += amount;
    }

    int coins() {
        return coins;
    }
}

public class MutableParameterDemo {
    static void reward(Wallet wallet) {
        wallet.add(3);
        System.out.println("inside=" + wallet.coins());
    }

    public static void main(String[] args) {
        Wallet mine = new Wallet(5);

        reward(mine);

        System.out.println("outside=" + mine.coins());
    }
}
```

```bash
javac MutableParameterDemo.java
java MutableParameterDemo
```

```text
inside=8
outside=8
```

Ở lời gọi `reward(mine)`, parameter `wallet` giữ **bản sao của reference** mine. Cả hai tham chiếu **cùng Wallet object**, nên `wallet.add(3)` làm object chung đổi state.

**Điều không xảy ra:** Method không thay đổi **biến mine**. Biến mine trước/sau vẫn trỏ cùng Wallet object.

## 9. Thí nghiệm 6 — Gán lại parameter không làm caller đổi tham chiếu

Tạo **`ParameterRebindDemo.java`**:

```java
final class Wallet {
    int coins;

    Wallet(int coins) {
        this.coins = coins;
    }
}

public class ParameterRebindDemo {
    static void replace(Wallet parameter) {
        parameter = new Wallet(999);
        System.out.println("inside=" + parameter.coins);
    }

    public static void main(String[] args) {
        Wallet mine = new Wallet(5);

        replace(mine);

        System.out.println("outside=" + mine.coins);
    }
}
```

```bash
javac ParameterRebindDemo.java
java ParameterRebindDemo
```

```text
inside=999
outside=5
```

Sơ đồ:

```text
Trước:
mine      ──┐
parameter ──┴──> Wallet(5)

Trong replace sau parameter = new Wallet(999):
mine      ─────> Wallet(5)
parameter ─────> Wallet(999)
```

Thay giá trị **biến parameter** không thay đổi biến mine. Đây là bằng chứng trực tiếp Java không pass caller variable by reference.

## 10. Thí nghiệm 7 — Cả mutate và rebind trong cùng method

Tạo **`MutateThenRebindDemo.java`**:

```java
final class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class MutateThenRebindDemo {
    static void work(Box parameter) {
        parameter.value = 10;
        parameter = new Box(20);
        parameter.value = 30;

        System.out.println("method=" + parameter.value);
    }

    public static void main(String[] args) {
        Box box = new Box(1);

        work(box);

        System.out.println("caller=" + box.value);
    }
}
```

```bash
javac MutateThenRebindDemo.java
java MutateThenRebindDemo
```

```text
method=30
caller=10
```

Thực hiện theo thời gian:

1. Ban đầu cả `box` và `parameter` cùng trỏ object A có value 1.
2. `parameter.value = 10` sửa **A**.
3. `parameter = new Box(20)` tạo **B**, đổi parameter sang B.
4. `parameter.value = 30` chỉ sửa **B**.
5. Caller vẫn trỏ A với value 10.

**Quy tắc giải đề:** Mỗi khi gặp dấu `=`, xem bên trái là **biến tham chiếu** hay **field của object**. Hai loại assignment có tác động khác nhau.

## 11. Thí nghiệm 8 — Method `swap` không hoán đổi biến của caller

Người mới học thường thử:

```java
static void swap(Object a, Object b) {
    Object temp = a;
    a = b;
    b = temp;
}
```

Method này chỉ hoán đổi **hai parameter locals**. Tạo chương trình kiểm chứng **`FailedSwapDemo.java`**:

```java
public class FailedSwapDemo {
    static void swap(StringBuilder a, StringBuilder b) {
        StringBuilder temp = a;
        a = b;
        b = temp;

        System.out.println("inside=" + a + "," + b);
    }

    public static void main(String[] args) {
        StringBuilder first = new StringBuilder("A");
        StringBuilder second = new StringBuilder("B");

        swap(first, second);

        System.out.println("outside=" + first + "," + second);
    }
}
```

```bash
javac FailedSwapDemo.java
java FailedSwapDemo
```

```text
inside=B,A
outside=A,B
```

Caller variables `first`/`second` không bị đổi. Nếu caller muốn swap **references**, thao tác swap phải xảy ra **tại caller**, hoặc thiết kế một mutable holder/list và swap **các phần tử bên trong holder** qua parameter reference.

Không có cú pháp Java thông thường để một method nhận một biến cục bộ của caller theo kiểu `ref parameter` rồi thay giá trị chính biến đó.

## 12. Thí nghiệm 9 — Trả reference mới để caller chủ động gán

Tạo **`ReturnNewReferenceDemo.java`**:

```java
final class Ticket {
    final String code;

    Ticket(String code) {
        this.code = code;
    }
}

public class ReturnNewReferenceDemo {
    static Ticket replace(Ticket current) {
        return new Ticket(current.code + "-NEW");
    }

    public static void main(String[] args) {
        Ticket ticket = new Ticket("T1");

        Ticket updated = replace(ticket);

        System.out.println(ticket.code);
        System.out.println(updated.code);
        System.out.println(ticket == updated);

        ticket = updated;
        System.out.println(ticket.code);
    }
}
```

```bash
javac ReturnNewReferenceDemo.java
java ReturnNewReferenceDemo
```

```text
T1
T1-NEW
false
T1-NEW
```

Thay vì cố gán caller variable từ bên trong method, method **trả reference mới**. Caller quyết định có cập nhật local variable hay không bằng `ticket = updated`.

Đây là mẫu thường gặp khi xử lý immutable value objects: tạo giá trị mới và trả về, thay vì mutate object cũ.

## 13. String là immutable: khác biệt giữa “đổi biến” và “đổi object”

Tạo **`StringReferenceDemo.java`**:

```java
public class StringReferenceDemo {
    static void append(String parameter) {
        parameter = parameter + "!";
        System.out.println("inside=" + parameter);
    }

    public static void main(String[] args) {
        String text = "Java";

        append(text);

        System.out.println("outside=" + text);
    }
}
```

```bash
javac StringReferenceDemo.java
java StringReferenceDemo
```

```text
inside=Java!
outside=Java
```

`String` immutable; biểu thức nối chuỗi cho một giá trị String khác (có thể chịu tối ưu nội bộ), và assignment chỉ đổi parameter. Không có mutate state của String object ban đầu.

So sánh với `StringBuilder`, object mutable, ở thí nghiệm kế tiếp.

## 14. StringBuilder: reference parameter có thể làm thay đổi nội dung

Tạo **`StringBuilderParameterDemo.java`**:

```java
public class StringBuilderParameterDemo {
    static void append(StringBuilder parameter) {
        parameter.append("!");
    }

    public static void main(String[] args) {
        StringBuilder builder =
                new StringBuilder("Java");

        append(builder);

        System.out.println(builder);
    }
}
```

```bash
javac StringBuilderParameterDemo.java
java StringBuilderParameterDemo
```

```text
Java!
```

Hai thí nghiệm cho thấy tác động còn phụ thuộc **object có mutable methods hay không**. Quy tắc pass-by-value **không đổi** giữa String và StringBuilder.

**Đừng suy ra Java truyền immutable types bằng giá trị còn mutable types bằng tham chiếu.** Mọi arguments luôn pass-by-value, nhưng nội dung được copy khác nhau: primitive value hoặc reference value.

## 15. Array là object và có thể được chia sẻ

Một array có identity. Gán tên khác cho array chỉ copy reference, giống class instance.

Tạo **`SharedArrayDemo.java`**:

```java
import java.util.Arrays;

public class SharedArrayDemo {
    public static void main(String[] args) {
        int[] first = {1, 2, 3};
        int[] second = first;

        second[1] = 99;

        System.out.println(Arrays.toString(first));
        System.out.println(first == second);
    }
}
```

```bash
javac SharedArrayDemo.java
java SharedArrayDemo
```

```text
[1, 99, 3]
true
```

`first` và `second` cùng trỏ một array. Gán `second[1]` thay **phần tử của object array**, nên first quan sát thay đổi.

**Khác với primitive variable:** `int x = 1; int y = x; y = 9;` chỉ đổi biến y vì primitive value được copy trực tiếp.

## 16. Array được truyền tham trị nhưng elements vẫn có thể bị sửa

Tạo **`ArrayParameterDemo.java`**:

```java
import java.util.Arrays;

public class ArrayParameterDemo {
    static void work(int[] values) {
        values[0] = 8;
        values = new int[] {100, 200};

        System.out.println(
                "inside=" + Arrays.toString(values));
    }

    public static void main(String[] args) {
        int[] input = {1, 2};

        work(input);

        System.out.println(
                "outside=" + Arrays.toString(input));
    }
}
```

```bash
javac ArrayParameterDemo.java
java ArrayParameterDemo
```

```text
inside=[100, 200]
outside=[8, 2]
```

`values[0] = 8` sửa array cũ mà input vẫn tham chiếu. `values = new int[]{...}` đổi **parameter local** sang array mới, nên không thay input reference.

Thí nghiệm gộp hai quy tắc trong một tình huống và thường là cách kiểm tra hiểu biết đáng tin hơn câu hỏi lý thuyết “Java là pass-by-reference hay pass-by-value?”.

## 17. Reference trong List: mutation container và mutation element

Một `List<Person>` gồm hai lớp đối tượng:

1. **List object** chứa references.
2. **Person objects** mà những references trỏ tới.

Tạo **`ListReferenceLayersDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Person {
    String name;

    Person(String name) {
        this.name = name;
    }
}

public class ListReferenceLayersDemo {
    public static void main(String[] args) {
        Person person = new Person("An");
        List<Person> list = new ArrayList<>();
        list.add(person);

        person.name = "Binh";
        System.out.println(list.get(0).name);

        list.set(0, new Person("Chi"));
        System.out.println(person.name);
        System.out.println(list.get(0).name);
    }
}
```

```bash
javac ListReferenceLayersDemo.java
java ListReferenceLayersDemo
```

```text
Binh
Binh
Chi
```

Ban đầu list element và biến person cùng trỏ object A. `person.name = "Binh"` mutate A, nên list quan sát Binh.

Sau `list.set(0, new Person("Chi"))`, list element trỏ object B. Biến person vẫn trỏ A với name Binh.

**Một dòng Java có thể đổi container entry chứ không đổi object cũ.** Khi phân tích aliasing, hãy vẽ mũi tên từ list slot và từ local variable riêng.

## 18. Ba mức dễ nhầm: alias, shallow copy, deep copy

Giả sử một `Order` có field `List<Item>` và mỗi `Item` có mutable state.

| Thao tác | Object Order/container mới? | Item objects mới? | Tác động khi Item bị sửa |
| --- | --- | --- | --- |
| `b = a` | Không | Không | Cùng toàn bộ object graph |
| Shallow copy của Order | Có, theo cách copy | Thường không | Cùng Item có thể thấy thay đổi |
| Copy List bằng `new ArrayList<>(list)` | List mới | Không | Item vẫn chia sẻ |
| Deep copy theo chính sách | Order/List mới | Có cho mutable Items cần tách | Item mutations độc lập trong phạm vi copy |
| Copy khi Item immutable | List có thể mới | Có thể chia sẻ immutable Item | Không có mutation trạng thái Item để lan truyền |

**Đừng dùng từ “copy” một mình khi API dễ gây hiểu nhầm.** Hãy định nghĩa rõ muốn bản sao độc lập ở **mức nào**, có giữ shared immutable objects không và có giữ alias relationships trong graph hay không.

## 19. Thí nghiệm sao chép thứ nhất — Gán reference không tạo bản sao

Tạo **`AssignmentIsNotCopyDemo.java`**:

```java
final class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class AssignmentIsNotCopyDemo {
    public static void main(String[] args) {
        Box original = new Box(10);
        Box assigned = original;

        assigned.value = 20;

        System.out.println(original == assigned);
        System.out.println(original.value);
    }
}
```

```bash
javac AssignmentIsNotCopyDemo.java
java AssignmentIsNotCopyDemo
```

```text
true
20
```

Tên `assigned` không biến nó thành bản sao. Không có `new Box(...)` thứ hai, copy constructor hoặc factory tạo instance mới.

**Kiểm bằng identity:** Với ordinary mutable class được tạo độc lập, `original == copied` nên false nếu thật sự là object mới. Nhưng chỉ `== false` chưa chứng minh bản sao *deep*; các nested references vẫn có thể chia sẻ.

## 20. Copy constructor: tạo một top-level object khác

Tạo **`SimpleCopyConstructorDemo.java`**:

```java
final class Point {
    int x;
    int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    Point(Point other) {
        this(other.x, other.y);
    }
}

public class SimpleCopyConstructorDemo {
    public static void main(String[] args) {
        Point original = new Point(2, 3);
        Point copy = new Point(original);

        copy.x = 9;

        System.out.println(original == copy);
        System.out.println(original.x);
        System.out.println(copy.x);
    }
}
```

```bash
javac SimpleCopyConstructorDemo.java
java SimpleCopyConstructorDemo
```

```text
false
2
9
```

`copy` là object khác original. Vì Point chỉ lưu hai primitive fields, sao chép field values đã đủ để state độc lập. Với reference fields trỏ mutable nested objects, **chép reference fields** thường chỉ là shallow copy; phải xem tiếp.

## 21. Thí nghiệm shallow copy — Hai owners, một mutable child

Tạo **`ShallowCopyDemo.java`**:

```java
final class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

final class Customer {
    String name;
    Address address;

    Customer(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    Customer(Customer other) {
        this.name = other.name;
        this.address = other.address;
    }
}

public class ShallowCopyDemo {
    public static void main(String[] args) {
        Customer original =
                new Customer("An", new Address("Hue"));
        Customer copy = new Customer(original);

        System.out.println(original == copy);
        System.out.println(
                original.address == copy.address);

        copy.name = "Binh";
        copy.address.city = "Da Nang";

        System.out.println(original.name);
        System.out.println(original.address.city);
    }
}
```

```bash
javac ShallowCopyDemo.java
java ShallowCopyDemo
```

```text
false
true
An
Da Nang
```

Giải thích:

- `new Customer(original)` tạo Customer mới, nên `original == copy` false.
- `this.address = other.address` copy **reference** đến cùng Address, nên identity true.
- `copy.name = "Binh"` đổi field reference của Customer copy. Original vẫn có name An.
- `copy.address.city = "Da Nang"` mutate **shared Address object**, nên original nhìn thấy city mới.

### Sơ đồ shallow copy

```text
original Customer ──address──┐
                             ├──> Address("Hue" → "Da Nang")
copy Customer ──────address──┘

original.name → "An"
copy.name     → "Binh"
```

Bản sao top-level đã độc lập, nhưng **mutable child chưa độc lập**.

## 22. Thí nghiệm deep copy — Tạo lại mutable child

Tạo **`DeepCopyDemo.java`**:

```java
final class Address {
    String city;

    Address(String city) {
        this.city = city;
    }

    Address(Address other) {
        this.city = other.city;
    }
}

final class Customer {
    String name;
    Address address;

    Customer(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    static Customer deepCopy(Customer other) {
        return new Customer(
                other.name,
                new Address(other.address));
    }
}

public class DeepCopyDemo {
    public static void main(String[] args) {
        Customer original =
                new Customer("An", new Address("Hue"));
        Customer copy = Customer.deepCopy(original);

        System.out.println(original == copy);
        System.out.println(
                original.address == copy.address);

        copy.address.city = "Da Nang";

        System.out.println(original.address.city);
        System.out.println(copy.address.city);
    }
}
```

```bash
javac DeepCopyDemo.java
java DeepCopyDemo
```

```text
false
false
Hue
Da Nang
```

Trong ví dụ này **top-level Customer lẫn mutable Address** đều được copy thành objects mới. Field name là String immutable, nên việc dùng cùng String instance không làm state bị mutate từ phía bản sao.

**Deep copy không bắt buộc tạo mới từng immutable object.** Mục tiêu là **độc lập về những mutable components mà hợp đồng yêu cầu**, không phải tạo lại vô hạn mọi object trong graph.

## 23. Deep copy phải định nghĩa phạm vi rõ ràng

Một entity thực tế có thể chứa:

- `String` immutable name.
- Mutable `List<Line>`.
- Mutable `byte[]`.
- Một `Connection` hoặc `Socket`.
- Một `CustomerId` immutable value.
- Reference tới shared service/repository.
- Reference đến parent object, tạo cycle.

Không thể đơn giản viết “deep copy = new mọi field” cho tất cả:

- File/socket/DB connection **không nên copy** như state value.
- Shared services thường cần giữ nguyên shared identity, không duplicate.
- Cyclic graphs cần tránh recursion vô hạn.
- Multiple references tới cùng child có thể cần giữ alias topology.
- Một snapshot có thể chỉ cần immutable value data, không cần entity identity.

**Câu hỏi contract:** “Bản sao độc lập về những thay đổi nào? Các quan hệ chia sẻ nào cần được giữ? Resources nào không thuộc bản sao?” Trả lời trước khi chọn thuật toán.

## 24. Sao chép primitive array bằng `clone()`

Với primitive array, mỗi element là primitive value. `clone()` tạo array mới, nên sửa primitive element ở copy không ảnh hưởng original.

Tạo **`PrimitiveArrayCloneDemo.java`**:

```java
import java.util.Arrays;

public class PrimitiveArrayCloneDemo {
    public static void main(String[] args) {
        int[] original = {1, 2, 3};
        int[] copy = original.clone();

        copy[0] = 99;

        System.out.println(original == copy);
        System.out.println(Arrays.toString(original));
        System.out.println(Arrays.toString(copy));
    }
}
```

```bash
javac PrimitiveArrayCloneDemo.java
java PrimitiveArrayCloneDemo
```

```text
false
[1, 2, 3]
[99, 2, 3]
```

Array instance khác nhau. Với `int[]`, copy primitive elements đã đủ tạo độc lập theo contents. Có thể dùng `Arrays.copyOf(original, original.length)`, `System.arraycopy` vào array mới hoặc `clone()` tùy ngữ cảnh.

**Không suy rằng tất cả array clone là deep copy** — array của object references có hành vi khác.

## 25. Object array clone vẫn dùng chung elements

Tạo **`ObjectArrayCloneDemo.java`**:

```java
final class Item {
    String label;

    Item(String label) {
        this.label = label;
    }
}

public class ObjectArrayCloneDemo {
    public static void main(String[] args) {
        Item[] original = {
                new Item("A"),
                new Item("B")
        };
        Item[] copy = original.clone();

        System.out.println(original == copy);
        System.out.println(original[0] == copy[0]);

        copy[0].label = "X";
        System.out.println(original[0].label);

        copy[0] = new Item("Y");
        System.out.println(original[0].label);
        System.out.println(copy[0].label);
    }
}
```

```bash
javac ObjectArrayCloneDemo.java
java ObjectArrayCloneDemo
```

```text
false
true
X
X
Y
```

`original` và `copy` là **hai arrays**. Nhưng slot 0 ban đầu chứa reference đến **cùng Item**. Vì vậy `copy[0].label = "X"` mutate shared Item. Sau `copy[0] = new Item("Y")`, chỉ slot 0 của array copy đổi reference; original slot vẫn trỏ Item có label X.

**Nhìn hai tầng:** thay element field (mutation đối tượng) khác thay array slot (mutation container).

## 26. Mảng nhiều chiều là array của arrays

Với `int[][]`, mỗi row cũng là một array object. Gọi `clone()` trên outer array chỉ copy **row references**, không copy inner arrays.

Tạo **`TwoDimensionalArrayCopyDemo.java`**:

```java
import java.util.Arrays;

public class TwoDimensionalArrayCopyDemo {
    public static void main(String[] args) {
        int[][] original = {
                {1, 2},
                {3, 4}
        };
        int[][] shallow = original.clone();

        shallow[0][0] = 99;

        System.out.println(original == shallow);
        System.out.println(original[0] == shallow[0]);
        System.out.println(Arrays.deepToString(original));
    }
}
```

```bash
javac TwoDimensionalArrayCopyDemo.java
java TwoDimensionalArrayCopyDemo
```

```text
false
true
[[99, 2], [3, 4]]
```

Sao chép sâu theo cấu trúc mảng hai chiều đơn giản cần copy **từng row**; nếu rows chứa mutable object references, còn cần copy elements đó theo policy.

## 27. Copy từng row để tách mảng hai chiều primitive

Tạo **`DeepPrimitiveMatrixCopyDemo.java`**:

```java
import java.util.Arrays;

public class DeepPrimitiveMatrixCopyDemo {
    static int[][] copyMatrix(int[][] source) {
        int[][] copy = new int[source.length][];

        for (int i = 0; i < source.length; i++) {
            copy[i] = source[i].clone();
        }
        return copy;
    }

    public static void main(String[] args) {
        int[][] original = {
                {1, 2},
                {3, 4}
        };
        int[][] copy = copyMatrix(original);

        copy[0][0] = 99;

        System.out.println(Arrays.deepToString(original));
        System.out.println(Arrays.deepToString(copy));
        System.out.println(original[0] == copy[0]);
    }
}
```

```bash
javac DeepPrimitiveMatrixCopyDemo.java
java DeepPrimitiveMatrixCopyDemo
```

```text
[[1, 2], [3, 4]]
[[99, 2], [3, 4]]
false
```

Ví dụ giả định **mọi row đều non-null**. Với jagged array có null rows, cần check trước khi clone. Đây là copy độc lập cho primitive rows, nhưng nếu hai vị trí của outer source cùng trỏ **một row**, thuật toán này **không giữ alias topology** vì mỗi vị trí clone riêng. Sẽ bàn ở phần graph.

## 28. `new ArrayList<>(old)` tạo container mới, không deep-copy elements

Tạo **`ListShallowCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Item {
    String name;

    Item(String name) {
        this.name = name;
    }
}

public class ListShallowCopyDemo {
    public static void main(String[] args) {
        List<Item> original = new ArrayList<>();
        original.add(new Item("Pen"));

        List<Item> copy = new ArrayList<>(original);

        System.out.println(original == copy);
        System.out.println(original.get(0) == copy.get(0));

        copy.get(0).name = "Pencil";
        System.out.println(original.get(0).name);

        copy.add(new Item("Book"));
        System.out.println(original.size());
        System.out.println(copy.size());
    }
}
```

```bash
javac ListShallowCopyDemo.java
java ListShallowCopyDemo
```

```text
false
true
Pencil
1
2
```

- **Container copy:** list mới có thể add/remove độc lập.
- **Element share:** mutable Item ban đầu vẫn cùng identity.
- `copy.add(...)` không làm original list có thêm element vì containers tách nhau.
- `copy.get(0).name = ...` làm original quan sát mutation vì Item chung.

### Khi nào shallow list copy là đủ?

Nếu elements là Strings, enums hoặc value objects có state thực sự bất biến, có thể an toàn chia sẻ elements. Nếu elements mutable và API hứa một snapshot độc lập, phải copy elements hoặc chuyển sang immutable snapshot representation.

## 29. `List.copyOf` khác `new ArrayList<>(...)`

`List.copyOf(source)` trả **unmodifiable list**, từ chối null elements và tạo snapshot của sequence tại thời điểm gọi theo API. Nó **không deep-copy mutable elements**.

Tạo **`ListCopyOfDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Cell {
    int value;

    Cell(int value) {
        this.value = value;
    }
}

public class ListCopyOfDemo {
    public static void main(String[] args) {
        Cell cell = new Cell(1);
        List<Cell> source = new ArrayList<>();
        source.add(cell);

        List<Cell> snapshot = List.copyOf(source);

        source.add(new Cell(2));
        cell.value = 9;

        System.out.println(source.size());
        System.out.println(snapshot.size());
        System.out.println(snapshot.get(0).value);

        try {
            snapshot.add(new Cell(3));
        } catch (UnsupportedOperationException ex) {
            System.out.println("unmodifiable");
        }
    }
}
```

```bash
javac ListCopyOfDemo.java
java ListCopyOfDemo
```

```text
2
1
9
unmodifiable
```

Snapshot không thay khi source add element. Nhưng snapshot vẫn chứa reference đến Cell đã bị mutate từ 1 sang 9.

**Từ khóa “unmodifiable”** nói về mutation API của **list structure**, không làm Cell immutable. Đừng nhầm với **deeply immutable object graph**.

## 30. `Collections.unmodifiableList` là view, không phải độc lập snapshot

Tạo **`UnmodifiableViewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewDemo {
    public static void main(String[] args) {
        List<String> mutable = new ArrayList<>();
        mutable.add("A");

        List<String> view =
                Collections.unmodifiableList(mutable);

        mutable.add("B");

        System.out.println(view.size());
        System.out.println(view.get(1));

        try {
            view.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("cannot add through view");
        }
    }
}
```

```bash
javac UnmodifiableViewDemo.java
java UnmodifiableViewDemo
```

```text
2
B
cannot add through view
```

`view` không cho add qua chính view, nhưng **phản ánh thay đổi structural** từ backing list mutable.

Phân biệt:

- `new ArrayList<>(source)` → mutable container riêng, elements shared.
- `List.copyOf(source)` → unmodifiable snapshot container, elements shared; implementation **có thể tái sử dụng** một nguồn vốn unmodifiable phù hợp, nên không hứa `!=`.
- `Collections.unmodifiableList(source)` → unmodifiable **view** lên source, phản ánh thay đổi backing list.

Chọn theo hợp đồng của class sở hữu collection.

## 31. `subList` là view: chia sẻ backing list

Tạo **`SubListViewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class SubListViewDemo {
    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("A", "B", "C"));

        List<String> view = source.subList(1, 3);

        view.set(0, "X");

        System.out.println(source);
        System.out.println(view);
    }
}
```

```bash
javac SubListViewDemo.java
java SubListViewDemo
```

```text
[A, X, C]
[X, C]
```

`subList` thường trả một view lên backing list. `view.set(0, "X")` làm `source[1]` đổi.

**Giới hạn:** Structural modifications trực tiếp trên backing list ngoài view có thể khiến semantics của subList không còn được định nghĩa rõ theo API; đừng đưa vào ví dụ dự đoán output một cách máy móc. Nếu cần snapshot độc lập của đoạn dữ liệu, dùng `new ArrayList<>(source.subList(...))` hoặc `List.copyOf(...)` tùy quyền mutation, rồi xem thêm elements có mutable không.

## 32. Sao chép Map cũng có hai tầng

`new HashMap<>(old)` tạo Map structure mới nhưng không tạo bản sao các key/value objects mutable.

Tạo **`MapShallowCopyDemo.java`**:

```java
import java.util.HashMap;
import java.util.Map;

final class Detail {
    int score;

    Detail(int score) {
        this.score = score;
    }
}

public class MapShallowCopyDemo {
    public static void main(String[] args) {
        Map<String, Detail> original = new HashMap<>();
        original.put("A", new Detail(1));

        Map<String, Detail> copy =
                new HashMap<>(original);

        copy.get("A").score = 7;

        System.out.println(original.get("A").score);
        System.out.println(original == copy);

        copy.remove("A");
        System.out.println(original.containsKey("A"));
    }
}
```

```bash
javac MapShallowCopyDemo.java
java MapShallowCopyDemo
```

```text
7
false
true
```

Map containers là hai objects, nhưng value Detail chung. Remove entry khỏi copy không remove entry khỏi original.

**Lưu ý keys:** Mutable keys mà thay đổi fields ảnh hưởng `equals/hashCode` có thể làm Map/Set hoạt động sai dù không hề copy. Thiết kế keys immutable là ưu tiên tốt cho các APIs dạng này.

## 33. Record không tự deep-copy mutable component

Records phù hợp value-oriented data carrier, nhưng một record component kiểu `int[]` vẫn là reference đến mutable array.

Tạo **`RecordArraySharingDemo.java`**:

```java
import java.util.Arrays;

record Scores(int[] values) {
}

public class RecordArraySharingDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        Scores scores = new Scores(input);

        input[0] = 9;
        System.out.println(
                Arrays.toString(scores.values()));

        scores.values()[1] = 8;
        System.out.println(Arrays.toString(input));
    }
}
```

```bash
javac RecordArraySharingDemo.java
java RecordArraySharingDemo
```

```text
[9, 2]
[9, 8]
```

Record fields được gán một lần, nhưng `values` là reference đến **array mutable**. Final reference không làm array immutable. Compiler-generated accessor trả cùng reference nếu không override. Đây là **aliasing leak**, dù record trông gọn và có `final` fields.

### Equality của record chứa array

Generated `equals()` của record so components theo quy tắc record; với array component, equality là **reference equality**, không phải deep contents. Nếu cần value equality theo elements, phải tự thiết kế `equals/hashCode` nhất quán; hoặc chọn representation immutable phù hợp.

## 34. Defensive copy ở record constructor và accessor

Tạo **`DefensiveRecordDemo.java`**:

```java
import java.util.Arrays;

record Scores(int[] values) {
    Scores {
        values = values.clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    int sum() {
        int result = 0;
        for (int value : values) {
            result = Math.addExact(result, value);
        }
        return result;
    }
}

public class DefensiveRecordDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        Scores scores = new Scores(input);

        input[0] = 9;
        int[] leaked = scores.values();
        leaked[1] = 8;

        System.out.println(scores.sum());
        System.out.println(
                Arrays.toString(scores.values()));
        System.out.println(Arrays.toString(input));
    }
}
```

```bash
javac DefensiveRecordDemo.java
java DefensiveRecordDemo
```

```text
3
[1, 2]
[9, 2]
```

Trong compact constructor, việc gán `values = values.clone()` cập nhật formal parameter, rồi compiler gán vào field record tương ứng sau compact constructor body theo quy tắc Java. Override accessor trả copy để caller không lấy được internal array và sửa nó.

**Điều chưa được sửa:** Nếu sử dụng generated `equals/hashCode`, array component vẫn có reference semantics. Defensive copies bảo vệ mutation, **không tự biến generated record equality thành Arrays.equals**.

### Khi cần equals/hashCode theo nội dung

Một hướng là dùng immutable `List<Integer>` representation khi domain cho phép, hoặc tự override `equals/hashCode` dựa trên `Arrays.equals/hashCode` và tuân thủ hợp đồng. Nhớ nhất quán cả hai methods nếu record dùng làm Map key.

## 35. Chọn một immutable representation dễ hơn nhiều deep-copy thủ công

Tạo **`ImmutableSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record InvoiceSnapshot(List<String> items) {
    InvoiceSnapshot {
        items = List.copyOf(items);
    }
}

public class ImmutableSnapshotDemo {
    public static void main(String[] args) {
        List<String> source =
                new ArrayList<>(List.of("Pen"));

        InvoiceSnapshot snapshot =
                new InvoiceSnapshot(source);

        source.add("Book");

        System.out.println(source.size());
        System.out.println(snapshot.items());
    }
}
```

```bash
javac ImmutableSnapshotDemo.java
java ImmutableSnapshotDemo
```

```text
2
[Pen]
```

`String` immutable, `List.copyOf` trả unmodifiable snapshot, nên ví dụ tạo cấu trúc value snapshot ổn định. Nếu items là `List<MutableItem>`, `List.copyOf` vẫn shallow về elements; bản thân Item có thể bị mutate.

**Bài học thiết kế:** Trước khi viết deep-copy machinery, thử chọn các **immutable value objects và unmodifiable snapshots**. Điều đó giảm số đường aliasing cần quản lý.

## 36. Copy constructor phòng vệ trên đầu vào và đầu ra

Một class giữ mutable array cần kiểm hai biên:

1. **Constructor nhận array**: nếu lưu thẳng input, caller vẫn có thể sửa array.
2. **Getter trả array**: nếu trả thẳng internal array, caller có thể mutate state.

Tạo **`DefensiveCopyClassDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Histogram {
    private final int[] buckets;

    Histogram(int[] buckets) {
        this.buckets =
                Objects.requireNonNull(buckets).clone();
    }

    Histogram(Histogram other) {
        this(other.buckets);
    }

    int[] buckets() {
        return buckets.clone();
    }

    int total() {
        int total = 0;
        for (int bucket : buckets) {
            total = Math.addExact(total, bucket);
        }
        return total;
    }
}

public class DefensiveCopyClassDemo {
    public static void main(String[] args) {
        int[] data = {2, 3};
        Histogram original = new Histogram(data);
        Histogram copy = new Histogram(original);

        data[0] = 100;
        int[] output = copy.buckets();
        output[1] = 99;

        System.out.println(original.total());
        System.out.println(copy.total());
        System.out.println(
                Arrays.toString(copy.buckets()));
    }
}
```

```bash
javac DefensiveCopyClassDemo.java
java DefensiveCopyClassDemo
```

```text
5
5
[2, 3]
```

Input array và output array đều **không** là alias của private buckets field. `Histogram(Histogram)` cũng tạo array riêng. Đây là một example có **copy semantics rõ ràng**.

**Lưu ý:** Defensive cloning chỉ shallow nếu array chứa mutable reference elements. `int[]` primitive nên sao chép toàn bộ các phần tử là đủ theo cấu trúc này.

## 37. List of mutable children: copy structure chưa đủ

Tạo **`NestedListCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Task {
    String status;

    Task(String status) {
        this.status = status;
    }

    Task(Task source) {
        this.status = source.status;
    }
}

public class NestedListCopyDemo {
    static List<Task> copyTasks(List<Task> source) {
        List<Task> copied = new ArrayList<>();
        for (Task task : source) {
            copied.add(new Task(task));
        }
        return copied;
    }

    public static void main(String[] args) {
        List<Task> original = new ArrayList<>();
        original.add(new Task("NEW"));

        List<Task> copy = copyTasks(original);
        copy.get(0).status = "DONE";

        System.out.println(original.get(0).status);
        System.out.println(copy.get(0).status);
        System.out.println(
                original.get(0) == copy.get(0));
    }
}
```

```bash
javac NestedListCopyDemo.java
java NestedListCopyDemo
```

```text
NEW
DONE
false
```

`copyTasks` tạo list mới **và** tạo Task mới cho mỗi element. Field status là String immutable nên copy reference đủ.

### Chi phí

Với nhiều objects, deep copy tăng allocations, CPU time và memory footprint. Chỉ copy những dữ liệu cần độc lập; không deep-copy theo phản xạ nếu shared immutable data hoặc ownership contract đã an toàn.

## 38. Alias topology: hai fields cùng trỏ một child

Một deep-copy routine có thể vô tình **phá quan hệ chia sẻ** bên trong original graph.

Ví dụ:

```text
Original:
a ──────┐
        ├──> Child X
b ──────┘
```

Nếu clone mỗi field riêng:

```text
Copied:
a ──────> Child X1
b ──────> Child X2
```

Giờ `copied.a == copied.b` là false, trong khi original.a == original.b là true. Nếu domain quan trọng rằng hai fields chính là cùng node (ví dụ graph, owner-reference, shared vertex), bản sao này **không giữ semantics**.

Deep copy cần xác định **có giữ alias relations trong bản sao không**. Trong graph cloning, thường cần map từ original identity sang copied identity.

## 39. Thí nghiệm bảo toàn alias trong deep-copy graph có chu kỳ

Tạo **`CyclicGraphCopyDemo.java`**:

```java
import java.util.IdentityHashMap;
import java.util.Map;

final class Node {
    String name;
    Node next;
    Node shared;

    Node(String name) {
        this.name = name;
    }
}

public class CyclicGraphCopyDemo {
    static Node deepCopy(
            Node original, Map<Node, Node> copies) {
        if (original == null) {
            return null;
        }

        Node cached = copies.get(original);
        if (cached != null) {
            return cached;
        }

        Node copy = new Node(original.name);
        copies.put(original, copy);

        copy.next = deepCopy(original.next, copies);
        copy.shared = deepCopy(original.shared, copies);
        return copy;
    }

    public static void main(String[] args) {
        Node a = new Node("A");
        Node b = new Node("B");

        a.next = b;
        b.next = a;
        a.shared = b;

        Node copied = deepCopy(
                a, new IdentityHashMap<>());

        System.out.println(a == copied);
        System.out.println(a.next == copied.next);
        System.out.println(copied.next.next == copied);
        System.out.println(copied.next == copied.shared);

        copied.next.name = "B2";
        System.out.println(b.name);
        System.out.println(copied.next.name);
    }
}
```

```bash
javac CyclicGraphCopyDemo.java
java CyclicGraphCopyDemo
```

```text
false
false
true
true
B
B2
```

**Vì sao dùng `IdentityHashMap`?** Graph copying phải phân biệt **object identity**, không gộp hai nodes chỉ vì `equals()` true. Map lưu mỗi original object → đúng một copied object.

**Vì sao put trước khi đệ quy?** Khi gặp cycle a → b → a, recursive call về a sẽ tìm được copy đã lưu; nếu không lưu sớm, đệ quy có thể vô hạn.

**Giới hạn:** Đây là graph copy minh họa đơn luồng, không xử lý concurrency, subclass types, custom resources hoặc extremely deep graph có thể làm stack overflow. Trong hệ thật cần nêu rõ graph model và copy contract.

## 40. `Object.clone()`: mặc định nông và có nhiều ràng buộc

`Object.clone()` là protected method. Thông thường class phải implement `Cloneable` và override/publicize method nếu muốn cung cấp API clone cho callers. Implementation mặc định tạo **field-wise shallow copy** của object, không gọi một copy constructor để clone nested children.

Tạo **`ShallowObjectCloneDemo.java`**:

```java
final class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

final class Member implements Cloneable {
    String name;
    Address address;

    Member(String name, Address address) {
        this.name = name;
        this.address = address;
    }

    @Override
    public Member clone() {
        try {
            return (Member) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class ShallowObjectCloneDemo {
    public static void main(String[] args) {
        Member original =
                new Member("An", new Address("Hue"));
        Member copy = original.clone();

        System.out.println(original == copy);
        System.out.println(original.address == copy.address);

        copy.address.city = "Da Nang";
        System.out.println(original.address.city);
    }
}
```

```bash
javac ShallowObjectCloneDemo.java
java ShallowObjectCloneDemo
```

```text
false
true
Da Nang
```

**Điểm quan trọng:**

- Member copy khác original.
- Address vẫn cùng identity vì `super.clone()` sao chép reference field.
- Nếu class không implement Cloneable mà dùng `super.clone()`, thường sẽ gặp `CloneNotSupportedException`.
- `Cloneable` là marker interface, bản thân nó không khai báo một public `clone()` method.
- Không mặc nhiên xem Object.clone là deep clone.
- Với final/reference fields chứa mutable objects, thiết kế clone có thể phức tạp.

Trong nhiều ứng dụng domain, **copy constructor hoặc static factory có tên diễn tả contract** thường dễ đọc và validate hơn `Cloneable`.

## 41. Thử clone array và clone object: cùng tên, khác chi tiết

Array types trong Java hỗ trợ public `clone()` và kết quả đúng kiểu array, nhưng:

- `int[].clone()` → copy primitive values, thường đủ độc lập về contents.
- `Item[].clone()` → copy reference elements, Item objects vẫn chia sẻ.
- `int[][].clone()` → copy outer references, inner arrays vẫn chia sẻ.

Đối với một class implement `Cloneable`, gọi `super.clone()` cũng tạo shallow copy theo fields.

**Đừng dùng từ “clone” làm bằng chứng về mức sao chép.** Cần xét **kiểu thành phần và implementation**, không chỉ method name.

## 42. Sao chép bằng serialization: cân nhắc nhưng không coi là mặc định

Một số thiết kế serialize object graph rồi deserialize để có bản sao. Cách này có thể tách state theo representation, nhưng không phải một deep-copy primitive bảo đảm cho mọi Java object:

- Mọi thành phần phải tương thích serialization mechanism.
- Fields `transient` có thể mất.
- Object identity/alias có rules riêng của serialization mechanism.
- Có thể tốn CPU/memory.
- Constructors, validation, security boundaries có semantics đặc biệt.
- Không phải strategy hợp lý cho connections, locks, threads, external handles.
- Native Java serialization có nhiều vấn đề bảo mật khi đọc dữ liệu không tin cậy.

**Khuyến nghị thực hành:** Dùng copy constructor/factory rõ contract, immutable snapshots hoặc mapping DTO; chỉ dùng serialization-based copying nếu domain, bảo mật và performance cho phép.

## 43. Equality `equals()` khác identity `==`

Hai objects có thể mang giá trị giống nhau nhưng khác identity.

Tạo **`EqualityVersusIdentityDemo.java`**:

```java
record Point(int x, int y) {
}

public class EqualityVersusIdentityDemo {
    public static void main(String[] args) {
        Point first = new Point(2, 3);
        Point second = new Point(2, 3);
        Point alias = first;

        System.out.println(first == second);
        System.out.println(first.equals(second));
        System.out.println(first == alias);
    }
}
```

```bash
javac EqualityVersusIdentityDemo.java
java EqualityVersusIdentityDemo
```

```text
false
true
true
```

`equals` trả true cho two Point records cùng component values. `==` trả false giữa first và second vì distinct objects. Alias true vì same reference.

**Khi kiểm deep-copy correctness**, cần cả hai câu hỏi:

1. Copy giữ giá trị semantics chưa?
2. Những mutable objects cần độc lập có identity khác chưa?

Chỉ test `original.equals(copy)` có thể bỏ sót aliasing gây mutation leak.

## 44. Record chứa array: `equals` có thể gây bất ngờ

Tạo **`RecordArrayEqualityDemo.java`**:

```java
record PackageData(int[] numbers) {
}

public class RecordArrayEqualityDemo {
    public static void main(String[] args) {
        int[] a = {1, 2};
        int[] b = {1, 2};

        PackageData first = new PackageData(a);
        PackageData second = new PackageData(b);
        PackageData shared = new PackageData(a);

        System.out.println(first.equals(second));
        System.out.println(first.equals(shared));
    }
}
```

```bash
javac RecordArrayEqualityDemo.java
java RecordArrayEqualityDemo
```

```text
false
true
```

Hai mảng a/b có contents giống nhau nhưng identity khác; generated record equals xử lý array component theo reference equality. `first.equals(shared)` true vì cùng array reference.

Nếu domain muốn so array contents, cần representation/method equals/hashCode theo nội dung. **Đừng đoán** record sinh ra deep equals cho nested arrays.

## 45. Truyền tham trị không bảo đảm thread safety

Nếu hai threads giữ references đến cùng mutable object, pass-by-value không ngăn race. Chẳng hạn `counter.value++` không tự atomic vì giá trị tham chiếu được copy khi đưa cho thread khác.

**Tách ba trục thiết kế:**

- **Reference aliasing:** có chia sẻ cùng object không?
- **Mutability/ownership:** ai được thay state?
- **Concurrency:** nếu nhiều threads truy cập, đồng bộ/happens-before và atomicity có đúng không?

Nếu class cần shared mutable state đồng thời, cân nhắc synchronization, locks, atomic types hoặc immutable messages theo Java Memory Model. Copy object thành snapshot có thể giảm sharing nhưng không giải quyết tất cả atomicity/visibility problems nếu snapshot được tạo trong lúc source đang bị sửa mà không synchronization.

## 46. Thí nghiệm đồng bộ đơn giản với shared AtomicInteger

Tạo **`SharedAtomicReferenceDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class SharedAtomicReferenceDemo {
    public static void main(String[] args)
            throws InterruptedException {
        AtomicInteger counter = new AtomicInteger(0);
        AtomicInteger alias = counter;

        Thread worker = new Thread(alias::incrementAndGet);
        worker.start();
        worker.join();

        System.out.println(counter == alias);
        System.out.println(counter.get());
    }
}
```

```bash
javac SharedAtomicReferenceDemo.java
java SharedAtomicReferenceDemo
```

```text
true
1
```

Hai variables cùng trỏ một AtomicInteger. Worker gọi atomic increment; `join` chờ công việc hoàn tất, output xác định. Đây là cách minh họa aliasing trong concurrent scenario mà không dùng data race.

**Không hiểu ngược:** `AtomicInteger` bảo đảm atomic operations theo contract, nhưng nó **không** biến mọi phép toán nhiều bước trên những objects khác thành atomic.

## 47. API design: chia sẻ reference là một quyết định công khai

Khi một class nhận list/array, hãy quyết định rõ:

| API contract | Cách thường gặp | Rủi ro/đặc tính |
| --- | --- | --- |
| Share mutable state có chủ đích | Lưu same reference | External mutations tác động đến owner |
| Input snapshot primitive array | `input.clone()` | Tách array contents |
| Input snapshot immutable elements | `List.copyOf(input)` | List snapshot, elements có thể shared |
| Input snapshot mutable elements | Copy mỗi mutable element | Thêm allocation, cần deep policy |
| Live read-only view | `Collections.unmodifiableList(backing)` | Reflect backing changes |
| Return mutable independent copy | `new ArrayList<>(internal)` | Caller sửa structure riêng, elements shared |
| Return array an toàn | `internal.clone()` | Với nested mutable elements cần thêm xử lý |
| Shared immutable value object | Return same object | An toàn nếu thực sự immutable và contract phù hợp |

API không có một lựa chọn duy nhất đúng cho mọi nơi. Điều quan trọng là **document và bảo vệ invariant phù hợp**.

## 48. Thí nghiệm thiết kế API sai: lưu thẳng array đầu vào

Tạo **`LeakyArrayOwnerDemo.java`**:

```java
final class Settings {
    private final int[] limits;

    Settings(int[] limits) {
        this.limits = limits;
    }

    int firstLimit() {
        return limits[0];
    }
}

public class LeakyArrayOwnerDemo {
    public static void main(String[] args) {
        int[] input = {10};
        Settings settings = new Settings(input);

        input[0] = 99;

        System.out.println(settings.firstLimit());
    }
}
```

```bash
javac LeakyArrayOwnerDemo.java
java LeakyArrayOwnerDemo
```

```text
99
```

`final` chỉ cấm gán lại field reference `limits`, không cấm array elements đổi. Caller còn giữ input reference, nên có thể mutate internal state của Settings mà class không kiểm.

Nếu Settings có trách nhiệm giữ immutable snapshot, constructor nên clone input và accessor (nếu có) cũng nên copy đầu ra. Nếu Settings **cố ý** chia sẻ live configuration array, thiết kế cần nêu rõ ownership/concurrency contract.

## 49. Thí nghiệm fix: input copy, output copy, test mutation

Tạo **`SafeArrayOwnerDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Settings {
    private final int[] limits;

    Settings(int[] limits) {
        this.limits =
                Objects.requireNonNull(limits).clone();
    }

    int[] limits() {
        return limits.clone();
    }
}

public class SafeArrayOwnerDemo {
    public static void main(String[] args) {
        int[] input = {10, 20};
        Settings settings = new Settings(input);

        input[0] = 99;
        int[] received = settings.limits();
        received[1] = 77;

        System.out.println(
                Arrays.toString(settings.limits()));
        System.out.println(Arrays.toString(input));
        System.out.println(Arrays.toString(received));
    }
}
```

```bash
javac SafeArrayOwnerDemo.java
java SafeArrayOwnerDemo
```

```text
[10, 20]
[99, 20]
[10, 77]
```

Settings giữ array riêng, input và output đều là arrays khác. Các mutations từ bên ngoài không tác động private limits.

**Bản chất:** Defensive copying là một cách enforce **ownership boundary**, không chỉ là một kỹ thuật Java syntax.

## 50. Chi phí sao chép: không copy “toàn bộ thế giới”

Copy có thể:

- Tạo allocations mới và tăng GC pressure.
- Chiếm thêm heap nếu graph lớn.
- Cần xử lý cycles và aliases.
- Làm mất ý nghĩa identity của entity.
- Tạo snapshot không đồng nhất nếu source mutable bị sửa đồng thời.
- Thay đổi resource ownership/transaction semantics nếu copy nhầm handles.
- Tạo lỗi performance khi copy lặp trong vòng lặp lớn.

### Các phương án cân nhắc

1. **Immutable values:** Chia sẻ an toàn, giảm copy.
2. **Defensive copy tại boundary:** Chỉ tách dữ liệu ở nơi ownership chuyển giao.
3. **Copy-on-write:** Chỉ copy khi cần mutate theo thiết kế phù hợp.
4. **Persistent immutable collections:** Chia sẻ cấu trúc bất biến có kiểm soát.
5. **DTO snapshots:** Chỉ copy dữ liệu cần xuất bản/ghi nhận.
6. **Explicit mutable ownership:** Cho phép share có quy tắc nếu thật sự cần.

**Đừng deep-copy một connection, thread, lock hoặc service singleton như dữ liệu nghiệp vụ.** Chúng có lifecycle và identity riêng.

## 51. Thí nghiệm chuỗi thời gian: đoán rồi kiểm từng lệnh

Tạo **`ReferenceTimelineDemo.java`**:

```java
final class Data {
    int count;

    Data(int count) {
        this.count = count;
    }
}

public class ReferenceTimelineDemo {
    static void process(Data value) {
        value.count += 2;
        value = new Data(50);
        value.count++;
        System.out.println("process=" + value.count);
    }

    public static void main(String[] args) {
        Data a = new Data(3);
        Data b = a;
        process(b);

        System.out.println("a=" + a.count);

        b = new Data(8);
        b.count += 2;

        System.out.println("a=" + a.count);
        System.out.println("b=" + b.count);
        System.out.println("shared=" + (a == b));
    }
}
```

```bash
javac ReferenceTimelineDemo.java
java ReferenceTimelineDemo
```

```text
process=51
a=5
a=5
b=10
shared=false
```

Bước luận giải:

1. a/b cùng trỏ Data(3).
2. Method process nhận bản sao reference b.
3. `value.count += 2` sửa object A thành 5.
4. `value = new Data(50)` đổi parameter sang object mới C.
5. `value.count++` làm C thành 51.
6. Caller a/b vẫn trỏ A(5).
7. `b = new Data(8)` đổi caller variable b sang object mới B; a vẫn A.
8. `b.count += 2` làm B thành 10.
9. a != b vì identities khác.

Nếu có thể giải thích ví dụ này mà không dựa vào câu “Java truyền tham chiếu”, bạn đã nắm mô hình chính xác.

## 52. Thí nghiệm so ba kiểu copy cùng một nguồn

Tạo **`ThreeCopyModesDemo.java`**:

```java
final class Detail {
    int score;

    Detail(int score) {
        this.score = score;
    }

    Detail(Detail source) {
        this.score = source.score;
    }
}

final class Report {
    String label;
    Detail detail;

    Report(String label, Detail detail) {
        this.label = label;
        this.detail = detail;
    }

    static Report shallow(Report source) {
        return new Report(source.label, source.detail);
    }

    static Report deep(Report source) {
        return new Report(
                source.label, new Detail(source.detail));
    }
}

public class ThreeCopyModesDemo {
    public static void main(String[] args) {
        Report original =
                new Report("A", new Detail(1));
        Report alias = original;
        Report shallow = Report.shallow(original);
        Report deep = Report.deep(original);

        System.out.println(original == alias);
        System.out.println(original == shallow);
        System.out.println(original.detail == shallow.detail);
        System.out.println(original.detail == deep.detail);

        alias.label = "B";
        shallow.detail.score = 9;
        deep.detail.score = 7;

        System.out.println(original.label);
        System.out.println(original.detail.score);
        System.out.println(deep.detail.score);
    }
}
```

```bash
javac ThreeCopyModesDemo.java
java ThreeCopyModesDemo
```

```text
true
false
true
false
B
9
7
```

- **Alias:** cùng Report, đổi label qua alias là đổi original.
- **Shallow:** Report mới nhưng Detail chung; đổi score qua shallow ảnh hưởng original.
- **Deep trong phạm vi Detail:** cả Report và Detail mới; đổi score qua deep không ảnh hưởng original.

Đây là ví dụ tổng hợp thích hợp nhất để đối chiếu ba khái niệm trước khi dùng API copy của thư viện.

## 53. Self-test 1 — Java luôn pass-by-value

Tạo **`PassByValueSelfTest.java`**:

```java
final class Holder {
    int value;

    Holder(int value) {
        this.value = value;
    }
}

public class PassByValueSelfTest {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void change(int primitive, Holder reference) {
        primitive = 99;
        reference.value = 7;
        reference = new Holder(100);

        check(primitive == 99, "local primitive");
        check(reference.value == 100, "local reference");
    }

    public static void main(String[] args) {
        int number = 1;
        Holder object = new Holder(2);

        change(number, object);

        check(number == 1, "caller primitive unchanged");
        check(object.value == 7, "shared object changed");

        System.out.println("pass-by-value PASS");
    }
}
```

```bash
javac PassByValueSelfTest.java
java PassByValueSelfTest
```

```text
pass-by-value PASS
```

Test xác nhận đồng thời: primitive variable ở caller không đổi, reference parameter rebind không đổi caller reference, và object chung được mutate qua parameter.

`check` ném AssertionError trực tiếp, không cần bật JVM `-ea`.

## 54. Self-test 2 — Shallow copy và deep copy

Tạo **`CopySemanticsSelfTest.java`**:

```java
final class Address {
    String city;

    Address(String city) {
        this.city = city;
    }

    Address(Address other) {
        city = other.city;
    }
}

final class Person {
    Address address;

    Person(Address address) {
        this.address = address;
    }

    static Person shallow(Person other) {
        return new Person(other.address);
    }

    static Person deep(Person other) {
        return new Person(new Address(other.address));
    }
}

public class CopySemanticsSelfTest {
    static void check(boolean value, String message) {
        if (!value) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Person original = new Person(new Address("Hue"));
        Person shallow = Person.shallow(original);
        Person deep = Person.deep(original);

        check(original != shallow, "shallow parent new");
        check(original.address == shallow.address,
                "shallow child shared");
        check(original != deep, "deep parent new");
        check(original.address != deep.address,
                "deep child independent");

        shallow.address.city = "Da Nang";
        check(original.address.city.equals("Da Nang"),
                "shallow mutation visible");

        deep.address.city = "Ha Noi";
        check(original.address.city.equals("Da Nang"),
                "deep mutation isolated");

        System.out.println("copy semantics PASS");
    }
}
```

```bash
javac CopySemanticsSelfTest.java
java CopySemanticsSelfTest
```

```text
copy semantics PASS
```

Self-test không dùng GC hay địa chỉ bộ nhớ. Nó kiểm **identities và behaviors** xác định. Bản sao deep được định nghĩa đủ rõ cho object graph nhỏ ở đây.

## 55. Self-test 3 — Không rò mutable array qua constructor/accessor

Tạo **`DefensiveCopySelfTest.java`**:

```java
import java.util.Arrays;

final class ImmutableScores {
    private final int[] scores;

    ImmutableScores(int[] scores) {
        this.scores = scores.clone();
    }

    int[] scores() {
        return scores.clone();
    }
}

public class DefensiveCopySelfTest {
    static void check(boolean value, String label) {
        if (!value) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2, 3};
        ImmutableScores holder = new ImmutableScores(input);

        input[0] = 99;
        int[] exposed = holder.scores();
        exposed[1] = 88;

        check(Arrays.equals(
                holder.scores(), new int[] {1, 2, 3}),
                "snapshot unchanged");

        System.out.println("defensive copy PASS");
    }
}
```

```bash
javac DefensiveCopySelfTest.java
java DefensiveCopySelfTest
```

```text
defensive copy PASS
```

Phép thử dùng `Arrays.equals` vì quan tâm **nội dung** primitive arrays. Dùng `==` ở đây sẽ chỉ kiểm identity, không kiểm ba giá trị được giữ.

## 56. Bài tập 1 — Dự đoán reference identity và output

Cho chương trình:

```java
final class Box {
    int n;

    Box(int n) {
        this.n = n;
    }
}

public class ExerciseOne {
    public static void main(String[] args) {
        Box a = new Box(1);
        Box b = a;
        Box c = new Box(1);

        b.n = 5;

        System.out.println(a.n);
        System.out.println(a == b);
        System.out.println(a == c);
    }
}
```

Lưu thành **`ExerciseOne.java`**.

```bash
javac ExerciseOne.java
java ExerciseOne
```

```text
5
true
false
```

**Lời giải:** a/b cùng trỏ object đầu tiên; c là object khác dù n ban đầu giống. Sửa qua b làm a.n = 5.

## 57. Bài tập 2 — Dự đoán array parameter rebind

Lưu thành **`ExerciseTwo.java`**:

```java
import java.util.Arrays;

public class ExerciseTwo {
    static void update(int[] values) {
        values[0] = 10;
        values = new int[] {20};
        System.out.println(Arrays.toString(values));
    }

    public static void main(String[] args) {
        int[] source = {1};
        update(source);
        System.out.println(Arrays.toString(source));
    }
}
```

```bash
javac ExerciseTwo.java
java ExerciseTwo
```

```text
[20]
[10]
```

**Lời giải:** Thao tác đầu mutate shared array; gán parameter sang new array không đổi source reference ở caller.

## 58. Bài tập 3 — Thêm copy method cho List có mutable elements

Yêu cầu có `List<Task>`; mỗi Task chứa `String name` và `int progress` mutable. Hãy viết một method trả **list độc lập và Task objects độc lập**.

Một lời giải runnable là **`ExerciseThree.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Task {
    String name;
    int progress;

    Task(String name, int progress) {
        this.name = name;
        this.progress = progress;
    }

    Task(Task source) {
        this(source.name, source.progress);
    }
}

public class ExerciseThree {
    static List<Task> deepCopy(List<Task> input) {
        List<Task> result = new ArrayList<>();

        for (Task task : input) {
            result.add(new Task(task));
        }
        return result;
    }

    public static void main(String[] args) {
        List<Task> original =
                new ArrayList<>(List.of(new Task("A", 10)));

        List<Task> copied = deepCopy(original);
        copied.get(0).progress = 99;

        System.out.println(original.get(0).progress);
        System.out.println(copied.get(0).progress);
    }
}
```

```bash
javac ExerciseThree.java
java ExerciseThree
```

```text
10
99
```

**Giới hạn:** Nếu list đầu vào cho phép null elements, ví dụ phải định nghĩa policy cho null trước khi `new Task(task)`. Nếu Task có reference đến mutable children khác, copy constructor cần mở rộng theo contract.

## 59. Bài tập 4 — Sửa record có mutable array

Cho:

```java
record Palette(int[] rgb) {
}
```

Người gọi có thể sửa `rgb` sau constructor hoặc lấy `palette.rgb()` rồi sửa nội dung. Yêu cầu: giữ một snapshot primitive array, kiểm đúng ba channels, không cho sửa state qua accessor.

Một lời giải:

```java
record Palette(int[] rgb) {
    Palette {
        if (rgb == null || rgb.length != 3) {
            throw new IllegalArgumentException("RGB length");
        }
        rgb = rgb.clone();
    }

    @Override
    public int[] rgb() {
        return rgb.clone();
    }
}
```

Đây là **đoạn khai báo minh họa**, hai phiên bản Palette là phương án trước/sau **không khai báo cùng compilation unit**.

**Nâng cao:** Các channels có cần nằm trong [0,255] không? Nếu có, validation là trách nhiệm của Palette. Cần equality theo nội dung RGB hay identity? Nếu cần, override equals/hashCode tương ứng với Arrays.equals/Arrays.hashCode. Đừng ngầm giả định defensive copying tự thay đổi generated record equality.

## 60. Bài tập 5 — Xây graph copy giữ cycle

Với các nodes A → B → A, hãy sao chép sao cho:

- A copy khác A original.
- B copy khác B original.
- A copy.next trỏ B copy.
- B copy.next trỏ A copy.
- Nếu hai references trong source cùng trỏ B, hai references tương ứng ở copy phải cùng trỏ B copy.

**Gợi ý:** `IdentityHashMap<OriginalNode, CopiedNode>`, kiểm map trước; tạo copy và put vào map **trước** khi đệ quy copy children. Thí nghiệm `CyclicGraphCopyDemo` cho lời giải runnable đầy đủ.

**Không dùng HashMap chỉ vì tiện** nếu equals của nodes có thể gộp hai instances cùng nội dung nhưng khác identity.

## 61. Các sai lầm thường gặp

| Phát biểu hoặc code sai | Vấn đề | Cách hiểu/sửa |
| --- | --- | --- |
| “Java pass-by-reference” | Parameter không alias caller variable | Java pass-by-value của reference value |
| `b = a` là copy object | Chỉ copy reference | Dùng new/copy constructor/factory |
| Mutate parameter tức là đổi biến caller | Mutate object, không đổi biến caller | Phân biệt `p.field` và `p =` |
| Gán parameter sang new object đổi caller | Rebind local parameter | Return reference mới, caller chủ động gán |
| `swap(a,b)` hoán đổi caller variables | Chỉ swap local params | Swap tại caller hoặc mutable holder |
| Array là primitive | Array là object | Mảng có identity, alias được |
| `array.clone()` luôn deep | Reference elements vẫn shared | Copy nested mutable elements nếu cần |
| `new ArrayList<>(old)` deep-copy | Chỉ copy structure | Copy element objects phù hợp |
| `List.copyOf` làm elements immutable | Unmodifiable structure, shallow elements | Immutable elements hoặc deep snapshots |
| Unmodifiable view là snapshot | View phản ánh backing updates | `List.copyOf`/copy container |
| `record` chứa `int[]` tự immutable | Array mutable bị share | Constructor/accessor defensive copies |
| Record arrays tự so deep equals | Generated equals dùng reference equality cho array | Custom equals/hashCode hoặc immutable representation |
| `Object.clone()` là deep clone | super.clone field-wise shallow | Copy constructor/factory rõ |
| Deep copy phải clone cả singleton/socket | Resources/identity có contract riêng | Chỉ copy value state cần thiết |
| Deep copy luôn giữ graph topology | Naive recursion có thể nhân đôi shared child | Identity map khi cần |
| Cyclic graph copy dùng đệ quy thuần | Dễ stack overflow vô hạn | Memoize copy trước khi recurse |
| `==` kiểm same value | Với references, kiểm identity | `equals` cho value contract |
| `equals` true chứng minh deep copy | Vẫn có thể share nested objects | Check nested identity và mutation isolation |
| `final` reference làm object immutable | Chỉ chặn reassign field | Defensive copy/immutable components |
| Gán null là giải phóng object tức thì | Không có GC deadline | Quản lý owner/retention path |
| Sao chép state đồng thời luôn snapshot nhất quán | Source có thể bị sửa giữa các lần copy | Cần concurrency/snapshot policy |
| Shallow copy luôn sai | Có thể đủ với immutable children | Chọn theo mutable graph và contract |
| Deep copy luôn tốt hơn | Tăng cost và có thể sai identity | Chọn depth theo yêu cầu |
| `Arrays.equals` giống `==` | So contents vs identity | Chọn đúng loại câu hỏi |
| Cùng tên method clone nghĩa cùng semantics | Contract phụ thuộc kiểu và implementation | Xem source/API documentation |

## 62. Checklist thực hành trước khi dùng đối tượng hay API copy

### A. Tham chiếu

- [ ] Tôi phân biệt biến tham chiếu và object chưa?
- [ ] Tôi biết `a == b` kiểm identity, không phải equality theo value?
- [ ] Assignment `b = a` có chỉ copy reference value?
- [ ] Có thể nhiều fields/list slots cùng trỏ một mutable child?
- [ ] Tôi đã vẽ reference arrows ở các chỗ dễ nhầm?

### B. Truyền tham trị

- [ ] Tôi hiểu primitive và reference **đều pass-by-value**?
- [ ] Gán lại parameter chỉ đổi parameter local?
- [ ] Sửa mutable object qua parameter sẽ có tác động qua aliases?
- [ ] Nếu muốn đổi caller reference, method có nên return object mới?
- [ ] Đã thử case mutate rồi rebind?
- [ ] Không dùng khái niệm “copy cả object khi truyền argument”?

### C. Sao chép

- [ ] Đây là alias assignment, container copy hay deep copy?
- [ ] Nếu array primitive, clone có đáp ứng independence cần thiết?
- [ ] Nếu array references, có copy elements chưa?
- [ ] Nếu mảng nhiều chiều, có copy rows cần thiết?
- [ ] Nếu List/Map, đã xét nested mutable objects?
- [ ] Có phân biệt `List.copyOf` với unmodifiable view?
- [ ] Nếu dùng record chứa mutable component, constructor/accessor đã phòng vệ?
- [ ] Nếu dùng Object.clone, có hiểu mặc định field-wise shallow?
- [ ] Deep-copy graph có cycles/aliases cần IdentityHashMap?
- [ ] Có fields nào là shared service/resource **không** được copy?
- [ ] Có thể thiết kế immutable value object thay deep-copy machinery?

### D. Đảm bảo API

- [ ] Ai sở hữu state và quyền thay đổi?
- [ ] Constructor có giữ input alias dẫn tới invariant leak?
- [ ] Accessor có lộ mutable internals không?
- [ ] Equality/hashCode có khớp value/identity semantics?
- [ ] Copy giữ những invariants nào?
- [ ] Copy giữ alias topology khi cần không?
- [ ] Copy có thực hiện dưới synchronization thích hợp nếu source concurrent?
- [ ] Có test success/failure/mutation isolation chứ không chỉ copy result equals?
- [ ] Có đo cost trước khi copy một graph lớn trong loop nóng?

## 63. Câu hỏi ôn tập nhanh có đáp án

**1.** `Person b = a` có tạo Person mới không?

*Không; chỉ copy reference value.*

**2.** Nếu `a == b` và `b.name = "X"`, a có thấy name mới không?

*Có nếu mutable field của cùng object bị sửa và không có concurrency visibility issue.*

**3.** `b = new Person()` có đổi a không?

*Không; b được gán reference khác.*

**4.** Java truyền primitive parameter thế nào?

*Copy primitive value.*

**5.** Java truyền reference parameter thế nào?

*Copy reference value, không copy object.*

**6.** Phương thức có thay trực tiếp biến cục bộ caller bằng cách gán parameter không?

*Không.*

**7.** Phương thức có mutate object caller đang trỏ không?

*Có, nếu parameter trỏ cùng mutable object và method có quyền mutate.*

**8.** Vì sao swap method không swap caller variables?

*Vì nó chỉ gán lại các parameter locals.*

**9.** Array được truyền vào method có thể bị sửa elements không?

*Có; method nhận copy reference nhưng cùng array object.*

**10.** `int[] copy = source.clone()` có tạo array object mới không?

*Có.*

**11.** Clone int[] có làm primitive elements độc lập không?

*Có, vì element values được copy.*

**12.** Clone Item[] có tạo Item objects mới không?

*Không mặc định; reference elements được copy.*

**13.** `new ArrayList<>(old)` có tạo List mới không?

*Có.*

**14.** List elements là mutable objects có bị deep-copy theo đó không?

*Không.*

**15.** `List.copyOf` có bảo đảm mutable element objects không thay đổi không?

*Không.*

**16.** `Collections.unmodifiableList` có là snapshot không?

*Không; nó là view của backing list.*

**17.** Record với component `int[]` tự deeply immutable không?

*Không.*

**18.** Vì sao cần clone array trong record constructor và accessor?

*Để tránh caller mutate internal array qua input/output aliases.*

**19.** Defensive copy có làm generated record equals so array contents không?

*Không.*

**20.** Với hai Point records cùng x/y nhưng được new riêng, `==` thường là gì?

*False, vì distinct object identities.*

**21.** `equals` có thể true dù `==` false không?

*Có, với value equality contract.*

**22.** Shallow copy Customer có Address reference chung thì sao?

*Mutation trên Address thông qua copy có thể tác động original.*

**23.** Deep copy Customer/Address tốt hơn ở điểm nào?

*Nó cho independent Address state trong phạm vi contract.*

**24.** Deep copy có luôn cần clone String không?

*Không; String immutable và an toàn chia sẻ value.*

**25.** Vì sao graph copy cần identity map?

*Để giữ alias relationships và ngăn recursion vô hạn qua cycles.*

**26.** `Object.clone()` default là shallow hay deep?

*Field-wise shallow.*

**27.** `Cloneable` có tự khai báo public clone method không?

*Không; nó là marker interface.*

**28.** `System.gc()` có cần thiết để kiểm copy đúng không?

*Không. Dùng identity và mutation tests xác định.*

**29.** Copying liên quan gì đến encapsulation?

*Defensive copy giúp lớp giữ ownership và bảo vệ invariants ở boundary.*

**30.** Nếu children immutable thì shallow container copy có thể đủ không?

*Có, khi contract chỉ cần structural independence.*

**31.** Nếu data được sửa đồng thời lúc copy thì sao?

*Có thể tạo snapshot không nhất quán; cần synchronization hoặc immutable snapshot mechanism.*

**32.** Một câu tóm tắt đúng về Java references là gì?

*Biến giữ reference values; nhiều biến có thể cùng trỏ một object; method luôn nhận bản sao argument value; copy nông/sâu phải xét từng tầng của object graph.*

## 64. Bài tập tự kiểm không cần chạy GC

Hãy tự tạo một class `Profile` chứa `String displayName` và `List<StringBuilder> notes`, rồi triển khai ba phiên bản:

1. **Reference alias:** `Profile b = a`.
2. **Shallow:** `new Profile(a.displayName, new ArrayList<>(a.notes))`.
3. **Deep theo phạm vi StringBuilder:** Tạo List mới, mỗi StringBuilder element mới bằng constructor copy `new StringBuilder(old.toString())`.

Sau đó viết tests cho:

- `a == b` trong alias.
- `a != shallow` nhưng `a.notes.get(0) == shallow.notes.get(0)`.
- `a != deep` và `a.notes.get(0) != deep.notes.get(0)`.
- `shallow.notes.get(0).append("!")` tác động original.
- `deep.notes.get(0).append("!")` không tác động original.
- `shallow.notes.add(...)` không làm original list có element mới.
- Input null/empty list policy và ownership.
- Nếu list có **hai slots cùng trỏ một StringBuilder**, deep copier có giữ alias topology không? Có cần giữ không?

**Đáp án định hướng:** Alias giữ toàn bộ identity. Shallow tách container nhưng share elements. Deep tách elements theo policy; muốn bảo toàn alias khi hai slots gốc trỏ cùng instance, cần một map từ original element identity sang copied element identity, không tạo copy riêng cho từng slot.

## 65. Tham khảo chính thức

- *Java Language Specification, Java SE 17 — `15.12 Method Invocation Expressions*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12 — argument evaluation và invocation semantics.
- *Java Language Specification, Java SE 17 — `4 Types, Values, and Variables*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html — primitive/reference types và values.
- *Java Language Specification, Java SE 17 — `10 Arrays*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html — arrays là objects, clone và elements.
- *Java SE 17 API — `java.lang.Object.clone`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html#clone() — clone contract và `CloneNotSupportedException`.
- *Java SE 17 API — `java.util.List.copyOf`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection) — unmodifiable snapshot semantics.
- *Java SE 17 API — `java.util.IdentityHashMap`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html — key equality theo object identity.
- *Java SE 17 API — `java.util.Arrays`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html — copyOf, equals, deepEquals, toString, deepToString.

---

**Ghi nhớ cuối bài:** Trong Java, `b = a` với reference types chỉ **copy reference value**, khiến hai biến có thể **dùng chung một mutable object**. Java **luôn truyền tham trị**: tham số nhận bản sao primitive value hoặc bản sao reference value; vì vậy **gán lại parameter không đổi caller variable**, nhưng **mutate shared object qua parameter có thể thay đổi state caller quan sát được**. **Shallow copy** tạo object/container mới nhưng thường chia sẻ mutable children; **deep copy** phải chủ động tách những mutable descendants thuộc contract, và có thể cần giữ aliases/cycles bằng identity map. Array clone, List copy, record, Object.clone không tự động có cùng độ sâu. Hãy chọn copy policy theo **ownership, mutability và invariants**, kiểm bằng `==`, nội dung và mutation isolation, thay vì đoán theo tên biến hoặc đợi GC.