# Không để chi tiết thư viện phụ thuộc trở thành hợp đồng công khai ngoài ý muốn

Khi một API Java gọi thư viện phân tích dữ liệu, HTTP client, JDBC driver hoặc SDK bên ngoài, thư viện đó có thể ném những exception rất cụ thể. Nếu các kiểu exception, mã lỗi, thông điệp hay cách xử lý nội bộ ấy tràn qua ranh giới API, người dùng API sẽ vô tình phụ thuộc vào một thư viện mà họ không trực tiếp lựa chọn. Việc thay thư viện hoặc nâng phiên bản về sau có thể trở thành thay đổi phá vỡ hợp đồng.

Mục tiêu là **công khai ý nghĩa lỗi ổn định ở mức chức năng**, giữ chi tiết phụ thuộc trong phần triển khai và vẫn bảo toàn thông tin cần thiết để chẩn đoán. Đây là quyết định thiết kế exception của Java; không nhất thiết phải tạo một lớp bọc cho mọi exception.

## 1. Khi nào exception trở thành một phần hợp đồng API?

Hợp đồng của một phương thức không chỉ gồm tên, tham số và kiểu trả về. Người gọi còn cần biết:

- Thao tác có thể thất bại trong những tình huống nào: dữ liệu không hợp lệ, tài nguyên không tồn tại, truy cập bị từ chối, dịch vụ tạm thời không sẵn sàng...
- Lỗi nào người gọi có thể **xử lý có chủ đích** (sửa đầu vào, thử lại, hiển thị thông báo, hủy giao dịch)?
- Dấu hiệu ổn định để phân loại lỗi: kiểu exception công khai, mã lỗi/enum, hoặc một hợp đồng kết quả được tài liệu hóa.
- Các bảo đảm sau lỗi: thao tác có làm thay đổi trạng thái không, có an toàn khi thử lại không, dữ liệu có thể đã được ghi một phần không?

Ví dụ về chữ ký **minh họa, chưa phải chương trình Java hoàn chỉnh**:

```java
// API vô tình buộc client biết thư viện parser.
public Report importReport(String input) throws VendorParseException;
```

Nếu `VendorParseException` là checked exception được khai báo trong `throws`, mã gọi phải bắt hoặc khai báo tiếp nó; client có thể phải mang dependency chứa kiểu đó để biên dịch. Ngay cả khi exception là unchecked (không bắt buộc xuất hiện trong `throws`), nó vẫn tạo phụ thuộc ngầm nếu người dùng bắt cụ thể, kiểm tra bằng `instanceof` hoặc dựa vào tên lớp/thông điệp để quyết định.

Một kiểu `IOException` công khai **không tự động là thiết kế sai**: đây là abstraction phổ biến của JDK và có thể đúng hợp đồng của API thao tác I/O. Vấn đề là API làm lộ một **chi tiết triển khai không có chủ đích**.

## 2. Những con đường làm rò rỉ dependency

| Điểm rò rỉ | Ví dụ | Hậu quả |
| --- | --- | --- |
| Chữ ký checked exception | `throws VendorParseException` | Client bị ràng buộc với kiểu của dependency lúc biên dịch. |
| Unchecked exception không được chuyển nghĩa | Vendor SDK ném `VendorTimeoutException` đi xuyên qua API | Client có thể dựa vào lớp/vendor để phân loại lỗi. |
| Kiểu public chứa class phụ thuộc | `VendorError getLastError()` | Kiểu trả về cũng trở thành hợp đồng, kể cả khi `throws` sạch. |
| Mã lỗi hoặc message nội bộ | So khớp chuỗi `"VND-1042"` hoặc `getMessage()` | Nâng phiên bản, đổi ngôn ngữ hoặc đổi thư viện có thể làm hỏng logic. |
| Tài liệu, ví dụ, bài kiểm thử client | Hướng dẫn `catch (VendorXException e)` | Một hành vi ban đầu “vô tình” có thể được cộng đồng xem là bảo đảm tương thích. |
| Serialization của lỗi | Đưa nguyên tên lớp, stack trace hoặc `cause` ra JSON trả cho client | Lộ cấu trúc nội bộ, phụ thuộc và đôi khi thông tin nhạy cảm. |

