# Đặt tên theo ý nghĩa, đơn vị và phạm vi sử dụng

## 1. Vì sao tên gọi là một phần của chất lượng mã nguồn?

Trong một hệ thống đang phát triển, lập trình viên dành nhiều thời gian đọc, đối chiếu và sửa mã có sẵn. Một biến có tên `t`, một phương thức tên `process()` hoặc một cờ tên `flag` có thể hoàn toàn hợp lệ về cú pháp, nhưng buộc người đọc phải tra ngược nhiều câu lệnh để đoán ý định. Ngược lại, những tên như `paymentTimeout`, `remainingInventory` hay `hasUnpaidInvoices` giúp truyền tải một phần hợp đồng ngay tại chỗ sử dụng.

Trong module `CODE_QUALITY_FUNDAMENTALS`, chúng ta tìm hiểu **những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Thuộc chương **Khả năng đọc**, bài này tập trung vào một kỹ năng có tác động lớn tới cả ba thuộc tính đó: **đặt tên dựa trên ý nghĩa nghiệp vụ, đơn vị đo và phạm vi sử dụng**.

Tên tốt không thể thay thế thuật toán đúng, kiểu dữ liệu phù hợp hoặc kiểm thử. Nhưng tên thiếu chính xác có thể dẫn tới lỗi thật: coi thời gian mili giây là giây, hiểu số tiền đã gồm thuế là chưa gồm thuế, dùng biến tổng số người dùng khi lẽ ra chỉ tính người dùng đang hoạt động, hoặc gọi một phương thức có tác dụng phụ vì tưởng nó chỉ truy vấn dữ liệu.

Sau bài học, người học có thể:

- Chọn tên thể hiện **khái niệm, điều kiện, hành động và kết quả**, thay vì chỉ phản ánh kiểu dữ liệu hay chi tiết triển khai.
- Diễn đạt **đơn vị, mốc thời gian, tỷ lệ, tiền tệ và quy ước biên** để hạn chế nhầm lẫn.
- Điều chỉnh mức độ cụ thể của tên theo **phạm vi sống, số nơi sử dụng và mức độ công khai của hợp đồng**.
- Áp dụng quy ước đặt tên Java nhất quán, nhận diện tên dễ gây hiểu lầm và cải thiện mã hiện có mà không vô tình phá vỡ API.
- Kiểm chứng tính dễ hiểu bằng ví dụ, kiểm thử và câu hỏi review thay vì chỉ dựa vào cảm giác rằng một tên "nghe hay".

## 2. Một tên hữu ích cần trả lời những câu hỏi nào?

Khi nhìn thấy một định danh, người đọc thường cần biết ít nhất ba điều:

1. **Ý nghĩa:** giá trị này đại diện cho khái niệm gì; phương thức thực hiện hành vi gì; kết quả có ý nghĩa nào?
2. **Đơn vị hoặc quy ước:** số lượng là cái gì, thời gian tính theo giây hay mili giây, tiền theo đồng hay đơn vị nhỏ nhất, tỷ lệ nằm trong khoảng `0..1` hay `0..100`?
3. **Phạm vi:** tên được hiểu trong một vòng lặp ba dòng, trong cả phương thức, qua nhiều lớp hay là một hợp đồng công khai được sử dụng bởi nhiều hệ thống?

Ví dụ, `count` có thể chấp nhận được trong một đoạn mã rất ngắn đã nói rõ đối tượng được đếm. Nhưng trong một lớp tính phí, `count` có thể là số kiện hàng, số người mua, số lần thử thanh toán hoặc số ngày thuê. Khi đó `itemCount`, `paymentAttemptCount` hay `rentalDayCount` làm giảm đáng kể khả năng hiểu nhầm.

| Tên | Vấn đề khi đọc | Tên rõ hơn trong một ngữ cảnh xác định |
| --- | --- | --- |
| `data` | Không biết dữ liệu gì và đã được xử lý đến bước nào | `validatedOrder`, `rawWebhookPayload` |
| `list` | Không biết phần tử thuộc tập hợp nào | `pendingInvoices`, `availableSeats` |
| `status` | Không biết trạng thái của đối tượng nào | `paymentStatus`, `shipmentStatus` |
| `time` | Không biết mốc thời gian hay khoảng thời gian, đơn vị nào | `createdAt`, `requestTimeout` |
| `amount` | Không biết tiền hay số lượng, đã bao gồm thuế chưa | `refundAmount`, `netAmount` |
| `check()` | Không biết kiểm tra điều kiện hay thay đổi trạng thái | `isEligibleForRefund()`, `validateOrder()` |
| `result` | Không biết kết quả đã hoàn thành, được chấp nhận hay thất bại | `reservationOutcome`, `validationErrors` |

Những tên "rõ hơn" trong bảng là **ví dụ theo từng ngữ cảnh**, không phải quy tắc đổi tên máy móc. Chẳng hạn, `validatedOrder` chỉ đúng khi đối tượng đã thực sự qua bước xác thực hoặc kiểm tra hợp lệ; đặt tên như vậy trước khi kiểm tra sẽ tạo ra sự bảo đảm giả.

