# Tham chiếu `final` vẫn có thể trỏ tới đối tượng thay đổi được trong Java

## 1. Ý tưởng cốt lõi: khóa biến tham chiếu, không khóa đối tượng

Trong Java, từ khóa **`final` đặt trên biến kiểu tham chiếu** có nghĩa là: **sau khi biến được gán giá trị theo quy tắc definite assignment, không thể gán lại biến đó sang một giá trị tham chiếu khác**. Nó **không tự biến object được tham chiếu thành bất biến** (*immutable*).

Xét:

```java
final StringBuilder message = new StringBuilder("Java");

message.append(" Core"); // Hợp lệ: thay đổi nội dung object.
// message = new StringBuilder("Other"); // Không hợp lệ: gán lại biến final.
```

Ở ví dụ này:

- `message` là **biến tham chiếu** được khai báo `final`.
- `new StringBuilder("Java")` tạo **một object `StringBuilder` mutable**.
- `message.append(" Core")` là **lời gọi method làm thay đổi state của object**, không phải phép gán lại biến `message`.
- Nếu bỏ comment ở phép gán `message = ...`, compiler từ chối: **biến final đã được gán không thể nhận tham chiếu mới**.

Sơ đồ trước và sau:

```text
Trước append:
message (final) ──────────> StringBuilder A {text="Java"}

Sau append:
message (final) ──────────> StringBuilder A {text="Java Core"}

Mũi tên từ biến đến object A không đổi.
Chỉ state bên trong object A thay đổi.
```

Sơ đồ thể hiện **quan hệ tham chiếu theo ngữ nghĩa Java**, không phải mô tả địa chỉ vật lý của object, ô nhớ hoặc cách JVM bố trí heap/stack.

> **Câu cần nhớ:** `final` trên reference **cấm đổi đối tượng mà biến trỏ tới bằng phép gán biến**, chứ **không cấm gọi mutating methods hoặc sửa field/array slots của đối tượng đó nếu quyền truy cập cho phép**.

## 2. Phân biệt ba lớp khái niệm: biến, tham chiếu và object

Hãy đặt từng thứ vào đúng vai trò:

| Khái niệm | Ví dụ | `final` tác động như thế nào? |
| --- | --- | --- |
| **Biến tham chiếu** | `final Box box` | Biến `box` không được gán lại sau khi đã gán |
| **Giá trị tham chiếu** | Giá trị trỏ đến một `Box` cụ thể, hoặc `null` | `final` không biến object đích thành readonly |
| **Object** | `Box` có field `count` | Object vẫn mutable nếu thiết kế cho phép sửa `count` |
| **Field của object** | `box.count` | Có thể thay đổi nếu field và quyền truy cập cho phép |
| **Mảng object** | `final Box[] boxes` | Biến `boxes` không được trỏ mảng khác; các slot mảng có thể thay |
| **Object con** | `person.address().setCity(...)` | Có thể mutate object con nếu có đường tham chiếu hợp lệ |

Cần tránh phát biểu mơ hồ “`final` làm object không thể thay đổi”. Câu đúng phụ thuộc **`final` được đặt ở đâu**:

- `final` trên **primitive variable** cấm gán lại giá trị primitive.
- `final` trên **reference variable** cấm gán lại giá trị tham chiếu.
- `final` trên **instance field** cấm gán lại field sau khi được khởi tạo đúng luật; nếu field chứa reference, object phía sau reference vẫn có thể mutable.
- `final` trên **class** ngăn kế thừa.
- `final` trên **instance method** ngăn override method theo quy tắc áp dụng.
- `final` **không phải** một cơ chế deep-freeze toàn bộ object graph.

Phạm vi bài này tập trung vào **biến/field/tham số kiểu tham chiếu có `final`**, không đánh đồng với hai trường hợp cuối.

## 3. Ví dụ Java 17+ chạy hoàn chỉnh: final reference và mutable object

Tạo tệp **`FinalReferenceDemo.java`**:

```java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void increment() {
        value++;
    }

    void add(int amount) {
        value += amount;
    }

    int value() {
        return value;
    }
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        final Counter counter = new Counter(10);

        System.out.println("before=" + counter.value());
        counter.increment();
        counter.add(4);
        System.out.println("after=" + counter.value());

        // counter = new Counter(99);
        // Bỏ comment sẽ lỗi biên dịch vì counter là final.
    }
}
```

Biên dịch và chạy:

```bash
javac FinalReferenceDemo.java
java FinalReferenceDemo
```

**Standard output:**

```text
before=10
after=15
```

Giải thích từng bước:

1. `new Counter(10)` tạo object Counter A với `value=10`.
2. `final Counter counter = ...` gán giá trị tham chiếu tới A đúng một lần.
3. `counter.increment()` tăng **state của A** từ 10 lên 11.
4. `counter.add(4)` tăng **state của A** lên 15.
5. Biến `counter` **vẫn trỏ A**, hoàn toàn không có phép `counter = ...` trong code chạy.
6. Một phép gán mới cho `counter` bị compiler từ chối, kể cả phép gán trỏ về chính object cũ.

**Điểm đáng chú ý:** `Counter.value` ở đây là `private`. Caller không được viết `counter.value = 15`; nhưng method `increment`/`add` của lớp Counter vẫn có quyền sửa state. Quyền truy cập `private` và quy tắc `final` trên biến caller là **hai cơ chế khác nhau**.

## 4. Vì sao gọi setter được nhưng gán lại biến thì không?

So sánh hai biểu thức:

```java
final Counter counter = new Counter(1);

counter.increment();        // Đúng: gọi method trên object.
// counter = new Counter(2); // Sai: thay giá trị biến counter.
```

Đoạn thứ nhất không có phép gán nào tới **biến `counter`**. Ở runtime, phương thức nhận object A làm receiver và thay field `value` của A. Đoạn thứ hai (nếu bỏ comment) sẽ gán một **giá trị tham chiếu mới** vào chính ô biến `counter`, vi phạm ràng buộc final.

Một phép gọi mutating method có thể chứa phép gán **bên trong method**, ví dụ:

```java
void increment() {
    value = value + 1;
}
```

Phép gán ở đây có đích là **field `value` của Counter object**, không phải biến final của caller.

**Mẹo phân tích:** đứng ở dấu `=` hoặc toán tử gán, hỏi “**lvalue** (vị trí được gán) nằm ở đâu?”:

- `counter = other` → gán **biến final**: không hợp lệ sau khởi tạo.
- `counter.value = 5` → gán **field của object**: có thể hợp lệ nếu field accessible và không final.
- `counter.increment()` → gọi method, có thể gián tiếp gán field: hợp lệ nếu method/receiver accessible.
- `counters[0] = other` → gán **slot mảng**, không gán biến `counters`.

Java kiểm tra **nơi bị gán**, chứ không kiểm tra “vì caller khai báo final nên bất kỳ object nào reachable cũng phải đóng băng”.

## 5. `final` và aliasing: nhiều biến cùng trỏ một object

`final` không ngăn các biến khác giữ cùng giá trị tham chiếu. Hiện tượng nhiều biến/field/slot cùng trỏ một object gọi là **aliasing**.

