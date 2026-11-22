# Downcast compatibility trong pattern của Java

## 1. “Downcast compatibility” là điều kiện gì?

Khi viết `value instanceof Dog dog`, Java phải trả lời **hai câu hỏi khác nhau**:

1. **Lúc biên dịch:** xét **kiểu tĩnh** của biểu thức `value` và **kiểu đích** `Dog`, phép kiểm tra này có hợp lệ về mặt hệ thống kiểu không?
2. **Lúc chạy:** giá trị mà `value` đang tham chiếu có thật sự là một đối tượng tương thích với `Dog` hay không? Nếu có, Java khởi tạo pattern variable `dog` và điều kiện trả về `true`; nếu không, điều kiện trả về `false`.

Câu hỏi thứ nhất chính là chủ đề **downcast compatibility** trong cú pháp pattern của Java. Nó là bộ lọc ở **compile time**, không phải sự bảo đảm rằng biểu thức `instanceof` sẽ trả về `true`.

Trong **Java 17**, [JLS §14.30.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1) quy định biểu thức `e` tương thích với type pattern kiểu `T` nếu `e` **downcast compatible** với `T` theo [JLS §5.5](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5). Có thể hiểu thực dụng: compiler phải tìm thấy một phép chuyển kiểu tham chiếu phù hợp, trong đó **không phải dựa vào một phép narrowing reference conversion unchecked**. Quy tắc này cho phép kiểm tra kiểu có ý nghĩa, nhưng ngăn những trường hợp chắc chắn không tương thích hoặc yêu cầu giả định generic type argument mà runtime không thể kiểm chứng.

Tên gọi “downcast compatible” **không có nghĩa** pattern chỉ được viết từ biến lớp cha sang lớp con. Hệ thống kiểu còn xét class, interface, mảng, generic và những chuyển kiểu tham chiếu khác. Riêng với `instanceof` type pattern, Java 17 còn có một quy tắc bổ sung: pattern hiển nhiên đúng chỉ dựa trên kiểu tĩnh có thể bị từ chối vì **kiểm tra thừa**.

Từ **Java 21**, JLS §14.30.3 mô tả type pattern có thể áp dụng (*applicable*) ở kiểu `T` khi `T` **checked cast convertible** tới kiểu của pattern. Java 21 cũng hỗ trợ record pattern và pattern trong `switch`. Vì vậy khi đọc tài liệu nhiều phiên bản, cần đối chiếu đúng thuật ngữ và quy tắc của phiên bản đang biên dịch; các ví dụ `instanceof` cơ bản trong bài dùng Java 17, các record pattern dùng Java 21.

## 2. Phân biệt khả năng chuyển kiểu, phép match và ép kiểu tường minh

Xét hệ phân cấp:

```text
Animal
├── Dog
└── Cat
```

Và khai báo:

```java
class Animal {}
class Dog extends Animal {}
class Cat extends Animal {}
```

Với biến kiểu tĩnh `Animal`:

```java
Animal animal = new Dog();

if (animal instanceof Dog dog) {
    System.out.println("Matched Dog");
}
```

Compiler **chấp nhận** phép kiểm tra vì một tham chiếu kiểu `Animal` hoàn toàn có thể chứa một đối tượng `Dog`. Khi chương trình chạy, đối tượng thực tế đúng là `Dog`, pattern khớp và biến `dog` được khởi tạo.

Đổi đối tượng thành `new Cat()`:

```java
Animal animal = new Cat();

if (animal instanceof Dog dog) {
    // Không vào nhánh này.
}
```

Mã vẫn **biên dịch hợp lệ** vì kiểu tĩnh vẫn là `Animal`; nhưng ở lần chạy này pattern không khớp, nên `dog` không được khởi tạo để sử dụng trong nhánh thành công.

Với ép kiểu tường minh:

```java
Animal animal = new Cat();

// Dog dog = (Dog) animal; // Biên dịch được, nhưng chạy sẽ ném ClassCastException.
```

