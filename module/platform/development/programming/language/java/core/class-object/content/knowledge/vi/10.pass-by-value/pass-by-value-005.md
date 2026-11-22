# Vì sao gán lại tham số không thay thế biến của bên gọi trong Java

Trong Java, **mọi đối số của lời gọi phương thức đều được truyền theo giá trị** (*pass-by-value*). Điều này đúng cho cả kiểu nguyên thủy như `int`, `double`, `boolean` và kiểu tham chiếu như `String`, `Person`, `List<String>` hay mảng.

Khi một phương thức được gọi, **tham số hình thức là một biến riêng** được khởi tạo từ giá trị của đối số. Vì vậy:

- **Gán lại tham số**, chẳng hạn `number = 99` hoặc `person = new Person("Bình")`, chỉ thay đổi **biến tham số bên trong lời gọi**. Nó không gán lại biến ở nơi gọi.
- **Thay đổi trạng thái đối tượng** qua tham số tham chiếu, chẳng hạn `person.setName("Bình")`, có thể làm bên gọi thấy thay đổi nếu cả hai vẫn tham chiếu **cùng đối tượng**.
- **Muốn biến của bên gọi trỏ đối tượng mới**, hãy **trả tham chiếu mới về và để bên gọi thực hiện phép gán**, ví dụ `person = replace(person);`.
- Java **không có cơ chế pass-by-reference của biến** giống tham số `ref`/`out` trong một số ngôn ngữ khác. “Truyền bản sao tham chiếu” **khác** “truyền chính biến cho hàm gán lại”.

Chỉ cần hiểu rõ **biến**, **giá trị trong biến** và **đối tượng được tham chiếu** là có thể giải thích phần lớn hiện tượng dễ gây nhầm này.

## 1. Một lời gọi có hai phía độc lập

Xét phương thức:

```java
static void change(int value) {
    value = 100;
}
```

Và lời gọi:

```java
int original = 5;
change(original);
System.out.println(original); // 5
```

Ở **nơi gọi**, `original` là một biến cục bộ kiểu `int`, đang giữ giá trị `5`. Trong **khai báo phương thức**, `value` là một **tham số hình thức**, cũng có kiểu `int`. Khi gọi `change(original)`:

1. Biểu thức đối số `original` được đánh giá thành giá trị `5`.
2. Tham số `value` trong lần gọi đó được khởi tạo với **bản sao giá trị `5`**.
3. Câu lệnh `value = 100;` gán lại biến **`value`**, không phải biến **`original`**.
4. Sau khi phương thức kết thúc, `original` vẫn giữ `5`.

Có thể hình dung:

```text
Trước khi gọi:

  original (caller) = 5

Trong lời gọi:

  original (caller) = 5
  value    (callee) = 5  ← giá trị được sao chép

Sau câu lệnh value = 100:

  original (caller) = 5
  value    (callee) = 100
```

Đây là **sơ đồ khái niệm về hai biến**, không nhằm mô tả chính xác layout stack/register mà JVM/JIT sử dụng. Trình biên dịch có thể tối ưu chi tiết lưu trữ mà không thay đổi ngữ nghĩa Java.

### Tham số hình thức không phải bí danh của biến truyền vào

Một tên tham số như `value` không có khả năng tự “trở thành tên thứ hai” của biến `original`. Java lấy **giá trị của biểu thức đối số** để khởi tạo tham số, không chuyển quyền gán của caller sang phương thức.

Điều này đúng ngay cả khi tên hai biến giống nhau ở hai phương thức khác nhau:

```java
static void reset(int count) {
    count = 0;
}

// Trong một phương thức khác:
int count = 10;
reset(count);
```

Hai tên `count` cùng cách viết nhưng nằm ở **hai phạm vi khác nhau**. `reset` không thay đổi biến `count` ở caller.

## 2. “Truyền tham trị” với kiểu nguyên thủy

Với primitive, vấn đề đơn giản nhất: giá trị như `10`, `true` hoặc `3.5` được dùng để khởi tạo biến tham số khác.

Ví dụ Java 17 hoàn chỉnh, lưu thành **`PrimitiveParameterDemo.java`**:

```java
public class PrimitiveParameterDemo {
    static void changeNumber(int number) {
        number = 99;
        System.out.println("Trong changeNumber: " + number);
    }

    static void changeFlag(boolean flag) {
        flag = false;
        System.out.println("Trong changeFlag: " + flag);
    }

    public static void main(String[] args) {
        int score = 10;
        boolean enabled = true;

        changeNumber(score);
        changeFlag(enabled);

        System.out.println("score ở main: " + score);
        System.out.println("enabled ở main: " + enabled);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 PrimitiveParameterDemo.java
java PrimitiveParameterDemo
```

**Stdout:**

```text
Trong changeNumber: 99
Trong changeFlag: false
score ở main: 10
enabled ở main: true
```

Cả `score` lẫn `enabled` đều không thay đổi ở `main`. Không phải vì Java “tự khôi phục” hai biến sau lời gọi, mà vì **chưa có câu lệnh nào gán vào chính hai biến đó**.

## 3. Với đối tượng: sao chép **giá trị tham chiếu**, không sao chép đối tượng

Kiểu tham chiếu phức tạp hơn vì một giá trị tham chiếu có thể dẫn đến **một đối tượng mutable**.

Giả sử:

```java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}
```

Khi gọi:

```java
static void process(Box parameter) {
    // ...
}
```

bằng đối số:

```java
Box callerVariable = new Box(10);
process(callerVariable);
```

thì lúc mới vào `process`, biến `parameter` và `callerVariable` là **hai biến riêng**, nhưng đang chứa **giá trị tham chiếu đến cùng đối tượng `Box`**.

```text
callerVariable (ở caller) ───┐
                            ├──> Box #1 { value: 10 }
parameter (ở process) ──────┘
```

Số `#1` là nhãn minh họa danh tính đối tượng, không phải địa chỉ bộ nhớ. Việc truyền đối số **không tạo một `new Box(...)` ẩn**, cũng không clone field `value`.

### Hai thao tác khác hẳn

```java
parameter.value = 20;        // A: sửa đối tượng Box #1
parameter = new Box(30);     // B: gán lại biến parameter
```

- **A — Mutation:** thay field `value` của `Box #1` thành `20`. Vì bên gọi vẫn tham chiếu `Box #1` nên đọc `callerVariable.value` sẽ thấy `20`.
- **B — Reassignment:** tạo `Box #2` và gán tham chiếu mới vào **biến `parameter`**. Biến `callerVariable` vẫn trỏ `Box #1`. Nếu sau đó `parameter.value = 40`, chỉ `Box #2` đổi, không phải `Box #1`.

