# ClassFormatError, VerifyError và lỗi phiên bản class khi định nghĩa hidden class (Java 15+)

## 1. Tại sao hidden class cũng có thể gặp lỗi class file?

Từ **Java 15**, Java hỗ trợ tạo *hidden class* bằng `MethodHandles.Lookup.defineHiddenClass(byte[] bytes, boolean initialize, ClassOption... options)`. Thay vì tìm một lớp đã có theo tên, API nhận **bytecode ở định dạng file `.class`** và nhờ JVM định nghĩa một lớp mới. Kết quả thành công là một `MethodHandles.Lookup` gắn với hidden class vừa tạo.

Dù gọi là “hidden”, JVM **vẫn phải đọc cấu trúc class file, kiểm tra phiên bản, xác minh bytecode và liên kết lớp** theo các quy tắc an toàn. Vì thế dữ liệu `byte[]` không hợp lệ có thể gây `ClassFormatError`, `VerifyError` hoặc `UnsupportedClassVersionError`.

Bài học phân biệt rõ ba lỗi, cách tái hiện trên Java 17+, ý nghĩa của chúng trong luồng `defineHiddenClass` và cách sửa nguyên nhân. Các API này vẫn được hỗ trợ ở các JDK hiện đại; không dùng cơ chế cũ hay tùy chọn tắt kiểm chứng bytecode.

## 2. Ba loại lỗi: cùng liên quan class file nhưng khác nguyên nhân

| Lỗi | Khi nào xảy ra? | Bản chất | Ví dụ nguyên nhân |
| --- | --- | --- | --- |
| `ClassFormatError` | JVM không thể diễn giải byte đầu vào thành một cấu trúc `ClassFile` hợp lệ | **Sai định dạng class file** | Sai 4 byte magic, constant pool lỗi, cấu trúc thuộc tính hỏng |
| `VerifyError` | Cấu trúc file đọc được, nhưng bytecode không vượt qua kiểm chứng | **Sai quy tắc xác minh mã** | Lệnh trả giá trị không khớp kiểu khai báo, trạng thái operand stack không hợp lệ |
| `UnsupportedClassVersionError` | `major_version` hoặc `minor_version` không được JVM hiện tại hỗ trợ | **Sai/tương thích phiên bản class file** | Class biên dịch bằng JDK quá mới so với runtime, hoặc file dùng preview bytecode không phù hợp |

**Điểm quan trọng:** `UnsupportedClassVersionError` là **một lớp con của `ClassFormatError`**. Vì vậy, khi phân loại lỗi bằng `catch`, phải bắt `UnsupportedClassVersionError` trước `ClassFormatError`. Ngược lại, `VerifyError` là nhánh riêng trực tiếp từ `LinkageError`, **không phải** lớp con của `ClassFormatError`.

## 3. Phân cấp ngoại lệ chính xác

```text
java.lang.Throwable
  └── java.lang.Error
       └── java.lang.LinkageError
            ├── java.lang.ClassFormatError
            │    └── java.lang.UnsupportedClassVersionError
            └── java.lang.VerifyError
```

Tất cả đều là `Error` không được kiểm tra bắt buộc tại thời điểm biên dịch (*unchecked*). Chúng khác `Exception` thông thường:

- Không cần thêm chúng vào `throws` khi viết phương thức gọi `defineHiddenClass`.
- Trong ứng dụng sản xuất, thông thường **không nên bắt `Error` để tiếp tục vận hành như không có gì xảy ra**. Tập trung sửa bytecode hoặc cấu hình sai.
- Trong công cụ nạp mã động hoặc bài kiểm thử, có thể bắt từng kiểu cụ thể tại ranh giới định nghĩa lớp để ghi nhận lỗi và dừng ca xử lý đó.
- `catch (ClassFormatError e)` quá sớm sẽ bắt cả `UnsupportedClassVersionError`, làm mất phân loại lỗi phiên bản.

Một cách viết phân loại đúng:

