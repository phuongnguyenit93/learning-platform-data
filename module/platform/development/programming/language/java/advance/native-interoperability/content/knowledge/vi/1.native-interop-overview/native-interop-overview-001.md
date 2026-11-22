# Tương tác với mã bản địa (native code) là gì và vì sao Java cần đến?

## 1. Native code và native interoperability

**Mã bản địa (native code)** trong ngữ cảnh tương tác với Java là mã đã được biên dịch cho một nền tảng máy cụ thể (hệ điều hành, kiến trúc CPU và quy ước nhị phân), thường từ C, C++ hoặc Rust, và có thể được hệ điều hành nạp để thực thi. Ví dụ: thư viện động `.dll` trên Windows, `.so` trên Linux hoặc `.dylib` trên macOS.

Thông thường, mã nguồn Java được biên dịch thành **bytecode** (`.class`); JVM tải, kiểm tra, thông dịch hoặc JIT-compile bytecode rồi thực thi. **Native interoperability** là khả năng chương trình Java *gọi chức năng hoặc truy cập dữ liệu bên ngoài môi trường Java thông thường*, chẳng hạn hàm trong một thư viện C hiện có hoặc một API đặc thù của hệ điều hành. Chiều ngược lại cũng có thể xảy ra: mã native gọi lại một phương thức Java.

Cần phân biệt ba khái niệm:

- **Java được JIT biên dịch thành mã máy:** vẫn là quá trình JVM tối ưu hóa và thực thi chương trình Java; tự nó không có nghĩa chương trình đang gọi thư viện C bên ngoài.
- **Java gọi thư viện native trong cùng tiến trình:** thường thông qua JNI hoặc Foreign Function & Memory (FFM) API. Mã native chia sẻ không gian địa chỉ và đặc quyền của tiến trình JVM.
- **Java gọi một chương trình bên ngoài:** thông qua `ProcessBuilder`, HTTP, socket hoặc IPC. Chương trình kia có thể viết bằng C/C++ nhưng chạy ở tiến trình khác; đây là cách tích hợp khác với việc nạp thư viện vào JVM.

Ví dụ thực tế: ứng dụng Java muốn điều khiển một thiết bị mà nhà sản xuất chỉ cung cấp SDK C; Java có thể gọi hàm SDK qua một lớp tương tác native, sau đó trả kết quả dưới dạng đối tượng Java.

## 2. Luồng tương tác diễn ra như thế nào?

```text
Mã Java (business logic)
        |
        | lời gọi qua giao diện tương tác
        v
JNI / FFM / thư viện cầu nối
        |
        | chuyển kiểu dữ liệu, địa chỉ, quy ước gọi hàm
        v
Thư viện native (.dll / .so / .dylib)
        |
        v
Hàm C/C++/Rust, API hệ điều hành, thiết bị, thư viện cũ
        |
        +---- giá trị / trạng thái / lỗi ----> trở về Java
```

Các bước cốt lõi:

1. **Có thư viện đúng nền tảng.** Một thư viện cho Linux x86-64 thường không thể nạp trực tiếp trên Windows hay máy ARM. Ngoài kiến trúc CPU, còn phải tương thích ABI (Application Binary Interface), quy ước gọi hàm, định dạng nhị phân và các thư viện phụ thuộc.
2. **Nạp và liên kết chức năng.** Với JNI, Java khai báo phương thức `native` và nạp thư viện bằng `System.loadLibrary(...)` hoặc `System.load(...)`; JVM liên kết phương thức đó với hàm native tương ứng. Với FFM, Java có thể tra cứu ký hiệu hàm và tạo lời gọi qua giao diện FFM.
3. **Chuyển đổi dữ liệu tại biên giới Java/native.** Kiểu nguyên thủy đơn giản có thể ánh xạ trực tiếp; chuỗi, mảng, cấu trúc C, con trỏ hoặc đối tượng Java cần quy tắc chuyển đổi, sao chép, truy cập hay quản lý tham chiếu thích hợp.
4. **Thực thi và trả kết quả.** Hàm native chạy trong cùng tiến trình, có thể gọi dịch vụ hệ điều hành hoặc xử lý dữ liệu rồi trả giá trị về Java. Nếu có callback, mã native phải tuân thủ quy tắc gọi trở lại JVM.

Biên giới này quan trọng vì hai phía khác nhau về **hệ kiểu**, **cách quản lý bộ nhớ**, **mô hình lỗi** và **vòng đời tài nguyên**. Java có garbage collector và exception; C thường dùng con trỏ, cấp phát/giải phóng thủ công và mã lỗi. Một lớp cầu nối đúng phải xử lý các khác biệt ấy.

