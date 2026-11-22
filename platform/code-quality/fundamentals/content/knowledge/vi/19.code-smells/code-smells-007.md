# Biến hoặc trường tạm làm kéo dài trạng thái không cần thiết

Một phương thức cần tính tổng đơn hàng và phí vận chuyển. Thay vì giữ các kết quả trung gian trong biến cục bộ, lập trình viên đặt chúng vào những **trường của đối tượng** để các phương thức nhỏ khác cùng đọc và sửa. Mã có thể chạy đúng ở lần gọi đầu, nhưng từ thời điểm ấy, đối tượng luôn phải mang theo những giá trị chỉ có ý nghĩa **trong lúc tính**. Khi một yêu cầu khác chạy xen vào hoặc một ngoại lệ xảy ra giữa chừng, các trường có thể phản ánh dữ liệu của yêu cầu trước, trạng thái chưa hoàn tất hoặc nhiều yêu cầu bị trộn với nhau.

Trong chương **Mùi mã** của module **CODE_QUALITY_FUNDAMENTALS**, chủ đề này giúp nhận diện những biểu hiện khiến mã nguồn khó tin cậy, khó hiểu và khó thay đổi. **Mùi mã** (*code smell*) không phải một lỗi được chứng minh chỉ bằng cách nhìn tên trường. Nó là tín hiệu cho thấy thiết kế có thể đang đặt dữ liệu ở **phạm vi sống dài hơn mức cần thiết**, làm tăng số trạng thái mà người đọc và chương trình phải quản lý.

Nguyên tắc cốt lõi:

> Dữ liệu chỉ cần trong một phép tính nên tồn tại trong phạm vi của phép tính đó. Chỉ lưu trong trường đối tượng khi giá trị thực sự là một phần trạng thái có ý nghĩa qua các lần gọi.

## 1. Phân biệt biến cục bộ, trường tạm và trạng thái thực sự

Trong Java, **biến cục bộ** (*local variable*) được khai báo bên trong phương thức hoặc khối lệnh. **Trường** (*field*) là thành viên của lớp và tồn tại theo vòng đời của đối tượng hoặc, với **static field**, theo thời gian tồn tại của lớp trong class loader liên quan.

| Dạng dữ liệu | Ví dụ | Phạm vi sống điển hình | Thường hợp lý khi |
| --- | --- | --- | --- |
| Biến cục bộ | **long subtotalVnd** trong **calculate()** | Trong một lượt thực thi phương thức | Giá trị trung gian chỉ phục vụ lượt tính đó |
| Tham số | **boolean vip** | Trong lời gọi, theo hợp đồng tham số | Đầu vào được cung cấp từ bên gọi |
| Trường tạm đáng nghi | **this.currentSubtotal** chỉ được gán khi **quote()** chạy | Lâu bằng đối tượng, dù ý nghĩa chỉ tồn tại trong **quote()** | Thường nên chuyển về local hoặc đối tượng tính toán ngắn hạn |
| Trường trạng thái hợp lệ | **accountBalanceVnd** của một thực thể số dư | Qua nhiều thao tác có kiểm soát | Giá trị biểu diễn trạng thái nghiệp vụ lâu dài |
| Trường cấu hình | **final PricingPolicy policy** | Qua nhiều lời gọi | Phụ thuộc/cấu hình dùng chung được cấp vào khi tạo đối tượng |
| Cache được quản lý | Bảng tra cứu kết quả đã tính | Qua nhiều lời gọi | Có lý do đo được, khóa cache và quy tắc vô hiệu hóa rõ |

**Không phải cứ có biến “tạm” là xấu.** Biến cục bộ có tên rõ như **subtotalVnd**, **discountVnd** hay **isEligible** thường giúp mã dễ đọc. Mùi mã xuất hiện khi **dữ liệu ngắn hạn bị đẩy lên vùng lưu trữ dài hạn**, tạo ra mối quan hệ về thời gian mà người đọc không nhận thấy từ chữ ký phương thức.

### 1.1. Cách nhận diện trường tạm

Một trường đáng xem xét khi có một hoặc nhiều dấu hiệu:

- Chỉ được gán và đọc trong một **lượt tính toán** hoặc một nhóm phương thức luôn được gọi theo trình tự.
- Không đại diện cho trạng thái mà nghiệp vụ cần lưu **giữa hai lần gọi**.
- Phải đặt lại về **null**, **0**, **false** hoặc xóa thủ công trước hoặc sau mỗi lượt.
- Chỉ hợp lệ trong một giai đoạn của xử lý; phần còn lại của vòng đời đối tượng trường đó vô nghĩa.
- Một phương thức phụ chỉ hoạt động đúng sau khi phương thức khác đã gán trường.
- Kết quả của lượt gọi hiện tại có thể phụ thuộc phần dữ liệu còn sót từ lần gọi trước.
- Các lời gọi trên cùng đối tượng không an toàn nếu diễn ra đồng thời.

Những dấu hiệu trên là **gợi ý để điều tra**, không phải quy tắc tự động yêu cầu xóa mọi trường. Một cache, một state machine có vòng đời rõ hoặc một object builder đang được xây dựng từng bước có thể cần trường thay đổi.

## 2. Vì sao kéo dài trạng thái làm mã phức tạp hơn?

### 2.1. Tăng số điều kiện phải ghi nhớ

Nếu một phương thức chỉ dùng ba biến cục bộ, người đọc có thể theo dõi chúng trong phạm vi phương thức ấy. Khi chúng thành ba trường, người đọc phải tự hỏi:

1. Phương thức nào có thể sửa từng trường?
2. Giá trị hiện tại là của lần gọi nào?
3. Trường nào đã được gán, trường nào vẫn mang giá trị cũ?
4. Có phương thức nào đọc chúng trước khi khởi tạo không?
5. Đối tượng này có được dùng chung giữa các thread không?
6. Sau khi có ngoại lệ, trạng thái còn hợp lệ không?

Mỗi câu hỏi là một phần **gánh nặng nhận thức**. Phạm vi sống dài hơn cũng tạo thêm nhiều **đường chuyển trạng thái** cần kiểm tra.

### 2.2. Phụ thuộc vào thứ tự gọi (*temporal coupling*)

Ví dụ:

~~~java
public final class ReportDraft {
    private String title;
    private String content;

    public void prepareTitle(String rawTitle) {
        title = rawTitle.trim();
    }

    public void prepareContent(String rawContent) {
        content = rawContent.trim();
    }

    public String render() {
        return title + "\n" + content;
    }
}
~~~

Nếu **render()** được gọi trước hai bước chuẩn bị, kết quả có thể chứa chữ **null**. Nếu đối tượng được dùng lại cho báo cáo tiếp theo nhưng chỉ cập nhật một trường, báo cáo mới có thể chứa nội dung từ báo cáo trước.

