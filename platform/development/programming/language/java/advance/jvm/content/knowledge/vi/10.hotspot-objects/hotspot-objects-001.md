# Chuỗi tạo đối tượng trong HotSpot: cấp phát, giá trị mặc định và chạy constructor

## Mục tiêu

Biểu thức `new Person("Lan")` chứa nhiều hoạt động khác nhau: kiểm tra và khởi tạo class nếu cần, cấp phát một **instance** có đủ các fields, đặt chúng về **default values**, đánh giá các đối số constructor, rồi gọi phương thức đặc biệt **`<init>`**. Constructor không phải hàm cấp phát bộ nhớ: khi constructor bắt đầu chạy, instance và các trường mặc định đã tồn tại về mặt ngữ nghĩa.

Sau bài học bạn có thể:
- Mô tả trình tự tạo class instance theo **JLS `15.9.4, `12.5** và lệnh **`new`** theo JVMS.
- Phân biệt **`<clinit>` của class** với **`<init>` của từng instance**, default fields và explicit initializers.
- Hiểu thứ tự constructor superclass/subclass, `this(...)`, `super(...)`, field initializer, instance initializer block và constructor body.
- Giải thích vì sao constructor superclass có thể nhìn thấy field subclass bằng 0/null dù source khai báo giá trị khác.
- Nhận biết cơ chế cấp phát riêng của **HotSpot** như TLAB, đường cấp phát nhanh/chậm, zeroing, object header, alignment, compressed oops và ảnh hưởng của JIT.
- Phân biệt tạo object từ `new` với tạo mảng qua `newarray`, `anewarray`, `multianewarray`.
- Đọc bytecode bằng `javap`, giải thích `new`, `dup`, `invokespecial` và rủi ro constructor thất bại hoặc `this` bị publish quá sớm.

## 1. Chuỗi tạo đối tượng theo ngữ nghĩa Java và JVM

Một biểu thức Java:

~~~java
Person person = new Person("Lan");
~~~

Đây là snippet minh họa, cần có class `Person` và constructor phù hợp để biên dịch.

Sơ đồ khái niệm:

~~~text
new Person("Lan")
      |
      v
Resolve class; class initialization nếu chưa được thực hiện
      |
      v
Cấp phát class instance (bao gồm fields của superclasses)
      |
      v
Thiết lập default values cho TẤT CẢ instance fields
      |
      v
Đánh giá constructor arguments từ trái sang phải
      |
      v
Chạy instance initialization method <init>:
  constructor chain -> superclass trước, subclass sau
  field initializers và instance blocks của từng class
  statements trong constructor body
      |
      v
Nếu thành công -> trả reference tới object mới
Nếu lỗi -> hoàn tất abruptly / ném exception
~~~

