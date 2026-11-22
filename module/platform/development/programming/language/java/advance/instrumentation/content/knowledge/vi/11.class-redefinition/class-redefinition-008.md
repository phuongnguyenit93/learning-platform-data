# Redefinition: thay đồng thời các lớp phụ thuộc và đánh giá kết quả toàn tập

Trong Java Instrumentation, **Instrumentation.redefineClasses(ClassDefinition... definitions)** cho phép một Java agent thay **định nghĩa của nhiều lớp đã được JVM nạp** trong **cùng một yêu cầu**. Đây là khả năng quan trọng khi thay đổi của lớp A phụ thuộc vào thay đổi đồng thời của lớp B: ví dụ một lớp API gọi sang lớp Repository, hoặc một bộ điều phối và một bộ xử lý cần dùng cùng phiên bản thuật toán.

Theo hợp đồng Java SE 17, **redefineClasses vận hành trên một tập để hỗ trợ các thay đổi liên quan nhau**. Nếu **chính lời gọi đó ném exception**, **không lớp nào trong tập được redefine bởi lời gọi ấy**. Điều này khác hẳn việc gọi redefineClasses(A) trước rồi redefineClasses(B) sau: nếu A được cài thành công còn B thất bại, JVM **không tự hoàn nguyên A** chỉ vì B thuộc lần gọi tiếp theo.

Bài này giải thích **ClassDefinition**, capability **Can-Redefine-Classes**, giới hạn thay đổi class schema, lựa chọn các lớp phụ thuộc, tính nguyên tử ở cấp class definitions, cách kiểm tra **toàn tập sau cập nhật**, và một ví dụ Java 17+ chạy được với **ba kịch bản**: cập nhật đồng thời thành công, batch thất bại toàn bộ, và hai lời gọi riêng tạo kết quả cập nhật một phần.

## 1. Mục tiêu học tập

Sau khi học, bạn cần làm được:

1. Phân biệt **redefineClasses** với **retransformClasses** và class loading mới.
2. Dùng **ClassDefinition(Class<?> theClass, byte[] theClassFile)** để gắn **đúng Class object** với một class file thay thế.
3. Hiểu vì sao cần đưa những class phụ thuộc về mặt định nghĩa vào **cùng một lời gọi redefineClasses(...)**.
4. Phân tích chính xác bảo đảm **all-or-none khi lời gọi thất bại** và giới hạn của bảo đảm đó.
5. Kiểm tra **isRedefineClassesSupported()** và **isModifiableClass(...)**, xác định đúng defining class loader/module.
6. Chuẩn bị bytecode hợp lệ: giữ tên lớp và những phần class schema không được phép thay đổi.
7. Xác minh **toàn bộ nhóm**, không kết luận thành công chỉ từ một class hoặc một log transformer.
8. Phân biệt definition mới với **active stack frames**, instance/static state và các side effect có thể vẫn còn.
9. Có phương án rollback/retry và quan sát trạng thái mà không tạo lỗi “nửa phiên bản cũ, nửa phiên bản mới”.

## 2. Vì sao phải thay nhiều lớp như một tập?

Giả sử ứng dụng có:

~~~java
// Mã source minh họa kiến trúc, không phải file chạy độc lập.
public final class Api {
    public static String route() {
        return "API_V1>" + Store.value();
    }
}

public final class Store {
    public static String value() {
        return "STORE_V1";
    }
}
~~~

Một thay đổi logic cần đưa cả hai sang phiên bản 2:

~~~text
Api V1 ───── gọi ─────> Store V1
   │                      │
   │                       └── trả STORE_V1
   └── format API_V1>STORE_V1

Muốn chuyển sang:
Api V2 ───── gọi ─────> Store V2
   │                      │
   │                       └── trả STORE_V2
   └── format API_V2>STORE_V2
~~~

Nếu chỉ thay Api trước, trong một khoảng thời gian ứng dụng có thể nhận **API_V2>STORE_V1**. Nếu hai lớp chỉ thay *nội dung method* mà vẫn giữ hợp đồng nhị phân, trạng thái trộn này không nhất thiết gây lỗi JVM; nhưng có thể sai nghiệp vụ, ví dụ phiên bản giao thức A cần dữ liệu mới chỉ phiên bản B hiểu đúng.

Một yêu cầu:

~~~java
// Đoạn minh họa bên trong agent/service đã có Instrumentation inst.
inst.redefineClasses(
    new ClassDefinition(Api.class, apiV2Bytes),
    new ClassDefinition(Store.class, storeV2Bytes)
);
~~~

cho phép JVM xử lý hai **class definitions liên quan** trong cùng một lời gọi. Ngược lại:

~~~java
// Hai lời gọi độc lập, KHÔNG phải một transaction.
inst.redefineClasses(
    new ClassDefinition(Api.class, apiV2Bytes)
);
inst.redefineClasses(
    new ClassDefinition(Store.class, storeV2Bytes)
);
~~~

không có bảo đảm rollback xuyên qua ranh giới hai lời gọi. Nếu lần thứ hai lỗi, Api đã được cài ở lần thứ nhất có thể tiếp tục là V2.

### 2.1. Kết quả tập khác kết quả từng lớp

| Trường hợp | Một lời gọi redefine(A2, B2) | Hai lời gọi redefine(A2), rồi redefine(B2) |
| --- | --- | --- |
| Cả A2/B2 hợp lệ | Lời gọi thành công, hai định nghĩa được cập nhật | Cả hai lời gọi có thể thành công |
| B2 không phải class file hợp lệ | **Lời gọi ném lỗi; không A2 hay B2 nào được cài từ lời gọi này** | A2 có thể đã được cài; B2 thất bại |
| B không modifiable | Yêu cầu thất bại, không cài phần tử nào | Nếu A đã được cài trước, JVM không hoàn nguyên A |
| Muốn kiểm chứng một phiên bản logic đồng bộ | Dễ gắn một version/operation ID cho cả nhóm | Phải tự điều phối các lần cập nhật độc lập |
| Retry | Có thể sửa nguyên nhân rồi gửi lại toàn bộ nhóm | Phải biết chính xác lần nào đã thành công để tránh sai version |

Đối với các class phụ thuộc, **ranh giới nguyên tử của yêu cầu** phải phản ánh **ranh giới tương thích của logic nghiệp vụ**; chọn một tập quá nhỏ có thể khiến ứng dụng tạm thời hoặc lâu dài chạy hai phiên bản không đồng bộ.

## 3. Redefinition hoạt động ở tầng nào của JVM?

**redefineClasses** không tạo một Class mới có tên trùng tên cũ. Nó yêu cầu JVM thay **định nghĩa** của một **Class object đã load**, trong giới hạn JVM cho phép. Những object hiện có vẫn là instance của class đó; fields/static state không tự trở về trạng thái khởi tạo.

Sơ đồ khái niệm:

~~~text
Trong một JVM đang chạy:

Class A (v1)    Class B (v1)
       │           │
       └─────┬─────┘
             │  agent đã có Instrumentation
             ▼
  chuẩn bị ClassDefinition(A.class, bytesV2_A)
  chuẩn bị ClassDefinition(B.class, bytesV2_B)
             │
             ▼
    redefineClasses(defA, defB)
             │
       ┌─────┴─────┐
       │           │
  toàn bộ hợp lệ   bất kỳ class nào gây lỗi
       │           │
       ▼           ▼
  Cài cả tập       Ném exception
  định nghĩa mới   Không class nào trong
                   yêu cầu ấy được redefine
