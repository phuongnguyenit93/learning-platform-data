# Lệnh jdeprscan trong JDK

`jdeprscan` là công cụ dòng lệnh đi kèm JDK dùng để quét bytecode Java và tìm các tham chiếu tới API đã bị đánh dấu deprecated. Công cụ giúp nhóm phát triển kiểm tra ứng dụng và thư viện trước khi nâng cấp JDK, xác định API đã lỗi thời đang được sử dụng, đồng thời ưu tiên xử lý những API đã được đánh dấu sẽ bị loại bỏ.

Khác với cảnh báo deprecation của `javac` khi biên dịch source, `jdeprscan` có thể kiểm tra các class file và JAR đã được build, kể cả artifact của thư viện bên thứ ba. Nó báo cáo nơi bytecode tham chiếu tới API deprecated để nhóm phát triển điều tra và lập kế hoạch thay thế.

## 1. jdeprscan dùng để làm gì?

Java đánh dấu một API là deprecated khi API đó không còn được khuyến nghị sử dụng. API vẫn có thể hoạt động, nhưng nhà phát triển nên chuyển sang lựa chọn mới hơn hoặc an toàn hơn.

Ví dụ, `java.util.Date.getYear()` đã deprecated từ lâu. Một số API còn được đánh dấu `forRemoval=true` để báo hiệu chúng dự kiến bị loại bỏ trong một phiên bản Java tương lai.

`jdeprscan` hỗ trợ các công việc:

- Quét class file sau khi biên dịch để tìm tham chiếu tới API deprecated.
- Quét một thư mục chứa cây package đã biên dịch.
- Quét file JAR của ứng dụng hoặc thư viện.
- Quét một lớp theo tên đầy đủ nếu lớp có thể được tìm thấy qua classpath.
- Chỉ hiển thị API đã deprecated và được đánh dấu sẽ bị loại bỏ bằng `--for-removal`.
- Liệt kê tập API deprecated có trong một Java SE release bằng `--list`.
- Chọn release làm mốc đối chiếu bằng `--release`.
- Thêm thông tin xử lý bằng `--verbose`.

Công cụ hữu ích trong migration assessment, kiểm tra thư viện cũ, chuẩn bị nâng cấp JDK và bổ sung kiểm tra tương thích vào CI.

## 2. Deprecation và forRemoval khác nhau thế nào?

Annotation `java.lang.Deprecated` có hai thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `since` | Phiên bản Java mà API được đánh dấu deprecated. |
| `forRemoval` | Cho biết API đã được đánh dấu để loại bỏ trong tương lai hay chưa. |

Ví dụ:

~~~java
@Deprecated(since = "9")
public void oldMethod() {
}
~~~

API trên đã deprecated nhưng không khai báo `forRemoval=true`.

Một API được đánh dấu để loại bỏ:

~~~java
@Deprecated(since = "1.2", forRemoval = true)
public void stop() {
}
~~~

Khi dùng `jdeprscan`:

- Quét thông thường tìm các tham chiếu tới API deprecated.
- `--for-removal` giới hạn kết quả vào các API có `forRemoval=true` trong release được chọn.
- API được đánh dấu for removal cần được ưu tiên đánh giá vì rủi ro tương thích cao hơn.

Deprecated không đồng nghĩa API đã bị xóa. `jdeprscan` giúp tìm nơi sử dụng; nhóm phát triển vẫn cần đọc tài liệu API để chọn phương án thay thế đúng.

## 3. Kiểm tra JDK và cú pháp cơ bản

`jdeprscan` là công cụ thuộc JDK. Kiểm tra môi trường:

~~~bash
java -version
jdeprscan --version
~~~

Xem trợ giúp:

~~~bash
jdeprscan --help
~~~

Cú pháp tổng quát:

~~~text
jdeprscan [options] {dir|jar|class} ...
~~~

Các đối số đầu vào có thể là:

- Thư mục gốc của một cây package chứa class file.
- File JAR.
- Đường dẫn tới một class file.
- Tên lớp đầy đủ, ví dụ `com.acme.LegacyApiDemo`.

Tên lớp lồng nhau sử dụng dấu `$` làm ký tự phân cách, ví dụ `java.lang.Thread$State`. Trong shell có xử lý biến như Bash, hãy đặt tên lớp trong dấu nháy đơn để dấu `$` không bị shell diễn giải.

