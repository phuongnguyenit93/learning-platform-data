# Kiểu trả về hiệp biến và hợp đồng phương thức khi kế thừa Generics trong Java

## 1. Bài toán và kết quả cần nắm

Khi một lớp con **ghi đè (override)** phương thức của lớp cha, Java cho phép phương thức ở lớp con trả về **một kiểu cụ thể hơn** so với kiểu trả về trong hợp đồng cha. Cơ chế này gọi là **covariant return type — kiểu trả về hiệp biến**. Nó rất hữu ích khi kế thừa lớp generic: lớp cha định nghĩa thao tác bằng tham số kiểu `T`; lớp con cố định `T` thành một kiểu cụ thể, rồi cung cấp kết quả chính xác hơn mà vẫn dùng được thông qua tham chiếu của lớp cha.

Ví dụ:

```java
class Animal {
    String name() { return "animal"; }
}

class Dog extends Animal {
    String bark() { return "gâu"; }
}

class AnimalFactory {
    Animal create() { return new Animal(); }
}

class DogFactory extends AnimalFactory {
    @Override
    Dog create() { return new Dog(); } // Hợp lệ: Dog là subtype của Animal.
}
```

Với `DogFactory`, phương thức `create()` có thể trả `Dog`, nhưng lời gọi qua tham chiếu `AnimalFactory` vẫn có hợp đồng trả `Animal`. Hành vi thực tế của đối tượng vẫn được chọn bằng **dynamic dispatch**, không phải bằng kiểu trả về ở nơi gọi.

Mục tiêu bài học:

- Hiểu chính xác khi nào kiểu trả về của override có thể cụ thể hơn.
- Phân biệt **hiệp biến kiểu trả về** với **bất biến (invariance) của generic type arguments**.
- Đọc và viết đúng contract khi lớp con kế thừa `Parent<T>`, đặc biệt `extends Parent<Dog>`.
- Hiểu giới hạn đối với **tham số phương thức, visibility, checked exceptions, `final`/`static`**, và các kiểu primitive/`void`.
- Hiểu vai trò của **type erasure** và **bridge method**, tránh tự thêm cast hoặc làm mất an toàn kiểu.
- Áp dụng vào API factory, repository, provider, builder và các collection bằng chương trình Java 17+ chạy được.

## 2. Hiệp biến kiểu trả về là gì?

Giả sử `Dog extends Animal`. Khi override một phương thức instance trong `AnimalSource` có kết quả `Animal`, `DogSource` có thể trả `Dog`:

```java
class AnimalSource {
    public Animal get() {
        return new Animal();
    }
}

class DogSource extends AnimalSource {
    @Override
    public Dog get() {
        return new Dog();
    }
}
```

Quy tắc cốt lõi là **kiểu trả về của phương thức override phải tương thích để thay thế kiểu trả về trong hợp đồng phương thức bị override** (*return-type substitutability*). Với các kiểu tham chiếu thông thường, một subtype phù hợp của kiểu trả về cha được chấp nhận.

Lời gọi minh họa:

```java
DogSource direct = new DogSource();
Dog dog = direct.get(); // Kiểu biểu thức get() là Dog.

AnimalSource general = direct;
Animal animal = general.get(); // Kiểu biểu thức get() là Animal.
```

Cả hai lời gọi chạy trên **cùng đối tượng** `DogSource` và đều thực thi implementation `DogSource.get()`. Kiểu tĩnh của biến ở nơi gọi quyết định những gì compiler cho phép sử dụng tiếp:

```java
Dog concrete = direct.get();
concrete.bark();                  // Hợp lệ.
Animal generalResult = general.get();
// generalResult.bark();          // Lỗi biên dịch: Animal không khai báo bark().
```

Hợp đồng của lớp cha bảo đảm người dùng nhận được **ít nhất một `Animal`**. Lớp con đáp ứng hợp đồng bằng việc cung cấp một `Dog`, vốn là một `Animal` hợp lệ.

### Vì sao có lợi?

Nếu Java bắt buộc override trả đúng kiểu `Animal`, client `DogSource` phải cast:

```java
// Không cần làm vậy khi DogSource.get() trả Dog:
// Dog dog = (Dog) direct.get();
```

Covariant return cho phép client có kiểu kết quả đủ cụ thể, giữ kiểm tra lúc biên dịch và giảm cast trong các API chuyên biệt.

## 3. Ghi đè trước hết phải đúng hợp đồng phương thức

