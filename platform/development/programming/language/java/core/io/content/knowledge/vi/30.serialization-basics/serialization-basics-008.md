# Constructor của lớp Serializable và lớp cha không Serializable

## 1. Câu hỏi cốt lõi

Khi gọi `new` để tạo một đối tượng Java, các constructor của những lớp trong chuỗi kế thừa được chạy theo quy tắc khởi tạo đối tượng thông thường. Nhưng khi dùng **Java Object Serialization** với `ObjectInputStream.readObject()` để khôi phục một đối tượng có lớp triển khai `java.io.Serializable`, quy tắc constructor **khác đáng kể**.

**Quy tắc phải nhớ:** Trong quá trình *deserialization* mặc định của một lớp `Serializable` thông thường, **constructor của chính lớp `Serializable` và của các lớp cha cũng `Serializable` không được gọi**. Thay vào đó, Java **gọi constructor không tham số, có thể truy cập được, của lớp cha gần nhất không triển khai `Serializable`**. Từ constructor đó, các constructor của những tổ tiên không `Serializable` tiếp tục được thực thi theo quy tắc `super()` bình thường.

Ví dụ:

```text
Object                 (không Serializable)
   |
   v
Base                   (không Serializable)  <-- no-arg constructor được gọi
   |
   v
Account                (implements Serializable) <-- constructor KHÔNG chạy
   |
   v
PremiumAccount         (kế thừa Serializable) <-- constructor KHÔNG chạy

new PremiumAccount()                -> Object -> Base -> Account -> PremiumAccount
ObjectInputStream.readObject()      -> Object -> Base
                                   -> phục hồi field của Account/PremiumAccount
```

Sơ đồ được giản lược để mô tả constructor của đối tượng đang được khôi phục; quá trình thật còn giải quyết descriptor, handles, references, chuỗi đối tượng và hook serialization.

Đặc biệt, **không được nói “deserialization không chạy constructor nào”**. Đúng hơn: nó **không chạy constructor của các lớp thuộc chuỗi kế thừa `Serializable`**, nhưng **vẫn chạy constructor không tham số của lớp cha không `Serializable` gần nhất** và constructor tổ tiên mà constructor đó gọi.

Đây là chủ đề quyết định việc field nào được khôi phục, field nào có giá trị khởi tạo mới và tại sao việc thiếu constructor phù hợp ở lớp cha có thể làm `readObject()` thất bại.

## 2. `Serializable` chỉ là marker interface

`java.io.Serializable` là **marker interface**: không khai báo phương thức bắt buộc phải hiện thực. Một class trực tiếp ghi `implements Serializable` hoặc **kế thừa** từ class đã triển khai interface này đều thuộc nhóm serializable theo cơ chế mặc định, miễn những điều kiện serialization khác được đáp ứng.

```java
import java.io.Serializable;

class Parent {
    Parent() { }
}

class Child extends Parent implements Serializable {
    private static final long serialVersionUID = 1L;

    Child() {
        super();
    }
}
```

Đây là đoạn mã minh họa, không có `main`. `Parent` **không** cần implements `Serializable` để `Child` trở thành Serializable. Nhưng việc không Serializable của `Parent` có hệ quả:

- **Field khai báo tại `Parent` không được cơ chế Java serialization mặc định lưu và khôi phục tự động**.
- Khi deserialization một `Child`, Java gọi **no-arg constructor hợp lệ của `Parent`**.
- Constructor của `Child` không được gọi; field Serializable của `Child` được khôi phục từ stream thay vì khởi tạo qua constructor thông thường.

Lưu ý: `Serializable` được kế thừa như một khả năng của class. Nếu `GrandParent implements Serializable`, `Parent extends GrandParent` và `Child extends Parent`, cả `Parent` và `Child` đều là Serializable ngay cả khi chúng không lặp lại chữ `implements Serializable`.

## 3. Vì sao constructor xử lý khác với `new`?

### 3.1. Tạo đối tượng bằng `new`

Trong Java thông thường:

```java
Child child = new Child();
```

Trình tự constructor về nguyên tắc là:

1. Khởi tạo object theo cơ chế JVM.
2. Constructor của lớp trên cùng không có cha rõ ràng, chẳng hạn `Object()`, chạy theo chuỗi `super`.
3. Constructor của các lớp cha chạy từ trên xuống.
4. Constructor của class cụ thể `Child` chạy; field initializers và instance initializer blocks được thực hiện theo thứ tự khởi tạo Java.

Nếu field hoặc constructor của `Child` gọi `super(args)`, quy tắc trình tự tương ứng được áp dụng.

### 3.2. Khôi phục bằng `readObject()`

Khi:

```java
Child restored = (Child) objectInput.readObject();
```

cơ chế serialization cần tái tạo **trạng thái đã được lưu** của phần serializable, chứ không “gọi `new Child()` rồi gán vài field” theo cách ứng dụng bình thường.

Vì vậy:

