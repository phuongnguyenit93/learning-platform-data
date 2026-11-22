# Phân biệt tham số hình thức và đối số tại lời gọi trong Java

Khi đọc một lời gọi phương thức Java như `greet("An", 2)`, cần phân biệt hai khái niệm:

- **Tham số hình thức (formal parameter)**: biến được **khai báo trong phần định nghĩa phương thức** để nhận dữ liệu khi phương thức được gọi. Ví dụ `String name` và `int times` trong `void greet(String name, int times)`.
- **Đối số (argument / actual argument)**: **biểu thức được cung cấp tại vị trí gọi** để truyền dữ liệu vào những tham số tương ứng. Ví dụ `"An"` và `2` trong `greet("An", 2)`.

Hai khái niệm nằm ở **hai phía khác nhau của một lời gọi**: tham số hình thức là một phần của *khai báo*, còn đối số là một phần của *lời gọi*. Java truyền **giá trị** thu được từ biểu thức đối số vào biến tham số, kể cả khi giá trị đó là một **tham chiếu đến đối tượng**.

## 1. Nhận biết nhanh bằng một ví dụ

```java
static void greet(String name, int times) {
    for (int i = 0; i < times; i++) {
        System.out.println("Xin chào " + name);
    }
}

// Khi gọi trong main hoặc một phương thức khác:
greet("An", 2);
```

Ở **khai báo**:

- `String name` là tham số hình thức thứ nhất, kiểu `String`, tên `name`.
- `int times` là tham số hình thức thứ hai, kiểu `int`, tên `times`.

Ở **lời gọi**:

- `"An"` là đối số thứ nhất, một biểu thức chuỗi.
- `2` là đối số thứ hai, một literal số nguyên.

Khi gọi, giá trị `"An"` được dùng để khởi tạo tham số `name`, còn `2` dùng để khởi tạo `times`. Vì vậy phương thức in hai lần:

```text
Xin chào An
Xin chào An
```

Đoạn trên minh họa cú pháp và hoạt động; muốn chạy độc lập cần đặt khai báo phương thức và lời gọi vào lớp/phương thức thích hợp. Một chương trình biên dịch chạy được có ở mục 4.

| Tiêu chí | Tham số hình thức | Đối số tại lời gọi |
| --- | --- | --- |
| Xuất hiện ở đâu? | Trong dấu `(...)` của **khai báo** phương thức/constructor | Trong dấu `(...)` của **biểu thức gọi** |
| Ví dụ | `int quantity` ở `buy(int quantity)` | `3` ở `buy(3)` |
| Bản chất | **Biến** có tên và kiểu được khai báo, thuộc phạm vi của phương thức | **Biểu thức** được đánh giá để cho giá trị truyền vào |
| Có bắt buộc là biến không? | Là khai báo biến tham số | Không: có thể là literal, biến, phép tính, lời gọi phương thức, `new ...` |
| Phạm vi sử dụng | Trong thân phương thức theo quy tắc scope | Ở mã gọi; bản thân biểu thức không tạo biến tham số |
| Khi nào nhận giá trị? | Mỗi lần phương thức được gọi, tham số được khởi tạo bằng giá trị đối số tương ứng | Biểu thức đối số được đánh giá tại lời gọi |
| Quan hệ kiểu dữ liệu | Kiểu tham số tham gia kiểm tra tính hợp lệ của lời gọi | Kết quả biểu thức phải có khả năng chuyển đổi phù hợp tới kiểu tham số |

**Mẹo đọc:** `calculate(int x, int y)` đang *đặt tên cho đầu vào*; `calculate(10, value + 1)` đang *cung cấp giá trị đầu vào*.

## 2. Cấu trúc khai báo và lời gọi phương thức

Một khai báo phương thức cơ bản:

```java
static int add(int left, int right) {
    return left + right;
}
```

Một lời gọi:

```java
int sum = add(10, 5);
```

Các thành phần có vai trò khác nhau:

- `add` là tên phương thức, `int` trước `add` là **kiểu trả về**.
- `int left` và `int right` là **hai khai báo tham số hình thức**.
- `10` và `5` là **hai biểu thức đối số**.
- `sum` là **biến nhận kết quả trả về**; nó không phải tham số của `add`.
- `return left + right;` trả một kết quả `int` về nơi gọi; thao tác trả kết quả khác với việc truyền đối số vào phương thức.

Biểu thức đối số không nhất thiết là một giá trị viết sẵn:

```java
int base = 4;
int result = add(base + 1, Math.max(2, 7));
```

