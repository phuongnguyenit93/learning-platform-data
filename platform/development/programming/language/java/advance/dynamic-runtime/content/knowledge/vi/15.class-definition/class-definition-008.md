# 15.8 Định nghĩa trùng tên, sai phiên bản class file, VerifyError và LinkageError

**Module:** Java Advance - dynamic-runtime  
**Chủ đề cha:** 15. Định nghĩa lớp  
**Môi trường thực hành:** Java 17+ (biên dịch ví dụ bằng `javac --release 17`).  
**Trọng tâm:** định nghĩa lớp bằng `ClassLoader.defineClass`, định danh lớp runtime, kiểm tra version/format/bytecode, liên kết nhị phân và cách phân tích lỗi.

## 1. Mục tiêu học tập

Trong chương trình động, lớp có thể được biên dịch trước, đọc từ JAR, tải bằng nhiều `ClassLoader` hoặc sinh từ bytecode. Một class file hợp lệ về mặt **dữ liệu** chưa chắc hợp lệ về **luồng lệnh JVM**; một class tồn tại chưa chắc tương thích với class khác đã biên dịch từ phiên bản cũ; và cùng một **binary name** không bảo đảm chỉ có một kiểu runtime trên toàn JVM.

Hoàn thành bài này, bạn có thể:

1. Phân biệt **binary name**, **defining class loader**, **initiating loader**, `Class<?>` runtime identity và hậu quả của việc cùng tên khác loader.
2. Giải thích vì sao định nghĩa lại một binary name trong **cùng defining loader** bằng `defineClass` không tương đương với tải lại, và có thể ném `LinkageError`.
3. Đọc header class file: `0xCAFEBABE`, `minor_version`, `major_version`; kiểm tra sự phù hợp giữa JDK dùng để biên dịch và JVM dùng để chạy.
4. Phân biệt chính xác `UnsupportedClassVersionError`, `ClassFormatError`, `VerifyError` và các phân lớp khác của `LinkageError`.
5. Hiểu thứ tự logic **loading → linking (verification, preparation, resolution) → initialization**, cũng như lý do thời điểm quan sát lỗi có thể bị trì hoãn.
6. Biên dịch một demo Java 17+ tái hiện **định nghĩa trùng**, **version không hỗ trợ**, **class bytes hỏng**, **bytecode không xác minh được**, và **hai loader khác nhau có cùng tên lớp**.
7. Tái hiện `NoSuchMethodError` bằng cách biên dịch client với một API, rồi chạy với bản API không tương thích.
8. Chẩn đoán lỗi bằng `java -version`, `javac -version`, `javap -verbose`, classpath/module path và dấu vết class loading mà không “chữa” lỗi bằng cách tắt verifier.

## 2. Ngữ cảnh JVM: ba khái niệm tên lớp dễ bị trộn

### 2.1. Binary name trong class file

Mỗi class có tên nhị phân (binary name) như:

~~~text
com.example.plugin.UserTransformer
com.example.plugin.Outer$Inner
~~~

Tên nội bộ trong constant pool thường viết với dấu gạch chéo như `com/example/plugin/UserTransformer`. Class file lưu tên này trong cấu trúc `this_class`; khi `ClassLoader.defineClass` nhận `name == null`, JVM lấy tên thực từ class bytes.

`ClassLoader.defineClass(String name, byte[] b, int off, int len)` có thể dùng binary name mong đợi. Nếu `name` được chỉ định nhưng **không trùng binary name trong bytes**, JVM có thể ném `NoClassDefFoundError` dạng “wrong name”. Đây **không giống** lỗi định nghĩa trùng.

Tách rõ:

- **Tên file `UserTransformer.class`**: cách phổ biến để lưu dữ liệu; bản thân tên file không tạo identity.
- **Binary name**: `com.example.plugin.UserTransformer` nằm trong class file.
- **Object `Class<?>`**: kiểu đã được JVM định nghĩa, có thông tin class loader/module thực tế.

### 2.2. Identity runtime không chỉ là một chuỗi tên

Với các kiểu tham chiếu thông thường được class loader định nghĩa, JVM nhận diện type theo **binary name + defining loader**. Hai loader riêng có thể định nghĩa class cùng binary name và nhận hai `Class<?>` **khác nhau**:

~~~text
loader A -> class com.example.Message -> Class object A
loader B -> class com.example.Message -> Class object B

A.getName().equals(B.getName()) == true
A == B                               == false
~~~

Điều này tự nó **không phải lỗi định nghĩa trùng**, vì hai loader có namespace định nghĩa khác nhau. Nhưng có hệ quả:

- Một object tạo từ type của loader B **không tự cast** được sang type cùng tên của loader A.
- Hai interface có cùng binary name do hai loader định nghĩa có thể không tương thích trong plugin system.
- Signature method đi qua hai hệ loader có thể vi phạm **loader constraints** của JVM; một số trường hợp ném `LinkageError` với thông tin loader constraint violation.
- Nếu muốn host/plugin giao tiếp bằng cùng một SPI, cần cho cả hai dùng **đúng một định nghĩa SPI** qua class loader/module topology có chủ đích, không chỉ sao chép JAR tên giống nhau.

**Đừng đánh đồng:** “loader A/B cùng định nghĩa tên X” khác “một loader A cố `defineClass` tên X lần thứ hai”.

### 2.3. Defining loader và initiating loader

**Defining loader** là loader thực hiện định nghĩa class từ bytes. **Initiating loader** là loader được JVM ghi nhận là đã tham gia yêu cầu nạp kiểu đó; qua parent delegation, initiating loader không nhất thiết là defining loader.

Theo cách thực thi mặc định của `ClassLoader.loadClass(name, resolve)`:

1. Hỏi `findLoadedClass(name)` xem tên đó đã được loader này ghi nhận chưa.
2. Thử **parent loader**.
3. Nếu parent không tìm thấy, gọi `findClass(name)` để loader hiện tại định nghĩa.
4. Nếu được yêu cầu, gọi `resolveClass`.

Vì thế **hai lần gọi `loadClass("X")` đúng chuẩn không có nghĩa hai lần `defineClass("X")`**. `loadClass` có caching/ủy quyền và đồng bộ theo khóa loading của class. Trong demo dưới đây, ta **cố tình gọi trực tiếp wrapper của `defineClass`** hai lần để minh họa JVM từ chối định nghĩa trùng; đó không phải mẫu triển khai loader production.

