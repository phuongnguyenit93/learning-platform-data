# Các hạn chế đối với JNI từ JDK 24 và ảnh hưởng khi nâng JDK

## 1. Bối cảnh và mục tiêu

**JNI (Java Native Interface)** cho phép mã Java gọi hàm trong thư viện native (thường viết bằng C/C++) thông qua phương thức `native`, đồng thời cho phép mã native gọi trở lại JVM. Thư viện có thể là `.so` trên Linux, `.dylib` trên macOS hoặc `.dll` trên Windows. Khả năng này cần thiết cho nhiều driver, thư viện nén, xử lý ảnh, cơ sở dữ liệu và phần mềm tích hợp hệ điều hành, nhưng mã native có thể gây crash JVM, truy cập bộ nhớ sai hoặc phá vỡ các bảo đảm an toàn của Java.

**JEP 472 – Prepare to Restrict the Use of JNI**, được đưa vào **JDK 24**, mở rộng cơ chế *native access restrictions* vốn đã áp dụng với Foreign Function & Memory (FFM) API sang JNI. Từ JDK 24, JVM kiểm tra quyền native access khi Java **nạp thư viện native** và khi **liên kết (bind) phương thức `native`**. Mặc định ở JDK 24, 25 và 26, thao tác chưa được cấp quyền vẫn chạy nhưng phát cảnh báo. Một phiên bản JDK tương lai sẽ đổi mặc định thành từ chối; không nên gán trước thay đổi ấy cho một phiên bản cụ thể khi chưa có công bố chính thức.

Mục tiêu của bài: nhận diện đúng hai điểm kiểm soát, phân biệt cảnh báo với lỗi thực sự, cấp quyền cho đúng module và chuẩn bị nâng JDK mà không phụ thuộc vào cấu hình tạm thời.

> **Điểm cần nhớ:** JNI vẫn là giao diện tiêu chuẩn, không bị JEP 472 xóa bỏ hay đánh dấu deprecated. JEP này kiểm soát **quyền thực hiện thao tác native ở phía Java/JVM**, không vô hiệu hóa các hàm JNI bên trong mã C/C++ đã chạy.

## 2. Những thao tác JNI nào bị hạn chế?

| Thao tác phía Java | Khi nào kiểm tra? | Module cần có native access |
| --- | --- | --- |
| `System.load(String absolutePath)` | Khi gọi phương thức nạp thư viện | Module chứa mã **gọi load** |
| `System.loadLibrary(String libraryName)` | Khi gọi phương thức nạp thư viện | Module chứa mã **gọi loadLibrary** |
| `Runtime.getRuntime().load(...)` / `loadLibrary(...)` | Khi gọi phương thức nạp thư viện tương ứng | Module chứa mã **gọi load** |
| Khai báo `native` và gọi phương thức lần đầu | Khi JVM liên kết phương thức Java với hàm native (binding) | Module **khai báo phương thức `native`** |

`System.load(...)` và `System.loadLibrary(...)` là cách gọi tiện lợi tới `Runtime`; bốn phương thức nạp thư viện đều thuộc nhóm restricted. Với `load`, đối số là đường dẫn tuyệt đối; với `loadLibrary`, đối số là tên thư viện logic, ví dụ `nativemath` để JVM tìm `libnativemath.so` trên Linux. Cả hai vẫn phải tìm được thư viện tương thích.

**Loading** nguy hiểm vì mã khởi tạo của hệ điều hành hoặc hàm `JNI_OnLoad` có thể chạy ngay khi thư viện được nạp. **Binding** nguy hiểm vì JVM không thể chứng minh chữ ký và hành vi của hàm native thực sự phù hợp với phía Java. Khi một phương thức `native` chưa từng được gọi, chỉ riêng việc khai báo hoặc tải class không nhất thiết gây cảnh báo binding: kiểm tra xảy ra lúc phương thức được liên kết, thường ở lời gọi đầu tiên.

Một module chỉ **gọi** phương thức `native` do **module khác khai báo** không tự động cần quyền native access cho lời gọi ấy. Nhưng module nào thực hiện `System.loadLibrary` vẫn cần quyền riêng của nó. Ví dụ, nếu `com.acme.loader` nạp thư viện và `com.acme.codec` khai báo `native int decode(...)`, hãy cấp quyền cho **cả hai** module. Nếu một module làm cả hai việc thì chỉ cấp cho module đó.