Trong trường hợp này:

1. Đối số thứ nhất `base + 1` được đánh giá thành `5`.
2. Đối số thứ hai `Math.max(2, 7)` được đánh giá thành `7`.
3. Hai tham số `left` và `right` của `add` nhận hai giá trị `5` và `7`.
4. Phương thức trả về `12` và biến `result` nhận giá trị đó.

**Không có chuyện đặt tên đối số theo tên tham số khi gọi** trong Java 17. Không viết `add(left: 5, right: 7)` theo kiểu cú pháp named arguments của một số ngôn ngữ khác. Cách gọi thông thường là `add(5, 7)` với vị trí tương ứng.

## 3. Cách Java truyền giá trị từ đối số vào tham số

Khi một phương thức được gọi, về mặt logic Java thực hiện:

1. Xác định phương thức sẽ gọi theo quy tắc tên, kiểu, số lượng đối số, overload và khả năng truy cập.
2. Đánh giá biểu thức receiver nếu cần và các biểu thức đối số theo quy tắc thứ tự đánh giá của Java.
3. Kiểm tra/thực hiện các chuyển đổi phù hợp để khởi tạo các biến tham số.
4. Thực thi phần thân phương thức với **một bộ biến tham số riêng cho lần gọi đó**.
5. Khi phương thức kết thúc, trả quyền điều khiển về nơi gọi, kèm giá trị trả về nếu phương thức khai báo kiểu khác `void`.

Điểm trọng tâm: **Java luôn truyền tham số theo giá trị (pass-by-value)**.

- Với đối số kiểu nguyên thủy như `int`, `double` hoặc `boolean`, tham số nhận **bản sao giá trị nguyên thủy**.
- Với đối số kiểu tham chiếu như `Person` hay `List<String>`, tham số nhận **bản sao giá trị tham chiếu**. Cả bên gọi và tham số có thể cùng tham chiếu đến **một đối tượng**, nhưng vẫn là **hai biến khác nhau**.
- **Gán lại một tham số** không gán lại biến tham chiếu của bên gọi.
- **Thay đổi trạng thái đối tượng được cùng tham chiếu**, nếu đối tượng cho phép, có thể được bên gọi nhìn thấy.

Không nên diễn đạt “Java truyền đối tượng theo tham chiếu” vì dễ bị hiểu thành Java cho phép một phương thức thay đổi trực tiếp *biến* của nơi gọi. Java truyền **bản sao của giá trị tham chiếu**, không phải cơ chế pass-by-reference của biến theo nghĩa đó.

## 4. Ví dụ hoàn chỉnh: tham số, đối số và pass-by-value

Lưu toàn bộ mã sau vào **`ParameterArgumentDemo.java`**:

```java
class Person {
    String name;

    Person(String name) {
        this.name = name;
    }
}

public class ParameterArgumentDemo {
    static void greet(String name, int times) {
        for (int i = 0; i < times; i++) {
            System.out.println("Xin chào " + name);
        }
    }

    static int add(int left, int right) {
        return left + right;
    }

    static void changeNumber(int number) {
        number = 999;
        System.out.println("Trong changeNumber: " + number);
    }

    static void changeName(Person person) {
        person.name = "Bình";
    }

    static void replacePerson(Person person) {
        person = new Person("Linh");
        System.out.println("Trong replacePerson: " + person.name);
    }

    public static void main(String[] args) {
        greet("Java", 2);

        int base = 7;
        System.out.println("Tổng: " + add(base, 5));

        changeNumber(base);
        System.out.println("Sau changeNumber: " + base);

        Person original = new Person("An");
        changeName(original);
        System.out.println("Sau changeName: " + original.name);

        replacePerson(original);
        System.out.println("Sau replacePerson: " + original.name);
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ParameterArgumentDemo.java
java ParameterArgumentDemo
```

**Kết quả chuẩn:**

```text
Xin chào Java
Xin chào Java
Tổng: 12
Trong changeNumber: 999
Sau changeNumber: 7
Sau changeName: Bình
Trong replacePerson: Linh
Sau replacePerson: Bình
```

Giải thích chi tiết:

- Trong `greet(String name, int times)`, `name` và `times` là tham số hình thức; trong `greet("Java", 2)`, `"Java"` và `2` là đối số.
- Trong `add(int left, int right)`, `left` và `right` là tham số. Tại `add(base, 5)`, **biến `base` ở vị trí đối số** được *đọc lấy giá trị* `7` và giá trị literal `5` được truyền vào; hai tham số không phải hai tên mới của biến `base`.
- `changeNumber(base)` sao chép giá trị nguyên thủy `7` vào tham số `number`. Gán `number = 999` chỉ thay đổi **tham số bên trong lời gọi**, vì vậy `base` ở `main` vẫn là `7`.
- `changeName(original)` sao chép **tham chiếu đến đối tượng `Person`** vào tham số `person`. `person.name = "Bình"` thay đổi đối tượng được chia sẻ nên `original.name` trở thành `"Bình"`.
- `replacePerson(original)` cũng nhận bản sao tham chiếu. `person = new Person("Linh")` chỉ gán lại biến tham số `person` thành tham chiếu của đối tượng mới; biến `original` ở `main` vẫn trỏ đối tượng ban đầu có tên `"Bình"`.

Sơ đồ khi vừa gọi `changeName(original)`:

```text
Trong main: original ──┐
                       ├────> Person { name: "An" }
Tham số:      person ──┘

person.name = "Bình"    => đối tượng chung đổi name thành "Bình"
```

Sơ đồ trong `replacePerson(original)` **sau khi gán lại tham số**:

```text
Trong main: original ────────> Person { name: "Bình" }

Tham số:    person   ────────> Person { name: "Linh" }
```

Hai biến tham chiếu không còn trỏ cùng đối tượng; chỉ **biến cục bộ `person`** đã đổi. Sau khi phương thức kết thúc, `original` không bị gán lại.

## 5. Đối số có thể là những biểu thức nào?

Đối số là một **biểu thức có giá trị phù hợp**, không bắt buộc là một biến đã khai báo. Các ví dụ sau giả định chúng nằm trong ngữ cảnh có những khai báo tương ứng:

| Lời gọi | Biểu thức đối số | Giá trị được truyền |
| --- | --- | --- |
| `printNumber(5)` | Literal `5` | Số nguyên `5` |
| `printNumber(total)` | Đọc giá trị biến `total` | Giá trị hiện tại của `total` |
| `printNumber(a + b)` | Biểu thức cộng | Kết quả phép cộng |
| `printNumber(Math.abs(-8))` | Lời gọi phương thức | `8` |
| `showName("An" + " Bình")` | Nối chuỗi | `"An Bình"` |
| `save(new Person("Lan"))` | Tạo đối tượng | Tham chiếu đến đối tượng mới |
| `showPerson(null)` | Literal `null` | Tham chiếu rỗng, nếu kiểu tham số phù hợp |
| `process(flag ? x : y)` | Biểu thức điều kiện | Giá trị nhánh được chọn |
| `accept(list.get(0))` | Lời gọi phương thức trên đối tượng | Kết quả `get(0)` |

Vì mỗi đối số có thể là một biểu thức, số lượng tham số hình thức của phương thức **không tương đương** số biến cục bộ xuất hiện trong lời gọi. Ví dụ `sum(a + b, c * 2)` có **hai đối số**, dù biểu thức đọc **ba biến** `a`, `b`, `c`.

### Biểu thức đối số được đánh giá trước khi phần thân phương thức chạy

```java
static void show(int value) {
    System.out.println("Trong show: " + value);
}

// Trong một phương thức:
int number = 3;
show(number++);  // Đối số được đánh giá, number tăng
```

`show` nhận **giá trị cũ `3`** vì `number++` là post-increment; biến `number` ở nơi gọi sau đó là `4`. Nếu muốn tránh tác dụng phụ khó theo dõi, tính kết quả trong một lệnh riêng rồi truyền vào phương thức.

## 6. Java đánh giá các biểu thức đối số từ trái sang phải

Thứ tự biểu thức có side effect là kiến thức quan trọng khi gọi phương thức nhiều tham số. Java xác định thứ tự đánh giá các biểu thức đối số **từ trái sang phải**.

Ví dụ Java 17 độc lập, lưu thành **`ArgumentOrderDemo.java`**:

```java
public class ArgumentOrderDemo {
    static int trace(String label, int value) {
        System.out.println("Đánh giá " + label + ": " + value);
        return value;
    }

    static int add(int left, int right) {
        System.out.println("Bắt đầu add");
        return left + right;
    }

    public static void main(String[] args) {
        int result = add(
                trace("trái", 2),
                trace("phải", 3)
        );
        System.out.println("Kết quả: " + result);
    }
}
```

```bash
javac -encoding UTF-8 ArgumentOrderDemo.java
java ArgumentOrderDemo
```

**Stdout:**

