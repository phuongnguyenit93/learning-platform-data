# Giá trị mặc định trước biểu thức khởi tạo trường trong Java

Khi Java tạo một đối tượng hoặc chuẩn bị một lớp để sử dụng, **trường (field) có giá trị mặc định trước khi biểu thức khởi tạo trường được thực thi**. Vì thế hai câu lệnh tưởng giống nhau — “một field có giá trị 0 lúc đầu” và “một field được lập trình viên gán 0” — không hoàn toàn giống về **thời điểm** và **cơ chế**.

Ví dụ:

~~~java
class Sensor {
    int count = 10;
    boolean active = true;
    String label = "READY";
}
~~~

Khi cấp phát một đối tượng `Sensor`, các instance fields ban đầu nhận **`0`**, **`false`**, **`null`** tương ứng. Chỉ sau đó, trong quá trình khởi tạo đối tượng, các initializer `= 10`, `= true`, `= "READY"` mới được thực thi. Với `static` fields, bước thiết lập giá trị mặc định nằm trong **preparation** khi liên kết lớp; các static initializers sẽ chạy ở giai đoạn **class initialization**.

Đối với chương trình bình thường, trạng thái cuối cùng sau constructor mới là điều caller thường thấy. Tuy nhiên, thứ tự này có thể quan sát được khi một initializer gọi phương thức đọc field còn chưa đến lượt gán, hoặc khi constructor của lớp cha gọi một phương thức được lớp con ghi đè. Hiểu điều đó giúp giải thích output, tránh sai sót khi thiết kế constructor và phân biệt **field**, **phần tử mảng** với **biến cục bộ**.

Bài học thuộc **Java core - class-object**, mục **Thứ tự khởi tạo**. Các chương trình đầy đủ sử dụng Java 17+, có tên tệp, lệnh biên dịch/chạy và stdout để đối chiếu.

## 1. Ba thời điểm cần phân biệt

Đối với một instance field có initializer `int size = 12;`, hãy phân biệt:

1. **Cấp phát và thiết lập mặc định:** vùng lưu field của object mới được cấp phát; `size` ban đầu nhận `0`.
2. **Chạy field initializer:** khi đến lượt initializer của lớp khai báo field, câu `size = 12` được thực hiện.
3. **Chạy thân constructor:** constructor có thể tiếp tục xử lý hợp lệ hóa hoặc thực hiện thao tác khác theo luật của Java; sau khi khởi tạo thành công, caller có object với trạng thái đã được thiết lập.

Mô hình đơn giản:

~~~text
new Sensor()
    |
    v
Cấp phát object
count = 0, active = false, label = null
    |
    v
Các bước constructor của superclass tương ứng
    |
    v
Chạy instance field initializers / instance initializer blocks
count = 10, active = true, label = "READY"
    |
    v
Chạy phần thân constructor Sensor
    |
    v
Object được trả về khi tạo thành công
~~~

Đây là sơ đồ cho một lớp đơn giản; constructor chaining qua `this(...)` có quy tắc riêng và **không chạy lặp lại instance initializers** sau mỗi lần ủy quyền. Với subclass, thứ tự khởi tạo của từng lớp đi theo chuỗi constructor tương ứng, được giải thích ở phần sau.

**Quan trọng:** việc có một giá trị mặc định ở giai đoạn đầu **không bảo đảm mọi đoạn Java thông thường được phép đọc giá trị đó trước initializer**. Ngôn ngữ còn có quy tắc cấm một số tham chiếu sớm đến field và quy tắc definite assignment cho `final`.

## 2. Bảng giá trị mặc định chính xác của field

Các **instance fields** và **static fields** được thiết lập giá trị mặc định tương ứng kiểu dữ liệu trước các bước khởi tạo tường minh phù hợp:

| Kiểu trường | Giá trị mặc định | Lưu ý |
| --- | --- | --- |
| `byte` | `0` | Số nguyên 8 bit |
| `short` | `0` | Số nguyên 16 bit |
| `int` | `0` | Số nguyên 32 bit |
| `long` | `0L` | Số nguyên 64 bit |
| `float` | `+0.0f` | Floating-point dương zero |
| `double` | `+0.0d` | Floating-point dương zero |
| `boolean` | `false` | Không phải `null` |
| `char` | Ký tự có mã `U+0000` | Thường không nhìn thấy khi in trực tiếp |
| Mọi kiểu tham chiếu: `String`, object, mảng, wrapper, `List` | `null` | Không tự tạo object/collection |

Hai điểm dễ sai:

- **`String` không mặc định là chuỗi rỗng `""`**. Một field `String name;` sẽ là `null` trước khi có phép gán thích hợp.
- **Field `int[] values;` mặc định là `null`**, không tự trở thành mảng rỗng. Nếu khởi tạo `new int[3]`, đó là một object mảng mới, và **các phần tử** của mảng lại có mặc định riêng (`0` với `int`).

Các giá trị trên được quy định bởi ngôn ngữ, không phụ thuộc cách JVM cụ thể đặt field ở heap, vùng nhớ nào hay thanh ghi nào.

## 3. Chương trình hoàn chỉnh: xem các mặc định trước khi đặt initializer tường minh

Tạo tệp **`DefaultFieldValuesDemo.java`**:

~~~java
class DefaultFields {
    byte small;
    short medium;
    int count;
    long total;
    float ratio;
    double average;
    boolean enabled;
    char symbol;
    String title;
    int[] numbers;

    String describe() {
        return "byte=" + small
                + ",short=" + medium
                + ",int=" + count
                + ",long=" + total
                + ",float=" + ratio
                + ",double=" + average
                + ",boolean=" + enabled
                + ",charCode=" + (int) symbol
                + ",ref=" + title
                + ",array=" + numbers;
    }
}