## 3. Vì sao cần đến native code?

### 3.1. Tái sử dụng thư viện đã tồn tại

Nhiều hệ thống đã có thư viện C/C++ được kiểm chứng qua thời gian: xử lý ảnh/tín hiệu, codec, thuật toán khoa học, engine chuyên ngành hoặc bộ thư viện tích hợp doanh nghiệp. Tạo cầu nối cho phép Java tận dụng chúng mà không phải viết lại toàn bộ, đồng thời giữ phần lớn ứng dụng trong hệ sinh thái Java.

**Ví dụ:** một ứng dụng Java gọi thư viện xử lý ảnh C++ có sẵn để xử lý từng khung hình, rồi hiển thị hoặc lưu kết quả bằng Java.

### 3.2. Truy cập chức năng nền tảng hoặc phần cứng đặc thù

Một số khả năng của hệ điều hành, driver hoặc thiết bị không có API Java tiêu chuẩn tương đương, hoặc nhà cung cấp chỉ phát hành thư viện native. Khi đó cầu nối có thể cung cấp quyền truy cập vào API hệ điều hành, USB/thiết bị công nghiệp, bộ cảm biến, HSM và SDK chuyên dụng.

**Ví dụ:** nhà sản xuất máy quét cung cấp `scanner.dll` và các hàm C; lớp Java wrapper chuyển yêu cầu quét thành lời gọi SDK và chuyển dữ liệu nhận được về Java.

### 3.3. Tích hợp hệ thống cũ và nền tảng hỗn hợp

Trong một tổ chức, ứng dụng Java có thể cần chạy cùng mô-đun native đã triển khai nhiều năm. Một lớp tương tác có giao diện Java rõ ràng giúp kết nối mà không buộc thay đổi mô-đun cũ ngay lập tức.

### 3.4. Tận dụng năng lực tính toán chuyên biệt

Thư viện native có thể tận dụng SIMD, lệnh CPU chuyên dụng, thư viện tính toán hoặc bộ tăng tốc đặc thù. Tuy nhiên **native không đồng nghĩa với nhanh hơn Java**: JVM JIT tối ưu rất tốt; mỗi lần vượt biên giới native có chi phí gọi hàm, chuyển đổi hoặc sao chép dữ liệu. Chỉ nên chọn cách này vì hiệu năng sau khi **đo đạc bằng benchmark thực tế**; thường có lợi khi giao từng khối công việc lớn thay vì gọi hàng triệu hàm native rất nhỏ.

### 3.5. Đáp ứng ràng buộc của bên thứ ba

Một SDK có thể bắt buộc dùng C ABI, yêu cầu gọi hàm qua con trỏ hoặc cung cấp callback native. Trong trường hợp ấy, tương tác native là điều kiện tích hợp, không nhất thiết là một quyết định tối ưu hiệu năng.

**Không phải trường hợp nào cũng cần native:** trước tiên hãy tìm API Java chuẩn, thư viện Java thuần hoặc giao thức mạng tương đương. Ví dụ, nhiều tác vụ mã hóa, nén, I/O, truy cập cơ sở dữ liệu và mạng đã có giải pháp Java phù hợp.

## 4. Các cách tiếp cận phổ biến

| Cách | Ý tưởng chính | Phù hợp khi | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| **JNI (Java Native Interface)** | API chuẩn kết nối phương thức `native` của Java với mã C/C++ (hoặc ngôn ngữ có thể cung cấp ABI tương thích); native cũng có thể thao tác đối tượng và gọi phương thức Java qua JNI. | Cần điều khiển sát JVM, tương tác phức tạp hoặc dùng mã JNI có sẵn; tương thích các JDK lâu đời như Java 17. | Phải duy trì lớp glue code, quản lý tham chiếu/bộ nhớ và xử lý lỗi cẩn thận. |
| **FFM API (Foreign Function & Memory API)** | API chuẩn thuộc `java.lang.foreign`, được hoàn thiện từ **JDK 22**, dùng để gọi hàm native và thao tác vùng nhớ ngoài heap mà nhiều trường hợp không cần viết glue JNI. | Java hiện đại, thư viện xuất hàm theo C ABI, cần quản lý vùng nhớ native có phạm vi rõ ràng. | Yêu cầu JDK phù hợp, hiểu ABI/bộ nhớ; một số thao tác bị kiểm soát quyền native access. |
| **JNA (Java Native Access)** | Thư viện bên thứ ba ánh xạ nhiều hàm C vào giao diện Java mà thường không phải tự viết JNI C. | Tích hợp nhanh thư viện C với API tương đối đơn giản. | Thêm dependency, cần kiểm tra ánh xạ kiểu, khả năng hỗ trợ và hiệu năng thực tế. |
| **Tiến trình ngoài / IPC** | Java giao tiếp với executable/service qua `ProcessBuilder`, pipe, HTTP, gRPC hoặc socket. | Muốn cách ly lỗi, chạy thành phần khác kiến trúc triển khai, hoặc hệ thống đã có dịch vụ riêng. | Chi phí tuần tự hóa, giao tiếp và vận hành giữa tiến trình. |

