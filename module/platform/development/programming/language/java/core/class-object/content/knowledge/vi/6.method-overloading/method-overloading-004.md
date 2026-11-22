# Lựa chọn phương thức theo kiểu tại thời điểm biên dịch trong Java

Khi một lớp có nhiều phương thức **nạp chồng (overloading)** cùng tên, Java phải xác định **phương thức nào được gọi**. Điểm nền tảng là: **lựa chọn overload được thực hiện khi biên dịch, dựa trên kiểu được xác định tại thời điểm biên dịch của các biểu thức liên quan đến lời gọi**, cùng với số lượng đối số, khả năng áp dụng và các quy tắc chọn phương thức cụ thể nhất.

Điều này dẫn đến tình huống dễ nhầm: một biến được khai báo kiểu `Animal` nhưng đang tham chiếu đối tượng `Dog` thì lời gọi `describe(animal)` **không tự chọn** overload có tham số `Dog`. Compiler nhìn biểu thức `animal` có **kiểu tĩnh `Animal`**.

Phân biệt hai giai đoạn:

1. **Overload resolution — tại compile time:** lựa chọn chữ ký phương thức dựa trên kiểu của receiver và đối số, phạm vi truy cập và các quy tắc chuyển đổi.
2. **Dynamic dispatch — tại runtime nếu phương thức instance được override:** sau khi đã biết chữ ký được chọn, JVM quyết định **implementation override** nào chạy dựa trên đối tượng receiver thực tế.

Hai quá trình này liên quan nhưng không thay thế nhau. Bài sẽ giải thích rõ cách chọn overload, ưu tiên chuyển đổi kiểu, tình huống mơ hồ và cách đọc chính xác kết quả Java 17.

## 1. Định nghĩa overload và một ví dụ đầu tiên

**Nạp chồng phương thức** là việc khai báo nhiều phương thức cùng tên trong cùng ngữ cảnh kiểu, nhưng có **danh sách kiểu tham số khác nhau**. Ví dụ:

```java
static void show(int value) {
    System.out.println("int: " + value);
}

static void show(String value) {
    System.out.println("String: " + value);
}
```

Các lời gọi:

```java
show(10);     // Chọn show(int)
show("10");   // Chọn show(String)
```

Điều làm chữ ký khác nhau có thể là:

- **Số tham số:** `print()` và `print(String text)`.
- **Kiểu tham số:** `print(int number)` và `print(String text)`.
- **Thứ tự kiểu tham số:** `combine(int number, String text)` và `combine(String text, int number)`.

**Không thể** nạp chồng chỉ bằng tên biến tham số hoặc chỉ bằng kiểu trả về:

```java
// SAI nếu cả hai cùng nằm trong một lớp:
int calculate(int value) { return value; }
int calculate(int number) { return number * 2; }

// Cũng SAI nếu cả hai cùng nằm trong một lớp:
int size(String text) { return text.length(); }
long size(String text) { return text.length(); }
```

Các ví dụ `SAI` dùng để minh họa lỗi biên dịch, không phải chương trình runnable. Tên tham số `value`/`number` không phân biệt chữ ký; `int`/`long` ở vị trí kiểu trả về cũng không phân biệt chữ ký.

Điều quan trọng với bài này là **khi các overload hợp lệ đã được khai báo, Java lựa chọn overload nào tại lời gọi**.

## 2. Kiểu tại thời điểm biên dịch (static type) là gì?

**Kiểu tĩnh** của một biểu thức là kiểu mà trình biên dịch biết khi phân tích mã nguồn. Nó không nhất thiết trùng với **lớp thực tế lúc chạy** của đối tượng mà biểu thức đánh giá ra.

Ví dụ:

```java
class Animal { }
class Dog extends Animal { }

Animal pet = new Dog();
```

- `Animal` là **kiểu khai báo của biến `pet`**, cũng là kiểu tĩnh của biểu thức `pet`.
- `Dog` là **lớp thực tế** của đối tượng được tạo bởi `new Dog()`.
- Kiểu tĩnh của biểu thức `new Dog()` là `Dog`.
- Kiểu tĩnh của biểu thức `(Dog) pet` là `Dog` sau cast, với rủi ro `ClassCastException` tại runtime nếu đối tượng không thực sự tương thích với `Dog`.

Nếu có:

```java
static void inspect(Animal value) {
    System.out.println("Animal");
}

static void inspect(Dog value) {
    System.out.println("Dog");
}
```

Thì:

```java
inspect(pet);          // Chọn inspect(Animal)
inspect(new Dog());    // Chọn inspect(Dog)
inspect((Dog) pet);    // Chọn inspect(Dog), nếu cast hợp lệ khi chạy
```

**Cốt lõi:** Java không quan sát trước rằng `pet` đang chứa đối tượng `Dog` để tự chọn overload `inspect(Dog)`. Lựa chọn phải phù hợp với kiểu tĩnh `Animal`, bởi khi chạy, biến `pet` hoàn toàn có thể tham chiếu một đối tượng thuộc một lớp con khác.

## 3. Chương trình hoàn chỉnh: overload được chọn theo kiểu tĩnh

Lưu vào tệp **`StaticTypeDemo.java`**:

