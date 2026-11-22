# Quyền native access và cấu hình theo yêu cầu của từng phiên bản

Trong **Java Advance Compatibility Migration**, các ứng dụng dùng JNI (Java Native Interface), Foreign Function & Memory API (FFM), thư viện native, Java agent hoặc công cụ instrumentation cần được đánh giá riêng khi nâng JDK. Một đoạn code gọi `System.loadLibrary()` có thể từng chạy mà không thấy cảnh báo, nhưng ở JDK mới sẽ phát cảnh báo về quyền truy cập native. Một đoạn FFM dùng `Linker.downcallHandle()` có thể yêu cầu bật quyền native access. Ở một chế độ chặt hơn, JVM từ chối thao tác với `IllegalCallerException`.

Tuy nhiên, không phải mọi lỗi liên quan `.dll`, `.so`, `.dylib`, agent hoặc reflection đều được sửa bằng cùng một cờ JVM. `--enable-native-access`, `--illegal-native-access`, `--add-opens`, `-javaagent` và `-XX:+EnableDynamicAgentLoading` có **mục tiêu khác nhau**. Dùng sai cờ có thể che dấu nguyên nhân thực hoặc mở rộng quyền nhiều hơn cần thiết.

Bài học giải thích native access là gì, thay đổi qua các JDK, cách gán quyền theo module, cách tìm thành phần yêu cầu quyền, ví dụ cấu hình cho classpath/module path/Gradle/Maven và cách kiểm chứng trên đúng runtime đích. Mục tiêu không phải là “tắt mọi cảnh báo”, mà là **cấp quyền có chủ đích cho code đáng tin cậy, giữ tính toàn vẹn của JVM và có bằng chứng tương thích theo từng JDK**.

## 1. Native access là gì và vì sao được kiểm soát?

Java code thông thường được JVM quản lý về kiểu dữ liệu, bộ nhớ và truy cập object. Khi chương trình gọi native code hoặc dùng một số API có khả năng tác động trực tiếp tới bộ nhớ ngoài JVM, runtime không còn xác minh đầy đủ mọi điều kiện an toàn.

Ví dụ:

- JNI nạp thư viện native bằng `System.loadLibrary` hoặc `System.load`.
- Java class khai báo method với modifier `native` và liên kết nó với một hàm native.
- FFM API liên kết lời gọi Java với function trong thư viện C, hoặc tạo một số kiểu memory view không an toàn.
- Một thư viện native thao tác pointer, buffer hoặc gọi những system API có ảnh hưởng đến process.
- Một Java agent dùng instrumentation hoặc native JVMTI để quan sát/chỉnh sửa quá trình chạy JVM.

Native code có thể hợp lệ và thiết yếu, ví dụ xử lý video, database driver có thư viện native, compression, machine learning, smart card hoặc tích hợp OS. Nhưng lỗi ở native code có thể gây **memory corruption**, crash JVM, leak resource hoặc thực thi mã ngoài dự kiến. Vì vậy, quyền native access được xem là quyết định cần khai báo bởi người cấu hình ứng dụng, thay vì tự động được cấp cho mọi thư viện.

**Native access enablement không phải sandbox.** Nó phân biệt những module đã được cho phép thực hiện thao tác native có rủi ro; một module có quyền vẫn phải dùng thư viện native an toàn và được kiểm thử.

## 2. Phân biệt JNI, FFM, Java agent và JVMTI

| Cơ chế | Vai trò | Ví dụ | Liên quan tới native access |
|---|---|---|---|
| JNI | Java gọi method native hoặc native code tương tác JVM | `native int calculate(int)`, `System.loadLibrary` | Từ JDK 24, các thao tác JNI thuộc phạm vi hạn chế theo JEP 472 |
| FFM API | API Java để truy cập memory ngoài heap và gọi native function | `java.lang.foreign.Linker`, `MemorySegment` | Một số phương thức được đánh dấu restricted; cần enable theo module |
| Java Instrumentation Agent | Instrument class khi startup hoặc lúc runtime | `-javaagent:agent.jar` | Có quy tắc riêng về dynamic agent loading; không đồng nhất JNI/FFM |
| Native JVMTI agent | Agent native tích hợp ở mức JVM tooling | `-agentlib:...`, `-agentpath:...` | Cần xem cơ chế và chính sách agent/JVM riêng, không suy ra mọi cờ JNI áp dụng tương đương |
| Reflection/JPMS | Truy cập metadata và member Java qua module boundary | `setAccessible(true)` | Điều khiển qua `opens` / `--add-opens`, không tự giải quyết bằng native access |
| Java classpath/module path | Quy định cách code/module được nạp | `-cp`, `-p` | Quyết định target được cấp quyền là `ALL-UNNAMED` hay named module |

Một ứng dụng có thể dùng nhiều cơ chế đồng thời. Khi thấy warning hoặc exception, phải xác định **JVM nào**, **code thuộc module nào**, **operation nào** và **cờ nào thật sự có tác dụng**.

## 3. Tại sao quyền native access có thay đổi qua từng JDK?

Lộ trình Java không áp dụng đồng thời một chính sách bất biến cho tất cả release. Có các mốc quan trọng:

| Mốc JDK | Nội dung cần biết | Lưu ý khi migration |
|---|---|---|
| JDK 8/11/17 | JNI được dùng rộng rãi; những giới hạn native access kiểu JEP 472 chưa vận hành như JDK 24 | Không chép nguyên các flag mới cho JDK cũ nếu launcher không hỗ trợ |
| JDK 17–21 | FFM trải qua các giai đoạn incubator/preview và thay đổi API theo release | Ví dụ code FFM phải khớp đúng release, đôi khi cần `--enable-preview` ở thế hệ preview |
| JDK 21 | JEP 451 bắt đầu cảnh báo khi agent được nạp động trong nhiều tình huống | Đây là **dynamic agent loading**, không phải cờ native access của JNI/FFM |
| JDK 22 | JEP 454 đưa FFM API thành final API trong `java.lang.foreign` | Một số thao tác FFM vẫn là restricted và cần `--enable-native-access` |
| JDK 24 | JEP 472 chuẩn bị hạn chế JNI; đồng bộ cảnh báo cho JNI và FFM | Có `--illegal-native-access=allow/warn/deny`; mặc định `warn` trong JDK 24 |
| JDK 25/26 | Chính sách restricted native operations tiếp tục có chế độ `warn` mặc định theo tài liệu các release này | Nên thử `deny` để chuẩn bị cho chính sách chặt hơn trong tương lai |
| Release tương lai | Tài liệu JEP 472 dự kiến một thời điểm `deny` trở thành mặc định | **Không tự gán một số JDK cụ thể** nếu release notes của đích chưa xác nhận |

