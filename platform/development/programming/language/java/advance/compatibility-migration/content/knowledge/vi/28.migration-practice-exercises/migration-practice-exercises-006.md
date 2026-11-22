# Tìm và thay thế một API nội bộ bằng jdeps

Một ứng dụng Java có thể chạy tốt trên JDK cũ nhưng phát sinh cảnh báo, lỗi class loading hoặc lỗi quyền truy cập khi được chuyển lên Java 17, 21 hay một JDK mới hơn. Trong nhiều trường hợp, nguyên nhân là mã ứng dụng hoặc thư viện phụ thuộc vào **API nội bộ của JDK** như `sun.misc.Unsafe`, `sun.security.x509.*` hoặc các lớp thuộc `jdk.internal.*`.

Những API đó có thể đã được dùng trong nhiều năm và một số vẫn hiện diện trong JDK hiện đại. Tuy nhiên, chúng **không có cùng cam kết tương thích với Java SE API công khai**. Việc một internal class vẫn tồn tại trên runtime không bảo đảm chữ ký, quyền truy cập hoặc behavior của nó được giữ nguyên trong các bản JDK tương lai.

**`jdeps`** là công cụ đi kèm JDK, đọc class files/JARs để phát hiện phụ thuộc ở mức bytecode. Tùy chọn `--jdk-internals` giúp tìm những tham chiếu tĩnh tới API nội bộ. Nó không sửa source code, không chứng minh toàn bộ runtime behavior và không thể tự xác định một replacement đúng cho mọi use case.

Bài thực hành này thực hiện một vòng migration từ đầu đến cuối:

```text
Mã nguồn dùng sun.misc.Unsafe
               |
               v
       Biên dịch thành JAR
               |
               v
      jdeps --jdk-internals
               |
               v
        Tìm class vi phạm
               |
               v
       Hiểu hành vi cần giữ
               |
               v
 Thay bằng AtomicIntegerFieldUpdater
               |
               v
     Biên dịch --release 8
               |
               v
     Chạy concurrency contract test
               |
               v
      Quét lại JAR bằng jdeps
               |
               v
   Lưu bằng chứng và xử lý phần còn lại
```

Ví dụ trung tâm sử dụng `sun.misc.Unsafe.compareAndSwapInt` để tăng một bộ đếm một cách nguyên tử. Bản sửa sử dụng `java.util.concurrent.atomic.AtomicIntegerFieldUpdater`, là Java SE API công khai có mặt trong Java 8. Phần nâng cao giới thiệu `VarHandle` cho Java 9+ và hướng xử lý khi một thư viện bên thứ ba, reflection hoặc native code phụ thuộc API nội bộ.

> **Môi trường:** Các lệnh minh họa cho một JDK đầy đủ kiểu HotSpot/OpenJDK, ưu tiên JDK 17 hoặc 21 để thực hiện. Khi dùng JDK vendor/version khác, kiểm tra `jdeps --help`, `javac --help` và tài liệu release tương ứng. Không chỉnh production JVM hoặc bypass chính sách bảo mật chỉ để chạy bài lab.

---

## 1. Mục tiêu và tiêu chí hoàn thành

Sau khi hoàn thành, người học cần:

1. Phân biệt Java SE public API với JDK internal API và JDK-specific API.
2. Tìm được vị trí dùng internal class trong một compiled JAR bằng `jdeps`.
3. Hiểu report `jdeps --jdk-internals` ở mức module và class.
4. Dùng `javap` xác minh bytecode thực sự tham chiếu class/method nào.
5. Xác định behavior của code cũ trước khi chọn replacement.
6. Viết một implementation không còn sử dụng `Unsafe`.
7. Biên dịch source mới bằng `javac --release 8`.
8. Chạy cùng một bài kiểm tra concurrent trên code cũ và code mới.
9. Quét lại JAR để xác nhận finding của module được sửa đã biến mất.
10. Biết giới hạn của phân tích tĩnh, kiểm kê dependency graph và đưa kiểm tra vào CI.

**Điều kiện hoàn thành hợp lý:** JAR mới không còn tham chiếu `sun.misc.Unsafe` do source của bài lab tạo ra, sử dụng API chuẩn, vẫn tăng đủ số lượt khi chạy đồng thời và có thể biên dịch ở mức Java 8. Điều kiện này chỉ xác nhận scope của bài, không phải chứng nhận toàn bộ ứng dụng tùy ý đã tương thích với mọi JDK.

## 2. Chuẩn bị môi trường

### 2.1. Các công cụ cần có

- JDK 17 hoặc JDK 21 đầy đủ.
- `java` để chạy chương trình.
- `javac` để biên dịch.
- `jar` để đóng gói.
- `jdeps` để phân tích phụ thuộc.
- `javap` để xem bytecode.
- Một text editor/IDE và terminal.

Kiểm tra:

```shell
java -version
javac -version
jdeps --version
jdeps --help
```

Nếu công cụ không được tìm thấy, kiểm tra shell `PATH` và JDK installation. Một runtime image tạo bằng `jlink` có thể chỉ chứa các module để **chạy** ứng dụng, không bao gồm những development tools này.

### 2.2. Cấu trúc thư mục

Tạo một thư mục làm việc riêng:

```text
internal-api-lab/
  src/
    api/
      demo/Counter.java
    legacy/
      demo/LegacyCounter.java
    modern/
      demo/ModernCounter.java
    test/
      demo/CounterContractTest.java
  build/
    legacy/
    modern/
    test/
    legacy-counter.jar
    modern-counter.jar
    report-legacy.txt
    report-modern.txt
```

Các file trong `src` do người học tạo bằng nội dung cung cấp dưới đây. Các file trong `build` sẽ được tạo bởi lệnh biên dịch/đóng gói.

### 2.3. Tập trung vào artifact đã biên dịch

`jdeps` phân tích bytecode từ `.class` hoặc JAR. Nó không chỉ tìm chuỗi văn bản trong `.java`. Vì vậy phải **biên dịch code cũ trước khi chạy lệnh quét**.

Trong ứng dụng thật, nên quét các artifact mà release thực sự sử dụng, không chỉ các source classes ở IDE. Một thư viện phụ thuộc có thể sử dụng internal API dù source application không import bất kỳ `sun.*` class nào.

## 3. API nội bộ là gì?

### 3.1. Public API có hợp đồng hỗ trợ

Ví dụ Java SE APIs:

```java
java.util.concurrent.atomic.AtomicInteger
java.util.concurrent.atomic.AtomicIntegerFieldUpdater
java.lang.invoke.VarHandle
java.util.Base64
java.nio.ByteBuffer
java.security.cert.CertificateFactory
```

Các API công khai có phiên bản xuất hiện khác nhau: `VarHandle` cần Java 9+, `Base64` có trong Java 8. “Public” không đồng nghĩa có mặt trong tất cả JDK releases. Phải xác định **minimum Java** của sản phẩm trước khi chọn.

### 3.2. API nội bộ có rủi ro khác

Một số ví dụ:

```text
sun.misc.Unsafe
jdk.internal.misc.Unsafe
sun.security.x509.*
sun.reflect.* (tùy class và bản JDK)
```

Những lớp này có thể là chi tiết triển khai, không được Java SE specification cam kết ổn định. Với module system, một số nằm trong packages được đóng bởi strong encapsulation; một số quan trọng cho tương thích vẫn được cung cấp qua `jdk.unsupported`.

