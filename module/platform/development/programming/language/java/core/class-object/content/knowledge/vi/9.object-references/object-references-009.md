# Kiểu khai báo của biến và lớp thực tế của đối tượng trong Java

Khi một biến Java có **kiểu tham chiếu (reference type)**, ta cần phân biệt **kiểu được khai báo của biến** với **lớp thực tế của đối tượng mà biến đang tham chiếu**. Hai khái niệm thường trùng nhau trong ví dụ đơn giản, nhưng có thể khác nhau khi có **kế thừa, interface, đa hình, chuyển kiểu, generic hoặc các phép gán tham chiếu**.

Ví dụ:

```java
Animal animal = new Dog();
```

- **`Animal`** ở bên trái là **kiểu khai báo của biến `animal`** (*declared type*). Khi biểu thức chỉ gồm tên biến `animal`, đó cũng là **kiểu của biểu thức tại thời điểm biên dịch** (*compile-time/static type*).
- **`Dog`** ở bên phải là lớp được nêu trong biểu thức `new Dog()`. Đối tượng mới tạo có **lớp thực tế `Dog`** (*runtime class*).
- Giá trị nằm trong `animal` là **tham chiếu đến đối tượng `Dog`**. Java **không chuyển đối tượng Dog thành đối tượng Animal** khi gán; chỉ xem tham chiếu ấy thông qua kiểu rộng hơn.
- Compiler cho phép gọi những thành viên có thể truy cập từ kiểu tĩnh `Animal`, nhưng khi gọi một **instance method bị override**, implementation thực thi có thể được chọn từ lớp thực tế `Dog` tại runtime.

**Nguyên tắc quan trọng:** *Kiểu tĩnh quy định những thao tác nào được phép viết và cách giải quyết một số tên/tham số ở compile time; lớp thực tế ảnh hưởng đến triển khai instance method được override và những kiểm tra kiểu tại runtime.*

Bài này trình bày từ nền tảng đến các tình huống dễ nhầm: upcasting, downcasting, `instanceof`, `getClass()`, overriding/overloading, field hiding, `static`, `null`, interface, mảng, generic, `var`, thay đổi tham chiếu và bài thực hành Java 17.

## 1. Biến tham chiếu, giá trị tham chiếu và đối tượng

Xét khai báo:

```java
Dog dog = new Dog();
```

Để hiểu chính xác dòng này, tách thành ba phần:

| Thành phần | Trong ví dụ | Giải thích |
| --- | --- | --- |
| **Biến** | `dog` | Vị trí lưu **giá trị tham chiếu**; biến có kiểu khai báo `Dog` |
| **Giá trị tham chiếu** | Giá trị được nhận từ `new Dog()` | Dùng để truy cập một đối tượng; không phải bản sao mọi field |
| **Đối tượng** | Thể hiện mới của `Dog` | Có identity, trạng thái field và lớp thực tế được xác định khi tạo |

Sơ đồ khái niệm:

```text
Biến dog (kiểu tĩnh Dog)
          |
          | giá trị tham chiếu
          v
Đối tượng #1 (lớp thực tế Dog)
    ├── các field kế thừa
    └── các field khai báo trong Dog
```

`#1` là ký hiệu minh họa, không phải địa chỉ bộ nhớ. Java không yêu cầu người viết dùng địa chỉ bộ nhớ thật để thao tác với tham chiếu.

Khi viết:

```java
Animal animal = dog;
```

thì `dog` và `animal` cùng giữ giá trị tham chiếu tới **một đối tượng `Dog`**, nhưng **kiểu khai báo hai biến khác nhau**:

```text
dog    : Dog    ───┐
                   ├──> cùng một đối tượng #1, runtime class = Dog
animal : Animal ───┘
```

Không có đối tượng `Animal` mới nào được tự tạo bởi phép gán `animal = dog`.

### So sánh với kiểu nguyên thủy

`int n = 10;` có kiểu primitive `int`; không có đối tượng lớp `Integer` nhất thiết được tạo cho chính giá trị primitive ấy. Khái niệm **runtime class của đối tượng được tham chiếu** chỉ có ý nghĩa trực tiếp khi một tham chiếu trỏ tới đối tượng.

Trong bài này, các ví dụ kiểu `Animal`, `Dog` và `Cat` là những lớp tham chiếu; từ khóa `int`, `boolean` được dùng để so sánh khi cần.

## 2. Kiểu tĩnh và lớp thực tế: hai câu hỏi khác nhau

Hãy luôn hỏi riêng:

1. **Biểu thức có kiểu nào tại compile time?** Nếu biểu thức là tên biến, đọc **khai báo biến**. Nếu biểu thức là phép ép kiểu, lời gọi method, toán tử điều kiện hoặc `new`, phải xét quy tắc xác định kiểu cho **toàn bộ biểu thức** đó.
2. **Khi chạy, tham chiếu đang trỏ đối tượng của lớp nào?** Điều này phụ thuộc đối tượng được tạo, giá trị tham chiếu được truyền/gán, và trạng thái chương trình tại thời điểm xét.

Ví dụ:

```java
Animal pet = new Dog();
```

Đối với **biểu thức `pet`**:
- Kiểu tĩnh: `Animal`.
- Runtime class của đối tượng được tham chiếu: `Dog`.

Đối với **biểu thức `new Dog()`**:
- Kiểu compile time: `Dog`.
- Đối tượng mới có runtime class: `Dog`.

Đối với **biểu thức `(Animal) new Dog()`**:
- Kiểu compile time của **toàn biểu thức sau cast**: `Animal`.
- Đối tượng được tham chiếu vẫn có runtime class `Dog`.

Một đối tượng có thể được quan sát qua nhiều biến hoặc biểu thức kiểu khác nhau mà **lớp thực tế của chính đối tượng không thay đổi**. Chỉ khi biến được **gán tham chiếu đến đối tượng khác** thì lớp thực tế của đối tượng *hiện được biến tham chiếu* mới có thể khác.

## 3. Ví dụ hoàn chỉnh: cùng object, khác kiểu khai báo

Lưu thành **`DeclaredVsRuntimeDemo.java`**:

```java
class Animal {
    String kind() {
        return "Animal";
    }

    String speak() {
        return "Âm thanh chung";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "Gâu";
    }

    String fetch() {
        return "Đang nhặt bóng";
    }
}

public class DeclaredVsRuntimeDemo {
    public static void main(String[] args) {
        Dog dog = new Dog();
        Animal pet = dog;
        Object unknown = dog;

        System.out.println(dog == pet);
        System.out.println(pet == unknown);
        System.out.println(pet.getClass().getSimpleName());

        System.out.println(pet.kind());
        System.out.println(pet.speak());
        System.out.println(dog.fetch());

        // pet.fetch();     // SAI: Animal không khai báo fetch()
        // unknown.speak(); // SAI: Object không khai báo speak()
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 DeclaredVsRuntimeDemo.java
java DeclaredVsRuntimeDemo
```

**Stdout chính xác:**

```text
true
true
Dog
Animal
Gâu
Đang nhặt bóng
```

Giải thích:

- `dog`, `pet` và `unknown` cùng tham chiếu một đối tượng `Dog`, vì vậy hai phép `==` đều đúng.
- `pet.getClass().getSimpleName()` cho biết tên đơn giản của **lớp thực tế** đối tượng: `Dog`.
- `pet.kind()` hợp lệ vì kiểu tĩnh `Animal` khai báo `kind()`; `Dog` không override method này nên kết quả là `Animal`.
- `pet.speak()` cũng hợp lệ qua kiểu `Animal`. Tuy nhiên `Dog` **override** method `speak()` nên runtime thực thi triển khai trong `Dog`, in `Gâu`.
- `dog.fetch()` hợp lệ vì `dog` có kiểu tĩnh `Dog` và `Dog` khai báo `fetch()`.
- `pet.fetch()` **không biên dịch**, dù `pet` đang trỏ đến đối tượng `Dog`, bởi `fetch()` không có trong tập method có thể truy cập thông qua kiểu tĩnh `Animal`.
- `unknown.speak()` **không biên dịch** vì kiểu tĩnh của `unknown` chỉ là `Object`, không khai báo `speak()`.

**Rút ra:** chỉ xem runtime class để dự đoán lời gọi hợp lệ là không đủ. Compiler còn phải kiểm tra kiểu **biểu thức bên trái dấu chấm**.

## 4. Upcasting: dùng một tham chiếu kiểu con như kiểu cha

**Upcasting** là việc sử dụng tham chiếu đến đối tượng của một kiểu con ở vị trí đòi hỏi kiểu cha hoặc interface phù hợp.

```java
Dog dog = new Dog();
Animal animal = dog;     // Upcast tự động
Object object = dog;     // Upcast rộng hơn
```

Với kế thừa `Dog extends Animal`:

- `Dog` là subtype của `Animal`.
- `Animal` là subtype của `Object`.
- Java cho phép chuyển tham chiếu `Dog` sang `Animal` hoặc `Object` qua **widening reference conversion** trong nhiều ngữ cảnh hợp lệ.
- Thao tác **không tạo đối tượng mới** và không xóa phần dữ liệu hay phương thức của `Dog`.
- Sau upcast, **kiểu tĩnh của biến nhận** hạn chế những method/field có thể truy cập qua biến đó.

Ví dụ:

```java
Animal animal = new Dog();
animal.speak();         // Hợp lệ
// animal.fetch();      // Lỗi biên dịch
```

`animal` chỉ nhìn thấy API được kiểu `Animal` cho phép. Điều này là đặc tính quan trọng của **đa hình theo subtype** (*subtype polymorphism*): mã có thể làm việc với kiểu chung mà không cần biết cụ thể từng lớp con.

### Upcasting sang interface

```java
interface Payable {
    int amount();
}

class Invoice implements Payable {
    private final int total;

    Invoice(int total) {
        this.total = total;
    }

    @Override
    public int amount() {
        return total;
    }

    String label() {
        return "Invoice";
    }
}
```

Với `Payable p = new Invoice(200);`:

- Kiểu tĩnh của `p` là **interface `Payable`**.
- Runtime class của đối tượng là **`Invoice`**.
- `p.amount()` hợp lệ và được triển khai bởi `Invoice`.
- `p.label()` không hợp lệ vì `Payable` không khai báo `label()`.

Gán tham chiếu qua interface không tạo “một nửa đối tượng Invoice”; vẫn là một đối tượng `Invoice` nguyên vẹn, chỉ được nhìn qua hợp đồng `Payable`.

## 5. Downcasting: khi cần dùng khả năng riêng của lớp con

Để gọi method chỉ có trên lớp con qua một biến kiểu cha, đôi khi cần **downcast** (ép tham chiếu từ kiểu rộng sang kiểu hẹp).

```java
Animal animal = new Dog();
Dog dog = (Dog) animal;
System.out.println(dog.fetch()); // Đang nhặt bóng
```

Ở đây:

1. `animal` có kiểu tĩnh `Animal`.
2. `(Dog) animal` là biểu thức có kiểu tĩnh `Dog` nhờ cast.
3. Đối tượng thực tế đang là `Dog` nên phép cast **thành công tại runtime**.
4. `dog` tham chiếu **chính đối tượng cũ**. Cast không clone, không chuyển hóa object, không sửa field.

### 5.1. Cast có thể biên dịch nhưng thất bại khi chạy

```java
Animal animal = new Cat();
Dog dog = (Dog) animal;
```

Giả sử `Cat extends Animal` và `Dog extends Animal` như hai lớp con riêng. Compiler có thể cho phép cast từ kiểu tĩnh `Animal` sang `Dog`, nhưng tại runtime đối tượng thực tế là `Cat` nên xảy ra **`ClassCastException`**.

Java không “biến Cat thành Dog” bằng cast. Cast chỉ yêu cầu JVM **kiểm tra** rằng tham chiếu thực tế tương thích với kiểu được yêu cầu.

### 5.2. Cast có thể bị phát hiện là không thể từ compile time

Không phải mọi cast giữa hai lớp bất kỳ đều hợp lệ về cú pháp/kiểu:

```java
Dog dog = new Dog();
// Cat cat = (Cat) dog; // Lỗi biên dịch với hai lớp sibling không liên quan
```

Vì cả hai kiểu sibling không có quan hệ chuyển đổi hợp lệ trực tiếp trong ngữ cảnh này, compiler có thể bác bỏ ngay. Nếu nhận một biến kiểu cha rồi cast sang lớp con, thông tin tĩnh cho phép kiểm tra ở runtime.

### 5.3. Cách an toàn: `instanceof` và pattern matching Java 17

`instanceof` kiểm tra xem tham chiếu tại runtime có tương thích với kiểu cần hỏi hay không. Java 17 hỗ trợ **pattern matching for instanceof**:

```java
static String action(Animal animal) {
    if (animal instanceof Dog dog) {
        return dog.fetch();
    }
    return "Không phải Dog";
}
```

Khi điều kiện đúng, biến mẫu `dog` có kiểu tĩnh `Dog` và tham chiếu đến **đối tượng ban đầu**. Không cần cast thêm.

Nếu `animal == null`, biểu thức `animal instanceof Dog` trả **`false`**; không ném `NullPointerException` chỉ vì kiểm tra.

## 6. Chương trình Java 17: kiểm tra runtime class và cast an toàn

Lưu thành **`RuntimeTypeCheckDemo.java`**:

```java
class Animal {
    String speak() {
        return "...";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "Gâu";
    }

    String fetch() {
        return "Nhặt bóng";
    }
}

class Cat extends Animal {
    @Override
    String speak() {
        return "Meo";
    }
}

public class RuntimeTypeCheckDemo {
    static String describe(Animal animal) {
        if (animal instanceof Dog dog) {
            return "Dog: " + dog.fetch();
        }
        if (animal instanceof Cat) {
            return "Cat: " + animal.speak();
        }
        if (animal == null) {
            return "Không có đối tượng";
        }
        return "Animal khác";
    }

    public static void main(String[] args) {
        Animal first = new Dog();
        Animal second = new Cat();
        Animal missing = null;

        System.out.println(first.getClass().getSimpleName());
        System.out.println(first instanceof Dog);
        System.out.println(second instanceof Dog);
        System.out.println(missing instanceof Dog);

        System.out.println(describe(first));
        System.out.println(describe(second));
        System.out.println(describe(missing));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 RuntimeTypeCheckDemo.java
java RuntimeTypeCheckDemo
```

**Stdout chính xác:**

```text
Dog
true
false
false
Dog: Nhặt bóng
Cat: Meo
Không có đối tượng
```

**Lưu ý:**