Những dòng trên là các mốc quan trọng, không phải danh mục đầy đủ mọi thay đổi JNI/JVMTI theo vendor. Trước khi nâng production, đọc **release notes và java launcher documentation của đúng JDK/update/build đang triển khai**. Không coi mặc định của JDK 24 là lời hứa vĩnh viễn cho JDK 27 hoặc các JDK tiếp theo.

### 3.1. Mốc JDK 22: FFM API final không có nghĩa mọi method đều an toàn

FFM API final trong JDK 22 cho phép sử dụng những API `java.lang.foreign` mà không cần preview flag chỉ để kích hoạt bản final. Tuy nhiên, một số thao tác như tạo downcall handle hoặc nạp native library qua FFM vẫn được đánh dấu **restricted** vì có thể vượt khỏi bảo đảm an toàn của Java.

Do đó phải phân biệt:

- API có mặt trong một Java release.
- API được dùng với cú pháp nào ở release đó.
- Phương thức nào là restricted theo tài liệu của release.
- Module gọi phương thức ấy có native access hay không.

Một chương trình FFM có thể compile được nhưng khi chạy vẫn phát cảnh báo hoặc bị từ chối vì thiếu quyền.

### 3.2. Mốc JDK 24: native restriction áp dụng cả JNI

Với JEP 472, các thao tác như `System.loadLibrary`, `System.load`, `Runtime.loadLibrary`, `Runtime.load` và việc liên kết lần đầu một method khai báo `native` được xét trong cơ chế kiểm soát native access. Khi module chưa có quyền, hành vi được điều khiển bởi `--illegal-native-access`.

Mặc định `warn` cho phép thao tác tiếp tục và phát cảnh báo, thường tối đa một cảnh báo cho mỗi module đối với cơ chế này. Chính vì vậy, **ứng dụng vẫn chạy được không có nghĩa đã sẵn sàng cho thời điểm `deny` trở thành mặc định**.

## 4. Hai tùy chọn chủ đạo: --enable-native-access và --illegal-native-access

### 4.1. `--enable-native-access`: cấp quyền cho module cụ thể

Cú pháp launcher điển hình:

~~~text
--enable-native-access=module1,module2,...
~~~

Ví dụ cho named module:

~~~bash
java --enable-native-access=com.example.nativebridge \
     --module-path mods \
     --module com.example.app/com.example.Main
~~~

Trong ví dụ, `com.example.nativebridge` là module chứa code thực hiện restricted JNI/FFM operation. Nó **không nhất thiết là module có main method**. Cần xác định caller của restricted operation trước khi cấu hình.

Đối với ứng dụng chạy trên classpath:

~~~bash
java --enable-native-access=ALL-UNNAMED \
     -cp "app.jar:lib/*" \
     com.example.Main
~~~

`ALL-UNNAMED` cấp native access cho code trong các **unnamed modules** (thông thường là classpath). Đây là phạm vi rộng: không chỉ riêng một JAR có JNI. Trên Windows, danh sách classpath sử dụng dấu chấm phẩy `;` thay vì dấu hai chấm `:`.

Không cần nhét đường dẫn thư viện native vào giá trị của `--enable-native-access`. Tùy chọn này nhận **tên module Java hoặc ALL-UNNAMED**, không nhận tên `libmylib.so` hay file DLL.

### 4.2. `--illegal-native-access`: cách JVM xử lý khi chưa được cấp quyền

Từ JDK 24, hành vi có thể được chọn bằng:

~~~text
--illegal-native-access=allow
--illegal-native-access=warn
--illegal-native-access=deny
~~~

| Mode | Hành vi khi module chưa được cấp native access | Cách dùng hợp lý |
|---|---|---|
| `allow` | Cho thao tác tiếp tục, không cảnh báo từ cơ chế này | Chỉ cân nhắc chuyển tiếp ngắn hạn, không phải giải pháp cuối |
| `warn` | Cho tiếp tục và cảnh báo cho module liên quan | Giúp tìm code cần cập nhật cấu hình |
| `deny` | Từ chối thao tác restricted không được cấp quyền, có thể ném `IllegalCallerException` | Dùng ở môi trường kiểm thử để xác định toàn bộ module cần quyền trước tương lai chặt hơn |

Tùy chọn này là công cụ **định nghĩa chính sách đối với những module chưa được enable**. Cách khắc phục bền vững khi native access thực sự cần thiết là **enable đúng module**, không phải đặt `allow` cho toàn JVM vô thời hạn.

### 4.3. Kết hợp đúng hai tùy chọn

Một cấu hình kiểm chứng hữu ích trên JDK hỗ trợ cả hai:

~~~bash
java --enable-native-access=com.example.nativebridge \
     --illegal-native-access=deny \
     --module-path mods \
     --module com.example.app/com.example.Main
~~~

Ý nghĩa: module `com.example.nativebridge` được phép thực hiện restricted native operations; những module khác chưa được cấp quyền sẽ bị chặn khi thử thao tác đó. Nếu test fail, cần xác định module có thật sự cần quyền hay dependency đang làm gì ngoài dự kiến.

Đối với ứng dụng classpath có thể dùng:

~~~bash
java --enable-native-access=ALL-UNNAMED \
     --illegal-native-access=deny \
     -cp "app.jar:lib/*" com.example.Main
~~~

Cấu hình thứ hai dễ áp dụng hơn nhưng mở quyền rộng hơn. Không được coi nó tương đương với việc chỉ cho phép một JAR.

## 5. Classpath và module path quyết định độ chi tiết của quyền

JPMS phân biệt **named module** và **unnamed module**. Từ đó native access được cấu hình theo module, chứ không theo một package Java hoặc một method đơn lẻ.

| Vị trí code | Tên dùng khi enable | Phạm vi |
|---|---|---|
| Classpath | `ALL-UNNAMED` | Mọi code thuộc unnamed modules |
| Module path, explicit named module | `com.example.nativebridge` | Chỉ module có tên được chỉ định |
| Module path, automatic module | Tên module mà runtime xác định cho JAR | Một module automatic cụ thể |
| Dynamic module layer | Có thể dùng API cấp quyền cho module trong layer khi thỏa điều kiện | Phụ thuộc thiết kế module layer và JDK hỗ trợ |

