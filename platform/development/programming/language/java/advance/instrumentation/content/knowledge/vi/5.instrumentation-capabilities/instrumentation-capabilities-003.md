# `Can-Redefine-Classes` và `Instrumentation.isRedefineClassesSupported()`

Một Java agent có thể thay bytecode của lớp **đã được tải** mà không cần khởi động lại JVM, nhưng việc này cần một *capability* được cấp khi nạp agent. Hai tên trong đề bài trả lời hai câu hỏi khác nhau:

- **`Can-Redefine-Classes`**: agent đã yêu cầu JVM cho phép **class redefinition** trong `META-INF/MANIFEST.MF` hay chưa?
- **`Instrumentation.isRedefineClassesSupported()`**: cấu hình JVM hiện tại **thực sự có hỗ trợ** redefinition hay không?

Nếu phép hỏi trả `true`, vẫn chưa thể sửa tùy ý mọi lớp. Agent còn phải kiểm tra **`Instrumentation.isModifiableClass(clazz)`**, cung cấp **class file bytes** phù hợp qua `ClassDefinition` và để JVM xác minh bytes khi gọi **`redefineClasses(...)`**.

## 1. Class redefinition là gì?

*Redefinition* thay định nghĩa một lớp **đang tồn tại trong JVM** bằng một định nghĩa mới; điển hình là thay thân phương thức khi debug, sửa logic trong môi trường phát triển hoặc thay bộ bytecode phục vụ công cụ chẩn đoán. Khác với `ClassLoader#defineClass`, nó không định nghĩa thêm một class độc lập có cùng tên. Lời gọi nhận **chính đối tượng `Class<?>`** của lớp cần sửa, có danh tính gắn với class loader của lớp ấy.

Ví dụ: lớp `demo.Message` đã được tải và `value()` trả `"old"`. Bạn biên dịch một bản `demo.Message` khác, **giữ nguyên tên lớp và chữ ký method**, nhưng `value()` trả `"new"`. Khi JVM cho phép redefine và bytecode mới hợp lệ, những **lời gọi mới** đến method sẽ có thể trả `"new"`. Đối tượng đã tạo không bị tạo lại, và method đang có stack frame hoạt động vẫn chạy phiên bản bytecode cũ cho tới khi frame đó kết thúc.

Redefinition không phải công cụ thay toàn bộ cấu trúc Java tùy ý: việc thêm field, thêm method, đổi chữ ký hoặc thay quan hệ kế thừa bị giới hạn bởi JVM TI. Vì thế, phân biệt “**hỗ trợ thao tác**” và “**một thay đổi cụ thể hợp lệ**” là nền tảng của bài này.

## 2. Thuộc tính `Can-Redefine-Classes` trong agent manifest

Manifest của agent nạp bằng `-javaagent` có thể như sau:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProbeAgent
Can-Redefine-Classes: true

~~~

**Ý nghĩa từng dòng:**

| Dòng | Chức năng |
|---|---|
| `Manifest-Version: 1.0` | Khai báo phiên bản định dạng manifest |
| `Premain-Class: demo.ProbeAgent` | Lớp có `premain` được gọi khi dùng `-javaagent` |
| `Can-Redefine-Classes: true` | Yêu cầu JVM cung cấp khả năng redefine nếu môi trường hỗ trợ |

Quy tắc theo đặc tả `java.lang.instrument`:

1. `Can-Redefine-Classes` là thuộc tính **tùy chọn**, mặc định **`false`** nếu vắng mặt.
2. Giá trị là boolean (`true`/`false`, không phân biệt hoa thường). Giá trị khác `true` được coi là `false`.
3. Thuộc tính phải nằm trong **main section** của `META-INF/MANIFEST.MF` bên trong **JAR được JVM nạp làm agent**. Chỉ đặt nó trong manifest của một JAR khác, trong file ứng dụng hoặc trong `-D...` không đủ.
4. `true` **yêu cầu capability**, không tự tạo capability ở một JVM vốn không hỗ trợ.
5. `Premain-Class` lựa chọn entrypoint **startup agent**. Nếu nạp agent bằng cơ chế attach, JAR dùng `Agent-Class` và callback `agentmain`; thuộc tính capability vẫn phục vụ yêu cầu redefine, không quyết định callback.
6. Thay manifest trên đĩa sau khi JVM/agent đã khởi động **không cập nhật ngược** capability của JVM hiện tại.

