# Vì sao thêm wrapper khi lớp đã nạp chịu giới hạn thay đổi cấu trúc

## 1. Bài toán: muốn đo native method nhưng class đã được nạp

Trong Java Instrumentation, ta có thể chèn lệnh ghi thời gian, trace hoặc metric vào **bytecode của Java method**. Nhưng native method, chẳng hạn:

~~~java
package demo;
public final class NativeTarget {
    public native int ping(int input);
}
~~~

là một method có cờ **`ACC_NATIVE`** và không chứa thuộc tính **`Code`** với Java bytecode body. Phần thực thi thực tế của `ping` nằm ở native implementation được liên kết qua JNI hoặc cơ chế khác của JVM. **Không có body Java để chèn trực tiếp `invokestatic Probe.before()` hay `Probe.after()`.**

Một giải pháp phổ biến là **bọc** lời gọi native bằng **Java wrapper** có bytecode: wrapper ghi thời gian trước/sau rồi gọi native method thật qua tên đã đổi. API `Instrumentation.setNativeMethodPrefix` (tương ứng JVM TI `SetNativeMethodPrefix`) hỗ trợ native method name resolution khi transform class theo mẫu này.

**Tuy nhiên, wrapper mới thêm vào class đã nạp thường yêu cầu thay đổi cấu trúc method table:** thêm method hoặc đổi cờ `native` của method cũ. Java 17 JVM TI `RedefineClasses`/`RetransformClasses` **không hỗ trợ những thay đổi schema đó**. Agent attach muộn không thể bỏ qua giới hạn chỉ bằng cách gọi `setNativeMethodPrefix`.

Mục tiêu của bài:

1. Giải thích tại sao native method cần Java wrapper để thực hiện bytecode instrumentation.
2. Chỉ ra wrapper **ở lần định nghĩa class đầu tiên** khác wrapper **sau khi class đã nạp** thế nào.
3. Phân biệt các thay đổi method body hợp lệ với việc thêm method/field/đổi modifiers bị hạn chế.
4. Hiểu chức năng thực tế của native method prefix và JVMTI `NativeMethodBind`.
5. Thực hành với Java 17+: thêm method wrapper vào loaded class bị từ chối; tạo hình dạng Java/native wrapper quá muộn cũng bị từ chối; dùng **helper ngoài class + chỉ sửa body Java method hiện hữu** thì thành công.
6. Chọn giải pháp khi JVM đã load native class: instrument caller, thay thiết kế build/startup hoặc dùng native binding hook có kiểm soát.

## 2. Native method không có Java Code attribute

Xét Java method thường:

~~~java
public int compute(int input) {
    return input * 2;
}
~~~

Sau khi compiler tạo file `.class`, method `compute` có bytecode instruction như `iload`, `imul`, `ireturn`. Bytecode transformer có thể xem, biến đổi, bổ sung calls và sinh classfile mới (với stack frames, constant pool và descriptors hợp lệ).

Trái lại:

~~~java
public native int ping(int input);
~~~

có declaration và descriptor, nhưng **không có code Java** để biến đổi trực tiếp. Một Java agent dùng `ClassFileTransformer` không thể giả vờ rằng `native ping` có một Java method body sẵn có.

~~~text
Java method:
  Caller -> compute(int) -> bytecode trong .class -> kết quả

Native method:
  Caller -> ping(int) -> native method resolution -> JNI function -> kết quả
                                        |
                          Java Code attribute không tồn tại
~~~

Nếu mục tiêu chỉ là đo **Java call-site** dẫn tới `ping`, có thể instrument Java caller có body. Nhưng nếu muốn một Java-level entry/exit hook thống nhất cho **mọi invocation `ping`**, bạn cần tổ chức wrapper từ đúng thời điểm, hoặc sử dụng native interception khác.

**Đừng đánh đồng:** `java.lang.instrument` làm việc ở tầng Java classfile, còn JVM TI là native API rộng hơn với các callbacks/capabilities. Hai tầng có thể hỗ trợ nhau nhưng không cùng một khái niệm.

## 3. Mô hình wrapper với setNativeMethodPrefix

Tài liệu chính thức Java SE 17 minh họa việc biến một declaration native:

~~~java
native boolean foo(int x);
~~~

thành hai methods trong classfile **trước khi JVM định nghĩa class**:

~~~java
boolean foo(int x) {
    Probe.enter(x);
    try {
        return $agent$foo(x);
    } finally {
        Probe.exit();
    }
}

native boolean $agent$foo(int x);
~~~

Đây là **hình dạng mã sau transform**, không phải file Java độc lập có thể chạy ngay: cần `Probe`, native implementation, thư viện JNI phù hợp và agent/classfile transformer. Tên `$agent$` chỉ minh họa prefix; production phải dùng prefix đặc thù, ít xung đột.

Cơ chế:

- Caller vẫn gọi **`foo`**, nên public API không cần đổi tên.
- `foo` giờ là **non-native Java wrapper**, có body để thu thập entry/exit, ghi lỗi, latency, trace.
- Method có tên prefix **`$agent$foo`** là **native declaration** mà wrapper gọi.
- JVM thử liên kết tên `$agent$foo` tới JNI implementation; nhờ native method prefix được đăng ký, khi resolution thông thường thất bại JVM có thể thử loại prefix để tìm implementation gốc tương ứng với `foo`.
- Với `RegisterNatives` cũng có cơ chế retry phù hợp theo hợp đồng prefix.
- Method native thực tế vẫn do native library triển khai; `setNativeMethodPrefix` **không tự tạo JNI implementation**.