## 3. Đặt tên theo ý nghĩa: dùng ngôn ngữ của bài toán

### 3.1. Gọi đúng khái niệm nghiệp vụ

Tên nên gắn với điều người dùng và hệ thống đang thực sự quan tâm. Nếu hệ thống quản lý đặt chỗ, `reservation`, `seat`, `holdExpiresAt` diễn đạt nghiệp vụ tốt hơn `record`, `item`, `date`. Nếu hệ thống quản lý thanh toán, cần phân biệt `authorizedAmount`, `capturedAmount`, `refundedAmount`; cả ba có thể cùng là `BigDecimal` nhưng ý nghĩa không giống nhau.

```java
// Người đọc phải suy từ phép tính ra ý nghĩa.
int a = orders.size();
int b = canceled.size();
int c = a - b;

// Người đọc thấy rõ điều được đếm (với giả định canceled là tập con của orders).
int totalOrderCount = orders.size();
int canceledOrderCount = canceledOrders.size();
int remainingOrderCount = totalOrderCount - canceledOrderCount;
```

Cần đọc đúng quy tắc thực tế: nếu một đơn có thể nằm trong nhiều tập hoặc `canceledOrders` chứa đơn ngoài danh sách ban đầu, phép trừ trên không bảo đảm đúng. **Tên diễn đạt giả định, còn cấu trúc dữ liệu và kiểm thử phải bảo vệ giả định đó.**

### 3.2. Tên phương thức là lời hứa về hành vi

Một tên phương thức tốt giúp caller biết nó **truy vấn**, **tính toán**, **kiểm tra** hay **thay đổi trạng thái**. So sánh:

```java
OrderResult process(Order order);
```

với các hành vi riêng biệt:

```java
ValidationResult validateOrder(Order order);
PriceQuote calculateOrderTotal(Order order);
ReservationResult reserveInventory(Order order);
PaymentResult capturePayment(PaymentRequest request);
```

Các phương thức trên không nhất thiết phải được tách nếu thực tế chỉ cần một thao tác nghiệp vụ duy nhất. Ý chính là **không dùng một động từ quá chung khi người gọi cần phân biệt các tác dụng cụ thể**.

Tên như `findCustomerById` thường gợi ý truy vấn; `deleteCustomer` gợi ý thay đổi trạng thái. Tuy vậy, tên không thể một mình bảo đảm việc truy vấn không có tác dụng phụ: hợp đồng, kiến trúc, giới hạn giao dịch và test vẫn cần xác nhận.

### 3.3. Tên boolean mô tả mệnh đề có thể đọc thành câu hỏi

Các tiền tố `is`, `has`, `can`, `should` thường làm mục đích cờ dễ hiểu hơn:

```java
boolean isActive;
boolean hasOutstandingBalance;
boolean canCancelReservation;
boolean shouldRetryRequest;
```

Một biểu thức như `if (canCancelReservation)` có thể đọc gần với ngôn ngữ tự nhiên. Tránh những tên quá chung hoặc phủ định lồng nhau:

```java
// Khó đọc: if (!notAllowed) nghĩa là gì?
boolean notAllowed = !hasPermission;
if (!notAllowed) {
    // ...
}

// Dễ đọc hơn:
boolean canEditInvoice = hasPermission;
if (canEditInvoice) {
    // ...
}
```

Đừng đổi một trạng thái nghiệp vụ có ba khả năng (`APPROVED`, `REJECTED`, `PENDING`) thành boolean chỉ để có tên ngắn. `isApproved` không biểu diễn được trạng thái chờ; dùng enum hoặc kết quả có kiểu để giữ trọn ý nghĩa.

### 3.4. Tên phải phân biệt giá trị thô, đã kiểm tra và đã xử lý

Ở ranh giới hệ thống, sự khác biệt giữa `rawInput`, `parsedRequest`, `validatedCommand` và `persistedOrder` thường liên quan trực tiếp tới độ tin cậy. Những tên này có ích khi thực sự tồn tại các bước chuyển đổi tương ứng:

```java
String rawEmailAddress = request.email();
String normalizedEmailAddress = normalizeEmail(rawEmailAddress);
```

Nhưng `normalizedEmailAddress` vẫn chưa đồng nghĩa với `verifiedEmailAddress`: chuẩn hóa định dạng không chứng minh người dùng sở hữu địa chỉ email. Việc đổi tên cần phản ánh **cam kết đã được thực thi**, không nâng cấp ý nghĩa bằng lời.

## 4. Đặt tên theo đơn vị: tránh lỗi nhìn hợp lý nhưng tính sai

### 4.1. Thời gian: mốc, khoảng và đơn vị

Một trong những lỗi tên gọi phổ biến là lưu thời gian dưới kiểu số nguyên mà không ghi rõ đơn vị:

```java
long timeout = 5000;
long started = System.currentTimeMillis();
```

`timeout` có nghĩa là 5.000 giây hay 5.000 mili giây? `started` là thời điểm bắt đầu dưới dạng epoch milliseconds hay số lượng tick của đồng hồ đơn điệu? Không có hợp đồng rõ, người khác rất dễ tạo lỗi khi chuyển giá trị giữa các API.

