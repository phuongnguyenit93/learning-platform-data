# Tách một chuỗi xử lý phức tạp thành các biến cục bộ rõ nghĩa (Java 10+)

## 1. Vấn đề và mục tiêu của bài thực hành

Trong các ứng dụng Java, một chuỗi xử lý dài thường bắt đầu từ **dữ liệu thô**, sau đó liên tiếp **parse → validate → filter → sort → aggregate → format**. Stream API khiến những thao tác này có thể được viết rất gọn:

~~~java
var output = input.stream()
        .map(this::parse)
        .filter(this::isEligible)
        .sorted(this::compare)
        .map(this::format)
        .collect(Collectors.joining(", "));
~~~

Đoạn trên là **minh họa cấu trúc**, chưa phải một chương trình độc lập. Nó thể hiện một bài toán đọc có vẻ đơn giản: ta biết có nhiều thao tác, nhưng phải tìm từng method mới hiểu **dữ liệu đang ở trạng thái nào** và **điều kiện nghiệp vụ** áp dụng ở bước nào.

Một kỹ thuật refactor là **tách các kết quả trung gian thành local variables có tên rõ nghĩa**:

~~~java
var parsedRecords = parseRecords(input);
var eligibleRecords = onlyEligible(parsedRecords);
var sortedRecords = sortForPresentation(eligibleRecords);
var output = formatRecords(sortedRecords);
~~~

Mỗi tên trả lời một câu hỏi:
- `parsedRecords`: đầu vào đã được phân tích cú pháp chưa?
- `eligibleRecords`: dữ liệu nào qua được điều kiện?
- `sortedRecords`: thứ tự đã được đảm bảo chưa?
- `output`: đã là chuỗi dành cho người đọc chưa?

Bài này thuộc nhóm **Thực hành tổng hợp** trong module **Java 10**. Nó minh họa cách kết hợp **local-variable type inference với `var` (JEP 286)** và nguyên tắc **đặt tên theo ý nghĩa dữ liệu**; những kiến thức này vẫn áp dụng trong JDK 17, 21, 25 và các phiên bản Java hiện đại.

**Thông điệp quan trọng:** Không phải cứ thêm nhiều biến hay thay mọi kiểu tường minh bằng `var` là code sẽ tốt. Mục tiêu là làm rõ **những ranh giới xử lý có giá trị**, giữ nguyên kết quả/side effects của code gốc và cân bằng với chi phí bộ nhớ.

Sau bài học, bạn có thể:
1. Phân tích một chuỗi Stream dài thành các giai đoạn logic.
2. Đặt local variables dựa trên *ý nghĩa kết quả* thay vì tên `a`, `tmp`, `list2`.
3. Sử dụng `var` đúng với quy tắc **static typing** của Java 10.
4. Giữ kết quả ổn định khi đổi từ một pipeline sang nhiều bước.
5. Đọc rõ business rule, ví dụ khoảng ngày, trạng thái, thứ tự sắp xếp và đơn vị tiền.
6. Phân biệt Stream lazy với List đã được materialize.
7. Hiểu trade-off về heap, allocation, GC và số lượt duyệt dữ liệu.
8. Chạy ví dụ Java 17+ tương thích với language/API Java 10.
9. Kiểm tra kết quả và cả các edge cases.
10. Chọn khi nào nên đặt biến, khi nào nên trích xuất named helper methods.

## 2. `var` của Java 10 giúp kỹ thuật này như thế nào?

**JEP 286 — Local-Variable Type Inference** cho phép viết:

~~~java
var firstDay = LocalDate.of(2026, 10, 1);
var nextMonth = firstDay.plusMonths(1);
~~~

thay cho:

~~~java
LocalDate firstDay = LocalDate.of(2026, 10, 1);
LocalDate nextMonth = firstDay.plusMonths(1);
~~~

Trong cả hai cách, **mỗi biến vẫn có kiểu tĩnh `LocalDate`**. Compiler xác định kiểu qua initializer ngay lúc biên dịch, không đợi runtime và không đổi kiểu theo lần gán sau.

~~~java
var count = 4;    // int
count = 5;        // hợp lệ
// count = "five"; // compile-time error
~~~

`var` là **reserved type name** dành cho những vị trí khai báo thích hợp, không phải kiểu dữ liệu tên `var`, cũng không giống `var` của JavaScript.

### Vì sao `var` hữu ích khi tách pipeline?

Với generic types dài, lặp lại kiểu bên trái có thể che tên biến:

~~~java
List<Order> parsedOrders = rawLines.stream()
        .map(Order::parse)
        .collect(Collectors.toList());
~~~

Từ Java 10:

~~~java
var parsedOrders = rawLines.stream()
        .map(Order::parse)
        .collect(Collectors.toList());
~~~

Khi `Order.parse` trả `Order`, compiler suy ra kiểu của `parsedOrders` từ kết quả collector. Tên biến `parsedOrders` trở thành điểm nhấn dễ đọc.

Tuy nhiên **không lạm dụng**:

~~~java
var x = factory.create();
var y = transform(x);
~~~

Nếu `factory.create()` hoặc `transform(x)` không cho biết giá trị được tạo là gì, khai báo kiểu tường minh hoặc đổi tên method/variable có thể dễ hiểu hơn.

### Những giới hạn cần nhớ

Không hợp lệ trong Java 10:

~~~java
// var a;                 // thiếu initializer
// var a = null;          // null literal không cung cấp kiểu
// var fn = x -> x;       // lambda cần target functional-interface type
// var make = String::new;// method reference cần target type
// var a = 1, b = 2;      // không khai báo nhiều biến kiểu này
~~~

`var` không dùng cho **fields**, **method parameters thông thường** hay **return types**. Java 11 bổ sung cú pháp `var` cho các **lambda parameters** trong những điều kiện cụ thể; điều đó không làm Java trở thành dynamic typing.

Cũng phải thận trọng khi dùng diamond:

~~~java
var names = new ArrayList<>();
// Kiểu thường được suy ra là ArrayList<Object>.

var typedNames = new ArrayList<String>();
// ArrayList<String>.

List<String> namesAsInterface = new ArrayList<>();
// List<String> do người viết code chỉ định.
~~~

Nếu cần bảo toàn **interface type** hoặc generic target typing, viết kiểu tường minh vẫn có thể tốt hơn.

## 3. Khi nào đáng tạo một biến cục bộ trung gian?

