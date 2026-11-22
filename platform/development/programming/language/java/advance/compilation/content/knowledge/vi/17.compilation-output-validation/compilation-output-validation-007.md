# Phân biệt lỗi biên dịch với lỗi liên kết do thư viện không tương thích

Một ứng dụng Java có thể **biên dịch thành công** hôm nay nhưng **không chạy được** ngày mai nếu thư viện đi kèm đã bị thay bằng một phiên bản không tương thích. Ngược lại, một source file có thể **không biên dịch được** với bản thư viện mới, trong khi class file cũ vẫn chạy được nếu thay đổi thư viện là **binary compatible**. Vì vậy, trong kiểm chứng đầu ra, việc nhìn thấy `BUILD SUCCESS` hoặc file `.class` chưa đủ để kết luận toàn bộ ứng dụng đã sẵn sàng chạy.

Bài học này phân biệt:

1. **Compile-time error**: `javac` không thể phân tích, kiểm tra kiểu, phân giải tham chiếu hoặc chấp nhận chương trình nguồn với classpath/module path hiện tại.
2. **Linkage error**: JVM nạp/xác minh/phân giải các class và **symbolic references** đã nằm trong class file, nhưng môi trường runtime không cung cấp một định nghĩa tương thích.
3. **Runtime exception và lỗi ứng dụng**: việc thực thi đã tới logic chương trình và gây lỗi như `NullPointerException` hoặc `IllegalArgumentException`; không được gộp mọi exception runtime thành linkage error.
4. **Binary compatibility**: mức độ một thay đổi thư viện vẫn cho phép những class files **đã biên dịch trước đó** tiếp tục liên kết đúng.

Ví dụ dùng Java 17+ và hai phiên bản của một thư viện có **cùng fully qualified class name**. Người học sẽ nhìn thấy cả lỗi `cannot find symbol` của compiler và `NoSuchMethodError` của JVM, biết cách sử dụng `javap` để đối chiếu chữ ký bytecode và xây một quy trình kiểm chứng release/library an toàn.

## 1. Hai thời điểm kiểm tra và hai góc nhìn

Giả sử `demo.Main` gọi `api.Greeter.message()`. Khi biên dịch, `javac` cần đọc định nghĩa thư viện trên **compile classpath** để kiểm tra type/method; nó sẽ ghi một tham chiếu ký hiệu tương ứng vào bytecode của `Main.class`.

Khi chạy, JVM sử dụng **runtime classpath/module path và class loaders** để tìm định nghĩa của `api.Greeter` và phân giải tham chiếu tới method được bytecode gọi. JVM không quay lại đọc `Main.java` để tự sửa tên hoặc chọn một phương thức tương tự ở library v2.

```text
SOURCE & COMPILE TIME                         RUNTIME
---------------------                         -------
src/demo/Main.java                           build/app/demo/Main.class
   |                                              |
   | javac -cp lib-v1                              | java -cp app:lib-v2
   v                                              v
lib-v1/api/Greeter.class (có message)      lib-v2/api/Greeter.class (không có message)
   |                                              |
   v                                              v
javac phân giải method thành công           JVM cố resolve symbolic reference
   |                                              |
   v                                              v
Main.class chứa lời gọi message()           NoSuchMethodError
```

Phân biệt:

| Hỏi gì? | `javac` khi biên dịch source | JVM khi chạy class file |
| --- | --- | --- |
| Đầu vào chính | `.java` + dependency classes/modules | `.class` + runtime dependencies |
| Nơi tra method/field/type | Compile classpath/module path, source path | Runtime classpath/module path, class loaders |
| Khi thiếu method | Diagnostic như `cannot find symbol` | `NoSuchMethodError` khi tham chiếu tương ứng được phân giải |
| Khi không đủ quyền truy cập | Compile-time access error | `IllegalAccessError` nếu binary cũ dùng một member nay không accessible |
| Khi class file quá mới | Compiler cũ có thể báo `bad class file / wrong version` | `UnsupportedClassVersionError` từ VM không hỗ trợ định dạng |
| Khi kiểm tra thành công | `javac` trả exit code 0; output có thể được tạo | Không bảo đảm mọi đường đi runtime đều chạy thành công |
| Khi lỗi xuất hiện | Trong quá trình parse/enter/analyze/compile | Có thể lúc load, verify, resolve hoặc chỉ khi nhánh code liên quan được thực thi |

**Lưu ý về thời điểm:** JVM specification cho phép **lazy hoặc eager resolution** trong các giới hạn xác định. Không nên khẳng định `NoSuchMethodError` *luôn* xuất hiện ngay ở startup hoặc *luôn* chính xác tại một lệnh `invokevirtual` cụ thể trong mọi JVM. Lỗi liên kết có thể chỉ bộc lộ khi chương trình lần đầu sử dụng một class hoặc member.

## 2. ABI và binary compatibility khác source compatibility ra sao?

**API** là giao diện mà người lập trình dùng ở cấp source; **ABI** (Application Binary Interface) mô tả những thứ mà **binary client** dựa vào sau khi biên dịch: class/interface identity, member name, access flags, JVM descriptors, static/instance distinction, inheritance và các metadata liên quan.

Với Java, class file có **constant pool** chứa symbolic references. Ví dụ source:

```java
String text = api.Greeter.message();
```

thường dẫn tới một tham chiếu bytecode kiểu:

```text
invokestatic api/Greeter.message:()Ljava/lang/String;
```

Đây là **dạng disassembly rút gọn minh họa**, không phải output đầy đủ của `javap`. Nó cho thấy JVM cần method có:

- Owner class: `api/Greeter`.
- Tên: `message`.
- Descriptor: `()Ljava/lang/String;`, tức **không có tham số, trả về `java.lang.String`**.
- Hình thức gọi: `invokestatic`, nghĩa là compiler đã tin đây là method **static**.

Nếu thư viện v2 chỉ còn `message(int)` hoặc `text()`, JVM không tự đổi symbolic reference trong `Main.class` sang tên/descriptor mới. Nếu client được **recompile** với API v2, `javac` sẽ kiểm tra lại và phát diagnostic ngay khi source không còn hợp lệ.

### Ba thuộc tính tương thích cần tách riêng

| Thuộc tính | Câu hỏi | Minh họa |
| --- | --- | --- |
| **Source compatibility** | Mã nguồn client cũ có còn biên dịch được với API mới không? | Đổi method name khiến source gọi tên cũ lỗi |
| **Binary compatibility** | Client class file **không recompile** có link được với library mới không? | Xóa method cũ dẫn tới `NoSuchMethodError` |
| **Behavioral compatibility** | Chương trình còn thực hiện đúng hành vi mong đợi không? | Method vẫn tồn tại nhưng đổi kết quả/trạng thái, không nhất thiết có linkage error |

**Binary compatibility không đồng nghĩa behavioral compatibility.** Một thư viện có thể giữ nguyên chữ ký method, để mọi class cũ tiếp tục link, nhưng thay đổi output, side effect, exception do method body ném hoặc chính sách thread safety. Kiểm chứng release cần cả ABI checks lẫn functional tests.

## 3. Ví dụ đầy đủ Java 17: thư viện v1, ứng dụng, thư viện v2

Để tái hiện chính xác sự khác biệt, chúng ta tạo **hai bản độc lập của cùng class `api.Greeter`** và **một client `demo.Main`**.

### 3.1. Cây source ban đầu

```text
project/
└── src/
    ├── v1/
    │   └── api/
    │       └── Greeter.java
    ├── v2/
    │   └── api/
    │       └── Greeter.java
    └── client/
        └── demo/
            └── Main.java
```

**`src/v1/api/Greeter.java`:**

```java
package api;

public final class Greeter {
    private Greeter() {
    }

    public static String message() {
        return "library-v1";
    }
}
```

**`src/v2/api/Greeter.java`:**

```java
package api;

public final class Greeter {
    private Greeter() {
    }

    // Method message() đã bị loại bỏ ở phiên bản này.
    public static String replacement() {
        return "library-v2";
    }
}
```

**`src/client/demo/Main.java`:**

```java
package demo;

import api.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Greeter.message());
    }
}
```

Đây là **ba file độc lập**, không copy cả ba class vào cùng một `.java`. Hai file `Greeter.java` cùng package/class name **không được compile chung vào một output directory**; ta chọn **một version tại một thời điểm**. Cấu hình đầu ra riêng giúp thí nghiệm không lẫn class files.

### 3.2. Compile library v1 và client bằng Java 17

Tại thư mục `project`:

```sh
javac --release 17 -encoding UTF-8 -d build/lib-v1 src/v1/api/Greeter.java
javac --release 17 -encoding UTF-8 -cp build/lib-v1 -d build/app src/client/demo/Main.java
```

Lệnh compile thành công thường không in stdout. Kết quả mong đợi:

```text
build/
├── lib-v1/
│   └── api/Greeter.class
└── app/
    └── demo/Main.class
```

**Chạy với library v1.**

Linux/macOS (dấu `:` phân cách classpath):

```sh
java -cp build/app:build/lib-v1 demo.Main
```

Windows PowerShell hoặc cmd (dấu `;` phân cách classpath):

```powershell
java -cp "build/app;build/lib-v1" demo.Main
```

**Stdout chính xác:**

```text
library-v1
```

Điều này chứng minh compiler đọc được API v1, client binary gọi được `message()` và runtime lúc đó chứa đúng bản library.

### 3.3. Compile library v2 riêng, nhưng không compile lại client

```sh
javac --release 17 -encoding UTF-8 -d build/lib-v2 src/v2/api/Greeter.java
```

Kiểm tra phương thức trong hai bản:

```sh
javap -classpath build/lib-v1 -p -s api.Greeter
javap -classpath build/lib-v2 -p -s api.Greeter
javap -classpath build/app -c demo.Main
```

Trong v1, phần quan trọng tương đương:

```text
public static java.lang.String message();
  descriptor: ()Ljava/lang/String;
```

Trong v2, phần quan trọng tương đương:

```text
public static java.lang.String replacement();
  descriptor: ()Ljava/lang/String;
```

Ở `Main.class`, bytecode có tham chiếu tới **`api.Greeter.message:()Ljava/lang/String;`**. Output `javap` thực tế còn có constant-pool indices, offsets và thông tin khác; các đoạn trên là **trích rút nội dung**, không cam kết format chính xác.

Bây giờ **chạy client cũ với library v2**:

Linux/macOS:

```sh
java -cp build/app:build/lib-v2 demo.Main
```

Windows:

```powershell
java -cp "build/app;build/lib-v2" demo.Main
```