Các hàm JNI được gọi từ mã C/C++ không bị JEP 472 cấm riêng từng hàm. Tuy nhiên, cấp quyền native access không làm mã C/C++ trở nên memory-safe, không cấp quyền truy cập file/hệ điều hành và không thay thế kiểm tra tương thích ABI/kiến trúc.

## 3. Khi nâng JDK, hành vi thay đổi thế nào?

| Mốc | Ý nghĩa đối với JNI |
| --- | --- |
| JDK 17/21 và các bản trước JDK 24 | Chưa áp dụng cơ chế cảnh báo JNI của JEP 472; lỗi thư viện, ABI và binding truyền thống vẫn tồn tại. |
| JDK 22–23 | FFM API đã có hạn chế native access; JNI chưa có mở rộng tương đương theo JEP 472. |
| **JDK 24** | JEP 472 có hiệu lực: cảnh báo mặc định khi loading/binding JNI chưa được cấp quyền; cách xử lý JNI và FFM được thống nhất. |
| JDK 25–26 | Tài liệu migration tiếp tục mô tả `warn` là mặc định và hỗ trợ các tùy chọn native access. |
| JDK tương lai | Kế hoạch là `deny` trở thành mặc định và việc dùng native trái quyền dẫn đến ngoại lệ; theo dõi release notes trước mỗi đợt nâng. |

Một ứng dụng có thể **biên dịch và chạy đúng trên JDK 21**, rồi **vẫn chạy nhưng sinh `WARNING` ở stderr trên JDK 24+**. Nếu bật chế độ kiểm tra nghiêm ngặt `deny` mà chưa cấp quyền, ứng dụng có thể lỗi ngay ở bước tải thư viện hoặc lần đầu bind phương thức. Vì cảnh báo thường chỉ xuất hiện **một lần cho mỗi module**, log sạch sau lần gọi đầu tiên không chứng minh rằng tất cả đường đi JNI đã được kiểm thử.

### Hai tùy chọn JVM cần phân biệt

- `--enable-native-access=...`: **cấp quyền** cho module được chỉ định, là cấu hình lâu dài cần dùng.
- `--illegal-native-access=...`: chọn **cách JVM phản ứng khi module chưa có quyền**. Đây là công cụ kiểm thử/chuyển tiếp, không thay thế việc cấp quyền.

| `--illegal-native-access` | Hành vi với thao tác chưa được cấp quyền | Khi sử dụng |
| --- | --- | --- |
| `allow` | Cho chạy, không cảnh báo | Chỉ là giải pháp chuyển tiếp ngắn hạn nếu thực sự cần; dễ che giấu phụ thuộc native. |
| `warn` | Cho chạy và cảnh báo ở lần vi phạm đầu của mỗi module | Mặc định trong JDK 24–26; giúp phát hiện khi chạy thực tế. |
| `deny` | Ném `IllegalCallerException` tại thao tác trái quyền | **Nên dùng trong CI/staging** cùng với các quyền đã xác định để kiểm chứng khả năng nâng JDK tương lai. |

Cảnh báo có thể đề cập tên module, class, phương thức và gợi ý `--enable-native-access=...`. Nó được gửi đến **stderr**; nội dung và vị trí file trong thông báo thay đổi theo JVM, nên không viết test so khớp cứng toàn bộ cảnh báo.

## 4. Cấp native access đúng phạm vi

### 4.1. Ứng dụng chạy trên classpath (unnamed modules)

Nếu mã dùng JNI đang ở classpath, có thể cấp quyền cho các unnamed module:

```bash
java --enable-native-access=ALL-UNNAMED -cp app.jar com.acme.Main
```

Để thử trước hành vi chặn nghiêm ngặt:

```bash
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp app.jar com.acme.Main
```

`ALL-UNNAMED` cho phép **mọi mã trên classpath** thực hiện restricted JNI/FFM operations; vì phạm vi rộng, chỉ dùng khi chưa thể tách các thư viện cần native sang module path. `ALL-UNNAMED` **không** tự cấp quyền cho các named module ở module path.

### 4.2. Ứng dụng dùng Java Platform Module System (JPMS)

Nếu JNI nằm trong module có tên `com.acme.nativebridge`:

```bash
java --enable-native-access=com.acme.nativebridge --illegal-native-access=deny --module-path mods -m com.acme.app/com.acme.app.Main
```

Trong thực tế, thêm tất cả module thực sự **gọi hàm load** hoặc **khai báo phương thức `native`** vào danh sách phân tách bằng dấu phẩy:

```bash
java --enable-native-access=com.acme.loader,com.acme.nativebridge --illegal-native-access=deny --module-path mods -m com.acme.app/com.acme.app.Main
```

