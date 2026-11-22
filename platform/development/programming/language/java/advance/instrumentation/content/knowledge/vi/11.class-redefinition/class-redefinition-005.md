# Những thay đổi cấu trúc không được hỗ trợ theo hợp đồng JVM hiện hành

> **Kết luận cốt lõi:** Với **class đã được JVM định nghĩa**, `Instrumentation.redefineClasses(...)` có thể cập nhật **phần thân method**, constant pool và những thuộc tính class file được phép; nhưng nó **không phải cơ chế thay đổi tùy ý cấu trúc của class**. Theo hợp đồng Java Instrumentation/JVM TI thông thường, không thể dùng redefine để thêm, xóa hay đổi tên field/method; đổi descriptor của method; đổi class hierarchy; đổi modifier; hoặc thay các thuộc tính cấu trúc được đặc tả là bất biến như `NestHost`, `NestMembers`, `Record` và `PermittedSubclasses`. Nếu yêu cầu vi phạm, JVM từ chối và **không cài đặt định nghĩa mới**.

Bài thuộc chủ đề **Redefinition** trong Java Advance – instrumentation. Mục đích không chỉ là ghi nhớ "HotSwap chỉ sửa method body", mà là hiểu vì sao source code trông nhỏ nhưng class-file schema có thể đổi, cách nhận biết từng loại từ chối, và cách thiết kế agent/đường cập nhật không vượt hợp đồng JVM.

## 1. Phân biệt thay hành vi với thay cấu trúc

Một class sau khi được định nghĩa không chỉ là chuỗi bytecode của một method. Nó có **danh tính và cấu trúc** mà JVM, verifier, runtime, reflection và những class khác có thể đã sử dụng:

- Danh tính class gắn với **binary name + defining class loader**, cùng quan hệ module/package phù hợp.
- Quan hệ kế thừa: direct superclass và danh sách trực tiếp implement interfaces.
- Danh sách **field**: tên, descriptor kiểu JVM, modifier và layout/metadata liên quan.
- Danh sách **method/constructor**: tên, descriptor, modifier; class có thể chứa cả method do compiler sinh.
- Những class attributes có ý nghĩa cấu trúc: nestmate, record, sealed subclasses và các thuộc tính khác chịu quy tắc của JVM TI.
- Phần **Code** của method, constant pool và metadata không bị cấm thay đổi.

Hãy xem hai trường hợp:

~~~java
// Phiên bản A — ví dụ rút gọn, không phải file chạy độc lập.
public class Invoice {
    private int amount;

    public int total() {
        return amount;
    }
}
~~~

~~~java
// Phiên bản B — vẫn cùng field/method descriptor, chỉ đổi Code.
public class Invoice {
    private int amount;

    public int total() {
        return Math.max(0, amount);
    }
}
~~~

Bản B **có thể là ứng viên redefine hợp lệ** nếu JVM hỗ trợ, class modifiable và bytecode mới tương thích. Không phải cứ giữ tên method là đủ: vẫn cần cùng schema và các checks khác.

Ngược lại:

~~~java
// Phiên bản C — thêm field vào class đã load: schema khác.
public class Invoice {
    private int amount;
    private int discount; // thêm field

    public int total() {
        return amount - discount;
    }
}
~~~

Bản C **không phải** một thay đổi method-body-only. Nó đòi class đã load có một field mới, ảnh hưởng cấu trúc và layout. Khi dùng `redefineClasses` tiêu chuẩn để thay A bằng C trên JVM hiện hành, yêu cầu bị từ chối vì thay đổi schema.

**Đừng nhầm hai thời điểm:** Khi class được **định nghĩa lần đầu**, một `ClassFileTransformer` có thể sinh classfile với field/method bổ sung miễn classfile đó hợp lệ và thỏa các điều kiện runtime. Nhưng khi class **đã định nghĩa**, `redefineClasses` hoặc `retransformClasses` phải tuân thủ giới hạn thay đổi definition hiện hữu. Quyền biến đổi ở **first load** không tạo quyền thay schema trong **live redefinition**.

## 2. Bảng các thay đổi cấu trúc không được hỗ trợ

Đối chiếu **hai classfile** của cùng class, không chỉ hai tệp `.java`:

| Nhóm | Ví dụ thay đổi | Lý do bị giới hạn khi redefine |
| --- | --- | --- |
| **Thêm field** | `private long count;` xuất hiện sau khi class đã load | Thay đổi danh sách field và schema của đối tượng/class |
| **Xóa field** | Bản mới không còn `private int amount;` | Bỏ một field đã được JVM định nghĩa |
| **Đổi tên field** | `amount` → `quantity` | Ở mức classfile là bỏ field cũ và thêm field tên mới |
| **Đổi kiểu field** | `int amount` → `long amount` | Descriptor JVM từ `I` thành `J`; thay schema |
| **Đổi modifier field** | `private` → `public`, `static` ↔ instance, `final` khác đi | Modifiers không còn trùng cấu trúc field gốc |
| **Thêm method/constructor** | Thêm `calculateTax()` hoặc constructor overload | Danh sách method JVM thay đổi |
| **Xóa method/constructor** | Bỏ `total()` hoặc một `<init>` | JVM đang có method identity cần được giữ |
| **Đổi tên method** | `total()` → `sum()` | Method cũ bị bỏ, method mới được thêm |
| **Đổi chữ ký/descriptor** | `total()I` → `total(J)I` hay `total()J` | JVM method descriptor thay đổi (gồm tham số và return type) |
| **Đổi modifier method** | Instance → `static`, public → private, thêm/bỏ `synchronized`/`native` | Thay method modifiers không được hỗ trợ |
| **Đổi modifier class** | Class đang chạy trở thành `final` hay thay accessibility | Class modifiers khác bản đang định nghĩa |
| **Đổi superclass** | `extends BaseA` → `extends BaseB` | Thay inheritance và quan hệ method/field resolution |
| **Đổi tập direct interfaces** | Bổ sung/bỏ `implements Marker` | Thay class hierarchy hợp đồng JVM |
| **Đổi nestmate attributes** | `NestHost` hay `NestMembers` khác trước | Thay quan hệ nestmate đã định nghĩa |
| **Đổi `Record` attribute** | Thay record components của class đã load | Thuộc tính cấu trúc `Record` phải giữ nhất quán |
| **Đổi `PermittedSubclasses`** | Thêm/bỏ subclass được phép cho sealed class | Hợp đồng sealed hierarchy thay đổi |

