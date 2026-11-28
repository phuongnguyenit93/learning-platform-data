# Kiểm tra API bị loại bỏ, bị hạn chế hoặc có thay đổi hành vi ảnh hưởng mã đang dùng

## 1. Mục tiêu và bối cảnh

Nâng cấp JDK không chỉ là đổi phiên bản compiler hoặc thay image container. Một ứng dụng có thể vẫn biên dịch được nhưng gặp lỗi khi chạy vì một API đã bị xóa, một quyền truy cập nội bộ bị đóng, một lời gọi JNI cần khai báo quyền native access, hoặc một API vẫn tồn tại nhưng hành vi mặc định đã đổi.

Với Java 25, cần phân biệt ba dạng tương thích:

| Dạng | Câu hỏi cần kiểm tra | Ví dụ lỗi |
| --- | --- | --- |
| **Source compatibility** | Source hiện tại còn biên dịch được không? | Gọi constructor đã bị xóa hoặc import lớp đã bị loại bỏ. |
| **Binary compatibility** | Class/JAR đã biên dịch có liên kết và nạp được không? | Bytecode tham chiếu method/constructor không còn trong runtime. |
| **Behavioral compatibility** | Chương trình còn cho kết quả và hành vi như trước không? | File.delete() trả false với file read-only trên Windows; TLS handshake bị từ chối thuật toán cũ. |

**JDK 25 là một bản LTS**, nhưng việc chuyển từ JDK 8, 11, 17 hoặc 21 lên JDK 25 vẫn cần kiểm tra các thay đổi đã xuất hiện ở những release trung gian. Đặc biệt, một số thay đổi lớn xảy ra từ JDK 17, 18, 23 và 24, sau đó tiếp tục ảnh hưởng khi chạy trên JDK 25.

Bài **Kiểm tra API bị loại bỏ, bị hạn chế hoặc có thay đổi hành vi ảnh hưởng mã đang dùng**, thuộc chương **Tác động nâng cấp** của lộ trình **JAVA_VERSION_JAVA25**, hướng dẫn:

1. Phân loại API đã xóa, API deprecated for removal, tính năng bị tắt và hành vi đã đổi.
2. Xác định các thay đổi quan trọng trong JDK 24 và JDK 25.
3. Kiểm tra những thay đổi nền tảng từ JDK 17, 18 và 23 vẫn ảnh hưởng ứng dụng.
4. Thay thế API hoặc cấu hình cũ bằng lựa chọn được hỗ trợ.
5. Quét bytecode, JDK internals và native access trước khi nâng cấp.
6. Thiết kế kiểm thử tương thích, rollout và phương án quay lui.

**Phạm vi:** bài tập trung vào các thay đổi còn có ý nghĩa khi ứng dụng chạy trên JDK 25. Các flag, cơ chế hoặc API đã bị loại bỏ được nhắc đến để nhận diện mã cũ và lập kế hoạch chuyển đổi; không hướng dẫn dùng chúng như giải pháp mới.

## 2. Đọc đúng trạng thái của một API hoặc tính năng

Không phải mọi dòng cảnh báo trong tài liệu migration đều có cùng mức độ khẩn cấp.

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| **Removed** | API/tính năng không còn trong release đích. | Xóa lời gọi cũ và thay bằng API hoặc cách triển khai khác. |
| **Deprecated** | API vẫn tồn tại nhưng không nên dùng cho code mới. | Lập kế hoạch thay thế; kiểm tra lý do deprecation. |
| **Deprecated for removal** | API có ý định bị loại bỏ trong tương lai. | Ưu tiên chuyển đổi, không thêm phụ thuộc mới. |
| **Restricted** | API vẫn tồn tại nhưng cần quyền truy cập hoặc điều kiện runtime cụ thể. | Cấp quyền đúng phạm vi hoặc thay bằng API được khuyến nghị. |
| **Behavior changed** | API còn tồn tại nhưng kết quả, ngoại lệ hoặc mặc định đã đổi. | Kiểm tra test và logic phụ thuộc vào hành vi cũ. |
| **Obsolete option** | Flag có thể vẫn được nhận diện nhưng không còn tác dụng hoặc sắp bị xóa. | Gỡ khỏi startup script; không dựa vào nó để sửa lỗi. |

Một API deprecated chưa chắc đã bị xóa trong release kế tiếp. Ngược lại, một API không deprecated nhưng hành vi thay đổi vẫn có thể làm hỏng ứng dụng. Vì vậy, kiểm tra cả compiler warning, runtime warning, release notes và integration test.

## 3. Các API Java SE bị xóa trực tiếp trong JDK 25

Theo Oracle JDK Migration Guide, hai mục Java SE API được liệt kê là bị xóa trong Java SE 25:

| API bị xóa | Lý do / ảnh hưởng | Cách chuyển đổi |
| --- | --- | --- |
| **javax.swing.plaf.synth.SynthLookAndFeel.load(URL)** | Overload cũ đã deprecated for removal. | Dùng **load(InputStream, Class<?>)** để nạp file Synth, hoặc **setStyleFactory(...)** nếu ứng dụng tự cung cấp style factory. |
| **javax.swing.plaf.basic.BasicSliderUI()** | Constructor không tham số bị đưa vào nhầm API từ JDK 16, deprecated for removal từ JDK 23 và bị xóa trong JDK 25. | Dùng **BasicSliderUI(JSlider)** hoặc để Look and Feel tạo UI delegate qua cơ chế **createUI(JComponent)**. |

Ví dụ chuyển cách nạp Synth Look and Feel:

~~~java
import javax.swing.UIManager;
import javax.swing.plaf.synth.SynthLookAndFeel;
import java.io.InputStream;