Tên module phải đúng **tên tại runtime**, không nhất thiết trùng package, tên dự án hay file JAR. Với automatic module, có thể kiểm tra tên đã được suy ra bằng `jar --describe-module --file path/to/library.jar` hoặc quan sát cảnh báo thực tế.

### 4.3. Những nơi khác có thể truyền cấu hình

- Script khởi động, cấu hình container, systemd/service, launcher của application server và quy trình kiểm thử đều cần truyền tùy chọn cho **đúng tiến trình `java`**.
- Có thể dùng biến môi trường `JDK_JAVA_OPTIONS` hoặc file đối số của launcher như `java @java-options.txt`.
- Với **executable JAR** chạy bằng `java -jar`, manifest của JAR ứng dụng có thể ghi `Enable-Native-Access: ALL-UNNAMED`. Giá trị manifest được hỗ trợ là **`ALL-UNNAMED`**, không phải danh sách named modules; đừng trông đợi manifest của một dependency JAR tự cấp quyền cho cả ứng dụng.
- Với runtime image tùy chỉnh, có thể dùng tùy chọn `--add-options` của `jlink` để đóng gói JVM option phù hợp. Mọi cách triển khai đều phải được kiểm thử trên image và lệnh khởi động thực tế.

**Không dùng `--add-opens` hoặc `--add-exports` để xử lý cảnh báo JEP 472**: các cờ ấy phục vụ encapsulation/module access, khác với native access. Cũng không coi `-Djava.library.path=...` là cách cấp quyền JNI: thuộc tính này chỉ hỗ trợ định vị thư viện.

## 5. Ví dụ JNI có thể tự biên dịch và kiểm chứng

Ví dụ chạy trên **Linux** với JDK 24+ và trình biên dịch C `gcc`; phần Java dùng cú pháp tương thích Java 17+. Trên Windows/macOS, phần build thư viện dùng công cụ và định dạng thư viện phù hợp hệ điều hành.

**Bước 1 — `NativeMath.java`:**

```java
public final class NativeMath {
    static {
        System.loadLibrary("nativemath");
    }

    private static native int add(int left, int right);

    public static void main(String[] args) {
        System.out.println("sum=" + add(3, 4));
    }
}
```

`System.loadLibrary` chạy khi class được khởi tạo; lời gọi `add(3, 4)` khiến JVM liên kết phương thức `native` với implementation trong thư viện.

**Bước 2 — `NativeMath.c`:**

```c
#include "NativeMath.h"

JNIEXPORT jint JNICALL Java_NativeMath_add(
        JNIEnv *env, jclass clazz, jint left, jint right) {
    (void) env;
    (void) clazz;
    return left + right;
}
```

`NativeMath.h` do `javac -h` tạo ra, chứa chữ ký JNI tương ứng; `jclass` là tham số của phương thức `static native`. Mã C tính tổng hai số và không giữ con trỏ bộ nhớ bên ngoài lời gọi.

**Bước 3 — Biên dịch trên Linux:**

```bash
javac -h . NativeMath.java
gcc -fPIC -shared -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" -o libnativemath.so NativeMath.c
```

Lệnh cần `JAVA_HOME` trỏ đúng JDK đang dùng để build. Kết quả có `NativeMath.class`, `NativeMath.h`, `libnativemath.so` trong thư mục hiện tại.

**Bước 4 — So sánh ba chế độ khi chạy bằng JDK 24+:**

```bash
# (A) Mặc định: chạy được nhưng có cảnh báo native access trên stderr.
java -Djava.library.path=. NativeMath

# (B) Mô phỏng tương lai: từ chối nếu chưa cấp quyền.
java --illegal-native-access=deny -Djava.library.path=. NativeMath

# (C) Cấp quyền và kiểm tra chặt: chạy được, không có cảnh báo JEP 472.
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -Djava.library.path=. NativeMath
```

Với (A) và (C), **stdout chính xác** của chương trình là:

```text
sum=7
```

Ở (A), JDK 24+ mặc định in cảnh báo lên **stderr** khi tải thư viện. Vì cùng unnamed module đã có một cảnh báo, JVM không nhất thiết in thêm cảnh báo khi `add` được bind. Ở (B), thao tác `System.loadLibrary` chưa có quyền dẫn đến `IllegalCallerException`; do xảy ra trong static initializer, stack trace có thể xuất hiện thêm `ExceptionInInitializerError`. Chương trình **không** in `sum=7`. Ở (C), quyền được cấp cho unnamed module chứa cả thao tác load và khai báo `native`.

