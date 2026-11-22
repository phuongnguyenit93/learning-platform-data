# Vì sao không thể khởi tạo trực tiếp lớp trừu tượng trong Java?

## 1. Trả lời trực tiếp

Trong Java, một lớp khai báo bằng từ khóa `abstract` **không được dùng trực tiếp ở vế phải của `new`**. Ví dụ, nếu `Animal` là lớp trừu tượng thì `new Animal()` gây **lỗi biên dịch**, ngay cả khi lớp đó có constructor và ngay cả khi lớp đó không khai báo phương thức `abstract` nào.

Lý do nằm ở **hợp đồng của kiểu dữ liệu**: lớp trừu tượng mô tả một kiểu chung, dành cho các lớp con kế thừa và hoàn thiện hành vi. Một lớp trừu tượng có thể chứa các phương thức chưa có phần thân, nên Java không cho phép tạo trực tiếp một đối tượng thuộc chính lớp đó. Quy tắc này được kiểm tra dựa trên khai báo `abstract`, chứ không phụ thuộc vào việc một lớp cụ thể có bao nhiêu phương thức trừu tượng.

Muốn có đối tượng, hãy tạo **một lớp con cụ thể (concrete class)** đáp ứng toàn bộ các phương thức trừu tượng còn thiếu. Biến tham chiếu vẫn có thể mang kiểu lớp trừu tượng:

```java
Animal pet = new Cat("Mimi"); // Hợp lệ nếu Cat là lớp con cụ thể của Animal
// Animal pet = new Animal("Mimi"); // Không hợp lệ: Animal là abstract
```

Ở dòng hợp lệ, **kiểu khai báo của biến** là `Animal`, nhưng **đối tượng thực sự được tạo** có kiểu `Cat`.

## 2. Điều gì xảy ra khi dùng `new` với lớp trừu tượng?

Giả sử ta có một khuôn mẫu chung cho các loài động vật:

```java
abstract class Animal {
    abstract String sound();
}

class InvalidExample {
    void demo() {
        Animal a = new Animal(); // Lỗi biên dịch
    }
}
```

Nếu lưu đoạn trên thành `InvalidExample.java` rồi chạy `javac InvalidExample.java`, trình biên dịch từ chối biểu thức `new Animal()` và thông báo theo ý nghĩa: `Animal is abstract; cannot be instantiated`.

Tại đây, `sound()` chỉ nêu **hành vi phải có** mà chưa quy định **hành vi cụ thể**. Nếu `new Animal()` được phép, không có phần cài đặt nào của `sound()` dành cho đối tượng thuộc chính lớp `Animal`. Vì vậy, thiết kế yêu cầu chương trình cung cấp một lớp con hoàn chỉnh trước khi tạo đối tượng.

Cần phân biệt hai mức:

- **Nguyên nhân trong ví dụ:** `Animal` chưa cài đặt `sound()`.
- **Quy tắc của ngôn ngữ:** mọi lớp được khai báo `abstract` đều không thể khởi tạo trực tiếp, kể cả khi tất cả phương thức đã có phần thân.

Đây là **lỗi tại thời điểm biên dịch** trong trường hợp viết trực tiếp `new Animal()`; chương trình không cần chạy đến dòng đó mới phát hiện lỗi.

## 3. Lớp trừu tượng không nhất thiết có phương thức trừu tượng

Điều dễ gây nhầm lẫn là từ khóa `abstract` tự nó đã đủ để cấm khởi tạo trực tiếp:

```java
abstract class BaseConfiguration {
    String environment() {
        return "production";
    }
}

class InvalidExample {
    void demo() {
        BaseConfiguration config = new BaseConfiguration(); // Vẫn lỗi biên dịch
    }
}
```

`BaseConfiguration` không có phương thức trừu tượng; tuy nhiên, người thiết kế vẫn muốn nó đóng vai trò **lớp nền để mở rộng**, không phải một kiểu được tạo độc lập. Khai báo `abstract` thể hiện chủ đích này và trình biên dịch thực thi đúng quy tắc.

Ngược lại, một lớp **không khai báo `abstract`** thì không được để lại phương thức trừu tượng chưa được cài đặt (trực tiếp hoặc kế thừa). Nếu còn hành vi bắt buộc chưa hoàn thiện, lớp con cũng phải tiếp tục được khai báo `abstract`.

## 4. Cách đúng: khởi tạo lớp con cụ thể

Ví dụ sau là chương trình Java độc lập, chạy được trên Java 17 trở lên. Lớp `Animal` đặt ra hợp đồng `sound()`; lớp `Cat` cài đặt hợp đồng ấy.

**Tệp `Main.java`:**

