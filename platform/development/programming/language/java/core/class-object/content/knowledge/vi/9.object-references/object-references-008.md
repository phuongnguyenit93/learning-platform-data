# Mảng đối tượng: tạo mảng tham chiếu và tạo từng phần tử trong Java

## 1. Hai loại đối tượng khác nhau: object mảng và object phần tử

Trong Java, **mảng (*array*) là một đối tượng**. Khi khai báo mảng của một lớp, ví dụ `Student[]`, mảng không chứa các object `Student` trực tiếp theo mô hình ngôn ngữ; nó chứa **các phần tử là giá trị tham chiếu**. Mỗi phần tử có thể tham chiếu đến một object `Student` hoặc nhận `null`.

Hai biểu thức sau **khác nhau về bản chất**:

```java
Student[] students = new Student[3];
Student one = new Student("An");
```

Đây là **đoạn mã minh họa**; giả sử lớp `Student` có constructor nhận một `String`.

- `new Student[3]` tạo **một object mảng** có ba ô tham chiếu, mỗi ô ban đầu là **`null`**. Nó **không** gọi `new Student()` và **không** tạo ba object `Student`.
- `new Student("An")` tạo **một object `Student`** (sau đó khởi tạo theo constructor tương ứng); giá trị biểu thức là tham chiếu tới object đó.
- `students` là biến tham chiếu đến **array object**.
- `students[0]` là **một slot của array object** lưu giá trị tham chiếu `Student`. Ban đầu giá trị slot là `null`; bạn có thể gán tham chiếu một `Student` cụ thể vào đó.

**Sơ đồ ngay sau `new Student[3]`:**

```text
students : Student[]
       |
       v
  +---------------------------+
  | Student[] array (length 3)|
  +---------------------------+
  | [0] ----> null            |
  | [1] ----> null            |
  | [2] ----> null            |
  +---------------------------+

Số Student object do dòng new Student[3] tạo: 0
Số array object do dòng đó tạo: 1
```

**Sơ đồ sau khi tạo một phần tử:**

```java
students[0] = new Student("An");
```

```text
students
    |
    v
  +----------------------+
  | Student[] (length 3) |
  | [0] -----------------------+----> Student A { name="An" }
  | [1] ---> null       |     |
  | [2] ---> null       |     |
  +----------------------+     |
                               +--- 1 Student object mới
```

Các hình là **sơ đồ tham chiếu khái niệm**, không phải bản mô tả địa chỉ bộ nhớ máy hoặc một cách biểu diễn vật lý cố định của JVM.

> **Ghi nhớ đầu tiên:** tạo *mảng tham chiếu* và tạo *đối tượng được tham chiếu bởi từng phần tử* là **hai việc riêng biệt**. Đối với mảng của lớp, interface hoặc các kiểu tham chiếu khác, không được suy diễn rằng số phần tử mảng chính là số object thành phần được tạo.

## 2. Cú pháp khai báo, cấp phát và gán phần tử

Các dạng khai báo phổ biến:

```java
Student[] first;
Student second[];
Student[] third = new Student[3];
```

Hai dạng `Student[] first` và `Student second[]` đều được Java hỗ trợ, nhưng **`Student[]` thường dễ đọc hơn** vì dấu ngoặc vuông đặt cạnh kiểu. Đây là mảnh khai báo dùng trong phạm vi phù hợp, không chứa định nghĩa `Student`.

Phân biệt ba hành động:

| Câu lệnh | Ý nghĩa | Tạo array object? | Tạo Student object? |
| --- | --- | --- | --- |
| `Student[] a;` | Chỉ khai báo biến cục bộ kiểu mảng | Không | Không |
| `Student[] a = null;` | Khai báo và gán giá trị null | Không | Không |
| `Student[] a = new Student[3];` | Tạo mảng dài 3, các slot null | **Có: 1** | Không |
| `a[0] = new Student("An");` | Tạo Student và gán tham chiếu vào slot 0 | Không tạo mảng mới | **Có: 1** |
| `a[1] = a[0];` | Sao chép tham chiếu từ slot 0 vào slot 1 | Không | Không |
| `a = new Student[5];` | Tạo mảng khác và gán lại biến `a` | **Có: 1 mảng mới** | Không |
| `a[2] = null;` | Đặt slot 2 về null | Không | Không |

**Điểm tinh tế:** `Student[] a;` nếu là **biến cục bộ** phải được *definitely assigned* trước khi đọc. Nếu là instance field hoặc static field, nó có giá trị mặc định `null` theo quy tắc khởi tạo field. Ngược lại, **các phần tử** của `new Student[3]` đã được mặc định thành `null` ngay khi mảng được tạo.

Mã minh họa lỗi compile-time:

```java
// Trong một method:
Student[] local;
// System.out.println(local.length); // Lỗi: local chưa được gán.
local = new Student[3];
System.out.println(local.length);      // Hợp lệ, in 3.
```

Một biến mảng có kiểu `Student[]` **không phải** một `Student`. Bạn không thể gọi instance method của `Student` trực tiếp trên cả mảng:

```java
// students.getName(); // Sai nếu getName() là method của Student.
students[0].getName(); // Đúng cú pháp nếu students[0] khác null.
```

Dòng hợp lệ ở cuối vẫn có thể ném `NullPointerException` khi phần tử bằng `null`.

## 3. Chương trình chạy độc lập đầu tiên: đếm lần gọi constructor

Tạo tệp **`StudentArrayBasicsDemo.java`** và chạy bằng JDK 17+:

```java
class Student {
    private final String name;
    private static int created;

    Student(String name) {
        this.name = name;
        created++;
    }

    String getName() {
        return name;
    }

    static int getCreated() {
        return created;
    }
}

public class StudentArrayBasicsDemo {
    public static void main(String[] args) {
        Student[] students = new Student[3];

        System.out.println("array length=" + students.length);
        System.out.println("created=" + Student.getCreated());
        System.out.println("first null=" + (students[0] == null));

        students[0] = new Student("An");
        students[1] = new Student("Binh");
        students[2] = new Student("Chi");

        System.out.println("created=" + Student.getCreated());

        for (int i = 0; i < students.length; i++) {
            System.out.println(i + ": " + students[i].getName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac StudentArrayBasicsDemo.java
java StudentArrayBasicsDemo
```

**Standard output chính xác:**

```text
array length=3
created=0
first null=true
created=3
0: An
1: Binh
2: Chi
```

Giải thích theo thứ tự:

1. `new Student[3]` tạo array object với ba phần tử `null`; chưa có lệnh nào gọi constructor `Student(String)` nên `Student.getCreated()` trả `0`.
2. Ba câu `students[i] = new Student(...)` thực thi ba biểu thức `new Student` riêng, tạo ba object `Student` khác nhau; constructor được gọi ba lần nên biến đếm `created` thành `3`.
3. Mỗi phần tử mảng giữ tham chiếu đến object tương ứng, nên sau khi các slot đã được gán hợp lệ, `students[i].getName()` gọi method trên từng object.
4. `students.length` là **field đặc biệt của array** biểu diễn độ dài; `Student.getCreated()` là method static do lớp Student tự khai báo. Độ dài mảng và số Student objects thực sự tạo **không bắt buộc bằng nhau**.

Trong Java, mảng có độ dài cố định. Bạn có thể **thay giá trị tham chiếu bên trong từng slot**, nhưng không thể đổi giá trị của `students.length` từ 3 thành 5.

## 4. Từng slot mặc định null: lỗi dereference phổ biến

Ví dụ:

```java
Student[] students = new Student[2];
// System.out.println(students[0].getName());
```

Sau `new Student[2]`, `students` **không null**, nhưng `students[0]` và `students[1]` **đều null**. Nếu bỏ comment ở dòng thứ hai và chạy, lời gọi instance method trên `students[0]` sẽ ném `NullPointerException`.

Cần phân biệt ba tình huống:

| Biểu thức | Trạng thái | Kết quả/hậu quả |
| --- | --- | --- |
| `students == null` | Kiểm tra **biến mảng** có trỏ array object không | Nếu true, chưa thể truy cập `length` hoặc `[i]` |
| `students[0] == null` | Kiểm tra **phần tử thứ 0** có trỏ Student object không | Nếu true, không thể gọi instance method của Student qua slot ấy |
| `students[0].getName()` | Truy cập Student object qua slot 0 | Cần biến mảng và phần tử hợp lệ, chỉ số nằm trong phạm vi |

Một mảng đã được tạo **không bảo đảm mỗi phần tử cũng được tạo**.

### Ví dụ chạy độc lập: kiểm tra null đúng chỗ

Tệp **`ArrayNullDemo.java`**:

```java
class Entry {
    private final String text;

    Entry(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}

public class ArrayNullDemo {
    public static void main(String[] args) {
        Entry[] entries = new Entry[2];

        System.out.println(entries == null);
        System.out.println(entries[0] == null);

        entries[1] = new Entry("Ready");

        for (int i = 0; i < entries.length; i++) {
            if (entries[i] == null) {
                System.out.println(i + ": empty");
            } else {
                System.out.println(i + ": " + entries[i].text());
            }
        }

        try {
            entries[0].text();
        } catch (NullPointerException ex) {
            System.out.println("cannot call on null element");
        }
    }
}
```

Lệnh:

```bash
javac ArrayNullDemo.java
java ArrayNullDemo
```

```text
false
true
0: empty
1: Ready
cannot call on null element
```

**Đọc kết quả:**

- `entries` trỏ tới array object nên `entries == null` là `false`.
- `entries[0]` chưa được gán Student/Entry object nên vẫn `null`.
- `entries[1]` được khởi tạo bằng `new Entry("Ready")`, cho phép gọi `text()`.
- Khối `try/catch` cố ý gọi trên slot null để cho thấy lỗi runtime và bắt nó; chương trình không in stack trace vì đã xử lý ngoại lệ trong ví dụ.

Cách làm an toàn thực tế là **bảo đảm toàn bộ các slot phải dùng đã được khởi tạo**, hoặc **kiểm tra null rõ ràng** nếu mảng được thiết kế cho phép slot trống. Không nên dùng `try/catch NullPointerException` làm chiến lược điều khiển luồng thông thường.

## 5. Dùng vòng lặp `for` để tạo từng object riêng biệt

Khi cần một mảng có mọi phần tử khác null, hãy **tạo riêng một object cho từng chỉ số**:

```java
Student[] students = new Student[3];

for (int i = 0; i < students.length; i++) {
    students[i] = new Student("S" + (i + 1));
}
```

Kết quả khái niệm:

```text
students ──> Student[] length=3
               [0] ─────> Student A {name="S1"}
               [1] ─────> Student B {name="S2"}
               [2] ─────> Student C {name="S3"}

A, B, C là ba object có identity khác nhau.
```

Mỗi vòng lặp có một `new Student(...)` mới, nên object vừa tạo khác những object do lần lặp trước tạo. Điều này khác với việc chỉ có một `new` rồi sao chép cùng tham chiếu cho nhiều slot.

### Ví dụ độc lập minh họa identity

Tệp **`IndependentElementsDemo.java`**:

```java
class Item {
    private String label;

    Item(String label) {
        this.label = label;
    }

    void rename(String next) {
        label = next;
    }

    String label() {
        return label;
    }
}

public class IndependentElementsDemo {
    public static void main(String[] args) {
        Item[] items = new Item[3];

        for (int i = 0; i < items.length; i++) {
            items[i] = new Item("item-" + i);
        }

        items[0].rename("changed");

        System.out.println(items[0].label());
        System.out.println(items[1].label());
        System.out.println(items[0] == items[1]);
        System.out.println(items[1] == items[2]);
    }
}
```

```bash
javac IndependentElementsDemo.java
java IndependentElementsDemo
```

```text
changed
item-1
false
false
```

Ở đây mọi slot được gán bằng **một lệnh `new Item(...)` trong mỗi lần lặp**; vì vậy đổi nhãn object ở index 0 không tác động object ở index 1. Hai phép so sánh `==` trả `false` vì những tham chiếu ở các chỉ số khác nhau chỉ tới các object khác nhau.

### Dùng `Arrays.setAll` khi muốn tạo dựa theo chỉ số

Java có utility `java.util.Arrays.setAll` để gán mỗi slot bằng kết quả của một hàm theo chỉ số:

```java
Student[] students = new Student[3];
java.util.Arrays.setAll(students, i -> new Student("S" + i));
```

Đây là **mảnh mã hợp lệ trong method**, giả sử lớp `Student` có constructor phù hợp. `setAll` gọi generator cho từng index, nên biểu thức `new` trong lambda tạo object riêng mỗi lần. Lưu ý generator có thể trả `null` hoặc cùng một object nếu bạn viết như vậy; **`setAll` không tự bảo đảm uniqueness**. `for` thông thường dễ hiểu hơn ở giai đoạn đầu học về tham chiếu.

## 6. Sai lầm rất phổ biến: `Arrays.fill` tạo nhiều slot nhưng chỉ một object

Với mảng tham chiếu, `Arrays.fill` gán **cùng một giá trị tham chiếu** vào các slot, không tự gọi constructor nhiều lần.

Tạo tệp **`FillAliasDemo.java`**:

```java
import java.util.Arrays;

class Counter {
    int value;

    Counter(int value) {
        this.value = value;
    }
}

public class FillAliasDemo {
    public static void main(String[] args) {
        Counter[] counters = new Counter[3];

        Arrays.fill(counters, new Counter(5));

        System.out.println(counters[0] == counters[1]);
        System.out.println(counters[1] == counters[2]);

        counters[2].value += 7;

        System.out.println(counters[0].value);
        System.out.println(counters[1].value);
        System.out.println(counters[2].value);
    }
}
```

```bash
javac FillAliasDemo.java
java FillAliasDemo
```

**Output:**

```text
true
true
12
12
12
```

Giải thích:

1. `new Counter[3]` tạo mảng ba slot null.
2. Trong lời gọi `Arrays.fill(counters, new Counter(5))`, **biểu thức đối số** `new Counter(5)` được đánh giá một lần để tạo **một Counter object**.
3. `fill` sao chép cùng tham chiếu object đó vào cả ba slot. Vì vậy `counters[0] == counters[1] == counters[2]` theo nghĩa từng cặp đều tham chiếu cùng object.
4. Lệnh `counters[2].value += 7` thay đổi **một object dùng chung** từ 5 lên 12; đọc qua slot 0, 1, 2 đều thấy 12.

**Sơ đồ:**

```text
counters ───> Counter[] length=3
                [0] ─────────┐
                [1] ─────────┼──> Counter A {value=12}
                [2] ─────────┘
```

Nếu cần **ba object độc lập**, dùng vòng lặp với `new Counter(5)` **nằm trong thân vòng lặp**, hoặc `Arrays.setAll(counters, i -> new Counter(5))`. `Arrays.fill` chỉ phù hợp khi thực sự muốn mọi phần tử nhận **cùng giá trị**, chẳng hạn một immutable shared object hoặc shared sentinel có chủ đích.

## 7. Gán slot, sửa trạng thái object và gán lại cả biến mảng

Ba câu lệnh sau tác động vào **ba vị trí khác nhau**:

```java
Item[] items = new Item[2];
items[0] = new Item("A");
Item[] aliasArray = items;

items[0].rename("B");            // Sửa object Item ở slot 0.
items[0] = new Item("C");        // Thay tham chiếu bên trong slot 0.
items = new Item[2];             // Thay tham chiếu trong biến items.
```

Đây là **mảnh code minh họa** giả định lớp `Item` ở ví dụ trước.

Sơ đồ từng giai đoạn:

```text
1) Sau items[0] = new Item("A"):
items ─┐
       ├──> Array X: [0] ───> Item A {label="A"}, [1] ───> null
aliasArray ─┘

2) Sau items[0].rename("B"):
items ─┐
       ├──> Array X: [0] ───> Item A {label="B"}, [1] ───> null
aliasArray ─┘

3) Sau items[0] = new Item("C"):
items ─┐
       ├──> Array X: [0] ───> Item C {label="C"}, [1] ───> null
aliasArray ─┘

4) Sau items = new Item[2]:
items ───────────────> Array Y: [0]=null, [1]=null
aliasArray ──────────> Array X: [0] ───> Item C, [1]=null
```

**Phân biệt hai tầng aliasing:**

- **Alias tới mảng:** `items` và `aliasArray` từng trỏ tới **cùng Array X**, nên thay một slot của Array X qua `items[0] = ...` cũng có thể quan sát qua `aliasArray[0]`.
- **Alias tới phần tử:** hai slot có thể cùng trỏ một **Item object**, như trong ví dụ `Arrays.fill`. Thay đổi **state của Item** qua một slot sẽ quan sát qua slot kia.
- **Gán lại biến mảng:** `items = new Item[2]` không chuyển `aliasArray` sang Array Y vì phép gán chỉ thay giá trị biến `items`.

Khi lập sơ đồ, nên vẽ cả **biến tham chiếu tới mảng** lẫn **mũi tên từ mỗi slot tới element object**; chỉ vẽ một tầng mũi tên thường dẫn tới hiểu sai.

## 8. Khởi tạo ngay trong cú pháp mảng: từng `new` tạo từng object

Nếu biết trước số lượng phần tử và dữ liệu, có thể tạo mảng cùng các phần tử bằng **array initializer**:

```java
Student[] students = {
    new Student("An"),
    new Student("Binh"),
    new Student("Chi")
};
```

Cú pháp ngắn này tạo **một array object** và **ba Student objects** (vì có ba biểu thức `new Student(...)`).

Trong biểu thức thay vì ngữ cảnh khai báo, có thể dùng dạng đầy đủ:

```java
Student[] students = new Student[] {
    new Student("An"),
    null,
    new Student("Chi")
};
```

Trường hợp này tạo một array object và **chỉ hai Student objects**, còn phần tử index 1 là `null`. Cú pháp `{...}` trong khai báo mảng có phạm vi dùng riêng; ở ngữ cảnh cần một biểu thức đầy đủ (như đối số method), viết `new Student[] { ... }`.

### Array initializer cũng có thể chứa alias

```java
Student shared = new Student("Shared");
Student[] students = {shared, shared};
```

Cú pháp này **không tạo hai Student objects**. Có một `new Student` và hai slot cùng lưu một tham chiếu tới object ấy. Số phần tử = 2 nhưng số element objects được tạo ở đoạn mã chỉ = 1.

### Một ví dụ output hoàn chỉnh

Tạo tệp **`ArrayInitializerDemo.java`**:

```java
class Label {
    private final String text;

    Label(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}

public class ArrayInitializerDemo {
    public static void main(String[] args) {
        Label shared = new Label("S");
        Label[] labels = {
            new Label("A"),
            shared,
            shared,
            null
        };

        System.out.println(labels.length);
        System.out.println(labels[0].text());
        System.out.println(labels[1] == labels[2]);
        System.out.println(labels[3] == null);
    }
}
```

```bash
javac ArrayInitializerDemo.java
java ArrayInitializerDemo
```

```text
4
A
true
true
```

Mảng có **bốn phần tử tham chiếu**, nhưng đoạn mã chỉ tạo hai `Label` objects: một object `shared` và một object `"A"`. Hai slot 1 và 2 cùng tham chiếu `shared`, slot 3 là null.

## 9. Truy cập bằng chỉ số và thuộc tính `length`

Mảng Java được đánh chỉ số bắt đầu từ **0**:

```text
Student[] array = new Student[4]

Chỉ số hợp lệ:  0     1     2     3
               |     |     |     |
Slot:         null  null  null  null
```

Với mảng độ dài `n`, chỉ số hợp lệ là `0` đến `n - 1`. Độ dài đọc bằng `array.length`, **không phải** `array.length()`.

```java
Student[] students = new Student[4];

System.out.println(students.length); // 4
// students[4] = new Student("X");
// Nếu chạy: ArrayIndexOutOfBoundsException.
```

Đoạn code có thể đặt trong method; dòng lỗi runtime đã comment. Trong mảng dài 4, index 4 nằm ngoài khoảng 0..3.