```text
Đánh giá trái: 2
Đánh giá phải: 3
Bắt đầu add
Kết quả: 5
```

Ý nghĩa:

1. Java đánh giá đối số thứ nhất `trace("trái", 2)` và thu được `2`.
2. Sau đó mới đánh giá đối số thứ hai `trace("phải", 3)` và thu được `3`.
3. Khi các giá trị đối số đã được chuẩn bị, phần thân `add` nhận các tham số `left = 2` và `right = 3`.
4. Giá trị trả về `5` được gán cho `result`.

Nếu một biểu thức đối số ném ngoại lệ và lời gọi bị dừng, những biểu thức đối số phía sau có thể **không được đánh giá**. Vì thế nên tránh dùng quá nhiều phép tăng/giảm hoặc cập nhật trạng thái trong danh sách đối số khi điều đó làm khó hiểu mã nguồn.

**Đối số không nhất thiết được tính ở nơi khai báo phương thức.** Biểu thức của đối số chạy tại thời điểm gọi; tham số mới được sử dụng trong phần thân của lời gọi tương ứng.

## 7. Số lượng, vị trí và kiểu dữ liệu giữa đối số và tham số

Với phương thức không có `varargs`, Java yêu cầu **số đối số** phù hợp với **số tham số hình thức**, và từng đối số phải có kiểu có thể chuyển sang kiểu tham số theo các quy tắc áp dụng.

```java
static void register(String username, int age) {
    System.out.println(username + ": " + age);
}
```

Các lời gọi:

```java
register("An", 20);       // Hợp lệ
register("Bình", 18);     // Hợp lệ

// register("An");        // SAI: thiếu một đối số
// register("An", 20, 1);  // SAI: thừa một đối số
// register(20, "An");     // SAI: thứ tự/kiểu không phù hợp
```

Các ví dụ lời gọi giả định đặt trong một phương thức; hai lệnh bị comment không biên dịch nếu bỏ comment.

**Vị trí có ý nghĩa.** Java ghép đối số thứ nhất với tham số thứ nhất, đối số thứ hai với tham số thứ hai, trừ trường hợp cơ chế varargs đặc biệt. Tên tham số không tự điều khiển cách ghép.

### 7.1. Chuyển đổi kiểu hợp lệ khi truyền đối số

Không phải kiểu đối số luôn phải **trùng hệt** kiểu tham số. Java cho phép những chuyển đổi tương thích theo ngữ cảnh gọi phương thức, chẳng hạn:

```java
static void showLong(long number) {
    System.out.println(number);
}

static void showBoxed(Integer number) {
    System.out.println(number);
}

static void showObject(Object value) {
    System.out.println(value);
}
```

Ví dụ trong phương thức:

```java
showLong(10);       // int -> long: widening primitive
showBoxed(10);      // int -> Integer: boxing
showObject("Hello");// String -> Object: widening reference
```

Ngoài ra có unboxing (`Integer` sang `int`) khi điều kiện phù hợp. **Không được tự giả định mọi kiểu đều được chuyển đổi**: `showLong("10")` không hợp lệ vì Java không tự chuyển chuỗi sang số nguyên trong lời gọi. Nếu truyền `null` cho tham số đòi `int`, lời gọi không hợp lệ; nếu truyền một biến `Integer` đang là `null` để unbox thành `int` thì có thể ném `NullPointerException` khi chạy.

Chuyển đổi được chấp nhận trong một lời gọi còn phụ thuộc overload và các giai đoạn chọn phương thức. Đừng suy ra rằng Java sẽ chọn bất cứ overload nào chỉ nhờ “ép kiểu tiện nhất”.

### 7.2. Kiểu tham số tham gia lựa chọn overload

Ví dụ:

```java
static void display(int number) {
    System.out.println("int: " + number);
}

static void display(String text) {
    System.out.println("String: " + text);
}
```

`display(5)` gọi overload có tham số `int`; `display("5")` gọi overload có tham số `String`. Khai báo có **cùng tên nhưng danh sách kiểu tham số khác nhau** là overloading.

Các overload **không thể chỉ khác nhau về tên của tham số**:

```java
// SAI khi cùng nằm trong một lớp:
// static void set(int first) { }
// static void set(int second) { }
```

Tên `first` và `second` không làm hai chữ ký phương thức khác nhau.

Tương tự, hai overload có cùng tên và danh sách kiểu tham số nhưng chỉ khác **kiểu trả về** cũng không hợp lệ. Java lựa chọn overload dựa trên kiểu và số lượng đối số cùng các quy tắc tương ứng, không dựa chỉ vào tên tham số hình thức hay kiểu của biến bên trái phép gán.

