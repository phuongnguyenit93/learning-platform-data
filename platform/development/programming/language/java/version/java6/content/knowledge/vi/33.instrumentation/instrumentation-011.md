# Kiểm thử biến đổi, gỡ biến đổi và khả năng đọc class file

## 1. Mục tiêu: kiểm chứng bytecode đã biến đổi, biết cách hoàn tác và đọc đúng nguồn class file

Một Java agent có thể đăng ký `ClassFileTransformer` để quan sát/biến đổi class files khi chúng được nạp hoặc khi JVM thực hiện `retransformClasses`/`redefineClasses`. Trong một hệ thống thực tế, vấn đề không chỉ là “transformer có được gọi không?”, mà gồm ba câu hỏi độc lập:

1. **Biến đổi có tác dụng thật?** Code chạy trong JVM có khác theo kỳ vọng, và bản class file trả về có hợp lệ không?
2. **Gỡ biến đổi có nghĩa gì?** `removeTransformer` chỉ gỡ *đăng ký callback*, hay đồng thời khôi phục method đã bị biến đổi?
3. **Đọc class file từ đâu?** Bytecode trên classpath/JAR, bytes trong `classfileBuffer` và definition đang chạy trong JVM có thể khác nhau hay không?

`java.lang.instrument.Instrumentation`, `ClassFileTransformer` và `retransformClasses` là các Java Instrumentation APIs **vẫn hiện hành trong Java SE 26**; những khả năng retransform và đăng ký transformer có cờ `canRetransform` xuất hiện từ Java 6. Với JDK hiện đại, `java.lang.classfile.ClassFile` là **Class-File API chuẩn từ Java 24** để đọc/ghi/biến đổi mô hình class file. Vì vậy bài tách hai mức thực hành:

- **Java 17+:** startup `-javaagent`, transformer, gỡ transformer, retransform/redefine và đọc bytes qua resource stream; biên dịch/chạy trên JDK 17 trở lên.
- **Java 24+:** đọc `SampleTarget.class` bằng `java.lang.classfile.ClassFile.of().parse(bytes)` và kiểm tra class model; **không biên dịch phần này bằng `--release 17`**.

**Cảnh báo lớn nhất:** `Instrumentation.removeTransformer(transformer)` **không tự động hoàn tác các biến đổi đã áp dụng** cho classes đang loaded. Nó chỉ bỏ registration cho tương lai (và callbacks đang thực thi đồng thời vẫn có thể tới muộn). Muốn khôi phục definition đã load phải có chiến lược riêng: retransformation theo pipeline có thể khôi phục trong điều kiện được kiểm soát, hoặc redefinition bằng bytecode gốc đã lưu, cùng kiểm tra hiệu lực thật.

**Bài có ba chương trình Java 17+ và một chương trình Java 24+ đã được biên dịch, chạy và đối chiếu stdout trên OpenJDK 24.** Thao tác thay bytes bằng một chuỗi có cùng độ dài chỉ là **fixture thử nghiệm không thay đổi schema**, không phải phương pháp viết production bytecode transformer.

### Sau bài này, bạn sẽ biết

1. Vẽ lại luồng `ClassLoader` → transformer → verifier → installed class definition.
2. Sử dụng `premain` và manifest `Premain-Class` cùng `Can-Retransform-Classes`/`Can-Redefine-Classes`.
3. Phân biệt `addTransformer(transformer)` với `addTransformer(transformer, true)`.
4. Hiểu `transform` trả `null`, trả bản copy bytes đã sửa hoặc ném exception có những hậu quả gì.
5. Kiểm tra **class identity**, callback count, method behavior và đọc classfile bytes ban đầu.
6. Biết `removeTransformer` **không** rollback class đã được biến đổi.
7. Biết `retransformClasses` lấy lại definition theo quy tắc reapply transformers, không mặc nhiên đảm bảo quay về artifact ban đầu nếu còn lớp biến đổi khác.
8. Biết `redefineClasses` với `ClassDefinition` có thể cài classfile bytes rõ ràng, nhưng vẫn chịu JVM restrictions và các transformers còn đăng ký.
9. Hiểu dữ liệu từ `Class.getResourceAsStream` có thể là artifact gốc chứ không phải bytecode đang chạy, hoặc không tồn tại với custom class loaders.
10. Sử dụng `java.lang.classfile.ClassFile` (từ Java 24) để parse và kiểm tra class name, major version, methods.
11. Dùng `javap -v`, `-c`, `-p` để quan sát class file đã biên dịch mà không chạy agent.
12. Thiết kế regression tests, negative tests và rollout/rollback có kiểm soát; không biến đổi classes không thuộc phạm vi.

~~~text
             SampleTarget.java
                    |
                 javac
                    |
          SampleTarget.class (artifact)
                    |
               ClassLoader
                    |
          classfileBuffer (bytes)
                    |
             Transformer #1
                    |
            copies and patches
                    |
             Transformer #2...
                    |
              JVM verifier
                    |
       Installed definition in JVM
                    |
             SampleTarget.value()
                    |
               MODIFIED_VALUE

         removeTransformer(#1)
                    |
      Registration removed only
                    |
     Existing method still patched

       retransformClasses(Target)
                    |
       Initial bytes + remaining
           transformer semantics
                    |
       Original possible ONLY
       under controlled pipeline
~~~

## 2. Phân biệt ba nơi chứa “class bytes”

### 2.1. Artifact: class file trên đĩa hoặc trong JAR

Sau khi chạy `javac`, class file có binary format theo JVM Specification, bắt đầu bằng **magic bytes `CA FE BA BE`**, chứa version, constant pool, fields, methods và attributes. Ví dụ compile target Java 17 tạo **major version 61**.

~~~bash
javac -encoding UTF-8 --release 17 SampleTarget.java
javap -v -p SampleTarget
javap -c -p SampleTarget
~~~

Các lệnh trên là **minh họa**, chạy trong thư mục có `SampleTarget.java`. `javap -v` hiển thị constant pool, classfile major/minor, attributes; `javap -c` hiển thị bytecode instructions. Đây là **artifact file**, không phải nội dung đã được JVM cài đặt sau khi các agents sửa code.

### 2.2. classfileBuffer: bytes trong callback của ClassFileTransformer

~~~java
byte[] transform(
    ClassLoader loader,
    String className,
    Class<?> classBeingRedefined,
    ProtectionDomain protectionDomain,
    byte[] classfileBuffer);
~~~

Đây là **chữ ký callback** dạng đoạn trích; cần import `java.security.ProtectionDomain`. `classfileBuffer` là **input của transformer hiện tại**, chưa phải chắc chắn artifact gốc hoặc installed runtime bytes cuối cùng.

- Ở class load lần đầu, transformer đầu tiên thường nhận bytes mà classloader đưa cho `defineClass`.
- Trong nhiều transformers, output của transformer trước được truyền làm input cho transformer sau.
- Ở redefinition, transformer có thể nhận bytes từ `ClassDefinition` đã cung cấp.
- Ở retransformation, JVM dùng initial bytes theo contract và tái áp các transformers, có nuances về constant pool/order/attributes và non-retransform-capable transforms.

**Không sửa trực tiếp `classfileBuffer` tại chỗ**; khi muốn thay đổi, tạo `byte[]` mới/copy và trả array mới. Nếu không thay, trả `null`.

### 2.3. Installed definition: class mà JVM đang thực thi

JVM kiểm tra và cài đặt class definition sau các transformations thành công. **`Class<?>` không có public method `getClassFileBytes()` để lấy bản bytes hiện đang được thực thi**. `Instrumentation.getAllLoadedClasses()` trả **`Class<?>[]`**, không trả runtime bytes; Java Reflection mô tả cấu trúc/thành viên, không xuất một classfile copy đầy đủ.

Khi app gọi `SampleTarget.value()` và nhận `"MODIFIED_VALUE"`, đó là **bằng chứng hành vi** rằng method definition hiện tại đã chịu biến đổi. Đọc `SampleTarget.class` từ resource có thể vẫn thấy `"ORIGINAL_VALUE"` — hai quan sát không mâu thuẫn.

### 2.4. Ba nguồn có thể khác nhau

| Nguồn | Cách lấy | Ý nghĩa chính | Không bảo đảm |
| --- | --- | --- | --- |
| Artifact trong classes/JAR | `Files.readAllBytes(path)` hoặc `Class.getResourceAsStream(...)` | Bytes tồn tại ở nguồn classpath/resource | Đúng installed runtime bytes |
| `classfileBuffer` | Callback `ClassFileTransformer.transform` | Bytes đầu vào của tầng transformer đó | Là original disk bytes nếu đã qua transformer trước |
| JVM class definition đang chạy | Kiểm tra behavior/Reflection/JFR, hoặc thu bytes qua instrumentation callback theo chính sách | Hành vi và metadata runtime | Có public `Class#getClassFileBytes()` |
| Definition thay thế | `ClassDefinition(c, replacementBytes)` | Bytes ứng dụng yêu cầu redefine | Mọi schema change được hỗ trợ |
| Class-File API model | `ClassFile.of().parse(bytes)` Java 24+ | Parse binary classfile đã có thành model | Tự động đọc “current loaded class” không có input bytes |

**Kết luận:** Muốn đọc một classfile để debug, hãy nói rõ “đọc từ artifact”, “đọc callback bytes”, hay “xác minh runtime behavior”; đừng dùng ba cụm này thay nhau.

## 3. API hợp đồng: addTransformer, removeTransformer, retransformClasses, redefineClasses

### 3.1. Đăng ký transformer

~~~java
Instrumentation inst = /* do JVM cấp trong premain */;
inst.addTransformer(transformer, true);
~~~

Đây là **đoạn trích**, chưa có biến `inst`/`transformer`. Dòng thứ hai yêu cầu một **retransformation-capable transformer**. JVM phải trả `inst.isRetransformClassesSupported()==true`, nếu không `addTransformer(transformer,true)` ném `UnsupportedOperationException`.

Ngược lại:

~~~java
inst.addTransformer(transformer);
~~~

Đoạn trích. Overload một tham số tương đương `addTransformer(transformer,false)`. Transformer vẫn có thể thấy **future class loads** và **redefinitions**, nhưng callback của nó **không chạy lại** cho retransformation của class đã loaded. JVM có thể **tái áp output cũ** của transformer non-capable mà không gọi callback lại — chi tiết quan trọng khi nghĩ về rollback.

### 3.2. removeTransformer trả về gì?

~~~java
boolean removed = inst.removeTransformer(transformer);
~~~

**`true`** nghĩa transformer instance có trong registry và lần registration phù hợp vừa được loại khỏi danh sách. **`false`** nghĩa không tìm thấy registration đang tồn tại; không đồng nghĩa “class đã hoàn tác”.

Theo Javadoc Java SE 26, mặc dù đã `removeTransformer`, callback từ class loading **đang diễn ra đồng thời** có thể vẫn tới. Transformer phải an toàn với late calls, không đóng tài nguyên quá sớm rồi gây lỗi trong callback.

Không đăng ký cùng một instance transformer nhiều lần: nếu làm vậy, `removeTransformer` chỉ gỡ **registration phù hợp gần nhất**, dễ tạo leak và khó hiểu ownership.

### 3.3. Retransformation dựa trên định nghĩa nào?

`inst.retransformClasses(Target.class)` chạy lại pipeline theo nguyên tắc:

1. Bắt đầu từ **initial classfile bytes** của class definition (hoặc bytes gần nhất được đưa vào redefinition), có thể không **bit-for-bit** giống artifact ban đầu vì JVM có quyền điều chỉnh constant pool/order/attributes.
2. Với transformers **không capable retransformation** vẫn nằm trong pipeline, output trước đây của chúng được **tái sử dụng**, không nhất thiết gọi callback.
3. Với transformers **capable retransformation** còn đăng ký, JVM gọi callback để tạo output mới.
4. JVM kiểm tra/verify và cài definition mới nếu không vi phạm giới hạn JVM TI.

~~~java
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(Target.class)) {
    inst.retransformClasses(Target.class);
}
~~~

