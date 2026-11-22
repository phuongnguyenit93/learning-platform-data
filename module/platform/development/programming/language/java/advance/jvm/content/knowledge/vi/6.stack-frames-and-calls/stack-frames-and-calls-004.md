# Phân giải phương thức và chọn phương thức theo kiểu thực của đối tượng trong JVM

Khi một biến Java khai báo kiểu cha nhưng trỏ tới đối tượng lớp con, lời gọi phương thức instance có thể chạy phần triển khai của lớp con. Ví dụ `Animal animal = new Dog(); animal.sound();` có thể gọi `Dog.sound()`, dù tên phương thức trong bytecode của đoạn gọi được tham chiếu qua `Animal`. Để giải thích chính xác hành vi này phải tách **phân giải tham chiếu phương thức (method resolution)** và **lựa chọn phương thức để thực thi (method selection/dispatch)**.

Trong JVM, hai công việc ấy không phải một thao tác: **resolution** tìm một phương thức phù hợp với tham chiếu ký hiệu trong constant pool; còn **selection** ở `invokevirtual`/`invokeinterface` xét **kiểu runtime của đối tượng receiver** và phương thức đã được phân giải để chọn cách triển khai thích hợp. Đó là nền tảng cho overriding và đa hình động. Bài tập trung vào cơ chế JVM Java SE 17, liên hệ với cách `javac` chọn overload, mã lệnh gọi, JVM frames, interface default methods, bridge methods và các trường hợp không dispatch động.

## 1. Ba khái niệm cần phân biệt

| Giai đoạn | Câu hỏi phải trả lời | Dữ liệu được dùng |
| --- | --- | --- |
| **Compile-time method lookup / overload resolution** (JLS `15.12`) | Trong các tên trùng nhau, lời gọi source chọn **chữ ký nào**? | Kiểu tĩnh của biểu thức, kiểu đối số, khả năng áp dụng overload, generic inference và quy tắc chọn most-specific |
| **JVM symbolic reference resolution** (JVMS `5.4.3`) | Constant-pool method reference đang gọi được gắn với method nào, có hợp lệ về class/interface, tên, descriptor và quyền truy cập? | Methodref/InterfaceMethodref, class loader, hệ thống class/interface, name + descriptor và kiểm tra liên kết |
| **Run-time method selection** (JVMS `5.4.6`) | Với `invokevirtual` hoặc `invokeinterface`, object thực sự cần chạy implementation nào? | **Run-time class của receiver**, phương thức đã resolve và quy tắc overriding/inheritance |

Ví dụ một biểu thức `animal.sound()`:

1. Compiler biết `animal` có kiểu tĩnh `Animal`, xác định lời gọi `sound()` hợp lệ và descriptor trả về phù hợp.
2. Trong class file, invocation tham chiếu ký hiệu kiểu như `Animal.sound:()Ljava/lang/String;`.
3. JVM phân giải method reference đó theo quy tắc liên kết.
4. Khi chạy lệnh `invokevirtual` trên object thực `Dog`, JVM chọn implementation `Dog.sound()` nếu đó là override hợp lệ.
5. JVM tạo frame/cơ chế gọi tương ứng và chuyển điều khiển tới code đã chọn.

**Kết luận then chốt:** kiểu tĩnh quyết định **lời gọi nào hợp lệ và overload nào được mã hóa**; kiểu runtime quyết định **override nào được chạy** đối với lời gọi virtual thích hợp. Không phải mọi opcode gọi method đều dùng bước lựa chọn này.

## 2. Method reference trong class file có những thông tin gì?

Tệp `.class` có một **constant pool** chứa các tham chiếu ký hiệu. Tham chiếu tới phương thức class thường dùng `CONSTANT_Methodref_info`; tham chiếu tới phương thức interface thường dùng `CONSTANT_InterfaceMethodref_info`. Mỗi tham chiếu mang ý nghĩa:

- Một class/interface được tham chiếu bằng tên nhị phân.
- **Tên phương thức**, ví dụ `sound` hoặc `get`.
- **Method descriptor** ghi kiểu tham số và kiểu trả về ở mức JVM.
- Kết hợp các thành phần thành tham chiếu cần resolution, **chưa phải địa chỉ máy** hay con trỏ cố định tới instruction.

Các descriptor minh họa:

| Java method | JVM descriptor |
| --- | --- |
| `String sound()` | `()Ljava/lang/String;` |
| `int add(int a, int b)` | `(II)I` |
| `void accept(Object o)` | `(Ljava/lang/Object;)V` |
| `long calculate(int x, long y)` | `(IJ)J` |
| `String[] split(String text)` | `(Ljava/lang/String;)[Ljava/lang/String;` |

Quy tắc ký hiệu: `I` = `int`, `J` = `long`, `V` = `void`, `L...;` là class/interface reference, dấu `[` là array. **Descriptor JVM có cả kiểu trả về**, còn Java source **không** cho phép overload chỉ khác kiểu trả về. Đó là lý do cần phân biệt “source method signature” với “JVM method descriptor”, đặc biệt khi đọc bridge methods do compiler sinh.

