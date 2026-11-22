# `instanceof` với kiểu lớp cụ thể trong Java

## 1. `instanceof` kiểm tra điều gì khi đặt tên một lớp?

Trong Java, toán tử `instanceof` kiểm tra **đối tượng được tham chiếu ở thời điểm chạy** có phải là một thể hiện (*instance*) của lớp được chỉ định **hoặc một lớp con của lớp đó** hay không. Kết quả là `boolean`: `true` nếu quan hệ kiểu phù hợp, `false` nếu không.

Cú pháp kiểm tra lớp theo kiểu truyền thống:

```java
reference instanceof ClassName
```

Ví dụ, khi có lớp `Dog` và một biến tham chiếu `animal`:

```java
if (animal instanceof Dog) {
    // Đối tượng mà animal đang giữ là Dog hoặc lớp con của Dog.
}
```

Từ Java 16 (bao gồm Java 17+), có thể dùng **type pattern** để kiểm tra lớp và khai báo ngay một biến mang kiểu đó:

```java
if (animal instanceof Dog dog) {
    // dog có kiểu tĩnh Dog; không cần ép kiểu tường minh.
}
```

Ở đây `Dog` là **tên lớp cụ thể được yêu cầu kiểm tra**; `dog` là *pattern variable* chỉ dùng được ở những vị trí mà Java xác định phép thử đã khớp. Cả hai biểu thức đều kiểm tra quan hệ kiểu thực tế; cú pháp thứ hai giúp dùng thành viên của `Dog` gọn hơn.

Cần phân biệt hai khái niệm:

- **Kiểu khai báo (static/declared type)** của biến, ví dụ `Animal animal`, cho trình biên dịch biết những phép gọi nào hợp lệ.
- **Kiểu thực tế (runtime class)** của đối tượng, ví dụ `new Dog()`, quyết định kết quả của `instanceof`.

Một đối tượng vẫn có thể được kiểm tra thành `Dog` dù biến chứa nó được khai báo là `Object` hoặc lớp cha `Animal`. `instanceof` không kiểm tra chuỗi ký tự tên lớp và cũng không tạo đối tượng mới.

## 2. Quan hệ kế thừa: lớp con cũng là thể hiện của lớp cha

Xét các lớp sau (đây là **mảnh mã minh họa**, các lớp đầy đủ nằm trong chương trình chạy được ở mục 3):

```java
class Animal {}
class Dog extends Animal {}
class Poodle extends Dog {}
class Cat extends Animal {}
```

Khi đó:

```java
Animal pet = new Poodle();

pet instanceof Poodle  // true
pet instanceof Dog     // true
pet instanceof Animal  // true
pet instanceof Cat     // false
```

`Poodle` kế thừa `Dog`, `Dog` kế thừa `Animal`. Vì vậy một `Poodle` **đồng thời là** `Dog` và `Animal`. Nhưng `Cat` là nhánh kế thừa khác nên phép thử `Cat` thất bại.

| Đối tượng đang được tham chiếu | `instanceof Animal` | `instanceof Dog` | `instanceof Poodle` | `instanceof Cat` |
| --- | --- | --- | --- | --- |
| `new Animal()` | `true` | `false` | `false` | `false` |
| `new Dog()` | `true` | `true` | `false` | `false` |
| `new Poodle()` | `true` | `true` | `true` | `false` |
| `new Cat()` | `true` | `false` | `false` | `true` |
| `null` | `false` | `false` | `false` | `false` |

Những giá trị này được xét theo **đối tượng thật**, không chỉ theo tên kiểu ở bên trái dấu `=`. `instanceof` theo lớp bao gồm các lớp con gián tiếp; nó **không đòi hỏi trùng chính xác lớp tại runtime**.

Một lớp đích của `instanceof` cũng có thể là lớp `abstract`; điều cần kiểm tra là quan hệ kiểu của đối tượng thực tế. Trong tên bài này, “kiểu lớp cụ thể” là việc chỉ định một lớp như `Dog` hoặc `Cat` để kiểm tra, không có nghĩa rằng toán tử chỉ chấp nhận lớp `final` hay lớp có thể gọi `new`.

## 3. Ví dụ Java 17+ hoàn chỉnh: kiểm tra các lớp cụ thể

Lưu đúng tên tệp `ClassInstanceofDemo.java`:

```java
public class ClassInstanceofDemo {
    static class Animal {}

    static class Dog extends Animal {
        String sound() {
            return "woof";
        }
    }

    static final class Poodle extends Dog {}
    static final class Cat extends Animal {}

    static void describe(Animal animal) {
        if (animal instanceof Poodle poodle) {
            System.out.println("Poodle: " + poodle.sound());
        } else if (animal instanceof Dog dog) {
            System.out.println("Dog: " + dog.sound());
        } else if (animal instanceof Cat) {
            System.out.println("Cat");
        } else if (animal == null) {
            System.out.println("null");
        } else {
            System.out.println("Animal");
        }
    }

    public static void main(String[] args) {
        Animal dog = new Dog();
        Animal poodle = new Poodle();
        Animal cat = new Cat();

        System.out.println("dog is Dog: " + (dog instanceof Dog));
        System.out.println("dog is Poodle: " + (dog instanceof Poodle));
        System.out.println("poodle is Dog: " + (poodle instanceof Dog));
        System.out.println("poodle is Poodle: " + (poodle instanceof Poodle));
        System.out.println("cat is Dog: " + (cat instanceof Dog));

        System.out.println("poodle exact Dog: "
                + (poodle.getClass() == Dog.class));
        System.out.println("poodle exact Poodle: "
                + (poodle.getClass() == Poodle.class));

        describe(poodle);
        describe(dog);
        describe(cat);
        describe(new Animal());
        describe(null);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac ClassInstanceofDemo.java
java ClassInstanceofDemo
```

Kết quả chính xác:

```text
dog is Dog: true
dog is Poodle: false
poodle is Dog: true
poodle is Poodle: true
cat is Dog: false
poodle exact Dog: false
poodle exact Poodle: true
Poodle: woof
Dog: woof
Cat
Animal
null
```

**Giải thích các điểm then chốt:**

1. `dog` được khai báo `Animal` nhưng giữ `new Dog()`, nên `dog instanceof Dog` là `true`; nó không phải `Poodle` nên phép thử `Poodle` là `false`.
2. `poodle` được khai báo `Animal` nhưng giữ `new Poodle()`: `instanceof Dog` và `instanceof Poodle` đều đúng.
3. `cat` giữ `new Cat()`; hai lớp `Cat` và `Dog` cùng kế thừa `Animal` nhưng một `Cat` không phải `Dog`.
4. `poodle.getClass() == Dog.class` là `false` vì lớp chính xác của nó là `Poodle`, trong khi `poodle instanceof Dog` là `true`.
5. Trong chuỗi `if` / `else if`, **kiểm tra lớp con chuyên biệt `Poodle` trước lớp cha `Dog`**. Nếu kiểm tra `Dog` trước, `Poodle` sẽ khớp ngay nhánh `Dog` và không đi đến nhánh `Poodle`.
6. `null` không khớp với bất kỳ lớp nào qua `instanceof`; nhánh `animal == null` xử lý nó riêng.

Bài ví dụ sử dụng các lớp lồng `static` để có thể biên dịch ngay từ một tệp. Các lớp `Poodle` và `Cat` khai báo `final` vì ví dụ không yêu cầu kế thừa tiếp; yếu tố này **không ảnh hưởng** đến việc chúng là các lớp con của `Dog` hoặc `Animal`.

## 4. Kiểm tra trước khi ép kiểu xuống (downcast)

Một biến kiểu cha có thể giữ đối tượng lớp con:

```java
Animal animal = new Dog();
```

Nhưng kiểu tĩnh `Animal` không khai báo phương thức `sound()`, nên `animal.sound()` **không biên dịch được**, dù đối tượng thực tế là `Dog`. Muốn dùng API riêng của `Dog`, cần làm rõ kiểu cho trình biên dịch.

### 4.1. Cách truyền thống: `instanceof` rồi cast

Đoạn sau dùng các lớp đã khai báo ở mục 3, được đặt trong một phương thức hợp lệ:

```java
static void playSound(Animal animal) {
    if (animal instanceof Dog) {
        Dog dog = (Dog) animal;
        System.out.println(dog.sound());
    }
}
```

Phép cast `(Dog) animal` chỉ được thực hiện sau khi `instanceof Dog` đúng, nên không gây `ClassCastException` trong trường hợp kiểm tra đó. Nếu cast một `Cat` sang `Dog` mà không bảo đảm kiểu phù hợp, chương trình có thể ném `ClassCastException`.

### 4.2. Cách Java 17+: type pattern

```java
static void playSound(Animal animal) {
    if (animal instanceof Dog dog) {
        System.out.println(dog.sound());
    }
}
```

Biến `dog` có kiểu `Dog` và được khởi tạo khi đối tượng khớp. Cả `Dog` lẫn `Poodle` đều qua được phép thử này; phương thức `sound()` có thể được gọi trực tiếp, không cần cast.

Khi có điều kiện bổ sung, `&&` khai thác quy tắc **short-circuit**:

```java
if (animal instanceof Dog dog && dog.sound().equals("woof")) {
    System.out.println("A dog that says woof");
}
```