Covariant return **chỉ thay đổi điều kiện về kiểu trả về**; nó không có nghĩa lớp con được tùy ý sửa chữ ký phương thức. Để override đúng, vẫn cần thỏa các quy tắc Java về:

1. **Tên phương thức và danh sách tham số** phải khớp theo quy tắc override/subsignature; không thể tùy tiện thay `Animal` thành `Dog` ở **tham số đầu vào** rồi vẫn gọi đó là override.
2. Kiểu trả về phải **return-type-substitutable** với kiểu trả về cha.
3. Mức truy cập của phương thức override không được **hẹp hơn** mức truy cập của phương thức cha.
4. Phương thức override không được khai báo checked exception mới hoặc rộng hơn những gì hợp đồng cha cho phép (có thể khai báo tập ngoại lệ hẹp hơn).
5. Không override phương thức `final`, `private` hay `static` theo nghĩa đa hình của instance method. `static` là *method hiding* với quy tắc riêng.
6. Constructor **không phải phương thức được override** và không có kiểu trả về; áp dụng hiệp biến kiểu trả về cho constructor là sai phạm vi.

Ví dụ có visibility và checked exception:

```java
import java.io.IOException;

class Reader {
    protected Animal load() throws IOException {
        return new Animal();
    }
}

class DogReader extends Reader {
    @Override
    public Dog load() {
        return new Dog();
    }
}
```

`DogReader.load()` mở rộng quyền truy cập từ `protected` lên `public`, thu hẹp kiểu kết quả từ `Animal` xuống `Dog`, và loại bỏ checked exception `IOException`. Cả ba điều đều phù hợp.

Ví dụ không hợp lệ:

```java
class BadDogReader extends Reader {
    // @Override
    // private Animal load() throws Exception {
    //     return new Dog();
    // }
    // Sai: private làm hẹp truy cập; Exception rộng hơn IOException.
}
```

**Đừng phân biệt override chỉ bằng câu hỏi “tên có giống không?”**. Luôn nhìn đủ hợp đồng, bao gồm danh sách tham số, kiểu trả về, visibility và exceptions.

## 4. Sử dụng `T` của lớp cha generic

Giờ xét lớp cha được tham số hóa:

```java
class Container<T> {
    private final T value;

    Container(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }
}
```

Khi lớp con cố định type argument:

```java
class DogContainer extends Container<Dog> {
    DogContainer(Dog value) {
        super(value);
    }

    @Override
    public Dog get() {
        return super.get();
    }
}
```

Với `DogContainer extends Container<Dog>`, tham số kiểu `T` của superclass được cố định là `Dog`, nên client thấy `Container<Dog>.get()` có kết quả `Dog` ngay cả khi không có override. Việc ghi đè ở lớp con vẫn hợp lệ, và có thể thêm validation, logging hoặc biến đổi giá trị khi thật sự cần.

```java
Container<Dog> parentView = new DogContainer(new Dog());
Dog value = parentView.get(); // Được kiểm tra là Dog.
```

**Hai ý phải tách rõ:**

- **Thế tham số kiểu (*generic substitution*):** `T` ở `Container<T>` được diễn giải như `Dog` trong `Container<Dog>`.
- **Hiệp biến kiểu trả về:** khi override một phương thức hợp lệ, lớp con có thể chọn kiểu trả về tương thích nhưng **cụ thể hơn** kiểu mà phương thức cha yêu cầu.

Trong ví dụ này, override trả `Dog` cũng là cùng kiểu đã được chuyên biệt hóa. Ví dụ tiếp theo thể hiện cả chuyên biệt hóa theo generic và hiệp biến subtype ở cấp kết quả.

### Khi kiểu trả về được làm hẹp thêm

```java
class Mammal extends Animal {}

class MammalContainer extends Container<Mammal> {
    MammalContainer(Mammal value) {
        super(value);
    }
}

class SpecificMammal extends Mammal {}

class SpecificMammalContainer extends Container<Mammal> {
    SpecificMammalContainer(SpecificMammal value) {
        super(value);
    }

    @Override
    public SpecificMammal get() {
        return (SpecificMammal) super.get();
    }
}
```

`Container<Mammal>.get()` có hợp đồng trả `Mammal`. Lớp con có thể trả `SpecificMammal` vì đây là subtype. Nhưng cách cast ở đây **chỉ an toàn nếu invariant thực sự bảo đảm mọi đối tượng trong container là `SpecificMammal`**. Nếu phương thức cha có thể bị dùng để thay đổi giá trị thành `Mammal` khác, cách override sẽ nguy hiểm.