Ví dụ trong disassembly `javap -c -v`:

```text
invokevirtual #N  // Method DispatchWalkthrough$Animal.sound:()Ljava/lang/String;
```

`#N` ở đây là ký hiệu chỗ đứng cho **index thật** của constant pool; đừng coi `N` là một số cố định hoặc là phần output thực tế. Ở `javap`, đích của symbolic reference có thể là `Animal.sound` dù runtime chọn `Dog.sound`. Việc thấy tên lớp cha trong constant pool **không bác bỏ** dispatch động.

### Method resolution không đồng nhất với class initialization

- Loading chuẩn bị biểu diễn kiểu; linking gồm verification, preparation và resolution; initialization chạy `<clinit>` khi các điều kiện kích hoạt xảy ra.
- Method resolution tìm method được tham chiếu và kiểm tra hợp lệ của liên kết; class initialization là quá trình khác. `invokestatic` có thể khiến class/interface được initialize theo quy tắc riêng.
- JVMS cho phép implementation thực hiện resolution theo chiến lược phù hợp (ví dụ chủ động hoặc khi cần); đừng khẳng định mọi tham chiếu method “chỉ được resolve đúng lần đầu gọi” hoặc “bắt buộc resolve hết lúc khởi động”.
- JVM có thể cache kết quả resolution hoặc tối ưu call site; đó là chi tiết triển khai. Bảo đảm được quy định nằm ở **hành vi quan sát được**.

## 3. Java chọn overload tại compile time, rồi JVM mới chọn override

Hai từ thường bị nhầm:

- **Overloading:** nhiều method cùng tên nhưng khác danh sách tham số; compiler chọn method áp dụng và phù hợp nhất theo **kiểu tĩnh** tại nơi gọi. Đây không phải runtime dispatch theo kiểu thực của đối số.
- **Overriding:** lớp con cung cấp implementation thay thế cho một **instance method** được kế thừa, với điều kiện tương thích về chữ ký, quyền truy cập, kiểu trả về và các quy tắc Java liên quan. Khi lời gọi virtual đến receiver thuộc lớp con, implementation override có thể được chọn.

Ví dụ:

```java
class Animal { }
class Dog extends Animal { }

static String describe(Animal a) { return "Animal"; }
static String describe(Dog d) { return "Dog"; }

Animal value = new Dog();
System.out.println(describe(value)); // Animal
```

Đây là **đoạn trích minh họa**, đặt trong một class thích hợp để biên dịch. `describe(value)` chọn overload `describe(Animal)` vì tại source `value` có kiểu **Animal**. JVM không “đổi overload” thành `describe(Dog)` khi phát hiện object runtime là Dog. Muốn dùng overload khác phải viết lời gọi có kiểu tĩnh tương ứng (ví dụ cast hợp lệ), hoặc dùng cơ chế dispatch theo đối tượng chủ động.

Ngược lại:

```java
Animal value = new Dog();
System.out.println(value.sound()); // Giả sử Dog override sound()
```

Compiler chọn method có descriptor `sound()` trên kiểu tĩnh `Animal`; sau resolution, `invokevirtual` có thể chọn body override ở `Dog`. Hai bước liên quan **khác loại lựa chọn**.

### Cảnh báo về cast

`((Dog) value).sound()` làm biểu thức có kiểu tĩnh `Dog` và runtime kiểm tra cast. Nhưng ngay cả khi **không cast**, `value.sound()` đã có thể gọi `Dog.sound()` nếu override hợp lệ. Cast không phải điều kiện cần của dynamic dispatch; nó chủ yếu thay đổi những method được phép truy cập tại compile time, overload được chọn, hoặc thực hiện cast check.

## 4. Quy tắc lựa chọn của `invokevirtual` và `invokeinterface`

Sau khi đã resolve method reference, khi thực thi `invokevirtual`/`invokeinterface`, JVM xét **class runtime của receiver** và method đã resolve. Mô hình học tập cho những trường hợp instance method thông thường:

1. Nếu receiver là `null`, lời gọi instance tương ứng gây `NullPointerException`, không có object để chọn implementation.
2. Nếu method đã resolve thuộc trường hợp đặc biệt `ACC_PRIVATE`, selection không diễn ra như một method có thể được override.
3. Với method có thể override, xét class runtime của receiver: có declaration method override phù hợp thì chọn nó.
4. Nếu class ấy không khai báo override, đi lên superclass gần nhất có implementation override phù hợp.
5. Nếu không tìm được trong chuỗi class, xét các **maximally-specific superinterface methods** theo quy tắc JVMS; một default method phù hợp có thể được chọn.
6. Nếu không có implementation cụ thể phù hợp, hoặc có xung đột mặc định đặc biệt do thay đổi binary, việc gọi có thể gây liên kết/lỗi thời gian chạy như `AbstractMethodError` hoặc `IncompatibleClassChangeError`.