Không suy từ tiền tố tên một cách máy móc. Một số API có tên `com.sun.*` được JDK cung cấp với tài liệu cụ thể. Phải dùng công cụ, đặc tả và support policy của vendor để phân loại.

### 3.3. Vì sao ứng dụng cũ sử dụng chúng?

- Chưa có public API tương đương khi code được viết.
- Thư viện cần thao tác CAS, memory ordering hoặc native memory.
- Serialization/ORM tạo instance theo cơ chế đặc biệt.
- Framework/agent instrument bytecode hoặc đọc JVM internals.
- Mã đã được copy từ một ví dụ tối ưu hóa JVM-specific.
- Library cũ có fast path dùng internal API và fallback khác.

Không nên xóa một dòng `Unsafe` mà chưa xác định **vì sao** nó tồn tại. Một phép thay thế chỉ đúng khi giữ functional semantics và concurrency contract.

## 4. Công cụ `jdeps`: khả năng và giới hạn

### 4.1. Các tùy chọn quan trọng

| Tùy chọn | Mục đích |
|---|---|
| `--jdk-internals` | Tìm tham chiếu tĩnh tới API nội bộ JDK |
| `--class-path` hoặc `-cp` | Cung cấp JAR/classes phụ thuộc |
| `--recursive` hoặc `-R` | Đi theo dependencies theo khả năng công cụ |
| `--verbose:class` | Hiển thị phụ thuộc ở mức class |
| `--print-module-deps` | Đưa ra danh sách module dependencies |
| `--list-deps` | Liệt kê module dependencies |
| `--multi-release` | Phân tích đúng class variant của MR-JAR theo target |
| `--ignore-missing-deps` | Tiếp tục analysis khi có dependencies thiếu |

Không phải mọi option đều có thể kết hợp tùy tiện; dùng `jdeps --help` của JDK đang chạy để xác nhận cách gọi.

### 4.2. `jdeps` chỉ thấy một phần của câu chuyện

Ví dụ trực tiếp:

```java
import sun.misc.Unsafe;

Class<?> type = Unsafe.class;
```

Bytecode có class reference rõ ràng để `jdeps` có thể phân tích.

Ví dụ dynamic:

```java
Class<?> type = Class.forName("sun.misc.Unsafe");
```

Tên class trong ví dụ thứ hai nằm dưới dạng string. `jdeps` không thể chắc chắn mọi string là một class sẽ được nạp ở runtime; reflection, generated bytecode và plugin loading có thể không được phát hiện đầy đủ.

### 4.3. So sánh công cụ

| Công cụ | Trả lời câu hỏi |
|---|---|
| `javac` | Code có biên dịch được cho release/API target không? |
| `jdeps` | Artifact phụ thuộc những class/module/API nội bộ nào? |
| `javap` | Bytecode chứa method/class references cụ thể gì? |
| `java` | Behavior có hoạt động trên runtime đích không? |
| Maven/Gradle reports | Runtime dependency versions nào thực sự được chọn? |
| JFR/GC/runtime diagnostics | Hiệu năng và hành vi JVM trong thực tế thế nào? |

Một báo cáo `jdeps` không thay thế compiler checks, contract tests hoặc chạy ứng dụng trên JDK mục tiêu.

## 5. Định nghĩa bài toán bộ đếm nguyên tử

Ta cần một counter mà nhiều threads có thể cập nhật đồng thời:

```text
Counter
  incrementAndGet():
    - tăng chính xác 1
    - trả về giá trị sau khi tăng
  get():
    - đọc giá trị hiện tại
```

Giả sử 4 threads, mỗi thread tăng 10.000 lần:

```text
4 x 10.000 = 40.000 increments
Giá trị cuối phải là 40.000.
```

Nếu code dùng `value++` thông thường, các threads có thể đọc cùng giá trị trước khi ghi và làm mất increments.

### 5.1. Vì sao `volatile` không đủ?

```java
private volatile int value;

public int incrementAndGet() {
    return ++value;
}
```

`volatile` giúp một số đảm bảo visibility/ordering nhưng biểu thức `++` vẫn gồm đọc, cộng và ghi; toàn bộ read-modify-write không tự trở thành atomic.

### 5.2. CAS bảo vệ việc cập nhật

```text
value = 7

Thread A: đọc 7
Thread B: đọc 7
Thread A: CAS(expected=7, update=8) -> thành công
Thread B: CAS(expected=7, update=8) -> thất bại
Thread B: đọc 8 và thử lại
Thread B: CAS(expected=8, update=9) -> thành công

Kết quả đúng: 9
```

Code legacy dùng API internal cho thao tác CAS. Code mới phải giữ cùng behavior mà không phụ thuộc implementation details của JVM.

## 6. Tạo API chung cho hai implementation

File:

```text
src/api/demo/Counter.java
```

Nội dung:

```java
package demo;

public interface Counter {
    int incrementAndGet();

    int get();
}
```

Interface không lộ `sun.misc.Unsafe`, field offset, `AtomicIntegerFieldUpdater` hoặc `VarHandle`. Nhờ vậy, caller có thể dùng cùng một contract với nhiều implementations.

## 7. Tạo implementation legacy dùng `Unsafe`

File:

```text
src/legacy/demo/LegacyCounter.java
```

Nội dung đầy đủ:

```java
package demo;

import java.lang.reflect.Field;
import sun.misc.Unsafe;

public final class LegacyCounter implements Counter {
    private static final Unsafe UNSAFE;
    private static final long VALUE_OFFSET;

    static {
        try {
            Field field =
                Unsafe.class.getDeclaredField("theUnsafe");
            field.setAccessible(true);

            UNSAFE = (Unsafe) field.get(null);
            VALUE_OFFSET = UNSAFE.objectFieldOffset(
                LegacyCounter.class.getDeclaredField("value")
            );
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private volatile int value;

    @Override
    public int incrementAndGet() {
        for (;;) {
            int before = value;
            int after = before + 1;

            if (UNSAFE.compareAndSwapInt(
                    this, VALUE_OFFSET, before, after)) {
                return after;
            }
        }
    }

    @Override
    public int get() {
        return value;
    }
}
```

Đây là **mã cố tình dùng API nội bộ để minh họa**; không nên đưa nguyên xi vào một project mới.

### 7.1. Các điểm quan trọng

- `import sun.misc.Unsafe`: dependency nội bộ trực tiếp.
- `Unsafe.class`: tham chiếu class mà phân tích bytecode có thể nhìn thấy.
- `theUnsafe`: field private được lấy bằng reflection.
- `objectFieldOffset`: lấy offset của field trong object.
- `compareAndSwapInt`: cập nhật nguyên tử bằng CAS.
- `volatile`: field đồng thời được truy cập bởi nhiều threads.

Một số HotSpot JDK vẫn cung cấp `sun.misc.Unsafe` trong module `jdk.unsupported` vì lý do tương thích. Nhưng sự hiện diện đó **không biến nó thành Java SE API được bảo đảm lâu dài**.

### 7.2. Vì sao lấy instance bằng reflection?

`Unsafe.getUnsafe()` thường không dành cho application classes thông thường. Một số thư viện lịch sử dùng reflection để truy cập singleton instance.

Ví dụ này chỉ nhằm mô tả dependency đang cần được loại bỏ. Nếu JDK hoặc môi trường bảo mật không cho phép truy cập, đó là một kết quả migration có ý nghĩa; không nên phá policy để bằng mọi giá cho ví dụ cũ chạy.

