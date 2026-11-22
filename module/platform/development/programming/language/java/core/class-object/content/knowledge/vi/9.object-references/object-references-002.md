# Sơ đồ tham chiếu khi khai báo, gán và tạo đối tượng trong Java

## 1. Dùng sơ đồ để theo dõi object graph, không chỉ học định nghĩa

Mục tiêu riêng của bài này là **vẽ lại các mũi tên sau từng câu lệnh**. Hãy xem variables, fields và array slots là những vị trí có thể chứa reference; đối tượng nằm ở phần còn lại của sơ đồ. Chỉ vẽ thêm object nếu có thao tác tạo object thành công, không vẽ thêm chỉ vì có phép gán.

~~~java
Student first = new Student("Lan");
Student second = first;
~~~

Đây là snippet giả sử class Student có constructor nhận String.

~~~text
Vị trí chứa reference          Object
first  ----------------┐
                       +----> Student A {name="Lan"}
second ----------------┘
~~~

Quy trình truy vết:

1. Đánh dấu thời điểm `new` chạy để thêm object.
2. Tìm biến hoặc slot nhận reference mới và vẽ lại **mũi tên**.
3. Khi gặp `alias.field = ...`, cập nhật **object**; khi gặp `alias = ...`, cập nhật **biến reference**.
4. Dự đoán `==`, null và output từ trạng thái sơ đồ ở đúng thời điểm.

Mũi tên là mô hình ngữ nghĩa, **không phải địa chỉ RAM thật**. Các mục kế tiếp dùng cùng phương pháp cho chuỗi gán, methods, mảng và vòng đời object.

## 2. Ba thao tác dễ bị nhầm: khai báo, gán, tạo đối tượng

Bảng dưới đây tách từng thao tác và kết quả:

| Mã | Thao tác | Có tạo `Student` mới không? | Kết quả |
| --- | --- | --- | --- |
| `Student s;` | Khai báo biến cục bộ | Không | `s` tồn tại trong scope nhưng chưa được gán chắc chắn |
| `Student s = null;` | Khai báo và gán `null` | Không | `s` không trỏ tới object nào |
| `s = new Student("A");` | Tạo object và gán tham chiếu | Có | `s` trỏ đến object vừa tạo |
| `Student t = s;` | Sao chép giá trị tham chiếu | Không | `t` và `s` cùng trỏ object |
| `t = new Student("B");` | Tạo object mới và gán lại `t` | Có | `t` trỏ object B; `s` vẫn trỏ object A |
| `s = t;` | Gán lại tham chiếu | Không | `s` và `t` cùng trỏ object B |
| `t = null;` | Bỏ tham chiếu trong `t` | Không | Chỉ `t` thành `null`; object B chưa chắc không còn tham chiếu khác |

**Đặc biệt:** `Student s;` chỉ đơn thuần khai báo một **biến cục bộ** chưa gán. Không được đọc `s` trước khi Java chứng minh *definite assignment*. Trong một method:

```java
Student s;
// System.out.println(s); // Nếu bỏ comment: lỗi biên dịch.
s = new Student("Lan");
System.out.println(s != null); // true
```

Đây là **mảnh mã minh họa** giả định `Student` được định nghĩa và có constructor `Student(String)`; muốn chạy cần đặt vào chương trình hợp lệ. Khác với local variable, **instance field** hoặc **static field** có kiểu tham chiếu được Java cấp giá trị mặc định `null` khi khởi tạo theo quy tắc.

## 3. Sơ đồ 1 — Chỉ khai báo biến chưa tạo object

Xét trong một method:

```java
Person p;
```

Ở thời điểm này:

```text
Scope của method
┌───────────────────┐
│ p : Person        │
│ chưa definite     │
│ assigned          │
└───────────────────┘

Không có Person object nào được tạo bởi câu khai báo này.
```

Không nên vẽ ngay `p ──> Person { ... }` vì **chưa có lệnh tạo instance**. Cũng không nên vẽ `p ──> null` đối với **local variable chưa khởi tạo**, vì `p` chưa có giá trị hợp lệ để đọc. Java dùng kiểm tra definite assignment để chặn việc đọc trước khi biến được gán.

Nếu viết:

```java
Person p = null;
```

thì sơ đồ khác:

```text
p : Person
  |
  +----> null (không có Person object)
```

`null` là giá trị tham chiếu đặc biệt thể hiện **không trỏ đến object nào**. Nó không phải một `Person` rỗng, cũng không phải object có field mặc định.

### Phân biệt field mặc định với local variable

```java
class Holder {
    Person current;            // Instance field: mặc định null.
    static Person selected;    // Static field: mặc định null.
}
```

Với một `Holder` vừa được tạo, `current` ban đầu là `null` nếu chưa có initializer/constructor gán khác; `Holder.selected` cũng có giá trị mặc định `null` trước các bước khởi tạo tĩnh tường minh. Tuy nhiên, local `Person p;` phải được gán trước khi đọc. Đây là ba tình huống có **quy tắc khởi tạo khác nhau**, dù cùng khai báo kiểu `Person`.

## 4. Sơ đồ 2 — `new` tạo object và trả về tham chiếu

Khi viết:

```java
Person p = new Person("Mai");
```

hãy hình dung hai sự kiện:

1. Biểu thức `new Person("Mai")` tạo một instance `Person` mới theo quy tắc class instance creation, bao gồm cấp phát, các bước khởi tạo và lời gọi constructor thích hợp.
2. Kết quả của biểu thức `new` là **một tham chiếu tới instance mới**, được gán cho biến `p`.

```text
Sau khi new Person("Mai") hoàn tất:

Biến p                                 Đối tượng A
┌───────────────────┐                  ┌──────────────────┐
│ p : Person  ──────┼─────────────────>│ Person           │
└───────────────────┘                  │ name = "Mai"     │
                                     └──────────────────┘
```

Một **constructor** không phải method trả về `Person`. Bản thân biểu thức `new Person(...)` tạo ra giá trị tham chiếu có thể được gán; constructor được gọi trong tiến trình xây dựng object và không có kiểu trả về.

Trong code Java, tên biến `p` không được nhúng làm thuộc tính danh tính của object. Sau khi đổi tên biến hoặc gán object cho một biến khác, **object vẫn là chính object đó**.

### `new` khác khai báo field và khai báo lớp

```java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }
}
```

Việc định nghĩa lớp `Person` hoặc field `name` không tự tạo một đối tượng `Person` cho mỗi dòng khai báo trong mã nguồn. Instance chỉ xuất hiện khi có hoạt động tạo instance thích hợp, chẳng hạn `new Person("Mai")`. Một class có thể chưa có instance nào trong quá trình chạy.

## 5. Sơ đồ 3 — Phép gán giữa hai biến tham chiếu tạo alias

Giả sử:

```java
Person first = new Person("Mai");
Person alias = first;
```

Sau hai lệnh:

```text
first ──────────┐
                ├──────> [Person A: name="Mai"]
alias ──────────┘
```

`alias` là một biến mới, **không phải một bản sao mới của `Person A`**. Hai biến cùng giữ tham chiếu đến object A; mối quan hệ ấy thường gọi là **aliasing**.

Nếu thực thi `alias.setName("Lan")` với instance method cập nhật field, cả `first.getName()` và `alias.getName()` đều thấy `"Lan"` vì chúng đang truy cập **cùng object**. Phép cập nhật qua tham chiếu không có nghĩa Java tự đồng bộ hai biến theo tên; hai biến chỉ đang trỏ đến cùng nơi chứa trạng thái object.

### Ví dụ chạy độc lập: aliasing thay đổi trạng thái chung

Tạo tệp **`AliasDemo.java`**:

```java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

public class AliasDemo {
    public static void main(String[] args) {
        Person first = new Person("Mai");
        Person second = first;

        second.rename("Lan");

        System.out.println(first.name());
        System.out.println(second.name());
        System.out.println(first == second);
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac AliasDemo.java
java AliasDemo
```

Kết quả chuẩn:

```text
Lan
Lan
true
```

Phương thức `rename` nhận object được gọi làm `this`. `second.rename("Lan")` sửa object mà `second` trỏ tới, cũng chính là object của `first`. Toán tử `==` trên hai tham chiếu object trả `true` khi chúng cùng trỏ tới đúng một object.

## 6. Sơ đồ 4 — Gán lại một biến không làm biến alias kia đổi theo

Tiếp tục:

```java
Person first = new Person("Mai");
Person second = first;
second = new Person("Nam");
```

Trước khi gán lại `second`:

```text
first ───────────┐
                 ├──> [Person A: "Mai"]
second ──────────┘
```

Sau `second = new Person("Nam")`:

```text
first ────────────────> [Person A: "Mai"]

second ───────────────> [Person B: "Nam"]
```

Đã có **hai object** khác nhau. `second` chuyển sang tham chiếu object B, nhưng `first` **vẫn giữ tham chiếu tới object A**. Java không duy trì một “mối liên kết vĩnh viễn” giữa hai biến chỉ vì trước đây chúng từng cùng trỏ một object.

Khi viết `second = first;` ở bước tiếp theo, nó **chỉ sao chép lại tham chiếu** của `first` sang `second`; không tạo object mới và không tự hủy object B ngay tại câu lệnh đó. Object B có thể còn tham chiếu khác; ngay cả khi không còn, việc thu gom bộ nhớ không nhất thiết xảy ra tức thì.

### Thay trạng thái object khác với gán lại biến

Hai câu sau có tác dụng hoàn toàn khác:

- `second.rename("An");`: gọi method trên **object mà `second` đang trỏ tới**, có thể thay đổi trạng thái object.
- `second = first;`: thay **giá trị tham chiếu trong biến `second`**; bản thân nội dung hai object không tự bị sao chép hay chỉnh sửa.

Đây là cách phân biệt cốt lõi để hiểu bug aliasing và tránh đoán sai dữ liệu khi method/field nhận tham chiếu.

## 7. Ví dụ nhiều bước với sơ đồ và output chính xác

Tạo tệp **`ReferenceTimelineDemo.java`**:

```java
class Box {
    private final String id;
    private int value;

    Box(String id, int value) {
        this.id = id;
        this.value = value;
    }

    void add(int amount) {
        value += amount;
    }

    String describe() {
        return id + "=" + value;
    }
}

public class ReferenceTimelineDemo {
    public static void main(String[] args) {
        Box a = new Box("A", 10);
        Box b = a;

        b.add(5);
        System.out.println("1: " + a.describe());
        System.out.println("2: " + (a == b));

        b = new Box("B", 20);
        System.out.println("3: " + b.describe());
        System.out.println("4: " + (a == b));

        a = b;
        a.add(2);
        System.out.println("5: " + a.describe());
        System.out.println("6: " + b.describe());
        System.out.println("7: " + (a == b));
    }
}
```