```java
class Animal {
}

class Dog extends Animal {
}

class Cat extends Animal {
}

public class StaticTypeDemo {
    static void describe(Animal animal) {
        System.out.println("Overload: Animal");
    }

    static void describe(Dog dog) {
        System.out.println("Overload: Dog");
    }

    static void describe(Cat cat) {
        System.out.println("Overload: Cat");
    }

    public static void main(String[] args) {
        Animal pet = new Dog();
        Dog dog = new Dog();
        Cat cat = new Cat();

        describe(pet);
        describe(dog);
        describe(cat);
        describe(new Dog());
        describe((Dog) pet);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 StaticTypeDemo.java
java StaticTypeDemo
```

**Stdout chính xác:**

```text
Overload: Animal
Overload: Dog
Overload: Cat
Overload: Dog
Overload: Dog
```

Giải thích từng lời gọi:

| Biểu thức đối số | Kiểu tại compile time | Lớp đối tượng lúc chạy | Overload được chọn |
| --- | --- | --- | --- |
| `pet` | `Animal` | `Dog` | `describe(Animal)` |
| `dog` | `Dog` | `Dog` | `describe(Dog)` |
| `cat` | `Cat` | `Cat` | `describe(Cat)` |
| `new Dog()` | `Dog` | `Dog` | `describe(Dog)` |
| `(Dog) pet` | `Dog` | `Dog` | `describe(Dog)` |

Trong chương trình, cast `(Dog) pet` chạy được vì `pet` đang giữ đối tượng `Dog`. Không nên cast tùy tiện chỉ để gọi một overload: ví dụ `(Dog) new Cat()` bị phát hiện là không thể chuyển đổi giữa hai lớp sibling trong tình huống này; còn một cast từ biến kiểu cha sang lớp con không tương thích với đối tượng thật có thể ném `ClassCastException`.

## 4. Quy trình chọn overload: ứng viên, khả năng áp dụng, độ cụ thể

Ở mức trực quan, có thể đọc quá trình lựa chọn một lời gọi phương thức như sau:

1. **Xác định nơi tra cứu phương thức:** receiver là kiểu nào, phương thức có tên gì, phương thức nào được thừa hưởng hoặc có thể truy cập? Java cũng có các quy tắc riêng cho lời gọi `super`, generic, method reference và interface.
2. **Xét số lượng và kiểu đối số:** các biểu thức đối số có thể được chuyển đổi đến kiểu tham số của overload nào theo quy tắc áp dụng?
3. **Xét theo giai đoạn:** ưu tiên phương thức áp dụng theo **strict invocation**, sau đó **loose invocation**, cuối cùng **variable arity** nếu chưa có phương thức áp dụng ở giai đoạn trước.
4. **Chọn phương thức cụ thể nhất:** trong giai đoạn đầu tiên có các ứng viên áp dụng, Java so sánh chúng theo quy tắc `most specific` của ngôn ngữ. Nếu không tồn tại một lựa chọn duy nhất, lời gọi có thể bị báo **ambiguous**.
5. **Kiểm tra các quy tắc còn lại:** quyền truy cập, ràng buộc generic, kiểu trả về trong ngữ cảnh và cách gọi phù hợp với phương thức được chọn.

Đây là hướng dẫn thực hành; thuật toán chính thức có nhiều chi tiết hơn về kiểu generic, biểu thức lambda, kiểu suy luận và phương thức có cùng chữ ký do kế thừa. Không thể đơn giản xem overload resolution như việc so “khoảng cách từ kiểu dữ liệu tới kiểu tham số”.

### Ba giai đoạn quan trọng

| Giai đoạn | Mô tả gần đúng | Ví dụ |
| --- | --- | --- |
| **1 — Strict invocation** | Dùng chuyển đổi cho phép trong ngữ cảnh strict; không cần boxing/unboxing, không mở rộng varargs | `int` → `long` |
| **2 — Loose invocation** | Nếu giai đoạn 1 không có ứng viên, cho phép thêm boxing/unboxing và các chuyển đổi được quy định | `int` → `Integer`; `Integer` → `long` qua unboxing rồi widening |
| **3 — Variable arity** | Nếu hai giai đoạn trước không có ứng viên, xét overload varargs với phần tử được mở rộng | `f(int...)` gọi bằng `f(1, 2)` |

**Một phương thức khai báo `int...` có thể được xét ở giai đoạn gọi fixed arity** khi truyền trực tiếp một đối số kiểu `int[]`; chữ `...` trong khai báo không đồng nghĩa mọi lời gọi của nó chỉ được xét ở giai đoạn 3.

## 5. Widening primitive được xét trước boxing và mở rộng varargs

Một trong những nhầm lẫn phổ biến là Java sẽ chọn phương thức có kiểu giống giá trị runtime nhất hoặc tự động ưu tiên wrapper. Trong các lời gọi thông thường, **primitive widening** thường có cơ hội ở giai đoạn strict trước khi boxing được xét.

Ví dụ chạy được, lưu **`PrimitiveOverloadDemo.java`**:

```java
public class PrimitiveOverloadDemo {
    static void select(long number) {
        System.out.println("long");
    }

    static void select(Integer number) {
        System.out.println("Integer");
    }

    static void select(int... numbers) {
        System.out.println("varargs " + numbers.length);
    }

    public static void main(String[] args) {
        select(5);
        select(Integer.valueOf(5));
        select((short) 5);
        select(1, 2);
        select(new int[]{3, 4, 5});
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 PrimitiveOverloadDemo.java
java PrimitiveOverloadDemo
```

Kết quả:

```text
long
Integer
long
varargs 2
varargs 3
```

**Phân tích:**

