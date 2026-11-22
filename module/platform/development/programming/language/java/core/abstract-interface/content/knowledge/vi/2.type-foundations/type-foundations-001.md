# Kiểu tham chiếu và kiểu thực tế của đối tượng trong Java

Khi làm việc với kế thừa, lớp trừu tượng và interface, cần phân biệt **kiểu của biến tham chiếu** với **kiểu thực tế của đối tượng mà biến đang trỏ tới**. Phân biệt này giải thích vì sao cùng một lời gọi phương thức có thể chạy các phần cài đặt khác nhau, vì sao không gọi được mọi phương thức của đối tượng qua một biến, và vì sao ép kiểu xuống đôi khi thất bại.

## 1. Hai khái niệm khác nhau

Xét câu lệnh:

```java
Animal pet = new Dog("Milo");
```

Giả sử `Dog extends Animal`:

- **Kiểu tham chiếu (reference type / kiểu khai báo, compile-time type)** của `pet` là `Animal`. Đây là kiểu mà trình biên dịch dùng để kiểm tra phép gán, khả năng truy cập thành viên, chữ ký phương thức và lựa chọn overload. Kiểu khai báo của biến `pet` không tự đổi thành `Dog`.
- **Kiểu thực tế (runtime class / kiểu động)** của đối tượng được tạo bởi `new Dog(...)` là `Dog`. Đối tượng ấy có phần trạng thái và hành vi do `Dog` định nghĩa hoặc kế thừa. `pet.getClass()` trả về `Dog.class` khi `pet` khác `null`.
- `pet` lưu **giá trị tham chiếu tới đối tượng**. Phép gán từ biến tham chiếu khác chỉ sao chép giá trị tham chiếu; nó không biến đối tượng `Dog` thành một đối tượng `Animal` mới.

Sơ đồ ý tưởng:

```text
Biến pet
  kiểu khai báo: Animal
  giá trị: tham chiếu ──────────> đối tượng được tạo bởi new Dog(...)
                                   lớp thực tế: Dog
                                   phần Animal + phần Dog
```

Có thể nhìn hai khái niệm theo hai câu hỏi:

| Câu hỏi | Yếu tố quyết định |
| --- | --- |
| Mã nguồn `pet.someMethod()` có hợp lệ không? | Kiểu tham chiếu `Animal` và các phương thức mà kiểu đó khai báo hoặc kế thừa |
| Với phương thức instance được override, thân hàm nào chạy? | Lớp thực tế của đối tượng, ở đây là `Dog` |
| Biểu thức truy cập field nào, hoặc phương thức `static` nào được chọn? | Kiểu của biểu thức tại thời điểm biên dịch |
| Overload nào được chọn? | Kiểu tĩnh của các đối số và các overload khả dụng khi biên dịch |
| Ép kiểu xuống `Dog` có chạy thành công không? | Đối tượng thật có tương thích với `Dog` tại runtime không? |

## 2. Upcasting và tính đa hình

Nếu `Dog` là một kiểu con của `Animal`, Java cho phép gán một đối tượng `Dog` cho tham chiếu `Animal`:

```java
Dog dog = new Dog("Milo");
Animal animal = dog;      // Upcasting ngầm định: hợp lệ
Object value = animal;    // Mọi class Java đều kế thừa Object
```

Cả ba biến có thể đang tham chiếu **cùng một đối tượng** `Dog`. Upcasting không tạo bản sao và không làm mất các phần của đối tượng. Tương tự, có thể dùng một interface làm kiểu tham chiếu nếu lớp đối tượng thực tế triển khai interface ấy.

```java
interface Trainable {
    void train();
}

class Puppy implements Trainable {
    @Override
    public void train() {
        System.out.println("Training");
    }
}

Trainable t = new Puppy(); // Biến có kiểu interface; đối tượng thật là Puppy
t.train();                 // Gọi được vì Trainable khai báo train()
```

Đoạn trên là **mảnh mã minh họa**, không phải một tệp chương trình độc lập. Một abstract class hoặc interface không thể được khởi tạo trực tiếp bằng `new` thông thường, nhưng vẫn có thể làm kiểu tham chiếu tới thể hiện của lớp cụ thể phù hợp.

Đa hình (polymorphism) xuất hiện khi mã làm việc qua kiểu chung mà hành vi vẫn phụ thuộc vào từng đối tượng cụ thể:

```java
Animal first = new Dog("Milo");
Animal second = new Cat("Luna");

first.sound();  // Thân hàm Dog.sound()
second.sound(); // Thân hàm Cat.sound()
```

Ở đây `Animal` phải khai báo hoặc kế thừa phương thức `sound()` thì hai lệnh mới biên dịch. Việc chọn **implementation** tương ứng của phương thức instance được override xảy ra khi chạy, dựa trên lớp thực tế của đối tượng.

