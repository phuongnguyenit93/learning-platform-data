# Phương thức void và phương thức trả về giá trị trong Java

Trong Java, **phương thức (method)** là một khối lệnh được khai báo trong một lớp hoặc interface để thực hiện một hành vi. Khi khai báo phương thức, lập trình viên phải chỉ ra **kiểu trả về** (*return type*). Hai trường hợp cơ bản là:

- **Phương thức `void`:** thực hiện hành động nhưng **không trả về một giá trị** cho nơi gọi.
- **Phương thức trả về giá trị:** khai báo một kiểu cụ thể (ví dụ `int`, `boolean`, `String` hoặc một lớp tự định nghĩa) và trả về **một giá trị tương thích** với kiểu đã khai báo.

Chọn đúng kiểu trả về giúp thiết kế API rõ ràng: phương thức **thực hiện công việc** như in thông báo có thể dùng `void`; phương thức **tính toán hoặc cung cấp kết quả** như tính tổng hoặc kiểm tra điều kiện thường nên trả về giá trị.

## 1. Cấu trúc một khai báo phương thức

Một phương thức thông thường trong lớp có dạng:

```java
[modifier] returnType methodName(parameterList) {
    // Các câu lệnh trong thân phương thức
}
```

Đây là **sơ đồ cú pháp**, không phải chương trình Java độc lập. Các thành phần:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Modifier (nếu có) | `public`, `private`, `static` | Quyền truy cập hoặc đặc tính của phương thức |
| Kiểu trả về | `void`, `int`, `String` | Quy định lời gọi có tạo ra giá trị để dùng không, và kiểu giá trị là gì |
| Tên phương thức | `printMessage`, `calculateTotal` | Tên gọi để sử dụng phương thức |
| Danh sách tham số | `int a, int b` | Khai báo dữ liệu nhận vào; có thể không có tham số |
| Thân phương thức | `{ ... }` | Các lệnh thực thi khi gọi phương thức |

Ví dụ:

```java
static void printMessage(String message) {
    System.out.println(message);
}

static int add(int a, int b) {
    return a + b;
}
```

Cả hai phương thức đều có thể nhận dữ liệu đầu vào. Điểm khác biệt là **`printMessage` không tạo giá trị trả về**, còn **`add` có kết quả kiểu `int`**.

`void` là từ khóa dành cho việc khai báo **không có giá trị trả về**. Không thể sử dụng `void` làm kiểu biến thông thường, và `void` **không phải** một đối tượng hoặc một giá trị `null`.

## 2. Phương thức `void`: làm việc mà không trả về giá trị

Phương thức `void` thường dùng khi mục đích chính là **tạo tác động** (*side effect*), chẳng hạn:

- In thông báo hoặc ghi log.
- Cập nhật trạng thái của một đối tượng.
- Gửi yêu cầu, lưu dữ liệu hoặc thực hiện thao tác I/O.
- Thay đổi một đối tượng thông qua API kiểm soát dữ liệu.
- Thực hiện một chuỗi bước xử lý mà kết quả không cần trả về cho nơi gọi.

Ví dụ:

```java
class Lamp {
    private boolean on;

    void turnOn() {
        on = true;
    }

    boolean isOn() {
        return on;
    }
}
```

`turnOn()` trả về `void` vì mục đích của nó là đổi trạng thái trường `on`. `isOn()` trả về `boolean` vì nơi gọi cần biết đèn đang bật hay tắt.

**`void` không đồng nghĩa “không làm gì”.** Phương thức `void` vẫn có thể tính toán tạm thời, gọi các phương thức khác, cập nhật dữ liệu và ném ngoại lệ.

### 2.1. Phương thức `void` có thể kết thúc tự nhiên

```java
static void greet(String name) {
    System.out.println("Xin chào, " + name);
}
```

Nếu thực thi đến dấu `}` cuối thân phương thức mà không có câu lệnh thoát khác, phương thức `void` kết thúc và trả **quyền điều khiển** về nơi gọi. Không có giá trị kết quả được trả về.

### 2.2. `return;` trong phương thức `void`

Từ khóa `return` **không bị cấm** trong phương thức `void`. Dạng hợp lệ là `return;` **không có biểu thức phía sau**. Nó kết thúc thực thi phương thức ngay tại vị trí đó.

```java
static void printPositive(int number) {
    if (number <= 0) {
        System.out.println("Bỏ qua: " + number);
        return; // Kết thúc sớm; không trả về giá trị
    }

    System.out.println("Hợp lệ: " + number);
}
```

