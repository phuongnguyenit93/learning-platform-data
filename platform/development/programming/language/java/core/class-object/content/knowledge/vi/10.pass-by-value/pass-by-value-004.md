# Vì sao phương thức có thể sửa trạng thái đối tượng bên ngoài trong Java?

## 1. Câu trả lời ngắn: truyền tham trị vẫn có thể chia sẻ cùng đối tượng

Java luôn sử dụng **truyền tham trị** (*pass-by-value*) khi gọi phương thức. Quy tắc này áp dụng cho cả kiểu nguyên thủy như `int`, `double`, `boolean` lẫn **kiểu tham chiếu** như `Student`, `Account`, `StringBuilder`, `int[]` và `List<String>`.

Điểm dễ nhầm nằm ở chỗ **giá trị được truyền** là gì:

- Với biến kiểu nguyên thủy, Java sao chép **giá trị nguyên thủy** (ví dụ số `10`).
- Với biến kiểu tham chiếu, Java sao chép **giá trị tham chiếu tới một đối tượng**. Phương thức nhận bản sao ấy trong biến tham số riêng của nó.
- Hai biến tham chiếu — một ở nơi gọi và một là tham số trong phương thức — vì thế **có thể cùng trỏ tới đúng một object**.
- Nếu method dùng tham số để **thay đổi trạng thái của object chung**, nơi gọi có thể quan sát trạng thái mới.
- Nhưng nếu method chỉ **gán lại biến tham số** sang object khác, biến tham chiếu của nơi gọi **không tự thay đổi**.

Ví dụ:

```java
class Account {
    int balance;

    Account(int balance) {
        this.balance = balance;
    }
}

class Example {
    static void deposit(Account parameter) {
        parameter.balance += 50;
    }

    static void reassign(Account parameter) {
        parameter = new Account(999);
    }
}
```

Đây là **khai báo lớp minh họa**, chưa có `main`. Nếu caller có `Account mine = new Account(100);`, thì `Example.deposit(mine)` làm `mine.balance` thành `150`, trong khi `Example.reassign(mine)` **không** làm `mine` chuyển sang account có số dư `999`.

> **Quy tắc trung tâm:** Java **sao chép tham chiếu**, không tự sao chép object. Vì có thể cùng tham chiếu tới một object có thể sửa đổi (*mutable object*), phương thức vẫn có khả năng gây ra **tác động quan sát được từ bên ngoài** (*side effect*) — hoàn toàn không mâu thuẫn với pass-by-value.

## 2. Phân biệt bốn thứ thường bị gọi nhầm là “tham chiếu”

Để giải thích đúng, hãy phân biệt:

| Khái niệm | Vai trò | Trong lời gọi phương thức |
| --- | --- | --- |
| **Object** | Thực thể có identity và state, ví dụ `Account{balance=100}` | Object không tự bị sao chép chỉ vì truyền đối số |
| **Biến ở caller** | Một ô biến như `mine` có kiểu `Account`, chứa giá trị tham chiếu | Vẫn là biến của caller |
| **Giá trị tham chiếu** | Giá trị biểu thị một object cụ thể, hoặc `null` | Java sao chép giá trị này |
| **Biến tham số** | Một biến cục bộ thuộc lời gọi method, ví dụ `parameter` | Nhận bản sao; có thể gán lại riêng |

Hình dung:

```text
Caller                                  Method deposit

mine : Account ──────────┐
                         ├──────────> Object A
parameter : Account ─────┘             balance = 100

Hai ô biến khác nhau. Hai giá trị tham chiếu cùng chỉ Object A.
```

Sau lệnh `parameter.balance += 50`:

```text
mine ────────────────────┐
                         ├──────────> Object A
parameter ───────────────┘             balance = 150
```

Không có **biến caller nào bị gán lại**; chỉ có **field của Object A** đổi từ 100 sang 150.

Sau lệnh `parameter = new Account(999)` trong một method khác:

```text
mine ─────────────────────────────> Object A: balance = 150

parameter ────────────────────────> Object B: balance = 999
```

Lúc này **mũi tên của tham số** đổi, không phải mũi tên của `mine`.

Các sơ đồ trên chỉ mô tả **quan hệ tham chiếu theo ngữ nghĩa Java**, không khẳng định vị trí vật lý của biến trên stack hay địa chỉ object trên heap; cách bố trí thật do JVM quản lý.

## 3. Ví dụ độc lập quan trọng nhất: sửa object khác gán lại tham số

Lưu toàn bộ mã vào tệp **`MutationVsReassignmentDemo.java`** (JDK 17+):

```java
class Account {
    private int balance;

    Account(int balance) {
        this.balance = balance;
    }

    void deposit(int amount) {
        balance += amount;
    }

    int balance() {
        return balance;
    }
}

public class MutationVsReassignmentDemo {
    static void edit(Account target) {
        target.deposit(20);
        target = new Account(999);
        target.deposit(1);
        System.out.println("inside=" + target.balance());
    }

    public static void main(String[] args) {
        Account account = new Account(100);
        Account alias = account;

        edit(account);

        System.out.println("outside=" + account.balance());
        System.out.println("alias=" + alias.balance());
        System.out.println("same=" + (account == alias));
    }
}
```

Biên dịch/chạy:

```bash
javac MutationVsReassignmentDemo.java
java MutationVsReassignmentDemo
```

**Kết quả:**

```text
inside=1000
outside=120
alias=120
same=true
```

Giải thích từng bước:

1. `new Account(100)` tạo **Object A**, field `balance=100`. Biến `account` trỏ Object A.
2. `Account alias = account;` chỉ sao chép giá trị tham chiếu. `alias` cũng trỏ Object A; **không có Account mới**.
3. Khi `edit(account)` bắt đầu, tham số `target` nhận **bản sao tham chiếu** trỏ Object A.
4. `target.deposit(20)` gọi instance method trên Object A, làm `balance` đổi từ 100 thành 120. Biến `account` và `alias` vẫn trỏ Object A nên sau này đều đọc được 120.
5. `target = new Account(999)` tạo **Object B**, rồi **chỉ thay tham chiếu cục bộ** trong tham số `target`. `account` và `alias` không chuyển sang B.
6. `target.deposit(1)` gọi method trên Object B, nâng số dư B thành 1000; vì vậy in `inside=1000`.
7. Sau khi `edit` kết thúc, caller vẫn giữ Object A có số dư 120; in `outside=120` và `alias=120`. `account == alias` là `true` vì cả hai cùng giữ tham chiếu tới A.