Nếu (A) hoặc (C) báo `UnsatisfiedLinkError`, hãy kiểm tra file `.so`, `java.library.path`, kiến trúc 32/64-bit, thư viện phụ thuộc và chữ ký JNI; lỗi tìm/nạp/bind thư viện này **khác** với thiếu quyền native access.

## 6. Phát hiện phần nào của ứng dụng phụ thuộc JNI

**Quét tĩnh bằng `jnativescan` (có từ JDK 24):**

```bash
jnativescan --class-path app.jar
jnativescan --class-path app.jar --print-native-access
jnativescan --module-path mods --add-modules com.acme.app --print-native-access
```

Công cụ quét JAR và các module phụ thuộc trong cấu hình được chỉ định, phát hiện tham chiếu đến restricted methods cùng khai báo `native`; chế độ `--print-native-access` trả về tên module cần xem xét. Nó không thay thế kiểm thử runtime: lớp chỉ tải bằng reflection, thư viện được chọn theo nền tảng, đường đi lỗi hiếm gặp và JNI nằm sâu trong dependency có thể khiến kiểm kê chưa đầy đủ nếu bạn quét thiếu JAR hoặc chưa chạy đúng chức năng.

**Quan sát runtime:** chạy bản ứng dụng thật trên JDK đích, lưu stderr từ giai đoạn khởi động **và** các luồng chức năng cần JNI. Các sự kiện JDK Flight Recorder `jdk.NativeLibraryLoad` và `jdk.NativeLibraryUnload` giúp quan sát thư viện được tải/gỡ, nhưng không tự thay thế việc xác định module Java nào cần cấp quyền.

**Kiểm tra dependency:** rà soát JAR chứa khai báo `native`, mã gọi `System.loadLibrary`, thư viện `.so/.dll/.dylib` đi kèm, native launcher/agent, phiên bản driver và các biến môi trường liên quan. Một ứng dụng Java thuần ở tầng business có thể phụ thuộc JNI gián tiếp qua thư viện thứ ba.

## 7. Quy trình đề xuất khi nâng từ JDK 17/21 lên JDK 24+

1. **Chốt phiên bản đích và baseline:** ghi lại JDK của môi trường phát triển, CI, staging và production; kiểm tra Java và native libraries thực sự được nạp, kể cả kiến trúc CPU và OS.
2. **Lập danh sách chủ sở hữu native access:** quét JAR bằng `jnativescan`, chạy tích hợp trên JDK đích để thu cảnh báo và phân loại theo module **thực hiện load** hoặc **khai báo `native`**; xác minh cả phụ thuộc transitively.
3. **Cấp quyền tối thiểu:** ưu tiên named modules và `--enable-native-access=M1,M2`. Nếu hệ thống vẫn hoàn toàn chạy classpath thì dùng `ALL-UNNAMED` có kiểm soát và lập kế hoạch thu hẹp khi phù hợp.
4. **Bật kiểm tra nghiêm ngặt:** chạy staging/CI bằng `--illegal-native-access=deny` cùng danh sách quyền cần thiết. Kích hoạt thực sự những chức năng gọi JNI, kể cả tải lazy, startup hook, shutdown hook và trường hợp lỗi.
5. **Sửa thư viện/đóng gói:** nâng bản thư viện hỗ trợ JDK/OS/ABI đích, sửa tên thư viện/đường dẫn nếu cần; tránh giải quyết lỗi `UnsatisfiedLinkError` bằng cách thêm quyền không liên quan.
6. **Đưa option vào launcher thật:** xác nhận cờ đến JVM trong Docker/Kubernetes, script deploy, test runner, IDE và service wrapper; kiểm thử lại từ artifact cuối cùng, không chỉ từ lệnh chạy thử trên máy lập trình.
7. **Đặt điều kiện phát hành:** với cấu hình đích, các luồng JNI quan trọng chạy qua `deny` mà không có `IllegalCallerException`, không phát sinh lỗi native/ABI và giữ đúng kết quả nghiệp vụ. Tiếp tục theo dõi release notes của các JDK sau.

Nếu một dependency chỉ có bản dùng JNI, việc **giữ JNI và cấp quyền đúng** là giải pháp hợp lệ. Cân nhắc FFM API (ổn định từ JDK 22) cho phát triển hoặc hiện đại hóa phù hợp, nhưng FFM cũng có restricted operations và vẫn cần native access ở các điểm liên quan; **chuyển từ JNI sang FFM không tự loại bỏ yêu cầu cấp quyền**.

