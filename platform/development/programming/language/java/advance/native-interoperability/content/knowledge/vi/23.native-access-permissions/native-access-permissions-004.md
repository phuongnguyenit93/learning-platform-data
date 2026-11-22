# Quyền truy cập native — Cấu hình cảnh báo hoặc từ chối bằng --illegal-native-access trên JDK hỗ trợ

## 1. Mục tiêu và phạm vi

Ứng dụng Java có thể tương tác với code ngoài JVM bằng **JNI** (Java Native Interface) và **FFM API** (Foreign Function & Memory API). Những thao tác như nạp thư viện C/C++, liên kết native method, tạo foreign downcall/upcall hay diễn giải vùng nhớ tại một địa chỉ tùy ý có thể làm hỏng bộ nhớ hoặc làm JVM crash nếu dùng sai. Java vì vậy có cơ chế **cấp quyền native access theo module** và **chính sách cho những lần truy cập chưa được cấp quyền**.

Từ **JDK 24**, **JEP 472 — Prepare to Restrict the Use of JNI** mở rộng cơ chế kiểm soát native access, thống nhất cách xử lý một số thao tác JNI và các restricted methods của FFM. Một tùy chọn JVM mới là:

```text
--illegal-native-access=allow
--illegal-native-access=warn
--illegal-native-access=deny
```

Ba chế độ **không cấp quyền riêng cho module nào**. Chúng chỉ quy định JVM **phản ứng ra sao nếu một module chưa được cấp quyền** mà cố thực hiện restricted native operation. Lựa chọn lâu dài phù hợp hơn là **cho phép đúng module cần native access** bằng `--enable-native-access`, đồng thời đặt `--illegal-native-access=deny` để phát hiện phần còn thiếu.

**Mục tiêu sau bài:** giải thích chính xác `allow/warn/deny` và phạm vi phiên bản; tạo ứng dụng Java 24 để kiểm tra cả ba; kết hợp `--enable-native-access=ALL-UNNAMED` hoặc tên module; hiểu cảnh báo/`IllegalCallerException`; sử dụng `jnativescan` để định vị nơi cần cấp quyền; và biết vì sao không nên dùng `allow` như cách sửa dài hạn.

**Phiên bản:** ví dụ thực thi đã kiểm chứng trên **OpenJDK 24.0.2, Windows x64**. Tài liệu Oracle cho **JDK 24, 25, 26** vẫn mô tả ba giá trị và mặc định `warn` ở các bản đó. Một bản JDK tương lai có thể đổi mặc định sang `deny` hoặc loại bỏ `allow`; phải kiểm tra tài liệu của JDK đang triển khai thay vì coi chính sách luôn cố định.

## 2. “Illegal native access” là gì?

**Native access** là việc Java truy cập hoặc gọi code/data nằm ngoài Java runtime. Trong cơ chế mới, không phải mọi thao tác tính toán Java thông thường đều yêu cầu quyền; đối tượng bị kiểm tra là **restricted native operations** theo đặc tả JDK.

### 2.1. FFM API

Ví dụ các phương thức bị hạn chế trong JDK 24:

- `Linker.downcallHandle(...)` để liên kết lời gọi Java → hàm C.
- `Linker.upcallStub(...)` để chuyển một Java `MethodHandle` thành callback pointer cho C.
- `SymbolLookup.libraryLookup(...)` để nạp/tra symbol từ native library.
- `MemorySegment.reinterpret(...)` để tạo view một vùng nhớ theo kích thước mà Java không tự chứng minh an toàn.
- `AddressLayout.withTargetLayout(...)` để gắn layout dữ liệu đích cho pointer.

Danh sách **không cố định vĩnh viễn**. Khi nâng JDK, tham chiếu tài liệu chính thức về restricted methods của đúng release. Ví dụ kiểm thử trong bài sẽ dùng `AddressLayout.withTargetLayout(...)` vì nó là **restricted** nhưng **không cần nạp DLL, không dereference con trỏ và không gọi một hàm C thực sự**.

### 2.2. JNI

Từ **JDK 24**, các đường đi JNI quan trọng cũng thuộc native-access restrictions:

- `System.load(...)`, `System.loadLibrary(...)`, `Runtime.load(...)` và `Runtime.loadLibrary(...)`: nạp thư viện native, có thể kích hoạt initializer hoặc `JNI_OnLoad`.
- Lần **binding** đầu tiên của một phương thức được khai báo `native` vào hàm tương ứng trong thư viện: một bước có rủi ro ABI và mã native.

JDK 24 có thể phát warning khi nạp thư viện JNI hoặc liên kết native method từ một module chưa được cấp native access. Với `deny`, một restricted operation trái phép phát `IllegalCallerException` thay vì tiếp tục hoạt động bình thường.