Với thư viện đang nằm trên classpath, khi muốn giới hạn quyền chặt hơn, có thể xem xét chuyển JAR đó sang module path. Một JAR chưa được modularize có thể được JVM xử lý như **automatic module**. Tuy nhiên, việc chuyển classpath sang module path có thể phát sinh vấn đề tên module, split packages, readability hoặc service loading. Không chuyển chỉ để giảm phạm vi cờ mà không kiểm integration.

Tên automatic module không nhất thiết giống artifact Maven/Gradle. Xem thông tin module bằng:

~~~bash
jar --describe-module --file native-wrapper.jar
~~~

Khi JAR được cập nhật và tên file/module thay đổi, launcher config cũng có thể phải đổi. Nên dùng tên module ổn định nếu thư viện hỗ trợ.

### 5.1. Không nhầm quyền native với quyền package

`--enable-native-access=com.example.nativebridge` không export một package của module khác và không cho phép `setAccessible(true)` vào private field của JDK.

Ngược lại, `--add-opens=java.base/java.lang=ALL-UNNAMED` mở package cho deep reflection trong phạm vi cho phép, **không cấp quyền JNI/FFM restricted operations**.

Nếu framework vừa dùng reflection sâu vừa dùng native library, ứng dụng có thể gặp **hai vấn đề riêng**. Mỗi vấn đề cần root cause và remediation riêng; không thêm cả hai cờ chỉ vì thấy lỗi khởi động.

## 6. Ví dụ JNI tối giản

Mã Java có thể khai báo method native:

~~~java
package com.example.nativebridge;

public final class NativeMath {
    static {
        System.loadLibrary("native_math");
    }

    private NativeMath() {}

    public static native int twice(int input);
}
~~~

Lớp này cần một thư viện native phù hợp với OS/architecture và chứa implementation JNI khớp đúng khai báo. Ví dụ dùng từ consumer:

~~~java
package com.example.app;

import com.example.nativebridge.NativeMath;

public final class Main {
    public static void main(String[] args) {
        System.out.println(NativeMath.twice(21));
    }
}
~~~

Có thể tạo JNI header bằng compiler, trong môi trường dự án đã chuẩn bị:

~~~bash
javac -h native-headers \
      -d classes \
      src/com/example/nativebridge/NativeMath.java
~~~

Header được sinh chứa signature JNI mà code C/C++ cần triển khai. Việc build native binary với compiler và linker phụ thuộc OS/toolchain; ví dụ Java ở đây **không tự có thư viện native** nếu chưa compile/install nó.

### 6.1. Phân biệt ba loại lỗi JNI

| Biểu hiện | Nguyên nhân thường gặp | Điều tra |
|---|---|---|
| Warning về restricted native access | Module gọi JNI chưa được enable theo chính sách JDK | `--enable-native-access` cho đúng module |
| `IllegalCallerException` ở restricted operation trong mode `deny` | Caller không có native access | Cấu hình quyền và module caller |
| `UnsatisfiedLinkError` | Native library không tìm thấy, không tải được hoặc method symbol không khớp | `java.library.path`, OS/architecture, ABI, export symbol |
| JVM crash như `SIGSEGV` | Native code truy cập memory sai hoặc ABI mismatch | Core dump, hs_err log, native debugger và test an toàn |
| `UnsupportedClassVersionError` | Bytecode Java yêu cầu JDK mới hơn | Class-file version và runtime JDK |

**Không dùng native access flag để chữa `UnsatisfiedLinkError` do sai path hoặc sai symbol**. Đó là hai vấn đề độc lập.

### 6.2. Nơi đặt thư viện native

Thông thường `System.loadLibrary("native_math")` yêu cầu runtime tìm được file với tên theo OS, ví dụ `libnative_math.so` trên Linux hoặc `native_math.dll` trên Windows. Cách tìm kiếm phụ thuộc launcher, JVM, thư viện và chính sách OS.

Một cấu hình minh họa:

~~~bash
java -Djava.library.path=/opt/app/native \
     --enable-native-access=ALL-UNNAMED \
     -cp app.jar com.example.app.Main
~~~

`java.library.path` giúp tìm thư viện native trong một số kiểu load, nhưng **không cấp quyền native access**; còn `--enable-native-access` cấp quyền nhưng **không tìm hoặc sửa binary native**. Cần kiểm cả hai lớp.

## 7. Ví dụ FFM ở JDK 22+

Khi dùng FFM final API trên JDK 22 trở lên, một chương trình có thể tìm native symbol rồi tạo method handle để gọi function.

Ví dụ Java API minh họa:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class NativeFFM {
    public static void main(String[] args) throws Throwable {
        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup lookup =
                    SymbolLookup.libraryLookup(
                            Path.of("/opt/app/native/libnative_math.so"),
                            arena);

            MemorySegment symbol = lookup.find("twice").orElseThrow();

            MethodHandle twice = Linker.nativeLinker().downcallHandle(
                    symbol,
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT));

            int result = (int) twice.invokeExact(21);
            System.out.println(result);
        }
    }
}
~~~

Giả định thư viện đã có function C tương ứng `int twice(int)`, ABI khớp, file tồn tại trên Linux và JDK hỗ trợ API đúng như ví dụ. Đây không phải ví dụ có thể chạy trên Windows hoặc macOS mà không đổi đường dẫn/tên thư viện.

Các thao tác như `SymbolLookup.libraryLookup` và `Linker.downcallHandle` có liên quan tới restricted native access. Khi chạy trên runtime phù hợp, cần cấp quyền cho module chứa class gọi:

~~~bash
java --enable-native-access=ALL-UNNAMED \
     -cp classes NativeFFM
~~~

Nếu ứng dụng được đóng gói thành named module, thay `ALL-UNNAMED` bằng **module name thực sự** có restricted operation.

### 7.1. Native permission không bảo đảm memory safety của FFM

FFM giúp biểu diễn memory lifetime, layout và lời gọi native rõ hơn so với nhiều workaround dựa trên internal API. Nhưng khi tạo một downcall handle sai function descriptor hoặc dùng pointer sai, ứng dụng vẫn có thể crash hoặc làm hỏng dữ liệu.

Khi thay JNI bằng FFM:

- Xác minh calling convention và ABI.
- Kiểm kích thước `int`/`long`, alignment và struct layout của platform.
- Kiểm ownership/lifetime của native memory segment và arena.
- Đảm bảo native function không lưu pointer đã hết lifetime ngoài hợp đồng.
- Kiểm callback/upcall, thread-safety và native error handling.
- Thử trên từng OS/architecture được hỗ trợ.
- Ghi rõ module nào cần quyền native access.

Không coi việc bật cờ là bằng chứng code FFM đúng.

## 8. Nguồn cảnh báo cho biết module nào đang thiếu quyền

