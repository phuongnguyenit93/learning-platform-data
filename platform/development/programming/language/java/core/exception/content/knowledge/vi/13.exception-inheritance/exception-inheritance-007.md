# Checked exception của constructor lớp cha trong Java

## 1. Tình huống cần hiểu

Trong Java, khi tạo đối tượng của một lớp con, **constructor lớp cha phải được thực thi** như một phần của quá trình khởi tạo. Nếu constructor lớp cha khai báo một **checked exception** như `IOException`, constructor lớp con gọi nó phải tuân thủ quy tắc kiểm tra ngoại lệ. Đây là tình huống dễ bị nhầm với quy tắc `throws` của phương thức `@Override`.

Ví dụ:

```java
class Parent {
    Parent() throws java.io.IOException {
        throw new java.io.IOException("parent initialization failed");
    }
}

class Child extends Parent {
    Child() throws java.io.IOException {
        super();
    }
}
```

Đây là **hai class minh họa hợp lệ**, chưa có `main`. Lời gọi `super()` có thể truyền `IOException` ra ngoài, vì vậy `Child()` khai báo `throws IOException`. Khi caller viết `new Child()`, chính caller phải bắt hoặc khai báo checked exception.

Mục tiêu của bài:

- Hiểu chính xác thứ tự gọi constructor từ lớp cha đến lớp con.
- Biết kiểm tra checked exception ở lời gọi `super(...)` tường minh và `super()` ngầm định.
- Nhận ra vì sao constructor mặc định của lớp con có thể **không biên dịch** nếu constructor cha khai báo checked exception.
- Giải thích lý do không thể đặt `super(...)` vào một khối `try/catch` ngay trong constructor con ở **Java 17**.
- Dùng `throws`, lựa chọn overload của constructor cha hoặc thiết kế lại API khi cần.
- Phân biệt **constructor không bị override** với **phương thức override bị hạn chế checked exception**.
- Hiểu `this(...)` và chuỗi constructor qua nhiều lớp.
- Xác định cách caller xử lý lỗi, điều gì đã chạy trước khi khởi tạo thất bại và các lưu ý quản lý tài nguyên.
- Tránh nhầm lỗi biên dịch do `throws` với lỗi không có constructor cha phù hợp hoặc không có quyền truy cập.

Các chương trình đầy đủ trong bài tương thích Java 17+, có lệnh `javac`/`java` và `stdout` được mô tả tách bạch. Những đoạn mã **cố ý không biên dịch** được đánh dấu.

## 2. Constructor không phải phương thức có thể override

Trước hết cần phân biệt hai khái niệm:

- **Method overriding:** lớp con cung cấp implementation thay thế cho phương thức được kế thừa, có quan hệ hợp đồng về `throws` giữa phương thức cha và phương thức con.
- **Constructor chaining:** constructor lớp con gọi constructor lớp cha để khởi tạo phần đối tượng thuộc lớp cha; đây là một **lời gọi constructor**, không phải một lần override.

Ví dụ:

```java
class Parent {
    Parent() throws java.io.IOException {
    }

    void read() throws java.io.IOException {
    }
}

class Child extends Parent {
    Child() throws Exception { // HỢP LỆ VỀ THROWS CỦA CONSTRUCTOR.
        super();
    }

    @Override
    void read() throws Exception { // KHÔNG HỢP LỆ VỚI METHOD OVERRIDE.
    }
}
```

Đây là **mã minh họa lỗi biên dịch có chủ ý**, vì `Child.read()` khai báo `Exception` rộng hơn `IOException`. Riêng `Child() throws Exception` là hợp lệ về quan hệ constructor: `IOException` của `super()` là subtype của `Exception`, nên checked exception được xử lý bằng khai báo.

Vì sao hai kết quả khác nhau?

- Constructor không được thừa kế và không thể override; constructor con có **hợp đồng độc lập** đối với caller `new Child(...)`.
- Phương thức `read()` ở lớp con override một hợp đồng có thể được gọi qua kiểu tĩnh `Parent`. Java không cho thêm checked exception mới/rộng hơn vào phương thức override.
- Dù constructor con có thể khai báo `throws Exception`, trong API tốt bạn nên khai báo **kiểu hẹp, có ý nghĩa**, để caller không phải bắt `Exception` quá rộng.

**Quy tắc trọng tâm:** constructor con có thể khai báo checked exception bằng hoặc rộng hơn loại do `super(...)` yêu cầu; nhưng không được **bỏ qua** nghĩa vụ checked exception từ lời gọi constructor cha nếu không có cơ chế xử lý hợp lệ.

## 3. Thứ tự khởi tạo đối tượng: lớp cha trước lớp con

Khi `new Child(...)` thực hiện thành công, Java phải khởi tạo phần trạng thái lớp cha trước khi hoàn tất phần của lớp con. Một sơ đồ rút gọn:

```text
caller gọi new Child(...)
        |
        v
Child(...) bắt đầu chuỗi constructor
        |
        v
super(...) / this(...) theo ngữ nghĩa constructor
        |
        v
Parent(...) và các lớp tổ tiên cần thiết
        |
        v
khởi tạo instance field / instance initializer của Child
        |
        v
thân constructor Child
        |
        v
new Child(...) trả về tham chiếu
```

Sơ đồ không cố thể hiện chi tiết về cấp phát/giá trị mặc định trước khi chạy constructor. Điều quan trọng là nếu một constructor lớp cha kết thúc đột ngột bằng ngoại lệ, **phần khởi tạo tiếp theo của lớp con không chạy**.

### Chương trình chạy được: lỗi trong constructor cha chặn constructor con

Tạo tệp **`ParentConstructorFlowDemo.java`**:

```java
import java.io.IOException;

class Parent {
    Parent(boolean fail) throws IOException {
        System.out.println("parent start");
        if (fail) {
            throw new IOException("parent failed");
        }
        System.out.println("parent end");
    }
}

class Child extends Parent {
    private final int number = initializeNumber();

    private int initializeNumber() {
        System.out.println("child field initializer");
        return 7;
    }

    Child(boolean fail) throws IOException {
        super(fail);
        System.out.println("child constructor body");
    }

    int number() {
        return number;
    }
}

public class ParentConstructorFlowDemo {
    public static void main(String[] args) {
        try {
            new Child(true);
        } catch (IOException failure) {
            System.out.println("caught=" + failure.getMessage());
        }

        System.out.println("---");

        try {
            Child child = new Child(false);
            System.out.println("result=" + child.number());
        } catch (IOException failure) {
            System.out.println("unexpected=" + failure.getMessage());
        }
    }
}
```