- `select(5)`: literal `5` có kiểu `int`. `select(long)` áp dụng nhờ **widening primitive `int → long`** ở giai đoạn 1, trước `select(Integer)` cần boxing ở giai đoạn 2 và `select(int...)` cần variable arity ở giai đoạn 3.
- `select(Integer.valueOf(5))`: biểu thức đã có kiểu `Integer`; `select(Integer)` nhận đúng kiểu ở giai đoạn 1, còn `select(long)` cần unboxing `Integer → int` rồi widening `int → long` ở giai đoạn 2.
- `select((short) 5)`: biểu thức có kiểu `short` và có thể widening sang `long` ngay ở giai đoạn 1.
- `select(1, 2)`: các overload `select(long)` và `select(Integer)` đều không nhận hai đối số; `select(int...)` được chọn khi mở rộng varargs.
- `select(new int[]{3, 4, 5})`: đối số là một mảng `int[]`, khớp tham số mảng của `select(int...)` theo **fixed arity**, và trong thân có ba phần tử.

Hãy phân biệt kiểu *literal* và kiểu *biến*: `Integer boxed = 5; select(boxed);` chọn overload `Integer`, còn `int primitive = 5; select(primitive);` chọn overload `long` trong chương trình này.

### Các phép chuyển đổi không phải lúc nào cũng kết hợp tự do

Ví dụ:

```java
static void show(Long value) {
    System.out.println("Long");
}

// show(5); // Không hợp lệ nếu chỉ có show(Long)
```

Lý do: `int` không được chuyển bằng chuỗi **widening primitive `int → long` rồi boxing `long → Long`** trong method invocation conversion theo cách đó. Java cho phép `int → Integer` qua boxing, và `int → long` qua widening, nhưng không tự ghép chúng thành `int → Long`.

Ngược lại, một đối số `Integer` có thể được **unbox** thành `int` rồi widening sang `long` khi phương thức nhận `long` được xét ở giai đoạn phù hợp.

## 6. Cụ thể nhất (most specific) theo kiểu tĩnh

Khi nhiều overload đều khả dụng trong một giai đoạn, Java chọn overload **cụ thể hơn** theo các quy tắc của ngôn ngữ.

Ví dụ:

```java
static String tag(Object value) {
    return "Object";
}

static String tag(CharSequence value) {
    return "CharSequence";
}

static String tag(String value) {
    return "String";
}
```

Các kiểu có quan hệ `String implements CharSequence` và `String extends Object`. Nếu đặt các khai báo trên vào một lớp phù hợp:

```java
System.out.println(tag("Java"));                  // String
System.out.println(tag((CharSequence) "Java"));  // CharSequence
System.out.println(tag((Object) "Java"));        // Object
```

Khi đối số là `"Java"`, kiểu tĩnh là `String` nên `tag(String)` cụ thể nhất trong các overload áp dụng. Với `(CharSequence) "Java"`, kiểu tĩnh của biểu thức sau cast là `CharSequence`; overload `tag(String)` không tự áp dụng chỉ vì đối tượng thực tế là `String`.

**Điểm quan trọng:** lựa chọn phương thức cụ thể nhất được thực hiện **trong tập ứng viên áp dụng của giai đoạn hiện tại**. Không được bỏ qua thứ tự giai đoạn chỉ để ưu tiên một overload dùng boxing có tên kiểu trông “gần” đối số hơn.

### Ví dụ chương trình độc lập

Lưu thành **`MostSpecificDemo.java`**:

```java
public class MostSpecificDemo {
    static void tag(Object value) {
        System.out.println("Object");
    }

    static void tag(CharSequence value) {
        System.out.println("CharSequence");
    }

    static void tag(String value) {
        System.out.println("String");
    }

    public static void main(String[] args) {
        String text = "Java";
        CharSequence sequence = text;
        Object object = text;

        tag(text);
        tag(sequence);
        tag(object);
        tag((Object) text);
        tag((CharSequence) text);
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 MostSpecificDemo.java
java MostSpecificDemo
```

Stdout:

```text
String
CharSequence
Object
Object
CharSequence
```

Cả ba biến `text`, `sequence`, `object` có thể trỏ đến **cùng một đối tượng `String`**, nhưng lựa chọn overload vẫn khác nhau vì **kiểu tĩnh khác nhau**.

## 7. Khi nào lời gọi bị mơ hồ (ambiguous)?

Một lời gọi **mơ hồ** khi tồn tại nhiều overload có thể áp dụng mà quy tắc chọn phương thức cụ thể nhất **không xác định được duy nhất một phương thức**.

### 7.1. Literal `null` và hai kiểu tham chiếu không có quan hệ subtype

```java
static void display(String text) {
    System.out.println("String");
}

static void display(Integer number) {
    System.out.println("Integer");
}

// display(null); // SAI: ambiguous
```

Literal `null` có thể phù hợp với cả `String` lẫn `Integer`, nhưng `String` và `Integer` không phải quan hệ subtype của nhau. Không có overload nào cụ thể hơn trong ví dụ này.

Có thể làm rõ ý định:

```java
display((String) null);  // Chọn display(String)
display((Integer) null); // Chọn display(Integer)
```

**Cần phân biệt:** nếu overload là `display(Object)` và `display(String)`, thì `display(null)` **không mơ hồ**: `String` cụ thể hơn `Object`.

### 7.2. Đối số bị mơ hồ khi có nhiều overload varargs

