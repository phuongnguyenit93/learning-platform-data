# Đọc kết quả scan bằng jdeprscan

**jdeprscan** là công cụ trong JDK dùng để tìm các class đã biên dịch đang tham chiếu tới API Java bị đánh dấu deprecated. Khi chạy scan, công cụ xác định class của ứng dụng đang sử dụng method, constructor hoặc field deprecated nào trong API của một Java SE release cụ thể.

Kết quả thường có dạng:

~~~text
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Mỗi dòng cho biết **class bên ứng dụng**, **API deprecated được tham chiếu** và, nếu có, trạng thái **forRemoval=true**. Đây là thông tin đầu vào để xác định phạm vi ảnh hưởng, ưu tiên nâng cấp và tìm cách thay thế API.

Lệnh scan cơ bản:

~~~bash
jdeprscan --release 17 build/classes
~~~

Lệnh trên kiểm tra class trong build/classes theo danh sách API deprecated của Java 17. Tùy chọn --release rất quan trọng: cùng một API có thể được đánh dấu deprecated for removal trong release mới hơn nhưng chưa mang trạng thái đó ở release cũ.

## 1. Kết quả jdeprscan trả lời câu hỏi nào?

jdeprscan phân tích bytecode để tìm tham chiếu tới API đã deprecated. Kết quả giúp trả lời:

- Class nào trong ứng dụng đang dùng API deprecated?
- API được gọi thuộc class hoặc package nào?
- Đó là method, constructor hay field?
- API có được đánh dấu for removal trong release đang chọn không?
- Có thể thay API đó bằng API nào?
- Cần ưu tiên sửa phần nào trước khi nâng cấp JDK?

Công cụ đọc class file, thư mục class hoặc JAR đã biên dịch. Nó không phân tích source Java như một trình lint source thông thường và không chạy ứng dụng.

Ví dụ:

~~~java
import java.util.Date;

public final class LegacyApiUse {
    public static int year(Date date) {
        return date.getYear();
    }
}
~~~

Method Date.getYear() đã deprecated. Sau khi compile, jdeprscan có thể phát hiện class LegacyApiUse đang tham chiếu tới method đó.

Một phát hiện trong output không tự nói rằng ứng dụng đã lỗi khi chạy. Deprecated API vẫn có thể hoạt động ở release hiện tại. Kết quả cảnh báo rằng API đã được đánh dấu không nên tiếp tục dùng và có thể bị loại bỏ trong tương lai nếu được đánh dấu for removal.

## 2. Cấu trúc một dòng kết quả

Ví dụ:

~~~text
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
~~~

Có thể tách thành các phần:

| Phần | Ý nghĩa |
|---|---|
| class | Dòng này là một class đang sử dụng API deprecated |
| LegacyApiUse | Class phía ứng dụng có tham chiếu |
| uses deprecated method | Loại phát hiện: sử dụng method deprecated |
| java/util/Date | Class sở hữu API deprecated |
| getYear | Tên method được sử dụng |
| ()I | JVM method descriptor: không có tham số, trả về int |

### Caller class

Tên ngay sau từ class là class chứa tham chiếu tới API deprecated. Trong ví dụ, LegacyApiUse là caller.

Nếu output có nhiều caller:

~~~text
class com.example.report.ReportService uses deprecated method java/util/Date::getYear()I
class com.example.importer.LegacyReader uses deprecated method java/util/Date::getYear()I
~~~

thì cả ReportService và LegacyReader đều cần được xem xét. Không nên sửa một caller rồi kết luận toàn bộ ứng dụng đã sạch.

### Owner của API deprecated

Tên class phía sau uses deprecated method là nơi khai báo member. Trong ví dụ, java/util/Date là owner.

Tên class được viết theo internal form của JVM, dùng dấu gạch chéo giữa các package thay cho dấu chấm:

~~~text
java/util/Date
java/lang/Thread
java/io/File
~~~