```java
try {
    lookup.defineHiddenClass(classBytes, false);
} catch (UnsupportedClassVersionError e) {
    // Phiên bản class không được JVM này hỗ trợ.
} catch (ClassFormatError e) {
    // Cấu trúc class file không hợp lệ.
} catch (VerifyError e) {
    // Bytecode không vượt qua kiểm chứng.
}
```

Đoạn mã trên chỉ minh họa thứ tự `catch`: cần đặt trong phương thức, định nghĩa `lookup`/`classBytes`, và xử lý `IllegalAccessException` theo ngữ cảnh. Chương trình đầy đủ chạy được ở phần 7.

## 4. JVM thực hiện những bước gì khi tạo hidden class?

Luồng khái niệm với `MethodHandles.Lookup.defineHiddenClass`:

```text
byte[] classBytes
       |
       v
Đọc header + cấu trúc ClassFile
       |-- Hỏng cấu trúc ------------> ClassFormatError
       |-- Phiên bản không hỗ trợ ---> UnsupportedClassVersionError
       v
Xác minh bytecode (verification)
       |-- Không hợp lệ ------------> VerifyError
       v
Liên kết và định nghĩa hidden class
       |-- Vấn đề liên kết khác ----> LinkageError / lỗi chuyên biệt
       v
MethodHandles.Lookup của hidden class
       |
       v
lookup.lookupClass().isHidden() == true
```

Đây là **mô hình chẩn đoán**, không phải cam kết rằng mọi JVM phải tiến hành hoặc báo lỗi theo thứ tự tuyệt đối này với mọi tệp hỏng đồng thời nhiều chỗ. JVM có thể phát hiện các bất thường khác nhau tại các pha xử lý phù hợp với đặc tả.

Một lời gọi thông thường:

```java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup hiddenLookup = MethodHandles.lookup()
        .defineHiddenClass(classBytes, false);

Class<?> hiddenClass = hiddenLookup.lookupClass();
```

Hai tham số quan trọng:

- `classBytes` phải là toàn bộ class file hợp lệ, không phải mã nguồn `.java` hoặc văn bản ngẫu nhiên.
- `false` có nghĩa **không yêu cầu khởi tạo lớp ngay tại lời gọi này**. Nó **không** có nghĩa “bỏ qua việc kiểm chứng bytecode”. Class vẫn phải được JVM định nghĩa và liên kết đúng.

`defineHiddenClass` còn đòi hỏi quyền truy cập đầy đủ của `Lookup` và yêu cầu class nằm trong cùng runtime package theo hợp đồng API. Nếu vi phạm những điều kiện này, có thể gặp `IllegalAccessException` hoặc `IllegalArgumentException`; không nên quy chụp mọi lỗi từ phương thức thành ba loại lỗi đang học.

## 5. ClassFormatError: byte đầu vào không biểu diễn được class file

JVM kỳ vọng cấu trúc class file theo Java Virtual Machine Specification (JVMS). Phần đầu file có bố cục:

```text
offset (byte)    field
0..3             magic = 0xCAFEBABE
4..5             minor_version
6..7             major_version
8..9             constant_pool_count
...              constant_pool, flags, fields, methods, attributes ...
```

Đây là các byte ở dạng **big-endian** cho giá trị nhiều byte. Nếu 4 byte đầu không phải `CA FE BA BE`, hoặc các phần cấu trúc khác không thể được diễn giải theo JVMS, JVM có thể ném `ClassFormatError`.

Ví dụ phá magic:

```java
byte[] badMagic = originalClassBytes.clone();
badMagic[0] = 0;
lookup.defineHiddenClass(badMagic, false); // ClassFormatError
```

Lời gọi chỉ minh họa; `originalClassBytes` và `lookup` phải tồn tại trong code chạy. Việc `clone()` tạo bản sao giúp không phá hủy dữ liệu hợp lệ gốc.

Những tình huống thực tế thường dẫn tới lỗi định dạng:

- Đọc nhầm file `.java`, JSON hoặc nội dung HTTP thay vì file `.class`.
- File `.class` bị cắt ngắn, ghi lỗi hoặc bị thao tác byte không chính xác.
- Công cụ sinh/sửa class file viết sai constant pool, số lượng mục, độ dài attribute hoặc chỉ số tham chiếu.
- Dữ liệu đầu vào không khớp cấu trúc `ClassFile` mà JVM có thể giải mã.