**Bảng truy vết:**

| Thời điểm | `account` ở caller | `alias` ở caller | `target` trong method | Trạng thái |
| --- | --- | --- | --- | --- |
| Trước gọi | A | A | Chưa tồn tại | A.balance=100 |
| Vừa vào `edit` | A | A | A | A.balance=100 |
| Sau `target.deposit(20)` | A | A | A | A.balance=120 |
| Sau `target = new Account(999)` | A | A | B | A=120, B=999 |
| Sau `target.deposit(1)` | A | A | B | A=120, B=1000 |
| Sau khi return | A | A | Hết scope | A=120 |

**Kết luận:** “Method sửa được object của caller” và “method gán lại được biến của caller” là **hai phát biểu hoàn toàn khác nhau**. Java cho phép điều đầu trong nhiều tình huống, nhưng không thực hiện điều sau chỉ bằng phép gán lại một tham số.

## 4. So với kiểu nguyên thủy: không có object chung để sửa

Với primitive `int`, callee chỉ nhận bản sao **giá trị số**, không có object `int` chung để sửa:

```java
static void addTen(int number) {
    number += 10;
}

// Trong caller:
int points = 5;
addTen(points);
// points vẫn bằng 5.
```

Đối chiếu với object có mutable state:

| Thao tác trong method | Đích của phép thay đổi | Biến caller đổi tham chiếu/giá trị? | Object chung bị sửa? |
| --- | --- | --- | --- |
| `number = 99;` | Biến tham số primitive | Không | Không |
| `target = new Account(99);` | Biến tham số tham chiếu | Không | Không |
| `target.deposit(10);` | State của object chung | Không | Có |
| `array[0] = 10;` | Slot của array chung | Không | Có |
| `array = new int[3];` | Biến tham số mảng | Không | Không |

Các biểu thức trên là **snippets**, giả định biến/kiểu và method tương ứng tồn tại. Điểm khác biệt là **đích được gán**: một parameter variable riêng hay state của object có aliases. Bài riêng về primitives phân tích sâu widening, boxing, overload và đánh giá đối số; ở đây so sánh chỉ để soi rõ câu hỏi “vì sao method sửa được object bên ngoài?”.

## 5. Instance method sử dụng `this`: caller không cần truyền tham số tường minh

Có một cơ chế liên quan dễ bị lẫn với tham số: **instance method** luôn được gọi trong ngữ cảnh một **receiver object**.

```java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void increment() {
        this.value++;
    }

    int value() {
        return this.value;
    }
}
```

Nếu có `Counter counter = new Counter(4);` và gọi `counter.increment();`, trong thân `increment()`, `this` trỏ chính object mà `counter` đang tham chiếu. Lệnh `this.value++` sửa field của receiver đó. Đó là lý do caller sau đó đọc `counter.value()` sẽ thấy `5`.

**Phân biệt với pass-by-value:** Với `counter.increment()` không có tham số object tường minh; object được chọn làm **receiver** của instance method. Với `Utility.increment(counter)` là lời gọi static method có thể nhận tham chiếu `counter` làm **đối số**, và tham số của method nhận bản sao giá trị tham chiếu. Trong cả hai cách, cuối cùng một method có thể sửa **cùng object**.

### Ví dụ chạy: receiver khác nhau thì object thay đổi khác nhau

Tệp **`ReceiverMutationDemo.java`**:

```java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void add(int delta) {
        this.value += delta;
    }

    int value() {
        return value;
    }
}

public class ReceiverMutationDemo {
    static void addTo(Counter target, int delta) {
        target.add(delta);
    }

    public static void main(String[] args) {
        Counter left = new Counter(2);
        Counter right = new Counter(7);

        left.add(3);
        addTo(right, 4);

        System.out.println(left.value());
        System.out.println(right.value());
    }
}
```

```bash
javac ReceiverMutationDemo.java
java ReceiverMutationDemo
```

```text
5
11
```

`left.add(3)` sửa object `left` qua `this`; `addTo(right,4)` sửa object `right` qua tham số `target` rồi gọi instance method. Không có sự “lan truyền” từ object left sang right, vì hai biến không cùng trỏ một object.

## 6. “Đối tượng bên ngoài” thực ra là cùng một object được nhìn qua nhiều đường

Phương thức không có đặc quyền thay đổi mọi object nằm ngoài phạm vi của nó. Nó chỉ làm việc với những object mà mã của nó **có đường tham chiếu hợp lệ để truy cập** (qua tham số, receiver, field, static field, kết quả method, v.v.).

Ví dụ:

```java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Person {
    Address address;

    Person(Address address) {
        this.address = address;
    }
}
```

Các lớp là **khai báo minh họa**, không có `main`. Giả sử:

```java
Address shared = new Address("Hue");
Person an = new Person(shared);
Person binh = new Person(shared);
```

Đồ thị đối tượng:

```text
shared ────────────────────┐
                          |
an ──> Person A ─ address ┼──> Address X {city="Hue"}
                          |
binh -> Person B ─address─┘
```

Nếu method nhận `an` rồi thực hiện `an.address.city = "Da Nang";`, cả `shared.city` và `binh.address.city` sẽ thấy `"Da Nang"` vì tất cả dẫn tới **Address X**. Nếu method chỉ thực hiện `an.address = new Address("Ha Noi");`, field `address` của Person A được gán sang object khác; Person B vẫn trỏ Address X. Đây là **hai cấp tham chiếu**:

1. Local variable `an` trỏ Person A.
2. Field `an.address` trỏ Address X.
3. Phép gán `an.address = ...` **không gán lại local variable `an`**, nhưng **sửa state của Person A** bằng cách thay một field tham chiếu của nó.
4. Việc sửa `an.address.city` thay đổi **state của Address X**, nên mọi alias của X có thể quan sát.