**Lưu ý:** điều này **không cấm JNI/FFM**. Hệ thống chỉ yêu cầu ứng dụng hoặc runtime deployment thể hiện rõ **module nào được tin cậy thực hiện native operations**. Cấp quyền không khiến native code an toàn nếu C pointer, C ABI, calling convention, lifetime hay đồng bộ bị sai.

## 3. Ba chế độ của --illegal-native-access

| JVM option | Khi một module **chưa được cấp native access** gọi restricted operation | Ý nghĩa sử dụng |
| --- | --- | --- |
| `--illegal-native-access=allow` | **Cho phép**, **không cảnh báo** | Tạm thời giảm nhiễu khi migration, nhưng che khuất module thiếu quyền |
| `--illegal-native-access=warn` | **Cho phép** và phát **warning lên stderr** lần vi phạm đầu tiên của mỗi module | Phát hiện nợ native access mà chưa gây gián đoạn dịch vụ |
| `--illegal-native-access=deny` | **Từ chối thao tác**, ném `IllegalCallerException` | Kiểm thử ứng dụng đã khai báo quyền đúng và chuẩn bị cho mặc định nghiêm ngặt hơn |

**Mặc định của JDK 24** là `warn`. Tài liệu Oracle JDK 25 và 26 cũng vẫn mô tả `warn` là mặc định. Tuy nhiên JEP 472 nêu định hướng **đổi mặc định sang `deny` trong một release tương lai**; `allow` là chế độ chuyển tiếp có thể bị loại bỏ. Không dự đoán một số hiệu bản phát hành cụ thể nếu chưa có công bố chính thức.

### 3.1. Chi tiết quan trọng của `warn`

- JVM chỉ phát **tối đa một nhóm cảnh báo cho mỗi module** trong một tiến trình, vào **lần đầu** module đó thực hiện illegal native access.
- Warning ghi ở **stderr**, không nhất thiết là stdout của ứng dụng.
- Module chưa được cấp quyền **vẫn được thực hiện thao tác**. `warn` là chính sách quan sát, **không phải sandbox**.
- Nếu khởi động **một JVM mới**, warning có thể lặp lại trong process mới; “một lần” không có nghĩa “một lần mãi mãi trên máy”.
- Nếu có **hai module khác nhau** cùng vi phạm, mỗi module có thể nhận cảnh báo riêng.
- Không được nhầm warning từ `--illegal-native-access=warn` với cảnh báo từ compiler về preview, deprecation hay một policy khác.

### 3.2. Chi tiết quan trọng của `deny`

- Khi một restricted operation chưa được cấp quyền, JVM ném `IllegalCallerException`.
- Nếu ứng dụng bắt exception, chương trình **có thể tiếp tục chạy** nhưng **thao tác native bị từ chối**; nếu không bắt, chương trình thường kết thúc do uncaught exception.
- `deny` **không tước quyền** của module đã được phép qua `--enable-native-access`. Hai flag được thiết kế để dùng cùng nhau.
- Với code cần chạy native thực sự, cấu hình `deny` mà **không cấp quyền đúng module** có thể làm fail lúc khởi động, khi load library hoặc ngay lần đầu gọi phương thức restricted.
- Đây là kiểm soát quyền tại các điểm API xác định, **không phải cơ chế chặn code C độc hại chạy bên trong một thư viện đã được cấp quyền**.

### 3.3. `allow` không phải “sửa triệt để”

Đặt `allow` chỉ ngăn cảnh báo/denial **theo chính sách hiện tại**, không giúp tìm được các thư viện Java/JNI đang cần native access. Cách sửa bền vững là xác định module thực hiện restricted call, **cấp quyền cho module đó** và chạy test với `--illegal-native-access=deny`. Giữ `allow` trong production lâu dài có thể che lỗi migration và gây sự cố khi phiên bản sau bỏ chế độ này.

**Giá trị hợp lệ trong JDK 24 là `allow`, `warn`, `deny`.** `debug` và `permit` thuộc lịch sử **`--illegal-access` cho reflection**, **không phải** giá trị của `--illegal-native-access`. Không chép các flag reflection cũ sang native access.

## 4. Phân biệt hai option: policy và explicit permission

### `--enable-native-access=...`: cấp quyền cho module

```bash
# Cấp quyền cho TẤT CẢ unnamed modules (code trên classpath):
java --enable-native-access=ALL-UNNAMED -cp out MyMain

# Cấp quyền cho một named module:
java --enable-native-access=com.example.nativebridge \
  --module-path mods \
  -m com.example.app/com.example.app.Main

# Cấp cho nhiều named modules cụ thể:
java --enable-native-access=com.example.nativebridge,com.example.codec \
  --module-path mods -m com.example.app/com.example.app.Main
```

Các tên `MyMain`, `com.example.app`, `com.example.nativebridge` và `com.example.codec` trong ví dụ chỉ minh họa cấu hình module; phải thay bằng class/module có thật trong dự án. Đối tượng cần được cấp quyền là **module chứa code trực tiếp thực hiện restricted operation**, không nhất thiết là module chứa `main`.

