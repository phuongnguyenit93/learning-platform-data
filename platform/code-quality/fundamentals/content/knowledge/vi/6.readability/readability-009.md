# Tránh che tác dụng phụ sau tên gọi hoặc biểu thức khó đoán

Một phương thức tên `calculateTotal()` tưởng như chỉ tính tiền, nhưng lại ghi một bản ghi giảm giá vào cơ sở dữ liệu. Một phương thức `isEligible()` tưởng như chỉ kiểm tra điều kiện, nhưng lại giữ hàng trong kho. Một biểu thức `stream().peek(...).findFirst()` có thể thực hiện ít tác dụng phụ hơn người viết dự đoán. Những đoạn mã này thường khó đọc vì người xem phải đoán **chương trình thực sự làm thay đổi điều gì**.

Trong chương **Khả năng đọc** của **CODE_QUALITY_FUNDAMENTALS**, bài học này tập trung vào việc khiến tác dụng phụ (*side effect*) xuất hiện rõ ở tên gọi, cấu trúc lệnh và ranh giới trách nhiệm. Đây là một phần của mục tiêu học phần: hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Một đoạn mã dễ đọc cho người bảo trì biết được giá trị nào chỉ được tính toán, dữ liệu nào được đọc, trạng thái nào có thể thay đổi, và thay đổi diễn ra theo thứ tự nào.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện tác dụng phụ trực tiếp và gián tiếp trong mã Java.
2. Phát hiện sự không khớp giữa **tên phương thức** và **hành vi thực sự**, đặc biệt ở các hàm trông như truy vấn.
3. Giải thích vì sao nhét tác dụng phụ vào toán tử điều kiện, biểu thức phức tạp, Stream hoặc Optional làm khó dự đoán chương trình.
4. Tách **tính toán, kiểm tra, quyết định** khỏi **thực thi hành động thay đổi trạng thái** khi thích hợp.
5. Thiết kế tên gọi, trình tự lệnh và kiểm thử thể hiện rõ những thay đổi có thể quan sát.

## 1. Tác dụng phụ là gì và vì sao liên quan đến khả năng đọc?

**Tác dụng phụ** là tác động có thể quan sát ngoài giá trị mà biểu thức hay phương thức trả về. Trong lập trình Java, đó có thể là:

- Thay đổi trường của đối tượng, biến dùng chung, collection hoặc cache.
- Ghi cơ sở dữ liệu, tạo/xóa tệp, gửi HTTP request có thay đổi dữ liệu.
- Gửi email, thông báo, thanh toán, phát thông điệp.
- Ghi log, cập nhật số liệu đo lường, thay đổi bộ đếm.
- Làm thay đổi đối tượng được truyền vào qua tham chiếu.

Ngay cả thao tác chỉ đọc cơ sở dữ liệu hoặc tệp cũng là một **tương tác với môi trường bên ngoài**: kết quả có thể thay đổi giữa các lần đọc, thời gian thực hiện có thể lớn, và thao tác có thể ném ngoại lệ I/O. Nó không nhất thiết là *thay đổi trạng thái nghiệp vụ*, nhưng không phải một phép tính thuần chỉ phụ thuộc vào tham số.

Ví dụ đối chiếu:

```java
// Chỉ tính kết quả từ đầu vào; không sửa trạng thái của đối tượng khác.
static long calculateSubtotal(long unitPrice, int quantity) {
    if (unitPrice < 0 || quantity < 0) {
        throw new IllegalArgumentException("Negative price or quantity");
    }
    return Math.multiplyExact(unitPrice, quantity);
}

// Thay đổi trạng thái ngoài phương thức: có tác dụng phụ.
void saveOrder(Order order) {
    orderRepository.save(order);
}
```

Hàm `calculateSubtotal` là phép tính thuần đối với các đầu vào được cung cấp (ngoại lệ của `Math.multiplyExact` khi tràn số cũng được xác định bởi đầu vào). `saveOrder` có chủ đích ghi dữ liệu. Cả hai đều có thể là mã tốt nếu **người đọc nhìn vào tên và vị trí gọi có thể nhận biết loại hành vi**.

Tác dụng phụ **không phải điều xấu mặc định**: hệ thống phải lưu đơn hàng, trừ tồn kho và gửi thông báo để tạo ra giá trị. Vấn đề xuất hiện khi chúng bị che giấu, xảy ra vào lúc người gọi không dự kiến hoặc bị thực thi nhiều hay ít lần ngoài ý muốn.

### Ba câu hỏi khi đọc một lời gọi

Khi gặp `service.method(argument)`, hãy tự hỏi:

1. Phương thức **đọc hay thay đổi** trạng thái nào?
2. Nếu nó thay đổi trạng thái, **thay đổi diễn ra khi nào, bao nhiêu lần** và có thể thất bại giữa chừng không?
3. Tên gọi, kiểu trả về và vị trí trong luồng xử lý có **thể hiện kỳ vọng đó** không?

Nếu câu trả lời chỉ có thể tìm thấy bằng cách mở hàng loạt hàm lồng nhau, mã có thể đang che tác dụng phụ.

## 2. Tên gọi phải phản ánh hành vi có thể quan sát