Thuộc tính này thường có trong agent muốn gọi `redefineClasses` trên lớp đã được tải. Một agent chỉ quan sát các lớp *sắp tải* qua transformer không nhất thiết phải yêu cầu redefinition.

**Hai mức cần phân biệt:** Agent A có manifest `true`, JVM X hỗ trợ redefinition → có thể được cấp khả năng. Agent B có manifest thiếu thuộc tính, dù cũng chạy trên JVM X → không được coi là đã yêu cầu khả năng. Agent A chuyển sang JVM Y không hỗ trợ → manifest `true` cũng không bảo đảm thành công.

## 3. `isRedefineClassesSupported()`: kiểm tra khả năng runtime

Chữ ký API:

~~~java
boolean isRedefineClassesSupported();
~~~

Phương thức là thành viên của `java.lang.instrument.Instrumentation`. JVM chuyển instance `Instrumentation` cho agent qua callback `premain(String, Instrumentation)` hoặc `agentmain(String, Instrumentation)`. Đây không phải object bạn tự `new` để thử một tùy chọn.

- **`true`**: khả năng redefine **được hỗ trợ trong cấu hình JVM hiện tại**, với yêu cầu capability phù hợp của agent. Khi đó có thể tiếp tục kiểm tra lớp và bytes.
- **`false`**: hiện tại không có khả năng redefine qua API này; gọi `redefineClasses(...)` sẽ dẫn tới `UnsupportedOperationException` do capability không được cấp.
- **Kết quả ổn định trong cả vòng đời một JVM**: API quy định nhiều lần gọi trong cùng một JVM trả về cùng kết quả. Không có thao tác “đợi thêm một lúc” để `false` tự thành `true`.

Không nên lấy `isRedefineClassesSupported()` làm phép kiểm tra class `java.lang.String`, `demo.Service` hay `int[]` vì nó **không nhận đối số lớp**. Với lớp cụ thể, dùng `isModifiableClass`.

### Ma trận quyết định

| Agent yêu cầu capability? | JVM hỗ trợ/cấp capability? | Kết quả kiểm tra |
|---|---|---|
| Không (`false` hoặc thiếu thuộc tính) | JVM có thể triển khai redefine | `isRedefineClassesSupported()` vẫn không được bảo đảm `true`; theo hợp đồng agent phải yêu cầu |
| Có (`true`) | Không | `false` |
| Có (`true`) | Có | `true`; **chưa bảo đảm** lớp đích sửa được |
| Có (`true`) | Có, nhưng bytes mới sai schema/format | Kiểm tra có thể `true`, nhưng `redefineClasses` vẫn **thất bại** |

Luồng xử lý nên là:

~~~text
Agent JAR: Can-Redefine-Classes: true?
    |
    v
Instrumentation.isRedefineClassesSupported() == true?
    |
    v
Instrumentation.isModifiableClass(Target.class) == true?
    |
    v
Bytecode mới đúng class, version, schema và verifier?
    |
    v
Instrumentation.redefineClasses(new ClassDefinition(Target.class, bytes))
    |
    +-- thành công: các lời gọi method mới dùng định nghĩa mới
    +-- ngoại lệ: phân tích lỗi, không coi mọi thay đổi là hợp lệ
~~~

## 4. `isModifiableClass` hỏi về lớp đích, không hỏi về capability

~~~java
boolean isModifiableClass(Class<?> theClass);
~~~