**Cách chọn:** Ưu tiên giải pháp Java thuần khi đáp ứng yêu cầu. Nếu cần gọi thư viện C trong cùng tiến trình, xem xét FFM với JDK 22+; JNI vẫn phù hợp, đặc biệt với thành phần cần dùng trực tiếp các API JVM hoặc đang có mã JNI. Nếu cần tránh thư viện lỗi làm sập JVM, cân nhắc tiến trình riêng thay vì nạp trực tiếp.

## 5. Ví dụ hoàn chỉnh: Java gọi hàm C qua JNI

Ví dụ tối giản dùng **Java 17+**, không có package, để thấy một lời gọi đi qua biên giới Java/native. Hàm native cộng hai số nguyên; ngoài đời không nên dùng JNI để cộng hai số vì chi phí cầu nối không đáng.

### 5.1. Tệp `NativeMath.java`

```java
public final class NativeMath {
    static {
        System.loadLibrary("nativemath");
    }

    private NativeMath() {
    }

    private static native int add(int a, int b);

    public static void main(String[] args) {
        System.out.println(add(19, 23));
    }
}
```

Ý nghĩa:

- `native` khai báo rằng phần thân phương thức `add` do mã native cung cấp.
- `System.loadLibrary("nativemath")` dùng **tên logic** của thư viện, không kèm đường dẫn, tiền tố `lib` hay phần mở rộng. JVM ánh xạ thành tên tệp phù hợp nền tảng.
- `private static native int add(int a, int b)` nhận/trả về kiểu `int`; trong JNI, kiểu tương ứng ở C là `jint`.
- `main` gọi phương thức Java như bình thường; JVM chuyển quyền thực thi đến hàm C đã liên kết.

### 5.2. Tệp `NativeMath.c`

```c
#include "NativeMath.h"

JNIEXPORT jint JNICALL Java_NativeMath_add(
        JNIEnv *env, jclass clazz, jint a, jint b) {
    (void) env;
    (void) clazz;
    return a + b;
}
```

`NativeMath.h` là header do `javac -h` tạo ra, chứa khai báo JNI và `#include <jni.h>`. Cần dùng header được sinh từ **đúng phiên bản** của lớp Java để tránh sai tên/ký hiệu.

- `JNIEXPORT` và `JNICALL` bảo đảm quy tắc xuất hàm/gọi hàm phù hợp.
- Với phương thức `static`, đối số ẩn thứ nhất là `JNIEnv *` (giao diện gọi JVM trên thread hiện tại), đối số thứ hai là `jclass` (lớp khai báo). Với phương thức instance, đối số thứ hai là `jobject`.
- `Java_NativeMath_add` là tên JNI được ánh xạ từ lớp `NativeMath` và phương thức `add`. Khi có package hoặc overload, tên ký hiệu thay đổi; hãy dựa vào header sinh tự động.
- Hai lệnh `(void)` chỉ để tránh cảnh báo về các đối số không dùng.

### 5.3. Biên dịch và chạy

Chuẩn bị **JDK 17 trở lên** và compiler C phù hợp hệ điều hành/CPU. Đặt `JAVA_HOME` trỏ đến thư mục JDK, tạo hai tệp trên trong cùng thư mục. Chạy trước:

```bash
javac -h . NativeMath.java
```

Lệnh này tạo `NativeMath.class` và `NativeMath.h`. Sau đó biên dịch thư viện ở **đúng hệ điều hành đang chạy JVM**.

**Linux (GCC):**

```bash
gcc -shared -fPIC -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" NativeMath.c -o libnativemath.so
java -Djava.library.path=. NativeMath
```

**macOS (Clang):**

```bash
clang -dynamiclib -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" NativeMath.c -o libnativemath.dylib
java -Djava.library.path=. NativeMath
```

**Windows (MSVC Developer Command Prompt):**

```bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" NativeMath.c /link /OUT:nativemath.dll
java -Djava.library.path=. NativeMath
```

Khi nạp và liên kết thành công, **stdout** ở cả ba nền tảng là:

```text
42
```

