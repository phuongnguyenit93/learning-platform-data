# Tác dụng phụ và phụ thuộc vào trạng thái bên ngoài trong lập trình hàm Java

Trong lập trình theo phong cách hàm, một nguyên tắc quan trọng là **tách phép tính khỏi tác dụng phụ** và làm rõ mọi dữ liệu mà phép tính phụ thuộc vào. Hai vấn đề liên quan nhưng không đồng nhất là:

- **Tác dụng phụ (side effect):** khi thực hiện một thao tác, chương trình còn tạo thay đổi hoặc tương tác có thể quan sát được bên ngoài giá trị trả về.
- **Phụ thuộc vào trạng thái bên ngoài (external-state dependency):** kết quả hoặc hành vi của thao tác phụ thuộc vào dữ liệu mà lời gọi không nhận trực tiếp qua các tham số, chẳng hạn biến toàn cục có thể thay đổi, thời gian hiện tại, môi trường, một đối tượng được capture hoặc dữ liệu từ hệ thống ngoài.

Java hỗ trợ lambda, method reference, functional interface và Stream API để viết mã theo phong cách hàm, nhưng **không tự loại bỏ tác dụng phụ hay sự phụ thuộc ngầm**. Hiểu hai khái niệm này giúp viết hàm dễ dự đoán, kiểm thử và xử lý đồng thời an toàn hơn.

## 1. Thế nào là tác dụng phụ?

Xét phương thức:

~~~java
static int doubleOf(int value) {
    return value * 2;
}
~~~

Với đầu vào 5, phương thức tính 10 và không cần thay đổi dữ liệu bên ngoài. Ngược lại:

~~~java
static int calls = 0;

static int doubleAndCount(int value) {
    calls++;
    return value * 2;
}
~~~

Hai lời gọi doubleAndCount(5) đều trả về 10 nhưng đồng thời sửa biến dùng chung calls. **Thay đổi calls** là tác dụng phụ; việc chỉ nhìn giá trị trả về không cho biết đầy đủ những gì đã xảy ra.

Các tác dụng phụ thường gặp:

| Thao tác | Tác dụng phụ có thể quan sát |
| --- | --- |
| Gán/sửa biến static hoặc field của đối tượng chia sẻ | Trạng thái về sau thay đổi |
| Thêm/xóa phần tử trong List hoặc Map được chia sẻ | Dữ liệu mà nơi khác đang giữ thay đổi |
| System.out.println, ghi tệp, ghi log, ghi database | Tạo đầu ra hoặc thay đổi hệ thống ngoài |
| Gửi HTTP request, email hoặc message | Tương tác với dịch vụ, có thể sinh hành động bên ngoài |
| Tăng bộ đếm, cập nhật cache dùng chung | Làm thay đổi trạng thái có thể ảnh hưởng lần gọi sau |

**Không phải mọi phép gán đều là tác dụng phụ đáng lo.** Việc tạo và sửa một biến cục bộ hoặc một đối tượng mới mà tham chiếu chưa thoát ra ngoài có thể chỉ là chi tiết triển khai nội bộ:

~~~java
static int sumPositive(int[] numbers) {
    int sum = 0;
    for (int n : numbers) {
        if (n > 0) {
            sum += n;
        }
    }
    return sum;
}
~~~

Nếu mảng đầu vào không bị phương thức sửa và không có tương tác ngầm nào khác, phép gán sum += n chỉ cập nhật trạng thái cục bộ không lộ ra ngoài. Một hàm không cần tránh mọi biến cục bộ để có hành vi thuần; điều quan trọng là **không tạo thay đổi có thể quan sát ngoài kết quả**.

## 2. Phụ thuộc vào trạng thái bên ngoài khác tác dụng phụ ra sao?

Ví dụ:

~~~java
static int taxPercent = 10;

static int totalWithTax(int price) {
    return price + price * taxPercent / 100;
}
~~~

totalWithTax(100) có thể trả về 110 hoặc 120 nếu nơi khác đổi taxPercent từ 10 thành 20. Phương thức **đọc** trạng thái toàn cục, dù bản thân nó không sửa biến đó. Vì vậy, **hàm có thể phụ thuộc vào trạng thái bên ngoài mà không tự gây tác dụng phụ**.

