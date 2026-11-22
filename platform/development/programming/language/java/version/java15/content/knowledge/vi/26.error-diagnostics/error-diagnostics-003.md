# Phân biệt lỗi dữ liệu với lỗi lập trình trong Java 15+

## 1. Mục tiêu và tình huống

Một dịch vụ Java nhận chuỗi `A12|2|19.95` để tạo đơn hàng. Khi chạy, ba tình huống có thể cùng biểu hiện dưới dạng **exception**:

- Client gửi `A12|x|19.95`: số lượng `x` không phải số nguyên theo hợp đồng dữ liệu.
- Code xử lý một đơn hàng hợp lệ nhưng truy cập biến nội bộ chưa được khởi tạo, gây `NullPointerException`.
- Đơn hàng đã được kiểm tra hợp lệ nhưng kho lưu trữ tạm thời không truy cập được, gây `IOException` hoặc exception ở tầng truy cập dữ liệu.

Nếu bắt mọi `Exception` và trả **“Dữ liệu đầu vào sai”**, ta vừa đổ lỗi cho client khi chương trình có bug, vừa che khuất sự cố hạ tầng. Nếu coi mọi `RuntimeException` là bug, ta lại phân loại sai những lỗi parse hợp lệ như `NumberFormatException`. Cả hai cách đều làm hệ thống khó chẩn đoán, khó giám sát và đôi khi xử lý sai quyền hoặc dữ liệu.

Bài này trả lời chính xác chủ đề **“Phân biệt lỗi dữ liệu với lỗi lập trình”**, trong bối cảnh chẩn đoán lỗi Java 15 và API Java vẫn áp dụng trên các JDK hiện đại.

Sau bài, bạn sẽ:
1. Phân loại **lỗi dữ liệu không hợp lệ**, **lỗi lập trình/vi phạm bất biến**, **lỗi hệ thống/phụ thuộc** và **xung đột trạng thái nghiệp vụ**, không chỉ nhìn tên exception.
2. Xác định **nguồn dữ liệu, trust boundary, hợp đồng API và trách nhiệm khôi phục** trước khi gắn nhãn lỗi.
3. Dùng validation và exception translation có phạm vi nhỏ; giữ stack trace/cause nội bộ khi cần, không làm lộ dữ liệu nhạy cảm ra response.
4. Viết code Java 15 chuẩn với `NumberFormatException`, `BigDecimal`, exception nghiệp vụ, `IOException` và một ca bug cố ý.
5. Đọc **12 dòng stdout đã kiểm chứng**, giải thích vì sao không bắt mọi lỗi làm “400 Bad Request”.
6. Thiết kế logging, HTTP mapping (nếu là API web), retry policy, cảnh báo và bộ test cho từng nhóm lỗi.

**Nguyên tắc xuyên suốt:** Một exception là **tín hiệu kỹ thuật**. Nhãn “lỗi dữ liệu” hay “lỗi lập trình” phải dựa vào **hợp đồng và nguồn gốc của dữ liệu tại đúng tầng xử lý**, không được suy luận tuyệt đối từ việc exception là checked hay unchecked.

## 2. Bốn nhóm lỗi để chẩn đoán có trách nhiệm

| Nhóm | Định nghĩa thực hành | Ví dụ | Hướng xử lý |
| --- | --- | --- | --- |
| **Dữ liệu đầu vào không hợp lệ (invalid input)** | Dữ liệu từ ranh giới không đáng tin vi phạm format, type, range hoặc quy tắc được công bố | Thiếu trường, số lượng bằng 0, ngày sai format, payload vượt size limit | Từ chối có lý do an toàn; client sửa dữ liệu; thường không retry nguyên bản |
| **Lỗi lập trình / invariant violation** | Code tự vi phạm giả định nội bộ mà lẽ ra phải đúng sau validation | Truy cập danh sách sai index, cast sai đối tượng nội bộ, dereference biến nội bộ null | Ghi log có stack trace; alert; fix/test/deploy; không đổ cho client |
| **Lỗi hệ thống / phụ thuộc (operational)** | Không thực hiện được vì tài nguyên hoặc dịch vụ ngoài không sẵn sàng | Network timeout, DB unavailable, ổ đĩa hết dung lượng, lỗi I/O | Retry có giới hạn nếu an toàn, circuit breaker, failover hoặc báo tạm thời |
| **Xung đột / từ chối nghiệp vụ (domain conflict)** | Dữ liệu cú pháp hợp lệ nhưng yêu cầu không hợp trạng thái/quyền/quy tắc ứng dụng | Trùng mã giao dịch, version conflict, không đủ tồn kho | Trả mã nghiệp vụ riêng (ví dụ conflict), không gọi là bug tự động |

**Một dữ liệu lỗi cũng có thể báo hiệu vấn đề nội bộ.** Nếu người dùng gửi số lượng `x`, đó là input invalid. Nhưng nếu **chính hệ thống** lưu một bản ghi đã qua validate với số lượng `x` vào DB rồi lần sau đọc lại, có thể là data corruption, lỗi migration hoặc bug persistence; không trả thẳng “client nhập sai” cho yêu cầu đọc bản ghi đó.

### Cần phân biệt thêm lỗi bảo mật và lỗi tài nguyên

- **Authentication/authorization failures**: không được coi chỉ là lỗi format hoặc lỗi lập trình; trả kết quả theo chính sách bảo mật, không tiết lộ thông tin về tài khoản hoặc dữ liệu.
- **Quota/rate limit/oversized payload**: có thể đến từ client vi phạm giới hạn hoặc bị tấn công. Validation và resource limits phải xảy ra sớm.
- **`OutOfMemoryError`, `StackOverflowError`, lỗi JVM nghiêm trọng**: không phải “input invalid” thông thường; cần xử lý ở mức độ sức khỏe hệ thống/tiến trình, không bắt `Throwable` rồi cố chạy nghiệp vụ bình thường.

**Câu hỏi chọn nhóm:** Ai sở hữu đầu vào? Hợp đồng nào đã được cam kết? Có thể sửa bằng cách đổi payload không? Có phải hệ thống không giữ được invariant? Có cần retry với chính payload ấy không? Ai cần được cảnh báo?

## 3. Ranh giới tin cậy quyết định ý nghĩa của một lỗi

Một hệ thống thường có luồng:

```text
[HTTP, CLI, file upload, message queue, external API]
                           |
                           v
                 RANH GIỚI ĐẦU VÀO
            size/encoding/schema/range checks
                           |
              +------------+------------+
              |                         |
         Không hợp lệ                  Hợp lệ
              |                         |
          INPUT_ERROR                   v
                                Domain model đã validate
                                         |
                                         v
                                   Business logic
                                   /          \
                              invariant OK   invariant sai
                                 |                |
                                 v                v
                         Dependency access   PROGRAMMING_ERROR
                                 |
                         +-------+-------+
                         |               |
                      success       external failure
                         |               |
                         v               v
                        OK          SYSTEM_ERROR
```