Các chi tiết đầy đủ như method access, override rules, interface/Object methods, abstract/default methods và lỗi liên kết được JVMS `5.4.3.3–`5.4.6 và từng `invoke*` quy định. Đừng giản lược selection thành “luôn tìm method đầu tiên trùng tên trên object”: **descriptor và khả năng override hợp lệ** cũng quan trọng.

Ví dụ hierarchy:

```text
Animal
  ├─ sound()       [Animal body]
  └─ eat()         [Animal body]
      ^
      |
     Dog
      └─ sound()   [Dog override]

Animal a = new Dog();
a.sound()  → Dog.sound()
a.eat()    → Animal.eat() (Dog không override)
```

Điểm quan trọng là “method thật được gọi theo runtime type” **không có nghĩa** mọi method thuộc class runtime đều được phép gọi. Một lời gọi như `a.bark()` vẫn bị compiler từ chối nếu `Animal` không khai báo/không thừa kế method `bark()`, dù object runtime là Dog.

## 5. Nhóm opcode invocation: lệnh nào dispatch động?

| Opcode JVM | Cách dùng chính | Quan hệ với kiểu runtime receiver |
| --- | --- | --- |
| `invokevirtual` | Method instance thông thường của class; phần lớn lời gọi có override | **Có selection** dựa trên receiver class và method đã resolve |
| `invokeinterface` | Lời gọi instance thông qua interface method reference | **Có selection** theo receiver, class hierarchy/default interface methods |
| `invokespecial` | Constructor `<init>`, lời gọi `super.m()`, một số lời gọi instance đặc biệt/private | Có các quy tắc tìm đích riêng; **không** sử dụng cơ chế dispatch virtual thông thường |
| `invokestatic` | Method `static` của class hoặc interface | Không có receiver để dispatch theo runtime; tìm method static đã resolve |
| `invokedynamic` | Dynamic call site được liên kết qua bootstrap method, như nhiều lambda/string concat do compiler tạo | Cơ chế liên kết call site riêng, **không** đồng nghĩa “invokevirtual chọn override” |

### `invokevirtual`

Nhận **object reference** cùng các đối số trên operand stack, dùng method reference từ constant pool, rồi chọn target theo runtime receiver. Nếu target không phải `native`, thông thường JVM tạo một **frame** cho method được gọi; frame nhận receiver tại local slot 0 và tham số ở các slot kế tiếp. Mô hình frame ở phần sau sẽ minh họa.

### `invokeinterface`

Dùng interface method reference trong constant pool, nhưng object thực thi có runtime class cụ thể. Ví dụ:

```java
Runnable task = new SomeRunnable();
task.run();
```

Ở đây chỉ là **đoạn minh họa**; `SomeRunnable` giả định implements `Runnable` và có method `run`. Compiler có thể sinh `invokeinterface Runnable.run:()V`. Target thực tế được chọn theo class của `task` (hoặc inherited implementation), không chạy bytecode “nằm trong interface” nếu interface method trừu tượng.

### `invokespecial`

Dùng cho những lời gọi có quan hệ ngữ nghĩa đặc biệt, chẳng hạn `new Dog()` cần gọi constructor `<init>`, hoặc `super.sound()` cố ý bắt đầu theo quy tắc superclass. Với class file có `ACC_SUPER`, JVM có thêm quy tắc lookup cho `super`; nói `invokespecial` “chỉ thực thi chính xác method có tên trên constant pool, không có lookup” là quá đơn giản. Nhưng nó **không chọn override từ class runtime receiver như `invokevirtual`**.

### `invokestatic`

Method static thuộc về class/interface được dùng tại compile time/link time, không phải instance. `static` trong subclass có thể **hide** method static superclass, nhưng không override. Gọi `Animal.category()` và `Dog.category()` chọn hai method khác nhau theo tên class trong source. Lời gọi qua biến `Animal ref = new Dog(); ref.category();` hợp lệ trong Java nhưng không nên viết kiểu đó vì dễ khiến người đọc tưởng có dispatch động; mục tiêu vẫn thuộc `Animal`.

### `invokedynamic`

`invokedynamic` liên kết một **call site** qua thông tin bootstrap của constant pool. Nó thường xuất hiện trong bytecode compiler tạo cho lambda hoặc string concatenation trên Java hiện đại. Hành vi cụ thể phụ thuộc bootstrap và target call site; không mặc định áp dụng bảng chọn override của `invokevirtual` cho chính opcode `invokedynamic`, dù method được liên kết sâu hơn có thể thực hiện lời gọi ảo khác.

## 6. Chương trình Java 17: thấy rõ override, overload, static hiding, super và private

Tạo file **`DispatchWalkthrough.java`**:

```java
public class DispatchWalkthrough {

    static class Animal {
        public String sound() {
            return "Animal";
        }

        public String eat() {
            return "Animal.eat";
        }

        public static String category() {
            return "Animal.category";
        }

        private String secret() {
            return "Animal.secret";
        }

        public String reveal() {
            return secret();
        }
    }

    static class Dog extends Animal {
        @Override
        public String sound() {
            return "Dog";
        }

        public String bark() {
            return "woof";
        }

        public static String category() {
            return "Dog.category";
        }

        private String secret() {
            return "Dog.secret";
        }

        public String revealDog() {
            return secret();
        }

        public String callSuper() {
            return super.sound();
        }
    }

    static String describe(Animal value) {
        return "describe(Animal)";
    }

    static String describe(Dog value) {
        return "describe(Dog)";
    }

    public static void main(String[] args) {
        Animal ref = new Dog();
        Dog dog = new Dog();

        System.out.println("virtual=" + ref.sound());
        System.out.println("inherited=" + ref.eat());
        System.out.println("overload=" + describe(ref));
        System.out.println("overloadDog=" + describe(dog));

        // Cố tình minh họa lời gọi static qua reference;
        // code thực tế nên dùng Animal.category() trực tiếp.
        System.out.println("static=" + ref.category());
        System.out.println("super=" + dog.callSuper());
        System.out.println("private=" + ref.reveal());
        System.out.println("dogPrivate=" + dog.revealDog());

        try {
            Animal missing = null;
            missing.sound();
        } catch (NullPointerException ex) {
            System.out.println("null=NPE");
        }
    }
}
```

Biên dịch/chạy trên JDK có `javac` hỗ trợ Java 17:

```bash
javac --release 17 DispatchWalkthrough.java
java DispatchWalkthrough
```

**Stdout**:

```text
virtual=Dog
inherited=Animal.eat
overload=describe(Animal)
overloadDog=describe(Dog)
static=Animal.category
super=Animal
private=Animal.secret
dogPrivate=Dog.secret
null=NPE
```

Giải thích từng dòng:

- `virtual=Dog`: `ref` có kiểu tĩnh `Animal` nhưng object runtime là `Dog`; `Dog.sound()` override nên được chọn.
- `inherited=Animal.eat`: `Dog` không override `eat`, vì vậy body kế thừa từ `Animal` thực thi.
- `overload=describe(Animal)`: `describe(ref)` chọn overload theo kiểu **Animal** đã biết lúc compile.
- `overloadDog=describe(Dog)`: `dog` có kiểu tĩnh `Dog`, chọn overload dành cho Dog.
- `static=Animal.category`: static method được xác định theo kiểu tĩnh `Animal` dù `ref` trỏ tới Dog. Đó là **method hiding**, không phải polymorphic override.
- `super=Animal`: trong `Dog.callSuper()`, `super.sound()` cố ý gọi implementation superclass theo ngữ nghĩa `invokespecial`.
- `private=Animal.secret`: `Animal.reveal()` gọi method **private** của chính `Animal`. `Dog.secret()` có cùng tên nhưng không override method private ấy.
- `dogPrivate=Dog.secret`: body `Dog.revealDog()` gọi method private của `Dog`.
- `null=NPE`: instance receiver `null` không thể được dispatch đến implementation.

`Dog.bark()` tồn tại trên object thật, nhưng thêm `ref.bark();` sẽ **không biên dịch**, vì kiểu tĩnh `Animal` không có method đó. Đa hình động không thay thế kiểm tra kiểu của compiler.

### Đọc bytecode đúng nơi

Chạy disassembler:

```bash
javap -c -p DispatchWalkthrough
javap -c -p 'DispatchWalkthrough$Dog'
javap -v -p 'DispatchWalkthrough$Animal'
```

Các điểm cần quan sát trên class do `javac` tạo:

- Trong `DispatchWalkthrough.main`, lời gọi `ref.sound()` thường hiện với opcode **`invokevirtual`**, tham chiếu tới method kiểu `DispatchWalkthrough$Animal.sound:()Ljava/lang/String;`. Object chạy lúc đó là `Dog` nên kết quả `Dog`.
- Trong `Dog.callSuper()`, phần gọi `super.sound()` dùng **`invokespecial`** đến method của lớp cha.
- Với `describe(...)` và `category()`, vì method là static, bytecode dùng **`invokestatic`** đến method được compiler chọn theo kiểu.
- Constructor `Dog.<init>` gọi constructor `Animal.<init>` với **`invokespecial`**.
- Lời gọi private liên quan có thể có cách biểu diễn bytecode tùy Java release/compiler và quy tắc private method; bản chất vẫn là method **không thể bị override**. Không biến một mẫu disassembly thành khẳng định “mọi private call luôn luôn mang opcode duy nhất X”.

Trong kết quả `javap`, index constant pool `#7`, `#15`… và offset bytecode phụ thuộc build/compiler, nên **không gán cố định** các con số đó cho mọi môi trường. Thêm nữa, các biểu thức nối chuỗi như `"virtual=" + ref.sound()` trên JDK 17 có thể xuất hiện `invokedynamic` phục vụ string concatenation; nó **không làm mất** việc `ref.sound()` được thực thi theo quy tắc lời gọi instance riêng.

