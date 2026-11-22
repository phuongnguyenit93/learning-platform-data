# Thực hành quy trình lọc, chuẩn hóa và tính tổng đơn hàng bằng Java Stream

## 1. Mục tiêu và bối cảnh bài thực hành

Một hệ thống bán hàng nhận danh sách đơn hàng thô, trong đó có những đơn đã thanh toán, đang chờ thanh toán hoặc đã hủy. Mã đơn hàng, mã khách hàng và SKU có thể chứa khoảng trắng hay chữ thường/chữ hoa không thống nhất. Mỗi đơn có nhiều dòng hàng, mỗi dòng gồm số lượng và đơn giá. Nhiệm vụ là **tạo một pipeline xử lý rõ ràng, kiểm chứng được**:

1. **Lọc** chỉ các đơn ở trạng thái đã thanh toán (**PAID**).
2. **Chuẩn hóa** mã đơn, mã khách hàng và mã SKU theo một quy tắc nhất quán.
3. **Kiểm tra** dữ liệu cần dùng: mã không rỗng, dòng hàng không null, số lượng dương, đơn giá không âm.
4. **Tính thành tiền từng dòng** = số lượng × đơn giá; **tổng từng đơn** = tổng thành tiền các dòng.
5. **Gom tổng doanh thu theo khách hàng**, đồng thời tính **tổng doanh thu của tất cả đơn đã chọn**.
6. **Kiểm thử** đường đi bình thường, tập rỗng, đơn không hợp lệ, phép tính tràn số, thứ tự, trạng thái và tình huống có dữ liệu thiếu.

Đây là một bài thực hành thuộc Java core — **functional programming**, nên trọng tâm không chỉ là viết được một chuỗi **stream().filter().map().collect()**. Quan trọng hơn là phân định rõ **hợp đồng đầu vào**, **biến đổi dữ liệu**, **bất biến của kết quả** và **chính sách xử lý lỗi**.

Phạm vi tính tiền của ví dụ:

- Mọi giá trị tiền được lưu dưới dạng **long amountCents**, tức **đơn vị tiền nhỏ nhất** của một đồng tiền giả định. Không có chuyển đổi tỷ giá.
- Không áp dụng thuế, chiết khấu, phí vận chuyển, hoàn tiền hoặc làm tròn tỉ lệ. Nếu nghiệp vụ có những yếu tố đó, phải bổ sung quy tắc tính trước khi đưa vào doanh thu.
- **PAID** được coi là trạng thái doanh thu đủ điều kiện theo giả định của bài. Hệ thống kế toán thực tế có thể cần phân biệt đã thanh toán, đã ghi nhận doanh thu, đã hoàn tiền và các điều chỉnh kế toán.
- **Không được âm thầm nuốt lỗi** của đơn PAID. Ở phương án chính, dữ liệu sai khiến phép xử lý thất bại; phần sau trình bày cách thu thập lỗi theo từng đơn nếu nghiệp vụ cần tiếp tục.

### 1.1. Dữ liệu mẫu

| Mã đơn thô | Khách hàng thô | Trạng thái | Dòng hàng | Tổng hợp lệ |
| --- | --- | --- | --- | ---: |
| " so-01 " | " kh01 " | PAID | 2 × 12.500; 1 × 15.000 | 40.000 |
| "SO-02" | "kh02" | PENDING | Dòng hàng thử không hợp lệ | Không tính |
| " so-03 " | "kh01" | PAID | 1 × 12.500; 3 × 7.000 | 33.500 |
| "SO-04" | "kh03" | CANCELLED | Không có dòng hàng | Không tính |

Kết quả cần đạt:

~~~text
Paid receipts: 2
SO-01 | KH01 | 40000
SO-03 | KH01 | 33500
Customer totals: {KH01=73500}
Grand total: 73500
~~~

Số tiền trong stdout là **amountCents**, chưa định dạng thành tiền tệ hiển thị. Tổng toàn bộ = **40.000 + 33.500 = 73.500**.

## 2. Thiết kế mô hình dữ liệu trước khi viết Stream

Ta dùng **record** của Java 17 để biểu diễn dữ liệu thô và dữ liệu đã xử lý:

~~~java
enum Status {
    PAID, PENDING, CANCELLED, REFUNDED
}

record RawLine(String sku, int quantity, long unitPriceCents) {}

record RawOrder(
        String id,
        String customerId,
        Status status,
        List<RawLine> lines
) {}

record BillLine(
        String sku,
        int quantity,
        long amountCents
) {}

record Receipt(
        String orderId,
        String customerId,
        List<BillLine> lines,
        long amountCents
) {}
~~~

Đây là **nhóm khai báo mô hình minh họa**, cần import **java.util.List**. Chương trình hoàn chỉnh ở mục 5 có tất cả khai báo và import cần thiết.

Phân biệt:

- **RawLine** giữ SKU thô, số lượng, đơn giá.
- **RawOrder** giữ dữ liệu nguồn. Không giả định các chuỗi đã được chuẩn hóa.
- **BillLine** giữ SKU chuẩn hóa và thành tiền đã tính cho dòng. Có thể còn cần quantity để hỗ trợ giải thích và đối soát.
- **Receipt** biểu diễn một đơn đã được chuẩn hóa và định giá, kèm danh sách dòng và tổng.

**Tại sao tách RawOrder khỏi Receipt?** Một pipeline dễ kiểm tra hơn khi không sửa trực tiếp object nguồn. Nếu dùng **map** tạo ra record mới, các bước sau có thể tin vào hợp đồng dữ liệu đã chuẩn hóa thay vì phải xử lý lặp lại nhiều dạng mã thô.

Record giúp giảm boilerplate và cung cấp accessor, equals/hashCode, toString; tuy nhiên **record không tự xác thực đầu vào**. Nếu record chứa List mutable, bản thân khai báo record cũng không tự tạo deep immutability. Trong chương trình chính, ta chủ động tạo kết quả theo cách không cho sửa cấu trúc List.

### 2.1. Đặt tên theo đơn vị tiền

Tên **unitPriceCents** và **amountCents** cố tình bao gồm đơn vị. Một lỗi thường gặp là cộng lẫn:

~~~java
long amountCents = quantity * unitPriceCents;
double amountMajor = amountCents / 100.0;
~~~

Đây là đoạn minh họa, chưa có khai báo các biến đầu vào. Quy đổi sang đơn vị lớn để hiển thị chỉ nên xảy ra ở boundary giao diện nếu hợp đồng tiền tệ cho phép. **Không dùng double cho các phép tính tài chính cần chính xác thập phân** khi chưa xem xét yêu cầu rounding và precision.

**Lưu ý đặc biệt:** biểu thức **quantity * unitPriceCents** thông thường **không báo lỗi tràn số**. Bài này dùng **Math.multiplyExact** và **Math.addExact** để không tạo doanh thu sai âm thầm.

## 3. Phân chia trách nhiệm của pipeline

Thiết kế một chuỗi bước có trách nhiệm rõ:

~~~text
List<RawOrder>
       |
       |  kiểm tra collection nguồn khác null
       v
Stream<RawOrder>
       |
       |  kiểm tra từng RawOrder khác null
       v
filter(status == PAID)
       |
       |  bỏ PENDING / CANCELLED / REFUNDED
       v
map(toReceipt)
       |
       |  chuẩn hóa mã
       |  xác thực dòng hàng
       |  tính amountCents của từng dòng
       |  cộng tổng đơn bằng Math.addExact
       v
