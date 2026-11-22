# Phân biệt trường, tham số và biến cục bộ trong Java

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận biết đúng **trường (field)**, **tham số (parameter)** và **biến cục bộ (local variable)** khi đọc một lớp Java.
- Phân biệt nơi khai báo, phạm vi nhìn thấy (*scope*), thời điểm nhận giá trị, trạng thái được lưu trữ và khả năng truy cập của từng loại.
- Hiểu sự khác nhau giữa **instance field** và **static field**, giữa giá trị mặc định của field và quy tắc *definite assignment* của biến cục bộ.
- Phân biệt trường của đối tượng với tham số/biến cục bộ trùng tên bằng `this` và tên lớp.
- Giải thích chính xác cơ chế **truyền tham số theo giá trị** của Java đối với kiểu nguyên thủy và kiểu tham chiếu.
- Sử dụng `final`, biến *effectively final* và `var` đúng ngữ cảnh, tránh các nhầm lẫn khi viết constructor, phương thức và lambda.

## 1. Ba loại biến thường gặp trong lớp Java

Xem lớp đơn giản dưới đây:

~~~java
public class Product {
    private String name;       // Trường thực thể (instance field)
    private int quantity;       // Trường thực thể
    private static int created; // Trường lớp (static field)

    public Product(String name, int quantity) { // Hai tham số constructor
        this.name = name;
        this.quantity = quantity;
        created++;
    }

    public void add(int amount) { // amount là tham số phương thức
        int oldQuantity = quantity; // Biến cục bộ
        quantity += amount;
        System.out.println(oldQuantity + " -> " + quantity);
    }
}
~~~

Đây là **một lớp hoàn chỉnh có thể biên dịch**, nhưng không có `main`; ví dụ chương trình chạy độc lập sẽ xuất hiện ở phần sau.

- **Field**: `name`, `quantity` và `created` được khai báo trực tiếp trong thân lớp, ở ngoài các method/constructor. Hai field đầu thuộc từng đối tượng; `created` thuộc lớp vì có `static`.
- **Parameter**: `name`, `quantity` trong constructor và `amount` trong `add`. Khi gọi constructor/method, đối số (*argument*) cung cấp giá trị cho tham số hình thức tương ứng.
- **Local variable**: `oldQuantity` được khai báo trong phần thân `add`, dùng để lưu số lượng trước khi cập nhật trong lần gọi đó.

Chữ `quantity` trong cùng một chương trình có thể là **trường** hoặc **tham số**, tùy nơi khai báo và cách tham chiếu. Kiểu dữ liệu không quyết định loại biến: cả field, parameter và local variable đều có thể mang kiểu `int`, `String`, mảng hoặc kiểu tham chiếu khác.

### 1.1. Bảng so sánh cốt lõi

| Tiêu chí | Field | Parameter | Local variable |
| --- | --- | --- | --- |
| Nơi khai báo | Trực tiếp trong class hoặc kiểu có field, ngoài method/constructor | Trong danh sách tham số của constructor/method, lambda, hoặc ngữ cảnh tham số tương ứng | Trong thân method/constructor, block, một số cấu trúc như vòng lặp |
| Thuộc về | Đối tượng nếu không `static`; lớp nếu có `static` | Một lần gọi hoặc lần thực thi cấu trúc nhận tham số | Một lần thực thi phạm vi khai báo |
| Giá trị khi bắt đầu | Có giá trị mặc định; initializer/constructor có thể thay đổi | Được gán từ argument khi lời gọi bắt đầu | Phải được gán chắc chắn trước khi đọc; không có giá trị mặc định để đọc |
| Phạm vi sử dụng | Theo quy tắc tên, truy cập và static/instance của lớp | Phạm vi do khai báo tham số quy định, thường là thân method/constructor | Từ điểm khai báo trong phạm vi của block/cấu trúc tương ứng |
| Modifier thường gặp | `private`, `public`, `protected`, `static`, `final`, ... | Có thể dùng `final`; không khai báo `private` hay `static` cho tham số method | Có thể dùng `final`; `var` hỗ trợ suy luận kiểu local ở ngữ cảnh hợp lệ |
| Ví dụ | `private int balance;` | `deposit(int amount)` | `int fee = 2;` |
| Truy cập qua `this` | Có thể dùng `this.field` cho instance field | Không có `this.parameter`; tham số là tên biến riêng | Không có `this.local`; local là tên biến riêng |