**Vì vậy phải hỏi:** “Method đang gán lại **biến nào**?” và “Method đang thay đổi **object nào**?”. Chỉ biết một dòng có dấu `=` chưa đủ để kết luận caller có bị ảnh hưởng hay không.

## 7. Ví dụ nhiều object: đổi field tham chiếu cũng là sửa object của caller

Tạo tệp **`NestedReferenceMutationDemo.java`**:

```java
class Address {
    private String city;

    Address(String city) {
        this.city = city;
    }

    String city() {
        return city;
    }

    void moveTo(String city) {
        this.city = city;
    }
}

class Person {
    private Address address;

    Person(Address address) {
        this.address = address;
    }

    Address address() {
        return address;
    }

    void setAddress(Address address) {
        this.address = address;
    }
}

public class NestedReferenceMutationDemo {
    static void changeCity(Person person, String city) {
        person.address().moveTo(city);
    }

    static void replaceAddress(Person person, String city) {
        person.setAddress(new Address(city));
    }

    public static void main(String[] args) {
        Address shared = new Address("Hue");
        Person an = new Person(shared);
        Person binh = new Person(shared);

        changeCity(an, "Da Nang");
        System.out.println("A=" + an.address().city());
        System.out.println("B=" + binh.address().city());

        replaceAddress(an, "Ha Noi");
        System.out.println("A=" + an.address().city());
        System.out.println("B=" + binh.address().city());
        System.out.println("shared=" + shared.city());
    }
}
```

```bash
javac NestedReferenceMutationDemo.java
java NestedReferenceMutationDemo
```

**Output:**

```text
A=Da Nang
B=Da Nang
A=Ha Noi
B=Da Nang
shared=Da Nang
```

Giải thích:

- `changeCity(an, "Da Nang")` nhận bản sao tham chiếu tới **Person An**, gọi `person.address()` để lấy **Address chung**, rồi gọi `moveTo` trên Address chung. Bởi An và Binh đang trỏ cùng Address object, cả hai đọc thành phố mới.
- `replaceAddress(an, "Ha Noi")` cũng nhận bản sao tham chiếu tới Person An, nhưng gọi `person.setAddress(new Address(...))`. Việc này thay **field tham chiếu trong Person An**, không thay biến `an` ở caller.
- Person Binh vẫn trỏ tới Address ban đầu, nên B vẫn ở `Da Nang`; biến `shared` cũng vẫn trỏ Address ban đầu.

Điểm chính của bài không phải “mọi thao tác trong method đều thay đổi object bên ngoài”, mà là **method có thể thay đổi object reachable qua các tham chiếu được truyền vào hoặc có sẵn**, tùy thân method và quyền truy cập.

## 8. Gán lại tham số không thể thay biến tham chiếu của caller

Để cô lập ý này, xét:

```java
static void rebind(StringBuilder text) {
    text = new StringBuilder("new");
}
```

Khi caller có:

```java
StringBuilder original = new StringBuilder("old");
rebind(original);
System.out.println(original.toString());
```

Kết quả vẫn là `old`. Lệnh `text = new StringBuilder("new")` chỉ đổi **biến tham số `text`**, không đổi biến `original`.

Trong Java, không có cơ chế mặc định khiến tham số của method trở thành **bí danh của chính ô biến caller** để một phép gán như `text = ...` cập nhật biến caller. Vì thế câu “Java truyền tham chiếu vào phương thức” chỉ đúng nếu hiểu là **truyền giá trị tham chiếu theo giá trị**; gọi Java là *pass-by-reference* theo nghĩa của những ngôn ngữ cho phép callee gán lại biến caller sẽ gây hiểu sai.

### Caller muốn thay tham chiếu thì nhận giá trị trả về

Thiết kế rõ ràng hơn:

```java
static StringBuilder replacement() {
    return new StringBuilder("new");
}
```

Sau đó caller **tự gán**:

```java
StringBuilder original = new StringBuilder("old");
original = replacement();
System.out.println(original.toString()); // new
```

Đây là mảnh code ở trong method. Việc `original` thay sang object mới là **kết quả của phép gán `original = ...` tại caller**, không phải method lén sửa ô biến caller.

Tương tự, nếu muốn method tạo một `Account` thay thế, API có thể trả `Account` mới hoặc một kiểu kết quả chứa các thông tin cần thiết. Với API cập nhật object đang có, nên thể hiện rõ bằng tên method và hợp đồng, ví dụ `updateAddress(...)` hoặc `deposit(...)`.

## 9. Mảng là object: method sửa phần tử được, nhưng không thay biến mảng ở caller

Mảng Java là object, vì thế phương thức có thể thay **giá trị slot** của một mảng mà caller đang tham chiếu:

Tạo tệp **`ArrayArgumentMutationDemo.java`**:

```java
public class ArrayArgumentMutationDemo {
    static void modify(int[] numbers) {
        numbers[0] += 10;
        numbers[1] = 77;
        numbers = new int[] {999};
        System.out.println("inside length=" + numbers.length);
    }

    public static void main(String[] args) {
        int[] values = {1, 2};

        modify(values);

        System.out.println("outside length=" + values.length);
        System.out.println(values[0]);
        System.out.println(values[1]);
    }
}
```

```bash
javac ArrayArgumentMutationDemo.java
java ArrayArgumentMutationDemo
```

```text
inside length=1
outside length=2
11
77
```

Trong `modify`:

1. `numbers` là bản sao tham chiếu tới array object ban đầu.
2. `numbers[0] += 10` và `numbers[1] = 77` **ghi vào hai slot của mảng ban đầu**, nên caller đọc `11` và `77`.
3. `numbers = new int[]{999}` tạo mảng mới và chỉ đổi tham chiếu **trong biến tham số**.
4. `values` ở caller vẫn trỏ mảng ban đầu dài 2; `numbers` bên trong đang trỏ mảng mới dài 1 nên dòng `inside length=1` không mâu thuẫn với `outside length=2`.

Sơ đồ:

```text
Khi vừa vào modify:
values  ─────┐
             ├──> Array A: [1, 2]
numbers ─────┘

Sau hai lần sửa slot:
values  ─────┐
             ├──> Array A: [11, 77]
numbers ─────┘

Sau numbers = new int[]{999}:
values  ───────> Array A: [11, 77]
numbers ───────> Array B: [999]
```

**Lưu ý:** Trong mảng `int[]`, các phần tử là **giá trị primitive**, nhưng chính **mảng** vẫn là object. Do đó `numbers[0]` thay đổi là sửa state array object; không phải Java tự chuyển `int` thành pass-by-reference.

## 10. Mảng đối tượng: sửa object phần tử và thay tham chiếu trong slot

Đối với `Student[]`, có thể có **hai cấp mutation** khác nhau:

- `students[0].rename("Lan");` sửa **object Student** mà slot 0 đang tham chiếu.
- `students[0] = new Student("Lan");` sửa **slot 0 của array object** để trỏ một Student object mới.

Tạo tệp **`ObjectArrayMutationDemo.java`**:

```java
class Student {
    private String name;

    Student(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

public class ObjectArrayMutationDemo {
    static void mutate(Student[] people) {
        people[0].rename("First");
        people[1] = new Student("Second");
    }

    public static void main(String[] args) {
        Student shared = new Student("Original");
        Student[] students = {shared, shared};

        mutate(students);

        System.out.println(shared.name());
        System.out.println(students[0].name());
        System.out.println(students[1].name());
        System.out.println(students[0] == students[1]);
    }
}
```

```bash
javac ObjectArrayMutationDemo.java
java ObjectArrayMutationDemo
```

```text
First
First
Second
false
```

**Giải thích:** Ban đầu cả hai slot trỏ cùng Student `shared`. `people[0].rename("First")` sửa chính Student đó; caller quan sát `shared.name()` thành `First`. `people[1] = new Student("Second")` chỉ đổi **tham chiếu ở slot 1**; slot 0 vẫn giữ object đầu, nên hai phần tử không còn cùng trỏ một Student object.

Không nhầm `Student[] people` với `Student people`. Với tham số mảng, ngoài biến tham số còn có **mảng chung và các object phần tử** mà method có thể tiếp cận.

## 11. Collections: thêm, xóa, sửa phần tử cũng là mutation của object chung

Các lớp như `ArrayList`, `HashMap` và `HashSet` là những object có thể thay đổi được. Khi truyền một `List` hoặc `Map` mutable vào method, hai bên có thể dùng các tham chiếu khác nhau tới **cùng collection object**.

Ví dụ Java 17+ độc lập, tệp **`ListMutationDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ListMutationDemo {
    static void update(List<String> items) {
        items.add("Java");
        items.set(0, "Core");

        items = new ArrayList<>();
        items.add("Local");
        System.out.println("inside=" + items);
    }

    public static void main(String[] args) {
        List<String> topics = new ArrayList<>();
        topics.add("Basics");

        update(topics);

        System.out.println("outside=" + topics);
    }
}
```

```bash
javac ListMutationDemo.java
java ListMutationDemo
```

```text
inside=[Local]
outside=[Core, Java]
```

Trước phép gán lại tham số, `items` và `topics` trỏ cùng `ArrayList` nên `add` và `set` sửa danh sách mà caller giữ. Sau `items = new ArrayList<>()`, tham số trỏ list mới và `add("Local")` chỉ tác động list mới ấy. Vì vậy caller vẫn thấy `[Core, Java]`.

**Không phải mọi `List` đều có thể sửa:** `List.of("A", "B")` trả danh sách **unmodifiable**; gọi `add`/`set` có thể ném `UnsupportedOperationException`. Cơ chế pass-by-value **không quyết định object có mutable hay không** — điều đó do triển khai/hợp đồng của object.

### Collection chứa mutable elements: hai tầng chia sẻ

Nếu `List<Person>` chứa những Person objects có thể sửa, thì:

- `list.add(person)` thay đổi **cấu trúc collection**.
- `list.get(0).rename(...)` thay đổi **Person object** được collection trỏ tới.
- `list = new ArrayList<>()` trong method chỉ thay **tham số local**, không thay biến caller.
- `list.set(0, new Person(...))` thay **reference ở vị trí 0 của collection**.

Một bản copy nông `new ArrayList<>(existing)` tạo **collection khác** nhưng thường **giữ cùng các tham chiếu element**. Muốn cô lập cả mutable element objects, phải copy elements theo chính sách dữ liệu phù hợp.

## 12. Mutable và immutable: có tham chiếu chung chưa chắc có state để sửa

Một object **mutable** cho phép trạng thái quan sát được thay đổi qua API hoặc quyền truy cập hợp lệ, ví dụ `StringBuilder`, `ArrayList`, một lớp `Account` có setter/deposit hoặc một mảng.

Ngược lại, object **immutable** không cho thay đổi trạng thái đã được định nghĩa bởi hợp đồng của nó sau khi khởi tạo. Ví dụ `String` bất biến. Vì vậy có khác biệt giữa:

```java
String text = "cat";
text = text + "!";
```

và:

```java
StringBuilder builder = new StringBuilder("cat");
builder.append("!");
```

Với `String`, biểu thức nối tạo một **giá trị String mới** theo ngữ nghĩa, rồi biến `text` được gán sang giá trị đó. Nó không thay nội dung String object `"cat"` cũ. Với `StringBuilder`, `append` thay đổi nội dung của **chính builder object**.

### Chương trình so sánh kết quả qua tham số

Tệp **`ImmutableVsMutableDemo.java`**:

```java
public class ImmutableVsMutableDemo {
    static void appendToString(String text) {
        text = text + "!";
        System.out.println("string inside=" + text);
    }

    static void appendToBuilder(StringBuilder builder) {
        builder.append("!");
        System.out.println("builder inside=" + builder);
    }

    public static void main(String[] args) {
        String word = "cat";
        StringBuilder buffer = new StringBuilder("cat");

        appendToString(word);
        appendToBuilder(buffer);

        System.out.println("string outside=" + word);
        System.out.println("builder outside=" + buffer);
    }
}
```