### 7.3. Cảnh báo compile mong đợi

Khi compile, compiler có thể in warning đại ý:

```text
Unsafe is internal proprietary API and may be removed
in a future release
```

Wording và mức độ warning khác theo toolchain. Đây chính là một vấn đề cần quan tâm, không phải chỉ là warning noise cần tắt.

## 8. Biên dịch và đóng gói legacy JAR

### 8.1. Linux/macOS

Đứng tại root của `internal-api-lab`:

```shell
mkdir -p build/legacy

javac -d build/legacy \
  src/api/demo/Counter.java \
  src/legacy/demo/LegacyCounter.java

jar --create --file build/legacy-counter.jar \
  -C build/legacy .
```

### 8.2. Windows PowerShell

Có thể viết mỗi lệnh trên một dòng:

```powershell
New-Item -ItemType Directory -Force -Path build/legacy | Out-Null
javac -d build/legacy src/api/demo/Counter.java src/legacy/demo/LegacyCounter.java
jar --create --file build/legacy-counter.jar -C build/legacy .
```

Đường dẫn thư mục giả định khớp bố cục ở mục 2. Dấu `/` thường cũng được Java tools xử lý trong đường dẫn Windows; nếu IDE sử dụng cách đặt thư mục khác, thay cho phù hợp.

### 8.3. Vì sao chưa dùng `--release 8` trên legacy code?

`javac --release 8` giới hạn Java SE API symbols ở release mục tiêu, thường không cho dùng những lớp nội bộ như `sun.misc.Unsafe` trong build thông thường.

Để tạo artifact legacy có finding, bài dùng JDK hiện đại **không bật `--release 8`**. Vì vậy, bản legacy JAR trong lab không được tuyên bố là có thể chạy trên Java 8 chỉ dựa vào tên `legacy`. Bản sửa sẽ được compile rõ ràng với `--release 8`.

Nếu ứng dụng thực tế đã có JAR Java 8 dùng `Unsafe`, bạn có thể phân tích trực tiếp artifact đó mà không cần tự biên dịch demo.

### 8.4. Kiểm tra JAR có class

```shell
jar --list --file build/legacy-counter.jar
```

Kỳ vọng thấy `demo/Counter.class` và `demo/LegacyCounter.class`. Nếu chỉ thấy file source hoặc thiếu class, kiểm tra tham số `-d` và `-C` của lệnh build.

## 9. Chạy `jdeps --jdk-internals`

### 9.1. Lệnh chính

```shell
jdeps --jdk-internals build/legacy-counter.jar
```

PowerShell:

```powershell
jdeps --jdk-internals .\build\legacy-counter.jar
```

Một kết quả điển hình có ý nghĩa tương tự:

```text
legacy-counter.jar -> jdk.unsupported
   demo.LegacyCounter -> sun.misc.Unsafe
      JDK internal API (jdk.unsupported)
```

**Đây là output minh họa**, không cam kết khớp từng chữ với stdout của mọi JDK.

### 9.2. Cách đọc kết quả

| Thành phần | Ý nghĩa |
|---|---|
| `legacy-counter.jar` | Artifact đang quét |
| `demo.LegacyCounter` | Class trong application/JAR tạo dependency |
| `sun.misc.Unsafe` | Internal API được tham chiếu |
| `jdk.unsupported` | Module chứa class ở các JDK cung cấp nó |
| “JDK internal API” | Cảnh báo về mức hỗ trợ/tương thích |

Không suy từ `jdk.unsupported` rằng class luôn có trên mọi runtime custom; module có thể không nằm trong `jlink` image, hoặc vendor có khác biệt hỗ trợ.

### 9.3. Báo cáo cung cấp manh mối, chưa phải vị trí method cụ thể

`jdeps` có thể chỉ ra class nào tham chiếu `Unsafe` mà không nêu từng dòng source. Khi đã biết `demo.LegacyCounter`, quay về source tìm `objectFieldOffset` và `compareAndSwapInt`.

Nếu source không tồn tại hoặc không chắc đúng phiên bản đang chạy, chuyển sang `javap`.

### 9.4. Lưu báo cáo

Unix-like:

```shell
jdeps --jdk-internals build/legacy-counter.jar \
  > build/report-legacy.txt
```

PowerShell:

```powershell
jdeps --jdk-internals .\build\legacy-counter.jar | Out-File -FilePath build\report-legacy.txt -Encoding utf8
```

Lưu thêm:

```text
JDK vendor/full version:
jdeps version:
Application/artifact version:
Artifact checksum:
Scan command:
Finding:
Owning source/module:
Planned replacement:
```

Việc pin toolchain giúp so sánh report qua các lần nâng JDK mà không hiểu nhầm khác biệt format là code regression.

## 10. Xem binary references bằng `javap`

### 10.1. Lệnh phân tích

```shell
javap -classpath build/legacy-counter.jar \
  -c -p -v demo.LegacyCounter
```

Các chuỗi có thể thấy trong constant pool/bytecode:

```text
sun/misc/Unsafe
compareAndSwapInt
objectFieldOffset
theUnsafe
```

Cú pháp output thực tế có method descriptors, flags và constant-pool indexes. Nội dung trên chỉ nêu những biểu tượng cần tìm.

### 10.2. Tại sao không chỉ đọc source code?

- JAR production có thể được build từ commit khác.
- Đã có generated classes do annotation processor.
- Dependency được shade và relocate.
- Một bản JAR cũ còn trong container layer.
- Thư viện chỉ có binary, không có source.
- IDE và CI có dependency versions khác.

`javap` trên chính artifact được quét giúp xác nhận bytecode **thực sự** tham chiếu API nội bộ.

### 10.3. Điều `javap` không làm

`javap` không chứng minh code path được thực thi trong workload thật. Nó cũng không tự xác nhận API có replacement semantics tương đương. Để làm điều đó, phải hiểu yêu cầu và viết tests.

## 11. Tìm API thay thế cho nhu cầu CAS

### 11.1. Câu hỏi phải hỏi trước khi sửa

- Code có cần atomic increment hay chỉ đọc/ghi đơn giản?
- Field là `int`, `long` hay object reference?
- Có yêu cầu return old value/new value không?
- Cần volatile/acquire/release memory ordering nào?
- Object layout có phải một phần public binary contract không?
- Có hỗ trợ Java 8 hay đã nâng baseline lên Java 17/21?
- Hiệu năng trong hot path có phải yêu cầu đo được không?
- Có external caller phụ thuộc vào trường hoặc implementation không?

### 11.2. Bảng thay thế theo use case

| Cách dùng internal API | Public API đáng xem | Giới hạn |
|---|---|---|
| Atomic integer counter | `AtomicInteger` | Thay representation bằng một object |
| Atomic update trên volatile int field | `AtomicIntegerFieldUpdater` | Field và quyền truy cập phải phù hợp |
| Atomic update trên reference field | `AtomicReferenceFieldUpdater` | Kiểu field và visibility rules |
| CAS/access modes đa dạng | `VarHandle` (Java 9+) | Mức Java tối thiểu và access semantics |
| Direct buffer | `ByteBuffer.allocateDirect` | Không tương đương tùy ý raw addresses |
| Off-heap memory | API bộ nhớ phù hợp JDK, native abstraction | Phải xét ownership và lifecycle |
| Tạo object không qua constructor | Factory/constructor/serialization framework phù hợp | Thường không có thay thế một-một |
| Internal security/certificate APIs | JCA/JCE/`java.security.cert`/thư viện được hỗ trợ | Phải xét validation và standards |

