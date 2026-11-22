# `instanceof` với kiểu con và kiểu cha trong Java

## 1. Hiểu đúng câu hỏi: kiểm tra kiểu nào?

Trong Java, `instanceof` kiểm tra **đối tượng thực tế ở thời điểm chạy** có tương thích với một kiểu tham chiếu cho trước hay không. Đối tượng của lớp con cũng là đối tượng của mọi lớp cha trong chuỗi kế thừa của nó. Vì vậy, một đối tượng `Dog` thường thỏa cả `instanceof Dog` lẫn `instanceof Animal` nếu `Dog extends Animal`.

Có hai khái niệm phải phân biệt:

- **Kiểu khai báo (static/compile-time type):** kiểu của biến trong mã nguồn, ví dụ `Animal animal`. Compiler sử dụng kiểu này để kiểm tra cú pháp, quyền gọi phương thức và tính hợp lệ của phép kiểm tra.
- **Kiểu thực tế (runtime type):** lớp của đối tượng do `new` tạo ra, ví dụ `Dog` trong câu lệnh `Animal animal = new Dog("Milo");`. Đây là cơ sở để xác định kết quả `instanceof` khi chương trình chạy.

Ví dụ, với các lớp:

```text
Animal
├── Dog
│   └── Puppy
└── Cat
```

`Dog` và `Cat` là hai lớp con cùng cha; `Puppy` kế thừa gián tiếp `Animal` qua `Dog`. Quan hệ “là một” (IS-A) có tính bắc cầu: **Puppy là Dog, Dog là Animal, nên Puppy cũng là Animal**.

```java
Animal pet = new Dog("Milo");  // Upcasting: Dog -> Animal

System.out.println(pet instanceof Animal); // true
System.out.println(pet instanceof Dog);    // true
System.out.println(pet instanceof Cat);    // false
```

Ba biểu thức trên kiểm tra **cùng một đối tượng `Dog`**. Việc khai báo biến `pet` dưới kiểu `Animal` không biến đối tượng thành một `Animal` thuần, cũng không xóa thông tin kiểu con của nó.

## 2. Quy tắc với cha, con, cháu và lớp anh em

Giả sử:

```java
class Animal {}
class Dog extends Animal {}
class Puppy extends Dog {}
class Cat extends Animal {}
```

Bảng sau minh họa các phép kiểm tra hợp lệ trên **biến có kiểu tĩnh `Animal`**:

| Đối tượng được tham chiếu bởi biến `Animal a` | `a instanceof Animal` | `a instanceof Dog` | `a instanceof Puppy` | `a instanceof Cat` |
| --- | --- | --- | --- | --- |
| `new Animal()` | `true` | `false` | `false` | `false` |
| `new Dog()` | `true` | `true` | `false` | `false` |
| `new Puppy()` | `true` | `true` | `true` | `false` |
| `new Cat()` | `true` | `false` | `false` | `true` |
| `null` | `false` | `false` | `false` | `false` |

**Kiểm tra từ con lên cha:** nếu biến tham chiếu đến một đối tượng `Dog` không `null`, `instanceof Animal` cho `true`, vì đối tượng của lớp con mang đầy đủ quan hệ kế thừa tới lớp cha. Điều này vẫn đúng khi biến được khai báo là `Dog` hoặc `Object` và phép kiểm tra được compiler chấp nhận.

**Kiểm tra từ cha xuống con:** một biến khai báo kiểu `Animal` *có thể* tham chiếu tới `Dog`, `Puppy`, `Cat` hoặc `Animal` thuần. Vì vậy, `animal instanceof Dog` có thể là `true` hoặc `false` tùy đối tượng thực tế. Biến có kiểu cha không bảo đảm nó đang giữ một đối tượng của lớp con cụ thể.

**Kiểm tra giữa các lớp anh em:** đối tượng `Cat` không tự động là `Dog` chỉ vì hai lớp có chung lớp cha `Animal`. Nếu biểu thức có kiểu tĩnh `Animal`, phép kiểm tra `animal instanceof Dog` hoàn toàn hợp lệ và trả về `false` khi đối tượng thực tế là `Cat`.

**Trường hợp `null`:** `null instanceof Animal`, `null instanceof Dog` và các phép `instanceof` kiểm tra kiểu tham chiếu khác đều cho `false`. `null` có thể gán vào biến kiểu lớp, nhưng bản thân nó không phải đối tượng được tạo từ lớp đó.

## 3. Ví dụ Java 17+ chạy độc lập

Lưu toàn bộ chương trình vào file `InstanceofInheritanceDemo.java`:

