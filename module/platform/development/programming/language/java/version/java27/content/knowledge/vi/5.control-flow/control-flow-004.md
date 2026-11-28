# Switch statement và switch expression

## 1. Vai trò của switch trong điều khiển luồng

**switch** dùng để chọn một nhánh thực thi dựa trên giá trị hoặc dạng của một biểu thức. Cấu trúc này phù hợp khi một biến có nhiều trường hợp rời rạc, chẳng hạn mã trạng thái HTTP, loại giao dịch, lệnh CLI, ngày trong tuần hoặc trạng thái đơn hàng.

Java hiện có hai cách dùng chính:

- **Switch statement** là câu lệnh điều khiển luồng. Nó thực thi nhánh phù hợp nhưng không tạo ra giá trị để gán trực tiếp cho biến.
- **Switch expression** là biểu thức có kết quả. Nó chọn một nhánh và tạo ra một giá trị có thể gán, trả về hoặc kết hợp trong biểu thức khác.

~~~mermaid
flowchart TD
    A[Bieu thuc selector] --> B{Chon case phu hop}
    B -->|switch statement| C[Thuc thi nhanh]
    B -->|switch expression| D[Danh gia nhanh va tao gia tri]
    C --> E[Tiep tuc luong chuong trinh]
    D --> F[Gan, return hoac ket hop gia tri]
~~~

Switch expression được chuẩn hóa từ Java 14. Pattern matching trong switch được chuẩn hóa từ Java 21, cho phép kiểm tra kiểu và xử lý null trực tiếp trong các nhánh. Đây là những khả năng hiện hành có thể sử dụng trong Java 27 mà không cần bật preview.

## 2. Các kiểu selector và nhãn case

Với switch dùng nhãn hằng truyền thống, selector thường là một trong các kiểu:

- Kiểu nguyên thủy **byte**, **short**, **char** hoặc **int**.
- Kiểu bao tương ứng **Byte**, **Short**, **Character** hoặc **Integer**.
- **String**.
- Một kiểu **enum**.

Các kiểu **long**, **float**, **double** và **boolean** không dùng được với switch hằng truyền thống. Java hiện cũng có switch dùng pattern matching cho các kiểu tham chiếu rộng hơn; phần sau trình bày cách dùng này.

Nhãn **case** truyền thống phải là hằng số hợp lệ tại thời điểm biên dịch, chẳng hạn số nguyên, ký tự, chuỗi literal hoặc tên hằng enum. Không thể dùng một biến thông thường làm nhãn case. Các nhãn trong cùng switch không được trùng nhau.

Ví dụ với số nguyên:

~~~java
int priority = 2;

switch (priority) {
    case 1:
        System.out.println("Critical");
        break;
    case 2:
        System.out.println("High");
        break;
    case 3:
        System.out.println("Normal");
        break;
    default:
        System.out.println("Unknown");
}
~~~

Với **String**, việc so khớp phân biệt chữ hoa và chữ thường. Nhãn **"start"** không khớp với **"START"**. Với enum, viết tên hằng mà không cần tiền tố tên enum:

~~~java
enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}

OrderStatus status = OrderStatus.PAID;

switch (status) {
    case NEW:
        System.out.println("Đơn hàng mới");
        break;
    case PAID:
        System.out.println("Đã thanh toán");
        break;
    case SHIPPED:
        System.out.println("Đang giao hàng");
        break;
    case CANCELLED:
        System.out.println("Đã hủy");
        break;
}
~~~

## 3. Switch statement với nhãn dấu hai chấm

Cú pháp truyền thống dùng dấu hai chấm sau nhãn **case**:

~~~java
switch (statusCode) {
    case 200:
        System.out.println("Success");
        break;
    case 400:
    case 422:
        System.out.println("Invalid request");
        break;
    case 401:
        System.out.println("Unauthorized");
        break;
    default:
        System.out.println("Other response");
}
~~~

Sau khi tìm thấy nhãn phù hợp, chương trình bắt đầu thực thi từ vị trí đó và tiếp tục các câu lệnh phía sau cho đến khi gặp **break**, **return**, **throw** hoặc kết thúc cấu trúc switch. Nếu không có **break**, luồng có thể đi xuyên qua các nhánh kế tiếp. Hành vi này được gọi là *fall-through*.

