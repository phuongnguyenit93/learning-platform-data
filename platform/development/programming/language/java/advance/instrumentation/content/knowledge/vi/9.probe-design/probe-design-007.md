# Chèn mã vào constructor sau khi this có trạng thái hợp lệ

## 1. Mục tiêu và thông điệp chính

Trong Java Instrumentation, việc thêm mã đo vào **constructor** (phương thức bytecode tên `<init>`) khó hơn thêm vào method thường. Ở đầu constructor, tham chiếu tới đối tượng đang được tạo **chưa được JVM coi là một instance đã khởi tạo đầy đủ**. Nếu transformer chèn lệnh đọc/gọi method trên `this` không đúng thời điểm, class có thể bị từ chối với `VerifyError`. Ngay cả khi JVM chấp nhận bytecode, **trạng thái nghiệp vụ của đối tượng vẫn có thể chưa hoàn chỉnh**, nhất là khi có trường `final`, field initializer, constructor delegation hoặc kế thừa.

Bài này làm rõ hai yêu cầu riêng biệt:

1. **Hợp lệ theo JVM verifier:** chỉ sử dụng `this` như một tham chiếu instance đã khởi tạo tại những điểm bytecode cho phép.
2. **Hợp lệ theo vòng đời ứng dụng:** chỉ thu thập/công bố trạng thái khi các trường mà phép đo cần đã được thiết lập, không vô tình để `this` thoát sang thread khác khi object chưa xây dựng xong.

Hai thời điểm đó **không nhất thiết trùng nhau**. Ví dụ, ngay sau khi một superclass constructor trả về, `this` có thể đã dùng được theo verifier, nhưng subclass còn chưa gán các trường của chính nó. Một hook “constructor-return” tại lớp cha cũng không chứng minh đối tượng thuộc lớp con đã hoàn tất.

### Kết quả học tập

Sau bài, bạn có thể:

- giải thích `uninitializedThis` và vai trò của `invokespecial <init>`;
- phân biệt gọi `super(...)` với `this(...)` và nhận diện rủi ro đo trùng;
- chọn điểm đặt probe **sau initialization call** hoặc **ngay trước `RETURN`**, theo mục đích;
- tránh sử dụng `this` trong constructor khi chưa hợp lệ và tránh đọc field trước khi gán;
- phân biệt normal return với exception path;
- triển khai/đọc một mẫu transformer dựa trên ASM `AdviceAdapter`;
- kiểm thử một chương trình Java 17+ có kế thừa, field initializer, constructor chaining và exception.

## 2. Vòng đời xây dựng object: ba giai đoạn khác nhau

Xét:

~~~java
class Base {
    Base() { /* body của Base */ }
}

class Child extends Base {
    String label = "field-init";
    final String id;

    Child(String id) {
        super();
        this.id = id;
    }
}
~~~

Ở mức khái niệm, khi chạy `new Child("ready")` trên Java 17:

~~~text
Cấp phát object:
    label = null, id = null          (giá trị mặc định của field)
        |
        v
Child.<init>(String) bắt đầu:
    this vẫn chưa hoàn thành bước khởi tạo theo verifier
        |
        v
invokespecial Base.<init>()
    Base khởi tạo phần thuộc Base và chạy body của Base
        |
        v
Lời gọi Base.<init>() trả về bình thường
    this có thể dùng được theo các quy tắc verifier áp dụng
        |
        v
Field initializer của Child chạy
    label = "field-init", id = null
        |
        v
Body constructor Child tiếp tục
    id = "ready"
        |
        v
RETURN của Child.<init>(String)
    constructor Child(String) hoàn tất bình thường
~~~

### 2.1. “Đã khởi tạo theo verifier” không đồng nghĩa “đã đủ state”

Bộ xác minh JVM quan tâm tới **tính hợp lệ kiểu của bytecode**. Chẳng hạn, trước initialization call phù hợp, tham chiếu local 0 có trạng thái verifier đặc biệt; nó không được tự do sử dụng như một reference bình thường. Sau khi lời gọi khởi tạo trên chính instance trở về bình thường, trạng thái verifier thay đổi.

Ứng dụng quan tâm tới **invariant**: `id` đã khác `null` chưa, collection đã được tạo chưa, dependency đã được gán chưa, cấu hình đã được kiểm tra chưa. JVM không tự suy ra những invariant nghiệp vụ này.

Vì vậy:

| Điểm đo | `this` hợp lệ như object đã initialized theo verifier? | Trạng thái ứng dụng có đầy đủ? | Mục đích phù hợp |
|---|---|---|---|
| Trước lời gọi khởi tạo `super/this` phù hợp | **Không được giả định** | Chưa | Chỉ đo bằng dữ liệu không đòi `this`, nếu bytecode và stack frame cho phép |
| Ngay sau lời gọi khởi tạo phù hợp trả về | Có thể dùng theo verifier | **Chưa chắc**; field initializer/body của lớp hiện tại có thể chưa chạy | Đếm/ghi sự kiện kỹ thuật, không đọc mọi field |
| Phần giữa constructor body | Thường có, nếu sau initialization call | Phụ thuộc trình tự gán | Đọc đúng field đã gán, tránh giả định toàn bộ object ready |
| Ngay trước `RETURN` của `<init>` | Có, nếu return hợp lệ | Constructor hiện tại hoàn tất **bình thường** | Success hook cho constructor cụ thể |
| `RETURN` của superclass constructor | Có đối với constructor lớp cha | Subclass có thể chưa khởi tạo | Không coi là hoàn tất toàn bộ dynamic object |
| Trước `ATHROW` hoặc trong exception handler | Phụ thuộc có đi qua initialization call hợp lệ chưa | Có thể đang dang dở | Không dùng `this` nếu không chứng minh được state; tách failure hook |

