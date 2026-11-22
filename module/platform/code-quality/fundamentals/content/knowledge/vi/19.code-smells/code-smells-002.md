# Phương thức dài và lớp tập trung quá nhiều trách nhiệm

Một yêu cầu tưởng nhỏ: “Đơn hàng từ 500.000 VND được miễn phí giao hàng”. Người phát triển mở `CheckoutManager.checkout()` để sửa một điều kiện, nhưng phương thức này còn kiểm tra đầu vào, duyệt sản phẩm, tính tiền, ghi dữ liệu và gửi email. Trong cùng lớp còn có chức năng hủy đơn, xuất báo cáo CSV, đối soát thanh toán và quản lý thông báo. Muốn chắc việc sửa phí vận chuyển không làm hỏng chức năng khác, người phát triển phải hiểu nhiều phần không liên quan và chạy một bộ kiểm thử rất rộng.

Hai dấu hiệu thường xuất hiện cùng nhau là **phương thức dài (*Long Method*)** và **lớp ôm quá nhiều trách nhiệm (*Large Class* hoặc *God Class*)**. Chúng là những *code smell* — tín hiệu thiết kế có thể cần xem xét — chứ không tự động chứng minh chương trình có lỗi. Một phương thức dài có thể giải quyết một thuật toán gắn kết rõ ràng; một lớp lớn có thể là mô hình hợp lý nếu các hành vi cùng phục vụ một bất biến. Điều cần điều tra là **mã khó hiểu và khó thay đổi vì đang trộn những trách nhiệm khác nhau hay không**.

Bài thuộc chương **Mùi mã** của module `CODE_QUALITY_FUNDAMENTALS`, với mục tiêu hiểu những đặc điểm giúp mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Chúng ta sẽ đi từ một ví dụ Java, nhận diện trách nhiệm, cải thiện theo từng bước và kiểm tra những rủi ro khi refactor.

Sau bài học, bạn có thể:

- Nhận diện dấu hiệu của Long Method, Large Class và God Class mà không lệ thuộc máy móc vào số dòng.
- Phân biệt **độ dài** với **độ phức tạp nhận thức**, **số lượng phương thức** với **số lý do thay đổi**.
- Xác định các trách nhiệm, bất biến dữ liệu và tác dụng phụ đang bị trộn.
- Dùng các kỹ thuật như **Extract Method**, **Extract Class**, **Move Method** và đặt tên theo nghiệp vụ đúng lúc.
- Bảo vệ hành vi bằng test trước khi di chuyển logic, đặc biệt ở các ranh giới dữ liệu, tiền và trạng thái.
- Tránh phân rã quá mức thành nhiều helper, interface hoặc lớp chuyển tiếp không mang thêm ý nghĩa.

## 1. “Mùi mã” là lời mời điều tra, không phải bản án

Một bộ phân tích mã có thể cảnh báo: “Phương thức này dài 120 dòng” hoặc “Lớp này có 40 phương thức”. Cảnh báo giúp người bảo trì biết nơi nên xem kỹ, nhưng **số dòng không tự nói được đoạn mã có sai, có khó đọc hay cần refactor ngay không**.

So sánh hai trường hợp:

- Một phương thức 100 dòng chứa bảng ánh xạ có tên rõ, không có tác dụng phụ, được kiểm thử ổn định và rất hiếm thay đổi.
- Một phương thức 35 dòng lồng nhiều điều kiện, gọi database trong vòng lặp, thay đổi đối tượng dùng chung rồi gửi thông báo; chỉ cần sửa một nhánh đã dễ gây lỗi hồi quy.

Trường hợp thứ hai có thể đáng ưu tiên hơn dù ngắn hơn nhiều.

Một code smell hữu ích khi gợi ra câu hỏi cụ thể: **Nếu ngày mai quy tắc giao hàng thay đổi, tôi phải hiểu và sửa những phần nào?** Nếu một yêu cầu hẹp liên tục buộc nhóm chạm tới nhiều trách nhiệm không liên quan, đó là bằng chứng mạnh hơn một ngưỡng dòng cố định.

### Ba mức cần phân biệt

| Hiện tượng | Quan sát | Cần điều tra gì? |
| --- | --- | --- |
| **Long Method** | Một phương thức có nhiều bước, nhánh, biến tạm hoặc tác dụng phụ | Các bước có cùng một nhiệm vụ rõ nghĩa không? |
| **Large Class** | Một lớp có nhiều trường, phương thức hoặc dòng mã | Những thành phần có cùng một lý do thay đổi không? |
| **God Class** | Một lớp biết quá nhiều về nhiều miền và điều phối/triển khai gần như mọi việc | Có nhiều trách nhiệm độc lập đang tập trung tại một nơi không? |

Một lớp lớn chưa chắc là God Class. Một lớp 200 dòng với các thao tác nhất quán cho cùng một kiểu dữ liệu có thể dễ duy trì hơn một lớp 70 dòng gọi tới sáu registry tổng quát. Mục tiêu là **gắn kết (*cohesion*) cao và phụ thuộc (*coupling*) hợp lý**, không phải đạt số file nhỏ hay lớn tùy ý.

## 2. Nhận diện Long Method qua chi phí hiểu và sửa

Một phương thức dễ hiểu thường có một mục đích có thể mô tả bằng tên rõ. Những dấu hiệu sau cho thấy phương thức có thể đang làm nhiều việc hơn cần thiết:

1. **Phải cuộn qua nhiều màn hình để thấy kết quả cuối**, trong khi có nhiều bước độc lập.
2. **Nhiều biến tạm sống lâu**, đổi giá trị hoặc được sử dụng ở những phần cách xa nhau.
3. **Nhiều mức lồng nhau** của `if`, `for`, `try` hoặc các nhánh điều kiện phủ định.
4. **Trộn logic tính toán với I/O**, ví dụ vừa tính phí, vừa gọi API, vừa ghi database, vừa gửi email.
5. **Nhiều mức trừu tượng trong cùng một đoạn**, như câu “xác nhận đơn hàng” đặt cạnh chi tiết “đọc dòng JDBC tiếp theo”.
6. **Khó kiểm thử một quy tắc riêng** vì chỉ có thể gọi toàn bộ luồng dài.
7. **Một sửa đổi nhỏ kéo theo việc hiểu nhiều mã không liên quan**, làm tăng rủi ro sửa nhầm.
8. **Thêm tính năng bằng cách nối thêm một khối `if` lớn**, thay vì xác định đúng khái niệm đang thay đổi.

Không nên coi mọi dấu hiệu là lỗi. Một thuật toán duyệt cây có nhiều bước liên tiếp nhưng gắn kết tốt có thể tự nhiên dài. Vấn đề là **chi phí nhận thức và phạm vi tác động**, không đơn thuần số dòng.