Với `printPositive(-2)`, chương trình in `Bỏ qua: -2` rồi rời phương thức; dòng `Hợp lệ` không chạy. Với `printPositive(5)`, điều kiện sai, chương trình in `Hợp lệ: 5` và kết thúc tại cuối thân phương thức.

`return;` thường được dùng làm **guard clause** để tránh lồng nhiều `if`, miễn là luồng điều khiển vẫn dễ hiểu.

### 2.3. Không được `return expression;` trong phương thức `void`

Đoạn dưới **không hợp lệ**:

```java
static void calculate() {
    return 10; // Lỗi biên dịch: phương thức void không thể trả về giá trị
}
```

Muốn trả về `10`, phải đổi kiểu trả về:

```java
static int calculate() {
    return 10;
}
```

Nếu chỉ muốn kết thúc sớm trong phương thức `void`, dùng `return;`.

## 3. Phương thức trả về giá trị: kiểu khai báo và lệnh `return`

Với phương thức không phải `void`, kiểu đặt trước tên phương thức biểu thị **kiểu kết quả** mà nơi gọi được phép nhận.

```java
static int multiply(int a, int b) {
    return a * b;
}

static boolean isEven(int number) {
    return number % 2 == 0;
}

static String fullName(String firstName, String lastName) {
    return firstName + " " + lastName;
}
```

- `multiply` trả về `int`.
- `isEven` trả về `boolean`.
- `fullName` trả về một tham chiếu kiểu `String`.

Câu lệnh `return expression;` thực hiện ba việc quan trọng:

1. Đánh giá biểu thức sau từ khóa `return`.
2. Chuyển kết quả thành kiểu tương thích với kiểu trả về được khai báo (theo quy tắc chuyển đổi được Java cho phép).
3. Kết thúc thực thi phương thức tại đó và chuyển giá trị về nơi gọi.

Ví dụ `int result = multiply(3, 4);` khiến biến `result` nhận `12`. Mã **sau một câu lệnh `return` được thực thi** trong cùng lần gọi sẽ không tiếp tục được chạy.

Đừng nhầm giữa **kiểu tham số** và **kiểu trả về**. `static double average(int a, int b)` nhận hai `int` nhưng trả về `double`; hai nhóm kiểu độc lập và phục vụ hai hướng truyền dữ liệu khác nhau.

## 4. Chương trình Java 17 hoàn chỉnh kết hợp `void` và phương thức trả về giá trị

Lưu toàn bộ mã sau vào tệp **`MethodReturnDemo.java`**:

```java
class Receipt {
    final int amount;

    Receipt(int amount) {
        this.amount = amount;
    }
}

public class MethodReturnDemo {
    static void greet(String name) {
        System.out.println("Xin chào, " + name);
    }

    static int add(int a, int b) {
        return a + b;
    }

    static boolean isAdult(int age) {
        return age >= 18;
    }

    static String category(int score) {
        if (score >= 80) {
            return "Giỏi";
        }
        if (score >= 50) {
            return "Đạt";
        }
        return "Cần cố gắng";
    }

    static void printPositive(int number) {
        if (number <= 0) {
            System.out.println("Bỏ qua: " + number);
            return;
        }
        System.out.println("Hợp lệ: " + number);
    }

    static Receipt createReceipt(int amount) {
        return new Receipt(amount);
    }

    public static void main(String[] args) {
        greet("An");

        int sum = add(7, 5);
        System.out.println("Tổng: " + sum);
        System.out.println("Đủ tuổi: " + isAdult(20));
        System.out.println("Xếp loại: " + category(76));

        printPositive(-3);
        printPositive(4);

        Receipt receipt = createReceipt(150);
        System.out.println("Biên lai: " + receipt.amount);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 MethodReturnDemo.java
java MethodReturnDemo
```

**Stdout chính xác:**

```text
Xin chào, An
Tổng: 12
Đủ tuổi: true
Xếp loại: Đạt
Bỏ qua: -3
Hợp lệ: 4
Biên lai: 150
```

Diễn giải:

1. `greet("An")` là lời gọi phương thức `void`; tác động của nó là in thông báo.
2. `add(7, 5)` trả về số nguyên `12`; mã gọi lưu kết quả vào `sum` rồi in.
3. `isAdult(20)` trả về giá trị logic `true`, có thể nối vào chuỗi khi in.
4. `category(76)` trả về `"Đạt"` nhờ nhánh điều kiện thứ hai. Dù có nhiều `return` trong mã nguồn, **chỉ một đường thực thi được chọn** cho một lời gọi.
5. `printPositive(-3)` gặp `return;` sớm, nên không in `Hợp lệ: -3`; `printPositive(4)` đi đến cuối thân và in `Hợp lệ: 4`.
6. `createReceipt(150)` trả về **tham chiếu đến một đối tượng `Receipt` mới tạo**. Nơi gọi có thể đọc `receipt.amount` vì trường này có quyền truy cập phù hợp trong ví dụ (các lớp ở cùng package).

