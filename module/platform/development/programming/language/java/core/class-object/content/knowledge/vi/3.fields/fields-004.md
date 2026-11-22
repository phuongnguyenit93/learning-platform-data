# Giá trị mặc định của trường và yêu cầu khởi tạo biến cục bộ trong Java

## 1. Cùng là biến, vì sao có chỗ đọc được ngay và có chỗ bị lỗi biên dịch?

Xét hai đoạn mã Java:

```java
class Notebook {
    int pageCount;                 // Field của mỗi Notebook.

    void printCount() {
        System.out.println(pageCount); // Hợp lệ: ban đầu field có giá trị 0.
    }
}
```

```java
class Example {
    void printCount() {
        int pageCount;                  // Biến cục bộ.
        // System.out.println(pageCount);
        // Nếu bỏ dấu //, dòng trên không biên dịch:
        // variable pageCount might not have been initialized
    }
}
```

Cả hai biến đều khai báo kiểu `int`. Điểm khác biệt là **vị trí và loại biến**.

- **Trường dữ liệu (*field*)** được khai báo trực tiếp trong thân lớp hoặc trong một khai báo kiểu thích hợp. Instance field thuộc từng đối tượng; `static field` thuộc lớp. Java cung cấp **giá trị mặc định** cho các field khi thực hiện quy trình cấp phát/khởi tạo, trước khi áp dụng các phép khởi tạo tường minh.
- **Biến cục bộ (*local variable*)** khai báo trong method, constructor hoặc block phải được **gán giá trị trước khi đọc**. Java không cấp giá trị mặc định có thể sử dụng cho biến cục bộ. Trình biên dịch dùng quy tắc **definite assignment** (*chắc chắn đã được gán*) để kiểm tra các luồng điều khiển có thể đi đến điểm đọc biến.
- **Phần tử mảng** cũng có giá trị mặc định khi tạo mảng; việc biến cục bộ đang giữ tham chiếu tới mảng được gán khác với việc các phần tử của mảng được khởi tạo.

Quy tắc này là một phần của ngôn ngữ Java, không tùy thuộc việc hệ điều hành hay JVM ngoài thực tế có “xóa sạch vùng nhớ” bằng kỹ thuật nào. Không nên dựa vào dữ liệu rác hoặc giả định về layout bộ nhớ để giải thích kết quả.

## 2. Bảng giá trị mặc định của field và phần tử mảng

Nếu không có phép gán tường minh nào thay đổi giá trị, Java bảo đảm các giá trị khởi tạo mặc định sau:

| Kiểu dữ liệu | Giá trị mặc định | Chú ý |
| --- | --- | --- |
| `byte` | `0` | Giá trị số nguyên 0, thuộc kiểu `byte`. |
| `short` | `0` | Giá trị số nguyên 0, thuộc kiểu `short`. |
| `int` | `0` | Không phải `null`. |
| `long` | `0L` | Biểu diễn kết quả có thể in là `0`. |
| `float` | `0.0f` | In bằng `println` thông thường là `0.0`. |
| `double` | `0.0d` | In bằng `println` thông thường là `0.0`. |
| `char` | `'\u0000'` | Ký tự NUL, mã Unicode U+0000, **không phải** ký tự `'0'` hoặc dấu cách. |
| `boolean` | `false` | Không phải `0` hay `null`. |
| Bất kỳ kiểu tham chiếu nào | `null` | Bao gồm `String`, lớp tự định nghĩa, interface, enum, mảng và nhiều kiểu tham chiếu khác. |

Trong bảng, `0L`, `0.0f`, `0.0d` là cách viết literal minh họa đúng kiểu; giá trị mặc định bản thân không cần được “viết” vào chương trình. Với `char`, `'\u0000'` diễn đạt ký tự có giá trị bằng 0; in trực tiếp ký tự NUL thường **không tạo ra chữ nhìn thấy được** trên terminal.

Quy tắc áp dụng cho cả **instance field** và **static field**. Ví dụ:

```java
class Profile {
    int age;                  // Instance field -> 0
    boolean verified;         // Instance field -> false
    String displayName;       // Instance field -> null

    static long createdCount;  // Static field -> 0L
    static Profile active;     // Static field -> null
}
```

Đây là khai báo lớp có thể biên dịch nhưng không có `main` riêng. Field `createdCount` chỉ có **một trạng thái thuộc lớp**; mỗi đối tượng `Profile` có `age`, `verified` và `displayName` của riêng mình.