Chiều ngược lại cũng tồn tại:

~~~java
static int printDouble(int number) {
    int result = number * 2;
    System.out.println(result);
    return result;
}
~~~

Giá trị trả về có thể luôn bằng number * 2 mà hàm vẫn gây tác dụng phụ qua việc in ra console. Một phương thức vừa có thể đọc trạng thái ngoài vừa tạo tác dụng phụ, chẳng hạn đọc giá trị bộ đếm dùng chung rồi tăng chính bộ đếm đó.

| Câu hỏi | Tác dụng phụ | Phụ thuộc trạng thái bên ngoài |
| --- | --- | --- |
| Ta quan sát điều gì? | Thao tác gây thay đổi/tương tác ngoài kết quả trả về | Kết quả/hành vi bị chi phối bởi dữ liệu không hiện rõ ở đối số |
| Ví dụ đơn giản | System.out.println("Hi") | Đọc biến static có thể thay đổi |
| Vì sao khó kiểm thử? | Cần theo dõi và cô lập tương tác hoặc trạng thái bị sửa | Cần thiết lập trạng thái ngầm trước mỗi lần gọi |
| Cách cải thiện | Đưa thao tác I/O hoặc cập nhật trạng thái ra ranh giới rõ ràng | Truyền dữ liệu hoặc dependency qua tham số |

Một số nguồn phụ thuộc ngầm thường gặp trong Java:

- Biến static mutable, singleton có trạng thái, field mutable của đối tượng bên ngoài.
- Clock.systemUTC().instant(), System.currentTimeMillis(), LocalDate.now() khi không cấp Clock; giá trị thay đổi theo thời điểm gọi.
- Random dùng nguồn ngẫu nhiên có trạng thái; mỗi lần lấy số có thể cho kết quả mới.
- System.getenv, System.getProperty, cấu hình đang đổi, database hoặc tệp trên đĩa.
- ThreadLocal, trạng thái giao dịch, bảo mật hoặc context gắn với luồng xử lý.
- Đối tượng mutable mà một lambda capture, dù tham chiếu cục bộ được khai báo final.

Lưu ý: **Tham số chỉ có kiểu tham chiếu cũng có thể mang trạng thái thay đổi bên trong**. Truyền List vào phương thức là truyền phụ thuộc một cách tường minh hơn, nhưng nếu người khác sửa List đồng thời, hành vi vẫn khó dự đoán. Tính thuần đòi hỏi cả cách sử dụng đối tượng đầu vào.

## 3. Hàm thuần, tính xác định và khả năng thay thế biểu thức

Một hàm **thuần** (pure function) theo cách hiểu thực dụng trong Java có hai tính chất:

1. Với cùng những đầu vào ổn định, phép tính trả cùng kết quả.
2. Lời gọi không gây tác dụng phụ có thể quan sát bên ngoài giá trị trả về.

Khi biểu thức là thuần, ta có thể thay lời gọi bằng kết quả tương ứng mà không làm đổi hành vi quan sát được của chương trình. Đây là ý tưởng **referential transparency** (tính trong suốt tham chiếu).

~~~java
static int discount(int amount, int percent) {
    return amount * percent / 100;
}
~~~

Khi amount = 200 và percent = 10, kết quả luôn là 20 (bỏ qua lỗi tràn số với đầu vào quá lớn; ví dụ nhằm minh họa đầu vào nhỏ). Để thay đổi mức giảm, truyền percent mới. Phương thức không phải đọc một biến percent ẩn.

So sánh:

~~~java
static int activeDiscountPercent = 10;

static int discountFromGlobal(int amount) {
    return amount * activeDiscountPercent / 100;
}
~~~

Lời gọi discountFromGlobal(200) che giấu một đầu vào quan trọng là activeDiscountPercent. Việc đổi giá trị global giữa hai lần gọi khiến kết quả khác nhau.

**Một kết quả giống nhau không đủ chứng minh hàm thuần.** Hai lần gọi System.out.println("hello") đều trả về void nhưng vẫn in hai lần. Tương tự, hàm đọc đồng hồ có thể tình cờ trả cùng mili giây trong hai lời gọi gần nhau; nó vẫn phụ thuộc thời gian.

