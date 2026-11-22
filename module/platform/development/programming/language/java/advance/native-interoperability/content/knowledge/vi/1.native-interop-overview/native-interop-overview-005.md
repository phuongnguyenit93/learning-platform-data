# Phân biệt native interoperability với việc biên dịch Java thành mã máy hoặc Native Image

## 1. Ba câu hỏi cần tách biệt

Trong Java, chữ **native** có thể chỉ ba việc khác nhau:

1. **Native interoperability (tương tác với mã bản địa):** chương trình Java **gọi hoặc được gọi bởi mã bên ngoài Java runtime**, thường là thư viện C/C++ hay API của hệ điều hành. Câu hỏi chính: *Java giao tiếp với mã ngoại như thế nào?*
2. **Biên dịch mã Java thành mã máy bằng JIT:** JVM nhận bytecode rồi có thể biên dịch các đoạn thường chạy thành lệnh máy ngay **trong lúc chương trình hoạt động**. Câu hỏi chính: *JVM thực thi và tối ưu mã Java như thế nào?*
3. **Biên dịch ahead-of-time (AOT) thành Native Image:** công cụ như **GraalVM Native Image** tạo tệp thực thi mã máy **trước khi triển khai**, thường chạy không cần khởi động một JVM HotSpot riêng. Câu hỏi chính: *Ứng dụng được đóng gói và chạy bằng loại tệp nào?*

**Kết luận cốt lõi:** “Gọi thư viện native” là chuyện **kết nối giữa hai thế giới mã**; “Java được biên dịch thành native code” là chuyện **cách Java được thực thi hoặc đóng gói**. Chúng độc lập về mặt khái niệm và có thể cùng xuất hiện trong một ứng dụng.

## 2. Java thông thường thực thi ra sao?

Với chương trình Java thông thường:

```text
Tệp .java
   │ javac (biên dịch lúc xây dựng)
   ▼
Tệp .class / bytecode
   │ java (khởi động JVM)
   ▼
JVM: nạp lớp, xác minh bytecode, thông dịch và/hoặc JIT
   │
   ▼
Lệnh máy được CPU thực thi
```

- `javac` thông thường tạo **bytecode** (`.class`), **không tạo trực tiếp** tệp thực thi độc lập như `.exe`.
- **JIT (Just-In-Time)** là một khả năng tối ưu của JVM: các phương thức “nóng” có thể được biên dịch thành mã máy để chạy nhanh hơn. Một chương trình nhỏ có thể kết thúc trước khi phương thức được JIT; không phải mọi dòng Java đều nhất thiết được JIT.
- Việc CPU cuối cùng chạy lệnh máy **không có nghĩa** ứng dụng đã gọi thư viện C/C++ do người lập trình cung cấp. JVM vốn phải thực thi trên CPU, kể cả khi ứng dụng chỉ dùng Java thuần.
- JIT cũng không đồng nghĩa với Native Image: mã máy JIT phát sinh **trong tiến trình JVM khi chạy**, còn mã máy AOT được tạo **trước khi ứng dụng chạy**.

Ví dụ, `Math.addExact(7, 5)` là lời gọi API Java; dù JVM có tối ưu bằng JIT, nó **không phải** ví dụ về JNI hoặc một lời gọi FFI do ứng dụng chủ động khai báo.

## 3. Native interoperability: vượt qua ranh giới Java ↔ mã bản địa

Ví dụ ứng dụng Java phải gọi thư viện C có sẵn để xử lý thiết bị, sử dụng SDK chỉ cung cấp API native, hoặc tích hợp một thuật toán C/C++ vốn đang được duy trì. Khi đó cần một **cơ chế tương tác** để thống nhất ký hiệu hàm, kiểu dữ liệu, con trỏ, bộ nhớ, vòng đời tài nguyên và ABI (Application Binary Interface).

Các hướng thường gặp:

- **JNI (Java Native Interface):** giao diện chuẩn lâu đời của JDK; Java khai báo phương thức `native`, thư viện C/C++ xuất hàm JNI phù hợp; có thể gọi theo cả chiều Java → native và native → Java. JNI yêu cầu xử lý cẩn thận con trỏ, tham chiếu JNI, thread và exception.
- **Foreign Function & Memory API (FFM):** API trong `java.lang.foreign`, hoàn thiện thành tính năng chính thức từ **JDK 22 (JEP 454)**. Cho phép truy cập vùng nhớ ngoài heap và gọi hàm ngoại qua mô tả hàm/kiểu, không cần viết một lớp JNI C cho mọi lời gọi. Việc cấp quyền truy cập native và khả năng hỗ trợ phụ thuộc phiên bản JDK và môi trường chạy.
- **JNA/JNR-FFI và các wrapper:** thư viện bên thứ ba hỗ trợ gọi native theo mức trừu tượng khác nhau; cần xem phiên bản và khả năng triển khai thực tế.
- **IPC hoặc gọi dịch vụ qua mạng:** Java cũng có thể giao tiếp với một chương trình native ở *tiến trình khác* bằng socket, HTTP hay pipe. Đây là tích hợp hệ thống nhưng không phải lời gọi hàm native trong cùng tiến trình kiểu JNI/FFM.

