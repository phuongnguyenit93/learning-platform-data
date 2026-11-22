# Khởi tạo interface và ảnh hưởng của default method trong Java

Trong Java, **interface cũng có giai đoạn khởi tạo (initialization)**, dù không thể tạo instance trực tiếp bằng `new Interface()`. Điểm dễ nhầm là quy tắc khởi tạo interface khác với quy tắc của class, và **default method** có thể khiến interface được khởi tạo khi JVM khởi tạo một class triển khai nó, **ngay cả khi chương trình chưa gọi default method đó**.

Theo *Java Language Specification (JLS) §12.4.1*:

- Khởi tạo **class** đòi hỏi khởi tạo các superclass chưa được khởi tạo, đồng thời khởi tạo các **superinterface khai báo ít nhất một default method** phù hợp trong cây kế thừa.
- Khởi tạo **interface** riêng nó **không tự động khởi tạo các superinterface**.
- Interface có thể được khởi tạo vì truy cập một trường `static` không phải *constant variable*, gọi `static` method do nó khai báo, hoặc do một thao tác phản chiếu có yêu cầu initialization.

Cần tách bạch ba việc: JVM đã **nạp** định nghĩa interface, đã **liên kết** interface, và đã **khởi tạo** interface. Chỉ giai đoạn khởi tạo mới chạy logic gán giá trị trường `static` có tính toán của interface.

## 1. Interface được khởi tạo nghĩa là gì?

Với class, ta quen thuộc với `static` field initializer và `static { ... }`. **Interface không cho phép khai báo `static` initializer block**, nhưng field được khai báo trong interface mặc định là `public static final`, và biểu thức khởi tạo các field có thể chạy mã khi interface được initialized.

```java
interface Feature {
    int FIXED_LIMIT = 10;
    int RUNTIME_LIMIT = calculate();

    static int calculate() {
        System.out.println("Feature initialized");
        return 20;
    }

    static void printInfo() {
        System.out.println("Feature.printInfo()");
    }
}
```

Đây là **đoạn minh họa**, không phải file có `main`. Hai field đều ngầm mang `public static final`, nhưng chúng khác nhau quan trọng:

- `FIXED_LIMIT = 10` là một **constant variable**: kiểu primitive/String, `final`, được khởi tạo bằng *constant expression*. Trình biên dịch có thể ghi sẵn `10` vào mã của nơi sử dụng, nên chỉ đọc `Feature.FIXED_LIMIT` **không yêu cầu khởi tạo `Feature`**.
- `RUNTIME_LIMIT = calculate()` **không** phải constant variable, dù cũng là `static final`. Đọc trực tiếp `Feature.RUNTIME_LIMIT` khi interface chưa initialized khiến JVM khởi tạo interface, gọi `calculate()` một lần, rồi nhận `20`.
- `Feature.printInfo()` là lời gọi `static` method do `Feature` khai báo; nếu `Feature` chưa initialized, lời gọi này cũng kích hoạt initialization.

Các trường trong interface được khởi tạo **theo thứ tự khai báo trong mã nguồn**, phù hợp quy tắc khởi tạo của Java. Không được coi mọi field `static final` là giá trị đã được tính sẵn ở compile time.

### Bốn trạng thái thường bị lẫn

| Sự kiện | Ý nghĩa đối với interface `Feature` |
|---|---|
| JVM load/create kiểu | Có biểu diễn runtime `Class<Feature>` và loader phù hợp; chưa chắc chạy các field initializer |
| JVM link kiểu | Verify và prepare; resolution có thể làm theo nhu cầu; chưa đồng nghĩa evaluate `calculate()` |
| JVM initialize interface | Chạy quá trình khởi tạo biến interface (như `RUNTIME_LIMIT = calculate()`) nếu có |
| Tạo object triển khai | Tạo instance của một **class** triển khai `Feature`; không tồn tại `new Feature()` trực tiếp |

Một interface được khởi tạo tối đa một lần thành công cho **mỗi định nghĩa kiểu runtime** (theo defining class loader); nhiều đối tượng của class triển khai không làm nó chạy lại field initializer.

## 2. Những trigger khởi tạo interface

Các trường hợp hay gặp:

| Thao tác | Có bắt buộc initialize interface T chỉ vì thao tác đó? | Lý do |
|---|---|---|
| `T.class` | Không | Class literal lấy đại diện kiểu, không phải active use |
| `Class.forName(name, false, loader)` | Không yêu cầu | Tra cứu/nạp và liên kết kiểu với `initialize=false` |
| `Class.forName(name)` | Có, nếu chưa initialized | Overload này yêu cầu khởi tạo kiểu tìm được |
| `T.CONST` với field là constant variable | Không | Giá trị compile-time constant có thể được inline |
| `T.RUNTIME_FIELD` là field `static` không phải constant variable, do T khai báo | Có | Truy cập trường non-constant là active use |
| `T.staticMethod()`, method do T khai báo | Có | Gọi `static` method là active use |
| `class C implements T { ... }` (chỉ khai báo kiểu) | Không | Quan hệ `implements` không tự nó buộc initialization |
| Initialize class `C implements T`, T **không khai báo default method** | Không chỉ vì `implements` | JVM không buộc initialize mọi interface được triển khai |
| Initialize class `C implements T`, T **khai báo default method** | Có, nếu chưa initialized | Quy tắc khởi tạo superinterface có default method |
| Gọi instance default method trên object của `C` | T đã được initialized nếu T thuộc nhóm bắt buộc trước khi C initialized | Khởi tạo C đã xảy ra trước khi tạo object để gọi method |

Bảng mô tả **yêu cầu bắt buộc** theo Java; một interface có thể đã được initialized từ một nguyên nhân khác trước khi thao tác diễn ra. Reflection và method handles còn có những điểm kích hoạt riêng do API/VM quy định.

**Đặc biệt:** không thể khai báo một `static` method ở interface rồi trông chờ interface triển khai được “kế thừa” method ấy như default method. `static` method của interface được gọi qua tên chính interface khai báo method.

## 3. Vì sao default method làm thay đổi quy tắc?

Default method (Java 8+) là **instance method có phần thân mặc định** khai báo trong interface:

```java
interface Greeting {
    int INIT = logInitialization();

    static int logInitialization() {
        System.out.println("Greeting initialized");
        return 1;
    }

    default String greet() {
        return "Hello";
    }
}
```

`Greeting` không cần instance riêng để tồn tại. Một class có thể triển khai `Greeting` và sử dụng hoặc override `greet()`.

Với:

```java
class Greeter implements Greeting {
    static {
        System.out.println("Greeter initialized");
    }
}
```

Khi JVM **initialize `Greeter`**, nó phải bảo đảm `Greeting` cũng initialized vì `Greeting` khai báo một **default method**. Theo JLS, điều này xảy ra **ngay cả khi constructor của `Greeter` không gọi `greet()` và ngay cả khi `Greeter` override `greet()`**.

Điểm quyết định nằm ở **khai báo default method trong một superinterface** chứ không phải ở việc chương trình đã thực thi phần thân default method bao nhiêu lần. Việc gọi default method sau đó chỉ là thực thi phương thức trên một instance hợp lệ.

### Default method khác static method, abstract method và private interface method

| Method trong interface | Ví dụ | Nó làm interface trở thành superinterface cần initialize khi class triển khai initialized? |
|---|---|---|
| **Default instance method** | `default void run() { }` | **Có** |
| Abstract instance method | `void run();` | **Không chỉ vì method này** |
| Static method | `static void help() { }` | **Không chỉ vì nó tồn tại**; gọi trực tiếp method lại là một trigger khác |
| Private helper method | `private void helper() { }` hoặc `private static void helper() { }` | **Không chỉ vì helper này** |

Một interface có cả abstract, static và default methods vẫn thuộc nhóm phải initialize lúc class triển khai initialized vì nó **có khai báo default method**. Nếu không có default method thì không có yêu cầu đó chỉ từ quan hệ `implements`.

**Cảnh báo với bytecode:** Java compiler có thể sinh *synthetic default methods* trong một số trường hợp. Khi phân tích bytecode thực, quy tắc JVM xét phương thức được khai báo trong định nghĩa kiểu runtime, không chỉ những dòng `default` mà người học trực tiếp nhìn thấy trong Java source.