Nếu độ dài tạo mảng âm:

```java
int count = -1;
// Student[] students = new Student[count];
// Nếu chạy: NegativeArraySizeException.
```

**Mảng độ dài 0 cũng hợp lệ:**

```java
Student[] empty = new Student[0];
System.out.println(empty.length); // 0
```

Không có slot phần tử và không tạo object `Student` nào, nhưng biểu thức `new Student[0]` vẫn tạo một **array object** với độ dài 0. Câu `empty[0]` sẽ vượt giới hạn chỉ số.

### Thận trọng với `array == null`

`Student[] students = null;` không có array object, nên `students.length` sẽ ném `NullPointerException`. Ngược lại, `Student[] students = new Student[0];` có array object hợp lệ, `students.length == 0` và có thể xử lý như mảng trống.

## 10. Vòng lặp for-each: đọc từng tham chiếu, không sửa slot bằng cách gán lại biến lặp

Cú pháp enhanced `for` rất thuận tiện khi chỉ cần **đọc/xử lý** các phần tử đã được khởi tạo:

```java
for (Student student : students) {
    if (student != null) {
        System.out.println(student.getName());
    }
}
```

Mỗi vòng lặp gán **giá trị phần tử** hiện tại vào một **biến cục bộ** `student`. Nếu gán lại biến này, **slot mảng không thay đổi**.

Tạo tệp **`ForEachReferenceDemo.java`**:

```java
class Badge {
    String name;

    Badge(String name) {
        this.name = name;
    }
}

public class ForEachReferenceDemo {
    public static void main(String[] args) {
        Badge[] badges = {
            new Badge("A"),
            new Badge("B")
        };

        for (Badge badge : badges) {
            badge = new Badge("X");
        }

        System.out.println(badges[0].name);
        System.out.println(badges[1].name);

        for (Badge badge : badges) {
            badge.name = "changed";
        }

        System.out.println(badges[0].name);
        System.out.println(badges[1].name);
    }
}
```

```bash
javac ForEachReferenceDemo.java
java ForEachReferenceDemo
```

**Output:**

```text
A
B
changed
changed
```

Giải thích:

- Trong vòng đầu, `badge = new Badge("X")` chỉ gán lại **biến cục bộ của vòng lặp**. Các slot `badges[0]` và `badges[1]` vẫn giữ tham chiếu ban đầu, nên sau vòng đầu vẫn in `A` và `B`. Hai object `Badge("X")` được tạo trong vòng lặp không được lưu vào mảng.
- Trong vòng thứ hai, `badge.name = "changed"` **sửa field của object** mà biến `badge` tham chiếu. Đây là object đang được slot mảng giữ tham chiếu, nên thay đổi quan sát được sau vòng lặp.

Muốn **thay phần tử mảng** bằng object mới, dùng vòng `for` theo chỉ số:

```java
for (int i = 0; i < badges.length; i++) {
    badges[i] = new Badge("X" + i);
}
```

Đây là mảnh code minh họa; nó **thực sự ghi lại từng slot**.

## 11. Truyền mảng vào method: cũng là pass-by-value

Java luôn truyền tham số bằng **giá trị**, kể cả tham số có kiểu mảng. Khi gọi một method với `Student[]`, Java sao chép **tham chiếu tới array object** vào tham số.

Method có thể:

1. **Ghi một slot** của array object đang được cả caller và callee tham chiếu.
2. **Sửa object phần tử** mà một slot trỏ tới.
3. **Gán lại biến tham số mảng** thành một mảng mới, nhưng thao tác này **không làm biến ở caller đổi tham chiếu**.

Tệp **`ArrayParameterDemo.java`**:

```java
class Score {
    int value;

    Score(int value) {
        this.value = value;
    }
}

public class ArrayParameterDemo {
    static void modify(Score[] parameter) {
        parameter[0].value += 4;
        parameter[1] = new Score(9);
        parameter = new Score[] {new Score(100)};
        System.out.println("inside length=" + parameter.length);
    }

    public static void main(String[] args) {
        Score[] scores = {new Score(1), new Score(2)};
        modify(scores);

        System.out.println("outside length=" + scores.length);
        System.out.println("first=" + scores[0].value);
        System.out.println("second=" + scores[1].value);
    }
}
```

```bash
javac ArrayParameterDemo.java
java ArrayParameterDemo
```

```text
inside length=1
outside length=2
first=5
second=9
```

Đồ thị trong lời gọi `modify`:

```text
Ban đầu:
scores ────────┐
               ├──> Array A: [0] -> Score(1), [1] -> Score(2)
parameter ─────┘

Sau parameter[0].value += 4:
scores ────────┐
               ├──> Array A: [0] -> Score(5), [1] -> Score(2)
parameter ─────┘

Sau parameter[1] = new Score(9):
scores ────────┐
               ├──> Array A: [0] -> Score(5), [1] -> Score(9)
parameter ─────┘

Sau parameter = new Score[]{new Score(100)}:
scores ─────────> Array A: [0] -> Score(5), [1] -> Score(9)
parameter ──────> Array B: [0] -> Score(100)
```

Đoạn `parameter = ...` chỉ đổi tham chiếu của **tham số local**, không thay giá trị biến `scores` ở caller. Nhưng trước đó, việc sửa slot và state phần tử của **Array A** vẫn có hiệu lực sau khi method trả về.

Nếu muốn method thay mảng của caller, hãy **trả tham chiếu mảng mới** và để caller gán: `scores = replacement(scores);`. Không nói rằng Java dùng “pass-by-reference” cho mảng theo nghĩa cho phép callee gán lại biến caller.

## 12. Sao chép mảng tham chiếu: `clone` và `Arrays.copyOf` là shallow copy

Để tạo **một array object khác** nhưng giữ cùng các object phần tử, có thể dùng `clone()` hoặc `Arrays.copyOf(...)`.

```java
Student[] original = {new Student("An"), new Student("Binh")};
Student[] copied = original.clone();
```

Sơ đồ:

```text
original ──> Array A
               [0] ──────────┐
               [1] ───────┐  |
                            |  |
copied ────> Array B        |  |
               [0] ────────+--+--> Student #0 ("An")
               [1] ────────+------> Student #1 ("Binh")
```

**Ý nghĩa chính xác:**

- `original != copied` là `true` vì có **hai array objects**.
- `original[0] == copied[0]` là `true` vì phần tử ở hai mảng vẫn tham chiếu cùng Student object.
- `copied[0] = new Student("Chi")` chỉ thay slot 0 của **Array B**; slot 0 của Array A không bị gán lại.
- Nếu `Student` mutable và gọi `copied[0].rename(...)` trước khi thay slot, object được chia sẻ có thể thay đổi và quan sát qua `original[0]`.
- Dùng `Arrays.copyOf(original, original.length)` cũng tạo **bản sao mảng nông** với tham chiếu phần tử được sao chép.

