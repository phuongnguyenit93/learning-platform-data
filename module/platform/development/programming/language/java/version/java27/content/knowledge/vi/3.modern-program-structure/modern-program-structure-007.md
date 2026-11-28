# Đọc lỗi biên dịch, stack trace và gỡ lỗi bằng IDE

Khi phát triển chương trình Java 27, bạn sẽ thường gặp ba tình huống: mã nguồn không biên dịch được, chương trình phát sinh exception khi chạy, hoặc chương trình chạy bình thường nhưng cho kết quả sai. Mỗi tình huống cần một cách điều tra khác nhau. Biết đọc thông báo của trình biên dịch, lần theo stack trace và điều khiển chương trình bằng debugger giúp bạn tìm đúng nguyên nhân thay vì sửa thử nhiều dòng mã.

Bài viết này trình bày quy trình thực hành với JDK 27 và các IDE có hỗ trợ Java hiện nay, tập trung vào IntelliJ IDEA và Visual Studio Code. Tên menu, phím tắt và một số khả năng có thể thay đổi theo phiên bản IDE, extension và keymap đang sử dụng.

## 1. Phân biệt lỗi biên dịch, lỗi khi chạy và lỗi logic

Trước khi điều tra, hãy xác định chương trình đang thất bại ở giai đoạn nào.

| Loại vấn đề | Thời điểm xuất hiện | Dấu hiệu thường gặp | Cách bắt đầu xử lý |
|---|---|---|---|
| Lỗi biên dịch (*compile-time error*) | Khi trình biên dịch kiểm tra mã nguồn | `error:`, `cannot find symbol`, `incompatible types`, lỗi cú pháp | Đọc chẩn đoán đầu tiên, mở đúng file và dòng được chỉ ra, kiểm tra kiểu dữ liệu, tên và cấu trúc câu lệnh |
| Lỗi khi chạy (*runtime failure*) | Sau khi chương trình đã biên dịch và bắt đầu thực thi | Exception hoặc Error cùng stack trace | Đọc loại exception và thông điệp, lần theo các stack frame và phần `Caused by` |
| Lỗi logic (*logic bug*) | Chương trình vẫn chạy nhưng kết quả hoặc trạng thái sai | Không nhất thiết có thông báo lỗi hay stack trace | Tạo lại tình huống, đặt breakpoint trước khi kết quả sai, theo dõi giá trị qua từng bước |

Một lỗi biên dịch có thể ngăn chương trình khởi chạy. Một exception có thể làm một luồng hoặc toàn bộ ứng dụng dừng lại nếu không được xử lý. Lỗi logic thường khó nhận biết hơn vì chương trình vẫn có thể kết thúc với mã thoát thành công.

## 2. Đọc thông báo lỗi của trình biên dịch Java

`javac` đọc mã nguồn Java và biên dịch thành các class file chạy trên JVM. Khi có lỗi, compiler thường chỉ ra file, số dòng, loại lỗi và vị trí gần đúng trong câu lệnh.

Ví dụ, file `Price.java` có nội dung:

```java
public class Price {
    public static void main(String[] args) {
        int quantity = "3";
        System.out.println(quantity);
    }
}
```

Khi biên dịch, bạn sẽ nhận được chẩn đoán tương tự:

```text
Price.java:3: error: incompatible types: String cannot be converted to int
        int quantity = "3";
                       ^^^
1 error
```

Đọc thông báo theo thứ tự sau:

1. `Price.java:3` cho biết file và dòng cần xem.
2. `error` cho biết đây là lỗi khiến quá trình biên dịch không thể hoàn tất.
3. `incompatible types` mô tả nhóm vấn đề: kiểu biểu thức ở vế phải không thể gán cho biến `int`.
4. Dấu `^` đánh dấu vị trí compiler muốn bạn chú ý. Nó giúp khoanh vùng, nhưng nguyên nhân đôi khi nằm ở biểu thức hoặc khai báo ở dòng trước.

Sửa bằng cách chuyển chuỗi thành số một cách có chủ đích:

```java
public class Price {
    public static void main(String[] args) {
        int quantity = Integer.parseInt("3");
        System.out.println(quantity);
    }
}
```

