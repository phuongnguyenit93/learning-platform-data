# Thứ tự khởi tạo lớp cha, giao diện liên quan và thành viên `static` trong JVM

Khi lần đầu tạo một đối tượng của class con, JVM không thực thi ngay các câu lệnh `static` của class con. Nó phải đảm bảo những kiểu liên quan được khởi tạo theo đúng **quy tắc của Java Language Specification (JLS) và Java Virtual Machine Specification (JVMS)**. Thông thường, **superclass khởi tạo trước subclass**. Nhưng còn một chi tiết quan trọng dễ bị bỏ sót: khi khởi tạo một **class**, JVM cũng khởi tạo những **superinterface trực tiếp hoặc gián tiếp có khai báo default method** theo thứ tự đệ quy được quy định. Những interface không khai báo default method **không tự động bị khởi tạo chỉ vì class đó `implements` chúng**.

Trong mỗi class hoặc interface, các initializer của thành viên `static` và các static initialization blocks hợp lệ được thực thi **theo thứ tự xuất hiện trong source** khi đến lượt kiểu đó. Ngoài ra, `static final` là **compile-time constant** có cơ chế `ConstantValue` riêng và việc đọc constant trong source thường **không kích hoạt khởi tạo** của class/interface khai báo.

Các quy tắc này giải thích thứ tự log gây ngạc nhiên trong hệ thống plugin, singleton, cache tĩnh, inheritance và code có default methods. Bài học xây dựng mô hình chính xác rồi dùng các chương trình **Java 17+ độc lập, runnable, stdout xác định** để kiểm tra.

## 1. Loading, linking, preparation và initialization không phải một

JVM quản lý vòng đời class và interface theo những khái niệm khác nhau:

| Hoạt động | Mục đích | Có chạy các câu lệnh `static { ... }` của class không? |
| --- | --- | --- |
| **Loading** | Tìm hoặc tạo biểu diễn của class/interface qua class loader | **Không** chỉ vì loading |
| **Verification** | Kiểm tra cấu trúc và các ràng buộc bytecode/type | **Không** chỉ vì verification |
| **Preparation** | Chuẩn bị static fields và giá trị mặc định theo quy tắc JVM | **Không** chạy initializer biểu thức người viết |
| **Resolution** | Liên kết các symbolic references đến class/field/method thật | **Không nhất thiết** kích hoạt initializer của kiểu liên quan |
| **Initialization** | Thực hiện thủ tục khởi tạo, đặt constant values thích hợp và chạy `<clinit>` nếu có | **Có**, ở đúng thời điểm theo thủ tục |

Mô hình:

```text
class bytes
    │
    ▼
Loading
    │
    ▼
Linking
    ├─ Verification
    ├─ Preparation: static fields có default values
    └─ Resolution (có thể xảy ra theo nhu cầu)
    │
    ▼
Initialization
    ├─ xử lý ConstantValue theo quy tắc
    ├─ nếu là class: khởi tạo superclass rồi những superinterface phù hợp
    ├─ chạy mã <clinit> của chính class/interface nếu có
    └─ ghi nhận trạng thái fully initialized
    │
    ▼
Tiếp tục thao tác đã yêu cầu khởi tạo
```

**Đừng đồng nhất “đã được nạp” với “đã chạy static initializer”.** Một class có thể được load, verify, prepare hoặc resolve một số references mà chưa thực hiện initialization.

### 1.1. Các giá trị mặc định xuất hiện trước code initializer

Khi preparation, một static field kiểu `int` có giá trị mặc định `0`, `boolean` là `false`, reference là `null`. Sau đó khi khởi tạo kiểu, những initializer biểu thức mới đặt các giá trị do lập trình viên tính toán.

```java
static int count = 7;
static Object cache = new Object();
```

Không nên suy rằng `count` đã là 7 và `cache` đã trỏ tới object mới ngay khi class vừa được load. Việc chạy biểu thức `new Object()` là hành vi của initialization, không phải một bước mặc định trong preparation.

**Ngoại lệ cần nhớ:** trường `static final` là compile-time constant có thể có `ConstantValue` attribute. JVMS xử lý giá trị constant theo bước riêng trong thủ tục khởi tạo, **trước bước khởi tạo superclass**. Điều này không có nghĩa mọi `static final` đều được gán theo cách ấy: `static final Integer BOXED = 42;` chẳng hạn không phải constant variable theo JLS.

## 2. Khi nào một class hoặc interface thật sự khởi tạo?

