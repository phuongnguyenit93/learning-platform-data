# Khai báo phương thức, kiểu trả về và phạm vi truy cập trong Java

Phương thức (method) là thành phần mô tả một hành vi có thể được gọi trong chương trình Java. Một phương thức có thể nhận tham số, thực hiện xử lý, trả về kết quả hoặc chỉ thực hiện một hành động mà không trả về giá trị. Khi khai báo phương thức, cần xác định tên, kiểu trả về, danh sách tham số, phần thân và các modifier như `public`, `private` hoặc `static`.

Trong Java 27, phương thức thường được khai báo bên trong class, interface, enum hoặc record. Compact source file cũng cho phép viết method declaration ở cấp cao nhất của file; compiler xem các khai báo này là thành viên của class được khai báo ngầm. Những quy tắc dưới đây áp dụng cho Java hiện hành và không dựa vào cú pháp đã bị loại bỏ.

## 1. Cấu trúc khai báo phương thức

Một khai báo phương thức trong class có dạng tổng quát:

```java
[access-modifier] [other-modifiers] ReturnType methodName(
        ParameterList
) [throws ExceptionTypes] {
    // method body
}
```

Ví dụ:

```java
public static int calculateTotal(int price, int quantity) {
    return price * quantity;
}
```

Các thành phần:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Access modifier | `public` | Xác định nơi có thể truy cập phương thức |
| Modifier khác | `static` | Khai báo phương thức thuộc class |
| Kiểu trả về | `int` | Kiểu giá trị phương thức trả về |
| Tên phương thức | `calculateTotal` | Tên dùng khi gọi phương thức |
| Tham số | `int price, int quantity` | Dữ liệu đầu vào |
| Phần thân | `{ return ...; }` | Các câu lệnh được thực hiện khi gọi |
| Mệnh đề throws | `throws IOException` | Khai báo các exception có thể được ném ra |

Trong ví dụ trên, phương thức nhận hai tham số kiểu `int`, nhân chúng với nhau và trả về kết quả kiểu `int`.

Tên phương thức thường được đặt theo camelCase và nên diễn tả hành động, chẳng hạn `calculateTotal`, `findUserById`, `isEligible` hoặc `printReport`. Phương thức kiểm tra một điều kiện thường có tên bắt đầu bằng `is`, `has`, `can` hoặc `should`.

### 1.1. Phương thức được khai báo ở đâu?

Trong compilation unit thông thường, method declaration phải nằm trong một kiểu như class, interface, enum hoặc record. Ví dụ:

```java
public class Calculator {
    public int add(int first, int second) {
        return first + second;
    }
}
```

Một class có thể khai báo nhiều phương thức. Mỗi phương thức có thể có quyền truy cập, kiểu trả về, tham số và modifier riêng.

Từ Java 25, compact source file cho phép viết các khai báo method trực tiếp trong file mà không cần tự khai báo class:

```java
int add(int first, int second) {
    return first + second;
}

void main() {
    IO.println(add(10, 20));
}
```

Trong JDK 27, đây là tính năng ngôn ngữ chính thức. Compiler đặt các method và field ở cấp cao nhất này vào class được khai báo ngầm. Khi tổ chức ứng dụng nhiều class hoặc xây dựng API cần được kiểu khác tham chiếu, nên dùng các kiểu được khai báo tường minh.

## 2. Kiểu trả về của phương thức

Kiểu trả về (return type) cho biết kiểu giá trị mà phương thức cung cấp cho nơi gọi. Java cho phép kiểu trả về là kiểu nguyên thủy, kiểu tham chiếu hoặc `void`.

### 2.1. Phương thức trả về kiểu nguyên thủy

Phương thức có thể trả về `int`, `long`, `double`, `boolean`, `char` và các kiểu nguyên thủy khác:

```java
public class Temperature {
    public double toFahrenheit(double celsius) {
        return celsius * 9.0 / 5.0 + 32.0;
    }

    public boolean isFreezing(double celsius) {
        return celsius <= 0.0;
    }
}
```