List<Receipt>
       |
       +-- collect(toMap(..., Math::addExact, TreeMap::new))
       |                  -> doanh thu theo khách hàng
       |
       +-- mapToLong(...).reduce(0L, Math::addExact)
                          -> tổng doanh thu
~~~

**Thứ tự bước không tùy ý.** Trong hợp đồng của bài:

- **Chỉ đơn PAID được xử lý thành Receipt**. Dữ liệu dòng hàng của đơn PENDING bị bỏ qua trong lượt tính doanh thu. Nếu đổi **map(toReceipt)** lên trước **filter**, một đơn PENDING chứa dòng không hợp lệ có thể làm thất bại toàn bộ lượt báo cáo dù không cần dùng dòng đó.
- **RawOrder null bị coi là lỗi cấu trúc nguồn**, không được âm thầm loại bỏ.
- **Status null bị coi là lỗi đầu vào**, không tự xem như “khác PAID”.
- Các lỗi của **đơn PAID** phải được phát hiện; không có quy tắc mặc định biến lỗi thành doanh thu bằng 0.

Đây là **chính sách cụ thể của bài thực hành**. Một chương trình khác có thể yêu cầu **xác thực tất cả đơn trước khi lọc** vì dữ liệu lỗi ở đơn chưa thanh toán cũng phải được báo cáo. Khi ấy, hãy đổi thứ tự có chủ đích và viết test cho quy tắc mới.

## 4. Chuẩn hóa dữ liệu: thuần, rõ, kiểm tra được

Một hàm chuẩn hóa mã phổ biến:

~~~java
static String normalizeCode(String raw, String fieldName) {
    if (raw == null) {
        throw new IllegalArgumentException(fieldName + " is null");
    }
    String result = raw.strip().toUpperCase(Locale.ROOT);
    if (result.isEmpty()) {
        throw new IllegalArgumentException(fieldName + " is blank");
    }
    return result;
}
~~~

Đây là **phương thức minh họa**, cần import **java.util.Locale** và đặt trong một class.

Các bước:

1. **Kiểm tra null trước khi gọi strip()**. Nếu không, **NullPointerException** xảy ra trước khi ta có thông báo lỗi hữu ích.
2. **strip()** loại khoảng trắng Unicode ở hai đầu theo quy tắc của Character.isWhitespace, khác đôi chút với trim() cũ.
3. **toUpperCase(Locale.ROOT)** tạo mã không phụ thuộc locale mặc định của máy đang chạy.
4. **isEmpty()** kiểm tra mã rỗng sau khi chuẩn hóa, không để chuỗi toàn khoảng trắng lọt vào.
5. Hàm trả String mới và không sửa dữ liệu nguồn. Cùng input cho cùng output theo quy tắc áp dụng.

Ví dụ:

~~~text
" so-01 "    -> "SO-01"
" kh01 "     -> "KH01"
" cf-01 "    -> "CF-01"
" bánh "     -> "BÁNH"
"   "        -> IllegalArgumentException
null         -> IllegalArgumentException
~~~

**Không phải mọi mã nên uppercase.** Đây là giả định ID/SKU **không phân biệt chữ hoa chữ thường**. Nếu kho dữ liệu dùng mã phân biệt case, uppercase có thể làm hai mã khác nhau trở thành một mã; khi đó không được áp dụng quy tắc này. Với SKU có khoảng trắng có ý nghĩa ở giữa, **strip** chỉ bỏ hai đầu chứ không xóa phần giữa.

### 4.1. Chuẩn hóa khác xác thực

- **Chuẩn hóa**: chuyển biểu diễn tương đương về dạng chuẩn, như strip và uppercase.
- **Xác thực**: xác định dữ liệu có đáp ứng ràng buộc hay không, như mã không rỗng, quantity lớn hơn 0.
- **Tính toán**: áp dụng quy tắc số học và giới hạn miền.
- **Tổng hợp**: cộng các kết quả đã hợp lệ.

Không nên viết một lambda dài vừa thay đổi chuỗi, vừa gọi database, vừa kiểm tra permission, vừa cộng số tiền trong biến ngoài. Hãy tách thành các hàm nhỏ với tên diễn đạt ý nghĩa để có thể test độc lập.

### 4.2. Không coi mã chuẩn hóa là định danh đã xác minh

"KH01" sau uppercase vẫn chỉ là **chuỗi chuẩn hóa**. Việc mã khách hàng đó có tồn tại, thuộc về người đặt đơn, hoặc có quyền mua hàng phải do tầng nghiệp vụ/nguồn dữ liệu có trách nhiệm xác nhận. **Chuẩn hóa không thay thế kiểm tra định danh**.

## 5. Chương trình Java 17 hoàn chỉnh: lọc, chuẩn hóa, tính tổng

Tạo tệp **OrderPipelineDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;

enum Status {
    PAID, PENDING, CANCELLED, REFUNDED
}

record RawLine(String sku, int quantity, long unitPriceCents) {}

record RawOrder(
        String id,
        String customerId,
        Status status,
        List<RawLine> lines
) {}

record BillLine(
        String sku,
        int quantity,
        long amountCents
) {}

record Receipt(
        String orderId,
        String customerId,
        List<BillLine> lines,
        long amountCents
) {}

public class OrderPipelineDemo {
    static String normalizeCode(String raw, String fieldName) {
        if (raw == null) {
            throw new IllegalArgumentException(fieldName + " is null");
        }

        String normalized = raw.strip().toUpperCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                    fieldName + " is blank");
        }
        return normalized;
    }

    static Receipt toReceipt(RawOrder order) {
        String orderId = normalizeCode(order.id(), "order id");
        String customerId =
                normalizeCode(order.customerId(), "customer id");

        List<RawLine> rawLines =
                Objects.requireNonNull(order.lines(), "lines");

        List<BillLine> billLines = rawLines.stream()
                .map(line -> {
                    Objects.requireNonNull(line, "line");
                    String sku = normalizeCode(line.sku(), "sku");

                    if (line.quantity() <= 0) {
                        throw new IllegalArgumentException(
                                "quantity must be positive");
                    }
                    if (line.unitPriceCents() < 0L) {
                        throw new IllegalArgumentException(
                                "unit price must be nonnegative");
                    }

                    long amount = Math.multiplyExact(
                            (long) line.quantity(),
                            line.unitPriceCents());

                    return new BillLine(
                            sku, line.quantity(), amount);
                })
                .toList();

        long orderTotal = billLines.stream()
                .mapToLong(BillLine::amountCents)
                .reduce(0L, Math::addExact);

        return new Receipt(
                orderId,
                customerId,
                List.copyOf(billLines),
                orderTotal);
    }

    static List<Receipt> process(List<RawOrder> source) {
        Objects.requireNonNull(source, "source");

        return source.stream()
                .map(order -> Objects.requireNonNull(
                        order, "order"))
                .filter(order -> {
                    if (order.status() == null) {
                        throw new IllegalArgumentException(
                                "status is null");
                    }
                    return order.status() == Status.PAID;
                })
                .map(OrderPipelineDemo::toReceipt)
                .toList();
    }

    static Map<String, Long> totalsByCustomer(
            List<Receipt> receipts) {
        return receipts.stream()
                .collect(Collectors.toMap(
                        Receipt::customerId,
                        Receipt::amountCents,
                        Math::addExact,
                        TreeMap::new));
    }

    static long grandTotal(List<Receipt> receipts) {
        return receipts.stream()
                .mapToLong(Receipt::amountCents)
                .reduce(0L, Math::addExact);
    }

    public static void main(String[] args) {
        List<RawOrder> orders = List.of(
                new RawOrder(
                        " so-01 ", " kh01 ", Status.PAID,
                        List.of(
                                new RawLine(" cf-01 ", 2, 12_500),
                                new RawLine(" te-02 ", 1, 15_000)
                        )),
                new RawOrder(
                        "SO-02", "kh02", Status.PENDING,
                        List.of(new RawLine("not-used", 0, -50))),
                new RawOrder(
                        " so-03 ", "kh01", Status.PAID,
                        List.of(
                                new RawLine("cf-01", 1, 12_500),
                                new RawLine(" bánh ", 3, 7_000)
                        )),
                new RawOrder(
                        "SO-04", "kh03", Status.CANCELLED,
                        List.of())
        );

        List<Receipt> receipts = process(orders);

        System.out.println("Paid receipts: " + receipts.size());
        receipts.forEach(receipt ->
                System.out.println(
                        receipt.orderId() + " | "
                        + receipt.customerId() + " | "
                        + receipt.amountCents()));

        System.out.println(
                "Customer totals: " + totalsByCustomer(receipts));
        System.out.println(
                "Grand total: " + grandTotal(receipts));
    }
}
~~~