Thiết kế tốt hơn thường lưu kiểu chuyên biệt ngay từ đầu hoặc giữ đường khởi tạo bảo đảm invariant, ví dụ dùng lớp con `extends Container<SpecificMammal>`. Không dùng covariance như một lý do để ép kiểu không được chứng minh.

## 5. Covariant return và `extends Parent<String>`

Với kế thừa có type argument cố định, Java ánh xạ chữ ký inherited method thành một contract có kiểu:

```java
class Parent<T> {
    public T read() {
        return null;
    }
}

class TextChild extends Parent<String> {
    @Override
    public String read() {
        return "Java";
    }
}
```

`String` là kiểu kết quả mà lời gọi `Parent<String>.read()` công khai. Khi override bằng `String`, lớp con đáp ứng đúng contract. Lúc compile, người gọi có thể viết:

```java
Parent<String> base = new TextChild();
String result = base.read(); // "Java"; không cần cast.
```

Nếu `Parent<T>` có bound:

```java
class NumberParent<T extends Number> {
    private final T number;
    NumberParent(T number) {
        this.number = number;
    }
    public T read() { return number; }
}

class IntegerChild extends NumberParent<Integer> {
    IntegerChild(Integer n) {
        super(n);
    }

    @Override
    public Integer read() {
        return super.read();
    }
}
```

`Integer` đáp ứng `T extends Number`. Tại source level, caller `NumberParent<Integer>` nhận `Integer`. Khi kiểm tra erasure ở bytecode, compiler xử lý các khác biệt chữ ký cần thiết bằng bridge method; client không phải viết thêm cầu nối.

### Getter không phải nơi duy nhất có covariance

Có thể override một phương thức tạo bản sao để nó trả chính subtype:

```java
class Copyable<T> {
    private final T value;
    Copyable(T value) { this.value = value; }
    public Copyable<T> copy() {
        return new Copyable<>(value);
    }
}

class StringCopyable extends Copyable<String> {
    StringCopyable(String value) { super(value); }

    @Override
    public StringCopyable copy() {
        return new StringCopyable("copy");
    }
}
```

`StringCopyable` là subtype của `Copyable<String>`, nên kiểu trả về `StringCopyable` phù hợp với kiểu trả về `Copyable<String>` của cha. Đây là mẫu **self-returning API** được dùng ở builder, factory, copy/clone và fluent API.

Không có nghĩa Java có cơ chế “self type” tuyệt đối cho mọi cây kế thừa. Nếu lớp con sâu hơn cần trả về đúng lớp con mới, có thể phải override tiếp hoặc xem xét generic self-type pattern khi cần.

## 6. Phân biệt kiểu trả về với kiểu tham số phương thức

Hiệp biến kết quả không áp dụng đối xứng để bạn tự ý đổi **tham số đầu vào**:

```java
class AnimalHandler {
    public Animal handle(Animal item) {
        return item;
    }
}

class DogHandler extends AnimalHandler {
    // KHÔNG phải override của handle(Animal).
    public Dog handle(Dog item) {
        return item;
    }
}
```

`handle(Dog)` là **overload**, vì danh sách tham số thay đổi. Lời gọi thông qua `AnimalHandler` vẫn chọn chữ ký `handle(Animal)`; nếu lớp con không override chữ ký đó, implementation cha vẫn chạy.

Để override chính xác:

```java
class CorrectDogHandler extends AnimalHandler {
    @Override
    public Dog handle(Animal item) {
        return new Dog();
    }
}
```

`CorrectDogHandler.handle(Animal)` giữ nguyên tham số `Animal` nhưng có thể thu hẹp kết quả thành `Dog`. Gắn `@Override` giúp compiler phát hiện nhầm lẫn giữa override và overload.

Trong generic inheritance, cũng phải nhớ `List<Dog>` **không** phải subtype của `List<Animal>` dù `Dog extends Animal`. Đây là câu chuyện về **invariance của kiểu đã tham số hóa**, khác với covariance của kiểu trả về là một `Dog` đơn lẻ.

## 7. Quan trọng: `List<Dog>` không thay được `List<Animal>`

Giả sử lớp cha khai báo:

```java
class AnimalService {
    public java.util.List<Animal> findAll() {
        return java.util.List.of(new Animal());
    }
}
```

Lớp con không được override thành `List<Dog>`:

```java
class BadDogService extends AnimalService {
    // @Override
    // public java.util.List<Dog> findAll() {
    //     return java.util.List.of(new Dog());
    // }
    // Sai: List<Dog> không phải subtype của List<Animal>.
}
```