Ví dụ:

```java
Counter shared = new Counter(5);
final Counter left = shared;
Counter right = shared;

right.increment();

System.out.println(left.value());  // 6
```

Đây là **mảnh mã dùng lớp Counter của ví dụ trước**. Cả `left` và `right` cùng tham chiếu Counter A. Việc `left` final **không cấm** `right` gọi mutating method trên A.

Sơ đồ:

```text
shared ─────┐
left final ─┼─────────> Counter A {value=5}
right ──────┘

Sau right.increment():

shared ─────┐
left final ─┼─────────> Counter A {value=6}
right ──────┘
```

### Chương trình runnable: mutation qua alias không final

Tệp **`FinalAliasDemo.java`**:

```java
class Label {
    private String text;

    Label(String text) {
        this.text = text;
    }

    void rename(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}

public class FinalAliasDemo {
    public static void main(String[] args) {
        Label shared = new Label("old");

        final Label fixed = shared;
        Label movable = shared;

        movable.rename("updated");

        System.out.println("fixed=" + fixed.text());
        System.out.println("same=" + (fixed == movable));

        movable = new Label("new object");

        System.out.println("fixed=" + fixed.text());
        System.out.println("movable=" + movable.text());
        System.out.println("same=" + (fixed == movable));
    }
}
```

```bash
javac FinalAliasDemo.java
java FinalAliasDemo
```

```text
fixed=updated
same=true
fixed=updated
movable=new object
same=false
```

Diễn giải:

- `fixed` là final và `movable` không final, nhưng ban đầu cùng trỏ `Label A`.
- `movable.rename("updated")` mutate A; đọc qua `fixed` cũng thấy `updated`.
- `movable = new Label("new object")` chỉ **gán lại biến `movable`**, không làm `fixed` chuyển sang object mới.
- Final giới hạn phép gán **theo từng biến**, không tạo liên kết bất biến giữa mọi alias.

## 6. Gán lại chính tham chiếu cũ cũng bị cấm

Không phải chỉ “trỏ sang một object khác” mới vi phạm final. Compiler áp dụng quy tắc **gán lại biến sau khi được khởi tạo**, bất kể giá trị mới có `==` với giá trị cũ hay không.

```java
final StringBuilder b = new StringBuilder("A");

// b = b;              // Sai: vẫn là phép gán lại biến final.
// b = null;           // Sai: gán lại biến final.
// b = new StringBuilder("A"); // Sai dù text có vẻ giống.
b.append("B");         // Đúng: sửa state object.
```

Một trường hợp đáng nhớ:

```java
final StringBuilder b = null;

// b = new StringBuilder(); // Sai: b đã được gán null.
```

`null` cũng là một **giá trị hợp lệ để khởi tạo biến tham chiếu final**. Sau khi `b` được gán `null`, nó không còn được gán một object khác. Việc gọi `b.append(...)` sẽ gặp `NullPointerException` vì không có object nhận lời gọi.

**Không nói rằng `final` bảo đảm non-null.** `final` và “không thể null” là hai thuộc tính khác nhau.

## 7. Biến local `final` có thể được gán một lần về sau

Không nhất thiết phải có initializer ngay tại dòng khai báo. Với local variable, Java áp dụng quy tắc **definite assignment** và **final assignment**:

```java
final StringBuilder buffer;

if (System.currentTimeMillis() >= 0) {
    buffer = new StringBuilder("A");
} else {
    buffer = new StringBuilder("B");
}

buffer.append("!");
System.out.println(buffer);
```

Đây là **mảnh minh họa trong method**. Mỗi nhánh gán biến `buffer` một lần trên đường thực thi của nó; sau câu `if/else` biến chắc chắn được gán, nên có thể dùng. Output phụ thuộc điều kiện runtime, vì vậy đoạn này **không được trình bày như một chương trình có stdout cố định**.

Cũng cần tránh:

```java
final StringBuilder buffer = new StringBuilder("A");

// buffer = new StringBuilder("B"); // Không hợp lệ: gán lần hai.
```

**Cốt lõi:** “`final`” có nghĩa **biến được khởi tạo đúng luật rồi không gán lại**, không có nghĩa phải dùng cú pháp `final T x = ...` trên cùng một dòng trong mọi trường hợp.

## 8. Tham số `final`: không gán lại tham số, nhưng vẫn sửa object

Tham số method là **biến cục bộ thuộc lời gọi method**. Nếu khai báo `final`, không được gán lại tham số đó. Tuy nhiên, nếu tham số nhận tham chiếu tới mutable object, method vẫn có thể sửa object.

Tệp **`FinalParameterDemo.java`**:

```java
class Note {
    private String text;

    Note(String text) {
        this.text = text;
    }

    void append(String suffix) {
        text += suffix;
    }

    String text() {
        return text;
    }
}

public class FinalParameterDemo {
    static void edit(final Note note) {
        note.append("!");

        // note = new Note("other");
        // Sai: không được gán lại tham số final.
    }

    public static void main(String[] args) {
        Note note = new Note("Hello");

        edit(note);

        System.out.println(note.text());
    }
}
```

```bash
javac FinalParameterDemo.java
java FinalParameterDemo
```

```text
Hello!
```

**Vì sao caller thấy thay đổi?**

Java truyền tham số bằng **giá trị** (*pass-by-value*). Với kiểu tham chiếu, giá trị được sao chép là **giá trị tham chiếu tới cùng Note object**, không phải deep-copy Note. Biến caller và tham số final đều có thể trỏ cùng Note A, nên `note.append(...)` mutate object chung. `final` chỉ hạn chế gán lại **tham số của method**.

Nếu bỏ `final` ở tham số và gán `note = new Note("other")`, thao tác đó cũng **không gán lại biến caller**. Nhưng điều ấy là do Java pass-by-value, **không phải do `final`**.

### `final` không bảo đảm method “read-only”

Một method nhận `final List<String> values` vẫn có thể gọi `values.add(...)` nếu list mutable. Vì vậy lời hứa “method không sửa input” phải được kiểm soát bằng **contract, implementation, types và defensive copy**, không thể suy chỉ từ keyword `final`.

## 9. Trường `final` kiểu tham chiếu: field không đổi, object vẫn mutable

Một field được khai báo `final` có thể giữ tham chiếu tới mutable object:

```java
class Task {
    private final StringBuilder description;

    Task(String initial) {
        description = new StringBuilder(initial);
    }

    void addDetail(String detail) {
        description.append(detail);
    }

    String description() {
        return description.toString();
    }
}
```

Nếu `Task task = new Task("A");` rồi gọi `task.addDetail("B")`:

- Field `description` đã được khởi tạo đúng một lần trong constructor.
- Constructor và method không gán field sang `StringBuilder` khác.
- `StringBuilder` phía sau field vẫn đổi nội dung từ `A` sang `AB`.

**Phân biệt ba lớp dữ liệu:**

```text
task variable
      |
      v
Task object
   |
   +-- description [final reference] ───> StringBuilder A
                                         mutable text
```