Sơ đồ sau B:

```text
callerVariable ──────> Box #1 { value: 20 }

parameter      ──────> Box #2 { value: 30 }
```

**Công thức ghi nhớ:** `parameter = ...` thay đổi **biến tham số**; `parameter.field = ...` thay đổi **field của đối tượng** mà tham số đang trỏ đến.

## 4. Chương trình đầy đủ: mutate rồi reassign tham số

Lưu thành **`ReferenceParameterDemo.java`**:

```java
class Box {
    private int value;

    Box(int value) {
        this.value = value;
    }

    int value() {
        return value;
    }

    void setValue(int value) {
        this.value = value;
    }
}

public class ReferenceParameterDemo {
    static void mutate(Box box) {
        box.setValue(20);
    }

    static void reassign(Box box) {
        box = new Box(30);
        System.out.println("Trong reassign: " + box.value());
    }

    static void mutateThenReassign(Box box) {
        box.setValue(40);
        box = new Box(50);
        box.setValue(60);
        System.out.println("Trong mutateThenReassign: " + box.value());
    }

    public static void main(String[] args) {
        Box original = new Box(10);

        mutate(original);
        System.out.println("Sau mutate: " + original.value());

        reassign(original);
        System.out.println("Sau reassign: " + original.value());

        mutateThenReassign(original);
        System.out.println("Sau mutateThenReassign: " + original.value());
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 ReferenceParameterDemo.java
java ReferenceParameterDemo
```

**Stdout chính xác:**

```text
Sau mutate: 20
Trong reassign: 30
Sau reassign: 20
Trong mutateThenReassign: 60
Sau mutateThenReassign: 40
```

Phân tích từng phương thức:

- `mutate(original)` nhận bản sao tham chiếu đến object gốc. `box.setValue(20)` sửa object đó, nên bên gọi đọc `20`.
- `reassign(original)` ban đầu nhận cùng tham chiếu gốc nhưng sau đó thực hiện `box = new Box(30)`. **Chỉ biến tham số `box` đổi**; bên gọi vẫn đọc `20`.
- `mutateThenReassign(original)` trước tiên sửa object gốc thành `40`. Tiếp theo `box` được gán sang object mới `Box(50)`, rồi object mới bị sửa thành `60`. Bởi vậy **bên trong** in `60`, còn object gốc của `original` vẫn có `40`.

**Quy tắc không có ngoại lệ ở đây:** gán lại tham số chỉ tác động trực tiếp lên tham số đó. Việc bên gọi thấy thay đổi trong vài ví dụ xuất phát từ **mutation trên object dùng chung**, không phải vì Java bí mật dùng pass-by-reference.

## 5. Tại sao `Box box = callerBox` không giống `Box box = new Box(...)`?

Hai lệnh có thể cùng tạo một **biến tham chiếu**, nhưng chỉ một lệnh tạo object mới:

```java
Box first = new Box(5);
Box alias = first;
Box independent = new Box(5);
```

- `first` và `alias` cùng tham chiếu một object.
- `independent` trỏ một object khác, dù trạng thái ban đầu bằng nhau.
- `alias = new Box(9)` chuyển `alias` sang một object mới, không làm `first` “chạy theo”.
- `first.setValue(7)` sửa object của `first`; không ảnh hưởng `alias` nếu `alias` đã được gán sang object khác.

Nếu class `Box` chưa override `equals`, có thể dùng `==` để nhận biết hai tham chiếu có cùng identity. Khi hai object có trạng thái bằng nhau, `==` vẫn có thể là `false`.

Lời gọi phương thức hoạt động giống việc tạo **một alias tạm thời dưới dạng biến tham số**, chứ không sao chép nội dung object.

## 6. Java không truyền **biến tham chiếu** theo tham chiếu

Đây là điểm mấu chốt về ngôn ngữ:

> Java **pass-by-value**, kể cả với reference types. Tham số nhận **một giá trị tham chiếu đã sao chép**, không nhận “quyền thay trực tiếp biến của caller”.

Đôi khi có câu nói “Java truyền object theo tham chiếu”. Câu này dễ gây hiểu sai:

- **Đúng ở khía cạnh chia sẻ object:** bên nhận và caller có thể cùng truy cập một object thông qua các giá trị tham chiếu.
- **Sai nếu hiểu là pass-by-reference của biến:** gán `parameter = other` không thể tự gán `callerVariable = other`.

Nếu một ngôn ngữ có tham số pass-by-reference thực sự của biến, bên nhận có thể thay chính vị trí lưu giá trị của biến bên gọi. Java **không có cú pháp method parameter tương đương `ref Box` hay `out Box` để làm việc đó**.

Đặc biệt, ***bất kể* loại tham chiếu nào**, như `String`, `Integer`, `List`, mảng hay đối tượng do bạn tự tạo, nguyên tắc trên vẫn giữ nguyên.

## 7. “Hoán đổi hai biến” bằng cách gán lại tham số sẽ thất bại

Đây là hệ quả trực tiếp của việc tham số là biến riêng:

```java
static void swap(Box left, Box right) {
    Box temporary = left;
    left = right;
    right = temporary;
}
```

Giả sử caller tạo `Box first = new Box(1); Box second = new Box(2);` với constructor phù hợp. Sau `swap(first, second)`, `first` vẫn chỉ Box(1), `second` vẫn chỉ Box(2). Chỉ `left` và `right` bị hoán đổi cục bộ, rồi hết scope khi phương thức trở về.

Đây là **snippet**, không phải file độc lập. Bài “Phân tích ví dụ hoán đổi hai tham chiếu không thành công” là nơi dạy chính: chương trình có stdout, sơ đồ sau từng phép gán và bốn cách xử lý đúng (mảng, list, holder, trả cặp giá trị). Trong bài về gán lại tham số này, swap chỉ là phản ví dụ gọn cho việc callee **không thể thay biến caller thông qua phép gán vào parameter**.

## 8. Nếu muốn thay biến ở bên gọi: trả giá trị mới và gán lại

Thiết kế Java thường dùng là **return a replacement**:

```java
static Box replace(Box oldBox) {
    return new Box(oldBox.id + 1);
}
```

Nơi gọi **phải thực hiện phép gán**:

```java
Box current = new Box(1);
current = replace(current);
```

Lời gọi `replace(current)` tự nó **không đổi biến `current`**. Biến đổi bởi phần bên trái dấu `=` ở câu lệnh `current = ...` của **caller**.

### 8.1. Phân biệt ba cách viết

Giả sử:

```java
static Box next(Box value) {
    return new Box(value.id + 1);
}
```

Với `Box current = new Box(10);`:

| Câu lệnh của caller | Biến `current` sau câu lệnh | Giải thích |
| --- | --- | --- |
| `next(current);` | Vẫn trỏ `Box(10)` | Giá trị trả về bị bỏ qua |
| `Box other = next(current);` | Vẫn trỏ `Box(10)` | `other` nhận object mới |
| `current = next(current);` | Trỏ `Box(11)` | Caller chủ động gán lại chính biến `current` |

Không cần và không nên tạo một cách “gán hộ” biến của caller nếu có thể thiết kế API **trả về kết quả rõ ràng**.

### 8.2. Ví dụ chương trình thay tham chiếu đúng cách

Lưu thành **`ReturnAndAssignDemo.java`**:

```java
class Ticket {
    final int version;

    Ticket(int version) {
        this.version = version;
    }
}

public class ReturnAndAssignDemo {
    static Ticket upgraded(Ticket input) {
        return new Ticket(input.version + 1);
    }

    public static void main(String[] args) {
        Ticket current = new Ticket(1);
        Ticket alias = current;

        upgraded(current); // Bỏ qua kết quả trả về
        System.out.println("Sau lời gọi bỏ qua: " + current.version);

        current = upgraded(current);
        System.out.println("current: " + current.version);
        System.out.println("alias: " + alias.version);
        System.out.println("Cùng object: " + (current == alias));
    }
}
```

```bash
javac -encoding UTF-8 ReturnAndAssignDemo.java
java ReturnAndAssignDemo
```

**Stdout:**

```text
Sau lời gọi bỏ qua: 1
current: 2
alias: 1
Cùng object: false
```

Đây là ví dụ rõ ràng về **gán lại biến ở đúng nơi cần gán**. `alias` vẫn giữ object cũ; `current` đã nhận tham chiếu object mới. Không có thay đổi nào trên object cũ chỉ vì hàm trả về object mới.

## 9. Đối tượng mutable và bất biến: đừng nhầm mutate với reassignment

### 9.1. `String` là immutable

`String` không có thao tác sửa trực tiếp nội dung của một object chuỗi đã tạo. Các method như `concat`, `replace`, `toUpperCase` thông thường cho kết quả là một `String` (có thể tái sử dụng đối tượng trong một số trường hợp), chứ không thay nội dung object hiện tại.

```java
static void changeText(String text) {
    text = text + " Java";
}

String message = "Hello";
changeText(message);
System.out.println(message); // Hello
```

`text = text + " Java"` gán tham chiếu tới chuỗi kết quả **vào biến tham số `text`**. Nó không gán lại biến `message` ở caller.

Nếu muốn nhận chuỗi mới:

```java
static String appendJava(String text) {
    return text + " Java";
}

// Caller:
message = appendJava(message);
```

Lúc này `message` nhận giá trị `"Hello Java"` vì **caller có phép gán**, không phải vì Java truyền `message` theo tham chiếu.

### 9.2. `StringBuilder` là mutable

`StringBuilder.append` sửa nội dung **đối tượng builder**:

```java
static void appendText(StringBuilder builder) {
    builder.append(" Java");
}
```

Nếu `StringBuilder message = new StringBuilder("Hello");`, sau `appendText(message)`, `message.toString()` là `"Hello Java"`. Đây là **mutation trên object** có chung tham chiếu.

Nhưng:

```java
static void replaceBuilder(StringBuilder builder) {
    builder = new StringBuilder("New");
}
```

không thay biến `message` ở caller. Constructor `new StringBuilder("New")` tạo object khác rồi gán **biến tham số `builder`**.

### Ví dụ Java 17: String và StringBuilder

Lưu vào **`StringParameterDemo.java`**:

```java
public class StringParameterDemo {
    static void reassignString(String text) {
        text = text.concat(" World");
        System.out.println("Trong String: " + text);
    }

    static void mutateBuilder(StringBuilder builder) {
        builder.append(" World");
    }

    static void reassignBuilder(StringBuilder builder) {
        builder = new StringBuilder("Other");
        System.out.println("Trong Builder: " + builder);
    }

    public static void main(String[] args) {
        String text = "Hello";
        StringBuilder builder = new StringBuilder("Hello");

        reassignString(text);
        mutateBuilder(builder);
        reassignBuilder(builder);

        System.out.println("text ở main: " + text);
        System.out.println("builder ở main: " + builder);
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 StringParameterDemo.java
java StringParameterDemo
```

Stdout:

```text
Trong String: Hello World
Trong Builder: Other
text ở main: Hello
builder ở main: Hello World
```

Hai giá trị cuối khác nhau vì **`String` bất biến và biến tham số được gán lại**, trong khi `StringBuilder` có thao tác sửa nội dung đối tượng dùng chung.

## 10. Mảng: thay nội dung mảng và thay tham chiếu mảng

Mảng Java là **đối tượng**. Với:

```java
int[] data = {1, 2};
```

biến `data` có kiểu tham chiếu `int[]`, đang trỏ đến một object mảng. Nếu truyền `data` vào phương thức:

```java
static void process(int[] numbers) {
    numbers[0] = 9;
    numbers = new int[]{7, 8};
}
```

thì:

- `numbers[0] = 9` thay nội dung **đối tượng mảng** được dùng chung, bên gọi nhìn thấy `9`.
- `numbers = new int[]{7, 8}` chỉ gán lại **biến tham số `numbers`**. Biến `data` vẫn trỏ mảng cũ `[9, 2]`.

### Ví dụ chạy được

Lưu **`ArrayParameterDemo.java`**:

```java
import java.util.Arrays;

public class ArrayParameterDemo {
    static void alter(int[] numbers) {
        numbers[0] = 9;
        numbers = new int[]{7, 8};
        numbers[1] = 6;
        System.out.println("Trong alter: " + Arrays.toString(numbers));
    }

    public static void main(String[] args) {
        int[] data = {1, 2};
        int[] alias = data;

        alter(data);

        System.out.println("Ở main: " + Arrays.toString(data));
        System.out.println("alias: " + Arrays.toString(alias));
        System.out.println("Cùng mảng: " + (data == alias));
    }
}
```

```bash
javac -encoding UTF-8 ArrayParameterDemo.java
java ArrayParameterDemo
```

Stdout:

```text
Trong alter: [7, 6]
Ở main: [9, 2]
alias: [9, 2]
Cùng mảng: true
```

Đây vẫn là **pass-by-value**. Biến `data` và biến `numbers` lúc đầu là hai biến riêng cùng tham chiếu mảng, nhưng reassignment của `numbers` không thay đổi `data`.

### Một array wrapper có thể giúp thay *phần tử* mà caller đọc

