# Ép kiểu lên, ép kiểu xuống, `instanceof` và `ClassCastException` trong Java

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **kiểu tĩnh/kiểu khai báo** (*compile-time type*) của một biến tham chiếu khác **kiểu thực tế** (*runtime class*) của object mà biến ấy đang tham chiếu.
- Nhận biết quan hệ **subtype/supertype** qua `extends` và `implements`, kể cả khi một object được nhìn qua biến kiểu superclass hoặc interface.
- Sử dụng **upcasting** (ép kiểu lên) an toàn trong các assignment, truyền tham số và trả về từ method, đồng thời hiểu cast này **không tạo object mới**.
- Biết lúc nào cần **downcasting** (ép kiểu xuống) để truy cập thành viên riêng của subtype; phân biệt **ép kiểu hợp lệ ở compile time** với **ép kiểu thực sự thành công khi chạy**.
- Dự đoán khi nào JVM ném `ClassCastException`; phân biệt nó với lỗi biên dịch, `NullPointerException` và `ArrayStoreException`.
- Viết kiểm tra kiểu bằng toán tử `instanceof` và dùng **pattern matching for instanceof** đã là tính năng chuẩn trong Java 17.
- Hiểu phạm vi (*flow scoping*) của pattern variable, cách xử lý `null`, và các kết hợp `&&`, `!`, `||` với điều kiện phân luồng.
- Phân biệt ảnh hưởng của kiểu tĩnh tới **overloading/member lookup** với **dynamic dispatch** của overridden instance methods.
- Phân tích interface casts, arrays, generics/type erasure, wrapper types và các giới hạn không thể kiểm tra generic arguments tại runtime.
- Chọn thiết kế **polymorphism, interface contract, visitor/strategy** khi phù hợp thay vì lạm dụng chuỗi `instanceof` rồi downcast.
- Biên dịch/chạy độc lập các ví dụ Java 17+, kiểm tra stdout và tự sửa các lỗi ép kiểu phổ biến.

## 1. Điểm xuất phát: một object có thể được nhìn qua nhiều kiểu

Xét cây kế thừa:

~~~text
          Animal
          /    \
        Dog    Cat
~~~

Một object `Dog` là một `Dog` và đồng thời thỏa kiểu `Animal` theo quan hệ thừa kế. Nhưng một object `Cat` không phải là `Dog` chỉ vì chúng cùng có superclass Animal.

Trong Java:

~~~java
class Animal {
    void move() {
        System.out.println("animal moves");
    }
}

class Dog extends Animal {
    void bark() {
        System.out.println("woof");
    }
}

class Cat extends Animal {
    void meow() {
        System.out.println("meow");
    }
}
~~~

Đây là các **khai báo minh họa** có thể đặt trong cùng một source phù hợp; chưa có `main`.

Xét:

~~~java
Dog dog = new Dog();
Animal animal = dog;
~~~

- **Object thực tế:** duy nhất một object có runtime class `Dog`.
- **Biến `dog`:** có kiểu tĩnh `Dog`.
- **Biến `animal`:** có kiểu tĩnh `Animal`.
- **Giá trị tham chiếu:** cả hai biến có thể giữ reference tới **chính cùng một Dog object**.

Sơ đồ:

~~~text
dog: Dog  --------+
                 |
                 v
             [Dog object]
                 ^
                 |
animal: Animal --+
~~~

Dòng `Animal animal = dog;` **không biến Dog object thành Animal object mới** và không sao chép fields. Nó chỉ cho phép dùng reference Dog qua một biến có kiểu tĩnh rộng hơn.

### 1.1. Kiểu tĩnh và kiểu runtime giải quyết hai câu hỏi khác nhau

**Kiểu tĩnh** cho compiler biết phép gọi thành viên có hợp lệ không, overload nào là ứng viên, cần kiểm tra cast nào và kiểu kết quả của biểu thức.

**Kiểu runtime** giúp JVM chọn implementation của instance method được override và thực hiện kiểm tra an toàn runtime khi downcast.

Vì thế:

~~~java
Animal animal = new Dog();
animal.move(); // Được: Animal khai báo move().
// animal.bark(); // Không biên dịch: Animal không có bark().
~~~

Dù object thực tế là Dog, compiler không cho `animal.bark()` vì expression `animal` có kiểu tĩnh Animal và không có method bark trong API tương ứng.

Muốn gọi `bark` phải bảo đảm object thật là Dog và thể hiện điều đó với kiểm tra/cast phù hợp.

## 2. Upcasting: từ subtype lên supertype

**Upcasting** là việc xem một reference có kiểu subtype qua kiểu supertype phù hợp, chẳng hạn `Dog` → `Animal` hoặc `Dog` → một interface mà Dog implements.

Ví dụ:

~~~java
Dog dog = new Dog();

Animal asAnimal = dog;  // Upcasting ngầm định.
Object asObject = dog;  // Dog là subtype của Object.
~~~

Đây là **widening reference conversion** trong Java. Với các quan hệ kiểu hợp lệ, thường không cần viết cast tường minh:

~~~java
Animal asAnimal = (Animal) dog; // Có thể viết nhưng dư thừa.
~~~

Một object Dog đã đáp ứng hợp đồng Animal nên đây là phép chuyển kiểu reference hợp lệ.

### 2.1. Upcasting xảy ra ở nhiều ngữ cảnh

**Assignment:**

~~~java
Animal animal = new Dog();
~~~

**Truyền tham số:**

~~~java
static void examine(Animal animal) {
    animal.move();
}

examine(new Dog());
~~~

**Trả về từ method:**

~~~java
static Animal createAnimal() {
    return new Dog();
}
~~~

**Phần tử collection:**

~~~java
java.util.List<Animal> animals = new java.util.ArrayList<>();
animals.add(new Dog());
animals.add(new Cat());
~~~

Những ví dụ trên là **mảnh minh họa**, cần các khai báo `Animal`, `Dog`, `Cat` thích hợp trong cùng context.

**Điểm chung:** trong các ngữ cảnh được nêu, một Dog/Cat instance có thể được dùng qua interface/superclass contract mà không cần tạo lại object.

### 2.2. Upcasting không xóa các thành viên riêng

Object Dog vẫn có thể chứa state riêng và method `bark()`; compiler chỉ **giới hạn góc nhìn qua biến Animal**. Nếu một method lấy `Animal` rồi trả lại cùng reference hoặc caller giữ reference Dog ban đầu, state của Dog không hề biến mất.

Đừng nói rằng “ép lên làm mất thuộc tính của Dog”. Câu chính xác là **kiểu tĩnh Animal không công bố các member riêng của Dog cho lời gọi trực tiếp**.

## 3. Chương trình runnable: upcasting và dynamic dispatch

Lưu **`UpcastingDemo.java`**:

~~~java
public class UpcastingDemo {
    static class Animal {
        String sound() {
            return "unknown";
        }

        String category() {
            return "animal";
        }
    }

    static final class Dog extends Animal {
        @Override
        String sound() {
            return "woof";
        }

        void bark() {
            System.out.println("Dog.bark");
        }
    }

    static final class Cat extends Animal {
        @Override
        String sound() {
            return "meow";
        }
    }

    static void describe(Animal animal) {
        System.out.println(animal.category() + ":" + animal.sound());
    }