API yêu cầu một **trình tự ngầm** mà kiểu dữ liệu và chữ ký không thể hiện đầy đủ. Nếu bản thảo thật sự là một đối tượng có vòng đời nhiều bước, cần mô hình trạng thái, validation và hợp đồng rõ. Nếu mục tiêu chỉ là định dạng một lần, việc giữ **title** và **content** trong trường có thể không cần thiết.

### 2.3. Trạng thái cũ và cập nhật một phần

Giả sử một lượt xử lý đi qua các bước:

~~~text
Gán subtotal của yêu cầu A
       |
       v
Tính shippingFee của A
       |
       v
Tạo kết quả A
~~~

Nếu bước hai ném ngoại lệ, trường **subtotal** có thể đã đổi trong khi **shippingFee** còn từ lần trước. Đối tượng lúc ấy chứa một tổ hợp không còn đại diện cho bất kỳ báo giá hoàn chỉnh nào.

Ngay cả khi tầng gọi không truy cập các trường này trực tiếp, một phương thức mới được thêm trong tương lai có thể vô tình dựa vào trạng thái dang dở. Việc sửa lỗi sẽ trở nên khó vì **đường lỗi và trạng thái còn sót** không được thể hiện ở kết quả trả về.

### 2.4. Nguy cơ với lời gọi đồng thời và tái nhập (*reentrancy*)

Một service được dùng lại cho nhiều yêu cầu có thể chạy nhiều phương thức trên **cùng một instance**. Nếu kết quả trung gian nằm trong trường, các lời gọi có thể ghi đè lẫn nhau.

Không chỉ đa luồng mới gây vấn đề. Một phương thức có thể gọi callback; callback lại gọi chính đối tượng khi lượt xử lý trước chưa xong. Đó là **tái nhập** và có thể gây lỗi tương tự khi trường đang chứa giá trị tạm.

Việc dùng **volatile**, **synchronized** hoặc **ThreadLocal** đôi khi thay đổi đặc tính truy cập, nhưng không tự trả lời câu hỏi cơ bản: **giá trị ấy có thực sự cần được lưu trong đối tượng không?**

## 3. Ví dụ Java: báo giá dùng trường trung gian

Giả sử cửa hàng có chính sách minh họa:

- Đơn giá và số lượng dòng hàng phải hợp lệ; tổng được tính bằng số nguyên VND.
- Khách VIP miễn phí vận chuyển nếu tổng tiền hàng từ **300.000 VND** trở lên.
- Mọi khách miễn phí nếu tổng từ **500.000 VND** trở lên.
- Các đơn còn lại trả **30.000 VND** phí vận chuyển.
- Ví dụ chỉ tính báo giá; không truy vấn DB, không thực hiện thanh toán hoặc áp dụng giảm giá.

### 3.1. Phiên bản có mùi mã

~~~java
import java.util.List;
import java.util.Objects;

public final class StatefulShippingCalculator {
    public record Line(long unitPriceVnd, int quantity) {
        public Line {
            if (unitPriceVnd < 0 || quantity <= 0) {
                throw new IllegalArgumentException("Invalid line");
            }
            Math.multiplyExact(unitPriceVnd, quantity);
        }

        public long amountVnd() {
            return Math.multiplyExact(unitPriceVnd, quantity);
        }
    }

    private long subtotalVnd;
    private long shippingFeeVnd;
    private boolean vip;

    public long quote(List<Line> lines, boolean isVip) {
        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Empty cart");
        }

        this.vip = isVip;
        this.subtotalVnd = 0L;
        for (Line line : lines) {
            this.subtotalVnd = Math.addExact(
                    this.subtotalVnd, line.amountVnd());
        }

        this.shippingFeeVnd =
                (this.vip && this.subtotalVnd >= 300_000L)
                || this.subtotalVnd >= 500_000L
                        ? 0L : 30_000L;

        return Math.addExact(
                this.subtotalVnd, this.shippingFeeVnd);
    }
}
~~~

Ở mức tuần tự, khi một lượt tính hoàn thành bình thường và không có ai sửa dữ liệu đầu vào, kết quả có thể đúng. Nhưng ba trường **subtotalVnd**, **shippingFeeVnd** và **vip** chỉ là dữ liệu của **một lần quote**. Chúng vẫn tồn tại sau khi phương thức kết thúc, mặc dù không có khái niệm “báo giá đang được lưu trong calculator” trong hợp đồng.

### 3.2. Một lịch chạy có thể tạo kết quả sai

Giả sử cùng một **StatefulShippingCalculator** được hai request sử dụng:

| Thời điểm | Request A: VIP, tổng 400.000 VND | Request B: khách thường, tổng 200.000 VND |
| --- | --- | --- |
| T1 | Đặt **vip = true** và **subtotalVnd = 400.000** | Chưa chạy |
| T2 | Tạm dừng trước khi tính phí | Đặt **vip = false**, đặt lại subtotal và tính thành **200.000** |
| T3 | Tiếp tục, đọc **vip = false** và **subtotalVnd = 200.000**, tính phí **30.000** | Có thể tiếp tục tính |
| T4 | Trả tổng dựa trên trường bị ghi đè, có thể **230.000** | Kết quả B tùy lịch chạy |

Theo hợp đồng, kết quả đúng của A phải là **400.000 VND**, vì khách VIP được miễn phí từ 300.000 VND. Lịch chạy minh họa cho thấy một kết quả có thể sai **không phải vì công thức nghiệp vụ**, mà vì dữ liệu trung gian bị chia sẻ giữa các lượt gọi.

Đây là **một lịch chạy có thể xảy ra**, không phải khẳng định mỗi lần chạy đa luồng đều tạo đúng kết quả 230.000. Trong Java, truy cập đồng thời không được đồng bộ vào các trường mutable còn tạo **data race**; vấn đề tính hiển thị bộ nhớ và interleaving khiến việc suy luận càng khó.

### 3.3. Vì sao đặt lại trường đầu phương thức chưa đủ?

Phiên bản trên đã đặt **subtotalVnd = 0** mỗi lần và cập nhật **vip** từ đầu vào. Nhưng:

- Hai lượt gọi vẫn có thể xen nhau và ghi đè.
- **shippingFeeVnd** có thể còn từ lần trước khi một lượt mới thất bại giữa chừng.
- Việc bổ sung phương thức phụ đọc trường sau này có thể lộ trạng thái dang dở.
- Người review phải bảo đảm tất cả đường đi đều đặt lại mọi trường, kể cả khi quy tắc được mở rộng.

**Đặt lại trạng thái tạm** chỉ giảm một số lỗi tuần tự, không loại bỏ nguyên nhân là **phạm vi sống và chia sẻ sai**.