JLS `12.4.1 mô tả các tình huống kích hoạt initialization. Những trường hợp thường gặp:

1. **Tạo instance của class `C`**: `new C()` cần khởi tạo `C` trước khi tạo instance theo điều kiện tương ứng.
2. **Gọi static method được khai báo bởi `C`**: `C.work()` dẫn đến initialization của kiểu **khai báo method được resolve**, nếu chưa khởi tạo.
3. **Gán static field**: `C.value = 1` kích hoạt initialization của kiểu khai báo field tương ứng.
4. **Đọc static field không phải constant variable**: `System.out.println(C.value)` kích hoạt initialization của kiểu khai báo field.
5. **Một số thao tác reflection và method handles** có thể yêu cầu initialization, theo API/loại tham chiếu cụ thể.
6. **Class khởi đầu chương trình** được khởi tạo trước khi chạy `main` tương ứng.

Ở mức JVM, các instruction thường liên quan là `new`, `getstatic`, `putstatic` và `invokestatic`. Nhưng để biết chính xác **kiểu nào** phải initialize, cần xem **declaring class/interface của field hoặc method sau resolution**, không chỉ đọc tên viết ở source.

### 2.1. Những thao tác KHÔNG đủ để kết luận đã khởi tạo

| Thao tác | Tự nó có bắt buộc khởi tạo class được nhắc tới? |
| --- | --- |
| `C.class` | **Không**, class literal không phải active use buộc chạy `<clinit>` |
| `new C[5]` | **Không** buộc initialize component class `C` chỉ vì tạo array |
| Khai báo `C variable;` hoặc method signature dùng `C` | **Không** chỉ vì đề cập kiểu |
| `C.CONSTANT` với constant variable theo JLS | **Không**; compiler có thể inline constant |
| `Class.forName("pkg.C", false, loader)` | **Không yêu cầu** initialize `C` |
| `Class.forName("pkg.C")` | **Có**, overload phổ biến này yêu cầu initialization (với loader theo quy tắc API) |
| `loader.loadClass("pkg.C")` | Không nên coi đây là thao tác bắt buộc thực thi initializer |
| `obj instanceof C` | Không tự buộc initialization của `C` chỉ do phép kiểm tra này |

**Lưu ý:** class có thể đã được initialized trước đó bởi thao tác khác, hoặc việc resolution/loading có thể xảy ra sớm. Bảng nói rằng một thao tác **không tự nó đòi khởi tạo**, không hứa class tuyệt đối vẫn chưa được khởi tạo trong toàn tiến trình.

### 2.2. Inherited static field: tên class con không quyết định kiểu khởi tạo

```java
class Parent {
    static int size = 5;
}
class Child extends Parent {}
```

Với `Child.size`, field thực sự **được khai báo bởi Parent**. Theo quy tắc truy cập static field, đọc `Child.size` kích hoạt initialization của **Parent**, **không tự bắt Child khởi tạo** chỉ vì source viết tiền tố `Child`. Kết quả này trái với trực giác “chạm Child thì chạy static của Child”.

Điều tương tự áp dụng cho static field thừa kế từ interface/superinterface: cần quan sát nơi **khai báo field** sau resolution.

## 3. Quy tắc superclass trước subclass

Đối với một class `Sub extends Base`, khi JVM phải initialize `Sub`, nó bảo đảm `Base` đã được initialized trước khi chạy các initializer biểu thức và static blocks của `Sub`. Nếu `Base` còn có superclass chưa initialized, chuỗi tiếp tục lên trên.

Ví dụ đơn giản:

```java
class Grandparent {
    static { System.out.println("Grandparent"); }
}
class Parent extends Grandparent {
    static { System.out.println("Parent"); }
}
class Child extends Parent {
    static { System.out.println("Child"); }
}
```

Nếu trong một chương trình độc lập các class này chưa khởi tạo mà lần đầu thực hiện `new Child()`, thứ tự log dự kiến:

```text
Grandparent
Parent
Child
```

Đây là **ví dụ rút gọn về quan hệ khởi tạo**, không phải chương trình có method `main`. Constructor và instance field initialization là bước khác xảy ra **sau khi class initialization liên quan được hoàn tất**.

### 3.1. Không phải “đợi tới khi gọi constructor của Base mới chạy static”

Java object creation có liên quan constructor chaining `super(...)`, nhưng **static initialization** và **instance initialization** là hai quá trình khác nhau.

```text
new Child()
  ├─ class initialization (nếu cần)
  │    ├─ Grandparent <clinit>
  │    ├─ Parent <clinit>
  │    └─ Child <clinit>
  └─ tạo/khởi tạo instance
       ├─ chạy constructor chain và instance field initializers theo JLS
       └─ trả reference tới instance hoàn tất
```

Không nhầm `<clinit>` (class/interface initialization) với `<init>` (instance constructor). Một class có thể khởi tạo thành công đúng một lần theo định danh class và class loader nhưng tạo **nhiều object instances** bằng constructor.

### 3.2. Parent đã initialized thì không in lại

Nếu một thao tác trước đó đã khởi tạo `Parent`, rồi mới `new Child()`, JVM **không chạy lại** static code `Parent` chỉ vì class con đang được initialized. “Super trước sub” là **thứ tự đảm bảo trạng thái**, không bắt buộc mọi trigger đều in cùng toàn bộ chuỗi log mới.

## 4. Giao diện (`interface`): không thể áp dụng máy móc quy tắc class inheritance

Java hỗ trợ interface inheritance và default methods. Điều kiện khởi tạo interface có **hai trường hợp khác nhau**.

### 4.1. Khởi tạo riêng một interface không tự khởi tạo các superinterface của nó

Ví dụ:

```java
interface Root {
    int X = Helper.computeRoot();
}
interface Child extends Root {
    int Y = Helper.computeChild();
}
```

Nếu code truy cập **`Child.Y`** (non-constant expression) và chưa có loại nào được khởi tạo, điều này yêu cầu initialize **Child interface**. Nó **không tự động initialize Root** chỉ vì `Child extends Root`.

Ngược lại, `Root.X` sẽ yêu cầu initialize `Root` vì `Root` khai báo field `X`. Đây là khác biệt quan trọng so với quy tắc bắt buộc khởi tạo superclass khi initialize một **class**.

Hai dòng trên là **mã minh họa cần cung cấp `Helper`**, không phải một file độc lập. Ví dụ runnable minh họa interface rules nằm ở mục 6.

### 4.2. Nhưng khi initialize một CLASS: default-method superinterfaces có vai trò đặc biệt

Trong Java 17, khi class `C` đang initialize, JVMS `5.5 / JLS `12.4.2 yêu cầu xử lý:

1. Superclass của `C` (nếu có) trước.
2. Những superinterfaces trực tiếp hoặc gián tiếp **khai báo ít nhất một default method** — chính xác hơn ở mức JVMS là các superinterface khai báo phương thức instance **không abstract, không static** theo điều kiện của đặc tả.
3. Sau đó mới chạy mã initialization của bản thân `C`.

Các superinterfaces được xác định theo cách **duyệt đệ quy có thứ tự**: duyệt từng interface trong danh sách `implements` từ trái sang phải, truy sâu các superinterfaces của interface ấy theo thứ tự khai báo **trước khi** quay lại interface hiện tại. Trong các interface tìm được, chỉ những interface đáp ứng điều kiện default-method ở trên mới phải initialize vì quy tắc này.

```text
class Leaf extends Parent implements ChildInterface, Marker
  │
  ├─ initialize Parent trước
  │
  ├─ duyệt hierarchy interfaces của Leaf
  │    ├─ ChildInterface
  │    │     └─ RootInterface  [có default method] → init RootInterface
  │    │  ChildInterface      [có default method] → init ChildInterface
  │    └─ Marker              [không default method] → không auto-init
  │
  └─ initialize Leaf
