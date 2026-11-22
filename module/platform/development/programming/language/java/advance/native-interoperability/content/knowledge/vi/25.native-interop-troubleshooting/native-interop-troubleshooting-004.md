# Dò JNI bằng jnativescan và kiểm tra quyền native access khi nâng JDK

## 1. Mục tiêu và phạm vi

Khi nâng ứng dụng từ JDK cũ lên JDK 24 hoặc mới hơn, việc ứng dụng vẫn khởi động được **không bảo đảm** các đường đi sử dụng JNI đã an toàn trước chính sách native access. Bài này hướng dẫn xác định JAR/module nào dùng JNI, diễn giải kết quả của công cụ `jnativescan`, kiểm tra tác động của `--illegal-native-access` lúc chạy, rồi cấp quyền đúng phạm vi bằng `--enable-native-access`.

Sau bài học, bạn cần làm được bốn việc: (1) phân biệt việc quét tĩnh với việc thực thi JNI; (2) tìm lớp khai báo `native` và lời gọi phương thức restricted; (3) kiểm tra cấu hình class path/module path, cảnh báo và lỗi; (4) lập bằng chứng trước khi đổi JDK trong môi trường thật.

**Phạm vi phiên bản:** `jnativescan` và cơ chế hạn chế JNI nêu dưới đây có từ **JDK 24** (JEP 472). Hãy dùng bộ công cụ của JDK 24+ để quét; JDK 17/21 có thể biên dịch ví dụ Java đơn giản nhưng không có cùng công cụ/cờ kiểm tra này. Theo tài liệu JDK 27, chế độ mặc định vẫn là `warn`; `deny` được dự kiến trở thành mặc định ở một bản phát hành tương lai. Luôn kiểm tra tài liệu đúng bản JDK đích thay vì đoán thời điểm thay đổi.

## 2. Điều gì thực sự bị giới hạn?

Java Native Interface (JNI) cho Java tương tác với mã native (thường là thư viện `.so`, `.dll` hoặc `.dylib`). JNI hữu ích khi cần dùng API hệ điều hành hoặc thư viện có sẵn, nhưng mã native nằm ngoài những bảo đảm an toàn thông thường của JVM: lỗi con trỏ, ABI hoặc bộ nhớ có thể làm hỏng tiến trình.

Trong JDK 24+, hai trường hợp JNI cần đặc biệt chú ý:

- **Nạp thư viện native:** gọi `System.load(...)`, `System.loadLibrary(...)`, `Runtime.load(...)` hoặc `Runtime.loadLibrary(...)`. Đây là các phương thức restricted vì thư viện có thể chạy mã native ngay trong quá trình nạp.
- **Liên kết phương thức `native`:** một khai báo như `private static native int sum(int a, int b);` được gắn với hàm native khi phương thức ấy được gọi lần đầu. Bước liên kết (binding) này là hoạt động bị giới hạn.

JDK cũng áp dụng mô hình native access cho **Foreign Function & Memory API (FFM)**. Vì thế `jnativescan` có thể báo cả lời gọi FFM restricted, dù mục tiêu kiểm kê chính của bài này là JNI.

Cảnh báo có thể xuất hiện muộn: một nhánh nghiệp vụ hiếm gặp chưa được thực thi sẽ chưa kích hoạt nạp thư viện hoặc liên kết phương thức `native`. Ngược lại, một khai báo `native` có thể được bộ quét tìm thấy dù ứng dụng chưa từng gọi nó. **Quét tĩnh là chỉ dấu cần điều tra; kiểm thử đường đi thật mới cho biết hành vi lúc chạy.**

## 3. Dùng jnativescan đúng cách

Kiểm tra công cụ trước:

~~~bash
java -version
jnativescan --version
jnativescan --help
~~~

Hãy chắc chắn cả `java` chạy thử và `jnativescan` đều thuộc JDK đích hoặc bản JDK được chọn có chủ ý. Công cụ nhận **các JAR**, class path, module path và root module; không được hiểu nó là công cụ quét trực tiếp nội dung mã máy trong tệp `.dll`/`.so`.