Phép kiểm tra này trả `true` nếu lớp thuộc loại mà JVM có thể sửa bằng redefinition **hoặc** retransformation, và `false` nếu không sửa được. Đặc tả nói rõ kết quả của `isModifiableClass` **không bị chi phối** bởi giá trị `isRedefineClassesSupported()` hay `isRetransformClassesSupported()`.

Ví dụ, trên một JVM thông thường:

- `isModifiableClass(demo.Message.class)` có thể là `true`;
- `isModifiableClass(int.class)` luôn `false`;
- `isModifiableClass(String[].class)` luôn `false`.

Một số lớp do JVM triển khai đặc biệt cũng có thể không sửa được. Việc `isModifiableClass(Message.class)` trả `true` **không có nghĩa** agent đã được quyền redefine; điều kiện capability cần kiểm tra riêng.

Nếu muốn sửa một lớp:

~~~java
if (inst.isRedefineClassesSupported()
        && inst.isModifiableClass(Target.class)) {
    byte[] bytes = java.nio.file.Files.readAllBytes(
            java.nio.file.Path.of("replacement/Target.class"));
    inst.redefineClasses(
            new java.lang.instrument.ClassDefinition(Target.class, bytes));
}
~~~

Đây là **đoạn mã minh họa nằm trong một method**: giả định tồn tại `Target`, `Instrumentation inst` và file bytes tương ứng. `ClassDefinition` ghép **`Class<?>` thực tế** với **toàn bộ byte của class file mới**, không phải Java source hay chỉ một phần code của method.

Hai class cùng tên nhị phân nhưng thuộc hai class loader khác nhau có danh tính khác nhau. Cần truyền đúng `Class<?>` của đối tượng mà ứng dụng đang dùng.

## 5. Thực hành Java 17+: thay bytecode của method đã được tải

Ví dụ sau có thể biên dịch với **JDK 17+**. Nó tạo một agent nhận `Instrumentation` qua `premain`, một bản gốc và một bản thay thế của cùng lớp `demo.Message`. Ứng dụng gọi `Message.value()` trước và sau thao tác redefine.

### 5.1. Cây thư mục

~~~text
redefine-lab/
├── MANIFEST.MF
├── src/
│   └── demo/
│       ├── ProbeAgent.java
│       ├── Message.java
│       └── Demo.java
├── replacement-src/
│   └── demo/
│       └── Message.java
└── out/
    ├── original/
    ├── replacement/
    └── demo.jar
~~~

Hai file `Message.java` có **cùng tên class/package**, nhưng biên dịch vào **hai thư mục khác nhau**. Bản cũ được đóng vào JAR ứng dụng; bản mới được đọc trực tiếp thành bytes để gửi JVM. Không để hai phiên bản lẫn nhau trên cùng classpath.

### 5.2. `src/demo/ProbeAgent.java`

~~~java
package demo;

import java.lang.instrument.Instrumentation;

public final class ProbeAgent {
    private static volatile Instrumentation instance;

    public static void premain(String options, Instrumentation inst) {
        instance = inst;
    }

    public static Instrumentation instrumentation() {
        if (instance == null) {
            throw new IllegalStateException(
                    "Start with -javaagent:out/demo.jar");
        }
        return instance;
    }
}
~~~

`premain` được JVM gọi trước `main` khi có `-javaagent`. Ở ví dụ này agent và ứng dụng nằm cùng JAR, để ứng dụng có thể lấy `Instrumentation` đã được lưu. Trong môi trường có nhiều class loader, cần đảm bảo class lưu instance và class truy cập instance đúng là một định nghĩa.

### 5.3. `src/demo/Message.java` — lớp gốc

~~~java
package demo;

public final class Message {
    public static String value() {
        return "old";
    }
}
~~~

### 5.4. `replacement-src/demo/Message.java` — lớp thay thế

~~~java
package demo;

public final class Message {
    public static String value() {
        return "new";
    }
}
~~~

