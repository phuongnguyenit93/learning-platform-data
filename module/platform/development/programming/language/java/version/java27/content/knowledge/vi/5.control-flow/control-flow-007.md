# Tách luồng xử lý phức tạp bằng guard clause

Khi một phương thức phải kiểm tra nhiều điều kiện trước khi thực hiện công việc chính, các câu lệnh `if` lồng nhau có thể khiến phần xử lý quan trọng bị đẩy sâu vào bên trong. **Guard clause** là cách viết các điều kiện chặn ngay ở đầu phương thức hoặc tại đầu một vòng lặp. Khi một điều kiện không thỏa mãn, chương trình kết thúc sớm nhánh hiện tại bằng `return`, `throw` hoặc `continue`; phần còn lại chỉ xử lý trường hợp hợp lệ.

Guard clause là một cách tổ chức luồng điều khiển bằng những câu lệnh Java tiêu chuẩn. Java 27 không giới thiệu một từ khóa `guard` riêng cho idiom này. Bài viết sử dụng các tính năng ngôn ngữ và API hiện hành của Java 27, chẳng hạn `return`, `throw`, `continue`, `Objects.requireNonNull` và pattern matching trong `switch`.

## 1. Vì sao cần guard clause?

Hãy xem một phương thức gửi thông báo cho khách hàng:

```java
public void sendReminder(Customer customer) {
    if (customer != null) {
        if (customer.isActive()) {
            if (customer.emailNotificationsEnabled()) {
                if (customer.email() != null && !customer.email().isBlank()) {
                    mailer.send(customer.email(), "Bạn có một thông báo mới");
                }
            }
        }
    }
}
```

Phương thức có nhiều cấp lồng nhau. Người đọc phải đi qua từng khối `if` mới nhìn thấy hành động chính. Khi thêm điều kiện, độ sâu tiếp tục tăng và rất dễ bỏ sót nhánh xử lý.

Nếu các điều kiện trên biểu thị những trường hợp không cần gửi thông báo, có thể viết lại:

```java
public void sendReminder(Customer customer) {
    if (customer == null) {
        return;
    }

    if (!customer.isActive()) {
        return;
    }

    if (!customer.emailNotificationsEnabled()) {
        return;
    }

    if (customer.email() == null || customer.email().isBlank()) {
        return;
    }

    mailer.send(customer.email(), "Bạn có một thông báo mới");
}
```

Luồng xử lý giờ được đọc từ trên xuống: loại bỏ từng trường hợp không đủ điều kiện, sau đó thực hiện hành động gửi thông báo. Các kiểm tra cũng trở thành những điểm dừng rõ ràng để đặt breakpoint hoặc viết kiểm thử.

Trong ví dụ này, `customer == null` được xem là một trường hợp có thể bỏ qua theo hợp đồng của phương thức. Nếu `customer` bắt buộc phải có, cách xử lý đúng sẽ là từ chối tham số bằng exception thay vì âm thầm `return`. Việc chọn kiểu guard phụ thuộc vào ý nghĩa nghiệp vụ, không chỉ phụ thuộc vào cú pháp.

## 2. Guard clause hoạt động như thế nào?

Một guard clause thường có hai phần:

1. Một điều kiện mô tả trường hợp không nên đi tiếp.
2. Một câu lệnh chuyển luồng ra khỏi phần xử lý hiện tại khi điều kiện đó đúng.

Các dạng thường gặp:

| Câu lệnh | Tác động | Trường hợp sử dụng |
|---|---|---|
| `return;` hoặc `return value;` | Kết thúc lời gọi phương thức hiện tại | Không có việc cần làm hoặc đã xác định được kết quả sớm |
| `throw exception;` | Phát sinh exception và chuyển quyền xử lý cho tầng gọi gần nhất có thể bắt exception | Đầu vào vi phạm hợp đồng hoặc trạng thái không cho phép thao tác |
| `continue;` | Bỏ phần còn lại của vòng lặp hiện tại và bắt đầu lượt kế tiếp | Bỏ qua phần tử không cần xử lý |
| `break;` | Thoát khỏi vòng lặp hoặc cấu trúc `switch` gần nhất phù hợp | Đã tìm được kết quả hoặc điều kiện yêu cầu dừng vòng lặp |