## 3. Ví dụ Java 17+ biên dịch và chạy được

Lưu đúng toàn bộ mã dưới đây vào tệp `ReferenceRuntimeTypeDemo.java`:

```java
public class ReferenceRuntimeTypeDemo {

    static abstract class Animal {
        final String name;
        String kind = "Animal field";

        Animal(String name) {
            this.name = name;
        }

        abstract String sound();

        String introduce() {
            return name + ": " + sound();
        }

        static String family() {
            return "Animal static";
        }
    }

    static final class Dog extends Animal {
        String kind = "Dog field";

        Dog(String name) {
            super(name);
        }

        @Override
        String sound() {
            return "woof";
        }

        void fetch() {
            System.out.println(name + " fetches");
        }

        static String family() {
            return "Dog static";
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

    static String select(Animal animal) {
        return "Animal overload";
    }

    static String select(Dog dog) {
        return "Dog overload";
    }

    public static void main(String[] args) {
        Animal pet = new Dog("Milo");

        System.out.println("declared type: Animal");
        System.out.println("runtime type: " + pet.getClass().getSimpleName());
        System.out.println("sound: " + pet.sound());
        System.out.println("introduce: " + pet.introduce());
        System.out.println("field via Animal: " + pet.kind);
        System.out.println("field via Dog: " + ((Dog) pet).kind);
        System.out.println("static via Animal: " + Animal.family());
        System.out.println("static via Dog: " + Dog.family());
        System.out.println("overload via Animal: " + select(pet));
        System.out.println("overload via Dog: " + select((Dog) pet));

        if (pet instanceof Dog dog) {
            dog.fetch();
        }

        Animal other = new Cat("Luna");
        System.out.println("other: " + other.introduce());
    }
}
```

Chạy tại thư mục chứa tệp:

```bash
javac ReferenceRuntimeTypeDemo.java
java ReferenceRuntimeTypeDemo
```

Kết quả chuẩn:

```text
declared type: Animal
runtime type: Dog
sound: woof
introduce: Milo: woof
field via Animal: Animal field
field via Dog: Dog field
static via Animal: Animal static
static via Dog: Dog static
overload via Animal: Animal overload
overload via Dog: Dog overload
Milo fetches
other: Luna: meow
```

**Giải thích từng hiện tượng quan trọng:**

1. `Animal pet` xác định kiểu khai báo; `new Dog(...)` xác định lớp đối tượng thực tế. Dòng in `declared type: Animal` là nhãn ta tự ghi trong mã; Java không cung cấp `pet.getDeclaredType()` để lấy trực tiếp kiểu khai báo của một biến tại runtime.
2. `pet.sound()` chạy `Dog.sound()` do **dynamic dispatch**. Trong `Animal.introduce()`, lời gọi `sound()` cũng được dispatch tới `Dog.sound()`, dù thân `introduce()` nằm ở lớp cha.
3. `pet.kind` chọn field `Animal.kind`; `((Dog) pet).kind` chọn field `Dog.kind`. Field **bị che khuất (field hiding)**; việc truy cập field không có dynamic dispatch như gọi phương thức được override.
4. `Animal.family()` và `Dog.family()` minh họa **static method hiding**, không phải overriding. Nên gọi phương thức static qua tên lớp cho rõ ý định. Nếu viết `pet.family()`, Java vẫn chọn phiên bản theo kiểu khai báo `Animal`, không theo đối tượng `Dog`.
5. `select(pet)` chọn overload `select(Animal)` khi biên dịch vì đối số có kiểu khai báo `Animal`. Ép kiểu biểu thức thành `Dog` làm `select((Dog) pet)` chọn overload `select(Dog)`; việc ép kiểu thành công chỉ vì đối tượng thực tế là `Dog`.
6. `other` cũng là tham chiếu `Animal`, nhưng trỏ tới `Cat`, nên `other.introduce()` gọi `Cat.sound()`.

## 4. Những gì kiểu tham chiếu cho phép nhìn thấy

Giả sử `Animal` khai báo `sound()`, còn chỉ `Dog` khai báo `fetch()`:

```java
Animal a = new Dog("Milo");
a.sound(); // Hợp lệ: Animal khai báo sound()
a.fetch(); // LỖI BIÊN DỊCH: không tìm thấy fetch() trên kiểu Animal
```

Đây là **mảnh mã giải thích lỗi**, không phải đoạn được đưa vào chương trình chạy ở mục 3. Đối tượng vẫn là `Dog` và vẫn có hành vi `fetch()`, nhưng trình biên dịch chỉ có thể dựa vào giao diện mà kiểu `Animal` công bố. Java không tự cho phép gọi phương thức riêng của mọi lớp con qua biến lớp cha.