## 7. Theo dõi operand stack và frame khi gọi một instance method

Xét riêng:

```java
Animal receiver = new Dog();
String result = receiver.sound();
```

Đây là đoạn **minh họa đặt trong một method**. Một chuỗi bytecode tiêu biểu cho phần lời gọi có thể là:

```text
aload_1                 // nạp reference receiver lên operand stack
invokevirtual #N        // Method Animal.sound:()Ljava/lang/String;
astore_2                // lưu String result vào local slot tương ứng
```

Số index locals và constant pool là **minh họa**, phụ thuộc cách compiler bố trí frame. Luồng ý nghĩa:

1. Frame caller đang tồn tại; local variable chứa reference tới object `Dog`.
2. `aload` sao chép reference lên **operand stack** của caller. Nó không sao chép toàn bộ Dog object.
3. `invokevirtual` đọc symbolic reference và thực hiện các kiểm tra/selection thích hợp. Method đã resolve đóng vai trò điểm bắt đầu, class runtime `Dog` dẫn đến method `Dog.sound`.
4. Các đối số (nếu có) và reference receiver được lấy từ operand stack của caller; với method Java thông thường, frame callee được tạo và nhận receiver trong **local slot 0** (`this`), các tham số ở slots tiếp theo.
5. Code của `Dog.sound` thực thi trong frame callee, trả về `String` reference qua `areturn`; kết quả trở lại operand stack của caller.
6. Caller dùng `astore` hoặc thao tác khác với kết quả.

Với method `static`, `invokestatic` không cần receiver slot 0; tham số đầu tiên bắt đầu ở local 0. Với method instance, tham số `long`/`double` chiếm hai local slots. **Kiểu object được chọn để dispatch không thay đổi vị trí `this` ở slot 0** của frame method được gọi.

### Phân giải một lần hay mỗi invocation?

Đặc tả phân biệt symbolic reference resolution và lựa chọn invocation; JVM có thể cache kết quả resolution/dispatch, dùng bảng method hoặc tối ưu JIT. Trong ví dụ, nhiều lần gọi `receiver.sound()` không buộc JVM phải thực hiện lại mọi lookup bằng thuật toán chậm trong một vòng lặp. Nhưng dù triển khai tối ưu kiểu gì, **kết quả quan sát được phải như ngữ nghĩa chuẩn**.

## 8. Interface methods và default methods: receiver vẫn quyết định implementation

Interface có thể khai báo method trừu tượng hoặc cung cấp **default method**. `invokeinterface` dựa trên reference tới interface method, sau đó selection dựa vào class runtime receiver và cấu trúc triển khai.

Tạo file độc lập **`InterfaceDispatch.java`**:

```java
public class InterfaceDispatch {

    interface Speaker {
        default String text() {
            return "Speaker";
        }
    }

    static class Basic implements Speaker {
        // Kế thừa default method Speaker.text()
    }

    static class Premium extends Basic {
        @Override
        public String text() {
            return "Premium";
        }
    }

    static class Decorated implements Speaker {
        @Override
        public String text() {
            return "Decorated(" + Speaker.super.text() + ")";
        }
    }

    public static void main(String[] args) {
        Speaker first = new Basic();
        Speaker second = new Premium();
        Speaker third = new Decorated();

        System.out.println("first=" + first.text());
        System.out.println("second=" + second.text());
        System.out.println("third=" + third.text());
    }
}
```

```bash
javac --release 17 InterfaceDispatch.java
java InterfaceDispatch
javap -c -p InterfaceDispatch
javap -c -p 'InterfaceDispatch$Decorated'
```

**Stdout của `java InterfaceDispatch`**:

```text
first=Speaker
second=Premium
third=Decorated(Speaker)
```

- `first.text()` có receiver `Basic`; không tìm thấy class override, nên default method `Speaker.text()` thích hợp được dùng.
- `second.text()` có receiver `Premium`; class này override `text` nên chọn body `Premium.text()`.
- `third.text()` chọn `Decorated.text()`; bên trong method này, `Speaker.super.text()` là lời gọi default implementation được chỉ định rõ, thường thể hiện bởi **`invokespecial`** tới method interface phù hợp.
- Ở `InterfaceDispatch.main`, các lời gọi qua biến `Speaker` thường có opcode **`invokeinterface`**.

### Khi class method và interface default cùng tên

Method instance cụ thể phù hợp trong class/superclass được ưu tiên so với default method interface tương ứng. Nếu nhiều default methods từ các interface độc lập gây xung đột khi viết Java source, compiler thường yêu cầu class thực thi cung cấp override để giải quyết. Không nên giả định JVM sẽ tự chọn ngẫu nhiên một default method khi có hai lựa chọn xung đột.

Với class files được sinh từ các bản thư viện **không tương thích** sau binary evolution, những tình huống không còn một target hợp lệ có thể dẫn tới lỗi liên kết như `IncompatibleClassChangeError` hay `AbstractMethodError`; đó là lý do thay đổi API interface cần kiểm tra binary compatibility.