- Không thực thi constructor `Child`.
- Không thực thi **instance field initializer** hoặc **instance initializer block** của những class nằm trong phần Serializable của chuỗi kế thừa.
- Không thực thi constructor của các superclass Serializable nằm giữa.
- Có thực thi constructor không tham số được chọn ở lớp cha gần nhất **không** Serializable; constructor ấy có thể gọi tiếp superclass non-serializable của nó.
- Sau đó các field thuộc những class serializable được phục hồi từ dữ liệu stream theo cơ chế Object Serialization.

**Quan trọng:** static initialization là cơ chế riêng của JVM. Khi class lần đầu được khởi tạo, static initializer có thể chạy theo quy tắc khởi tạo class; không được nhầm điều đó với việc constructor instance được gọi cho mỗi đối tượng deserialize.

## 4. Ví dụ Java 17: constructor nào chạy và field nào được giữ?

Chương trình chạy độc lập sau sử dụng lớp cha **không Serializable** và lớp con **Serializable**.

Ở lúc tạo mới, lớp cha đặt `baseValue = 10`; constructor lớp con ghi đè thành 99 và đặt `childValue = 77`. Sau khi ghi rồi đọc đối tượng bằng stream, constructor lớp cha lại chạy và đặt `baseValue = 10`, nhưng constructor lớp con không chạy. Vì `baseValue` là field của lớp cha không Serializable nên giá trị 99 **không được tự khôi phục**; `childValue` là field của lớp con Serializable và được khôi phục thành 77.

**Tệp `SerializableConstructorDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class SerializableConstructorDemo {
    static class Base {
        int baseValue;

        Base() {
            System.out.println("Base constructor");
            baseValue = 10;
        }
    }

    static class Child extends Base implements Serializable {
        private static final long serialVersionUID = 1L;

        int childValue;

        Child() {
            // super() được compiler thêm mặc định.
            System.out.println("Child constructor");
            baseValue = 99;
            childValue = 77;
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {

        Child original = new Child();
        System.out.println("Before: base=" + original.baseValue
                + ", child=" + original.childValue);

        ByteArrayOutputStream memory = new ByteArrayOutputStream();
        try (ObjectOutputStream output =
                     new ObjectOutputStream(memory)) {
            output.writeObject(original);
        }

        Child restored;
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(memory.toByteArray()))) {
            restored = (Child) input.readObject();
        }

        System.out.println("After: base=" + restored.baseValue
                + ", child=" + restored.childValue);
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac SerializableConstructorDemo.java
java SerializableConstructorDemo
```

**Stdout chính xác khi chương trình thành công:**

```text
Base constructor
Child constructor
Before: base=99, child=77
Base constructor
After: base=10, child=77
```

**Phân tích:**

1. `new Child()`: chạy `Base()` rồi `Child()`, nên `baseValue=99` và `childValue=77`.
2. `ObjectOutputStream.writeObject(original)`: lưu state Serializable của `Child`. Nó không tự lưu `Base.baseValue` trong cơ chế mặc định vì `Base` không Serializable.
3. `ObjectInputStream.readObject()`: JVM tạo một instance của `Child` theo cơ chế phục hồi, **không gọi `Child()`**.
4. `Base()` được gọi vì `Base` là superclass không Serializable gần nhất có constructor không tham số hợp lệ, nên `baseValue=10`.
5. `childValue` thuộc phần Serializable và được khôi phục từ stream thành `77`.

Đây là cách kiểm chứng thực nghiệm rõ nhất: lần thứ hai output có dòng **`Base constructor`** nhưng **không có dòng `Child constructor`**.

## 5. Nếu có nhiều lớp Serializable kế thừa nhau thì sao?

Giả sử:

```text
PlainRoot              không Serializable
   |
   +-- SerialParent    implements Serializable
          |
          +-- SerialChild  extends SerialParent
```

Khi khôi phục một `SerialChild`:

- Constructor `PlainRoot()` được chạy.
- Constructor `SerialParent()` **không chạy**.
- Constructor `SerialChild()` **không chạy**.
- Các field Serializable của **cả `SerialParent` lẫn `SerialChild`** được khôi phục từ stream, trừ những field không được serialization mặc định ghi (như `transient`).

Các lớp dưới `SerialParent` tự động Serializable do kế thừa. Việc chúng có constructor rỗng hay không **không quyết định** cách gọi constructor khi deserialization mặc định.

### Ví dụ Java 17: ba cấp kế thừa

**Tệp `SerializationHierarchyDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class SerializationHierarchyDemo {
    static class PlainRoot {
        int rootNumber;

        PlainRoot() {
            System.out.println("PlainRoot()");
            rootNumber = 1;
        }
    }

    static class SerialParent extends PlainRoot
            implements Serializable {
        private static final long serialVersionUID = 1L;

        int parentNumber;

        SerialParent() {
            System.out.println("SerialParent()");
            rootNumber = 99;
            parentNumber = 2;
        }
    }

    static class SerialChild extends SerialParent {
        private static final long serialVersionUID = 1L;

        int childNumber;

        SerialChild() {
            System.out.println("SerialChild()");
            childNumber = 3;
        }
    }

    public static void main(String[] args) throws Exception {
        SerialChild before = new SerialChild();

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output =
                     new ObjectOutputStream(bytes)) {
            output.writeObject(before);
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            SerialChild after = (SerialChild) input.readObject();
            System.out.println("Values: " + after.rootNumber
                    + ", " + after.parentNumber
                    + ", " + after.childNumber);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac SerializationHierarchyDemo.java
java SerializationHierarchyDemo
```