## 3. Vòng đời lớp: lỗi xuất hiện ở pha nào?

Mô hình khái niệm:

~~~text
Đọc class bytes / tìm định nghĩa
        |
        v
LOADING: tạo hoặc tìm Class object, kiểm tra cấu trúc cần thiết
        |
        v
LINKING:
    - verification: kiểm tra kiểu và tính hợp lệ của bytecode
    - preparation: chuẩn bị vùng static fields với giá trị mặc định
    - resolution: nối symbolic references đến lớp/member thực
        |
        v
INITIALIZATION: chạy static initializer / thiết lập static state
        |
        v
USAGE: khởi tạo instance, gọi method, truy cập field
~~~

Không suy diễn từ sơ đồ rằng mọi JVM phải thực hiện **toàn bộ resolution** vào một thời điểm duy nhất trước khi dùng class. Resolution của các symbolic references có thể được tiến hành sớm hoặc muộn theo quy tắc JVM; verification của một class cũng có thể trở nên quan sát được khi class được **resolve/active-use/reflective-use**, tùy cơ chế cụ thể.

Điều này quan trọng trong debug: stack trace ở `Class.forName`, `ClassLoader.defineClass`, `getDeclaredMethod` hoặc một lần gọi method **không đủ** để kết luận lỗi được *tạo ra tại dòng source đó*. Nhiều khi đó là điểm JVM buộc phải load/link một class phụ thuộc đã không còn hợp lệ.

### 3.1. Đừng nhầm compile-time và runtime

- **Compile-time (`javac`):** source được kiểm tra dựa trên dependency mà compiler đang thấy, tạo bytecode và symbolic references.
- **Runtime (`java`):** JVM nạp những artifact thực tế có trên classpath/module path. Chúng **có thể khác version** so với khi build.
- **Class loading:** bytes có thể lấy từ đĩa, archive, network, generated code, hoặc custom loader.
- **Linking:** JVM phải tin classfile và các liên kết của nó là hợp lệ; một lỗi có thể chỉ lộ ra khi method cụ thể được dùng.

Compile thành công không bảo đảm runtime classpath chứa binary compatible dependencies.

## 4. `LinkageError` là họ lỗi, không phải một nguyên nhân duy nhất

`java.lang.LinkageError` là subclass của `Error`, và chứa nhiều lỗi liên quan tới định nghĩa/liên kết/thực thi lớp đã biên dịch. Nó không phải checked exception như `ClassNotFoundException`.

~~~text
java.lang.Error
  |
  +-- LinkageError
       |
       +-- ClassFormatError
       |     +-- UnsupportedClassVersionError
       +-- VerifyError
       +-- NoClassDefFoundError
       +-- IncompatibleClassChangeError
       |     +-- NoSuchMethodError
       |     +-- NoSuchFieldError
       |     +-- AbstractMethodError
       |     +-- IllegalAccessError
       +-- ClassCircularityError
       +-- BootstrapMethodError
       +-- ExceptionInInitializerError
       +-- UnsatisfiedLinkError
~~~

*Đây là sơ đồ phân cấp một số loại lỗi thường gặp*, không phải danh sách đầy đủ mọi subclass hoặc mọi tình huống. Các phân lớp mô tả **nhiều cơ chế thất bại khác nhau**; hãy đọc loại cụ thể thay vì chỉ biết chung “LinkageError”.

| Loại | Tầng thường liên quan | Dấu hiệu điển hình |
| --- | --- | --- |
| `LinkageError` trực tiếp | Định nghĩa/liên kết bị xung đột | Một defining loader cố định nghĩa cùng binary name lần thứ hai; loader constraint violation |
| `UnsupportedClassVersionError` | Classfile format/version | JVM không hỗ trợ `major_version`/`minor_version` |
| `ClassFormatError` | Đọc cấu trúc class file | Magic/header/constant pool/attribute sai hoặc class bytes hỏng |
| `VerifyError` | Bytecode verification | Classfile đủ cấu trúc cơ bản nhưng operand stack/local types/frames không hợp lệ |
| `NoClassDefFoundError` | JVM cần class nhưng không có định nghĩa thích hợp, hoặc class từng khởi tạo lỗi | Runtime thiếu dependency, tên không khớp, hoặc trạng thái erroneous của class |
| `NoSuchMethodError` | Resolution của method reference | Client được biên dịch với method có ở API v1, runtime lại thấy API v2 không có method đó |
| `NoSuchFieldError` | Resolution của field reference | Field đã bị xóa/đổi tên/type theo binary contract |
| `AbstractMethodError` | Lời gọi method không có implementation có thể sử dụng | Thay đổi interface/class làm binary implementation cũ không còn hợp lệ |
| `IllegalAccessError` | Runtime access checking | Member/package/module không còn accessible theo liên kết runtime |
| `IncompatibleClassChangeError` | Member/class kinds và binary API không khớp | Từ instance thành static hoặc thay class thành interface |
| `BootstrapMethodError` | Liên kết `invokedynamic`/dynamic constants | Bootstrap không tạo linkage hợp lệ |
| `ExceptionInInitializerError` | Khởi tạo class | Static initializer ném exception không phải Error |
| `UnsatisfiedLinkError` | Native library/method linkage | Thiếu native library hoặc symbol JNI thích hợp |

**Phân biệt đặc biệt:** `UnsupportedClassVersionError extends ClassFormatError extends LinkageError`. Còn `VerifyError extends LinkageError` **trực tiếp**, không qua `ClassFormatError`. Do đó một câu lệnh `catch(ClassFormatError e)` có thể bắt cả unsupported version, nhưng **không bắt VerifyError**.

Không nên dùng `catch(LinkageError e)` để nuốt mọi lỗi rồi tiếp tục với class loader đang có trạng thái không chắc chắn. Đây thường là lỗi **cấu hình/build/artifact/ABI nghiêm trọng**; cần thu thập chẩn đoán, cô lập plugin thất bại và dừng đường thực thi có vấn đề.

## 5. Class file version: major/minor và `UnsupportedClassVersionError`