Một internal API rất lớn như `Unsafe` không thể được thay thế toàn bộ bằng một class duy nhất.

### 11.3. Lựa chọn chính: AtomicIntegerFieldUpdater

`AtomicIntegerFieldUpdater` có từ Java 5, thuộc Java SE public API, cho phép cập nhật một field `volatile int` theo cách nguyên tử. Nó đúng phạm vi bài lab, giảm sự phụ thuộc vào JVM internals mà không buộc tăng minimum JDK.

## 12. Viết implementation mới

Tạo file:

```text
src/modern/demo/ModernCounter.java
```

Nội dung:

```java
package demo;

import java.util.concurrent.atomic.AtomicIntegerFieldUpdater;

public final class ModernCounter implements Counter {
    private static final AtomicIntegerFieldUpdater<ModernCounter>
        VALUE_UPDATER =
            AtomicIntegerFieldUpdater.newUpdater(
                ModernCounter.class,
                "value"
            );

    private volatile int value;

    @Override
    public int incrementAndGet() {
        return VALUE_UPDATER.incrementAndGet(this);
    }

    @Override
    public int get() {
        return value;
    }
}
```

### 12.1. Những gì đã được loại bỏ

Bản mới không còn:

```text
import sun.misc.Unsafe
Field("theUnsafe")
setAccessible(true) trên lớp Unsafe
objectFieldOffset(...)
compareAndSwapInt(...)
```

Thay vào đó là một public atomic updater. Caller tiếp tục gọi `Counter.incrementAndGet()` và `Counter.get()` như cũ.

### 12.2. `volatile` vẫn bắt buộc

`AtomicIntegerFieldUpdater` cần một field phù hợp với contract; với kiểu updater này, field mục tiêu phải là `volatile int`. Không thể tùy ý đổi thành `Integer` hoặc xóa `volatile`.

### 12.3. Vị trí tạo updater và quyền truy cập

Factory `newUpdater` kiểm tra quyền truy cập field. Trong ví dụ, updater được tạo ở static initializer của chính class chứa private field, tránh vấn đề access từ một module/class không được phép.

Nếu đưa logic factory sang helper class hoặc named module khác, cần xem accessibility và có thể phải điều chỉnh thiết kế. Không mở toàn bộ module chỉ để giữ một layout implementation thiếu rõ ràng.

### 12.4. Vì sao kết quả tương đương?

Bản cũ dùng CAS loop để đảm bảo mỗi lần tăng được ghi nguyên tử. `incrementAndGet` của updater cung cấp atomic update theo API contract, trả đúng giá trị mới.

Điều **không tương đương**:

```java
public int incrementAndGet() {
    return ++value;
}
```

Một biểu thức increment trên `volatile int` vẫn có thể mất updates khi chạy đa luồng.

## 13. Một phương án đơn giản hơn: AtomicInteger

Nếu không cần giữ primitive field, có thể dùng:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public final class SimpleCounter implements Counter {
    private final AtomicInteger value = new AtomicInteger();

    @Override
    public int incrementAndGet() {
        return value.incrementAndGet();
    }

    @Override
    public int get() {
        return value.get();
    }
}
```

Lựa chọn này thường dễ đọc và có ít ràng buộc về field access. Đánh đổi là representation/instance memory layout khác. Không nên mặc định updater nhanh hơn `AtomicInteger`; nếu hiệu năng quan trọng, đo trên workload tương đương.

## 14. Biên dịch bản mới bằng `--release 8`

### 14.1. Unix-like

```shell
mkdir -p build/modern

javac --release 8 -d build/modern \
  src/api/demo/Counter.java \
  src/modern/demo/ModernCounter.java

jar --create --file build/modern-counter.jar \
  -C build/modern .
```

### 14.2. Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path build/modern | Out-Null
javac --release 8 -d build/modern src/api/demo/Counter.java src/modern/demo/ModernCounter.java
jar --create --file build/modern-counter.jar -C build/modern .
```

**Ý nghĩa:** `--release 8` giới hạn cú pháp, class-file target và Java SE API được compiler nhận diện theo Java 8. Nó giúp tránh vô tình gọi các Java 11/17/21-only APIs khi artifact vẫn phải phục vụ Java 8.

### 14.3. Kiểm tra class-file version

```shell
javap -classpath build/modern-counter.jar \
  -verbose demo.ModernCounter
```

Với bản mới compile `--release 8`, dòng liên quan:

```text
major version: 52
```

Major 52 tương ứng Java 8. Tuy nhiên, nếu ứng dụng có dependencies bên ngoài, chúng cũng phải phù hợp minimum Java của distribution. Class chính major 52 chưa đủ kết luận cả runtime graph tương thích.

## 15. Quét lại JAR đã thay

### 15.1. Lệnh

```shell
jdeps --jdk-internals build/modern-counter.jar
```

PowerShell:

```powershell
jdeps --jdk-internals .\build\modern-counter.jar
```

Vì `ModernCounter` chỉ sử dụng Java SE public APIs, dự kiến báo cáo **không còn** finding `demo.ModernCounter -> sun.misc.Unsafe`.

Kết quả có thể không in gì hoặc có format khác tùy phiên bản `jdeps`; không được giả định công cụ luôn xuất một thông báo `PASS`.

### 15.2. Lưu báo cáo mới

```shell
jdeps --jdk-internals build/modern-counter.jar \
  > build/report-modern.txt
```

PowerShell:

```powershell
jdeps --jdk-internals .\build\modern-counter.jar | Out-File -FilePath build\report-modern.txt -Encoding utf8
```

### 15.3. Xem module dependencies khi cần

```shell
jdeps --list-deps build/legacy-counter.jar
jdeps --list-deps build/modern-counter.jar
```

Trên JDK phù hợp, bản legacy có thể phụ thuộc `jdk.unsupported`, trong khi bản modern chỉ dùng các module nền tảng như `java.base`. Danh sách module là một bằng chứng bổ sung, không thay thế `--jdk-internals` và runtime tests.

### 15.4. Bảng so sánh

| Hạng mục | Bản legacy | Bản modern |
|---|---|---|
| Implementation | `LegacyCounter` | `ModernCounter` |
| API dùng để cập nhật | `sun.misc.Unsafe` | `AtomicIntegerFieldUpdater` |
| Direct reflection vào `theUnsafe` | Có | Không |
| Field offset thủ công | Có | Không |
| `jdeps` finding nội bộ từ class lab | Có thể thấy | Dự kiến không còn |
| Java SE API tương thích Java 8 | Không thể dựa vào `Unsafe` | Có |
| Cần concurrency test | Có | Có |
| Có bảo đảm performance giống hệt | Không | Không |

Điều quan trọng là **thay đổi kỹ thuật mà vẫn giữ hợp đồng**; báo cáo không có finding chỉ là một phần của bằng chứng.

## 16. Viết contract test đa luồng

Tạo file:

```text
src/test/demo/CounterContractTest.java
```