public class DefaultFieldValuesDemo {
    public static void main(String[] args) {
        DefaultFields fields = new DefaultFields();
        System.out.println(fields.describe());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 DefaultFieldValuesDemo.java
java DefaultFieldValuesDemo
~~~

**Stdout chính xác:**

~~~text
byte=0,short=0,int=0,long=0,float=0.0,double=0.0,boolean=false,charCode=0,ref=null,array=null
~~~

**Giải thích:** Class `DefaultFields` không có initializer ở những field đã khai báo. Java vẫn thiết lập giá trị mặc định, nên không cần viết thủ công `count = 0`, `enabled = false`, `title = null` để tránh “đọc rác” như trong một số ngôn ngữ khác.

Phép ép kiểu `(int) symbol` cho biết ký tự mặc định có mã 0. Nếu in trực tiếp `symbol`, ký tự U+0000 thường không hiển thị thành một dấu dễ nhận ra trên console.

**Đừng hiểu đây là lời khuyên luôn bỏ initializer.** `new ArrayList<>()`, một giá trị bắt buộc như mã đơn hàng hay trạng thái `ACTIVE` cần được thiết lập rõ tại nơi thích hợp; Java chỉ đảm bảo giá trị mặc định về mặt ngôn ngữ, không đảm bảo nó thỏa **invariant nghiệp vụ**.

## 4. Trường khác biến cục bộ: local không có mặc định được phép đọc

Đây là điểm quan trọng nhất khi so sánh field với biến trong phương thức.

Đối với field:

~~~java
class ReadableField {
    int number;

    int read() {
        return number; // Hợp lệ: number mặc định 0.
    }
}
~~~

Đối với biến cục bộ:

~~~java
class LocalExample {
    static void demo() {
        int number;
        // System.out.println(number); // Lỗi biên dịch: chưa definite assigned.
        number = 5;
        System.out.println(number);
    }
}
~~~

Hai lớp là các đoạn minh họa hợp lệ vì dòng cố ý gây lỗi được comment. **Biến cục bộ và tham số** tuân các quy tắc definite assignment riêng; biến local chưa được gán chắc chắn không được đọc. Java **không tự cho local `int number;` một giá trị mặc định 0 có thể dùng**.

Các tham số method/constructor thì nhận giá trị đối số theo cơ chế truyền giá trị; chúng không phải instance fields mới được cấp phát.

| Vị trí khai báo | Có giá trị mặc định dùng được? | Ví dụ |
| --- | --- | --- |
| Field instance `int x;` | Có | `0` |
| Field static `static int x;` | Có trong cơ chế chuẩn bị kiểu | `0` |
| Phần tử `new int[3]` | Có | Mỗi phần tử là `0` |
| Local `int x;` | **Không được đọc trước khi được gán chắc chắn** | Compiler từ chối |
| Tham số `void f(int x)` | Nhận giá trị do caller truyền | Không tự lấy 0 |

Không suy từ câu “Java có default values” thành “mọi biến Java tự có default value theo cách đọc được”.

## 5. Mảng cũng nhận mặc định, nhưng ở một giai đoạn tạo object khác

Khi viết `new int[3]`, Java tạo một **array object** với ba phần tử `int` mặc định 0. Nếu viết `new String[2]`, mỗi phần tử là một tham chiếu mặc định `null`. Điều này **khác** với field tham chiếu `int[]` chưa được gán, vốn là `null`.

Tạo tệp **`ArrayDefaultValuesDemo.java`**:

~~~java
import java.util.Arrays;

class Element {
    static {
        System.out.println("Element initialized");
    }

    Element() {
        System.out.println("Element constructed");
    }
}

public class ArrayDefaultValuesDemo {
    public static void main(String[] args) {
        int[] counts = new int[3];
        boolean[] checks = new boolean[2];
        String[] names = new String[2];

        System.out.println("counts=" + Arrays.toString(counts));
        System.out.println("checks=" + Arrays.toString(checks));
        System.out.println("names=" + Arrays.toString(names));

        Element[] elements = new Element[2];
        System.out.println("element slot=" + elements[0]);

        elements[0] = new Element();
        System.out.println("created=" + (elements[0] != null));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ArrayDefaultValuesDemo.java
java ArrayDefaultValuesDemo
~~~

**Stdout:**

~~~text
counts=[0, 0, 0]
checks=[false, false]
names=[null, null]
element slot=null
Element initialized
Element constructed
created=true
~~~

`new Element[2]` tạo **mảng tham chiếu**, không tạo hai object `Element` và không tự khởi tạo class `Element` chỉ vì có mảng chứa phần tử kiểu đó. Chỉ đến `new Element()` trong ví dụ, class `Element` mới cần initialization rồi constructor được gọi.

**Mặc định của phần tử mảng** là cơ chế áp dụng khi tạo object mảng, không đồng nghĩa chạy initializer trong class `Element`. Mảng `int[]` cũng không gọi constructor cho từng số nguyên.

## 6. `static` field: mặc định được thiết lập ở preparation

Với một class có field static:

~~~java
class GlobalConfig {
    static int retryCount = computeRetries();

    private static int computeRetries() {
        return 3;
    }
}
~~~

Đây là class minh họa hợp lệ. Khi class được **liên kết (linked)**, bước **preparation** chuẩn bị storage của `retryCount` và cho nó giá trị mặc định `0`; `computeRetries()` **chưa chạy vì riêng preparation**.

Khi class được **initialized**, phép tính `computeRetries()` mới được thực thi và kết quả gán vào `retryCount`. Một lần đọc `GlobalConfig.retryCount` từ bên ngoài là *active use* của nonconstant static field nên bình thường **kích hoạt initialization** trước khi trả giá trị. Do vậy caller thường đọc được 3 chứ không thấy 0.

~~~text
Loading / linking:
    retryCount = 0          (preparation)
    KHÔNG gọi computeRetries()

Initialization của GlobalConfig:
    chạy computeRetries() -> 3
    retryCount = 3

Sau initialization thành công:
    GlobalConfig.retryCount -> 3
~~~

Mô hình này giúp hiểu tại sao một static block có thể thấy giá trị mặc định của **static field ở phía dưới source** trong những tình huống được phép, nhưng **không** có nghĩa mọi lần đọc field từ lớp khác trước đó đều thấy 0.

## 7. Ví dụ chạy được: static initializer đọc field khai báo phía sau qua method

Tạo tệp **`StaticFieldOrderDemo.java`**:

~~~java
class StaticSequence {
    static int first = calculateFirst();

    static int second = 42;

    static {
        System.out.println("block second=" + second);
    }

    private static int calculateFirst() {
        System.out.println("during: second=" + second);
        return second + 5;
    }
}

public class StaticFieldOrderDemo {
    public static void main(String[] args) {
        System.out.println("before");
        System.out.println("first=" + StaticSequence.first);
        System.out.println("second=" + StaticSequence.second);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 StaticFieldOrderDemo.java
java StaticFieldOrderDemo
~~~

**Stdout chính xác:**

~~~text
before
during: second=0
block second=42
first=5
second=42
~~~

### Giải thích từng bước

1. `main` in `before`.
2. Truy cập `StaticSequence.first` đòi khởi tạo `StaticSequence`.
3. Trước các initializer, `first` và `second` đã có **giá trị mặc định 0** theo bước preparation.
4. Initializer của `first` chạy trước, gọi `calculateFirst()`.
5. `calculateFirst()` đọc field `second` thông qua phương thức — lúc này initializer `second = 42` **chưa chạy**, nên in `0` và trả `5`.
6. Java tiếp tục initializer `second = 42` rồi chạy static block, in `block second=42`.
7. `main` mới in `first=5` và `second=42`.

Đây là một **hiện tượng có thể quan sát giá trị mặc định trước initializer**. Nó không phải bảo đảm tốt cho thiết kế; nếu `first` thực sự cần `second = 42`, nên **đặt `second` trước `first`**, tính toán qua hằng số thích hợp hoặc tách logic khởi tạo rõ ràng.

## 8. Instance field: trước initializer cũng có giá trị mặc định

Với instance fields, cơ chế mặc định xảy ra **mỗi lần cấp phát object mới**. Các initializer được thực thi theo thứ tự textual tương ứng trong quá trình chạy constructor của lớp khai báo.

Tạo tệp **`InstanceFieldOrderDemo.java`**:

~~~java
class InstanceSequence {
    int first = calculateFirst();
    int second = 7;
    boolean ready = true;

    {
        System.out.println("block second=" + second
                + ", ready=" + ready);
    }

    private int calculateFirst() {
        System.out.println("during: second=" + second
                + ", ready=" + ready);
        return second + 5;
    }

    InstanceSequence() {
        System.out.println("constructor first=" + first
                + ", second=" + second
                + ", ready=" + ready);
    }
}

public class InstanceFieldOrderDemo {
    public static void main(String[] args) {
        System.out.println("before first");
        new InstanceSequence();
        System.out.println("before second");
        new InstanceSequence();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 InstanceFieldOrderDemo.java
java InstanceFieldOrderDemo
~~~

**Stdout:**

~~~text
before first
during: second=0, ready=false
block second=7, ready=true
constructor first=5, second=7, ready=true
before second
during: second=0, ready=false
block second=7, ready=true
constructor first=5, second=7, ready=true
~~~

### Tại sao lại đọc được 0 và false?

Sau khi object mới được cấp phát, các field của nó đã được đặt mặc định, bao gồm `second=0`, `ready=false`. Java thực thi initializer `first = calculateFirst()` **trước** khi đến hai initializer của `second` và `ready`. Method `calculateFirst()` vì thế nhìn thấy các giá trị mặc định và trả 5.

Khi initializer `second=7` và `ready=true` hoàn thành, instance initializer block và phần thân constructor nhìn thấy giá trị đã gán.

Khi tạo object thứ hai, toàn bộ **chuỗi instance initialization** diễn ra với một object mới, nên hiện tượng lặp lại. Điều này khác với static initialization chỉ thực hiện cho mỗi class runtime khi cần.

## 9. Quy tắc thứ tự theo source: field initializer xen kẽ initializer block

Trong một lớp, các **instance field initializers** và **instance initializer blocks** được thực thi theo thứ tự chúng xuất hiện trong source, tại giai đoạn khởi tạo instance của lớp đó. Tương tự, các **static field initializers** và **static initializer blocks** được thực thi theo thứ tự textual khi class được initialized.

Ví dụ:

~~~java
class OrderSketch {
    static int s1 = markStatic("s1");
    static {
        System.out.println("static block");
    }
    static int s2 = markStatic("s2");

    int x1 = markInstance("x1");
    {
        System.out.println("instance block");
    }
    int x2 = markInstance("x2");

    static int markStatic(String name) {
        System.out.println(name);
        return 1;
    }

    int markInstance(String name) {
        System.out.println(name);
        return 1;
    }
}
~~~

Đây là lớp minh họa hợp lệ (không có `main`). Khi class initialization xảy ra, nhóm static chạy theo thứ tự: `s1`, static block, `s2`. Khi tạo object, sau các bước superclass liên quan, nhóm instance chạy theo thứ tự `x1`, instance block, `x2`.

**Không có nguyên tắc “tất cả field initializer chạy trước tất cả initializer blocks”.** Chúng có thể **xen kẽ** theo văn bản nguồn. Đồng thời, static và instance là hai lịch trình khác nhau: `new OrderSketch()` lần thứ hai không làm chạy lại nhóm static.

Một instance field initializer có thể gọi method thường; khi method đọc field chưa được khởi tạo tường minh ở phía dưới, nó có thể quan sát mặc định như phần trước.

## 10. Forward reference: không phải mọi cách đọc field phía dưới đều hợp lệ

Java có quy tắc **illegal forward reference** ở [JLS §8.3.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3). Nếu một field được tham chiếu **bằng tên đơn giản** trong initializer cùng lớp trước khai báo thích hợp, compiler có thể từ chối.

Ví dụ **cố ý không biên dịch**:

~~~java
class BadStaticForward {
    static int first = second; // illegal forward reference
    static int second = 9;
}

class BadInstanceForward {
    int first = second; // illegal forward reference
    int second = 9;
}
~~~

Không nên hiểu “field có mặc định 0” thành “viết `first = second` trước khai báo `second` lúc nào cũng được”.

Ngược lại, trong `StaticFieldOrderDemo`, tên `second` nằm **trong phần thân method `calculateFirst()`**, không phải một tham chiếu trực tiếp bằng tên đơn giản ở field initializer bị hạn chế. Nó hợp lệ và có thể đọc 0 khi method được gọi quá sớm.

Một cách khác mà JLS không cấm theo đúng quy tắc **simple-name forward reference** là truy cập qua tên đã định danh rõ, ví dụ:

~~~java
class QualifiedStaticRead {
    static int before = QualifiedStaticRead.after;
    static int after = 9;
}

class QualifiedInstanceRead {
    int before = this.after;
    int after = 9;
}
~~~

Hai lớp trên **biên dịch được**. Trong trường hợp không có phép gán bất thường khác, `before` sẽ là 0 vì `after` chưa đến lượt initializer `= 9`.

**Cảnh báo về thiết kế:** khả năng vượt qua ràng buộc của tên đơn giản không có nghĩa nên cố tình dựa vào mặc định ở các tham chiếu sớm. Thứ tự trường có thể bị thay đổi khi refactor và gây lỗi khó nhận ra. Cách tốt hơn là **khởi tạo dependency trước khi field phụ thuộc nó**.

## 11. Kiểm tra bằng chương trình: qualified forward reference

Tạo tệp **`QualifiedForwardReferenceDemo.java`**:

~~~java
class QualifiedStatic {
    static int early = QualifiedStatic.later;
    static int later = 11;
}

class QualifiedInstance {
    int early = this.later;
    int later = 22;
}

public class QualifiedForwardReferenceDemo {
    public static void main(String[] args) {
        System.out.println("static early=" + QualifiedStatic.early);
        System.out.println("static later=" + QualifiedStatic.later);

        QualifiedInstance item = new QualifiedInstance();
        System.out.println("instance early=" + item.early);
        System.out.println("instance later=" + item.later);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 QualifiedForwardReferenceDemo.java
java QualifiedForwardReferenceDemo
~~~

**Stdout:**

~~~text
static early=0
static later=11
instance early=0
instance later=22
~~~

### Điều gì đáng nhớ?

- Trước static field initializers của `QualifiedStatic`, các field static chưa gán tường minh có mặc định 0.
- `QualifiedStatic.early = QualifiedStatic.later` đọc `later` khi nó còn 0, lưu giá trị đó vào `early`.
- Khi `later = 11` chạy, Java **không tự tính lại** `early`. Nó vẫn bằng 0.
- Với object `QualifiedInstance`, `this.later` cũng đọc mặc định 0 tại lượt initializer của `early`; sau đó `later` mới nhận 22.

Đây là ví dụ để **giải thích cơ chế**, không phải mẫu khuyến nghị. Trong hệ thống thực, hãy đảo thứ tự khai báo hoặc tính giá trị tại điểm đủ điều kiện để tránh phụ thuộc vào mặc định ngoài ý muốn.

## 12. Khi có superclass: object con đã có default fields trước constructor cha

Một cơ chế gây bất ngờ hơn: object của subclass được cấp phát với những field instance thuộc **cả superclass lẫn subclass** đã có giá trị mặc định. Trong quá trình khởi tạo, constructor của superclass chạy **trước khi** instance field initializers của subclass.

Nếu constructor của superclass gọi một method **có thể override**, Java dùng dynamic dispatch để gọi phiên bản override thuộc subclass. Nhưng các field của subclass có thể **vẫn đang ở giá trị mặc định**.

Tạo tệp **`ConstructorDispatchDefaultDemo.java`**:

~~~java
class BaseStage {
    BaseStage() {
        System.out.println("base constructor");
        describe();
    }

    void describe() {
        System.out.println("base describe");
    }
}

class DerivedStage extends BaseStage {
    private int value = 10;
    private String label = "ready";
    private boolean finished = true;

    {
        System.out.println("derived initializer=" + value
                + "/" + label + "/" + finished);
    }

    DerivedStage() {
        System.out.println("derived constructor=" + value
                + "/" + label + "/" + finished);
    }

    @Override
    void describe() {
        System.out.println("override=" + value
                + "/" + label + "/" + finished);
    }
}

public class ConstructorDispatchDefaultDemo {
    public static void main(String[] args) {
        new DerivedStage();
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 ConstructorDispatchDefaultDemo.java
java ConstructorDispatchDefaultDemo
~~~

**Stdout:**

~~~text
base constructor
override=0/null/false
derived initializer=10/ready/true
derived constructor=10/ready/true
~~~

Tại thời điểm `BaseStage()` gọi `describe()`, Java dispatch tới `DerivedStage.describe()` vì object thực sự có kiểu `DerivedStage`. Nhưng các initializer `value = 10`, `label = "ready"`, `finished = true` của subclass **chưa chạy**, nên method quan sát `0/null/false`.

Sau khi constructor cha hoàn thành, các initializer và initializer block của subclass chạy, rồi thân constructor subclass mới in các giá trị đã gán.

**Quy tắc thiết kế quan trọng:** tránh gọi những phương thức instance **có thể override** từ constructor, nhất là khi subclass có field phụ thuộc vào initializer. Tránh cả việc để `this` “thoát” ra callback hoặc luồng khác trước khi object khởi tạo xong.

## 13. Constructor chaining không chạy lặp lại default/initializer cho cùng object

Trong một class có nhiều constructor:

~~~java
class ChainSketch {
    int value = initialize();

    {
        System.out.println("instance block");
    }

    ChainSketch() {
        this("default");
        System.out.println("no-arg body");
    }

    ChainSketch(String name) {
        System.out.println("named body=" + name);
    }

    private int initialize() {
        System.out.println("field initializer");
        return 8;
    }
}
~~~

Đây là lớp minh họa hợp lệ. Constructor không tham số gọi `this("default")` đến constructor một tham số. Các initializer của class chỉ chạy **một lần cho một object**, theo cơ chế constructor chaining, không chạy riêng một lần cho mỗi thân constructor trong chuỗi.

Tạo tệp **`ConstructorChainOrderDemo.java`** với mã đầy đủ:

~~~java
class ChainSample {
    int number = announce();

    {
        System.out.println("instance block");
    }

    ChainSample() {
        this("default");
        System.out.println("no-arg constructor");
    }

    ChainSample(String name) {
        System.out.println("named constructor=" + name
                + ", number=" + number);
    }

    private int announce() {
        System.out.println("field initializer");
        return 8;
    }
}

public class ConstructorChainOrderDemo {
    public static void main(String[] args) {
        new ChainSample();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConstructorChainOrderDemo.java
java ConstructorChainOrderDemo
~~~

**Stdout:**

~~~text
field initializer
instance block
named constructor=default, number=8
no-arg constructor
~~~

Lúc đầu object được cấp phát và field `number` có mặc định 0, nhưng **không có code đọc nó ở giai đoạn đó**. Sau quá trình constructor superclass liên quan, initializer đặt `number=8` một lần; constructor nhận `name` và cuối cùng thân no-arg chạy.

**Không suy luận rằng** mỗi lệnh `this(...)` cấp phát thêm một object. Nó chỉ ủy quyền khởi tạo **cùng object** qua constructor khác trong lớp.

## 14. Phân biệt class initialization và object initialization

Có hai hệ thống thời điểm riêng:

| Đặc điểm | `static` field | Instance field |
| --- | --- | --- |
| Thuộc về | Class/interface runtime thích hợp | Mỗi object |
| Khi thiết lập mặc định | Linking/preparation cho class hoặc interface | Khi cấp phát object |
| Khi thực thi field initializer tường minh | Class/interface initialization | Trong chuỗi khởi tạo mỗi object |
| Tần suất sau thành công | Một lần cho mỗi runtime class được initialized | Mỗi object mới |
| Có `this` tại initializer? | Không | Có khi ở ngữ cảnh instance hợp lệ |
| Quan sát giá trị sớm | Phụ thuộc thứ tự static initialization | Phụ thuộc thứ tự object/superclass initialization |

Khi viết:

~~~java
new Example();
new Example();
~~~

trong một chương trình có định nghĩa `Example` tương ứng, class initialization có thể xảy ra trước lần tạo đầu. Sau đó **hai object** vẫn lần lượt trải qua instance default assignment, instance initializers và constructors của chúng.

**Loading và linking** không phải hai lần gọi constructor. Class initialization cũng không tạo một instance class chỉ vì có static block. Một constructor instance không tự được gọi bởi một static field initializer trừ khi biểu thức initializer thực sự sử dụng `new`.

## 15. Constant variables: ngoại lệ đặc biệt của `static final`

Một trường như:

~~~java
static final int CAPACITY = 32;
static final String LABEL = "ready";
~~~

là **constant variable** khi thỏa quy tắc kiểu (`String` hoặc primitive), `final` và initializer bằng **constant expression**. Java xử lý các trường ấy khác với nonconstant static fields:

- JLS mô tả chúng được gán giá trị constant **trước khi** các static field initializers/static blocks thông thường được xử lý trong class initialization.
- Bytecode dùng cơ chế `ConstantValue` phù hợp khi áp dụng.
- Một nơi dùng có thể nhận giá trị được **inline tại compile time**; chỉ đọc constant variable từ client **không bắt class khai báo initialized**.

Ngược lại:

~~~java
static final int COMPUTED = Integer.parseInt("32");
static final Integer WRAPPED = 32;
~~~

không phải *constant variable* theo cùng định nghĩa: `COMPUTED` gọi method, còn `WRAPPED` thuộc kiểu tham chiếu `Integer`, không phải `String`.

Đừng kết luận “mọi static field đều mặc định 0 rồi static block thấy 0” đối với một field **constant variable**. JLS bảo đảm việc xử lý constant values riêng; tham chiếu bằng tên đơn giản tới constant variable sẽ không quan sát giá trị mặc định trước khi được gán.

## 16. Ví dụ chạy được: constant so với nonconstant field

Tạo tệp **`ConstantVersusRuntimeDemo.java`**:

~~~java
class StaticConstants {
    static final int CAPACITY = 32;
    static final String LABEL = "ready";
    static final int COMPUTED = calculate();

    static {
        System.out.println("StaticConstants block");
    }

    private static int calculate() {
        System.out.println("calculating");
        return 33;
    }
}

public class ConstantVersusRuntimeDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        System.out.println("capacity=" + StaticConstants.CAPACITY);
        System.out.println("label=" + StaticConstants.LABEL);
        System.out.println("computed=" + StaticConstants.COMPUTED);
        System.out.println("again=" + StaticConstants.COMPUTED);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ConstantVersusRuntimeDemo.java
java ConstantVersusRuntimeDemo
~~~

**Stdout:**

~~~text
begin
capacity=32
label=ready
calculating
StaticConstants block
computed=33
again=33
~~~

Đọc `CAPACITY` và `LABEL` từ client không làm chạy `calculate()` hoặc static block vì đó là constant variables. Lần đầu đọc `COMPUTED` mới yêu cầu initialized `StaticConstants`, chạy initializer gọi method, rồi đến static block.

**Giới hạn:** kết luận này dựa trên **điều kiện của constant variable**, không đơn thuần do tên có chữ `final`. Trong các trường hợp phức tạp, hãy xét biểu thức initializer có phải constant expression theo JLS không.

## 17. `final` field cũng có giá trị mặc định về mặt cấp phát, nhưng compiler yêu cầu gán

Xét một **blank final instance field**:

~~~java
final class OrderId {
    private final String value;

    OrderId(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value không hợp lệ");
        }
        this.value = value;
    }

    String value() {
        return value;
    }
}
~~~

Đây là một lớp minh họa hợp lệ. Về mặt cấp phát object, trường tham chiếu có mặc định `null` trước quá trình constructor. Nhưng compiler áp dụng **definite assignment**: trên mọi đường constructor kết thúc bình thường, blank final instance field phải đã được gán đúng cách. Không thể bỏ qua `this.value = value;` rồi dựa vào `null` mặc định.

Tương tự, blank `static final` phải được gán đúng trong static initialization thích hợp; nó không thể cứ “mặc định 0” rồi được coi là đã hoàn thành nghĩa vụ của `final`.

**Phân biệt:**

- Giá trị mặc định là một phần của **khởi tạo storage**.
- `final` và definite assignment là **ràng buộc compile-time** về quyền và sự chắc chắn của phép gán.
- Invariant nghiệp vụ như ID không rỗng là **quy tắc ứng dụng** do constructor bảo vệ.

Không dựa vào giá trị mặc định để cố ý để trống field `final` sau khi tạo object thành công.

## 18. Tại sao thấy `null` trong constructor có thể nguy hiểm?

Một field tham chiếu `private Service service = createService();` có mặc định `null` trước khi `createService()` chạy. Nếu một callback hoặc method được gọi quá sớm trong quá trình khởi tạo object và cố dùng `service`, nó có thể gặp `NullPointerException`.

Ví dụ rủi ro đặc biệt là **superclass constructor gọi overridden method** như `ConstructorDispatchDefaultDemo`; overridden method của subclass có thể thấy field `null` rồi cố gọi method trên tham chiếu đó.

Những chiến lược an toàn:

1. Tránh gọi method có thể override từ constructor.
2. Không đăng ký `this` vào nơi có thể gọi lại khi chưa hoàn thành khởi tạo.
3. Tính toán các dependency bắt buộc bằng biến cục bộ trước khi lưu vào field.
4. Kiểm tra constructor parameters và invariant cần thiết.
5. Ưu tiên fields `final` cho reference ổn định khi thiết kế cho phép, nhưng không coi `final` là thuốc chữa mọi vấn đề.
6. Không tự nhiên thêm `if (service == null)` khắp nơi để che một thứ tự khởi tạo sai; hãy sửa kiến trúc khởi tạo nếu nguyên nhân là early exposure.

Việc Java bảo đảm field có mặc định `null` **ngăn dữ liệu rác không xác định**, nhưng bản thân `null` vẫn có thể là trạng thái không thể sử dụng theo nghiệp vụ.

## 19. Lỗi trước khi initializer hoàn thành có ảnh hưởng gì?

Giá trị mặc định không đảm bảo rằng **mọi initializer đều hoàn thành thành công**.

Với instance:

~~~java
class UnsafeInstance {
    int value = calculate();

    private int calculate() {
        throw new IllegalArgumentException("bad instance");
    }
}
~~~

Nếu `new UnsafeInstance()` khiến initializer ném exception, lời gọi tạo object không trả về một instance hoàn chỉnh cho caller. Class không nhất thiết trở thành không sử dụng được; caller có thể thử tạo object khác theo chính sách ứng dụng nếu nguyên nhân có thể thay đổi.

Với static:

~~~java
class UnsafeStatic {
    static int value = calculate();

    private static int calculate() {
        throw new IllegalStateException("bad static");
    }
}
~~~

Nếu lỗi không được xử lý xảy ra trong class initialization, JVM có cơ chế đánh dấu class ở trạng thái initialization thất bại. Những lần sử dụng class tiếp theo trong cùng định nghĩa runtime có thể thất bại thay vì tự chạy lại static initializer từ đầu.

**Không nên suy từ “field mặc định 0” rằng mọi trường hợp dùng class sau khi static initializer lỗi đều trả 0.** Class initialization có cơ chế lỗi đặc biệt; người gọi thông thường sẽ thấy `ExceptionInInitializerError` hoặc lỗi tương ứng, không được phép lặng lẽ bỏ qua initialization hỏng rồi lấy field chưa khởi tạo.

## 20. Static forward dependence và chu kỳ tham chiếu

Một thiết kế đáng tránh là **initializers phụ thuộc vòng nhau**:

~~~java
class CyclicSketch {
    static int left = calculateLeft();
    static int right = calculateRight();

    private static int calculateLeft() {
        return right + 1;
    }

    private static int calculateRight() {
        return left + 1;
    }
}
~~~

Đây là class minh họa hợp lệ. Khi class initialized:

1. `left` và `right` ban đầu có mặc định 0.
2. `left = calculateLeft()` thấy `right=0`, nên `left=1`.
3. `right = calculateRight()` thấy `left=1`, nên `right=2`.

Kết quả là `left=1` và `right=2`, nhưng người đọc rất dễ lầm tưởng hai phép tính tạo một hệ phương trình cần giải đồng thời. Java **không làm phép giải toán học đồng thời** cho field initializers; nó thực hiện **trình tự gán** theo chương trình.

Nếu dữ liệu có quan hệ hai chiều thật, hãy:

- Chọn một nguồn dữ liệu gốc và tính các giá trị từ nguồn đó.
- Dời các điều kiện phụ thuộc vào một bước tạo cấu hình có validation.
- Tránh gọi static methods từ initializer nếu methods vô tình đọc state đang được khởi tạo.
- Cẩn thận khi một static initializer tạo instance hoặc kích hoạt initialization của class khác cũng tham chiếu ngược lại.

Tình huống tương tự có thể xảy ra với instance field initializers; thay vì để chúng đọc nhau theo thứ tự ngẫu nhiên, hãy thiết kế dependency theo một hướng rõ ràng.

## 21. `this` thoát sớm và nhiều luồng

Khi constructor đưa `this` cho mã khác quá sớm — chẳng hạn đăng ký listener, chạy callback hoặc cho một thread khác giữ reference — object có thể bị quan sát **trước khi mọi instance initializer/constructor logic hoàn thành**. Điều đó không vi phạm nguyên tắc default value, nhưng thường vi phạm **invariant** mà tác giả class kỳ vọng.

Trong chương trình đa luồng, còn có khía cạnh **memory visibility**. Java Memory Model quy định các bảo đảm đặc biệt cho việc khởi tạo `final` fields đúng cách, nhưng không có nghĩa một reference bị công bố sai thời điểm sẽ tự an toàn.

Nên dùng cách tổ chức:

~~~text
1. Kiểm tra dữ liệu cần thiết.
2. Tạo object và hoàn tất các initializer/constructor.
3. Không cho callback hoặc thread khác quan sát "this" dở dang.
4. Công bố reference qua cơ chế thích hợp.
5. Nếu object mutable được chia sẻ, dùng synchronization/atomic/ownership.
~~~

Đối với static initialization, JVM phối hợp việc initialized class theo quy tắc đặc biệt. Nhưng **static field mutable vẫn có thể bị race sau initialization**, ví dụ `static int counter` dùng `counter++` từ nhiều thread.

Nhớ rằng các trường có giá trị mặc định không có nghĩa **đồng bộ hóa đa luồng được giải quyết**, vì những yêu cầu này nằm ở cấp độ khác.

## 22. Những nhầm lẫn phổ biến

| Phát biểu nhầm | Tại sao không đúng | Cách hiểu đúng |
| --- | --- | --- |
| “Java chỉ gán field khi gặp initializer.” | Field đã có mặc định trước đó | Initializer có thể **thay** giá trị mặc định |
| “`String` field tự là `""`.” | Reference mặc định `null` | Phải gán chuỗi rỗng nếu cần |
| “`int[]` field tự là mảng rỗng.” | Reference field mặc định `null` | `new int[0]` là phép tạo mảng riêng |
| “Local `int x;` tự đọc được 0.” | Local phải definite assigned | Gán trước khi đọc |
| “`static int x = f()` chạy ngay khi linking.” | Preparation không chạy initializer source | `f()` chạy khi class initialization |
| “Mọi lần đọc static field đều trả mặc định trước.” | Active use có thể trigger initialization | Client thường thấy giá trị sau init |
| “Field ở dòng dưới luôn đọc được bằng tên đơn giản.” | Illegal forward reference | Tuân JLS §8.3.3 |
| “Mọi cách đọc forward đều lỗi.” | Gọi method/qualified reference có trường hợp hợp lệ | Nhưng có thể đọc default không mong muốn |
| “`new T[5]` tạo năm object `T`.” | Chỉ tạo array tham chiếu | Các slot mặc định `null` |
| “`static final` lúc nào cũng chỉ bắt đầu từ 0.” | Constant variables được xử lý đặc biệt | Xét constant expression và JLS |
| “Superclass constructor thấy fields subclass đã init.” | Subclass initializers chạy sau | Virtual dispatch có thể đọc default |
| “Mỗi constructor trong chuỗi `this(...)` chạy initializer lại.” | Một object chỉ đi qua initializer tương ứng một lần | Chaining không cấp phát object mới |
| “`final` có thể để default mà không gán.” | Blank final chịu definite assignment | Phải gán đúng trên đường thành công |
| “Object đã có default thì không thể NPE.” | Reference default chính là null | Cần khởi tạo trước khi dùng |
| “Static init lỗi, đọc field sẽ còn giá trị mặc định.” | Runtime có cơ chế initialization failure | Không dựa vào state khởi tạo lỗi |
| “Default initialization giúp thread-safe.” | Mặc định không đồng nghĩa atomic/visibility | Thiết kế concurrency riêng |

**Câu hỏi chẩn đoán:** ở đúng thời điểm đang xét, field vừa mới nhận **mặc định**, đã được **initializer tường minh gán**, hay còn đang bị đọc qua một method chạy **quá sớm**?

## 23. Quy trình giải bài tập output theo thứ tự field initialization

Nếu một bài hỏi “chương trình in gì?”, đừng thử đoán từ thứ tự dòng `println` một cách tách rời. Làm theo quy trình:

1. **Tách field thành static và instance**, ghi rõ lớp khai báo chúng.
2. Với static, xác định **lần active use đầu tiên** đòi class initialization; xem các trường compile-time constant riêng.
3. Trước static initializers, đánh dấu các static fields thông thường ở giá trị mặc định theo preparation.
4. Chạy **static field initializers và static blocks theo thứ tự source** khi class initialized, ghi lại mọi lần method đọc field phía dưới.
5. Nếu tạo instance, mô hình cấp phát **tất cả instance fields ở mặc định** của object mới.
6. Đi theo chuỗi constructor superclass rồi subclass; kiểm tra có **virtual dispatch** từ constructor cha hay không.
7. Chạy các instance field initializers và initializer blocks của từng lớp theo thứ tự tương ứng, rồi chạy phần thân constructor.
8. Nếu constructor gọi `this(...)`, **không nhân đôi initializer** trong cùng object.
9. Mỗi lần gán field, cập nhật bảng giá trị; **không tự tính lại** field đã được gán trước đó.
10. Nếu thấy direct forward simple-name reference hoặc blank final field thiếu gán, xác định **lỗi biên dịch** thay vì cố tính stdout.
11. Nếu có exception trong initializer, phân tích **đường thất bại** trước khi tiếp tục các bước còn lại.

Bảng theo dõi ngắn cho `StaticFieldOrderDemo`:

| Thời điểm | `first` | `second` |
| --- | ---: | ---: |
| Sau preparation | 0 | 0 |
| `calculateFirst()` đang đọc `second` | Chưa nhận kết quả gán | 0 |
| Sau `first = calculateFirst()` | 5 | 0 |
| Sau `second = 42` | 5 | 42 |
| Sau static block | 5 | 42 |

Cách lập bảng theo thời gian thường giải thích output tốt hơn việc tưởng tượng Java “quay lại” gán các field cùng lúc.

## 24. Bài tập tự luyện

**Câu 1 — Default primitive.** Lớp có `int count;`, `boolean ready;`, `char mark;`. Sau `new` hợp lệ mà không có initializer, ba trường mang những giá trị gì?

**Câu 2 — Default reference.** `String title;`, `int[] scores;` sẽ là chuỗi rỗng và mảng rỗng hay là `null`?

**Câu 3 — Local variable.** Tại sao `int x; System.out.println(x);` trong một method không hợp lệ, trong khi `class A { int x; }` có thể đọc `new A().x`?

**Câu 4 — Instance order.** Với `int a = readB(); int b = 7;` và `readB()` trả `b+5`, giá trị `a` và `b` sau constructor là gì nếu không có phép gán khác?

**Câu 5 — Static order.** `static int first = readSecond(); static int second = 42;`. Nếu `readSecond()` trả `second`, giá trị của `first` sau class initialization là gì?

**Câu 6 — Forward reference.** Vì sao `static int a = b; static int b=1;` có thể không biên dịch? `static int a = Name.b; static int b=1;` (trong lớp `Name`) có giống không?

**Câu 7 — Mảng.** `new Student[3]` tạo bao nhiêu object `Student`? Ba phần tử của mảng có giá trị gì?

**Câu 8 — Superclass.** Constructor lớp cha gọi method override của lớp con, và method đọc field `String name = "An";` của lớp con. Tại thời điểm đó field có thể là gì? Cách phòng tránh?

**Câu 9 — Constructor chaining.** Constructor không tham số gọi `this("x")`. Field initializer của cùng class chạy mấy lần cho object ấy?

**Câu 10 — Constant variable.** `static final int A=20;` và `static final int B=Integer.parseInt("20");` khác nhau ra sao về việc đọc có thể kích hoạt initialization?

**Câu 11 — Blank final.** Có thể khai báo `final String code;` trong class rồi bỏ qua gán tại mọi constructor vì field tham chiếu đã mặc định null không?

**Câu 12 — Static failure.** Static initializer ném exception chưa xử lý. Lần đọc tiếp theo có được hứa rằng sẽ thấy 0 mặc định không?

**Câu 13 — Field dependency.** Nếu hai static fields phụ thuộc qua helper methods và đọc giá trị trước initializer, Java có tự giải một hệ phương trình để đưa ra giá trị cuối cùng không?

**Câu 14 — Concurrency.** Giá trị mặc định và static initialization theo JVM có tự làm phép `counter++` của static field an toàn giữa hai thread không?

### Đáp án và lời giải

1. `0`, `false`, ký tự mã `U+0000`.
2. Cả hai đều `null` vì chúng là reference fields; chưa tạo `String` hay array object nào.
3. Local variable phải được definite assigned trước khi đọc; field có default values do ngữ nghĩa khởi tạo object.
4. `a=5`, `b=7`: khi `readB()` chạy, `b` còn 0; gán `b=7` sau đó không tính lại `a`.
5. `first=0`, vì `second` mặc định 0 khi helper được gọi; sau đó `second` được gán 42.
6. Direct simple-name forward reference chịu quy tắc cấm của JLS; qualified name có thể hợp lệ và trong ví dụ đọc default 0, nhưng không nên dựa vào mẹo này.
7. Không có object `Student` nào được tạo chỉ bởi mảng; ba slot reference mặc định null.
8. Có thể là `null` vì subclass initializer chưa chạy; không gọi method overridable từ constructor superclass.
9. Một lần cho object đó; constructor chaining không tạo object mới và không chạy lại toàn bộ initializer ở mỗi tầng `this`.
10. `A` là constant variable nên việc đọc chỉ riêng nó không đòi initialized class; `B` không phải constant expression, đọc `B` sẽ yêu cầu initialization của lớp khai báo.
11. Không. Blank final field phải được gán hợp lệ trước khi mọi constructor kết thúc bình thường.
12. Không. Class initialization thất bại có cơ chế lỗi riêng; không được hứa trả giá trị mặc định.
13. Không. Java thực thi field initializers theo thứ tự, dùng trạng thái hiện có ở lúc đọc; các giá trị đã gán không tự tính lại.
14. Không. Bảo đảm khởi tạo và thread safety cho các cập nhật mutable sau đó là hai vấn đề khác nhau.

## 25. Nguồn tham khảo Java 17

- [JLS §4.12.5 — Initial Values of Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.5): giá trị mặc định của field và phần tử mảng.
- [JLS §8.3.2 — Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): initializer của instance/static field và thời điểm thực hiện.
- [JLS §8.3.3 — Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3): illegal forward reference và simple-name restrictions.
- [JLS §8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): instance initializer blocks.
- [JLS §8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): static initializer blocks.
- [JLS §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): active use, constant fields và thứ tự static initialization.
- [JLS §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): cấp phát object, mặc định của instance fields và thứ tự constructor/initializers.
- [JLS §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): khác biệt về đọc biến cục bộ và blank final fields.
- [JVMS §5.4.2 — Preparation](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.2): static fields được cấp phát và gán mặc định trong linking.
- [JVMS §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): class initialization và cơ chế gán constant values.
- [JVMS §4.7.2 — ConstantValue Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2): cách biểu diễn hằng số được gán trước phần mã class initialization thông thường.

**Kết luận:** Trước khi field initializer tường minh chạy, Java đã thiết lập **giá trị mặc định** cho instance fields khi cấp phát object và cho static fields trong preparation của class. Initializers sau đó **ghi đè theo thứ tự**; những lần đọc qua phương thức, qualified forward reference hoặc dynamic dispatch quá sớm có thể thấy 0/false/null. Quy tắc này **không áp dụng theo cùng cách cho local variables**, không cho phép bỏ qua definite assignment của blank `final`, và không thay thế validation hay an toàn đồng thời. Thiết kế tốt là làm các dependency rõ ràng, khởi tạo chúng đúng thứ tự và không công bố object trước khi hoàn thành.