Biên dịch/chạy:

```bash
javac ParentConstructorFlowDemo.java
java ParentConstructorFlowDemo
```

`stdout` chính xác:

```text
parent start
caught=parent failed
---
parent start
parent end
child field initializer
child constructor body
result=7
```

Giải thích đường thất bại:

1. Caller gọi `new Child(true)`.
2. `Child(boolean)` gọi `super(true)`.
3. `Parent(boolean)` in `parent start` và ném `IOException("parent failed")`.
4. Constructor cha không hoàn thành bình thường, nên **initializer của field `number` và thân constructor con chưa chạy**.
5. Đối tượng `Child` không được trả về cho caller; `catch (IOException)` ở caller xử lý lỗi.

Đường thành công: constructor cha hoàn thành, sau đó initializer và thân constructor con thực thi theo thứ tự, rồi caller nhận đối tượng `Child` và đọc `number() == 7`.

**Ghi chú:** một lỗi constructor **không tự rollback** những side effect đã xảy ra trước khi ném, ví dụ ghi log, tạo file hoặc thao tác bên ngoài. Nếu constructor mở tài nguyên rồi thất bại, việc cleanup cần được thiết kế tại phạm vi đã sở hữu tài nguyên.

## 4. `super(...)` ném checked exception: constructor con làm gì?

Một constructor lớp con phải gọi constructor của lớp cha, trực tiếp hoặc gián tiếp qua `this(...)`. Khi lời gọi constructor cha có khả năng ném checked exception, constructor con cần khai báo một loại phù hợp trong `throws`, trừ khi đường thiết kế được thay đổi để không gọi constructor cha có hợp đồng ấy.

Ví dụ cơ bản:

```java
import java.io.IOException;

class ConfigBase {
    ConfigBase() throws IOException {
        // Có thể đọc cấu hình.
    }
}

class ConfigChild extends ConfigBase {
    ConfigChild() throws IOException {
        super();
    }
}
```

Đây là **mảnh khai báo class hợp lệ**, chưa có `main`.

Khi viết `new ConfigChild()`, caller phải có `try/catch` hoặc khai báo `throws IOException`. Lỗi checked có thể xuất hiện dù thân `ConfigChild()` không thực hiện thao tác I/O nào sau `super()`: **lời gọi constructor cha đã đủ tạo nghĩa vụ**.

### 4.1. Khai báo rộng hơn thì sao?

Về mặt ngôn ngữ, constructor con này cũng hợp lệ:

```java
class ConfigChild extends ConfigBase {
    ConfigChild() throws Exception {
        super();
    }
}
```

Đây là mảnh thay thế, **không đặt đồng thời với class cùng tên ở trên** khi biên dịch. Vì `IOException` kế thừa `Exception`, khai báo `throws Exception` bao phủ lỗi từ `super()`. Nhưng caller phải xét hợp đồng `Exception` rộng hơn và có thể bị buộc bắt nhiều hơn cần thiết.

Nếu constructor con có các bước riêng cũng ném checked exception, nó có thể liệt kê nhiều kiểu:

```java
class ConfigChild extends ConfigBase {
    ConfigChild() throws IOException, java.text.ParseException {
        super();
        parseOwnState();
    }

    private void parseOwnState() throws java.text.ParseException {
        throw new java.text.ParseException("invalid child config", 0);
    }
}
```

Đây là mảnh class minh họa, cần khai báo `import java.io.IOException` hoặc dùng tên đủ; `IOException` được hiểu là `java.io.IOException`. `ParseException` phát sinh **từ logic lớp con**, không nhất thiết từ constructor cha. Constructor con có thể bổ sung checked exception của chính nó vì **không phải method override**.

### 4.2. Subclass không được khai báo checked exception không liên quan rồi bỏ quên lỗi cha

Đoạn sau **cố ý không biên dịch**:

```java
class Parent {
    Parent() throws java.io.IOException {
    }
}

class Child extends Parent {
    Child() throws java.sql.SQLException {
        super(); // IOException không được SQLException bao phủ.
    }
}
```

Compiler từ chối vì `SQLException` và `IOException` là hai checked exception khác nhánh. Chỉ khai báo một kiểu checked khác không hoàn thành nghĩa vụ đối với `super()`.

Sửa bằng `throws IOException` hoặc `throws IOException, SQLException` nếu thân constructor con còn có đường ném `SQLException` phù hợp. Không thể xem “đã có `throws` rồi” là đủ.

## 5. `super()` ngầm định: lỗi dễ bị bỏ sót nhất

Trong Java 17, nếu constructor lớp con không bắt đầu bằng lời gọi constructor hợp lệ tường minh như `this(...)` hoặc `super(...)`, compiler sẽ ngầm chèn lời gọi `super()` phù hợp.

Ví dụ:

```java
class Parent {
    Parent() throws java.io.IOException {
    }
}

class Child extends Parent {
    Child() {
        System.out.println("child");
    }
}
```

Đây là **mã cố ý không biên dịch**. Mặc dù không nhìn thấy từ khóa `super`, ý nghĩa constructor con tương đương:

```java
Child() {
    super(); // Ngầm định và có thể ném IOException.
    System.out.println("child");
}
```

Vì `Child()` không khai báo `throws IOException`, javac báo lỗi checked exception không được xử lý/khai báo tại constructor. Không phải do `System.out.println`.

**Sửa:**

```java
class Child extends Parent {
    Child() throws java.io.IOException {
        super(); // Có thể bỏ dòng này; super() vẫn được gọi ngầm.
        System.out.println("child");
    }
}
```

Ở đây các đoạn class `Child` là các **phương án thay thế**, không nên đặt nhiều khai báo cùng tên trong cùng scope.

### `super()` ngầm định khác với không có constructor không tham số