Khi gọi phương thức, biểu thức gọi có kiểu trả về được khai báo:

```java
Temperature temperature = new Temperature();

double fahrenheit = temperature.toFahrenheit(25.0);
boolean freezing = temperature.isFreezing(-2.0);
```

Biến nhận kết quả phải tương thích với kiểu trả về. Java có thể áp dụng các chuyển kiểu được phép trong ngữ cảnh gán, nhưng không tự động cho phép mọi chuyển đổi thu hẹp.

### 2.2. Phương thức trả về kiểu tham chiếu

Phương thức cũng có thể trả về một đối tượng, mảng, interface hoặc kiểu tham chiếu khác:

```java
public class UserService {
    public String normalizeName(String name) {
        return name == null ? "" : name.trim();
    }

    public int[] createScores() {
        return new int[] { 85, 90, 96 };
    }
}
```

Kiểu trả về có thể là một interface, giúp phương thức giảm phụ thuộc vào cách triển khai cụ thể:

```java
import java.util.List;

public class CourseService {
    public List<String> getCourseNames() {
        return List.of("Java", "SQL", "HTTP");
    }
}
```

Phương thức trả về một tham chiếu có thể trả về `null` nếu hợp đồng của phương thức cho phép. Tuy nhiên, cần xác định rõ ý nghĩa của `null`; với API hiện đại, có thể cân nhắc `Optional<T>` khi muốn biểu đạt rõ một kết quả có thể không tồn tại.

### 2.3. Phương thức `void`

`void` cho biết phương thức không cung cấp giá trị kết quả cho nơi gọi. Phương thức loại này thường thực hiện hành động như in thông tin, cập nhật trạng thái hoặc ghi dữ liệu:

```java
public class MessagePrinter {
    public void printWelcome(String name) {
        System.out.println("Welcome, " + name + "!");
    }
}
```

Trong phương thức `void`, có thể dùng `return;` để kết thúc sớm:

```java
public void printName(String name) {
    if (name == null || name.isBlank()) {
        return;
    }

    System.out.println(name);
}
```

Không được viết `return expression;` trong phương thức `void`. Ngược lại, phương thức có kiểu trả về khác `void` phải trả về một giá trị tương thích trên mọi đường thực thi có thể kết thúc bình thường.

### 2.4. Câu lệnh return

Câu lệnh `return` kết thúc lần gọi phương thức hiện tại. Nếu phương thức có kiểu trả về, biểu thức sau `return` phải tương thích với kiểu đó:

```java
public int max(int first, int second) {
    if (first > second) {
        return first;
    }

    return second;
}
```

Nếu mọi nhánh đều không trả về giá trị, compiler báo lỗi:

```java
// Không hợp lệ: có đường thực thi đi đến cuối phương thức.
public int classify(int value) {
    if (value > 0) {
        return 1;
    }
}
```

Có thể sửa bằng cách xử lý đầy đủ trường hợp còn lại:

```java
public int classify(int value) {
    if (value > 0) {
        return 1;
    }

    return 0;
}
```

Với kiểu trả về tham chiếu, giá trị trả về phải có thể chuyển đổi sang kiểu đã khai báo. Ví dụ, phương thức khai báo trả về `Number` có thể trả về một đối tượng `Integer`, vì `Integer` là lớp con của `Number`.

### 2.5. Kiểu trả về không thuộc chữ ký phương thức

Kiểu trả về là một phần của khai báo phương thức nhưng không được dùng một mình để phân biệt các overload. Hai phương thức không thể chỉ khác nhau ở kiểu trả về:

```java
// Không hợp lệ: cùng tên và cùng danh sách tham số.
int calculate(int value) {
    return value;
}

// double calculate(int value) {
//     return value;
// }
```

Khi cần cung cấp kết quả khác nhau, hãy đổi danh sách tham số hoặc đặt tên phương thức khác.

