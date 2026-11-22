# Checked exception và thay đổi yêu cầu xử lý ngoại lệ

Trong Java, checked exception là một phần quan trọng của hợp đồng phương thức. Khi một thư viện hoặc module thay đổi danh sách ngoại lệ được khai báo trong throws, mã nguồn của consumer có thể phải sửa cách gọi, cách bắt lỗi hoặc cách triển khai interface. Tuy nhiên, thay đổi này không phải lúc nào cũng làm bytecode cũ mất khả năng liên kết. Để đánh giá migration chính xác, cần phân biệt tương thích mã nguồn, tương thích nhị phân và tương thích hành vi.

Ví dụ, một phiên bản thư viện có phương thức load() khai báo IOException. Ở phiên bản sau, nhà cung cấp bổ sung SQLException. Consumer đang gọi phương thức có thể phải bổ sung catch hoặc khai báo ngoại lệ mới. Nhưng JVM không dùng mệnh đề throws để xác định chữ ký liên kết của method. Vì vậy, một chương trình đã biên dịch trước đó có thể vẫn liên kết với phiên bản thư viện mới, rồi gặp ngoại lệ mới trong runtime mà mã nguồn cũ chưa xử lý.

## 1. Checked exception là gì?

Java chia exception thành hai nhóm chính theo cách compiler yêu cầu xử lý:

- **Checked exception:** các ngoại lệ thuộc Throwable nhưng không phải RuntimeException hoặc Error. Mã nguồn phải bắt chúng bằng try/catch hoặc khai báo truyền tiếp bằng throws.
- **Unchecked exception:** RuntimeException, các lớp con của nó và Error. Compiler không bắt buộc caller phải bắt hoặc khai báo các ngoại lệ này.

Ví dụ:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ConfigLoader {
    public String load(Path path) throws IOException {
        return Files.readString(path);
    }
}
~~~

IOException là checked exception. Caller phải xử lý hoặc khai báo nó:

~~~java
public void start() throws IOException {
    String config = new ConfigLoader().load(Path.of("app.properties"));
    initialize(config);
}
~~~

Hoặc caller có thể bắt và chuyển đổi lỗi:

~~~java
public void start() {
    try {
        String config = new ConfigLoader().load(Path.of("app.properties"));
        initialize(config);
    } catch (IOException exception) {
        throw new IllegalStateException("Cannot load application configuration", exception);
    }
}
~~~

Compiler kiểm tra yêu cầu này từ kiểu ngoại lệ được khai báo và các biểu thức có thể ném checked exception. JVM không cưỡng chế quy tắc checked exception khi chạy bytecode. Đây là khác biệt quan trọng khi thay đổi API đã được consumer biên dịch trước đó.

## 2. Mệnh đề throws là một phần của hợp đồng mã nguồn

Mệnh đề throws cho biết phương thức có thể truyền những checked exception nào ra caller. Nó giúp consumer biết loại lỗi cần xử lý và cho phép compiler kiểm tra luồng xử lý ngoại lệ.

Ví dụ:

~~~java
public Customer findById(String id) throws IOException {
    // Đọc dữ liệu từ một nguồn có thể phát sinh lỗi I/O.
}
~~~

Hợp đồng không chỉ là danh sách tên exception. Nó còn bao gồm điều kiện nào làm ngoại lệ xuất hiện, phương thức có thể để ngoại lệ đi qua hay sẽ wrap nó, trạng thái hệ thống sau lỗi và liệu caller có thể retry an toàn hay không.

Một phương thức có thể khai báo throws IOException nhưng thực tế chỉ ném một lớp con như FileNotFoundException. Caller được phép dựa vào loại khai báo IOException; nếu nhà cung cấp muốn cam kết chi tiết hơn, cần tài liệu hóa rõ các loại ngoại lệ và điều kiện phát sinh.

## 3. Các chiều tương thích cần phân biệt

### 3.1. Tương thích mã nguồn (source compatibility)