Có ít nhất **hai lỗi biên dịch khác nhau**:

1. Constructor cha không tham số **tồn tại** nhưng khai báo checked exception → constructor con cần `throws` phù hợp.
2. Lớp cha **không có constructor không tham số truy cập được** → `super()` ngầm định **không khớp lời gọi**, dù thêm `throws Exception` cũng không sửa được. Phải gọi `super(arguments)` để chọn constructor hợp lệ của cha.

Ví dụ trường hợp 2:

```java
class Parent {
    Parent(String name) {
    }
}

class Child extends Parent {
    Child() {
        // Không có Parent() nên super() ngầm định không hợp lệ.
    }
}
```

Đây là **mã cố ý không biên dịch**. Sửa thành:

```java
class Child extends Parent {
    Child() {
        super("default");
    }
}
```

**Quan trọng:** không được nhầm “không có default constructor” với “default constructor ném checked exception”. Hai lỗi cần hai cách giải quyết khác nhau.

## 6. Constructor **mặc định** của lớp con cũng có thể không biên dịch

Nếu lớp con **không viết constructor nào**, Java có cơ chế tạo default constructor. Với lớp thông thường, default constructor này gọi `super()` và **không tự suy ra danh sách checked exception để thêm vào `throws`**.

Ví dụ **cố ý không biên dịch**:

```java
class Parent {
    Parent() throws java.io.IOException {
    }
}

class Child extends Parent {
    // Không khai báo constructor.
    // Default Child() phải gọi Parent(), nhưng IOException chưa khai báo.
}
```

Điều này đôi khi gây ngạc nhiên: “Tôi chưa hề khai báo `Child()`, tại sao compiler báo lỗi ở lớp con?” Vì constructor mặc định không thể thực hiện lời gọi `super()` có checked exception mà nó không khai báo.

Cách sửa là **khai báo constructor con tường minh**:

```java
class Child extends Parent {
    Child() throws java.io.IOException {
        super();
    }
}
```

Nếu constructor cha không tham số không tồn tại hoặc không truy cập được, cách sửa còn phải chọn đúng constructor cha, không chỉ thêm `throws`.

### Mẫu thử dễ hiểu

- Viết lớp cha có `Parent() throws IOException`.
- Viết lớp con trống.
- Biên dịch → lỗi liên quan default constructor/checked exception.
- Viết `Child() throws IOException { super(); }`.
- Biên dịch lại → hợp lệ nếu không có lỗi khác.

Các đoạn này là **mảnh class thay thế** để học một quy tắc; không dán tất cả phiên bản `Child` cùng tên vào một file.

## 7. Vì sao không thể bọc `super(...)` trong `try/catch` của constructor con ở Java 17?

Một phản xạ tự nhiên là thử:

```java
class Child extends Parent {
    Child() {
        try {
            super();
        } catch (java.io.IOException failure) {
            System.out.println("fallback");
        }
    }
}
```

Đây là **mã cố ý không biên dịch theo Java 17**. Lời gọi constructor cha `super(...)` không được đặt tùy ý bên trong một khối `try` trong phần thân constructor con. Ở Java 17, explicit constructor invocation phải đứng ở vị trí đầu của constructor; không thể dùng một `try/catch` bao quanh lời gọi `super(...)` để “bắt ngay trong constructor con”.

Ngay cả khi bạn đặt một `try/catch` **sau** `super()` thì nó chỉ bắt ngoại lệ từ các thao tác được thực thi trong `try` sau đó, không bao quanh lời gọi constructor cha đã xảy ra:

```java
class Child extends Parent {
    Child() throws java.io.IOException {
        super();

        try {
            doChildWork();
        } catch (java.io.IOException failure) {
            System.out.println("child work failed");
        }
    }

    private void doChildWork() throws java.io.IOException {
        throw new java.io.IOException("child operation");
    }
}
```

Đây là class minh họa hợp lệ khi `Parent()` khai báo `throws IOException`. Constructor con **vẫn** phải khai báo `throws IOException` cho `super()`.

### Nếu thật sự cần phục hồi từ lỗi của constructor cha

Bạn cần **thay đổi ranh giới xử lý** chứ không bọc trực tiếp `super()` trong constructor con:

- **Caller** bắt checked exception khi gọi `new Child(...)`.
- **Lớp cha** tự xử lý lỗi nội bộ hoặc cung cấp một constructor khác với hợp đồng phù hợp.
- **Thiết kế lại việc khởi tạo**: nếu có thể, tách hoạt động có thể thất bại sang một factory hoặc phương thức khởi tạo có chính sách lỗi riêng, thay vì bắt buộc constructor cha phải ném checked exception.
- **Chọn overload constructor cha khác** nếu semantics và hợp đồng cho phép.

Đừng tạo object giả thành công nếu phần khởi tạo bắt buộc của lớp cha thất bại. Nếu constructor cha ném, quá trình tạo đối tượng lớp con không hoàn tất bình thường.

**Phạm vi phiên bản:** giải thích cú pháp `super(...)` ở đây dành cho Java 17. Các JDK đời sau có thể mở rộng cấu trúc thân constructor qua tính năng ngôn ngữ mới; khi làm bài Java 17 hãy tuân thủ quy tắc phiên bản đó.

## 8. Chọn một overload constructor cha không ném checked exception

Một lớp cha có nhiều constructor với hợp đồng khác nhau. Lớp con được chọn một overload hợp lệ bằng `super(arguments)`:

```java
class Parent {
    Parent() throws java.io.IOException {
        throw new java.io.IOException("default failed");
    }

    Parent(String preset) {
        System.out.println("parent preset=" + preset);
    }
}
```

Nếu lớp con gọi `super()`, nó phải xử lý/khai báo `IOException`. Nếu gọi `super("cached")`, overload được chọn **không khai báo checked exception**, nên lớp con không phải khai báo `IOException` chỉ vì **overload khác** của lớp cha có `throws`.

### Chương trình chạy được: chọn constructor cha an toàn

Tạo tệp **`OverloadedSuperConstructorDemo.java`**:

```java
import java.io.IOException;

class Base {
    Base() throws IOException {
        throw new IOException("default path unavailable");
    }

    Base(String mode) {
        System.out.println("base mode=" + mode);
    }
}

class Derived extends Base {
    Derived() {
        super("cached");
        System.out.println("derived ready");
    }
}

public class OverloadedSuperConstructorDemo {
    public static void main(String[] args) {
        new Derived();
        System.out.println("done");
    }
}
```

```bash
javac OverloadedSuperConstructorDemo.java
java OverloadedSuperConstructorDemo
```

`stdout`:

```text
base mode=cached
derived ready
done
```

Giải thích: `Derived()` gọi overload `Base(String)`. Overload `Base() throws IOException` không được thực thi trên đường này. Vì vậy `Derived()` không cần `throws IOException`.

**Không lạm dụng:** chỉ chọn overload khác nếu nó thật sự thiết lập được các bất biến mà đối tượng cần. Đổi từ khởi tạo bắt buộc sang “cached” chỉ để thoát khỏi checked exception có thể tạo đối tượng không đúng trạng thái.

## 9. `this(...)`: ngoại lệ đi qua chuỗi constructor của chính lớp con

`this(arguments)` dùng để gọi một constructor khác trong **cùng lớp**. Một constructor trong chuỗi cuối cùng phải dẫn đến constructor cha phù hợp. Checked exception từ constructor được gọi qua `this(...)` cũng phải được xử lý theo quy tắc compile-time.

Ví dụ:

```java
class Child extends Parent {
    Child() throws java.io.IOException {
        this("sample");
    }

    Child(String name) throws java.io.IOException {
        super();
        System.out.println(name);
    }
}
```

Đây là mảnh class minh họa khi `Parent() throws IOException`. Constructor không tham số **không trực tiếp gọi `super()`**, nhưng nó gọi `this("sample")`; constructor được ủy quyền sẽ gọi `super()` và có thể ném `IOException`. Vì vậy cả chuỗi phải bảo đảm checked exception được khai báo tại từng lời gọi không được bắt.

### Ví dụ chạy được: truyền lỗi qua `this(...)`

Tạo tệp **`ThisConstructorChainDemo.java`**:

```java
import java.io.IOException;

class Parent {
    Parent(boolean fail) throws IOException {
        System.out.println("parent");
        if (fail) {
            throw new IOException("parent failed");
        }
    }
}

class Child extends Parent {
    Child(boolean fail) throws IOException {
        this("delegated", fail);
        System.out.println("outer child");
    }

    Child(String name, boolean fail) throws IOException {
        super(fail);
        System.out.println("inner child: " + name);
    }
}

public class ThisConstructorChainDemo {
    public static void main(String[] args) {
        try {
            new Child(false);
        } catch (IOException failure) {
            System.out.println("unexpected");
        }

        System.out.println("---");

        try {
            new Child(true);
        } catch (IOException failure) {
            System.out.println("caught=" + failure.getMessage());
        }
    }
}
```

```bash
javac ThisConstructorChainDemo.java
java ThisConstructorChainDemo
```

`stdout`:

```text
parent
inner child: delegated
outer child
---
parent
caught=parent failed
```

Ở đường thành công, thứ tự là constructor cha → phần còn lại của constructor nhận `(String, boolean)` → phần còn lại của constructor nhận `(boolean)`. Ở đường lỗi, constructor cha ném trước, nên các dòng `inner child` và `outer child` của đường thứ hai không xuất hiện.

Nếu constructor con gọi `this(...)` mà **không** khai báo checked exception mà constructor đích có thể ném, compiler sẽ báo lỗi tại constructor gọi, dù constructor con không trực tiếp viết `super()`.

### Không thể tạo vòng `this(...)`

`Child() { this(1); }` và `Child(int n) { this(); }` nếu chỉ gọi lẫn nhau sẽ là **recursive constructor invocation** không hợp lệ. Có thêm `throws` không giải quyết được vì cần một đường thực sự khởi tạo lớp cha và hoàn tất chuỗi constructor.

## 10. Chuỗi nhiều cấp kế thừa: root → middle → leaf

Đối với nhiều tầng:

```text
Root() throws IOException
     |
     v
Middle() throws IOException
     |
     v
Leaf() throws IOException
     |
     v
new Leaf() tại caller
```

Mỗi constructor gọi lên cấp cao hơn có thể phải khai báo checked exception tương thích. Nếu một tầng không thể thay đổi constructor gốc, caller vẫn phải chuẩn bị cho exception cuối cùng được công bố bởi constructor được chọn của tầng thấp nhất.

### Chương trình chạy được: ba cấp constructor

Tạo file **`ThreeLevelConstructorDemo.java`**:

```java
import java.io.IOException;

class Root {
    Root(boolean fail) throws IOException {
        System.out.println("root");
        if (fail) {
            throw new IOException("root failed");
        }
    }
}

class Middle extends Root {
    Middle(boolean fail) throws IOException {
        super(fail);
        System.out.println("middle");
    }
}

class Leaf extends Middle {
    Leaf(boolean fail) throws IOException {
        super(fail);
        System.out.println("leaf");
    }
}

public class ThreeLevelConstructorDemo {
    public static void main(String[] args) {
        try {
            new Leaf(false);
        } catch (IOException failure) {
            System.out.println("unexpected");
        }

        System.out.println("---");

        try {
            new Leaf(true);
        } catch (IOException failure) {
            System.out.println("caught=" + failure.getMessage());
        }
    }
}
```

```bash
javac ThreeLevelConstructorDemo.java
java ThreeLevelConstructorDemo
```

`stdout`:

```text
root
middle
leaf
---
root
caught=root failed
```

Khi root lỗi, **không có dòng middle/leaf** ở lượt khởi tạo thất bại. Đối tượng Leaf chưa hoàn tất tạo, không được trả về cho caller.

Điều này cũng áp dụng nếu `Root` là abstract class có constructor: abstract class không được khởi tạo trực tiếp bằng `new Root()`, nhưng constructor của nó **vẫn được thực thi** khi tạo subclass cụ thể. Abstract constructor có `throws IOException` cũng tạo nghĩa vụ kiểm tra ngoại lệ cho constructor lớp con.

## 11. Checked exception từ **biểu thức đối số** của `super(...)`