`final` đặt trên **field tham chiếu `description`** của Task, chứ không phải trên mọi byte dữ liệu reachable từ field ấy.

### Blank final field

Một field `final` có thể không được khởi tạo ngay tại declaration:

```java
class Holder {
    private final StringBuilder content;

    Holder(String text) {
        this.content = new StringBuilder(text);
    }

    void append(String text) {
        content.append(text);
    }
}
```

Với **blank final instance field**, mọi constructor hoàn tất bình thường phải bảo đảm field được khởi tạo theo quy tắc Java. Sau đó không được gán lại `content` từ instance method. Nhưng `content.append(...)` vẫn hợp lệ.

**Điều này bảo vệ identity của đối tượng mà field giữ tham chiếu, không tự bảo vệ nội dung của đối tượng đó.**

## 10. Ví dụ Java 17+ độc lập: final field và state object

Tệp **`FinalFieldDemo.java`**:

```java
class Journal {
    private final StringBuilder text;

    Journal(String initial) {
        this.text = new StringBuilder(initial);
    }

    void write(String line) {
        text.append("|").append(line);
    }

    String read() {
        return text.toString();
    }
}

public class FinalFieldDemo {
    public static void main(String[] args) {
        final Journal journal = new Journal("start");

        journal.write("first");
        journal.write("second");

        System.out.println(journal.read());

        // journal = new Journal("new");  // Sai: biến journal final.
        // Trong Journal cũng không được gán lại field text sau khởi tạo.
    }
}
```

```bash
javac FinalFieldDemo.java
java FinalFieldDemo
```

```text
start|first|second
```

Hai lớp `final` tiềm ẩn cần phân biệt:

1. Biến cục bộ `journal` là final, không thể trỏ `Journal` object khác.
2. Field `Journal.text` cũng final, không thể trỏ `StringBuilder` object khác sau khi khởi tạo.

**Nhưng** object `StringBuilder` vẫn mutable, nên các lời gọi `journal.write(...)` thay đổi nội dung. Đóng gói thật sự đến từ việc `Journal` chỉ cho caller sửa nội dung qua method `write`; không phải từ một bảo đảm deep immutability do `final` tự sinh.

## 11. Mảng: `final T[]` không có nghĩa các phần tử final

Mảng Java là một **object**, và các phần tử của nó là những **slot có thể thay giá trị**, trừ phi có ràng buộc khác do thiết kế (mảng Java thông thường không có `final` trên từng slot chỉ vì biến mảng final).

```java
final int[] numbers = {1, 2, 3};

numbers[0] = 99;           // Hợp lệ: sửa slot 0 của mảng.
// numbers = new int[3];  // Không hợp lệ: gán lại biến final.
```

Tương tự với mảng tham chiếu:

```java
final StringBuilder[] builders = new StringBuilder[2];

builders[0] = new StringBuilder("A");  // Sửa slot của array object.
builders[0].append("B");             // Sửa element object.
builders[1] = builders[0];           // Sao chép tham chiếu sang slot khác.
```

Ở đây có **ba tầng**:

1. **Biến final `builders`** không được trỏ một array object khác.
2. **Array object** có slots `[0]`, `[1]` và những slots này vẫn có thể được gán.
3. **StringBuilder element object** cũng mutable; nhiều slots có thể cùng trỏ nó.

### Chương trình runnable: vừa thay slot, vừa mutate element

Tệp **`FinalArrayDemo.java`**:

```java
public class FinalArrayDemo {
    public static void main(String[] args) {
        final StringBuilder[] parts = new StringBuilder[2];

        parts[0] = new StringBuilder("A");
        parts[1] = parts[0];

        parts[1].append("B");

        System.out.println(parts[0]);
        System.out.println(parts[1]);
        System.out.println(parts[0] == parts[1]);

        parts[1] = new StringBuilder("C");

        System.out.println(parts[0]);
        System.out.println(parts[1]);
        System.out.println(parts[0] == parts[1]);

        // parts = new StringBuilder[3]; // Sai: final reference.
    }
}
```

```bash
javac FinalArrayDemo.java
java FinalArrayDemo
```

```text
AB
AB
true
AB
C
false
```

Giải thích:

- `parts[1] = parts[0]` tạo **alias**: hai slots cùng trỏ StringBuilder A.
- `parts[1].append("B")` sửa A nên cả hai vị trí đọc `AB`.
- `parts[1] = new StringBuilder("C")` sửa **slot 1** để trỏ object B. Slot 0 vẫn trỏ A.
- Không có bước nào gán lại **biến final `parts`**; nó luôn trỏ array object ban đầu.

**Sai lầm thường gặp:** nhìn thấy `final StringBuilder[]` rồi tưởng vừa mảng vừa các StringBuilder bên trong đều bất biến. Không đúng.

## 12. `final` trên collection reference không làm collection bất biến

Xét:

```java
final java.util.List<String> names =
        new java.util.ArrayList<>();

names.add("An");
names.add("Binh");
names.set(0, "Chi");
names.remove("Binh");

// names = new java.util.ArrayList<>(); // Sai: final.
```

Biến `names` giữ nguyên một tham chiếu tới `ArrayList`, nhưng `add`, `set` và `remove` mutate **collection object**.

Một trường hợp tương tự:

```java
final java.util.Map<String, Integer> scores =
        new java.util.HashMap<>();

scores.put("An", 10);
scores.put("An", 20);
```

`scores` final, nhưng nội dung map vẫn đổi từ `{"An":10}` thành `{"An":20}`.

### Ví dụ runnable: final list vẫn có thể thêm/xóa

Tệp **`FinalCollectionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class FinalCollectionDemo {
    public static void main(String[] args) {
        final List<String> colors = new ArrayList<>();

        colors.add("red");
        colors.add("blue");

        System.out.println("initial=" + colors);

        colors.set(0, "green");
        colors.remove("blue");

        System.out.println("updated=" + colors);

        // colors = List.of("black"); // Sai: colors final.
    }
}
```

```bash
javac FinalCollectionDemo.java
java FinalCollectionDemo
```

```text
initial=[red, blue]
updated=[green]
```

**Câu phân biệt:** “Không đổi reference của List” khác với “không đổi các phần tử List”. `final` chỉ mang nghĩa thứ nhất.

## 13. `static final` collection vẫn có thể bị sửa và được chia sẻ rộng

Đây là một cạm bẫy thiết kế API:

```java
public final class SharedNames {
    public static final java.util.List<String> NAMES =
            new java.util.ArrayList<>();

    private SharedNames() {
    }
}
```

Dù `NAMES` là `public static final`:

- `static`: field thuộc về class, không phải từng instance.
- `final`: field không thể được gán lại từ những nơi không có quyền gán theo quy tắc.
- `public`: nhiều callers có thể nhìn thấy reference.
- **Object `ArrayList` vẫn mutable**: caller có thể gọi `SharedNames.NAMES.add("X")`.

**Hậu quả:** các thành phần khác trong cùng tiến trình có thể quan sát dữ liệu thay đổi bất ngờ; tests có thể làm ô nhiễm trạng thái của nhau; nhiều thread có thể truy cập không an toàn nếu thiếu đồng bộ.