**Stdout chính xác nếu I/O thành công:**

```text
PlainRoot()
SerialParent()
SerialChild()
PlainRoot()
Values: 1, 2, 3
```

**Tại sao root=1 thay vì 99?** `rootNumber` là field khai báo trên lớp `PlainRoot` không Serializable. Khi tạo instance `new`, constructor `SerialParent` đổi thành 99; nhưng quá trình deserialize không gọi `SerialParent()`, mà gọi `PlainRoot()` đặt lại 1. Hai field Serializable `parentNumber` và `childNumber` được phục hồi thành 2 và 3 từ stream.

## 6. Constructor cần tồn tại ở **superclass đầu tiên không Serializable**

Giả sử `Child implements Serializable` và `Base` là superclass trực tiếp không Serializable. `ObjectInputStream` yêu cầu **constructor không tham số hợp lệ** của `Base` để khôi phục đối tượng.

### 6.1. Chấp nhận được

```java
class Base {
    protected Base() {
        // Thiết lập trạng thái nền tảng.
    }
}

class Child extends Base implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    Child(int value) {
        super();
    }
}
```

Vì `Base()` là `protected`, constructor đó có thể được lớp con truy cập theo quy tắc Java. Constructor `Child(int)` có tham số hay không **không quan trọng đối với việc constructor Child được gọi lúc deserialize**, vì constructor ấy không được dùng trong cơ chế mặc định.

### 6.2. Không có constructor không tham số

```java
class Base {
    Base(int value) {
        // Không khai báo Base() không tham số.
    }
}

class Child extends Base implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    Child() {
        super(42);
    }
}
```

**Code này có thể biên dịch**, vì constructor `Child()` chủ động gọi `super(42)` khi tạo mới. Nhưng `Base` **không có no-arg constructor**, nên deserialization một `Child` thông thường không thể thực hiện đúng bước khởi tạo superclass và sẽ thất bại với `InvalidClassException` báo không có constructor hợp lệ.

Điều đó không chỉ là lỗi lúc compile. **Việc `new Child()` và `writeObject(child)` thành công không chứng minh `readObject()` sẽ thành công.**

### 6.3. Constructor riêng tư hoặc không truy cập được

Constructor của superclass không Serializable được chọn cần **accessible to the subclass that is Serializable** theo đặc tả Java Object Serialization.

- `public` hoặc `protected` no-arg constructor nhìn chung là lựa chọn rõ ràng.
- No-arg constructor *package-private* chỉ dùng được trong bối cảnh truy cập phù hợp (ví dụ cùng package).
- Constructor `private` không thể được lớp con thường truy cập; việc có constructor rỗng private **không** giải quyết yêu cầu.
- Các rào cản module/access giữa package và module có thể tạo vấn đề quyền truy cập trong thiết kế phức tạp.

**Không nên lược giản thành “phải có public no-arg constructor”.** Với `Serializable` thông thường, `protected` hoặc no-arg constructor có khả năng truy cập theo ngữ cảnh cũng có thể hợp lệ; yêu cầu **public** áp dụng nổi bật cho `Externalizable`, một cơ chế khác được so sánh phía dưới.

## 7. Ví dụ Java 17: thiếu no-arg constructor dẫn đến InvalidClassException

Ví dụ này cố ý tạo một class có superclass chỉ có constructor một tham số. Nó chứng minh:

- Constructor lớp con dùng để tạo mới có thể hoạt động.
- Serialization bằng `writeObject` có thể hoàn thành.
- **Deserialization thất bại** vì superclass không cung cấp no-arg constructor hợp lệ.

**Tệp `MissingSuperclassConstructorDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class MissingSuperclassConstructorDemo {
    static class Base {
        int value;

        Base(int value) {
            this.value = value;
        }
    }

    static class Child extends Base implements Serializable {
        private static final long serialVersionUID = 1L;

        Child() {
            super(42);
        }
    }

    public static void main(String[] args) throws Exception {
        Child original = new Child();
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (ObjectOutputStream output =
                     new ObjectOutputStream(sink)) {
            output.writeObject(original);
        }

        System.out.println("Write succeeded");

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(sink.toByteArray()))) {
            input.readObject();
            System.out.println("Read succeeded");
        } catch (InvalidClassException ex) {
            System.out.println("Read failed: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac MissingSuperclassConstructorDemo.java
java MissingSuperclassConstructorDemo
```

**Stdout chính xác khi lỗi như mong đợi xảy ra:**

```text
Write succeeded
Read failed: InvalidClassException
```

Thông điệp chi tiết của `InvalidClassException` có thể khác nhau giữa các JDK/triển khai. Vì vậy chương trình chỉ in **tên loại ngoại lệ**, không giả định một message cố định.

Cách sửa phù hợp nếu có quyền chỉnh lớp cha:

```java
class Base {
    int value;

    protected Base() {
        value = 0;
    }

    Base(int value) {
        this.value = value;
    }
}
```