Tại sao? Nếu điều đó được chấp nhận, code dùng tham chiếu `AnimalService` có thể xem kết quả như `List<Animal>` và (nếu list có thể sửa) thêm một `Animal` không phải `Dog`, phá hợp đồng `List<Dog>`. Java giữ generic types mặc định **invariant**.

### Cách 1: thiết kế hợp đồng cha bằng wildcard phù hợp

Nếu API chỉ có nhu cầu **cung cấp/đọc** danh sách các `Animal`, lớp cha có thể trả `List<? extends Animal>`:

```java
class AnimalCatalog {
    public java.util.List<? extends Animal> animals() {
        return java.util.List.of(new Animal());
    }
}

class DogCatalog extends AnimalCatalog {
    @Override
    public java.util.List<Dog> animals() {
        return java.util.List.of(new Dog());
    }
}
```

Ở đây `List<Dog>` **là subtype của** `List<? extends Animal>`, do đó override hợp lệ. Người dùng tham chiếu cha đọc phần tử như `Animal`; không thể tùy ý thêm `Animal` vào danh sách trả về qua biến wildcard:

```java
AnimalCatalog catalog = new DogCatalog();
java.util.List<? extends Animal> list = catalog.animals();
Animal first = list.get(0);
// list.add(new Animal()); // Lỗi biên dịch: phần tử có kiểu capture chưa biết.
```

Với `List<? extends Animal>`, việc thêm giá trị cụ thể không được bảo đảm an toàn; chỉ thêm `null` mới được phép về mặt hệ thống kiểu (implementation có thể từ chối).

### Cách 2: generic hóa hợp đồng cha

Nếu cần giữ đúng kiểu phần tử, có thể thiết kế:

```java
class Service<T extends Animal> {
    public java.util.List<T> findAll() {
        return java.util.List.of();
    }
}

class DogService extends Service<Dog> {
    @Override
    public java.util.List<Dog> findAll() {
        return java.util.List.of(new Dog());
    }
}
```

`Service<Dog>.findAll()` đã có kiểu `List<Dog>` từ phép thế `T = Dog`; override ở `DogService` bảo toàn hợp đồng chính xác. Đây thường là cách phù hợp khi domain API cần thao tác theo một kiểu duy nhất xuyên suốt.

**Đừng thay hợp đồng bằng raw `List` hoặc cast unchecked** chỉ để compiler im lặng: làm vậy sẽ che giấu lỗi quan hệ kiểu và có thể dẫn tới `ClassCastException` khi sử dụng dữ liệu.

## 8. Interface generic và kiểu trả về hiệp biến

Covariant return không chỉ áp dụng giữa hai class. Một lớp triển khai interface cũng có thể trả một kiểu cụ thể hơn kiểu kết quả interface yêu cầu:

```java
interface Producer<T> {
    T produce();
}

class AnimalProducer implements Producer<Animal> {
    @Override
    public Dog produce() {
        return new Dog();
    }
}
```

`Producer<Animal>.produce()` có hợp đồng trả `Animal`; trả `Dog` là đáp ứng hợp đồng, vì `Dog extends Animal`.

Sử dụng qua interface:

```java
Producer<Animal> producer = new AnimalProducer();
Animal item = producer.produce();
```

Điểm cần nhớ: `AnimalProducer implements Producer<Animal>` **không** làm nó thành `Producer<Dog>`:

```java
// Producer<Dog> dogs = new AnimalProducer(); // Không hợp lệ.
```

Một instance có thể tạo ra `Dog` nhưng type argument của interface vẫn là `Animal`; generic assignment tuân theo invariance.

### Khi interface cố định sẵn kết quả

```java
interface StringProvider {
    CharSequence text();
}

class FixedStringProvider implements StringProvider {
    @Override
    public String text() {
        return "Hello";
    }
}
```

`String implements CharSequence`, nên `String` là một covariant return type hợp lệ. Mẫu này xuất hiện ở interface SDK, builder và adapter khi implementation cung cấp một đối tượng có API cụ thể hơn.

## 9. Type erasure và bridge method: vì sao đa hình vẫn đúng?

Java generics được triển khai chủ yếu dựa trên **type erasure**. Khi compiler biên dịch `class Source<T extends Animal>`, phần `T` thường được thay bằng bound `Animal` trong chữ ký tương ứng ở bytecode. Lớp con `Source<Dog>` lại có phương thức override trả kiểu `Dog`.

Ví dụ ý tưởng:

```java
class Source<T extends Animal> {
    public T read() {
        return null;
    }
}

class DogSource extends Source<Dog> {
    @Override
    public Dog read() {
        return new Dog();
    }
}
```