Ví dụ:

```java
static void send(String... messages) {
    System.out.println("String varargs");
}

static void send(Integer... numbers) {
    System.out.println("Integer varargs");
}

// send();     // SAI: ambiguous
// send(null); // SAI: ambiguous
```

Ở `send()`, không có giá trị nào giúp phân biệt `String[]` và `Integer[]` ở khả năng áp dụng varargs. Ở `send(null)`, cả hai overload đều có thể nhận mảng tham chiếu `null`. Cách gọi rõ ràng hơn:

```java
send(new String[0]);
send(new Integer[0]);
send((String[]) null);
```

Các đoạn trên là **mã minh họa**, giả định nằm trong lớp có các khai báo tương ứng; không chạy riêng lẻ.

### 7.3. Không giải quyết mơ hồ bằng cách nhìn dữ liệu thực tế

Nếu có hai overload `parse(String)` và `parse(Integer)`, Java **không đọc nội dung của `"123"` rồi tự suy luận** cần phiên bản xử lý số nguyên. Đối số `"123"` có kiểu `String`; muốn `Integer`, bên gọi phải tạo/biến đổi thành giá trị `Integer` hoặc dùng API tương ứng.

**Khi lời gọi mơ hồ**, ưu tiên thiết kế tên/kiểu API rõ ràng. Cast có thể hữu ích ở một lời gọi cụ thể nhưng không nên dùng để che một thiết kế overload quá khó hiểu.

## 8. Lựa chọn overload khác với override chạy đa hình

Đây là khác biệt cốt lõi giữa **nạp chồng** và **ghi đè**:

| Vấn đề | Overloading | Overriding |
| --- | --- | --- |
| Điều thay đổi | Danh sách tham số của các phương thức cùng tên | Triển khai của một instance method có chữ ký tương ứng |
| Cơ sở lựa chọn chính | Kiểu tĩnh, số lượng đối số và quy tắc Java khi biên dịch | Lớp thực tế của đối tượng receiver lúc chạy |
| Chọn lúc nào? | Compile time | Runtime cho instance method được override |
| Kiểu trả về khác có đủ tạo overload không? | Không | Phải tuân thủ return-type substitutability khi override |
| Phương thức `static` | Có thể nạp chồng; static method được chọn theo quy tắc tĩnh | Không override động; có thể bị **hiding** trong lớp con |
| Phương thức `private` | Có thể nạp chồng trong phạm vi có quyền truy cập | Không override theo nghĩa đa hình thông thường |

### 8.1. Một chương trình minh họa cả hai quá trình

Lưu thành **`OverloadOverrideDemo.java`**:

```java
class Animal {
}

class Dog extends Animal {
}

class Handler {
    String handle(Animal animal) {
        return "Handler: Animal";
    }

    String handle(Dog dog) {
        return "Handler: Dog";
    }
}

class SpecialHandler extends Handler {
    @Override
    String handle(Animal animal) {
        return "SpecialHandler: Animal";
    }

    @Override
    String handle(Dog dog) {
        return "SpecialHandler: Dog";
    }
}

public class OverloadOverrideDemo {
    public static void main(String[] args) {
        Handler handler = new SpecialHandler();
        Animal animal = new Dog();
        Dog dog = new Dog();

        System.out.println(handler.handle(animal));
        System.out.println(handler.handle(dog));
        System.out.println(handler.handle((Dog) animal));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 OverloadOverrideDemo.java
java OverloadOverrideDemo
```

**Stdout:**

```text
SpecialHandler: Animal
SpecialHandler: Dog
SpecialHandler: Dog
```

Phân tích từng dòng:

1. `handler.handle(animal)`: compiler thấy receiver có kiểu tĩnh `Handler`, đối số có kiểu tĩnh `Animal`, nên chọn **chữ ký `handle(Animal)`**. Khi chạy, receiver là đối tượng `SpecialHandler`, vì vậy triển khai override **`SpecialHandler.handle(Animal)`** được thực thi.
2. `handler.handle(dog)`: compiler thấy đối số kiểu tĩnh `Dog`, nên chọn chữ ký **`handle(Dog)`**. Runtime thực thi phiên bản override `SpecialHandler.handle(Dog)`.
3. `handler.handle((Dog) animal)`: cast khiến biểu thức đối số có kiểu tĩnh `Dog` và cast runtime thành công, nên chọn `handle(Dog)` và chạy phiên bản override tương ứng.

**Không diễn giải** dòng đầu thành “runtime chọn overload `handle(Animal)` vì đối tượng thật là `SpecialHandler`”. Phần chọn `Animal` đã xảy ra ở **compile time**; runtime chỉ quyết định triển khai override của **chữ ký đã chọn**.

### 8.2. Phương thức static không có dynamic dispatch

Xét các khai báo minh họa:

```java
class Base {
    static String label() {
        return "Base";
    }
}

class Derived extends Base {
    static String label() {
        return "Derived";
    }
}
```

Với:

```java
Base value = new Derived();
System.out.println(value.label());     // Base
System.out.println(Derived.label());   // Derived
```

`Derived.label` **hides** `Base.label` chứ không override động. Dù `value` tham chiếu đối tượng `Derived`, `value.label()` được ràng buộc theo kiểu tĩnh `Base`. Nên gọi static method qua **tên lớp** (`Base.label()`) để tránh nhầm.