Với code có hợp đồng rõ:
- **Trước khi validate**: nhận dữ liệu null, text không đúng kiểu, số quá lớn, JSON thiếu trường là điều có thể dự kiến. Xử lý như lỗi đầu vào nếu client chịu trách nhiệm.
- **Sau khi validate và tạo domain object hợp lệ**: những điều kiện như “đơn hàng đã validate nhưng quantity = null” phải được coi là **invariant bị phá**, không phải cứ đổ ngược cho client.
- **Tại ranh giới dữ liệu ngoài khác** (DB, file, message broker): phải xem **nguồn**. Một record bị lỗi có thể được đưa vào quarantine/poison-message handling, báo data quality incident, không luôn là lập trình viên hoặc client hiện tại sai.
- **Tại dependency**: timeout, connection reset, storage outage cần xử lý theo loại tác vụ và khả năng thực hiện lại an toàn.

### Ví dụ cùng một exception nhưng nguyên nhân khác nhau

```java
// Tình huống A: text do client gửi.
int quantity = Integer.parseInt(requestQuantity);
// NumberFormatException khi client gửi "abc":
// -> có thể dịch thành validation error.

// Tình huống B: code tự tạo hằng nội bộ.
int port = Integer.parseInt(INTERNAL_CONFIG_STRING);
// NumberFormatException vì cấu hình deployment bị sai:
// -> configuration/operational error, không phải client bad input.
```

Hai đoạn trên là **minh họa không độc lập**, giả sử có biến đúng tên trong phương thức. Cùng `NumberFormatException` nhưng trách nhiệm khác nhau do **nguồn dữ liệu khác nhau**.

Tương tự, `NullPointerException` có thể phát sinh vì lập trình viên quên kiểm tra body null, vì code tự đặt field null hoặc do một thư viện bị lỗi. Khi null đến từ client, hãy **phát hiện sớm và trả validation error có chủ đích**; không để `NullPointerException` trôi ra rồi vội phân loại mọi NPE là input error. Nếu NPE vẫn xảy ra trong logic với model đã đảm bảo non-null, cần điều tra bug.

## 4. Checked và unchecked exceptions: hữu ích nhưng không đủ để phân loại

Java có hệ thống:

```text
Throwable
  +-- Exception
  |     +-- IOException             (checked)
  |     +-- SQLException            (checked)
  |     +-- RuntimeException        (unchecked)
  |            +-- IllegalArgumentException
  |            |      +-- NumberFormatException
  |            +-- NullPointerException
  |            +-- IndexOutOfBoundsException
  |            +-- IllegalStateException
  +-- Error
        +-- OutOfMemoryError
        +-- StackOverflowError
```

- **Checked exception**: ngoại lệ mà compile-time yêu cầu catch hoặc khai báo throws, ví dụ `IOException`, `SQLException`, exception nghiệp vụ tự định nghĩa `extends Exception`.
- **Unchecked exception**: `RuntimeException` và các lớp con, cùng `Error`. Không bị Java compiler bắt buộc catch/declare.
- **Checked không đồng nghĩa có thể retry**. Một `IOException` có thể là quyền file sai không thể khôi phục bằng retry, hoặc I/O tạm thời.
- **Unchecked không đồng nghĩa bug**. `NumberFormatException` do input `"abc"` là hành vi parser được dự kiến.
- **Checked không tự đồng nghĩa input error**. `SQLException` có thể do network, schema migration, constraints hoặc bug SQL.
- **`IllegalArgumentException` không luôn là client bad input**: nếu một method nội bộ truyền argument sai tới API thì đó là vi phạm contract ở **caller**.
- **`IllegalStateException` không luôn là bug**: trạng thái domain không cho phép một hành động có thể là conflict dự kiến, nhưng nên biểu diễn rõ bằng kiểu lỗi/domain result phù hợp.
- **`Error`** thường chỉ sự cố nghiêm trọng; không dùng `catch (Throwable)` để chuyển mọi lỗi thành “400”.

**Quy tắc:** Khi dịch lỗi thành kết quả public, xem **operation + trust boundary + hợp đồng**. Chọn loại exception giúp code dễ hiểu, nhưng tên class không thay thế chẩn đoán.

## 5. Thiết kế validation: biết chắc dữ liệu sai trước khi áp dụng nghiệp vụ

### 5.1. Validate theo tầng

Một pipeline đơn giản cho dữ liệu nhận từ bên ngoài:

1. **Giới hạn kích thước** trước khi parse hoặc cấp phát các buffer lớn; ví dụ giới hạn request 128 ký tự ở bài tập. Ở ứng dụng thật cần giới hạn cả **bytes** khi nhận từ mạng, tránh kiểm tra `String.length()` thay cho dung lượng thực.
2. **Encoding/framing**: UTF-8 hợp lệ, đúng định dạng payload, đúng số lượng trường, tách trường không bỏ mất vị trí rỗng.
3. **Syntax/type**: số nguyên, số thập phân, ngày/giờ, mã ID theo grammar đã công bố.
4. **Range/semantic**: quantity 1..1000, price dương và nằm trong khoảng được phép, ngày nằm trong khung nghiệp vụ.
5. **Cross-field validation**: số đầu/cuối, tổng tiền, quan hệ giữa các trường.
6. **Domain validation/authorization**: quyền đặt hàng, tài khoản hợp lệ, trạng thái tồn kho, version conflict.
7. **Chỉ sau đó** đưa domain object hợp lệ vào phần xử lý có invariant rõ.

Nên đặt các ràng buộc càng sớm càng tốt, nhưng không lặp validation vô tội vạ ở mọi method. Cần một contract rõ: tầng parse đảm bảo gì? Tầng domain model đảm bảo gì? Tầng persistence có thể từ chối những điều kiện nào?

### 5.2. Chuyển text sang số, không dùng exception message của JVM làm API

```java
int quantity;
try {
    quantity = Integer.parseInt(rawQuantity);
} catch (NumberFormatException ex) {
    throw new BadInputException("quantity must be an integer");
}
```

Đây là đoạn **minh họa trong phương thức đã có `rawQuantity`**, và lớp `BadInputException` sẽ được định nghĩa trong chương trình đầy đủ mục 9.

Không phản hồi trực tiếp `ex.toString()` cho người dùng: exception có thể mang input nhạy cảm, thông tin về implementation hoặc chi tiết không ổn định theo phiên bản JDK. Dùng thông điệp validation ổn định, dễ hiểu theo protocol và ghi log nội bộ phù hợp.

### 5.3. Giá tiền cần BigDecimal và hợp đồng định dạng rõ

Với tiền tệ, `double` có sai số biểu diễn nhị phân nên không thích hợp nếu cần tính đúng số thập phân theo quy tắc kế toán. Ví dụ:

```java
BigDecimal unitPrice = new BigDecimal("19.95");
BigDecimal total = unitPrice.multiply(BigDecimal.valueOf(2));
System.out.println(total.toPlainString()); // 39.90
```

Sử dụng `BigDecimal(String)`, `BigDecimal.valueOf(...)` khi phù hợp và phép so sánh `compareTo`. Không dùng `new BigDecimal(0.1)` để kỳ vọng giá trị chính xác 0.1 thập phân từ binary floating-point. Nếu hệ thống yêu cầu đúng 2 chữ số sau dấu chấm, cần định nghĩa việc **làm tròn hay từ chối**, không âm thầm làm tròn mọi chuỗi nhập sai.

Ví dụ mục 9 **từ chối** giá có trên hai chữ số thập phân (19.955); đồng thời từ chối giá ≤0 và >99999.99. Nó dùng `price.setScale(2)` sau khi đã kiểm tra scale/range. Tùy giao thức, có thể cần **bắt buộc** đúng hai chữ số, cấm exponent notation hoặc chọn locale-specific formatting khác; những quy tắc đó là quyết định của domain, không phải mặc định của `BigDecimal`.

## 6. Một số lỗi dữ liệu thường gặp trong Java hiện hành

| Nguồn dữ liệu | API/phép kiểm | Lỗi có thể gặp | Nhận định đúng |
| --- | --- | --- | --- |
| Chuỗi số nguyên từ user | `Integer.parseInt`, `Long.parseLong` | `NumberFormatException` | Input error **nếu** chuỗi thật sự đến từ user và vi phạm contract |
| Số thập phân | `new BigDecimal(String)` | `NumberFormatException` | Parse error; bổ sung precision/range theo domain |
| Ngày tháng | `LocalDate.parse` / `DateTimeFormatter` | `DateTimeParseException` | Input syntax/semantic error nếu ngày người dùng cung cấp |
| UTF-8 bytes | `CharsetDecoder` và `CodingErrorAction.REPORT` | `CharacterCodingException` | Bytes không thỏa contract encoding tại trust boundary |
| Payload thiếu trường | Kiểm tra schema/`split(...,-1)` | Exception ứng dụng do ta định nghĩa | Data invalid, **không** để crash `ArrayIndexOutOfBoundsException` |
| Mã ID sai grammar | Regex / validation code | Domain validation exception | Không nên coi như lập trình viên sai |
| Số nguyên đã tràn | `Math.addExact` / `multiplyExact` | `ArithmeticException` | Xem nguồn/range: user vượt giới hạn, lỗi thiết kế hoặc invariant sai |
| Dữ liệu DB cũ bị sai | Parser/mapper ở persistence | Có thể là các parse exceptions tương tự | **Data integrity/configuration incident**, không tự đổ cho current client |
| Đối số method nội bộ sai | API Java kiểm tra argument | `IllegalArgumentException` | Thường là **caller bug**, không nhất thiết input error |
| Danh sách truy cập sai index trong business logic | `list.get(index)` | `IndexOutOfBoundsException` | Thường là lỗi chỉ mục/invariant trong code |
| File/socket không truy cập được | I/O APIs | `IOException`, `SocketTimeoutException` | Phụ thuộc/operational hoặc policy/quyền — cần xem ngữ cảnh |

### 6.1. Ví dụ ngày tháng strict, không “sửa hộ” input bất hợp lệ

```java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;

DateTimeFormatter formatter = DateTimeFormatter
        .ofPattern("uuuu-MM-dd")
        .withResolverStyle(ResolverStyle.STRICT);
LocalDate date = LocalDate.parse("2026-02-28", formatter);
// "2026-02-30" sẽ bị từ chối bằng DateTimeParseException.
```

Đây là đoạn minh họa cần đặt trong một phương thức, các import tương ứng. Dùng `uuuu` và resolver strict giúp hợp đồng ngày lịch rõ hơn. Không gọi `LocalDate.parse` rồi catch tất cả exceptions thành “mã đơn hàng không đúng”.

### 6.2. Bytes UTF-8 bị lỗi, không chấp nhận dữ liệu đã bị thay thế âm thầm

```java
java.nio.charset.CharsetDecoder strictUtf8 =
        java.nio.charset.StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(
                    java.nio.charset.CodingErrorAction.REPORT)
                .onUnmappableCharacter(
                    java.nio.charset.CodingErrorAction.REPORT);

String value = strictUtf8.decode(
        java.nio.ByteBuffer.wrap(receivedBytes)).toString();
```

Đoạn này thuộc phương thức có biến `byte[] receivedBytes` và xử lý `CharacterCodingException`. `new String(bytes, UTF_8)` có thể thay malformed sequences bằng ký tự thay thế; nếu protocol yêu cầu UTF-8 strict, decoder cấu hình REPORT sẽ giúp từ chối rõ. Vẫn cần giới hạn bytes đầu vào và xác thực dữ liệu theo nhu cầu.

## 7. Lỗi lập trình: dựa vào invariant và trách nhiệm caller

### 7.1. NPE và lỗi chỉ mục

Ví dụ:

```java
Order validatedOrder = getOrderFromTrustedDomainLayer();
String id = validatedOrder.id; // Không được null theo contract.

String cachedName = null;        // Bug nội bộ.
cachedName.length();             // NullPointerException.
```

Đây chỉ là **mã minh họa có chủ ý gây lỗi**, không phải chương trình độc lập. Nếu một field nội bộ đã được tuyên bố non-null nhưng không được gán, lỗi cần được sửa ở code/lifecycle, không trả cho client “tên sản phẩm sai định dạng”.

Tương tự:

```java
java.util.List<String> items = java.util.List.of("one");
String second = items.get(1); // IndexOutOfBoundsException.
```

Cần kiểm tra nguồn index. Nếu index là đầu vào bên ngoài và ứng dụng không validate, phải bổ sung validation ở boundary. Nếu index được tính từ logic nội bộ sai, sửa thuật toán và viết unit tests.

### 7.2. Objects.requireNonNull không đồng nghĩa validation hợp lệ cho user

`Objects.requireNonNull(arg)` hữu ích để xác nhận **contract nội bộ**: argument bắt buộc không null cho method chỉ được gọi sau validation. Nhưng tại API public nhận body người dùng, nếu body null là lỗi được dự kiến, hãy trả một lỗi validation có chủ đích thay vì trông chờ `NullPointerException`.

Ví dụ hai ý nghĩa khác nhau:

```java
// User-facing boundary:
if (requestBody == null) {
    throw new BadInputException("request body is missing");
}

// Internal method contract:
this.repository = java.util.Objects.requireNonNull(repository,
        "repository dependency must be configured");
```

Đoạn là minh họa trong các ngữ cảnh có `requestBody`, `repository` và class exception định nghĩa phù hợp. Không “chữa” lỗi cấu hình repository bị null bằng cách báo client gửi request sai.

### 7.3. Đừng biến bug thành dữ liệu “xấu”