Chỉ đánh dấu một phương thức `native` **không biên dịch toàn bộ Java sang mã máy**. Nó khai báo rằng **phần thân của phương thức được cung cấp từ môi trường native**. Phần Java còn lại có thể tiếp tục chạy dưới JVM thông thường và được JIT như trước.

### Ví dụ JNI tối thiểu, có thể xây dựng trên JDK 17+

Tạo tệp `NativeMath.java`:

```java
public final class NativeMath {
    static {
        System.loadLibrary("nativemath");
    }

    private static native int sum(int a, int b);

    public static void main(String[] args) {
        System.out.println("JNI: " + sum(7, 5));
    }
}
```

Tạo header JNI bằng JDK:

```bash
javac -h . NativeMath.java
```

Lệnh trên biên dịch lớp Java và tạo `NativeMath.h`. Tạo `NativeMath.c` cùng thư mục:

```c
#include <jni.h>
#include "NativeMath.h"

JNIEXPORT jint JNICALL Java_NativeMath_sum(
        JNIEnv *env, jclass clazz, jint a, jint b) {
    (void) env;
    (void) clazz;
    return a + b;
}
```

Trên **Linux**, khi `JAVA_HOME` trỏ đến thư mục JDK và có GCC:

```bash
gcc -shared -fPIC \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  -o libnativemath.so NativeMath.c
java -Djava.library.path=. NativeMath
```

Trên **macOS** có Clang, thay lệnh biên dịch thư viện bằng:

```bash
clang -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  -o libnativemath.dylib NativeMath.c
java -Djava.library.path=. NativeMath
```

Trên **Windows**, từ *Developer Command Prompt* đã cấu hình MSVC và `JAVA_HOME`:

```bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" NativeMath.c /Fe:nativemath.dll
java -Djava.library.path=. NativeMath
```

Khi biên dịch đúng và tải được thư viện, **stdout** là:

```text
JNI: 12
```

Giải thích chính xác điều vừa xảy ra:

1. `javac` biên dịch `NativeMath.java` thành `NativeMath.class` và sinh header khai báo chữ ký JNI tương ứng.
2. Trình biên dịch C tạo **thư viện dùng chung của nền tảng**: `libnativemath.so`, `libnativemath.dylib` hoặc `nativemath.dll`. Đây là phần mã máy của hàm C.
3. JVM chạy bytecode Java, `System.loadLibrary("nativemath")` nạp thư viện theo quy tắc đặt tên của OS, còn `-Djava.library.path=.` bổ sung thư mục tìm kiếm.
4. Lời gọi `sum(7, 5)` vượt biên Java/native rồi trả kết quả `jint` cho Java. Ứng dụng vẫn đang chạy **trong JVM**, dù một hàm được cài bằng C.

Nếu thiếu thư viện, sai kiến trúc CPU, sai tên symbol hoặc đường dẫn, có thể gặp `UnsatisfiedLinkError`. Ví dụ này không cần GraalVM Native Image, và chỉ phù hợp với ABI/hệ điều hành nơi thư viện đã được biên dịch.

## 4. Native Image: biên dịch ứng dụng Java trước khi chạy

GraalVM Native Image đọc bytecode Java cùng metadata cần thiết, phân tích thành phần có thể được gọi, rồi **AOT biên dịch và liên kết** thành tệp thực thi cho một hệ điều hành/kiến trúc cụ thể. Binary thường mang theo các phần runtime cần thiết (như quản lý bộ nhớ/GC và luồng), dù **không cần tiến trình JVM HotSpot riêng** để chạy ứng dụng đã biên dịch.

Ví dụ thuần Java, tệp `SimpleApp.java`:

```java
public final class SimpleApp {
    public static void main(String[] args) {
        int total = 7 + 5;
        System.out.println("Tổng: " + total);
    }
}
```

Chạy kiểu JVM:

```bash
javac SimpleApp.java
java SimpleApp
```

Khi máy đã cài bản phân phối có lệnh `native-image` và bộ công cụ biên dịch cần thiết, tạo bản AOT từ **chính bytecode đó**:

```bash
native-image SimpleApp simple-app
./simple-app
```

Lệnh chạy cuối minh họa Linux/macOS; trên Windows chạy `simple-app.exe`. Cả hai cách đều in:

```text
Tổng: 12
```

`SimpleApp` **không hề gọi JNI, FFM hay một thư viện C tùy chỉnh**. Bản native executable chỉ thay **cách triển khai/chạy** ứng dụng Java. Ngược lại, một chương trình JVM gọi JNI như `NativeMath` vẫn dùng native interoperability dù không được AOT biên dịch.

Lưu ý: Native Image sử dụng phân tích tĩnh theo nguyên tắc thường gọi là **closed-world assumption**. Reflection, dynamic proxies, resource loading, serialization hoặc JNI truy cập phần tử theo cách động có thể cần metadata/cấu hình phù hợp. Đóng gói thành binary không đảm bảo mọi ứng dụng dùng cơ chế nạp động sẽ chạy giống JVM mà không chỉnh cấu hình. Không nên đồng nhất “standalone executable” với “không cần bất kỳ thư viện hệ điều hành nào”: phụ thuộc runtime native còn tùy bản dựng và cách liên kết.

## 5. Bảng so sánh theo đúng tiêu chí

| Tiêu chí | Native interoperability (JNI/FFM) | JVM với JIT | AOT / GraalVM Native Image |
| --- | --- | --- | --- |
| Mục tiêu | Gọi/nhận lời gọi từ mã bên ngoài Java, trao đổi dữ liệu qua ABI | Tối ưu thực thi bytecode Java khi chương trình chạy | Biến ứng dụng Java thành binary trước khi chạy |
| Ranh giới kỹ thuật | Java ↔ thư viện/hàm/native memory | Bytecode ↔ mã máy do JVM quản lý | Bytecode/build-time ↔ executable mã máy |
| Thời điểm chủ yếu | Khi ứng dụng thực thi lời gọi ngoại | Trong lúc chạy, tùy mức độ “nóng” | Khi xây dựng bản phát hành |
| Đầu vào/đầu ra điển hình | Java + thư viện `.so`/`.dylib`/`.dll` hoặc API native | `.class`/JAR chạy với `java`, JIT phát mã máy nội bộ | `.class`/JAR → tệp thực thi dành cho OS/CPU |
| Có bắt buộc viết C/C++? | JNI wrapper thường có; FFM có thể gọi thư viện có sẵn mà không viết wrapper JNI | Không | Không |
| Có cần JVM HotSpot để chạy? | Thường có trong ứng dụng Java thông thường; có thể kết hợp Native Image | Có | Không cần khởi động HotSpot riêng cho binary Native Image |
| Tính di động | Code Java có thể portable, thư viện native phải phù hợp OS/CPU/ABI | Bytecode có thể chuyển môi trường nếu có JVM phù hợp | Phải xây dựng/phân phối binary phù hợp nền tảng |
| Vấn đề đặc trưng | Linkage, ABI, con trỏ, crash native, quản lý bộ nhớ | Warm-up, tối ưu/khử tối ưu JIT, runtime JVM | Thời gian build, kích thước, metadata cho tính năng động, khác biệt môi trường |
| Hiểu đúng | **Cơ chế tích hợp mã** | **Cơ chế thực thi/tối ưu** | **Cơ chế biên dịch/đóng gói** |

## 6. Chúng hoàn toàn có thể kết hợp

Có bốn tình huống hợp lệ:

| Cách chạy ứng dụng | Không gọi thư viện native tùy chỉnh | Có gọi thư viện native |
| --- | --- | --- |
| **Chạy trên JVM** | Ứng dụng Java thuần; JVM có thể JIT | Ứng dụng Java sử dụng JNI/FFM; phần Java vẫn có thể JIT |
| **Chạy bằng Native Image** | Binary AOT của ứng dụng Java thuần | Binary AOT vẫn tích hợp thư viện native qua cơ chế được Native Image hỗ trợ và cấu hình phù hợp |

Ví dụ thực tế: một dịch vụ Java gọi thư viện xử lý ảnh C qua JNI là **native interoperability**; nếu dịch vụ đó còn được biên dịch bằng GraalVM Native Image, nó đồng thời dùng **interop và AOT**. Không có mâu thuẫn: hai lựa chọn giải quyết hai vấn đề khác nhau.

GraalVM Native Image có hỗ trợ JNI, nhưng các lớp/phương thức/trường được truy cập động qua JNI có thể cần khai báo ở **build time**. Với FFM và các tính năng native khác, phải kiểm tra khả năng hỗ trợ theo **phiên bản GraalVM/JDK đang sử dụng**.

## 7. Hệ quả khi chọn giải pháp