Trong JDK hiện hành, JVM TI **RedefineClasses** và **RetransformClasses** đều nêu rõ các nhóm bị cấm này. Danh sách có thể thay đổi trong một **phiên bản JVM tương lai**, nên khi nói "hiện hành" phải gắn với API/VM đích. Không suy ra mọi sản phẩm quảng cáo "enhanced hotswap" đều có cùng hợp đồng Java Instrumentation chuẩn.

### Đọc descriptor thay vì chỉ nhìn tên source

Từ góc độ Java source, hai declaration sau có vẻ chỉ đổi một tham số:

~~~java
public int total() { return 0; }
public int total(long customerId) { return 0; }
~~~

Nhưng classfile có hai method descriptors khác nhau:

~~~text
total()I       // không tham số, trả int
total(J)I      // nhận long, trả int
~~~

Khi **thay** method cũ bằng method mới, JVM quan sát một method bị xóa và một method khác được thêm. Cũng cần nhớ **return type là một phần của JVM method descriptor**, dù signature theo ngôn ngữ Java không phân biệt overload chỉ bằng return type. Vì vậy đổi `int total()` thành `long total()` vẫn là thay descriptor và không hợp lệ cho redefine của class đã load.

### Source không đổi hình thức nhưng compiler có thể sinh schema khác

Compiler có thể tạo method/field mà người viết không khai báo trực tiếp:

- Lambda expression có thể được biên dịch thành synthetic helper method tên dạng `lambda$...`; đổi cấu trúc biểu thức có thể thêm/bỏ/chuyển method ở classfile.
- Generic override có thể sinh **bridge method** để giữ tính đa hình theo erasure.
- Một thay đổi về inner class, record, enum, synthetic access hoặc desugaring có thể thay danh sách method/field hoặc class attributes.
- Kotlin, Scala, Lombok hoặc công cụ code generation cũng có thể sinh thành viên không thấy rõ từ một đoạn diff ngắn.

Vì vậy, code review của một bản vá live class nên **so sánh classfile thực** bằng `javap -p -s` hoặc thư viện phân tích bytecode; không kết luận "chỉ sửa một dòng Java" đồng nghĩa "chỉ sửa Code attribute".

## 3. Những gì thường *có thể* thay đổi

Hợp đồng JVM TI cho phép thay **method bodies**, **constant pool** và **một số attributes không bị cấm**, với điều kiện final bytes sau chuỗi transformer là classfile hợp lệ và không thay schema bị bảo vệ.

| Thay đổi | Có thể là redefine hợp lệ? | Điều kiện quan trọng |
| --- | --- | --- |
| Đổi thuật toán trong **method body hiện hữu** | Thường **có** | Giữ tên/descriptor/modifier, verifier chấp nhận, dependency liên kết được |
| Đổi string constant được một method dùng | Thường **có** | Constant pool/classfile hợp lệ, không phá schema |
| Đổi cách xử lý exception trong Code | Thường **có** | Bytecode, stack-map frames, exception handlers hợp lệ |
| Thêm lời gọi đến **helper method thuộc class khác** trong body hiện hữu | Có thể **có** | Helper load được, visibility/module đúng, không thêm method mới vào class đích |
| Thay metadata không bị JVM TI cấm | **Phụ thuộc** attribute và JVM | Không coi mọi annotation/attribute là tự động được phép |
| Thêm field vào class đích | **Không** theo hợp đồng này | Cần cơ chế khác hoặc triển khai phiên bản mới khi class được define |
| Thêm method vào class đích | **Không** | Không thể "ẩn" việc này bằng `ClassDefinition` |
| Đổi `extends`/`implements` | **Không** | Quan hệ hierarchy phải giữ |
| Thay `Record`/`PermittedSubclasses`/nestmate attributes | **Không** | Các class attributes này bị cấm thay |

**Ví dụ hợp lệ về mặt cấu trúc** (mã minh họa):

~~~java
// Trước: method này đã tồn tại ở lớp đang chạy.
public int calculate(int a, int b) {
    return a + b;
}

// Sau: vẫn calculate(II)I, nhưng method body khác.
public int calculate(int a, int b) {
    return Math.addExact(a, b);
}
~~~

Đổi implementation như trên **không tự bảo đảm** yêu cầu thành công: nếu bytes sai version, method body thiếu stack-map frames hợp lệ, module không đọc được helper mới hay transformer khác sửa cấu trúc, JVM vẫn từ chối hoặc phát sinh linkage error.

**Hạn chế biến đổi `<clinit>`:** Nếu bạn đổi body của class initializer, redefine **không chạy lại class initializer**. Giữ tên/descriptor của `<clinit>` không có nghĩa có cơ hội tái thiết lập static state trên JVM đang chạy.