**Cách sửa:** kiểm tra nguồn `byte[]`, magic, độ dài file; tái biên dịch từ mã nguồn tin cậy; nâng cấp công cụ sinh bytecode cho phiên bản Java đang dùng; tránh tự sửa các offset nếu không có parser class file đúng đặc tả.

## 6. VerifyError: class file đọc được nhưng bytecode không hợp lệ

`VerifyError` thường xuất hiện khi **cấu trúc file class hợp lệ ở mức định dạng**, nhưng nội dung lệnh và loại dữ liệu bên trong không bảo đảm các quy tắc kiểm chứng JVM.

Ví dụ một phương thức đã biên dịch có chữ ký:

```java
static int answer() {
    return 42;
}
```

Với bytecode do `javac --release 17` sinh ra trong ví dụ này, phần lệnh cho `answer()` là:

```text
bipush 42   // opcode 0x10, toán hạng 0x2A
ireturn     // opcode 0xAC: trả về int
```

Nếu sửa **duy nhất** opcode `ireturn` thành `areturn` (opcode `0xB0`), phương thức vẫn khai báo trả về `int` nhưng lệnh cuối lại cố trả về một tham chiếu đối tượng. Verifier phát hiện kiểu dữ liệu không phù hợp và có thể ném `VerifyError`.

So sánh:

| Đúng | Bị sửa sai |
| --- | --- |
| `bipush 42; ireturn` | `bipush 42; areturn` |
| Stack chứa `int`, lệnh trả `int` | Stack chứa `int`, lệnh muốn trả reference |
| Kiểm chứng thành công | `VerifyError` |

Trong thực tế, `VerifyError` thường là dấu hiệu **bytecode được sinh hoặc biến đổi sai**, không phải lỗi cú pháp Java phổ thông. Với code Java bình thường biên dịch bằng `javac`, compiler sẽ không cho bạn viết trực tiếp một phương thức trả `String` khi khai báo `int`: lỗi đó đã bị chặn ở giai đoạn compile. Vấn đề xuất hiện khi các công cụ *bytecode engineering*, instrumentation hoặc dữ liệu class file không đúng quy tắc.

**Cách sửa:** xác nhận bản class file thực tế, biên dịch lại; kiểm tra instrumenter/bytecode generator, kiểu dữ liệu stack, `StackMapTable`, nhánh điều khiển và chữ ký method; dùng công cụ tương thích class-file version. Không xử lý bằng cách tắt bytecode verifier.

## 7. Chương trình Java 17+ tạo ra cả ba lỗi, với stdout đã xác minh

Ví dụ sau là một **ứng dụng học tập độc lập**. Chương trình biên dịch nested class `Template`, đọc bytecode của nó, sau đó tạo các **bản sao bị sửa trong bộ nhớ** để kích hoạt từng lỗi. Không cần thư viện ngoài JDK và không ghi đè file `.class` hợp lệ.

