# Kiểm tra API deprecated bằng công cụ jdeprscan

## 1. API deprecated là gì?

Một API deprecated là API mà nhà phát triển Java khuyến nghị ngừng sử dụng trong mã mới. API vẫn có thể tồn tại và hoạt động, nhưng có thể có lựa chọn tốt hơn, có vấn đề thiết kế, khó bảo trì hoặc được dự kiến loại bỏ trong tương lai.

Java đánh dấu API deprecated bằng annotation `@Deprecated`. Annotation này có hai thuộc tính quan trọng:

- `since` cho biết phiên bản Java mà API được đánh dấu deprecated.
- `forRemoval` cho biết API được đánh dấu để loại bỏ trong một phiên bản tương lai. Giá trị mặc định là `false`.

Ví dụ:

~~~java
/**
 * @deprecated Use {@link #newOperation()} instead.
 */
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
    // Legacy behavior
}
~~~

Cần phân biệt annotation `@Deprecated` với Javadoc tag `@deprecated`:

- `@Deprecated` là metadata trong bytecode, được compiler và công cụ phân tích đọc.
- `@deprecated` là phần giải thích dành cho người đọc tài liệu, thường nêu lý do và API thay thế.
- Nên dùng cả hai khi đánh dấu API của chính dự án.

Deprecated không đồng nghĩa với đã bị xóa. API có thể tiếp tục tồn tại qua nhiều phiên bản. `forRemoval = true` thể hiện ý định loại bỏ, nhưng không cung cấp một ngày hoặc phiên bản xóa chắc chắn.

## 2. jdeprscan dùng để làm gì?

`jdeprscan` là công cụ trong JDK dùng để quét bytecode và tìm tham chiếu tới các API Java SE đã deprecated trong một release được chọn. Công cụ hỗ trợ kiểm tra thư mục class, file JAR, file class riêng lẻ hoặc tên lớp đầy đủ.

Công cụ hữu ích khi:

- Nâng cấp ứng dụng lên JDK mới.
- Kiểm tra thư viện cũ trước khi cập nhật dependency.
- Tìm API được đánh dấu deprecated trong bytecode đã biên dịch.
- Tách các API chỉ deprecated khỏi các API đã được đánh dấu `forRemoval`.
- Tạo báo cáo kỹ thuật để lập kế hoạch thay thế API cũ.

`jdeprscan` phân tích bytecode đã biên dịch. Nó không nhận file nguồn `.java` làm đầu vào và không tự sửa mã nguồn. Đối với mã nguồn đang biên dịch, kết hợp thêm `javac -Xlint:deprecation` và `javac -Xlint:removal`.

Công cụ cũng không thay thế việc chạy test trên JDK đích. Một API có thể vẫn còn deprecated nhưng hoạt động khác trong runtime mới; ngược lại, một tham chiếu không bị scanner báo không chứng minh ứng dụng tương thích hoàn toàn.

## 3. Cài đặt và xác định phiên bản công cụ

`jdeprscan` nằm trong thư mục `bin` của JDK. Nếu biến `JAVA_HOME` trỏ tới JDK, có thể chạy:

~~~bash
jdeprscan --version
jdeprscan --full-version
jdeprscan --help
~~~

Các tùy chọn:

- `--version` in phiên bản rút gọn.
- `--full-version` in chuỗi phiên bản đầy đủ.
- `--help` hiển thị cú pháp, loại đầu vào và các release được hỗ trợ.

Trong môi trường kiểm chứng của bài này, công cụ là JDK 24.0.2. Phần trợ giúp liệt kê các release có thể chọn từ Java 8 đến Java 24. Danh sách này phụ thuộc phiên bản JDK đang cài; hãy kiểm tra `jdeprscan --help` trên máy build thay vì giả định mọi JDK hỗ trợ cùng một tập release.

Nếu lệnh không được nhận diện, kiểm tra:

~~~bash
java --version
javac --version
jdeprscan --version
~~~

Ba lệnh nên trỏ tới cùng một JDK toolchain trong CI. Nếu `java` và `jdeprscan` đến từ hai thư mục JDK khác nhau, kết quả phân tích có thể không khớp với môi trường chạy dự kiến.

## 4. Cú pháp và các loại đầu vào

Cú pháp tổng quát:

~~~bash
jdeprscan [options] {dir|jar|class} ...
~~~

Các loại đầu vào chính:

| Đầu vào | Ví dụ | Ý nghĩa |
|---|---|---|
| Thư mục | `build/classes` | Quét cây package/class bắt đầu từ thư mục được chỉ định. |
| JAR | `build/app.jar` | Quét các class bên trong archive. |
| File class | `build/classes/demo/Main.class` | Quét một class cụ thể. |
| Tên lớp | `demo.Main` | Quét lớp theo tên đầy đủ; có thể cần class path để tìm lớp. |

Ví dụ quét từng loại:

~~~bash
# Quét toàn bộ thư mục class
jdeprscan --release 17 build/classes

# Quét một JAR
jdeprscan --release 17 build/app.jar

# Quét một class file
jdeprscan --release 17 build/classes/demo/Main.class

# Quét theo tên lớp
jdeprscan --release 17 --class-path build/classes demo.Main
~~~

Tên lớp lồng nhau dùng dấu `$` để phân cách class ngoài và class trong. Ví dụ:

~~~bash
jdeprscan --release 17 --class-path build/classes 'demo.Outer$Nested'
~~~

`jdeprscan` không nhận source file trực tiếp. Nếu chỉ có mã nguồn, biên dịch thành class file trước rồi mới quét.

## 5. Chọn API catalog bằng --release

Tùy chọn `--release` chỉ định tập API deprecated của Java SE release được dùng để đối chiếu:

~~~bash
jdeprscan --release 17 build/classes
~~~

Điều này giúp kiểm tra theo release ứng dụng sẽ chạy. Nếu đang chuẩn bị nâng cấp từ Java 17 lên Java 24, có thể chạy cả hai lượt:

~~~bash
jdeprscan --release 17 build/classes
jdeprscan --release 24 build/classes
~~~

Không nhầm `jdeprscan --release` với `javac --release`:

- `jdeprscan --release` chọn catalog deprecated API của Java SE release cần kiểm tra.
- `javac --release` chọn tập API và quy tắc ngôn ngữ mà compiler dùng khi biên dịch source.

Kết quả có thể thay đổi theo release vì metadata deprecated được cập nhật qua các phiên bản. Ví dụ đã kiểm tra bằng JDK 24.0.2: `Thread.stop()` được báo deprecated khi quét theo release 17, nhưng ở catalog release 24 nó còn được đánh dấu `forRemoval=true`. Vì vậy, cùng một bytecode có thể cho thông tin khác khi thay đổi release được chọn.

Hãy chọn release đích thực tế, ghi rõ nó trong script CI và không so sánh hai báo cáo nếu chúng được tạo từ hai API catalog khác nhau mà không ghi chú.

## 6. Các tùy chọn quan trọng

| Tùy chọn | Công dụng |
|---|---|
| `--release N` | Chọn Java SE release làm nguồn metadata deprecated API. |
| `--for-removal` | Chỉ báo cáo API được đánh dấu deprecated for removal. |
| `--class-path PATH` | Cung cấp đường dẫn để phân giải các class phụ thuộc. |
| `--list` hoặc `-l` | Liệt kê tập API deprecated của release; không quét class/JAR. |
| `--verbose` hoặc `-v` | In thêm thông tin về quá trình xử lý. |
| `--version` | In phiên bản rút gọn của công cụ. |
| `--full-version` | In phiên bản đầy đủ. |
| `--help`, `-h`, `-?` | In trợ giúp. |

`--list` là chế độ liệt kê catalog. Khi dùng tùy chọn này, không truyền thư mục, JAR hoặc class cần quét:

~~~bash
jdeprscan --list --release 17
~~~

Chỉ liệt kê API được đánh dấu để loại bỏ:

~~~bash
jdeprscan --list --release 17 --for-removal
~~~

Chỉ quét tham chiếu được đánh dấu để loại bỏ:

~~~bash
jdeprscan --release 17 --for-removal build/classes
~~~

Trong JDK 24.0.2, trợ giúp nêu `--for-removal` không dùng được với release 6, 7 hoặc 8. Hãy đọc trợ giúp của phiên bản đang chạy trước khi ghép tùy chọn này với một release cũ.

## 7. Ví dụ thực hành: quét class và JAR

Tạo cấu trúc:

~~~text
jdeprscan-demo/
├── src/
│   └── demo/
│       └── LegacyApiDemo.java
├── build/
│   └── classes/
└── app.jar
~~~

Tệp `src/demo/LegacyApiDemo.java`:

~~~java
package demo;

import java.util.Date;

public class LegacyApiDemo {

