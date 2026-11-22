# `Can-Retransform-Classes` và `isRetransformClassesSupported()` trong Java Instrumentation

## 1. Vấn đề: class đã được JVM nạp rồi thì còn instrument được không?

Trong Java Instrumentation, `ClassFileTransformer` thường nhận bytecode khi một class **sắp được định nghĩa**. Tuy nhiên, Java agent có thể được bật muộn, hoặc profiler/tracer muốn thay đổi cách quan sát một class đã nạp. **Retransformation** là cơ chế yêu cầu JVM chạy lại quá trình biến đổi bytecode cho những class **đang được tải trong JVM** mà không cần khởi động lại tiến trình.

Hai thành phần trong tiêu đề giải quyết hai tầng khác nhau:

- **`Can-Retransform-Classes: true`** là thuộc tính trong **main manifest của agent JAR**: agent yêu cầu quyền năng retransform.
- **`Instrumentation.isRetransformClassesSupported()`** là phương thức Java trả về khả năng **thực sự sẵn có trong cấu hình JVM hiện tại**. Chỉ bật manifest chưa bảo đảm JVM sẽ cấp khả năng đó.

Khi đã có khả năng, agent vẫn cần đăng ký transformer đúng chế độ, chọn class có thể chỉnh sửa, rồi gọi `Instrumentation.retransformClasses(...)`. Đừng đồng nhất bốn câu hỏi: “JVM có hỗ trợ?”, “agent đã yêu cầu?”, “transformer có được gọi lại?” và “class cụ thể có sửa được không?”.

Bài học áp dụng với `java.lang.instrument` trong Java 17+ và các runtime tương thích; retransform là khả năng **tùy chọn** của JVM nên kết quả phải được kiểm tra trên môi trường chạy thật.

## 2. `Can-Retransform-Classes` được khai báo ở đâu?

Khi đưa agent JAR vào JVM lúc khởi động bằng `-javaagent`, manifest có thể chứa:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.RetransformAgent
Can-Retransform-Classes: true

```

- `Premain-Class` là lớp Java có `public static void premain(String, Instrumentation)` được launcher gọi khi dùng `-javaagent`.
- `Can-Retransform-Classes` là thuộc tính **manifest**, không phải annotation hay tham số của `javac`.
- Thuộc tính phải nằm trong **main section** của `META-INF/MANIFEST.MF` trong **agent JAR thực sự được JVM nạp**.
- Giá trị `true`, không phân biệt hoa/thường, thể hiện yêu cầu. Nếu **thiếu**, đặt `false` hoặc nhập giá trị khác `true`, giá trị được xem là `false`.
- Agent chạy bằng cơ chế attach sử dụng `Agent-Class` thay cho `Premain-Class` và cũng cần khai báo capability phù hợp trong agent JAR.
- Với agent nhúng trong executable JAR sử dụng `Launcher-Agent-Class` và `agentmain`, cần kiểm tra capability của agent được JVM khởi chạy theo cơ chế đó; tên entry point không thay thế thuộc tính `Can-Retransform-Classes`.

Manifest chỉ mô tả **nhu cầu** của agent. Không có API Java chính thức để gọi `instrumentation.enableRetransform()` trong lúc chạy nhằm sửa lại một manifest đã thiếu capability.

### Điều kiện để `isRetransformClassesSupported()` trả về `true`

Theo hợp đồng của `Instrumentation`:

```text
isRetransformClassesSupported() == true
             chỉ khi
    agent yêu cầu Can-Retransform-Classes: true
                    VÀ
      JVM hiện tại hỗ trợ retransformation
