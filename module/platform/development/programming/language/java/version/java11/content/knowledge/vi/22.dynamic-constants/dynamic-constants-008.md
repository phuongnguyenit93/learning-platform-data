# BootstrapMethodError và chẩn đoán lỗi phân giải hằng số động trong Java 11

## Mục tiêu

Từ **Java 11**, JVM hỗ trợ **dynamic class-file constants** (*condy*) theo **JEP 309**. Khác với `CONSTANT_String` chứa literal, `CONSTANT_Dynamic` chứa một **symbolic reference** liên quan tới bootstrap method (BSM). Khi JVM cần giá trị tại lệnh `ldc`, nó resolve BSM cùng arguments, gọi BSM rồi kiểm giá trị trả về. Nếu quá trình đó không đáp ứng hợp đồng, một trong những lỗi quan trọng nhất là **`java.lang.BootstrapMethodError`**.

Bài học tập trung vào **BootstrapMethodError và chẩn đoán lỗi phân giải**, không phải chỉ mô tả tên exception. Bạn sẽ:

1. Nhận diện `CONSTANT_Dynamic` tag **17**, classfile **major version 55** (Java 11), `BootstrapMethods`, `CONSTANT_MethodHandle` và `ldc/ldc_w/ldc2_w`.
2. Phân biệt **load/verify classfile**, **resolve symbolic reference**, **invoke bootstrap**, **convert result**, **cache success/failure**.
3. Hiểu BSM cho condy thường nhận **`MethodHandles.Lookup`, `String`, `Class<?>`** và các static args nếu được khai báo.
4. Phân biệt lỗi do **bootstrap signature**, do exception trong BSM, do return type không phù hợp, do `null` primitive, và do lỗi linkage xảy ra *trước* invocation.
5. Biết **`BootstrapMethodError extends LinkageError`**, không thuộc nhánh `Exception`; học cách quan sát `getCause()` và exception wrappers khi dùng reflection.
6. Hiểu vì sao failed dynamic constant resolution không tự «retry» khi thay đổi cấu hình; đồng thời biết JVM có thể **invoke BSM đồng thời** trong concurrent first-resolution.
7. Chạy một chương trình Java 11 **không có thư viện ngoài**, tự ghi các classfile condy thật và kiểm thử JVM với nhiều tình huống lỗi/success.
8. Dùng `javap -v -c` và checklist để chẩn đoán lỗi từ bytecode generator, shading, classloader, module, dependency version.

Theo Special Note, bài chỉ dùng kiến thức còn được áp dụng trong JDK hiện đại. Không dùng API nội bộ `jdk.internal.*` hay cách tạo synthetic lỗi thời. Những behavior thuộc JVM Specification và Javadoc Java 11 vẫn có ý nghĩa trên các JDK mới.

## 1. Mô hình CONSTANT_Dynamic

### 1.1. Cấu trúc classfile

Theo JVMS `4.4.10, một entry có dạng:

~~~text
CONSTANT_Dynamic_info {
    u1 tag;                         // 17
    u2 bootstrap_method_attr_index; // trỏ entry trong BootstrapMethods
    u2 name_and_type_index;         // tên + field descriptor
}
~~~

`CONSTANT_Dynamic` không chứa giá trị tính sẵn mà chứa **chỉ dẫn để tính giá trị**. `name_and_type_index` tham chiếu `CONSTANT_NameAndType` có unqualified name và **field descriptor**, ví dụ `Ljava/lang/String;` hoặc `I`. `BootstrapMethods` (JVMS `4.7.23) chỉ ra một `CONSTANT_MethodHandle` của BSM cùng zero hoặc nhiều static arguments.

~~~text
GeneratedGood.class (major 55)
  constant pool:
    ... Methodref bootstrap(...)
    ... MethodHandle REF_invokeStatic ...
    ... NameAndType good:Ljava/lang/String;
    ... Dynamic bootstrap[0], good:Ljava/lang/String;

  BootstrapMethods:
    [0] bootstrap MethodHandle, static arguments=[]

  static String value():
    ldc_w #Dynamic
    areturn
~~~

Sơ đồ trên không phải output `javap` nguyên văn; constant pool indexes được JVM/compiler gán và thay đổi theo classfile. Khi `value()` chạy, `ldc_w` tham chiếu dynamic entry, yêu cầu giá trị đã resolve hoặc gây lỗi tại điểm dùng.

**Classfile tag 17 chỉ có từ Java 11 / major version 55 trở đi**. Một JVM Java 8 không có hỗ trợ hợp lệ cho kiểu entry này.

### 1.2. Condy không phải invokedynamic