### Mức trừu tượng trộn lẫn

Đoạn sau nằm trong một phương thức điều phối nghiệp vụ:

```java
boolean eligible = subtotalVnd >= 500_000L;
preparedStatement.setLong(1, customerId);
while (resultSet.next()) {
    // ...
}
mailer.sendReceipt(...);
```

“Đủ điều kiện”, “bind tham số SQL”, “đọc ResultSet” và “gửi biên nhận” nằm ở **những mức khái niệm khác nhau**. Nếu đưa chi tiết SQL xuống repository và phép tính vào quy tắc miền, phần điều phối có thể diễn đạt luồng nghiệp vụ rõ ràng hơn.

Tuy nhiên, chuyển một dòng `preparedStatement.setLong(...)` sang một lớp tên `GenericDatabaseCommandExecutor` không tự tạo cải tiến. Ranh giới chỉ có ích khi lớp mới có **trách nhiệm và hợp đồng rõ**.

## 3. Nhận diện lớp quá nhiều trách nhiệm qua “lý do phải sửa”

Hãy tưởng tượng một lớp tên `OrderManager` chứa các phương thức:

```java
class OrderManager {
    void createOrder(...) { /* kiểm tra giỏ, tính giá, lưu đơn */ }
    void cancelOrder(...) { /* cập nhật trạng thái, trả lại tồn kho */ }
    void sendReceipt(...) { /* định dạng và gửi email */ }
    void exportOrdersToCsv(...) { /* định dạng CSV và ghi tệp */ }
    void syncPaymentProvider(...) { /* giao tiếp API thanh toán */ }
    void rebuildSearchIndex(...) { /* cập nhật chỉ mục tìm kiếm */ }
}
```

Đây là mã minh họa về **phân bố trách nhiệm**, không phải một class biên dịch nguyên xi vì các tham số `...` chưa được định nghĩa.

Để nhận diện lớp quá tải, thử hỏi: “Những sự kiện nào khiến lớp này phải thay đổi?”

| Yêu cầu thay đổi | Phần trong `OrderManager` bị ảnh hưởng | Chủ sở hữu kiến thức |
| --- | --- | --- |
| Đổi ngưỡng miễn phí giao hàng | Tính phí/định giá | Chính sách giá |
| Đổi mẫu email | `sendReceipt` | Trình bày/thông báo |
| Đổi định dạng CSV | `exportOrdersToCsv` | Xuất báo cáo |
| Đổi giao thức cổng thanh toán | `syncPaymentProvider` | Tích hợp thanh toán |
| Đổi trạng thái hủy đơn | `cancelOrder` | Vòng đời đơn hàng |
| Đổi cách đánh chỉ mục | `rebuildSearchIndex` | Tìm kiếm |

Nếu những thay đổi này thường **độc lập**, nhưng đều phải sửa và kiểm thử một lớp lớn, lớp có nhiều lý do thay đổi không liên quan. Đây là một cách vận dụng tư duy *Single Responsibility Principle* (SRP): mỗi thành phần nên có một **lý do thay đổi có tính gắn kết**, không phải “chỉ được có một phương thức”.

### Dấu hiệu Large/God Class thường gặp

- Có nhiều nhóm trường chỉ phục vụ một vài phương thức khác nhau, ví dụ `mailClient` chỉ dùng ở `sendReceipt`, `csvWriter` chỉ dùng ở `exportOrders`.
- Có nhiều phương thức không chia sẻ cùng bất biến hoặc dữ liệu miền.
- Một thay đổi ở một tính năng làm lớp phải biên dịch, review hoặc test lại những phần khác.
- Lớp biết chi tiết nhiều thư viện và hạ tầng: SQL, HTTP, SMTP, định dạng file.
- Constructor nhận một danh sách phụ thuộc dài vì lớp làm quá nhiều việc.
- Tên lớp rất rộng như `Manager`, `Processor`, `Helper`, `Util` nhưng chức năng thực tế trải rộng.
- Các phương thức liên tục truyền đi nhiều biến/đối tượng chỉ để vượt qua phần logic không liên quan.

Tên `Manager` hoặc nhiều dependency **chỉ là tín hiệu**, không phải kết luận. Một application service có nhiệm vụ điều phối nhiều hệ thống có thể hợp lý nếu nó không tự ôm chi tiết từng hệ thống. Cần xét lớp có **ra quyết định và thực hiện mọi việc** hay chỉ **điều phối hợp đồng đã tách rõ**.

## 4. Ví dụ Java: một phương thức checkout đang làm quá nhiều

Giả sử hệ thống bán hàng có những quy tắc đơn giản:

- Mã đơn và email không được rỗng.
- Giỏ phải có ít nhất một mặt hàng; SKU không rỗng, số lượng dương, đơn giá VND không âm.
- Tạm tính bằng tổng `quantity × unitPriceVnd`; phát hiện tràn số.
- Khách VIP hoặc giỏ từ 500.000 VND được miễn phí giao hàng; trường hợp còn lại phí 25.000 VND.
- Lưu đơn trước, sau đó gửi biên nhận. Nếu bước lưu thất bại, không gửi biên nhận.

Mô hình dữ liệu và hai hợp đồng I/O:

```java
import java.util.List;

record CartItem(String sku, int quantity, long unitPriceVnd) {}

record CheckoutInput(
        String orderId,
        String email,
        boolean vip,
        List<CartItem> items
) {}

record Receipt(
        String orderId,
        long subtotalVnd,
        long shippingFeeVnd,
        long totalVnd
) {}

interface OrderStore {
    void save(Receipt receipt);
}

interface ReceiptSender {
    void send(String email, Receipt receipt);
}
```

Phiên bản đầu tập trung phần lớn logic vào một phương thức:

```java
import java.util.Objects;

final class CheckoutManager {
    private final OrderStore store;
    private final ReceiptSender sender;

    CheckoutManager(OrderStore store, ReceiptSender sender) {
        this.store = Objects.requireNonNull(store);
        this.sender = Objects.requireNonNull(sender);
    }

    Receipt checkout(CheckoutInput input) {
        if (input == null) {
            throw new IllegalArgumentException("Checkout input is required");
        }
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new IllegalArgumentException("Order ID is required");
        }
        if (input.email() == null || input.email().isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
        if (input.items() == null || input.items().isEmpty()) {
            throw new IllegalArgumentException("Cart cannot be empty");
        }

        long subtotalVnd = 0L;
        for (CartItem item : input.items()) {
            if (item == null) {
                throw new IllegalArgumentException("Cart item is required");
            }
            if (item.sku() == null || item.sku().isBlank()) {
                throw new IllegalArgumentException("SKU is required");
            }
            if (item.quantity() <= 0) {
                throw new IllegalArgumentException("Quantity must be positive");
            }
            if (item.unitPriceVnd() < 0L) {
                throw new IllegalArgumentException("Negative unit price");
            }

            long lineTotal = Math.multiplyExact(
                    item.unitPriceVnd(), item.quantity());
            subtotalVnd = Math.addExact(subtotalVnd, lineTotal);
        }

        long shippingFeeVnd;
        if (input.vip() || subtotalVnd >= 500_000L) {
            shippingFeeVnd = 0L;
        } else {
            shippingFeeVnd = 25_000L;
        }

        long totalVnd = Math.addExact(subtotalVnd, shippingFeeVnd);
        Receipt receipt = new Receipt(
                input.orderId(), subtotalVnd, shippingFeeVnd, totalVnd);

        store.save(receipt);
        sender.send(input.email(), receipt);

        return receipt;
    }
}
```