## 8. Sự cố thường gặp và cách chẩn đoán

| Hiện tượng | Khả năng cao | Cách xử lý |
| --- | --- | --- |
| `WARNING: A restricted method ... System::loadLibrary ...` | Module gọi nạp thư viện chưa được cấp quyền | Xác định module thực hiện load, thêm vào `--enable-native-access`. |
| `WARNING: A native method ... has been bound` | Module **khai báo** phương thức `native` chưa được cấp quyền | Cấp quyền cho module khai báo, không chỉ module gọi phương thức. |
| `IllegalCallerException` khi bật `deny` | Có thao tác restricted ở module chưa được cấp native access | Dùng cảnh báo/scan/stack trace để tìm module, chỉnh launcher rồi chạy lại cùng `deny`. |
| `UnsatisfiedLinkError: no ... in java.library.path` | Thiếu thư viện hoặc đường dẫn tra cứu sai | Kiểm tra tên logic thư viện, file, `java.library.path`, phụ thuộc hệ điều hành và kiến trúc. |
| `UnsatisfiedLinkError` ở phương thức `native` | Không tìm thấy symbol hoặc chữ ký JNI không khớp | Tạo lại header bằng `javac -h`, kiểm tra exported symbol, library/classloader. |
| Cảnh báo vẫn tồn tại dù đã thêm `ALL-UNNAMED` | Mã restricted nằm trong **named module**, hoặc option không đến đúng JVM | Đọc tên module trong cảnh báo; cấp quyền riêng cho named module; kiểm tra startup command. |
| Mã Java chỉ gọi wrapper mà vẫn thấy cảnh báo | Wrapper/dependency thực hiện load hoặc khai báo native | Tìm implementation và module sở hữu thao tác restricted; đừng chỉ xem caller business. |

Không nhầm những lỗi sau với JEP 472: lỗi truy cập reflection/module như `InaccessibleObjectException`, thiếu package được export, thư viện native sai ABI, crash từ con trỏ C/C++, hoặc permission của hệ điều hành. `--enable-native-access` chỉ giải quyết chính sách native access của JVM.

## 9. Tự kiểm tra kiến thức

**Tình huống A:** Module `com.acme.api` gọi `NativeBridge.compute()`; `NativeBridge` khai báo `native` trong `com.acme.bridge`, còn chính `com.acme.bridge` gọi `System.loadLibrary`. **Cấp quyền cho module nào?** → `com.acme.bridge`; `com.acme.api` chỉ gọi Java method đã được khai báo ở module khác.

**Tình huống B:** `com.acme.loader` gọi `System.loadLibrary`, `com.acme.bridge` khai báo `native`. **Cấp quyền cho module nào?** → Cả `com.acme.loader` và `com.acme.bridge`, vì kiểm tra load và binding gắn với hai module khác nhau.

**Tình huống C:** Sau nâng lên JDK 24, startup vẫn hoạt động nhưng stderr có warning JNI một lần. **Có thể bỏ qua vĩnh viễn?** → Không. Đó là tín hiệu cần cấp quyền và thử `--illegal-native-access=deny` trước các bản JDK siết chặt mặc định.

**Tình huống D:** Đã thêm `--enable-native-access=ALL-UNNAMED`, nhưng ứng dụng vẫn lỗi không tìm thấy `libfoo.so`. **Sửa gì?** → Kiểm tra việc đóng gói thư viện và đường dẫn nạp; flag cấp quyền không cung cấp file thư viện.

## 10. Nguồn chuẩn để tra cứu khi nâng phiên bản

- [OpenJDK JEP 472 – Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): phạm vi, cảnh báo loading/binding, cấp quyền và kế hoạch thay đổi mặc định.
- [Oracle JDK 24 Migration Guide – Restrictions on and Warnings from Accessing Native Code](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html): hướng dẫn chuyển đổi và triển khai.
- [Oracle JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/migrating-from-jdk-8-later-jdk-releases.html): hành vi trong các phiên bản tiếp theo.
- [JDK 24 `jnativescan` Tool Guide](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jnativescan.html): cú pháp quét classpath/module path.
- [Java Native Interface Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/index.html): quy tắc tương tác và binding JNI.

**Nguyên tắc vận hành:** xác định chính xác nơi Java nạp thư viện hoặc khai báo phương thức `native` → cấp native access cho module tương ứng → chạy kiểm thử tích hợp với `--illegal-native-access=deny`. Đó là cách giữ ứng dụng JNI hoạt động ổn định khi nâng JDK.