~~~

**ClassDefinition** chỉ là đối tượng Java giữ **Class<?> mục tiêu** và **byte[] của class file mới**. Byte[] phải mô tả **cùng lớp đó** và phù hợp các ràng buộc về schema; không thể truyền file của một class tên khác rồi yêu cầu JVM “đổi danh tính” class đang chạy.

### 3.1. Giao diện chính xác trong Java 17

~~~java
// Các chữ ký API JDK 17. Đoạn tham khảo, không là file độc lập.
boolean isRedefineClassesSupported();
boolean isModifiableClass(Class<?> theClass);

void redefineClasses(ClassDefinition... definitions)
    throws ClassNotFoundException, UnmodifiableClassException;
~~~

**ClassNotFoundException** vẫn xuất hiện trong chữ ký vì lý do tương thích API; Javadoc Java 17 lưu ý exception này **không thể được ném bởi phương thức hiện tại**. Các lỗi class format, linkage và unsupported change có thể là **Error** hoặc runtime exception, không được gói thành checked exception thông thường.

### 3.2. ClassDefinition giữ tham chiếu tới mảng bytes

Javadoc của constructor **ClassDefinition(Class, byte[])** nêu rõ nó **không sao chép byte[]**, mà giữ tham chiếu tới mảng do caller truyền. Vì vậy:

~~~java
// Minh họa: cần giữ mảng ổn định trong lúc yêu cầu sử dụng nó.
byte[] stableBytes = Files.readAllBytes(path);
ClassDefinition definition =
        new ClassDefinition(targetClass, stableBytes);

// Tránh làm điều này trước/trong lúc redefine:
stableBytes[0] = 0; // Có thể phá header và làm dữ liệu đầu vào thay đổi.
~~~

Đoạn trên dùng **Files** và **Path** đã được import ở file thực tế; nó chỉ minh họa quyền sở hữu dữ liệu. Nên tạo dữ liệu thay thế hoàn chỉnh, kiểm tra/hash trước rồi **coi byte[] là bất biến** cho đến khi yêu cầu kết thúc; nếu có nhiều thread chuẩn bị/triển khai, dùng snapshot/copy và điều phối ownership rõ ràng.

## 4. Capability: cần Can-Redefine-Classes, không phải Can-Retransform-Classes

**Redefinition** và **retransformation** là hai khả năng tùy chọn **khác nhau**:

| API | Mục tiêu | Capability manifest |
| --- | --- | --- |
| **redefineClasses(...)** | Cài class file bytes được caller cung cấp | **Can-Redefine-Classes: true** |
| **retransformClasses(...)** | JVM chạy lại quá trình transform từ class bytes nền | **Can-Retransform-Classes: true** |

Đối với startup Java agent, manifest cho ví dụ:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.AgentEntry
Can-Redefine-Classes: true
~~~

Ngay cả khi manifest khai báo **true**, JVM vẫn phải thực sự hỗ trợ capability. Kiểm tra trong code:

~~~java
// Đoạn minh họa bên trong agent đã nhận Instrumentation inst.
if (!inst.isRedefineClassesSupported()) {
    throw new IllegalStateException("Class redefinition unavailable");
}
~~~

Nếu capability không được cấp, **redefineClasses** có thể ném **UnsupportedOperationException**. **isModifiableClass** trả true chỉ là một điều kiện cần, không đồng nghĩa chắc chắn redefine được: schema, class file version, tên nội bộ, linker/verifier và những transformer khác vẫn có thể khiến yêu cầu thất bại.

### 4.1. Tránh chọn sai lớp trong class loader phức tạp

**Class<?>** là định danh thực của lớp đang chạy, không phải chỉ một chuỗi FQCN. Hai plugin có thể cùng có **com.example.Service**, được định nghĩa bởi hai class loader khác nhau; đó là **hai kiểu JVM khác nhau**. Một file class lấy từ JAR plugin A rồi áp vào Class của plugin B có thể không phù hợp, ngay cả khi tên giống nhau.

Nếu cần tìm Class đã load, có thể duyệt **inst.getAllLoadedClasses()**, lọc đúng binary name, defining class loader, module và các tiêu chí cần thiết. Không tự thay bằng **Class.forName("...")** nếu điều đó làm load lớp mới hoặc chọn nhầm loader.

### 4.2. Array/primitive classes và một số lớp JVM đặc biệt

Theo Javadoc Java 17, **primitive classes** và **array classes** không modifiable. Vì vậy không đưa **int[].class** hoặc **int.class** vào yêu cầu với mong muốn thay bytecode của chúng. Kiểm tra từng lớp:

~~~java
for (Class<?> type : targets) {
    if (!inst.isModifiableClass(type)) {
        throw new IllegalArgumentException(
            "Class not modifiable: " + type.getName()
        );
    }
}
~~~

Một lớp có thể modifiable nhưng vẫn không chấp nhận class bytes mới do vi phạm giới hạn schema. Preflight giúp tìm lỗi sớm, **không thay thế kiểm tra trong redefineClasses**.

## 5. Giới hạn thay đổi: không phải hot deployment tùy ý

Trong Java 17, khả năng redefine class đã nạp **không cho phép mọi dạng thay đổi source**. Những thay đổi thường bị cấm hoặc bị giới hạn ở mức JVM TI bao gồm:

- Thêm hoặc xóa field/method của lớp đã định nghĩa.
- Thay tên lớp, supertype hoặc những quan hệ kế thừa không được phép.
- Thay descriptor/signature của method hoặc field theo cách làm đổi class schema đã load.
- Thay một số access/modifier, cấu trúc liên quan đến record/nest/module và thuộc tính mà JVM không hỗ trợ cập nhật.
- Đưa class bytes sai version/không hợp lệ hoặc tên nội bộ khác tên lớp cần redefine.

Những thay đổi phù hợp thường là **thay nội dung method body** trong giới hạn schema hiện hữu; compiler có thể tạo constant pool/Code attribute khác nếu định nghĩa vẫn hợp lệ. Trong ví dụ dưới đây, cả hai phiên bản của mỗi class có **cùng tên package, tên class, constructor và cùng phương thức public static với descriptor không đổi**; chỉ thay giá trị string và code bên trong.

**Lưu ý:** Không tự kết luận rằng mọi thay đổi được phép ở class loading cũng được phép ở redefine. Dự án thật phải xác minh với JVM TI/JDK thực tế và chạy kiểm thử verifier/linkage trên bản bytes mới.

### 5.1. Tránh thay giao thức nhị phân giữa hai class khi không được phép

Ví dụ bạn muốn đổi **Store.value():String** thành **Store.value(int):String** rồi đổi **Api.route()** để gọi descriptor mới. Dù muốn redefine cả hai cùng lúc, JVM thông thường **không cho đổi bộ method/schema như vậy** cho các class đã load. Tính nguyên tử của tập không biến thay đổi không hợp lệ thành hợp lệ.

Nếu cần nâng cấp giao thức nhị phân kiểu đó, hãy thiết kế **phiên bản API từ trước**, dùng **indirection/helper**, class loader mới hoặc rolling restart tùy môi trường. Dùng batch redefine cho những phiên bản **tương thích với giới hạn JVM**.