**Thứ tự quan trọng:** theo **JLS `15.9.4**, đối với class instance creation expression thông thường, bước **cấp phát và thiết lập default fields xảy ra trước đánh giá các actual constructor arguments**. Arguments được đánh giá **từ trái sang phải** rồi mới gọi constructor được chọn. Với qualified inner-class creation, qualifying expression còn phải được đánh giá trước, theo quy tắc riêng.

Bytecode `new` yêu cầu class được resolve/initialized theo JVMS nếu cần trước khi tiếp tục tạo instance. Khi class đã được initialized từ trước, JVM **không chạy lại class initializer** cho từng phép `new`.

Bảng phân biệt:

| Hoạt động | JVM/JLS bảo đảm gì? | Triển khai HotSpot có thể làm gì? |
| --- | --- | --- |
| Class resolution/initialization | Class hợp lệ được resolve và initialized khi cần theo quy tắc `new` | Kiểm tra metadata class, class-init fast path |
| Allocation | Instance mới về mặt ngữ nghĩa, chứa các inherited/declared instance fields | Cấp phát nhanh từ TLAB hoặc đi slow path |
| Default initialization | Số nguyên 0, boolean false, floating-point +0.0, char NUL, reference null | Zeroing/khai thác vùng đã được zero |
| Object metadata | VM biết runtime type/identity để thao tác với instance | Ghi header, Klass metadata, căn chỉnh theo cấu hình |
| Constructor | Chạy chuỗi `<init>` và initializer đúng thứ tự | Interpreter/JIT, có thể inline các lời gọi |
| Kết quả biểu thức | Reference nếu hoàn tất thành công | Representation reference do VM quyết định |

Sơ đồ là **mô hình ngữ nghĩa**, không phải danh sách lệnh CPU bắt buộc; optimizer chỉ được thay đổi cách thực hiện khi không làm sai hành vi Java quan sát được.

## 2. Class initialization khác instance initialization

**`<clinit>`** là phương thức đặc biệt cho **class/interface initialization**, liên quan static initializers. **`<init>`** là tên JVM dành cho **constructor/instance initialization methods**. Chúng không thay thế nhau.

~~~java
class Counter {
    static int total = 10;
    int value = 5;

    Counter() {
        total++;
    }
}
~~~

Đây là class minh họa, chưa có `main`. Nếu `Counter` chưa được initialized, lần `new Counter()` có thể kích hoạt quy trình class initialization để static field `total` nhận giá trị 10. Sau đó **mỗi** lần tạo một Counter instance:
1. Object nhận default `value=0` sau allocation.
2. Chạy initializer `value=5` và constructor body tăng `total`.
3. Class initializer **không chạy lại** cho instance thứ hai.

| Thuật ngữ | Nội dung | Tần suất theo semantics |
| --- | --- | --- |
| **Class preparation** | Trong linking, tạo static fields và default values | Cho class/interface runtime được link |
| **Class initialization** | Gán ConstantValue và chạy `<clinit>` nếu có | Theo quy tắc class-init, không phải mỗi object |
| **Object allocation** | Tạo một instance mới | Mỗi evaluation `new` về mặt ngữ nghĩa |
| **Object default initialization** | Thiết lập toàn bộ instance fields về default | Cho instance mới |
| **Instance initialization** | Chuỗi constructor `<init>` và field/block initializers | Cho instance đang tạo |

Không nhầm **class preparation** (tạo static fields của class) với việc cấp phát **instance fields** của một object.

## 3. Default values có trước các explicit field initializers

Khi cấp phát instance, JVM tạo trạng thái gồm mọi instance fields thuộc class được tạo và các superclasses, kể cả các field bị hide. Chúng nhận giá trị mặc định, không phải giá trị source khai báo sau dấu `=`.

| Instance field | Default sau allocation |
| --- | --- |
| `byte`, `short`, `int`, `long` | 0 tương ứng kiểu |
| `float` | +0.0f |
| `double` | +0.0d |
| `boolean` | false |
| `char` | NUL, code unit 0 (`'\u0000'`) |
| `String`, class/interface reference | null |
| `int[]` hoặc reference đến mảng | null |

Ví dụ:

~~~java
class Data {
    int count = 7;
    String label = "ready";
    int[] numbers = new int[3];
}
~~~

Đây là class minh họa. **Ngay sau object allocation** và trước các explicit instance initializers: `count=0`, `label=null`, `numbers=null`. Sau khi các initializer thực thi trong constructor chain: `count=7`, `label` trỏ đến String, `numbers` trỏ đến array mới có ba int elements bằng 0.

Không cần `javac` sinh bytecode gán 0/null cho từng field. Hoạt động bảo đảm default values do VM thực hiện. Giá trị `'\u0000'` khác ký tự số `'0'`; reference null cũng khác object String rỗng.

### Hidden fields không biến mất

~~~java
class A { int id = 1; }
class B extends A { int id = 2; }
~~~

Class B instance có **cả A.id và B.id** như hai fields riêng. Mỗi field đều nhận default 0 khi allocation, rồi initializer của declaring class được chạy theo constructor chain. Đây là field *hiding*, không phải overriding field.

## 4. Constructor chain: superclasses trước, subclass sau

Đối với Java 17 và constructor bình thường, tiến trình initialization mang ý nghĩa:

~~~text
Object.<init>()
       |
       v
Base instance field initializers + instance blocks
       |
       v
Base constructor body
       |
       v
Derived instance field initializers + instance blocks
       |
       v
Derived constructor body
~~~

Các field initializers và instance initializer blocks của **cùng một class** được thực hiện theo **thứ tự xuất hiện trong source**. Constructor có thể gọi `this(...)` để delegate sang constructor khác trong cùng class hoặc `super(...)` để gọi superclass constructor. Nếu không ghi explicit invocation, compiler thêm lời gọi superclass constructor mặc định theo quy tắc Java khi hợp lệ.

**Quan trọng:** Java 17 đòi explicit constructor invocation kiểu `this(...)`/`super(...)` ở đầu constructor tương ứng theo quy tắc phiên bản này; không trộn những cú pháp linh hoạt hơn của các JDK tương lai vào ví dụ Java 17.

### Chương trình chạy được: thấy field subclass còn mặc định

Tạo **`CreationOrderDemo.java`**:

~~~java
public class CreationOrderDemo {
    static int trace(String label, int value) {
        System.out.println(label + "=" + value);
        return value;
    }

    static class Base {
        int baseValue = trace("Base.field", 10);

        {
            System.out.println("Base.block=" + baseValue);
        }

        Base() {
            System.out.println(
                    "Base.constructor childValue=" +
                    ((Child) this).childValue);
        }
    }

    static final class Child extends Base {
        static {
            System.out.println("Child.<clinit>");
        }

        int childValue = trace("Child.field", 20);

        {
            System.out.println("Child.block=" + childValue);
        }

        Child() {
            System.out.println("Child.constructor=" + childValue);
        }
    }

    public static void main(String[] args) {
        System.out.println("main");
        Child c = new Child();
        System.out.println("after=" + c.baseValue + "," + c.childValue);
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac --release 17 CreationOrderDemo.java
java CreationOrderDemo
~~~

**Stdout chính xác:**

~~~text
main
Child.<clinit>
Base.field=10
Base.block=10
Base.constructor childValue=0
Child.field=20
Child.block=20
Child.constructor=20
after=10,20
~~~

**Diễn giải:**
1. `main` của outer class in `main`. Khi JVM cần tạo Child đầu tiên, static initializer của Child in `Child.<clinit>`.
2. Instance Child được tạo với field `Base.baseValue` **và** `Child.childValue` đã có nhưng đều bằng 0.
3. Constructor Child dẫn tới Base constructor. Sau phần gọi `Object.<init>`, Base initializer gán 10 và in hai dòng tương ứng.
4. **Trong Base constructor body**, Child field initializer chưa chạy, nên `((Child)this).childValue` vẫn là 0.
5. Sau khi Base constructor hoàn tất, Child initializer gán 20, block in 20, Child constructor body in 20.
6. Sau toàn bộ chuỗi, expression `new Child()` trả reference; dòng cuối in `after=10,20`.

Cast trong ví dụ an toàn vì object thực sự là Child. Tuy nhiên, **superclass constructor đọc trạng thái subclass** là cách thiết kế không nên lạm dụng. Đặc biệt, gọi một method có thể override từ superclass constructor có thể dispatch tới subclass method trước khi subclass fields được initialize, dẫn đến thấy 0/null hoặc gây `NullPointerException`.

### Virtual dispatch vẫn hoạt động trong constructor

~~~java
class Parent {
    Parent() {
        onReady();
    }

    void onReady() {}
}

class Child extends Parent {
    String name = "ready";

    @Override
    void onReady() {
        System.out.println(name);
    }
}
~~~

Đây là **class minh họa**. Khi tạo Child, `Parent()` có thể gọi method override `Child.onReady()` trước khi `Child.name` được gán "ready", vì object đã có runtime type Child. Khi đó có thể in `null`. Không nên gọi method overridable từ constructor base trừ khi thực sự hiểu và kiểm soát hệ quả.

## 5. Gọi `this(...)` không tạo thêm object

Constructor delegation sang overload không phải biểu thức `new` mới và không làm field initializers của class chạy lặp lại.

Tạo file **`ConstructorChainDemo.java`**:

~~~java
public class ConstructorChainDemo {
    static class Parent {
        Parent() {
            System.out.println("Parent()");
        }
    }

    static final class Child extends Parent {
        int value = initializeValue();

        {
            System.out.println("Child.block");
        }

        Child() {
            this(7);
            System.out.println("Child()");
        }

        Child(int requested) {
            System.out.println("Child(int)=" + requested);
        }

        int initializeValue() {
            System.out.println("Child.field");
            return 2;
        }
    }

    public static void main(String[] args) {
        Child c = new Child();
        System.out.println("value=" + c.value);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ConstructorChainDemo.java
java ConstructorChainDemo
~~~

**Stdout chính xác:**

~~~text
Parent()
Child.field
Child.block
Child(int)=7
Child()
value=2
~~~

`Child()` delegate tới `Child(int)`. Constructor đích xử lý chuỗi superclass; rồi Child field initializer/block được thực hiện **một lần**, sau đó thân `Child(int)` chạy và cuối cùng quay lại phần còn lại của `Child()`. Không có thêm Child instance được cấp phát do `this(7)`.

## 6. Bytecode của object creation: `new` không trực tiếp chạy `<init>`

Ví dụ một phương thức trong class (snippet minh họa):

~~~java
static Box create() {
    return new Box(5);
}
~~~

Giả sử có class Box với constructor nhận int. Bytecode từ `javac` thường có dạng:

~~~text
new           #N   // class Box
dup
iconst_5
invokespecial #M   // Method Box."<init>":(I)V
areturn
~~~

Đây là **mẫu minh họa**, không phải dump exact với offset/index bắt buộc. Mô hình operand stack:

| Instruction | Stack sau lệnh (từ đáy đến đỉnh) |
| --- | --- |
| `new #N` | `[uninitializedRef]` |
| `dup` | `[uninitializedRef, uninitializedRef]` |
| `iconst_5` | `[uninitializedRef, uninitializedRef, 5]` |
| `invokespecial #M` | `[initializedRef]` nếu constructor thành công |
| `areturn` | Trả reference cho caller |