Đây là **đoạn trích**. Retransform có thể thất bại do class không modifiable hoặc bytecode không hợp lệ. **Không suy rằng retransform không có callback thì mọi thay đổi của mọi agent đã biến mất.** Nếu một non-retransform-capable transformer đã biến đổi class, output đó có thể được giữ lại theo contract.

### 3.4. Redefinition: đưa bytes cụ thể

~~~java
inst.redefineClasses(
    new ClassDefinition(Target.class, originalClassfileBytes));
~~~

Đây là **đoạn trích**, `originalClassfileBytes` đã được ứng dụng xác minh. `redefineClasses` cài một definition dựa trên bytes được cung cấp và vẫn chịu các transformers liên quan đến redefinition nếu còn được đăng ký. Để “hoàn tác” đáng tin cậy, cần nguồn original bytes đúng target/classloader/class version, quản lý các transformers khác, rồi **kiểm tra behavior** sau khi redefine.

### 3.5. Gỡ transformer khác hoàn tác class

| Thao tác | Thay registry transformers? | Có thể thay definition đã loaded? | Ý nghĩa |
| --- | --- | --- | --- |
| `addTransformer(t,true)` | Có, thêm | Không trực tiếp cho class cũ | Chuẩn bị callback cho future events/retransforms |
| `removeTransformer(t)` | Có, bỏ | **Không tự đổi** | Ngừng đăng ký callbacks mới |
| `retransformClasses(c)` | Không | Có | Chạy lại pipeline theo quy tắc JVM |
| `redefineClasses(def)` | Không | Có | Cung cấp definition bytes khác |
| `Class.getResourceAsStream("X.class")` | Không | Không | Đọc resource nếu classloader cung cấp |
| `ClassFile.of().parse(bytes)` | Không | Không | Phân tích bytes đã có |

### 3.6. Không thể hoàn tác arbitrary class schema một cách tự do

JVM TI đặt giới hạn đối với retransform/redefine như thay superclass, field/method layout/signatures và một số class attributes. Một class `isModifiableClass(c)==true` **không có nghĩa** “mọi bytecode/schema change hợp lệ”. Demo chỉ đổi một **string literal cùng độ dài** trong constant pool, không thêm/xóa method/field, không sửa hierarchy.

## 4. ClassFileTransformer: callback, thứ tự, lỗi và an toàn bytes

### 4.1. Hai dạng transform

Interface `ClassFileTransformer` có overload năm tham số và overload có `Module` (từ Java 9). Trong Java 17, cả hai đều có default implementations; **không xem interface này là functional interface để viết lambda tùy tiện**.

~~~java
ClassFileTransformer transformer = new ClassFileTransformer() {
    @Override
    public byte[] transform(ClassLoader loader,
            String internalName,
            Class<?> beingRedefined,
            ProtectionDomain domain,
            byte[] input) {
        if (!"com/example/Target".equals(internalName)) {
            return null;
        }
        return input.clone(); // Copy hợp lệ, nhưng chưa sửa gì.
    }
};
~~~

Đây là **đoạn trích**; cần import `java.lang.instrument.ClassFileTransformer` và `java.security.ProtectionDomain`. `internalName` dùng dấu `/` thay vì `.` với package paths. Callback không bao giờ phải tự ý đổi bytes của một class ngoài allowlist.

### 4.2. Callback exception không tự hủy class load

Theo Javadoc, nếu transformer ném exception ra ngoài, JVM vẫn gọi các transformers còn lại; về ảnh hưởng biến đổi, nó được xử lý như **trả `null`**. Vì vậy **không dùng throw trong transformer như rollback transaction**. Với dữ liệu malformed, `IllegalClassFormatException` giúp chẩn đoán/logging nhưng vẫn không thay cho một chính sách fail-closed ở cấp agent/application.

Đối với một kiểm thử:
- Kiểm tra callback thực sự được gọi qua bounded counter.
- So input/output hashes/bytes trên đúng target.
- Tách điều kiện “callback chạy” khỏi “definition installed” và “business behavior đúng”.
- Dùng fixture class không có side effects rủi ro.

### 4.3. Thứ tự transformer có ảnh hưởng

Khi có nhiều transformers, output của cái trước là input của cái sau. Javadoc nêu nhóm ưu tiên gồm:
1. Java transformers **retransformation-incapable**;
2. native retransformation-incapable;
3. Java transformers **retransformation-capable**;
4. native retransformation-capable.

Trong từng nhóm, các transformers chạy theo registration order. Khi tính undo, cần biết **những tầng nào còn active** và tầng non-capable nào được reapply tự động. Đừng chỉ nhìn một transformer do mình sở hữu rồi cho rằng pipeline hoàn toàn rỗng.

### 4.4. Không mutation input buffer

~~~java
byte[] result = input.clone();
System.arraycopy(replacement, 0, result, offset, replacement.length);
return result;
~~~

Đây là **đoạn trích**. Việc copy input bảo đảm transformer sau không nhìn một input đã bị sửa bất ngờ ngoài contract. Đối với production bytecode changes, cần parser/rewriter hiểu constant pool, stack maps và classfile version; không “find and replace string” tràn lan.

### 4.5. Gỡ transformer nhưng vẫn có callback trễ

Mặc dù `removeTransformer(t)` trả true, một luồng khác có thể đã vào class definition/transform pipeline và gọi t sau đó. Khi t dùng logs/metrics/network resources, cấu trúc lifecycle phải an toàn với callback đang chạy:
- đánh dấu stopping;
- không thu hồi dữ liệu mà callback còn dùng;
- giới hạn synchronization để tránh lock recursion trong class loading;
- chờ hoặc dùng ref-count/coordination nếu cần;
- không assume Java APIs có lệnh “join mọi transformer callbacks”.

## 5. Class file có thể đọc như thế nào?