**Giá trị mặc định không phải lúc nào cũng là giá trị nghiệp vụ hợp lệ.** Ví dụ `age == 0` có thể là trạng thái thật hoặc biểu thị chưa gán, còn `displayName == null` không tự có nghĩa “tên rỗng”. Nếu mô hình yêu cầu tuổi dương và tên có nội dung, constructor hoặc phương thức tạo đối tượng nên kiểm tra và thiết lập dữ liệu phù hợp.

## 3. Ví dụ chạy độc lập: quan sát đủ các nhóm kiểu

Tạo tệp **`FieldDefaultsDemo.java`** với mã sau (Java 17 trở lên):

```java
class DefaultValues {
    byte byteValue;
    short shortValue;
    int intValue;
    long longValue;
    float floatValue;
    double doubleValue;
    char charValue;
    boolean booleanValue;
    String text;
    int[] numbers;

    static int staticCount;
}

public class FieldDefaultsDemo {
    public static void main(String[] args) {
        DefaultValues values = new DefaultValues();

        System.out.println("byte=" + values.byteValue);
        System.out.println("short=" + values.shortValue);
        System.out.println("int=" + values.intValue);
        System.out.println("long=" + values.longValue);
        System.out.println("float=" + values.floatValue);
        System.out.println("double=" + values.doubleValue);
        System.out.println("charCode=" + (int) values.charValue);
        System.out.println("boolean=" + values.booleanValue);
        System.out.println("text=" + values.text);
        System.out.println("numbers=" + values.numbers);
        System.out.println("staticCount=" + DefaultValues.staticCount);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac FieldDefaultsDemo.java
java FieldDefaultsDemo
```

Kết quả chuẩn:

```text
byte=0
short=0
int=0
long=0
float=0.0
double=0.0
charCode=0
boolean=false
text=null
numbers=null
staticCount=0
```

Các field trên không có initializer rõ ràng, nên chương trình quan sát được giá trị mặc định. `(int) values.charValue` chuyển mã ký tự NUL sang số `0` để output rõ ràng. Khi nối `String` với tham chiếu `null`, Java tạo biểu diễn văn bản `null` trong kết quả nối chuỗi; điều đó **không biến field** `text` hay `numbers` thành chuỗi `"null"`.

Một số phân biệt quan trọng:

- `new DefaultValues()` tạo **đối tượng** mới với các instance field đã được khởi tạo theo quy tắc Java.
- `DefaultValues values;` trong một method chỉ là khai báo **biến cục bộ giữ tham chiếu**, chưa được gán. Không thể đọc `values` trước khi gán giá trị.
- `DefaultValues.staticCount` là field tĩnh thuộc lớp; không cần instance để đọc nó (khi quyền truy cập cho phép).
- Nếu viết `values.numbers.length` ngay trong ví dụ này, chương trình có thể ném `NullPointerException` vì field `numbers` là `null`, chưa trỏ tới mảng.

## 4. Giá trị mặc định được đặt vào thời điểm nào?

Với một đối tượng được tạo bằng `new`, có thể hình dung các bước chính:

1. Java cấp phát đối tượng và thiết lập các instance field về giá trị mặc định (`0`, `false`, `null`, ...), bao gồm cả những field sẽ được gán lại ở initializer hoặc constructor.
2. Các bước xây dựng chuỗi đối tượng cha/con diễn ra theo quy tắc constructor của Java.
3. Các **instance field initializer** như `int count = 5;` và **instance initializer block** như `{ count++; }` của từng lớp được thực thi ở thời điểm tương ứng, theo thứ tự văn bản trong lớp, sau khởi tạo phần superclass.
4. Phần thân constructor của lớp hoàn thành các phép gán/kiểm tra còn lại. Khi constructor chain dùng `this(...)`, initializer của cùng lớp không bị thực hiện lại chỉ vì có thêm lời gọi ủy quyền.

Với **static field**, Java cũng có giai đoạn thiết lập giá trị mặc định khi lớp được chuẩn bị (*preparation*), trước khi các **static field initializer** và `static { ... }` thực thi trong quá trình **class initialization**. Khởi tạo lớp thường diễn ra trước lần *active use* đầu tiên; không đồng nhất với việc chỉ đọc hoặc nạp metadata của lớp.

Ví dụ về việc initializer ghi đè giá trị mặc định:

```java
class Configuration {
    static int port = 8080;   // Ghi đè 0 trong quá trình class initialization.
    String host = "localhost"; // Ghi đè null khi khởi tạo instance.

    Configuration(String host) {
        this.host = host;      // Tiếp tục ghi đè theo tham số constructor.
    }
}
```

Các câu trong comment mô tả thứ tự logic, không phải ba giá trị luôn có thể được quan sát dễ dàng từ mã bình thường. **Không nên cố tình đọc field của object đang xây dựng dở** để dựa vào giá trị mặc định: làm như vậy thường tạo lỗi thiết kế, nhất là khi constructor gọi method có thể bị override.