    @SuppressWarnings({"deprecation", "removal"})
    public static int legacyYear(Date date) {
        return date.getYear();
    }

    @SuppressWarnings({"deprecation", "removal"})
    public static void stopLegacyThread(Thread thread) {
        thread.stop();
    }
}
~~~

Ví dụ cố ý giữ tham chiếu tới hai API cũ để scanner có thể tìm trong bytecode. Không gọi `stopLegacyThread` trong ứng dụng thật; `Thread.stop()` có thể dừng thread tại thời điểm tùy ý và làm dữ liệu dùng chung rơi vào trạng thái không nhất quán.

Biên dịch bằng JDK 17 API:

~~~bash
mkdir -p build/classes
javac --release 17 -d build/classes src/demo/LegacyApiDemo.java
~~~

Quét thư mục class:

~~~bash
jdeprscan --release 17 build/classes
~~~

Output quan trọng có dạng:

~~~text
Directory build/classes:
class demo/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class demo/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V
~~~

Quét lại bằng catalog Java 24:

~~~bash
jdeprscan --release 24 build/classes
~~~

Output của JDK 24.0.2 có dạng:

~~~text
Directory build/classes:
class demo/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class demo/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Đóng gói class thành JAR:

~~~bash
jar --create --file app.jar -C build/classes .
~~~

Quét JAR:

~~~bash
jdeprscan --release 17 app.jar
~~~

Kết quả quét JAR chứa cùng hai tham chiếu deprecated như khi quét thư mục class. Có thể dùng cách này để kiểm tra artifact đã đóng gói trước khi phát hành.

## 8. Đọc kết quả của jdeprscan

Một dòng kết quả có dạng:

~~~text
class demo/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
~~~

Ý nghĩa:

- `class demo/LegacyApiDemo` là class trong ứng dụng đang chứa tham chiếu.
- `java/util/Date` là class sở hữu API được gọi.
- `getYear` là tên method.
- `()I` là JVM method descriptor: không có tham số và trả về kiểu `int`.

Ví dụ khác:

~~~text
class demo/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

`()V` nghĩa là method không có tham số và trả về `void`. Phần `forRemoval=true` cho biết API được đánh dấu để loại bỏ trong catalog release đang quét.

Output có thể bắt đầu bằng `Directory` hoặc `Jar file` để chỉ loại đầu vào. Khi bật `--verbose`, công cụ in thêm class được xử lý và tiến trình phân giải.

Không phải mọi dòng output đều có nghĩa là ứng dụng sẽ lỗi ngay khi chạy. Đây là cảnh báo về dependency API cần được đánh giá và lập kế hoạch thay thế.

## 9. Phân biệt deprecated và deprecated for removal

`@Deprecated` có thể được dùng mà không đánh dấu for removal. Hai trạng thái có ý nghĩa khác nhau:

| Trạng thái | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Deprecated | API không còn được khuyến nghị; có thể vẫn tồn tại lâu dài. | Tìm API thay thế và đưa vào kế hoạch bảo trì. |
| Deprecated for removal | API được đánh dấu với ý định loại bỏ trong tương lai. | Ưu tiên xử lý, kiểm tra release đích và tránh thêm dependency mới. |
| Removed | API đã bị loại khỏi release đang dùng. | Cần thay thế hoặc dùng thư viện/runtime tương thích; scanner không biến API đã bị xóa thành API còn tồn tại. |

`--for-removal` lọc các API ở hàng thứ hai. Không nên chỉ chạy chế độ này: những API deprecated thông thường vẫn có thể cần được thay thế trước khi nâng cấp lớn.

Một quy trình migration hợp lý là chạy cả báo cáo đầy đủ và báo cáo for-removal, sau đó ưu tiên các API có nguy cơ bị xóa cao.

## 10. Quét class có dependency bằng --class-path

Một class có thể tham chiếu tới class khác trong thư viện phụ thuộc. Dùng `--class-path` để cung cấp đường dẫn tìm các class đó:

~~~bash
jdeprscan --release 17 \
  --class-path "build/classes;lib/*" \
  build/app.jar
~~~

Trên Windows, dấu phân cách class path là dấu chấm phẩy (`;`). Trên Linux/macOS, dấu phân cách là dấu hai chấm (`:`):

~~~bash
jdeprscan --release 17 \
  --class-path "build/classes:lib/*" \
  build/app.jar
~~~

Class path giúp công cụ phân giải các type mà bytecode tham chiếu. Nó không phải module path và không thay thế việc cung cấp dependency cần thiết trong môi trường build.