Tên phương thức tạo ra một lời hứa với người đọc. Những động từ như `is`, `has`, `find`, `calculate`, `format` thường khiến người đọc kỳ vọng một thao tác kiểm tra, đọc hoặc tính toán. Những động từ như `save`, `update`, `reserve`, `send`, `charge`, `delete`, `publish` báo trước hành động có thể tạo tác dụng phụ.

### Ví dụ: `isReadyToShip()` âm thầm giữ hàng

```java
// Tên gợi ý một phép kiểm tra, nhưng implementation đang ghi trạng thái.
boolean isReadyToShip(Order order) {
    if (!inventory.reserve(order.sku(), order.quantity())) {
        return false;
    }
    notifications.sendReserved(order.customerEmail());
    return true;
}

if (isReadyToShip(order) && fraudService.isApproved(order)) {
    shipmentService.schedule(order);
}
```

Trong biểu thức `&&` trên, Java đánh giá vế trái trước. Nếu `isReadyToShip` trả về `true`, kho đã bị giữ và thông báo có thể đã được gửi **trước khi** kiểm tra chống gian lận. Nếu `fraudService.isApproved(order)` trả về `false`, lệnh đặt lịch vận chuyển không chạy nhưng hai tác dụng phụ trước đó đã xảy ra.

Điều nguy hiểm là tên `isReadyToShip` và vị trí trong điều kiện khiến người đọc tưởng cả hai vế chỉ đang kiểm tra. Người sửa mã có thể đổi thứ tự vế, gọi phương thức hai lần để debug hoặc retry toàn bộ đoạn mã mà không thấy rủi ro.

### Tách quyết định và hành động

```java
void prepareShipment(Order order) {
    if (!fraudService.isApproved(order)) {
        return;
    }

    // Hành động thay đổi tồn kho hiện rõ trong luồng điều khiển.
    Reservation reservation =
            inventory.reserve(order.sku(), order.quantity());

    // Các hành động có tác dụng phụ tiếp theo đều có tên gọi chủ động.
    shipmentService.schedule(order.id(), reservation.id());
    notifications.queueReservationNotice(order.id());
}
```

Ví dụ này dùng `inventory.reserve` như một **lệnh giữ hàng nguyên tử**: nó trả về `Reservation` hoặc báo lỗi nếu không thể giữ đủ hàng. Cần lưu ý rằng sắp xếp câu lệnh rõ ràng **chưa tự bảo đảm giao dịch xuyên qua kho, vận chuyển và thông báo**. Nếu một bước thất bại, ứng dụng vẫn phải có chính sách nhất quán, bù trừ, retry hoặc outbox phù hợp.

Điểm cải thiện về khả năng đọc là **người xem thấy rõ các bước thay đổi trạng thái và thứ tự của chúng**. Thay đổi nghiệp vụ cũng dễ đặt đúng chỗ hơn: nếu phải kiểm tra một điều kiện mới trước khi giữ hàng, người sửa mã biết thêm vào đâu.

### Bảng đặt tên theo kỳ vọng hành vi

| Tên gợi nhầm lẫn | Hành vi thực tế | Tên hoặc cách tổ chức dễ hiểu hơn |
| --- | --- | --- |
| `getNextOrderId()` | Tăng và lưu bộ đếm cấp ID. | `allocateOrderId()` hoặc `reserveNextOrderId()`. |
| `calculateDiscount()` | Tính mức giảm **và sử dụng** voucher. | `calculateDiscount()` để tính, `redeemVoucher()` để tiêu thụ lượt dùng. |
| `isCustomerValid()` | Kiểm tra rồi tự động sửa hồ sơ khách hàng. | `validateCustomer()` để kiểm tra, `normalizeAndSaveCustomer()` để sửa/lưu. |
| `findOrCreateAccount()` | Đọc hoặc tạo bản ghi mới. | Giữ tên `findOrCreate` nếu hợp đồng nói rõ hành vi tạo; đừng đổi thành `findAccount()`. |
| `loadReport()` | Đọc từ ổ đĩa và tải dữ liệu lên hệ thống khác. | Tách `loadReport()` và `uploadReport()`. |
| `checkAndSend()` | Vừa kiểm tra vừa gửi thông báo. | Tách `canSend()` và `sendNotification()` nếu ranh giới nghiệp vụ cho phép. |

Các quy ước tên không phải luật tuyệt đối. Ví dụ `getOrCreate`, `computeIfAbsent` và `saveAndFlush` có thể là API hợp lý nếu người dùng hiểu rõ hợp đồng của chúng. Điều quan trọng là **tên gọi và tài liệu công khai không khiến tác dụng phụ trở thành bất ngờ**.

## 3. Tách truy vấn và lệnh: tư duy Command–Query Separation

Một nguyên tắc hữu ích là **Command–Query Separation (CQS)**:

- **Query:** trả lời câu hỏi về dữ liệu, không chủ đích thay đổi trạng thái nghiệp vụ.
- **Command:** yêu cầu hệ thống thực hiện thay đổi trạng thái; tên gọi làm rõ hành động đó.

Ví dụ với dịch vụ vé:

```java
interface SeatStore {
    int remainingSeats(String eventId);              // Đọc trạng thái.
    boolean reserveSeats(String eventId, int count); // Thay đổi trạng thái.
}

final class TicketService {
    private final SeatStore seats;

    TicketService(SeatStore seats) {
        this.seats = java.util.Objects.requireNonNull(seats);
    }

    boolean canBook(String eventId, int count) {
        return count > 0 && seats.remainingSeats(eventId) >= count;
    }

    boolean book(String eventId, int count) {
        if (count <= 0) {
            throw new IllegalArgumentException("Count must be positive");
        }
        return seats.reserveSeats(eventId, count);
    }
}
```

`canBook` làm công việc đọc; `book` thực hiện lệnh. Chữ ký `book` trả về `boolean` để báo thành công không có nghĩa nó trở thành query: **một command vẫn có thể trả về mã kết quả, định danh hoặc biên nhận** trong một API thực tế. CQS là định hướng để giảm tác dụng phụ bất ngờ trong cách tổ chức phương thức, không phải đòi hỏi mọi command phải có kiểu trả về `void`.

**Ranh giới tính đúng đắn:** `canBook()` chỉ phản ánh tình trạng ghế ở **thời điểm đọc**. Hai yêu cầu đồng thời có thể cùng nhận `true`; vì thế `reserveSeats` cần cập nhật nguyên tử và kiểm tra số ghế còn lại ở nơi lưu trữ. Không được xem query kiểm tra trước là bảo đảm đặt vé thành công.

CQS ở **cấp phương thức** cũng không đồng nghĩa với **CQRS** (Command Query Responsibility Segregation), một lựa chọn kiến trúc tách các đường đọc/ghi ở cấp hệ thống. Bạn không cần xây dựng CQRS để đặt tên query/command rõ ràng trong một ứng dụng Java nhỏ.

### Khi nào không nhất thiết phải tách?

Một thao tác có ý nghĩa nghiệp vụ thống nhất vẫn có thể vừa thay đổi trạng thái, vừa trả về kết quả. Chẳng hạn `inventory.reserve(...)` thực hiện việc giữ hàng và trả về mã giữ hàng trong cùng một giao dịch. Tách nó thành `hasStock()` rồi `decreaseStock()` có thể gây lỗi đồng thời và làm người gọi phải tự phối hợp nhiều bước.

Mục tiêu là làm **ranh giới hiệu ứng** rõ ràng, không phải chia một thao tác nguyên tử thành nhiều hàm chỉ để các hàm trông nhỏ hơn.

## 4. Tác dụng phụ ẩn trong biểu thức điều kiện

Các toán tử `&&`, `||` và `?:` cho phép viết gọn logic. Tuy nhiên, khi một vế ghi trạng thái, **điều kiện đánh giá** đồng thời quyết định **tác dụng phụ có được thực hiện hay không**.

Ví dụ:

```java
if (isValid(order) && repository.save(order) != null) {
    audit.logCreated(order.id());
}
```

`repository.save` thay đổi dữ liệu nhưng bị nhúng trong một điều kiện trông như phép kiểm tra. Người đọc phải lần theo cả giá trị trả về và hành động ẩn để biết vì sao một số dòng được ghi, một số dòng không.

Viết tuyến tính dễ theo dõi hơn:

```java
if (!isValid(order)) {
    return;
}

Order savedOrder = repository.save(order);
audit.logCreated(savedOrder.id());
```

Đoạn thứ hai làm rõ thời điểm ghi đơn và ghi audit. Nếu `repository.save` có thể trả về `null` theo hợp đồng thực tế, phải xử lý kết quả thiếu một cách rõ ràng thay vì mặc định nó luôn thành công. Khi `save` có thể ném ngoại lệ hoặc cần giao dịch chung với audit, cách bảo đảm nhất quán cũng phải được thiết kế riêng.

### Thứ tự đánh giá và ngắt mạch

Trong Java, `&&` và `||` là toán tử **ngắt mạch** (*short-circuit*): vế phải không được đánh giá nếu đã biết kết quả từ vế trái.

```java
if (isInStock(item) && sendPromotionEmail(customer)) {
    // ...
}
```

Nếu `isInStock(item)` trả về `false`, email không được gửi. Nếu ai đó đổi thứ tự vế để “tối ưu” mà không biết `sendPromotionEmail` có tác dụng phụ, chương trình có thể bắt đầu gửi email cho cả khách hàng có mặt hàng đã hết.

Việc gọi một hàm có tác dụng phụ bên trong biểu thức điều kiện cũng khiến việc thêm log hoặc debug khó an toàn: gọi thử cùng phương thức để xem kết quả có thể thực thi hành động lần nữa.

### Gán hoặc tăng biến ngay trong điều kiện

```java
int index = 0;
while (index++ < records.size()) {
    process(records.get(index - 1));
}
```

Mã này có thể hoạt động với một `records` ổn định, nhưng người đọc phải ghi nhớ `index++` trả **giá trị cũ**, sau đó mới tăng biến. Nếu cần thao tác theo chỉ số, vòng `for` thông thường diễn đạt ý định rõ hơn:

```java
for (int index = 0; index < records.size(); index++) {
    process(records.get(index));
}
```