Đoạn mã có thể hoạt động đúng với yêu cầu giả định. Nhưng để hiểu `checkout`, người đọc phải chuyển qua ít nhất bốn nhóm công việc:

1. Kiểm tra thông tin đầu vào.
2. Kiểm tra từng mặt hàng và tính tạm tính.
3. Áp dụng chính sách phí vận chuyển.
4. Lưu và gửi biên nhận.

Đây là dấu hiệu ứng viên **Extract Method/Extract Class**, chưa phải bằng chứng phải lập tức tạo bốn mươi lớp. Một bước tốt là **đặt tên rõ cho phần tính toán và tách phần thuần túy khỏi I/O**, đồng thời giữ thứ tự xử lý như cũ.

### Vấn đề testability nhìn từ ví dụ

Nếu muốn kiểm tra ngưỡng 499.999/500.000 VND, test phải gọi `checkout` và cung cấp `OrderStore`, `ReceiptSender`. Điều này vẫn có thể thực hiện bằng fake, nhưng phép tính giá có thể đáng được kiểm thử như một quy tắc độc lập.

Nếu sửa chính sách phí, hàm hiện phải được đọc chung với luồng email và lưu dữ liệu. Khi tính giá phức tạp hơn (khuyến mãi, thuế, vùng giao hàng), phương thức sẽ tiếp tục dài ra.

## 5. Bắt đầu bằng Extract Method nhỏ và có tên nghiệp vụ

**Extract Method** là đưa một đoạn mã làm nhiệm vụ rõ ràng vào phương thức riêng, rồi gọi phương thức đó từ chỗ cũ.

Thay vì viết:

```java
long shippingFeeVnd;
if (vip || subtotalVnd >= 500_000L) {
    shippingFeeVnd = 0L;
} else {
    shippingFeeVnd = 25_000L;
}
```

ta có thể có:

```java
private static final long FREE_SHIPPING_THRESHOLD_VND = 500_000L;
private static final long STANDARD_FEE_VND = 25_000L;

private static long shippingFeeVnd(boolean vip, long subtotalVnd) {
    if (vip || subtotalVnd >= FREE_SHIPPING_THRESHOLD_VND) {
        return 0L;
    }
    return STANDARD_FEE_VND;
}
```

Dòng sử dụng trở thành:

```java
long feeVnd = shippingFeeVnd(input.vip(), subtotalVnd);
```

Tên hàm cho biết **điều gì được tính**; hằng cho biết **ý nghĩa của ngưỡng**. Đây có thể là đủ nếu logic chỉ sử dụng tại một nơi và chưa có lý do thay đổi độc lập.

### Một extraction có ích thường có ba đặc điểm

- Đoạn được trích có **đầu vào và kết quả có thể giải thích**, không buộc người đọc biết biến mutable ở xa.
- Tên phương thức mô tả **khái niệm hoặc ý định**, không chỉ `doStep2`, `processData`.
- Phần gọi trở nên đọc được như các bước của bài toán, trong khi chi tiết ở tầng dưới có trách nhiệm riêng.

Ví dụ, `validateCartItems` có nghĩa hơn `helper1`. Nhưng nếu đưa một khối 5 dòng vào `calculatePartA` rồi thêm `calculatePartB` chỉ để hạ số dòng, mã có thể khó theo dõi hơn.

## 6. Tách phần định giá khi nó có lý do thay đổi riêng

Nếu quy tắc tính giá có khả năng phát triển độc lập (thay ngưỡng, thêm chương trình thành viên hoặc thuế), một lớp nhỏ theo nghiệp vụ có thể hữu ích.

Định nghĩa kết quả có tên:

```java
record CheckoutTotals(
        long subtotalVnd,
        long shippingFeeVnd,
        long totalVnd
) {}
```

Lớp chịu trách nhiệm kiểm tra các mặt hàng và tính phí:

```java
import java.util.List;

final class CartPricing {
    private static final long FREE_SHIPPING_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 25_000L;

    CheckoutTotals price(List<CartItem> items, boolean vip) {
        if (items == null || items.isEmpty()) {
            throw new IllegalArgumentException("Cart cannot be empty");
        }

        long subtotalVnd = 0L;
        for (CartItem item : items) {
            if (item == null) {
                throw new IllegalArgumentException("Cart item is required");
            }
            if (item.sku() == null || item.sku().isBlank()) {
                throw new IllegalArgumentException("SKU is required");
            }
            if (item.quantity() <= 0) {
                throw new IllegalArgumentException("Quantity must be positive");
            }
            if (item.unitPriceVnd() < 0L) {
                throw new IllegalArgumentException("Negative unit price");
            }

            long lineTotal = Math.multiplyExact(
                    item.unitPriceVnd(), item.quantity());
            subtotalVnd = Math.addExact(subtotalVnd, lineTotal);
        }

        long shippingFeeVnd =
                vip || subtotalVnd >= FREE_SHIPPING_THRESHOLD_VND
                        ? 0L
                        : STANDARD_FEE_VND;

        long totalVnd = Math.addExact(subtotalVnd, shippingFeeVnd);

        return new CheckoutTotals(
                subtotalVnd, shippingFeeVnd, totalVnd);
    }
}
```

Lớp này **không gọi database, email hoặc đồng hồ hệ thống**. Với cùng đầu vào và không có trạng thái ngoại vi, nó trả cùng kết quả hoặc ném cùng loại lỗi đã xác định. Vì vậy, các ca 499.999/500.000 VND hoặc tràn số có thể được kiểm thử cục bộ.

Không cần bắt `CartPricing` thực thi mọi thứ liên quan đến đơn hàng. Nó không nên biết cách gửi email, bắt lỗi JDBC hoặc xử lý retry của giao thức thanh toán. Tên và trách nhiệm đi cùng nhau.