Các ví dụ trong mục này là đoạn minh họa; không phải chương trình hoàn chỉnh có `main`. Một ứng dụng thực tế nên tránh gọi static method qua biến đối tượng.

## 9. Receiver kiểu cha có thể giới hạn cả tập overload nhìn thấy

Kiểu tĩnh của **receiver** cũng ảnh hưởng đến những phương thức mà compiler có thể xem xét.

Ví dụ:

```java
class ParentPrinter {
    void print(Object value) {
        System.out.println("Parent Object");
    }
}

class ChildPrinter extends ParentPrinter {
    void print(String value) {
        System.out.println("Child String");
    }
}
```

Trong mã gọi:

```java
ParentPrinter printer = new ChildPrinter();
printer.print("Hello");                // Parent Object
((ChildPrinter) printer).print("Hello"); // Child String
```

Giải thích:

- Biến `printer` có kiểu tĩnh `ParentPrinter`. Với biểu thức `printer.print("Hello")`, overload `print(String)` được khai báo riêng ở `ChildPrinter` **không có trong tập phương thức có thể truy cập qua kiểu `ParentPrinter`**. Compiler chọn `print(Object)`.
- `ChildPrinter` không override `print(Object)` trong ví dụ. Vì thế runtime vẫn thực thi `ParentPrinter.print(Object)`.
- Sau cast receiver thành `ChildPrinter`, compiler thấy cả `print(Object)` được kế thừa lẫn `print(String)` của lớp con và chọn `print(String)` cụ thể hơn cho đối số `"Hello"`.

**Không chỉ đối số, kiểu tĩnh của receiver cũng quan trọng.** Một lớp con có thêm overload mới không làm mọi biến kiểu lớp cha tự nhận biết overload mới đó.

## 10. Lựa chọn overload với các kiểu primitive cụ thể

Có thể hiểu những trường hợp thường gặp bằng quan hệ chuyển đổi primitive:

```text
byte  -> short -> int -> long -> float -> double
char  ------------> int -> long -> float -> double
```

Sơ đồ đơn giản này cho thấy một số đường **widening primitive**, không phải sơ đồ đầy đủ của tất cả chuyển đổi Java. Ví dụ `char` không tự chuyển sang `short`, và `boolean` không tham gia chuyển đổi số.

Nếu có:

```java
static void measure(long n) {
    System.out.println("long");
}

static void measure(double n) {
    System.out.println("double");
}
```

Thì `measure(1)` chọn `measure(long)` vì `long` cụ thể hơn `double` theo quy tắc liên quan trong nhóm overload có thể áp dụng.

Cần nhớ kiểu của literal:

- `1` có kiểu `int`.
- `1L` có kiểu `long`.
- `1.0` có kiểu `double`.
- `1.0f` có kiểu `float`.
- `'A'` có kiểu `char`.

Ví dụ lựa chọn với `int`/`long`:

```java
static void test(int number) {
    System.out.println("int");
}

static void test(long number) {
    System.out.println("long");
}

// test(1)    -> int
// test(1L)   -> long
// test('A')  -> int (char widening thành int)
```

Một overload có tham số `long` không thể tự nhận chuỗi `"1"`: chuyển `String` sang giá trị số cần API chuyển đổi hoặc logic rõ ràng.

### Biểu thức điều kiện và kiểu của biểu thức

Kiểu tĩnh có thể được suy ra từ **toàn bộ biểu thức**, không phải từ giá trị của riêng nhánh chạy thực tế. Ví dụ `boolean flag`, `Animal a` và `Dog d`:

```java
// inspect(flag ? d : a);
```

Nếu `inspect` được overload theo `Animal` và `Dog`, compiler sẽ xác định kiểu của biểu thức điều kiện `flag ? d : a` theo quy tắc kiểu của toán tử điều kiện cho các toán hạng tham chiếu. Khi kiểu biểu thức là `Animal`, overload `inspect(Animal)` được chọn **dù tại runtime cờ `flag` khiến biểu thức trả tham chiếu đến Dog**.

Không được chọn overload chỉ từ việc quan sát nhánh nào sẽ được thực thi trong một lần chạy.

## 11. Overloading, giá trị `null` và kiểu khai báo của biến

So sánh hai trường hợp:

**Trường hợp 1 — có quan hệ cha/con:**

```java
static void show(Object o) { System.out.println("Object"); }
static void show(String s) { System.out.println("String"); }

// show(null) -> String
```

`String` cụ thể hơn `Object`, nên literal `null` chọn overload `String`.

**Trường hợp 2 — không có quan hệ cha/con phù hợp:**

```java
static void show(String s) { System.out.println("String"); }
static void show(Integer i) { System.out.println("Integer"); }

// show(null) -> SAI: ambiguous
```

Trong cùng một lớp, không đặt hai trường hợp này trùng tên/chữ ký vào chung tệp khi thử nghiệm. Hai bộ khai báo trên là **hai ví dụ riêng**.

Nếu có một biến `Object item = "abc";` thì `show(item)` theo overload `show(Object)`/`show(String)` sẽ chọn **`show(Object)`**. Nếu cần một overload chuyên biệt, có thể kiểm tra và chuyển kiểu có chủ đích:

```java
if (item instanceof String text) {
    show(text);
}
```

Trong Java 17, pattern matching cho `instanceof` tạo biến `text` có kiểu tĩnh `String` trong nhánh phù hợp. Lúc đó overload `show(String)` được chọn. Cách này có ích khi thật sự cần xử lý các kiểu con khác nhau; tránh dùng cast khi chưa kiểm tra tính tương thích.