public final class SynthThemeLoader {

    public static void install() throws Exception {
        SynthLookAndFeel lookAndFeel = new SynthLookAndFeel();

        try (InputStream input = SynthThemeLoader.class
                .getResourceAsStream("/theme/synth.xml")) {
            if (input == null) {
                throw new IllegalStateException("Không tìm thấy theme/synth.xml");
            }
            lookAndFeel.load(input, SynthThemeLoader.class);
        }

        UIManager.setLookAndFeel(lookAndFeel);
    }
}
~~~

Ví dụ này sử dụng overload còn được hỗ trợ trong Java 25. Tham số Class làm resource base để Synth giải quyết các đường dẫn tương đối trong file theme.

Với BasicSliderUI, nếu thật sự cần tạo delegate trực tiếp, phải truyền JSlider:

~~~java
import javax.swing.JSlider;
import javax.swing.plaf.basic.BasicSliderUI;

JSlider slider = new JSlider();
BasicSliderUI ui = new BasicSliderUI(slider);
~~~

Trong ứng dụng Swing thông thường, không nên tự khởi tạo UI delegate nếu Look and Feel đã quản lý vòng đời đó.

## 4. Constructor Socket không còn tạo được datagram socket

JDK 25 thay đổi hai constructor deprecated của java.net.Socket có tham số stream. Khi stream là false, chúng ném IllegalArgumentException. Không thể tiếp tục dùng các constructor này để tạo UDP/datagram socket.

Mẫu cũ:

~~~java
// Mẫu cũ: không còn hợp lệ trong JDK 25
Socket socket = new Socket(address, port, false);
~~~

Mẫu đúng:

~~~java
import java.net.DatagramSocket;
import java.net.InetSocketAddress;

try (DatagramSocket socket =
        new DatagramSocket(new InetSocketAddress(0))) {
    socket.connect(remoteAddress, remotePort);
    // Gửi/nhận DatagramPacket theo giao thức UDP.
}
~~~

Hãy phân biệt:

- **Socket** biểu diễn kết nối stream như TCP.
- **DatagramSocket** biểu diễn giao tiếp datagram như UDP.

Hai constructor cũ vẫn có mặt nhưng đã đổi hành vi và được lên kế hoạch loại bỏ trong release tương lai. Không giữ chúng chỉ vì code vẫn biên dịch được.

## 5. Các thay đổi hành vi đáng chú ý trong JDK 25

Một số thay đổi không làm source code lỗi biên dịch nhưng có thể khiến test hoặc ứng dụng production hoạt động khác:

| Khu vực | Thay đổi | Ảnh hưởng có thể gặp |
| --- | --- | --- |
| File trên Windows | **File.delete()** không còn tự xóa thuộc tính DOS read-only trước khi xóa file. | Lệnh xóa trả false nếu file thường có thuộc tính read-only. |
| Path trên Windows | Path có thành phần tên file/thư mục kết thúc bằng dấu cách bị từ chối nhất quán. | mkdir() có thể trả false, createNewFile() có thể ném IOException. |
| ICC profile | Các instance dùng chung do JDK cung cấp không còn cho phép ứng dụng sửa dữ liệu profile. | Gọi thao tác sửa trên instance dùng chung có thể ném exception. |
| Console | System.console() mặc định không còn dựa trên JLine. | Trải nghiệm line editing/terminal nâng cao có thể khác so với JDK 22–24. |
| jpackage | Runtime image không còn tự đưa service bindings vào mặc định. | Service provider không có trong runtime image nếu không được thêm rõ ràng. |
| TLS 1.2/DTLS 1.2 | SHA-1 handshake signatures bị vô hiệu hóa mặc định. | Kết nối tới peer chỉ hỗ trợ chữ ký handshake SHA-1 có thể thất bại. |

### 5.1. Xóa file read-only trên Windows

Từ JDK 25, File.delete() trả false với regular file có DOS read-only attribute. Trước đó JDK tự xóa thuộc tính này rồi mới thử xóa file; hai thao tác không nguyên tử nên có thể để lại file với thuộc tính đã bị đổi nếu xóa thất bại.

Nếu nghiệp vụ thực sự cho phép xóa file read-only, hãy bỏ thuộc tính một cách tường minh:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.DosFileAttributeView;

static void deleteReadOnlyFile(Path path) throws IOException {
    DosFileAttributeView dos =
            Files.getFileAttributeView(path, DosFileAttributeView.class);

    if (dos != null && dos.readAttributes().isReadOnly()) {
        dos.setReadOnly(false);
    }

    Files.delete(path);
}
~~~

Chỉ thực hiện bước bỏ read-only khi chính sách nghiệp vụ cho phép. Không dùng thuộc tính file làm cách vượt qua quyền truy cập của hệ điều hành.

JDK 25 có property **jdk.io.File.allowDeleteReadOnlyFiles=true** để tạm khôi phục hành vi cũ. Đây là compatibility switch cho giai đoạn chuyển đổi; nên sửa code xóa file và gỡ property khỏi cấu hình dài hạn.

### 5.2. Path kết thúc bằng dấu cách trên Windows

Tên file/thư mục có thành phần kết thúc bằng dấu cách không phải pathname hợp lệ trên Windows. JDK 25 khiến thao tác file thất bại nhất quán thay vì có lúc trông như thành công.

Hãy kiểm tra dữ liệu tên file đến từ người dùng, import, batch hoặc hệ thống ngoài. Nếu chuẩn nghiệp vụ cho phép chuẩn hóa tên, thực hiện chuẩn hóa ở ranh giới nhập dữ liệu và ghi nhận thay đổi. Không âm thầm trim mọi path hệ thống vì điều đó có thể làm hai tên khác nhau trở thành cùng một file.