- `getClass()` là instance method. `first.getClass()` hợp lệ vì `first` không null; `missing.getClass()` sẽ ném `NullPointerException`.
- `instanceof` kiểm tra khả năng tương thích runtime với kiểu được nêu, không đòi kiểu chính xác bằng nhau. Chẳng hạn nếu có `class Puppy extends Dog`, đối tượng `Puppy` vẫn thỏa `instanceof Dog`.
- Biến pattern `dog` chỉ có phạm vi hợp lệ mà compiler phân tích được theo luồng điều khiển; không thể dùng nó ngoài phạm vi mà Java chưa bảo đảm điều kiện đúng.

**Thiết kế:** nếu phải dùng chuỗi `instanceof` rất dài để xử lý các subtype, cân nhắc **polymorphic method** hoặc một mẫu thiết kế phù hợp. Kiểm tra kiểu lúc chạy hữu ích nhưng không nên thay thế hoàn toàn thiết kế interface và overriding.

## 7. Method overriding: chọn triển khai dựa trên lớp thực tế

Một instance method đủ điều kiện được **ghi đè** (*override*) ở lớp con:

```java
class Animal {
    String speak() {
        return "Âm thanh";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "Gâu";
    }
}
```

Với:

```java
Animal a = new Dog();
System.out.println(a.speak()); // Gâu
```

Compiler kiểm tra:

- Biểu thức `a` có kiểu tĩnh `Animal`.
- `Animal` khai báo instance method `speak()` có thể gọi.

Khi chạy, **dynamic method dispatch** sử dụng lớp thực tế của receiver để chọn implementation override phù hợp. Vì đối tượng là `Dog`, phiên bản `Dog.speak()` chạy.

Một ép kiểu receiver sang cha **không ép phương thức override của cha chạy**:

```java
Dog dog = new Dog();
System.out.println(((Animal) dog).speak()); // Gâu
```

`((Animal) dog)` có kiểu tĩnh `Animal`, nhưng receiver vẫn là đối tượng `Dog` và lời gọi vẫn được dispatch tới override của `Dog`.

### Muốn gọi implementation của cha?

Trong **thân instance method của lớp con**, từ khóa `super.method()` có cú pháp dispatch đặc biệt:

```java
class Dog extends Animal {
    @Override
    String speak() {
        return super.speak() + " + Gâu";
    }
}
```

`super.speak()` là cách lớp con yêu cầu gọi implementation của superclass. Đây **không** phải cơ chế “cast đối tượng Dog thành Animal” hoặc đổi runtime class.

## 8. Overloading: chữ ký được chọn theo kiểu tại compile time

**Overloading** (*nạp chồng*) khác với overriding. Các overload cùng tên nhưng **khác danh sách tham số**; compiler chọn phương thức áp dụng khi biên dịch dựa trên **kiểu tĩnh của đối số**, số lượng đối số, chuyển đổi kiểu và các quy tắc overload resolution.

Ví dụ:

```java
static void handle(Animal animal) {
    System.out.println("Overload Animal");
}

static void handle(Dog dog) {
    System.out.println("Overload Dog");
}
```

Với:

```java
Animal pet = new Dog();
Dog dog = new Dog();

handle(pet);          // Overload Animal
handle(dog);          // Overload Dog
handle((Dog) pet);    // Overload Dog, vì cast làm kiểu biểu thức thành Dog
```

**Runtime class của `pet` không tự chuyển lời gọi `handle(pet)` sang overload `handle(Dog)`.**

### 8.1. Chương trình đầy đủ: overriding và overloading cạnh nhau

Lưu **`DispatchComparisonDemo.java`**:

```java
class Animal {
    String speak() {
        return "Animal sound";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "Dog sound";
    }
}

public class DispatchComparisonDemo {
    static void show(Animal animal) {
        System.out.println("Overload Animal: " + animal.speak());
    }

    static void show(Dog dog) {
        System.out.println("Overload Dog: " + dog.speak());
    }

    public static void main(String[] args) {
        Animal asAnimal = new Dog();
        Dog asDog = new Dog();

        show(asAnimal);
        show(asDog);
        show((Dog) asAnimal);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 DispatchComparisonDemo.java
java DispatchComparisonDemo
```

Kết quả:

```text
Overload Animal: Dog sound
Overload Dog: Dog sound
Overload Dog: Dog sound
```

Dòng đầu cho thấy **cả hai cơ chế hoạt động trong một lời gọi**:

1. **Compile time:** `show(asAnimal)` chọn overload `show(Animal)` do `asAnimal` có kiểu tĩnh `Animal`.
2. **Runtime trong thân `show(Animal)`:** lời gọi `animal.speak()` thực thi override `Dog.speak()` vì receiver thực tế là `Dog`.

Khi phân tích kết quả, hãy luôn tách **lựa chọn overload** khỏi **dispatch override**.

## 9. Receiver kiểu cha không nhìn thấy mọi thành viên mới của lớp con

Không chỉ đối số: **kiểu tĩnh của receiver bên trái dấu chấm** cũng quyết định compiler có thể thấy tên method nào.

```java
class Parent {
    void common() {
        System.out.println("Common");
    }
}

class Child extends Parent {
    void onlyChild() {
        System.out.println("Only child");
    }
}
```

```java
Parent variable = new Child();
variable.common();        // Hợp lệ
// variable.onlyChild();   // SAI tại compile time
```

`variable` có kiểu tĩnh `Parent`. Dù object thực tế là `Child`, compiler **không cho dùng** `onlyChild()` qua biểu thức kiểu `Parent` vì method này không được khai báo trong API nhìn thấy từ `Parent`.

Nếu thật sự cần chức năng riêng:

```java
if (variable instanceof Child child) {
    child.onlyChild();
}
```

Hoặc **thiết kế API chung** ngay trong `Parent`/interface nếu chức năng đó mang ý nghĩa đa hình, giúp giảm nhu cầu cast.

Một biến kiểu cha không thể “tự cập nhật” danh sách thành viên được phép gọi sau khi bạn gán cho nó một đối tượng lớp con.

## 10. Field hiding: chọn field theo kiểu tĩnh, không theo runtime class

**Trường dữ liệu (field)** không có dynamic dispatch như instance method. Nếu lớp con khai báo field trùng tên với field của lớp cha, đó là **field hiding**.

Ví dụ:

```java
class Animal {
    String label = "Animal field";
}

class Dog extends Animal {
    String label = "Dog field";
}
```

```java
Animal pet = new Dog();
System.out.println(pet.label);           // Animal field
System.out.println(((Dog) pet).label);   // Dog field
```

Vì `pet` có kiểu tĩnh `Animal`, `pet.label` chọn field khai báo ở `Animal`. Sau cast, kiểu tĩnh của receiver là `Dog` nên tên `label` chọn field của `Dog`.

**Đây không phải cùng một field được override.** Một đối tượng `Dog` chứa **hai field khác nhau** cùng tên trong hệ phân cấp, được truy cập thông qua các quy tắc lựa chọn field.

### Chương trình Java 17: field và method cho kết quả khác nhau

Lưu **`FieldAndMethodDemo.java`**:

```java
class Parent {
    String label = "Parent field";

    String label() {
        return "Parent method";
    }
}

class Child extends Parent {
    String label = "Child field";

    @Override
    String label() {
        return "Child method";
    }
}

public class FieldAndMethodDemo {
    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = (Child) parentView;

        System.out.println(parentView.label);
        System.out.println(childView.label);
        System.out.println(parentView.label());
        System.out.println(childView.label());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 FieldAndMethodDemo.java
java FieldAndMethodDemo
```

Stdout:

```text
Parent field
Child field
Child method
Child method
```

Diễn giải:

- Hai lần đọc **field** theo kiểu tĩnh tương ứng `Parent` và `Child`.
- Hai lần gọi **instance method `label()`** theo triển khai override `Child.label()` vì runtime receiver ở cả hai lời gọi là đối tượng `Child`.

**Khuyến nghị:** tránh tạo field trùng tên giữa lớp cha và con vì dễ nhầm với overriding. Ưu tiên field private và API method rõ ý nghĩa khi cần đa hình.

## 11. Static methods không dùng dynamic dispatch như instance methods

Nếu lớp con khai báo static method cùng chữ ký với superclass, đây là **static method hiding** (che khuất), không phải override động.

```java
class Parent {
    static String typeName() {
        return "Parent";
    }
}

class Child extends Parent {
    static String typeName() {
        return "Child";
    }
}
```

Với:

```java
Parent p = new Child();
System.out.println(p.typeName());     // Parent
System.out.println(Child.typeName()); // Child
```

Java cho phép biểu thức `p.typeName()` trong ví dụ, nhưng compiler chọn static method theo **kiểu tĩnh `Parent`**. **Nên viết `Parent.typeName()` thay vì `p.typeName()`** để tránh ấn tượng sai rằng lời gọi sẽ dispatch theo object runtime.

**Tổng kết nhanh:**

| Loại thành viên | Yếu tố chọn chính |
| --- | --- |
| Instance method bị override | Chữ ký được phân tích tại compile time, implementation được dispatch theo runtime receiver |
| Method overloading | Chữ ký overload được xác định theo compile-time types và quy tắc overload |
| Instance field bị hide | Field được chọn dựa trên kiểu của biểu thức nhận tại compile time |
| Static method bị hide | Tên static method được ràng buộc theo quy tắc compile time, không override động |
| Static field | Thuộc lớp được chọn, không là trạng thái riêng của từng object |

Đừng nói “Java luôn chọn theo runtime class” hoặc “Java luôn chọn theo declared type”. Mỗi loại thành viên có **quy tắc cụ thể**.

## 12. `null`: có kiểu tham chiếu nhưng không có đối tượng để hỏi lớp thực tế

Ví dụ:

```java
Animal pet = null;
```

- **Kiểu khai báo biến `pet`** vẫn là `Animal`.
- Giá trị của `pet` hiện là `null`, tức **không tham chiếu đến đối tượng nào**.
- Vì không có đối tượng, không tồn tại “runtime class của object đang được `pet` trỏ đến”.
- `pet instanceof Dog` trả **`false`**.
- `pet.getClass()` ném **`NullPointerException`** khi thực thi.
- Một phép cast tham chiếu `(Dog) pet` với `pet == null` có thể cho ra `null` mà **không** ném `ClassCastException`; cast không tạo object.

### Ví dụ runnable về `null`

Tệp **`NullRuntimeTypeDemo.java`**:

```java
class Animal {
}

class Dog extends Animal {
}

public class NullRuntimeTypeDemo {
    public static void main(String[] args) {
        Animal pet = null;

        System.out.println(pet == null);
        System.out.println(pet instanceof Dog);

        Dog casted = (Dog) pet;
        System.out.println(casted == null);

        try {
            System.out.println(pet.getClass().getSimpleName());
        } catch (NullPointerException exception) {
            System.out.println("Không có đối tượng để gọi getClass()");
        }
    }
}
```

```bash
javac -encoding UTF-8 NullRuntimeTypeDemo.java
java NullRuntimeTypeDemo
```

Stdout:

```text
true
false
true
Không có đối tượng để gọi getClass()
```

**Chú ý:** `null` không có runtime class nhưng biểu thức có `null` vẫn tham gia kiểm tra kiểu compile time. Chẳng hạn một literal `null` có thể truyền cho tham số kiểu `String` hoặc `Integer`, và nếu có hai overload không thể phân biệt, `f(null)` có thể bị báo **ambiguous**.

## 13. Một biến có thể lần lượt tham chiếu các lớp thực tế khác nhau

Ví dụ:

```java
Animal current = new Dog();
System.out.println(current.getClass().getSimpleName()); // Dog

current = new Cat();
System.out.println(current.getClass().getSimpleName()); // Cat
```

Giả sử `Dog` và `Cat` đều extends `Animal`. **Kiểu khai báo `current` vẫn là `Animal`** suốt thời gian tồn tại của biến. Nhưng giá trị tham chiếu được gán vào biến đã thay đổi, nên đối tượng đang được trỏ đến có runtime class khác.

**Không được hiểu đối tượng `Dog` ban đầu đã bị chuyển lớp thành `Cat`.** Phép gán `current = new Cat()` chọn một đối tượng **khác** cho biến `current`.

### Ví dụ chương trình xác định rõ sau khi gán lại

Tệp **`ReassignmentTypeDemo.java`**:

```java
class Animal {
    String speak() {
        return "?";
    }
}

class Dog extends Animal {
    @Override
    String speak() {
        return "Gâu";
    }
}

class Cat extends Animal {
    @Override
    String speak() {
        return "Meo";
    }
}

public class ReassignmentTypeDemo {
    public static void main(String[] args) {
        Animal current = new Dog();
        Animal saved = current;

        System.out.println(current.speak());
        current = new Cat();
        System.out.println(current.speak());
        System.out.println(saved.speak());
        System.out.println(current == saved);
    }
}
```

```bash
javac -encoding UTF-8 ReassignmentTypeDemo.java
java ReassignmentTypeDemo
```

Stdout:

```text
Gâu
Meo
Gâu
false
```

`saved` vẫn tham chiếu đối tượng `Dog` cũ. Sau khi `current` đổi sang `Cat`, **dynamic dispatch** của `speak()` trên mỗi biến cho kết quả theo runtime object tương ứng.

## 14. `Object` là kiểu tham chiếu rộng, không đồng nghĩa mọi method đều truy cập được

Các lớp Java thông thường kế thừa từ `Object` trực tiếp hoặc gián tiếp. Có thể khai báo:

```java
Object value = "Java";
```

Đối tượng thực tế ở đây là `String`, nhưng qua biến kiểu `Object`, compiler chỉ cho phép những thành viên thuộc API của `Object` và các quy tắc kiểu áp dụng:

```java
System.out.println(value.getClass().getSimpleName()); // String
System.out.println(value.toString());                  // Java

// value.length(); // SAI: Object không khai báo length()
```

Nếu kiểm tra:

```java
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

thì trong nhánh hợp lệ, biến mẫu `text` có kiểu tĩnh `String`.

**Không nên dùng `Object` cho mọi biến** chỉ để “linh hoạt”. Một kiểu quá rộng làm mất khả năng kiểm tra và hỗ trợ API ở compile time, tăng số lần cần cast. Hãy khai báo kiểu **đủ tổng quát cho hợp đồng** nhưng vẫn thể hiện đúng những thao tác mà mã cần.

Ví dụ thường ưu tiên `List<String>` thay vì `Object` cho biến lưu danh sách chuỗi, hoặc `Payable` thay vì `Object` nếu mã chỉ cần gọi `amount()`.

## 15. Interface và abstract class là kiểu biến hợp lệ nhưng không phải object cần tạo trực tiếp

Interface và abstract class có thể làm **kiểu khai báo** của biến:

```java
interface Shape {
    double area();
}

class Square implements Shape {
    private final double side;

    Square(double side) {
        this.side = side;
    }