### Chuyển dữ liệu có cấu trúc, tránh trích phương thức nhận quá nhiều tham số

Một dấu hiệu extraction chưa tốt:

```java
long calculate(
        String sku,
        int quantity,
        long unitPrice,
        boolean vip,
        String region,
        String currency,
        long discount,
        long tax,
        boolean weekend) {
    // ...
}
```

Nếu các tham số cùng thuộc một khái niệm ổn định, có thể dùng một kiểu dữ liệu miền với tên và bất biến phù hợp. Tuy nhiên, **đừng tạo một “context” chứa toàn bộ trạng thái hệ thống** chỉ để tránh danh sách tham số: `Map<String, Object>` hoặc `GenericContext` thường che mất hợp đồng và lỗi truyền nhầm.

Trong ví dụ định giá, `List<CartItem>` và `boolean vip` đã mô tả đủ dữ liệu đầu vào; `CheckoutTotals` giúp trả ba giá trị liên quan mà không cần mutable output parameters.

## 7. Phương thức điều phối sau khi tách trách nhiệm

`CheckoutService` có thể giữ trách nhiệm **điều phối một lần tạo đơn**, trong khi chi tiết tính giá nằm ở `CartPricing`:

```java
import java.util.Objects;

final class CheckoutService {
    private final CartPricing pricing;
    private final OrderStore store;
    private final ReceiptSender sender;

    CheckoutService(
            CartPricing pricing,
            OrderStore store,
            ReceiptSender sender
    ) {
        this.pricing = Objects.requireNonNull(pricing);
        this.store = Objects.requireNonNull(store);
        this.sender = Objects.requireNonNull(sender);
    }

    Receipt checkout(CheckoutInput input) {
        if (input == null) {
            throw new IllegalArgumentException("Checkout input is required");
        }
        requireText(input.orderId(), "Order ID");
        requireText(input.email(), "Email");

        CheckoutTotals totals = pricing.price(input.items(), input.vip());

        Receipt receipt = new Receipt(
                input.orderId(),
                totals.subtotalVnd(),
                totals.shippingFeeVnd(),
                totals.totalVnd());

        store.save(receipt);
        sender.send(input.email(), receipt);
        return receipt;
    }

    private static void requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " is required");
        }
    }
}
```

Ở phiên bản mới, người đọc có thể thấy **trình tự nghiệp vụ** ngay trong `checkout`:

```text
Kiểm tra thông tin bắt buộc
          |
          v
Định giá giỏ hàng
          |
          v
Tạo biên nhận
          |
          v
Lưu biên nhận
          |
          v
Gửi thông báo
          |
          v
Trả kết quả
```

Lợi ích không chỉ là ít dòng hơn. Mỗi thành phần có một lý do thay đổi dễ giải thích:

- `CartPricing`: quy tắc tính tiền và kiểm tra dòng hàng.
- `CheckoutService`: thứ tự điều phối quy trình checkout.
- `OrderStore`: hợp đồng lưu trữ.
- `ReceiptSender`: hợp đồng gửi biên nhận.

**Lưu ý:** ví dụ chưa giải quyết yêu cầu phân tán “lưu và gửi email phải cùng thành công hoặc cùng thất bại”. Nếu `store.save` đã ghi thành công mà `sender.send` thất bại, đơn vẫn có thể đã được lưu dù người gọi nhận exception. Điều này đã tồn tại ở bản cũ. Chỉ tách lớp **không tự sửa vấn đề tính nhất quán**; cần quyết định nghiệp vụ riêng và cơ chế phù hợp như outbox/idempotency khi có yêu cầu. Không được âm thầm thay hành vi trong một refactor được mô tả là “chỉ đổi cấu trúc”.

## 8. Từ Large Class tới các thành phần có tính gắn kết

Khi một lớp gồm nhiều nhóm phương thức ít liên quan, **Extract Class** có thể đưa một nhóm dữ liệu và hành vi có cùng lý do thay đổi sang thành phần riêng.

Ví dụ lớp `OrderManager` ban đầu kiêm tính giá, xuất file và gửi thông báo. Có thể tổ chức lại theo ranh giới:

| Trách nhiệm | Thành phần có thể sở hữu | Điều cần giữ rõ |
| --- | --- | --- |
| Tính tạm tính, phí, giảm giá | `CartPricing` hoặc `OrderPricingPolicy` | Quy tắc tiền và làm tròn |
| Điều phối checkout | `CheckoutService` | Thứ tự, lỗi và kết quả |
| Lưu/truy vấn đơn | `OrderStore` / `OrderRepository` | Hợp đồng dữ liệu, transaction |
| Tạo nội dung CSV | `OrderCsvExporter` | Header, escaping, encoding |
| Gửi biên nhận | `ReceiptSender` | Hợp đồng gửi, lỗi và retry |
| Hủy và chuyển trạng thái đơn | `OrderLifecycleService` hoặc mô hình `Order` | Chuyển trạng thái và bất biến |

Đây là **phân tích ví dụ**, không phải kiến trúc bắt buộc cho mọi ứng dụng. Nếu lớp chỉ có hai phương thức tính giá nhỏ và không có yêu cầu thay đổi độc lập, thêm một `PricingFactory`, `PricingRegistry` và `AbstractPricingHandler` có thể khiến hệ thống khó hiểu hơn.

### Tập trung theo lý do thay đổi, không phải ép từng động từ vào một lớp

Một phản ứng quá mức có thể là:

```text
ValidateOrderService
CalculateSubtotalService
DecideShippingService
ConstructReceiptService
SaveReceiptService
SendReceiptService
CheckoutCoordinatorService
```

Nếu mỗi service chỉ chứa một lời gọi chuyển tiếp, người đọc phải mở nhiều file để hiểu một quy trình đơn giản. Sự phân tách tốt cần **ranh giới có ý nghĩa**, không chỉ chia số dòng.

Một lớp `CartPricing` có thể sở hữu nhiều phép toán giá liên quan, vì chúng có thể chia sẻ quy tắc làm tròn, đơn vị tiền và bất biến. Không nhất thiết tách `addLineTotals` và `checkShippingThreshold` thành hai dịch vụ độc lập khi chúng cùng thay đổi và không có phụ thuộc riêng.

## 9. Tính gắn kết và phụ thuộc: kiểm tra sau khi tách

Hai khái niệm giúp đánh giá kết quả refactor:

**Cohesion (tính gắn kết):** các phương thức và dữ liệu trong cùng thành phần có phục vụ một khái niệm/mục đích chung không?

**Coupling (mức phụ thuộc):** để thay đổi hoặc kiểm thử thành phần này, phải hiểu và tác động bao nhiêu thành phần khác?