`-Djava.library.path=.` cho JVM tìm thư viện native ở thư mục hiện hành trong ví dụ. Trong ứng dụng triển khai thật, nên dùng đường dẫn/cơ chế đóng gói được kiểm soát thay vì tùy tiện dựa vào thư mục làm việc.

**Lưu ý phiên bản mới:** Từ **JDK 24**, JNI có cơ chế cảnh báo đối với thao tác native access bị hạn chế. Với chương trình chạy trên classpath như ví dụ, có thể bật quyền rõ ràng để tránh cảnh báo:

```bash
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. NativeMath
```

Tùy JDK/cấu hình, cảnh báo có thể xuất hiện ở **stderr** dù stdout vẫn là `42`. Với ứng dụng dùng Java module, nên cấp quyền cho **module cụ thể** thay vì tất cả mã classpath.

## 6. Các chi phí, giới hạn và rủi ro

### 6.1. Mất một phần tính di động “write once, run anywhere”

Java bytecode thường chạy trên nhiều nền tảng có JVM tương thích. Thư viện native thì phải được **biên dịch, phân phối và kiểm thử riêng** cho các tổ hợp cần hỗ trợ (OS, kiến trúc, ABI, runtime C và dependency). Thư viện dành cho x86-64 không tự chạy trên ARM64; `.dll` không thay thế trực tiếp cho `.so`.

### 6.2. An toàn bộ nhớ và độ ổn định

Lỗi con trỏ, truy cập ngoài biên, use-after-free hoặc double-free trong mã native có thể **làm crash cả tiến trình JVM**, thậm chí làm hỏng dữ liệu trong bộ nhớ. Garbage collector của Java **không tự quản lý** vùng nhớ do `malloc`/API native cấp phát. JNI có local/global reference với quy tắc vòng đời riêng; FFM dùng `MemorySegment` và `Arena` để mô tả, giới hạn và giải phóng nhiều dạng vùng nhớ native.

Trong JNI: local reference thông thường hết hiệu lực khi lời gọi native trở về; global reference phải được xóa khi không còn dùng. Chuỗi/mảng nhận từ JNI phải được giải phóng hoặc trả quyền truy cập bằng API tương ứng theo hợp đồng của từng hàm. Không nên lưu `JNIEnv *` để dùng ở thread khác: nó gắn với thread đang gọi; thread do native tự tạo phải được gắn vào JVM theo đúng JNI protocol nếu muốn gọi Java.

### 6.3. Độ phức tạp về dữ liệu và lỗi

- Java `String` không tương đương trực tiếp với `char *`; phải định nghĩa encoding, độ dài, sở hữu và thời điểm giải phóng.
- Native struct có alignment, padding và byte order; chuyển trực tiếp sang Java mà không kiểm tra layout dễ gây sai dữ liệu.
- Ngoại lệ Java không tự biến thành mã lỗi C, và mã lỗi C không tự biến thành exception Java. Lớp cầu nối phải kiểm tra và ánh xạ lỗi có chủ đích.
- Khi native gọi vào JVM qua JNI, phải xử lý exception đang chờ (`ExceptionCheck`/quy tắc JNI phù hợp) trước khi tiếp tục gọi API không cho phép trong trạng thái đó.

### 6.4. Hiệu năng phải được đo ở mức toàn luồng

Không chỉ so sánh tốc độ một hàm C với một hàm Java. Phải tính cả chi phí vượt biên giới, cấp phát, sao chép mảng, chuyển encoding, khóa luồng và khả năng tối ưu của JIT. Ví dụ, gọi một hàm native để xử lý **một triệu phần tử một lần** có thể hợp lý hơn gọi native **một triệu lần, mỗi lần một phần tử**. Dùng benchmark phù hợp, warm-up JVM và đo trên phần cứng/khối lượng dữ liệu thực.

### 6.5. Bề mặt bảo mật và vận hành

Thư viện native được nạp chạy với quyền của tiến trình ứng dụng; JVM không thể bảo đảm an toàn bộ nhớ cho mã C/C++ tùy ý. Cần kiểm soát **nguồn gốc và phiên bản binary**, thư viện phụ thuộc, đường dẫn nạp, cập nhật bảo mật và quyền hệ điều hành. Từ JDK 24, cấu hình native access cần được đưa vào quy trình triển khai khi sử dụng các thao tác JNI/FFM bị hạn chế.

## 7. Cách thiết kế lớp tương tác dễ bảo trì