| Tình huống | Tên gợi ý | Lợi ích |
| --- | --- | --- |
| Dữ liệu từ bên ngoài, chưa kiểm tra | `rawOrderLines` | Không nhầm raw text với domain objects |
| Dữ liệu đã parse | `parsedOrders` | Có điểm kiểm tra lỗi parsing |
| Đã qua điều kiện nghiệp vụ | `paidInMonth` | Thể hiện ngữ nghĩa ngay từ tên |
| Có thứ tự xác định | `rankedOrders` | Dễ xem sort/tie-break |
| Giá trị tính toán quan trọng | `totalPaidVnd` | Có ý nghĩa và đơn vị |
| Mốc thời gian ranh giới | `endExclusive` | Rõ chính sách date range |
| Quy tắc so sánh | `amountDescendingThenId` | Có thể review/reuse comparator |
| Các phần tử để render | `displayParts` | Tách domain model khỏi trình bày |
| Kết quả cuối cùng | `orderSummary` | Không đặt chung chung `result` |

Một biến nên mang **thông tin mới** về dữ liệu hoặc cách xử lý. Ngược lại, các tên `data1`, `list2`, `temp3` chỉ làm pipeline dài hơn mà không dễ đọc hơn.

Tách bước là hợp lý khi:
- Một kết quả có tên nghiệp vụ rõ;
- Cần đặt breakpoint hoặc unit test;
- Giá trị dùng hơn một lần;
- Có một validation, side effect hoặc điểm có thể fail cần tách;
- Một comparator/predicate quá dài;
- Có ranh giới giữa domain data và presentation.

**Không nhất thiết tạo biến** cho phép tính trivial chỉ dùng một lần nếu tên không đóng góp ý nghĩa. Cũng không phải mọi bước Stream đều phải kết thúc bằng `collect(toList())`; phần dưới sẽ chỉ ra chi phí của cách đó.

## 4. Bài toán tổng hợp: báo cáo đơn hàng đã thanh toán

Để có ví dụ thật sự chạy được, ta sử dụng dữ liệu đơn hàng giả lập theo format:

~~~text
id|customer|date|status|amountVnd
~~~

Dữ liệu:

~~~text
ORD-104|Lan|2026-10-02|PAID|150000
ORD-101|Minh|2026-10-04|PAID|200000
ORD-102|Lan|2026-09-30|PAID|300000
ORD-103|Mai|2026-10-05|PENDING|500000
ORD-106|Binh|2026-10-02|PAID|200000
ORD-107|Ha|2026-10-08|PAID|75000
ORD-108|Ha|2026-11-01|PAID|99000
ORD-109|Linh|2026-10-11|REFUNDED|100000
~~~

Yêu cầu:
1. Chuyển từng dòng thành đối tượng `Order`.
2. Dữ liệu có cấu trúc sai phải bị **từ chối rõ ràng**, không âm thầm bỏ qua.
3. Chỉ lấy đơn `PAID`.
4. Chỉ lấy đơn trong **tháng 10/2026**.
5. Sắp xếp **số tiền giảm dần**, nếu bằng nhau thì **ID tăng dần**.
6. Tính **số đơn**, **tổng tiền VND** và chuỗi `ID(số tiền)` nối bằng `, `.
7. So sánh kết quả với một pipeline viết gộp để chắc chắn refactor không làm sai.

Những đơn thỏa điều kiện là:
- `ORD-101`: 200000;
- `ORD-106`: 200000;
- `ORD-104`: 150000;
- `ORD-107`: 75000.

Tổng cần đúng **625000 VND**. Hai đơn cùng 200000 được sắp theo ID. Không tính `PENDING`, `REFUNDED`, đơn thuộc tháng 9 hoặc tháng 11.

### Vì sao chọn `LocalDate` và `BigDecimal`?

**`LocalDate`** biểu diễn ngày theo lịch, không có time-of-day hoặc timezone. Với bài tập báo cáo theo ngày, nó cho kết quả không phụ thuộc đồng hồ hệ thống.

**`BigDecimal`** phù hợp khi mô hình nghiệp vụ yêu cầu số học thập phân chính xác. Chương trình chỉ chấp nhận amount dưới dạng số nguyên dương VND; dùng `toPlainString()` để có output ổn định, không phụ thuộc locale hoặc ký hiệu khoa học.

Với tiền ở production, chính sách rounding, currency và minor units cần được định nghĩa tại domain boundary. Ví dụ này chọn dạng nguyên VND để tránh đưa ra một rounding policy không nằm trong đề bài.

## 5. “Trước khi refactor”: pipeline gộp

Một đoạn xử lý có thể trông như thế này:

~~~java
var details = inputLines.stream()
        .map(Order::parse)
        .filter(order -> order.status == Status.PAID
                && !order.date.isBefore(firstDay)
                && order.date.isBefore(firstDay.plusMonths(1)))
        .sorted(Comparator.comparing(
                (Order order) -> order.amountVnd)
                .reversed()
                .thenComparing(order -> order.id))
        .map(order -> order.id + "("
                + order.amountVnd.toPlainString() + ")")
        .collect(Collectors.joining(", "));
~~~

Đây là **đoạn trích trong ngữ cảnh một method**, không phải chương trình độc lập; lớp `Order`, enum `Status` và imports sẽ có trong mã hoàn chỉnh.

Vấn đề khi cần bảo trì:
- Điều kiện thời gian và status nằm chung trong lambda;
- Comparator dài chen giữa;
- Từ `String` → `Order` → `String` diễn ra trong một biểu thức;
- Khó xem dữ liệu trung gian trong debugger;
- Khi cần thêm tổng tiền, dễ viết thêm pipeline khác và parse/filter lại;
- Có thể quên tie-break làm kết quả không xác định.

Tuy vậy, **một chuỗi Stream liên tiếp không phải lỗi chỉ vì dài**. Với dữ liệu lớn, nó còn có thể hiệu quả hơn khi tránh tạo List trung gian. Mục tiêu refactor là **làm rõ trách nhiệm**, không phải áp dụng một mẫu cứng.

## 6. “Sau khi refactor”: các bước được đặt tên

Một cách tách:

~~~java
var endExclusive = firstDay.plusMonths(1);

var parsedOrders = inputLines.stream()
        .map(Order::parse)
        .collect(Collectors.toList());

var paidInMonth = parsedOrders.stream()
        .filter(order -> order.status == Status.PAID)
        .filter(order -> !order.date.isBefore(firstDay)
                && order.date.isBefore(endExclusive))
        .collect(Collectors.toList());

var ranking = Comparator.comparing(
        (Order order) -> order.amountVnd)
        .reversed()
        .thenComparing(order -> order.id);

var rankedOrders = paidInMonth.stream()
        .sorted(ranking)
        .collect(Collectors.toList());