### 5.1. Header class file

Cấu trúc đầu của một class file JVM:

~~~text
byte offset    0  1  2  3 | 4  5 | 6  7
giá trị        CA FE BA BE | minor | major
               magic        u2      u2
~~~

- `magic=0xCAFEBABE`: marker nhận dạng class file.
- `minor_version` và `major_version`: hai số nguyên **unsigned 16-bit big-endian**, mô tả version class format.
- Các mục tiếp theo gồm constant pool, modifiers, superclass/interfaces, methods và attributes.

Ví dụ ánh xạ phổ biến:

| Java release | Class file major |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

JVM Java 17 hỗ trợ classfile major đến **61**, không nạp được classfile major 65 của Java 21. Trường hợp đó có thể phát sinh `UnsupportedClassVersionError`. Ví dụ demo bên dưới **cố ý chỉnh major thành 99** cho chắc chắn không được hỗ trợ ở JDK dùng để thử, **không phải** một phiên bản Java release thực tế.

Từ class file major 56 trở lên, minor thường là `0` hoặc `65535` theo định dạng; minor `65535` liên quan **preview features** và có thêm quy tắc chỉ được nạp trên JVM đúng release với preview được bật. Không chỉ kiểm tra mỗi major mà bỏ qua minor trong mọi trường hợp.

### 5.2. Cách nhận diện đúng phiên bản

Kiểm tra công cụ thực sự đang được dùng:

~~~bash
java -version
javac -version
~~~

Kiểm tra class file đã build:

~~~bash
javap -verbose -classpath out 'ClassDefinitionFailureDemo$Good'
~~~

Tìm dòng:

~~~text
major version: 61
~~~

Các lệnh dùng tên nested class có ký tự `$` nên ví dụ đặt tên trong **dấu nháy đơn**. Nếu dùng Windows PowerShell, dấu nháy đơn cũng giữ nguyên ký tự `$`. Đừng chỉ dựa vào `pom.xml`/`build.gradle`: artifact chạy thực tế có thể được lấy từ cache, Docker image, shaded JAR, multi-release JAR hoặc một dependency khác.

### 5.3. Sửa đúng lỗi unsupported version

- Nếu **runtime cũ** nhưng artifact được biên dịch bằng Java mới, nâng runtime theo chính sách phát hành **hoặc** build lại bằng một release được hỗ trợ.
- Với JDK 17+ và mục tiêu Java 17: `javac --release 17 ...`. Cờ này chọn ngôn ngữ, classfile version **và** API nền tảng phù hợp với release đích.
- Đừng tưởng `--source 17 --target 17` luôn tương đương `--release 17` ở khả năng bảo đảm chỉ dùng API của Java 17 khi compiler đang chạy trên JDK mới.
- Đừng chỉnh tay byte major xuống 61 trong artifact sản xuất: bytecode vẫn có thể dùng opcode, constant pool tags, classfile features hoặc API mới không tương thích. Demo đổi bytes **chỉ để tạo lỗi có kiểm soát**.
- Nếu dùng preview features, cấu hình Java release/`--enable-preview` tương ứng; không coi `--release` đơn thuần là giải pháp cho mọi preview class.

## 6. Định nghĩa trùng tên trong cùng loader

### 6.1. `defineClass` tạo class, không “đổi method của class đã có”

Giả sử một custom loader đã thực hiện:

~~~java
Class<?> first = defineClass(
        "demo.Dynamic", validBytes, 0, validBytes.length);
~~~

Đoạn này chỉ là **minh họa bên trong subclass `ClassLoader`** có quyền gọi protected method; `validBytes` là classfile bytes đúng binary name. Nếu loader **cố định nghĩa lần nữa** cùng tên trong chính loader ấy, JVM có thể ném `LinkageError` trực tiếp vì “attempted duplicate class definition”.

Đây không phải một cơ chế hot reload. Một object `Class<?>` đã được định nghĩa không thể được thay bằng `defineClass` lần thứ hai trong cùng loader.

### 6.2. Hai cách xử lý hợp lệ khi có yêu cầu reload

**Nếu chỉ muốn dùng lại class đã nạp:** sử dụng `loadClass` với cache/parent delegation; mặc định `ClassLoader.loadClass` đã có logic `findLoadedClass`. Custom loader thường chỉ override `findClass`, không gọi `defineClass` mỗi lần được yêu cầu.

**Nếu thực sự cần một phiên bản class khác cùng tên:** có thể tạo **class loader mới** để định nghĩa phiên bản mới. Nhưng object từ loader cũ và mới có **kiểu runtime khác nhau**, có thể gây `ClassCastException`, duplicate service contracts, loader constraints, giữ tài nguyên hoặc classloader leak. Cần tách ranh giới giao tiếp qua API/SPI chung và quản lý lifecycle.

**Instrumentation:** `java.lang.instrument.Instrumentation.redefineClasses`/`retransformClasses` là cơ chế chuyên biệt khác, có giới hạn (không phải mọi thay đổi cấu trúc class đều được hỗ trợ). Nó **không** tương đương với gọi `defineClass` lần thứ hai. Đừng nêu nó như giải pháp mặc định cho mọi plugin hot swap.

### 6.3. Class loading race và quy tắc đồng bộ

Nếu hai thread đồng thời yêu cầu định nghĩa cùng tên:

- Dùng cơ chế `loadClass` chuẩn và khóa `getClassLoadingLock(name)` phù hợp; JVM cũng cần bảo vệ namespace định nghĩa.
- Tránh “check-then-define” không đồng bộ: hai thread cùng thấy class chưa có rồi cả hai `defineClass`.
- Loader parallel-capable có quy tắc đăng ký và locking riêng; không tự chế synchronization khi không hiểu mô hình.
- Không bắt `LinkageError` rồi giả định class thứ hai “đã được nạp thành công”: hãy phân biệt xung đột do racing thread với classfile/loader constraints khác.

## 7. `ClassFormatError` và `VerifyError` khác nhau thế nào?

### 7.1. Format checking: classfile có thể được giải mã không?

Ví dụ class bytes có magic sai:

~~~text
trước: CA FE BA BE ...
sau:   00 FE BA BE ...
~~~