Đoạn này là phần minh họa thay thế định nghĩa `Base`, không chạy riêng. Nếu deserialize `Child`, giá trị `Base.value` được khởi tạo theo `Base()`, **không tự lấy lại giá trị 42** từng được đặt lúc tạo mới. Nếu cần phục hồi trạng thái superclass nonserializable, phải bổ sung cách lưu/khôi phục tường minh theo hợp đồng serialization.

## 8. Phân biệt **constructor lớp cha được gọi** và **field được serialize**

Đây là hai chuyện khác nhau:

| Field khai báo ở đâu? | Constructor phần class đó khi deserialize? | Field được khôi phục tự động? |
| --- | --- | --- |
| Class cha đầu tiên **không Serializable** | **Có**, gọi no-arg constructor | **Không**, không mặc định lưu field của superclass này |
| Tổ tiên không Serializable phía trên | Có theo chuỗi `super()` của constructor được gọi | **Không** theo cơ chế mặc định |
| Class đầu tiên `implements Serializable` | **Không** | Có đối với field instance thuộc dữ liệu serializable, trừ ngoại lệ như `transient` |
| Class con của một class Serializable | **Không** | Có đối với field instance phù hợp |
| `static` field | Không phải field của từng instance | **Không** lưu như instance state |
| `transient` field | Field initializer của Serializable không chạy | **Không** tự lưu/khôi phục; nhận mặc định trừ custom logic |

Những field **không được lưu** theo cơ chế mặc định không tự biết trạng thái trước đó. `Base()` có thể thiết lập lại field của superclass nonserializable, hoặc nếu không thiết lập thì chúng nhận giá trị mặc định theo quy tắc JVM/constructor chain.

Một nuance: field của lớp nonserializable có thể là đối tượng chứa socket, file descriptor hoặc state runtime. Ngay cả khi có cách serialize một phần giá trị của nó, việc khôi phục kết nối bên ngoài **không** đồng nghĩa deserialize một object có thể tự tái lập tài nguyên đó. Khi thiết kế object graph, nên mô hình hóa rõ phần trạng thái bền vững và phần tài nguyên sống.

## 9. Instance field initializers và initializer blocks có chạy lại không?

**Không đối với phần serializable của đối tượng được deserialize theo cơ chế mặc định.** Đây là điểm khiến giá trị field trông “bất ngờ”.

Ví dụ minh họa:

```java
class Base {
    int parentCounter = 100;

    Base() {
        parentCounter++;
    }
}

class Child extends Base implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    int number = 10;
    transient int cache = 20;

    {
        number += 5;
        cache += 5;
    }

    Child() {
        number += 1;
    }
}
```

Khi `new Child()`:

- `Base` field initializer đặt `parentCounter=100`, constructor tăng thành 101.
- `Child.number` bắt đầu 10, initializer block tăng thành 15, constructor tăng thành 16.
- `cache` bắt đầu 20, initializer block tăng thành 25.

Nếu serialize rồi deserialize với cơ chế mặc định:

- `Base()` chạy lại; `parentCounter` lại là **101**.
- `Child` instance initializers và constructor **không** chạy.
- `number` khôi phục giá trị đã lưu, ví dụ **16**.
- `cache` là `transient` nên được khôi phục về **0** (giá trị mặc định của `int`) nếu không có custom deserialization xử lý thêm.

**Cẩn thận:** ví dụ này là đoạn class minh họa, không có `main`. Mọi giả định về giá trị cache cần xét thêm `readObject` custom nếu lớp có triển khai hook này.

## 10. Ví dụ Java 17: transient và initializer không được gọi lại

**Tệp `TransientInitializationDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class TransientInitializationDemo {
    static class Base {
        int parentCounter = 100;

        Base() {
            parentCounter++;
        }
    }

    static class Child extends Base implements Serializable {
        private static final long serialVersionUID = 1L;

        int number = 10;
        transient int cache = 20;

        {
            number += 5;
            cache += 5;
        }

        Child() {
            number += 1;
        }
    }

    public static void main(String[] args) throws Exception {
        Child before = new Child();

        System.out.println("Before: parent="
                + before.parentCounter + ", number="
                + before.number + ", cache=" + before.cache);

        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
            out.writeObject(before);
        }

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(sink.toByteArray()))) {
            Child after = (Child) in.readObject();

            System.out.println("After: parent="
                    + after.parentCounter + ", number="
                    + after.number + ", cache=" + after.cache);
        }
    }
}
```

Chạy:

```bash
javac TransientInitializationDemo.java
java TransientInitializationDemo
```

**Stdout chính xác khi thao tác thành công:**

```text
Before: parent=101, number=16, cache=25
After: parent=101, number=16, cache=0
```

`parentCounter` không tự được khôi phục từ stream nhưng no-arg constructor `Base()` thiết lập thành 101 ở cả hai thời điểm. `number` được khôi phục từ stream, còn `cache` mặc định về 0. Vì initializer của `Child` không chạy lại lúc deserialization, nó không được đặt lại thành 20 hay 25.