Sau erasure, JVM nhìn những method descriptor có kiểu trả về khác nhau. Để đảm bảo lời gọi qua `Source<Dog>` vẫn tới implementation `DogSource.read()`, compiler có thể sinh một **bridge method** tổng hợp, chuyển lời gọi kiểu erasure sang phương thức chuyên biệt.

Đây là cơ chế quan trọng để giữ **đa hình** khi generic method signatures và covariant returns gặp nhau. Bridge methods:

- Do compiler tạo ra khi cần; không phải phương thức bạn tự viết trong mã nguồn.
- Thường mang dấu `synthetic` và `bridge` ở bytecode.
- Có thể được quan sát qua reflection bằng `Method.isBridge()` hoặc `javap -c -p`.
- Không có nghĩa runtime duy trì một lớp chuyên biệt riêng cho `Source<Dog>`.
- Không phải lý do để bỏ `@Override`, dùng raw type hay tự ép kiểu.

Trong ví dụ đầy đủ ở mục 12, `DogSource` override cả `read()` và `copy()`. Với compiler Java đã thử, reflection đếm được **2 bridge method** do các chữ ký được làm cụ thể hơn. Nếu sửa thiết kế hoặc phiên bản compiler, không nên sử dụng số lượng bridge method như một hợp đồng business logic.

### Có nên tự viết bridge?

Không. Mã nguồn chỉ cần viết đúng override và để compiler thực hiện phần tương thích runtime. Tự viết hai phương thức khác nhau chỉ bởi kiểu trả về cũng **không hợp lệ**, vì Java không cho overload bằng kiểu trả về đơn thuần.

## 10. Kết quả primitive, `void`, checked exceptions và `static`

Các ví dụ `Dog`/`Animal` đều là **reference types**. Với primitive và `void`, không áp dụng hiệp biến như quan hệ lớp:

```java
class BaseCount {
    int size() { return 1; }
}

class ChildCount extends BaseCount {
    // @Override long size() { return 1L; } // Sai: long không thay int.
    @Override int size() { return 2; } // Đúng.
}
```

`int` và `long` có chuyển đổi số học mở rộng khi gán biểu thức, nhưng **không tạo quan hệ subtype** để thay đổi kiểu trả về khi override. Tương tự, một phương thức trả `void` phải được override bằng phương thức trả `void`.

### Checked exceptions

```java
import java.io.IOException;
import java.io.FileNotFoundException;

class ParentLoader {
    Animal load() throws IOException { return new Animal(); }
}

class ChildLoader extends ParentLoader {
    @Override
    Dog load() throws FileNotFoundException { return new Dog(); }
}
```

`FileNotFoundException` là subtype của `IOException`, vì vậy lớp con thu hẹp checked exception và thu hẹp kiểu trả về — cả hai hợp lệ. Ngược lại, thêm `throws Exception` khi lớp cha chỉ cho phép `IOException` là không hợp lệ.

### Quy tắc `static` và `final`

`static` methods không tham gia dynamic dispatch theo kiểu override instance; cùng tên/chữ ký ở lớp con là **hiding**. Không dùng `@Override` cho method static:

```java
class BaseFactory {
    static Animal create() { return new Animal(); }
}

class ChildFactory extends BaseFactory {
    // Đang che khuất static method, không phải override đa hình.
    static Dog create() { return new Dog(); }
}
```

Các quy tắc tương thích khi hiding vẫn cần được tuân thủ; đừng dùng hiding như cách thay thế override để biểu diễn trạng thái đối tượng.

Phương thức `final` không thể override nên không thể cung cấp kiểu trả về hiệp biến bằng cách override; `private` method không được kế thừa như một phương thức có thể override. Constructor luôn không có kiểu trả về và không phải đối tượng của quy tắc hiệp biến.

## 11. API tự trả subtype: factory, copy và builder

Một ứng dụng thường gặp của covariant return là lớp con muốn các thao tác fluent hoặc clone/copy trả lại **chính loại đối tượng chuyên biệt**:

```java
class BuilderBase {
    public BuilderBase configure() {
        return this;
    }
}

class DogBuilder extends BuilderBase {
    @Override
    public DogBuilder configure() {
        return this;
    }

    Dog build() {
        return new Dog();
    }
}
```

Người sử dụng `DogBuilder` gọi `configure()` sẽ nhận `DogBuilder` và có thể gọi tiếp `build()` mà không cần cast:

```java
DogBuilder builder = new DogBuilder();
Dog dog = builder.configure().build();
```

