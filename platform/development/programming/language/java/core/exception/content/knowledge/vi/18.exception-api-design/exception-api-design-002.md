# Chọn checked hay unchecked theo hợp đồng và khả năng xử lý trong Java

Một API Java phải cho người gọi biết **khi nào thao tác không thể hoàn thành** và bên gọi được kỳ vọng làm gì. Quyết định chọn **checked exception** hay **unchecked exception** không chỉ là chọn `extends Exception` hoặc `extends RuntimeException`: đó là quyết định về **hợp đồng giữa người triển khai và người sử dụng API**, đặc biệt về khả năng xử lý, phục hồi và chi phí lan truyền ngoại lệ qua nhiều tầng.

Nguyên tắc thực dụng: nếu một tình huống thất bại là **phần được dự kiến của thao tác** và phía sử dụng API có **hành động xử lý hợp lý** (thử lại, hỏi đầu vào khác, dùng nguồn dự phòng, bỏ qua một bản ghi theo chính sách, hoặc thực hiện bù trừ), **checked exception có thể phù hợp** để buộc caller xem xét tình huống ấy. Nếu lỗi biểu thị **dùng API sai, vi phạm tiền điều kiện, bug/invariant bị phá vỡ**, hoặc phía gọi không có chính sách phục hồi tại tầng đó, **unchecked exception thường phù hợp**.

Đây là **hướng dẫn thiết kế**, không phải quy tắc cơ học được Java cưỡng chế. Có lỗi hạ tầng bên ngoài được biểu diễn bằng checked `IOException`, cũng có lỗi I/O được bao bằng unchecked `UncheckedIOException` khi đi qua API callback không khai báo `throws`. Một caller có thể phục hồi một số unchecked exception, và một caller khác có thể không phục hồi nổi checked exception. Quan trọng là **hợp đồng cụ thể, mức độ ổn định của API, ranh giới trách nhiệm và ngữ nghĩa lỗi**.

Bài viết dùng Java 17+ để giải thích hệ phân cấp, `catch-or-specify`, cách đánh giá khả năng phục hồi, lựa chọn kiểu lỗi theo tầng, giữ cause khi dịch ngoại lệ, ngoại lệ trong interface/override, callback/bất đồng bộ, thử lại, transaction, lỗi đóng tài nguyên, `InterruptedException`, cách kiểm thử và những anti-pattern nên tránh.

## 1. Checked và unchecked: chính xác là gì?

Java phân loại theo hệ phân cấp `Throwable`:

~~~text
java.lang.Throwable
  ├── java.lang.Error                       [unchecked]
  │     ├── AssertionError
  │     └── VirtualMachineError
  └── java.lang.Exception
        ├── IOException                    [checked]
        ├── SQLException                   [checked]
        ├── InterruptedException           [checked]
        ├── CustomFailure extends Exception [checked, nếu không thuộc RuntimeException]
        └── java.lang.RuntimeException     [unchecked]
              ├── IllegalArgumentException
              ├── IllegalStateException
              ├── NullPointerException
              └── CustomFailure extends RuntimeException
~~~

Theo JLS §11.1.1, **unchecked exception classes** gồm `RuntimeException` và các lớp con, `Error` và các lớp con. Các lớp ngoại lệ còn lại trong nhánh `Throwable` là **checked**. Thông thường custom checked exception được tạo bằng `extends Exception`, còn custom unchecked exception bằng `extends RuntimeException`.

| Yếu tố | Checked | Unchecked |
| --- | --- | --- |
| Kế thừa thông dụng | `Exception` nhưng không thuộc nhánh `RuntimeException` | `RuntimeException` hoặc nhánh `Error` |
| Trình biên dịch buộc `catch` hoặc `throws`? | Có, khi checked exception có thể thoát khỏi phương thức và không được xử lý | Không |
| Có được khai báo `throws`? | Có | Có, nhưng không bắt buộc |
| Có lan truyền qua call stack nếu không bị bắt? | Có | Có |
| Có mang `message`, `cause`, `stack trace`? | Có | Có |
| Có thể được `catch`? | Có | Có, nếu chính sách phù hợp |
| Compiler có buộc caller **phục hồi thành công**? | Không; chỉ buộc bắt hoặc khai báo | Không |
| Dùng cho lỗi đầu vào/API misuse? | Tùy hợp đồng | Thường là `IllegalArgumentException` hoặc loại phù hợp |
| Dùng cho lỗi môi trường có khả năng sửa? | Thường là lựa chọn đáng cân nhắc | Cũng có thể phù hợp ở tầng không thể khai báo checked |

**Điểm quan trọng:** `catch-or-specify` là nghĩa vụ **tại biên dịch**, không phải bảo đảm lỗi đã được giải quyết. Caller có thể khai báo `throws` và chuyển trách nhiệm lên tầng trên. Ngược lại, unchecked vẫn có thể làm chương trình kết thúc đột ngột nếu không có tầng xử lý.

## 2. Ví dụ 1: sự khác nhau của hợp đồng ngay tại phương thức

Lưu thành `CheckedUncheckedContractDemo.java`:

~~~java
public class CheckedUncheckedContractDemo {
    static class DocumentUnavailableException extends Exception {
        DocumentUnavailableException(String message) {
            super(message);
        }
    }

    static class InvalidDocumentIdException extends RuntimeException {
        InvalidDocumentIdException(String message) {
            super(message);
        }
    }

    static String load(String id) throws DocumentUnavailableException {
        if (id == null || id.isBlank()) {
            throw new InvalidDocumentIdException("id must not be blank");
        }
        if ("offline".equals(id)) {
            throw new DocumentUnavailableException("document store offline");
        }
        return "document:" + id;
    }