## 12. Kiểu trả về không điều khiển lựa chọn overload

Giả sử có hai overload hợp lệ:

```java
static Object load(Object key) {
    return "from Object";
}

static String load(String key) {
    return "from String";
}
```

Với:

```java
Object key = "id";
Object first = load(key);             // Chọn load(Object)
String second = load((String) key);  // Chọn load(String)
```

Loại overload được chọn dựa trên **kiểu biểu thức đối số**. Không được giả định rằng vì bên trái phép gán là `String` thì compiler sẽ chọn overload trả về `String`, bỏ qua sự phù hợp của tham số.

Đoạn sau **sai**:

```java
String text = load(key); // key có kiểu Object: chọn load(Object), trả về Object
```

Nó không thể gán trực tiếp `Object` sang `String` mà không có chuyển đổi phù hợp.

**Lưu ý nâng cao:** Java có *poly expressions* (ví dụ một số biểu thức lambda, method reference, generic method invocation) mà ngữ cảnh kiểu đích có thể tham gia suy luận kiểu. Điều đó **không thay đổi nguyên tắc chung** rằng không thể định nghĩa hai phương thức chỉ khác kiểu trả về hoặc chọn tùy ý một overload độc lập với chữ ký và quy tắc áp dụng. Hãy dùng ví dụ với biểu thức thông thường để xây nền trước khi học suy luận kiểu generic.

## 13. Generic và type erasure: hai tình huống liên quan

### 13.1. Kiểu tham số generic có thể gây trùng chữ ký sau erasure

Ví dụ không hợp lệ:

```java
// SAI khi khai báo cùng một lớp:
static void process(java.util.List<String> items) { }

static void process(java.util.List<Integer> items) { }
```

Do **type erasure**, cả hai có cùng dạng tham số `List` ở mức chữ ký bị xóa kiểu; Java không cho phép hai khai báo như vậy cùng tồn tại trong lớp.

Có thể đổi tên phương thức hoặc chọn kiểu API thể hiện rõ nhu cầu:

```java
static void processNames(java.util.List<String> names) { }

static void processNumbers(java.util.List<Integer> numbers) { }
```

Việc kiểu generic khác nhau **không phải lúc nào cũng** đủ để tạo overload hợp lệ.

### 13.2. Overload với generic có thể phụ thuộc suy luận kiểu

```java
static <T extends Number> String describe(T number) {
    return "Number generic";
}

static String describe(String text) {
    return "String";
}
```

Ở `describe(5)`, giá trị `int` có thể được boxing thành `Integer` và phù hợp với ràng buộc `T extends Number` nên overload generic có thể áp dụng; `describe("hello")` chọn overload `String` vì `String` không thỏa `T extends Number`.

Khi có lambda hoặc method reference, việc chọn overload có thể phức tạp hơn do tính tương thích của biểu thức với **functional interface** là một phần của phân tích tại compile time. Đừng cố đoán chỉ từ tên kiểu runtime của lambda; cần xét kiểu đích và quy tắc overload chính thức.

### 13.3. Lambda có thể làm lời gọi trở nên mơ hồ

Ví dụ minh họa, **không chạy độc lập**:

```java
static void use(java.util.function.Function<String, String> f) { }

static void use(java.util.function.Consumer<String> c) { }

// use(s -> s.trim()); // Có thể gây lựa chọn không như dự đoán;
// một lambda dạng biểu thức cần xét cả value-compatibility và void-compatibility.
```

Để diễn đạt rõ mục đích, truyền biểu thức lambda dưới kiểu functional interface cụ thể hoặc chọn tên API khác. Đối với học phần cơ bản, nên thành thạo trường hợp đối số là literal, biến, cast và varargs trước khi đi sâu vào overload resolution của lambda.

## 14. Các chuyển đổi thường gặp: bảng dự đoán kết quả

Bảng sau đưa ra một số trường hợp **độc lập**; mỗi hàng giả định **chỉ có các overload liệt kê trong hàng đó**, không trộn tất cả vào một lớp.

| Overload đang có | Lời gọi | Kết quả |
| --- | --- | --- |
| `f(int)`, `f(long)` | `f(1)` | `f(int)` — exact match |
| `f(int)`, `f(long)` | `f(1L)` | `f(long)` |
| `f(long)`, `f(Integer)` | `f(1)` | `f(long)` — widening ở giai đoạn strict |
| `f(Integer)`, `f(int...)` | `f(1)` | `f(Integer)` — boxing ở giai đoạn fixed arity trước variable arity |
| `f(int)`, `f(int...)` | `f(1)` | `f(int)` — fixed arity |
| `f(int)`, `f(int...)` | `f(1, 2)` | `f(int...)` |
| `f(Object)`, `f(String)` | `f("Hi")` | `f(String)` |
| `f(Object)`, `f(String)` | `f((Object) "Hi")` | `f(Object)` |
| `f(Object)`, `f(String)` | `f(null)` | `f(String)` |
| `f(String)`, `f(Integer)` | `f(null)` | Lỗi **ambiguous** |
| `f(String...)`, `f(Integer...)` | `f()` | Lỗi **ambiguous** |
| `f(long)` | `f(Integer.valueOf(2))` | `f(long)` qua unboxing rồi widening |
| `f(Long)` | `f(2)` | Lỗi: không có chuyển đổi `int → Long` phù hợp |

