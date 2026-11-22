# `final` trên biến: chỉ gán một lần trong Java

Trong Java, từ khóa **`final`** đặt trên một **biến** giới hạn khả năng **gán giá trị cho biến đó**. Sau khi biến `final` đã được gán giá trị theo đúng quy tắc khởi tạo, không thể gán lại một giá trị khác cho **chính biến ấy**.

Ví dụ:

```java
final int MAX_RETRIES = 3;
// MAX_RETRIES = 5;  // Lỗi biên dịch: biến final đã được gán.
```

Với kiểu tham chiếu:

```java
final StringBuilder message = new StringBuilder("Java");
message.append(" 17");            // Hợp lệ: sửa đối tượng StringBuilder.
// message = new StringBuilder(); // Lỗi: gán lại biến message.
```

**Điểm cần nhớ ngay từ đầu:** `final` trên biến ngăn **reassignment của biến**, không tự làm **đối tượng mà tham chiếu trỏ tới** trở nên immutable. Có thể một biến `final` tham chiếu object mutable và các field/phần tử trong object vẫn thay đổi qua API được phép.

Bài tập trung vào ý nghĩa **“chỉ gán một lần”** của `final` đối với **biến cục bộ, tham số phương thức/constructor, trường đối tượng và trường static**; cách compiler kiểm tra definite assignment, những tình huống với nhánh điều kiện/vòng lặp, tham chiếu đối tượng, lambda và các lỗi thường gặp trong Java 17+.

## 1. Hiểu đúng ba thuật ngữ: biến, gán và giá trị

Xét:

```java
int number = 10;
```

- `number` là **biến** có kiểu `int`.
- `10` là **giá trị khởi tạo**.
- `=` trong khai báo thực hiện **initialization**, tức đưa giá trị ban đầu vào biến.

Nếu sau đó viết:

```java
number = 20;
```

đây là **assignment/reassignment**: biến `number` nhận giá trị mới. Với biến thường, điều này hợp lệ nếu phép gán thỏa kiểu và những quy tắc khác.

Nhưng:

```java
final int number = 10;
// number = 20; // Không hợp lệ.
```

Biến `number` đã được khởi tạo. `final` khiến một phép gán giá trị khác cho nó không được compiler chấp nhận.

### “Chỉ gán một lần” nghĩa là gì?

Cách nói trên là trực giác hữu ích, nhưng chính xác hơn:

> Một biến `final` chỉ được phép **nhận giá trị thông qua việc khởi tạo/gán trong những đường điều khiển mà Java cho phép**, và sau đó không thể bị **gán lại**.

Trường hợp đặc biệt là **blank final**: có thể khai báo trước nhưng gán giá trị về sau, miễn bảo đảm những quy tắc *definite assignment* và *definite unassignment* mà Java yêu cầu.

Vì vậy `final` **không bắt buộc** mọi khai báo local variable đều phải viết initializer ngay trên cùng dòng.

## 2. Biến local `final` đã khởi tạo: không thể gán lại

Đây là trường hợp đơn giản nhất.

```java
void process() {
    final int limit = 100;
    System.out.println(limit);

    // limit = 200; // Lỗi biên dịch.
}
```

`limit` là biến cục bộ và được gán khi khai báo. Nó không thể nhận giá trị thứ hai.

Dù phép gán mới có **cùng giá trị** như ban đầu, compiler cũng không cho phép:

```java
final int value = 7;
// value = 7; // Vẫn lỗi.
```

**`final` không kiểm tra giá trị có thay đổi hay không.** Nó ràng buộc **việc gán vào biến**. Một phép gán lần hai bị cấm kể cả khi vế phải bằng vế phải lần đầu.

### Các toán tử cập nhật đều là phép gán

Những lệnh sau **không hợp lệ** với local variable `final` đã khởi tạo:

```java
final int count = 1;

// count++;      // Lỗi.
// ++count;      // Lỗi.
// count += 2;   // Lỗi.
// count *= 3;   // Lỗi.
// count = 1;    // Lỗi.
```

Vì `++`, `--` và compound assignments như `+=` đều cập nhật **chính biến `count`**, chúng cũng bị giới hạn bởi `final`.

Ngược lại, chỉ **đọc** biến là hợp lệ:

```java
final int count = 3;
int doubled = count * 2;
System.out.println(doubled); // 6
```

## 3. Chương trình Java 17: local `final`

Lưu toàn bộ thành **`FinalLocalDemo.java`**:

```java
public class FinalLocalDemo {
    public static void main(String[] args) {
        final int base = 10;
        final int multiplier = 3;
        int result = base * multiplier;

        System.out.println("base = " + base);
        System.out.println("multiplier = " + multiplier);
        System.out.println("result = " + result);

        result += 5; // result không final.
        System.out.println("result mới = " + result);

        // base = 20;       // SAI: base là final.
        // multiplier++;    // SAI: multiplier là final.
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 FinalLocalDemo.java
java FinalLocalDemo
```

**Stdout chính xác:**

```text
base = 10
multiplier = 3
result = 30
result mới = 35
```

Giải thích: `base` và `multiplier` không bị gán lại, còn `result` là biến thường nên `result += 5` hợp lệ. Việc dùng một biến `final` trong biểu thức tính toán không làm **các biến nhận kết quả** cũng tự trở thành `final`.

## 4. Blank final local variable: khai báo trước, gán sau

**Blank final variable** là biến `final` được khai báo **chưa có initializer** ở vị trí khai báo.

Ví dụ:

```java
final int value;
value = 42;
System.out.println(value); // 42

// value = 50; // Lỗi: gán lần thứ hai.
```

Các bước:

1. Khai báo `final int value;`.
2. Compiler chưa coi `value` đã có giá trị để được đọc.
3. Dòng `value = 42;` là phép gán khởi tạo hợp lệ.
4. Từ đó không được gán thêm giá trị cho `value`.

### Không được đọc trước khi gán

```java
final int value;
// System.out.println(value); // SAI: có thể chưa khởi tạo.
value = 42;
```

Compiler dùng phân tích luồng điều khiển để bảo đảm biến local đã được **definitely assigned** trước khi đọc. Java không tự cấp giá trị mặc định `0` cho **biến cục bộ chưa khởi tạo** như đối với instance field.

Một blank final variable **không được phép gán chỉ vì “chưa dùng tới”** nếu compiler đã xác định trước đó nó có giá trị. Đơn vị xét là khả năng được gán theo các đường chạy hợp lệ.

## 5. `final` với `if`/`else`: chọn giá trị một lần

Một tình huống thực tế là muốn biến `final` nhận một trong hai kết quả tùy điều kiện:

```java
final String environment;

if (production) {
    environment = "PROD";
} else {
    environment = "DEV";
}

System.out.println(environment);
```

Dù mã nguồn có **hai dòng phép gán**, trong mỗi lần chạy bình thường chỉ **một nhánh** được thực thi, nên mỗi đường điều khiển hợp lệ chỉ gán biến `environment` một lần.

**Điểm quan trọng:** “chỉ gán một lần” **không** có nghĩa trong toàn bộ file Java chỉ được xuất hiện đúng **một câu lệnh gán** đến biến final. Compiler phân tích nhánh điều khiển và điều kiện definite assignment.

### Ví dụ hoàn chỉnh

Lưu **`FinalBranchDemo.java`**:

```java
public class FinalBranchDemo {
    static String mode(boolean production) {
        final String environment;

        if (production) {
            environment = "PROD";
        } else {
            environment = "DEV";
        }

        return environment;
    }

    public static void main(String[] args) {
        System.out.println(mode(true));
        System.out.println(mode(false));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FinalBranchDemo.java
java FinalBranchDemo
```

Stdout:

```text
PROD
DEV
```

Giải thích:
- `mode(true)` đi vào nhánh đầu và gán `environment = "PROD"`.
- `mode(false)` đi vào nhánh `else` và gán `environment = "DEV"`.
- Trong mỗi lần gọi `mode`, tham số và biến local thuộc **lần gọi riêng**; hai lần gọi không “gán hai lần” cho một biến chung.

### Nếu thiếu một nhánh thì sao?

```java
final String mode;
if (production) {
    mode = "PROD";
}

// System.out.println(mode); // SAI: production có thể false.
```

Nếu `production` là false, `mode` chưa được gán. Do đó Java không cho đọc ở điểm mà biến có thể chưa khởi tạo.

Cách sửa có thể là thêm `else`, dùng một biểu thức có giá trị trên mọi trường hợp, hoặc thiết kế một đường `return`/`throw` phù hợp.

## 6. Dùng toán tử điều kiện khi chọn giá trị cuối cùng

Nếu chỉ cần một giá trị theo điều kiện, có thể khởi tạo trực tiếp:

```java
final String label = enabled ? "ON" : "OFF";
```

`label` được gán đúng một lần khi đánh giá biểu thức.

So sánh:

```java
final int port;
if (testMode) {
    port = 8081;
} else {
    port = 8080;
}
```

và:

```java
final int port = testMode ? 8081 : 8080;
```

Cả hai đều có thể hợp lệ và cùng ý nghĩa nếu `testMode` không có side effects liên quan. Phiên bản dùng toán tử điều kiện thường ngắn hơn, còn `if`/`else` rõ ràng hơn khi việc xác định giá trị phức tạp.

**Không được gán `port` thêm lần nữa** sau khi kết quả đã được xác định.

## 7. `final` và `switch`: đảm bảo mọi đường hợp lệ đều có giá trị

Trong Java 17, **switch expression** có thể trả ra kết quả để khởi tạo biến final:

```java
final int severity = switch (level) {
    case "LOW" -> 1;
    case "MEDIUM" -> 2;
    case "HIGH" -> 3;
    default -> 0;
};
```

`switch` ở đây là **biểu thức**: nó cho một giá trị cuối cùng, không phải lời gọi cập nhật biến nhiều lần.

### Ví dụ runnable

Lưu **`FinalSwitchDemo.java`**:

```java
public class FinalSwitchDemo {
    static int priority(String level) {
        final int result = switch (level) {
            case "LOW" -> 1;
            case "MEDIUM" -> 2;
            case "HIGH" -> 3;
            default -> 0;
        };
        return result;
    }

    public static void main(String[] args) {
        System.out.println(priority("LOW"));
        System.out.println(priority("HIGH"));
        System.out.println(priority("UNKNOWN"));
    }
}
```

```bash
javac -encoding UTF-8 FinalSwitchDemo.java
java FinalSwitchDemo
```

Stdout:

```text
1
3
0
```

Lưu ý: `switch` trên một tham chiếu `String` null không tự trả `default` theo quy tắc Java 17 thông thường; cần xử lý `null` riêng nếu đó là đầu vào hợp lệ của API.

## 8. `final` trong vòng lặp: phân biệt biến cố định và biến mới mỗi lượt

`final` thường gây lỗi khi được áp dụng cho **biến điều khiển vòng lặp** cần tăng/giảm:

```java
// SAI:
// for (final int i = 0; i < 3; i++) {
//     System.out.println(i);
// }
```

Bởi `i++` là một phép gán vào `i`, compiler từ chối nếu `i` đã khai báo `final` và khởi tạo bằng `0`.

### Biến `final` khai báo bên trong thân vòng lặp