`jdeprscan` quét bytecode đã biên dịch. Nó không nhận file source `.java` làm đầu vào quét trực tiếp. Hãy biên dịch source trước, sau đó quét thư mục class hoặc JAR đầu ra.

## 4. Các tùy chọn thường dùng

Các tùy chọn được JDK 24.0.2 cung cấp:

| Tùy chọn | Chức năng |
|---|---|
| `--class-path PATH` | Cung cấp đường dẫn tìm các class phụ thuộc khi phân giải. |
| `--for-removal` | Chỉ quét hoặc liệt kê API deprecated có đánh dấu for removal. |
| `--full-version` | In chuỗi phiên bản đầy đủ của công cụ. |
| `--help`, `-h`, `-?` | In hướng dẫn sử dụng. |
| `--list`, `-l` | Liệt kê tập API deprecated, không thực hiện quét đầu vào. |
| `--release N` | Chọn Java SE release dùng làm mốc API để quét. |
| `--verbose`, `-v` | In thêm thông tin trong quá trình xử lý. |
| `--version` | In phiên bản rút gọn của công cụ. |

Danh sách release được hỗ trợ phụ thuộc phiên bản JDK cài đặt. Trên JDK 24.0.2 được dùng để kiểm chứng bài này, `--release` hỗ trợ các giá trị từ 8 đến 24.

Không nên sao chép cứng danh sách release vào script dùng lâu dài. Khi đổi JDK, chạy `jdeprscan --help` để xem phạm vi release mà bản công cụ mới hỗ trợ.

## 5. Chọn release bằng --release

`--release` chọn phiên bản Java SE làm mốc xác định API deprecated. Đây là lựa chọn quan trọng khi đánh giá một ứng dụng cho mục tiêu nâng cấp cụ thể.

Ví dụ:

~~~bash
jdeprscan --release 17 build/classes
~~~

Lệnh yêu cầu công cụ đối chiếu các tham chiếu trong bytecode với tập API deprecated của Java SE 17.

Quét theo release mới hơn:

~~~bash
jdeprscan --release 24 build/classes
~~~

Cùng một API có thể có trạng thái deprecation khác nhau giữa các release. Ví dụ đã kiểm chứng trên JDK 24.0.2:

- Trong danh sách API for removal của release 17, `java.lang.Thread.stop()` không xuất hiện.
- Trong danh sách API for removal của release 24, phương thức này xuất hiện với `@Deprecated(since="1.2", forRemoval=true)`.

Do đó, khi chuẩn bị nâng cấp lên JDK 24, cần quét theo release 24 để nhìn thấy các API được đánh dấu for removal ở release đó. Chọn release gần với mục tiêu migration giúp kết quả có ý nghĩa hơn.

Nếu bỏ `--release`, công cụ sử dụng tập API của JDK đang chạy. Để kết quả CI có thể tái lập, nên ghi rõ release thay vì phụ thuộc ngầm vào JDK cài trên agent build.

Trong JDK 24, `--for-removal` không thể dùng cùng `--release 8`. Kiểm tra trợ giúp của phiên bản công cụ đang dùng trước khi kết hợp các tùy chọn.

## 6. Quét thư mục chứa class file

Sau khi biên dịch ứng dụng, có thể quét toàn bộ thư mục đầu ra:

~~~bash
javac -d build/classes src/com/acme/LegacyApiDemo.java
jdeprscan --release 24 build/classes
~~~

Thư mục được truyền vào là root của cây package. Công cụ duyệt các class file bên dưới để tìm tham chiếu deprecated.

Ví dụ cấu trúc:

~~~text
build/
└── classes/
    └── com/
        └── acme/
            ├── LegacyApiDemo.class
            └── service/
                └── LegacyService.class
~~~

Lệnh quét `build/classes` có thể tìm kết quả trong cả `LegacyApiDemo.class` và `LegacyService.class`.

Nếu chỉ muốn quét một class file cụ thể:

~~~bash
jdeprscan --release 24 build/classes/com/acme/LegacyApiDemo.class
~~~

Cách này phù hợp khi điều tra một class cụ thể hoặc thu hẹp phạm vi của một báo cáo lớn.

## 7. Quét file JAR

`jdeprscan` nhận trực tiếp đường dẫn JAR:

~~~bash
jdeprscan --release 24 build/legacy-demo.jar
~~~

JAR thường chứa nhiều package và class. Quét JAR giúp kiểm tra artifact sau khi đóng gói, đúng với nội dung dự kiến phân phối.

