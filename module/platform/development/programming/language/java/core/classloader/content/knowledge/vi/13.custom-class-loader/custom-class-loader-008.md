# Phân loại lỗi không tìm thấy và bytecode không hợp lệ trong custom ClassLoader

## 1. Vấn đề cốt lõi: “không tải được lớp” không phải chỉ có một nguyên nhân

Khi viết custom `ClassLoader`, bạn có thể thấy nhiều lỗi với kết quả giống nhau ở tầng nghiệp vụ: ứng dụng không sử dụng được class được yêu cầu. Nhưng **bản chất và hướng xử lý khác nhau hoàn toàn**:

- **`ClassNotFoundException`**: loader **không tìm được lớp được yêu cầu** qua đường tìm kiếm đang dùng. Đây là **checked exception** thường được khai báo ở `loadClass` và `findClass`.
- **`ClassFormatError`**: JVM đã nhận dữ liệu để định nghĩa class nhưng class file **sai định dạng hoặc không thể diễn giải như class file hợp lệ**.
- **`UnsupportedClassVersionError`**: class file có **major/minor version JVM hiện tại không hỗ trợ**. Nó là **subclass của `ClassFormatError`**.
- **`VerifyError`**: class file đủ cấu trúc để JVM đi vào verification, nhưng bytecode **vi phạm các ràng buộc verifier**, ví dụ tính đúng đắn của stack/kiểu ở các đường điều khiển.
- **`NoClassDefFoundError`**: trong khi JVM cần định nghĩa, liên kết hoặc khởi tạo class, một định nghĩa cần thiết **không khả dụng** hoặc một class trước đó **đã khởi tạo thất bại**; riêng `defineClass` còn có thể ném lỗi này khi tên yêu cầu **khác binary name chứa trong bytes**.
- **Các `LinkageError` khác** như `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` hoặc `IncompatibleClassChangeError`: JVM tìm thấy bytecode nhưng việc liên kết các ký hiệu/API runtime không phù hợp.

**Nguyên tắc:** Đừng biến tất cả thành `ClassNotFoundException`. Nếu bytecode tồn tại nhưng **không hợp lệ**, thông tin chẩn đoán quan trọng thường nằm ở một **Error** thuộc nhánh `LinkageError`, không phải ở tình trạng “không tìm thấy file”.

## 2. Đặt lỗi vào đúng giai đoạn của vòng đời class

```text
loader.loadClass("demo.Plugin")
          │
          ▼
1. findLoadedClass(name)
          │
          ▼
2. parent.loadClass(name)
          │ cha không tìm thấy?
          ▼
3. findClass(name) [custom loader]
          │
          ├── Không có bytecode
          │     └── ClassNotFoundException
          │
          ├── Đọc được bytecode
          │     └── defineClass(name, bytes, ...)
          │            ├── File sai định dạng → ClassFormatError
          │            ├── Version không hỗ trợ
          │            │      → UnsupportedClassVersionError
          │            ├── Tên không khớp
          │            │      → NoClassDefFoundError
          │            └── Class<?> đã định nghĩa
          │
          ▼
4. Verification / preparation / resolution
          │
          ├── Vi phạm quy tắc verifier → VerifyError
          ├── Thiếu dependency → có thể NoClassDefFoundError
          └── Sai liên kết binary API → các LinkageError khác
          │
          ▼
5. Initialization khi có active use
          │
          ├── Static initializer thành công
          └── Static initializer lỗi
                 ├── lần đầu: ExceptionInInitializerError
                 └── lần sau: thường NoClassDefFoundError
```

**Đây là mô hình để chẩn đoán, không phải lịch trình cứng cho mọi JVM.** Việc verification, resolution và sử dụng tham chiếu ký hiệu có thể được JVM thực hiện vào thời điểm khác nhau trong những giới hạn đặc tả. Vì vậy `loadClass(name)` thành công **chưa chứng minh** mọi dependency, mọi method reference và static initializer của lớp sẽ hoạt động.

### Hai ranh giới phải nhớ

1. **File có tồn tại không?** Đây mới là một bước trong `findClass`. File tồn tại không đồng nghĩa đó là class hợp lệ.
2. **Class đã được định nghĩa chưa?** Tìm được bytes hoặc nhận `Class<?>` không đồng nghĩa class đã khởi tạo hay các tham chiếu đều resolution thành công.

Nếu custom loader tự dùng `Files.readAllBytes(path)`, bước đọc là **I/O do ứng dụng viết**. Các lỗi sau khi gọi `defineClass` hoặc khi JVM liên kết là **lỗi hợp đồng JVM**. Cần giữ ranh giới này rõ trong code và logs.

## 3. Sơ đồ phân loại exception/error