Nếu dữ liệu đến từ người dùng hoặc nguồn bên ngoài, hãy kiểm tra trường hợp chuỗi không phải số. `Integer.parseInt` có thể ném `NumberFormatException`; việc biên dịch thành công không bảo đảm dữ liệu đầu vào hợp lệ.

### Những dạng chẩn đoán thường gặp

| Thông báo | Ý nghĩa | Hướng kiểm tra |
|---|---|---|
| `';' expected` hoặc `')' expected` | Thiếu dấu kết thúc hoặc dấu đóng mà cú pháp yêu cầu | Kiểm tra dòng được chỉ ra và biểu thức ngay trước đó |
| `cannot find symbol` | Tên biến, phương thức, lớp hoặc thành viên không được tìm thấy trong phạm vi hiện tại | Kiểm tra chính tả, khai báo, import, phạm vi truy cập và dependency |
| `incompatible types` | Giá trị không thể gán hoặc truyền vào tham số có kiểu yêu cầu | Kiểm tra kiểu thực tế, kiểu khai báo và phép chuyển đổi |
| `method ... cannot be applied to given types` | Không có overload phù hợp với số lượng hoặc kiểu đối số đã truyền | Đối chiếu chữ ký phương thức và kiểu từng đối số |
| `unreported exception ... must be caught or declared to be thrown` | Checked exception chưa được xử lý hoặc khai báo trong `throws` | Quyết định xử lý tại chỗ hay chuyển trách nhiệm cho caller |
| `package ... does not exist` | Compiler không tìm thấy package hoặc module cần thiết | Kiểm tra dependency, class path, module path và cấu hình build |
| `duplicate class` | Có định nghĩa lớp trùng tên đầy đủ trong phạm vi biên dịch | Kiểm tra source set, package và file được đưa vào build |

Không nên chỉ sửa đúng ký tự được đánh dấu mà bỏ qua thông điệp. Chẳng hạn, một dấu ngoặc bị thiếu có thể khiến compiler báo thêm nhiều lỗi ở các dòng phía sau. Hãy xử lý lỗi cấu trúc đầu tiên rồi biên dịch lại để xem những lỗi còn lại có thực sự tồn tại hay không.

### Phân biệt error và warning

- **Error**: compiler không thể tạo kết quả biên dịch hợp lệ cho phần mã liên quan.
- **Warning**: compiler phát hiện cách sử dụng có khả năng gây vấn đề; mặc định cảnh báo không ngăn biên dịch hoàn tất, trừ khi build bật tùy chọn như `-Werror`.
- **Note**: thông tin bổ sung, chẳng hạn compiler cho biết một số thao tác có sử dụng API deprecated hoặc unchecked.

Warning vẫn cần được xem xét. Một cảnh báo về phép ép kiểu không an toàn, API deprecated hoặc thao tác với generic có thể báo trước lỗi khó tìm khi chạy. Không nên tắt toàn bộ cảnh báo chỉ để làm output sạch hơn.

## 3. Dùng javac để nhận chẩn đoán rõ hơn

Trong ví dụ nhỏ, bạn có thể gọi trực tiếp compiler từ terminal. JDK 27 cung cấp các tùy chọn hữu ích sau:

| Tùy chọn | Tác dụng |
|---|---|
| `--release 27` | Biên dịch theo quy tắc ngôn ngữ và API của Java SE 27, đồng thời tạo class file hướng tới release đó |
| `-Xdiags:verbose` | Chọn chế độ chẩn đoán chi tiết của compiler |
| `-Xlint:all` | Bật các nhóm lint warning |
| `-g` | Sinh đầy đủ thông tin debug, bao gồm thông tin biến cục bộ |
| `-d out` | Đặt class file được tạo vào thư mục `out` |

Ví dụ:

```bash
javac --release 27 -Xdiags:verbose -Xlint:all -g -d out src/Price.java
```

Sau khi biên dịch, nếu không có lỗi, class file được đặt trong thư mục output. Có thể chạy chương trình bằng class path tương ứng, ví dụ:

```bash
java -cp out Price
```

`--release 27` đặc biệt hữu ích khi JDK dùng để biên dịch và phiên bản Java mục tiêu của dự án cần được xác định rõ. Không ghép `--release` với `--source` hoặc `--target` trong cùng lệnh; các tùy chọn đó không được dùng đồng thời theo quy định của `javac`.