### 5.1. Đọc resource classfile trong Java 17+

~~~java
try (InputStream stream =
        Example.class.getResourceAsStream("/SampleTarget.class")) {
    if (stream == null) {
        throw new IllegalStateException("Resource unavailable");
    }
    byte[] bytes = stream.readAllBytes();
    // bytes của resource; KHÔNG tự nhận đây là installed definition.
}
~~~

**Đoạn trích**, cần imports `java.io.InputStream`. `/SampleTarget.class` là resource absolute trong context class classpath. Với class có package `com.example`, resource có thể là `/com/example/SampleTarget.class`. Relative name không có dấu / được resolve theo package của class đang gọi.

**Không giả định resource luôn tồn tại:**
- Custom class loader có thể tạo class từ bytes mà không expose `.class` resource;
- Dynamically generated/hidden classes có thể không có resource URL;
- Artifact đã bị thay/xóa sau khi class load;
- JPMS/module encapsulation hoặc custom loader có thể ảnh hưởng resource lookup;
- Multi-release JAR có thể chọn version-specific class entry;
- Container/classpath overlay có thể có multiple resources;
- Runtime transformations không buộc ghi ngược file `.class`.

### 5.2. Đọc file bằng Path và Files

~~~java
Path classFile = Path.of("classes", "SampleTarget.class");
byte[] bytes = Files.readAllBytes(classFile);
~~~

Đây là **đoạn trích**, cần imports `java.nio.file.Path`, `java.nio.file.Files`. Path này chỉ tồn tại theo build layout bạn biết. Với JAR, cần `JarFile`/`ZipFile` entries hoặc `JarURLConnection`/resource streams; không nối path của file JAR với `/SampleTarget.class` như thể nó là folder bình thường.

### 5.3. Đọc đúng binary header

~~~text
CA FE BA BE   00 00   00 3D   ...
| magic     | minor | major=61 (Java 17 class file)
~~~

Đây là định dạng minh họa. Major version của classfile compiled với `--release 17` là 61. Với các Java versions khác, version có thể khác. **Magic đúng chưa đủ để chứng minh classfile hợp lệ**; bạn còn phải parse constant pool, method/field tables, attributes và bytecode verifier constraints.

### 5.4. `javap` không đọc definition đang chạy

~~~bash
javap -v -p classes/SampleTarget.class
javap -c -p SampleTarget
~~~

Đây là lệnh minh họa. Tùy `javap` options/path, nó đọc **artifact** từ file/classpath; không tự kết nối JVM đang chạy rồi xuất “installed post-agent bytes”. Vì vậy `javap` có thể cho `ORIGINAL_VALUE` trong khi app trả `MODIFIED_VALUE`. Cả hai kết quả có thể đúng.

### 5.5. Không có API chính thức để dump mọi installed class bytes từ Class

`Class<?>` có `getDeclaredMethods`, `getDeclaredFields`, `getClassLoader`, `getModule`, nhưng không công bố `getClassFileBytes`. `Instrumentation.getAllLoadedClasses()` cho danh sách Class objects, không cho bytes. Muốn giám sát classfile bytes khi load/retransform, dùng transformer với **scope rõ và nguồn dữ liệu có nguồn gốc**, hoặc tools/JVM diagnostics được hỗ trợ; không dùng reflection hack/internal unsupported APIs để trích bytecode.

## 6. Java 24+ Class-File API: đọc class file bằng parser chính thức

`java.lang.classfile.ClassFile` và `ClassModel` là **standard Class-File API kể từ Java 24 (JEP 484)**. Nó tiếp tục có trong Java SE 26 và là lựa chọn hiện đại để parse/generate/transform classfile ở JDK 24+. Một parser thực có thể hiểu constant pool, method models và attributes thay vì chỉnh byte strings tùy tiện.

### 6.1. Cách parse đơn giản

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;

ClassModel model = ClassFile.of().parse(bytes);
String internalName = model.thisClass().asInternalName();
int version = model.majorVersion();
boolean found = model.methods().stream().anyMatch(
        method -> "value".equals(method.methodName().stringValue()));
~~~

Đây là **đoạn trích**, `bytes` là một byte array đã được ứng dụng đọc, không phải current installed JVM bytes. `ClassModel` cung cấp model có **lazy parsing** ở nhiều thành phần: truy cập accessor sau `parse` vẫn có thể phát sinh `IllegalArgumentException` nếu classfile malformed; không coi parser đã hoàn thành toàn bộ deep validation khi chỉ đọc header.

### 6.2. Java 17/21 có dùng java.lang.classfile được không?

**Không.** API chính thức này từ Java 24. Ví dụ sau phải compile `--release 24` hoặc target mới hơn. Nếu library phải hỗ trợ Java 17/21, có thể:
- Dùng tools `javap` để phân tích artifact thủ công;
- Dùng classfile library như **ASM** phiên bản cập nhật hỗ trợ target classfile version, nếu project cho phép dependency;
- Dùng logic chỉ đọc header/metadata đơn giản khi đủ yêu cầu, không tự viết transformer bytecode phức tạp.

Đừng import `java.lang.classfile` trong source `--release 17` rồi thêm JVM flag tùy tiện; đó là API không tồn tại trong Java 17.

### 6.3. Class-File API không tự restore

Dù parser đọc thành công file, việc cài bytes vào JVM vẫn cần `Instrumentation`/JVM capabilities và class eligibility. `ClassFile.parse` là **phân tích bytes**, không phải lệnh `retransformClasses` hay rollback; parser không cung cấp phép màu để xóa modifications đang cài trong JVM.

## 7. Tư duy kiểm thử: ba lớp bằng chứng phải đi cùng nhau

Một bài test tốt cho instrumentation cần tách:

**Lớp 1 — cấu hình và callback:**
- Agent `premain` được gọi;
- Manifest capabilities được JVM cấp;
- `isModifiableClass(target)==true`;
- Transformer của bạn thấy đúng class name/classloader;
- Callback count như kỳ vọng, không vô tình transform classes khác.

**Lớp 2 — bytes/classfile:**
- Original artifact có magic/version/class name đúng;
- Transformer nhận input bytes đúng kỳ vọng;
- Output bytes không làm hỏng classfile;
- Original reference có nguồn gốc đáng tin (artifact hash/version/classloader);
- Parser/verification không báo malformed;
- Không đổi binary name/schema trừ khi JVM cho phép.

**Lớp 3 — runtime behavior và undo:**
- Gọi method sau class load được transformed value;
- Sau `removeTransformer`, method vẫn giữ definition đã đổi;
- Khi deliberately `retransformClasses` trong controlled pipeline không còn transformer, method khôi phục baseline;
- Khi `redefineClasses` bằng patched bytes, behavior đổi;
- Khi `redefineClasses` bằng source bytes gốc, behavior khôi phục;
- Resource artifact đọc lại vẫn unchanged;
- Cleanup có kiểm soát, không biến đổi classes ngoài phạm vi.

**Chỉ assert callback-count >0 là chưa đủ.** Transformer có thể trả `null`, class verifier từ chối output, transformation diễn ra ở classloader khác hoặc method đang gọi dùng active old frames.

## 8. Java 17+ runnable: startup agent kiểm tra biến đổi và hoàn tác

Bài lab có ba file Java:
- `LabAgent.java`: agent nhận Instrumentation trong `premain`, đăng ký transformer **retransformation-capable**, chỉ nhắm class `SampleTarget`.
- `SampleTarget.java`: method trả string literal `ORIGINAL_VALUE`.
- `TransformationLifecycleDemo.java`: assert từng giai đoạn, truy cập original resource, remove transformer, retransform, redefine và kiểm tra output.

JAR agent được build với manifest:
- `Premain-Class: LabAgent`;
- `Can-Retransform-Classes: true`;
- `Can-Redefine-Classes: true`.

Tất cả test code compile target Java 17 và dùng standard Java libraries.

### 8.1. File SampleTarget.java

~~~java
public final class SampleTarget {
    public static String value() {
        return "ORIGINAL_VALUE";
    }
}
~~~

`SampleTarget` cố ý có method rất nhỏ, không có static side effects, không phụ thuộc DB hoặc network. Ta sẽ **chỉ** sửa chuỗi literal trong classfile do compiler tạo ra. Một string mới `MODIFIED_VALUE` có cùng số bytes ASCII với `ORIGINAL_VALUE`, nên trong fixture có thể đổi byte array mà không làm thay đổi kích thước constant-pool entry.

**Lưu ý:** Cách thay byte string này **chỉ an toàn trong lớp test được kiểm soát**, có assert đúng một chỗ xuất hiện, cùng byte length, class đã compile và runtime đã test. Không đưa nó vào production bytecode rewriter, vì arbitrary strings có thể nằm trong multiple constant-pool entries, modified UTF-8, attributes, debug metadata hoặc cấu trúc khác.

### 8.2. File LabAgent.java