var displayParts = rankedOrders.stream()
        .map(order -> order.id + "("
                + order.amountVnd.toPlainString() + ")")
        .collect(Collectors.toList());

var details = String.join(", ", displayParts);
var totalPaidVnd = rankedOrders.stream()
        .map(order -> order.amountVnd)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

**Dòng dữ liệu trở nên dễ đọc hơn:**

~~~text
inputLines (List<String>)
        │ parse
        ▼
parsedOrders (List<Order>)
        │ filter PAID + tháng cần tính
        ▼
paidInMonth (List<Order>)
        │ sort amount DESC, ID ASC
        ▼
rankedOrders (List<Order>)
        ├───────────────┐
        │ sum amounts   │ map format
        ▼               ▼
totalPaidVnd       displayParts
(BigDecimal)       (List<String>)
                        │ join
                        ▼
                    details (String)
~~~

Ở mỗi ranh giới, debugger có thể giúp xem danh sách, số phần tử và invariants. Các local variables đều có **kiểu tĩnh suy luận được**, không chứa một kiểu “dynamic”.

**Đánh đổi:** Có thêm các `List` được materialize, làm tăng bộ nhớ và số lượt duyệt. Trong một hệ thống đọc hàng triệu rows, cân nhắc giữ pipeline lazy và chỉ tách những predicate/comparator/helper methods có tên.

## 7. Ví dụ Java 17+ hoàn chỉnh, chạy được theo Java 10

File **`OrderPipelineRefactorDemo.java`** sau đây:
- Không cần thư viện ngoài JDK.
- Chỉ dùng APIs và cú pháp phù hợp với **Java 10**.
- Dùng `var` ở các biến cục bộ có initializer rõ.
- Dùng `BigDecimal` và `LocalDate`.
- Có hai implementations `detailsInline` và `buildReportStepwise`.
- Kiểm tra output, count và total bằng điều kiện luôn được thực thi, không phụ thuộc flag `-ea`.
- Có một phép kiểm tra parser từ chối dòng sai.

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class OrderPipelineRefactorDemo {

    enum Status {
        PAID, PENDING, REFUNDED
    }

    static final class Order {
        final String id;
        final String customer;
        final LocalDate date;
        final Status status;
        final BigDecimal amountVnd;

        Order(String id, String customer, LocalDate date,
              Status status, BigDecimal amountVnd) {
            this.id = id;
            this.customer = customer;
            this.date = date;
            this.status = status;
            this.amountVnd = amountVnd;
        }

        static Order parse(String line) {
            if (line == null) {
                throw new IllegalArgumentException("Missing input line");
            }

            var columns = line.split("\\|", -1);
            if (columns.length != 5) {
                throw new IllegalArgumentException("Expected five fields");
            }

            var id = columns[0].trim();
            var customer = columns[1].trim();

            if (id.isEmpty() || customer.isEmpty()) {
                throw new IllegalArgumentException(
                        "ID and customer are required");
            }

            var date = LocalDate.parse(columns[2].trim());
            var status = Status.valueOf(columns[3].trim());

            var amountText = columns[4].trim();
            if (!amountText.matches("[0-9]+")) {
                throw new IllegalArgumentException(
                        "VND amount must be an unsigned integer");
            }

            var amountVnd = new BigDecimal(amountText);
            if (amountVnd.signum() <= 0) {
                throw new IllegalArgumentException(
                        "VND amount must be positive");
            }

            return new Order(id, customer, date, status, amountVnd);
        }
    }

    static final class Report {
        final int paidCount;
        final BigDecimal totalPaidVnd;
        final String details;

        Report(int paidCount, BigDecimal totalPaidVnd, String details) {
            this.paidCount = paidCount;
            this.totalPaidVnd = totalPaidVnd;
            this.details = details;
        }
    }

    static Comparator<Order> amountDescendingThenId() {
        return Comparator
                .comparing((Order order) -> order.amountVnd)
                .reversed()
                .thenComparing(order -> order.id);
    }

    static boolean inMonth(Order order, LocalDate firstDay,
                           LocalDate endExclusive) {
        return !order.date.isBefore(firstDay)
                && order.date.isBefore(endExclusive);
    }

    static String formatItem(Order order) {
        return order.id + "(" + order.amountVnd.toPlainString() + ")";
    }

    // Cách viết một Stream pipeline:
    static String detailsInline(List<String> inputLines,
                                LocalDate firstDay) {
        var endExclusive = firstDay.plusMonths(1);

        return inputLines.stream()
                .map(Order::parse)
                .filter(order -> order.status == Status.PAID
                        && inMonth(order, firstDay, endExclusive))
                .sorted(amountDescendingThenId())
                .map(OrderPipelineRefactorDemo::formatItem)
                .collect(Collectors.joining(", "));
    }

    // Cách tách các kết quả trung gian thành local variables:
    static Report buildReportStepwise(List<String> inputLines,
                                      LocalDate firstDay) {
        var endExclusive = firstDay.plusMonths(1);

        var parsedOrders = inputLines.stream()
                .map(Order::parse)
                .collect(Collectors.toList());

        var paidInMonth = parsedOrders.stream()
                .filter(order -> order.status == Status.PAID)
                .filter(order -> inMonth(
                        order, firstDay, endExclusive))
                .collect(Collectors.toList());

        var ranking = amountDescendingThenId();
        var rankedOrders = paidInMonth.stream()
                .sorted(ranking)
                .collect(Collectors.toList());

        var displayParts = rankedOrders.stream()
                .map(OrderPipelineRefactorDemo::formatItem)
                .collect(Collectors.toList());

        var details = String.join(", ", displayParts);

        var totalPaidVnd = rankedOrders.stream()
                .map(order -> order.amountVnd)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new Report(
                rankedOrders.size(), totalPaidVnd, details);
    }

    public static void main(String[] args) {
        var inputLines = List.of(
                "ORD-104|Lan|2026-10-02|PAID|150000",
                "ORD-101|Minh|2026-10-04|PAID|200000",
                "ORD-102|Lan|2026-09-30|PAID|300000",
                "ORD-103|Mai|2026-10-05|PENDING|500000",
                "ORD-106|Binh|2026-10-02|PAID|200000",
                "ORD-107|Ha|2026-10-08|PAID|75000",
                "ORD-108|Ha|2026-11-01|PAID|99000",
                "ORD-109|Linh|2026-10-11|REFUNDED|100000"
        );

        var firstDay = LocalDate.of(2026, 10, 1);
        var report = buildReportStepwise(inputLines, firstDay);
        var inlineDetails = detailsInline(inputLines, firstDay);

        // Kiểm tra bằng if, không phụ thuộc Java assert có bật không.
        if (!inlineDetails.equals(report.details)
                || report.paidCount != 4
                || report.totalPaidVnd.compareTo(
                        new BigDecimal("625000")) != 0) {
            throw new AssertionError(
                    "Refactoring changed the expected result");
        }

        boolean invalidRowRejected;
        try {
            Order.parse("INVALID");
            invalidRowRejected = false;
        } catch (IllegalArgumentException expected) {
            invalidRowRejected = true;
        }

        System.out.println("Month: "
                + firstDay.toString().substring(0, 7));
        System.out.println("Eligible orders: " + report.paidCount);
        System.out.println("Total paid: "
                + report.totalPaidVnd.toPlainString() + " VND");
        System.out.println("Order details: " + report.details);
        System.out.println("Equivalent detail: "
                + inlineDetails.equals(report.details));
        System.out.println("Invalid row rejected: " + invalidRowRejected);
    }
}
~~~