## 4. Refactor: chuyển dữ liệu về phạm vi một phép tính

Cách đơn giản nhất thường là **Replace Temporary Field with Local Variable**: thay các trường không có vai trò dài hạn bằng biến cục bộ hoặc các giá trị được truyền giữa phương thức.

### 4.1. Phiên bản không lưu trạng thái tạm trong đối tượng

Tệp **ShippingQuoteCalculator.java**, dùng JDK 17 trở lên:

~~~java
import java.util.List;

public final class ShippingQuoteCalculator {
    private static final long VIP_FREE_FROM_VND = 300_000L;
    private static final long REGULAR_FREE_FROM_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 30_000L;

    private ShippingQuoteCalculator() {}

    public record Line(long unitPriceVnd, int quantity) {
        public Line {
            if (unitPriceVnd < 0 || quantity <= 0) {
                throw new IllegalArgumentException("Invalid line");
            }
            Math.multiplyExact(unitPriceVnd, quantity);
        }

        public long amountVnd() {
            return Math.multiplyExact(unitPriceVnd, quantity);
        }
    }

    public record Quote(
            long subtotalVnd,
            long shippingFeeVnd,
            long totalVnd) {}

    public static Quote calculate(List<Line> input, boolean vip) {
        List<Line> lines = List.copyOf(input);
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Empty cart");
        }

        long subtotalVnd = 0L;
        for (Line line : lines) {
            subtotalVnd = Math.addExact(
                    subtotalVnd, line.amountVnd());
        }

        boolean getsFreeShipping =
                (vip && subtotalVnd >= VIP_FREE_FROM_VND)
                || subtotalVnd >= REGULAR_FREE_FROM_VND;

        long shippingFeeVnd =
                getsFreeShipping ? 0L : STANDARD_FEE_VND;
        long totalVnd =
                Math.addExact(subtotalVnd, shippingFeeVnd);

        return new Quote(
                subtotalVnd, shippingFeeVnd, totalVnd);
    }
}
~~~

Điểm thay đổi chính:

1. **subtotalVnd**, **getsFreeShipping**, **shippingFeeVnd** và **totalVnd** chỉ tồn tại trong một lượt thực thi.
2. **vip** là tham số và không cần lưu thành trường.
3. Hàm trả một **Quote** có tên trường thể hiện rõ kết quả. Bên gọi không cần truy cập trạng thái bên trong calculator.
4. Các ngưỡng và mức phí là **static final** không thay đổi, không phải dữ liệu của một request.
5. **List.copyOf** tạo một snapshot danh sách phần tử theo cấu trúc; các phần tử **Line** là record chỉ chứa kiểu nguyên thủy, nên không bị sửa trong khi tính. Giả định dữ liệu đầu vào không bị sửa đồng thời trong lúc tạo bản sao.
6. **Math.addExact** và **Math.multiplyExact** báo lỗi tràn số thay vì lặng lẽ làm sai kết quả.

**Giới hạn của ví dụ:** chính sách chỉ dựa trên tổng tiền hàng và cờ VIP. Không có thuế, ưu đãi, trọng lượng, giao dịch hoặc dữ liệu thay đổi từ hệ thống khác. Việc trả về một record mới **không tự bảo vệ** khỏi race condition ở DB hoặc tác dụng phụ của quy trình thanh toán.

### 4.2. Ví dụ sử dụng và kết quả

~~~java
import java.util.List;

public final class ShippingExample {
    public static void main(String[] args) {
        var cart = List.of(
                new ShippingQuoteCalculator.Line(200_000L, 2));

        var vipQuote = ShippingQuoteCalculator.calculate(cart, true);
        var regularQuote =
                ShippingQuoteCalculator.calculate(cart, false);

        System.out.println(vipQuote.totalVnd());
        System.out.println(regularQuote.totalVnd());
    }
}
~~~

Đầu ra mong đợi:

~~~text
400000
430000
~~~

Hai lần gọi dùng cùng một danh sách đầu vào **bất biến theo hợp đồng** nhưng không chia sẻ biến trung gian. Việc gọi lần VIP không để lại trạng thái khiến lần thường bị ảnh hưởng.

### 4.3. Độ ngắn không phải mục đích

Phiên bản mới có thể dài hơn vì thêm **Quote**, tên biến và validation. Lợi ích không phải giảm số dòng mà là **giảm số trạng thái toàn cục theo vòng đời đối tượng**, giảm phụ thuộc vào thứ tự lời gọi và giúp kiểm thử quy tắc độc lập.

Không cần tạo một lớp mới cho mỗi biến trung gian. Các biến cục bộ có tên rõ ràng là lựa chọn tốt khi chúng phản ánh những bước của cùng một phép tính.

## 5. Khi tách phương thức, đừng vô tình chuyển local thành field

Một lý do thường gặp khiến dữ liệu tạm bị đưa thành trường là muốn tách phương thức dài:

~~~java
public final class InvoiceRenderer {
    private StringBuilder buffer;
    private String title;

    public String render(String rawTitle, String body) {
        buffer = new StringBuilder();
        title = rawTitle.trim();
        appendHeader();
        appendBody(body);
        return buffer.toString();
    }

    private void appendHeader() {
        buffer.append("# ").append(title).append('\n');
    }

    private void appendBody(String body) {
        buffer.append(body);
    }
}
~~~

Hai helper **appendHeader()** và **appendBody()** ngắn, nhưng đọc/ghi **buffer** và **title** mà chữ ký không thể hiện. Một người chỉ nhìn helper không biết nó phải được gọi sau bước nào. Nếu renderer được dùng chung cho các yêu cầu, hai lượt render có thể trộn nội dung.

### 5.1. Giữ quan hệ dữ liệu hiển thị qua tham số

~~~java
public final class InvoiceRenderer {
    public String render(String rawTitle, String body) {
        String title = rawTitle.trim();
        StringBuilder buffer = new StringBuilder();

        appendHeader(buffer, title);
        appendBody(buffer, body);
        return buffer.toString();
    }

    private void appendHeader(
            StringBuilder buffer, String title) {
        buffer.append("# ").append(title).append('\n');
    }

    private void appendBody(
            StringBuilder buffer, String body) {
        buffer.append(body);
    }
}
~~~

Phiên bản mới **vẫn dùng một đối tượng mutable StringBuilder**, nhưng quyền sở hữu của nó chỉ nằm trong **một lần render**. Các helper nhận rõ đối tượng đang sửa thay vì bí mật phụ thuộc trường của renderer.

Điều quan trọng không phải loại bỏ mọi giá trị mutable. Trong trường hợp này, **StringBuilder là dữ liệu cục bộ** hữu ích cho việc xây chuỗi. Nó không bị lưu làm trường và không được công bố cho bên ngoài trước khi hoàn thành.

