# API Deprecated for removal trong Java và cách kiểm tra bằng jdeprscan

## 1. Deprecated for removal nghĩa là gì?

Trong Java, một API được đánh dấu **deprecated** khi nhà phát triển JDK hoặc thư viện khuyến cáo không tiếp tục sử dụng API đó. API vẫn có thể tồn tại và chạy bình thường, nhưng có thể có cách làm tốt hơn, an toàn hơn hoặc phù hợp hơn với thiết kế hiện tại.

Từ Java 9, annotation `@Deprecated` có thêm hai thuộc tính quan trọng:

- `since`: phiên bản mà API bắt đầu bị deprecated.
- `forRemoval`: cho biết API đã được đánh dấu để xem xét loại bỏ trong một bản phát hành tương lai.

Ví dụ:

~~~java
@Deprecated(since = "17", forRemoval = true)
public void oldOperation() {
    // Legacy implementation
}
~~~

`forRemoval = true` có nghĩa API được đánh dấu là **deprecated for removal**. Đây là tín hiệu mạnh hơn deprecation thông thường: code mới không nên phụ thuộc vào API đó và code hiện tại cần có kế hoạch thay thế.

Nếu chỉ viết:

~~~java
@Deprecated(since = "17")
public void legacyOperation() {
}
~~~

thì `forRemoval` mặc định là `false`. API đã deprecated nhưng chưa được đánh dấu để loại bỏ.

Hai trạng thái cần phân biệt:

| Trạng thái | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Deprecated | Không khuyến nghị dùng nữa | Ưu tiên API thay thế khi sửa hoặc mở rộng code |
| Deprecated for removal | Được đánh dấu để loại bỏ trong tương lai | Lập kế hoạch di chuyển và loại bỏ dependency sớm |

Đánh dấu for removal không có nghĩa API sẽ biến mất ngay trong phiên bản kế tiếp. Annotation không đưa ra một ngày hoặc phiên bản loại bỏ chắc chắn. Hãy kiểm tra Javadoc và release note của phiên bản JDK mục tiêu để biết lý do, hướng thay thế và trạng thái hiện tại.

## 2. Annotation @Deprecated và Javadoc @deprecated

Annotation `@Deprecated` cung cấp metadata cho compiler, IDE và công cụ phân tích. Block tag `@deprecated` trong Javadoc giải thích cho người dùng API vì sao không nên dùng nữa và nên chuyển sang đâu.

Ví dụ một API cũ có hướng thay thế:

~~~java
/**
 * Returns the legacy identifier.
 *
 * @deprecated Use {@link #identifier()} instead.
 */
@Deprecated(since = "17", forRemoval = true)
public String oldIdentifier() {
    return identifier();
}

/** Returns the current identifier. */
public String identifier() {
    return "current";
}
~~~

Một documentation comment tốt nên nêu:

- Lý do API bị deprecated.
- API hoặc cách làm thay thế nếu có.
- Khác biệt hành vi cần chú ý khi chuyển đổi.
- Phiên bản bắt đầu deprecated nếu thông tin đó hữu ích.

Không phải API deprecated for removal nào cũng có một phương thức thay thế tương đương. Nếu không có replacement trực tiếp, hãy mô tả hướng thiết kế cần chuyển sang thay vì đưa ra một thay thế sai ngữ nghĩa.

## 3. Compiler phân biệt deprecation và removal warning

Compiler có thể cảnh báo khi source code sử dụng API deprecated. Với API được đánh dấu `forRemoval = true`, cảnh báo thường được phân loại là **removal warning**.

Hai nhóm lint hữu ích:

| Tùy chọn javac | Mục đích |
|---|---|
| `-Xlint:deprecation` | Hiển thị cảnh báo sử dụng API deprecated |
| `-Xlint:removal` | Hiển thị cảnh báo sử dụng API deprecated for removal |

Có thể bật cả hai:

~~~bash
javac --release 17 -Xlint:deprecation,removal -d build/classes src/demo/LegacyApiScan.java
~~~

Compiler có thể hiển thị dạng:

~~~text
warning: [deprecation] getYear() in Date has been deprecated
warning: [removal] privilegedThreadFactory() in Executors has been deprecated and marked for removal
2 warnings
~~~