```java
abstract class Animal {
    private final String name;

    protected Animal(String name) {
        this.name = name;
        System.out.println("Animal constructor: " + name);
    }

    protected abstract String sound();

    public String introduce() {
        return name + " says " + sound();
    }
}

final class Cat extends Animal {
    Cat(String name) {
        super(name);
    }

    @Override
    protected String sound() {
        return "meow";
    }
}

public class Main {
    public static void main(String[] args) {
        Animal pet = new Cat("Mimi");

        System.out.println(pet.introduce());
        System.out.println(pet instanceof Cat);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Kết quả chuẩn trên stdout:**

```text
Animal constructor: Mimi
Mimi says meow
true
```

Phân tích từng điểm:

1. `new Cat("Mimi")` tạo **đối tượng `Cat`**, vì `Cat` không trừu tượng và đã cài đặt `sound()`.
2. `Animal pet` hoàn toàn hợp lệ: một tham chiếu kiểu cha có thể trỏ đến đối tượng kiểu con (đa hình).
3. Lệnh `pet.introduce()` gọi phương thức kế thừa từ `Animal`; lời gọi `sound()` bên trong được phân phối đến phiên bản của `Cat`, trả về `"meow"`.
4. Constructor `Animal(String)` vẫn chạy thông qua `super(name)` khi khởi tạo `Cat`. Dòng đầu tiên trên stdout chứng minh việc đó.
5. `pet instanceof Cat` trả về `true` vì kiểu thực tế của đối tượng là `Cat`.

Nếu bỏ phần cài đặt `sound()` trong `Cat` mà vẫn giữ `Cat` là lớp cụ thể, chương trình sẽ không biên dịch. Khi đó, phải cài đặt `sound()` hoặc khai báo `Cat` là `abstract` và tiếp tục để lớp con sau hoàn thiện.

## 5. Tại sao lớp trừu tượng vẫn có constructor?

Constructor của lớp trừu tượng khởi tạo phần trạng thái mà mọi lớp con chia sẻ. Khi tạo `new Cat("Mimi")`, Java gọi constructor `Animal` thông qua `super(name)`; điều đó không có nghĩa là một đối tượng `Animal` riêng được tạo ra, và cũng không làm `new Animal(...)` trở nên hợp lệ.

Constructor không được kế thừa và không thể khai báo `abstract`. Nếu lớp cha chỉ có constructor nhận tham số, constructor lớp con phải gọi một constructor tương ứng bằng `super(...)`; nếu không, lời gọi `super()` ngầm định có thể gây lỗi biên dịch. Quy tắc chọn access modifier, chuỗi `this(...)`/`super(...)` và thứ tự khởi tạo được trình bày đầy đủ trong bài về constructor.

## 6. Vì sao cú pháp `new Animal() { ... }` có thể hợp lệ?

Cú pháp có dấu ngoặc nhọn sau `new` tạo **lớp con vô danh (anonymous class)**. Nó không tạo đối tượng thuộc trực tiếp lớp `abstract`.

**Ví dụ độc lập khác, lưu lại dưới tên `Main.java`:**

```java
abstract class Action {
    abstract String execute();
}