Ví dụ `CartPricing` có tính gắn kết tương đối rõ: dữ liệu đầu vào là mặt hàng và thông tin VIP, đầu ra là các số tiền. Nó không cần phụ thuộc SMTP hay SQL.

Một `CheckoutService` vẫn phụ thuộc `OrderStore` và `ReceiptSender`, nhưng phụ thuộc ở **cấp hợp đồng**, vì nó phải điều phối việc lưu và gửi. Một điều phối viên có nhiều phụ thuộc không nhất thiết là God Class nếu nó không tự triển khai chi tiết của từng adapter.

Cách đánh giá thực dụng:

- Khi đổi định dạng email, có cần sửa `CartPricing` không?
- Khi đổi quy tắc phí, có cần sửa adapter JDBC không?
- Khi đổi nhà cung cấp gửi email, có cần sửa công thức tiền không?
- Khi thêm cột CSV, có cần sửa quy trình checkout không?
- Khi chạy test phí tại ngưỡng, có phải khởi động database không?

Nếu câu trả lời đa số là **không**, ranh giới có thể đã cải thiện sự độc lập. Nhưng cũng cần tránh tạo quá nhiều tầng trừu tượng khiến mỗi thay đổi nhỏ phải sửa thêm factory, registry và cấu hình.

## 10. Rủi ro khi refactor: giữ nguyên hành vi trước khi cải tiến thiết kế

Chia một phương thức dài có thể làm thay đổi hành vi không chủ ý, dù mục tiêu chỉ là “dễ đọc hơn”.

Những điểm rủi ro trong ví dụ checkout:

1. **Thứ tự validation:** trường hợp vừa thiếu email vừa có item sai trước đây báo lỗi email trước; nếu đổi thứ tự, kết quả lỗi quan sát được thay đổi.
2. **Điều kiện biên:** `>= 500_000` khác `> 500_000`.
3. **Số học:** `Math.addExact` và `Math.multiplyExact` báo lỗi tràn số; thay thành toán tử thường có thể tạo giá trị sai.
4. **Tác dụng phụ:** `store.save` phải xảy ra trước `sender.send` theo hợp đồng hiện tại.
5. **Thời điểm lỗi:** input sai hoặc phép tính sai phải bị từ chối trước khi ghi dữ liệu.
6. **Bản chất collection:** sao chép, sắp xếp hoặc lọc lại giỏ hàng có thể đổi thứ tự hoặc nội dung.
7. **Transaction và retry:** di chuyển lệnh qua ranh giới transaction hoặc đổi cách bắt exception có thể làm thay đổi tính nhất quán.

Một refactor an toàn cần xác định **hành vi hiện hành** trước khi sửa. Nếu phát hiện hành vi cũ thực sự là lỗi, có thể sửa, nhưng nên coi đó là **thay đổi chức năng riêng** với test và đánh giá tác động tương ứng.

### Đừng thay exception thành giá trị mặc định vô tình

Ví dụ khi `CartPricing` phát hiện giá âm, nó từ chối đơn. Nếu một helper mới “tiện tay” dùng `Math.max(0, price)`, việc sửa tên và tách code đã lặng lẽ biến dữ liệu không hợp lệ thành giá 0. Đó không còn là refactor thuần cấu trúc.

Với nghiệp vụ tiền và quyền truy cập, giữ chính xác ý nghĩa lỗi thường quan trọng hơn việc giảm số nhánh.

## 11. Viết test đặc tả trước khi di chuyển logic

Một bộ test nhỏ có thể bảo vệ những quy tắc quan trọng. Ví dụ JUnit 5 cho `CartPricing`:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class CartPricingTest {
    private final CartPricing pricing = new CartPricing();

    @Test
    void nonVipBelowThresholdPaysShipping() {
        CheckoutTotals result = pricing.price(
                List.of(new CartItem("A", 1, 499_999L)),
                false);

        assertEquals(499_999L, result.subtotalVnd());
        assertEquals(25_000L, result.shippingFeeVnd());
        assertEquals(524_999L, result.totalVnd());
    }

    @Test
    void exactThresholdAndVipAreFree() {
        CheckoutTotals exactThreshold = pricing.price(
                List.of(new CartItem("A", 1, 500_000L)),
                false);
        CheckoutTotals vip = pricing.price(
                List.of(new CartItem("A", 1, 100_000L)),
                true);

        assertEquals(0L, exactThreshold.shippingFeeVnd());
        assertEquals(0L, vip.shippingFeeVnd());
    }

    @Test
    void rejectsInvalidInputAndOverflow() {
        assertThrows(IllegalArgumentException.class, () ->
                pricing.price(List.of(), false));
        assertThrows(IllegalArgumentException.class, () ->
                pricing.price(List.of(new CartItem("A", 0, 100L)), false));
        assertThrows(ArithmeticException.class, () ->
                pricing.price(
                        List.of(new CartItem("A", 2, Long.MAX_VALUE)),
                        false));
    }
}
```

Test này chứng minh các điều kiện **trên tập đã thử**, không khẳng định mọi trạng thái nghiệp vụ đều được bao phủ. Có thể bổ sung test đơn giá âm, SKU rỗng, tổng nhiều dòng tràn và đầu vào null.

Khi chuyển từ `CheckoutManager` sang `CheckoutService`, test theo hành vi của quy trình nên giữ vai trò kiểm tra trình tự I/O:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    @Test
    void savesBeforeSendingAndReturnsReceipt() {
        List<String> events = new ArrayList<>();
        OrderStore store = receipt -> events.add("saved");
        ReceiptSender sender = (email, receipt) -> events.add("sent");

        CheckoutService service =
                new CheckoutService(new CartPricing(), store, sender);

        Receipt receipt = service.checkout(new CheckoutInput(
                "O-1",
                "buyer@example.test",
                false,
                List.of(new CartItem("A", 1, 500_000L))));

        assertEquals(500_000L, receipt.totalVnd());
        assertEquals(List.of("saved", "sent"), events);
    }

    @Test
    void invalidCartDoesNotWriteOrSend() {
        List<String> events = new ArrayList<>();
        OrderStore store = receipt -> events.add("saved");
        ReceiptSender sender = (email, receipt) -> events.add("sent");

        CheckoutService service =
                new CheckoutService(new CartPricing(), store, sender);

        assertThrows(IllegalArgumentException.class, () ->
                service.checkout(new CheckoutInput(
                        "O-1",
                        "buyer@example.test",
                        false,
                        List.of(new CartItem("A", 0, 100L)))));
        assertTrue(events.isEmpty());
    }

    @Test
    void storageFailureDoesNotSendReceipt() {
        OrderStore store = receipt -> {
            throw new IllegalStateException("Store unavailable");
        };
        List<String> events = new ArrayList<>();
        ReceiptSender sender = (email, receipt) -> events.add("sent");

        CheckoutService service =
                new CheckoutService(new CartPricing(), store, sender);

        assertThrows(IllegalStateException.class, () ->
                service.checkout(new CheckoutInput(
                        "O-1",
                        "buyer@example.test",
                        false,
                        List.of(new CartItem("A", 1, 500_000L)))));
        assertTrue(events.isEmpty());
    }
}
```