**Kết quả:** JVM ném **`java.lang.NoSuchMethodError`** khi tham chiếu method cũ được phân giải. Thông điệp thường chỉ rõ chữ ký `api.Greeter.message()`:

```text
Exception in thread "main" java.lang.NoSuchMethodError: 'java.lang.String api.Greeter.message()'
```

Đây là **dòng đại diện thường gặp**, không phải toàn bộ stderr bắt buộc; stack trace, dấu nháy và văn bản có thể thay đổi theo JDK. Điều quan trọng là **exception type**, tên class/member và descriptor mà client yêu cầu.

Vì đây là **lỗi liên kết do ABI không tương thích**, `Main.java` chưa bị thay đổi, `Main.class` vẫn tồn tại và trước đó compile đã thành công. Việc thay thư viện ở runtime chính là nguyên nhân.

### 3.4. Recompile client cũ với library v2: giờ là lỗi compile

Giữ nguyên `src/client/demo/Main.java` nhưng compile lại với API v2:

```sh
javac --release 17 -encoding UTF-8 -cp build/lib-v2 -d build/app-v2 src/client/demo/Main.java
```

**Kết quả dự kiến:** `javac` thất bại, vì class `api.Greeter` hiện tại không có method `message()`. Một đoạn diagnostic thường có nghĩa:

```text
error: cannot find symbol
  symbol:   method message()
  location: class api.Greeter
```

Đây là **trích ý thông báo**, không khẳng định nguyên văn đầy đủ, số dòng hoặc số lỗi trên mọi compiler. Với command này, compiler đã **đọc được** `Greeter.class` v2 (cùng class-file major 61), nhưng source không còn phù hợp API.

**Kết luận của thí nghiệm:** *Cùng một thay đổi thư viện — bỏ method `message()` — dẫn đến lỗi ở hai giai đoạn khác nhau*:

| Trường hợp | Điều đang được kiểm tra | Lỗi |
| --- | --- | --- |
| `javac` compile `Main.java` với lib-v2 | **Source compatibility** | `cannot find symbol: method message()` |
| `java` chạy `Main.class` cũ với lib-v2 | **Binary compatibility** | `NoSuchMethodError` |
| `java` chạy `Main.class` cũ với lib-v1 | API/ABI còn đúng | In `library-v1` |
| Sửa `Main.java` gọi `replacement()` rồi compile với lib-v2 | Client và library cùng API mới | Compile được; phải test runtime riêng |

### 3.5. Cách sửa đúng

Một trong hai hướng bền vững:

**Giữ tương thích binary cho client cũ** bằng cách cung cấp lại method trong library v2:

```java
package api;

public final class Greeter {
    private Greeter() {
    }

    /** @deprecated Dùng replacement() trong mã mới. */
    @Deprecated
    public static String message() {
        return replacement();
    }

    public static String replacement() {
        return "library-v2";
    }
}
```

Đây là **phiên bản thay thế hoàn chỉnh** cho file `src/v2/api/Greeter.java`. Khi build lại library v2 có cả `message()`, client binary cũ có thể link với nó. Output sẽ thành `library-v2` do implementation mới, dù binary compatibility được giữ lại.

**Hoặc chủ động nâng client**: sửa `Main.java` dùng `Greeter.replacement()`, compile lại với library v2 và đảm bảo runtime đóng gói lib-v2. Việc cập nhật client là breaking-change migration; không thể chỉ đổi version number mà bỏ qua lệnh recompile và các binary clients khác.

## 4. Ví dụ thứ hai: đổi static thành instance method

Một thay đổi ABI phổ biến nhưng đôi khi khó nhận ra hơn xóa method là đổi **`static` sang instance**. Giả sử binary client đã compile với:

```java
public static String message()
```

Nếu library mới vẫn có method cùng tên và kiểu trả về nhưng bỏ `static`:

```java
package api;

public final class Greeter {
    public Greeter() {
    }

    public String message() {
        return "instance-v3";
    }
}
```

Đây là **nội dung hoàn chỉnh của một phiên bản `Greeter.java` khác**, nên biên dịch vào `build/lib-v3` riêng, không đưa vào cùng thư mục với v1/v2:

```sh
javac --release 17 -encoding UTF-8 -d build/lib-v3 src/v3/api/Greeter.java
```

Lệnh trên giả định bạn đã lưu source ở **`src/v3/api/Greeter.java`**. Nếu chạy `Main.class` đã compile với v1 nhưng runtime cung cấp v3, JVM gặp **`IncompatibleClassChangeError`** vì bytecode đang dùng `invokestatic` trong khi method runtime là instance. Không thể sửa bằng cách “tìm thấy một method cùng tên”: **hình thức static/instance nằm trong hợp đồng binary**.

Ngược lại, nếu **recompile `Main.java` nguồn cũ** với lib-v3, compiler không chấp nhận `Greeter.message()` được gọi tĩnh từ class name, và phát diagnostic tương tự “non-static method cannot be referenced from a static context”. Hai đường đi khác nhau nhưng cùng một thay đổi API/ABI.

**Lưu ý:** `IncompatibleClassChangeError` là lớp cha của một số loại linkage errors khác như `NoSuchMethodError` và `NoSuchFieldError`; khi lỗi cụ thể đã được JVM báo, hãy giữ **tên subclass thực tế**, không chỉ ghi chung “incompatible class”.

## 5. Những loại linkage errors quan trọng khi nâng/thay thư viện