### Lệnh biên dịch và chạy

Bằng JDK 17+ có hỗ trợ target Java 10:

~~~bash
javac --release 10 OrderPipelineRefactorDemo.java
java OrderPipelineRefactorDemo
~~~

Hoặc compile với phiên bản hiện tại của compiler:

~~~bash
javac OrderPipelineRefactorDemo.java
java OrderPipelineRefactorDemo
~~~

**Stdout chính xác của chương trình:**

~~~text
Month: 2026-10
Eligible orders: 4
Total paid: 625000 VND
Order details: ORD-101(200000), ORD-106(200000), ORD-104(150000), ORD-107(75000)
Equivalent detail: true
Invalid row rejected: true
~~~

**Vì sao chắc chắn kết quả này?**
- `LocalDate.of(2026, 10, 1)` cố định tháng; không dùng `LocalDate.now()`.
- Có bốn đơn đúng `PAID` và thuộc `[2026-10-01, 2026-11-01)`.
- Tổng `200000 + 200000 + 150000 + 75000 = 625000`.
- Comparator sắp amount giảm dần; `ORD-101` đứng trước `ORD-106` khi amount bằng nhau.
- Cả `detailsInline` và `buildReportStepwise` gọi cùng các quy tắc parse, filter, sort, format nên chuỗi details trùng trên dataset này.
- Dòng `INVALID` không có năm trường; parser ném `IllegalArgumentException`, phép kiểm tra in `true`.

**Không cần database, network, đồng hồ hiện tại hoặc random**, nên stdout có thể tái lập.

### Lưu ý về `--release 10`

Các API được ví dụ sử dụng đều có mặt trong Java 10: `List.of`, `LocalDate`, `BigDecimal`, `Comparator`, `Collectors.toList`, `var`. Tùy compiler JDK rất mới, một số target `--release` cũ có thể không còn được hỗ trợ; khi đó biên dịch mặc định trên một JDK hiện đại để học ngữ nghĩa refactor, hoặc dùng compiler phù hợp nếu thực sự cần target Java 10.

**Đừng đổi `.collect(Collectors.toList())` thành `.toList()` khi vẫn cần `--release 10`.** `Stream.toList()` chỉ xuất hiện từ Java 16. Việc sử dụng `Collectors.toList()` ở đây là chủ ý để giữ source/API compatibility, không phải lời khuyên về khả năng thay đổi nội dung của List kết quả (API không cam kết list type/mutability cụ thể).

## 8. Giải thích từng biến cục bộ trong bản refactor

### 8.1. `endExclusive` biểu đạt thời gian rõ ràng

~~~java
var endExclusive = firstDay.plusMonths(1);
~~~

Thay vì gọi `firstDay.plusMonths(1)` ở nhiều vị trí, tên `endExclusive` biểu đạt khoảng thời gian **nửa mở**:

~~~text
[firstDay, endExclusive)
~~~

Ngày 01/10 được tính, ngày 01/11 không được tính. Đặt tên có thể tránh lỗi khi code được mở rộng sang thời gian có timezone.

### 8.2. `parsedOrders` là kiểu dữ liệu đã được chuyển đổi

~~~java
var parsedOrders = inputLines.stream()
        .map(Order::parse)
        .collect(Collectors.toList());
~~~

Kiểu suy luận là `List<Order>`, không phải `List<String>`. Tên cho biết dữ liệu đã qua parser, giúp:
- Xem được số record trước lọc;
- Phát hiện lỗi cấu trúc đầu vào;
- Đặt breakpoint sau parse;
- Tránh dùng nhầm raw text ở bước nghiệp vụ.

Ở code gốc, toàn bộ parse nằm trong pipeline; debug theo giai đoạn khó hơn. Trong bản tách, `parsedOrders` là một List thực sự đã được tính.

### 8.3. `paidInMonth` là kết quả lọc có ý nghĩa nghiệp vụ

~~~java
var paidInMonth = parsedOrders.stream()
        .filter(order -> order.status == Status.PAID)
        .filter(order -> inMonth(
                order, firstDay, endExclusive))
        .collect(Collectors.toList());
~~~

Tên nói rõ **đã thanh toán và trong tháng**. Ta không cần đoán `filter1` là gì. Hàm `inMonth` còn tách được logic date range để test boundary cases.

### 8.4. `ranking` và `rankedOrders` tách policy khỏi dữ liệu

~~~java
var ranking = amountDescendingThenId();
var rankedOrders = paidInMonth.stream()
        .sorted(ranking)
        .collect(Collectors.toList());
~~~

`ranking` có kiểu tĩnh `Comparator<Order>`. `rankedOrders` có kiểu tĩnh `List<Order>`.

Comparator có tên giúp trả lời: *Sắp xếp theo tiêu chí nào?* Nó là một quy tắc đọc độc lập với việc dữ liệu được lưu trong List hay xuất ra String.

### 8.5. `displayParts` chỉ chứa dữ liệu presentation

~~~java
var displayParts = rankedOrders.stream()
        .map(OrderPipelineRefactorDemo::formatItem)
        .collect(Collectors.toList());

var details = String.join(", ", displayParts);
~~~

Domain object `Order` được chuyển thành String riêng ở giai đoạn hiển thị. Nếu thay cách định dạng, không cần sửa điều kiện lọc hoặc comparator.

**Không bắt buộc tạo `displayParts` ở mọi ứng dụng**. Nếu chỉ dùng một lần, `.map(...).collect(Collectors.joining(", "))` thường gọn và ít cấp phát hơn.

### 8.6. `totalPaidVnd` cho thấy đơn vị và phép toán