    @Override
    public double area() {
        return side * side;
    }
}
```

```java
Shape shape = new Square(3);
System.out.println(shape.area()); // 9.0
```

Biến `shape` có kiểu tĩnh `Shape`, đối tượng thực tế có lớp `Square`. Không có đối tượng “interface Shape” được tạo trực tiếp: interface định nghĩa một **hợp đồng kiểu**, còn object được tạo từ một lớp cụ thể.

Tương tự:

```java
abstract class Vehicle {
    abstract String move();
}

class Car extends Vehicle {
    @Override
    String move() {
        return "Drive";
    }
}
```

`Vehicle v = new Car();` hợp lệ; `new Vehicle()` không hợp lệ vì `Vehicle` là abstract class.

**Tránh lẫn lộn ba câu:**

- “Biến có **kiểu interface** `Shape`” — đúng.
- “Đối tượng `Square` **triển khai interface** `Shape`” — đúng.
- “Đối tượng được tạo là một instance của **interface** theo nghĩa một object được khởi tạo trực tiếp bằng `new Shape()`” — không đúng.

Có thể nói đối tượng `Square` **là một thể hiện của kiểu `Shape`** theo quan hệ subtype và kiểm tra `instanceof Shape`, nhưng **lớp thực tế** vẫn là `Square`.

## 16. Kiểu tĩnh ảnh hưởng việc chọn overload khi nhận tham số kiểu interface

Ví dụ:

```java
interface Worker {
    String work();
}

class Developer implements Worker {
    @Override
    public String work() {
        return "Code";
    }
}
```

Với hai overload:

```java
static void process(Worker worker) {
    System.out.println("Worker");
}

static void process(Developer developer) {
    System.out.println("Developer");
}
```

Nếu:

```java
Worker w = new Developer();
Developer d = new Developer();

process(w); // Worker
process(d); // Developer
```

Cả `w` và `d` đều có thể tham chiếu object `Developer`, nhưng overload được chọn theo **kiểu biểu thức đối số**.

Trong khi đó `w.work()` vẫn gọi triển khai `Developer.work()` nhờ **instance method overriding**.

**Một thiết kế tốt:** nếu hai overload mang hành vi nghiệp vụ hoàn toàn khác nhau, cân nhắc đặt tên method rõ nghĩa hoặc sử dụng polymorphic method để tránh phụ thuộc không mong muốn vào kiểu khai báo của biến.

## 17. `getClass()` và `instanceof` khác nhau ở mục đích

Hai cách kiểm tra runtime type thông dụng:

| Cách | Ý nghĩa | Đặc điểm |
| --- | --- | --- |
| `obj.getClass()` | Lấy đối tượng `Class` biểu thị **lớp thực tế chính xác** của receiver | Receiver **không được null**; trả `Class<?>` theo ngữ cảnh |
| `obj instanceof Dog` | Kiểm tra object có tương thích với kiểu `Dog` theo quy tắc `instanceof` hay không | `null instanceof Dog` là `false`; subtype của Dog cũng có thể đúng |
| `obj.getClass() == Dog.class` | Kiểm tra **đúng lớp `Dog`**, không phải subclass | Receiver phải khác null |
| `Dog.class.isInstance(obj)` | Kiểm tra thông qua reflection-like Class API xem obj là instance của Dog hay subtype | Với `null` trả false |
| `obj instanceof Dog d` | Kiểm tra + giới thiệu biến pattern `d` trong nhánh hợp lệ (Java 17) | Tránh cast lặp lại |

Nếu có:

```java
class Dog extends Animal {
}

class Puppy extends Dog {
}
```

thì với `Animal animal = new Puppy();`:

- `animal instanceof Dog` là **`true`**.
- `animal.getClass() == Dog.class` là **`false`**.
- `animal.getClass() == Puppy.class` là **`true`**.
- `Dog.class.isInstance(animal)` là **`true`**.

**Mức học cần nhớ:** `instanceof` dùng kiểm tra **tương thích subtype**, còn `getClass() == Type.class` thường kiểm tra **lớp chính xác**. Không chọn một cách kiểm tra chỉ vì tên gần với mục tiêu; cần xem API yêu cầu đa hình hay chính xác.

### Đừng lạm dụng `getClass()` để điều khiển nghiệp vụ

Ví dụ:

```java
if (animal.getClass() == Dog.class) {
    // Chỉ nhận chính lớp Dog, không nhận subclass Dog.
}
```

Đoạn này có thể làm mất tính mở rộng: lớp con `Puppy` sẽ không thỏa. Nếu hành vi có thể được biểu diễn bằng method được override, thường tốt hơn là gọi method đa hình thay vì phân nhánh liên tục theo lớp runtime. Cách kiểm tra lớp chính xác vẫn hữu ích khi **đó chính là quy tắc nghiệp vụ**, chẳng hạn một số chính sách so sánh hoặc xử lý serialisation.

## 18. Arrays: kiểu biến mảng và kiểu mảng thực tế

Mảng trong Java là đối tượng và cũng có kiểu runtime cụ thể. Mảng tham chiếu có tính **covariant**: trong nhiều tình huống, `String[]` có thể được gán cho biến kiểu `Object[]`.

```java
Object[] items = new String[]{"A", "B"};
```

Ở đây:

- Kiểu khai báo của biến `items` là `Object[]`.
- Kiểu runtime của đối tượng mảng là `String[]`.
- `items[0] = "C";` hợp lệ vì `String` tương thích với kiểu thành phần runtime của mảng.
- `items[1] = Integer.valueOf(42);` **biên dịch được** qua kiểu tĩnh phần tử `Object`, nhưng **ném `ArrayStoreException` tại runtime** vì mảng thực tế chỉ chứa `String`.

### Ví dụ Java 17 runnable

Lưu **`ArrayRuntimeTypeDemo.java`**:

```java
import java.util.Arrays;

public class ArrayRuntimeTypeDemo {
    public static void main(String[] args) {
        Object[] items = new String[]{"A", "B"};

        System.out.println(items.getClass() == String[].class);
        items[0] = "C";
        System.out.println(Arrays.toString(items));

        try {
            items[1] = Integer.valueOf(42);
        } catch (ArrayStoreException exception) {
            System.out.println("Không thể lưu Integer vào String[]");
        }

        System.out.println(Arrays.toString(items));
    }
}
```

```bash
javac -encoding UTF-8 ArrayRuntimeTypeDemo.java
java ArrayRuntimeTypeDemo
```

Stdout:

```text
true
[C, B]
Không thể lưu Integer vào String[]
[C, B]
```

**Điểm rút ra:** kiểu tĩnh `Object[]` cho phép compiler xem phép gán phần tử `Object` là hợp lệ, nhưng JVM còn **kiểm tra kiểu phần tử thực của mảng** để bảo vệ object mảng `String[]`.

**Đừng suy luận primitive arrays giống reference arrays:** `int[]` có thể gán cho `Object` nhưng **không phải subtype của `Object[]`**:

```java
Object any = new int[]{1, 2}; // Hợp lệ
// Object[] array = new int[]{1, 2}; // SAI
```

Mảng nguyên thủy `int[]` là một đối tượng, nhưng các phần tử `int` không phải object tham chiếu tương thích với `Object[]`.

## 19. Generics: kiểu tham chiếu có cả tham số kiểu

Với generic, kiểu tĩnh không chỉ là tên lớp “thô”. Chẳng hạn:

```java
java.util.List<String> names = new java.util.ArrayList<>();
```

- Kiểu khai báo của biến là **`List<String>`**.
- Lớp thực tế của đối tượng collection là **`ArrayList`**.
- `ArrayList` triển khai `List`.
- Thông tin `String` trong `List<String>` phục vụ kiểm tra kiểu **compile time**. Do *type erasure*, `names.getClass()` không cho biết trực tiếp “`ArrayList<String>`” như một lớp runtime có tham số `String` riêng.

### 19.1. Generic không covariant như mảng

Đoạn sau **không hợp lệ**:

```java
java.util.List<String> strings = new java.util.ArrayList<>();
// java.util.List<Object> objects = strings; // SAI: generic invariant
```

Dù `String` là subtype của `Object`, điều đó **không** làm `List<String>` trở thành subtype của `List<Object>`.

Nếu cho phép, một đoạn `objects.add(42)` có thể phá vỡ cam kết rằng mọi phần tử của `strings` là `String`. Vì vậy hệ kiểu generic của Java không cho chuyển như trên.

### 19.2. Dùng wildcard khi cần nhìn qua một kiểu rộng

```java
java.util.List<? extends Animal> animals =
        new java.util.ArrayList<Dog>();