## 4. Kiểm tra điều kiện trước khi gọi `redefineClasses`

API Java chính:

~~~java
boolean supported = inst.isRedefineClassesSupported();
boolean modifiable = inst.isModifiableClass(Target.class);

if (!supported || !modifiable) {
    throw new IllegalStateException("Cannot redefine this class here");
}

byte[] bytes = /* classfile hợp lệ cho cùng target class */;
inst.redefineClasses(new ClassDefinition(Target.class, bytes));
~~~

Đây là **mảnh code minh họa**, không phải file Java độc lập vì chưa có `Instrumentation inst`, `Target` và bytes. Ví dụ hoàn chỉnh ở phần tiếp theo.

### Cấu hình manifest và JVM capability

Startup agent dùng `-javaagent` cần khai báo:

~~~text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true
~~~

`Can-Redefine-Classes: true` là một yêu cầu capability. `isRedefineClassesSupported()` còn phụ thuộc JVM; **không** tự đúng chỉ nhờ manifest. Giá trị `true` không bật tính năng **thay cấu trúc** — nó chỉ cho phép gọi redefine trong giới hạn JVM hỗ trợ.

**Hai phép kiểm tra độc lập:**

- `isRedefineClassesSupported()`: cấu hình VM có hỗ trợ class redefinition hay không.
- `isModifiableClass(clazz)`: class cụ thể có được phép sửa definition hay không.

Cả hai đều có thể trả `true` mà **classfile mới vẫn bị từ chối do thay đổi cấu trúc**. Đây là điểm quan trọng nhất khi debug một lỗi `UnsupportedOperationException` sau khi preflight đã vượt qua.

### Phân biệt với `retransformClasses`

`redefineClasses` nhận `ClassDefinition(targetClass, byte[])` do caller đưa vào; `retransformClasses` lấy bytes nền và chạy lại chuỗi transformer theo quy tắc capability `canRetransform`. Cách có được bytes khác nhau, nhưng **giới hạn không thêm/xóa method/field/đổi hierarchy trong class đã load vẫn áp dụng**.

Đừng đổi `redefineClasses` thành `retransformClasses` chỉ vì thấy lỗi "method added": nếu kết quả bytecode vẫn thêm method/field, đổi API không làm delta cấu trúc được phép.

## 5. Thí nghiệm Java 17+: method body được nhận, thêm field bị từ chối

Ví dụ sau là **một chương trình hoàn chỉnh** với startup agent có khả năng redefine. Nó kiểm chứng ba điều:

1. Thay body của `Target.status()` từ `"ORIGINAL"` thành `"UPDATED"` **thành công**, trong khi cùng đối tượng `Target` vẫn có field `amount=7`.
2. Thử **thêm field** vào chính class `Target` đã load bị từ chối bằng `UnsupportedOperationException` trên OpenJDK/HotSpot kiểm thử.
3. Khi redefine **hai class trong một batch**, nếu một definition không hợp lệ về cấu trúc thì JVM **không áp dụng một phần**; class `Companion` dù có bytes thay thế hợp lệ vẫn giữ hành vi cũ.

Dùng **JDK 17+**, không cần thư viện bytecode ngoài. Chúng ta tạo những file `.class` khác nhau từ source có cùng tên, sau đó cung cấp bytes cho `ClassDefinition`; không phải instrument ở lần nạp đầu.

### 5.1. Tệp gốc `Target.java`

~~~java
public class Target {
    private int amount = 7;
    public String status() { return "ORIGINAL"; }
    public int amount() { return amount; }
}
~~~

Tên class, constructor mặc định, field và cả hai method là schema gốc. Bản ở classpath root sẽ được JVM load trước khi gọi redefine.

### 5.2. Tệp gốc `Companion.java`

~~~java
public class Companion {
    public String status() { return "COMPANION_ORIGINAL"; }
}
~~~

Đây là class thứ hai để kiểm chứng hành vi **atomic all-or-none** khi một lệnh redefine có nhiều `ClassDefinition`.

### 5.3. Bản thay thế chỉ đổi method body — `variants/body/Target.java`

~~~java
public class Target {
    private int amount = 7;
    public String status() { return "UPDATED"; }
    public int amount() { return amount; }
}
~~~

Schema trùng với bản gốc; chỉ chuỗi trả về của method thay đổi. Đây là thay đổi mà redefinition thông thường có thể chấp nhận.

### 5.4. Bản thay thế cố tình thêm field — `variants/addField/Target.java`

~~~java
public class Target {
    private int amount = 7;
    private int extra = 99;
    public String status() { return "STRUCTURAL"; }
    public int amount() { return amount; }
}
~~~

File này **biên dịch Java bình thường**, nhưng không phải bytes hợp lệ **cho việc redefine class `Target` đã tồn tại** vì có thêm `extra`. Cần phân biệt rõ: **`javac` thành công không chứng minh `redefineClasses` có thể cài definition mới**.

### 5.5. Bản thay thế hợp lệ cho class khác — `variants/companionBody/Companion.java`

~~~java
public class Companion {
    public String status() { return "COMPANION_UPDATED"; }
}
~~~

Bản này chỉ đổi body, nhưng sẽ được gửi trong **cùng một batch** với bản `Target` có thêm field, để chứng minh cả batch bị từ chối.

### 5.6. Agent `RedefineAgent.java`