### `--illegal-native-access=...`: xử lý module chưa được cấp

```bash
# Mọi module CHƯA được cấp quyền sẽ bị từ chối.
java --illegal-native-access=deny -cp out MyMain

# Quyền được cấp rõ ràng; những module khác vẫn bị từ chối.
java --illegal-native-access=deny \
  --enable-native-access=ALL-UNNAMED \
  -cp out MyMain
```

Cách nhớ:

```text
              Module M gọi restricted operation
                            │
                            ▼
                M đã có native access?
                     ┌──────┴───────┐
                    YES             NO
                     │              │
                     ▼              ▼
                 Cho phép      --illegal-native-access?
                                  │
               ┌──────────────────┼─────────────────┐
               ▼                  ▼                 ▼
             allow               warn              deny
               │                  │                 │
             Cho phép          Cho phép        IllegalCallerException
             im lặng         + cảnh báo
```

**Kết hợp khuyến nghị khi chuẩn bị migration:**

```bash
java --enable-native-access=ALL-UNNAMED \
     --illegal-native-access=deny \
     -cp out MyMain
```

Đây là cú pháp đúng cho **classpath**. Trong hệ modular thực tế, nên **chỉ cấp tên module cần native** thay vì `ALL-UNNAMED` rộng. Nếu một thư viện Java trên classpath gọi restricted method, chính unnamed module của thư viện cần quyền; `--enable-native-access=com.example.app` **không tự cấp** quyền cho mọi JAR còn nằm trên classpath.

### Không nhầm với các flag khác

| Flag | Lĩnh vực | Có thay thế native access policy không? |
| --- | --- | --- |
| `--enable-preview` | Cho phép preview API/features của đúng JDK release | **Không**; preview và restricted permissions là hai việc khác nhau |
| `--add-opens` | Mở package để deep reflection | **Không** |
| `--add-exports` | Export package cho compile/runtime access | **Không** |
| `--illegal-access` | Cơ chế reflection cũ, đã obsolete từ JDK 17 | **Không**; không phải `--illegal-native-access` |
| `--enable-native-access` | Cấp quyền module thực hiện native restricted operation | **Có**, đây là đường cấp quyền đúng |
| `--illegal-native-access` | Xác định allow/warn/deny khi module **chưa được cấp quyền** | **Có**, đây là chính sách vi phạm, không phải danh sách cấp quyền |

Cả `--enable-native-access` và `--illegal-native-access` là **JVM launcher options**. Đặt **trước** tên main class, `-jar` hoặc mục tiêu `-m`. Không đặt `--illegal-native-access=deny` sau `NativeAccessModesDemo`, vì nó sẽ thành một string trong `args` chứ không cấu hình JVM.

## 5. Ví dụ Java chạy được: kiểm tra cả ba chế độ trên JDK 24

Ví dụ intentionally **không nạp native library** và **không gọi pointer nguy hiểm**. Nó gọi một **restricted FFM API** để thấy đúng chính sách mà JVM áp dụng, nhờ đó lặp lại được trên máy JDK 24+ có FFM API.

### 5.1. Source đầy đủ `NativeAccessModesDemo.java`

```java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.ValueLayout;

public final class NativeAccessModesDemo {
    public static void main(String[] args) {
        try {
            AddressLayout layout = ValueLayout.ADDRESS.withTargetLayout(
                ValueLayout.JAVA_INT);

            System.out.println("restricted call: OK");
            System.out.println("pointer bytes: " + layout.byteSize());
        } catch (IllegalCallerException denied) {
            System.out.println("restricted call: IllegalCallerException");
        }
    }
}
```

**Vì sao chọn `AddressLayout.withTargetLayout`?** JDK 24 đánh dấu nó là restricted FFM method. Nó cho phép khai báo loại dữ liệu đích của một pointer layout nhưng không dereference một địa chỉ C tùy ý. Vì vậy bài thử chính sách này **không cần C compiler hay shared library**. Các FFM operations khác như `Linker.downcallHandle` hoặc JNI `System.loadLibrary` cũng tuân theo native-access permissions, nhưng thử với chúng có thêm phụ thuộc platform.

`catch (IllegalCallerException)` ở đây chỉ để **đưa ra stdout ổn định cho bài học**. Trong production, không dùng catch này để âm thầm coi phần native không chạy là thành công; phải cấu hình đúng quyền hoặc báo lỗi triển khai.

### 5.2. Biên dịch một lần

Dùng `java`, `javac` **JDK 24**. Trên Windows PowerShell hoặc terminal Unix:

```bash
java -version
javac -version

mkdir -p out
javac -encoding UTF-8 -d out NativeAccessModesDemo.java
```