Vế phải chỉ chạy sau khi `Dog dog` đã khớp. Không thay `&&` bằng `||` ở đây, vì vế phải của `||` được đánh giá khi phép thử đầu sai; lúc đó biến `dog` không sẵn có.

Pattern variable có **flow scope**: ví dụ, bên ngoài `if` thông thường không thể gọi `dog.sound()` vì đường đi không khớp vẫn có thể tiếp tục. Trong một phương thức, nếu nhánh không khớp kết thúc bằng `return` hoặc `throw`, biến pattern có thể dùng sau `if` theo quy tắc *definitely matched*.

## 5. `instanceof` khác gì `getClass()` và `==`?

Ba phép so sánh này trả lời những câu hỏi khác nhau:

| Biểu thức | Ý nghĩa | Có tính lớp con không? |
| --- | --- | --- |
| `obj instanceof Dog` | `obj` có phải `Dog` hoặc lớp con của `Dog`? | **Có** |
| `obj.getClass() == Dog.class` | Lớp runtime của `obj` **chính xác** là `Dog`? | **Không** |
| `obj1 == obj2` | Hai tham chiếu có trỏ tới cùng một đối tượng (hoặc đều `null`)? | Không phải phép so kiểu |

Ví dụ:

```java
Animal animal = new Poodle();

System.out.println(animal instanceof Dog);           // true
System.out.println(animal.getClass() == Dog.class);  // false
System.out.println(animal.getClass() == Poodle.class); // true
```

Dùng `instanceof` khi muốn chấp nhận lớp đích **và các lớp con** để thực hiện xử lý tương thích. Chỉ dùng `getClass() == SomeClass.class` nếu thật sự cần phân biệt **đúng lớp runtime**, ví dụ một quy tắc xử lý đặc biệt không áp dụng cho subclass.

`getClass()` là lời gọi phương thức: `obj.getClass()` với `obj == null` sẽ ném `NullPointerException`. Ngược lại, `obj instanceof Dog` trả về `false` khi `obj == null`, không ném lỗi.

`instanceof` cũng không so sánh **bằng nhau về nội dung** của các đối tượng. Nếu cần so sánh giá trị, hãy xem hợp đồng `equals()` của lớp tương ứng.

## 6. Quy tắc biên dịch và trường hợp biên

### 6.1. Java loại bỏ phép kiểm tra kiểu chắc chắn không tương thích

Trình biên dịch kiểm tra xem kiểu tĩnh của toán hạng và kiểu lớp đích có **khả năng tương thích** theo quy tắc ép kiểu hay không. Ví dụ với hai lớp `final` không có quan hệ kế thừa, phép thử sau là lỗi biên dịch:

```java
String text = "hello";
// if (text instanceof Integer) { } // LỖI: hai lớp không tương thích

Object value = text;
System.out.println(value instanceof Integer); // false, nhưng hợp lệ
```

Với `Object value`, đối tượng tại runtime có thể thuộc nhiều lớp khác nhau, nên phép thử `Integer` hợp lệ và kết quả trong ví dụ là `false`. Nhưng `text` có kiểu tĩnh `String`, không có khả năng là `Integer` tại runtime.

Tương tự, trong Java 17, phép thử type pattern **dư thừa** có thể bị từ chối:

```java
String text = "hello";
// if (text instanceof String s) { } // LỖI trong Java 17
Object value = text;
if (value instanceof String s) {     // Hợp lệ
    System.out.println(s.length());  // 5
}
```

Vì `text` đã có kiểu tĩnh `String`, khai báo pattern `String s` trong trường hợp đó không mang lại phép kiểm tra hữu ích. Để kiểm tra chính xác kiểu của một biến `String`, không cần `instanceof`.

### 6.2. `null` và kiểu nguyên thủy

`null instanceof Dog` luôn `false` đối với `instanceof` kiểu tham chiếu trong Java 17; bất cứ tham chiếu nào đang là `null` cũng cho kết quả đó, kể cả khi được khai báo là `Dog`.

`instanceof` trong Java 17 áp dụng cho biểu thức có **kiểu tham chiếu**, không dùng trực tiếp với một giá trị nguyên thủy:

```java
int count = 5;
// System.out.println(count instanceof Integer); // LỖI trong Java 17

Object boxed = count; // Autoboxing thành Integer.
System.out.println(boxed instanceof Integer); // true
```

Việc một biến chứa giá trị nguyên thủy có thể được boxing thành đối tượng không làm thay đổi yêu cầu cú pháp của `instanceof`.

### 6.3. Lớp generic

Với một lớp generic, không thể yêu cầu `instanceof` kiểm tra một đối số kiểu không còn được biết chính xác ở runtime (do *type erasure*):