Trong một phương thức, `return` và `throw` là hai cách kết thúc sớm thường thấy nhất. Trong vòng lặp, `continue` giúp đưa điều kiện loại bỏ phần tử lên đầu thân vòng lặp. `break` có thể dùng để dừng vòng lặp sớm, nhưng ý nghĩa của nó là kết thúc vòng lặp chứ không phải bỏ qua riêng lượt hiện tại.

Theo Java Language Specification, `return`, `throw`, `continue` và `break` làm câu lệnh hoàn tất theo cách chuyển luồng (*abrupt completion*). Các câu lệnh phía sau trong nhánh đã bị kết thúc sẽ không được thực thi. Đây là cơ sở ngôn ngữ cho cách tổ chức guard clause.

## 3. Chọn `return`, `throw` hay `continue`

Điểm quan trọng nhất khi thiết kế guard clause là phân biệt một điều kiện biểu thị kết quả bình thường với một điều kiện biểu thị lỗi.

### Dùng `return` khi kết thúc sớm là kết quả hợp lệ

Ví dụ, hàm tính phí giao hàng không cần tính phí cho đơn hàng kỹ thuật số:

```java
import java.math.BigDecimal;
import java.util.Objects;

public BigDecimal calculateShippingFee(Order order) {
    Objects.requireNonNull(order, "order");

    if (order.isDigitalOnly()) {
        return BigDecimal.ZERO;
    }

    if (order.totalWeightGrams() <= 0) {
        return BigDecimal.ZERO;
    }

    return calculateFeeByWeight(order.totalWeightGrams());
}
```

Đơn hàng kỹ thuật số và đơn hàng không có khối lượng tính cước là những trường hợp hợp lệ theo ví dụ nghiệp vụ. Trả về `BigDecimal.ZERO` thể hiện kết quả bình thường, không phải một lỗi cần exception.

Với phương thức `void`, dùng `return;` để kết thúc khi không còn việc cần làm:

```java
public void refreshCache(CacheEntry entry) {
    if (entry == null || !entry.isExpired()) {
        return;
    }

    cache.reload(entry.key());
}
```

### Dùng `throw` khi điều kiện vi phạm hợp đồng hoặc trạng thái

Nếu một phương thức yêu cầu tham số bắt buộc, hãy thể hiện rõ điều đó:

```java
import java.util.Objects;

public Receipt createReceipt(Order order) {
    Objects.requireNonNull(order, "order");
    Objects.requireNonNull(order.lines(), "order.lines");

    if (order.lines().isEmpty()) {
        throw new IllegalArgumentException(
                "Đơn hàng phải có ít nhất một dòng sản phẩm"
        );
    }

    if (!order.isPaid()) {
        throw new IllegalStateException(
                "Chỉ tạo biên nhận cho đơn hàng đã thanh toán"
        );
    }

    return buildReceipt(order);
}
```

Hai loại exception trong ví dụ diễn đạt hai tình huống khác nhau:

- `IllegalArgumentException`: đối số được truyền vào không đáp ứng yêu cầu của phương thức, như danh sách dòng hàng rỗng.
- `IllegalStateException`: đối tượng có tồn tại nhưng trạng thái hiện tại không cho phép thực hiện thao tác, như đơn hàng chưa thanh toán.

`Objects.requireNonNull` phù hợp khi null vi phạm hợp đồng tham số. API này trả lại chính tham chiếu nếu khác null và ném `NullPointerException` nếu tham chiếu null; overload nhận thông điệp giúp chỉ ra tên tham số. Không nên dùng `NullPointerException` như một cách báo mọi loại lỗi nghiệp vụ.

### Dùng `continue` để bỏ qua phần tử trong vòng lặp

Giả sử cần tính tổng tiền của các hóa đơn đã được xác nhận:

```java
BigDecimal total = BigDecimal.ZERO;

for (Invoice invoice : invoices) {
    if (invoice == null) {
        continue;
    }

    if (!invoice.isConfirmed()) {
        continue;
    }

    total = total.add(invoice.amount());
}
```

