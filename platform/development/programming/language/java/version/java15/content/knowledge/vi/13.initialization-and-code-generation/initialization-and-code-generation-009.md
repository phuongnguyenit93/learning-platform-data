# Kiểm tra thư viện sinh mã tương thích với JDK triển khai (Java 15+)

## Mục tiêu

Một thư viện sinh hoặc biến đổi bytecode có thể **biên dịch thành công** với ứng dụng, nhưng vẫn thất bại khi chạy trên JDK triển khai: lớp sinh ra có *class-file version* quá mới, thư viện đọc bytecode không hiểu cấu trúc mới, việc định nghĩa lớp thiếu quyền `Lookup`, hoặc truy cập phản chiếu bị giới hạn bởi module.

Bài học này đưa ra một quy trình **kiểm tra tương thích end-to-end** trong bối cảnh Java 15 và các JDK hiện đại. Sau bài này, bạn có thể:

1. Phân biệt **phiên bản JDK chạy ứng dụng**, **phiên bản bytecode lớp sinh ra** và **phiên bản thư viện sinh/đọc bytecode**.
2. Kiểm tra `major_version`/`minor_version` của một tệp `.class`, hiểu lỗi `UnsupportedClassVersionError` và ý nghĩa của bytecode *preview*.
3. Kiểm tra thư viện sinh mã (ví dụ ASM, Byte Buddy hoặc thư viện dùng chúng) và các dependency transitively được đóng gói.
4. Nhận biết sự khác nhau giữa sinh **lớp có tên** với `Lookup.defineClass` và **hidden class** qua `Lookup.defineHiddenClass`, tính năng chính thức từ Java 15.
5. Thiết kế smoke test trên **đúng runtime và cấu hình triển khai**, không chỉ tin kết quả biên dịch.
6. Đọc thông báo lỗi để khoanh vùng: VM không chấp nhận phiên bản, parser bytecode quá cũ, bytecode không hợp lệ, hay vi phạm quyền truy cập module.

**Special Note — giới hạn kiến thức hiện hành:** Bài chỉ dùng cơ chế/API vẫn có giá trị trên Java hiện đại. Ví dụ chạy với **JDK 17+** và biên dịch bằng `javac --release 17`; không phụ thuộc API nội bộ `sun.*`, không dựa vào kỹ thuật sinh anonymous class đã bị loại bỏ, và không khẳng định một phiên bản thư viện cố định là “mới nhất” cho mọi thời điểm.

## 1. “Tương thích với JDK” gồm nhiều lớp kiểm tra

Không thể chỉ xem một ô “Java version” trong `pom.xml` hay `build.gradle` rồi kết luận tương thích. Cần phân biệt ít nhất **bốn thành phần**:

| Thành phần | Câu hỏi phải xác minh | Ví dụ |
| --- | --- | --- |
| JDK dùng **biên dịch ứng dụng** | `javac` nào đang chạy và `--release` nào được áp dụng? | `javac --release 17` |
| **JDK triển khai** thực sự khởi động JVM | Container, service, CI, server hoặc người dùng chạy phiên bản nào? | JDK 17, 21, 25… |
| **Thư viện sinh/biến đổi mã** | Phiên bản thư viện có hiểu class-file format của JDK đang dùng và API runtime cần thiết không? | ASM, Byte Buddy, plugin test, agent |
| **Lớp được sinh ra** | Major/minor của bytecode là bao nhiêu; có đặc tính preview hoặc dependency không có ở đích không? | `61.0` (Java 17), `65.0` (Java 21) |

Có **hai chiều tương thích khác nhau**:

- **JVM nạp lớp được sinh:** Lớp `.class` phải có phiên bản và cấu trúc mà JVM đích hiểu; dependency cần có; JVM verifier, linker và access check phải chấp nhận.
- **Thư viện sinh/đọc/biến đổi lớp:** Thư viện hoặc engine nằm bên trong plugin phải nhận diện class-file format và cấu trúc cần đọc/ghi. JVM có thể hỗ trợ Java 25 nhưng một parser ASM cũ lại từ chối bytecode Java 25. Nâng JDK không tự nâng parser của thư viện.

