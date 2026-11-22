# Tra cứu hợp đồng API và phạm vi hỗ trợ theo nền tảng

> **Phạm vi và tính cập nhật (11/2026):** Bài học nằm trong chủ đề Java 14 nhưng sử dụng phương pháp tra cứu vẫn đúng cho Java hiện nay. Java 14 là bản **non-LTS** cũ, không còn là bản phù hợp để chọn cho dự án triển khai mới. Tính đến tháng 11/2026, Oracle công bố Java 27 là release mới nhất và Java 25 là LTS mới nhất. Tài liệu Java 14 chỉ dùng để đối chiếu một yêu cầu tương thích cũ; với sản phẩm hiện tại hãy chọn JDK được nhà cung cấp còn bảo trì và đọc đặc tả của chính release đó.

## 1. Cần tìm được những gì?

Mỗi lần muốn dùng một API Java, người phát triển cần xác minh được:

1. **Hợp đồng API:** Chữ ký phương thức, tham số, giá trị trả về, điều kiện đầu vào, ngoại lệ, hành vi khi gặp trường hợp biên và cam kết về luồng.
2. **Phiên bản:** API được thêm từ release nào, có trong bản Java tối thiểu của sản phẩm không, có bị deprecated/removed hoặc đang ở trạng thái preview không?
3. **Ranh giới nền tảng:** Đây là Java SE chuẩn, API riêng của JDK, Android SDK, Jakarta EE hay thư viện bên thứ ba?
4. **Môi trường đích:** Runtime có module liên quan không? JDK vendor nào? OS và kiến trúc CPU nào được hỗ trợ? Chức năng có phụ thuộc file system, quyền truy cập hoặc native library không?
5. **Bằng chứng:** Tài liệu chính thức của release đích, kết quả biên dịch bằng `--release` và kết quả kiểm thử trên runtime thật.

**IDE gợi ý được một tên phương thức không phải bằng chứng rằng API đó có trong Java 14 hoặc chạy trên mọi nền tảng.**

## 2. Đọc «hợp đồng» trong Javadoc

Hợp đồng API là những hành vi được **đặc tả công khai** và người sử dụng có thể dựa vào. Khi mở trang Javadoc, hãy đọc:

| Mục trong tài liệu | Cần kiểm tra |
| --- | --- |
| **Module / Package / Class / Method** | Đúng module, class và overload (cùng tên nhưng tham số khác nhau có thể có hợp đồng khác nhau). |
| **Signature** | Visibility, static/instance, kiểu tham số, generic, kiểu trả về và ngoại lệ được khai báo. |
| **Description / Parameters / Returns** | Giới hạn đầu vào, xử lý `null`, ý nghĩa kết quả, điều kiện và các đảm bảo cụ thể. |
| **Throws** | Khi nào xảy ra ngoại lệ, ứng dụng cần bắt hay xử lý trường hợp nào. |
| **Since** | API lần đầu xuất hiện ở release nào; mốc này không bảo đảm mọi môi trường đều hỗ trợ hoặc API không thay đổi ở release mới. |
| **Deprecated / forRemoval** | Không nên mặc định sử dụng API cho mã mới; tìm lý do, phiên bản và phương án thay thế hiện hành. |
| **API Note / Implementation Requirements / Implementation Note** | Phân biệt gợi ý sử dụng, yêu cầu đối với mọi implementation và thông tin về cách triển khai cụ thể. |
| **Specified by / Overrides** | Hợp đồng ở interface/superclass mà phương thức phải tuân theo. |

Ví dụ, `Path.of("logs", "app.log")` tạo đối tượng `Path` theo file-system provider; nó **không tạo file** và **không bảo đảm** kết quả dạng chuỗi dùng cùng dấu phân cách trên mọi hệ điều hành. `Files.move(..., ATOMIC_MOVE)` có thể ném `AtomicMoveNotSupportedException` nếu file system không hỗ trợ thao tác nguyên tử. Hai chi tiết này là một phần hợp đồng cần đọc trước khi thiết kế chương trình.