Một lựa chọn cho danh sách giá trị cố định:

```java
public final class SharedNames {
    public static final java.util.List<String> NAMES =
            java.util.List.of("An", "Binh");

    private SharedNames() {
    }
}
```

`List.of` trả về list **unmodifiable**, nên `NAMES.add(...)` ném `UnsupportedOperationException` thay vì sửa structure của list. Tuy nhiên **unmodifiable collection không đồng nghĩa deep immutability của mọi element object**. Trong ví dụ phần tử `String` immutable nên dễ suy luận.

**Đừng nhầm:** `static final` phù hợp cho một hằng reference, nhưng muốn bảo vệ cả giá trị reachable phải xét **kiểu và implementation object được tham chiếu**.

## 14. `final` khác `Collections.unmodifiableList`

`Collections.unmodifiableList(source)` tạo một **view không cho phép thao tác thay đổi qua view**. Nhưng nếu `source` là một list mutable và có alias khác, view có thể phản ánh các thay đổi được thực hiện qua nguồn.

Ví dụ:

```java
java.util.List<String> source = new java.util.ArrayList<>();
source.add("A");

final java.util.List<String> view =
        java.util.Collections.unmodifiableList(source);

source.add("B");

System.out.println(view); // [A, B]
```

Đây là **mảnh code minh họa trong method**.

Hai ý độc lập:

- `view` final: không gán lại biến `view`.
- `view` unmodifiable: không thể gọi thành công `view.add("C")` theo contract view.
- Nhưng `source.add("B")` thay đổi list nền; `view` có thể thấy dữ liệu mới.

### Chương trình đầy đủ minh họa alias và view

Tệp **`UnmodifiableViewDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class UnmodifiableViewDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        final List<String> view =
                Collections.unmodifiableList(source);

        System.out.println("before=" + view);

        source.add("B");
        System.out.println("after source change=" + view);

        try {
            view.add("C");
        } catch (UnsupportedOperationException ex) {
            System.out.println("view cannot add");
        }

        System.out.println("source=" + source);
    }
}
```

```bash
javac UnmodifiableViewDemo.java
java UnmodifiableViewDemo
```

```text
before=[A]
after source change=[A, B]
view cannot add
source=[A, B]
```

**Kết luận:** muốn gọi một biến là “read-only” phải nêu rõ **đọc qua reference nào**, **object có được chia sẻ với alias khác không**, và **cần snapshot hay view sống**. `final` riêng lẻ không giải quyết những câu hỏi này.

## 15. `List.copyOf`: tách structure của list, nhưng là shallow copy về elements

Trong Java 17+, `List.copyOf(collection)` trả một unmodifiable list chứa các phần tử tương ứng tại thời điểm tạo. Với nguồn mutable list thông thường, nó tạo một **bản sao snapshot về cấu trúc** (implementation có thể tái sử dụng đối tượng nguồn nếu nguồn đã là immutable phù hợp theo contract).

Ví dụ:

```java
java.util.List<String> source = new java.util.ArrayList<>();
source.add("A");

final java.util.List<String> snapshot = java.util.List.copyOf(source);

source.add("B");

System.out.println(snapshot); // [A]
System.out.println(source);   // [A, B]
```

Ở đây `snapshot` không tự biến thành `[A, B]` khi source list mutable được thêm phần tử mới sau đó.

**Nhưng:** nếu elements là mutable objects, `List.copyOf` **không deep-copy từng object**. Đó vẫn là các giá trị tham chiếu phần tử, có thể chia sẻ.

### Ví dụ chạy: snapshot structure nhưng element mutable chung

Tệp **`ShallowSnapshotDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Task {
    String title;

    Task(String title) {
        this.title = title;
    }

    @Override
    public String toString() {
        return title;
    }
}

public class ShallowSnapshotDemo {
    public static void main(String[] args) {
        List<Task> source = new ArrayList<>();
        Task shared = new Task("Draft");
        source.add(shared);

        final List<Task> snapshot = List.copyOf(source);

        source.add(new Task("Review"));
        shared.title = "Updated";

        System.out.println("source=" + source);
        System.out.println("snapshot=" + snapshot);
        System.out.println("same element=" +
                (source.get(0) == snapshot.get(0)));
    }
}
```

```bash
javac ShallowSnapshotDemo.java
java ShallowSnapshotDemo
```

```text
source=[Updated, Review]
snapshot=[Updated]
same element=true
```

Đọc từng khác biệt:

- `source.add(new Task("Review"))` mutate **source list structure**, không thêm slot vào snapshot.
- `shared.title = "Updated"` mutate **Task object chung** được cả hai list tham chiếu, nên `snapshot` in `Updated`.
- `final List<Task> snapshot` không làm `Task` objects immutable.

**Cảnh báo:** `List.copyOf` không chấp nhận phần tử null theo contract; nếu cần giữ nulls, chọn chiến lược khác và mô tả rõ. Với source mutable bị thay đồng thời không có đồng bộ, cũng phải xét thread-safety và snapshot consistency.

## 16. Bản sao phòng vệ (*defensive copy*) và quyền sở hữu đối tượng

Một class có field `private final List<...>` có vẻ đã đóng gói, nhưng nếu giữ trực tiếp tham chiếu input, caller vẫn có thể mutate cùng object.

Ví dụ:

```java
class UnsafeTeam {
    private final java.util.List<String> members;

    UnsafeTeam(java.util.List<String> members) {
        this.members = members;
    }

    int size() {
        return members.size();
    }
}
```

Nếu caller tiếp tục `input.add(...)`, field `members` của `UnsafeTeam` vẫn trỏ **cùng input list**, vì constructor chỉ gán tham chiếu. Việc field final không ngăn alias ở caller sửa list.

Thiết kế phòng vệ:

```java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> source) {
        this.members = java.util.List.copyOf(source);
    }

    java.util.List<String> members() {
        return members;
    }
}
```

Với `String` elements immutable và input không null, dùng `List.copyOf` tạo unmodifiable snapshot phù hợp. Caller không thể thêm/bớt phần tử qua getter hoặc qua list nguồn để thay structure nội bộ. Nhưng với `List<MutablePerson>`, phải quyết định **có cần defensive copy từng MutablePerson không**.

### Ví dụ đầy đủ: field final + copy input

Tệp **`DefensiveFinalFieldDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

class Team {
    private final List<String> names;

    Team(List<String> source) {
        names = List.copyOf(source);
    }

    List<String> names() {
        return names;
    }
}

public class DefensiveFinalFieldDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        final Team team = new Team(input);

        input.add("Binh");

        System.out.println("input=" + input);
        System.out.println("team=" + team.names());

        try {
            team.names().add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("team list unmodifiable");
        }
    }
}
```

```bash
javac DefensiveFinalFieldDemo.java
java DefensiveFinalFieldDemo
```

```text
input=[An, Binh]
team=[An]
team list unmodifiable
```

Ở đây có **hai final references** ở hai nơi:

1. Biến local `team` final, không gán lại Team object.
2. Field `Team.names` final, không gán sang list khác.