**Điểm đo nên dựa trên điều kiện cần của phép đo**, không chỉ dựa trên việc một callback báo “đã vào constructor”.

## 3. Quy tắc bytecode: uninitializedThis và invokespecial

### 3.1. Constructor không phải method thường

Trên JVM, constructor Java được biểu diễn bởi một instance initialization method có tên **`<init>`** và kiểu trả về `void`; constructor không được thừa kế như method thông thường. Khi class verifier phân tích code của constructor, **local 0** ban đầu thường mang verification type **`uninitializedThis`**.

Trước khi initialization call trên chính instance thành công, không thể xem `uninitializedThis` như một reference thường để:

- gọi tùy ý instance method;
- truyền trực tiếp như `Object` tới một probe như `Probe.observe(Object)`;
- đọc tùy ý instance field;
- công bố tham chiếu tới object chưa hoàn chỉnh.

Những thao tác đặc biệt dùng để tiến hành khởi tạo, như `invokespecial` đến `<init>` thích hợp, và một số dạng gán field bị ràng buộc bởi đặc tả, cần được phân tích theo quy tắc verifier; không được suy ra rằng mọi thao tác `ALOAD 0` đều hợp lệ với mọi mục đích.

Một sơ đồ bytecode **chỉ minh họa**, không phải kết quả disassemble đầy đủ:

~~~text
aload_0
invokespecial #Base.<init>:()V     ; khởi tạo lớp cha
; TỪ ĐÂY có thể thực hiện thao tác đòi reference đã initialized
aload_0
ldc "value"
putfield #Child.id:Ljava/lang/String;
return
~~~

Nếu thêm:

~~~text
aload_0
invokestatic #Probe.observe:(Ljava/lang/Object;)V
~~~

**trước** lời gọi khởi tạo phù hợp, JVM có thể từ chối class vì receiver của probe không phải một `java/lang/Object` initialized hợp lệ ở điểm đó. Tránh cách “đặt trước instruction đầu tiên của `<init>`” bằng visitor viết cho method thông thường.

### 3.2. Không chỉ tìm “lệnh invokespecial đầu tiên”

`invokespecial` dùng cho nhiều trường hợp (constructor, private method, special invocation) và có thể xuất hiện cho **một object khác** trong quá trình tính toán tham số constructor. Một lớp có thể thực hiện `new Helper()`, gọi `Helper.<init>` để chuẩn bị tham số rồi mới gọi `super(...)`; điều đó **không làm `this` thành initialized**.

Khi instrument constructor:

1. Nhận diện lời gọi **`<init>` trên receiver chính là `uninitializedThis`**, không phải mọi `invokespecial <init>`.
2. Chỉ xem constructor của chính object đã qua bước initialization call khi lệnh đó **hoàn thành bình thường**.
3. Nếu bytecode có nhánh hoặc exception handler, cần theo dõi verifier frame/stack chính xác, không đoán dựa vào vị trí text.
4. Dùng adapter/framework hiểu constructor thay vì tự chèn instruction khi không phân tích được state.

ASM `AdviceAdapter` hỗ trợ nhận diện pha này; không nên thay thế nó bằng kiểm tra “opcode đầu tiên bằng `INVOKESPECIAL`” thiếu điều kiện về receiver và control flow.

### 3.3. Nếu super() ném exception?

Nếu lời gọi constructor cha ném exception, object **không trở thành initialized bình thường** chỉ vì đã thực thi opcode `invokespecial`. Quy tắc verifier về exception edge xử lý đối tượng bị khởi tạo dang dở như không còn dùng được. Hook trên đường exception **không được sử dụng `this` như một đối tượng hoàn chỉnh**.

Vì vậy, không viết một catch-all handler bao phủ cả phần trước `super()` rồi dùng `ALOAD 0` gọi probe nhận `Object` trong handler ấy. Nếu cần ghi lỗi, hãy dùng thông tin an toàn như tên class hoặc mã lỗi; trường hợp bắt exception sau pha init cần đánh giá riêng.

## 4. Constructor chaining, kế thừa và field initializer

### 4.1. super(...) và this(...) khác nhau về vòng đời

- `super(...)` gọi constructor lớp cha. Khi superclass constructor trả về, trường và body của lớp con có thể **chưa được xử lý**.
- `this(...)` ủy quyền sang constructor khác **trong cùng lớp**. Constructor được gọi sẽ thực thi theo chuỗi; sau khi nó trả về, constructor ủy quyền tiếp tục phần thân còn lại.
- Mỗi constructor `<init>` là một method khác nhau ở cấp bytecode; mỗi method có `RETURN` riêng.

Ví dụ:

~~~java
Child() {
    this("ready");       // Chuyển sang Child(String)
    // Trở lại sau khi Child(String) trả về
}

Child(String id) {
    super();
    this.id = id;
}
~~~

Nếu transformer chèn “thành công” vào **mọi `RETURN` của mọi constructor**, một lần `new Child()` có thể ghi **hai success events**: một ở `Child(String)`, một ở `Child()`. Nếu còn kế thừa, constructor lớp cha cũng có thể ghi sự kiện riêng.