`-Xlint:removal` hữu ích vì nó giúp phân biệt API chỉ deprecated với API đã được đánh dấu để loại bỏ. Có thể dùng `-Werror` trong build nếu chính sách dự án yêu cầu warning phải làm build thất bại; hãy xử lý warning trước khi bật chế độ nghiêm ngặt cho toàn bộ dự án.

Compiler chỉ cảnh báo khi mã nguồn được biên dịch lại. Một JAR đã biên dịch từ lâu có thể chứa tham chiếu đến API sắp bị loại bỏ mà không còn log compile nào trong lần build hiện tại. Đây là lý do cần quét bytecode bằng `jdeprscan`.

## 4. jdeprscan là gì?

`jdeprscan` là công cụ dòng lệnh đi kèm JDK, dùng để phân tích class file, thư mục class hoặc JAR và tìm việc sử dụng các API deprecated của nền tảng Java.

Công cụ đặc biệt hữu ích khi:

- Ứng dụng có nhiều module, package hoặc JAR đã biên dịch.
- Source code không còn đầy đủ hoặc không thể biên dịch ngay.
- Muốn kiểm kê API deprecated trong artifact trước khi nâng cấp JDK.
- Muốn tập trung vào các API đã đánh dấu for removal.
- Muốn so sánh danh sách API theo phiên bản Java mục tiêu.

`jdeprscan` đọc tham chiếu trong bytecode và đối chiếu với danh mục API deprecated của Java SE trong release được chọn. Nó không thay thế compiler, unit test hoặc kiểm thử runtime.

Một điểm quan trọng về phạm vi: `jdeprscan` tập trung vào API deprecated của nền tảng Java mà công cụ biết theo release catalogue. Nó không phải bộ quét tổng quát để tìm mọi annotation `@Deprecated` trong mọi thư viện bên thứ ba hoặc API nội bộ do dự án tự định nghĩa. Hãy dùng thêm compiler, IDE, static analysis hoặc công cụ riêng của thư viện khi cần kiểm tra các API đó.

## 5. Cú pháp và các tùy chọn chính

Cú pháp tổng quát:

~~~bash
jdeprscan [options] {dir|jar|class} ...
~~~

Đối tượng đầu vào có thể là:

- Một thư mục gốc chứa package hierarchy và class file.
- Một JAR.
- Một class file.
- Tên class đầy đủ package, ví dụ `demo.LegacyApiScan`.

Với nested class, tên class có thể dùng dấu `$`, ví dụ `java.lang.Thread$State`.

Các tùy chọn quan trọng:

| Tùy chọn | Chức năng |
|---|---|
| `--for-removal` | Chỉ báo cáo API deprecated for removal |
| `--release N` | Chọn danh mục API deprecated theo Java SE release N |
| `--class-path PATH` | Chỉ định nơi tìm class phụ thuộc để phân giải tham chiếu |
| `--list` hoặc `-l` | Liệt kê API deprecated trong danh mục, không quét artifact |
| `--verbose` hoặc `-v` | Hiển thị thông tin xử lý chi tiết hơn |
| `--version` | In phiên bản rút gọn của công cụ |
| `--full-version` | In chuỗi phiên bản đầy đủ |
| `--help`, `-h`, `-?` | Hiển thị trợ giúp |

Ví dụ xem trợ giúp và phiên bản:

~~~bash
jdeprscan --help
jdeprscan --version
jdeprscan --full-version
~~~

Tùy chọn và danh sách release hỗ trợ phụ thuộc JDK được cài. Hãy xem `jdeprscan --help` của chính JDK đang dùng trước khi đưa lệnh vào CI.

## 6. Chỉ tìm API deprecated for removal

Đây là chức năng trực tiếp nhất cho chủ đề này:

~~~bash
jdeprscan --for-removal build/classes
~~~

Lệnh trên quét bytecode trong thư mục `build/classes`, nhưng chỉ hiển thị tham chiếu đến API được đánh dấu để loại bỏ.

Nếu bỏ `--for-removal`:

~~~bash
jdeprscan build/classes
~~~

công cụ sẽ hiển thị cả API deprecated thông thường lẫn API deprecated for removal. Dòng báo cáo có hậu tố `(forRemoval=true)` khi tham chiếu thuộc nhóm cần loại bỏ.

Ví dụ định dạng đầu ra:

~~~text
Directory build/classes:
class demo/LegacyApiScan uses deprecated method java/util/concurrent/Executors::privilegedThreadFactory()Ljava/util/concurrent/ThreadFactory; (forRemoval=true)
~~~