| | Condy | Invokedynamic |
| --- | --- | --- |
| Constant-pool tag | `CONSTANT_Dynamic` = **17** | `CONSTANT_InvokeDynamic` = **18** |
| Instruction | `ldc` / `ldc_w` / `ldc2_w` | `invokedynamic` |
| Descriptor được dùng | Field descriptor | Method descriptor |
| Third bootstrap arg | `Class<?>` | `MethodType` |
| Bootstrap result | Một **constant value** đúng declared type | `CallSite` có target type phù hợp |
| Có thể ném BME? | Có | Có |

`BootstrapMethodError` đã có trong Java từ 1.7 để phục vụ invokedynamic. Nhưng **condy là từ Java 11**. Khi đọc stack trace, cần xác định call site là `ldc_w Dynamic` hay `invokedynamic` trước khi quyết định loại lỗi.

### 1.3. Các pha JVM

~~~text
class loading / verification
    |
    +-- bad classfile -> ClassFormatError / VerifyError
    |
    v
first relevant use of a CONSTANT_Dynamic
    |
    +-- resolve BSM MethodHandle
    +-- resolve field descriptor type
    +-- resolve static bootstrap arguments
    +-- invoke bootstrap
    +-- convert result to descriptor type
    |
    +-- success: cache constant
    +-- failure: cache resolution failure
~~~

**Load class thành công không chứng minh dynamic constant có thể resolve.** Error có thể chỉ xuất hiện tại first relevant `ldc`. Ngược lại, lỗi định dạng bytecode có thể xuất hiện trước BSM. Không nhầm resolution với Java static field initializer `<clinit>` hoặc `ExceptionInInitializerError`.

## 2. Hợp đồng bootstrap method

### 2.1. Signature cơ bản

~~~java
public static Object bootstrap(MethodHandles.Lookup lookup,
                               String name, Class<?> type) {
    return "ready";
}
~~~

Đây là **đoạn minh họa**, cần import `java.lang.invoke.MethodHandles`. JVM chuẩn bị:

~~~text
arg[0] = Lookup cho class CHỨA symbolic reference condy
arg[1] = String tên hằng số
arg[2] = Class kiểu hằng số theo field descriptor
arg[3..] = static args, nếu BootstrapMethods khai báo
~~~

`lookup.lookupClass()` là class cần resolve constant, **không nhất thiết là class sở hữu bootstrap method**. Khi BSM dùng MethodHandles hoặc reflection, cần kiểm quyền classloader/module/lookup thực tế, không tự cho rằng nó có mọi quyền của helper class.

### 2.2. Tham số đầu bắt buộc là Lookup