Nếu muốn hoán đổi các phần tử của mảng caller, có thể sửa trực tiếp mảng:

```java
static void swapFirstTwo(Box[] values) {
    Box temp = values[0];
    values[0] = values[1];
    values[1] = temp;
}
```

`values[0] = ...` sửa **phần tử mảng**; không gán lại biến tham chiếu mảng của caller. Vì caller giữ cùng mảng, thứ tự phần tử thay đổi là điều có thể thấy.

Tuy nhiên đây **không** phải hoán đổi trực tiếp hai biến cục bộ `Box first` và `Box second` của caller; chỉ hai slot trong **đối tượng mảng** được đổi.

## 11. Dùng một holder: cho phép caller quan sát **field tham chiếu** bị thay

Nếu một API cần có “tham chiếu hiện tại” mà phương thức khác được quyền thay, ta có thể chuyển việc cần cập nhật từ **biến cục bộ** sang **field của một đối tượng mutable** được dùng chung.

Ví dụ:

```java
class Holder<T> {
    T value;

    Holder(T value) {
        this.value = value;
    }
}
```

Thay vì cố viết:

```java
static void replace(Box box) {
    box = new Box(99); // Không đổi biến Box của caller
}
```

ta có thể viết:

```java
static void replace(Holder<Box> holder) {
    holder.value = new Box(99); // Sửa field của object Holder chung
}
```

Lúc đó **biến `holder` của caller không bị gán lại**, nhưng **field `holder.value`** của object chung được thay đổi. Caller đọc `holder.value` sẽ thấy đối tượng mới.

Sơ đồ:

```text
caller.holder   ─────┐
                     ├──> Holder #1
parameter holder ────┘         └── value ───> Box #2

replace() thay Holder #1.value, KHÔNG thay caller.holder.
```

### Ví dụ Java 17 với holder

Lưu thành **`HolderParameterDemo.java`**:

```java
class Box {
    final int number;

    Box(int number) {
        this.number = number;
    }
}

class Holder<T> {
    T value;

    Holder(T value) {
        this.value = value;
    }
}

public class HolderParameterDemo {
    static void replace(Holder<Box> holder) {
        holder.value = new Box(99);
        holder = new Holder<>(new Box(123));
        System.out.println("Holder cục bộ: " + holder.value.number);
    }

    public static void main(String[] args) {
        Holder<Box> outer = new Holder<>(new Box(10));
        replace(outer);

        System.out.println("Holder ở main: " + outer.value.number);
    }
}
```

```bash
javac -encoding UTF-8 HolderParameterDemo.java
java HolderParameterDemo
```

Stdout:

```text
Holder cục bộ: 123
Holder ở main: 99
```

Diễn giải:

1. Ban đầu hai biến holder tham chiếu cùng object `Holder<Box>`.
2. `holder.value = new Box(99)` sửa field của object `Holder` dùng chung, nên `outer.value.number` đổi thành `99`.
3. `holder = new Holder<>(new Box(123))` chỉ gán lại tham số holder, vì thế dòng in cục bộ là `123` nhưng object `Holder` của caller vẫn có field `value` tham chiếu `Box(99)`.

**Đừng kết luận Java đã trở thành pass-by-reference.** Cơ chế không đổi: caller và callee cùng sở hữu tham chiếu đến một **holder mutable**; cả hai có thể quan sát **mutation của holder**.

### Khi nào dùng holder, khi nào return?

- Nếu phương thức chỉ cần tạo một replacement, **return** thường rõ ràng nhất: `current = replace(current);`.
- Nếu cần cập nhật **nhiều giá trị** hay API bắt buộc nhận một cấu trúc mutable, holder/record kết quả có thể phù hợp.
- Nếu muốn giữ API bất biến và dễ kiểm thử, ưu tiên **trả kết quả** thay vì ẩn thay đổi trong một holder.
- Nếu làm việc đa luồng, một holder tự định nghĩa với field thường **không tự an toàn**; cần thiết kế synchronization hoặc dùng các abstraction đồng thời phù hợp.

## 12. Gán lại *field* khác với gán lại *biến tham số*

Một object có thể chứa một field tham chiếu đến object khác:

```java
class Address {
    String city;

    Address(String city) {
        this.city = city;
    }
}

class Customer {
    Address address;

    Customer(Address address) {
        this.address = address;
    }
}
```

Hai câu lệnh này không đồng nghĩa:

```java
customer.address = new Address("Huế");  // Gán lại FIELD của Customer
customer = new Customer(new Address("Hà Nội")); // Gán lại BIẾN customer
```

Câu thứ nhất **mutate object `Customer`** bằng cách thay giá trị field `address` của nó. Nếu caller và callee cùng tham chiếu đến `Customer` ấy, caller có thể thấy `customer.address` mới.

Câu thứ hai, nếu nằm trong một phương thức mà `customer` là **tham số**, chỉ thay **biến tham số `customer`**. Caller không bị ép đổi sang `Customer` mới.

### Ví dụ trực tiếp với method

```java
static void update(Customer customer) {
    customer.address = new Address("Đà Nẵng");
}

static void replace(Customer customer) {
    customer = new Customer(new Address("Huế"));
}
```

Với `Customer c = new Customer(new Address("Hà Nội"));`:

- `update(c);` làm `c.address.city` thành `"Đà Nẵng"`.
- `replace(c);` **không** làm `c.address.city` thành `"Huế"`.

Field là một **vị trí lưu tham chiếu thuộc object**, khác với **biến tham số cục bộ**. Một phép gán có tác động ra ngoài hay không phụ thuộc vào **đích của phép gán**.

## 13. `null` không làm cơ chế truyền tham trị thay đổi

Với:

```java
Box value = null;
```

đối số `value` có **giá trị tham chiếu `null`**. Phương thức nhận bản sao `null`:

```java
static void initialize(Box box) {
    if (box == null) {
        box = new Box(10);
    }
}
```

Lời gọi `initialize(value);` không làm `value` thoát khỏi `null`. Bên trong phương thức, `box` được gán tham chiếu object mới nhưng **biến `value` của caller vẫn là `null`**.

### Cách đúng nếu cần khởi tạo giá trị cho caller

```java
static Box initialize(Box box) {
    if (box == null) {
        return new Box(10);
    }
    return box;
}

// Caller:
value = initialize(value);
```

Vì phép gán nằm ở caller, biến `value` mới nhận tham chiếu kết quả.

### Một lỗi nữa: dereference khi tham số `null`

```java
static void mutate(Box box) {
    box.setValue(10);
}
```