### 5.3. Console không còn JLine mặc định

Trong JDK 22–24, implementation mặc định của System.console() dựa trên JLine. JDK 25 đưa implementation JLine trở lại chế độ opt-in. Nếu ứng dụng phụ thuộc line editing, history hoặc tính năng terminal nâng cao, hãy kiểm tra trên môi trường terminal/IDE thật.

Nếu tính năng đó là yêu cầu sản phẩm, nên khai báo và sử dụng thư viện terminal như một dependency trực tiếp thay vì dựa vào implementation nội bộ của System.console().

## 6. jpackage không còn tự bind service providers

Từ JDK 25, jpackage tạo runtime image mà không tự bao gồm service bindings. Runtime image có thể chứa ít module hơn so với image tạo bằng JDK trước đó.

Điều này có thể ảnh hưởng ứng dụng dùng:

- ServiceLoader.
- JDBC drivers được phát hiện qua service provider.
- Logging providers.
- Plugin hoặc framework tìm implementation qua module service binding.
- Các service implementation nằm trong module path nhưng không được thêm trực tiếp.

Nếu runtime image cần service providers, thêm --bind-services vào các jlink options của jpackage:

~~~bash
jpackage --name OrdersApp ^
  --input input ^
  --main-jar orders-app.jar ^
  --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services"
~~~

Trong ví dụ Windows, dấu ^ là ký hiệu nối dòng của cmd.exe; khi chạy PowerShell, có thể viết lệnh trên một dòng hoặc dùng dấu backtick để nối dòng. Trên Linux/macOS dùng dấu backslash để nối dòng.

Đừng thêm --bind-services theo thói quen cho mọi image. Hãy kiểm tra service provider thực tế mà ứng dụng cần, sau đó xác nhận module đã có trong image bằng java --list-modules và chạy smoke test trên đúng runtime image đã đóng gói.

## 7. Thay đổi bảo mật TLS và provider mật mã

Nâng cấp JDK có thể làm một kết nối hoặc thao tác mật mã cũ thất bại dù source code không đổi. Hai nhóm cần kiểm tra trong JDK 25:

### 7.1. SHA-1 trong TLS/DTLS 1.2 handshake

JDK 25 mặc định vô hiệu hóa các chữ ký handshake SHA-1 cho TLS 1.2 và DTLS 1.2, gồm:

- **rsa_pkcs1_sha1**
- **ecdsa_sha1**
- **dsa_sha1**

Điều này áp dụng cho chữ ký trong quá trình handshake, không đồng nghĩa mọi chữ ký SHA-1 ở mọi định dạng dữ liệu đều bị loại bỏ cùng lúc.

Nếu kết nối thất bại sau nâng cấp, kiểm tra log JSSE và cấu hình thuật toán của peer. Giải pháp bền vững là cập nhật server/client, chứng chỉ và cấu hình TLS để dùng thuật toán chữ ký hiện đại được hỗ trợ. Không khôi phục SHA-1 chỉ để làm cho kết nối cũ tiếp tục hoạt động.

### 7.2. SunPKCS11 bỏ một số PBE SecretKeyFactory

JDK 25 loại bỏ các implementation password-based SecretKeyFactory trong provider SunPKCS11, ví dụ các nhóm:

- **PBEWithHmac[MD]AndAES_128**
- **PBEWithHmac[MD]AndAES_256**
- **HmacPBE[MD]**

Trong đó [MD] có thể là SHA1, SHA224, SHA256, SHA384 hoặc SHA512. Các implementation cũ tạo key encoding khác với implementation tương ứng của SunJCE, dễ gây nhầm lẫn và lỗi liên thông.

Nếu ứng dụng gọi các thuật toán này qua SunPKCS11, hãy kiểm tra provider thực tế và mục đích sử dụng. Với password-based encryption thông thường, dùng provider được hỗ trợ như SunJCE nếu phù hợp; nếu yêu cầu thao tác trong HSM, kiểm tra cơ chế PKCS#11 native được thiết bị/provider hỗ trợ và kiểm thử khả năng tương thích key encoding.

JDK 25 cũng cải thiện PBE của SunJCE để hỗ trợ password Unicode theo UTF-8. Nếu hệ thống dùng password không phải ASCII, hãy kiểm tra lại quá trình tạo/đọc dữ liệu mã hóa ở cả hai đầu và xác nhận cùng quy tắc chuyển password thành bytes.

### 7.3. Root certificates bị loại khỏi cacerts

JDK 25 loại bỏ các root certificate đã hết hạn hoặc không còn được sử dụng, gồm Baltimore CyberTrust Root sau ngày hết hạn và hai root của Camerfirma. Nếu hệ thống kết nối tới endpoint cũ, chain có thể không còn được trust như trước.

Không nên thêm lại root đã bị loại một cách tự động. Kiểm tra chain, issuer và thời hạn; yêu cầu đối tác cập nhật certificate chain sang CA còn được tin cậy. Nếu tổ chức quản lý trust store riêng, rà soát chính sách tin cậy và vòng đời chứng chỉ của tổ chức.

## 8. Security Manager đã bị vô hiệu hóa từ JDK 24

Đây là thay đổi cần xử lý khi nâng từ JDK 17 hoặc 21 lên JDK 25. JDK 24 đã **permanently disable Security Manager**. API vẫn còn để duy trì một phần tương thích, nhưng không còn thực thi mô hình kiểm soát quyền cũ.

Các hành vi quan trọng:

| API/cấu hình | Hành vi trên JDK 24+ |
| --- | --- |
| Khởi chạy với **-Djava.security.manager** | JVM báo lỗi và thoát. |
| **System.setSecurityManager(...)** | Ném UnsupportedOperationException. |
| **System.getSecurityManager()** | Luôn trả null. |
| **SecurityManager.checkPermission(...)** | Ném SecurityException/AccessControlException theo API. |
| **AccessController.doPrivileged(...)** | Thực thi action ngay, như khi không có Security Manager. |
| **Policy.setPolicy(...)** | Ném UnsupportedOperationException. |
| **Subject.getSubject(...)** | Ném UnsupportedOperationException. |

Với JAAS, chuyển:

- **Subject.getSubject(AccessController.getContext())** sang **Subject.current()**.
- **Subject.doAs(...)** sang **Subject.callAs(...)**.

Không có API Java thay thế trực tiếp cho Security Manager. Nếu ứng dụng dùng nó để sandbox plugin hoặc mã không tin cậy, chuyển ranh giới bảo mật ra ngoài JVM: process riêng, user hệ điều hành riêng, container, quyền filesystem/network tối thiểu và IPC được kiểm soát.

Nếu thư viện chỉ gọi System.getSecurityManager() để kiểm tra null hoặc gọi AccessController.doPrivileged() theo idiom cũ, nó có thể vẫn chạy nhưng các lời gọi đó không còn cung cấp sandbox. Rà soát mục đích thực tế thay vì chỉ bỏ warning.

## 9. JNI, FFM và quyền native access

Từ JDK 24, việc dùng JNI và các restricted methods của Foreign Function & Memory API chịu native access restrictions. Mặc định, lời gọi chưa được cấp quyền vẫn có thể chạy nhưng phát cảnh báo; ở release tương lai, hành vi mặc định sẽ chuyển sang từ chối.

Các trường hợp cần rà soát:

- **System.loadLibrary(...)**, **System.load(...)**.
- **Runtime.loadLibrary(...)**, **Runtime.load(...)**.
- Khai báo method **native**.
- FFM restricted methods như thao tác reinterpret hoặc truy cập native memory.

Trước tiên, quét JAR:

~~~bash
jnativescan --release 25 --class-path app.jar
~~~

Nếu ứng dụng dùng module path:

~~~bash
jnativescan --release 25 --module-path mods --add-modules com.example.app
~~~

Để lấy danh sách module cần native access:

~~~bash
jnativescan --release 25 --class-path app.jar --print-native-access
~~~

Sau khi xác định module nào thực sự cần, bật native access có chọn lọc:

~~~bash
java --enable-native-access=com.example.nativebridge -m com.example.app/com.example.Main
~~~

Nếu code ở classpath (unnamed module), có thể dùng **--enable-native-access=ALL-UNNAMED**. Đây là quyền rộng cho toàn bộ code classpath; chỉ dùng khi đã kiểm kê và chấp nhận phạm vi đó.

Chạy integration test với:

~~~bash
java --illegal-native-access=deny --enable-native-access=com.example.nativebridge -jar app.jar
~~~

deny giúp phát hiện lời gọi native chưa được cấp quyền trước khi JDK đổi mặc định. jnativescan là phân tích tĩnh, không thể thấy mọi đường đi được tạo động qua reflection hoặc cấu hình runtime; vẫn cần kiểm thử theo chức năng thật.

Lưu ý: **--illegal-native-access** cũng được đánh dấu sẽ bị loại bỏ trong một release tương lai. Chỉ dùng chế độ **deny** như một bước kiểm thử chuyển tiếp trên JDK 25; cấu hình dài hạn nên tập trung vào việc cấp **--enable-native-access** cho đúng module và loại bỏ những đường gọi native không cần thiết.

## 10. sun.misc.Unsafe và truy cập JDK internals

Hai nhóm vấn đề thường bị gộp chung nhưng có mức xử lý khác nhau:

### 10.1. Memory-access methods của sun.misc.Unsafe

Các memory-access methods của sun.misc.Unsafe đã deprecated for removal từ JDK 23. JDK 24 trở lên phát cảnh báo runtime khi chúng được gọi. Class sun.misc.Unsafe vẫn còn trong JDK 25, nhưng không nên xem đó là API được hỗ trợ ổn định.

Hướng thay thế tùy mục tiêu:

| Mục đích cũ | Hướng thay thế |
| --- | --- |
| Đọc/ghi field hoặc memory location theo kiểu có kiểm soát | VarHandle |
| Truy cập native memory hoặc gọi native function | Foreign Function & Memory API |
| Atomic update và memory ordering | VarHandle với access mode phù hợp |
| Quản lý resource native | Arena, MemorySegment và try-with-resources theo FFM API |

Không chuyển máy móc từng lời gọi Unsafe thành một lời gọi VarHandle. Cần kiểm tra memory ordering, alignment, lifetime, bounds và concurrency semantics của thao tác gốc.

### 10.2. Strong encapsulation từ JDK 17

JDK 17 trở đi strongly encapsulate JDK internals. Reflection truy cập private field/method trong package java.* không mở có thể ném InaccessibleObjectException. --illegal-access đã obsolete từ JDK 17 và không mở lại quyền truy cập.

Nếu thư viện cũ cần truy cập public type trong package chưa export, --add-exports có thể mở quyền truy cập compile/runtime. Nếu cần reflection vào thành viên non-public, --add-opens có thể mở package cụ thể.

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Đây chỉ là workaround có phạm vi rõ ràng để xác nhận nguyên nhân hoặc chờ nâng thư viện. Không thêm hàng loạt --add-opens cho mọi module; cập nhật thư viện để dùng API công khai và gỡ các cờ mở quyền sau khi đã chuyển đổi.

