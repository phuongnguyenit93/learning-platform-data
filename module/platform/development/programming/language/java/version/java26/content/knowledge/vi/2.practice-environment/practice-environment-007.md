# Tổ chức ví dụ, tài nguyên, dữ liệu mẫu và lệnh chạy

Một bài thực hành Java chỉ thật sự hữu ích khi người học có thể mở dự án, hiểu ví dụ cần gì, chạy bằng đúng JDK và nhận được kết quả có thể kiểm tra. Nếu chương trình phụ thuộc vào đường dẫn riêng trên máy tác giả, dữ liệu không được cung cấp hoặc cấu hình IDE không được ghi lại, người học rất dễ gặp lỗi môi trường thay vì học được nội dung Java.

Với module Java 26, các ví dụ còn có thể sử dụng tính năng chính thức, preview feature hoặc incubator API. Vì vậy, mỗi ví dụ cần ghi rõ phiên bản JDK, trạng thái tính năng, module và cờ chạy bắt buộc. Cấu trúc dự án tốt giúp ví dụ có thể được chạy lại, kiểm thử và nâng cấp khi JDK thay đổi.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Tổ chức mã nguồn, tài nguyên ứng dụng, dữ liệu mẫu và dữ liệu kiểm thử theo quy ước Java hiện hành.
- Chọn cách đọc tài nguyên phù hợp khi dữ liệu nằm trên classpath hoặc do người dùng cung cấp qua đường dẫn.
- Chuẩn bị dữ liệu mẫu nhỏ, an toàn và có kết quả xác định để người khác chạy lại được.
- Ghi lại JDK, trạng thái preview/incubator, dependency và lệnh chạy của từng ví dụ.
- Dùng Maven Wrapper hoặc Gradle Wrapper để các lệnh build và test nhất quán giữa máy cá nhân và CI.

## 1. Nguyên tắc tổ chức một bộ ví dụ

Mỗi ví dụ nên trả lời được năm câu hỏi trước khi người học chạy:

1. **Ví dụ minh họa điều gì?** Nêu mục tiêu ngắn gọn, đầu vào, đầu ra và phần mã nguồn cần đọc.
2. **Cần môi trường nào?** Ghi phiên bản JDK tối thiểu, JDK dùng để biên dịch, phiên bản build tool và dependency cần thiết.
3. **Tính năng Java đang ở trạng thái nào?** Phân biệt API chính thức với preview feature và incubator API; ghi cờ hoặc module bắt buộc nếu có.
4. **Dữ liệu lấy ở đâu?** Chỉ rõ tài nguyên được đóng gói trong ứng dụng, fixture dùng cho test hay file bên ngoài do người chạy truyền vào.
5. **Chạy và xác nhận kết quả thế nào?** Cung cấp lệnh có thể sao chép, kết quả mong đợi và cách chạy test.

Nên giữ ví dụ nhỏ, tập trung vào một mục tiêu kỹ thuật. Nếu một ví dụ cần dịch vụ ngoài, credential, dữ liệu lớn hoặc cấu hình phức tạp, hãy tách phần chuẩn bị môi trường thành hướng dẫn riêng và cung cấp một đường chạy mẫu cục bộ khi có thể. Không yêu cầu người học sửa mã nguồn chỉ để thay đường dẫn trên máy tác giả.

## 2. Cấu trúc mã nguồn và tài nguyên

Maven và Gradle đều hỗ trợ quy ước thư mục Java phổ biến. Một dự án thực hành đơn giản có thể dùng cấu trúc sau:

```text
java26-practice/
├── README.md
├── .gitignore
├── pom.xml                 # hoặc build.gradle.kts và settings.gradle.kts
├── mvnw                    # Maven Wrapper, nếu dùng Maven
├── mvnw.cmd
├── .mvn/wrapper/
└── src/
    ├── main/
    │   ├── java/
    │   │   └── vn/example/java26/
    │   │       ├── http/
    │   │       ├── pattern/
    │   │       └── concurrency/
    │   └── resources/
    │       ├── data/orders.csv
    │       └── config/example.properties
    └── test/
        ├── java/
        │   └── vn/example/java26/
        └── resources/
            └── fixtures/orders-invalid.csv
```

Các quy ước chính:

- `src/main/java` chứa mã nguồn ứng dụng. Tên package phải khớp với cấu trúc thư mục bên dưới thư mục này.
- `src/main/resources` chứa tài nguyên được đóng gói cùng ứng dụng, chẳng hạn file cấu hình mặc định, JSON hoặc dữ liệu nhỏ dùng để minh họa.
- `src/test/java` chứa kiểm thử tự động.
- `src/test/resources` chứa fixture chỉ phục vụ kiểm thử; chúng không được đóng gói như tài nguyên ứng dụng thông thường.
- `target/` của Maven và `build/` của Gradle là thư mục đầu ra build. Không đặt dữ liệu nguồn hoặc chỉnh sửa thủ công trong các thư mục này.

Nếu dùng một build project cho nhiều ví dụ, đặt mỗi ví dụ trong package riêng, có class chạy riêng và tên dễ nhận biết. Khi các ví dụ cần dependency, cờ preview hoặc module khác nhau, cân nhắc tách thành subproject để cấu hình của ví dụ này không ảnh hưởng ví dụ khác. Một ví dụ dùng incubator API không nên khiến mọi ví dụ cơ bản đều phải thêm module đó khi biên dịch hoặc chạy.

## 3. Phân loại tài nguyên và dữ liệu mẫu

Không phải file nào cũng nên đặt cùng một chỗ. Hãy chọn vị trí theo vòng đời của dữ liệu:

| Loại dữ liệu | Vị trí phù hợp | Cách sử dụng |
|---|---|---|
| Tài nguyên mặc định được phân phối cùng ứng dụng | `src/main/resources` | Đọc từ classpath; dữ liệu thường chỉ đọc |
| Fixture kiểm thử | `src/test/resources` | Test nạp trực tiếp để kiểm tra trường hợp hợp lệ và lỗi |
| File đầu vào do người chạy chọn | Đường dẫn truyền qua tham số dòng lệnh hoặc cấu hình | Dùng `Path` và `Files`; kiểm tra đường dẫn và lỗi đọc file |
| File đầu ra được tạo khi chạy | Thư mục đầu ra được cấu hình hoặc thư mục tạm | Không ghi đè tài nguyên trong classpath hoặc mã nguồn |
| Dữ liệu lớn hoặc có nguồn cấp riêng | Kho lưu trữ được tài liệu hóa hoặc bước chuẩn bị dữ liệu riêng | Ghi nguồn, giấy phép, phiên bản và cách xác minh tính toàn vẹn |

Tài nguyên trong `src/main/resources` thường được đóng gói vào JAR. Khi ứng dụng chạy từ JAR, tài nguyên có thể không còn là một file độc lập trên hệ thống file. Vì thế, không nên tạo `File` hoặc `Path` bằng cách ghép đường dẫn tới `src/main/resources`. Hãy đọc tài nguyên qua classpath.

Ví dụ đọc một file CSV nhỏ được đóng gói trong ứng dụng:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class OrdersExample {
    public static void main(String[] args) throws IOException {
        try (InputStream input = OrdersExample.class
                .getResourceAsStream("/data/orders.csv")) {
            if (input == null) {
                throw new IllegalStateException(
                        "Missing classpath resource: /data/orders.csv");
            }

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(input, StandardCharsets.UTF_8))) {
                reader.lines().forEach(System.out::println);
            }
        }
    }
}
```

Dấu `/` ở đầu đường dẫn chỉ vị trí từ gốc classpath. Nếu bỏ dấu `/`, `Class.getResourceAsStream` sẽ diễn giải đường dẫn tương đối với package của class. Nên dùng đường dẫn tuyệt đối từ classpath trong ví dụ nhập môn để tránh nhầm lẫn. Luôn kiểm tra trường hợp tài nguyên không tồn tại và đóng stream bằng try-with-resources.

Nếu file do người chạy cung cấp, hãy dùng `Path` và `Files` thay vì giả định file nằm trong thư mục làm việc hiện tại:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ExternalFileExample {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: ExternalFileExample <input-file>");
        }

        Path input = Path.of(args[0]).toAbsolutePath().normalize();
        if (!Files.isRegularFile(input) || !Files.isReadable(input)) {
            throw new IllegalArgumentException("Input file is not readable: " + input);
        }

        try (BufferedReader reader = Files.newBufferedReader(
                input, StandardCharsets.UTF_8)) {
            reader.lines().forEach(System.out::println);
        }
    }
}
```

Đây là ví dụ đọc file do người dùng chỉ định. Với ứng dụng xử lý dữ liệu không tin cậy, cần bổ sung giới hạn kích thước, xác thực định dạng và chính sách thư mục được phép truy cập phù hợp với bài toán. Không đưa đường dẫn tuyệt đối của máy tác giả vào mã nguồn hoặc tài liệu.