**Đếm constructor hoàn tất không nhất thiết bằng đếm object mới được cấp phát.** Với nhu cầu metric, phải xác định rõ đang đo số lượt chạy constructor, số object tạo xong, hay số factory operation.

### 4.2. Field initializer không nhất thiết xuất hiện ngay sau super ở source

Trong Java 17, compiler thường phát sinh các instruction thực hiện **instance field initializers và instance initializer blocks** sau khi lời gọi superclass constructor hoàn tất, trước phần thân còn lại của constructor không ủy quyền. Vì vậy, đặt probe ở **bytecode ngay sau `invokespecial super.<init>`** có thể chạy **trước** các initializer mà mã nguồn cho thấy ở đầu class.

Ví dụ `String label = "field-init";` có thể chưa được gán ở bytecode ngay sau `super.<init>`, dù dòng source field nằm trước khai báo constructor.

Một hook đặt ở **đầu phần thân constructor trong source Java** lại có thể nhìn thấy `label="field-init"` vì compiler đã chèn field initializer trước đoạn body đó. Không đánh đồng hai điểm đo.

### 4.3. Lớp cha không thể giả định state của lớp con đã đầy đủ

Khi constructor `Base` chạy, object thực tế có thể là instance của `Child`; các field của `Child` vẫn đang ở giá trị mặc định. Nếu lớp cha gọi method virtual đã bị override trong lớp con, code override có thể đọc state chưa sẵn sàng. Tránh triển khai probe sau `super()` bằng cách gọi một instance method có thể bị override.

Nếu cần quan sát object trong lúc xây dựng, ưu tiên **đo scalar an toàn** hoặc một probe tĩnh không lưu reference. Đừng đẩy `this` vào queue, thread, registry, callback ngoài hoặc cấu trúc shared state trước khi hoàn tất invariant.

## 5. Demo chạy được bằng Java 17: quan sát từng pha khởi tạo

Ví dụ sau là **mã Java đầy đủ**, không phụ thuộc ASM. Nó mô phỏng các vị trí mà một probe có thể được đặt bằng những lời gọi tường minh, giúp thấy **state thực tế**; sau đó ta dùng `javap` xem bytecode tương ứng.

Tệp **`ConstructorProbeDemo.java`**:

~~~java
public class ConstructorProbeDemo {
    static class Base {
        Base() {
            Probe.log("base-body", this);
        }
    }

    static final class Child extends Base {
        String label = "field-init";
        final String id;

        Child() {
            this("ready");
            Probe.log("delegating-exit", this);
        }

        Child(String id) {
            super();
            Probe.log("child-body-start", this);
            this.id = id;
            Probe.log("target-exit", this);
        }
    }

    static final class Fragile extends Base {
        Fragile(boolean fail) {
            super();
            if (fail) throw new IllegalArgumentException("boom");
            Probe.log("fragile-exit", this);
        }
    }

    static class Probe {
        static void log(String stage, Base object) {
            if (object instanceof Child child) {
                System.out.println(stage + ": label=" + child.label
                        + ", id=" + child.id);
            } else {
                System.out.println(stage + ": other");
            }
        }
    }

    public static void main(String[] args) {
        new Child();
        try {
            new Fragile(true);
        } catch (IllegalArgumentException expected) {
            System.out.println("caught:" + expected.getMessage());
        }
    }
}
~~~

**Biên dịch và kiểm tra verifier** (JDK 17 trở lên):

~~~bash
javac --release 17 ConstructorProbeDemo.java
java -Xverify:all ConstructorProbeDemo
~~~

**Stdout đã kiểm thử:**

~~~text
base-body: label=null, id=null
child-body-start: label=field-init, id=null
target-exit: label=field-init, id=ready
delegating-exit: label=field-init, id=ready
base-body: other
caught:boom
~~~

**Giải thích sáu dòng:**

1. `base-body`: constructor cha đã có thể truyền `this` cho static `Probe.log`, nhưng các field của `Child` vẫn là `null`. Đây là minh chứng rõ về **initialized theo cấp cha ≠ fully initialized theo lớp con**.
2. `child-body-start`: trong source của `Child(String)`, initializer của `label` đã thực thi nhưng `id` chưa được gán.
3. `target-exit`: đoạn gần kết thúc constructor có `id="ready"`.
4. `delegating-exit`: constructor `Child()` tiếp tục sau khi `this("ready")` trả về; object vẫn là một object, nhưng có **hai điểm kết thúc constructor**.
5. `base-body: other`: constructor cha cũng được gọi trong quá trình tạo `Fragile`.
6. `caught:boom`: `Fragile` ném exception; **không có `fragile-exit`** vì đường thành công không chạy.

**Giới hạn của demo:** Lời gọi `Probe.log` là code nguồn được đặt tại những điểm Java cho phép; nó không tự chèn vào bytecode của class khác. Ví dụ dùng `instanceof Child` để đọc field chưa sẵn sàng **chỉ trong môi trường test một thread**, nhằm minh họa rủi ro. Không sao chép việc phát tán `this` ở phase chưa hoàn chỉnh vào ứng dụng production.

### 5.1. Dùng javap để nhìn chính xác bytecode

Sau khi biên dịch, dùng:

~~~bash
javap -c -p 'ConstructorProbeDemo$Child'
~~~