### Chương trình độc lập so sánh bản sao nông

Tệp **`ShallowCopyDemo.java`**:

```java
import java.util.Arrays;

class Note {
    String text;

    Note(String text) {
        this.text = text;
    }
}

public class ShallowCopyDemo {
    public static void main(String[] args) {
        Note[] original = {new Note("A"), new Note("B")};
        Note[] copied = Arrays.copyOf(original, original.length);

        System.out.println(original == copied);
        System.out.println(original[0] == copied[0]);

        copied[0].text = "changed";
        copied[1] = new Note("C");

        System.out.println(original[0].text);
        System.out.println(original[1].text);
        System.out.println(copied[1].text);
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
changed
B
C
```

Lý do `original[0].text` cũng thành `changed`: cả hai slot index 0 trỏ **cùng Note object**. Ngược lại, thay `copied[1]` bằng một Note mới chỉ thay slot của mảng copy, nên `original[1].text` vẫn là `B`.

### Khi nào cần deep copy?

Nếu bạn muốn hai mảng có **các object phần tử độc lập**, phải sao chép phần tử theo hợp đồng của lớp:

```java
Note[] deep = new Note[original.length];

for (int i = 0; i < original.length; i++) {
    Note source = original[i];
    deep[i] = source == null ? null : new Note(source.text);
}
```

Đây là **mảnh code** dùng `Note` của ví dụ trên. Mỗi slot có nguồn non-null tạo một `Note` mới. Tuy nhiên, **deep copy thực sự** phụ thuộc cấu trúc object: nếu một `Note` lại giữ field tham chiếu tới mutable object khác, chỉ sao chép `text` có thể chưa đủ cho đồ thị phức tạp. Phải có copy constructor hoặc phương án copy phù hợp với invariants và chính sách chia sẻ của từng lớp.

## 13. Mảng đa chiều của đối tượng: hai tầng mảng trước khi đến object phần tử

Trong Java, `Student[][]` là **mảng của các tham chiếu tới mảng `Student[]`**. Mảng đa chiều không phải một object “ma trận” không thể chia nhỏ; từng hàng là array object riêng.

### Tạo đủ cả hai chiều

```java
Student[][] classes = new Student[2][3];
```

Biểu thức này tạo:

- **Một outer array** độ dài 2.
- **Hai inner arrays**, mỗi mảng độ dài 3.
- **Không tạo Student object nào**. Sáu slot `Student` bên trong các hàng vẫn là `null`.

Sơ đồ:

```text
classes : Student[][]
   |
   v
Outer array (length 2)
   [0] ──> Row 0: [null] [null] [null]
   [1] ──> Row 1: [null] [null] [null]

Có: 1 outer array + 2 inner arrays
Chưa có: Student object nào
```

Muốn tạo Student objects:

```java
for (int row = 0; row < classes.length; row++) {
    for (int col = 0; col < classes[row].length; col++) {
        classes[row][col] = new Student("S" + row + col);
    }
}
```

Với đoạn lặp này, sáu slot được gán sáu tham chiếu tới sáu Student objects mới.

### Tạo outer array trước, hàng vẫn null

```java
Student[][] groups = new Student[2][];
```

Trường hợp này **chỉ có outer array**, và `groups[0]`, `groups[1]` mặc định `null`; chưa có inner arrays.

```text
groups ──> Outer Student[][] length=2
             [0] ----> null (chưa có row array)
             [1] ----> null (chưa có row array)
```

Phải tạo từng hàng trước khi dùng `groups[row][col]`:

```java
groups[0] = new Student[1];
groups[1] = new Student[3];

groups[0][0] = new Student("Solo");
groups[1][2] = new Student("Third");
```

Đây là **jagged array** với hàng 0 dài 1 và hàng 1 dài 3. Tất cả slot khác chưa được gán object vẫn `null`.

### Chương trình độc lập: phân biệt null hàng và null phần tử

Tệp **`TwoDimensionalStudentDemo.java`**:

```java
class Student {
    private final String name;

    Student(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }
}

public class TwoDimensionalStudentDemo {
    public static void main(String[] args) {
        Student[][] groups = new Student[2][];

        System.out.println(groups.length);
        System.out.println(groups[0] == null);

        groups[0] = new Student[2];
        groups[1] = new Student[1];

        System.out.println(groups[0][0] == null);

        groups[0][0] = new Student("Mai");
        groups[0][1] = new Student("Nam");
        groups[1][0] = new Student("Lan");

        System.out.println(groups[0].length);
        System.out.println(groups[1].length);
        System.out.println(groups[0][0].name());
        System.out.println(groups[1][0].name());
    }
}
```

```bash
javac TwoDimensionalStudentDemo.java
java TwoDimensionalStudentDemo
```

```text
2
true
true
2
1
Mai
Lan
```

Lúc `new Student[2][]` chỉ có outer array, nên `groups[0] == null` là `true`. Sau `groups[0] = new Student[2]`, hàng 0 đã tồn tại nhưng slot `groups[0][0]` vẫn null. Chỉ `new Student("Mai")` mới tạo Student object cho slot ấy.

**Hai kiểu NPE khác nhau cần phân biệt:**

- `groups[0] == null` và gọi `groups[0].length` → không có **inner array** để truy cập.
- `groups[0] != null` nhưng `groups[0][0] == null` và gọi `groups[0][0].name()` → có row array nhưng thiếu **Student object**.

## 14. Mảng object với interface, kế thừa và đa hình

Mảng kiểu tham chiếu không chỉ dành cho một concrete class. Một mảng khai báo kiểu **interface** hoặc **superclass** có thể chứa tham chiếu tới các object có runtime type phù hợp.

Tệp **`PolymorphicArrayDemo.java`**:

```java
interface Animal {
    String sound();
}

class Dog implements Animal {
    @Override
    public String sound() {
        return "woof";
    }
}

class Cat implements Animal {
    @Override
    public String sound() {
        return "meow";
    }
}

public class PolymorphicArrayDemo {
    public static void main(String[] args) {
        Animal[] animals = new Animal[3];

        animals[0] = new Dog();
        animals[1] = new Cat();
        animals[2] = new Dog();

        for (Animal animal : animals) {
            System.out.println(animal.sound());
        }
    }
}
```

```bash
javac PolymorphicArrayDemo.java
java PolymorphicArrayDemo
```

```text
woof
meow
woof
```

Điểm cần phân biệt:

- `new Animal[3]` hợp lệ vì đang tạo **mảng tham chiếu kiểu interface Animal**, không hề cố `new Animal()`.
- `new Animal()` tự nó **không hợp lệ** vì interface không thể được khởi tạo trực tiếp.
- Ba slot nhận tham chiếu tới hai `Dog` objects và một `Cat` object được tạo riêng.
- `animal.sound()` là lời gọi instance method qua interface. Java chọn implementation theo **kiểu runtime của object nhận lời gọi** khi method được override/implemented; vì thế cùng một mảng có thể chứa hành vi đa hình.
- Nếu một slot bằng null, `animal.sound()` sẽ không có receiver và ném `NullPointerException`. Cần kiểm tra null hoặc bảo đảm khởi tạo đủ.

Các biến `Animal` chỉ giữ một tham chiếu có **kiểu tĩnh `Animal`**; chúng không tạo thêm lớp wrapper Animal hay copy Dog/Cat.

## 15. Mảng là covariant: `ArrayStoreException` khi runtime type không khớp

Mảng Java của các kiểu tham chiếu có tính **covariant**. Ví dụ một `String[]` có thể được dùng ở nơi có kiểu tĩnh `Object[]`, vì `String` là subtype của `Object`:

```java
String[] names = new String[2];
Object[] objects = names;
```

Điều này không tạo array object mới: `names` và `objects` là hai biến cùng trỏ **một String[] array object**.

Nhưng runtime array type vẫn là `String[]`. Nếu qua biến `Object[]` mà gán một `Integer` vào slot, **JVM sẽ chặn tại runtime** bằng `ArrayStoreException`.

Tệp **`ArrayCovarianceDemo.java`**:

```java
public class ArrayCovarianceDemo {
    public static void main(String[] args) {
        String[] strings = new String[2];
        Object[] objects = strings;

        objects[0] = "Java";
        System.out.println(strings[0]);
        System.out.println(objects == strings);

        try {
            objects[1] = Integer.valueOf(42);
        } catch (ArrayStoreException ex) {
            System.out.println("wrong runtime element type");
        }

        System.out.println(strings[1] == null);
    }
}
```

```bash
javac ArrayCovarianceDemo.java
java ArrayCovarianceDemo
```

```text
Java
true
wrong runtime element type
true
```

Giải thích: kiểu tĩnh `Object[]` cho phép compiler chấp nhận phép gán một `Integer` trong ví dụ, nhưng array object thực tế là `String[]`. Runtime kiểm tra **kiểu thành phần** và từ chối gán Integer. Slot `strings[1]` vẫn `null` sau khi phép gán không thành công.

**Hệ quả thực tế:** mảng của lớp/interface có kiểu phần tử được kiểm tra cả **compile time** lẫn **runtime**. Dùng generic collections như `List<String>` thường tránh được một số rủi ro covariance này ở compile time, nhưng generic và array còn có quy tắc khác nhau; không nên dùng phép cast ép `Object[]` bừa bãi.

### Mảng primitive khác mảng tham chiếu

`int[]` chứa các **giá trị nguyên thủy `int`** ở các slot, không phải tham chiếu `Integer`. `Integer[]` lại chứa các **tham chiếu tới Integer objects hoặc null**. Java không tự biến `int[]` thành `Integer[]` bằng boxing:

```java
int[] primitive = new int[2];       // [0,0]
Integer[] boxed = new Integer[2];   // [null,null]
```

Hai loại mảng có ngữ nghĩa phần tử và kiểu runtime khác nhau. Đặc biệt `boxed[0]++` khi slot vẫn null có thể gây `NullPointerException` do unboxing `null`, còn `primitive[0]++` là phép tăng primitive bình thường.

## 16. `final` trên biến mảng và phần tử mảng

Nếu một biến mảng được khai báo `final`, nó không thể được **gán lại** sau khi đã được khởi tạo hợp lệ, nhưng **các slot vẫn có thể thay đổi**:

```java
final Student[] students = new Student[2];

students[0] = new Student("A");
students[0] = new Student("B"); // Hợp lệ: thay slot.

// students = new Student[3];   // Lỗi: gán lại biến final.
```

`final` ở đây bảo vệ **mũi tên từ biến `students` tới array object**, không khóa các slot bên trong array object, cũng không tự làm element objects bất biến.

Nếu cần chia sẻ dữ liệu một cách an toàn, xem xét:

- Cung cấp các getter chỉ đọc thay vì trả trực tiếp mutable array nội bộ.
- Sao chép mảng khi nhận/trả dữ liệu nếu muốn ngăn caller thay đổi **các slot** của mảng nội bộ.
- Nếu element objects cũng mutable, cân nhắc defensive copy của **từng element** hoặc thiết kế immutable elements.
- Nếu dùng mảng trong mã đa luồng, cần thêm cơ chế đồng bộ hóa/phối hợp truy cập thích hợp; `final` đơn lẻ không bảo đảm mọi mutation của slot và object an toàn.

## 17. In mảng cho dễ quan sát: không nên dựa vào địa chỉ ngẫu nhiên

Nếu viết `System.out.println(students)` với `Student[]`, Java sử dụng biểu diễn dạng text mặc định của **array object**, không tự in danh sách tên học sinh. Giá trị text mặc định thường mang thông tin kiểu và hash, không ổn định để đưa làm output mẫu.

Thay vào đó:

```java
System.out.println(java.util.Arrays.toString(students));
```

`Arrays.toString` duyệt các slot và tạo chuỗi dạng `[element0, element1, ...]`, gọi `String.valueOf` thích hợp với các tham chiếu (gồm `null`). Nếu phần tử là object tự định nghĩa chưa override `toString()`, chuỗi vẫn có thể chứa biểu diễn mặc định không đẹp. Hãy override `toString()` hoặc dùng vòng lặp gọi getter khi muốn output có ý nghĩa.

Tệp **`ArrayToStringDemo.java`**:

```java
import java.util.Arrays;

class User {
    private final String name;

    User(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return name;
    }
}

public class ArrayToStringDemo {
    public static void main(String[] args) {
        User[] users = {
            new User("An"),
            null,
            new User("Binh")
        };

        System.out.println(Arrays.toString(users));
        System.out.println(users.length);
    }
}
```

```bash
javac ArrayToStringDemo.java
java ArrayToStringDemo
```

```text
[An, null, Binh]
3
```

Có ba slot nhưng chỉ hai `User` objects được tạo trong initializer. `Arrays.toString` không tự tạo object phần tử còn thiếu; nó chỉ thể hiện slot null bằng chữ `null` khi tạo chuỗi kết quả.

Với mảng nhiều chiều, `Arrays.deepToString` thường có ích hơn `Arrays.toString` vì nó đệ quy biểu diễn nested arrays; vẫn phải cẩn trọng nếu object graph có chu kỳ phức tạp.

## 18. Khi nào nên để slot `null`, khi nào nên khởi tạo đủ?

Việc mọi phần tử ban đầu `null` **không tự là lỗi**. Tính đúng đắn phụ thuộc **hợp đồng thiết kế** của mảng:

| Mục đích | Chiến lược phù hợp | Lưu ý |
| --- | --- | --- |
| Cần đúng `n` object độc lập sẵn sàng dùng | Vòng lặp tạo `new Element(...)` cho từng index | Chi phí tạo đủ đối tượng; cần dữ liệu đầu vào hợp lệ |
| Slot biểu diễn “chưa có dữ liệu” | Để `null` và kiểm tra trước khi dùng | Tránh dereference null không kiểm soát |
| Mảng chỉ dùng làm bộ chứa tham chiếu được điền dần | `new Element[n]` rồi gán từng slot khi có dữ liệu | Theo dõi những slot đã hợp lệ |
| Cần dùng cùng sentinel object ở mọi vị trí | `Arrays.fill` với một immutable/shared sentinel | Phải chủ ý chia sẻ tham chiếu |
| Muốn sao chép danh sách vị trí nhưng giữ cùng phần tử | `array.clone()` hoặc `Arrays.copyOf` | Đây là **shallow copy** |
| Muốn mọi phần tử độc lập với nguồn | Tạo từng element object mới theo hợp đồng copy | Dễ tốn chi phí; tránh sao chép sai invariant |
| Số phần tử tăng giảm thường xuyên | Cân nhắc `ArrayList<Element>` | ArrayList vẫn giữ **tham chiếu**, không tự tạo element objects |

Không có chiến lược duy nhất cho mọi bài toán. Ví dụ một hệ thống giữ cache có thể chủ ý để slot trống; còn danh sách học sinh bắt buộc đủ `n` học sinh cần khởi tạo/validate mọi slot.

### Mảng có kích thước cố định, không có `add()` như `ArrayList`

`Student[] students = new Student[3]` có ba slot; bạn có thể điền hoặc thay các slot đó, nhưng không thể “append” phần tử thứ tư vào chính array object bằng `students.add(...)`. Nếu cần mảng lớn hơn, tạo mảng mới và sao chép tham chiếu, hoặc dùng một collection thích hợp. Lưu ý `ArrayList<Student>` cũng **không tự gọi `new Student(...)`** khi tạo list; nó chỉ chứa những object references mà bạn chủ động thêm.

## 19. Những lỗi thường gặp khi học mảng đối tượng

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`new Student[3]` gọi Student constructor ba lần” | Không: chỉ tạo một array object với ba tham chiếu null |
| “`Student[]` chứa trực tiếp ba Student objects” | Nó chứa **các tham chiếu** có thể trỏ tới Student objects |
| “Mảng không null thì mọi phần tử không null” | Array object tồn tại nhưng các slot vẫn có thể null |
| “`new Student[n]` cùng nghĩa `new Student()` lặp n lần” | Phải viết vòng lặp/initializer có `new Student(...)` riêng |
| “`Arrays.fill(a, new Student(...))` tạo n Students” | Nó đánh giá một object làm đối số rồi sao chép cùng tham chiếu vào các slot |
| “`a[0] = a[1]` sao chép object” | Nó sao chép tham chiếu, có thể tạo alias tới object |
| “`a[0].rename(...)` thay slot bằng object mới” | Đây là lời gọi method trên object đang được slot tham chiếu |
| “`a[0] = new Student(...)` sửa tên object cũ” | Nó thay tham chiếu trong slot; object cũ có thể còn alias khác |
| “`for (Student s : a) s = new Student(...)` điền mảng” | Chỉ gán lại local `s`; muốn thay slot phải gán `a[i]` |
| “`a.clone()` clone toàn bộ Student objects” | Chỉ clone array object và sao chép các tham chiếu |
| “`new Student[2][]` đã có hai mảng hàng” | Chỉ có outer array; cả hai row slots mặc định null |
| “`new Student[2][3]` đã có sáu Students” | Có outer + inner arrays, nhưng sáu Student slots null |
| “`Student[]` không thể chứa subtype instances” | Có thể lưu các subtype phù hợp theo quy tắc kiểu |
| “`Object[] x = new String[2]; x[0]=42` an toàn” | Runtime array type là String[] nên phát sinh `ArrayStoreException` |
| “`int[]` và `Integer[]` giống nhau” | Primitive values khác reference slots; `Integer[]` mặc định null |
| “`final Student[]` cấm thay phần tử” | Cấm gán lại biến final, không cấm thay các slot |
| “`array.length()` như `String.length()`” | Array dùng field `length`, String dùng method `length()` |
| “Truyền array vào method là pass-by-reference” | Java pass-by-value: bản sao giá trị tham chiếu tới mảng |
| “Phần tử null là object Student rỗng” | null là không có object đích |
| “In array bằng println tự ra tên mọi phần tử” | Nên dùng `Arrays.toString` hoặc vòng lặp + `toString`/getter |

## 20. Tự kiểm tra với đáp án

**Câu 1.** `Student[] students = new Student[5];` tạo bao nhiêu Student objects và bao nhiêu array objects?

*Đáp án:* **0 Student objects**, **1 array object** có độ dài 5 và năm slot `null`.

**Câu 2.** Sau câu trên, `students.length` trả gì? `students[0]` có giá trị gì?

*Đáp án:* `students.length == 5`; `students[0] == null` là true.

**Câu 3.** `students[0] = new Student("An"); students[1] = students[0];` đã tạo bao nhiêu Student objects?

*Đáp án:* Một Student object. Hai slot 0 và 1 cùng tham chiếu object đó.

**Câu 4.** Nếu gọi `students[1].rename("Mai")` với một Student mutable, `students[0]` có thể thấy thay đổi không?

*Đáp án:* Có, vì hai slot cùng trỏ một object. Điều kiện là `rename` thật sự sửa state object và không tạo object khác.

**Câu 5.** Sau đó `students[1] = new Student("Binh");` có sửa tham chiếu trong `students[0]` không?

*Đáp án:* Không. Slot 1 được gán sang object mới; slot 0 vẫn trỏ object trước đó.

**Câu 6.** `Arrays.fill(students, new Student("X"))` trên mảng dài 5 tạo bao nhiêu Student objects từ biểu thức new ấy?

*Đáp án:* Một. `fill` gán cùng tham chiếu vào năm slot.

**Câu 7.** Nếu muốn năm object độc lập bằng nhau về nội dung, nên viết sao?

*Đáp án:* Vòng lặp `for (int i=0;i<students.length;i++) students[i]=new Student("X");` để thực hiện `new` năm lần, hoặc một generator thực sự tạo object mới theo từng index.

**Câu 8.** `Student[][] table = new Student[2][];` có bao nhiêu inner row arrays?

*Đáp án:* Chưa có row array nào; chỉ outer array dài 2, hai row slots `null`.

**Câu 9.** `Student[][] table = new Student[2][3];` có bao nhiêu Student objects?