Theo mặc định, `javac` tạo thông tin số dòng và tên file nguồn để hỗ trợ stack trace. Tùy chọn `-g` bổ sung thông tin debug, bao gồm tên biến cục bộ, giúp debugger hiển thị dữ liệu trong một số cấu hình biên dịch. Nếu dự án dùng Maven hoặc Gradle, hãy kiểm tra cấu hình compiler của build thay vì biên dịch thủ công một file rồi kết luận rằng toàn bộ dự án đã được kiểm tra. Build tool còn quản lý dependency, source set, annotation processor và module path.

Với dự án dùng build tool, hãy chạy tác vụ biên dịch của chính dự án, chẳng hạn:

```bash
# Gradle Wrapper
./gradlew compileJava

# Maven Wrapper
./mvnw compile
```

Trên Windows, dùng script wrapper tương ứng như `gradlew.bat` hoặc `mvnw.cmd`. Wrapper giúp nhóm phát triển dùng phiên bản build tool đã được dự án cấu hình.

## 4. Stack trace là gì?

Khi một `Throwable` được tạo, nó có thể lưu thông điệp, cause và ảnh chụp các stack frame của luồng tại thời điểm đó. Khi in stack trace, Java hiển thị loại throwable, thông điệp và các vị trí thực thi liên quan. Stack trace vì thế là bản ghi đường đi của lời gọi phương thức dẫn đến exception.

Ví dụ:

```text
Exception in thread "main" java.lang.NullPointerException: Cannot invoke "String.trim()" because "rawName" is null
    at app.NameNormalizer.normalize(NameNormalizer.java:8)
    at app.CustomerService.register(CustomerService.java:24)
    at app.Main.main(Main.java:12)
```

Các thành phần cần đọc:

- `Exception in thread "main"`: exception không được xử lý đã thoát khỏi luồng `main`.
- `java.lang.NullPointerException`: lớp exception cho biết loại lỗi.
- Phần thông điệp sau dấu hai chấm: mô tả tình huống cụ thể nếu throwable có thông điệp.
- `at app.NameNormalizer.normalize(NameNormalizer.java:8)`: phương thức, file nguồn và số dòng của một stack frame.
- Các dòng tiếp theo thể hiện những phương thức đã gọi đến phương thức hiện tại.

Stack frame ở phía trên thường là lời gọi gần thời điểm exception được tạo nhất; các frame phía dưới là những caller trước đó. Dùng tên package, lớp, phương thức và số dòng để mở đúng vị trí trong source code. Nếu hiển thị `Native Method` hoặc `Unknown Source`, thông tin file/dòng không có sẵn cho frame đó.

**Dòng đầu tiên trong mã ứng dụng không nhất thiết là nguyên nhân gốc.** Đó thường là vị trí thao tác thất bại. Hãy đọc cả dữ liệu đầu vào, các caller và chuỗi cause để hiểu vì sao trạng thái đó xuất hiện.

## 5. Đọc `Caused by`, `Suppressed` và các frame rút gọn

Một exception ở tầng cao có thể bọc exception ở tầng thấp. Ví dụ, service muốn biểu diễn lỗi theo ngữ nghĩa nghiệp vụ nhưng nguyên nhân trực tiếp lại là lỗi I/O:

```java
try {
    repository.load(orderId);
} catch (IOException cause) {
    throw new IllegalStateException(
            "Không thể tải đơn hàng " + orderId,
            cause
    );
}
```

Stack trace có thể thể hiện:

```text
java.lang.IllegalStateException: Không thể tải đơn hàng 42
    at app.OrderService.load(OrderService.java:31)
    at app.OrderController.show(OrderController.java:18)
Caused by: java.io.IOException: Connection timed out
    at app.OrderRepository.load(OrderRepository.java:57)
    ... 2 more
```

Ý nghĩa:

- Exception ngoài cùng (`IllegalStateException`) mô tả lỗi mà tầng service công bố cho caller.
- `Caused by` chỉ ra exception được dùng làm nguyên nhân của exception bên ngoài. Trong ví dụ, cần điều tra kết nối ở repository.
- `... 2 more` nghĩa là hai stack frame còn lại trùng với các frame ở phần stack trace bao ngoài, nên được rút gọn.