| Tùy chọn | Tác dụng |
| --- | --- |
| `--class-path app.jar` | Quét JAR trên class path; chúng thuộc unnamed module. |
| `--module-path mods --add-modules com.example.app` | Quét root module và các module phụ thuộc được giải quyết từ module path, kể cả các provider theo cơ chế `uses`. |
| `--print-native-access` | In danh sách tên module cần xem xét, thay vì cây JAR/lớp/phương thức. |
| `--release 25` | Chọn quy tắc restricted API và lớp trong multi-release JAR phù hợp Java 25; thay `25` bằng phiên bản đích. |
| `--help`, `--version` | Xem cú pháp và phiên bản công cụ. |

Dùng dấu `:` giữa các phần tử class path/module path trên Linux, macOS; dùng `;` trên Windows. JAR được chỉ định trong `--class-path` đều được quét, bao gồm các JAR khai báo trong `Class-Path` của manifest nếu tìm thấy. Với `--module-path`, việc cung cấp đường dẫn **chưa đủ**: cần `--add-modules` để chỉ rõ root modules phải quét.

Ví dụ tổng quát (đổi đường dẫn và tên module theo ứng dụng):

~~~bash
jnativescan --class-path app.jar
jnativescan --class-path app.jar --print-native-access
jnativescan --module-path mods --add-modules com.example.app
jnativescan --module-path mods --add-modules com.example.app --print-native-access
jnativescan --class-path app.jar --release 25
~~~

Trong báo cáo chi tiết, hãy đọc lần lượt **JAR → module → lớp → phương thức**. Dòng `is a native method declaration` cho biết có khai báo `native`; dòng `references restricted methods` cho biết bytecode tham chiếu phương thức restricted nào. Danh sách module từ `--print-native-access` là đầu vào để đánh giá việc cấp quyền, **không tự động chứng minh mọi phương thức đó đã thực thi**.

## 4. Thực hành tái lập được, không cần xây thư viện C

Tạo một tệp `NativeAccessAudit.java` như sau (Java 17+ hợp lệ). Ví dụ cố tình dùng tên thư viện không tồn tại để tách lỗi **cấp quyền** khỏi lỗi **tìm thư viện**. Chỉ chạy với thư mục thử nghiệm sạch không có thư viện trùng tên:

~~~java
public final class NativeAccessAudit {
    private static native int nativeSum(int left, int right);

    private static void probe() {
        try {
            System.loadLibrary("native_audit_demo_library_not_installed");
            System.out.println("Library loaded");
        } catch (IllegalCallerException ex) {
            System.out.println("Denied: IllegalCallerException");
        } catch (UnsatisfiedLinkError ex) {
            System.out.println("Gate passed; library absent");
        }
    }

    public static void main(String[] args) {
        if (args.length == 1 && "probe".equals(args[0])) {
            probe();
        } else {
            System.out.println("Ready; no native operation executed");
        }
    }
}
~~~

Biên dịch, đóng gói, chạy đường đi **không thực thi** JNI rồi quét JAR:

~~~bash
javac NativeAccessAudit.java
jar --create --file native-access-audit.jar NativeAccessAudit.class
java -cp native-access-audit.jar NativeAccessAudit
jnativescan --class-path native-access-audit.jar
jnativescan --class-path native-access-audit.jar --print-native-access
~~~

`stdout` của lệnh `java` đầu tiên là chính xác:

~~~text
Ready; no native operation executed
~~~

Kết quả quét chi tiết sẽ chỉ ra cả hai dấu hiệu: khai báo `NativeAccessAudit::nativeSum(int,int)int` là `native` và phương thức `probe()` tham chiếu `java.lang.System::loadLibrary(String)void`. Vị trí/định dạng dòng phụ thuộc phiên bản công cụ. Với chế độ `--print-native-access`, JAR đặt trên class path trả về:

~~~text
ALL-UNNAMED
~~~

Điểm cần nhớ: chương trình vừa chạy **không phát cảnh báo JNI** ở nhánh mặc định, nhưng `jnativescan` vẫn phát hiện khả năng native access. Lý do là `main` chưa gọi `probe` hoặc `nativeSum`.

Bây giờ kiểm thử đúng cổng cấp quyền trên **JDK 24+**:

~~~bash
java --illegal-native-access=deny -cp native-access-audit.jar NativeAccessAudit probe
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp native-access-audit.jar NativeAccessAudit probe
~~~