Instruction `new` sử dụng constant pool entry xác định class được tạo, có thể làm class resolution/initialization nếu cần. `invokespecial` gọi instance initialization method `<init>`, với receiver và arguments có kiểu phù hợp.

**Verifier phân biệt uninitialized reference với reference đã hoàn tất constructor** để ngăn bytecode tùy ý sử dụng đối tượng trước khi initialized. Dù object đã có storage, không thể giả định mọi bytecode thao tác hợp lệ trên receiver chưa gọi `<init>`.

### Dùng javap kiểm chứng

Sau khi biên dịch:

~~~bash
javap -c -p CreationOrderDemo
javap -c -p 'CreationOrderDemo$Base'
javap -c -p 'CreationOrderDemo$Child'
javap -v -p 'CreationOrderDemo$Child'
~~~

Quan sát:
- `main` chứa `new`, `dup`, `invokespecial <init>` khi tạo Child.
- `Child.<init>` gọi `Base.<init>` trước các phép gán vào `childValue`.
- `Base.<init>` gọi `Object.<init>`, tiếp theo là initializer `baseValue`, instance block và constructor body.
- `Child.<clinit>` chứa static block, tách biệt với `Child.<init>`.
- Lệnh `putfield` gán 10/20 đến từ **explicit field initializers**; không cần có những lệnh gán default 0 do compiler sinh.