## 3. Tham số và đối số

Tham số (parameter) là biến được khai báo trong danh sách tham số của phương thức. Đối số (argument) là giá trị hoặc biểu thức được truyền vào khi gọi phương thức.

```java
public int multiply(int number, int factor) { // number và factor là tham số
    return number * factor;
}

int result = multiply(6, 7); // 6 và 7 là đối số
```

### 3.1. Tham số bắt buộc và nhiều tham số

Một phương thức có thể không có tham số hoặc có một hay nhiều tham số:

```java
public void reset() {
    // Không nhận đầu vào.
}

public double calculateArea(double width, double height) {
    return width * height;
}
```

Khi gọi phương thức có tham số, số lượng và kiểu đối số phải phù hợp với một cách gọi hợp lệ. Thứ tự đối số tương ứng với thứ tự tham số.

Java không có cú pháp khai báo giá trị mặc định cho tham số như một số ngôn ngữ khác. Nếu cần nhiều cách gọi, có thể dùng overload hoặc tự xử lý giá trị tùy chọn trong thân phương thức.

### 3.2. Truyền tham số theo giá trị

Java luôn truyền đối số theo giá trị (pass-by-value). Với kiểu nguyên thủy, giá trị được sao chép vào tham số. Với kiểu tham chiếu, giá trị tham chiếu được sao chép; tham số và biến bên ngoài có thể cùng tham chiếu một đối tượng, nhưng việc gán lại tham số không làm biến bên ngoài trỏ sang đối tượng mới.

Ví dụ với kiểu nguyên thủy:

```java
public class ParameterDemo {
    static void changeNumber(int value) {
        value = 100;
    }

    public static void main(String[] args) {
        int number = 10;
        changeNumber(number);
        System.out.println(number); // 10
    }
}
```

Ví dụ với tham chiếu:

```java
import java.util.ArrayList;
import java.util.List;

public class ParameterDemo {
    static void addItem(List<String> items) {
        items.add("Java"); // thay đổi đối tượng được tham chiếu
    }

    static void replaceList(List<String> items) {
        items = new ArrayList<>(); // chỉ gán lại bản sao tham chiếu
        items.add("SQL");
    }

    public static void main(String[] args) {
        List<String> languages = new ArrayList<>();
        addItem(languages);
        replaceList(languages);

        System.out.println(languages); // [Java]
    }
}
```

Phương thức `addItem` thay đổi đối tượng chung nên thay đổi được nhìn thấy ở nơi gọi. `replaceList` chỉ gán lại biến tham số cục bộ, vì vậy biến `languages` vẫn tham chiếu danh sách ban đầu.

### 3.3. Tham số final

Có thể khai báo tham số với modifier `final`. Khi đó, không thể gán lại biến tham số trong thân phương thức:

```java
public int addTax(final int price, final int tax) {
    // price = 100; // lỗi: price là final
    return price + tax;
}
```

Với tham số tham chiếu `final`, không thể gán tham số sang một đối tượng khác, nhưng vẫn có thể thay đổi trạng thái của đối tượng nếu kiểu đối tượng cho phép.

### 3.4. Tham số biến độ dài (varargs)

Varargs cho phép truyền số lượng đối số thay đổi cho tham số cuối cùng. Cú pháp dùng dấu ba chấm sau kiểu:

```java
public int sum(int... numbers) {
    int total = 0;

    for (int number : numbers) {
        total += number;
    }

    return total;
}
```

Có thể gọi với không, một hoặc nhiều đối số:

```java
int empty = sum();
int one = sum(5);
int many = sum(1, 2, 3, 4);
```

Bên trong phương thức, tham số varargs được xử lý như một mảng. Mỗi khai báo phương thức chỉ có tối đa một tham số varargs và tham số này phải đứng cuối danh sách tham số:

```java
public void log(String category, String... messages) {
    for (String message : messages) {
        System.out.println("[" + category + "] " + message);
    }
}
```