`getCause()` hữu ích cho việc chẩn đoán, nhưng **không nên hứa rằng lớp cause từ vendor sẽ ổn định**. Nếu framework tự serialize toàn bộ throwable, cần kiểm soát rõ dữ liệu trả ra; chỉ “bọc” exception mà vẫn trả toàn bộ stack trace cho bên ngoài chưa tạo được ranh giới thông tin.

## 3. Thiết kế ranh giới lỗi có chủ đích

Đặt một lớp chuyển đổi lỗi tại nơi hệ thống giao tiếp với dependency: adapter, repository, gateway hoặc implementation của service. Chuyển **ngữ nghĩa** của lỗi, không chỉ đổi tên class.

1. **Liệt kê hành vi mà người gọi cần phân biệt.** Ví dụ `INVALID_FORMAT` (sửa dữ liệu), `RESOURCE_NOT_FOUND` (chọn tài nguyên khác), `TEMPORARY_UNAVAILABLE` (cân nhắc retry). Chỉ tách lỗi nếu người gọi cần hành động khác nhau.
2. **Chọn hợp đồng lỗi thuộc quyền sở hữu API.** Với Java, thường là exception chuyên biệt của miền nghiệp vụ, kèm enum/mã lỗi ổn định. Giữ loại lỗi đủ cụ thể để xử lý, tránh một `RuntimeException` mơ hồ cho mọi trường hợp.
3. **Bắt loại lỗi cụ thể gần điểm gọi thư viện.** Chuyển `VendorParseException` thành lỗi định dạng của API, `VendorTimeoutException` thành lỗi tạm thời, v.v. Tránh `catch (Exception)` rồi gán tất cả là lỗi đầu vào.
4. **Giữ nguyên nhân gốc để điều tra.** Truyền exception đã bắt vào constructor `super(message, cause)`, hoặc cơ chế `initCause` nếu có lý do phù hợp. Đừng ghép toàn bộ stack trace vào message.
5. **Tách thông điệp công khai khỏi thông tin chẩn đoán.** Thông điệp hướng người dùng cần ổn định, an toàn; log nội bộ mới chứa ngữ cảnh vận hành và cause. Không log cùng stack trace nhiều lần ở mọi lớp.
6. **Tài liệu hóa hành vi ổn định.** Nêu exception công khai, mã lỗi, điều kiện phát sinh, khả năng retry và trạng thái sau thất bại. Không hứa hành vi của vendor nếu không kiểm soát được.

Luồng thông thường:

```text
Client
  → API / Service công khai
      → Adapter của dependency
          → Thư viện bên ngoài ném VendorParseException
      ← Adapter bắt lỗi và chuyển thành ReportImportException(INVALID_FORMAT)
  ← Client xử lý theo mã lỗi của API
```

Không cần dịch tất cả exception: lỗi lập trình như `NullPointerException` do bug nội bộ nên được sửa, ghi nhận đúng nguyên nhân, thay vì ngụy trang thành “dữ liệu người dùng sai”.

## 4. Ví dụ Java 17 chạy độc lập: bọc lỗi và giữ cause

Giả sử một thư viện parser có thể ném `VendorParseException`. API nhập báo cáo công khai `ReportImportException` và mã `ReportError` do chính API sở hữu. Để ví dụ chạy độc lập không cần tải dependency, `VendorParser` bên dưới là **thư viện giả lập nội bộ**.

Tạo tệp `DependencyBoundaryDemo.java`:

```java
public class DependencyBoundaryDemo {

    // Phần public là hợp đồng lỗi mà client được phép dựa vào.
    public enum ReportError {
        INVALID_FORMAT,
        TEMPORARY_UNAVAILABLE
    }

    public static final class ReportImportException extends RuntimeException {
        private final ReportError code;

        public ReportImportException(
                ReportError code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        public ReportError code() {
            return code;
        }
    }

    public static final class ReportService {
        private final VendorParser parser = new VendorParser();

        /**
         * @throws ReportImportException khi dữ liệu không thể nhập.
         */
        public int importReport(String text) {
            try {
                return parser.parseTotal(text);
            } catch (VendorParseException cause) {
                throw new ReportImportException(
                    ReportError.INVALID_FORMAT,
                    "Dữ liệu báo cáo không hợp lệ",
                    cause
                );
            }
        }
    }

    // Mô phỏng dependency: các lớp vendor KHÔNG xuất hiện
    // trong chữ ký public hoặc mã lỗi public của ReportService.
    private static final class VendorParser {
        int parseTotal(String text) {
            int separator = text.indexOf('=');
            if (separator < 0) {
                throw new VendorParseException("Missing '='");
            }
            try {
                return Integer.parseInt(text.substring(separator + 1));
            } catch (NumberFormatException cause) {
                throw new VendorParseException("Invalid integer", cause);
            }
        }
    }

    private static final class VendorParseException extends RuntimeException {
        VendorParseException(String message) {
            super(message);
        }

        VendorParseException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    public static void main(String[] args) {
        ReportService service = new ReportService();
        try {
            service.importReport("total=?");
        } catch (ReportImportException ex) {
            System.out.println(ex.code());
            System.out.println(ex.getMessage());
            System.out.println(ex.getCause() != null);
        }
    }
}
```

Biên dịch và chạy:

```bash
javac DependencyBoundaryDemo.java
java DependencyBoundaryDemo
```

Kết quả chuẩn:

```text
INVALID_FORMAT
Dữ liệu báo cáo không hợp lệ
true
```

Giải thích:

- `Integer.parseInt("?")` ném `NumberFormatException`, parser giả lập chuyển thành `VendorParseException`.
- `ReportService.importReport` bắt đúng lỗi của dependency và ném `ReportImportException` với `ReportError.INVALID_FORMAT`.
- Người gọi chỉ cần xử lý `ReportImportException` và `code()`. Việc thay `VendorParser` bằng parser khác không nhất thiết làm thay đổi hợp đồng API.
- `super(message, cause)` giữ chuỗi nguyên nhân để chẩn đoán; `getCause() != null` cho thấy thông tin này còn đó. Client **không nên kiểm tra kiểu cause vendor** như điều kiện nghiệp vụ.
- Trong thư viện thực, có thể tách các kiểu công khai thành những tệp riêng (`ReportService.java`, `ReportImportException.java`, `ReportError.java`) và đặt adapter vendor trong package nội bộ. Ví dụ dùng nested classes để chỉ cần một tệp tự chạy.

`TEMPORARY_UNAVAILABLE` mới được khai báo như một mã có thể mở rộng; ví dụ **chưa mô phỏng lỗi mạng** và không tự nhận đã xử lý timeout/retry.

## 5. Checked exception hay unchecked exception?

Cả hai đều có thể tạo ra hợp đồng tốt hoặc tạo ràng buộc ngoài ý muốn.

| Lựa chọn | Phù hợp khi | Lưu ý |
| --- | --- | --- |
| Checked exception ổn định của API | Caller được kỳ vọng phải quyết định cách phục hồi và compiler cần nhắc xử lý; ví dụ API đọc tệp công khai `IOException` hoặc API miền nghiệp vụ có `ImportFailedException` checked | `throws` là một phần chữ ký Java; thêm hoặc đổi checked exception có tác động đến mã nguồn client. |
| Unchecked exception ổn định của API | Không phải mọi caller đều có cách phục hồi hữu ích, hoặc caller xử lý lỗi tại boundary cao hơn | Vẫn tài liệu hóa loại lỗi/mã lỗi và hành vi; “unchecked” không đồng nghĩa với “không có hợp đồng”. |
| Đối tượng kết quả có phân nhánh lỗi | Lỗi là kết quả dự kiến, thường xuyên và quy trình nghiệp vụ cần buộc caller xét đủ các trường hợp | Không thay thế việc ném exception cho bug hoặc hỏng hạ tầng không mong đợi. |