**Giả định ví dụ:** rawTitle và body không null, dữ liệu là văn bản trong một định dạng minh họa, chưa có chính sách escape đầu ra hoặc giới hạn kích thước. Nếu kết quả được xuất ra HTML hay Markdown cho người dùng cuối, cần xem xét ngữ cảnh hiển thị và dữ liệu không đáng tin.

### 5.2. Khi nào helper cần nhận tham số và trả kết quả?

Một helper **thuần** có thể chỉ nhận dữ liệu cần thiết và trả một giá trị:

~~~java
private static long shippingFeeVnd(
        long subtotalVnd, boolean vip) {
    if (vip && subtotalVnd >= 300_000L) {
        return 0L;
    }
    return subtotalVnd >= 500_000L ? 0L : 30_000L;
}
~~~

Phương thức này thể hiện đầy đủ phụ thuộc trong hai tham số. Nó có thể được kiểm thử độc lập nếu thực sự là một quy tắc nghiệp vụ đáng tách.

Nếu helper cần quá nhiều tham số vì một phép tính thực sự có nhiều đầu vào gắn bó, có thể cân nhắc **một đối tượng dữ liệu có tên rõ nghĩa** thay vì đẩy tham số thành trường của service. Tuy nhiên, tránh tạo “context object” khổng lồ chứa dữ liệu không liên quan chỉ để giảm số tham số.

## 6. Cả biến cục bộ cũng nên có phạm vi vừa đủ

Không chỉ trường đối tượng, **biến cục bộ được khai báo quá sớm** cũng có thể khiến người đọc phải theo dõi một giá trị lâu hơn cần thiết:

~~~java
public void sendSummary(Order order) {
    String customerLabel = order.customerName().trim();

    validateOrder(order);
    reserveInventory(order);
    recordOrder(order);

    sendConfirmation(customerLabel);
}
~~~

Nếu **customerLabel** chỉ cần ở bước cuối, khai báo nó gần nơi dùng hơn có thể làm mục đích rõ ràng:

~~~java
public void sendSummary(Order order) {
    validateOrder(order);
    reserveInventory(order);
    recordOrder(order);

    String customerLabel = order.customerName().trim();
    sendConfirmation(customerLabel);
}
~~~

Tuy nhiên, hai đoạn **không đương nhiên tương đương về hành vi**. Nếu **validateOrder**, **reserveInventory** hoặc **recordOrder** có thể sửa tên khách hàng, hoặc nếu **customerName()** có tác dụng phụ, việc chuyển dòng khai báo sẽ đổi giá trị hoặc thời điểm lỗi.

Vì vậy, khi thu hẹp phạm vi biến:

- Xác định giá trị có cần được chụp lại **trước** một thao tác thay đổi trạng thái hay không.
- Kiểm tra thứ tự ném ngoại lệ và các tác dụng phụ quan trọng.
- Đặt biến ở vị trí **gần nơi dùng nhưng đúng thời điểm nghiệp vụ**.
- Không đổi thứ tự thực thi chỉ để đạt một quy tắc trình bày.

Một khối **if**, **for** hoặc **try** có phạm vi nhỏ thường là nơi tốt để khai báo giá trị tạm. Dù vậy, phạm vi lexical ngắn hơn **không bảo đảm** máy ảo Java sẽ thu gom đối tượng ngay khi ra khỏi khối; thời điểm thu gom còn phụ thuộc khả năng truy cập đối tượng và cơ chế JVM. Lợi ích chắc chắn hơn là **giảm phạm vi suy luận của lập trình viên**.

### 6.1. Đừng nhầm “biến trung gian” với “trạng thái thừa”

~~~java
long subtotalVnd = calculateSubtotal(lines);
long discountVnd = calculateDiscount(subtotalVnd, member);
long payableVnd = Math.subtractExact(subtotalVnd, discountVnd);
~~~

Ba biến cục bộ làm rõ **các bước nghiệp vụ** và có thể dễ đọc hơn một biểu thức lồng nhiều lời gọi. Không có lý do để xóa hết chúng chỉ vì tên “biến tạm”.

Mùi mã cần giải quyết là **dữ liệu sống quá lâu, khó biết ai sở hữu hoặc tạo phụ thuộc thời gian**, không phải mọi phép tính có bước trung gian.

## 7. Field thực sự có ý nghĩa khi nào?

Không nên hiểu bài học thành “Java class càng ít field càng tốt”. Object-oriented design cần trường để lưu **danh tính, cấu hình, mối quan hệ và trạng thái nghiệp vụ có vòng đời**.

### 7.1. Trạng thái nghiệp vụ kéo dài giữa các lời gọi

~~~java
public final class Reservation {
    public enum Status {
        PENDING, CONFIRMED, CANCELLED
    }

    private final String reservationId;
    private Status status = Status.PENDING;

    public Reservation(String reservationId) {
        if (reservationId == null || reservationId.isBlank()) {
            throw new IllegalArgumentException("Invalid reservation ID");
        }
        this.reservationId = reservationId;
    }

    public void confirm() {
        if (status != Status.PENDING) {
            throw new IllegalStateException(
                    "Only pending reservations can be confirmed");
        }
        status = Status.CONFIRMED;
    }

    public Status status() {
        return status;
    }
}
~~~

Trong ví dụ, **status** là một phần trạng thái có ý nghĩa của đặt chỗ qua các bước nghiệp vụ. Nó không phải dữ liệu trung gian chỉ có ích trong lúc một phương thức tính toán chạy. **reservationId** cũng là thuộc tính lâu dài của đối tượng.

Ví dụ này chỉ minh họa mô hình trong bộ nhớ, không tự bảo đảm an toàn khi nhiều thread cùng thao tác hoặc khi lưu vào DB. Hệ thống thực cần kiểm soát chuyển trạng thái cạnh tranh và đồng bộ với nơi lưu trữ phù hợp.

### 7.2. Cấu hình và phụ thuộc được chia sẻ

~~~java
public final class PricingService {
    private final PricingPolicy policy;
    private final PriceRepository repository;

    public PricingService(
            PricingPolicy policy, PriceRepository repository) {
        this.policy = policy;
        this.repository = repository;
    }
}
~~~

**PricingPolicy** và **PriceRepository** là các kiểu phụ thuộc minh họa. Trường **final** chứa phụ thuộc được sử dụng qua nhiều lượt gọi không phải “temporary field”. Dù vậy, phải xem chính đối tượng phụ thuộc có an toàn để dùng chung hay không; **final** cố định tham chiếu, **không** làm đối tượng được tham chiếu tự động bất biến hoặc thread-safe.

### 7.3. Builder hoặc phiên làm việc có vòng đời rõ