```java
for (int i = 0; i < 3; i++) {
    final int squared = i * i;
    System.out.println(squared);
}
```

Đây là mã hợp lệ. Mỗi lượt thực hiện thân vòng lặp khởi tạo một **biến cục bộ theo lần thực thi block tương ứng**. Không có phép gán thứ hai vào chính biến `squared` sau khi nó được khởi tạo trong lượt đó.

### Enhanced for với biến lặp `final`

```java
int[] values = {2, 4, 6};

for (final int value : values) {
    System.out.println(value);
    // value++; // SAI: không được gán lại biến final.
}
```

Enhanced `for` cho phép khai báo phần tử lặp là `final`. Mỗi lần lặp nhận giá trị phần tử theo cơ chế của vòng lặp; chương trình không được tự gán lại biến `value` trong thân vòng.

### Ví dụ runnable

Lưu **`FinalLoopDemo.java`**:

```java
public class FinalLoopDemo {
    public static void main(String[] args) {
        for (int i = 0; i < 3; i++) {
            final int square = i * i;
            System.out.println("square = " + square);
        }

        int sum = 0;
        for (final int value : new int[]{2, 4, 6}) {
            sum += value;
        }
        System.out.println("sum = " + sum);
    }
}
```

```bash
javac -encoding UTF-8 FinalLoopDemo.java
java FinalLoopDemo
```

Stdout:

```text
square = 0
square = 1
square = 4
sum = 12
```

**Mẹo:** vòng lặp cần biến đếm được cập nhật thì **đừng đặt biến đếm ấy thành `final`**. Nhưng biến chỉ đọc được tạo từ biến đếm ở mỗi lượt lại có thể `final` rất hợp lý.

## 9. `final` trên biến kiểu primitive: khóa giá trị biến, không khóa mọi tính toán

Các kiểu primitive như `int`, `long`, `double`, `boolean`, `char` có giá trị lưu trực tiếp theo mô hình kiểu của Java.

```java
final int width = 4;
final int height = 5;

int area = width * height;
area += 10;
```

- `width` và `height` không thể bị gán lại.
- `area` được phép đổi vì không khai báo `final`.
- Biểu thức `width * height` tính ra một giá trị; nó **không phải cập nhật `width` hoặc `height`**.

Khai báo final còn có thể dùng cho primitive boolean:

```java
final boolean active = true;
// active = false; // SAI.
```

Cũng có thể dùng với local variable kiểu tham chiếu tới boxed primitive:

```java
final Integer count = 7;
// count = 8; // SAI: gán lại tham chiếu count.
```

Với `Integer` là immutable value object, caller không thể mutate nội dung integer đó bằng setter. Nhưng lý do **không được gán `count = 8`** vẫn là ràng buộc của biến `final`.

## 10. `final` trên tham chiếu: không có nghĩa đối tượng bất biến

Đây là nhầm lẫn phổ biến nhất.

```java
final StringBuilder builder = new StringBuilder("Java");
builder.append(" Core");     // Hợp lệ.
// builder = new StringBuilder("Other"); // Lỗi.
```

`builder` giữ nguyên tham chiếu đã khởi tạo. Nhưng đối tượng `StringBuilder` có thể thay đổi nội dung thông qua `append`.

### Ví dụ mảng `final`

```java
final int[] numbers = {1, 2, 3};
numbers[0] = 9;               // Hợp lệ: cập nhật phần tử mảng.
// numbers = new int[]{4, 5}; // SAI: gán lại biến numbers.
```

Mảng **là object mutable**. `final` trên biến `numbers` **không** biến từng phần tử mảng thành final.

### Ví dụ collection `final`

```java
final java.util.List<String> names =
        new java.util.ArrayList<>();

names.add("An");       // Hợp lệ.
names.add("Bình");     // Hợp lệ.
// names = new ArrayList<>(); // SAI: gán lại biến names.
```

Không được gán biến `names` sang list khác, nhưng có thể sửa object `ArrayList` được tham chiếu nếu API cho phép.

### Hai câu hỏi phải tách riêng

1. **Tham chiếu có thể thay đổi sang object khác không?** `final` trên biến trả lời **không**, sau khi đã khởi tạo.
2. **Object có thể thay đổi trạng thái không?** Phụ thuộc vào **kiểu object, field, method và hợp đồng thiết kế**. `final` trên biến không quyết định điều đó.

## 11. Chương trình hoàn chỉnh: `final` với mảng, list và builder

Lưu **`FinalReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class FinalReferenceDemo {
    public static void main(String[] args) {
        final int[] values = {1, 2};
        final List<String> names = new ArrayList<>();
        final StringBuilder text = new StringBuilder("Java");

        values[0] = 10;
        names.add("An");
        names.add("Bình");
        text.append(" 17");

        System.out.println(Arrays.toString(values));
        System.out.println(names);
        System.out.println(text);

        // values = new int[]{3, 4};             // SAI
        // names = new ArrayList<>();            // SAI
        // text = new StringBuilder("Other");    // SAI
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
```

**Stdout:**

```text
[10, 2]
[An, Bình]
Java 17
```

Đây là chứng minh thực nghiệm rằng `final` **không phải deep immutability**.

### Một đối tượng bất biến có thể được tham chiếu qua biến không final

```java
String message = "Java";
message = message + " 17";
```

Đối tượng `String` được coi là immutable; phép nối chuỗi không sửa nội dung object cũ mà tạo/nhận chuỗi kết quả. Nhưng biến `message` **không final**, nên được gán tham chiếu kết quả.

Nếu viết:

```java
final String message = "Java";
// message = message + " 17"; // SAI: gán lại biến final.
```

thì compiler từ chối, không phải vì `String` cần “mở khóa”, mà vì **biến `message` bị khóa phép gán**.