1. **Chỉ đặt phần thật sự cần thiết ở native.** Giữ quy tắc nghiệp vụ, kiểm tra đầu vào và điều phối ở Java; tạo API wrapper hẹp, có tên và hợp đồng rõ ràng.
2. **Xác định quyền sở hữu tài nguyên.** Ai cấp phát, ai giải phóng, ở thread nào, khi nào? Với native handle, dùng `AutoCloseable`/`try-with-resources` ở lớp Java nếu thích hợp; với FFM quản lý vòng đời bằng `Arena` phù hợp.
3. **Thiết kế dữ liệu qua biên giới.** Chọn kiểu và encoding có quy ước rõ; tránh trả con trỏ trần cho phần Java không biết vòng đời. Kiểm tra `null`, kích thước, offset, overflow và các trường hợp lỗi trước khi dùng native.
4. **Thiết lập hợp đồng lỗi.** Đổi mã lỗi native thành exception Java có thông tin chẩn đoán; không để lỗi native bị bỏ qua hoặc dùng tài nguyên sau khi đã giải phóng.
5. **Kiểm thử theo ma trận nền tảng.** Chạy test trên từng OS/CPU/JDK cần hỗ trợ; kiểm thử dữ liệu rỗng, ký tự Unicode, dung lượng lớn, lỗi thiết bị, gọi đồng thời, nạp thư viện và giải phóng tài nguyên.
6. **Theo dõi và đóng gói đúng cách.** Đóng gói binary theo nền tảng, xác minh đường dẫn tìm thư viện và phụ thuộc native trong CI/CD; khi sự cố nặng, thu thập log JVM và `hs_err_pid...log` nếu JVM tạo ra.
7. **Tách biệt rủi ro khi cần.** Với SDK native không đáng tin hoặc thường crash, dùng tiến trình riêng và giao thức IPC để một sự cố không trực tiếp làm sập JVM chính.

## 8. Hiểu đúng qua các câu hỏi thường gặp

**“Native code có luôn nhanh hơn Java không?”** Không. Java có JIT, tối ưu runtime và thư viện chuẩn hiệu quả. Tương tác native chỉ đáng giá về hiệu năng khi lợi ích xử lý vượt chi phí cầu nối và được benchmark chứng minh.

**“Hễ ứng dụng Java dùng thư viện C thì bắt buộc phải viết JNI?”** Không. Tùy JDK, ABI và mục tiêu có thể dùng FFM, thư viện như JNA, hoặc gọi tiến trình/dịch vụ bên ngoài. JNI là một lựa chọn chuẩn, đặc biệt hữu ích khi cần làm việc sâu với đối tượng và vòng đời JVM.

**“Garbage collector có tự dọn mọi bộ nhớ native không?”** Không. GC quản lý đối tượng Java; vùng nhớ/tài nguyên native cần cơ chế sở hữu và giải phóng phù hợp. Wrapper Java có thể giúp quản lý nhưng không thay thế việc giải phóng đúng ở phía native.

**“Java giao tiếp native có còn chạy được trên mọi hệ điều hành không?”** Phần Java có thể di động, nhưng binary native phải có phiên bản tương thích cho mỗi môi trường đích; thêm kiểm thử/đóng gói là bắt buộc.

**“Java chạy mã native qua JNI có ở tiến trình khác không?”** Thông thường không: thư viện được nạp vào **cùng tiến trình** với JVM. Muốn cách ly bằng tiến trình, cần kiến trúc như `ProcessBuilder` hoặc IPC.

## 9. Checklist trước khi quyết định dùng native interoperability

- **Nhu cầu thật:** Có API Java thuần/thư viện Java đủ tốt chưa? Có bắt buộc dùng SDK native hoặc khả năng hệ điều hành không?
- **Giao diện:** Cần gọi hàm C đơn giản, truy cập native memory, callback hay thao tác trực tiếp đối tượng Java? Từ đó chọn FFM, JNI hoặc giải pháp thích hợp.
- **Triển khai:** Có binary đúng OS/CPU/ABI, version, thư viện phụ thuộc và cách nạp an toàn không?
- **Vận hành:** Ai sở hữu bộ nhớ/handle, xử lý lỗi/thread/callback thế nào, cách đo hiệu năng và chẩn đoán crash ra sao?
- **Rủi ro:** Nếu thư viện native lỗi, có chấp nhận toàn bộ JVM dừng không, hay nên tách thành service/tiến trình riêng?

### Tài liệu tham khảo chính thức

- [Oracle — Java Native Interface Specification (Java 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): mô hình JNI, liên kết phương thức, kiểu và vòng đời reference.
- [Oracle — Foreign Function and Memory API (JDK 22)](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): `java.lang.foreign`, gọi hàm native và quản lý bộ nhớ ngoài heap.
- [OpenJDK — JEP 472](https://openjdk.org/jeps/472): quyền truy cập native và cảnh báo JNI từ JDK 24.