Một builder có thể giữ các giá trị người dùng cung cấp qua nhiều lệnh **with...** rồi dùng **build()** để tạo đối tượng cuối cùng. Đây có thể là chủ đích nếu:

- Builder được tạo mới cho **một lần xây dựng**, không dùng chung bừa bãi.
- Mỗi trạng thái của builder có quy tắc dễ hiểu.
- **build()** kiểm tra đầy đủ trường bắt buộc và tạo kết quả hợp lệ.
- Tài liệu nói rõ builder có thể dùng lại hay không và có thread-safe không.

Trái lại, một singleton service vừa làm builder cho nhiều request vừa lưu các trường như **currentCustomer** thường là dấu hiệu nguy hiểm.

### 7.4. Phân biệt bằng câu hỏi về vòng đời

| Câu hỏi | Dấu hiệu trường hợp lý | Dấu hiệu trường tạm |
| --- | --- | --- |
| Giá trị có ý nghĩa sau khi phương thức kết thúc? | Có, ví dụ trạng thái đặt chỗ | Không, chỉ phục vụ tính tổng một lượt |
| Lần gọi sau có chủ đích cần kết quả trước? | Có, theo hợp đồng | Không, mỗi lần phải độc lập |
| Ai được phép sửa giá trị? | Có phương thức chuyển trạng thái kiểm soát | Nhiều helper ghi tùy thứ tự |
| Cần reset trước mỗi lượt? | Không, hoặc reset chính là nghiệp vụ có hợp đồng | Có, chỉ để tránh nhiễm dữ liệu cũ |
| Có ý nghĩa khi dùng chung instance? | Được thiết kế và đồng bộ phù hợp | Nguy cơ trộn trạng thái các request |

## 8. Trạng thái dẫn xuất và cache: hai trường hợp dễ nhầm

### 8.1. Lưu cả dữ liệu gốc lẫn tổng tính lại

~~~java
public final class MutableCart {
    private final List<Line> lines = new ArrayList<>();
    private long totalVnd;

    public void add(Line line) {
        lines.add(line);
        totalVnd = Math.addExact(totalVnd, line.amountVnd());
    }
}
~~~

**Line** là kiểu minh họa có phương thức **amountVnd()**. Cấu trúc này cố giữ **totalVnd** đồng bộ với **lines**. Nếu bước cập nhật danh sách thành công nhưng **Math.addExact** ném ngoại lệ do tràn số, danh sách đã đổi còn tổng có thể chưa được cập nhật. Nếu sau này có hàm xóa/sửa dòng mà quên cập nhật tổng, hai nguồn dữ liệu mâu thuẫn.

Có hai hướng:

1. **Tính tổng từ dữ liệu gốc khi cần** nếu số phần tử nhỏ và chi phí phù hợp.
2. **Duy trì tổng dẫn xuất có kiểm soát** nếu có lý do hiệu năng hoặc nghiệp vụ, nhưng cần thứ tự cập nhật an toàn, bất biến và kiểm thử khi thao tác thất bại.

Ví dụ một cách tính từ dữ liệu gốc:

~~~java
public long totalVnd(List<Line> lines) {
    long total = 0L;
    for (Line line : lines) {
        total = Math.addExact(total, line.amountVnd());
    }
    return total;
}
~~~

Việc tránh lưu tổng dài hạn giúp giảm nhu cầu **đồng bộ hai biểu diễn của cùng một sự thật**. Tuy nhiên, không nên áp dụng cách tính lại vô điều kiện nếu dữ liệu lớn và tính tổng quá tốn kém; cần đánh giá chi phí thật.

### 8.2. Cache có thể là ngoại lệ hợp lệ

Cache qua nhiều lời gọi có thể hợp lý khi dữ liệu được dùng lại và chi phí tính toán lớn. Nhưng cần trả lời:

- **Khóa cache** bao gồm đủ dữ kiện quyết định kết quả chưa?
- Khi dữ liệu nguồn đổi, cache được **vô hiệu hóa** lúc nào?
- Cache có giới hạn số phần tử, bộ nhớ hoặc thời gian sống không?
- Có bị lẫn dữ liệu giữa khách hàng, tenant hoặc quyền truy cập không?
- Khi nhiều thread cùng đọc/ghi, có cơ chế đồng thời phù hợp không?
- Nếu cache lỗi hoặc hết hạn, hành vi dự phòng là gì?

**Cache có chính sách rõ** là trạng thái được thiết kế. Một trường **lastResult** chỉ được thêm để tránh truyền kết quả từ phương thức này sang phương thức khác thường chỉ là **trường tạm bị kéo dài vòng đời**.

### 8.3. Lazy initialization cần hợp đồng riêng

Một trường chỉ được tính khi lần đầu sử dụng có thể hợp lý nếu kết quả ổn định và chia sẻ giữa các lượt gọi. Nhưng lazy initialization còn cần xử lý:

- Khởi tạo thất bại rồi thử lại hay ghi nhớ lỗi?
- Hai thread cùng khởi tạo có tạo hai instance không?
- Đối tượng kết quả có mutable và được chia sẻ an toàn không?
- Khi dữ liệu nền thay đổi, giá trị cũ có trở nên sai không?

Không nên gọi mọi trường được gán muộn là code smell. Khác biệt chính là **giá trị có vai trò lâu dài theo hợp đồng không**.

## 9. Những cách “sửa nhanh” chưa xử lý nguyên nhân

### 9.1. Reset trường ở cuối hoặc trong finally

~~~java
try {
    calculateUsingFields();
} finally {
    currentOrder = null;
    subtotalVnd = 0L;
}
~~~

**calculateUsingFields** và **currentOrder** là thành phần minh họa. **finally** có thể giúp dọn một số trạng thái sau lỗi, nhưng trong thời gian **calculateUsingFields()** chạy, một thread khác vẫn có thể đọc hoặc ghi các trường tạm. Ngoài ra, một callback tái nhập cùng đối tượng có thể làm hai lượt xử lý chồng nhau trước khi reset.

**finally** là công cụ đúng cho việc giải phóng tài nguyên hoặc hoàn nguyên một trạng thái tạm **thực sự phải được thiết lập**, nhưng không phải lý do để duy trì các trường lẽ ra có thể trở thành biến cục bộ.

### 9.2. Đánh dấu phương thức synchronized

~~~java
public synchronized Quote calculate(Order order) {
    // Vẫn lưu dữ liệu một request trong các field.
    // ...
}
~~~

Đồng bộ hóa có thể ngăn hai thread cùng chạy **phương thức này trên một instance**, nếu mọi truy cập liên quan đều tuân thủ cùng cơ chế. Nhưng nó:

- Có thể làm các request phải chờ nhau và giảm khả năng xử lý song song.
- Không xử lý việc **các phương thức khác** đọc/ghi trường mà không đồng bộ tương ứng.
- Không xóa trạng thái còn sót sau một lượt thất bại.
- Không khiến một trường chỉ có ý nghĩa trong một phép tính trở thành trạng thái nghiệp vụ hợp lý.

Nếu dữ liệu trung gian có thể giữ trong local, **không tạo chia sẻ ngay từ đầu** thường đơn giản hơn việc dùng khóa để điều phối chia sẻ không cần thiết.

### 9.3. Biến các trường thành volatile

**volatile** hỗ trợ những bảo đảm nhất định về khả năng nhìn thấy và thứ tự bộ nhớ đối với một biến. Nó **không biến chuỗi nhiều thao tác** như “đặt subtotal, tính shipping, trả tổng” thành một giao dịch nguyên tử. Hai request vẫn có thể ghi đè nhau qua nhiều trường.

Đừng sửa code smell chia sẻ state bằng cách thêm **volatile** trên mọi trường rồi coi như thread-safe.

### 9.4. Dùng ThreadLocal cho dữ liệu request

**ThreadLocal** tạo vùng giá trị gắn với thread. Nó có thể có chỗ dùng trong một số cơ chế ngữ cảnh luồng, nhưng không nên là giải pháp mặc định khi dữ liệu hoàn toàn có thể truyền qua tham số:

- Thread pool **tái sử dụng thread**, nên giá trị cũ có thể còn lại nếu không remove đúng.
- Luồng xử lý bất đồng bộ có thể chuyển sang **thread khác**; ngữ cảnh không tự truyền theo yêu cầu trong mọi mô hình.
- Rò rỉ ngữ cảnh có thể gây trộn dữ liệu hoặc vấn đề bảo mật.
- Code khó thấy dữ liệu phụ thuộc vào đâu vì không xuất hiện ở chữ ký.

Khi cần cơ chế ngữ cảnh theo thread, hãy làm rõ quyền sở hữu, phạm vi, cleanup trong finally và cách truyền ngữ cảnh qua task; không coi ThreadLocal là thay thế tự nhiên cho biến cục bộ.

## 10. Khi phép tính quá phức tạp để chứa hoàn toàn trong một phương thức

Có những thuật toán cần nhiều bước và nhiều dữ liệu trung gian, nên việc truyền mười tham số qua hàng loạt helper sẽ gây nhiễu. Hai giải pháp vẫn có thể tránh trường sống lâu trong service.

### 10.1. Dùng đối tượng kết quả trung gian bất biến

~~~java
public record Totals(
        long subtotalVnd,
        long discountVnd,
        long shippingFeeVnd) {

    public long payableVnd() {
        long afterDiscount =
                Math.subtractExact(subtotalVnd, discountVnd);
        return Math.addExact(afterDiscount, shippingFeeVnd);
    }
}
~~~

Một bước tính có thể tạo **Totals** rồi chuyển nó sang bước tiếp theo. Dữ liệu cùng thuộc một khái niệm được gom lại, nhưng **không nằm trong trường của service dùng chung cho nhiều request**.

Việc tạo record không tự bảo đảm mọi tổ hợp trường đều hợp lệ; nếu **discountVnd** không được phép vượt subtotal, nên thêm validation tại constructor hoặc factory theo hợp đồng.

### 10.2. Tạo đối tượng tính toán dùng một lượt (*method object*)

Nếu thuật toán thực sự cần rất nhiều trạng thái trung gian để điều phối các bước, có thể đóng gói chúng trong một object ngắn hạn **được tạo mới cho mỗi lượt tính**:

~~~java
public final class QuoteUseCase {
    public Quote execute(QuoteRequest request) {
        QuoteCalculation calculation =
                new QuoteCalculation(request);
        return calculation.run();
    }
}
~~~

Đây là **pseudocode Java ở mức thiết kế**: **Quote**, **QuoteRequest** và **QuoteCalculation** là các kiểu chưa được khai báo trong đoạn. Điểm quan trọng là mỗi lượt tạo một **QuoteCalculation riêng**, và không lưu đối tượng này vào trường của service.

Một method object vẫn có trường mutable, nên bản thân nó **không thuần** và không tự an toàn đa luồng. Lợi ích là **thu hẹp vòng đời và chủ sở hữu trạng thái**. Giải pháp này nên là ngoại lệ có lý do khi cấu trúc local/helper thông thường không diễn đạt được thuật toán rõ ràng.

## 11. Kiểm thử hành vi sau khi refactor

Việc chuyển field về local nhìn có vẻ đơn giản, nhưng vẫn cần kiểm tra **hợp đồng hiện có**: giá trị biên, ngoại lệ, thứ tự tác dụng phụ và những trường hợp đầu vào không hợp lệ.

### 11.1. Kiểm thử JUnit 5 với đầu vào rõ ràng

Đây là ví dụ kiểm thử cho **ShippingQuoteCalculator** ở phần 4. JUnit Jupiter và JUnit Jupiter Params là dependency kiểm thử ngoài JDK:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class ShippingQuoteCalculatorTest {
    @ParameterizedTest
    @CsvSource({
        "true, 299999, 30000, 329999",
        "true, 300000, 0, 300000",
        "false, 499999, 30000, 529999",
        "false, 500000, 0, 500000"
    })
    void respectsFreeShippingThresholds(
            boolean vip, long subtotalVnd,
            long expectedShippingVnd, long expectedTotalVnd) {
        var line = new ShippingQuoteCalculator.Line(
                subtotalVnd, 1);
        var quote = ShippingQuoteCalculator.calculate(
                List.of(line), vip);

        assertEquals(subtotalVnd, quote.subtotalVnd());
        assertEquals(
                expectedShippingVnd, quote.shippingFeeVnd());
        assertEquals(expectedTotalVnd, quote.totalVnd());
    }

    @Test
    void twoCallsWithDifferentCustomersRemainIndependent() {
        var cart = List.of(
                new ShippingQuoteCalculator.Line(200_000L, 2));

        var vip = ShippingQuoteCalculator.calculate(cart, true);
        var regular = ShippingQuoteCalculator.calculate(cart, false);

        assertEquals(400_000L, vip.totalVnd());
        assertEquals(430_000L, regular.totalVnd());
        assertEquals(400_000L, vip.totalVnd());
    }

    @Test
    void rejectsInvalidLines() {
        assertThrows(IllegalArgumentException.class,
                () -> new ShippingQuoteCalculator.Line(100L, 0));
        assertThrows(IllegalArgumentException.class,
                () -> ShippingQuoteCalculator.calculate(
                        List.of(), false));
    }

    @Test
    void detectsOverflowWhenAddingLines() {
        var lines = List.of(
                new ShippingQuoteCalculator.Line(
                        Long.MAX_VALUE, 1),
                new ShippingQuoteCalculator.Line(1L, 1));

        assertThrows(ArithmeticException.class,
                () -> ShippingQuoteCalculator.calculate(lines, false));
    }
}
~~~