Nếu vẫn cần kiểu số ở ranh giới, đặt tên có đơn vị:

```java
long requestTimeoutMillis = 5_000;
long requestStartedAtEpochMillis = System.currentTimeMillis();
```

Ở lớp nghiệp vụ Java, có thể dùng kiểu có ngữ nghĩa mạnh hơn:

```java
import java.time.Duration;
import java.time.Instant;

Duration requestTimeout = Duration.ofSeconds(5);
Instant requestStartedAt = Instant.now();
```

`Duration` biểu diễn **khoảng thời gian**, `Instant` biểu diễn **mốc thời gian tuyệt đối**. Tên `requestTimeoutMillis` không cần thiết khi biến đã có kiểu `Duration`, vì kiểu dữ liệu đã mang ý nghĩa đơn vị; `requestTimeout` là đủ rõ. Ngược lại, `requestStartedAt` tốt hơn `requestTime` vì `At` cho biết đó là mốc.

Với đo **thời gian thực thi**, nên dùng nguồn thời gian đơn điệu như `System.nanoTime()` để tính chênh lệch; đồng hồ hệ thống (`System.currentTimeMillis()` hoặc `Instant.now()`) có thể được điều chỉnh. Đừng dùng số tick từ `nanoTime()` như một mốc lịch để lưu trữ hoặc trao đổi giữa các tiến trình.

| Ý nghĩa | Tên gợi ý | Kiểu hoặc quy ước phù hợp |
| --- | --- | --- |
| Thời điểm tạo bản ghi | `createdAt` | `Instant` (thường lưu UTC) |
| Ngày sinh không gắn giờ | `birthDate` | `LocalDate` |
| Khoảng tối đa để kết nối | `connectionTimeout` | `Duration` |
| Số mili giây ở API chỉ nhận `long` | `connectionTimeoutMillis` | `long`, ghi rõ đơn vị |
| Giá trị tick phục vụ đo thời lượng | `startedAtNanos` | `long` từ `System.nanoTime()` |
| Ngày hết hạn theo lịch địa phương | `expiryDate` | `LocalDate`, phải xác định múi giờ khi chuyển thành mốc |

### 4.2. Tiền tệ: số tiền, đơn vị nhỏ nhất, giá trước/sau thuế

Đoạn mã `long amount = 1500;` không cho biết đó là 1.500 VND, 1.500 USD hay 1.500 cent. Với tiền, cần làm rõ **đơn vị tiền tệ, đơn vị biểu diễn và ngữ nghĩa nghiệp vụ**:

```java
long refundAmountCents = 1_500; // 15.00 USD nếu hệ thống dùng USD cents.
```

Nếu hệ thống hỗ trợ nhiều đồng tiền, chỉ đặt hậu tố `Cents` là chưa đủ vì mỗi loại tiền có quy tắc đơn vị nhỏ nhất khác nhau. Có thể dùng một kiểu `Money` chứa cả `amount` và `currency`, hoặc một mô hình đã chuẩn hóa phù hợp với nghiệp vụ. Khi dùng `BigDecimal`, cần quy định **currency, scale, rounding** và tránh tính toán tiền thập phân bằng `double` nếu đòi hỏi độ chính xác thập phân.

Tên `subtotalBeforeTax`, `taxAmount`, `totalAfterTax`, `capturedAmount` giúp người đọc nhận ra các phép tính không thể thay thế cho nhau. Tránh gọi hai biến là `price1` và `price2` khi thực tế một giá chưa áp dụng chiết khấu và một giá đã áp dụng chiết khấu.

### 4.3. Tỷ lệ, phần trăm và các đơn vị khác

```java
double discountRate = 0.15;   // Quy ước: tỷ lệ trong [0, 1].
double discountPercent = 15;  // Quy ước: phần trăm trong [0, 100].
```

Hai giá trị khác nhau 100 lần nhưng có thể biểu thị cùng mức giảm giá 15%. `discount` không tự thể hiện quy ước này. Tương tự, `speedKph`, `distanceMeters`, `fileSizeBytes`, `temperatureCelsius` và `weightGrams` hữu ích khi API buộc dùng kiểu số sơ cấp. Với các phép chuyển đổi phức tạp, dùng kiểu đơn vị hoặc đối tượng giá trị có kiểm tra sẽ an toàn hơn việc chỉ dựa vào tên.

**Tính nhất quán rất quan trọng:** đừng để một phương thức nhận `timeoutSeconds` trong khi lớp gọi truyền `timeoutMillis` vì cả hai cùng là `long`. Ở ranh giới bắt buộc dùng số nguyên, kiểm thử chuyển đổi đơn vị và điều kiện biên phải đi cùng hợp đồng.

## 5. Đặt tên theo phạm vi: càng nhiều người thấy, càng cần nói rõ

Một định danh trong vòng lặp ba dòng có **ngữ cảnh rất gần**. Một phương thức public trong thư viện có thể được gọi từ hàng trăm nơi, nên cần tên tự chứa nhiều thông tin hơn.