`Receipt` và `MethodReturnDemo` là hai lớp cấp cao nhất trong cùng tệp nguồn; chỉ `MethodReturnDemo` khai báo `public`. Mã trên cố ý không có phụ thuộc ngoài JDK.

## 5. Sử dụng kết quả của lời gọi phương thức

Lời gọi phương thức có kiểu trả về khác `void` là một **biểu thức có giá trị**, nên có thể xuất hiện trong nhiều ngữ cảnh khác nhau:

```java
int total = add(3, 5);                   // Gán kết quả cho biến
int doubled = add(3, 5) * 2;             // Dùng trong biểu thức
System.out.println(add(3, 5));          // Truyền làm đối số
if (isAdult(20)) {                       // Dùng trong điều kiện boolean
    System.out.println("Đủ tuổi");
}
```

Các đoạn ngắn này giả định chúng nằm trong phương thức có thể gọi `add` và `isAdult` đã khai báo ở mục 4; chúng **không phải chương trình độc lập**.

Đặc biệt, **không bắt buộc phải lưu kết quả** vào biến:

```java
add(3, 5); // Hợp lệ, nhưng kết quả 8 bị bỏ qua
```

Java cho phép lời gọi phương thức dùng như một câu lệnh biểu thức ngay cả khi nó trả về giá trị. Việc bỏ kết quả đôi khi hợp lý nếu phương thức còn có side effect; nhưng với hàm chỉ tính toán, đây thường là dấu hiệu viết nhầm hoặc thiếu bước sử dụng kết quả.

Ngược lại, **lời gọi `void` không cung cấp một giá trị** cho phép gán hoặc dùng trong các biểu thức đòi giá trị.

```java
greet("An");                // Hợp lệ: câu lệnh gọi phương thức void
int x = greet("An");        // SAI: void không chuyển thành int
System.out.println(greet("An")); // SAI: println cần đối số có giá trị
```

Nếu chỉ muốn vừa in lời chào vừa có một chuỗi để sử dụng tiếp, cần tách ý định thành phương thức **trả về chuỗi** và lệnh in:

```java
static String greeting(String name) {
    return "Xin chào, " + name;
}

// Trong main:
String message = greeting("An");
System.out.println(message);
```

`greeting` tạo ra giá trị, còn `println` thực hiện tác động in và có kiểu trả về `void`. Phân tách này giúp dễ kiểm thử kết quả và tái sử dụng phương thức tạo chuỗi.

## 6. Phân biệt `return` với `System.out.println`

Hai hành động này **không tương đương**:

| `return` | `System.out.println` |
| --- | --- |
| Chuyển một giá trị về nơi gọi (nếu phương thức có kiểu trả về) | Ghi nội dung ra standard output |
| Kết thúc lời gọi phương thức hiện tại ngay tại câu lệnh đó | Sau khi in xong, các lệnh tiếp theo có thể vẫn chạy |
| Kết quả có thể được nơi gọi lưu hoặc dùng tiếp | Bản thân `println` trả về `void` |
| Không bắt buộc hiển thị bất kỳ thông tin nào ra màn hình | Có hiệu ứng in ra màn hình/luồng đầu ra |
| `return;` hợp lệ trong phương thức `void` để kết thúc sớm | `println` có thể được gọi từ cả phương thức `void` và không phải `void` |

Ví dụ sai về mặt mục đích:

```java
static int square(int number) {
    System.out.println(number * number);
    // SAI: thiếu return giá trị int
}
```

Chỉ in kết quả `number * number` **không đáp ứng** yêu cầu kiểu trả về `int`. Phiên bản đúng nếu muốn **trả về** là:

```java
static int square(int number) {
    return number * number;
}
```

Nơi gọi quyết định hiển thị hay lưu kết quả:

```java
int result = square(6);
System.out.println(result); // 36
```

Nếu nhiệm vụ thật sự chỉ là in bình phương và không cần trả về kết quả, có thể dùng:

```java
static void printSquare(int number) {
    System.out.println(number * number);
}
```

Lựa chọn phụ thuộc vào **hợp đồng của phương thức**, không phụ thuộc việc bên trong có phép tính.

## 7. Phương thức khác `void` phải trả về trên mọi đường kết thúc bình thường