Nếu gọi `mutate(null)` và thực thi `box.setValue(10)`, phương thức ném **`NullPointerException`**. Không có object để mutate. Gán `box = new Box(10)` trước đó có thể giúp biến tham số không còn null, **nhưng vẫn không gán lại biến của caller**.

Đừng dùng kiểu diễn đạt “truyền null nên Java tạo object rồi gắn lại cho caller” nếu code chỉ thay tham số cục bộ.

## 14. `final` trên tham số cấm gán lại, nhưng không khóa object

Một tham số có thể khai báo `final`:

```java
static void modify(final Box box) {
    box.setValue(15);        // Hợp lệ nếu Box mutable và method cho phép
    // box = new Box(20);     // SAI: không gán lại tham số final
}
```

`final` ở đây ràng buộc **biến tham số `box`**. Nó không biến object của `Box` thành immutable.

Tương tự ở caller:

```java
final Box value = new Box(5);
modify(value);
```

`value` không thể được gán tham chiếu mới, nhưng trạng thái của object mà `value` trỏ đến vẫn có thể đổi nếu API cho phép.

| Khai báo / thao tác | Có hợp lệ không? | Lý do |
| --- | --- | --- |
| `Box b = new Box(1); b = new Box(2);` | Có | `b` không final |
| `final Box b = new Box(1); b = new Box(2);` | Không | Gán lại biến final |
| `final Box b = new Box(1); b.setValue(2);` | Có nếu API mutable | Sửa object, không gán lại b |
| `void f(final Box b) { b = null; }` | Không | Gán lại tham số final |
| `void f(final Box b) { b.setValue(3); }` | Có nếu API mutable | Tham số final chỉ giữ tham chiếu |

Một số framework/đội ngũ thích khai báo tham số final để ngăn vô tình gán lại biến trong thân method. Đây là phong cách kiểm soát mã hữu ích nhưng **không làm Java dùng pass-by-reference** và không tự bảo đảm thread safety.

## 15. Tham số không có tác động “hai chiều” đặc biệt vì cùng tên

Có người đặt tên tham số giống tên biến ở caller rồi mong nó bị cập nhật:

```java
static void change(int score) {
    score = 100;
}

public static void main(String[] args) {
    int score = 10;
    change(score);
}
```

Tên giống nhau **không tạo liên kết** giữa hai biến `score`:

- `score` trong `main` là local variable của `main`.
- `score` trong `change` là formal parameter thuộc lời gọi `change`.
- Hai tên nằm ở các scope khác nhau. Chúng **không** cùng một slot biến theo quy tắc của Java.

Thậm chí đối số không cần là tên biến:

```java
change(1 + 2);
change(Math.max(3, 5));
```

Hai lời gọi đều hợp lệ dù `1 + 2` và `Math.max(3, 5)` là **biểu thức**, không phải “biến của caller” để gán lại. Điều này minh họa rằng đầu vào của method là **giá trị biểu thức**, không phải một địa chỉ biến có thể cập nhật tùy ý.

## 16. Constructor cũng nhận bản sao giá trị đối số

Các tham số của **constructor** tuân thủ quy tắc truyền tham trị tương tự method.

```java
class Profile {
    private String name;

    Profile(String name) {
        name = "Inside"; // Chỉ gán lại tham số name
    }
}
```

Đoạn trên không gán vào field `this.name`. Vì vậy field `name` nhận giá trị mặc định `null` (giả sử không có initializer khác), còn biến tham số `name` chỉ bị thay bên trong constructor.

Đoạn đúng khi cần lưu dữ liệu vào object:

```java
class Profile {
    private String name;

    Profile(String name) {
        this.name = name; // Gán FIELD từ giá trị THAM SỐ
    }
}
```

**`this.name = name` khác `name = name`.** Vế trái là field của object, chứ không phải biến tham số. Đây là lỗi rất phổ biến khi tên field và tham số constructor giống nhau.

Ngay cả khi trong constructor, gán tham số là **gán biến riêng của constructor**, không sửa biến bên gọi đã dùng trong `new Profile(inputName)`.

## 17. Varargs cũng không thể gán lại biến mảng của caller

Một khai báo varargs:

```java
static void process(int... numbers) {
    numbers = new int[]{8, 9};
}
```

Bên trong method, `numbers` là một tham số kiểu mảng `int[]`. Nếu gọi:

```java
int[] data = {1, 2};
process(data);
```

thì `numbers = new int[]{8, 9}` chỉ gán lại **tham số mảng**; `data` vẫn là mảng `[1, 2]`.

Nếu method sửa phần tử:

```java
static void process(int... numbers) {
    numbers[0] = 8;
}
```

thì khi caller truyền **một mảng có sẵn** qua `process(data)`, mutation của mảng có thể được quan sát qua `data`. Còn với `process(1, 2)`, lời gọi variable arity được chuẩn bị bằng một mảng cho các giá trị, không có biến mảng caller cần thay tham chiếu.

**Lưu ý:** `process((int[]) null)` truyền giá trị tham chiếu mảng null; `numbers[0]` khi đó ném `NullPointerException` nếu thực thi. Đây không phải lý do để coi varargs là pass-by-reference.

## 18. `this` làm đối số vẫn chỉ là truyền giá trị tham chiếu

Trong một instance method:

```java
class Task {
    void register(Registry registry) {
        registry.add(this);
    }
}
```

`this` là **tham chiếu đến object `Task` hiện tại**. `registry.add(this)` truyền **bản sao giá trị tham chiếu** đến `Task` cho `Registry.add`. Registry có thể giữ tham chiếu và tác động đến object nếu được phép, nhưng **không thể gán lại từ xa từ khóa `this`** của phương thức đang gọi.

Nếu callee thực hiện `task = new Task();` với tham số `Task task`, callee chỉ thay **biến tham số task**, tương tự các ví dụ trước.

Một phương thức có thể `return this;` để trả chính object hiện tại, nhưng một lần nữa việc bên gọi có gán kết quả vào biến nào hay không là **quyết định của bên gọi**.

**Cẩn thận về vòng đời:** truyền `this` cho registry/callback ngay trong constructor có thể làm object chưa khởi tạo đầy đủ bị lộ ra ngoài (*this escape*). Vấn đề này liên quan an toàn thiết kế object, không thay đổi nguyên lý pass-by-value.

## 19. Sự khác nhau giữa thay một field và thay biến của caller

Giả sử:

```java
class Session {
    String status;

    Session(String status) {
        this.status = status;
    }
}
```

Có hai method:

```java
static void setStatus(Session session) {
    session.status = "ACTIVE";
}

static void replaceSession(Session session) {
    session = new Session("ACTIVE");
}
```

Với:

```java
Session current = new Session("NEW");
setStatus(current);
System.out.println(current.status); // ACTIVE

replaceSession(current);
System.out.println(current.status); // ACTIVE, vẫn object cũ
```

Sau `setStatus`, object hiện có đã bị sửa trạng thái. Sau `replaceSession`, object hiện có **không bị thay bởi object mới**, nên dòng in vẫn phản ánh object cũ đang có trạng thái `ACTIVE`.

Để thấy khác biệt rõ hơn, nếu bắt đầu một `current` mới với `"NEW"` và **chỉ** gọi `replaceSession(current)`, giá trị `current.status` vẫn là `"NEW"`.

### Khi dùng mutable holder field tham chiếu

Nếu `class SessionStore { Session current; }` và callee nhận `SessionStore store` rồi viết `store.current = new Session("ACTIVE");`, caller đang giữ **cùng object `SessionStore`** sẽ đọc được field `current` mới.

**Nhưng vẫn không phải gán lại biến `store` ở caller.** Cái được mutate là **field của một object dùng chung**. Hãy xác định chính xác **vế trái phép gán**:

- `parameter = value;` → biến tham số.
- `parameter.field = value;` → field của object được tham chiếu.
- `parameter.array[i] = value;` → phần tử mảng được tham chiếu.
- `callerVariable = method(...);` → biến của caller, do chính câu lệnh ở caller gán.

## 20. Quy tắc cho kết quả trả về của method

Giá trị trả về **không tự gán vào đối số**:

```java
static int doubleValue(int number) {
    number *= 2;
    return number;
}
```

Với:

```java
int x = 5;
doubleValue(x);
System.out.println(x); // 5
```

`doubleValue(x)` tính được kết quả `10` nhưng bên gọi **bỏ qua** giá trị trả về. `x` không đổi.

Nếu muốn `x` thay đổi:

```java
x = doubleValue(x);
System.out.println(x); // 10
```

**Cần tách hai hành động:**

1. Trong method, `return expression;` cung cấp một **giá trị kết quả**.
2. Ở caller, phép gán `x = ...` lấy giá trị kết quả ấy để **thay đổi biến x**.

`return` không có quyền tự “đoán” rằng caller muốn sửa biến nào. Một kết quả có thể được gán vào nhiều biến khác nhau, dùng trong biểu thức hoặc bỏ qua.

## 21. Thay đổi nhiều giá trị: dùng kiểu kết quả, không giả lập pass-by-reference

Nếu một phép tính cần trả nhiều giá trị, Java có một số cách rõ ràng:

- Trả một **đối tượng kết quả** chứa các trường cần thiết.
- Dùng `record` bất biến trong Java 17 để nhóm các giá trị trả về.
- Trả một collection/mảng phù hợp khi các phần tử cùng nghĩa và được kiểm soát.
- Dùng mutable holder khi API thật sự yêu cầu **một object mang trạng thái có thể cập nhật**.

Ví dụ trả hai số mới bằng `record`:

```java
record Pair(int left, int right) {
}
```

```java
static Pair swapValues(int left, int right) {
    return new Pair(right, left);
}
```

Caller:

```java
int a = 1;
int b = 2;

Pair swapped = swapValues(a, b);
a = swapped.left();
b = swapped.right();
```

Cách này **không thay trực tiếp tham số của caller**. Caller nhận object kết quả chứa giá trị cần dùng và **tự cập nhật hai biến `a`/`b`**.

### Chương trình Java 17 với record kết quả

Lưu **`ReturnPairDemo.java`**:

```java
record Pair(int left, int right) {
}

public class ReturnPairDemo {
    static Pair swapValues(int left, int right) {
        return new Pair(right, left);
    }

    public static void main(String[] args) {
        int first = 10;
        int second = 20;

        Pair result = swapValues(first, second);
        System.out.println("Trước gán: " + first + ", " + second);

        first = result.left();
        second = result.right();
        System.out.println("Sau gán: " + first + ", " + second);
    }
}
```

```bash
javac -encoding UTF-8 ReturnPairDemo.java
java ReturnPairDemo
```

**Stdout:**

```text
Trước gán: 10, 20
Sau gán: 20, 10
```

`record Pair` trong Java 17 tạo kiểu chứa hai thành phần với các accessor `left()` và `right()`. Việc hoán đổi **biến caller** vẫn nằm trong `main` và được thể hiện bằng hai câu lệnh gán rõ ràng.

## 22. Các trường hợp thường bị diễn giải sai

| Ví dụ | Tác động thực tế | Có thay biến caller không? |
| --- | --- | --- |
| `void f(int x) { x = 9; }` | Gán biến tham số nguyên thủy | **Không** |
| `void f(Box x) { x = new Box(9); }` | Gán biến tham số tham chiếu | **Không** |
| `void f(Box x) { x.setValue(9); }` | Mutate object do tham số trỏ tới | Không gán biến caller; object của caller **có thể đổi** |
| `void f(int[] x) { x[0] = 9; }` | Sửa phần tử mảng dùng chung | Không gán biến mảng caller; phần tử **có thể đổi** |
| `void f(int[] x) { x = new int[]{9}; }` | Gán tham số sang mảng mới | **Không** |
| `void f(String x) { x += "a"; }` | Gán tham số sang chuỗi kết quả | **Không** |
| `void f(StringBuilder x) { x.append("a"); }` | Sửa builder dùng chung | Không gán biến caller; nội dung builder **có thể đổi** |
| `void f(Holder<Box> x) { x.value = new Box(9); }` | Gán **field** của holder dùng chung | Biến holder caller không đổi; field **có thể đổi** |
| `Box f(Box x) { return new Box(9); }` | Trả một tham chiếu mới | **Không**, nếu caller bỏ qua kết quả |
| `caller = f(caller);` | Caller tự gán giá trị trả về | **Có**, do phép gán ở caller |
| `void f(final Box x) { x.setValue(9); }` | Mutate object qua tham số final | Biến caller không đổi; object **có thể đổi** |
| `void f(final Box x) { x = new Box(9); }` | Không hợp lệ | **Lỗi biên dịch** |

**Cẩn thận cách hỏi:** “Có làm caller thấy khác đi không?” khác “Có gán lại biến của caller không?”. Mutation có thể làm caller thấy trạng thái mới **mà không hề gán lại biến caller**.

## 23. Nhận diện lỗi bằng sơ đồ trước/sau

Đối với những đoạn code phức tạp, dùng quy trình bốn bước:

1. **Liệt kê biến** ở caller và tham số ở callee; đánh dấu chúng là **các biến khác nhau**.
2. **Vẽ tham chiếu ban đầu**: biến nào trỏ object nào; đặt nhãn object A/B thay cho suy đoán địa chỉ.
3. **Đọc từng phép gán đúng vế trái**: nếu là `parameter = ...` thì sửa biến callee; nếu là `parameter.field = ...` thì sửa object; nếu là `caller = method(...)` thì sửa biến caller.
4. **Khi thoát method**, bỏ các biến cục bộ của lần gọi; giữ lại mọi mutation đã tác động lên object dùng chung và mọi giá trị đã được caller chủ động nhận.

Ví dụ:

```java
static void execute(Box item) {
    item.setValue(2);
    item = new Box(3);
    item.setValue(4);
}
```

Caller:

```java
Box box = new Box(1);
Box alias = box;
execute(box);
```

Sơ đồ:

```text
1. Ban đầu:
box  ─┐
alias ─┴──> Box A { value: 1 }

2. Vào execute:
box   ────┐
alias ────┼──> Box A { value: 1 }
item  ────┘

3. item.setValue(2):
box   ────┐
alias ────┼──> Box A { value: 2 }
item  ────┘

4. item = new Box(3):
box   ────┐
alias ────┴──> Box A { value: 2 }
item  ─────────> Box B { value: 3 }

5. item.setValue(4):
box   ────┐
alias ────┴──> Box A { value: 2 }
item  ─────────> Box B { value: 4 }

6. Sau khi execute kết thúc:
box   ────┐
alias ────┴──> Box A { value: 2 }
```

Ở bước 6, `box.value()` và `alias.value()` đều là `2`. `Box B` không được tự “chuyển vào” biến `box` vì chưa hề có phép gán nào vào `box` của caller.

Đây là kỹ thuật giải thích chắc chắn hơn việc nói mơ hồ “Java truyền địa chỉ” hay “Java truyền bản sao object”.

## 24. Liên quan đến getter, setter và đóng gói

Một API có thể không cho sửa field trực tiếp:

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
```

Với:

```java
Account account = new Account(100);
addMoney(account);
```

và:

```java
static void addMoney(Account a) {
    a.deposit(50);
}
```

thì caller sẽ thấy `account.balance() == 150`. Điều này **không chứng minh `addMoney` có quyền gán lại biến `account` ở caller**. Nó chỉ gọi một public/package-accessible instance method làm thay đổi trạng thái object.

Ngược lại, nếu:

```java
static void replaceAccount(Account a) {
    a = new Account(999);
}
```

thì caller vẫn giữ object ban đầu.

**Đóng gói** kiểm soát những thay đổi trạng thái nào được phép qua API, nhưng bản thân cơ chế sao chép giá trị đối số vẫn không đổi.

## 25. Đồng thời và object dùng chung: phạm vi hiểu biết cần thiết

Khi nhiều thread cùng sử dụng tham chiếu đến một object mutable, thao tác mutation có thể gây **race condition** nếu thiếu đồng bộ. Nhưng đó là **vấn đề khác với** pass-by-value.

Ví dụ:

- Hai thread cùng giữ tham chiếu đến một `Counter`.
- Một thread thực hiện `counter.increment()`, thread kia đọc trạng thái.
- Việc một thread gán lại **biến tham số cục bộ** `counter = new Counter()` không thay đổi biến của thread kia.
- Việc cả hai cùng sửa **một object Counter** có thể cần `synchronized`, atomic types hoặc một chiến lược bất biến/snapshot.

`AtomicReference<T>` là một object có API cho phép **thay giá trị tham chiếu được lưu trong nó với ngữ nghĩa đồng thời thích hợp**, chứ không làm Java thay cách truyền đối số:

```java
java.util.concurrent.atomic.AtomicReference<Box> holder =
        new java.util.concurrent.atomic.AtomicReference<>(new Box(1));
```

Một method nhận tham số `AtomicReference<Box> holder` rồi gọi `holder.set(new Box(2))` đã **thay state của object AtomicReference dùng chung**. Biến tham chiếu `holder` của caller không bị gán lại. Đồng thời, `AtomicReference` chỉ cung cấp bảo đảm về hoạt động atomic trên **giá trị tham chiếu được giữ**, không tự làm thread-safe tất cả field bên trong object `Box`.

**Không cần dùng `AtomicReference` chỉ để “cho Java truyền tham chiếu”** trong mã một luồng. Nên ưu tiên return value hoặc một lớp kết quả dễ hiểu.

## 26. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `change(x)` rồi `x` không đổi | Method chỉ gán tham số riêng | Trả giá trị mới, gọi `x = change(x)` |
| `replace(obj)` tạo object mới nhưng biến caller giữ object cũ | `obj = new ...` trong method chỉ đổi tham số | Trả object mới và gán ở caller |
| `swap(a, b)` không hoán đổi hai biến | Chỉ hoán đổi bản sao tham chiếu/giá trị của tham số | Dùng giá trị trả về, một record, hoặc đổi phần tử trong một cấu trúc mutable |
| `list.add(...)` từ method lại ảnh hưởng list ở caller | Cùng object list được chia sẻ qua tham chiếu | Đây là mutation, không phải reassignment |
| `list = new ArrayList<>()` trong method không thay list caller | Gán lại tham số list | Trả list mới hoặc cập nhật object holder nếu hợp đồng yêu cầu |
| `String` không đổi sau `text += "!"` trong method | `String` bất biến; biến tham số nhận chuỗi khác | `return text + "!"` và gán ở caller |
| `StringBuilder` lại đổi sau `append` | `append` mutate builder được chia sẻ | Nếu cần độc lập, copy builder hoặc thiết kế immutable |
| `parameter = null` nhưng caller vẫn giữ object | Chỉ biến tham số được gán `null` | Muốn caller không còn tham chiếu, caller phải tự gán `null` |
| `final Parameter` bị lỗi khi gán lại | Tham số final không được reassigned | Tránh gán lại hoặc bỏ final nếu có lý do |
| `final Box` mà object vẫn sửa được | Final biến không làm Box immutable | Thiết kế field/API immutable hoặc defensive copies |
| Gán `customer = new Customer(...)` thay vì `customer.address = ...` | Nhầm đích phép gán | Xác định caller muốn thay object hay sửa field |
| Truyền `this` và tưởng method đổi được `this` bên gọi | Java sao chép giá trị tham chiếu của `this` | Trả kết quả hoặc gọi API mutate hợp lệ |
| Tạo wrapper/holder rồi tưởng đây là pass-by-reference Java | Chỉ state của wrapper được thay | Gọi đúng là shared mutable holder |
| Gọi `method(expr)` và kỳ vọng method sửa biến nằm trong expr | Method nhận **giá trị biểu thức** | Caller tự cập nhật biến theo kết quả |

## 27. Bài tập tự kiểm tra có đáp án

### Bài 1: Tham số primitive có thay biến caller?

```java
static void increase(int n) {
    n++;
}

