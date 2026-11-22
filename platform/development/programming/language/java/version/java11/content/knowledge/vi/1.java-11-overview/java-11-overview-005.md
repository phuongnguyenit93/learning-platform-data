# Thực hành trên JDK được hỗ trợ thay vì phụ thuộc runtime cũ

> **Ngữ cảnh Java 11 — định hướng thực hành hiện nay.** Học cú pháp và API đã có từ Java 11 không có nghĩa phải cài và triển khai một bản runtime Java 11 đã ngừng nhận bản vá từ nhà cung cấp. Hãy tách **mức tương thích của mã nguồn** khỏi **phiên bản JDK/JVM đang vận hành**, sau đó chọn bản JDK còn được bảo trì cho môi trường thực tế.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Phân biệt JDK dùng để **biên dịch**, mức Java được **nhắm tới**, và JVM dùng để **chạy**.
2. Chọn một bản JDK có cập nhật bảo mật và vòng đời hỗ trợ rõ ràng thay vì phụ thuộc bản cài đặt cũ trên máy.
3. Biên dịch một chương trình sử dụng **API Java 11** bằng một **JDK hiện đại**, chạy và đối chiếu đầu ra.
4. Hiểu giới hạn của `javac --release 11` và kiểm tra tương thích thực tế trước khi đổi runtime sản xuất.
5. Đưa các bước kiểm tra phiên bản, phụ thuộc và kiểm thử vào quy trình phát triển/CI.

## 2. Chọn JDK theo vòng đời hỗ trợ, không chỉ theo số phiên bản

**Tại thời điểm cập nhật 07/11/2026:**

| Nhánh Java | Vai trò thực tế |
| --- | --- |
| **JDK 25 (LTS)** | Lựa chọn mặc định hợp lý cho bài thực hành mới và nhiều ứng dụng cần vòng đời dài; chọn bản cập nhật bảo mật mới nhất của nhà cung cấp. |
| **JDK 21 (LTS)** | Vẫn là lựa chọn cho hệ thống có chuỗi thư viện/công cụ đã kiểm chứng; xác nhận chính sách cập nhật và giấy phép của bản phân phối cụ thể. |
| **JDK 27 (non-LTS)** | Nhánh tính năng mới phát hành tháng 9/2026; phù hợp khám phá, thử nghiệm hoặc tổ chức chủ động nâng cấp theo chu kỳ ngắn. |
| **JDK 11 (LTS)** | Vẫn có các kênh hỗ trợ từ một số nhà cung cấp. Chỉ giữ runtime 11 nếu hợp đồng hỗ trợ, bản vá, ràng buộc sản phẩm hoặc yêu cầu tương thích thực sự cần đến; tránh dùng bản 11 cũ, không được vá, chỉ vì giáo trình đặt tên Java 11. |

**“Được hỗ trợ” phải được đánh giá theo bộ bốn:** phiên bản JDK **+ nhà cung cấp/bản phân phối + hệ điều hành/kiến trúc + ngày kết thúc hỗ trợ**. Chữ “LTS” một mình không bảo đảm bản cài đặt cụ thể vẫn nhận vá lỗi. Các bản phân phối phổ biến gồm Eclipse Temurin, Microsoft Build of OpenJDK, Amazon Corretto và Oracle JDK; xem lịch cập nhật, điều kiện sử dụng và phạm vi hỗ trợ **của chính bản phân phối được chọn**.

Trong bài này, **giả sử dùng JDK 25 LTS đã cập nhật** để học các tính năng ổn định của Java 11. Nếu dự án đã chuẩn hóa trên JDK 21 LTS và còn nhận cập nhật thì có thể thực hành trên JDK 21 với cùng mã nguồn. Không cần một runtime quá cũ chỉ để minh họa Java 11.

### Ba khái niệm dễ bị nhầm

- **JDK biên dịch:** chương trình `javac` và bộ công cụ phát triển đang được gọi, ví dụ JDK 25.
- **Mức tương thích mã:** quy tắc ngôn ngữ, tập API Java SE và định dạng bytecode mục tiêu, ví dụ `--release 11`.
- **JVM chạy:** chương trình `java` thật sự khởi động ứng dụng, ví dụ JVM 25 trên máy phát triển và trong môi trường triển khai.

Ví dụ: **JDK 25 biên dịch mã ở mức Java 11 rồi JVM 25 chạy** là quy trình hợp lệ. Trái lại, biên dịch bằng JDK 25 mà không đặt mức tương thích có thể tạo class file không chạy được trên JVM 11. Việc chọn mức biên dịch và việc chọn runtime có mục tiêu khác nhau.

## 3. Chuẩn bị và xác nhận bộ công cụ