Các test dùng fake/lambda để quan sát hành vi, không phụ thuộc database hoặc hệ thống email thật. Chúng **không thay thế integration test** cho transaction, lưu trữ và giao thức gửi. Khi thay đổi ranh giới dữ liệu hoặc xử lý lỗi, phải kiểm tra thêm ở mức phù hợp.

### Test tính tương đương giữa phiên bản cũ và mới

Có thể chạy cả `CheckoutManager` và `CheckoutService` với cùng đầu vào và fake riêng, rồi so sánh `Receipt` và chuỗi sự kiện. Với một tập đầu vào tiêu biểu, việc này giúp nhận ra sự khác biệt ngoài ý muốn. Tuy nhiên, nếu cả hai triển khai cùng chứa một lỗi nghiệp vụ, phép so sánh tương đương không thể phát hiện lỗi đó; vẫn cần test dựa trên yêu cầu.

## 12. Kỹ thuật refactor cho phương thức dài: chọn đúng công cụ

| Kỹ thuật | Khi nên cân nhắc | Rủi ro cần chú ý |
| --- | --- | --- |
| **Extract Method** | Một khối có ý định riêng và đầu vào/đầu ra rõ | Tên chung chung, truyền quá nhiều biến, giấu side effect |
| **Introduce/Extract Parameter Object** | Nhiều tham số cùng một khái niệm hoặc luôn đi chung | Tạo “context” quá rộng, mutable và thiếu validation |
| **Replace Temp with Query** | Biến tạm chỉ lưu một kết quả thuần túy có tên rõ | Tính lại nhiều lần gây tốn chi phí hoặc thay hành vi |
| **Guard Clauses** | Các trường hợp loại trừ sớm làm giảm lồng nhau | Thứ tự điều kiện và exception có thể thay đổi |
| **Split Phase** | Quy trình gồm các giai đoạn tự nhiên: parse → validate → compute | Làm thay đổi thứ tự tác dụng phụ hoặc mất trạng thái cần thiết |
| **Extract Class** | Một nhóm phương thức và dữ liệu có lý do thay đổi riêng | Tăng phụ thuộc chéo, phá bất biến khi di chuyển dữ liệu |
| **Move Method** | Hành vi sử dụng chủ yếu dữ liệu và quy tắc của thành phần khác | Vô tình mở rộng API nội bộ hoặc gây vòng phụ thuộc |

Đây là các kỹ thuật có thể phối hợp, không phải một chuỗi bắt buộc. Đôi khi chỉ cần đổi tên biến và dùng early return, không cần tạo thêm lớp.

### Bài toán “biến tạm” và phạm vi trạng thái

Một phương thức dài thường dùng các biến như `subtotal`, `discount`, `tax`, `fee`, `total`, `error` và `result`. Khi trích khối tính toán, nếu phải truyền 12 biến vào và ra, đó là dấu hiệu nên xem:

- Các giá trị nào cùng thuộc một khái niệm như `CheckoutTotals`?
- Có thể trả kết quả bất biến thay vì truyền mutable output không?
- Có cần tách giai đoạn tính toán và giai đoạn lưu trữ không?
- Có biến nào chỉ dùng vì các bước trước đang thay đổi trạng thái dùng chung không?

Không nên “sửa” bằng cách chuyển mọi biến cục bộ thành field của class. Việc đó có thể tạo **trạng thái chia sẻ và lỗi đồng thời** khi service được nhiều request sử dụng.

## 13. Refactor một lớp lớn: giữ bất biến và ranh giới sở hữu

Tách logic khỏi một lớp lớn đòi hỏi biết ai **sở hữu dữ liệu và đảm bảo tính nhất quán**. Ví dụ một lớp `Inventory` vừa quản lý số lượng, vừa tính phí giao hàng, vừa ghi log. Có thể tách định giá khỏi kho. Nhưng không nên tách thao tác trừ tồn kho thành ba lớp độc lập nếu chúng phải phối hợp nguyên tử để bảo vệ bất biến.

Một quyết định sai:

```text
InventoryReader đọc số lượng còn lại
       |
       v
InventoryPolicy quyết định có thể trừ
       |
       v
InventoryWriter ghi số lượng mới
```

Nếu hai request chạy đồng thời, cả hai có thể cùng đọc “còn 1” rồi cùng quyết định thành công. Việc “chia trách nhiệm” không thay transaction hoặc cập nhật nguyên tử.

Với những bất biến liên quan trạng thái dùng chung, cần cân nhắc:

- Giữ quyết định và cập nhật trong một ranh giới transaction hợp lý.
- Dùng cập nhật có điều kiện hoặc khóa/phiên bản khi cần chống ghi đè cạnh tranh.
- Tách phần tính toán thuần túy khỏi I/O **mà không phá một thao tác nguyên tử**.
- Ghi rõ kết quả nào còn không chắc chắn khi phụ thuộc ngoài timeout.

Điểm đến của refactor là **phân quyền sở hữu rõ hơn**, không phải phân tán mọi bước thành các service độc lập rồi hy vọng trạng thái vẫn nhất quán.

## 14. Phương thức dài do điều kiện nghiệp vụ phức tạp: xử lý thế nào?

Không phải mọi phương thức dài đều nên chia nhỏ đơn giản theo độ dài. Đôi khi vấn đề là bảng quy tắc hoặc máy trạng thái.

Ví dụ:

```java
if (status == PENDING && paymentConfirmed) {
    // ...
} else if (status == PAID && refundRequested) {
    // ...
} else if (status == CANCELLED && paymentConfirmed) {
    // ...
}
```

Nhiều nhánh có thể là dấu hiệu quy trình có **trạng thái và chuyển trạng thái** cần mô hình hóa. Một bảng chuyển trạng thái, enum hoặc phương thức theo hành vi nghiệp vụ có thể rõ hơn chia mỗi `if` thành `check1()`, `check2()`.

Khi điều kiện phụ thuộc nhiều chiều như vùng giao hàng, phân khúc khách hàng, ngày hiệu lực và sản phẩm, có thể dùng các chính sách chuyên biệt nếu chúng **thật sự thay đổi độc lập**. Nhưng đừng tạo rule engine động cho một vài điều kiện ổn định chỉ vì một phương thức đã dài.