Trong Java, nói “hàm thuần” là **cam kết về hành vi và trạng thái liên quan**, không phải một modifier hay annotation chuẩn mà compiler xác minh. Các thư viện Java phổ biến cho phép cả callback thuần lẫn callback có tác dụng phụ.

## 4. Lambda và capture: effectively final không có nghĩa là bất biến

Biến cục bộ được lambda sử dụng phải là final hoặc **effectively final**: sau khi gán, không được gán lại biến đó.

~~~java
int threshold = 50;
java.util.function.IntPredicate eligible = score -> score >= threshold;
~~~

Đoạn trên hợp lệ. Gán lại threshold sau khi tạo lambda sẽ khiến chương trình không biên dịch.

Tuy nhiên, ràng buộc này chỉ bảo vệ **biến tham chiếu cục bộ**, không làm đối tượng mà biến tham chiếu tới trở nên bất biến:

~~~java
java.util.List<String> audit = new java.util.ArrayList<>();
java.util.function.Consumer<String> recorder = message -> audit.add(message);

recorder.accept("started");
~~~

audit không bị gán lại nên thỏa điều kiện capture, nhưng recorder vẫn thay đổi List. Đây là tác dụng phụ đối với đối tượng có thể được quan sát bên ngoài lambda.

Tương tự, lambda có thể đọc mutable field:

~~~java
class Pricing {
    int surcharge = 5;

    java.util.function.IntUnaryOperator calculator =
        amount -> amount + surcharge;
}
~~~

Kết quả calculator.applyAsInt(100) có thể thay đổi nếu surcharge thay đổi. **Lambda là cú pháp truyền hành vi; không tự bảo đảm hành vi thuần hay thread-safe.**

Một ví dụ còn nguy hiểm hơn khi callback vừa đọc vừa sửa một bộ đếm:

~~~java
int[] counter = {0};
java.util.function.IntSupplier next = () -> ++counter[0];
~~~

Biến counter vẫn effectively final, nhưng phần tử mảng thay đổi: hai lần next.getAsInt() lần lượt trả 1, 2. Dùng mảng hoặc AtomicInteger để lách ràng buộc effectively final không biến logic này thành hàm thuần. AtomicInteger làm thao tác tăng/đọc cụ thể an toàn về tính nguyên tử, nhưng không tự bảo đảm toàn bộ thuật toán an toàn hay có tính xác định.

## 5. Hậu quả trong Stream API: stateless và non-interference

Stream API khuyến nghị behavioral parameters của pipeline, chẳng hạn lambda trong filter, map, sorted và reduce, **không can thiệp nguồn** (non-interfering) và trong đa số trường hợp nên **không mang trạng thái** (stateless).

- **Non-interfering:** callback không sửa nguồn dữ liệu đang được pipeline duyệt, trừ các ngoại lệ cụ thể được tài liệu API cho phép.
- **Stateless:** kết quả của callback cho một phần tử không phụ thuộc vào trạng thái có thể bị thay đổi trong quá trình pipeline chạy.

### 5.1. Tránh sửa nguồn khi đang duyệt

~~~java
java.util.List<Integer> values =
    new java.util.ArrayList<>(java.util.List.of(1, 2, 3));

// Ví dụ sai: không chạy trong chương trình minh họa hoàn chỉnh.
values.stream()
    .filter(n -> {
        values.add(n + 10);  // Can thiệp nguồn đang duyệt.
        return n % 2 != 0;
    })
    .toList();
~~~

Thao tác này vi phạm yêu cầu non-interference và có thể gây lỗi, hành vi không đáng tin hoặc kết quả ngoài dự kiến tùy nguồn và cách thực thi. Không nên phụ thuộc vào việc nó luôn ném ConcurrentModificationException.

Cách đúng nếu cần kết quả mới:

~~~java
java.util.List<Integer> extended = values.stream()
    .map(n -> n + 10)
    .toList();
~~~

Map tạo các giá trị kết quả mà không sửa values. Nếu nghiệp vụ cần thay đổi collection gốc, hãy thực hiện cập nhật ở bước riêng, có kiểm soát.