Với phương thức được khai báo trả về giá trị, Java kiểm tra rằng không có **đường thực thi có thể hoàn tất bình thường mà thiếu giá trị trả về**. Đây là kiểm tra tại thời điểm biên dịch; không đủ khi “đa số trường hợp đều có `return`”.

### Ví dụ sai: thiếu nhánh trả về

```java
static String result(int score) {
    if (score >= 50) {
        return "Đạt";
    }
    // SAI: nếu score < 50, phương thức đến cuối thân mà không return
}
```

Khắc phục bằng `else`:

```java
static String result(int score) {
    if (score >= 50) {
        return "Đạt";
    } else {
        return "Chưa đạt";
    }
}
```

Hoặc dùng kết quả mặc định sau `if`:

```java
static String result(int score) {
    if (score >= 50) {
        return "Đạt";
    }
    return "Chưa đạt";
}
```

Cả hai phương án đều đáp ứng yêu cầu: mọi đường **hoàn tất bình thường** trả về `String`.

### `return` trong vòng lặp và `switch`

`return` bên trong vòng lặp hoặc `switch` **thoát khỏi toàn bộ phương thức**, không chỉ khỏi vòng lặp/`switch`. Đừng nhầm nó với `break` hay `continue`:

- `break` thường thoát khỏi vòng lặp hoặc khối `switch` phù hợp.
- `continue` bỏ qua phần còn lại của vòng lặp hiện tại và sang vòng lặp kế tiếp.
- `return` kết thúc phương thức, có thể gửi kết quả về nơi gọi.

Với một số vòng lặp, trình biên dịch không thể bảo đảm chúng luôn có lần lặp sẽ kích hoạt `return`, nên vẫn cần xét đường không lặp hoặc không vào nhánh. Một phương thức có kiểu trả về **có thể ném ngoại lệ** thay vì trả về trong một nhánh; khi ngoại lệ thoát khỏi phương thức, nhánh đó không phải đường hoàn tất bình thường.

### Ví dụ có ngoại lệ thay cho một giá trị

```java
static int positiveValue(int number) {
    if (number <= 0) {
        throw new IllegalArgumentException("number must be positive");
    }
    return number;
}
```

Nếu `number <= 0`, phương thức ném ngoại lệ và **không có giá trị `int` được trả về**. Nếu `number > 0`, phương thức trả về `number`. Đây là mã hợp lệ; không cần viết `return` sau `throw`.

## 8. Kiểu trả về phải tương thích với biểu thức trong `return`

Java kiểm tra kiểu trả về **tại thời điểm biên dịch**, kể cả khi kết quả không được nơi gọi sử dụng.

### 8.1. Trả về primitive

```java
static long count() {
    return 10;        // Hợp lệ: int literal được widening thành long
}

static double average(int a, int b) {
    return (a + b) / 2.0; // double, không chia nguyên
}

static boolean hasItems(int count) {
    return count > 0;
}
```

`return "10";` không hợp lệ trong phương thức khai báo `int`; Java không tự biến `String` thành số nguyên trong câu lệnh `return`. Tương tự, `return 1;` không hợp lệ với kiểu trả về `boolean`.

Một phương thức khai báo `double` có thể trả về biểu thức kiểu `int` qua chuyển đổi mở rộng phù hợp, nhưng điều đó **không sửa phép toán đã tính sai kiểu**. Chẳng hạn `return (a + b) / 2;` thực hiện **chia nguyên** trước rồi mới chuyển kết quả thành `double`. Dùng `2.0` trong phép chia nếu muốn giá trị thập phân.

### 8.2. Trả về tham chiếu

```java
static CharSequence label() {
    return "Hello";            // String là một CharSequence
}

static Object box() {
    return Integer.valueOf(7); // Integer cũng là Object
}
```

Kiểu biểu thức `return` phải có khả năng chuyển đổi phù hợp sang kiểu trả về. Một kiểu cha/interface có thể nhận tham chiếu của đối tượng thuộc lớp con hoặc lớp triển khai tương thích.

### 8.3. Trả về `null`

```java
static String findName(boolean found) {
    if (found) {
        return "An";
    }
    return null;
}
```

`null` là giá trị hợp lệ của **kiểu tham chiếu** (trừ ràng buộc chuyên biệt của ngôn ngữ/công cụ), nhưng **không** phải giá trị của kiểu primitive.

```java
static int findNumber() {
    return null; // SAI: null không thể chuyển thành int
}
```

Một phương thức trả về `String` với `null` có thể khiến nơi gọi gặp `NullPointerException` khi thực hiện `findName(false).length()`. Hãy mô tả rõ hợp đồng có thể trả `null`, hoặc thiết kế kiểu kết quả biểu thị trạng thái không tìm thấy, chẳng hạn `Optional<String>` khi phù hợp.