Trong ví dụ trên, hai nhãn **400** và **422** cùng dẫn đến một phần xử lý. Đây là fall-through có chủ đích vì giữa hai nhãn không có câu lệnh. Nếu quên **break** sau một nhánh có nội dung, chương trình có thể thực thi nhầm cả nhánh tiếp theo.

Một switch statement không bắt buộc phải xử lý mọi giá trị selector. Nếu không nhãn nào khớp và không có **default**, switch kết thúc mà không thực thi nhánh nào. Điều này có thể phù hợp khi bỏ qua một số trường hợp là chủ đích; với dữ liệu nghiệp vụ, thường nên có nhánh xử lý rõ ràng cho giá trị không dự kiến.

## 4. Switch statement với arrow rules

Java hỗ trợ nhãn dạng mũi tên **->**. Mỗi nhánh có thể chứa một biểu thức lệnh, một khối lệnh hoặc một lệnh ném ngoại lệ. Nhánh arrow không tự động rơi xuống nhánh kế tiếp, vì vậy không cần viết **break** để ngăn fall-through.

~~~java
switch (statusCode) {
    case 200 -> System.out.println("Success");
    case 400, 422 -> System.out.println("Invalid request");
    case 401 -> System.out.println("Unauthorized");
    default -> System.out.println("Other response");
}
~~~

Có thể gom nhiều nhãn vào cùng một nhánh bằng dấu phẩy. Cách viết này làm rõ các giá trị có cùng hành vi:

~~~java
switch (command) {
    case "start", "restart" -> startService();
    case "stop" -> stopService();
    case "status" -> printStatus();
    default -> printUsage();
}
~~~

Nếu một nhánh cần nhiều câu lệnh, dùng block:

~~~java
switch (status) {
    case NEW -> {
        validateOrder();
        reserveInventory();
        saveOrder();
    }
    case PAID -> {
        createShipment();
        notifyCustomer();
    }
    case CANCELLED -> cancelPendingWork();
}
~~~

Trong block của switch statement, có thể dùng **break** để kết thúc switch sớm, **return** để trả về từ phương thức chứa switch hoặc **throw** để ném ngoại lệ. Arrow rule tự ngăn việc thực thi tiếp sang nhánh khác sau khi nhánh hoàn thành bình thường.

## 5. Switch expression tạo ra giá trị

Switch expression được dùng khi kết quả của việc chọn nhánh cần trở thành một giá trị. Thay vì khai báo biến rồi gán trong từng nhánh, có thể viết trực tiếp:

~~~java
String label = switch (status) {
    case NEW -> "Mới tạo";
    case PAID -> "Đã thanh toán";
    case SHIPPED -> "Đang giao";
    case CANCELLED -> "Đã hủy";
};
~~~

Biểu thức switch phải tạo ra một giá trị trên mọi đường thực thi bình thường thuộc miền giá trị mà trình biên dịch kiểm tra tính đầy đủ. Với enum, trình biên dịch có thể xác nhận tính đầy đủ khi tất cả hằng enum được liệt kê. Nếu selector là một miền giá trị rộng hơn, có thể dùng **default** để xử lý phần còn lại. Giá trị **null** vẫn cần được xử lý riêng bằng **case null** hoặc kiểm tra trước; **default** không tự khớp với null.

Ví dụ phân loại mã kết quả:

~~~java
String category = switch (statusCode) {
    case 200, 201, 204 -> "success";
    case 400, 401, 403, 404, 422 -> "client-error";
    case 500, 502, 503, 504 -> "server-error";
    default -> "other";
};
~~~

Kết quả của switch expression có thể được trả về trực tiếp:

~~~java
static String describe(OrderStatus status) {
    return switch (status) {
        case NEW -> "Đơn hàng đang chờ xử lý";
        case PAID -> "Đơn hàng đã thanh toán";
        case SHIPPED -> "Đơn hàng đã được gửi";
        case CANCELLED -> "Đơn hàng đã bị hủy";
    };
}
~~~