Thứ ba, cách định nghĩa lớp (qua class loader, `Lookup.defineClass` hoặc `Lookup.defineHiddenClass`) còn liên quan tới package, module và quyền truy cập; class-file version hợp lệ **chưa phải điều kiện đủ**.

## 2. Đọc class-file version thay vì suy đoán

Trong định dạng tệp `.class` của JVM, các byte đầu chứa:

```text
Offset   Kích thước   Ý nghĩa
0        4 byte       magic = 0xCAFEBABE
4        2 byte       minor_version (unsigned)
6        2 byte       major_version (unsigned)
```

Những trường này lưu theo **big-endian**. Trên các Java SE tương đối mới, giá trị *major* tăng theo phiên bản phát hành.

| Java SE | Major class-file |
| --- | ---: |
| Java 11 | 55 |
| Java 15 | 59 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 26 | 70 |

Bảng trên chỉ nêu vài mốc hữu ích để đọc log và kiểm tra tương thích; không có nghĩa cần dùng tất cả các phiên bản đó. Ví dụ **class file `65.0` yêu cầu JVM ít nhất hiểu class-file format Java 21**; JVM Java 17 chỉ hỗ trợ đến major `61` và không thể nạp trực tiếp lớp major `65`.

Khi dùng JDK 17+ làm **đích chạy**, có thể đọc major của file và kiểm tra bước đầu bằng công thức: `major <= Runtime.version().feature() + 44`. Công thức này hữu ích cho class file thông thường ở các phiên bản hiện đại, nhưng **không thay thế kiểm tra VM thật**, nhất là đối với bytecode không hợp lệ, preview, module access và dependency.

### 2.1. Minor version 65535 và preview

Với major thuộc Java 12 trở lên, `minor_version` là `0` cho định dạng bình thường hoặc `65535` cho class file sử dụng **preview features** tương ứng. Một class file đánh dấu preview chỉ được VM tải nếu:

- VM có **đúng phiên bản Java SE tương ứng major**;
- preview được bật khi chạy, ví dụ `--enable-preview`;
- những yêu cầu còn lại của class file vẫn hợp lệ.

Không phải “JDK mới hơn là chạy mọi preview cũ”: các preview class file không mặc nhiên tương thích tiến về trước. Nếu muốn triển khai sản phẩm không phụ thuộc preview, hãy phát hành class file thông thường và kiểm tra minor bằng `0`.

### 2.2. Lệnh kiểm tra file class

Sau khi biên dịch:

```bash
javac --release 17 -encoding UTF-8 GeneratorCompatibilityDemo.java
javap -verbose GeneratorTemplate
```

Trong output `javap -verbose`, tìm:

```text
  minor version: 0
  major version: 61
```

Đừng kết luận toàn bộ lớp **được thư viện sinh ở runtime** có major `61` chỉ vì mã nguồn ứng dụng dùng `--release 17`. Thư viện có thể tạo bytecode trong bộ nhớ với **target class-file riêng**, độc lập với file `.class` của ứng dụng. Phải kiểm tra **chính bytecode thực tế** thư viện phát ra hoặc kết quả của quá trình định nghĩa lớp trên runtime đích.

## 3. Đối chiếu phiên bản của thư viện sinh mã và các dependency

Ví dụ các nhóm thư viện có liên quan:

- **ASM:** làm việc trực tiếp với class file để đọc, biến đổi hoặc phát sinh bytecode.
- **Byte Buddy:** cung cấp API cấp cao để tạo, thay đổi và instrument class; nó có tài liệu *Java version compatibility* riêng.
- **Framework thử nghiệm, proxy hoặc instrumentation:** có thể dùng ASM/Byte Buddy gián tiếp (kể cả khi tên những thư viện đó không xuất hiện trong mã ứng dụng).
- **Plugin biên dịch và build:** có thể kèm engine bytecode riêng trong classpath của plugin, không giống dependency runtime của ứng dụng.

**Không dùng các con số phiên bản thư viện được ghi trong một bài viết cũ làm tiêu chuẩn mãi mãi.** Thay vào đó:

1. Xác định **JDK phiên bản nào thực sự được triển khai**.
2. Đọc compatibility matrix/release notes **của phiên bản thư viện đang khóa trong dependency lockfile**. Kiểm tra cả mức JDK tối thiểu *để chạy thư viện* và class-file version tối đa *mà thư viện phân tích/phát ra*.
3. Truy ngược dependency transitively đưa engine bytecode vào ứng dụng hoặc plugin. Một plugin đang đóng gói bản parser cũ có thể hoạt động khác với bản bạn khai báo trực tiếp.
4. Kiểm tra những mode cụ thể được sử dụng: tạo subclass/proxy, đọc class đã biên dịch bằng JDK mới, transformer/agent, mock final class, hidden class, v.v. “Hỗ trợ Java 21” không nhất thiết bao phủ mọi cách tích hợp và cấu hình.

Ví dụ cách xem dependency Maven (lệnh cần plugin tương ứng, chạy trong dự án thực tế):

```bash
mvn -version
mvn dependency:tree
```

Với Gradle, khi dự án có Gradle wrapper:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
```

Các lệnh trên chỉ cung cấp **bằng chứng dependency/toolchain**, không tự chạy kiểm tra sinh bytecode. Nếu thư viện nằm trong classpath **build plugin** hoặc bị *shaded/relocated* trong một JAR, riêng cây dependency runtime có thể không lộ đúng bản parser. Kiểm tra tài liệu plugin và nội dung artifact khi cần.

**Nguồn cập nhật chính thức để đối chiếu phiên bản:**

- [ASM — Release/Versions](https://asm.ow2.io/versions.html)
- [Byte Buddy — Java version compatibility](https://github.com/raphw/byte-buddy#java-version-compatibility)

Tại thời điểm kiểm tra trong dự án, hãy căn cứ bản **release đã khóa và release notes đi kèm**; đừng tự nâng version bừa bãi nếu có khác biệt API hoặc yêu cầu runtime.

## 4. Các lỗi đặc trưng khi thư viện hoặc bytecode không tương thích

| Hiện tượng | Nguồn lỗi thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| `UnsupportedClassVersionError` khi JVM nạp/định nghĩa class | Major/minor của class file không được runtime hỗ trợ | Kiểm tra bytecode thực, JDK chạy và preview |
| Parser báo “unsupported class file major version” từ thư viện | Thư viện đọc bytecode chưa hỗ trợ phiên bản đó | Compatibility matrix của ASM/Byte Buddy/plugin thực tế |
| `ClassFormatError` | Cấu trúc class-file không hợp lệ | Trường header, constant pool, attributes, output generator |
| `VerifyError` | Bytecode/stack map frame không thỏa verifier | Cách generator tính frame, operand stack, control-flow |
| `NoClassDefFoundError` hoặc lỗi liên kết | Dependency của lớp sinh không có trong runtime hoặc linkage thất bại | Classpath/module path, package, loader, dependency |
| `IllegalAccessError` | Bytecode được tạo cố dùng thành viên/lớp không được phép truy cập | `public/private`, nestmates, module exports, loader identity |
| `InaccessibleObjectException` khi deep reflection | Package không được `opens` cho caller | Module descriptor, `Lookup` phù hợp, thiết kế API |
| `IllegalAccessException` khi `Lookup.defineHiddenClass` | Lookup không có full privilege phù hợp | Cách nhận lookup, package/module của class bytes |
| `IllegalArgumentException` khi `defineHiddenClass` | Ví dụ bytecode class nằm ở package khác lookup class | Quy tắc package và đầu vào của API |

Một error message có chứa chữ *class version* **chưa đủ** để biết JVM hay thư viện bên ngoài đang ném lỗi. Cần xem loại exception, stack trace và tên package chứa code tạo lỗi.

Không chữa `VerifyError` bằng cách giảm class-file major một cách cơ học; verifier còn kiểm tra cấu trúc bytecode và stack map frames. Việc sửa hai byte header để “giảm version” **không tự biến mã dùng đặc tính JDK mới thành bytecode tương thích JDK cũ**.

## 5. Java 15: hidden class thay cho kỹ thuật runtime không còn phù hợp

Java 15 chuẩn hóa API:

```java
MethodHandles.lookup().defineHiddenClass(bytecode, true)
```

qua **JEP 371 — Hidden Classes**. Đây là cơ chế phù hợp khi một runtime muốn tạo lớp phụ trợ **không cần tham chiếu danh định bằng binary name**, chẳng hạn một số mô hình code generation.

Những điểm cần xác minh:

- `Lookup.defineHiddenClass(...)` yêu cầu lookup có quyền thích hợp; bytecode class phải thuộc **cùng package** với lookup class, theo quy định của API.
- Lớp ẩn có `Class<?>` thật và có thể gọi phương thức với `MethodHandle` phù hợp, nhưng không được tìm theo tên bằng `Class.forName(hidden.getName())` như lớp thông thường.
- `Class.isHidden()` kiểm tra tính chất của lớp sinh ra.
- `ClassOption.NESTMATE` (nếu dùng) có thể thay đổi quan hệ nest, nhưng không loại bỏ quy tắc truy cập module hoặc biến một `Lookup` thiếu quyền thành đầy đủ quyền.
- Một class file có major phù hợp vẫn có thể không định nghĩa được vì lỗi quyền lookup, lỗi định dạng hoặc bytecode không hợp lệ.

Phân biệt với `Lookup.defineClass(byte[])`, API định nghĩa **lớp có tên**, có thể phù hợp khi dự án cần tải class theo binary name. Đừng coi hai API là thay thế nhau về danh tính/tìm kiếm lớp.

**Không áp dụng hướng dẫn cũ dựa vào `sun.misc.Unsafe.defineAnonymousClass`:** API nội bộ này đã bị loại bỏ từ JDK 17. Đối với code generation trên Java hiện đại, hãy sử dụng API công khai phù hợp hoặc thư viện tương thích và được bảo trì; không lấy “truy cập nội bộ JVM” làm cơ sở giải pháp.

## 6. Chương trình tự kiểm tra: header và khả năng định nghĩa hidden class

Chương trình dưới đây là **smoke test không cần ASM/Byte Buddy**. Nó kiểm tra các nguyên tắc mà bạn cũng nên áp dụng với bytes do một thư viện thực tế tạo:

1. Đọc một class file đã biên dịch, xem magic/minor/major.
2. Kiểm tra class file phù hợp phiên bản runtime ở bước đầu.
3. Định nghĩa hidden class qua API chuẩn từ Java 15 và gọi phương thức tĩnh của nó.
4. **Sửa header trên một bản sao trong bộ nhớ** để tạo *tình huống âm* có major lớn hơn runtime; xác nhận JVM từ chối bằng `UnsupportedClassVersionError`.

**Quan trọng:** Bước cuối là một phép thử **giả lập class-file version không hỗ trợ**, không phải phương pháp tạo hoặc nâng/hạ phiên bản bytecode trong ứng dụng. Bài kiểm tra thực sự đối với thư viện bên ngoài phải lấy **bytecode do chính thư viện ấy sinh ra**.

### 6.1. Tệp nguồn hoàn chỉnh

Tạo tệp `GeneratorCompatibilityDemo.java` trong một thư mục riêng:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class GeneratorCompatibilityDemo {
    private static byte[] templateBytes() throws IOException {
        try (InputStream in = GeneratorTemplate.class
                .getResourceAsStream("GeneratorTemplate.class")) {
            if (in == null) {
                throw new IOException("GeneratorTemplate.class not found");
            }
            return in.readAllBytes();
        }
    }

    private static int u2(byte[] data, int index) {
        return ((data[index] & 0xff) << 8) | (data[index + 1] & 0xff);
    }

    private static int u4(byte[] data, int index) {
        return (u2(data, index) << 16) | u2(data, index + 2);
    }

    private static void check(String name, boolean success) {
        if (!success) {
            throw new AssertionError(name + " failed");
        }
        System.out.println(name + "=PASS");
    }

    public static void main(String[] args) throws Throwable {
        byte[] original = templateBytes();
        int minor = u2(original, 4);
        int major = u2(original, 6);
        int runtimeMajor = Runtime.version().feature() + 44;

        check("magic", u4(original, 0) == 0xCAFEBABE);
        System.out.println("compiledMajor=" + major);
        System.out.println("compiledMinor=" + minor);
        check("targetSupported", major <= runtimeMajor && minor == 0);

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(original, true);
        Class<?> generated = hiddenLookup.lookupClass();
        check("hiddenDefined", generated.isHidden());

        int answer = (int) hiddenLookup.findStatic(
                generated, "answer", MethodType.methodType(int.class))
                .invokeExact();
        check("generatedMethod", answer == 42);

        byte[] tooNew = original.clone();
        int unsupportedMajor = runtimeMajor + 1;
        tooNew[6] = (byte) (unsupportedMajor >>> 8);
        tooNew[7] = (byte) unsupportedMajor;
        check("futureHeader", u2(tooNew, 6) > runtimeMajor);

        boolean rejected = false;
        try {
            MethodHandles.lookup().defineHiddenClass(tooNew, false);
        } catch (UnsupportedClassVersionError expected) {
            rejected = true;
        }
        check("futureRejected", rejected);
    }
}

class GeneratorTemplate {
    public static int answer() {
        return 42;
    }
}
```