| Dạng lỗi | Hệ phân cấp | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|---|
| `ClassNotFoundException` | `Exception`, checked | Loader không tìm được class qua nguồn đã cấu hình | Kiểm tra binary name, URL/classpath, JAR entry, delegation |
| `ClassFormatError` | `LinkageError` | Bytes không có cấu trúc class file hợp lệ | Kiểm tra magic, constant pool, transformer, file hỏng |
| `UnsupportedClassVersionError` | `ClassFormatError` | Major/minor không được runtime hỗ trợ | So JDK chạy và target `--release` |
| `VerifyError` | `LinkageError` | Bytecode vi phạm ràng buộc verifier | Kiểm tra bytecode generator/transformer, stack map, control flow |
| `NoClassDefFoundError` | `LinkageError` | JVM cần class/definition nhưng không có; hoặc init từng thất bại; hoặc wrong name | Đọc toàn bộ message và cause; xét thiếu dependency/init/wrong name |
| `NoSuchMethodError` | `IncompatibleClassChangeError` → `LinkageError` | Method từng được compile tham chiếu không tồn tại đúng signature lúc chạy | So JAR/API bản compile và runtime |
| `NoSuchFieldError` | `IncompatibleClassChangeError` → `LinkageError` | Field không còn đúng tên/descriptor | So versions của dependency |
| `IllegalAccessError` | `IncompatibleClassChangeError` → `LinkageError` | JVM tìm được thành viên nhưng runtime không có quyền truy cập | Kiểm tra access modifiers, runtime package, module, loader |
| `ExceptionInInitializerError` | `LinkageError` | Logic khởi tạo static thất bại | Đọc root cause trong `<clinit>` |
| `SecurityException` | `RuntimeException` | Vi phạm kiểm tra bảo vệ khi định nghĩa/truy cập class | Kiểm tra package như `java.*`, certificates, security context |

**Lưu ý kế thừa:** `UnsupportedClassVersionError extends ClassFormatError`. Khi viết các `catch` riêng, phải bắt lỗi version **trước** `ClassFormatError`; nếu không, nhánh version sẽ bị nhánh cha giữ lại. `VerifyError` là một nhánh khác dưới `LinkageError`, không phải subclass của `ClassFormatError`.

## 4. ClassNotFoundException: “không tìm được tên class”

API chuẩn:

```java
protected Class<?> findClass(String name)
        throws ClassNotFoundException
```

Trong loader tuân theo mô hình ủy quyền mặc định, `findClass` được gọi sau khi parent không tìm được lớp được yêu cầu. Triển khai mặc định của `ClassLoader.findClass(String)` ném `ClassNotFoundException`; subclass override để biết tìm bytecode từ đâu.

Với một custom loader tìm class trên ổ đĩa:

```java
// Trích đoạn bên trong override findClass:
Path classFile = root.resolve(
        name.replace('.', '/') + ".class"
);

byte[] bytes;
try {
    bytes = Files.readAllBytes(classFile);
} catch (IOException cause) {
    throw new ClassNotFoundException(name, cause);
}
return defineClass(name, bytes, 0, bytes.length);
```

Đây là **trích đoạn**, cần có `root`, imports và một subclass `ClassLoader`. Cách bọc `IOException` giữ lại nguyên nhân I/O; ví dụ `NoSuchFileException` cho thấy đường dẫn không tồn tại.

Trong loader production, nên phân biệt thêm:
- **Không có class trong nguồn này**: `ClassNotFoundException` là tín hiệu hợp lý để caller biết lớp không tìm được.
- **Nguồn tồn tại nhưng I/O hỏng**: hợp đồng `findClass` vẫn có thể trình bày dưới dạng `ClassNotFoundException` với **cause gốc**; không được mất thông tin đường dẫn, quyền đọc, timeout hay lỗi storage.
- **Bytes đã đọc nhưng hỏng**: **không** catch `ClassFormatError` rồi thay thành `ClassNotFoundException`, vì như vậy sẽ che mất nguyên nhân “bytecode có nhưng không hợp lệ”.

### Sai lầm thường gặp

```java
// ANTI-PATTERN — không sử dụng nguyên văn:
try {
    byte[] bytes = loadBytes(name);
    return defineClass(name, bytes, 0, bytes.length);
} catch (Throwable anything) {
    throw new ClassNotFoundException(name, anything);
}
```

Đây là **mã minh họa anti-pattern**, các phương thức và biến chưa được định nghĩa. Bắt `Throwable` nuốt cả `LinkageError`, `OutOfMemoryError`, `ThreadDeath` và những lỗi nghiêm trọng khác. Caller tưởng class chỉ vắng mặt và có thể retry/fallback vô nghĩa. **Chỉ bắt đúng những lỗi thực sự có thể xử lý.**

## 5. ClassFormatError: “đã có bytes nhưng không phải class file hợp lệ”

Một class file Java có cấu trúc nhị phân quy định bởi JVMS:

```text
u4 magic          // 0xCAFEBABE
u2 minor_version
u2 major_version
u2 constant_pool_count
...
```

**Ví dụ nguyên nhân:**

- Dữ liệu đầu file không có magic `CAFEBABE`; đọc nhầm một tệp text/HTML/JAR/ảnh như `.class`.
- File bị cắt/truncated trong quá trình tải, giải nén hoặc deploy.
- Cấu trúc constant pool, indices, attributes hoặc phần khác không tuân theo class-file format.
- Một công cụ bytecode transformer sinh ra bytes sai cấu trúc.
- Loader đọc nhầm tệp do cách map binary name sang path bị lỗi.

`ClassFormatError` là **`Error`**, không phải checked `Exception`. `defineClass` có thể ném lỗi này khi nhận bytes không hợp lệ. Cần tìm **nguồn bytes** và **nguyên nhân làm hỏng dữ liệu**, không chỉ thử lại tên class.