| Lỗi JVM | Một nguyên nhân tương thích điển hình | Ví dụ thay đổi |
| --- | --- | --- |
| `NoSuchMethodError` | Binary gọi method/constructor có name + descriptor không còn được phân giải | Xóa method, đổi kiểu trả về hoặc parameter types |
| `NoSuchFieldError` | Field referenced by old binary không còn theo name + descriptor | Xóa/đổi type field, không còn field tương ứng |
| `IllegalAccessError` | Class/member trước đây accessible nay không còn quyền truy cập ở runtime | Giảm visibility; thay module `exports` |
| `IncompatibleClassChangeError` | Class/member đã đổi loại tương thích không thể đáp ứng instruction/linking | `static` ↔ instance; một số thay đổi class/interface/inheritance |
| `AbstractMethodError` | Binary cố gọi method mà runtime không có concrete implementation hợp lệ | Thay method concrete thành abstract hoặc incompatibility của implementation |
| `NoClassDefFoundError` | VM từng cần định nghĩa class nhưng không tìm/khởi tạo được trong bối cảnh nạp | Runtime thiếu dependency transitively hoặc class initialization thất bại |
| `UnsupportedClassVersionError` | VM không hỗ trợ class-file major/minor version | Lib build `--release 21` chạy bằng Java 17 |
| `VerifyError` | JVM verifier thấy class files không thỏa quy tắc kiểm chứng | Binaries/transformer/library thay đổi gây bytecode không hợp lệ |

**`LinkageError` là nhánh của `Error`, không phải `Exception` thông thường.** Dùng `catch (Exception e)` **không** bắt được `NoSuchMethodError`. Dù `catch (LinkageError e)` có thể dùng ở ranh giới chẩn đoán plugin, application thông thường **không nên coi linkage error là một lỗi nghiệp vụ có thể phục hồi đơn giản**. Nó thường cho thấy environment/deployment/classloader đang sai và cần khắc phục artifact versions.

### `ClassNotFoundException` không giống `NoClassDefFoundError`

`ClassNotFoundException` là **checked exception** thường gặp khi code yêu cầu tải class bằng tên, chẳng hạn:

```java
Class.forName("com.example.Missing")
```

Đây là **biểu thức minh họa**; muốn chạy độc lập cần class/method bao quanh và xử lý checked exception.

`NoClassDefFoundError` là một **`LinkageError`**, xuất hiện khi VM cần định nghĩa class mà binary đã tham chiếu nhưng không có định nghĩa phù hợp; nó cũng có thể xuất hiện sau khi khởi tạo class thất bại trước đó (thường kèm thông tin “Could not initialize class”). Không suy luận “tên class thiếu” là một triệu chứng duy nhất: kiểm tra nguyên nhân và nguyên nhân gốc trong log.

### `ExceptionInInitializerError` và `NoClassDefFoundError` kế tiếp

Nếu static initializer của một class ném runtime exception, JVM có thể báo `ExceptionInInitializerError` lần đầu. Khi chương trình thử dùng lại class sau khởi tạo thất bại, JVM có thể báo `NoClassDefFoundError` do class đã ở trạng thái khởi tạo lỗi. Đây không phải cùng kịch bản với đổi/xóa method trong JAR; cần nhìn **cause ban đầu**.

### Class-file version là một trục riêng với ABI

`UnsupportedClassVersionError` có thể xảy ra dù tên method hoàn toàn tương thích, nếu JVM **không đọc nổi định dạng `.class`**. Ví dụ Java 17 thường hỗ trợ major 61; class Java 21 có major 65. Đổi `--release 17` của **chính app** không tự thay class files major 65 ở thư viện.

Cần tách:

- **Định dạng class file hỗ trợ không?**
- **Class/library có được tìm và nạp không?**
- **Các symbolic references có resolve đúng không?**
- **Các quyền truy cập và classloader/module rules có đáp ứng không?**
- **Method body/runtime behavior có đúng không?**

Một ứng dụng có thể qua vài bước nhưng thất bại ở bước khác.

## 6. Quan sát bằng `javap`: tên method, descriptor và opcode

Với thí nghiệm v1/v2 ở mục 3:

```sh
javap -classpath build/lib-v1 -p -s api.Greeter
javap -classpath build/lib-v2 -p -s api.Greeter
javap -classpath build/app -c -p demo.Main
javap -classpath build/app -v demo.Main
```

Ý nghĩa:

| Lệnh | Dùng để xác minh |
| --- | --- |
| `javap -p` | Thành viên public/private còn hay đã biến mất |
| `javap -s` | JVM method/field descriptors, đặc biệt return type/parameter types |
| `javap -c` | Bytecode instruction `invokestatic`, `invokevirtual`, `getstatic`, v.v. |
| `javap -v` | Constant pool symbolic references và flags/attributes chi tiết |

Trong source Java, **method signature** thường nói tới tên + parameter types. Nhưng ở **JVM method descriptor**, **return type cũng được mã hóa**. Đổi return type, ngay cả khi source call không sử dụng giá trị trả về, có thể làm client binary cũ vẫn gọi descriptor đã mất và ném `NoSuchMethodError`.

Ví dụ:

```java
// v1
public static int count() { return 3; }

// v2
public static long count() { return 3L; }
```

Đây là **hai mảnh minh họa của hai library versions**, không phải source file độc lập có thể đặt cả hai vào một class. Descriptor v1 là `()I`, descriptor v2 là `()J`; old binary yêu cầu `()I` sẽ không tự được cập nhật.