## 12. Aliasing: biến khác vẫn có thể sửa đối tượng của biến `final`

Giả sử:

```java
final StringBuilder first = new StringBuilder("A");
StringBuilder alias = first;

alias.append("B");
System.out.println(first); // AB
```

`first` và `alias` cùng tham chiếu **một đối tượng `StringBuilder`**. `final` chỉ áp dụng cho **biến `first`**, không hạn chế biến `alias` và không tự làm đối tượng chia sẻ thành immutable.

Sơ đồ:

```text
first (final) ──────┐
                    ├──> StringBuilder { "AB" }
alias (thường) ─────┘
```

Nếu:

```java
alias = new StringBuilder("C");
```

thì `alias` chuyển sang object mới; `first` vẫn giữ object cũ `"AB"`. Không có hành vi “final giữ cho mọi biến khác luôn trỏ cùng object”.

### `final` không bảo vệ nội dung được chia sẻ

Một `final List<String>` vẫn có thể bị sửa bởi code giữ alias đến cùng `ArrayList`:

```java
List<String> source = new ArrayList<>();
final List<String> stored = source;
source.add("A");
```

`stored` vẫn trỏ list đã có phần tử `"A"`. Nếu muốn **đóng gói** dữ liệu, cần chiến lược như defensive copying, immutable collection và kiểm soát mutable elements, chứ không chỉ gắn `final` lên tham chiếu.

## 13. `final` trên tham số phương thức

Có thể khai báo tham số là `final`:

```java
static void greet(final String name) {
    System.out.println("Xin chào " + name);
    // name = "Khác"; // SAI: không được gán lại tham số.
}
```

Tham số hình thức được khởi tạo khi gọi method từ **giá trị đối số**. Dù caller có biến không final, bản sao giá trị đã vào tham số final sẽ không được gán lại trong thân method.

`final` trên tham số là cách thể hiện chủ đích “không dùng biến tham số làm nơi lưu giá trị khác”. Nó **không** thay đổi cơ chế truyền đối số của Java: vẫn luôn **pass-by-value**.

### Tham số tham chiếu final vẫn cho phép mutation

```java
static void addItem(final List<String> items) {
    items.add("Java"); // Hợp lệ nếu list mutable.
    // items = new ArrayList<>(); // SAI.
}
```

Đoạn này có thể sửa list mà caller cũng đang giữ. Điều đó **không chứng minh Java truyền biến theo tham chiếu**; method nhận bản sao **giá trị tham chiếu** cùng trỏ một object.

### Chương trình runnable

Lưu **`FinalParameterDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class FinalParameterDemo {
    static void increase(final int number) {
        System.out.println("Trong method: " + (number + 1));
        // number++; // SAI: tham số final.
    }

    static void add(final List<String> values) {
        values.add("Java");
        // values = new ArrayList<>(); // SAI.
    }

    public static void main(String[] args) {
        int original = 5;
        increase(original);
        System.out.println("Ở main: " + original);

        List<String> list = new ArrayList<>();
        add(list);
        System.out.println(list);
    }
}
```

```bash
javac -encoding UTF-8 FinalParameterDemo.java
java FinalParameterDemo
```

Stdout:

```text
Trong method: 6
Ở main: 5
[Java]
```

`increase` chỉ tính giá trị mới và in, không sửa tham số. `add` làm thay đổi object list dùng chung. Cả hai tuân theo pass-by-value, bất kể tham số có `final`.

## 14. `final` trên tham số constructor

Constructor cũng có thể dùng tham số `final`:

```java
class Person {
    private final String name;

    Person(final String name) {
        this.name = name;
        // name = "Other"; // SAI: tham số final.
    }
}
```

Phân biệt:
- `name` bên phải là **tham số final** của constructor.
- `this.name` bên trái là **instance field final**.
- `this.name = name;` gán **giá trị của tham số** vào **field của object**, **không** gán lại tham số `name`.

Hai thành phần là hai biến khác nhau, dù cùng tên. `final` trên tham số không khiến field tự final, và `final` trên field không khiến tham số tự final.

Ví dụ:

```java
class Product {
    private String label;

    Product(final String label) {
        this.label = label;
    }

    void rename(String newLabel) {
        this.label = newLabel; // Field không final.
    }
}
```

Ở đây tham số `label` final chỉ cấm gán lại **tham số lúc xây dựng**. Field `this.label` vẫn không final, nên có thể đổi về sau theo API.

## 15. Biến `final` và instance field `final`: giống nguyên tắc, khác nơi khởi tạo

Với **local variable** `final`, compiler kiểm tra khả năng gán đúng một lần tại phạm vi khối/lần gọi method. Với **instance field** `final`, mọi đường khởi tạo object hoàn tất bình thường phải gán field đúng theo các quy tắc constructor/initializer.

~~~java
class Ticket {
    private final String id;

    Ticket(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }
}
~~~

`new Ticket("A")` và `new Ticket("B")` tạo hai instance có giá trị `id` độc lập. Đây là điểm nối sang bài **Trường final và yêu cầu gán giá trị trên mọi nhánh khởi tạo**; phần phân tích chi tiết constructor paths/definite assignment thuộc bài đó.

## 16. Constructor overload và blank final field

Nếu có nhiều constructors, cần bảo đảm đường xây dựng object nào cũng khởi tạo blank final field.

Ví dụ đúng:

```java
class Configuration {
    private final String mode;

    Configuration() {
        this("DEFAULT");
    }

    Configuration(String mode) {
        this.mode = mode;
    }

    String mode() {
        return mode;
    }
}
```

Constructor không tham số gọi `this("DEFAULT")`. Constructor có tham số gán field `mode`. Mỗi object được xây dựng có một giá trị cuối cùng cho `mode`.