## 4. Thiết kế dữ liệu mẫu có thể chạy lại

Dữ liệu mẫu tốt giúp người học tập trung vào API đang học. Hãy dùng dữ liệu tổng hợp hoặc dữ liệu công khai có giấy phép rõ ràng; không đưa dữ liệu khách hàng, thông tin cá nhân, token, mật khẩu hay bản sao dữ liệu nội bộ vào repository.

Với CSV, JSON hoặc file văn bản, tài liệu của ví dụ nên mô tả:

- Encoding, ưu tiên UTF-8 và chỉ rõ nếu có BOM.
- Tên trường, kiểu dữ liệu, đơn vị đo, định dạng ngày giờ và quy tắc giá trị rỗng.
- Dấu phân tách, quy tắc escape và việc file có dòng tiêu đề hay không.
- Số dòng mẫu và kết quả mong đợi để người học đối chiếu.
- Nguồn dữ liệu, giấy phép và phiên bản nếu không phải dữ liệu tự tạo.

Giữ fixture nhỏ để người học dễ đọc và test chạy nhanh. Nên có dữ liệu cho trường hợp bình thường, dữ liệu rỗng, thiếu trường, sai định dạng và giá trị biên. Đừng phụ thuộc vào thứ tự file hệ thống trả về hoặc thứ tự phần tử không được API cam kết. Nếu ví dụ dùng số ngẫu nhiên, cố định seed trong bài thực hành để kết quả có thể lặp lại. Nếu dùng ngày giờ, locale hoặc múi giờ, khai báo rõ giá trị được dùng thay vì dựa vào thiết lập máy.

Phân biệt dữ liệu mẫu đóng gói với file đầu vào có thể thay đổi. Tài nguyên classpath nên được coi là chỉ đọc. Nếu ví dụ cần ghi kết quả, hãy ghi vào thư mục do người dùng chỉ định hoặc thư mục tạm; không sửa file trong `src/main/resources` hay `src/test/resources`.

## 5. Tổ chức kiểm thử và đầu ra