### Chú ý fields có compile-time constants

Một trường hợp gây hiểu nhầm là:

```java
public static final int LIMIT = 10;
```

Nếu `LIMIT` là **constant variable** được Java compiler nội tuyến vào client binary, client có thể **không cần** `getstatic` để đọc nó; đổi `LIMIT` trong thư viện mới có thể khiến client cũ vẫn sử dụng **giá trị 10** thay vì báo `NoSuchFieldError`.

Muốn dùng một thí nghiệm dễ quan sát field linkage, chọn field **không phải compile-time constant**, chẳng hạn:

```java
public static int counter = 7;
```

Khi đó client bình thường dùng `getstatic` để truy cập. Nếu v2 xóa/đổi field và vẫn chạy client class cũ, `NoSuchFieldError` có thể xuất hiện. **Không** lấy kết luận về fields từ một ví dụ hằng primitive/String được inline tại compile time.

## 7. Phân biệt lỗi do compiler với lỗi do runtime trong pipeline thực tế

Một đường build thực tế thường có nhiều bước:

```text
Dependency resolution
       |
       v
Compile source -> annotation processing -> output classes
       |
       v
Package JAR/WAR/container
       |
       v
Deploy / JVM loading / linking
       |
       v
Runtime execution and tests
```

Ở mỗi bước có lỗi khác nhau:

| Pha | Ví dụ lỗi | Đầu mối |
| --- | --- | --- |
| Tải/resolve dependency | Artifact không tìm thấy, version conflict | Maven/Gradle repository và dependency graph |
| Compile source | `cannot find symbol`, incompatible types, module not readable | `javac` diagnostics, compile classpath |
| Compile đọc class file | `bad class file: wrong version` | JDK compiler và target/format của dependency |
| Package | Gói thiếu JAR, shade relocation sai, manifest/module path sai | Kiểm tra artifact đã đóng gói |
| JVM load/link | `NoSuchMethodError`, `NoClassDefFoundError`, `IllegalAccessError` | Runtime classpath/classloader và ABI |
| JVM execute | `NullPointerException`, sai kết quả, race condition | Runtime state và logic ứng dụng |

Không kết luận lỗi từ từ khóa “class” hoặc “method” trong message. **Thời điểm** và **loại lỗi đầy đủ** quan trọng hơn.

### Tại sao compile thành công nhưng CI vẫn thất bại?

Ví dụ project có:

- `compileClasspath` mang `library:1.0` với `message()`.
- `runtimeClasspath` mang `library:2.0` không có `message()` vì một dependency khác ép version.
- `Main.class` được compile bằng v1 nên compile-pass.
- Integration test hoặc server chạy với v2, gọi vào method cũ → `NoSuchMethodError`.

Nếu chỉ xem log của `compileJava`, ta không phát hiện được. Phải so sánh **effective compile classpath** và **effective runtime classpath** sau dependency mediation/overrides, không chỉ phiên bản khai báo ở một dòng build file.

### Runtime class loader có thể chọn lớp khác mong đợi

Các hệ thống application server, IDE, plugin, OSGi, servlet container hoặc shaded/fat JAR có thể có nhiều classloaders. Một class `api.Greeter` được load từ **JAR khác** so với file mà `javap` bạn vừa xem.

Nếu chạy Java 9+ thông thường, có thể dùng logging class loading để hỗ trợ điều tra:

```sh
java -Xlog:class+load=info -cp build/app:build/lib-v2 demo.Main
```

Output log của `-Xlog` **rất dài và phụ thuộc JVM/JDK**; xem dòng cho `api.Greeter` và nguồn code location. Đừng dán toàn bộ log vào một unit test và so sánh từng byte. Với app có Java agents hoặc custom class loaders, log có thể cần thêm cấu hình.

Ngoài ra, có thể xem nguồn class sau khi load:

```java
System.out.println(
    api.Greeter.class.getProtectionDomain()
        .getCodeSource().getLocation());
```

Đây là **snippet** trong ứng dụng đã load thành công class `api.Greeter`, không phải tệp độc lập. `getCodeSource()` có thể là `null` tùy classloader/security context; cần null checks trong code thật. Nếu class không thể nạp do `UnsupportedClassVersionError` thì ngay thao tác lấy class literal/reflect cũng không phải phương tiện debug đáng tin.

## 8. Các thay đổi thư viện thường ảnh hưởng tương thích thế nào?

| Thay đổi thư viện | Source client cũ (recompile) | Binary client cũ (không recompile) |
| --- | --- | --- |
| Xóa `public` method được gọi | Không compile | Có thể `NoSuchMethodError` |
| Đổi tên method | Không compile nếu còn dùng tên cũ | Có thể `NoSuchMethodError` |
| Đổi parameters/return type | Thường không compile nếu lời gọi không còn khớp | Có thể `NoSuchMethodError` vì descriptor đổi |
| Giảm visibility `public` thành package-private/private | Source ngoài package/module không compile | Có thể `IllegalAccessError` |
| Đổi method static ↔ instance | Source cũ có thể không compile | Có thể `IncompatibleClassChangeError` |
| Đổi concrete method thành abstract | Source có thể fail tùy class hierarchy | Có thể `AbstractMethodError` khi invocation cần implementation |
| Xóa non-constant public field | Source cũ không compile | Có thể `NoSuchFieldError` |
| Thêm overload mới | Có thể làm recompile ambiguous hoặc chọn overload khác | Binary cũ thường giữ reference đã chọn trước đó |
| Đổi `throws` clause | Source compatibility có thể thay đổi | **Không tự làm mất binary compatibility** vì checked exceptions được kiểm ở compile time |
| Đổi method body, giữ descriptor và access | Recompile thường được | Thường vẫn binary compatible, nhưng hành vi có thể đổi |
| Thêm method mới | Source client cũ thường vẫn compile | Thường binary compatible; có ngoại lệ/hệ quả trong hierarchy |
| Đổi export/open module | Source/client access có thể fail | Có thể gây access/linkage hoặc reflective-access lỗi tùy context |