Khi JVM đọc bytes không còn header classfile hợp lệ, lỗi phù hợp là **`ClassFormatError`**. Các lỗi khác có thể phát sinh khi constant pool, attribute, metadata hoặc kích thước classfile sai cấu trúc.

**`UnsupportedClassVersionError`** là trường hợp version classfile không được hỗ trợ và nằm **bên dưới `ClassFormatError` trong cây kế thừa**. Thông điệp lỗi có thể chứa “class file version X” và “runtime recognizes up to Y”, nhưng **không** dựa vào text message làm API contract ổn định.

### 7.2. Verification: bytecode có an toàn theo type system JVM không?

Một classfile có thể có **magic đúng, version được hỗ trợ, constant pool hợp lệ**, nhưng code bên trong lại vi phạm type safety:

- `iadd` yêu cầu lấy **hai `int`** từ operand stack; `ladd` yêu cầu **hai `long`**.
- `ireturn` cần `int`, `areturn` cần reference; return opcode phải phù hợp method descriptor.
- Local variables có type không phù hợp với lệnh load/store.
- Điều khiển nhảy tới offset không hợp lệ, stack height/stack map frames không nhất quán, dùng object chưa khởi tạo sai quy tắc.
- Một tool sửa bytecode (instrumentation/obfuscator/generator) làm sai `StackMapTable` hoặc frames cho Java classfile hiện đại.

Ví dụ method:

~~~java
public static int addOne(int n) {
    return n + 1;
}
~~~

Với `javac --release 17`, dãy bytecode cho method này có thể là:

~~~text
iload_0
iconst_1
iadd
ireturn
~~~

Trong demo được thử nghiệm, ta thay **một byte opcode `iadd (0x60)`** thành **`ladd (0x61)`**, trong khi trước đó stack chứa hai int. Classfile vẫn có cấu trúc cơ bản, nhưng phương thức **không thể verify** → `VerifyError`.

Đây là minh họa để hiểu verifier; **không phải hướng dẫn chỉnh sửa artifact thật**. Không chỉnh bytes của thư viện production hoặc bỏ verifier để “làm nó chạy”. Nếu dùng ASM/Byte Buddy/agent, cần bảo đảm **bytecode shape, operand stack, local frames, stack map** hợp lệ và version phù hợp.

### 7.3. Không xác định pha chỉ dựa vào nơi ném lỗi

JVM có thể làm format checks khi định nghĩa class và verify ở thời điểm liên kết/đòi hỏi dùng class. Trong demo, code cố tìm method bằng Reflection sau `defineClass` để kích hoạt verification nếu nó chưa diễn ra. **Không cam kết `VerifyError` luôn ném chính tại `defineClass`** cho mọi JVM.

`javac` thường tạo bytecode hợp lệ. Nếu thấy `VerifyError` sau instrumentation, shading hoặc bytecode enhancement, cần xem **bytes cuối cùng JVM thực sự nhận**, không chỉ source Java ban đầu.

## 8. Demo Java 17: tái hiện bốn loại lỗi trong một file

Chương trình hoàn chỉnh:

- Đọc bytes của **nested class đã biên dịch**.
- Định nghĩa một binary name bằng custom loader, rồi thử `defineClass` lần thứ hai **trong cùng loader**.
- Định nghĩa cùng tên từ **loader khác** và so sánh runtime identity.
- Thay `major_version` thành 99 → `UnsupportedClassVersionError`.
- Sửa magic byte đầu → `ClassFormatError`.
- Sửa `iadd` thành `ladd` trên một method đơn giản → `VerifyError`.
- Kiểm tra mối quan hệ superclass giữa các error types.

**Tệp chạy độc lập:** `ClassDefinitionFailureDemo.java`

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;

public final class ClassDefinitionFailureDemo {
    public static final class Good {
        public static String message() { return "ok"; }
    }

    public static final class Arithmetic {
        public static int addOne(int n) { return n + 1; }
    }

    private static final class RawLoader extends ClassLoader {
        RawLoader() {
            super(ClassDefinitionFailureDemo.class.getClassLoader());
        }
        Class<?> defineRaw(byte[] bytes) {
            return defineClass(null, bytes, 0, bytes.length);
        }
    }

    private static byte[] classBytes(Class<?> type) throws IOException {
        String resource = type.getName().replace('.', '/') + ".class";
        try (InputStream input = ClassDefinitionFailureDemo.class
                .getClassLoader().getResourceAsStream(resource)) {
            if (input == null) {
                throw new IOException("Missing resource: " + resource);
            }
            return input.readAllBytes();
        }
    }

    private static int locate(byte[] bytes, byte[] pattern) {
        int found = -1;
        for (int i = 0; i <= bytes.length - pattern.length; i++) {
            boolean match = true;
            for (int j = 0; j < pattern.length; j++) {
                if (bytes[i + j] != pattern[j]) {
                    match = false;
                    break;
                }
            }
            if (match) {
                if (found >= 0) {
                    throw new IllegalStateException("Bytecode pattern not unique");
                }
                found = i;
            }
        }
        if (found < 0) {
            throw new IllegalStateException("Bytecode pattern absent");
        }
        return found;
    }