`(Dog) animal` yêu cầu runtime thực hiện cast và có thể ném `ClassCastException`. Còn `animal instanceof Dog dog` kiểm tra trước; nếu không khớp thì trả về `false` và không chạy thân `if`, nên bản thân phép kiểm tra không gây `ClassCastException` do kiểu đối tượng không phù hợp.

| Khái niệm | Xác định khi nào? | Ví dụ `Animal animal = new Cat();` |
| --- | --- | --- |
| Pattern có tương thích với kiểu tĩnh không? | Compile time | `animal instanceof Dog dog` hợp lệ |
| Giá trị có match type pattern không? | Runtime | `false` vì đối tượng là `Cat` |
| Pattern variable có được gắn giá trị không? | Khi runtime match thành công | Không có `dog` khả dụng |
| Cast tường minh có thành công không? | Có thể cần kiểm tra runtime | `(Dog) animal` ném `ClassCastException` |

**Điểm mấu chốt:** *được phép kiểm tra* khác với *kiểm tra thành công*; pattern là kiểm tra có điều kiện, còn ép kiểu tường minh có thể thất bại bằng ngoại lệ.

## 3. Các trường hợp compiler cho phép hoặc từ chối

### 3.1. Từ kiểu cha xuống kiểu con: hợp lệ nếu có thể xảy ra

```java
Object source = "Java";

if (source instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

`Object` có thể giữ tham chiếu tới `String`. Mặc dù không phải mọi `Object` là `String`, biểu thức có ý nghĩa và hợp lệ. Đây là ví dụ quen thuộc nhất của kiểu kiểm tra có tính “downcast”.

Tương tự, `Animal` có thể giữ `Dog`, và một `Animal` có thể chứa đối tượng cháu của `Dog`; pattern `Dog dog` vẫn khớp với đối tượng cháu vì quan hệ kế thừa có tính bắc cầu.

### 3.2. Hai kiểu lớp đã chắc chắn tách biệt: lỗi compile time

```java
String input = "Java";

// SAI: String và Integer là hai class final, không có đối tượng chung.
// if (input instanceof Integer number) {
//     System.out.println(number);
// }
```

`String` là `final` và không phải `Integer`, nên compiler chứng minh không thể có đối tượng nào vừa là `String` vừa là `Integer`. Ở đây Java **không** cho thực hiện phép kiểm tra rồi trả về `false`; nó từ chối cú pháp ngay khi biên dịch.

Cần xét cả **kiểu tĩnh của biểu thức**, không chỉ đoán giá trị runtime. Nếu khai báo biến là `Object`, phép kiểm tra `obj instanceof Integer number` hợp lệ vì một `Object` bất kỳ có thể là `Integer`.

### 3.3. Hai lớp anh em không có chung đối tượng

```java
class Animal {}
class Dog extends Animal {}
class Cat extends Animal {}

Dog dog = new Dog();

// SAI: không có quan hệ subclass/superclass giữa Dog và Cat.
// if (dog instanceof Cat cat) { }
```

Với biến kiểu tĩnh `Dog`, phép kiểm tra `Cat` không hợp lệ. Nhưng nếu biến có kiểu tĩnh `Animal`, phép kiểm tra đó hợp lệ:

```java
Animal animal = new Dog();

if (animal instanceof Cat cat) {
    // Hợp lệ về cú pháp, nhưng lần chạy này không match.
}
```

Do đó không thể kết luận chỉ bằng việc “đối tượng thực tế là `Dog`”. **Compiler dùng kiểu tĩnh** để quyết định liệu phép kiểm tra có thể xảy ra trong một tình huống khác hay không.

### 3.4. Kiểm tra thừa với `instanceof` type pattern

```java
String value = "Java";

System.out.println(value instanceof Object); // true (type test truyền thống)