Tạo file **`HiddenClassFailureDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public class HiddenClassFailureDemo {
    static class Template {
        static int answer() {
            return 42;
        }
    }

    static byte[] readTemplateBytes() throws IOException {
        Class<?> type = Template.class;
        String resource = "/" + type.getName().replace('.', '/') + ".class";

        try (InputStream stream = type.getResourceAsStream(resource)) {
            if (stream == null) {
                throw new IOException("Missing " + resource);
            }
            return stream.readAllBytes();
        }
    }

    static void attempt(String label, byte[] bytes)
            throws IllegalAccessException {
        try {
            MethodHandles.lookup().defineHiddenClass(bytes, false);
            System.out.println(label + "=OK");
        } catch (UnsupportedClassVersionError e) {
            System.out.println(label + "=UnsupportedClassVersionError");
        } catch (ClassFormatError e) {
            System.out.println(label + "=ClassFormatError");
        } catch (VerifyError e) {
            System.out.println(label + "=VerifyError");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] original = readTemplateBytes();
        attempt("valid", original);

        // 1) Cố ý sửa magic (CA FE BA BE) thành magic sai.
        byte[] badMagic = original.clone();
        badMagic[0] = 0;
        attempt("badMagic", badMagic);

        // 2) Cố ý đặt major_version = 0x7F7F, quá mới để hỗ trợ.
        byte[] futureVersion = original.clone();
        futureVersion[6] = (byte) 0x7F;
        futureVersion[7] = (byte) 0x7F;
        attempt("futureVersion", futureVersion);

        // 3) Đổi bipush 42; ireturn -> bipush 42; areturn.
        // Chỉ dùng để minh họa bytecode cụ thể do javac sinh.
        byte[] invalidCode = original.clone();
        int matches = 0;

        for (int i = 0; i < invalidCode.length - 2; i++) {
            if ((invalidCode[i] & 0xff) == 0x10
                    && (invalidCode[i + 1] & 0xff) == 0x2A
                    && (invalidCode[i + 2] & 0xff) == 0xAC) {
                invalidCode[i + 2] = (byte) 0xB0;
                matches++;
                i += 2;
            }
        }

        System.out.println("patchMatches=" + matches);
        if (matches != 1) {
            throw new IllegalStateException("Unexpected template bytecode");
        }

        attempt("invalidCode", invalidCode);
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**; nên dùng `--release 17` cho demo để có bytecode mẫu cố định:

```bash
javac --release 17 HiddenClassFailureDemo.java
java HiddenClassFailureDemo
```

**Stdout chính xác**, đã kiểm chứng trên JDK 24 với class file được biên dịch bằng `javac --release 17`:

```text
valid=OK
badMagic=ClassFormatError
futureVersion=UnsupportedClassVersionError
patchMatches=1
invalidCode=VerifyError
```

Ý nghĩa kết quả:

1. **`valid=OK`**: bytecode của `Template` hợp lệ và được định nghĩa thành công dưới dạng hidden class.
2. **`badMagic=ClassFormatError`**: byte đầu của header đã bị thay đổi, nên dữ liệu không còn một class file đúng định dạng.
3. **`futureVersion=UnsupportedClassVersionError`**: `major_version` bị thay thành `0x7F7F`, lớn hơn phiên bản JVM hỗ trợ.
4. **`patchMatches=1`**: ví dụ tìm thấy duy nhất một đoạn byte `10 2A AC` và sửa opcode `AC` thành `B0`.
5. **`invalidCode=VerifyError`**: class file vẫn có cấu trúc đọc được, nhưng bytecode không hợp lệ về kiểu giá trị trả về.

### Lưu ý về kỹ thuật sửa byte trong demo

Cách tìm một chuỗi ba byte trong toàn bộ class file **chỉ nhằm tạo ví dụ ngắn có thể chạy**; nó dựa vào bytecode cụ thể của `javac --release 17` cho method `answer()`. Trên compiler khác hoặc sau khi đổi code, chuỗi byte có thể thay đổi hoặc trùng ở vị trí không mong muốn. Vì vậy chương trình kiểm tra `matches == 1` rồi dừng nếu mẫu không đúng.

**Không dùng cách dò byte thô này để thao tác class file trong sản phẩm.** Công cụ thực tế phải phân tích đúng constant pool, `Code` attribute, ranh giới method và các cấu trúc JVM liên quan. Mục tiêu demo chỉ để phân biệt ba loại lỗi, không phải xây dựng bytecode editor.

## 8. Lỗi phiên bản class: major/minor và Java runtime

Mỗi file `.class` chứa số phiên bản `major_version.minor_version`. Trong header:

```text
CA FE BA BE  00 00  00 3D ...
| magic   |  minor  major
                       0x003D = 61 (Java 17)
