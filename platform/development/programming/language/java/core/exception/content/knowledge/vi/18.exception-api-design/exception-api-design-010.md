# Tác động tương thích khi thay đổi hợp đồng ngoại lệ trong Java

> **Phạm vi:** Java Core → Exception → Thiết kế API. Bài này tập trung vào hậu quả đối với mã gọi, lớp triển khai, bản biên dịch cũ và hành vi vận hành khi một API thay đổi ngoại lệ có thể phát sinh.

## 1. Hợp đồng ngoại lệ là gì?

Hợp đồng ngoại lệ (*exception contract*) mô tả những tình huống thất bại mà người dùng API cần dự liệu, cách phát hiện chúng và cách khôi phục hoặc truyền lỗi lên tầng cao hơn. Hợp đồng được thể hiện qua nhiều nguồn:

- **Khai báo `throws`:** cho biết các *checked exception* mà trình biên dịch buộc bên gọi phải xử lý hoặc khai báo tiếp. Khai báo này là khả năng xảy ra, không bảo đảm ngoại lệ luôn phát sinh.
- **Kiểu ngoại lệ thực tế:** lớp exception và quan hệ kế thừa quyết định một khối `catch` có bắt được lỗi hay không.
- **Tài liệu API:** `@throws`, điều kiện lỗi, tính khôi phục được, và ý nghĩa của tham số hoặc trạng thái khi thao tác thất bại.
- **Hành vi quan sát được:** thời điểm phát sinh, việc giữ `cause`, trạng thái tài nguyên hoặc giao dịch sau lỗi, cơ chế retry/cancel, và các tín hiệu cho logging/monitoring.

Ví dụ, một phương thức đọc cấu hình có thể cam kết ném `IOException` khi truy cập dữ liệu thất bại. Khách hàng được quyền viết `catch (IOException e)` để thực hiện fallback. Nếu phiên bản mới đổi lỗi đó thành `IllegalStateException`, chữ ký phương thức có thể vẫn biên dịch, nhưng fallback cũ không còn hoạt động. Vì vậy đánh giá tương thích phải xét cả hợp đồng đã công bố lẫn hành vi thực tế.

### Checked và unchecked exception

- **Checked:** các lớp con của `Throwable` không thuộc nhánh `RuntimeException` hoặc `Error`; ví dụ `IOException`, `SQLException`. Chúng được kiểm tra tại thời điểm biên dịch theo quy tắc Java.
- **Unchecked:** `RuntimeException`, `Error` và các lớp con của chúng; ví dụ `IllegalArgumentException`, `IllegalStateException`. Trình biên dịch không yêu cầu `catch` hoặc `throws`, nhưng bên gọi vẫn có thể bắt.
- **Không dùng `Error` làm ngoại lệ nghiệp vụ.** Nó thường biểu thị lỗi nghiêm trọng ở mức runtime/hệ thống, không phải một đường xử lý lỗi thường lệ của API ứng dụng.

Một hợp đồng tốt nêu rõ **điều kiện phát sinh và lựa chọn xử lý**, thay vì chỉ liệt kê tên lớp ngoại lệ. `throws Exception` hoặc `throws Throwable` quá rộng thường làm người gọi khó quyết định phải xử lý điều gì.

## 2. Ba trục tương thích cần đánh giá riêng

| Loại tương thích | Câu hỏi phải trả lời | Ví dụ |
|---|---|---|
| **Mã nguồn (source)** | Biên dịch lại mã khách hàng hoặc lớp triển khai với API mới có thành công không? | Thêm `throws IOException` khiến một phương thức gọi cũ thiếu `catch`. |
| **Nhị phân (binary)** | Bản `.class` đã biên dịch có liên kết/chạy được với thư viện mới không? | Chỉ thay đổi mệnh đề `throws` không làm thay đổi JVM method descriptor. |
| **Hành vi (behavioral)** | Các luồng xử lý lỗi, retry, fallback, ghi log và phản hồi hệ thống có giữ nguyên ý nghĩa không? | Ngoại lệ cũ được bọc thành một runtime exception mà không giữ `cause`. |