Khi gọi một overload có tham số varargs, Java ưu tiên các cách phân giải overload phù hợp không cần dùng varargs trước. Vì vậy, nhiều overload có thể làm lời gọi trở nên khó hiểu hoặc mơ hồ; hãy thiết kế danh sách tham số rõ ràng.

## 4. Modifier truy cập và phạm vi truy cập

Access modifier quyết định mã nguồn ở vị trí nào có thể truy cập một phương thức. Java có bốn mức truy cập: `public`, `protected`, package-private (không ghi modifier) và `private`.

| Modifier | Trong class khai báo | Class khác cùng package | Subclass ở package khác | Class không liên quan ở package khác |
|---|---|---|---|---|
| `public` | Có | Có | Có | Có, nếu kiểu và package được phép truy cập |
| `protected` | Có | Có | Có, theo quy tắc protected | Không |
| Package-private | Có | Có | Không | Không |
| `private` | Có | Không | Không | Không |

Quyền truy cập thực tế còn phụ thuộc vào khả năng truy cập của kiểu bao ngoài và ranh giới module. Ví dụ, một phương thức `public` trong một package không được module export vẫn không thể được module khác sử dụng như API công khai.

### 4.1. public

`public` cho phép mã nguồn có quyền truy cập đến kiểu chứa phương thức gọi phương thức đó, miễn là các quy tắc package và module cũng được đáp ứng:

```java
package com.example.service;

public class UserService {
    public String getDisplayName() {
        return "Guest";
    }
}
```

Một class ở package khác có thể gọi phương thức này nếu class `UserService` và package chứa nó được phép truy cập.

### 4.2. private

`private` giới hạn truy cập vào phạm vi kiểu khai báo và các kiểu lồng trong cùng top-level nest theo quy tắc truy cập của Java. Đây là cách đóng gói logic nội bộ:

```java
public class BankAccount {
    private long balance;

    public void deposit(long amount) {
        if (amount > 0) {
            balance += amount;
        }
    }

    public long getBalance() {
        return balance;
    }
}
```

Mã bên ngoài không thể truy cập trực tiếp `balance`, nhưng có thể tương tác thông qua các phương thức được cung cấp. Các thành viên khác trong cùng class có thể truy cập thành viên private; Java cũng cho phép các instance của cùng class truy cập private member của nhau.

### 4.3. Package-private

Nếu không ghi access modifier, phương thức có quyền truy cập package-private. Chỉ mã trong cùng package mới truy cập được phương thức này (ngoài class khai báo):

```java
package com.example.internal;

class CacheStore {
    void clearExpiredEntries() {
        // Chỉ dùng bên trong package.
    }
}
```

Package-private phù hợp với các phương thức hỗ trợ nội bộ mà các class trong cùng package cần dùng, nhưng không muốn công bố ra API bên ngoài.

### 4.4. protected

`protected` cho phép truy cập từ class khai báo, các class cùng package và các subclass theo quy tắc của Java. Khi subclass nằm ở package khác, quyền truy cập protected có giới hạn theo ngữ cảnh subclass; không thể xem nó như quyền truy cập công khai với mọi đối tượng.

```java
package com.example.base;

public class Vehicle {
    protected void startEngine() {
        System.out.println("Engine started");
    }
}
```

```java
package com.example.car;

import com.example.base.Vehicle;

public class Car extends Vehicle {
    public void start() {
        startEngine(); // truy cập protected qua kế thừa
    }
}
```

Hãy dùng `protected` khi một phương thức là điểm mở rộng dành cho subclass hoặc là thành phần cần chia sẻ trong package. Tránh dùng nó chỉ vì muốn cho phép mọi class khác truy cập.

## 5. Phạm vi (scope) và khả năng truy cập (accessibility)

Scope và access modifier có liên quan nhưng không đồng nghĩa:

- **Scope** xác định vùng mã nguồn mà một tên được khai báo có thể được sử dụng.
- **Accessibility** xác định một khai báo có thể được truy cập từ vị trí mã nguồn hiện tại theo quy tắc thành viên, package và module hay không.

Tên phương thức là thành viên của kiểu khai báo nó. Một lời gọi có thể dùng tên đơn giản trong ngữ cảnh phù hợp hoặc dùng qua đối tượng/tên class:

```java
class Formatter {
    String trim(String text) {
        return text.strip();
    }

    String format(String text) {
        return trim(text); // gọi phương thức cùng instance
    }
}
```

Với phương thức instance, lời gọi không ghi receiver thường tương đương gọi trên `this` trong ngữ cảnh instance. Với phương thức static, có thể gọi qua tên class:

```java
class NumberTools {
    static int square(int value) {
        return value * value;
    }
}

int result = NumberTools.square(5);
```

### 5.1. Phạm vi của tham số và biến cục bộ

Tham số có phạm vi trong thân phương thức. Biến cục bộ có phạm vi từ vị trí khai báo đến hết block chứa nó:

```java
public int calculate(int input) {
    int result = input * 2;

    if (result > 10) {
        int bonus = 5;
        result += bonus;
    }

    // bonus không còn trong scope ở đây
    return result;
}
```

Biến cục bộ phải được gán chắc chắn trước khi đọc. Khác với field, biến cục bộ không tự nhận giá trị mặc định:

```java
public int invalidExample() {
    int result;
    // return result; // lỗi: result chưa được gán chắc chắn
    result = 0;
    return result;
}
```

### 5.2. Static và instance method

Phương thức instance được gọi trên một đối tượng và có thể truy cập trạng thái instance thông qua `this`. Phương thức static thuộc class và không có `this`:

```java
public class Counter {
    private int value;
    private static int createdCount;

    public Counter() {
        createdCount++;
    }

    public void increment() {
        value++;
    }

    public int getValue() {
        return value;
    }

    public static int getCreatedCount() {
        return createdCount;
    }
}
```

Sử dụng:

```java
Counter first = new Counter();
first.increment();

System.out.println(first.getValue());
System.out.println(Counter.getCreatedCount());
```

Một static method không thể truy cập trực tiếp field hoặc method instance khi không có đối tượng. Nếu cần dùng trạng thái instance, hãy nhận đối tượng qua tham số hoặc gọi phương thức instance trên một đối tượng cụ thể.

## 6. Modifier khác của phương thức

Ngoài access modifier, method declaration có thể có modifier khác để xác định cách sử dụng.

| Modifier | Ý nghĩa |
|---|---|
| `static` | Phương thức thuộc class, không có `this` |
| `final` | Subclass không thể override phương thức đó |
| `abstract` | Khai báo phương thức chưa có phần thân; kiểu chứa phải cho phép phương thức abstract |
| `synchronized` | Thực thi phương thức theo cơ chế khóa monitor của đối tượng hoặc class |
| `default` | Khai báo phương thức có phần thân trong interface |
| `private` trong interface | Phương thức hỗ trợ nội bộ cho các method khác trong interface |

Không phải mọi modifier đều có thể kết hợp tùy ý. Ví dụ, phương thức không thể vừa `abstract` vừa `final`, vì một bên yêu cầu subclass cung cấp phần triển khai còn bên kia cấm override. Phương thức `abstract` cũng không có phần thân thực thi.

### 6.1. Abstract method

Abstract method chỉ khai báo chữ ký, kết thúc bằng dấu chấm phẩy. Class thông thường chứa abstract method phải được khai báo là abstract; interface cũng có thể khai báo abstract method. Enum có quy tắc riêng: nếu enum khai báo abstract method, mỗi enum constant phải cung cấp phần triển khai trong constant-specific class body.

```java
abstract class Shape {
    public abstract double area();

    public void printArea() {
        System.out.println(area());
    }
}
```

Class cụ thể kế thừa `Shape` phải triển khai các abstract method còn thiếu:

```java
class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
}
```

### 6.2. Method trong interface

Interface có thể khai báo abstract method, default method, static method và private method:

```java
interface Auditable {
    void audit(); // public abstract ngầm định

    default void auditWithMessage(String message) {
        System.out.println(message);
        audit();
        writeInternalLog();
    }

    static boolean isValidId(long id) {
        return id > 0;
    }

    private void writeInternalLog() {
        System.out.println("Audit operation");
    }
}
```

Các method không có body trong interface mặc định là `public abstract`. Default method có body và được instance của class triển khai kế thừa. Static method được gọi qua tên interface; private method chỉ phục vụ logic bên trong interface.

### 6.3. Final method và override

Một final method không thể bị override trong subclass:

```java
class BaseService {
    public final void validateRequest() {
        System.out.println("Common validation");
    }
}
```

Khi override một method kế thừa, phương thức mới không được giảm mức truy cập của phương thức gốc. Annotation `@Override` giúp compiler kiểm tra rằng method thực sự override một method có thể override:

```java
class Parent {
    public Number getValue() {
        return 10;
    }
}

class Child extends Parent {
    @Override
    public Integer getValue() {
        return 20;
    }
}
```

Ví dụ này dùng kiểu trả về hiệp biến (covariant return type): phương thức override có thể trả về một kiểu tham chiếu con của kiểu trả về được khai báo ở phương thức gốc.

## 7. Nạp chồng phương thức (method overloading)

Overloading cho phép khai báo nhiều phương thức cùng tên trong cùng kiểu, miễn là danh sách tham số khác nhau về số lượng, kiểu hoặc thứ tự kiểu tham số:

```java
public class Converter {
    public String toText(int value) {
        return Integer.toString(value);
    }

    public String toText(double value) {
        return Double.toString(value);
    }

    public String toText(boolean value) {
        return Boolean.toString(value);
    }

    public String toText(int value, int radix) {
        return Integer.toString(value, radix);
    }
}
```

Lời gọi được compiler chọn dựa trên tên phương thức và các kiểu đối số tại thời điểm biên dịch. Đây là overload resolution.

Các quy tắc quan trọng:

- Có thể khác nhau về số lượng tham số.
- Có thể khác nhau về kiểu tham số.
- Có thể khác nhau về thứ tự kiểu tham số.
- Chỉ đổi tên biến tham số không tạo overload mới.
- Chỉ đổi kiểu trả về không tạo overload mới.
- Thêm hoặc bỏ modifier truy cập/static cũng không tạo overload mới.

Ví dụ không hợp lệ:

```java
class InvalidOverload {
    int find(int id) {
        return id;
    }

    // Không hợp lệ: chỉ khác kiểu trả về.
    // long find(int id) {
    //     return id;
    // }
}
```

Tránh thiết kế các overload khiến một lời gọi có thể phù hợp với nhiều phương thức ngang nhau. Ví dụ, lời gọi truyền `null` có thể mơ hồ nếu có overload nhận hai kiểu tham chiếu không liên quan:

```java
void print(String value) { }
void print(Integer value) { }

// print(null); // lỗi: lời gọi mơ hồ
```

Có thể giải quyết bằng cách ép kiểu rõ ràng hoặc thiết kế API với tên/phân nhóm tham số khác.

## 8. Mệnh đề throws và exception