### 7.3. `null` có thể gây overload không rõ ràng

Xét hai overload:

```java
static void read(String text) { }
static void read(Integer number) { }
```

`read(null)` là **lời gọi mơ hồ** vì `null` có thể dùng cho cả `String` và `Integer`, mà hai kiểu không có quan hệ subtype trực tiếp để chọn một overload cụ thể hơn. Có thể chỉ rõ ý định khi cần:

```java
read((String) null);
read((Integer) null);
```

Các đoạn này chỉ để minh họa cú pháp, không phải chương trình độc lập. Với các API thực tế, tránh overload dễ gây mơ hồ hoặc dùng tên phương thức khác nhau để thể hiện mục đích.

## 8. Tham số hình thức là biến cục bộ theo từng lần gọi

Tên tham số có phạm vi riêng trong thân phương thức theo quy tắc ngôn ngữ. Mỗi lần gọi có **các biến tham số riêng**, nên các lời gọi không chia sẻ cùng một biến tham số chỉ vì chúng dùng cùng tên.

```java
static int twice(int value) {
    value = value * 2;
    return value;
}
```

Một đoạn mã gọi:

```java
int original = 6;
int first = twice(original);
int second = twice(original);

System.out.println(original); // 6
System.out.println(first);    // 12
System.out.println(second);   // 12
```

Trong mỗi lời gọi, tham số `value` được khởi tạo bằng `6` từ đối số `original`; dòng `value = value * 2` chỉ thay đổi **biến tham số của lần gọi hiện tại**.

**Tham số không được khai báo trùng tên trong cùng danh sách khai báo.** Ví dụ `void f(int x, int x)` không hợp lệ. Bên trong thân phương thức cũng không được khai báo một biến cục bộ trùng tên tham số trong phạm vi bị chồng lấn:

```java
static void show(int count) {
    // int count = 0; // SAI: trùng tên tham số trong cùng phạm vi
    System.out.println(count);
}
```

Trái lại, các phương thức khác nhau có thể dùng cùng tên tham số, chẳng hạn `add(int value)` và `multiply(int value)` vì chúng ở các phạm vi phương thức khác nhau.

### 8.1. Tham số có thể che khuất field

```java
class User {
    private String name;

    User(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }
}
```

Ở constructor và `rename`:

- `name` (không có `this`) là **tham số hình thức**.
- `this.name` là **field của đối tượng hiện tại**.
- `this.name = name;` sao chép giá trị tham chiếu từ tham số sang field.

Dùng tên tham số trùng field thường gặp và hợp lệ. `this` giúp phân biệt rõ hai biến độc lập; `this.name` không phải một tham số khác.

## 9. `final` áp dụng cho tham số hình thức

Có thể khai báo tham số `final`:

```java
static void printLength(final String text) {
    System.out.println(text.length());
    // text = "Khác"; // SAI: không được gán lại tham số final
}
```

`final` ngăn **gán lại biến tham số** trong thân phương thức. Nó **không** ngăn gọi phương thức trên một đối tượng mutable được tham chiếu:

```java
static void addItem(final java.util.List<String> items) {
    items.add("Mới"); // Hợp lệ nếu List hỗ trợ thêm phần tử
    // items = new java.util.ArrayList<>(); // SAI: gán lại tham số final
}
```

Dòng `items.add("Mới")` thao tác với đối tượng `List` đang được tham chiếu; nó không gán lại biến `items`. Muốn hàm không làm thay đổi danh sách, phải có hợp đồng và cách triển khai phù hợp, không chỉ thêm `final` vào tham số.

Việc sử dụng `final` là lựa chọn của API/đội phát triển, không biến cơ chế truyền tham số của Java thành pass-by-reference hoặc tự động bảo đảm bất biến đối tượng.

## 10. Tham số biến độ dài (varargs) và đối số tại lời gọi

Với phương thức có **varargs**, tham số cuối được khai báo bằng cú pháp `Type... name`. Bên trong thân phương thức, nó hoạt động như **một biến mảng** của kiểu tương ứng.

```java
static int sumAll(int... numbers) {
    int sum = 0;
    for (int n : numbers) {
        sum += n;
    }
    return sum;
}
```

Trong khai báo `sumAll(int... numbers)`, chỉ có **một tham số hình thức**: `numbers`, kiểu sử dụng trong thân là `int[]`.

Khi gọi, có thể truyền các đối số mở rộng:

```java
sumAll();                     // Không có đối số bổ sung, mảng rỗng
sumAll(1, 2, 3);              // Ba biểu thức đối số kiểu int
sumAll(new int[]{4, 5});     // Một đối số là mảng int[]
```

Java có thể đóng gói những giá trị int riêng lẻ vào một mảng để cung cấp cho tham số varargs theo quy tắc gọi phương thức. `varargs` phải nằm **cuối danh sách tham số** và chỉ có thể có **một tham số biến độ dài** trong một khai báo.

Ví dụ độc lập, lưu **`VarargsDemo.java`**:

```java
public class VarargsDemo {
    static int sumAll(int... numbers) {
        int sum = 0;
        for (int number : numbers) {
            sum += number;
        }
        return sum;
    }

    static void report(String title, int... scores) {
        System.out.println(title + ": " + sumAll(scores));
    }

    public static void main(String[] args) {
        System.out.println(sumAll());
        System.out.println(sumAll(1, 2, 3));
        System.out.println(sumAll(new int[]{4, 5}));
        report("Điểm", 2, 3, 4);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 VarargsDemo.java
java VarargsDemo
```

Stdout:

```text
0
6
9
Điểm: 9
```

Trong `report(String title, int... scores)`, `title` và `scores` là **hai tham số hình thức**. Lời gọi `report("Điểm", 2, 3, 4)` có **bốn biểu thức đối số**. Ba số nguyên cuối cùng được xử lý theo cơ chế varargs vào mảng `scores`.

**Không suy luận “số đối số luôn bằng số tham số”.** Điều đó đúng với lời gọi thông thường không varargs ở mức danh sách, nhưng với varargs số lượng biểu thức thực tế có thể thay đổi. Trong lời gọi dạng mảng `sumAll(new int[]{4, 5})`, toàn bộ mảng là **một đối số**.

## 11. Tham số của constructor cũng khác đối số của `new`

Constructor có **tham số hình thức** tương tự phương thức, và khi tạo đối tượng bằng `new`, biểu thức trong dấu ngoặc là **đối số** của lời gọi constructor.

```java
class Book {
    private final String title;
    private final int pages;

    Book(String title, int pages) {
        this.title = title;
        this.pages = pages;
    }

    String summary() {
        return title + " (" + pages + " trang)";
    }
}
```

Đoạn gọi trong một phương thức:

```java
Book book = new Book("Java Core", 320);
System.out.println(book.summary());
```

Ở khai báo `Book(String title, int pages)`, `title` và `pages` là **tham số hình thức của constructor**. Trong `new Book("Java Core", 320)`, chuỗi và số là **hai đối số**. `this.title` và `this.pages` là **field của đối tượng mới** được constructor gán từ tham số.

Điều này không biến `new Book(...)` thành một lời gọi phương thức `void`: constructor **không khai báo kiểu trả về**; biểu thức tạo đối tượng `new Book(...)` tạo đối tượng và cho ra tham chiếu đến đối tượng nếu hoàn tất bình thường.

## 12. Đối số của lời gọi instance method và biểu thức receiver

Xét:

```java
class Calculator {
    int multiply(int a, int b) {
        return a * b;
    }
}
```

Một lời gọi:

```java
Calculator calculator = new Calculator();
int result = calculator.multiply(3, 4);
```

Cần phân biệt:

- `calculator` là **biểu thức receiver** (đối tượng được gọi phương thức trên đó).
- `3` và `4` là **hai biểu thức đối số** của lời gọi.
- `int a` và `int b` là **hai tham số hình thức** được khai báo.
- Từ khóa `this` trong thân instance method (nếu được sử dụng) chỉ đối tượng receiver; nó **không phải một tham số hình thức do bạn khai báo trong danh sách `(...)`**.
- `result` nhận **giá trị trả về** `12`; nó không phải đối số truyền vào `multiply`.

Với một phương thức `static` như `Math.max(3, 4)`, `Math` là tên lớp để truy cập phương thức và không có instance receiver `this`. Hai biểu thức `3` và `4` vẫn là đối số.

Một phương thức có thể không có tham số hình thức nào:

```java
static String greeting() {
    return "Xin chào";
}
```

Lời gọi `greeting()` không có đối số. Dấu ngoặc trống là một phần cú pháp lời gọi, không có nghĩa phương thức không thể trả về giá trị.

## 13. Lambda và tham số kiểu (type parameter): đừng nhầm với đối số giá trị

Trong Java, từ “parameter” còn xuất hiện ở những ngữ cảnh khác, cần phân biệt khi đọc mã:

### 13.1. Tham số hình thức của biểu thức lambda

```java
java.util.function.Function<Integer, Integer> square =
        (Integer number) -> number * number;

int result = square.apply(5);
```

`number` là **tham số hình thức của lambda**; nó nhận dữ liệu khi hàm được gọi qua phương thức chức năng tương ứng. `5` là đối số của lời gọi `apply(5)`; đoạn ví dụ trả về `25`.

Java cũng cho phép suy luận kiểu trong nhiều lambda:

```java
java.util.function.Function<Integer, Integer> doubleIt =
        value -> value * 2;
```

`value` vẫn là tham số, dù không viết kiểu `Integer` tường minh.

### 13.2. Tham số kiểu và đối số kiểu trong generic

```java
static <T> T identity(T value) {
    return value;
}
```

Trong khai báo này có **hai phạm trù khác nhau**:

- `T` sau `<T>` là **tham số kiểu** (*type parameter*) của phương thức generic.
- `T value` là **tham số hình thức nhận giá trị**; kiểu của nó phụ thuộc vào việc áp dụng generic.

Lời gọi:

```java
String text = MyUtils.<String>identity("Java");
```

Giả sử phương thức `identity` đã được khai báo `static` trong lớp `MyUtils`, thì `String` sau `<String>` là **đối số kiểu** (*type argument*), còn `"Java"` trong `(...)` mới là **đối số giá trị** của phương thức.

Cả hai đều có chữ “argument”, nhưng **khác ngữ cảnh**. Khi câu hỏi nói “tham số hình thức và đối số tại lời gọi phương thức”, trọng tâm là **danh sách biến trong ngoặc tròn** và **biểu thức đối số trong ngoặc tròn**, không phải cú pháp generic trong `<...>`.

## 14. Tham số `String[] args` của phương thức `main`

Phương thức điểm vào truyền thống:

```java
public static void main(String[] args) {
    System.out.println(args.length);
}
```

Trong khai báo `main(String[] args)`, `args` là **một tham số hình thức** kiểu `String[]`.

Khi chạy chương trình qua launcher:

```bash
java Main red blue
```

Nếu lớp `Main` chứa `main` nêu trên và đã được biên dịch, ứng dụng thường nhận mảng đối số dòng lệnh có hai phần tử chuỗi `"red"` và `"blue"`, nên in `2`.

Lưu ý có **hai cấp gọi khác nhau**:

- Ở lớp Java, `main` có **một tham số hình thức** kiểu mảng.
- Người dùng cung cấp các từ trên command line để launcher tạo dữ liệu mảng phục vụ `main`.

Đừng nhầm số token trên dòng lệnh với số tham số khai báo của `main`. Nếu chủ động gọi `Main.main(new String[]{"red", "blue"})` từ mã Java, lời gọi này có **một biểu thức đối số mảng**.

Ví dụ chạy được, lưu thành **`Main.java`**:

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("Số phần tử: " + args.length);
        for (String arg : args) {
            System.out.println(arg);
        }
    }
}
```

```bash
javac -encoding UTF-8 Main.java
java Main red blue
```

Stdout:

```text
Số phần tử: 2
red
blue
```

## 15. Các nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`int x` trong `f(int x)` là một đối số.” | `x` là **tham số hình thức** được khai báo; đối số xuất hiện ở `f(10)` hoặc `f(value)`. |
| “Tên biến truyền vào phải trùng tên tham số.” | Chỉ cần vị trí, số lượng và kiểu phù hợp; `f(total)` vẫn có thể truyền vào tham số tên `x`. |
| “Đối số bắt buộc là tên một biến.” | Có thể là literal, phép tính, kết quả lời gọi, biểu thức `new`, v.v. |
| “`f(a + b)` có hai đối số vì có hai biến.” | Nó có **một biểu thức đối số** là `a + b`. |
| “Tham số `int` và biến `int` ở nơi gọi là cùng một biến.” | Tham số nhận **bản sao giá trị** của đối số. |
| “Java truyền đối tượng theo tham chiếu nên gán lại tham số sẽ đổi biến của caller.” | Java sao chép **giá trị tham chiếu**; gán lại tham số không đổi biến ở caller. |
| “Mọi lời gọi phải có số đối số bằng đúng số tham số.” | Với **varargs**, số lượng biểu thức đối số có thể biến đổi. |
| “Tên tham số quyết định overload.” | Overload dựa trên danh sách kiểu tham số và các quy tắc lời gọi, không dựa vào tên tham số. |
| “`this` là một đối số viết trong `object.method(...)`.” | `this` biểu thị receiver trong instance method, không phải đối số tường minh trong ngoặc tròn. |
| “`return` là cách truyền đối số.” | `return` chuyển kết quả **từ phương thức ra ngoài**, đối số cung cấp dữ liệu **từ nơi gọi vào phương thức**. |
| “`final Person p` nghĩa là đối tượng Person không thể bị sửa.” | `final` trên tham số chỉ cấm gán lại biến tham số, không tự làm đối tượng bất biến. |
| “`T` trong `<T>` và `T value` đều là tham số giá trị.” | `T` là tham số **kiểu**; `value` mới là tham số hình thức nhận **giá trị**. |

## 16. Bài tự kiểm tra

### Câu 1 — Đếm đúng tham số và đối số

```java
static int calculate(int x, int y, int z) {
    return x + y * z;
}