Khi không có cờ cấp quyền, lệnh thứ nhất in:

~~~text
Denied: IllegalCallerException
~~~

Khi đã cấp native access cho unnamed module, lệnh thứ hai in:

~~~text
Gate passed; library absent
~~~

Lệnh thứ hai đi qua bước kiểm tra native access, rồi `System.loadLibrary` thất bại vì **không có tệp thư viện**; ngoại lệ `UnsatisfiedLinkError` đã được bắt để bài thực hành chạy độc lập. Điều này **không chứng minh một thư viện JNI thật đã liên kết thành công**. Để kiểm thử tích hợp, cần cung cấp đúng binary native, kiến trúc CPU, các thư viện phụ thuộc và đường dẫn nạp.

Thử `--illegal-native-access=warn` trên nhánh `probe` sẽ cho phép đi qua cổng và có thể thấy cảnh báo `WARNING` trên **stderr** (thường một lần cho mỗi module trong chế độ này), rồi vẫn nhận thông báo thiếu thư viện ở `stdout`. Đừng so khớp nguyên văn cảnh báo: tên lớp, module và đường dẫn thực tế thay đổi theo JDK và môi trường.

## 5. Cấp quyền theo module, hiểu rõ ALL-UNNAMED

Cờ `--enable-native-access` xác định **module được phép** làm thao tác restricted. Nó cần xuất hiện trong cấu hình của **tiến trình JVM thật** chạy chương trình, trước tên main class hoặc tham số `-jar`.

**Ứng dụng trên class path** (legacy JAR, code nằm trong unnamed module):

~~~bash
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -cp "app.jar:lib/dependency.jar" com.example.Main
~~~

Ví dụ trên dùng dấu `:` của Linux/macOS; thay bằng `;` nếu chạy Windows. `ALL-UNNAMED` cấp quyền native access cho **mọi code trên class path**, vì vậy chỉ nên dùng khi đã hiểu phạm vi và chưa thể tách module hẹp hơn.

**Ứng dụng có named modules**:

~~~bash
java --enable-native-access=com.example.nativebridge --illegal-native-access=deny --module-path mods --module com.example.app/com.example.Main
~~~

Lệnh minh họa giả định `mods` chứa module `com.example.app` và `com.example.nativebridge`, và module thứ hai là nơi thực hiện restricted operation. Các tên này là ví dụ; hãy lấy tên thật từ cấu hình module và kết quả quét. Nếu nhiều module trực tiếp dùng native access, truyền danh sách cách nhau bằng dấu phẩy: `--enable-native-access=mod.one,mod.two`.

Có thể đưa JAR không có `module-info.class` lên module path để JVM nhận là **automatic module**, rồi cấp quyền theo tên module thực tế. Việc chuyển đường dẫn có thể ảnh hưởng dependency, reflection, service loading; phải kiểm thử lại ứng dụng. Không tự giả định tên module từ tên artifact nếu chưa kiểm tra.

| Chế độ `--illegal-native-access` | Hành vi khi module chưa được cấp quyền |
| --- | --- |
| `allow` | Cho thực hiện mà không cảnh báo; chỉ thích hợp để đối chiếu/tạm thời. |
| `warn` | Cho thực hiện, cảnh báo lần đầu theo module; mặc định trong JDK 24–27 theo tài liệu hiện hành. |
| `deny` | Ném `IllegalCallerException` khi thực hiện native access trái phép; nên dùng khi kiểm thử nâng JDK. |

**Cách kiểm tra hiệu quả nhất:** chạy toàn bộ kịch bản tích hợp với `--illegal-native-access=deny`, sau đó chỉ cấp `--enable-native-access` cho module đã được xác minh cần JNI/FFM. Đừng dùng `--illegal-native-access=allow` làm giải pháp nâng cấp lâu dài. Việc cấp quyền không thay thế kiểm tra độ tin cậy của thư viện native.

## 6. Quy trình rà soát ứng dụng trước khi nâng JDK