Khi tạo exception bọc, hãy giữ nguyên cause:

```java
throw new IllegalStateException("Không thể tải đơn hàng " + orderId, cause);
```

Nếu chỉ tạo exception mới từ `cause.getMessage()` hoặc chỉ ghi thông điệp rồi bỏ throwable gốc, bạn sẽ làm mất loại exception, stack trace ban đầu và quan hệ nguyên nhân. Khi cần chuyển đổi tầng trừu tượng, hãy thêm ngữ cảnh có ích và truyền cause vào constructor.

### Exception bị suppressed

`Suppressed` thường xuất hiện khi nhiều thao tác cùng thất bại và Java cần chọn một exception chính để truyền ra ngoài. Một tình huống phổ biến là `try`-with-resources: exception trong thân `try` được truyền ra, trong khi exception phát sinh lúc đóng tài nguyên được gắn vào danh sách suppressed.

```java
try (var reader = Files.newBufferedReader(path)) {
    process(reader);
}
```

Nếu cả `process(reader)` và thao tác `close()` đều thất bại, stack trace có thể chứa:

```text
java.io.IOException: Không thể xử lý dữ liệu
    at app.Importer.process(Importer.java:22)
    at app.Importer.run(Importer.java:14)
Suppressed: java.io.IOException: Không thể đóng tài nguyên
    at app.ReaderResource.close(ReaderResource.java:19)
```

Exception suppressed cung cấp thêm thông tin về lỗi xảy ra trong quá trình dọn dẹp. Đừng bỏ qua phần này nếu lỗi liên quan đến file, stream, kết nối hoặc tài nguyên cần đóng.

### Lần theo chuỗi exception bằng Java API

Bạn có thể truy cập dữ liệu của throwable trong một phương thức xử lý lỗi:

```java
static void inspectException(Throwable exception) {
    System.err.println("Lỗi: " + exception.getMessage());

    Throwable cause = exception.getCause();
    while (cause != null) {
        System.err.println("Nguyên nhân: " + cause);
        cause = cause.getCause();
    }

    for (Throwable suppressed : exception.getSuppressed()) {
        System.err.println("Lỗi khi dọn dẹp: " + suppressed);
    }
}
```

Đoạn mã minh họa cách duyệt cause trực tiếp và danh sách suppressed của exception hiện tại. Trong ứng dụng thực tế, hãy dùng cơ chế logging của ứng dụng để ghi throwable cùng ngữ cảnh cần thiết; tránh chỉ ghi `exception.getMessage()` vì cách đó bỏ mất stack trace.

## 6. Hiểu các exception thường gặp khi chạy Java

Một số loại exception quen thuộc và hướng điều tra:

| Exception | Tình huống thường gặp | Điều cần kiểm tra |
|---|---|---|
| `NullPointerException` | Truy cập phương thức hoặc field thông qua tham chiếu `null` | Biến nào null, dữ liệu được tạo ở đâu, hợp đồng của phương thức có cho phép null không |
| `IndexOutOfBoundsException` | Chỉ số nằm ngoài phạm vi collection hoặc list | Giá trị index, kích thước collection, điều kiện vòng lặp |
| `ArrayIndexOutOfBoundsException` | Truy cập mảng bằng chỉ số không hợp lệ | Độ dài mảng và phép tính index |
| `NumberFormatException` | Chuyển chuỗi không có định dạng số hợp lệ thành số | Giá trị đầu vào, khoảng trắng, dấu phân cách và quy tắc định dạng |
| `ClassCastException` | Ép kiểu đối tượng sang kiểu không tương thích tại runtime | Kiểu thực tế của đối tượng, cấu trúc kế thừa và generic boundary |
| `IllegalArgumentException` | Phương thức nhận đối số nằm ngoài miền giá trị được chấp nhận | Điều kiện đầu vào và hợp đồng phương thức |
| `IOException` | Đọc/ghi hoặc truy cập tài nguyên gặp lỗi | Đường dẫn, quyền truy cập, trạng thái file, mạng hoặc thiết bị |
| `ConcurrentModificationException` | Cấu trúc dữ liệu phát hiện thay đổi không phù hợp trong lúc duyệt | Cách sửa collection trong vòng lặp và cơ chế đồng bộ |