Lỗi checked không chỉ đến từ **thân constructor cha**. Khi đánh giá biểu thức dùng làm đối số của `super(arguments)` hoặc `this(arguments)`, một phương thức phụ có thể ném checked exception, và constructor đang gọi cũng phải xử lý/khai báo.

Ví dụ:

```java
class Parent {
    Parent(String value) {
        System.out.println("parent=" + value);
    }
}

class Child extends Parent {
    private static String loadValue() throws java.io.IOException {
        throw new java.io.IOException("cannot prepare argument");
    }

    Child() throws java.io.IOException {
        super(loadValue());
    }
}
```

Đây là **mảnh class hợp lệ**. `Parent(String)` không khai báo checked exception, nhưng `loadValue()` được gọi **để tạo đối số** cho constructor cha và có `throws IOException`. Vì thế `Child()` vẫn cần khai báo checked `IOException`.

### Ví dụ chạy được: đối số thất bại trước khi constructor cha được gọi

Tạo file **`SuperArgumentFailureDemo.java`**:

```java
import java.io.IOException;

class Base {
    Base(String value) {
        System.out.println("base=" + value);
    }
}

class Derived extends Base {
    private static String prepare(boolean fail) throws IOException {
        System.out.println("prepare argument");
        if (fail) {
            throw new IOException("argument failed");
        }
        return "ready";
    }

    Derived(boolean fail) throws IOException {
        super(prepare(fail));
        System.out.println("derived body");
    }
}

public class SuperArgumentFailureDemo {
    public static void main(String[] args) {
        try {
            new Derived(true);
        } catch (IOException failure) {
            System.out.println("caught=" + failure.getMessage());
        }
        System.out.println("---");
        try {
            new Derived(false);
        } catch (IOException failure) {
            System.out.println("unexpected");
        }
    }
}
```

```bash
javac SuperArgumentFailureDemo.java
java SuperArgumentFailureDemo
```

`stdout`:

```text
prepare argument
caught=argument failed
---
prepare argument
base=ready
derived body
```

Trong đường lỗi, `prepare(true)` ném trước khi lời gọi `Base(String)` thực sự thực hiện thân của constructor cha, nên **không in `base=...`**. Đây là một khác biệt quan trọng: trong phần phân tích checked exception, phải xem cả constructor được gọi lẫn **các biểu thức tính toán đối số**.

Trong Java 17, tránh dùng trực tiếp `this` hoặc thành viên instance chưa hợp lệ trong explicit constructor invocation. Phương thức `prepare` của ví dụ là `static` để không phụ thuộc vào trạng thái instance chưa khởi tạo.

## 12. Constructor lớp con có được thêm checked exception của chính mình không?

**Có.** Constructor không phải override, vì vậy không có quy tắc “lớp con chỉ được giữ hoặc thu hẹp throws của lớp cha” như với phương thức ghi đè.

Nếu `Parent()` không ném checked exception, `Child()` có thể khai báo `throws IOException` và ném nó từ chính phần thân:

```java
class Parent {
    Parent() {
    }
}

class Child extends Parent {
    Child(boolean fail) throws java.io.IOException {
        super();
        if (fail) {
            throw new java.io.IOException("child setup failed");
        }
    }
}
```

Đây là class minh họa hợp lệ. Caller `new Child(true)` phải xử lý/khai báo `IOException` theo chữ ký của `Child(boolean)`, dù `Parent()` hoàn toàn không ném checked exception.

So sánh với phương thức override:

```java
class Parent {
    void load() {
    }
}

class Child extends Parent {
    @Override
    void load() throws java.io.IOException {
    }
}
```

Đây là **mã cố ý không biên dịch**, vì phương thức `Parent.load()` không cho phép checked `IOException`. Như vậy “constructor con mở rộng checked exception được, phương thức override không được” là khác biệt cần nhớ chính xác.

### Thiết kế hợp đồng constructor

Bên gọi chỉ có thể tạo một object thành công nếu toàn bộ chuỗi khởi tạo cần thiết hoàn tất. Vì vậy, constructor con nên khai báo các checked exception **thực sự có ý nghĩa** cho quá trình khởi tạo. Khai báo `throws Exception` rộng tùy tiện làm caller khó phân loại lỗi và có thể tạo ra code xử lý quá tổng quát.

## 13. Caller phải bắt hoặc khai báo checked exception khi `new`

Nếu constructor `Child(...)` có `throws IOException`, biểu thức `new Child(...)` được kiểm tra tương tự các lời gọi có checked exception khác.

Hai cách hợp lệ:

**Cách A — caller bắt:**

```java
try {
    Child child = new Child(true);
    System.out.println("created");
} catch (java.io.IOException failure) {
    System.out.println("construction failed: " + failure.getMessage());
}
```

**Cách B — caller khai báo:**

```java
public static void main(String[] args)
        throws java.io.IOException {
    Child child = new Child(false);
    System.out.println("created");
}
```

Hai đoạn là **mảnh mã minh họa**: cần có class `Child` và method/`main` thích hợp.

**Trường hợp C — không bắt, không khai báo** trong method bình thường sẽ bị compiler từ chối:

```java
static void start() {
    Child child = new Child(true); // Không xử lý IOException.
}
```

Đây là mảnh **cố ý không biên dịch**, giả định `Child(boolean) throws IOException`.

### Caller dùng biến kiểu cha thì sao?

Với:

```java
Parent value = new Child(true);
```

Quy tắc checked exception của biểu thức `new Child(true)` phụ thuộc vào **constructor của Child được chọn**, không phải chỉ vào kiểu biến `Parent` sẽ nhận tham chiếu. Kiểu tĩnh của biến nhận không làm mất nghĩa vụ xử lý lỗi khởi tạo của constructor con.

Khi object **đã tạo thành công**, các lời gọi phương thức thông qua `Parent` lại dùng hợp đồng checked exception của phương thức được chọn qua **kiểu tĩnh** `Parent`. Đây là hai thao tác khác nhau: `new` để xây object và method invocation trên object đã tồn tại.

## 14. Constructor thất bại và quản lý tài nguyên

Một ngoại lệ từ `super(...)` khiến construction không hoàn tất. Tuy nhiên, **những tài nguyên đã được mở trước khi ném** có thể còn tồn tại nếu không được quản lý.