## 4. Ba quan hệ kế thừa phải phân biệt

### 4.1. Class implements interface chỉ có abstract method

```java
interface AbstractOnly {
    int CHECK = init();

    static int init() {
        System.out.println("AbstractOnly initialized");
        return 1;
    }

    void run();
}

class Implementation implements AbstractOnly {
    @Override
    public void run() { }
}
```

Nếu chương trình chỉ tạo `new Implementation()`, JVM **không bắt buộc** initialize `AbstractOnly` chỉ vì quan hệ implements. Một định nghĩa interface có thể đã được nạp/liên kết để kiểm tra kiểu mà vẫn chưa chạy initializer `CHECK`.

Nhưng truy cập `AbstractOnly.CHECK` sẽ buộc initialize interface đó vì `CHECK` không phải compile-time constant.

### 4.2. Class implements interface có default method

```java
interface WithDefault {
    int CHECK = init();

    static int init() {
        System.out.println("WithDefault initialized");
        return 1;
    }

    default void run() { }
}

class DefaultImplementation implements WithDefault {
    static {
        System.out.println("DefaultImplementation initialized");
    }
}
```

Khi `new DefaultImplementation()` là lần sử dụng chủ động đầu tiên và các kiểu chưa initialized, thứ tự bắt buộc sẽ bao gồm:

1. Khởi tạo superclass của `DefaultImplementation` nếu cần.
2. Khởi tạo superinterface **`WithDefault`** vì nó khai báo default method.
3. Chạy initializer riêng của `DefaultImplementation`.
4. Tạo/khởi tạo instance.

Vì vậy `WithDefault initialized` xuất hiện trước `DefaultImplementation initialized`. JVM không phải chờ gọi `run()` mới initialize `WithDefault`.

### 4.3. Interface extends interface có default method

```java
interface Parent {
    int VALUE = trace();

    static int trace() {
        System.out.println("Parent initialized");
        return 1;
    }

    default void ping() { }
}

interface Child extends Parent {
    int CHILD_VALUE = childTrace();

    static int childTrace() {
        System.out.println("Child initialized");
        return 2;
    }
}
```

Với đoạn trên:

- **Đọc `Child.CHILD_VALUE`** buộc initialize `Child` (field được khai báo ở Child). Việc initialize `Child` **không tự động initialize `Parent`**, dù Parent khai báo default method.
- **Đọc `Child.VALUE`** về mặt cú pháp dùng tên Child nhưng field `VALUE` thực sự được **Parent khai báo**. Truy cập này buộc initialize **Parent**, không có lý do tự động initialize Child.
- **Initialize một concrete class `C implements Child`**: JVM xem các superinterface trong cây kế thừa của C. Vì **Parent khai báo default method**, Parent phải initialized (nếu chưa) trước khi C initialized. `Child` *không tự động* initialized do implements nếu nó không khai báo default method riêng và không có trigger khác.

Điểm dễ lẫn: **initialize interface Child** khác với **initialize một class triển khai Child**. Trường hợp thứ hai xét các superinterface có default method; trường hợp thứ nhất không tự lan việc initialization lên toàn bộ interface cha.

## 5. Cây kế thừa sâu: interface nào sẽ chạy initializer?

Giả sử quan hệ:

```text
interface Root              declares default method
    |
    v
interface Mid               only abstract / static methods
    |
    v
interface Leaf              only constants / abstract methods
    ^
    |
class Concrete              implements Leaf
```

Khi `Concrete` được initialized, **`Root`** thuộc nhóm superinterface có khai báo default method. Nếu `Mid` và `Leaf` không khai báo default method và không có trigger khác, chúng **không bắt buộc** initialized chỉ vì `Concrete implements Leaf`.

Như vậy “chỉ interface được implements trực tiếp mới đáng quan tâm” cũng sai: điều kiện được xét trong **cây superinterface**, gồm cả tổ tiên gián tiếp có default method.

### Thứ tự quan sát khi có nhiều nhánh

JVM có thuật toán khởi tạo liên quan superclass và các superinterface chứa default methods; nó bảo đảm những loại cần thiết được initialized trước khi chính class hoàn tất initialization. Quy tắc chi tiết về duyệt cây và trạng thái đã initialized nằm ở **JVM Specification §5.5**.