Các anti-pattern nguy hiểm:

```java
try {
    processValidatedOrder(order);
} catch (RuntimeException ex) {
    // Sai: ClassCastException, NullPointerException, IndexOutOfBoundsException
    // hoặc lỗi logic đều bị đổ cho client.
    throw new BadInputException("bad request");
}
```

Code minh họa này **không nên dùng**, vì vừa mất phân biệt nguyên nhân, vừa che stack trace/context. Thay bằng catch **đúng exception dự kiến ở đúng thao tác**, hoặc để bug nổi lên global error handler/tracking.

**Lưu ý:** “nổi lên” không đồng nghĩa lộ stack trace cho người dùng. Public API có thể trả generic 500, nhưng nội bộ cần giữ stack trace, request ID/correlation ID, alert và test để sửa lỗi.

## 8. Lỗi hệ thống/phụ thuộc và xung đột nghiệp vụ

### 8.1. I/O/DB timeout không phải lỗi dữ liệu

Một request hoàn toàn hợp lệ vẫn có thể thất bại vì:
- Database down hoặc connection pool exhausted.
- Disk không đủ dung lượng hoặc file permission thay đổi.
- Network timeout, DNS failure, service remote không phản hồi.
- Container bị giới hạn CPU/memory gây gián đoạn.

Bản chất thường là **operational failure**, không phải yêu cầu sửa trường quantity. HTTP (nếu là REST API) có thể chọn `503 Service Unavailable` hoặc mã 5xx phù hợp; retry cần xét method và idempotency.

Không suy từ mọi `IOException` rằng retry sẽ thành công. Ví dụ `AccessDeniedException` với permission bị thiếu kéo dài có thể yêu cầu sửa config/quyền; một `SocketTimeoutException` sau khi gửi giao dịch có thể mang **kết quả chưa biết**, cần query status/idempotency key thay vì gửi lại vô hạn.

### 8.2. Dữ liệu hợp lệ nhưng xung đột trạng thái

Ví dụ:
- Client cập nhật phiên bản 3 nhưng bản ghi hiện tại đã ở phiên bản 4.
- Mã đơn đã tồn tại và chính sách cấm trùng.
- Yêu cầu hủy đơn đã giao hàng.
- User không có quyền thực hiện thao tác.

Đây là **domain/authorization decision**, không cần quy thành bug. Có thể dùng typed result, domain exception, HTTP 409 (conflict) hoặc 403/404 tùy chính sách. Cũng không gộp hết thành “422” vì format body có thể hoàn toàn hợp lệ.

**Ranh giới quan trọng:** Nếu code khẳng định business invariant mà không kiểm tra điều kiện cạnh tranh (race condition), kết quả sai có thể là **bug của transaction/concurrency**, dù lúc đầu hiện ra như một lỗi constraint ở DB. Hãy phân tích workflow chứ không tự suy từ một SQLException.

## 9. Chương trình Java 15 đầy đủ: phân biệt input, dependency và bug

Ví dụ sau dùng một input **chuỗi ba trường**:
- `orderId|quantity|price`;
- order ID gồm một chữ hoa theo sau 2–11 ký tự chữ hoa/số;
- quantity là integer từ 1 đến 1000;
- price dương, không quá 99999.99, tối đa 2 chữ số sau dấu thập phân.

Các ràng buộc này **được bài thực hành tự định nghĩa**, không phải chuẩn hóa toàn cầu của ngành bán hàng. Dấu phân cách `|`, không tự trim/canonicalize dữ liệu; các hệ thống thật cần đặc tả encoding, locale, payload size, currency rounding, version rõ ràng.

Kết quả phân loại:
- `BadInputException extends Exception` cho những lỗi **dữ liệu khách nhập** đã biết; mã nghiệp vụ stable.
- `IOException` giả lập một dependency outage **sau khi input đã hợp lệ**.
- `NullPointerException` được cố ý tạo **trong code nội bộ** sau parse để chứng minh bug **không** phải input lỗi.
- `runCase(...)` là **test harness** bắt `RuntimeException` để in ra một dòng có thể kiểm chứng; production phải log/alert hoặc propagate đúng, tuyệt đối không biến bug thành thành công.

Lưu file đúng tên **`FaultClassificationDemo.java`**:

```java
import java.io.IOException;
import java.math.BigDecimal;

public final class FaultClassificationDemo {
    static final class BadInputException extends Exception {
        BadInputException(String message) { super(message); }
    }

    static final class Order {
        final String id;
        final int quantity;
        final BigDecimal unitPrice;

        Order(String id, int quantity, BigDecimal unitPrice) {
            this.id = id;
            this.quantity = quantity;
            this.unitPrice = unitPrice;
        }

        BigDecimal total() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    static Order parseRequest(String body) throws BadInputException {
        if (body == null || body.isBlank()) {
            throw new BadInputException("request body is missing");
        }
        if (body.length() > 128) {
            throw new BadInputException("request is too long");
        }

        String[] fields = body.split("\\|", -1);
        if (fields.length != 3) {
            throw new BadInputException("expected 3 fields");
        }
        String id = fields[0];
        if (!id.matches("[A-Z][A-Z0-9]{2,11}")) {
            throw new BadInputException("orderId format is invalid");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(fields[1]);
        } catch (NumberFormatException e) {
            throw new BadInputException("quantity must be an integer");
        }
        if (quantity < 1 || quantity > 1000) {
            throw new BadInputException("quantity must be 1..1000");
        }

        final BigDecimal price;
        try {
            price = new BigDecimal(fields[2]);
        } catch (NumberFormatException e) {
            throw new BadInputException("price must be a decimal");
        }
        if (price.scale() > 2) {
            throw new BadInputException("price supports at most 2 decimals");
        }
        if (price.signum() <= 0
                || price.compareTo(new BigDecimal("99999.99")) > 0) {
            throw new BadInputException("price must be > 0 and <= 99999.99");
        }
        return new Order(id, quantity, price.setScale(2));
    }

    static void process(String body, boolean simulateDependencyFailure,
                        boolean simulateBug)
            throws BadInputException, IOException {
        Order order = parseRequest(body);
        if (simulateBug) {
            // Simulated internal programming bug; not caused by input syntax.
            String mustBeInitialized = null;
            mustBeInitialized.length();
        }
        if (simulateDependencyFailure) {
            throw new IOException("Simulated storage outage");
        }
        System.out.println("OK: order=" + order.id
                + ", total=" + order.total().toPlainString());
    }

    static void runCase(String name, String body,
                        boolean ioFailure, boolean programmingBug) {
        System.out.print(name + " => ");
        try {
            process(body, ioFailure, programmingBug);
        } catch (BadInputException e) {
            System.out.println("INPUT_ERROR: " + e.getMessage());
        } catch (IOException e) {
            System.out.println("SYSTEM_ERROR: dependency unavailable");
        } catch (RuntimeException e) {
            // This catch is a demonstration/test harness only:
            // production code must log/alert with a correlation ID,
            // return a generic 500, and never silently accept/ignore the bug.
            System.out.println("BUG_DETECTED: "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        runCase("valid", "A12|2|19.95", false, false);
        runCase("missing-field", "A12|2", false, false);
        runCase("bad-quantity", "A12|x|19.95", false, false);
        runCase("quantity-range", "A12|0|19.95", false, false);
        runCase("bad-price", "A12|2|NaN", false, false);
        runCase("precision", "A12|2|19.955", false, false);
        runCase("bad-id", "a12|2|19.95", false, false);
        runCase("negative-price", "A12|2|-1.00", false, false);
        runCase("empty-field", "A12||19.95", false, false);
        runCase("missing-body", null, false, false);
        runCase("dependency", "A12|2|19.95", true, false);
        runCase("program-bug", "A12|2|19.95", false, true);
    }
}
```

