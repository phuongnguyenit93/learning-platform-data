# Thiết kế hợp đồng phương thức và kiểm tra dữ liệu đầu vào

Một phương thức Java có thể biên dịch thành công nhưng vẫn khó sử dụng hoặc dễ gây lỗi nếu người gọi không biết dữ liệu nào được phép truyền vào, phương thức sẽ thay đổi trạng thái nào, kết quả có ý nghĩa gì và lỗi nào có thể xảy ra. Hợp đồng phương thức (method contract) giải quyết vấn đề đó bằng cách mô tả rõ trách nhiệm của bên gọi và bên thực thi.

Thiết kế hợp đồng tốt giúp API dễ hiểu, dễ kiểm thử và an toàn hơn khi nhận dữ liệu từ người dùng, tệp, dịch vụ mạng hoặc thư viện khác. Với Java 27, có thể kết hợp kiểu dữ liệu, record, các tiện ích trong **java.util.Objects**, exception và Javadoc để biểu đạt cũng như kiểm tra các điều kiện này.

Bài viết sử dụng các quy tắc ngôn ngữ và API đang được hỗ trợ trong Java SE 27. Tham khảo [Java Language Specification 27 – Method Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.4), [Method Invocation Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.12), [Java SE 27 API – Objects](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html) và [Oracle Secure Coding Guidelines for Java SE](https://www.oracle.com/java/technologies/javase/seccodeguide.html), phiên bản 11.1 cập nhật tháng 11/2026.

## 1. Hợp đồng phương thức gồm những gì?

Hợp đồng mô tả cách một phương thức được phép gọi và những gì người gọi có thể kỳ vọng sau khi phương thức kết thúc. Một hợp đồng rõ ràng thường có các thành phần sau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Tiền điều kiện (precondition) | Người gọi phải cung cấp dữ liệu hoặc trạng thái nào? | Mã khách hàng không null và không rỗng |
| Hậu điều kiện (postcondition) | Nếu phương thức thành công, kết quả có đặc điểm gì? | Trả về mã đặt chỗ duy nhất |
| Bất biến (invariant) | Điều kiện nào phải luôn đúng với đối tượng hoặc dữ liệu? | Ngày kết thúc phải sau ngày bắt đầu |
| Tác dụng phụ (side effect) | Phương thức có thay đổi trạng thái, ghi dữ liệu hoặc gọi dịch vụ bên ngoài không? | Lưu một giao dịch và phát sinh mã giao dịch |
| Điều kiện lỗi | Trường hợp nào dẫn đến exception hoặc kết quả thất bại? | Ném IllegalArgumentException nếu số khách vượt giới hạn |
| Giới hạn vận hành | Phương thức xử lý tối đa bao nhiêu dữ liệu hoặc có yêu cầu hiệu năng nào? | Không nhận danh sách có hơn 100.000 phần tử |

Ví dụ, một phương thức đặt chỗ có thể được mô tả như sau:

- Tiền điều kiện: yêu cầu đặt chỗ không null; mã khách hàng hợp lệ; ngày kết thúc sau ngày bắt đầu; số khách nằm trong giới hạn cho phép.
- Hậu điều kiện: nếu thành công, trả về một mã đặt chỗ và thông tin thời gian đã được xác nhận.
- Tác dụng phụ: tạo bản ghi đặt chỗ trong hệ thống.
- Điều kiện lỗi: tham số sai sẽ bị từ chối; phòng hết chỗ hoặc dịch vụ lưu trữ gặp lỗi sẽ được báo theo loại lỗi tương ứng.

Hợp đồng không chỉ là một danh sách kiểm tra. Nó còn là thỏa thuận giữa các thành phần trong chương trình. Bên gọi chịu trách nhiệm thỏa mãn tiền điều kiện đã công bố; phương thức chịu trách nhiệm bảo đảm hậu điều kiện nếu thực thi thành công và báo lỗi theo hợp đồng khi không thể hoàn thành.

Java không tự động kiểm tra mọi tiền điều kiện hay hậu điều kiện. Trình biên dịch kiểm tra các quy tắc kiểu và cú pháp; phần kiểm tra giá trị, trạng thái, tác dụng phụ và quy tắc nghiệp vụ phải được thể hiện trong mã, tài liệu và kiểm thử.

## 2. Thiết kế chữ ký phương thức dễ hiểu

### 2.1. Tên phương thức và tên tham số phải thể hiện ý định

Tên phương thức nên mô tả hành động hoặc kết quả cụ thể. Tên tham số nên cho biết dữ liệu đại diện cho điều gì và đơn vị của nó nếu có.

~~~~java
// Tên chung chung, không thể hiện đơn vị hay ý nghĩa
double calculate(double value, double rate);

// Tên cụ thể hơn
Money calculateInterest(Money principal, BigDecimal annualRate);
~~~~

Trong ví dụ thứ hai, người đọc nhận ra phương thức tính tiền lãi, số tiền gốc và lãi suất năm. Với tham số dạng số, nên thể hiện đơn vị trong tên hoặc kiểu dữ liệu, ví dụ **timeoutMillis**, **distanceMeters**, **amountInCents**. Điều này hạn chế việc truyền nhầm giây với mili giây hoặc mét với kilomet.

Tránh các tên quá ngắn như **x**, **data**, **value** khi ngữ cảnh không đủ rõ. Tên tốt giúp người gọi hiểu chữ ký mà không cần mở phần triển khai.

### 2.2. Chọn kiểu tham số thể hiện đúng giới hạn

Kiểu tham số là một phần của hợp đồng. Hãy chọn kiểu gần với khái niệm nghiệp vụ và mức trừu tượng mà phương thức cần:

| Nhu cầu | Kiểu nên cân nhắc | Lý do |
| --- | --- | --- |
| Một số lượng đếm được | int hoặc long | Thể hiện giá trị nguyên |
| Một tỷ lệ cần độ chính xác thập phân | BigDecimal | Kiểm soát phép toán thập phân |
| Một ngày không có giờ | LocalDate | Không phải tự phân tích chuỗi ngày |
| Một thời điểm tuyệt đối | Instant | Đại diện một thời điểm trên trục thời gian |
| Một nhóm giá trị có thứ tự | List<T> | Người gọi truyền được nhiều kiểu triển khai List |
| Một tập giá trị không trùng | Set<T> | Kiểu dữ liệu thể hiện quy tắc không trùng |
| Một cặp khóa và giá trị | Map<K, V> | Biểu đạt ánh xạ |
| Một trạng thái trong tập hữu hạn | enum | Hạn chế các giá trị không hợp lệ |

Ưu tiên nhận interface phù hợp như **List**, **Set**, **Collection**, **Map** thay vì yêu cầu một lớp triển khai cụ thể khi phương thức không phụ thuộc vào đặc điểm riêng của lớp đó. Ví dụ, một phương thức chỉ duyệt dữ liệu thường chỉ cần **Collection<T>** hoặc **Iterable<T>**.

Đối với dữ liệu có nhiều quy tắc gắn kết, hãy tạo kiểu miền riêng hoặc record để gom dữ liệu liên quan. Một record có thể kiểm tra bất biến ngay lúc tạo:

~~~~java
import java.math.BigDecimal;
import java.util.Objects;

record PaymentRequest(String orderId, BigDecimal amount) {
    PaymentRequest {
        orderId = Objects.requireNonNull(orderId, "orderId").strip();
        amount = Objects.requireNonNull(amount, "amount");

        if (orderId.isBlank()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
    }
}
~~~~

Record phù hợp với dữ liệu mang theo giá trị và có thể bảo vệ các điều kiện cơ bản ngay tại điểm khởi tạo. Tuy nhiên, record chỉ tự động tạo các thành phần dữ liệu và hành vi chuẩn; nó không tự biết quy tắc nghiệp vụ của ứng dụng. Các bất biến vẫn phải được kiểm tra trong constructor hoặc phương thức thích hợp.

### 2.3. Giữ số tham số ở mức cần thiết

Một phương thức có quá nhiều tham số độc lập thường khó gọi đúng và khó đọc:

~~~~java
createBooking(customerId, roomId, startDate, endDate,
              guestCount, breakfast, airportPickup, note);
~~~~

Nếu các giá trị thường xuyên đi cùng nhau và tạo thành một khái niệm có ý nghĩa, hãy nhóm chúng vào một kiểu yêu cầu:

~~~~java
createBooking(bookingRequest);
~~~~

Không nên tạo một record chỉ để gom những tham số không liên quan. Một kiểu tham số riêng nên biểu đạt một khái niệm có tên, có quy tắc và có vòng đời rõ ràng.

### 2.4. Tránh tham số boolean làm chữ ký khó hiểu

Một tham số boolean ở vị trí gọi thường không nói rõ ý nghĩa:

~~~~java
generateReport(report, true);
~~~~

Người đọc phải mở phần khai báo để biết **true** có nghĩa là xuất PDF, gửi email hay ghi đè tệp. Có thể thay bằng enum:

~~~~java
enum ReportFormat {
    PDF,
    CSV
}

generateReport(report, ReportFormat.PDF);
~~~~

Hoặc tạo các phương thức có tên thể hiện hành động riêng nếu hai luồng thực sự khác nhau. Không phải mọi boolean đều cần thay thế; boolean vẫn phù hợp khi ý nghĩa tại nơi gọi đã rõ, ví dụ **isActive()** hoặc **contains(value)**.

### 2.5. Dùng overload và varargs có chủ đích

Overload hữu ích khi cùng một hành động có một số cách gọi hợp lý:

~~~~java
void sendMessage(String recipient, String message);
void sendMessage(String recipient, String message, Duration timeout);
~~~~

Các overload cần có ngữ nghĩa nhất quán và không gây nhập nhằng khi truyền **null**, literal số hoặc lambda. Không tạo quá nhiều overload chỉ để mô phỏng tham số tùy chọn.

Varargs phù hợp khi số đối số có thể thay đổi và tất cả cùng một loại:

~~~~java
void logEvents(String category, String... events);

logEvents("payment", "created", "authorized", "completed");
~~~~

Tham số varargs phải đứng cuối danh sách tham số. Bên trong phương thức, nó được xử lý như một mảng. Nếu phương thức giữ tham chiếu đến mảng đó sau khi trả về hoặc chia sẻ nó với thành phần khác, hãy cân nhắc sao chép để tránh người gọi thay đổi dữ liệu ngoài ý muốn.

## 3. Xác định rõ chính sách null và dữ liệu rỗng

### 3.1. Phân biệt null, chuỗi rỗng và chuỗi chỉ có khoảng trắng

Với một tham số String, có ít nhất ba trường hợp cần xem xét:

| Giá trị | Ý nghĩa có thể có |
| --- | --- |
| null | Không có tham chiếu hoặc không được cung cấp |
| Chuỗi rỗng: "" | Có giá trị chuỗi nhưng không có ký tự |
| Chuỗi chỉ có khoảng trắng | Có ký tự nhưng không có nội dung hữu ích theo quy tắc nghiệp vụ |

Không nên tự động coi ba trường hợp này là giống nhau. Ví dụ, trường ghi chú có thể cho phép chuỗi rỗng nhưng mã khách hàng bắt buộc phải có nội dung.

Java cung cấp **String.isEmpty()** và **String.isBlank()**. isBlank kiểm tra chuỗi rỗng hoặc chỉ chứa ký tự khoảng trắng theo định nghĩa của API:

~~~~java
String customerName = Objects.requireNonNull(rawName, "rawName").strip();

if (customerName.isBlank()) {
    throw new IllegalArgumentException("customerName must not be blank");
}
~~~~

**strip()** loại bỏ khoảng trắng ở hai đầu chuỗi theo quy tắc Unicode của API. Chỉ chuẩn hóa bằng strip khi hợp đồng cho phép; với mật khẩu, mã định danh hoặc dữ liệu mà khoảng trắng có ý nghĩa, việc tự ý loại bỏ ký tự có thể làm thay đổi dữ liệu người gọi.

### 3.2. Dùng Objects.requireNonNull cho tham số bắt buộc

Khi một tham số tham chiếu bắt buộc phải có giá trị, **Objects.requireNonNull** biểu đạt ý định trực tiếp:

~~~~java
import java.util.Objects;

public void publish(Event event) {
    Objects.requireNonNull(event, "event");
    // Xử lý event sau khi đã xác nhận khác null.
}
~~~~

Phương thức trả lại chính tham chiếu không null, vì vậy có thể gán ngay khi cần:

~~~~java
this.repository = Objects.requireNonNull(repository, "repository");
~~~~

Nếu null là giá trị được chấp nhận và có ý nghĩa riêng, hãy ghi rõ trong hợp đồng và xử lý có chủ đích. Không dùng requireNonNull cho tham số được phép vắng mặt.

### 3.3. Optional chủ yếu dùng để biểu đạt kết quả có thể vắng mặt

**Optional<T>** thường phù hợp với giá trị trả về có thể không tồn tại:

~~~~java
Optional<Customer> findCustomer(CustomerId id);
~~~~

Người gọi phải xử lý trường hợp không có kết quả:

~~~~java
Customer customer = findCustomer(id)
        .orElseThrow(() -> new CustomerNotFoundException(id));
~~~~

Đối với tham số phương thức, hãy cân nhắc nhận trực tiếp kiểu miền và định nghĩa rõ null có được chấp nhận hay không. Dùng Optional làm tham số không tự động làm hợp đồng rõ hơn; nó có thể tạo thêm lớp bọc và cách gọi phức tạp. Không dùng **Optional.get()** mà không xác nhận có giá trị; các phương thức như **orElseThrow**, **orElse**, **orElseGet**, **ifPresent** thường diễn đạt ý định rõ hơn.

## 4. Kiểm tra giá trị theo từng loại dữ liệu

### 4.1. Kiểm tra miền giá trị số

Kiểu int hoặc long bảo đảm giá trị là số nguyên trong miền biểu diễn của kiểu, nhưng không bảo đảm giá trị có ý nghĩa nghiệp vụ. Ví dụ, số lượng khách phải lớn hơn 0 và không vượt giới hạn:

~~~~java
public void reserve(int guestCount) {
    if (guestCount < 1 || guestCount > 8) {
        throw new IllegalArgumentException(
                "guestCount must be between 1 and 8");
    }
}
~~~~

Kiểm tra cả giá trị biên, giá trị âm, số 0 và giá trị vượt giới hạn. Với số tiền hoặc tỷ lệ thập phân cần độ chính xác, hãy cân nhắc **BigDecimal** thay vì dùng double rồi so sánh bằng phép bằng tuyệt đối.

Phép toán số nguyên có thể tràn mà không tự ném exception. Khi hợp đồng yêu cầu phát hiện tràn, dùng các phương thức chính xác của Math:

~~~~java
int total;
try {
    total = Math.addExact(currentTotal, newAmount);
} catch (ArithmeticException exception) {
    throw new IllegalArgumentException("total is too large", exception);
}
~~~~

Các phương thức như **Math.addExact**, **subtractExact**, **multiplyExact** và **toIntExact** báo ArithmeticException nếu kết quả không biểu diễn được bằng kiểu đích. Chọn cách xử lý phù hợp với hợp đồng; không bỏ qua lỗi tràn nếu kết quả có thể ảnh hưởng đến tiền, giới hạn dung lượng hoặc quyền truy cập.

### 4.2. Kiểm tra chỉ số và đoạn dữ liệu

Một chỉ số hợp lệ phải nằm trong khoảng từ 0 đến length - 1. Java SE cung cấp các tiện ích kiểm tra trong **Objects**:

~~~~java
int checkedIndex = Objects.checkIndex(index, values.length);
~~~~

Với đoạn dữ liệu, có thể dùng **checkFromToIndex** hoặc **checkFromIndexSize**:

~~~~java
import java.util.Arrays;
import java.util.Objects;

static byte[] copySegment(byte[] source, int offset, int size) {
    Objects.requireNonNull(source, "source");
    Objects.checkFromIndexSize(offset, size, source.length);
    return Arrays.copyOfRange(source, offset, offset + size);
}
~~~~

**checkFromIndexSize** kiểm tra đoạn bắt đầu tại offset, có size phần tử và nằm trong phạm vi mảng. Dùng API này giúp tránh tự viết phép kiểm tra dễ sai do tràn số khi tính offset + size. Các phương thức kiểm tra chỉ số ném IndexOutOfBoundsException nếu phạm vi không hợp lệ.

Không cần kiểm tra lặp lại một điều kiện mà API được gọi đã bảo đảm theo hợp đồng của nó, trừ khi phương thức của bạn cần đưa ra loại lỗi hoặc thông điệp cụ thể hơn.

### 4.3. Kiểm tra collection

Với List, Set hoặc Map, hợp đồng nên xác định:

- Collection có được phép null hay không.
- Collection rỗng có hợp lệ không.
- Phần tử null có được phép không.
- Có giới hạn số lượng phần tử hay kích thước dữ liệu không.
- Thứ tự và phần tử trùng lặp có ý nghĩa không.
- Phương thức có giữ tham chiếu hoặc thay đổi collection của người gọi không.

Ví dụ, API yêu cầu danh sách mã quyền không null, không chứa null và không được vượt quá 20 phần tử:

~~~~java
import java.util.List;
import java.util.Objects;

static List<String> validatePermissions(List<String> permissions) {
    List<String> snapshot = List.copyOf(
            Objects.requireNonNull(permissions, "permissions"));

    if (snapshot.size() > 20) {
        throw new IllegalArgumentException(
                "at most 20 permissions are allowed");
    }

    for (String permission : snapshot) {
        if (permission.isBlank()) {
            throw new IllegalArgumentException(
                    "permission must not be blank");
        }
    }

    return snapshot;
}
~~~~

**List.copyOf** tạo một danh sách không sửa đổi được từ dữ liệu đầu vào và từ chối phần tử null. Việc giữ snapshot giúp phương thức làm việc với một tập phần tử riêng thay vì tiếp tục phụ thuộc vào collection mà người gọi có thể thay đổi.

Nếu collection có thể bị sửa đồng thời trong lúc sao chép, cần có quy ước đồng bộ hoặc kiểu dữ liệu đầu vào phù hợp. Việc sao chép không tự tạo ra snapshot nguyên tử cho mọi kiểu collection có thể thay đổi đồng thời.

### 4.4. Kiểm tra ngày và khoảng thời gian

Với kiểu ngày giờ trong java.time, hãy kiểm tra quan hệ giữa các giá trị thay vì nhận chuỗi ngày chưa được phân tích:

~~~~java
static void validatePeriod(LocalDate startDate, LocalDate endDate) {
    Objects.requireNonNull(startDate, "startDate");
    Objects.requireNonNull(endDate, "endDate");

    if (!endDate.isAfter(startDate)) {
        throw new IllegalArgumentException(
                "endDate must be after startDate");
    }
}
~~~~

Hợp đồng cần nói rõ khoảng thời gian có bao gồm ngày kết thúc hay không. Ví dụ, đặt chỗ thường dùng khoảng [startDate, endDate), trong đó ngày bắt đầu được tính còn ngày kết thúc là mốc trả phòng và không tính là một đêm lưu trú.

Không nên dùng chuỗi định dạng tự do ở sâu trong lớp nghiệp vụ. Hãy phân tích dữ liệu tại biên nhận dữ liệu, chuyển thành kiểu miền như LocalDate, Instant hoặc Duration, rồi truyền kiểu đã có ý nghĩa rõ ràng vào các phương thức nội bộ.

## 5. Thứ tự kiểm tra và bảo vệ dữ liệu đầu vào

### 5.1. Kiểm tra tại ranh giới tin cậy

Dữ liệu có thể đi vào phương thức từ nhiều nguồn: giao diện người dùng, HTTP request, tệp, biến môi trường, message queue, plugin hoặc thư viện bên ngoài. Không nên mặc định dữ liệu hợp lệ chỉ vì một lớp trước đó đã kiểm tra.

Một quy trình thường dùng:

1. Nhận dữ liệu tại ranh giới của hệ thống.
2. Phân tích cú pháp và chuẩn hóa theo quy tắc được công bố.
3. Tạo bản sao phòng vệ nếu đầu vào có thể bị thay đổi.
4. Kiểm tra kiểu, null, miền giá trị, kích thước và các quan hệ giữa trường.
5. Kiểm tra lại điều kiện sát thời điểm thực hiện thao tác nhạy cảm nếu dữ liệu hoặc trạng thái có thể thay đổi.
6. Thực hiện nghiệp vụ và trả kết quả theo hợp đồng.

Oracle Secure Coding Guidelines nhấn mạnh việc kiểm tra dữ liệu không tin cậy trước khi sử dụng, kiểm tra lại theo ngữ cảnh trước thao tác nhạy cảm và thực hiện validation sau defensive copy khi đầu vào có thể thay đổi. Xem [Guideline 5-1: Validate inputs](https://www.oracle.com/java/technologies/javase/seccodeguide.html#input-validation) và [Guideline 6-3: Create safe copies of mutable and subclassable input values](https://www.oracle.com/java/technologies/javase/seccodeguide.html).

### 5.2. Sao chép dữ liệu mutable trước khi dựa vào kết quả kiểm tra

Mảng và collection có thể thay đổi sau khi được truyền vào phương thức. Nếu kiểm tra một đối tượng rồi sử dụng chính tham chiếu đó trong thời gian dài, một thành phần khác có thể thay đổi dữ liệu giữa hai thời điểm.

Ví dụ với mảng:

~~~~java
static int[] normalizeScores(int[] input) {
    Objects.requireNonNull(input, "input");
    int[] snapshot = input.clone();

    for (int score : snapshot) {
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException("score out of range");
        }
    }

    return snapshot;
}
~~~~

Phương thức kiểm tra và trả về bản sao riêng. Người gọi có thể thay đổi mảng gốc sau đó mà không làm thay đổi snapshot đã được xác nhận. Với collection, có thể dùng **List.copyOf**, **Set.copyOf** hoặc **Map.copyOf** khi ngữ nghĩa của collection phù hợp với yêu cầu.

Sao chép nông chỉ tách cấu trúc ngoài. Nếu phần tử là đối tượng mutable, tham chiếu đến từng đối tượng vẫn được chia sẻ. Khi hợp đồng yêu cầu dữ liệu độc lập hoàn toàn, phải thiết kế cách sao chép đối tượng hoặc chuyển dữ liệu thành kiểu bất biến phù hợp.

### 5.3. Phân biệt validation, normalization và sanitization

Ba thao tác này có mục tiêu khác nhau:

| Thao tác | Mục đích | Ví dụ |
| --- | --- | --- |
| Validation | Xác định dữ liệu có đáp ứng quy tắc không | Từ chối số khách bằng 0 |
| Normalization | Đưa dữ liệu tương đương về dạng chuẩn theo hợp đồng | Loại bỏ khoảng trắng đầu/cuối của mã khách hàng nếu nghiệp vụ cho phép |
| Sanitization hoặc encoding theo ngữ cảnh | Xử lý dữ liệu trước khi đưa vào một ngữ cảnh có quy tắc đặc biệt | Encode dữ liệu khi hiển thị HTML hoặc dùng parameter binding khi truy vấn SQL |

Không dùng việc loại bỏ ký tự tùy tiện để biến dữ liệu sai thành dữ liệu có vẻ hợp lệ. Với định dạng như URL, đường dẫn hoặc tên tài nguyên, hãy dùng API phân tích phù hợp rồi áp dụng quy tắc nghiệp vụ trên kết quả đã phân tích. Regex đơn giản không thay thế được việc hiểu cú pháp và ngữ nghĩa của định dạng.

Validation cũng không thay thế encoding đầu ra. Một chuỗi hợp lệ làm tên hiển thị vẫn có thể chứa ký tự cần encode khi đưa vào HTML; một chuỗi hợp lệ theo cú pháp cũng chưa chắc được phép dùng làm tên bảng hoặc biểu thức SQL.

### 5.4. Kiểm tra giới hạn tài nguyên

Dữ liệu đầu vào có thể hợp lệ về cú pháp nhưng quá lớn so với khả năng xử lý. Hợp đồng cần xác định giới hạn phù hợp với nghiệp vụ:

- Số lượng phần tử tối đa của collection.
- Độ dài chuỗi tối đa.
- Kích thước tệp hoặc payload tối đa.
- Số trang, số bản ghi hoặc độ sâu lồng nhau tối đa.
- Thời gian chờ và số lần thử lại tối đa.

Kiểm tra giới hạn trước khi cấp phát mảng lớn, giải nén, parse hoặc thực hiện phép tính tốn tài nguyên. Khi tính kích thước từ nhiều tham số, kiểm tra tràn số và giới hạn kết quả. Việc chỉ kiểm tra một giá trị đầu vào riêng lẻ có thể không đủ nếu tổ hợp các giá trị tạo ra mức tiêu thụ lớn.

## 6. Chọn exception phù hợp với hợp đồng

Exception là một phần của cách phương thức thông báo rằng không thể hoàn thành thao tác theo hợp đồng. Hãy chọn loại exception dựa trên nguyên nhân và trách nhiệm của bên gọi.

| Trường hợp | Loại exception thường phù hợp | Ví dụ |
| --- | --- | --- |
| Tham số bắt buộc là null | NullPointerException | Objects.requireNonNull(request, "request") |
| Giá trị có kiểu đúng nhưng nằm ngoài miền hợp lệ | IllegalArgumentException | Số lượng âm hoặc ngày kết thúc trước ngày bắt đầu |
| Chỉ số hoặc đoạn dữ liệu vượt phạm vi | IndexOutOfBoundsException | Objects.checkIndex(index, length) |
| Trạng thái hiện tại không cho phép thao tác | IllegalStateException | Gọi complete() khi giao dịch đã đóng |
| Lỗi môi trường mà caller có thể xử lý | Checked exception hoặc exception miền được công bố | Lỗi đọc tệp, lỗi giao tiếp hoặc lỗi lưu trữ |
| Lỗi không thể tiếp tục một cách an toàn | Exception phù hợp được truyền lên tầng xử lý | Lỗi cấu hình hoặc lỗi hệ thống cần xử lý ở tầng điều phối |

Không dùng IllegalArgumentException cho mọi lỗi. Ví dụ, một yêu cầu có cấu trúc hợp lệ nhưng tài khoản không tồn tại là một kết quả nghiệp vụ khác với tham số sai định dạng. Có thể dùng exception miền hoặc kiểu kết quả chuyên biệt nếu người gọi cần phân biệt các tình huống.

### 6.1. Checked và unchecked exception

Checked exception được khai báo trong mệnh đề **throws** và buộc caller phải xử lý hoặc tiếp tục khai báo. Chúng phù hợp khi caller có khả năng quyết định cách phục hồi từ điều kiện thất bại đã được dự kiến.

Unchecked exception gồm RuntimeException và các lớp con. Chúng thường biểu đạt tham số không hợp lệ, trạng thái không phù hợp hoặc lỗi lập trình mà caller không thể khắc phục bằng một nhánh xử lý thông thường.

Không biến mọi lỗi thành unchecked chỉ để giảm khai báo. Ngược lại, cũng không khai báo checked exception cho mọi trường hợp vi phạm tiền điều kiện. Hãy xem caller cần biết điều gì và có thể làm gì khi lỗi xảy ra.

### 6.2. Không nuốt exception hoặc trả giá trị giả

Đoạn mã sau che giấu lỗi:

~~~~java
int parseQuantity(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException exception) {
        return 0;
    }
}
~~~~

Nếu 0 là một giá trị hợp lệ, caller không thể phân biệt dữ liệu nhập là 0 với dữ liệu sai định dạng. Hãy truyền lỗi lên hoặc chuyển đổi sang kiểu kết quả có biểu đạt thất bại rõ ràng:

~~~~java
int parseQuantity(String text) {
    Objects.requireNonNull(text, "text");
    int quantity = Integer.parseInt(text);

    if (quantity < 0) {
        throw new IllegalArgumentException("quantity must not be negative");
    }
    return quantity;
}
~~~~

Nếu cần bổ sung ngữ cảnh, hãy giữ nguyên nguyên nhân bằng cách truyền exception gốc vào constructor của exception mới. Không catch rồi bỏ qua, không chỉ log rồi tiếp tục như thể thao tác đã thành công.

### 6.3. Không dùng assert để xác thực dữ liệu bên ngoài

**assert** phù hợp để diễn đạt giả định nội bộ trong quá trình phát triển và gỡ lỗi. Assertion có thể bị tắt khi JVM chạy mà không bật assertion, vì vậy không dùng assert làm cơ chế bắt buộc để bảo vệ API công khai hoặc dữ liệu không tin cậy.

~~~~java
// Không dùng cho hợp đồng đầu vào công khai:
assert amount.signum() > 0;

// Kiểm tra thực sự luôn được thực thi:
if (amount.signum() <= 0) {
    throw new IllegalArgumentException("amount must be positive");
}
~~~~

## 7. Công bố hợp đồng bằng Javadoc

Javadoc giúp người gọi hiểu tiền điều kiện, hậu điều kiện và lỗi mà không phải đọc phần triển khai. Với phương thức public hoặc API dùng chung, nên mô tả:

- Ý nghĩa và đơn vị của từng tham số.
- Tham số nào có thể null, collection có được rỗng không.
- Phạm vi giá trị, quy tắc giữa nhiều tham số và giới hạn dữ liệu.
- Giá trị trả về, trường hợp không có kết quả và quyền sở hữu dữ liệu trả về.
- Tác dụng phụ và trạng thái mà phương thức có thể thay đổi.
- Các exception có thể được caller xử lý.

Ví dụ:

~~~~java
/**
 * Calculates the total price for a requested number of tickets.
 *
 * @param unitPrice non-null price for one ticket; must not be negative
 * @param quantity number of tickets; must be between 1 and 100
 * @return the exact product of unitPrice and quantity
 * @throws NullPointerException if unitPrice is null
 * @throws IllegalArgumentException if unitPrice is negative or
 *         quantity is outside the supported range
 */
public BigDecimal calculateTotal(BigDecimal unitPrice, int quantity) {
    Objects.requireNonNull(unitPrice, "unitPrice");

    if (unitPrice.signum() < 0) {
        throw new IllegalArgumentException("unitPrice must not be negative");
    }
    if (quantity < 1 || quantity > 100) {
        throw new IllegalArgumentException("quantity must be between 1 and 100");
    }

    return unitPrice.multiply(BigDecimal.valueOf(quantity));
}
~~~~

Mô tả hậu điều kiện cần chính xác. Nếu phương thức có làm tròn, hãy nêu rõ scale và rounding mode; ví dụ trên không làm tròn mà trả về kết quả nhân BigDecimal. Javadoc phải theo kịp mã nguồn, nếu không hợp đồng trên tài liệu sẽ trở nên sai lệch.

## 8. Ví dụ tổng hợp: kiểm tra yêu cầu đặt chỗ

Ví dụ dưới đây sử dụng record để biểu diễn yêu cầu, kiểm tra bất biến khi tạo record và công bố hợp đồng cho phương thức dịch vụ. Phần xử lý tạo mã đặt chỗ chỉ minh họa việc trả kết quả; ứng dụng thực tế sẽ bổ sung kiểm tra tình trạng còn chỗ và lưu dữ liệu trong một giao dịch phù hợp.

~~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

record BookingRequest(
        String customerId,
        LocalDate startDate,
        LocalDate endDate,
        int guestCount,
        List<String> options) {

    BookingRequest {
        customerId = Objects.requireNonNull(customerId, "customerId").strip();
        startDate = Objects.requireNonNull(startDate, "startDate");
        endDate = Objects.requireNonNull(endDate, "endDate");
        options = List.copyOf(Objects.requireNonNull(options, "options"));

        if (customerId.isBlank()) {
            throw new IllegalArgumentException("customerId must not be blank");
        }
        if (!endDate.isAfter(startDate)) {
            throw new IllegalArgumentException("endDate must be after startDate");
        }
        if (guestCount < 1 || guestCount > 8) {
            throw new IllegalArgumentException("guestCount must be between 1 and 8");
        }
        if (options.size() > 5) {
            throw new IllegalArgumentException("at most 5 options are allowed");
        }
        for (String option : options) {
            if (option.isBlank()) {
                throw new IllegalArgumentException("option must not be blank");
            }
        }
    }
}

record BookingReceipt(
        UUID reference,
        String customerId,
        LocalDate startDate,
        LocalDate endDate,
        int guestCount) {
}

final class BookingService {

    /**
     * Creates a booking receipt for a validated request.
     *
     * @param request non-null booking request
     * @return receipt containing a new booking reference
     * @throws NullPointerException if request is null
     */
    public BookingReceipt createBooking(BookingRequest request) {
        Objects.requireNonNull(request, "request");

        // A real service would check availability and persist atomically here.
        return new BookingReceipt(
                UUID.randomUUID(),
                request.customerId(),
                request.startDate(),
                request.endDate(),
                request.guestCount());
    }
}

public class BookingDemo {
    public static void main(String[] args) {
        BookingRequest request = new BookingRequest(
                "customer-1024",
                LocalDate.of(2026, 12, 10),
                LocalDate.of(2026, 12, 12),
                2,
                List.of("breakfast", "late-checkout"));

        BookingReceipt receipt = new BookingService().createBooking(request);
        System.out.println(receipt);
    }
}
~~~~

Trong ví dụ:

1. Record nhận dữ liệu và xác nhận các tham số bắt buộc không null.
2. customerId được chuẩn hóa theo hợp đồng bằng strip; chuỗi rỗng sau chuẩn hóa bị từ chối.
3. Khoảng ngày được kiểm tra theo quan hệ giữa startDate và endDate.
4. guestCount và số lượng options được giới hạn theo chính sách.
5. List.copyOf tạo snapshot không sửa đổi được và từ chối phần tử null.
6. Phương thức dịch vụ xác nhận request khác null trước khi sử dụng.
7. Javadoc nêu điều kiện và lỗi mà caller cần biết.

Ví dụ cho thấy kiểm tra đầu vào có thể nằm ở nhiều lớp. Record bảo vệ tính hợp lệ cơ bản của dữ liệu yêu cầu; dịch vụ kiểm tra tham số tại ranh giới phương thức và chịu trách nhiệm các quy tắc phụ thuộc trạng thái hệ thống như tình trạng còn chỗ.

## 9. Kiểm thử hợp đồng phương thức

Kiểm thử nên dựa trên hợp đồng đã công bố. Với mỗi phương thức, xác định dữ liệu hợp lệ, dữ liệu không hợp lệ và hậu điều kiện cần quan sát.

| Nhóm kiểm thử | Trường hợp ví dụ | Kết quả cần xác nhận |
| --- | --- | --- |
| Giá trị hợp lệ | Số khách bằng 1 hoặc 8 | Chấp nhận nếu đúng giới hạn |
| Biên dưới | Số khách bằng 0 | Ném exception đã công bố |
| Biên trên | Số khách bằng 9 | Ném exception đã công bố |
| Null | Tham số bắt buộc bằng null | Ném NullPointerException tại ranh giới đã xác định |
| Chuỗi rỗng | customerId là chuỗi rỗng | Bị từ chối |
| Chuỗi khoảng trắng | customerId chỉ có khoảng trắng | Bị từ chối sau chuẩn hóa |
| Quan hệ tham số | endDate bằng startDate | Bị từ chối |
| Collection | Danh sách có phần tử null hoặc quá nhiều phần tử | Bị từ chối theo hợp đồng |
| Dữ liệu mutable | Người gọi thay đổi collection gốc sau khi tạo request | Snapshot đã lưu không thay đổi |
| Tràn số | Tổng vượt miền biểu diễn của kiểu | Phương thức phát hiện tràn hoặc áp dụng chính sách đã công bố |
| Tác dụng phụ | Thao tác thất bại giữa chừng | Trạng thái không bị cập nhật một phần trái với hợp đồng |

Ngoài kiểm thử từng trường hợp, cần kiểm tra các tổ hợp tham số có quan hệ với nhau. Ví dụ, startDate hợp lệ riêng và endDate hợp lệ riêng nhưng tổ hợp có thể không hợp lệ nếu endDate không sau startDate.

Với phương thức có tác dụng phụ, kiểm tra cả trạng thái trước và sau khi gọi. Một phương thức trả exception không có nghĩa là mọi thay đổi trước đó tự động được hoàn tác; tính nguyên tử cần được bảo đảm bằng thiết kế giao dịch hoặc cơ chế thích hợp.

## 10. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Không công bố null có được phép hay không | Caller đoán cách xử lý và dễ gặp NullPointerException ở vị trí khó truy vết | Ghi rõ null policy và kiểm tra ngay tại ranh giới |
| Dùng một kiểu String cho mọi loại định danh | Truyền nhầm mã khách hàng, mã đơn hàng hoặc trạng thái | Tạo kiểu miền hoặc enum khi có ý nghĩa riêng |
| Chỉ kiểm tra kiểu dữ liệu mà không kiểm tra miền giá trị | Số âm hoặc giá trị quá lớn vẫn đi vào nghiệp vụ | Kiểm tra range, giới hạn và quan hệ giữa các tham số |
| Tin rằng lớp trước đã kiểm tra dữ liệu | Dữ liệu có thể thay đổi hoặc được gọi từ đường khác | Kiểm tra theo ngữ cảnh tại điểm sử dụng |
| Kiểm tra collection rồi giữ nguyên tham chiếu mutable | Dữ liệu có thể thay đổi sau khi kiểm tra | Sao chép phòng vệ rồi kiểm tra snapshot |
| Tính offset + size mà không xét tràn số | Phạm vi sai có thể vượt qua kiểm tra | Dùng Objects.checkFromIndexSize |
| Dùng assert để kiểm tra tham số public | Kiểm tra có thể không chạy khi assertion bị tắt | Dùng kiểm tra thực thi và exception phù hợp |
| Catch exception rồi trả giá trị mặc định | Che giấu dữ liệu sai và lỗi thực thi | Truyền lỗi hoặc dùng kiểu kết quả biểu đạt thất bại |
| Không ghi rõ tác dụng phụ | Caller không biết phương thức có sửa trạng thái hoặc dữ liệu đầu vào không | Mô tả side effect và quyền sở hữu dữ liệu |
| Trả về tham chiếu mutable nội bộ | Caller có thể sửa trạng thái của đối tượng | Trả bản sao hoặc cấu trúc không sửa đổi được |
| Gộp nhiều quy tắc vào một boolean | Lệnh gọi khó đọc và khó mở rộng | Dùng enum, kiểu yêu cầu hoặc phương thức có tên cụ thể |

## 11. Checklist thiết kế một phương thức

- [ ] Tên phương thức thể hiện hành động hoặc kết quả.
- [ ] Tên và kiểu tham số cho biết đúng ý nghĩa, đơn vị và mức trừu tượng.
- [ ] Hợp đồng xác định tham số bắt buộc, null policy và dữ liệu rỗng.
- [ ] Các miền giá trị, giới hạn kích thước và quan hệ giữa các tham số được nêu rõ.
- [ ] Kiểu dữ liệu được chọn để loại bỏ những trạng thái không hợp lệ có thể biểu đạt bằng kiểu.
- [ ] Dữ liệu mutable được sao chép nếu phương thức cần một snapshot ổn định.
- [ ] Validation được thực hiện tại ranh giới tin cậy và sát thao tác nhạy cảm khi cần.
- [ ] Exception phản ánh đúng nguyên nhân và được công bố cho caller.
- [ ] Tác dụng phụ, hậu điều kiện và quyền sở hữu dữ liệu trả về được mô tả.
- [ ] Có kiểm thử cho giá trị hợp lệ, null, biên, sai miền, tràn số và dữ liệu thay đổi.

Thiết kế hợp đồng phương thức tốt bắt đầu từ việc làm rõ người gọi phải cung cấp gì và có thể kỳ vọng gì. Khi chữ ký, kiểu dữ liệu, kiểm tra đầu vào, exception và tài liệu cùng diễn đạt một quy tắc, phương thức sẽ dễ sử dụng và dễ bảo vệ hơn. Java 27 cung cấp các kiểu và tiện ích cần thiết để biến nhiều điều kiện thành kiểm tra rõ ràng, có thể thực thi và kiểm thử.