## 11. Thay đổi đã xuất hiện ở JDK 17, 18 và 23 vẫn ảnh hưởng JDK 25

Nếu nâng từ JDK 8 hoặc 11, không thể chỉ đọc danh sách thay đổi của JDK 25. Các thay đổi trung gian dưới đây vẫn có hiệu lực:

| Phiên bản | Thay đổi | Rủi ro khi ứng dụng vẫn dựa vào hành vi cũ |
| --- | --- | --- |
| JDK 9 | Module system, runtime image modular, rt.jar/tools.jar không còn. | Tool tìm rt.jar, đọc classpath của bootstrap loader hoặc phụ thuộc extension mechanism bị lỗi. |
| JDK 9–17 | Strong encapsulation dần được áp dụng; JDK 17 đóng truy cập nội bộ theo mặc định. | Reflection vào private JDK fields/methods ném InaccessibleObjectException. |
| JDK 18 | UTF-8 trở thành default charset trên mọi hệ điều hành. | Đọc/ghi file text phụ thuộc code page Windows cũ có thể đổi nội dung. |
| JDK 23 | Legacy locale data JRE/COMPAT bị loại bỏ. | java.locale.providers=JRE,CLDR không còn khôi phục locale cũ. |
| JDK 23 | Memory-access methods của sun.misc.Unsafe deprecated for removal. | JDK 24+ phát warning runtime khi gọi. |
| JDK 24 | Security Manager bị vô hiệu hóa. | Sandbox hoặc kiểm tra quyền dựa vào Security Manager không còn hiệu lực. |
| JDK 24 | JNI/FFM native access phát warning nếu chưa được cấp quyền. | Ứng dụng cần native access sẽ phải khai báo module được phép; tương lai sẽ bị từ chối mặc định. |
| JDK 24 | ZGC chỉ còn generational mode. | Cấu hình hoặc script còn yêu cầu non-generational ZGC cần được gỡ. |

### Default charset

Trên JDK 17 trở xuống, charset mặc định phụ thuộc môi trường. Từ JDK 18, default charset là UTF-8. Hãy chỉ định charset rõ ràng khi đọc/ghi dữ liệu có định dạng:

~~~java
Files.readString(path, StandardCharsets.UTF_8);
Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

Đối với giao thức hoặc file có encoding cố định, luôn truyền charset rõ ràng thay vì dựa vào Charset.defaultCharset().

### Locale và định dạng ngày/giờ

CLDR là locale data mặc định từ JDK 9; legacy locale provider đã bị loại bỏ từ JDK 23. Nếu ứng dụng phụ thuộc vào chuỗi ngày/tháng, tiền tệ hoặc tên quốc gia chính xác theo từng locale, hãy kiểm thử cả format và parse.

Không dùng chuỗi hiển thị đã format làm định dạng trao đổi giữa hệ thống. Dùng định dạng giao thức cố định, ví dụ ISO-8601 cho ngày/giờ, và locale rõ ràng cho nội dung hiển thị.

## 12. Các API và flag bị deprecated for removal trong JDK 25

Một số mục vẫn có thể chạy nhưng cần được rà soát trước khi nâng cấp:

| API/flag | Trạng thái trong JDK 25 | Hướng xử lý |
| --- | --- | --- |
| **UseCompressedClassPointers** | Deprecated; lựa chọn uncompressed dự kiến bị loại bỏ. | Gỡ cờ + hoặc - khỏi startup options; compressed class pointers đã là mặc định. |
| **java.locale.useOldISOCodes** | Deprecated; đặt true không còn tác dụng. | Gỡ property và cập nhật mã/đầu ra theo mã ISO hiện hành. |
| **DescriptorSupport** XML interchange | Các constructor/method XML và XMLParseException deprecated for removal. | Không dùng XML interchange cũ; nếu cần lưu metadata, chọn định dạng và serializer được ứng dụng quản lý. |
| **Object.finalize()** | Deprecated for removal từ JDK 18; vẫn tồn tại nhưng không nên dùng cho cleanup. | Dùng AutoCloseable và try-with-resources cho resource cần đóng tường minh; Cleaner chỉ là phương án dự phòng. |
| Các lớp **Permission** liên quan Security Manager | Nhiều lớp deprecated for removal. | Rà soát phần code dùng Permission để kiểm soát Security Manager; chuyển chính sách bảo vệ ra ngoài JVM. |
| **-Djdk.lang.Process.launchMechanism=VFORK** trên Linux | Deprecated do rủi ro vốn có. | Dùng cơ chế mặc định dựa trên posix_spawn; chỉ cân nhắc FORK khi có lý do đã kiểm chứng. |

Các permission class được deprecated for removal gồm nhiều lớp trong java.security, java.io, java.net, JMX, JFR và Attach API. Điều này không có nghĩa toàn bộ API JMX, JFR hoặc Attach đã bị xóa; chỉ các lớp/quyền phụ thuộc Security Manager được nêu trong release notes bị đánh dấu.

Không nên tiếp tục cấu hình cờ đã deprecated chỉ vì chúng không gây lỗi ngay. Mỗi cờ như vậy tạo thêm gánh nặng khi nâng JDK tiếp theo.

## 13. Các thay đổi giám sát và JMX

JDK 25 loại bỏ một số JMX system properties rất cũ, vốn chỉ tồn tại để hỗ trợ hành vi tương thích trước đây:

- **jmx.extend.open.types**
- **jmx.invoke.getters**
- **jdk.jmx.mbeans.allowNonPublic**
- **jmx.mxbean.multiname**
- **jmx.tabular.data.hash.map**
- **jmx.remote.x.buffer.size**