```bash
javac ImmutableVsMutableDemo.java
java ImmutableVsMutableDemo
```

```text
string inside=cat!
builder inside=cat!
string outside=cat
builder outside=cat!
```

**Vì sao khác?**

- `appendToString` chỉ gán lại **tham số `text`** bằng một String kết quả mới; caller `word` vẫn trỏ String cũ.
- `appendToBuilder` gọi method **mutate** trên builder chung; caller `buffer` đọc trạng thái mới của chính object đó.
- Cả hai lời gọi vẫn áp dụng **pass-by-value** như nhau. Khác biệt nằm ở **hành vi của loại object và method**.

### Wrapper types và record cũng cần hiểu đúng

`Integer`, `Long`, `Boolean` và những wrapper thông dụng là immutable. Khi viết `Integer x = 10; x++;`, phép tăng liên quan unboxing/boxing và **gán lại biến** `x`; không phải sửa field trong Integer object cũ.

Một `record` có các component fields `final` theo quy tắc record, nhưng nếu component chứa **tham chiếu tới object mutable** thì record vẫn có thể **bộc lộ sự thay đổi gián tiếp** nếu không defensive copy. Ví dụ record chứa `List<String>` có thể nhìn thấy list thay đổi nếu chính list được chia sẻ. Không đánh đồng “biến reference không gán lại” với “toàn bộ đồ thị đối tượng bất biến”.

## 13. `final` giới hạn gán lại biến; không tự chặn mutation

Từ khóa `final` có hai tình huống cần phân biệt:

**Biến tham chiếu `final` ở caller:**

```java
final StringBuilder builder = new StringBuilder("A");

builder.append("B"); // Hợp lệ: sửa object.
// builder = new StringBuilder("C"); // Không hợp lệ: gán lại biến final.
```

**Tham số `final` trong method:**

```java
static void update(final StringBuilder target) {
    target.append("!");
    // target = new StringBuilder("other"); // Lỗi: tham số final không được gán lại.
}
```

`final` chỉ cấm **gán lại biến tham chiếu** (`builder` hoặc `target`). Nó không tự đóng băng object `StringBuilder`, nên `append` vẫn hoạt động.

Nếu muốn method không mutate đối số, `final` trên tham số **không phải** công cụ đủ để bảo đảm. Cần API chỉ đọc, kiểu immutable, defensive copy, contract rõ ràng hoặc cơ chế kiểm soát khác phù hợp.

**Ghi nhớ:** Một method hoàn toàn có thể sửa state của object mà caller giữ qua **tham số `final`**; pass-by-value vẫn giữ nguyên.

## 14. Phân biệt mutation trực tiếp, mutation gián tiếp và tạo kết quả mới

Không phải mọi tác động quan sát được đều đến từ câu lệnh `field = value` trong method hiện tại.

**Mutation trực tiếp:**

```java
static void increase(Box box) {
    box.count++;
}
```

**Mutation qua method khác:**

```java
static void increase(Counter counter) {
    counter.increment();
}
```

**Mutation gián tiếp qua object con:**

```java
static void move(Person person) {
    person.address().moveTo("Hue");
}
```

**Không mutate đầu vào mà trả object mới:**

```java
static String appendMark(String text) {
    return text + "!";
}
```

Các đoạn trên là **mảnh method minh họa** và giả định các lớp `Box`, `Counter`, `Person` đã được khai báo cùng những thành phần phù hợp. Cần xem **implementation được gọi bên trong** mới biết trạng thái nào thay đổi.

Một method có thể trông như “chỉ gọi getter” nhưng getter có side effect nếu implementation được viết như vậy; tương tự một method có tên `update` không bảo đảm nó mutate tham số — nó có thể trả object mới. **Đọc contract và implementation**, không suy từ tên.

### “Thay đổi bên ngoài” không có nghĩa caller quan sát ngay trong mọi hoàn cảnh

Trong một luồng đơn, nếu hai tham chiếu cùng trỏ một mutable object và method cập nhật nó thành công, những lần đọc sau trên cùng object có thể quan sát giá trị mới. Nhưng điều kiện còn gồm:

- Method **thực sự thực hiện mutation** và không rollback/đổi lại trước khi caller quan sát.
- Caller giữ một đường tham chiếu tới object bị sửa, **không phải** object khác.
- Caller đọc đúng field/state có liên quan, có thể qua getter hoặc API thể hiện trạng thái.
- Với nhiều thread, việc **nhìn thấy** thay đổi qua thread khác còn cần các quan hệ đồng bộ/visibility thích hợp theo Java Memory Model.

Phần pass-by-value không tự giải quyết các quy tắc concurrency.

## 15. Return value, hợp đồng API và hai kiểu thiết kế

Hai kiểu API thường gặp:

### A. Mutating API — thay đổi object được truyền vào

```java
class Score {
    private int value;

    Score(int value) {
        this.value = value;
    }

    void add(int amount) {
        value += amount;
    }

    int value() {
        return value;
    }
}
```

Cách dùng:

```java
Score score = new Score(10);
score.add(5);
System.out.println(score.value()); // 15
```

Caller vẫn giữ **cùng Score object** và đọc state mới. Điều này phù hợp khi object đại diện một thực thể có identity và vòng đời trạng thái rõ ràng.

### B. Non-mutating API — tạo hoặc trả giá trị mới

```java
record ScoreValue(int value) {
    ScoreValue added(int amount) {
        return new ScoreValue(value + amount);
    }
}
```

Cách dùng:

```java
ScoreValue original = new ScoreValue(10);
ScoreValue changed = original.added(5);

System.out.println(original.value()); // 10
System.out.println(changed.value());  // 15
```

`ScoreValue` là Java record (hỗ trợ Java 17+). Phương thức `added` trả **record instance mới**; không thay state của record cũ. Cách này làm luồng dữ liệu rõ hơn và giảm rủi ro side effect, nhưng cần cân nhắc chi phí/tính phù hợp của việc tạo giá trị mới.

Cả A và B đều dùng **truyền tham trị**. Không có mối quan hệ “method mutate thì Java chuyển sang pass-by-reference”. Sự khác biệt là **quy ước thiết kế và implementation**.