1. **Ghi lại runtime mục tiêu:** phiên bản JDK hiện tại và đích, hệ điều hành/kiến trúc CPU, lệnh launch thực tế (CLI, IDE, Gradle/Maven, container, service), thư viện native đang đóng gói và path nạp. Xác định cả những tiến trình phụ do công cụ test hoặc framework tạo ra.
2. **Thu đủ JAR chạy thật:** gồm ứng dụng và các dependency runtime, plugin, JDBC/driver/framework native bridge nếu có. Với Spring Boot executable/fat JAR chứa JAR lồng ở `BOOT-INF/lib/`, đừng mặc định `jnativescan --class-path app-fat.jar` sẽ tự quét các JAR lồng; hãy lấy các JAR dependency riêng để quét.
3. **Quét chi tiết trước:** chạy `jnativescan` trên class path thực tế hoặc `--module-path ... --add-modules ...`, chỉ định `--release` phù hợp bản JDK đích nếu cần. Lưu kết quả theo từng JAR, lớp, phương thức; gom module bằng `--print-native-access`.
4. **Phân loại kết quả:** thư viện nào trực tiếp khai báo `native`, lớp nào gọi `System.load*`/`Runtime.load*` hoặc FFM restricted, ai là chủ sở hữu dependency, đường đi nghiệp vụ nào kích hoạt, và có phiên bản thư viện tương thích với JDK mới không.
5. **Chạy kiểm thử hành vi:** dùng `--illegal-native-access=deny` không cấp quyền trước để xác định những nhánh thật sự bị chặn. Sau đó chỉ bổ sung cờ `--enable-native-access` cần thiết, kiểm thử lại startup, chức năng hiếm dùng, shutdown, test suite và môi trường đóng gói.
6. **Đối chiếu log:** với `warn`, cảnh báo thường ghi trên stderr. Dùng stack trace và tên module trong cảnh báo để tìm mã gọi. Có thể bật JFR và kiểm tra sự kiện `jdk.NativeLibraryLoad` / `jdk.NativeLibraryUnload` để tìm thư viện thực tế được nạp/tháo; các sự kiện này không thay cho danh sách phương thức JNI được liên kết.
7. **Chốt bằng chứng nâng cấp:** lưu phiên bản công cụ, lệnh scan, đầu vào JAR/module, danh sách module cần quyền, cờ JVM cuối cùng, lỗi trước/sau, kết quả kiểm thử native binary trên từng OS/architecture; chạy lại trên bản JDK đích khi dependency thay đổi.

Một cách đối chiếu sự kiện library loading với Java Flight Recorder (JFR) khi JDK và cấu hình ghi hỗ trợ:

~~~bash
java -XX:StartFlightRecording=filename=native-audit.jfr,settings=profile -cp app.jar com.example.Main
jfr print --events jdk.NativeLibraryLoad,jdk.NativeLibraryUnload native-audit.jfr
~~~

Đây là **mẫu lệnh áp dụng cho ứng dụng thật**, không chạy được ngay nếu thiếu `app.jar`/`com.example.Main`. Việc không thấy sự kiện có thể do đường đi chưa chạy hoặc cấu hình JFR chưa bật event; không kết luận ứng dụng không dùng JNI chỉ từ kết quả rỗng.

## 7. Hạn chế của scan và các bẫy thường gặp

- **Kết quả quét rỗng không đủ kết luận “không JNI”.** `jnativescan` phân tích tĩnh JAR và các tham chiếu nhìn thấy trong bytecode. Nó không chạy ứng dụng, không bảo đảm thấy mọi nhánh nạp thư viện qua reflection, bytecode sinh động, plugin được nạp ngoài tập JAR đã quét hoặc mã native tự gọi API native khác.
- **Quét sai tập đầu vào:** bỏ sót dependency runtime, multi-release JAR, module cung cấp service hoặc chỉ quét JAR “fat” có thư viện lồng sẽ cho bức tranh thiếu. Phải quét runtime class path/module path gần nhất với bản triển khai.
- **Nhầm cảnh báo với lỗi nạp thư viện:** `IllegalCallerException` là cổng native access bị chặn; `UnsatisfiedLinkError` thường là không tìm được library/ký hiệu native, sai kiến trúc hoặc lệch chữ ký; crash JVM có thể do lỗi mã native. Cấp quyền không sửa lỗi binary/ABI.
- **Nhầm `native` declaration với “đã chạy native code”:** đây là tín hiệu tĩnh. JNI binding chỉ xảy ra khi phương thức được gọi; thư viện cũng có thể được nạp theo nhánh khác.
- **Sai module được cấp quyền:** mã thực hiện restricted operation nằm trong module nào thì module đó cần quyền. Cấp quyền cho application entrypoint không tự động cấp cho mọi thư viện named module phụ thuộc.
- **Đặt cờ sai vị trí:** cờ JVM đứng trước tên main class hoặc `-jar`; mọi cấu hình Gradle `test`, container entrypoint, service wrapper và trình khởi chạy khác cần kiểm tra riêng.
- **Nhầm native access với reflective access:** `--add-opens`, `--add-exports` giải quyết một nhóm giới hạn của Java module system; chúng **không** thay thế `--enable-native-access`.
- **Dùng `ALL-UNNAMED` vô điều kiện:** tiện cho hệ thống legacy nhưng mở quyền cho toàn class path. Ưu tiên thu hẹp qua named/automatic modules nếu ứng dụng cho phép.