Đối với buffer notification từ xa, tên property đúng đã tồn tại từ JDK 6 là **jmx.remote.x.notification.buffer.size**. Gỡ alias cũ và dùng tên đúng.

JDK 25 loại bỏ periodic sampling functionality trong PerfData, bao gồm StatSampler. Flag **-XX:PerfDataSamplingInterval** được đánh dấu obsolete và dự kiến bị xóa trong một release tương lai; không nên mô tả flag này như đã bị xóa hoàn toàn trong JDK 25. Một số **sun.rt._sync*** counters cũng bị xóa. Nếu agent giám sát đọc trực tiếp PerfData hoặc các counter nội bộ này, cập nhật agent.

Các hướng thay thế được duy trì:

- Dùng JMX API chuẩn để đọc heap, runtime và garbage collector metrics.
- Dùng JFR events cho monitor contention và hoạt động JVM chi tiết.
- Dùng Micrometer/metrics endpoint của ứng dụng cho metric nghiệp vụ.

Đối với các monitor counters đã bị xóa, JDK release notes gợi ý các event JFR như **jdk.JavaMonitorEnter**, **jdk.JavaMonitorWait**, **jdk.JavaMonitorNotify**, **jdk.JavaMonitorInflate**, **jdk.JavaMonitorDeflate** và **jdk.JavaMonitorStatistics** tùy chỉ số cần theo dõi.

## 14. Quét API deprecated và API nội bộ trước khi nâng cấp

Không nên chỉ tìm kiếm source code bằng tên API. Dependency bên thứ ba có thể đã biên dịch sẵn và chứa bytecode gọi API cũ.

### 14.1. jdeprscan

jdeprscan quét JAR hoặc class files để tìm lời gọi tới Java SE APIs đã deprecated:

~~~bash
# Liệt kê API deprecated for removal trong Java SE 25
jdeprscan --release 25 --list --for-removal

# Quét JAR của ứng dụng
jdeprscan --release 25 --for-removal build/orders-app.jar

# Quét tất cả deprecated Java SE APIs
jdeprscan --release 25 build/orders-app.jar
~~~

Nếu tool không tìm thấy class dependency, cung cấp classpath bằng --class-path. jdeprscan chỉ báo deprecated APIs thuộc Java SE; nó không quét deprecation của thư viện bên thứ ba.

### 14.2. jdeps

jdeps tìm phụ thuộc tới JDK internal APIs:

~~~bash
jdeps --jdk-internals --recursive build/orders-app.jar
~~~

Để xem dependency modules:

~~~bash
jdeps --list-deps build/orders-app.jar
~~~

Nếu JAR là multi-release JAR, chọn version cần phân tích bằng --multi-release 25.

### 14.3. jnativescan

jnativescan quét native method declarations và restricted method calls:

~~~bash
jnativescan --release 25 --class-path build/orders-app.jar
~~~

Với module path, truyền --module-path và --add-modules. Dùng --print-native-access để lấy danh sách module cần khai báo native access.

### 14.4. Giới hạn của công cụ quét

Không công cụ nào thay thế hoàn toàn test runtime:

- jdeprscan không tìm deprecation trong dependency bên thứ ba.
- jdeps không phát hiện mọi reflection dựa trên chuỗi hoặc mọi đường truy cập được tạo động.
- jnativescan không audit mã native C/C++ và không thể biết mọi đường nạp thư viện động theo cấu hình.
- Công cụ không chứng minh TLS peer, database driver hoặc HSM tương thích với chính sách mới.

Kết hợp quét bytecode, tìm kiếm source, cập nhật dependency và integration test trên JDK đích.

## 15. Kiểm tra dependency và runtime image

Trước khi nâng cấp, lập danh sách:

1. JDK vendor, build, OS và architecture.
2. Framework, application server, JDBC driver, logging provider và agent.
3. JAR có sử dụng reflection hoặc JDK internals.
4. JNI libraries, FFM code, native image/agent và HSM provider.
5. JVM flags, system properties, security properties và environment variables.
6. Runtime image được tạo bằng jlink hoặc jpackage.

Kiểm tra thư viện bằng release notes của chính vendor và phiên bản framework. Đừng giả định một thư viện chạy được trên JDK 21 sẽ tự động chạy đúng trên JDK 25 chỉ vì nó dùng bytecode class file tương thích.

### Kiểm tra jpackage image

Nếu ứng dụng dùng service loader, sau khi tạo runtime image:

~~~bash
java --list-modules
~~~

Kiểm tra provider thực sự được đóng gói và chạy smoke test bằng runtime trong image, không chỉ chạy bằng JDK cài trên máy phát triển. Runtime image có thể thiếu module service provider nếu quên --bind-services.

## 16. Thiết kế kiểm thử tương thích theo thay đổi

Không chỉ chạy unit test tổng quát. Mỗi thay đổi cần có test xác nhận riêng:

| Nhóm thay đổi | Test cần có |
| --- | --- |
| API bị xóa | Compile toàn bộ source và chạy các test khởi tạo UI/driver liên quan. |
| Socket UDP | Kiểm thử tạo socket, gửi/nhận datagram và timeout. |
| File Windows | Test xóa read-only file, path có trailing space và empty pathname trên Windows. |
| Console | Test trong terminal thật, IDE và môi trường không có console. |
| jpackage | Chạy ServiceLoader và kiểm tra module trong runtime image. |
| Security Manager | Test startup script và các thư viện từng kiểm tra permission. |
| Native access | Chạy với --illegal-native-access=deny, cấp quyền module cần thiết và test JNI/FFM. |
| TLS/PKCS11 | Test handshake tới peer thật, certificate chain, provider và thao tác với HSM. |
| Charset/locale | Test file UTF-8, parse/format ngày giờ, số và tiền tệ với locale sản xuất. |
| Unsafe/JDK internals | Chạy test trên JDK đích và kiểm tra warning/inaccessible access. |