Quan trọng hơn, chính **object list nội bộ** được thiết kế unmodifiable và tạo từ một snapshot riêng. **Tính bất biến quan sát được** trong ví dụ xuất phát từ phối hợp **immutable element type (`String`)**, **snapshot** và **không phơi bày mutable state**, không phải chỉ hai từ khóa final.

## 17. Getter trả tham chiếu tới mutable field: `final` không thay thế encapsulation

Giả sử:

```java
class EventLog {
    private final StringBuilder log = new StringBuilder();

    StringBuilder getLog() {
        return log;
    }
}
```

Getter `getLog()` trả **chính reference** đang được field final `log` giữ. Nếu caller gọi:

```java
EventLog event = new EventLog();
event.getLog().append("injected");
```

caller mutate nội dung **StringBuilder của EventLog** dù field `log` là `private final`.

Một API an toàn hơn có thể:

- Chỉ trả **String snapshot** bằng `return log.toString();`.
- Cung cấp methods có kiểm tra hợp đồng để thêm log entry.
- Nếu cần mutable objects phức tạp, trả defensive copy thay vì internal reference.
- Nếu nhiều thread, quản lý synchronization/visibility theo contract.

**`private` cấm truy cập field trực tiếp từ class không có quyền, `final` cấm gán lại field; cả hai đều không cấm mọi thao tác gián tiếp lên object được field tham chiếu nếu API làm rò rỉ reference.**

## 18. Ví dụ Java 17+: trả snapshot thay vì mutable reference

Tệp **`SafeLogDemo.java`**:

```java
class EventLog {
    private final StringBuilder content = new StringBuilder();

    void append(String event) {
        if (event == null || event.isBlank()) {
            throw new IllegalArgumentException("event required");
        }
        if (content.length() > 0) {
            content.append("|");
        }
        content.append(event);
    }

    String snapshot() {
        return content.toString();
    }
}

public class SafeLogDemo {
    public static void main(String[] args) {
        final EventLog log = new EventLog();

        log.append("start");

        String captured = log.snapshot();
        log.append("done");

        System.out.println("captured=" + captured);
        System.out.println("current=" + log.snapshot());
    }
}
```

```bash
javac SafeLogDemo.java
java SafeLogDemo
```

```text
captured=start
current=start|done
```

Tại sao `captured` không đổi? `snapshot()` tạo/cho ra một giá trị `String` bất biến đại diện nội dung tại thời điểm gọi. `log.append("done")` mutate `StringBuilder` nội bộ, không mutate String `captured`. Lưu ý đây là demo **đơn luồng**; `StringBuilder` không tự thread-safe nếu nhiều threads cùng gọi `append` và `snapshot`.

Phân biệt ý nghĩa của hai APIs:

- `StringBuilder getMutableContent()` (nếu tồn tại) làm lộ mutable reference.
- `String snapshot()` chỉ trả một giá trị có nội dung tại thời điểm gọi.

Thiết kế API nên nói rõ có trả **live mutable view** hay **snapshot**.

## 19. `final` và immutable objects: hai tính chất độc lập

Có hai ví dụ đối xứng quan trọng:

**Reference final tới mutable object:**

```java
final StringBuilder builder = new StringBuilder("A");
builder.append("B"); // Object đổi thành "AB".
```

**Reference không final tới immutable object:**

```java
String text = "A";
text = text + "B";    // Biến text đổi sang giá trị String mới.
```

Trong ví dụ đầu, **biến không đổi**, object đổi. Trong ví dụ sau, **biến có thể đổi**, object `String` cũ không bị mutate.

| Reference variable | Object được tham chiếu | Ví dụ hành vi |
| --- | --- | --- |
| final | mutable | `final StringBuilder b`; `b.append(...)` hợp lệ |
| không final | mutable | Có thể gán lại biến **và** mutate object |
| final | immutable | Không gán lại biến; object không có API mutable |
| không final | immutable | Có thể gán biến sang immutable object khác; object cũ không bị mutate |

**Bất biến (immutability) là thuộc tính của kiểu/implementation/object graph**, còn `final` trên reference là **hạn chế gán một biến cụ thể**. Đây là hai trục độc lập.

## 20. String và StringBuilder: ví dụ tương phản dễ nhớ

Tệp **`FinalStringVsBuilderDemo.java`**:

```java
public class FinalStringVsBuilderDemo {
    public static void main(String[] args) {
        final String text = "Hi";
        final StringBuilder builder = new StringBuilder("Hi");

        String next = text.concat("!");
        builder.append("!");

        System.out.println("text=" + text);
        System.out.println("next=" + next);
        System.out.println("builder=" + builder);

        // text = next; // Không hợp lệ: final String variable.
        // builder = new StringBuilder(); // Không hợp lệ.
    }
}
```

```bash
javac FinalStringVsBuilderDemo.java
java FinalStringVsBuilderDemo
```

```text
text=Hi
next=Hi!
builder=Hi!
```

Giải thích:

- `String.concat` trả một String result; không thay nội dung của String object `text`.
- Vì `text` final, không thể gán nó sang `next`. Giá trị `text` vẫn là `Hi`.
- `StringBuilder.append` mutate builder object mà `builder` tham chiếu; biến final `builder` vẫn giữ reference cũ.

Đừng nghĩ chỉ có `final String` mới làm String immutable. **Ngay cả `String` không final cũng là immutable object**; sự khác biệt nằm ở khả năng **gán lại biến**.

## 21. Object có field `final` nhưng chứa mutable object con

Một object có thể có nhiều field `final` mà vẫn không được xem là immutable nếu một field trỏ tới mutable object hoặc có method thay đổi object con.

Ví dụ:

```java
class Profile {
    private final String id;
    private final StringBuilder notes;

    Profile(String id) {
        this.id = id;
        this.notes = new StringBuilder();
    }

    void addNote(String text) {
        notes.append(text);
    }

    String notes() {
        return notes.toString();
    }
}
```

Cả hai fields đều final, nhưng `Profile.addNote` mutate `StringBuilder` object, nên **state quan sát được của Profile có thể thay đổi**.

### Shallow immutability và deep immutability

- **Shallow**: field references không đổi, nhưng objects reachable từ chúng có thể đổi.
- **Deep**: toàn bộ state được coi là thành phần bất biến của object **không thể bị đổi qua những đường truy cập hợp lệ**, bao gồm mutable elements/objects con theo contract.

Trong thực hành, deep immutability thường cần:

1. Không cung cấp mutating methods trên object được thiết kế immutable.
2. Final fields cho các thành phần state thích hợp.
3. Immutable primitive/value components khi có thể.
4. Defensive copy của mutable arguments vào constructor.
5. Không trả mutable references nội bộ qua getter.
6. Copy hoặc wrap thích hợp cho collections/arrays.
7. Không để `this` escape trong lúc khởi tạo.

**Chỉ thêm `final` vào mọi field không tự đáp ứng đủ danh sách ấy.**

## 22. Record trong Java 17+ cũng có thể chứa mutable reference

Java records có các component fields với những quy tắc final riêng, nhưng một record chứa mutable object như `StringBuilder` vẫn có thể bộc lộ mutation.