```

Trên một JVM cụ thể, nhiều lần gọi phương thức này trong cùng vòng đời JVM **trả về cùng một kết quả**. Đây không phải tín hiệu biến động theo class đang được kiểm tra hay theo số transformer đã đăng ký.

| Manifest của agent | Runtime/JVM | Kết quả mong đợi |
| --- | --- | --- |
| Không có `Can-Retransform-Classes` | JVM có khả năng | `false` theo cấu hình agent |
| `Can-Retransform-Classes: false` | JVM có khả năng | `false` |
| `Can-Retransform-Classes: true` | JVM hỗ trợ, khả năng được cấp | `true` |
| `Can-Retransform-Classes: true` | JVM không hỗ trợ khả năng tùy chọn này | `false` |

**Không suy đoán từ số phiên bản Java**: API đã có từ Java 6, nhưng đặc tả vẫn coi retransformation là khả năng tùy chọn. Hãy log giá trị phương thức lúc agent khởi tạo.

## 3. Ba cấp độ cần kiểm tra trước khi retransform

### Cấp 1 — JVM/agent có khả năng không?

```java
boolean supported = instrumentation.isRetransformClassesSupported();
```

Nếu `false`, không gọi `addTransformer(transformer, true)` hoặc `retransformClasses(...)` như thể chắc chắn thành công. `addTransformer(..., true)` ném `UnsupportedOperationException` khi cấu hình JVM không cho phép retransformation.

### Cấp 2 — Transformer có được đăng ký để chạy lại không?

```java
instrumentation.addTransformer(transformer, true);
```

Đối số `true` ở đây có nghĩa **transformer cụ thể** được gọi lại khi retransform. Không có nghĩa “yêu cầu JVM retransform ngay” và không thay thế manifest.

Trong khi đó:

```java
instrumentation.addTransformer(transformer);
instrumentation.addTransformer(transformer, false);
```

Hai lời gọi tương đương về khả năng retransform của transformer: **`canRetransform = false`**. Transformer loại này có thể được gọi lúc định nghĩa class ban đầu và khi redefine; khi retransform, JVM **không gọi lại** `transform(...)` của nó. Tuy vậy, các kết quả transform trước đó của nó được áp lại khi xây dựng definition mới.

Một transformer đăng ký `true` **không tự làm class đã nạp biến đổi lại**. Muốn xử lý class đã nạp, vẫn cần gọi `retransformClasses(...)` ở thời điểm thích hợp.

### Cấp 3 — Class đích có modifiable không?

```java
if (instrumentation.isRetransformClassesSupported()
        && instrumentation.isModifiableClass(MyService.class)) {
    instrumentation.retransformClasses(MyService.class);
}
```

`isModifiableClass(Class<?>)` là câu hỏi **riêng** về class đích; phương thức này không phụ thuộc giá trị `isRetransformClassesSupported()`. Ví dụ, kiểu nguyên thủy (`int.class`) và kiểu mảng (`String[].class`) **không** modifiable.

Ngay cả khi cả hai điều kiện kiểm tra trả về `true`, `retransformClasses` vẫn có thể thất bại nếu transformer sinh ra class file không hợp lệ hoặc thay đổi bị JVM cấm. Vì vậy phải có đường xử lý lỗi.

## 4. `retransformClasses(...)` thực sự làm gì?

API:

```java
void retransformClasses(Class<?>... classes)
        throws UnmodifiableClassException;
```

Nó yêu cầu JVM **xây dựng lại định nghĩa** của một hay nhiều class đã nạp, sử dụng các transformer đã đăng ký. Có thể truyền nhiều class để JVM xử lý tập class liên quan với nhau; nếu lời gọi ném exception, đặc tả bảo đảm **không class nào trong tập được retransform thành công một phần**.

Sơ đồ đơn giản:

```text
Lớp đã được JVM định nghĩa
           |
           | instrumentation.retransformClasses(Foo.class)
           v
Bytes gốc của lần define/redefine gần nhất
           |
           +-- Transformer canRetransform=false:
           |       tái dùng kết quả đã lưu, KHÔNG gọi transform lại
           |
           +-- Transformer canRetransform=true:
           |       GỌI lại transform trên bytecode hiện tại của chuỗi
           |
           v
JVM kiểm tra/verify class file mới
           |
           +-- hợp lệ  -> cài đặt definition mới
           |
           +-- lỗi     -> ném exception; không cài đặt thay đổi