Câu hỏi dẫn đường: “Người đọc đang gặp khó vì phải **nhớ nhiều điều kiện**, vì **quy tắc bị trộn**, hay vì **các quy tắc thực sự phức tạp**?” Mỗi nguyên nhân cần biện pháp khác nhau.

## 15. Số dòng, complexity, coupling và churn: tín hiệu hỗ trợ

Các công cụ phân tích có thể chỉ ra:

- **Method length / số dòng:** phương thức có nhiều chi tiết cần đọc.
- **Cyclomatic complexity:** số điểm quyết định của luồng điều khiển theo quy ước công cụ.
- **Cognitive complexity / độ sâu lồng nhau:** dấu hiệu người đọc phải giữ nhiều ngữ cảnh.
- **Class size / field count / dependency count:** lớp có phạm vi rộng hoặc nhiều yếu tố cần biết.
- **Churn:** file/lớp thay đổi nhiều trong một khoảng thời gian.
- **Lỗi hồi quy:** vùng mã thường xảy ra sự cố sau chỉnh sửa.

Không có ngưỡng “quá 30 dòng chắc chắn phải tách” phù hợp mọi dự án. Định nghĩa điểm complexity có thể khác giữa công cụ hoặc phiên bản. Những chỉ số này nên tạo **danh sách vị trí cần điều tra**, rồi kết hợp lịch sử thay đổi và rủi ro nghiệp vụ.

Một bảng phân tích giả định:

| Thành phần | Dấu hiệu | Bối cảnh | Ưu tiên điều tra |
| --- | --- | --- | --- |
| `CheckoutManager` | Nhiều trách nhiệm, sửa liên tục | Các thay đổi về phí, email, lưu trữ thường xung đột | Cao |
| `CsvParser.parse` | 120 dòng, nhiều nhánh | Mã ổn định, nhiều test, ít lỗi | Cần đánh giá trước khi sửa |
| `PaymentStateMachine` | Có nhiều trạng thái | Mô hình miền phức tạp thật, rủi ro cao | Cao dù không phải God Class |
| `ReportFormatter` | Nhiều dòng tạo nội dung | Một trách nhiệm rõ, đầu vào/ra minh bạch | Không nhất thiết refactor |

**Các đánh giá trong bảng chỉ là ví dụ minh họa**, không phải kết quả đo một repository cụ thể.

Một kỹ thuật thực tế là chọn **điểm giao nhau giữa khó hiểu, hay thay đổi và có tác động lớn**, thay vì chỉ chọn file dài nhất.

## 16. Quy trình refactor an toàn theo từng bước

Khi cần cải thiện Long Method hoặc Large Class, có thể dùng quy trình sau:

### Bước 1: Chọn một yêu cầu thay đổi cụ thể

Ví dụ: “Đổi chính sách miễn phí giao hàng nhưng không thay cách lưu hoặc gửi email”. Đừng bắt đầu bằng việc xóa nguyên một lớp chỉ vì nó bị công cụ cảnh báo.

### Bước 2: Ghi lại hợp đồng và tác dụng phụ

Liệt kê đầu vào hợp lệ, kết quả, exception, thứ tự I/O và bất biến. Nếu có transaction, xác định ranh giới transaction hiện tại. Với `CheckoutManager`, thứ tự “validate → calculate → save → send” là một phần cần chú ý.

### Bước 3: Viết hoặc củng cố test đặc tả

Bảo vệ các trường hợp tại ngưỡng, đầu vào rỗng/âm, overflow, lỗi lưu và thứ tự tác dụng phụ. Nếu hành vi hiện tại có lỗi nhưng chưa có yêu cầu sửa, ghi lại vấn đề để tách thay đổi chức năng khỏi refactor.

### Bước 4: Trích phương thức có tên rõ

Chọn một khối độc lập như `calculateShippingFeeVnd` hoặc `validateItems`. Kiểm tra đoạn trích có đưa vào quá nhiều biến hoặc phụ thuộc ẩn không.

### Bước 5: Chỉ tách lớp khi có lý do thay đổi riêng

Nếu tính giá tiếp tục phát triển và có thể kiểm thử độc lập, chuyển nó sang `CartPricing`. Nếu nó chỉ là phép so sánh hai dòng ổn định, có thể giữ một phương thức nhỏ trong lớp.

### Bước 6: Giữ và xác minh các ranh giới nhất quán

Không di chuyển lời gọi DB ra ngoài transaction, không tự đổi thứ tự gửi sự kiện và không nuốt lỗi chỉ để làm code ngắn. Với hoạt động I/O, bổ sung integration test khi cần.

### Bước 7: Chạy lại test và đọc như người bảo trì

Test pass chưa đủ nếu mã mới bắt người đọc đi qua quá nhiều lớp. Hãy mô phỏng một yêu cầu mới: “thêm phí vùng xa”. Nếu nơi cần sửa rõ ràng và tác động hẹp hơn, refactor có khả năng đạt mục tiêu.

### Bước 8: Ghi nhận quyết định trong review

Mô tả trách nhiệm nào đã được tách, hành vi nào được giữ và test nào bảo vệ. Khi quan trọng, ghi rõ những vấn đề chưa giải quyết như email thất bại sau khi đã lưu đơn.

Thực hiện từng bước nhỏ giúp dễ hoàn tác khi phát hiện thay đổi hành vi không chủ ý.

## 17. Những giải pháp sai thường gặp

**Chỉ nhìn số dòng để tách.** Một phương thức xử lý một bảng ánh xạ rõ ràng có thể dài nhưng gắn kết; chia nhỏ có thể chỉ tăng số nơi phải mở.

**Đặt helper tên chung chung.** `stepOne`, `processPart`, `doWork` không giúp người đọc hiểu nghiệp vụ, dù giảm số dòng trong phương thức gốc.

**Tạo class cho mỗi phép tính nhỏ.** Một lớp `SubtractDiscountService` chỉ có một dòng và một interface riêng có thể tạo thêm gián tiếp mà không giảm rủi ro.

**Chuyển biến cục bộ thành field chia sẻ.** Có thể gây lỗi concurrency, state rò rỉ giữa request và khó test.

**Dùng một “Context” rất lớn để truyền mọi thứ.** `Map<String, Object>` hoặc DTO chứa hàng chục thuộc tính không liên quan giấu hợp đồng và tăng phụ thuộc.

**Tách theo tầng mà không xét bất biến.** Di chuyển thao tác cập nhật ra ngoài transaction có thể làm mất tính nguyên tử.

**Đổi điều kiện trong lúc refactor.** Một ký hiệu `>` thành `>=`, đảo thứ tự nhánh hoặc sửa cách bắt lỗi có thể đổi hành vi.

**Đánh đồng nhiều dependency với God Class.** Một lớp điều phối có thể hợp lý khi các dependency là hợp đồng rõ ràng và lớp không tự cài đặt hết chi tiết.