## 6. Bài thực hành Java 17+: thay hai lớp phụ thuộc trong một yêu cầu

Bài thực hành **không dùng thư viện bytecode bên ngoài**. Ta biên dịch **hai bộ source song song**, một bộ đang chạy phiên bản 1, một bộ tạo các file class phiên bản 2. Agent nạp khi JVM khởi động, cung cấp handle Instrumentation cho ứng dụng mẫu. Ứng dụng đọc **bytes phiên bản 2 trên đĩa** rồi gọi redefineClasses.

Ba mode được thiết kế rõ ràng:

- **batch-ok**: class file phiên bản 2 của Api và Store đều hợp lệ, gửi **một** redefineClasses(defApi, defStore).
- **batch-bad**: Api V2 hợp lệ nhưng bytes Store cố ý không phải class file; gửi cả hai **cùng một** redefineClasses, dự kiến **không cài class nào**.
- **split-bad**: gọi redefineClasses(Api V2) trước, thành công, sau đó gọi redefineClasses(Store invalid) và thất bại; minh họa **kết quả cập nhật một phần do hai yêu cầu độc lập**.

### 6.1. Cấu trúc thư mục

~~~text
redefine-batch-demo/
  agent.mf
  src/
    agent/
      demo/
        AgentEntry.java
    base/
      demo/
        Api.java
        Store.java
        Main.java
    patch/
      demo/
        Api.java
        Store.java
~~~

Hai file cùng tên **Api.java** ở **src/base** và **src/patch** có cùng FQCN **demo.Api** nhưng được biên dịch vào **hai thư mục output khác nhau**, không bao giờ compile chung một lượt. Tương tự với **demo.Store**.

### 6.2. File agent: src/agent/demo/AgentEntry.java

~~~java
package demo;

import java.lang.instrument.Instrumentation;

public final class AgentEntry {
    private static volatile Instrumentation instrumentation;

    private AgentEntry() {
    }

    public static void premain(String options, Instrumentation inst) {
        if (inst == null) {
            throw new IllegalArgumentException("Instrumentation missing");
        }
        if (instrumentation != null) {
            throw new IllegalStateException("Agent installed twice");
        }
        instrumentation = inst;
    }

    public static Instrumentation required() {
        Instrumentation current = instrumentation;
        if (current == null) {
            throw new IllegalStateException(
                    "Start JVM with -javaagent:redefine-agent.jar"
            );
        }
        return current;
    }
}
~~~

**Instrumentation** do JVM truyền vào **premain**. **volatile** bảo đảm reference đã gán được đọc an toàn từ thread khác theo Java Memory Model, nhưng ví dụ chỉ có một thread. Trong hệ thống thật cần điều phối các yêu cầu redefine cạnh tranh và vòng đời agent. Đừng tự tạo implementation của Instrumentation hoặc nghĩ rằng mọi ứng dụng có thể lấy Instrumentation từ một API toàn cục.

### 6.3. File manifest: agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: demo.AgentEntry
Can-Redefine-Classes: true
~~~

**Manifest phải có newline cuối file**. Đây là **startup agent** dùng **-javaagent**, không phải dynamic attach; nếu nạp agent sau startup cần **Agent-Class** và **agentmain** phù hợp.

### 6.4. Hai lớp phiên bản 1: src/base/demo/Api.java và Store.java

**File src/base/demo/Api.java**

~~~java
package demo;

public final class Api {
    private Api() {
    }

    public static String route() {
        return "API_V1>" + Store.value();
    }
}
~~~

**File src/base/demo/Store.java**

~~~java
package demo;

public final class Store {
    private Store() {
    }

    public static String value() {
        return "STORE_V1";
    }
}
~~~

**Api.route()** trực tiếp gọi **Store.value()** ở runtime; nó không chỉ đọc một **static final String field** có nguy cơ bị inline khi compile. Hai class có quan hệ gọi thực sự, nên nếu chỉ redefine Api, method Api V2 sẽ gọi vào Store V1. Ta sẽ quan sát trạng thái trộn đó ở mode split-bad.

### 6.5. Hai lớp phiên bản 2: src/patch/demo/Api.java và Store.java

**File src/patch/demo/Api.java**

~~~java
package demo;

public final class Api {
    private Api() {
    }

    public static String route() {
        return "API_V2>" + Store.value();
    }
}
~~~

**File src/patch/demo/Store.java**

~~~java
package demo;

public final class Store {
    private Store() {
    }

    public static String value() {
        return "STORE_V2";
    }
}
~~~

Hai phiên bản có **cùng package, tên lớp, constructor và method descriptor**, chỉ đổi string literal trong method. JVM được phép redefine phần method body nếu capability và những điều kiện còn lại thỏa mãn.

**Không** thay phương thức **Store.value()** thành **value(int)** hoặc thêm field mới trong bản patch; những việc đó sẽ làm hỏng mục tiêu kiểm thử tính nguyên tử bằng một lỗi schema độc lập không được dự kiến.

### 6.6. Bộ điều phối: src/base/demo/Main.java

~~~java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Main {
    private Main() {
    }

    private static String snapshot() {
        return Api.route() + "|" + Store.value();
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2
                || (!"batch-ok".equals(args[0])
                    && !"batch-bad".equals(args[0])
                    && !"split-bad".equals(args[0]))) {
            throw new IllegalArgumentException(
                    "Usage: Main batch-ok|batch-bad|split-bad patch-dir"
            );
        }

        String mode = args[0];
        Path patchDir = Path.of(args[1]);

        Instrumentation inst = AgentEntry.required();
        if (!inst.isRedefineClassesSupported()) {
            throw new IllegalStateException(
                    "This JVM/agent lacks class redefinition capability"
            );
        }
        if (!inst.isModifiableClass(Api.class)
                || !inst.isModifiableClass(Store.class)) {
            throw new IllegalStateException(
                    "Api or Store is not modifiable"
            );
        }

        // Đảm bảo cả hai class đã load/chạy phiên bản V1.
        String before = snapshot();
        System.out.println("BEFORE=" + before);

        // Đọc các class file V2 đã biên dịch riêng.
        byte[] apiV2 = Files.readAllBytes(
                patchDir.resolve("demo/Api.class"));
        byte[] storeV2 = Files.readAllBytes(
                patchDir.resolve("demo/Store.class"));

        if (!"batch-ok".equals(mode)) {
            // Cố ý tạo ClassDefinition không hợp lệ cho Store:
            // class file ngắn và không có magic CAFEBABE.
            storeV2 = new byte[] {0, 1, 2, 3};
        }

        ClassDefinition apiDef =
                new ClassDefinition(Api.class, apiV2);
        ClassDefinition storeDef =
                new ClassDefinition(Store.class, storeV2);

        boolean failed = false;
        try {
            if ("split-bad".equals(mode)) {
                // Hai yêu cầu riêng: Api có thể đã được cài
                // trước khi Store thất bại.
                inst.redefineClasses(apiDef);
                inst.redefineClasses(storeDef);
            } else {
                // MỘT yêu cầu cho cả tập lớp phụ thuộc.
                inst.redefineClasses(apiDef, storeDef);
            }
            System.out.println("REDEFINE_OK");
        } catch (UnmodifiableClassException
                 | UnsupportedOperationException
                 | LinkageError error) {
            failed = true;
            System.out.println("REDEFINE_FAILED");
        }

        String after = snapshot();
        System.out.println("AFTER=" + after);

        String expected = switch (mode) {
            case "batch-ok" -> "API_V2>STORE_V2|STORE_V2";
            case "batch-bad" -> before;
            case "split-bad" -> "API_V2>STORE_V1|STORE_V1";
            default -> throw new AssertionError("Unknown mode");
        };

        boolean expectFailure = !"batch-ok".equals(mode);
        if (failed != expectFailure || !expected.equals(after)) {
            throw new AssertionError(
                    "Unexpected redefine result: " + after
            );
        }
        System.out.println("CHECK=PASS");
    }
}
~~~