Lệnh:

```bash
javac ReferenceTimelineDemo.java
java ReferenceTimelineDemo
```

Output:

```text
1: A=15
2: true
3: B=20
4: false
5: B=22
6: B=22
7: true
```

Có thể truy vết bằng bốn trạng thái:

**Trạng thái T1 — Sau khi khai báo, tạo, gán alias:**

```text
a ─────┐
       ├──> [Box A, value=10]
b ─────┘
```

**Trạng thái T2 — Sau `b.add(5)`:**

```text
a ─────┐
       ├──> [Box A, value=15]
b ─────┘
```

Object A bị thay đổi, không có object mới. `a.describe()` trả `A=15`; `a == b` trả `true`.

**Trạng thái T3 — Sau `b = new Box("B",20)`:**

```text
a ───────> [Box A, value=15]

b ───────> [Box B, value=20]
```

Object B là object mới; `a==b` thành `false`. Object A vẫn được `a` trỏ tới.

**Trạng thái T4 — Sau `a = b; a.add(2)`:**

```text
a ─────┐
       ├──> [Box B, value=22]
b ─────┘

[Box A, value=15]  (không còn được a hoặc b trỏ tới)
```

`a = b` không tạo object mới; hai biến cùng trỏ B. `a.add(2)` sửa B thành 22. Vì vậy cả `a.describe()` và `b.describe()` đều trả `B=22`. Box A có thể trở nên không thể truy cập từ đoạn chương trình này; không được kết luận rằng nó bị hủy ngay, vì garbage collection do JVM quyết định.

> **Cách đọc sơ đồ:** Vẽ một hộp cho **mỗi object thực**, một nhãn cho **mỗi biến tham chiếu**, sau đó cập nhật mũi tên khi có phép gán. Chỉ cập nhật **nội dung hộp object** khi có hành vi sửa trạng thái. Không tạo thêm hộp object chỉ vì xuất hiện biến alias.

## 8. `null`: có giá trị tham chiếu nhưng không trỏ tới object

Ví dụ:

```java
Box current = null;
```

Sơ đồ:

```text
current : Box ──────> null

Không có Box object tại đầu mũi tên.
```

Tại đây `current` **đã được gán** một giá trị hợp lệ của kiểu tham chiếu. Nhưng `current.describe()` sẽ ném `NullPointerException` khi lời gọi instance method đòi receiver object.

```java
class NullReferenceExample {
    static void show() {
        String name = null;
        System.out.println(name == null);  // true
        // System.out.println(name.length());
        // Nếu chạy: NullPointerException vì name không trỏ String object.
    }
}
```

Đây là khai báo lớp có thể biên dịch do câu lỗi runtime đã được comment. Biến local `name` được gán `null` nên **không vi phạm definite assignment**; nguy cơ nằm ở dereference một tham chiếu không trỏ object.

### Phân biệt với chuỗi ký tự `"null"`

`String a = null;` khác `String b = "null";`:

```text
a ──────> null                  (không có String object)
b ──────> String có nội dung "null"
```

`a == null` là `true`, còn `b == null` là `false`. Việc in một giá trị null bằng phương tiện nối chuỗi có thể cho thấy chữ `null` trên console nhưng không biến null thành đối tượng String.

## 9. `==` kiểm tra cùng object; `equals` kiểm tra theo hợp đồng của lớp

Với tham chiếu, `==` so sánh **identity của tham chiếu**: hai biến có chỉ cùng object không? Còn `equals` là một instance method; nếu lớp override đúng hợp đồng, nó có thể so sánh **nội dung có ý nghĩa**.

Ví dụ với object bất biến:

```java
String one = new String("Java");
String two = new String("Java");

System.out.println(one == two);      // false
System.out.println(one.equals(two)); // true
```

Đây là mảnh code trong method. Hai phép `new String("Java")` tạo hai String objects riêng theo ngữ nghĩa của biểu thức `new`; chúng có cùng nội dung nhưng không phải cùng object. `String.equals` so sánh nội dung ký tự, nên trả `true`.

Sơ đồ:

```text
one ────> [String object #1: "Java"]

two ────> [String object #2: "Java"]
```

**Cẩn trọng với String literal:** các chuỗi literal có thể được intern, vì vậy phép `==` giữa literal không chứng minh nội dung được so sánh đúng trong mọi tình huống. Khi cần so sánh text, dùng `equals` hoặc `Objects.equals(a,b)` nếu phải xử lý khả năng `null`.

### `equals` mặc định chưa chắc so sánh field

Một class tự định nghĩa **không override `equals`** sẽ thừa hưởng implementation của `Object.equals`, vốn về cơ bản so sánh identity. Vì thế hai `new Box("A", 10)` có cùng dữ liệu chưa chắc `equals` trả `true`.

Nếu thiết kế một **value object** cần so sánh theo nội dung, phải triển khai `equals` và `hashCode` nhất quán (hoặc dùng `record` khi phù hợp). Phần này không thay đổi sơ đồ tham chiếu; nó thay đổi **cách so sánh nội dung theo API**.

