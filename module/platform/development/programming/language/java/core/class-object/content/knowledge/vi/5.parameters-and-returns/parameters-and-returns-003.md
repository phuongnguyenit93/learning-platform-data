# Tham số kiểu nguyên thủy và tham số kiểu tham chiếu trong Java

Khi gọi một phương thức, Java chuyển **giá trị của đối số (argument)** cho **tham số (parameter)**. Điều quan trọng nhất cần nhớ là: **Java luôn truyền đối số bằng giá trị (pass-by-value)**, cho cả kiểu nguyên thủy lẫn kiểu tham chiếu.

Sự khác biệt nằm ở **giá trị nào được sao chép**:

- Với tham số kiểu nguyên thủy như `int`, `double`, `boolean`, Java sao chép **giá trị nguyên thủy**. Gán lại tham số không làm thay đổi biến nguyên thủy của bên gọi.
- Với tham số kiểu tham chiếu như `Student`, `StringBuilder`, `int[]`, Java sao chép **giá trị tham chiếu** đến đối tượng. Hai biến có thể cùng trỏ đến một đối tượng. Phương thức có thể sửa trạng thái đối tượng đó nếu đối tượng cho phép, nhưng **gán lại tham số** không gán lại biến của bên gọi.

Câu “truyền object theo tham chiếu” thường khiến người mới học hiểu sai rằng phương thức nhận quyền gán lại biến ở bên gọi. Trong Java, **không có cơ chế pass-by-reference cho biến của bên gọi**. Để hiểu chính xác, ta cần tách bốn thứ: **biến**, **giá trị biến**, **đối tượng** và **phép gán/thay đổi trạng thái**.

## 1. Ôn lại: đối số, tham số và kiểu dữ liệu

Một **đối số** là biểu thức được viết tại điểm gọi; một **tham số** là biến được khai báo trong chữ ký của phương thức.

~~~java
static int increase(int number) {
    return number + 1;
}

// Trong một phương thức khác:
int score = 10;
int result = increase(score);
~~~

Đây là các **đoạn mã minh họa**, cần đặt trong class/method thích hợp. `score` là biến ở bên gọi; biểu thức `score` trong `increase(score)` là đối số. `number` là tham số của `increase`. `increase` trả `11`, còn `score` vẫn là `10`.

### Hai nhóm kiểu liên quan

| Nhóm | Kiểu ví dụ | Giá trị được chuyển khi gọi phương thức |
| --- | --- | --- |
| Nguyên thủy (primitive) | `byte`, `short`, `int`, `long`, `float`, `double`, `char`, `boolean` | Giá trị số, ký tự hoặc logic, sau chuyển đổi được Java cho phép |
| Tham chiếu (reference) | Class tự định nghĩa như `Account`, `String`, `Integer`, interface type, array như `int[]` | Giá trị tham chiếu đến đối tượng, hoặc `null` |

`String` là class; `Integer` là wrapper class; **mảng cũng là object**. Vì thế chúng đều thuộc nhóm kiểu tham chiếu. Một object có thể chứa nhiều trường primitive, nhưng biến có kiểu class không “chứa toàn bộ object” theo nghĩa sao chép tất cả trường khi truyền tham số.

Mỗi tham số nhận giá trị của đối số theo quy tắc chuyển đổi khi gọi phương thức. Ví dụ một `int` có thể được widening thành `long` khi phương thức yêu cầu `long`. Đó vẫn là **truyền bằng giá trị**.

## 2. Tham số nguyên thủy: sửa tham số không sửa biến của caller

Lưu chương trình sau thành **`PrimitiveParameterDemo.java`**:

~~~java
public class PrimitiveParameterDemo {
    static void change(int number, boolean enabled) {
        System.out.println("inside before: " + number + ", " + enabled);

        number = 99;
        enabled = false;

        System.out.println("inside after: " + number + ", " + enabled);
    }