### Phân biệt file tồn tại với dữ liệu hợp lệ

```java
// Trích đoạn:
byte[] bytes = Files.readAllBytes(classFile);
System.out.println("bytes length=" + bytes.length);
return defineClass(name, bytes, 0, bytes.length);
```

Nếu `bytes.length > 0`, ta chỉ biết đã đọc được dữ liệu; chưa biết đó là Java class file. Ngay cả việc bốn byte đầu là `CAFEBABE` cũng **chưa chứng minh** constant pool, nội dung hoặc bytecode hợp lệ.

## 6. UnsupportedClassVersionError: “bytecode mới hơn/không được JVM hỗ trợ”

Đây là **subclass của `ClassFormatError`**, dành cho trường hợp `major_version`/`minor_version` trong class file không được JVM nhận diện theo quy tắc phiên bản.

Một số mốc:

| Java release | Class file major thường dùng |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |
| Java 26 | 70 |

Ví dụ ứng dụng chạy **Java 17** nhưng custom loader đọc class đã biên dịch cho **Java 21** (major 65) thì JVM Java 17 không thể nạp bytecode đó. Dù class file tồn tại và magic hợp lệ, vẫn phát sinh `UnsupportedClassVersionError`.

**Không giải quyết bằng cách đổi phần mở rộng, đổi thư mục hoặc đổi vài byte major trong class file**: opcode, constant pool, language feature và API có thể cần runtime mới thật sự.

Giải pháp đúng:

1. Kiểm tra **JVM runtime đang chạy** bằng `java -version`, không chỉ `javac -version`.
2. Kiểm tra **major/minor của file .class thực tế** bằng `javap -verbose` (hoặc công cụ đọc header đáng tin).
3. Biên dịch lại với `javac --release <supported-version>` nếu mã và các API nó dùng cho phép.
4. Nếu tính năng không thể hạ target, **nâng Java runtime** cho phù hợp.
5. Nếu dùng multi-release JAR, kiểm tra đúng entry versioned mà runtime/loader thật sự chọn.

Một ngoại lệ tinh tế là **preview-feature class files** có `minor=65535` từ các release hỗ trợ quy tắc preview. Chúng thường chỉ dùng được trên runtime **cùng release** với tùy chọn bật preview tương ứng; không suy ra major thấp hơn có nghĩa mọi JDK mới đều nhận bytecode preview.

## 7. VerifyError: bytecode qua bước định dạng nhưng không qua verifier

`VerifyError` biểu thị JVM phát hiện class file **không vượt qua các điều kiện verification**, ví dụ:

- Instruction đòi operand stack có kiểu/độ sâu không tương thích.
- Branch nhảy đến vị trí hoặc trạng thái stack không phù hợp.
- Return type/stack-map information không phù hợp với đường điều khiển.
- Các phép thao tác local variables/receiver vi phạm quy tắc an toàn kiểu.

Đây là nhóm vấn đề thường xuất hiện khi:

- Tự sinh bytecode bằng ASM/Byte Buddy hoặc viết class-file generator.
- Instrumentation/rewrite bytecode nhưng không cập nhật stack map frames hay max stack/local variables đúng cách.
- Một công cụ obfuscator/shader/agent tạo bytecode không phù hợp runtime target.

**Phân biệt với `ClassFormatError`:** Một class file có thể có header/constant pool hợp lệ nhưng chứa code vi phạm verifier. JVM có thể chỉ phát hiện `VerifyError` khi verification thực sự xảy ra; đừng gán một lịch trình cố định cho mọi JVM.

`javac` bình thường sinh bytecode hợp lệ cho target được hỗ trợ; vì vậy không cần cố xây một ví dụ `VerifyError` bằng source Java hợp lệ đơn thuần. Để tạo lỗi xác định, phải cố tình sinh/mutate bytecode theo cách kiểm soát. Trong production, **không vô hiệu hóa verifier** làm cách “sửa” file bytecode hỏng.

## 8. Demo Java 17+: phân biệt bốn tình huống bằng một custom loader

Ví dụ sau chủ động tạo bốn đường:

1. `MISSING`: yêu cầu một binary name không có file → `ClassNotFoundException`.
2. `MALFORMED`: sửa magic đầu file của class hợp lệ → `ClassFormatError`.
3. `NEWER`: sửa major thành giá trị cao hơn khả năng của Java 17 → `UnsupportedClassVersionError`.
4. `WRONG_NAME`: yêu cầu một binary name khác tên được khai trong bytes → `NoClassDefFoundError`.
5. `VALID`: sử dụng bytes hợp lệ → nạp được class, sau đó reflection gọi phương thức và khởi tạo lớp.

Các tình huống dùng **loader riêng cho mỗi lần thử** để không bị `findLoadedClass` lấy lại class đã nạp từ lượt trước. Demo cố ý **không tạo `VerifyError`** vì cần một bytecode transformer phù hợp, và cũng không giả định mọi JVM chọn đúng cùng thời điểm verification.

### 8.1. File Sample.java

Tạo file `Sample.java`:

```java
package demo;

public final class Sample {
    static {
        System.out.println("Sample initialized");
    }

    public static String greet() {
        return "hello";
    }
}
```

### 8.2. File FailureKindsDemo.java