Nội dung:

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class CounterContractTest {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: CounterContractTest <provider-class>"
            );
        }

        Class<?> type = Class.forName(args[0]);
        final Counter counter =
            (Counter) type.getDeclaredConstructor().newInstance();

        final int workers = 4;
        final int incrementsPerWorker = 10000;

        ExecutorService pool =
            Executors.newFixedThreadPool(workers);

        try {
            List<Future<?>> tasks =
                new ArrayList<Future<?>>();

            for (int i = 0; i < workers; i++) {
                tasks.add(pool.submit(new Runnable() {
                    @Override
                    public void run() {
                        for (int n = 0;
                                n < incrementsPerWorker; n++) {
                            counter.incrementAndGet();
                        }
                    }
                }));
            }

            for (Future<?> task : tasks) {
                task.get();
            }
        } finally {
            pool.shutdownNow();
        }

        int expected = workers * incrementsPerWorker;
        int actual = counter.get();

        if (actual != expected) {
            throw new AssertionError(
                "Expected " + expected + ", got " + actual
            );
        }

        System.out.println("PASS: counter=" + actual);
    }
}
```

### 16.1. Vì sao dùng `Class.forName`?

Ta muốn chạy cùng một test binary với hai implementations, không cần compile test trực tiếp tham chiếu cả `LegacyCounter` và `ModernCounter`.

Tên provider class được truyền như argument; test phản ánh một cách dùng dynamic class loading có chủ đích. Đây cũng là ví dụ rõ về giới hạn `jdeps`: từ bytecode của test, nó không thể biết người vận hành sẽ truyền class name nào.

### 16.2. Test có ý nghĩa gì?

- Bắt đầu với counter 0.
- Tạo bốn workers.
- Mỗi worker tăng 10.000 lần.
- Chờ tất cả `Future.get()` hoàn thành.
- So kết quả cuối với 40.000.
- Fail nếu thiếu increments.

Test này không chứng minh đầy đủ Java Memory Model, nhưng kiểm tra trực tiếp tính năng mà migration cần bảo toàn.

## 17. Biên dịch và chạy contract test

### 17.1. Compile test

Unix-like:

```shell
mkdir -p build/test

javac --release 8 \
  -cp build/modern-counter.jar \
  -d build/test \
  src/test/demo/CounterContractTest.java
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path build/test | Out-Null
javac --release 8 -cp build/modern-counter.jar -d build/test src/test/demo/CounterContractTest.java
```

Test chỉ tham chiếu `Counter` ở compile-time, nên không cần đưa legacy và modern implementation vào cùng compile classpath.

### 17.2. Chạy bản cũ

Unix-like:

```shell
java -cp "build/legacy-counter.jar:build/test" \
  demo.CounterContractTest demo.LegacyCounter
```

Windows PowerShell:

```powershell
java -cp "build/legacy-counter.jar;build/test" demo.CounterContractTest demo.LegacyCounter
```

Nếu runtime hỗ trợ code cũ và cho truy cập `Unsafe`, output dự kiến:

```text
PASS: counter=40000
```

Nếu bản cũ không thể khởi chạy do API nội bộ đã bị giới hạn hoặc thay đổi, ghi nhận exception và môi trường. Không nên bypass chính sách để có bằng được output mong muốn.

### 17.3. Chạy bản mới

Unix-like:

```shell
java -cp "build/modern-counter.jar:build/test" \
  demo.CounterContractTest demo.ModernCounter
```

Windows PowerShell:

```powershell
java -cp "build/modern-counter.jar;build/test" demo.CounterContractTest demo.ModernCounter
```

Output dự kiến:

```text
PASS: counter=40000
```

### 17.4. Không để cả hai JAR trong cùng test classpath

Trong demo, cả legacy JAR và modern JAR đều chứa `demo.Counter`. Để tránh duplicate classes không cần thiết, mỗi lần chạy dùng **một** JAR và test classes.

Trong project production, nên tách `Counter` vào một API JAR chung và chỉ đóng gói implementation tương ứng với release.

### 17.5. Các bài test cần thêm trước production

- Initial value và sequential increment.
- Nhiều counter instances độc lập.
- Số workers và số lần tăng khác nhau.
- Overflow nếu được hợp đồng cho phép.
- Performance dưới contention thực tế.
- Error handling/resource lifecycle nếu code nằm trong service.
- JDK tối thiểu được sản phẩm cam kết.
- Integration tests trên final application artifact.

Một lần 40.000 increments thành công không chứng minh tất cả điều kiện concurrent execution đã được kiểm thử.

## 18. VarHandle: lựa chọn cho JDK 9+

Nếu minimum JDK của ứng dụng là Java 9+, `java.lang.invoke.VarHandle` là public API cần cân nhắc khi code yêu cầu atomic access và các memory ordering modes.

### 18.1. Ví dụ đầy đủ

```java
package demo;