**Điều gì đã đổi?** Từ **một** method `native foo` thành **hai** method declarations: Java `foo` và native `$agent$foo`. `foo` bị đổi modifier từ native sang non-native, và `$agent$foo` là method mới. Đây chính là nguyên nhân tạo vấn đề khi class đã nạp.

### 3.1. Prefix không có nghĩa wrapper tự phát sinh

~~~java
inst.setNativeMethodPrefix(transformer, "$agent$");
~~~

Dòng trên **chỉ điều chỉnh native name-resolution retry** cho một transformer đã đăng ký. Nó không:

- tự sinh bytecode cho `foo`;
- tự thêm `$agent$foo` vào class;
- tự thay body C/C++ của native function;
- bỏ qua schema restrictions của loaded class;
- tự load shared library hay sửa signature JNI.

Nếu `foo` đã load là native và không có Java wrapper hợp lệ, gọi prefix một mình không cung cấp Java-level tracing.

### 3.2. Tại sao có thể transform khi class chưa load?

Trước **lần định nghĩa đầu tiên**, `ClassFileTransformer.transform` hoặc JVM TI `ClassFileLoadHook` có thể sinh một **classfile mới sẽ được JVM định nghĩa lần đầu**. Chưa có instance layout, class identity hay active frame thuộc định nghĩa cũ cần được giữ lại, nên schema đã biến đổi có thể được JVM chấp nhận nếu hợp lệ.

~~~text
Load lần đầu:
   classfile có native foo
         |
   ClassFileTransformer / ClassFileLoadHook
         |
   tạo Java foo wrapper + prefixed native foo
         |
   JVM verify và DEFINE CLASS với schema đã biến đổi
         |
   Java caller gọi foo -> wrapper -> native binding
~~~

**Điểm quyết định là class được định nghĩa lần đầu**, không phải chỉ thời điểm agent được attach. Startup agent nên đăng ký transformer sớm và lọc class cụ thể trước khi classloader nạp target.

## 4. Khi đã load, JVM TI giới hạn thay đổi method và field

Theo JVM TI Java 17, cả **`RedefineClasses`** lẫn **`RetransformClasses`** có thể thay đổi **bodies của method**, constant pool và một số attributes. Chúng **không được** tùy tiện:

- thêm, xóa hoặc đổi tên method/field;
- đổi descriptor/chữ ký method;
- đổi method/class modifiers, gồm cờ `native`;
- đổi superclass/interfaces;
- đổi một số attributes như `NestHost`, `NestMembers`, `Record` hoặc `PermittedSubclasses`.

Đặc tả có thể được nới trong các release tương lai, nhưng không được giả định JVM đang dùng hỗ trợ đổi schema. **Java agent không thể biến một request sai cấu trúc thành hợp lệ bằng cách bật nhiều capability hơn.**

| Cách sửa loaded class | Phạm vi thay đổi | Rủi ro giới hạn |
|---|---|---|
| Thêm `wrapper()` mới trong class | Thêm method | Không được theo giới hạn JVMTI thông thường |
| Đổi native `foo` thành Java `foo` | Đổi `ACC_NATIVE`/method code shape | Không được tùy ý |
| Thêm native `$prefix$foo` | Thêm method | Không được |
| Thêm field `probeState` | Thay field/layout | Không được |
| Chèn `Probe.enter` vào body **Java method đã tồn tại** | Body-only, schema giữ | Có thể hợp lệ |
| Sửa Java method hiện hữu gọi **helper class khác** | Body-only ở target | Có thể hợp lệ, cần helper visibility |
| Chặn tại Java caller đang có body | Body của caller | Có thể hợp lệ, tùy phạm vi và loader |
| Đăng ký native `NativeMethodBind` proxy | Native binding address, không thêm Java method | Khác cơ chế và capability |

### 4.1. Những mã lỗi quan trọng

Ở tầng JVM TI có các mã:

- `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_METHOD_ADDED`: replacement cần thêm method;
- `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_METHOD_DELETED`: replacement xóa method;
- `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_SCHEMA_CHANGED`: thay đổi field;
- `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_METHOD_MODIFIERS_CHANGED`: thay modifier method, có thể là `native`;
- `JVMTI_ERROR_UNSUPPORTED_REDEFINITION_HIERARCHY_CHANGED`: đổi hierarchy.

Ở tầng Java Instrumentation, `redefineClasses` hoặc `retransformClasses` có thể ném **`UnsupportedOperationException`** cho thay đổi không hỗ trợ. Thông điệp cụ thể khác nhau giữa JVM; đừng mong có Java exception mang tên nguyên văn JVMTI error code.

**`isModifiableClass(target) == true` chỉ là điều kiện cần**, không phải bằng chứng có thể thêm method. Class có thể modifiable để **sửa body** mà vẫn không modifiable theo kiểu **thêm schema**.

### 4.2. Đừng trộn các loại lỗi

- `UnmodifiableClassException`: target class không modifiable.
- `UnsupportedOperationException`: VM/config không cho thao tác hoặc thay đổi không được hỗ trợ.
- `ClassFormatError`/`VerifyError`: bytes sai định dạng hoặc thất bại ở verifier.
- `NoClassDefFoundError`/`IllegalAccessError`: có thể do class name/helper/loader/linkage.
- `UnsatisfiedLinkError`: native function chưa liên kết được, thường cần kiểm tra library/prefix/JNI names.
- `UnsupportedClassVersionError`: classfile major vượt runtime.

Không dựa vào một lỗi sai classfile để đánh giá khả năng thêm wrapper. Lab sau dùng các file đã compile hợp lệ nhưng bị từ chối vì **schema**.

## 5. setNativeMethodPrefix: capability và thời điểm sử dụng

`Instrumentation.setNativeMethodPrefix(ClassFileTransformer, String)` là một **optional capability**. Với Java agent:

1. Main manifest có **`Can-Set-Native-Method-Prefix: true`**.
2. JVM trả `inst.isNativeMethodPrefixSupported() == true`.
3. `ClassFileTransformer` phải được đăng ký bằng `addTransformer` trước.
4. Agent gắn **prefix riêng** với transformer bằng `setNativeMethodPrefix`.
5. Transformer sinh classfile wrapper hợp lệ **tại load-time** nếu cần thêm methods/đổi native modifier.
6. Prefix được giữ khi các prefixed native methods còn có thể cần resolution.

Mẫu cấu hình:

~~~java
public static void premain(String arg, Instrumentation inst) {
    if (!inst.isNativeMethodPrefixSupported()) {
        throw new IllegalStateException(
                "Native prefix not supported");
    }
    ClassFileTransformer tx = createNativeWrapperTransformer();
    inst.addTransformer(tx);
    inst.setNativeMethodPrefix(tx, "$myagent$");
}
~~~

**Đây là trích đoạn minh họa, chưa phải chương trình biên dịch độc lập**: `createNativeWrapperTransformer` cần được viết để sinh classfile hợp lệ; phải import `java.lang.instrument.*`. Không dùng nó với `Target` đã load rồi giả định schema changes thành công.

Manifest cho agent thuộc loại này:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.NativeWrapAgent
Can-Set-Native-Method-Prefix: true

~~~

Giữ newline ở cuối manifest. Các capability **`Can-Redefine-Classes`**, **`Can-Retransform-Classes`** và **`Can-Set-Native-Method-Prefix`** là những thứ khác nhau. Bật prefix không nới giới hạn class schema.

### 5.1. Tên prefix và JNI native resolution

Khi method `$myagent$foo` không tìm được implementation JNI theo tên đã đổi, JVM có thể retry dựa trên prefix để tìm implementation của `foo`. Điều này áp dụng theo quy tắc tương ứng cho lookup tên JNI và `RegisterNatives`.

- Prefix phải đủ riêng để không match method đã tồn tại.
- Native function phải có JNI ABI/signature đúng.
- Native library phải được nạp trong ngữ cảnh phù hợp.
- Nhiều transformers có thể xếp nhiều lớp wrapper/prefix, nên cần kiểm soát thứ tự.
- Native resolution có thể xảy ra muộn; đừng dỡ prefix ngay khi callback `transform` kết thúc.

Nếu không có implementation native hợp lệ, sẽ vẫn xuất hiện `UnsatisfiedLinkError`. Prefix **không tạo C/C++ symbol thay cho bạn**.

## 6. Chọn giải pháp nếu class đã nạp

Có bốn hướng khác nhau, không thay thế lẫn nhau.

### A. Chèn vào Java call-site

Thay body của Java method **gọi** native target, chèn probe trước và sau call instruction:

~~~text
Java caller:
  trước:   result = nativeTarget.ping(x)
  sau:     beforeNativeCall()
           result = nativeTarget.ping(x)
           afterNativeCall()
~~~

Đây là **sơ đồ thuật toán**, không phải Java method hoàn chỉnh. Ưu điểm: không sửa native method và không cần thêm method vào class native target. Nhược điểm: chỉ bao phủ những **call-sites thực sự được instrument**; lời gọi từ native code hoặc caller khác có thể không đi qua hook.

### B. Helper ngoài class + body-only transform của Java method có sẵn

Nếu target là Java method `compute` đã có body, ta có thể thay body để gọi một **`Wrapper` class khác**. Target không cần thêm method hay field. Đây là con đường lab sẽ kiểm chứng.

Nhưng **native method không có Java body** để thay theo cách này. Không được dùng thành công của `compute` để suy rằng `native ping` cũng sửa body được.

### C. NativeMethodBind ở JVM TI

Ở tầng native, JVM TI có **`NativeMethodBind`**, một event khi VM liên kết Java native method tới địa chỉ function native. Agent native có thể đổi `*new_address_ptr` để sử dụng một native proxy có JNI ABI đúng.

Đây là **native binding interception**, không thêm Java method vào class đã load. Điều kiện: phải có capability, callback đăng ký và event bật trước thời điểm binding muốn chặn; binding đã xảy ra không được tự replay khi agent attach muộn.

### D. Startup/load-time wrapper hoặc deployment mới

Nếu muốn đúng kỹ thuật **Java wrapper + native prefix**, lựa chọn dễ chứng minh hơn là đăng ký agent **trước lần đầu class được define** hoặc đưa wrapper vào **source/build artifact** trước khi triển khai. Nếu schema cần thay đổi mà class đã load, cân nhắc một JVM/process mới thay vì giả vờ redefinition có thể migrate schema cũ.

## 7. Thực hành Java 17+: xác nhận giới hạn qua agent thật

Lab này dùng `Instrumentation.redefineClasses` với **replacement class bytes**. Nó kiểm tra:

1. Thêm `wrapper(int)` **bên trong class đã load** bị từ chối.
2. Muốn biến `native ping` thành Java wrapper + native method mới cũng bị từ chối.
3. Giữ schema cũ nhưng sửa **body của Java method `compute`** để gọi **class helper `Wrapper` độc lập** thì thành công.
4. Existing object giữ state cũ; phép tính vẫn trả đúng kết quả.

**Không cần JNI library** vì trong lab ta chỉ **load `NativeTarget.class`** chứ **không gọi native `ping`**. Lab này đo **khả năng thay schema**, không kiểm thử native prefix resolution.

### 7.1. Cây thư mục