Không nhất thiết biến mọi `IOException` thành một exception tự đặt tên. Với thư viện đọc stream, `IOException` có thể là chính abstraction ổn định; khi dùng SDK chuyên biệt để tải một tài liệu theo ID, một mã lỗi như `DOCUMENT_NOT_FOUND` hoặc `TEMPORARY_UNAVAILABLE` lại có thể giúp client hơn.

Đừng khai báo `throws Exception` chỉ để tránh chọn lỗi phù hợp. Nó làm API kém rõ ràng mà vẫn không bảo đảm tránh phụ thuộc; `throws` cũng không kiểm soát tất cả unchecked exception.

## 6. Bảng chuyển nghĩa dựa trên hành động của caller

Ví dụ bảng thiết kế **minh họa** cho một API nhập tài liệu; tên các exception vendor chỉ là ký hiệu mẫu:

| Nguyên nhân trong adapter | Exception/mã public có thể dùng | Người gọi nên làm gì? |
| --- | --- | --- |
| `VendorParseException` do nội dung sai cấu trúc | `INVALID_FORMAT` | Sửa tệp/đầu vào; retry nguyên xi thường vô ích. |
| `VendorNotFoundException` | `RESOURCE_NOT_FOUND` | Kiểm tra ID hoặc chọn tài nguyên khác. |
| `VendorTimeoutException` do timeout tạm thời | `TEMPORARY_UNAVAILABLE` | Retry có giới hạn, backoff nếu thao tác an toàn để lặp. |
| `VendorAuthenticationException` do cấu hình credentials của server | `INTERNAL_INTEGRATION_ERROR` hoặc một hợp đồng phù hợp | Thông báo lỗi vận hành; không gán nhầm là lỗi nhập liệu của người dùng. |
| `IllegalArgumentException` do API phát hiện tham số caller không hợp lệ | Có thể giữ `IllegalArgumentException` của JDK hoặc công khai lỗi đầu vào riêng | Sửa cách gọi API. |
| Bug, invariant hỏng, `NullPointerException` ngoài ý muốn | Thông thường để cơ chế xử lý lỗi nội bộ ghi nhận | Sửa code; không cố “dịch” thành lỗi nghiệp vụ bình thường. |

Phân loại dựa vào **ý nghĩa thực tế**, không dựa duy nhất vào tên exception. Chẳng hạn cùng một `IOException` có thể có nguyên nhân khác nhau; không thể mặc định mọi `IOException` đều an toàn để thử lại.

### Đặt exception ở lớp nào?

Một adapter hướng SDK có thể bắt kiểu vendor và dịch sang một exception kỹ thuật ổn định của ứng dụng. Service nghiệp vụ có thể tiếp tục dịch sang lỗi miền nghiệp vụ khi ngữ cảnh đủ rõ. Tuy nhiên, tránh bọc lồng nhiều lớp vô ích:

```text
VendorTimeoutException
  → PaymentGatewayUnavailableException
  → CheckoutTemporarilyUnavailableException
```

Hai lần dịch chỉ hợp lý nếu mỗi lớp bổ sung ý nghĩa khác nhau cho **người tiêu dùng của chính lớp đó**. Nếu service chỉ catch rồi đổi tên mà không bổ sung ngữ nghĩa, bớt một lớp bọc sẽ rõ và dễ truy vết hơn.

## 7. Các tình huống đặc biệt cần giữ đúng ngữ nghĩa