## 10. Truyền object vào method: Java luôn truyền tham số theo giá trị

Đây là nguồn nhầm lẫn lớn: Java **pass-by-value**, kể cả khi đối số là tham chiếu. Khi gọi method với một biến tham chiếu, Java **sao chép giá trị tham chiếu** vào tham số cục bộ của method.

Điều này dẫn tới hai hệ quả khác nhau:

1. Method có thể dùng tham số để **sửa nội dung object chung**, nếu object là mutable và quyền truy cập cho phép.
2. Method **không thể đổi giá trị biến tham chiếu tại caller** chỉ bằng cách gán lại tham số cục bộ.

### Sơ đồ khi truyền tham chiếu

```text
Trước lời gọi:
callerRef ─────────> [Box A, value=10]

Trong lời gọi change(callerRef):
callerRef ─────────┐
                   ├──> [Box A, value=10]
parameter ─────────┘

Sau lệnh parameter = new Box("B",20):
callerRef ─────────> [Box A, value=10]
parameter ─────────> [Box B, value=20]

Ra khỏi method:
Biến parameter hết scope; callerRef vẫn trỏ Box A.
```

### Ví dụ Java 17+ chạy được

Tạo tệp **`PassByValueReferenceDemo.java`**:

```java
class Cell {
    int number;

    Cell(int number) {
        this.number = number;
    }
}

public class PassByValueReferenceDemo {
    static void change(Cell parameter) {
        parameter.number += 3;
        parameter = new Cell(99);
        System.out.println("inside=" + parameter.number);
    }

    public static void main(String[] args) {
        Cell original = new Cell(2);
        change(original);
        System.out.println("outside=" + original.number);
    }
}
```

Biên dịch/chạy:

```bash
javac PassByValueReferenceDemo.java
java PassByValueReferenceDemo
```

Output:

```text
inside=99
outside=5
```

Tại đầu `change`, biến `parameter` và `original` cùng tham chiếu object `Cell(2)`. Lệnh `parameter.number += 3` sửa object chung thành `5`. Tiếp đến, `parameter = new Cell(99)` tạo một object khác và **chỉ gán lại biến tham số**. Vì vậy method in `inside=99`, còn caller vẫn dùng object đầu với `number=5`.

**Không gọi đây là “Java truyền object theo tham chiếu” theo nghĩa pass-by-reference:** giá trị được chuyển là **bản sao của tham chiếu**. Method không nhận quyền thay đổi trực tiếp ô biến `original` của caller.

### Muốn caller nhận object mới thì làm thế nào?

Method có thể **trả về tham chiếu**:

```java
static Cell replacement(int number) {
    return new Cell(number);
}
```

Khi caller chủ động gán `original = replacement(42);`, biến ở caller đổi tham chiếu vì **caller thực hiện phép gán**. Method không tự gán lại biến caller.

## 11. Sơ đồ tham chiếu với field chứa object khác

Một object có thể chứa field kiểu tham chiếu tới object khác, tạo thành **object graph** (đồ thị đối tượng).

```java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Employee {
    String name;
    Address address;

    Employee(String name, Address address) {
        this.name = name;
        this.address = address;
    }
}
```

Khi chạy:

```java
Address home = new Address("Da Nang");
Employee an = new Employee("An", home);
Employee binh = new Employee("Binh", home);
```

Sơ đồ:

```text
home ───────────────────────────────┐
                                    v
                             [Address A]
                              city="Da Nang"
                                    ^
                                    |
an ──> [Employee An] ── address ────┤
                                    |
binh ─> [Employee Binh] ─ address ──┘
```

Có **hai Employee objects** nhưng **một Address object** được chia sẻ. Vì thế nếu `home.city = "Hue";` và các field truy cập được trong phạm vi ví dụ, cả `an.address.city` và `binh.address.city` đều cho `"Hue"`. Nhưng nếu viết `an.address = new Address("Ha Noi");`, chỉ field `address` của Employee An được gán sang Address mới; Employee Binh vẫn trỏ Address A.

Đây là **mã minh họa không có `main` riêng**. Trường hợp chia sẻ một mutable object dễ tạo side effect giữa các thành phần ứng dụng. Với dữ liệu cần bất biến, có thể dùng immutable value object hoặc cơ chế defensive copy khi thiết kế constructor/getter.

### Tại sao aliasing không chỉ xảy ra giữa biến local?

Bất kỳ nơi nào lưu giá trị tham chiếu — local variable, field, static field, array element, method parameter — đều có thể trở thành một đường dẫn tới cùng object. Sơ đồ cần vẽ **đúng các nơi giữ tham chiếu**, không chỉ những biến viết trong `main`.

## 12. Mảng cũng là object: biến mảng và phần tử mảng giữ vai trò khác nhau

`int[] numbers = new int[3];` có hai khái niệm:

- `numbers` là **biến tham chiếu** kiểu `int[]`.
- `new int[3]` là **một object mảng** chứa ba phần tử `int`, ban đầu đều bằng `0`.

```text
numbers ─────> [int[] object]
               index 0 = 0
               index 1 = 0
               index 2 = 0
```