```

Có thể đọc một phần tử dưới kiểu `Animal`:

```java
// Animal first = animals.get(0); // Hợp lệ về kiểu nếu có phần tử
```

Nhưng không thể tùy ý thêm `Dog` hoặc `Cat` vào một `List<? extends Animal>` vì compiler không biết kiểu phần tử cụ thể ở đầu nhận:

```java
// animals.add(new Dog()); // SAI về kiểu
```

**Điểm trung tâm:** với generic, nhìn thấy runtime class `ArrayList` không đủ để suy ra kiểu phần tử biên dịch `String`/`Dog`. Cần đọc **khai báo generic** và các ràng buộc wildcard.

### 19.3. Ví dụ runnable: interface, generic và runtime class

Tệp **`GenericReferenceDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class GenericReferenceDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");
        names.add("Bình");

        System.out.println(names.getClass().getSimpleName());
        System.out.println(names.get(0));
        System.out.println(names.size());
        System.out.println(names instanceof ArrayList);
    }
}
```

```bash
javac -encoding UTF-8 GenericReferenceDemo.java
java GenericReferenceDemo
```

Stdout:

```text
ArrayList
An
2
true
```

`names` có kiểu tĩnh `List<String>`; lớp thực tế là `ArrayList`. Method `get` trả về giá trị được hệ kiểu biểu diễn là `String` ở nơi gọi, dù runtime class của collection không riêng biệt hóa theo `String`.

### 19.4. Không thể dùng `instanceof List<String>` như cách kiểm tra runtime thông thường

Do type erasure, không thể đơn giản viết:

```java
Object value = new ArrayList<String>();
// if (value instanceof List<String>) { } // SAI: kiểu tham số hóa không reifiable
```

Có thể kiểm tra kiểu raw runtime theo cách hợp lệ:

```java
if (value instanceof List<?> list) {
    System.out.println(list.size());
}
```

`List<?>` cho biết đối tượng có thể sử dụng như danh sách với kiểu phần tử chưa xác định, **không chứng minh** mọi phần tử là `String`. Nếu thật sự cần kiểm tra nội dung, phải kiểm tra từng phần tử hoặc sử dụng hợp đồng API đảm bảo kiểu.

## 20. `var`: suy luận kiểu tại compile time, không có “kiểu biến đổi động”

Java 10+ có thể dùng `var` cho biến cục bộ khi compiler suy luận được kiểu từ initializer:

```java
var dog = new Dog();
```

**`var` không biến Java thành ngôn ngữ có dynamic typing.** Nó yêu cầu compiler suy ra một **kiểu tĩnh cụ thể** khi khai báo biến.

- Với `var dog = new Dog();`, kiểu suy luận của `dog` là `Dog`.
- Với `Animal animal = new Dog();`, kiểu khai báo `animal` là `Animal`.
- Sau khi khai báo, một biến `var` không thể tự đổi kiểu tĩnh theo các phép gán sau đó.

Ví dụ:

```java
var dog = new Dog();
// dog = new Cat(); // Không hợp lệ nếu Cat không phải subtype của Dog
```

Trong khi:

```java
Animal pet = new Dog();
pet = new Cat(); // Hợp lệ nếu Dog và Cat đều extends Animal
```

Với kiểu generic, `var names = new ArrayList<String>();` suy luận kiểu tĩnh của `names` là `ArrayList<String>`, không phải `List<String>`. Nếu muốn mã phụ thuộc vào interface `List`, hãy **khai báo tường minh `List<String> names = ...`**.

### Hạn chế `var`

`var` không thể dùng tùy ý làm kiểu field hoặc kiểu trả về method thông thường. Nó cũng cần initializer để suy luận kiểu và không cho phép khởi tạo biến cục bộ chỉ từ literal `null` như `var value = null;`.

Nhờ vậy, `var` vẫn nằm trong mô hình **kiểm tra kiểu tĩnh**, không tự chuyển sang cơ chế “biến có lớp runtime nào thì gọi member lớp đó”.

## 21. Kiểu trả về của method cũng ảnh hưởng khả năng sử dụng object

Một method có thể khai báo trả về superclass/interface nhưng thực tế trả một đối tượng subclass:

```java
static Animal choose() {
    return new Dog();
}
```

Với:

```java
Animal pet = choose();
```

- Kiểu **khai báo trả về** của `choose()` là `Animal`.
- Kiểu tĩnh của biểu thức lời gọi `choose()` là `Animal`.
- Đối tượng được trả về ở lần chạy này có runtime class `Dog`.
- `choose().speak()` hợp lệ nếu `Animal` khai báo `speak()`.
- `choose().fetch()` không hợp lệ dù phương thức hiện đang tạo `Dog`, vì compiler nhìn return type `Animal`.

Nếu API cần cho caller sử dụng chức năng chuyên biệt `Dog`, phải cân nhắc khai báo return type phù hợp, API factory chuyên biệt hoặc thiết kế đa hình.

### Covariant return khi override

Instance method override được phép có **return type tham chiếu cụ thể hơn** trong các trường hợp được Java chấp nhận:

```java
class AnimalFactory {
    Animal create() {
        return new Animal();
    }
}