Đối với **CONSTANT_Dynamic**, **JVMS 11 `5.4.3.6 yêu cầu tham số đầu tiên trong descriptor BSM phải đúng là `MethodHandles.Lookup`**. Nếu descriptor bắt đầu bằng `String`/`Object` thay vì `Lookup`, resolution thất bại với **`BootstrapMethodError`** trước khi BSM được gọi.

Những tham số tiếp theo có thể được áp dụng các chuyển đổi của `MethodHandle.invokeWithArguments` và handling varargs hợp lệ. Dạng `(Lookup, String, Class<?>)` cộng static args tường minh là cách dễ hiểu, dễ kiểm thử nhất.

### 2.3. Static args có thể fail trước bootstrap ngoài

~~~text
Dynamic OUTER
  └─ static argument = Dynamic INNER
         ├─ INNER resolves  -> OUTER BSM được invoke
         └─ INNER fails     -> OUTER BSM có thể CHƯA được gọi
~~~

Nếu static arg reference một type hoặc một condy bị lỗi, JVM có thể dừng ở bước chuẩn bị args. **Không đánh đồng một lỗi BME của OUTER với việc body của OUTER BSM nhất thiết đã chạy.**

Chu kỳ static args như A → B → A không hợp lệ. JVMS quy định thất bại với `StackOverflowError` trong trường hợp condy phụ thuộc chính mình theo cách đó; bytecode generator nên ngăn cycle thay vì tạo một vòng recursion vô hạn.

## 3. BootstrapMethodError và các nhóm lỗi

### 3.1. Cây kế thừa

~~~text
java.lang.Throwable
  java.lang.Error
    java.lang.LinkageError
      java.lang.BootstrapMethodError
~~~

`BootstrapMethodError` là **lỗi linkage**, không phải checked `Exception` hay `RuntimeException`. `catch (Exception)` không bắt được. Trong hệ thống, lỗi này thường cần sửa classfile/BSM/library/loader hoặc deploy, không phải một lần retry HTTP thông thường.

### 3.2. Bảng phân loại lỗi

| Nguyên nhân | Pha | Kết quả theo JVMS |
| --- | --- | --- |
| Tham số đầu của BSM condy không phải `Lookup` | Resolve bootstrap handle descriptor | **`BootstrapMethodError`** |
| BSM ném `IllegalStateException` | Invocation | **`BootstrapMethodError` với `getCause()` là exception gốc** |
| BSM ném `AssertionError` | Invocation | **`AssertionError` được propagate trực tiếp**, không tự bọc vào BME |
| BSM trả `Integer` cho descriptor `String` | Conversion | **`BootstrapMethodError`**, không auto `toString()` |
| BSM trả `null` cho primitive descriptor `I` | Conversion | **`BootstrapMethodError`** vì không unbox được |
| BSM trả `null` cho reference descriptor `Ljava/lang/String;` | Conversion | **Hợp lệ** |
| Bootstrap target method thiếu hoặc đổi signature | Resolve MethodHandle | `NoSuchMethodError` / LinkageError phù hợp |
| Bootstrap owner thiếu khỏi runtime | Resolve method/class | `NoClassDefFoundError` / LinkageError |
| Caller không được quyền truy cập bootstrap | Access check | `IllegalAccessError` / LinkageError phù hợp |
| Classfile version/tag/attribute structure sai | Load/verify | `ClassFormatError` / `VerifyError` trước BSM |
| Nested dynamic argument sai | Resolve static args | Propagate lỗi của static argument; outer BSM có thể chưa chạy |
| Cyclic condy static args | Resolve args | `StackOverflowError` theo JVMS |

**Không phải mọi lỗi có chữ «bootstrap» đều là BME.** Có lỗi xuất hiện *trước* invocation, có lỗi *trong* BSM, và có lỗi *sau* invocation khi convert result.

### 3.3. Vì sao cần kiểm getCause()

Với non-Error exception từ BSM, trace thường có cấu trúc:

~~~text
java.lang.BootstrapMethodError: ...
    at GeneratedFail.value(...)
Caused by: java.lang.IllegalStateException: failure-marker
    at CondyResolutionDemo.bootstrap(...)
~~~

Đây là **sơ đồ**; thông điệp và frame formatting khác nhau giữa các phiên bản JVM. Từ BME bề mặt không thể tự xác định root cause. Hãy đi theo `Throwable.getCause()` để tìm `IllegalStateException`, classloader mismatch, argument type mismatch hoặc lỗi dependency.

Nếu dùng `Method.invoke` để gọi generated method, một wrapper **`InvocationTargetException`** có thể được thêm bởi **reflection API**, không phải bởi quá trình condy linkage. Unwrap nó trước khi nhìn BME.

## 4. Resolution caching và concurrency

### 4.1. Thành công được cache

Theo JVMS `5.4.3, khi một dynamic constant symbolic reference trong runtime constant pool đã resolve thành công, lần dùng tiếp theo của **cùng reference** sử dụng giá trị đã tính. Bootstrap không được chạy lại trong các lần dùng tuần tự chỉ để tính lại cùng một giá trị.

Vì vậy **condy không phải factory được invoke mỗi request**. Nếu bootstrap lấy config tại lúc resolution, thay đổi config về sau không tự cập nhật constant đã resolve.

### 4.2. Thất bại cũng được ghi nhớ

Một lần resolution fail làm những lần dùng tiếp theo vẫn fail; **bootstrap không tự chạy lại** cho chính symbolic reference đó.

~~~text
t0: ready = false
    GeneratedRecoverA.value()  -> BSM throws
                                 JVM reports BME
t1: ready = true
    GeneratedRecoverA.value()  -> still fails (not retried)
t2: GeneratedRecoverB.value()  -> different runtime constant pool
                                 BSM can run afresh and succeed
~~~

A và B là **hai class riêng**, mỗi class có runtime constant pool riêng. Chúng có thể cùng dùng bootstrap method và cùng constant name nhưng không chia sẻ duy nhất một cache condy toàn JVM.

**Không nên dùng object identity `firstError == repeatedError` làm phép kiểm duy nhất**, đặc biệt qua reflection và các wrapper. Trong ví dụ kiểm tra **BSM invocation count** ở các đường lỗi có BME, cùng exception type/cause khi đặc tả yêu cầu.

### 4.3. Concurrent first-resolution là trường hợp quan trọng