Không phải mọi biểu thức `++` hay phép gán trong điều kiện đều sai. Ví dụ `while ((line = reader.readLine()) != null)` là mẫu đọc stream phổ biến. Tuy nhiên, nó đồng thời cập nhật biến `line` và đọc I/O; cần bảo đảm người xem hiểu quy tắc này và lựa chọn có chủ ý, đặc biệt trong mã nhiều nhánh.

## 5. Stream: tránh dùng `peek` để điều khiển tác dụng phụ nghiệp vụ

Java Stream là một ví dụ quan trọng vì nhiều thao tác trung gian như `map`, `filter`, `peek` có cơ chế **đánh giá lười** (*lazy evaluation*). Một pipeline thường không chạy cho đến khi có thao tác kết thúc (*terminal operation*), và thao tác kết thúc có thể **ngắt sớm**.

Ví dụ nguy hiểm:

```java
boolean hasOverdue = invoices.stream()
        .peek(invoice -> repository.markReviewed(invoice.id()))
        .anyMatch(Invoice::isOverdue);
```

Người đọc có thể nghĩ tất cả hóa đơn đều được đánh dấu “đã xem” rồi mới kiểm tra có quá hạn hay không. Thực tế, `anyMatch` có thể dừng ngay khi gặp hóa đơn quá hạn đầu tiên, nên chỉ một phần hóa đơn có thể đi qua `peek`. Việc dùng tác dụng phụ bên trong `peek` cũng có thể hành xử khác khi đổi pipeline, thay nguồn dữ liệu hoặc dùng stream song song.

Nếu yêu cầu là **đánh dấu tất cả hóa đơn đã xem**, hãy biểu diễn đó là một bước nghiệp vụ độc lập:

```java
for (Invoice invoice : invoices) {
    repository.markReviewed(invoice.id());
}

boolean hasOverdue = invoices.stream()
        .anyMatch(Invoice::isOverdue);
```

Bây giờ người đọc thấy rõ bước ghi trạng thái và bước trả lời câu hỏi. Nếu một lần `markReviewed` thất bại giữa vòng lặp, có thể có một phần hóa đơn đã được đánh dấu; đó là vấn đề giao dịch cần giải quyết theo hợp đồng, không phải điều cú pháp Stream hay vòng `for` tự khắc phục.

### `map`, `filter` và `peek` có vai trò gì?

| Thao tác | Ý định dễ hiểu | Rủi ro khi giấu side effect |
| --- | --- | --- |
| `map` | Chuyển mỗi phần tử thành giá trị khác. | Ghi DB/gửi thông báo khi biến đổi, có thể bị bỏ qua nếu phần tử không được tiêu thụ. |
| `filter` | Chọn phần tử thỏa điều kiện. | Predicate sửa trạng thái khiến việc lọc phụ thuộc thứ tự gọi. |
| `peek` | Quan sát phần tử đi qua pipeline, thường để debug. | Không nên dựa vào nó cho hiệu ứng bắt buộc với mọi phần tử. |
| `forEach` | Thực hiện hành động với các phần tử được duyệt. | Hành động được thể hiện rõ hơn, nhưng stream song song có thể tạo vấn đề thứ tự và an toàn luồng. |
| `findFirst`, `anyMatch`, `limit` | Có thể chỉ xử lý một phần nguồn. | Tác dụng phụ ở bước trung gian không bảo đảm chạy trên mọi phần tử. |

Với yêu cầu “gửi thông báo cho từng khách hàng”, một vòng lặp với lời gọi `notificationService.send(...)` có thể dễ kiểm soát ngoại lệ và trạng thái thành công/thất bại hơn pipeline lồng nhiều phép biến đổi. Với mục tiêu “chuyển danh sách thành dữ liệu hiển thị”, Stream thuần thường rất dễ đọc.

## 6. Optional và các biểu thức fallback có hiệu ứng

`Optional` giúp mô hình hóa giá trị có hoặc không, nhưng cũng dễ bị lạm dụng để giấu những thao tác thay đổi trạng thái.

### `orElse` đánh giá tham số ngay

```java
User user = optionalUser.orElse(userRepository.createGuest());
```

Trong Java, đối số của `orElse(...)` được đánh giá **trước khi gọi `orElse`**. Vì vậy, `createGuest()` có thể chạy và ghi bản ghi guest **ngay cả khi** `optionalUser` đang chứa một `User` hợp lệ. Đây là tác dụng phụ khó nhìn thấy nếu đọc nhanh dòng code.

Nếu cần tạo guest **chỉ khi không có user**:

```java
User user = optionalUser.orElseGet(userRepository::createGuest);
```

`orElseGet` nhận một `Supplier` và chỉ gọi nó khi Optional rỗng. Nhưng nếu việc tạo guest là một bước nghiệp vụ quan trọng cần ghi log, kiểm soát giao dịch và xử lý lỗi riêng, cách tách nhánh có thể còn rõ ràng hơn:

```java
User user;
if (optionalUser.isPresent()) {
    user = optionalUser.get();
} else {
    user = userRepository.createGuest();
}
```