Tạo file `FailureKindsDemo.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class FailureKindsDemo {
    enum Mode {
        MISSING, MALFORMED, NEWER, WRONG_NAME, VALID
    }

    static final class TestLoader extends ClassLoader {
        private final Path root;
        private final Mode mode;

        TestLoader(Path root, ClassLoader parent, Mode mode) {
            super(parent);
            this.root = root;
            this.mode = mode;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            String relativePath = mode == Mode.WRONG_NAME
                    ? "demo/Sample.class"
                    : name.replace('.', '/') + ".class";

            byte[] bytes;
            try {
                bytes = Files.readAllBytes(root.resolve(relativePath));
            } catch (IOException cause) {
                throw new ClassNotFoundException(name, cause);
            }

            if (mode == Mode.MALFORMED) {
                bytes[0] = 0; // Phá magic CAFEBABE.
            } else if (mode == Mode.NEWER) {
                bytes[6] = (byte) 0x7F; // Major rất cao.
                bytes[7] = (byte) 0x7F;
            }

            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Path.of("plugin-classes");
        ClassLoader parent = FailureKindsDemo.class.getClassLoader();

        for (Mode mode : Mode.values()) {
            TestLoader loader = new TestLoader(root, parent, mode);

            String name = switch (mode) {
                case MISSING -> "demo.Absent";
                case WRONG_NAME -> "demo.WrongName";
                default -> "demo.Sample";
            };

            try {
                Class<?> type = loader.loadClass(name);
                System.out.println(mode + " -> loaded: " + type.getName());

                if (mode == Mode.VALID) {
                    Object greeting =
                            type.getMethod("greet").invoke(null);
                    System.out.println("invoke: " + greeting);
                }
            } catch (ClassNotFoundException | LinkageError error) {
                System.out.println(
                        mode + " -> " + error.getClass().getSimpleName()
                );
            }
        }
    }
}
```

**Mục đích từng bước:**

- `TestLoader.findClass` tìm file khi parent không có class. Nếu `Files.readAllBytes` ném `IOException`, nó chuyển thành `ClassNotFoundException(name, cause)`, giữ lại nguyên nhân gốc.
- `MALFORMED` phá magic của bytes: dữ liệu không còn là class file hợp lệ.
- `NEWER` thay **major** ở offset 6–7 của header class file bằng `0x7F7F` (32767): Java 17 không hỗ trợ version đó, nhưng các bytes khác vẫn xuất phát từ một class file hợp lệ.
- `WRONG_NAME` yêu cầu `demo.WrongName` nhưng tải bytes tự khai tên `demo.Sample`. `defineClass(name,...)` phát hiện tên binary không khớp.
- `VALID` định nghĩa và trả về `demo.Sample` đúng tên; static initializer chỉ chạy khi reflection thực sự gọi `greet()`.

### 8.3. Biên dịch và chạy

Tạo thư mục plugin riêng. Trên Bash:

```bash
mkdir -p plugin-classes
```

Trên PowerShell:

```powershell
New-Item -ItemType Directory -Force plugin-classes | Out-Null
```

Biên dịch **bằng JDK 17**:

```bash
javac --release 17 -d plugin-classes Sample.java
javac --release 17 FailureKindsDemo.java
java -cp . FailureKindsDemo
```

Kết quả file:

```text
working-directory/
├── Sample.java
├── FailureKindsDemo.java
├── FailureKindsDemo.class
├── FailureKindsDemo$Mode.class
├── FailureKindsDemo$TestLoader.class
└── plugin-classes/
    └── demo/
        └── Sample.class
```

**Điều kiện thử nghiệm:** `plugin-classes` **không nằm trên `-cp` của host**. Nếu thêm `plugin-classes` vào application classpath, parent loader có thể tìm `demo.Sample` trước và nhánh `findClass` tùy chỉnh không được gọi cho tên đó.

### 8.4. Stdout trên JDK 17

```text
MISSING -> ClassNotFoundException
MALFORMED -> ClassFormatError
NEWER -> UnsupportedClassVersionError
WRONG_NAME -> NoClassDefFoundError
VALID -> loaded: demo.Sample
Sample initialized
invoke: hello
```

**Phân tích thứ tự:**

1. `MISSING`: parent không có `demo.Absent`; child tìm `plugin-classes/demo/Absent.class` nhưng không có, nên ném `ClassNotFoundException`.
2. `MALFORMED`: parent không có `demo.Sample`; child đọc file có thật nhưng sửa magic. JVM nhận bytes không hợp lệ và ném `ClassFormatError`.
3. `NEWER`: đọc file có thật và tạo major không hỗ trợ. JVM phân loại là `UnsupportedClassVersionError`, **một loại `ClassFormatError` cụ thể**.
4. `WRONG_NAME`: content class file thực sự là `demo.Sample` nhưng `defineClass` được yêu cầu tên `demo.WrongName`; lỗi là `NoClassDefFoundError`, thường chứa thông tin “wrong name” trong message thực.
5. `VALID`: class được định nghĩa thành công và in `loaded: demo.Sample`. `loadClass` chưa yêu cầu chạy static initializer; khi gọi `greet` bằng reflection, in `Sample initialized` rồi `invoke: hello`.