Với cú pháp và ngữ nghĩa ngôn ngữ, dùng **Java Language Specification (JLS)**; với mô hình máy ảo và bytecode, dùng **Java Virtual Machine Specification (JVMS)**; với hành vi API, dùng **Javadoc API Specification**; với `javac`, `jdeps` hoặc `jlink`, dùng **JDK Tool Specifications**. JEP giải thích sự thay đổi và trạng thái một tính năng nhưng không thay thế tài liệu API của bản phát hành cụ thể.

## 3. Phạm vi hỗ trợ có nhiều chiều

| Chiều | Câu hỏi xác minh | Nguồn chính |
| --- | --- | --- |
| Ngôn ngữ / bytecode | Cú pháp và class file có phù hợp bản Java tối thiểu không? | JLS/JVMS, `javac --release`. |
| API Java SE | Class/method có trong Java SE của release đích không? | Javadoc theo release. |
| API riêng của JDK | API nằm trong module `jdk.*` hay đặc thù implementation? | Nhánh JDK của Javadoc, tài liệu vendor. |
| Module runtime | Module cần thiết có trong ảnh runtime được đóng gói không? | `java --list-modules`, `java --describe-module`, cấu hình `jlink`. |
| Vendor và bản cập nhật | JDK binary, security updates và vòng đời hỗ trợ thế nào? | Vendor release notes và support roadmap. |
| OS / CPU | Đúng phiên bản Linux/Windows/macOS, x64/AArch64 có được chứng nhận không? | Certified System Configurations của **đúng vendor + JDK release**. |
| Khả năng môi trường | Có quyền file, thiết bị, GUI, TLS, filesystem features, native libs không? | Javadoc, tài liệu OS/provider và test thực tế. |
| Nền tảng khác | Android/Jakarta EE/dependency có hợp đồng riêng không? | Android API level, Jakarta spec, tài liệu thư viện. |

Java SE cung cấp các module như `java.base`, `java.net.http`, `java.sql`. Bộ JDK còn có các module như `jdk.jdeps`, `jdk.jlink` và các tiện ích khác; module JDK-specific không mặc nhiên thuộc hợp đồng của mọi Java SE implementation. Không suy luận API chỉ từ tên package; xem **module và nhánh Java SE/JDK** của Javadoc.

Khả năng chạy đa nền tảng của bytecode không biến mọi API thành chức năng luôn sẵn có. OS, CPU, container, file-system provider, quyền và module đã đóng gói đều có thể ảnh hưởng hành vi.

## 4. Quy trình tra cứu thực hành

### Bước 1 — Xác định chính xác đích cần hỗ trợ

Ghi rõ Java release tối thiểu, JDK dùng để build, JDK thực tế dùng để chạy, vendor/update, OS/CPU, container và các thư viện phụ thuộc. Chạy:

```bash
java --version
javac --version
javac --help
java --list-modules
```

`java --version` trong terminal có thể khác Java toolchain của Gradle/Maven và khác runtime production. Kiểm tra riêng các môi trường đó. `javac --help` cho biết compiler hiện tại có hỗ trợ release mục tiêu của `--release` hay không.

### Bước 2 — Mở đúng tài liệu API của release

