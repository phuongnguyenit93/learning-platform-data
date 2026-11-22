# Lời gọi đang chạy khác với lời gọi bắt đầu sau khi redefine

## 1. Bài toán: thay định nghĩa method giữa lúc JVM đang chạy

Giả sử một JVM đang phục vụ request. Thread A đã vào method `Service.work()` và vẫn đang thực thi. Cùng lúc, một Java agent gọi `Instrumentation.redefineClasses(...)`, cung cấp classfile mới với body `work()` đã thay đổi. Vậy thread A có nhảy từ đoạn code cũ sang code mới không? Lời gọi `work()` được tạo sau khi redefine sẽ chạy code nào?

**Quy tắc cốt lõi của Java Instrumentation:** Khi method được redefine có **active stack frames**, những frame đó **tiếp tục thực thi bytecode của phiên bản method cũ**. **Các method invocation mới** sau khi định nghĩa mới được cài sẽ sử dụng **method body mới**. Đây là hợp đồng của `Instrumentation.redefineClasses` trong Java SE 17, không đơn thuần là một hiện tượng ngẫu nhiên của `Thread.sleep` hay JIT.

Bài Knowledge này tập trung vào sự khác nhau giữa **lời gọi đang chạy** và **lời gọi bắt đầu sau redefine**, đồng thời trả lời những câu hỏi liên quan:

- “Cũ” và “mới” mô tả phiên bản **method body**, hay phiên bản **object**?
- Có cần tạo `new Service()` để code V2 có hiệu lực không?
- Instance fields và static fields có tự reset khi class được redefine không?
- Thời điểm nào đủ chắc chắn để công bố instrumentation V2 đã hoạt động?
- Khi rollback V2 về V1, những frame V2 đang sống có bị thay code giữa chừng không?
- Redefinition khác retransformation, class loading và application restart ở đâu?

Kết thúc bài có ví dụ **Java 17+ đầy đủ**: agent thực sự gọi `redefineClasses(new ClassDefinition(...))`, hai bản `HotMethod.class` cùng schema, hai `CountDownLatch` bảo đảm thứ tự, bytecode verifier, stdout đã được kiểm chứng và các bài tập mở rộng.

## 2. Active frame và new invocation là hai mốc khác nhau

### 2.1. Method invocation và stack frame

Mỗi lần gọi một method tạo một invocation mới; JVM sử dụng frame để chứa local variables, operand stack và trạng thái thực thi của lần gọi. Frame có thể vẫn hoạt động dù thread đang bị block bởi lock, latch, I/O hoặc lời gọi method khác.

~~~java
void process() {
    loadOrder();
    awaitSignal();
    commitOrder();
}
~~~

Đây chỉ là **đoạn code minh họa**, chưa có định nghĩa của `loadOrder`, `awaitSignal` và `commitOrder`. Nếu thread đã vào `process()` và đang chờ trong `awaitSignal()`, frame của `process` **chưa kết thúc**. Lời gọi đã bắt đầu từ trước khi agent thay definition.

### 2.2. Frame V1 không tự chuyển thành frame V2

Một frame của `process()` V1 có local variables và bytecode offset thuộc về V1. Nếu thay definition ngay trong lúc nó đang chờ, JVM **không tự sửa frame để tiếp tục từ một offset tương ứng trong V2**. Mặc dù VM có thể thực hiện deoptimization hoặc thay các compiled artifacts, nó vẫn duy trì **ngữ nghĩa V1** cho active frame.

Một invocation `process()` **bắt đầu sau khi redefinition thành công** dùng method body đã cập nhật V2. Đó là một frame khác; không phải frame V1 được khởi động lại.

### 2.3. Một object, nhiều thời điểm invocation

~~~text
service = new Service();                     // Chỉ một object

Thread A: service.work() gọi khi class = V1
              |
              +--> frame A (V1) chạy, rồi chờ
                                           Thread B:
                                           redefineClasses(Service, V2)
                                               |
                                           redefinition thành công
              |
Thread A:     +--> frame A tiếp tục bytecode V1, RETURN
                                           Thread B:
                                           service.work() gọi lần mới
                                               |
                                           frame B dùng V2, RETURN
~~~

Ở cả hai lần gọi, `service` là **cùng reference đã tạo từ trước**. Không có yêu cầu tạo object mới để V2 có hiệu lực. Tính “mới” trong **new invokes** nói về **lần gọi method mới**, không phải **instance mới**.

### 2.4. Điều gì không được suy ra?

- Redefine thành công **không có nghĩa mọi thread lập tức chạy V2**.
- Một frame cũ tiếp tục V1 **không có nghĩa nó giữ snapshot các field cũ**.
- Cả V1 và V2 có thể cùng xuất hiện trong JVM một thời gian; đó không nhất thiết là dấu hiệu update thất bại.
- Cần phân biệt **đã gửi yêu cầu redefine** với **API đã hoàn tất thành công**.
- Trong trường hợp invocation bắt đầu ngay lúc operation đang thực thi, không nên phân loại bằng timestamps thô; dùng đồng bộ để xác định trước/sau.

## 3. Hợp đồng chính thức của redefineClasses

API Java 17:

~~~java
void redefineClasses(ClassDefinition... definitions)
        throws ClassNotFoundException, UnmodifiableClassException;
~~~

Dòng này là **chữ ký rút gọn để học**, không phải một file Java độc lập. `Instrumentation` là interface trong module `java.instrument`. Java agent có thể nhận đối tượng `Instrumentation` qua `premain(String, Instrumentation)` khi JVM startup, hoặc `agentmain(String, Instrumentation)` nếu JVM hỗ trợ dynamic attach.

Điểm quan trọng của đặc tả `redefineClasses`:

1. Thay thế definition của **class đã được load** bằng những classfile bytes do caller cung cấp, không cần dựa vào file bytes cũ.
2. Được thiết kế để hỗ trợ các bản thay đổi kiểu debugger hot replace hoặc fix-and-continue. Có thể cập nhật **nhiều class** trong một lời gọi nếu chúng có phụ thuộc lẫn nhau.
3. **Active frames** của method đã redefine tiếp tục chạy **original bytecodes**.
4. **New method invocations** dùng definition đã redefine.
5. Không tự làm chạy lại class initialization; **giá trị static variables không tự reset**.
6. Các **instance hiện có không bị thay mới** vì redefine.
7. Replacement bytes được JVM/transformer liên quan xử lý và kiểm tra trước khi cài. Nếu API ném exception, **không class nào thuộc tập được yêu cầu được redefine**.

Điều 3 và 4 chính là trọng tâm của bài. Các điều 5 và 6 giải thích vì sao cùng một instance có thể chạy V1 rồi V2 mà vẫn giữ dữ liệu hiện có.

### 3.1. ClassDefinition là gì?

~~~java
new ClassDefinition(targetClass, replacementBytes)
~~~

`ClassDefinition` ghép chính xác một `Class<?>` đang tồn tại với `byte[]` chứa classfile mới. Tài liệu Java 17 cho biết constructor này **giữ tham chiếu tới mảng**, không tự sao chép. Do vậy, không mutate mảng trong lúc agent đang dùng nó để redefine. File bytes phải ứng với **đúng binary name/class identity** của target.

Đừng nhầm việc đọc `.class` từ ổ đĩa với việc JVM tự nạp lại class. Thao tác thay đổi chỉ xảy ra khi agent thực sự gọi `redefineClasses` và JVM chấp nhận.

### 3.2. Các điều kiện cần

~~~java
if (!inst.isRedefineClassesSupported()
        || !inst.isModifiableClass(targetClass)) {
    throw new IllegalStateException("Cannot redefine");
}

inst.redefineClasses(
        new ClassDefinition(targetClass, replacementBytes));
~~~

Đây là **trích đoạn** có các biến cần cung cấp từ agent. Trước khi dùng phải kiểm tra:

- **`isRedefineClassesSupported()`:** capability redefinition được JVM cấu hình và hỗ trợ.
- **`isModifiableClass(targetClass)`:** class cụ thể có thể thay đổi. Primitive classes và array classes không modifiable; VM có thể hạn chế những class khác.
- **Manifest của agent:** `Can-Redefine-Classes: true` trong main section.
- **Bytes:** đúng class name, classfile version, schema hợp lệ và dependencies có thể được nạp từ runtime/class loader phù hợp.

`Can-Redefine-Classes` **không phải** `Can-Retransform-Classes`. Chúng là hai capability riêng.

## 4. Dòng thời gian có thể kiểm chứng

~~~text
Thời điểm    Thread worker (old frame)              Thread main/agent
---------    -------------------------              ------------------------
t0           service.work() gọi khi là V1
t1           in OLD:entered
t2           phát tín hiệu ENTERED
t3           chờ RELEASE latch
t4                                                 nhận ENTERED
t5                                                 in main:before-redefine
t6                                                 đọc bytes V2
t7                                                 redefineClasses(...V2)
t8                                                 JVM xác minh/cài V2
t9                                                 in agent:redefine-ok
t10                                                in main:after-redefine
t11                                                mở latch RELEASE
t12          frame V1 tiếp tục, in OLD:resumed
t13          frame V1 return
t14                                                main gọi service.work()
t15                                                invocation mới chạy V2
t16                                                in NEW:invoked
~~~

Tại **t12**, dù cài V2 đã thành công ở t8, frame cũ tiếp tục V1. Tại **t15**, cùng object đó nhận invocation mới V2. Đây là cách chứng minh bằng hành vi, không chỉ dựa vào callback hoặc thông báo agent “đã update”.

**CountDownLatch** tạo quan hệ thứ tự xác định: worker không thể qua t12 trước khi main mở RELEASE, còn main không thể bắt đầu redefine trước khi worker đã phát ENTERED. So với `Thread.sleep(500)`, cách này tránh phụ thuộc máy nhanh/chậm, JIT, scheduler và GC.

## 5. Demo Java 17+: redefine trong khi frame V1 đang hoạt động

Ví dụ này đã được kiểm tra bằng một JVM thực có hỗ trợ redefinition. Ta tạo **hai bản classfile cùng tên `demo.HotMethod`**:

- **V1:** `work()` in `OLD:entered`, chờ latch, rồi in `OLD:resumed`.
- **V2:** `work()` in `NEW:invoked`.
- **RedefineAgent:** đọc file class V2 và dùng **`Instrumentation.redefineClasses(new ClassDefinition(...))`**.
- **Main:** tạo **một `HotMethod` duy nhất**, gọi V1 trên worker, đợi worker đã vào method, redefine sang V2, cho worker hoàn thành rồi gọi lại method mới.

Để kiểm tra state, cả V1 và V2 có cùng hai field: `private int count = 7` và `static int staticCounter = 100`. Main gán lại thành `9` và `777` trước khi gọi. Re-definition không reset các field này.

### 5.1. Bố cục tệp

~~~text
redefine-active-frame-lab/
├── agent.mf
├── src/
│   ├── agent/
│   │   └── demo/
│   │       └── RedefineAgent.java
│   ├── app/
│   │   └── demo/
│   │       └── Main.java
│   ├── v1/
│   │   └── demo/
│   │       └── HotMethod.java
│   └── v2/
│       └── demo/
│           └── HotMethod.java
└── out/                         # được tạo khi build
    ├── agent/
    ├── v1/
    ├── v2/
    └── redefine-agent.jar
~~~

Hai bản `HotMethod.java` có **cùng package và class name** nhưng được biên dịch **riêng**. Khi chạy main, **chỉ `out/v1` nằm trên classpath**; file V2 được agent đọc làm replacement bytes, không được nạp như class identity thứ hai.

### 5.2. Agent: src/agent/demo/RedefineAgent.java