Phương thức có thể khai báo các checked exception mà nó có thể ném ra bằng mệnh đề `throws`. Điều này thông báo cho nơi gọi rằng cần xử lý hoặc tiếp tục khai báo exception đó:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileReaderService {
    public String readText(Path path) throws IOException {
        return Files.readString(path);
    }
}
```

Nơi gọi có thể dùng `try-catch`:

```java
try {
    String content = new FileReaderService().readText(Path.of("notes.txt"));
    System.out.println(content);
} catch (IOException exception) {
    System.err.println("Cannot read file: " + exception.getMessage());
}
```

Mệnh đề `throws` không phải kiểu trả về và không thuộc chữ ký dùng để phân biệt overload. Các unchecked exception như `RuntimeException` không bắt buộc phải khai báo trong `throws`.

## 9. Chữ ký phương thức và phân biệt với constructor

Chữ ký (method signature) được dùng trong các quy tắc overload và override. Về cơ bản, chữ ký gồm tên phương thức và các kiểu tham số hình thức, có xét đến các quy tắc kiểu tổng quát của Java.

Chữ ký không bao gồm:

- Kiểu trả về.
- Tên biến tham số.
- Modifier truy cập.
- Modifier `static`, `final` hoặc `synchronized`.
- Mệnh đề `throws`.

Constructor không phải method. Constructor có tên gắn với class, không khai báo kiểu trả về và được gọi khi tạo đối tượng bằng `new`. Ví dụ:

```java
class Product {
    private final String name;

    Product(String name) { // constructor
        this.name = name;
    }

    public String getName() { // method
        return name;
    }
}
```

Không viết `void Product(...)` nếu muốn khai báo constructor; cú pháp đó sẽ khai báo một method có tên `Product` và kiểu trả về `void`.

## 10. Thiết kế phương thức dễ sử dụng và bảo trì

Một phương thức tốt nên có trách nhiệm rõ ràng, tên dễ hiểu và danh sách tham số vừa đủ. Một số nguyên tắc thực tế:

- Dùng động từ mô tả hành động: `calculatePrice`, `sendNotification`, `findById`.
- Chọn kiểu trả về thể hiện đúng kết quả; dùng `void` khi chỉ cần thực hiện hành động.
- Giữ mức truy cập hẹp nhất đáp ứng nhu cầu sử dụng. Chỉ công khai method khi nó thực sự thuộc API cần cung cấp.
- Tách xử lý phức tạp thành các method nhỏ có tên rõ nghĩa.
- Tránh method có quá nhiều tham số; cân nhắc gom các dữ liệu liên quan vào một kiểu phù hợp.
- Tránh thay đổi trạng thái ngoài ý muốn; mô tả rõ tác dụng phụ nếu phương thức cập nhật dữ liệu.
- Dùng `@Override` khi override method để compiler hỗ trợ phát hiện lỗi.
- Tránh overload mơ hồ hoặc các method có ý nghĩa gần giống nhưng quy tắc tham số khó đoán.

Ví dụ một class có API công khai nhỏ và các bước xử lý nội bộ:

```java
public class OrderService {
    public double calculateFinalPrice(double price, double discountRate) {
        validateInputs(price, discountRate);

        double discount = calculateDiscount(price, discountRate);
        return price - discount;
    }

    private void validateInputs(double price, double discountRate) {
        if (price < 0 || discountRate < 0 || discountRate > 1) {
            throw new IllegalArgumentException("Invalid price or discount rate");
        }
    }