**Giải thích chi tiết:**

1. **AgentEntry.required()** lấy reference **Instrumentation** đã được JVM cấp ở startup. Nếu chạy mà không có agent, chương trình fail rõ, không giả vờ redefine thành công.
2. **isRedefineClassesSupported()** kiểm tra capability, còn **isModifiableClass(...)** xác nhận từng lớp có thể được xét redefine.
3. **snapshot()** gọi **Api.route()** và **Store.value()** trước khi đọc patch, làm cả hai class được load và phản ánh phiên bản V1.
4. **Files.readAllBytes** đọc **hai file .class riêng**, chứa bytes hoàn chỉnh đã compile của cùng FQCN. Mã không sử dụng API để “recompile trong JVM”.
5. **ClassDefinition** ghép mỗi **Class object của JVM hiện tại** với **bytes V2 tương ứng**. Dữ liệu được giữ ổn định trong suốt lời gọi.
6. **batch-ok** và **batch-bad** dùng **một** phương thức **redefineClasses(apiDef, storeDef)**.
7. **split-bad** gọi redefine **Api** xong rồi mới gọi redefine **Store**. Bước thứ nhất có thể commit trước khi bước thứ hai thất bại.
8. Với chế độ lỗi, Store nhận một mảng **không phải class file hợp lệ**, để yêu cầu phản hồi thất bại. Đó là **test fixture cố ý**; không được dùng mảng lỗi trong agent production.
9. Các exception **ClassFormatError** và nhiều lỗi class format/linkage là subclass của **LinkageError**, được catch trong ví dụ. **ClassNotFoundException** có trong throws của API vì tương thích, nhưng không dự kiến xuất hiện; **main throws Exception** giữ chữ ký đơn giản.
10. Assertion cuối phân biệt **kết quả đúng của từng mode** và in **CHECK=PASS** chỉ khi kết quả thực sự phù hợp. Nếu implementation không hỗ trợ redefine, chương trình fail fast và không in một transcript thành công giả.

**Điều phải nhớ:** Trong mode **batch-bad**, **Api V2 có thể được kiểm tra/chuyển tới JVM trước khi Store bị từ chối**, nhưng vì **cùng một lời gọi thất bại**, Api không được cài từ batch đó. Ngược lại, trong **split-bad**, API không có cơ chế rollback qua hai lời gọi, nên kết quả cuối có thể là **Api V2 + Store V1**.

### 6.7. Biên dịch và đóng gói trên JDK 17

Trong thư mục gốc của project, với **shell POSIX** (Linux/macOS hoặc môi trường bash tương đương):

~~~bash
mkdir -p build/agent build/base build/patch

# Compile agent trước, đóng gói JAR có Premain-Class.
javac --release 17 -d build/agent src/agent/demo/AgentEntry.java
jar cfm redefine-agent.jar agent.mf \
    -C build/agent demo/AgentEntry.class

# Compile ứng dụng V1, tham chiếu AgentEntry từ JAR.
javac --release 17 -cp redefine-agent.jar \
    -d build/base \
    src/base/demo/Api.java \
    src/base/demo/Store.java \
    src/base/demo/Main.java

# Compile hai class V2 độc lập vào thư mục patch.
javac --release 17 -d build/patch \
    src/patch/demo/Api.java \
    src/patch/demo/Store.java
~~~

Với Windows PowerShell/cmd, dùng cùng các lệnh **javac/jar**, nhưng viết mỗi lệnh trên **một dòng** thay vì dùng backslash nối dòng. Tạo thư mục bằng cú pháp phù hợp hệ điều hành.

Kết quả:

~~~text
build/
  agent/
    demo/AgentEntry.class
  base/
    demo/Api.class
    demo/Store.class
    demo/Main.class
  patch/
    demo/Api.class
    demo/Store.class
redefine-agent.jar
~~~

Lưu ý: **build/base** phải chứa đúng V1, **build/patch** chứa đúng V2. Tuyệt đối không ghi V2 vào build/base trong khi thử, vì ví dụ cần JVM bắt đầu từ V1 để kiểm chứng kết quả. Kiểm tra JAR:

~~~bash
jar tf redefine-agent.jar
~~~

Phải có **META-INF/MANIFEST.MF** và **demo/AgentEntry.class**.

### 6.8. Chạy batch hợp lệ: batch-ok

~~~bash
java -javaagent:redefine-agent.jar \
    -cp "build/base:redefine-agent.jar" \
    demo.Main batch-ok build/patch
~~~

Trong bash, dấu **:** ngăn các mục classpath. Với Windows, dùng **;** giữa đường dẫn và chạy lệnh một dòng:

~~~text
java -javaagent:redefine-agent.jar -cp "build/base;redefine-agent.jar" demo.Main batch-ok build/patch
~~~

Trên HotSpot JDK 17 thông thường có class redefinition capability, output:

~~~text
BEFORE=API_V1>STORE_V1|STORE_V1
REDEFINE_OK
AFTER=API_V2>STORE_V2|STORE_V2
CHECK=PASS
~~~

**Đọc kết quả:** trước batch, Api V1 gọi Store V1; sau khi redefineClasses trả về bình thường, lời gọi **mới** của Api dùng body V2 và Store dùng body V2. Kết quả là cùng một cặp version đã yêu cầu. Việc đọc **Api.route()** và **Store.value()** trong snapshot còn kiểm tra cả đường gọi phụ thuộc và đường gọi trực tiếp.

### 6.9. Batch một lớp lỗi: batch-bad

Chạy trong **JVM mới**, không sử dụng lại process ở batch-ok:

~~~bash
java -javaagent:redefine-agent.jar \
    -cp "build/base:redefine-agent.jar" \
    demo.Main batch-bad build/patch
~~~

Output:

~~~text
BEFORE=API_V1>STORE_V1|STORE_V1
REDEFINE_FAILED
AFTER=API_V1>STORE_V1|STORE_V1
CHECK=PASS
~~~

**Store** được yêu cầu redefine bằng mảng 4 byte không có cấu trúc class file. JVM từ chối **yêu cầu gồm cả Api và Store**; theo hợp đồng, **không lớp nào được redefine khi lời gọi ném exception**. Dù Api có bytes V2 hợp lệ, JVM giữ hai định nghĩa trước lời gọi thất bại.

Không dựa vào giả định JVM sẽ kiểm tra Store trước hay Api trước; Javadoc không yêu cầu bạn suy ra thứ tự từ log xử lý. Bằng chứng chính là **lời gọi ném lỗi** và **toàn bộ hành vi sau đó vẫn ở phiên bản cũ**.