### 9.1. Biên dịch và chạy

Với JDK hỗ trợ Java 15:

```bash
javac --release 15 FaultClassificationDemo.java
java FaultClassificationDemo
```

**Stdout chính xác đã biên dịch và chạy kiểm chứng** trên JDK hiện đại với `javac --release 15`:

```text
valid => OK: order=A12, total=39.90
missing-field => INPUT_ERROR: expected 3 fields
bad-quantity => INPUT_ERROR: quantity must be an integer
quantity-range => INPUT_ERROR: quantity must be 1..1000
bad-price => INPUT_ERROR: price must be a decimal
precision => INPUT_ERROR: price supports at most 2 decimals
bad-id => INPUT_ERROR: orderId format is invalid
negative-price => INPUT_ERROR: price must be > 0 and <= 99999.99
empty-field => INPUT_ERROR: quantity must be an integer
missing-body => INPUT_ERROR: request body is missing
dependency => SYSTEM_ERROR: dependency unavailable
program-bug => BUG_DETECTED: NullPointerException
```

Chương trình có **12 dòng stdout**: 1 happy path, 9 input errors, 1 dependency failure và 1 intentionally injected bug. Không dùng kết quả ngẫu nhiên, không cần mạng hay database ngoài. Các nhãn `INPUT_ERROR`/`SYSTEM_ERROR`/`BUG_DETECTED` là **nhãn kiểm thử**, không phải class có sẵn trong Java hoặc HTTP status code tự động.

### 9.2. Vì sao các catch được đặt như vậy?

- Chỉ `parseRequest(...)` chịu trách nhiệm biết **chuỗi client vi phạm hợp đồng**. Nó biến `NumberFormatException` phát sinh ở **đúng thao tác parse input** thành `BadInputException` có thông điệp ổn định.
- `process(...)` không bắt cả đoạn code bằng `catch (RuntimeException)`. Nếu logic đã được validate mà dereference một biến nội bộ null, exception **được truyền ra** thay vì nói input sai.
- `IOException` chỉ xuất hiện qua ca giả lập dependency lỗi **sau khi parse thành công**; test harness báo chung “dependency unavailable” mà không public hóa message mô phỏng.
- `runCase(...)` catch `RuntimeException` **chỉ để in một ca bug có thể kiểm tra trong tài liệu**. Trong production, global error handler có thể ghi stack trace/correlation ID và trả lỗi 500 tổng quát, nhưng phải có cơ chế quan sát, cảnh báo hoặc rethrow phù hợp. **Không im lặng nuốt lỗi hoặc tự báo nghiệp vụ thành công.**
- `BadInputException extends Exception` chỉ là một cách biểu diễn lỗi; ứng dụng có thể dùng một domain result object thay cho throw khi invalid input là tình huống rất phổ biến.
- `String.split("\\|", -1)` giữ cả trường rỗng; vì thế `A12||19.95` không biến thành gói chỉ còn hai trường. Quy tắc này quan trọng để báo đúng field lỗi.
- `BigDecimal` được dùng để giữ phép tính tiền thập phân có hợp đồng; không sử dụng `double` cho ví dụ cần tính chính xác.
- Input `"1E2"` được `BigDecimal` chấp nhận là 100 vì Java hiểu exponent notation. Nếu hợp đồng sản phẩm **chỉ** cho phép dạng `123.45`, phải thêm regex/schema kiểm tra cú pháp trước khi tạo `BigDecimal`; bài không cố tuyên bố parser này cấm mọi định dạng khoa học.

### 9.3. Những gì demo chưa phải production-ready

Đây là **parser minh họa**, không phải một REST controller đầy đủ. Nó chưa bao gồm:
- Unicode normalization hoặc wire-level byte size limit; length 128 tính theo UTF-16 code units.
- Authentication/authorization, request ID, audit policy, currency code/tax/rounding rules.
- Đối chiếu uniqueness và transaction trong database.
- Cấu hình HTTP status, JSON error schema, correlation ID và log sink.
- Giới hạn tài nguyên ở tầng network trước khi decode.
- Retry/circuit breaker khi dependency có lỗi.
- Validation mở rộng cho số dạng exponential, số ký tự tiền tệ hoặc thousand separators theo yêu cầu địa phương.

Không dùng một ví dụ chạy console như bằng chứng rằng ứng dụng đã xử lý mọi dạng dữ liệu ác ý, concurrency hoặc rủi ro nghiệp vụ.

## 10. Bản đồ ngoại lệ → trách nhiệm tại các tầng

| Tầng | Exception hoặc condition | Hướng phân loại ban đầu | Làm gì tiếp? |
| --- | --- | --- | --- |
| HTTP body decoder | Malformed UTF-8, payload quá dài | Invalid external input | 400/413 tùy hợp đồng và bảo mật |
| JSON/form/CSV parser | Missing field, unexpected syntax, unknown mandatory type | Invalid external input | 400 hoặc 422 có schema lỗi rõ |
| Input validation | Quantity 0, date sai format/range | Invalid external input | 422 hoặc 400, thông điệp field-level |
| Domain command | ID trùng, optimistic lock version mismatch | Business conflict | 409 hoặc domain result thích hợp |
| Authorization | Identity không đủ quyền | Security decision | 403/404/401 tùy tình huống/chính sách |
| Business implementation | NPE, invalid cast, illegal index do code | Programming defect | 500 generic, log/alert nội bộ |
| Internal invariant check | `IllegalStateException` do lifecycle sai | Programming defect hoặc state conflict | Điều tra hợp đồng; không tự coi là 400 |
| Storage/remote service | Timeout, connection refused | Operational/dependency error | 503/504/5xx thích hợp, retry **nếu an toàn** |
| Persistence mapping | DB record vi phạm schema nội bộ | Data integrity/configuration incident | 500/alert/quarantine, không đổ cho current user |
| Runtime | OOM/StackOverflow/VM fatal error | Process/infra incident | Health check, recovery/deployment; không trả 400 |