### So sánh kết quả trước và sau nâng cấp

Với mỗi test quan trọng, lưu:

- JDK vendor và java -version.
- JVM options đầy đủ.
- Kết quả đầu ra hoặc mã lỗi.
- Warning mới trong stderr.
- Log của TLS, provider, native library và service loader khi liên quan.
- Thời gian khởi động, latency và GC nếu thay đổi có ảnh hưởng hiệu năng.

Một test pass nhưng có warning mới vẫn cần được phân loại. Warning về native access hoặc Unsafe có thể là dấu hiệu một thư viện sẽ bị chặn ở release tương lai.

## 17. Quy trình nâng cấp có kiểm soát

~~~mermaid
flowchart TD
    A["Chốt JDK đích và môi trường"] --> B["Quét API deprecated / JDK internals / native"]
    B --> C["Cập nhật code và dependency"]
    C --> D["Build trên JDK đích"]
    D --> E["Unit + integration tests"]
    E --> F["Test native access deny và TLS/provider"]
    F --> G["Đóng gói runtime image và smoke test"]
    G --> H["Canary / staging"]
    H --> I{"SLO và hành vi đạt?"}
    I -->|Không| J["Khoanh vùng và rollback"]
    I -->|Có| K["Mở rộng rollout"]
    K --> L["Theo dõi warning và deprecation còn lại"]
~~~

### Giai đoạn 1 — Inventory

Thu thập toàn bộ JDK options, property, dependency, module, provider và native library. Lưu cấu hình hiện tại để so sánh.

### Giai đoạn 2 — Static scan

Chạy jdeprscan, jdeps --jdk-internals và jnativescan. Phân loại kết quả theo mức độ:

- Build blocker.
- Runtime failure.
- Warning cần xử lý trước release kế tiếp.
- Internal API workaround cần loại bỏ.

### Giai đoạn 3 — Chuyển đổi

Thay API đã xóa, gỡ flag cũ, cập nhật dependency và thay cách cấp native access. Không gom mọi thay đổi vào một patch lớn nếu có thể tách theo nguyên nhân.

### Giai đoạn 4 — Test trên JDK thật

Dùng đúng vendor/build sẽ triển khai. Chạy test trên hệ điều hành và architecture production; kiểm tra runtime image sau đóng gói.

### Giai đoạn 5 — Canary và rollout

Triển khai một phần traffic, so sánh error rate, latency, heap, GC, TLS failures và log warning. Giữ khả năng quay về JDK/runtime image trước trong thời gian rollout.

## 18. Bảng ưu tiên khi nâng từ JDK cũ lên JDK 25

| Mức ưu tiên | Hạng mục | Lý do |
| --- | --- | --- |
| **P0 — chặn nâng cấp** | Security Manager startup/custom policy; API Java SE đã bị xóa; native access bị deny. | JVM không khởi động hoặc code không thể thực thi. |
| **P1 — kiểm tra sớm** | Reflection vào JDK internals; sun.misc.Unsafe; JNI/FFM; TLS SHA-1; PKCS11 provider. | Có thể gây runtime failure hoặc warning liên quan bảo mật. |
| **P1 — kiểm thử theo nền tảng** | File delete/read-only, trailing-space paths, Console, Swing UI. | Hành vi thay đổi theo OS hoặc desktop runtime. |
| **P1 — packaging** | jpackage service bindings và custom runtime modules. | Ứng dụng đóng gói có thể thiếu provider/module khi chạy độc lập. |
| **P2 — dọn cấu hình** | JMX legacy properties, PerfData sampling, sun.rt._sync* counters, flags deprecated. | Agent hoặc script giám sát có thể không còn số liệu. |
| **P2 — kiểm thử dữ liệu** | UTF-8 default, CLDR locale, mã ISO và format/parse. | Dữ liệu đầu vào/đầu ra có thể khác trước. |
| **P2 — chuẩn bị release sau** | Finalization, permission classes, UseCompressedClassPointers, VFORK. | Chưa phải tất cả đã bị xóa nhưng đang trên lộ trình loại bỏ. |

P0/P1 không có nghĩa mọi ứng dụng đều bị ảnh hưởng. Đây là thứ tự ưu tiên để xác minh dựa trên inventory thực tế.

## 19. Bài tập thực hành

### Bài A — Quét một JAR trước nâng cấp

Chạy jdeprscan --release 25 --for-removal, jdeps --jdk-internals --recursive và jnativescan --release 25. Ghi lại dependency hoặc API cần xử lý.

**Đạt:** phân biệt được ba loại cảnh báo và nêu giới hạn của từng công cụ.

### Bài B — Sửa API bị xóa

Tạo nhánh thử nghiệm có đoạn gọi BasicSliderUI() hoặc SynthLookAndFeel.load(URL). Chuyển sang constructor/overload được hỗ trợ trong Java 25 và chạy test Swing.

**Đạt:** code biên dịch trên JDK 25 và không còn gọi API đã xóa.

### Bài C — Kiểm thử file trên Windows

Tạo file read-only và thử xóa bằng File.delete(). Kiểm tra giá trị trả về, sau đó dùng DosFileAttributeView để bỏ read-only rồi xóa.

**Đạt:** hiểu thay đổi JDK 25 và không phụ thuộc compatibility property lâu dài.

### Bài D — Kiểm thử native access

Dùng một JAR có JNI hoặc FFM. Chạy jnativescan, sau đó chạy ứng dụng với --illegal-native-access=deny và chỉ cấp quyền cho module cần thiết.