// SAI trong Java 17: type pattern Object obj chắc chắn khớp mọi String khác null.
// if (value instanceof Object obj) {
//     System.out.println(obj);
// }
```

Java 17 không cho dùng type pattern `Object obj` trong tình huống mà kiểu tĩnh `String` đã là subtype của kiểu pattern, vì đây là kiểm tra pattern thừa theo quy tắc của `instanceof`. Việc `String` có thể chuyển thành `Object` **không có nghĩa** mọi cú pháp pattern đều hợp lệ.

**Cách sửa:** nếu đã biết kiểu tĩnh và muốn một biến kiểu cha, gán trực tiếp: `Object obj = value;`. Nếu cần phân nhánh theo kiểu con thực sự, dùng biến có kiểu tĩnh rộng hơn, chẳng hạn `Object input`, rồi kiểm tra `input instanceof String text`.

## 4. Interface: có khi không triển khai trực tiếp vẫn tương thích

Java cho phép một lớp **không final** được kế thừa bởi lớp mới mà lớp mới đó hiện thực thêm interface. Vì thế, kiểm tra với interface có thể hợp lệ dù lớp cha chưa trực tiếp `implements` interface.

```java
interface Tagged {}

class OpenBase {}

class TaggedChild extends OpenBase implements Tagged {}

OpenBase value = new TaggedChild();

if (value instanceof Tagged tag) {
    System.out.println("Tagged"); // Tagged
}
```

Compiler cho phép vì một đối tượng thuộc subclass của `OpenBase` có thể đồng thời hiện thực `Tagged`; ở ví dụ trên nó đúng là `TaggedChild`.

Ngược lại, nếu một class **final** không hiện thực interface, không có subclass nào có thể thêm interface đó:

```java
interface Tagged {}
final class FixedBase {}

FixedBase value = new FixedBase();

// SAI: FixedBase final và không implements Tagged.
// if (value instanceof Tagged tag) { }
```

Tại Java 17, quy tắc về các kiểu **disjoint** cũng xét quan hệ `sealed` và danh sách lớp/interface được phép kế thừa. Vì thế, đừng suy ra chỉ từ việc “class này không `implements` interface” rằng luôn có lỗi; cần xét khả năng có subclass hợp lệ.

**Ứng dụng:** khi xử lý một vai trò hành vi (ví dụ `Runnable`), `value instanceof Runnable runnable` thường đúng mục đích hơn việc kiểm tra tất cả concrete class có thể triển khai vai trò đó.

## 5. Generic type và lý do phải tránh unchecked narrowing

Đây là điểm dễ hiểu sai nhất khi nói về **downcast compatibility**.

### 5.1. Không thể đoán `List<String>` từ một `Object`

```java
Object value = java.util.List.of("Java");

// SAI: từ Object, không thể kiểm tra an toàn type argument String.
// if (value instanceof java.util.List<String> strings) {
//     System.out.println(strings.get(0));
// }
```

Generic type argument của `List<String>` không được giữ đầy đủ để kiểm tra ở runtime (type erasure). Từ kiểu tĩnh `Object`, yêu cầu kiểm tra trực tiếp `List<String>` cần dựa vào narrowing reference conversion **unchecked**; không phải điều kiện hợp lệ để viết type pattern `List<String> strings` trong trường hợp này.

Có thể kiểm tra một kiểu **reifiable** với wildcard:

```java
Object value = java.util.List.of("Java");

if (value instanceof java.util.List<?> elements) {
    System.out.println(elements.size()); // 1
}
```

Ở đây `List<?>` xác nhận giá trị runtime là một `List`, không khẳng định kiểu của từng phần tử. Để sử dụng phần tử như `String`, kiểm tra riêng:

```java
if (value instanceof java.util.List<?> elements
        && !elements.isEmpty()
        && elements.get(0) instanceof String first) {
    System.out.println(first.toUpperCase()); // JAVA
}
```

Vế phải `&&` an toàn vì các phép kiểm tra trước đó đã khớp. Dù phần tử đầu là `String`, điều đó **không chứng minh mọi phần tử của List đều là String**.

### 5.2. Một số type pattern có tham số generic vẫn hợp lệ

```java
java.util.List<Integer> numbers =
        new java.util.ArrayList<>(java.util.List.of(2, 4));