JVMS `5.4.3.6 cho phép nhiều threads cùng cố resolve một symbolic reference **đồng thời invoke bootstrap method handle**. JVM chọn **một** kết quả để cài đặt, kết quả những invocation khác không được dùng.

Do đó **không thể khẳng định BSM chỉ được gọi đúng một lần trong mọi race đa luồng**, dù các lần dùng **sau resolution** không yêu cầu chạy lại. Bootstrap nên idempotent, thread-safe và không thực hiện side effects nghiệp vụ có kỳ vọng exactly-once như gửi email, thanh toán, hay sửa dữ liệu khó rollback.

## 5. Chương trình chạy thật trên JVM: tạo condy classfile Java 11

Để chứng minh **một BME thực từ `ldc_w CONSTANT_Dynamic`**, không phải `throw new BootstrapMethodError()` giả lập, chương trình tự tạo classfile version 55 bằng **`ByteArrayOutputStream`, `DataOutputStream`** rồi `ClassLoader.defineClass`.

Ví dụ sử dụng các constant-pool tags `Utf8 (1)`, `Class (7)`, `Methodref (10)`, `NameAndType (12)`, `MethodHandle (15)`, `Dynamic (17)`. Một `BootstrapMethods` attribute liên kết handle với entry Dynamic. Code `value()` gọi `ldc_w` và `areturn/ireturn`, giúp JVM thực hiện resolution đúng quy tắc.

**Đây là trình tạo classfile tối thiểu để kiểm thử**, không phải một bytecode framework production. Không có thư viện ngoài hoặc `--add-exports`.

### 5.1. File CondyResolutionDemo.java

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationTargetException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public final class CondyResolutionDemo {
    private static final ConcurrentHashMap<String, AtomicInteger> CALLS =
            new ConcurrentHashMap<>();
    private static volatile boolean repaired;

    public static Object bootstrap(MethodHandles.Lookup lookup,
                                   String name, Class<?> type) {
        CALLS.computeIfAbsent(name, n -> new AtomicInteger())
                .incrementAndGet();
        if ("good".equals(name)) return "resolved-good";
        if ("failure".equals(name))
            throw new IllegalStateException("failure-marker");
        if ("recover".equals(name)) {
            if (!repaired) throw new IllegalArgumentException("not-ready");
            return "recovered";
        }
        if ("wrongType".equals(name)) return Integer.valueOf(99);
        if ("nullInt".equals(name)) return null;
        if ("nullRef".equals(name)) return null;
        if ("fatal".equals(name)) throw new AssertionError("fatal-marker");
        throw new IllegalArgumentException("Unknown constant " + name);
    }

    public static Object badBootstrap(String notLookup,
                                      String name, Class<?> type) {
        CALLS.computeIfAbsent("badBootstrap", n -> new AtomicInteger())
                .incrementAndGet();
        return "never";
    }

    private static int count(String name) {
        AtomicInteger i = CALLS.get(name);
        return i == null ? 0 : i.get();
    }

    private static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    @FunctionalInterface
    interface Writer {
        void write(DataOutputStream output) throws IOException;
    }

    private static final class Pool {
        private final List<byte[]> entries = new ArrayList<>();

        int add(int tag, Writer writer) {
            ByteArrayOutputStream memory = new ByteArrayOutputStream();
            try {
                DataOutputStream out = new DataOutputStream(memory);
                out.writeByte(tag);
                writer.write(out);
                out.flush();
            } catch (IOException impossible) {
                throw new AssertionError(impossible);
            }
            entries.add(memory.toByteArray());
            return entries.size();
        }

        int utf8(String value) {
            return add(1, out -> out.writeUTF(value));
        }

        int type(String internalName) {
            int name = utf8(internalName);
            return add(7, out -> out.writeShort(name));
        }

        int nameAndType(String name, String descriptor) {
            int n = utf8(name);
            int d = utf8(descriptor);
            return add(12, out -> {
                out.writeShort(n);
                out.writeShort(d);
            });
        }

        int methodRef(String owner, String name, String descriptor) {
            int c = type(owner);
            int nt = nameAndType(name, descriptor);
            return add(10, out -> {
                out.writeShort(c);
                out.writeShort(nt);
            });
        }

        void write(DataOutputStream out) throws IOException {
            out.writeShort(entries.size() + 1);
            for (byte[] entry : entries) out.write(entry);
        }
    }

    private static byte[] generate(String binaryName, String constantName,
                                   String descriptor, boolean badSignature) {
        String owner = "CondyResolutionDemo";
        String signature =
                "(Ljava/lang/invoke/MethodHandles$Lookup;"
              + "Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/Object;";
        String invalidSignature =
                "(Ljava/lang/String;Ljava/lang/String;"
              + "Ljava/lang/Class;)Ljava/lang/Object;";
        Pool pool = new Pool();
        int thisClass = pool.type(binaryName);
        int objectClass = pool.type("java/lang/Object");
        int methodRef = pool.methodRef(owner,
                badSignature ? "badBootstrap" : "bootstrap",
                badSignature ? invalidSignature : signature);
        int handle = pool.add(15, out -> {
            out.writeByte(6);
            out.writeShort(methodRef);
        });
        int nameType = pool.nameAndType(constantName, descriptor);
        int dynamic = pool.add(17, out -> {
            out.writeShort(0);
            out.writeShort(nameType);
        });
        int valueName = pool.utf8("value");
        int valueDescriptor = pool.utf8("()" + descriptor);
        int codeName = pool.utf8("Code");
        int bootstrapName = pool.utf8("BootstrapMethods");

        ByteArrayOutputStream memory = new ByteArrayOutputStream();
        try {
            DataOutputStream out = new DataOutputStream(memory);
            out.writeInt(0xCAFEBABE);
            out.writeShort(0);
            out.writeShort(55);
            pool.write(out);
            out.writeShort(0x0021); // public super
            out.writeShort(thisClass);
            out.writeShort(objectClass);
            out.writeShort(0); // interfaces
            out.writeShort(0); // fields
            out.writeShort(1); // methods
            out.writeShort(0x0009); // public static
            out.writeShort(valueName);
            out.writeShort(valueDescriptor);
            out.writeShort(1); // one Code attribute
            out.writeShort(codeName);
            out.writeInt(16); // Code attribute length
            out.writeShort(1); // max_stack
            out.writeShort(0); // max_locals
            out.writeInt(4); // bytecode: ldc_w #dynamic; xreturn
            out.writeByte(0x13); // ldc_w
            out.writeShort(dynamic);
            out.writeByte("I".equals(descriptor) ? 0xAC : 0xB0);
            out.writeShort(0); // exception handlers
            out.writeShort(0); // nested Code attributes
            out.writeShort(1); // class attributes
            out.writeShort(bootstrapName);
            out.writeInt(6); // one bootstrap, zero static arguments
            out.writeShort(1);
            out.writeShort(handle);
            out.writeShort(0);
            out.flush();
        } catch (IOException impossible) {
            throw new AssertionError(impossible);
        }
        return memory.toByteArray();
    }

    static final class Isolated extends ClassLoader {
        Isolated() {
            super(CondyResolutionDemo.class.getClassLoader());
        }

        Class<?> add(String name, byte[] bytes) {
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    private static Object invoke(Class<?> clazz) throws Throwable {
        try {
            return clazz.getMethod("value").invoke(null);
        } catch (InvocationTargetException error) {
            throw error.getCause();
        }
    }

    private static <T extends Throwable> T expect(Class<T> expected,
                                                  Class<?> clazz)
            throws Throwable {
        Object unexpected;
        try {
            unexpected = invoke(clazz);
        } catch (Throwable error) {
            if (expected.isInstance(error)) return expected.cast(error);
            throw new AssertionError("Expected " + expected.getName()
                    + " but got " + error.getClass().getName(), error);
        }
        throw new AssertionError("Expected " + expected.getName()
                + " but method returned " + unexpected);
    }

    public static void main(String[] args) throws Throwable {
        Isolated loader = new Isolated();
        byte[] goodBytes = generate("GeneratedGood", "good",
                "Ljava/lang/String;", false);
        if (args.length == 1) {
            Files.write(Path.of(args[0], "GeneratedGood.class"), goodBytes);
        }
        Class<?> good = loader.add("GeneratedGood", goodBytes);
        check(count("good") == 0, "bootstrap should be deferred");
        System.out.println("PASS no bootstrap during class definition");

        check("resolved-good".equals(invoke(good)), "first resolved value");
        check("resolved-good".equals(invoke(good)), "cached value");
        check(count("good") == 1, "successful resolution cached");
        System.out.println("PASS successful condy cached");

        Class<?> fail = loader.add("GeneratedFail",
                generate("GeneratedFail", "failure",
                        "Ljava/lang/String;", false));
        BootstrapMethodError first = expect(BootstrapMethodError.class, fail);
        check(first.getCause() instanceof IllegalStateException,
                "original unchecked exception is cause");
        check("failure-marker".equals(first.getCause().getMessage()),
                "original exception message retained");
        expect(BootstrapMethodError.class, fail);
        check(count("failure") == 1,
                "failed resolution cached without bootstrap retry");
        System.out.println("PASS BootstrapMethodError cause and caching");

        Class<?> wrong = loader.add("GeneratedWrong",
                generate("GeneratedWrong", "wrongType",
                        "Ljava/lang/String;", false));
        expect(BootstrapMethodError.class, wrong);
        check(count("wrongType") == 1,
                "wrong return type was produced by bootstrap");
        System.out.println("PASS incompatible result type rejected");

        Class<?> noInt = loader.add("GeneratedNullInt",
                generate("GeneratedNullInt", "nullInt", "I", false));
        expect(BootstrapMethodError.class, noInt);
        check(count("nullInt") == 1, "primitive null was produced");
        System.out.println("PASS null primitive constant rejected");

        Class<?> nullRef = loader.add("GeneratedNullRef",
                generate("GeneratedNullRef", "nullRef",
                        "Ljava/lang/String;", false));
        check(invoke(nullRef) == null && count("nullRef") == 1,
                "null reference is valid for String descriptor");
        System.out.println("PASS null reference constant allowed");

        Class<?> bad = loader.add("GeneratedBadSignature",
                generate("GeneratedBadSignature", "badSignature",
                        "Ljava/lang/String;", true));
        expect(BootstrapMethodError.class, bad);
        check(count("badBootstrap") == 0,
                "invalid first parameter rejected before invocation");
        System.out.println("PASS invalid bootstrap signature rejected");

        Class<?> fatal = loader.add("GeneratedFatal",
                generate("GeneratedFatal", "fatal",
                        "Ljava/lang/String;", false));
        AssertionError original = expect(AssertionError.class, fatal);
        check("fatal-marker".equals(original.getMessage()),
                "Error class preserved");
        System.out.println("PASS direct Error propagation");

        Class<?> recoverA = loader.add("GeneratedRecoverA",
                generate("GeneratedRecoverA", "recover",
                        "Ljava/lang/String;", false));
        BootstrapMethodError before = expect(
                BootstrapMethodError.class, recoverA);
        check(before.getCause() instanceof IllegalArgumentException,
                "original recover failure");
        repaired = true;
        expect(BootstrapMethodError.class, recoverA);
        check(count("recover") == 1,
                "same constant pool entry stays failed");
        Class<?> recoverB = loader.add("GeneratedRecoverB",
                generate("GeneratedRecoverB", "recover",
                        "Ljava/lang/String;", false));
        check("recovered".equals(invoke(recoverB)),
                "independent class can resolve after repair");
        check(count("recover") == 2,
                "one attempt per independent constant pool entry");
        System.out.println("PASS independent runtime constant pools");

        System.out.println("ALL CONDY BOOTSTRAP TESTS PASSED");
    }
}
~~~

### 5.2. Lệnh biên dịch và stdout

Trong thư mục chứa `CondyResolutionDemo.java`:

~~~bash
javac --release 11 -encoding UTF-8 CondyResolutionDemo.java
java CondyResolutionDemo .
~~~

Tham số `.` khiến chương trình ghi thêm một `GeneratedGood.class` trong thư mục hiện hành để kiểm bằng `javap`. Nếu không muốn file phụ, chạy `java CondyResolutionDemo` không tham số.

**Stdout mong đợi khi mọi assertion đúng:**

~~~text
PASS no bootstrap during class definition
PASS successful condy cached
PASS BootstrapMethodError cause and caching
PASS incompatible result type rejected
PASS null primitive constant rejected
PASS null reference constant allowed
PASS invalid bootstrap signature rejected
PASS direct Error propagation
PASS independent runtime constant pools
ALL CONDY BOOTSTRAP TESTS PASSED
~~~

Giải thích:

- **Define không gọi BSM:** mới tạo class, counter `good` bằng 0; chỉ khi gọi `value` cần `ldc_w` mới bắt đầu resolution.
- **Success caching:** hai lần dùng cùng reference chỉ có một invocation BSM trong test tuần tự.
- **Non-Error exception:** `IllegalStateException` trở thành cause của `BootstrapMethodError`; đọc `getCause()` thay vì đoán message.
- **Failure caching:** lần thứ hai vẫn báo lỗi mà counter BSM không tăng.
- **Type/null mismatch:** Integer không thể convert thành String, null không thể unbox thành int; null reference String được chấp nhận.
- **Wrong first argument:** BSM có tham số đầu là `String` bị từ chối trước invocation, counter BSM sai bằng 0.
- **Error propagation:** `AssertionError` được propagate trực tiếp; demo không dựa vào exception wrapper identity hoặc số lần retry Error qua provider.
- **Pool độc lập:** một constant entry đã fail không được retry, nhưng một generated class khác có pool riêng có thể resolve sau khi config được sửa.

### 5.3. Kiểm chứng bằng javap

Sau khi chạy `java CondyResolutionDemo .`:

~~~bash
javap -v -c -classpath . GeneratedGood
~~~

Các dấu mốc cần thấy:

~~~text
major version: 55

Constant pool:
  ... = MethodHandle   6:#... // REF_invokeStatic ...
  ... = Dynamic        #0:#... // good:Ljava/lang/String;

public static java.lang.String value();
  Code:
     0: ldc_w #...  // Dynamic #0:good:Ljava/lang/String;
     3: areturn

BootstrapMethods:
  0: #... REF_invokeStatic CondyResolutionDemo.bootstrap:...
~~~

Trích đoạn là **định hướng**, không phải output cố định. Tool có thể thay đổi constant-pool indexes và format. Nếu class bị `ClassFormatError`, kiểm version, constant pool references, `Code` attribute length, `BootstrapMethods` index và descriptor trước khi debug BSM.

## 6. Quy trình chẩn đoán lỗi phân giải trong dự án

### Bước 1. Thu toàn bộ Throwable chain

Nếu lỗi bị bọc bởi reflection, có thể unwrap:

~~~java
Throwable current = error;
while (current instanceof InvocationTargetException
        && current.getCause() != null) {
    current = current.getCause();
}
for (Throwable cause = current; cause != null;
        cause = cause.getCause()) {
    System.err.println(cause.getClass().getName()
            + " : " + cause.getMessage());
}
~~~

Đây là **đoạn minh họa**, giả định `error` và imports đã có. Không log password, secret, token hoặc dữ liệu nhạy cảm từ static args/BSM.

### Bước 2. Phân biệt Dynamic với InvokeDynamic

Mở đúng **artifact đã deploy** bằng `javap -v -c`, tìm `ldc_w Dynamic` hay `invokedynamic InvokeDynamic`. Trường hợp thứ hai đòi điều tra `CallSite`/`MethodType`, không áp các giả định return `Class<?>` của condy.

### Bước 3. So bootstrap handle và args

Kiểm method owner, method descriptor, reference kind, `Lookup` đầu, tên constant, field descriptor, static arguments và kiểu trả. Một BSM không có quyền truy cập hoặc method target không tồn tại có thể ném linkage error **trước khi body BSM chạy**.

### Bước 4. Kiểm môi trường runtime

Đối chiếu:
- JDK đang chạy và classfile major version.
- Dependency versions của bootstrap helper, shaded class names và generated bytecode.
- Defining classloader/module của owner/return types. Hai types **cùng binary name nhưng khác defining loader** không nhất thiết có cùng runtime identity.
- Module visibility, exports/opens đúng mục đích, không bật `--add-opens` bừa bãi.
- Constant pool entry và bootstrap static args có cycle hoặc thiếu dependency.

### Bước 5. Hiểu lỗi được ghi nhớ

Nếu cùng condy đã fail, những lần dùng sau vẫn fail, bootstrap không tự chạy lại. Đừng retry mù quáng. Sửa classfile, phiên bản thư viện, quyền truy cập hoặc khởi động lại lifecycle/triển khai phù hợp. Không tự tạo vô hạn classloaders để né cache.

### Bước 6. Test theo ba pha

| Pha | Lỗi có thể thấy | Hành động |
| --- | --- | --- |
| **Load/verify** | `ClassFormatError`, `VerifyError` | Sửa cấu trúc classfile/bytecode generator |
| **Resolve handle/args** | `NoSuchMethodError`, `NoClassDefFoundError`, `IllegalAccessError` | Sửa classpath/module, target descriptor, static args |
| **Invoke BSM** | BME có cause non-Error, Error direct | Sửa BSM logic; không nuốt lỗi |
| **Convert result** | BME do null primitive/wrong type | Khớp declared field descriptor |
| **Use after failure** | Cùng reference vẫn lỗi, BSM không retry | Sửa deployment/lifecycle, không thay flag rồi retry |

## 7. Lỗi thường gặp

1. Coi `BootstrapMethodError` là `Exception`: thực tế thuộc `Error → LinkageError`.
2. Coi mọi BME là invokedynamic: condy Java 11 cũng dùng BME.
3. Coi một entry `CONSTANT_Dynamic` là Java static field initializer: đó là runtime constant pool reference.
4. Bỏ qua cause của BME và chỉ dựa vào text của message.
5. Không unwrap `InvocationTargetException` của reflection khi kiểm test.
6. Dùng BSM có tham số đầu không phải `Lookup` cho condy.
7. BSM trả sai type rồi kỳ vọng JVM tự `toString()`/auto-parse JSON.
8. Coi null reference và null primitive đều thất bại.
9. Cho rằng BSM ném `Error` luôn được wrap thành BME.
10. Bỏ qua lỗi static argument và method-handle resolution trước BSM.
11. Coi class load thành công chứng minh BSM đã resolve.
12. Coi mỗi `ldc_w` lại gọi bootstrap.
13. Thay config rồi retry một failed constant và kỳ vọng nó được tính mới.
14. Đặt side effects không-idempotent trong BSM dù có thể concurrent first-resolution.
15. So identity của throwable wrapper như hợp đồng duy nhất.
16. Dùng bytecode tool cũ không hiểu tag17/classfile55.
17. Không kiểm artifact thực sau shading/relocation/agent instrumentation.
18. Không phân biệt linker errors với Java class initialization errors.
19. Bắt mọi `Throwable` rồi trả fallback như kết quả đã được JVM xác thực.
20. Tự dùng API nội bộ `jdk.internal.*` làm giải pháp mặc định thay vì `javap` và công cụ hỗ trợ public API.

## 8. FAQ và checklist

**1. Hằng số động có từ Java nào?** — Java 11, constant-pool tag 17, classfile 55.0.

**2. BSM condy nhận những gì?** — `Lookup`, `String name`, `Class<?> type`, rồi static args nếu có.

**3. Nếu BSM ném IllegalArgumentException?** — JVM báo `BootstrapMethodError` với exception gốc trong `getCause()` khi lỗi xảy ra trong invocation.

**4. Nếu BSM ném AssertionError?** — Error có thể được propagate trực tiếp, không bọc BME.

**5. Nếu BSM trả null cho String và int?** — Reference String có thể nhận null, primitive int không unbox được nên lỗi.

**6. Sau failed resolution, gọi lại có rerun BSM không?** — Không đối với cùng dynamic constant symbolic reference đã fail.

**7. Hai generated classes cùng dùng BSM có chung cache không?** — Không mặc định, vì có runtime constant pools khác nhau.

**8. Có thể có hai BSM invocation đồng thời cho một condy không?** — Có thể trong concurrent resolution; JVM chọn một kết quả, những kết quả khác bị bỏ qua.

**9. Nên nhìn gì ở `javap`?** — `Dynamic`, `BootstrapMethods`, method handle descriptor, `ldc/ldc_w/ldc2_w` và classfile major version.

**10. Điều gì quan trọng nhất khi xử lý BME?** — Phân loại đúng pha lỗi, đọc cause, kiểm bytecode+runtime, hiểu cache thất bại và sửa căn nguyên chứ không retry mù.

**Checklist:**

- [ ] Classfile ≥55, tag17, BootstrapMethods index và field descriptor hợp lệ.
- [ ] Bootstrap handle resolve được, descriptor có tham số đầu `Lookup`.
- [ ] Static arguments được resolve chính xác và không tạo chu kỳ.
- [ ] Return value phù hợp field descriptor; phân biệt null primitive/reference.
- [ ] Xử lý `BootstrapMethodError` khác với `Error` trực tiếp.
- [ ] Đọc `getCause()` và unwrap reflection wrappers.
- [ ] Đã hiểu caching success/failure và concurrent first-resolution.
- [ ] Biên dịch bằng `javac --release 11`, chạy đủ các case PASS.
- [ ] Có CI trên runtime Java 11 nếu sản phẩm thật yêu cầu baseline Java 11.

## 9. Tài liệu chính thức

1. [JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309)
2. [JVMS Java 11 `4.4.10 — CONSTANT_Dynamic_info](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.4.10)
3. [JVMS Java 11 `4.7.23 — BootstrapMethods attribute](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-4.html#jvms-4.7.23)
4. [JVMS Java 11 `5.4.3 — Resolution và cache](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3)
5. [JVMS Java 11 `5.4.3.6 — Bootstrap invocation và error handling](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-5.html#jvms-5.4.3.6)
6. [Java SE 11 — BootstrapMethodError](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/BootstrapMethodError.html)
7. [Java SE 11 — ConstantBootstraps](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html)
8. [Java SE 11 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
9. [Java SE 11 — MethodHandle.invokeWithArguments](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/invoke/MethodHandle.html)
10. [JVMS Java 11 `6.5 — ldc/ldc_w/ldc2_w](https://docs.oracle.com/javase/specs/jvms/se11/html/jvms-6.html#jvms-6.5.ldc)
11. [JVMS Java 26 `5.4.3.6 — đối chiếu quy định hiện hành](https://docs.oracle.com/en/java/javase/26/docs/specs/jvms/jvms-5.html#jvms-5.4.3.6)