Cũng có thể dùng switch expression trong phép gán, câu lệnh **return**, đối số của lời gọi phương thức hoặc một biểu thức lớn hơn. Hãy ưu tiên biểu thức khi mỗi nhánh chỉ cần tính ra một kết quả; cách viết này giúp giá trị được xác định tại một điểm và giảm lỗi quên gán.

## 6. Dùng block và yield trong switch expression

Khi một nhánh cần khai báo biến cục bộ hoặc thực hiện nhiều bước trước khi tạo kết quả, dùng block và **yield**:

~~~java
int shippingFee = switch (region) {
    case "INNER_CITY" -> 20_000;
    case "SUBURB" -> 35_000;
    case "REMOTE" -> {
        int baseFee = 50_000;
        int surcharge = calculateRemoteSurcharge();
        yield baseFee + surcharge;
    }
    default -> throw new IllegalArgumentException(
        "Unsupported region: " + region
    );
};
~~~

**yield** kết thúc nhánh hiện tại và cung cấp giá trị cho switch expression. Nó khác **return**, vì **return** kết thúc phương thức chứa nó. Nó cũng khác **break**, vốn được dùng để kết thúc một cấu trúc điều khiển như switch statement hoặc vòng lặp.

Trong một block của switch expression, mọi đường thực thi bình thường phải tạo ra giá trị bằng **yield**; đường thực thi cũng có thể kết thúc đột ngột bằng lệnh như **throw** hoặc **return**. Ví dụ sau không hợp lệ vì nhánh block có đường đi đến cuối block mà không tạo ra giá trị:

~~~java
// Khong hop le: block khong yield gia tri tren moi duong
int result = switch (mode) {
    case "A" -> {
        if (enabled) {
            yield 1;
        }
    }
    default -> 0;
};
~~~

Có thể sửa bằng cách cung cấp kết quả cho mọi nhánh của điều kiện:

~~~java
int result = switch (mode) {
    case "A" -> {
        if (enabled) {
            yield 1;
        } else {
            yield 0;
        }
    }
    default -> 0;
};
~~~

Khi block chỉ có một phép tính đơn giản, không cần tạo block hoặc dùng **yield**; arrow expression trực tiếp dễ đọc hơn.

## 7. Tính đầy đủ và default

Tính đầy đủ (*exhaustiveness*) là yêu cầu quan trọng của switch expression. Trình biên dịch phải xác định được rằng mọi giá trị có thể đi vào biểu thức đều dẫn đến một nhánh tạo kết quả hoặc ném ngoại lệ.

Với enum, có thể liệt kê toàn bộ hằng:

~~~java
enum PaymentState {
    PENDING, APPROVED, REJECTED
}

PaymentState paymentState = PaymentState.PENDING;

String message = switch (paymentState) {
    case PENDING -> "Đang chờ";
    case APPROVED -> "Đã duyệt";
    case REJECTED -> "Bị từ chối";
};
~~~

Nếu thêm một hằng enum mới, mã nguồn switch không có nhánh tương ứng có thể không biên dịch khi được biên dịch lại. Đây là lợi ích của việc liệt kê đầy đủ các trạng thái mà ứng dụng cần xử lý.

Khi selector đến từ một miền mở hoặc có thể nhận giá trị mới mà mã nguồn không biết trước, **default** là cách xử lý phần còn lại:

~~~java
String description = switch (externalCode) {
    case "A1" -> "Accepted";
    case "R1" -> "Rejected";
    default -> "Unrecognized code";
};
~~~

Có một quyết định thiết kế cần cân nhắc với enum. Nếu muốn trình biên dịch nhắc khi enum được mở rộng, hãy liệt kê từng hằng và không thêm **default** một cách máy móc. Nếu dữ liệu có thể đến từ hệ thống bên ngoài, phiên bản khác hoặc nguồn không kiểm soát, hãy có nhánh dự phòng thích hợp. **default** giúp switch expression đầy đủ nhưng có thể khiến mã nguồn không còn cảnh báo rõ khi enum được bổ sung giá trị mới.

## 8. Xử lý null trong switch hiện đại

Với switch hằng truyền thống trên kiểu tham chiếu như **String** hoặc enum, selector là **null** sẽ gây **NullPointerException**. Nhãn **default** không tự động khớp với null.