if (numbers instanceof java.util.ArrayList<Integer> actual) {
    System.out.println(actual.get(0)); // 2
}
```

Đoạn trên hợp lệ trong Java 17. Vì `numbers` **đã có kiểu tĩnh `List<Integer>`**, compiler có thể chấp nhận checked narrowing từ `List<Integer>` sang `ArrayList<Integer>`. Kiểm tra runtime xác nhận đây là `ArrayList`; sự nhất quán của type argument `Integer` đã được xác lập trong hệ thống kiểu tĩnh, chứ JVM không kiểm tra từng phần tử là `Integer` trong phép `instanceof`.

So sánh:

| Kiểu tĩnh của biểu thức | Kiểu pattern | Hợp lệ? | Giải thích |
| --- | --- | --- | --- |
| `Object` | `String text` | Có | Có thể cast có kiểm tra sang String |
| `Animal` | `Dog dog` | Có | Animal có thể trỏ tới Dog |
| `String` | `Integer n` | Không | Hai kiểu final không có đối tượng chung |
| `Object` | `List<?> xs` | Có | Kiểm tra được bản thân List |
| `Object` | `List<String> xs` | Không | Cần narrowing unchecked về generic type |
| `List<Integer>` | `ArrayList<Integer> xs` | Có | Type argument đã tương thích từ kiểu tĩnh |
| `String` | `Object obj` | Không với type pattern Java 17 | Kiểm tra pattern thừa vì kiểu tĩnh là subtype |

**Không nên suy diễn** rằng mọi generic pattern đều bị cấm. Điều quan trọng là **cặp kiểu nguồn–đích** có chuyển kiểu checked được ngôn ngữ chấp nhận hay không.

## 6. `null` và sự khác biệt giữa cast với pattern

Với `null`, Java phân biệt rõ phép cast tường minh và phép `instanceof`:

```java
Object value = null;

System.out.println(value instanceof String); // false

if (value instanceof String text) {
    // Không chạy; text không được khởi tạo từ null.
}

String casted = (String) value; // Hợp lệ, casted vẫn là null.
```

Phép ép `(String) null` thành công và trả về `null`. Trái lại, `null` **không match type pattern `String text`** trong `instanceof`. Kết quả `false` này không gây lỗi và cũng không gán `null` vào `text` để dùng ở nhánh thành công.

Đây là một ví dụ sắc nét cho thấy:

- **Tính hợp lệ về kiểu khi biên dịch** không quyết định giá trị pattern có match hay không.
- **Casting có thể chấp nhận null**, nhưng **type pattern của `instanceof` từ chối match với null**.
- Không cần viết `value != null && value instanceof String text` chỉ để tránh `NullPointerException`: toán tử `instanceof` đã an toàn với `null`.

Với record pattern Java 21 (ở mục sau), một record chứa component `null` có thể làm **component type pattern** không match, ngay cả khi bản thân đối tượng record là non-null.

## 7. Java 17: chương trình chạy độc lập minh họa đầy đủ

Lưu chương trình sau vào file **`DowncastPatternDemo.java`**:

```java
public class DowncastPatternDemo {
    static class Animal {
        final String name;

        Animal(String name) {
            this.name = name;
        }
    }

    static final class Dog extends Animal implements Runnable {
        Dog(String name) {
            super(name);
        }

        String bark() {
            return "woof";
        }

        @Override
        public void run() {
            // Demo cho khả năng thực thi Runnable.
        }
    }