Chỉ số `#N`, bytecode offset và cách ghép chuỗi trong lệnh in có thể khác giữa compiler/JDK. Trên Windows cmd.exe có thể dùng tên class chứa dấu `$` trực tiếp; trên Bash/PowerShell, quote đơn như ví dụ ngăn shell diễn giải ký tự đặc biệt.

## 7. Cơ chế cấp phát riêng của HotSpot: TLAB và đường chậm

**Thread-Local Allocation Buffer (TLAB)** là một vùng **trong heap** mà HotSpot có thể dùng cho cấp phát object nhanh của một thread. Tên có chữ “thread-local” **không có nghĩa object nằm trên thread stack**; object được cấp vào TLAB vẫn là heap object và có thể chia sẻ sau đó.

Sơ đồ:

~~~text
Java heap / allocation region
    |
    +-- TLAB thread A: [start ... top ---> ... end]
    |
    +-- TLAB thread B: [start ... top ---> ... end]
    |
    +-- shared / slow allocation path nếu cần
~~~

Đường cấp phát nhanh có thể:
1. Xác định kích thước instance sau khi xét header, fields và alignment.
2. Kiểm tra `top + size` còn nằm trong giới hạn của TLAB không.
3. Nếu đủ, bump-pointer tăng top và nhận vùng chứa object.
4. Chuẩn bị header và default fields theo semantics.
5. Sau đó thực hiện instance constructor initialization.