Cài một **bản JDK được nhà cung cấp duy trì** tương thích với hệ điều hành, cấu hình `JAVA_HOME` đến thư mục JDK và để `PATH` ưu tiên thư mục `bin` của JDK đó. Mở terminal mới rồi chạy:

```text
java --version
javac --version
javac --help
```

- `java --version` xác nhận **runtime** được gọi; `javac --version` xác nhận **compiler**. Nếu chúng trỏ đến các bản khác nhau, kiểm tra `JAVA_HOME`, `PATH` và cấu hình IDE/build tool.
- Trong `javac --help`, kiểm tra `--release` và các giá trị release mà compiler đang dùng hỗ trợ. **Không giả định** mọi JDK trong tương lai đều giữ mọi mức đích cũ.
- Trên Windows, `where.exe java` và `where.exe javac` cho biết đường dẫn thực tế. Trên macOS/Linux, dùng `command -v java` và `command -v javac`.
- Với Maven/Gradle/IDE, xác nhận thêm **JDK mà công cụ build sử dụng**; IDE có thể chạy compiler khác terminal. Cần phiên bản Maven/Gradle/plugin thực sự hỗ trợ JDK đã chọn.

**Mẹo vận hành:** ghi lại **nhà cung cấp, phiên bản đầy đủ (gồm update/build), hệ điều hành và ngày kiểm tra** trong tài liệu dự án hoặc log CI. Hai máy cùng báo “Java 25” vẫn có thể ở các mức vá bảo mật khác nhau.

## 4. Bài thực hành hoàn chỉnh: biên dịch ở mức Java 11, chạy trên JDK được hỗ trợ