**Đạt:** xác định được module cần native access và không bật ALL-UNNAMED nếu không cần.

### Bài E — Kiểm thử runtime image

Đóng gói một ứng dụng dùng ServiceLoader bằng jpackage. So sánh runtime image mặc định với image có --bind-services.

**Đạt:** giải thích được vì sao service provider có thể biến mất trong runtime image JDK 25.

### Bài F — Kiểm tra Security Manager

Tìm code và dependency gọi System.setSecurityManager, AccessController, Policy hoặc Subject.getSubject. Phân loại phần nào chỉ là compatibility wrapper, phần nào từng thực thi sandbox.

**Đạt:** đề xuất được cách thay thế phù hợp; không giả định doPrivileged còn tạo ranh giới bảo mật.

### Bài G — Kiểm thử TLS và provider

Kết nối tới một endpoint test chỉ hỗ trợ SHA-1 TLS handshake hoặc sử dụng PBE qua SunPKCS11. Xác định lỗi trên JDK 25 và đề xuất cập nhật peer/provider.

**Đạt:** hiểu thay đổi mật mã là chính sách bảo mật và không tự động bật lại thuật toán yếu.

## 20. Câu hỏi tự kiểm tra

1. Source compatibility, binary compatibility và behavioral compatibility khác nhau như thế nào?
2. Hai Java SE APIs nào được Oracle liệt kê là bị xóa trong Java 25?
3. Vì sao constructor Socket với stream=false không còn tạo được UDP socket?
4. File.delete() trên Windows thay đổi ra sao với file read-only?
5. Vì sao runtime image từ jpackage có thể thiếu service provider trong JDK 25?
6. Security Manager bị vô hiệu hóa từ JDK nào và System.setSecurityManager() phản ứng ra sao?
7. Khi nào cần --enable-native-access và làm thế nào để tìm module cần quyền?
8. jdeprscan, jdeps và jnativescan tìm những vấn đề khác nhau nào?
9. Vì sao --illegal-access không còn là giải pháp cho strong encapsulation?
10. sun.misc.Unsafe đã bị xóa hoàn toàn trong JDK 25 chưa? Những API nào là hướng thay thế?
11. Vì sao default charset và locale data có thể làm thay đổi dữ liệu đầu ra dù code không đổi?
12. SHA-1 bị vô hiệu hóa trong TLS 1.2 ở phạm vi nào?
13. UseCompressedClassPointers và java.locale.useOldISOCodes đang ở trạng thái nào?
14. Vì sao phải chạy test trên runtime image đã đóng gói thay vì chỉ test bằng JDK cài sẵn?

## 21. Tài liệu tham khảo chính thức

- [Oracle JDK Migration Guide — Release 25](https://docs.oracle.com/en/java/javase/25/migrate/index.html): quy trình nâng cấp và các thay đổi theo release.
- [Removed APIs — Java SE 25](https://docs.oracle.com/en/java/javase/25/migrate/removed-apis.html): danh sách Java SE APIs bị xóa từ JDK 11 đến JDK 25.
- [Removed Tools and Components — JDK 25](https://docs.oracle.com/en/java/javase/25/migrate/removed-tools-and-components.html): tính năng, option, property và tool bị xóa hoặc deprecated.
- [JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html): thay đổi hành vi, API, security provider và tương thích.
- [Security Manager Is Permanently Disabled — Java SE 25](https://docs.oracle.com/en/java/javase/25/security/security-manager-is-permanently-disabled.html): hành vi API sau JEP 486.
- [Migrating from JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): UTF-8 default, CLDR, strong encapsulation, Security Manager, finalization và native access.
- [The jdeprscan Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeprscan.html): quét deprecated Java SE APIs.
- [The jdeps Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html): phân tích dependency và JDK internal APIs.
- [The jnativescan Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jnativescan.html): quét JNI declarations và restricted native methods.
- [Restricted Methods — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/doc-files/RestrictedMethods.html): native access restrictions.
- [Packaging Overview — jpackage](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): runtime image và service bindings.
- [JEP 403 — Strongly Encapsulate JDK Internals by Default](https://openjdk.org/jeps/403): strong encapsulation.
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): lộ trình thay thế finalization.
- [JEP 471 — Deprecate the Memory-Access Methods in sun.misc.Unsafe for Removal](https://openjdk.org/jeps/471): thay thế memory access methods.
- [JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): native access restrictions.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): Security Manager bị vô hiệu hóa.
- [JEP 498 — Warn upon Use of Memory-Access Methods in sun.misc.Unsafe](https://openjdk.org/jeps/498): cảnh báo runtime cho Unsafe memory access.
- [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset.
- [JEP 252 — Use CLDR Locale Data by Default](https://openjdk.org/jeps/252): thay đổi locale data.

**Ghi chú tính hiện hành:** Các ví dụ và danh sách mục tiêu trong bài lấy JDK 25 làm runtime đích. Khi chuyển lên JDK mới hơn, kiểm tra migration guide và release notes của chính release đích vì có thể có thêm API hoặc flag đã bị loại bỏ. Không coi compatibility property, --add-opens, hoặc việc bật lại thuật toán yếu là giải pháp nâng cấp lâu dài.

**Kết quả cần nộp:** bảng inventory API/flag/dependency, output jdeprscan/jdeps/jnativescan, danh sách thay đổi đã sửa, test tương thích theo OS và security provider, kết quả runtime image sau jpackage, cùng quyết định rollout/rollback có bằng chứng. Kết quả cần chứng minh bạn phát hiện được API bị xóa, quyền bị hạn chế và thay đổi hành vi trước khi triển khai JDK 25.