### 5.2. Tránh tích lũy bằng trạng thái chung

~~~java
java.util.List<Integer> numbers = java.util.List.of(1, 2, 3, 4);
java.util.List<Integer> shared = new java.util.ArrayList<>();

// Không phù hợp với parallelStream:
numbers.parallelStream().forEach(shared::add);
~~~

ArrayList không an toàn khi nhiều luồng thêm phần tử đồng thời; số lượng/phần tử có thể sai và cấu trúc dữ liệu có thể bị hỏng. Với stream tuần tự, thêm vào danh sách ngoài vẫn có tác dụng phụ và giảm tính rõ ràng.

Nếu mục tiêu là tạo danh sách:

~~~java
java.util.List<Integer> doubled = numbers.parallelStream()
    .map(n -> n * 2)
    .toList();
~~~

Nếu mục tiêu là tổng:

~~~java
int sum = numbers.parallelStream()
    .mapToInt(Integer::intValue)
    .sum();
~~~

Ở các ví dụ này, kết quả được Stream terminal operation tạo ra mà không cần callback thay đổi một biến dùng chung.

### 5.3. Không nhầm forEach và peek với phép biến đổi thuần

forEach thường dành cho tác dụng phụ ở **ranh giới xử lý cuối**, như in kết quả đã tính. Trong parallel stream, forEach không bảo đảm thực hiện theo encounter order. forEachOrdered dùng khi cần giữ thứ tự theo hợp đồng, nhưng vẫn không biến callback thành hàm thuần.

peek phù hợp chủ yếu để quan sát khi debug; vì Stream lazy và có thể tối ưu, đừng đặt nghiệp vụ quan trọng như ghi audit, gửi request hay cập nhật database trong peek hoặc filter/map rồi giả định callback chắc chắn được chạy đúng một lần trên mọi phần tử.

Ví dụ có thể gây hiểu lầm:

~~~java
long count = java.util.stream.Stream.of("A", "B")
    .peek(System.out::println)
    .count();
~~~

Không được xây nghiệp vụ dựa trên việc hai chữ cái chắc chắn được in. Trong trường hợp nguồn biết trước kích thước, count có thể tính kết quả mà không cần duyệt từng phần tử hoặc gọi peek.

### 5.4. Side effect càng khó kiểm soát khi chạy song song

Một pipeline phụ thuộc bộ đếm dùng chung hoặc thứ tự callback sẽ khó bảo đảm tính xác định khi chuyển từ stream() sang parallelStream(). Kể cả sử dụng synchronized hoặc AtomicInteger, kết quả có thể vẫn phụ thuộc thứ tự chạy nếu phép tính quyết định khác nhau theo vị trí tăng bộ đếm.

Với reduce song song, phép toán kết hợp cần có **tính kết hợp (associative)** và giá trị identity phù hợp. Chẳng hạn phép cộng số nguyên thường dùng tốt; phép trừ không có tính kết hợp nên không thể tùy tiện dùng như phép reduce kết hợp song song. Trong tính toán số thực, sai khác thứ tự cộng còn có thể làm thay đổi kết quả làm tròn; “không có side effect” chưa đủ để bảo đảm mọi kết quả bit-for-bit giống nhau ở mọi thứ tự.

## 6. Chuyển phụ thuộc ngầm thành đầu vào tường minh

Cải thiện một hàm thường bắt đầu bằng việc liệt kê **những gì thật sự quyết định kết quả**.

Ví dụ phụ thuộc đồng hồ và thuế ẩn:

~~~java
static int currentTaxPercent = 10;

static String quoteBad(int basePrice) {
    int total = basePrice + basePrice * currentTaxPercent / 100;
    return java.time.Instant.now() + ": " + total;
}
~~~

Kết quả phụ thuộc cả currentTaxPercent và thời gian thực, dù chỉ nhận basePrice. Phiên bản làm rõ toàn bộ dữ liệu:

~~~java
static String quoteText(
    int basePrice,
    int taxPercent,
    java.time.Instant issuedAt
) {
    int total = basePrice + basePrice * taxPercent / 100;
    return issuedAt + ": " + total;
}
~~~