**Lưu ý thuật ngữ:** Ở mức đặc tả Java, tham số là một loại biến riêng có quy tắc scope/khởi tạo của nó; trong cách nói hằng ngày, đôi khi người ta gọi cả tham số là “biến cục bộ”. Khi phân tích chương trình, nên tách rõ ba nhóm để không nhầm nhiệm vụ của chúng.

## 2. Field: trạng thái của đối tượng hoặc lớp

Một **instance field** biểu diễn một phần trạng thái của từng đối tượng. Với hai đối tượng khác nhau, mỗi đối tượng có field cùng tên nhưng **vị trí trạng thái riêng**:

~~~java
class Counter {
    int value;

    void increment() {
        value++;
    }
}
~~~

Đây là đoạn khai báo class dùng được trong tệp Java thích hợp, chưa có `main`. Nếu tạo `Counter first = new Counter();` và `Counter second = new Counter();`, sau khi gọi `first.increment()`, giá trị `first.value` là `1`, còn `second.value` vẫn `0`.

Ngược lại, **static field** được gắn với lớp:

~~~java
class Counter {
    static int totalCreated;
    int value;

    Counter() {
        totalCreated++;
    }
}
~~~

Hai lần tạo `new Counter()` tăng cùng một `Counter.totalCreated`. `static` không có nghĩa field tự an toàn trong đa luồng: `totalCreated++` gồm nhiều thao tác và không được bảo đảm nguyên tử khi nhiều luồng cùng ghi.

### 2.1. Field có giá trị mặc định, khác parameter và local

Các field `int` chưa gán tường minh ban đầu là `0`; `boolean` là `false`; field kiểu tham chiếu như `String` là `null` (nhóm primitive khác nhận mặc định tương ứng với kiểu). Điều này đúng với instance và static field trước các initializers phù hợp. **Parameter** nhận giá trị từ argument lúc gọi, còn **local variable** không được đọc trước khi chắc chắn đã gán theo quy tắc *definite assignment*.

Trong phần phân loại ba loại biến này, điều quan trọng hơn việc lặp nguyên bảng mặc định là: **field thuộc object/class, parameter thuộc lời gọi, còn local thuộc phạm vi thực thi**. Chúng khác cả nơi khai báo lẫn thời điểm nhận giá trị; các ví dụ tiếp theo làm rõ từng nhóm.

### 2.2. Truy cập và tính đóng gói

Đối với dữ liệu trạng thái, field thường được khai báo `private` rồi thay đổi qua phương thức để bảo vệ các điều kiện hợp lệ:

~~~java
class Wallet {
    private int balance;

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance += amount;
    }

    int balance() {
        return balance;
    }
}
~~~

Đoạn này là khai báo lớp minh họa không có `main`. `balance` là field; `amount` là parameter. Khai báo `private` ảnh hưởng **khả năng truy cập field từ mã khác**, không biến nó thành local variable.

## 3. Parameter: tên nhận giá trị từ lời gọi

Parameter được viết trong danh sách tham số khi **khai báo** method hoặc constructor. Khi **gọi** method/constructor, ta truyền *argument* vào.

Ví dụ:

~~~java
void rename(String newName) {
    this.name = newName;
}
~~~

Đây là method minh họa trong một lớp có instance field `name`. `String newName` là **khai báo tham số hình thức**; trong lời gọi `book.rename("Java");`, `"Java"` là **đối số**. `newName` tồn tại dưới tên đó trong phạm vi method, và lời gọi cung cấp giá trị ban đầu cho nó.