Khi hóa đơn không hợp lệ hoặc chưa xác nhận, `continue` bỏ qua phần cộng tiền và chuyển sang hóa đơn tiếp theo. Phần xử lý chính không phải nằm trong một khối `if` lớn.

Chỉ dùng cách bỏ qua phần tử nếu đó là quy tắc nghiệp vụ. Nếu hóa đơn null cho thấy dữ liệu đầu vào bị hỏng và cần được báo lỗi, hãy ghi nhận hoặc ném exception theo hợp đồng của luồng xử lý thay vì âm thầm bỏ qua.

## 4. Viết lại cấu trúc `if` lồng nhau bằng guard clause

Xét phương thức xử lý yêu cầu rút tiền. Mã ban đầu:

```java
public Withdrawal withdraw(Account account, BigDecimal amount) {
    if (account != null) {
        if (amount != null) {
            if (amount.signum() > 0) {
                if (account.isActive()) {
                    if (account.balance().compareTo(amount) >= 0) {
                        account.debit(amount);
                        return new Withdrawal(amount, account.balance());
                    } else {
                        throw new IllegalStateException("Số dư không đủ");
                    }
                } else {
                    throw new IllegalStateException("Tài khoản không hoạt động");
                }
            } else {
                throw new IllegalArgumentException("Số tiền phải lớn hơn 0");
            }
        } else {
            throw new IllegalArgumentException("Số tiền không được null");
        }
    } else {
        throw new IllegalArgumentException("Tài khoản không được null");
    }
}
```

Mã có thể chạy đúng, nhưng các điều kiện hợp lệ và không hợp lệ đan xen trong nhiều tầng. Bản viết lại:

```java
public Withdrawal withdraw(Account account, BigDecimal amount) {
    if (account == null) {
        throw new IllegalArgumentException("Tài khoản không được null");
    }

    if (amount == null) {
        throw new IllegalArgumentException("Số tiền không được null");
    }

    if (amount.signum() <= 0) {
        throw new IllegalArgumentException("Số tiền phải lớn hơn 0");
    }

    if (!account.isActive()) {
        throw new IllegalStateException("Tài khoản không hoạt động");
    }

    if (account.balance().compareTo(amount) < 0) {
        throw new IllegalStateException("Số dư không đủ");
    }

    account.debit(amount);
    return new Withdrawal(amount, account.balance());
}
```

Phần thực hiện rút tiền giờ nằm ở cuối phương thức và không bị lồng sâu. Trước khi sửa mã thực tế, cần bảo đảm các điều kiện và thứ tự kiểm tra giữ nguyên ý nghĩa nghiệp vụ. Ví dụ này cũng làm rõ rằng kiểm tra số tiền null và số tiền không dương là hai điều kiện khác nhau.

## 5. Thứ tự kiểm tra guard clause

Thứ tự các guard ảnh hưởng đến cả tính đúng đắn lẫn thông điệp lỗi mà caller nhận được. Có thể cân nhắc các nguyên tắc sau:

### Kiểm tra null trước khi truy cập đối tượng

Không gọi phương thức trên tham chiếu trước khi xác định hợp đồng null của nó:

```java
public String displayName(Customer customer) {
    Objects.requireNonNull(customer, "customer");

    if (customer.name() == null || customer.name().isBlank()) {
        return "Khách hàng chưa có tên";
    }

    return customer.name().trim();
}
```

`Objects.requireNonNull` làm rõ rằng bản thân `customer` là bắt buộc; tên rỗng được xử lý như một trường hợp dữ liệu hợp lệ nhưng chưa có nội dung hiển thị.

### Kiểm tra cấu trúc trước khi kiểm tra nội dung

Với một request có nhiều trường, nên kiểm tra sự tồn tại của request và các collection trước khi truy cập phần tử hoặc tính toán dựa trên chúng:

```java
public void importLines(ImportRequest request) {
    Objects.requireNonNull(request, "request");
    Objects.requireNonNull(request.lines(), "request.lines");

    if (request.lines().isEmpty()) {
        throw new IllegalArgumentException("Không có dòng dữ liệu để nhập");
    }

    validateLines(request.lines());
    saveLines(request.lines());
}
```