| Phạm vi | Đặc điểm khi đọc | Cách chọn tên |
| --- | --- | --- |
| Biến cục bộ, sống vài dòng | Ngữ cảnh nằm ngay bên cạnh | Có thể ngắn nhưng phải đủ phân biệt khái niệm |
| Biến trong phương thức dài | Người đọc phải giữ thông tin trong đầu lâu hơn | Ưu tiên tên có chủ thể, trạng thái và đơn vị rõ |
| Trường của lớp | Được dùng bởi nhiều phương thức | Nêu chính xác vai trò bền vững của dữ liệu |
| Tham số phương thức | Người đọc phải hiểu hợp đồng và giá trị caller truyền | Tránh `x`, `arg`, `n` khi chúng đại diện cho các quy tắc khác nhau |
| Public API / interface / sự kiện | Có nhiều caller và phiên bản khác nhau | Chọn thuật ngữ ổn định, không gắn quá chặt với triển khai |
| Lớp hoặc module | Định hướng trách nhiệm ở quy mô lớn | Tên phản ánh miền nghiệp vụ và ranh giới trách nhiệm |

### 5.1. Tên ngắn không phải lúc nào cũng sai

```java
for (int i = 0; i < values.size(); i++) {
    // i là chỉ số trong một vòng lặp rất ngắn.
    sum += values.get(i);
}
```

Ở đây `i` có thể đủ rõ. Nhưng nếu cùng phương thức có nhiều chỉ số lồng nhau, hoặc các biến được dùng xa nơi khởi tạo, `itemIndex`, `rowIndex`, `columnIndex` có thể làm giảm nhầm lẫn.

Với phép biến đổi đơn giản dùng lambda, `invoice -> invoice.isOverdue()` thường rõ hơn `x -> x.isOverdue()`. Tuy nhiên, lặp lại những phần đã được ngữ cảnh xác định có thể khiến tên dài một cách vô ích: trong `InvoiceRepository`, tên `findInvoiceByInvoiceId` đôi khi có thể rút còn `findById` nếu hợp đồng và kiểu tham số đã chỉ rõ chủ thể.

### 5.2. Tránh che khuất biến và dùng lại tên cho nhiều ý nghĩa

```java
private Duration timeout;

public void configure(Duration timeout) {
    this.timeout = timeout;
}
```

Việc tham số có cùng tên với trường trong Java có thể chấp nhận được vì `this.timeout` phân biệt rõ. Nhưng việc tạo một biến `timeout` cục bộ khác với đơn vị hoặc ý nghĩa khác ngay trong phương thức dễ gây nhầm lẫn. Đừng dùng cùng một tên cho ba giai đoạn dữ liệu có quy tắc khác nhau.

### 5.3. Tên public là một phần của cam kết tương thích

Đổi `calculateTotal()` thành `computeTotal()` trong mã nội bộ có thể chỉ là refactor. Nhưng nếu đó là phương thức public của thư viện đang được sử dụng bên ngoài, việc đổi tên có thể phá **tương thích mã nguồn hoặc nhị phân**. Với API HTTP, tên trường JSON hoặc query parameter cũng là hợp đồng; đổi tên có thể khiến client cũ không đọc được dữ liệu dù triển khai nội bộ đã được cải thiện.

Khi tên cũ gây hiểu lầm nhưng đã được sử dụng rộng, cân nhắc thêm API mới có tên chính xác, giữ adapter tương thích, đánh dấu API cũ deprecated, đo mức sử dụng và có lộ trình chuyển đổi. Không tự ý phá hợp đồng chỉ vì tên mới nghe hợp lý hơn.

## 6. Quy ước đặt tên Java và tính nhất quán trong dự án

Java có các quy ước phổ biến giúp người đọc nhận biết loại định danh trước khi xem khai báo:

| Thành phần | Quy ước phổ biến | Ví dụ |
| --- | --- | --- |
| Class / record / interface / enum | `UpperCamelCase` | `InvoiceService`, `PaymentOutcome`, `CustomerId` |
| Method và biến | `lowerCamelCase` | `calculateNetAmount`, `retryCount` |
| Hằng số bất biến có ý nghĩa hằng | `UPPER_SNAKE_CASE` | `MAX_RETRY_ATTEMPTS`, `DEFAULT_TIMEOUT` |
| Package | Chữ thường, tên có ý nghĩa theo miền | `com.example.billing.invoice` |
| Tên boolean | Mệnh đề đọc được | `isExpired`, `hasPermission`, `canRetry` |
| Tên tập hợp | Gợi ý nhiều phần tử | `pendingOrders`, `customerIds` |
| Tên hành động | Động từ và đối tượng | `issueRefund`, `loadInvoice`, `validateRequest` |
| Tên loại lỗi | Nêu điều kiện cụ thể | `InsufficientBalanceException`, `InvalidOrderException` |