Biên dịch/chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 OrderPipelineDemo.java
java OrderPipelineDemo
~~~

Stdout:

~~~text
Paid receipts: 2
SO-01 | KH01 | 40000
SO-03 | KH01 | 33500
Customer totals: {KH01=73500}
Grand total: 73500
~~~

### 5.1. Theo dấu từng bước

**Bước 1 — nguồn:** có bốn RawOrder. Trong đó hai đơn PAID, một PENDING và một CANCELLED.

**Bước 2 — kiểm tra cấu trúc:** **map(Objects.requireNonNull)** phát hiện phần tử RawOrder null nếu xuất hiện. Vì dữ liệu mẫu dùng **List.of** và không chứa null, bước này đi qua bình thường.

**Bước 3 — lọc trạng thái:** chỉ các đơn PAID tới **toReceipt**. Đơn PENDING có dòng hàng quantity=0 và unitPriceCents=-50 nhưng không được xử lý trong phép tính doanh thu này. Quy tắc được xác định rõ ở mục 3; không phải khuyến nghị bỏ qua kiểm tra chất lượng dữ liệu ở toàn bộ hệ thống.

**Bước 4 — chuẩn hóa:** " so-01 " thành **SO-01**, " kh01 " thành **KH01**, " cf-01 " thành **CF-01**, " bánh " thành **BÁNH**. Các mã xuất hiện trong Receipt đã được đưa về dạng chuẩn.

**Bước 5 — tính dòng:** đơn SO-01 có 2 × 12.500 = **25.000**, cộng 1 × 15.000 = **15.000**; tổng đơn là **40.000**.

**Bước 6 — tính đơn thứ hai:** SO-03 có 1 × 12.500 = **12.500** và 3 × 7.000 = **21.000**; tổng là **33.500**.

**Bước 7 — gộp theo khách:** hai Receipt đều có customerId "KH01", nên **Collectors.toMap** dùng merge function **Math::addExact** để cộng 40.000 + 33.500 = **73.500**.

**Bước 8 — tổng toàn bộ:** **mapToLong(Receipt::amountCents).reduce(0L, Math::addExact)** tạo tổng 73.500.

**Bước 9 — xác định thứ tự hiển thị:** **TreeMap::new** cố định thứ tự khóa khách hàng khi in Map. Với bài mẫu chỉ có một khách thì không thấy khác biệt, nhưng việc chọn TreeMap giúp báo cáo ổn định khi có nhiều khách.

### 5.2. Vì sao List.copyOf không làm dữ liệu đầu ra thành deep immutable?

**List.copyOf(billLines)** tạo một danh sách không cho sửa cấu trúc. Các **BillLine** trong ví dụ là record chứa String, int, long, nên cách mô hình hóa này khá an toàn cho bài thực hành.

Tuy nhiên, quy tắc tổng quát vẫn là: **List.copyOf không deep-copy những object mutable**. Nếu BillLine có field tham chiếu một List hoặc object mutable, bạn phải kiểm tra ownership và khả năng thay đổi sâu hơn.

**Stream.toList()** ở Java 17 cũng tạo danh sách không sửa được. Việc copyOf ở ví dụ nhằm làm rõ hợp đồng trả về của Receipt; trong production có thể tối ưu để tránh bước copy không cần thiết sau khi kiểm chứng yêu cầu ownership.

## 6. Phân biệt filter trước và sau normalize

Đây là một quyết định nghiệp vụ quan trọng:

~~~java
source.stream()
        .filter(order -> order.status() == Status.PAID)
        .map(OrderPipelineDemo::toReceipt);
~~~

Đây là đoạn minh họa; giả định source chứa RawOrder không null và OrderPipelineDemo là lớp đã khai báo. Trong bài toán này, chỉ các đơn PAID mới được định giá.

Nếu đảo thứ tự:

~~~java
source.stream()
        .map(OrderPipelineDemo::toReceipt)
        .filter(receipt -> ...);
~~~

Đây là **đoạn cố ý không đầy đủ và không nên copy nguyên**, vì Receipt ở mô hình ví dụ **không còn status** để lọc sau này. Quan trọng hơn, việc toReceipt chạy trước có thể ném exception với dữ liệu đơn PENDING/CANCELLED, làm thay đổi hành vi báo cáo.

**Vì sao không đưa status vào Receipt?** Receipt đã là mô hình **đơn PAID được chọn và định giá**, nên không cần mang theo status nếu không có tình huống nghiệp vụ khác đòi hỏi. Tách mô hình RawOrder/Receipt giúp tránh “lọc sau nhưng mất thông tin lọc”.

Mặt khác, nếu yêu cầu là **kiểm tra mọi đơn đầu vào** trước khi lập báo cáo, phải xây riêng bước validation cho RawOrder toàn bộ danh sách. Không nên vô tình thay đổi chính sách chỉ bằng cách đổi thứ tự Stream stages.

### 6.1. Không dùng peek để chuẩn hóa hoặc cập nhật

Phản mẫu:

~~~java
orders.stream()
        .peek(order -> order.setStatus(Status.PAID))
        .filter(order -> order.getStatus() == Status.PAID)
        .toList();
~~~

Đây là **phản mẫu minh họa** giả định có lớp Order mutable với setter/getter; không áp dụng cho record RawOrder ở ví dụ chính. **peek** chủ yếu dùng để quan sát/debug, không phải nơi sửa trạng thái nghiệp vụ bắt buộc. Với tối ưu Stream, side effect trong intermediate operation không phải thứ để dựa vào để bảo đảm kết quả.

Thay vào đó, dùng **filter** để chọn, **map** để tạo dữ liệu chuẩn hóa mới, và **collect/toList** để nhận kết quả. Nếu cần thay đổi trạng thái trong database, dùng quy trình tường minh với transaction, xử lý lỗi và idempotency phù hợp.

## 7. Phân biệt map, flatMap, mapToLong và collect

Một đơn có nhiều dòng hàng, vì vậy pipeline có **hai tầng dữ liệu**:

~~~text
Stream<RawOrder>
    -> map(toReceipt)
    -> Stream<Receipt>
    -> toList()
    -> List<Receipt>

RawOrder.lines(): List<RawLine>
    -> stream().map(toBillLine)
    -> Stream<BillLine>
    -> toList()
    -> List<BillLine>
~~~

Ở đây **map** phù hợp vì mỗi RawOrder PAID tạo đúng một Receipt; mỗi RawLine hợp lệ tạo đúng một BillLine.