Tệp **`RecordMutabilityDemo.java`**:

```java
record NoteRecord(StringBuilder text) {
}

public class RecordMutabilityDemo {
    public static void main(String[] args) {
        StringBuilder original = new StringBuilder("A");

        final NoteRecord note = new NoteRecord(original);

        original.append("B");
        System.out.println(note.text());

        note.text().append("C");
        System.out.println(original);

        // note = new NoteRecord(new StringBuilder("X"));
        // Không hợp lệ: biến note final.
    }
}
```

```bash
javac RecordMutabilityDemo.java
java RecordMutabilityDemo
```

```text
AB
ABC
```

Nhận xét:

- Record `NoteRecord` giữ field reference cho component `text` theo cơ chế của record; field ấy không được gán lại sau khi khởi tạo.
- `original` và `note.text()` giữ tham chiếu tới cùng `StringBuilder`, nên cả hai đường có thể mutate object ấy.
- Biến `note` cũng final, nhưng hai tầng final vẫn **không làm StringBuilder immutable**.

**Cách cải thiện:** nếu contract yêu cầu record immutable, dùng component kiểu immutable như `String`, hoặc defensive copy và accessor trả bản copy cho các thành phần mutable. Khi thiết kế record chứa array/list, đừng mặc định record đã deep-freeze chúng.

## 23. `final` trên reference không tự bảo đảm thread safety

Một field `final` có thể giúp triển khai các quy tắc khởi tạo/an toàn công bố của Java Memory Model đối với chính field và những hiệu ứng liên quan khi object được xây dựng đúng cách. Tuy nhiên, **không thể từ đó suy ra rằng các mutation xảy ra sau constructor trở thành thread-safe**.

Ví dụ:

```java
class SharedCounter {
    private final int[] counts = {0};

    void increment() {
        counts[0]++;
    }

    int count() {
        return counts[0];
    }
}
```

`counts` là field tham chiếu final, không được gán lại sau khi khởi tạo. Nhưng slot `counts[0]` vẫn là giá trị `int` mutable trong array object. Hai threads cùng gọi `increment()` có thể gây **lost update** vì `counts[0]++` là thao tác read-modify-write, không được biến thành atomic chỉ bởi final field.

**Đừng nhầm các bảo đảm:**

- **Final field semantics**: có những quy tắc đặc thù cho khởi tạo/visibility của final fields khi object không bị công bố sai cách trong constructor.
- **Thread-safe mutation**: đòi hỏi đồng bộ/atomic operations đúng cho những state được thay đổi sau khi object được công bố.
- **Deep immutability**: một kiểu không cho state quan sát được thay đổi theo hợp đồng, khác cả hai điều trên.

Với shared mutable state, cân nhắc `synchronized`, `Lock` hoặc `AtomicInteger`; các readers và writers phải phối hợp theo cùng cơ chế. Không dùng `final` như một “khóa” bảo vệ phép tăng.

### Ví dụ dùng `AtomicInteger` với final reference

Tệp **`FinalAtomicDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class FinalAtomicDemo {
    private final AtomicInteger counter = new AtomicInteger();

    void increment() {
        counter.incrementAndGet();
    }

    int value() {
        return counter.get();
    }

    public static void main(String[] args) {
        final FinalAtomicDemo demo = new FinalAtomicDemo();

        demo.increment();
        demo.increment();

        System.out.println(demo.value());
    }
}
```

```bash
javac FinalAtomicDemo.java
java FinalAtomicDemo
```

```text
2
```

Ở đây field `counter` là final reference **và** object `AtomicInteger` **chủ động mutable**; method `incrementAndGet` cung cấp phép cập nhật nguyên tử theo contract atomic type. `final` ngăn thay cả AtomicInteger object bằng reference mới; nó không cần thiết để method atomic kia hoạt động đúng về nguyên tử.

**Ngược lại:** `final AtomicInteger` không đảm bảo mọi thao tác phức tạp như “đọc hai biến atomic rồi kiểm điều kiện” đều nguyên tử như một transaction. Thiết kế concurrency phải dựa trên contract của từng tổ hợp hành vi.

## 24. Biến `final` không ngăn method khác mutate object thông qua alias

Kể cả khi một method chỉ nhận tham số không final, nếu nó được truyền một object mà caller đang giữ bằng biến final, method vẫn có thể sửa object.

```java
static void update(StringBuilder text) {
    text.append("!");
}
```

Caller:

```java
final StringBuilder buffer = new StringBuilder("Hi");

update(buffer);

System.out.println(buffer); // Hi!
```

Đây là **các mảnh mã** đặt trong class/method hợp lệ.

Sơ đồ:

```text
Caller:
buffer (final) ───────┐
                      ├────> StringBuilder A ("Hi")
Method:
text (parameter) ─────┘

Sau text.append("!"):
buffer (final) ───────┐
                      ├────> StringBuilder A ("Hi!")
text ─────────────────┘
```

**Khác biệt với `final StringBuilder text` ở tham số:** thêm `final` vào tham số chỉ cấm method viết `text = other`; nó không cấm `text.append(...)`. Caller cũng không “truyền tham chiếu theo reference” theo nghĩa cho phép callee gán lại biến caller; Java vẫn **pass-by-value của giá trị tham chiếu**.

## 25. So sánh phương thức thay state và phương thức trả object mới

Khi thiết kế API, bạn có thể chọn:

**Mutating API:**

```java
class MutablePoint {
    int x;
    int y;

    void move(int dx, int dy) {
        x += dx;
        y += dy;
    }
}
```

`final MutablePoint p = new MutablePoint(); p.move(1,2);` hợp lệ: object state đổi.

**Immutable value API:**

```java
record Point(int x, int y) {
    Point moved(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}
```

Caller có thể viết:

```java
final Point original = new Point(0, 0);
Point moved = original.moved(1, 2);
```

`original` final và `Point` immutable về hai primitive components nên original giữ giá trị cũ, còn `moved` là record instance mang state mới.

**Lưu ý:** phép `x + dx` trên `int` có thể overflow. Nếu cần contract loại trừ overflow, dùng `Math.addExact`. Đây là vấn đề **đúng đắn phép tính**, độc lập với việc reference final hay không.

### Ví dụ runnable so sánh hai API

Tệp **`MutationVsImmutableDemo.java`**:

```java
class MutablePoint {
    private int x;
    private int y;

    MutablePoint(int x, int y) {
        this.x = x;
        this.y = y;
    }

    void move(int dx, int dy) {
        x += dx;
        y += dy;
    }

    String location() {
        return x + "," + y;
    }
}

record Point(int x, int y) {
    Point moved(int dx, int dy) {
        return new Point(x + dx, y + dy);
    }
}

public class MutationVsImmutableDemo {
    public static void main(String[] args) {
        final MutablePoint mutable = new MutablePoint(1, 2);
        mutable.move(3, 4);

        final Point immutable = new Point(1, 2);
        Point moved = immutable.moved(3, 4);

        System.out.println("mutable=" + mutable.location());
        System.out.println("original=" + immutable);
        System.out.println("moved=" + moved);
    }
}
```