~~~text
loaded-wrapper-lab/
├── agent.mf
├── src/
│   ├── agent/demo/SwapAgent.java
│   ├── app/demo/Main.java
│   ├── app/demo/Wrapper.java
│   ├── v1/demo/Target.java
│   ├── bad/demo/Target.java
│   ├── good/demo/Target.java
│   ├── native1/demo/NativeTarget.java
│   └── nativebad/demo/NativeTarget.java
└── out/
    ├── agent/
    ├── base/
    ├── bad/
    ├── good/
    ├── nativebad/
    └── swap-agent.jar
~~~

**Ba tệp `Target.java` có cùng tên package/class** là chủ ý để build **ba classfiles riêng**, không được compile chung. Runtime classpath chỉ dùng **`out/base`**, còn agent đọc `.class` trong `out/bad`, `out/good`, `out/nativebad` làm replacement bytes.

### 7.2. Agent: src/agent/demo/SwapAgent.java

~~~java
package demo;

import java.lang.instrument.ClassDefinition;
import java.lang.instrument.Instrumentation;
import java.nio.file.Files;
import java.nio.file.Path;

public final class SwapAgent {
    private static Instrumentation inst;

    public static void premain(
            String args, Instrumentation instrumentation) {
        inst = instrumentation;
    }

    public static void change(
            Class<?> target, Path path) throws Exception {
        if (!inst.isRedefineClassesSupported()
                || !inst.isModifiableClass(target)) {
            throw new IllegalStateException(
                    "Redefinition unsupported");
        }
        inst.redefineClasses(new ClassDefinition(
                target, Files.readAllBytes(path)));
    }
}
~~~

Đây là **agent hoàn chỉnh cho lab**. `premain` lấy `Instrumentation`; `change` đọc bytes classfile đã biên dịch, kiểm tra quyền và gọi `redefineClasses`. Nếu thay đổi schema bị cấm, JVM ném lỗi, không cài định nghĩa lỗi.

Main manifest `agent.mf`:

~~~text
Manifest-Version: 1.0
Premain-Class: demo.SwapAgent
Can-Redefine-Classes: true

~~~

`Can-Redefine-Classes` chỉ yêu cầu quyền redefine; không cấp quyền thêm methods/fields vào loaded class. Lệnh chạy `-javaagent` sẽ nạp agent trước `main`, nhưng `change` chỉ được gọi **sau khi app đã tạo object và nạp target**.

### 7.3. Class V1: src/v1/demo/Target.java

~~~java
package demo;

public final class Target {
    private int factor = 2;

    public void setFactor(int factor) {
        this.factor = factor;
    }

    public int raw(int input) {
        return input * factor;
    }

    public int compute(int input) {
        return raw(input);
    }
}
~~~

Class ban đầu có các methods `setFactor`, `raw`, `compute` và constructor mặc định. Main gán `factor=7`, nên `compute(5) == 35`.

### 7.4. V2 bị từ chối: src/bad/demo/Target.java

~~~java
package demo;

public final class Target {
    private int factor = 2;

    public void setFactor(int factor) {
        this.factor = factor;
    }

    public int raw(int input) {
        return input * factor;
    }

    public int compute(int input) {
        return wrapper(input);
    }

    private int wrapper(int input) {
        return raw(input);
    }
}
~~~

Bản này chỉ thêm một private method đơn giản `wrapper(int)`. Nhưng vì **method list khác V1**, VM tiêu chuẩn từ chối redefinition. Không quan trọng method mới có side effect nhỏ hay không: đây là **schema change**.

### 7.5. V3 body-only: src/good/demo/Target.java

~~~java
package demo;

public final class Target {
    private int factor = 2;

    public void setFactor(int factor) {
        this.factor = factor;
    }

    public int raw(int input) {
        return input * factor;
    }

    public int compute(int input) {
        return Wrapper.around(this, input);
    }
}
~~~

V3 có **cùng field list/method list/descriptors với V1**. Chỉ body `compute` đổi từ `raw(input)` sang `Wrapper.around(this,input)`. Vì `Wrapper` là **class khác** chứ không phải method mới của `Target`, target schema không đổi.

Tính đúng của V3 còn phụ thuộc helper có thể được JVM nạp, có visibility phù hợp và không đệ quy vào `compute`.

### 7.6. Helper: src/app/demo/Wrapper.java

~~~java
package demo;

public final class Wrapper {
    private Wrapper() {
    }

    public static int around(Target target, int input) {
        System.out.println("wrapper:before input=" + input);

        int result = target.raw(input);

        System.out.println("wrapper:after result=" + result);

        return result;
    }
}
~~~

`Wrapper` là một class **độc lập**, đã được biên dịch cùng ứng dụng vào `out/base`. `around` gọi **`raw`** để giữ logic gốc, **không gọi `compute`**: vì V3 `compute` đang gọi `around`, gọi ngược lại `compute` sẽ tạo recursion vô hạn.

### 7.7. NativeTarget V1: src/native1/demo/NativeTarget.java

~~~java
package demo;

public final class NativeTarget {
    public native int ping(int input);
}
~~~

Không gọi `ping` trong lab, nên không có yêu cầu native library. Chỉ cần tải `NativeTarget.class` để VM có class identity rồi thử redefine.

### 7.8. Native wrapper quá muộn: src/nativebad/demo/NativeTarget.java

~~~java
package demo;

public final class NativeTarget {
    public int ping(int input) {
        return wrappedPing(input);
    }

    private native int wrappedPing(int input);
}
~~~

Từ một `native ping` ban đầu, V2 cố:

- đổi `ping` từ native sang Java method có body;
- thêm method mới `wrappedPing` mang cờ native.

**Cả hai loại thay đổi đều là vấn đề** đối với schema của class đã nạp. Đây là file test cho VM từ chối, không phải wrapper JNI chạy độc lập.

### 7.9. Main: src/app/demo/Main.java