Nếu không có TLAB phù hợp, object quá lớn hoặc vùng hiện tại không đủ, HotSpot đi **slow path** để thử refill TLAB, cấp phát bằng con đường khác hoặc kích hoạt các hoạt động GC; nếu thất bại có thể báo `OutOfMemoryError`.

Không khẳng định **mọi** HotSpot object đều cấp từ Eden/TLAB hoặc mọi GC dùng cùng chiến lược. Collector, architecture, JVM flags, size class và JDK version quyết định chi tiết.

### Zeroing không phải chạy constructor

Một cách hiện thực default fields là **zeroing bộ nhớ**; JVM cũng có thể dùng vùng đã zero hoặc tối ưu hóa các thao tác ghi mặc định không cần thiết. Nhưng kết quả Java phải tương đương các fields có default values **trước** phần code được phép quan sát chúng.

**Header không phải toàn bộ bit zero:** object header cần chứa thông tin runtime. Do đó nói “JVM zero mọi byte của object, kể cả header, rồi mới chạy code” như một quy tắc bất biến là không chính xác.

## 8. Object header, field layout và alignment

HotSpot thường phải quản lý:
- Metadata trong **object header** về object state/lock/GC theo chế độ phù hợp.
- Thông tin kiểu runtime qua **Klass metadata/pointer** hoặc cách mã hóa tương ứng.
- **Instance fields** của class và superclasses.
- **Padding/alignment** để tuân thủ điều kiện cấp phát.
- Với arrays, thông tin **array length** và vùng chứa elements.

Sơ đồ minh họa:

~~~text
[header / runtime metadata]
[Klass information nếu layout cần]
[instance fields của superclasses và class hiện tại]
[padding / alignment nếu có]
~~~

Đây **không phải layout tuyệt đối**. Kích thước header, vị trí field, compressed object pointers (compressed oops), compressed class pointers và các hình thức **compact object headers** phụ thuộc HotSpot version/options/platform. Không dạy cố định “mọi object 12 byte header” hoặc “reference luôn là địa chỉ máy 64 bit thô”.

Một class chỉ có `byte value` không có nghĩa object thực tế chiếm đúng 1 byte; còn header, padding và thừa kế. Để đo heap layout thực tế trên một JDK cụ thể, có thể dùng công cụ như Java Object Layout/JOL phiên bản phù hợp, ghi rõ môi trường và JVM flags. Kết quả phép đo **không phải** một phần của Java Language Specification.

## 9. Đánh giá constructor arguments và lỗi giữa các bước