### 6.10. Hai lời gọi riêng: split-bad

~~~bash
java -javaagent:redefine-agent.jar \
    -cp "build/base:redefine-agent.jar" \
    demo.Main split-bad build/patch
~~~

Output:

~~~text
BEFORE=API_V1>STORE_V1|STORE_V1
REDEFINE_FAILED
AFTER=API_V2>STORE_V1|STORE_V1
CHECK=PASS
~~~

Đây là tình huống dễ mắc lỗi trong hệ thống cập nhật nhiều lớp: lời gọi đầu tiên **redefineClasses(apiDef)** hoàn thành thành công. Lời gọi thứ hai **redefineClasses(storeDef)** thất bại. Hai lời gọi có hai ranh giới nguyên tử khác nhau; JVM **không rollback Api**.

Vì Api V2 vẫn gọi **Store.value()** qua descriptor cũ nên ứng dụng tiếp tục chạy, nhưng output cho thấy **một cặp version không đồng bộ**. Trong hệ thống nghiệp vụ thật, trạng thái đó có thể làm sai cấu trúc message, metric, tracing context hoặc quy tắc xử lý.

### 6.11. Kiểm tra bản trên đĩa khác bản trong JVM

~~~bash
javap -c -p -classpath build/base demo.Api
javap -c -p -classpath build/patch demo.Api
~~~

File **build/base/demo/Api.class** vẫn biểu diễn V1; file **build/patch/demo/Api.class** biểu diễn V2. Redefinition không sửa hai file này, mà cài method definition **trong JVM đang chạy**. Vì vậy chạy **javap trên file base sau khi batch-ok** vẫn thấy bản cũ không phải dấu hiệu agent thất bại.

## 7. Bảo đảm nguyên tử: chính xác là điều gì?

Java 17 Instrumentation API nêu: nếu **redefineClasses(...) ném exception, không class nào đã được redefine** bởi lời gọi ấy. Cần hiểu đúng đối tượng được bảo đảm.

### 7.1. Điều được bảo đảm

- Các **ClassDefinition** trong **một lời gọi** được xử lý như một tập để hỗ trợ thay đổi liên quan.
- Nếu lỗi xảy ra và **lời gọi ném exception**, không định nghĩa lớp nào thuộc tập đã được cài **bởi lời gọi thất bại đó**.
- Những định nghĩa đã cài ở các lần gọi **thành công trước đó** không bị rollback chỉ vì lần gọi sau lỗi.
- Nếu các bytes hợp lệ, capability đủ và lời gọi hoàn thành bình thường, JVM đã chấp nhận thao tác redefine của tập (nhưng business semantics vẫn phải được kiểm tra).

### 7.2. Điều KHÔNG được JVM bảo đảm như một transaction nghiệp vụ

| Thành phần | Batch redefine lỗi có tự hoàn tác không? |
| --- | --- |
| **Class definitions của chính yêu cầu đang thất bại** | **Không cài mới** các định nghĩa đó |
| **Log/counter mà một transformer đã ghi** | **Không** |
| **I/O, network request, thread do callback tạo** | **Không** |
| **Cấu hình static/memory của Java agent** | **Không** |
| **Batch redefine thành công trước đó** | **Không** |
| **Class khác được tải/biến đổi độc lập** | **Không thuộc ranh giới bảo đảm của yêu cầu này** |
| **Static field values và object state** | **Không bị reset** |
| **Active stack frames đang thực thi method cũ** | **Không được chuyển tức thì sang bytecode mới** |
| **Business request đã đi qua một phần đường gọi trước lúc thay** | **Không được chạy lại hoặc rollback** |

Vì vậy, thuật ngữ **atomic** ở đây phải được hiểu là **all-or-none cho class definitions trong một lời gọi bị lỗi**, **không** phải ACID transaction cho toàn bộ JVM.

### 7.3. Trong thời gian chuyển đổi, các thread có thể chạy code cũ

Theo API, nếu method đang có **active stack frames**, các frame ấy tiếp tục chạy bytecode của method cũ, còn **new invokes** sử dụng definition mới. Ví dụ request R đã vào Api V1 rồi JVM cập nhật cả Api và Store sang V2; khi R từ Api V1 gọi Store sau update, nó có thể gặp Store V2 nếu lời gọi xảy ra sau thời điểm cập nhật.

Do đó **all-or-none tại class-definition level** không đồng nghĩa **mọi business request luôn thấy cùng một snapshot version**. Nếu bài toán đòi hỏi tính nhất quán ở cấp request, cần thêm **quiescence, drain traffic, version pinning, routing theo generation hoặc cơ chế điều phối phía ứng dụng**. Một batch redefine không thay thế được transaction logic ứng dụng.

### 7.4. Static initializer và instances không chạy lại

Redefinition **không làm chạy lại class initializer <clinit>**, không reset static fields và không tạo lại instance hiện có. Thay method đọc static field không tự thay giá trị field. Nếu ứng dụng dùng caches, singleton hoặc state machine, cần xác định xem code V2 có tương thích với state V1 đã tồn tại hay không.

Ví dụ:

~~~java
// Minh họa source-level.
static final java.util.Map<String, String> CACHE =
        new java.util.HashMap<>();

static String read() {
    return CACHE.get("key");
}
~~~

Nếu bạn thay body **read()** mà vẫn dùng CACHE đang có, các entry của cache không tự xóa. Không thiết kế một phiên bản mới dựa trên giả định tất cả static state đã được khởi tạo lại.

## 8. Đánh giá kết quả toàn tập: không chỉ bắt exception

Một chương trình quản lý class redefinition cần **hai tầng kết quả**:

1. **Kết quả API:** redefineClasses trả bình thường hay ném exception.
2. **Kết quả chức năng toàn tập:** mọi class trong tập có đúng behavior, giao thức phụ thuộc và tính toàn vẹn sau cập nhật không.

Một lời gọi có thể hoàn thành bình thường dù bạn cung cấp class bytes tương đương hiện tại, hoặc dù logic mới mang lỗi nghiệp vụ. JVM verify/link class definition chứ không chứng minh rằng thuật toán của bạn trả đúng kết quả mong muốn.

### 8.1. Trạng thái triển khai nên phân biệt

~~~text
PREPARED
   │
   ├── VALIDATION_FAILED    → không gọi API
   │
   ▼
REQUESTED
   │
   ├── REDEFINE_FAILED      → không lớp nào trong batch thất bại được cài
   │
   ▼
DEFINITIONS_APPLIED
   │
   ├── BEHAVIOR_MISMATCH    → class đã được cài, nhưng toàn tập chưa đúng nghiệp vụ
   │
   ▼
WHOLE_SET_VERIFIED
~~~

Các nhãn là **trạng thái ứng dụng tự định nghĩa**, không phải enum chuẩn của JDK. Đặc biệt, **BEHAVIOR_MISMATCH sau một lần redefine thành công** không có nghĩa JVM sẽ tự rollback. Nếu cần rollback, hãy thực hiện một thao tác có kiểm soát, sau khi xác minh bytes và capability cần thiết.

### 8.2. Bảng kiểm kết quả của A và B