### Thứ tự field initializer và instance initializer có ảnh hưởng

Chương trình hoàn chỉnh **`InitializationValuesDemo.java`**:

```java
class Score {
    int value = 3;

    {
        value += 4;
    }

    Score() {
        value *= 2;
    }

    int getValue() {
        return value;
    }
}

public class InitializationValuesDemo {
    public static void main(String[] args) {
        Score first = new Score();
        Score second = new Score();
        System.out.println(first.getValue());
        System.out.println(second.getValue());
    }
}
```

```bash
javac InitializationValuesDemo.java
java InitializationValuesDemo
```

```text
14
14
```

Mỗi đối tượng mới ban đầu có `value == 0`; field initializer gán `3`; instance initializer cộng `4` thành `7`; constructor nhân đôi thành `14`. Đó là **trạng thái hoàn tất sau khởi tạo**, không còn là giá trị mặc định. Hai instance trải qua cùng các bước nhưng sở hữu field độc lập.

Tương tự, nếu khai báo `static int count = 3;` rồi có `static { count += 4; }`, giá trị nhìn thấy thông thường sau class initialization là `7`. Khối `static` không chạy lại khi tạo đối tượng thứ hai.

## 5. Biến cục bộ: khai báo chưa đồng nghĩa đã khởi tạo

Biến cục bộ được khai báo trong một block, method hoặc constructor:

```java
class LocalVariableExample {
    void calculate() {
        int quantity;              // Chỉ khai báo.
        quantity = 5;              // Gán lần đầu.
        System.out.println(quantity); // Hợp lệ vì chắc chắn đã được gán.
    }
}
```

Không có quy tắc tự động gán `quantity = 0` cho biến cục bộ có thể đọc được. Trình biên dịch kiểm tra **mọi đường thực thi có thể đi đến lần đọc** để quyết định biến đã được gán chắc chắn hay chưa. Với method ở trên, mọi đường dẫn tới `println` đều đi qua `quantity = 5;` nên hợp lệ.

Trái lại:

```java
class InvalidLocal {
    void print() {
        int quantity;
        // System.out.println(quantity); // Bỏ comment -> lỗi biên dịch.
    }
}
```

Code đang hiển thị **biên dịch được do dòng lỗi được comment**. Bỏ comment gây thông báo kiểu `variable quantity might not have been initialized`. Đây là lỗi **biên dịch**, không phải việc Java chạy và đọc ra `0` hay “giá trị rác”.

### Khác biệt với tham số method và constructor

Tham số cũng là biến trong phạm vi thực thi, nhưng được **gán từ đối số lời gọi** khi method/constructor bắt đầu, nên có thể đọc ngay:

```java
class ParameterExample {
    void show(int count) {
        System.out.println(count); // Hợp lệ: tham số có đối số truyền vào.
    }
}
```

Ví dụ `show(0)` in `0` do caller truyền số `0`, **không phải do Java tự mặc định gán biến cục bộ**. Nếu tham số kiểu tham chiếu nhận `null`, nó mang giá trị `null` hợp lệ nhưng không nên dereference mà không kiểm tra.

Biến được khai báo trong vòng `for` tăng dần bằng initializer (`for (int i = 0; ... )`) hoặc biến lặp trong enhanced for (`for (String name : names)`) cũng có giá trị ở những điểm sử dụng hợp lệ theo cơ chế tương ứng; không có một “giá trị mặc định cho mọi biến cục bộ”.

## 6. Definite assignment: Java kiểm tra theo luồng điều khiển

Để quyết định một biến cục bộ đã được gán trước khi đọc hay chưa, compiler xem xét cấu trúc chương trình, **không chạy thử chương trình** để đoán đầu vào. Phân biệt hai ý:

- **Đã được gán trên một nhánh** không đủ nếu có nhánh khác vẫn đến điểm đọc mà chưa gán.
- **Chắc chắn được gán trên mọi đường có thể đi đến điểm đọc** là điều kiện cần; có thể dùng `if/else`, `switch` hoặc một phép gán trước khi chia nhánh để bảo đảm.

### 6.1. Chỉ gán trong một nhánh `if`: chưa đủ

```java
class BranchProblem {
    static void show(boolean selected) {
        int price;
        if (selected) {
            price = 100;
        }

        // System.out.println(price);
        // Bỏ comment -> lỗi: price có thể chưa được gán.
    }
}
```

Đường đi `selected == false` bỏ qua phép gán. Compiler không cho phép đọc `price` sau `if`.

Sửa bằng `else`:

```java
class BranchSolution {
    static void show(boolean selected) {
        int price;
        if (selected) {
            price = 100;
        } else {
            price = 50;
        }

        System.out.println(price); // Hợp lệ ở cả hai nhánh.
    }
}
```

Hoặc đặt giá trị ban đầu trước `if`:

```java
int price = 50;
if (selected) {
    price = 100;
}
System.out.println(price);
```

Đoạn sau chỉ là **mảnh code trong một method có biến `selected` hợp lệ**, không phải chương trình độc lập. Khởi tạo chủ động là cách đơn giản để đọc code khi một biến có giá trị mặc định có ý nghĩa nghiệp vụ.

### 6.2. Hai lần `if` độc lập không thay thế `if/else` một cách tổng quát

```java
boolean isExpress = true;
int fee;

if (isExpress) {
    fee = 20;
}
if (!isExpress) {
    fee = 5;
}
// System.out.println(fee); // Có thể không vượt kiểm tra definite assignment.
```

Hai điều kiện đối lập về mặt logic con người, nhưng Java không chứng minh mọi quan hệ tùy ý giữa hai biểu thức `if` độc lập. Dùng `if/else` để thể hiện rõ “chắc chắn một trong hai nhánh”:

```java
int fee;
if (isExpress) {
    fee = 20;
} else {
    fee = 5;
}
System.out.println(fee);
```

Các đoạn trên là **mã minh họa trong method**, không có lớp `public` hoặc `main`.

### 6.3. Vòng lặp có thể không chạy

```java
class LoopProblem {
    static void printFirst(boolean available) {
        int first;

        while (available) {
            first = 1;
            break;
        }

        // System.out.println(first);
        // Bỏ comment -> lỗi: available có thể false ngay từ đầu.
    }
}
```

Dù trong vòng lặp có lệnh gán, compiler phải tính đến trường hợp vòng lặp chạy **0 lần**. Sửa bằng khởi tạo trước vòng lặp hoặc bố trí luồng điều khiển để có phép gán chắc chắn trên đường tới điểm đọc.

`do/while` bảo đảm thân vòng lặp bắt đầu được thực hiện ít nhất một lần, nhưng mọi nhánh như `break`, `continue`, exception hoặc phép gán có điều kiện bên trong vẫn phải được xem xét khi chứng minh definite assignment. Không nên thay `while` bằng `do/while` chỉ để “đánh lừa” compiler.

### 6.4. `switch`: cần bao phủ tất cả lối ra

Mẫu Java 17 hợp lệ trong một method:

```java
static String category(int code) {
    String result;

    switch (code) {
        case 1 -> result = "Basic";
        case 2 -> result = "Advanced";
        default -> result = "Unknown";
    }

    return result;
}
```

Mỗi nhánh đều gán `result`; `default` xử lý mọi giá trị còn lại, vì thế `return result` hợp lệ. Nếu bỏ `default` trong `switch statement` này, trình biên dịch không thể bảo đảm mọi giá trị `code` đều dẫn tới một phép gán.

Một lựa chọn ngắn và sáng rõ hơn là **switch expression**:

```java
static String category(int code) {
    return switch (code) {
        case 1 -> "Basic";
        case 2 -> "Advanced";
        default -> "Unknown";
    };
}
```

Trong ví dụ sau, `switch` trực tiếp tạo một giá trị trả về. Cả hai đoạn là **method để đặt trong lớp**, không có `main` riêng.

### 6.5. Phép toán trên biến cũng là hành vi đọc

```java
int count;
// count++;         // Lỗi: cần đọc count trước khi tăng.
// count += 2;      // Lỗi: cần đọc giá trị cũ trước khi cộng.
// System.out.println(count); // Lỗi: đọc trước khi gán.
count = 0;
count++;
System.out.println(count); // Hợp lệ: in 1.
```

`count++` và `count += 2` đều sử dụng giá trị hiện tại của biến. Một lệnh gán đơn giản như `count = 0` là phép ghi và không đòi hỏi đọc trước. Các dòng lỗi đã được comment để mảnh mã còn lại hợp lệ khi đặt trong method.

## 7. Ví dụ hoàn chỉnh về definite assignment với nhiều nhánh

Tạo tệp **`LocalAssignmentDemo.java`**:

```java
public class LocalAssignmentDemo {
    static String shipping(boolean express, int distance) {
        String label;
        int fee;

        if (express) {
            label = "Express";
            fee = 20;
        } else {
            label = "Standard";
            fee = 5;
        }

        int surcharge;
        if (distance > 100) {
            surcharge = 7;
        } else {
            surcharge = 0;
        }

        return label + ": " + (fee + surcharge);
    }

    public static void main(String[] args) {
        System.out.println(shipping(true, 120));
        System.out.println(shipping(false, 20));

        int quantity;
        quantity = 4;
        quantity += 1;
        System.out.println("quantity=" + quantity);
    }
}
```