Test nên chạy độc lập, không cần gọi mạng hoặc phụ thuộc vào file có sẵn trên máy phát triển. Đặt fixture vào `src/test/resources`, rồi nạp qua classpath tương tự tài nguyên ứng dụng. Với test cần tạo file, dùng thư mục tạm do framework kiểm thử cấp, ví dụ JUnit Jupiter `@TempDir`:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class OutputFileTest {
    @TempDir
    Path tempDir;

    @Test
    void writesResultToTemporaryDirectory() throws IOException {
        Path output = tempDir.resolve("result.txt");
        Files.writeString(output, "completed", StandardCharsets.UTF_8);

        assertTrue(Files.readString(output, StandardCharsets.UTF_8)
                .contains("completed"));
    }
}
```

Không để test ghi vào một file cố định bên trong repository; điều đó dễ gây lỗi khi chạy song song hoặc khi test trước để lại dữ liệu. Với kết quả văn bản cần so sánh, lưu expected output nhỏ và ổn định trong fixture, hoặc kiểm tra các thuộc tính quan trọng thay vì so sánh dữ liệu biến động như timestamp hay thứ tự không xác định.

Nếu ví dụ cần gọi HTTP, database hoặc dịch vụ bên ngoài, hãy phân biệt test đơn vị với kiểm thử tích hợp. Test đơn vị nên dùng dữ liệu giả lập và chạy offline. Kiểm thử tích hợp cần ghi rõ dịch vụ, cấu hình, credential qua biến môi trường và cách khởi động. Không để test mặc định âm thầm gọi endpoint thật khi người học chỉ chạy lệnh test cơ bản.

## 6. Ghi metadata và lệnh chạy cho từng ví dụ

Ở thư mục gốc, `README.md` nên có bảng mục lục các ví dụ và lệnh chung để kiểm tra môi trường. Mỗi ví dụ phức tạp hơn một class đơn giản nên có README riêng với mẫu thông tin sau:

```text
Tên: HTTP client - gửi yêu cầu GET
Mục tiêu: minh họa gửi request và xử lý response
JDK: 26
Release: 26
Trạng thái API: API chính thức / preview / incubator (chọn đúng một)
Preview: không; nếu có, ghi --enable-preview và JDK cần dùng
Module: không; nếu có, ghi module cần thêm
Dependency: liệt kê thư viện và phiên bản
Dữ liệu: src/main/resources/data/request.json
Lệnh chạy: ./gradlew runHttpExample
Kết quả mong đợi: HTTP status và nội dung phản hồi mẫu
Giới hạn: ghi rõ nếu cần mạng hoặc endpoint thử nghiệm
```

Với ví dụ sử dụng preview feature của Java 26, ghi rõ cả bước biên dịch lẫn bước chạy đều cần cấu hình preview và dùng đúng JDK 26. Preview của một phiên bản không phải cam kết tương thích với phiên bản kế tiếp. Với incubator API như Vector API, ghi rõ module cần thiết, ví dụ `jdk.incubator.vector`, và cảnh báo trạng thái incubator của API. Hãy tách các ví dụ này khỏi cấu hình mặc định nếu việc bật cờ hoặc module sẽ ảnh hưởng đến những bài học khác.

Không ghi chung chung "chạy bằng Java mới nhất". Người học cần biết chính xác JDK nào được hỗ trợ và build tool nào được dùng. Khi cập nhật JDK, dependency hoặc trạng thái tính năng, phải cập nhật README và lệnh chạy cùng lúc.

## 7. Dùng Wrapper để lệnh chạy nhất quán

Wrapper giúp dự án cố định phiên bản build tool và cho phép người khác chạy build mà không phải cài Maven hoặc Gradle toàn hệ thống. Commit các file wrapper vào repository; không đưa chúng vào `.gitignore` hoặc yêu cầu người học tự chọn một phiên bản build tool bất kỳ.

Với Maven Wrapper trên Windows:

```powershell
java --version
javac --version
.\mvnw.cmd --version
.\mvnw.cmd clean test
.\mvnw.cmd package
```

Trên macOS hoặc Linux:

```bash
java --version
javac --version
./mvnw --version
./mvnw clean test
./mvnw package
```

Với Gradle Wrapper trên Windows:

```powershell
java --version
javac --version
.\gradlew.bat --version
.\gradlew.bat clean test
```

Trên macOS hoặc Linux:

```bash
java --version
javac --version
./gradlew --version
./gradlew clean test
```

Các lệnh `test` kiểm tra mã nguồn và test theo cấu hình dự án. Để chạy một ví dụ bằng Gradle, có thể khai báo task `JavaExec` riêng để chọn class chính và runtime classpath:

```kotlin
tasks.register<JavaExec>("runHttpExample") {
    group = "application"
    description = "Runs the HTTP client practice example"
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("vn.example.java26.http.HttpClientExample")
}
```

Sau đó chạy `./gradlew runHttpExample` trên macOS/Linux hoặc `.\gradlew.bat runHttpExample` trên Windows. Runtime classpath do Gradle cung cấp bao gồm class đã biên dịch, tài nguyên và dependency runtime. Nếu ví dụ cần tham số, truyền bằng `--args="..."` và ghi rõ cú pháp tham số trong README.

Với Maven, có thể cấu hình một plugin chạy class chính và cố định phiên bản plugin trong `pom.xml`; sau đó ghi lệnh `mvnw` tương ứng vào README. Không dùng lệnh `java -cp target/classes ...` như hướng dẫn chung cho ứng dụng có dependency, vì classpath đó không bao gồm thư viện runtime. Lệnh này chỉ phù hợp với ví dụ độc lập không có dependency ngoài và đã chỉ rõ cách đưa tài nguyên vào classpath.

Wrapper cố định phiên bản Maven hoặc Gradle, nhưng không tự bảo đảm JDK đúng. Hãy khai báo Java toolchain trong build script khi cần cố định JDK biên dịch; đồng thời kiểm tra phiên bản build tool có hỗ trợ JDK 26 theo ma trận tương thích chính thức. Việc chọn JDK chạy Gradle/Maven và việc chọn toolchain biên dịch là hai cấu hình cần được xác minh riêng.

## 8. Quản lý cấu hình, bí mật và file sinh ra

Chỉ đưa cấu hình mặc định không nhạy cảm vào `src/main/resources`. Với thông tin phụ thuộc môi trường như endpoint, token hoặc mật khẩu, đọc từ biến môi trường hoặc cơ chế quản lý bí mật của môi trường triển khai. Có thể cung cấp `.env.example` với tên biến và giá trị giả, nhưng không commit file `.env` chứa bí mật thật.

`.gitignore` cần loại các đầu ra có thể tái tạo như `target/`, `build/`, `out/`, file `.class`, log và file tạm. Giữ lại mã nguồn, fixture, wrapper, cấu hình build và tài liệu cần để tái tạo kết quả. Không bỏ qua toàn bộ thư mục `src` hoặc các file wrapper.

Nếu ví dụ tải dữ liệu từ mạng, ghi URL nguồn, phiên bản dữ liệu, cách tải và cách kiểm tra checksum nếu có. Không khiến bài học cơ bản phụ thuộc vào một URL không ổn định hoặc một dịch vụ có thể ngừng hoạt động. Khi phù hợp, lưu một fixture nhỏ đã được cấp phép để người học vẫn có thể chạy phần xử lý dữ liệu offline.

## 9. Checklist trước khi chia sẻ một ví dụ

- [ ] README mô tả mục tiêu, JDK, trạng thái API, dependency và lệnh chạy.
- [ ] Mã nguồn nằm trong package rõ ràng; tài nguyên và fixture ở đúng source set.
- [ ] Không có đường dẫn tuyệt đối, credential hoặc dữ liệu cá nhân trong repository.
- [ ] Encoding, schema và kết quả mong đợi của dữ liệu mẫu đã được mô tả.
- [ ] Tài nguyên classpath được đọc bằng API classpath; file bên ngoài được đọc bằng `Path`/`Files`.
- [ ] File sinh ra nằm trong thư mục đầu ra hoặc thư mục tạm, không ghi vào source tree.
- [ ] Test có thể chạy lặp lại và không cần mạng nếu đó không phải mục tiêu của bài.
- [ ] Wrapper và phiên bản plugin/build tool được cố định; JDK toolchain được ghi rõ.
- [ ] Preview feature hoặc incubator module được cô lập và có lệnh biên dịch/chạy tương ứng.
- [ ] Các lệnh trong README đã được kiểm tra trên hệ điều hành được tuyên bố hỗ trợ.

## 10. Bài tập thực hành

Bạn cần chuẩn bị một ví dụ Java 26 đọc danh sách đơn hàng từ CSV, in tổng số đơn và ghi kết quả ra file. Một bài học khác trong cùng repository minh họa HTTP Client; một ví dụ thử nghiệm khác dùng preview feature.

**Yêu cầu:**

1. Tạo cấu trúc thư mục tách mã nguồn, tài nguyên ứng dụng, test và fixture kiểm thử.
2. Đặt một CSV nhỏ với dữ liệu tổng hợp trong `src/main/resources/data/` và mô tả schema, encoding, đơn vị tiền tệ.
3. Đọc CSV từ classpath bằng `getResourceAsStream`; không tham chiếu trực tiếp tới `src/main/resources`.
4. Ghi kết quả vào đường dẫn đầu ra do người chạy truyền vào hoặc thư mục tạm trong test.
5. Viết test cho file hợp lệ và file sai định dạng; dùng fixture riêng trong `src/test/resources`.
6. Viết README gồm JDK yêu cầu, trạng thái API, dependency, lệnh test và lệnh chạy trên Windows cùng macOS/Linux.
7. Đề xuất cách cô lập ví dụ preview để bài CSV và HTTP Client không cần bật preview.

**Kết quả mong đợi:**

- Tài nguyên CSV được nạp từ classpath nên chương trình vẫn đọc được khi đóng gói vào JAR.
- Test dùng fixture riêng, chạy offline và không phụ thuộc file còn sót lại từ lần chạy trước.
- File đầu ra không được ghi đè vào thư mục mã nguồn hoặc tài nguyên.
- README cho phép người khác kiểm tra JDK và chạy lại ví dụ bằng wrapper.
- Ví dụ preview có metadata và cấu hình riêng, dùng đúng JDK của preview; các ví dụ API chính thức không phải nhận thêm cờ preview.

## Tài liệu tham khảo

- [Class — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): API lấy tài nguyên qua classpath.
- [Files — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/file/Files.html): API đọc và ghi file trên hệ thống file.
- [Standard Directory Layout — Maven](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html): quy ước thư mục mã nguồn, tài nguyên và kiểm thử.
- [The Application Plugin — Gradle](https://docs.gradle.org/current/userguide/application_plugin.html) và [Java Plugin — Gradle](https://docs.gradle.org/current/userguide/java_plugin.html): source set, runtime classpath và task chạy ứng dụng Java.
- [Gradle Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): lựa chọn JDK dùng để biên dịch và kiểm thử.
- [Maven Wrapper](https://maven.apache.org/wrapper/) và [Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): cố định phiên bản build tool và chạy lệnh qua wrapper.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): tổ chức test, resource và thư mục tạm với JUnit Jupiter.