Ở đây `isPresent()` và `get()` được dùng sau khi đã kiểm tra, nên ví dụ an toàn với Optional này. Không phải lúc nào cũng cần đổi mọi `orElseGet` thành `if`; chọn cách diễn đạt giúp hành động có tác dụng phụ đủ nổi bật trong luồng nghiệp vụ.

### `map` không phải nơi mặc định để ghi dữ liệu

```java
Optional<String> email = optionalUser.map(user -> {
    auditRepository.recordViewed(user.id());
    return user.email();
});
```

Dù `Optional.map` thực thi ánh xạ khi có giá trị, biểu thức này trộn hai công việc: lấy email và ghi sự kiện đã xem. Một người chỉ muốn lấy email có thể không nghĩ thao tác sẽ ghi DB.

Có thể tách:

```java
Optional<String> email = optionalUser.map(User::email);
optionalUser.ifPresent(user -> auditRepository.recordViewed(user.id()));
```

Ở bản sau, `ifPresent` nói rõ một hành động có điều kiện, dù việc ghi audit cần diễn ra trước hay sau khi lấy email vẫn phải theo yêu cầu nghiệp vụ. Nếu thao tác audit là bắt buộc, nên đặt nó trong bước nghiệp vụ có tên chủ động như `recordProfileView` thay vì gắn ngầm vào thao tác đọc hồ sơ.

## 7. Getter, `toString`, `equals` và collection cũng cần hợp đồng rõ

### Getter có tác dụng phụ ẩn

```java
public int getRewardPoints() {
    rewardRepository.recalculateAndSave(customerId);
    return rewardRepository.currentPoints(customerId);
}
```

Tên `getRewardPoints` gợi ý đọc giá trị, nhưng phương thức tính lại và ghi dữ liệu. Gọi getter trong giao diện, log hoặc lúc debug có thể bất ngờ làm thay đổi điểm. Nếu tính lại là một thao tác nghiệp vụ, hãy tách:

```java
rewardService.recalculateAndSavePoints(customerId);
int points = rewardRepository.currentPoints(customerId);
```

Một getter có cache nội bộ là tình huống khác: nó có thể thay đổi bộ nhớ để tối ưu. Việc cache không nhất thiết làm đổi kết quả nghiệp vụ, nhưng vẫn đặt ra vấn đề về đồng thời, tính mới của dữ liệu và chi phí. Khi cache ảnh hưởng đến hành vi mà người gọi quan tâm, hợp đồng phải nói rõ.

### `toString`, `equals` và `hashCode`

Các phương thức này có thể được framework, debugger, logger hoặc collection gọi gián tiếp. Tránh thiết kế chúng để gửi network request, ghi trạng thái nghiệp vụ hoặc phụ thuộc vào tác dụng phụ.

Ví dụ, một đối tượng làm key trong `HashMap` cần `equals` và `hashCode` nhất quán. Nếu chúng đồng thời thay đổi thuộc tính quyết định hash hoặc gây hiệu ứng bên ngoài, việc tra cứu sẽ khó dự đoán và có thể làm hỏng các giả định của cấu trúc dữ liệu.

### Đầu vào bị sửa qua tham chiếu

```java
List<Order> eligible = filterEligible(orders);
```

Nếu `filterEligible` thực hiện `orders.removeIf(...)` rồi trả lại chính danh sách ban đầu, tên `filterEligible` có thể che việc **thay đổi collection của người gọi**. Một phiên bản thuần về mặt dữ liệu có thể tạo danh sách mới:

```java
List<Order> eligible = orders.stream()
        .filter(Order::isEligible)
        .toList(); // Java 16+: danh sách kết quả không hỗ trợ thao tác sửa.
```

Nếu yêu cầu đúng là sửa danh sách tại chỗ, tên như `removeIneligibleOrdersInPlace(orders)` báo rõ tác dụng phụ. Lưu ý rằng `Stream.toList()` không tự biến các phần tử `Order` thành bất biến; nếu `Order` có thể bị sửa, phần tử trong hai danh sách vẫn có thể trỏ tới cùng đối tượng.

### API thư viện có hành vi ghi không thể bỏ qua

`Map.computeIfAbsent(key, mappingFunction)` có thể **thêm phần tử mới vào map** nếu khóa chưa có ánh xạ giá trị khác `null`. Vì thế nó phù hợp với thao tác tạo cache có chủ đích nhưng không nên bị xem là phép tính thuần chỉ vì tên chứa từ `compute`.

```java
Map<String, List<String>> groups = new HashMap<>();
groups.computeIfAbsent("java", key -> new ArrayList<>()).add("readability");
```

Dòng này có thể vừa thêm một danh sách mới vào `groups`, vừa thêm phần tử vào danh sách. Nó là idiom Java phổ biến và có thể rõ ràng với người quen API; nếu đây là trạng thái nghiệp vụ quan trọng, nên đặt trong một phương thức có tên phản ánh thao tác như `addTopicToGroup`.

## 8. Làm rõ tác dụng phụ bằng cấu trúc mã

Đọc được mã không chỉ là đặt tên đúng. **Trình tự lệnh, mức trừu tượng và nơi xử lý lỗi** cũng quyết định người bảo trì có đoán đúng hành vi hay không.

### Trước: biểu thức ngắn nhưng giấu nhiều hành động