```bash
javac MutationVsImmutableDemo.java
java MutationVsImmutableDemo
```

```text
mutable=4,6
original=Point[x=1, y=2]
moved=Point[x=4, y=6]
```

Vì `Point` là record có primitive components, record instances trong ví dụ không có mutable referenced component. `MutablePoint` thay đổi state object dù caller dùng final reference; `Point.moved` trả một object mới.

## 26. `final` không bảo đảm side-effect-free hoặc rollback khi lỗi

Giả sử:

```java
static void update(final java.util.List<String> names) {
    names.add("A");

    if (names.size() > 3) {
        throw new IllegalStateException("too many names");
    }
}
```

Đây là mảnh method minh họa. Nếu `names` là mutable list đã có ba phần tử, method:

1. **Thêm phần tử thứ tư**.
2. Sau đó kiểm tra và ném exception.
3. Caller nhận exception, **nhưng list đã bị sửa**.

`final` trên tham số hoàn toàn không khắc phục lỗi **partial mutation** này.

Cách an toàn hơn khi biết capacity và input:

```java
static void addIfRoom(final java.util.List<String> names, String value) {
    if (names.size() >= 3) {
        throw new IllegalStateException("too many names");
    }
    names.add(value);
}
```

Với nhiều bước có thể lỗi, có thể cân nhắc **copy → validate → commit** hoặc dữ liệu immutable. Nếu nhiều thread cùng mutate list, cần cơ chế đồng bộ riêng cho check-and-update để tránh TOCTOU.

**Đừng gọi một method là “read-only” chỉ vì tham số của nó khai báo final.** Muốn có contract không mutate, phải xem implementation, kiểu object và khả năng chia sẻ alias.

## 27. `final`, quyền truy cập và encapsulation: áp dụng đúng vai trò

Một thiết kế dữ liệu có thể phối hợp:

- **`private` field**: hạn chế nơi source code được trực tiếp truy cập field.
- **`final` field**: bảo đảm field không bị gán lại sau khởi tạo hợp lệ.
- **Immutable implementation/value type**: hạn chế chính object đổi state.
- **Defensive copy**: tránh caller giữ alias tới mutable internal data.
- **Controlled mutator methods**: cung cấp thay đổi được kiểm tra invariant.
- **Synchronization/atomic APIs**: kiểm soát truy cập đồng thời khi cần.

Không có một modifier duy nhất thay thế tất cả.

Ví dụ:

```java
class BankAccount {
    private final String accountId;
    private int balance;

    BankAccount(String accountId, int balance) {
        if (accountId == null || accountId.isBlank() || balance < 0) {
            throw new IllegalArgumentException("invalid account");
        }
        this.accountId = accountId;
        this.balance = balance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("invalid amount");
        }
        balance = Math.addExact(balance, amount);
    }

    int balance() {
        return balance;
    }

    String accountId() {
        return accountId;
    }
}
```

Ở đây `accountId` là final String reference tới immutable String; trong hợp đồng ứng dụng, ID không đổi sau construction. `balance` không final vì số dư được thiết kế thay đổi qua `deposit`. Đây có thể là thiết kế **rõ nghĩa hơn** so với việc cố gán mọi thứ final nhưng giấu số dư trong một mutable array/object con chỉ để có thể mutate.

**Chọn final theo ý nghĩa dữ liệu**, không tìm cách “bôi final lên mọi khai báo” nếu điều đó khiến mô hình trạng thái rối hơn.

## 28. Những ngộ nhận phổ biến

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “`final Object obj` làm object bất biến” | Chỉ cấm gán lại biến `obj` |
| “`obj.method()` bị cấm nếu method sửa state” | Vẫn được nếu method accessible và object mutable |
| “Gọi setter nghĩa gán lại final variable” | Setter sửa state object; biến reference không đổi |
| “`final` cấm mọi phép gán có dấu `=` liên quan tới object” | Nó cấm gán lại chính biến/field final, không tự cấm ghi field khác |
| “`final` ngăn alias khác sửa object” | Nhiều alias cùng trỏ mutable object và có thể mutate |
| “Gán lại cùng tham chiếu cũ là hợp lệ” | Gán lại biến final vẫn sai kể cả giá trị `==` ban đầu |
| “Biến final không thể null” | Nó có thể được khởi tạo bằng `null` và không gán lại |
| “`final T[]` biến array slots thành final” | Các slots vẫn có thể thay |
| “`final List` tương đương `List.of`” | `final` trên biến không thay implementation của List |
| “`public static final List` luôn immutable” | List object mutable vẫn có thể bị thay qua reference công khai |
| “`Collections.unmodifiableList` là deep immutable snapshot” | Nó là unmodifiable view; source alias có thể thay dữ liệu nền |
| “`List.copyOf` deep-copy mọi element” | Không; references tới mutable elements vẫn có thể được chia sẻ |
| “`private final List` không bị caller thay đổi” | Nếu constructor/getter lộ alias tới mutable list, caller có thể mutate list |
| “Record có final fields nên mọi component objects immutable” | Record có thể chứa mutable objects |
| “`final String` và `final StringBuilder` đều bất biến như nhau” | String immutable; StringBuilder mutable |
| “`final` parameter ngăn method sửa đối số” | Chỉ ngăn gán lại tham số, không cấm mutate object chung |
| “`final` field tự bảo đảm thread safety” | Mutation sau construction vẫn cần cơ chế concurrent access phù hợp |
| “`final AtomicInteger` không thể tăng được” | Reference không gán lại; AtomicInteger object được thiết kế để cập nhật |
| “`final` làm exception tự rollback mutation” | Exception không tự hoàn tác field/list updates |
| “`final class` và `final reference` là một quy tắc” | Final class cấm kế thừa; final variable cấm gán lại |
| “Chỉ cần final fields để xây immutable class” | Cần xem mutable object graph, constructors, getters và copy policy |

## 29. Bài tập truy vết tham chiếu: dự đoán output

Tạo **`FinalReferenceTraceDemo.java`**:

```java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

public class FinalReferenceTraceDemo {
    static void increase(final Box target) {
        target.value += 3;

        // target = new Box(99); // Sai: final parameter.
    }

    public static void main(String[] args) {
        final Box first = new Box(2);
        Box second = first;

        increase(first);
        second.value *= 2;

        System.out.println("first=" + first.value);
        System.out.println("second=" + second.value);
        System.out.println("same=" + (first == second));

        second = new Box(100);

        System.out.println("first=" + first.value);
        System.out.println("second=" + second.value);
        System.out.println("same=" + (first == second));
    }
}
```

```bash
javac FinalReferenceTraceDemo.java
java FinalReferenceTraceDemo
```

```text
first=10
second=10
same=true
first=10
second=100
same=false
```

### Từng bước diễn ra

```text
A = Box object {value=2}

first (final) ──┐
                ├──────> A {value=2}
second ─────────┘

increase(first):
target (final parameter) ────> A
A.value += 3                  => A.value=5

second.value *= 2:
A.value=10

second = new Box(100):
first (final) ────────────────> A {value=10}
second ───────────────────────> B {value=100}
```