import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class VarHandleCounter implements Counter {
    private static final VarHandle VALUE_HANDLE;

    static {
        try {
            VALUE_HANDLE = MethodHandles.lookup()
                .findVarHandle(
                    VarHandleCounter.class,
                    "value",
                    int.class
                );
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private volatile int value;

    @Override
    public int incrementAndGet() {
        int before = (int) VALUE_HANDLE.getAndAdd(this, 1);
        return before + 1;
    }

    @Override
    public int get() {
        return value;
    }
}
```

### 18.2. Giá trị trả về khác nhau

`AtomicIntegerFieldUpdater.incrementAndGet(this)` trả giá trị **sau tăng**.

`VarHandle.getAndAdd(this, 1)` trả giá trị **trước tăng**. Vì vậy ví dụ cộng thêm 1 để đáp ứng `Counter.incrementAndGet()`.

Thay một API thấp tầng mà không kiểm tra return-value semantics có thể tạo bug dù không còn compiler warnings.

### 18.3. Baseline quan trọng

| API | Mức JDK tối thiểu |
|---|---|
| `AtomicInteger` | Java 5 |
| `AtomicIntegerFieldUpdater` | Java 5 |
| `VarHandle` | Java 9 |
| `sun.misc.Unsafe` | Không phải Java SE public API ổn định |

Nếu còn consumer Java 8, không đặt `VarHandle` trực tiếp trong shared implementation target 8. Có thể tạo adapter hoặc multi-release JAR khi thật sự cần nhiều implementations, nhưng phải kiểm thử từng JVM.

## 19. Những trường hợp Unsafe không thể thay thế đơn giản

### 19.1. Atomic operations khác direct memory

`Unsafe` có nhiều năng lực: CAS, object offsets, native memory, unaligned access, object allocation và một số thao tác JVM-specific.

Nếu code cũ chỉ dùng CAS trên `int`, `AtomicIntegerFieldUpdater` là một lựa chọn tự nhiên. Nếu code dùng `Unsafe.allocateMemory`, thay bằng updater là sai hoàn toàn về chức năng.

### 19.2. Off-heap memory

Các hướng hiện đại có thể gồm:

- `ByteBuffer.allocateDirect` nếu phù hợp model dữ liệu.
- Foreign Function & Memory API trên JDK có phiên bản được hỗ trợ.
- Native library abstraction được quản lý.
- Refactor đưa dữ liệu về on-heap khi không cần off-heap.

FFM API trở thành final trong JDK 22, nhưng trước đó trải qua các giai đoạn incubator/preview và API đã thay đổi. Không copy ví dụ JDK 22 vào Java 17 hoặc Java 21 rồi giả định tương thích.

### 19.3. Object allocation không gọi constructor

Một số serialization frameworks lịch sử dùng internal methods để tạo object. Việc thay bằng `new` có thể làm thay đổi invariant, constructor side effects và compatibility với dữ liệu cũ.

Cần xem framework được bảo trì và Java Serialization/JSON/JPA contracts, không chỉ cố thay method name.

### 19.4. Memory ordering

Một số code dùng release/acquire, volatile, opaque hoặc ordered memory access. Chuyển sang API công khai phải hiểu **Java Memory Model** và kiểu ordering thực sự được yêu cầu.

Đừng đánh đồng tất cả CAS, set hoặc lazy-set methods. Nếu semantics của code hiện tại không rõ, cần contract tests ở mức concurrency và có thể review chuyên sâu.

## 20. Thực hành phụ: Base64 internal API

Một số ứng dụng Java cũ dùng:

```java
sun.misc.BASE64Encoder
sun.misc.BASE64Decoder
```

Java 8 cung cấp public API `java.util.Base64`:

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] input = "Xin chào Java".getBytes(
    StandardCharsets.UTF_8
);

String encoded = Base64.getEncoder()
    .encodeToString(input);

byte[] decoded = Base64.getDecoder()
    .decode(encoded);
```

### 20.1. Không chỉ kiểm tra round trip

Hãy so behavior về:

- Base64 alphabet chuẩn hay URL-safe.
- Padding.
- MIME line wrapping.
- Whitespace handling.
- Character encoding của dữ liệu gốc.
- Error behavior với input không hợp lệ.

`Base64.getEncoder()`, `getUrlEncoder()` và `getMimeEncoder()` có mục đích khác nhau.

### 20.2. Lưu ý khi quét artifact quá cũ

Một internal class tồn tại trên JDK 8 nhưng đã không còn trong runtime hiện đại có thể được `jdeps` mới báo là missing dependency, thay vì nhận diện đầy đủ như JDK internal API trong target JDK đó.

Không kết luận code an toàn chỉ vì `--jdk-internals` không in tên class đã bị loại. Kết hợp scan trên các JDK baseline, source/binary inspection và runtime tests.

## 21. Ứng dụng thực tế: API nội bộ nằm trong dependency bắc cầu

Ví dụ:

```text
order-service.jar
   |
   +-- web-framework.jar
   |
   +-- messaging-client.jar
   |       |
   |       +-- buffer-helper.jar
   |                 |
   |                 +-- sun.misc.Unsafe
   |
   +-- jdbc-driver.jar
```

Nếu chỉ quét `order-service.jar`, có thể bỏ sót API nội bộ trong `buffer-helper.jar`. Một quét phù hợp cần bao gồm runtime dependency closure.

### 21.1. Dùng classpath và phân tích đệ quy

Unix-like:

```shell
jdeps --recursive --jdk-internals \
  --class-path "lib/*" \
  application.jar
```

PowerShell:

```powershell
jdeps --recursive --jdk-internals --class-path "lib/*" application.jar
```

Phân tích chỉ đầy đủ trong **phạm vi JARs/modules được đưa cho công cụ và có thể resolve**. Các plugin JARs load động, JARs lồng trong executable archives hoặc server-shared libraries có thể cần được thu thập riêng.

### 21.2. Chạy quét trực tiếp trên từng dependency

Trong một thư mục có nhiều runtime JARs, có thể lập inventory và quét từng artifact để tìm internal API không nằm trên đường static reference từ main JAR.

Khi tự động hóa, nhớ lưu artifact path, version và checksums. Không chỉ xuất “3 findings” mà không chỉ rõ JAR nào chứa chúng.

### 21.3. `--ignore-missing-deps` không phải giấy chứng nhận

Nếu buộc phải tiếp tục phân tích khi thiếu thư viện:

```shell
jdeps --ignore-missing-deps --recursive \
  --jdk-internals \
  --class-path "lib/*" \
  application.jar
```

Hãy đồng thời ghi nhận dependencies bị thiếu. Một scan chạy xong nhưng thiếu JAR chứa internal API có thể trả báo cáo không đầy đủ.

## 22. Maven: xác định nơi internal dependency đi vào

### 22.1. Kiểm tra dependency tree

```shell
./mvnw dependency:tree
```

Trong multi-module:

```shell
./mvnw -pl app-module dependency:tree
```

Có thể dùng Maven Dependency Plugin để copy runtime libraries vào một thư mục phân tích. Pin plugin version và kiểm tra scope để tránh nhầm test libraries với production dependencies.

### 22.2. Quy trình gợi ý

```text
Maven package
     |
     v
Xuất runtime dependency JARs
     |
     v
jdeps --jdk-internals trên ứng dụng + dependencies
     |
     v
Báo cáo theo JAR, owner, rủi ro
     |
     v
Nâng library / sửa source
     |
     v
Rebuild + quét lại + runtime tests
```

### 22.3. Compiler target

Nếu bản mới vẫn cần hỗ trợ Java 8:

```xml
<properties>
    <maven.compiler.release>8</maven.compiler.release>
</properties>
```

Phải dùng phiên bản Maven Compiler Plugin và javac phù hợp. `javac --release` là cơ chế của compiler hiện đại, không phải tùy chọn của javac Java 8.

### 22.4. Dùng BOM và dependencyManagement

Một dependency có internal API có thể được thay bằng phiên bản mới từ BOM/framework release line. Nhưng không ép một version tùy ý nếu nó không phù hợp các companion modules.

Khi nâng, kiểm tra:

- Minimum Java của thư viện mới.
- API/binary compatibility.
- Transitive graph.
- Framework support matrix.
- Runtime behavior và performance.

## 23. Gradle: kiểm tra runtimeClasspath

### 23.1. Resolved dependencies

```shell
./gradlew dependencies --configuration runtimeClasspath
```

Đối với subproject:

```shell
./gradlew :app:dependencies --configuration runtimeClasspath
```

Khi cần tìm nguồn một thư viện:

```shell
./gradlew :app:dependencyInsight \
  --dependency buffer-helper \
  --configuration runtimeClasspath
```

Windows có thể dùng `gradlew.bat` tương ứng.

### 23.2. Toolchain và release target

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 8
}
```

Compiler JDK 21 có thể tạo Java 8 class files với `--release 8` cho source mới dùng public APIs. Điều đó không tự hạ class major hoặc public API requirements của transitive dependency khác.

### 23.3. CI task quét nội bộ

Một pipeline nên chạy `jdeps` sau khi build JAR và resolve runtime classpath. Cần pin JDK toolchain dùng để chạy `jdeps`, thay vì ngẫu nhiên dùng JDK của Gradle daemon.

Không nhất thiết phải gắn mọi thao tác vào một Gradle plugin. Một script CI version-controlled có inputs/outputs rõ ràng cũng phù hợp.

## 24. Tạo CI gate và quản lý ngoại lệ

### 24.1. Đừng chỉ xem exit code

Một lần `jdeps --jdk-internals` có thể in danh sách internal API findings mà process exit status không báo “quality gate failed vì có finding”.

Nếu muốn CI fail khi phát hiện API nội bộ:

1. Pin JDK/tool version.
2. Lưu đầy đủ stdout/stderr và exit status.
3. Phân biệt tool error với scan findings.
4. Parse report bằng logic được kiểm thử.
5. Chạy positive fixture cố ý dùng `Unsafe`.
6. Chạy negative fixture chỉ dùng public APIs.
7. Fail nếu finding mới không nằm trong allowlist.
8. Không công bố PASS khi missing dependencies chưa được giải quyết.

### 24.2. Allowlist phải có deadline

Ví dụ metadata:

```yaml
artifact: legacy-buffer-helper
owner: platform-runtime
finding: sun.misc.Unsafe
status: temporary-exception
reason: upstream migration in progress
target_jdk: "21"
remediation: upgrade dependency
review_by: "YYYY-MM-DD"
```

Đây là mẫu khai báo chứ không phải định dạng chuẩn của `jdeps`. Không tự đặt vô hạn các exceptions; mỗi exception cần owner, rủi ro và ngày review.

### 24.3. Không tạo false assurance

Một gate chỉ quét source module chính có thể “xanh” dù production fat JAR vẫn chứa một bản library cũ.

Phải xác minh:

- Runtime dependencies đã resolve.
- Final JAR/WAR/OCI image layout.
- JARs nested hoặc server-provided.
- MR-JAR variants.
- Plugin/agent artifacts nếu có.
- Minimum runtime/JDK của production.

## 25. Khi thư viện bên thứ ba dùng Unsafe

Nếu `jdeps` báo một JAR không do bạn sở hữu đang tham chiếu `sun.misc.Unsafe`, không nên trực tiếp sửa binary trong local repository rồi bỏ qua nguồn gốc.

Các hướng xử lý:

1. Tìm phiên bản mới từ vendor có support JDK target.
2. Đọc release notes xem internal API fast path đã được thay chưa.
3. Chọn phiên bản framework/BOM tương thích, không ép từng JAR riêng.
4. Kiểm tra library có fallback được vendor hỗ trợ không.
5. Nếu library đã EOL, lập kế hoạch thay thế.
6. Fork có kiểm soát khi tổ chức có khả năng duy trì và kiểm thử.
7. Ghi nhận ngoại lệ có hạn nếu chưa thể xử lý ngay.

Một library có thể tiếp tục dùng `Unsafe` trong một code path và dùng public API trong path khác. Finding `jdeps` vẫn quan trọng, nhưng quyết định ưu tiên cần xem runtime support và tần suất dùng thật.

## 26. Phân biệt jdeps finding với lỗi JPMS

### 26.1. `jdk.unsupported` là gì?

Một số critical internal APIs như `sun.misc.Unsafe` nằm trong module `jdk.unsupported` trên các JDK hiện đại. Điều này hỗ trợ các trường hợp tương thích lịch sử, không biến API thành Java SE.

### 26.2. `InaccessibleObjectException`

Lỗi này thường xuất hiện khi reflection muốn truy cập member không được mở theo JPMS strong encapsulation. Nó có thể xảy ra với code mà `jdeps` không nhìn thấy dependency qua tên string.

### 26.3. `IllegalAccessError`

Có thể xuất hiện khi bytecode tham chiếu class/member không accessible theo access/module rules. Không phải mọi internal API finding đều tạo lỗi này.

### 26.4. Vì sao không chỉ thêm `--add-opens`?

`--add-opens` giúp mở quyền reflection trong một số trường hợp; `--add-exports` ảnh hưởng exports cho truy cập khác. Nhưng chúng:

- Không khôi phục class/method đã bị loại.
- Không sửa semantics của API nội bộ.
- Không xóa dependency khỏi bytecode.
- Có thể làm tăng rủi ro và chi phí duy trì flags.

Dùng workaround tạm có scope, owner và deadline nếu cần. Hướng dài hạn là thay sang public API hoặc library có support phù hợp.

## 27. Những giới hạn của phân tích tĩnh cần nhớ

### 27.1. Reflection strings

`Class.forName("sun.misc.Unsafe")` có thể không được `jdeps` nhận ra là class dependency trực tiếp. Cần source search và runtime integration tests.

### 27.2. Generated bytecode

Byte Buddy, ASM, Mockito, ORM, agents và proxies có thể sinh class ở runtime. Phải kiểm tra framework support matrix và thử trên JDK đích.

### 27.3. Native code

JNI/JVMTI libraries có thể phụ thuộc JVM implementation, OS/architecture hoặc ABI. `jdeps` không phân tích toàn bộ native shared library semantics.

### 27.4. Multi-release JAR

Một JAR có thể chứa:

```text
com/example/Feature.class
META-INF/versions/17/com/example/Feature.class
META-INF/versions/21/com/example/Feature.class
```

Khi quét, cần chọn `--multi-release` phù hợp và kiểm tra runtime thực sự nạp versioned class nào. Một scan cho một release không tự chứng minh tất cả variants sạch.

### 27.5. Internal API đã biến mất trên JDK mới

Một class nội bộ trong JDK 8 có thể bị loại ở JDK mới. `jdeps` chạy trên JDK mới có thể báo missing dependency thay vì gắn nhãn internal API như mong đợi.

Vì vậy “không có dòng JDK internal API” không tương đương với “không thiếu class”. Phải xem missing-deps warnings và runtime tests.

### 27.6. Custom runtime image

Một image do `jlink` tạo có thể không chứa `jdk.unsupported` hoặc những modules khác. Khi deploy trên custom runtime, kiểm tra module list và chạy actual image; một scan trên full JDK không thay thế thực tế deployment.

## 28. Hiệu năng sau khi thay API nội bộ

### 28.1. Correctness là ưu tiên đầu tiên

Thay CAS loop bằng public atomic updater chỉ thành công nếu giữ behavior. Tiếp theo mới đánh giá performance nếu use case yêu cầu.

### 28.2. Benchmark cần kiểm soát

Không kết luận từ một lần đo `System.nanoTime()` quanh vài trăm vòng lặp. Kết quả chịu ảnh hưởng:

- JIT warm-up.
- Dead-code elimination.
- CPU frequency/throttling.
- Cache effects.
- Contention.
- Allocation/GC.
- JDK version và flags.
- OS scheduling.

Nếu performance rất quan trọng, dùng JMH hoặc một harness được quản lý, chạy đủ warm-up/repetitions và ghi exact JDK/hardware.

### 28.3. Theo dõi sau deploy

Nếu code nằm trên hot path, cần so:

- Error rate, exception types.
- p95/p99 latency.
- Throughput.
- CPU và allocation.
- Heap/native memory.
- Lock contention.
- GC pauses.
- Resource saturation.

Không giữ `Unsafe` chỉ vì một benchmark sơ bộ chưa kiểm soát cho thấy nhanh hơn vài phần trăm.

## 29. Troubleshooting

### 29.1. Không tìm thấy `jdeps`

Nguyên nhân thường là PATH/JDK installation hoặc chỉ dùng JRE/custom runtime image.

Kiểm tra `java`, `javac`, `jdeps` có cùng toolchain/version không. Nếu cần, chạy `jdeps` từ đường dẫn JDK đầy đủ.

### 29.2. Compiler cảnh báo proprietary API

Đây là finding dự kiến ở mã legacy. Không tắt warning để kết luận migration xong.

### 29.3. `--release 8` không tìm thấy `Unsafe`

Internal API không nằm trong public Java SE API view của `--release 8` trên compiler hiện đại. Không cố bypass để đóng gói bản cũ; sửa sang public API như bài.

### 29.4. Legacy example không chạy được trên JDK mới

Có thể do reflective access policy, API đã thay đổi hoặc missing module. Ghi lỗi và xác nhận JDK target. Hướng chính là dùng bản modern.

### 29.5. Updater initialization thất bại

Kiểm tra field `value` có đúng tên, kiểu `volatile int`, class owner và quyền truy cập của updater factory không.

### 29.6. Test trả giá trị nhỏ hơn 40.000

Kiểm tra implementation có sử dụng atomic update thật không, test có chờ `Future.get()` không và có load nhầm class không.

### 29.7. jdeps vẫn báo Unsafe sau khi sửa

Một dependency JAR khác có thể còn tham chiếu `Unsafe`, hoặc artifact cũ chưa được rebuild/publish lại. Xem chính xác tên source class và JAR trong report, đối chiếu checksum.

### 29.8. jdeps trống nhưng runtime vẫn lỗi

Có thể thiếu dependencies, có reflection strings, native code, dynamic plugins, MR-JAR variants hoặc lỗi không liên quan internal API. Kiểm tra full stack trace và final artifact.

### 29.9. Kết quả khác nhau giữa JDKs

API internal modules, class availability và `jdeps` output có thể thay đổi. Pin exact JDK vendor/version, ghi commands và không so stdout từng byte giữa releases.

### 29.10. Bản sửa chạy đúng nhưng chậm hơn

Không lập tức quay lại Unsafe. Xác định workload, contention, allocation và JIT behavior; benchmark có đối chứng, sau đó chọn public API hợp lý.

## 30. Quy trình triển khai vào repository thật

### Bước 1: Chọn JDK mục tiêu

Ghi Java baseline, JDK vendor/full version, deployment format, OS/arch và support contract.

### Bước 2: Inventory binary artifacts

Lấy application JAR, runtime dependencies, plugin/agent JARs và server-shared libraries cần phân tích.

### Bước 3: Chạy `jdeps --jdk-internals`

Lưu report theo artifact và JDK version. Không bỏ qua những dependencies chưa resolve.

### Bước 4: Phân loại findings

Gắn mỗi finding với owner, mức độ ảnh hưởng, code path, khả năng thay thế và thời hạn xử lý.

### Bước 5: Hiểu hành vi

Đọc source, `javap`, tests và workload. Không sửa khi chưa biết API nội bộ thực hiện nhiệm vụ gì.

### Bước 6: Chọn public API thay thế

Ưu tiên Java SE API đủ mức baseline hoặc thư viện có support rõ. Tách adapters nếu cần hỗ trợ nhiều JDK.

### Bước 7: Refactor có tests

Giữ chức năng, concurrency semantics và data contract. Compile với `--release` phù hợp.

### Bước 8: Quét lại final artifact

Đối chiếu trước/sau, không chỉ quét một class source. Kiểm tra transitive dependencies.

### Bước 9: Runtime và performance tests

Chạy trên minimum/target JDK thực tế, test integration, error, latency và memory khi relevant.

### Bước 10: Ghi migration evidence

Lưu report, toolchain metadata, artifact checksums, remaining risks và rollback plan.

## 31. Bài tập mở rộng

### Bài tập 1: Dùng AtomicInteger

Tạo implementation khác từ `AtomicInteger`. Chạy cùng contract test và `jdeps`. So mức đơn giản, object layout và hiệu năng nếu cần.

### Bài tập 2: Dùng VarHandle

Tạo `VarHandleCounter` trên JDK 17/21, compile `--release 17`, chạy test và giải thích vì sao không dùng trực tiếp trong shared library target Java 8.

### Bài tập 3: Cố tình dùng `++value`

Tạo một counter không atomic, tăng số workers/lượt tăng và chạy test nhiều lần. Giải thích lost-update race và vì sao một lần may mắn trả đúng 40.000 không phải chứng minh thread safety.

### Bài tập 4: Reflection không bị phát hiện

Tạo một class chỉ dùng `Class.forName("sun.misc.Unsafe")`. Quét bằng `jdeps` và so với việc dùng `Unsafe.class`. Mô tả giới hạn phân tích tĩnh.

### Bài tập 5: Dependency bắc cầu

Tạo application JAR chỉ tham chiếu public API, nhưng phụ thuộc một library dùng `Unsafe`. So report khi chỉ quét app với khi cung cấp/quét tất cả runtime dependency JARs.

### Bài tập 6: Base64 compatibility

Thay `sun.misc.BASE64Encoder` bằng `java.util.Base64` cho một bộ dữ liệu mẫu. Kiểm tra padding, MIME wrapping, URL alphabet và whitespace behavior.

### Bài tập 7: Viết CI gate

Pin `jdeps` JDK version và tạo positive/negative fixtures. Thiết kế rule fail khi có finding mới hoặc missing dependencies, nhưng cho phép exception được review có hạn.

### Bài tập 8: Thư viện không còn được bảo trì

Một dependency cũ dùng `jdk.internal.*` và vendor đã EOL. Lập kế hoạch nâng version, thay thư viện, fork có kiểm soát hoặc migration adapter; xác định owner, deadline và test matrix.

## 32. Checklist kết thúc bài thực hành

### Chuẩn bị

- [ ] Có JDK đầy đủ với `javac`, `jar`, `jdeps`, `javap`.
- [ ] Biết exact vendor/full JDK version.
- [ ] Có thư mục demo riêng.
- [ ] Biết minimum Java của artifact cần hỗ trợ.
- [ ] Có binary JAR để quét, không chỉ source.

### Phân tích

- [ ] `jdeps --jdk-internals` phát hiện tham chiếu của legacy class.
- [ ] Đã xác định đúng owning class/JAR.
- [ ] Đã đối chiếu bằng source hoặc `javap`.
- [ ] Hiểu hành vi CAS của code cũ.
- [ ] Không nhầm finding với lỗi runtime chắc chắn.
- [ ] Đã ghi giới hạn của static analysis.

### Thay thế

- [ ] Chọn public API phù hợp JDK baseline.
- [ ] Không còn dùng `theUnsafe` và field offsets.
- [ ] Giữ atomic increment, không dùng `volatile ++`.
- [ ] Compile bản mới với `--release 8`.
- [ ] Không làm rò rỉ JDK mới API vào shared contract.
- [ ] Có test đa luồng cho giá trị cuối.

### Kiểm chứng

- [ ] `jdeps` quét lại JAR modern.
- [ ] Không còn finding của `ModernCounter` liên quan `Unsafe`.
- [ ] Đã chạy contract test với implementation mới.
- [ ] Đã xem class-file major và runtime Java tương ứng.
- [ ] Đã kiểm tra runtime dependencies nếu áp dụng vào project thật.
- [ ] Không xem report trống như chứng nhận toàn hệ thống.
- [ ] Đã lưu finding trước/sau và artifact/toolchain provenance.
- [ ] Có owner/plan cho các API nội bộ chưa xử lý.

## Kết luận

**Tìm và thay thế một API nội bộ bằng `jdeps`** là quy trình kết hợp phân tích bytecode với hiểu biết về Java API và kiểm thử behavior. Trong bài, `sun.misc.Unsafe` được sử dụng để tăng một field nguyên tử; `jdeps --jdk-internals` xác định sự phụ thuộc, sau đó `AtomicIntegerFieldUpdater` thay thế nhu cầu CAS mà không cần truy cập cấu trúc thấp tầng của JVM.

Làm migration đúng không đơn thuần là khiến một warning biến mất. Cần **hiểu mục đích của internal API, bảo toàn semantics, biên dịch đúng baseline, kiểm thử trên runtime thực tế và xác nhận final artifact không còn dependency đã xử lý**. Khi được kết hợp với dependency inventory, kiểm tra transitive JARs, CI gates và release provenance, `jdeps` trở thành một công cụ hữu ích để giảm rủi ro tương thích trong Java Advance Compatibility Migration.