Không cần `--enable-preview` chỉ để dùng FFM ở JDK 24: FFM đã finalized từ JDK 22. `--illegal-native-access` không phải cờ của `javac`, mà thuộc **java launcher**.

### 5.3. Chạy default và `warn`

```bash
# Mặc định của JDK 24: warn.
java -cp out NativeAccessModesDemo

# Chỉ định rõ warn.
java --illegal-native-access=warn -cp out NativeAccessModesDemo
```

**Stdout cho mỗi lệnh (đã kiểm thử Windows x64/OpenJDK 24.0.2):**

```text
restricted call: OK
pointer bytes: 8
```

**stderr có nhóm warning**, trong đó các dòng quan trọng là:

```text
WARNING: A restricted method in java.lang.foreign.AddressLayout has been called
WARNING: java.lang.foreign.AddressLayout::withTargetLayout has been called by NativeAccessModesDemo in an unnamed module (...)
WARNING: Use --enable-native-access=ALL-UNNAMED to avoid a warning for callers in this module
WARNING: Restricted methods will be blocked in a future release unless native access is enabled
```

Dấu `(...)` chỉ phần đường dẫn classpath tùy máy, **không** là output nguyên văn của Java. Warning nêu **API bị hạn chế**, **class/module gây ra**, và **flag cấp quyền** được đề xuất. Theo chính sách `warn`, method vẫn hoạt động, vì vậy stdout vẫn báo `OK`.

### 5.4. Chạy `allow`

```bash
java --illegal-native-access=allow -cp out NativeAccessModesDemo
```

**Stdout đã kiểm thử:**

```text
restricted call: OK
pointer bytes: 8
```

**stderr liên quan native access của ví dụ: trống.** Không có warning dù module vẫn chưa được cấp quyền tường minh. Đây là lý do `allow` nguy hiểm nếu dùng để “làm sạch logs”: nó dễ che đi các JNI/FFM dependencies cần xử lý trước khi nâng JDK.

### 5.5. Chạy `deny` mà không cấp quyền

```bash
java --illegal-native-access=deny -cp out NativeAccessModesDemo
```

**Stdout đã kiểm thử:**

```text
restricted call: IllegalCallerException
```

Không có dòng `pointer bytes: 8`, vì restricted method đã bị từ chối. Chương trình demo **bắt exception có chủ đích**, nên process exit code vẫn có thể là `0`; đừng dùng riêng exit code của demo để tuyên bố native access thành công. Trong code thật, không bắt exception này một cách mù quáng hoặc biến denial thành một kết quả thành công.

### 5.6. Chạy `deny` nhưng cấp quyền đúng

```bash
java --enable-native-access=ALL-UNNAMED \
     --illegal-native-access=deny \
     -cp out NativeAccessModesDemo
```

**Stdout đã kiểm thử:**

```text
restricted call: OK
pointer bytes: 8
```

**Không có restricted warning** trong stderr của demo. Lý do: code ở unnamed module đã được cấp quyền explicit, nên `deny` chỉ áp dụng cho những module khác **chưa** được cấp. Đây là mẫu cấu hình **đúng về nguyên tắc**: strict policy + explicit permission.

### 5.7. Bảng kết quả tổng hợp đã chạy

| Cách chạy | Module được cấp quyền? | Stdout quan trọng | stderr native warning |
| --- | --- | --- | --- |
| Mặc định (JDK 24) | Không | `restricted call: OK`, `pointer bytes: 8` | Có |
| `--illegal-native-access=warn` | Không | `restricted call: OK`, `pointer bytes: 8` | Có |
| `--illegal-native-access=allow` | Không | `restricted call: OK`, `pointer bytes: 8` | Không |
| `--illegal-native-access=deny` | Không | `restricted call: IllegalCallerException` | Không; thao tác bị từ chối |
| `--illegal-native-access=deny --enable-native-access=ALL-UNNAMED` | Có | `restricted call: OK`, `pointer bytes: 8` | Không |

**Giới hạn của số `8`:** đó là độ rộng pointer theo byte trên **Windows x64** đã kiểm thử. Trên ABI 32-bit, `layout.byteSize()` có thể khác (thường là `4`), nhưng ý nghĩa `allow/warn/deny` không thay đổi.

## 6. Ví dụ named module: cấp quyền tối thiểu

Nếu ứng dụng modular hóa, không nên cấp `ALL-UNNAMED` cho toàn bộ classpath khi chỉ một bridge module cần restricted APIs. Ví dụ dưới đây được **biên dịch và chạy trực tiếp trên JDK 24**.

### 6.1. Cấu trúc project

```text
src/
└── com.example.nativebridge/
    ├── module-info.java
    └── com/
        └── example/
            └── nativebridge/
                └── NativeAccessNamedDemo.java
```

**`src/com.example.nativebridge/module-info.java`**:

```java
module com.example.nativebridge {
}
```

