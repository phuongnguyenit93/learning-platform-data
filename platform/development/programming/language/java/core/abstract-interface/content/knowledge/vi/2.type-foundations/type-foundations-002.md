# Quan hệ kiểu cha và kiểu con trong Java

Trong Java, **kiểu con (subtype)** có thể được dùng ở nơi API yêu cầu kiểu cha (supertype). Quan hệ này tạo nền tảng cho đa hình và thiết kế API linh hoạt. Cần phân biệt quan hệ kiểu với quan hệ kế thừa giữa hai lớp: một interface cũng có thể là supertype dù không phải superclass.

## 1. Subclass khác subtype như thế nào?

Giả sử `Dog extends Animal`:

- `Dog` là **subclass** của `Animal`; `Animal` là superclass.
- `Dog` cũng là **subtype** của `Animal`; `Animal` là supertype.
- Nếu `Animal implements CanMove`, thì `Dog` cũng là subtype của `CanMove` thông qua quan hệ kế thừa. `CanMove` không trở thành superclass của `Dog`.
- Quan hệ subtype có tính bắc cầu: nếu `Poodle extends Dog` và `Dog extends Animal`, thì `Poodle` là subtype của `Animal`.

Một lớp không khai báo `extends` trực tiếp sẽ có `Object` làm superclass (ngoại trừ chính `Object`). Interface không phải subclass của `Object`, nhưng một đối tượng của lớp triển khai interface vẫn có thể được gán cho biến `Object`. Kiểu nguyên thủy như `int` không thuộc hệ phân cấp class/interface; boxing là cơ chế chuyển đổi riêng.

**“Is-a” và “has-a” trả lời hai câu hỏi khác nhau.** `Dog extends Animal` diễn tả Dog là một Animal. `Car` giữ trường `Engine engine` diễn tả Car có một Engine; nó không làm `Car` thành subtype của `Engine`. Chỉ dùng kế thừa khi hành vi công khai của kiểu cha còn đúng với kiểu con.

## 2. Những khai báo tạo quan hệ kiểu

| Khai báo | Quan hệ | Giới hạn chính |
|---|---|---|
| `class Dog extends Animal` | `Dog` là subtype của `Animal`. | Một class chỉ có một superclass trực tiếp. |
| `class Dog implements CanMove, Named` | `Dog` là subtype của cả hai interface. | Class cụ thể phải đáp ứng các abstract method còn thiếu. |
| `interface Smart extends CanMove, Named` | `Smart` kế thừa hợp đồng của nhiều interface. | Interface dùng `extends`, không dùng `implements`. |
| `abstract class Animal implements CanMove` | `Animal` là subtype của `CanMove`. | Vì `Animal` abstract, nó có thể chuyển tiếp nghĩa vụ triển khai cho lớp con. |
| `final class Dog extends Animal` | Vẫn là subtype của `Animal`. | `final` ngăn tạo subclass mới của `Dog`. |

Trong Java 17+, `sealed` class/interface có thể giới hạn các subtype trực tiếp được phép khai báo. Những giới hạn đó không thay đổi ý nghĩa cơ bản của quan hệ subtype.

## 3. Ví dụ chạy được: nhiều kiểu con, một hợp đồng

Lưu toàn bộ mã sau thành `TypeRelationDemo.java`:

```java
public class TypeRelationDemo {
    interface CanMove {
        void move();
    }

    static abstract class Animal implements CanMove {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }

        abstract String sound();

        @Override
        public void move() {
            System.out.println(name + " moves");
        }
    }

    static final class Dog extends Animal {
        Dog(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "woof";
        }

        void fetch() {
            System.out.println(name() + " fetches");
        }
    }

    static final class Cat extends Animal {
        Cat(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "meow";
        }
    }

    static void describe(Animal animal) {
        System.out.println(animal.name() + ": " + animal.sound());
    }

    public static void main(String[] args) {
        Dog rex = new Dog("Rex");

        Animal animal = rex;
        CanMove mover = rex;
        Object any = rex;

        describe(animal);
        mover.move();
        System.out.println(animal instanceof Dog);

        if (animal instanceof Dog dog) {
            dog.fetch();
        }

        Animal other = new Cat("Mimi");
        describe(other);
        System.out.println(any.getClass().getSimpleName());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac TypeRelationDemo.java
java TypeRelationDemo
```

Stdout:

```text
Rex: woof
Rex moves
true
Rex fetches
Mimi: meow
Dog
```

`animal`, `mover` và `any` cùng tham chiếu một đối tượng `Dog`; upcast không sao chép đối tượng. `describe(Animal)` dùng được với cả `Dog` và `Cat`. Biến `animal` không công bố phương thức `fetch()`, nên cần kiểm tra kiểu trước khi dùng khả năng riêng của `Dog`. Phần phân giải chi tiết giữa kiểu khai báo, lớp runtime, overload và field được giải thích ở bài **Kiểu tham chiếu và kiểu thực tế của đối tượng**.

## 4. Tương thích kiểu và tính thay thế về hành vi

Gán `Dog` cho biến `Animal` hoặc `CanMove` là **upcasting** ngầm định nhờ quan hệ subtype; các biến vẫn tham chiếu cùng object. Chiều ngược lại là **downcasting**: kiểu biểu thức hẹp hơn nhưng không đổi object. Phải kiểm tra kiểu thực tế, chẳng hạn `candidate instanceof Dog dog`, trước khi dùng `dog.fetch()` khi không chắc `candidate` là `Dog`; cast sai có thể ném `ClassCastException`. `instanceof` trả `false` với `null`.