## 16. Encapsulation: method có thể sửa object không đồng nghĩa nên cho sửa mọi field

Việc truyền tham chiếu tạo khả năng tiếp cận object, nhưng **quyền truy cập thành viên Java** vẫn được compiler kiểm tra. Một method trong lớp khác không thể trực tiếp ghi `private` field chỉ vì nó nhận được tham chiếu object.

```java
class BankAccount {
    private int balance;

    BankAccount(int balance) {
        this.balance = balance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("positive amount required");
        }
        balance += amount;
    }

    int balance() {
        return balance;
    }
}
```

Một method bên ngoài lớp có thể gọi `account.deposit(10)` khi method truy cập được, nhưng không được viết `account.balance = -100;` từ lớp không có quyền truy cập field. Đây là **encapsulation**: cho phép thay đổi state theo các quy tắc đảm bảo invariant.

Vì object có thể được nhiều alias giữ, mọi mutation cần bảo đảm **bất biến nghiệp vụ của object**. Nếu cho một phương thức tùy ý gán field không kiểm tra, nhiều nơi trong chương trình có thể đọc một object ở trạng thái sai.

Một thiết kế API rõ ràng nên cho biết method:

- Có mutate receiver/đối số hay không.
- Trạng thái nào bị thay đổi, có validation gì.
- Kết quả trả về biểu thị object cũ, object mới hay giá trị tính toán.
- Có giữ lại tham chiếu tới đầu vào để dùng sau hay không.
- Có giới hạn concurrency/ownership hay không.

## 17. Defensive copy để tránh người gọi thay đổi state nội bộ

Nếu lớp nhận một mutable object từ caller rồi lưu trực tiếp tham chiếu, caller có thể vẫn giữ alias tới dữ liệu nội bộ. Điều đó tạo nguy cơ **representation exposure**.

Ví dụ dễ lỗi:

```java
import java.util.List;

class UnsafeTeam {
    private final List<String> members;

    UnsafeTeam(List<String> members) {
        this.members = members;
    }

    List<String> members() {
        return members;
    }
}
```

Đây là khai báo hợp lệ nhưng có rủi ro thiết kế. Nếu caller tạo một `ArrayList`, đưa vào `new UnsafeTeam(list)`, sau đó `list.add("New")`, field `members` của team đang giữ **cùng list object** nên quan sát thay đổi. Getter cũng trả thẳng tham chiếu list nội bộ, cho phép caller sửa gián tiếp.

### Ví dụ chạy có bản sao phòng vệ

Tạo tệp **`DefensiveCopyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Team {
    private final List<String> members;

    Team(List<String> source) {
        this.members = new ArrayList<>(source);
    }

    List<String> members() {
        return List.copyOf(members);
    }

    void add(String member) {
        members.add(member);
    }
}

public class DefensiveCopyDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Team team = new Team(input);

        input.add("Binh");
        System.out.println("input=" + input);
        System.out.println("team=" + team.members());

        team.add("Chi");
        System.out.println("team=" + team.members());
        System.out.println("input=" + input);
    }
}
```

```bash
javac DefensiveCopyDemo.java
java DefensiveCopyDemo
```

```text
input=[An, Binh]
team=[An]
team=[An, Chi]
input=[An, Binh]
```

**Cơ chế:**

1. Constructor `Team(List<String> source)` nhận **bản sao tham chiếu** đến input list, nhưng tạo **ArrayList mới** để lưu trong field `members`. Vì thế caller sửa `input` không tự thay danh sách nội bộ.
2. Getter `members()` trả `List.copyOf(members)`, một bản danh sách unmodifiable mới theo hợp đồng, thay vì trao trực tiếp mutable list nội bộ cho caller.
3. `team.add("Chi")` mutate list **nội bộ Team**, không mutate list input của caller. Vì vậy sau cùng Team có `[An, Chi]`, input có `[An, Binh]`.

**Giới hạn:** `new ArrayList<>(source)` và `List.copyOf(...)` là bản sao **nông về các phần tử tham chiếu**. Trong ví dụ `String` là immutable nên đủ hữu ích. Nếu list chứa mutable `Person` objects, cần quyết định có copy từng element không; chỉ tạo list khác vẫn có thể để hai list cùng trỏ các Person objects.

## 18. Chủ quyền đối tượng (*ownership*) và aliasing trong thiết kế lớn

Java không cung cấp một “chủ sở hữu duy nhất” mặc định cho mọi mutable object. Một mutable object có thể được nhiều method, field hoặc thread khác nhau giữ tham chiếu. Vì vậy cần có **quy ước ownership** ở cấp thiết kế.

Một số lựa chọn thực tế:

1. **Cho phép mutation có kiểm soát:** Object có identity rõ ràng như tài khoản hoặc đơn hàng; các method `deposit`, `approve` kiểm tra điều kiện trước khi sửa.
2. **Không chia sẻ mutable state:** Mỗi thành phần tạo bản copy riêng, hoặc trả immutable value khi có thể.
3. **Không phơi bày collection mutable nội bộ:** Trả unmodifiable view/copy hoặc các method truy vấn thay vì trả trực tiếp object gốc.
4. **Có hợp đồng rõ về input mutation:** Nếu API ghi “sorts the supplied list in place”, caller biết list sẽ bị thay đổi; nếu API ghi “returns a sorted copy”, caller không nên thấy input bị sửa.
5. **Tránh aliasing không chủ ý:** Khi gán `a = b` hoặc dùng `Arrays.fill` với một mutable object, cân nhắc các biến/slot có đang chia sẻ object hay không.

Các quy ước này không thay đổi quy tắc pass-by-value của Java; chúng quyết định **ai được phép mutate object khi có tham chiếu tới nó**.

### `Collections.unmodifiableList` và bản copy khác nhau ở đâu?

Một **unmodifiable view** có thể ngăn mutation qua view nhưng vẫn **phản ánh thay đổi của collection nền** do nơi khác thực hiện. Ngược lại, tạo **snapshot/copy** ở thời điểm cụ thể có thể tách collection structure khỏi thay đổi sau đó của nguồn; tuy nhiên element objects mutable vẫn có thể chia sẻ.