Bảng chỉ là **định hướng**; JLS Chương 13 phân tích nhiều trường hợp với inheritance, interfaces, generic erasure, default methods, overloaded methods, sealed types, enums và constants. Đừng lấy một ví dụ nhỏ làm quy tắc tuyệt đối cho mọi class hierarchy.

### ABI của generics

Ở JVM, generic type parameters phần lớn bị **erasure**. Một thay đổi ở source generic signature có thể ảnh hưởng source compatibility trong khi descriptor sau erasure chưa đổi. Ngược lại, thay một bounded type khiến erasure đổi có thể tác động descriptor và ABI.

Method **bridge** có thể do compiler sinh để giữ overriding sau erasure hoặc covariant return. Khi kiểm tra `javap -v`, có thể gặp `ACC_BRIDGE` và `ACC_SYNTHETIC`. Đừng tự xóa bridge/helper trên công cụ bytecode vì “không có trong source”; binary clients có thể cần nó.

### Enum và constant inlining

Thêm enum constant thường được JLS coi là binary compatible, nhưng hành vi của `switch` exhaustive hoặc logic client có thể thay đổi. Đổi thứ tự constants cũng có thể làm dữ liệu dùng `ordinal()` bị lệch dù không có linkage error. Tương thích binary là một khía cạnh, **không phải kết quả kiểm chứng hành vi đầy đủ**.

## 9. Module path, classpath và compatibility của runtime dependencies

Trong Java 9+, môi trường có thể bao gồm:

- **Classpath:** unnamed module, tên lớp được phân giải theo class loader/classpath order.
- **Module path:** explicit named/automatic modules, có readability/exports/resolution checks.
- **Multiple class loaders/layers:** ví dụ plugin system hoặc application server.

Nếu `javac` không được module cho phép đọc package, có thể phát diagnostic như `package ... is not visible` hoặc `module ... does not read ...`. Nếu runtime module graph khác compile-time, code có thể gặp lỗi trong quá trình resolution/loading/access check. **Không mặc định mọi lỗi JPMS đều là `NoSuchMethodError`**.

**Qualified exports** và `opens` cần tách biệt: `exports` cho truy cập Java công khai của package theo điều kiện; `opens` cho deep reflection ở runtime. Một framework reflection bị `InaccessibleObjectException` không phải cùng vấn đề với binary client gọi một method đã bị xóa.

### Dependency trực tiếp và bắc cầu

Thư viện `A` phụ thuộc `B`; ứng dụng chỉ khai báo `A` nhưng runtime thiếu/khác version `B`. Khi compiler compile với đầy đủ `A+B` mà deploy bỏ `B`, lỗi có thể chỉ xuất hiện lúc code từ `A` gọi tới `B`.

Để điều tra, kiểm tra cả:

1. **Direct dependency:** phiên bản `A` mà client được compile cùng.
2. **Transitive dependencies:** phiên bản `B`, `C`... có mặt trong compile/runtime graph.
3. **Dependency mediation:** quy tắc chọn version cuối của Maven/Gradle, exclusions, constraints.
4. **Shading/relocation:** những classes được đóng gói với package mới/cũ, duplicate classes.
5. **Deployment class loader:** JAR từ application hoặc container/shared libs nào được chọn.

Đổi tên JAR hoặc sửa `CLASSPATH` ngẫu nhiên có thể che lỗi nhưng không giải quyết được vấn đề provenance/ABI.

## 10. Công cụ kiểm tra: từ lệnh nhỏ tới kiểm thử CI

### Kiểm tra JDK dùng để compile và chạy

```sh
javac -version
java -version
```

Hai phiên bản có thể khác nhau nếu build tool sử dụng Java toolchain riêng. Khi một class file được biên dịch bằng JDK mới hơn mức JVM hỗ trợ, lỗi `UnsupportedClassVersionError` liên quan **class-file version**, không trực tiếp do xóa method. Kiểm tra bằng:

```sh
javap -verbose -classpath build/lib-v2 api.Greeter
```

Java 17 class-file major version là **61**; Java 21 là **65**. Lệnh `--release 17` của ứng dụng không tự chuyển dependency đã build cho Java 21 thành class-file major 61.

### Kiểm tra đúng symbolic reference

```sh
javap -c -p -classpath build/app demo.Main
javap -p -s -classpath build/lib-v1 api.Greeter
javap -p -s -classpath build/lib-v2 api.Greeter
```

Tập trung vào:

- Method name và JVM descriptor.
- Opcode `invokestatic`/`invokevirtual`/`invokeinterface` của client.
- Method có thật trong library runtime không?
- Access flags public/private/protected/static có còn tương thích?
- Class owner và inheritance path có thay đổi không?