int value = 5;
increase(value);
System.out.println(value);
```

**Đáp án:** in `5`. `n++` cập nhật biến tham số, không cập nhật `value` ở caller.

### Bài 2: Hai biến cùng trỏ object, method làm gì?

```java
static void process(Box b) {
    b.setValue(7);
    b = new Box(9);
}

Box first = new Box(1);
Box alias = first;
process(first);
System.out.println(first.value());
System.out.println(alias.value());
```

**Đáp án:** in `7` và `7`. Cả hai biến caller vẫn tham chiếu Box cũ đã được set thành `7`. Phép `b = new Box(9)` chỉ gán lại tham số.

### Bài 3: Khi nào caller nhận object mới?

```java
static Box create(Box oldValue) {
    return new Box(oldValue.value() + 1);
}

Box box = new Box(10);
create(box);
System.out.println(box.value());
box = create(box);
System.out.println(box.value());
```

**Đáp án:** `10` rồi `11`. Lời gọi đầu không sử dụng return value, lời gọi sau có phép gán ở caller.

### Bài 4: Vì sao gán `null` không xóa object của caller?

```java
static void clear(Box box) {
    box = null;
}

Box caller = new Box(3);
clear(caller);
System.out.println(caller.value());
```

**Đáp án:** in `3`. Method chỉ đặt biến tham số `box` thành `null`; tham chiếu `caller` không đổi.

### Bài 5: Gán lại field hay tham số?

```java
class Item {
    String label;

    Item(String label) {
        this.label = label;
    }
}

class Holder {
    Item item;

    Holder(Item item) {
        this.item = item;
    }
}

static void change(Holder h) {
    h.item = new Item("New");
    h = new Holder(new Item("Other"));
}
```

Với:

```java
Holder caller = new Holder(new Item("Old"));
change(caller);
System.out.println(caller.item.label);
```

**Đáp án:** in `New`. Phép gán `h.item = ...` thay field của Holder chung; phép `h = new Holder(...)` chỉ thay tham số.

### Bài 6: Hoán đổi bằng record có thay hai biến tự động?

```java
record Pair(int x, int y) {
}

static Pair reverse(int x, int y) {
    return new Pair(y, x);
}
```

`reverse(a, b);` **không** sửa `a` hoặc `b`. Muốn cập nhật chúng:

```java
Pair result = reverse(a, b);
a = result.x();
b = result.y();
```

**Đáp án:** việc đổi biến diễn ra tại **hai dòng gán ở caller**, không phải do tham số `x`/`y` tự liên kết với `a`/`b`.

### Bài 7: Có thể làm thay đổi mảng mà không đổi biến mảng?

```java
static void process(int[] values) {
    values[0] = 8;
    values = new int[]{9};
}

int[] data = {1, 2};
process(data);
System.out.println(java.util.Arrays.toString(data));
```

**Đáp án:** `[8, 2]`. Mảng cũ bị sửa phần tử đầu. Biến `data` không trỏ mảng mới `{9}`.

### Bài 8: `final` có ngăn mutation?

```java
static void update(final Box box) {
    box.setValue(2);
    // box = new Box(3);
}
```

**Đáp án:** `box.setValue(2)` có thể hợp lệ và sửa object dùng chung. Dòng gán lại `box = new Box(3)` bị lỗi vì tham số final.

## 28. Checklist khi phân tích vì sao caller không đổi

1. **Đánh dấu tên biến caller** đang mong thay đổi (ví dụ `current`).
2. **Đọc tham số hình thức** trong method (ví dụ `Box parameter`): đây là **biến khác**.
3. **Xác định kiểu đối số:** primitive được sao chép giá trị; reference sao chép **giá trị tham chiếu**.
4. **Vẽ alias lúc bắt đầu lời gọi**: những biến nào đang trỏ cùng object?
5. **Nhìn chính xác vế trái dấu `=`**: là `parameter`, `parameter.field`, `array[i]` hay biến ở caller?
6. **Nếu `parameter = new ...`**, chỉ tham số chuyển object; đừng suy ra biến caller cũng đổi.
7. **Nếu `parameter.method()`**, đọc implementation/hợp đồng để biết đó là mutation hay trả object mới.
8. **Nếu muốn đổi biến caller**, method cần trả kết quả để caller tự viết `caller = method(caller)`, hoặc dùng một shared holder với hợp đồng rõ.
9. **Nếu có `final`**, nhớ nó giới hạn gán lại biến được bổ nghĩa, không tự khóa object.
10. **Nếu tham số ban đầu `null`**, một phép `parameter = new ...` bên trong method không tự khởi tạo biến caller đang null.
11. **Nếu là mảng/collection**, phân biệt sửa **phần tử/trạng thái** với gán lại **biến mảng/list**.
12. **Nếu dùng static/shared field**, mutation field có thể nhìn thấy từ nơi khác, nhưng đó không phải pass-by-reference của biến caller.
13. **Nếu có nhiều thread**, bổ sung phân tích đồng bộ và visibility riêng; không dùng concurrency để giải thích sai quy tắc truyền tham số.
14. **Kiểm tra bằng kết quả cụ thể**: in biến caller, in biến tham số trong method, in identity khi cần và đối chiếu sơ đồ tham chiếu.

## Ghi nhớ

- Java **chỉ truyền đối số theo giá trị**. Một tham số hình thức luôn là **biến riêng** của lần gọi, được khởi tạo từ giá trị biểu thức đối số.
- Với primitive, method nhận **bản sao giá trị primitive**. Với object, method nhận **bản sao giá trị tham chiếu**, không phải bản sao toàn bộ object.
- **`parameter = ...` không gán lại `callerVariable`**; hai biến độc lập dù ban đầu cùng trỏ một object.
- **`parameter.field = ...` hoặc lời gọi mutator** có thể sửa **object dùng chung**, khiến caller thấy trạng thái đổi **mà biến caller vẫn giữ nguyên tham chiếu**.
- Gán `null`, tạo object mới hoặc hoán đổi hai tham số **không tự thay biến của caller**.
- Cần thay biến caller? **Trả giá trị mới rồi gán ở caller**: `current = transform(current);`. Cần sửa trạng thái chung? Thiết kế API mutator hoặc holder phù hợp và nêu rõ side effect.
- **Phân biệt ba thứ** khi đọc code: *biến tham số*, *biến bên gọi* và *đối tượng được tham chiếu*. Khi tách đúng ba thứ này, hiện tượng “gán lại tham số không thay biến của bên gọi” sẽ không còn khó hiểu.