Vì vậy khi muốn “method không để caller thay state nội bộ”, cần cân nhắc **copy hay view**, và liệu elements có immutable hay không. Không chỉ đổi kiểu khai báo `List` là đủ bảo vệ state.

## 19. `null`, exception và mutation dở dang

Một tham số reference có thể mang giá trị `null`. Khi method viết `target.deposit(5)`, nếu `target == null`, gọi instance method không có receiver object và thường ném `NullPointerException`. Không có object nào để mutate qua tham số null đó.

```java
static void deposit(Account account, int amount) {
    if (account == null) {
        throw new IllegalArgumentException("account is required");
    }
    account.deposit(amount);
}
```

Đây là mảnh method dùng lớp `Account` thích hợp. Kiểm tra null giúp lỗi dễ hiểu và cho API hợp đồng rõ ràng. Trong code thật có thể dùng `Objects.requireNonNull(account, "account")` nếu phù hợp.

### Exception không tự hoàn tác những mutation đã xảy ra

Xét một method:

```java
static void updateTwo(int[] data) {
    data[0] = 10;
    throw new IllegalStateException("failed later");
}
```

Nếu caller truyền mảng hợp lệ và bắt ngoại lệ, `data[0]` của mảng chung **vẫn là 10**, trừ khi có logic rollback rõ ràng. Java không cung cấp tính nguyên tử giao dịch cho nhiều phép mutation chỉ vì các phép ấy nằm trong cùng method.

Do đó, nếu một method cập nhật nhiều trạng thái liên quan, cần xem việc validation trước khi sửa, xử lý thất bại, hoặc cơ chế transaction/rollback thích hợp. Pass-by-value **không bảo vệ caller khỏi side effect** do method đã thực hiện trước khi thất bại.

## 20. Concurrency: chia sẻ mutable object cần quy tắc đồng bộ riêng

Các ví dụ trước giả định quan sát theo **một luồng thực thi**. Khi nhiều thread cùng giữ tham chiếu tới một mutable object và đọc/ghi state, có thể phát sinh **data race**, lost update hoặc visibility issue nếu không đồng bộ đúng theo Java Memory Model.

```java
class Counter {
    private int count;

    void increment() {
        count++;
    }
}
```

Hai thread cùng gọi `increment()` trên **cùng Counter object** không bảo đảm tổng tăng chính xác nếu không có đồng bộ phù hợp; `count++` không phải một cập nhật nguyên tử ở mức yêu cầu đồng thời của ví dụ.

Có thể dùng synchronized methods, lock phù hợp hoặc atomic types tùy bài toán:

```java
class SafeCounter {
    private int count;

    synchronized void increment() {
        count++;
    }

    synchronized int get() {
        return count;
    }
}
```

Ở đây cả `increment()` và `get()` khóa **monitor của cùng receiver** khi được gọi trên một object. Những đường đọc/ghi khác cũng phải tuân thủ cùng giao thức; `synchronized` không tự bảo vệ nếu mã khác truy cập state không qua khóa thích hợp.

**Tóm lại:** method có thể sửa object caller vì hai bên tham chiếu chung object; việc thay đổi ấy **có được nhìn thấy đúng lúc giữa các thread hay không** còn cần cơ chế concurrency. Không được diễn giải pass-by-value như một đảm bảo thread safety.

## 21. Các lỗi suy luận thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Java truyền object theo reference, nên method đổi được biến caller” | Java sao chép **giá trị tham chiếu**; method mutate object được, nhưng không gán lại biến caller qua tham số |
| “`p = new Person(...)` trong method làm caller đổi object” | Chỉ gán lại tham số `p`; caller muốn đổi thì phải tự nhận kết quả và gán |
| “Gọi setter trên tham số giống gán lại tham số” | Setter thường sửa **state của object**; gán lại tham số đổi **giá trị biến tham số** |
| “Object ở ngoài method thì method không thể sửa” | Nếu có tham chiếu và quyền truy cập phù hợp, method có thể mutate object đó |
| “Pass-by-value nghĩa mọi object được copy” | Chỉ **giá trị tham chiếu** được copy, không tự sao chép object |
| “Hai biến alias nên gán lại một biến làm biến kia đổi theo” | Aliasing của object không phải liên kết giữa hai ô biến; gán lại một biến chỉ đổi biến đó |
| “`final Account account` làm Account immutable” | Cấm gán lại biến `account`; object có thể vẫn mutable |
| “`String` không đổi vì Java dùng kiểu truyền khác” | Vẫn pass-by-value; `String` là immutable, phép nối cho giá trị mới và gán lại biến |
| “Tham số `int[]` truyền theo reference đặc biệt” | Mảng là object; tham số nhận bản sao tham chiếu; sửa slot ảnh hưởng mảng chung |
| “Đổi `items = new ArrayList<>()` trong method xóa danh sách caller” | Chỉ gán lại tham số local, không xóa object list ban đầu |
| “`List.copyOf` làm mọi object phần tử immutable” | Bản danh sách là unmodifiable; các element objects mutable có thể vẫn được chia sẻ |
| “Method mutate rồi throw exception thì mọi state tự rollback” | Không có rollback mặc định; mutation đã xảy ra có thể còn |
| “Một static method không có `this` nên không sửa được object” | Static method vẫn sửa object qua tham số, field, hoặc tham chiếu hợp lệ |
| “Hai object `equals` nhau thì sửa một object sẽ sửa object kia” | `equals` phụ thuộc nội dung/hợp đồng; chỉ alias tới **cùng identity** mới chia sẻ state của chính object ấy |
| “Có cùng object giữa hai thread thì lúc nào cũng thấy giá trị mới ngay” | Visibility/concurrency cần đồng bộ phù hợp; pass-by-value không giải quyết data race |

### Lỗi đặc biệt: hiểu sai từ “tham chiếu”

Nói “method nhận một tham chiếu” không sai nếu bạn có ý nói method nhận **giá trị tham chiếu tới object**. Nhưng trong lập luận về truyền tham số, cần tránh câu “Java truyền **theo tham chiếu**” nếu nó khiến người nghe hiểu **tham số là tên khác của biến caller**.