Nếu cần thống kê **toàn bộ dòng hàng** của nhiều Receipt, ta có quan hệ một-nhiều và có thể dùng **flatMap**:

~~~java
long lineCount = receipts.stream()
        .flatMap(receipt -> receipt.lines().stream())
        .count();
~~~

Đây là đoạn minh họa, giả định receipts là List<Receipt>. **flatMap** làm phẳng các danh sách dòng thành một Stream<BillLine>. Với dữ liệu mẫu, có 2 dòng ở SO-01 và 2 dòng ở SO-03, nên **lineCount = 4**.

Nếu cần tính tổng tiền, có thể làm phẳng trực tiếp từng dòng:

~~~java
long byLines = receipts.stream()
        .flatMap(r -> r.lines().stream())
        .mapToLong(BillLine::amountCents)
        .reduce(0L, Math::addExact);
~~~

Kết quả **73.500** bằng tổng các Receipt nếu bất biến **Receipt.amountCents == sum(Receipt.lines.amountCents)** được đảm bảo.

**Tại sao dùng mapToLong thay vì map?** **mapToLong(BillLine::amountCents)** tạo **LongStream**, tránh boxing thành Long ở bước xử lý primitive tương ứng. **reduce(0L, Math::addExact)** dùng phép cộng có kiểm tra overflow, khác **LongStream.sum()** vốn không tự ném lỗi khi tràn miền long.

### 7.1. Identity 0L trong reduce

Với phép cộng long:

~~~java
long total = amounts.reduce(0L, Math::addExact);
~~~

Đây là đoạn minh họa, giả định amounts là một LongStream chưa tiêu thụ. **0L** là identity của phép cộng: cộng 0 không đổi giá trị. Khi stream rỗng, reduce trả **0L**, đúng quy tắc tổng của tập rỗng theo bài thực hành.

**Lưu ý:** Math.addExact(long,long) ném **ArithmeticException** nếu phép cộng tràn miền long. Một số giá trị lớn có tổng toán học nằm trong phạm vi long nhưng có thể tràn ở cách nhóm trung gian nhất định; nếu bài toán cần tổng luôn đúng với mọi cách phối hợp cả khi trung gian vượt giới hạn, hãy dùng kiểu số đủ rộng như BigInteger hoặc BigDecimal.

## 8. Tính tiền an toàn: không dùng phép nhân/cộng có nguy cơ tràn âm thầm

### 8.1. Vì sao Math.multiplyExact?

Phản mẫu:

~~~java
long lineTotal = quantity * unitPriceCents;
~~~

Đây là đoạn minh họa. Nếu quantity × unitPriceCents vượt phạm vi long, phép nhân thường **không ném ArithmeticException**, mà wrap theo quy tắc số nguyên Java. Tổng tiền có thể thành số âm hoặc một số dương sai.

Bản có kiểm tra:

~~~java
long lineTotal = Math.multiplyExact(
        (long) quantity, unitPriceCents);
~~~

Nếu phép nhân vượt long, **Math.multiplyExact** ném ArithmeticException. Cast **(long) quantity** đặt cả phép nhân vào overload **long,long**, để tránh tình huống nhân hai int trước rồi mới gán sang long khi cả hai toán hạng đầu là int.

### 8.2. Vì sao Math.addExact?

Phản mẫu:

~~~java
long grandTotal = receipts.stream()
        .mapToLong(Receipt::amountCents)
        .sum();
~~~

Đây là đoạn minh họa. **LongStream.sum()** cộng long nhưng không phải một API kiểm soát overflow. Để phát hiện tràn:

~~~java
long grandTotal = receipts.stream()
        .mapToLong(Receipt::amountCents)
        .reduce(0L, Math::addExact);
~~~

Đoạn này dùng chính phép cộng có kiểm tra. Nếu lỗi số học xảy ra, pipeline thất bại thay vì xuất báo cáo doanh thu sai.

### 8.3. Khi nào long vẫn chưa đủ?

Nếu đơn giá, số lượng hoặc tổng hợp vượt miền **long**, phải chọn một mô hình khác. Với tiền có phần thập phân và chính sách rounding, **BigDecimal** thường phù hợp; với đơn vị nguyên rất lớn có thể cân nhắc **BigInteger**. Không chuyển sang **double** chỉ vì muốn tránh overflow, vì double có sai số biểu diễn và không giữ chính xác mọi số nguyên lớn.

## 9. Chương trình Java 17: kiểm tra dữ liệu lỗi và overflow

Tạo tệp **OrderValidationDemo.java**:

~~~java
import java.util.List;
import java.util.Objects;

record Line(int quantity, long unitPriceCents) {}

public class OrderValidationDemo {
    static long total(List<Line> lines) {
        Objects.requireNonNull(lines, "lines");

        return lines.stream()
                .mapToLong(line -> {
                    Objects.requireNonNull(line, "line");

                    if (line.quantity() <= 0) {
                        throw new IllegalArgumentException(
                                "quantity must be positive");
                    }
                    if (line.unitPriceCents() < 0L) {
                        throw new IllegalArgumentException(
                                "unit price must be nonnegative");
                    }
                    return Math.multiplyExact(
                            (long) line.quantity(),
                            line.unitPriceCents());
                })
                .reduce(0L, Math::addExact);
    }

