# Truyền tên, offset và length chính xác cho defineClass

Khi tự viết `ClassLoader` để đọc bytecode từ tệp, JAR, mạng, bộ nhớ hoặc một container riêng, bước quyết định là gọi đúng phương thức **`defineClass(String name, byte[] b, int off, int len)`**. Ba giá trị **`name`, `off`, `len`** phải mô tả chính xác **định nghĩa lớp** mà vùng byte mang theo: tên nhị phân của lớp bên trong ClassFile và vị trí bắt đầu/độ dài phần ClassFile hợp lệ trong mảng.

Một lỗi nhỏ có thể tạo ra `ClassFormatError`, `NoClassDefFoundError` hoặc lỗi chỉ xuất hiện khi code nạp lớp ở môi trường production. Việc byte array đủ lớn hay có chứa một đoạn ClassFile hợp lệ **không đủ** nếu ta cắt sai ranh giới, truyền nhầm kích thước vùng đệm hoặc khai báo một tên lớp không khớp.

**Quy tắc chính:**

~~~java
Class<?> type = defineClass(binaryName, bytes, offset, classFileLength);
~~~

Đây là **fragment** phải chạy từ một subclass của `ClassLoader` hoặc ngữ cảnh có quyền gọi phương thức `protected` đó; không phải một lệnh gọi công khai từ bất kỳ class nào.

- `binaryName`: tên nhị phân JVM/Java của **đúng class nằm trong ClassFile**, ví dụ `com.example.Widget`, không phải đường dẫn `com/example/Widget.class`.
- `bytes`: mảng có chứa dữ liệu ClassFile.
- `offset`: **chỉ số byte đầu** của ClassFile trong mảng `bytes`, đếm từ **0**.
- `classFileLength`: **số byte của ClassFile bắt đầu tại offset**, không phải chỉ số cuối mảng.

Nếu toàn bộ mảng là đúng một ClassFile (không có header/footer thừa), cách gọi điển hình nhất là:

~~~java
defineClass("com.example.Widget", classBytes, 0, classBytes.length);
~~~

## 1. Vai trò của defineClass trong một class loader tùy chỉnh

`ClassLoader` chịu trách nhiệm tìm dữ liệu của lớp và phối hợp với JVM định nghĩa class. Với subclass truyền thống, các bước thường là:

~~~text
Yêu cầu nạp "com.example.Widget"
       |
       v
loadClass(...) kiểm tra đã nạp / ủy quyền parent
       |
       v
findClass(...) đọc hoặc lấy byte[] ClassFile
       |
       v
xác định binary name + đoạn byte hợp lệ
       |
       v
defineClass(name, bytes, offset, length)
       |
       v
JVM tạo định nghĩa Class<?>
       |
       v
resolve / initialize vào thời điểm thích hợp
~~~

`defineClass` là bước **định nghĩa class từ biểu diễn ClassFile**. Nó không có nghĩa mọi lúc đều chạy static initializer ngay tại dòng gọi. Liên kết, resolution và khởi tạo là các hoạt động riêng của JVM. `resolveClass(type)` thường được gọi bởi mã trong `loadClass` khi yêu cầu resolve; initialization chỉ xảy ra theo các điều kiện của Java/JVM.

Subclass đơn giản thường ghi đè **`findClass(String name)`** để lấy bytes, còn giữ cơ chế `loadClass` parent-first mặc định. Không tự ghi đè `loadClass` nếu chưa cần child-first hoặc chính sách đặc biệt, vì rất dễ phá delegation, tạo hai kiểu cùng tên bởi loader khác nhau hoặc chặn lớp nền tảng.

### Đặc tả tham số quan trọng

| Tham số | Ý nghĩa | Sai sót thường gặp |
| --- | --- | --- |
| `name` | Binary name tương ứng với lớp trong ClassFile; API cũng hỗ trợ `null` ở một số overload, nhưng thông thường nên truyền tên đúng. | Dùng đường dẫn `pkg/MyClass.class` hoặc tên khác `this_class` bên trong bytecode. |
| `b` | Mảng byte chứa ClassFile. | Truyền một buffer chưa ghi đầy dữ liệu, buffer bị sửa, hoặc dữ liệu đã nén/mã hóa chưa giải mã. |
| `off` | Byte đầu tiên cần đọc, chỉ số zero-based. | Đọc nhầm header container hoặc gửi offset 0 dù có prefix. |
| `len` | Số byte ClassFile trong mảng tính từ `off`. | Truyền `b.length` thay vì độ dài payload, nhầm `endIndex` với `length`, hoặc quên trừ prefix. |