Cùng bộ ba đối số ổn định sẽ tạo cùng chuỗi. Nơi gọi lấy thời gian và mức thuế từ hệ thống, sau đó truyền vào hàm. Cách tổ chức này cho phép kiểm thử bằng Instant cố định, không cần thay đổi đồng hồ toàn cục.

Nếu một lớp thực sự cần đọc đồng hồ tại thời điểm chạy, **dependency injection** qua Clock là kỹ thuật hữu ích:

~~~java
class TimestampSource {
    private final java.time.Clock clock;

    TimestampSource(java.time.Clock clock) {
        this.clock = clock;
    }

    java.time.Instant now() {
        return clock.instant();
    }
}
~~~

Trong ứng dụng thật có thể cấp Clock.systemUTC(); trong test cấp Clock.fixed(instant, zone). Cần phân biệt: **truyền Clock giúp phụ thuộc rõ ràng và dễ mô phỏng, nhưng now() vẫn phụ thuộc trạng thái của Clock** nếu Clock chạy theo thời gian thực; bản thân nó chưa phải một hàm thuần. Truyền **Instant đã được chụp** vào phép tính mới là cách làm cho phép tính đó độc lập với thời gian biến đổi.

Tương tự, thay vì gọi nguồn Random bên trong hàm tính tiền hoặc sinh mã, có thể truyền giá trị đã sinh vào phần xử lý thuần. Khi cần giả lập một chuỗi ngẫu nhiên cho test, truyền RandomGenerator đã seed là một cách kiểm soát dependency, nhưng mỗi lần gọi nextInt vẫn thay đổi trạng thái của generator.

## 7. Tổ chức “functional core, imperative shell”

Một mô hình áp dụng thực tế trong Java:

1. **Imperative shell (lớp tương tác):** đọc request, đồng hồ, cấu hình, database; ghi log, gửi response, cập nhật dữ liệu.
2. **Functional core (lõi tính toán):** nhận giá trị tường minh, tính toán và trả giá trị mới; không truy cập I/O hoặc sửa trạng thái chia sẻ.

Ví dụ nghiệp vụ tính báo giá:

- Shell lấy các dòng hàng, thời điểm lập báo giá và mức giảm giá từ request/cấu hình.
- Core tính tổng tiền và tạo kết quả kiểu dữ liệu rõ ràng.
- Shell lưu hoặc in báo giá sau khi core đã hoàn tất.

Điều này giúp unit test chạy nhanh và lặp lại được, vì phần tính tiền không cần database, clock thật hoặc server. Nó cũng giúp người đọc dễ thấy vị trí nào có thể tạo tác dụng phụ. Tác dụng phụ không phải “điều cấm”: ứng dụng thực tế **phải** đọc/ghi I/O. Mục tiêu là đặt chúng đúng chỗ và điều phối có chủ đích.

## 8. Chương trình Java 17+ hoàn chỉnh

Ví dụ dưới đây chủ động để phần tính toán không sửa dữ liệu bên ngoài. Tương tác in ra console và ghi vào audit nằm tại main; thời điểm phát hành được lấy từ Clock rồi truyền vào hàm dựng thông điệp.

Tạo tệp **FunctionalEffectsDemo.java**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

public class FunctionalEffectsDemo {
    record Line(String item, int unitPrice, int quantity) {}
    record Quote(String code, int subtotal, int discount, int total) {}

    // Tính trên các đầu vào tường minh, không sửa danh sách lines.
    static Quote calculate(
        String code,
        List<Line> lines,
        int discountPercent
    ) {
        if (discountPercent < 0 || discountPercent > 100) {
            throw new IllegalArgumentException("Invalid discount");
        }

        int subtotal = lines.stream()
            .mapToInt(line ->
                Math.multiplyExact(line.unitPrice(), line.quantity())
            )
            .reduce(0, Math::addExact);
        int discount = Math.multiplyExact(
            subtotal, discountPercent
        ) / 100;
        return new Quote(
            code,
            subtotal,
            discount,
            Math.subtractExact(subtotal, discount)
        );
    }

    // Chuỗi chỉ phụ thuộc Quote và thời điểm đã truyền vào.
    static String receipt(Quote quote, Instant issuedAt) {
        return quote.code() + "@" + issuedAt
            + " total=" + quote.total();
    }