~~~java
import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("capability=" + inst.isRedefineClassesSupported());
    }

    public static boolean modifiable(Class<?> target) {
        return instrumentation.isModifiableClass(target);
    }

    public static void redefineBody() throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("variants/body/Target.class"));
        instrumentation.redefineClasses(new ClassDefinition(Target.class, bytes));
        System.out.println("body=SUCCESS");
    }

    public static void tryAddingField() throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("variants/addField/Target.class"));
        try {
            instrumentation.redefineClasses(new ClassDefinition(Target.class, bytes));
            System.out.println("addField=UNEXPECTED_SUCCESS");
        } catch (UnsupportedOperationException expected) {
            System.out.println("addField=UnsupportedOperationException");
        }
    }

    public static void tryBatch() throws Exception {
        byte[] invalid = Files.readAllBytes(Path.of("variants/addField/Target.class"));
        byte[] valid = Files.readAllBytes(Path.of("variants/companionBody/Companion.class"));
        try {
            instrumentation.redefineClasses(
                new ClassDefinition(Target.class, invalid),
                new ClassDefinition(Companion.class, valid));
            System.out.println("batch=UNEXPECTED_SUCCESS");
        } catch (UnsupportedOperationException expected) {
            System.out.println("batch=UnsupportedOperationException");
        }
    }
}
~~~

**Cách đọc agent:**

- `Instrumentation` đến từ JVM qua `premain`.
- `ClassDefinition(Target.class, bytes)` gắn **đối tượng class đã load** với class-file bytes đề nghị cài đặt.
- `redefineBody()` thực hiện một thay đổi method body hợp lệ.
- `tryAddingField()` bắt **chỉ** lỗi dự kiến `UnsupportedOperationException` của bài thử. Trong ứng dụng thực, cần phân biệt các exception khác (file không tồn tại, classfile hỏng, unsupported VM, target không modifiable) và có chính sách xử lý cụ thể.
- `tryBatch()` gửi hai definition cùng lúc. Nếu bất kỳ definition nào không hợp lệ, JVM không cài class mới cho cả hai.
- Sau khi một redefine thất bại, việc đã in log ở agent hoặc việc transformer từng nhận callback **không đồng nghĩa** classfile mới đã được cài.

Lớp agent không cần chứa `Target.class` hoặc `Companion.class` trong agent JAR; chúng nằm ở application classpath. `Can-Redefine-Classes: true` thuộc manifest của agent JAR, không phải thuộc tính của file `Target.class`.

### 5.7. Ứng dụng `Demo.java`

~~~java
public final class Demo {
    public static void main(String[] args) throws Exception {
        Target target = new Target();
        Companion companion = new Companion();
        if (!RedefineAgent.modifiable(Target.class)) {
            throw new IllegalStateException("Target is not modifiable");
        }
        System.out.println("modifiable=true");
        System.out.println("before=" + target.status() + "/" + target.amount());

        RedefineAgent.redefineBody();
        System.out.println("after-body=" + target.status() + "/" + target.amount());

        RedefineAgent.tryAddingField();
        System.out.println("after-reject=" + target.status() + "/" + target.amount());

        System.out.println("companion-before=" + companion.status());
        RedefineAgent.tryBatch();
        System.out.println("companion-after=" + companion.status());
    }
}
~~~

Trong demo, `Target` và `Companion` được tạo **trước** các yêu cầu redefine. Tên và reference đối tượng không bị thay; chính **method body đang được JVM dùng ở các lời gọi mới** là thứ có thể thay đổi.

### 5.8. Manifest `agent.mf`

~~~text
Manifest-Version: 1.0
Premain-Class: RedefineAgent
Can-Redefine-Classes: true
~~~

Lưu manifest với dấu xuống dòng ở cuối. Bài dùng startup agent `-javaagent` nên phải có `Premain-Class`. Không cần `Can-Retransform-Classes`, vì mọi lệnh trong ví dụ sử dụng **`redefineClasses`**, không phải `retransformClasses`.

### 5.9. Cấu trúc thư mục và lệnh chạy

Tạo thư mục như sau:

~~~text
demo/
  Target.java
  Companion.java
  RedefineAgent.java
  Demo.java
  agent.mf
  variants/
    body/
      Target.java
    addField/
      Target.java
    companionBody/
      Companion.java
~~~

Từ **thư mục `demo`**, chạy bằng JDK 17+:

~~~bash
javac --release 17 Target.java Companion.java RedefineAgent.java Demo.java

javac --release 17 -d variants/body variants/body/Target.java

javac --release 17 -d variants/addField variants/addField/Target.java

javac --release 17 -d variants/companionBody variants/companionBody/Companion.java

jar --create --file redefine-agent.jar --manifest agent.mf RedefineAgent.class

java -javaagent:redefine-agent.jar Demo
~~~

Lệnh `-d` giúp mỗi bản variant được biên dịch ra **thư mục riêng**. Java app chỉ thấy `Target.class` và `Companion.class` bản gốc ở thư mục chạy; agent chủ động đọc các file thay thế từ `variants/...`. Không copy `Target.class` variant vào root trước lúc app khởi động, nếu không bài sẽ không còn mô phỏng **redefinition của class đã chạy**.

**Stdout trên OpenJDK 24 với source biên dịch bằng `javac --release 17`:**

~~~text
capability=true
modifiable=true
before=ORIGINAL/7
body=SUCCESS
after-body=UPDATED/7
addField=UnsupportedOperationException
after-reject=UPDATED/7
companion-before=COMPANION_ORIGINAL
batch=UnsupportedOperationException
companion-after=COMPANION_ORIGINAL
~~~

Từng dòng đều có ý nghĩa:

- `capability=true`: manifest và JVM cho phép redefine. Đây **không** phải quyền thay schema.
- `modifiable=true`: `Target` có thể được sửa definition về nguyên tắc; **không** có nghĩa mọi classfile thay thế đều hợp lệ.
- `body=SUCCESS` và `after-body=UPDATED/7`: đổi method body thành công; state `amount=7` của instance đã tồn tại được giữ nguyên.
- `addField=UnsupportedOperationException`: thêm `extra` bị JVM từ chối dù source Java đã biên dịch thành công.
- `after-reject=UPDATED/7`: lớp tiếp tục ở **definition đã được cài thành công gần nhất**; bản `STRUCTURAL` không được áp dụng.
- `batch=UnsupportedOperationException`: batch có một definition thêm field không hợp lệ.
- `companion-after=COMPANION_ORIGINAL`: ngay cả `Companion`, dù bytes mới chỉ sửa method body, cũng **không được thay** vì batch thất bại.

Đây là hành vi được kiểm chứng thực tế, không phải mô phỏng bằng cách in sẵn kết quả của mọi nhánh. **Không áp dụng cùng một tên exception cho mọi trường hợp lỗi trên mọi JVM**: classfile sai tên có thể gây `NoClassDefFoundError`, sai format gây `ClassFormatError`, và class không modifiable có thể gây `UnmodifiableClassException`.

## 6. Các biến thể lỗi khác: giải thích trước–sau theo classfile

Trong một thử nghiệm mở rộng trên OpenJDK 24, từ lớp ban đầu:

~~~java
public class DemoService {
    private int seed = 7;
    public String message() { return "ORIGINAL"; }
    public int value() { return seed; }
}
~~~

Có thể biên dịch các phiên bản thay thế riêng, rồi cấp bytes của từng phiên bản cho `redefineClasses(new ClassDefinition(DemoService.class, bytes))`. **Bảng dưới là mô tả kết quả thực nghiệm**, không phải danh sách file Java bổ sung phải tạo để chạy demo phần 5.

| Phiên bản mới được thử | Delta classfile | Kết quả trên OpenJDK 24 |
| --- | --- | --- |
| Chỉ sửa body `message()` thành `"UPDATED"` | Code/constant pool khác | `SUCCESS` |
| Thêm `private int extra` | Thêm field | `UnsupportedOperationException` |
| Bỏ `seed` và đổi body `value()` trả hằng số | Xóa field | `UnsupportedOperationException` |
| Thêm `extraMethod()` | Thêm method | `UnsupportedOperationException` |
| Bỏ `value()` | Xóa method | `UnsupportedOperationException` |
| Đổi `message()` thành `message(int)` | Đổi method descriptor | `UnsupportedOperationException` |
| Thêm `extends Parent` | Đổi direct superclass | `UnsupportedOperationException` |
| Thêm `implements Marker` | Đổi tập direct interface | `UnsupportedOperationException` |
| Đổi field `seed` từ `private` thành `public` | Đổi field modifier | `UnsupportedOperationException` |
| Đổi `message()` từ instance thành `static` | Đổi method modifier | `UnsupportedOperationException` |
| Đổi class thành `final class DemoService` | Đổi class modifier | `UnsupportedOperationException` |

Trường hợp đặc biệt: nếu một `ClassDefinition` gắn với `DemoService.class` nhưng bytecode thực tế khai báo **class tên `WrongName`**, JVM báo `NoClassDefFoundError` trong thí nghiệm. Đây là lỗi **tên class không khớp**, không phải một `UnsupportedOperationException` về delta schema.

**Tại sao phải thử sau khi body đổi thành công?** Nó minh họa rằng khi một lượt redefine tiếp theo thất bại, JVM vẫn giữ definition đang dùng ở thời điểm đó. "Giữ nguyên" không nhất thiết là quay về bản startup nguyên thủy; đó là **bản đã cài thành công gần nhất**.

## 7. Những thay đổi cấu trúc gián tiếp dễ bị bỏ sót

### 7.1. Constructor và phương thức do compiler sinh

Đổi một constructor từ:

~~~java
public Order() {
    this.count = 0;
}
~~~

thành:

~~~java
public Order(int start) {
    this.count = start;
}
~~~

là đổi descriptor từ `<init>()V` thành `<init>(I)V`, **không phải chỉ sửa Code**. Nếu class đã load, việc xóa constructor cũ và thêm constructor mới bị cấm. Bạn có thể sửa **nội dung một constructor đã tồn tại** mà giữ nguyên descriptor, nhưng redefine **không tự gọi lại constructor** cho các object đã tạo.

Tương tự, thay generics hoặc một method override có thể khiến compiler sinh thêm/bớt **bridge method**. Lúc đó diff source có thể không nhắc tới bridge nhưng classfile lại chứa method set khác.

### 7.2. Lambda và synthetic methods

Một thay đổi Java như:

~~~java
// Đoạn minh họa trong một method đã tồn tại:
Runnable r = () -> System.out.println("audit");
~~~

có thể tạo method synthetic dạng `lambda$...` trong chính class và bootstrap linkage qua `invokedynamic`. Thêm một lambda mới **không phải lúc nào** chỉ là đổi Code của method ban đầu. Nếu danh sách method/descriptor hoặc bootstrap/linkage bị thay theo cách không được phép, JVM có thể từ chối.

**Cách kiểm tra:** biên dịch cả phiên bản gốc và phiên bản mới ở các thư mục khác nhau, dùng `javap -p -s -c` xem cả private/synthetic members và method descriptors. Đừng đoán từ source code đã format đẹp.

### 7.3. Record, sealed class và nestmates

Ví dụ về ý định thay đổi cấu trúc:

~~~java
record InvoiceLine(long amount) {}
// Đổi thành record InvoiceLine(long amount, String currency) {}
~~~