Nếu viết `int[] alias = numbers;`, hai biến cùng trỏ một mảng. `alias[0] = 7;` sẽ khiến `numbers[0]` thành `7`. Tạo `alias = new int[3];` sẽ khiến hai biến trỏ hai array objects khác nhau; mảng `numbers` không đổi.

### Mảng object lưu tham chiếu ở từng phần tử

```java
Person[] people = new Person[2];
```

Sơ đồ ngay sau `new Person[2]`:

```text
people ─────> [Person[] array object]
               [0] ───> null
               [1] ───> null
```

Java **chỉ tạo object mảng**, không gọi `new Person()` hai lần. Mỗi phần tử kiểu `Person` mang giá trị mặc định `null` cho đến khi được gán.

Sau khi viết `people[0] = new Person("Mai"); people[1] = people[0];`:

```text
people ─────> [Person[] array object]
               [0] ──────────┐
                             ├──> [Person A: "Mai"]
               [1] ──────────┘
```

Hai phần tử mảng tham chiếu **một** Person object. Việc sửa object qua `people[1]` sẽ quan sát được khi đọc qua `people[0]`. Nếu gán `people[1] = new Person("Nam");`, hai phần tử lại trỏ hai objects.

### Ví dụ độc lập: aliasing trong mảng

Tạo tệp **`ArrayReferenceDemo.java`**:

```java
class Point {
    int x;

    Point(int x) {
        this.x = x;
    }
}

public class ArrayReferenceDemo {
    public static void main(String[] args) {
        Point[] points = new Point[2];
        System.out.println(points[0] == null);

        points[0] = new Point(4);
        points[1] = points[0];
        points[1].x += 3;

        System.out.println(points[0].x);
        System.out.println(points[0] == points[1]);

        points[1] = new Point(9);
        System.out.println(points[0].x);
        System.out.println(points[1].x);
    }
}
```

```bash
javac ArrayReferenceDemo.java
java ArrayReferenceDemo
```

```text
true
7
true
7
9
```

Khi hai phần tử cùng trỏ một `Point`, cập nhật `points[1].x` làm `points[0].x` đổi. Gán một `new Point(9)` vào phần tử thứ hai thay **tham chiếu trong slot mảng**, không sửa object đầu.

## 13. Static field giữ tham chiếu được chia sẻ trên cấp lớp

Một `static field` kiểu tham chiếu là nơi lưu tham chiếu thuộc về **lớp**, không gắn riêng với mỗi object.

```java
class Registry {
    static Point current;
}
```

Ban đầu, trước khi có phép gán tường minh, `Registry.current` mang `null` theo quy tắc mặc định. Sau khi `Registry.current = new Point(10);`:

```text
Registry.current ──────────> [Point A: x=10]
```

Nếu hai local variables đều được gán từ `Registry.current`, chúng có thể cùng trỏ `Point A`. Việc ghi `Registry.current = new Point(20);` chỉ thay tham chiếu lưu trong static field; các biến đã từng sao chép tham chiếu cũ **không tự chuyển** sang object mới.

Ví dụ:

```java
Point old = Registry.current;
Registry.current = new Point(20);

// old vẫn tham chiếu Point A (x=10).
// Registry.current trỏ Point B (x=20).
```

Các dòng trên là mảnh mã trong method, dùng lớp `Point` đã minh họa ở mục trước. Cần phân biệt “trường dữ liệu dùng chung” với “mọi biến từng đọc trường đó luôn được cập nhật”: việc **lưu lại bản sao tham chiếu** làm thay đổi đường tham chiếu về sau.

Trong chương trình đa luồng, truy cập một static field mutable còn liên quan visibility/data race; một sơ đồ tham chiếu đơn luồng chưa đủ chứng minh an toàn đồng thời.

## 14. Tham chiếu và kế thừa: kiểu tĩnh khác lớp thực tế

Một biến kiểu lớp cha hoặc interface có thể trỏ tới object lớp con phù hợp:

```java
Animal animal = new Dog();
```

Về mặt sơ đồ:

```text
animal : Animal ───────> [Dog object]
                         kind = Dog
```

Biến `animal` **có kiểu tĩnh `Animal`**, trong khi object runtime là `Dog`. Phép gán này hợp lệ nếu `Dog` là subtype phù hợp của `Animal`. Nhưng đổi kiểu tham chiếu **không biến object Dog thành Animal object mới**.

Đây là ý quan trọng khi đọc method call:

- Compiler xác định method có thể gọi dựa vào **kiểu tĩnh** của biểu thức nhận lời gọi.
- Khi instance method đã được override và có thể dispatch động, runtime chọn implementation theo **lớp thực tế của receiver**.
- Với field access, Java phân giải field theo các quy tắc **kiểu tĩnh**, không dùng dynamic dispatch cho field.

### Ví dụ đầy đủ

Tạo tệp **`ReferencePolymorphismDemo.java`**:

```java
class Animal {
    String speak() {
        return "animal";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "woof";
    }

    String fetch() {
        return "ball";
    }
}

public class ReferencePolymorphismDemo {
    public static void main(String[] args) {
        Dog dog = new Dog();
        Animal animal = dog;

        System.out.println(animal.speak());
        System.out.println(dog.fetch());
        System.out.println(animal == dog);
        System.out.println(animal instanceof Dog);
    }
}
```