Muốn gọi `fetch()`, hãy dùng tham chiếu có kiểu phù hợp sau khi kiểm tra đối tượng:

```java
Animal a = new Dog("Milo");
if (a instanceof Dog dog) { // Pattern matching for instanceof, Java 16+
    dog.fetch();
}
```

Kiểu của biểu thức cũng quyết định khả năng nhìn thấy thành viên theo quy tắc truy cập `public`, `protected`, package-private và `private`. Một thành viên có tồn tại trong đối tượng không đồng nghĩa với việc mọi vị trí trong chương trình đều được quyền truy cập thành viên đó.

### Gọi instance, truy cập field, static và overload

| Cơ chế | Được quyết định khi nào? | Quy tắc ngắn |
| --- | --- | --- |
| Chọn chữ ký phương thức có thể gọi | Biên dịch | Dựa vào kiểu tham chiếu và quyền truy cập |
| Chạy thân phương thức instance được override | Runtime | Dựa vào lớp thực tế của đối tượng |
| Truy cập field trùng tên giữa lớp cha/con | Biên dịch | Dựa vào kiểu của biểu thức truy cập |
| Gọi phương thức `static` trùng tên | Biên dịch | Hiding theo lớp/kiểu tham chiếu |
| Chọn overload `doWork(Animal)` hay `doWork(Dog)` | Biên dịch | Dựa trên kiểu tĩnh của đối số |
| Constructor | Khi tạo đối tượng | `new Dog(...)` tạo đối tượng `Dog`; constructor không được override |
| Phương thức `private` hoặc `final` | Theo quy tắc khai báo | Không thể override những phương thức này |

Phân biệt hai từ dễ nhầm: **overriding** là lớp con cung cấp thân mới cho phương thức instance có chữ ký thích hợp của lớp cha/interface; **overloading** là nhiều phương thức cùng tên nhưng khác danh sách tham số. Overriding tạo đa hình runtime, còn quá trình chọn overload là tĩnh.

## 5. Downcasting: đổi cách nhìn, không đổi đối tượng

Ép kiểu từ một tham chiếu cha xuống lớp con gọi là **downcasting**:

```java
Animal a = new Dog("Milo");
Dog d = (Dog) a;     // Hợp lệ và thành công tại runtime
d.fetch();
```

Lệnh `(Dog) a` không tạo đối tượng mới, không thay đổi lớp của đối tượng và không thay đổi kiểu khai báo của biến `a`. Nó tạo ra một biểu thức tham chiếu có kiểu `Dog` sau kiểm tra tương thích runtime.

Không thể suy ra rằng *mọi* `Animal` đều là `Dog`:

```java
Animal a = new Cat("Luna");
Dog d = (Dog) a; // Biên dịch được nhưng ném ClassCastException khi chạy
```

Lý do: `Cat` và `Dog` đều là lớp con của `Animal` nhưng đối tượng thực tế là `Cat`. Việc ép kiểu chỉ hợp lệ nếu đối tượng thật là thể hiện của kiểu đích hoặc kiểu con tương ứng. Cách an toàn, dễ đọc:

```java
void handle(Animal animal) {
    if (animal instanceof Dog dog) {
        dog.fetch();
    } else {
        System.out.println("Not a Dog");
    }
}
```

Đây là **phương thức minh họa** đặt trong một lớp thích hợp, dùng các lớp `Animal`/`Dog` ở ví dụ chính. Nếu có thể giải quyết yêu cầu bằng phương thức đa hình chung trên `Animal`, hãy ưu tiên thiết kế đó thay vì kiểm tra từng lớp con liên tiếp.

**Upcast** thường là chuyển đổi an toàn, ngầm định từ lớp con sang lớp cha/interface. **Downcast** cần kiểm tra tại runtime; với kiểu tham chiếu không liên quan mà trình biên dịch biết chắc không thể chuyển đổi, bản thân phép cast còn bị từ chối khi biên dịch.

## 6. `instanceof`, `getClass()` và `null`

Hai cách kiểm tra khác nhau:

- `obj instanceof Dog` trả về `true` nếu đối tượng không null và tương thích với `Dog`, bao gồm cả thể hiện của các lớp con của `Dog` (nếu `Dog` không `final`).
- `obj.getClass() == Dog.class` chỉ đúng khi **lớp thực tế chính xác** là `Dog`. Gọi `getClass()` trên `null` ném `NullPointerException`.

Ví dụ:

```java
Object obj = "Java";
System.out.println(obj instanceof String);             // true
System.out.println(obj.getClass() == String.class);     // true

Object empty = null;
System.out.println(empty instanceof String);           // false
// empty.getClass(); // NullPointerException
```