// Trong một phương thức:
int a = 2;
int b = 3;
int result = calculate(a + b, 4, a);
```

**Đáp án:** `calculate` khai báo **ba tham số hình thức**: `x`, `y`, `z`. Lời gọi có **ba biểu thức đối số**: `a + b`, `4`, `a`. Giá trị truyền lần lượt là `5`, `4`, `2`; kết quả `5 + 4 * 2 = 13`.

### Câu 2 — Thay đổi biến primitive bên ngoài?

```java
static void increment(int count) {
    count++;
}

// Trong một phương thức:
int n = 10;
increment(n);
System.out.println(n);
```

**Đáp án:** In `10`. `n` là đối số dạng biến; biến tham số `count` được khởi tạo bằng **bản sao số `10`**. `count++` không đổi `n`.

### Câu 3 — Thay đổi đối tượng hay thay đổi tham số?

```java
class Box {
    int value;
}

static void change(Box box) {
    box.value = 20;
    box = new Box();
    box.value = 50;
}
```

Giả sử các khai báo trên đã nằm trong ngữ cảnh hợp lệ, đoạn gọi:

```java
Box original = new Box();
original.value = 5;
change(original);
System.out.println(original.value);
```

**Đáp án:** In `20`. Phép gán `box.value = 20` sửa đối tượng của `original`. Sau đó `box = new Box()` chỉ chuyển **biến tham số** sang đối tượng mới; `box.value = 50` không tác động đến `original`.

### Câu 4 — Số đối số với varargs

```java
static void print(String heading, int... values) {
    System.out.println(heading + ": " + values.length);
}
```

Hãy đếm:

- `print("A");` có **một biểu thức đối số**, và mảng `values` có `0` phần tử.
- `print("B", 1, 2);` có **ba biểu thức đối số**, và mảng `values` có `2` phần tử.
- `print("C", new int[]{5, 6});` có **hai biểu thức đối số**, và mảng `values` có `2` phần tử.

Trong cả ba trường hợp, khai báo `print` chỉ có **hai tham số hình thức**: `heading` và `values`.

### Câu 5 — Phân biệt loại tên

```java
static <T> T echo(T item) {
    return item;
}
```

Với lời gọi `Util.<String>echo("OK")` (giả sử `echo` thuộc lớp `Util`):

- `T` là **tham số kiểu**.
- `item` là **tham số hình thức nhận giá trị**.
- `String` trong `<String>` là **đối số kiểu**.
- `"OK"` trong `("OK")` là **đối số giá trị**.
- Kết quả trả về là chuỗi `"OK"`.

## Ghi nhớ

1. **Tham số hình thức** nằm ở **khai báo**: `method(Type parameterName)`.
2. **Đối số** nằm ở **lời gọi**: `method(expression)`. Đối số có thể là bất kỳ biểu thức có giá trị hợp lệ, không nhất thiết là biến.
3. Đối số được đánh giá và giá trị của chúng được dùng để khởi tạo biến tham số theo quy tắc gọi; Java **pass-by-value**, kể cả với tham chiếu.
4. Thay đổi **biến tham số** không làm biến bên gọi đổi giá trị; thay đổi **đối tượng được cùng tham chiếu** có thể được quan sát từ bên gọi.
5. Số lượng, thứ tự và kiểu đối số phải phù hợp với phương thức được chọn; **overloading** và **varargs** là các trường hợp cần xem xét thêm.
6. **Đối số truyền vào** và **giá trị `return` trả ra** là hai hướng dữ liệu khác nhau; receiver, biến nhận kết quả và type argument cũng không phải tham số hình thức nhận giá trị trong ngoặc tròn.