Dòng kết quả cho biết:

- `demo/LegacyApiScan` là class đang sử dụng API.
- `java/util/concurrent/Executors` là class thuộc JDK chứa API được gọi.
- `privilegedThreadFactory()` là method được sử dụng.
- `(forRemoval=true)` xác nhận API được đánh dấu để loại bỏ.

`jdeprscan` là công cụ báo cáo tĩnh. Có kết quả không có nghĩa ứng dụng đã chạy hoặc chắc chắn sẽ lỗi ngay; nó chỉ ra dependency cần được xem xét.

## 7. Chọn API catalogue bằng --release

Nếu ứng dụng chạy trên Java 17, nên kiểm tra theo danh mục Java 17:

~~~bash
jdeprscan --release 17 build/classes
~~~

Chỉ lọc API for removal trong release đó:

~~~bash
jdeprscan --for-removal --release 17 build/classes
~~~

Nếu không truyền `--release`, công cụ sử dụng danh mục của JDK hiện tại. Chọn `--release` giúp kết quả phản ánh API deprecated theo phiên bản Java mục tiêu, thay vì chỉ theo JDK dùng để chạy công cụ.

Danh mục có thể khác giữa các release. Một API có thể được đánh dấu for removal ở một bản Java mới hơn, trong khi bản cũ chỉ ghi nhận là deprecated thông thường. Vì vậy:

- Chọn release tương ứng với runtime mà ứng dụng đang hỗ trợ.
- Chạy lại scan khi nâng target Java.
- Không so sánh kết quả giữa hai JDK mà quên ghi rõ `--release`.
- Cập nhật JDK scanner khi muốn kiểm tra release mới hơn mà phiên bản công cụ cũ chưa hỗ trợ.

Ví dụ xem danh sách API for removal trong Java 17:

~~~bash
jdeprscan --list --release 17 --for-removal
~~~

`--list` chỉ in danh mục API. Không truyền thư mục, class hoặc JAR vào cùng chế độ này vì lúc đó bạn đang liệt kê catalogue, không quét ứng dụng.

## 8. Quét JAR và class phụ thuộc

Quét một JAR:

~~~bash
jdeprscan --for-removal --release 17 build/libs/application.jar
~~~

Nếu bytecode tham chiếu đến class khác cần được phân giải, thêm classpath:

~~~bash
jdeprscan --for-removal --release 17 --class-path "lib/*" build/libs/application.jar
~~~

Quét một class theo tên đầy đủ:

~~~bash
jdeprscan --for-removal --release 17 --class-path build/classes demo.LegacyApiScan
~~~

`--class-path` là đường dẫn tìm class phụ thuộc để phân giải tham chiếu. Nó không có nghĩa mọi JAR trong classpath đều tự động trở thành đầu vào cần quét. Hãy đưa từng thư mục hoặc JAR cần phân tích vào danh sách đối số.

Trên Windows, nhiều đường dẫn trong classpath thường phân cách bằng dấu chấm phẩy `;`. Linux và macOS dùng dấu hai chấm `:`.

Trong help của JDK 24.0.2, `jdeprscan` cung cấp `--class-path` nhưng không liệt kê tùy chọn `--module-path`. Khi xử lý ứng dụng modular, hãy kiểm tra cách tổ chức artifact và dependency theo đúng phiên bản công cụ; không tự thêm một tùy chọn không được hỗ trợ.

## 9. Ví dụ Java 17 hoàn chỉnh

Ví dụ dưới đây sử dụng hai API JDK để thấy sự khác nhau:

- `Date.getYear()` là API deprecated thông thường.
- `Executors.privilegedThreadFactory()` được đánh dấu deprecated for removal từ Java 17.

Cấu trúc:

~~~text
project/
  src/
    demo/
      LegacyApiScan.java
  build/
    classes/
~~~

Tệp `src/demo/LegacyApiScan.java`:

~~~java
package demo;

import java.util.Date;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

/** Demonstrates ordinary deprecation and deprecation for removal. */
public final class LegacyApiScan {
    /**
     * Creates and reports legacy API values.
     *
     * @return whether a thread factory was created
     */
    public boolean run() {
        Date date = new Date(0L);
        int legacyYear = date.getYear();

        ThreadFactory factory = Executors.privilegedThreadFactory();

        System.out.println("legacyDateYear=" + legacyYear);
        System.out.println("factoryCreated=" + (factory != null));

        return factory != null;
    }