## 9. Overriding phụ thuộc chữ ký và khả năng kế thừa: không chỉ trùng tên

Những điều kiện quyết định một method có override method đã resolve hay không gồm:

- **Tên và chữ ký thích hợp**, với các quy tắc về erasure/subsignature, return-type substitutability và visibility theo JLS.
- **Instance vs static:** static method chỉ có thể hide, không override instance method. Java cấm “override static bằng instance” hoặc ngược lại khi hai method có cùng signature phù hợp.
- **`private`:** method private không được kế thừa để override theo cách thông thường. Class con có thể có method cùng tên độc lập.
- **`final`:** method instance final không cho class con override hợp lệ; JVM có thể tối ưu vì target không bị thay thế bởi subclass theo quy tắc Java.
- **Package-private:** quan hệ override phụ thuộc khả năng kế thừa/khả năng truy cập giữa package và class hierarchy; không thể chỉ so tên rồi kết luận.
- **`abstract`:** method được khai báo nhưng không có body; object cụ thể phải có implementation hợp lệ trước khi việc gọi đó thành công.
- **Interface defaults:** có các quy tắc ưu tiên, maximally-specific và giải quyết xung đột.

### Một phản ví dụ với field

`Field access` thường quyết định field theo kiểu tĩnh (và symbolic reference) của biểu thức, không dùng cùng kiểu override dispatch của instance methods.

```java
class Base {
    String name = "Base-field";
    String who() { return "Base-method"; }
}
class Child extends Base {
    String name = "Child-field";
    @Override String who() { return "Child-method"; }
}
```

Nếu `Base x = new Child();` thì `x.name` đọc field được chọn từ kiểu `Base` và trả `"Base-field"`, còn `x.who()` chạy override `Child.who()`. Đây là **đoạn minh họa** để phân biệt field hiding và method overriding; không phải chương trình độc lập.

## 10. Generics, erasure và bridge methods có thể làm bytecode khác source

Java generics được triển khai với **type erasure**. Khi kiểu trả về ở source là covariant hoặc khi erasure khiến chữ ký bytecode khác nhau, compiler có thể sinh **bridge method** mang flags `ACC_BRIDGE` và `ACC_SYNTHETIC` để giữ đúng hành vi polymorphism và binary linkage.

Tạo **`BridgeDispatch.java`**:

```java
public class BridgeDispatch {

    static class Box<T> {
        T value() {
            return null;
        }
    }

    static class TextBox extends Box<String> {
        @Override
        String value() {
            return "hello";
        }
    }

    public static void main(String[] args) {
        Box<String> box = new TextBox();
        System.out.println("value=" + box.value());
    }
}
```

```bash
javac --release 17 BridgeDispatch.java
java BridgeDispatch
javap -c -v -p 'BridgeDispatch$TextBox'
```

**Stdout**:

```text
value=hello
```

Trong bytecode của `Box<T>`, method sau erasure có descriptor `value:()Ljava/lang/Object;`. `TextBox` khai báo method trả `String` với descriptor `value:()Ljava/lang/String;`. `javac` thường tạo thêm **bridge** trong `TextBox` có descriptor trả `Object`; bridge gọi method trả `String` thực tế.

Vì vậy, một lời gọi có symbolic reference đến `Box.value:()Ljava/lang/Object;` vẫn có thể dispatch tới **bridge `TextBox.value:()Ljava/lang/Object;`**, sau đó bridge chuyển tới body `TextBox.value:()Ljava/lang/String;`. Từ đó hiểu vì sao đôi khi `javap -p` thấy hai method trùng tên dù source chỉ khai báo một method.

Đừng xóa bridge method khỏi bytecode chỉ vì nó `synthetic`: các caller đã biên dịch có thể cần method đó để giữ hành vi gọi tương thích.

## 11. Những lỗi runtime liên quan tới resolution/selection

JVM không được phép chọn method bất kỳ nếu tham chiếu không hợp lệ. Phân biệt một số nhóm lỗi:

| Lỗi thường gặp | Tình huống điển hình | Ý nghĩa khi debug |
| --- | --- | --- |
| `NoSuchMethodError` | Caller đã biên dịch đối với descriptor/method tồn tại, nhưng thư viện runtime không còn method phù hợp | Kiểm tra **phiên bản binary**, descriptor, classpath/module path |
| `IllegalAccessError` | Method/reference không còn truy cập được theo quy tắc liên kết | Kiểm tra visibility, package/module và binary compatibility |
| `IncompatibleClassChangeError` | Caller kỳ vọng static/instance/interface/class không khớp hoặc interface defaults xung đột | Kiểm tra sự thay đổi hình dạng API giữa compile và runtime |
| `AbstractMethodError` | Target chọn được nhưng trừu tượng, không có implementation cụ thể tương ứng | Kiểm tra thay đổi interface/class library và class files |
| `NullPointerException` | Lời gọi instance dùng receiver `null` | Kiểm tra data flow của reference, không quy về thiếu method |
| `VerifyError` | Bytecode vi phạm ràng buộc typing/stack/control flow | Kiểm tra generator/instrumentation và verification metadata |
| `ExceptionInInitializerError` | Class initialization chạy `<clinit>` lỗi theo điều kiện chuẩn | Phân biệt lỗi khởi tạo class với lỗi tìm method |