Trên Bash, dấu nháy đơn bảo vệ ký tự `$` để shell không nội suy. Trong PowerShell, dấu nháy đơn cũng giữ nguyên chuỗi tên class lồng.

Các instruction quan trọng trong constructor **`Child(String)`**:

~~~text
0: aload_0
1: invokespecial ... Base."<init>":()V
4: aload_0
5: ldc           ... String field-init
7: putfield      ... Field label:Ljava/lang/String;
10: ldc          ... String child-body-start
...
16: aload_0
17: aload_1
18: putfield     ... Field id:Ljava/lang/String;
...
27: return
~~~

Các dấu `...` chỉ thể hiện những constant-pool index và phần chú thích đã rút gọn; đây là **trích dẫn instruction có chọn lọc**, không phải output nguyên bản dùng để copy-paste vào assembler. Nhờ nó, thấy rõ instruction gán `label` xuất hiện **sau** `Base.<init>` nhưng **trước** lời gọi `child-body-start` trong source.

Constructor **`Child()`** bắt đầu bằng `invokespecial ... Child."<init>":(Ljava/lang/String;)V` và có một `return` riêng. Chính điều đó khiến probe ở cuối mỗi `<init>` có thể đếm hai lần cho một lần tạo object.

### 5.2. Bài kiểm tra phản chứng

Nếu chuyển `Probe.log("target-exit", this)` lên trước `this.id = id`, Java vẫn biên dịch vì gọi probe **sau `super()`**, nhưng output sẽ in `id=null`. Không có `VerifyError`, song phép đo “đối tượng đã sẵn sàng” **sai về nghiệp vụ**.

Điều này củng cố kết luận: vượt qua verifier chỉ là **điều kiện cần**, không phải bằng chứng object đã có invariant mong muốn.

## 6. Đặt probe ở đâu cho đúng mục đích?

| Nhu cầu | Điểm chèn thường dùng | Có nên đọc `this`? | Cảnh báo |
|---|---|---|---|
| Đếm số lần **vào constructor** | Static counter ở điểm an toàn, hoặc đo tại call-site | Không cần | Không làm lỗi verifier; constructor chaining có thể tạo nhiều lượt |
| Biết khi nào **super/this initialization call đã thành công** | Hook sau initialization call được xác minh | Có thể, nhưng **không nên đọc state chưa xác định** | Field initializer và body có thể còn chạy |
| Đo **một constructor hoàn tất bình thường** | Ngay trước `RETURN` của chính `<init>` | Có thể trong điều kiện frame hợp lệ | Nhiều constructor cùng chạy cho một object |
| Đo object của **lớp cụ thể** có field đã gán | Sau những lệnh gán field cần thiết, hoặc trước `RETURN` của constructor lớp đó | Chỉ khi state thực sự sẵn sàng | Không suy rộng cho subclass chưa hoàn tất |
| Đo **object thực sự đã tạo xong** ở một call-site | Sau cặp cấp phát + constructor trả về thành công tại nơi gọi | Có thể, nếu reference đã hợp lệ | Không bao phủ object tạo ở mọi nơi |
| Đếm **constructor thất bại** | Lớp bảo vệ/exception path sau initialization call phù hợp; cân nhắc call-site | Thường không cần | `ATHROW` không bao trùm mọi lỗi phát sinh trong lời gọi con |
| Gắn timing end-to-end | Kết hợp điểm bắt đầu hợp lệ và mọi đường kết thúc cần đo | Thường không cần object reference | Tránh làm thay đổi hành vi constructor khi probe lỗi |

**Không có một injection point tuyệt đối đúng cho mọi phép đo.** Người thiết kế phải quyết định rõ đơn vị đo: **mỗi `<init>`**, **mỗi lần khởi tạo một loại object**, **mỗi lời gọi factory**, hay **mỗi lời gọi allocation ở call-site**.

## 7. Chèn bytecode bằng ASM AdviceAdapter

ASM là thư viện bên ngoài JDK, thường dùng trong Java agent để thăm và sinh bytecode. Module **`asm-commons`** cung cấp `AdviceAdapter`, một adapter hiểu được thời điểm constructor gọi initialization method, giúp triển khai hook an toàn hơn việc chèn opcode ở vị trí đầu method.

Theo tài liệu `AdviceAdapter`:

- `onMethodEnter()` được gọi ở đầu method thường, hoặc **sau initialization call thích hợp** trong constructor.
- `onMethodExit(int opcode)` được gọi trước instruction thoát method như `RETURN` hoặc `ATHROW`.
- Adapter theo dõi operand stack để nhận diện bước khởi tạo, thay vì dựa vào “`invokespecial` đầu tiên”.
- Callback không tự biết invariant nghiệp vụ của object. Sau `super(...)` vẫn không đồng nghĩa mọi field đã sẵn sàng.

### 7.1. Mẫu visitor chèn success hook trước RETURN

Ví dụ bên dưới là **một lớp helper hoàn chỉnh theo ASM 9.x**, nhưng **không phải chương trình Java 17 độc lập chỉ dùng JDK**: phải thêm thư viện `org.ow2.asm:asm` và `org.ow2.asm:asm-commons` tương thích, đồng thời có class `demo.ConstructorMetrics` trên classpath có thể nạp từ target loader.

~~~java
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.ClassVisitor;
import org.objectweb.asm.ClassWriter;
import org.objectweb.asm.MethodVisitor;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.commons.AdviceAdapter;