Phân biệt bằng câu hỏi kiểm chứng:

- Nếu method viết `parameter.field = x` và quyền truy cập hợp lệ, caller có thể thấy state của object đổi không? **Có**, nếu cùng object.
- Nếu method viết `parameter = new Type(...)`, biến caller có tự đổi tham chiếu không? **Không**.
- Nếu method `return` object mới và caller viết `caller = method(caller)`, biến caller có đổi không? **Có**, vì **caller gán lại**.
- Nếu method nhận primitive `int x` và viết `x++`, biến primitive caller có đổi không? **Không**.

Bốn câu trên đủ để phân biệt hai cơ chế mà phần lớn người học nhầm.

## 22. Bài thực hành tổng hợp: tự dự đoán và vẽ mũi tên

Tạo tệp **`ReferenceMutationTraceDemo.java`**:

```java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class ReferenceMutationTraceDemo {
    static void change(Box first, Box second) {
        first.value += 5;
        second = new Box(20);
        second.value += 2;

        System.out.println("inside first=" + first.value);
        System.out.println("inside second=" + second.value);
    }

    public static void main(String[] args) {
        Box left = new Box(1);
        Box right = left;

        change(left, right);

        System.out.println("left=" + left.value);
        System.out.println("right=" + right.value);
        System.out.println("same=" + (left == right));
    }
}
```

```bash
javac ReferenceMutationTraceDemo.java
java ReferenceMutationTraceDemo
```

**Đáp án:**

```text
inside first=6
inside second=22
left=6
right=6
same=true
```

**Truy vết:**

```text
Bước 1: trước gọi change
left ───┐
        ├──> Box A {value=1}
right ──┘

Bước 2: vừa vào change
left ───┐
right ──┤
first ──┤──> Box A {value=1}
second ─┘

Bước 3: first.value += 5
left ───┐
right ──┤
first ──┤──> Box A {value=6}
second ─┘

Bước 4: second = new Box(20); second.value += 2
left ───┐
right ──┤──> Box A {value=6}
first ──┘

second ─────> Box B {value=22}

Bước 5: return
left ───┐
        ├──> Box A {value=6}
right ──┘

Hai biến tham số first, second hết scope.
```

Có **hai Box objects** được tạo trong chương trình: A ở caller và B bên trong method. Đoạn code chỉ tạo B một lần, không “nhân đôi A” khi truyền nó cho cả `first` và `second`. Sau khi return, caller vẫn giữ object A qua hai biến `left` và `right`.

### Tự biến đổi bài tập

1. Nếu thay `second = new Box(20)` bằng `second.value = 20`, caller in gì? **Cả `left` và `right` sẽ đọc object A có `value=20` rồi `second.value+=2` thành 22**, nên hai dòng ngoài cùng in 22.
2. Nếu caller tạo `Box right = new Box(10)` thay vì `right = left`, `first.value+=5` sẽ sửa Box A, còn `second = new Box(20)` chỉ đổi tham số trong method. Sau return, `left.value=6` và `right.value=10`.
3. Nếu method thay `second = new Box(20)` rồi `return second;`, và caller viết `right = change(left,right);` với kiểu trả về được sửa phù hợp, caller **chủ động gán** tham chiếu object B vào `right`; khi ấy `left` vẫn trỏ A, `right` trỏ B.
4. Nếu `Box` là một immutable value type không cung cấp phép sửa `value`, method không thể trực tiếp `first.value+=5` bằng API thông thường. Nó sẽ cần tạo giá trị mới/trả kết quả, và caller quyết định có gán lại hay không.

Các biến thể 1–4 là **bài suy luận**, không phải bốn chương trình biên dịch độc lập nguyên văn với tệp mẫu.

## 23. Checklist khi một method “làm thay đổi dữ liệu ngoài ý muốn”

Khi đọc hoặc debug Java code có tham số là object, thực hiện lần lượt:

1. **Xác định object thực tế** mà biến caller đang trỏ tới trước khi gọi; phân biệt kiểu tĩnh của biến và runtime object.
2. **Vẽ tham số** như một biến riêng ở method, nhận **bản sao tham chiếu**; không đồng nhất tham số với biến caller.
3. **Đánh dấu mọi alias**: các biến, field, array slots hoặc collection entries khác cùng giữ tham chiếu tới object.
4. **Phân loại từng phép gán:** `parameter = new ...` là gán lại tham số; `parameter.field = ...` là sửa object; `parameter.array[i] = ...` là sửa array object reachable.
5. **Theo dõi lời gọi gián tiếp:** `parameter.deposit(...)` hoặc `parameter.getAddress().moveTo(...)` có thể mutate object ở nhiều cấp.
6. **Kiểm tra mutable/immutable contract** của object được gọi; `String` khác `StringBuilder`, `List.of` khác `ArrayList`.
7. **Xác định object nào caller vẫn giữ sau khi return**; caller không tự đổi tham chiếu vì method đã gán lại tham số.
8. **Kiểm tra return value:** nếu method trả object mới, caller có gán kết quả vào biến hay không?
9. **Kiểm tra copy nông hay copy sâu:** copy collection không tự copy mọi mutable element.
10. **Xem xét quyền truy cập và invariants:** method có được phép mutate field hay nên thông qua API kiểm tra hợp lệ?
11. **Xem xét exception:** có mutation nào xảy ra trước khi throw? Có rollback/transaction không?
12. **Nếu nhiều thread:** có data race và thiếu synchronization không? Không giả định visibility chỉ vì cùng giữ tham chiếu.

---

**Ghi nhớ:** Java **luôn truyền tham trị**. Với đối số kiểu tham chiếu, method nhận **bản sao giá trị tham chiếu**, vì thế caller và method có thể cùng trỏ **một mutable object**. Sửa **state của object chung** qua method/field/array slot có thể được caller quan sát; nhưng **gán lại tham số** sang object khác **không** gán lại biến caller. Muốn kiểm soát side effect, hãy phân biệt **biến tham chiếu**, **đối tượng**, **mutability**, **aliasing** và **hợp đồng API**.