Ví dụ in **chỉ tên lớp lỗi** qua `getClass().getSimpleName()` để có stdout ổn định. Message chi tiết của JVM có thể khác theo bản JDK và không nên dùng làm chuỗi kiểm thử cứng. Trong hệ thống thật, cần giữ **message + cause + stack trace** để biết nguồn lỗi và đường nạp.

### 8.5. Nếu chạy bằng Java mới hơn thì sao?

Nhánh `NEWER` dùng major `32767`, cao vượt xa class-file major của các Java release hiện có. Nó được chọn nhằm mô phỏng một version không được JVM hỗ trợ trong demo, **không phải** khuyến nghị sửa bytes để “nâng phiên bản class”.

Đối với dữ liệu sản xuất, đừng sửa thủ công header; hãy dùng compiler với target phù hợp hoặc kiểm tra bằng `javap -verbose`. Thử nghiệm này chỉ giúp quan sát **phân loại lỗi**.

## 9. Vì sao NoClassDefFoundError khác ClassNotFoundException?

Tên hai lỗi tương tự nhưng quan hệ không giống nhau:

- `ClassNotFoundException` là **checked Exception**, thường xuất hiện khi **code chủ động yêu cầu loader tìm một binary name mà loader không tìm thấy**.
- `NoClassDefFoundError` là **LinkageError**, thường xuất hiện khi JVM cần một định nghĩa để **liên kết hoặc thực thi class đã tham chiếu** nhưng không thể đáp ứng; ngoài ra có đường riêng khi binary name trong bytes không khớp `defineClass`, hoặc khi class đã initialization thất bại.

Ví dụ ứng dụng được compile cùng thư viện `lib.Helper`, nhưng runtime chỉ còn `App.class` mà không có `lib.Helper.class`. Lời gọi đến `Helper` trong code App có thể gây `NoClassDefFoundError` khi JVM cần tải lớp phụ thuộc đó. Đừng diễn giải là caller của `App` đã trực tiếp gọi `ClassLoader.loadClass("lib.Helper")` và bắt `ClassNotFoundException`.

Trong JDK, một `ClassNotFoundException` cũng có thể nằm sâu bên trong **cause** của `NoClassDefFoundError`, tùy đường nạp. Nếu gặp `NoClassDefFoundError`, phải xem message và cause, không chỉ tên exception.

### Trường hợp class đã lỗi initialization

Lần đầu code chạm vào một class có static initializer ném một exception không thuộc `Error`, JVM thường bọc thành `ExceptionInInitializerError`. Class chuyển sang trạng thái erroneous; lần yêu cầu init tiếp theo của cùng runtime class thường ném `NoClassDefFoundError` với thông báo “Could not initialize class ...”.

Đây **không phải** bằng chứng thiếu file class. Thay classpath mà không kiểm tra static initializer có thể sửa sai vấn đề.

## 10. Ví dụ riêng: nạp được class nhưng initializer thất bại

Tạo `InitFailureDemo.java`:

```java
public final class InitFailureDemo {
    static final class Broken {
        static int value = initialize();

        static int initialize() {
            throw new IllegalStateException("invalid configuration");
        }
    }

    public static void main(String[] args) throws Exception {
        String name = "InitFailureDemo$Broken";
        ClassLoader loader = InitFailureDemo.class.getClassLoader();

        System.out.println("loaded: "
                + (Class.forName(name, false, loader) != null));

        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                Class.forName(name, true, loader);
            } catch (LinkageError error) {
                System.out.println(
                        attempt + ": " + error.getClass().getSimpleName()
                );
            }
        }
    }
}
```

Chạy:

```bash
javac --release 17 InitFailureDemo.java
java InitFailureDemo
```

Stdout:

```text
loaded: true
1: ExceptionInInitializerError
2: NoClassDefFoundError
```

Lời gọi `forName(..., false, ...)` thành công cho thấy JVM **tìm được class** và không yêu cầu chạy initializer. Lần `initialize=true` đầu thất bại vì code trong `Broken`, không phải vì thiếu class file. Lần tiếp theo class vẫn erroneous và không chạy initializer lại.

**Quy tắc debug:** tìm **lỗi xuất hiện đầu tiên**, vì sau đó một chuỗi lỗi “Could not initialize class” có thể chỉ là hậu quả thứ cấp.

## 11. Không che LinkageError bằng fallback sang loader khác

Một custom ClassLoader tuân parent-first thường làm:

```text
findLoadedClass(name)
       ↓ chưa có
parent.loadClass(name)
       ↓ parent báo ClassNotFoundException
findClass(name)
```

Điều kiện fallback thông thường là parent **không tìm thấy class**, chứ không phải parent báo bất kỳ lỗi nào. Nếu parent tìm thấy bytes nhưng ném `ClassFormatError` hoặc `VerifyError`, thuật toán mặc định **không âm thầm đổi sang một bản class khác** ở child.

Đây là nguyên tắc quan trọng cho plugin loader:

- **Không tìm thấy**: có thể thử nguồn class tiếp theo theo chính sách lookup được thiết kế.
- **Tìm thấy nhưng bị hỏng**: cần báo lỗi; không giả vờ rằng lớp không tồn tại.
- **Class có version mới hơn runtime**: đổi sang bytes cũ hơn một cách tùy tiện có thể che lỗi build/deploy. Nếu muốn fallback có kiểm soát, hãy thiết kế rõ các artifacts/versions hoặc **multi-release JAR** theo spec, không catch `UnsupportedClassVersionError` rồi âm thầm nạp class khác không kiểm chứng.
- **Lỗi security hoặc package definition**: không nuốt lỗi để vượt chính sách truy cập.