### 8.4. `void` khác `Void` và `null`

- `void` (chữ thường) biểu thị phương thức **không có kết quả trả về**.
- `java.lang.Void` (chữ hoa) là **một lớp tham chiếu** thường được dùng trong API generic để đại diện việc không có kết quả có ý nghĩa; nó **không biến thành `void`**.
- Một phương thức khai báo `Void` có thể dùng `return null;`, vì `null` là giá trị tham chiếu; điều này không giống `void` với `return;`.

Ví dụ minh họa:

```java
static void doWork() {
    return; // void: không có giá trị
}

static Void doOtherWork() {
    return null; // Void: trả về một giá trị tham chiếu null
}
```

Không cần dùng `Void` cho các phương thức thông thường nếu `void` đáp ứng mục đích; `Void` chủ yếu xuất hiện trong hợp đồng API generic, ví dụ `Callable<Void>`.

## 9. Trả về primitive và trả về đối tượng: hiểu đúng giá trị tham chiếu

Java **truyền tham số theo giá trị** và câu lệnh `return` cũng cung cấp một **giá trị** cho nơi gọi. Khi kiểu là tham chiếu, giá trị đó là **tham chiếu tới đối tượng**, không phải bản sao tự động của toàn bộ đối tượng.

Ví dụ:

```java
class Box {
    int value;

    Box(int value) {
        this.value = value;
    }
}

class Factory {
    static Box createBox() {
        return new Box(10);
    }

    static Box sameBox(Box input) {
        return input;
    }
}
```

Các khai báo trên là ví dụ để dùng trong mã khác, không phải chương trình độc lập. Đặt đoạn này trong một phương thức có quyền truy cập:

```java
Box first = Factory.createBox();
Box second = Factory.sameBox(first);
second.value = 99;

System.out.println(first.value);  // 99
System.out.println(first == second); // true
```

- `createBox()` tạo một đối tượng `Box` mới và trả về tham chiếu đến đối tượng đó.
- `sameBox(first)` nhận một bản sao của giá trị tham chiếu, sau đó `return input;` trả lại tham chiếu cùng đối tượng; không có `new Box(...)` trong `sameBox`.
- Vì `first` và `second` cùng tham chiếu một đối tượng, sửa `second.value` được quan sát qua `first.value`.
- Đối với `int`, `double`, `boolean`, v.v., giá trị primitive được trả về không tự có cơ chế “chia sẻ đối tượng” như tham chiếu.

Một phương thức trả về tham chiếu **không tự bảo vệ trạng thái nội bộ**. Nếu trả về trực tiếp đối tượng mutable đang được giữ trong lớp, bên gọi có thể sửa đối tượng đó nếu API cho phép. Khi cần đóng gói, cân nhắc đối tượng bất biến hoặc defensive copy.

## 10. Phương thức có thể vừa trả về giá trị vừa có side effect

Sự khác biệt `void` và non-`void` nằm ở **kiểu kết quả**, không phải quy tắc “có/không có tác động phụ”.

Ví dụ phương thức **trả về giá trị** nhưng cũng sửa trạng thái:

```java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int incrementAndGet() {
        value++;
        return value;
    }

    int getValue() {
        return value;
    }
}
```

- `increment()` thay đổi field và không có giá trị trả về.
- `incrementAndGet()` **vừa** thay đổi field **vừa** trả về giá trị mới.
- `getValue()` chỉ đọc field và trả về giá trị, không thay đổi field trong cách triển khai này.

Nếu yêu cầu nghiệp vụ chỉ là “hãy thực hiện thay đổi”, `void` thường phù hợp. Nếu người gọi **cần** trạng thái hoặc kết quả sau thao tác, việc trả về giá trị có thể hữu ích. Nên chọn kiểu trả về để phản ánh **ý nghĩa công khai của API**, không chỉ dựa vào số dòng code bên trong.

### Ví dụ chạy được: tác động phụ và giá trị kết quả

Lưu thành **`CounterDemo.java`**:

```java
class Counter {
    private int value;

    void increment() {
        value++;
    }

    int incrementAndGet() {
        value++;
        return value;
    }

    int getValue() {
        return value;
    }
}

public class CounterDemo {
    public static void main(String[] args) {
        Counter counter = new Counter();
        counter.increment();
        System.out.println("Sau void: " + counter.getValue());

        int newValue = counter.incrementAndGet();
        System.out.println("Kết quả trả về: " + newValue);
        System.out.println("Giá trị hiện tại: " + counter.getValue());
    }
}
```