**`src/com.example.nativebridge/com/example/nativebridge/NativeAccessNamedDemo.java`**:

```java
package com.example.nativebridge;

import java.lang.foreign.AddressLayout;
import java.lang.foreign.ValueLayout;

public class NativeAccessNamedDemo {
    public static void main(String[] args) {
        try {
            AddressLayout layout = ValueLayout.ADDRESS.withTargetLayout(
                ValueLayout.JAVA_INT);

            System.out.println("named module: granted");
            System.out.println("native enabled: "
                + NativeAccessNamedDemo.class.getModule()
                      .isNativeAccessEnabled());
            System.out.println("pointer bytes: " + layout.byteSize());
        } catch (IllegalCallerException denied) {
            System.out.println("named module: denied");
        }
    }
}
```

`Module.isNativeAccessEnabled()` trả trạng thái cấp quyền native access cho module hiện tại. Vì lệnh restricted method đứng trước dòng check, chương trình sẽ in `named module: denied` khi bị chặn và không in trạng thái grant.

### 6.2. Biên dịch module

```bash
javac --module-source-path src -d mods -m com.example.nativebridge
```

### 6.3. Từ chối vì chưa cấp quyền

```bash
java --illegal-native-access=deny \
  --module-path mods \
  -m com.example.nativebridge/com.example.nativebridge.NativeAccessNamedDemo
```

**Stdout đã kiểm thử:**

```text
named module: denied
```

### 6.4. Cấp đúng named module, giữ `deny` cho phần khác

```bash
java --illegal-native-access=deny \
  --enable-native-access=com.example.nativebridge \
  --module-path mods \
  -m com.example.nativebridge/com.example.nativebridge.NativeAccessNamedDemo
```

**Stdout đã kiểm thử Windows x64/OpenJDK 24:**

```text
named module: granted
native enabled: true
pointer bytes: 8
```

Kết quả cho thấy **module trực tiếp gọi restricted method** mới cần được cấp quyền. Nếu `com.example.app` gọi vào một bridge `com.example.nativebridge` và chính bridge tạo FFM downcall, tên bridge là mục tiêu phù hợp cho `--enable-native-access`. Đừng cấp quyền ngẫu nhiên cho module `main` chỉ vì nó là điểm khởi chạy.

**Lưu ý:** command Java mang tính cross-platform trong shell hỗ trợ ký tự `\` để nối dòng (Linux/macOS, bash); trên PowerShell, dùng **một dòng lệnh** hoặc ký tự backtick của PowerShell để nối dòng thay vì `\`. Các lệnh một dòng đều có thể viết tương đương và đã được kiểm thử qua PowerShell.

## 7. Tìm module cần native access bằng `jnativescan`

**`jnativescan`** có từ JDK 24 để quét các JAR/module nhằm phát hiện những chỗ có khả năng dùng native functionalities, bao gồm **restricted method calls** và **khai báo phương thức `native`**. Nó hỗ trợ việc chuẩn bị `--illegal-native-access=deny` mà không cần dò từng stack trace thủ công.

Ví dụ ở mục 5 có thể đóng thành JAR:

```bash
# Chạy tại thư mục chứa class file, hoặc chỉ định đúng đường dẫn:
jar --create --file demo.jar -C out NativeAccessModesDemo.class

jnativescan --class-path demo.jar

jnativescan --class-path demo.jar --print-native-access
```

**Kết quả quét thực tế trên JDK 24 (rút gọn đường dẫn JAR cho dễ đọc):**

```text
demo.jar (ALL-UNNAMED):
  NativeAccessModesDemo:
    NativeAccessModesDemo::main(String[])void references restricted methods:
      java.lang.foreign.AddressLayout::withTargetLayout(MemoryLayout)AddressLayout
```

Với `--print-native-access`, **stdout chính xác** của thử nghiệm:

```text
ALL-UNNAMED
```

**Giới hạn của scanner:**

- `jnativescan` là **static analysis** trên cấu hình classpath/module path bạn cung cấp; nó không quan sát mọi code path thực thi bằng runtime.
- Reflection, plugin được tải động, code generated, thư viện chưa nằm trong JAR được quét hoặc native code do bên ngoài gọi có thể không xuất hiện đầy đủ.
- Kết quả `ALL-UNNAMED` chỉ nói code quét đang nằm trên classpath, **không chứng minh mọi JAR classpath thực sự cần quyền**.
- Với project modular, quét đúng root modules và dependencies; dùng kết quả cùng runtime tests chạy `deny`, không chỉ dựa vào phân tích tĩnh.
- Một cảnh báo runtime thường nêu rõ **caller class và module**. Có thể dựa vào nó để tìm đúng jar/library, nâng cấp dependency hoặc thiết kế named module.

Công cụ có thể hiện diện tùy bản JDK/JVM distribution. Kiểm tra `jnativescan --help` trên JDK đích; không giả định JDK 17/21 có lệnh này.

## 8. Cấu hình trong Maven, Gradle, IDE và production launcher

`--illegal-native-access` là **runtime flag**. Cấu hình compiler `javac` không tự truyền flag tới JVM chạy tests, `java -jar`, plugin executor, daemon, IDE hoặc Docker container.

### 8.1. Maven Surefire (fragment)

Ví dụ đoạn bên trong `pom.xml`:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration>
        <argLine>
          --illegal-native-access=deny
          --enable-native-access=ALL-UNNAMED
        </argLine>
      </configuration>
    </plugin>
  </plugins>
</build>
```