```

`major_version` là hai byte tại offset 6–7, `minor_version` ở offset 4–5. Một số cột mốc phiên bản class file chính thức:

| Java SE | Major class file |
| --- | ---: |
| Java 15 | 59 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |
| Java 25 | 69 |
| Java 26 | 70 |
| Java 27 (phát hành 9/2026) | 71 |

Bảng theo Java Virtual Machine Specification **Java SE 27**, là phiên bản mới nhất tại thời điểm bài học. Java 17 runtime hỗ trợ đến major 61; Java 24 runtime hỗ trợ đến major 68; Java 27 runtime hỗ trợ đến major 71. Việc **JVM chạy được class file cũ** không có nghĩa một JVM cũ chạy được bytecode vừa biên dịch bằng JDK mới.

Ví dụ, nếu công cụ sinh hidden class xuất class file major 65 (Java 21) nhưng ứng dụng chạy trên JDK 17 (tối đa 61), `defineHiddenClass` có thể ném `UnsupportedClassVersionError`. Đây là lỗi **không tương thích version**, không phải bằng chứng dữ liệu file đã hỏng magic hoặc method có kiểu sai.

### 8.1. `--release` giúp gì?

Nếu mã nguồn và các API sử dụng đều tương thích Java 17, biên dịch bằng:

```bash
javac --release 17 MyClass.java
```

sẽ tạo class file mục tiêu cho Java 17 (major 61), đồng thời giới hạn API nền tảng theo phiên bản tương ứng. Chỉ hạ `major_version` thủ công trong byte array **không** biến những instruction hoặc constant pool entry mới thành hợp lệ trên runtime cũ; cũng không giải quyết việc thư viện phụ thuộc đòi JDK cao hơn.

Nếu runtime thực sự cần các API hoặc tính năng mới, phải **nâng JVM chạy chương trình** thay vì ép `--release` không tương thích.

### 8.2. Trường hợp preview class file

JVMS còn quy định `minor_version = 65535` cho class file phụ thuộc **preview features của một phiên bản Java cụ thể** (với các major hỗ trợ cơ chế này). Preview class file gắn với đúng bản Java đã tạo nó; không thể giả định bật `--enable-preview` trên một JDK khác sẽ chạy được.

Bài học này sử dụng API `defineHiddenClass` **chính thức**, không cần `--enable-preview`. Trong sản phẩm, tránh dùng class file preview để làm artifact chạy đa phiên bản.

## 9. Các lỗi khác có thể đến từ `defineHiddenClass`

Không phải mọi thất bại khi định nghĩa hidden class đều là một trong ba lỗi trên. Theo hợp đồng API hiện hành:

| Lỗi/ngoại lệ | Tình huống gợi ý | Hướng kiểm tra |
| --- | --- | --- |
| `IllegalAccessException` | `Lookup` không có đủ quyền *full privilege access* | Nguồn `Lookup`, phạm vi gọi, quyền truy cập |
| `IllegalArgumentException` | Bytecode biểu diễn class ở package khác package của lookup, hoặc không phải class/interface phù hợp | Tên class trong class file và package hiện hành |
| `IncompatibleClassChangeError` | Quan hệ lớp cha/interface không hợp lệ khi liên kết | Superclass, superinterface, các dependency |
| `ClassCircularityError` | Phụ thuộc vòng khi xác lập quan hệ kế thừa | Sơ đồ kế thừa |
| `LinkageError` khác | Vấn đề liên kết không nằm trong các lỗi cụ thể đã nêu | Dependency và cấu hình runtime |
| `NullPointerException` | Truyền tham số `null` không hợp lệ | Kiểm tra dữ liệu và options |

Nếu `initialize=true`, chương trình cũng có thể gặp lỗi phát sinh từ **class initializer** khi JVM khởi tạo lớp. Đó không nhất thiết là lỗi cú pháp bytecode hoặc class-file version; cần phân biệt giai đoạn khởi tạo với giai đoạn định nghĩa/kiểm chứng.

Ngoài ra, `ClassNotFoundException` từ `Class.forName(...)` hoặc `ClassLoader.loadClass(...)` là một vấn đề **tìm class theo tên**. Hidden class vốn không thể được các API này tìm lại bằng binary name, nhưng điều đó **không đồng nghĩa** `ClassFormatError`, `VerifyError` hoặc `UnsupportedClassVersionError` đã xảy ra khi định nghĩa nó.

## 10. Cách kiểm tra nhanh class file và runtime

Khi gặp `UnsupportedClassVersionError` hoặc lỗi bytecode, hãy thu thập phiên bản JVM đang chạy và dữ liệu class file thực tế:

```bash
java -version
javac -version
javap -verbose HiddenClassFailureDemo
```

Lệnh `javap -verbose` hiển thị các thông tin như:

```text
minor version: 0
major version: 61
```

Nếu đã biên dịch demo bằng `--release 17`, đây là phiên bản class file dự kiến. `javap` có thể dùng cho file class đã được ghi ra đĩa; **hidden class tạo trong bộ nhớ không tự xuất thành một file `.class` để `javap` tìm bằng tên**. Với công cụ sinh hidden class, hãy giữ bản `byte[]` gốc hoặc lưu bản phân tích trong môi trường kiểm thử nếu cần chẩn đoán, không giả định có thể tìm lại hidden class bằng tên.

Quy trình debug có thể thực hiện theo thứ tự sau:

1. **Kiểm tra byte đầu và nguồn dữ liệu:** có phải byte của class file thật, không phải văn bản hoặc file bị cắt?
2. **Kiểm tra version:** `major/minor` của bytecode có nằm trong dải JVM hiện tại hỗ trợ, có dùng preview không?
3. **Kiểm tra bytecode:** nếu là `VerifyError`, xem stack types, method descriptors, control-flow và `StackMapTable` trong công cụ sinh/sửa.
4. **Kiểm tra điều kiện lookup:** cùng runtime package, full privilege access và các quyền cần thiết.
5. **Tách giai đoạn định nghĩa/khởi tạo:** nếu cần, chạy với `initialize=false` để phân biệt lỗi initializer; không hiểu nhầm nó là tắt verification.
6. **Kiểm thử trên runtime mục tiêu:** `java` được chạy trong CI và production phải dùng phiên bản dự kiến, không chỉ JDK của máy lập trình.

Không khuyến khích “sửa” bằng cách bỏ verifier, bỏ qua `Error` hoặc thay đổi bừa các byte version. Những cách đó che giấu lỗi và có thể làm chương trình không an toàn hoặc không ổn định.

## 11. Tình huống thực tế: phân biệt nguyên nhân và hướng xử lý

### Tình huống A: nhận byte array từ công cụ sinh class

Công cụ tạo bytecode trả về dữ liệu rỗng hoặc sai header. `defineHiddenClass` báo `ClassFormatError`. Hãy xác minh bộ sinh đã tạo đúng cấu trúc `ClassFile` và có hoàn tất luồng ghi. **Không** thử tăng/giảm version để chữa magic sai.

### Tình huống B: runtime cũ hơn công cụ biên dịch

Build tạo class file Java 21 (major 65), nhưng server chạy Java 17 (tối đa 61). JVM báo `UnsupportedClassVersionError`. Hướng sửa: nâng runtime lên bản phù hợp hoặc build lại với `--release 17` **nếu source và API thực sự tương thích**. Không tự sửa hai byte major của class file.

### Tình huống C: bytecode bị instrumentation sai

Một agent hoặc library biến đổi instruction khiến operand stack và return type không thống nhất. Tệp có magic đúng và version hỗ trợ nhưng JVM báo `VerifyError`. Hướng sửa: kiểm tra stack map frame, thứ tự instruction, kiểu return, nhánh control-flow; cập nhật thư viện sinh/biến đổi class file tương thích JDK.

### Tình huống D: code đổi package trong bytecode

Một class file hợp lệ mô tả package khác package của `Lookup`. `defineHiddenClass` có thể báo `IllegalArgumentException`. Không coi đó là `ClassFormatError` vì lỗi nằm ở **điều kiện API**, không nhất thiết ở cấu trúc file hay bytecode verifier.

## 12. Các nhầm lẫn quan trọng cần tránh

1. **“Cả ba đều là `ClassFormatError`.”** Sai: `UnsupportedClassVersionError extends ClassFormatError`, nhưng `VerifyError` là nhánh khác trực tiếp dưới `LinkageError`.
2. **“Có `VerifyError` thì file .class chắc chắn sai magic.”** Sai: verifier phát hiện sai quy tắc trong bytecode dù cấu trúc file có thể hợp lệ.
3. **“UnsupportedClassVersionError luôn có nghĩa file class bị hỏng.”** Sai: file có thể hoàn toàn hợp lệ nhưng dành cho một JVM mới hơn.
4. **“`initialize=false` bỏ qua verification.”** Sai: cờ này chỉ liên quan khởi tạo class, không làm bytecode không hợp lệ trở thành hợp lệ.
5. **“Chỉ cần đổi major bytes là bytecode mới chạy trên JDK cũ.”** Sai: instruction, constant pool, dependency và API nền tảng có thể không tương thích.
6. **“`Class.forName` không tìm hidden class tức là class có lỗi định dạng.”** Sai: đó là đặc điểm không thể tìm theo tên của hidden class.
7. **“`catch (ClassFormatError)` rồi `catch (UnsupportedClassVersionError)` là đúng.”** Sai: `catch` cụ thể phải đứng trước; thứ tự ngược lại gây lỗi unreachable catch khi compile.
8. **“Tắt bytecode verifier là cách sửa VerifyError.”** Sai và không phải thực hành nên dùng: cần sửa bộ sinh/sửa bytecode để đáp ứng quy tắc JVM.

## 13. Checklist và tổng kết

Khi `Lookup.defineHiddenClass` báo lỗi, hãy tự hỏi:

- `byte[]` có thật là một file `.class` đầy đủ, bắt đầu bằng `CA FE BA BE`?
- `major_version.minor_version` có được JVM hiện tại hỗ trợ không; có yếu tố preview không?
- Nếu đúng định dạng và đúng version, lệnh JVM, return type, stack, `StackMapTable` có nhất quán không?
- `Lookup` có đúng quyền và cùng runtime package với class file không?
- Nếu đã qua định nghĩa nhưng lỗi khi khởi tạo, vấn đề có nằm ở static initializer không?
- Các phép bắt lỗi đã phân biệt rõ `UnsupportedClassVersionError`, `ClassFormatError`, `VerifyError` và các linkage errors khác chưa?

**Ghi nhớ:** `ClassFormatError` = định dạng `.class` sai; `VerifyError` = bytecode sai quy tắc kiểm chứng; `UnsupportedClassVersionError` = major/minor không được JVM hỗ trợ. Cả ba đều có thể xuất hiện khi JVM đọc và định nghĩa hidden class; cách sửa nằm ở **nguồn bytecode, tính đúng đắn của bytecode hoặc sự tương thích runtime**, không phải ở việc ẩn tên lớp.

## Tài liệu chính thức còn hiệu lực

- [Oracle JDK 26 — MethodHandles.Lookup.defineHiddenClass](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)): nêu `ClassFormatError`, `UnsupportedClassVersionError`, `VerifyError` và các điều kiện khác. API được giới thiệu trong Java 15.
- [Oracle JDK 26 — ClassFormatError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassFormatError.html): định dạng class file không hợp lệ.
- [Oracle JDK 26 — VerifyError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/VerifyError.html): verifier phát hiện bytecode không nhất quán.
- [Oracle JDK 26 — UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/UnsupportedClassVersionError.html): lỗi phiên bản major/minor; subclass của `ClassFormatError`.
- [Java Virtual Machine Specification, Java SE 27 — §1.2/§1.5](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-1.html): dải major version và class file dùng preview features.
- [Java Virtual Machine Specification, Java SE 27 — §4.1](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-4.html#jvms-4.1): cấu trúc `ClassFile` và định dạng major/minor.
- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): thiết kế chính thức của hidden class trong Java 15.

Bài học sử dụng API vẫn được hỗ trợ trong Java hiện đại; phần phiên bản Java dựa trên đặc tả Java SE 27 (9/2026). Ví dụ Java 17+ đã được biên dịch và chạy thử trên JDK 24.