```bash
javac -encoding UTF-8 CounterDemo.java
java CounterDemo
```

Stdout:

```text
Sau void: 1
Kết quả trả về: 2
Giá trị hiện tại: 2
```

Không có mâu thuẫn trong việc `incrementAndGet()` cập nhật trạng thái và trả về kết quả. Khi sử dụng API thực tế, điều cần đọc là **hợp đồng** của phương thức về giá trị trả về và tác động phụ.

## 11. `return` và `finally`: thứ tự thực thi cần biết

Trong `try`/`finally`, Java bảo đảm khối `finally` được thực thi trong quá trình rời `try` ở các trường hợp thông thường, kể cả khi có `return`. Vì vậy không nên mặc định “gặp `return` là bỏ qua mọi `finally`”.

Ví dụ chạy được, lưu thành **`FinallyReturnDemo.java`**:

```java
public class FinallyReturnDemo {
    static int compute() {
        try {
            System.out.println("Đang tính");
            return 10;
        } finally {
            System.out.println("Dọn dẹp");
        }
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + compute());
    }
}
```

```bash
javac -encoding UTF-8 FinallyReturnDemo.java
java FinallyReturnDemo
```

Stdout:

```text
Đang tính
Dọn dẹp
Kết quả: 10
```

Biểu thức sau `return` được đánh giá trước; sau đó `finally` chạy trước khi kết quả được giao lại cho nơi gọi. **Tránh viết `return` bên trong `finally`**: nó có thể che mất kết quả trả về hoặc ngoại lệ đang phát sinh và khiến chương trình khó dự đoán. `finally` cũng có thể gặp các tình huống đặc biệt như JVM chấm dứt đột ngột khiến việc thực thi không diễn ra như luồng bình thường, nên không nên coi nó là bảo đảm tuyệt đối trong mọi trường hợp hệ thống.

## 12. Liên quan đến ghi đè và nạp chồng phương thức

Kiểu trả về ảnh hưởng đến hợp đồng của phương thức, nhưng không đủ để phân biệt hai phương thức cùng tên khi **nạp chồng (overloading)**.

### 12.1. Không thể overload chỉ bằng kiểu trả về

Ví dụ sai:

```java
class Calculator {
    int parse(String text) {
        return Integer.parseInt(text);
    }

    double parse(String text) {
        return Double.parseDouble(text);
    }
}
```

Cả hai phương thức cùng tên `parse` và cùng danh sách tham số `(String)`. Chúng **không thể cùng tồn tại** chỉ vì một cái trả về `int` và cái khác trả về `double`. Trong Java, kiểu trả về **không nằm trong chữ ký phương thức được dùng để phân biệt overload**.

Ví dụ hợp lệ:

```java
class Calculator {
    int parse(String text) {
        return Integer.parseInt(text);
    }

    double parse(double value) {
        return value;
    }
}
```

Hai phương thức `parse` trên có **danh sách tham số khác nhau** nên hợp lệ. Trong mã API thực tế, nên đặt tên sao cho ý nghĩa thao tác rõ ràng, không cố dùng overload để “chọn” kiểu kết quả mong muốn.

### 12.2. Override và kiểu trả về

Khi **ghi đè (overriding)** instance method, phương thức lớp con cần đáp ứng quy tắc tương thích kiểu trả về của Java:

- Có thể giữ nguyên kiểu trả về.
- Với kiểu tham chiếu, có thể dùng **covariant return type** (trả về một kiểu con phù hợp của kiểu trả về tham chiếu ở lớp cha).
- Không thể tùy tiện đổi phương thức trả `void` thành phương thức trả `int` khi override, hoặc đổi kiểu primitive `int` thành `long`.

Ví dụ minh họa:

```java
class Animal {
}

class Dog extends Animal {
}

class AnimalFactory {
    Animal make() {
        return new Animal();
    }
}

class DogFactory extends AnimalFactory {
    @Override
    Dog make() {
        return new Dog(); // Hợp lệ: Dog là subtype của Animal
    }
}
```

Lớp con `DogFactory` có thể khai báo `Dog make()` vì `Dog` là subtype của `Animal`. Đây là **override**, khác với **overload**. Đoạn trên là khai báo kiểu minh họa, không có `main`.

## 13. Trường hợp phương thức `void` và phương thức có kiểu trả về trong interface

Một interface có thể khai báo hành vi với cả hai dạng kết quả:

```java
interface Printer {
    void print(String text);

    int pagesPrinted();
}
```