```

Ở đây “bytes gốc” là cách nói về cơ sở của lần định nghĩa hoặc redefine cuối; JVM không cam kết byte array đó **trùng từng byte** với tệp `.class` trên đĩa. Bố cục constant pool, thứ tự các entry hoặc một số attribute có thể khác nhưng ngữ nghĩa tương ứng vẫn phải đúng.

### Transformer `true` và `false` không được xử lý giống nhau

Giả sử lúc class được tải:

1. Transformer A đăng ký với `canRetransform=false` thay bytecode P thành Q.
2. Transformer B đăng ký với `canRetransform=true` biến Q thành R.

Lúc gọi `retransformClasses`:

1. JVM khởi đầu với bytes cơ sở thích hợp.
2. Phần biến đổi trước đó của A được áp lại **không gọi A.transform()**.
3. JVM **gọi B.transform()** để B có thể tạo kết quả mới.
4. JVM chỉ cài đặt definition sau khi kết quả thỏa ràng buộc.

Quy tắc thứ tự tổng quát còn bao gồm transformer native/JVMTI: nhóm không có khả năng retransform (Java rồi native) được xử lý trước nhóm có khả năng retransform (Java rồi native); trong mỗi nhóm, thứ tự đăng ký được tôn trọng. Hãy cẩn thận khi có nhiều agent cùng tác động tới một class.

### Retransform có làm mất trạng thái đối tượng không?

Thông thường, **không tạo lại instance** hoặc reset static field chỉ vì `retransformClasses` chạy. Class initializer không được chạy lại. Với phương thức đang có **stack frame hoạt động**, frame đó tiếp tục thực thi bytecode cũ; các lần gọi method tiếp theo sẽ dùng definition mới. Điều này lý giải vì sao instrumentation được áp vào ứng dụng sống cần cân nhắc thời điểm và hành vi giữa các thread.

## 5. Ví dụ Java 17 chạy được: bật capability, quan sát retransformation

Ví dụ dưới chứng minh ba điều:

1. JVM chỉ báo hỗ trợ khi agent JAR yêu cầu `Can-Retransform-Classes: true` và runtime đáp ứng.
2. Transformer `canRetransform=true` được gọi lại với `classBeingRedefined != null` khi retransform class đã nạp.
3. Trả về `null` chỉ quan sát, **không sửa bytecode**. Giá trị hàm của ứng dụng trước/sau sẽ giống nhau.

Các tệp trong cùng thư mục:

```text
retransform-demo/
├── RetransformAgent.java
├── DemoTarget.java
├── DemoApp.java
└── manifest-enabled.mf
```

Các class thuộc default package để lệnh biên dịch và đóng gói ngắn gọn. Trong sản phẩm thật, nên dùng package riêng cho agent.

### 5.1. Tệp `RetransformAgent.java`

```java
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;

public final class RetransformAgent {
    private static volatile Instrumentation instrumentation;

    private RetransformAgent() {
    }

    public static void premain(String agentArgs, Instrumentation inst) {
        instrumentation = inst;

        boolean supported = inst.isRetransformClassesSupported();
        System.out.println("[agent] supported=" + supported);

        if (!supported) {
            return;
        }

        inst.addTransformer(
                (loader, className, classBeingRedefined,
                 protectionDomain, classfileBuffer) -> {
                    // Chỉ in khi DemoTarget được retransform,
                    // không in ở lần tải class đầu tiên.
                    if ("DemoTarget".equals(className)
                            && classBeingRedefined != null) {
                        System.out.println(
                                "[transformer] retransform DemoTarget");
                    }
                    return null; // Không sửa bytecode.
                },
                true
        );
    }

    public static void retransform(Class<?> target) {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Agent not initialized");
        }

        if (!inst.isRetransformClassesSupported()) {
            System.out.println("[agent] skipped: unsupported");
            return;
        }

        if (!inst.isModifiableClass(target)) {
            System.out.println("[agent] skipped: class not modifiable");
            return;
        }