Đừng chỉ so sánh text `public String message()` nhìn bằng mắt ở source; class file descriptor và cách JVM resolve mới quyết định binary linkage.

### Xem dependency graph của build tool

Một số lệnh phổ biến (phải chạy trong dự án thực tế với tool đã cài):

```sh
mvn dependency:tree
```

Đối với Gradle:

```sh
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency example-lib --configuration runtimeClasspath
```

Đây là **mẫu lệnh**; `example-lib` phải thay bằng tên dependency thật, `runtimeClasspath` phụ thuộc plugin/project. Trên Windows có thể dùng `gradlew.bat`. Cần kiểm tra cả cấu hình compile lẫn runtime khi nghi version mismatch.

**Dependency tree cho biết resolution**, không luôn chứng minh JAR nào JVM thực sự load khi có container classpath, fat JAR, custom loader hoặc agents. Dùng class-loading logs để bổ sung khi cần.

### `jdeps` giúp gì?

`jdeps` phân tích dependencies tĩnh từ class/JAR files và có thể giúp phát hiện module/class dependencies:

```sh
jdeps --class-path libs/* build/app
```

Đây là **mẫu lệnh minh họa**: wildcard expansion/classpath syntax thay đổi theo shell, và công cụ phải nhận đúng files/JARs thực tế. `jdeps` không thay thế kiểm tra method/field ABI đầy đủ, nhất là reflection và classloaders tùy biến.

## 11. Xây một pipeline kiểm chứng đúng cả compile-time và runtime

Để phát hiện incompatibility sớm, không chỉ chạy `javac` trên source:

### Bước 1 — Chốt runtime mục tiêu

Ví dụ ứng dụng cam kết chạy Java 17. Lưu phiên bản JDK compiler, target `--release 17` và JVM tối thiểu ở build configuration. Một bản release chỉ chạy Java 21 cần được công bố là tăng minimum Java, thay vì giữ nhãn “Java 17 compatible”.

### Bước 2 — Xây dependency graph có thể tái lập

Dùng version pinning/constraints/lockfiles phù hợp build tool. Tránh giải pháp thay đổi thư viện một cách ngầm định giữa lần compile và lúc package/deploy. Xác minh các dependency bắc cầu.

### Bước 3 — Chạy compile tests với API dự kiến

Recompile ứng dụng với **bản dependency dự kiến đóng gói**. Bước này bắt các lỗi source: method/field đã xóa, access modifiers mới, generic API không còn khớp.

### Bước 4 — Chạy binary compatibility test

Nếu cần hỗ trợ clients đã phát hành, giữ **old client binaries** và chạy chúng với **new library**. Không recompile old client trong bài kiểm thử này, vì recompile làm thay đổi câu hỏi cần trả lời. Có thể dùng công cụ API/ABI diff phù hợp để đánh giá breaking changes, nhưng vẫn cần runtime tests.

### Bước 5 — Test artifact đóng gói cuối

Chạy integration/smoke tests bằng **JVM mục tiêu** cùng JAR/WAR/container mà production nhận được. Kiểm tra class-loading failures ở những đường đi code có sử dụng các APIs quan trọng; không chỉ gọi main rồi thoát.

### Bước 6 — Gắn nguyên nhân với bằng chứng

Nếu xảy ra `NoSuchMethodError`, log tối thiểu:

- Exception class và full member signature từ lỗi.
- Stack trace vị trí nơi reference được sử dụng.
- Runtime JDK version.
- Tên module/class loader và code source của class liên quan khi có thể.
- Artifacts versions/hashes/paths đã đóng gói; có class trùng tên không?
- `javap -s` output của **old client** và **actual runtime library**.

Từ đó mới quyết định restore binary API, recompile client, nâng/downgrade library hay sửa dependency resolution.

## 12. Chẩn đoán theo loại lỗi: chọn đúng bước tiếp theo

| Dấu hiệu trong log | Bước đầu nên làm |
| --- | --- |
| `error: cannot find symbol` | Xác minh source import/method/field, compile classpath và API hiện tại |
| `package ... is not visible` | Kiểm tra module readability/exports và quyền truy cập |
| `bad class file: wrong version` | So sánh `javac -version` với class-file major của dependency |
| `NoSuchMethodError` | `javap` method owner/name/descriptor của caller và runtime callee, đối chiếu JAR versions |
| `NoSuchFieldError` | Xem JVM field descriptor, constant inlining và runtime class owner |
| `IllegalAccessError` | Kiểm tra visibility, module exports, classloader identity và descriptor |
| `IncompatibleClassChangeError` | Kiểm tra static/instance distinction, class/interface kind và hierarchy |
| `AbstractMethodError` | Kiểm tra interface/class implementation thực và thư viện đã compile |
| `NoClassDefFoundError` | Kiểm tra missing transitive JAR, class name, initialization failure cause |
| `UnsupportedClassVersionError` | Xem classfile major/minor, JDK build/runtime và preview features |
| Runtime chạy nhưng output sai | Kiểm thử behavioral/API contract, dữ liệu, dependency semantics; không đổ lỗi cho linker khi không có bằng chứng |

### Một quy trình debug 8 câu hỏi