**Compiler chấp nhận phép gán chưa bảo đảm tính thay thế hành vi.** Theo nguyên tắc Liskov (LSP), chương trình dùng supertype phải tiếp tục hoạt động theo các cam kết của supertype khi nhận subtype. Lớp con không nên siết điều kiện đầu vào đã được cha chấp nhận, phá bất biến hoặc từ chối thao tác mà hợp đồng cha bảo đảm. Nếu `CanMove.move()` hứa di chuyển hợp lệ, một implementation luôn ném `UnsupportedOperationException` vi phạm kỳ vọng đó. Hãy chỉ cho những đối tượng thực sự có khả năng di chuyển triển khai `CanMove`.

Do đó, cần kiểm tra **hai tầng**: quan hệ subtype ở mức ngôn ngữ và khả năng giữ đúng hợp đồng ở mức thiết kế, kiểm thử.

## 5. Subtype không tự động truyền qua generic

Có `Dog extends Animal` **không** có nghĩa `List<Dog>` là subtype của `List<Animal>`. Generic Java thường bất biến:

```java
java.util.List<Dog> dogs = java.util.List.of(new Dog("Rex"));
// java.util.List<Animal> animals = dogs; // Lỗi biên dịch

java.util.List<? extends Animal> view = dogs;
Animal first = view.get(0); // Đọc an toàn như Animal
// view.add(new Dog("Max")); // Không thêm Dog tùy ý được
```

`? extends Animal` cho phép đọc phần tử dưới dạng `Animal`, nhưng kiểu con thực tế của danh sách chưa biết; nó có thể là `List<Cat>`. Khi API cần **tiêu thụ** giá trị `Dog`, `? super Dog` có thể phù hợp hơn. Chọn wildcard theo chiều dữ liệu vào/ra thay vì cố ép hai loại `List` thành cùng kiểu.

Mảng Java có tính covariant nhưng việc ghi phần tử được kiểm tra lúc chạy:

```java
Animal[] animals = new Dog[1];  // Hợp lệ khi biên dịch
animals[0] = new Cat("Mimi");  // ArrayStoreException lúc chạy
```

Vì vậy, quan hệ giữa kiểu phần tử, kiểu container và an toàn runtime là các vấn đề riêng. Đừng suy từ `Dog <: Animal` rằng mọi cấu trúc chứa `Dog` đều gán được cho cấu trúc chứa `Animal`.

## 6. Chọn supertype cho API

Ưu tiên kiểu trừu tượng nhỏ nhất đáp ứng nhu cầu của caller:

- Dùng `CanMove` nếu hàm chỉ cần gọi `move()`, để cả `Animal`, `Robot` hoặc lớp không cùng cây kế thừa đều có thể tham gia.
- Dùng `Animal` khi thật sự cần những thuộc tính/hành vi chung của họ động vật.
- Dùng class cụ thể như `Dog` chỉ khi nghiệp vụ cần khả năng riêng như `fetch()`.

Composition phù hợp khi quan hệ là “có một” hoặc “ủy quyền cho”, chẳng hạn `Car` chứa `Engine`. Kế thừa phù hợp khi quan hệ “là một” có ý nghĩa và subtype giữ đúng hợp đồng của supertype. Không nên kế thừa chỉ để lấy một phương thức tiện ích.

## 7. Các ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| Interface được triển khai là superclass. | Nó là supertype, nhưng superclass chỉ là lớp trong nhánh `extends`. |
| Hai lớp cùng superclass có thể gán trực tiếp cho nhau. | `Dog` và `Cat` đều là `Animal`, nhưng không phải subtype của nhau. |
| Upcast tạo một đối tượng lớp cha mới. | Các biến sau upcast có thể cùng tham chiếu một instance ban đầu. |
| `instanceof` thay thế đa hình. | Override dùng dispatch tự động; `instanceof` là kiểm tra kiểu khi cần rẽ nhánh. |
| `List<Dog>` có thể dùng như `List<Animal>`. | Generic bất biến; dùng wildcard thích hợp. |
| Kế thừa cú pháp đủ chứng minh thiết kế đúng. | Subtype còn phải giữ các cam kết hành vi của supertype. |

## 8. Tự kiểm tra

1. Nếu `Dog extends Animal` và `Animal implements CanMove`, `Dog` có thể gán cho `CanMove` không? **Có**, vì quan hệ subtype bắc cầu.
2. `Dog` và `Cat` cùng kế thừa `Animal`; có thể gán trực tiếp `Dog` cho biến `Cat` không? **Không**, hai nhánh không có quan hệ subtype đó.
3. Vì sao `List<Dog>` không gán được cho `List<Animal>`? **Vì generic invariant**; nếu cho phép, code có thể thêm `Cat` vào danh sách vốn chỉ nhận `Dog`.
4. Khi nào composition phù hợp hơn `extends`? Khi đối tượng có hoặc ủy quyền cho một thành phần mà không thực sự là subtype của nó.

**Ghi nhớ:** quan hệ subtype trả lời “giá trị này có dùng được ở nơi cần kiểu kia không?”. Kế thừa lớp và triển khai interface có thể tạo quan hệ đó, nhưng API tốt còn đòi hỏi hợp đồng hành vi đúng và kiểu tham số không ràng buộc caller quá mức.