Ở JDK 24+, cảnh báo native access thường đề cập một method hoặc module gọi restricted operation. Một ví dụ mang tính minh họa:

~~~text
WARNING: A restricted method in java.lang.System has been called
WARNING: java.lang.System::load has been called by ...
WARNING: Use --enable-native-access=... to avoid a warning
~~~

Nội dung thông báo có thể thay đổi giữa các JDK/update, nên không phụ thuộc vào nguyên văn từng dòng. Những thông tin cần lấy:

1. Restricted method đã được gọi là gì?
2. Caller Java class thuộc JAR nào?
3. Caller thuộc named module hay unnamed module?
4. JVM runtime nào phát cảnh báo?
5. Code path nào kích hoạt operation?
6. Cấu hình native access đã được áp dụng lên JVM đó chưa?
7. Có nhiều thư viện/JAR khác cũng cần quyền không?

Không nên giải quyết bằng cách bật `--illegal-native-access=allow` cho toàn JVM rồi bỏ qua nguồn cảnh báo. Một runtime ở chế độ `warn` vẫn có thể chạy thành công nhưng warning chỉ ra khoản nợ migration cần xử lý.

## 9. Phân biệt --enable-native-access và --enable-preview

Hai cờ có ý nghĩa khác nhau:

- `--enable-preview`: cho phép sử dụng **preview features** của một Java release khi compiler/runtime yêu cầu.
- `--enable-native-access`: cấp quyền cho những module thực hiện **restricted native operations**.

Ở các JDK trước khi FFM trở thành final, ví dụ mã FFM có thể thuộc API incubator/preview và cách kích hoạt thay đổi theo release. Trên JDK 22+, FFM final API không đòi preview flag **chỉ để dùng bản final**, nhưng những method restricted vẫn có thể yêu cầu native access.

Không lấy ví dụ FFM viết cho JDK 21 rồi giả định compile trực tiếp trên JDK 22/25; package và API surface đã thay đổi qua giai đoạn incubator/preview. Hãy dùng mã và tài liệu của **đúng JDK mục tiêu**.

## 10. Java agents: dynamic attach không phải JNI/FFM policy

Trong module **Agent và mã native**, cần phân biệt chính sách native access với **dynamic agent loading**.

Một Java instrumentation agent được truyền từ lúc JVM khởi động:

~~~bash
java -javaagent:monitor-agent.jar -jar application.jar
~~~

Trong khi đó, một công cụ có thể attach agent vào một JVM đã chạy thông qua Attach API hoặc công cụ giám sát. JEP 451 (JDK 21) đưa vào cảnh báo về **nạp agent động** để chuẩn bị cho việc siết quyền trong tương lai.

Các flag liên quan trong những JDK hỗ trợ bao gồm:

~~~text
-XX:+EnableDynamicAgentLoading
-XX:-EnableDynamicAgentLoading
~~~

Ý nghĩa của chúng liên quan đến chính sách **dynamic loading của agent**, không tự cấp quyền JNI hoặc FFM. Khi điều tra:

| Triệu chứng | Lớp vấn đề |
|---|---|
| Warning khi agent được attach sau khi JVM đã chạy | Dynamic agent loading, JEP 451 |
| JNI load/native bind warning trên JDK 24+ | Native access, JEP 472 |
| FFM restricted method warning | Native access của module gọi FFM |
| `InaccessibleObjectException` khi agent reflect vào JDK internals | JPMS opens/reflective access |
| Không tìm thấy `libagent.so` | Native library path/ABI |
| Agent không tương thích class-file version | JDK/bytecode support của agent |

Một công cụ instrumentation có thể gây **nhiều loại warning độc lập**. Không tự ý đặt `-XX:+EnableDynamicAgentLoading` và `--enable-native-access=ALL-UNNAMED` cho mọi JVM chỉ vì có agent.

### 10.1. Native agent và Java agent khác nhau

- `-javaagent:...` nạp Java instrumentation agent theo chuẩn manifest/capabilities của agent.
- `-agentlib:name` hoặc `-agentpath:path` liên quan native agent/tooling interfaces.
- JNI/FFM restricted operations do Java code thực hiện phải tuân theo chính sách native access của JDK tương ứng.
- Chính sách nạp agent và các quyền của JVMTI có cơ chế riêng, không thể suy từ tên một flag sang flag kia.

Khi gặp lỗi từ một monitoring agent, ưu tiên xác nhận phiên bản agent được nhà cung cấp hỗ trợ trên JDK mới và cấu hình họ công bố.

## 11. Java SE module name và automatic module

Một thư viện native có thể được đóng gói dưới tên Maven:

~~~text
com.example:native-bridge:2.4.0
~~~

nhưng tên module JPMS thực tế có thể là `com.example.nativebridge` hoặc tên khác. `--enable-native-access` dùng tên **module**, không dùng `group:artifact:version`.

Với module descriptor explicit:

~~~java
module com.example.nativebridge {
    exports com.example.nativebridge.api;
}
~~~

Việc gọi native restricted operation bên trong module này có thể cần:

~~~bash
java --enable-native-access=com.example.nativebridge \
     --module-path mods \
     --module com.example.app/com.example.Main
~~~

`exports` không đồng nghĩa native access; module descriptor cung cấp quan hệ module/API, trong khi native access là quyết định của launcher hoặc cơ chế cấp quyền tương ứng.

Nếu JAR là automatic module, xác nhận module name bằng `jar --describe-module`. Không tự suy từ tên file khi dependency có `Automatic-Module-Name` hoặc cách đặt tên đã thay đổi qua phiên bản.

## 12. Manifest và các cách triển khai quyền native access

Ngoài CLI, một số JDK hỗ trợ cấu hình quyền native access bằng các cơ chế nhất định.

### 12.1. Manifest cho executable JAR

Một manifest có thể khai báo:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Enable-Native-Access: ALL-UNNAMED
~~~

Theo tài liệu các JDK hỗ trợ, manifest attribute này áp dụng cho executable JAR và có giá trị `ALL-UNNAMED`; nó **không cho phép chỉ định tên named module tùy ý** qua thuộc tính này.

Việc đưa quyền vào executable JAR có nghĩa người đóng gói đã chọn phạm vi rộng cho code classpath. Khi cần least privilege, dùng module path và launcher option nhắm đích cụ thể có thể phù hợp hơn.

### 12.2. Environment, argument file và runtime image

Tùy chọn native access có thể được đưa vào launcher bằng những cơ chế được tài liệu JDK hỗ trợ, chẳng hạn:

- Command line khi chạy `java`.
- `JDK_JAVA_OPTIONS` trong một số môi trường.
- Argument file `@options.txt` của Java launcher.
- Một custom runtime image xây bằng `jlink` với option được cấu hình qua plugin thích hợp.
- Native application tạo JVM qua JNI Invocation API có thể chuyển launch options khi khởi tạo.

Không nên phân tán một cờ ở cả script, environment và JAR manifest rồi mất kiểm soát phạm vi. Quyết định nên thuộc **cấu hình phát hành được quản lý** với owner và cách kiểm chứng hiệu lực.

### 12.3. Dynamic module layers

Nếu hệ thống tạo module layer động, các API như `ModuleLayer.Controller.enableNativeAccess(Module)` (có từ JDK 22 ở dạng final API) có thể được sử dụng trong điều kiện nhất định. Bản thân việc cấp quyền này cũng thuộc nhóm restricted operation và yêu cầu caller có native access.

Đây là tình huống chuyên biệt dành cho framework quản lý module layers. Một ứng dụng thông thường không cần viết code cấp native access động chỉ để dùng một JNI library trên classpath; launcher configuration thường rõ ràng hơn.

## 13. Gradle: cấp quyền đúng tiến trình JVM

Các JVM có thể khác nhau:

- Gradle daemon chạy plugin và build logic.
- `JavaCompile` dùng JDK compiler/toolchain.
- `Test` worker chạy unit/integration tests.
- `JavaExec` chạy ứng dụng hoặc tool.
- Java application khi triển khai production.
- Java agent có thể chạy ở một hoặc nhiều tiến trình trên.

Ví dụ cấu hình **JDK 24+** để phát hiện mọi native access chưa được cấp quyền ở test:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs(
        "--enable-native-access=ALL-UNNAMED",
        "--illegal-native-access=deny"
    )
}
~~~

Cấu hình này chỉ áp dụng cho JVM của những `Test` task được cấu hình. Không có nghĩa Gradle daemon hoặc ứng dụng production nhận các args tương tự.

Với một task `JavaExec`:

~~~kotlin
tasks.withType<JavaExec>().configureEach {
    jvmArgs(
        "--enable-native-access=ALL-UNNAMED",
        "--illegal-native-access=deny"
    )
}
~~~

Không áp dụng toàn cục khi chỉ một task cần native access. Nếu task A chứa code JNI còn task B không dùng, có thể cấu hình A riêng để giới hạn phạm vi.

### 13.1. Application plugin

Nếu dự án dùng Gradle Application plugin, có thể cấu hình JVM arguments mặc định cho scripts mà plugin tạo:

~~~kotlin
plugins {
    application
}

application {
    mainClass.set("com.example.Main")
    applicationDefaultJvmArgs = listOf(
        "--enable-native-access=ALL-UNNAMED",
        "--illegal-native-access=deny"
    )
}
~~~

Đây là ví dụ dành cho runtime/JDK hỗ trợ các option này. Dùng classpath hay module path trong bản phát hành thực tế sẽ quyết định có nên dùng `ALL-UNNAMED` hay named module. Build có thể chạy trên một JDK khác với runtime; không tự truyền `--illegal-native-access=deny` cho các JDK cũ không hỗ trợ flag.

### 13.2. Cẩn thận với Gradle daemon

Nếu warning do **Gradle plugin** dùng native code trong daemon, thêm `jvmArgs` cho test sẽ không xử lý được. Ngược lại, cấu hình daemon không tự truyền quyền native cho các forked test JVM.

Cần đọc stack trace/warning và xác định process ID, lệnh launcher, version Gradle/JDK và module caller. Ưu tiên nâng plugin hoặc sử dụng phiên bản công cụ được hỗ trợ thay vì mở quyền rộng cho toàn bộ build.

## 14. Maven: test plugin và Java runtime là các tiến trình khác

Khi chạy Maven, JDK chạy Maven core, compiler và test fork có thể khác nhau. Với Maven Surefire, có thể cấu hình JVM args cho forked tests theo plugin:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version><!-- choose a compatible plugin version --></version>
  <configuration>
    <argLine>
      --enable-native-access=ALL-UNNAMED --illegal-native-access=deny
    </argLine>
  </configuration>
</plugin>
~~~

Đây là **khung cấu hình**: khi dùng thực tế cần thay phần version/comment bằng version hợp lệ và đối chiếu JDK. Nếu Maven test không fork JVM hoặc plugin khác đảm nhiệm integration tests, các option cần được đặt đúng nơi plugin đó hỗ trợ.

Nếu sử dụng Maven Failsafe cho integration test, cấu hình tương ứng cho Failsafe. Không giả định `argLine` của Surefire tự cấu hình mọi plugin hoặc ứng dụng production.

Với `mvnw`/`gradlew`, wrapper giúp chọn build tool, **không tự bật native access cho tất cả JVM mà build khởi tạo**.

## 15. Container và deployment: quyền phải được áp dụng khi chạy thực tế

Một cấu hình test local không tự chuyển sang container production. Ví dụ Dockerfile có runtime JDK phù hợp:

~~~dockerfile
FROM eclipse-temurin:25-jre

WORKDIR /app
COPY app.jar /app/app.jar
COPY native/ /opt/app/native/

ENTRYPOINT [
  "java",
  "--enable-native-access=ALL-UNNAMED",
  "--illegal-native-access=deny",
  "-Djava.library.path=/opt/app/native",
  "-jar",
  "/app/app.jar"
]
~~~

Đây là ví dụ minh họa. Một image thực tế còn cần chọn đúng base image/digest đã được phê duyệt, quyền file, user không đặc quyền nếu phù hợp, native dependency, ABI, OS architecture và cách quản lý secret.

Trong deployment, cần xác minh:

1. Runtime có hỗ trợ những option launcher đã cấu hình không.
2. Container đang dùng đúng JDK feature/update/vendor được kiểm thử không.
3. Native library phù hợp Linux/Windows/macOS và CPU architecture không.
4. Các thư viện phụ thuộc hệ thống (ví dụ libc) có sẵn và ABI tương thích không.
5. Java process có quyền đọc/execute native binary cần thiết không.
6. Cờ có được áp dụng cho đúng JVM, kể cả worker/batch subprocess không.
7. Các cảnh báo mới có được thu thập và giám sát không.

Đưa quyền vào container không thể cứu một native binary bị compile cho hệ điều hành hoặc kiến trúc khác.

## 16. Tìm code cần native access bằng jnativescan

Từ JDK 24, công cụ `jnativescan` giúp phân tích tĩnh các JAR để tìm sử dụng restricted methods và các method khai báo `native`.

Ví dụ:

~~~bash
jnativescan --class-path app.jar
~~~

Để chỉ liệt kê các module được công cụ nhận diện có native access:

~~~bash
jnativescan --class-path app.jar --print-native-access
~~~

Nếu các JAR được đưa lên module path:

~~~bash
jnativescan --module-path mods \
    --add-modules com.example.nativebridge \
    --print-native-access
~~~

Một số phiên bản công cụ hỗ trợ `--release` để chọn tập restricted methods và lớp phù hợp với Java release mục tiêu, đặc biệt hữu ích khi phân tích multi-release JAR:

~~~bash
jnativescan --release 24 --class-path app.jar
~~~

Trước khi dùng, kiểm tra:

~~~bash
jnativescan --help
jnativescan --version
~~~

**Giới hạn:** công cụ là static analysis. Nó có thể không xác định mọi lời gọi phát sinh bằng reflection, dynamic class loading, JNI callbacks hoặc những JAR chưa đưa vào tập quét. Kết quả không có warning không chứng minh ứng dụng không bao giờ dùng native. Ngoài ra, tool này không phải thành phần mặc định của mọi JDK cũ: đừng thêm vào pipeline Java 17 rồi giả định sẵn có.

### 16.1. Phân tích tập dependency đầy đủ

Nếu ứng dụng đóng gói nhiều thư viện trong `lib/`, cần quét cả những JAR có khả năng chứa JNI/FFM, kể cả direct và transitive dependencies:

- Codec, compression, image/video processing.
- Database client/driver có native variant.
- Machine-learning inference/native BLAS libraries.
- Terminal/console libraries và platform-specific utilities.
- Java agents, profilers hoặc instrumentation toolkits.
- JNI wrappers trong third-party SDK.
- JAR được tải động qua plugin hệ thống.

Không cần quét JAR không có mặt trong runtime chỉ vì cùng group Maven. Quan trọng là **resolved dependency graph** và deployment artifact thực sự dùng.

## 17. Quan sát thư viện native bằng JFR và runtime logs

JDK Flight Recorder có thể cung cấp các sự kiện như:

~~~text
jdk.NativeLibraryLoad
jdk.NativeLibraryUnload
~~~

Những sự kiện này giúp nhìn thư viện native nào được load/unload trong JVM khi chạy một code path. Chúng không thay thế `jnativescan`, và việc không thấy event trong một session không chứng minh mọi code path không dùng native.

Trong quá trình điều tra, ghi:

- Tên tiến trình, JDK build và startup arguments.
- Thời điểm native library được load.
- JAR/class/module liên quan.
- Native library path, OS và architecture.
- Stack trace/warnings nếu có.
- Test case kích hoạt việc load/bind.
- Error type và kết quả sau khi cấu hình quyền.

Đừng trích xuất log chứa path nhạy cảm, credential hoặc thông tin người dùng không cần thiết vào báo cáo công khai.

## 18. Phân biệt native access warning với lỗi loading hoặc ABI

| Triệu chứng | Điều cần điều tra | Có chữa bằng --enable-native-access không? |
|---|---|---|
| `WARNING: restricted method ...` | Module nào dùng restricted JNI/FFM operation | Có thể, nếu thật sự cần và cấp đúng module |
| `IllegalCallerException` ở restricted method | Mode `deny` và caller chưa được cấp quyền | Có thể, sau khi xác minh |
| `UnsatisfiedLinkError: no ... in java.library.path` | File binary không được tìm thấy | Không, phải sửa đường dẫn/đóng gói |
| `UnsatisfiedLinkError` khi resolve JNI method | Symbol, signature, ABI, mangling | Không, phải sửa native implementation |
| `wrong ELF class` hoặc thông báo architecture mismatch | 32/64 bit, ARM/x64, OS binary | Không |
| Thiếu dependency của `.so`/`.dll` | Loader của OS và thư viện bắc cầu native | Không |
| `InaccessibleObjectException` | Module openness/deep reflection | Không, xem `opens`/`--add-opens` |
| Agent attach warning | JEP 451/dynamic agent loading | Không tự giải quyết; xem agent policy |
| `SIGSEGV` / `EXCEPTION_ACCESS_VIOLATION` | Native memory corruption hoặc lỗi ABI | Không, phải điều tra native crash |
| `UnsupportedClassVersionError` | Java bytecode không tương thích JVM | Không, chọn JDK/artifact phù hợp |

Một thao tác bị từ chối vì thiếu native access **có thể được sửa bằng cờ**, nhưng phải kiểm chứng rằng cờ không chỉ giúp chạy tới một lỗi native nghiêm trọng khác. Cấp quyền là điều kiện cho operation, không phải chứng nhận code an toàn.

## 19. Chuẩn bị cho mode deny theo cách có kiểm chứng

Với JDK 24+ và những bản có option tương ứng, nên thử nghiệm có kiểm soát:

~~~bash
java --illegal-native-access=deny \
     -cp "app.jar:lib/*" com.example.Main
~~~

Ở lần chạy này, không có module nào được cấp native access qua flag trong ví dụ. Nếu code path cần JNI/FFM, runtime có thể từ chối. Sau đó, tìm module thực sự và cấp quyền:

~~~bash
java --enable-native-access=ALL-UNNAMED \
     --illegal-native-access=deny \
     -cp "app.jar:lib/*" com.example.Main
~~~

Với module path, ưu tiên quyền theo tên module cụ thể. Một kế hoạch thực hiện:

1. Chạy baseline trên JDK mục tiêu ở chế độ mặc định, lưu warning.
2. Dùng `jnativescan` và dependency inventory để lập danh sách caller.
3. Thử `--illegal-native-access=deny` để tìm những đường còn thiếu quyền.
4. Với mỗi module, đánh giá có cần native operation không hay có thể bỏ/đổi dependency.
5. Cấp quyền tối thiểu và chạy lại test.
6. Chạy integration tests cho code path native: load, call, callback, error handling và cleanup.
7. Đưa đúng cấu hình qua test, app launcher và production deployment.
8. Theo dõi warning khi nâng JDK update hoặc thư viện mới.
9. Lưu điều kiện phải xem xét lại quyền, không sao chép vĩnh viễn các flag cũ.

Dù tất cả test pass, kết luận chỉ có hiệu lực cho **JDK, OS, architecture, native library, driver và code path đã kiểm**.

## 20. Những yêu cầu bảo mật và vận hành không thể giải quyết chỉ bằng cờ

Native code nằm ngoài một phần bảo đảm an toàn kiểu/bộ nhớ của Java. Một thư viện native đáng tin cậy vẫn có thể bị lỗi hoặc ảnh hưởng khi môi trường thay đổi.