Consumer được xem là tương thích mã nguồn khi mã nguồn cũ vẫn biên dịch được với phiên bản thư viện mới mà không cần chỉnh sửa vì thay đổi đang xét.

Thay đổi checked exception có thể buộc caller:

- Thêm catch cho loại checked exception mới.
- Bổ sung exception vào throws của method gọi.
- Đổi kiểu exception được khai báo ở tầng API cao hơn.
- Điều chỉnh implementation của interface hoặc abstract method.
- Sửa lambda expression hoặc method reference được gán cho functional interface.

### 3.2. Tương thích nhị phân (binary compatibility)

Bytecode consumer đã biên dịch có thể tiếp tục liên kết với phiên bản thư viện mới hay không là câu hỏi khác. Trong JVM method descriptor, các thành phần dùng để định danh method gồm tên method, kiểu tham số và kiểu trả về; danh sách exception được khai báo không nằm trong descriptor.

Do đó, chỉ thêm, bớt hoặc đổi kiểu trong throws thường không làm thay đổi descriptor của method và bản thân thay đổi đó không phá vỡ liên kết nhị phân. Tuy nhiên, nếu method thực sự ném một checked exception mới, bytecode cũ có thể không có handler tương ứng và ngoại lệ có thể truyền ra ngoài luồng gọi.

### 3.3. Tương thích hành vi (behavioral compatibility)

Ngay cả khi chữ ký và liên kết nhị phân giữ nguyên, thay đổi loại exception thực tế, thời điểm ném, điều kiện ném hoặc trạng thái sau lỗi vẫn có thể làm consumer hoạt động khác đi.

Ví dụ, caller trước đây nhận IOException và retry khi lỗi tạm thời. Phiên bản mới wrap mọi lỗi thành IllegalStateException. Chương trình vẫn có thể biên dịch và liên kết, nhưng chính sách retry của caller không còn được kích hoạt.

Vì vậy, cần đánh giá cả ba chiều thay vì kết luận “binary compatible” đồng nghĩa “an toàn để nâng cấp”.

## 4. Thêm checked exception vào một phương thức hiện có

Giả sử phiên bản đầu khai báo:

~~~java
public Customer load(String id) throws IOException {
    return repository.load(id);
}
~~~

Consumer có thể viết:

~~~java
Customer customer = service.load(customerId);
~~~

trong một method đã khai báo throws IOException, hoặc bắt IOException tại chỗ.

Ở phiên bản sau, nhà cung cấp bổ sung SQLException:

~~~java
public Customer load(String id) throws IOException, SQLException {
    return repository.load(id);
}
~~~

Consumer biên dịch lại có thể nhận lỗi như:

~~~text
unreported exception SQLException; must be caught or declared to be thrown
~~~

Caller phải xử lý ngoại lệ mới hoặc truyền nó tiếp. Đây là thay đổi có thể phá vỡ source compatibility, đặc biệt với API công khai được nhiều module sử dụng.

Về binary compatibility, throws không thuộc method descriptor. Bytecode cũ vẫn có thể tìm thấy cùng method nếu tên, tham số, kiểu trả về và các điều kiện liên kết khác không đổi. Nhưng nếu implementation mới thực sự ném SQLException, code cũ có thể để ngoại lệ thoát ra ngoài mà không có xử lý dự kiến. JVM không tự động chuyển checked exception thành unchecked và cũng không tự chèn catch vào bytecode cũ.

## 5. Mở rộng hoặc thay đổi kiểu checked exception

Thay đổi từ một kiểu cụ thể sang kiểu cha rộng hơn thường làm source compatibility xấu đi vì caller phải chuẩn bị cho nhiều loại lỗi hơn.

Ví dụ:

~~~java
// Phiên bản cũ
public String read() throws FileNotFoundException;

// Phiên bản mới
public String read() throws IOException;
~~~

Caller cũ chỉ bắt FileNotFoundException có thể không xử lý các IOException khác mà phiên bản mới có thể ném. Nếu caller khai báo throws FileNotFoundException, nó cũng không thể truyền tiếp IOException rộng hơn. Caller cần cập nhật catch hoặc throws.