```java
public class InstanceofInheritanceDemo {
    static class Animal {
        final String name;

        Animal(String name) {
            this.name = name;
        }

        String describe() {
            return "Animal " + name;
        }
    }

    static class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        String describe() {
            return "Dog " + name;
        }

        String play() {
            return name + " fetches";
        }
    }

    static class Puppy extends Dog {
        Puppy(String name) {
            super(name);
        }
    }

    static class Cat extends Animal {
        Cat(String name) {
            super(name);
        }
    }

    static void inspect(Animal animal) {
        String id = animal == null ? "null" : animal.name;

        System.out.println(
            id
                + ": Animal=" + (animal instanceof Animal)
                + ", Dog=" + (animal instanceof Dog)
                + ", Cat=" + (animal instanceof Cat)
        );

        if (animal instanceof Dog dog) {
            System.out.println("  " + dog.play());
        }
    }

    public static void main(String[] args) {
        inspect(new Dog("Milo"));
        inspect(new Animal("Base"));
        inspect(new Puppy("Nho"));
        inspect(new Cat("Mimi"));
        inspect(null);

        Animal x = new Dog("Milo");
        System.out.println("Describe: " + x.describe());
    }
}
```

Biên dịch và chạy từ thư mục chứa file bằng JDK 17 hoặc mới hơn:

```bash
javac --release 17 InstanceofInheritanceDemo.java
java InstanceofInheritanceDemo
```

Kết quả:

```text
Milo: Animal=true, Dog=true, Cat=false
  Milo fetches
Base: Animal=true, Dog=false, Cat=false
Nho: Animal=true, Dog=true, Cat=false
  Nho fetches
Mimi: Animal=true, Dog=false, Cat=true
null: Animal=false, Dog=false, Cat=false
Describe: Dog Milo
```

Giải thích từng trường hợp:

1. **`Milo`:** tham chiếu `Animal` trỏ tới một `Dog`. Nó thỏa pattern của `Dog` và `Animal` nhưng không phải `Cat`. Biến mẫu `dog` được khởi tạo và cho gọi `play()`.
2. **`Base`:** đối tượng thực sự được tạo từ `Animal`. Là `Animal` không đồng nghĩa với là `Dog`, nên chỉ phép kiểm tra với cha đúng.
3. **`Nho`:** đối tượng `Puppy` kế thừa từ `Dog`, nên `instanceof Dog` đúng, dù nó không được tạo trực tiếp bằng `new Dog(...)`. Nhánh gọi `play()` vẫn chạy vì phương thức được kế thừa.
4. **`Mimi`:** đối tượng `Cat` là `Animal`, nhưng không là `Dog`.
5. **`null`:** mọi phép kiểm tra kiểu ở đây đều trả về `false`.
6. **`Describe: Dog Milo`:** biến `x` khai báo là `Animal`, nhưng phương thức được override `describe()` được phân giải theo kiểu thực tế `Dog`. Đó là **đa hình khi chạy (dynamic dispatch)**; kết quả này nhất quán với `x instanceof Dog` là `true`.

Các khai báo `Animal`, `Dog`, `Puppy`, `Cat` trong các ví dụ ngắn dưới đây có thể hiểu là những lớp tương ứng trong chương trình này; những đoạn ngắn chỉ nhằm minh họa một quy tắc và không phải toàn bộ file độc lập.

## 4. Upcasting không làm mất kiểu thực tế

**Upcasting** là gán tham chiếu của đối tượng lớp con cho biến lớp cha. Java thực hiện việc này tự động vì mọi `Dog` đều là `Animal`:

```java
Dog dog = new Dog("Milo");
Animal animal = dog;   // Hợp lệ, không cần ép kiểu
Object object = dog;   // Hợp lệ vì các class Java kế thừa Object

System.out.println(animal instanceof Dog); // true
System.out.println(object instanceof Dog); // true
```

Cả ba biến có thể trỏ tới **chính một đối tượng**. `animal` chỉ thấy những thành viên được phép sử dụng qua kiểu `Animal` khi biên dịch; nhưng Java vẫn biết đối tượng thực tế là `Dog`. Vì thế, đoạn sau không biên dịch:

```java
Animal animal = new Dog("Milo");
animal.play(); // Lỗi biên dịch: Animal không khai báo play()
```

Để dùng hành vi riêng của `Dog`, cần kiểm tra kiểu và thu hẹp tham chiếu một cách hợp lệ.

## 5. Downcasting: kiểm tra trước khi ép kiểu

**Downcasting** chuyển một tham chiếu đang có kiểu tĩnh là cha về kiểu con. Nó chỉ thành công khi đối tượng thực tế tương thích với kiểu con được yêu cầu.