*Đáp án:* Không có Student object nào. Có một outer array và hai inner arrays với tổng sáu slot Student đang null.

**Câu 10.** Vì sao `for (Student s : students) s = new Student("X");` không điền lại các phần tử?

*Đáp án:* `s` là biến cục bộ nhận bản sao tham chiếu từ mỗi slot; gán `s` không cập nhật slot tương ứng.

**Câu 11.** `Student[] copy = students.clone();` có đảm bảo `copy[0] != students[0]` không?

*Đáp án:* Không. `copy` là array object khác nhưng `copy[0]` và `students[0]` vẫn giữ cùng tham chiếu lúc sao chép, trừ trường hợp dữ liệu trong các slot vốn khác theo thiết kế.

**Câu 12.** Với `Object[] values = new String[2]; values[0] = Integer.valueOf(7);`, lỗi gì?

*Đáp án:* `ArrayStoreException` ở runtime vì array object thực là `String[]` và không cho lưu Integer vào slot.

**Câu 13.** `final Student[] items = new Student[2]; items[0]=new Student("A");` có hợp lệ không?

*Đáp án:* Có. `final` cấm gán lại biến `items`, không cấm sửa phần tử mảng.

**Câu 14.** `Student[] items = null; System.out.println(items.length);` có tạo array object hoặc trả 0 không?

*Đáp án:* Không tạo array object; truy cập `length` qua tham chiếu `null` ném `NullPointerException`. `new Student[0]` mới tạo một mảng rỗng hợp lệ với `length == 0`.

**Câu 15.** Nếu method có tham số `Student[] p` rồi viết `p = new Student[10];`, mảng biến tại caller có tự đổi sang mảng mới không?

*Đáp án:* Không. `p` là bản sao giá trị tham chiếu. Caller phải nhận kết quả trả về và chủ động gán nếu muốn đổi biến caller.

## 21. Bài thực hành cuối: truy vết mảng và hai tầng aliasing

Đọc từng dòng, vẽ mũi tên và thử dự đoán output trước khi xem lời giải.

Tạo tệp **`ObjectArrayTraceDemo.java`**:

```java
class Node {
    int number;

    Node(int number) {
        this.number = number;
    }
}

public class ObjectArrayTraceDemo {
    public static void main(String[] args) {
        Node[] first = new Node[2];
        first[0] = new Node(1);
        first[1] = first[0];

        Node[] second = first;
        second[0].number += 4;

        first[1] = new Node(9);

        System.out.println(first == second);
        System.out.println(first[0] == first[1]);
        System.out.println(second[0].number);
        System.out.println(second[1].number);

        second = first.clone();
        second[0] = new Node(7);

        System.out.println(first == second);
        System.out.println(first[0].number);
        System.out.println(second[0].number);
        System.out.println(first[1] == second[1]);
    }
}
```

```bash
javac ObjectArrayTraceDemo.java
java ObjectArrayTraceDemo
```

**Kết quả:**

```text
true
false
5
9
false
5
7
true
```

**Lời giải theo sơ đồ:**

Sau `first[1] = first[0]`:

```text
first ──> Array A
            [0] ─────┐
            [1] ─────┴──> Node X {number=1}
```

Sau `Node[] second = first; second[0].number += 4`:

```text
first  ──┐
         ├──> Array A
second ──┘      [0] ────┐
                       ├──> Node X {number=5}
                 [1] ───┘
```

Sau `first[1] = new Node(9)`:

```text
first  ──┐
         ├──> Array A
second ──┘      [0] ─────────> Node X {number=5}
                 [1] ─────────> Node Y {number=9}
```

Vì `first` và `second` còn trỏ chung Array A, `first == second` là true. Slot 0 và slot 1 giờ trỏ hai Nodes khác nhau nên `first[0] == first[1]` là false. Đọc qua `second[0]` và `second[1]` trả lần lượt 5 và 9.

Sau `second = first.clone()`:

```text
first  ──> Array A              second ──> Array B
            [0] ──┐                          [0] ──┐
                  ├──> Node X {number=5}           ┘ (cùng Node X)
            [1] ──┐                          [1] ──┐
                  ├──> Node Y {number=9}           ┘ (cùng Node Y)
```

Sau `second[0] = new Node(7)`:

```text
first  ──> Array A             second ──> Array B
            [0] ──> Node X {5}             [0] ──> Node Z {7}
            [1] ─────┐                     [1] ────┐
                     └──> Node Y {9} <─────────────┘
```

Giờ `first == second` là false vì có hai array objects. `first[0].number` vẫn 5, `second[0].number` là 7, nhưng `first[1] == second[1]` vẫn true vì `clone()` chỉ sao chép các tham chiếu phần tử.

### Checklist trước khi chạy mã với mảng đối tượng

1. Đã phân biệt **biến mảng** với **array object** và **element object** chưa?
2. `new Element[n]` chỉ tạo mảng hay còn có biểu thức `new Element(...)` cho từng slot?
3. Slot nào còn `null`? Mã có kiểm tra null trước khi gọi method hay đọc field không?
4. Mỗi slot có cần một object độc lập, hay có chủ đích chia sẻ một object?
5. Có dùng `Arrays.fill` với một mutable object khiến mọi slot thành alias ngoài ý muốn không?
6. Có dùng for-each để gán lại biến lặp mà tưởng đã thay slot không?
7. Có hiểu khác biệt giữa **thay tham chiếu trong slot** và **sửa state object qua slot** không?
8. Nếu sao chép mảng, đã phân biệt **shallow copy** và **deep copy** chưa?
9. Với `Element[][]`, đã tạo **row arrays** trước khi truy cập `[row][col]` chưa?
10. Có xét đúng `length`, các chỉ số hợp lệ, `ArrayIndexOutOfBoundsException`, và `null` ở từng tầng không?
11. Nếu dùng supertype array, có hiểu runtime component type và `ArrayStoreException` không?
12. Khi truyền mảng vào method, đã nhớ Java **pass-by-value của tham chiếu** chưa?

---

**Ghi nhớ:** `new Student[3]` tạo **một mảng có ba ô tham chiếu đang null**, không tạo ba Student objects. Muốn có object ở một slot, phải gán **tham chiếu tới object đã tồn tại** hoặc tạo object bằng `new Student(...)` cho slot ấy. Nhiều slot có thể trỏ cùng object, nên thay đổi state qua một slot được quan sát qua các alias; ngược lại, gán lại một slot không tự thay các slot khác. Mảng là object có độ dài cố định, được truyền theo giá trị tham chiếu, có thể được sao chép nông và có những kiểm tra kiểu/index/null riêng. Phân biệt rõ **array object, element reference và element object** giúp đọc đúng mọi sơ đồ và tránh phần lớn lỗi khi dùng mảng đối tượng trong Java.