Không nên chỉ đổi loại exception hoặc bắt tất cả exception để chương trình tiếp tục. Hãy xác định hợp đồng của thao tác, dữ liệu thực tế và cách phục hồi phù hợp. Chỉ xử lý exception tại nơi có đủ thông tin để đưa ra quyết định có ý nghĩa.

### Helpful NullPointerException

JVM hiện đại có thể cung cấp thông điệp chi tiết hơn cho `NullPointerException` do JVM phát sinh, ví dụ:

```text
Cannot invoke "String.trim()" because "rawName" is null
```

Thông điệp cho biết thao tác nào thất bại và tham chiếu nào có giá trị `null`. Đây là khả năng Helpful NullPointerExceptions được giới thiệu trong JEP 358 và có trong các JDK hiện đại. Thông điệp cụ thể phụ thuộc vào biểu thức, bytecode và thông tin JVM có thể xác định; exception do ứng dụng tự tạo với message riêng sẽ hiển thị message đó.

Ví dụ mã gây lỗi:

```java
public final class NameNormalizer {
    public String normalize(String rawName) {
        return rawName.trim().toUpperCase(Locale.ROOT);
    }
}
```

Nếu `rawName` là `null`, lời gọi `trim()` thất bại. Cách sửa phụ thuộc vào hợp đồng dữ liệu. Nếu tên bắt buộc phải có, có thể từ chối đầu vào ngay tại biên hệ thống:

```java
public final class NameNormalizer {
    public String normalize(String rawName) {
        if (rawName == null || rawName.isBlank()) {
            throw new IllegalArgumentException("Tên không được để trống");
        }

        return rawName.trim().toUpperCase(Locale.ROOT);
    }
}
```

Trong ví dụ này cần thêm `import java.util.Locale;`. Thông điệp lỗi rõ ràng giúp người gọi biết đầu vào không hợp lệ; debugger giúp lần lại vì sao dữ liệu null đi tới phương thức.

## 7. Quy trình gỡ lỗi có hệ thống

Khi gặp lỗi, hãy tiến hành theo một quy trình có thể lặp lại:

1. **Tạo lại lỗi:** ghi lại thao tác, dữ liệu đầu vào, môi trường và các bước khiến lỗi xuất hiện. Một lỗi không tái hiện ổn định sẽ khó kiểm chứng bản sửa.
2. **Xác định giai đoạn:** lỗi biên dịch, exception khi chạy hay kết quả logic sai. Chọn công cụ tương ứng.
3. **Đọc bằng chứng đầu tiên:** với compiler, bắt đầu từ diagnostic đầu tiên; với runtime, bắt đầu từ loại exception và stack trace; với lỗi logic, xác định kết quả thực tế khác kết quả mong đợi ở đâu.
4. **Thu hẹp phạm vi:** mở đúng source frame hoặc đặt breakpoint gần nơi dữ liệu bắt đầu sai. Không cần bước qua toàn bộ chương trình từ `main` nếu đã có vị trí đáng tin cậy.
5. **Kiểm tra trạng thái:** quan sát tham số, biến cục bộ, field của object, kết quả phương thức và call stack.
6. **Theo dõi luồng thực thi:** dùng Step Over, Step Into và Step Out để tìm thời điểm trạng thái chuyển từ đúng sang sai.
7. **Sửa nguyên nhân:** cập nhật logic hoặc hợp đồng dữ liệu ở nơi chịu trách nhiệm; tránh chỉ che exception.
8. **Chạy lại kiểm chứng:** tái hiện trường hợp lỗi, chạy test liên quan và kiểm tra các trường hợp biên có thể bị ảnh hưởng.

Ghi lại giả thuyết trước khi sửa, chẳng hạn: “`rawName` trở thành null sau khi đọc hồ sơ khách hàng”. Sau đó dùng breakpoint và watch để xác nhận hoặc bác bỏ giả thuyết đó. Cách làm này giúp mỗi lần sửa đều dựa trên bằng chứng.

## 8. Sử dụng debugger trong IDE