Các ca biên được suy ra từ chính sách: VIP **300.000** được miễn phí, khách thường **500.000** được miễn phí. Kiểm thử cũng cho thấy hai lượt tính liên tiếp không làm thay đổi kết quả trả về trước đó.

**Giới hạn của bằng chứng:** một kiểm thử tuần tự xanh không chứng minh rằng mọi mã dùng chung instance đều an toàn đồng thời. Phiên bản mới được thiết kế với biến trung gian cục bộ và **record Line bất biến**, nên việc không chia sẻ trạng thái tính toán có thể được lập luận trực tiếp từ cấu trúc mã. Nếu có cache, I/O hoặc đối tượng mutable khác được thêm vào, cần kiểm tra lại.

### 11.2. Kiểm thử đồng thời khi có rủi ro thật

Với một service thực sự được nhiều thread gọi, nên có kiểm thử hoặc điều phối chạy xen nhau ở những điểm chia sẻ nhạy cảm. Ví dụ:

- Hai yêu cầu sử dụng cùng một instance nhưng khác cờ VIP và tổng tiền.
- Một yêu cầu ném lỗi giữa chừng, yêu cầu khác bắt đầu ngay sau đó.
- Một callback gọi lại service trước khi lời gọi trước hoàn thành.
- Nhiều request cùng dùng kết nối, cache hoặc collection được chia sẻ.

Có thể dùng **CountDownLatch**, **CyclicBarrier** hoặc hạ tầng kiểm thử thích hợp để tạo lịch chạy quan trọng. Tuy nhiên, kiểm thử concurrency có thể không liệt kê được mọi interleaving. **Thiết kế loại bỏ chia sẻ không cần thiết** thường mang lại bằng chứng mạnh hơn việc chỉ chạy nhiều vòng test ngẫu nhiên.

### 11.3. Cẩn trọng với thay đổi hành vi khi refactor

Chuyển field sang local đôi khi làm lộ một **phụ thuộc ngầm mà hệ thống đang dựa vào**. Trước khi sửa, phải kiểm tra:

1. Có API nào đọc giá trị **lastComputedTotal** sau khi tính không?
2. Có callback hoặc hook dùng trạng thái nội bộ trong lúc phương thức chạy không?
3. Có phương thức nào cần dữ liệu của lượt trước theo hợp đồng không?
4. Có thao tác I/O hoặc kiểm tra lỗi bị đổi thứ tự không?
5. Có đối tượng mutable nào được chia sẻ qua tham số hoặc kết quả không?

Nếu **lastComputedTotal** thật sự là tính năng công khai, phải thiết kế hợp đồng cho nó: giá trị thuộc request nào, được lưu bao lâu, có thể được cập nhật đồng thời không? Không được xóa trường và coi mọi thay đổi là “refactor thuần túy” khi nó có thể phá hành vi bên gọi.

## 12. Quy trình thực hành khi gặp temporary field

Một cách xử lý có kiểm soát:

1. **Ghi lại hợp đồng hiện tại:** đầu vào, kết quả, lỗi, tác dụng phụ và quan hệ giữa các lời gọi.
2. **Tìm nơi gán/đọc trường:** trường được dùng ở những phương thức nào, có được đọc ngoài một lượt tính không?
3. **Xác định vòng đời đúng:** chỉ một biểu thức, một phương thức, một request hay toàn bộ vòng đời thực thể?
4. **Tìm những giả định thời gian:** helper có cần gọi sau bước chuẩn bị không, có reset ở đầu/cuối không?
5. **Ưu tiên thay bằng local:** nếu dữ liệu chỉ có ý nghĩa trong một lời gọi, đưa về local rồi truyền qua tham số/giá trị trả về.
6. **Tách những quy tắc có tên rõ:** đừng biến service thành tập helper phụ thuộc vào field bí mật.
7. **Cân nhắc object ngắn hạn khi cần:** tạo riêng cho một lượt thao tác, nêu rõ quyền sở hữu và không chia sẻ bừa bãi.
8. **Kiểm tra trạng thái dẫn xuất:** có cần lưu lại không, hay nên tính từ nguồn dữ liệu gốc?
9. **Chạy kiểm thử liên quan:** trường hợp thường, biên, lỗi, nhiều lượt gọi và đồng thời nếu có dùng chung instance.
10. **Review kết quả:** số trường giảm có giúp cách dùng API rõ hơn và giảm đường trạng thái không hợp lệ không?

**Tiêu chí thành công** không phải “xóa được nhiều field”, mà là: mỗi giá trị được lưu **đúng nơi có trách nhiệm**, các phụ thuộc được thể hiện rõ và các lượt xử lý không vô tình tác động lẫn nhau.

## 13. Dấu hiệu để reviewer và công cụ cùng hỗ trợ

### 13.1. Checklist code review

| Câu hỏi | Tín hiệu nên xem lại |
| --- | --- |
| Trường có được khởi tạo lại ở đầu mọi request? | Có thể chỉ là biến cục bộ bị đẩy lên cấp lớp |
| Có cần đặt trường về null sau mỗi lần dùng? | Vòng đời giá trị có thể ngắn hơn vòng đời đối tượng |
| Helper có tham số trống nhưng đọc nhiều field mutable? | Có phụ thuộc ngầm và temporal coupling |
| Một service có tên trường currentX/lastX nhưng không có hợp đồng lưu lịch sử? | Có thể giữ dữ liệu của request trước |
| Có trường lưu kết quả tính được hoàn toàn từ trường khác? | Cần xem bất biến và cơ chế cập nhật |
| Instance có được dùng chung nhiều request/thread? | Trạng thái request-scoped trong field có nguy cơ race |
| Có constructor hoặc method phải gọi theo thứ tự bí mật? | API có thể biểu diễn thiếu trạng thái |
| Có nhiều reset, cleanup hoặc cờ “initialized” thủ công? | Khả năng lưu trạng thái quá lâu |

### 13.2. Phân tích tĩnh có thể giúp tới đâu?

Một công cụ có thể phát hiện **trường được ghi trong một phương thức rồi chỉ đọc ở một số nơi**, biến không được dùng, lớp có quá nhiều trường mutable hoặc một số mẫu truy cập thiếu đồng bộ. Nhưng không phải công cụ nào cũng suy luận chính xác **vòng đời nghiệp vụ**.