**Đây là fragment, không phải một `pom.xml` độc lập.** Dự án thật cần khóa phiên bản plugin tương thích JDK 24+ và cấu hình build đầy đủ. Nếu JaCoCo hay plugin khác đã sử dụng `argLine` để gắn Java agent, **không ghi đè `-javaagent`**; ghép hai loại flags bằng cách phù hợp với build hiện tại.

Khi dự án đủ điều kiện modularize, thay `ALL-UNNAMED` bằng tên module thực sự gọi native. Nếu bài test cần chạy **cả đường thất bại do thiếu grant**, tạo một test profile/process riêng với `--illegal-native-access=deny` mà **không** đặt `--enable-native-access` cho module cần thử; nếu cấp quyền trước thì không thể kiểm tra denial.

### 8.2. Gradle Groovy DSL (fragment)

```groovy
tasks.withType(Test).configureEach {
    jvmArgs '--illegal-native-access=deny',
            '--enable-native-access=ALL-UNNAMED'
}

tasks.withType(JavaExec).configureEach {
    jvmArgs '--illegal-native-access=deny',
            '--enable-native-access=ALL-UNNAMED'
}
```

`Test` điều khiển JVM chạy tests; `JavaExec` điều khiển JVM được task Gradle chạy. Các flags này **không bảo đảm** áp dụng cho một tiến trình `java -jar app.jar` ngoài Gradle: phải đặt ở launcher của sản phẩm, service unit, container command hoặc runtime options tương ứng.

### 8.3. IDE

Trong Run/Debug configuration của IntelliJ IDEA, Eclipse hoặc IDE khác:

- Chọn **JDK 24+** có hỗ trợ option.
- Đặt `--illegal-native-access=deny` và `--enable-native-access=...` vào **VM options**, không phải **program arguments**.
- Các cấu hình JUnit/test runner và code coverage thường có JVM riêng; phải cấu hình chúng độc lập.
- Nếu có nhiều JDK cài cùng máy, kiểm tra chính Java executable thực tế mà IDE dùng.

### 8.4. CLI và CI/CD

Ví dụ ứng dụng đóng gói thành JAR chạy trên classpath:

```bash
java --illegal-native-access=deny \
     --enable-native-access=ALL-UNNAMED \
     -jar myapp.jar
```

Với named module, dùng `--module-path` và `-m` như mục 6. Khi đóng gói thành Docker image hoặc Java runtime custom bằng `jlink`, bảo đảm launcher trong môi trường deploy có **cùng policy và grants** với CI. Không giả định biến `JAVA_HOME` của build là JDK đang chạy container.

Có thể dùng `JDK_JAVA_OPTIONS` hoặc Java `@argument-file` để chuyển launcher flags; việc này tác động đến **mọi process Java** thừa hưởng cấu hình, nên cẩn trọng khi dùng trong môi trường có nhiều ứng dụng. Cách rõ ràng hơn là cấu hình trực tiếp ở launcher cần native access.

### 8.5. Kiểm thử migration nhiều bước

1. Ghi nhận Java runtime thật bằng `java -version`.
2. Chạy baseline với **`--illegal-native-access=warn`** để tìm caller/module đang dùng restricted operations.
3. Chạy `jnativescan` trên các JAR/module thực tế và so khớp với warnings runtime.
4. Nâng/cập nhật thư viện native nếu có phiên bản hỗ trợ native access policy tốt hơn.
5. Cấp explicit native access chỉ cho module cần, ví dụ `com.example.nativebridge`.
6. Chạy integration tests với **`--illegal-native-access=deny`** để phát hiện lỗ hổng grant, kể cả các đường lazy JNI loading hoặc plugin tải theo yêu cầu.
7. Test native library loading/unloading, callbacks, error branches và shutdown sau khi thay chính sách.
8. Deploy với explicit grants và strict mode trên JDK có hỗ trợ; kiểm tra lại trên JDK release đích sau mỗi lần nâng cấp.

## 9. Hành vi theo phiên bản JDK