### Ví dụ runnable

Lưu **`FinalFieldConstructorDemo.java`**:

```java
class Configuration {
    private final String mode;
    private final int port;

    Configuration() {
        this("DEV", 8080);
    }

    Configuration(String mode, int port) {
        this.mode = mode;
        this.port = port;
    }

    String describe() {
        return mode + ":" + port;
    }
}

public class FinalFieldConstructorDemo {
    public static void main(String[] args) {
        Configuration first = new Configuration();
        Configuration second = new Configuration("PROD", 9090);

        System.out.println(first.describe());
        System.out.println(second.describe());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 FinalFieldConstructorDemo.java
java FinalFieldConstructorDemo
```

Stdout:

```text
DEV:8080
PROD:9090
```

Chú ý: trong Java 17, `this(...)` hoặc `super(...)` trong constructor phải tuân thủ quy tắc vị trí ở đầu thân constructor. Trong ví dụ này `this("DEV", 8080)` là lời gọi đầu tiên.

### Lỗi không khởi tạo tất cả nhánh

```java
class BadConfiguration {
    final String mode;

    BadConfiguration(boolean enabled) {
        if (enabled) {
            mode = "ACTIVE";
        }
        // SAI: nếu enabled false, mode chưa được gán.
    }
}
```

Đây là **ví dụ chủ ý không biên dịch**. Để sửa, phải xử lý đường `else` hoặc luôn gán giá trị phù hợp.

## 17. Blank final field với instance initializer

Blank final instance field cũng có thể được gán ở **instance initializer** của chính class, ví dụ:

~~~java
class Token {
    final String kind;
    { kind = "ACCESS"; }
    Token() {}
}
~~~

Constructor không được gán lại `kind` vì initializer đã gán. Trong chương này, trọng tâm chính vẫn là `final` của **biến**, nên các vị trí gán blank final field và thứ tự constructor/initializer được học ở bài **Trường final chưa có giá trị và nơi được phép gán**.

## 18. Static final field: giá trị thuộc lớp, chỉ được gán một lần

Một `static final` field là biến static thuộc lớp và bị giới hạn gán lại.

```java
class Limits {
    static final int MAX_USERS = 100;
}
```

Thông qua cách sử dụng hợp lệ `Limits.MAX_USERS`, code đọc được giá trị `100`; không được sửa:

```java
// Limits.MAX_USERS = 200; // SAI.
```

Không cần một instance `Limits` cụ thể vì field là static.

### Blank static final field

Có thể khai báo một blank static final field rồi khởi tạo trong **static initializer**:

```java
class Limits {
    static final int MAX_USERS;

    static {
        MAX_USERS = 100;
    }
}
```

Nếu static final field đã có initializer, không được gán thêm lần nữa trong static block.

Compiler phải chứng minh blank static final field được gán theo quy tắc khi khởi tạo lớp hoàn tất bình thường.

### Ví dụ Java 17

Lưu **`StaticFinalDemo.java`**:

```java
class Limits {
    static final int MAX_USERS;
    static final String APPLICATION = "Learning";

    static {
        MAX_USERS = 100;
    }

    static String describe() {
        return APPLICATION + ": " + MAX_USERS;
    }
}

public class StaticFinalDemo {
    public static void main(String[] args) {
        System.out.println(Limits.describe());
        System.out.println(Limits.MAX_USERS);
    }
}
```

```bash
javac -encoding UTF-8 StaticFinalDemo.java
java StaticFinalDemo
```

Stdout:

```text
Learning: 100
100
```

**Đừng nhầm:** `static final` không phải lúc nào cũng là một *compile-time constant*. Điều đó còn phụ thuộc **kiểu** và **biểu thức khởi tạo**.

## 19. Compile-time constant khác với `final` thông thường

Không phải mọi `final` đều là **constant variable** tại thời điểm biên dịch:

~~~java
final int value = Integer.parseInt("42");
static final java.time.LocalDate START =
        java.time.LocalDate.of(2026, 1, 1);
~~~

Giá trị được thiết lập lúc chạy chứ không phải constant expression hợp lệ theo JLS. Một biến `final` chỉ giới hạn **gán lại binding**; điều kiện chính xác để primitive/String final được coi là constant variable, việc inline qua module và thời điểm khởi tạo class nằm ở bài **Hằng static final và điều kiện của hằng tại thời điểm biên dịch**.

## 20. `final` với `var`: kiểu suy luận vẫn cố định

Từ Java 10, một biến cục bộ có thể dùng `var` nếu compiler suy luận được kiểu từ initializer. `final` hoàn toàn có thể kết hợp:

```java
final var name = "Java";
final var count = 10;
```

- `name` được suy luận kiểu `String`.
- `count` được suy luận kiểu `int`.
- Cả hai biến đều final: không được gán lại sau khi khởi tạo.

Đây **không** phải dynamic typing. Kiểu tĩnh của biến được xác định tại compile time và `final` giới hạn reassignment.

```java
final var builder = new StringBuilder("A");
builder.append("B"); // Hợp lệ.
// builder = new StringBuilder("C"); // SAI.
```

### Hạn chế riêng của `var`

`var` cần initializer trong khai báo local variable để suy luận kiểu. Ví dụ:

```java
// final var value; // SAI: không có initializer để suy luận kiểu.
```

Nếu cần blank final, khai báo một **kiểu tường minh**:

```java
final String value;
value = "Java";
```

Đừng tưởng `final var` có thể “để trống rồi suy luận kiểu khi gán về sau” như một kiểu động.

## 21. `final` và lambda: captured variable phải final hoặc effectively final

Biến local/parameter được lambda sử dụng từ phạm vi bao quanh phải là **final hoặc effectively final** (không bị gán lại theo các quy tắc của Java):