    static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }
    }

    static String describe(Animal value) {
        if (value instanceof Dog dog) {
            return "Dog:" + dog.name + ":" + dog.bark();
        }

        if (value instanceof Cat cat) {
            return "Cat:" + cat.name;
        }

        return value == null ? "null" : "Animal:" + value.name;
    }

    public static void main(String[] args) {
        Animal[] animals = {
            new Dog("Rex"),
            new Cat("Miu"),
            new Animal("Base"),
            null
        };

        for (Animal a : animals) {
            System.out.println(describe(a));
        }

        Animal pet = new Dog("Rex");
        if (pet instanceof Runnable runnable) {
            System.out.println("implements Runnable=" + (runnable != null));
        }

        java.util.List<Integer> numbers =
            new java.util.ArrayList<>(java.util.List.of(2, 4));

        if (numbers instanceof java.util.ArrayList<Integer> values) {
            System.out.println("first=" + values.get(0));
        }

        Object any = java.util.List.of("x");
        if (any instanceof java.util.List<?> items) {
            System.out.println("size=" + items.size());
        }

        Object other = "text";
        System.out.println("other is Dog=" + (other instanceof Dog));
    }
}
```

Dùng **JDK 17+** để biên dịch và chạy:

```bash
javac --release 17 DowncastPatternDemo.java
java DowncastPatternDemo
```

Đầu ra:

```text
Dog:Rex:woof
Cat:Miu
Animal:Base
null
implements Runnable=true
first=2
size=1
other is Dog=false
```

Giải thích:

1. Với `new Dog("Rex")`, `Animal` có thể downcast sang `Dog` và giá trị thực tế khớp, nên in `Dog:Rex:woof`.
2. Với `new Cat("Miu")`, pattern `Dog dog` **hợp lệ nhưng không khớp**; pattern `Cat cat` khớp.
3. Với `new Animal("Base")`, cả hai pattern kiểu con không khớp; code xử lý kiểu cha.
4. Với `null`, type pattern không khớp nên nhánh cuối trả chuỗi `"null"`.
5. Dù `pet` khai báo là `Animal`, đối tượng runtime `Dog` thực hiện `Runnable`, nên pattern interface hợp lệ và khớp.
6. Với `List<Integer>` sang `ArrayList<Integer>`, compiler có đủ thông tin generic để chấp nhận pattern cụ thể; đối tượng thực tế là `ArrayList` nên in phần tử đầu `2`.
7. Với `Object any`, pattern `List<?>` kiểm tra được `List` ở runtime và cho `size=1`.
8. `Object other` đang giữ `String`, nên pattern `Dog` hợp lệ về mặt kiểu nguồn `Object` nhưng cho `false` khi chạy.

Ví dụ này sử dụng các type pattern của `instanceof` đã chính thức từ Java 16; `--release 17` đủ và không cần `--enable-preview`.

## 8. Java 21+: record pattern có kiểm tra tương thích theo từng thành phần

Java 21 mở rộng pattern matching bằng **record pattern** và pattern trong `switch`. Ngoài tương thích giữa kiểu selector và kiểu record, compiler còn xét pattern của từng record component so với kiểu component được khai báo.

Ví dụ, record `Envelope(Object content)` có component tĩnh kiểu `Object`. Pattern `Envelope(String text)` có thể áp dụng vì component `Object` có thể chứa `String`:

```java
record Envelope(Object content) {}

Object input = new Envelope("Java");

if (input instanceof Envelope(String text)) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

Đây là **mã minh họa trong ngữ cảnh có khai báo `Envelope`**, yêu cầu Java 21+. Đầu tiên, runtime kiểm tra `input` có phải `Envelope` không; sau đó lấy component và kiểm tra component có phải `String` không. Chỉ khi **tất cả phần liên quan khớp**, pattern toàn phần mới thành công và `text` mới dùng được.

Ví dụ đầy đủ để chạy: lưu thành **`PatternRecordDemo.java`**.

```java
public class PatternRecordDemo {
    record Envelope(Object content) {}

    static String inspect(Object input) {
        return switch (input) {
            case Envelope(String text) -> "text:" + text;
            case Envelope(Integer number) -> "number:" + number;
            case null -> "null input";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect(new Envelope("Java")));
        System.out.println(inspect(new Envelope(7)));
        System.out.println(inspect(new Envelope(null)));
        System.out.println(inspect(null));
    }
}
```

Biên dịch/chạy bằng **JDK 21+**:

```bash
javac --release 21 PatternRecordDemo.java
java PatternRecordDemo
```

Đầu ra:

```text
text:Java
number:7
other
null input
```

Chú ý sự khác biệt:

- `new Envelope("Java")` match record pattern chứa `String text`.
- `new Envelope(7)` match record pattern chứa `Integer number`.
- `new Envelope(null)` là **một record không null**, nhưng component `null` không match type pattern `String` hoặc `Integer`, nên vào `default`.
- `null` không phải record; được xử lý riêng bởi `case null`.