~~~java
import java.lang.instrument.*;
import java.nio.charset.StandardCharsets;
import java.security.ProtectionDomain;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicInteger;

public final class LabAgent {
    private static volatile Instrumentation instrumentation;
    static volatile byte[] inputAtLoad;
    static final AtomicInteger transformations = new AtomicInteger();
    private static volatile ClassFileTransformer transformer;
    private static final String ORIGINAL = "ORIGINAL_VALUE";
    private static final String REPLACEMENT = "MODIFIED_VALUE";

    public static void premain(String arguments, Instrumentation inst) {
        instrumentation = inst;
        if (!inst.isRetransformClassesSupported() || !inst.isRedefineClassesSupported()) {
            throw new IllegalStateException("Required capabilities absent");
        }
        transformer = new ClassFileTransformer() {
            @Override public byte[] transform(ClassLoader loader, String className,
                    Class<?> classBeingRedefined, ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {
                if (!"SampleTarget".equals(className)) return null;
                inputAtLoad = classfileBuffer.clone();
                transformations.incrementAndGet();
                return replaceLiteral(classfileBuffer, ORIGINAL, REPLACEMENT);
            }
        };
        inst.addTransformer(transformer, true);
        System.out.println("agent-started=true");
    }

    static Instrumentation instrument() {
        if (instrumentation == null) throw new IllegalStateException("-javaagent missing");
        return instrumentation;
    }

    static boolean detach() {
        ClassFileTransformer saved = transformer;
        boolean removed = instrument().removeTransformer(saved);
        transformer = null;
        return removed;
    }

    static byte[] replaceLiteral(byte[] src, String from, String to) {
        byte[] needle = from.getBytes(StandardCharsets.US_ASCII);
        byte[] replacement = to.getBytes(StandardCharsets.US_ASCII);
        if (needle.length != replacement.length) {
            throw new IllegalArgumentException("Only equal length literals in test");
        }
        byte[] result = src.clone();
        int matches = 0;
        for (int i = 0; i <= result.length - needle.length; i++) {
            boolean match = true;
            for (int j = 0; j < needle.length; j++) {
                if (result[i + j] != needle[j]) { match = false; break; }
            }
            if (match) {
                System.arraycopy(replacement, 0, result, i, replacement.length);
                matches++;
                i += needle.length - 1;
            }
        }
        if (matches != 1) throw new IllegalArgumentException("Expected one literal, got " + matches);
        return result;
    }
}
~~~

**Đọc code:** `LabAgent.premain` chạy trước application main; nhận JVM capability rồi đăng ký transformer. Chỉ `SampleTarget` được patch; mọi class khác trả `null`. `inputAtLoad` là bản copy của callback bytes để so với original resource trong test. `AtomicInteger` đếm callback. `replaceLiteral` kiểm tra input/output ASCII equal length, copy array và require đúng một occurrence; nếu không đạt sẽ fail thay vì âm thầm sửa vùng bytes khác.

**Điểm cần ghi nhớ:** Transformer này không dùng bytecode API; nó là fixture để minh họa vòng đời, không phải mẫu thay String constants tổng quát. Trong production dùng parser/transformer library được bảo trì với target JDK/version.

### 8.3. File TransformationLifecycleDemo.java

~~~java
import java.io.InputStream;
import java.lang.instrument.*;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class TransformationLifecycleDemo {
    static void check(boolean okay, String name) {
        if (!okay) throw new AssertionError(name);
    }

    static byte[] readResource(String name) throws Exception {
        try (InputStream stream = TransformationLifecycleDemo.class.getResourceAsStream(name)) {
            if (stream == null) throw new IllegalStateException("Missing " + name);
            return stream.readAllBytes();
        }
    }

    static boolean containsOriginal(byte[] bytes) {
        return new String(bytes, StandardCharsets.ISO_8859_1)
                .contains("ORIGINAL_VALUE");
    }

    public static void main(String[] args) throws Exception {
        Instrumentation inst = LabAgent.instrument();
        check(inst.isRetransformClassesSupported() && inst.isRedefineClassesSupported(),
                "manifest support missing");
        check(inst.isModifiableClass(SampleTarget.class), "target not modifiable");

        String loaded = SampleTarget.value();
        check("MODIFIED_VALUE".equals(loaded), "load transform not applied");
        check(LabAgent.transformations.get() == 1, "expected one target transform");

        byte[] resourceBytes = readResource("/SampleTarget.class");
        check((resourceBytes[0] & 255) == 0xCA
                && (resourceBytes[1] & 255) == 0xFE
                && (resourceBytes[2] & 255) == 0xBA
                && (resourceBytes[3] & 255) == 0xBE, "CAFEBABE missing");
        check(containsOriginal(resourceBytes), "original resource missing");
        check(Arrays.equals(resourceBytes, LabAgent.inputAtLoad),
                "load callback should see original classfile bytes");

        boolean detached = LabAgent.detach();
        check(detached, "transformer was not registered");
        check("MODIFIED_VALUE".equals(SampleTarget.value()),
                "removing transformer should not restore class");
        inst.retransformClasses(SampleTarget.class);
        check("ORIGINAL_VALUE".equals(SampleTarget.value()),
                "retransformation without transformer should restore baseline");
        byte[] patched = LabAgent.replaceLiteral(
                resourceBytes, "ORIGINAL_VALUE", "MODIFIED_VALUE");
        inst.redefineClasses(new ClassDefinition(SampleTarget.class, patched));
        check("MODIFIED_VALUE".equals(SampleTarget.value()),
                "redefinition using patched bytes");
        inst.redefineClasses(new ClassDefinition(SampleTarget.class, resourceBytes));
        check("ORIGINAL_VALUE".equals(SampleTarget.value()),
                "redefinition using original bytes");
        check(Arrays.equals(resourceBytes, readResource("/SampleTarget.class")),
                "classpath resource changed unexpectedly");

        System.out.println("retransform-supported=true");
        System.out.println("redefine-supported=true");
        System.out.println("target-modifiable=true");
        System.out.println("original-resource-magic=CAFEBABE");
        System.out.println("load-transform-count=" + LabAgent.transformations.get());
        System.out.println("initial-result=" + loaded);
        System.out.println("captured-input-equals-resource=true");
        System.out.println("resource-still-original-after-transform=true");
        System.out.println("removed-transformer=" + detached);
        System.out.println("value-after-remove=MODIFIED_VALUE");
        System.out.println("value-after-retransform=ORIGINAL_VALUE");
        System.out.println("value-after-redefine-patched=MODIFIED_VALUE");
        System.out.println("value-after-redefine-original=ORIGINAL_VALUE");
        System.out.println("resource-still-original=true");
        System.out.println("tests=PASS");
    }
}
~~~

**Đọc code:** `LabAgent.instrument()` chỉ trả Instrumentation khi agent đã startup. `SampleTarget.class` được load và transform khi app dùng class lần đầu. `readResource` đọc compiled class file từ classpath, không dump installed definition. Sau `detach()`, method vẫn cho transformed result. `retransformClasses` trong test này chạy sau khi transformer duy nhất đã được gỡ, nên quay lại baseline. Hai `redefineClasses` lần lượt dùng bytes đã patch và original bytes, rồi assertions xác minh hành vi hai chiều.

### 8.4. Manifest file agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: LabAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
~~~

**Giữ một dòng trống sau dòng cuối** khi lưu manifest. Nếu thiếu `Can-Retransform-Classes:true`, `addTransformer(transformer,true)`/`retransformClasses` có thể bị từ chối; nếu thiếu `Can-Redefine-Classes:true`, redefine có thể bị từ chối. JVM cũng phải thực sự hỗ trợ những capabilities đó. Không tự suy từ manifest rằng operation chắc chắn thành công.

### 8.5. Compile, đóng JAR và chạy trên Java 17+

Tạo 3 source files và manifest trong cùng một thư mục. Lệnh bash/Linux/macOS:

~~~bash
mkdir -p classes
javac -encoding UTF-8 --release 17 -d classes LabAgent.java SampleTarget.java TransformationLifecycleDemo.java
jar --create --file lab-agent.jar --manifest agent.mf -C classes LabAgent.class -C classes 'LabAgent$1.class'
java -javaagent:lab-agent.jar -cp classes TransformationLifecycleDemo
~~~

Lưu ý có **`LabAgent$1.class`** vì anonymous `ClassFileTransformer` ở trong `LabAgent.java` sinh inner class file. Nếu chỉ đưa `LabAgent.class` vào JAR nhưng không đóng inner class, JVM có thể báo `NoClassDefFoundError` khi `premain` tạo transformer. Dấu nháy đơn trong lệnh bash bảo vệ `$1` không bị shell expansion.

Với PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path classes | Out-Null
javac -encoding UTF-8 --release 17 -d classes LabAgent.java SampleTarget.java TransformationLifecycleDemo.java
jar --create --file lab-agent.jar --manifest agent.mf -C classes LabAgent.class -C classes 'LabAgent$1.class'
java "-javaagent:lab-agent.jar" -cp classes TransformationLifecycleDemo
~~~

**Môi trường đã kiểm thử:** dùng OpenJDK 24 để compile với `--release 17`, tạo JAR và chạy. Không dùng attach API, không bật remote instrumentation, không sửa code ứng dụng thực tế.

### 8.6. Stdout đã kiểm thử, chính xác

~~~text
agent-started=true
retransform-supported=true
redefine-supported=true
target-modifiable=true
original-resource-magic=CAFEBABE
load-transform-count=1
initial-result=MODIFIED_VALUE
captured-input-equals-resource=true
resource-still-original-after-transform=true
removed-transformer=true
value-after-remove=MODIFIED_VALUE
value-after-retransform=ORIGINAL_VALUE
value-after-redefine-patched=MODIFIED_VALUE
value-after-redefine-original=ORIGINAL_VALUE
resource-still-original=true
tests=PASS
~~~

### 8.7. Phân tích từng giai đoạn

**Agent loaded:** `agent-started=true` nghĩa `premain` đã chạy và transformer đăng ký trước application main. Không có dòng này thường phải kiểm tra startup flags/manifest.

**Capabilities:** `retransform-supported=true`, `redefine-supported=true` và `target-modifiable=true` xác nhận cả agent-level operation support và class-level eligibility trong JVM test.

**Input artifact:** `original-resource-magic=CAFEBABE` cho biết resource bắt đầu bằng classfile magic. `captured-input-equals-resource=true` chỉ khớp trong fixture có một simple classpath load và transformer đầu tiên. Với custom loader/multiple transformers, đừng mong chúng luôn trùng.

**Load-time transformation:** `load-transform-count=1` và `initial-result=MODIFIED_VALUE` xác nhận callback thực sự sửa class được JVM load. Đây là behavior test, mạnh hơn việc chỉ đếm callback.

**Removal:** `removed-transformer=true` nhưng `value-after-remove=MODIFIED_VALUE` chứng minh gỡ callback **không hoàn tác định nghĩa hiện hành**.

**Retransform:** `value-after-retransform=ORIGINAL_VALUE` chứng minh test đã khôi phục baseline **trong pipeline đơn giản không còn transformer**. Kết quả này không tự tổng quát hóa cho nhiều agents hoặc non-retransform-capable transforms.

**Redefine:** `value-after-redefine-patched=MODIFIED_VALUE` và `value-after-redefine-original=ORIGINAL_VALUE` chứng minh có thể cài classfile bytes cụ thể theo thứ tự khi có capability và không đổi schema.

**Resource bytes:** `resource-still-original=true` chứng minh classpath artifact không bị cập nhật khi JVM thay definition trong memory. Điều này bác bỏ giả định “đọc .class thì thấy runtime bytecode hiện tại”.

## 9. Java 24+ runnable: phân tích classfile bằng Class-File API

Chương trình độc lập này dùng package `java.lang.classfile`. Nó đọc **file `classes/SampleTarget.class`** do `javac --release 17` tạo ra, parse thành `ClassModel`, kiểm tra:
- Internal class name là `SampleTarget`;
- Major version là `61` (Java 17);
- Method `value` tồn tại;
- Source file có literal `ORIGINAL_VALUE`;
- Input sai magic/thiếu bytes bị parser từ chối bằng `IllegalArgumentException`.

Chương trình không cần Java agent, không sửa file, không dùng `Instrumentation`. Nó giúp xác minh **readability/structure của original artifact**, chứ không chứng minh runtime behavior của transformed class.

### 9.1. File ClassFileInspectionDemo.java

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public final class ClassFileInspectionDemo {
    static void check(boolean okay, String reason) {
        if (!okay) throw new AssertionError(reason);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("classfile path required");
        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        ClassModel model = ClassFile.of().parse(bytes);
        String className = model.thisClass().asInternalName();
        boolean methodExists = model.methods().stream().anyMatch(
                method -> "value".equals(method.methodName().stringValue()));
        boolean hasOriginal = new String(bytes, StandardCharsets.ISO_8859_1)
                .contains("ORIGINAL_VALUE");
        boolean badRejected = false;
        try {
            ClassFile.of().parse(new byte[]{0, 1, 2});
        } catch (IllegalArgumentException expected) {
            badRejected = true;
        }
        check("SampleTarget".equals(className), "wrong class name");
        check(model.majorVersion() == 61, "should be Java 17 version 61");
        check(methodExists && hasOriginal && badRejected, "classfile inspection failed");
        System.out.println("classfile-name=" + className);
        System.out.println("classfile-major-version=" + model.majorVersion());
        System.out.println("method-value-found=" + methodExists);
        System.out.println("original-literal-present=" + hasOriginal);
        System.out.println("malformed-input-rejected=" + badRejected);
        System.out.println("tests=PASS");
    }
}
~~~

### 9.2. Compile và chạy đúng target JDK

Giữ `SampleTarget.class` đã build bằng `--release 17` ở mục 8. Chạy với **JDK 24+**:

~~~bash
javac -encoding UTF-8 --release 24 -d classes ClassFileInspectionDemo.java
java -cp classes ClassFileInspectionDemo classes/SampleTarget.class
~~~

PowerShell tương tự:

~~~powershell
javac -encoding UTF-8 --release 24 -d classes ClassFileInspectionDemo.java
java -cp classes ClassFileInspectionDemo "classes/SampleTarget.class"
~~~

Không compile bằng Java 17, vì `java.lang.classfile` là API chuẩn từ Java 24. Nếu chỉ có JDK 17, làm riêng mục 8 và dùng `javap` hoặc thư viện classfile parser được bảo trì.

### 9.3. Stdout chính xác trên OpenJDK 24

~~~text
classfile-name=SampleTarget
classfile-major-version=61
method-value-found=true
original-literal-present=true
malformed-input-rejected=true
tests=PASS
~~~

### 9.4. Hạn chế của parsing

`ClassFile.of().parse(bytes)` hỗ trợ parse classfile, nhưng:
- ClassModel có thể parse lazy; lỗi malformed ở phần sâu có thể xuất hiện khi truy cập accessor;
- Parser không thay JVM verifier/linker;
- Source literal search bằng chuyển raw bytes sang ISO_8859_1 trong demo chỉ là kiểm tra fixture ASCII, không phải kiểm tra mọi constant pool encoding;
- File trên đĩa có thể là version khác với class đã được custom loader define;
- Model từ file không tự cập nhật khi runtime JVM đang ở definition khác.

Một production diagnostic tool nên kiểm tra class version, name, method descriptors và cần tính provenance/sha256 của bytes; không suy behavior từ việc parser không ném exception.

## 10. Khi gỡ biến đổi, “restore” là một yêu cầu riêng

### 10.1. Vì sao removeTransformer không thể tự rollback?

JVM đã cài một definition có thể đã làm JIT compile, lưu metadata và đang có active stack frames. `removeTransformer` chỉ thao tác **danh sách các hooks** được gọi cho class definitions về sau; nó không yêu cầu JVM phát lại tất cả definitions đã transform. Vì vậy class behavior vẫn là modified khi method được gọi sau remove.

### 10.2. Cơ chế restore bằng retransform trong pipeline được kiểm soát

Nếu:
- Class được load từ original bytes đã biết;
- Transformer của bạn được đăng ký `canRetransform=true` và là tầng duy nhất tác động tới target;
- Bạn đã remove transformer đó;
- Không có non-retransform-capable transformer khác để reapply changes;
- Chưa redefine class bằng bytes mới khác baseline;
- Agent/JVM hỗ trợ và target modifiable;
- Bytecode baseline vẫn hợp lệ;

thì `retransformClasses(Target.class)` có thể khôi phục behavior gốc. Demo chứng minh đúng trường hợp này.

Nhưng khi có **các transformers khác** vẫn còn active hoặc output non-retransform-capable được JVM tái áp, retransform có thể **không** quay về artifact gốc. Không triển khai API “undo” theo tên method mà bỏ qua dependency này.

### 10.3. Restore bằng redefine với bytes gốc được xác minh

Một cách khác là `redefineClasses(new ClassDefinition(Target.class, originalBytes))` sau khi kiểm soát transformer registrations. Cần có original bytes đúng class **loader/version**. Không tự gán original bytes bằng file cùng tên tìm được trên classpath nếu có multi-release JAR, shaded classes, generated classes hay runtime definition khác.

### 10.4. Active stack frames và state

Theo Javadoc, các active stack frames của methods được retransform/redefine có thể tiếp tục dùng **old bytecodes** cho đến khi kết thúc; method invocations mới sẽ thấy definition mới. JVM không tự:
- chạy lại class initializer;
- reset static fields;
- sửa state của existing objects;
- rollback external side effects;
- khôi phục database transactions.

Vì vậy ngay cả khi `value()` trong demo trở lại `ORIGINAL_VALUE`, điều đó **không phải rollback toàn bộ ứng dụng**. Rollback production cần canary, business validation, safe deployment và khả năng restart nếu không đủ tin cậy.

### 10.5. Nên lưu những gì để rollback?

Một agent quản lý nhiều classes có thể cần lưu **có giới hạn**:
- Class identity gồm binary name + defining loader identity + module + process;
- Artifact build ID, SHA-256, classfile major version;
- Original definition bytes được thu thập theo nguồn đáng tin;
- Transformer pipeline/registration phiên bản;
- Có bao nhiêu classes được instrument thành công, thất bại, skipped;
- Operation/capabilities và thời điểm;
- Quy trình xác minh runtime sau restore.

**Không lưu toàn bộ application classes vô hạn** trong heap hay ghi ra files công khai; bytes có thể chứa secrets/implementation details. Có memory budgets/retention/encryption/access control rõ ràng.

## 11. Kịch bản test matrix cho agent

| Kịch bản | Bằng chứng kỳ vọng | Cách tránh false positive |
| --- | --- | --- |
| Agent premain chạy | `agent-started=true` | Không suy từ JAR tồn tại |
| Manifest không có retransform capability | `isRetransformClassesSupported()==false` hoặc startup policy phù hợp | Không gọi `addTransformer(t,true)` mù |
| Target class modifiable | `isModifiableClass(target)==true` | Không suy từ retransform capability |
| Transformer đúng target | Class internal name, loader, callback count | Không transform toàn JVM |
| Transformer trả null | Behavior nguyên gốc | Không kết luận có patch |
| Transformer trả bytes đã copy | Class verifier chấp nhận; method behavior đã đổi | Không mutate input |
| Other class load | Không bị patch | Allowlist filter |
| Mismatched literal occurrence | Fail fixture, không âm thầm đổi | Require exactly one match |
| Original resource available | Magic/major/name/sha256 | Phân biệt resource vs installed |
| Resource missing | Diagnostic rõ `null` | Không crash silent |
| Remove registered transformer | Returns true | Không nói runtime restored |
| Remove lần hai | Trả false khi không còn registration | Không dùng như dấu hiệu undo |
| Call method sau remove | Vẫn modified trong fixture | Behavioral assert |
| Retransform sau remove | Baseline restored chỉ ở controlled setup | Biết remaining transforms |
| Redefine bytes patched | Method returns patched value | Capabilities, modifiable, schema |
| Redefine original bytes | Method returns baseline | Verified provenance |
| Redefine unsupported schema | Fail rõ, không báo success | Test isolated process |
| Non-capable transform reapply | Có thể giữ transformed output | Thử pipeline nhiều tầng |
| Concurrent class loading/remove | Late callbacks có thể xảy ra | Defensive transformer lifecycle |
| Classfile parser Java 24+ | Class name/version/methods hợp lệ | Không compile --release17 |
| Invalid classfile header | Parser rejects | Không chỉ kiểm tra magic |
| Incorrect classfile version | Báo unsupported/mismatch | Verify target JDK |
| Multi-release JAR | Đọc đúng version-selected resource | Test runtime JDK matrix |
| Custom classloader | Resource may be missing/different | Test actual loader paths |
| Hidden class/dynamic generated | Không giả định có .class resource | Use provenance/callback |
| Class loader duplication | Hai runtime classes cùng name khác loader | Correlate identity |
| Active method frame during patch | Old frame may continue old bytes | New invocations tests |
| Static field state after redefine | Not reset | Separate state migration |
| JDK 17/21/24/26 | Verify APIs/examples per target | Explicit --release values |
| Security | No arbitrary bytecode upload endpoint | Trust, authentication, audit |
| Performance | Callback overhead bounded | Run benchmark/canary |
| No agent loaded | Fail with clear guidance | Không use null Instrumentation |
| Startup failure | Root cause visible | Don't swallow errors |
| Cleanup | Transformer deregistered, resources released | Finally/owner handles |

### 11.1. Một test tốt phải verify behavior, không chỉ callback

Ví dụ callback count = 1 không chứng minh output transformed bytes được verifier cài. Nếu method vẫn trả original value, nguyên nhân có thể là transformer trả null, filter sai, class đã load trước, compiled constant inlined ở caller, hoặc multi-agent interaction. Demo kiểm tra cả callback count và `SampleTarget.value()` để tăng độ tin cậy.

### 11.2. Tránh constant inlining sai ngữ cảnh

Nếu bạn muốn kiểm thử constant biến đổi, nên sửa một **method body** hoặc read runtime method return như fixture. Đừng viết test kiểu `public static final String MESSAGE = "ORIGINAL_VALUE"` rồi gọi `Caller.MESSAGE`: `javac` có thể inline compile-time constant vào caller, khiến bạn tưởng redefinition thất bại dù target class đã đổi. Demo gọi `SampleTarget.value()`, không đọc public static final String từ caller.

### 11.3. Chạy một JVM mới cho mỗi kịch bản quan trọng

Class loading state và transformer registrations ảnh hưởng test. Những trường hợp negative như corrupt bytes, unsupported schema, duplicate transformer registration, dynamic loading restrictions nên chạy **process test riêng có timeout**, không trộn vào app production hay build process có shared static state. Sau mỗi test kiểm tra exit status, stdout/stderr, file outputs và cleanup.

## 12. Class file validity và những lỗi thường gặp

### 12.1. ClassFormatError

Nếu transformed bytes không phải classfile hợp lệ, JVM có thể ném `ClassFormatError`. Không biến lỗi này thành một log warning nhẹ rồi coi class đã được instrument. Xác minh:
- Header/magic/version;
- Constant pool indices, modified UTF-8 entries;
- Method code/stack map frames;
- Name/loader/module compatibility;
- Binary class name trùng target;
- Code length/limits;
- Không vi phạm structural redefinition limits.

### 12.2. UnmodifiableClassException và unsupported operations

`isModifiableClass(Target.class)==true` không bảo đảm mọi operation. `retransformClasses` và `redefineClasses` còn phụ thuộc optional JVM/agent capabilities. Nếu class unsupported, `UnmodifiableClassException`; nếu operation/structural change unsupported, `UnsupportedOperationException`. Dùng documented capability checks và policy trước, nhưng vẫn handle exceptions khi thực hiện.

### 12.3. UnsupportedClassVersionError

Classfile có major version cao hơn JVM có thể xử lý sẽ không load. Khi test Java 17+, compile `--release 17` cho test baseline để chạy trên JDK17; chỉ file `ClassFileInspectionDemo` cần `--release 24`. Không “nâng major version” bằng cách sửa hai bytes trong header mà không compile target semantics.

### 12.4. NoClassDefFoundError và classpath/JAR packaging

JAR agent thiếu anonymous transformer `LabAgent$1.class` có thể khiến `premain` thất bại. Khi root cause là packaging, không suy do `isModifiableClass` hay JVM forbids instrumentation. Dùng `jar --list --file lab-agent.jar` để xem entries.

### 12.5. Classfile resource đọc thất bại

`getResourceAsStream` có thể trả null; `Files.readAllBytes` có thể ném IOException; jar entry có thể thay đổi. Khi không đọc được artifact, báo rõ **resource unavailable**, source path, loader/module context đã được phép log, và skip chức năng đọc nếu optional. Không làm giả bytes từ `new byte[0]` rồi tiếp tục parse/redefine.

### 12.6. Multi-release JAR / wrong classloader

Với JAR có `META-INF/versions/XX/...`, runtime có thể nạp version-specific entry. Một tool trực tiếp đọc root entry có thể không trùng runtime definition. Hai custom classloaders cũng có thể define cùng binary class name nhưng khác bytecode. Luôn correlate **Class identity** và **actual resource selection**.

### 12.7. Hidden classes và dynamically generated classes

Một hidden class/implementation generated on the fly có thể không có stable `.class` resource. `Class.getResourceAsStream` không tạo ra source artifact từ không khí. Instrumentation API có constraints riêng với hidden classes; dùng Java-supported diagnostics và instrumentation points phù hợp thay vì cố extract bytecode bằng unsupported internals.

### 12.8. Transformer exception không dừng toàn bộ pipeline

Một transformer ném `IllegalClassFormatException` không bảo đảm process class load bị abort; theo contract, exception từ transformer được xử lý như null transform về mặt pipeline, các transformers sau vẫn chạy. Với agent bắt buộc, cần thiết kế **explicit health/fail policy** tại điểm có thể quan sát kết quả, thay vì trông chờ throw trong transform là fail-closed.

## 13. Operational safety: quản lý agent, bytecode, logging và shutdown

### 13.1. Chỉ instrument classes được phép

Một agent có quyền rộng. Không nên dùng vòng lặp `getAllLoadedClasses()` để retransform mọi class. Lọc theo namespace, classloader/module, version, và tránh các classes của JVM hoặc chính agent vì recursive classloading/verification/synchronization risks.

### 13.2. Không gắn remote arbitrary transformer endpoint

Không cho client upload arbitrary .class/JAR và gọi `redefineClasses` trên process production. Bytecode là executable code; đây là bề mặt rủi ro cao. Nếu cần quản lý agents từ xa, dùng signed/trusted artifacts, authenticated admin workflow, authorization, audit, provenance và rollback plan.

### 13.3. Không dump bytecode thô vào logs

Classfile bytes có thể chứa source strings, business logic, internal endpoints hoặc một số dữ liệu nhạy cảm. Logs mặc định nên chứa **hash, major version, class identity, counts, reason code** thay vì toàn bộ byte arrays. Lưu snapshot original bytes nếu thực sự cần rollback, với encryption/retention/quota.

### 13.4. Performance của transformer

Transformers có thể được gọi trong critical path của class loading. Tránh:
- network I/O trong callback;
- load classes mới dễ tạo recursion;
- locks phức tạp;
- regex scans trên mọi class;
- cấp phát hàng trăm MB cho mỗi class;
- serializing full bytecode vào telemetry;
- synchronous remote config fetch.

Dùng fast allowlist filter (class internal name) trước khi parse/transform. Bài test chỉ patch `SampleTarget`; mỗi class khác trả null.

### 13.5. Startup -javaagent vs dynamic attach

Bài dùng **startup `-javaagent`**, được Java platform hỗ trợ rõ ràng. Dynamic agent loading có policy giới hạn hơn trên JDK hiện đại nhằm bảo vệ JVM integrity (JEP 451/JDK21 trở đi). Đừng thiết kế một bài test chỉ chạy nếu attach tự do được bật; khi cần attach, phải được admin cho phép và kiểm tra JDK/version.

### 13.6. Rollback và redeploy

Nếu transformer gây lỗi production:
- Disable/rollback agent artifact tại deployment control plane;
- Đừng chỉ gọi `removeTransformer` rồi giả định code đã khôi phục;
- Dùng controlled retransform/redefine **khi biết chắc** source bytes/pipeline/VM support;
- Nếu không thể khôi phục an toàn, **restart JVM với agent version đúng** có thể là giải pháp đơn giản và tin cậy hơn;
- Xác minh business behavior, health, latency và error rate sau rollback.

## 14. Bảng troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xác minh/khắc phục |
| --- | --- | --- |
| Không có agent-started | Manifest/Premain-Class/-javaagent sai | Kiểm tra command, JAR manifest và stderr |
| `ClassFileTransformer` không được gọi | Target đã load trước khi đăng ký; filter sai | Kiểm tra startup registration và internal class name |
| Callback đếm 1, behavior không đổi | Transformer trả null/bytes không được cài/inlining | Test method return + verify |
| `isModifiableClass==true` nhưng retransform failed | Agent thiếu capability/bytecode invalid | Check `isRetransformClassesSupported` và exception |
| `addTransformer(t,true)` failed | Missing Can-Retransform-Classes + JVM support | Dùng đúng manifest, test target JVM |
| `removeTransformer` returned true nhưng value vẫn changed | **Đúng contract**: chỉ deregister | Nếu cần restore, retransform/redefine có kế hoạch |
| `removeTransformer` returned false | Instance không registered / đã remove | Kiểm tra ownership, không tự ghi đè |
| Transformer vẫn nhận callback sau remove | Concurrency/in-flight definition | Defensive lifecycle, quiescence |
| Retransform không restore original | Non-capable previous transforms re-applied hoặc definition đã redefine | Xem pipeline và last redefinition provenance |
| Redefine original bytes không khôi phục | Wrong artifact/classloader hoặc transformer active | Verify exact bytes/class identity, disable conflicting transformers |
| `getResourceAsStream` null | No resource exposed/custom loader/generated class | Dùng known artifact path/callback provenance |
| Resource chứa ORIGINAL còn runtime MODIFIED | **Bình thường**: artifact khác installed definition | Test behavior, không nhầm nguồn |
| `ClassFile` import không compile trên JDK17 | Class-File API since Java24 | Use JDK24+ hoặc parser library cho 17 |
| Parser accepted basic header nhưng deeper traversal fails | Lazy parsing / malformed classfile | Walk relevant structures, handle IllegalArgumentException |
| Major version không phải 61 | Không compile `--release 17`/file khác | Check build target, artifact version |
| `ClassFormatError` khi transform | Bad constant pool/bytecodes/stack maps | Dùng valid parser/rewriter và isolated tests |
| `UnsupportedClassVersionError` | Classfile mới hơn runtime | Compile correct --release |
| `NoClassDefFoundError LabAgent$1` | Thiếu inner class trong agent JAR | Package compiled nested classes |
| `UnmodifiableClassException` | Class không eligible | Check target via isModifiableClass |
| Agent gây JVM slowdown | Transformer heavy/all classes | Allowlist, benchmark, lower overhead |
| Conflicts với agent thứ hai | Transformer order/definitions khác nhau | Integration tests, scope và version control |
| Active stack vẫn behavior cũ | Old frames continue old bytecodes | Test new invocations và business lifecycle |
| Static counter không reset sau redefine | Static state preserved | Tách state reset/migration khỏi class redefinition |
| Logging bytecode chứa secrets | Overcollection | Log hashes/provenance thay raw bytes |

## 15. Tình huống production: đừng nhầm khôi phục class và khôi phục hệ thống

Một service dùng agent thêm code đo duration vào `CheckoutService` có thể gặp performance regression. Kịch bản sai:

~~~text
1. removeTransformer(agentTransformer) returns true
2. Đặt status = "ROLLED_BACK"
3. Không test class behavior sau đó
4. Error rate vẫn tăng
~~~

Đây là **mẫu anti-pattern**, không phải log chạy thật. Vì transformed method vẫn có thể được JVM thực thi, status “rolled back” thiếu bằng chứng.

Quy trình đúng:

~~~text
1. Khoanh vùng class/method và agent version gây vấn đề
2. Xác minh quyền/capabilities, affected loaders và hashes
3. Quiesce/canary giảm rủi ro, chặn new rollout
4. Remove/disable transformer để ngăn tác động tương lai
5. Chọn restore strategy:
   - retransform trong known pipeline, hoặc
   - redefine với authentic baseline classfile, hoặc
   - restart/redeploy JVM nếu không thể đảm bảo
6. Test method behavior và business invariants
7. Quan sát latency/error/throughput/GC và log signals
8. Ghi audit trail và hướng rollback nếu regression quay lại
~~~

Đây là workflow, không phải Java code runnable. Không tự động rollback bằng cách inject arbitrary bytes không được kiểm tra. Với security-critical agent, missing instrumentation coverage cũng có thể yêu cầu **fail closed** thay vì “skip và tiếp tục” nếu chính sách xác định như vậy.

## 16. Câu hỏi tự đánh giá

**1.** `removeTransformer(transformer)` có hoàn tác class đang loaded không?

**Đáp án:** Không. Nó chỉ bỏ registration; class definition đã biến đổi vẫn có thể tồn tại.

**2.** `removeTransformer` trả true có nghĩa gì?

**Đáp án:** Một transformer registration phù hợp đã được tìm và gỡ; không khẳng định runtime bytes đã restore.

**3.** Transformer có thể được gọi sau khi remove không?

**Đáp án:** Có, do class loading concurrent/in-flight; phải viết defensive callbacks.

**4.** `transform(...)` trả `null` nghĩa gì?

**Đáp án:** Không đề xuất bytes thay thế từ transformer đó; không phải tự động fail class load.

**5.** Nếu transformer ném exception, JVM có dừng pipeline không?

**Đáp án:** Không nhất thiết; theo contract các transformers sau vẫn chạy, thrown exception có hiệu ứng như null transform về đầu ra.

**6.** `classfileBuffer` của transformer số hai luôn là original bytes?

**Đáp án:** Không, nó có thể là output của transformer số một.

**7.** Vì sao demo dùng `input.clone()`?

**Đáp án:** Để không mutate JVM-provided input buffer; transformer trả new bytes theo contract.

**8.** `retransformClasses` luôn restore artifact đầu tiên?

**Đáp án:** Không. Nó reapply non-retransform-capable transformations và capable transformers còn active theo rules; initial bytes có thể từ lần redefine mới nhất.

**9.** Trong demo, vì sao retransform sau remove restore được?

**Đáp án:** Chỉ có một capable transformer tác động target, đã remove; baseline vẫn là original compile bytes.

**10.** `redefineClasses` khác retransform thế nào?

**Đáp án:** Redefine cung cấp classfile bytes mới qua `ClassDefinition`; retransform chạy lại transformation pipeline.

**11.** Sau redefine, static fields có tự reset không?

**Đáp án:** Không; giá trị static state vẫn còn, class initializer không tự chạy lại.

**12.** Active stack frames có ngay lập tức chạy bytecode mới không?

**Đáp án:** Không bảo đảm; chúng có thể tiếp tục old bytecodes, new invocations thấy definition mới.

**13.** Vì sao `SampleTarget.class` resource có ORIGINAL trong khi method trả MODIFIED?

**Đáp án:** Resource là artifact trên classpath, không phải installed class definition đã transform.

**14.** Có public `Class#getClassFileBytes()` không?

**Đáp án:** Không. Reflection và getAllLoadedClasses không trả classfile bytes đang chạy.

**15.** Khi nào `getResourceAsStream("X.class")` trả null?

**Đáp án:** Có thể với custom/generated/hidden classes, loader không expose resource, module/resource policy hoặc file không còn.

**16.** Magic `CAFEBABE` có chứng minh classfile hợp lệ không?

**Đáp án:** Không. Nó chỉ là signature; cần parse/version/verify và metadata consistency.

**17.** Major version 61 tương ứng classfile target nào?

**Đáp án:** Java 17.

**18.** `ClassFile.of().parse(bytes)` được chuẩn hóa từ Java nào?

**Đáp án:** Java 24, không có trong Java 17 standard library.

**19.** Parser `ClassFile` đọc file có tự modify runtime JVM không?

**Đáp án:** Không. Nó chỉ tạo model từ bytes, cần Instrumentation/JVM capabilities để thay loaded class.

**20.** Vì sao demo patch chuỗi equal length?

**Đáp án:** Chỉ để giữ constant-pool layout trong controlled fixture; không phải cách transform production an toàn.

**21.** Vì sao cần đóng `LabAgent$1.class` vào agent JAR?

**Đáp án:** Vì transformer là anonymous inner class được compiler sinh riêng.

**22.** Nếu muốn sửa class đã loaded, đủ chỉ `addTransformer(t,true)` không?

**Đáp án:** Không. Phải thực hiện `retransformClasses` hoặc `redefineClasses` với điều kiện JVM hỗ trợ; addTransformer chỉ đăng ký callback.

**23.** Cần kiểm tra gì ngoài callback count?

**Đáp án:** Artifact integrity, class identity/loader, installed behavior, bytecode validity, errors và safe restore.

**24.** Multi-release JAR có thể khiến source bytes chọn nhầm không?

**Đáp án:** Có. Cần xác định runtime-selected class resource/version và defining loader.

**25.** Một agent nên dùng `getAllLoadedClasses()` rồi transform tất cả classes không?

**Đáp án:** Không. Phải allowlist targets, tránh unsupported/platform/hidden classes, có budget và security review.

**26.** Khi biến đổi gây lỗi nhưng restore không chắc chắn, cách ứng phó an toàn?

**Đáp án:** Dừng rollout và xem xét restart/redeploy với artifact sạch, xác minh behavior/metrics thay vì giả vờ removeTransformer đã rollback.

### Bài tập thực hành

1. Build `SampleTarget.java` và kiểm tra `javap -v` thấy major version 61.
2. Chạy `TransformationLifecycleDemo` với JDK17+, giải thích output ở từng giai đoạn.
3. Xóa gọi `retransformClasses` trong fixture, xem tại sao after-remove vẫn modified.
4. Đổi `removeTransformer` thành hai lần remove cùng object, kiểm tra true rồi false; thêm tests ở process riêng.
5. Đăng ký transformer `canRetransform=false` và một capable transformer, quan sát semantics reapplication (process test riêng).
6. Thử transformer return `null` thay bytes đã patch và đo behavior original.
7. Đổi target name filter sang tên không tồn tại, assert callback count/behavior đúng.
8. Thử chỉ đăng ký transformer sau khi `SampleTarget` đã loaded, rồi dùng `retransformClasses` để áp transform.
9. Thử in CRC32/SHA-256 của original resource và callback bytes thay vì in raw byte arrays.
10. Xóa `LabAgent$1.class` khỏi JAR thử nghiệm và giải thích packaging failure; không tác động production agent.
11. Build manifest thiếu `Can-Retransform-Classes`, kiểm tra capability và exception trong test isolate.
12. Build manifest thiếu `Can-Redefine-Classes`, kiểm tra redefine availability.
13. Chạy `ClassFileInspectionDemo` bằng JDK24+ và giải thích ClassModel.majorVersion.
14. Thử parse một byte array malformed, assert IllegalArgumentException.
15. Thêm kiểm tra name trong class model, không chỉ magic/version.
16. Đổi `SampleTarget` sang package `com.example.lab` và cập nhật resource path/internal name.
17. Tạo custom class loader cung cấp class bytes nhưng không expose resource; quan sát `getResourceAsStream==null`.
18. Tạo hai classloaders load same binary name với khác bytes, chứng minh provenance phải gắn với loader.
19. Chạy nhiều transformers với order xác định, kiểm tra input của transformer thứ hai.
20. Thiết kế test khi callback throws IllegalClassFormatException và xem class loading tiếp tục theo contract.
21. Làm integration test có active method frame khi redefine, ghi nhận old vs new invocations.
22. Thử redefinition bằng original bytes của sai class trong isolated JVM và bắt lỗi phù hợp.
23. Kiểm tra late callback race khi removeTransformer được gọi đồng thời class loading.
24. Thiết kế rollback playbook gồm tắt registration, restore/redeploy, post-rollback behavioral tests.
25. Kiểm tra Java17/21/24/26 compatibility, chỉ import java.lang.classfile ở module/tool Java24+.
26. Viết validation layer cho artifact SHA-256 + class name + major version trước khi redefine.
27. Đánh giá lợi ích của parser/rewriter chuẩn so với raw constant-pool byte find/replace.
28. Soát quyền truy cập file class bytes, audit và retention trong instrumentation agent của tổ chức.
29. Benchmark thời gian classloading của no-op transformer so với transformer phân tích tất cả classes.
30. Giữ một allowlist namespace/classLoader/module và assert ngoài allowlist không bị đổi behavior.

## 17. Tài liệu chính thức vẫn hiện hành

- [Oracle Java SE 26 — Instrumentation](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): add/remove transformers, retransform/redefine, capabilities, class eligibility, loaded classes.
- [Oracle Java SE 26 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback signatures, transform order, classfileBuffer ownership và null/exception semantics.
- [Oracle Java SE 26 — ClassDefinition](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): target class + replacement bytes.
- [Oracle Java SE 26 — IllegalClassFormatException](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/IllegalClassFormatException.html): malformed classfiles trong transform callback.
- [Oracle Java SE 26 — UnmodifiableClassException](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/UnmodifiableClassException.html): target classes bị giới hạn.
- [Oracle Java SE 26 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/26/docs/api/java.instrument/java/lang/instrument/package-summary.html): startup agent, manifests, dynamic attach policies.
- [Oracle Java SE 26 — ClassFile](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/ClassFile.html): Java24+ parse/build/transform API.
- [Oracle Java SE 26 — ClassModel](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/ClassModel.html): internal class name, majorVersion, fields/methods, lazy models.
- [Oracle Java SE 26 — java.lang.classfile package](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/classfile/package-summary.html): classfile reading/writing patterns, parser nuances.
- [Oracle Java SE 26 — ClassLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): class loading/resource lookup.
- [Oracle Java SE 26 — Class](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): reflection/runtime class identity.
- [Oracle Java SE 26 — Jar Tool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html): manifest/JAR packaging.
- [Oracle Java SE 26 — javap Tool](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html): bytecode and classfile disassembly.
- [Oracle Java SE 26 — Java Launcher](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): `-javaagent` startup.
- [Oracle Java SE 17 — Instrumentation](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): Java17 lab target availability.
- [Oracle Java SE 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): Java17 callback contract.
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484): Class-File API chuẩn từ Java 24.
- [JEP 451 — Prepare to Disallow Dynamic Agent Loading](https://openjdk.org/jeps/451): Java agent loading và JVM integrity.
- [JVMS SE 26 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html): magic, constant pool, versions, descriptors và classfile structure.
- [Java SE 26 — Java Virtual Machine Tool Interface](https://docs.oracle.com/en/java/javase/26/docs/specs/jvmti.html): JVM TI retransform/redefine constraints, native tooling contracts.

**Tóm tắt:** Để kiểm thử Java instrumentation đáng tin cậy, cần đo **(1) callback**, **(2) original/transformed bytes có nguồn gốc**, **(3) runtime method behavior** và **(4) rollback behavior**. `removeTransformer` chỉ gỡ registration, **không** sửa ngược classes đã loaded. `retransformClasses` có thể restore trong **controlled pipeline** nhưng phải hiểu reapplication của các transformers khác; `redefineClasses` có thể cài bytes gốc nếu source/provenance/capabilities hợp lệ. `Class.getResourceAsStream` đọc artifact chứ không cung cấp bảo đảm installed bytes. Với Java 24+, dùng **`ClassFile.of().parse(bytes)`** để đọc class file một cách có cấu trúc, còn Java17+ có thể dùng resource streams/`javap` và được kiểm thử độc lập qua agent startup. Luôn xử lý classloader/module/JDK versions, transformer concurrency, security và validation — không ngụy tạo rollback chỉ từ một dòng log “remove returned true”.