### 14.1. Constructor cha cần tự bảo toàn cleanup của chính mình

Nếu constructor cha mở tài nguyên A, sau đó bước khởi tạo tiếp theo thất bại, caller không có tham chiếu tới object được xây xong để gọi `close()`. Constructor hoặc factory phụ trách tài nguyên A cần cleanup trên đường lỗi.

Ví dụ **mảnh logic**:

```java
Resource opened = openFirst();
try {
    initializeFurther(opened); // Có thể thất bại.
} catch (Exception failure) {
    try {
        opened.close();
    } catch (Exception cleanup) {
        failure.addSuppressed(cleanup);
    }
    throw failure;
}
```

Đây là **mảnh minh họa** cần khai báo `Resource`, các phương thức và kiểm tra checked exception đầy đủ. Mục đích là cho thấy nguyên nhân gốc không nên bị lỗi close che mất. Khi resource thực thi `AutoCloseable` và quyền sở hữu phù hợp, `try-with-resources` thường dễ đúng hơn cleanup thủ công.

### 14.2. Resource được tạo trong header TWR trước một constructor con thất bại

Tạo file **`ConstructorWithResourcesDemo.java`**:

```java
import java.io.IOException;

class TraceResource implements AutoCloseable {
    TraceResource() {
        System.out.println("open first");
    }

    @Override
    public void close() {
        System.out.println("close first");
    }
}

class Parent {
    Parent(boolean fail) throws IOException {
        System.out.println("parent constructor");
        if (fail) {
            throw new IOException("constructor failed");
        }
    }
}

class Child extends Parent implements AutoCloseable {
    Child(boolean fail) throws IOException {
        super(fail);
        System.out.println("child constructor");
    }

    @Override
    public void close() {
        System.out.println("close child");
    }
}

public class ConstructorWithResourcesDemo {
    public static void main(String[] args) {
        try (TraceResource first = new TraceResource();
             Child child = new Child(true)) {
            System.out.println("body");
        } catch (IOException failure) {
            System.out.println("caught=" + failure.getMessage());
        }
    }
}
```

```bash
javac ConstructorWithResourcesDemo.java
java ConstructorWithResourcesDemo
```

`stdout`:

```text
open first
parent constructor
close first
caught=constructor failed
```

Ở đây:

1. `TraceResource first` được khởi tạo thành công trong header TWR.
2. Khi khởi tạo `Child child`, constructor `Parent` ném `IOException`.
3. Vì `Child` chưa tạo thành công, **không có đối tượng `Child` được gắn vào resource slot để gọi `close()`**; không xuất hiện dòng `close child`.
4. Resource `first` đã được quản lý trong header nên được đóng, và dòng `close first` xuất hiện.
5. Caller nhận checked exception từ quá trình tạo `Child`.

Nếu `first.close()` cũng ném, lỗi đóng có thể trở thành **suppressed exception** gắn vào lỗi chính do constructor ném. `try-with-resources` không thể tự đóng các tài nguyên mà chính constructor cha đã tạo nội bộ rồi làm mất tham chiếu; constructor/factory phải thiết kế cleanup riêng.

### 14.3. Không gọi phương thức trên object chưa được tạo thành công

Nếu `new Child(...)` ném, phép gán thông thường `Child child = new Child(...)` không hoàn tất và chương trình không có một đối tượng `Child` được trả lại cho caller. Không có phương thức `child.close()` hợp lệ trên kết quả xây dựng thất bại đó. Hãy đặt trách nhiệm cleanup nơi tài nguyên được sở hữu và đã có thể truy cập.

## 15. Những trường hợp dễ nhầm với ngoại lệ constructor cha

### 15.1. Lỗi không có constructor `super()` phù hợp

Nếu cha chỉ có `Parent(int)`, lớp con phải gọi `super(intValue)`. Thêm `throws IOException` không tạo ra constructor không tham số.

### 15.2. Lỗi quyền truy cập constructor cha

Nếu constructor cha là `private` và lớp con ở class khác không có quyền gọi, lỗi là **accessibility**, không phải checked exception. Cần chọn constructor truy cập được hoặc thay đổi thiết kế lớp cha.

### 15.3. Constructor trong abstract class

Abstract class vẫn có constructor. Khi tạo lớp con cụ thể, constructor abstract parent vẫn được gọi và checked exception vẫn phải được xử lý/khai báo.

### 15.4. Interface không có constructor

Lớp implements interface không gọi constructor của interface: interface không có instance constructor. Nó vẫn gọi constructor của **lớp cha thực sự** (thường là `Object` nếu không có `extends` class cụ thể).

### 15.5. Constructor không thể bị `@Override`

Đặt `@Override` trên constructor là sai. Tên constructor trùng tên lớp, không có kiểu trả về. Quy tắc giới hạn checked `throws` khi override method không áp lên constructor.

### 15.6. Ngoại lệ từ instance initializer lớp con

Nếu constructor cha hoàn thành, các instance field initializer và instance initializer của lớp con chạy **trước thân constructor con**. Chúng có thể làm construction thất bại, nhưng đó không phải là lỗi do constructor cha ném. Quy tắc checked exception của initializer có những ràng buộc riêng trong JLS; không nên suy đoán rằng mọi checked exception trong initializer đều được ném tùy ý mà không cần xét toàn bộ constructors của lớp.

### 15.7. Lỗi runtime không khai báo

Constructor cha có thể ném `RuntimeException` hoặc `Error` dù không khai báo `throws`. Những kiểu này là unchecked, nên compiler không bắt constructor con khai báo chúng. Tuy nhiên, chúng vẫn có thể làm quá trình tạo object thất bại tại runtime.

### 15.8. Thông điệp lỗi compiler

Thông báo như “unreported exception ...; must be caught or declared to be thrown” là dấu hiệu checked exception chưa được xử lý. Thông báo “constructor ... cannot be applied to given types” hoặc “... has private access” liên quan overload/access. Đọc loại lỗi thực tế, không thêm `throws Exception` một cách máy móc.

## 16. Sơ đồ quyết định khi subclass không biên dịch