        try {
            inst.retransformClasses(target);
            System.out.println("[agent] retransform request completed");
        } catch (UnmodifiableClassException
                 | UnsupportedOperationException ex) {
            System.out.println(
                    "[agent] failed: " + ex.getClass().getSimpleName());
        }
    }
}
```

**Vì sao chạy được trên Java 17?** `ClassFileTransformer` là functional interface; lambda năm đối số ở `addTransformer` triển khai biến thể `transform(ClassLoader, String, Class<?>, ProtectionDomain, byte[])`. Không cần thư viện bytecode bên ngoài do transformer chỉ quan sát và trả `null`.

`volatile` dùng để bảo đảm khả năng nhìn thấy trường `Instrumentation` nếu sau này có truy cập giữa nhiều thread; trong demo này agent `premain` chạy trước `main` nên không cần cơ chế đồng bộ phức tạp hơn.

### 5.2. Tệp `DemoTarget.java`

```java
final class DemoTarget {
    static String message() {
        return "hello";
    }
}
```

Class này là mục tiêu. Không có transformer nào sửa bytecode, nên `message()` luôn trả `"hello"`.

### 5.3. Tệp `DemoApp.java`

```java
public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) {
        System.out.println("[main] before=" + DemoTarget.message());

        // DemoTarget đã được tải bởi lời gọi ở trên.
        RetransformAgent.retransform(DemoTarget.class);

        System.out.println("[main] after=" + DemoTarget.message());
    }
}
```

Ứng dụng chủ động yêu cầu retransform sau khi đã dùng `DemoTarget`. Trong thực tế, agent có thể tìm class đã tải qua `getAllLoadedClasses()` và chọn class đích theo tên/class loader, nhưng cần tránh quét và can thiệp thiếu kiểm soát vào mọi class.

### 5.4. Tệp `manifest-enabled.mf`

```text
Manifest-Version: 1.0
Premain-Class: RetransformAgent
Can-Retransform-Classes: true

```

Giữ **dòng trống kết thúc** main section của manifest. `Premain-Class` dùng khi khởi chạy agent bằng `-javaagent`; `Can-Retransform-Classes` yêu cầu capability. Vì các class đang ở default package, tên lớp `RetransformAgent` không có tiền tố package.

### 5.5. Biên dịch, đóng gói và chạy

Mở terminal tại thư mục chứa bốn tệp, dùng JDK 17 trở lên có hỗ trợ `--release 17`:

```bash
javac --release 17 RetransformAgent.java DemoTarget.java DemoApp.java
jar --create --file demo-enabled.jar --manifest manifest-enabled.mf RetransformAgent.class DemoTarget.class DemoApp.class
java -javaagent:demo-enabled.jar -cp demo-enabled.jar DemoApp
```

Với **HotSpot/JDK 17+ thông thường có hỗ trợ retransformation**, stdout của lệnh `java` là:

```text
[agent] supported=true
[main] before=hello
[transformer] retransform DemoTarget
[agent] retransform request completed
[main] after=hello
```

Ý nghĩa:

- `premain` chạy trước `DemoApp.main` và xác nhận capability.
- Việc gọi `DemoTarget.message()` đầu tiên chỉ tải class. Transformer được đăng ký nên có thể nhận callback khi tải lần đầu, nhưng câu lệnh `println` trong transformer cố ý chỉ chạy khi `classBeingRedefined != null`.
- `retransformClasses(DemoTarget.class)` gọi lại transformer đã đăng ký `true`; nó in dòng `[transformer] ...`.
- Vì transformer trả `null`, hành vi `message()` không đổi. **Retransformation không có nghĩa mọi lần đều phải thay bytecode.**

Nếu JVM không cấp capability, chương trình đi vào nhánh `supported=false` và in `skipped: unsupported`. Không được lấy output `supported=true` ở môi trường HotSpot điển hình làm cam kết cho mọi JVM.

### 5.6. Đối chứng: thiếu capability trong manifest

Tạo tệp **`manifest-disabled.mf`**:

```text
Manifest-Version: 1.0
Premain-Class: RetransformAgent
Can-Retransform-Classes: false