Từ Java 21, switch có pattern matching được chuẩn hóa và hỗ trợ nhãn **case null**. Có thể xử lý rõ ràng trường hợp thiếu dữ liệu:

~~~java
String message = switch (command) {
    case null -> "Chưa cung cấp lệnh";
    case "start" -> "Đang khởi động";
    case "stop" -> "Đang dừng";
    default -> "Lệnh không được hỗ trợ";
};
~~~

Cú pháp này cũng dùng được trong switch statement:

~~~java
switch (command) {
    case null -> System.err.println("Command is required");
    case "start" -> startService();
    case "stop" -> stopService();
    default -> System.err.println("Unknown command");
}
~~~

Nhãn **case null** làm switch trở thành pattern switch. Không nên giả định rằng **default** thay thế được nhánh null; nếu null là đầu vào hợp lệ cần xử lý, hãy khai báo tường minh. Nếu null là dữ liệu vi phạm hợp đồng, có thể kiểm tra sớm bằng **Objects.requireNonNull** hoặc trả lỗi xác thực phù hợp.

## 9. Kết hợp switch với pattern matching

Pattern matching trong switch cho phép chọn nhánh theo kiểu của đối tượng và gắn biến mẫu để sử dụng ngay trong nhánh. Tính năng này đã là ngôn ngữ Java chính thức từ Java 21.

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "Không có giá trị";
        case String text when !text.isBlank() -> "Văn bản: " + text;
        case String text -> "Văn bản rỗng";
        case Integer number -> "Số nguyên: " + number;
        default -> "Kiểu dữ liệu khác";
    };
}
~~~

Trong ví dụ, **String text** kiểm tra đối tượng có kiểu String và tạo biến mẫu **text** có thể dùng trong nhánh. Guard **when** bổ sung điều kiện cho pattern; nếu chuỗi không rỗng, nhánh đầu tiên được chọn, còn chuỗi rỗng đi đến nhánh String tiếp theo. **default** xử lý các kiểu không được liệt kê.

Thứ tự nhánh có ý nghĩa. Một pattern tổng quát đặt trước có thể làm các pattern cụ thể phía sau không bao giờ được chọn; trình biên dịch sẽ phát hiện các trường hợp bị che khuất (*dominated labels*). Hãy đặt nhánh cụ thể trước nhánh tổng quát và chỉ dùng guard khi điều kiện thực sự cần thiết.

Pattern switch hữu ích khi mô hình dữ liệu gồm nhiều kiểu, chẳng hạn một hệ phân cấp sealed hoặc kết quả từ nhiều loại thông điệp. Với lựa chọn đơn giản giữa một số hằng số, switch truyền thống hoặc switch expression thường dễ đọc hơn.

## 10. So sánh switch statement và switch expression

| Tiêu chí | Switch statement | Switch expression |
|---|---|---|
| Mục đích | Thực thi nhánh lệnh | Chọn và tạo ra một giá trị |
| Cách dùng | Một câu lệnh độc lập | Trong phép gán, return hoặc biểu thức |
| Tính đầy đủ | Có thể không có nhánh cho mọi giá trị | Bắt buộc có kết quả cho mọi trường hợp |
| Arrow rule | Hỗ trợ, không fall-through | Hỗ trợ, mỗi nhánh tạo giá trị hoặc kết thúc bất thường |
| Block nhiều câu lệnh | Thực thi các lệnh trong block | Dùng yield để cung cấp giá trị |
| Default | Tùy yêu cầu nghiệp vụ | Cần khi chưa chứng minh được tính đầy đủ |
| Kết thúc nhánh | Có thể dùng break, return, throw | Dùng giá trị biểu thức, yield hoặc throw |

Một ví dụ cùng bài toán theo hai cách:

~~~java
// Switch statement
String statementLabel;
switch (status) {
    case NEW -> statementLabel = "Mới";
    case PAID -> statementLabel = "Đã thanh toán";
    case SHIPPED -> statementLabel = "Đang giao";
    case CANCELLED -> statementLabel = "Đã hủy";
    default -> statementLabel = "Không xác định";
}