Cách truyền thống:

```java
Animal animal = new Dog("Milo");

if (animal instanceof Dog) {
    Dog dog = (Dog) animal; // An toàn sau kiểm tra
    System.out.println(dog.play());
}
```

Nếu bỏ kiểm tra và ép một `Animal` thuần hoặc `Cat` sang `Dog`, runtime sẽ ném `ClassCastException`:

```java
Animal animal = new Cat("Mimi");
Dog dog = (Dog) animal; // ClassCastException
```

Dù hai lớp `Dog` và `Cat` cùng kế thừa `Animal`, điều đó không làm phép chuyển từ một đối tượng `Cat` sang `Dog` trở nên hợp lệ. Một phép ép kiểu **không biến đổi đối tượng** thành một đối tượng mới: nó yêu cầu runtime xác minh rằng đối tượng đã tương thích với kiểu đích.

### Sử dụng type pattern từ Java 16 (ổn định trong Java 17)

```java
Animal animal = new Dog("Milo");

if (animal instanceof Dog dog) {
    System.out.println(dog.play());
}
```

`instanceof Dog dog` vừa kiểm tra kiểu, vừa khai báo và khởi tạo biến mẫu `dog` khi đối tượng khớp. Bên trong nhánh thành công, `dog` có kiểu `Dog`, nên gọi được `play()` mà không cần viết `(Dog) animal`.

Pattern variable chỉ dùng được trên các đường đi mà compiler bảo đảm pattern khớp:

```java
static void process(Animal animal) {
    if (!(animal instanceof Dog dog)) {
        return;
    }

    System.out.println(dog.play()); // Hợp lệ sau guard return
}
```

Nếu `animal` là `Cat`, `Animal` thuần hoặc `null`, điều kiện phủ định đúng và phương thức trả về sớm; chỉ các đối tượng `Dog` (kể cả `Puppy`) mới đến được dòng gọi `play()`.

Có thể ghép kiểm tra bổ sung một cách an toàn với `&&`:

```java
if (animal instanceof Dog dog && dog.name.startsWith("M")) {
    System.out.println(dog.play());
}
```

Vế phải của `&&` chỉ được đánh giá khi pattern ở vế trái khớp, do đó `dog` đã có giá trị. Ngược lại, viết `animal instanceof Dog dog || dog.name.startsWith("M")` không hợp lệ: vế phải `||` chỉ được đánh giá khi pattern bên trái không khớp.

## 6. Kiểu tĩnh quyết định phép `instanceof` nào hợp lệ khi biên dịch

Kết quả `true`/`false` phụ thuộc kiểu runtime, nhưng **không phải mọi phép so sánh đều được compiler cho phép**. Compiler dùng kiểu tĩnh và hệ thống kế thừa để loại trừ những kiểm tra không thể thành công.

Với hai lớp anh em `Dog` và `Cat`:

```java
Dog dog = new Dog("Milo");

// Không hợp lệ: một Dog không thể đồng thời là Cat
// System.out.println(dog instanceof Cat);
```

Trong ví dụ này, Java biết một đối tượng có kiểu `Dog` không thể là một đối tượng của `Cat`, bởi hai lớp nằm ở hai nhánh khác nhau của cây kế thừa (và không có quan hệ cha con). Phép kiểm tra kiểu không tương thích này bị từ chối ngay từ lúc biên dịch.

Khi thay bằng biến kiểu cha, phép kiểm tra trở nên hợp lệ:

```java
Animal animal = new Dog("Milo");
System.out.println(animal instanceof Cat); // false
```

Kiểu tĩnh `Animal` cho phép biến tham chiếu một `Cat` trong các lần gán khác, nên đây là phép kiểm tra có ý nghĩa tại runtime. Tuy nhiên, ở lần chạy cụ thể này biến đang trỏ tới `Dog`, vì vậy kết quả là `false`.

Cũng cần phân biệt **kiểm tra kiểu truyền thống** và **type pattern**. Trong Java 17, một type pattern được chứng minh luôn đúng chỉ dựa trên quan hệ kiểu tĩnh bị xem là thừa và dẫn tới lỗi biên dịch. Ví dụ:

```java
Dog directDog = new Dog("Milo");

System.out.println(directDog instanceof Animal); // Hợp lệ: true

// Trong Java 17, type pattern dưới đây bị từ chối là kiểm tra thừa:
// if (directDog instanceof Animal parent) {
//     System.out.println(parent.name);
// }
```