Vì vậy, ngoài native access, cần kiểm:

- Provenance/checksum/signature của native binary và Java wrapper.
- CPU architecture, OS ABI, runtime library versions và static/dynamic linkage.
- Quyền filesystem để đọc/load thư viện.
- Ownership/lifetime của pointer, buffer, allocator/arena.
- Threading model của JNI/FFM, reentrancy và synchronization.
- Input validation khi truyền dữ liệu không tin cậy tới native function.
- Error handling và resource cleanup nếu native function thất bại.
- Crash dump handling và giới hạn truy cập log/dump chứa dữ liệu nhạy cảm.
- Concurrency và shutdown hooks.
- Tính tương thích của agent/profiler với JDK/runtime mới.
- Hiệu năng và memory usage khi đổi wrapper hoặc backend.

Nếu migration từ `sun.misc.Unsafe` sang FFM/VarHandle, phải xác định chính xác use case. `VarHandle` phù hợp nhiều phép truy cập có kiểm soát; FFM phù hợp nhiều bài toán foreign memory/native function; nhưng đây không phải hai API có thể thay nhau ở mọi trường hợp. Không nên tiếp tục dùng internal API chỉ vì một cờ tương thích làm warning biến mất.

## 21. Ma trận test theo JDK và runtime thực tế

Một ứng dụng được công bố hỗ trợ nhiều JDK cần có **ma trận bằng chứng**, không suy từ một lần chạy.

| Tổ hợp | Hạng mục xác minh |
|---|---|
| JDK 17 + JNI hiện tại | Có chạy JNI như kỳ vọng trên release này không; loader, native ABI |
| JDK 21 + agent/instrumentation | Warning dynamic agent loading, startup vs runtime attach |
| JDK 22 + FFM final | API source, restricted methods và `--enable-native-access` |
| JDK 24 + JNI/FFM | JEP 472 warning, `--illegal-native-access=deny` và module enablement |
| JDK 25/26 + native stack | Policies/defaults của release, runtime test, JAR/module và OS ABI |
| JDK tương lai | Đọc release notes trước; không mặc định behavior JDK 24 sẽ giữ nguyên |

Nếu ứng dụng chỉ chạy một JDK và một OS, có thể ưu tiên sâu vào tổ hợp đó. Nhưng nếu phát hành SDK hoặc thư viện cho consumer bên ngoài, cần xác định support policy và minimum JDK rõ ràng.

### 21.1. Test case quan trọng

- Nạp thư viện native lần đầu.
- Gọi native method bình thường, giá trị biên, lỗi và null.
- Gọi callback hoặc upcall nếu có.
- Tạo/hủy memory arena, kiểm ownership và leak.
- Chạy đồng thời nhiều thread.
- Khởi động với quyền đúng và với quyền thiếu ở môi trường test.
- Tìm native library trên từng OS/architecture được hỗ trợ.
- Kiểm behavior khi binary native không tìm thấy hoặc không tương thích.
- Thử agent attach khi đó là use case hợp lệ và được hỗ trợ.
- Theo dõi các thông báo warning/error sau nâng JDK.
- So sánh hiệu năng và tài nguyên với baseline.

Không chạy negative test gây crash hoặc memory corruption có chủ ý trên production. Dùng môi trường test được cách ly và dữ liệu an toàn.

## 22. Ghi native-access exception trong hồ sơ migration

Một bản ghi ví dụ:

~~~yaml
nativeAccess:
  component: "example-native-wrapper"
  javaArtifact: "com.example:native-bridge:2.4.0"
  targetJdk:
    feature: 25
    vendorBuild: "fill from java -version"
  execution:
    mode: "module-path"
    module: "com.example.nativebridge"
  requiredOperations:
    - "System.loadLibrary"
    - "JNI native method binding"
  approvedLaunchOptions:
    - "--enable-native-access=com.example.nativebridge"
    - "--illegal-native-access=deny"
  checks:
    jnativescan: "NOT_YET_RUN"
    integrationTest: "NOT_YET_RUN"
    nativeAbiTest: "NOT_YET_RUN"
  limitations:
    - "windows-arm64-not-tested"
  owner: "platform-team"
~~~

Đây là **mẫu hồ sơ**, không phải kết quả một lần kiểm thử thật. Khi thực hiện, ghi thêm commit, artifact/native binary checksum, OS, CPU, dependency graph, logs, thời điểm kiểm tra, test reports, owner và ngày rà soát lại quyền.

Nếu phải sử dụng `ALL-UNNAMED` vì thư viện chưa có module name ổn định, cần ghi rõ phạm vi rộng hơn, lý do và kế hoạch chuyển sang cấu hình hẹp khi khả thi.

## 23. Quy trình ra quyết định về quyền native access

### Bước 1: Chốt JDK đích

Ghi Java feature/update/build, vendor, OS, architecture và runtime/container image. Không chọn cờ dựa trên blog cho một JDK khác.

### Bước 2: Xác định nguồn native

Tìm JNI declarations, `System.loadLibrary`, FFM restricted methods, native-wrapper dependencies và những agent sử dụng instrumentation. Đừng bỏ qua code được tải động.

### Bước 3: Phân loại lỗi

Phân biệt thiếu native access với loader path, native ABI, `--add-opens` và agent attach restrictions.

### Bước 4: Kiểm tra chính sách đúng release

Đọc launcher docs/JEP/release notes của JDK đích. Xác nhận option nào được hỗ trợ và default hiện tại là gì.

### Bước 5: Chọn module cần quyền

Ưu tiên named module nếu kiến trúc cho phép, thay vì `ALL-UNNAMED` cho toàn classpath. Chỉ enable module có lý do kỹ thuật rõ ràng.

### Bước 6: Kiểm bằng deny trong môi trường test

Nếu JDK hỗ trợ `--illegal-native-access=deny`, kết hợp nó với enablement chính xác rồi chạy những luồng JNI/FFM quan trọng.

### Bước 7: Đánh giá native binary

Xác nhận library path, OS/arch/ABI, signature, memory lifetime và crash handling. Không coi flag permission là chứng nhận tương thích binary.

### Bước 8: Đồng bộ mọi launcher

Đảm bảo JVM chạy test, JVM chạy ứng dụng, container worker, batch job và những JVM phụ trợ đều được cấu hình **đúng theo nhu cầu của chúng**. Đừng nhân bản quyền qua mọi process.

### Bước 9: Lưu bằng chứng và nâng cấp có kiểm soát