Chỉ thay logic trả chuỗi: không thêm field, đổi chữ ký hoặc đổi modifiers. Đây là loại thay đổi phù hợp mục đích redefinition. Nếu muốn thử thêm field, xem phần lỗi thường gặp; **không thay bản thay thế đang dùng trong lần chạy thành công**.

### 5.5. `src/demo/Demo.java`

~~~java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Demo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: demo.Demo <replacement-class-file>");
        }

        System.out.println("before=" + Message.value());

        Instrumentation inst = ProbeAgent.instrumentation();
        boolean supported = inst.isRedefineClassesSupported();
        boolean modifiable = inst.isModifiableClass(Message.class);

        System.out.println("supported=" + supported);
        System.out.println("modifiable=" + modifiable);

        if (!supported || !modifiable) {
            System.out.println("skipped");
            return;
        }

        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        ClassDefinition replacement =
                new ClassDefinition(Message.class, bytes);

        inst.redefineClasses(replacement);
        System.out.println("after=" + Message.value());
    }
}
~~~

Giải thích:

1. `Message.value()` được gọi trước thao tác để thấy `"old"` và chắc chắn class đích đã được tải.
2. Hai phép hỏi kiểm tra **khả năng JVM** và **khả năng sửa lớp đích**.
3. `Files.readAllBytes` đọc chính bytes của file `.class` mới; không yêu cầu lớp mới được nạp song song vào JVM.
4. `ClassDefinition(Message.class, bytes)` chỉ rõ lớp cần thay trong JVM.
5. Nếu `redefineClasses` thành công, lời gọi `Message.value()` tiếp theo dùng thân method mới.

Method `main` khai báo `throws Exception` để giữ ví dụ ngắn; agent production cần phân loại và xử lý lỗi theo quy trình riêng.

### 5.6. `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProbeAgent
Can-Redefine-Classes: true

~~~

Đảm bảo file manifest có **dòng trống kết thúc**. Trong ví dụ chạy bằng `-cp ... demo.Demo`, không cần `Main-Class` vì tên lớp ứng dụng được ghi rõ ở command line.

### 5.7. Lệnh biên dịch và chạy

Mở terminal trong `redefine-lab`. Tạo thư mục bằng Bash/Git Bash:

~~~bash
mkdir -p out/original out/replacement
~~~

Hoặc bằng Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/original, out/replacement | Out-Null
~~~

Tiếp tục chạy các lệnh JDK sau trong chính thư mục đó:

~~~bash
javac --release 17 -d out/original src/demo/ProbeAgent.java src/demo/Message.java src/demo/Demo.java
javac --release 17 -d out/replacement replacement-src/demo/Message.java
jar --create --file out/demo.jar --manifest MANIFEST.MF -C out/original .
java -javaagent:out/demo.jar -cp out/demo.jar demo.Demo out/replacement/demo/Message.class
~~~

Dấu `/` trong những đường dẫn ở trên được Java hỗ trợ trên Windows. `--release 17` giúp class file phù hợp Java 17. Không thêm `out/replacement` vào `-cp`: lớp gốc cần được tải trước, còn bản mới được truyền dưới dạng bytes.

Trên **HotSpot JDK hỗ trợ redefine** và đã cấp capability, stdout kỳ vọng:

~~~text
before=old
supported=true
modifiable=true
after=new
~~~

Hai giá trị boolean phải được quan sát ở **JVM đang dùng**; các bản phân phối/cấu hình JVM khác có thể báo `false`. Nếu không đủ điều kiện, code minh họa in `skipped`. Nếu đủ điều kiện nhưng bytes mới không hợp lệ, lệnh `redefineClasses` có thể ném ngoại lệ; việc `supported=true` **không bảo đảm** sẽ luôn in dòng `after=new`.

Nếu bỏ `-javaagent`, JVM không gọi `premain`, trường `instance` chưa được gán và demo báo phải chạy với `-javaagent`.

## 6. Thí nghiệm đối chứng: manifest tắt khả năng redefine