**Di chuyển logic sang quá nhiều lớp.** Mỗi điểm complexity giảm nhưng đường đọc xuyên lớp dài hơn; kết quả có thể khó bảo trì hơn.

**Giữ nguyên mọi thứ vì “đã chạy ổn”.** Nếu một vùng mã làm mọi thay đổi trở nên rủi ro và đã có lỗi hồi quy, việc bỏ qua code smell cũng có chi phí thực.

## 18. Khi nào không nên vội refactor?

Có những tình huống giữ một phương thức hoặc lớp tương đối lớn là lựa chọn có cơ sở:

- Một thuật toán tuyến tính nhiều bước nhưng cùng mục tiêu, có tên và test rõ, người đọc dễ theo từ đầu đến cuối.
- Mã mô tả bảng trạng thái hoặc định dạng phức tạp nhưng ít thay đổi; chia nhỏ sẽ làm mất tầm nhìn tổng thể.
- Mã sinh tự động không nên sửa tay; cần thay generator hoặc schema nếu thật sự có vấn đề.
- Phần mã rất cũ, ổn định, ít thay đổi nhưng rủi ro cao khi tách; nên củng cố test/quan sát trước.
- Một đối tượng miền cần giữ nhiều thao tác cùng một bất biến; tách ra có thể làm mất quyền sở hữu trạng thái.

**Tránh refactor** không có nghĩa “không cần làm gì”. Có thể thêm test, tài liệu hóa quy tắc khó hoặc chuẩn bị ranh giới thay đổi trước khi tính năng tiếp theo xuất hiện.

Ngược lại, nếu một phương thức đang gây xung đột thường xuyên, một lớp bị nhiều nhóm sửa vì nhiều trách nhiệm không liên quan hoặc việc test một quy tắc nhỏ luôn đòi chạy toàn hệ thống, đó là bằng chứng thực tế để ưu tiên cải thiện.

## 19. Bài tập tình huống

### Tình huống A: phương thức 150 dòng nhưng chỉ một thuật toán

Một bộ phân tích CSV gồm 150 dòng, có các bước đọc ký tự, nhận dạng dấu nháy, xử lý escape và kết thúc bản ghi. Mã có test tốt và ít thay đổi.

Bạn sẽ quyết định refactor dựa vào số dòng hay đánh giá khả năng theo dõi trạng thái? Nếu tách, ranh giới nào giúp người đọc hiểu hơn mà không phá tính nhất quán của máy trạng thái?

### Tình huống B: lớp quản lý đơn hàng 2.000 dòng

`OrderManager` vừa tính giá, quản lý tồn kho, gửi email, tạo PDF và gọi cổng thanh toán. Các nhóm thay đổi template email thường xung đột với thay đổi logic thanh toán.

Hãy lập bảng “lý do thay đổi → nhóm phương thức/trường → chủ sở hữu mới”. Chọn một trách nhiệm để tách trước và xác định test cần bảo vệ.

### Tình huống C: refactor làm mất transaction

Một phương thức cũ cập nhật tồn kho và tạo đơn trong cùng transaction. Sau khi tách thành `InventoryService` và `OrderService`, hai thao tác được gọi độc lập, có thể thành công một phần.

Hãy phân biệt việc tách trách nhiệm với việc chuyển ranh giới nguyên tử. Đề xuất vị trí điều phối transaction và một integration test cho trường hợp bước thứ hai thất bại.

### Tình huống D: nhiều helper hơn nhưng khó đọc hơn

Một phương thức `calculateShippingFee` ban đầu 30 dòng bị chia thành 12 helper tên `partA`…`partL` và ba interface; người sửa cần mở sáu file để đổi một điều kiện.

Hãy chỉ ra vì sao số dòng của phương thức gốc giảm không đủ chứng minh cải tiến. Đề xuất cách đặt tên và tập hợp logic theo khái niệm thay vì số dòng.

### Tình huống E: lỗi đúng ngưỡng tiền

Trong lúc chuyển logic sang `CartPricing`, lập trình viên đổi `subtotalVnd >= 500_000L` thành `subtotalVnd > 500_000L`. Các test chỉ dùng 400.000 và 600.000 VND nên vẫn qua.

Hãy viết test tại 499.999, 500.000 và 500.001 VND. Giải thích vì sao kiểm thử biên quan trọng khi làm Extract Method/Class.

### Tình huống F: gửi email sau khi lưu thất bại

Một hệ thống checkout lưu đơn thành công nhưng dịch vụ email timeout. Lớp mới được tách đẹp, nhưng người dùng thử lại và tạo đơn trùng vì API trả lỗi.

Hãy phân biệt **mùi mã do nhiều trách nhiệm** với **bài toán nhất quán phân tán và idempotency**. Việc tách lớp giúp phát hiện ranh giới nào, và cần quyết định nghiệp vụ/kiểm thử bổ sung gì trước khi đổi hành vi?

Với mỗi tình huống, trả lời theo chuỗi: **triệu chứng → trách nhiệm đang trộn → nguyên nhân và rủi ro → thay đổi nhỏ nhất → test xác minh → chi phí trừu tượng mới**.

## 20. Ghi nhớ

**Phương thức dài** và **lớp tập trung quá nhiều trách nhiệm** là dấu hiệu cần đặt câu hỏi về chi phí đọc, thay đổi và kiểm thử, không phải lời kết luận tự động từ số dòng.

- Với phương thức dài, tìm các khối nghiệp vụ, mức trừu tượng bị trộn, biến tạm kéo dài và tác dụng phụ xen kẽ.
- Với lớp lớn, phân tích **những lý do thay đổi độc lập** và nhóm hành vi/dữ liệu có tính gắn kết.
- Bắt đầu bằng tên rõ và Extract Method; chỉ dùng Extract Class khi có ranh giới trách nhiệm thật sự.
- Giữ phần điều phối nghiệp vụ dễ theo dõi, không đẩy logic sang hàng loạt helper hoặc registry tổng quát.
- Đặc biệt bảo vệ điều kiện biên, xử lý lỗi, thứ tự side effect và transaction khi refactor.
- Dùng test hành vi, lịch sử thay đổi, complexity và phản hồi review để đánh giá lợi ích thật.
- Một lớp dài nhưng gắn kết có thể chấp nhận được; một lớp ngắn nhưng nhiều trách nhiệm vẫn có thể là mùi mã.

Một thiết kế chất lượng không nhất thiết có ít dòng nhất hay nhiều lớp nhất. Nó giúp người bảo trì nhìn ra **mỗi trách nhiệm thuộc về đâu, vì sao cần sửa ở đó và có thể kiểm chứng thay đổi mà không làm hỏng phần khác**.