Nếu scanner không phân giải được một class phụ thuộc, kiểm tra:

- JAR có thực sự nằm trong class path không.
- Wildcard có được shell truyền đúng không.
- Tên package/class có đúng không.
- Dependency có được build thành class file tương thích không.
- Phiên bản dependency có phù hợp với artifact đang quét không.

Không bỏ qua cảnh báo phân giải chỉ để có báo cáo ít dòng hơn. Ghi nhận class chưa phân giải để tránh kết luận rằng toàn bộ dependency graph đã được kiểm tra.

## 11. Liệt kê catalog API deprecated

`--list` hữu ích khi cần tìm API nào được đánh dấu deprecated trong một release mà không cần có ứng dụng mẫu.

Liệt kê toàn bộ catalog:

~~~bash
jdeprscan --list --release 17
~~~

Liệt kê riêng các API for removal:

~~~bash
jdeprscan --list --release 17 --for-removal
~~~

Trên PowerShell, lọc một số API:

~~~powershell
jdeprscan --list --release 17 |
    Select-String -Pattern "java.util.Date.getYear|java.lang.Thread.stop"
~~~

Trên Linux/macOS:

~~~bash
jdeprscan --list --release 17 |
    grep -E "java.util.Date.getYear|java.lang.Thread.stop"
~~~

Catalog thường lớn, nên lọc theo class hoặc API cần điều tra. Lệnh này chỉ hiển thị metadata của JDK; nó không chứng minh ứng dụng đang sử dụng API đó.

Để biết ứng dụng có tham chiếu tới API hay không, phải quét class/JAR thực tế.

## 12. Tìm cách thay thế API deprecated

`jdeprscan` chỉ báo vị trí tham chiếu. Nó không tự đề xuất một thay thế đúng cho mọi trường hợp. Khi thay API, phải hiểu semantics cũ, cách xử lý exception và yêu cầu tương thích của chương trình.

Một số hướng thay thế phổ biến:

| API cũ | Hướng thay thế | Lưu ý |
|---|---|---|
| `Date.getYear()` và các thao tác ngày giờ cũ | `java.time` như `LocalDate`, `ZonedDateTime`, `Instant` | Chú ý timezone và giá trị năm cũ của `Date.getYear()` là năm trừ 1900. |
| `Class.newInstance()` | `getDeclaredConstructor().newInstance()` | Kiểm tra constructor, quyền truy cập và các exception mới. |
| `Thread.stop()` | `interrupt()`, cờ hủy tác vụ hoặc `ExecutorService` | Dùng hủy hợp tác; không dừng thread tại thời điểm tùy ý. |
| `Thread.suspend()` / `resume()` | Cơ chế phối hợp bằng lock, condition hoặc trạng thái tác vụ | Thiết kế lại đồng bộ hóa để tránh deadlock. |
| API bảo mật cũ | API bảo mật hiện hành và cấu hình runtime được hỗ trợ | Kiểm tra mô hình bảo mật của ứng dụng thay vì thay tên method máy móc. |

Ví dụ thay `Class.newInstance()`:

~~~java
Class<?> type = String.class;
Object value = type.getDeclaredConstructor().newInstance();
~~~

Cách mới có thể ném `NoSuchMethodException`, `InvocationTargetException`, `InstantiationException` hoặc `IllegalAccessException`. Hãy điều chỉnh exception handling theo hợp đồng mới.

Với `Date.getYear()`, ví dụ lấy năm thực tế từ một instant:

~~~java
int year = date.toInstant()
        .atZone(ZoneId.systemDefault())
        .getYear();
~~~

`Date.getYear()` trả về năm trừ 1900, còn `LocalDate.getYear()` trả về năm đầy đủ. Nếu cần giữ nguyên giá trị legacy vì tương thích, phải chuyển đổi có chủ đích; không thay method rồi giả định kết quả giống hệt.

## 13. Thay Thread.stop() bằng hủy hợp tác

`Thread.stop()` nguy hiểm vì thread có thể bị dừng giữa lúc đang cập nhật trạng thái dùng chung. Cách thông thường là yêu cầu thread tự kết thúc bằng interrupt hoặc cờ hủy.

Ví dụ độc lập có thể biên dịch và chạy:

~~~java
import java.util.concurrent.CountDownLatch;

public class CooperativeCancellation {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            started.countDown();