Ghi support matrix, log, test report, version dependency, quyền đã bật và các ngoại lệ. Khi JDK sau thay đổi default, có đủ dữ liệu để điều chỉnh mà không đoán.

## 24. Những hiểu lầm thường gặp

**“JNI nào cũng bị cấm từ Java 24.”** Không. JEP 472 chuẩn bị cơ chế hạn chế, mặc định phát warning đối với những module chưa có quyền ở JDK 24; hành vi còn phụ thuộc mode và release.

**“Không có warning nghĩa là native code an toàn.”** Không. Native library vẫn có thể lỗi memory, ABI hoặc logic; warning chỉ là một phần của chính sách truy cập.

**“Có `--enable-native-access` thì hết mọi `UnsatisfiedLinkError`.”** Không. Native path, symbol, architecture và dependencies của OS phải được xử lý riêng.

**“`--enable-native-access=ALL-UNNAMED` chỉ cấp quyền cho app.jar.”** Không. Nó áp dụng cho unnamed modules, thường rộng hơn một JAR.

**“Cứ bật `--illegal-native-access=allow` là migration xong.”** Không. Đây là chế độ bỏ warning/cho qua, không phải cấu hình quyền có kiểm soát cho tương lai.

**“`--add-opens` giống `--enable-native-access`.”** Không. Một cờ phục vụ deep reflection/module openness; cờ kia phục vụ restricted native operations.

**“`--enable-preview` đủ để gọi mọi FFM method.”** Không. Preview feature và native permission là hai cơ chế khác nhau; ở JDK 22+ FFM final vẫn có restricted methods.

**“Mọi Java agent đều cần `--enable-native-access`.”** Không. Dynamic agent loading và native JNI/FFM operations là những vấn đề khác nhau.

**“`-XX:+EnableDynamicAgentLoading` cấp quyền JNI.”** Không. Flag này liên quan chính sách dynamic agent loading của JVM.

**“Cấp quyền cho main module luôn đủ.”** Không. Quyền cần đúng module chứa caller restricted operation; caller có thể nằm trong dependency.

**“Cờ đã có ở Gradle daemon nên test và production cũng nhận.”** Không. Mỗi JVM có launcher/config riêng.

**“Lệnh của JDK 24 chắc chắn chạy trên JDK 17.”** Không. Option support thay đổi theo release.

**“Chạy được trên Linux x64 nghĩa là native library cũng chạy trên Windows hoặc ARM.”** Không. Native binary và ABI phụ thuộc OS/architecture.

**“`jnativescan` không tìm thấy nghĩa là ứng dụng không dùng native.”** Không. Static analysis chỉ bao phủ artifact và các kiểu reference được tool nhận diện.

## 25. Checklist trước khi phát hành

- [ ] Đã xác định đúng JDK feature/update/build, vendor, OS và architecture.
- [ ] Đã kiểm release notes và launcher option của JDK đích.
- [ ] Đã phân biệt JNI, FFM, Java agent, JVMTI và JPMS reflection.
- [ ] Đã kiểm kê direct/transitive/native dependencies và agent.
- [ ] Đã xác định class/module thực hiện restricted JNI/FFM operation.
- [ ] Đã dùng `jnativescan` hoặc phương pháp phù hợp nếu JDK hỗ trợ.
- [ ] Đã kiểm những giới hạn của static scan bằng runtime tests.
- [ ] Đã chọn `--enable-native-access` theo named module khi khả thi.
- [ ] Nếu dùng `ALL-UNNAMED`, đã hiểu phạm vi rộng và ghi lý do.
- [ ] Đã xác minh `--illegal-native-access` được JDK mục tiêu hỗ trợ.
- [ ] Đã thử mode `deny` ở môi trường test trên những JDK tương ứng.
- [ ] Đã phân biệt lỗi native permission với `UnsatisfiedLinkError` và crash native.
- [ ] Đã xác nhận thư viện `.so`/`.dll`/`.dylib`, path và ABI phù hợp.
- [ ] Đã kiểm FFM/JNI memory lifetime, concurrency và error handling.
- [ ] Đã kiểm agent attach theo quy định riêng khi liên quan.
- [ ] Đã cấu hình đúng JVM của test, JavaExec, application và container.
- [ ] Đã kiểm định trên các OS/JDK thuộc support matrix.
- [ ] Đã lưu artifact/native checksum, logs, test reports và owner.
- [ ] Đã có kế hoạch cập nhật khi JDK sau đổi default sang chế độ chặt hơn.
- [ ] Không dùng `allow` rộng hoặc workaround không kiểm soát làm tiêu chí hoàn tất.

## 26. Tài liệu tham khảo chính thức

Khi triển khai thực tế, ưu tiên tài liệu đúng với JDK đích:

- **JEP 454 — Foreign Function & Memory API (JDK 22):** https://openjdk.org/jeps/454
- **JEP 472 — Prepare to Restrict the Use of JNI (JDK 24):** https://openjdk.org/jeps/472
- **JEP 451 — Prepare to Disallow the Dynamic Loading of Agents (JDK 21):** https://openjdk.org/jeps/451
- **JDK 25 — Restricted Methods:** https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html
- **JDK 24 — jnativescan command:** https://docs.oracle.com/en/java/javase/24/docs/specs/man/jnativescan.html
- **JDK 26 — java launcher:** https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html

Các link trên là nguồn xác minh phạm vi và ý nghĩa của tùy chọn ở những release được nêu. Khi nâng sang JDK khác, cần đọc tài liệu release đó và không mặc định cờ hay mode cũ còn được hỗ trợ như trước.

## Kết luận

**Quyền native access là quyết định cấu hình theo JDK và theo module Java, không phải một cờ bật chung cho mọi lỗi native.** FFM final API từ JDK 22 vẫn có những restricted methods; JEP 472 ở JDK 24 đưa JNI vào cơ chế cảnh báo/hạn chế thống nhất với FFM, với `--enable-native-access` để cấp quyền và `--illegal-native-access` để quyết định cách xử lý khi thiếu quyền.

Một migration bền vững cần phân biệt JNI, FFM, reflection, Java agent và native library loading; xác định module thực sự cần quyền; ưu tiên cấu hình hẹp; kiểm thử ở mode chặt phù hợp với JDK; và xác minh riêng binary native, ABI, OS và dữ liệu. **Không đánh đồng việc warning biến mất với an toàn hoặc tương thích thực tế.** Khi quyền được ghi rõ, test có phạm vi và artifact có thể truy vết, ứng dụng sẽ dễ nâng sang các JDK mới hơn mà không phụ thuộc vào những chế độ cho phép rộng vốn chỉ mang tính chuyển tiếp.