public final class ConstructorWeaver {
    public static byte[] instrument(byte[] original) {
        ClassReader reader = new ClassReader(original);
        ClassWriter writer = new ClassWriter(
                reader, ClassWriter.COMPUTE_MAXS);

        ClassVisitor visitor = new ClassVisitor(Opcodes.ASM9, writer) {
            private String owner;

            @Override
            public void visit(int version, int access, String name,
                    String signature, String superName,
                    String[] interfaces) {
                owner = name;
                super.visit(version, access, name,
                        signature, superName, interfaces);
            }

            @Override
            public MethodVisitor visitMethod(int access, String name,
                    String descriptor, String signature,
                    String[] exceptions) {
                MethodVisitor mv = super.visitMethod(
                        access, name, descriptor,
                        signature, exceptions);

                if (mv == null || !"<init>".equals(name)) {
                    return mv;
                }

                return new AdviceAdapter(
                        Opcodes.ASM9, mv, access, name, descriptor) {
                    @Override
                    protected void onMethodExit(int opcode) {
                        if (opcode != Opcodes.RETURN) {
                            return;
                        }

                        // Không cần ALOAD 0: tránh phát tán this.
                        visitLdcInsn(owner.replace('/', '.'));
                        visitMethodInsn(
                                Opcodes.INVOKESTATIC,
                                "demo/ConstructorMetrics",
                                "completed",
                                "(Ljava/lang/String;)V",
                                false);
                    }
                };
            }
        };

        reader.accept(visitor, ClassReader.EXPAND_FRAMES);
        return writer.toByteArray();
    }
}
~~~

**Kết quả logic**: trước mỗi `RETURN` của constructor, callback chèn lời gọi:

~~~java
demo.ConstructorMetrics.completed("ten.Class");
~~~

Dòng trên chỉ diễn giải **hiệu ứng bytecode**, không phải Java source tự phát sinh trong class đích. Probe nhận tên class thay vì `this`, giảm nguy cơ object escape, phụ thuộc invariant và giữ reference ngoài ý muốn.

Một helper đo đạc đơn giản (cần được đặt ở nơi class loader của ứng dụng tìm thấy) có thể là:

~~~java
package demo;

import java.util.concurrent.atomic.LongAdder;

public final class ConstructorMetrics {
    private static final LongAdder COMPLETED = new LongAdder();

    public static void completed(String className) {
        COMPLETED.increment();
    }

    public static long count() {
        return COMPLETED.sum();
    }
}
~~~

**Không tự diễn giải `COMPLETED` là số object duy nhất.** Với `this(...)` constructor chaining hoặc khi instrument cả class cha và con, phép đo có thể ghi nhiều lần cho một object. Nếu cần phân biệt, phải xác định constructor/entry point được instrument và đơn vị đo rõ ràng.

### 7.2. Khi nào nên dùng onMethodEnter()?

Nếu mục tiêu là đặt một probe kỹ thuật **ngay sau bước initialization call**, `AdviceAdapter.onMethodEnter()` là vị trí phù hợp trong transformer hiểu constructor. Nhưng **không đọc tất cả field của `this` tại đây**; field initializer và body vẫn có thể chưa chạy.

Mẫu logic cho hook rất nhẹ:

~~~java
@Override
protected void onMethodEnter() {
    // Chỉ ghi một metric không phụ thuộc field của this.
    visitMethodInsn(
            Opcodes.INVOKESTATIC,
            "demo/ConstructorMetrics",
            "constructorPhaseReached",
            "()V",
            false);
}
~~~

**Đây là trích đoạn** đặt trong subclass `AdviceAdapter`, không chạy độc lập; phương thức `ConstructorMetrics.constructorPhaseReached()` cần được triển khai riêng nếu dùng mẫu. Nếu cần quan sát `this`, chỉ dùng sau khi adapter xác định reference đã được khởi tạo theo verifier, đồng thời phải tự bảo đảm invariant phù hợp.

### 7.3. Những chi tiết kỹ thuật khi tích hợp agent

1. **Không chỉ thêm thư viện ASM vào source:** cần build, phân phối và làm cho thư viện phụ thuộc có thể nạp trong ngữ cảnh agent. Không dựa vào ASM nội bộ `jdk.internal.org.objectweb.asm` bằng `--add-exports` như giải pháp production.
2. **Không tự chèn hook vào mọi class:** lọc `className`, loader, module và tránh instrument class của agent, metrics helper, JVM core để khỏi recursion hoặc deadlock.
3. **Cần bảo toàn/verifier-correct bytecode:** ví dụ đơn giản thêm `invokestatic` trước `RETURN` chỉ làm tăng stack usage và dùng `COMPUTE_MAXS`. Khi đổi control flow, handlers hoặc frames, có thể cần `COMPUTE_FRAMES` và một strategy giải quyết superclass từ đúng class loader. Không mặc định tính frames là vô hại trong mọi runtime.
4. **Stack tại RETURN:** constructor trả `void`, nên `RETURN` không có return value trên stack. Nếu thêm code trước `ATHROW`, operand stack chứa throwable và phải bảo toàn đúng stack state.
5. **Khi retransform:** áp dụng cùng các giới hạn của `Instrumentation`, không thay field/method/class hierarchy tùy ý và phải kiểm soát instrument trùng.
6. **Helper method có thể ném exception:** nếu probe ném lỗi trước `RETURN`, nó có thể biến constructor vốn thành công thành thất bại. Đường hot path phải cực kỳ an toàn, được đo overhead và tránh I/O blocking.