Đặc biệt, trong code override `loadClass`, đừng dùng:

```java
// ANTI-PATTERN — không chạy trực tiếp:
try {
    return parent.loadClass(name);
} catch (Throwable ignored) {
    return findClass(name);
}
```

Vì như vậy lỗi bytecode hỏng của parent có thể bị biến thành việc nạp một bản class khác. Điều này tạo kết quả khó tái hiện và nguy cơ xung đột danh tính class/runtime package.

## 12. Những lỗi link khác không thuộc “không tìm thấy class file”

### 12.1. NoSuchMethodError / NoSuchFieldError

Chúng thường liên quan **binary incompatibility**: class caller được compile với API version A, còn runtime nạp dependency version B thiếu method/field tương ứng.

Ví dụ về source API:

```java
// Library v1:
public class Api {
    public static String version() {
        return "v1";
    }
}
```

Caller compile với v1 và gọi `Api.version()`. Nếu runtime thay bằng library v2 đã xóa method đó, JVM có thể ném `NoSuchMethodError` khi resolve lời gọi.

Đoạn trên chỉ là **minh họa hai bản thư viện**, không phải một file runnable chứng minh lỗi tự thân. Cách sửa là làm rõ dependency runtime và giữ binary compatibility, không bắt `ClassNotFoundException`.

### 12.2. IllegalAccessError

`IllegalAccessError` xảy ra khi JVM tìm được một field/method/class nhưng điều kiện truy cập runtime không thỏa. Với custom loaders, hai class có cùng tên package về mặt chữ nhưng do **different defining loaders** định nghĩa **không tự thuộc cùng runtime package**. Vì vậy code từng truy cập package-private thành công khi compile hoặc chạy cùng loader có thể thất bại trong một bố cục loader khác.

Không giải quyết lỗi access bằng cách thay `ClassNotFoundException`, vì class **đã được tìm thấy**.

### 12.3. IncompatibleClassChangeError và duplicate definition

`IncompatibleClassChangeError` bao gồm nhiều thay đổi binary contract, ví dụ static/instance mismatch. Tự gọi `defineClass` nhiều lần cho cùng binary name trong cùng defining loader có thể gây `LinkageError` do duplicate class definition. Triển khai `ClassLoader.loadClass` mặc định kiểm tra `findLoadedClass` và dùng locking thích hợp nhằm tránh một phần các vấn đề này.

Đừng gọi trực tiếp `findClass(name)` từ client nếu định làm hoạt động lookup bình thường: bạn có thể bỏ qua caching/delegation/synchronization của `loadClass` và tạo lỗi khó kiểm soát.

## 13. Cách bắt lỗi đúng tầng ứng dụng

Ở **ranh giới plugin/module loading**, có thể phân loại để ghi log và quyết định:

```java
// Trích đoạn trong method có biến:
// ClassLoader loader; String binaryName;

try {
    Class<?> type = loader.loadClass(binaryName);
    useType(type);
} catch (ClassNotFoundException ex) {
    report("Class not found in configured sources", ex);
} catch (UnsupportedClassVersionError ex) {
    report("Class version not supported by this JVM", ex);
} catch (ClassFormatError ex) {
    report("Malformed or incompatible class-file format", ex);
} catch (VerifyError ex) {
    report("Bytecode verification failed", ex);
} catch (NoClassDefFoundError ex) {
    report("Required definition unavailable or class init failed", ex);
} catch (LinkageError ex) {
    report("Other JVM linkage failure", ex);
}
```

Đây là **trích đoạn**, `useType` và `report` là các phương thức do ứng dụng định nghĩa, không phải API Java chuẩn. Thứ tự `catch` quan trọng: `UnsupportedClassVersionError` đứng trước `ClassFormatError`; các trường hợp chuyên biệt đứng trước `LinkageError`.

**Cẩn thận:** nếu plugin API được dùng ở framework, không nhất thiết **mọi nơi** đều nên catch `LinkageError`. Thường chỉ tầng biên có chính sách quản lý plugin/fail-fast rõ ràng mới nên làm thế. Đừng bắt Error rồi “tiếp tục chạy như không có gì xảy ra”. Hệ thống có thể đã ở trạng thái không nhất quán.

### Giữ thông tin chẩn đoán

Một log tối thiểu nên gồm:

- **Binary name yêu cầu** (ví dụ `demo.Sample`).
- **ClassLoader và parent chain**; nếu có, defining loader của class thực sự được trả về.
- **Nguồn class file**: URL, JAR entry, path, version artifact, checksum nếu hữu ích.
- **JVM runtime** (feature version, vendor).
- **Loại lỗi, message, cause chain, suppressed exceptions**.
- **Thời điểm xảy ra**: find bytes, defineClass, resolve/verify, initialize hay lúc gọi method.
- **Thread thực thi và TCCL** nếu framework dùng service/provider discovery.

Không đưa dữ liệu nhạy cảm như credential, token trong URL nguồn vào logs sản xuất. Khi xem URL từ nguồn mạng, cần redact query string hay thông tin xác thực phù hợp.