**Mục tiêu tích hợp:** Nếu cần gọi SDK hệ điều hành hoặc thư viện C/C++ đã tồn tại, đánh giá JNI, FFM hoặc wrapper phù hợp. Chọn Native Image một mình **không tự sinh ra binding** đến mọi hàm C và cũng không giải quyết khác biệt ABI.

**Mục tiêu triển khai:** Nếu cần thời gian khởi động ngắn, giảm overhead của một số workload hoặc phân phối executable mà không yêu cầu người dùng cài JVM HotSpot riêng, đánh giá Native Image. Nó có thể đổi lại thời gian build dài hơn, yêu cầu metadata và một số giới hạn đối với hành vi động; kết quả hiệu năng phụ thuộc ứng dụng, không thể kết luận AOT luôn nhanh hơn JVM JIT.

**Mục tiêu hiệu năng:** JNI/FFM có chi phí chuyển qua biên gọi và chi phí chuyển đổi dữ liệu; lời gọi rất nhỏ lặp dày đặc có thể không có lợi. JVM JIT có warm-up nhưng có thể tối ưu tốt một workload chạy dài. Native Image thường có lợi thế về khởi động trong nhiều tình huống, còn throughput/memory phải đo trên tải thật và cấu hình thực tế.

**Mục tiêu an toàn:** Một lỗi native như truy cập con trỏ sai hoặc ghi vượt vùng nhớ có thể làm hỏng tiến trình hoặc gây crash; GC của Java không tự quản lý tài nguyên cấp phát ở C. Native Image vẫn có quản lý bộ nhớ cho đối tượng Java, nên “mã máy” không đồng nghĩa “tất cả bộ nhớ đều quản lý thủ công”.

**Mục tiêu portability:** JAR Java thuần tương đối độc lập với OS/CPU khi có JDK/JRE thích hợp. Native library và executable AOT thường phải được xây dựng đúng nền tảng, kiến trúc CPU và các dependency/ABI liên quan.

## 8. Các nhầm lẫn phổ biến và cách sửa

1. **“Có từ khóa `native` thì Java đã AOT thành executable.”** Sai. `native` chỉ khai báo thân phương thức nằm ngoài Java; `javac` vẫn tạo bytecode cho lớp Java.
2. **“JIT tạo mã máy nên đó là native interoperability.”** Sai. JIT tạo mã máy cho **mã Java**; không ngụ ý có lời gọi đến thư viện C tùy chỉnh.
3. **“Native Image luôn cần JNI.”** Sai. Một ứng dụng Java thuần có thể được AOT mà không khai báo bất kỳ hàm JNI nào.
4. **“Native Image không thể gọi C/C++.”** Sai. Có thể sử dụng cơ chế interoperability được hỗ trợ, chẳng hạn JNI, cùng cấu hình build tương ứng.
5. **“Tạo executable là hết phụ thuộc hệ điều hành.”** Sai. Binary có target OS/CPU, có thể còn phụ thuộc shared libraries và runtime cấp hệ điều hành.
6. **“Native Image loại bỏ GC và đảm bảo nhanh hơn.”** Sai. Native Image vẫn có runtime hỗ trợ GC; hiệu năng phụ thuộc startup, thời gian chạy, bộ nhớ, build options và workload.
7. **“Gọi C từ Java an toàn như gọi Java thuần.”** Sai. Sai ABI, vòng đời bộ nhớ hoặc thao tác con trỏ có thể gây lỗi nghiêm trọng ngoài các bảo đảm kiểu thông thường của Java.

## 9. Tự kiểm tra bằng ba câu hỏi

Khi gặp một công nghệ có chữ “native”, hãy hỏi:

- **Có lời gọi vượt ranh giới Java ↔ external code/data không?** Nếu có, đang nói về **interop** (JNI, FFM, FFI hoặc IPC, tùy cách kết nối).
- **Ai biên dịch mã Java thành lệnh máy và vào lúc nào?** JVM tối ưu lúc chạy là **JIT**; công cụ biên dịch trước khi chạy là **AOT**.
- **Tệp nào được triển khai và runtime nào khởi động nó?** `.class`/JAR với `java` là mô hình JVM; executable sinh bởi `native-image` là mô hình AOT Native Image.

Giải thích được ba câu này là có thể phân biệt đúng ngay cả khi một sản phẩm dùng cả JNI, JIT và Native Image ở các giai đoạn khác nhau.

## Tài liệu tham khảo chính thức

- [Java Native Interface Specification (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html)
- [Foreign Function & Memory API (JDK 22)](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html) và [JEP 454](https://openjdk.org/jeps/454)
- [GraalVM Native Image](https://www.graalvm.org/latest/reference-manual/native-image/)
- [GraalVM: JNI in Native Image](https://www.graalvm.org/reference-manual/native-image/JNI/)