- Mỗi lần gọi có các parameter variables của riêng lần gọi.
- Parameter không tự là field: thay đổi tham số bằng phép gán **không tự thay đổi trạng thái đối tượng**.
- Constructor parameter cũng vậy: `this.name = name;` là thao tác tường minh chép giá trị tham số vào field.
- Trong method thông thường, parameter có kiểu khai báo, tên và có thể có modifier `final`; Java **không hỗ trợ đối số mặc định trong khai báo method** theo cú pháp `void f(int x = 1)`.

Parameter còn xuất hiện trong **lambda** và **catch clause**, với chi tiết riêng về kiểu, phạm vi và modifier. Trong bài này, phần chính tập trung vào parameter của method/constructor để dễ so sánh với field và local variable.

### 3.1. Java luôn truyền tham số theo giá trị

Đây là nguyên tắc đặc biệt quan trọng:

- Với **kiểu nguyên thủy** như `int`, method nhận **bản sao giá trị số**. Gán lại parameter không sửa biến bên gọi.
- Với **kiểu tham chiếu** như `StringBuilder` hoặc `Box`, method nhận **bản sao giá trị tham chiếu**. Bản sao này trỏ cùng đối tượng, vì vậy method có thể sửa nội dung đối tượng nếu đối tượng cho phép.
- Nếu method **gán parameter tham chiếu sang đối tượng khác**, biến tham chiếu ban đầu ở bên gọi vẫn không bị đổi. Java **không truyền tham chiếu biến của caller theo reference**.

Chương trình chạy được ở mục 6 sẽ minh họa cả ba tình huống này.

## 4. Local variable: biến dùng trong một phạm vi thực thi

Local variable được khai báo trong block, phần thân method/constructor hoặc cấu trúc cho phép khai báo biến cục bộ. Ví dụ:

~~~java
void calculate(int price) {
    int tax = 2;
    int total = price + tax;
    System.out.println(total);
}
~~~

`price` là parameter; `tax` và `total` là local variables. Mỗi lần method chạy, các biến cục bộ tương ứng phục vụ riêng lần thực thi đó. Chúng không trở thành trường của đối tượng và không thể được đọc từ method khác chỉ bằng tên biến ấy.

### 4.1. Biến cục bộ bắt buộc được gán trước khi đọc

Một field có giá trị mặc định, còn local variable phải thỏa quy tắc **definite assignment** (được gán chắc chắn trên mọi luồng điều khiển có thể đến nơi đọc).

~~~java
void example(boolean enabled) {
    int result;

    if (enabled) {
        result = 10;
    } else {
        result = 20;
    }

    System.out.println(result); // Hợp lệ: cả hai nhánh đều gán result
}
~~~

Đây là method minh họa, không phải tệp chạy độc lập. Nếu bỏ nhánh `else` mà không gán `result` ở đường khác, compiler sẽ báo biến cục bộ có thể chưa được khởi tạo. Dù bạn biết “thực tế enabled luôn true”, compiler vẫn áp dụng phân tích luồng điều khiển theo quy tắc ngôn ngữ.

Cần phân biệt:

~~~java
class Example {
    int field;   // Mặc định 0

    void method() {
        int local;
        // System.out.println(local); // Không biên dịch nếu mở comment
        local = 5;
        System.out.println(field + local);
    }
}
~~~

Trong trường hợp này `field` có thể đọc khi chưa gán tường minh vì đã mặc định là `0`; `local` phải được gán `5` trước lần đọc.

### 4.2. Phạm vi của local variable và các block

Các dấu ngoặc nhọn tạo những phạm vi block hữu ích:

~~~java
void blocks() {
    int outer = 10;

    if (outer > 0) {
        int inner = 5;
        System.out.println(outer + inner);
    }

    System.out.println(outer);
    // System.out.println(inner); // Lỗi: inner ngoài phạm vi
}
~~~

Trong phương thức trên, `outer` được dùng ở cả block ngoài và block `if`; `inner` chỉ có phạm vi trong block `if`. Khi phần khai báo nằm trong vòng `for` như `for (int i = 0; i < 3; i++)`, biến `i` chỉ tồn tại trong phạm vi mà cấu trúc `for` cho phép; không thể đọc `i` sau vòng lặp.