Theo JLS `15.9.4, **allocation của class instance diễn ra trước khi arguments được đánh giá** (đối với biểu thức tạo class instance thông thường). Arguments sau đó được đánh giá trái sang phải.

Tạo file **`ArgumentOrderDemo.java`**:

~~~java
public class ArgumentOrderDemo {
    static int value(String label, int result) {
        System.out.println(label);
        return result;
    }

    static class Point {
        Point(int x, int y) {
            System.out.println("constructor=" + x + "," + y);
        }
    }

    public static void main(String[] args) {
        System.out.println("begin");
        new Point(value("arg1", 1), value("arg2", 2));
        System.out.println("end");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ArgumentOrderDemo.java
java ArgumentOrderDemo
~~~

**Stdout chính xác:**

~~~text
begin
arg1
arg2
constructor=1,2
end
~~~

Stdout minh họa thứ tự **side effects trong argument evaluation và constructor body**. Nó không đo trực tiếp thời điểm VM cấp phát bộ nhớ vì allocation thông thường không in gì. Nếu argument đầu ném exception, những arguments phía sau không được đánh giá và constructor body không chạy; biểu thức `new` không trả kết quả bình thường.

**OutOfMemoryError:** nếu allocation không thể thực hiện, biểu thức có thể ném OOME. JLS có quy định thứ tự kiểm tra OOME trước việc đánh giá argument của class instance creation. Không nên dùng thử nghiệm thiếu heap như một test có stdout ổn định vì OOME và GC phụ thuộc runtime/memory pressure.

## 10. Khi constructor ném exception

Constructor có thể kết thúc bất thường sau khi đã thực hiện một số side effects. Khi đó biểu thức `new` **không trả reference bình thường**, nhưng không có cơ chế “rollback mọi side effects”.

Tạo tệp **`ConstructorFailureDemo.java`**:

~~~java
public class ConstructorFailureDemo {
    static int attempts;

    static class Fragile {
        int value = 5;

        Fragile() {
            attempts++;
            System.out.println("constructor value=" + value);
            throw new IllegalStateException("failed");
        }
    }

    public static void main(String[] args) {
        try {
            Fragile f = new Fragile();
            System.out.println(f.value);
        } catch (IllegalStateException expected) {
            System.out.println("caught=" + expected.getMessage());
        }

        System.out.println("attempts=" + attempts);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ConstructorFailureDemo.java
java ConstructorFailureDemo
~~~

**Stdout chính xác:**

~~~text
constructor value=5
caught=failed
attempts=1
~~~

Field initializer `value=5` đã chạy trước thân constructor. Constructor tăng static counter rồi ném exception; kết quả `new` hoàn tất abruptly, còn `attempts=1` chứng minh side effect không tự bị hoàn tác. Nếu không có reference nào thoát ra, object không còn cần thiết có thể được GC thu hồi theo thời điểm VM quyết định.

### Tránh để `this` thoát khỏi constructor

~~~java
class UnsafePublication {
    static UnsafePublication leaked;
    final String label;

    UnsafePublication() {
        leaked = this;
        label = "ready";
    }
}
~~~

Đây là **ví dụ anti-pattern**, không phải khuyến nghị. Việc đưa `this` vào static field, listener, thread khác hoặc collection chia sẻ trước khi constructor hoàn tất có thể làm object bị quan sát ở trạng thái partially initialized và tạo rủi ro Java Memory Model, nhất là khi publication không có synchronization.

**Nguyên tắc:** hoàn thành constructor trước khi publish reference; dùng cơ chế safe publication phù hợp như synchronized/volatile/concurrent collections hoặc thread-safe factory. Không gọi virtual overridable method từ constructor nếu method đó cần subclass state đã khởi tạo.

## 11. Arrays: cấp phát và default elements, không chạy constructor phần tử

| Java source | Opcode JVM thường gặp | Hành vi |
| --- | --- | --- |
| `new int[3]` | `newarray int` | Một int[] object, ba primitive values 0 |
| `new Item[2]` | `anewarray Item` | Một Item[] object, hai references null |
| `new int[2][3]` | `multianewarray [[I, 2` | Outer array và inner arrays của các chiều chỉ định |
| `new int[2][]` | `anewarray [I` hoặc instruction tương đương | Outer array, hai slots null |

Mảng là object trong heap theo JVM. Tuy nhiên **`new Item[2]` không gọi constructor Item hai lần**, vì các phần tử ban đầu chỉ là reference values null.

Ví dụ chạy được **`ArrayBirthDemo.java`**:

~~~java
import java.util.Arrays;

public class ArrayBirthDemo {
    static final class Item {
        int count = 7;
    }

    public static void main(String[] args) {
        int[] numbers = new int[3];
        Item[] items = new Item[2];
        int[][] matrix = new int[2][3];

        System.out.println("numbers=" + Arrays.toString(numbers));
        System.out.println("items[0]=" + items[0]);
        System.out.println("matrixRows=" + matrix.length);
        System.out.println("matrixCols=" + matrix[0].length);

        items[0] = new Item();
        System.out.println("itemCount=" + items[0].count);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 ArrayBirthDemo.java
java ArrayBirthDemo
~~~

**Stdout chính xác:**

~~~text
numbers=[0, 0, 0]
items[0]=null
matrixRows=2
matrixCols=3
itemCount=7
~~~

**Mảng có quy tắc lỗi riêng:** dimension âm gây `NegativeArraySizeException`; thiếu bộ nhớ có thể gây OOME. Thứ tự đánh giá dimension expressions của array trong JLS `15.10.2 **khác** thứ tự allocation/arguments của class instance creation ở `15.9.4, không áp một công thức cho cả hai.

## 12. JIT escape analysis, GC và reference value

Ở cấp Java, `new` tạo class instance mới về mặt ngữ nghĩa. Nhưng HotSpot JIT có thể tối ưu **object allocation vật lý** khi chứng minh object không escape và thay đổi này bảo toàn mọi hành vi quan sát được.

~~~java
static int total(int a, int b) {
    Pair p = new Pair(a, b);
    return p.first + p.second;
}
~~~

Đây là snippet minh họa, cần có class `Pair` với các fields thích hợp. JVM có thể dùng **scalar replacement** để thay object bằng các giá trị field riêng nếu điều kiện phù hợp. Không thể khẳng định bất kỳ lệnh `new` nào cũng chắc chắn có một khối RAM heap riêng trên mọi JIT run; ngược lại cũng không khẳng định **mọi object nhỏ được cấp trên stack**.

Khi một method kết thúc:
- Frame/local variables có thể không còn tồn tại theo mô hình stack.
- Object vẫn có thể reachable từ caller, static fields, những object khác hoặc GC roots thích hợp.
- GC có thể thu hồi object không còn reachable **vào thời điểm không xác định**, không nhất thiết đúng lúc constructor/body method return.
- TLAB là vùng heap hỗ trợ cấp phát, **không phải cơ chế tự dọn toàn bộ objects khi thread chết**.

Một object đã hoàn tất constructor cũng cần được **publish an toàn** nếu chia sẻ qua thread khác. Default initialization và constructor completion không biến mọi thao tác concurrent thành thread-safe.

## 13. Lỗi thường gặp và cách phân tích

| Triệu chứng / nhận định | Phân tích chính xác |
| --- | --- |
| “`new` chính là constructor.” | `new` cấp phát object; `invokespecial <init>` dùng để instance initialization. |
| “Field `int x=7` nhận 7 ngay trong allocation.” | Default 0 có trước; field initializer gán 7 trong chuỗi constructor. |
| “Child field phải là 20 khi Base constructor đang chạy.” | Child explicit initializer chưa chạy; Base có thể quan sát default 0. |
| “Constructor gọi `this(...)` nghĩa là một object thứ hai được tạo.” | Delegation trên cùng một object; không có `new` thứ hai chỉ bởi `this(...)`. |
| “Static block chạy mỗi lần tạo instance.” | Class initializer theo quy tắc class lifecycle, không phải mỗi object. |
| “Header của mọi HotSpot object có kích thước cố định.” | Phụ thuộc JVM version/flags/architecture, có thể có compact headers. |
| “TLAB là thread stack allocation.” | TLAB ở heap; object có thể escape và sống sau thread. |
| “Cứ có `new` là chắc chắn thấy một allocation trên profiler.” | JIT có thể loại bỏ allocation không quan sát được. |
| “Nếu constructor ném exception, mọi side effects rollback.” | Side effects không tự rollback; new hoàn tất abruptly. |
| “Array reference slots tự tạo các phần tử class.” | Reference elements nhận null, phải tạo object phần tử riêng. |
| “Class chưa init sẽ chạy constructor trước static initializer.” | Class initialization nếu cần được bảo đảm theo quy tắc `new` trước tạo instance. |
| “`new int[-1]` gọi một constructor mảng.” | Không có constructor array Java kiểu đó; NegativeArraySizeException. |
| “Một object tự nhiên thread-safe vì memory đã zero.” | Default values không bảo đảm safe publication/thread-safety. |

### Lộ trình chẩn đoán lỗi tạo object

1. **Resolution/loading:** class có đúng JAR/module, class loader và binary compatibility không?
2. **Class initialization:** static initializer ném exception không? Xem `ExceptionInInitializerError` và nguyên nhân.
3. **Allocation:** thiếu heap/GC pressure, `OutOfMemoryError`? Đo thay vì suy đoán.
4. **Argument evaluation:** actual argument ném exception trước constructor body?
5. **Constructor chain:** exception ở superclass initializer, instance initializer hay constructor body?
6. **Publication:** object bị lộ sớm/được chia sẻ giữa threads mà thiếu happens-before?
7. **Performance:** đang đo JIT warmup/GC/TLAB hay allocation logic? Tránh gán một kết quả profiler cho mọi JDK.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Khi nào instance fields nhận default values?

**Đáp án:** Sau allocation, **trước** constructor arguments evaluation và constructor initialization theo JLS `15.9.4 đối với class instance creation thông thường.

**Câu 2.** `new` có trực tiếp thực thi `<init>` không?

**Đáp án:** Không; ở class file, `new` tạo uninitialized object reference, rồi compiler dùng `invokespecial` để gọi `<init>`.

**Câu 3.** Vì sao Base constructor đọc `Child.childValue` bằng 0?

**Đáp án:** Toàn object đã có default values, nhưng explicit Child field initializer vẫn chưa chạy.

**Câu 4.** `this(7)` trong constructor có cấp phát object mới không?

**Đáp án:** Không. Nó delegate tới overload constructor trên **cùng instance**.

**Câu 5.** `<clinit>` và `<init>` khác nhau?

**Đáp án:** `<clinit>` khởi tạo class/static state; `<init>` khởi tạo từng object thông qua constructor chain.

**Câu 6.** TLAB nằm trong stack hay heap?

**Đáp án:** Heap; nó là vùng cấp phát cục bộ theo thread của HotSpot, không đồng nghĩa vùng stack.

**Câu 7.** Có thể khẳng định object header luôn 12/16 byte không?

**Đáp án:** Không. Layout/header phụ thuộc phiên bản HotSpot, architecture, flags và hình thức header.

**Câu 8.** `new Item[3]` tạo mấy Item objects?

**Đáp án:** Không tạo Item instance nào; chỉ tạo một Item[] array object với ba null reference elements.

**Câu 9.** Constructor thất bại có trả reference qua biểu thức `new` như bình thường không?

**Đáp án:** Không; biểu thức hoàn tất abruptly, exception truyền ra, nhưng side effects đã xảy ra không tự rollback.

**Câu 10.** Tạo xong object có nghĩa mọi thread khác luôn nhìn thấy fields cuối cùng không?

**Đáp án:** Không. Cần safe publication và các quy tắc Java Memory Model; tránh this-escape.

**Câu 11.** Vì sao compiler/JIT có thể bỏ một allocation mà Java semantics vẫn đúng?

**Đáp án:** Khi object không escape và phép tối ưu bảo toàn mọi hành vi quan sát được, JIT có thể scalar-replace/eliminate physical allocation.

**Câu 12.** Thứ tự argument evaluation của constructor?

**Đáp án:** Trái sang phải, sau allocation với class instance creation expression thông thường theo JLS.

## 15. Bản đồ ghi nhớ

~~~text
JAVA SOURCE                JVM / HOTSPOT
new Type(args)
      |
      +--> Resolve class, class initialization nếu cần
      |
      +--> Allocate instance  (HotSpot: TLAB hoặc slow path)
      |
      +--> Default fields     (0, false, NUL, +0.0, null)
      |
      +--> Evaluate args      (left to right)
      |
      +--> invokespecial <init>
              |
              +-- Object/superclass constructor chain
              +-- superclass initializers / constructor body
              +-- subclass initializers / constructor body
              |
              v
          Thành công? -- YES --> trả reference tới instance
                      -- NO  --> exception, không có kết quả thường

Class init: <clinit>, không phải constructor của từng object
Arrays: newarray / anewarray / multianewarray
TLAB: heap allocation fast path, KHÔNG phải thread stack
JIT: có thể bỏ allocation vật lý, nhưng phải giữ đúng semantics
~~~

**Kết luận:** tạo instance có hai phần khác nhau: **cấp phát + default initialization** do JVM quản lý và **constructor initialization** do code `<init>` thực hiện. Superclass constructor chạy trước phần khởi tạo của subclass, vì vậy có thể gặp default values khi object còn đang xây dựng. Hiểu thêm TLAB, object header và JIT giúp phân biệt những guarantee của Java với các tối ưu nội bộ HotSpot.

## Tài liệu chính thức

- [JLS Java SE 17 — `15.9.4 Run-Time Evaluation of Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.4).
- [JLS Java SE 17 — `12.5 Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5).
- [JVMS Java SE 17 — `6.5 new](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.new).
- [JVMS Java SE 17 — `2.5.3 Heap](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3).
- [JVMS Java SE 17 — `2.9.1 Instance Initialization Methods](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.9.1).
- [JVMS Java SE 17 — `4.10.2.4 Newly Created Objects](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10.2.4).
- [OpenJDK HotSpot source — oop.hpp (chi tiết triển khai)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/oops/oop.hpp).
- [JDK 17 — javap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