## 14. Chẩn đoán bằng javap, file header và JVM log

### 14.1. Kiểm tra class file được deploy

```bash
javap -verbose -classpath plugin-classes demo.Sample
```

Tìm những thông tin có ích:

- `major version` và `minor version`.
- `this_class` tương ứng `demo/Sample`.
- Constant pool, method descriptors, bytecode và các attributes.

Với lệnh biên dịch `javac --release 17` trong ví dụ, `major version` của `demo.Sample` là **61** và minor thông thường là **0**.

Nếu `javap` không đọc được, hãy kiểm tra liệu tệp thực sự là `.class`, có bị cắt/hỏng hay không; điều này không có nghĩa JVM chắc chắn sẽ ném đúng cùng lỗi và message như `javap`.

### 14.2. Kiểm tra đúng JDK runtime

```bash
java -version
javac -version
```

`java` và `javac` có thể đến từ hai JDK installations khác nhau qua PATH, IDE, Maven/Gradle toolchain, container image hoặc CI. `javac` mới không làm JVM runtime cũ hiểu bytecode mới hơn.

### 14.3. Log class load

Với HotSpot hỗ trợ unified logging:

```bash
java -Xlog:class+load=info -cp . FailureKindsDemo
```

Log giúp quan sát class load và một phần nguồn class, nhưng không nên coi log class load là **log mọi bước của findClass, verification, resolution hoặc initialization**. Để biết chính xác mã trong custom loader làm gì, thêm log trước `Files.readAllBytes` và trước `defineClass`, tránh log những dữ liệu có thể nhạy cảm.

### 14.4. Bytecode transformer và agent

Nếu code chỉ lỗi khi chạy với Java agent, AOP/ORM proxy hoặc bytecode enhancer, so sánh:

1. Bytes class file **gốc** trước biến đổi.
2. Bytes **sau biến đổi** ngay trước `defineClass`.
3. JVM version và phiên bản thư viện transformer.
4. Các attributes như `StackMapTable` có được tạo/cập nhật đúng không.

Không kiểm tra duy nhất source code Java: source hợp lệ nhưng transformer vẫn có thể phá bytecode.

## 15. Cẩn trọng với lớp đã nạp và vấn đề tái hiện lỗi

Khi custom loader đã định nghĩa thành công `demo.Sample`:

```java
Class<?> first = loader.loadClass("demo.Sample");
Class<?> second = loader.loadClass("demo.Sample");
System.out.println(first == second); // true, với cùng loader mặc định
```

Đây là **trích đoạn**. Nếu bạn thay file `Sample.class` thành file hỏng **sau lần nạp thành công**, lần gọi tiếp theo theo `loadClass` mặc định thường dùng `findLoadedClass` và **không đọc lại file mới**. Điều đó có thể khiến một thí nghiệm “bytecode hỏng nhưng vẫn load được” nếu quên rằng class đã cached.

Muốn kiểm tra file mới:

- Chạy **JVM mới**, hoặc
- Tạo **defining ClassLoader mới** với bố cục parent phù hợp, bảo đảm nó không ủy quyền cho parent vốn đã có class cùng tên.

Tương tự, nếu một class initializer đã thất bại và class trở thành erroneous, JVM không tự thử lại initialization cho **cùng runtime class** mỗi lần gọi. Tạo file class khác trên ổ đĩa không xóa trạng thái erroneous của runtime class đó.

## 16. Quy trình quyết định khi một plugin load thất bại

```text
Không sử dụng được plugin class
          │
          ▼
Có ClassNotFoundException?
    ├─ Có → binary name / path / URL / JAR / parent / permissions
    └─ Không
          │
          ▼
Có UnsupportedClassVersionError?
    ├─ Có → so major/minor với Java runtime, --release
    └─ Không
          │
          ▼
Có ClassFormatError?
    ├─ Có → bytes bị hỏng / sai cấu trúc / đọc nhầm file
    └─ Không
          │
          ▼
Có VerifyError?
    ├─ Có → bytecode generator, StackMapTable, kiểu/stack
    └─ Không
          │
          ▼
Có NoClassDefFoundError?
    ├─ Có → dependency, wrong name, failed initialization
    └─ Không
          │
          ▼
Có lỗi LinkageError khác?
    ├─ Có → binary API, access, class identity
    └─ Không → xem các exception khác của ứng dụng/framework
```

**Đây là quy trình triage**, không phải danh sách exhaustive của mọi lỗi JVM. Một plugin có thể đồng thời tồn tại nhiều vấn đề; sửa lỗi đầu tiên rồi chạy lại trong **môi trường sạch** để xác định lỗi kế tiếp.

## 17. Lỗi phổ biến khi tự viết ClassLoader