Tạo tệp **`SupportedJdkLab.java`** với nội dung sau. Đây là chương trình độc lập, không cần thư viện bên ngoài hay truy cập mạng.

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class SupportedJdkLab {
    public static void main(String[] args) throws Exception {
        String raw = "  Java 11  ";
        String clean = raw.strip();

        System.out.println("Blank: " + " \t ".isBlank());
        System.out.println("Text: " + clean);

        Path temp = Files.createTempFile("supported-jdk-", ".txt");
        try {
            Files.writeString(temp, clean.repeat(2), StandardCharsets.UTF_8);
            System.out.println("Read: " +
                    Files.readString(temp, StandardCharsets.UTF_8));
        } finally {
            Files.deleteIfExists(temp);
        }
    }
}
```

Mở terminal ở thư mục chứa tệp, dùng **JDK 25 LTS** (hoặc JDK khác đang được hỗ trợ và chấp nhận mức đích 11):

```sh
mkdir out
javac --release 11 -d out SupportedJdkLab.java
java -cp out SupportedJdkLab
```

**Kết quả chuẩn** (không phụ thuộc tên tệp tạm vì chương trình không in đường dẫn):

```text
Blank: true
Text: Java 11
Read: Java 11Java 11
```

**Giải thích từng điểm quan sát được:**

1. `strip()` loại khoảng trắng đầu/cuối theo cách xác định whitespace của Java; `isBlank()` trả về `true` cho chuỗi chỉ chứa khoảng trắng. Hai phương thức này có từ **Java 11**.
2. `repeat(2)` nhân đôi nội dung chuỗi. Đây cũng là API có từ **Java 11**.
3. `Files.writeString` và `Files.readString` là API Java 11 dùng để ghi/đọc văn bản gọn gàng; ví dụ chỉ rõ `StandardCharsets.UTF_8` để tránh phụ thuộc charset mặc định của máy.
4. `Files.createTempFile` tạo tệp tạm; khối `finally` xóa tệp dù thao tác đọc/ghi ném lỗi. Mẫu đơn giản này đủ để kiểm tra API, xử lý I/O và cleanup; ứng dụng thật thường bắt `IOException` phù hợp thay vì khai báo `throws Exception` ở `main`.
5. `--release 11` yêu cầu compiler áp dụng **quy tắc cú pháp Java 11**, chỉ cho dùng **API được cung cấp cho release 11**, và sinh **class file Java 11**. Vì vậy, chương trình tập trung vào kiến thức Java 11 dù đang chạy trên JVM 25.

Để quan sát định dạng class file, chạy:

```sh
javap -verbose -classpath out SupportedJdkLab
```

Tìm dòng **`major version: 55`** trong đầu ra. Class-file version **55** tương ứng Java 11. `javap` in thêm nhiều thông tin khác nên không cần đối chiếu toàn bộ đầu ra.

### Điều gì sẽ xảy ra nếu bỏ `--release 11`?

Với compiler JDK 25, lệnh `javac -d out SupportedJdkLab.java` mặc định biên dịch theo release hiện tại của compiler. Vì thế class file và các API được phép sử dụng có thể đòi hỏi JVM mới hơn Java 11. Chỉ bỏ `--release` khi **mục tiêu triển khai** và toàn bộ pipeline đã thống nhất hỗ trợ mức Java mới đó.

Nếu phải hỗ trợ **runtime Java 11 thực tế**, hãy giữ `--release 11` **và** chạy bài kiểm thử trên bản Java 11 **được nhà cung cấp còn duy trì**. Biên dịch thành công không tự chứng minh thư viện ngoài, cấu hình TLS, phản chiếu (reflection), native library và hành vi runtime tương thích trên mọi JVM.

## 5. Bài học chuyển thành quy trình cho dự án thật

### Tình huống A — Viết nội dung Java 11 nhưng triển khai mới

- Chọn runtime sản xuất là một **JDK LTS được bảo trì**, ưu tiên nhánh đã được tổ chức kiểm chứng và nhận bản vá.
- Dùng **API Java 11 vẫn hoạt động tốt** để học: `String.isBlank`, `String.strip`, `String.repeat`, `Files.readString`, `Files.writeString`, `java.net.http.HttpClient`, `var` trong phạm vi được Java 11 cho phép.
- Nếu bài tập phải chứng minh đúng cú pháp/API Java 11, cố định `--release 11` và lưu bằng chứng compile/test. Nếu dự án thật chỉ phục vụ runtime JDK 25, có thể đặt mức release 25 sau khi thống nhất chiến lược sản phẩm.
- Sử dụng dependencies, plugin build và IDE có bản cập nhật tương thích JDK đang chọn.

### Tình huống B — Chuyển hệ thống hiện chạy Java 11 sang JDK mới

1. **Kiểm kê hiện trạng:** ghi JDK vendor/build, OS, JVM flags, thư viện, framework, công cụ build, cấu hình container và môi trường CI.
2. **Chọn bản đích còn hỗ trợ:** ví dụ JDK 25 LTS, xác nhận release notes, điều kiện sử dụng và chu kỳ vá của nhà cung cấp. Chốt một **phiên bản cập nhật cụ thể** cho mọi môi trường; đừng dùng thẻ container trôi nổi không có quy trình kiểm soát.
3. **Chạy ứng dụng và bộ test hiện tại trên JDK đích trước khi refactor hàng loạt.** Nhiều mã Java 11 dùng API chuẩn vẫn hoạt động; lấy lỗi thực tế làm đầu vào xử lý.
4. **Nâng phiên bản dependencies/build plugins** tương thích runtime đích. Khi có lỗi liên quan JDK internals, ưu tiên API công khai hoặc bản thư viện đã sửa.
5. **Kiểm tra tương thích hành vi:** encoding/Unicode, múi giờ/locale, TLS/chứng chỉ, phản chiếu, serialization, kết nối CSDL, native code, quản lý bộ nhớ, container limits và hiệu năng.
6. **Kiểm thử ở đúng môi trường triển khai:** CI, staging rồi production với monitoring, rollback và kế hoạch vá JDK định kỳ. Ghi lại bằng chứng thay vì chỉ nhìn thấy dòng “Build successful”.

Công cụ `jdeps` giúp phát hiện một phần phụ thuộc vào JDK internal APIs trong tệp class/JAR. Với một JAR ứng dụng thực tế:

```sh
jdeps --jdk-internals app.jar
```

Đổi `app.jar` thành đường dẫn JAR thực tế của bạn. Nếu có phụ thuộc nội bộ, xử lý ở mã hoặc thư viện sở hữu phụ thuộc đó. `jdeps` là **phân tích tĩnh** nên có thể không phát hiện mọi truy cập bằng reflection. Nó bổ sung, không thay thế, kiểm thử chạy thật.

**Lỗi đáng kiểm tra khi đổi JDK:**

| Dấu hiệu | Nguyên nhân thường gặp | Hướng xử lý hiện hành |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Class được biên dịch cho release mới hơn JVM đang chạy. | Xác định JVM thật sự chạy, class-file version và mức `--release`; thống nhất pipeline với runtime được hỗ trợ. |
| `NoSuchMethodError` hoặc `ClassNotFoundException` | Phiên bản thư viện/runtime classpath lệch nhau hoặc thiếu dependency. | Kiểm tra cây phụ thuộc và runtime classpath/module path; dùng bộ thư viện tương thích. |
| `InaccessibleObjectException` | Thư viện reflection truy cập thành phần JDK bị đóng gói chặt trên JDK hiện đại. | Nâng thư viện hoặc thay cách truy cập bằng API công khai. Chỉ xem `--add-opens` như biện pháp chuyển tiếp có kiểm soát. |
| Lỗi ký tự, thời gian, TLS khi đổi JVM | Khác biệt cấu hình charset, locale, timezone, chứng chỉ hoặc thuật toán bảo mật. | Chỉ định UTF-8 khi cần, kiểm tra cấu hình tường minh, chạy kiểm thử hội nhập trên runtime đích. |
| `javac: command not found` hoặc bản `java`/`javac` không khớp | `PATH`/`JAVA_HOME` trỏ sai hoặc mới có runtime mà chưa có bộ biên dịch. | Cài và chọn đúng JDK, kiểm tra đường dẫn và cấu hình toolchain. |

Không coi các flag mở quyền truy cập nội bộ hay một runtime image tự tạo từ nhiều năm trước là giải pháp bảo trì lâu dài. Nếu đóng gói runtime riêng bằng `jlink`/`jpackage`, hãy **xây lại và phát hành lại từ JDK đã cập nhật** theo quy trình vá lỗi; runtime đã đóng gói không tự nhận bản vá chỉ vì máy build được cập nhật.

## 6. Kiểm tra tự thực hành

**Bài tập 1 — Xác minh môi trường.** Ghi kết quả `java --version`, `javac --version`, đường dẫn hai executable và vendor/update build. Đối chiếu với chính sách hỗ trợ của vendor. Trả lời: hai lệnh có đang dùng cùng dòng JDK không?

**Bài tập 2 — Giữ phạm vi Java 11.** Biên dịch và chạy `SupportedJdkLab.java` bằng `--release 11`. Đối chiếu ba dòng stdout với phần 4 và xác nhận class file có `major version: 55`. Giải thích tại sao kết quả này không yêu cầu runtime 11.

**Bài tập 3 — Chứng minh ranh giới API.** Thử thêm lời gọi `"x".indent(2)` vào chương trình: đây là phương thức xuất hiện **sau Java 11**, nên khi biên dịch với `--release 11` compiler phải từ chối. Gỡ thay đổi này để khôi phục bài chạy được. Không tắt `--release` chỉ để vượt qua lỗi: chọn mức Java theo yêu cầu tương thích trước.

**Bài tập 4 — Lập kế hoạch môi trường.** Nếu sản phẩm bắt buộc chạy trên JVM 11, mô tả bản phân phối JDK 11 còn được vá, cách kiểm thử trên JVM 11 và lịch nâng cấp. Nếu sản phẩm mới chạy JDK 25, mô tả vì sao vẫn có thể học API Java 11 nhưng chọn runtime 25 khi triển khai.

### Tiêu chí hoàn thành

- [ ] Đã xác nhận bản JDK cụ thể còn được cập nhật và đủ quyền sử dụng theo chính sách nhà cung cấp.
- [ ] `java`, `javac` và công cụ build dùng các JDK đã xác định.
- [ ] Mã ví dụ biên dịch với `--release 11`, cho đúng stdout và được kiểm tra class-file version.
- [ ] Đã phân biệt **Java 11 API** với **JVM 11**; không mặc định hai thứ phải cùng phiên bản.
- [ ] Có kế hoạch kiểm thử dependencies và runtime thật nếu nâng JDK của một hệ thống đang chạy.

## 7. Tài liệu kiểm chứng và theo dõi cập nhật

- [Oracle Java SE Support Roadmap](https://www.oracle.com/java/technologies/java-se-support-roadmap.html) — danh sách nhánh LTS, lịch hỗ trợ theo sản phẩm Oracle và các lưu ý về giấy phép.
- [Thông báo phát hành JDK 27 (15/09/2026)](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/) — bối cảnh nhánh tính năng hiện tại.
- [Oracle javac command reference](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html) — ý nghĩa của `--release` và các lựa chọn biên dịch.
- [Java SE 11: String API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html) và [Files API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/nio/file/Files.html) — API dùng trong chương trình.
- [Oracle JDK 25 Migration Guide](https://docs.oracle.com/en/java/javase/25/migrate/index.html) — chuẩn bị chuyển JDK, phân tích phụ thuộc và thay đổi runtime.

**Nguyên tắc áp dụng về lâu dài:** giữ nội dung học Java 11 ở **mức cú pháp/API Java 11** khi mục tiêu bài học yêu cầu; sử dụng **JDK/JVM được cập nhật, kiểm thử và có chính sách hỗ trợ rõ ràng** để phát triển và triển khai. Đánh giá lại số phiên bản và vòng đời khi cập nhật môi trường, thay vì mặc định một release sẽ được hỗ trợ mãi mãi.