**Điểm dễ nhầm:** theo Java Language Specification (JLS §13.4.21), thay đổi riêng mệnh đề `throws` của phương thức hoặc constructor **không phá vỡ tương thích nhị phân**; cơ chế kiểm tra checked exception diễn ra lúc biên dịch. Điều đó **không** có nghĩa thay đổi an toàn về mã nguồn hoặc hành vi. Nếu thay cả tên phương thức, tham số, kiểu trả về, khả năng truy cập, lớp exception hay logic thực thi, phải đánh giá các thay đổi đó độc lập.

## 3. Ma trận tác động của các thay đổi thường gặp

| Thay đổi ở API công khai | Khi biên dịch lại bên gọi/triển khai | Với nhị phân cũ nếu **chỉ đổi `throws`** | Rủi ro hành vi |
|---|---|---|---|
| **Thêm checked exception** `throws IOException` | Bên gọi phải bắt/khai báo; method reference hoặc lambda liên quan có thể không hợp lệ | Vẫn tương thích nhị phân | Đường lỗi mới có thể chưa được xử lý |
| **Xóa checked exception** khỏi `throws` | `catch` chuyên biệt có thể trở thành không hợp lệ; lớp override khai báo ngoại lệ cũ có thể lỗi | Vẫn tương thích nhị phân | Khách hàng không biết lỗi được đổi thành gì |
| **Đổi từ subtype sang supertype checked** (ví dụ `FileNotFoundException` → `IOException`) | Mở rộng phạm vi lỗi cần xử lý; caller bắt loại hẹp có thể thiếu xử lý | Vẫn tương thích nhị phân | Caller không phân biệt được một số trường hợp |
| **Thu hẹp từ supertype sang subtype checked** | Một số lớp override đang khai báo loại rộng sẽ không biên dịch lại; bên gọi có `catch` phù hợp thường vẫn hợp lệ | Vẫn tương thích nhị phân | Có thể thay đổi ý nghĩa cam kết lỗi |
| **Thêm/đổi sang unchecked exception** | Thường không cần khai báo mới, nhưng mã nguồn của `catch` checked cũ có thể lỗi nếu checked bị xóa | Nếu chỉ sửa `throws`, vẫn liên kết; logic ném lỗi là vấn đề riêng | Fallback, retry, thống kê lỗi, điều khiển giao dịch có thể thay đổi |
| **Giữ kiểu exception nhưng đổi điều kiện ném** | Có thể vẫn biên dịch | Có thể vẫn liên kết | Phá vỡ hợp đồng ngữ nghĩa dù không hề đổi chữ ký |
| **Đổi thông tin `cause`, error code hoặc loại wrapper** | Thường không được trình biên dịch cảnh báo | Thường không làm lỗi liên kết nếu không đổi cấu trúc công khai | Debug, phân loại lỗi và chính sách retry có thể sai |

Bảng trên không phải cam kết rằng mọi thay đổi đều an toàn nhị phân: phạm vi cột nhị phân chỉ là **thay đổi đơn thuần ở `throws`**. Nếu xóa class ngoại lệ công khai, đổi hệ phân cấp lớp, bỏ phương thức hoặc đổi descriptor, có thể gây lỗi ở lúc biên dịch, liên kết hoặc chạy.

## 4. Thêm checked exception: lỗi xuất hiện từ vị trí gọi

Giả sử phiên bản 1 công bố:

~~~java
// Trích đoạn khai báo API phiên bản 1, không phải chương trình độc lập.
public String fetch(String key);
~~~

Phiên bản 2 đổi thành:

~~~java
// Trích đoạn khai báo API phiên bản 2.
public String fetch(String key) throws java.io.IOException;
~~~

Mã khách hàng từng viết:

~~~java
String value = service.fetch("theme");
System.out.println(value);
~~~

Khi biên dịch lại với API phiên bản 2, trình biên dịch phát hiện checked exception chưa được xử lý. Bên gọi phải đặt đoạn lệnh trong `try/catch` hoặc thêm `throws IOException` vào phương thức bao quanh; nếu là constructor, cũng phải xét `throws` của constructor đó. Chỉ “thêm khai báo để biên dịch qua” có thể tiếp tục đẩy lỗi lên các tầng chưa sẵn sàng xử lý.