Đây là **mảnh minh họa**, không phải hai class có thể khai báo cạnh nhau trong cùng file để chạy. Record components liên hệ tới field, accessor, constructor và `Record` attribute. Redefine record đã load theo cách đổi components vi phạm nhiều giới hạn, trong đó có `Record` attribute.

~~~java
sealed interface PaymentResult permits Success, Failure {}
// Muốn thêm Pending vào danh sách permits sau khi lớp đã được định nghĩa.
~~~

Thêm `Pending` vào `PermittedSubclasses` attribute của interface/class đã load không được hỗ trợ. Một class `Pending` mới được compile bình thường **không** làm thay đổi permitted hierarchy đã được JVM định nghĩa.

Nestmate attributes `NestHost` và `NestMembers` cũng không được thay. Nếu công cụ rewrite bytecode tự ý thêm/bớt nest members để truy cập private member, đó không còn là một thay đổi body vô hại.

**Điểm quan trọng:** Các giới hạn này dựa trên **classfile attributes** và JVM TI, chứ không chỉ danh sách từ khóa `record`, `sealed` hay `private` của ngôn ngữ Java. Tùy JDK, compiler và thư viện bytecode, còn có thuộc tính khác cần xác minh khi tạo final classfile.

### 7.4. Enum và synthetic fields

Thêm một enum constant sau khi class enum đã được định nghĩa thường kéo theo thêm static field, thay metadata và thay logic khởi tạo/các tập giá trị nội bộ. Không nên xem một enum constant mới như "chỉ thêm một string". Vì redefine không cho thêm field và không chạy lại initialization, cách hot-patch enum này không phù hợp với cơ chế tiêu chuẩn.

## 8. Vì sao JVM không tự điều chỉnh cấu trúc class đang chạy?

Hãy hình dung một ứng dụng có:

~~~text
Object a, b, c đã được tạo theo schema của Account phiên bản A
     |
     +-- bytecode khác đã resolution tới Account.balance:I
     +-- reflection/cache có thể giữ thông tin member
     +-- thread có stack frame đang chạy trong method cũ
     +-- JIT có thể đã tối ưu trên các giả định về layout và method
~~~

Nếu redefine tùy tiện thêm `long creditLimit`, đổi `balance:I` thành `balance:J` hoặc đổi superclass, JVM phải tái cấu trúc trạng thái của đối tượng đang sống, xử lý references đã liên kết, inheritance resolution và các frames/runtime metadata. Hợp đồng Java Instrumentation tiêu chuẩn **không cung cấp một phép migration đối tượng/schema tổng quát** như vậy.

Đây là lời giải thích về động cơ thiết kế, **không** phải tuyên bố JVM về mặt kỹ thuật tuyệt đối không bao giờ có thể hỗ trợ enhanced class redefinition. Một số runtime, VM tùy biến hoặc công cụ phát triển có khả năng riêng ngoài API chuẩn; code production portable không được giả định chúng có mặt.

### Điều gì xảy ra với object và thread khi body redefine thành công?

- **Instance vẫn là chính nó**; không có constructor được gọi lại chỉ vì redefine. Các field đã có giữ giá trị hiện tại.
- **Static fields giữ giá trị** đã có; class initializer `<clinit>` không chạy lại tự động.
- **Active stack frames** của method được redefine có thể tiếp tục thực thi bytecode phiên bản cũ; những **lượt gọi mới** tới method sẽ dùng definition mới.
- Đổi logic code **không tự đảo ngược** side effects đã xảy ra, I/O, transaction hoặc business state.
- Không có bảo đảm rằng mọi thread lập tức có cùng quan sát tại một thời điểm ứng dụng chọn, nếu chúng đang ở các frames khác nhau.

Ví dụ phần 5 cho thấy `target.amount()` vẫn trả `7` sau khi body `status()` đổi. Nhưng việc đổi code cho các lời gọi tiếp theo không sửa dữ liệu `Target.amount` ở tất cả instance theo một thuật toán migration.

## 9. Phân biệt lỗi cấu trúc với các lỗi khác của `redefineClasses`

Không phải exception nào cũng có nghĩa "đã đổi cấu trúc".

| Exception / triệu chứng | Loại vấn đề | Cách điều tra |
| --- | --- | --- |
| `UnsupportedOperationException` | JVM không hỗ trợ capability **hoặc** delta classfile yêu cầu thay đổi không được phép | Kiểm tra `isRedefineClassesSupported()`, diff schema, modifiers và các attributes bị cấm |
| `UnmodifiableClassException` | Class đích không cho đổi definition | Gọi `isModifiableClass(clazz)` trước và kiểm tra đúng class/loader |
| `NoClassDefFoundError` | Binary name trong classfile mới không khớp target class | Dùng `javap -verbose`, kiểm tra file `.class` được đọc có đúng class không |
| `ClassFormatError` | Bytes không tuân định dạng classfile | Kiểm tra công cụ sinh bytes, constant pool, stack-map frames và file I/O |
| `UnsupportedClassVersionError` | Class-file version mới không được JVM đang chạy hỗ trợ | Biên dịch với `--release` phù hợp JDK runtime |
| `ClassCircularityError` | Class definition gây vòng phụ thuộc kế thừa không hợp lệ | Xem superclass/interfaces sau transform |
| `LinkageError` khác | Lỗi liên kết trong quá trình áp dụng/giải quyết class | Kiểm tra loader, class visibility, module access, helper classes |
| `ClassNotFoundException` trong chữ ký API | Được khai báo vì tương thích lịch sử; theo Javadoc không phát sinh từ chính thao tác này | Xem root cause và API đang gọi nếu ứng dụng có wrapper riêng |
| Không có exception nhưng method vẫn như cũ | Có thể bytes thực tế giống cũ, transformer trả `null` hoặc không instrument method dự kiến | Kiểm tra input classfile, danh sách transformer và behavior sau thao tác |