| JDK | FFM/JNI và native-access policy liên quan |
| --- | --- |
| **JDK 17** | FFM đời cũ còn trong incubator; **không áp nguyên** option `--illegal-native-access` JDK 24 |
| **JDK 21** | FFM **Third Preview (JEP 442)**, cần `--enable-preview` khi compile/run; không dùng lệnh `--illegal-native-access` mới của JDK 24 như thể đã có |
| **JDK 22–23** | FFM finalized từ JDK 22 (**JEP 454**), nhưng `--illegal-native-access` chưa có semantics chung của JEP 472; chính sách restricted FFM có khác biệt |
| **JDK 24** | **JEP 472** đưa `--illegal-native-access=allow/warn/deny` và áp dụng cơ chế cảnh báo JNI/FFM nhất quán; **warn mặc định** |
| **JDK 25–26** | Tài liệu Oracle tương ứng vẫn mô tả `allow/warn/deny` và `warn` mặc định; cần kiểm tra runtime thực tế |
| **JDK tương lai** | Định hướng chuyển sang **deny mặc định**, loại bỏ `allow` và cuối cùng option chuyển tiếp; không dựa vào mặc định cố định |

Không sử dụng `--illegal-native-access=debug`: đó không phải một mode hợp lệ. Không coi `--enable-preview` là cách cấp quyền restricted JNI/FFM. Không cho rằng `--enable-native-access` phải xuất hiện trong `javac` cho chương trình Java bình thường; đó là launch-time module permission.

### Khác biệt tinh tế giữa JDK 22–23 và JDK 24

JEP 472 làm **dịu** một số tình huống FFM ở JDK 24 để giống JNI: trước JDK 24, nếu đã cấp native access cho một hay nhiều module mà module khác gọi restricted FFM method thì module khác có thể bị từ chối bằng `IllegalCallerException`; với `warn` ở JDK 24, nó có thể được tiếp tục chạy kèm warning. Vì vậy việc một ứng dụng **chạy được trên JDK 24 với warnings** không chứng minh nó đã cấu hình an toàn cho chính sách `deny` của tương lai.

Giải pháp thử ổn định: cấu hình `--enable-native-access=...` tường minh cho module cần thiết và **bật `--illegal-native-access=deny`** ở CI. Đây cũng là hướng migration được Oracle đề xuất.

## 10. Chẩn đoán lỗi cấu hình thường gặp

| Hiện tượng | Lý do thường gặp | Cách sửa |
| --- | --- | --- |
| Console có `WARNING: A restricted method ...` | Module chưa được cấp quyền, policy `warn` | Tìm module trong warning; cấp đúng `--enable-native-access` |
| `IllegalCallerException` khi dùng FFM/JNI | Policy `deny` từ chối restricted call của module chưa được cấp | Cấp module đúng hoặc loại bỏ native operation không cần thiết |
| Có `--enable-native-access=com.example.app` mà bridge vẫn bị chặn | Restricted call thực tế nằm trong module thư viện/bridge khác | Cấp quyền cho module có caller thật; dùng `jnativescan`/warning |
| Bật `--illegal-native-access=allow` không còn warning | `allow` che vi phạm, không phải cấp quyền đúng | Chuyển sang explicit grant + `deny` |
| Đã chạy `deny` nhưng demo vẫn exit code 0 | Demo chủ động bắt `IllegalCallerException` | Kiểm tra stdout `restricted call: IllegalCallerException`, không chỉ exit code |
| `Unrecognized option: --illegal-native-access` | JVM quá cũ hoặc không hỗ trợ | Dùng JDK 24+ phù hợp, không áp flag mới cho Java 21 |
| `Unrecognized option / invalid mode debug` | Nhầm `--illegal-native-access` với `--illegal-access` | Dùng `allow`, `warn`, `deny` |
| Đặt flag sau tên main class | Flag trở thành program argument | Đặt trước class/`-jar`/`-m` |
| App chạy CLI được nhưng test fail | Test JVM chưa có permission/grant | Cấu hình Surefire, Gradle Test hoặc IDE test VM options |
| App test pass nhưng Docker fail | Runtime trong container khác JDK hoặc thiếu launcher flags | Kiểm tra `java -version` và command thực tế ở deploy |
| Warning từ một dependency trên classpath | Unnamed module chứa restricted native call | Tạm `ALL-UNNAMED` khi cần; lâu dài chuyển riêng bridge JAR sang module path |
| `--illegal-native-access=deny` đã qua nhưng native code vẫn crash | Chính sách không kiểm tra mọi ABI/lifetime/memory bug | Sửa C ABI, kích thước, pointer lifetime, allocator và native code |

### Không nhầm suppression warning với bảo mật thật

`--illegal-native-access=deny` giúp **phát hiện/cấm restricted operations từ module chưa được cấp quyền**. Sau khi một module đã được cấp native access, code trong module đó vẫn có thể sử dụng JNI/FFM không an toàn và làm JVM crash. Native access restriction không cô lập native code vào sandbox, cũng không kiểm tra toàn bộ mọi truy cập địa chỉ C/C++.