Mã gồm một lớp public có `main` và một lớp package-private `GeneratorTemplate` cùng **unnamed package** để ví dụ gọn và tuân thủ ràng buộc cùng package của `Lookup.defineHiddenClass`. Trong dự án thực, đặt class helper và code định nghĩa lớp ở **package/module phù hợp**; chỉ sao chép bytecode class có package khác lookup sẽ không hợp lệ.

### 6.2. Biên dịch và chạy

Tại thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 GeneratorCompatibilityDemo.java
java GeneratorCompatibilityDemo
```

Lệnh `--release 17` cố định bytecode của hai lớp nguồn ở **major 61** và chỉ cho phép các API tương thích Java 17. Máy chạy cần JDK/JRE **17 hoặc mới hơn**. Nếu chạy chương trình trên JDK mới, chương trình vẫn tạo ra `61.0` cho lớp nguồn nhờ `--release 17`.

**Stdout chính xác:**

```text
magic=PASS
compiledMajor=61
compiledMinor=0
targetSupported=PASS
hiddenDefined=PASS
generatedMethod=PASS
futureHeader=PASS
futureRejected=PASS
```

Bài kiểm tra có thể chạy lại trên JDK khác từ phiên bản 17 trở lên. Với JDK đó, `runtimeMajor` được lấy từ `Runtime.version().feature()`. Nó tạo một header lớn hơn ngưỡng runtime để xác minh *negative path* thay vì hardcode một class version bị từ chối trong mọi JDK.

**Giải thích kết quả:**

- `magic=PASS` xác nhận bốn byte đầu là `0xCAFEBABE`.
- `compiledMajor=61` và `compiledMinor=0` cho biết class được biên dịch cho Java 17 không sử dụng marker preview.
- `targetSupported=PASS` là bộ lọc phiên bản bước đầu, **không chứng minh bytecode hợp lệ**. Phép `defineHiddenClass` sau đó mới kiểm tra việc JVM thực sự có thể định nghĩa lớp.
- `hiddenDefined=PASS` chứng minh API công khai tạo hidden class; `generatedMethod=PASS` xác nhận gọi phương thức thành công.
- `futureHeader=PASS` chứng minh bản sao header vượt ngưỡng major runtime. `futureRejected=PASS` kiểm tra đúng exception `UnsupportedClassVersionError`.

Không cần phát hành mã “sửa byte header” vào production. Đây chỉ là một test nhỏ có phạm vi cố định, kiểm tra phản ứng của runtime với đầu vào không được hỗ trợ.

## 7. Kiểm tra thư viện thực thay cho bytecode giả lập

Khi áp dụng vào Byte Buddy, ASM hoặc một framework sinh mã thực tế, cần thay byte `original` trong ví dụ bằng **bytes đầu ra thực tế của generator**. Mỗi thư viện có API phát class bytes khác nhau; hãy dùng API và hướng dẫn của đúng phiên bản đang sử dụng để lấy dữ liệu đó.

### 7.1. Kiểm tra trước khi định nghĩa lớp

Trong một **test riêng**, thực hiện:

1. Chạy logic sinh mã với các tham số đại diện cho production.
2. Nhận chính xác mảng byte class đã sinh.
3. Kiểm tra `CA FE BA BE`, major/minor và kỳ vọng `target JDK`.
4. Nếu dùng thư viện đọc/transform bytecode, cho parser của thư viện **đang khóa version** đọc class bytecode đích.
5. Định nghĩa/tải class trên JVM đích với class loader hoặc `Lookup` hợp lệ.
6. Gọi một phương thức cụ thể, xác nhận hành vi; với transformer, kiểm tra class thật sau khi biến đổi.

Lưu ý: việc truyền class bytes vào `Lookup.defineHiddenClass` chỉ phù hợp với **trường hợp muốn hidden class**. Nếu thư viện của bạn chủ đích tạo lớp có binary name để code khác gọi qua tên, hãy kiểm tra trên **cơ chế định nghĩa lớp thật** của thư viện; không ép nó dùng hidden class chỉ để vượt qua smoke test.

### 7.2. Kiểm tra dependency và bytecode ở nhiều môi trường

Một kiểm thử trên máy phát triển có JDK mới **không thay thế** kiểm thử trên JVM production. Để làm rõ version thật:

```bash
java -version
javac -version
```

Trong Maven/Gradle, kiểm tra toolchain/Java launcher thực tế được cấu hình trong CI và artifact/container triển khai, không chỉ biến môi trường trong shell. Nếu dùng Docker, chú ý image ở **build stage** có thể khác JDK ở **runtime stage**.

Việc `javac --release 17` thành công giúp bảo đảm class file của **mã nguồn được javac biên dịch** và các API công khai của Java 17; nó không tự ràng buộc toàn bộ class do generator/plugin tự viết ra lúc chạy. Nếu phụ thuộc vào thư viện version mới có runtime API yêu cầu Java 21, class file major thấp của ứng dụng cũng không làm JDK 17 chạy được thư viện ấy.

## 8. Những khía cạnh ngoài major version dễ bị bỏ sót

### 8.1. Stack map frames và verifier

Đối với class file mới, verifier yêu cầu tính hợp lệ của operand stack, local variables, control-flow và stack map frame theo định dạng áp dụng. Một thư viện sinh bytecode không đúng có thể tạo class **major hợp lệ** nhưng vẫn gây `VerifyError`. Hãy test các nhánh điều kiện, try/catch, constructor, generic bridge method, interface method và trường hợp instrument method phức tạp mà ứng dụng thật sử dụng.

### 8.2. Module và reflective access

Từ Java 9, JPMS kiểm soát `exports` và `opens`. Một framework thao tác private field/method có thể cần module đích mở package cho framework. Với Java hiện đại, **strong encapsulation** khiến lời gọi reflection vào nội bộ JDK có thể thất bại.

Nếu gặp `InaccessibleObjectException`, đừng kết luận bytecode quá mới. Hãy kiểm tra module và package được truy cập. Tùy chọn `--add-opens` có thể là công cụ chẩn đoán hoặc tương thích có phạm vi, nhưng không nên làm giải pháp lâu dài nếu dự án có thể dùng API công khai và mô hình module rõ ràng.

### 8.3. Class loader, nest và package

Một class sinh động có thể chạy được trên classpath nhưng không tương tác được với package-private members trong một môi trường class loader khác. Trong Java, **runtime package** phụ thuộc vào package và class loader; tên package trùng nhau chưa đủ.

Nếu sinh hidden class với tùy chọn `NESTMATE`, cần xác minh đúng nest host và quyền lookup; nó không tự mở module hay cấp quyền truy cập private của mọi lớp trong module. Đặc biệt khi sử dụng `privateLookupIn` qua ranh giới module, lookup nhận được có giới hạn quyền; không mặc nhiên đủ quyền gọi `defineHiddenClass`.

### 8.4. Bytecode preview và loại đặc tính class file mới

Nếu một ứng dụng dùng preview của một JDK, classfile có thể mang minor `65535`. Dù major không vượt runtime, một VM sai phiên bản hoặc không bật preview vẫn có thể từ chối. Một thư viện phân tích bytecode còn phải hiểu các attribute và cấu trúc liên quan.

Các Java release mới còn mang thay đổi trong classfile attributes hoặc verification rules. Vì vậy “thư viện nhận ra major version” **chưa đủ** để kết luận nó hỗ trợ mọi đặc tính của class file ở release đó.

## 9. Bộ tiêu chí QA trước khi đưa thư viện sinh mã vào production

| Hạng mục | Cách xác minh | Tiêu chí PASS |
| --- | --- | --- |
| Runtime thực tế | `java -version` trên container/service/CI | Đúng phiên bản đã quyết định |
| Compiler/toolchain | `javac -version`, `--release`, cấu hình Maven/Gradle | Target bytecode rõ ràng |
| Tính tương thích thư viện | Compatibility matrix và release notes cho bản đang khóa | Hỗ trợ đúng JDK và class-file target |
| Dependency transitively/shaded | Dependency tree, build plugin classpath, artifact nếu cần | Không bị parser/engine cũ ngoài dự kiến |
| Generated major/minor | Đọc header bytecode thực tế; `javap -verbose` nếu có tệp | Trong giới hạn VM đích; preview được xử lý rõ |
| Load/define | Gọi API định nghĩa class trong môi trường thực | Không có lỗi version, format, verify hoặc linkage |
| Access/module | Dùng đúng `Lookup`, package, module | Không có lỗi quyền hoặc mở package sai |
| Hành vi | Gọi phương thức sinh và so kết quả | Giá trị và side effect đúng |
| Thử JDK thấp nhất được hỗ trợ | Chạy test trên runtime thấp nhất trong chính sách | Không dùng API/classfile quá mới |
| Thử JDK hiện hành dự kiến nâng cấp | Ma trận CI trên JDK mới trong phạm vi hỗ trợ | Không bị parser cũ hay thay đổi hành vi |
| Đường phát hành thật | Chạy artifact như production (module path, classpath, container) | Không khác biệt dependency, launcher hoặc agents |

Đừng gắn nhãn “tương thích” chỉ vì cả ứng dụng và generator compile được. Một bộ kiểm thử tốt phải đi qua **sinh bytes → tải/định nghĩa class → gọi phương thức → kiểm tra kết quả** trên runtime thật.

### Gợi ý tổ chức CI

- Dùng toolchain/Java launcher cụ thể cho test trên từng JDK mục tiêu; không dựa vào máy build chọn JDK ngẫu nhiên.
- Chạy một smoke test sinh lớp tối thiểu và một test có cấu trúc phức tạp hơn (branch, exception handler, interface hoặc constructor).
- Khóa phiên bản dependency, kể cả build plugin và instrumentation agent khi có.
- Nếu hỗ trợ nhiều JDK, chạy ma trận trên **JDK thấp nhất** và **những JDK triển khai thực tế**; tránh tuyên bố hỗ trợ Java mới chỉ vì dự án compile trên một Java cũ.
- Thu thập log về version JDK, tên/phiên bản thư viện, classfile major/minor và stack trace lỗi. Không ghi dump bytecode chứa dữ liệu nhạy cảm ra nơi truy cập rộng.
- Kiểm tra artifact/container cuối cùng như người dùng sẽ chạy, đặc biệt khi build và deploy dùng hai image khác nhau.

## 10. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Cho rằng `--release 17` ép **mọi generator** xuất major `61` | Generator có thể đặt target riêng | Đọc bytecode thực do generator tạo |
| JVM hỗ trợ version mới nên nghĩ parser ASM cũ cũng hỗ trợ | Parser báo unsupported class-file version | Nâng/kiểm tra phiên bản parser/plugin theo release notes |
| Thấy `UnsupportedClassVersionError` rồi sửa hai byte major | Không loại được đặc tính/bytecode mới | Sinh lại class với target hợp lệ từ công cụ hỗ trợ |
| Test bytecode trên máy build nhưng deploy JDK cũ | Runtime production từ chối | Test trên đúng image/JDK triển khai |
| Bỏ qua `minor=65535` | Preview class file bị từ chối | Dùng đúng JDK cùng release và `--enable-preview` hoặc bỏ preview |
| Dùng `sun.misc.Unsafe.defineAnonymousClass` cũ | API nội bộ đã bị loại | Dùng `Lookup.defineHiddenClass` hoặc API được hỗ trợ |
| Bỏ qua quyền `Lookup` và package | `IllegalAccessException`/`IllegalArgumentException` | Dùng lookup có quyền thích hợp, cùng runtime package |
| Bỏ qua module `opens` cho deep reflection | `InaccessibleObjectException` | Thiết kế public API, opens có phạm vi đúng |
| Chỉ thử class rỗng, không thử branch/exception | Bytecode có thể lỗi stack map frame | Thêm test định nghĩa và thực thi các code path đại diện |
| So sánh message exception chính xác | Message thay đổi theo VM/library | Khẳng định kiểu lỗi, điều kiện và hành vi |
| Chỉ xem dependency runtime | Có thể bỏ sót plugin hoặc shaded bytecode engine | Kiểm tra cả build plugin và artifact |
| Nghĩ phiên bản bytecode hợp lệ bảo đảm tương thích hoàn toàn | Có thể lỗi linkage/API/class loader/module | Chạy smoke test end-to-end trên runtime đích |

## 11. Bài tập tự kiểm tra

**Bài 1.** Một ứng dụng được biên dịch với `--release 17`, nhưng một thư viện tạo class có major `65`. Nếu chạy trên JVM 17, điều gì xảy ra?

**Đáp án:** JVM 17 chỉ hỗ trợ class file đến major `61`; khi nạp/định nghĩa class major `65` sẽ gặp lỗi phiên bản, thường là `UnsupportedClassVersionError`. `--release 17` của mã ứng dụng không tự kiểm soát generator.

**Bài 2.** JVM 25 hiểu class file major `69`. Có chắc một plugin dùng bytecode parser cũ sẽ đọc được class major `69` không?

**Đáp án:** Không. Support của **JVM** và support của **bytecode parser** là hai lớp khác nhau. Cần đối chiếu phiên bản plugin/engine với release notes thực tế và chạy test đọc class tương ứng.

**Bài 3.** Một class file có major `61` và minor `65535`. Chạy trên JDK 21 với `--enable-preview` có đủ không?

**Đáp án:** Không. Đây là class file preview của **Java 17**, chỉ được tải với đúng release Java 17 và preview enabled; JDK 21 không hỗ trợ tải preview classfile của release khác.

**Bài 4.** Vì sao smoke test cần gọi một phương thức của class được sinh thay vì chỉ đọc header?

**Đáp án:** Major/minor hợp lệ không bảo đảm bytecode, verifier, linker, class loader và quyền truy cập đều hợp lệ. Gọi phương thức cụ thể kiểm tra thêm hành vi thực tế.

**Bài 5.** Muốn định nghĩa hidden class ở module khác với một `Lookup` không có quyền đầy đủ, có thể chỉ cần đổi tên package trong bytecode không?

**Đáp án:** Không. `defineHiddenClass` kiểm tra quyền lookup, module và package của class bytes; phải sử dụng ngữ cảnh/lookup hợp lệ, không thể lách bằng thay ký tự trong header/tên.

## Ghi nhớ

**Kiểm tra tương thích thư viện sinh mã với JDK triển khai cần nhiều hơn “build xanh”.** Xác định **JDK thực tế**, **generator/parser đang được dùng**, **class-file major/minor** của output và **quyền định nghĩa/truy cập lớp**. Java 15 cung cấp `Lookup.defineHiddenClass` cho trường hợp sinh hidden class; không sử dụng API anonymous-class nội bộ đã bị loại. Hãy kiểm chứng **bytecode thật trên JDK thật**, trong cấu hình production tương ứng, bằng quá trình nạp/định nghĩa và gọi hành vi có expected rõ ràng.

### Tài liệu chính thức và nguồn kiểm tra phiên bản

- [Java Virtual Machine Specification — Chapter 4: Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html)
- [Oracle JDK 17 — MethodHandles.Lookup.defineHiddenClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...))
- [OpenJDK JEP 371 — Hidden Classes (Java 15)](https://openjdk.org/jeps/371)
- [Oracle JDK 17 Release Notes — Removal of Unsafe::defineAnonymousClass](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html)
- [ASM — Official version history](https://asm.ow2.io/versions.html)
- [Byte Buddy — Java version compatibility table](https://github.com/raphw/byte-buddy#java-version-compatibility)