~~~java
var totalPaidVnd = rankedOrders.stream()
        .map(order -> order.amountVnd)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Tên làm rõ **tổng tiền VND**, tránh nhầm với số đơn. `BigDecimal.ZERO` cho kết quả 0 khi tập đầu vào rỗng. Vì amount được parse từ chữ số nguyên dương, output `toPlainString()` có thể dự đoán.

### 8.7. `report` và `inlineDetails` được dùng để đối chiếu

~~~java
var report = buildReportStepwise(inputLines, firstDay);
var inlineDetails = detailsInline(inputLines, firstDay);
~~~

Cặp biến giúp kiểm tra refactor: cùng raw data và rules phải tạo cùng chi tiết. Chương trình còn so tổng tiền và count mong đợi.

**Một dataset trùng output chưa chứng minh mọi trường hợp đều tương đương.** Với production còn phải test edge cases, thứ tự exception và side effects.

## 9. Quy trình refactor giữ nguyên hành vi

### Bước 1 — Chốt hợp đồng đầu vào/đầu ra

Trước khi sửa:
- Input là loại gì?
- Có dữ liệu null/trống/sai định dạng không?
- Filtering rules cụ thể?
- Sort/ordering contract?
- Aggregation dùng đơn vị và precision nào?
- Có side effects, transactions hoặc I/O không?
- Những exceptions là một phần contract?

Không hiểu contract thì một thay đổi “cho dễ đọc” có thể là **feature change**.

### Bước 2 — Viết test kết quả ban đầu

Dùng:
- Dataset bình thường;
- Danh sách rỗng;
- Một phần tử;
- Ngày đầu tháng, cuối tháng;
- Ngày ngoài tháng;
- Hai đơn cùng amount;
- Trạng thái khác `PAID`;
- Dòng thiếu field hoặc amount sai;
- Input null nếu cần chính sách null.

Test cả **count**, **total** và **order details**, vì một pipeline sai thứ tự vẫn có thể cho tổng tiền đúng.

### Bước 3 — Đặt tên cho các ranh giới có ý nghĩa

Ví dụ:

~~~text
raw input
→ parsed records
→ eligible records
→ ranked records
→ aggregate / rendered output
~~~

Đặt biến theo **dữ liệu đã đạt trạng thái nào**, không đặt tên theo vị trí câu lệnh.

### Bước 4 — Chọn local variable hay helper method

Local variable phù hợp khi:
- Giá trị trung gian cần được xem hoặc dùng nhiều lần;
- Scope ngắn;
- Tên có ý nghĩa;
- Memory overhead chấp nhận được.

Helper method phù hợp khi:
- Predicate/comparator/formatting cần kiểm thử độc lập;
- Có thể dùng lại;
- Một đoạn lambda quá dài;
- Muốn giữ một pipeline duy nhất để tránh extra Lists.

**Không biến mọi biểu thức trivial thành một method hoặc biến**, làm người đọc phải nhảy qua nhiều nơi.

### Bước 5 — Giữ đúng thứ tự validation, filtering và side effects

Stream pipeline có tính **lazy**. Ví dụ:

~~~java
var stream = rawLines.stream().map(Order::parse);
~~~

Chỉ khai báo `stream` thường **chưa chạy parser**. Parser được tiêu thụ khi có terminal operation.

Trong bản tách:

~~~java
var parsedOrders = rawLines.stream()
        .map(Order::parse)
        .collect(Collectors.toList());
~~~

toàn bộ input được parse trước khi lọc. Nếu có dữ liệu sai định dạng mà pipeline gốc chỉ xử lý một phần vì short-circuiting, thời điểm hoặc khả năng ném lỗi có thể khác.

**Refactor không được tự ý bỏ qua các lỗi parsing** bằng cách lọc chuỗi raw trước khi parse mà không có lý do nghiệp vụ.

### Bước 6 — Đo memory/performance nếu là hot path

Nhiều lần `collect(toList())` tạo nhiều Lists:
- `parsedOrders`;
- `paidInMonth`;
- `rankedOrders`;
- `displayParts`.

Trên vài trăm records, overhead có thể chấp nhận để đổi lấy readability. Trên hàng triệu records, peak heap và GC pressure có thể lớn.

Dùng profiler/benchmark đúng workload để quyết định. Đừng tuyên bố “refactor nhanh hơn” chỉ từ việc nhìn code.

## 10. Trường hợp nên tách logic nhưng giữ một Stream duy nhất

Tính rõ nghĩa không bắt buộc tạo List mỗi stage. Một phiên bản cân bằng:

~~~java
var endExclusive = firstDay.plusMonths(1);

java.util.function.Predicate<Order> isPaidInMonth =
        order -> order.status == Status.PAID
                && inMonth(order, firstDay, endExclusive);

var ranking = amountDescendingThenId();

var details = orders.stream()
        .filter(isPaidInMonth)
        .sorted(ranking)
        .map(OrderPipelineRefactorDemo::formatItem)
        .collect(Collectors.joining(", "));
~~~

**Đây là trích đoạn minh họa trong class của bài**, giả sử `orders` là `List<Order>` đã parse. Tên predicate/comparator rõ mà chỉ cần một terminal operation.

Một cách khác là đưa các bước vào helper methods:

~~~java
static boolean isEligible(Order order, LocalDate start,
                          LocalDate endExclusive) {
    return order.status == Status.PAID
            && inMonth(order, start, endExclusive);
}
~~~

Rồi gọi:

~~~java
var details = orders.stream()
        .filter(order -> isEligible(
                order, firstDay, endExclusive))
        .sorted(amountDescendingThenId())
        .map(OrderPipelineRefactorDemo::formatItem)
        .collect(Collectors.joining(", "));
~~~

Kết quả vẫn có ý nghĩa, không cần thêm List ở từng ranh giới. **Đặt tên cho chính sách** thường là bước refactor mang lại giá trị cao nhất khi pipeline chạy với dữ liệu lớn.

## 11. Không dùng lại cùng một Stream sau terminal operation

Một nhầm lẫn thường gặp:

~~~java
var paidStream = orders.stream().filter(Order::isPaid);

// var count = paidStream.count();
// var total = paidStream
//         .map(Order::amountVnd)
//         .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Hai terminal operations trên cùng `paidStream` là không hợp lệ: Stream chỉ được tiêu thụ một lần.

Nếu cần count và total:
- Tạo Stream mới từ collection có thể lặp lại;
- Materialize một List đúng chỗ;
- Hoặc viết collector/aggregation trong một lượt.

Ví dụ giả định `Order` có methods `isPaid()`, `amountVnd()`:

~~~java
var paidOrders = orders.stream()
        .filter(Order::isPaid)
        .collect(Collectors.toList());