public class Main {
    public static void main(String[] args) {
        Action action = new Action() {
            @Override
            String execute() {
                return "Action completed";
            }
        };

        System.out.println(action.execute());
    }
}
```

Chạy `javac -encoding UTF-8 Main.java` rồi `java Main` sẽ in:

```text
Action completed
```

Biểu thức `new Action() { ... }` khai báo ngay tại chỗ một lớp con vô danh kế thừa `Action`, cài đặt `execute()`, sau đó tạo đối tượng của **lớp con vô danh** ấy. Nếu không cài đặt đủ phương thức trừu tượng còn thiếu, biểu thức này cũng không biên dịch.

Vì vậy, hai biểu thức trông gần giống nhau nhưng có ý nghĩa khác nhau:

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `new Action()` | Lỗi biên dịch | Cố tạo trực tiếp lớp trừu tượng |
| `new Action() { /* cài đặt đầy đủ */ }` | Hợp lệ | Tạo lớp con vô danh cụ thể rồi khởi tạo nó |
| `new ConcreteAction()` | Hợp lệ nếu lớp con cụ thể và constructor truy cập được | Tạo đối tượng lớp con có tên |

Lớp con vô danh hữu ích cho triển khai ngắn tại một vị trí. Khi hành vi lớn, cần tái sử dụng hoặc có nhiều phụ thuộc, một lớp con có tên thường dễ đọc và kiểm thử hơn.

## 7. Cơ chế thiết kế và các trường hợp cần phân biệt

**Lớp trừu tượng là kiểu có thể sử dụng trong khai báo, nhưng không là đích khởi tạo trực tiếp.** Java cho phép dùng lớp trừu tượng làm kiểu của biến, tham số, kiểu trả về, trường dữ liệu và phần tử của mảng. Chẳng hạn, một phương thức có thể nhận `Animal` để xử lý mọi lớp con mà không phụ thuộc vào `Cat`, `Dog` hay một triển khai cụ thể nào.

Một số trường hợp thường gây nhầm lẫn:

| Tình huống | Hợp lệ? | Lý do |
| --- | --- | --- |
| `Animal a;` | Có | Chỉ khai báo tham chiếu, chưa tạo đối tượng |
| `Animal a = null;` | Có | `null` không phải đối tượng của lớp trừu tượng |
| `Animal a = new Cat("Mimi");` | Có | Đối tượng được tạo thuộc lớp con cụ thể |
| `Animal[] animals = new Animal[3];` | Có | Tạo một **mảng chứa tham chiếu** kiểu `Animal`, không tạo ba đối tượng `Animal` |
| `new Animal("Mimi")` | Không | Khởi tạo trực tiếp lớp được khai báo `abstract` |
| `new Cat("Mimi")` khi `Cat` chưa cài đặt đủ phương thức trừu tượng | Không, nếu `Cat` bị buộc phải là lớp trừu tượng | Lớp con chưa đủ điều kiện để khởi tạo |

Có thể hình dung lớp trừu tượng như một **hợp đồng kèm phần triển khai dùng chung**. Hợp đồng cho biết mọi lớp con cụ thể phải cung cấp những hành vi nào; phần triển khai dùng chung tránh lặp mã. Các đối tượng thực tế mang kiểu của những lớp con đáp ứng hợp đồng.

Tính trừu tượng cũng có thể dùng để **ngăn tạo lớp nền** ngay cả khi mọi hành vi đã được cài đặt. Vì thế, lời giải thích “vì còn phương thức thiếu phần thân” nêu một động cơ phổ biến, nhưng **không phải điều kiện cần** để một lớp được khai báo `abstract`.

### Những lỗi phổ biến

- **Nhầm “không tạo được đối tượng” với “không khai báo được biến”.** `Animal pet` hợp lệ; chính `new Animal()` mới bị cấm.
- **Tưởng thêm constructor công khai sẽ cho phép `new`.** Quyền truy cập constructor và quy tắc `abstract` là hai kiểm tra khác nhau; constructor `public` không biến lớp trừu tượng thành lớp cụ thể.
- **Tưởng mọi lớp con đều có thể khởi tạo.** Chỉ lớp con cụ thể đã thực hiện đủ hợp đồng trừu tượng và có constructor phù hợp mới được tạo đối tượng.
- **Tưởng lớp cha trừu tượng không có constructor.** Constructor của lớp cha vẫn được gọi trong quá trình tạo đối tượng lớp con.
- **Tưởng `new AbstractType() { ... }` phá quy tắc.** Đây là cách định nghĩa và tạo một lớp con vô danh cụ thể; lớp cha vẫn không được khởi tạo trực tiếp.
- **Tưởng một lớp chỉ trừu tượng khi có phương thức `abstract`.** Người viết có thể đánh dấu lớp `abstract` để quy định cách sử dụng, bất kể lớp ấy có phương thức trừu tượng hay không.

## 8. Cách tự kiểm tra khi gặp lỗi

Khi thấy lỗi gần với `SomeType is abstract; cannot be instantiated`, hãy lần lượt xem:

1. **Kiểu ngay sau `new` là gì?** Nếu là lớp `abstract` hoặc interface, không thể dùng `new SomeType()` trực tiếp.
2. **Có lớp con cụ thể phù hợp chưa?** Nếu có, dùng `new ConcreteSubtype(...)` rồi giữ biến tham chiếu kiểu cha nếu cần tính đa hình.
3. **Lớp con đã cài đặt đủ các phương thức trừu tượng chưa?** Kiểm tra cả phương thức nhận từ cha và các interface, chữ ký phương thức, kiểu trả về và mức truy cập khi override.
4. **Constructor lớp con có gọi được constructor lớp cha không?** Nếu lớp cha yêu cầu tham số, hãy truyền qua `super(...)`.
5. **Chỉ cần một triển khai ngắn tại chỗ?** Cân nhắc lớp con vô danh, nhưng vẫn phải cài đặt đầy đủ hành vi trừu tượng.

**Ghi nhớ:** `abstract` mô tả kiểu cha và quy định rằng không được khởi tạo trực tiếp kiểu ấy. Đối tượng phải thuộc một lớp con cụ thể; constructor và phương thức dùng chung của lớp trừu tượng vẫn có vai trò đầy đủ trong quá trình khởi tạo và thực thi.