| Anti-pattern | Vì sao sai? | Hướng sửa |
|---|---|---|
| Catch `Throwable` trong `findClass` rồi ném CNFE | Che lỗi bytecode, linkage, OOME và vấn đề bảo mật | Chỉ chuyển IOException phù hợp thành CNFE; để Error đi qua |
| Nếu file tồn tại thì kết luận class hợp lệ | Bytes có thể sai magic/constant pool/major/verification | Gọi `defineClass` để JVM xác minh, kiểm tra log |
| Dùng `UnsupportedClassVersionError` như lỗi “thiếu file” | JVM đã đọc được class nhưng không hỗ trợ version | Kiểm tra runtime, target, recompile |
| Bắt `ClassFormatError` trước `UnsupportedClassVersionError` | Branch version không bao giờ tới được | Bắt subclass trước |
| Chặn `LinkageError` và luôn fallback sang child | Có thể thay một bản class sai cách, phá identity | Fallback khi không tìm thấy theo chính sách đã định |
| Viết custom loader nhưng quên binary name | `defineClass` có thể ném `NoClassDefFoundError: wrong name` | Map name/path chính xác, không tự đổi package |
| Nạp từ JAR mới bằng loader cũ | `findLoadedClass` trả class cũ | Loader mới hoặc process mới |
| Dùng một JVM cho mọi biến thể thử nghiệm | Trạng thái đã load/init làm kết quả không độc lập | Loader riêng hoặc process riêng |
| Thấy `NoClassDefFoundError` rồi chỉ sửa classpath | Có thể do init thất bại hoặc wrong name | Đọc message/cause và lỗi đầu tiên |
| Bỏ qua `VerifyError` vì source compile được | Transformer có thể tạo bytecode sai | Kiểm tra bytes sau transform |
| Tắt verifier để “fix” lỗi | Che bytecode sai và phá bảo đảm an toàn JVM | Sửa generator/transformer |
| Không ghi loader identity khi debug | Hai class cùng name có thể khác runtime type | Log defining loader và path nguồn |

## 18. Bài tập tự kiểm tra

1. **Lớp không có trên classpath và `findClass` không tìm được file, lỗi nào phù hợp?** `ClassNotFoundException`.
2. **Một loader đọc được bốn byte ngẫu nhiên rồi gọi `defineClass`, có chắc là CNFE?** Không; nếu JVM thấy bytes không phải class file, đó là `ClassFormatError`.
3. **Java 17 tìm thấy bytecode Java 21 major 65 thì sao?** Có thể ném `UnsupportedClassVersionError`, không phải “không tìm thấy class”.
4. **`UnsupportedClassVersionError` có phải subclass của `ClassFormatError`?** Có.
5. **Class file có cấu trúc hợp lệ nhưng phép thao tác operand stack vi phạm type safety thì thường lỗi gì?** `VerifyError`.
6. **`defineClass("p.Other", bytesOfPActual, ...)` có thể ném gì?** `NoClassDefFoundError` do binary name không khớp.
7. **Class đã load được nhưng static initializer ném `IllegalStateException`, lần đầu và lần sau có thể thấy gì?** `ExceptionInInitializerError` rồi `NoClassDefFoundError`.
8. **Có nên catch mọi LinkageError và chuyển thành CNFE?** Không; làm mất nguyên nhân thực và cản trở triage.
9. **Nếu parent có class file sai cấu trúc, loader con có mặc nhiên thử bản cùng tên ở thư mục riêng không?** Không; parent-first mặc định chỉ fallback khi parent không tìm thấy theo hợp đồng, không nuốt các Error.
10. **Hai lỗi `ClassNotFoundException` và `NoClassDefFoundError` có cùng superclass trực tiếp không?** Không; một nhánh là checked Exception, nhánh kia là LinkageError.
11. **Tại sao trong demo dùng loader mới cho mỗi mode?** Để class đã định nghĩa ở mode khác không được reuse qua `findLoadedClass`.
12. **Một file class đúng header và đúng major có chắc thành công khi JVM sử dụng không?** Không; còn verification, binary dependencies, access và initialization.
13. **Muốn chắc runtime đang dùng bytecode nào thì làm gì?** Xác định JVM, loader, JAR entry/đường dẫn thực, kiểm tra bytes, `javap` và logs.
14. **Nếu class file version hỗ trợ nhưng method thiếu lúc runtime, lỗi nào có thể xảy ra?** `NoSuchMethodError` do binary incompatibility.

## Tài liệu chính thức

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `defineClass`, tên binary, xử lý CNFE và các lỗi khi định nghĩa class.
- [Java SE 21 — ClassFormatError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassFormatError.html): file class hỏng hoặc không diễn giải được.
- [Java SE 21 — UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/UnsupportedClassVersionError.html): lỗi major/minor version và quan hệ kế thừa với ClassFormatError.
- [Java SE 21 — VerifyError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/VerifyError.html): lỗi verification của JVM.
- [Java SE 21 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NoClassDefFoundError.html): lớp không còn định nghĩa khả dụng theo đường JVM yêu cầu.
- [JVM Specification — §4 The Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): định dạng class file, major/minor, constant pool, bytecode attributes.
- [JVM Specification — §5 Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html): loading, resolution, verification và class initialization.

**Kết luận:** Khi custom loader không sử dụng được một class, hãy phân biệt **“không tìm được bytes”** (`ClassNotFoundException`) với **“bytes có nhưng không phải class hợp lệ”** (`ClassFormatError`), **“class version không hỗ trợ”** (`UnsupportedClassVersionError`), **“bytecode không qua verifier”** (`VerifyError`) và **“liên kết/khởi tạo không thành công”** (các `LinkageError`). Giữ nguyên loại lỗi và nguyên nhân gốc là chìa khóa sửa đúng classpath, JDK target, bytecode generator hoặc cấu trúc dependency.