### 7.4. Đo thời điểm constructor "hoàn tất" không đồng nghĩa hoàn tất subclass

Ngay cả mẫu ASM chỉ chèn trước `RETURN` cũng **không chứng minh object đã hoàn chỉnh ở mọi mức kế thừa**. Constructor `Base.<init>` có thể `RETURN` rồi constructor `Child.<init>` mới xử lý field, thậm chí có thể ném lỗi. Vì vậy metric này nên được đặt tên **constructor invocation completed** theo class/descriptor cụ thể, thay vì **object created successfully** nếu không thể chứng minh.

## 8. Constructor exception: normal path và exceptional path

### 8.1. RETURN so với ATHROW

- **`RETURN`** trong một constructor đại diện cho đường thoát bình thường của chính method `<init>`.
- **`ATHROW`** đại diện cho instruction ném throwable tường minh tại vị trí đó, nhưng **không phải mọi exception thoát khỏi method đều đi qua một `ATHROW` nằm trong chính method**.
- Exception có thể phát sinh do gọi method khác, field initializer, superclass constructor, array access hoặc VM checks rồi lan ra ngoài mà không đi qua một `ATHROW` do code của constructor phát ra ở đó.

Một visitor chỉ gọi `onMethodExit` trước opcode `ATHROW` có thể **không đo hết mọi exception path**. Để đo thất bại toàn diện, cần thiết kế try/catch/finally bao đúng vùng được phép và bảo toàn state verifier, hoặc đo ở **call-site/factory** nếu mục tiêu là thành công/thất bại của toàn quá trình tạo object.

### 8.2. Không dùng this nếu super chưa trả về bình thường

Nếu exception phát sinh **trước hoặc trong superclass initialization**, trạng thái `uninitializedThis` cần được xử lý theo quy tắc verifier và exception stack frame. Một handler mới tạo không được dùng `ALOAD 0` như initialized receiver chỉ vì code đó “chạy ở cuối method”.

Với failure hook, ưu tiên truyền **tên class, descriptor, exception category hoặc thời điểm**, thay vì object reference chưa chắc hợp lệ. Khi đã chắc chắn nằm sau bước khởi tạo và muốn đo state, vẫn cần kiểm tra invariant nghiệp vụ.

### 8.3. Đừng làm probe trở thành nguyên nhân thất bại

Một constructor bình thường:

~~~text
new Customer(...) --> init fields --> RETURN --> object hợp lệ
~~~

Nếu probe được chèn trước `RETURN`:

~~~text
new Customer(...) --> init fields --> Probe.report(...)
                                    |
                                    +--> report ném exception
                                            |
                                            v
                                   constructor không RETURN
~~~

Vì vậy, gọi probe từ constructor phải được thiết kế để **ít có khả năng ném lỗi**, không dùng logic nghiệp vụ hoặc export mạng đồng bộ, và có chiến lược fall-back phù hợp. Một hook “quan sát” làm thay đổi kết quả khởi tạo là lỗi instrumentation đáng kể.

## 9. Những tình huống cần đặc biệt cẩn trọng

### 9.1. Constructor của record

Record có canonical constructor và có thể dùng compact constructor. Trường record được compiler gán theo quy tắc ngôn ngữ; **không suy luận thời điểm từng field được ghi chỉ từ vị trí trong source**. Nếu cần đo trạng thái record hoàn chỉnh, kiểm tra bytecode `<init>` sau biên dịch, chỉ đọc field sau khi được gán và ưu tiên normal exit thích hợp.

### 9.2. Enum và compiler-generated constructors

Enum constructor có những tham số/chi tiết bytecode do compiler sinh ra ngoài tham số xuất hiện trong source. Đừng hardcode giả định “constructor luôn có descriptor `()V`”. Tìm theo tên `<init>` và descriptor thực tế, và xác minh loader/bytecode version. Những lớp do framework sinh cũng có thể chứa synthetic constructs.

### 9.3. Constructor với nhiều đường đi

Java source có thể có nhánh kiểm tra và throw. Những `RETURN` ở bytecode cần được xử lý nhất quán nếu mục đích là đếm thành công, không đặt hook tại một điểm source duy nhất rồi bỏ sót các đường khác. Với thay đổi control-flow, phải kiểm thử stack map frames, exception table và verifier.

### 9.4. JDK 25 và Flexible Constructor Bodies

Từ **JDK 25**, JEP 513 đưa **Flexible Constructor Bodies** thành tính năng chính thức: source Java có thể chứa một số câu lệnh **trước** `super(...)` hoặc `this(...)`. Early construction context vẫn có **hạn chế nghiêm ngặt** đối với việc tham chiếu instance đang tạo; một số thao tác gán field được cho phép, nhưng không thể tùy ý đọc `this` hoặc gọi instance method trước khi initialization call phù hợp.

Do đó, không viết quy tắc tuyệt đối “mọi statement trước super đều bị Java cấm” cho tất cả JDK hiện đại. Quy tắc an toàn với instrumentation vẫn là: **dựa vào trạng thái verifier và đường khởi tạo thực tế, không dựa vào độ dài của phần đầu constructor hoặc thứ tự instruction được đoán**. Ví dụ Java 17 ở mục 5 dùng các quy tắc source Java 17 và đã được biên dịch với `--release 17`.