```

**Chú ý từ ngữ:** một interface chỉ **thừa kế** default method từ parent nhưng **không tự khai báo** default method không nhất thiết được initialize do chính điều kiện “declares default methods”. Khi đọc code sâu, phải nhìn phương thức **được khai báo** trong từng interface, không chỉ xem nó có thừa hưởng phương thức nào.

### 4.3. Static methods trong interface không phải default methods

```java
interface Utilities {
    static void run() {}
}
```

Static method trong interface **không khiến interface đó trở thành default-method interface** cho quy tắc auto-initialization của một class implements nó. Phương thức `default void run() {...}` mới là trường hợp khác. Mặc dù lời gọi `Utilities.run()` tự nó có thể kích hoạt initialization của `Utilities`, việc một class chỉ `implements Utilities` không buộc interface đó phải init trước class.

### 4.4. Không thể khai báo `static { ... }` block trong interface

Java interface fields mặc nhiên là `public static final`, nhưng không được có static initializer block `static { ... }` giống class. Interface vẫn có thể làm công việc initialization nhờ **biểu thức initializer của một field non-constant**:

```java
interface Marker {
    int FLAG = Logger.log("Marker initialized");
}
```

Nếu field initializer gọi một method như trên, giá trị `FLAG` **không phải compile-time constant**. Lần đọc `Marker.FLAG` có thể kích hoạt initialization và chạy biểu thức, dù không có static block trong source interface.

## 5. Static fields và static blocks: thứ tự văn bản

Trong một class, các static variable initializers và static initializer blocks được xử lý **theo thứ tự xuất hiện trong code** khi class đó initialize. Đây là một chuỗi có side effects; đổi thứ tự khai báo có thể đổi stdout, dữ liệu hoặc gây lỗi.

```java
class Order {
    static int first = trace("first");
    static { trace("block 1"); }
    static int second = trace("second");
    static { trace("block 2"); }
    static int trace(String value) {
        System.out.println(value);
        return 1;
    }
}
```

Khi `Order` được initialization lần đầu, code tương ứng sẽ in:

```text
first
block 1
second
block 2
```

Đây là đoạn class minh họa. Không phải JVM sẽ chạy lần lượt mọi method trong class: method `trace` chỉ được gọi vì các initializer đã gọi nó.

### 5.1. Compiler đưa code vào `<clinit>`

`javac` thường tổng hợp các static field initializers có runtime operations và static blocks vào class initialization method tên **`<clinit>`**, descriptor **`()V`**.

```text
source:
  static int n = compute();
  static { log(); }

bytecode logic:
  <clinit>:
    invokestatic compute:()I
    putstatic n:I
    invokestatic log:()V
    return
```

`<clinit>` là phương thức JVM dành cho class/interface initialization, **không** được gọi trực tiếp bằng Java như `MyClass.<clinit>()` và không phải constructor `<init>`.

Không phải mọi class có static fields đều cần có `<clinit>` trong class file. Những class chỉ có compile-time constants hoặc không có code initialization có thể **không chứa `<clinit>`**. JVM vẫn duy trì trạng thái initialization của class/interface theo quy tắc.

### 5.2. Nguyên tắc “thứ tự trong từng lớp”, không gộp source cha/con

Nếu `Parent` khai báo:

```java
static int p = initP();
static { logP(); }
```

và `Child` khai báo:

```java
static int c = initC();
static { logC(); }
```

thì JVM thực thi thứ tự **theo từng kiểu**:

```text
Parent.initP → Parent.logP
Child.initC  → Child.logC
```

Nếu Child có default-method superinterfaces chưa initialized, các interface đó có thể **chen giữa hai nhóm** theo thủ tục của `5.5`; không được kết luận Parent static xong là Child static chạy ngay.

### 5.3. Constant variables được xử lý đặc biệt

Một **constant variable** theo JLS là `final` variable kiểu primitive hoặc `String` được khởi tạo bằng **constant expression**:

```java
static final int MAX = 10;
static final String NAME = "service";
```

Các reference trong source có thể được compiler **nhúng giá trị vào bytecode người dùng**, không dùng `getstatic` để đọc field khi đã được fold, nên **không khởi tạo kiểu khai báo** chỉ vì đọc constant.

Ngược lại:

```java
static final Integer BOXED = 10;
static final int LENGTH = new String("abc").length();
static final String TEXT = new String("ready");
```

Không phải constant variables theo định nghĩa trên: `Integer` là reference wrapper; lời gọi constructor/method là runtime expressions. Truy cập các static fields này theo cách thông thường có thể kích hoạt initialization của declaring type.

**Đừng đồng nhất từ khóa `final` với constant-foldable.** `static final` object và collection không tự trở thành compile-time constants.

## 6. Ví dụ chạy được: superclass, default-method interfaces, marker interface

Tạo file **`InitHierarchyDemo.java`** trên JDK 17 trở lên:

```java
public class InitHierarchyDemo {
    static int trace(String message) {
        System.out.println(message);
        return 1;
    }