    public static void main(String[] args) throws Exception {
        byte[] good = classBytes(Good.class);
        int major = ((good[6] & 0xff) << 8) | (good[7] & 0xff);
        System.out.println("classFileMajor=" + major);

        RawLoader firstLoader = new RawLoader();
        Class<?> first = firstLoader.defineRaw(good);
        System.out.println("first=" + first.getName());

        try {
            firstLoader.defineRaw(good);
            System.out.println("duplicate=unexpected");
        } catch (LinkageError expected) {
            System.out.println("duplicate=" + expected.getClass().getSimpleName());
        }

        Class<?> peer = new RawLoader().defineRaw(good);
        System.out.println("sameBinaryName=" +
                first.getName().equals(peer.getName()));
        System.out.println("sameRuntimeClass=" + (first == peer));

        byte[] tooNew = good.clone();
        tooNew[6] = 0;
        tooNew[7] = 99;
        try {
            new RawLoader().defineRaw(tooNew);
            System.out.println("version=unexpected");
        } catch (UnsupportedClassVersionError expected) {
            System.out.println("version=" + expected.getClass().getSimpleName());
        }

        byte[] badFormat = good.clone();
        badFormat[0] = 0;
        try {
            new RawLoader().defineRaw(badFormat);
            System.out.println("format=unexpected");
        } catch (ClassFormatError expected) {
            System.out.println("format=" + expected.getClass().getSimpleName());
        }

        byte[] broken = classBytes(Arithmetic.class);
        byte[] instructions = {(byte) 0x1a, (byte) 0x04, (byte) 0x60, (byte) 0xac};
        int offset = locate(broken, instructions);
        broken[offset + 2] = (byte) 0x61; // iadd -> ladd; stack holds two ints
        try {
            Class<?> invalid = new RawLoader().defineRaw(broken);
            Method method = invalid.getDeclaredMethod("addOne", int.class);
            method.invoke(null, 1);
            System.out.println("verify=unexpected");
        } catch (VerifyError expected) {
            System.out.println("verify=" + expected.getClass().getSimpleName());
        }

        System.out.println("versionIsLinkage=" +
                (UnsupportedClassVersionError.class.getSuperclass()
                        == ClassFormatError.class));
        System.out.println("verifyIsLinkage=" +
                (VerifyError.class.getSuperclass() == LinkageError.class));
        System.out.println("formatIsLinkage=" +
                (ClassFormatError.class.getSuperclass() == LinkageError.class));
    }
}
~~~

### 8.1. Biên dịch và chạy

Lưu đúng tên file `ClassDefinitionFailureDemo.java`, dùng JDK 17 trở lên:

~~~bash
javac --release 17 -d out ClassDefinitionFailureDemo.java
java -cp out ClassDefinitionFailureDemo
~~~

Lệnh trên hoạt động khi chạy từ thư mục chứa source; `javac -d out` tạo thư mục output nếu chưa tồn tại. Các class phụ `Good`/`Arithmetic` do `javac` tạo cùng thư mục classpath; helper `classBytes` đọc chúng qua resource stream.

**Stdout đã kiểm chứng của chương trình:**

~~~text
classFileMajor=61
first=ClassDefinitionFailureDemo$Good
duplicate=LinkageError
sameBinaryName=true
sameRuntimeClass=false
version=UnsupportedClassVersionError
format=ClassFormatError
verify=VerifyError
versionIsLinkage=true
verifyIsLinkage=true
formatIsLinkage=true
~~~

Demo đã được biên dịch bằng `javac --release 17` và chạy thành công trên JVM thử nghiệm, đồng thời `javap -verbose` xác nhận classfile major 61.

### 8.2. Vì sao demo dùng `defineClass(null, ...)`?

Đây là trường hợp thử nghiệm có chủ đích:

- `name=null` cho JVM lấy binary name từ class bytes; nhờ vậy không cần biết tên nested class trước khi gọi.
- Hàm `defineRaw` **bỏ qua parent delegation** và gọi `defineClass` trực tiếp, cho phép chủ động tạo lỗi trùng tên trong **cùng loader**.
- Loader production thường sử dụng `findClass` trong mô hình `loadClass`; không nên copy `defineRaw` làm cách “reload” lớp.
- Mỗi thử nghiệm bytes bị chỉnh dùng **một instance `RawLoader` mới** để lỗi cần kiểm tra không bị nhầm với lỗi duplicate của thử nghiệm trước.
- Classfile bytes chỉ được clone và sửa **trong RAM**. Chương trình không ghi đè JAR/class file của dự án.

### 8.3. Giải thích từng dòng kết quả

**`classFileMajor=61`:** `javac --release 17` tạo class file format tương ứng Java 17.

**`duplicate=LinkageError`:** `firstLoader` đã định nghĩa `ClassDefinitionFailureDemo$Good` một lần; lần định nghĩa thứ hai với cùng binary name và defining loader bị JVM từ chối.

**`sameBinaryName=true`, `sameRuntimeClass=false`:** hai `RawLoader` khác nhau định nghĩa cùng bytes, cùng tên, nhưng trả hai object `Class<?>` khác nhau. Không có `LinkageError` chỉ vì hai loader độc lập dùng cùng tên.

**`version=UnsupportedClassVersionError`:** byte offset 6–7 bị đặt thành major 99, không được JVM đang chạy hỗ trợ. Đây là **lỗi version**, không phải VerifyError.

**`format=ClassFormatError`:** byte đầu của magic `CAFEBABE` bị sửa, khiến format không còn được nhận diện.

**`verify=VerifyError`:** classfile `Arithmetic` vẫn chứa cấu trúc file nhưng method `addOne` có opcode `ladd` trong lúc operand stack nắm hai int. Verifier từ chối method; chương trình bắt đúng loại lỗi ở pha link/use.

**Ba dòng `...IsLinkage=true`:** thể hiện quan hệ superclass trực tiếp:
- `UnsupportedClassVersionError` có superclass `ClassFormatError`;
- `ClassFormatError` và `VerifyError` có superclass `LinkageError`.

### 8.4. Lưu ý khi chỉnh bytecode minh họa

Hàm `locate` tìm đúng **một** chuỗi bytes `1a 04 60 ac` trong toàn bộ classfile đã được `javac --release 17` tạo. Đây là cách đơn giản có kiểm tra trùng/thiếu để kiểm thử class ngắn. Nó **không phải parser classfile tổng quát**: đổi compiler, đổi optimization/bytecode, hoặc thay method `addOne` có thể làm mẫu bytes biến mất.

Trong hệ thống thật, nếu cần sửa bytecode, dùng công cụ hiểu cấu trúc `Code`, constant pool và `StackMapTable`, đồng thời chạy verification/test đầy đủ. Mục tiêu demo là **phân biệt lỗi**, không hướng dẫn bytecode patch production.

## 9. Demo thứ hai: compile với API v1, chạy với API v2 gây `NoSuchMethodError`

Ví dụ trên cho thấy lỗi ngay khi định nghĩa/verify. Bây giờ hãy phân biệt với **binary compatibility**: source code được biên dịch hợp lệ, class file đều hợp lệ, nhưng runtime cung cấp một dependency đã thay đổi method.

Tạo cây:

~~~text
src-v1/sample/Api.java
src-v2/sample/Api.java
src-client/sample/Client.java
~~~

### 9.1. API v1