```java
Object value = new java.util.ArrayList<String>();

// if (value instanceof java.util.ArrayList<String>) { } // LỖI
if (value instanceof java.util.ArrayList<?> items) {
    System.out.println(items.size()); // 0
}
```

`ArrayList<?>` giúp kiểm tra **lớp thực tế** là `ArrayList` hoặc lớp con; nó không chứng minh rằng phần tử bên trong thuộc kiểu `String`. Dùng `instanceof` trên từng phần tử nếu cần kiểm tra kiểu phần tử.

### 6.4. Không cần dùng chuỗi `instanceof` khi đa hình đã đủ

Nếu hành vi thực sự tùy từng lớp con, thiết kế hướng đối tượng thường đặt phương thức ở lớp cha và override ở lớp con:

```java
abstract class Animal {
    abstract String sound();
}

class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}
```

Khi đó có thể gọi `animal.sound()` qua tham chiếu `Animal` mà không cần viết chuỗi `if (animal instanceof Dog) ...`. Ưu tiên đa hình khi bạn **kiểm soát các lớp** và các lớp nên tự cung cấp hành vi.

`instanceof` vẫn hữu ích ở ranh giới nhận `Object`, khi xử lý dữ liệu đầu vào không đồng nhất, ở adapter hoặc khi cần một thao tác riêng của một subclass mà API lớp cha không có.

## 7. Lỗi thường gặp

1. **Nhầm kiểu khai báo với kiểu runtime:** `Animal x = new Dog()` vẫn làm `x instanceof Dog` đúng.
2. **Cho rằng `instanceof Dog` chỉ khớp đúng `Dog`:** `new Poodle()` cũng khớp `Dog`; muốn đúng một lớp thì cân nhắc `getClass()`.
3. **Đặt kiểm tra lớp cha trước lớp con:** trong nhánh `else if`, `Dog` sẽ bắt cả `Poodle`; sắp xếp từ lớp chuyên biệt đến lớp tổng quát.
4. **Gọi phương thức chỉ có trên lớp con qua tham chiếu lớp cha:** phải dùng pattern variable, cast hợp lệ, hoặc đưa hành vi chung vào thiết kế đa hình.
5. **Cast mà không bảo đảm quan hệ kiểu:** một `Cat` không thể ép thành `Dog` tại runtime.
6. **Bỏ qua `null`:** `instanceof` trả `false`, còn `getClass()` ném ngoại lệ khi đối tượng `null`.
7. **Dùng `instanceof` với kiểu nguyên thủy hoặc đối số generic không kiểm tra được:** không hợp lệ trong Java 17.
8. **Dùng `==` để so kiểu hoặc so nội dung:** `==` giữa hai biến đối tượng so sánh tham chiếu, không kiểm tra quan hệ lớp và không thay `equals()`.

## 8. Bài tập tự luyện

1. Với `Animal`, `Dog`, `Poodle`, `Cat` ở mục 3, dự đoán kết quả `instanceof` cho biến `Animal x` lần lượt trỏ tới `new Dog()`, `new Poodle()`, `new Cat()` và `null`. Đối chiếu bằng bảng ở mục 2.
2. Đổi thứ tự `if (animal instanceof Poodle)` và `else if (animal instanceof Dog)` trong `describe`. Chạy với `new Poodle()` rồi giải thích vì sao nhánh kết quả thay đổi.
3. Viết phương thức `static String kind(Animal a)` trả `"dog"` nếu `a instanceof Dog`, `"cat"` nếu `a instanceof Cat`, và `"other"` nếu còn lại. Với `new Poodle()`, giá trị phải là `"dog"`.
4. Viết lại một đoạn kiểm tra `instanceof Dog` cộng cast `(Dog)` thành `instanceof Dog dog`. Nêu phạm vi dùng hợp lệ của `dog`.
5. So sánh `new Poodle()` bằng `instanceof Dog` và `getClass() == Dog.class`. Giải thích khi nào việc so đúng lớp runtime thực sự là yêu cầu nghiệp vụ.

**Ghi nhớ:** `instanceof` với tên lớp hỏi xem **đối tượng thật có thuộc lớp đó hoặc lớp con của nó hay không**. Nó đặc biệt hữu ích trước khi dùng hành vi riêng của lớp con qua biến kiểu cha; trong Java 17+, type pattern giúp kiểm tra và có biến đã được định kiểu trong cùng một biểu thức.

## Tham khảo

- [Java SE 17 — `instanceof` operator và pattern matching](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html).
- [Java Language Specification 17, §15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2).
- [OpenJDK JEP 394 — Pattern Matching for `instanceof`](https://openjdk.org/jeps/394).