Trong ứng dụng thực, trường `transient` đôi khi cần được khởi tạo lại theo logic của ứng dụng sau deserialize, ví dụ dùng `readObject` custom để tính cache từ các field đã khôi phục (kèm kiểm tra invariants). Không nên mong constructor Serializable tự làm việc đó.

## 11. Khi superclass không Serializable có constructor tác dụng phụ

Constructor của lớp cha có thể chứa hành vi ngoài việc đặt field:

```java
class ResourceBase {
    protected ResourceBase() {
        // Có thể mở tài nguyên, tăng metric, đăng ký listener...
    }
}
```

Vì constructor này **chạy khi deserialization**, tác dụng phụ có thể xảy ra **một lần nữa cho mỗi object thực sự được khôi phục**. Hệ quả cần xét:

- Constructor có thể tạo tài nguyên mới, khác tài nguyên đã tồn tại khi object được serialize.
- Constructor có thể đăng ký vào singleton, listener hoặc hệ thống giám sát.
- Nếu constructor phụ thuộc môi trường hiện tại (clock, cấu hình, OS, quyền), trạng thái cha có thể khác thời điểm ghi stream.
- Constructor ném ngoại lệ có thể làm quá trình deserialization thất bại hoặc bị bao gói thành lỗi I/O/stream theo cơ chế khôi phục.

Không nên thiết kế constructor superclass có tác dụng phụ nặng mà không hiểu nó có thể được chạy trong một quy trình deserialize. Mặt khác, **constructor của lớp Serializable không chạy** nên tuyệt đối không thể dùng constructor đó làm nơi duy nhất bảo đảm kiểm tra invariants cho dữ liệu lấy từ stream.

### Điểm nguy hiểm: constructor của cha gọi phương thức có thể override

Giả sử:

```java
class Base {
    Base() {
        init();
    }

    void init() {
        // logic nền
    }
}

class Child extends Base implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private String name;

    @Override
    void init() {
        // Có thể quan sát name khi nó chưa được khôi phục.
    }
}
```

Đây là đoạn class minh họa. Gọi phương thức có thể override từ constructor superclass có thể đi vào implementation của subclass **trước khi state serializable được phục hồi**. Khi đó `name` có thể vẫn là `null` dù stream lưu tên khác null.

Đây cũng là vấn đề khởi tạo object thông thường trong Java khi superclass constructor gọi virtual method, nhưng với deserialization sự khác biệt càng dễ bị bỏ sót vì constructor của subclass không chạy và dữ liệu được phục hồi sau bước khởi tạo superclass.

**Khuyến nghị:** tránh gọi những phương thức có thể override từ constructor nền tảng, nhất là khi chúng phụ thuộc field của lớp con; nếu cần kiểm tra consistency sau deserialization, dùng hook phù hợp và validate sau khi khôi phục trạng thái.

## 12. Nếu cần khôi phục field của superclass không Serializable thì làm thế nào?

Cơ chế mặc định **không tự lưu** các field khai báo ở superclass không Serializable. Nếu ứng dụng cần giữ một số giá trị, class Serializable có thể tùy chỉnh `writeObject` và `readObject` của **chính nó** để lưu và khôi phục thêm state, miễn dữ liệu an toàn/được phiên bản hóa hợp lý.

Cấu trúc thường gặp:

```java
private void writeObject(ObjectOutputStream out)
        throws IOException {
    out.defaultWriteObject();
    out.writeInt(this.valueInheritedFromNonSerializableParent);
}

private void readObject(ObjectInputStream in)
        throws IOException, ClassNotFoundException {
    in.defaultReadObject();
    this.valueInheritedFromNonSerializableParent = in.readInt();
}
```

**Đây chỉ là pseudocode gần Java:** field `valueInheritedFromNonSerializableParent` phải thực sự tồn tại và có quyền ghi, hook phải đặt trong class phù hợp, thêm import và quản lý stream format. Đặc biệt, cần cân nhắc **phạm vi truy cập**: field private của superclass không thể được subclass trực tiếp gán chỉ vì nó là Serializable; cần setter/protected API phù hợp nếu lớp cha cho phép.

Những điểm cần nhớ:

1. `defaultWriteObject()` và `defaultReadObject()` xử lý phần field thông thường của class Serializable theo cơ chế mặc định.
2. Các giá trị được ghi thêm bằng `writeInt`, `writeUTF`… cần đọc lại **đúng thứ tự và đúng kiểu**.
3. Hook `readObject` **không phải constructor**. Nó được gọi theo cơ chế Object Serialization và có thể kiểm tra lại state sau khi các field cần thiết được phục hồi.
4. Dữ liệu stream có thể thiếu, không hợp lệ hoặc bị sửa; phải kiểm tra ràng buộc nghiệp vụ và xem xét `InvalidObjectException` khi state không đáp ứng invariants.
5. Việc thay đổi định dạng dữ liệu của custom hook cần kế hoạch tương thích phiên bản.

### Ví dụ tư duy