var count = paidOrders.size();
var total = paidOrders.stream()
        .map(Order::amountVnd)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Đoạn này **không phải mã chạy độc lập**, mà minh họa việc lưu kết quả dưới dạng List để có thể duyệt lại. Chương trình runnable ở mục 7 dùng fields `status`, `amountVnd` thay vì hai getter đó.

**Phân biệt:** Một biến `var stream = ...` chỉ có kiểu Stream và vẫn là pipeline lazy. Nó **không tự biến thành kết quả đã lọc**, dù tên biến có chữ `paid`.

## 12. Những lỗi dễ làm thay đổi semantics

### 12.1. Đổi thứ tự parse và filter

Không tương đương:

~~~java
lines.stream()
        .map(Order::parse)
        .filter(order -> order.status == Status.PAID);
~~~

và:

~~~java
lines.stream()
        .filter(line -> line.contains("|PAID|"))
        .map(Order::parse);
~~~

Đoạn thứ hai có thể bỏ qua input sai hoặc match một chuỗi `PAID` xuất hiện trong phần khác của record. Một filter trên raw text không thể tự thay thế validation có kiểu.

### 12.2. Đổi các phép short-circuit

Pipeline gốc dùng `findFirst`, `anyMatch`, `limit` có thể **không cần xử lý toàn bộ nguồn**. Nếu refactor bằng cách collect mọi phần tử trước, bạn có thể:
- Parse nhiều record hơn;
- Tăng CPU/heap;
- Gây thêm lỗi vốn không xảy ra;
- Thay side effects;
- Tăng I/O nếu source là file/network.

Giữ lazy processing nếu early-stop là một phần của contract.

### 12.3. Đổi thứ tự sắp xếp

Nếu thiếu tie-break:
- Kết quả có thể phụ thuộc encounter order;
- Khi source/collection thay đổi, output có thể đổi;
- Dù count và total vẫn đúng, chi tiết report có thể sai yêu cầu.

Trong bài, amount DESC rồi ID ASC là hợp đồng được nêu rõ.

### 12.4. Dùng `peek` cho side effect

`peek` có thể hữu ích để quan sát trong lúc debug, nhưng không nên thực hiện những thay đổi nghiệp vụ quan trọng dựa trên giả định mọi phần tử luôn đi qua đó. Stream optimization/short-circuiting có thể ảnh hưởng số lần chạy callback.

Nếu cần ghi DB, gửi message hoặc gọi API, hãy tách **side-effect boundary** rõ ràng và dùng cơ chế transaction/retry/idempotency phù hợp.

### 12.5. Làm mất độ chính xác tiền tệ

Không đổi `BigDecimal` thành `double` chỉ vì muốn một phép `sum()` ngắn hơn. Với tiền, precision/currency/rounding policy có thể là một phần của contract.

### 12.6. Thay đổi exception và validation order

Nếu code gốc kiểm tra null trước khi gọi service, refactor không nên vô tình gọi service trước rồi mới ném exception. Khi xử lý I/O, transaction hoặc security, thứ tự lỗi/side effect có thể rất quan trọng.

### 12.7. Bị thay đổi quyền sửa List

`List.of` trả collection không cho mutate. `Collectors.toList()` **không hứa chắc** implementation type hay mutability cụ thể. `Stream.toList()` từ Java 16 trả unmodifiable list.

Khi refactor collection handling, phải xác định **có cần mutate kết quả hay không**. Nếu cần ArrayList có thể thay đổi:
 
~~~java
var mutableOrders = orders.stream()
        .filter(Order::isPaid)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Đây là đoạn minh họa, cần import và các members tương ứng nếu dùng độc lập. Không dựa vào việc một JDK hiện tại trả ArrayList từ `Collectors.toList()` như một cam kết API.

## 13. Kiểm thử sau refactor: danh sách tình huống

| Trường hợp | Kết quả mong muốn | Vì sao cần |
| --- | --- | --- |
| Input rỗng | Count 0, total 0, details rỗng | Không được có lỗi từ reduce/join |
| Một đơn PAID đúng tháng | Count 1 | Kiểm tra logic tối thiểu |
| Đơn PENDING đúng tháng | Bị loại | Đảm bảo lọc status |
| Đơn REFUNDED đúng tháng | Bị loại | Không tính tiền đã hoàn |
| PAID ngày 01/10/2026 | Được lấy | Ranh giới đầu kỳ inclusive |
| PAID ngày 31/10/2026 | Được lấy | Ngày cuối tháng vẫn hợp lệ |
| PAID ngày 01/11/2026 | Bị loại | Ranh giới cuối kỳ exclusive |
| Cùng amount, ID khác | ID ASC | Đảm bảo tie-break |
| Dòng thiếu trường | Bị từ chối | Không bỏ qua dữ liệu hỏng |
| Ngày sai ISO | Bị từ chối | Không parse sai |
| Status không hỗ trợ | Bị từ chối | Không tự coi như PAID |
| Amount âm/zero/chứa ký tự | Bị từ chối | Bảo toàn invariant |
| Dữ liệu lượng lớn | Chạy trong memory budget | Materialization có chi phí |

Một kiểm thử bổ sung khi sử dụng class bài tập:

~~~java
var report = buildReportStepwise(
        java.util.List.<String>of(),
        java.time.LocalDate.of(2026, 10, 1));
~~~

**Đây là trích đoạn gọi phương thức trong class, không phải chương trình độc lập.** Với input rỗng, mong đợi:
- `report.paidCount == 0`;
- `report.totalPaidVnd.compareTo(BigDecimal.ZERO) == 0`;
- `report.details.equals("")`.

Nếu test tự động:
- Dùng JUnit hoặc framework phù hợp trong dự án (phiên bản hiện hành của project);
- Tách parser/filter/comparator khi cần unit test;
- Thêm property-based tests nếu phải bảo toàn nhiều invariants;
- Dùng integration tests cho các side effects thật.

**Một stdout mẫu đúng không tự chứng minh mọi input tương đương.**

## 14. Đặt tên biến thế nào cho dễ review?

| Tên mơ hồ | Tên rõ nghĩa | Ý nghĩa |
| --- | --- | --- |
| `x` | `rawOrderLines` | Chuỗi chưa parse |
| `data` | `parsedOrders` | Domain objects đã parse |
| `list1` | `paidInMonth` | Đã qua điều kiện thanh toán/tháng |
| `list2` | `rankedOrders` | Đã sắp xếp |
| `cmp` | `amountDescendingThenId` | Comparator policy |
| `date2` | `endExclusive` | Đầu kỳ kế tiếp |
| `num` | `paidOrderCount` | Đơn vị đếm |
| `sum` | `totalPaidVnd` | Tổng tiền theo VND |
| `str` | `orderDetails` | Chuỗi hiển thị |
| `ok` | `isEligibleForBilling` | Điều kiện Boolean |