~~~java
int offset = 3;
java.util.function.IntUnaryOperator addOffset =
        number -> number + offset;
System.out.println(addOffset.applyAsInt(4)); // 7
// offset++; // Nếu bỏ comment sẽ làm lambda không hợp lệ.
~~~

**Effectively final** không tự tạo immutability: một reference effectively final vẫn có thể trỏ tới object mutable. Bài **Phân biệt final, effectively final và bất biến** phân tích nhiều đường gán, vòng lặp, anonymous/local class và các ví dụ capture chi tiết.

## 22. Anonymous class và local class: cùng ý tưởng capture

**Anonymous class** và **local class** có thể capture local variables/parameters của phạm vi bao ngoài với yêu cầu final/effectively final. Nếu code cố gán lại biến local đã được capture, compiler từ chối; không thể “lách” bằng cách cho lambda tự sửa biến bên ngoài.

~~~java
final int step = 2;
Runnable action = new Runnable() {
    @Override public void run() {
        System.out.println(step);
    }
};
action.run(); // 2
~~~

Đây là quy tắc về local **binding**, không ngăn anonymous object/field riêng của nó có mutable state. Các trường hợp khó (capture loop index, variable gán theo nhánh) có giải thích riêng ở B148.

## 23. `final` không có nghĩa object được tạo một lần duy nhất trong chương trình

Một khai báo nằm trong method:

```java
static void process() {
    final Object value = new Object();
}
```

Mỗi lần gọi `process()` có một lần thực thi local declaration theo cơ chế của method; biến `value` chỉ bị giới hạn phép gán **trong lần gọi ấy**.

Nếu gọi `process()` nhiều lần, Java có thể tạo **nhiều đối tượng khác nhau**, không phải chỉ một object dùng chung toàn chương trình.

Cũng tương tự, `final` instance field trong các object khác nhau là các field độc lập:

```java
class Item {
    final int id;

    Item(int id) {
        this.id = id;
    }
}

Item first = new Item(1);
Item second = new Item(2);
```

`first.id` và `second.id` khác nhau mà không vi phạm `final`. Mỗi object được khởi tạo theo giá trị constructor tương ứng.

**`final` trên local variable/field không tự có nghĩa singleton hoặc constant global.** Muốn một instance được chia sẻ, cần một thiết kế riêng như static field, factory hay dependency injection.

## 24. `final` field và tính an toàn đa luồng

`final` fields có **ngữ nghĩa khởi tạo đặc biệt** trong Java Memory Model khi object được xây dựng đúng cách và không để `this` thoát sớm. Tuy nhiên `final` không biến mutable object thành immutable, không làm `count++` atomic, và không tự đồng bộ các thay đổi tiếp theo của object graph.

Ví dụ `private final java.util.List<String> items = new java.util.ArrayList<>();` giữ reference ổn định nhưng vẫn cần quy tắc đồng bộ khi threads cập nhật cùng list. Hãy chọn immutable snapshots, encapsulation hoặc synchronization dựa trên contract, thay vì suy ra thread-safety từ riêng modifier `final`.

## 25. `final` trong record: component fields là final, nhưng không deep immutable

Java 17 `record` có các component fields `private final` và các accessors tương ứng:

~~~java
record Point(int x, int y) {}
~~~

Không thể gán lại `x` hoặc `y` sau khởi tạo. Nhưng `record Data(int[] values) {}` vẫn có thể phơi bày mảng mutable; final reference không bảo đảm **deep immutability**. Nếu domain cần value snapshot, dùng immutable component types hoặc defensive copies thích hợp. Phân tích chi tiết có trong bài về **tham chiếu final** và bài **effectively final/bất biến**.

## 26. `final` biến khác `final` method và `final` class

Cùng một keyword nhưng phạm vi ràng buộc khác nhau:

| Vị trí | Ý nghĩa |
| --- | --- |
| `final int x = 5;` | Không gán lại biến `x` |
| `final SomeObject ref = ...;` | Không gán lại reference; object vẫn có thể mutable |
| `private final String id;` | Field phải được khởi tạo hợp lệ và không bị gán lại |
| `final void work()` | Subclass không được override method đó |
| `final class Value {}` | Không cho class khác extends Value |

Bài **final trên phương thức và lớp** là nơi đi sâu vào override, overload, sealed hierarchy và extension points; không dùng quy tắc final variable để suy về khả năng kế thừa.

## 27. `final` trong catch, for-each và try-with-resources

Một số dạng khai báo đặc biệt cũng cho phép/áp dụng ràng buộc tương tự.

### Catch parameter

```java
try {
    Integer.parseInt("x");
} catch (final NumberFormatException exception) {
    System.out.println("Không phải số hợp lệ");
    // exception = new NumberFormatException(); // SAI.
}
```

`exception` là tham số catch và có thể khai báo final. Việc gán lại tham số bắt lỗi bị cấm; đọc exception và gọi các method của nó vẫn hợp lệ.

Đối với **multi-catch parameter**, Java có các ràng buộc ngôn ngữ khiến tham số này không thể bị gán lại trong cách dùng thông thường. Không nhất thiết thêm `final` ở mọi chỗ để mới đạt được hành vi đó.

### Enhanced for

```java
for (final String name : new String[]{"An", "Bình"}) {
    System.out.println(name);
}
```

Mỗi lượt lặp có biến phần tử lặp final theo cơ chế khai báo enhanced-for. Không thể `name = "Other";` trong thân.

### Try-with-resources

```java
try (final java.io.StringReader reader =
             new java.io.StringReader("Java")) {
    System.out.println((char) reader.read());
}
```