Đây là các ví dụ **điển hình**, không phải “một lỗi chỉ có duy nhất nguyên nhân X”. Hãy xem stack trace, cause, Java version, class loader và bộ JAR đang chạy. Một test trên JDK mới/IDE có thể vượt qua trong khi production dùng lớp cùng tên từ phiên bản cũ hơn dẫn đến lỗi liên kết.

### Khi thay đổi thư viện, giữ đúng descriptor quan trọng hơn tên method

Ví dụ thư viện phiên bản 1 có `String lookup(int id)`, caller đã biên dịch chứa method reference với descriptor `(I)Ljava/lang/String;`. Nếu runtime được thay bằng thư viện phiên bản 2 **chỉ** có `String lookup(long id)`, hai method khác descriptor: caller cũ có thể bị `NoSuchMethodError`. Nếu chỉ đổi implementation override mà vẫn giữ contract tương thích, dispatch lại có thể hoạt động bình thường. Binary compatibility phải xét **class file và method descriptor**, không chỉ tên trong source.

## 12. Hiệu năng: dispatch động không đồng nghĩa “luôn tìm kiếm tuyến tính mỗi lần gọi”

JVM triển khai có thể dùng method tables, interface lookup caches, profiling hoặc JIT để giảm chi phí invocation. HotSpot JIT có thể **devirtualize** hoặc inline một lời gọi nếu có đủ chứng cứ về target; khi giả thiết không còn đúng, VM có cơ chế guard/deoptimization thích hợp để bảo toàn ngữ nghĩa.

Những phát biểu cần phân tầng:

- **Đặc tả JVMS bảo đảm:** chọn implementation phù hợp theo resolution/selection, ném lỗi tương ứng và giữ kết quả quan sát được.
- **Chi tiết triển khai:** cách HotSpot tra cứu target trong memory, số lần cache lookup, monomorphic/polymorphic call site, thời điểm inline và hình thức machine code.
- **Phép đo thực tế:** benchmark trên đúng JDK build, compiler, flags, workload và trạng thái warm-up.

Không kết luận “virtual luôn chậm hơn static một mức cố định”, “JVM mỗi lần gọi đều đi từng superclass”, hoặc “JIT bỏ được dynamic dispatch nên không còn kiểm tra kiểu” chỉ từ một đoạn `javap`. `javap` cho biết **bytecode invocation**, không hiển thị đầy đủ machine code tối ưu lúc runtime.

## 13. Quy trình đọc và phân tích một lời gọi method

Khi thấy `receiver.m(args)` hoặc một opcode `invoke*`, áp dụng lần lượt:

1. **Chốt Java version và class file đang chạy**: `java -version`, `javac -version`, phiên bản thư viện, runtime classpath/module path.
2. **Ở Java source, xác định kiểu tĩnh** của receiver/arguments và overload đã chọn theo JLS `15.12`. Ghi rõ cast/generics/autoboxing/varargs nếu có.
3. **Dùng `javap -c -v -p`**, tìm class method đang chứa call site và instruction `invokevirtual`/`invokeinterface`/`invokestatic`/`invokespecial`/`invokedynamic`.
4. **Đọc constant-pool entry** của instruction: target owner, tên method và JVM descriptor. Nhớ kiểu trả về cũng nằm trong descriptor.
5. **Xác định loại invocation**: virtual/interface cần selection theo receiver; static/special/dynamic có cơ chế khác.
6. **Xác định class runtime thực** của receiver ở call site, không suy diễn từ tên biến. Có thể quan sát hợp lệ qua `obj.getClass()` khi reference không null hoặc qua debugger.
7. **Đi theo override chain**: class runtime, superclass, interface defaults theo JVMS và quyền truy cập. Với generics xem thêm bridge method.
8. **Đọc frame/operand stack nếu cần**: receiver/args được truyền, method có phải instance/static, và kết quả trở lại caller bằng opcode return nào.
9. **Nếu lỗi liên kết**, kiểm tra binary khác phiên bản/loader trước khi kết luận JVM dispatch sai.
10. **Nếu thắc mắc hiệu năng**, tách contract khỏi JIT optimizations; dùng profiling/benchmark, không suy diễn từ `javap`.

### Tự kiểm tra

**Câu 1:** `Parent p = new Child(); p.run();`, `Child` override `run` hợp lệ. Method nào thực thi khi dùng invocation virtual?  
**Đáp:** `Child.run()`, do receiver runtime là `Child`.