Tuy nhiên, khi API yêu cầu tự trả **mỗi subtype cuối cùng qua nhiều cấp**, covariant return override ở một cấp không tự “biến hình” theo subclass mới. Cần override tại các subtype sâu hơn hoặc cân nhắc mô hình self-bounded generics (*CRTP-like pattern*):

```java
abstract class Fluent<S extends Fluent<S>> {
    protected abstract S self();

    public S configure() {
        return self();
    }
}

final class Specialized extends Fluent<Specialized> {
    @Override
    protected Specialized self() {
        return this;
    }

    Specialized finish() {
        return this;
    }
}
```

Mẫu này giữ kiểu trả về xuyên qua API bằng generic parameter; nó khác với việc chỉ override một phương thức trả `Base` thành `Child`. Dùng khi hệ thống có nhiều lớp builder/fluent thực sự cần bảo đảm kiểu, không ép thêm phức tạp cho API nhỏ.

## 12. Chương trình Java 17+ độc lập, đã kiểm thử

Tạo file tên **`CovariantReturnDemo.java`**. Chương trình dưới đây minh họa cùng lúc kiểu trả về hiệp biến trên một phương thức thường, lớp cha generic có bound, interface, collection wildcard và bridge method.

```java
import java.util.List;
import java.util.Arrays;
import java.lang.reflect.Method;

public class CovariantReturnDemo {
    static class Animal {
        private final String name;
        Animal(String name) { this.name = name; }
        String name() { return name; }
    }

    static final class Dog extends Animal {
        Dog(String name) { super(name); }
        String bark() { return "gâu"; }
    }

    static class Source<T extends Animal> {
        private final T value;
        Source(T value) { this.value = value; }
        public T read() { return value; }
        public Source<T> copy() { return new Source<>(value); }
    }

    static final class DogSource extends Source<Dog> {
        DogSource(Dog value) { super(value); }
        @Override public Dog read() { return super.read(); }
        @Override public DogSource copy() { return new DogSource(read()); }
    }

    interface Provider<T> {
        T get();
    }

    static final class AnimalProvider implements Provider<Animal> {
        @Override public Dog get() { return new Dog("Nâu"); }
    }

    static class AnimalCatalog {
        public List<? extends Animal> animals() {
            return List.of(new Animal("Chung"));
        }
    }

    static final class DogCatalog extends AnimalCatalog {
        @Override public List<Dog> animals() {
            return List.of(new Dog("Mực"), new Dog("Vàng"));
        }
    }

    public static void main(String[] args) {
        DogSource child = new DogSource(new Dog("Bim"));
        Source<Dog> parent = child;
        System.out.println("parent: " + parent.read().name());
        System.out.println("child: " + child.read().bark());
        System.out.println("copy: " + child.copy().read().name());

        Provider<Animal> provider = new AnimalProvider();
        System.out.println("provider: " + provider.get().name());

        AnimalCatalog catalog = new DogCatalog();
        System.out.println("catalog: " +
                catalog.animals().stream().map(Animal::name).toList());

        long bridges = Arrays.stream(DogSource.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .count();
        System.out.println("bridges: " + bridges);
    }
}
```

Biên dịch và chạy (JDK 17 hoặc mới hơn):

```bash
javac --release 17 -Xlint:all CovariantReturnDemo.java
java CovariantReturnDemo
```

**Stdout chính xác** của bản trên (đã biên dịch với `--release 17 -Xlint:all` và chạy thành công):

```text
parent: Bim
child: gâu
copy: Bim
provider: Nâu
catalog: [Mực, Vàng]
bridges: 2
```

Giải thích từng dòng:

1. `Source<Dog> parent = child` hợp lệ vì `DogSource extends Source<Dog>`. Kiểu tĩnh của `parent.read()` là `Dog` theo `T = Dog`; implementation runtime là `DogSource.read()`.
2. `child.read().bark()` hợp lệ vì lớp con override trả `Dog`, cho phép dùng API riêng của `Dog`.
3. `child.copy()` trả `DogSource` — một subtype của `Source<Dog>` — nhờ covariant return, nên tiếp tục gọi `read()` với kiểu đúng.
4. `Provider<Animal> provider` dùng implementation `AnimalProvider.get()` trả `Dog`. Điều này đúng vì `Dog` là `Animal`; nó **không** làm biến `provider` có kiểu `Provider<Dog>`.
5. `AnimalCatalog.animals()` trả `List<? extends Animal>`, cho phép `DogCatalog.animals()` override bằng `List<Dog>`. Danh sách tên được giữ thứ tự từ `List.of(...)`.
6. Reflection đếm bridge methods được compiler tạo trong `DogSource` cho `read()` và `copy()`. Phần này chỉ nhằm kiểm chứng cơ chế biên dịch, không phải điều kiện mà logic ứng dụng nên dựa vào.