~~~java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class RedefineAgent {
    private static Instrumentation inst;

    public static void premain(
            String options, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static void replace(
            Class<?> type, Path classFile) throws Exception {

        if (inst == null || !inst.isRedefineClassesSupported()
                || !inst.isModifiableClass(type)) {
            throw new IllegalStateException(
                    "Redefinition unavailable");
        }

        byte[] v2 = Files.readAllBytes(classFile);

        System.out.println("agent:redefine-start");
        inst.redefineClasses(new ClassDefinition(type, v2));
        System.out.println("agent:redefine-ok");
    }
}
~~~

Giải thích:

1. JVM truyền `Instrumentation` cho `premain` của agent. Thực nghiệm dùng **startup agent** để đơn giản hóa setup; việc **redefine diễn ra sau khi application và frame V1 đã hoạt động**.
2. `replace` kiểm tra capability của VM và class.
3. `Files.readAllBytes` đọc file class V2 đã được biên dịch sẵn; không parse source Java tại runtime.
4. `new ClassDefinition(type, v2)` dùng đúng target class đã nạp.
5. `redefineClasses` đưa bytes tới VM để kiểm tra/cài. Không cần tự đăng ký `ClassFileTransformer` cho kiểu replace trực tiếp này.
6. `agent:redefine-ok` chỉ xuất hiện sau khi API **trả về bình thường**. Nếu thao tác thất bại thì không có dòng này.
7. Trong các app có transformer khác đã đăng ký, các transformer đó vẫn có thể được gọi khi class được redefine. Vì vậy kết quả cuối còn phụ thuộc transformer chain; demo không có transformer phụ để giữ bài dễ quan sát.

### 5.3. Main: src/app/demo/Main.java

~~~java
package demo;

import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;

public final class Main {
    static final CountDownLatch ENTERED = new CountDownLatch(1);
    static final CountDownLatch RELEASE = new CountDownLatch(1);

    public static void main(String[] args) throws Exception {
        HotMethod service = new HotMethod();
        service.setCount(9);
        HotMethod.staticCounter = 777;

        Thread oldFrame = new Thread(service::work, "v1-frame");
        oldFrame.start();

        ENTERED.await();
        System.out.println("main:before-redefine");

        try {
            RedefineAgent.replace(
                    HotMethod.class, Path.of(args[0]));
            System.out.println("main:after-redefine");
        } finally {
            RELEASE.countDown();
            oldFrame.join();
        }

        service.work();
    }
}
~~~

Giải thích:

- **`service` chỉ được tạo một lần**. Main và worker cùng gọi method trên chính instance ấy.
- `ENTERED` chỉ mở sau khi worker đã **vào V1.work()**, bảo đảm đây là frame V1 thực sự.
- `RELEASE` giữ worker ở bên trong method V1 cho tới khi main thực hiện redefine.
- `finally` luôn mở RELEASE và `join` worker để không treo test vô hạn nếu redefine ném lỗi.
- `service.work()` lần cuối chỉ được gọi **sau khi API redefine đã trả về thành công** và worker cũ kết thúc, khiến thứ tự log ổn định.
- Việc gán `count=9` và `staticCounter=777` trước khi khởi chạy worker cho phép ta quan sát cả version V1 và V2 đều thấy cùng state.

### 5.4. V1: src/v1/demo/HotMethod.java

~~~java
package demo;

public final class HotMethod {
    static int staticCounter = 100;
    private int count = 7;

    public void setCount(int value) {
        count = value;
    }

    public void work() {
        System.out.println("OLD:entered count=" + count +
                " static=" + staticCounter);
        Main.ENTERED.countDown();

        try {
            Main.RELEASE.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }

        System.out.println("OLD:resumed count=" + count +
                " static=" + staticCounter);
    }
}
~~~

Khi worker vào `work()`, nó in `OLD:entered` rồi chờ `Main.RELEASE.await()`. Frame `work` **vẫn đang hoạt động** khi thread ở trạng thái chờ. Sau khi main thay definition và giải phóng latch, chính frame đó in `OLD:resumed`, không gọi lại `work` từ đầu.

### 5.5. V2: src/v2/demo/HotMethod.java

~~~java
package demo;

public final class HotMethod {
    static int staticCounter = 100;
    private int count = 7;

    public void setCount(int value) {
        count = value;
    }

    public void work() {
        System.out.println("NEW:invoked count=" + count +
                " static=" + staticCounter);
    }
}
~~~

Điểm khác biệt **duy nhất có chủ ý** ở bài này là body `work()`. Cả hai class có cùng package/name, modifiers, fields, constructor mặc định và method descriptors. Giữ schema tương ứng giúp tránh giới hạn của HotSwap/redefinition về thêm/xóa fields, methods, thay signature và hierarchy.

Mặc dù source V2 vẫn ghi `staticCounter = 100` và `count = 7`, **redefine không làm chạy lại `<clinit>` hoặc constructor**, nên những giá trị đang lưu vẫn là **777** và **9**.

### 5.6. Manifest: agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: demo.RedefineAgent
Can-Redefine-Classes: true

~~~

Lưu file với newline kết thúc; thuộc tính nằm trong **main section**. `Premain-Class` định danh agent entry point được gọi bởi `-javaagent`. `Can-Redefine-Classes: true` yêu cầu JVM cấp quyền redefine; triển khai JVM vẫn có thể không hỗ trợ, do đó test phải kiểm tra capability runtime.

Không dùng `Can-Retransform-Classes: true` để thay thế: đây là **cơ chế khác**.

### 5.7. Biên dịch và đóng gói

Đứng tại thư mục gốc `redefine-active-frame-lab`. Trong Bash:

~~~bash
mkdir -p out/agent out/v1 out/v2
~~~

Trong PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/v1, out/v2
~~~

Sau đó chạy JDK tools từ gốc project:

~~~bash
javac --release 17 -d out/agent src/agent/demo/RedefineAgent.java
javac --release 17 -cp out/agent -d out/v1 src/v1/demo/HotMethod.java src/app/demo/Main.java
javac --release 17 -d out/v2 src/v2/demo/HotMethod.java
jar --create --file out/redefine-agent.jar --manifest agent.mf -C out/agent .
~~~

Vì sao đúng thứ tự:

1. `RedefineAgent` phải compile trước để `Main` có thể tham chiếu nó.
2. `Main` cùng V1 `HotMethod` được build trong `out/v1`.
3. V2 `HotMethod` được build vào `out/v2` **riêng**, tránh ghi đè V1.
4. Agent JAR chứa class `RedefineAgent` và manifest, không chứa V1/V2 `HotMethod`.
5. `--release 17` bảo đảm classfile target Java 17 và API dùng trong source không vượt phạm vi release 17.

Có thể kiểm tra:

~~~bash
jar --list --file out/redefine-agent.jar
javap -p -s -classpath out/v1 demo.HotMethod
javap -p -s -classpath out/v2 demo.HotMethod
javap -c -p -classpath out/v1 demo.HotMethod
javap -c -p -classpath out/v2 demo.HotMethod
~~~

Trong output `javap`, kiểm tra cùng method `work()V` và `setCount(I)V` ở cả hai bản, còn body `work` khác nhau. Không đặt `out/v2` trong classpath của lệnh chạy target.

### 5.8. Chạy ứng dụng và quan sát chính xác output

~~~bash
java -Xverify:all -javaagent:out/redefine-agent.jar -cp out/v1 demo.Main out/v2/demo/HotMethod.class
~~~

Lệnh này dùng một JVM:

- Agent được nạp khi startup để lấy `Instrumentation`, nhưng **không gọi redefine trong `premain`**.
- Application dùng V1 từ `out/v1`, tạo instance, chạy worker V1, rồi gọi agent để redefine.
- File `out/v2/demo/HotMethod.class` được đọc làm **bytecode mới**, không làm JVM nạp một class identity riêng biệt.
- `-Xverify:all` yêu cầu tăng cường bytecode verification trong môi trường thử nghiệm.

**Stdout đã xác nhận bằng JVM thực, khi capability redefine được hỗ trợ:**

~~~text
OLD:entered count=9 static=777
main:before-redefine
agent:redefine-start
agent:redefine-ok
main:after-redefine
OLD:resumed count=9 static=777
NEW:invoked count=9 static=777
~~~

Nếu API bị cấm, V2 sai schema/format, hoặc file không tìm thấy, chương trình sẽ báo lỗi thay vì có một chuỗi output thành công như trên. Hãy đối chiếu **log của JVM đích** cùng exception nếu kết quả khác.

### 5.9. Điều gì chứng minh bài học?

| Dòng stdout | Phát ra từ đâu? | Kết luận |
|---|---|---|
| `OLD:entered count=9 static=777` | Worker vào `work()` V1 | Frame V1 đã bắt đầu trước redefine |
| `main:before-redefine` | Main sau khi nhận ENTERED | Worker đã vào frame V1 và đang chờ |
| `agent:redefine-start` | Agent trước lời gọi API | Bắt đầu thay definition |
| `agent:redefine-ok` | Agent sau lời gọi API trả về | JVM đã chấp nhận thao tác redefine |
| `main:after-redefine` | Main | Main tiếp tục sau update |
| `OLD:resumed count=9 static=777` | **Frame V1 đã có sẵn** | Dù class đã cập nhật, frame cũ vẫn chạy bytecode V1 |
| `NEW:invoked count=9 static=777` | **Invocation mới trên cùng service** | Method V2 dùng cho invocation mới, state không bị reset |

Đặc biệt, V2 **không chứa** lệnh in `OLD:resumed`. Việc dòng đó xuất hiện sau khi redefine thành công cho thấy frame V1 cũ thực sự đã được JVM cho chạy tiếp.

## 6. Bytecode cũ không có nghĩa dữ liệu cũ

Một active V1 frame giữ **method bytecode version V1**, nhưng các lệnh đọc field trong V1 vẫn tham chiếu **object và static variables đang tồn tại**. Nếu thread khác ghi field sau redefine, frame cũ có thể đọc giá trị mới, tuân theo **Java Memory Model/happens-before**.

Ví dụ:

~~~text
Frame V1 đang chờ, object.count = 9
main redefine method -> V2
main cập nhật object.count = 41 (có đồng bộ hợp lệ)
frame V1 tiếp tục đọc object.count -> có thể đọc 41
invocation V2 mới cũng đọc cùng object.count
~~~

**Method version và data version là hai trục độc lập.** Điều mà `redefineClasses` không làm là tự reset state và tự chạy initializer. Nó không đóng băng trạng thái của object theo lúc frame bắt đầu.

Trong demo, main gán `count=9` và `staticCounter=777` **trước khi tạo worker**, nên hai lời gọi cùng thấy các giá trị ấy. `CountDownLatch` bảo đảm thứ tự giữa các thread trong thí nghiệm.

### 6.1. New invoke trên một instance cũ

Một cách tự kiểm tra là đặt thêm:

~~~java
System.out.println(service == originalService);
~~~

Đây là **trích đoạn**, cần biến `originalService` cùng kiểu và scope trong ứng dụng. Kết quả sẽ true nếu chỉ là alias của `service`; không cần tạo instance mới để method definition V2 có hiệu lực.

Class identity của `HotMethod.class` cũng được giữ nguyên. Redefinition **không giống** việc tạo một `URLClassLoader` mới để nạp class cùng tên.

### 6.2. Frame caller cũ có thể gọi callee phiên bản mới

Một nuance quan trọng: nếu caller `process()` đã bắt đầu bằng V1, nhưng sau khi thức dậy nó **tạo một invocation mới** của `helper()` đã được redefine sang V2, frame `helper` mới có thể chạy V2. Do đó trong **một request**, stack có thể chứa một frame V1 và một frame V2 đồng thời.

Không diễn giải “frame cũ tiếp tục mã cũ” thành “tất cả method mà request cũ gọi sau này cũng bị khóa ở V1”. Ranh giới bảo đảm nằm **ở mỗi method invocation**, không phải cả request như một snapshot nhất quán toàn hệ thống.

## 7. Hai phiên bản method có thể tồn tại đồng thời

Trong demo, `join` cho phép frame V1 kết thúc trước khi main tạo invocation V2 để log dễ đọc. Nhưng nếu main gọi `service.work()` ngay sau `agent:redefine-ok`, **trước khi giải phóng worker V1**, sẽ có thời điểm:

~~~text
Thread worker: frame HotMethod.work() từ V1 -> vẫn chờ RELEASE
Thread main:   frame HotMethod.work() mới V2 -> in NEW:invoked
~~~

Cùng object, cùng `Class<?>`, nhưng **hai stack frames được tạo ở hai thời điểm khác nhau**. Không cần hai loader và không cần hai JVM.

### 7.1. Nhiều lần redefine liên tiếp

Nếu update **V1 → V2 → V3**, có thể cùng thời điểm có:

- một frame rất dài đã vào V1 trước update thứ nhất;
- một frame đã vào V2 sau update thứ nhất;
- invocation mới sau update thứ hai chạy V3.

Không có cơ chế mặc định nào buộc cả ba frame chuyển sang V3 lập tức. Đây là lý do hotfix có thể tạo **giai đoạn chuyển tiếp nhiều phiên bản** dù cập nhật definition thành công.

### 7.2. Rollback cũng không ép frame quay về bản cũ

Giả sử sau V2 bạn gọi redefine đưa V1 trở lại. **Invocation mới sau rollback** dùng V1, nhưng **active frame V2** đã tạo trước rollback vẫn tiếp tục V2. Điều này có thể làm log “NEW” xuất hiện sau thời điểm thông báo rollback, mà không nhất thiết nghĩa là rollback không được áp dụng.

Muốn khôi phục definition phải **cung cấp bytes V1 và gọi `redefineClasses` lần nữa**; tắt agent hoặc remove transformer không tự hoàn nguyên method body đã cài.

## 8. Redefine khác retransformation, reload và restart

| Cơ chế | Bytecode input | Active frames | New invokes | State/identity |
|---|---|---|---|---|
| `redefineClasses` | `ClassDefinition(Class, byte[])` do công cụ cung cấp | Tiếp tục old method bytecodes | Dùng redefined method nếu thành công | Giữ class identity và object state |
| `retransformClasses` | Chạy lại transformation pipeline của class đã nạp | Tiếp tục old method bytecodes | Dùng retransformed method nếu thành công | Giữ identity/state |
| Nạp class cùng tên bằng loader khác | Loader định nghĩa một class identity khác | Frame của identity cũ không tự đổi | Phụ thuộc class identity/reference được gọi | Có thể có hai loại class cùng tên nhưng không đồng nhất |
| Restart JVM | Nạp lại ứng dụng trong process mới | Frame cũ thuộc process đã kết thúc | Chạy version từ process mới | In-memory state thường phải xây dựng lại |

Hai API Instrumentation có cùng quy tắc **active frame cũ/new invoke mới**, nhưng có **nguồn bytes và workflow khác**:

- **Redefine**: bạn cung cấp classfile replacement, thích hợp với debugger/hot replace code đã biên dịch. Capability là `Can-Redefine-Classes: true`.
- **Retransform**: VM chạy lại các transformer tương ứng; thích hợp khi muốn instrument class đang nạp. Capability là `Can-Retransform-Classes: true`.

Đừng tưởng rằng đổi file `.class` trên đĩa rồi gọi `retransformClasses` sẽ khiến JVM tự đọc file đó. Nếu muốn dùng replacement bytes đã biên dịch, `redefineClasses` nêu rõ ý định ấy.

**Không nhầm với `ClassLoader.defineClass`**: class đã được nạp không thể tự bị “nạp đè” chỉ bằng load class trùng tên trong loader hiện tại.

## 9. Giới hạn schema và tính toàn vẹn classfile

Redefinition trong một JVM đang sống phải giữ những ràng buộc phù hợp với instance, call sites, vtables và layout hiện có. Không mặc định JVM cho phép thay đổi tùy ý số field/method hoặc superclass chỉ bằng cách cung cấp classfile khác.

Ví dụ V2 an toàn cho bài thực hành:

~~~text
V1 HotMethod:
  static int staticCounter
  int count
  void setCount(int)
  void work() { ... OLD ... }

V2 HotMethod:
  static int staticCounter
  int count
  void setCount(int)
  void work() { ... NEW ... }

==> Cùng class schema, chỉ thay body của work()
~~~

Nếu thêm field `private String newField` **chỉ ở V2**, JVM phổ biến như HotSpot có thể từ chối vì thay schema không được hỗ trợ. Nếu đổi binary class name trong classfile, có thể xuất hiện `NoClassDefFoundError`. Nếu classfile major vượt JDK đích, có thể xuất hiện `UnsupportedClassVersionError`. Nếu bytes không hợp lệ, có thể có `ClassFormatError`, `VerifyError` hoặc `LinkageError` tương ứng.

### 9.1. Những dữ liệu nên kiểm tra trước khi redefine

- Binary class name, defining class loader và module.
- Major/minor version của V1/V2 classfile.
- Field/method names, descriptors và access flags trong phạm vi VM cho phép.
- Superclass và interfaces.
- Stack map frames và bytecode verification.
- Dependencies/helper classes được gọi từ V2 có sẵn trong runtime đích.
- Kiểu dữ liệu static/instance mà code V2 sẽ đọc trên object có nguồn gốc từ V1.
- Nếu có nhiều agent, transformer chain có thể biến đổi replacement bytes trước lúc VM cài.

### 9.2. Lỗi khi thực hiện set nhiều class

`redefineClasses` cho phép truyền **nhiều `ClassDefinition`** trong một lời gọi khi cần cập nhật các class phụ thuộc lẫn nhau:

~~~java
inst.redefineClasses(
        new ClassDefinition(First.class, firstBytes),
        new ClassDefinition(Second.class, secondBytes));
~~~

Đây là **đoạn mã minh họa**, với biến `inst`/`firstBytes`/`secondBytes` cần được cung cấp. Theo Javadoc, nếu lời gọi ném exception, **không class nào trong tập yêu cầu được redefine**. Tuy nhiên, kể cả khi áp dụng thành công một nhóm class, **các active frames cũ vẫn có thể tiếp tục mã phiên bản cũ**. “Cùng cài definition” không đồng nghĩa “mọi thread có cùng code version trong suốt request”.

## 10. Lỗi thường gặp và cách nhận diện

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm chứng và xử lý |
|---|---|---|
| `isRedefineClassesSupported()==false` | VM hoặc manifest chưa cho phép redefine | Xem `Can-Redefine-Classes: true` trong agent JAR và runtime configuration |
| `isModifiableClass(target)==false` | Class cụ thể không thể sửa đổi | Không ép thay; chọn mục tiêu hoặc cơ chế khác |
| `UnmodifiableClassException` | Có class không modifiable trong tập | Lọc class trước, quản lý kết quả update |
| `UnsupportedOperationException` | VM không hỗ trợ hoặc thay đổi cấu trúc bị cấm | So sánh schema V1/V2, chỉ đổi method body hợp lệ |
| `ClassFormatError` / `VerifyError` | Replacement class bytes không hợp lệ | Kiểm tra `javap`, verifier và công cụ sinh bytecode |
| `UnsupportedClassVersionError` | Target JVM không hỗ trợ classfile major của V2 | Build bằng `--release` phù hợp và test JVM mục tiêu |
| `NoClassDefFoundError` | Binary name không khớp hoặc thiếu dependency theo tình huống cụ thể | Kiểm tra tên classfile, loader và full exception message |
| Worker còn in OLD sau `agent:redefine-ok` | **Đúng hợp đồng**, active frame cũ giữ V1 | Dùng một **invocation mới** để chứng minh V2 |
| Invocation mới vẫn in OLD | Redefine thất bại, nhầm class loader, V2 không thật sự đổi hoặc class đã bị đổi tiếp | Xác nhận API return, replacement bytes và class identity |
| Static field về default khác mong đợi | Code agent/app đã thay field, không phải do redefine tự chạy initializer | Phân tích side effects, không giả định state tự reset |
| Log OLD/NEW trộn trong cùng request | Một frame V1 có thể gọi method mới V2 | Ghi version marker ở từng method hoặc invocation |
| Rollback rồi vẫn thấy NEW | Có active frame V2 chưa thoát | Phân biệt thời điểm bắt đầu frame và thời điểm rollback thành công |

**Khuyến nghị:** không căn cứ vào thời điểm log completion duy nhất để kết luận method V2 đang hay chưa chạy. Ghi nhận thời điểm invocation **bắt đầu**, thời điểm redefinition **thành công**, class identity và phiên bản probe/definition.

## 11. Tác động tới tracing, metrics và hotfix

### 11.1. Span cũ có thể thiếu telemetry mới

Giả sử `Checkout.process()` V1 bắt đầu lúc t0, redefinition sang V2 có thêm tracing entry hook ở t1, và request V1 kết thúc ở t2. Frame V1 **không tự có** mã instrumentation được chèn vào V2. Một request khác bắt đầu sau t1 có thể ghi entry span qua method V2.

~~~text
Request A:
t0: enter Checkout.process() V1 ------------ active frame --------- t2 return
                                             ^
                                             t1 redefine to V2

Request B:
t3: enter Checkout.process() V2 --> trace hook --> business code --> return
~~~

Đừng coi thiếu span của request A là lỗi exporter chỉ vì request hoàn tất sau t1. Cần xác minh request bắt đầu trước hay sau cutover; cũng cần kiểm tra các method sâu hơn được invoke sau cutover có thể dùng code mới.

### 11.2. Code hotfix phải chịu trạng thái cũ

Một method V2 có thể chạy trên **instance đã được khởi tạo bởi constructor V1**. Nếu V2 kỳ vọng dữ liệu mới không tồn tại hoặc protocol mới không tương thích, lỗi nghiệp vụ vẫn có thể xuất hiện dù classfile hợp lệ và redefinition thành công.

Khi thay đổi business behavior, không chỉ kiểm tra `java -Xverify:all`. Cần test integration và tình huống **old code đang chạy ↔ new code vừa được cài**, đặc biệt khi có transaction, database state, queue consumer, caches hoặc long-running tasks.

### 11.3. Không có cam kết latency không đổi

VM có thể cần safepoint, handshake, deoptimization hoặc invalidation compiled code tùy triển khai để giữ ngữ nghĩa. API không cam kết `redefineClasses` luôn nhanh hoặc hoàn toàn không gây pause.

Đo thực tế:

- thời gian `redefineClasses` và số lần lỗi;
- p95/p99 của request trong giai đoạn cập nhật;
- CPU, allocation/GC, JIT/deoptimization;
- số class/loader mục tiêu và thời gian frames cũ tồn tại;
- số request mới được instrument đúng và telemetry drop;
- rủi ro của helper method nếu V2 gọi sang thư viện không nhìn thấy từ class loader đích.

## 12. Các hiểu nhầm phổ biến

**“Redefine xong toàn bộ thread sẽ chạy V2 ngay.”** Sai. Chỉ invocation **mới** dùng definition mới. Active frame từ V1 tiếp tục V1.

**“Object V1 vẫn luôn chạy method V1.”** Sai. Object cũ có thể nhận invocation mới và chạy V2. Không cần tạo object mới.

**“Frame V1 bị đóng băng cả dữ liệu.”** Sai. V1 bytecode vẫn có thể đọc field hiện tại theo đồng bộ/JMM.

**“Source V2 có field initializer nên redefine sẽ reset field.”** Sai. Redefinition không chạy lại constructor/`<clinit>` chỉ vì replacement bytes được cài.

**“Đã ghi file .class V2 ra ổ đĩa là đủ.”** Sai. Cần `ClassDefinition` và `redefineClasses`.

**“Nếu Can-Retransform-Classes=true thì redefine chắc chắn hoạt động.”** Sai. Phải kiểm tra riêng `Can-Redefine-Classes` và `isRedefineClassesSupported()`.

**“Cùng binary name là cùng class.”** Sai nếu class được định nghĩa bởi các class loader khác nhau. Dùng đúng `Class<?>`, không chỉ so tên.

**“Một lần redefine thành công thay đổi được mọi class layout.”** Sai. Schema changes có giới hạn.

**“Chỉ cần đếm số callback transformer để biết V2 đã cài.”** Sai. Cần API hoàn thành và test **new invocation**.

**“Rollback làm mọi frame V2 quay lại V1 ngay lập tức.”** Sai. Active V2 frames có thể còn sống; invocation mới sau rollback mới dùng definition được khôi phục.

## 13. Bài luyện tập

### Bài tập A — dự đoán output

Trước khi chạy demo, viết đúng thứ tự bảy dòng stdout. Giải thích tại sao `OLD:resumed` xuất hiện **sau** `agent:redefine-ok` mà vẫn là OLD.

**Đáp án:** frame worker đã bắt đầu V1 trước redefine; khi latch mở, nó **tiếp tục V1**, không tạo invocation V2. Lời gọi mới ở cuối `Main` mới chạy V2.

### Bài tập B — chạy V1 và V2 cùng thời điểm

Chuyển lời gọi `service.work()` của main tới **ngay sau `main:after-redefine` nhưng trước `RELEASE.countDown()`** (điều chỉnh `try/finally`). Vì body V2 không chờ latch, nó có thể in NEW khi worker V1 vẫn đang bị block. Tại sao điều này không đòi class loader mới?

### Bài tập C — thay state nhưng không thay schema

Đổi `service.setCount(9)` thành `service.setCount(31)`, và `HotMethod.staticCounter = 777` thành `= 502`. Chạy lại. Vì sao cả V1/V2 có thể nhìn thấy giá trị mới thay vì initializer mặc định 7 và 100?

### Bài tập D — kiểm tra capability

Bỏ `Can-Redefine-Classes: true` khỏi manifest rồi build JAR mới, chạy trên JVM tôn trọng capability này. Vì sao `isRedefineClassesSupported()` không còn bảo đảm true? Nếu false, chương trình nên phản ứng thế nào?

### Bài tập E — cố tình thay class schema

Thêm một field mới **chỉ ở V2**, build lại, chạy test trên VM đang dùng. Nếu JVM từ chối redefine, nó báo lỗi ở tầng nào? Vì sao không thể suy rằng mọi object V1 sẽ tự có field layout mới?

### Bài tập F — rollback khi có active V2 frame

Cho V2 `work()` chờ một latch riêng, tạo frame V2, rồi redefine về V1. Dự đoán frame V2 đang chờ sẽ dùng code nào sau khi thức dậy và invocation mới sau rollback sẽ dùng code nào.

### Câu hỏi tự kiểm tra

1. **Frame đang chạy khi redefine có đổi bytecode giữa chừng không?** Không.
2. **Invocation mới trên chính instance cũ có dùng V2 không?** Có, sau update thành công.
3. **`redefineClasses` có cần một `ClassDefinition` chứa bytes thay thế không?** Có.
4. **Static initializer có chạy lại khi redefine không?** Không.
5. **Capability manifest dành riêng cho redefine là gì?** `Can-Redefine-Classes: true`.
6. **Nếu API ném exception khi cập nhật tập nhiều lớp, có một phần tập được redefine không?** Theo Javadoc, không.
7. **Một frame V1 có thể gọi một method mới V2 không?** Có, nếu invocation của callee bắt đầu sau update.
8. **Khi nào nên xác minh hiệu quả update?** Bằng **new invocation** sau `redefineClasses` thành công.

## 14. Tổng kết và tài liệu chuẩn

**Redefinition cập nhật method definition cho lời gọi tương lai, không ghi đè instruction stream của những stack frame đã bắt đầu.** Trong một JVM có thể đồng thời tồn tại active frame V1 và invocation V2 trên **cùng class identity, cùng object**, với static và instance state vẫn được giữ. Đây là điều phải nắm khi phân tích trace thiếu entry span, thay method hotfix, rollback và đo độ phủ instrumentation.

Muốn kiểm chứng kết luận, hãy sử dụng test có đồng bộ thật như `CountDownLatch`, đối chiếu output của active frame trước/sau redefine và của invocation mới, đồng thời kiểm tra API đã trả về thành công. Đừng dùng timestamps ngẫu nhiên hoặc chỉ dựa vào thông báo callback.

Tài liệu chính thức:

- [Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `redefineClasses`, active stack frames, new invokes, static state, lỗi và giới hạn.
- [Java SE 17 — ClassDefinition](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): cặp class identity và replacement byte array.
- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `-javaagent`, `premain`/`agentmain` và thuộc tính manifest.
- [Java SE 17 — UnmodifiableClassException](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html): điều kiện class không modifiable.
- [JVMTI 17 — RedefineClasses](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#RedefineClasses): ngữ nghĩa VM cấp thấp cho method versions.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): công cụ đồng bộ giúp tạo output xác định.