    public static void main(String[] args) {
        try {
            System.out.println("ok=" + load("A-1"));
            load("offline");
        } catch (DocumentUnavailableException ex) {
            System.out.println("checked=" + ex.getMessage());
        }

        try {
            load("");
        } catch (InvalidDocumentIdException ex) {
            System.out.println("unchecked=" + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 CheckedUncheckedContractDemo.java
java CheckedUncheckedContractDemo
~~~

Kết quả:

~~~text
ok=document:A-1
checked=document store offline
unchecked=id must not be blank
~~~

Giải thích:

- `DocumentUnavailableException extends Exception` là checked; `load` khai báo `throws DocumentUnavailableException` và caller bắt loại đó.
- `InvalidDocumentIdException extends RuntimeException` là unchecked; compiler không bắt buộc thêm nó vào `throws`. Nó diễn đạt **vi phạm tiền điều kiện của API**.
- Người gọi vẫn có thể bắt unchecked nếu thật sự cần biến lỗi tham số thành thông báo giao diện. Nhưng một tầng khác có thể chỉ cần sửa bug truyền tham số sai.
- Hai loại lỗi có **ý nghĩa khác nhau**: tài liệu tạm không truy cập được có thể gợi ý thử lại, còn ID rỗng phải được sửa tại đầu vào; không nên chọn kiểu chỉ dựa vào nơi exception được tạo.

Nếu bỏ `try-catch` hoặc `throws` cho `DocumentUnavailableException`, compiler từ chối khi phân tích lời gọi có thể phát sinh ngoại lệ checked. Nhưng ngay cả khi code biên dịch, vẫn cần chính sách thực tế sau khi bắt nó.

## 3. Khả năng xử lý hợp lý nghĩa là gì?

Một câu hỏi hữu ích trước khi thiết kế loại ngoại lệ là: **caller cụ thể có thể đưa hệ thống về trạng thái hợp lệ sau lỗi không?**

Các hành động xử lý có ý nghĩa có thể gồm:

1. **Thử lại có giới hạn**, khi lỗi có khả năng tạm thời và thao tác có thể retry an toàn.
2. **Chuyển sang nguồn dự phòng** đã được xác thực, khi fallback không làm sai dữ liệu.
3. **Yêu cầu sửa đầu vào**, chẳng hạn chọn file khác hoặc cấu hình lại vị trí lưu trữ.
4. **Bỏ qua mục lỗi có ghi nhận**, nếu mỗi mục độc lập và chính sách cho phép.
5. **Bù trừ/rollback**, khi một thao tác bị thất bại và trạng thái đã thay đổi một phần.
6. **Chuyển lỗi lên tầng có quyền quyết định**, bằng `throws` hoặc domain exception có cause.
7. **Dừng tác vụ đúng cách**, khi không có cơ hội phục hồi nhưng tầng hiện tại có trách nhiệm shutdown, cleanup, trả thông tin lỗi hoặc báo trạng thái thất bại.

**Chỉ log rồi nuốt ngoại lệ không được coi là phục hồi.** Tương tự, viết `catch (Exception ex) { throw new RuntimeException(ex); }` tự nó chỉ đổi cách lan truyền lỗi, không giúp phục hồi.

Một hệ thống xử lý lệnh có thể có caller A là giao diện người dùng, có thể đề nghị sửa một đường dẫn; caller B là job tự động, không thể hỏi người dùng và chỉ có thể báo thất bại. Cùng lỗi `IOException` nhưng chiến lược ở hai tầng khác nhau. Vì vậy quyết định checked/unchecked phải xét **đối tượng sử dụng API mục tiêu**, không chỉ tên ngoại lệ.

## 4. Bảng quyết định theo tình huống thực tế

| Tình huống | Lựa chọn thường đáng cân nhắc | Lý do / lưu ý |
| --- | --- | --- |
| Caller truyền chỉ số ngoài phạm vi công bố | `IndexOutOfBoundsException` unchecked | Vi phạm hợp đồng dùng API |
| Tham số bắt buộc nhưng nhận `null` | `NullPointerException` unchecked hoặc validation riêng | Code có thể sửa tại ranh giới |
| Phương thức gọi khi đối tượng đã đóng | `IllegalStateException` unchecked | Trạng thái không cho phép thao tác |
| Người dùng chọn file không tồn tại | `IOException` / checked domain exception | Caller có thể chọn file khác; không bắt buộc ở mọi API |
| Đọc từ thiết bị/mạng tạm thời lỗi | Checked hoặc unchecked domain exception | Xét quyền retry, idempotency, framework và tầng gọi |
| Lỗi quy tắc nghiệp vụ mà caller được yêu cầu điều chỉnh | Checked domain exception, validation result hoặc unchecked | Tùy liệu thất bại là đường nghiệp vụ dự kiến và contract giao tiếp |
| Lỗi SQL tại repository | `SQLException` checked ở API JDBC | Tầng service có thể dịch sang checked/unchecked domain failure |
| Lỗi I/O bên trong `Stream.map` | `UncheckedIOException` | `Function.apply` không khai báo checked |
| Vi phạm invariant do bug nội bộ | Unchecked, đôi khi `AssertionError` trong debug | Không ép caller xử lý như thất bại có thể phục hồi |
| API xử lý bulk input và cần báo nhiều dòng sai | `Result`/danh sách lỗi thay vì ném liên tục | Thất bại từng mục là kết quả dự kiến |
| Thread bị yêu cầu ngắt khi chờ | `InterruptedException` checked | Cần truyền tiếp hoặc restore interrupt đúng hợp đồng |
| JVM gặp `OutOfMemoryError` | `Error`, không tạo custom business Error | Thường không phục hồi đáng tin; cần thiết kế khả năng dừng/giám sát |

Đây là **bảng gợi ý**, không phải ánh xạ bắt buộc trong JLS. Ngay cả một lỗi do môi trường cũng có thể được biểu diễn dưới dạng unchecked khi thiết kế API đích yêu cầu như vậy; lúc ấy phải công bố rõ kiểu lỗi, giữ cause và chính sách xử lý.

## 5. Ví dụ 2: checked exception khi caller có phương án fallback

Giả sử một API tìm dữ liệu trên dịch vụ ngoài. Nếu đường truy cập tạm thời hỏng nhưng có dữ liệu cache được **xác nhận hợp lệ**, caller có thể chọn fallback. Đó là một tình huống mà checked exception giúp caller cân nhắc phương án.

Lưu thành `CheckedFallbackDemo.java`:

~~~java
import java.io.IOException;

public class CheckedFallbackDemo {
    static String remoteRead(boolean unavailable) throws IOException {
        if (unavailable) {
            throw new IOException("remote unavailable");
        }
        return "fresh-value";
    }

    static String readWithFallback(
            boolean remoteUnavailable, String cached) throws IOException {
        try {
            return remoteRead(remoteUnavailable);
        } catch (IOException ex) {
            if (cached != null) {
                return cached;
            }
            throw ex;
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println("remote="
                    + readWithFallback(false, "cached-value"));
            System.out.println("fallback="
                    + readWithFallback(true, "cached-value"));
            readWithFallback(true, null);
        } catch (IOException ex) {
            System.out.println("propagate=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CheckedFallbackDemo.java
java CheckedFallbackDemo
~~~

Kết quả:

~~~text
remote=fresh-value
fallback=cached-value
propagate=remote unavailable
~~~

Trong ví dụ, `readWithFallback` chỉ dùng cache khi cache tồn tại. Nếu không có cache, nó **ném lại nguyên ngoại lệ IOException**, để tầng trên quyết định. Đây mới là chính sách lỗi có chủ đích.

Trong ứng dụng thật, một cache “có dữ liệu” chưa chắc “đủ an toàn để dùng”: còn cần tuổi dữ liệu, tính nhất quán, quyền truy cập, phiên bản và yêu cầu độ mới. **Không làm fallback giả** bằng cách trả chuỗi rỗng hoặc dữ liệu bịa chỉ để tránh ngoại lệ.

## 6. Ví dụ 3: lỗi misuse nên được phát hiện bằng unchecked exception

Nếu caller truyền một `quantity` bằng 0 vào API có hợp đồng chỉ chấp nhận số dương, đây thường là **tiền điều kiện bị vi phạm**. Caller phải sửa đầu vào trước khi gọi; compiler không cần buộc xử lý checked exception ở mọi nơi.

Lưu thành `ArgumentContractDemo.java`:

~~~java
public class ArgumentContractDemo {
    static int price(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        return Math.multiplyExact(quantity, 10);
    }

    public static void main(String[] args) {
        System.out.println("price=" + price(3));

        try {
            price(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArgumentContractDemo.java
java ArgumentContractDemo
~~~

Kết quả:

~~~text
price=30
invalid=quantity must be positive
~~~

Lỗi tham số được kiểm tra **bằng mã luôn chạy**, không bằng `assert` có thể bị vô hiệu hóa. Việc dùng `Math.multiplyExact` còn giúp phát hiện overflow số học bằng `ArithmeticException` khi có số lượng lớn gây tràn.

Một tình huống khác cần phân biệt: người dùng nhập chuỗi `"abc"` vào trường số lượng. Đây là lỗi xác thực đầu vào ở ranh giới UI/API. Tầng nhận request có thể trả `ValidationResult` hoặc map `NumberFormatException` thành lỗi trường; không nhất thiết phải tạo checked exception bắt buộc ở mọi lớp chỉ vì người dùng có thể sửa dữ liệu.

## 7. Đặt ranh giới hợp đồng: hạ tầng, domain, giao diện

Giả sử các tầng:

~~~text
HTTP / CLI / Batch boundary
          |
          v
Application service
          |
          v
Repository / external client
          |
          v
Database / file / network
~~~

Một lỗi hạ tầng như `SQLException` hoặc `IOException` có thể có ngữ nghĩa khác ở mỗi tầng:

- **Repository** hiểu lỗi theo công nghệ: kết nối cơ sở dữ liệu, tệp hỏng, giới hạn truy cập.
- **Application service** hiểu mục tiêu nghiệp vụ: không lấy được đơn hàng, không tạo được báo cáo, không lưu được thanh toán.
- **HTTP/UI boundary** hiểu hành động tiếp theo: trả mã lỗi, đề nghị thử lại, yêu cầu sửa tham số, hủy giao dịch, hiển thị thông báo hoặc thông báo cho vận hành.

Không phải mọi tầng đều cần bọc ngoại lệ. Chỉ **dịch loại lỗi khi vượt qua một ranh giới có ý nghĩa**, ví dụ khi repository không muốn lộ `SQLException` như một phần public contract của service.

Khi chuyển, ưu tiên constructor dạng:

~~~java
public OrderLoadException(String message, Throwable cause) {
    super(message, cause);
}
~~~

Đây là **constructor minh họa** của lớp kế thừa Exception hoặc RuntimeException có constructor tương ứng. `message` chứa ý nghĩa ở tầng hiện tại; `cause` giữ **chính đối tượng lỗi gốc** cùng stack trace và suppressed exceptions của nó. Đừng chỉ dùng `new OrderLoadException(ex.getMessage())` nếu còn cần chẩn đoán cause chain.

## 8. Ví dụ 4: chuyển lỗi hạ tầng thành checked domain exception

Giả sử tầng repository có thể ném `IOException` nhưng service muốn công bố một lỗi có ý nghĩa nghiệp vụ, để caller chọn nguồn dự phòng hoặc hiển thị trạng thái không khả dụng.

Lưu thành `CheckedTranslationDemo.java`:

~~~java
import java.io.IOException;

public class CheckedTranslationDemo {
    static final class ReportUnavailableException extends Exception {
        ReportUnavailableException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String repository() throws IOException {
        throw new IOException("storage offline");
    }

    static String loadReport() throws ReportUnavailableException {
        try {
            return repository();
        } catch (IOException ex) {
            throw new ReportUnavailableException(
                    "Report cannot be loaded", ex);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(loadReport());
        } catch (ReportUnavailableException ex) {
            System.out.println("domain=" + ex.getMessage());
            System.out.println("causeType="
                    + ex.getCause().getClass().getSimpleName());
            System.out.println("causeMessage="
                    + ex.getCause().getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CheckedTranslationDemo.java
java CheckedTranslationDemo
~~~

Kết quả:

~~~text
domain=Report cannot be loaded
causeType=IOException
causeMessage=storage offline
~~~

Đây là **exception translation**, không phải “xử lý thành công”. Caller biết service không hoàn thành thao tác và nhận loại lỗi domain mà service đã công bố. Một interface service có thể dùng `throws ReportUnavailableException` để buộc các caller trực tiếp xem xét trường hợp này.

Nếu service chỉ truyền nguyên `IOException` mà hợp đồng cũng đã hứa về IOException thì việc bọc lại là không cần thiết. Ngược lại, nếu tầng gọi không nên phụ thuộc API hạ tầng, một domain exception ổn định giúp thay implementation bên dưới mà ít ảnh hưởng caller.

## 9. Ví dụ 5: chuyển sang unchecked tại ranh giới API khi có lý do

Một API có thể chọn unchecked domain exception cho lỗi dịch vụ để không buộc mọi caller ở nhiều tầng thêm `throws`, hoặc vì framework callback không hỗ trợ checked exception. Khi đó vẫn cần **tên loại lỗi rõ ràng và bảo toàn nguyên nhân gốc**.

Lưu thành `UncheckedTranslationDemo.java`:

~~~java
import java.io.IOException;

public class UncheckedTranslationDemo {
    static final class StorageFailure extends RuntimeException {
        StorageFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String readStorage() throws IOException {
        throw new IOException("disk unavailable");
    }

    static String service() {
        try {
            return readStorage();
        } catch (IOException ex) {
            throw new StorageFailure("Service data unavailable", ex);
        }
    }

    public static void main(String[] args) {
        try {
            System.out.println(service());
        } catch (StorageFailure ex) {
            System.out.println("domain=" + ex.getMessage());
            System.out.println("checkedRequired=false");
            System.out.println("causeIsIOException="
                    + (ex.getCause() instanceof IOException));
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 UncheckedTranslationDemo.java
java UncheckedTranslationDemo
~~~

Kết quả:

~~~text
domain=Service data unavailable
checkedRequired=false
causeIsIOException=true
~~~

Dòng `checkedRequired=false` mô tả hợp đồng biên dịch: `StorageFailure extends RuntimeException` không bắt buộc `throws`. **Nó không chứng minh lỗi đã được khắc phục**. Nếu không có nhánh catch, StorageFailure vẫn sẽ lan truyền.

Đừng biến mọi checked exception thành unchecked chỉ để xóa cảnh báo compiler. Trước khi dịch, xác định **ai nhận trách nhiệm xử lý** và API công khai có mô tả đầy đủ loại lỗi mới hay không. Đổi sang unchecked có thể làm caller cũ không còn được compiler nhắc phải xử lý tình huống mà nghiệp vụ từng xem là quan trọng.

## 10. `throws` là một phần của hợp đồng, không phải danh sách tuyệt đối mọi lỗi

Ví dụ chữ ký:

~~~java
String fetchReport(String key) throws ReportUnavailableException;
~~~

Đây là **phương thức interface/minh họa**, giả định ReportUnavailableException là checked exception.

Ý nghĩa: chương trình có thể để checked exception ấy thoát ra khi thực thi, và caller cần bắt hoặc khai báo loại đó (hoặc lớp cha phù hợp). Điều này **không** có nghĩa:

- Phương thức **luôn** ném lỗi mỗi lần chạy.
- Không có unchecked exception nào khác có thể xảy ra.
- Việc caller viết `catch` bảo đảm đã phục hồi.
- Compiler bắt buộc caller biết tất cả lỗi môi trường có thể xảy ra dưới dạng checked exception.

Các checked exceptions có thể được xử lý bằng `catch` tại chỗ hoặc lan truyền với `throws`. `throws RuntimeException` cũng hợp lệ nhưng không tạo nghĩa vụ compiler tương tự.

**Không viết `throws Exception` theo thói quen** nếu public API có thể dùng các loại lỗi cụ thể hơn. Một kiểu quá rộng khiến caller khó biết nên retry, sửa input, hiển thị thông báo hay dừng. Nhưng nếu API thực sự có contract cho nhiều lỗi độc lập và không thể biểu diễn rõ bằng loại cụ thể, cân nhắc interface riêng, error type/domain hierarchy hoặc Result.

## 11. Interface và override: ràng buộc về checked exception

Một interface là hợp đồng cho mọi implementation. Java không cho override một phương thức bằng chữ ký ném **checked exception rộng hơn** hợp đồng mà nó override (JLS §8.4.8.3).

Ví dụ đúng:

~~~java
interface Loader {
    String load() throws java.io.IOException;
}

class MemoryLoader implements Loader {
    @Override
    public String load() {
        return "cached";
    }
}
~~~

Đây là **hai khai báo hợp lệ** khi ở cùng file/package; implementation thu hẹp bằng cách không ném checked exception nào. Ở điểm gọi qua tham chiếu kiểu `Loader`, compiler vẫn dựa trên `throws IOException` của interface.

### Ví dụ 6: kiểu khai báo của tham chiếu quyết định nghĩa vụ checked

Lưu thành `InterfaceContractDemo.java`:

~~~java
import java.io.IOException;

public class InterfaceContractDemo {
    interface Loader {
        String load() throws IOException;
    }

    static class MemoryLoader implements Loader {
        @Override
        public String load() {
            return "cached";
        }
    }

    public static void main(String[] args) {
        Loader asInterface = new MemoryLoader();
        MemoryLoader asConcrete = new MemoryLoader();

        try {
            System.out.println("interface=" + asInterface.load());
        } catch (IOException ex) {
            System.out.println("unexpected I/O");
        }

        System.out.println("concrete=" + asConcrete.load());
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterfaceContractDemo.java
java InterfaceContractDemo
~~~

Kết quả:

~~~text
interface=cached
concrete=cached
~~~

Cùng đối tượng runtime MemoryLoader nhưng hai kiểu tham chiếu dẫn đến **hợp đồng biên dịch** khác nhau. `asInterface.load()` cần xử lý/khai báo IOException; `asConcrete.load()` không khai báo checked exception.

Ví dụ không hợp lệ:

~~~java
// CỐ Ý KHÔNG BIÊN DỊCH:
interface Service {
    void run() throws java.io.IOException;
}

class InvalidService implements Service {
    @Override
    public void run() throws Exception {
    }
}
~~~

Override bằng `throws Exception` mở rộng checked exception được phép so với `throws IOException`, vì vậy compiler từ chối. Muốn triển khai, dùng loại checked giống hoặc hẹp hơn, xử lý lỗi nội bộ, hoặc đổi hợp đồng interface một cách có chủ ý.

**Hệ quả khi thiết kế thư viện:** thêm một checked exception mới vào `throws` của public method có thể khiến code client trước đây đang biên dịch trở thành không hợp lệ. Thay đổi hợp đồng cần đánh giá ảnh hưởng tương thích mã nguồn.

## 12. Khi dùng callback/Stream, checked exception có thể không hợp đồng được

Một số functional interface chuẩn như `Function<T,R>`, `Consumer<T>`, `Supplier<T>` và `Runnable` **không khai báo checked exceptions** trong phương thức trừu tượng. Vì thế, lambda truyền cho `Stream.map` không thể trực tiếp ném `IOException` checked ra ngoài.

Đoạn sau **cố ý không biên dịch**:

~~~java
// GIẢ SỬ read(String) throws IOException:
java.util.function.Function<String, String> f =
        text -> read(text); // IOException chưa được xử lý trong lambda.
~~~

Không thể sửa bằng cách chỉ thêm `throws IOException` vào phương thức **tạo lambda**; thân lambda phải tương thích với **function type đích**.

Ba phương án thường dùng:

1. **Catch ngay trong lambda** khi có giá trị fallback thực sự hợp lệ.
2. **Bọc IOException bằng UncheckedIOException** và giữ cause, nếu callback phải báo lỗi cho tầng ngoài mà interface không khai báo checked.
3. **Thiết kế functional interface riêng có throws E** khi kiểm soát API và muốn giữ checked exception qua callback.

### Ví dụ 7: adapter I/O sang Function

Lưu thành `CallbackExceptionDemo.java`:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.function.Function;

public class CallbackExceptionDemo {
    @FunctionalInterface
    interface IOFunction<T, R> {
        R apply(T input) throws IOException;
    }

    static <T, R> Function<T, R> unchecked(IOFunction<T, R> operation) {
        return input -> {
            try {
                return operation.apply(input);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        };
    }

    static String fetch(String id) throws IOException {
        if ("bad".equals(id)) {
            throw new IOException("remote read failed");
        }
        return "ok:" + id;
    }

    public static void main(String[] args) {
        Function<String, String> f = unchecked(CallbackExceptionDemo::fetch);
        System.out.println(f.apply("A"));

        try {
            f.apply("bad");
        } catch (UncheckedIOException ex) {
            System.out.println("wrapper="
                    + ex.getClass().getSimpleName());
            System.out.println("cause=" + ex.getCause().getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CallbackExceptionDemo.java
java CallbackExceptionDemo
~~~

Kết quả:

~~~text
ok:A
wrapper=UncheckedIOException
cause=remote read failed
~~~

Adapter làm rõ **tại nơi nào hợp đồng checked được chuyển thành unchecked**. Ứng dụng không tự suy ra mọi IOException là không thể phục hồi; nó chỉ nêu rằng lời gọi qua Function thông thường không có `throws IOException`. Bên nhận callback vẫn phải có cơ chế xử lý thất bại phù hợp.

Nếu viết một API mới mà caller có quyền bắt checked exception, dùng interface riêng như `IOFunction` thay vì luôn ép qua `Function` có thể là lựa chọn tốt hơn.

## 13. Khi thất bại là kết quả thông thường, cân nhắc Result/Outcome

Không phải mọi trường hợp “không thành công” đều cần ném exception. Ví dụ, nhập hàng loạt mã đơn hàng: một vài mã bị sai định dạng là tình huống **được dự kiến trước** và muốn báo tất cả lỗi để người dùng sửa cùng lúc.

Một giá trị kết quả có trạng thái rõ ràng có thể phù hợp hơn:

~~~text
parse item
  ├── hợp lệ  -> Success(value)
  └── sai     -> Failure(code, field)
~~~

Khi dùng Result, caller phải kiểm tra trạng thái nhưng không bắt exception ở mỗi phần tử. Tuy nhiên, **đừng biến lỗi hạ tầng nghiêm trọng thành giá trị trông như thành công** hoặc bỏ nguyên nhân khi cần vận hành.

### Ví dụ 8: phân biệt validation result và lỗi bất thường

Lưu thành `ValidationResultDemo.java`:

~~~java
import java.util.List;

public class ValidationResultDemo {
    record ValidationResult(String raw, Integer value, String errorCode) {
        boolean success() {
            return errorCode == null;
        }
    }

    static ValidationResult parsePositive(String raw) {
        try {
            int value = Integer.parseInt(raw);
            if (value <= 0) {
                return new ValidationResult(raw, null, "NOT_POSITIVE");
            }
            return new ValidationResult(raw, value, null);
        } catch (NumberFormatException ex) {
            return new ValidationResult(raw, null, "INVALID_INTEGER");
        }
    }

    public static void main(String[] args) {
        for (String raw : List.of("10", "bad", "-2", "8")) {
            ValidationResult result = parsePositive(raw);
            if (result.success()) {
                System.out.println("ok=" + result.value());
            } else {
                System.out.println("error=" + result.errorCode());
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ValidationResultDemo.java
java ValidationResultDemo
~~~

Kết quả:

~~~text
ok=10
error=INVALID_INTEGER
error=NOT_POSITIVE
ok=8
~~~

Bài toán này không yêu cầu một checked exception để caller chọn retry. Những giá trị không hợp lệ là dữ liệu đầu vào bình thường trong quy trình kiểm tra và được trình bày bằng mã ổn định. Trong ứng dụng sản xuất, record có thể cần constructor/factory để cưỡng chế bất biến “thành công XOR thất bại”.

**Không hiểu sai rằng Result luôn tốt hơn exception**. Nếu API phục hồi bằng exception một cách tự nhiên hoặc thất bại có tính bất thường, dùng exception giúp không làm phức tạp đường thành công. Quyết định phụ thuộc cả tần suất lỗi và nhu cầu của caller.

## 14. Retry không phải cứ gặp ngoại lệ là thử lại

Một số checked exception phản ánh môi trường và **có thể** tạm thời, nhưng không phải mọi lỗi cùng kiểu đều nên retry.

Ví dụ, `IOException` có thể do mạng ngắt quãng, file bị thiếu vĩnh viễn, quyền đọc bị từ chối hoặc dữ liệu bị hỏng. Chỉ tên lớp không đủ để kết luận retry là an toàn.

Trước khi retry, cần hỏi:

- **Lỗi có khả năng tạm thời không?** Lỗi kết nối khác với file không tồn tại vĩnh viễn.
- **Thao tác có idempotent không?** Retry lệnh thanh toán sau timeout có thể tạo giao dịch trùng nếu server đã xử lý yêu cầu trước khi kết nối bị mất.
- **Có giới hạn lượt và thời gian không?** Không retry vô hạn.
- **Có backoff/jitter không?** Tùy hệ thống, tránh tạo áp lực đồng thời cho dịch vụ đang lỗi.
- **Có tín hiệu hủy/interrupt không?** Phải dừng khi bị yêu cầu.
- **Có điều kiện chuyển sang fallback hoặc báo lỗi cuối cùng không?**

### Ví dụ 9: retry có giới hạn, chỉ với lỗi I/O minh họa

Lưu thành `RetryPolicyDemo.java`:

~~~java
import java.io.IOException;

public class RetryPolicyDemo {
    private static int calls;

    static String readRemote() throws IOException {
        calls++;
        if (calls == 1) {
            throw new IOException("temporary outage");
        }
        return "READY";
    }

    static String retryAtMostThreeTimes() throws IOException {
        IOException last = null;

        for (int attempt = 1; attempt <= 3; attempt++) {
            try {
                return readRemote();
            } catch (IOException ex) {
                last = ex;
                System.out.println("retry-after=" + attempt);
            }
        }

        throw last;
    }

    public static void main(String[] args) {
        try {
            System.out.println("result=" + retryAtMostThreeTimes());
            System.out.println("calls=" + calls);
        } catch (IOException ex) {
            System.out.println("failed=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 RetryPolicyDemo.java
java RetryPolicyDemo
~~~

Kết quả:

~~~text
retry-after=1
result=READY
calls=2
~~~

Ví dụ cố ý không sleep để stdout xác định, chỉ minh họa một hành động phục hồi có giới hạn. Nó **không phải** policy retry dùng ngay cho hệ thống phân tán. Trong sản xuất nên phân loại lỗi tạm thời, backoff, idempotency, cancellation, time budget và khả năng giao dịch đã hoàn tất nhưng phản hồi bị mất.

Khi exhaustion xảy ra, ví dụ ném lại `IOException` cuối cùng. Caller vẫn nhìn thấy thất bại thực sự; code không âm thầm trả giá trị giả.

## 15. Giữ cause và suppressed exceptions khi chuyển loại lỗi

Một ngoại lệ có thể chứa:

- `getMessage()`: thông tin lỗi ở tầng hiện tại.
- `getCause()`: ngoại lệ trước đó đã gây ra lỗi hiện tại.
- `getStackTrace()`: các frame liên quan đến điểm Throwable được ghi stack trace.
- `getSuppressed()`: các lỗi phụ, thường phát sinh khi đóng tài nguyên trong try-with-resources.

Khi bọc một checked exception thành checked hoặc unchecked domain exception bằng `super(message, cause)`, JVM **giữ tham chiếu đến cause**, không tự sao chép danh sách suppressed sang wrapper. Lỗi phụ vẫn có thể được truy qua cause.

### Ví dụ 10: lỗi đọc là primary, lỗi đóng là suppressed

Lưu thành `SuppressedDomainDemo.java`:

~~~java
import java.io.IOException;

public class SuppressedDomainDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    static class ImportFailure extends Exception {
        ImportFailure(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static void repository() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("read failed");
        }
    }

    static void service() throws ImportFailure {
        try {
            repository();
        } catch (IOException ex) {
            throw new ImportFailure("Import unavailable", ex);
        }
    }

    public static void main(String[] args) {
        try {
            service();
        } catch (ImportFailure ex) {
            Throwable root = ex.getCause();
            System.out.println("domain=" + ex.getMessage());
            System.out.println("cause=" + root.getMessage());
            System.out.println("causeSuppressed="
                    + root.getSuppressed()[0].getMessage());
            System.out.println("wrapperSuppressed="
                    + ex.getSuppressed().length);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SuppressedDomainDemo.java
java SuppressedDomainDemo
~~~

Kết quả:

~~~text
domain=Import unavailable
cause=read failed
causeSuppressed=close failed
wrapperSuppressed=0
~~~

Điểm quan trọng: **dịch ngoại lệ có cause** không làm mất lỗi đóng tài nguyên của đối tượng IOException; nó vẫn nằm trong `root.getSuppressed()`. Nhưng wrapper mới không tự có suppressed tương tự. Khi log, nên truyền **đối tượng Throwable** cho logger để hiển thị cause chain/suppressed thay vì chỉ lấy `getMessage()` rồi bỏ phần còn lại.

## 16. `InterruptedException` không nên bọc/nuốt như lỗi thông thường

`InterruptedException` là checked exception đặc biệt thường báo một thao tác blocking đã bị yêu cầu ngắt. Nhiều phương thức như `Thread.sleep` có thể **xóa cờ interrupt khi ném InterruptedException**.

Khi bị ngắt:

- Nếu chữ ký cho phép, **truyền `InterruptedException` lên tầng có quyền quyết định hủy tác vụ**.
- Nếu API (ví dụ `Runnable.run()`) không thể khai báo checked exception này, thường nên **khôi phục cờ interrupt** bằng `Thread.currentThread().interrupt()` rồi kết thúc hoặc chuyển theo policy hủy.
- Không chỉ log và tiếp tục thao tác dài như thể chưa nhận tín hiệu, trừ khi có lý do và contract rõ.
- Không bọc `InterruptedException` thành `UncheckedIOException`: không đúng loại và sai ý nghĩa lỗi.

### Ví dụ 11: bảo toàn trạng thái gián đoạn

Lưu thành `InterruptContractDemo.java`:

~~~java
public class InterruptContractDemo {
    static void runTask() {
        Thread.currentThread().interrupt();

        try {
            Thread.sleep(1);
            System.out.println("unexpected");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            System.out.println("restored="
                    + Thread.currentThread().isInterrupted());
        }
    }

    public static void main(String[] args) {
        runTask();
    }
}
~~~

~~~bash
javac -encoding UTF-8 InterruptContractDemo.java
java InterruptContractDemo
~~~

Kết quả:

~~~text
restored=true
~~~

Vì cờ interrupt được đặt ngay trước khi gọi sleep, lời gọi phát hiện gián đoạn và ném InterruptedException. Trong catch, chương trình đặt lại cờ, bảo toàn tín hiệu cho logic phía ngoài. Đoạn demo kết thúc ngay sau đó; một tác vụ thật nên có chính sách dừng, cleanup và báo trạng thái bị hủy.

Việc InterruptException là checked **không làm nó tự động có thể phục hồi bằng retry**. Ý nghĩa hợp đồng của nó thường là phối hợp hủy/dừng tác vụ.

## 17. Checked exception và API bất đồng bộ

Các API bất đồng bộ có ranh giới ngoại lệ khác với lời gọi trực tiếp. Ví dụ `CompletableFuture.supplyAsync` nhận `Supplier<T>` không khai báo checked exception. Nếu tác vụ có thể ném IOException, lambda thường phải bắt và bọc lỗi thành unchecked; caller quan sát thất bại qua `join()` hoặc `get()`.

Các loại đáng nhớ:

- `CompletionException`: unchecked wrapper thường được thấy khi `CompletableFuture.join()` thất bại.
- `ExecutionException`: checked wrapper thường được thấy khi gọi `Future.get()`.
- `InterruptedException`: có thể phát sinh khi thread đang chờ `Future.get()` bị ngắt.
- `CancellationException`: unchecked, thể hiện tác vụ đã bị hủy trong nhiều API.
- Một checked exception do code chạy bên trong task ném có thể được **bọc lại**, nên không suy ra caller của join/get sẽ thấy trực tiếp đúng loại ngoại lệ gốc.

### Ví dụ 12: cause chain qua CompletableFuture

Lưu thành `AsyncFailureDemo.java`:

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public class AsyncFailureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> future =
                CompletableFuture.supplyAsync(() -> {
                    try {
                        throw new IOException("storage down");
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    }
                });

        try {
            System.out.println(future.join());
        } catch (CompletionException ex) {
            System.out.println("outer="
                    + ex.getClass().getSimpleName());
            System.out.println("wrapper="
                    + ex.getCause().getClass().getSimpleName());
            System.out.println("root="
                    + ex.getCause().getCause().getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 AsyncFailureDemo.java
java AsyncFailureDemo
~~~

Kết quả:

~~~text
outer=CompletionException
wrapper=UncheckedIOException
root=storage down
~~~

Tầng gọi nhận một CompletionException và có thể duyệt cause chain. Đừng chỉ bắt IOException quanh `future.join()` rồi nghĩ đó là cách xử lý trực tiếp: IOException là checked và chữ ký join không khai báo nó.

Ví dụ dùng task thất bại xác định, không có tác vụ khác hoặc race về kết quả. Trong ứng dụng thật, cần xét executor, timeout, cancellation, trạng thái transaction và nơi log lỗi.

## 18. Ngoại lệ, transaction và nhất quán dữ liệu

Một caller “có thể catch” không đồng nghĩa nó **nên tiếp tục giao dịch**. Ví dụ, thao tác lưu đơn hàng gồm nhiều bước có thể thất bại ở bước cuối sau khi vài thay đổi đã xảy ra. Khi đó:

- Bắt lỗi để **rollback hoặc bù trừ** trước khi trả kết quả.
- Nếu không bảo đảm toàn vẹn, phải thông báo trạng thái không rõ ràng và đưa lỗi tới tầng điều phối.
- Tránh retry tự động một lệnh có side effect nếu không có **idempotency key** hoặc cơ chế chống trùng.
- Không nuốt SQLException rồi trả thành công giả; hệ thống có thể đã không lưu đúng dữ liệu.
- Nếu dùng framework transaction, hãy hiểu rõ **quy tắc rollback** của framework, vì checked/unchecked có thể được framework diễn giải khác nhau theo cấu hình. Đây là chính sách framework, **không phải quy tắc JLS**.

Một checked exception có thể cần được trả lên thay vì xử lý tại repository. Một unchecked exception có thể cần được chuyển thành mã phản hồi ổn định ở HTTP boundary. Quyết định thiết kế không nên chỉ dựa trên loại compiler yêu cầu, mà còn trên **quyền kiểm soát trạng thái và hành động sau thất bại**.

## 19. Nguyên tắc bảo vệ hợp đồng công khai khi chọn loại lỗi

Khi public API chọn checked hoặc unchecked, hãy giữ ranh giới có ý nghĩa với caller:

- **Tên và loại lỗi ổn định** giúp caller quyết định sửa input, fallback, retry hay dừng; đừng trả một `RuntimeException("failed")` chung cho mọi trường hợp.
- **Vi phạm tiền điều kiện** thường báo bằng `IllegalArgumentException`, `NullPointerException` hoặc một loại unchecked phù hợp. Đừng dùng `assert` có thể bị vô hiệu hóa để kiểm tra input công khai.
- **Không lộ phụ thuộc hạ tầng ngoài ý muốn.** Nếu thay JDBC bằng HTTP mà caller phải sửa hàng loạt `catch (SQLException)`, thiết kế abstraction có thể chưa ổn; chuyển nghĩa ở ranh giới sở hữu hợp đồng và giữ `cause`.
- **Không lạm dụng `Error` cho nghiệp vụ** và không tạo cây custom exceptions nhiều tầng nếu các lớp không khác nhau về hành động xử lý.
- **Xem xét tác động nâng cấp.** Thêm/bớt checked `throws`, đổi class exception hoặc chuyển checked sang unchecked có thể làm mã nguồn hoặc hành vi caller thay đổi, kể cả khi binary linkage vẫn hoạt động.
- **Tài liệu hóa và kiểm thử đúng kết cục.** Caller cần biết loại lỗi, tình huống phát sinh, hậu điều kiện trạng thái và khả năng retry, không chỉ tên class.

Bài về ranh giới phụ thuộc và bài tương thích khi đổi hợp đồng ngoại lệ phân tích sâu hai rủi ro cuối. Ở đây tiêu chí chọn checked/unchecked vẫn là **khả năng và trách nhiệm xử lý hợp lý của caller**.

## 20. Anti-pattern: ba cách khiến hợp đồng lỗi trở nên khó dùng

### A. “Mọi lỗi đều là RuntimeException vì dễ viết code”

~~~java
catch (java.io.IOException ex) {
    throw new RuntimeException("failed");
}
~~~

Đây là **mã minh họa không độc lập và có vấn đề**. Nó vừa dùng loại lỗi quá chung, vừa bỏ cause. Một caller không biết thao tác gì thất bại và không thể nhìn lại IOException gốc bằng getCause.

Sửa theo contract của tầng:

~~~java
catch (java.io.IOException ex) {
    throw new StorageFailure("Cannot load report", ex);
}
~~~

Đoạn sau giả định `StorageFailure(String, Throwable)` đã khai báo; có thể chọn extends RuntimeException nếu tầng này thực sự muốn unchecked domain failure.

### B. “Mọi lỗi đều checked vì có thể xảy ra”

Đừng khai báo `throws Exception` trên mọi public method chỉ để “tài liệu hóa khả năng lỗi”. Điều đó làm caller khó phân biệt lỗi đầu vào, lỗi có thể retry và lỗi programmer. Unchecked exceptions vẫn tồn tại ngoài danh sách throws.

Hãy công bố **những loại checked mà caller được kỳ vọng xử lý**, và tài liệu hóa các unchecked quan trọng nếu caller cần biết. Không cố liệt kê mọi RuntimeException có thể phát sinh từ JDK.

### C. “Đã catch là xem như thành công”

~~~java
try {
    saveOrder();
} catch (Exception ex) {
    System.out.println("cannot save");
}
return true;
~~~

Đây là **mã minh họa sai chính sách**: nếu thao tác lưu thất bại, việc trả thành công giả có thể gây lỗi dữ liệu nghiêm trọng. Catch không tự tạo rollback, retry hoặc trạng thái thành công.

Sửa bằng **chính sách rõ ràng**: rollback rồi trả thất bại, chuyển exception có cause, hoặc fallback có tính đúng đắn; không dùng log như một cách thay thế xử lý lỗi.

## 21. Quy trình quyết định checked hay unchecked

Khi thiết kế một phương thức public, có thể dùng quy trình sau:

1. **Xác định thao tác và caller mục tiêu.** Ai gọi API: người dùng tương tác, service nội bộ, callback, batch job hay thư viện bên ngoài?
2. **Liệt kê các nhóm thất bại có ý nghĩa.** Lỗi đầu vào, trạng thái, tài nguyên không có, lỗi kết nối, timeout, hủy, dữ liệu không hợp lệ, invariant nội bộ.
3. **Gắn hành động mong đợi cho từng nhóm.** Sửa input, thử lại, fallback, rollback, bỏ qua có ghi nhận, dừng, cảnh báo vận hành hay sửa bug.
4. **Phân biệt expected outcome với exceptional failure.** Nếu “không có kết quả” là đường đi bình thường, có thể dùng `Optional` hoặc `Result`. Nếu caller cần bị buộc xem xét, checked exception có thể hữu ích.
5. **Đánh giá ngữ nghĩa lỗi.** Misuse/precondition thường unchecked; lỗi môi trường có khả năng xử lý thường đáng cân nhắc checked.
6. **Xem ràng buộc framework/API.** Functional interface, reactive/async API, interface overrides và code client ảnh hưởng hợp đồng khả thi.
7. **Chọn tên và hệ phân cấp ổn định.** Tránh loại `Exception` quá rộng và phân cấp quá sâu không có chính sách khác biệt.
8. **Thiết kế message/cause/metadata.** Có constructor `(String, Throwable)` khi dịch; bổ sung error code hoặc field khi caller cần xử lý theo cấu trúc.
9. **Quyết định nơi xử lý.** Tầng nhận lỗi có quyền làm gì? Nếu không thể xử lý, truyền lên thay vì catch rỗng.
10. **Xem tác dụng phụ và retry.** Bảo đảm idempotency, transaction, backoff, cancellation, resource cleanup nếu có.
11. **Viết test từ góc nhìn caller.** Thử đường thành công, từng loại thất bại, cause chain, rollback, retry và trường hợp không xử lý.
12. **Đánh giá tương thích khi thay đổi contract.** Nếu thư viện đã public, thêm/bỏ checked throws không chỉ là sửa nội bộ.

### Bảng quyết định ngắn

| Câu hỏi | Gợi ý |
| --- | --- |
| Caller **phải** có chính sách xử lý rõ? | Cân nhắc checked |
| Caller không có cách phục hồi hợp lý tại mọi điểm gọi? | Cân nhắc unchecked hoặc truyền lỗi tới boundary |
| Lỗi do dùng API sai/đầu vào không thỏa precondition? | Thường unchecked hoặc validation result |
| Lỗi là một kết quả nghiệp vụ thường xuyên? | Cân nhắc Result/Optional/status code |
| API đích không hỗ trợ checked throws? | Adapter/unchecked có cause hoặc interface riêng |
| Tầng service cần che chi tiết JDBC/file? | Dịch sang domain exception phù hợp, giữ cause |
| Lỗi phát sinh khi chờ bị interrupt? | Truyền hoặc restore interrupt, xử lý hủy |
| Lỗi có side effect một phần? | Rollback/bù trừ trước khi coi phục hồi |
| Thay đổi public signature tác động nhiều caller? | Xem tương thích nguồn và lộ trình migrate |

## 22. Câu hỏi tự kiểm tra

**1.** Checked exception có nghĩa caller đã phục hồi thành công chưa?  
**Chưa.** Compiler chỉ buộc `catch` hoặc `throws`; phục hồi phụ thuộc logic ứng dụng.

**2.** RuntimeException có thể bắt và xử lý không?  
**Có.** Unchecked nghĩa là không bắt buộc ở compile time, không phải “không thể catch”.

**3.** Lỗi nhập tham số âm vào API chỉ nhận số dương nên thường dùng loại nào?  
`IllegalArgumentException` unchecked hoặc một validation result theo hợp đồng.

**4.** IOException luôn bắt buộc được bọc thành checked domain exception không?  
**Không.** Tùy tầng và policy, có thể truyền IOException, bọc checked domain, bọc unchecked domain hoặc phục hồi.

**5.** Vì sao chỉ viết `new RuntimeException(ex.getMessage())` khi bọc lỗi là kém?  
Vì mất tham chiếu cause, loại lỗi gốc, stack trace và các suppressed exceptions đi kèm.

**6.** Nếu method trong interface không khai báo checked exception, implementation được thêm `throws IOException` không?  
**Không** khi IOException không được phép bởi hợp đồng override.

**7.** Một public API có thể khai báo `throws RuntimeException` không?  
**Có**, nhưng compiler không buộc caller catch/specify theo đó.

**8.** Vì sao thêm một checked exception vào API public có thể phá code client?  
Vì các caller trước đây chưa catch hoặc throws loại lỗi mới có thể không biên dịch.

**9.** Khi một kết quả “không tìm thấy” diễn ra thường xuyên và được dự kiến, có buộc phải tạo exception không?  
**Không.** Có thể chọn Optional/Result nếu phù hợp hợp đồng.

**10.** Có nên retry mọi IOException không?  
**Không.** Cần đánh giá lỗi tạm thời, idempotency, giới hạn lượt, backoff và cancellation.

**11.** Khi catch InterruptedException trong Runnable, làm thế nào để không làm mất tín hiệu?  
Thường khôi phục cờ bằng `Thread.currentThread().interrupt()` và kết thúc/hủy theo policy.

**12.** Checked exception của task async sẽ luôn thoát trực tiếp từ CompletableFuture.join() dưới cùng kiểu không?  
**Không.** Task có thể bọc lỗi và join thường báo CompletionException; phải xem cause chain.

**13.** Một wrapper mới có tự copy suppressed exceptions từ cause không?  
**Không.** Suppressed của cause vẫn thuộc đối tượng cause, có thể đọc qua getCause().getSuppressed().

**14.** Catch Exception rồi log có phải luôn là recovery không?  
**Không.** Nó có thể chỉ là ghi nhận; cần quyết định trả thất bại, retry, rollback, fallback hoặc truyền lỗi.

**15.** Vì sao “mọi lỗi từ bên ngoài checked, mọi lỗi từ code unchecked” không hoàn toàn chính xác?  
Vì policy API còn phụ thuộc quyền phục hồi, khả năng caller, framework, ranh giới tầng và mức ổn định hợp đồng; cùng lỗi I/O có thể xuất hiện dưới cả IOException và UncheckedIOException.

## 23. Tài liệu tham khảo chuẩn

- [JLS Java SE 21 — §11.1.1: The Kinds of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.1.1) — phân loại checked và unchecked.
- [JLS 21 — §11.2: Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2) — nghĩa vụ catch-or-specify và hợp đồng.
- [JLS 21 — §8.4.6: Method Throws](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.6) — khai báo throws.
- [JLS 21 — §8.4.8.3: Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.8.3) — giới hạn checked exceptions khi override.
- [Oracle Java Tutorials — Unchecked Exceptions: The Controversy](https://docs.oracle.com/javase/tutorial/essential/exceptions/runtime.html) — hướng dẫn chọn theo khả năng phục hồi; tài liệu mang tính hướng dẫn, không thay JLS.
- [Oracle Java Tutorials — The Catch or Specify Requirement](https://docs.oracle.com/javase/tutorial/essential/exceptions/catchOrDeclare.html).
- [Java SE 21 — Throwable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html) — cause, suppressed, stack trace.
- [Java SE 21 — IOException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/IOException.html).
- [Java SE 21 — UncheckedIOException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/UncheckedIOException.html).
- [Java SE 21 — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

**Ghi nhớ:** Quyết định checked hay unchecked là thiết kế **hợp đồng xử lý lỗi**. Checked yêu cầu caller cân nhắc lỗi ở compile time; unchecked không tạo nghĩa vụ đó nhưng vẫn có thể cần xử lý tại boundary. Hãy xuất phát từ người gọi có thể làm gì khi thất bại, giữ nguyên nhân kỹ thuật khi dịch loại lỗi, tránh bắt rộng/nuốt lỗi và kiểm thử cả đường phục hồi lẫn đường thất bại không thể phục hồi.