Một superclass không Serializable `BasePerson` có field `protected int age`. Subclass `PersonRecord implements Serializable` có thể tự ghi `age` vào phần dữ liệu bổ sung. Trong deserialization, `BasePerson()` chạy trước và tạo age mặc định; sau đó `PersonRecord.readObject(...)` đọc giá trị age đã được serialize rồi cập nhật field. Kết quả là state cha có thể được phục hồi một cách **có chủ đích**, thay vì dựa vào cơ chế mặc định vốn không lưu nó.

Hãy cân nhắc tránh lưu những field trạng thái hệ thống có tính không thể tái tạo, như native handles, sockets đang mở, thread hay locks đang sống. Serialization không bảo đảm khôi phục nguyên trạng các tài nguyên hệ điều hành ấy.

## 13. `serialVersionUID` và lỗi lớp không tương thích

Nên khai báo `serialVersionUID` rõ ràng trong class Serializable:

```java
private static final long serialVersionUID = 1L;
```

ID này dùng trong kiểm tra khả năng tương thích của serialized class descriptor. Nếu class cục bộ không tương thích với descriptor trong stream, `readObject()` có thể ném `InvalidClassException` trước hoặc trong quá trình khôi phục đối tượng.

**Phải phân biệt nguyên nhân:**

| Vấn đề | Lỗi/hậu quả thường gặp |
| --- | --- |
| Superclass không Serializable thiếu no-arg constructor hợp lệ | `InvalidClassException`, ví dụ nguyên nhân “no valid constructor” |
| `serialVersionUID` không khớp hoặc class descriptor không tương thích | `InvalidClassException`, nhưng là lý do khác |
| Field chứa object không serializable trong lúc `writeObject` | `NotSerializableException` |
| Class cần khôi phục không có ở classpath | `ClassNotFoundException` |
| Dữ liệu hỏng hoặc stream không hợp lệ | `StreamCorruptedException`/`IOException` hoặc lỗi khác theo tình huống |

Không xử lý mọi `InvalidClassException` bằng cách “thêm constructor” nếu gốc lỗi là phiên bản lớp không tương thích. Ngược lại, **khai báo `serialVersionUID` không thể bù cho constructor superclass bị thiếu**.

## 14. `Serializable` khác `Externalizable`

`Externalizable` **mở rộng `Serializable`**, nhưng là một giao thức serialization khác: class chủ động ghi/đọc toàn bộ nội dung cần lưu bằng `writeExternal` và `readExternal`.

Điểm rất quan trọng đối với constructor:

- **Serializable thông thường:** khi deserialize, **không gọi constructor của class Serializable**; gọi no-arg constructor hợp lệ của superclass gần nhất **không Serializable**.
- **Externalizable:** khi deserialize, runtime gọi **public no-arg constructor của chính class Externalizable** rồi gọi `readExternal(...)`; vì constructor của class Externalizable chạy, **chuỗi `super()` thông thường cũng chạy**.

Bảng so sánh:

| Tiêu chí | `Serializable` mặc định | `Externalizable` |
| --- | --- | --- |
| Có marker interface? | Có | Có, nhưng thêm phương thức |
| Constructor class được khôi phục có chạy? | **Không** | **Có**, public no-arg constructor |
| Superclass không Serializable được khởi tạo? | Có, qua no-arg constructor được chọn | Có, qua chuỗi constructor thông thường |
| Ai định nghĩa dữ liệu được ghi? | Default serialization, có thể thêm hook | `writeExternal` / `readExternal` |
| Yêu cầu constructor đặc trưng | No-arg của superclass nonserializable gần nhất, có thể truy cập | **Public** no-arg của class Externalizable |
| Lỗi thường gặp | Superclass thiếu no-arg hợp lệ | Externalizable thiếu public no-arg hoặc custom read/write không đối xứng |

**Đừng áp dụng quy tắc “constructor Serializable không chạy” cho `Externalizable` mà không phân biệt giao thức.** Đây là ngoại lệ quan trọng dễ bị hỏi trong phỏng vấn.

## 15. Ví dụ Java 17: constructor `Externalizable` được gọi

**Tệp `ExternalizableConstructorDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.Externalizable;
import java.io.IOException;
import java.io.ObjectInput;
import java.io.ObjectInputStream;
import java.io.ObjectOutput;
import java.io.ObjectOutputStream;

public class ExternalizableConstructorDemo {
    public static class Data implements Externalizable {
        private static final long serialVersionUID = 1L;

        private int number;

        public Data() {
            System.out.println("Data constructor");
        }

        Data(int number) {
            this.number = number;
        }

        @Override
        public void writeExternal(ObjectOutput out) throws IOException {
            out.writeInt(number);
        }

        @Override
        public void readExternal(ObjectInput in)
                throws IOException {
            number = in.readInt();
        }
    }

    public static void main(String[] args) throws Exception {
        Data before = new Data(25);

        ByteArrayOutputStream memory = new ByteArrayOutputStream();
        try (ObjectOutputStream output =
                     new ObjectOutputStream(memory)) {
            output.writeObject(before);
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(memory.toByteArray()))) {
            Data after = (Data) input.readObject();
            System.out.println("Value: " + after.number);
        }
    }
}
```

Biên dịch, chạy:

```bash
javac ExternalizableConstructorDemo.java
java ExternalizableConstructorDemo
```