Sự thay đổi còn lan sang biểu thức lambda hoặc method reference:

~~~java
// Minh họa: Supplier.get() không khai báo checked exception.
java.util.function.Supplier<String> supplier = () -> service.fetch("theme");
~~~

Biểu thức trên có thể hợp lệ với phiên bản 1 nhưng không còn hợp lệ nếu `fetch` của phiên bản 2 ném `IOException`. Một functional interface tự định nghĩa với `run() throws IOException` có thể biểu đạt hợp đồng thích hợp hơn, hoặc API cần cung cấp một nhánh chuyển đổi lỗi có chủ đích.

## 5. Xóa hoặc thu hẹp checked exception cũng có thể phá mã nguồn

Phiên bản 1:

~~~java
// Trích đoạn API, không phải chương trình độc lập.
public String read() throws java.io.IOException;
~~~

Bên gọi:

~~~java
// Trích đoạn mã phía caller.
try {
    return api.read();
} catch (java.io.IOException ex) {
    return "default";
}
~~~

Nếu phiên bản 2 đổi thành `public String read()` và thân `try` không có lệnh nào khác có thể ném `IOException`, `catch (IOException)` sẽ báo lỗi biên dịch vì checked exception này không thể phát sinh từ khối `try` theo phân tích tĩnh. Đây là ví dụ điển hình của thay đổi tưởng như “giảm ràng buộc” nhưng lại phá mã nguồn khách hàng.

Ngoài caller, còn có **hệ phân cấp kế thừa**. Quy tắc override: phương thức ghi đè không được khai báo checked exception rộng hơn các loại được phương thức bị ghi đè cho phép. Ví dụ:

~~~java
// Các đoạn này biểu diễn API cũ và lớp triển khai đang hợp lệ.
interface Loader {
    String load() throws java.io.IOException;
}

class DiskLoader implements Loader {
    @Override
    public String load() throws java.io.IOException {
        throw new java.io.IOException("unavailable");
    }
}
~~~

Nếu ở phiên bản sau `Loader.load()` bỏ `throws IOException` hoặc thu hẹp chỉ còn `FileNotFoundException`, thì `DiskLoader.load()` ở trên **không thể biên dịch lại** nếu vẫn khai báo `IOException`. Ngược lại, thêm một checked exception được cho phép vào khai báo của interface không buộc implementation hiện tại phải ném nó, nhưng bên **gọi** qua interface vẫn phải cập nhật.

Quy tắc tương tự áp dụng cho abstract class, phương thức override và functional interface. Đối với constructor, việc thay đổi `throws` tác động trực tiếp tới biểu thức `new` và các constructor gọi `super(...)`.

## 6. Đổi lớp exception hoặc chuyển checked thành unchecked

Ví dụ API truy xuất dữ liệu từng khai báo `SQLException`, sau đó chuyển sang `DataAccessException extends RuntimeException`. Chữ ký mới có thể ngắn gọn hơn, song một caller từng `catch (SQLException)` không tự động bắt được `DataAccessException`. Khi biên dịch lại, `catch` checked cũ có thể không còn hợp lệ; với bản caller đã biên dịch, ngoại lệ mới có thể đi xuyên qua các handler cũ.

Để quyết định việc chuyển đổi, cần trả lời:

1. Caller có **cách khôi phục cụ thể** từ checked exception ban đầu không (retry, chọn nguồn dự phòng, yêu cầu người dùng sửa đầu vào)?
2. Các điểm chặn lỗi có dựa vào **kiểu cụ thể** hay quan hệ kế thừa của exception không?
3. Khi bọc ngoại lệ, `cause` có còn truy xuất được để điều tra lỗi và phân loại thông báo không?
4. Lỗi xảy ra **trước hay sau** tác dụng phụ (ghi file, thay đổi trạng thái, commit giao dịch)? Người gọi có thể thử lại an toàn không?
5. API đã công bố hành vi gì trong Javadoc và tài liệu versioning?