            while (!Thread.currentThread().isInterrupted()) {
                try {
                    Thread.sleep(50);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }

            System.out.println("worker stopped cooperatively");
        });

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 CooperativeCancellation.java
java CooperativeCancellation
~~~

Stdout:

~~~text
worker stopped cooperatively
~~~

Thread kiểm tra trạng thái interrupt, thoát khỏi vòng lặp và kết thúc ở một điểm do chính nó kiểm soát. Với ứng dụng dùng thread pool, cân nhắc `ExecutorService.shutdown()` hoặc `shutdownNow()` và thiết kế tác vụ để phản hồi interruption.

Không nuốt `InterruptedException` mà không có lý do. Nếu không thể kết thúc ngay, hãy khôi phục interrupt status hoặc truyền exception lên tầng gọi thích hợp.

## 14. Kết hợp jdeprscan với compiler lint

`jdeprscan` quét bytecode; compiler lint kiểm tra các lời gọi deprecated trong source đang biên dịch. Hai công cụ bổ sung cho nhau.

Ví dụ:

~~~bash
javac --release 17 -Xlint:deprecation -d build/classes src/demo/LegacyApiDemo.java
~~~

Có thể biến warning thành lỗi trong CI:

~~~bash
javac --release 17 -Xlint:deprecation -Werror \
  -d build/classes \
  src/demo/LegacyApiDemo.java
~~~

Với API có cảnh báo removal trên release đang dùng, thêm lint tương ứng:

~~~bash
javac --release 24 -Xlint:deprecation -Xlint:removal -Werror \
  -d build/classes \
  src/demo/LegacyApiDemo.java
~~~

Trong phép kiểm tra bằng JDK 24.0.2, `Class.newInstance()` xuất hiện trong catalog `jdeprscan --list` và compiler `javac -Xlint:deprecation` phát cảnh báo. Tuy nhiên, scanner không báo tham chiếu đó trong class thử nghiệm, dù bytecode có lời gọi method. Đây là một giới hạn quan sát được ở phiên bản công cụ đã thử; không nên dựa duy nhất vào `jdeprscan` để kết luận không có deprecated API.

Vì vậy, với source của chính dự án, bật compiler lint. Với binary và thư viện đã biên dịch, chạy `jdeprscan`. Kết hợp thêm test trên JDK mục tiêu và công cụ phân tích dependency khi cần.

## 15. Giới hạn của việc quét bytecode

Kết quả scanner cần được hiểu theo phạm vi dữ liệu nó có thể đọc:

- Scanner phân tích bytecode đã biên dịch, không đọc source code như compiler.
- Nó đối chiếu với catalog API deprecated của Java SE release được chọn.
- Nó không tự hiểu chuỗi class/method được tạo từ cấu hình rồi gọi bằng reflection.
- Mã được sinh động tại runtime hoặc tải từ nơi không có trong đầu vào có thể không xuất hiện trong báo cáo.
- Tham chiếu tới API deprecated của thư viện bên thứ ba cần công cụ hoặc catalog phù hợp với thư viện đó; `jdeprscan` không phải báo cáo toàn diện cho mọi annotation `@Deprecated` trong mọi dependency.
- Thiếu class phụ thuộc có thể ảnh hưởng khả năng phân giải và chất lượng báo cáo.
- Báo cáo không đánh giá API thay thế có giữ nguyên hành vi nghiệp vụ hay không.

Một quan sát quan trọng khác: API có thể thay đổi trạng thái deprecation giữa các release. Luôn ghi release được quét, phiên bản JDK của công cụ và danh sách artifact đầu vào cùng báo cáo.

## 16. Quy trình migration trong CI

Có thể thêm bước quét deprecated API vào pipeline sau khi compile và trước khi đóng gói:

~~~bash
# 1. Build bytecode theo release mục tiêu
javac --release 17 -Xlint:deprecation \
  -d build/classes \
  @sources.txt

# 2. Quét mọi deprecated Java SE API
jdeprscan --release 17 build/classes

# 3. Quét riêng API for removal
jdeprscan --release 17 --for-removal build/classes

# 4. Quét JAR phát hành
jar --create --file build/app.jar -C build/classes .
jdeprscan --release 17 build/app.jar

# 5. Kiểm thử trên runtime đích
java -cp build/classes demo.Main
~~~

Với migration sang release mới, chạy báo cáo theo cả release hiện tại và release đích:

~~~bash
jdeprscan --release 17 build/app.jar
jdeprscan --release 24 build/app.jar
jdeprscan --release 24 --for-removal build/app.jar
~~~