```bash
javac ReferencePolymorphismDemo.java
java ReferencePolymorphismDemo
```

```text
woof
ball
true
true
```

`animal` và `dog` cùng trỏ một Dog object nên `animal == dog` là `true`. `animal.speak()` chọn implementation override ở `Dog`, nhưng `animal.fetch()` **không biên dịch** nếu thêm vào ví dụ vì kiểu tĩnh `Animal` không khai báo method `fetch()`. `animal instanceof Dog` là `true` do object thực tế là `Dog`.

**Không cần tạo thêm Dog object** khi gán `Animal animal = dog;`; thao tác này chỉ sao chép tham chiếu hợp lệ.

## 15. `final` trên biến tham chiếu không làm object bất biến

Từ khóa `final` giới hạn việc **gán lại biến**, chứ không tự làm object mà biến trỏ tới trở nên immutable.

```java
final Point point = new Point(5);
point.x = 8;                 // Hợp lệ nếu field x cho phép ghi.
// point = new Point(10);    // Lỗi: không thể gán lại biến final.
```

Đây là mảnh code trong method với lớp `Point` ở ví dụ mảng. Sơ đồ:

```text
point (final) ─────> [Point object]
                      x: 5 -> 8
```

Mũi tên từ biến `point` không được gán lại sang object khác theo quy tắc `final`; nhưng trạng thái object có thể thay đổi qua tham chiếu này hoặc alias khác.

Nếu một class cần **bất biến**, phải thiết kế field, constructor và cách phơi bày tham chiếu phù hợp (ví dụ private final primitive fields, không cung cấp setter, defensive copy cho mutable components). `final Point point` **chưa đủ** để bảo đảm Point object bất biến.

## 16. Sơ đồ tham chiếu và garbage collection: đừng nhầm “mất alias” với “object bị hủy ngay”

Xét:

```java
Box current = new Box("A", 1);
Box alias = current;

current = null;
```

Sơ đồ:

```text
current ──────> null

alias ────────> [Box A, value=1]
```

Object A vẫn có **tham chiếu mạnh** từ `alias`, nên việc gán `current = null` không khiến object lập tức “biến mất”. Nếu sau đó `alias = null;` và **không còn đường tham chiếu mạnh nào từ các GC roots tới object A**, object có thể trở nên **eligible for garbage collection**.

Tuy nhiên:

- **Eligible** không đồng nghĩa “được thu gom ngay”.
- `System.gc()` không bảo đảm một object cụ thể sẽ bị dọn trong thời điểm bạn muốn.
- JVM có thể tối ưu hóa cách quản lý vòng đời object; mã Java chuẩn không nên dựa vào một thời điểm hủy object cố định.
- Trạng thái “không còn reference từ hai biến local” không đủ chứng minh object unreachable nếu vẫn có static field, field của object khác, phần tử mảng, thread hoặc GC root khác tham chiếu tới nó.
- Một vòng tham chiếu (A trỏ B và B trỏ A) **không nhất thiết ngăn thu gom**, nếu cả hai không còn reachable từ GC roots; garbage collector Java có thể xử lý chu kỳ không reachable.

**Sơ đồ là công cụ lý luận về reachability**, không phải ảnh chụp heap thực của JVM. Không nên kết luận chính xác “object được giải phóng ở lệnh nào” chỉ dựa vào việc một biến được gán `null`.

### Không có phép xóa object trực tiếp trong Java

Java không có `delete object;` như một số cơ chế quản lý bộ nhớ thủ công của ngôn ngữ khác. Để giải phóng tài nguyên ngoài bộ nhớ (file, socket, kết nối), cần dùng API đóng tài nguyên phù hợp, ví dụ `try-with-resources`; đừng thay việc đóng tài nguyên bằng thao tác `reference = null`.

## 17. Các sơ đồ “stack/heap” nên hiểu ở mức nào?

Tài liệu nhập môn thường vẽ biến local ở **stack** và object ở **heap**. Đây là **mô hình giản lược hữu ích để bắt đầu**, nhưng không phải cam kết rằng mỗi biến tham chiếu đều nằm ở vị trí nhớ cố định hay mọi object luôn có một địa chỉ heap mà chương trình có thể quan sát.

Ngữ nghĩa Java bảo đảm các quan hệ như:

1. Giá trị tham chiếu có thể trỏ object hoặc là `null`.
2. Phép gán giữa hai biến tham chiếu sao chép **giá trị tham chiếu**, không tự clone object.
3. `new` tạo instance theo ngữ nghĩa biểu thức, và object có **identity** riêng.
4. Hai alias có thể cùng quan sát thay đổi trạng thái của mutable object.
5. Tham số method nhận **bản sao giá trị tham chiếu**.
6. JVM quản lý vòng đời object và garbage collection, không phơi bày thao tác giải phóng trực tiếp.

Những chi tiết triển khai như object header, compressed oops, escape analysis, stack allocation optimization hoặc scalar replacement phụ thuộc JVM và chế độ tối ưu. **Không dựa vào các chi tiết ấy để giải thích output** trừ khi đang học riêng về JVM internals.

Nếu vẽ sơ đồ trong bài tập, nên ghi nhãn hai vùng:

```text
Các nơi giữ tham chiếu       Đồ thị đối tượng (khái niệm)
(local / field / array)      (không cam kết layout máy)

local x ────────────────────> Object #1
field y ────────────────────> Object #2
array[0] ───────────────────> Object #1
```