Tạo file `MANIFEST-disabled.MF`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.ProbeAgent
Can-Redefine-Classes: false

~~~

Tạo một JAR khác từ đúng lớp gốc đã biên dịch và chạy trong **JVM mới**:

~~~bash
jar --create --file out/demo-disabled.jar --manifest MANIFEST-disabled.MF -C out/original .
java -javaagent:out/demo-disabled.jar -cp out/demo-disabled.jar demo.Demo out/replacement/demo/Message.class
~~~

Một kết quả thường gặp trên HotSpot:

~~~text
before=old
supported=false
modifiable=true
skipped
~~~

Giải thích quan trọng: `supported=false` nghĩa capability redefine chưa được cấp. `modifiable=true` **vẫn có thể đúng**, vì thuộc tính lớp có sửa được hay không được hỏi **độc lập với capability**. Chuỗi `skipped` là logic do **Demo** tự in, không phải thông báo mặc định của JVM.

Nếu một JVM nào đó trả `modifiable=false`, vẫn không làm thay đổi nguyên tắc: cần kiểm tra **cả hai điều kiện** trước khi tiến hành. Đổi `false` thành `true` trong manifest cũng không ép một JVM không hỗ trợ redefinition phải hỗ trợ.

## 7. Giới hạn của `redefineClasses` và hành vi sau khi thay

Trong JVMTI Java 21, redefinition có thể thay đổi thân method, constant pool và một số class-file attributes cho phép, nhưng có nhiều giới hạn cấu trúc. Những thay đổi như **thêm/xóa/đổi tên field hoặc method; thay chữ ký method, modifiers, quan hệ kế thừa; thay `NestHost`, `NestMembers`, `Record`, `PermittedSubclasses`** bị cấm theo hợp đồng tương ứng.

| Tình huống | Kết quả/ý nghĩa |
|---|---|
| Chỉ đổi thân `value()` từ trả `"old"` sang `"new"` | Hợp lệ về cấu trúc; còn cần bytes và verifier hợp lệ |
| Thêm `private int counter` vào class đã tải | Đổi schema; không thuộc thay đổi redefinition thông thường |
| Đổi `String value()` thành `int value()` | Đổi chữ ký; không được phép |
| Đổi superclass, thêm/bỏ method hoặc thay modifiers | Đổi cấu trúc; không được phép |
| Dùng `.class` có tên khác tên của `Class<?>` đích | Không hợp lệ; có thể có `NoClassDefFoundError` |
| Dùng `.class` tạo cho Java mới hơn JVM đích | Có thể có `UnsupportedClassVersionError` |
| Bytes lỗi cấu trúc, stack map hoặc verification | Có thể có `ClassFormatError` hay lỗi liên kết/xác minh |
| Nhắm tới primitive/array class | Không thể sửa những lớp đó |

Một số **hệ quả runtime** không thể bỏ qua:

- **Đối tượng cũ vẫn tồn tại** và giữ nguyên các field instance. Redefinition không làm lại constructor hoặc di chuyển dữ liệu.
- **Static initializer không tự chạy lại** và giá trị static field không tự đặt về ban đầu. Đổi source code khai báo static field chưa chắc làm trạng thái hiện tại đổi theo.
- **Stack frame đang chạy tiếp tục phiên bản method cũ**; **lời gọi mới** đến method dùng phiên bản mới. Đừng dùng một thread đang ở giữa method để kết luận redefine thất bại.
- **Compile-time constants có thể được inline** ở class gọi. Đổi một `static final` constant trong class được redefine không tự sửa các bytes đã được biên dịch vào class khác.
- **Nhiều class trong cùng một lần gọi** có thể được redefine cùng nhau; nếu lời gọi ném ngoại lệ, API bảo đảm **không class nào trong nhóm được cập nhật**.
- **Lần redefine thành công không tự hoàn tác**. Muốn khôi phục logic cũ, phải lưu bộ bytes cũ và chủ động thực hiện thao tác tương ứng nếu môi trường cho phép.
- JVM TI có thể xóa các **breakpoint** của lớp bị redefine; cần đồng bộ lại công cụ debug nếu đang dựa vào chúng.