| Điều kiểm tra | Vì sao cần? | Bằng chứng phù hợp |
| --- | --- | --- |
| Đúng **Class object** | Tránh patch nhầm class loader | FQCN + defining loader/module |
| Đúng **version bytes** | Tránh lấy nhầm file patch | Hash/build ID của class file đầu vào |
| Capability được cấp | Tránh lệnh bị từ chối | isRedefineClassesSupported() |
| Mọi lớp modifiable | Chặn yêu cầu lỗi sớm | isModifiableClass trên từng Class |
| **Một** lời gọi chứa toàn bộ tập | Ranh giới all-or-none đúng phạm vi | Request ID và danh sách ClassDefinition |
| API hoàn thành bình thường | JVM đã chấp nhận request | Không có exception |
| A V2 đúng | Không chỉ thấy B đổi | Invocation riêng của A |
| B V2 đúng | Không chỉ thấy A đổi | Invocation riêng của B |
| **A→B** đúng | Xác minh phụ thuộc và phiên bản giao thức | Invocation xuyên cả hai class |
| Exception/return gốc không sai | Không làm hỏng semantics | Regression tests |
| Active frame/state được quản lý | Bảo đảm consistency request khi cần | Version routing/quiescence checks |

Khi một lớp không có API để đọc version, cần xác định **probe hợp lệ** hoặc kiểm chứng behavior đại diện. Không nên chỉ dựa vào dòng log “TRANSFORMED A” của một callback để kết luận cả tập đã được cài.

### 8.3. Vì sao kiểm tra riêng A, riêng B và đường phụ thuộc A→B?

Nếu chỉ test **Api.route()**, có thể output đúng tình cờ dù Store chưa cập nhật; ví dụ Api V2 có hard-coded kết quả hoặc nhánh test chưa đi qua Store. Ngược lại, test **Store.value()** đúng không chứng minh Api đã dùng Store theo protocol mới.

Cần ít nhất:

- **A-specific behavior**: Api đã dùng rule/logic mới?
- **B-specific behavior**: Store đã dùng rule/logic mới?
- **Cross-class behavior**: Api gọi Store tạo output/protocol tương thích?
- **Failure-path behavior**: cả hai lớp giữ nguyên logic cũ khi cùng batch fail?

Ví dụ **snapshot()** trong bài đọc cả Api.route() lẫn Store.value() để người học trực tiếp thấy trạng thái trộn trong split-bad.

## 9. Vai trò của ClassFileTransformer khi redefineClasses

Cần phân biệt **ClassDefinition bytes caller đưa vào** với **bytes cuối cùng JVM cài**. Nếu có các ClassFileTransformer đã đăng ký, chúng có thể tham gia xử lý **sự kiện redefine** theo hợp đồng. Vì vậy classfileBuffer đi qua transformer có thể được biến đổi thêm, và class bytes cuối có thể khác bytes patch bạn đọc từ file.

~~~text
ClassDefinition(Api.class, patchBytesApi)
    │
    ▼
JVM chạy các ClassFileTransformer áp dụng cho redefine
    │
    ▼
bytes cuối của Api

ClassDefinition(Store.class, patchBytesStore)
    │
    ▼
JVM chạy các ClassFileTransformer áp dụng cho redefine
    │
    ▼
bytes cuối của Store

               │
               ▼
       kiểm tra / cài toàn tập
~~~

Ngữ nghĩa:

- **return null** từ một transformer nghĩa là transformer ấy không cung cấp thay đổi; không loại bỏ bytes mà transformer trước đã tạo.
- **return byte[] mới** nghĩa là có dữ liệu thay thế cho bước tiếp theo, không tự là bằng chứng class đã được cài.
- Nếu một transformer **ném exception**, JVM có thể tiếp tục các transformer khác; không dùng cách ném trong callback như một giao thức chính để buộc redefine fail.
- Nếu bytes cuối của **bất kỳ lớp nào** vi phạm class format/schema, lời gọi redefineClasses có thể ném lỗi; **bảo đảm all-or-none vẫn áp dụng với cả batch**.
- Một transformer cũng có thể có **side effect** trước khi API phát hiện lỗi ở lớp khác. Side effect đó **không được JVM rollback**.

### 9.1. Không nhầm redefine với retransform

**retransformClasses(A,B)** bắt đầu từ class bytes nền do JVM tái tạo và áp dụng các phép biến đổi theo quy tắc retransformation. Trong khi đó **redefineClasses(defA,defB)** bắt đầu từ **class file bytes do caller chủ động cung cấp**, rồi áp dụng những transformer liên quan.

Cả hai đều xử lý được tập nhiều lớp và có bảo đảm nếu lời gọi ném exception thì không lớp nào của tập được cài, nhưng **khác nguồn bytes và khác capability**. Theo API, nếu mục tiêu là “thay class definition bằng một bản class file vừa biên dịch từ source”, **redefineClasses** phù hợp; nếu muốn chạy lại bytecode instrumentation trên các lớp đã load, **retransformClasses** thường phù hợp hơn.

## 10. Phân loại lỗi và cách phản ứng

| Lỗi | Điều kiện thường gặp | Hướng xử lý |
| --- | --- | --- |
| **UnmodifiableClassException** | Một Class trong tập không modifiable | Preflight từng Class, thay đổi tập/mục tiêu |
| **UnsupportedOperationException** | Capability thiếu hoặc thay đổi schema không được hỗ trợ | Kiểm tra manifest/JVM, khác biệt fields/methods/hierarchy |
| **ClassFormatError** | Byte[] không phải class file hợp lệ | Kiểm tra magic, class file parser, pipeline transform |
| **NoClassDefFoundError** | Internal name trong bytes không khớp target Class | Kiểm tra binary/internal class name và packaging |
| **UnsupportedClassVersionError** | Bytecode target version cao hơn JVM cho phép | Dùng javac --release phù hợp và kiểm tra major version |
| **ClassCircularityError** | Định nghĩa gây vòng phụ thuộc class không hợp lệ | Xem hierarchy/dependency |
| **LinkageError** | Lỗi linkage/verification liên quan | Kiểm tra cause, JVM logs, loader/module |
| **NullPointerException** | Mảng ClassDefinition hoặc phần tử null | Validate đầu vào, không gửi null |
| **ClassNotFoundException** trong chữ ký | Di sản tương thích API; Javadoc nêu không thể ném | Biết chữ ký, không đoán là lỗi thường gặp |
| API thành công nhưng behavior sai | Bản patch có lỗi logic hoặc probe không đúng | Test toàn bộ class, đường gọi phụ thuộc và exception path |

**Không báo partial success cho một lời gọi redefineClasses bị ném lỗi.** Các callback có thể đã xử lý bytes, nhưng điều đó không phải kết quả cài definition. Nếu bạn thấy partial state sau failure, kiểm tra xem hệ thống đã gửi **các lời gọi riêng biệt trước đó**, có agent khác đang đổi lớp, hoặc bạn đang quan sát active frames/state cũ hay không.

### 10.1. Diagnostic: xác định lớp gây lỗi nhưng không phá ranh giới atomic

Khi một tập 30 lớp bị từ chối, thật dễ muốn thử nhị phân: gửi nửa lớp trước rồi nửa sau. **Cảnh báo:** nếu thử việc đó trên chính production JVM, nửa đầu có thể **được cài thành công** và tạo trạng thái trộn.