~~~java
package demo;

import java.nio.file.Path;

public final class Main {
    public static void main(String[] args)
            throws Exception {
        Target target = new Target();
        target.setFactor(7);

        System.out.println("before=" + target.compute(5));

        try {
            SwapAgent.change(Target.class, Path.of(args[0]));
            System.out.println("added-method:accepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("added-method:rejected");
        }

        System.out.println(
                "after-rejected=" + target.compute(5));

        try {
            SwapAgent.change(
                    NativeTarget.class, Path.of(args[2]));
            System.out.println("native-wrap:accepted");
        } catch (UnsupportedOperationException expected) {
            System.out.println("native-wrap:rejected");
        }

        SwapAgent.change(
                Target.class, Path.of(args[1]));
        System.out.println("body-only:accepted");
        System.out.println(
                "after-valid=" + target.compute(5));
    }
}
~~~

Thứ tự:

1. Tạo **một object Target**, gán factor=7, gọi V1 `compute(5)`.
2. Cố redefine sang V2 thêm method → JVM từ chối; V1 vẫn hoạt động.
3. Cố redefine native class sang dạng Java wrapper + prefixed native method mới → JVM từ chối.
4. Redefine target sang V3 **không thêm method/field**, chỉ đổi body của `compute`.
5. Gọi `compute(5)` trên **object ban đầu**, helper in before/after, kết quả vẫn là 35.

Lab bắt `UnsupportedOperationException` để output ổn định giữa các HotSpot hỗ trợ redefine. Trong ứng dụng thật nên ghi nguyên nhân chi tiết, không coi việc từ chối là “thay thành công”.

## 8. Lệnh build và output đã kiểm chứng

Ở gốc project `loaded-wrapper-lab`, tạo thư mục output bằng Bash:

~~~bash
mkdir -p out/agent out/base out/bad out/good out/nativebad
~~~

Hoặc PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out/agent, out/base, out/bad, out/good, out/nativebad
~~~

Biên dịch bằng **JDK 17+ có hỗ trợ `--release 17`**:

~~~bash
javac --release 17 -d out/agent src/agent/demo/SwapAgent.java
javac --release 17 -cp out/agent -d out/base src/v1/demo/Target.java src/native1/demo/NativeTarget.java src/app/demo/Wrapper.java src/app/demo/Main.java
javac --release 17 -d out/bad src/bad/demo/Target.java
javac --release 17 -cp out/base -d out/good src/good/demo/Target.java
javac --release 17 -d out/nativebad src/nativebad/demo/NativeTarget.java
jar --create --file out/swap-agent.jar --manifest agent.mf -C out/agent .
~~~

Trong các output directories:

- `out/base` có target V1, native V1, `Main` và `Wrapper`.
- `out/bad` có target V2 với method mới.
- `out/good` có target V3 với cùng schema.
- `out/nativebad` có native-wrapper replacement không hợp lệ sau load.
- Agent JAR chứa `SwapAgent.class` và manifest; không chứa các replacement classes.

Chạy:

~~~bash
java -Xverify:all -javaagent:out/swap-agent.jar -cp out/base demo.Main out/bad/demo/Target.class out/good/demo/Target.class out/nativebad/demo/NativeTarget.class
~~~

**Stdout đã đo được từ bản test chạy trên JDK 24.0.2 với bytecode biên dịch `--release 17`:**

~~~text
before=35
added-method:rejected
after-rejected=35
native-wrap:rejected
body-only:accepted
wrapper:before input=5
wrapper:after result=35
after-valid=35
~~~

Lab đã biên dịch và chạy thành công với `-Xverify:all`, exit code 0. Kết quả trên cho thấy **đúng hai trường hợp schema change bị VM từ chối**, nhưng body-only wrapper call được chấp nhận.

| Dòng | Bằng chứng |
|---|---|
| `before=35` | V1 đang chạy, object có factor=7 |
| `added-method:rejected` | V2 thêm method trong chính class đã nạp bị từ chối |
| `after-rejected=35` | Lần cập nhật lỗi không ghi đè V1 |
| `native-wrap:rejected` | Native-to-Java wrapper sau load vi phạm cấu trúc |
| `body-only:accepted` | Thay method body, giữ schema được chấp nhận |
| `wrapper:before input=5` | Helper class ngoài target được gọi |
| `wrapper:after result=35` | Helper gọi đường business cũ và lấy đúng kết quả |
| `after-valid=35` | Invocation mới trên object cũ dùng body đã sửa |

### 8.1. Dùng javap xem schema

~~~bash
javap -p -s -classpath out/base demo.Target
javap -p -s -classpath out/bad demo.Target
javap -p -s -classpath out/good demo.Target
javap -p -s -classpath out/base demo.NativeTarget
javap -p -s -classpath out/nativebad demo.NativeTarget
~~~

Tìm `wrapper(int)` chỉ có trong V2 bad; bản V3 good không có method mới. So sánh `native ping` và Java `ping`/`native wrappedPing` ở hai bản native. Nếu muốn xem method bodies, dùng `javap -c -p`.

**Ghi nhớ:** Compiling V2/V3 tạo classfile hợp lệ **khi load lần đầu** không có nghĩa có thể **redefine class đã nạp** bằng bytes đó. Đây là hai giai đoạn với ràng buộc khác nhau.

## 9. JVMTI NativeMethodBind là một cách khác

JVM TI có event **`NativeMethodBind`** khi VM liên kết Java native method tới địa chỉ C/C++ implementation — chẳng hạn ở lần đầu gọi native hoặc khi JNI `RegisterNatives`. Native agent có thể chỉ định **một function address khác** làm binding thay thế.

Chữ ký callback (minh họa API C):

~~~c
void JNICALL NativeMethodBind(
    jvmtiEnv* jvmti_env,
    JNIEnv* jni_env,
    jthread thread,
    jmethodID method,
    void* address,
    void** new_address_ptr);
~~~

Đây **không phải native agent hoàn chỉnh**. Để chạy cần C/C++ library, JVMTI env, capability, callback registration và xử lý ABI/JNI signature.

Nó có thể hỗ trợ trường hợp class native target **đã được load** mà không thêm Java method mới:

- Event gắn với thời điểm **binding native function**, không phải thay class method schema.
- Nếu agent sở hữu capability **`can_generate_native_method_bind_events`** và bật event kịp lúc, có thể thay `*new_address_ptr` bằng địa chỉ native proxy.
- Proxy native phải đúng JNI calling convention, receiver `jobject/jclass`, parameter types, return type và exception behavior.
- Nếu binding **đã diễn ra trước khi agent attach/bật event**, event không tự phát lại cho lần bind cũ.
- Redirection của native function pointer có điều kiện riêng; không phải một cú pháp Java wrapper tùy ý.
- Việc thay địa chỉ nhầm hoặc gọi JNI sai có thể gây crash JVM, nên cần native-level testing kỹ lưỡng.

**Không nhầm hai cơ chế**:

| Cơ chế | Can thiệp vào đâu? | Có tạo Java wrapper mới không? |
|---|---|---|
| `setNativeMethodPrefix` + load-time transformer | Classfile trước define và native name-resolution fallback | Có thể, nếu transformer sinh classfile |
| JVM TI `NativeMethodBind` | Native implementation function pointer khi bind | Không |
| `redefineClasses` sửa body Java đã có | Bytecode của Java method trong loaded class | Không cần thêm method |
| Java caller instrumentation | Bytecode ở vị trí gọi native method | Không cần sửa native target |

## 10. Hệ quả khi attach muộn

Một agent được attach sau khi ứng dụng đã chạy lâu có thể phát hiện `NativeTarget` đã load. Những điều cần kiểm tra theo thứ tự:

1. JVM có cho attach/dynamic agent loading không? Các JDK mới có flags/warnings/policy liên quan.
2. Đúng class identity/class loader nào đang chứa target? Hai loaders có thể define class cùng tên.
3. Class đã **load** chưa, và native method đã **bind** tới implementation chưa? Đây là hai mốc khác nhau.
4. Có Java call-site vẫn có thể transform không?
5. JVM có hỗ trợ `isRedefineClassesSupported`, `isRetransformClassesSupported` và `isModifiableClass` cho class liên quan không?
6. Có cần **thêm wrapper method** trong target? Nếu có thì thông thường không dùng redefine/retransform lúc này.
7. Có thể dùng helper ngoài class và thay **body Java đã tồn tại** không?
8. Nếu cần quan sát native binding, agent JVM TI có `NativeMethodBind` capability và bắt kịp thời điểm bind không?
9. Nếu không, có thể chuyển logic sang **startup/pre-load** hoặc build-time weaving không?

Tránh logic sai: “`setNativeMethodPrefix` được hỗ trợ, vậy có thể chèn Java method mới vào bất kỳ class đã load nào.” Capability prefix chỉ điều khiển name resolution, không sửa điều kiện cho phép biến đổi schema.

### 10.1. getAllLoadedClasses không phải lock

`Instrumentation.getAllLoadedClasses()` cho biết tập class đang được JVM load tại thời điểm đọc. Việc bạn chưa thấy class trong list **không khóa các thread khác khỏi load nó ngay sau đó**. Nếu cần bảo đảm transformer vào trước lần define, thiết kế agent/startup/classloading order phù hợp, không dựa vào một check rồi sleep.

## 11. Điều kiện bổ sung với helper/wrapper ngoài class

Mẫu body-only `compute` trong lab thành công vì cả `Target` và `Wrapper` ở cùng package và cùng application classloader. Trong hệ thống thật, có thể khác:

- App có custom classloader hoặc module layers khác; helper được nạp bởi agent/system loader chưa chắc target thấy được.
- Nếu chèn calls vào named module, cần quan hệ readability/export phù hợp; xem `Instrumentation.redefineModule` khi cần mở rộng module graph, nhưng không cấp quyền thừa.
- Agent nên tránh instrument chính helper để khỏi recursion.
- Helper có thể phải giữ `ThreadLocal`/tracing context, nhưng phải dọn state tránh leak.
- Nếu helper ném exception, nó có thể làm business method vốn chạy đúng trở nên lỗi.
- Một wrapper dùng I/O synchronous tại hot path có thể làm tăng latency đáng kể.
- JNI proxy còn phải bảo toàn pending native exception, local/global refs và ABI.
- Nếu wrapper muốn bắt cả success và failure, cần `try/finally` và giữ nguyên return value/exception semantics.

Ví dụ structure của Java helper (chỉ minh họa, cần lớp `Probe`):

~~~java
static int around(Target target, int value) {
    Probe.enter();
    try {
        return target.raw(value);
    } finally {
        Probe.exit();
    }
}
~~~

`Probe.exit()` cũng phải an toàn, tránh che lỗi gốc bằng một exception mới.

### 11.1. Tránh recursion

Nếu `Target.compute` mới đã gọi `Wrapper.around`, còn `Wrapper.around` lại gọi `target.compute`, chu trình sẽ tiếp tục vô hạn cho tới khi `StackOverflowError`. Lab dùng `target.raw` vì đây là **đường thực thi đã tồn tại**, không gọi lại entry method đã bị wrap.

Nếu không có method gốc có thể delegate an toàn, chèn probe trực tiếp vào **body Java method hiện hữu**, bảo toàn instructions gốc, thay vì tạo helper gọi lại chính entry method.

## 12. Lưu ý về JVM TI events, tracing và native method lifecycle

- `MethodEntry`/`MethodExit` của JVM TI có thể hỗ trợ theo dõi method-level events nếu VM có capabilities phù hợp, nhưng overhead khác hoàn toàn bytecode probe và phải cấu hình đúng sự kiện/threads; không tự giả định mọi native behavior sẽ được nhìn thấy giống Java bytecode.
- `NativeMethodBind` quan sát **binding time**, không mặc nhiên ghi một event cho **mỗi invocation**. Một callback bind thành công không phải method invocation tracing đầy đủ.
- JNI native functions có thể giữ locks, global references, pinned arrays hoặc native memory; Java wrapper không tự quản lý đúng tài nguyên đó.
- Native method có thể thực hiện callbacks vào Java hoặc tạo thread. Timing wrapper ở Java-level đo khoảng thời gian từ caller tới native completion ở thread đó, không đồng nghĩa độ trễ của mọi asynchronous task do native khởi phát.
- Stack frames đã chạy từ trước một lần redefinition/retransformation vẫn có thể tiếp tục bytecode cũ; probe mới ở caller Java không retroactively xuất hiện trong một active frame cũ.
- Cần test overhead và JNI error propagation khi bật instrument trên production traffic.

## 13. Những sai lầm phổ biến

**Sai lầm 1 — “Native method có thể chèn vào body như method Java.”** Không: native không có Java `Code` attribute.

**Sai lầm 2 — “Tạo Java wrapper tại bất kỳ lúc nào cũng được.”** Không: nếu đòi thêm method/đổi native modifier trong class đã load, sẽ gặp schema limits.

**Sai lầm 3 — “Bật `Can-Redefine-Classes` thì được thêm field/method.”** Không: capability chỉ cấp phép operation, không nới mọi thay đổi cấu trúc.

**Sai lầm 4 — “setNativeMethodPrefix tự đổi bytecode.”** Không: transformer vẫn phải sinh classfile và JNI linking phải hợp lệ.

**Sai lầm 5 — “Prefix đảm bảo native library tồn tại.”** Không: JNI implementation vẫn phải nạp/liên kết; có thể gặp `UnsatisfiedLinkError`.

**Sai lầm 6 — “External helper bọc được cả native method không có body.”** Không trực tiếp; helper phải nằm ở **call-site**, hoặc method Java khác có body, hoặc dùng native-level hook.

**Sai lầm 7 — “Classfile V2 biên dịch thành công thì redefine chắc chắn được.”** Sai: compilation chỉ xác nhận đây là classfile có thể được định nghĩa từ đầu, không xác nhận có thể thay schema của class đã nạp.

**Sai lầm 8 — “NativeMethodBind là sự kiện cho mỗi lời gọi native.”** Không: đó là event **binding**, không phải entry/exit của mọi invocation.

**Sai lầm 9 — “Attach sau binding thì NativeMethodBind tự phát lại.”** Không. Phải xem lifecycle binding và các cơ chế registration phù hợp.

**Sai lầm 10 — “Thêm helper class ngoài luôn an toàn.”** Chưa chắc: loader/module, recursion, performance, GC, JNI state và exception handling cần được kiểm chứng.

## 14. Bài tập thực hành

### A. Dự đoán output trước khi chạy

Với `Main` ở mục 7, dự đoán kết quả `Target.compute(5)` trước và sau hai lần redefine. Giải thích tại sao `after-rejected` vẫn là 35 nhưng sau lần body-only cập nhật có thêm log wrapper.

**Đáp án:** V2 schema change bị từ chối, nên V1 vẫn được dùng. V3 không thêm methods/fields, chỉ thay body `compute` để gọi helper; kết quả business vẫn 35.

### B. Tự kiểm tra schema bằng javap

Dùng `javap -p -s` so sánh V1, V2 và V3 của Target. Hãy chỉ ra method **`wrapper(int)`** có trong V2 nhưng không ở V1/V3. Dùng `javap -c -p` để tìm lời gọi `Wrapper.around` trong body V3.

### C. Thử lỗi khi native method không có library

Trong môi trường test cô lập, thử gọi `new NativeTarget().ping(1)` khi không có JNI implementation. Quan sát `UnsatisfiedLinkError`. Vì sao nó là **lỗi native resolution**, không phải bằng chứng của schema limit?

### D. Chọn cách instrument khi target đã load

Một agent attach muộn muốn đo tất cả lời gọi `foo`. Hãy so sánh ba giải pháp: instrument các Java call-sites; JVM TI `NativeMethodBind` nếu còn điều kiện binding; restart JVM với load-time wrapper. Nêu độ phủ, quyền/capability và giới hạn của từng cách.

### E. Phân biệt native prefix với JNI symbol

Giả sử output class có `$trace$foo` native nhưng shared library chỉ có JNI implementation của `foo`. Prefix phải được đăng ký với transformer nào? Nếu chưa register prefix, điều gì có thể xảy ra khi JVM resolve native call?

**Đáp án:** đăng ký prefix cho transformer đã tạo wrapper; nếu thiếu, lookup của tên có prefix có thể thất bại và gây `UnsatisfiedLinkError`.

### F. Tìm recursion trong external helper

Đổi `Wrapper.around` gọi `target.compute` thay vì `target.raw`. Phân tích call graph và giải thích nguy cơ `StackOverflowError`. Sau đó khôi phục bản đúng.

### G. Thêm field để lưu probe state

Thêm `long startTime` chỉ ở Target V3; compile thành công rồi thử redefine. Vì sao việc muốn lưu state tiện lợi lại bị schema restriction? Hãy đề xuất state ngoài class hoặc đo bằng local variables trong body đã có (với bytecode/frame hợp lệ).

### Tự kiểm tra nhanh

1. **Vì sao phải có wrapper để chèn Java probe quanh native method?** — Native method không có Java bytecode.
2. **Wrapper cần thời điểm tốt nhất để thay method table?** — Lúc class chưa được define lần đầu.
3. **Sau class load, thêm method wrapper bằng redefine được bảo đảm không?** — Không.
4. **Đổi `ACC_NATIVE` của method đã load có phải body-only change không?** — Không.
5. **`Can-Set-Native-Method-Prefix` có thay thế `Can-Redefine-Classes` không?** — Không.
6. **External helper pattern kiểm thử thành công trong lab áp dụng cho loại method nào?** — Java method có body và schema giữ nguyên.
7. **`NativeMethodBind` thay đổi method list của Java class không?** — Không, nó can thiệp native function binding.
8. **Nếu chưa có JNI library, chỉ gọi prefix có tự sửa lỗi không?** — Không.
9. **Khi redefinition ném exception, có class nào trong tập đã thay thành công không?** — Theo Java Instrumentation, không.
10. **Cách kiểm tra schema khác nhau?** — `javap -p -s`, đối chiếu field/method descriptors và modifiers.

## 15. Checklist dành cho Java agent / native agent

### Trước khi triển khai

- [ ] Xác định mục tiêu có Java bytecode hay là native declaration.
- [ ] Kiểm tra class đã loaded chưa, native method đã bound chưa.
- [ ] Xác nhận định dùng pre-load transformer hay late redefine/retransform.
- [ ] So sánh schema trước/sau: methods, fields, descriptors, native flags.
- [ ] Nếu dùng prefix, xác minh manifest `Can-Set-Native-Method-Prefix: true` và `isNativeMethodPrefixSupported`.
- [ ] Nếu dùng redefine, xác minh `Can-Redefine-Classes` và `isModifiableClass`; đừng lẫn capability với schema support.
- [ ] Nếu dùng native binding event, xác minh JVM TI capability và callback registration.
- [ ] Xác định JNI implementation có đúng symbol/signature/lifecycle.
- [ ] Chuẩn bị fallback khi target đã load và không thể thêm wrapper.

### Trong khi instrument

- [ ] Filter class theo binary name **và class loader/module identity**.
- [ ] Sinh class bytes hợp lệ, không mutate buffer input.
- [ ] Không thêm method/field vào target đã load khi VM không hỗ trợ.
- [ ] Không gọi `setNativeMethodPrefix` trên transformer chưa register.
- [ ] Không in log/perform blocking I/O với tần suất cao ở probe.
- [ ] Tránh instrument chính class helper và recursion.
- [ ] Bảo toàn try/finally/exception flow, return type và stack frames.
- [ ] Tránh dùng JNI proxy function sai ABI gây crash VM.

### Sau khi instrument

- [ ] Dùng `javap -p -s` và `javap -c -p` để xác minh schema/bytecode.
- [ ] Test với `-Xverify:all` trên runtime đích.
- [ ] Kiểm thử JNI binding thật nếu native wrapper được deploy.
- [ ] Phân biệt `UnsupportedOperationException` với `UnsatisfiedLinkError`/`VerifyError`.
- [ ] Kiểm tra helper class loader/module visibility.
- [ ] Xác nhận probe giữ đúng giá trị trả về và exception behavior.
- [ ] Đo overhead, GC, memory leaks, JNI references và latency.
- [ ] Ghi rõ độ phủ call-sites/những native invocations không được quan sát.
- [ ] Chuẩn bị rollback/restart có kiểm soát.

## 16. Tổng kết và nguồn chuẩn

**Tại sao thêm wrapper?** Vì native method không chứa Java bytecode; Java wrapper cung cấp một method body để thêm timing/trace rồi chuyển lời gọi tới implementation native qua prefixed method. **Tại sao class đã nạp là vấn đề?** Vì thêm wrapper trong chính class thường thêm method/đổi modifier `native`, trong khi JVM TI `RedefineClasses` và `RetransformClasses` Java 17 không hỗ trợ các thay đổi cấu trúc này.

Khi class đã load, hãy chọn đúng **điểm can thiệp còn hợp lệ**: body Java method đã có, Java call-site, helper class riêng, JVM TI NativeMethodBind nếu phù hợp, hoặc thiết kế load-time wrapper cho lần khởi động tiếp theo. **setNativeMethodPrefix không tự vượt qua schema limits.**

Tài liệu chuẩn:

- [Java SE 17 — Instrumentation.setNativeMethodPrefix](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#setNativeMethodPrefix(java.lang.instrument.ClassFileTransformer,java.lang.String)): native wrapper, prefix-based JNI resolution, capability và transformer registration.
- [Java SE 17 — Instrumentation.redefineClasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#redefineClasses(java.lang.instrument.ClassDefinition...)): class replacement, lỗi và hạn chế.
- [Java SE 17 — java.lang.instrument](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): Java agent và manifest capabilities.
- [JVM TI Java 17 — RedefineClasses](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#RedefineClasses): schema restrictions và error codes.
- [JVM TI Java 17 — RetransformClasses](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#RetransformClasses): live class transform limits.
- [JVM TI Java 17 — SetNativeMethodPrefix](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#SetNativeMethodPrefix): hỗ trợ prefixed native binding.
- [JVM TI Java 17 — NativeMethodBind](https://docs.oracle.com/en/java/javase/17/docs/specs/jvmti.html#NativeMethodBind): native bind event, địa chỉ proxy và capability.
- [JNI Specification — Resolving Native Method Names](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html#resolving-native-method-names): quy tắc tìm JNI functions.