Vì thế không nên tự ấn định thứ tự log cho **nhiều nhánh độc lập** chỉ từ sơ đồ không phản ánh đầy đủ thứ tự khai báo và thuật toán JVM. Điều chắc chắn của một tình huống đơn giản là:

```text
new Concrete()
    |
    +--> initialize superclass nếu chưa initialized
    |
    +--> initialize các superinterface có default method
    |    theo quy tắc JVM, nếu chưa initialized
    |
    +--> initialize Concrete
    |
    +--> gọi constructor Concrete
```

**Không phải** tất cả interface được nạp đều phải initialized, và cũng không có chuyện initializer của cùng một định nghĩa interface chạy lặp lại mỗi lần tạo object.

## 6. Thí nghiệm Java 17+: quan sát cả ba trường hợp

Tạo file **`InterfaceInitializationDemo.java`** với toàn bộ chương trình sau. Ví dụ dùng nested interfaces và nested static classes để có thể chạy trong một file; phương thức `mark` in thông báo mỗi khi initializer có tính toán được thực thi.

```java
public class InterfaceInitializationDemo {
    static int mark(String name) {
        System.out.println("init " + name);
        return 1;
    }

    interface AbstractOnly {
        int VALUE = mark("AbstractOnly");
        void work();
    }

    interface Defaulted {
        int VALUE = mark("Defaulted");

        default void work() {
            System.out.println("Defaulted.work");
        }
    }

    interface Parent {
        int VALUE = mark("Parent");

        default void work() {
            System.out.println("Parent.work");
        }
    }

    interface Leaf extends Parent {
        int VALUE = mark("Leaf");
    }

    interface Config {
        int CONST = 10;
        int NON_CONST = mark("Config");

        static void ping() {
            System.out.println("Config.ping");
        }
    }

    static class AbstractImpl implements AbstractOnly {
        static {
            System.out.println("init AbstractImpl");
        }

        @Override
        public void work() { }
    }

    static class DefaultImpl implements Defaulted {
        static {
            System.out.println("init DefaultImpl");
        }
    }

    static class LeafImpl implements Leaf {
        static {
            System.out.println("init LeafImpl");
        }
    }

    public static void main(String[] args) {
        System.out.println("1) literal: " + Leaf.class.getSimpleName());
        System.out.println("2) Leaf.VALUE: " + Leaf.VALUE);
        System.out.println("3) constant: " + Config.CONST);

        System.out.println("4) construct AbstractImpl");
        new AbstractImpl();

        System.out.println("5) construct DefaultImpl");
        new DefaultImpl().work();

        System.out.println("6) construct LeafImpl");
        new LeafImpl().work();

        System.out.println("7) Config.NON_CONST: " + Config.NON_CONST);
        System.out.println("8) Config.ping");
        Config.ping();
    }
}
```

Dùng **JDK 17 hoặc mới hơn**:

```bash
javac InterfaceInitializationDemo.java
java InterfaceInitializationDemo
```

**Stdout dự kiến (trong chương trình này):**

```text
1) literal: Leaf
init Leaf
2) Leaf.VALUE: 1
3) constant: 10
4) construct AbstractImpl
init AbstractImpl
5) construct DefaultImpl
init Defaulted
init DefaultImpl
Defaulted.work
6) construct LeafImpl
init Parent
init LeafImpl
Parent.work
init Config
7) Config.NON_CONST: 1
8) Config.ping
Config.ping
```

### Phân tích chính xác từng mốc

**(1) `Leaf.class`:** JVM cung cấp `Class<Leaf>`. Việc lấy literal không tự yêu cầu initialize `Leaf` hoặc `Parent`; vì vậy chưa có dòng `init ...`.

**(2) `Leaf.VALUE`:** field này do **Leaf** khai báo; giá trị đến từ lời gọi `mark("Leaf")` nên nó không phải constant variable. Truy cập khiến **Leaf initialized** và in `init Leaf`. Mặc dù Leaf extends Parent và Parent có default method, **Parent không tự initialized** khi Leaf initialized.

**(3) `Config.CONST`:** giá trị `10` là compile-time constant nên chỉ đọc nó không cần initialize Config. Không có dòng `init Config` ở đây.