Đoạn trên là mảnh lệnh minh họa trong một phương thức. `null` không có lớp thực tế của đối tượng vì **không có đối tượng** nào được tham chiếu. Có thể gán `null` cho biến kiểu tham chiếu, nhưng không thể gọi phương thức instance của đối tượng qua giá trị null. Phép cast `(Dog) null` cho kết quả `null`, không ném `ClassCastException` tại thời điểm cast.

Một đối tượng có **một lớp thực tế cụ thể** khi được tạo, nhưng có thể tương thích với nhiều kiểu tham chiếu (các lớp cha và interface của nó). `instanceof` kiểm tra tương thích kiểu; `getClass()` cho biết lớp thực tế chính xác. Không nên dùng so sánh `getClass()` để thay thế máy móc cho `instanceof`, vì hai biểu thức trả lời hai câu hỏi khác nhau.

## 7. Những lỗi hiểu nhầm thường gặp

**Nhầm 1: “Biến `Animal` thì đối tượng là `Animal`.”** Sai với `Animal a = new Dog(...)`: biến có kiểu tĩnh `Animal`, đối tượng có lớp thực tế `Dog`. Kể cả `Animal` là abstract class thì khai báo biến kiểu `Animal` vẫn hợp lệ.

**Nhầm 2: “Override và overload đều chọn theo lớp thực tế.”** Override của phương thức instance dispatch động. Overload được giải quyết khi biên dịch dựa trên kiểu biểu thức đối số, như `select(pet)` trong ví dụ.

**Nhầm 3: “Field được đa hình như method.”** Truy cập field theo kiểu biểu thức; field cùng tên trong lớp con là hiding. Dùng phương thức instance (ví dụ getter có thể override) nếu cần hành vi đa hình, thay vì dựa vào việc che khuất field.

**Nhầm 4: “Ép kiểu xuống biến đối tượng thành lớp con.”** Cast chỉ đổi kiểu của **biểu thức tham chiếu** mà mã đang sử dụng và thực hiện kiểm tra khi cần; đối tượng vẫn mang lớp được xác định lúc tạo.

**Nhầm 5: “`instanceof` luôn tương đương `getClass() == ...`.”** `instanceof` chấp nhận kiểu con, còn so sánh `getClass()` yêu cầu lớp thực tế trùng chính xác; `null` cũng tạo ra kết quả khác.

**Nhầm 6: “Kiểu của một collection tự động thay đổi vì phần tử là lớp con.”** `List<Dog>` không phải kiểu con của `List<Animal>` trong Java, dù `Dog extends Animal`. Đây là quy tắc invariance của generic type arguments, độc lập với việc một phần tử `Dog` có thể được gán cho một biến `Animal`. Có thể dùng `List<? extends Animal>` để đọc các phần tử như `Animal` khi phù hợp.

## 8. Cách tự phân tích một biểu thức

Khi gặp `Base x = new Derived();` và `x.action()`, hãy trả lời theo thứ tự:

1. **Biến `x` được khai báo là kiểu nào?** Compiler dùng kiểu đó để xác định phương thức có tồn tại và có truy cập được không.
2. **Đối tượng `x` đang trỏ đến được tạo từ lớp nào?** Nếu `action()` là phương thức instance được override, implementation tương ứng của lớp thực tế sẽ chạy.
3. **Đang gọi method instance, method static, overload hay truy cập field?** Chỉ phương thức instance override mới có dynamic dispatch theo nghĩa đang xét.
4. **Có phép cast hoặc `instanceof` không?** Kiểm tra tương thích của lớp thực tế và nhớ rằng kiểu tĩnh của biểu thức sau cast có thể ảnh hưởng đến overload và member access.
5. **Tham chiếu có thể là `null` không?** Kiểm tra trước khi dereference nếu luồng dữ liệu cho phép null.

### Tự kiểm tra nhanh

**Câu 1.** `Animal a = new Dog("Milo");` thì `a.sound()` gọi phương thức nào nếu `Dog` override `sound()`? — **`Dog.sound()`**, miễn lời gọi hợp lệ theo kiểu `Animal`.

**Câu 2.** Vì sao `a.fetch()` có thể không biên dịch, dù `a.getClass()` là `Dog.class`? — Vì **kiểu khai báo `Animal` không công bố `fetch()`**; compiler không dựa vào kết quả `getClass()` tại runtime để cho phép lời gọi.

**Câu 3.** `Animal a = new Cat("Luna"); Dog d = (Dog) a;` lỗi ở đâu? — Cast có thể **biên dịch**, nhưng ném **`ClassCastException` lúc chạy**, do đối tượng là `Cat`.

**Ghi nhớ:** kiểu tham chiếu kiểm soát **mã có thể yêu cầu điều gì**; lớp thực tế của đối tượng quyết định **implementation nào chạy** khi gọi phương thức instance được override. Hiểu đúng hai tầng này là nền tảng để thiết kế API bằng abstract class/interface và dùng đa hình an toàn.