Biến resource `reader` là final theo khai báo. Java quản lý đóng resource theo cú pháp try-with-resources. Từ Java 9, có thể dùng biến resource **final hoặc effectively final** đã tồn tại ở vị trí phù hợp, thay vì nhất thiết khai báo biến mới trong dấu ngoặc.

**Lưu ý:** final không phải là lý do resource được đóng; chính semantics của **try-with-resources** điều khiển việc gọi `close()`.

## 28. Bảng lỗi thường gặp khi dùng `final`

| Mã/tình huống | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `final int n = 1; n = 2;` | Gán lại biến đã final | Tạo biến kết quả mới hoặc bỏ final nếu thật sự cần cập nhật |
| `final int n = 1; n++;` | `++` cập nhật biến | Dùng biến đếm thường |
| `final int n = 1; n += 2;` | Compound assignment cũng là gán | Dùng `int other = n + 2;` |
| `final int n; println(n);` | Đọc trước definite assignment | Gán giá trị hợp lệ trước khi đọc |
| `final String mode; if(flag) mode="A"; print(mode);` | Nhánh false có thể chưa gán | Bổ sung `else` hoặc biểu thức chọn giá trị |
| `final int x = 1; if(flag) x = 2;` | Có đường gán lần hai | Thiết kế khởi tạo một lần theo nhánh |
| `for(final int i=0;i<3;i++)` | `i++` gán biến final | Dùng `int i` |
| `final var x;` | `var` thiếu initializer để suy luận kiểu | Dùng kiểu tường minh cho blank final |
| `final List<String> x = new ArrayList<>(); x.add("A");` | Thực ra **hợp lệ** | Phân biệt mutation của list và reassignment của biến |
| `final int[] a = {1}; a[0] = 2;` | Thực ra **hợp lệ** | `final` không áp dụng lên từng phần tử |
| `void f(final User u) { u = new User(); }` | Gán lại tham số final | Trả object mới cho caller hoặc bỏ final có chủ đích |
| `private final int id;` mà constructor không gán | Blank final field chưa được khởi tạo hợp lệ | Khởi tạo ở field/initializer/constructor trên mọi đường cần thiết |
| Final field có initializer, constructor gán lại | Gán lần hai | Chỉ khởi tạo ở một cơ chế phù hợp |
| Static final blank field không được gán | Khởi tạo lớp không bảo đảm field có giá trị | Gán trong static initializer/field declaration |
| Bắt biến captured rồi gán lại | Biến không còn effectively final | Dùng biến khác hoặc giải pháp state/ownership phù hợp |
| `final StringBuilder b = ...; b.append(...)` | Thực ra **hợp lệ** | Nếu cần nội dung bất biến, dùng immutable representation |
| `static final List<String> ITEMS = new ArrayList<>(); ITEMS.add(...)` | Thực ra **hợp lệ** | Cần immutable list nếu muốn cấm sửa object |
| `final class X` nhưng object vẫn có setter | Final class chỉ cấm kế thừa | Thiết kế immutable object riêng |
| Đổi public static final compile-time constant mà client cũ chưa thấy | Có thể có constant inlining | Cân nhắc versioning/recompile clients |

## 29. Bài tập tự luyện có đáp án

### Bài 1 — Biến final với giá trị giống hệt ban đầu

```java
final int score = 10;
// score = 10;
```

**Đáp án:** nếu bỏ comment, code **không biên dịch**. `final` cấm phép gán thứ hai kể cả khi vế phải bằng giá trị cũ.

### Bài 2 — Hai nhánh `if`/`else`

```java
final String state;
if (ready) {
    state = "READY";
} else {
    state = "PENDING";
}
System.out.println(state);
```

**Đáp án:** hợp lệ nếu `ready` là boolean được xác định. Mỗi đường chạy chỉ gán `state` một lần; sau `if`/`else` biến đã definitely assigned.

### Bài 3 — Thiếu nhánh

```java
final int result;
if (valid) {
    result = 1;
}
// System.out.println(result);
```

**Đáp án:** đọc `result` ở cuối sẽ gây lỗi biên dịch vì `valid` có thể false. Thêm `else`/return/throw hoặc một cách xác định giá trị trên mọi đường phù hợp.

### Bài 4 — `final` với mảng

```java
final int[] scores = {5, 6};
scores[0] = 9;
System.out.println(scores[0]);
// scores = new int[]{1, 2};
```

**Đáp án:** in `9`. Sửa phần tử mảng hợp lệ, gán lại `scores` sang mảng khác không hợp lệ.

### Bài 5 — `final` với mutable list

```java
final java.util.List<String> items =
        new java.util.ArrayList<>();
items.add("A");
items.add("B");
System.out.println(items);
```

**Đáp án:** in `[A, B]`. Ràng buộc final đặt trên **biến items**, không đặt trên cấu trúc của `ArrayList`.

### Bài 6 — Parameter final

```java
static void change(final StringBuilder builder) {
    builder.append("!");
    // builder = new StringBuilder("X");
}
```

**Đáp án:** `append` hợp lệ nếu builder không null và mutable. Dòng gán lại `builder` không hợp lệ. Caller có thể quan sát nội dung được thêm qua object đã truyền.

### Bài 7 — Local final mỗi lượt lặp

```java
for (int i = 0; i < 3; i++) {
    final int value = i + 1;
    System.out.println(value);
}
```

**Đáp án:**

```text
1
2
3
```

Biến `value` được khởi tạo một lần trong mỗi lần thực thi khai báo của block; không bị gán lại trong block.

### Bài 8 — Field final trong constructor

```java
class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
```

**Đáp án:** hợp lệ. Mỗi instance được xây dựng khởi tạo hai fields. Constructor khác cũng phải bảo đảm khởi tạo các blank final fields qua đường hợp lệ.