    /**
     * Runs the example.
     *
     * @param args command-line arguments (not used)
     */
    public static void main(String[] args) {
        new LegacyApiScan().run();
    }
}
~~~

Biên dịch tương thích Java 17:

~~~bash
javac --release 17 -Xlint:deprecation,removal \
    -d build/classes src/demo/LegacyApiScan.java
~~~

Compiler báo hai nhóm warning: một cho `Date.getYear()` và một cho `Executors.privilegedThreadFactory()` đã được đánh dấu for removal.

Chạy chương trình:

~~~bash
java -cp build/classes demo.LegacyApiScan
~~~

Stdout chính xác:

~~~text
legacyDateYear=70
factoryCreated=true
~~~

Quét tất cả API deprecated:

~~~bash
jdeprscan --release 17 build/classes
~~~

Kết quả có hai tham chiếu, một đến `Date.getYear()` và một đến `Executors.privilegedThreadFactory()`.

Chỉ quét API for removal:

~~~bash
jdeprscan --for-removal --release 17 build/classes
~~~

Dòng quan trọng:

~~~text
class demo/LegacyApiScan uses deprecated method java/util/concurrent/Executors::privilegedThreadFactory()Ljava/util/concurrent/ThreadFactory; (forRemoval=true)
~~~

`Date.getYear()` không còn xuất hiện trong kết quả lọc vì nó deprecated nhưng không được đánh dấu for removal trong catalogue Java 17. Đây là khác biệt mà tùy chọn `--for-removal` giúp thể hiện.

## 10. Kết hợp jdeprscan với javac trong quy trình nâng cấp

Một quy trình kiểm tra hữu ích có hai lớp:

1. `javac -Xlint:deprecation,removal` cảnh báo khi biên dịch source.
2. `jdeprscan --for-removal` kiểm tra các class/JAR đã được biên dịch.

Ví dụ:

~~~bash
javac --release 17 -Xlint:deprecation,removal \
    -d build/classes src/demo/*.java

jdeprscan --for-removal --release 17 build/classes
~~~

Trong CI, có thể chạy scan trên:

- Thư mục class output của ứng dụng.
- JAR do dự án tạo ra.
- Các JAR nội bộ được đóng gói cùng sản phẩm.
- Các artifact dependency mà nhóm có trách nhiệm duy trì.

Giữ kết quả scan làm artifact của build để so sánh giữa các lần phát hành. Nếu có kết quả mới, tạo công việc migration cho module hoặc class liên quan.

Không nên chỉ kiểm tra mã nguồn chính rồi kết luận toàn bộ sản phẩm sạch. Một dependency đã biên dịch có thể tiếp tục gọi API cũ dù source của ứng dụng không trực tiếp sử dụng API đó.

## 11. Cách xử lý kết quả scan

Khi `jdeprscan` báo một API for removal:

1. Xác định class trong ứng dụng đang gọi API.
2. Tìm đúng API JDK và đọc Javadoc của release mục tiêu.
3. Kiểm tra lý do deprecated và replacement được đề xuất.
4. Xác định dependency trực tiếp hay gián tiếp.
5. Thay thế API và kiểm tra thay đổi về hành vi.
6. Biên dịch lại, chạy test và quét lại artifact.

Không thay thế máy móc chỉ dựa trên tên method. Hai API có tên gần giống có thể có semantics, quyền truy cập, bảo mật hoặc lifecycle khác nhau.

Ví dụ, `Thread.stop()` là API không an toàn vì có thể dừng thread giữa lúc đang giữ trạng thái dùng chung. Nếu code đang dựa vào việc ép dừng thread, hướng sửa thường là thiết kế hủy tác vụ có phối hợp: đặt cờ hủy, gọi `interrupt()` khi phù hợp, và để code đang chạy kiểm tra trạng thái hủy ở các điểm an toàn.

Với `Executors.privilegedThreadFactory()`, hãy xem lại lý do code cần access-control context và thiết kế bảo mật hiện tại của ứng dụng. Không thay bằng một factory khác nếu điều đó làm thay đổi giả định quyền hoặc ranh giới bảo mật.

Sau khi sửa, chạy lại cả test chức năng lẫn scan. Mục tiêu là loại dependency không còn phù hợp mà vẫn giữ đúng hành vi và chính sách bảo mật.

## 12. Giới hạn của jdeprscan

`jdeprscan` là một công cụ kiểm kê bytecode, không phải bằng chứng đầy đủ rằng ứng dụng tương thích với JDK mới.

Nó có một số giới hạn:

- Chỉ báo cáo API deprecated thuộc catalogue Java mà phiên bản scanner biết.
- Không tự phát hiện mọi API deprecated trong thư viện bên thứ ba hoặc API do dự án tự tạo.
- Không thể suy ra mọi lời gọi được tạo động qua reflection, tên class dạng chuỗi, script hoặc cấu hình.
- Không kiểm tra logic nghiệp vụ hoặc hành vi thực tế của ứng dụng.
- Không thay thế unit test, integration test, kiểm thử bảo mật và kiểm thử trên JDK mục tiêu.
- Chỉ quét các artifact được truyền vào; classpath hỗ trợ phân giải dependency chứ không tự động yêu cầu quét mọi dependency.
- Kết quả phụ thuộc release catalogue và phiên bản JDK của công cụ.

Vì vậy, dùng `jdeprscan` cùng compiler lint, kiểm tra dependency, static analysis và test suite. Nếu thư viện bên thứ ba có API riêng được đánh dấu `@Deprecated(forRemoval=true)`, cần dựa vào tài liệu, compiler warning hoặc công cụ hiểu metadata của thư viện đó.

## 13. Lỗi thường gặp và cách xử lý

### Không có kết quả dù source có API deprecated

`jdeprscan` quét bytecode, không quét file `.java`. Hãy biên dịch source trước rồi quét thư mục class hoặc JAR.

### Quên tùy chọn --for-removal

Không có `--for-removal`, scanner có thể báo cả API deprecated thông thường. Nếu chỉ cần danh sách API được đánh dấu để loại bỏ, hãy thêm tùy chọn này.

### Chọn sai --release

Nếu ứng dụng chạy trên Java 17 nhưng scanner mặc định dùng catalogue của JDK 24, một số API có thể có trạng thái khác. Chọn `--release 17` để kiểm tra theo nền tảng mục tiêu.

### Scanner không phân giải được dependency

Thêm dependency cần thiết vào `--class-path`. Kiểm tra đúng thư mục hoặc JAR và dấu phân cách path theo hệ điều hành.

### Nghĩ rằng --list quét ứng dụng

`--list` chỉ liệt kê API deprecated trong catalogue. Muốn quét, bỏ `--list` và truyền thư mục, JAR hoặc class cần kiểm tra.

### Nghĩ rằng scan sạch nghĩa là không còn API nguy hiểm

Scan sạch chỉ có nghĩa không tìm thấy tham chiếu thuộc catalogue đã chọn trong các artifact đã quét. Nó không chứng minh không có reflection, dependency chưa quét, API bên thứ ba deprecated hoặc vấn đề runtime khác.

## 14. Checklist trước khi nâng cấp JDK

- [ ] Xác định JDK runtime mục tiêu của ứng dụng.
- [ ] Dùng phiên bản `jdeprscan` hỗ trợ release cần kiểm tra.
- [ ] Biên dịch source với `-Xlint:deprecation,removal`.
- [ ] Quét thư mục class và JAR của ứng dụng.
- [ ] Dùng `--for-removal` để tập trung vào API có nguy cơ bị loại bỏ.
- [ ] Dùng `--release` phù hợp với runtime mục tiêu.
- [ ] Kiểm tra dependency mà nhóm đang duy trì.
- [ ] Đọc Javadoc để tìm replacement và lý do deprecation.
- [ ] Đánh giá lại thay đổi hành vi và chính sách bảo mật khi thay thế.
- [ ] Chạy unit test, integration test và test trên JDK đích.
- [ ] Lưu kết quả scan để so sánh trong CI và các lần phát hành sau.

`@Deprecated(forRemoval=true)` là tín hiệu cần lập kế hoạch migration. `jdeprscan --for-removal` giúp tìm tham chiếu đến các API Java SE đã mang tín hiệu đó trong bytecode, còn compiler lint giúp phát hiện ngay khi source được biên dịch. Kết hợp hai cách sẽ giảm nguy cơ phụ thuộc vào API có thể bị loại bỏ trong các bản Java tiếp theo.