```

Đóng gói vào **JAR khác** để tránh nhầm artifact:

```bash
jar --create --file demo-disabled.jar --manifest manifest-disabled.mf RetransformAgent.class DemoTarget.class DemoApp.class
java -javaagent:demo-disabled.jar -cp demo-disabled.jar DemoApp
```

Trên cùng HotSpot hỗ trợ retransformation, stdout giờ là:

```text
[agent] supported=false
[main] before=hello
[agent] skipped: unsupported
[main] after=hello
```

Mã Java **không thay đổi**, khác biệt xuất phát từ **manifest của agent JAR**. Nếu bỏ hẳn dòng `Can-Retransform-Classes`, mặc định cũng là `false`.

### 5.7. Điều gì xảy ra nếu bỏ phần kiểm tra?

Nếu bỏ điều kiện `if (!supported) return;` và cứ gọi:

```java
inst.addTransformer(transformer, true);
```

trong cấu hình không hỗ trợ, API có thể ném **`UnsupportedOperationException`** ngay lúc đăng ký. Tương tự, gọi `inst.retransformClasses(...)` khi cấu hình không cho phép cũng ném `UnsupportedOperationException`. Đừng dùng exception này như cách thông thường để “thử xem JVM hỗ trợ không”; API đã cung cấp `isRetransformClassesSupported()` cho phép phân nhánh rõ ràng.

## 6. Giới hạn của retransformation

### 6.1. Không phải hot reload thay đổi cấu trúc tùy ý

Trên nhiều JVM, retransform dùng để sửa **mã của các phương thức hiện có** hoặc metadata được cho phép. Không thể giả định được phép:

- Thêm, xóa, đổi tên method hoặc field;
- Đổi chữ ký method, modifier có ảnh hưởng đến cấu trúc, superclass hoặc interfaces;
- Thay đổi các quan hệ cấu trúc như nestmate, record hoặc permitted-subclass theo cách JVM TI không hỗ trợ;
- Thay class file bằng version mới hơn JVM hiện tại có thể hiểu.

Tập thay đổi chính xác được quy định bởi **JVMTI `RetransformClasses`** và khả năng JVM. Biến đổi không hợp lệ có thể dẫn đến `UnsupportedOperationException`, `ClassFormatError`, `VerifyError` hoặc các dạng `LinkageError` phù hợp tình huống.

### 6.2. Không phải class nào cũng có thể sửa

`isModifiableClass()` trả về khả năng của class cụ thể. Kiểu nguyên thủy, mảng luôn không modifiable; một số class JVM đặc biệt cũng có thể bị giới hạn. Không nên đưa toàn bộ `getAllLoadedClasses()` vào `retransformClasses(...)` mà không lọc.

Cần hiểu rõ **class identity** gồm tên và class loader. Hai `com.example.Service` được định nghĩa bởi hai class loader khác nhau là hai class riêng. Nếu agent lọc chỉ theo tên mà không lưu ý loader, nó có thể đụng nhầm class của ứng dụng, plugin, test hoặc framework.

### 6.3. Không bảo đảm mọi frame đang chạy chuyển ngay sang mã mới

Khi phương thức đang thực thi, frame cũ có thể tiếp tục với bytecode phiên bản cũ; những lần gọi mới dùng definition mới. Instance và giá trị static hiện có không tự được tạo lại/reset. Vì vậy, “retransform thành công” không đồng nghĩa tất cả thread sẽ quan sát thay đổi cùng một thời điểm.

### 6.4. Capability đã cấp không đồng nghĩa transformer nào cũng chạy lại

Một transformer đăng ký bằng `addTransformer(transformer)` **không được gọi lại** lúc retransform; phần kết quả đã áp của nó được reuse. Cần đăng ký với `addTransformer(transformer, true)` **từ đầu** khi thực sự muốn callback trên các class đã nạp.

Không có thao tác trên cùng registration để đổi `false` thành `true`; có thể quản lý registration (hủy/đăng ký lại) khi capability đã được hỗ trợ, nhưng phải tính đến các class đã biến đổi, thứ tự transformer và race với class loading.

## 7. So sánh với load-time transform và redefine

| Tiêu chí | Load-time transform | Retransform | Redefine |
| --- | --- | --- | --- |
| Kích hoạt | JVM chuẩn bị định nghĩa class | `retransformClasses(Class<?>...)` | `redefineClasses(ClassDefinition...)` |
| Class đã nạp? | Chưa định nghĩa tại thời điểm transformer được gọi | **Có** | **Có** |
| Nguồn bytecode | Bytes được gửi để định nghĩa class | Bytes cơ sở của định nghĩa/redefine gần nhất và chuỗi transformer | Bytes thay thế do caller cung cấp |
| Yêu cầu capability | Không cần `Can-Retransform-Classes` để đăng ký transformer `false` | Cần `Can-Retransform-Classes` + VM hỗ trợ | Cần `Can-Redefine-Classes` + VM hỗ trợ |
| API điều khiển | `addTransformer(transformer)` | `addTransformer(transformer, true)` và `retransformClasses` | `redefineClasses` với `ClassDefinition` |
| Hạn chế | Bytecode phải hợp lệ và phù hợp class được định nghĩa | Giới hạn thay đổi class đã nạp | Giới hạn thay đổi class đã nạp |

`Can-Retransform-Classes` và `Can-Redefine-Classes` là hai manifest capability **độc lập**. Không suy rằng bật một là bật cả hai. `isRetransformClassesSupported()` không dùng để thay thế `isRedefineClassesSupported()`.

## 8. Thiết kế agent an toàn với capability tùy chọn

Trong agent quan sát hiệu năng, coverage hay tracing, một quy trình thực tế thường là:

1. Khi `premain` hoặc `agentmain` nhận `Instrumentation`, đọc/log `isRetransformClassesSupported()`.
2. Nếu `true`, đăng ký transformer với `canRetransform=true` và chuẩn bị cơ chế chọn đúng class đã nạp; nếu `false`, dùng chế độ chỉ quan sát class nạp trong tương lai với `addTransformer(transformer, false)` khi điều đó đáp ứng nhu cầu.
3. Khi cần sửa class đã nạp, lọc `getAllLoadedClasses()` theo loại class, class loader, module hoặc tên; kiểm tra `isModifiableClass` cho từng class.
4. Thực hiện `retransformClasses` theo batch có kiểm soát; các transformer nên có hành vi xác định, idempotent và xử lý lỗi rõ ràng.
5. Kiểm tra tác động trên môi trường JVM mục tiêu: hiệu năng startup/runtime, tương tác giữa nhiều agent, số lần callback, thread hiện hoạt và lỗi verify/linkage.
6. Khi ngừng dùng transformer, có thể gọi `removeTransformer(transformer)`; lưu ý vẫn có thể nhận callback đang diễn ra do các class load song song, và việc hủy registration **không tự động hoàn tác các bytecode đã cài**.

### “Fallback” khi retransform không hỗ trợ

Một số agent chỉ cần đo các class được nạp **sau khi agent được gắn vào**. Khi capability false, đăng ký transformer `false` vẫn cho phép load-time instrumentation của các class mới; không thể kỳ vọng các class đã nạp đi qua transformer. Agent muốn quan sát các class đã nạp có thể chọn giải pháp khác như dữ liệu thống kê sẵn có, logging từ ứng dụng hoặc giảm phạm vi tính năng. Không nên tuyên bố đã instrument đầy đủ nếu thực tế đang thiếu các class quan trọng.

### Đừng gắn retransform vào vòng lặp quá dày

Retransformation phải đi qua xử lý class file/verification và có thể ảnh hưởng độ trễ, JIT hoặc hành vi của mã đang chạy. Không mặc định gọi lặp vô hạn cho mọi class để “giữ agent cập nhật”. Chỉ kích hoạt khi có thay đổi cấu hình hoặc yêu cầu đo đạc rõ ràng, đồng thời quan sát thời gian và lỗi.

## 9. Những lỗi thường gặp và cách khắc phục

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| `isRetransformClassesSupported()` là `false` trên JDK có vẻ đủ mới | Manifest trong **agent JAR thực tế** có `Can-Retransform-Classes: true` chưa? Có khởi chạy đúng `-javaagent`/entry point không? JVM có hỗ trợ capability không? |
| `addTransformer(t, true)` ném `UnsupportedOperationException` | Đang yêu cầu transformer có khả năng retransform nhưng cấu hình không cấp; phải kiểm tra `isRetransformClassesSupported()` trước |
| Không thấy `transform()` được gọi lại | Transformer có được đăng ký với tham số `true` không? Có thực sự gọi `retransformClasses` cho class đã nạp? Bộ lọc class name/loader đúng chưa? |
| `isModifiableClass(c)` là `false` | Class có thể là array/primitive hoặc class JVM không cho sửa; bỏ qua thay vì cố retransform |
| `retransformClasses` ném `UnmodifiableClassException` | Có class trong tập không modifiable; kiểm tra và chia batch để xác định class |
| `retransformClasses` ném `UnsupportedOperationException` | Capability bị thiếu hoặc transformer đã tạo thay đổi không được hỗ trợ đối với class đang hoạt động |
| `ClassFormatError`/`VerifyError`/`LinkageError` | Bytecode sinh ra không hợp lệ; kiểm tra class-file version, stack map frames, constant pool, schema và thư viện ASM/Byte Buddy |
| Retransform thành công nhưng hành vi không đổi | Transformer trả `null`, không instrument phương thức mục tiêu, filter sai, hoặc frame đang chạy vẫn dùng mã cũ |
| Sau `removeTransformer` vẫn thấy tác động cũ | Unregister không tự undo definition đang được JVM sử dụng; cần thiết kế hoàn nguyên riêng nếu cần |
| Chạy với `-cp` nhưng không có agent | Chưa khởi động bằng `-javaagent` hoặc cơ chế agent phù hợp; chỉ có manifest trong JAR nằm trên classpath không tự kích hoạt |

Khi chẩn đoán, xem cả **đường chạy thực tế** (`java -javaagent:...`, dynamic attach hay executable JAR), **manifest sau build**, JVM đang chạy, **class loader**, và stack trace chính xác. Một thông báo “unsupported” có thể đến từ JVM, thư viện bytecode hoặc agent; cần phân biệt nguồn trước khi sửa.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Một agent JAR có `Premain-Class` nhưng không có `Can-Retransform-Classes`. Agent gọi `addTransformer(t)` rồi chạy ổn. Điều đó chứng minh retransform được hỗ trợ chưa?

**Đáp án:** Chưa. `addTransformer(t)` mặc định là `canRetransform=false`, cho phép quan sát/biến đổi class load-time. Khả năng retransform cần manifest đúng và JVM cấp; đọc `isRetransformClassesSupported()` để biết.

**Câu 2.** `Can-Retransform-Classes: true` nhưng `isRetransformClassesSupported() == false`. Có thể gọi `retransformClasses` để “buộc” JVM bật tính năng không?

**Đáp án:** Không. Capability là tùy chọn của JVM; lời gọi có thể ném `UnsupportedOperationException`. Chọn đường fallback phù hợp hoặc dùng runtime có hỗ trợ.

**Câu 3.** JVM hỗ trợ retransformation nhưng transformer được thêm bằng `addTransformer(t, false)`. Khi `retransformClasses` chạy, có gọi lại `t.transform(...)` không?

**Đáp án:** Không. Kết quả biến đổi trước của transformer này được áp lại theo hợp đồng; chỉ transformer đăng ký `true` mới được gọi lại trong retransformation.

**Câu 4.** `isRetransformClassesSupported() == true` có đồng nghĩa mọi class sửa được không?

**Đáp án:** Không. Còn `isModifiableClass(c)`, các giới hạn class-file/JVMTI và tính hợp lệ của bytecode. Class nguyên thủy/mảng không thể sửa bằng cơ chế này.

**Câu 5.** Retransform một class đang có method chạy dở có tự chạy lại static initializer hay thay nội dung stack frame cũ không?

**Đáp án:** Không. Static initializer không chạy lại chỉ do retransform; frame đang hoạt động tiếp tục với bytecode cũ, invocation mới sử dụng definition mới.

## 11. Tài liệu chính thức để tra cứu

- [Oracle Java SE 17 — `Instrumentation` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `isRetransformClassesSupported`, `isModifiableClass`, `addTransformer`, `retransformClasses`.
- [Oracle Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): các manifest attributes và cơ chế khởi động agent.
- [Oracle Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): thứ tự transformer, đặc điểm callback và điều kiện retransform.
- [Oracle Java SE 21 — `Instrumentation` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): quy trình retransformation, lỗi và ràng buộc khi sửa class đã nạp.
- [JVM Tool Interface — `RetransformClasses`](https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html): giới hạn thay đổi class file ở tầng VM.

**Ghi nhớ:** Manifest `Can-Retransform-Classes: true` chỉ **yêu cầu** capability; `isRetransformClassesSupported()` xác nhận **khả năng được cấp**. Muốn biến đổi class đã nạp, đăng ký transformer với `canRetransform=true`, kiểm tra `isModifiableClass` và gọi `retransformClasses`. Khả năng được cấp không loại bỏ các giới hạn class file, runtime hay việc kiểm thử.