    interface Root {
        int VALUE = trace("Root.field");
        default void rootMethod() {}
    }

    interface Branch extends Root {
        int VALUE = trace("Branch.field");
        default void branchMethod() {}
    }

    interface Marker {
        int VALUE = trace("Marker.field");
    }

    static class Parent {
        static int parentValue = trace("Parent.field");
        static { trace("Parent.block"); }
    }

    static class Leaf extends Parent implements Branch, Marker {
        static int leafValue = trace("Leaf.field");
        static { trace("Leaf.block"); }
    }

    public static void main(String[] args) {
        System.out.println("before new");
        new Leaf();
        System.out.println("after new");
        System.out.println("markerValue=" + Marker.VALUE);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 InitHierarchyDemo.java
java InitHierarchyDemo
```

**Stdout chính xác:**

```text
before new
Parent.field
Parent.block
Root.field
Branch.field
Leaf.field
Leaf.block
after new
Marker.field
markerValue=1
```

### 6.1. Lý giải từng dòng

1. Khi chương trình vào `main`, class ngoài `InitHierarchyDemo` đã được initialized. Nhưng các **nested types** `Parent`, `Leaf` và interfaces `Root`, `Branch`, `Marker` chưa bắt buộc phải initialize chỉ vì class ngoài có tên của chúng.
2. `System.out.println("before new")` in trước khi tạo object.
3. `new Leaf()` yêu cầu initialize `Leaf`. JVM kiểm tra superclass `Parent` trước: field initializer in `Parent.field`, rồi static block in `Parent.block`.
4. `Leaf` trực tiếp `implements Branch, Marker`. Việc duyệt interface `Branch` truy về `Root`: cả hai **tự khai báo default method**, nên init `Root` rồi `Branch`. Field initializer non-constant tương ứng in `Root.field` và `Branch.field`.
5. `Marker` không khai báo default method. Do đó **chưa** bắt buộc initialize trong bước xử lý default-method superinterfaces của `Leaf`.
6. Sau các kiểu cần trước, mã static của `Leaf` chạy theo thứ tự: field rồi block.
7. `after new` in sau khi thao tác tạo `Leaf` hoàn tất.
8. `Marker.VALUE` là field `int` với initializer qua lời gọi `trace(...)` nên **không phải constant variable**. Lệnh truy cập gây initialization của `Marker`, in `Marker.field` trước khi in `markerValue=1`.

**Nếu xóa `default void rootMethod() {}` khỏi `Root`:** ở một class-file mới được biên dịch, `Root` không còn thuộc nhóm tự khai báo default method, nên một `new Leaf()` đơn thuần không tự yêu cầu `Root` initialize vì nhánh này. Đây là cách tốt để tự kiểm nghiệm vì sao interface graph và quy tắc “có khai báo default method” quan trọng.

### 6.2. Từ đâu ra thứ tự Root rồi Branch?

Cơ chế duyệt interface hierarchy là **đệ quy trước khi quay lại interface trực tiếp**. `Leaf` duyệt `Branch`, rồi `Root` là superinterface của `Branch`; sau đó quay lại `Branch`, cuối cùng tới `Marker`.

Chỉ các interface phù hợp điều kiện được initialize. Vì vậy kết quả là `Root` rồi `Branch`. `Marker` dù nằm trong `implements` vẫn chưa initialized ở thời điểm `Leaf` chạy static block.

Nếu có nhiều superinterfaces hình kim cương, thuật toán bảo đảm không chạy lại initialization đã hoàn tất; cùng một interface có thể được gặp qua nhiều nhánh nhưng code `<clinit>` của nó không phải được thực thi lặp lại mỗi lần duyệt.

### 6.3. Vì sao static fields của Root/Branch được in?

Trong interface Java, `int VALUE = trace("...")` tương đương field `public static final int VALUE` nhưng expression **không phải compile-time constant**. Trong quá trình initialization của interface do default methods, biểu thức `trace` được gọi và tạo side effect. Nếu thay bằng `int VALUE = 1`, việc lấy constant value không gọi `trace` và không có dòng log.

## 7. Ví dụ chạy được: thứ tự static field và giá trị mặc định

Khi một static initializer gọi method đọc một static field **chưa được gán bằng initializer văn bản**, method có thể quan sát giá trị mặc định từ preparation. Đây là nguyên nhân phổ biến của output khó đoán.

Tạo file **`StaticSequenceDemo.java`**:

```java
public class StaticSequenceDemo {
    static int first = readSecond();
    static int second = 7;

    static {
        System.out.println("static block second=" + second);
    }

    static int readSecond() {
        System.out.println("observed second=" + second);
        return second + 1;
    }

    public static void main(String[] args) {
        System.out.println("first=" + first);
        System.out.println("second=" + second);
    }
}
```

Chạy:

```bash
javac --release 17 StaticSequenceDemo.java
java StaticSequenceDemo
```

**Stdout:**

```text
observed second=0
static block second=7
first=1
second=7
```

Diễn tiến:

1. Khi `StaticSequenceDemo` initialize, `first` và `second` đã có giá trị mặc định **0** theo preparation.
2. Initializer của `first` gọi `readSecond()`. Lúc này `second = 7` **chưa chạy**, nên method in `observed second=0` và trả `1`. JVM gán `first=1`.
3. Tiếp theo biểu thức initializer `second=7` chạy.
4. Static block in `static block second=7`.
5. Khi class initialize xong, launcher mới gọi `main`, in `first=1` và `second=7`.

### 7.1. Sao không viết thẳng `static int first = second;`?

Với quy tắc **illegal forward reference** của Java source trong những ngữ cảnh nhất định, code:

```java
static int first = second;
static int second = 7;
```

có thể **bị `javac` từ chối** vì tham chiếu bằng tên đơn giản tới field static khai báo phía sau trong initializer. Ví dụ runnable đã gọi **method `readSecond()`**, và body method đọc field — trường hợp có quy tắc khác, nên nó có thể quan sát giá trị preparation **0**.

**Không biến ví dụ `first = second;` thành chương trình chạy với expected stdout**, vì nó nhằm minh họa compile error, không phải hành vi runtime.

### 7.2. Không có cơ chế “sắp xếp lại theo dependency”

JVM không đọc source và tự topologically sort static initializers. Nếu field A phụ thuộc B ở bên dưới, người viết cần tổ chức dependency/initialization rõ ràng. Java vẫn bảo toàn thứ tự thực thi phù hợp với source trong class body; JVM không đoán ý định nghiệp vụ và chạy `second=7` trước `first=readSecond()`.

## 8. Ví dụ chạy được: compile-time constant, inherited field và non-constant static

Tạo file **`StaticTriggerDemo.java`**:

```java
public class StaticTriggerDemo {

    static int report(String message, int result) {
        System.out.println(message);
        return result;
    }

    static class Settings {
        static final int LIMIT = 42;
        static final String LABEL = "stable";
        static final Integer BOXED = 42;

        static {
            System.out.println("Settings initialized");
        }
    }

    static class Parent {
        static int inherited = report("Parent initialized", 7);
    }

    static class Child extends Parent {
        static int own = report("Child initialized", 9);
    }

    public static void main(String[] args) {
        System.out.println("limit=" + Settings.LIMIT);
        System.out.println("label=" + Settings.LABEL);
        System.out.println("inherited=" + Child.inherited);
        System.out.println("boxed=" + Settings.BOXED);
        System.out.println("own=" + Child.own);
    }
}
```

Lệnh:

```bash
javac --release 17 StaticTriggerDemo.java
java StaticTriggerDemo
```

**Stdout chính xác:**

```text
limit=42
label=stable
Parent initialized
inherited=7
Settings initialized
boxed=42
Child initialized
own=9
```

Giải thích:

- `Settings.LIMIT` và `Settings.LABEL` là compile-time constants. Compiler Java có thể ghi hằng `42` và `"stable"` trực tiếp ở nơi sử dụng. Hai truy cập đầu không buộc initialize `Settings`, nên chưa thấy `Settings initialized`.
- `Child.inherited` truy cập field **khai báo trong `Parent`**. Kết quả yêu cầu initialize `Parent`, in `Parent initialized`; **Child chưa phải initialize** chỉ do truy cập field này.
- `Settings.BOXED` có kiểu `Integer`, không phải constant variable. Đọc nó bằng `getstatic` làm `Settings` initialize, chạy static block in `Settings initialized`, sau đó in giá trị `42`.
- `Child.own` thuộc field **do Child khai báo**. Khi cần init Child, Parent đã initialized nên không in lại Parent; chỉ in `Child initialized`.

### 8.1. Điều gì xảy ra nếu thay `Child.inherited` bằng `Child.own` ở dòng đầu?

Nếu dòng truy cập đầu vào class hierarchy là `Child.own`, JVM phải initialize Child và do đó đảm bảo Parent initialized trước. Khi ấy Parent và Child in liền nhau theo thứ tự. Nhưng ví dụ ban đầu cố ý tách hai trigger để chứng minh **kiểu khai báo field** mới quyết định việc initialization qua static field access.

### 8.2. “Compile-time constant” được quyết định lúc compile

Nếu thư viện thay `Settings.LIMIT` từ 42 thành 43 và chỉ build lại JAR chứa `Settings` nhưng **không biên dịch lại code client**, client cũ có thể vẫn dùng giá trị hằng **42 đã inline**. Đây là hệ quả về **binary compatibility**: thay constant variable không giống đổi non-constant static field.

Khi thiết kế library API, đừng dùng `public static final int` làm “giá trị cấu hình động” mà mong mọi client tự cập nhật sau khi thay JAR. Với giá trị runtime/configuration, nên đưa qua method hoặc cơ chế truy cập phù hợp.

## 9. Thứ tự khởi tạo static và khởi tạo instance

Một class có thể chứa:

- Static field initializer: `static int x = compute();`.
- Static initialization block: `static { ... }`.
- Instance field initializer: `int y = computeInstance();`.
- Instance initializer block: `{ ... }`.
- Constructor: `MyClass() { ... }`.

Hai nhóm này **khác nhau về thời điểm**:

| Thành phần | Khi nào chạy theo mô hình Java? |
| --- | --- |
| Static field initializer có runtime code | Khi initialize **class**, một lần cho trạng thái thành công của class đó theo loader |
| Static block | Khi initialize **class**, theo thứ tự cùng các field initializers |
| Instance field initializer | Khi tạo **mỗi object**, theo trình tự instance initialization |
| Instance initializer block | Khi tạo **mỗi object**, theo trình tự instance initialization |
| Constructor body | Trong quá trình tạo **mỗi object**, sau các bước thích hợp của superclass/instance initialization |

Ví dụ khái niệm:

```text
new Child() lần đầu
  → initialize Parent/related interfaces/Child (nếu chưa)
  → instance initialization + constructor chain
new Child() lần hai
  → không cần chạy lại <clinit> của những kiểu đã thành công
  → vẫn chạy instance initialization + constructor chain cho object mới
```

Không được kết luận “static luôn chạy ngay trước constructor” ở **mọi lần** tạo object: nó chỉ cần thực thi trước lần active use đầu nếu kiểu chưa initialized.

## 10. Reentrant initialization và concurrency

JVM phải phối hợp nhiều thread cùng muốn initialize một class/interface. Quy tắc `5.5` dùng **initialization lock** để bảo đảm trạng thái của một class được xử lý nhất quán.

Các trạng thái ý tưởng:

```text
verified/prepared, not initialized
       │
       ├─ thread A bắt đầu initialize
       │      ├─ ghi nhận "initialization in progress by A"
       │      ├─ khởi tạo superclass/interfaces phù hợp
       │      └─ chạy <clinit>, hoàn tất thành công hoặc thất bại
       │
       └─ thread B cùng cần class
              → chờ initialization của A theo cơ chế JVM
              → tiếp tục khi class initialized hoặc nhận lỗi
```

- Nếu **cùng thread A** đang initialize class và trong quá trình ấy lại yêu cầu initialize **chính class đó**, JVM nhận diện recursive initialization và **không chạy lại `<clinit>`** từ đầu. Đây là lý do method `readSecond()` trong `StaticSequenceDemo` có thể được gọi khi class đang initializing.
- Nếu **thread B** cần class đó, B có thể phải đợi A hoàn thành.
- Nếu initialization của class **thất bại**, class có thể chuyển sang **erroneous state**; những lần thử tiếp theo không đơn giản chạy lại static block như chưa có chuyện gì.
- Synchronization của class initialization **không** thay thế việc đồng bộ thread-safe cho các static mutable fields **sau khi** initialization hoàn tất.

### 10.1. Đừng tạo vòng phụ thuộc init giữa hai classes/threads

Nếu static initializer của class A yêu cầu B còn static initializer của B lại yêu cầu A, đặc biệt khi **hai threads** đang initialize các class khác nhau, có thể gặp chờ vòng hoặc deadlock initialization. Các JVM phải giữ quy tắc đồng bộ; người thiết kế cần tránh side effects phức tạp, I/O blocking hoặc chạy worker tasks trong static initializer khi có dependency chưa rõ.

**Thực hành:** để static initialization càng đơn giản/deterministic càng tốt; đưa việc kết nối mạng, khởi động thread pool, đăng ký plugin và dependency injection phức tạp vào các bước startup được kiểm soát rõ ràng nếu có thể.

## 11. Khi static initialization ném exception

Class initialization có thể thất bại:

```java
class Broken {
    static final Object CONFIG = loadConfiguration();

    static Object loadConfiguration() {
        throw new IllegalStateException("bad config");
    }
}
```

Đoạn class này **minh họa**. Khi lần đầu active use của `Broken`:

1. JVM bắt đầu initialization.
2. `<clinit>` (nếu có) thực thi initializer biểu thức và gặp exception.
3. Nếu throwable làm initialization thất bại **không thuộc `Error`**, JVM áp dụng quy tắc bao bọc thích hợp trong **`ExceptionInInitializerError`** (trừ chi tiết khi không thể tạo wrapper).
4. Class có thể bị ghi nhận ở **erroneous state**.
5. Những lần active use về sau có thể thất bại bằng **`NoClassDefFoundError`** nêu rằng class không thể khởi tạo, thay vì chạy initializer lần nữa.

Nếu exception của initializer vốn là một `Error`, nó không nhất thiết bị bọc thành `ExceptionInInitializerError` theo cùng quy tắc. Vì thế đừng viết monitoring chỉ đếm `ExceptionInInitializerError` mà bỏ qua lỗi initialization loại khác.

### 11.1. Cách xử lý trong ứng dụng

- Đọc **cause/stack trace** đầu tiên để biết initializer nào đã lỗi.
- Xem cấu hình, dependency, file path, environment và code có side effects trong static blocks.
- Kiểm tra xem lớp có bị khởi tạo sớm bởi library, reflection hoặc framework không.
- Đừng “retry” bằng cách lặp `new Broken()` trong **cùng class loader** rồi kỳ vọng JVM tự chạy lại initialization.
- Nếu yêu cầu recovery động, thiết kế một service/configuration lifecycle có thể retry **ngoài** `<clinit>`, thay vì lệ thuộc class initialization.

## 12. `javap`: nhìn thấy `<clinit>` và constant folding

Dùng JDK 17:

```bash
# Compile cả ba ví dụ độc lập:
javac --release 17 InitHierarchyDemo.java
javac --release 17 StaticSequenceDemo.java
javac --release 17 StaticTriggerDemo.java

# Xem các lệnh, method/field descriptors:
javap -c -p StaticSequenceDemo
javap -c -p StaticTriggerDemo

# Xem nested classes, giữ dấu $ trong dấu nháy:
javap -c -p 'InitHierarchyDemo$Parent'
javap -c -p 'InitHierarchyDemo$Leaf'
javap -c -p 'InitHierarchyDemo$Root'
javap -c -p 'InitHierarchyDemo$Branch'
javap -c -p 'InitHierarchyDemo$Marker'

# Hiển thị ConstantValue và thông tin sâu:
javap -v -p 'StaticTriggerDemo$Settings'
```

Với `StaticSequenceDemo`, thường thấy:

```text
static {};
   invokestatic readSecond:()I
   putstatic first:I
   bipush 7
   putstatic second:I
   getstatic java/lang/System.out
   ...
   return
```

Đây là **trích đoạn logic của `<clinit>`**, không phải output chuẩn từng byte/offset; mã in chuỗi của `System.out.println` còn có instructions/constant-pool operands khác. Điều cần xác minh là lệnh gọi `readSecond()` **đứng trước** lệnh ghi `second=7`.

Với `Settings`, chú ý:

- `LIMIT` và `LABEL` có thể có **`ConstantValue` attributes**.
- `BOXED` cần gán giá trị bằng code runtime trong `<clinit>`.
- Static block in `Settings initialized` cũng nằm trong `<clinit>` sau bước gán `BOXED` ở ví dụ.
- Ở **client `StaticTriggerDemo`**, các lần dùng `LIMIT`/`LABEL` có thể chỉ đẩy literal hoặc constant lên stack, không có `getstatic Settings.LIMIT` bắt buộc.

### 12.1. `-Xlog:class+init` (HotSpot) dùng ra sao?

Trên **HotSpot JVM** có Unified Logging, có thể xem log class initialization theo cấu hình tương thích, ví dụ:

```bash
java -Xlog:class+init=info InitHierarchyDemo
```

Đây là **tùy chọn diagnostic đặc thù runtime**, không phải cú pháp Java/JVMS bắt buộc mọi implementation phải hỗ trợ. Log có thể nhiều dòng, gồm các JDK classes và thứ tự thông tin khác nhau giữa bản HotSpot; do đó **không đưa một stdout cố định cho diagnostic này**.

Để xác nhận hành vi trong học tập, hãy ưu tiên **stdout chủ động từ phương thức `trace()`** của ví dụ `InitHierarchyDemo`.

## 13. Những sai lầm phổ biến

1. **“`extends` chỉ ảnh hưởng method lookup, không ảnh hưởng thứ tự static init.”** Sai. Superclass phải initialize trước subclass.
2. **“Class implements interface nào cũng initialize interface đó trước.”** Sai. Với class initialization, quy tắc liên quan đặc biệt tới superinterfaces **khai báo default methods**; interface khác không tự init chỉ vì implements.
3. **“Khởi tạo một interface luôn khởi tạo interface cha.”** Sai. Initialization của interface không tự bắt buộc initialization superinterfaces.
4. **“Default method phải được gọi thì interface mới init.”** Sai khi class initialization yêu cầu initialize superinterface có khai báo default method, dù method ấy chưa được gọi.
5. **“Static methods của interface tương đương default methods.”** Sai. Static method không phải instance default method.
6. **“Static fields chạy theo tên chữ cái hoặc dependency.”** Sai. Runtime initializer expressions và static blocks của cùng kiểu chạy theo thứ tự code được biên dịch theo Java source.
7. **“`static final` nào cũng là constant và không trigger init.”** Sai. Chỉ **constant variable** theo JLS mới có tính chất compile-time constant; `Integer` hoặc biểu thức runtime khác.
8. **“Đọc `Child.parentField` chắc chắn init Child.”** Sai. Đọc field `static` kích hoạt loại **khai báo field**, thường là Parent.
9. **“`C.class` và `new C()` đều chạy static block.”** Sai. Class literal không tự kích hoạt initialization; tạo instance cần class initialization.
10. **“Preparation đặt `static int n = 7` thành 7 ngay.”** Sai với biểu thức initializer thông thường. Preparation đặt giá trị mặc định, runtime assignment xảy ra khi khởi tạo.
11. **“Không thể thấy giá trị 0 từ static field có initializer 7.”** Có thể thấy 0 nếu một initializer trước gọi method đọc field chưa được gán, như `StaticSequenceDemo`.
12. **“Constructor `<init>` và class initialization `<clinit>` là một.”** Sai; constructor là quy trình tạo từng object.
13. **“Mỗi lần tạo object thì class static block chạy lại.”** Sai nếu class đã initialized thành công.
14. **“`<clinit>` luôn tồn tại ở mọi class.”** Sai. Class chỉ chứa compile-time constants có thể không có code initialization method.
15. **“Một static initializer lỗi lần đầu sẽ retry vô hạn khi dùng lại class.”** Sai. Initialization failure dẫn tới trạng thái lỗi theo class loader.
16. **“Cùng tên class trên toàn JVM nghĩa là chỉ một init duy nhất.”** Không hoàn toàn: identity của class còn gắn với **defining class loader**; các loaders có thể định nghĩa các classes khác nhau cùng binary name.
17. **“Chỉ thay JAR chứa static final constant là client đã dùng giá trị mới.”** Không chắc, vì client có thể đã inline compile-time constant.

## 14. Tự kiểm tra (có đáp án)

**Câu 1.** `class C extends B` với `B` chưa initialized. Trước khi chạy static block của `C`, điều gì phải xảy ra?

**Đáp án:** `B` và superclass chain chưa initialized của `B` cần initialize theo đúng quy tắc; còn có thể có default-method superinterfaces liên quan trước khi chạy static body của `C`.

**Câu 2.** Interface `I` có field `int A = compute()` nhưng không khai báo default methods. `new C()` với `class C implements I` có bắt buộc chạy `I.A` initializer không?

**Đáp án:** **Không** chỉ vì `C implements I`. Khi active use đọc `I.A`, `I` có thể được initialize; `compute()` lúc ấy mới chạy.

**Câu 3.** `interface B extends A`. Chỉ truy cập non-constant static field khai báo bởi `B` thì `A` có nhất thiết initialize không?

**Đáp án:** **Không**. Initialize một interface không tự khởi tạo các superinterfaces. Nếu expression initializer của `B` tự gọi vào `A` thì đó là một trigger riêng.

**Câu 4.** `static final int N = 5` và `static final Integer M = 5` có giống nhau về trigger initialization không?

**Đáp án:** Không. `N` là constant variable (compile-time constant) nếu đúng các điều kiện của JLS; `M` là reference kiểu `Integer` không phải constant variable và đọc qua `getstatic` có thể trigger initialization.

**Câu 5.** Vì sao `StaticSequenceDemo` in `observed second=0` trước khi có `second=7`?

**Đáp án:** `second` đã có default value 0 sau preparation nhưng initializer biểu thức `second=7` nằm **sau** initializer của `first`. Method `readSecond()` đọc nó trước khi dòng gán 7 chạy.

**Câu 6.** Tại sao `InitHierarchyDemo` in `Root.field` và `Branch.field` trước `Leaf.field` nhưng không in `Marker.field` ngay?

**Đáp án:** `Root` và `Branch` khai báo default methods nên được initialize theo traversal phù hợp khi class `Leaf` initialize. `Marker` không khai báo default methods; nó chỉ init sau khi source truy cập non-constant `Marker.VALUE`.

**Câu 7.** `static int p` khai báo trong Parent nhưng được truy cập bằng `Child.p`. Kiểu nào phải initialize do truy cập đó?

**Đáp án:** Parent là kiểu **khai báo field**. Tham chiếu tên Child ở source không tự buộc initialize Child.

**Câu 8.** Nếu class initialization ném `IllegalStateException` không được xử lý, lỗi ngoài cùng lần đầu thường là gì? Lần sau thì sao?

**Đáp án:** Lần đầu thường là **`ExceptionInInitializerError`** bọc exception không phải Error; class chuyển sang erroneous state. Lần sau dùng lại cùng class/loader thường gặp **`NoClassDefFoundError`**, không chạy lại initialization body.

**Câu 9.** Thao tác `new SomeClass[2]` có tự yêu cầu initialize `SomeClass` không?

**Đáp án:** Không. Đây là tạo array chứa references; component class không tự phải initialize chỉ do allocation array.

**Câu 10.** Nếu class đã được initialized ở thread A, thread B gọi static method sau đó thì có chạy lại `<clinit>` không?

**Đáp án:** Không. B sử dụng trạng thái đã initialized của class theo đồng bộ JVM, không chạy lại static body.

## 15. Tổng kết

```text
Trigger yêu cầu initialize class C?
      │
      ▼
C đã initialized? ───── Có ───► tiếp tục dùng C
      │ Không
      ▼
xử lý initialization lock/trạng thái C
      │
      ▼
ConstantValue fields của C theo quy tắc JVMS
      │
      ▼
Nếu C là CLASS:
  superclass SC chưa initialized → initialize SC
  superinterfaces có khai báo default methods (thứ tự recursive) → initialize
      │
      ▼
chạy <clinit> của C nếu có
  - static field initializers (runtime)
  - static initializer blocks
  - thứ tự textual của C
      │
      ▼
đánh dấu initialized thành công
      │
      ▼
tiếp tục thao tác new/getstatic/putstatic/invokestatic...
```

**Điểm cốt lõi:** Thứ tự khởi tạo không phải “mọi thứ có chữ `static` chạy từ trên xuống trên toàn bộ cây thừa kế”. JVM thực hiện initialization **theo từng class/interface**, với **superclass trước subclass**, các **default-method superinterfaces** liên quan theo thứ tự đệ quy, rồi mới tới initializer code của class đó. Trong một kiểu, static runtime initializers chạy **theo thứ tự source**, còn constant variables có quy tắc riêng. Phân biệt **declaring type**, **compile-time constant** và **class vs interface initialization** là chìa khóa để dự đoán output và tránh initialization bugs.

### Tài liệu tham khảo chuẩn

- [JLS Java SE 17 — 12.4.1 When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1).
- [JLS Java SE 17 — 12.4.2 Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2).
- [JVMS Java SE 17 — 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5).
- [JVMS Java SE 17 — 5.4.2 Preparation](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.2).
- [JVMS Java SE 17 — 2.9.2 Class Initialization Methods](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.9.2).
- [JVMS Java SE 17 — 4.7.2 ConstantValue Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2).
- [JLS Java SE 17 — 8.3.2.1 Static Field Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2.1).
- [JLS Java SE 17 — 9.3.1 Interface Field Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.3.1).
- [JDK 17 `javap` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