- [Javadoc Java SE 14 / JDK 14](https://docs.oracle.com/en/java/javase/14/docs/api/index.html) — kiểm tra tương thích với Java 14.
- [Javadoc Java SE 25 / JDK 25](https://docs.oracle.com/en/java/javase/25/docs/api/index.html) — một bản LTS hiện hành.
- [Javadoc Java SE 27 / JDK 27](https://docs.oracle.com/en/java/javase/27/docs/api/index.html) — release Java SE mới nhất khi biên soạn.

Tìm **tên đầy đủ** gồm package và method, xác nhận đúng overload, rồi đọc `Since`, `Throws`, điều kiện sử dụng và ghi chú provider. Nếu phải tương thích Java 14 thì bắt buộc đối chiếu với **Javadoc 14**; nếu đang viết ứng dụng mới, dùng tài liệu của JDK mà dự án chọn hiện nay.

### Bước 3 — Xác định tính ổn định và vòng đời

Xem danh sách **Deprecated API**, **Preview API**, **New API** (nếu tài liệu release cung cấp), cùng release notes. Không dựa vào API internal/không export, API thử nghiệm ở bản Java cũ, hay biện pháp lách encapsulation để xây mã production. `@since 11` chỉ nói thời điểm xuất hiện; không chứng minh API chưa bị deprecated và cũng không cam kết hỗ trợ mọi hệ điều hành.

### Bước 4 — Kiểm tra module

Ví dụ `java.net.http.HttpClient` thuộc `java.net.http`:

```bash
java --describe-module java.net.http
java --list-modules
```

Mã modular dùng `module-info.java` cần khai báo `requires java.net.http;` nếu phụ thuộc module này. Với runtime tạo bằng `jlink`, đối chiếu các module thực tế được đưa vào ảnh chạy; JDK đầy đủ trên máy lập trình có thể có nhiều module hơn ứng dụng đóng gói.

### Bước 5 — Đối chiếu OS, CPU và môi trường

Dùng ma trận **certified/supported system configurations** của nhà cung cấp, chọn đúng bản JDK và OS version; ví dụ [Oracle JDK 27 Certified System Configurations](https://www.oracle.com/java/technologies/javase/products-doc-jdk27certconfig.html). Không áp dụng kết luận hỗ trợ của Oracle JDK cho mọi vendor OpenJDK khác. Trong môi trường container còn phải xem base image, libc, filesystem mounts, quyền, network và yêu cầu headless/GUI.

### Bước 6 — Khóa API theo bản Java đích khi biên dịch

Khi compiler hỗ trợ release yêu cầu:

```bash
javac --release 14 PortablePath.java
```

`--release` kiểm tra cú pháp, định dạng class file **và tập API công khai của Java release đích**. Ngược lại, `--source 14 --target 14` trên compiler hiện đại không tự hạn chế việc gọi những API chỉ có ở bản Java mới. Nếu `javac` hiện tại không hỗ trợ `--release 14`, dùng toolchain thích hợp để xác minh tương thích, thay vì bỏ qua bước kiểm tra.

Có thể hỗ trợ việc audit các phụ thuộc bằng:

```bash
jdeps --jdk-internals app.jar
jdeprscan app.jar
```

`jdeps` giúp tìm phụ thuộc vào API nội bộ JDK; `jdeprscan` hỗ trợ rà soát API deprecated. Các lệnh này không thay thế việc biên dịch theo release và kiểm thử chức năng trên môi trường đích.

### Bước 7 — Chạy test trên ma trận cam kết

Chạy CI/integration test với các tổ hợp JDK vendor × update × OS × CPU mà sản phẩm dự định hỗ trợ. Kiểm tra đường dẫn, quyền, filesystem case sensitivity, locale/timezone, TLS, native library, giới hạn bộ nhớ và khả năng chạy không GUI. Ghi tài liệu tham chiếu, ngày tra cứu và kết quả kiểm thử; khi nâng JDK hoặc OS, đánh giá lại phần liên quan.

## 5. Ví dụ 1 — `Path.of`: có trong Java 14 và vẫn hợp lệ

Trang Javadoc Java 14 của `java.nio.file.Path.of(String, String...)` ghi **Since: 11**. API này có trong Java 14 và vẫn hữu ích trong các JDK hiện đại. Nó tạo một đường dẫn trừu tượng từ các thành phần, chưa truy cập hoặc tạo tệp.

Lưu mã trong file `PortablePath.java`:

```java
import java.nio.file.Path;

public class PortablePath {
    public static void main(String[] args) {
        Path file = Path.of("reports", "2026", "summary.txt");
        System.out.println(file.getNameCount());
        System.out.println(file.getFileName());
    }
}
```

```bash
javac --release 14 PortablePath.java
java PortablePath
```

Các lệnh chạy trên JDK compiler hỗ trợ mục tiêu 14. **Stdout chính xác:**

```text
3
summary.txt
```

Có ba thành phần tên; thành phần cuối là `summary.txt`. Nếu in trực tiếp `file`, cách hiển thị dấu phân cách có thể khác giữa provider/OS. Trong Javadoc, đừng bỏ qua `InvalidPathException` và ghi chú cách ghép chuỗi **phụ thuộc provider**. Khi tiếp tục thao tác bằng `Files.*`, kiểm tra thêm ngoại lệ I/O và quyền.

Tài liệu: https://docs.oracle.com/en/java/javase/14/docs/api/java.base/java/nio/file/Path.html

## 6. Ví dụ 2 — `HexFormat`: ổn định hiện nay, không có trong Java 14

`java.util.HexFormat` xuất hiện từ **Java 17**, theo Javadoc (Since: 17). Code này chạy trên Java 17+ phù hợp, nhưng không phải một API có sẵn của Java 14.

File `HexApi.java`:

```java
import java.util.HexFormat;

public class HexApi {
    public static void main(String[] args) {
        byte[] bytes = {0x0A, (byte) 0xFF};
        System.out.println(HexFormat.of().formatHex(bytes));
    }
}
```

```bash
javac --release 17 HexApi.java
java HexApi
```

**Stdout chính xác:**

```text
0aff
```

Nếu compiler hỗ trợ `--release 14`, thử `javac --release 14 HexApi.java` sẽ **báo lỗi** vì không tìm thấy `java.util.HexFormat` trong API Java 14. Đây là cách phát hiện giới hạn tương thích ngay từ lúc biên dịch. Với dự án yêu cầu Java 14, phải dùng giải pháp có sẵn ở bản đích hoặc thay đổi mức phiên bản tối thiểu bằng quyết định kỹ thuật được chấp thuận; không dùng API nội bộ như đường vòng.

Tài liệu: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html

## 7. Ví dụ 3 — Có API nhưng chức năng tùy filesystem

`FileStore.supportsFileAttributeView("posix")` kiểm tra file store hiện tại có hỗ trợ POSIX file attribute view không; câu trả lời phụ thuộc thực tế triển khai, không thể đoán chắc chỉ từ tên hệ điều hành.

File `CapabilityCheck.java`:

```java
import java.io.IOException;
import java.nio.file.FileStore;
import java.nio.file.Files;
import java.nio.file.Path;

public class CapabilityCheck {
    public static void main(String[] args) throws IOException {
        FileStore store = Files.getFileStore(Path.of("."));
        boolean supported = store.supportsFileAttributeView("posix");
        System.out.println(supported);
    }
}
```

```bash
javac --release 17 CapabilityCheck.java
java CapabilityCheck
```

**Stdout có thể là `true` hoặc `false`** tùy file system/provider. Truy vấn file store có thể gặp `IOException`; hỗ trợ attribute view cũng không mặc nhiên cấp quyền thao tác. Không được ghi một giá trị stdout cố định cho ví dụ này.

Tương tự, nếu dùng `Files.move` với `StandardCopyOption.ATOMIC_MOVE`, phải dự kiến `AtomicMoveNotSupportedException` khi hệ thống tệp không cung cấp bảo đảm nguyên tử. Cách đúng là kiểm tra hợp đồng của từng thao tác và xử lý kết quả/ngoại lệ được đặc tả.

## 8. Tránh nhầm Java SE, Android, Jakarta và native platform

**Java SE/JDK:** Tập API Java SE nằm trong các module được đặc tả; công cụ và API trong JDK có phạm vi riêng. Ảnh runtime do `jlink` tạo có thể đã bỏ một số module dù máy build dùng JDK đầy đủ.

**Android:** Phiên bản Java của compiler không đồng nghĩa Android có tất cả class/method thuộc Java SE. Kiểm tra Android API level, `minSdk`, `compileSdk`, core library support và tài liệu từng API: https://developer.android.com/build/jdks.

**Jakarta EE/Spring/dependency khác:** Mỗi framework/thư viện có phiên bản và hợp đồng riêng. Cần xác minh artifact thực tế, phiên bản dependency và runtime container/server phù hợp, thay vì mặc định thư viện đó thuộc JDK.

**OS/CPU/native:** Bytecode thường portable, nhưng JDK binary, JNI/native libraries, headless environment, filesystem, cổng mạng, chứng chỉ và quyền vẫn khác nhau. Chỉ kết luận «được hỗ trợ» cho tổ hợp đã có tài liệu vendor và kiểm thử tương ứng.

## 9. Mẫu ghi quyết định sử dụng API trong review

| Thông tin | Ví dụ cho `Path.of` |
| --- | --- |
| Mục đích | Tạo đường dẫn tương đối theo default filesystem. |
| API và module | `java.nio.file.Path.of(String, String...)` / `java.base`. |
| Hợp đồng | Kết hợp các thành phần đường dẫn; có thể ném `InvalidPathException`; không tạo tệp. |
| Release có API | Java 11+; tài liệu Java 14 xác nhận có mặt. |
| Runtime triển khai | Ghi vendor, bản Java feature/update, OS/CPU thực tế; dùng release còn được bảo trì. |
| Điều kiện nền tảng | Separator/định dạng đường dẫn theo provider; thao tác file phụ thuộc quyền và filesystem. |
| Bằng chứng | Javadoc đúng release, kết quả `--release` và test trên nền tảng cam kết. |

## 10. Những lỗi phổ biến

1. **Tra nhầm Javadoc version:** kết quả tìm kiếm có thể dẫn tới Java 8, 14 hoặc 27; phải đọc tiêu đề release.
2. **Dựa vào `Since` để kết luận chạy được mọi nơi:** mốc giới thiệu API không nói về OS/CPU, quyền hay vendor.
3. **Chỉ đọc signature:** bỏ sót `Throws`, xử lý `null`, trạng thái deprecated và điều kiện provider.
4. **Dùng `--source`/`--target` thay cho `--release`:** có thể vô tình gọi API ra đời sau bản Java tối thiểu.
5. **Thấy code chạy trên máy mình là đủ:** cần thử trên môi trường đích, đặc biệt file system, native code và container.
6. **Coi preview/incubating cũ là hợp đồng ổn định:** chỉ chọn API công khai, được tài liệu bản triển khai hiện hành bảo đảm.
7. **Nhầm Android/Jakarta với Java SE:** phải kiểm tra SDK/framework/dependency theo hợp đồng riêng.
8. **Nhầm «API tồn tại» với «bản Java còn nhận bản vá»:** Java 14 dùng làm mốc tương thích, không phải lựa chọn bảo trì cho dự án mới.

## 11. Tự kiểm tra

**Câu 1.** Product phải hỗ trợ API Java 14, một PR thêm `HexFormat.of()`. Có được merge theo yêu cầu hiện tại không?

**Đáp án:** Không, vì `HexFormat` chỉ xuất hiện từ 17. Cần xác nhận Javadoc, biên dịch `--release 14` và sửa chiến lược API hoặc cập nhật baseline được duyệt.

**Câu 2.** `Files.move(..., ATOMIC_MOVE)` biên dịch nhưng fail trên filesystem không hỗ trợ atomic move. Có mâu thuẫn Java SE không?

**Đáp án:** Không; ngoại lệ `AtomicMoveNotSupportedException` là một phần hợp đồng. Ứng dụng phải xử lý hoặc đề xuất phương án phù hợp.

**Câu 3.** Ứng dụng chạy với JDK đầy đủ nhưng báo thiếu module trong runtime thu gọn.

**Đáp án:** Kiểm tra `java --list-modules`, `module-info.java`, cấu hình `jlink` và phụ thuộc của ứng dụng. Kiểm tra Javadoc chỉ là một bước, chưa chứng minh module có trong ảnh runtime.

**Câu 4.** JDK 25 có class bạn cần. Có nghĩa mọi Android device cũng có class ấy không?

**Đáp án:** Không. Android có API level và bộ core libraries riêng; tra tài liệu Android ở mức API/minSdk mục tiêu.

## 12. Nguồn chính thức

- [Java 14 API Specification](https://docs.oracle.com/en/java/javase/14/docs/api/index.html), [Java 25 API Specification](https://docs.oracle.com/en/java/javase/25/docs/api/index.html), [Java 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/index.html).
- [Java Language & VM Specifications](https://docs.oracle.com/javase/specs/).
- [JDK 27 javac command specification](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html), đặc biệt mục `--release`.
- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) để xem mốc bảo trì theo vendor.
- [Oracle JDK 27 Certified System Configurations](https://www.oracle.com/java/technologies/javase/products-doc-jdk27certconfig.html) để đối chiếu OS/CPU cụ thể.
- [Android: Java versions in Android builds](https://developer.android.com/build/jdks).

**Quy tắc chốt:** Mọi kết luận về hỗ trợ phải kèm **API + hợp đồng + phiên bản Java + nền tảng/vendor + bằng chứng kiểm tra**. Phân biệt rõ khả năng tương thích Java 14 với lựa chọn Java còn được bảo trì ở thời điểm triển khai.