Nếu lựa chọn unchecked exception vì caller không thể xử lý hợp lý tại vị trí gọi, hãy dùng một kiểu đủ rõ nghĩa, chẳng hạn `UncheckedIOException` cho lỗi I/O được chuyển đổi, hoặc một exception miền nghiệp vụ có `cause`. Không nên đổi mọi lỗi thành `RuntimeException` chung, vì caller sẽ mất khả năng phân nhánh theo nguyên nhân.

### Chương trình Java 17+ chạy được: chuyển đổi lỗi mà giữ nguyên nguyên nhân

Ví dụ dưới đây minh họa **một API được thiết kế công khai để trả lỗi unchecked**. Nếu đang di chuyển từ API checked đã phát hành, cần thêm lộ trình tương thích ở phần 8; chỉ áp dụng lớp bọc không tự bảo đảm tương thích.

Lưu toàn bộ vào tệp `ExceptionContractDemo.java`:

~~~java
import java.io.IOException;

public class ExceptionContractDemo {
    static final class ConfigurationException extends RuntimeException {
        ConfigurationException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String loadRaw(boolean fail) throws IOException {
        if (fail) {
            throw new IOException("storage unavailable");
        }
        return "mode=prod";
    }

    static String load(boolean fail) {
        try {
            return loadRaw(fail);
        } catch (IOException cause) {
            throw new ConfigurationException("cannot load config", cause);
        }
    }