Đặc tả JVM TI là nguồn để biết giới hạn trong từng phiên bản JDK. Những thay đổi đặc thù class file mới có thể có ràng buộc bổ sung; không dùng kết quả boolean làm bảo đảm chấp nhận mọi bytecode.

## 8. Những ngoại lệ thường gặp

Chữ ký Java:

~~~java
void redefineClasses(ClassDefinition... definitions)
        throws ClassNotFoundException, UnmodifiableClassException;
~~~

| Hiện tượng/lỗi | Giải thích | Hướng xử lý |
|---|---|---|
| `isRedefineClassesSupported()` bằng `false` | Manifest không yêu cầu, hoặc JVM không hỗ trợ/cấp khả năng | Đối chiếu **manifest trong agent JAR thực tế**, cấu hình/JVM |
| `UnsupportedOperationException` khi capability false | Không cho phép redefine trong cấu hình hiện tại | Hỏi `isRedefineClassesSupported()` trước |
| `UnmodifiableClassException` | Có class đích không thể sửa | Dùng `isModifiableClass`, loại bỏ loại class đặc biệt |
| `UnsupportedOperationException` dù capability true | Thao tác bytes mới yêu cầu thay đổi không được hỗ trợ (chẳng hạn đổi schema) | So sánh danh sách field/method, modifiers, hierarchy và attributes |
| `ClassFormatError`/lỗi verification | Bytes không phải class file hợp lệ hoặc bytecode sai | Dùng `javap -v -c`/verifier, kiểm tra tool tạo bytes |
| `NoClassDefFoundError` khi tên class khác | Bytes khai báo class có tên không khớp target | Bảo đảm đúng package và tên nhị phân |
| `UnsupportedClassVersionError` | Class file version không được JVM đích hỗ trợ | Biên dịch bằng `--release` tương thích |
| Logic mới không xuất hiện giữa method đang chạy | Frame cũ còn hoạt động | Kiểm chứng ở **lời gọi mới**, không ở giữa frame hiện tại |

Lưu ý `ClassFormatError`, `UnsupportedClassVersionError`, `LinkageError` thuộc nhóm `Error`, không phải tất cả là `Exception`. Do đó, `throws Exception` trong demo nhằm đơn giản hóa ví dụ, **không phải chiến lược xử lý toàn bộ lỗi runtime**.

`ClassNotFoundException` vẫn xuất hiện trong khai báo vì lý do tương thích API; tài liệu `Instrumentation` mô tả trường hợp exception này không thực sự được ném bởi `redefineClasses` trong hợp đồng hiện tại. Đừng dùng việc khai báo checked exception này để suy ra JVM sẽ tìm class mới qua classpath.

## 9. Redefinition và retransformation có liên quan nhưng không đồng nhất

| Khía cạnh | Redefinition | Retransformation |
|---|---|---|
| Manifest capability | `Can-Redefine-Classes` | `Can-Retransform-Classes` |
| Method kiểm tra | `isRedefineClassesSupported()` | `isRetransformClassesSupported()` |
| Method thực hiện | `redefineClasses(ClassDefinition...)` | `retransformClasses(Class<?>...)` |
| Dữ liệu đầu vào | **Class file bytes thay thế** do agent truyền | Quá trình áp dụng lại các transformer từ **initial class file bytes** liên quan |
| Dùng khi | Thay bản class đã biên dịch / hot code replace | Áp dụng, tính lại transformations trên class đã tải |
| Per-class guard | `isModifiableClass(clazz)` | Cũng dùng `isModifiableClass(clazz)` |

`Can-Redefine-Classes: true` **không đồng nghĩa** `Can-Retransform-Classes: true`. Không gọi `addTransformer(transformer, true)` rồi cho rằng redefinition capability tự động có sẵn; mỗi cơ chế có điều kiện riêng.