```text
Child constructor có lỗi tại super()/implicit super()
                     |
                     v
Parent có constructor tương ứng, truy cập được?
         |                                 |
        KHÔNG                             CÓ
         |                                 |
         v                                 v
Chọn đúng super(args) hoặc       Constructor cha / biểu thức
sửa API/access của Parent        đối số có checked exception?
                                           |
                               +-----------+-----------+
                               |                       |
                              CÓ                      KHÔNG
                               |                       |
                               v                       v
                         Child phải khai báo       Kiểm tra lỗi cú pháp
                         checked tương thích       hoặc logic khác
                         trong throws hoặc
                         chọn đường khởi tạo
                         hợp lệ khác
                               |
                               v
                         Caller new Child(...)
                         bắt/khai báo checked
```

Khi constructor con còn tự gọi `this(...)`, hãy lần theo chuỗi ủy quyền để tìm constructor cuối cùng gọi `super(...)`; kiểm tra checked exception ở từng lời gọi.

### Quy trình sửa an toàn

1. Xác nhận lỗi phát sinh từ `super()` ngầm định, `super(arguments)` tường minh, `this(arguments)` hay biểu thức đối số.
2. Tra **chữ ký constructor thực sự được chọn** (không suy đoán theo tên class).
3. Kiểm tra constructor cha có truy cập được và tham số khớp hay không.
4. Liệt kê checked exception từ constructor được gọi và từ các biểu thức đối số.
5. Khai báo kiểu checked phù hợp trên constructor gọi, hoặc dùng một overload/thiết kế khởi tạo khác có ngữ nghĩa đúng.
6. Lần theo caller `new Child(...)` để bắt hoặc khai báo checked exception.
7. Kiểm tra đường thất bại: phần khởi tạo nào đã chạy, resource nào đã tạo, ai phải cleanup.
8. Biên dịch lại và kiểm tra kết quả theo đường thành công và đường thất bại.

## 17. Bảng tổng hợp về hợp đồng `throws`

| Tình huống | Hợp lệ theo Java 17? | Vì sao |
| --- | --- | --- |
| `Parent() throws IOException`; `Child() throws IOException { super(); }` | **Có** | Child khai báo đúng checked exception từ super |
| `Parent() throws IOException`; `Child() throws Exception { super(); }` | **Có** | Exception bao phủ IOException nhưng hợp đồng rộng |
| `Parent() throws IOException`; `Child() { super(); }` | **Không** | Bỏ nghĩa vụ checked exception |
| `Parent() throws IOException`; `Child() throws SQLException { super(); }` | **Không** | SQLException khác nhánh, không bao phủ IOException |
| `Parent() throws IOException`; `class Child extends Parent { }` | **Không** trong tình huống nêu | Default Child() không tự khai báo throws |
| Cha chỉ có `Parent(String)`; Child viết `Child() { }` | **Không** | super() ngầm định không có overload phù hợp |
| Cha có `Parent(String)` không throws; Child dùng `super("A")` | **Có** | Overload được gọi không khai báo checked |
| Cha không ném checked; Child constructor tự `throws IOException` | **Có** | Constructor con không override constructor cha |
| Parent method không ném checked; override method thêm `throws IOException` | **Không** | Quy tắc checked exception của method override |
| Constructor con gọi `this(...)` có `throws IOException` nhưng không khai báo | **Không** | Lời gọi constructor được ủy quyền có checked |
| Constructor cha không ném checked, nhưng `super(loadValue())` với `loadValue() throws IOException` | Cần `throws` tương ứng | Lỗi đến từ đánh giá đối số |
| `try { super(); } catch (IOException e) { ... }` trong Child() | **Không** ở Java 17 | Không thể bọc explicit constructor invocation theo cách này |
| `new Child()` khi Child() throws IOException trong caller không catch/throws | **Không** | Caller phải xử lý checked exception |
| Parent constructor ném `IllegalStateException`, Child không khai báo throws | **Có** về kiểm tra unchecked | RuntimeException không bắt buộc khai báo |

Bảng đánh giá **riêng những quy tắc nêu ra**; những ví dụ viết tắt giả định class, quyền truy cập và các khai báo khác phù hợp. Một đoạn hoàn chỉnh còn phải biên dịch về tham số, field, package và class names.

## 18. Những hiểu nhầm phổ biến

**“Constructor của lớp con override constructor lớp cha.”** Sai. Constructor không được kế thừa/override; lời gọi `super(...)` là constructor chaining, không phải dynamic dispatch của method.

**“Vì override không được mở rộng checked exception, Child constructor cũng không được thêm `SQLException` nếu Parent constructor chỉ throws IOException.”** Sai về quy tắc constructor. Child có thể khai báo thêm checked exception riêng vì constructor không override. Nhưng nó **vẫn phải bao phủ IOException** nếu gọi constructor cha có `throws IOException`.

**“Không viết `super()` nghĩa là không có checked exception của cha.”** Sai. Java 17 chèn `super()` ngầm định khi constructor không ủy quyền hay gọi cha tường minh.

**“Lớp con không khai báo constructor nên compiler sẽ tạo default constructor với đủ `throws`.”** Sai. Default constructor không tự suy ra `throws IOException` để đáp ứng constructor cha.

**“Có thể bọc `super()` trong `try/catch` của Child để xử lý lỗi ngay.”** Không hợp lệ ở Java 17. Cần xử lý ở caller, thay đổi API/constructor cha hoặc chọn overload phù hợp.

**“`throws SQLException` trên Child đủ vì đó cũng là checked exception.”** Sai nếu lời gọi `super()` có `throws IOException` mà SQLException không bao phủ.

**“Nếu Parent() có `throws IOException` nhưng thân rỗng, Child không cần khai báo.”** Sai. Kiểm tra dựa trên hợp đồng phương thức/constructor được gọi, không chỉ theo một lần chạy thực tế.

**“Constructor con kết thúc thân trước rồi mới gọi constructor cha.”** Sai. Constructor cha được thực hiện trước phần initializer và thân constructor con trong các ví dụ thông thường.

**“Parent constructor lỗi nhưng Child vẫn tạo thành công với field mặc định.”** Sai. Nếu lỗi thoát khỏi construction, biểu thức `new Child(...)` không hoàn tất bình thường.