class DogFactory extends AnimalFactory {
    @Override
    Dog create() {
        return new Dog();
    }
}
```

Khi biến receiver có kiểu tĩnh `DogFactory`, `factory.create()` có thể được nhìn với kiểu trả về `Dog`. Nhưng khi receiver chỉ khai báo `AnimalFactory`, compiler xét kiểu trả về của method qua **kiểu tĩnh `AnimalFactory`**, dù runtime dispatch gọi implementation `DogFactory.create()`.

**Đừng nhầm:** implementation có thể trả đối tượng `Dog`, còn biểu thức tại nơi gọi vẫn có kiểu compile time `Animal` tùy kiểu tĩnh của receiver và method được nhìn thấy.

## 22. `final` không buộc biến trỏ đúng lớp khai báo và không khóa đối tượng

`final` trên một biến tham chiếu có nghĩa là **giá trị biến không được gán lại sau khi khởi tạo hợp lệ**. Nó không có nghĩa lớp runtime phải bằng hệt kiểu khai báo.

```java
final Animal pet = new Dog();
```

Hoàn toàn hợp lệ:
- Kiểu khai báo: `Animal`.
- Runtime class: `Dog`.
- Biến `pet` không được gán lại `pet = new Cat();`.
- Nếu `Dog` có field/method mutable, trạng thái object **vẫn có thể thay đổi** qua API được phép.

**Phân biệt `final` gắn với những thứ khác nhau:**

| Vị trí `final` | Ý nghĩa cốt lõi |
| --- | --- |
| `final Animal pet = new Dog();` | Không gán lại biến `pet` |
| `final class Dog { ... }` | Không cho lớp khác extends `Dog` |
| `final void speak() { ... }` | Không cho subtype override instance method đó |
| `final SomeType field;` | Field phải được gán theo quy tắc khởi tạo final và không được gán lại sau đó |

Một **final class** vẫn có thể được tham chiếu qua superclass/interface; `String` là ví dụ lớp final thường được sử dụng qua kiểu rộng như `Object` hoặc `CharSequence`.

## 23. Một đối tượng có thể thỏa nhiều interface cùng lúc

Một lớp thực tế có thể triển khai nhiều interface, nhưng biến được khai báo theo **một kiểu tham chiếu cụ thể** tại vị trí đó.

```java
interface Named {
    String name();
}

interface Identified {
    int id();
}

class Member implements Named, Identified {
    @Override
    public String name() {
        return "An";
    }

    @Override
    public int id() {
        return 7;
    }
}
```

Các biến:

```java
Member member = new Member();
Named named = member;
Identified identified = member;
Object object = member;
```

Cả bốn biến đều có thể tham chiếu đến **một thể hiện `Member`**, nhưng:

- `named.name()` hợp lệ; `named.id()` không hợp lệ qua kiểu tĩnh `Named`.
- `identified.id()` hợp lệ; `identified.name()` không hợp lệ qua kiểu tĩnh `Identified`.
- `member.name()` và `member.id()` đều hợp lệ.
- `object.toString()` hợp lệ do `Object`; `object.name()` không hợp lệ qua kiểu tĩnh `Object`.

Nếu cần một API yêu cầu **cả hai hợp đồng**, có thể khai báo interface kết hợp, hoặc dùng generic bounds theo nhu cầu. Không cần luôn cast tham chiếu sang một lớp triển khai duy nhất.

## 24. Ví dụ tổng hợp: một object qua nhiều góc nhìn

Lưu vào **`TypeViewReview.java`**:

```java
interface Named {
    String name();
}

class Person implements Named {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }

    String role() {
        return "Person";
    }
}

class Student extends Person {
    Student(String name) {
        super(name);
    }

    @Override
    String role() {
        return "Student";
    }

    String school() {
        return "Java Academy";
    }
}

public class TypeViewReview {
    static String accept(Person person) {
        return "Person overload: " + person.role();
    }

    static String accept(Student student) {
        return "Student overload: " + student.role();
    }