**File `src-v1/sample/Api.java`:**

~~~java
package sample;

public final class Api {
    public static String greet() {
        return "hello-v1";
    }
}
~~~

### 9.2. API v2 không còn method `greet()`

**File `src-v2/sample/Api.java`:**

~~~java
package sample;

public final class Api {
    public static String speak() {
        return "hello-v2";
    }
}
~~~

### 9.3. Client được biên dịch **chỉ với v1**

**File `src-client/sample/Client.java`:**

~~~java
package sample;

public final class Client {
    public static void main(String[] args) {
        System.out.println(Api.greet());
    }
}
~~~

Client bytecode có symbolic method reference tới `sample.Api.greet:()Ljava/lang/String;`. Mã này biên dịch được khi compiler thấy API v1. API v2 vẫn có class `sample.Api`, nhưng **không có method** tên `greet` theo descriptor đó.

### 9.4. Build và chạy trên Windows PowerShell

Từ thư mục chứa ba cây nguồn:

~~~powershell
javac --release 17 -d build/v1 src-v1/sample/Api.java
javac --release 17 -d build/v2 src-v2/sample/Api.java
javac --release 17 -cp build/v1 -d build/client src-client/sample/Client.java
java -cp "build/v1;build/client" sample.Client
java -cp "build/v2;build/client" sample.Client
~~~

### 9.5. Build và chạy trên Bash (Linux/macOS)

~~~bash
javac --release 17 -d build/v1 src-v1/sample/Api.java
javac --release 17 -d build/v2 src-v2/sample/Api.java
javac --release 17 -cp build/v1 -d build/client src-client/sample/Client.java
java -cp "build/v1:build/client" sample.Client
java -cp "build/v2:build/client" sample.Client
~~~

**Với v1**, chương trình in chính xác:

~~~text
hello-v1
~~~

**Với v2**, chương trình kết thúc lỗi; dòng quan trọng trong stack trace có dạng:

~~~text
java.lang.NoSuchMethodError: ... sample.Api.greet() ...
~~~

Dấu `...` nghĩa là **message minh họa**, không phải stdout đầy đủ cần so khớp; JVM có thể trình bày descriptor và dấu nháy khác nhau. Thử nghiệm đã xác nhận loại lỗi thực là **`NoSuchMethodError`**.

### 9.6. Điều gì khác với “định nghĩa trùng”?

Ở **mỗi lần chạy** ví dụ v1/v2, app loader chỉ nạp **một** bản `sample.Api` theo classpath được cung cấp. Không có cố gắng `defineClass` trùng trong cùng loader. Vấn đề là **client binary yêu cầu method đã không còn ở dependency runtime**.

Nếu **biên dịch lại client** với v2, `javac` sẽ phát hiện lỗi source vì `Api.greet()` không tồn tại. Nhưng binary client cũ chỉ lộ lỗi ở runtime khi JVM resolve/call method reference.

Kỹ thuật phòng ngừa: kiểm thử **binary compatibility**, đồng bộ dependency versions và classpath, tránh phân phối client cũ kèm API mới làm phá vỡ ABI. Đổi `greet` thành `speak` là một API breaking change ngay cả khi hai method thực hiện nghiệp vụ tương tự.

## 10. Phân biệt `ClassNotFoundException` và `NoClassDefFoundError`

Hai tên thường bị nhầm:

- **`ClassNotFoundException`** là **checked exception** từ yêu cầu tìm class tường minh như `Class.forName("...")` hoặc `ClassLoader.loadClass("...")` khi loader không tìm thấy tên được yêu cầu.
- **`NoClassDefFoundError`** là **`LinkageError`**, xuất hiện khi JVM không thể lấy một định nghĩa class cần thiết theo tiến trình liên kết/thực thi. Ví dụ binary thiếu dependency lúc chạy, tên class được yêu cầu không khớp bytes, hoặc một class rơi vào trạng thái erroneous sau lỗi khởi tạo.

Không đủ căn cứ để suy ngược “`NoClassDefFoundError` luôn nghĩa là chưa có file `.class` trên đĩa”. Nó cũng có thể liên quan class loader, classpath/module path, thiếu một dependency *của* class đó hoặc initialization failure.

Ví dụ một dòng `Class.forName("no.such.Plugin")` có thể ném `ClassNotFoundException` khi không có class phù hợp; ngược lại, mã bytecode gọi vào một class từng có lúc biên dịch nhưng thiếu ở runtime có thể ném `NoClassDefFoundError`. Hai biểu hiện đến từ **cách JVM yêu cầu và resolve class**, không chỉ câu chữ “class not found”.

## 11. Chẩn đoán lỗi theo trình tự có thể tái lập

### 11.1. Xác định artifact, class loader và JVM thật

1. Ghi **lệnh `java` đang chạy**, `java -version`, `javac -version` và cấu hình runtime trong Docker/service/IDE/CI. JDK để build và JRE/JVM để chạy có thể không cùng phiên bản.
2. Xác định class đang nạp từ JAR/thư mục nào; kiểm tra **classpath order**, module path, shaded/fat JAR, plugin bundle và version của dependency.
3. Xem classfile header: `javap -verbose -classpath <đường-dẫn> com.example.Type`, tìm `major version`. Với JAR, dùng `jar tf file.jar` để tìm entry thực tế trước.
4. Nếu có custom loader, in binary name và defining loader identity. Đừng chỉ in tên class. Gợi ý:

~~~java
Class<?> type = someObject.getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
System.out.println(type.getModule());
System.out.println(type.getProtectionDomain().getCodeSource());
~~~

Đoạn mã này giả định `someObject` đã có và chỉ dùng để **chẩn đoán trong môi trường được phép**; `getCodeSource()` có thể là `null` với class sinh động, nên không được coi là một trường luôn tồn tại. Log có thể lộ đường dẫn nội bộ — bảo vệ log production phù hợp.

### 11.2. Tách lỗi theo loại