Khi tìm trong Javadoc hoặc source, đổi sang tên đầy đủ thông thường:

~~~text
java.util.Date
java.lang.Thread
java.io.File
~~~

### Member name

Sau dấu hai chấm kép là tên member. Ví dụ:

~~~text
java/util/Date::getYear()I
java/lang/Thread::stop()V
~~~

getYear và stop là method được tham chiếu. Output cũng có thể chỉ ra constructor hoặc field tùy loại API deprecated.

## 3. Đọc JVM method descriptor

Phần trong ngoặc sau tên method là JVM descriptor. Nó mô tả kiểu tham số và kiểu trả về theo định dạng bytecode.

Ví dụ:

~~~text
getYear()I
stop()V
substring(I)Ljava/lang/String;
valueOf(I)Ljava/lang/String;
~~~

Một số ký hiệu cơ bản:

| Ký hiệu | Kiểu Java |
|---|---|
| V | void |
| Z | boolean |
| B | byte |
| C | char |
| S | short |
| I | int |
| J | long |
| F | float |
| D | double |
| Lpackage/Type; | Kiểu tham chiếu |
| [T | Mảng của kiểu T |

Cách đọc:

- getYear()I: không có tham số, trả về int.
- stop()V: không có tham số, trả về void.
- substring(I)Ljava/lang/String;: nhận một int, trả về String.
- valueOf(I)Ljava/lang/String;: nhận một int, trả về String.

Với nhiều tham số, các descriptor được nối liên tiếp trong cặp ngoặc:

~~~text
replace(CC)Ljava/lang/String;
~~~

Ví dụ này có hai tham số char và trả về String.

Descriptor hữu ích khi class có nhiều overload cùng tên. Tên method riêng lẻ có thể chưa đủ để xác định overload; descriptor cho biết chính xác signature mà bytecode tham chiếu.

## 4. Ý nghĩa của forRemoval=true

Một số API deprecated được đánh dấu rõ rằng chúng đang được xem xét để loại bỏ khỏi Java platform. Trong annotation, trạng thái này được biểu diễn bằng thuộc tính forRemoval=true.

Ví dụ output:

~~~text
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Dòng này có nghĩa:

- LegacyApiUse đang tham chiếu tới Thread.stop().
- Method đã deprecated trong release được chọn.
- API được đánh dấu deprecated for removal trong release đó.
- Việc sử dụng cần được ưu tiên xử lý vì API có thể bị loại bỏ trong một release tương lai.

forRemoval=true không cho biết chính xác API sẽ bị xóa ở phiên bản Java nào. Nó là tín hiệu về ý định loại bỏ, không phải lịch xóa đã được cam kết.

Nếu dòng kết quả không có marker forRemoval=true, điều đó chỉ có nghĩa API không được đánh dấu for removal trong bộ dữ liệu release đang dùng. API vẫn có thể deprecated và vẫn cần được thay thế theo kế hoạch.

### Vì sao phải quan tâm release?

Trạng thái deprecated của API có thể thay đổi theo thời gian. Một API có thể:

1. Chưa deprecated trong release cũ.
2. Được deprecated trong release tiếp theo.
3. Sau đó được đánh dấu for removal.
4. Có thể bị loại bỏ ở một release về sau.

Do đó, khi đọc kết quả scan, luôn ghi nhận release được dùng để phân tích.

## 5. --release thay đổi cách diễn giải kết quả

Tùy chọn --release chỉ định Java SE release cung cấp tập API deprecated để đối chiếu.

~~~bash
jdeprscan --release 17 build/classes
~~~

Lệnh trên dùng tập API deprecated của Java 17.

~~~bash
jdeprscan --release 24 build/classes
~~~

Lệnh trên dùng tập API deprecated của Java 24.

Tùy chọn này **không biên dịch lại class**, không thay đổi bytecode và không tự kiểm tra class file có tương thích với release đó hay không. Nó chọn bộ dữ liệu API deprecated mà jdeprscan dùng để đối chiếu.

### Ví dụ đã xác minh trên JDK 24.0.2

Một class được biên dịch với --release 17 sử dụng Date.getYear() và Thread.stop(). Khi scan theo Java 17, kết quả:

~~~text
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V
~~~

Khi scan cùng class theo Java 24:

~~~text
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Có thể thấy Thread.stop() được đánh dấu forRemoval=true trong tập API Java 24, nhưng chưa có marker đó trong tập API Java 17.

Đây là lý do không nên đọc một kết quả scan mà bỏ qua release. Một báo cáo không có marker forRemoval=true không chứng minh API sẽ không bị loại bỏ; nó chỉ phản ánh metadata của release được chọn.

### Chọn release nào?

- Chọn release mà ứng dụng đang hỗ trợ để biết API deprecated theo baseline hiện tại.
- Chọn release JDK dự định nâng cấp tới để biết các cảnh báo theo mục tiêu tương lai.
- Nếu đang chuẩn bị nâng cấp nhiều bước, scan lần lượt từng release mục tiêu.
- Ghi lại release và phiên bản công cụ cùng báo cáo để kết quả có thể tái lập.

JDK 24.0.2 liệt kê các giá trị --release từ 8 đến 24. Danh sách release được hỗ trợ thay đổi theo phiên bản jdeprscan; kiểm tra --help của JDK đang dùng thay vì giả định mọi JDK hỗ trợ cùng một dải.

## 6. --for-removal: chỉ xem API có nguy cơ bị loại bỏ

Tùy chọn:

~~~bash
jdeprscan --for-removal build/classes
~~~

chỉ giữ lại các API được đánh dấu deprecated for removal trong tập API mà công cụ đang dùng.

Kết hợp với release cụ thể:

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

Trong ví dụ LegacyApiUse, kết quả chỉ còn Thread.stop():

~~~text
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Date.getYear() vẫn deprecated, nhưng không được đánh dấu for removal trong tập API đó nên bị lọc khỏi output.

Đây là cách hữu ích để ưu tiên việc cần làm:

- Chạy scan thông thường để có toàn bộ deprecated API.
- Chạy thêm --for-removal để lập danh sách ưu tiên cao.
- Không bỏ qua API deprecated thông thường; chúng vẫn cần được đánh giá và thay thế.
- Theo dõi riêng các API for removal trong kế hoạch nâng cấp JDK.

Theo trợ giúp của JDK 24, --for-removal không được kết hợp với --release 6, 7 hoặc 8. Hãy kiểm tra giới hạn tương ứng trong phiên bản công cụ đang sử dụng.

## 7. --list: tra cứu danh sách API deprecated

Có thể dùng jdeprscan để xem tập API deprecated của một release mà không scan class nào.

~~~bash
jdeprscan --list
~~~

Lệnh này liệt kê API deprecated của release mặc định (JDK đang chạy).

Chỉ liệt kê API for removal:

~~~bash
jdeprscan --list --for-removal
~~~

Tra cứu theo Java 17:

~~~bash
jdeprscan --list --release 17
~~~

Lưu ý: --list chỉ liệt kê danh sách API, không thực hiện scan. Không truyền thư mục, JAR hoặc class làm đối số scan trong cùng chế độ này.

Output của --list thường cung cấp chữ ký API và metadata annotation. Ví dụ đã quan sát trên JDK 24:

~~~text
@Deprecated(since="1.2", forRemoval=true) void java.lang.Thread.stop()
@Deprecated(since="9", forRemoval=true) void java.lang.Object.finalize()
@Deprecated int java.util.Date.getYear()
~~~

Khi dùng --list --release 17, Thread.stop() và Object.finalize() xuất hiện là deprecated nhưng không có forRemoval=true trong metadata của release đó. Date.getYear() cũng là deprecated.

Danh sách này giúp tra cứu trạng thái API và thời điểm deprecated (since) khi cần quyết định hướng thay thế. Nó không tự cho biết class nào trong ứng dụng đang gọi API; cần scan artifact để tìm caller.

## 8. Đọc header và nhóm kết quả

Khi scan thư mục, jdeprscan có thể in header:

~~~text
Directory C:\work\app\classes:
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
~~~

Header cho biết đối tượng đang được scan. Các dòng sau là phát hiện trong đối tượng đó.

Khi scan JAR, header có thể chỉ ra archive đang được xử lý. Khi truyền nhiều đầu vào, hãy đọc từng header để biết phát hiện thuộc thư mục hoặc JAR nào.

Nếu có nhiều class cùng sử dụng một API, output có thể chứa nhiều dòng. Khi tổng hợp báo cáo:

- Nhóm theo API deprecated để biết API nào được dùng nhiều nơi.
- Nhóm theo caller class để xác định module hoặc package cần sửa.
- Giữ nguyên release dùng khi scan.
- Giữ marker forRemoval=true trong dữ liệu tổng hợp.
- Không gộp các overload có descriptor khác nhau thành một phát hiện duy nhất nếu cần truy vết chính xác.

Một API có thể xuất hiện trong nhiều caller. Một caller cũng có thể sử dụng nhiều API deprecated. Đây là quan hệ nhiều-nhiều.

## 9. Scan thư mục, class file và JAR

Cú pháp tổng quát:

~~~bash
jdeprscan [options] {dir|jar|class} ...
~~~

Các loại đầu vào:

- Thư mục là root của package hierarchy chứa class file.
- JAR là archive cần phân tích.
- Class file là file .class cụ thể.
- Class name là tên đầy đủ của class; nested class dùng dấu $ để phân tách.

Ví dụ scan thư mục:

~~~bash
jdeprscan --release 17 build/classes
~~~

Scan một class file:

~~~bash
jdeprscan --release 17 build/classes/com/example/LegacyApiUse.class
~~~

Scan một JAR:

~~~bash
jdeprscan --release 17 build/libs/application.jar
~~~

Scan nested class bằng class name:

~~~bash
jdeprscan --release 17 'com.example.Outer$Nested'
~~~

Khi dùng tên class thay vì đường dẫn file, class name phải fully qualified. Dấu $ trong tên nested class cần được giữ nguyên; trên shell có thể đặt trong dấu nháy để tránh xử lý đặc biệt.

### Scan nhiều artifact

Có thể truyền nhiều đầu vào:

~~~bash
jdeprscan --release 17 \
    build/libs/application.jar \
    build/libs/legacy-adapter.jar \
    build/classes
~~~

Điều này giúp audit nhiều phần của sản phẩm trong một lượt. Tuy nhiên, cần lưu ý phạm vi: jdeprscan scan các đầu vào được truyền. Việc một JAR có mặt trong classpath để phân giải dependency không đồng nghĩa JAR đó tự động trở thành đối tượng scan.

## 10. Classpath dùng để phân giải dependency

Tùy chọn --class-path chỉ định nơi tìm class phụ thuộc khi jdeprscan cần phân giải tham chiếu.

Ví dụ:

~~~bash
jdeprscan \
    --release 17 \
    --class-path "lib/common.jar;lib/vendor.jar" \
    build/classes
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy. Trên Linux/macOS, dùng dấu hai chấm:

~~~bash
jdeprscan \
    --release 17 \
    --class-path "lib/common.jar:lib/vendor.jar" \
    build/classes
~~~

Classpath giúp công cụ tìm các class mà đầu vào tham chiếu tới. Nó không phải danh sách các artifact sẽ được scan.

Nếu muốn scan cả application.jar và vendor.jar, hãy truyền cả hai làm đầu vào:

~~~bash
jdeprscan --release 17 \
    --class-path lib/common.jar \
    application.jar \
    vendor.jar
~~~

Nếu một class dependency không được tìm thấy, kết quả scan có thể không đầy đủ hoặc công cụ có thể báo lỗi phân giải. Hãy bổ sung đúng JAR và chạy lại.

Trong trợ giúp JDK 24, jdeprscan có tùy chọn --class-path nhưng không liệt kê --module-path. Đừng tự suy ra cú pháp module path từ các công cụ khác như jdeps hoặc javac. Hãy xem --help của đúng JDK khi xử lý modular artifact và bảo đảm mọi dependency cần phân giải đều có sẵn theo cơ chế mà phiên bản jdeprscan hỗ trợ.

## 11. --verbose và các tùy chọn hiển thị khác

Tùy chọn --verbose hoặc -v bật thêm thông tin trong quá trình xử lý:

~~~bash
jdeprscan --verbose --release 17 build/classes
~~~

Verbose hữu ích khi cần chẩn đoán cách công cụ xử lý đầu vào. Tuy nhiên, không nên giả định nó sẽ thêm source line number cho mọi finding. Output chính của jdeprscan xác định caller class và API deprecated, nhưng thường không cho biết chính xác dòng source.

Các tùy chọn phiên bản:

~~~bash
jdeprscan --version
jdeprscan --full-version
~~~

--version in phiên bản rút gọn; --full-version in chuỗi phiên bản đầy đủ của công cụ.

Trước khi viết script CI, xem trợ giúp:

~~~bash
jdeprscan --help
~~~

Đặc biệt kiểm tra release range và các tùy chọn có sẵn trên JDK của build agent.

## 12. Từ finding đến vị trí source cần sửa

jdeprscan thường báo caller class và API, không phải file Java cùng số dòng. Để tìm vị trí gọi trong source:

1. Đọc caller class trong output.
2. Tìm source tương ứng theo package và class name.
3. Tìm method hoặc field được báo cáo.
4. Nếu có nhiều overload, đối chiếu descriptor.
5. Nếu không có source, dùng javap để xem bytecode và xác định method chứa tham chiếu.
6. Kiểm tra cả code được sinh tự động hoặc dependency nội bộ.

Ví dụ output:

~~~text
class com.example.legacy.DateAdapter uses deprecated method java/util/Date::getYear()I
~~~

Có thể tìm trong source:

~~~bash
rg "getYear" src
~~~

Lệnh rg là công cụ tìm kiếm source bên ngoài JDK; nếu không có, dùng tìm kiếm của IDE hoặc grep.

Nếu source không có hoặc tên method không đủ để xác định overload, xem bytecode:

~~~bash
javap -classpath build/classes -c -p com.example.legacy.DateAdapter
~~~

javap -c hiển thị bytecode; -p hiển thị cả member không public. Tìm instruction gọi method tương ứng, rồi lần ngược tới method source nếu có debug information.

Không khẳng định số dòng source chỉ từ output jdeprscan nếu công cụ không cung cấp vị trí đó.

## 13. Cách xử lý finding: từ API cũ tới API thay thế

Finding là điểm bắt đầu của quá trình sửa, không phải chỉ dẫn tự động. Cần đọc tài liệu API và hiểu semantics của code trước khi thay.

### Date.getYear()

Finding:

~~~text
java/util/Date::getYear()I
~~~

Date.getYear() trả về năm trừ đi 1900 và phụ thuộc múi giờ mặc định. Khi thay bằng java.time, cần chọn timezone rõ ràng để giữ đúng ý nghĩa nghiệp vụ.

Ví dụ chuyển sang năm theo system default zone:

~~~java
import java.time.ZoneId;
import java.util.Date;

int year = date.toInstant()
        .atZone(ZoneId.systemDefault())
        .getYear();
~~~

Nếu nghiệp vụ yêu cầu timezone cố định, thay ZoneId.systemDefault() bằng ZoneId cụ thể. Không thay máy móc bằng LocalDate.now() vì đó là ngày hiện tại, không phải ngày chứa trong Date object.

### Thread.stop()

Finding:

~~~text
java/lang/Thread::stop()V (forRemoval=true)
~~~

Thread.stop() có thể dừng thread bất ngờ, khiến object ở trạng thái không nhất quán. Hướng thay thế thường là cơ chế dừng hợp tác: dùng interrupt, cờ trạng thái hoặc cancellation token.

Ví dụ:

~~~java
public final class Worker implements Runnable {
    @Override
    public void run() {
        while (!Thread.currentThread().isInterrupted()) {
            doOneUnitOfWork();
        }
    }

    private void doOneUnitOfWork() {
        // Perform one bounded unit of work.
    }
}
~~~

Code quản lý yêu cầu dừng:

~~~java
Thread worker = new Thread(new Worker());
worker.start();

// Request cooperative shutdown.
worker.interrupt();
~~~

Nếu worker đang chờ trong blocking operation có thể ném InterruptedException, hãy xử lý interruption đúng cách và giữ lại trạng thái interrupt khi cần. Không dùng interrupt như một lệnh cưỡng bức dừng ngay lập tức; worker cần có cơ hội dọn dẹp tài nguyên.

### Object.finalize()

Nếu finding chỉ ra finalize(), cần chuyển logic giải phóng tài nguyên sang cơ chế rõ ràng như AutoCloseable và try-with-resources. Không dựa vào thời điểm garbage collector chạy để đóng file, socket hoặc handle.

Ví dụ:

~~~java
try (var input = java.nio.file.Files.newInputStream(path)) {
    // Read data.
}
~~~

Đóng tài nguyên xác định theo lexical scope giúp code dễ kiểm thử và không phụ thuộc finalization.

## 14. Ưu tiên và phân loại kết quả scan

Một báo cáo hữu ích nên phân loại theo nhiều chiều.

### Theo trạng thái deprecated

- Deprecated thông thường: cần đánh giá và lên kế hoạch thay thế.
- Deprecated for removal: ưu tiên cao hơn vì API được đánh dấu có thể bị loại bỏ.
- API chỉ deprecated ở release mới: có thể không ảnh hưởng baseline hiện tại nhưng tác động tới mục tiêu nâng cấp.

### Theo vị trí caller

- Code do nhóm phát triển sở hữu: có thể sửa trực tiếp.
- Dependency nội bộ: cập nhật module hoặc library liên quan.
- Dependency bên thứ ba: tìm phiên bản mới hoặc liên hệ nhà cung cấp.
- Code được sinh tự động: cập nhật generator hoặc template, không chỉ sửa file output.

### Theo mức độ ảnh hưởng

Đánh giá thêm:

- API có nằm trên đường chạy chính không?
- Có được gọi thường xuyên không?
- Có nằm trong public API của thư viện không?
- Có ảnh hưởng binary compatibility không?
- Có giải pháp thay thế tương đương không?
- Có cần thay đổi hành vi hoặc timezone/concurrency semantics không?

Không chỉ đếm số dòng warning. Một finding forRemoval trong đường chạy chính có thể quan trọng hơn nhiều finding deprecated trong công cụ nội bộ ít dùng.

## 15. Phân biệt deprecated API với API không còn tồn tại

jdeprscan tìm API deprecated theo tập API của release được chọn. Nó không phải công cụ tổng quát để chứng minh mọi tham chiếu đều tương thích với một JDK khác.

Các trường hợp cần phân biệt:

- **Deprecated:** API vẫn tồn tại nhưng được khuyến nghị không sử dụng.
- **Deprecated for removal:** API vẫn tồn tại trong release được phân tích nhưng được đánh dấu có thể bị loại bỏ.
- **Removed:** API không còn trong release mới; class có thể gặp lỗi compile hoặc linkage nếu vẫn tham chiếu.
- **Missing dependency:** class không tìm được khi công cụ phân giải dependency; đây không đồng nghĩa với deprecated API.

Nếu ứng dụng cần nâng cấp JDK, kết hợp jdeprscan với compile bằng --release phù hợp, test trên runtime mục tiêu và kiểm tra dependency. Không dùng một lần scan deprecated làm bằng chứng đầy đủ về binary compatibility.

## 16. Ví dụ thực hành hoàn chỉnh Java 17+

Ví dụ sau tạo một class có hai tham chiếu deprecated để minh họa cách đọc kết quả.

Cấu trúc:

~~~text
jdeprscan-demo/
├── src/
│   └── LegacyApiUse.java
└── build/
    └── classes/
~~~

### LegacyApiUse.java

~~~java
import java.util.Date;

public final class LegacyApiUse {

    private LegacyApiUse() {
    }

    public static int legacyYear(Date date) {
        return date.getYear();
    }

    public static void legacyStop(Thread thread) {
        thread.stop();
    }

    public static void main(String[] args) {
        System.out.println("jdeprscan demo ready.");
    }
}
~~~

### Biên dịch

~~~bash
mkdir -p build/classes

javac --release 17 \
    -Xlint:deprecation \
    -d build/classes \
    src/LegacyApiUse.java
~~~

Compiler có thể in warning deprecation cho getYear() và stop(). Đây là cảnh báo từ javac; nó khác với output của jdeprscan.

### Chạy chương trình

~~~bash
java -cp build/classes LegacyApiUse
~~~

Output:

~~~text
jdeprscan demo ready.
~~~

Main không gọi hai method deprecated nên ví dụ có thể chạy mà không thực thi thao tác dừng thread.

### Scan theo Java 17

~~~bash
jdeprscan --release 17 build/classes
~~~

Output đã xác minh trên JDK 24.0.2:

~~~text
Directory ...\build\classes:
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V
~~~

Dấu ... đại diện cho đường dẫn thư mục thực tế. Kết quả cho thấy LegacyApiUse chứa hai tham chiếu deprecated. Trong tập API Java 17, Thread.stop() chưa mang marker forRemoval=true.

### Scan theo Java 24

~~~bash
jdeprscan --release 24 build/classes
~~~

Output:

~~~text
Directory ...\build\classes:
class LegacyApiUse uses deprecated method java/util/Date::getYear()I
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

### Chỉ xem API for removal

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

Output:

~~~text
Directory ...\build\classes:
class LegacyApiUse uses deprecated method java/lang/Thread::stop()V (forRemoval=true)
~~~

Date.getYear() không còn xuất hiện vì API đó không được đánh dấu for removal trong tập Java 24. Đây là minh họa cho việc dùng --for-removal để lọc danh sách ưu tiên.

### Đóng gói và scan JAR

~~~bash
jar --create \
    --file build/legacy-api-use.jar \
    -C build/classes .

jdeprscan --release 24 build/legacy-api-use.jar
~~~

Kết quả về API deprecated tương tự khi scan thư mục class. Header sẽ chỉ ra archive được phân tích thay vì thư mục.

## 17. Tích hợp jdeprscan vào CI

jdeprscan có thể là một bước audit trong pipeline nâng cấp JDK:

1. Compile tất cả module/artifact.
2. Scan thư mục class hoặc JAR của code do nhóm sở hữu.
3. Chạy theo release hiện tại.
4. Chạy theo release mục tiêu.
5. Chạy --for-removal để tạo danh sách ưu tiên.
6. Phân loại finding theo caller và API.
7. Lưu báo cáo cùng phiên bản JDK và lệnh đã dùng.
8. Sửa code hoặc cập nhật dependency.
9. Scan lại và so sánh kết quả.

Ví dụ:

~~~bash
jdeprscan --release 17 build/classes
jdeprscan --release 24 build/classes
jdeprscan --release 24 --for-removal build/classes
~~~

Trong CI, cần quyết định chính sách riêng:

- Chỉ báo cáo finding hay làm build thất bại?
- Có chặn finding forRemoval mới không?
- Có cho phép baseline finding cũ trong thời gian migration không?
- Có scan dependency bên thứ ba hay chỉ code nội bộ?
- Ai chịu trách nhiệm xử lý finding trong mỗi module?

Không giả định rằng mọi finding đều làm jdeprscan trả exit code khác 0. Công cụ có thể in phát hiện và vẫn kết thúc bình thường; pipeline muốn fail theo policy cần phân tích output hoặc dùng bước kiểm tra riêng.

Lưu ý thêm: các finding trong JAR dependency cần được scan bằng cách truyền JAR đó làm input. Chỉ thêm nó vào --class-path để phân giải không đồng nghĩa đã audit toàn bộ code bên trong JAR.

## 18. Giới hạn của jdeprscan

jdeprscan phân tích bytecode tĩnh. Nó có thể bỏ sót hoặc không thể kết luận về:

- API được gọi qua reflection với tên class/member lấy từ chuỗi.
- Class được nạp động từ plugin hoặc cấu hình bên ngoài.
- Dependency được tải sau khi ứng dụng khởi chạy.
- Hành vi của mã native.
- API được sử dụng trong source nhưng chưa được compile thành artifact đang scan.
- Artifact chưa được truyền làm input.
- Mọi vấn đề tương thích binary hoặc thay đổi semantics.

Một scan không có finding không có nghĩa ứng dụng chắc chắn tương thích với mọi release Java. Nó chỉ nói rằng công cụ không tìm thấy tham chiếu deprecated trong phạm vi đầu vào và API release được chọn.

Để audit đáng tin cậy hơn, scan tất cả artifact do ứng dụng sở hữu, cung cấp classpath dependency cần thiết, kiểm tra plugin/configuration và chạy test trên runtime mục tiêu.

## 19. Checklist đọc và xử lý một báo cáo

Với mỗi dòng finding, hãy xác nhận:

- [ ] Release dùng để scan đã được ghi nhận.
- [ ] Caller class đã được xác định.
- [ ] Owner class và member deprecated đã được nhận diện.
- [ ] Descriptor đã được giải mã nếu có overload.
- [ ] Marker forRemoval=true đã được giữ lại nếu xuất hiện.
- [ ] API đã được tra cứu trong Javadoc của đúng release.
- [ ] Source hoặc bytecode đã được truy vết tới vị trí sử dụng.
- [ ] Đã phân loại code nội bộ, code sinh tự động hay dependency bên thứ ba.
- [ ] Đã đánh giá semantics của API thay thế.
- [ ] Đã chạy test sau khi sửa.
- [ ] Đã scan lại theo release mục tiêu.
- [ ] Báo cáo và phiên bản công cụ được lưu để so sánh về sau.

## 20. Quy trình lệnh cần nhớ

~~~bash
# Version and options
jdeprscan --version
jdeprscan --help

# List deprecated APIs
jdeprscan --list
jdeprscan --list --for-removal
jdeprscan --list --release 17

# Scan compiled classes
jdeprscan --release 17 build/classes

# Scan a JAR
jdeprscan --release 24 build/libs/application.jar

# Scan only APIs for removal
jdeprscan --release 24 --for-removal build/classes

# Resolve dependent classes
jdeprscan --class-path "lib/common.jar" build/classes

# Additional processing messages
jdeprscan --verbose --release 24 build/classes
~~~

Khi đọc output, hãy bắt đầu từ release, xác định caller class, giải mã owner/member/descriptor, rồi kiểm tra marker forRemoval=true. Sau đó truy vết source, đánh giá API thay thế và scan lại. Cách làm này biến danh sách deprecated thành kế hoạch nâng cấp cụ thể, thay vì chỉ là một tập warning khó xử lý.

## Tài liệu tham khảo

- [The jdeprscan Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html)
- [Deprecated API — Java Platform, Standard Edition 24](https://docs.oracle.com/en/java/javase/24/docs/api/deprecated-list.html)
- [The javap Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javap.html)
- [JEP 277: Enhanced Deprecation](https://openjdk.org/jeps/277)