```java
boolean accepted = cart.isValid()
        && couponService.consumeIfAvailable(cart.coupon())
        && paymentService.charge(cart.total())
        && emailService.sendReceipt(cart.customer());
```

Biểu thức trả về boolean, nhưng đằng sau là **tiêu thụ coupon, thanh toán và gửi email**. Nếu email thất bại, `accepted` là `false` dù coupon và khoản thanh toán có thể đã được thực hiện. Nếu người gọi retry toàn bộ biểu thức, tác dụng phụ trước đó có thể lặp lại. Sự ngắn gọn khiến những vấn đề này khó được phát hiện trong review.

### Sau: nêu rõ ý định và kết quả từng bước

```java
if (!cart.isValid()) {
    return CheckoutResult.rejected("Invalid cart");
}

CouponRedemption redemption =
        couponService.redeem(cart.coupon(), cart.id());
PaymentReceipt payment =
        paymentService.charge(cart.total(), cart.id());
receiptService.queueReceipt(cart.customer(), payment.id());

return CheckoutResult.accepted(payment.id(), redemption.id());
```

Những kiểu `CheckoutResult`, `CouponRedemption` và `PaymentReceipt` là ví dụ API miền. Mỗi lời gọi có tên chủ động và kết quả riêng, giúp đặt điểm xử lý lỗi. `cart.id()` có thể được dùng làm thành phần khóa lặp an toàn **nếu** hợp đồng nghiệp vụ đã xác nhận một cart tương ứng một lần checkout; không được tự suy điều đó chỉ từ tên ID.

Đây là cải thiện về **khả năng đọc**, chưa phải thiết kế giao dịch hoàn chỉnh. Coupon và thanh toán có thể nằm trên hai hệ thống khác nhau; nếu bước sau lỗi, cần quy trình bù trừ, idempotency và đối soát tương ứng. Việc tách hành động ra từng lệnh giúp nhìn thấy vấn đề và thiết kế cách xử lý, thay vì khiến chúng biến mất sau toán tử `&&`.

### Làm rõ hành động nào được phép lặp

Một phương thức `calculateTotal(cart)` thường nên gọi được nhiều lần mà không phát sinh charge hay redeem. Một phương thức `chargePayment(...)` cần nói rõ quy tắc khi gọi lại, ví dụ yêu cầu idempotency key. Nếu một hàm vừa tính, vừa trừ tiền, người gọi khó biết nó an toàn đến đâu khi cache, retry hoặc dùng cho màn hình xem trước.

Đó là mối liên hệ giữa **khả năng đọc** và **độ tin cậy**: tên gọi không tự bảo đảm idempotency, nhưng nó giúp người viết và người review xác định chính xác chỗ cần cơ chế bảo vệ tác dụng phụ.

## 9. Đánh giá tác dụng phụ theo mức độ và ngữ cảnh

Không phải cứ nhìn thấy một tác dụng phụ là phải tách thành phương thức mới. Hãy cân nhắc **tính dự đoán được, phạm vi ảnh hưởng, khả năng thất bại và chi phí đọc hiểu**:

| Tình huống | Mức độ cần làm rõ | Hướng xử lý |
| --- | --- | --- |
| Tăng biến chỉ số trong vòng `for` quen thuộc. | Thấp. | Giữ cấu trúc chuẩn, không cần helper. |
| Thu thập `metrics.incrementCounter()` trong một command. | Thường thấp đến trung bình. | Có thể chấp nhận nếu không làm sai nghiệp vụ; cần tránh để metrics gây lỗi chính. |
| Getter tự đồng bộ và ghi dữ liệu. | Cao. | Tách lệnh đồng bộ khỏi truy vấn hoặc công bố rõ hợp đồng. |
| `Stream.peek` gửi email. | Cao. | Dùng bước gửi rõ ràng với quy tắc lỗi/retry cụ thể. |
| `computeIfAbsent` tạo cache. | Phụ thuộc ngữ cảnh. | Phù hợp nếu nhóm phát triển hiểu hành vi; cân nhắc bao bọc trong API có tên rõ. |
| `isReady()` đồng thời giữ tài nguyên. | Cao. | Đổi tên thành command hoặc tách kiểm tra và thực thi theo hợp đồng. |
| Thao tác `reserve()` ghi DB và trả biên nhận. | Tác dụng phụ được công bố. | Giữ một command nguyên tử khi nghiệp vụ yêu cầu. |

Một thước đo thực tế: **người đọc có thể đánh dấu ngay các dòng làm thay đổi trạng thái quan trọng mà không phải lần theo nhánh lồng nhau hay không?** Nếu không, mã có thể cần tổ chức lại.

## 10. Kiểm thử hành vi và khả năng đọc

Kiểm thử không đo trực tiếp “mã dễ đọc hay chưa”, nhưng có thể bảo vệ **hợp đồng tác dụng phụ** mà tên gọi và cấu trúc mã đang hứa hẹn.

Với `TicketService` ở trên, một fake đơn giản giúp chứng minh `canBook` chỉ đọc và `book` gọi thao tác giữ chỗ:

```java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class TicketServiceTest {
    static final class FakeSeatStore implements SeatStore {
        int remaining = 5;
        int reserveCalls = 0;

        @Override
        public int remainingSeats(String eventId) {
            return remaining;
        }

        @Override
        public boolean reserveSeats(String eventId, int count) {
            reserveCalls++;
            if (count > remaining) {
                return false;
            }
            remaining -= count;
            return true;
        }
    }

    @Test
    void canBookOnlyReadsSeatAvailability() {
        FakeSeatStore fake = new FakeSeatStore();
        TicketService service = new TicketService(fake);

        assertTrue(service.canBook("EVENT-1", 2));
        assertEquals(5, fake.remaining);
        assertEquals(0, fake.reserveCalls);
    }

    @Test
    void bookMakesItsStateChangeExplicit() {
        FakeSeatStore fake = new FakeSeatStore();
        TicketService service = new TicketService(fake);

        assertTrue(service.book("EVENT-1", 2));
        assertEquals(3, fake.remaining);
        assertEquals(1, fake.reserveCalls);
    }

    @Test
    void invalidCountIsRejectedBeforeReservation() {
        FakeSeatStore fake = new FakeSeatStore();
        TicketService service = new TicketService(fake);

        assertThrows(IllegalArgumentException.class,
                () -> service.book("EVENT-1", 0));
        assertEquals(0, fake.reserveCalls);
    }
}
```

Ví dụ test thể hiện **hợp đồng đọc/ghi ở cấp phương thức**. Nó không chứng minh việc đặt ghế đồng thời đúng trên cơ sở dữ liệu thật; kiểm thử tích hợp và cơ chế cập nhật nguyên tử là trách nhiệm khác.

### Câu hỏi dùng trong code review

Khi review một thay đổi có logic nghiệp vụ, nên đọc các lời gọi theo thứ tự xuất hiện:

1. **Tên gọi có nói thật về hành động không?** `is`, `get`, `find`, `calculate` có đang ghi DB hoặc gửi request không?
2. **Có tác dụng phụ nằm trong predicate, toán tử điều kiện, biểu thức tam phân hoặc lambda không?** Nó có chạy đúng số lần và đúng thứ tự dự kiến không?
3. **Đầu vào có bị sửa bất ngờ không?** Một danh sách có bị `removeIf` hoặc một DTO có bị mutate mà không được nêu rõ không?
4. **Kết quả trả về có mô tả đúng trạng thái sau khi chạy không?** Nếu bước cuối thất bại, các bước trước đã tác động đến hệ thống hay chưa?
5. **Có thể thêm log, cache hoặc retry mà không lặp hành động nghiệp vụ ngoài ý muốn không?** Nếu không, hợp đồng có chỉ ra nơi cần bảo vệ không?
6. **Thứ tự hành động có được trình bày tuyến tính và có lý do không?** Nếu đổi thứ tự hai dòng, hiệu ứng nào sẽ thay đổi?

Không cần biến các câu hỏi này thành yêu cầu tạo lớp mới cho mọi dòng code. Chúng giúp nhận ra nơi một thay đổi rất nhỏ có thể gây hiệu ứng lớn vì người bảo trì đã hiểu nhầm tác dụng của phương thức.

## 11. Sai lầm thường gặp và cách điều chỉnh

**“Tên ngắn là tên tốt.”** Tên `check()` hoặc `process()` không cho biết hành động nào được thực hiện. Hãy chọn tên diễn đạt **mục đích và tác động chính**: `validateInvoice()`, `postInvoice()`, `sendInvoiceEmail()`.

**“Tác dụng phụ trong lambda vẫn rõ vì lambda ngắn.”** Lambda ba dòng có thể gửi email hoặc sửa collection. Độ dài không phản ánh phạm vi tác dụng; cần xem vị trí lambda được thực thi, có lazy/short-circuit/parallel hay không.

**“Kết quả boolean đủ để biết thành công hay thất bại.”** Nếu một biểu thức có ba lệnh ghi và lệnh cuối trả về `false`, boolean không nói được hai lệnh đầu đã thực hiện. Dùng các bước có tên và kết quả/trạng thái lỗi rõ hơn.

**“Đổi tên thôi là đủ.”** Đổi `isReady` thành `reserveIfReady` giúp cảnh báo tác dụng phụ, nhưng vẫn cần xử lý tính nguyên tử, thứ tự và lỗi khi bước giữ tài nguyên thất bại.

**“CQS yêu cầu command phải `void`.”** Trong thực tế, command có thể trả về kết quả cho người gọi. Điều cốt lõi là phân biệt lời gọi đọc với lời gọi có thể thay đổi trạng thái.

**“Dùng Stream luôn dễ đọc hơn vòng lặp.”** Stream rất hợp với biến đổi dữ liệu thuần; một quy trình gửi thông báo hay cập nhật DB đôi khi rõ ràng và an toàn hơn dưới dạng các lệnh tường minh.

**“Getter được framework gọi nên có thể tận dụng để ghi dữ liệu.”** Getter dễ được gọi trong nhiều ngữ cảnh ngoài dự tính. Nếu cần hành động nghiệp vụ, hãy dùng phương thức command riêng và gọi tại điểm có chủ đích.