Lưu ý về phiên bản: quy tắc chính xác đối với các *unconditional patterns* có thay đổi trong các phiên bản Java mới hơn. Phân biệt này đặc biệt quan trọng khi biên dịch bằng `javac --release 17`. Cách rõ ràng nhất là dùng upcasting trực tiếp nếu bạn đã biết biến là `Dog`, và chỉ dùng `instanceof` khi cần phân nhánh theo kiểu thực tế.

## 7. So sánh với `getClass()` và toán tử `==`

`instanceof` kiểm tra **quan hệ tương thích kiểu**, kể cả lớp con nhiều cấp. `getClass()` trả về **lớp runtime chính xác**, vì vậy biểu thức so sánh lớp có ý nghĩa khác:

```java
Animal a = new Puppy("Nho");

System.out.println(a instanceof Animal);       // true
System.out.println(a instanceof Dog);          // true
System.out.println(a instanceof Puppy);        // true
System.out.println(a.getClass() == Dog.class);  // false
System.out.println(a.getClass() == Puppy.class);// true
```

`Puppy` là một `Dog` theo quan hệ kế thừa nhưng không có lớp runtime *chính xác* là `Dog`. Dùng `getClass() == Dog.class` khi yêu cầu chỉ chấp nhận đối tượng có đúng lớp `Dog`, không chấp nhận lớp con. Phương thức `getClass()` ném `NullPointerException` nếu gọi trên tham chiếu `null`, trong khi `null instanceof Dog` là `false`.

**Không dùng `==` giữa hai tham chiếu để kiểm tra quan hệ cha–con:** ví dụ `animal == dog` chỉ kiểm tra có cùng tham chiếu đối tượng hay không, không xác định kiểu của đối tượng.

## 8. Liên hệ với interface và cấu trúc kế thừa

`instanceof` không giới hạn ở lớp cha/lớp con trực tiếp. Nó cũng hỗ trợ interface: một đối tượng `Dog` có thể vừa là `Animal` theo kế thừa lớp vừa là `Trainable` qua việc hiện thực interface.

Ví dụ độc lập minh họa interface:

```java
interface Trainable {
    void train();
}

class Animal {}

class Dog extends Animal implements Trainable {
    @Override
    public void train() {
        System.out.println("Dog training");
    }
}
```

Với các kiểu trên:

```java
Animal animal = new Dog();

System.out.println(animal instanceof Animal);     // true
System.out.println(animal instanceof Dog);        // true
System.out.println(animal instanceof Trainable);  // true
```

Kiểu tĩnh `Animal` không cần tự khai báo `implements Trainable`. Đối tượng thực tế `Dog` có hiện thực interface, nên biểu thức vẫn trả về `true`. Đây là kiểm tra phù hợp khi cần xử lý một **khả năng** (capability) cụ thể được biểu diễn bằng interface.

Một đối tượng cũng có thể hiện thực nhiều interface; kiểm tra `instanceof` cho từng interface độc lập với quan hệ kế thừa class. Vì Java chỉ hỗ trợ đơn kế thừa class nhưng đa triển khai interface, điều này hữu ích khi một đối tượng cung cấp nhiều vai trò.

## 9. Khi nào nên dùng `instanceof`, khi nào nên dùng đa hình?

Nếu mục đích là gọi một hành vi mà **mọi lớp con đều phải có**, hãy cân nhắc khai báo hành vi đó ở lớp cha và cho lớp con override:

```java
Animal animal = new Dog("Milo");
System.out.println(animal.describe()); // Dog Milo
```

Đây là cách dùng đa hình: không cần kiểm tra tất cả lớp con để gọi `describe()`. Còn khi xử lý một thao tác **chỉ có ở lớp con** (ví dụ `play()` của `Dog`), kiểm tra `instanceof Dog dog` có thể hợp lý.

Một phương thức kiểm tra liên tiếp `instanceof Dog`, `instanceof Cat`, `instanceof Bird` để làm mọi công việc thường là tín hiệu cần xem lại thiết kế: nếu hành vi vốn là trách nhiệm chung, hãy cân nhắc chuyển nó thành phương thức đa hình hoặc một interface. Ngược lại, tại ranh giới nhận dữ liệu kiểu tổng quát (`Object`), trước thao tác ép kiểu, hoặc khi phải thích nghi với API hiện có, `instanceof` là công cụ đúng.

**Bảo toàn nguyên tắc:** hãy kiểm tra theo kiểu thể hiện *nhu cầu thực sự* của nhánh xử lý. Nếu chỉ cần hành vi của `Trainable`, kiểm tra `instanceof Trainable` thường linh hoạt hơn việc liệt kê một lớp con cụ thể.

