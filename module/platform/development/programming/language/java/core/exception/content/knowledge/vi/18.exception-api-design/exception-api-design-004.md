# Phân biệt lỗi tham số, lỗi trạng thái và lỗi từ phụ thuộc khi thiết kế API Java

## 1. Vì sao phải phân loại đúng lỗi?

Khi một phương thức Java thất bại, người gọi cần biết **mình truyền sai dữ liệu**, **đối tượng/hệ thống đang ở trạng thái không cho phép thao tác**, hay **một thành phần bên ngoài không thực hiện được công việc**. Ba nhóm này dẫn đến cách sửa và cách xử lý khác nhau:

- **Lỗi tham số (invalid argument):** Giá trị đầu vào vi phạm hợp đồng của phương thức. Người gọi thường cần sửa dữ liệu hoặc cách gọi.
- **Lỗi trạng thái (invalid state):** Tham số có thể hoàn toàn hợp lệ, nhưng trạng thái hiện tại của đối tượng hoặc tài nguyên không cho phép thao tác. Người gọi cần thay đổi trình tự thao tác hoặc bảo đảm điều kiện trạng thái.
- **Lỗi từ phụ thuộc (dependency failure):** Đầu vào và trạng thái phía API có thể hợp lệ, nhưng thao tác lên mạng, tệp, cơ sở dữ liệu, hệ thống khác hoặc thư viện phụ thuộc thất bại. Cần xử lý ở ranh giới tích hợp: chẩn đoán, thông báo, thử lại có điều kiện hoặc dự phòng.

Cách phân loại này mô tả **nguyên nhân và trách nhiệm khắc phục**, không phải ba nhánh cố định của cây kế thừa `Exception`. Ví dụ `IllegalArgumentException` và `IllegalStateException` đều là `RuntimeException`; lỗi phụ thuộc có thể xuất hiện dưới dạng ngoại lệ checked, unchecked hoặc ngoại lệ miền nghiệp vụ.

## 2. Bảng quyết định nhanh

| Tiêu chí | Lỗi tham số | Lỗi trạng thái | Lỗi từ phụ thuộc |
| --- | --- | --- | --- |
| Câu hỏi trọng tâm | “Giá trị người gọi đưa vào có đúng hợp đồng?” | “Lời gọi này có hợp lệ **lúc này**?” | “Một thành phần cần thiết có thực thi được?” |
| Nguyên nhân điển hình | Số âm khi yêu cầu số không âm; chuỗi sai định dạng; tham chiếu `null` bị cấm | Dùng dịch vụ sau khi đóng; gọi `commit()` trước `begin()`; đọc tài nguyên chưa khởi tạo | Mất kết nối, timeout, lỗi I/O, DB không sẵn sàng |
| Ngoại lệ Java thường gặp | `IllegalArgumentException`, `NullPointerException`, `IndexOutOfBoundsException` | `IllegalStateException`; đôi khi ngoại lệ trạng thái riêng của API | `IOException`, `SQLException`, `TimeoutException` hoặc loại `...UnavailableException` do API định nghĩa |
| Người gọi thường làm gì? | Sửa đối số; sửa logic gọi | Sửa trình tự hoặc vòng đời tài nguyên | Xem nguyên nhân, khôi phục kết nối, retry nếu an toàn, báo lỗi tạm thời |
| Có nên thử lại nguyên lời gọi ngay? | Thường không; phải sửa tham số | Thường không; phải thay đổi trạng thái trước | Chỉ khi lỗi tạm thời, thao tác an toàn để retry và có chính sách giới hạn |

**Nguyên tắc quan trọng:** Cùng một chuỗi đầu vào có thể dẫn đến nhiều loại lỗi ở các giai đoạn khác nhau. Một mã tiền tệ hợp lệ về cú pháp vẫn có thể không được nhà cung cấp dữ liệu hỗ trợ, hoặc nhà cung cấp có thể mất kết nối khi xử lý mã đó. Hãy phân loại dựa trên **hợp đồng API và nguyên nhân thực**, không chỉ theo thông báo hay tên lớp ngoại lệ.

## 3. Lỗi tham số: vi phạm tiền điều kiện của lời gọi

Tham số sai khi người gọi có thể xác định lỗi **từ hợp đồng công khai của phương thức và giá trị truyền vào**, không phụ thuộc trạng thái bên ngoài. Ví dụ:

- `transfer(amount)` yêu cầu `amount > 0` nhưng nhận `0` hoặc số âm.
- `parsePort(port)` yêu cầu cổng trong khoảng `1..65535` nhưng nhận `70000`.
- `findById(id)` yêu cầu `id` khác `null` nhưng nhận `null`.
- API yêu cầu chuỗi gồm ba chữ cái in hoa mà người gọi truyền chuỗi sai định dạng.

Chọn ngoại lệ:

- `IllegalArgumentException`: tham số không thỏa điều kiện giá trị/định dạng của API.
- `NullPointerException`: thường phù hợp khi tham số tham chiếu bị cấm `null`; `Objects.requireNonNull(value, "value")` là idiom của JDK. API cũng có thể chọn `IllegalArgumentException` cho chính sách riêng, nhưng cần nhất quán.
- `IndexOutOfBoundsException`: dành cho chỉ số vượt miền hợp lệ của một chuỗi, danh sách, mảng hoặc cấu trúc hỗ trợ truy cập theo chỉ số. Đây là trường hợp cụ thể hơn của `RuntimeException`.

Mẫu kiểm tra:

```java
Objects.requireNonNull(name, "name");
if (name.isBlank()) {
    throw new IllegalArgumentException("name must not be blank");
}
if (pageSize < 1 || pageSize > 100) {
    throw new IllegalArgumentException("pageSize must be between 1 and 100");
}
```

Đây là **đoạn mã đặt bên trong phương thức** đã khai báo biến `name` và `pageSize`, không phải chương trình độc lập. `Objects.requireNonNull` ném `NullPointerException` khi nhận `null`; `String.isBlank()` được hỗ trợ từ Java 11. Thông báo lỗi nên nói rõ tên tham số và quy tắc bị vi phạm nhưng tránh in dữ liệu nhạy cảm.

**Ranh giới cần nhớ:** “Không tìm thấy tài khoản theo ID” không mặc nhiên là đối số sai. ID có thể đúng định dạng, nhưng tài khoản không tồn tại: đó là trường hợp *resource not found* trong miền nghiệp vụ, thường có ngoại lệ hoặc giá trị kết quả riêng. Cũng không nên dùng `IllegalArgumentException` để che lỗi DB chỉ vì lời gọi DB có truyền một tham số.

## 4. Lỗi trạng thái: giá trị hợp lệ nhưng thao tác sai thời điểm

Lỗi trạng thái xuất hiện khi tiền điều kiện phụ thuộc vào **vòng đời, pha xử lý hoặc trạng thái hiện tại** của đối tượng/tài nguyên:

- Gọi `send()` sau `close()`.
- Gọi `commit()` khi chưa bắt đầu transaction.
- Gọi `next()` trên đối tượng đã bị đóng, nếu hợp đồng quy định không được dùng sau khi đóng.
- Gọi `start()` lần thứ hai trong khi bộ xử lý chỉ cho phép khởi động một lần.

`IllegalStateException` diễn đạt rằng **lời gọi không phù hợp với trạng thái của đối tượng hoặc ứng dụng**. Nó hữu ích cho API đồng bộ nội bộ và object lifecycle:

```java
if (closed) {
    throw new IllegalStateException("service is closed");
}
```

Đoạn này giả định có biến trạng thái `closed` trong lớp sở hữu thao tác.

Khác biệt quan trọng: một tham số hợp lệ không trở nên “sai tham số” chỉ vì đối tượng đã đóng. Trạng thái cũng không đồng nghĩa với “mọi lỗi xảy ra lúc chạy”; một DB bị timeout là lỗi phụ thuộc, dù xảy ra khi đối tượng Java đang ở trạng thái sử dụng bình thường.

Các API đã định nghĩa ngoại lệ chuyên biệt cần tuân thủ hợp đồng của chính chúng. Ví dụ `UnsupportedOperationException` thường thể hiện thao tác không được hỗ trợ, không nhất thiết là trạng thái tạm thời; đừng thay bằng `IllegalStateException` chỉ để thống nhất hình thức.

## 5. Lỗi từ phụ thuộc: hệ thống bên ngoài thất bại

“Phụ thuộc” là thứ phương thức cần gọi để hoàn thành công việc: HTTP client, database, file system, message broker, RPC service, thư viện/native service hoặc nguồn dữ liệu từ một module khác. Hãy phân biệt ba trường hợp:

1. **Không liên lạc được:** mất mạng, timeout, tên miền không phân giải, kết nối bị từ chối.
2. **Liên lạc được nhưng xử lý thất bại:** DB báo tạm quá tải, dịch vụ trả lỗi 5xx, file không thể đọc do I/O.
3. **Phụ thuộc trả dữ liệu/hành vi vi phạm hợp đồng tích hợp:** payload thiếu trường bắt buộc, phản hồi không thể phân tích, phiên bản schema không tương thích.

Trong Java, `IOException` là ngoại lệ checked điển hình khi thao tác I/O thất bại; `SQLException` có thể xuất hiện từ JDBC. Thư viện HTTP/DB cụ thể có thể dùng ngoại lệ unchecked, ngoại lệ theo danh mục transient/permanent hoặc exception wrapper; không có một lớp Java duy nhất bao quát mọi lỗi phụ thuộc.

**Không phải mọi lỗi do dependency ném ra đều thuộc nhóm dependency failure.** Ví dụ một HTTP service trả `400` vì người dùng nhập trường bị cấm có thể tương ứng với lỗi đầu vào của API công khai; lỗi `401` có thể do thông tin xác thực của ứng dụng tích hợp; phản hồi `404` có thể là đối tượng nghiệp vụ không tồn tại. Cần đối chiếu chính xác hợp đồng từng tầng và ai có khả năng sửa lỗi.

Với lỗi phụ thuộc, thiết kế hợp đồng nên cân nhắc:

- **Giữ nguyên loại gốc** khi caller cần phân biệt `IOException`, `SQLException`... và API muốn cho phép xử lý chi tiết.
- **Dùng ngoại lệ miền hoặc ranh giới** (ví dụ `RateProviderUnavailableException`) khi muốn tránh rò rỉ công nghệ nội bộ; luôn giữ `cause` gốc.
- **Phân biệt lỗi tạm thời và lâu dài** dựa trên dữ liệu đáng tin: timeout/kết nối mất có thể tạm thời; cấu hình sai hoặc thông tin xác thực hết hiệu lực thường đòi hỏi sửa cấu hình.
- **Giới hạn retry:** có số lần chờ tối đa, timeout hợp lý, backoff/jitter và kiểm tra tính idempotent của thao tác. Không tự động retry một thao tác thanh toán hoặc ghi dữ liệu không có cơ chế chống trùng.
- **Không tiết lộ bí mật:** log theo ngữ cảnh phù hợp, ẩn token, mật khẩu, payload riêng tư và chi tiết kết nối khi trả lỗi cho người dùng.

## 6. Ví dụ Java 17+: cùng một API, ba nguyên nhân lỗi

Chương trình dưới đây có **một lớp public, một file độc lập** và mô phỏng nhà cung cấp tỷ giá. Nó kiểm tra đối số trước, sau đó kiểm tra trạng thái dịch vụ, cuối cùng mới gọi phụ thuộc. Mã `EUR` cố ý tạo lỗi I/O giả lập để dễ thấy nhánh dependency.

Tạo file `ExceptionTaxonomyDemo.java`:

```java
import java.io.IOException;
import java.math.BigDecimal;
import java.util.Objects;

public class ExceptionTaxonomyDemo {
    @FunctionalInterface
    interface RateProvider {
        BigDecimal rateOf(String currency) throws IOException;
    }

    static final class QuoteService {
        private final RateProvider provider;
        private boolean closed;

        QuoteService(RateProvider provider) {
            this.provider = Objects.requireNonNull(provider, "provider");
        }

        BigDecimal quote(BigDecimal amount, String currency) throws IOException {
            Objects.requireNonNull(amount, "amount");
            Objects.requireNonNull(currency, "currency");
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("amount must be >= 0");
            }
            if (!currency.matches("[A-Z]{3}")) {
                throw new IllegalArgumentException("currency must have 3 uppercase letters");
            }
            if (closed) {
                throw new IllegalStateException("service is closed");
            }
            return amount.multiply(provider.rateOf(currency));
        }

        void close() {
            closed = true;
        }
    }

    public static void main(String[] args) throws IOException {
        QuoteService service = new QuoteService(currency -> {
            if ("EUR".equals(currency)) {
                throw new IOException("exchange-rate endpoint unavailable");
            }
            return new BigDecimal("25000");
        });

        System.out.println("OK: " + service.quote(new BigDecimal("2"), "VND"));

        try {
            service.quote(new BigDecimal("-1"), "VND");
        } catch (IllegalArgumentException ex) {
            System.out.println("PARAM: " + ex.getClass().getSimpleName());
        }

        try {
            service.quote(new BigDecimal("2"), "EUR");
        } catch (IOException ex) {
            System.out.println("DEPENDENCY: " + ex.getClass().getSimpleName());
        }

        service.close();
        try {
            service.quote(new BigDecimal("2"), "VND");
        } catch (IllegalStateException ex) {
            System.out.println("STATE: " + ex.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file (JDK 17 hoặc mới hơn):

```bash
javac -encoding UTF-8 ExceptionTaxonomyDemo.java
java ExceptionTaxonomyDemo
```

```text
OK: 50000
PARAM: IllegalArgumentException
DEPENDENCY: IOException
STATE: IllegalStateException
```

Giải thích các nhánh:

1. `quote(2, "VND")`: số tiền và mã tiền tệ hợp lệ, dịch vụ mở, nhà cung cấp trả `25000` nên kết quả là `2 × 25000 = 50000`.
2. `quote(-1, "VND")`: số tiền vi phạm điều kiện `amount >= 0`, ném `IllegalArgumentException` **trước khi** gọi dependency.
3. `quote(2, "EUR")`: cả đầu vào và trạng thái đều hợp lệ, nhưng provider giả lập ném `IOException`. Đây là lỗi phụ thuộc, không phải lỗi tham số.
4. Sau `service.close()`, `quote(2, "VND")` ném `IllegalStateException`; tham số vẫn hợp lệ và provider không được gọi.

Ví dụ cố tình đơn giản: tỷ giá cố định chỉ phục vụ minh họa, biểu thức `[A-Z]{3}` kiểm tra **định dạng** chứ không chứng minh mã được ISO 4217 công nhận, `QuoteService` không hỗ trợ truy cập đồng thời và `close()` chỉ đổi cờ nội bộ (không triển khai `AutoCloseable`). Trong ứng dụng thật cần kiểm tra tính hợp lệ theo nghiệp vụ, quản lý tài nguyên và đồng bộ hóa phù hợp.

## 7. Thiết kế hợp đồng ngoại lệ cho phương thức public

Một API tốt cho caller biết những gì nó phải bảo đảm trước khi gọi, trạng thái cần thiết và loại thất bại bên ngoài có thể gặp. Ví dụ tài liệu `quote` tương ứng với chương trình trên:

```java
/**
 * Quy đổi amount theo tỷ giá do provider cung cấp.
 *
 * @param amount số tiền không âm; không được null
 * @param currency mã gồm đúng 3 chữ cái in hoa; không được null
 * @return số tiền sau quy đổi
 * @throws NullPointerException nếu amount hoặc currency là null
 * @throws IllegalArgumentException nếu amount âm hoặc currency sai định dạng
 * @throws IllegalStateException nếu service đã đóng
 * @throws IOException nếu rate provider bị lỗi I/O
 */