## 8. Bảng chẩn đoán nhanh

| Quan sát | Cách diễn giải | Việc nên kiểm tra |
| --- | --- | --- |
| `jnativescan` báo `native method declaration` | Có phương thức JNI trong bytecode. | Tìm nhánh gọi, thư viện chứa hàm tương ứng, phiên bản OS/JDK. |
| `jnativescan` báo `references restricted methods` | Có lời gọi API restricted trong JAR. | Tên lớp, method, module; đường đi runtime thực thi lời gọi. |
| Khi chạy hiện `WARNING` về native access | Module chưa được cấp quyền; ở chế độ `warn`, thao tác vẫn được cho phép. | Cờ launch, tên module trong stderr, nguồn phát sinh. |
| `IllegalCallerException` khi đặt `deny` | Cổng native access đang chặn mã không được cấp quyền. | Cấp quyền cho đúng module, không chỉ module main. |
| `UnsatisfiedLinkError` sau khi đã cấp quyền | Có thể lỗi tìm/nạp binary hoặc native method binding, độc lập với gate. | `java.library.path`, đường dẫn, CPU architecture, dependencies, JNI symbol/signature. |
| Không thấy cảnh báo ở startup nhưng scan có kết quả | Chưa thực thi nhánh native hoặc module đã được cấp quyền. | Kiểm thử chức năng, log stderr và cấu hình khởi chạy. |

## 9. Tiêu chí hoàn thành kiểm tra trước khi nâng JDK

- [ ] Đã xác định và ghi đúng JDK đích, công cụ `jnativescan` và `--release`.
- [ ] Đã quét đủ JAR runtime và root modules; đã kiểm tra kết quả theo lớp/phương thức.
- [ ] Đã phân biệt khai báo `native`, restricted method call và thao tác thực sự diễn ra.
- [ ] Đã chạy `--illegal-native-access=deny` trên các luồng chính, luồng lỗi, batch/plugin và các nhánh ít dùng.
- [ ] Đã chỉ định `--enable-native-access` cho đúng các module phải dùng native code; phạm vi `ALL-UNNAMED` được cân nhắc rõ nếu bắt buộc.
- [ ] Đã xử lý độc lập các lỗi `UnsatisfiedLinkError`, sai binary/ABI và lỗi quyền; không dùng một cờ để che các lỗi khác.
- [ ] Đã kiểm thử trên môi trường triển khai thật và lưu lệnh, kết quả scan, stderr và kết quả test để đối chiếu lần nâng JDK tiếp theo.

## Tài liệu chính thức

- JEP 472 — Prepare to Restrict the Use of JNI: https://openjdk.org/jeps/472
- Oracle JDK 25, `jnativescan` command: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jnativescan.html
- Oracle JDK 27, `java` command (native access options): https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- Oracle JDK 27, Migration Guide (JNI/native access): https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html

**Ghi nhớ:** `jnativescan` giúp xác định **nơi có khả năng dùng native access**; chế độ `deny` và kiểm thử luồng chạy cho biết **nơi hệ thống thực sự cần quyền**. Quyền đúng module cộng với thư viện native tương thích mới là kết quả cần đạt khi nâng JDK.