Bảng minh họa hướng xử lý cho các tình huống phổ biến, nhưng **không thay thế** thuật toán đầy đủ của Java Language Specification, nhất là khi phối hợp generic, inheritance, lambda hoặc nhiều mức biến đổi kiểu.

## 15. Các lỗi và cách chẩn đoán

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| “Sao `Animal a = new Dog(); f(a)` không chọn `f(Dog)`?” | Overload resolution dùng kiểu tĩnh `Animal` | Đọc kiểu khai báo của `a`; chỉ cast/kiểm tra kiểu khi đúng nhu cầu |
| “Sao object runtime là lớp con nhưng mã in từ lớp cha?” | Receiver chỉ nhìn thấy overload theo kiểu tĩnh; lớp con có thể chỉ thêm overload | Kiểm tra chữ ký đã chọn và xem có override đúng chữ ký đó không |
| “Sao `f(1)` chọn `f(long)` thay vì `f(Integer)`?” | Widening primitive được xét ở giai đoạn trước boxing | Xác định kiểu của literal `1` và thứ tự giai đoạn |
| “Sao `f(1)` chọn `f(Integer)` thay vì `f(int...)`?” | Boxing fixed arity được xét trước variable arity | Xét `...` như tham số mảng và nhận diện pha gọi |
| “Sao `f(null)` báo ambiguous?” | Hai overload tham chiếu không có quan hệ cụ thể nhất | Kiểm tra các kiểu tham số; dùng tên API khác hoặc cast có chủ đích |
| “Hai overload khác tên tham số nhưng compiler báo trùng?” | Chữ ký không tính tên tham số | Thay số lượng/thứ tự/kiểu tham số thực sự |
| “Hai overload khác kiểu trả về nhưng compiler báo trùng?” | Kiểu trả về không phải yếu tố phân biệt overload | Thiết kế chữ ký/tên phương thức khác |
| “`List<String>` và `List<Integer>` không overload được?” | Erasure dẫn đến xung đột chữ ký | Đổi tên API hoặc thêm kiểu tham số phân biệt hợp lệ |
| “Cast để gọi overload chuyên biệt lại ném `ClassCastException`?” | Cast chỉ hợp lệ lúc chạy nếu đối tượng tương thích | Dùng `instanceof` và kiểm tra dữ liệu |
| “Lời gọi `f(null)` vào `String...` xử lý mảng null?” | Biểu thức `null` có thể khớp `String[]` ở fixed arity | Viết rõ `(String[]) null` hoặc `(String) null` |
| “Thay kiểu của biến local nhưng giữ đối tượng, kết quả gọi lại đổi?” | Kiểu tĩnh của đối số đã thay đổi | Đây là hành vi dự kiến của overload resolution |
| “Đã chọn chữ ký đúng nhưng runtime in từ lớp con?” | Instance method bị override trong lớp receiver thực tế | Phân biệt bước chọn chữ ký và bước dynamic dispatch |

Để xử lý một lời gọi phức tạp, nên thực hiện các bước cụ thể: **ghi lại kiểu tĩnh của receiver**, **ghi lại kiểu tĩnh của từng đối số**, **liệt kê các overload nhìn thấy và có thể truy cập**, **xét các giai đoạn**, rồi **xác định có override động hay không**. Thói quen này giúp tránh suy luận dựa trên dữ liệu runtime một cách sai lệch.

## 16. Bài tập dự đoán đầu ra

### Bài 1 — Kiểu tĩnh của biến

Cho hai overload:

```java
static void print(Object value) {
    System.out.println("Object");
}

static void print(String value) {
    System.out.println("String");
}
```

Và mã gọi:

```java
Object a = "Xin chào";
String b = "Xin chào";
print(a);
print(b);
print((Object) b);
```

**Đáp án:**

```text
Object
String
Object
```

Ba đối số đều có thể biểu thị đối tượng chuỗi, nhưng kiểu tĩnh lần lượt là `Object`, `String`, `Object`. Do đó các overload được chọn khác nhau.

### Bài 2 — Widening so với boxing

Cho:

```java
static void process(long value) {
    System.out.println("long");
}

static void process(Integer value) {
    System.out.println("Integer");
}
```

Và:

```java
int primitive = 3;
Integer boxed = 3;
process(primitive);
process(boxed);
```

**Đáp án:**

```text
long
Integer
```

`primitive` có kiểu `int`, được widening sang `long` ngay ở giai đoạn strict. `boxed` có kiểu `Integer` nên khớp overload `Integer`.

### Bài 3 — Phân biệt overload và override

Giả sử có lớp `Base` và `Derived`:

```java
class Base {
    void run(Object value) {
        System.out.println("Base Object");
    }
}

class Derived extends Base {
    @Override
    void run(Object value) {
        System.out.println("Derived Object");
    }

    void run(String value) {
        System.out.println("Derived String");
    }
}
```

Mã gọi:

```java
Base receiver = new Derived();
receiver.run("A");
((Derived) receiver).run("A");
```

**Đáp án:**

```text
Derived Object
Derived String
```

Với `receiver.run("A")`, kiểu tĩnh của receiver chỉ có `run(Object)` nên chọn chữ ký đó; runtime chạy override của `Derived`. Với receiver được cast sang `Derived`, overload `run(String)` có thể được xét và cụ thể hơn.

### Bài 4 — `null` có mơ hồ không?

Cho:

```java
static void check(Object value) { }
static void check(String value) { }
```

`check(null)` **hợp lệ** và chọn `check(String)` vì `String` cụ thể hơn `Object`.

Nếu thay overload `check(Object)` bằng `check(Integer)`, `check(null)` sẽ **mơ hồ** vì `String` và `Integer` không có quan hệ subtype phù hợp.

### Bài 5 — Overload và varargs

Cho:

```java
static void total(int value) {
    System.out.println("one");
}

static void total(int... values) {
    System.out.println("many: " + values.length);
}
```

Các lời gọi:

```java
total(1);
total();
total(1, 2);
total(new int[]{1, 2, 3});
```

**Đáp án:**

```text
one
many: 0
many: 2
many: 3
```

`total(1)` ưu tiên overload fixed arity `int`; `total()` và `total(1, 2)` cần varargs mở rộng; `total(new int[]{1, 2, 3})` truyền một mảng có ba phần tử tới phương thức khai báo `int...`.

## 17. Một chương trình ôn tập tổng hợp

Lưu toàn bộ mã dưới đây vào tệp **`OverloadReview.java`**:

```java
class BaseItem {
}

class SpecialItem extends BaseItem {
}

class Printer {
    String print(BaseItem item) {
        return "base item";
    }

    String print(SpecialItem item) {
        return "special item";
    }
}

class FancyPrinter extends Printer {
    @Override
    String print(BaseItem item) {
        return "fancy base item";
    }
}

public class OverloadReview {
    static String number(long value) {
        return "long";
    }

    static String number(Integer value) {
        return "Integer";
    }

    static String number(int... values) {
        return "varargs(" + values.length + ")";
    }

    public static void main(String[] args) {
        Printer printer = new FancyPrinter();

        BaseItem base = new SpecialItem();
        SpecialItem special = new SpecialItem();

        System.out.println(printer.print(base));
        System.out.println(printer.print(special));
        System.out.println(printer.print((SpecialItem) base));

        int primitive = 3;
        Integer boxed = 3;
        System.out.println(number(primitive));
        System.out.println(number(boxed));
        System.out.println(number(1, 2));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 OverloadReview.java
java OverloadReview
```

Kết quả:

```text
fancy base item
special item
special item
long
Integer
varargs(2)
```

Giải thích:

- `Printer printer = new FancyPrinter()` giữ kiểu tĩnh receiver là `Printer` nhưng runtime receiver là `FancyPrinter`.
- `printer.print(base)` chọn chữ ký `print(BaseItem)` do `base` có kiểu tĩnh `BaseItem`; runtime chạy override của `FancyPrinter` → `fancy base item`.
- `printer.print(special)` chọn `print(SpecialItem)` do đối số kiểu tĩnh `SpecialItem`. Vì `FancyPrinter` không override chữ ký này, implementation kế thừa từ `Printer` chạy → `special item`.
- Cast `(SpecialItem) base` hợp lệ tại runtime ở ví dụ, khiến compiler chọn `print(SpecialItem)`.
- `number(primitive)` chọn `number(long)` qua widening ở giai đoạn strict.
- `number(boxed)` chọn overload `number(Integer)` với kiểu tĩnh chính xác.
- `number(1, 2)` cần lời gọi biến độ dài nên chọn `number(int...)`.

Tập trung vào **chữ ký chọn tại compile time**, sau đó mới xem **implementation override** có được quyết định ở runtime hay không. Đây là hai bước độc lập đủ để giải thích toàn bộ kết quả ở ví dụ.

## Checklist khi phân tích lựa chọn phương thức

1. **Xác định các khai báo có cùng tên** và xem chúng thực sự có chữ ký khác nhau hay không.
2. **Ghi kiểu tĩnh của receiver:** một biến kiểu cha có thể không nhìn thấy overload chỉ khai báo ở lớp con.
3. **Ghi kiểu tĩnh của mỗi biểu thức đối số:** literal, biến, cast, kết quả lời gọi và biểu thức điều kiện có thể mang kiểu khác nhau.
4. **Xét quyền truy cập và khả năng áp dụng** theo số lượng/kiểu tham số; không sử dụng kiểu thực tế runtime của đối tượng để đoán overload.
5. **Xét theo giai đoạn:** strict trước, loose có boxing/unboxing sau, variable arity cuối.
6. **Nếu có nhiều ứng viên cùng giai đoạn, xét most specific**; nhận ra lỗi ambiguous với các kiểu không có lựa chọn duy nhất.
7. **Không dùng kiểu trả về làm tiêu chí tùy ý** để phân biệt overload; không overload chỉ bằng tên tham số hoặc kiểu trả về.
8. **Sau khi xác định chữ ký, mới xét override động** nếu đó là instance method có thể override. Với static methods, không có dynamic dispatch.
9. **Kiểm tra các góc đặc biệt:** `null`, varargs nhận mảng trực tiếp, type erasure, cast và generic inference.
10. **Khi thiết kế API**, tránh nhiều overload gần nghĩa khiến lời gọi `null`, lambda hoặc số nguyên gây mơ hồ; tên phương thức rõ mục đích thường dễ bảo trì hơn.

Java không lựa chọn overload bằng cách “nhìn đối tượng là loại gì lúc chạy”. **Kiểu tại thời điểm biên dịch và quy tắc áp dụng** xác định chữ ký; **dispatch động** (nếu có) chỉ xác định implementation tương ứng với chữ ký đó.