Một hằng số số nguyên như `MAX_RETRY_ATTEMPTS = 3` cần mô tả **số lần thử tổng cộng hay số lần thử lại sau lượt đầu**. Nếu là số lần retry thêm, `MAX_ADDITIONAL_RETRIES` có thể chính xác hơn. Đổi tên mà không xem cách vòng lặp đếm có thể giữ nguyên lỗi ranh giới.

Quy ước **không thay thế từ vựng nghiệp vụ**. Nếu toàn bộ hệ thống dùng `customer`, một lớp mới tên `ClientManager` có thể gây hiểu nhầm rằng `client` là một đối tượng khác. Hãy tạo và duy trì một bảng thuật ngữ chung (*ubiquitous language*) cho những khái niệm dễ bị dùng lẫn như `order`/`reservation`, `payment`/`settlement`, `active`/`enabled` và `amount`/`balance`.

Tránh viết tắt không phổ biến như `cstmr`, `pmtSt`, `flg`; viết tắt đã thành thuật ngữ được mọi thành viên hiểu (chẳng hạn `HTTP`, `URL`, `ID`) có thể chấp nhận theo quy ước của dự án. Sự nhất quán với codebase và hệ sinh thái Java thường quan trọng hơn sở thích cá nhân về cách viết tắt.

## 7. Ví dụ Java: từ `check(long, long)` đến một hợp đồng thời gian rõ ràng

Giả sử hệ thống đặt hàng cho phép khách nhận hàng trong một khoảng thời gian kể từ lúc nhân viên đánh dấu **hàng đã sẵn sàng**. Quy tắc nghiệp vụ: **tại đúng thời điểm hết hạn, cửa sổ nhận hàng được coi là đã đóng**.

### 7.1. Cách viết khó đọc và dễ nhầm đơn vị

```java
public boolean check(long t, long n) {
    return System.currentTimeMillis() - t >= n;
}
```

Mã trên không nói rõ `t` là thời điểm nào, `n` tính theo giây hay mili giây, `check` trả về `true` có nghĩa là hết hạn hay vẫn còn hiệu lực. Nó còn lấy đồng hồ hệ thống trực tiếp, khiến việc tạo kiểm thử đúng tại ranh giới khó hơn. Người sửa dễ truyền `n = 15` với ý định 15 phút, trong khi phép so sánh thực tế dùng mili giây.

### 7.2. Thiết kế theo khái niệm và kiểu dữ liệu

Ví dụ sau dùng Java 17+, khai báo dưới dạng một lớp trong tệp `PickupWindowPolicy.java`:

```java
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class PickupWindowPolicy {
    private PickupWindowPolicy() {}

    /**
     * Trả true khi cửa sổ nhận hàng đã đóng.
     * Tại đúng deadline, cửa sổ được coi là đóng.
     */
    public static boolean isPickupWindowClosed(
            Instant orderReadyAt,
            Instant evaluatedAt,
            Duration pickupWindow) {

        Objects.requireNonNull(orderReadyAt, "orderReadyAt");
        Objects.requireNonNull(evaluatedAt, "evaluatedAt");
        Objects.requireNonNull(pickupWindow, "pickupWindow");
        if (pickupWindow.isNegative() || pickupWindow.isZero()) {
            throw new IllegalArgumentException("pickupWindow phải lớn hơn 0");
        }

        Instant pickupDeadline = orderReadyAt.plus(pickupWindow);
        return !evaluatedAt.isBefore(pickupDeadline);
    }
}
```

Các tên đóng vai trò khác nhau:

| Tên | Điều nó giải thích |
| --- | --- |
| `PickupWindowPolicy` | Đây là quy tắc nghiệp vụ về thời hạn nhận hàng, không phải một tiện ích thời gian chung chung |
| `isPickupWindowClosed` | Kết quả boolean trả lời một câu hỏi cụ thể và có chiều nghĩa rõ |
| `orderReadyAt` | Mốc bắt đầu là lúc hàng sẵn sàng, không phải lúc tạo đơn hay lúc thanh toán |
| `evaluatedAt` | Mốc được đem ra đánh giá, do bên gọi cung cấp để có thể kiểm thử |
| `pickupWindow` | Khoảng thời gian được biểu diễn bằng `Duration`, tránh nhầm giây với mili giây |
| `pickupDeadline` | Mốc kết thúc tính từ thời điểm sẵn sàng và khoảng cho phép |

Đây là một mô hình **quy tắc thuần**: không tự gọi database, không lấy đồng hồ hiện tại và không phát sinh tác dụng phụ. Ở lớp ngoài, có thể truyền `clock.instant()` hoặc một `Instant` đã ghi nhận từ yêu cầu. Nếu nghiệp vụ sử dụng lịch mở cửa hay múi giờ địa phương, cần bổ sung quy tắc tương ứng; `Duration` đơn thuần không thể đại diện cho mọi loại lịch.