**Ngắt luồng và hủy tác vụ.** Nếu adapter bắt `InterruptedException`, thông thường cần khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` trước khi chuyển/thoát, trừ khi API chủ ý truyền tiếp `InterruptedException`. Không biến một tín hiệu hủy thành lỗi để retry vô hạn. `CancellationException` cũng nên được xử lý theo chính sách hủy của hệ thống. Đoạn sau là **mảnh minh họa**, giả định có kiểu `TaskAbortedException` do API định nghĩa:

```java
try {
    blockingCall();
} catch (InterruptedException cause) {
    Thread.currentThread().interrupt();
    throw new TaskAbortedException("Tác vụ đã bị ngắt", cause);
}
```

**Lỗi nghiêm trọng và bug.** Không dùng `catch (Throwable)` để bọc tất cả, vì nó bắt cả `Error` như `OutOfMemoryError`. Không dùng `catch (RuntimeException)` bao trùm tùy tiện và đổi mọi lỗi thành `INVALID_FORMAT`; cách đó che bug và phá ý nghĩa lỗi.

**Đóng tài nguyên.** Với `try-with-resources`, lỗi xảy ra khi đóng tài nguyên có thể nằm trong `getSuppressed()` của exception chính. Nếu chuyển exception, giữ `cause` sẽ bảo toàn đường truy vết tới suppressed exceptions gốc; nếu bỏ cause, thông tin này có thể mất. Đừng chỉ ghi `cause.getMessage()` rồi ném exception mới không có cause.

**Giao dịch và ghi một phần.** Một exception “service unavailable” không tự bảo đảm rằng thao tác chưa thực hiện thành công ở phía dịch vụ. Với API ghi dữ liệu, cần tài liệu hóa idempotency, mã yêu cầu, khả năng ghi một phần và điều kiện retry. Bọc lỗi transport thành mã ổn định là chưa đủ để cho phép retry an toàn.

**Thông tin nhạy cảm.** Message vendor có thể chứa URL nội bộ, SQL, tên bảng, token hoặc dữ liệu người dùng. Không trực tiếp dùng `cause.getMessage()` làm thông điệp trả cho client. Giữ cause cho log được kiểm soát quyền truy cập; thông điệp public cần ít thông tin nhạy cảm và vẫn đủ để caller hành động.

## 8. Tương thích khi thay dependency

Giả sử phiên bản đầu dùng parser A, phiên bản sau chuyển sang parser B:

- **Trước:** client bắt `ParserAException` rồi đọc error code do A định nghĩa.
- **Sau, nếu không có ranh giới:** client phải đổi import, cập nhật `catch`, có thể phải hiểu hệ mã lỗi của B.
- **Sau, với hợp đồng có chủ đích:** service vẫn ném `ReportImportException` với `INVALID_FORMAT`; chỉ code adapter và ánh xạ lỗi thay đổi.

Tuy nhiên, **giữ nguyên tên exception chưa đủ**. Cần giữ cả ngữ nghĩa: input nào bị từ chối, lỗi được ưu tiên khi có nhiều nguyên nhân, error code nào được trả, retry có an toàn không. Thay parser có thể làm thay đổi tiêu chí hợp lệ của input; nếu điều đó thuộc hợp đồng, vẫn phải đánh giá tương thích và cập nhật test/tài liệu.

Nếu API cũ **đã công khai** exception từ vendor và người dùng đang dựa vào nó, việc loại bỏ ngay có thể phá mã nguồn hoặc hành vi runtime. Nên đánh giá mức độ sử dụng, chính sách versioning, kế hoạch deprecation/migration và kiểm thử tương thích. Không thể giả định rằng chỉ đổi checked exception sang unchecked là nâng cấp tương thích hoàn toàn.

## 9. Kiểm thử đúng ranh giới

Thiết kế test tập trung vào những điều API hứa, không cố đóng băng chi tiết thư viện:

1. Khi đầu vào có lỗi định dạng, assert **kiểu lỗi công khai**, `code() == INVALID_FORMAT` và thông điệp public an toàn. Không assert tên/vendor message từ `getCause()`.
2. Với lỗi phụ thuộc tạm thời, giả lập timeout ở adapter, kiểm tra mã public và chính sách retry/idempotency do API tuyên bố.
3. Với lỗi hạ tầng không xác định hoặc bug, xác nhận chúng không bị gán sai thành lỗi dữ liệu người dùng.
4. Với lỗi có cause, xác nhận cause được bảo toàn để chẩn đoán nội bộ; không coi **kiểu cause cụ thể** là API promise.
5. Nếu đổi thư viện, chạy lại bộ contract test độc lập với vendor trước khi xuất bản phiên bản mới.
6. Kiểm tra boundary xuất JSON/log để chắc không vô tình hiển thị stack trace, token, câu SQL hoặc tên class phụ thuộc cho client ngoài.

Tài liệu Javadoc của API nên mô tả **điều kiện và hành động**. Ví dụ cho phương thức trong bài:

```java
/**
 * Nhập tổng tiền từ nội dung báo cáo.
 *
 * @param text nội dung dạng "total=123"
 * @return giá trị tổng tiền
 * @throws ReportImportException nếu không thể phân tích nội dung;
 *         code() là INVALID_FORMAT khi định dạng sai
 */