## 10. Sai lầm thường gặp

1. **“Biến khai báo `Animal` thì `instanceof Dog` luôn sai.”** Sai: nếu biến chứa đối tượng `Dog` hoặc `Puppy`, phép kiểm tra `Dog` đúng.
2. **“Đối tượng lớp cha luôn là lớp con.”** Sai: `new Animal() instanceof Dog` là `false`. Quan hệ IS-A đi từ con tới cha, không tự đảo chiều.
3. **“Hai lớp cùng cha thì là cùng kiểu.”** Sai: `Dog` và `Cat` không có quan hệ kế thừa với nhau. Kiểu tĩnh cũng có thể khiến một phép kiểm tra giữa hai lớp này bị cấm khi biên dịch.
4. **“Ép kiểu sẽ biến `Cat` thành `Dog`.”** Sai: ép kiểu không thay đổi đối tượng. Ép sai kiểu có thể ném `ClassCastException`.
5. **“`instanceof` kiểm tra chính xác một lớp.”** Sai: nó cũng chấp nhận lớp con, chẳng hạn `new Puppy() instanceof Dog` là `true`. Muốn kiểm tra đúng class, dùng `getClass()`, có xử lý `null`.
6. **“Tham chiếu `null` thuộc lớp đã khai báo.”** Sai: `Animal a = null; a instanceof Animal` cho `false`.
7. **“Pattern variable có thể dùng ở mọi nhánh.”** Sai: chỉ dùng được nơi compiler chứng minh pattern đã khớp. Đừng sử dụng biến mẫu ở nhánh thất bại hoặc vế phải của `||` thiếu bảo đảm khớp.
8. **“`instanceof` thay thế toàn bộ đa hình.”** Không nên: nếu chỉ cần gọi phương thức chung của lớp cha, dynamic dispatch thường làm mã ngắn và dễ mở rộng hơn.

## 11. Tự kiểm tra nhanh

Cho cây kế thừa `Animal <- Dog <- Puppy` và `Cat extends Animal`:

**Câu 1.** `Animal a = new Puppy();`. Kết quả `a instanceof Animal`, `a instanceof Dog`, `a instanceof Puppy`, `a instanceof Cat` là gì?

Đáp án: lần lượt `true`, `true`, `true`, `false`. Đối tượng cháu giữ quan hệ với cả cha và ông, nhưng không thuộc nhánh `Cat`.

**Câu 2.** `Animal a = new Cat();`. Có thể viết `(Dog) a` và chạy thành công không?

Đáp án: phép ép có thể hợp lệ về cú pháp vì kiểu tĩnh `Animal` có thể chứa `Dog`, nhưng khi chạy sẽ ném `ClassCastException`, vì đối tượng thực tế là `Cat`. Phải kiểm tra `a instanceof Dog` trước.

**Câu 3.** `Animal a = null;`. Có cần kiểm tra `a != null` trước `a instanceof Dog` để tránh lỗi không?

Đáp án: không. `instanceof` với `null` tự trả về `false`. Tuy nhiên, nếu gọi `a.getClass()`, phải kiểm tra `null` trước.

**Câu 4.** `Animal a = new Puppy();`. Vì sao `a instanceof Dog` đúng nhưng `a.getClass() == Dog.class` sai?

Đáp án: phép đầu kiểm tra quan hệ kế thừa, phép sau đòi lớp runtime chính xác là `Dog`; lớp runtime ở đây là `Puppy`.

**Câu 5.** Có thể gọi `a.play()` nếu `a` khai báo kiểu `Animal` và thực tế trỏ tới `Dog` không?

Đáp án: không gọi trực tiếp được khi `Animal` không khai báo `play()`. Dùng `if (a instanceof Dog dog) { dog.play(); }` để compiler xác định kiểu `Dog` an toàn.

### Ghi nhớ

- **Con → cha:** một đối tượng lớp con không `null` luôn tương thích với kiểu cha trong chuỗi kế thừa.
- **Cha → con:** biến khai báo kiểu cha chỉ khớp với một kiểu con khi **đối tượng thực tế** thuộc kiểu con đó (hoặc lớp cháu của kiểu con).
- **Lớp anh em:** chung cha không có nghĩa các lớp là kiểu của nhau.
- **`null`:** mọi phép `instanceof` kiểu tham chiếu ở trên đều sai.
- **Pattern matching:** `instanceof Dog dog` vừa kiểm tra kiểu vừa giúp sử dụng biến `Dog` an toàn ở nhánh khớp.

### Tài liệu chính thức

- [JLS Java SE 17, §15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2)
- [JLS Java SE 17, §5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