    public static void main(String[] args) {
        List<Line> lines = List.of(
            new Line("Book", 100, 2),
            new Line("Pen", 20, 3)
        );
        Quote first = calculate("Q-001", lines, 10);
        Quote second = calculate("Q-001", lines, 10);

        System.out.println(first);
        System.out.println(first.equals(second));

        // Ở ranh giới ứng dụng, quyết định thời điểm.
        Clock fixed = Clock.fixed(
            Instant.parse("2026-01-02T03:04:05Z"),
            ZoneOffset.UTC
        );
        Instant issuedAt = fixed.instant();
        String message = receipt(first, issuedAt);
        System.out.println(message);

        // Ghi audit là tác dụng phụ có chủ đích.
        List<String> audit = new ArrayList<>();
        audit.add("created:" + first.code());
        System.out.println(audit);

        // Pipeline biến đổi dữ liệu mà không đụng audit/lines.
        List<String> items = lines.stream()
            .filter(line -> line.quantity() > 1)
            .map(Line::item)
            .toList();
        System.out.println(items);
    }
}
~~~

Dùng JDK 17 trở lên, chạy trong thư mục chứa tệp:

~~~bash
javac FunctionalEffectsDemo.java
java FunctionalEffectsDemo
~~~

Stdout:

~~~text
Quote[code=Q-001, subtotal=260, discount=26, total=234]
true
Q-001@2026-01-02T03:04:05Z total=234
[created:Q-001]
[Book, Pen]
~~~

Phân tích cụ thể:

- calculate dùng các Line đầu vào và discountPercent = 10; subtotal = 100 × 2 + 20 × 3 = 260, discount = 26, total = 234. Phương thức không đọc biến global và không thay đổi lines.
- first.equals(second) trả true vì record Quote có equals dựa trên các thành phần. Hai lời gọi calculate với cùng đầu vào bất biến có kết quả tương đương.
- Clock.fixed trả thời gian cố định. Shell lấy Instant này, còn receipt chỉ ghép dữ liệu đã biết. Nếu muốn xuất báo giá ở thời gian thật, shell có thể dùng Clock.systemUTC() mà không cần thay đổi receipt.
- audit.add(...) là tác dụng phụ, được đặt rõ trong main để người đọc biết thời điểm xảy ra.
- filter/map/toList tạo danh sách item mới, không thêm phần tử vào audit hoặc lines. Stream.toList() tạo List không thể thêm/xóa/thay phần tử.

Ví dụ dùng List.of chứa các record chỉ mang String và int, nên các đầu vào ở đây không bị người gọi âm thầm sửa. Trong hệ thống thực tế, nếu record chứa List hoặc đối tượng mutable, record **không tự tạo bất biến sâu**: cần sao chép phòng vệ, xác định ownership hoặc dùng kiểu bất biến phù hợp.

**Về lỗi và giới hạn dữ liệu:** calculate kiểm tra discountPercent và dùng Math.multiplyExact/addExact/subtractExact để phát hiện tràn số int, các phép có thể ném exception đối với dữ liệu bất hợp lệ. Chương trình minh họa dùng các số nhỏ hợp lệ. Nghiệp vụ tiền tệ thật thường cần BigDecimal hoặc đơn vị tiền nhỏ nhất cùng quy tắc làm tròn rõ ràng; ví dụ ở đây tập trung vào quản lý tác dụng phụ.

## 9. Kiểm thử hiệu quả khi trạng thái và tác dụng phụ rõ ràng

Khi một hàm không phụ thuộc ngầm vào clock, mutable singleton, database hoặc thứ tự callback, unit test có thể truyền chính xác các đầu vào và so sánh kết quả. Ví dụ cho chương trình trên:

~~~java
// Minh họa assertion trong phương thức test;
// không phải chương trình độc lập.
var lines = java.util.List.of(
    new FunctionalEffectsDemo.Line("Notebook", 50, 2)
);
var result = FunctionalEffectsDemo.calculate("Q-T", lines, 10);
assert result.total() == 90;
~~~