### 7.3. Kiểm thử ranh giới bằng JUnit 5

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class PickupWindowPolicyTest {
    private final Instant orderReadyAt =
            Instant.parse("2026-11-16T08:00:00Z");
    private final Duration pickupWindow = Duration.ofMinutes(15);

    @Test
    void staysOpenJustBeforeDeadline() {
        Instant evaluatedAt = Instant.parse("2026-11-16T08:14:59Z");

        assertFalse(PickupWindowPolicy.isPickupWindowClosed(
                orderReadyAt, evaluatedAt, pickupWindow));
    }

    @Test
    void closesAtExactDeadline() {
        Instant evaluatedAt = Instant.parse("2026-11-16T08:15:00Z");

        assertTrue(PickupWindowPolicy.isPickupWindowClosed(
                orderReadyAt, evaluatedAt, pickupWindow));
    }

    @Test
    void rejectsNonPositivePickupWindow() {
        assertThrows(IllegalArgumentException.class, () ->
                PickupWindowPolicy.isPickupWindowClosed(
                        orderReadyAt, orderReadyAt, Duration.ZERO));
    }
}
```

Tên từng test truyền đạt **hành vi biên**: `staysOpenJustBeforeDeadline`, `closesAtExactDeadline`, `rejectsNonPositivePickupWindow`. Chúng giúp người sửa hiểu quy ước mà chỉ nhìn tên phương thức `isPickupWindowClosed` chưa chắc suy ra được. Dữ liệu thời gian cố định làm test có thể chạy lặp lại mà không phụ thuộc vào thời điểm thực thi.

Đây là ví dụ minh họa cho cách đặt tên và bảo vệ quy tắc. Một hệ thống thật còn cần xử lý các giá trị cực hạn của `Instant` và `Duration`, trạng thái thay đổi khi nhiều người đặt cùng lúc, và tính nhất quán với cách lưu thời điểm ở database nếu các rủi ro đó tồn tại.

## 8. Tên của dữ liệu, kết quả và ngoại lệ cần phản ánh trạng thái thật

### 8.1. Phân biệt dữ liệu nguồn với dữ liệu đã xác nhận

Một pipeline nhận dữ liệu có thể trải qua các bước: nhận payload → phân tích cú pháp → xác thực → lưu bền vững. Nếu mỗi bước đều gọi biến là `request`, người đọc sẽ khó biết đã đi qua ranh giới tin cậy nào.

```java
String rawCustomerId = httpRequest.customerId();
CustomerId parsedCustomerId = CustomerId.parse(rawCustomerId);
Customer customer = customerRepository.findById(parsedCustomerId);
```

Đặt `parsedCustomerId` giúp phân biệt dữ liệu đã chuyển thành đối tượng với chuỗi thô. Tuy nhiên, nếu `CustomerId.parse()` chỉ kiểm tra cú pháp, điều đó **chưa chứng minh** khách hàng đã tồn tại hay người gọi có quyền truy cập. Tên `authorizedCustomer` chỉ được dùng sau khi có cơ chế phân quyền phù hợp.

### 8.2. Tên kết quả phân biệt các khả năng quan trọng

Phương thức `processPayment()` trả `boolean` bắt caller tự nhớ `true`/`false` nghĩa là gì. Nhưng thao tác thanh toán có thể có ít nhất các trạng thái: đã hoàn tất, bị từ chối, hoặc **chưa rõ kết quả do timeout**. Nếu đánh đồng timeout với thất bại đã xác nhận, hệ thống có thể thử lại và thu tiền hai lần.

```java
enum PaymentOutcome {
    CAPTURED,
    DECLINED,
    PENDING_RECONCILIATION
}
```

Những tên này làm cho khác biệt nghiệp vụ xuất hiện trong chữ ký và các nhánh xử lý. Tên `PENDING_RECONCILIATION` chỉ có giá trị nếu hệ thống thực sự có đường lưu trạng thái và đối soát; enum tự nó không bảo đảm quy trình phục hồi.

### 8.3. Exception nên nói rõ điều kiện thất bại

Tên `BusinessException`, `ProcessingException` hoặc `RuntimeException` có thể quá chung khi caller cần phân biệt lỗi để quyết định trả phản hồi hay retry. Những loại như `InsufficientInventoryException` hoặc `InvalidReservationException` giúp người đọc hiểu nguyên nhân.

Đừng tạo hàng chục lớp ngoại lệ chỉ để tên dài hơn. Nếu API đã có một kiểu kết quả miền nghiệp vụ rõ ràng, có thể dùng kết quả đó cho các tình huống bình thường; ngoại lệ tập trung cho trường hợp mà luồng chính không thể tiếp tục. Quan trọng là **phân loại phù hợp với quyết định mà caller cần thực hiện**.

## 9. Những kiểu đặt tên dễ gây nợ chất lượng

| Kiểu tên | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| `a`, `b`, `x`, `tmp` ở phạm vi rộng | Không có thông tin để phân biệt | Dựa vào vai trò thực: `previousBalance`, `parsedAmount` |
| `data`, `info`, `obj`, `list` | Lặp lại kiểu hoặc mô tả quá rộng | Gọi đúng chủ thể và trạng thái: `pendingPayments`, `invoiceLines` |
| `doWork`, `handle`, `process` | Không nói loại công việc và tác dụng phụ | `validateInvoice`, `dispatchNotification` khi ngữ cảnh cần phân biệt |
| `isNotDisabled`, `notAllowed` | Phủ định kép khiến điều kiện khó đọc | Chọn mệnh đề dương `isEnabled`, `canProceed` nếu diễn đạt được chính xác |
| `total1`, `total2` | Không phân biệt trước và sau bước nào | `subtotalBeforeTax`, `totalAfterDiscount` |
| `date` hoặc `timestamp` cho `long` | Thiếu mốc và đơn vị | `createdAtEpochMillis` hoặc `Instant createdAt` |
| `discount` dùng khi giá trị là phần trăm | Mơ hồ về miền giá trị | `discountRate` cho `0..1`, `discountPercent` cho `0..100` |
| `newUser`, `oldUser` | Ý nghĩa thay đổi theo thời điểm hoặc phiên bản | `userBeforeUpdate`, `userAfterUpdate` nếu đó là điều muốn nói |
| `customerStringValue` | Tên lặp kiểu và quá dài | `customerId` với kiểu `CustomerId` hoặc `String` có hợp đồng |
| `IUserService`, `UserServiceImpl` | Dễ làm tên chỉ phản ánh cấu trúc kỹ thuật | Ưu tiên tên theo vai trò thật khi có nhiều triển khai: `RemoteUserDirectory`, `CachedUserDirectory` |

Đây là **tín hiệu để đặt câu hỏi**, không phải danh sách cấm tuyệt đối. `handle()` có thể đủ rõ trong interface chuyên biệt như `EventHandler`, `value` có thể đủ rõ trong một hàm chuyển đổi ngắn, `oldValue` và `newValue` có thể đúng trong callback phát thông báo thay đổi. Hãy đánh giá bằng cách xem người đọc có thể suy luận chính xác mà không cần lần theo quá nhiều chi tiết hay không.

### Đừng dùng tên để che giấu thiết kế sai

Đổi `data` thành `customerProfileDataTransferObject` có thể khiến tên dài hơn nhưng không làm trách nhiệm rõ hơn nếu đối tượng vẫn chứa dữ liệu của khách hàng, hóa đơn, tồn kho và báo cáo cùng lúc. Khi thiếu ranh giới, cần tách dữ liệu hoặc logic trước khi chọn tên mới. Tương tự, một boolean `wasSuccessfullyProcessed` không giải quyết được việc hệ thống không phân biệt thất bại và kết quả chưa xác định.

## 10. Khi nào nên đổi tên và làm thế nào để đổi an toàn?

Đổi tên có thể là refactor hữu ích vì làm rõ ý nghĩa mà không thay đổi hành vi. Nhưng phạm vi sửa và tác động tương thích phải được kiểm soát.

1. **Xác định sự thật trước:** biến đại diện cho gì, đơn vị nào, trạng thái trước/sau bước nào, điều kiện đúng/sai là gì? Đọc code và kiểm thử liên quan; tránh tự suy từ tên sai hiện tại.
2. **Chọn tên diễn đạt hợp đồng:** ưu tiên thuật ngữ thống nhất với miền nghiệp vụ, vừa đủ ngắn theo phạm vi dùng.
3. **Tìm mọi nơi sử dụng:** IDE rename refactoring có thể cập nhật tham chiếu Java nhưng không chắc cập nhật SQL, JSON, YAML, reflection, script và consumer bên ngoài.
4. **Phân biệt tên nội bộ với hợp đồng công khai:** đổi local variable thường an toàn hơn đổi public method, tên cột database hay tên field JSON.
5. **Giữ nguyên hành vi trong refactor:** có kiểm thử cho các kết quả và điều kiện biên quan trọng; khi cần thay API, dùng adapter hoặc lộ trình phiên bản.
6. **Review tính nhất quán:** tên mới phải khớp với kiểu dữ liệu, đơn vị, log, tài liệu, phương thức liên quan và các trường dữ liệu cùng nghĩa.
7. **Kiểm chứng sau đổi:** chạy kiểm thử phù hợp, kiểm tra diff và rủi ro tương thích; đối với API hay schema, xác minh các bên sử dụng thực tế.

Ví dụ, nếu một phương thức public `getTimeout()` trả `long` là mili giây, đổi thành `getTimeoutSeconds()` **không** làm nó trả giây. Đổi tên đúng phải đi kèm quyết định về hành vi: giữ `getTimeoutMillis()` cho caller cũ và bổ sung `getTimeout()` trả `Duration` là một hướng chuyển tiếp, nhưng cũng cần chính sách tương thích vì tên và kiểu trả về mới là API khác.

## 11. Checklist review tên gọi

Khi review một đoạn Java, hãy dùng những câu hỏi cụ thể sau:

- **Ý nghĩa:** nếu chỉ nhìn chữ ký và vài dòng xung quanh, người đọc có biết giá trị/điều kiện/hành động này là gì không?
- **Chủ thể:** `status` là trạng thái của đối tượng nào; `count` đếm loại phần tử nào; `amount` là khoản tiền nào?
- **Đơn vị:** có giá trị số nào phải mang tên `Millis`, `Seconds`, `Bytes`, `Meters`, `Cents`, `Percent` hoặc được đổi sang kiểu dữ liệu mạnh hơn không?
- **Mốc thời gian:** tên có phân biệt `createdAt`, `expiresAt`, `duration`, `elapsedTime` và ngày theo lịch không?
- **Boolean:** một biểu thức `if (...)` có đọc thành mệnh đề đúng rõ ràng không; có phủ định kép hoặc trường hợp trạng thái thứ ba bị mất không?
- **Tác dụng phụ:** tên method có khiến caller hiểu nhầm một hành động ghi dữ liệu là truy vấn thuần không?
- **Phạm vi:** tên có đủ rõ khi dùng ở một tệp khác, class khác hoặc API công khai không; có bị dài do lặp ngữ cảnh đã quá rõ không?
- **Trạng thái dữ liệu:** tên có nói đúng dữ liệu đã được kiểm tra, xác thực, phân quyền hoặc lưu bền vững chưa?
- **Tính nhất quán:** các khái niệm giống nhau có cùng thuật ngữ ở code, test, API và tài liệu không?
- **Tương thích:** đổi tên này có ảnh hưởng tới caller, schema, message, JSON, reflection hay công cụ vận hành không?

Một review tốt không chỉ phê bình "tên chưa đẹp", mà nêu **điều đang mơ hồ**, **hệ quả có thể xảy ra** và **tên mới chính xác hơn**. Ví dụ: "`delay` có thể bị hiểu là giây; API nhận milliseconds, nên dùng `retryDelayMillis` hoặc đổi kiểu sang `Duration`" là góp ý có thể kiểm chứng.

## 12. Bài tập thực hành

**Bài 1 — Nhận diện sai đơn vị.** Một API gửi thời gian chờ dưới dạng `timeout = 30`; phía server lưu `long` và dùng với `Thread.sleep(timeout)`. Người viết API mong muốn 30 giây. Hãy chỉ ra sai lệch, đề xuất tên cho tham số ở ranh giới, kiểu dữ liệu trong miền nghiệp vụ, và test giúp phát hiện lỗi chuyển đổi.

**Bài 2 — Chọn tên đúng theo trạng thái.** Luồng thanh toán có các giá trị: số tiền khách muốn thanh toán, số tiền cổng thanh toán đã xác nhận thu, số tiền đã hoàn trả. Hãy đặt tên ba biến, giải thích vì sao không nên dùng `amount1`, `amount2`, `amount3`, và xác định những phép so sánh nào cần thêm đơn vị tiền tệ hoặc một kiểu `Money`.

**Bài 3 — Tên boolean.** Cho các biến `ok`, `notError`, `done`, `flag`. Với chức năng đặt vé, hãy đặt lại tên để phân biệt: còn ghế, có quyền đặt, đã xác nhận thanh toán, đang chờ đối soát. Có trạng thái nào nên dùng enum thay vì boolean không? Vì sao?

**Bài 4 — Phạm vi và tính tương thích.** Một thư viện có phương thức `long getTime()` trả epoch milliseconds và nhiều ứng dụng đang gọi. Hãy lập phương án đưa vào API mới diễn đạt rõ mốc thời gian (`Instant` hoặc tên có đơn vị) mà không làm hỏng ứng dụng cũ ngay lập tức; nêu điều kiện và thời điểm có thể ngừng hỗ trợ API trước.

**Bài 5 — Đọc test như tài liệu.** Dựa trên `PickupWindowPolicy`, hãy viết thêm test cho thời điểm sau deadline một giây và thời điểm trước lúc hàng sẵn sàng; đặt tên test diễn tả quy tắc thay vì gọi `test1()` hoặc `caseA()`. Xác định quy tắc nghiệp vụ nào cần hỏi thêm trước khi đổi điều kiện `>=` thành `>`.

Với mỗi bài, trả lời theo ba yếu tố: **ý nghĩa cần bảo toàn, tên/kiểu đề xuất, và cách kiểm chứng lựa chọn không tạo hành vi sai**.

## 13. Ghi nhớ

Đặt tên có chất lượng là một quyết định thiết kế nhỏ nhưng xuất hiện ở mọi nơi. **Tên theo ý nghĩa** giúp người đọc nhận ra khái niệm và hành vi; **tên theo đơn vị** giảm lỗi chuyển đổi và hiểu nhầm giá trị; **tên theo phạm vi** cung cấp đủ ngữ cảnh ở đúng nơi người khác cần sử dụng.

Hãy chọn tên chính xác, nhất quán với từ vựng nghiệp vụ và khớp với kiểu dữ liệu cũng như hành vi thực. Đừng cố giải quyết mọi vấn đề bằng cách viết tên thật dài: khi một khái niệm phải mang quá nhiều thông tin trong tên, hãy xem lại mô hình dữ liệu, ranh giới phương thức và hợp đồng. Mã đáng đọc là mã mà người tiếp theo có thể hiểu **nó biểu diễn điều gì, dùng đơn vị nào, có thể tin vào cam kết nào và thay đổi ra sao** mà không cần đoán.