Cách an toàn hơn:

1. **Tiền kiểm tra ngoại tuyến** từng class file về format/schema so với bản gốc.
2. Chạy batch trong **JVM kiểm thử giống production**, cùng JDK/agent/classloader, để cô lập lỗi.
3. Nếu phải thử chia tập, chỉ làm trên môi trường thử nghiệm hoặc thiết kế một kế hoạch update có rollback thực sự.
4. Ở production, giữ nguyên ranh giới batch đã xác định, sửa bytes lỗi rồi retry tập hoàn chỉnh khi an toàn.
5. Lưu hash, build ID, classloader identity và exception stack trace để đối chiếu.

Một lời gọi redefine với **mảng rỗng** được Javadoc cho phép và không thực hiện gì. Đừng ghi “đã triển khai tất cả” nếu thực tế bạn chỉ gửi một mảng trống.

## 11. Rollback, retry và version control

### 11.1. Batch bị từ chối không cần rollback class definitions của chính nó

Nếu **redefineClasses(A2, B2)** ném exception, class definitions trước lời gọi vẫn còn. Nhưng nếu callback/agent đã đổi biến, tăng counter hoặc gửi sự kiện ra hệ thống ngoài, những side effect này không tự bị hoàn tác. Có thể ghi **FAILED** và sửa nguyên nhân trước khi thử lại.

### 11.2. Batch thành công nhưng kiểm thử hậu triển khai lỗi

Đây là tình huống khác: API đã cài A2 và B2, sau đó business regression test báo lỗi. JVM **không tự rollback vì assertion của bạn thất bại**. Bạn cần có **class bytes V1 hợp lệ** và gửi một lời gọi redefine mới chứa **cả A và B** để quay về version cũ, rồi kiểm chứng lại.

~~~java
// Pseudocode, các bytes old đã được xác minh, không phải file độc lập.
inst.redefineClasses(
    new ClassDefinition(Api.class, originalApiBytes),
    new ClassDefinition(Store.class, originalStoreBytes)
);
~~~

Bản rollback vẫn chịu những giới hạn capability/schema và những transformer đang đăng ký. Nếu callback transformer thêm advice, bytes cuối sau rollback có thể khác bytes cũ trên đĩa. Với hệ thống quan trọng, cần thử **rollback path** ngay từ giai đoạn staging, không đợi lỗi production.

### 11.3. Retry cần có generation và tính idempotent

Nếu agent nhận nhiều yêu cầu gần nhau:

~~~text
Request #101: đổi A,B sang V2
Request #102: đổi A,B sang V3
Request #101: retry muộn
~~~

không có điều phối, retry muộn của #101 có thể ghi đè V3 thành V2 dù cả hai request đều được JVM chấp nhận. Hãy dùng **operation ID, expected generation**, một điểm điều phối với lock/queue phù hợp và kiểm tra state trước khi gửi. JVM API không quản lý version application giúp bạn.

**ClassDefinition không tự copy byte[]**, vì vậy nếu producer/agent giữ buffer mutable và có thread khác ghi vào, có thể tạo lỗi khó lặp. Chuẩn bị bytes bất biến cho mỗi operation, dùng hash/content-addressed artifact khi thích hợp, và không dùng chung một mảng mutable giữa các yêu cầu.

### 11.4. Khi nào nên restart thay vì redefine?

Nếu patch đòi thay class schema, thay nhiều dependency ngoài khả năng kiểm soát, đổi layout/state của đối tượng hoặc yêu cầu tất cả request thấy một bản protocol mới ngay cả với active frames, **rolling restart, classloader-based versioning hoặc cơ chế nâng cấp ứng dụng khác** thường phù hợp hơn. Không cố ép redefineClasses làm nhiệm vụ mà JVM không bảo đảm.

## 12. Kế hoạch vận hành an toàn cho tập lớp phụ thuộc

### 12.1. Giai đoạn PREPARE

1. Xác định tập **A, B, ...** dựa trên quan hệ method invocation/ABI và business protocol.
2. Lấy đúng **Class<?> mục tiêu** ở JVM hiện tại; kiểm tra loader/module.
3. Đọc/compile **toàn bộ class bytes mới** cùng một phiên bản build; không trộn file từ hai artifact versions.
4. So sánh schema bản cũ/mới: method descriptors, fields, hierarchy, modifiers và class file version.
5. Kiểm tra **isRedefineClassesSupported()** và **isModifiableClass**.
6. Kiểm tra/chuẩn bị runtime helper/module access mà new body cần.
7. Dự đoán các test **per-class** và **cross-class** cần chạy sau update.
8. Lưu bytes của phiên bản trước (nếu cần rollback), hash và operation ID.

### 12.2. Giai đoạn APPLY

1. Tránh nhiều controller tự redefine cùng Class object song song nếu cần bảo đảm version logic.
2. Đóng băng danh sách target và bytes mới cho operation.
3. Tạo **một ClassDefinition cho mỗi Class**.
4. Gọi **một redefineClasses(defA, defB, ...)** cho tập phụ thuộc.
5. Chỉ báo **DEFINITIONS_APPLIED** khi lời gọi hoàn thành bình thường.
6. Nếu lời gọi ném lỗi, báo **REDEFINE_FAILED** và **none installed by this call**; giữ chính xác error type/cause.

### 12.3. Giai đoạn VERIFY

1. Chạy invocation mới trên đúng lớp/loader để kiểm tra mỗi class.
2. Kiểm tra đường phụ thuộc A→B, không chỉ riêng A và B.
3. Kiểm tra return, exception path, concurrency và side effect theo phạm vi nghiệp vụ.
4. Xác nhận thời điểm chuyển thế hệ code phù hợp trạng thái request đang chạy.
5. Đánh dấu **WHOLE_SET_VERIFIED** chỉ khi tập đã qua toàn bộ điều kiện.
6. Nếu lỗi logic sau khi API thành công, xử lý theo runbook rollback/feature disable/restart; **không ghi thành “JVM transaction đã rollback”**.

~~~text
PREPARE → VALIDATE → APPLY → VERIFY → ACTIVE
   │          │        │        │
   │          │        │        └── lỗi nghiệp vụ:
   │          │        │            cần hành động khắc phục riêng
   │          │        └── API throw:
   │          │             none installed by this call
   │          └── lỗi trước API: không gọi redefine
   └── xác định class identity và artifact version
~~~

## 13. Những giả định sai thường gặp

### 13.1. “Đưa hai class vào ClassDefinition[] nghĩa là JVM sẽ tạo Class mới”

Sai. Redefinition nhắm tới những **Class object đã load**. Nó cập nhật phần định nghĩa được phép, không tạo kiểu runtime mới thay kiểu cũ. Nếu cần kiểu hoàn toàn mới hoặc layout mới, phải dùng chiến lược class loading/triển khai phù hợp.

### 13.2. “Nếu một lớp lỗi, JVM cài những lớp hợp lệ và bỏ lớp lỗi”

Sai đối với **một lời gọi redefineClasses nhiều lớp ném exception**. Tất cả các phần tử trong lời gọi ấy **không được redefine**. Nếu quan sát thấy trạng thái trộn, kiểm tra các lời gọi riêng đã thành công hoặc những hoạt động ngoài ranh giới batch.