1. **Lỗi ở `javac` hay `java`?** Log command nào thất bại?
2. **Lỗi cụ thể thuộc lớp nào?** Diagnostic compile, `LinkageError` hay application exception?
3. **Class/method/field nào được yêu cầu?** Ghi nguyên tên và descriptor nếu có.
4. **Client binary được compile với artifact nào?** Không đoán chỉ từ version trong một file POM.
5. **Runtime thực sự load artifact nào?** Kiểm tra classpath/module path/classloader.
6. **ABI giữa hai artifacts đổi ở đâu?** Dùng `javap -p -s -v` khi cần.
7. **Khác biệt có thể khắc phục ở client hay library?** Restore API hoặc recompile và đóng gói nhất quán.
8. **Sau sửa đã test cả old binary và packaged runtime chưa?** Không chỉ chạy lại compilation.

## 13. Một số hiểu nhầm có thể gây phát hành lỗi

**“Đã compile thành công thì liên kết runtime chắc chắn thành công.”** Sai. Bytecode tham chiếu symbolic members được resolver kiểm tra ở runtime, trong môi trường có thể chứa dependency phiên bản khác.

**“`NoSuchMethodError` là một `Exception` nên catch `Exception` sẽ bắt được.”** Sai. Nó là một `LinkageError`. Cách chữa chính là sửa artifact mismatch, không bao lỗi bằng try-catch chung.

**“Chỉ cần sửa source của app để thích nghi là mọi client cũ đều an toàn.”** Sai. Nếu bạn phát hành library công khai, old binaries chưa recompile vẫn có thể gọi method descriptor cũ. Cần đánh giá binary compatibility riêng.

**“Compiler sẽ thay thế method cũ bằng method tên gần giống trong JAR mới.”** Sai. Resolution tuân theo method owner, name và descriptor mà client binary chứa; compiler overload resolution đã diễn ra từ lúc biên dịch old client.

**“Mọi thay đổi public API đều làm old binary lỗi.”** Sai. Thêm overload có thể binary compatible; đổi method body hoặc `throws` clause không tự phá binary compatibility, dù source/behavior có thể thay đổi.

**“Đổi `static final int` rồi old client vẫn chạy nghĩa là linker đã chọn version mới.”** Không chắc. Compiler có thể inline constant vào client nên không resolve field tại runtime; client cũ còn giữ giá trị cũ.

**“Classpath của IDE và production luôn giống nhau.”** Sai. Test runner, server, Gradle/Maven, fat JAR và container có thể chọn dependency/classloader khác.

**“Mọi `NoClassDefFoundError` đều do JAR không tồn tại.”** Sai. Nó cũng có thể liên quan initialization failure hoặc nguyên nhân sâu hơn; đọc cause.

**“Đổi class-file major bằng hex editor sẽ xử lý incompatibility.”** Sai. Class format có thể chứa constructs JDK cũ không hiểu; đổi header không chuyển đổi bytecode hay ABI hợp lệ.

**“Linkage error bắt buộc xuất hiện ngay lúc start.”** Sai. JVM có thể trì hoãn resolution; test phải cover các code paths.

## 14. Checklist xác minh trước khi release

- [ ] Source client biên dịch lại với dependency versions mà bản phát hành thực sự sử dụng?
- [ ] Class files/JARs cuối cùng có target major version phù hợp JVM tối thiểu?
- [ ] Compile classpath và runtime classpath được đối chiếu sau dependency resolution?
- [ ] Các transitive dependencies, shaded classes và module/classloader paths được kiểm tra?
- [ ] Nếu hỗ trợ old clients, đã chạy test **không recompile old binaries** với bản library mới?
- [ ] Đã kiểm tra method/field JVM descriptors và access/static flags cho thay đổi public ABI?
- [ ] Đã xem xét generic erasure, bridge methods và inline compile-time constants?
- [ ] Đã phân biệt source compatibility, binary compatibility và behavioral compatibility?
- [ ] Đã chạy integration tests trên **artifact đã đóng gói** với Java runtime mục tiêu?
- [ ] CI không chỉ dựa vào `javac` exit code; có thêm runtime smoke tests ở các luồng trọng yếu?
- [ ] Log đủ thông tin từ `NoSuchMethodError`/`IllegalAccessError` để xác định binary caller và actual callee?
- [ ] Nếu thay API không tương thích, có migration/versioning plan hoặc compatibility shim?
- [ ] Đã chạy lại build/test từ đầu ra sạch để tránh class files cũ che lỗi?

**Ghi nhớ:** *Lỗi biên dịch* cho biết mã nguồn hiện tại không phù hợp với những thư viện mà `javac` đang nhìn thấy. *Lỗi liên kết* cho biết JVM không thể đáp ứng tham chiếu đã được ghi vào **binary cũ** bằng những class/member thực sự có ở runtime. Để xác minh thư viện tương thích, hãy so sánh **cả source API, ABI của class files và runtime artifact graph**, không lấy một lần compile thành công làm bằng chứng duy nhất.

## Tài liệu tham khảo chính thức

- Java Language Specification 17, **Chương 13 — Binary Compatibility**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html
- Java Virtual Machine Specification 17, **Chương 5 — Loading, Linking, and Initializing**, nhất là `5.4` Resolution: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- Java SE 17, API **`LinkageError`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html
- Java SE 17, API **`NoSuchMethodError`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html
- Java SE 17, API **`UnsupportedClassVersionError`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedClassVersionError.html
- Oracle JDK 17, **`javap` command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- Oracle JDK 17, **`javac` command**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html