**Lưu ý:** `UnsupportedOperationException` không phân loại chi tiết loại delta ở Java API. JVM TI native có những lỗi rõ hơn như `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_SCHEMA_CHANGED`, `..._METHOD_ADDED`, `..._METHOD_DELETED`, `..._HIERARCHY_CHANGED`, `..._CLASS_MODIFIERS_CHANGED` và `..._METHOD_MODIFIERS_CHANGED`. Java agent chỉ nên kết luận nhóm lỗi từ exception và **diff classfile**, không đoán chính xác một mã JVM TI nội bộ khi không có bằng chứng.

### Đọc classfile trước khi gửi vào JVM

Một số lệnh hỗ trợ kiểm tra:

~~~bash
javap -p -s -classpath . Target
javap -p -s -classpath variants/body Target
javap -p -s -classpath variants/addField Target

javap -verbose -classpath . Target
javap -verbose -classpath variants/addField Target
~~~

- `-p` hiện cả private members, tránh bỏ sót field/method của class.
- `-s` in JVM descriptors, giúp nhìn thay đổi như `()I` → `(J)I`.
- `-verbose` hiển thị classfile version, access flags, constant pool và attributes; dùng cùng diff có chọn lọc để hiểu nguyên nhân.
- **Thứ tự member trong output không phải tiêu chí duy nhất**: một công cụ bytecode có thể sắp xếp lại metadata mà vẫn giữ schema. So sánh theo *name, descriptor, modifier, hierarchy và prohibited attributes*.

Với class đã nạp bởi loader đặc biệt, **file trên disk không nhất thiết giống classfile đang chạy**. Những transform lúc load, shading, patch/module, version khác hoặc lần redefine trước có thể đã tác động. Để kiểm tra production, thu thập đúng bytes đã sử dụng/được đưa vào callback từ workflow quan sát đáng tin cậy, rồi kiểm chứng trên JVM thật.

## 10. Nhiều class trong một yêu cầu: tính atomic và giới hạn phạm vi

`Instrumentation.redefineClasses(ClassDefinition... definitions)` nhận **một tập class** vì đôi khi hai class phụ thuộc nhau cần thay đổi đồng thời. Theo hợp đồng API/JVM TI, khi yêu cầu có lỗi và ném exception, **không class nào trong tập được cài definition mới**.

~~~text
Đang chạy:
  Target.status()    = UPDATED
  Companion.status() = COMPANION_ORIGINAL

Yêu cầu redefine đồng thời:
  Target -> bytes có thêm field "extra"          (KHÔNG hợp lệ)
  Companion -> bytes chỉ đổi method body          (có thể hợp lệ)

Kết quả:
  UnsupportedOperationException
  Target vẫn UPDATED
  Companion vẫn COMPANION_ORIGINAL
~~~

Đây chính là phần **`batch`** đã kiểm thử trong demo. Tuy vậy, "atomic với việc cài definition" **không có nghĩa mọi side effect từ agent đã được hoàn tác**. Nếu một `ClassFileTransformer` được gọi trong quá trình xử lý và đã ghi file, gửi telemetry hay sửa cấu hình trước khi JVM phát hiện một class khác không hợp lệ, những side effects riêng đó không được API tự rollback.

Bởi vậy transformer nên hạn chế side effects; phép kiểm tra classfile trước khi yêu cầu giúp giảm nguy cơ một batch bị từ chối, nhưng **chỉ JVM mới quyết định cuối cùng** bytes sau chuỗi transformer có được cài hay không.

Trong quy trình sửa nóng an toàn:

1. Chuẩn bị **đúng bytes** và đối tượng `Class<?>` đích cho từng class/loader.
2. Kiểm tra capability, modifiability và diff cấu trúc của **toàn bộ tập**.
3. Đảm bảo bytecode mới liên kết được với những class khác đang chạy.
4. Gửi batch có phạm vi nhỏ, tránh trộn một đổi schema cần deployment với một đổi body phù hợp hotfix.
5. Chỉ báo "installed" khi `redefineClasses` trả về thành công; xác minh hành vi tiếp theo.

## 11. Nếu thật sự cần thêm field/method hoặc đổi hierarchy, nên làm gì?

**Lựa chọn 1 — Thiết kế method body dùng helper class mới.** Nếu chỉ cần triển khai thêm logic, giữ nguyên schema lớp đích và thay body method hiện hữu để gọi `HelperClass` trong class độc lập đã được load/định nghĩa hợp lệ. Phải kiểm tra class loader, module readability, visibility và dependency. Cách này **không** biến một helper method mới thành member của class đích.

~~~java
// Mảnh code minh họa phần thân method sẵn có sau khi thay:
public String status() {
    return AuditHelper.computeStatus(this);
}
~~~

Helper phải tồn tại và dễ liên kết; đoạn này **không phải chương trình độc lập**. Nếu bạn cần **một field mới theo từng instance**, có thể cân nhắc side table ngoài đối tượng (ví dụ weak-key map) hoặc thiết kế lại state storage. Khi đó phải giải quyết garbage collection, identity, đồng bộ và chi phí; không nên xem side table tương đương field Java về mọi ngữ nghĩa.

**Lựa chọn 2 — Thêm cấu trúc tại first class definition.** Với startup `ClassFileTransformer`, class **chưa loaded** có thể được biến đổi thành classfile mới chứa member bổ sung, miễn bytes hợp lệ. Đây là điểm khác giữa **load-time instrumentation** và **live redefinition**. Phải bảo đảm agent chạy đủ sớm, và mọi class loader mục tiêu đều dùng version tương thích.