Ví dụ tạo JAR từ thư mục class:

~~~bash
jar --create --file build/legacy-demo.jar -C build/classes .
jdeprscan --release 24 build/legacy-demo.jar
~~~

Có thể quét nhiều đầu vào trong cùng một lần chạy:

~~~bash
jdeprscan --release 24 build/classes build/legacy-demo.jar
~~~

Khi dùng nhiều đầu vào, kết quả được nhóm theo từng thư mục hoặc JAR. Nếu cùng một class xuất hiện ở nhiều đầu vào, báo cáo có thể xuất hiện lặp theo từng artifact được quét.

Nên quét artifact thực tế mà nhóm chuẩn bị phát hành. Quét thư mục class và quét JAR giúp kiểm tra ở hai giai đoạn khác nhau của build pipeline.

## 8. Quét lớp theo tên và classpath

Có thể truyền tên lớp đầy đủ thay vì đường dẫn class file:

~~~bash
jdeprscan --release 24 --class-path build/classes com.acme.LegacyApiDemo
~~~

`--class-path` cung cấp vị trí tìm class và dependency mà công cụ cần phân giải. Tên lớp cần dùng package đầy đủ, không dùng tên đơn giản nếu lớp nằm trong package.

Nếu có nhiều dependency, phân tách theo quy tắc classpath của hệ điều hành:

Linux/macOS:

~~~bash
jdeprscan --release 24 \
  --class-path "build/classes:lib/customer-api.jar:lib/common.jar" \
  com.acme.LegacyApiDemo
~~~

Windows PowerShell:

~~~powershell
jdeprscan --release 24 --class-path "build/classes;lib/customer-api.jar;lib/common.jar" com.acme.LegacyApiDemo
~~~

Tên lớp lồng nhau dùng dấu `$`:

~~~bash
jdeprscan --release 24 --class-path build/classes 'com.acme.Outer$Inner'
~~~

Phân biệt hai vai trò:

- Đối số cuối như `com.acme.LegacyApiDemo` xác định lớp cần quét.
- `--class-path` giúp tìm lớp và dependency phục vụ quá trình phân giải.

Class path không thay thế danh sách đầu vào cần quét. Nếu muốn kiểm tra cả một thư viện, hãy truyền JAR hoặc thư mục chứa class của thư viện đó làm đối số quét.

## 9. Chỉ tìm API được đánh dấu for removal

Khi chuẩn bị nâng cấp JDK, nhóm thường muốn ưu tiên các API có nguy cơ bị loại bỏ.

Dùng:

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

Kết quả chỉ chứa các tham chiếu deprecated được đánh dấu for removal theo release đã chọn.

Có thể kết hợp với JAR:

~~~bash
jdeprscan --release 24 --for-removal build/legacy-demo.jar
~~~

`--for-removal` cũng dùng được với `--list` để xem danh sách API thuộc nhóm này:

~~~bash
jdeprscan --release 24 --for-removal --list
~~~

Lệnh trên chỉ liệt kê API, không quét class, thư mục hoặc JAR. Không truyền đối số đầu vào quét cùng chế độ `--list`.

Nếu cần bức tranh đầy đủ về deprecation, chạy thêm một lượt không có `--for-removal`. Chỉ quét for removal có thể bỏ qua các API deprecated thông thường mà nhóm vẫn muốn thay thế dần.

## 10. Liệt kê API deprecated bằng --list

`--list` hiển thị tập API deprecated được biết đến trong release đã chọn:

~~~bash
jdeprscan --release 24 --list
~~~

Lệnh không quét class file. Nó hữu ích khi cần tra cứu API nào đang được đánh dấu deprecated trong một phiên bản Java.

Lọc danh sách for removal:

~~~bash
jdeprscan --release 24 --for-removal --list
~~~

Một dòng trong danh sách có thể có dạng:

~~~text
@Deprecated(since="1.2", forRemoval=true) void java.lang.Thread.stop()
~~~

Dòng trên thể hiện phương thức `Thread.stop()` được đánh dấu deprecated từ phiên bản 1.2 và hiện có `forRemoval=true` trong tập API của release được chọn.

Trên PowerShell có thể lọc kết quả để tra một API:

~~~powershell
jdeprscan --release 24 --list | Select-String "java.lang.Thread.stop"
~~~

Trên Linux/macOS có thể dùng `grep`:

~~~bash
jdeprscan --release 24 --list | grep 'java.lang.Thread.stop'
~~~

Khi dùng pipe, kết quả hiển thị là phần khớp với bộ lọc. Lệnh `--list` gốc vẫn là nguồn dữ liệu đầy đủ.

## 11. Đọc và hiểu kết quả quét

Ví dụ kết quả thực tế từ JDK 24.0.2 khi quét class directory:

~~~text
Directory out:
class com/acme/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class com/acme/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Cách đọc:

- `Directory out:` cho biết đầu vào đang được quét là thư mục.
- `class com/acme/LegacyApiDemo` là class có tham chiếu tới API deprecated.
- `java/util/Date::getYear()I` xác định class sở hữu API, tên method và JVM descriptor.
- `java/lang/Thread::stop()V` xác định tham chiếu tới `Thread.stop()`.
- `(forRemoval=true)` cho biết API được đánh dấu để loại bỏ.

Tên class trong descriptor dùng dấu gạch chéo xuôi thay cho dấu chấm. Phần sau tên method là JVM descriptor:

| Ký hiệu | Ý nghĩa |
|---|---|
| `()I` | Không có tham số, trả về `int`. |
| `()V` | Không có tham số, trả về `void`. |
| `(Ljava/lang/String;)I` | Nhận một `String`, trả về `int`. |
| `(I)Ljava/lang/String;` | Nhận một `int`, trả về `String`. |

Descriptor giúp phân biệt overload và xác định chính xác chữ ký được bytecode tham chiếu.

Kết quả của JAR có phần mở đầu khác:

~~~text
Jar file legacy-demo.jar:
class com/acme/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class com/acme/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Nếu dùng `--for-removal`, dòng `Date.getYear()` sẽ bị loại khỏi báo cáo, còn `Thread.stop()` vẫn xuất hiện.

## 12. Ví dụ hoàn chỉnh: biên dịch và quét API deprecated

Ví dụ dùng hai API có trạng thái khác nhau:

- `Date.getYear()` là API deprecated thông thường.
- `Thread.stop()` được JDK 24 đánh dấu for removal.

Tạo cấu trúc:

~~~text
jdeprscan-demo/
└── src/
    └── com/
        └── acme/
            └── LegacyApiDemo.java
~~~

Tệp `src/com/acme/LegacyApiDemo.java`:

~~~java
package com.acme;

import java.util.Date;

public class LegacyApiDemo {
    public static void main(String[] args) {
        Date epoch = new Date(12L * 60 * 60 * 1000);
        System.out.println("Legacy year offset: " + epoch.getYear());
    }

    static void stopThread(Thread thread) {
        thread.stop();
    }
}
~~~

Method `stopThread` chỉ minh họa tham chiếu bytecode tới API for removal. Chương trình không gọi method này khi chạy; `Thread.stop()` không nên được dùng để dừng thread trong ứng dụng thực tế.

### Bước 1: Biên dịch

Từ thư mục gốc `jdeprscan-demo`:

~~~bash
javac -Xlint:deprecation -d build/classes src/com/acme/LegacyApiDemo.java
~~~

Compiler sẽ cảnh báo `Date.getYear()` đã deprecated và `Thread.stop()` đã deprecated, được đánh dấu để loại bỏ. Cảnh báo biên dịch phát sinh từ source đang được biên dịch.

### Bước 2: Chạy chương trình

~~~bash
java -cp build/classes com.acme.LegacyApiDemo
~~~

Stdout chính xác:

~~~text
Legacy year offset: 70
~~~

`Date.getYear()` trả về năm trừ đi 1900. Với thời điểm được chọn trong ví dụ, giá trị trả về là 70.

### Bước 3: Quét thư mục class

~~~bash
jdeprscan --release 24 build/classes
~~~

Kết quả:

~~~text
Directory build/classes:
class com/acme/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class com/acme/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

### Bước 4: Chỉ quét API for removal

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

Kết quả:

~~~text
Directory build/classes:
class com/acme/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

### Bước 5: Đóng gói JAR và quét lại

~~~bash
jar --create --file build/legacy-demo.jar -C build/classes .
jdeprscan --release 24 build/legacy-demo.jar
~~~

Kết quả:

~~~text
Jar file build/legacy-demo.jar:
class com/acme/LegacyApiDemo uses deprecated method java/util/Date::getYear()I
class com/acme/LegacyApiDemo uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Ví dụ chứng minh có thể quét thư mục class hoặc JAR và nhận diện cùng các tham chiếu deprecated sau khi đóng gói.

## 13. Verbose và phiên bản công cụ

Dùng `--verbose` để xem thêm thông tin khi công cụ xử lý đầu vào:

~~~bash
jdeprscan --verbose --release 24 build/classes
~~~

Thông tin verbose hữu ích khi cần biết công cụ đang xử lý những class hoặc dependency nào. Output chi tiết có thể khác giữa các bản JDK.

Xem phiên bản rút gọn:

~~~bash
jdeprscan --version
~~~

Xem chuỗi phiên bản đầy đủ:

~~~bash
jdeprscan --full-version
~~~

Khi so sánh kết quả giữa máy developer và CI, hãy ghi nhận phiên bản JDK cùng release baseline. Hai bản jdeprscan khác nhau có thể biết đến tập API deprecated khác nhau.

## 14. Giới hạn của jdeprscan

`jdeprscan` phân tích tham chiếu trong bytecode. Công cụ không thực thi ứng dụng và không thể phát hiện mọi cách một API có thể được sử dụng.

Một số giới hạn quan trọng:

- Không quét source `.java` trực tiếp; cần biên dịch trước.
- Không xác định được mọi lời gọi API được tạo động bằng reflection hoặc tên class/method lưu trong chuỗi.
- Không phân tích logic trong native code hoặc thư viện JNI.
- Không phát hiện mã được tải từ xa hoặc tạo ra sau thời điểm quét nếu artifact đó không nằm trong đầu vào.
- Không quyết định API thay thế nào tương đương về hành vi hoặc an toàn cho ứng dụng.
- Không bảo đảm ứng dụng chạy thành công trên JDK mới chỉ vì báo cáo không có kết quả.

Nếu ứng dụng dùng reflection, plugin, service loader, scripting hoặc native library, cần bổ sung kiểm thử runtime và rà soát cấu hình tương ứng.

Một lần quét không có kết quả chỉ có nghĩa công cụ không tìm thấy tham chiếu deprecated trong phạm vi đầu vào và release đã chọn. Nó không chứng minh toàn bộ hệ thống không sử dụng API deprecated ở mọi đường chạy.

## 15. Diễn giải kết quả và lập kế hoạch migration

Khi thấy một API deprecated, không nên thay thế hàng loạt mà chưa hiểu ngữ nghĩa.

Một quy trình xử lý thực tế:

1. Ghi lại class, method/field và descriptor được báo cáo.
2. Tìm source tương ứng hoặc xác định dependency chứa bytecode đó.
3. Đọc Javadoc của API deprecated để hiểu lý do và phương án thay thế.
4. Đánh giá API mới có giữ nguyên semantics, timezone, thread-safety, exception và hiệu năng hay không.
5. Viết hoặc cập nhật test trước khi thay thế.
6. Build lại toàn bộ ứng dụng và dependency nội bộ.
7. Chạy lại `jdeprscan` với release mục tiêu.
8. Chạy unit test, integration test và test trên JDK mục tiêu.

Ví dụ thay `Date.getYear()`:

~~~java
import java.time.Instant;
import java.time.ZoneId;

int year = Instant.ofEpochMilli(0L)
        .atZone(ZoneId.of("UTC"))
        .getYear();

System.out.println(year);
~~~

Output:

~~~text
1970
~~~

Đoạn code dùng `java.time` để lấy năm lịch theo múi giờ UTC. Đây là giá trị năm đầy đủ, khác với `Date.getYear()` vốn trả về năm trừ 1900. Khi thay API cũ, cần xác định rõ ứng dụng cần giá trị năm đầy đủ hay cần giữ logic legacy.

Với `Thread.stop()`, không thay bằng một API cưỡng bức khác theo kiểu máy móc. Cách dừng thread thông thường là yêu cầu thread tự kết thúc bằng cơ chế cooperative cancellation, thường dùng `Thread.interrupt()` cùng vòng lặp kiểm tra trạng thái interrupt hoặc cơ chế hủy của executor.

Nếu kết quả trỏ tới class trong thư viện bên thứ ba, ưu tiên kiểm tra phiên bản thư viện mới đã loại bỏ API deprecated chưa. Không nên sửa bytecode thư viện bằng tay để che cảnh báo.