**“Tách side effect khỏi expression tự động làm hệ thống đáng tin.”** Cấu trúc tuyến tính giúp nhìn thấy các ranh giới thất bại, nhưng vẫn cần transaction, kiểm soát đồng thời, retry/idempotency và đối soát khi hợp đồng đòi hỏi.

## 12. Quy trình thực hành khi viết hoặc sửa mã

1. **Liệt kê những gì đoạn mã đọc và thay đổi.** Bao gồm đối tượng đầu vào, DB, email, message queue, file và trạng thái chia sẻ.
2. **So khớp hành vi với tên.** Đổi tên hàm hoặc tách hàm khi người đọc khó dự đoán tác dụng phụ.
3. **Đưa lệnh có hiệu ứng ra khỏi biểu thức khó theo dõi.** Tránh dùng chúng làm predicate, điều kiện toán tử hoặc bước Stream chỉ để rút ngắn số dòng.
4. **Giữ các phép tính thuần ở nơi có thể.** Các hàm `calculate`, `format`, `validate` nên dễ gọi lại, kiểm thử và tái sử dụng.
5. **Tổ chức các command theo trình tự nghiệp vụ.** Đặt tên kết quả trung gian và bộc lộ nơi có thể phát sinh lỗi.
6. **Bảo vệ tính đúng đắn ở ranh giới ghi.** Không thay một lệnh nguyên tử bằng nhiều bước kiểm tra rồi ghi nếu có khả năng cạnh tranh dữ liệu.
7. **Viết kiểm thử cho cả kết quả và tác dụng phụ.** Kiểm tra có hoặc không có thao tác ghi theo hợp đồng; với DB và tích hợp bên ngoài, kiểm thử ở mức thích hợp.
8. **Review bằng góc nhìn người chưa biết implementation.** Chỉ nhìn tên phương thức và luồng lệnh, họ có dự đoán đúng hiệu ứng quan trọng không?

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Hàm `getDiscount()` trả đúng mức giảm giá nhưng đồng thời trừ một lượt sử dụng voucher. Vì sao tên đó khó đọc?

*Gợi ý:* `get` khiến người gọi kỳ vọng phép đọc. Người gọi thử lại hoặc hiển thị bản xem trước có thể vô tình tiêu thụ thêm lượt voucher. Nên tách bước tính hoặc đổi thành command có hợp đồng rõ.

**Câu 2.** Trong `stream().peek(sendEmail).findFirst()`, có chắc email được gửi cho mọi phần tử không?

*Gợi ý:* Không. Stream đánh giá lười và `findFirst` có thể ngắt sớm; `peek` không phải nơi phù hợp để bắt buộc phát email cho toàn bộ nguồn.

**Câu 3.** `optionalUser.orElse(repository.createGuest())` có tạo guest khi Optional đã có người dùng không?

*Gợi ý:* Có thể có. Đối số của `orElse` được tính trước khi gọi phương thức. Dùng `orElseGet` để thực hiện fallback lười, hoặc tách nhánh nếu đây là hành động nghiệp vụ quan trọng.

**Câu 4.** Một phương thức `reserveSeats` vừa trừ ghế vừa trả về `boolean`. Nó có trái với mục tiêu làm rõ side effect không?

*Gợi ý:* Không nhất thiết. Tên `reserve` đã công bố hành động ghi, còn boolean cho biết kết quả. Thao tác giữ chỗ cần được bảo vệ nguyên tử trong cơ sở dữ liệu.

**Câu 5.** Nếu viết lại một biểu thức thanh toán phức tạp thành các câu lệnh tách biệt, hệ thống đã tự bảo đảm không trừ tiền hai lần khi retry chưa?

*Gợi ý:* Chưa. Mã đã dễ đọc và review hơn, nhưng bảo đảm nghiệp vụ còn cần idempotency, transaction hoặc quy trình bù trừ/đối soát theo ranh giới hệ thống.

## Ghi nhớ

- **Tên gọi là một phần hợp đồng đọc hiểu.** Phương thức gợi ý chỉ kiểm tra hoặc tính toán không nên âm thầm thực thi hành động nghiệp vụ quan trọng.
- **Tác dụng phụ nên xuất hiện tại vị trí người đọc dự kiến.** Đặt command ở lệnh tường minh, có tên rõ và có kết quả/lỗi phù hợp.
- **Biểu thức điều kiện, Stream, Optional và getter** có thể che thời điểm, thứ tự hoặc số lần tác dụng phụ được thực hiện.
- **Tách query và command theo ý nghĩa nghiệp vụ**, đồng thời giữ những thao tác cần nguyên tử tại ranh giới ghi thích hợp.
- **Mã dễ đọc giúp phát hiện rủi ro**, nhưng vẫn cần kiểm thử, giao dịch, kiểm soát đồng thời và bảo vệ retry để đạt tính đúng đắn và độ tin cậy.

**Nguyên tắc áp dụng:** Khi đọc một dòng lệnh, hãy hỏi “Dòng này chỉ trả lời một câu hỏi, hay còn làm thay đổi thế giới bên ngoài?” Nếu có thay đổi, tên gọi và vị trí của nó cần giúp người tiếp theo nhận ra ngay.