**Ghi chú về tính xác định:** `Dog.name()` lấy từ lớp `Animal`, chuỗi `gâu` được ghi tường minh; thứ tự của `List.of(...)` giữ nguyên theo đầu vào. Mã không phụ thuộc múi giờ, mạng, I/O file hay dữ liệu ngẫu nhiên. Trên một bản cài đặt compiler thông thường tương thích với ví dụ này, số bridge method phản ánh đúng các override chuyên biệt; khi thay đổi chữ ký, kết quả đếm có thể đổi.

## 13. Những lỗi thường gặp

| Biểu hiện / đoạn mã | Nguyên nhân | Sửa đúng |
| --- | --- | --- |
| `Animal get()` ở cha, `Object get()` ở con | Mở rộng kiểu trả về thay vì trả subtype; không bảo đảm contract | Giữ `Animal` hoặc trả một subtype như `Dog`. |
| `int count()` ở cha, `long count()` ở con | Primitive không covariant theo quan hệ kế thừa lớp | Giữ `int` trong override. |
| `List<Animal> findAll()` ở cha, `List<Dog> findAll()` ở con | Generic type arguments invariant | Thay contract cha bằng `List<? extends Animal>` nếu chỉ đọc, hoặc generic hóa cha thành `Service<T>`. |
| Override `handle(Animal)` bằng `handle(Dog)` | Đổi tham số tạo overload thay vì override | Giữ danh sách tham số, chỉ làm hẹp kiểu kết quả hợp lệ. |
| Thêm `throws Exception` khi cha chỉ khai báo `IOException` | Checked exception rộng hơn contract | Giữ hoặc thu hẹp checked exceptions. |
| Giảm `public` thành `protected` hay `private` | Override không được thu hẹp khả năng truy cập | Giữ `public` hoặc tăng mức truy cập khi hợp lệ. |
| Gắn `@Override` trên `static` method | Static method được hide, không override động | Thiết kế instance method nếu cần đa hình. |
| Ghi đè method `final` | `final` cấm override | Sửa thiết kế, composition hoặc dùng phương thức mở rộng khác. |
| Gọi `new Parent<Dog>` rồi cast thành `Parent<Animal>` | Invariance; phép cast không làm hợp đồng an toàn | Dùng `Parent<? extends Animal>` cho mục đích đọc, hoặc API generic phù hợp. |
| Quên `@Override` | Lỗi chính tả/chữ ký dễ biến thành overload ngoài ý muốn | Thêm `@Override` cho mọi override thật sự. |
| Tự cast `(Dog) super.get()` mà không kiểm soát invariant | Có thể gây `ClassCastException` | Cố định type argument ở cha hoặc kiểm tra invariant, tránh cast vô căn cứ. |
| Cố overload hai method chỉ khác kiểu trả về | Java không phân giải overload chỉ bằng kết quả | Dùng tên khác hoặc tham số khác có ý nghĩa. |
| Tự viết bridge method vì nghĩ erasure làm mất đa hình | Compiler đã sinh bridge khi cần | Viết override có type safety và để compiler xử lý bytecode. |
| Dùng raw `List`/`Source` cho hết lỗi generic | Bỏ bớt kiểm tra kiểu; có thể sinh unchecked warnings | Sửa quan hệ kiểu thật, không che cảnh báo. |

### Cách đọc lỗi compiler khi override

Khi compiler báo kiểu trả về "incompatible", hãy lần lượt trả lời:

1. Phương thức cha có **đúng chữ ký sau khi thế type arguments** nào? `T` đã cố định thành `Dog`, `Animal` hay `List<Animal>`?
2. Phương thức con có thật sự override (cùng tên/danh sách tham số hợp lệ) hay chỉ overload?
3. Kết quả con có phải subtype phù hợp của kết quả cha **sau phép thế generics** không?
4. Nếu kết quả là một generic type, liệu quan hệ subtype thực sự tồn tại hay bạn đang suy từ `Dog extends Animal` sang `List<Dog> extends List<Animal>` một cách sai lầm?
5. Mức truy cập, checked exception, `static`, `final` có cản trở override không?
6. Có raw type/unchecked conversion từ code cũ khiến chữ ký bạn nhìn thấy khó hiểu không?