Các nhánh `switch` pattern còn có quy tắc **dominance**: một `case` tổng quát có thể làm `case` cụ thể phía sau không thể đạt tới. Ví dụ nếu đặt `case Object obj` trước `case String text` mà cả hai đều áp dụng cho cùng kiểu selector, nhánh `String` bị bao phủ và compiler báo lỗi. Điều đó là một quy tắc khác với downcast compatibility: **một pattern riêng lẻ có thể có kiểu hợp lệ nhưng vị trí của nó trong `switch` không hợp lệ**.

Khi chỉ viết Java 17, dùng `instanceof` type pattern; không sử dụng cú pháp record pattern hoặc `case String s when ...` vì chúng chưa là tính năng chính thức ở phiên bản đó.

## 9. Kiểm tra thực tế: ba tầng quyết định

Khi gặp một câu lệnh pattern khó hiểu, hãy kiểm tra theo trình tự:

**Tầng 1 — Kiểu tĩnh của biểu thức.** Ví dụ với `Object x`, pattern `String s` có thể hợp lệ; với `String x`, pattern `Integer n` là kiểm tra bất khả thi và bị cấm. Generic argument, tính `final`, quan hệ `sealed` và interface cũng có thể tác động tới quyết định này.

**Tầng 2 — Pattern có áp dụng được và có phạm quy tắc bổ sung không.** Java 17 loại những `instanceof` type pattern thừa dù chuyển kiểu đến supertype được phép. Java 21 kiểm tra applicability cho record/component patterns và dominance của các nhánh `switch`.

**Tầng 3 — Giá trị runtime có match không.** Đối tượng có thể đúng kiểu con, sai kiểu con hoặc `null`. Nếu type pattern không khớp, phép `instanceof` trả `false`; nếu khớp, pattern variable được khởi tạo và Java cho phép dùng trên những đường đi compiler chứng minh match thành công.

Bảng quyết định ngắn:

| Trường hợp | Compile time | Runtime |
| --- | --- | --- |
| `Animal a = new Dog(); a instanceof Dog d` | Hợp lệ | `true`, có `d` |
| `Animal a = new Cat(); a instanceof Dog d` | Hợp lệ | `false` |
| `Object x = "abc"; x instanceof String s` | Hợp lệ | `true`, có `s` |
| `Object x = null; x instanceof String s` | Hợp lệ | `false` |
| `String x = "abc"; x instanceof Integer n` | Lỗi | Không chạy |
| `Object x = List.of("a"); x instanceof List<String> xs` | Lỗi | Không chạy |
| `Object x = List.of("a"); x instanceof List<?> xs` | Hợp lệ | `true` |
| `String x = "abc"; x instanceof Object o` | Lỗi type pattern thừa (Java 17) | Không chạy |

## 10. Lỗi phổ biến và cách tránh

**Lỗi 1: Đồng nhất `cast được` với `match đúng`.** `Animal` có thể cast sang `Dog` nhưng một đối tượng `Cat` thực tế không phải `Dog`. Hãy tách kiểm tra lúc biên dịch khỏi kiểm tra runtime.

**Lỗi 2: Tưởng mọi phép `instanceof` sai kiểu sẽ chỉ trả `false`.** Với các kiểu static đã bị chứng minh không thể có đối tượng chung, Java từ chối ở compile time. Muốn kiểm tra một giá trị thật sự có nhiều khả năng kiểu, hãy giữ nó dưới kiểu nguồn phù hợp (như `Object` hoặc interface chung).

**Lỗi 3: Dùng `instanceof List<String>` từ biến `Object`.** Generic argument không được runtime kiểm tra đầy đủ. Dùng `List<?>`, kiểm tra từng phần tử khi cần và giữ kiểu generic tĩnh an toàn từ đầu quy trình.

**Lỗi 4: Nhầm `null` với cast thất bại.** `(Dog) null` cho `null`; `null instanceof Dog dog` trả `false`. Type pattern không gắn biến với `null`.

**Lỗi 5: Quên quy tắc pattern thừa.** Java 17 cho phép `"abc" instanceof Object` dưới dạng type comparison, nhưng không cho `"abc" instanceof Object obj` dưới dạng type pattern.