    private double calculateDiscount(double price, double discountRate) {
        return price * discountRate;
    }
}
```

Nơi sử dụng chỉ cần biết cách gọi `calculateFinalPrice`. Các bước kiểm tra và tính chiết khấu được đóng gói trong các method private.

## 11. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Thiếu `return` | Method có kiểu trả về nhưng một đường thực thi kết thúc bình thường mà không trả kết quả | Bổ sung return tương thích cho mọi nhánh |
| Trả về sai kiểu | Biểu thức sau return không chuyển được sang kiểu trả về | Chọn kiểu phù hợp hoặc chuyển đổi rõ ràng |
| Dùng `return value;` trong method `void` | `void` không có giá trị kết quả | Dùng `return;` hoặc bỏ return nếu chạy đến cuối |
| Gọi private method từ class khác | Phạm vi truy cập bị giới hạn trong kiểu khai báo | Cung cấp method public/protected phù hợp nếu đó là API cần thiết |
| Gọi instance method từ static context mà không có đối tượng | Static method không có `this` | Tạo/nhận đối tượng rồi gọi method trên đối tượng |
| Nghĩ Java truyền object theo tham chiếu | Tham số nhận bản sao của giá trị tham chiếu | Hiểu rằng Java luôn pass-by-value |
| Tạo overload chỉ khác kiểu trả về | Kiểu trả về không phân biệt chữ ký overload | Thay đổi danh sách tham số hoặc tên method |
| Dùng varargs ở giữa danh sách | Varargs phải là tham số cuối cùng | Chuyển varargs về cuối danh sách |
| Override làm giảm quyền truy cập | Quy tắc override không cho thu hẹp mức truy cập | Giữ mức truy cập bằng hoặc rộng hơn |
| Nhầm constructor là method | Constructor không có kiểu trả về | Phân biệt cú pháp constructor và method |

## 12. Bài tập thực hành

### Bài 1: Khai báo phương thức tính diện tích

Tạo class `Rectangle` với method `calculateArea` nhận chiều rộng và chiều cao kiểu `double`, trả về diện tích. Nếu một trong hai kích thước âm, hãy xử lý bằng cách ném `IllegalArgumentException`.

### Bài 2: Phân biệt void và kiểu trả về

Viết hai method:

- `printSummary(String name, int score)` in thông tin ra màn hình và có kiểu trả về `void`.
- `isPassed(int score)` trả về `boolean` dựa trên ngưỡng điểm do bạn chọn.

### Bài 3: Kiểm soát truy cập

Tạo class `Account` có field `balance` là private, method `deposit` là public và method `validateAmount` là private. Giải thích vì sao mã bên ngoài không thể gọi trực tiếp `validateAmount`.

### Bài 4: Overloading

Tạo class `MessageFormatter` có ba overload tên `format`: nhận một `String`, nhận một `String` và một `int`, nhận một tham số varargs `String...`. Thử các lời gọi khác nhau và giải thích overload nào được chọn.

### Bài 5: Pass-by-value

Viết method nhận một biến `int` và một `List<String>`. Thử thay đổi giá trị tham số nguyên, thêm phần tử vào danh sách và gán lại tham số danh sách. Quan sát sự khác nhau ở nơi gọi.

## 13. Tóm tắt

Khai báo phương thức xác định tên, kiểu trả về, tham số, phần thân và các modifier. Kiểu trả về có thể là kiểu nguyên thủy, kiểu tham chiếu hoặc `void`; method có kiểu trả về phải cung cấp giá trị tương thích trên mọi đường thực thi bình thường. Tham số nhận đối số theo cơ chế pass-by-value; varargs cho phép nhận số lượng đối số thay đổi và phải nằm cuối danh sách tham số.

Bốn mức truy cập của Java là `public`, `protected`, package-private và `private`. Scope xác định vùng mã nguồn mà tên được khai báo có thể được dùng, còn accessibility xác định mã ở vị trí đó có được phép truy cập thành viên hay không. Modifier `static`, `final`, `abstract` và các modifier liên quan điều chỉnh cách method hoạt động.

Overloading phân biệt phương thức bằng danh sách tham số, không phải kiểu trả về. Constructor là thành phần riêng để khởi tạo đối tượng, không phải method. Khi thiết kế API, hãy chọn tên rõ nghĩa, kiểu trả về chính xác và phạm vi truy cập hẹp nhất đáp ứng nhu cầu.

## Tài liệu tham khảo

- [Java Language Specification, Java SE 27 — §8.4 Method Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4)
- [Java Language Specification, Java SE 27 — §8.4.2 Method Signature](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4.2)
- [Java Language Specification, Java SE 27 — §6.6 Access Control](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-6.html#jls-6.6)
- [Java Language Specification, Java SE 27 — §14.17 The return Statement](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-14.html#jls-14.17)
- [JEP 512: Compact Source Files and Instance Main Methods](https://openjdk.org/jeps/512)