Các quy tắc có ích:
- Danh từ cho dữ liệu: `parsedOrders`, `summary`.
- Động từ cho hành động: `parseOrders`, `calculateTotal`.
- Boolean có dạng khẳng định rõ: `isPaid`, `hasAccess`.
- Thêm đơn vị ở chỗ dễ nhầm: `amountVnd`, `durationMillis`, `sizeBytes`.
- Nếu biến thể hiện dữ liệu đã qua xử lý, tên nên nói rõ trạng thái: `validatedRequest`, `normalizedEmails`.
- Tránh tên dài một cách máy móc. `eligibleOrders` có thể đủ nếu method/context đã chỉ rõ tháng và loại nghiệp vụ.

**Không dùng `var` như lý do để đặt tên kém.** Khi kiểu không xuất hiện bên trái, tên và initializer càng cần chất lượng.

## 15. Khi nào dùng kiểu tường minh thay `var`?

Có thể viết:

~~~java
var ranking = amountDescendingThenId();
~~~

Nếu method name rõ, kiểu `Comparator<Order>` dễ suy ra.

Nhưng khi muốn nhấn mạnh hợp đồng:

~~~java
Comparator<Order> ranking = amountDescendingThenId();
List<Order> orders = new ArrayList<>();
BigDecimal totalPaidVnd = calculateTotal(orders);
~~~

cũng hoàn toàn hợp lý.

Chọn **kiểu tường minh** khi:
- Muốn giới hạn API interface như `List<Order>` thay vì concrete `ArrayList<Order>`;
- Initializer quá mơ hồ;
- Generic type inference dễ ra kiểu khác mong muốn;
- Kiểu trả về của helper API là điều người đọc cần thấy ngay;
- Một thay đổi trong initializer không nên âm thầm đổi static type của local variable.

Chọn `var` khi:
- Initializer là `new SomeDescriptiveType(...)`;
- Method name trả về kiểu rõ;
- Generic type quá dài và không có thông tin mới;
- Scope ngắn;
- Tên biến nói rõ nội dung.

**Không có quy tắc “luôn var” hay “không bao giờ var”.** OpenJDK Project Amber Style Guidelines nhấn mạnh dùng local type inference khi nó làm code dễ đọc hơn, không phải chỉ để giảm số ký tự.

## 16. Bộ nhớ và hiệu năng: cái giá của những List trung gian

Trong bản stepwise, các `collect(Collectors.toList())` tạo thêm kết quả được giữ trong memory:
- `parsedOrders` giữ toàn bộ đối tượng đã parse.
- `paidInMonth` giữ references tới những đối tượng đủ điều kiện.
- `rankedOrders` giữ references ở thứ tự mới.
- `displayParts` giữ Strings để định dạng.

Chúng không nhất thiết **nhân bản sâu** toàn bộ các đối tượng `Order`, nhưng vẫn tạo List structures, references và Strings mới. Với dữ liệu hàng triệu records, overhead có thể đáng kể.

Tuy nhiên bản tách có lợi khi:
- Cần tái sử dụng `rankedOrders` cho nhiều thống kê;
- Cần debug từng mốc;
- Parser/validation có chi phí cao và không muốn chạy lại;
- Bộ dữ liệu vừa phải, ưu tiên maintainability.

Bản pipeline một lượt có lợi khi:
- Dữ liệu lớn;
- Các bước chỉ dùng một lần;
- Không cần giữ kết quả trung gian;
- Không cần debug các trạng thái bên trong lâu dài.

**Giải pháp cân bằng:** trích xuất các named functions/predicates/comparators nhưng vẫn thực hiện trên một Stream.

Không công bố kết luận “tách biến nhanh hơn” hay “tách biến chậm hơn” nếu chưa đo allocation, peak heap, GC pauses và thời gian chạy trên workload thực. Nếu tối ưu, dùng profiler/benchmark và bảo toàn tính đúng đắn.

## 17. Những lỗi phổ biến khi thực hành

**Lỗi 1 — Đặt tất cả biến là `tmp`, `data`, `list1`.**  
Không có ý nghĩa; tên phải giải thích trạng thái dữ liệu hoặc mục đích nghiệp vụ.

**Lỗi 2 — Tưởng `var` làm biến đổi kiểu khi gán.**  
Sai. Inferred type là static type của local variable.

**Lỗi 3 — Dùng `var` với initializer `null`.**  
Không có inferred type phù hợp; compilation thất bại.

**Lỗi 4 — Dùng `var list = new ArrayList<>()` rồi nghĩ element type chắc chắn là `Order`.**  
Không. Cần type argument tường minh hoặc target type.

**Lỗi 5 — Dùng lại một Stream sau terminal operation.**  
Không hợp lệ. Dùng List, tạo Stream mới hoặc thiết kế aggregator.

**Lỗi 6 — Materialize mọi bước mà không quan tâm heap.**  
Có thể làm tăng memory/GC pressure; tách logic không bắt buộc tách tất cả collections.

**Lỗi 7 — Đổi thứ tự `filter` và `map` mà chưa kiểm tra.**  
Có thể làm thay đổi validation và exception behavior.

**Lỗi 8 — Lạm dụng `peek` cho side effects.**  
Không nên đưa business mutations vào một điểm không có contract phù hợp về số lần chạy.

**Lỗi 9 — Chỉ test tổng tiền, không test thứ tự.**  
Sort/tie-break có thể sai dù total đúng.

**Lỗi 10 — Dùng `LocalDate.now()` trong demo yêu cầu output cố định.**  
Output phụ thuộc ngày chạy; dùng ngày cố định hoặc inject `Clock` cho test.

**Lỗi 11 — Dùng `double` cho tiền vì ngắn hơn.**  
Có thể mất precision. Giữ domain type phù hợp.

**Lỗi 12 — Giữ cùng một biến `data` rồi liên tục đổi nội dung.**  
Dễ nhầm raw/parsed/filtered. Tên riêng ở các ranh giới giúp review hơn.

**Lỗi 13 — Nghĩ `Collectors.toList()` luôn trả ArrayList mutable.**  
API không cam kết. Chọn `toCollection(ArrayList::new)` nếu đó là yêu cầu.

**Lỗi 14 — Dùng `Stream.toList()` rồi compile `--release 10`.**  
Không được: `Stream.toList()` mới xuất hiện Java 16.