Quy trình review nên:

1. Lưu output của từng release làm artifact CI.
2. Phân nhóm theo module/package, class sử dụng và API deprecated.
3. Ưu tiên API for removal.
4. Tìm API thay thế và kiểm tra khác biệt semantics.
5. Cập nhật code và test.
6. Quét lại artifact mới.
7. Chạy integration test trên JDK đích.
8. Ghi lại ngoại lệ còn tồn tại, lý do và kế hoạch xử lý.

Không nên làm pipeline thất bại chỉ vì có bất kỳ dòng output nào nếu dự án đang trong giai đoạn migration lớn. Có thể bắt đầu bằng báo cáo và baseline, sau đó đặt quality gate cho API mới hoặc API for removal.

## 17. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jdeprscan` không tìm thấy lệnh | JDK `bin` không có trong PATH. | Kiểm tra `JAVA_HOME` và gọi đúng executable trong thư mục `bin`. |
| Không có kết quả dù source có deprecated call | Đang quét source thay vì class/JAR, hoặc bytecode không chứa tham chiếu mà scanner nhận diện. | Biên dịch source, kiểm tra bytecode bằng `javap -c`, kết hợp compiler lint. |
| `jdeprscan --list` không quét ứng dụng | `--list` chỉ liệt kê catalog, không nhận target đầu vào. | Bỏ `--list` khi cần quét class, thư mục hoặc JAR. |
| Báo cáo khác nhau giữa hai JDK release | Catalog deprecation và trạng thái for-removal thay đổi theo release. | Chọn và ghi rõ `--release` cho từng báo cáo. |
| Class phụ thuộc không được phân giải | Dependency không có trong class path. | Bổ sung `--class-path` với đúng thư mục/JAR. |
| `--for-removal` không chạy với release cũ | Tổ hợp release và tùy chọn không được công cụ hỗ trợ. | Kiểm tra `jdeprscan --help` và dùng release được hỗ trợ. |
| Quét một JAR không phát hiện class trong thư viện phụ thuộc | JAR đầu vào không bao gồm dependency. | Quét riêng dependency hoặc cung cấp class path để phân giải. |
| Compiler warning không xuất hiện | Không bật lint, warning bị suppress hoặc source path không được compile. | Dùng `-Xlint:deprecation`, `-Xlint:removal` và xem annotation suppress. |
| Scanner báo API nhưng không biết cách sửa | Công cụ chỉ phát hiện tham chiếu, không thực hiện migration. | Tra API documentation, đánh giá semantics và viết test trước khi thay. |
| Không có báo cáo nhưng ứng dụng vẫn lỗi trên JDK mới | Có thể do API đã bị xóa, reflection, cấu hình động hoặc vấn đề runtime khác. | Compile/test trên JDK đích và kiểm tra các điểm nạp động, không chỉ dựa vào scanner. |

## 18. Checklist trước khi phát hành

- Đã xác định JDK toolchain dùng để chạy `jdeprscan`.
- Đã chọn `--release` đúng với runtime cần kiểm tra.
- Đầu vào là class directory, JAR, class file hoặc tên lớp hợp lệ.
- Dependency cần thiết đã được cung cấp bằng `--class-path`.
- Đã lưu báo cáo đầy đủ và báo cáo `--for-removal`.
- Đã xem xét từng API deprecated và xác định hướng thay thế.
- Đã bật `javac -Xlint:deprecation` cho source của dự án.
- Đã bật `javac -Xlint:removal` khi phù hợp.
- Không xem báo cáo rỗng là bằng chứng duy nhất về tương thích.
- Các điểm reflection hoặc tải class động đã được review riêng.
- Đã chạy test và integration test trên JDK đích.
- Các ngoại lệ migration còn lại có owner, lý do và kế hoạch xử lý.
- Báo cáo ghi rõ phiên bản công cụ, release được chọn và artifact đã quét.

## 19. Tài liệu tham khảo

- [The jdeprscan Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html)
- [Deprecated Annotation — JDK 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Deprecated.html)
- [Thread API — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Thread.html)

`jdeprscan` giúp phát hiện tham chiếu tới deprecated Java SE API trong bytecode và ưu tiên những API được đánh dấu for removal. Hãy chọn đúng release, quét cả thư mục class lẫn JAR phát hành, kết hợp compiler lint, đánh giá semantics của API thay thế và kiểm thử trên JDK đích trước khi hoàn tất migration.