Sơ đồ này chính xác về **aliasing** mà không tuyên bố vị trí vật lý của từng biến/object.

## 18. Những lỗi thường gặp khi vẽ hoặc giải thích tham chiếu

| Nhầm lẫn | Điều đúng cần dùng |
| --- | --- |
| “Khai báo `Person p;` đã tạo một Person” | Chỉ khai báo local; không có object mới |
| “`Person p = null;` có một Person rỗng” | `null` không trỏ object nào |
| “`Person b = a;` tạo bản sao đối tượng” | Chỉ sao chép giá trị tham chiếu; thường tạo alias |
| “Đổi tên biến sẽ đổi tên object” | Object có identity riêng, không gắn với tên biến |
| “Gán `a = new Person(...)` cập nhật mọi alias cũ” | Chỉ giá trị biến `a` được gán lại |
| “`b.rename(...)` thay biến `b` thành object khác” | Thường là thay state của receiver; phải đọc method body |
| “Truyền tham chiếu vào method là pass-by-reference” | Java pass-by-value: sao chép giá trị tham chiếu |
| “Method gán `parameter = new ...` làm caller đổi biến” | Không; chỉ gán lại tham số cục bộ |
| “`a == b` so sánh nội dung” | Với reference, `==` kiểm tra cùng object; `equals` tùy hợp đồng lớp |
| “`new Person[3]` tạo ba Person objects” | Chỉ tạo array object; các phần tử Person mặc định `null` |
| “`final` biến tham chiếu làm object immutable” | `final` không cho gán lại biến; object có thể vẫn mutable |
| “`Base x = new Derived()` tạo thêm Base object” | Một Derived instance; biến được gán reference có kiểu tĩnh Base |
| “Field và biến local đều mặc định `null`” | Reference field mặc định `null`; local phải definite assigned trước khi đọc |
| “Gán `x = null` lập tức gọi GC” | Chỉ gán biến; GC không được bảo đảm tức thì |
| “Mũi tên là địa chỉ pointer cụ thể” | Đó là biểu diễn khái niệm về tham chiếu, không phải API địa chỉ bộ nhớ |
| “Một object chỉ có thể có một biến trỏ tới” | Có thể nhiều local variables, fields, array elements cùng tham chiếu |
| “Hai object có field bằng nhau là cùng object” | Identity và equality theo nội dung là hai quan hệ khác nhau |
| “Tạo một object lớp con cũng tạo một object superclass độc lập” | Phần superclass được khởi tạo trong cùng instance lớp con |

## 19. Tự kiểm tra theo từng tình huống

**Câu 1.** Sau `Student x;` trong method, có object `Student` mới không? Đọc `x` ngay có hợp lệ không?

*Đáp án:* Không có object mới. `x` là local chưa definite assigned, nên đọc ngay là lỗi biên dịch.

**Câu 2.** `Student x = null;` có khác với `Student x;` không?

*Đáp án:* Có. `x = null` đã gán một giá trị tham chiếu đặc biệt có thể đọc; `Student x;` chỉ khai báo local chưa gán.

**Câu 3.** `Point a = new Point(4); Point b = a;` có bao nhiêu object `Point` được tạo bởi hai lệnh?

*Đáp án:* Một object. `b = a` chỉ sao chép tham chiếu và tạo alias.

**Câu 4.** Nếu sau đó `b.x = 7;`, `a.x` bằng gì?

*Đáp án:* `7`, vì `a` và `b` cùng trỏ một mutable Point object.

**Câu 5.** Nếu tiếp theo `b = new Point(9);`, `a.x` và `b.x` là bao nhiêu?

*Đáp án:* `a.x == 7`, `b.x == 9`. Có hai Point objects khác nhau.

**Câu 6.** Với `Box first = new Box("A",1); Box second = first;`, viết `first = null;` thì `second` có thành null không?

*Đáp án:* Không. `second` vẫn giữ tham chiếu object cũ.

**Câu 7.** Vì sao `new Person[3]` không tương đương với ba lần `new Person(...)`?

*Đáp án:* Biểu thức đầu chỉ tạo một object mảng chứa ba ô tham chiếu `null`; constructor `Person` chưa được gọi cho từng phần tử.

**Câu 8.** Nếu method `change(Cell p)` gán `p = new Cell(99);`, biến `original` ở caller có tự trỏ Cell(99) không?

*Đáp án:* Không, vì tham số `p` chỉ nhận bản sao giá trị tham chiếu. Caller phải tự gán kết quả nếu muốn đổi tham chiếu.

**Câu 9.** `Animal a = new Dog();` tạo hai objects Animal và Dog hay một?

*Đáp án:* Một Dog object. Biến `a` có kiểu tĩnh Animal nhưng trỏ Dog object.

**Câu 10.** `final Point p = new Point(1); p.x = 2;` có sai chỉ vì `p` final không?

*Đáp án:* Không, nếu field `x` cho phép sửa. `final` trên `p` cấm gán lại biến `p`, không cấm sửa nội dung Point.

**Câu 11.** Hai `new String("Hi")` khác nhau có thể `equals` bằng `true` nhưng `==` bằng `false` không?