Một lớp triển khai phải cung cấp thân phương thức phù hợp nếu nó là lớp cụ thể:

```java
class ConsolePrinter implements Printer {
    private int pages;

    @Override
    public void print(String text) {
        System.out.println(text);
        pages++;
    }

    @Override
    public int pagesPrinted() {
        return pages;
    }
}
```

Ở interface, các phương thức trừu tượng thông thường là `public abstract` theo quy tắc ngôn ngữ. Vì thế phương thức implement tại lớp cụ thể dùng `public`; không được giảm mức truy cập thành package-private. `print` là `void` và `pagesPrinted` trả về `int`. Hai phương thức thể hiện hai chức năng khác nhau: **thực thi thao tác** và **truy vấn thông tin**.

Một phương thức `abstract` không có thân chỉ **khai báo hợp đồng**; chỉ phương thức có thân mới trực tiếp chứa các câu lệnh `return`. Khi triển khai, quy tắc `void`/non-`void` vẫn được áp dụng như ở các lớp thông thường.

## 14. Chọn kiểu trả về sao cho API dễ dùng

Hãy dựa trên mục tiêu của phương thức:

| Mục tiêu | Kiểu trả về thường phù hợp | Ví dụ |
| --- | --- | --- |
| In ra một thông báo | `void` | `void printInvoice()` |
| Tính tổng tiền | `int`, `long` hoặc kiểu số phù hợp | `long totalPrice()` |
| Kiểm tra điều kiện | `boolean` | `boolean isValid()` |
| Trả về tên hiển thị | `String` | `String displayName()` |
| Tìm đối tượng | Kiểu tham chiếu hoặc `Optional<T>` tùy hợp đồng | `Optional<User> findUser(int id)` |
| Tạo đối tượng | Lớp hoặc interface phù hợp | `Receipt createReceipt()` |
| Cập nhật dữ liệu, không cần trả thông tin | `void` | `void changePassword(String value)` |
| Cập nhật rồi cần biết thành công không | `boolean` hoặc kiểu kết quả thích hợp | `boolean tryReserve(int count)` |
| Cập nhật rồi trả về trạng thái mới | Kiểu của trạng thái | `int incrementAndGet()` |

**Không bắt buộc** mọi hành động cập nhật đều trả về `void`: một phương thức cập nhật có thể trả trạng thái, số hàng bị ảnh hưởng hoặc chính đối tượng để hỗ trợ fluent API. Ngược lại, một phương thức tính toán có thể chọn `void` nếu hợp đồng chỉ yêu cầu xuất kết quả qua I/O. Điều quan trọng là **người gọi biết nhận được gì**.

Đối với API dễ kiểm thử, những phép tính thuần (ít hoặc không có side effect) thường nên **trả về kết quả** rồi để nơi gọi quyết định in, lưu hay sử dụng. Ví dụ `int calculateTotal()` tái sử dụng thuận tiện hơn `void printTotal()` khi cùng kết quả phải được dùng trong giao diện, kiểm thử và nghiệp vụ.

Tránh tạo một kết quả trả về “giả” (ví dụ `return 0;`) chỉ để thỏa trình biên dịch khi phương thức thực chất không có ý nghĩa kết quả. Cần chỉnh lại kiểu trả về hoặc định nghĩa rõ hợp đồng.

## 15. Các lỗi phổ biến và cách khắc phục

| Dấu hiệu | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `void cannot be converted to int` hoặc thông báo tương đương | Gán kết quả lời gọi `void` cho biến số | Đổi thiết kế phương thức để trả về `int` hoặc bỏ phép gán |
| `return 5;` bên trong `void method()` | Cố trả về giá trị trong phương thức `void` | Dùng `return;` hoặc đổi kiểu trả về |
| `return;` bên trong `int method()` | Không trả về một giá trị thuộc kiểu yêu cầu | Dùng `return expression;` tương thích |
| `missing return statement` | Có đường kết thúc bình thường thiếu `return` | Bao phủ các nhánh bằng kết quả hoặc dùng `throw` khi dữ liệu không hợp lệ |
| `System.out.println(result)` rồi cho rằng phương thức đã trả về `result` | Nhầm xuất ra stdout với trả về | Thêm `return result;` nếu kiểu trả về yêu cầu |
| Trả về `null` từ phương thức `int` | `null` chỉ phù hợp kiểu tham chiếu | Trả số hợp lệ hoặc thiết kế API khác |
| `return "123";` từ phương thức `int` | Không tự động chuyển String sang int | Chuyển đổi có kiểm soát, ví dụ `Integer.parseInt(...)` |
| Hai phương thức cùng tên/tham số nhưng khác return type | Cố overload chỉ bằng return type | Đổi danh sách tham số hoặc tên phương thức |
| Kết quả tính toán bị sai phần thập phân | Chia nguyên trước khi trả về `double` | Dùng phép tính số thực, ví dụ `/ 2.0` |
| Trả về đối tượng mutable rồi người gọi thay đổi dữ liệu bất ngờ | Trả về cùng tham chiếu đến trạng thái nội bộ | Đóng gói, tạo bản sao thích hợp hoặc dùng immutable object |
| Viết `return` trong `finally` rồi mất kết quả ban đầu | `finally` có thể thay đổi đột ngột cách phương thức kết thúc | Giữ `finally` cho dọn dẹp, tránh `return` ở đó |