**(4) `new AbstractImpl()`:** AbstractImpl triển khai AbstractOnly, nhưng AbstractOnly **không khai báo default method**. Initializer `AbstractImpl` chạy, còn `init AbstractOnly` không xuất hiện. JVM có thể đã nạp/liên kết AbstractOnly; điều này vẫn khác với initialization.

**(5) `new DefaultImpl().work()`:** trước khi khởi tạo DefaultImpl, JVM initialize **Defaulted** vì interface này khai báo default method. Thứ tự là `init Defaulted` rồi `init DefaultImpl`, sau đó mới gọi `Defaulted.work`. Nếu bỏ lời gọi `work()` và chỉ viết `new DefaultImpl()`, hai dòng initializer vẫn xuất hiện.

**(6) `new LeafImpl().work()`:** LeafImpl implements Leaf; Leaf kế thừa default method từ Parent. **Parent** thực sự khai báo default method nên Parent được initialized trước LeafImpl, dù Leaf đã initialized từ bước (2) và bản thân Leaf không khai báo default method. Phần thân `Parent.work` chạy *sau* khi object đã được tạo.

**(7) `Config.NON_CONST`:** lần truy cập field không phải compile-time constant mới kích hoạt `Config`, in `init Config` trước khi giá trị `1` được in.

**(8) `Config.ping()`:** static method của interface là trigger initialization; trong chương trình này Config **đã initialized ở bước (7)** nên chỉ còn lời gọi phương thức, không chạy lại `mark("Config")`.

### Biến thể đáng thử (không nằm trong stdout bên trên)

- Đưa `new DefaultImpl()` lên trước thao tác `Leaf.VALUE`: sẽ thấy `Defaulted` initialized trước khi bạn cần đọc field của Leaf.
- Bỏ toàn bộ thao tác `Leaf.VALUE` nhưng giữ `new LeafImpl()`: Parent vẫn initialized vì default method; **Leaf không buộc initialized** chỉ vì nó nằm giữa Parent và LeafImpl.
- Đổi `Defaulted.work()` từ `default` thành phương thức trừu tượng và bổ sung override `work()` trong DefaultImpl: khi initialize DefaultImpl, không còn yêu cầu initialize Defaulted chỉ từ quan hệ implements, nếu Defaulted không khai báo default method nào khác.
- Thêm override `work()` trong DefaultImpl mà **vẫn giữ default method khai báo ở Defaulted**: JVM vẫn phải initialize Defaulted khi initialize DefaultImpl.
- Thay `Config.CONST` bằng `Config.NON_CONST` ở bước (3): `Config` initialized sớm hơn vì field không còn là compile-time constant.

Các biến thể trên nhằm kiểm chứng **trigger**; không nên so sánh thứ tự tải lớp chính xác chỉ bằng output của initializer.

## 7. Default method có làm interface được initialized ngay khi load không?

**Không.** Một interface có default method vẫn có thể được JVM **load/link** mà chưa initialized:

```java
Class<?> type = Defaulted.class;
Class<?> checked = Class.forName(
        type.getName(), false, type.getClassLoader());
```

Đây là **đoạn minh họa trong cùng phạm vi nhìn thấy `Defaulted`**. `Class.forName(name, false, loader)` tìm/nạp và liên kết kiểu nhưng không yêu cầu initialized. Vì thế **định nghĩa default method không tự tạo trigger ngay tại thời điểm loading**.

Trigger ở đây là **initialization của concrete class triển khai**. Tại mốc đó, JVM xem quan hệ với các superinterface có khai báo default method và initialized chúng theo quy tắc.

Cũng không nên đánh đồng:
- **Được quyền gọi default method**: yêu cầu method resolution/dispatch trên một instance hợp lệ.
- **Khởi tạo interface chứa default method**: hệ quả bắt buộc khi class triển khai được initialized, kể cả chưa gọi method.
- **Khởi tạo một interface trực tiếp bằng static field/method**: trigger riêng, không phụ thuộc có instance hay default method.

## 8. Khi class override default method thì sao?

Xét class:

```java
interface Auditor {
    int READY = Hooks.touch();

    default String audit() {
        return "default";
    }
}

class Record implements Auditor {
    @Override
    public String audit() {
        return "override";
    }
}

class Hooks {
    static int touch() {
        System.out.println("Auditor initialized");
        return 1;
    }
}
```

Đây là **cụm khai báo minh họa**, chưa có `main`. Khi class `Record` được initialized, `Auditor` vẫn là superinterface **khai báo default method**, nên `Auditor` cần initialized ngay cả khi mọi instance của `Record` gọi bản override. Đây là quy tắc khởi tạo theo **khai báo phương thức**, không phụ thuộc thực tế dispatch sẽ chạy thân nào.

Có thể dùng `javap -c -p Auditor` và `javap -c -p Record` để quan sát bytecode, nhưng output `javap` phụ thuộc compiler và phiên bản JDK; **đừng** lấy một listing cụ thể thay cho quy tắc JLS/JVMS.

## 9. Thứ tự khởi tạo, vòng phụ thuộc và lỗi

### 9.1. Thứ tự khởi tạo trong interface

Interface không có `static { ... }`, nhưng những biểu thức khởi tạo trường không phải constant variable có thể gọi method. Các initializer trong interface được xử lý theo **thứ tự mã nguồn** trong giai đoạn initialization.

```java
interface Ordered {
    int A = log("A");
    int B = log("B");

    static int log(String name) {
        System.out.println(name);
        return 1;
    }
}
```

Nếu chương trình đọc `Ordered.A` khi Ordered chưa initialized, thứ tự output khởi tạo là `A` rồi `B`. Đọc tiếp `Ordered.B` không lặp lại output. Trong interface, các field là `final` nhưng vẫn có thể có biểu thức khởi tạo runtime.

### 9.2. Khởi tạo nhiều interface có default method

Nếu một class extends superclass và implements nhiều superinterface có default methods, các kiểu cần initialized được xác định theo quy tắc JLS/JVMS; nhiều interface có thể được initialized trước class, không thể mặc định chỉ interface được liệt kê đầu tiên sẽ chạy.