### 9.5. Instrumentation không được làm this escape

Tránh:

~~~java
static void unsafeRegister(Object thisObject) {
    GlobalRegistry.put(thisObject);
    new Thread(() -> use(thisObject)).start();
}
~~~

Đây là **mẫu chống chỉ định**, không phải code đầy đủ biên dịch độc lập: `GlobalRegistry` và `use` chỉ minh họa hệ thống bên ngoài. Nó công bố reference trước khi có bằng chứng object đã đủ state. Trong môi trường đa luồng, hệ quả không chỉ là đọc giá trị mặc định mà còn là vấn đề **safe publication**, data race và invariant hỏng.

**Đếm bằng counter tĩnh** hoặc ghi tên class là cách giảm rủi ro, dù vẫn phải đo overhead và bảo đảm probe không ném lỗi.

## 10. Checklist thiết kế và kiểm thử

### 10.1. Trước khi viết transformer

- [ ] Xác định rõ đang đo **mỗi constructor**, **mỗi object hoàn chỉnh**, hay **call-site/factory**.
- [ ] Liệt kê các constructor có `super(...)`, `this(...)`, kế thừa và overload.
- [ ] Xem bytecode thực tế bằng `javap -c -p`, không tự suy từ source.
- [ ] Xác định mọi field cần đo đã được gán ở thời điểm hook hay chưa.
- [ ] Xác minh constructor của lớp cha có thể chạy trước mọi phần khởi tạo subclass.
- [ ] Xác định normal return khác exceptional exit, không đếm các instance tạo thất bại là thành công.
- [ ] Chọn library/adapter hiểu verifier frame `uninitializedThis`.
- [ ] Không yêu cầu helper giữ reference của object chưa hợp lệ.
- [ ] Phân biệt nơi code helper được load và đường classloader/module của class đích.

### 10.2. Sau khi transform class

- [ ] Classfile sinh ra được JVM verify; dùng `java -Xverify:all` trong bài thử cô lập.
- [ ] Không có `VerifyError`, `ClassFormatError` hoặc `NoClassDefFoundError` do helper không nạp được.
- [ ] Các nhánh constructor, `this(...)` và `super(...)` vẫn giữ đúng ngữ nghĩa.
- [ ] Success hook chạy **đúng đơn vị** đã định nghĩa (constructor invocation hay object count).
- [ ] Khi constructor throw, success hook không chạy sai.
- [ ] Khi superclass constructor throw, không sử dụng `this` trong exception handler chưa hợp lệ.
- [ ] Probe không ném exception, giữ lock quá lâu hoặc gây recursion.
- [ ] Kiểm tra state của superclass/subclass với field initializer và field `final`.
- [ ] Test cả runtime Java 17+ mục tiêu, bytecode version và nhiều classloader nếu áp dụng.
- [ ] Đo overhead ở hot path; log có rate limit và không kéo dài construction time.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Khuyến nghị |
|---|---|---|
| `VerifyError` khi chèn đầu `<init>` | Probe sử dụng `this` khi verifier vẫn coi là `uninitializedThis` | Đợi initialization call trên `this` hoàn thành, dùng adapter hiểu constructor |
| `this` hợp lệ nhưng field vẫn `null` | Field initializer/body chưa chạy hoặc superclass đang khởi tạo subclass object | Chọn điểm đo sau khi gán field cần thiết; không đồng nhất verifier state với invariant |
| Metric tăng hai lần khi tạo một object | Có `this(...)` delegation; mỗi constructor có `RETURN` | Định nghĩa lại đơn vị đo, chọn constructor phù hợp hoặc đo tại call-site |
| Metric tăng cả khi object cuối cùng không tạo được | Hook ở superclass trả về, nhưng subclass constructor ném exception | Không gọi đó là “object created”; đo sau full construction |
| Hook không bắt được mọi lỗi | Chỉ intercept opcode `ATHROW`, bỏ qua exception từ lời gọi khác | Thiết kế exception handler đúng vùng hoặc hook ở call-site |
| Bất ngờ khi instrument lớp được generate | Descriptor của constructor khác dự đoán, có synthetic code | Dựa vào `<init>`/descriptor bytecode và verifier thực tế |
| Lỗi classloader khi gọi helper | Lớp được instrument không tìm được `ConstructorMetrics` | Bố trí helper trong loader/module phù hợp, xử lý visibility |
| Method probe làm app không khởi động | Helper ném exception, gây deadlock, class loading recursion | Giảm phụ thuộc, tránh hoạt động blocking, có lỗi fallback |
| Lỗi stack map frame sau khi thêm branch | Cập nhật frames/max stack sai | Dùng đúng ASM compute strategy, kiểm tra JVM verifier và control flow |
| Constructor cha gọi override và đọc field con chưa gán | Dynamic dispatch xảy ra trong construction | Tránh gọi overridable instance methods trong hook sớm |

Để phân tích lỗi, trước hết xác định **opcode và frame** nơi JVM báo lỗi, constructor descriptor, parent class, đường đi của `super/this`, rồi so sánh bytecode trước/sau transform. Nếu stack trace báo `VerifyError: Bad type on operand stack`, kiểm tra nhất là luồng của `uninitializedThis` qua lệnh truyền tham số/gọi static hoặc instance probe.

## 12. Bài tập và câu hỏi tự đánh giá

### Bài tập A — dự đoán output trước khi chạy