Debugger cho phép tạm dừng chương trình và xem trạng thái ngay tại thời điểm thực thi. Các IDE Java phổ biến hiện nay cung cấp những khả năng cốt lõi như breakpoint, xem biến, call stack, step execution, đánh giá biểu thức và dừng khi exception xảy ra.

### Các thao tác debugger cần biết

| Thao tác | Ý nghĩa | Khi nào dùng |
|---|---|---|
| Breakpoint | Tạm dừng khi chương trình đi đến vị trí được đánh dấu | Đặt trước dòng nghi ngờ hoặc nơi dữ liệu đi vào một tầng xử lý |
| Conditional breakpoint | Chỉ dừng khi biểu thức điều kiện đúng | Vòng lặp lớn hoặc lỗi chỉ xảy ra với một ID cụ thể |
| Exception breakpoint | Dừng khi một loại exception được ném | Muốn quan sát trạng thái tại nơi exception phát sinh, kể cả khi exception được catch ở tầng khác |
| Step Over | Thực thi dòng hiện tại rồi dừng ở dòng tiếp theo, không đi vào thân method được gọi | Bỏ qua method đã tin cậy và quan sát kết quả trả về |
| Step Into | Đi vào method được gọi | Kiểm tra cách method tính toán hoặc thay đổi trạng thái |
| Step Out | Chạy tiếp đến khi thoát method hiện tại và quay lại caller | Đã hiểu phần thân method hoặc muốn quay về tầng gọi |
| Continue/Resume | Tiếp tục đến breakpoint kế tiếp hoặc khi chương trình kết thúc | Chuyển đến điểm dừng kế tiếp sau khi kiểm tra xong |
| Variables / Watches | Xem giá trị biến hoặc biểu thức theo dõi | So sánh giá trị trước và sau một thao tác |
| Call Stack | Xem chuỗi lời gọi và chọn frame để kiểm tra | Xác định ai gọi method hiện tại và tham số đến từ đâu |
| Logpoint | Ghi thông tin khi tới vị trí mà không tạm dừng | Theo dõi vòng lặp hoặc luồng chạy mà không làm gián đoạn liên tục |

Tên và phím tắt có thể khác giữa IDE và keymap. Hãy dựa vào nhãn hành động trong cửa sổ Debug nếu phím tắt trên máy bạn không trùng ví dụ.

### Thực hành với IntelliJ IDEA

1. Mở project Java và kiểm tra Project SDK cùng cấu hình chạy đang dùng JDK 27.
2. Mở file có dòng cần điều tra. Nhấp vào lề bên trái số dòng thực thi để đặt line breakpoint.
3. Chọn cấu hình Run/Debug của ứng dụng rồi khởi chạy bằng **Debug**.
4. Khi chương trình dừng, xem **Variables** để kiểm tra biến cục bộ và field; xem **Frames/Call Stack** để biết đường đi đến vị trí hiện tại.
5. Dùng **Step Over** để chạy qua dòng hiện tại, **Step Into** để vào method và **Step Out** để quay về caller.
6. Thêm biểu thức vào **Watches** hoặc dùng Evaluate Expression để kiểm tra một giá trị trong frame đang chọn.
7. Nếu cần dừng tại thời điểm exception được ném, mở cấu hình breakpoints và thêm **Java Exception Breakpoint** cho loại exception cần theo dõi.

IntelliJ IDEA còn hỗ trợ conditional breakpoint và logpoint. Dùng điều kiện khi chỉ một số lần gọi gây lỗi; dùng logpoint khi muốn ghi giá trị mà không dừng chương trình. Tính năng và phím tắt cụ thể phụ thuộc phiên bản và keymap.

### Thực hành với Visual Studio Code

1. Cài **Extension Pack for Java**, trong đó có extension **Debugger for Java**.
2. Mở thư mục project Java và chờ extension hoàn tất việc nạp project.
3. Đặt breakpoint bằng cách nhấp vào lề cạnh dòng mã cần dừng.
4. Mở **Run and Debug**, chọn cấu hình phù hợp hoặc dùng lệnh Debug Java trên `main()` khi extension nhận diện được entry point.
5. Nhấn `F5` để bắt đầu phiên debug.
6. Khi chương trình dừng, kiểm tra **VARIABLES**, **CALL STACK** và **DEBUG CONSOLE**.
7. Dùng Step Over, Step Into, Step Out hoặc Continue trên thanh công cụ debug để điều khiển chương trình.