    public static void main(String[] args) {
        int score = 10;
        boolean active = true;

        change(score, active);

        System.out.println("outside: " + score + ", " + active);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 PrimitiveParameterDemo.java
java PrimitiveParameterDemo
~~~

Stdout:

~~~text
inside before: 10, true
inside after: 99, false
outside: 10, true
~~~

Khi gọi `change(score, active)`:

1. Java đọc giá trị của `score` là `10` và `active` là `true`.
2. Những giá trị này được đưa vào tham số mới có tên `number` và `enabled` của **lần gọi `change`**.
3. Gán `number = 99` và `enabled = false` chỉ thay đổi hai tham số đó.
4. Phương thức kết thúc; caller tiếp tục với `score = 10` và `active = true`.

Sơ đồ khái niệm:

~~~text
main()                          change(...)
  score  = 10    --copy 10-->    number  = 10 -> 99
  active = true  --copy ---->    enabled = true -> false

Sau change(): score = 10, active = true
~~~

Không có mũi tên liên kết làm một biến nguyên thủy ở caller tự cập nhật theo tham số. **Tên biến ở hai phía không bắt buộc giống nhau**; tính độc lập đến từ cơ chế truyền giá trị, không từ việc đặt tên.

### Đừng nhầm với phép gán ở bên gọi

~~~java
int score = 10;
score = increase(score);
~~~

Ở đây `score` **thay đổi** nếu `increase` trả giá trị khác, nhưng lý do là bên gọi thực hiện phép gán `score = ...`. Phương thức không tự viết lại biến `score` ở caller.

Với method `static int increase(int number) { return number + 1; }`, câu lệnh trên làm `score` thành `11`. Đây là thiết kế thường nên dùng nếu muốn tính toán ra **giá trị primitive mới** rồi cho caller quyết định có cập nhật biến hay không.

## 3. Tham số tham chiếu: sao chép tham chiếu, không sao chép object

Xét class:

~~~java
class Counter {
    int value;

    Counter(int value) {
        this.value = value;
    }
}
~~~

Một biến `Counter counter` giữ **giá trị tham chiếu** đến một Counter instance. Khi truyền biến này cho phương thức `update(Counter parameter)`, Java sao chép tham chiếu đó vào biến tham số `parameter`.

~~~text
Trước lời gọi:
caller.counter -------> Counter #1 { value = 5 }

Trong lời gọi:
caller.counter ---+
                  +----> Counter #1 { value = 5 }
callee.parameter -+
~~~

Hai biến khác nhau đang chứa các giá trị tham chiếu dẫn tới **cùng một object**. Thao tác `parameter.value = 20` thay đổi trường của object #1, nên đọc qua `caller.counter.value` cũng thấy `20`. Ngược lại, `parameter = new Counter(100)` chỉ làm **tham số** trỏ sang instance mới; biến của caller vẫn trỏ object #1.

### Ví dụ chạy độc lập: sửa object và gán lại tham số

Tạo file **`ReferenceParameterDemo.java`**:

~~~java
public class ReferenceParameterDemo {
    static final class Counter {
        private int value;

        Counter(int value) {
            this.value = value;
        }

        int getValue() {
            return value;
        }

        void setValue(int nextValue) {
            value = nextValue;
        }
    }

    static void change(Counter parameter) {
        parameter.setValue(20);
        System.out.println("after mutation: " + parameter.getValue());

        parameter = new Counter(100);
        System.out.println("after reassignment: " + parameter.getValue());
    }

    public static void main(String[] args) {
        Counter counter = new Counter(5);

        change(counter);

        System.out.println("caller: " + counter.getValue());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceParameterDemo.java
java ReferenceParameterDemo
~~~

Stdout:

~~~text
after mutation: 20
after reassignment: 100
caller: 20
~~~

Phân tích chính xác:

- Sau `parameter.setValue(20)`, **object đang được chia sẻ** có `value = 20`.
- Sau `parameter = new Counter(100)`, **tham số** được gán tham chiếu đến một object khác. Object mới có `value = 100`.
- Biến `counter` của caller chưa hề được gán tham chiếu mới. Nó vẫn tham chiếu đến object đầu có `value = 20`.
- Việc phương thức kết thúc không tự hoàn tác biến đổi trạng thái đã thực hiện trên object đầu.

Sơ đồ sau lệnh gán lại **ở bên trong `change`**:

~~~text
caller.counter ----------> Counter #1 { value = 20 }

callee.parameter --------> Counter #2 { value = 100 }
~~~

Hình này diễn tả **danh tính đối tượng và quan hệ tham chiếu**, không phải địa chỉ thực tế do JVM cấp phát. Không cần quan sát địa chỉ bộ nhớ để giải thích kết quả chương trình.

## 4. Phân biệt “sửa đối tượng” và “đổi tham chiếu”

Có ba thao tác viết khá giống nhau nhưng tác dụng khác:

| Đoạn lệnh trong method | Tác động | Caller có thấy thay đổi? |
| --- | --- | --- |
| `value = 7;` với `value` là tham số `int` | Gán lại tham số nguyên thủy | Không, trừ khi caller tự dùng giá trị được trả về |
| `item.setCount(7);` hoặc `item.count = 7;` nếu truy cập hợp lệ | Sửa **trạng thái object** mà tham số trỏ tới | Có, nếu caller vẫn quan sát cùng object |
| `item = new Item();` | Gán tham chiếu mới vào **biến tham số** | Không làm biến tham chiếu ở caller trỏ sang Item mới |

Một object có thể bất biến hoặc không cho phép sửa field từ phương thức; khi đó việc có một tham chiếu không tự cấp quyền thay đổi. Khả năng sửa phụ thuộc API, access modifier và thiết kế object, không phụ thuộc cơ chế truyền tham số.

### Chuyển giá trị tham chiếu qua nhiều phương thức

Nếu `main` gọi `service.process(account)` và `process` gọi tiếp `validate(account)`, mỗi lần gọi lại có **tham số riêng chứa bản sao giá trị tham chiếu**. Các tham số có thể cùng trỏ đến một object. Đó là lý do một sự thay đổi trạng thái qua nhiều tầng method có thể được quan sát ở caller đầu tiên.

Tuy nhiên, ở bất kỳ tầng nào, phép gán `account = anotherAccount` chỉ thay đổi **biến tại tầng đó**. Nó không đi ngược lên và gán lại mọi biến có cùng tên ở các caller.

## 5. Mảng cũng được truyền bằng giá trị tham chiếu

Mảng như `int[]` là **reference type**. Method có thể thay đổi phần tử trong mảng đang được chia sẻ nhưng không thể gán lại biến mảng của caller bằng cách gán tham số.

Tạo file **`ArrayParameterDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayParameterDemo {
    static void edit(int[] values) {
        values[0] = 99;
        values = new int[] {7, 8, 9};
        values[1] = 42;
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};

        edit(numbers);

        System.out.println("caller: " + Arrays.toString(numbers));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArrayParameterDemo.java
java ArrayParameterDemo
~~~

Stdout:

~~~text
caller: [99, 2, 3]
~~~

Giải thích:

1. Parameter `values` ban đầu và biến `numbers` cùng trỏ đến mảng `[1, 2, 3]`.
2. `values[0] = 99` ghi vào phần tử đầu của **mảng chung**, nên caller thấy `[99, 2, 3]`.
3. `values = new int[] {7, 8, 9}` đổi tham chiếu của **parameter** sang mảng mới.
4. `values[1] = 42` sửa mảng mới thành `[7, 42, 9]`, không đụng đến mảng `numbers` ban đầu.

### `int[]` là reference type dù phần tử là primitive

Một mảng `int[]` chứa các phần tử primitive `int`, nhưng **biến mảng** vẫn là tham chiếu đến object mảng. Do đó:

- `numbers[0]` là một giá trị `int`;
- `numbers` là một giá trị tham chiếu;
- `edit(numbers)` sao chép tham chiếu;
- `edit(numbers[0])`, nếu method có tham số `int` tương ứng, sẽ sao chép giá trị nguyên thủy của một phần tử.

Đây là sự phân biệt giữa **kiểu của phần tử** và **kiểu của đối số truyền vào method**.

### Muốn thay mảng của caller thì trả mảng mới

Một API có thể trả về mảng mới:

~~~java
static int[] replaceWithNewArray(int[] oldValues) {
    return new int[] {7, 8, 9};
}

// Trong caller:
numbers = replaceWithNewArray(numbers);
~~~

Đây là **đoạn minh họa**, cần đặt trong class và method tương ứng. Phép gán `numbers = ...` **ở caller** mới khiến biến `numbers` giữ tham chiếu tới mảng được trả về. Việc method trả tham chiếu không tự thay đổi biến caller nếu caller bỏ qua kết quả.

## 6. Không thể đổi chỗ hai biến tham chiếu của caller chỉ bằng hai tham số

Một lỗi phổ biến là viết `swap(a, b)` rồi kỳ vọng hai biến ở bên gọi đổi object cho nhau.

Tạo file **`SwapParameterDemo.java`**:

~~~java
public class SwapParameterDemo {
    static final class Box {
        final String label;

        Box(String label) {
            this.label = label;
        }
    }

    static void swap(Box first, Box second) {
        Box temporary = first;
        first = second;
        second = temporary;

        System.out.println("inside: " + first.label + ", " + second.label);
    }

    public static void main(String[] args) {
        Box left = new Box("LEFT");
        Box right = new Box("RIGHT");

        swap(left, right);

        System.out.println("outside: " + left.label + ", " + right.label);
    }
}
~~~

~~~bash
javac -encoding UTF-8 SwapParameterDemo.java
java SwapParameterDemo
~~~

Stdout:

~~~text
inside: RIGHT, LEFT
outside: LEFT, RIGHT
~~~

Method đã hoán đổi **hai biến tham số của nó**, nên dòng in trong method cho `RIGHT, LEFT`. Biến `left` và `right` trong `main` không bị gán lại; dòng in ngoài vẫn `LEFT, RIGHT`.

Nếu mục tiêu là thay đổi thứ tự **hai phần tử của một mảng**, method có thể sửa nội dung mảng được chia sẻ:

~~~java
static void swapElements(Box[] boxes) {
    Box temporary = boxes[0];
    boxes[0] = boxes[1];
    boxes[1] = temporary;
}
~~~

Đây là **đoạn method minh họa**; chỉ hợp lệ khi `Box[]` có ít nhất hai phần tử và mảng khác `null`. Method này có thể thay đổi **các phần tử của object mảng** mà caller truyền vào, chứ không trao đổi hai biến tham chiếu độc lập của caller.

Trong thực tế, phương thức nhận một container mutable hoặc trả về kết quả mới thường rõ nghĩa hơn API mong đợi can thiệp trực tiếp vào biến của caller.

## 7. `String`, wrapper và object bất biến: tham chiếu không có nghĩa sửa được

Một số class như `String` và các wrapper class `Integer`, `Long`, `Boolean` được thiết kế bất biến. Phương thức có thể tính chuỗi hoặc giá trị wrapper mới rồi **gán lại tham số**, nhưng không sửa trạng thái bên trong object cũ như với một `StringBuilder` mutable.

Tạo file **`ImmutableAndMutableDemo.java`**:

~~~java
public class ImmutableAndMutableDemo {
    static void update(String text, Integer number, StringBuilder builder) {
        text = text + "!";
        number = number + 1;
        builder.append("!");

        System.out.println("inside text: " + text);
        System.out.println("inside number: " + number);
        System.out.println("inside builder: " + builder);
    }

    public static void main(String[] args) {
        String text = "Java";
        Integer number = 10;
        StringBuilder builder = new StringBuilder("Java");

        update(text, number, builder);

        System.out.println("outside text: " + text);
        System.out.println("outside number: " + number);
        System.out.println("outside builder: " + builder);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableAndMutableDemo.java
java ImmutableAndMutableDemo
~~~

Stdout:

~~~text
inside text: Java!
inside number: 11
inside builder: Java!
outside text: Java
outside number: 10
outside builder: Java!
~~~

Lý do:

- `String` là immutable. Biểu thức `text + "!"` tạo nội dung chuỗi mới; `text = ...` gán tham chiếu mới **chỉ cho parameter `text`**.
- `Integer` là immutable. Biểu thức `number + 1` có quá trình unboxing, tính số rồi boxing (chi tiết có thể được tối ưu hóa); việc `number = ...` đổi tham chiếu của parameter, không làm biến `number` ở caller nhận giá trị mới.
- `StringBuilder` là mutable. `builder.append("!")` sửa trạng thái object mà cả parameter và caller cùng trỏ tới, nên caller thấy `Java!`.

**Tránh suy luận rằng “reference type thì lúc nào truyền vào method cũng sẽ thay đổi”.** Cơ chế truyền là giống nhau đối với mọi reference type; điều khác biệt là method thực hiện **gán lại parameter** hay **gọi hành vi sửa state object**.

### Kiểu nguyên thủy khác wrapper type

`int` và `Integer` không phải cùng kiểu:

- `int` luôn chứa một giá trị số nguyên trong miền kiểu `int`, không chứa `null`.
- `Integer` là reference type, có thể là `null`; auto-unboxing một giá trị `Integer` null gây `NullPointerException`.
- Một lời gọi có thể thực hiện boxing/unboxing theo quy tắc overload và conversion của Java, nhưng điều đó **không biến Java thành pass-by-reference**.
- Không nên dùng `==` để so sánh nội dung hai wrapper object nếu mục tiêu là bằng nhau theo giá trị: so sánh đúng kiểu phù hợp, như `Integer.equals` với xử lý null thích hợp, hoặc unbox có kiểm soát.

## 8. `null` cũng là một giá trị tham chiếu được truyền bằng giá trị

Nếu đối số là `null` hoặc một biến tham chiếu đang là `null`, tham số nhận giá trị null tương ứng. Không có object nào đằng sau null để method sửa.

~~~java
static void requireName(String name) {
    if (name == null) {
        throw new IllegalArgumentException("name is required");
    }
    System.out.println(name.length());
}
~~~

Đây là **đoạn method minh họa**, không phải chương trình độc lập. Nếu gọi `requireName(null)`, method ném `IllegalArgumentException` đã khai báo trong thân. Nếu bỏ câu lệnh kiểm tra rồi gọi `name.length()`, sẽ xảy ra `NullPointerException` vì receiver là null.

Một method có thể gán tham số null sang object mới:

~~~java
static void createIfMissing(StringBuilder value) {
    if (value == null) {
        value = new StringBuilder("created");
    }
}
~~~

Nhưng gọi `createIfMissing(null)` **không tạo object rồi tự đưa nó vào biến tham chiếu của caller**. Object mới chỉ được gán cho parameter `value`. Muốn nhận object mới, caller cần method **trả về tham chiếu**, chẳng hạn:

~~~java
static StringBuilder ensureValue(StringBuilder value) {
    return value == null ? new StringBuilder("created") : value;
}

// Trong caller:
StringBuilder result = ensureValue(null);
~~~

Các đoạn trên là ví dụ về cách xử lý tham chiếu, cần đặt trong class/method thích hợp.

## 9. Tham số `final`: không gán lại tham số nhưng vẫn có thể sửa object

Java cho phép khai báo tham số là `final`:

~~~java
static void rename(final StringBuilder builder) {
    builder.append("!");
    // builder = new StringBuilder("other"); // Lỗi biên dịch.
}
~~~

Trong method minh họa này, `final` ngăn phép gán tham chiếu mới vào biến tham số `builder`. Nó **không** ngăn `builder.append("!")` sửa StringBuilder. Tương tự, `final int number` không cho gán lại `number`.

Vì vậy:

- `final` trên **biến** quản lý khả năng gán lại biến.
- Bất biến của **object** là đặc tính thiết kế của class và toàn bộ những dữ liệu quan sát được của nó.
- `final` không thay đổi quy tắc pass-by-value.

Khai báo `final` giúp tránh vô tình gán lại tên tham số trong những method phức tạp, nhưng không bắt buộc để method sử dụng đúng cơ chế truyền tham số.

## 10. Tham chiếu đến object chứa field primitive: phân biệt hai tầng dữ liệu

Giả sử có:

~~~java
class Player {
    private int score;

    Player(int score) {
        this.score = score;
    }

    void addPoints(int points) {
        score += points;
    }
}
~~~

Các field `score` và tham số `points` đều là primitive `int`, nhưng lời gọi `player.addPoints(5)` là **instance method trên object `player`**. Trong method, phép `score += points` cập nhật **field primitive nằm trong trạng thái của object**, nên caller đọc qua object sau đó sẽ thấy score đổi.

Điều này không chứng minh phương thức nhận primitive bằng tham chiếu; thực tế:

- `points` nhận bản sao giá trị `5`.
- `this` trong `addPoints` biểu thị Player hiện tại.
- Phương thức cập nhật field `this.score` của object đó.
- Việc sửa field khác với việc gán lại biến `points` của caller.

Cần luôn trả lời câu hỏi: **Lệnh gán đang viết vào tham số, biến cục bộ, field của object, phần tử mảng hay biến của chính caller?** Hình thức `=` giống nhau nhưng mục tiêu là các vị trí lưu trữ khác nhau.

## 11. Truyền reference và vấn đề alias, đóng gói

Vì nhiều biến có thể tham chiếu tới cùng object mutable, code bên ngoài có thể sửa dữ liệu chung theo cách không mong muốn nếu API để lộ trực tiếp tham chiếu nội bộ.

Ví dụ class chưa an toàn về đóng gói:

~~~java
class ScoreBook {
    private final int[] scores;

    ScoreBook(int[] scores) {
        this.scores = scores;
    }

    int[] scores() {
        return scores;
    }
}
~~~

Đây là **class minh họa**. Constructor giữ đúng tham chiếu `scores` từ caller; method `scores()` lại trả tham chiếu đến mảng nội bộ. Caller có thể sửa `scores[0]` sau khi truyền vào, hoặc sửa phần tử của mảng nhận về. Không có bước sao chép mảng nào diễn ra tự động khi qua ranh giới method.

Một cách dùng defensive copy:

~~~java
class ScoreBook {
    private final int[] scores;

    ScoreBook(int[] scores) {
        if (scores == null) {
            throw new IllegalArgumentException("scores is required");
        }
        this.scores = scores.clone();
    }

    int[] scores() {
        return scores.clone();
    }
}
~~~

Đây là **phiên bản thay thế** cho class `ScoreBook` ở trên, không phải class được khai báo thêm cùng tên trong cùng package. Vì mảng chứa phần tử `int` nguyên thủy, `clone()` tạo mảng mới với giá trị từng phần tử được sao chép. Caller sửa mảng cũ hoặc mảng trả về sẽ không làm đổi mảng bên trong `ScoreBook`.

Với mảng các object mutable, `clone()` chỉ sao chép **cấu trúc mảng và các tham chiếu phần tử**, không tự sao chép sâu từng object bên trong. Muốn bất biến sâu cần thiết kế việc sao chép các phần tử hoặc dùng những kiểu bất biến phù hợp.

### Đặt hợp đồng method rõ ràng

Một API nên nói rõ method có được thay đổi object của caller không:

- `sortInPlace(int[] values)` có thể được thiết kế để sửa phần tử mảng truyền vào.
- `sortedCopy(int[] values)` có thể trả một mảng mới, giữ nguyên mảng caller.
- `addPoints(Player player, int points)` có thể sửa state Player.
- `calculateScore(Player player)` có thể chỉ đọc, không sửa state.
- `withName(String newName)` trên một value object có thể trả object mới thay vì sửa object hiện tại.

Các tên trên là **gợi ý thiết kế API**, không phải phương thức Java chuẩn có sẵn. Dù mỗi method chọn chính sách gì, việc truyền đối số vẫn tuân thủ pass-by-value.

## 12. Giá trị trả về là cách thông thường để thông báo giá trị mới

Muốn cập nhật một biến primitive của caller, method có thể trả giá trị mới:

~~~java
static int addBonus(int oldScore, int bonus) {
    return Math.addExact(oldScore, bonus);
}

// Trong caller:
int score = 10;
score = addBonus(score, 5);
~~~

`score` trở thành `15` vì caller chủ động gán giá trị `return`. Nếu bỏ phép gán và chỉ gọi `addBonus(score, 5);` thì biến `score` vẫn là `10`.

Muốn thay tham chiếu của caller, method cũng có thể trả object:

~~~java
static StringBuilder replace(StringBuilder original) {
    return new StringBuilder("new");
}

// Trong caller:
StringBuilder builder = new StringBuilder("old");
builder = replace(builder);
~~~

Phép gán ở caller khiến `builder` trỏ đến StringBuilder mới. Object cũ không nhất thiết bị thu gom ngay, vì điều đó phụ thuộc những đường tham chiếu còn lại và cơ chế GC.

**Đừng sử dụng parameter làm “output parameter” bằng việc tự gán lại nó rồi kỳ vọng caller thấy tham chiếu mới.** Java không cung cấp cú pháp `ref`/`out` parameter như ở một số ngôn ngữ khác.

## 13. Varargs thực chất vẫn là tham số mảng

Khai báo `int... values` cho phép truyền số lượng đối số `int` thay đổi. Trong thân method, `values` có kiểu `int[]`.

Tạo file **`VarargsParameterDemo.java`**:

~~~java
import java.util.Arrays;

public class VarargsParameterDemo {
    static void change(int... values) {
        if (values.length > 0) {
            values[0] = 77;
        }
        System.out.println("inside: " + Arrays.toString(values));
    }

    public static void main(String[] args) {
        int[] existing = {1, 2};

        change(existing);
        System.out.println("existing: " + Arrays.toString(existing));

        change(3, 4);
    }
}
~~~

~~~bash
javac -encoding UTF-8 VarargsParameterDemo.java
java VarargsParameterDemo
~~~

Stdout:

~~~text
inside: [77, 2]
existing: [77, 2]
inside: [77, 4]
~~~

Khi gọi `change(existing)`, method nhận tham chiếu đến chính mảng `existing`; sửa `values[0]` làm caller thấy phần tử đổi. Khi gọi `change(3, 4)`, cơ chế varargs tạo mảng đối số tương ứng cho lời gọi, và method sửa mảng đó. Không có một biến mảng tên `existing` nào ở caller của lần gọi thứ hai bị cập nhật.

Đây là lý do varargs cần được hiểu qua **kiểu mảng thực tế** của parameter. Trong ví dụ, thao tác thay phần tử là cố ý để quan sát alias; nhiều API varargs nên chỉ đọc dữ liệu đầu vào để tránh side effect bất ngờ.

## 14. Thứ tự đánh giá đối số: mỗi biểu thức chạy trước khi thân method

Một lời gọi `combine(first(), second())` phải đánh giá đối số trước khi method đích bắt đầu. Java quy định thứ tự đánh giá các biểu thức đối số **từ trái qua phải**. Các tác dụng phụ khi tính đối số có thể làm thay đổi giá trị được chuyển vào method.

Tạo file **`ArgumentOrderDemo.java`**:

~~~java
public class ArgumentOrderDemo {
    static int trace(String name, int value) {
        System.out.println(name + "=" + value);
        return value;
    }

    static void receive(int first, int second) {
        System.out.println("received=" + first + "," + second);
    }

    public static void main(String[] args) {
        int number = 3;

        receive(
                trace("left", number++),
                trace("right", number)
        );

        System.out.println("number=" + number);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArgumentOrderDemo.java
java ArgumentOrderDemo
~~~

Stdout:

~~~text
left=3
right=4
received=3,4
number=4
~~~

Đối số đầu tiên `number++` có giá trị biểu thức là `3`, đồng thời cập nhật **biến ở caller** lên `4` trước khi đánh giá đối số thứ hai. Vì vậy `trace("right", number)` nhận `4`.

Ví dụ này nhấn mạnh hai cơ chế độc lập:

1. Java đánh giá đối số từ trái sang phải và có thể thực hiện side effect **ngay tại caller**.
2. Sau đó method đích nhận giá trị đã tính vào các parameter riêng.

Nếu trong method `receive` có câu lệnh `first = 100;`, phép gán này vẫn không làm `number` trong `main` đổi thêm. Trong code thực tế, việc sửa biến ngay trong danh sách argument thường gây khó đọc; cân nhắc tách thành các câu lệnh rõ ràng.

## 15. Khi có exception: tham số chưa chắc đã được truyền đủ

Một biểu thức đối số có thể ném exception. Nếu một argument chưa đánh giá xong thì lời gọi method đích có thể không bắt đầu.

~~~java
static int fail() {
    throw new IllegalStateException("argument failed");
}

static void show(int a, int b) {
    System.out.println("show called");
}

// Trong caller:
show(1, fail());
~~~

Đây là các **đoạn minh họa**, không phải chương trình độc lập. Với lời gọi `show(1, fail())`, biểu thức `fail()` ném exception trong lúc chuẩn bị đối số thứ hai; thân `show` **không chạy** và dòng `show called` không được in. Nếu caller có `catch` phù hợp, nó có thể xử lý exception.

Trường hợp khác, nếu tham số là `null` và method truy cập `parameter.field`, exception có thể xuất hiện **bên trong thân method**. Hai trường hợp có stack trace khác nhau nên cần kiểm tra vị trí exception thật sự phát sinh.

## 16. Boxing, overload và kiểu tham số được chọn

Kiểu tham số trong chữ ký method quyết định những chuyển đổi được phép khi gọi. Ví dụ:

~~~java
static void print(long number) {
    System.out.println("long=" + number);
}

static void print(Integer number) {
    System.out.println("Integer=" + number);
}
~~~

Đây là **cặp method minh họa**, cần đặt trong class và gọi từ method thích hợp. Khi gọi `print(5)` với literal `int`, Java ưu tiên widening primitive sang `long` so với boxing sang `Integer` trong quy tắc overload tương ứng, nên chọn `print(long)`.

Đừng suy luận “vì `Integer` là object nên Java đã truyền theo tham chiếu”. Overload resolution quyết định **phương thức nào được gọi**; pass-by-value quyết định **tham số của phương thức đã chọn nhận giá trị nào**. Hai cơ chế thuộc hai giai đoạn/khía cạnh khác nhau.

Một số điều cần nhớ về wrapper:

- `Integer a = 5;` có thể sử dụng autoboxing để tạo/nhận giá trị wrapper.
- `int b = a;` sử dụng unboxing, và nếu `a == null` thì có thể ném `NullPointerException`.
- `Integer` không có setter thay đổi giá trị nguyên của instance. Gán `a = a + 1` là tạo/nhận giá trị wrapper khác để biến `a` tham chiếu tới, không sửa wrapper cũ.
- `==` giữa hai tham chiếu wrapper kiểm tra cùng instance, không nhất thiết cùng giá trị. Khi so sánh logic, dùng `equals` đúng hợp đồng và xử lý null.

## 17. “Truyền cùng object” không đồng nghĩa “được sửa object an toàn từ nhiều luồng”

Một object mutable có thể được chia sẻ bởi nhiều tham chiếu trong một thread hoặc giữa các thread. Khả năng cùng trỏ đến một object giải thích vì sao một method có thể làm trạng thái thay đổi, nhưng **không tự tạo ra cơ chế đồng bộ**.

~~~java
class UnsafeCounter {
    int value;

    void increment() {
        value++;
    }
}
~~~

Đây là class minh họa. Nếu nhiều thread đồng thời gọi `increment()` trên **cùng instance**, phép `value++` không bảo đảm cập nhật nguyên tử; có thể mất cập nhật hoặc gặp vấn đề visibility theo Java Memory Model. Một parameter chứa tham chiếu đến Counter không khiến hành vi đột nhiên thread-safe. Khi học concurrency, cần chọn synchronization, atomic types hoặc mô hình bất biến phù hợp.

Trong bài này, các chương trình chạy tuần tự để tập trung vào cơ chế primitive/reference. Đừng lẫn khái niệm pass-by-value với vấn đề chạy đồng thời.

## 18. Các nhầm lẫn phổ biến

| Phát biểu dễ sai | Cách hiểu đúng |
| --- | --- |
| “Primitive pass-by-value, object pass-by-reference.” | Cả hai đều pass-by-value; với object, giá trị được sao chép là **tham chiếu**. |
| “Gọi method với object sẽ tạo bản sao object.” | Chỉ sao chép tham chiếu; không clone các field một cách tự động. |
| “Gán lại parameter sẽ gán lại biến caller.” | Parameter là biến riêng của lần gọi, không thể gán lại biến caller qua phép gán đó. |
| “Sửa một field qua parameter không ảnh hưởng caller.” | Nếu caller và parameter cùng trỏ đến object mutable thì caller có thể quan sát field đã đổi. |
| “Mảng chứa int nên truyền như một int.” | `int[]` là reference type; element `int` là primitive. |
| “`String` là reference type nên nối chuỗi thay đổi string gốc.” | `String` immutable; phép nối cho giá trị chuỗi mới. |
| “`Integer` là primitive giống `int`.” | `Integer` là wrapper object, có thể null và immutable. |
| “`final` parameter ngăn sửa mọi object.” | Nó ngăn gán lại biến parameter, không tự ngăn gọi method mutable trên object. |
| “Method có thể swap hai biến object của caller bằng cách swap parameters.” | Chỉ swap hai tham số; cần caller gán kết quả hoặc sửa nội dung container có chủ đích. |
| “Một biến reference ra khỏi scope thì object chắc chắn biến mất.” | Object có thể có alias khác; thời điểm GC không được bảo đảm. |
| “Method nhận object là đương nhiên có thể sửa field private.” | Phương thức phải có quyền truy cập hoặc được cung cấp API phù hợp. |
| “Giá trị return của object là object được copy sâu.” | Trả reference thông thường chỉ trả giá trị tham chiếu, không deep copy. |

## 19. Bài tự kiểm tra: đọc mã trước khi nhìn kết quả

### Bài 1 — Primitive độc lập

~~~java
static void increase(int n) {
    n++;
}

// Trong caller:
int x = 2;
increase(x);
System.out.println(x);
~~~

Kết quả là **`2`**. Câu lệnh `n++` thay đổi tham số `n`. Nếu đổi method thành `static int increase(int n) { return n + 1; }` rồi viết `x = increase(x);`, kết quả là **`3`** vì caller gán giá trị trả về.

### Bài 2 — Reference cùng object

~~~java
class Item {
    int count;
}

static void fill(Item p) {
    p.count = 7;
}

// Trong caller:
Item a = new Item();
fill(a);
System.out.println(a.count);
~~~

Kết quả là **`7`**. Tham số `p` và biến `a` cùng tham chiếu đến một Item. Tên biến khác nhau không tạo object khác nhau.

### Bài 3 — Gán lại tham số không đổi caller

~~~java
static void reset(Item p) {
    p = new Item();
    p.count = 50;
}

// Trong caller, sau khi đã có a.count = 7:
reset(a);
System.out.println(a.count);
~~~

Kết quả vẫn là **`7`**, bởi `reset` chỉ gán tham chiếu mới cho parameter `p` rồi sửa Item mới. Item mà `a` trỏ tới không bị sửa.

### Bài 4 — Array alias

~~~java
static void replaceFirst(int[] array) {
    array[0] = -1;
    array = new int[] {100, 200};
}

// Trong caller:
int[] data = {5, 6};
replaceFirst(data);
System.out.println(data[0]);
~~~

Kết quả là **`-1`**. Dòng đầu sửa mảng caller; dòng sau chỉ gán biến parameter sang mảng mới.

### Bài 5 — Phân biệt String và StringBuilder

~~~java
static void modify(String text, StringBuilder builder) {
    text += "!";
    builder.append("!");
}

// Trong caller:
String a = "Go";
StringBuilder b = new StringBuilder("Go");
modify(a, b);
System.out.println(a + " / " + b);
~~~

Kết quả:

~~~text
Go / Go!
~~~

Biểu thức `text += "!"` trong method gán lại tham số String; `builder.append("!")` sửa StringBuilder chung.

Các đoạn Bài 1–5 là **mảnh mã dành để ghép vào class/method thử nghiệm**, không phải từng chương trình độc lập. Có thể dựa trên những file chạy hoàn chỉnh ở các mục trước để tự thử.

## 20. Checklist khi thiết kế phương thức

Trước khi viết hoặc gọi một method, hãy hỏi:

1. **Tham số là primitive hay reference type?** Mảng và wrapper là reference type, dù phần tử/nội dung liên quan tới số nguyên.
2. **Phương thức gán lại parameter hay sửa object?** `parameter = ...` khác `parameter.field = ...` hoặc `parameter.mutate()`.
3. **Caller cần giá trị mới hay side effect?** Nếu cần cập nhật một biến riêng của caller, thường dùng `return` rồi gán kết quả tại caller.
4. **Có alias khác không?** Những thành phần khác cùng giữ tham chiếu đến object mutable có thể quan sát sự thay đổi.
5. **Object có bất biến không?** `String` và `Integer` không có trạng thái nội bộ được thay đổi qua các thao tác như ví dụ mutable.
6. **Có thể có `null` không?** Kiểm tra tại ranh giới đầu vào nếu null không hợp lệ.
7. **Có cần bản sao phòng vệ không?** Đặc biệt khi nhận/trả mảng hoặc collections mutable.
8. **Phương thức có hợp đồng rõ về thay đổi state không?** Tên method, tài liệu và test nên thể hiện khi nào input được sửa.
9. **Có ca biên hoặc exception nào trước khi gọi xong không?** Đối số cũng là biểu thức Java được đánh giá và có thể có side effect.
10. **Có nhiều thread cùng sửa object không?** Cần thiết kế đồng bộ độc lập với cơ chế truyền tham số.

**Kết luận học tập:** Khi gặp một phương thức Java, hãy hình dung rằng **mỗi parameter là một biến riêng được nạp bằng bản sao giá trị đối số**. Với primitive, bản sao là giá trị nguyên thủy. Với reference, bản sao là tham chiếu có thể dẫn đến cùng object. Từ mô hình này, bạn sẽ giải thích đúng hành vi của việc gán tham số, sửa field, thay phần tử mảng, nối chuỗi, trả object mới và những trường hợp alias trong code Java thực tế.