```

Đây là đoạn **Javadoc đặt ngay trước khai báo phương thức `quote`**, không phải file biên dịch độc lập. Ký hiệu `@throws` mô tả cả ngoại lệ unchecked; chỉ ngoại lệ checked như `IOException` cần có trong `throws` của chữ ký phương thức (trừ trường hợp xử lý ngay trong phương thức).

Khi chọn kiểu lỗi, tự hỏi:

1. Caller có thể phát hiện điều kiện sai chỉ từ giá trị của chính tham số và hợp đồng không? Nếu có, nhóm lỗi tham số.
2. Tham số vẫn hợp lệ nhưng tài nguyên/đối tượng đang ở pha không cho phép thao tác? Nhóm lỗi trạng thái.
3. Gọi tới hệ thống/đối tượng phụ thuộc và nó không hoàn thành cam kết? Nhóm lỗi phụ thuộc.
4. Đó là trường hợp nghiệp vụ dự kiến (không tìm thấy, hết hàng, bị từ chối vì quyền hạn...) hay lỗi lập trình? Cân nhắc **kết quả hoặc ngoại lệ chuyên biệt**; không cưỡng ép vào ba nhóm nếu không đúng ý nghĩa.

Ưu tiên tên lỗi phản ánh trách nhiệm và khả năng phục hồi. Đừng chọn `IllegalStateException` chỉ để khỏi khai báo `throws IOException`. Việc checked hay unchecked là một quyết định API **riêng** với phân loại nguyên nhân.

## 8. Chuyển lỗi qua tầng trừu tượng: giữ đúng nhóm nguyên nhân

Tầng hạ tầng có thể ném `IOException` hoặc `SQLException`; tầng nghiệp vụ có thể công bố một loại lỗi ổn định hơn. **Chỉ chuyển khi tầng hiện tại hiểu chính xác ngữ nghĩa**, không dùng message của driver hoặc tên exception ngẫu nhiên làm bằng chứng:

~~~java
try {
    return provider.quote(currency);
} catch (java.io.IOException cause) {
    throw new RateProviderUnavailableException(
            "Không thể lấy tỷ giá", cause);
}
~~~

Đây là mảnh mã minh họa với `provider`, `currency` và constructor domain exception đã được định nghĩa. `cause` phải được truyền vào wrapper để người điều tra có thể truy lỗi nguồn và suppressed exceptions nếu có. Đừng đánh đồng **input sai** với **trạng thái chưa sẵn sàng** hay **dependency không hoạt động** chỉ để có một loại ngoại lệ chung.

Với tiêu đề bài này, câu hỏi quan trọng vẫn là **lỗi thuộc nhóm nào và caller được làm gì**. Bài tiếp theo về exception translation chỉ ra nơi dịch, khi nào không dịch và cách kiểm thử; bài giữ `cause` đi sâu vào danh tính đối tượng nguyên nhân.

## 9. Ánh xạ ở ranh giới HTTP hoặc service

Khi một API Java đứng sau HTTP, HTTP status cần phản ánh **hợp đồng cụ thể**; không có ánh xạ một-một bắt buộc giữa từng lớp exception và status:

| Nguyên nhân đã xác định | Hướng phản hồi HTTP thường thấy | Lưu ý |
| --- | --- | --- |
| Request sai cú pháp, thiếu trường hoặc vi phạm validation công khai | `400 Bad Request` hoặc `422 Unprocessable Content` | Mô tả trường cần sửa, không đưa stack trace ra client |
| Xung đột với trạng thái tài nguyên đang lưu | `409 Conflict` (tùy API) | `IllegalStateException` do bug nội bộ không mặc nhiên thành `409` |
| Tài nguyên được hỏi không tồn tại | `404 Not Found` | Thường là trường hợp miền nghiệp vụ riêng, không mặc nhiên là lỗi tham số |
| Upstream trả phản hồi lỗi/hỏng | `502 Bad Gateway` (trong vai trò gateway/proxy phù hợp) | Chọn theo vai trò thực tế của service |
| Phụ thuộc tạm không sẵn sàng | `503 Service Unavailable` | Có thể kèm chỉ dẫn thử lại khi có căn cứ |
| Timeout upstream | `504 Gateway Timeout` (khi thực sự là gateway/proxy) | Phân biệt với timeout ở chính service |
| Lỗi triển khai nội bộ chưa xử lý | `500 Internal Server Error` | Ghi log nội bộ, hạn chế chi tiết phản hồi |

Ví dụ API có quy tắc “chỉ hủy đơn ở trạng thái PENDING” thì hủy đơn đã giao là **xung đột trạng thái nghiệp vụ**, thường biểu diễn bằng lỗi miền riêng như `OrderCannotBeCancelledException`. Ngược lại một đối tượng client Java đã `close()` rồi vẫn bị sử dụng là vi phạm vòng đời đối tượng, thường phù hợp với `IllegalStateException`. Hai trường hợp cùng liên quan “trạng thái” nhưng mức API và cách trả HTTP có thể khác nhau.

## 10. Các lỗi thiết kế phổ biến

- **Đổi mọi lỗi thành `IllegalArgumentException`:** đánh đồng dịch vụ mất kết nối với dữ liệu người gọi sai; caller sẽ cố sửa một giá trị vốn hợp lệ.
- **Đổi mọi lỗi thành `IllegalStateException`:** che giấu IOException, SQL timeout, bug và điều kiện nghiệp vụ khác nhau; khó phân biệt retry với sửa trình tự gọi.
- **`catch (Exception ex)` rồi trả `null`/`0`:** biến thất bại thành kết quả hợp lệ giả, làm phát sinh lỗi ở đoạn mã xa hơn. Chỉ dùng fallback nếu hợp đồng cho phép và giá trị fallback có ý nghĩa rõ.
- **`throw new RuntimeException(ex.getMessage())`:** đánh mất `cause` và stack gốc. Nếu cần bọc, dùng constructor có `cause`.
- **Gọi lại API ngay với cùng tham số cho mọi exception:** không sửa được lỗi tham số hoặc lỗi trạng thái, có thể làm trùng giao dịch khi lỗi phụ thuộc xảy ra sau khi bên kia đã nhận lệnh.
- **Dùng thông điệp văn bản làm khóa phân loại:** văn bản có thể thay đổi và được địa phương hóa. Ưu tiên loại exception, mã lỗi ổn định hoặc thuộc tính cấu trúc.
- **Bỏ qua khác biệt giữa lỗi phụ thuộc và kết quả miền nghiệp vụ:** ví dụ HTTP 404 “khách hàng không tồn tại” khác với gateway không truy cập được server.
- **Rò rỉ chi tiết nhạy cảm:** trả stack trace, SQL, chuỗi kết nối hoặc token vào thông báo dành cho client.

## 11. Kiểm thử đúng nhóm và đúng thời điểm thất bại

Kiểm thử nên kiểm tra **loại ngoại lệ** và **không gọi dependency ở nhánh sai điều kiện**. Với một fake hoặc mock có bộ đếm số lần gọi, các trường hợp tối thiểu:

| Tình huống | Kỳ vọng | Provider được gọi? |
| --- | --- | --- |
| `amount = null`, dịch vụ mở | `NullPointerException` | Không |
| `amount = -1`, dịch vụ mở | `IllegalArgumentException` | Không |
| `currency = "vn"`, dịch vụ mở | `IllegalArgumentException` | Không |
| `amount = 2`, `currency = "VND"`, dịch vụ mở | Trả kết quả đúng | Có, một lần |
| `amount = 2`, `currency = "EUR"`, provider ném `IOException` | Giữ `IOException` hoặc bọc đúng loại và giữ `cause` | Có, một lần |
| Sau khi đóng dịch vụ, tham số hợp lệ | `IllegalStateException` | Không |

Ngoài happy path, nên kiểm tra thông báo có ích, `cause` không bị mất khi dịch lỗi, timeout được giới hạn, retry không tạo tác dụng phụ lặp lại, và logging không rò thông tin. Nếu đã quyết định **ưu tiên validation tham số trước kiểm tra trạng thái** như ví dụ, thêm test trường hợp đồng thời vừa sai tham số vừa đóng dịch vụ để bảo vệ thứ tự đó. Thứ tự ưu tiên không có quy tắc Java bắt buộc; API phải chọn và giữ hợp đồng nhất quán.

Với tài nguyên có thể bị thay đổi bởi luồng khác, kiểm tra `closed` rồi gọi tiếp có thể xảy ra race condition nếu không bảo vệ đồng bộ. Ví dụ học tập ở trên dành cho luồng đơn; ứng dụng thực tế cần xử lý thread safety theo hợp đồng riêng.

## 12. Checklist khi thiết kế hoặc review một API

1. Viết rõ tiền điều kiện của tham số: `null`, miền giá trị, định dạng, quy tắc nghiệp vụ công khai.
2. Viết rõ điều kiện trạng thái: trước/sau `open`, `start`, `commit`, `close`; xác định lời gọi nào hợp lệ.
3. Liệt kê phụ thuộc có thể thất bại và cách chúng báo lỗi; xác định lỗi nào có thể phục hồi.
4. Chọn exception hoặc kiểu kết quả thể hiện chính xác nguyên nhân và trách nhiệm của caller; dùng exception miền khi cần.
5. Ghi tài liệu `@throws`, giữ `cause` khi chuyển tầng, quy định retry/timeout khi phù hợp.
6. Kiểm thử ba nhánh lỗi, không gây tác dụng phụ không cần thiết khi validation/state thất bại, và bảo đảm dữ liệu phản hồi an toàn.

**Quy tắc nhận diện:** *Tham số sai* → sửa giá trị truyền vào; *trạng thái sai* → sửa trình tự hoặc vòng đời; *phụ thuộc thất bại* → xử lý ranh giới tích hợp và phục hồi khi an toàn. Một API dễ dùng giúp caller nhìn thấy khác biệt đó qua hợp đồng và loại lỗi, thay vì phải đoán từ thông báo exception.