**Lỗi 15 — Biến mọi biểu thức một dòng thành một local variable.**  
Thường làm rối thêm và tăng scope; chỉ tách những kết quả đáng đặt tên.

**Lỗi 16 — So sánh hai phiên bản với dữ liệu đầu vào khác nhau.**  
Không chứng minh được semantic equivalence. Giữ cùng input, environment và contracts.

**Lỗi 17 — Refactor pipeline có network/DB calls mà không kiểm tra số lượt gọi.**  
Side effects, retries và transaction boundaries có thể đổi. Phải kiểm thử riêng.

## 18. Checklist code review

1. Có mô tả input/output và business contract không?
2. Các biến có tên như `parsedOrders`, `paidInMonth`, `rankedOrders` thay vì `list1`, `list2`?
3. Mỗi local variable có mang thông tin mới không?
4. Có dùng `var` ở initializer rõ, và explicit type ở nơi cần?
5. Có giữ nguyên type/generic contract sau khi đổi sang `var`?
6. Có giữ logic validation của dữ liệu sai?
7. Có giữ đúng date boundaries và timezone semantics?
8. Có giữ sort order và tie-break?
9. Có bảo toàn precision/currency/units?
10. Có tránh reuse Stream sau terminal operation?
11. Có kiểm tra khi đổi lazy pipeline thành nhiều Lists?
12. Có giữ side-effect count, exceptions và transactions theo contract?
13. Có test input rỗng và dữ liệu lỗi?
14. Có test hai phần tử cùng sort key?
15. Có test kết quả trước–sau tương đương?
16. Có kiểm tra peak memory nếu tập dữ liệu lớn?
17. Có loại bỏ local variables quá vụn khi chúng không giúp đọc?
18. Có dùng helper method khi cần tái sử dụng/test riêng?
19. Có giữ scope các biến ngắn và gần nơi sử dụng?
20. Có code compile/run trên JDK mục tiêu và stdout đúng?

## 19. Câu hỏi tự kiểm tra

**1. Mục tiêu của việc tách chuỗi xử lý là gì?**  
Làm rõ các bước có ý nghĩa, dễ debug/review/test mà không làm đổi hợp đồng nghiệp vụ.

**2. Tại sao `var` phù hợp với các locals trung gian?**  
Vì compiler suy ra kiểu từ initializer, giảm sự lặp kiểu generic dài trong source mà Java vẫn static typed.

**3. `var` có là dynamic typing không?**  
Không. Java compiler xác định static type khi khai báo.

**4. Tên `parsedOrders` có ý nghĩa gì?**  
Dữ liệu đã chuyển từ raw lines thành domain objects và được kiểm tra cấu trúc.

**5. Tên `paidInMonth` nói gì?**  
Các orders đã qua status PAID và date range của tháng được chọn.

**6. Tại sao dùng `endExclusive`?**  
Để biểu đạt rõ ranh giới nửa mở `[start, end)` và tránh nhầm ngày cuối kỳ.

**7. Comparator trong ví dụ dùng hai tiêu chí nào?**  
Số tiền giảm dần, sau đó ID tăng dần.

**8. Tổng tiền kỳ vọng là bao nhiêu?**  
625000 VND cho bốn đơn thỏa điều kiện.

**9. Vì sao cần BigDecimal?**  
Để dùng số học thập phân phù hợp với tiền, tránh sai số không cần thiết của binary floating point.

**10. Có được gọi hai terminal operations trên cùng một Stream không?**  
Không. Stream chỉ được dùng một lần.

**11. Cách nào tách logic mà không tạo nhiều Lists?**  
Đặt tên cho predicate/comparator/helper methods và giữ một Stream pipeline.

**12. Vì sao materialize sớm có thể đổi behavior?**  
Nó đổi thời điểm thực thi lazy operations, exception/side effects và có thể bỏ short-circuiting.

**13. `Stream.toList()` có thuộc Java 10 không?**  
Không; API được thêm ở Java 16. Dùng collector phù hợp nếu cần tương thích Java 10.

**14. `final var` có biến List mutable thành immutable không?**  
Không; nó chỉ cấm gán lại local variable, không tự đóng băng object.

**15. Một dataset có output đúng đã chứng minh mọi input tương đương chưa?**  
Chưa. Cần edge-case tests, kiểm tra side effects và hiệu năng khi thích hợp.

## 20. Tổng kết

- Tách một chuỗi xử lý phức tạp thành các biến cục bộ **giúp nhìn rõ trạng thái dữ liệu tại từng ranh giới**.
- `var` từ **Java 10/JEP 286** giúp viết local declarations ngắn nhưng vẫn **có kiểu tĩnh**.
- Tên tốt là `parsedOrders`, `paidInMonth`, `rankedOrders`, `totalPaidVnd`; tên mơ hồ làm mất tác dụng refactor.
- **Đừng tự đổi thứ tự xử lý, validation, sort hay rounding** khi mục tiêu chỉ là refactor.
- Stream là lazy và single-use; List là dữ liệu đã được materialize có thể duyệt lại. Chia pipeline thành nhiều List có thể tăng allocation/heap.
- Có thể giữ một pipeline duy nhất và tách **named predicates/comparators/helpers** để cân bằng readability và memory.
- Khi type/interface quan trọng, **khai báo kiểu tường minh** vẫn cần thiết; `var` không phải lựa chọn bắt buộc.
- Với Java 10 compatibility, dùng các API phù hợp như `Collectors.toList()`, không dùng `Stream.toList()` được thêm sau này.
- **Kết quả của refactor phải được kiểm chứng** bằng test, bao gồm count/total/order, dữ liệu lỗi và behavior liên quan side effects.
- Tối ưu hiệu năng bằng số đo từ workload thực, không chỉ bằng số dòng code.

**Tài liệu tham khảo chính thức, hiện vẫn áp dụng:**
- [OpenJDK — JEP 286: Local-Variable Type Inference](https://openjdk.org/jeps/286).
- [OpenJDK Project Amber — Local Variable Type Inference Style Guidelines](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-style-guide.md).
- [OpenJDK Project Amber — Local Variable Type Inference FAQ](https://github.com/openjdk/amber-docs/blob/master/site/guides/lvti-faq.md).
- [Dev.java — Using the Var Type Identifier](https://dev.java/learn/language-basics/using-var/).
- [Oracle Java SE 17 — Local Variable Type Inference](https://docs.oracle.com/en/java/javase/17/language/local-variable-type-inference.html).
- [Oracle Java SE 25 — Stream API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html).
- [Oracle Java SE 25 — Collectors API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html).
- [Oracle Java SE 25 — BigDecimal API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).