// Switch expression
String expressionLabel = switch (status) {
    case NEW -> "Mới";
    case PAID -> "Đã thanh toán";
    case SHIPPED -> "Đang giao";
    case CANCELLED -> "Đã hủy";
};
~~~

Trong ví dụ thứ nhất, biến phải được khai báo trước và gán trong từng nhánh. Trong ví dụ thứ hai, toàn bộ giá trị được tính ngay tại nơi khai báo. Khi mục tiêu chỉ là tính một giá trị từ nhiều trường hợp, switch expression thường ngắn gọn và dễ kiểm tra hơn.

## 11. Chọn cấu trúc phù hợp và lỗi thường gặp

Dùng switch statement khi mỗi nhánh chủ yếu thực hiện hành động: gọi dịch vụ, ghi log, cập nhật trạng thái hoặc điều phối xử lý. Dùng switch expression khi mỗi nhánh tạo ra một giá trị: nhãn hiển thị, mức phí, chính sách, kết quả phân loại hoặc một đối tượng miền.

Một số lỗi phổ biến:

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Một nhánh thực thi tiếp nhánh sau | Dùng nhãn dấu hai chấm và thiếu break | Dùng arrow rule hoặc bổ sung break nếu thật sự cần |
| Switch expression báo không đầy đủ | Thiếu case, default hoặc nhánh ném ngoại lệ | Liệt kê đủ miền giá trị hoặc thêm nhánh dự phòng |
| Nhận NullPointerException | Selector là null trong switch không xử lý null | Kiểm tra đầu vào hoặc dùng case null trong pattern switch |
| Không biên dịch khi thêm enum mới | Switch expression liệt kê toàn bộ enum nhưng chưa thêm hằng mới | Bổ sung nhánh cho trạng thái mới và kiểm tra nghiệp vụ |
| Nhánh sau không thể tiếp cận | Pattern tổng quát đứng trước pattern cụ thể | Sắp xếp pattern cụ thể trước pattern tổng quát |
| Biểu thức block không tạo được giá trị | Một đường đi trong block không yield hoặc throw | Bảo đảm mọi đường đi đều yield hoặc kết thúc bất thường |
| Chuỗi không khớp dù nhìn giống nhau | String switch phân biệt hoa thường hoặc có khoảng trắng | Chuẩn hóa đầu vào theo quy tắc nghiệp vụ trước khi switch |

Không nên thêm **default** chỉ để làm trình biên dịch im lặng khi đang xử lý một enum nội bộ có miền giá trị đóng. Ngược lại, khi đọc mã từ hệ thống ngoài, cần có nhánh dự phòng để tránh bỏ sót giá trị mới hoặc không hợp lệ. Lựa chọn này phải dựa trên quyền kiểm soát miền dữ liệu và cách ứng dụng muốn phát hiện thay đổi.

## 12. Checklist sử dụng switch

- [ ] Chọn switch statement khi cần thực hiện hành động và switch expression khi cần tạo giá trị.
- [ ] Ưu tiên arrow rules để tránh fall-through ngoài ý muốn.
- [ ] Nếu dùng nhãn dấu hai chấm, xác định rõ nơi kết thúc nhánh.
- [ ] Liệt kê đầy đủ hằng enum khi muốn trình biên dịch phát hiện trạng thái mới.
- [ ] Dùng default cho miền dữ liệu mở hoặc đầu vào ngoài phạm vi kiểm soát.
- [ ] Xử lý null tường minh khi null là trường hợp cần hỗ trợ.
- [ ] Trong switch expression, mọi nhánh phải tạo giá trị hoặc ném ngoại lệ.
- [ ] Dùng yield cho block cần tính toán nhiều bước trong switch expression.
- [ ] Sắp xếp pattern cụ thể trước pattern tổng quát và tránh nhánh bị che khuất.
- [ ] Kiểm thử các giá trị biên, giá trị không hợp lệ, null và các trạng thái mới.

Switch hiện đại cung cấp một cách diễn đạt rõ ràng cho cả điều phối hành động lẫn tính toán giá trị. Việc chọn đúng dạng switch, khai báo miền giá trị đầy đủ và xử lý null có chủ đích giúp mã điều khiển luồng dễ đọc, dễ kiểm tra và an toàn hơn khi mô hình nghiệp vụ thay đổi.