Đối với cây kế thừa phức tạp và diamond inheritance, cần áp dụng thuật toán khởi tạo của **JVMS `5.5** để dự đoán thứ tự giữa các interface cụ thể. Không tự suy luận rằng default method nào được chọn khi gọi sẽ là **interface duy nhất** cần initialized.

### 9.3. Nếu interface initializer thất bại

Nếu initializer của interface ném exception khi nó đang được initialized, việc khởi tạo có thể thất bại, ảnh hưởng đến class triển khai đang chờ nó. Lần sử dụng đầu có thể thấy `ExceptionInInitializerError` (khi ngoại lệ thường bị bọc), và những lần dùng về sau với **cùng định nghĩa kiểu** có thể thấy `NoClassDefFoundError: Could not initialize class ...`.

**Thực hành:** tránh đặt side effects khó kiểm soát, kết nối mạng, truy vấn database hoặc vòng phụ thuộc phức tạp trong field initializer của interface; việc tạo object triển khai có thể kích hoạt initializer ấy **sớm hơn dự kiến** nếu interface có default method.

### 9.4. Đa luồng

JVM đồng bộ hóa initialization cho mỗi định nghĩa class/interface. Hai luồng cùng lúc tạo instance của class triển khai không làm initializer của interface chạy thành hai lần thành công; một luồng có thể phải chờ quá trình khởi tạo do luồng khác thực hiện. Logic blocking trong initializer hoặc vòng phụ thuộc giữa các kiểu vẫn có thể tạo deadlock hoặc tình huống khó phân tích.

## 10. Các nhầm lẫn cần sửa

1. **“Interface không có constructor nên không bao giờ initialized.”** Sai. Interface initialized khi có trigger như đọc trường không phải constant variable, gọi static method hoặc class triển khai có điều kiện default method.
2. **“Tất cả interface của một class đều initialized khi `new`.”** Sai. Chỉ các superinterface khai báo default methods là nhóm có yêu cầu từ quy tắc class initialization; những interface khác cần trigger riêng.
3. **“Chỉ gọi default method mới initialized interface.”** Sai. Interface chứa default method thường đã initialized trước khi class triển khai hoàn tất initialization.
4. **“Class override default method nên khỏi initialized interface đó.”** Sai. Yếu tố quyết định là interface **khai báo default method**, không phải method nào được dispatch.
5. **“`Child extends Parent` nên initialize Child thì Parent chắc chắn initialized.”** Sai đối với interface: khởi tạo interface không tự kích hoạt initialization của superinterface.
6. **“Class implements Child, chỉ xét default method khai báo trực tiếp ở Child.”** Sai. Cần xét cả superinterface **gián tiếp** như Parent.
7. **“Mọi `static final` field đều không trigger initialization.”** Sai. Biểu thức khởi tạo runtime làm trường đó không phải *constant variable*.
8. **“`T.class` và `Class.forName(name)` tương đương.”** Sai. Class literal không tự initialize T; overload `Class.forName(String)` yêu cầu initialized kiểu được tìm.
9. **“Load interface có default method là lập tức chạy initializer.”** Sai. Loading/linking khác initialization.
10. **“Default method tồn tại là đủ để tạo instance interface.”** Sai. Interface không thể trực tiếp `new`; đối tượng vẫn có kiểu runtime là một class cụ thể.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Interface `I` khai báo `default void save() { }`. Class `C implements I` và override `save()`. Khi `new C()` lần đầu, `I` có cần initialized không?

**Đáp án:** Có, nếu chưa initialized. `I` là superinterface của class đang initialized và **khai báo default method**. Việc override không loại bỏ yêu cầu này.

**Câu 2.** Interface `I` chỉ khai báo `void save();` và `int X = trace();`. Class `C implements I`. `new C()` có tự bắt buộc chạy `trace()` của `I` không?

**Đáp án:** Không chỉ vì implements. `I` không khai báo default method. Nhưng nếu mã đọc `I.X`, nó sẽ initialized và chạy `trace()`.

**Câu 3.** `Parent` có default method, `Child extends Parent` nhưng không khai báo default method riêng. Đọc field runtime `Child.X` có tự initialize Parent không?

**Đáp án:** Không. Khởi tạo Child không tự lan lên superinterface Parent. Trái lại, khi một class triển khai Child được initialized, Parent cần initialized do default method mà Parent khai báo.

**Câu 4.** Tại sao đọc `I.X` với `int X = 123;` khác `int X = calculate();`?

**Đáp án:** `123` là constant expression, nên `X` là compile-time constant. Lời gọi `calculate()` không phải constant expression; vì vậy đọc `I.X` ở trường hợp hai là trigger initialization.

**Câu 5.** Một interface đã initialized và class triển khai nó tạo 100 object. Field initializer của interface chạy bao nhiêu lần?

**Đáp án:** Không chạy lại trong 100 lần tạo mới. Với cùng một định nghĩa kiểu runtime đã initialized thành công, phần khởi tạo interface được thực thi một lần.

## 12. Tư duy kiểm tra nhanh

```text
Quan sát interface I có được initialized hay không
                       |
          +------------+-------------+
          |                          |
          v                          v
Đang dùng chính I?       Đang initialize class C?
          |                          |
   +------+------+                  v
   |             |       I có phải superinterface
static method  non-constant  (trực tiếp/gián tiếp)
của I         static field   và KHAI BÁO default method?
   |             |                 /         \
   +------+------+               có          không
          |                        |             |
   trigger initialize I    initialize I       không chỉ
   (nếu chưa)              (nếu chưa)         vì implements

Đọc compile-time constant hoặc I.class không tự initialize I.
Khởi tạo một interface không tự initialize interface cha.
```

Khi phân tích thực tế, hãy hỏi **(1) đang initialize class nào, (2) interface nào trong cây kế thừa *khai báo* default method, (3) có static field/method riêng nào đã kích hoạt initialization trước đó không?** Ba câu hỏi này giải thích được cả trường hợp interface được initialized trước khi dùng default method, lẫn trường hợp một interface trừu tượng hoàn toàn vẫn chưa chạy initializer sau khi class triển khai đã được tạo.

### Nguồn tham khảo chính thức

- [Java Language Specification, 12.4 và 12.4.1 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4.1)
- [Java Virtual Machine Specification, 5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5)
- [Java Language Specification, 9.4.3 — Interface Method Body (default methods)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.3)