    public static void main(String[] args) {
        Student student = new Student("An");
        Person person = student;
        Named named = student;
        Object any = student;

        System.out.println(student == person);
        System.out.println(person == named);
        System.out.println(named == any);
        System.out.println(any.getClass().getSimpleName());

        System.out.println(named.name());
        System.out.println(person.role());

        System.out.println(accept(person));
        System.out.println(accept(student));

        if (person instanceof Student match) {
            System.out.println(match.school());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 TypeViewReview.java
java TypeViewReview
```

Stdout:

```text
true
true
true
Student
An
Student
Person overload: Student
Student overload: Student
Java Academy
```

Giải thích chi tiết:

1. Một đối tượng `Student` được tạo bởi `new Student("An")` và được tham chiếu qua bốn biến khác kiểu: `Student`, `Person`, `Named` và `Object`.
2. Ba phép `==` đều đúng vì các biến vẫn chỉ một object; các kiểu khai báo khác nhau **không tạo object mới**.
3. `any.getClass().getSimpleName()` trả `Student`, lớp thực tế của object.
4. `named.name()` hợp lệ vì kiểu tĩnh `Named` có method `name()`.
5. `person.role()` hợp lệ vì `Person` khai báo `role()`; runtime chạy override `Student.role()` nên in `Student`.
6. `accept(person)` chọn **overload nhận `Person`** do kiểu tĩnh của biểu thức đối số `person`. Bên trong overload ấy, `person.role()` vẫn chạy override của `Student`.
7. `accept(student)` chọn overload nhận `Student` do kiểu tĩnh của đối số là `Student`.
8. `person instanceof Student match` kiểm tra runtime type; khi đúng, biến `match` có kiểu tĩnh `Student` và gọi được `school()`.

Đây là ví dụ quan trọng vì nó chứng minh đồng thời **kiểu tĩnh**, **runtime class**, **overload resolution**, **dynamic dispatch** và **downcast an toàn** mà không đổi đối tượng ban đầu.

## 25. Các lỗi thường gặp và cách sửa

| Tình huống | Sai lầm thường gặp | Cách hiểu/khắc phục |
| --- | --- | --- |
| `Animal a = new Dog();` | Nghĩ đối tượng `Dog` biến thành `Animal` | Chỉ tham chiếu qua biến kiểu cha; runtime class vẫn `Dog` |
| `a.fetch()` với `fetch` chỉ ở `Dog` | Nghĩ Java nhìn runtime Dog sẽ cho biên dịch | Compiler xem kiểu tĩnh `Animal`; cần API chung hoặc cast/`instanceof` |
| `Dog d = a;` với `a` khai báo `Animal` | Nghĩ vì runtime Dog nên không cần cast | Cần downcast hợp lệ và có thể phải kiểm tra runtime |
| `(Dog) a` khi object thực tế `Cat` | Nghĩ cast sẽ chuyển object thành Dog | Có thể ném `ClassCastException` |
| `a.speak()` chạy phiên bản `Dog` | Nghĩ biến `a` đã đổi kiểu tĩnh | Kiểu tĩnh không đổi; đây là overriding và dynamic dispatch |
| `handle(a)` chọn overload `Animal` | Nghĩ runtime phải chọn `Dog` | Overload được phân giải theo compile-time type của đối số |
| `a.label` và `((Dog)a).label` khác nhau | Nghĩ field bị override | Field hiding chọn theo kiểu tĩnh của receiver |
| `Parent p = new Child(); p.staticMethod()` | Nghĩ static method dispatch theo runtime | Static hiding/selection theo compile time; nên gọi qua tên lớp |
| `a.getClass()` khi `a == null` | Nghĩ `null` có runtime class | Ném `NullPointerException`; dùng guard |
| `a instanceof Dog` với `a == null` | Nghĩ có lỗi do null | Kết quả `false` |
| `Object x = "Hi"; x.length()` | Nghĩ compiler thấy String đang nằm bên trong | Object không khai báo `length()`; pattern/cast có chủ đích |
| `List<String> l = new ArrayList<>();` | Nghĩ `l.getClass()` biểu thị riêng `ArrayList<String>` | Runtime class là `ArrayList`; generic type argument thường bị erasure |
| `List<Object> dst = List<String>` | Nghĩ generic covariant như mảng | Generic invariant; dùng wildcard hoặc API tương thích |
| `Object[] a = new String[2]; a[0] = 1;` | Nghĩ Object[] cho phép mọi object vào mảng | Runtime check ném `ArrayStoreException` |
| `var x = new Dog();` | Nghĩ kiểu biến đổi động theo phép gán | `var` suy luận kiểu tĩnh `Dog` một lần |
| `final Animal a = new Dog();` | Nghĩ runtime class phải đúng `Animal` | `final` cấm gán lại biến, không ép đối tượng thuộc đúng lớp cha |
| `Animal a = new Dog(); a = new Cat();` | Nghĩ object Dog biến thành Cat | Biến `a` đổi tham chiếu sang object mới; Dog cũ không đổi lớp |

## 26. Bài tự luyện và đáp án

### Bài 1 — Kiểu nào là tĩnh, kiểu nào là runtime?

```java
Object value = new StringBuilder("Java");
```

**Đáp án:** biến `value` có kiểu khai báo `Object`; runtime class của object là `StringBuilder`. `value.append(" 17")` không biên dịch vì `Object` không có `append`; có thể dùng kiểm tra:

```java
if (value instanceof StringBuilder builder) {
    builder.append(" 17");
}
```

Sau đó object `StringBuilder` ban đầu được sửa, không có object mới chỉ vì pattern variable `builder` xuất hiện.

### Bài 2 — Override theo runtime class

```java
class Parent {
    String text() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String text() {
        return "Child";
    }
}
```

```java
Parent p = new Child();
System.out.println(p.text());
```

**Đáp án:** in `Child`. Compiler biết `Parent.text()`; runtime chọn implementation của `Child`.

### Bài 3 — Overload theo kiểu của đối số

```java
static void print(Object value) {
    System.out.println("Object");
}

static void print(String value) {
    System.out.println("String");
}
```

```java
Object a = "Hi";
String b = "Hi";
print(a);
print(b);
```

**Đáp án:**

```text
Object
String
```

Cả hai biểu thức có thể tham chiếu đến chuỗi, nhưng kiểu tĩnh của `a` là `Object`, của `b` là `String`. Overload được chọn ở compile time.

### Bài 4 — Runtime class có đổi khi gán lại biến?

```java
Animal a = new Dog();
Animal old = a;
a = new Cat();
```

**Đáp án:** `a` giờ tham chiếu object `Cat`; `old` tiếp tục tham chiếu object `Dog` ban đầu. Hai object không đổi lớp thực tế. Kiểu khai báo của cả `a` và `old` vẫn là `Animal`.

### Bài 5 — Cast với `null`

```java
Animal a = null;
Dog d = (Dog) a;
System.out.println(d == null);
System.out.println(a instanceof Dog);
```

**Đáp án:**

```text
true
false
```

Cast `null` sang kiểu tham chiếu `Dog` cho ra `null`; `instanceof` trên `null` trả false. Gọi `d.fetch()` sẽ ném `NullPointerException`.

### Bài 6 — Field và method khác nhau

```java
class A {
    String value = "A";

    String value() {
        return "method A";
    }
}

class B extends A {
    String value = "B";

    @Override
    String value() {
        return "method B";
    }
}
```

```java
A ref = new B();
System.out.println(ref.value);
System.out.println(ref.value());
```

**Đáp án:**

```text
A
method B
```

Field được chọn theo kiểu tĩnh `A`; instance method có override được chọn theo runtime object `B`.

### Bài 7 — Mảng generic và class thực tế

Giả sử:

```java
java.util.List<String> names = new java.util.ArrayList<>();
Object object = names;
```

**Đáp án:**

- Kiểu tĩnh `names`: `List<String>`.
- Kiểu tĩnh `object`: `Object`.
- Runtime class của object mà cả hai biến trỏ tới: `ArrayList`.
- `names.add("A")` hợp lệ; `object.add("A")` không biên dịch vì `Object` không có `add`.
- `object instanceof java.util.ArrayList` có thể dùng để kiểm tra kiểu lớp runtime, nhưng không tự chứng minh danh sách chứa toàn `String`.

### Bài 8 — Lựa chọn kiểu khai báo tốt hơn

Nếu mã cần dùng các phương thức `add`, `get`, `size` của danh sách chuỗi và không cần các API riêng của `ArrayList`, nên viết:

```java
java.util.List<String> names = new java.util.ArrayList<>();
```

thay vì:

```java
Object names = new java.util.ArrayList<String>();
```

**Lý do:** khai báo qua interface `List<String>` bộc lộ **hợp đồng cần thiết**, vẫn cho phép đổi lớp triển khai sau này mà không cần cast rải rác.

## 27. Checklist phân tích một biến tham chiếu

1. **Đọc khai báo biến**: `Type variable` là gì? Có phải generic type như `List<String>` không?
2. **Đọc biểu thức tạo/gán**: `new Subtype()`, giá trị trả về của method, cast, hoặc một tham chiếu khác?
3. **Xác định kiểu compile-time của biểu thức đang dùng**: tên biến, cast, `new`, method call, ternary có thể có kiểu khác nhau.
4. **Xác định runtime class** nếu tham chiếu khác `null`: object được tạo thuộc lớp nào?
5. **Đếm object bằng `new` và đường tạo thực tế, không đếm tên biến**: nhiều biến có thể alias cùng object.
6. **Nếu gọi method**, compiler có thấy tên/chữ ký qua kiểu tĩnh không? Nếu không, phải đổi API hoặc kiểm tra/cast đúng.
7. **Nếu instance method được override**, xét runtime receiver để xác định implementation chạy.
8. **Nếu nhiều overload**, xét các kiểu tĩnh của đối số, không dựa vào runtime object để đoán chữ ký.
9. **Nếu đọc field hoặc static method**, nhớ chúng không dùng dynamic dispatch như override instance method.
10. **Nếu downcast**, kiểm tra khả năng tương thích runtime; ưu tiên `instanceof` pattern trong Java 17 khi thích hợp.
11. **Nếu `null`**, không có object để hỏi `getClass()`; `instanceof` trả false và dereference có thể ném `NullPointerException`.
12. **Nếu dùng mảng/generic**, xem cả kiểm tra runtime của mảng, erasure và invariance của generic.
13. **Nếu biến được gán lại**, runtime class của object được tham chiếu hiện tại có thể đổi, nhưng **kiểu khai báo của biến vẫn giữ nguyên**.
14. **Thiết kế API theo interface/superclass vừa đủ**, để dùng đa hình mà vẫn giữ compile-time type safety, hạn chế cast không cần thiết.

## Ghi nhớ

- **Kiểu khai báo/static type** là thông tin compiler dùng để kiểm tra member access, type compatibility và lựa chọn overload.
- **Lớp thực tế/runtime class** thuộc về **đối tượng đang được tham chiếu**, không phải luôn trùng với kiểu khai báo của biến.
- `Animal a = new Dog();` là **một đối tượng Dog được tham chiếu qua biến kiểu Animal**; không tạo object Animal thứ hai.
- **Upcast** mở rộng cách nhìn kiểu tĩnh; **downcast** kiểm tra cách nhìn hẹp hơn ở runtime, không biến đổi object.
- **Overriding** cho phép implementation instance method chạy theo runtime receiver; **overloading**, **field hiding** và **static method hiding** có quy tắc chọn dựa trên thông tin compile time.
- `instanceof` dùng để kiểm tra subtype-compatible runtime type; `getClass()` lấy lớp thực tế chính xác của receiver khác `null`.
- **`null` không tham chiếu đối tượng nào**; một biến vẫn giữ kiểu khai báo dù giá trị là `null`.
- **Gán lại biến không thay đổi lớp của đối tượng cũ**; nó chỉ thay đổi object mà biến tham chiếu. Kiểu tĩnh của biến không tự đổi theo phép gán.