Trong Java, **không được khai báo lại một local variable hoặc parameter trùng tên bên trong một block lồng mà phạm vi của biến ngoài vẫn còn hiệu lực**. Ví dụ, nếu method đã khai báo `int n = 1;` thì một block lồng không thể khai báo lại `int n = 2;` theo cách tạo hai local variables cùng tên chồng phạm vi. Điều này khác với việc local/parameter che khuất **field** cùng tên, vốn là hợp lệ.

### 4.3. `var` chỉ suy luận kiểu trong ngữ cảnh cho phép

Từ Java 10, khai báo local variable có initializer có thể dùng `var`:

~~~java
var count = 5;            // Kiểu suy luận là int
var title = "Java";       // Kiểu suy luận là String
var names = new java.util.ArrayList<String>();
~~~

Đây là các dòng local variable minh họa trong method. `var` **không phải một kiểu dữ liệu động**: compiler suy luận kiểu tĩnh cụ thể lúc biên dịch. `var count = 5;` không cho phép về sau gán `count = "text";`.

Các khai báo sau không hợp lệ:

~~~java
// int dạng local được phép khai báo chưa gán:
int temporary;

// Sai ở ngữ cảnh local: không có initializer để suy luận kiểu
// var unknown;

// Sai ở cấp class: Java không cho var làm kiểu của field
// private var score = 10;
~~~

Không được dùng `var` để thay kiểu của parameter trong khai báo method/constructor thông thường; Java 11+ có cú pháp `var` riêng dành cho **tham số lambda** với các ràng buộc cụ thể. `var` cũng không dùng cho local declaration không có initializer hay initializer chỉ là `null`.

## 5. Trùng tên: field bị che khuất bởi parameter hoặc local variable

Khi field và parameter trùng tên, tên đơn giản trong method thường trỏ tới parameter; field có thể được xác định rõ bằng `this.fieldName`.

~~~java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }

    void print() {
        String name = "Local";
        System.out.println(name);      // Local variable
        System.out.println(this.name); // Instance field
    }
}
~~~

Trong constructor `Person(String name)`:

- `name` bên phải dấu `=` là parameter.
- `this.name` bên trái là instance field.
- Nếu viết `name = name;` thì chỉ gán lại parameter cho chính nó. Field `name` **không nhận giá trị của argument**.

Trong `print()`, `String name = "Local";` là local variable che khuất field `name`. `this.name` vẫn truy cập được field.

**`this` chỉ có nghĩa trong ngữ cảnh thực thể phù hợp.** Static method không có đối tượng hiện tại `this`; muốn truy cập instance field từ static method phải có một tham chiếu tới đối tượng, ví dụ `person.name` nếu quyền truy cập cho phép. Với static field, cách viết rõ ràng là `ClassName.field`.

Khi lớp có kế thừa, local/parameter có thể che khuất field, và field trong lớp con cũng có thể che khuất field lớp cha; đó là những cơ chế tên khác nhau. Trong phạm vi bài này, nguyên tắc cần nắm là **đừng lẫn sự giống nhau của tên với cùng một biến**.

## 6. Ví dụ chạy độc lập: cả ba loại biến trong một chương trình

Lưu đoạn mã vào **`VariableKindsDemo.java`**:

~~~java
public class VariableKindsDemo {
    private final String name; // Field thực thể
    private int points;        // Field thực thể, mặc định 0
    private static int createdCount; // Field static, mặc định 0

    public VariableKindsDemo(String name, int points) {
        // name và points bên phải dấu = là constructor parameters.
        this.name = name;
        this.points = points;
        createdCount++;
    }

    public void addPoints(int points) {
        int before = this.points; // Local variable
        this.points += points;    // this.points: field; points: parameter

        System.out.println(name + ": " + before + " -> " + this.points);
    }

    public void printScopes() {
        int points = 999; // Local variable che khuất field points
        System.out.println("local=" + points + ", field=" + this.points);
    }