**Tên `name` không phải tên file:** Nếu ta đọc `plugins/lab/generated/Echo.class` từ ổ đĩa, binary name của kiểu là `lab.generated.Echo`, không phải `plugins.lab.generated.Echo`, `lab/generated/Echo` hay chuỗi có đuôi `.class`.

## 2. Binary name phải khớp tên khai báo trong bytecode

Trong ClassFile có cấu trúc `this_class` tham chiếu đến metadata định danh kiểu. Với Java:

~~~java
package lab.generated;
public class Echo { }
~~~

ClassFile mô tả tên nội bộ tương ứng `lab/generated/Echo`, trong khi tham số `name` của `ClassLoader.defineClass` được cung cấp bằng **binary name**:

~~~text
Cần truyền:    lab.generated.Echo
Không truyền:  lab/generated/Echo
Không truyền:  lab/generated/Echo.class
Không truyền:  Echo
Không truyền:  lab.generated.Other
~~~

Tên class lồng còn dùng dấu `$` trong binary name, ví dụ `lab.generated.Outer$Inner` cho một member class được biên dịch thông thường. Tên file có thể chứa `$`, nhưng phải lấy theo **tên thực tế trong ClassFile**, không xây bằng cách thay dấu gạch chéo dựa trên đường dẫn container một cách tùy tiện.

Nếu cung cấp `name` **khác** tên mà ClassFile khai báo, JVM có thể ném **`NoClassDefFoundError`** (thường kèm thông tin *wrong name*). Không có cơ chế đổi tên kiểu bằng cách chỉ đổi tham số `name`: muốn class thật sự mang tên khác cần biến đổi ClassFile hợp lệ và tất cả metadata/tham chiếu liên quan theo quy tắc JVM.

**Có được truyền `null` không?** Một số `defineClass` overload cho phép `name == null` và JVM suy từ ClassFile, nhưng tài liệu API cảnh báo hạn chế kiểm tra gắn với tên/package; do đó **nên truyền binary name không null và đã xác thực** trong loader tùy chỉnh. Đặc biệt, package `java.*` có ràng buộc bảo vệ, và tên bytecode/loại module có thể ảnh hưởng kiểm tra bảo mật.

## 3. off và len là khoảng byte [off, off + len)

Thứ tự byte của một ClassFile chuẩn bắt đầu bằng **`CA FE BA BE`**. Có thể xuất hiện header/footer của định dạng lưu trữ riêng bên ngoài payload thực:

~~~text
byte[] container:

Index:  0   1   2   3   4   5   6   7   8   9  ...      N
        +-------------------+------------------------+----------+
Data:   | 5 byte HEADER     | CA FE BA BE ... .class | TRAILER  |
        +-------------------+------------------------+----------+
                            ^
                            off = 5
                             <---- len bytes ---->
~~~

Với ví dụ, ClassFile chiếm vùng **từ `off` (bao gồm) đến `off + len` (không bao gồm)**. Do đó:

- `off = 5`, `len = payload.length` là đúng nếu `payload` là toàn bộ byte ClassFile.
- `off = 0`, `len = payload.length` sẽ truyền cả header và cắt thiếu phần cuối ClassFile.
- `off = 5`, `len = container.length` dễ vượt quá giới hạn mảng; kể cả không vượt, truyền cả trailer là sai ý nghĩa.
- `off = 5`, `len = payload.length - 1` cắt mất byte cuối ClassFile, thường dẫn tới `ClassFormatError`.
- `off = 5`, `len = off + payload.length` là nhầm **chỉ số kết thúc** với **độ dài**.

Cần phân biệt bốn đại lượng:

~~~text
offset                 vị trí bắt đầu payload trong mảng
endExclusive           vị trí sau byte cuối = offset + length
length                 số byte payload = endExclusive - offset
container.length       độ dài cả mảng, có thể lớn hơn payload
~~~

Lỗi thường gặp trong xử lý stream, buffer pool và container tự thiết kế là dùng **capacity** thay vì số byte thực sự nhận được hoặc số byte payload đã được decode. Một buffer có capacity 65.536 không có nghĩa 65.536 byte đều thuộc ClassFile.

### Kiểm tra khoảng trước khi defineClass

Một điều kiện an toàn trước khi dùng một mảng không đáng tin là:

~~~java
if (offset < 0 || length < 0 || length > data.length
        || offset > data.length - length) {
    throw new IndexOutOfBoundsException("Invalid ClassFile byte range");
}
~~~

Đây là **fragment**, giả sử `data` là mảng khác `null` và `offset`/`length` là số nguyên. Điều kiện dùng `offset > data.length - length` giúp tránh overflow của biểu thức cộng `offset + length`. Thư viện/JVM vẫn kiểm tra tham số và định dạng bytecode, nhưng validation ở boundary giúp báo lỗi đầu vào rõ ràng hơn.

**Không coi validation độ dài là validation ClassFile.** Kiểm tra offset/length hợp lệ chỉ nói khoảng nằm trong mảng; bytes vẫn có thể sai magic, sai constant pool, sai phiên bản hoặc bị làm hỏng.

## 4. Ví dụ Java 17: cùng một file, buffer có prefix/suffix

Ví dụ này dùng compiler của JDK để tạo đúng một ClassFile `lab.generated.Echo` tại thời điểm chạy, rồi đặt payload vào một mảng lớn hơn có **5 byte prefix và 7 byte suffix**. Một subclass của `ClassLoader` gọi trực tiếp `defineClass` để thử cả trường hợp đúng và sai.

Tạo tệp độc lập **`DefineClassRangeDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class DefineClassRangeDemo {
    private static final String NAME = "lab.generated.Echo";
    private static final int PREFIX = 5;
    private static final int SUFFIX = 7;

    static class ByteArrayLoader extends ClassLoader {
        ByteArrayLoader() {
            super(ClassLoader.getSystemClassLoader());
        }

        Class<?> define(String binaryName, byte[] container,
                        int offset, int length) {
            return defineClass(binaryName, container, offset, length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("defineclass-range-");
        Path source = root.resolve("src/lab/generated/Echo.java");
        Path classes = root.resolve("classes");

        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);

        Files.writeString(source,
                "package lab.generated;\n"
                + "public class Echo {\n"
                + "  public static String message() { return \"OK\"; }\n"
                + "}\n",
                StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a full JDK");
        }

        int result = compiler.run(null, null, null,
                "--release", "17",
                "-d", classes.toString(), source.toString());

        if (result != 0) {
            throw new IllegalStateException("Compilation failed");
        }

        byte[] payload = Files.readAllBytes(
                classes.resolve("lab/generated/Echo.class"));

        byte[] container = new byte[PREFIX + payload.length + SUFFIX];
        Arrays.fill(container, (byte) 0x11);
        System.arraycopy(payload, 0, container, PREFIX, payload.length);

        Class<?> type = new ByteArrayLoader().define(
                NAME, container, PREFIX, payload.length);

        System.out.println("Loaded: " + type.getName());
        System.out.println("Message: "
                + type.getMethod("message").invoke(null));
        System.out.println("Container larger: "
                + (container.length > payload.length));

        try {
            new ByteArrayLoader().define(NAME, container, 0, payload.length);
        } catch (ClassFormatError e) {
            System.out.println("Wrong offset: ClassFormatError");
        }

        try {
            new ByteArrayLoader().define(
                    NAME, container, PREFIX, payload.length - 1);
        } catch (ClassFormatError e) {
            System.out.println("Short length: ClassFormatError");
        }

        try {
            new ByteArrayLoader().define(
                    "lab.generated.Other", container, PREFIX, payload.length);
        } catch (NoClassDefFoundError e) {
            System.out.println("Wrong name: NoClassDefFoundError");
        }

        try {
            new ByteArrayLoader().define(
                    NAME, container, container.length - 2, 8);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("Invalid range: IndexOutOfBoundsException");
        }
    }
}
~~~

Dùng **JDK 17 hoặc mới hơn**, chạy trong thư mục chứa file:

~~~bash
javac --release 17 DefineClassRangeDemo.java
java DefineClassRangeDemo
~~~

Với JDK chuẩn có `jdk.compiler`, chương trình in:

~~~text
Loaded: lab.generated.Echo
Message: OK
Container larger: true
Wrong offset: ClassFormatError
Short length: ClassFormatError
Wrong name: NoClassDefFoundError
Invalid range: IndexOutOfBoundsException
~~~

**Giải thích:**

1. `JavaCompiler` biên dịch file nguồn được sinh ra thành ClassFile của `lab.generated.Echo` với target Java 17. Bytecode được đọc **đúng** từ `classes/lab/generated/Echo.class`.
2. `Arrays.fill` tạo các byte bao ngoài không thuộc ClassFile. `System.arraycopy` đặt toàn bộ payload tại chỉ số `PREFIX = 5`.
3. Lời gọi `define(NAME, container, PREFIX, payload.length)` đưa JVM đúng vùng byte và đúng binary name, nên tạo class hợp lệ.
4. Phản chiếu gọi `message()` chứng minh class đã được định nghĩa và sử dụng. Kết quả là chuỗi `OK`.
5. Khi truyền `off = 0`, dữ liệu bắt đầu bằng 0x11 thay vì magic `CAFEBABE`. JVM bác bỏ định dạng bằng `ClassFormatError`.
6. Khi cắt `len` ngắn hơn payload một byte, ClassFile bị thiếu phần cuối và bị bác bỏ bằng `ClassFormatError`.
7. Khi truyền `name = lab.generated.Other` nhưng bytecode tự khai báo `lab.generated.Echo`, lỗi là `NoClassDefFoundError` do tên không khớp.
8. Với offset nằm sát cuối buffer và `len = 8` vượt quá mảng, JVM phát hiện khoảng bất hợp lệ và ném `IndexOutOfBoundsException`.
9. Mỗi phép thử lỗi dùng **một `ByteArrayLoader` mới**. Nếu thử định nghĩa lần nữa cùng tên trong loader đã định nghĩa thành công, sẽ cần xét thêm lỗi duplicate-definition thay vì chỉ quan sát input bytes.

Ví dụ tạo thư mục tạm để chứa source/class sinh động; bạn có thể dọn sau khi chạy. Nó không đòi kết nối mạng hay thư viện ngoài JDK. `Class.forName` hoặc `resolveClass` không cần cho demo này vì ta gọi trực tiếp protected `defineClass` rồi dùng reflection. Trong ứng dụng thật, cần thêm chính sách parent delegation, kiểm tra nguồn bytecode, bảo vệ package và quản lý lifecycle.

### Vì sao không dùng container.length?

`container.length` ở ví dụ là `5 + payload.length + 7`. Nếu lấy `len = container.length` bắt đầu tại offset 5, khoảng vượt cuối mảng. Nếu lấy offset 0 và length container.length, ta truyền cả prefix/trailer; JVM không thể hiểu đó là một ClassFile bắt đầu tại byte 0.

Khi container chứa **nhiều ClassFile**, không truyền toàn bộ container cho `defineClass`; phải trích chính xác một ClassFile cần nạp và tên tương ứng. Việc tìm ranh giới ClassFile trong định dạng container là trách nhiệm parser/decoder của container, không phải `defineClass`.

## 5. Ví dụ triển khai findClass đúng quy tắc

Đây là **fragment rút gọn** của một subclass `ClassLoader` có `byte[] data` là toàn bộ ClassFile đã được đọc từ một nguồn đáng tin:

~~~java
@Override
protected Class<?> findClass(String binaryName)
        throws ClassNotFoundException {
    byte[] data = readClassFileBytes(binaryName);
    if (data == null) {
        throw new ClassNotFoundException(binaryName);
    }
    return defineClass(binaryName, data, 0, data.length);
}
~~~

`readClassFileBytes(...)` trong fragment là method **chưa được định nghĩa**, minh họa một lớp loader sẽ đọc file/JAR/resource/memory; đây **không phải code độc lập để compile**. Những điểm cần giữ:

- Chuyển binary name sang đường dẫn một cách có kiểm soát, ví dụ `binaryName.replace('.', '/') + ".class"` khi đọc JAR/classpath riêng. Đường dẫn này là **tên entry/đường dẫn**, không phải tham số `name` cho `defineClass`.
- Nếu không tìm thấy bytecode, ném `ClassNotFoundException` với binary name và lưu nguyên nhân I/O nếu có, không nuốt lỗi rồi trả `null`.
- Nếu `byte[] data` là toàn bộ payload, `off = 0` và `len = data.length`.
- Không dùng `InputStream.available()` làm độ dài toàn bộ ClassFile; nó chỉ phản ánh số byte có thể đọc không chặn theo hợp đồng của stream, **không bảo đảm kích thước nội dung**. Với Java 17, `readAllBytes()` phù hợp cho file có kích thước kiểm soát và chính sách giới hạn hợp lý.
- Không dùng độ dài string sau khi decode bytecode thành text. ClassFile là **nhị phân**, không phải chuỗi UTF-8 chứa source Java.
- Với dữ liệu container có prefix/suffix, truyền đúng vùng hoặc tạo `Arrays.copyOfRange(container, off, off + len)` rồi `defineClass(name, slice, 0, slice.length)`. Cách copy dễ tránh sai offset nhưng dùng thêm bộ nhớ; cần kiểm tra chỉ số đầu/cuối trước khi copy.

**Lưu ý lớp trùng:** `findClass` chỉ nên định nghĩa class khi chưa có định nghĩa theo chính sách `loadClass`. Nếu tự bỏ qua `findLoadedClass` và định nghĩa lại cùng binary name trong một loader, JVM có thể ném `LinkageError`. Không cố dùng `defineClass` để ghi đè lớp đã nạp.

## 6. Những lỗi và exception cần phân biệt

| Biểu hiện | Nguyên nhân điển hình | Hướng kiểm tra |
| --- | --- | --- |
| `IndexOutOfBoundsException` | `off`/`len` âm hoặc khoảng vượt mảng. | Xem `off`, `len`, `b.length`; kiểm tra tính toán không overflow. |
| `ClassFormatError` | Dãy byte không tạo thành ClassFile hợp lệ: sai magic, hỏng constant pool, bị cắt ngắn, dữ liệu rác. | So lại 4 byte đầu `CAFEBABE` và đúng ranh giới payload. |
| `NoClassDefFoundError` kèm *wrong name* | `name` yêu cầu khác tên `this_class` trong ClassFile. | So binary name được yêu cầu với tên thực trong bytecode, dùng `javap -v`. |
| `UnsupportedClassVersionError` | Bytecode target phiên bản JVM chưa hỗ trợ. | Kiểm tra `major_version` trong ClassFile và bản Java chạy. |
| `SecurityException` | Có thể vi phạm quy tắc định nghĩa package bị cấm hoặc ràng buộc certificate/package. | Xem package, signing, ProtectionDomain và thiết kế nguồn code. |
| `LinkageError` | Ví dụ định nghĩa trùng trong cùng loader hoặc xung đột liên kết giữa các định nghĩa kiểu. | Kiểm tra `findLoadedClass`, đồng bộ loader, namespace và delegation. |
| `ClassNotFoundException` | `findClass` không tìm được dữ liệu cần thiết; thường ở đường tìm lớp, không phải phép parse ClassFile. | Xem chuyển binary name thành đường dẫn, nguồn bytes và cause I/O. |

Một số lỗi như `UnsupportedClassVersionError` và `NoClassDefFoundError` cũng thuộc họ `LinkageError`, nhưng có ý nghĩa chẩn đoán cụ thể hơn. Đừng mặc định mọi lỗi `NoClassDefFoundError` đều do sai tên: nó còn có thể do dependency bị thiếu hoặc lớp ở trạng thái khởi tạo lỗi trước đó. Hãy đọc **toàn bộ thông báo và cause**.

### Kiểm tra header nhanh

Một ClassFile hợp lệ có bốn byte đầu `CA FE BA BE`:

~~~java
boolean plausibleMagic = length >= 4
        && (data[offset] & 0xFF) == 0xCA
        && (data[offset + 1] & 0xFF) == 0xFE
        && (data[offset + 2] & 0xFF) == 0xBA
        && (data[offset + 3] & 0xFF) == 0xBE;
~~~

Đây là **fragment**, giả sử offset/length đã được kiểm tra hợp lệ trong data. `plausibleMagic` chỉ là phép **sanity check**; nó không thay JVM verifier và không bảo đảm phần còn lại của ClassFile hợp lệ hay đáng tin.

Với bytecode thiếu/không khớp phiên bản, có thể dùng:

~~~bash
javap -v lab.generated.Echo
~~~

khi `lab.generated.Echo` đã được biên dịch vào đúng classpath và không có xung đột tên. `javap -v` hiển thị major version, this_class, constant pool và cấu trúc giúp đối chiếu tên/phiên bản. Với custom container, có thể trích đúng ClassFile ra tệp trước khi kiểm tra.

## 7. ByteBuffer overload có giải quyết được lỗi offset không?

Ngoài overload dùng `byte[]`, `ClassLoader` còn có phương thức `defineClass(String, ByteBuffer, ProtectionDomain)` và các overload liên quan. Với `ByteBuffer`, cần hiểu chính xác vùng dữ liệu dùng để định nghĩa class theo **position/limit/remaining** của buffer và hợp đồng API thay vì đoán từ `capacity`.

Nếu dữ liệu nhận từ network/NIO, pattern thường là chuẩn bị buffer chỉ chứa payload hoặc tạo một **slice** với vị trí/giới hạn đúng, sau đó gọi overload phù hợp. Nhưng dùng ByteBuffer **không tự sửa** lỗi sai binary name, dữ liệu hỏng, sai ranh giới, hoặc không nhất quán về ProtectionDomain.

Đối với `byte[]`, điều quan trọng vẫn là tính toán:

~~~text
0 <= off
0 <= len
off + len <= b.length  (kiểm tra sao cho không overflow)
payload = b[off ... off+len)
~~~

Với input không tin cậy, nên đặt giới hạn kích thước payload, bảo đảm nguồn bytes đã được giải nén/xác thực đầy đủ, và không dùng dữ liệu mutable chung mà thread khác có thể sửa trong lúc định nghĩa lớp. Có thể copy sang mảng sở hữu riêng trước khi gọi `defineClass` nếu nguồn bytecode có thể bị thay đổi đồng thời.

## 8. Tên, package và quyền định nghĩa lớp

`defineClass` không chỉ kiểm tra cú pháp bốn tham số. JVM và ClassLoader còn áp dụng các quy tắc về:

- **Package:** một class thuộc package theo tên nhị phân thực tế. Một số package như `java.*` không được class loader tùy chỉnh định nghĩa thông thường.
- **ProtectionDomain:** overload đơn giản sử dụng miền bảo vệ mặc định gắn với loader theo hợp đồng API; khi tải code với nguồn/quyền truy cập khác nhau có thể cần overload với `ProtectionDomain` rõ ràng.
- **Certificate/signing consistency:** các class trong cùng package của một defining loader có thể phải tuân thủ điều kiện nhất quán về certificate theo `ClassLoader` API.
- **Type identity:** cùng binary name nhưng khác defining loader là hai kiểu JVM khác nhau. Không dùng `defineClass` hai lần ở hai loader để giả vờ tạo bản thứ hai của interface API dùng chung.
- **Class initialization:** `defineClass` không đồng nghĩa với việc chạy static initializer của kiểu vừa định nghĩa. Thời điểm khởi tạo tuân theo quy tắc JLS/JVMS.

Nếu cần xây hệ plugin với child-first, nên phân biệt package API chung (ủy quyền parent) và package implementation riêng (loader plugin sở hữu). Việc truyền đúng tên/byte range là điều kiện cần, nhưng **chưa đủ** để làm custom loader an toàn và tương thích mọi dependency.

## 9. Những anti-pattern dễ mắc

**Dùng `buffer.length` làm `len` dù có prefix:**

~~~java
// Sai nếu có header/trailer bên ngoài ClassFile:
defineClass(name, container, prefixSize, container.length);
~~~

`container.length` bao gồm bytes không thuộc payload, dễ vượt giới hạn mảng hoặc đi sai ClassFile. Dùng đúng `payloadLength`.

**Dùng chỉ số cuối làm độ dài:**

~~~java
// Sai nếu endExclusive là chỉ số kết thúc:
defineClass(name, container, start, endExclusive);
~~~

Đúng là `endExclusive - start` khi chỉ số kết thúc là exclusive.

**Dùng offset đúng nhưng name sai:**

~~~java
// Sai nếu ClassFile khai báo pkg.Widget, không phải pkg.Other:
defineClass("pkg.Other", bytes, 0, bytes.length);
~~~

Không thể đổi tên class bằng cách sửa chuỗi `name`.

**Đọc file nhị phân thành String rồi quay lại byte[]:**

~~~java
// Sai ý tưởng: ClassFile không phải văn bản UTF-8 của source code.
String source = new String(classBytes, java.nio.charset.StandardCharsets.UTF_8);
byte[] converted = source.getBytes(java.nio.charset.StandardCharsets.UTF_8);
~~~

Làm vậy có thể hỏng byte không hợp lệ cho UTF-8, thay đổi nội dung và gây `ClassFormatError`. Giữ dữ liệu nhị phân nguyên vẹn.

**Tự gộp nhiều ClassFile thành một mảng rồi define cả mảng:** JVM chỉ mong **một ClassFile hợp lệ** cho mỗi lần `defineClass`. Phải bóc đúng entry trước khi gọi.

**Giả định defineClass luôn trả về class có thể sử dụng được:** ClassFile có thể định nghĩa thành công nhưng lỗi linking/resolution/dependency hoặc initialization chỉ phát sinh lúc dùng về sau. Cần phân biệt lỗi ở từng pha và log nguyên nhân.

## 10. Checklist kiểm tra trước khi gọi defineClass

1. **Binary name:** có đúng `pkg.Type` theo tên trong ClassFile không? Không có `.class` hoặc dấu `/` của internal name.
2. **Dữ liệu đầu vào:** byte array có chứa **đầy đủ một** ClassFile chưa bị đổi, nén hoặc cắt mất dữ liệu?
3. **Ranh giới:** `off` là chỉ số bắt đầu; `len` là số byte payload; `off + len` không vượt `b.length`.
4. **Header:** nếu cần debug, bốn byte bắt đầu vùng payload có phải `CA FE BA BE`?
5. **Version:** ClassFile target có được JVM hiện hành hỗ trợ không?
6. **Class loader:** đã có cùng binary name được định nghĩa trong loader này chưa? Parent delegation và chính sách `findLoadedClass` có phù hợp?
7. **Package/ProtectionDomain:** có vi phạm package/certificate/security rule không?
8. **Đồng thời:** bytes có thể bị thread khác sửa trong lúc define không? Nếu có, copy thành buffer riêng.
9. **Quan sát lỗi:** phân biệt `ClassFormatError`, `NoClassDefFoundError`, `IndexOutOfBoundsException`, `UnsupportedClassVersionError` và các vấn đề linking/initialization.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Mảng dài 1024 byte, ClassFile bắt đầu tại offset 32 và dài 800 byte. Phải gọi thế nào?

**Trả lời:** `defineClass(name, b, 32, 800)`. Khoảng được đọc là `[32, 832)`, không phải `[32, 800)`.

**Câu 2.** Nếu truyền `len = 832` thay vì 800 thì có đúng vì 832 là `endExclusive`?

**Trả lời:** Không. `len` là **độ dài**, không phải chỉ số kết thúc. Nếu tính từ off 32, đoạn đó sẽ dài 832 byte và kết thúc tại 864.

**Câu 3.** Bytecode tự khai báo `com.demo.Service`; gọi `defineClass("com/demo/Service", bytes, 0, bytes.length)` có chuẩn không?

**Trả lời:** Không. Tham số `name` cần dùng **binary name** `com.demo.Service`, không phải internal name `com/demo/Service`.

**Câu 4.** ClassFile đúng hoàn toàn nhưng loader khai báo tên khác. Lỗi thường là gì?

**Trả lời:** `NoClassDefFoundError` với thông điệp *wrong name*, vì tên yêu cầu không khớp với tên bên trong bytecode.

**Câu 5.** `byte[]` có đúng bốn byte magic nhưng `len` thiếu một byte cuối. Có đủ để define thành công không?

**Trả lời:** Không. Magic chỉ là kiểm tra sơ bộ, còn định dạng ClassFile cần đầy đủ nội dung. JVM có thể ném `ClassFormatError`.

**Câu 6.** Mỗi loader định nghĩa một `com.example.Api` từ bytecode giống nhau. Hai kiểu có tự hợp nhất thành một không?

**Trả lời:** Không. Type identity bao gồm defining loader; cần dùng chung API contract qua loader phù hợp nếu hai bên muốn cast trực tiếp.

## Ghi nhớ

`defineClass(name, b, off, len)` đòi hỏi **đúng tên nhị phân** và **đúng vùng bytes của một ClassFile**. `off` là byte bắt đầu (zero-based), `len` là số byte cần đọc, không phải offset kết thúc hay capacity. Với mảng chỉ có một ClassFile, dùng `off=0` và `len=b.length`; với buffer chứa prefix/suffix, phải dùng ranh giới payload thực tế. Sau đó còn cần lưu ý package, version, ProtectionDomain, parent delegation và vòng đời class loader.

**Tài liệu chính thức:**

- Java SE 17 API, `ClassLoader#defineClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java Virtual Machine Specification, Java SE 17, §4.1 — *The ClassFile Structure*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1
- Java Virtual Machine Specification, Java SE 17, §5.3 — *Creation of Classes and Interfaces*: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java SE 17 API, `JavaCompiler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