### Ưu tiên điều kiện rẻ và không gây tác dụng phụ

Nếu nhiều điều kiện độc lập cùng cần kiểm tra, thường nên thực hiện những phép kiểm tra đơn giản trước các thao tác tốn tài nguyên. Ví dụ, xác thực định dạng cơ bản trước khi gọi dịch vụ bên ngoài. Tuy nhiên, thứ tự nghiệp vụ hoặc bảo mật có thể yêu cầu một kiểm tra khác phải diễn ra trước; hãy tuân thủ hợp đồng của hệ thống.

Tránh gọi method có side effect trong biểu thức guard. Một điều kiện kiểm tra nên dễ hiểu, có kết quả ổn định và không vô tình ghi dữ liệu, gửi request hoặc thay đổi trạng thái.

### Dùng short-circuit để bảo vệ biểu thức

Toán tử `&&` chỉ đánh giá vế phải khi vế trái là `true`; toán tử `||` chỉ đánh giá vế phải khi vế trái là `false`. Có thể tận dụng điều này để kiểm tra null trước khi gọi method:

```java
if (customer == null || customer.email() == null || customer.email().isBlank()) {
    return;
}
```

Nếu `customer` null, biểu thức dừng ở vế trái và không gọi `email()`. Nếu điều kiện đầu là `customer != null`, có thể dùng:

```java
if (customer != null && customer.email() != null
        && !customer.email().isBlank()) {
    send(customer.email());
}
```

Với nhiều điều kiện, hãy xuống dòng và đặt tên helper method nếu biểu thức trở nên khó đọc. Không gom mọi quy tắc nghiệp vụ thành một biểu thức boolean quá dài.

## 6. Kết hợp guard clause với API Java hiện hành

Java SE có sẵn các API giúp viết điều kiện rõ ràng. Dùng API phù hợp sẽ tránh tự tạo những phép kiểm tra lặp lại.

| Nhu cầu | API hoặc cách viết | Ví dụ |
|---|---|---|
| Từ chối tham chiếu null | `Objects.requireNonNull` | `Objects.requireNonNull(order, "order")` |
| Kiểm tra chuỗi rỗng hoặc chỉ chứa khoảng trắng | `String.isBlank` | `if (name.isBlank()) return;` |
| Kiểm tra collection không có phần tử | `Collection.isEmpty` | `if (items.isEmpty()) return;` |
| Kiểm tra kết quả Optional không có giá trị | `Optional.isEmpty` hoặc `orElseThrow` | `if (result.isEmpty()) return;` |
| Kiểm tra số nằm ngoài miền hợp lệ | So sánh theo kiểu dữ liệu | `if (amount.signum() <= 0) throw ...;` |

Ví dụ với `Optional`:

```java
public Receipt receiptFor(String orderId) {
    Objects.requireNonNull(orderId, "orderId");

    var orderResult = orderRepository.findById(orderId);
    if (orderResult.isEmpty()) {
        throw new OrderNotFoundException(orderId);
    }

    return buildReceipt(orderResult.orElseThrow());
}
```

Trong ví dụ, không tìm thấy đơn hàng là lỗi theo hợp đồng của phương thức nên guard ném exception. Nếu không tìm thấy là kết quả bình thường, chữ ký phương thức có thể trả `Optional<Receipt>` và dùng `Optional.empty()` thay vì ném exception.

Không cần thay mọi phép kiểm tra `if (value == null)` bằng một API tiện ích. Một phép kiểm tra trực tiếp vẫn phù hợp khi nó diễn đạt rõ quy tắc của đoạn mã. Hãy chọn cách viết dễ hiểu nhất và thống nhất với quy ước của dự án.

## 7. Guard clause trong vòng lặp và luồng xử lý collection

Guard clause trong vòng lặp thường dùng `continue` để tách phần tử cần bỏ qua khỏi phần xử lý chính.

Ví dụ, lọc các bản ghi có thể lập hóa đơn:

```java
List<Invoice> billableInvoices = new ArrayList<>();

for (Invoice invoice : invoices) {
    if (invoice == null) {
        continue;
    }

    if (!invoice.isApproved()) {
        continue;
    }

    if (invoice.total().signum() <= 0) {
        continue;
    }

    billableInvoices.add(invoice);
}
```

Các điều kiện loại bỏ đứng trước, phần thêm vào kết quả nằm ở cuối. Nếu logic chỉ là biến đổi và lọc dữ liệu đơn giản, Stream API cũng có thể làm rõ ý định:

```java
List<Invoice> billableInvoices = invoices.stream()
        .filter(Objects::nonNull)
        .filter(Invoice::isApproved)
        .filter(invoice -> invoice.total().signum() > 0)
        .toList();
```

`Stream.toList()` trả về danh sách không thể sửa đổi; các thao tác sửa đổi trên danh sách đó sẽ ném `UnsupportedOperationException`. Nếu caller cần danh sách có thể thay đổi, hãy tạo collection mutable một cách rõ ràng, chẳng hạn `new ArrayList<>(stream.toList())`.

Không nên chuyển một vòng lặp có side effect phức tạp sang Stream chỉ để tránh `if`. Với xử lý cần `break`, cập nhật trạng thái nhiều bước, xử lý exception theo từng phần tử hoặc kiểm soát thứ tự rõ ràng, vòng lặp truyền thống với `continue` có thể dễ đọc hơn.

## 8. Guard clause và guarded pattern trong switch

Java hiện đại còn có *guard* trong nhãn `case` của pattern matching `switch`, viết bằng từ khóa `when`. Đây là tính năng ngôn ngữ khác với idiom guard clause ở đầu phương thức.

Ví dụ sau dùng pattern matching for switch và guard `when`:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có dữ liệu";
        case String text when !text.isBlank() -> "Chuỗi: " + text;
        case String text -> "Chuỗi rỗng";
        case Integer number when number > 0 -> "Số dương";
        case Integer number -> "Số không dương";
        default -> "Kiểu dữ liệu khác";
    };
}
```

Trong đoạn mã:

- `case String text` và `case Integer number` là type pattern, cho phép kiểm tra kiểu và gắn tên biến cho giá trị phù hợp.
- `when !text.isBlank()` và `when number > 0` là điều kiện bổ sung để một pattern được chấp nhận.
- `case null` xử lý riêng giá trị null của selector; không nên giả định `default` tự động nhận null.
- Các nhánh được sắp xếp để trường hợp có điều kiện cụ thể được kiểm tra trước trường hợp tổng quát cùng kiểu.

Guard clause là cách thoát sớm khỏi method hoặc bỏ qua vòng lặp. Guard trong `case ... when` là điều kiện bổ sung cho một nhánh pattern của switch. Cả hai cùng dùng điều kiện để giới hạn luồng thực thi, nhưng có phạm vi và mục đích khác nhau. Pattern matching for switch và guarded patterns đã là tính năng chuẩn trong Java hiện đại; không cần bật preview để dùng ví dụ trên với Java 27.

## 9. Chia nhỏ phương thức khi guard clause vẫn chưa đủ

Guard clause giúp giảm độ sâu lồng nhau, nhưng không tự động làm một phương thức dài trở nên dễ hiểu. Nếu phần xử lý chính còn nhiều bước độc lập, hãy tách chúng thành các phương thức có tên diễn đạt mục đích.

Ví dụ:

```java
public Receipt checkout(Customer customer, Order order) {
    validateCustomer(customer);
    validateOrder(order);
    ensureCustomerCanCheckout(customer);
    ensureOrderCanBePaid(order);

    Payment payment = collectPayment(customer, order);
    return createReceipt(order, payment);
}

private void validateCustomer(Customer customer) {
    Objects.requireNonNull(customer, "customer");
    if (!customer.isActive()) {
        throw new IllegalStateException("Khách hàng không hoạt động");
    }
}