public int importReport(String text) {
    // Triển khai trong ReportService ở ví dụ đầy đủ phía trên.
    throw new UnsupportedOperationException("Minh họa chữ ký/Javadoc");
}
```

Đoạn Javadoc trên **chỉ minh họa tài liệu hợp đồng**, không phải bản triển khai thay thế cho chương trình đã chạy; `UnsupportedOperationException` là placeholder minh họa cú pháp trong snippet này.

## 10. Những sai lầm thường gặp

- **Bọc mọi exception thành `RuntimeException("Failed")`:** mất ngữ nghĩa, mất hướng xử lý; nếu thiếu cause còn mất chẩn đoán.
- **Gọi `cause.getMessage()` là message công khai:** làm format nội bộ trở thành hợp đồng và có thể lộ dữ liệu nhạy cảm.
- **Bắt `Exception` ở mọi tầng:** che bug, che lỗi ngắt, sinh nhiều lớp wrapper và stack trace khó đọc.
- **Tưởng unchecked exception không ảnh hưởng API:** client vẫn có thể bắt hoặc kiểm tra chúng; cam kết tài liệu cũng tạo ràng buộc.
- **Phát minh quá nhiều class lỗi:** tăng độ phức tạp nếu caller không có hành động khác nhau. Enum/mã lỗi ổn định đôi khi đủ.
- **Quên semantics retry:** timeout không cho biết server đã xử lý yêu cầu hay chưa.
- **Test phụ thuộc vendor:** assert exact text, subtype vendor hay stack trace khiến test vỡ khi thay thư viện dù hành vi public đúng.

## 11. Tự kiểm tra thiết kế API

Trước khi công bố một phương thức mới hoặc nâng cấp dependency, tự trả lời:

1. Nếu ngày mai đổi thư viện, người gọi có phải import/catch class khác, đổi phép so chuỗi hay đổi logic business không?
2. Người dùng API dựa vào những **lỗi có ý nghĩa nào** để xử lý, và chúng được mô tả ở đâu?
3. Chuỗi cause và suppressed exceptions có còn cho chẩn đoán không, và việc hiển thị cho client có an toàn không?
4. Hợp đồng có nói rõ trạng thái sau lỗi, điều kiện retry và lỗi do caller hay do hạ tầng không?
5. Có test xác nhận hành vi public **không phụ thuộc parser/SDK cụ thể** không?

Nguyên tắc cần nhớ: **thiết kế exception theo điều mà client cần biết và có thể xử lý; giữ loại lỗi, mã lỗi và message của dependency trong phần triển khai, trừ khi cố ý chọn chúng làm hợp đồng.**