Biên dịch, chạy:

```bash
javac LocalAssignmentDemo.java
java LocalAssignmentDemo
```

Output chính xác:

```text
Express: 27
Standard: 5
quantity=5
```

Ở thời điểm `return`, các biến `label`, `fee` và `surcharge` đều chắc chắn đã được gán trên mọi luồng điều khiển đến `return`. Hàm gọi bằng `true, 120` chọn phí `20` cộng phụ phí `7`; bằng `false, 20` chọn phí `5` cộng `0`. Biến `quantity` được gán `4` trước khi thực hiện `quantity += 1`.

**Bài học:** Việc không gán ngay trong dòng khai báo vẫn có thể đúng; yêu cầu của Java là **không đọc biến trước khi compiler chứng minh phép gán đã xảy ra**.

## 8. Trường `final` và biến cục bộ `final`: cùng bất biến gán một lần, khác cơ chế ban đầu

Từ khóa `final` giới hạn việc **gán lại biến**, nhưng không thay đổi nguyên tắc mặc định giữa field và local.

### 8.1. Blank final instance field

```java
class Member {
    private final String id; // Blank final field: chưa có initializer rõ ràng.

    Member(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
        this.id = id;
    }

    String getId() {
        return id;
    }
}
```

`id` vẫn có giá trị tham chiếu mặc định trong giai đoạn cấp phát, nhưng **mã nguồn phải bảo đảm definite assignment của blank final field** theo quy tắc Java trước khi constructor hoàn tất bình thường. Không thể dựa vào `null` mặc định để bỏ việc gán field `final` bắt buộc. Nếu thêm constructor khác, constructor ấy cũng phải bảo đảm `id` được gán hợp lệ, thường qua `this(...)`.

Một blank final instance field còn có thể được gán trong instance initializer; nhưng cần tuân theo quy tắc definite assignment và không được gán lại ở constructor. Ưu tiên khởi tạo tại nơi khai báo hoặc constructor khi điều đó giúp hiểu trạng thái rõ ràng.

### 8.2. Blank final static field

```java
class AppInfo {
    static final String VERSION;

    static {
        VERSION = "1.0";
    }
}
```

`VERSION` không có biểu thức khởi tạo trên dòng field, nhưng được gán một lần trong static initializer. Compiler yêu cầu blank final static field được definite assigned theo quy tắc khởi tạo tĩnh. Sau đó không thể gán lại `AppInfo.VERSION`.

### 8.3. Biến cục bộ `final`

```java
class FinalLocal {
    static int choose(boolean high) {
        final int limit;
        if (high) {
            limit = 100;
        } else {
            limit = 10;
        }
        return limit;
    }
}
```

Mỗi đường đi tới `return` gán `limit` **đúng một lần**, nên mã hợp lệ. Nếu đặt thêm `limit = 20;` sau `if/else` thì lỗi vì biến `final` đã chắc chắn được gán; Java không cho gán lại.

Một biến cục bộ **không `final`** có thể được gán nhiều lần, miễn được gán trước khi đọc. Trong lambda hoặc local/anonymous class, Java yêu cầu các biến cục bộ được bắt giữ phải là `final` hoặc *effectively final* (không bị gán lại sau gán ban đầu theo quy tắc). Đây là lý do một số biến local không thể bị thay đổi sau khi được sử dụng trong lambda, còn instance field có thể được thay đổi theo quy tắc truy cập.

`final` đối với **biến tham chiếu** chỉ cấm gán sang tham chiếu khác; nó không làm nội dung đối tượng được trỏ tới tự động bất biến.

## 9. Mảng: biến tham chiếu local và phần tử mảng là hai việc khác nhau

Tạo mảng bằng `new int[3]` cấp phát một đối tượng mảng và gán giá trị mặc định `0` cho **từng phần tử**. Với `String[]`, từng phần tử ban đầu là `null`. Điều này xảy ra dù biến giữ tham chiếu tới mảng là biến cục bộ hay field.

```java
import java.util.Arrays;

public class ArrayDefaultsDemo {
    public static void main(String[] args) {
        int[] scores = new int[3];
        String[] labels = new String[2];
        boolean[] flags = new boolean[2];

        System.out.println(Arrays.toString(scores));
        System.out.println(Arrays.toString(labels));
        System.out.println(Arrays.toString(flags));
    }
}
```

Lưu thành **`ArrayDefaultsDemo.java`**:

```bash
javac ArrayDefaultsDemo.java
java ArrayDefaultsDemo
```

```text
[0, 0, 0]
[null, null]
[false, false]
```