Thông báo `javac` có thể khác nhau giữa các JDK. Hãy đọc dòng khai báo **kiểu trả về**, kiểm tra mọi lệnh `return` và xác định những nơi đang **sử dụng kết quả của lời gọi**.

## 16. Tự luyện với đáp án

### Bài 1: Phương thức nào là `void`?

Xét các khai báo:

```java
static void a() { System.out.println("A"); }
static int b() { return 10; }
static String c() { return "C"; }
static void d() { return; }
```

**Đáp án:** `a` và `d` là phương thức `void`. `d` có `return;` nhưng không tạo giá trị. `b` trả về `int` và `c` trả về `String`.

### Bài 2: Đoạn nào sai?

```java
static int absolute(int x) {
    if (x < 0) {
        return -x;
    }
}
```

**Đáp án:** Thiếu `return x;` (hoặc một kết quả phù hợp) khi `x >= 0`. Sửa:

```java
static int absolute(int x) {
    if (x < 0) {
        return -x;
    }
    return x;
}
```

Với `x = Integer.MIN_VALUE`, phép đổi dấu của `int` có thể bị tràn số; ví dụ này chỉ minh họa luồng `return`, không thay thế API tính giá trị tuyệt đối cần xét mọi trường hợp dữ liệu.

### Bài 3: Dự đoán output

```java
static void announce() {
    System.out.println("Đang xử lý");
}

static int compute() {
    announce();
    return 4 * 3;
}
```

Trong `main`:

```java
System.out.println("Kết quả: " + compute());
```

**Đáp án:**

```text
Đang xử lý
Kết quả: 12
```

Vì `compute()` gọi phương thức `void` để in trước, sau đó trả về giá trị `12` cho lệnh in ở `main`.

### Bài 4: Biểu thức sau có hợp lệ không?

```java
static String getStatus() {
    return "READY";
}

static void printStatus() {
    System.out.println(getStatus());
}
```

**Đáp án:** Hợp lệ. `getStatus()` trả về chuỗi `"READY"` và `println(...)` nhận chuỗi đó để in. `printStatus()` là `void`; nó không trả chuỗi cho nơi gọi.

### Bài 5: Giá trị hay tham chiếu?

```java
class Item {
    int quantity = 1;
}

static Item same(Item item) {
    return item;
}
```

Giả sử bên trong một phương thức:

```java
Item first = new Item();
Item second = same(first);
second.quantity = 8;
System.out.println(first.quantity);
```

**Đáp án:** In `8`. `same` trả về **cùng giá trị tham chiếu** chứ không tạo đối tượng mới; cả `first` và `second` truy cập cùng một `Item`.

## Ghi nhớ

- **`void`:** phương thức **không tạo ra giá trị trả về**; có thể kết thúc tự nhiên hoặc dùng `return;` để dừng sớm.
- **Kiểu trả về cụ thể:** dùng `return expression;` với giá trị **tương thích**, bảo đảm mọi đường có thể kết thúc bình thường trả về kết quả.
- **`return` khác in ra màn hình:** `return` truyền giá trị về nơi gọi và kết thúc phương thức; `println` chỉ thực hiện thao tác xuất.
- **Kết quả có thể dùng trực tiếp:** gán biến, truyền tham số, kết hợp trong biểu thức hoặc điều kiện; không thể làm như vậy với lời gọi `void`.
- **Side effect không quyết định kiểu trả về:** một phương thức có thể vừa thay đổi trạng thái vừa trả về giá trị.
- **Kiểu tham chiếu:** trả về một tham chiếu đến đối tượng, không tự tạo bản sao đối tượng; **`null`** hợp lệ với kiểu tham chiếu nhưng không với primitive.
- Khi thiết kế phương thức, hãy xác định **hợp đồng với nơi gọi** trước: chỉ cần thực thi hành động, hay cần một giá trị để tiếp tục xử lý?