Một trường hợp khác là thay từ IOException sang Exception:

~~~java
// Trước
public Data load() throws IOException;

// Sau
public Data load() throws Exception;
~~~

Kiểu Exception rộng hơn nhiều. Consumer có thể phải thay đổi các tầng API, bởi những method trung gian trước đây chỉ khai báo IOException không thể tự nhiên truyền tiếp mọi Exception.

Nếu cần thêm một nguyên nhân lỗi mới nhưng vẫn muốn giữ hợp đồng ổn định, có thể xem xét đặt exception mới dưới một kiểu cha đã được khai báo từ trước, wrap nguyên nhân vào exception hiện có hoặc tạo một method/API mới. Mỗi cách cần cân nhắc khả năng caller phân biệt lỗi và chính sách retry.

## 6. Thu hẹp hoặc loại bỏ checked exception

Thu hẹp danh sách checked exception không phải lúc nào cũng hoàn toàn không ảnh hưởng tới source compatibility.

Ví dụ method trước đây khai báo:

~~~java
public Customer load() throws IOException;
~~~

Phiên bản mới chỉ khai báo:

~~~java
public Customer load() throws FileNotFoundException;
~~~

Caller bắt IOException vẫn hợp lệ vì IOException là lớp cha của FileNotFoundException. Caller khai báo throws IOException cũng vẫn có thể gọi method. Tuy nhiên, các class triển khai interface hoặc override method có thể cần điều chỉnh nếu chúng đang khai báo checked exception rộng hơn mức mới cho phép.

Nếu loại bỏ hoàn toàn checked exception:

~~~java
public Customer load();
~~~

Một số caller có catch IOException chỉ bao quanh lời gọi này có thể không biên dịch lại vì checked exception đó không còn được ném từ khối try. Caller cũng có thể cần xóa khai báo throws IOException nếu không còn thao tác nào khác yêu cầu nó.

Việc loại bỏ checked exception có thể là thay đổi tốt cho trải nghiệm API nếu lỗi đó không còn có ý nghĩa hoặc đã được xử lý nội bộ. Tuy nhiên, cần kiểm tra consumer sử dụng catch, throws, method reference và các tầng wrapper ra sao.

## 7. Quy tắc checked exception khi override và implement interface

Java giới hạn checked exception mà method ghi đè được phép khai báo. Method override có thể khai báo cùng kiểu hoặc kiểu con của checked exception trong method cha/interface; nó không được mở rộng sang checked exception rộng hơn.

Ví dụ:

~~~java
interface CustomerReader {
    Customer read() throws IOException;
}

class FileCustomerReader implements CustomerReader {
    @Override
    public Customer read() throws FileNotFoundException {
        // Hợp lệ: FileNotFoundException là lớp con của IOException.
        return loadFile();
    }
}
~~~

Ví dụ không hợp lệ:

~~~java
class RemoteCustomerReader implements CustomerReader {
    @Override
    public Customer read() throws IOException, SQLException {
        // Lỗi: SQLException không nằm trong throws của method interface.
        return loadRemote();
    }
}
~~~

Nếu cần phát sinh SQLException, implementation có thể wrap thành IOException phù hợp với hợp đồng, xử lý nội bộ hoặc thay đổi interface theo kế hoạch tương thích.

### 7.1. Mở rộng throws trên interface

Giả sử interface được mở rộng từ:

~~~java
interface CustomerReader {
    Customer read() throws IOException;
}
~~~

thành:

~~~java
interface CustomerReader {
    Customer read() throws IOException, SQLException;
}
~~~

Một implementation hiện có chỉ khai báo throws IOException vẫn có thể implement interface mới vì method triển khai được phép khai báo ít checked exception hơn. Tuy nhiên, caller sử dụng kiểu tham chiếu CustomerReader phải xử lý thêm SQLException khi biên dịch lại.

### 7.2. Thu hẹp throws trên interface