**HTTP statuses chỉ mang tính ví dụ tùy thiết kế API.** 400 và 422 được dùng khác nhau giữa các API; quan trọng hơn là giữ lỗi client có thể sửa **khác** lỗi server cần điều tra. Không gửi raw exception stack, SQL text, file path, token, user secrets ra response.

## 11. Thiết kế exception translation không làm mất nguyên nhân

### 11.1. Chỉ đổi exception ở đúng ranh giới

Một pattern tốt:

```java
static int parsePositiveQuantity(String value) throws BadInputException {
    final int q;
    try {
        q = Integer.parseInt(value);
    } catch (NumberFormatException cause) {
        throw new BadInputException("quantity must be an integer");
    }
    if (q <= 0) {
        throw new BadInputException("quantity must be positive");
    }
    return q;
}
```

Đây là snippet minh họa (cần lớp `BadInputException` như mục 9). Nếu cần **giữ nguyên cause** cho log/troubleshooting, thiết kế exception constructor `BadInputException(message, cause)` và wrap bằng `new BadInputException(..., cause)`. Với input từ client, nhiều ứng dụng cố tình không ghi cause/message nếu nó chứa raw input nhạy cảm; chọn theo logging policy.

Trong các tầng infrastructure:
- Có thể dịch một `IOException` từ adapter thành `DependencyUnavailableException` theo contract domain/application.
- **Giữ cause chain** và metadata kỹ thuật nội bộ (resource, operation, latency, status khi an toàn).
- Không biến mọi lỗi IO thành “có thể retry” và không parse exception message để quyết định logic.
- Khi throw lại exception, giữ thông tin phù hợp; không chỉ `throw new Exception("failed")` làm mất stack/cause.

### 11.2. Error code ổn định, thông điệp thân thiện

Public API có thể thiết kế:

```json
{
  "code": "INVALID_QUANTITY",
  "message": "Số lượng phải là số nguyên từ 1 đến 1000",
  "field": "quantity",
  "requestId": "req-example-001"
}
```

Đây là **mẫu JSON minh họa**, không phải output từ chương trình mục 9. Không dùng exception class name làm error code public vì nội bộ có thể thay đổi theo phiên bản JDK.

Một lỗi lập trình có thể trả:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "Không thể xử lý yêu cầu",
  "requestId": "req-example-001"
}
```

**Không** đưa tên method, stack trace, SQL, đường dẫn file hoặc internal object dump vào response. Cùng requestId có thể dùng để nối response với log nội bộ, không nên để requestId do attacker tự đưa vào làm khóa duy nhất mà không kiểm tra.

### 11.3. Log, metrics và traces theo loại lỗi

Ví dụ fields quan sát nội bộ:
- `error.category = invalid_input | domain_conflict | programming | dependency`.
- `error.code = INVALID_QUANTITY | DB_UNAVAILABLE | INVARIANT_BROKEN`.
- `request.id` / `trace.id`, operation, endpoint, service version, thời điểm.
- `exception.type`, stack trace **nội bộ** khi là lỗi chưa dự kiến.
- Thống kê counts/rates riêng cho các nhóm và mức độ ảnh hưởng.

**Tránh lộ dữ liệu:** không log password, private key, token, raw credit-card data, body chứa PII hoặc toàn bộ SQL parameters nhạy cảm. Với dữ liệu validation, log field name và error code thường hữu ích hơn giá trị raw. Đừng dùng raw user input làm label metric cardinality cao.

## 12. Retry và thông điệp trả về không giống nhau giữa các lỗi

| Loại lỗi | Retry nguyên yêu cầu? | Vì sao |
| --- | --- | --- |
| Input sai cú pháp/range | Thường **không**, đến khi payload được sửa | Retry không làm `"abc"` thành integer |
| Domain conflict | Tùy tình huống, cần dữ liệu/state/version mới | Retry mù có thể lặp conflict |
| Lỗi lập trình | **Không** nên retry vô hạn chỉ để che bug | Có thể tiếp tục tạo lỗi, nhân tải hoặc làm dữ liệu sai |
| Dependency timeout tạm thời | Có thể retry **có giới hạn** nếu operation an toàn | Cần backoff, jitter, circuit breaker và deadline |
| Timeout sau write/commit không rõ kết quả | **Không** đơn giản retry như chưa làm gì | Cần idempotency key hoặc tra cứu/trạng thái giao dịch |
| Resource exhaustion / OOM | Xử lý sức khỏe tiến trình, capacity/backpressure | Retry ngay có thể làm tình hình nghiêm trọng hơn |

**Một checked exception không tự cho phép retry.** Một unchecked exception cũng không có nghĩa mọi dữ liệu phải bị từ chối. Chính **nguyên nhân và operation semantics** mới quyết định hướng tiếp tục.

Nếu hệ thống dùng queue để nhận dữ liệu:
- Payload invalid có thể được trả lỗi/quarantine/dead-letter theo chính sách, tránh poison message retry vô hạn.
- Dependency lỗi có thể được requeue có delay/backoff và max attempts.
- Bug lập trình cần alert mạnh, DLQ hoặc dừng consumer sau khi đã bảo toàn dữ liệu theo quy trình.
- Tất cả nhánh phải kiểm tra duplicate/idempotency để tránh side effects khi message được redeliver.

## 13. Chẩn đoán lỗi qua stack trace mà không đoán bừa

Một stack trace cho bạn biết **lỗi được phát hiện ở đâu**, không nhất thiết nơi root cause bắt đầu. Quy trình:

1. **Đọc exception type, message, cause chain và suppressed exceptions**; kiểm tra exception bị wrap ở tầng nào.
2. **Tìm frame đầu tiên liên quan code của ứng dụng** nơi dữ liệu đi qua boundary, nhưng không kết luận frame đó là nguyên nhân duy nhất.
3. **Xác định provenance của dữ liệu**: raw user payload, DB record, config, result của thư viện hay object nội bộ.
4. **Đối chiếu contract**: field đã validate chưa, method có tiền điều kiện gì, caller là ai.
5. **Thử tái hiện tối thiểu** bằng input đã được ẩn dữ liệu nhạy cảm hoặc fixture an toàn.
6. **Kiểm tra thời điểm và các dependencies**: DB timeout, CPU, memory, network, feature flags, migration.
7. **Phân loại và xử lý**: input/domain (sửa payload), bug (fix code), operational (khôi phục service), data-integrity (sửa nguồn/di trú dữ liệu).
8. **Thêm regression tests** theo tầng nơi lỗi phát sinh và kiểm tra public error mapping.

### Ví dụ NPE chưa đủ chứng minh root cause

Nếu log báo:
```text
java.lang.NullPointerException
    at com.example.OrderService.calculateTotal(...)