### 13.3. “Bắt được exception và thấy log Api V2 nghĩa là Api đã cài”

Không nhất thiết. Log callback, đọc bytes và tạo ClassDefinition có thể hoàn tất **trước khi JVM quyết định batch thất bại**. Kết luận cài definition phải dựa vào API outcome và probe runtime.

### 13.4. “Class A và B cùng được cài thì mọi request dùng bản mới đồng bộ”

Không hẳn. **Active stack frames** có thể tiếp tục chạy code cũ, và object/static state vẫn tồn tại. Tính nguyên tử của class definitions không phải transaction toàn bộ request. Nếu cần nhất quán xuyên một request, phải thêm giao thức nâng cấp ở tầng ứng dụng.

### 13.5. “Chỉ cần thay method body của Store, Api tự động tương thích”

Không bảo đảm. Hai class có thể có **giao thức logic** thay đổi ngay cả khi descriptor nhị phân không đổi. Phải kiểm tra **giao diện observable** giữa chúng.

### 13.6. “Có Can-Retransform-Classes là đủ redefine”

Không. Hai capability riêng; kiểm tra **Can-Redefine-Classes** và **isRedefineClassesSupported()** cho API redefine.

### 13.7. “Một batch thành công nhưng test sau lỗi thì có thể bắt exception để rollback”

Không. Java exception của bài test không hoàn nguyên definitions. Cần thao tác redefine ngược hoặc cơ chế triển khai khác.

### 13.8. “Giữ file class V1 trên đĩa là đã rollback”

Không. JVM vẫn có thể đang dùng definition V2 đã cài trong bộ nhớ. Muốn thay runtime definition phải thực hiện thao tác phù hợp trong JVM, hoặc khởi động lại theo chính sách triển khai.

## 14. Ma trận kiểm thử cần có

| Test | Dữ liệu | Kỳ vọng |
| --- | --- | --- |
| Baseline | V1 Api và Store | API_V1>STORE_V1 |
| Batch hai lớp hợp lệ | V2 Api và Store trong một lời gọi | Cả hai là V2, đường Api→Store đúng |
| Batch Store bytes không hợp lệ | Api V2 hợp lệ, Store bad | Lời gọi ném lỗi; cả hai giữ trước batch |
| Hai lời gọi độc lập, Store lỗi | Api V2 commit trước | Trạng thái trộn Api V2 + Store V1; không rollback tự động |
| Lớp không modifiable | Thêm int[].class | Preflight từ chối hoặc API thất bại; không có commit từ batch lỗi |
| Không có capability | Manifest không bật redefine | Fail fast, không ghi thành công |
| Null ClassDefinition | Array có null | NullPointerException, không cài mới |
| Array definitions rỗng | redefineClasses() | Hợp lệ, không làm gì |
| Bytecode sai tên lớp | ClassDefinition(A.class, bytes B) | Bị từ chối; không class nào cài từ batch lỗi |
| Bytecode sai version | Compile cho JDK cao hơn target | Bị từ chối |
| Thay class schema | Thêm field/method trong patch | Không được JVM mặc định cho phép |
| Có ClassFileTransformer khác | Output bị sửa tiếp | Xác minh bytes cuối và hành vi thật |
| Hai classloader cùng FQCN | Hai Class object khác nhau | Chỉ đúng Class trong tập bị sửa |
| Active request cũ | Thread đang trong method V1 | Có thể tiếp tục V1; invocation mới dùng V2 |
| Rollback có kiểm soát | Lưu bytes cũ V1, apply cả tập | Cả hai trở lại hành vi V1 sau request rollback hợp lệ |
| Concurrency/retry | Hai operation version xung đột | Coordinator không cho version cũ ghi đè version mới |

### 14.1. Bộ assertion tối thiểu

Với ví dụ của bài, **không chỉ assert một string cuối** nếu muốn chứng minh toàn tập ở mức production. Hãy kiểm tra:

- Trước: **Api.route** và **Store.value** đều là V1.
- Sau batch-ok: **Api.route** chứa phần format V2 và kết quả **Store.value** thật là V2.
- Sau batch-bad: cả hai vẫn trả V1; không có class nào được cài từ lời gọi lỗi.
- Sau split-bad: Api V2/Store V1 là đối chứng cho nguy cơ tách batch.
- Thời điểm API trả bình thường vs thời điểm business probe.
- Lỗi class format/linkage được báo riêng, không nuốt trong callback.
- Với classloader/module thực: Class object thuộc đúng loader và patch bytes thuộc đúng bản build.

## 15. Checklist trước khi triển khai

- Tôi đã xác định **tập lớp phụ thuộc** và ranh giới version cần nhất quán.
- **Can-Redefine-Classes** được khai báo trong manifest và JVM báo hỗ trợ.
- Mọi target class đã load, đúng defining loader/module và có **isModifiableClass=true**.
- File class mới được compile từ cùng artifact version, có đúng internal name và phù hợp JDK target.
- Các thay đổi giữ schema trong phạm vi JVM hỗ trợ, không thêm/xóa fields/methods tùy ý.
- ClassDefinition ghép đúng Class và byte[]; **byte[] không bị mutate sau khi chuẩn bị**.
- Các transformer khác có thể tham gia redefine đã được cân nhắc.
- Tôi dùng **một redefineClasses(...)** cho các class cần thay cùng nhau, không ngầm chia thành nhiều request.
- Khi API ném lỗi, tôi báo **none installed by this call** và giữ nguyên kết quả các lần trước.
- Khi API trả bình thường, tôi chạy **kiểm tra từng lớp và đường phụ thuộc liên lớp** trước khi báo thành công toàn tập.
- Tôi biết JVM không reset instance/static fields và không tự chuyển active frame cũ sang bytecode mới.
- Có runbook rollback/retry và giới hạn concurrency nếu các yêu cầu cùng sửa class.
- Tôi đã thử cả **batch-ok**, **batch-bad**, **split-bad** ở JDK/framework dự kiến triển khai.

## 16. Tài liệu tham khảo chính thức

- [Java SE 17 — Instrumentation.redefineClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)): hợp đồng tập lớp, exception, active frames và no classes redefined khi lời gọi thất bại.
- [Java SE 17 — ClassDefinition](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): ghép Class với class bytes; constructor không copy byte[].
- [Java SE 17 — isRedefineClassesSupported và isModifiableClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): capability và kiểm tra modifiable.
- [Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): các transformer có thể tham gia khi class được redefine.
- [Java SE 17 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agent, premain và manifest Can-Redefine-Classes.
- [JVM TI Specification 17 — RedefineClasses](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html): các giới hạn class definition và khả năng thay đổi class.
- [Java Virtual Machine Specification 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): cấu trúc class file và ràng buộc bytecode.

**Kết luận:** Hãy dùng **một yêu cầu redefineClasses chứa toàn bộ các class phụ thuộc** nếu cần một ranh giới all-or-none ở cấp **class definitions**. Khi yêu cầu ấy ném exception, **không class nào trong tập đã được redefine bởi yêu cầu đó**. Khi yêu cầu thành công, bạn vẫn phải **đánh giá toàn tập bằng invocation mới**, kiểm tra class identity, semantics liên lớp, active frames và state của ứng dụng; việc commit definitions không tự bảo đảm thành công nghiệp vụ.