Nếu interface bỏ IOException, implementation cũ vẫn khai báo throws IOException có thể không còn biên dịch được vì method override không được khai báo checked exception rộng hơn method mới. Đây là lý do thay đổi throws clause có thể ảnh hưởng cả phía caller và phía implementor theo hai hướng khác nhau.

## 8. Checked exception trong functional interface, lambda và method reference

Throws clause của functional interface ảnh hưởng đến những lambda và method reference mà consumer có thể gán cho interface đó.

Ví dụ:

~~~java
@FunctionalInterface
interface ConfigReader {
    String read() throws IOException;
}
~~~

Lambda có thể gọi API ném IOException:

~~~java
ConfigReader reader = () -> Files.readString(Path.of("app.properties"));
~~~

Nếu interface bỏ throws IOException, lambda trên không còn biên dịch được vì target method không cho phép truyền checked exception đó ra ngoài.

Ngược lại, khi interface mở rộng throws clause, các lambda không ném exception vẫn có thể tiếp tục hoạt động. Nhưng caller gọi reader.read() sẽ phải xử lý tập checked exception rộng hơn.

Method reference cũng chịu quy tắc tương tự. Một method reference chỉ tương thích với functional interface nếu kiểu tham số, kiểu trả về và exception có thể ném phù hợp với descriptor của functional interface theo quy tắc kiểm tra của Java.

Khi thay đổi throws clause của một interface có nhiều consumer, cần tìm cả:

- Lambda expression được gán cho interface.
- Method reference tới method ném checked exception.
- Class hoặc anonymous class implement interface.
- Caller dùng kiểu interface để gọi method.

## 9. Thay checked exception bằng unchecked exception

Đôi khi API thay đổi từ checked exception sang unchecked exception:

~~~java
// Trước
public Customer load(String id) throws IOException;

// Sau
public Customer load(String id);
~~~

Nếu implementation mới ném UncheckedIOException hoặc một RuntimeException, compiler không yêu cầu caller phải khai báo hay bắt. Nhưng consumer cũ có thể đang có catch IOException chỉ dành cho lời gọi đó. Khi biên dịch lại, catch cụ thể có thể trở thành unreachable nếu không còn lời gọi nào khác trong khối try có thể ném IOException.

Ngoài ra, thay checked exception bằng unchecked exception có thể làm thay đổi cách ứng dụng xử lý lỗi. Các tầng gọi có thể trước đây truyền IOException lên một boundary, nhưng giờ exception đi qua các tầng mà không có khai báo, rồi bị framework xử lý như lỗi runtime.

Không nên đổi sang unchecked chỉ để giảm số throws trong chữ ký. Cần phân loại bản chất lỗi:

- Lỗi do đầu vào hoặc trạng thái lập trình sai thường có thể phù hợp với unchecked exception.
- Lỗi I/O, lỗi dịch vụ bên ngoài, lỗi đọc cấu hình hoặc lỗi tài nguyên thường cần được xem xét theo hợp đồng nghiệp vụ và khả năng phục hồi.
- Nếu chuyển sang unchecked, cần xác định exception type, cause, logging, retry và boundary chịu trách nhiệm xử lý.

## 10. Thay đổi kiểu exception thực tế dù throws clause không đổi

Có thể giữ nguyên khai báo throws IOException nhưng thay đổi loại exception thực tế:

~~~java
// Phiên bản cũ
throw new FileNotFoundException("Customer file is missing");

// Phiên bản mới
throw new SocketException("Remote storage is unavailable");
~~~

Cả hai đều là IOException, nên caller bắt IOException vẫn tương thích ở mức kiểu. Tuy nhiên, caller có thể có logic riêng cho FileNotFoundException, ví dụ hiển thị thông báo “không tìm thấy file” thay vì retry kết nối. Hành vi mới có thể làm thay đổi quyết định nghiệp vụ.

Tương tự, thay đổi exception wrapping có thể làm mất khả năng phân loại lỗi nếu cause không được giữ lại. Ví dụ, wrap SQLException thành một exception tổng quát nhưng không truyền cause sẽ làm mất thông tin để chẩn đoán.

Một hợp đồng ngoại lệ tốt nên mô tả:

- Loại exception có thể được ném ra.
- Điều kiện gây ra từng loại exception.
- Exception được truyền nguyên trạng hay được wrap.
- Cause có được giữ lại không.
- Caller có thể retry hay phải yêu cầu người dùng can thiệp.
- Trạng thái tài nguyên, transaction hoặc dữ liệu sau khi lỗi xảy ra.

## 11. Cách thiết kế API để thay đổi ngoại lệ an toàn hơn

### 11.1. Dùng exception domain ổn định ở ranh giới module

Nếu thư viện muốn thay đổi database driver hoặc HTTP client, không nên để exception đặc thù của implementation rò rỉ trực tiếp qua API công khai nếu không có lý do. Có thể định nghĩa exception thuộc domain của thư viện:

~~~java
public class CustomerAccessException extends Exception {
    public CustomerAccessException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

API:

~~~java
public interface CustomerLookup {
    Customer findById(String id) throws CustomerAccessException;
}
~~~

Implementation có thể chuyển đổi lỗi từ JDBC, HTTP hoặc cache sang CustomerAccessException, giữ nguyên cause để chẩn đoán. Khi đổi thư viện truy cập dữ liệu, consumer không phải phụ thuộc vào exception của driver.

Tuy nhiên, exception domain chỉ hữu ích nếu nó cung cấp phân loại đủ rõ. Nếu mọi lỗi đều bị gộp thành một loại mà không có mã lỗi, subtype hoặc cause phù hợp, consumer có thể mất khả năng xử lý khác nhau cho lỗi tạm thời và lỗi vĩnh viễn.

### 11.2. Giữ exception cha ổn định và thêm subtype có kiểm soát

Nếu API đã khai báo throws IOException, có thể bổ sung một subtype mới của IOException để biểu diễn nguyên nhân cụ thể. Caller đang bắt IOException vẫn nhận được lỗi; consumer cần xử lý riêng có thể bắt subtype khi có nhu cầu.

Không nên thay kiểu khai báo từ lớp cha sang lớp con nếu điều đó làm implementation consumer hoặc caller đang dựa vào phạm vi rộng bị ảnh hưởng. Có thể giữ kiểu khai báo cũ và mô tả subtype cụ thể trong tài liệu.

### 11.3. Dùng method mới khi ngữ nghĩa lỗi thay đổi lớn

Nếu phương thức mới có mô hình lỗi khác căn bản, một lựa chọn là thêm method mới với hợp đồng rõ ràng, giữ method cũ trong giai đoạn chuyển tiếp và đánh dấu deprecated khi phù hợp.

Ví dụ:

~~~java
public Customer load(String id) throws IOException {
    return loadLegacy(id);
}

public Customer loadWithPolicy(String id) throws CustomerAccessException {
    return loadUsingDomainPolicy(id);
}
~~~

Đây là ví dụ minh họa. API mới cần có tên thể hiện rõ ngữ nghĩa và không tạo ra hai cách xử lý mâu thuẫn. Nếu giữ method cũ, tài liệu phải nêu thời điểm dự kiến loại bỏ và cách chuyển đổi.

### 11.4. Giữ cause và thông tin ngữ cảnh

Khi wrap exception, luôn cân nhắc truyền cause:

~~~java
try {
    return repository.load(id);
} catch (SQLException exception) {
    throw new CustomerAccessException(
            "Cannot load customer " + id,
            exception);
}
~~~

Không đưa dữ liệu nhạy cảm như token, password hoặc thông tin cá nhân không cần thiết vào message. Exception message thường xuất hiện trong log và hệ thống quan sát.

## 12. Đánh giá thay đổi throws clause khi migration

Khi chuẩn bị thay đổi API, có thể dùng ma trận sau để xác định nơi cần kiểm tra:

| Thay đổi | Source compatibility | Binary compatibility | Rủi ro hành vi |
|---|---|---|---|
| Thêm checked exception mới | Có thể phá vỡ caller phải catch/declare thêm | Thường giữ nguyên vì throws không nằm trong method descriptor | Code cũ có thể nhận exception chưa xử lý. |
| Mở rộng kiểu exception từ subtype lên supertype | Caller và tầng wrapper có thể phải sửa | Thường giữ nguyên descriptor | Caller có thể gặp loại lỗi rộng hơn dự kiến. |
| Thu hẹp kiểu exception | Caller thường vẫn xử lý được nhưng implementor có thể phải sửa throws | Thường giữ nguyên descriptor | Phân loại lỗi và nhánh xử lý có thể thay đổi. |
| Loại bỏ checked exception | Catch cụ thể hoặc throws cũ có thể không còn biên dịch | Thường giữ nguyên descriptor | Caller có thể không còn nhận lỗi theo cách trước đây. |
| Đổi checked thành unchecked | Catch checked cụ thể có thể thành unreachable | Thường giữ nguyên descriptor | Exception có thể đi qua boundary trước đây xử lý checked exception. |
| Giữ throws nhưng thay exception thực tế | Có thể vẫn biên dịch | Giữ nguyên nếu descriptor không đổi | Logic catch subtype, retry và thông báo có thể thay đổi. |

“Thường giữ nguyên” ở cột binary chỉ nói về riêng thay đổi throws. Nếu đồng thời đổi tên method, tham số, kiểu trả về, class exception, visibility hoặc module boundary, vẫn có thể phát sinh binary incompatibility độc lập.

## 13. Quy trình kiểm tra consumer trước khi thay đổi

### Bước 1: Lập danh sách API có checked exception

Liệt kê method public/protected, interface, abstract class và functional interface có khai báo throws. Với thư viện, kiểm tra cả các kiểu exception được xuất hiện trong chữ ký công khai và các exception được tài liệu hóa.

### Bước 2: Tìm caller và implementor

Tìm mọi nơi gọi method, bắt exception, khai báo throws, override method hoặc implement interface. Bao gồm test, adapter, plugin và source set riêng. Đặc biệt tìm lambda và method reference nếu API là functional interface.

### Bước 3: Phân tích exception hierarchy

Xác định checked exception mới có phải subtype của kiểu đã khai báo không. Xem caller đang catch lớp cụ thể hay lớp cha; xem implementation có khai báo exception rộng hơn method được override hay không.

### Bước 4: Phân tích bytecode và API metadata

Dùng javap -s -v để quan sát descriptor và thuộc tính Exceptions của method. Công cụ API compatibility có thể giúp phát hiện thay đổi khai báo ngoại lệ trong tài liệu/API metadata, nhưng cần hiểu rằng throws không nằm trong JVM method descriptor.

Ví dụ:

~~~bash
javap -classpath library.jar -s -v com.example.CustomerService
~~~

Trong output, descriptor thể hiện tên và kiểu tham số/kiểu trả về ở dạng JVM. Thuộc tính Exceptions liệt kê các exception được khai báo. Việc Exceptions thay đổi có thể ảnh hưởng source contract và reflection metadata, dù descriptor giữ nguyên.

### Bước 5: Chạy consumer compile test

Biên dịch lại các consumer đại diện với phiên bản thư viện mới. Kiểm tra caller, implementor, lambda, method reference và các wrapper API.

### Bước 6: Chạy binary compatibility test

Giữ một consumer đã biên dịch với thư viện cũ, sau đó chạy nó với thư viện mới trên classpath/module path tương ứng. Kiểm tra liên kết và quan sát exception thực tế. Không chỉ kiểm tra việc JVM khởi động được; cần chạy code path có thể phát sinh ngoại lệ mới.

### Bước 7: Kiểm tra behavioral contract

Viết test cho từng loại lỗi, điều kiện phát sinh, cause, trạng thái sau lỗi và retry policy. Xác nhận các tầng xử lý lỗi trong ứng dụng vẫn nhận đúng loại exception và không nuốt mất thông tin quan trọng.

### Bước 8: Cập nhật tài liệu và lộ trình

Nếu thay đổi là breaking change ở mức source hoặc behavior, nêu rõ trong release notes, migration guide và chính sách versioning. Nếu cần, cung cấp phiên bản chuyển tiếp hoặc API mới trước khi loại bỏ hợp đồng cũ.

## 14. Ví dụ tổng hợp: thay đổi exception trong thư viện

Giả sử phiên bản 1 của thư viện khai báo:

~~~java
public interface ReportStore {
    Report load(String reportId) throws IOException;
}
~~~

Một ứng dụng consumer viết:

~~~java
public Report loadReport(String id) {
    try {
        return reportStore.load(id);
    } catch (FileNotFoundException exception) {
        return Report.empty();
    } catch (IOException exception) {
        throw new IllegalStateException("Cannot load report", exception);
    }
}
~~~

Ở phiên bản 2, nhóm muốn bổ sung lỗi truy cập dịch vụ từ xa và thay khai báo thành:

~~~java
public interface ReportStore {
    Report load(String reportId) throws IOException, SQLException;
}
~~~

Những điểm cần xem xét:

1. Caller biên dịch lại phải xử lý hoặc khai báo SQLException.
2. Implementation hiện có chỉ khai báo IOException vẫn có thể implement interface mới, nhưng implementation mới không được khai báo thêm SQLException nếu interface không cho phép; ở đây interface đã cho phép.
3. Bytecode consumer cũ vẫn có thể liên kết vì method descriptor không đổi.
4. Consumer cũ có thể nhận SQLException chưa được xử lý nếu implementation mới ném trực tiếp ngoại lệ đó.
5. Nếu SQLException thực chất là lỗi truy cập dữ liệu nội bộ, có thể cân nhắc wrap thành exception domain dưới IOException hoặc định nghĩa một exception ổn định của thư viện.
6. Cần kiểm tra retry policy: lỗi kết nối tạm thời có thể retry, nhưng lỗi SQL do dữ liệu hoặc câu lệnh sai có thể không nên retry.

Một lựa chọn khác là giữ nguyên throws IOException và chuyển lỗi từ storage adapter thành IOException có cause là SQLException. Cách này giữ source contract của caller, nhưng phải đánh giá liệu việc gộp lỗi có làm mất khả năng phân biệt các trường hợp mà consumer cần xử lý hay không.

## 15. Checklist khi thay đổi checked exception

- [ ] Đã xác định API công khai, interface, abstract method và functional interface bị tác động.
- [ ] Đã phân biệt checked exception với unchecked exception.
- [ ] Đã đánh giá caller, catch clause, throws propagation, override và implementor.
- [ ] Đã kiểm tra lambda expression và method reference nếu có.
- [ ] Đã phân biệt source compatibility, binary compatibility và behavioral compatibility.
- [ ] Đã xác minh throws không thuộc JVM method descriptor và kiểm tra metadata khi cần.
- [ ] Đã giữ cause và ngữ cảnh khi wrap exception.
- [ ] Đã xác định retry, transaction, resource lifecycle và trạng thái dữ liệu sau lỗi.
- [ ] Đã chạy consumer compile test và binary compatibility test phù hợp.
- [ ] Đã chạy test cho các loại exception thực tế trên JDK mục tiêu.
- [ ] Đã cập nhật tài liệu, release notes và hướng dẫn migration.

## Kết luận

Checked exception là một phần của hợp đồng mã nguồn và hành vi xử lý lỗi. Thêm, mở rộng, thu hẹp hoặc loại bỏ checked exception có thể ảnh hưởng caller, implementor, lambda và method reference theo những cách khác nhau. Riêng mệnh đề throws không nằm trong JVM method descriptor, nên thay đổi khai báo thường không phá vỡ liên kết nhị phân; nhưng bytecode cũ vẫn có thể nhận một exception mới mà nó không dự kiến xử lý. Khi migration, cần kiểm tra cả source, binary và behavioral compatibility, xác định exception hierarchy, giữ thông tin cause, kiểm thử consumer đã biên dịch và cập nhật lộ trình phát hành để thay đổi hợp đồng ngoại lệ có thể dự đoán được.