Với `ConstructorProbeDemo`, dự đoán giá trị `label` và `id` tại `base-body`, `child-body-start`, `target-exit` và `delegating-exit`. Kiểm tra bằng lệnh `javac --release 17` và `java -Xverify:all` ở mục 5.

**Đáp án:** các cặp giá trị theo thứ tự là `(null, null)`, `("field-init", null)`, `("field-init", "ready")`, `("field-init", "ready")`.

### Bài tập B — đo mỗi constructor so với mỗi object

Giả sử instrument **cả** `Child()` và `Child(String)` bằng một success hook ở `RETURN`. Khi chạy `new Child()`, có bao nhiêu hook? **Hai**. Vì sao vẫn chỉ có một object? Vì `this(...)` gọi lại constructor trên cùng instance.

Mở rộng với superclass `Base` cũng có hook: nếu đếm cả constructor của Base, sẽ có thêm một success event cho lần tạo `Child` này. Hãy đặt lại tên metric thành `constructor_return_count` để tránh suy diễn thành `allocated_objects_count`.

### Bài tập C — thấy this hợp lệ nhưng state chưa sẵn

Đưa lời gọi `Probe.log("target-exit", this)` lên trước `this.id = id`. Java có thể compile nhưng dữ liệu khác. Điều đó chứng minh rằng **verifier correctness và semantic correctness khác nhau** như thế nào?

### Bài tập D — chọn điểm đo cho lỗi constructor

Thêm `throw new IllegalArgumentException("boom")` sau `super()`, rồi thử chèn một success probe trước `RETURN` và một probe trước `ATHROW`. Vì sao `ATHROW` chỉ bao phủ một phần các trường hợp? Chỉ ra một lỗi từ lời gọi constructor khác có thể lan ra mà bytecode ở constructor hiện tại không có `ATHROW` tương ứng.

### Bài tập E — phát hiện chèn sai vị trí

Một transformer tìm **opcode `INVOKESPECIAL` đầu tiên trong `<init>`** rồi đặt `ALOAD 0` + `Probe.observe(Object)` ngay sau nó. Hãy giải thích tại sao cách này có thể sai nếu instruction đó chỉ khởi tạo **đối tượng khác**, còn `super(...)`/`this(...)` trên chính instance chưa thực thi.

### Câu hỏi nhanh

1. **Vì sao `ALOAD 0` + gọi static hook nhận Object trước `super/this` có thể bị từ chối?** — Vì verifier chưa coi `uninitializedThis` là reference bình thường.
2. **Sau `super(...)`, field của subclass đã gán hết chưa?** — Không nhất thiết.
3. **`AdviceAdapter.onMethodEnter` ở constructor phù hợp thời điểm nào?** — Sau initialization call mà adapter theo dõi; không phải ngay bytecode đầu.
4. **Chèn trước `RETURN` có bảo đảm object của subclass đã sẵn sàng không?** — Không, nếu hook ở superclass; hơn nữa constructor chaining có nhiều return.
5. **`onMethodExit(ATHROW)` có bắt mọi exceptional exit?** — Không, có exception phát sinh từ các instruction/lời gọi khác.
6. **Khi probe không dùng `this`, còn rủi ro không?** — Có: classloader, exception từ probe, overhead, recursion và metric đếm sai đơn vị.
7. **JDK 25 có cho phép một số code trước `super(...)` trong source không?** — Có, với hạn chế early construction context; không được tự do sử dụng `this`.
8. **Kiểm tra cuối cùng để tránh lỗi verification?** — Disassemble, dùng verifier của JVM đích, test constructor chaining/exception và so sánh bytecode trước/sau.

## 13. Tóm tắt

**Quy tắc thiết kế quan trọng nhất:** khi chèn instrumentation vào constructor, **không sử dụng `this` như initialized object trước khi lời gọi khởi tạo thích hợp trên chính instance hoàn tất**. Sau điểm đó, hãy **tiếp tục xem xét tính đầy đủ của state nghiệp vụ**: field initializer, constructor body, `this(...)` delegation và superclass/subclass khiến “đã initialized theo verifier” khác “đã sẵn sàng”.

Nếu cần **đếm constructor hoàn tất bình thường**, chèn probe nhẹ ngay trước `RETURN` của constructor được chọn, không chặn cả `ATHROW` như thành công. Nếu cần **đếm object hoàn chỉnh**, phải định nghĩa thời điểm sau toàn bộ chuỗi khởi tạo, có thể phù hợp hơn ở call-site/factory. Dù dùng ASM `AdviceAdapter` hay công cụ khác, kiểm thử bytecode thực tế, stack map frames, exception path và classloader mới là bằng chứng cuối cùng.

### Tài liệu tham khảo chính thức

- [Java SE 17 JLS `12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): thứ tự superclass constructor, instance initializers, constructor body và dispatch trong quá trình tạo object.
- [Java SE 17 JVMS `4.10.1.9 — Type Checking Instructions](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10.1.9): quy tắc verifier cho `uninitializedThis`, `invokespecial` và exception edges.
- [ASM 9.x — AdviceAdapter](https://asm.ow2.io/javadoc/org/objectweb/asm/commons/AdviceAdapter.html): callback sau initialization call và trước `RETURN`/`ATHROW`.
- [JDK 25 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html): early construction context và quy tắc Java source trước `super(...)` hoặc `this(...)`.
- [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513): mốc hoàn thiện tính năng ngôn ngữ ở JDK 25.