private void validateOrder(Order order) {
    Objects.requireNonNull(order, "order");
    if (order.lines().isEmpty()) {
        throw new IllegalArgumentException("Đơn hàng không có sản phẩm");
    }
}
```

Các helper method gom những kiểm tra thuộc cùng một khái niệm. Phương thức `checkout` thể hiện trình tự nghiệp vụ ở mức cao: xác thực, kiểm tra điều kiện, thu tiền và tạo biên nhận. Tên phương thức cần phản ánh hành động thật; tránh tạo các helper quá nhỏ chỉ để chuyển một câu lệnh sang nơi khác.

Một cách phân chia hữu ích là:

- Kiểm tra hợp đồng tham số ở ranh giới method.
- Kiểm tra trạng thái miền nghiệp vụ ở nơi có đủ ngữ cảnh.
- Tách phép tính hoặc thao tác có thể tái sử dụng thành helper có tên rõ ràng.
- Giữ phần thực hiện công việc chính thành một đoạn tuyến tính có thể đọc được.

## 10. Khi nào không nên dùng guard clause?

Guard clause không phải quy tắc bắt buộc cho mọi `if`. Có những trường hợp `if/else` hoặc `switch` thể hiện ý nghĩa rõ hơn.

### Khi hai nhánh là hai kết quả nghiệp vụ ngang hàng

```java
public String deliveryLabel(Delivery delivery) {
    if (delivery.isExpress()) {
        return "Giao nhanh";
    } else {
        return "Giao tiêu chuẩn";
    }
}
```

Hai nhánh là hai lựa chọn hợp lệ cùng cấp. Giữ `if/else` làm rõ sự phân đôi của kết quả.

### Khi nhiều nhánh cùng đóng góp vào một kết quả

Nếu mỗi nhánh cần cập nhật chung một cấu trúc hoặc tính một phần của kết quả, một cấu trúc điều kiện đầy đủ có thể dễ đọc hơn nhiều lệnh `return` rời rạc. Hãy chọn cách biểu diễn cho thấy rõ mối quan hệ giữa các trường hợp.

### Khi điều kiện thực sự là một lỗi cần được xử lý ở nơi khác

Không dùng `return` để âm thầm bỏ qua dữ liệu hỏng nếu caller cần biết thao tác thất bại. Ngược lại, không ném exception chỉ vì một trường hợp bình thường như không có kết quả tìm kiếm. Chữ ký phương thức và cách biểu diễn kết quả nên khớp với hợp đồng của API.

### Khi có nhiều guard trùng lặp

Nếu nhiều phương thức lặp lại cùng một nhóm kiểm tra, hãy xem xét tạo validator hoặc phương thức miền nghiệp vụ dùng chung. Không sao chép một danh sách guard dài vào mọi nơi vì các bản sao có thể dần khác nhau.

## 11. Các lưu ý về thứ tự thực thi và tài nguyên

`return`, `throw` và `continue` làm chuyển luồng ngay tại vị trí được thực thi. Tuy vậy, Java vẫn thực hiện các hành động dọn dẹp được quy định cho `finally` và `try`-with-resources khi luồng rời khỏi phạm vi tương ứng.

Ví dụ:

```java
public String readFirstLine(Path path) throws IOException {
    Objects.requireNonNull(path, "path");

    try (var reader = Files.newBufferedReader(path)) {
        String line = reader.readLine();
        if (line == null) {
            return "";
        }

        return line;
    }
}
```

Khi một guard `return` được thực thi, tài nguyên `reader` vẫn được đóng tự động trước khi phương thức trả về. Vì vậy, `try`-with-resources là cách quản lý tài nguyên phù hợp cho các thao tác file và stream hiện hành.

Tránh dùng `return` hoặc `throw` bên trong `finally` để ghi đè luồng điều khiển đã bắt đầu. Một `return` trong `finally` có thể che exception hoặc giá trị trả về từ khối `try`, làm mất thông tin quan trọng. `finally` nên dành cho việc dọn dẹp cần thiết; với tài nguyên triển khai `AutoCloseable`, ưu tiên `try`-with-resources.

Ngoài ra, hãy nhớ:

- `return` trong lambda kết thúc lần thực thi lambda đó, không tự động trả về từ phương thức bao ngoài.
- `continue` chỉ hợp lệ trong vòng lặp tương ứng; nó bỏ phần còn lại của lượt hiện tại và chuyển sang lượt tiếp theo.
- `break` thoát cấu trúc lặp hoặc switch mục tiêu, không tương đương với `continue`.
- Guard không thay thế đồng bộ hóa. Trong mã đa luồng, kiểm tra một trạng thái rồi thay đổi trạng thái có thể vẫn có race condition nếu thao tác không được bảo vệ phù hợp.

## 12. Kiểm thử các guard clause

Một phương thức có nhiều guard nên được kiểm thử cả từng trường hợp bị chặn lẫn đường xử lý thành công.

Với phương thức rút tiền, có thể xây dựng ma trận kiểm thử:

| Trường hợp | Kết quả mong đợi |
|---|---|
| `account` là null | Ném `IllegalArgumentException` với thông điệp tham số |
| `amount` là null | Ném `IllegalArgumentException` với thông điệp tham số |
| Số tiền bằng 0 | Ném `IllegalArgumentException` |
| Số tiền âm | Ném `IllegalArgumentException` |
| Tài khoản không hoạt động | Ném `IllegalStateException` |
| Số dư nhỏ hơn số tiền rút | Ném `IllegalStateException` và không trừ tiền |
| Dữ liệu hợp lệ | Trừ đúng số tiền và trả về biên nhận đúng |

Ngoài kết quả hoặc exception, hãy kiểm tra cả side effect. Ví dụ, nếu guard từ chối đơn hàng chưa thanh toán, dịch vụ thanh toán không được gọi và số dư không được thay đổi. Nếu vòng lặp bỏ qua một phần tử, phần tử đó không được đưa vào kết quả nhưng các phần tử hợp lệ phía sau vẫn phải được xử lý.

Một số câu hỏi hữu ích khi review:

1. Mỗi guard có diễn đạt một điều kiện có tên gọi hoặc ý nghĩa rõ ràng không?
2. Trường hợp bị chặn là lỗi, trạng thái không hợp lệ hay một kết quả bình thường?
3. Thứ tự guard có thể khiến một lỗi quan trọng bị che bởi lỗi khác không?
4. Có phép truy cập nào xảy ra trước khi tham chiếu được kiểm tra không?
5. Có side effect nào chạy trước khi mọi điều kiện bắt buộc được xác nhận không?
6. Phần xử lý chính có còn dễ đọc sau khi đưa guard lên đầu không?
7. Các guard có được kiểm thử riêng và có kiểm tra trạng thái sau khi bị từ chối không?

Không nên dùng câu lệnh `assert` để thay thế validation đầu vào trong ứng dụng. Assertion chủ yếu hỗ trợ kiểm tra giả định nội bộ khi phát triển và có thể bị tắt khi chạy nếu không bật assertion. Các điều kiện từ người dùng, request hoặc dữ liệu bên ngoài cần được kiểm tra bằng logic thực thi bình thường.

## 13. Tài liệu tham khảo chính thức

- [Oracle — Java Language Specification, Java SE 27, Chapter 14: Blocks, Statements, and Patterns](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html): ngữ nghĩa của `if`, `return`, `throw`, `continue`, `break`, `try`-with-resources và guarded patterns trong `switch`.
- [Oracle — `Objects` API, Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Objects.html): `requireNonNull`, `nonNull`, `checkIndex` và các tiện ích kiểm tra đối tượng.
- [Oracle — Java SE 27 API Specification](https://docs.oracle.com/en/java/javase/27/docs/api/): tài liệu API chuẩn dùng để kiểm tra các lớp và phương thức trong JDK 27.

Guard clause giúp phương thức thể hiện rõ các điều kiện dừng và giữ phần xử lý chính ở mức dễ theo dõi. Hãy chọn `return` cho kết quả kết thúc sớm hợp lệ, `throw` cho vi phạm hợp đồng hoặc trạng thái, và `continue` để bỏ qua lượt lặp. Khi các guard được sắp xếp đúng, không gây tác dụng phụ ngoài ý muốn và được kiểm thử theo từng nhánh, chương trình Java 27 sẽ có luồng xử lý rõ ràng hơn và dễ bảo trì hơn.