| Dấu hiệu đầu tiên | Hướng điều tra |
| --- | --- |
| `LinkageError: attempted duplicate class definition` | Loader nào gọi `defineClass` lần hai? `findLoadedClass`/`loadClass`/race/parallel-capable? |
| `UnsupportedClassVersionError` | Major/minor của class bytes so với runtime; JDK build khác JDK run? Có preview? |
| `ClassFormatError` | Class bytes bị truncate/hỏng, jar corruption, constant pool/attribute patch? |
| `VerifyError` | Bytecode cuối cùng, frames, stack/local types, classfile generator/agent/obfuscator |
| `NoSuchMethodError` hoặc `NoSuchFieldError` | Client được build theo API nào? Runtime dependency version/ABI thật là gì? |
| `AbstractMethodError` | Contract interface/class thay đổi nhưng provider binary cũ chưa rebuild? |
| `IllegalAccessError` | Quyền runtime đã đổi, class/member modifiers, module exports? |
| `NoClassDefFoundError` | Class cần thiết thiếu ở runtime, wrong-name, initialization failure, class loader topology |
| `ClassCastException` với cùng tên binary | Defining loader khác nhau tạo class identity khác; không nhất thiết là define duplicate |
| `BootstrapMethodError` | `invokedynamic` bootstrap/metafactory có signature/linkage/permission hợp lệ không? |

### 11.3. Các lệnh chẩn đoán hữu ích

~~~bash
java -version
javac -version
javap -verbose -classpath out com.example.Type
jar tf application.jar
~~~

`out`, `com.example.Type` và `application.jar` là **ví dụ tên placeholder cho thao tác chẩn đoán**, không phải đường dẫn buộc phải tồn tại trong demo. Với HotSpot JVM hỗ trợ Unified Logging, có thể dùng `-Xlog:class+load=info` để quan sát class loading, nhưng lượng log lớn và cú pháp/khả năng hỗ trợ tùy JVM.

Đừng dùng `-noverify` hoặc `-Xverify:none` để “sửa” `VerifyError`. Ngoài vấn đề bị hạn chế/deprecated ở những JDK mới, việc bỏ verifier che lỗi classfile nghiêm trọng và không tạo bytecode hợp lệ. Nếu dùng bytecode enhancer/agent, hãy sửa generator hoặc pipeline build.

### 11.4. Một số bài toán loader/module dễ gây nhầm

- **Nhiều bản JAR cùng class:** classpath thường chọn bản đầu theo loader policy, không tự động định nghĩa cả hai rồi gây duplicate. Nhưng bytecode/JAR lẫn phiên bản có thể dẫn đến `NoSuchMethodError`.
- **Parent-first vs child-first:** thay chính sách có thể tạo kiểu cùng tên nhưng khác loader; cần thiết kế vùng chia sẻ SPI cẩn thận.
- **JPMS package export/open:** quản lý accessibility theo module, không thay thế classfile version checking hoặc bytecode verifier. Không thể giải quyết `UnsupportedClassVersionError` bằng `--add-opens`.
- **Hot reload:** loader mới có thể nạp class tên cũ, nhưng không làm object từ loader cũ tự biến thành kiểu của loader mới. Dọn tài nguyên và loại bỏ các reference giữ loader cũ trước khi kỳ vọng class unloading.
- **Plugin không tin cậy:** class loader/JPMS không phải sandbox OS; đừng để việc định nghĩa được class đồng nghĩa được quyền chạy mọi tác vụ nhạy cảm.

## 12. Hướng xây hệ thống định nghĩa lớp đáng tin cậy

### 12.1. Với plugin manager

Thiết kế một **interface/contract chung** được nạp trong loader mà host và plugin cùng nhìn thấy đúng `Class<?>`. Để plugin loader phụ trách implementation packages. Khi cần cập nhật plugin:

- Phiên bản hóa contract trước khi phát hành artifact mới.
- Nạp plugin mới vào loader/module layer có kiểm soát; không định nghĩa lại class trong cùng loader.
- Xác minh artifact trước khi chạy: nguồn, checksum/chữ ký khi phù hợp, Java target version, dependency list và chính sách quyền.
- Giữ lifecycle của loader rõ ràng; đóng resource, xóa references/caches, không giữ thread context class loader cũ vô thời hạn.
- Log class name/loader/module/actual artifact của lỗi; không nuốt `LinkageError` để tiếp tục dùng một class “nửa hợp lệ”.

### 12.2. Với bytecode generator/agent

Một pipeline có thể làm hỏng classfile dù source ban đầu hợp lệ. Kiểm tra theo thứ tự:

1. Version classfile mà JVM mục tiêu hỗ trợ.
2. Magic, constant pool, class/method/field structures.
3. Bytecode instruction semantics: stack height, types, locals, control flow.
4. `StackMapTable`/frames sau khi chèn/xóa nhánh hoặc method.
5. External references/ABI đối với dependency/runtime thực.
6. Tự động kiểm thử **từ class bytes cuối cùng** được đưa vào loader, không chỉ unit test source.

**Đừng dùng thủ thuật sửa byte major để ép chạy** một classfile không tương thích. Nếu muốn tạo code tương thích Java 17, xây từ compiler/bytecode generator có target Java 17 và kiểm tra API/kỹ thuật bytecode thực sự được phép.

### 12.3. Với CI và phát hành

- Cài ít nhất một bước **test chạy trên JVM tối thiểu được hỗ trợ**, không chỉ compile `--release` trên JDK cao hơn.
- Kiểm thử clean runtime classpath/module path và build reproducibility; loại bỏ cache làm lệch artifact.
- Bổ sung binary compatibility checks khi thư viện có client/plugin độc lập được phát hành trước.
- Với JAR nhiều phiên bản (`META-INF/versions/...`), kiểm tra classfile **entry thật JVM lựa chọn** cho release tương ứng, không chỉ entry gốc.
- Ghi rõ release target, phiên bản bytecode enhancement tool, agent và dependency compatibility trong quy trình phát hành.

## 13. Những hiểu lầm cần tránh