`allow` cũng không giúp truy tìm memory leaks, double-free, use-after-free hoặc stack corruption. Cần các lớp QA khác: kiểm thử ABI, runtime integration tests, xử lý lỗi JNI pending exception, FFM arena lifetime, memory sanitizers trên native side và giới hạn quyền ở cấp OS/process phù hợp.

## 11. Checklist triển khai

- [ ] Xác nhận **JDK 24+** thực sự hỗ trợ `--illegal-native-access`; không giả định từ phiên bản Java trong IDE.
- [ ] Ghi nhận `java -version` và đường chạy JVM thật ở CLI, tests, CI, Docker/production.
- [ ] Hiểu sự khác nhau giữa **policy cho module thiếu quyền** và **explicit module grant**.
- [ ] Chọn `warn` để dò native access đang xảy ra (trên JDK 24 mặc định là `warn`).
- [ ] Chọn `deny` để thử cơ chế nghiêm ngặt; không dùng `allow` làm workaround vĩnh viễn.
- [ ] Chỉ cấp `--enable-native-access` cho **module chứa restricted code**, không suy từ tên module `main`.
- [ ] Với classpath, hiểu `ALL-UNNAMED` cấp rộng cho các unnamed modules; modularize khi muốn quyền tối thiểu.
- [ ] Xác định JNI `System.loadLibrary`, native method binding và các restricted FFM methods trong dependencies.
- [ ] Quét `jnativescan` rồi chạy integration tests bằng `deny` để tìm dynamic paths chưa được quét.
- [ ] Không đặt VM flags thành program arguments; không trộn với `--illegal-access` hoặc `--enable-preview`.
- [ ] Đối với Maven/Gradle/IDE, cấu hình **từng JVM thực thi**, không chỉ bước compile.
- [ ] Khi nâng JDK, kiểm tra lại **mode mặc định và các mode còn được hỗ trợ** trong tài liệu chính thức.
- [ ] Dù có grant, tiếp tục kiểm soát C ABI, pointer bounds, arena lifetimes và native error handling.

## 12. Câu hỏi tự luyện

1. `--illegal-native-access=warn` cho phép restricted call chạy tiếp không, và warning được phát tối đa bao nhiêu lần cho một module trong cùng JVM?
2. `--illegal-native-access=deny` và `--enable-native-access=ALL-UNNAMED` có mâu thuẫn nhau không? Vì sao dùng cùng nhau là hữu ích?
3. Nếu code restricted nằm ở `com.example.nativebridge` còn `main` nằm ở `com.example.app`, tên module nào cần `--enable-native-access`?
4. Vì sao `allow` có thể là rủi ro migration dù chương trình không báo warning?
5. `IllegalCallerException` có nhất thiết làm JVM exit nonzero không nếu demo đã bắt exception?
6. Tại sao `AddressLayout.withTargetLayout` phù hợp để thử chính sách mà không cần thư viện C?
7. `jnativescan --print-native-access` trả `ALL-UNNAMED` nghĩa là gì, và tại sao vẫn cần runtime tests?
8. Cơ chế JNI nào mới chịu native access restrictions trong JDK 24 theo JEP 472?
9. `--enable-preview` hoặc `--add-opens` có thay được `--enable-native-access` không?
10. `--illegal-native-access=deny` có bảo đảm C code đã được cấp quyền sẽ không gây memory corruption không?
11. Nếu một cảnh báo chỉ xuất hiện khi lazy-load plugin trên production, bạn sẽ kiểm tra file/module và launcher flags nào?
12. Khi policy mặc định thay đổi ở một JDK tương lai, cần bảo đảm gì để app không bất ngờ thất bại?

**Ghi nhớ:** Trên **JDK 24 và các bản hỗ trợ `--illegal-native-access`**, `warn` **cho chạy và cảnh báo**, `allow` **cho chạy im lặng**, còn `deny` **chặn và ném `IllegalCallerException`** khi một module **chưa có quyền** gọi restricted native operation. Cách triển khai bền vững là **`--enable-native-access=<đúng module>` + `--illegal-native-access=deny`**, thay vì nới lỏng `allow` trên toàn JVM.

### Tài liệu chính thức

- [Oracle JDK 24 — java launcher: --enable-native-access và --illegal-native-access](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html).
- [Oracle JDK 24 — Migration Guide: Controlling the Effect of Native Access Restrictions](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html).
- [Oracle JDK 26 — Migration Guide: JNI/FFM native access restrictions](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html).
- [Oracle JDK 25 — jnativescan command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jnativescan.html).
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472).
- [Inside Java — JDK 24 Quality Outreach Heads-up: Prepares Restricted Native Access](https://inside.java/2024/12/09/quality-heads-up/).
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final, JDK 22)](https://openjdk.org/jeps/454).