    public static void main(String[] args) {
        System.out.println(load(false));

        try {
            load(true);
        } catch (ConfigurationException ex) {
            System.out.println(ex.getClass().getSimpleName());
            System.out.println(ex.getCause().getClass().getSimpleName());
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ExceptionContractDemo.java
java ExceptionContractDemo
~~~

Đầu ra chuẩn chính xác:

~~~text
mode=prod
ConfigurationException
IOException
cannot load config
~~~

Ở đây `loadRaw` có hợp đồng checked `IOException`, còn `load` đưa ra hợp đồng unchecked `ConfigurationException`. Constructor `super(message, cause)` giữ được chuỗi nguyên nhân. Handler bên gọi của `load` cần nhận đúng `ConfigurationException`; nó không thể thay thế máy móc cho handler của một API checked cũ.

## 7. Các cam kết hành vi dễ bị bỏ sót

### 7.1. Phạm vi bắt lỗi và thứ tự `catch`

`catch (IOException)` bắt `IOException` cùng các lớp con, nhưng không bắt một `RuntimeException` không liên quan. Khi đổi ngoại lệ, nhánh fallback có thể không chạy. Với nhiều `catch`, phải đặt loại cụ thể trước loại rộng để tránh nhánh không thể tới; kiểm tra lại các khai báo trong `multi-catch` khi thay hệ phân cấp exception.

### 7.2. Nguyên nhân gốc và dữ liệu chẩn đoán

Cần giữ `cause` khi chuyển đổi ngoại lệ; tránh bắt rồi ném exception mới chỉ mang thông điệp và làm mất stack trace gốc. Thông điệp exception thường phục vụ chẩn đoán và không nên trở thành định dạng máy đọc ổn định nếu API chưa cam kết điều đó. Nếu caller cần phân loại bền vững, dùng **kiểu exception**, mã lỗi công khai hoặc thuộc tính có kiểu rõ ràng.

### 7.3. Ngắt luồng và hủy tác vụ

`InterruptedException` là tín hiệu kiểm soát việc chờ/hủy tác vụ. Nếu một API bắt rồi chuyển nó sang unchecked exception, cần cân nhắc khôi phục trạng thái interrupt để tầng ngoài nhận biết:

~~~java
// Đoạn minh họa nằm trong một phương thức đang bắt InterruptedException.
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("operation interrupted", ex);
}
~~~

Nếu API có thể khai báo `throws InterruptedException`, truyền ngoại lệ lên thường cho phép caller quyết định hủy tác vụ chính xác hơn. Không nuốt tín hiệu interrupt và tiếp tục xử lý như thể không có chuyện gì xảy ra.

### 7.4. Đóng tài nguyên và ngoại lệ bị suppress

Với `try-with-resources`, ngoại lệ phát sinh ở thân khối `try` thường là lỗi chính; ngoại lệ từ `close()` có thể được lưu trong `Throwable.getSuppressed()`. Việc chuyển đổi lỗi không nên làm mất thông tin này. Đổi khai báo `throws` của `AutoCloseable.close()` hoặc thay loại tài nguyên có thể kéo theo yêu cầu xử lý checked exception tại nơi sử dụng.

### 7.5. Bất đồng bộ, reflection và framework

Trong `CompletableFuture`, thất bại có thể được truyền qua exceptional completion; `join()` thường ném `CompletionException`, còn `get()` dùng `ExecutionException` để bao nguyên nhân. Chuyển một thao tác đồng bộ sang bất đồng bộ vì thế thay cả **kênh** nhận lỗi, không chỉ tên exception.

Reflection và một số framework quan sát được danh sách exception khai báo qua `Method.getExceptionTypes()`; cơ chế gọi phản xạ có thể bọc lỗi trong `InvocationTargetException`. Proxy, interceptor, logging, mapper HTTP, cấu hình retry và giao dịch cũng có thể rẽ nhánh theo loại exception. Một thay đổi không bị JVM từ chối vẫn có thể làm các tầng tích hợp vận hành khác trước.

## 8. Chiến lược tiến hóa API giảm nguy cơ phá vỡ khách hàng

### Cách 1: giữ API cũ và thêm entry point mới

Khi muốn cung cấp bản unchecked, một chiến lược rõ ràng là **giữ nguyên phương thức cũ** (tên, tham số, kiểu trả về và hợp đồng lỗi), đồng thời thêm phương thức mới khác tên. Ví dụ lớp thư viện đã có `read(Path)`:

~~~java
// Trích đoạn trong một lớp thư viện, với import java.io.*,
// java.nio.file.Files và java.nio.file.Path.
public byte[] read(Path path) throws IOException {
    return Files.readAllBytes(path);
}

public byte[] readUnchecked(Path path) {
    try {
        return read(path);
    } catch (IOException ex) {
        throw new UncheckedIOException("cannot read " + path, ex);
    }
}
~~~

Caller cũ vẫn gọi `read` và xử lý `IOException`; caller mới có thể chủ động chọn `readUnchecked`. Hai nhánh nên được kiểm thử để bảo đảm cùng một nguyên nhân lỗi không bị diễn giải khác nhau ngoài chủ đích.

### Cách 2: mở rộng bằng loại con có ý nghĩa

Nếu API khai báo `throws IOException`, việc implementation ném một **subtype của `IOException`** có thể vẫn đi qua handler bắt `IOException` hiện hữu. Đây thường là lựa chọn ít gây xáo trộn hơn ném một ngoại lệ checked không liên quan. Tuy nhiên caller bắt subtype riêng, theo dõi loại lỗi cụ thể hoặc có chính sách retry vẫn có thể bị ảnh hưởng; hãy tài liệu hóa điều kiện mới.

### Cách 3: lộ trình deprecate và phiên bản hóa

Nếu bắt buộc thay đổi hợp đồng cũ, nên công bố trước điều kiện lỗi, đường migration, ví dụ thay thế `catch`, mốc deprecation và phiên bản áp dụng. Với thay đổi lớn khó tránh phá mã nguồn, cân nhắc phát hành phiên bản API mới có tên hoặc package riêng, hoặc major version theo chính sách tương thích của thư viện. Không đánh dấu `@Deprecated` là đã giải quyết xong vấn đề: annotation chỉ báo cho người dùng, không tự bảo đảm hai hành vi cùng đúng.

### Những việc không nên dùng để “sửa nhanh”

- Thêm `throws Exception` khắp tầng ứng dụng: code có thể qua biên dịch nhưng hợp đồng càng khó kiểm soát.
- Đổi hết checked exception thành `RuntimeException` rồi giả định không có breaking change.
- Bắt `Exception` hay `Throwable` ở mọi nơi để che sự không tương thích.
- Bắt ngoại lệ rồi `return null` hoặc `Optional.empty()` mà không phân biệt **không có dữ liệu** với **thao tác thất bại**, trừ khi API đã cam kết rõ.
- Bỏ `cause`, bỏ `suppressed` hoặc nuốt `InterruptedException` khi làm wrapper.
- Phụ thuộc vào nội dung `getMessage()` làm protocol ổn định nếu thông điệp chỉ phục vụ con người.

## 9. Quy trình kiểm tra tương thích trước khi phát hành

1. **Liệt kê hợp đồng cũ và mới:** từng phương thức/constructor công khai, checked exception trong `throws`, runtime exception được tài liệu hóa, điều kiện lỗi, lớp exception và subtype được xuất bản.
2. **Đối chiếu bên dùng:** nơi gọi trực tiếp, `catch` chuyên biệt, method reference, lambda, constructor chaining, lớp `extends` hoặc `implements`, xử lý giao dịch và retry.
3. **Biên dịch lại mã khách hàng:** đặc biệt kiểm tra các trường hợp thêm checked exception, xóa checked exception có `catch` riêng, và thu hẹp hợp đồng của phương thức bị ghi đè.
4. **Thử nhị phân cũ với thư viện mới:** dùng artifact của caller đã biên dịch trước thay đổi. Phân biệt lỗi liên kết JVM với lỗi hành vi khi ngoại lệ thực tế thay đổi; có thể xem method descriptor bằng `javap -s` và metadata khai báo ngoại lệ bằng `javap -v`.
5. **Kiểm thử hành vi thất bại:** kiểm tra đúng class/cause của exception, tài nguyên được đóng, interrupt flag, side effect, fallback, retry, logs và phản hồi public-facing. Bao gồm nhiều exception gần nhau trong hệ phân cấp.
6. **Công bố migration:** nêu điều kiện thay đổi, phạm vi ảnh hưởng, cách thay handler và lịch loại bỏ API cũ. Chỉ xác nhận tương thích theo những trục đã kiểm thử.

### Bảng quyết định nhanh

| Tình huống | Hướng xử lý nên ưu tiên |
|---|---|
| Cần thêm một nguyên nhân lỗi checked cho API đã phát hành | Cân nhắc giữ hợp đồng cũ và cung cấp API mới, hoặc dùng subtype phù hợp với loại đã công bố; đánh giá caller trước khi thêm `throws`. |
| Muốn đơn giản hóa caller bằng unchecked exception | Giữ API checked cũ và thêm phương thức mới có tên, ngữ nghĩa và `cause` rõ ràng. |
| Muốn bỏ một ngoại lệ không còn phát sinh | Kiểm tra `catch` checked cũ và các lớp override; tài liệu hóa hành vi thay thế, tránh thay trực tiếp nếu gây lỗi biên dịch trên khách hàng. |
| Muốn thu hẹp `throws` ở interface | Kiểm tra tất cả implementation hiện có và khả năng họ biên dịch lại. |
| Chỉ đổi văn bản thông báo lỗi | Xác nhận không có hệ thống đã được cam kết dùng văn bản đó như mã máy đọc; ưu tiên error code ổn định. |
| Code vẫn liên kết nhưng fallback không chạy | Kiểm tra loại ngoại lệ thực tế, wrapper và `cause`, không kết luận an toàn chỉ từ kết quả build. |

## 10. Ghi nhớ

- **`throws` thuộc hợp đồng biên dịch của checked exception; loại exception thực tế và quy tắc xử lý tạo nên hợp đồng hành vi.**
- **Tương thích nhị phân không đồng nghĩa tương thích mã nguồn hoặc hành vi.** Chỉ đổi mệnh đề `throws` được JLS bảo đảm không phá liên kết nhị phân, nhưng khách hàng biên dịch lại vẫn có thể lỗi.
- **Xóa một checked exception cũng có thể là breaking change** vì `catch` cũ và override.
- Khi cần cải tiến API đã được sử dụng rộng rãi, giữ đường đi cũ hoạt động và công bố một đường mới rõ ràng thường dễ kiểm soát hơn đổi loại exception đột ngột.
- Đánh giá cuối cùng phải có cả **biên dịch lại**, **chạy nhị phân cũ**, và **test hành vi lỗi**.

### Tham chiếu tiêu chuẩn

- [JLS §11.2 — Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2)
- [JLS §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3)
- [JLS §13.4.21 — Method and Constructor Throws](https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html#jls-13.4.21)