### Bài 9 — Final reference và alias

```java
final StringBuilder left = new StringBuilder("A");
StringBuilder right = left;
right.append("B");
System.out.println(left);
```

**Đáp án:** `AB`. `left` không đổi giá trị tham chiếu, nhưng object chung bị sửa qua `right`.

### Bài 10 — Lambda và effectively final

```java
int offset = 3;
java.util.function.IntUnaryOperator f = x -> x + offset;
System.out.println(f.applyAsInt(4));
```

**Đáp án:** `7`. Biến `offset` không khai báo final tường minh nhưng effectively final. Nếu thêm phép `offset = 5;` trong cùng scope, việc capture có thể không còn hợp lệ.

### Bài 11 — `final var`

```java
final var greeting = "Hello";
System.out.println(greeting);
```

**Đáp án:** hợp lệ trong Java 17; `greeting` được suy luận kiểu `String` và final. `final var greeting;` không hợp lệ vì `var` cần initializer.

### Bài 12 — Static final và object mutable

```java
class Registry {
    static final java.util.List<String> NAMES =
            new java.util.ArrayList<>();
}

Registry.NAMES.add("An");
```

**Đáp án:** thao tác thêm có thể hợp lệ vì `Registry.NAMES` tham chiếu list mutable. `Registry.NAMES = new ArrayList<>();` không hợp lệ vì static field final. Muốn API không cho caller thêm phần tử cần quyền truy cập và immutable collection phù hợp.

### Bài 13 — Record chứa mảng

```java
record Data(byte[] bytes) { }
final Data value = new Data(new byte[]{1});
value.bytes()[0] = 9;
```

**Đáp án:** thao tác sửa phần tử mảng hợp lệ và thay mảng trong record đã tạo. Biến `value` và component reference field là final không tự sao chép mảng hay chặn mutation.

## 30. Checklist khi quyết định thêm `final` vào biến

1. **Biến có cần gán lại không?** Nếu không, `final` làm chủ đích rõ ràng.
2. **Đang dùng primitive hay reference?** `final` chặn gán lại cả hai, nhưng object mutable vẫn có thể đổi trạng thái.
3. **Nếu blank final, compiler chứng minh đã gán trước khi đọc chưa?**
4. **Nếu gán trong các nhánh**, mọi đường cần thiết đã khởi tạo và không gán hai lần chưa?
5. **Nếu biến đếm tăng/giảm trong loop**, không dùng `final` cho chính biến đếm đó.
6. **Nếu local `final` khai báo trong thân loop**, hiểu rằng nó được khởi tạo theo mỗi lần thực thi block tương ứng.
7. **Nếu là tham số**, có cần gán lại tham số trong body không? Nếu cần, hãy cân nhắc tạo local variable kết quả riêng.
8. **Nếu là instance final field**, đã được khởi tạo trong field initializer/instance initializer/constructor phù hợp chưa?
9. **Nếu có constructor overload**, mọi đường constructor chaining hợp lệ đã bảo đảm blank final fields có giá trị chưa?
10. **Nếu là static final field**, có initializer hoặc static block hợp lệ chưa?
11. **Nếu gọi biến là “hằng số”**, nó thật sự là compile-time constant hay chỉ là final reference?
12. **Nếu final reference đến list/array/builder**, còn mutable state hay alias từ nơi khác không?
13. **Nếu capture trong lambda**, biến local/parameter đã final hoặc effectively final chưa?
14. **Nếu dùng `var`**, có initializer để suy luận kiểu và có thật sự muốn khóa biến không?
15. **Nếu cần tính bất biến thực sự**, đã bảo vệ mutable fields/nested elements và đường lộ trạng thái chưa?
16. **Nếu dùng nhiều thread**, đã xem thread-safety của object mutable, không chỉ modifier final chưa?
17. **Nếu API public chứa compile-time constants**, đã cân nhắc hiệu ứng inlining khi nâng phiên bản chưa?
18. **Nếu gặp lỗi javac**, hãy xác định phép gán nào đang cố sửa **biến final** thay vì đoán rằng mọi thao tác với object đều bị cấm.

## Ghi nhớ

- **`final` trên biến giới hạn việc gán lại biến**. Biến đã khởi tạo hợp lệ không thể nhận phép gán mới, kể cả gán cùng giá trị.
- **Blank final** có thể được khai báo trước và khởi tạo sau nếu đáp ứng **definite assignment/definite unassignment** của Java.
- **Nhiều nhánh mã có thể có câu lệnh gán** cho một final variable, miễn compiler bảo đảm đường điều khiển hợp lệ chỉ khởi tạo biến theo quy tắc.
- `++`, `--` và `+=` đều là các dạng cập nhật biến nên không áp dụng cho biến final đã khởi tạo.
- **Final reference không đồng nghĩa immutable object**: có thể sửa phần tử của `final int[]`, thêm vào `final ArrayList` hoặc gọi `append` trên `final StringBuilder`.
- **Final parameter** không được gán lại trong method, nhưng vẫn nhận giá trị đối số theo cơ chế **pass-by-value**.
- **Final instance/static fields** cần khởi tạo đúng nơi và đường điều khiển; constructor/initializer có quy tắc riêng.
- **Final/effectively final** là điều kiện quan trọng khi lambda/local class capture biến cục bộ.
- **Final field, final method và final class khác nhau**: khóa gán biến, cấm override hoặc cấm kế thừa là những quy tắc ở vị trí khai báo khác nhau.
- Dùng `final` để **thể hiện chủ đích giữ ổn định biến**, nhưng muốn bảo vệ trạng thái object hãy thiết kế **immutability, defensive copy, access control** và **thread-safety** riêng.