**Stdout chính xác nếu thao tác thành công:**

```text
Data constructor
Value: 25
```

Tại sao chỉ có **một** dòng “Data constructor”? `new Data(25)` chạy constructor **một tham số**, không in gì. Khi `readObject()` khôi phục Externalizable, runtime gọi **public `Data()`**, in “Data constructor”, rồi gọi `readExternal()` để lấy số 25.

Nếu constructor một tham số cũng in log, ta sẽ thấy log của nó lúc tạo object mới, nhưng **lúc deserialize vẫn chỉ chọn public no-arg**.

Chú ý lớp ở ví dụ là **public static nested class**, có public no-arg constructor. Dùng một **non-static inner class** để serialize có nhiều bẫy về tham chiếu tới enclosing instance và yêu cầu constructor; khi minh họa nên ưu tiên static nested class hoặc top-level class.

## 16. Trường hợp lớp cha thay đổi giữa lúc ghi và đọc

Phần mô tả class nằm trong chương trình nhận stream, không chỉ trong serialized bytes. Vì vậy việc thay đổi cây kế thừa giữa lúc write và read có thể ảnh hưởng khả năng deserialize và cách khởi tạo lớp cha.

Ví dụ tư duy:

1. Phiên bản đầu có `Child implements Serializable` và `Base` là nonserializable với `Base()` hợp lệ.
2. Phiên bản mới thay `Base()` bằng một constructor chỉ nhận tham số.
3. Stream cũ có thể vẫn có `serialVersionUID` khớp với `Child`, nhưng **deserialization thất bại** vì superclass `Base` hiện không còn constructor hợp lệ.

Hành vi tương thích còn phụ thuộc những thay đổi lớp/field/serial descriptor khác. Vì vậy khi sửa thư viện có các class được serialize lâu dài, hãy thử **deserialize dữ liệu đã lưu từ phiên bản cũ bằng phiên bản mới**; đừng chỉ chạy test roundtrip `writeObject -> readObject` trong một binary duy nhất.

Nếu phải lưu dữ liệu lâu dài qua nhiều phiên bản và nhiều ngôn ngữ, Java native serialization có nhiều hạn chế so với định dạng schema có phiên bản như JSON/CBOR/Protocol Buffers hoặc các giải pháp chuyên biệt. Không nên chọn Java serialization chỉ vì muốn tự động lưu object graph mà không đánh giá yêu cầu tương thích.

## 17. Những lỗi suy luận phổ biến

| Suy luận sai | Vì sao sai | Hiểu đúng |
| --- | --- | --- |
| “Deserialization không bao giờ gọi constructor.” | Superclass nonserializable vẫn cần được khởi tạo | Chọn no-arg constructor hợp lệ của superclass gần nhất không Serializable |
| “Serializable class bắt buộc có no-arg constructor.” | Constructor của lớp đó không được gọi theo cơ chế mặc định | Yêu cầu nằm ở superclass đầu tiên không Serializable |
| “Bất kỳ no-arg constructor nào của superclass đều được.” | Private/inaccessible no-arg không đáp ứng hợp đồng | Phải accessible cho subclass Serializable |
| “Subclass không có `implements Serializable` thì constructor của nó chạy.” | Serializable được kế thừa | Mọi class trong đoạn cây serializable có constructor bị bỏ qua lúc deserialize |
| “Field của superclass không Serializable tự được lưu.” | Default serialization chỉ lưu phần serializable | Superclass state do constructor khởi tạo lại hoặc custom logic |
| “Initializer của Serializable chạy lại.” | Khôi phục không chạy instance initialization của Serializable | Serial fields từ stream; transient về mặc định |
| “Thêm `serialVersionUID` sửa được lỗi no-arg constructor.” | Hai điều kiện độc lập | Sửa cấu trúc/constructor superclass hoặc mô hình serialization |
| “`Externalizable` cũng bỏ qua constructor class.” | Giao thức Externalizable gọi public no-arg constructor | Phân biệt hai cơ chế |
| “Constructor lớp con luôn xác thực stream.” | Constructor lớp con không chạy | Xác thực qua custom readObject/readResolve hay cơ chế phù hợp |
| “Superclass constructor có thể gọi mọi method override an toàn.” | Method có thể quan sát subclass state chưa restored | Tránh virtual call từ superclass constructor |
| “Một stream không tin cậy có thể deserialize vô điều kiện.” | Object graph/hook có tác dụng phụ và nhiều rủi ro | Dùng filter hoặc tránh native serialization của input không tin cậy |

## 18. Về bảo mật và sự an toàn khi deserialize

Java native deserialization từ nguồn **không tin cậy** có rủi ro nghiêm trọng: object graph phức tạp, nội dung không mong muốn, chuỗi phương thức/hook và những class có tác dụng phụ. Ngay cả khi constructor của Serializable class **không chạy**, các **hook như `readObject`, `readResolve`**, việc khởi tạo superclass nonserializable và việc tạo những object khác trong graph vẫn có thể thực thi logic.

Vì vậy không kết luận “deserialization an toàn vì bỏ qua constructor”. Với ứng dụng nhận byte từ client hoặc nguồn bên ngoài:

- Ưu tiên **định dạng dữ liệu có schema** và decoder có kiểm tra chặt nếu có thể.
- Nếu buộc sử dụng Object Serialization, thiết lập `ObjectInputFilter` với allowlist/denylist phù hợp, giới hạn độ sâu, số lượng đối tượng và kích thước dữ liệu theo bối cảnh.
- Kiểm tra invariants sau khi khôi phục và không đưa object chưa xác thực trực tiếp vào logic đặc quyền.
- Quản lý phiên bản stream, loại class được phép nhận, giới hạn tài nguyên và cơ chế cô lập.

ObjectInputFilter giảm rủi ro nhưng **không biến việc deserialize mọi dữ liệu không tin cậy thành an toàn tuyệt đối**. Việc thiết kế loại class được khôi phục và chính sách xử lý vẫn cần rà soát riêng.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Class `Child extends Base implements Serializable`, `Base` không Serializable và có `protected Base()`. Khi `readObject()` trả về một `Child`, constructor nào chạy?

**Đáp án:** `Base()` và chuỗi constructor các tổ tiên nonserializable mà `Base()` gọi. `Child()` không chạy trong cơ chế Serializable thông thường.

**Câu 2.** `Base` chỉ có `Base(int)`, còn `Child()` gọi `super(1)` nên `new Child()` biên dịch. Deserialization có thành công không?

**Đáp án:** Không theo cơ chế default Serializable thông thường: thiếu no-arg constructor hợp lệ của superclass nonserializable. `readObject()` sẽ gặp `InvalidClassException`.

**Câu 3.** `Base` không Serializable có field `int x = 5` và no-arg constructor đặt `x = 8`. Sau khi `new Child()`, ứng dụng đổi `x = 20` rồi serialize `Child`. Sau deserialize, x có giá trị nào?

**Đáp án:** **8**, nếu không có custom serialization khác. Field của `Base` không được cơ chế mặc định lưu; no-arg constructor `Base()` chạy lại và đặt giá trị 8.

**Câu 4.** `Child` Serializable có `transient int cache = 100`. Sau khi deserialize, `cache` bằng 100 hay 0?

**Đáp án:** **0** nếu không có custom read hook. Field initializer của `Child` không chạy lại, và `transient` không được khôi phục bởi default serialization.

**Câu 5.** Một class `Data implements Externalizable` có `public Data()` và `Data(int)`. Khi đọc từ stream, constructor nào chạy?

**Đáp án:** Runtime gọi **public `Data()`**, rồi gọi `readExternal`. Trường hợp Externalizable không áp dụng quy tắc bỏ qua constructor của chính class như Serializable thông thường.

**Câu 6.** Có đúng rằng `static` field được serialize nếu khai báo ở Serializable class không?

**Đáp án:** Không. Java Object Serialization mặc định xử lý instance state; `static` là state thuộc class. Giá trị static có thể khác khi chạy chương trình đọc so với chương trình đã ghi.

**Câu 7.** Có thể dùng constructor của `Child implements Serializable` làm nơi duy nhất kiểm tra `balance >= 0` với đối tượng đọc từ stream không?

**Đáp án:** Không. Constructor `Child` không chạy khi deserialize theo cơ chế mặc định. Cần kiểm tra invariants trong hook phục hồi hoặc cơ chế xác thực phù hợp trước khi sử dụng object.

## 20. Tổng kết

Trong Java Object Serialization, cần nhớ ba “vùng” của chuỗi kế thừa:

```text
               Object (không Serializable)
                   |
               Base   (không Serializable)
                   |
            --- ranh giới ---
                   |
             Parent (Serializable)
                   |
             Child  (Serializable)

new Child():
  Constructor Object -> Base -> Parent -> Child

deserialize Child:
  Constructor Object -> Base
  KHÔNG gọi Parent/Child constructors;
  phục hồi state Serializable Parent/Child từ stream.
```

**Quy tắc vàng:** *Java chỉ yêu cầu một constructor không tham số phù hợp ở lớp cha gần nhất **không Serializable**; constructor của các class thuộc đoạn Serializable được bỏ qua khi khôi phục object thông thường. Vì vậy field của cha không Serializable cần được khởi tạo lại hoặc phục hồi tường minh, trong khi field Serializable được đọc từ stream.*

Cần kiểm tra kỹ `transient`, instance initializer, tính accessible của constructor, sự khác biệt với `Externalizable`, tương thích phiên bản và các rủi ro bảo mật. Đây là nền tảng để giải thích phần lớn câu hỏi về constructor trong Java serialization và để thiết kế class có khả năng deserialize ổn định.

**Tài liệu tham khảo Java SE 17:**

1. [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html) — yêu cầu no-arg constructor của nonserializable superclass và cơ chế khôi phục.
2. [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html) — `readObject()` và khôi phục object graph.
3. [Externalizable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Externalizable.html) — constructor và giao thức externalization.
4. [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html) — quy trình khôi phục, trạng thái lớp và stream format.
5. [ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html) — các giới hạn khi xử lý dữ liệu serialized.