## 16. Dùng jdeprscan trong CI

Có thể thêm bước quét sau khi build:

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

Sau đó quét toàn bộ deprecation:

~~~bash
jdeprscan --release 24 build/classes
~~~

Một pipeline migration có thể chia thành hai mức:

- **Mức ưu tiên cao:** rà soát và xử lý API có `forRemoval=true`.
- **Mức duy trì:** theo dõi toàn bộ API deprecated và lên kế hoạch thay thế theo module hoặc release.

Không nên chỉ dựa vào exit code để quyết định không có deprecation. Trong thử nghiệm với JDK 24.0.2, `jdeprscan` trả exit code 0 dù báo cáo có các tham chiếu deprecated. Vì vậy, CI cần lưu và kiểm tra output theo chính sách của dự án, chẳng hạn so sánh với baseline đã duyệt hoặc dùng script riêng để phát hiện kết quả mới.

Một cách triển khai an toàn là:

1. Chạy scan và lưu output thành artifact của build.
2. So sánh kết quả với baseline hiện có.
3. Chặn các tham chiếu for removal mới nếu đó là chính sách dự án.
4. Theo dõi tổng số deprecated usage qua các lần build.
5. Cập nhật baseline sau khi nhóm đã review thay đổi.

Không nên làm build thất bại ngay với mọi warning cũ nếu dự án có lượng legacy lớn. Có thể bắt đầu bằng việc ngăn phát sinh tham chiếu mới, rồi giảm dần baseline theo từng đợt migration.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jdeprscan` không được nhận diện | JDK chưa có trong PATH hoặc đang dùng môi trường chỉ có runtime. | Kiểm tra `java -version` và vị trí JDK; gọi công cụ từ thư mục bin của JDK nếu cần. |
| Không tìm thấy class theo tên | Thiếu package đầy đủ hoặc class không nằm trong classpath. | Dùng tên fully qualified và thêm `--class-path`. |
| Không có kết quả dù source có warning | Đang quét sai thư mục, JAR hoặc class file chưa được build lại. | Kiểm tra artifact thực tế và thời điểm build. |
| Không resolve được dependency | Class phụ thuộc không nằm trên đường dẫn tìm kiếm. | Cung cấp classpath thích hợp hoặc quét artifact có dependency đầy đủ. |
| Không thấy API for removal | Release baseline chưa đánh dấu API đó for removal. | Chọn release mục tiêu phù hợp và kiểm tra `--list`. |
| `--for-removal` không dùng được với release 8 | Tổ hợp tùy chọn không được công cụ hỗ trợ. | Dùng release tương thích hoặc bỏ `--for-removal` khi kiểm tra release 8. |
| Kết quả có nhiều dòng từ thư viện bên thứ ba | JAR được quét có chứa class tham chiếu API deprecated. | Xác định artifact gây ra tham chiếu và cập nhật dependency nếu có phiên bản sửa. |
| Build vẫn thành công dù có báo cáo deprecated | Findings không nhất thiết làm công cụ trả exit code khác 0. | Đọc output và áp dụng chính sách kiểm tra riêng trong CI. |

Nếu cần thêm thông tin chẩn đoán, chạy lại với `--verbose` và thu hẹp đầu vào xuống class hoặc JAR đang gây vấn đề.

## 18. Quy trình kiểm tra khuyến nghị

Một quy trình có thể tái lập:

1. Chọn JDK và release mục tiêu.
2. Build lại ứng dụng để bảo đảm class file phản ánh source hiện tại.
3. Quét thư mục class bằng `jdeprscan --release N`.
4. Quét JAR phân phối để kiểm tra artifact sau đóng gói.
5. Chạy thêm `--for-removal` để ưu tiên API có rủi ro loại bỏ.
6. Dùng `--list` khi cần xác minh trạng thái deprecated của một API.
7. Dùng `--class-path` nếu cần phân giải tên lớp hoặc dependency.
8. Ghi lại kết quả và phiên bản công cụ trong CI.
9. Điều tra từng tham chiếu, thay thế API và bổ sung test.
10. Quét lại và so sánh kết quả với baseline.

`jdeprscan` là công cụ phân tích bytecode phục vụ quản lý vòng đời API. Kết hợp nó với cảnh báo của compiler, kiểm thử runtime, kiểm tra dependency và tài liệu migration sẽ giúp phát hiện sớm các điểm cần thay đổi trước khi nâng cấp Java.