Lệnh assert của Java có thể bị tắt mặc định; khi dùng kiểm thử thực tế, ưu tiên assertion của JUnit hoặc bật -ea. Ví dụ này là phép kiểm tra toán học đơn giản, không yêu cầu mock database/đồng hồ.

Kiểm thử phần I/O và tác dụng phụ thì khác: xác minh một repository được gọi đúng lúc, một sự kiện được gửi một lần hay audit được ghi đúng dữ liệu. Đưa những tương tác này vào dependency qua interface sẽ giúp dùng test double hoặc fake. Đặt phép tính trong core cho phép kiểm tra quy tắc nghiệp vụ riêng mà không cần giả lập mọi dịch vụ.

Với hành vi phụ thuộc thời gian, thay LocalDate.now() trực tiếp bằng cách nhận Clock hoặc Instant tường minh. Với random, có thể truyền giá trị random đã sinh hoặc cung cấp nguồn xác định cho test. Với trạng thái toàn cục, giảm phạm vi sửa đổi và chuyển thành tham số hoặc đối tượng dữ liệu không đổi khi có thể.

## 10. Tác dụng phụ có thể xuất hiện ở các điểm khó nhận ra

### 10.1. Thay đổi đầu vào

~~~java
static int[] sortInPlace(int[] data) {
    java.util.Arrays.sort(data);
    return data;
}
~~~

sortInPlace sửa ngay mảng mà caller truyền vào. Việc trả lại chính mảng đó không làm cho phương thức thuần. Nếu cần hành vi ít tác dụng phụ hơn, tạo bản sao trước khi sắp xếp:

~~~java
static int[] sortedCopy(int[] data) {
    int[] copy = data.clone();
    java.util.Arrays.sort(copy);
    return copy;
}
~~~

Phương thức sortedCopy không sửa mảng đầu vào. Tuy nhiên, kết quả là một mảng mutable mới; người gọi vẫn có thể thay đổi mảng kết quả sau này.

### 10.2. Cache hoặc memoization

Một hàm có thể ghi cache nội bộ để cải thiện tốc độ. Nếu cache hoàn toàn bị che giấu và không thay đổi kết quả quan sát được, người dùng đôi khi vẫn xem API đó như hành vi thuần về mặt chức năng. Tuy vậy, cache vẫn thêm trạng thái cần quản lý, có thể ảnh hưởng bộ nhớ, concurrency, thứ tự thực thi và lỗi. Không đồng nhất “cùng kết quả” với “không có bất kỳ trạng thái nội bộ nào”.

### 10.3. Ngoại lệ và tính toàn phần

Phương thức ném exception không nhất thiết sửa trạng thái chia sẻ, nhưng có thể làm gián đoạn luồng điều khiển và buộc caller xử lý lỗi. Trong nhiều mô hình hiệu ứng, ném exception được xem là hiệu ứng quan sát được; cách định nghĩa “thuần” trong lập trình ứng dụng có thể phân biệt riêng lỗi tính toán với I/O hay mutation.

Để thiết kế có thể dự đoán, nêu rõ điều kiện đầu vào và lỗi; có thể biểu diễn lỗi dự kiến dưới dạng giá trị kết quả khi phù hợp. Không nên âm thầm bắt mọi exception rồi trả giá trị mặc định, vì có thể che giấu lỗi nghiệp vụ.

### 10.4. Sửa field bên trong record hoặc collection bất biến nông

~~~java
record Bag(java.util.List<String> items) {}

java.util.List<String> mutable = new java.util.ArrayList<>();
Bag bag = new Bag(mutable);
mutable.add("A");
~~~

bag.items() bây giờ nhìn thấy "A" dù tham chiếu items bên trong record là final. Có thể dùng List.copyOf trong constructor nếu cần bảo vệ cấu trúc danh sách, nhưng phần tử mutable bên trong vẫn cần cân nhắc thêm.

## 11. Khi nào dùng side effect và cách đặt ranh giới?

Không cần biến mọi đoạn Java thành Stream hay lambda để theo đuổi tính thuần. Trong ứng dụng thực, thao tác ghi database, gửi event, xuất báo cáo và logging đều cần thiết. Điều quan trọng là **quyết định rõ tác dụng phụ sẽ xuất hiện ở đâu**:

- **Tầng xử lý input/output:** đọc dữ liệu, xác thực, gọi dịch vụ, commit giao dịch, phát sự kiện hoặc in kết quả.
- **Tầng quy tắc nghiệp vụ:** nhận dữ liệu đã được thu thập, áp dụng điều kiện và tính kết quả, hạn chế đọc/sửa trạng thái ngoài.
- **Hợp đồng dữ liệu:** thể hiện đầu vào, đầu ra, khả năng thất bại và phạm vi mutable; tránh giữ ngầm dependency quan trọng trong static field.
- **Tính đồng thời:** giữ các hàm chuyển đổi trong stream càng stateless càng tốt; để các thao tác cập nhật trạng thái vào cơ chế chuyên dụng với ràng buộc đồng bộ rõ ràng.
- **Kiểm thử:** dùng input cố định và so sánh output cho core; test riêng tương tác có tác dụng phụ qua dependency có thể thay thế.

Ví dụ, sau khi tính Quote, thực hiện repository.save(quote) có tác dụng phụ nhưng hoàn toàn hợp lý. Nếu đặt repository.save(...) ngay trong map() của Stream đang biến đổi từng dòng hàng, việc thử lại, chạy song song hoặc tối ưu pipeline sẽ làm tác dụng phụ khó kiểm soát. Hãy tính dữ liệu trước, sau đó lưu theo chính sách giao dịch, retry và idempotency của hệ thống.

## 12. Những nhầm lẫn phổ biến và câu hỏi tự kiểm tra

**Nhầm lẫn 1: “Không ghi ra ngoài thì hàm thuần”.** Một hàm đọc số thuế từ mutable static field, thời gian hiện tại hay nội dung file vẫn có dependency ngầm; cùng tham số có thể cho kết quả khác.

**Nhầm lẫn 2: “Dùng lambda hoặc Stream thì là lập trình hàm thuần”.** Lambda hoàn toàn có thể capture ArrayList mutable, sửa field hoặc gọi I/O. Stream không ép callback thuần.

**Nhầm lẫn 3: “Biến capture effectively final thì thread-safe”.** final/effectively final bảo đảm không gán lại biến cục bộ, không bảo đảm trạng thái của đối tượng được tham chiếu bất biến hoặc đồng bộ.

**Nhầm lẫn 4: “Có AtomicInteger thì parallel stream đã tối ưu và an toàn”.** AtomicInteger hỗ trợ thao tác nguyên tử cụ thể, nhưng callback phụ thuộc trạng thái vẫn có thể sinh logic không xác định, khó đọc và chậm. Dùng collector/reduction phù hợp thường tốt hơn.

**Nhầm lẫn 5: “Record và unmodifiable List luôn bất biến sâu”.** Một record chứa đối tượng mutable và một List không cho sửa cấu trúc nhưng chứa phần tử mutable vẫn có thể bộc lộ trạng thái đổi từ bên ngoài.

**Nhầm lẫn 6: “Tác dụng phụ luôn xấu”.** Tác dụng phụ cần thiết cho tương tác thực. Vấn đề là tác dụng phụ ngầm, không kiểm soát, rải rác giữa các phép tính và khó kiểm thử.

Tự kiểm tra:

1. Phương thức chỉ đọc biến static mutable, không sửa gì: nó có tác dụng phụ hay phụ thuộc trạng thái ngoài?
2. Vì sao List<String> được capture trong lambda vẫn có thể bị thêm phần tử dù biến tham chiếu là final?
3. Tại sao sửa ArrayList dùng chung trong parallelStream().forEach(...) không an toàn?
4. Truyền Clock.systemUTC() vào một đối tượng có làm phương thức now() trở thành hàm thuần không? Truyền Instant cố định khác nhau thế nào?
5. Làm cách nào giữ tính toán giá tiền độc lập với việc lấy thời gian, ghi log hoặc lưu database?

Nếu phân biệt được **đầu vào tường minh, trạng thái đọc ngầm và tác dụng phụ quan sát được**, bạn có nền tảng vững để thiết kế các lambda, Stream pipeline và API Java dễ bảo trì, kiểm thử và chạy đồng thời hơn.