    public static void main(String[] args) {
        VariableKindsDemo a = new VariableKindsDemo("A", 10);
        VariableKindsDemo b = new VariableKindsDemo("B", 20);

        a.addPoints(3);
        b.addPoints(4);
        a.printScopes();

        System.out.println("A=" + a.points + ", B=" + b.points);
        System.out.println("created=" + VariableKindsDemo.createdCount);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 VariableKindsDemo.java
java VariableKindsDemo
~~~

**Output chính xác:**

~~~text
A: 10 -> 13
B: 20 -> 24
local=999, field=13
A=13, B=24
created=2
~~~

Phân tích:

1. `name`, `points`, `createdCount` đều là fields; hai field đầu thuộc mỗi đối tượng A/B, còn `createdCount` thuộc lớp và được tăng khi constructor chạy.
2. `main(String[] args)` có parameter `args`, là mảng chuỗi do JVM truyền vào. Hai tên `a`, `b` là local variables trong method `main`, chứa tham chiếu tới hai đối tượng.
3. Trong `addPoints(int points)`, `points` là parameter nhận `3` hoặc `4`; `before` là local variable chứa giá trị field cũ tại lần gọi đó.
4. `this.points += points` thay đổi field của **đối tượng nhận lời gọi**, không gán lại parameter.
5. `printScopes()` tạo local variable `points = 999`, nhưng field A vẫn là `13`. Vì vậy dòng in có cả `local=999` và `field=13`.
6. Trong `main`, lời gọi có hai đối tượng A/B cho thấy fields độc lập; `createdCount` là giá trị chia sẻ cấp lớp.

**Điểm cần nhớ:** Một tên như `points` xuất hiện ở nhiều nơi không chứng minh đó là một biến duy nhất. Cần xét **nơi khai báo** và **biểu thức tham chiếu**.

## 7. Ví dụ chạy độc lập: truyền theo giá trị và tham chiếu đối tượng

Lưu đoạn mã dưới tên **`ParameterPassingDemo.java`**:

~~~java
public class ParameterPassingDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void changeNumber(int number) {
        number += 10; // Chỉ thay đổi parameter bản sao
        System.out.println("inside number=" + number);
    }

    static void changeBox(Box box) {
        box.value += 5;  // Sửa cùng đối tượng với bên gọi
        box = new Box(999); // Gán lại biến parameter, không gán lại biến caller
        System.out.println("inside box=" + box.value);
    }

    public static void main(String[] args) {
        int number = 7;    // Local variable
        Box box = new Box(20); // Local variable tham chiếu đối tượng

        changeNumber(number);
        System.out.println("outside number=" + number);

        changeBox(box);
        System.out.println("outside box=" + box.value);
    }
}
~~~

Lệnh chạy:

~~~bash
javac ParameterPassingDemo.java
java ParameterPassingDemo
~~~

Output:

~~~text
inside number=17
outside number=7
inside box=999
outside box=25
~~~

Giải thích chi tiết:

- `number` trong `main` là local variable với giá trị `7`. Khi gọi `changeNumber(number)`, Java tạo parameter `number` của lời gọi với **bản sao giá trị `7`**. Cộng `10` trong method tạo `17`, không làm biến `number` trong `main` đổi.
- `box` trong `main` lưu một giá trị tham chiếu tới đối tượng `Box(20)`. Parameter `box` của `changeBox` nhận **bản sao giá trị tham chiếu đó**; cả hai tạm thời cùng chỉ vào một đối tượng.
- `box.value += 5` đổi field của đối tượng đang được tham chiếu từ `20` thành `25`. Vì `main` vẫn tham chiếu cùng đối tượng ban đầu nên quan sát được `25`.
- `box = new Box(999)` chỉ làm **parameter box** trỏ sang đối tượng mới trong method; biến local `box` của `main` vẫn trỏ đối tượng cũ. Vì vậy method in `999`, caller in `25`.

Java **chỉ truyền theo giá trị**, kể cả khi giá trị được sao chép là tham chiếu. Thuật ngữ “truyền đối tượng theo tham chiếu” dễ khiến người học hiểu sai rằng method có thể gán lại trực tiếp biến tham chiếu của caller.

## 8. Thời gian tồn tại, phạm vi và cách JVM thực thi

**Scope** là vùng mã nơi tên biến được phép tham chiếu theo quy tắc Java. Nó khác với **thời gian tồn tại của giá trị/đối tượng** và khác với bố trí bộ nhớ thực tế.

- **Instance field**: là thành phần trạng thái của đối tượng. Có thể được truy cập trong nhiều lời gọi method khác nhau khi còn tham chiếu thích hợp và được phép truy cập.
- **Static field**: gắn với lớp trong ngữ cảnh nạp lớp; không tạo bản sao riêng khi gọi method hoặc `new` thêm đối tượng.
- **Parameter/local variable**: thuộc phạm vi một lần thực thi method/constructor/block. Mỗi lời gọi có binding riêng; tên local không tự xuất hiện trong lời gọi khác.
- **Đối tượng được tạo trong method**: không nhất thiết biến mất ngay khi method kết thúc. Nếu tham chiếu tới đối tượng được trả về hoặc lưu trong field/cấu trúc khác, đối tượng vẫn có thể tiếp tục tồn tại.
- **Local variable được lambda nắm bắt**: compiler và runtime thực hiện theo quy tắc capture, nên không nên dùng quy tắc đơn giản “mọi local variable luôn nằm trên stack rồi biến mất” để giải thích ngữ nghĩa Java.

Không nên đồng nhất field = heap và local variable = stack như một **cam kết bắt buộc** của Java. Đó có thể là mô hình trực quan cho người mới, nhưng JVM/JIT có quyền tối ưu hóa cách lưu trữ. Về mặt ngôn ngữ, phân biệt bằng **khai báo, phạm vi, gán giá trị và khả năng truy cập** là chính xác hơn.

## 9. `final`, effectively final và lambda capture

Từ khóa `final` có thể xuất hiện trước field, parameter hoặc local variable, nhưng hiệu ứng cụ thể phụ thuộc loại biến:

| Biến | `final` có ý nghĩa gì? |
| --- | --- |
| Instance field | Tuân thủ quy tắc gán một lần của final field; có thể gán ở khai báo hoặc giai đoạn khởi tạo được phép, như constructor |
| Static field | Tuân thủ quy tắc gán một lần của final field; thường gán ở khai báo hoặc static initializer |
| Parameter | Không được gán lại biến parameter trong thân method |
| Local variable | Không được gán lại sau khi đã được gán giá trị theo quy tắc definite assignment |

Ví dụ những đoạn sau đặt trong ngữ cảnh method phù hợp:

~~~java
final int limit = 10;
// limit = 11; // Sai: gán lại final local variable

final StringBuilder builder = new StringBuilder("A");
builder.append("B"); // Hợp lệ: không đổi biến tham chiếu builder
// builder = new StringBuilder(); // Sai: gán lại final variable
~~~

`final` đối với tham chiếu **không làm đối tượng được tham chiếu tự bất biến**. Nếu cần đối tượng bất biến, phải thiết kế/ chọn kiểu dữ liệu phù hợp.

Một local variable hoặc parameter **effectively final** là biến không khai báo `final` nhưng không bị gán lại theo quy tắc của ngôn ngữ. Lambda hoặc anonymous class có thể capture local variables và parameters chỉ khi chúng là `final` hoặc *effectively final*.

### Chương trình capture chạy độc lập

Lưu tệp **`CaptureDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class CaptureDemo {
    static void greet(final String prefix) {
        String name = "Lan"; // Effectively final
        Runnable sayHello = () -> System.out.println(prefix + " " + name);
        sayHello.run();
    }

    public static void main(String[] args) {
        greet("Chào");

        List<String> names = new ArrayList<>(); // Effectively final
        Runnable printSize = () -> System.out.println("size=" + names.size());

        names.add("Java"); // Sửa đối tượng, không gán lại biến names
        printSize();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CaptureDemo.java
java CaptureDemo
~~~

Output:

~~~text
Chào Lan
size=1
~~~

Trong `greet`, `prefix` là final parameter; `name` là effectively final local variable. Lambda đọc được cả hai. Trong `main`, `names` là effectively final vì biến tham chiếu không bị gán lại, dù đối tượng `ArrayList` có thêm phần tử.

Nếu thêm `name = "Mai";` sau khi khai báo mà vẫn dùng `name` trong lambda, hoặc thêm `names = new ArrayList<>();` sau khi lambda capture `names`, compiler sẽ báo lỗi vì biến không còn effectively final. Đây là kiểm tra khi **biên dịch**, không phải hạn chế việc sửa nội dung một đối tượng mutable.

## 10. Các trường hợp dễ nhầm khác

### 10.1. Parameter và argument không phải một biến

~~~java
int original = 5; // local variable
printValue(original); // original là argument expression
~~~

`printValue` có thể được khai báo `static void printValue(int value) { ... }` trong cùng lớp. `value` là parameter, được khởi tạo từ giá trị của argument `original`. Khi method thực hiện `value = 10`, biến `original` vẫn là `5`. Đoạn này chỉ minh họa mối quan hệ; không phải chương trình độc lập.

### 10.2. Trường và local cùng tên không có nghĩa là hai field

~~~java
class Sample {
    int value = 10;

    void show() {
        int value = 3;
        System.out.println(value);      // 3: local variable
        System.out.println(this.value); // 10: instance field
    }
}
~~~

Local variable `value` chỉ tồn tại trong phạm vi `show()`; nó không thay thế, không tạo field mới trong đối tượng. `this.value` là cách tham chiếu rõ ràng tới field.

### 10.3. Biến vòng lặp và biến trong block

~~~java
for (int i = 0; i < 2; i++) {
    int square = i * i;
    System.out.println(square);
}
// i và square đều không thể được tham chiếu ở đây
~~~

Đây là đoạn trong method. `i` và `square` là local variables với phạm vi khác nhau. `i` thuộc phạm vi của cấu trúc `for`; `square` chỉ thuộc block thân vòng lặp. Mỗi lần chạy block có thể xử lý giá trị riêng của local variable theo mô hình ngữ nghĩa của Java.

### 10.4. Parameter `final` không ngăn sửa đối tượng

~~~java
void rename(final StringBuilder builder) {
    builder.append("!");
    // builder = new StringBuilder(); // Không hợp lệ
}
~~~

Parameter `builder` không thể bị gán lại nếu khai báo `final`, nhưng `append` vẫn có thể thay đổi đối tượng mà tham chiếu trỏ tới. Đây cũng là ví dụ cho thấy “biến không được gán lại” khác “đối tượng bất biến”.

### 10.5. Quyền truy cập thuộc field, không thuộc local

`private`, `protected`, `public` áp dụng cho khai báo thành viên thích hợp, ví dụ fields. Không đặt chúng lên local variables hoặc parameters của method theo cách khai báo field. Local variables vốn chỉ được tham chiếu trong phạm vi xác định bởi block, còn field được điều chỉnh thêm bằng access modifier và kiểu lớp chứa nó.

## 11. Bảng lỗi phổ biến

| Lỗi hoặc nhầm lẫn | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `variable x might not have been initialized` | Đọc local variable trước khi compiler xác nhận nó đã được gán | Gán giá trị trên mọi đường thực thi đi tới điểm đọc |
| Field `String name` tự động là `""` | Nhầm default value của kiểu tham chiếu | Nhớ field tham chiếu mặc định `null`; khởi tạo khi cần |
| Constructor `name = name;` không cập nhật field | Tham số cùng tên đang che khuất field | Dùng `this.name = name;` |
| `non-static variable ... cannot be referenced from a static context` | Dùng instance field trực tiếp khi không có đối tượng trong static method | Truy cập qua tham chiếu đối tượng, hoặc chuyển thành static nếu dữ liệu thực sự thuộc lớp |
| Đổi parameter rồi mong caller đổi biến | Hiểu sai pass-by-value | Trả về giá trị mới rồi gán ở caller, hoặc thay đổi trạng thái đối tượng theo thiết kế |
| Hai đối tượng dùng `static` và mong có hai giá trị độc lập | `static` là field của lớp | Dùng instance field cho dữ liệu của từng đối tượng |
| Đọc local ra ngoài dấu `}` | Tên biến đã hết scope | Di chuyển nơi sử dụng hoặc điều chỉnh phạm vi khai báo hợp lý |
| Khai báo lại tên parameter như local trong cùng scope | Phạm vi tên chồng nhau | Chọn tên khác, hoặc sử dụng lại parameter đã khai báo |
| Lambda báo biến phải final/effectively final | Local/parameter bị gán lại sau hoặc trước capture | Thiết kế lại luồng dữ liệu, dùng biến không bị gán lại |
| Cho rằng `final List` là immutable | `final` chỉ hạn chế phép gán lại biến | Bảo vệ dữ liệu bằng API không sửa được hoặc sao chép phòng vệ |
| Dùng `var` khai báo field | Local variable type inference không áp dụng cho field | Viết kiểu field tường minh, ví dụ `private int count;` |
| Nhầm phạm vi với bộ nhớ stack/heap | Ngữ nghĩa Java không bắt buộc lưu từng biến tại địa chỉ cố định | Dựa vào scope, biến được gán thế nào và tham chiếu đối tượng thay vì đoán bố trí JVM |

## 12. Tự kiểm tra

**Câu 1.** Với khai báo `private int counter;` ở đầu lớp và `int counter = 5;` trong một method, có bao nhiêu biến?  
**Đáp án:** Có một instance field và một local variable khác nhau. Trong method, tên đơn giản `counter` thường trỏ tới local; `this.counter` trỏ field.

**Câu 2.** Tại sao `int age;` trong class có thể đọc thành `0`, còn `int age;` trong method không được in trước khi gán?  
**Đáp án:** Field được Java gán default value; local variable phải thỏa quy tắc definite assignment trước mỗi lần đọc.

**Câu 3.** Khi gọi `addPoints(3)`, số `3` và `int points` trong chữ ký method lần lượt là gì?  
**Đáp án:** `3` là argument, còn `points` là parameter được khởi tạo từ argument.

**Câu 4.** `void change(int x) { x = 100; }` có thay đổi biến `n` của caller khi gọi `change(n)` không?  
**Đáp án:** Không. `x` là bản sao giá trị được truyền vào, thay đổi `x` không tự gán lại `n`.

**Câu 5.** `void add(final List<String> values) { values.add("A"); }` có hợp lệ khi truyền vào một `ArrayList` sửa được không?  
**Đáp án:** Có. `final` ngăn gán lại parameter `values`, không ngăn sửa nội dung đối tượng được tham chiếu.

**Câu 6.** Field `private static int total;` và local `int total = 5;` trong một static method có thể phân biệt thế nào?  
**Đáp án:** Local dùng tên `total`; truy cập field bằng `TênLớp.total` (theo điều kiện truy cập). Không dùng `this` trong static method.

**Câu 7.** Một local variable khai báo `List<String> names = new ArrayList<>();`, dùng trong lambda, rồi gọi `names.add("B")`: local có mất tính effectively final không?  
**Đáp án:** Không. Lời gọi `add` sửa danh sách, không gán lại biến `names`. Nếu viết `names = new ArrayList<>();` thì biến không còn effectively final.

## Kết luận

Để phân biệt đúng ba loại biến, hãy xem **vị trí khai báo trước tiên**: khai báo ở thân lớp là **field**, trong danh sách tham số là **parameter**, trong method/block là **local variable**. Field giữ trạng thái của đối tượng hoặc lớp và có default value; parameter được khởi tạo từ đối số khi lời gọi bắt đầu; local variable phải được gán chắc chắn trước khi đọc. Scope quyết định nơi tên biến dùng được; `this.field` giải quyết trường hợp tên bị che khuất; Java truyền cả kiểu nguyên thủy lẫn giá trị tham chiếu **theo giá trị**. Nắm chắc những nguyên tắc này giúp constructor, method và lambda hoạt động đúng như mong đợi.