    public static void main(String[] args) {
        long valid = total(List.of(
                new Line(2, 1_200),
                new Line(1, 700)));

        System.out.println("Valid total: " + valid);
        System.out.println("Empty total: " + total(List.of()));

        try {
            total(List.of(new Line(0, 1_000)));
        } catch (IllegalArgumentException failure) {
            System.out.println("Invalid: " + failure.getMessage());
        }

        try {
            total(List.of(new Line(2, Long.MAX_VALUE)));
        } catch (ArithmeticException failure) {
            System.out.println(
                    "Overflow: " + failure.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac OrderValidationDemo.java
java OrderValidationDemo
~~~

Stdout:

~~~text
Valid total: 3100
Empty total: 0
Invalid: quantity must be positive
Overflow: ArithmeticException
~~~

Phân tích:

1. **2 × 1.200 + 1 × 700 = 3.100**.
2. Danh sách rỗng được gộp bằng identity 0L, nên tổng = 0. Đây là **quy tắc tổng**, không tự khẳng định một đơn hàng không có dòng là nghiệp vụ hợp lệ.
3. Quantity=0 bị chặn trước khi nhân, nên ném IllegalArgumentException với thông điệp chính xác.
4. **2 × Long.MAX_VALUE** vượt miền long; Math.multiplyExact ném ArithmeticException. Chương trình bắt lỗi và in loại lỗi thay vì ghi sai một tổng tiền âm.
5. Phép kiểm tra đơn giá âm diễn ra trước phép nhân. Nếu đơn giá âm là cách biểu diễn giảm giá/hoàn tiền của nghiệp vụ, không nên gộp nó vào cùng mô hình Line thông thường mà chưa có quy tắc riêng.

**Điểm quan trọng:** ví dụ sử dụng **catch** trong main để minh họa các nhánh thất bại. Phương thức total **không tự nuốt lỗi**; caller nhận biết đầu vào không hợp lệ hoặc overflow qua exception.

## 10. Tổng hợp theo khách hàng: vì sao dùng toMap với merge function?

Một khách hàng có thể có nhiều Receipt. Nếu chỉ dùng:

~~~java
Collectors.toMap(
        Receipt::customerId,
        Receipt::amountCents)
~~~

thì với hai Receipt cùng customerId, collector **gặp khóa trùng** và ném IllegalStateException theo hợp đồng mặc định. Đây không phải cách đúng để tính tổng doanh thu theo khách.

Cần chỉ định **merge function**:

~~~java
Collectors.toMap(
        Receipt::customerId,
        Receipt::amountCents,
        Math::addExact,
        TreeMap::new)
~~~

Đây là biểu thức collector minh họa, cần imports Collectors, TreeMap. Khi hai Receipt cùng khóa, **Math.addExact** cộng hai amountCents một cách có kiểm tra overflow.

Các vai trò:

| Thành phần | Chức năng |
| --- | --- |
| **Receipt::customerId** | Xác định khóa nhóm khách hàng |
| **Receipt::amountCents** | Chọn giá trị cần cộng |
| **Math::addExact** | Xử lý khóa trùng bằng cộng có kiểm tra overflow |
| **TreeMap::new** | Chọn Map có thứ tự khóa ổn định |

**Không dùng merge function (old, next) -> next** nếu mục tiêu là tổng doanh thu: cách đó chỉ giữ giá trị cuối khi khóa trùng, làm mất số tiền của các đơn trước.

### 10.1. groupingBy cũng là một lựa chọn

Cách viết khác:

~~~java
Map<String, Long> totals = receipts.stream()
        .collect(Collectors.groupingBy(
                Receipt::customerId,
                TreeMap::new,
                Collectors.summingLong(Receipt::amountCents)));
~~~

Đây là đoạn minh họa, giả định receipts đã có và imports Map, TreeMap, Collectors.

Trong phạm vi dữ liệu nhỏ, cả **toMap + merge** và **groupingBy + summingLong** có thể cho cùng tổng. Tuy nhiên, **Collectors.summingLong** không có hợp đồng tự kiểm tra overflow. Bài thực hành ưu tiên **Math::addExact** để bảo vệ tính đúng đắn số học trong điều kiện phạm vi long.

Nếu cần nhiều thống kê theo khách như count, min, max, average, có thể dùng downstream collector phù hợp hoặc một result type giàu thông tin. Không cần tự tạo map phụ bên ngoài rồi cập nhật trong forEach khi collector đã biểu diễn việc gom dữ liệu rõ ràng.

### 10.2. Trường hợp không có Receipt

Nếu danh sách sau filter là rỗng:

- **totalsByCustomer** trả **Map rỗng**.
- **grandTotal** trả **0L** theo identity của reduce.
- **Paid receipts** bằng **0**.

Đừng tự thêm một khách hàng tên UNKNOWN để chứa tổng bằng 0 nếu không có yêu cầu nghiệp vụ. Mặt khác, một báo cáo kế toán có thể cần hiển thị tất cả khách kể cả không mua, khi đó phải kết hợp thêm danh sách khách từ nguồn nghiệp vụ khác.

## 11. Sắp xếp báo cáo tổng theo doanh thu và xử lý giá trị bằng nhau

Sau khi có Map tổng theo khách, đôi khi cần xếp hạng **doanh thu giảm dần**, và nếu bằng tiền thì sắp theo mã khách để có thứ tự ổn định.

Tạo tệp **OrderRankingDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

record Sale(String customer, long amountCents) {}
record CustomerTotal(String customer, long amountCents) {}

public class OrderRankingDemo {
    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("KH02", 10_000),
                new Sale("KH01", 25_000),
                new Sale("KH02", 30_000),
                new Sale("KH03", 40_000)
        );

        Map<String, Long> totals = sales.stream()
                .collect(Collectors.toMap(
                        Sale::customer,
                        Sale::amountCents,
                        Math::addExact,
                        TreeMap::new));

        List<CustomerTotal> ranking = totals.entrySet().stream()
                .map(entry -> new CustomerTotal(
                        entry.getKey(), entry.getValue()))
                .sorted(Comparator
                        .comparingLong(CustomerTotal::amountCents)
                        .reversed()
                        .thenComparing(CustomerTotal::customer))
                .toList();

        System.out.println("Totals: " + totals);
        System.out.println("Ranking:");
        ranking.forEach(item -> System.out.println(
                item.customer() + ": " + item.amountCents()));
    }
}
~~~

Chạy:

~~~bash
javac OrderRankingDemo.java
java OrderRankingDemo
~~~

Stdout:

~~~text
Totals: {KH01=25000, KH02=40000, KH03=40000}
Ranking:
KH02: 40000
KH03: 40000
KH01: 25000
~~~

**Giải thích:**

- Hai Sale của KH02 có 10.000 + 30.000 = **40.000**.
- KH03 có **40.000**, KH01 có **25.000**.
- Comparator sắp theo doanh thu giảm dần rồi theo customer tăng dần khi tiền bằng nhau. Vì vậy KH02 trước KH03.
- `sorted` **không loại các phần tử trùng**; mỗi CustomerTotal tương ứng một khóa duy nhất đã được gom. Nếu đặt TreeSet với comparator chỉ dựa vào amountCents, KH02 và KH03 có thể bị coi là trùng và một khách biến mất — sai yêu cầu báo cáo.

**Khác nhau giữa hai loại thứ tự:** TreeMap trong tổng hợp cho **thứ tự khóa**; Comparator ở ranking cho **thứ tự doanh thu**. Chọn đúng theo mục đích hiển thị.

## 12. Dữ liệu null: phát hiện, loại hay báo lỗi?

Một pipeline có thể gặp các kiểu null khác nhau:

1. **Nguồn List<RawOrder> null**.
2. **Một phần tử RawOrder null**.
3. **Trạng thái null**.
4. **Mã đơn, mã khách, SKU null**.
5. **Danh sách RawLine của một đơn null**.
6. **Một RawLine bên trong danh sách null**.

Trong chương trình chính:

| Tình huống | Chính sách |
| --- | --- |
| Source List null | Objects.requireNonNull, thất bại |
| RawOrder null | Objects.requireNonNull trong map trước filter, thất bại |
| Status null | IllegalArgumentException trong filter, thất bại |
| Mã null hoặc blank trên đơn PAID | IllegalArgumentException từ normalizeCode |
| lines null trên đơn PAID | NullPointerException với thông điệp "lines" |
| RawLine null trên đơn PAID | NullPointerException với thông điệp "line" |
| Quantity <= 0 trên đơn PAID | IllegalArgumentException |
| Unit price < 0 trên đơn PAID | IllegalArgumentException |
| Phép tính vượt long | ArithmeticException |

Điều quan trọng là **mỗi loại null cần một hợp đồng**. Một filter như **filter(Objects::nonNull)** có thể loại RawOrder null nhưng đồng thời làm báo cáo mất một bản ghi mà không ai biết. Trong bài học này, RawOrder null là lỗi cấu trúc nguồn, vì vậy cần fail fast.

**Một lựa chọn khác:** Nếu dữ liệu đọc từ API legacy chứa giá trị null được xác định là “không có đơn”, có thể lọc null ngay sau nguồn. Nhưng lựa chọn đó phải được ghi rõ, có test và không được áp dụng máy móc cho mọi nguồn.

### 12.1. List.of và Arrays.asList

**List.of** không chấp nhận null element; nếu cần kiểm thử chính sách phát hiện null trong Stream, có thể tạo danh sách bằng **Arrays.asList(...)** hoặc một ArrayList. Không gán một List chứa null vào List.of rồi cho rằng đã kiểm thử pipeline: chương trình sẽ ném NPE ngay lúc tạo List.of.

### 12.2. Stream.toList và dữ liệu đầu ra

**Stream.toList()** của Java 17 trả một List không thể sửa cấu trúc; **List.of()** cũng là collection unmodifiable nhưng không cho phép phần tử null. Đừng gộp tất cả các factory/terminal operation thành một ý nghĩa. Trong chương trình này, Receipt và BillLine được kiểm tra để tránh null, nên đầu ra không có lý do chứa null.

## 13. Lỗi của đơn PAID: dừng tất cả hay giữ kết quả từng đơn?

Có ít nhất hai chính sách nghiệp vụ hợp lý:

**Chính sách A — fail fast (chương trình chính):**

- Gặp đơn PAID có dữ liệu không hợp lệ → ném exception, không công bố một báo cáo doanh thu thành công.
- Ưu điểm: không âm thầm công bố tổng doanh thu thiếu.
- Hạn chế: cần cơ chế xử lý lỗi ở cấp gọi; không có danh sách tất cả đơn lỗi trong một lượt nếu dừng ở lỗi đầu.

**Chính sách B — gom kết quả theo đơn:**

- Xử lý từng đơn thành **Success(receipt)** hoặc **Failure(orderId,reason)**.
- Báo cáo riêng các đơn lỗi; doanh thu từ các đơn thành công chỉ được công bố cùng cờ trạng thái **partial/incomplete** nếu bài toán cho phép.
- Ưu điểm: giúp nhập dữ liệu hàng loạt, chẩn đoán và sửa nhiều bản ghi một lúc.
- Hạn chế: cần loại kết quả giàu thông tin, trách nhiệm không được ghi nhầm tổng partial là tổng đầy đủ.

Không nên viết:

~~~java
try {
    return calculate(order);
} catch (RuntimeException ignored) {
    return 0L;
}
~~~

Đây là **phản mẫu minh họa**, giả định ở trong một method trả long và đã định nghĩa calculate. Nó có thể biến đơn lỗi thành doanh thu 0; người xem báo cáo không biết đơn bị loại vì dữ liệu sai.

Nếu triển khai chính sách B, một mô hình kiểu **sealed interface OrderOutcome permits Success, Failure** hoặc record chứa receipt/error có bất biến rõ ràng thường tốt hơn cách ném rồi nuốt exception. Có thể thêm mã lỗi ổn định, vị trí bản ghi và mức độ nghiêm trọng để hỗ trợ sửa dữ liệu.

### 13.1. Phân biệt lỗi nghiệp vụ và lỗi hệ thống

- **Quantity <= 0** hoặc SKU blank có thể là lỗi validation input.
- **ArithmeticException** cho biết số vượt phạm vi kiểu long của thiết kế.
- **Lỗi database/network** (nếu có) là lỗi vận hành, không phải “đơn hàng không tồn tại”.
- **Hủy/hoàn tiền** là trạng thái nghiệp vụ, không phải lỗi ném exception chỉ vì chúng không thuộc tập đơn PAID được chọn.

Tầng xử lý cần bảo toàn nguyên nhân thực tế, không gộp mọi exception thành một chuỗi “Không có đơn”.

## 14. Kiểm thử đường đi đúng và đường đi lỗi

Một pipeline tốt phải **có thể kiểm thử theo hàm nhỏ** thay vì chỉ chạy main rồi nhìn stdout.

### 14.1. Bảng test cốt lõi

| Case | Đầu vào | Kết quả kỳ vọng |
| --- | --- | --- |
| Chuẩn hóa mã | " so-01 " | "SO-01" |
| Chuẩn hóa rỗng | "   " | IllegalArgumentException |
| Chuẩn hóa null | null | IllegalArgumentException |
| Đơn PAID hợp lệ | 2 × 12.500; 1 × 15.000 | 40.000 |
| Đơn PAID có quantity=0 | Quantity 0 | IllegalArgumentException |
| Đơn PAID có giá âm | Unit price -1 | IllegalArgumentException |
| Tính nhân vượt long | 2 × Long.MAX_VALUE | ArithmeticException |
| Tính tổng vượt long | Long.MAX_VALUE + 1 | ArithmeticException |
| PENDING dòng hỏng | Trạng thái PENDING | Không vào báo cáo theo chính sách A |
| CANCELLED hợp lệ | Trạng thái CANCELLED | Không vào báo cáo |
| Không có đơn PAID | Chỉ PENDING/CANCELLED | List rỗng, Map rỗng, tổng 0 |
| Hai đơn cùng khách | 40.000 + 33.500 | Một khóa KH01, tổng 73.500 |
| Hai khách cùng doanh thu | KH02 40.000, KH03 40.000 | Ranking theo khách tăng dần khi bằng tiền |
| RawOrder null | Một phần tử nguồn null | Fail fast |
| Status null | Một đơn có status null | Báo lỗi |
| Dòng null trên PAID | Một RawLine null | Báo lỗi |

**Đừng chỉ test số tiền cuối.** Một pipeline có thể cho đúng tổng nhưng lọc nhầm một đơn và cộng nhầm một đơn khác. Hãy kiểm tra **mã các Receipt được chọn, số dòng, customer, status nguồn, thứ tự**, rồi mới kiểm tra tổng.

### 14.2. Ví dụ assertions dạng hàm thuần

Có thể kiểm tra phương thức trong OrderPipelineDemo từ một chương trình test riêng:

~~~java
// Đoạn minh họa cho test hoặc main cùng package:
String code = OrderPipelineDemo.normalizeCode(" kh01 ", "customer");
if (!"KH01".equals(code)) {
    throw new AssertionError("normalize failed");
}

long total = OrderPipelineDemo.grandTotal(List.of(
        new Receipt("A", "KH01", List.of(), 100L),
        new Receipt("B", "KH01", List.of(), 50L)
));
if (total != 150L) {
    throw new AssertionError("sum failed");
}
~~~

Đây là **đoạn test minh họa**, không phải tệp độc lập. Nó cần các kiểu được khai báo trong chương trình chính và import List. Lưu ý hai Receipt thử nghiệm được tạo trực tiếp, nên **lines trống nhưng amountCents dương** không phản ánh bất biến đầu ra của toReceipt. Nếu cần kiểm tra toàn bộ quy trình, hãy dựng RawOrder/RawLine và gọi **process** thay vì tạo Receipt không qua validation.

### 14.3. Vì sao không chỉ dùng Java assert?

Câu lệnh **assert** của Java có thể bị vô hiệu khi chạy thông thường nếu JVM không được bật assertions bằng **-ea**. Với test quan trọng, dùng **JUnit 5** hoặc tự ném AssertionError khi điều kiện sai như đoạn minh họa. Không coi một lượt chạy bình thường không in lỗi là chứng cứ test đã được thực thi nếu chỉ dùng assert mà quên -ea.

### 14.4. Property-based/invariant tests hữu ích

Ngoài các case cụ thể, hãy kiểm thử những bất biến sau:

1. **Mọi Receipt xuất hiện trong kết quả** có nguồn là đơn PAID được chọn.
2. **Mỗi Receipt.amountCents** bằng tổng amountCents của các BillLine trong nó.
3. **grandTotal(receipts)** bằng tổng các giá trị Map totalsByCustomer, nếu không có overflow và cùng tập Receipt.
4. **Số Receipt** bằng số RawOrder PAID hợp lệ, trừ khi hệ thống có chính sách trùng ID.
5. **Mã đã chuẩn hóa** không có khoảng trắng ở hai đầu và có case theo quy tắc.
6. **Kết quả của process** không phụ thuộc vào trạng thái mutable ở ngoài, với cùng nguồn hợp lệ và không có thay đổi đồng thời.
7. **Không mất số tiền** khi một khách có nhiều đơn: merge function phải cộng, không ghi đè.
8. **Không bỏ lỗi tính toán**: các phép multiplyExact/addExact phải ném khi vượt miền long.

Bất biến mạnh giúp phát hiện những bug mà một fixture nhỏ không thể thấy hết, đặc biệt khi thêm nhóm khách mới hoặc thay đổi logic trạng thái.

## 15. Tính đúng đắn trước hiệu năng

Với Stream, các hàm **filter/map** nên stateless và non-interfering:

~~~java
List<Receipt> receipts = orders.stream()
        .filter(order -> order.status() == Status.PAID)
        .map(OrderPipelineDemo::toReceipt)
        .toList();
~~~

Đây là đoạn minh họa trên dữ liệu không null; chương trình chính có guard bổ sung. Một vài lời khuyên:

- **Không cập nhật biến tổng bên ngoài trong forEach/peek** để thay cho reduce/collector. Làm vậy tạo shared mutable state dễ gây race nếu chuyển sang parallel.
- **Không dùng AtomicLong.increment/add** trong filter/map rồi coi nó là phép tổng hợp đúng theo hợp đồng Stream. Atomic bảo vệ một thao tác cập nhật, không bảo đảm các side effect xảy ra đúng số lần mong muốn khi tối ưu/ngắn mạch.
- **Không lấy số dòng log peek làm số đơn đã xử lý**. Stream có thể lazy và một số terminal operation được tối ưu.
- **Tạo kết quả bất biến về cấu trúc** khi cần chia sẻ qua nhiều tầng xử lý; tránh sửa RawOrder/RawLine ngay trong pipeline.
- **Không tự bật parallel()** chỉ vì nguồn có nhiều phần tử. Chi phí chia/merge và quy tắc ngoại lệ trong parallel pipeline cần được đánh giá theo workload thật.

### 15.1. Thứ tự và tính ổn định báo cáo

Trên List có encounter order, **filter** và **map** tuần tự giữ thứ tự các đơn còn lại. **Stream.toList()** cũng giữ encounter order nếu Stream có thứ tự. Đó là lý do mã SO-01 xuất hiện trước SO-03 trong stdout.

Nếu chỉ cần **tổng doanh thu**, thứ tự Receipt không ảnh hưởng phép cộng toán học (ngoại trừ các vấn đề overflow intermediate khi dùng long có kiểm tra). Nhưng nếu báo cáo cần **top khách hàng**, hoặc hiển thị đơn theo ngày/ID, phải bổ sung **sorted(comparator)** với thứ tự và tie-breaker rõ ràng.

**Không dựa vào HashMap iteration order** để kiểm thử stdout. Ví dụ sử dụng TreeMap nhằm cố định thứ tự khóa.

### 15.2. Duyệt nhiều lần hay một lần?

Chương trình chính:

- Xây **List<Receipt>** một lần từ nguồn.
- Duyệt Receipt để tính Map doanh thu.
- Duyệt Receipt để tính grandTotal.

Với dữ liệu nhỏ/vừa và cần xuất Receipt chi tiết, thiết kế này rõ ràng và dễ test. Nếu nguồn là một luồng I/O rất lớn hoặc chỉ duyệt được một lần, cần cân nhắc **downstream collector tích hợp** nhiều kết quả hay processing theo batch. Đừng đổi sang một collector rất phức tạp chỉ để tiết kiệm một lượt duyệt List nhỏ.

**Không gọi nhiều terminal operations trên cùng một Stream instance.** Sau **toList, collect, reduce, count**, Stream đã bị tiêu thụ; muốn tính nhiều thứ phải tạo Stream mới từ dữ liệu có thể duyệt lại, hoặc thu vào một kết quả trung gian như List<Receipt>.

## 16. Tình huống mở rộng: thuế, giảm giá và hủy/hoàn tiền

Chương trình mẫu **không tính thuế/giảm giá**. Nếu bài toán thêm một tỷ lệ giảm giá 10%, cần xác định:

1. Giảm giá trước hay sau thuế?
2. Làm tròn ở từng dòng, từng đơn hay cuối báo cáo?
3. Đơn vị tiền tệ và số chữ số thập phân hợp lệ?
4. Giảm giá có được âm không? Giá trị tối đa là bao nhiêu?
5. Hoàn tiền cần trừ vào doanh thu cùng kỳ hay báo cáo riêng?
6. Dữ liệu có thể chứa nhiều đồng tiền không? Nếu có, **không được cộng thẳng** các amountCents khác currency.

Trong hệ thống thật, có thể dùng **BigDecimal** cho phép tính tỷ lệ và quy tắc rounding tường minh. Với giá trị nguyên theo minor units, cần chuyển đổi bằng các phép toán có kiểm tra và làm tròn được công bố, tránh tính bằng double rồi cast sang long tùy tiện.

### 16.1. Không coi PAID là kết luận kế toán phổ quát

Một đơn PAID có thể hoàn tiền một phần hoặc toàn phần; một đơn SHIPPED có thể được ghi nhận doanh thu theo chuẩn/điều kiện khác. Trạng thái lọc ở bài này là **giả định của yêu cầu thực hành**, không phải quy tắc kế toán chung.

Nếu có nhiều trạng thái có cùng ý nghĩa hoặc trạng thái hiệu lực theo thời gian, hãy đặt quy tắc vào một **Predicate/Policy** được đặt tên, test độc lập, thay vì viết các điều kiện rải rác tại nhiều nơi:

~~~java
Predicate<RawOrder> eligible = order ->
        order.status() == Status.PAID;
~~~

Đoạn minh họa cần import Predicate và giả định order khác null; khi thêm chính sách mới, cập nhật và test một nơi.

## 17. Những lỗi phổ biến trong bài thực hành

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Gọi normalize trước khi lọc mà không xác định chính sách | Đơn không tính doanh thu vẫn có thể gây lỗi | Định nghĩa rõ phạm vi validation, rồi đặt stage |
| Không kiểm tra status null | Có thể âm thầm coi là không PAID | Báo lỗi hoặc quy tắc riêng theo hợp đồng |
| Dùng trim/uppercase theo locale mặc định | Có thể thay đổi hành vi giữa môi trường | Quy định Locale.ROOT nếu mã case-insensitive |
| Coi mã sau normalize là đã xác minh identity | Sai về nghiệp vụ | Kiểm tra tồn tại/quyền ở boundary thích hợp |
| Tính qty × price bằng phép nhân thường | Có thể overflow âm thầm | Math.multiplyExact |
| Dùng LongStream.sum cho báo cáo cần báo overflow | sum không tự ném khi tràn | reduce(0L, Math::addExact) hoặc kiểu số khác |
| Dùng toMap không merge khi nhiều đơn cùng khách | Duplicate-key exception | Merge function phù hợp |
| Dùng merge (a,b) -> b | Làm mất doanh thu các đơn trước | Cộng có kiểm tra |
| Dùng double để giữ tiền chính xác | Sai số nhị phân/rounding | Long minor units hoặc BigDecimal |
| Chỉ test grandTotal | Có thể lọc nhầm nhưng tổng trùng hợp | Test IDs, status, lines, group và tổng |
| Trả 0 khi bắt mọi exception | Che dữ liệu hỏng và báo cáo thiếu | Fail fast hoặc kết quả partial có metadata |
| Dùng filter(Objects::nonNull) không chủ đích | Mất bản ghi lỗi | Chọn chính sách null cụ thể |
| Sửa RawOrder trong peek | Side effect không đáng tin | Dùng map tạo record mới |
| Dùng shared List/Map để collect trong parallelStream | Race/order issue | Collector hoặc reduction chuẩn |
| Nhầm đơn hàng rỗng với tổng bằng 0 | Không phân biệt vắng dòng và có dòng 0 tiền | Kiểm tra count/validation theo yêu cầu |
| Dựa vào HashMap order để in report | Thứ tự không cam kết | TreeMap hoặc sorted cho output cần ổn định |
| Dùng TreeSet cho top khách với comparator chỉ theo doanh thu | Hai khách cùng tổng có thể mất một | Dùng List và sorted, thêm tie-breaker |
| Không xem xét trùng orderId | Có thể tính hai lần cùng giao dịch | Thiết kế dedupe/idempotency trước báo cáo |
| Thay đổi nguồn trong lúc pipeline chạy | Vi phạm non-interference, dễ race | Snapshot hoặc bất biến dữ liệu |
| Cộng trực tiếp nhiều currency | Số tổng không có nghĩa | Nhóm theo currency hoặc chuyển đổi có quy tắc |

## 18. Bài tập luyện tập theo cấp độ

### Bài 1: Viết lại pipeline từ yêu cầu

Từ List<RawOrder>, dùng Stream để chọn các đơn PAID, chuẩn hóa mã, tính từng dòng và trả List<Receipt>. Nêu rõ **những lỗi đầu vào nào cần chặn** ở từng stage.

### Bài 2: Thay đổi dữ liệu mà không đổi code

Thêm một đơn PAID của khách **KH02**, có 3 sản phẩm đơn giá 9.000. Dự đoán grandTotal mới: **73.500 + 27.000 = 100.500**, Map có thêm khóa KH02 với giá trị 27.000.

### Bài 3: Kiểm thử overflow trong phép cộng

Tạo một Receipt có total Long.MAX_VALUE và một Receipt có total 1. Gọi grandTotal. Chứng minh **Math.addExact** ném ArithmeticException thay vì trả số sai.

### Bài 4: Null và blank

Thử RawOrder PAID có mã "  ", customer null, hoặc danh sách lines null. Mỗi trường hợp phải có hành vi nào? Vì sao **không thể coi chúng là đơn không thanh toán** chỉ để filter bỏ?

### Bài 5: Bộ lọc theo thời điểm

Bổ sung thuộc tính **paidAt** vào RawOrder và lọc những đơn PAID trong một kỳ ngày. Xác định timezone, khoảng đầu/cuối và quy tắc inclusive/exclusive. Không so sánh timestamp dưới dạng chuỗi theo may rủi.

### Bài 6: Nhiều khách cùng doanh thu

Áp dụng **OrderRankingDemo**, tạo hai khách có cùng doanh thu, kiểm tra tie-breaker theo customer. Giải thích tại sao cần **List + sorted** thay vì TreeSet với comparator chỉ theo amount.

### Bài 7: Tổng hợp theo SKU

Dùng:

~~~java
receipts.stream()
        .flatMap(r -> r.lines().stream())
        .collect(Collectors.toMap(
                BillLine::sku,
                BillLine::amountCents,
                Math::addExact,
                TreeMap::new));
~~~

Đây là đoạn minh họa cần imports Collectors/TreeMap và biến receipts. Hãy tính tổng doanh thu theo SKU. Phân biệt **tổng tiền theo SKU** với **tổng số lượng theo SKU**; muốn tổng quantity phải thay value mapper và merge function cho phù hợp.

### Bài 8: Chọn chính sách lỗi theo từng đơn

Thiết kế một record/Sealed Result cho phép ghi nhận success và failure. Tạo ba đơn PAID, trong đó một đơn thiếu SKU. Báo cáo vừa phải liệt kê lỗi vừa đánh dấu **doanh thu tính được là partial**, không công bố nó như tổng doanh thu đầy đủ.

### Bài 9: Kiểm thử tính ổn định

Chạy pipeline hai lần với cùng dữ liệu bất biến; so sánh Receipt list và Map. Vì sao không nên dùng một counter bên ngoài để gán số thứ tự trong map? Nếu cần thứ tự, hãy lấy từ chỉ số nguồn hoặc dùng một bước sắp xếp rõ ràng.

### Bài 10: Nâng cấp sang BigDecimal

Hãy thiết kế quy tắc chiết khấu và rounding cho từng dòng. Tại sao phép tính tỷ lệ không nên dùng double rồi ép về long mà không nêu quy tắc? Dùng BigDecimal và RoundingMode theo hợp đồng.

## 19. Checklist nghiệm thu một pipeline xử lý đơn hàng

Trước khi đưa vào sản phẩm thật, kiểm tra:

1. **Nguồn và schema**: có biết chính xác các trường bắt buộc, quy tắc null và đơn vị tiền?
2. **Bộ lọc**: trạng thái nào được tính doanh thu, và chính sách dữ liệu lỗi ở đơn không chọn?
3. **Chuẩn hóa**: có quy tắc strip/case/locale phù hợp với định danh thật?
4. **Dòng hàng**: quantity, unitPriceCents, SKU có được validate?
5. **Số học**: multiplyExact/addExact có đủ miền dữ liệu, hoặc cần BigInteger/BigDecimal?
6. **Bất biến Receipt**: tổng đơn bằng tổng các dòng, mã đã chuẩn hóa?
7. **Grouping**: khóa trùng được cộng thay vì ghi đè, Map order có được xác định nếu cần?
8. **Tập rỗng**: số đơn 0, tổng 0 và Map rỗng có đúng hợp đồng?
9. **Lỗi**: không âm thầm coi dữ liệu sai là doanh thu 0; thông điệp và nguyên nhân được giữ lại?
10. **Trùng đơn**: xử lý duplicate ID và idempotency nếu nguồn có thể phát cùng giao dịch nhiều lần?
11. **Tính thuần**: filter/map không dựa vào shared mutable state hoặc side effect bắt buộc?
12. **Kiểm thử**: có test PAID/PENDING/CANCELLED, null, blank, overflow, nhiều khách và ranking?
13. **Hiệu năng**: có đo trước khi dùng parallel hoặc collector phức tạp?
14. **Bảo mật/riêng tư**: báo cáo/log chỉ hiển thị thông tin cần thiết, tránh đưa thông tin khách hàng nhạy cảm ra console?
15. **Đối soát**: có cơ chế so sánh tổng, số dòng và kết quả với nguồn đáng tin cậy khi phát hành báo cáo?

## 20. Ghi nhớ

Một quy trình Stream đáng tin không chỉ là nối nhiều method reference. Nó là **một dãy hợp đồng**:

**Chọn đúng đơn** bằng filter; **chuẩn hóa đúng định danh** bằng hàm thuần; **xác thực dữ liệu cần thiết** trước khi dùng; **tính tiền bằng số học có kiểm tra giới hạn**; **gom theo khách đúng merge policy**; rồi **kiểm thử cả nhánh thành công và thất bại**.

Trong Java 17, các công cụ tiêu biểu cho bài toán này là **Stream.filter**, **map**, **flatMap**, **mapToLong**, **reduce**, **Collectors.toMap**, **TreeMap**, **Locale.ROOT**, **Math.multiplyExact** và **Math.addExact**. Mỗi công cụ chỉ đảm nhận một phần; tính đúng đắn đến từ việc dùng chúng theo đúng hợp đồng nghiệp vụ.

Câu hỏi tự kiểm tra cuối bài: **“Nếu một đơn bị loại, một mã bị sửa, một dòng bị lỗi hoặc một phép cộng vượt giới hạn, tôi có giải thích chính xác dữ liệu nào được tính, dữ liệu nào không và vì sao không?”** Nếu có, pipeline không chỉ ngắn gọn mà còn có thể bảo trì, kiểm tra và đối soát.