**Câu 2:** Hai overload `f(Parent)` và `f(Child)`; gọi `f(p)` với `p` khai báo `Parent` nhưng chứa object Child. Overload nào được chọn?  
**Đáp:** `f(Parent)`, do compiler xét kiểu tĩnh.

**Câu 3:** `Parent p = new Child(); p.staticMethod();` nếu hai class cùng khai báo static method?  
**Đáp:** Phiên bản static thuộc `Parent` được chọn theo kiểu tĩnh; cú pháp gọi qua instance nên tránh trong code thực tế.

**Câu 4:** `Child.callSuper()` thực thi `super.run()`; có chọn `Child.run()` vì object vẫn là Child?  
**Đáp:** Không; `super` yêu cầu lời gọi đặc biệt tới implementation thích hợp của superclass.

**Câu 5:** Một interface default method bị override trong class concrete, biến receiver khai báo kiểu interface. Method nào chạy?  
**Đáp:** Implementation override trong class runtime, theo các quy tắc selection thích hợp.

**Câu 6:** Vì sao `javap` có thể thấy method bridge mà source không khai báo?  
**Đáp:** Compiler tạo method synthetic/bridge để duy trì hợp đồng polymorphism sau erasure/covariant return.

**Câu 7:** Constant pool hiện `Animal.sound`, nhưng output của object Dog lại là `Dog`; có lỗi không?  
**Đáp:** Không. Tham chiếu ký hiệu được resolve riêng; `invokevirtual` chọn implementation theo receiver runtime.

## 14. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Resolution chọn luôn method thực thi cuối cùng” | Với `invokevirtual`/`invokeinterface` còn có **selection** dựa vào object runtime |
| “Overload được quyết định khi JVM thấy object” | Overload source được compiler chọn theo kiểu tĩnh và quy tắc method invocation |
| “Kiểu tĩnh của biến buộc lời gọi luôn chạy ở class cha” | Kiểu tĩnh ràng buộc lời gọi hợp lệ; override có thể chạy theo kiểu runtime |
| “Đối tượng Dog có `bark()` nên biến Animal gọi `bark()` được” | Compiler vẫn yêu cầu member hợp lệ trên kiểu tĩnh hoặc cần cast hợp lệ |
| “Method static được override giống instance method” | Static method có **hiding**, không virtual dispatch |
| “Method private cùng tên ở lớp con override private của cha” | Private superclass method không được override theo cách đó |
| “`super.m()` vẫn chọn override ở receiver class con” | `super` dùng `invokespecial` theo quy tắc lookup đặc biệt |
| “Interface luôn chạy method body định nghĩa trên interface” | Class override có thể được chọn; default method chỉ là một khả năng |
| “Một lời gọi Java bằng một opcode `invokevirtual` trong mọi trường hợp” | Có `invokeinterface`, `invokestatic`, `invokespecial`, `invokedynamic` và compiler transformations |
| “Method bridge là code thừa có thể xóa” | Bridge giữ khả năng gọi đúng sau erasure/covariant return |
| “`javap` nói `Animal.sound` nên JVM không thể gọi Dog” | Constant pool chứa method **tham chiếu**; selection có thể tìm `Dog.sound` |
| “JVM luôn đi từng lớp cha lúc mỗi lần gọi” | Đặc tả quy định kết quả, implementation/JIT có thể tối ưu lookup và inline |

## Tài liệu gốc Java SE 17

- [JLS `15.12` — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): method lookup, overload applicability, most-specific method và runtime invocation.
- [JLS `8.4.8.1` — Overriding (by Instance Methods)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.1): điều kiện overriding.
- [JLS `8.4.8.2` — Hiding (by Class Methods)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.2): method static hiding.
- [JVMS `5.1` — The Run-Time Constant Pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.1): symbolic method references.
- [JVMS `5.4.3.3–`5.4.3.4 — Method / Interface Method Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.3): tìm symbol và ràng buộc liên kết.
- [JVMS `5.4.5 — Method Overriding](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.5) và [`5.4.6 — Method Selection](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.6): quan hệ override và cách chọn target dựa trên kiểu runtime.
- [JVMS `6.5` — Instruction Set](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5): `invokevirtual`, `invokeinterface`, `invokespecial`, `invokestatic`, `invokedynamic`.
- [JVMS `2.6` — Frames](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): operand stack, local variables và frame khi gọi method.
- [JVMS `4.6 — Methods](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.6) và [`4.3.3 — Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3): tên/descriptor và method flags trong class file.
- [Java SE 17 `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): đọc symbolic references và disassembly.

**Ghi nhớ:** **JLS overload** chọn lời gọi dựa vào kiểu tĩnh; **JVM resolution** phân giải method reference trong constant pool; **method selection** của `invokevirtual`/`invokeinterface` chọn implementation dựa trên kiểu runtime của receiver và quan hệ override hợp lệ. Ba tầng này giải thích vì sao cùng một object có thể cho kết quả khác nhau khi gọi overload, override, static hoặc `super`.