Quan sát:

- `increase` có tham số final nhưng vẫn mutate Box A từ 2 lên 5.
- `second.value *= 2` mutate A lên 10 vì đang alias.
- `second = new Box(100)` không thể khiến `first` đổi tham chiếu, vì phép gán chỉ tác động biến `second`.
- `final` của `first` cấm caller viết `first = B`, không cấm B/A cùng tồn tại hoặc object A thay state.

## 30. Câu hỏi tự kiểm tra kèm đáp án

**Câu 1.** `final StringBuilder b = new StringBuilder("A"); b.append("B");` có hợp lệ không?

*Đáp án:* Có. Biến `b` không bị gán lại; StringBuilder object được mutate.

**Câu 2.** `final StringBuilder b = new StringBuilder("A"); b = b;` có hợp lệ không?

*Đáp án:* Không. Phép `b = b` vẫn là gán lại biến final đã được khởi tạo.

**Câu 3.** `final List<String> values = new ArrayList<>(); values.add("A");` có hợp lệ không?

*Đáp án:* Có. `ArrayList` là mutable list; `final` chỉ giới hạn reference variable.

**Câu 4.** `final int[] nums = {1,2}; nums[0] = 9;` có hợp lệ không?

*Đáp án:* Có. Mảng là object mutable, slot 0 thay đổi; biến `nums` vẫn trỏ mảng cũ.

**Câu 5.** `final String text = "A"; text.concat("B");` có đổi nội dung `text` không?

*Đáp án:* Không. String immutable; `concat` trả kết quả String mới (trừ các tối ưu không thay đổi ngữ nghĩa). Nếu bỏ kết quả, `text` vẫn là `A`.

**Câu 6.** Nếu một `final Person p` và một `Person q` cùng trỏ một mutable Person object, `q.rename(...)` có thể ảnh hưởng `p.name()` không?

*Đáp án:* Có, nếu `rename` mutate cùng Person object và `name()` đọc state đó.

**Câu 7.** `final Person p = null; p = new Person();` hợp lệ không?

*Đáp án:* Không. Biến đã được khởi tạo `null`; không được gán lại.

**Câu 8.** `final Person p; p = new Person();` có hợp lệ với biến cục bộ không?

*Đáp án:* Có nếu `p` được gán đúng một lần theo definite-assignment rules và không bị đọc trước khi gán.

**Câu 9.** `private final List<Person> people` có bảo đảm object graph immutable không?

*Đáp án:* Không. Field không gán lại nhưng list hoặc Person elements có thể mutable, đặc biệt nếu chia sẻ aliases.

**Câu 10.** Một method nhận `final List<String> items` có được `items.clear()` không?

*Đáp án:* Có về cú pháp/ý nghĩa `final`; có thành công runtime hay không phụ thuộc implementation của List (unmodifiable list có thể ném `UnsupportedOperationException`).

**Câu 11.** `Collections.unmodifiableList(source)` có chắc chắn là một snapshot tách khỏi `source` không?

*Đáp án:* Không. Đây là view; nếu nguồn thay đổi qua alias khác, view có thể phản ánh thay đổi đó.

**Câu 12.** `List.copyOf(source)` có sao chép sâu mọi mutable element không?

*Đáp án:* Không. Nó không tự deep-copy element objects.

**Câu 13.** Một record chứa `StringBuilder` có tự deep immutable không?

*Đáp án:* Không. Component reference có quy tắc final nhưng StringBuilder có thể bị mutate từ alias.

**Câu 14.** `final AtomicInteger count = new AtomicInteger(); count.incrementAndGet();` có hợp lệ không?

*Đáp án:* Có. Reference final và mutable atomic object là hai chuyện khác nhau.

**Câu 15.** `final` trên field tham chiếu có tự thay thế `synchronized`/atomic operations không?

*Đáp án:* Không. Các mutation sau khi object khởi tạo cần concurrency control theo contract.

**Câu 16.** Muốn một class thật sự immutable khi có field `List<String>`, cần thêm gì ngoài `final`?

*Đáp án:* Thiết kế list unmodifiable và snapshot phù hợp ở constructor/getter; với String elements immutable thì đủ cho phần này. Nếu elements mutable, còn cần bảo vệ các elements.

**Câu 17.** `final class Person` có ngăn methods của Person thay field mutable không?

*Đáp án:* Không. Final class chỉ ngăn subclassing, không làm object immutable.

**Câu 18.** `final` ngăn trạng thái dở dang nếu method mutate trước rồi ném exception chứ?

*Đáp án:* Không. Cần validation/compute-before-commit hoặc thiết kế exception safety, không suy từ final reference.

## 31. Checklist trước khi dùng `final` với tham chiếu

- [ ] Tôi muốn **giữ nguyên tham chiếu của biến** hay muốn **giữ nguyên state object**?
- [ ] Object phía sau reference có những mutating methods/fields nào?
- [ ] Biến final có thể chứa `null` không? Có cần thêm validation non-null?
- [ ] Mọi alias khác có thể mutate cùng object không?
- [ ] Nếu là mảng, các slots có được thay không và element objects có mutable không?
- [ ] Nếu là list/map/set, collection implementation mutable hay unmodifiable?
- [ ] Với `Collections.unmodifiableList`, nguồn còn alias mutable ở đâu?
- [ ] Với `List.copyOf`, elements có được chia sẻ references không?
- [ ] Field private final có bị getter/constructor làm lộ mutable reference không?
- [ ] Nếu cần snapshot, đã copy cấu trúc container và mutable elements thích hợp chưa?
- [ ] Nếu dùng record, components có chứa mutable references không?
- [ ] Nếu trả String từ StringBuilder, caller nhận snapshot hay live mutable reference?
- [ ] Khi một method nhận `final` parameter, tôi có đang nhầm nó với lời hứa không mutate?
- [ ] Nếu nhiều thread, mutation có đồng bộ/atomicity đúng không?
- [ ] Có lẫn final class, final method với final variable/field không?
- [ ] Có test tình huống mutation qua alias để xác minh hợp đồng?
- [ ] Có bảo vệ invariant và xử lý lỗi trước khi mutate để tránh state dở dang?
- [ ] Nếu muốn object bất biến thật sự, nên thay mutable data bằng immutable value types được không?

---

**Ghi nhớ cuối bài:** Trong Java, **`final` trên biến/field/tham số kiểu tham chiếu cố định việc gán giá trị tham chiếu**, **không làm đông cứng object phía sau**. Vì vậy `final StringBuilder` vẫn `append` được, `final int[]` vẫn thay slot được, `final List` vẫn mutate được nếu list hỗ trợ, và **alias khác cũng có thể sửa cùng object**. Muốn bất biến về nội dung phải dựa vào **immutable types, unmodifiable collections, defensive copies, encapsulation và hợp đồng API**; muốn an toàn đa luồng còn cần synchronization/atomic design thích hợp. Phân biệt rõ **“reference không gán lại”** và **“object không thay đổi”** là nền tảng để sử dụng `final` đúng trong Java.