Với ứng dụng cần tham số dòng lệnh, biến môi trường hoặc cấu hình khởi chạy riêng, tạo hay chỉnh `.vscode/launch.json` theo hướng dẫn của Debugger for Java. Nếu chương trình cần nhập dữ liệu từ bàn phím, chọn terminal phù hợp vì Debug Console mặc định của VS Code không nhận input tương tác.

## 9. Thực hành tìm nguyên nhân bằng breakpoint

Giả sử chương trình chuẩn hóa tên khách hàng nhưng thỉnh thoảng phát sinh `NullPointerException`. Hãy bắt đầu bằng một điểm dừng ở nơi nhận dữ liệu:

```java
public final class CustomerService {
    private final NameNormalizer normalizer = new NameNormalizer();

    public String register(String rawName) {
        String normalizedName = normalizer.normalize(rawName);
        return "Đã đăng ký: " + normalizedName;
    }
}
```

Đặt breakpoint tại dòng gọi `normalizer.normalize(rawName)`, sau đó chạy chương trình với tình huống gây lỗi.

Tại điểm dừng:

1. Xem giá trị `rawName`. Nếu giá trị đã là `null`, nguyên nhân xuất hiện trước khi gọi `normalize`.
2. Xem Call Stack để xác định caller truyền tham số vào `register`.
3. Chọn frame của caller để xem biến hoặc tham số tương ứng. Nếu cần, đặt breakpoint ở nơi dữ liệu được đọc hoặc chuyển đổi.
4. Tiếp tục từng bước để xác định câu lệnh đầu tiên tạo ra giá trị không hợp lệ.
5. Sửa tại nơi phù hợp: kiểm tra dữ liệu ở biên nhận, xác thực hợp đồng hoặc thay đổi cách xử lý null theo yêu cầu nghiệp vụ.

Nếu `rawName` thường có giá trị nhưng chỉ một khách hàng cụ thể bị lỗi, dùng conditional breakpoint với điều kiện phù hợp, ví dụ kiểm tra ID khách hàng hoặc `rawName == null`. Điều kiện cần dùng đúng tên biến đang có trong scope của breakpoint.

### Theo dõi vòng lặp và dữ liệu thay đổi

Với lỗi xuất hiện sau nhiều vòng lặp, breakpoint thông thường có thể khiến bạn phải bấm Continue nhiều lần. Dùng conditional breakpoint để dừng khi index đạt giá trị quan tâm hoặc logpoint để ghi giá trị mỗi lần chạy qua.

Ví dụ, với đoạn mã:

```java
for (int index = 0; index < orders.size(); index++) {
    total += orders.get(index).amount();
}
```

Bạn có thể đặt điều kiện `index == 25` để kiểm tra phần tử ở lần lặp thứ 26, hoặc theo dõi `orders.get(index).amount()` bằng watch/logpoint. Đảm bảo biểu thức điều kiện không gây thay đổi dữ liệu.

### Debug nhiều luồng

Trong ứng dụng đa luồng, mỗi thread có call stack riêng. Khi debugger tạm dừng ứng dụng, chọn đúng thread trong danh sách Threads rồi chọn frame tương ứng để xem biến. Đừng giả định stack trace của thread `main` mô tả toàn bộ hoạt động của ứng dụng. Với lỗi tranh chấp dữ liệu, hãy quan sát nơi đọc/ghi field dùng chung, thứ tự thực thi và điều kiện đồng bộ.

## 10. Đảm bảo IDE và build đang dùng cùng cấu hình Java

Một nguồn gây nhầm lẫn phổ biến là terminal biên dịch bằng JDK 27 nhưng IDE hoặc build tool dùng JDK khác. Khi đó, cảnh báo và lỗi hiển thị trong editor có thể không khớp kết quả build thực tế.

Kiểm tra các cấu hình liên quan:

- **Project SDK/JDK:** JDK dùng để phân tích và chạy project trong IDE.
- **Language level:** mức cú pháp Java mà editor cho phép trong project.
- **Compiler release:** phiên bản Java mục tiêu mà build tạo class file và kiểm tra API.
- **Gradle JVM:** JDK chạy Gradle daemon; cần phù hợp với phiên bản Gradle và cấu hình dự án.
- **Maven JDK/Runner JRE:** JDK mà IDE dùng để chạy Maven, nếu Maven được khởi chạy từ IDE.
- **Run/Debug configuration:** main class, classpath/module path, program arguments, VM options và environment variables.

Sau khi thay đổi cấu hình, tải lại project hoặc đồng bộ build tool nếu IDE yêu cầu, rồi chạy lại tác vụ build. Nếu terminal và IDE cho kết quả khác nhau, so sánh JDK thực tế, compiler release, dependency và cấu hình run trước khi sửa mã nguồn.

## 11. Những sai lầm nên tránh khi điều tra lỗi

- **Chỉ nhìn dòng cuối của stack trace:** có thể bỏ lỡ exception gốc trong phần `Caused by` hoặc lỗi phụ trong `Suppressed`.
- **Sửa dòng được đánh dấu mà không đọc diagnostic:** dấu caret chỉ là vị trí compiler khoanh vùng; nguyên nhân có thể nằm ở biểu thức hoặc khai báo liên quan.
- **Bắt `Exception` rồi bỏ qua:** chương trình có thể tiếp tục trong trạng thái không hợp lệ và làm mất dấu vết nguyên nhân.
- **Chỉ ghi message, không ghi throwable:** log không còn stack trace để lần theo đường gọi.
- **Đặt breakpoint ở quá nhiều dòng:** phiên debug trở nên chậm và khó tập trung. Hãy bắt đầu từ một vị trí có bằng chứng.
- **Đánh giá biểu thức có side effect trong Watches/Evaluate:** gọi một method có thể thay đổi trạng thái hoặc tạo I/O, làm sai lệch hiện tượng đang điều tra. Ưu tiên biểu thức đọc dữ liệu.
- **Không kiểm tra thread/frame đang chọn:** giá trị hiển thị thuộc frame hiện tại; chọn nhầm thread hoặc frame dễ dẫn đến kết luận sai.
- **Tin rằng IDE build pass đồng nghĩa mọi kiểm tra đều pass:** vẫn cần chạy đúng build task và test của dự án.
- **Sửa lỗi mà không chạy lại trường hợp tái hiện:** luôn xác nhận lỗi ban đầu đã hết và kiểm tra các trường hợp liên quan.

## 12. Tài liệu tham khảo chính thức

- [Oracle — The `javac` Command (JDK 27)](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): cấu trúc chẩn đoán, `--release`, `-Xdiags`, `-Xlint`, `-g` và cách compiler hoạt động.
- [Oracle — `Throwable` (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Throwable.html): stack trace, cause, suppressed exception và các API truy cập thông tin lỗi.
- [Oracle — `NullPointerException` (Java SE 27)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/NullPointerException.html): điều kiện phát sinh NPE và thông điệp chi tiết.
- [OpenJDK — JEP 358: Helpful NullPointerExceptions](https://openjdk.org/jeps/358): thiết kế thông điệp NPE chi tiết trong JVM.
- [JetBrains — Debug code](https://www.jetbrains.com/help/idea/debugging-code.html): quy trình debug trong IntelliJ IDEA.
- [JetBrains — Breakpoints](https://www.jetbrains.com/help/idea/using-breakpoints.html): line, method, field, exception, conditional breakpoints và logpoints.
- [JetBrains — Step through the program](https://www.jetbrains.com/help/idea/stepping-through-the-program.html): Step Over, Step Into và Step Out.
- [Visual Studio Code — Running and debugging Java](https://code.visualstudio.com/docs/java/java-debugging): Debugger for Java, cấu hình launch, breakpoint, variables, call stack và debug console.

Khi đọc lỗi, hãy xem diagnostic hoặc stack trace là bằng chứng để đặt giả thuyết. Compiler giúp xác định điều kiện mã nguồn không hợp lệ; stack trace chỉ ra đường gọi dẫn đến exception; debugger cho phép quan sát dữ liệu tại đúng thời điểm. Kết hợp cả ba với một tình huống tái hiện rõ ràng sẽ giúp bạn tìm và sửa nguyên nhân của lỗi trong chương trình Java 27.