**Lựa chọn 3 — Triển khai một phiên bản class/service mới.** Có thể tạo binary name mới, cấu trúc mới hoặc class loader mới; JVM coi class theo tên + defining loader, nên một class cùng tên từ loader mới là **class khác**, không tự thay mọi object/reference của lớp cũ. Migrate state, dependency injection, serialization và resource lifecycle là nhiệm vụ kiến trúc riêng.

**Lựa chọn 4 — Restart/redeploy.** Với thay schema thật, phương án portable dễ dự đoán là triển khai artifact mới và khởi động JVM/service mới, kết hợp rolling/canary deployment, migration dữ liệu và rollback theo quy trình.

**Lựa chọn 5 — Runtime tùy biến với "enhanced HotSwap".** Một vài JVM/tooling có mở rộng ngoài hợp đồng tiêu chuẩn, nhưng không nên dựa vào nó nếu ứng dụng cần chạy portable giữa các bản JDK/nhà cung cấp. Muốn sử dụng, cần xác minh rõ runtime, flags, compatibility, hỗ trợ classfile mới, cơ chế migration và tình huống rollback. Đây **không phải** chức năng được bật bằng `Can-Redefine-Classes: true` của Java Instrumentation chuẩn.

## 12. Checklist review bản vá redefinition và câu hỏi luyện tập

Trước khi ký duyệt một bản redefine ở JVM đang chạy:

- [ ] Đã xác định đúng `Class<?>`, defining loader và module, không chỉ tên file nguồn?
- [ ] Manifest agent có `Can-Redefine-Classes: true`, JVM trả `isRedefineClassesSupported()==true`?
- [ ] Class cụ thể trả `isModifiableClass(clazz)==true`?
- [ ] Classfile mới có **cùng binary name** và classfile version tương thích?
- [ ] Không thêm/xóa/đổi tên field/method/constructor; không đổi field descriptor, method descriptor, modifiers?
- [ ] Không đổi superclass, tập direct interfaces, `NestHost`/`NestMembers`, `Record` hoặc `PermittedSubclasses`?
- [ ] Đã so sánh member set **sau compile** gồm synthetic/bridge methods, không chỉ diff `.java`?
- [ ] Transformer khác có thể biến đổi final bytes không, và có kiểm tra tính hợp lệ sau chuỗi không?
- [ ] Có test một method-body-only update thành công, một schema update bị từ chối, và khả năng batch all-or-none?
- [ ] Có phân biệt **đổi code** với **migrate state** và xử lý active stack frames?
- [ ] Có cách rollback bằng bytes hợp lệ hoặc redeploy nếu sự cố, không chỉ remove transformer?
- [ ] Có xác nhận request thật sự cài definition trước khi báo "hotfix thành công"?

### Tự kiểm tra

**1.** `isRedefineClassesSupported() == true` và `isModifiableClass(Invoice.class) == true`. Agent thêm `private long amount;` rồi gọi redefine. Có đủ điều kiện chưa?

**Đáp án:** Chưa. Hai phép kiểm tra xác minh capability và class eligibility, **không bỏ giới hạn schema**. Thêm field vẫn không được hỗ trợ.

**2.** Một hotfix đổi body của method `parse(String)` nhưng method mới tham số `CharSequence`. Đây có phải body-only không?

**Đáp án:** Không. `String` và `CharSequence` tạo **descriptor khác**, nên đó là thay phương thức, không chỉ thay Code.

**3.** Lập trình viên thêm một lambda trong method và không thay public API. Có bảo đảm redefine được không?

**Đáp án:** Không. Cần so sánh classfile thực, đặc biệt synthetic methods/bridge methods và những thay đổi attributes do compiler sinh.

**4.** Một batch thay class A hợp lệ và class B không hợp lệ. Có thể class A đã được cài phiên bản mới không?

**Đáp án:** Theo hợp đồng `redefineClasses`, **không**: nếu thao tác thất bại, không class nào trong tập được cài definition mới. Nhưng side effects bên ngoài của callback/agent không được tự đảo ngược.

**5.** Đổi body method thành công. Các instance cũ, static fields và stack frames có tự reset?

**Đáp án:** Không. Instance và static state vẫn tồn tại; constructor/class initializer không được tự chạy lại; active frames có thể tiếp tục body cũ đến khi kết thúc.

**6.** JVM báo `NoClassDefFoundError` khi redefine bằng `WrongName.class`. Đây có phải cùng lỗi "thêm field" không?

**Đáp án:** Không. Ở đây binary name trong classfile không khớp với `Class<?>` đích. Cần kiểm tra class bytes và class name trước khi phân tích schema delta.

**Tóm tắt một câu:** `redefineClasses` **thay implementation của một class đang tồn tại trong giới hạn schema đã chốt**; nó không phải API để nâng cấp tùy ý mô hình object, danh sách member hay hierarchy của JVM đang chạy.

### Tài liệu chính thức

- [Java SE 17 — `Instrumentation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capability, `isModifiableClass`, `redefineClasses`, exception, xử lý stack frames, static state và batch semantics.
- [Java SE 17 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): gói `Class<?>` đích và class-file bytes dùng cho redefinition.
- [Java SE 17 — `java.lang.instrument` manifest](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): thuộc tính `Can-Redefine-Classes`.
- [JVM TI 25.0 — `RedefineClasses` và `RetransformClasses`](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html): giới hạn schema, modifiers, inheritance, nestmate/record/sealed attributes và atomicity.