*Đáp án:* Có. Hai object khác nhau về identity nhưng cùng nội dung ký tự.

**Câu 12.** Gán biến cuối cùng đang giữ tham chiếu tới một object thành `null` có đảm bảo object được thu gom ngay không?

*Đáp án:* Không. Reachability còn phụ thuộc các đường tham chiếu khác; ngay cả khi eligible for GC, không có bảo đảm thu gom tức thời.

**Câu 13.** Một `static Point current` đã tham chiếu object A; local `old = current`. Sau khi `current = new Point(8)`, `old` tham chiếu object nào?

*Đáp án:* Vẫn là A. Giá trị đã sao chép vào `old` không tự thay đổi khi static field `current` bị gán lại.

**Câu 14.** Trong sơ đồ `a ──> A` và `b ──> A`, nếu `b = a` thực thi thêm lần nữa, có object mới không?

*Đáp án:* Không. `b` chỉ nhận lại giá trị tham chiếu đang có trong `a`.

## 20. Quy trình vẽ sơ đồ tham chiếu chính xác

Khi làm bài tập Java có nhiều phép gán và lời gọi method, nên làm theo thứ tự:

1. **Liệt kê biến và nơi chứa tham chiếu:** local, tham số, field, static field, ô mảng. Ghi **kiểu tĩnh** của từng biến.
2. **Đánh dấu biến chưa gán:** với local `Type x;`, ghi “chưa definite assigned”, không tự vẽ null.
3. **Với `new`, tạo một hộp object mới:** ghi nhãn riêng như A, B, C; gán các field sau khi initializer/constructor hoàn tất theo kịch bản.
4. **Với phép gán tham chiếu `left = right`, cập nhật mũi tên của left:** không tự tạo bản sao object bên phải.
5. **Với `left.field = value` hoặc instance method sửa state, cập nhật nội dung object receiver:** nếu nhiều alias trỏ object ấy, tất cả đều quan sát cùng state khi đọc.
6. **Khi truyền vào method, vẽ một biến tham số mới cùng trỏ object:** mọi phép gán lại tham số chỉ cập nhật mũi tên cục bộ của tham số.
7. **Với array hoặc field kiểu tham chiếu, thêm mũi tên từ slot/field:** một object có thể được nhiều slots trỏ tới.
8. **Với `null`, vẽ không có object đích:** nếu code dereference null, ghi lỗi runtime thích hợp.
9. **Với `==` trên references, so sánh hai đích của mũi tên:** cùng object → true; khác object → false (trừ trường hợp null theo quy tắc).
10. **Với `equals`, xem hợp đồng của lớp thay vì suy từ sơ đồ identity.**
11. **Với `final`, khóa khả năng gán lại biến/field tham chiếu, không khóa state object một cách tự động.**
12. **Khi một object mất mũi tên, chưa vội ghi “đã hủy”:** chỉ phân tích reachability và khả năng GC, không cam kết thời điểm thu gom.
13. **Đối chiếu output theo thời gian:** sau mỗi statement, ghi lại từng biến trỏ object nào, field có giá trị gì và method thực thi trên receiver nào.

### Bài tập tự thực hành cuối

Không cần chạy ngay; thử tự vẽ sau từng dòng rồi đối chiếu lời giải:

```java
class Node {
    int value;
    Node next;

    Node(int value) {
        this.value = value;
    }
}

// Những lệnh dưới đây nằm trong một method:
Node a = new Node(1);
Node b = new Node(2);
a.next = b;
Node c = a;
b = new Node(3);
c.next.value += 5;
```

**Lời giải:**

```text
Sau hai lệnh new đầu:
a ─────> [Node A: value=1, next=null]
b ─────> [Node B: value=2, next=null]

Sau a.next = b:
a ─────> [Node A: value=1]
                     |
                     next ───> [Node B: value=2]
b ────────────────────────────────────^

Sau Node c = a:
a ──┐
    ├──> [Node A] ──next──> [Node B: value=2]
c ──┘                     ^
                          |
b ────────────────────────┘

Sau b = new Node(3):
a ──┐
    ├──> [Node A] ──next──> [Node B: value=2]
c ──┘
b ───────────────────────> [Node C: value=3]

Sau c.next.value += 5:
a ──┐
    ├──> [Node A] ──next──> [Node B: value=7]
c ──┘
b ───────────────────────> [Node C: value=3]
```

**Vì sao `Node B` vẫn tồn tại?** `b` đã chuyển sang Node C, nhưng field `a.next` (cũng được nhìn qua `c.next`) vẫn trỏ Node B. `c.next.value += 5` vì thế sửa **Node B**, không sửa Node C. Kết quả là `a.next.value == 7`, `b.value == 3` và `a == c` là `true`.

---

**Ghi nhớ:** **Khai báo biến không tạo object; `new` tạo object; phép gán giữa các biến tham chiếu chỉ sao chép tham chiếu.** Hai alias có thể cùng quan sát thay đổi của một mutable object, còn gán lại một alias không khiến alias khác tự chuyển đích. `null` là “không có object đích”; method nhận bản sao giá trị tham chiếu; `==` kiểm tra identity còn `equals` phụ thuộc hợp đồng lớp. Sơ đồ mũi tên là mô hình **quan hệ tham chiếu**, không phải cam kết về địa chỉ máy hoặc thời điểm garbage collection.