    public static void main(String[] args) {
        Dog dog = new Dog();

        Animal asAnimal = dog;
        Object asObject = dog;

        System.out.println("same Dog reference=" + (dog == asAnimal));
        System.out.println("same Object reference=" + (dog == asObject));
        System.out.println("sound=" + asAnimal.sound());

        describe(dog);
        describe(new Cat());

        dog.bark();
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac UpcastingDemo.java
java UpcastingDemo
~~~

**Stdout chính xác:**

~~~text
same Dog reference=true
same Object reference=true
sound=woof
animal:woof
animal:meow
Dog.bark
~~~

Giải thích:

1. `dog`, `asAnimal`, `asObject` cùng trỏ tới một Dog object.
2. `asAnimal.sound()` hợp lệ vì Animal định nghĩa `sound()`; implementation runtime là `Dog.sound()` nhờ **dynamic dispatch**.
3. `category()` không bị override nên implementation Animal trả `animal`.
4. `describe(Animal)` làm việc với Dog hoặc Cat mà không cần downcast để biết từng subtype.
5. `dog.bark()` gọi được vì biến `dog` có kiểu tĩnh Dog.

**Kết luận quan trọng:** upcasting **không phá đa hình**. Ngược lại, dùng một kiểu chung để gọi behavior được override chính là trường hợp tiêu biểu cho polymorphism.

## 4. Downcasting: từ kiểu rộng xuống kiểu hẹp

**Downcasting** là việc chuyển một reference nhìn qua supertype về một subtype cụ thể:

~~~java
Animal animal = new Dog();
Dog dog = (Dog) animal;
dog.bark();
~~~

`(Dog) animal` là một **narrowing reference conversion** tường minh. Compiler chấp nhận vì `Animal` và `Dog` có quan hệ có thể cast, nhưng việc phép cast thành công **phụ thuộc runtime object**.

Trong ví dụ, runtime object chính là Dog nên cast thành công. Nếu runtime object là Cat, cast sang Dog sẽ thất bại.

### 4.1. Downcast không “biến đổi đối tượng”

~~~java
Animal animal = new Dog();
Dog dog = (Dog) animal;
~~~

Sau cast:

- `animal` vẫn có kiểu tĩnh Animal.
- `dog` có kiểu tĩnh Dog.
- Cả hai references vẫn trỏ tới **cùng object Dog**.
- Không có constructor Dog mới.
- Không có copy fields hoặc chuyển đổi giá trị data.
- Không có chuyện cast “biến Cat thành Dog” hay cấp phát object Dog thay Cat.

Cast expression chỉ làm **kiểm tra/diễn giải một reference theo kiểu đích**, nếu ngôn ngữ cho phép.

### 4.2. Không cast xuống chỉ vì muốn truy cập một method

Nếu một method là behavior chung của Animal (như `speak()`), hãy khai báo nó trên Animal/interface và override trong subtypes. Khi đó caller dùng `Animal.speak()` thay vì `if (animal instanceof Dog) ... else ...`.

Downcast phù hợp hơn khi hành vi thật sự **chỉ tồn tại ở subtype** hoặc tại một ranh giới kiểm tra runtime type (parser, framework, event handler), và bạn đã quyết định xử lý rõ trường hợp khác subtype.

## 5. Chương trình runnable: cast thành công và không thành công

Lưu **`DowncastingDemo.java`**:

~~~java
public class DowncastingDemo {
    static class Animal {
        String kind() {
            return "animal";
        }
    }

    static final class Dog extends Animal {
        void bark() {
            System.out.println("woof");
        }
    }

    static final class Cat extends Animal {
        void meow() {
            System.out.println("meow");
        }
    }

    public static void main(String[] args) {
        Animal first = new Dog();
        Dog dog = (Dog) first;

        System.out.println("successful cast=" + (dog == first));
        dog.bark();

        Animal second = new Cat();

        try {
            Dog impossible = (Dog) second;
            impossible.bark();
        } catch (ClassCastException expected) {
            System.out.println("Cat cannot be cast to Dog");
        }

        System.out.println("runtime kind=" + second.getClass().getSimpleName());
    }
}
~~~

Chạy:

~~~bash
javac DowncastingDemo.java
java DowncastingDemo
~~~

Output:

~~~text
successful cast=true
woof
Cat cannot be cast to Dog
runtime kind=Cat
~~~

**Giải thích:**

- `first` có kiểu tĩnh Animal nhưng runtime class là Dog → cast Dog thành công.
- `second` có kiểu tĩnh Animal nhưng runtime class là Cat → cast Dog thất bại với `ClassCastException`.
- Catch block minh họa việc phân loại exception bằng **type**, không dựa vào nguyên văn exception message (message có thể khác giữa các JDK).
- `second.getClass().getSimpleName()` trả tên runtime class Cat trong ví dụ.

**Không nên** dựa vào `catch (ClassCastException)` như một cách điều khiển luồng bình thường nếu có thể kiểm tra kiểu từ trước. Exception nên đại diện lỗi bất thường hoặc vi phạm contract; phần sau sẽ dùng `instanceof`.

## 6. Kiểu tĩnh cho phép cast không bảo đảm runtime object phù hợp

Tình huống:

~~~java
Animal animal = new Cat();
Dog dog = (Dog) animal; // Compile được; lúc chạy ném ClassCastException.
~~~

Compiler thấy **Animal có thể tham chiếu Dog** nên cast có thể hợp lệ ở thời điểm viết code. Nhưng runtime value đang trỏ Cat.

**Hai bước kiểm tra phải tách rõ:**

1. **Compile-time compatibility:** Java cho phép kiểu nguồn và kiểu đích có khả năng chuyển reference theo quy tắc không?
2. **Runtime cast check:** Object cụ thể có là instance của kiểu đích hoặc subtype tương thích không?

Mọi lỗi của bước 1 là **compile-time error**; lỗi bước 2 của phép cast reference tường minh thường là `ClassCastException`.

### 6.1. Một số cast không tương thích ngay lúc biên dịch

~~~java
String name = "Lan";
// Integer invalid = (Integer) name; // Không thể cast giữa các final classes
//                                  // String và Integer không có quan hệ phù hợp.
~~~

Đây là mảnh minh họa với dòng sai đã comment. Compiler có thể bác bỏ ngay cast bất khả thi giữa những kiểu class cụ thể không liên quan.

Nhưng:

~~~java
Object unknown = "Lan";
// Integer value = (Integer) unknown; // Biên dịch được nhưng lỗi runtime.
~~~

Compiler chỉ thấy `Object` có thể giữ Integer, nên cast `(Integer) unknown` có thể compile. Runtime object thực là String, vì vậy nếu thực thi dòng đó sẽ ném `ClassCastException`.

**Không phải mọi cast giữa hai interface không liên quan đều bị chặn ở compile time.** Một class có thể implement nhiều interfaces, nên có những cast tới interface khác mà compiler cho phép, nhưng runtime vẫn phải kiểm tra object.

## 7. `ClassCastException` là gì?

`java.lang.ClassCastException` là một unchecked exception thuộc nhánh:

~~~text
Throwable
  |
Exception
  |
RuntimeException
  |
ClassCastException
~~~

Nó được ném khi một phép chuyển kiểu reference tại runtime cố coi một object là kiểu mà object đó **không phải**.

Những điểm cần nhớ:

- Upcasting hợp lệ không ném `ClassCastException`.
- Downcasting có runtime check; nếu không tương thích có thể ném `ClassCastException`.
- Cast `null` sang bất kỳ reference type hợp lệ nào **không ném** `ClassCastException`; null vẫn là null.
- Lời gọi method trên null có thể ném `NullPointerException`; đây là lỗi khác.
- Cast primitive như `(int) 3.9` là **numeric conversion**, không phải runtime reference cast và không ném `ClassCastException` vì số bị làm tròn.
- Array store vào array runtime có component type hẹp có thể ném `ArrayStoreException`, khác `ClassCastException`.

### 7.1. Thông báo exception không phải hợp đồng đầu ra cố định

Trong nhiều JVM, error message chứa tên nguồn, tên đích, module hoặc class loader. Không nên thiết kế logic theo cách parse chữ trong `ClassCastException.getMessage()`. Dựa vào **type** của exception và sửa nguồn dữ liệu/contract sai.

Nếu kiểm thử minh họa, có thể in `expected.getClass().getSimpleName()`; kết quả `ClassCastException` ổn định hơn việc in toàn bộ stack trace.

### 7.2. Lỗi ép kiểu có thể là lỗi thiết kế

Ví dụ caller luôn phải viết:

~~~java
Dog dog = (Dog) service.getAnimal();
~~~

Trong khi method `getAnimal()` có thể trả Cat, đó là một dấu hiệu contract chưa rõ. Các lựa chọn:

- Method trả kiểu `Dog` nếu bảo đảm kết quả luôn là Dog.
- Method trả `Optional<Dog>` khi có thể không tồn tại Dog.
- Method trả `Animal` và caller dùng API đa hình.
- Phân loại bằng `instanceof` và xử lý nhánh khác đúng mục đích.

Cast không nên thay thế tài liệu hoặc invariant của API.

## 8. `instanceof`: kiểm tra object có thuộc kiểu hay không

Toán tử `instanceof` truyền thống:

~~~java
if (animal instanceof Dog) {
    Dog dog = (Dog) animal;
    dog.bark();
}
~~~

Biểu thức `animal instanceof Dog` trả `true` khi runtime object không null và có kiểu tương thích với Dog theo quy tắc Java; ngược lại trả `false`.

Điểm quan trọng:

- Kiểm tra dựa vào **runtime object**, không chỉ kiểu biến.
- Subclass của Dog cũng có thể thỏa `instanceof Dog` nếu Dog không final.
- Một object có thể thỏa **nhiều** `instanceof`: subclass, superclass, implemented interfaces.
- `null instanceof Dog` là **false**, không ném exception.
- Trong Java 17, `instanceof` còn hỗ trợ **type pattern** để vừa kiểm tra vừa tạo pattern variable.

### 8.1. Chương trình kiểu truyền thống

Lưu **`TraditionalInstanceofDemo.java`**:

~~~java
public class TraditionalInstanceofDemo {
    static class Animal {
    }

    static final class Dog extends Animal {
        void bark() {
            System.out.println("woof");
        }
    }

    static final class Cat extends Animal {
    }

    static void inspect(Animal animal) {
        if (animal instanceof Dog) {
            Dog dog = (Dog) animal;
            dog.bark();
        } else if (animal instanceof Cat) {
            System.out.println("cat detected");
        } else {
            System.out.println("other or null");
        }
    }

    public static void main(String[] args) {
        inspect(new Dog());
        inspect(new Cat());
        inspect(null);
        inspect(new Animal());
    }
}
~~~

Chạy:

~~~bash
javac TraditionalInstanceofDemo.java
java TraditionalInstanceofDemo
~~~

Output:

~~~text
woof
cat detected
other or null
other or null
~~~

`instanceof` đã xác nhận Dog trước khi cast, nên cast trong cùng nhánh trên giá trị không bị thay đổi có thể thành công. Nhưng một kiểm tra riêng biệt cách xa vị trí cast trong code có state/concurrency có thể làm suy luận phức tạp hơn, vì vậy nên giữ kiểm tra và sử dụng gần nhau.

### 8.2. Khi nào kiểm tra trả false?

`instanceof` trả false nếu:

- Biến tham chiếu chứa `null`.
- Runtime object thuộc một kiểu không tương thích với type test.
- Object không implement interface được kiểm tra.

Không dùng `instanceof` như bài kiểm tra nội dung của object (ví dụ số dư hợp lệ, email đúng định dạng); nó chỉ trả lời câu hỏi **quan hệ kiểu**.

## 9. Pattern matching for `instanceof` trong Java 17

Java 17 hỗ trợ chuẩn cú pháp:

~~~java
if (animal instanceof Dog dog) {
    dog.bark();
}
~~~

`Dog dog` là **type pattern**. Khi phép kiểm tra thành công, biến `dog` có kiểu tĩnh Dog và tham chiếu cùng object như `animal`. Không cần cast tường minh lần nữa.

**Không phải** khai báo Dog object mới: pattern variable chỉ **giữ reference được ràng buộc sau khi type test thành công**.

### 9.1. Chương trình Java 17 đầy đủ

Lưu **`PatternInstanceofDemo.java`**:

~~~java
public class PatternInstanceofDemo {
    interface Pet {
        String name();
    }

    static final class Dog implements Pet {
        private final String name;

        Dog(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }

        String bark() {
            return "woof";
        }
    }

    static final class Cat implements Pet {
        private final String name;

        Cat(String name) {
            this.name = name;
        }

        public String name() {
            return name;
        }

        String meow() {
            return "meow";
        }
    }

    static void describe(Pet pet) {
        if (pet instanceof Dog dog) {
            System.out.println("dog " + dog.name() + ": " + dog.bark());
        } else if (pet instanceof Cat cat) {
            System.out.println("cat " + cat.name() + ": " + cat.meow());
        } else {
            System.out.println("unknown pet");
        }
    }

    public static void main(String[] args) {
        describe(new Dog("Milo"));
        describe(new Cat("Luna"));
        describe(null);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac PatternInstanceofDemo.java
java PatternInstanceofDemo
~~~

Output:

~~~text
dog Milo: woof
cat Luna: meow
unknown pet
~~~

Giải thích:

- `pet` có kiểu tĩnh Pet; implementations Dog/Cat thỏa interface.
- `pet instanceof Dog dog` kiểm tra runtime object, rồi đưa pattern variable `dog` vào phạm vi đúng của nhánh true.
- Trong nhánh đó, compiler biết `dog` là Dog nên có thể gọi `bark()`.
- `pet == null` làm cả hai type tests false, rơi vào nhánh cuối mà không ném NPE.
- Nếu sau này thêm loại Pet thứ ba, method hiện tại in `unknown pet`; đó là contract được chọn trong ví dụ, không tự động hỗ trợ behavior mới.

### 9.2. Java 17 pattern matching khác pattern switch

**Pattern matching cho `instanceof` là tính năng chuẩn ở Java 17.** Không đánh đồng với **pattern matching for switch** ở các đời Java sau; pattern switch từng ở trạng thái preview và có quy tắc khác theo phiên bản.

Để README biên dịch với `javac` Java 17 **không bật preview**, mọi ví dụ dùng pattern `instanceof`, không dựa vào các cú pháp `case Dog d ->` của pattern switch.

## 10. Phạm vi biến pattern: flow scoping

Pattern variable không có scope toàn bộ method chỉ vì có tên xuất hiện trong `instanceof`. Compiler xét **đường điều khiển nào bảo đảm pattern đã match**.

Ví dụ:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
// System.out.println(text); // Không hợp lệ ở đây: text hết scope.
~~~

Đây là mảnh minh họa: `value` có kiểu tĩnh Object hoặc kiểu phù hợp. Trong nhánh true, `text` tồn tại với kiểu String; sau if thông thường, không có bảo đảm pattern đã match.

### 10.1. Kết hợp với `&&`

Nếu một biểu thức:

~~~java
if (value instanceof String text && text.length() >= 3) {
    System.out.println(text.toUpperCase());
}
~~~

thì `text` có thể dùng ở vế phải của `&&` vì vế phải chỉ được đánh giá khi vế trái true và pattern đã match.

**Trái lại:**

~~~java
// if (value instanceof String text || text.isBlank()) {
//     ...
// }
~~~

là ví dụ **sai** khi sử dụng `text` trong vế phải `||`: vế phải chạy khi vế trái false, lúc pattern variable chưa được gán/ràng buộc hợp lệ.

### 10.2. `!` và early return

Một idiom Java 17:

~~~java
static int requireLength(Object value) {
    if (!(value instanceof String text)) {
        throw new IllegalArgumentException("String required");
    }
    return text.length();
}
~~~

Vì nhánh không match kết thúc bất thường bằng `throw`, sau if compiler có thể biết `text` đã match. `return` ở nhánh không match cũng thường tạo điều kiện flow-scoping tương tự.

**Đừng suy luận rằng bất kỳ if phủ định nào cũng làm pattern variable sống mãi**: compiler phải chứng minh các đường đi đến chỗ dùng đều đã match.

## 11. Chương trình runnable: flow scoping và điều kiện có bảo vệ

Lưu **`PatternFlowScopeDemo.java`**:

~~~java
public class PatternFlowScopeDemo {
    static void printLongName(Object value) {
        if (value instanceof String text && text.length() >= 4) {
            System.out.println("long=" + text.toUpperCase());
        } else {
            System.out.println("not long string");
        }
    }

    static int requireLength(Object value) {
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("String required");
        }
        return text.length();
    }

    public static void main(String[] args) {
        printLongName("Java");
        printLongName("Go");
        printLongName(42);
        printLongName(null);

        System.out.println("length=" + requireLength("Learn"));

        try {
            requireLength(10);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid type rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac PatternFlowScopeDemo.java
java PatternFlowScopeDemo
~~~

Output:

~~~text
long=JAVA
not long string
not long string
not long string
length=5
invalid type rejected
~~~

Ở `value instanceof String text && text.length() >= 4`, vế phải chỉ dùng `text` khi nó đã match. Ở `requireLength`, nhánh phủ định ném exception trước khi đi tới `return text.length()` nếu input không phải String.

Đây là cách viết gọn và an toàn hơn pattern truyền thống: `instanceof String` rồi `(String) value`.

### 11.1. Khi pattern bị xem là luôn đúng vì kiểu tĩnh

Trong Java 17, có những type patterns bị compiler bác bỏ nếu **kiểu tĩnh của biểu thức vốn đã là subtype của kiểu pattern**, khiến kiểm tra rườm rà/vô nghĩa theo quy tắc ngôn ngữ. Ví dụ:

~~~java
String text = "Java";
// if (text instanceof String value) { } // Compile-time error
// trong Java 17: expression đã là subtype của pattern type.
~~~

Đừng tự động biến mọi `instanceof` cũ thành pattern trong những chỗ không cần. Nếu biến đã có kiểu String và chỉ muốn kiểm tra null, dùng `text != null`.

## 12. `null` với `instanceof` và cast

`null` không trỏ object nào. Các biểu thức có ngữ nghĩa khác nhau:

~~~java
Object unknown = null;

boolean isString = unknown instanceof String; // false.
String text = (String) unknown;                 // null; không CCE.
// text.length();                              // NPE khi dereference.
~~~

**Không có object thực tế để kiểm tra subtype**, nên `instanceof` trả false. Nhưng cast một reference null sang kiểu tham chiếu được phép là hợp lệ và kết quả vẫn null.

### 12.1. Chương trình xác định từng trường hợp

Lưu **`NullCastingDemo.java`**:

~~~java
public class NullCastingDemo {
    public static void main(String[] args) {
        Object unknown = null;

        System.out.println("is String=" + (unknown instanceof String));

        String text = (String) unknown;
        System.out.println("cast is null=" + (text == null));

        try {
            System.out.println(text.length());
        } catch (NullPointerException expected) {
            System.out.println("null dereference rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac NullCastingDemo.java
java NullCastingDemo
~~~

Output:

~~~text
is String=false
cast is null=true
null dereference rejected
~~~

**Phân biệt kết luận:**

- `unknown instanceof String` không ném NPE.
- `(String) unknown` không ném CCE khi unknown null.
- `text.length()` ném NPE vì dereference null.

Nếu API không cho phép null, nên dùng precondition rõ, ví dụ `Objects.requireNonNull`, thay vì dùng cast như thể cast cũng kiểm tra khác null.

## 13. Upcasting qua interface và downcasting về implementation

Một class có thể implement nhiều interfaces:

~~~java
interface Printable {
    void print();
}

interface Scannable {
    void scan();
}

class MultifunctionDevice implements Printable, Scannable {
    public void print() { }
    public void scan() { }
}
~~~

Một `MultifunctionDevice` object có thể được upcast thành `Printable` hoặc `Scannable`. Khi caller chỉ cầm `Printable`, compiler chỉ cho những methods mà Printable công bố (cộng inherited Object methods theo rules). Để gọi `scan()`, caller có thể kiểm tra có phải Scannable hay không:

~~~java
if (printable instanceof Scannable scanner) {
    scanner.scan();
}
~~~

Một object có thể đồng thời thỏa **hai interface không có quan hệ extends với nhau**. Đây là lý do không thể suy đơn giản rằng “hai interface khác nhau thì cast giữa chúng luôn sai”.

### 13.1. Ví dụ runnable về interface cross-cast

Lưu **`InterfaceCastingDemo.java`**:

~~~java
public class InterfaceCastingDemo {
    interface Printable {
        void print();
    }

    interface Scannable {
        void scan();
    }

    static final class Device implements Printable, Scannable {
        public void print() {
            System.out.println("print");
        }

        public void scan() {
            System.out.println("scan");
        }
    }

    static final class PrinterOnly implements Printable {
        public void print() {
            System.out.println("printer only");
        }
    }

    static void inspect(Printable printer) {
        printer.print();
        if (printer instanceof Scannable scanner) {
            scanner.scan();
        } else {
            System.out.println("scan unavailable");
        }
    }

    public static void main(String[] args) {
        Printable both = new Device();
        Printable justPrinter = new PrinterOnly();

        inspect(both);
        inspect(justPrinter);

        System.out.println("both implements Scannable=" +
                (both instanceof Scannable));
    }
}
~~~

Chạy:

~~~bash
javac InterfaceCastingDemo.java
java InterfaceCastingDemo
~~~

Output:

~~~text
print
scan
printer only
scan unavailable
both implements Scannable=true
~~~

Method `inspect` không làm giả định rằng **mọi Printable đều Scannable**. Nếu printer runtime là Device, nhánh pattern match cho scanner. Nếu là PrinterOnly, method giải thích tính năng không khả dụng.

**Thiết kế thực tế:** Nếu mọi Printer trong một use case bắt buộc có chức năng scan, interface được chọn có thể quá rộng. Khi đó hãy định nghĩa contract phù hợp thay vì kiểm tra runtime trên mọi lời gọi.

## 14. Overloading chọn theo kiểu tĩnh; overriding chọn theo runtime

Đây là bẫy phổ biến khi học casting và polymorphism.

**Overloading**: nhiều methods cùng tên nhưng khác parameter list. Java chọn lời gọi hợp lệ theo **kiểu tại compile time**, quy tắc applicability và overload resolution.

**Overriding**: subclass cung cấp implementation của **cùng instance method signature**. Khi gọi qua object, runtime có thể chọn override tương ứng.

### 14.1. Chương trình chứng minh khác biệt

Lưu **`OverloadOverrideCastDemo.java`**:

~~~java
public class OverloadOverrideCastDemo {
    static class Animal {
        String speak() {
            return "animal";
        }
    }

    static final class Dog extends Animal {
        @Override
        String speak() {
            return "dog";
        }

        void fetch() {
            System.out.println("fetch");
        }
    }

    static void inspect(Animal animal) {
        System.out.println("overload Animal");
    }

    static void inspect(Dog dog) {
        System.out.println("overload Dog");
    }

    public static void main(String[] args) {
        Dog dog = new Dog();
        Animal animal = dog;

        inspect(dog);
        inspect(animal);

        System.out.println("runtime speak=" + animal.speak());
        inspect((Dog) animal);

        ((Dog) animal).fetch();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac OverloadOverrideCastDemo.java
java OverloadOverrideCastDemo
~~~

Output:

~~~text
overload Dog
overload Animal
runtime speak=dog
overload Dog
fetch
~~~

- `inspect(dog)` chọn overload Dog vì expression dog có kiểu Dog.
- `inspect(animal)` chọn overload Animal vì expression animal có kiểu **tĩnh Animal**, dù runtime object là Dog.
- `animal.speak()` chọn Dog override vì dynamic dispatch của instance method.
- `inspect((Dog) animal)` chọn overload Dog do **kiểu tĩnh của cast expression** là Dog; cast runtime thành công vì object thực Dog.
- Nếu animal thực sự trỏ Cat, cast `(Dog) animal` sẽ ném CCE trước khi gọi overload Dog.

**Đừng nghĩ** JVM dùng kiểu runtime để chọn toàn bộ overloads theo “method phù hợp nhất với object thật”. Java overload resolution diễn ra ở compile time.

## 15. `getClass()`, `instanceof`, `Class.isInstance` khác nhau thế nào?

Cần phân biệt:

- `obj instanceof Animal`: true với object Animal **hoặc subclass** phù hợp, null cho false.
- `obj.getClass() == Animal.class`: kiểm tra **đúng runtime class Animal**, không phải subclass. `getClass()` trên null ném NPE.
- `Animal.class.isInstance(obj)`: kiểm tra membership runtime giống phép `instanceof Animal` trong trường hợp class type thích hợp, và nhận null cho false.
- `Animal.class.isAssignableFrom(Dog.class)`: trả true nếu có quan hệ kiểu cho phép gán Dog instance tới biến kiểu Animal; dùng **hai Class objects** thay vì một object instance.

### 15.1. Chương trình runnable

Lưu **`RuntimeTypeCheckDemo.java`**:

~~~java
public class RuntimeTypeCheckDemo {
    static class Animal {
    }

    static final class Dog extends Animal {
    }

    public static void main(String[] args) {
        Object value = new Dog();

        System.out.println("Animal instanceof=" + (value instanceof Animal));
        System.out.println("Dog instanceof=" + (value instanceof Dog));
        System.out.println("exact Animal=" +
                (value.getClass() == Animal.class));
        System.out.println("exact Dog=" +
                (value.getClass() == Dog.class));

        System.out.println("Animal.isInstance=" +
                Animal.class.isInstance(value));
        System.out.println("Animal assignable from Dog=" +
                Animal.class.isAssignableFrom(Dog.class));
        System.out.println("Dog assignable from Animal=" +
                Dog.class.isAssignableFrom(Animal.class));
        System.out.println("null isInstance=" +
                Animal.class.isInstance(null));
    }
}
~~~

Lệnh:

~~~bash
javac RuntimeTypeCheckDemo.java
java RuntimeTypeCheckDemo
~~~

Output:

~~~text
Animal instanceof=true
Dog instanceof=true
exact Animal=false
exact Dog=true
Animal.isInstance=true
Animal assignable from Dog=true
Dog assignable from Animal=false
null isInstance=false
~~~

**Khi nào dùng?**

- `instanceof`: thường phù hợp khi kiểm tra một object thuộc subtype/interface trong code viết sẵn type.
- `getClass() == ...`: khi thực sự cần **exact runtime class** (ví dụ hợp đồng equality cụ thể), không chấp nhận subclass.
- `Class.isInstance`: hữu ích khi type được chọn dưới dạng một `Class<?>` value ở runtime.
- `Class.isAssignableFrom`: kiểm tra quan hệ giữa hai type descriptors; hướng **supertype.isAssignableFrom(subtype)** rất dễ bị viết ngược.

### 15.2. `Class.cast`

API `Class<T>.cast(Object)` cung cấp một phép cast có kiểm tra runtime qua một `Class<T>` object. Nó ném `ClassCastException` khi object không tương thích, và có thể trả null khi input null.

~~~java
Class<Dog> type = Dog.class;
Object unknown = new Dog();
Dog dog = type.cast(unknown);
~~~

Đây là đoạn minh họa dùng Dog class phù hợp. Nó hữu ích cho API generic nhận `Class<T>`, nhưng **không** có nghĩa method `Class.cast` an toàn với mọi runtime object; lỗi CCE vẫn xảy ra nếu caller đưa sai đối tượng.

## 16. Java generics và type erasure: không kiểm tra được mọi tham số kiểu

Một điều tưởng hợp lý nhưng **không hợp lệ trong Java 17**:

~~~java
Object value = java.util.List.of("A");
// if (value instanceof java.util.List<String> strings) { }
// Không hợp lệ: List<String> không reifiable như type test này.
~~~

Các generic type arguments như `String` thường bị **type erasure** ở runtime. Vì vậy không thể dùng `instanceof List<String>` làm kiểm tra toàn bộ danh sách chứa String.

**Hợp lệ:**

~~~java
if (value instanceof java.util.List<?> items) {
    System.out.println("size=" + items.size());
}
~~~

`List<?>` là type pattern hợp lệ về runtime kind của collection. Nhưng nó **chỉ chứng minh object là List**, không chứng minh toàn bộ elements đều String.

### 16.1. Bẫy unchecked cast

Giả sử một `Object` thực chất giữ `List<Integer>`:

~~~java
Object unknown = java.util.List.of(42);
@SuppressWarnings("unchecked")
java.util.List<String> texts = (java.util.List<String>) unknown;
~~~

Cast có thể hoàn thành runtime như cast tới raw List, do erasure, nhưng lần đọc element như String có thể ném `ClassCastException` khi compiler-inserted cast ở điểm lấy phần tử được thực hiện.

### 16.2. Chương trình minh họa runtime failure đến muộn

Lưu **`GenericCastErasureDemo.java`**:

~~~java
import java.util.List;

public class GenericCastErasureDemo {
    public static void main(String[] args) {
        Object source = List.of(42);

        if (source instanceof List<?> list) {
            System.out.println("list size=" + list.size());

            @SuppressWarnings("unchecked")
            List<String> wrong = (List<String>) source;

            System.out.println("casted list size=" + wrong.size());

            try {
                String text = wrong.get(0);
                System.out.println("text=" + text);
            } catch (ClassCastException expected) {
                System.out.println("element cast failed");
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac GenericCastErasureDemo.java
java GenericCastErasureDemo
~~~

Output:

~~~text
list size=1
casted list size=1
element cast failed
~~~

**Điều cần hiểu:**

- Runtime object là List với một Integer.
- `instanceof List<?>` chỉ biết đó là List.
- Unchecked cast sang `List<String>` không xác minh từng phần tử tại thời điểm cast.
- Khi `wrong.get(0)` được dùng ở ngữ cảnh cần String, runtime kiểm tra element và gặp Integer → `ClassCastException`.

**Không xem `@SuppressWarnings("unchecked")` là cách sửa lỗi kiểu dữ liệu.** Annotation chỉ tắt cảnh báo có chủ đích; chương trình vẫn có thể thất bại. Ưu tiên thiết kế API dùng generic types xuyên suốt, tránh raw types/unchecked casts.

### 16.3. Generics invariance

Dù Dog extends Animal, `List<Dog>` **không phải** subtype của `List<Animal>`:

~~~java
java.util.List<Dog> dogs = new java.util.ArrayList<>();
// java.util.List<Animal> animals = dogs; // Compile-time error.
~~~

Nếu có thể gán như vậy, caller có thể thêm Cat vào list ban đầu chỉ dành Dog. Java generics dùng **invariance** đối với type parameters thông thường; muốn đọc theo supertype có thể dùng wildcard:

~~~java
java.util.List<? extends Animal> animals = dogs;
~~~

Nhưng cách đó hạn chế việc thêm arbitrary Animals vào list. Đây là cơ chế khác với upcasting **một object Dog** thành Animal, và không nên cố downcast List để lách kiểm soát.

## 17. Array covariance và `ArrayStoreException`

Arrays của reference types trong Java có **covariance**: `Dog[]` có thể được xem như `Animal[]`. Nhưng JVM vẫn giữ runtime component type của array.

Nếu caller cố đặt một Cat vào array thực sự là `Dog[]` qua biến `Animal[]`, runtime ném `ArrayStoreException`.

### 17.1. Chương trình runnable

Lưu **`ArrayCovarianceDemo.java`**:

~~~java
public class ArrayCovarianceDemo {
    static class Animal {
    }

    static final class Dog extends Animal {
    }

    static final class Cat extends Animal {
    }

    public static void main(String[] args) {
        Dog[] dogs = new Dog[2];
        Animal[] animals = dogs;

        animals[0] = new Dog();
        System.out.println("stored Dog=" +
                (animals[0] instanceof Dog));

        try {
            animals[1] = new Cat();
        } catch (ArrayStoreException expected) {
            System.out.println("Cat cannot enter Dog[]");
        }

        System.out.println("array length=" + animals.length);
    }
}
~~~

Chạy:

~~~bash
javac ArrayCovarianceDemo.java
java ArrayCovarianceDemo
~~~

Output:

~~~text
stored Dog=true
Cat cannot enter Dog[]
array length=2
~~~

**Không nhầm hai lỗi:**

- `ClassCastException`: cast object reference sang kiểu không phù hợp.
- `ArrayStoreException`: cố **lưu phần tử** có runtime class không phù hợp với runtime component type của reference array.

Với generics, `List<Dog>` không cho gán vào `List<Animal>`, nên lỗi thêm Cat kiểu này bị ngăn sớm hơn ở compile time.

### 17.2. `instanceof` với mảng

Một `Dog[]` object cũng là `Animal[]` và `Object` phù hợp. Có thể dùng type test cho mảng:

~~~java
Object array = new Dog[2];

boolean isAnimalArray = array instanceof Animal[];
boolean isDogArray = array instanceof Dog[];
~~~

Cả hai trả true trong ví dụ. **Không suy ra** mọi phần tử array đều non-null hoặc đã được khởi tạo. Phần tử reference array mặc định null cho tới khi gán.

## 18. Ép kiểu số và wrapper types không phải downcast class hierarchy

So sánh hai loại conversion:

~~~java
double fraction = 3.9;
int roundedTowardZero = (int) fraction; // 3.
~~~

Đây là **narrowing primitive conversion**: thay đổi biểu diễn số, loại bỏ phần thập phân theo quy tắc Java (trong giới hạn thích hợp). Không có object reference cast và không ném `ClassCastException`.

Trong khi:

~~~java
Object number = Integer.valueOf(7);
// Long wrong = (Long) number; // Runtime ClassCastException.
~~~

`Integer` và `Long` là hai wrapper classes khác nhau; Integer object không biến thành Long object nhờ reference cast.

Nếu cần chuyển nội dung số từ `Number` sang kiểu rộng hơn, dùng API chuyển đổi **giá trị số** phù hợp.

### 18.1. Chương trình runnable phân biệt conversion

Lưu **`NumericVsReferenceCastDemo.java`**:

~~~java
public class NumericVsReferenceCastDemo {
    public static void main(String[] args) {
        double decimal = 3.9;
        int integral = (int) decimal;

        System.out.println("primitive cast=" + integral);

        Object boxed = Integer.valueOf(7);
        Number numeric = (Number) boxed;

        System.out.println("long value=" + numeric.longValue());

        try {
            Long wrong = (Long) boxed;
            System.out.println(wrong);
        } catch (ClassCastException expected) {
            System.out.println("Integer is not Long");
        }
    }
}
~~~

Chạy:

~~~bash
javac NumericVsReferenceCastDemo.java
java NumericVsReferenceCastDemo
~~~

Output:

~~~text
primitive cast=3
long value=7
Integer is not Long
~~~

**Chú ý:** `Number.longValue()` lấy giá trị số theo quy tắc subtype tương ứng. Với số quá lớn, floating point hoặc kiểu tùy chỉnh, việc chuyển có thể mất dữ liệu/precision; `Number.longValue()` không tự là phép chuyển số bảo toàn mọi giá trị.

### 18.2. Không nhầm boxing với reference casting

~~~java
int value = 7;
Integer boxed = value; // Autoboxing.
Object object = boxed; // Upcasting reference.
~~~

Nếu muốn lấy `int`:

~~~java
int back = (Integer) object; // Downcast Object -> Integer, rồi unboxing.
~~~

Hai bước xảy ra với cơ chế khác nhau. Nếu object là null, việc unboxing có thể ném `NullPointerException`. Nếu object là Long, reference cast tới Integer trước hết có thể ném CCE.

## 19. Thiết kế tốt: dùng đa hình thay chuỗi cast khi phù hợp

Một thiết kế ít mở rộng:

~~~java
static double shippingFee(Delivery delivery) {
    if (delivery instanceof BikeDelivery) {
        return 10;
    }
    if (delivery instanceof TruckDelivery) {
        return 50;
    }
    throw new IllegalArgumentException("unsupported delivery");
}
~~~

Đây là **mảnh minh họa** cần các types thực tế. Nếu mỗi lần thêm phương thức giao mới bạn phải sửa hàng loạt `instanceof` branches, logic phân nhánh bị phân tán và dễ thiếu case.

Có thể đặt behavior ở contract:

~~~java
interface Delivery {
    int fee();
}
~~~

Các implementations tự cung cấp `fee()`, caller dùng `delivery.fee()` không cần biết runtime subtype.

### 19.1. Chương trình dùng polymorphism

Lưu **`PolymorphismInsteadOfCastDemo.java`**:

~~~java
public class PolymorphismInsteadOfCastDemo {
    interface Delivery {
        String name();
        int fee();
    }

    static final class Bike implements Delivery {
        public String name() {
            return "bike";
        }

        public int fee() {
            return 10;
        }
    }

    static final class Truck implements Delivery {
        public String name() {
            return "truck";
        }

        public int fee() {
            return 50;
        }
    }

    static void quote(Delivery delivery) {
        System.out.println(delivery.name() + "=" + delivery.fee());
    }

    public static void main(String[] args) {
        quote(new Bike());
        quote(new Truck());
    }
}
~~~

Chạy:

~~~bash
javac PolymorphismInsteadOfCastDemo.java
java PolymorphismInsteadOfCastDemo
~~~

Output:

~~~text
bike=10
truck=50
~~~

Khi thêm một Delivery subtype mới, nó phải implement contract `name()` và `fee()`. Caller không cần thêm `instanceof NewDelivery` chỉ để tính phí cơ bản.

**Nhưng polymorphism không thay thế mọi type test:** nếu bạn xử lý một hệ thống plugin, các capabilities tùy chọn hoặc dữ liệu từ framework mà subtype-specific behavior thật sự khác biệt, kiểm tra runtime bằng `instanceof` có thể phù hợp. Mục tiêu là **lý do thiết kế rõ ràng**, không phải cấm ép kiểu.

## 20. Câu chuyện `instanceof` với `sealed` types (Java 17)

Java 17 chuẩn hóa **sealed classes/interfaces**, giới hạn tập subclass/implementer được phép ở cấp khai báo. Khi model thuộc một tập trường hợp đóng, code đôi khi cần phân tích theo subtype.

Ví dụ:

~~~java
sealed interface Result permits Success, Failure {
}

record Success(String value) implements Result {
}

record Failure(String message) implements Result {
}
~~~

Đây là mã minh họa cần được đặt vào file/package hợp lệ. Với Java 17, có thể dùng `if (result instanceof Success success)`/`else if (...)` để xử lý từng loại. **Không dùng pattern switch như tính năng non-preview chuẩn của Java 17**, vì syntax và tình trạng ổn định khác theo phiên bản.

### 20.1. Chương trình xử lý tập subtype đóng

Lưu **`SealedInstanceofDemo.java`**:

~~~java
public class SealedInstanceofDemo {
    sealed interface Result permits Success, Failure {
    }

    record Success(String value) implements Result {
    }

    record Failure(String message) implements Result {
    }

    static String describe(Result result) {
        if (result instanceof Success success) {
            return "ok=" + success.value();
        }
        if (result instanceof Failure failure) {
            return "error=" + failure.message();
        }
        return "missing";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("42")));
        System.out.println(describe(new Failure("timeout")));
        System.out.println(describe(null));
    }
}
~~~

Chạy:

~~~bash
javac SealedInstanceofDemo.java
java SealedInstanceofDemo
~~~

Output:

~~~text
ok=42
error=timeout
missing
~~~

Với `Result` sealed, các direct permitted implementations được kiểm soát theo ngôn ngữ; nhưng `null` vẫn không match hai patterns nên method chọn `missing`.

Khi thay đổi tập subtypes ở một phiên bản khác của API, hãy rà soát code phân nhánh. Sealed hierarchy có thể giúp thiết kế miền kiểu rõ hơn, nhưng không tự chứng minh mọi `if`/`else` xử lý exhaustive cases trong Java 17.

## 21. Những cast compiler cho phép nhưng runtime dễ thất bại

Hãy so sánh các trường hợp:

| Biểu thức | Compile? | Runtime nếu chạy | Vì sao |
| --- | --- | --- | --- |
| `Animal a = new Dog();` | Có | Thành công | Widening reference |
| `Dog d = (Dog) a;` với a trỏ Dog | Có | Thành công | Actual object là Dog |
| `Dog d = (Dog) a;` với a trỏ Cat | Có | `ClassCastException` | Actual object không phải Dog |
| `Object o = "hello"; Integer i = (Integer) o;` | Có | `ClassCastException` | Runtime String khác Integer |
| Cast trực tiếp `String` → `Integer` | Không trong tình huống lớp final không liên quan | Không chạy | Compile-time inconvertible types |
| `String s = (String) null;` | Có | `s == null` | Cast null không CCE |
| `o instanceof Dog` với o null | Có khi type test hợp lệ | false | Null không là instance |
| `Animal[] a = new Dog[1];` | Có | Thành công | Reference array covariance |
| `a[0] = new Cat();` khi runtime array Dog[] | Có | `ArrayStoreException` | Component type mismatch |
| `List<String> l = (List<String>) o;` khi o giữ List<Integer> | Có thể compile với unchecked warning | Có thể CCE khi lấy String element | Type erasure |
| `int i = (int) 3.9;` | Có | i bằng 3 | Numeric conversion, không phải reference cast |

Bảng giả định có những khai báo Animal/Dog/Cat/List thích hợp và đúng access context. Đừng biến toàn bộ snippets thành một file duy nhất với identifiers trùng nhau.

## 22. “Cast an toàn” thực sự cần những điều kiện gì?

Nếu muốn lấy một subtype:

~~~java
if (value instanceof Dog dog) {
    dog.bark();
}
~~~

thì:

1. `value` có kiểu tĩnh tương thích với một type test tới Dog.
2. Nếu runtime object là Dog/subtype phù hợp, pattern match.
3. Pattern variable `dog` chỉ được dùng trên đường điều khiển compiler biết match.
4. Phép gọi `bark()` còn phải có visibility và method signature hợp lệ.
5. Nếu `value` null/khác subtype, nhánh không chạy.
6. Không có **copy** hay **class conversion** của object thực.

### 22.1. Cảnh giác với field có thể thay đổi giữa check và cast

Ví dụ:

~~~java
if (holder.value instanceof Dog) {
    Dog dog = (Dog) holder.value;
}
~~~

Đây là mảnh minh họa, cần Holder/value phù hợp. Nếu `holder.value` là field mutable và có thể bị thay giữa hai lần đọc (do thread khác hoặc side effect khác), kết quả kiểm tra lần đầu không bảo đảm cast lần sau thấy cùng reference.

An toàn và dễ đọc hơn:

~~~java
Animal snapshot = holder.value;
if (snapshot instanceof Dog dog) {
    dog.bark();
}
~~~

Giả sử value có kiểu Animal. Pattern kiểm tra và ràng buộc **cùng snapshot reference value**. Nhưng nếu Dog object có state mutable, pattern matching **không tự khóa/đồng bộ state**; thread safety là câu hỏi khác.

### 22.2. `instanceof` không kiểm tra invariants

Ngay cả khi `value instanceof BankAccount` true, điều đó không bảo đảm số dư hợp lệ, tài khoản đang active hay object thread-safe. Kiểu là một phần contract, còn state conditions phải được kiểm tra qua API nghiệp vụ.

## 23. Có nên dùng cast khi caller đã biết subtype?

Nếu method nhận:

~~~java
static void handleDog(Dog dog) {
    dog.bark();
}
~~~

thì **không cần** ép lên Animal rồi ép xuống Dog. Nếu API của bạn luôn nhận Dog, hãy khai báo Dog ở parameter/return type.

Ngược lại, nếu method cần chấp nhận mọi Animal:

~~~java
static void handleAnimal(Animal animal) {
    System.out.println(animal.sound());
}
~~~

hãy dùng common contract. Cast nên được dùng **khi có lý do về runtime type**, không phải để thay cho việc chọn type signature chính xác.

### 23.1. Các lựa chọn thiết kế theo nhu cầu

| Nhu cầu | Lựa chọn nên cân nhắc |
| --- | --- |
| Cùng behavior ở mọi subtype | Method trong superclass/interface + override |
| Dependency có implementation thay đổi | Composition qua interface/strategy |
| Xử lý từng loại sự kiện không cùng hành vi | Type pattern `instanceof` với fallback rõ |
| API cam kết Dog | Parameter/return type Dog |
| API có thể không tìm thấy Dog | `Optional<Dog>` hoặc result type phù hợp |
| Generic collection đồng nhất | `List<Dog>`, giữ type information xuyên suốt |
| Xử lý graph kiểu đóng | Sealed hierarchy + type tests/polymorphism theo Java version |
| Framework nhận `Class<T>` | `Class.cast`, `Class.isInstance` với runtime checks |
| Object có capability tùy chọn | Interface type test phù hợp và xử lý no-capability |

## 24. Những lỗi thường gặp khi học casting

| Nhầm lẫn | Điều đúng |
| --- | --- |
| “Upcasting tạo một Animal object mới.” | Chỉ sao chép/diễn giải reference dưới supertype. |
| “Dog biến thành Animal nên mất bark().” | Runtime object vẫn Dog; kiểu tĩnh Animal không cho gọi bark trực tiếp. |
| “Đã cast được tại compile time thì chạy chắc thành công.” | Downcast có runtime check và có thể CCE. |
| “`(Dog) new Cat()` là cách biến Cat thành Dog.” | Không. Các types không tương thích; cast không xây object mới. |
| “`instanceof` kiểm tra tên biến.” | Nó kiểm tra runtime object với type. |
| “`null instanceof Dog` ném NPE.” | False. |
| “Cast null sang Dog gây CCE.” | Hợp lệ và kết quả null, nếu cast type hợp lệ. |
| “Pattern variable có scope toàn method.” | Flow-scoped, chỉ nơi compiler chứng minh đã match. |
| “`&&` và `||` cho pattern variable dùng như nhau.” | `&&` có bảo đảm matching ở vế phải; `||` không có bảo đảm tương tự. |
| “`@Override` là cast.” | Không; nó đánh dấu kiểm tra override ở compile time. |
| “Overloading chọn theo runtime class.” | Chọn overload theo kiểu tại compile time. |
| “Overridden method chọn theo kiểu biến.” | Dynamic dispatch có thể chọn implementation theo runtime class. |
| “`getClass()==Animal.class` và `instanceof Animal` giống nhau.” | Exact class vs quan hệ subtype. |
| “`List<Dog>` là subtype của `List<Animal>`.” | Generics thường invariant. |
| “`instanceof List<String>` kiểm tra từng element.” | Không hợp lệ với generic parameter không reifiable. |
| “Unchecked cast List<Integer>→List<String> xác nhận elements.” | Không; element read có thể gây CCE về sau. |
| “`Animal[]` giữ Dog[] nên có thể thêm Cat.” | JVM kiểm tra runtime component type, có thể ArrayStoreException. |
| “Integer object cast thành Long để đổi số.” | Reference cast không chuyển wrapper object; dùng number conversion API. |
| “Ép `double` sang `int` có CCE nếu mất phần thập phân.” | Numeric cast theo quy tắc số, không có CCE. |
| “ClassCastException luôn có message cố định.” | Không dựa vào message/stack trace khi test logic. |
| “Chỉ cần instanceof là mọi state thread-safe.” | Type test không bảo vệ mutable state. |
| “Chuỗi instanceof luôn là đa hình tốt.” | Có thể là dấu hiệu nên đưa behavior vào interface/subtype. |

## 25. Checklist đọc một đoạn Java có cast

Trước khi chấp nhận `(Dog) value`, tự hỏi:

1. **`value` có kiểu tĩnh nào?** Vì sao caller chỉ có supertype?
2. **Runtime object nào có thể xuất hiện?** Dog, Cat, null hay implementation khác?
3. **Cast có hợp lệ về mặt ngôn ngữ/compile time không?**
4. **Ai bảo đảm runtime object thật là Dog?** API invariant, type pattern, class token?
5. **Nếu sai subtype, contract mong muốn là gì?** Bỏ qua, trả Optional, báo lỗi hay exception?
6. **Downcast có thật sự cần?** Có thể gọi common polymorphic method không?
7. **Cast có tạo object mới không?** Không; đừng chờ state được chuyển đổi.
8. **Có dùng `instanceof Dog dog` để gắn type test và tham chiếu cùng nhau không?**
9. **Pattern variable còn trong scope ở chỗ dùng không?**
10. **Có kiểm tra null và state hợp lệ không?**
11. **Có overloads khiến compiler chọn method khác với điều mình tưởng không?**
12. **Nếu là collection generic, cast có unchecked warning không?**
13. **Nếu là array, component type runtime là gì?**
14. **Nếu là wrapper, bạn đang cần chuyển giá trị số hay chuyển kiểu object?**
15. **Nếu references là mutable fields, check và cast có dùng cùng snapshot không?**
16. **Có test với ít nhất Dog, Cat, null và một subtype mới trong tương lai không?**

## 26. Bài tập tự kiểm tra và đáp án

**Câu 1.** `Dog dog = new Dog(); Animal animal = dog;` có tạo bao nhiêu objects?  
**Đáp án:** Một Dog object, hai references tới cùng object.

**Câu 2.** `Animal animal = new Dog(); animal.bark();` có biên dịch không, nếu chỉ Dog khai báo bark?  
**Đáp án:** Không. Kiểu tĩnh Animal không công bố bark().

**Câu 3.** `animal.sound()` có thể chạy Dog.sound khi Animal khai báo sound và Dog override?  
**Đáp án:** Có. Đây là dynamic dispatch.

**Câu 4.** `Dog d = (Dog) animal;` thành công khi nào?  
**Đáp án:** Khi runtime value null hoặc tham chiếu object phù hợp Dog (với null cast trả null); với non-null Animal trỏ Dog/subtype thì thành công.

**Câu 5.** Nếu animal runtime là Cat nhưng code cast Dog thì gì xảy ra?  
**Đáp án:** `ClassCastException` tại runtime nếu cast được compiler cho phép.

**Câu 6.** Compiler có luôn từ chối `(Dog) animal` vì Animal rộng hơn Dog không?  
**Đáp án:** Không. Narrowing reference cast có thể hợp lệ ở compile time và được runtime kiểm tra.

**Câu 7.** `null instanceof Dog` bằng gì?  
**Đáp án:** `false`.

**Câu 8.** `Dog dog = (Dog) null;` có ném CCE không?  
**Đáp án:** Không. dog nhận null.

**Câu 9.** `dog.bark()` khi dog null sẽ gây lỗi gì?  
**Đáp án:** `NullPointerException` vì gọi instance method qua null.

**Câu 10.** `if (value instanceof Dog dog)` đã tạo Dog mới không?  
**Đáp án:** Không, pattern variable giữ reference đã match.

**Câu 11.** Vì sao `value instanceof String text && text.length()>3` hợp lệ?  
**Đáp án:** Short-circuit `&&` chỉ chạy vế phải sau khi pattern đã match.

**Câu 12.** Vì sao `value instanceof String text || text.isBlank()` sai?  
**Đáp án:** Vế phải chạy khi vế trái false, text chưa được pattern ràng buộc.

**Câu 13.** Java 17 có cần `--enable-preview` cho `instanceof Dog dog` không?  
**Đáp án:** Không. Pattern matching for instanceof đã là tính năng chuẩn.

**Câu 14.** Hai interface Printable và Scannable không extends nhau; một object có thể thỏa cả hai không?  
**Đáp án:** Có, class có thể implement cả hai.

**Câu 15.** `Object o = "hello"; Integer x = (Integer) o;` lỗi lúc nào?  
**Đáp án:** Runtime `ClassCastException` vì object thật là String.

**Câu 16.** Cast trực tiếp giữa String và Integer ở tình huống class final không liên quan có được không?  
**Đáp án:** Không; compiler có thể xác định inconvertible types.

**Câu 17.** `Animal a = new Dog(); inspect(a)` chọn overload Animal hay Dog khi có cả hai?  
**Đáp án:** Chọn Animal theo kiểu tĩnh argument a.

**Câu 18.** `a.speak()` với a kiểu Animal runtime Dog chọn implementation nào?  
**Đáp án:** Dog.speak nếu override hợp lệ.

**Câu 19.** `a.getClass()==Animal.class` và `a instanceof Animal` giống nhau khi a runtime Dog không?  
**Đáp án:** Không: so exact class false, instanceof Animal true.

**Câu 20.** `Animal.class.isAssignableFrom(Dog.class)` trả gì?  
**Đáp án:** `true` vì Dog là subtype phù hợp của Animal.

**Câu 21.** `List<Dog>` gán cho `List<Animal>` được không?  
**Đáp án:** Không theo generic invariance.

**Câu 22.** `value instanceof List<String>` dùng để xác minh elements kiểu String được không?  
**Đáp án:** Không; tham số generic không reifiable ở runtime cho kiểu test này.

**Câu 23.** Cast unchecked từ List<Integer> thành List<String> có chắc ném ngay CCE không?  
**Đáp án:** Không. Do erasure, lỗi có thể đến muộn khi lấy một Integer dùng như String.

**Câu 24.** `Animal[] animals = new Dog[1]; animals[0]=new Cat();` ném gì?  
**Đáp án:** `ArrayStoreException` nếu runtime array là Dog[].

**Câu 25.** `int i=(int)3.9;` có ném ClassCastException không?  
**Đáp án:** Không; đây là numeric conversion, kết quả 3.

**Câu 26.** `Object o=Integer.valueOf(7); Long l=(Long)o;` có phải chuyển Integer thành Long không?  
**Đáp án:** Không; ném CCE. Muốn lấy long value dùng `((Number)o).longValue()` khi phù hợp.

**Câu 27.** Có nên dùng `instanceof` để kiểm tra số dư ngân hàng hợp lệ không?  
**Đáp án:** Không đủ. `instanceof` chỉ kiểm tra kiểu, không kiểm tra business invariant.

**Câu 28.** Khi nhiều subtypes cùng có `fee()`, nên viết chuỗi instanceof hay common interface?  
**Đáp án:** Thường ưu tiên interface/superclass method và polymorphism nếu behavior thuộc contract chung.

**Câu 29.** Pattern `instanceof` có làm object thread-safe không?  
**Đáp án:** Không. Runtime type checking không đồng bộ mutable state.

**Câu 30.** Điều quan trọng nhất khi downcasting là gì?  
**Đáp án:** **Runtime object phải tương thích với kiểu đích**, không chỉ compiler chấp nhận một cú pháp cast.

## 27. Tài liệu tham khảo

- Java Language Specification (Java SE 17), [`4.10 — Subtyping](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10): quan hệ subtype/supertype.
- Java Language Specification, [`5.1.5 — Widening Reference Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.5): upcasting và widening reference conversions.
- Java Language Specification, [`5.1.6 — Narrowing Reference Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.6): downcasting.
- Java Language Specification, [`5.5 — Casting Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.5): conversions trong cast.
- Java Language Specification, [`15.16 — Cast Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.16): cú pháp/ý nghĩa cast expressions.
- Java Language Specification, [`15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type tests và patterns.
- Java Language Specification, [`14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30): pattern matching Java 17.
- Java Language Specification, [`6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): pattern-variable flow scoping.
- Java Language Specification, [`15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): overload resolution và runtime invocation.
- Java Language Specification, [`4.7 — Reifiable Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.7): giới hạn type tests với generics.
- Java Language Specification, [`10.5 — Array Store Exception](https://docs.oracle.com/javase/specs/jls/se17/html/jls-10.html#jls-10.5): runtime component type checks.
- Java Platform API, [`ClassCastException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassCastException.html): exception ép kiểu.
- Java Platform API, [`Class.isInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isInstance(java.lang.Object)): runtime type test qua class token.
- Java Platform API, [`Class.cast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#cast(java.lang.Object)): cast qua class token.

## Kết luận

**Upcasting** cho phép một reference subtype được dùng qua superclass/interface an toàn mà không tạo object mới. **Downcasting** lấy lại một góc nhìn subtype cụ thể nhưng phải thỏa **runtime object compatibility**; nếu object thực không có kiểu phù hợp, Java có thể ném `ClassCastException`.

Hãy nhớ **kiểu tĩnh** quyết định những member nào compiler cho dùng và overload nào được chọn, còn **kiểu runtime** quyết định overridden instance method implementation và kết quả type checks. `instanceof`, đặc biệt **type patterns trong Java 17**, giúp kiểm tra runtime type trước khi dùng subtype-specific behavior. Null không match `instanceof`, còn null reference cast được nhưng dereference có thể NPE.

Với collections, type erasure khiến unchecked generic casts không chứng minh types của từng element; với arrays, covariance có thể đưa lỗi vào runtime dưới dạng `ArrayStoreException`. Khi nhiều subtypes cùng thực hiện behavior chung, hãy **ưu tiên polymorphism** thay vì chuỗi downcasts dài. Chỉ downcast khi có hợp đồng và lý do rõ, xử lý nhánh kiểu không phù hợp một cách chủ động.