**Lỗi 6: Bỏ qua tính `final`/`sealed` và interface.** Kiểu class bình thường có thể có subclass implement interface; class final không thể. Tính tương thích phải xét khả năng có một loại đối tượng chung.

**Lỗi 7: Cố dùng biến mẫu ở nhánh pattern không khớp.** Pattern variable `dog` chỉ hợp lệ trong scope mà compiler chứng minh pattern đã khớp. Hãy dùng `if (x instanceof Dog dog)` và thao tác với `dog` trong nhánh đúng, hoặc guard clause loại nhánh không khớp bằng `return`.

**Lỗi 8: Trộn quy tắc Java 17 và Java 21.** Java 17 có type pattern cho `instanceof`; Java 21 chính thức hỗ trợ record pattern và pattern trong `switch`. Hãy biên dịch bằng đúng mức `--release` cần dùng.

## 11. Câu hỏi luyện tập

**Câu 1.** Có đoạn `Animal a = new Cat(); if (a instanceof Dog d) ...`. Nó lỗi biên dịch hay cho `false`?

*Đáp án:* Biên dịch hợp lệ, trả `false` khi chạy. Kiểu tĩnh `Animal` có thể chứa `Dog`, nhưng đối tượng thực tế lần này là `Cat`.

**Câu 2.** Với `String s = "x";`, vì sao `s instanceof Object` có thể hợp lệ, còn `s instanceof Object obj` trong Java 17 lại lỗi?

*Đáp án:* Biểu thức thứ nhất là kiểm tra kiểu truyền thống. Biểu thức thứ hai dùng type pattern bị xem là thừa do `String` đã là subtype của `Object`.

**Câu 3.** `Object x = List.of("x");`. Làm thế nào kiểm tra `x` là một `List` hợp lệ?

*Đáp án:* Dùng `x instanceof List<?> values`. Không khẳng định `List<String>` chỉ từ runtime check trên `Object`; nếu cần phần tử là `String`, kiểm tra phần tử riêng.

**Câu 4.** `Object x = null;`. Kết quả của `x instanceof Dog dog` và `(Dog) x` khác nhau thế nào?

*Đáp án:* `instanceof` trả `false` và không có `dog`; cast trả về `null` (không ném `ClassCastException` cho giá trị `null`).

**Câu 5.** Trong Java 21, `record Box(Object value) {}`, pattern `Box(String s)` có áp dụng được cho một biến kiểu `Object` không? Nếu box chứa `Integer` thì sao?

*Đáp án:* Có: kiểu `Object` có thể kiểm tra thành `Box`, và component `Object` có thể kiểm tra thành `String`. Nếu component runtime là `Integer`, record pattern không khớp; biến `s` không được bind.

## 12. Checklist khi áp dụng vào dự án

1. Xác định **kiểu tĩnh** của giá trị đang kiểm tra.
2. Xác định **kiểu pattern đích**, đặc biệt quan hệ class/interface và generic arguments.
3. Xem chuyển kiểu có **checked** hay cần **unchecked narrowing** hoặc bị chứng minh là bất khả thi.
4. Kiểm tra quy tắc riêng của cấu trúc (`instanceof` pattern thừa, `switch` dominance, record component).
5. Xử lý riêng giá trị `null` và dự liệu nhánh runtime không match.
6. Chỉ dùng pattern variable trong luồng mà pattern đã match.
7. Biên dịch với phiên bản Java mục tiêu (`--release 17` hoặc `--release 21`).

**Ghi nhớ:** *Downcast compatibility/applicability quyết định liệu pattern được phép kiểm tra; matching quyết định liệu đối tượng thực tế khớp; flow scoping quyết định nơi có thể sử dụng biến được bind.* Ba tầng này giải thích phần lớn lỗi với `instanceof` type pattern, generic và record pattern.

### Tài liệu chính thức

- [Java SE 17 JLS §14.30.1 — Kinds of Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1)
- [Java SE 17 JLS §5.5 — Casting Contexts (Downcast Compatible)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5)
- [Java SE 17 JLS §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [Java SE 21 JLS §14.30.3 — Properties of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