1. **“Hai loader cùng tải class tên X chắc chắn bị duplicate.”** Sai. Hai defining loaders độc lập có thể tạo hai kiểu runtime khác nhau cùng tên.
2. **“`Class.forName` mỗi lần đều `defineClass` lại.”** Sai. Loader có cache và delegation; repeated load thường trả class đã nạp.
3. **“`LinkageError` chỉ xảy ra khi class không tồn tại.”** Sai. Họ lỗi gồm duplicate, version, malformed/invalid bytecode, ABI incompatibility và nhiều tình huống khác.
4. **“`VerifyError` là `ClassFormatError`.”** Sai về phân cấp. Cả hai là `LinkageError` nhưng `VerifyError` không kế thừa `ClassFormatError`.
5. **“`UnsupportedClassVersionError` chỉ báo Java source syntax sai.”** Sai. Nó liên quan version của **classfile đang được JVM đọc**.
6. **“Đổi bytes major xuống 61 là có thể chạy trên Java 17.”** Sai. Classfile mới vẫn có thể dùng tính năng/constant pool/API không được hỗ trợ.
7. **“Lệnh `javac` thành công nghĩa runtime dependencies đều tương thích.”** Sai. `NoSuchMethodError` xuất hiện khi binary client v1 gặp API v2 không tương thích.
8. **“`NoClassDefFoundError` và `ClassNotFoundException` giống hệt nhau.”** Sai. Một là LinkageError; một là checked exception từ yêu cầu tìm class tường minh.
9. **“`VerifyError` luôn ném tại `defineClass`.”** Sai. Tùy điểm liên kết/verify/active use mà lỗi có thể lộ khác nhau.
10. **“Tắt verification hoặc thêm `--add-opens` sửa được bytecode lỗi.”** Sai và không an toàn.
11. **“Cùng binary name nghĩa có thể cast object qua loader khác nhau.”** Sai. Kiểu runtime phụ thuộc defining loader.
12. **“Hot reload = `defineClass` cùng tên lần hai.”** Sai. Loader mới hoặc instrumentation theo quy tắc riêng là chuyện khác.
13. **“Bắt `LinkageError` rồi bỏ qua là ổn.”** Sai. Nên xem đó là lỗi hệ thống/artifact nghiêm trọng, xác định nguyên nhân và cô lập đường chạy.

## 14. Bài tập thực hành

**Bài 1 — Cây phân cấp lỗi:** Vẽ quan hệ giữa `LinkageError`, `ClassFormatError`, `UnsupportedClassVersionError` và `VerifyError`. `catch(ClassFormatError)` có bắt VerifyError không? Vì sao?

**Bài 2 — Tên và loader:** Trong `ClassDefinitionFailureDemo`, tại sao `first.getName().equals(peer.getName())` đúng nhưng `first == peer` sai? Nếu hai object được khởi tạo từ các class tương ứng, chúng có mặc nhiên cast cho nhau không?

**Bài 3 — Định nghĩa trùng:** Thay `firstLoader.defineRaw(good)` lần hai bằng `firstLoader.loadClass(first.getName())`, quan sát loader nào trả class. Vì sao parent delegation có thể khiến kết quả khác `first`? Đừng chỉ so tên class.

**Bài 4 — Version:** Dùng `javac --release 17` build demo rồi đọc major bằng `javap -verbose`. Nếu muốn deploy trên JVM Java 11 (major tối đa 55), phải làm gì ngoài việc đổi major bytes?

**Bài 5 — Verifier:** Trong demo, việc sửa `iadd` thành `ladd` khiến stack types không khớp thế nào? Thử bỏ phần gọi `getDeclaredMethod`: JVM có luôn ném `VerifyError` ngay tại cùng một dòng trên mọi bản triển khai không?

**Bài 6 — ABI:** Với demo `sample.Api` v1/v2, giải thích vì sao client compile với v1 thành công nhưng chạy với v2 bị `NoSuchMethodError`. Thử biên dịch lại client với v2 để xem compile-time error và so sánh.

**Bài 7 — Wrong name:** Viết subclass `ClassLoader` gọi `defineClass("other.Name", goodBytes, 0, len)` trong khi bytes thực chứa `ClassDefinitionFailureDemo$Good`. Dự đoán subtype LinkageError nào xuất hiện.

**Bài 8 — Loading diagnostics:** Cho hai plugin JAR chứa cùng `com.example.Spi` nhưng được định nghĩa ở hai loader. Tìm cách đo class identity và đề xuất loader hierarchy để host/plugin dùng một contract chung.

**Bài 9 — CI compatibility:** Thiết kế pipeline xác thực artifact Java 17 từ build đến deploy: `--release 17`, kiểm tra major, runtime test trên JDK17, binary compatibility check và log loader. Giải thích lý do cần đủ cả các bước.

## 15. Tóm lược

- **Một binary name trong cùng defining class loader chỉ được định nghĩa một lần.** Gọi lại `defineClass` không phải reload; có thể gây `LinkageError`. Hai loader khác nhau có thể định nghĩa cùng tên thành **hai type runtime khác nhau**.
- **`UnsupportedClassVersionError`** báo classfile major/minor không được JVM hỗ trợ; **`ClassFormatError`** báo cấu trúc classfile hỏng; **`VerifyError`** báo bytecode/type-state không qua verifier.
- **`UnsupportedClassVersionError extends ClassFormatError extends LinkageError`**, trong khi **`VerifyError extends LinkageError`** trực tiếp.
- **`NoSuchMethodError`** là một ví dụ lỗi liên kết nhị phân khi client dùng API theo phiên bản compile-time nhưng runtime chứa API không tương thích.
- Lỗi có thể lộ khi load, link, resolve hoặc active-use; phải điều tra **artifact và loader/JVM thật**, không đoán theo vị trí stack trace duy nhất.
- Chữa đúng bằng cách đồng bộ version, cải thiện class loader policy và tạo **classfile/bytecode hợp lệ**, không bằng cách tắt verification.

## Tài liệu tham khảo chính thức (Java 17)

- [ClassLoader — `defineClass`, `loadClass`, `findLoadedClass`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [LinkageError — các phân lớp và ngữ nghĩa chung](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html)
- [UnsupportedClassVersionError — version không được hỗ trợ](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedClassVersionError.html)
- [ClassFormatError — classfile bị hỏng](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassFormatError.html)
- [VerifyError — bytecode verifier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/VerifyError.html)
- [JVMS 17 `4.1 — ClassFile structure, version table](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1)
- [JVMS 17 `4.10 — Verification of class files](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.10)
- [JVMS 17 `5.3–5.4 — Loading, Linking, Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [JLS 17 Chapter 13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
- [javac Java 17 manual — `--release`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