Khi gọi `redefineClasses`, các `ClassFileTransformer` đã đăng ký cũng có thể tham gia quy trình xử lý bytes trước khi JVM kiểm tra và cài định nghĩa cuối cùng. Vì vậy hãy cân nhắc tương tác với những agent khác trong cùng process.

## 10. Quy trình sử dụng an toàn và chính xác

1. **Khởi chạy đúng agent JAR** qua `Premain-Class`/`Agent-Class` phù hợp, và nhận `Instrumentation` từ JVM.
2. **Yêu cầu đúng capability** bằng `Can-Redefine-Classes: true` trong main manifest của agent JAR.
3. **Hỏi runtime** `isRedefineClassesSupported()`. Nếu `false`, báo giới hạn môi trường và không gọi redefine.
4. **Xác định lớp đích** bằng chính `Class<?>` ứng dụng sử dụng, bao gồm class loader; gọi `isModifiableClass`.
5. **Chuẩn bị toàn bộ class file bytes** mới, giữ cấu trúc và chữ ký hợp lệ. Kiểm tra class file bằng `javap`, công cụ kiểm tra bytecode khi cần.
6. **Thực hiện `redefineClasses`**; phân loại lỗi nếu có, không suy rằng preflight boolean đồng nghĩa thao tác thành công.
7. **Kiểm chứng các lời gọi mới**, theo dõi state/breakpoint và có phương án phục hồi bằng bytes gốc nếu cần.

## 11. Tự kiểm tra

1. **Manifest không có `Can-Redefine-Classes`; JVM về mặt kỹ thuật hỗ trợ redefinition. Agent chắc chắn được redefine?** Không. Agent phải yêu cầu capability, JVM phải cấp.
2. **`Can-Redefine-Classes: true` có bắt buộc `isRedefineClassesSupported()` trả `true` không?** Không; còn phụ thuộc JVM/cấu hình.
3. **`isModifiableClass(Message.class)` trả `true`, `isRedefineClassesSupported()` trả `false`; có được gọi `redefineClasses` không?** Không; phép hỏi per-class độc lập với capability.
4. **Gọi lại `isRedefineClassesSupported()` sau vài giây có đổi từ `false` thành `true` trong cùng JVM không?** Không; kết quả ổn định trong một phiên JVM.
5. **Có thể dùng `ClassDefinition(Target.class, bytes)` chứa một class khác tên để đổi tên class không?** Không; class file phải khớp target.
6. **Sau redefine, static initializer có chạy lại?** Không. Existing instances và static field state không tự reset.
7. **Method đang chạy có lập tức chuyển đến bytecode mới ở giữa method?** Không; frame hiện hành tiếp tục bản cũ, lời gọi mới dùng bản mới.
8. **Bật `Can-Redefine-Classes` có tự bật `Can-Retransform-Classes`?** Không; hai capabilities riêng.
9. **Khi nhóm hai class redefine cùng lúc thất bại, một class có thể đã được cập nhật?** Theo hợp đồng API, không class nào trong nhóm được redefine nếu lời gọi ném ngoại lệ.

### Nguồn tham khảo chuẩn

- [Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest capabilities và agent callbacks.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): chính xác các phép hỏi, thao tác và ngoại lệ.
- [Java SE 21 — `ClassDefinition`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): ghép class và class file bytes.
- [JVM Tool Interface 21 — RedefineClasses](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): giới hạn schema, frame hiện hành, state và nhóm lỗi.
- [Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): cấu trúc manifest.

**Điểm cần nhớ:** `Can-Redefine-Classes` là **yêu cầu của agent**; `isRedefineClassesSupported()` là **khả năng JVM cấp**; `isModifiableClass(clazz)` kiểm tra **lớp đích**; `redefineClasses(...)` mới kiểm tra và cài **bytes thay thế**.