Đây là thứ tự kiểm tra hiệu quả hơn so với việc thử thêm cast rồi xóa từng cảnh báo.

## 14. Bài tập tự luyện

**Bài 1 — Override cơ bản.** Tạo `class Vehicle` và `class Bike extends Vehicle`. Viết `VehicleFactory.create(): Vehicle` và `BikeFactory.create(): Bike`. Gọi qua biến `VehicleFactory` trỏ tới `BikeFactory`, ghi chú sự khác nhau giữa kiểu tĩnh của kết quả và class runtime.

**Bài 2 — Generic superclass với kiểu cố định.** Viết `class Box<T>` có `T get()`. Tạo `class BikeBox extends Box<Bike>` và override `get()` nếu muốn thêm hành vi. Chứng minh `Box<Bike> ref = new BikeBox(...)` hợp lệ và `Box<Vehicle> ref = new BikeBox(...)` không hợp lệ.

**Bài 3 — Hiệp biến kết quả factory.** Viết `class CopySource<T>` có `CopySource<T> duplicate()`. Tạo `class StringSource extends CopySource<String>` với override trả `StringSource`. Giải thích vì sao kiểu trả về con không phá hợp đồng cha.

**Bài 4 — Collection và wildcard.** Cho `List<Vehicle> vehicles()` ở cha. Thử override bằng `List<Bike> vehicles()` và xem lỗi. Chuyển kiểu kết quả cha thành `List<? extends Vehicle>` rồi kiểm chứng override hợp lệ. Thử `list.add(new Vehicle())` trên biến `List<? extends Vehicle>` và giải thích việc compiler từ chối.

**Bài 5 — Interface generic.** Định nghĩa `Provider<T>` với `T get()`. Tạo `Provider<Vehicle>` bằng implementation trả `Bike`. Tại sao `Provider<Bike> p = ...` không suy ra hợp lệ chỉ từ việc implementation trả `Bike`?

**Bài 6 — Bytecode bridge.** Biên dịch ví dụ `Source<T extends Animal>`/`DogSource`, chạy `javap -c -p` trên class con (với tên nested class tương ứng). Tìm các phương thức `bridge` do compiler sinh; giải thích tại sao gọi qua tham chiếu cha vẫn đi tới override con.

**Bài 7 — Hợp đồng ngoại lệ.** Lớp cha khai báo `Animal read() throws IOException`. Viết lớp con override trả `Dog`, có thể khai báo `throws FileNotFoundException`. Thử thay `IOException` bằng `Exception` trong override và giải thích lỗi.

**Bài 8 — Đọc chữ ký.** Giả sử `class AnimalRepo<T extends Animal> { List<T> all(); }`. Tạo `class DogRepo extends AnimalRepo<Dog>`. Kiểu kết quả của `all()` là gì? Có cần `@Override` để đơn thuần kế thừa không? Vì sao cố ghi đè thành `List<Animal>` là sai?

## 15. Tổng kết nhanh

- **Covariant return** cho phép override phương thức instance bằng kiểu trả về là subtype phù hợp của kiểu trả về mà hợp đồng cha yêu cầu.
- Trong generic inheritance, phải **thế tham số kiểu của lớp cha** trước khi quyết định kiểu kết quả ở lớp con, ví dụ `Parent<T>` với `extends Parent<Dog>`.
- `Dog extends Animal` **không kéo theo** `List<Dog> extends List<Animal>`. Invariance của generic types và covariance của kiểu trả về là hai khái niệm khác nhau.
- `List<Dog>` có thể thay `List<? extends Animal>` khi contract chỉ cần đọc các giá trị như `Animal`.
- Kiểu trả về có thể thu hẹp, nhưng **tham số, mức truy cập, checked exception, static/final** vẫn phải tuân thủ quy tắc override.
- **Bridge methods** là chi tiết compiler để kết hợp erasure với polymorphism; không cần tự triển khai.
- Chọn hợp đồng API trước, dùng `@Override` và kiểu generic chính xác, kiểm thử compile-time; đừng dùng raw type hoặc unchecked cast để che các quan hệ kiểu sai.

Khi đọc một override trong lớp generic, hãy tự đặt câu hỏi cuối cùng: **“Nếu client chỉ biết đến lớp cha, kết quả mà lớp con trả ra có luôn thỏa hợp đồng ấy hay không?”** Nếu câu trả lời có thể được compiler chứng minh bằng quan hệ subtype và generic đúng đắn, covariant return là một công cụ mạnh giúp API chuyên biệt mà vẫn giữ tính thay thế (substitutability).