**“Lỗi `super(load())` nhất định đến từ constructor cha.”** Không chắc. `load()` trong biểu thức đối số có thể ném trước khi thân constructor cha chạy.

**“Constructor abstract class không được gọi.”** Sai. Constructor của abstract parent vẫn là một mắt xích khi tạo subclass cụ thể.

**“Khi viết `Parent variable = new Child()`, compiler chỉ xét constructor của Parent.”** Sai. Nghĩa vụ checked exception của biểu thức `new Child()` dựa trên constructor Child được chọn.

**“Thêm `throws Exception` giải quyết mọi lỗi liên quan `super()`.”** Sai. Nó không sửa được thiếu overload, private constructor, sai kiểu tham số hoặc lỗi chuỗi `this(...)` đệ quy.

**“Vì Child construction thất bại, mọi tài nguyên Parent đã mở đều được rollback tự động.”** Sai. Java không tự rollback side effects hoặc đóng resource nội bộ không được quản lý. Cần thiết kế cleanup.

**“`try-with-resources` sẽ gọi `close()` trên Child ngay cả khi `new Child()` ném trước khi khởi tạo xong.”** Sai. Resource slot Child chưa hoàn tất khởi tạo nên chưa được đóng như một resource thành công; chỉ các resource trước đó đã được quản lý sẽ được đóng theo quy tắc.

**“Unchecked exception không thể làm constructor thất bại nếu không khai báo `throws`.”** Sai. `RuntimeException` và `Error` vẫn có thể phát sinh tại runtime.

## 19. Câu hỏi tự kiểm tra

1. **Parent() throws IOException, Child() gọi super() không ghi throws: hợp lệ không?** Không.
2. **Child() throws IOException { super(); } có hợp lệ không?** Có, nếu constructor cha được chọn là `Parent() throws IOException` và các điều kiện khác hợp lệ.
3. **Child() throws Exception thay IOException có hợp lệ về constructor không?** Có, nhưng rộng hơn cần thiết.
4. **Child() chỉ throws SQLException có bao phủ IOException của super không?** Không.
5. **Class Child không có constructor mà Parent() throws IOException: có vấn đề gì?** Default constructor ngầm định không khai báo checked exception, nên không biên dịch.
6. **Nếu Parent không có constructor không tham số, chỉ thêm throws có sửa được lỗi?** Không; cần gọi đúng overload `super(arguments)`.
7. **Vì sao không thể `try { super(); } catch ...` trong Child Java 17?** Explicit constructor invocation có ràng buộc vị trí, không thể được đặt trong try như vậy.
8. **Nếu có Parent(String) không throws, Child gọi super("preset") thì sao?** Không cần checked handler cho IOException của overload Parent() khác.
9. **Child() tự ném IOException nhưng Parent() không throws: được không?** Được, vì constructor không override.
10. **Parent method không throws, Child override method throws IOException: được không?** Không, vì method override không được thêm checked exception.
11. **Constructor Child(boolean) gọi this(String, boolean) throws IOException: Child(boolean) có cần throws không?** Có, nếu không có cơ chế xử lý hợp lệ khác; ở Java 17 không được bọc this(...) trong try.
12. **Parent constructor thực thi rồi ném trước khi khởi tạo field của Child: field initializer Child có chạy không?** Không.
13. **Lỗi từ super(load()) có thể do đâu?** Từ `load()` khi đánh giá đối số hoặc từ constructor cha được gọi.
14. **Caller new Child() khi Child() throws IOException phải làm gì?** Bắt hoặc khai báo IOException tương thích.
15. **Gán kết quả new Child() vào biến Parent có xóa nghĩa vụ IOException không?** Không.
16. **Nếu Parent là abstract class, constructor nó có chạy lúc tạo Child không?** Có.
17. **Parent() ném RuntimeException không khai báo; Child phải thêm throws RuntimeException?** Không bắt buộc vì unchecked.
18. **Nếu constructor cha thất bại, caller có object Child hoàn chỉnh để đóng không?** Không.
19. **Nếu resource thứ nhất trong TWR tạo xong, constructor resource thứ hai ném: resource thứ nhất có được đóng không?** Có, theo quy tắc TWR.
20. **Có nên tự thêm throws Exception vào mọi subclass constructor để khỏi kiểm tra?** Không; chọn hợp đồng cụ thể giúp caller xử lý đúng và phát hiện lỗi thiết kế.

## 20. Tài liệu chính thức Java 17

- [Java Language Specification 17 — `8.8 Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): cấu trúc constructor, `throws`, explicit constructor invocation và default constructor.
- [Java Language Specification 17 — `8.8.7.1 Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): quy tắc `this(...)`, `super(...)` và các giới hạn của vị trí lời gọi trong Java 17.
- [Java Language Specification 17 — `8.8.9 Default Constructor](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.9): constructor ngầm định khi class không khai báo constructor.
- [Java Language Specification 17 — `11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2): nghĩa vụ khai báo/bắt checked exception trong việc gọi constructor.
- [Java Language Specification 17 — `12.5 Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): quá trình tạo instance qua các cấp kế thừa.
- [Java Language Specification 17 — `8.4.8.3 Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): so sánh giới hạn `throws` của phương thức override với constructor.
- [Java Language Specification 17 — `14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): cleanup tài nguyên đã được khởi tạo trong header nếu resource sau khởi tạo thất bại.
- [Java SE 17 API — IOException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): checked exception thường gặp trong constructor thực hiện I/O.

**Ghi nhớ:** Constructor của lớp con không ghi đè constructor lớp cha: nó **gọi constructor cha** thông qua `super(...)` trực tiếp hoặc qua chuỗi `this(...)`. Nếu constructor cha hoặc biểu thức đối số có checked exception, constructor con cần **khai báo loại tương thích**, hoặc chọn một đường khởi tạo khác có hợp đồng đúng. `super()` có thể được chèn ngầm; default constructor lớp con không tự kế thừa `throws` của cha. Caller tạo đối tượng phải bắt/khai báo checked exception từ constructor được chọn, và nếu construction thất bại, các tài nguyên đã mở vẫn cần cleanup ở đúng phạm vi sở hữu.