Ở đây, các biến cục bộ `scores`, `labels`, `flags` **đều đã được gán bằng biểu thức `new ...`** khi khai báo. Những phần tử trong mảng do Java tự đặt giá trị mặc định.

Ngược lại:

```java
class ArrayLocalProblem {
    static void example() {
        int[] scores;
        // System.out.println(scores[0]);
        // Nếu bỏ comment: lỗi biên dịch vì biến cục bộ scores chưa được gán.
    }
}
```

Sau khi gán `scores = new int[3];`, ta có thể đọc `scores[0]` là `0`. Nếu thay bằng `scores = null;`, biến local đã được gán (đáp ứng definite assignment) nhưng đọc `scores[0]` tại runtime sẽ ném `NullPointerException`. **Definite assignment không chứng minh tham chiếu khác `null`.**

Một ví dụ dễ nhầm khác:

```java
class ArrayHolder {
    int[] values; // Field reference có giá trị mặc định null.
}

class UseArrayHolder {
    static void check() {
        ArrayHolder holder = new ArrayHolder();
        System.out.println(holder.values == null); // true
    }
}
```

Field `values` là `null`, nghĩa là **chưa tồn tại mảng nào** cho field này. Chỉ sau khi thực hiện `holder.values = new int[3];` mới có phần tử mảng với giá trị `0`.

## 10. Che khuất tên field bằng biến cục bộ (*shadowing*)

Có thể khai báo biến cục bộ hoặc tham số cùng tên với field:

```java
class Player {
    private int score;     // Field: mặc định 0.

    void show() {
        int score = 10;    // Biến cục bộ: có giá trị do gán 10.
        System.out.println(score);
        System.out.println(this.score);
    }
}
```

Trong `show()`, tên đơn `score` trỏ đến biến cục bộ do quy tắc phân giải tên; `this.score` chỉ field của đối tượng. Nếu gọi `new Player().show()`, hai dòng lần lượt là `10` và `0`. Ví dụ là một khai báo lớp hợp lệ; muốn chạy cần đặt trong chương trình có `main`.

Việc field có giá trị mặc định **không giải cứu** một biến cục bộ cùng tên bị chưa khởi tạo:

```java
class ShadowProblem {
    int count;

    void print() {
        int count;
        // System.out.println(count);      // Lỗi: đọc local count chưa gán.
        System.out.println(this.count);    // Hợp lệ: đọc field -> 0.
    }
}
```

Compiler xem `count` trong lần gọi không có `this` là **local variable**, còn `this.count` là instance field. Quy tắc này giải thích nhiều trường hợp người mới nghĩ “mình đã có field int rồi, sao Java vẫn báo chưa khởi tạo?”.

Thực tế nên hạn chế che khuất tên gây nhầm lẫn. Trường hợp tham số constructor trùng field rất phổ biến và rõ ràng khi dùng `this`:

```java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }
}
```

`name` ở vế phải là tham số đã được gán khi lời gọi constructor bắt đầu; `this.name` ở vế trái là field.

## 11. Bài chạy tổng hợp: field mặc định, blank final field và local chắc chắn được gán

Tạo tệp **`AssignmentRulesDemo.java`**:

```java
class Enrollment {
    static final String CATEGORY;
    static int totalCreated;

    static {
        CATEGORY = "course";
    }

    final int id;
    int attempts;
    String nickname;
    boolean confirmed;

    Enrollment(boolean vip) {
        if (vip) {
            id = 9;
        } else {
            id = 4;
        }
        totalCreated++;
    }
}

public class AssignmentRulesDemo {
    public static void main(String[] args) {
        Enrollment first = new Enrollment(true);

        int selected;
        if (first.id > 5) {
            selected = 100;
        } else {
            selected = 200;
        }

        int[] slots = new int[2];

        System.out.println("attempts=" + first.attempts);
        System.out.println("nickname=" + first.nickname);
        System.out.println("confirmed=" + first.confirmed);
        System.out.println("id=" + first.id);
        System.out.println("selected=" + selected);
        System.out.println("category=" + Enrollment.CATEGORY);
        System.out.println("created=" + Enrollment.totalCreated);
        System.out.println("slot0=" + slots[0]);
    }
}
```

Chạy với JDK 17+:

```bash
javac AssignmentRulesDemo.java
java AssignmentRulesDemo
```

```text
attempts=0
nickname=null
confirmed=false
id=9
selected=100
category=course
created=1
slot0=0
```

Giải thích từng nhóm:

1. `attempts`, `nickname` và `confirmed` là instance field không khai báo initializer hay được gán trong constructor. Giá trị mặc định lần lượt là `0`, `null` và `false`.
2. `id` là **blank final instance field**. Hai nhánh `if/else` trong constructor bảo đảm gán đúng một lần: trường hợp `vip == true` cho `id == 9`.
3. `CATEGORY` là **blank final static field** được gán trong static initializer; đây là phép khởi tạo của lớp, không phải giá trị mặc định `null` cuối cùng.
4. `totalCreated` là static field mặc định `0`, sau đó constructor tăng lên `1`. Vì chỉ tạo một `Enrollment` nên dòng `created=1`.
5. `selected` là biến cục bộ chỉ được khai báo trước `if`. Cả hai nhánh đều gán, vì vậy in `selected=100` là hợp lệ.
6. `slots` là biến cục bộ **đã được gán** tham chiếu từ `new int[2]`, còn `slots[0]` là phần tử mảng tự được khởi tạo về `0`.

## 12. Những hiểu nhầm liên quan đến compiler và runtime

### 12.1. “Java tự gán 0 cho tất cả biến `int`”

Sai. Java bảo đảm `0` cho **field** kiểu `int` và **phần tử mảng** kiểu `int`. Một local `int number;` không tự có giá trị có thể đọc; compiler yêu cầu definite assignment trước lần đọc.

### 12.2. “Compiler biết điều kiện luôn đúng vì tôi biết trước dữ liệu”

Phân tích definite assignment có quy tắc cụ thể; compiler không suy luận toàn bộ ý nghĩa nghiệp vụ hay mọi điều kiện số học. Hãy tổ chức cấu trúc rõ ràng với `if/else`, một phép gán ban đầu hoặc `switch` đủ nhánh. Tránh dựa vào suy luận không hiển nhiên để mã khó đọc.

### 12.3. “Có giá trị mặc định thì object đã ở trạng thái hợp lệ”

Không nhất thiết. `String email == null` hoặc `int age == 0` có thể vi phạm invariant của mô hình. Nếu bắt buộc có email hoặc tuổi dương, hãy nhận tham số và kiểm tra trong constructor. Giá trị mặc định là cam kết kỹ thuật về trạng thái ban đầu, không thay thế ràng buộc nghiệp vụ.

### 12.4. “Biến local đã được gán `null` tức là an toàn”

Sai. Definite assignment chỉ kiểm tra **biến đã được gán**, không bảo đảm object tồn tại. `String s = null;` hợp lệ về definite assignment, nhưng `s.length()` vẫn ném `NullPointerException` lúc chạy.

### 12.5. “Field `final` không cần khởi tạo vì đã có mặc định”

Sai. Một blank final field chịu kiểm tra definite assignment nghiêm ngặt: phải được gán đúng quy tắc trước khi constructor/class initialization hoàn tất bình thường. Giá trị mặc định trong giai đoạn cấp phát không thay thế trách nhiệm khởi tạo của mã nguồn.

### 12.6. “Có mảng tức là mọi phần tử tham chiếu đã có object”

Sai. `new Customer[3]` tạo **một đối tượng mảng** với ba phần tử `null`; không gọi constructor `Customer`. Để dùng `customers[0].getName()` cần gán một instance `Customer` cho phần tử 0 trước.

### 12.7. “Khi đọc một field khác từ initializer luôn thấy giá trị cuối cùng”

Không luôn đúng. Field ban đầu nhận giá trị mặc định; explicit initializer chạy theo thứ tự được định nghĩa. Ví dụ các phương thức được gọi từ initializer có thể đọc trạng thái chưa hoàn tất, gây bug khó đoán. Tránh lạm dụng side effect và quan hệ phụ thuộc vòng tròn trong initializer.

### 12.8. “Biến `static` luôn là hằng số”

`static` nói field thuộc lớp; nó vẫn có thể thay đổi nếu không có ràng buộc khác. `final` cấm gán lại field sau khởi tạo đúng quy tắc, nhưng bản thân `final` trên một tham chiếu không làm object tham chiếu trở nên bất biến.

## 13. Checklist chẩn đoán lỗi “variable might not have been initialized”

Khi compiler báo lỗi với một biến, kiểm tra theo thứ tự:

1. **Xác định biến được đọc thực sự là loại nào.** Nó là local, tham số, field hay phần tử mảng? Có bị một tên local che khuất field không?
2. **Tìm lần đọc đầu tiên.** `println(x)`, `x++`, `x += 1`, `someMethod(x)` hoặc `return x` đều dùng giá trị của `x`.
3. **Liệt kê các nhánh có thể tới điểm đọc.** Có `if` không có `else`, `switch` chưa bao phủ hết, vòng lặp có thể không thực hiện, `break` hoặc `return` làm đổi đường đi không?
4. **Đảm bảo phép gán xảy ra trước mọi đường tới lần đọc.** Dùng initializer rõ ràng khi có một giá trị mặc định có nghĩa; dùng `if/else` hoặc `switch` nếu mỗi nhánh cần giá trị khác nhau.
5. **Nếu biến là `final`, kiểm tra cả việc gán lại.** Một local final phải được gán đúng một lần trên đường đi tương ứng; blank final field phải được khởi tạo theo những quy tắc riêng.
6. **Phân biệt compile error với runtime exception.** Biến local chưa definite assigned gây lỗi biên dịch; tham chiếu đã gán `null` nhưng bị gọi method gây lỗi runtime.

Ví dụ sửa ngắn gọn:

```java
// Trước: có thể lỗi biên dịch nếu đọc shippingFee ngoài if.
int shippingFee;
// if (express) shippingFee = 20;
// System.out.println(shippingFee);

// Sau: mọi nhánh đều gán.
if (express) {
    shippingFee = 20;
} else {
    shippingFee = 5;
}
System.out.println(shippingFee);
```

Mảnh mã này đặt trong một method đã có biến `express` kiểu `boolean`; những dòng lỗi ban đầu được comment. Cách sửa thể hiện **ý nghĩa của từng nhánh** mà không dùng phép gán tùy tiện che lỗi.

## 14. Tự kiểm tra và thực hành

**Câu 1.** Một lớp khai báo `boolean enabled;`, `char symbol;`, `String title;` mà không gán gì. Ba field có giá trị gì ngay sau khi object được khởi tạo và chưa thay đổi?

**Đáp án:** `false`, ký tự U+0000 (NUL), và `null`. Ký tự U+0000 không phải `'0'`.

**Câu 2.** Vì sao đoạn sau không biên dịch?

```java
void test(boolean condition) {
    int value;
    if (condition) {
        value = 7;
    }
    // System.out.println(value);
}
```

**Đáp án:** Nếu bỏ comment dòng `println`, có đường chạy với `condition == false` mà `value` không được gán. Sửa bằng `else` hoặc gán một giá trị khởi tạo trước `if`.

**Câu 3.** `int[] values = new int[2];` trong method có hợp lệ để in `values[1]` ngay sau khai báo không? Nếu có, kết quả là gì?

**Đáp án:** Hợp lệ. Biến local `values` đã được gán tham chiếu mảng; phần tử thứ hai được khởi tạo mặc định bằng `0`.

**Câu 4.** Với `String text = null;` trong method, compiler có chặn `text.length()` vì chưa được gán không?

**Đáp án:** Không: `text` đã được gán. Lời gọi `text.length()` sẽ thất bại ở runtime với `NullPointerException` nếu được thực thi.

**Câu 5.** Field `final int id;` có thể chỉ giữ giá trị mặc định `0` mà không gán rõ ràng trong constructor/initializer không?

**Đáp án:** Không. Blank final field phải được definite assigned trong quá trình khởi tạo phù hợp; `0` mặc định của bộ nhớ không thay thế nghĩa vụ biên dịch đó.

**Câu 6.** Nếu method khai báo `int x;` và chỉ gán `x = 4;` sau lệnh `x++;`, phần nào sai?

**Đáp án:** `x++` đọc giá trị cũ của `x` trước khi tăng; ở điểm đó `x` chưa được gán chắc chắn. Phải gán trước `x++`.

**Câu 7.** Một field `int level = 5;` và instance initializer tiếp theo là `{ level += 2; }`. Nếu constructor không sửa `level` thì giá trị sau khi khởi tạo là bao nhiêu?

**Đáp án:** `7`. Field có `0` trong giai đoạn mặc định, rồi được gán `5`, sau đó tăng thêm `2`.

**Câu 8.** Trong `AssignmentRulesDemo`, đổi `new Enrollment(true)` thành `new Enrollment(false)` thì những dòng nào thay đổi?

**Đáp án:** `id=9` thành `id=4`; `selected=100` thành `selected=200`. Các giá trị mặc định của field khác, category, số lần tạo object và giá trị phần tử mảng vẫn như cũ.

---

**Ghi nhớ:** Java cấp giá trị mặc định cho **instance field**, **static field** và **phần tử mảng**; **biến cục bộ** phải được definite assigned trước khi đọc. Phép gán `null` vẫn là một phép gán hợp lệ nhưng không bảo đảm an toàn khi truy cập đối tượng. Với `final`, cần bảo đảm biến/field được khởi tạo theo quy tắc và không bị gán lại. Khi chương trình có nhánh và vòng lặp, hãy kiểm tra từng đường đi tới vị trí đọc biến để phân biệt lỗi biên dịch với trạng thái dữ liệu khi chạy.