```

Dòng này **chỉ là stack trace minh họa**, không lấy từ demo và không thể tự kết luận lỗi do user nhập null. Phải xem `calculateTotal` nhận dữ liệu nào, null được cho phép ở đâu, tầng parse đã đảm bảo gì, ai tạo đối tượng, có race hoặc cấu hình sai không.

**Tránh anti-pattern “catch NullPointerException rồi trả default 0”**: nó có thể biến bug thành sai tiền/kiểm tra quyền. Nếu null là dữ liệu được phép, thiết kế model và flow xử lý null/Optional cụ thể từ trước.

## 14. Các lỗi dễ phân loại nhầm

### 14.1. `IllegalArgumentException` không có một ý nghĩa

- User cung cấp tên loại hàng không có trong tập cho phép → validatable input error.
- Service gọi `Collections.copy(dest, src)` với `dest` sai kích thước do logic nội bộ → caller misuse/bug, có thể báo `IndexOutOfBoundsException`.
- Cấu hình `Duration.ofSeconds`, port hoặc locale sai do deployment → config error.
- Một thư viện ném `IllegalArgumentException` do API caller không tuân hợp đồng → xem call site và trust boundary.

### 14.2. `NumberFormatException` có thể xuất hiện sau lỗi chuẩn hóa

Ví dụ user nhập `"1,000"`, hệ thống định dạng US hay VN chưa được quy định:
- Nếu protocol chỉ cho `1000`, đó là input invalid theo format.
- Nếu UI cho phép dấu phân tách theo locale nhưng backend quên xử lý, đó có thể là **bug tích hợp**.
- Nếu dữ liệu lưu trong DB thay format qua migration, lỗi là data compatibility/integrity.

Đừng đặt `try { parseInt } catch { return 0; }`: số 0 có thể trở thành giá trị nghiệp vụ hợp lệ/sai, làm mất thông tin nguyên nhân.

### 14.3. `ClassCastException` cũng cần xem dữ liệu nguồn

Cast sai một object nội bộ do giả định inheritance/type sai thường là bug. Nhưng khi data deserialization từ nguồn ngoài có discriminator/type không được phép, hệ thống nên validate schema rồi trả input error an toàn, **không để cast nổ rồi báo 500 tùy tiện**. Sửa boundary/schema thay vì coi mọi `ClassCastException` là user lỗi.

### 14.4. DB constraint và race condition

Unique constraint thất bại vì client cố tạo ID đã tồn tại có thể là domain conflict. Tuy nhiên:
- Nếu code kiểm tra rồi insert không có transaction/constraint phù hợp và xảy ra race, thiết kế concurrency của code cần được điều tra.
- Foreign key violation có thể do input reference không hợp lệ, hoặc dữ liệu/transaction nội bộ thiếu nhất quán.
- SQLException/network error là operational; parse error trong SQL từ query hard-coded thường là bug.

**SQLState/error code của DB và operation context** cần được đọc, không dùng `catch (SQLException) -> "invalid data"` cho mọi thứ.

## 15. Bảo mật và giới hạn tài nguyên khi chẩn đoán input

Một parser đúng kiểu dữ liệu chưa đủ an toàn. Cần:
- Đặt giới hạn request **bytes** trước decode, giới hạn số fields/array elements, nesting depth, string length và timeouts.
- Decode UTF-8 strict khi protocol đòi chính xác, tránh Unicode normalization làm thay đổi business identifiers tùy tiện.
- Kiểm tra quá lớn/quá nhỏ và integer overflow; dùng `Math.addExact`/`Math.multiplyExact` khi tràn số phải được coi là lỗi, sau đó phân loại theo nguồn dữ liệu và invariant.
- Tránh regex có nguy cơ **catastrophic backtracking** trên input dài; ưu tiên regex đơn giản hoặc parser có giới hạn.
- Không đưa raw user input vào SQL, shell, file path hoặc reflective class names không kiểm soát; dùng prepared statements/allow-lists và path validation.
- Không để exception message lộ file paths, secrets, SQL, stack trace, internal hostnames hoặc token.
- Có rate limiting nếu attacker cố tạo hàng nghìn input invalid để làm nghẽn parser/logging.
- Không chấp nhận **một phần** command chỉ vì parse được vài fields; validate toàn bộ trước khi thực hiện side effects.
- Nếu validation fail, **không** khôi phục bằng cách chèn default nguy hiểm như `quantity=1`, `price=0` hoặc `role=admin` trừ khi đó là quy tắc đã công bố và có kiểm thử.

**Không bắt `Error` một cách tổng quát trong business logic** để gửi một response “dữ liệu sai”. Với OutOfMemoryError, việc cấp phát thêm object để serialize response thậm chí có thể thất bại. Dùng cơ chế health check, giám sát, memory limits và phục hồi hạ tầng.

## 16. Checklist kiểm thử và review code

Một tập test tối thiểu cho parser và handler:
- [ ] **Valid case** được chấp nhận và tính tổng chính xác: `A12|2|19.95 -> 39.90`.
- [ ] **Missing fields** bị báo field count, không gây index out-of-bounds.
- [ ] **Empty field** (có cả separator) được giữ lại để báo lỗi đúng trường.
- [ ] **Malformed integer** và **integer overflow** đều bị từ chối ở input boundary.
- [ ] **Out-of-range quantity** (0, -1, 1001) báo lỗi range.
- [ ] **Price invalid**: NaN, số âm, 0, quá lớn, quá nhiều chữ số thập phân.
- [ ] **Order ID** sai grammar/case và payload dài vượt limit bị từ chối.
- [ ] **Null/blank body** trả validation error có chủ đích, không để NPE lọt khỏi boundary.
- [ ] **Dependency outage** sau validation được phân loại system error, không bị biến thành bad input.
- [ ] **Internal NPE** do bug sau validation phải được quan sát/alert, không thành lỗi user và không thành success.
- [ ] **Error response** không lộ stack traces, SQL, path, secrets hoặc raw payload nhạy cảm.
- [ ] **Transaction/idempotency** được kiểm tra khi retries hoặc dependency có kết quả chưa xác định.
- [ ] **Persistent corrupted data** không bị gán cho người gọi hiện tại; có alert/quarantine đúng.
- [ ] **Monitoring** tách counts invalid_input, programming, domain_conflict, dependency và high-severity incidents.
- [ ] **Regression test** tạo lại lỗi đã sửa và xác nhận happy path vẫn hoạt động.

Cần kiểm tra riêng các phép đo: tỷ lệ invalid client inputs tăng có thể là thay đổi contract hoặc UI bug; tỷ lệ programming faults tăng sau deployment cần cảnh báo; dependency errors tăng có thể liên quan DB/service outage. Một dashboard chỉ cộng tất cả thành “exception count” sẽ che mất định hướng hành động.

## 17. Câu hỏi thực hành có đáp án

**Câu 1.** `Integer.parseInt("abc")` ném `NumberFormatException`. Có thể chắc chắn đây là bug không?

**Đáp án:** **Không.** Nếu chuỗi đến từ input user theo contract chỉ nhận số nguyên, đây là lỗi dữ liệu có thể dự kiến. Nếu chuỗi do code hoặc config nội bộ tạo không đúng contract, đó có thể là bug/configuration issue.

**Câu 2.** `IOException` luôn là lỗi có thể retry đúng không?

**Đáp án:** **Không.** Network transient có thể retry với backoff nếu operation idempotent, nhưng file permission sai cố định hoặc path không hợp lệ sẽ không tự sửa. Cần xem cause và operation semantics.

**Câu 3.** Một HTTP POST hợp lệ gặp `NullPointerException` vì field nội bộ chưa khởi tạo. Có nên trả 400?

**Đáp án:** **Không.** Đây là bug nội bộ; phản hồi server error tổng quát, log/alert với trace ID và sửa bằng regression test.

**Câu 4.** Nếu user gửi null body và handler chưa validate, `NullPointerException` là lỗi user hay lỗi code?

**Đáp án:** Null body có thể là input invalid, nhưng **việc để nó gây NPE trong handler** cho thấy validation/contract handling thiếu. Bổ sung kiểm tra tại boundary và trả lỗi đầu vào có chủ đích; không lấy exception NPE làm nhãn ngầm cho mọi trường hợp.

**Câu 5.** Client tạo đơn hàng đã tồn tại, payload vẫn đúng định dạng. Đây là bad syntax hay conflict?

**Đáp án:** **Conflict/state-dependent domain error**, thường xử lý bằng mã nghiệp vụ riêng (có thể HTTP 409). Không đổ cho bug chỉ vì DB từ chối unique constraint.

**Câu 6.** Vì sao `catch (RuntimeException) -> BadInputException` là nguy hiểm?

**Đáp án:** Nó bắt cả lỗi lập trình như NPE, cast, index, invariant, khiến client nhận chẩn đoán sai và có thể che lỗi nghiêm trọng. Chỉ translate exception đã biết tại thao tác parser/validator tương ứng.

**Câu 7.** Một bản ghi trong DB sai format nhưng request GET của người dùng hợp lệ. Trả “user nhập sai dữ liệu” đúng không?

**Đáp án:** **Không.** Đây có thể là data integrity issue/migration bug. Cần điều tra nguồn và đối chiếu contract giữa service/DB; không buộc người dùng sửa payload họ không gửi.

**Câu 8.** Vì sao phải dùng `BigDecimal` cho ví dụ giá tiền và kiểm tra scale?

**Đáp án:** Nó biểu diễn số thập phân chính xác cho phép tính theo hợp đồng; scale/range là quy tắc nghiệp vụ cần xác định, không phải auto-accept mọi độ chính xác rồi làm tròn tùy tiện.

**Câu 9.** Lỗi `OutOfMemoryError` là input error có thể catch rồi trả JSON ổn định không?

**Đáp án:** **Không.** Đây là sự cố tài nguyên/JVM nghiêm trọng. Cần giám sát, giới hạn tài nguyên và khôi phục ở mức hệ thống; không đảm bảo tiến trình đủ tài nguyên để tạo response.

**Câu 10.** Nếu một timeout xảy ra **sau** thao tác ghi giao dịch mà client chưa nhận ACK, có nên retry ngay lập tức vô hạn?

**Đáp án:** **Không.** Kết quả có thể đã commit; cần idempotency key, status reconciliation, backoff/deadline và giới hạn số lần thử theo hợp đồng.

**Câu 11.** `DateTimeParseException` khi parse `"2026-02-30"` từ form là lỗi gì?

**Đáp án:** Lỗi dữ liệu đầu vào nếu form đã định nghĩa ngày theo chuẩn strict. Nếu giá trị được chính server tạo từ trusted source thì cần kiểm tra code/cấu hình hoặc data integrity, không tự trả 400.

**Câu 12.** Có được log nguyên exception message từ input do người lạ cung cấp không?

**Đáp án:** Không mặc định. Nó có thể chứa raw PII/token hoặc làm tăng log volume/cardinality; ưu tiên error code, field name, request ID được kiểm soát, redaction và stack trace **nội bộ** chỉ khi cần.

**Tiêu chí đạt:** Bạn nhìn một lỗi Java bất kỳ và biết **đặt lại câu hỏi về nguồn dữ liệu, hợp đồng và trách nhiệm**, thay vì gắn nhãn checked/unchecked hoặc NPE/NumberFormatException một cách tuyệt đối. Bạn có thể thực hiện validation trước side effects, translate đúng lỗi đã biết, bảo vệ public responses và để internal bugs được chẩn đoán thật.

## 18. Tài liệu chuẩn còn áp dụng trên Java hiện hành

- [Java SE 15 – Throwable](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/Throwable.html): cause chain, stack trace, checked/unchecked hierarchy.
- [Java SE 25 – Exception](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Exception.html) và [RuntimeException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/RuntimeException.html): hệ thống ngoại lệ vẫn được hỗ trợ.
- [Java SE 25 – NumberFormatException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NumberFormatException.html): số không thể phân tích cú pháp.
- [Java SE 25 – Integer.parseInt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Integer.html#parseInt(java.lang.String)): contract phân tích integer và lỗi.
- [Java SE 25 – BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html): số thập phân, scale, compareTo, setScale và multiply.
- [Java SE 25 – LocalDate](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/LocalDate.html): parse và ngày lịch.
- [Java SE 25 – DateTimeFormatter](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/format/DateTimeFormatter.html): strict resolution và pattern `uuuu-MM-dd`.
- [Java SE 25 – CharsetDecoder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/CharsetDecoder.html): REPORT cho malformed/unmappable bytes.
- [Java SE 25 – Objects.requireNonNull](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): preconditions cho contract nội bộ.
- [Java SE 25 – IOException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/IOException.html): lỗi I/O, không tự tương đương retryable.
- [Java SE 25 – Math.addExact](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Math.html#addExact(int,int)): kiểm tra overflow khi cần.
- [Java SE 25 – Error](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Error.html): sự cố nghiêm trọng không nên coi như exception nghiệp vụ thông thường.
- [Java SE 25 – SQLException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLException.html): SQLState/vendor code/cause để chẩn đoán DB, không suy một loại chung cho mọi database issue.
- [IETF RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): cách biểu diễn lỗi HTTP có cấu trúc khi thiết kế public API; cần áp dụng theo giao thức/sản phẩm cụ thể.

**Ghi nhớ:** **Dữ liệu sai** là dữ liệu vi phạm hợp đồng tại một trust boundary; **bug** là code phá invariant hoặc gọi API sai theo contract; **lỗi hệ thống** là dependency/tài nguyên không đáp ứng; **domain conflict** là trạng thái nghiệp vụ từ chối một request cú pháp đúng. Tên exception giúp xác định điểm phát hiện lỗi, **không tự quyết định nguyên nhân**. Bắt và chuyển lỗi đúng nơi, giữ thông tin nội bộ để sửa bug, trả phản hồi an toàn, và kiểm thử từng nhóm riêng.