Ví dụ, một trường lưu **reservationStatus** có thể được sửa rất ít lần nhưng vẫn là trạng thái thực sự; một trường **currentInvoice** được gán trong mọi request lại có thể là temporary field dù được dùng ở nhiều helper.

Vì vậy, cảnh báo về code smell là **đầu vào cho review**, không phải mệnh lệnh refactor tự động. Muốn đánh giá đúng phải kết hợp **phân tích sử dụng**, **hợp đồng API**, **cách triển khai object scope** và **kiểm thử**.

## 14. Những hiểu nhầm thường gặp

**“Mọi biến tạm đều xấu.”** Biến cục bộ đặt tên cho một bước nghiệp vụ thường giúp người đọc hiểu mã hơn. Vấn đề là **phạm vi sống không cần thiết**, đặc biệt khi dữ liệu request bị lưu thành trường.

**“Cứ reset trường mỗi lần là an toàn.”** Reset không ngăn các lượt gọi đan xen, không bảo vệ trạng thái sau ngoại lệ và không làm rõ các phụ thuộc ngầm giữa helper.

**“Đặt synchronized sẽ xử lý xong thiết kế.”** Khóa có thể bảo vệ một số đường truy cập, nhưng vẫn làm chia sẻ trạng thái không cần thiết trở thành một vấn đề cần quản lý.

**“Đánh dấu final thì đối tượng bất biến.”** Một trường final có thể tham chiếu đến **List**, **Map** hoặc đối tượng mutable. Final không tự sao chép hoặc khóa trạng thái của đối tượng tham chiếu.

**“Dùng ThreadLocal là cách chuẩn cho mọi dữ liệu request.”** ThreadLocal gắn với thread, không tự gắn với toàn bộ request bất đồng bộ; cần cleanup và propagation đúng. Truyền dữ liệu rõ qua tham số thường đơn giản hơn.

**“Một class không có mutable field chắc chắn thread-safe.”** Còn phải xét static state, dependency được chia sẻ, các đối tượng input/output và tác dụng phụ bên ngoài.

**“Cache là temporary field nên phải xóa.”** Cache có hợp đồng, giới hạn và invalidation rõ ràng có thể là tối ưu hợp lệ; cần đánh giá theo rủi ro và chi phí thực.

**“Tách nhiều helper không tham số làm code sạch hơn.”** Nếu helper phụ thuộc những trường vừa được gán ở bước trước, phương thức ngắn vẫn có thể che giấu temporal coupling.

**“Chỉ cần test happy path sau refactor.”** Cần các ca biên, ngoại lệ và tình huống gọi lặp hoặc đồng thời để phát hiện sự phụ thuộc không mong muốn vào trạng thái cũ.

## 15. Tình huống luyện tập

Một ứng dụng tạo email thông báo đơn hàng dùng service sau:

~~~java
public final class OrderEmailComposer {
    private StringBuilder body;
    private String customerName;
    private long totalVnd;

    public String compose(Order order) {
        body = new StringBuilder();
        customerName = order.customerName();
        totalVnd = order.totalVnd();

        appendGreeting();
        appendTotal();
        return body.toString();
    }

    private void appendGreeting() {
        body.append("Xin chào, ").append(customerName).append('\n');
    }

    private void appendTotal() {
        body.append("Tổng tiền: ").append(totalVnd).append(" VND");
    }
}
~~~

Giả sử **Order** có các phương thức đọc dữ liệu ổn định và **OrderEmailComposer** có thể được nhiều yêu cầu sử dụng chung.

### Câu hỏi

1. Ba trường nào chỉ có ý nghĩa trong một lần **compose**?
2. Nếu hai request gọi **compose** trên cùng một instance, những giá trị nào có thể bị trộn?
3. Nếu **order.customerName()** ném ngoại lệ sau khi **body** đã được đặt lại, trạng thái của composer còn nhất quán không?
4. Tại sao thêm **synchronized** hoặc reset field trong **finally** chưa phải giải pháp đơn giản nhất?
5. Hãy viết lại bằng các biến cục bộ và các helper nhận tham số.
6. Nêu ít nhất ba ca kiểm thử cho văn bản trả về, gọi nhiều lần và đầu vào không hợp lệ theo hợp đồng.
7. Nếu sau này cần thêm cache template email, cache nào là trạng thái hợp lệ và cần quy tắc nào?

### Một cách refactor tham khảo

~~~java
public final class OrderEmailComposer {
    public String compose(Order order) {
        String name = order.customerName();
        long totalVnd = order.totalVnd();
        StringBuilder body = new StringBuilder();

        appendGreeting(body, name);
        appendTotal(body, totalVnd);
        return body.toString();
    }

    private static void appendGreeting(
            StringBuilder body, String customerName) {
        body.append("Xin chào, ")
                .append(customerName)
                .append('\n');
    }

    private static void appendTotal(
            StringBuilder body, long totalVnd) {
        body.append("Tổng tiền: ")
                .append(totalVnd)
                .append(" VND");
    }
}
~~~

**Gợi ý đối chiếu:** **body**, **customerName** và **totalVnd** đều là dữ liệu của một lần tạo email, không cần sống lâu trong composer. Bản refactor giữ **StringBuilder** mutable nhưng chỉ trong lời gọi hiện tại. Nếu service được dùng nhiều thread, các biến cục bộ tách biệt theo từng lời gọi nên không bị trộn bởi chính composer. Tuy nhiên, ví dụ **không tự kiểm tra null** của order/name hoặc các yêu cầu bảo mật khi gửi nội dung qua HTML; đó là những hợp đồng phải được xác định riêng. Nếu template được cache, cần phân biệt nội dung mẫu bất biến dùng chung với dữ liệu khách hàng của từng request và có quy tắc cập nhật cache rõ.

## 16. Ghi nhớ

- **Temporary field** là trường chỉ có ý nghĩa trong một giai đoạn ngắn nhưng lại tồn tại theo vòng đời đối tượng; nó có thể tạo **trạng thái cũ, temporal coupling, cập nhật một phần và lỗi đồng thời**.
- **Biến cục bộ** không tự là mùi mã. Hãy dùng phạm vi nhỏ, tên rõ và truyền kết quả qua tham số hoặc giá trị trả về khi phù hợp.
- Các cách sửa như **reset, synchronized, volatile, ThreadLocal** có thể giải quyết một vấn đề cụ thể nhưng không tự loại bỏ sự chia sẻ trạng thái không cần thiết.
- **Trạng thái nghiệp vụ có vòng đời rõ, dependency, builder hoặc cache có kiểm soát** là những trường hợp field có thể hợp lý.
- Refactor tốt giữ đúng hợp đồng, kiểm thử biên/lỗi và làm cho **ai sở hữu giá trị, giá trị sống bao lâu, khi nào có thể thay đổi** trở nên dễ hiểu.
