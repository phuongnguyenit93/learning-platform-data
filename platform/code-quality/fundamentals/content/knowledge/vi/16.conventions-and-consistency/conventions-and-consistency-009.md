# Đưa quy ước vào ví dụ và tài liệu dễ tra cứu

Một quy ước viết mã chỉ tạo giá trị khi người làm việc với codebase **biết quy ước tồn tại, hiểu lúc nào áp dụng và có thể thực hiện nó đúng cách**. Câu “hãy đặt tên rõ ràng” thường không đủ để hai lập trình viên đưa ra quyết định giống nhau. Ngược lại, một tài liệu ngắn có ví dụ đúng/sai, lý do và đường dẫn đến mã mẫu giúp người mới áp dụng ngay mà không phải đoán ý người review.

Bài học thuộc chương **Quy ước và nhất quán** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu module, các quy ước nên hỗ trợ mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**, chứ không phải chỉ làm mọi tệp giống nhau về hình thức. Chủ đề tập trung vào cách biến quy ước thành **ví dụ thực thi được**, **tài liệu có thể tra cứu tại thời điểm cần dùng**, và **quy trình duy trì nhất quán với mã thực tế**.

## 1. Vì sao “đã thống nhất trong nhóm” vẫn chưa đủ?

Hãy hình dung nhóm đã đồng ý “xử lý lỗi nhất quán”. Khi có yêu cầu mới, ba người có thể thực hiện rất khác:

- Người thứ nhất bắt mọi ngoại lệ rồi trả `null`.
- Người thứ hai ném `IllegalArgumentException` cho cả đầu vào không hợp lệ và sự cố database.
- Người thứ ba trả đối tượng kết quả có trạng thái cụ thể, đồng thời để lỗi I/O lan đến tầng điều phối.

Cả ba đều có thể nghĩ mình đang tuân theo “xử lý lỗi nhất quán”, bởi quy ước chưa trả lời **lỗi nào, ở ranh giới nào và cần giữ thông tin gì**.

Một quy ước hữu ích phải giải quyết ba vấn đề:

1. **Khả năng tìm thấy:** người viết mã biết tìm hướng dẫn ở đâu mà không cần hỏi người quen.
2. **Khả năng hiểu và thực hiện:** ví dụ cho thấy hành vi được kỳ vọng và trường hợp không áp dụng.
3. **Khả năng xác minh:** review hoặc công cụ có thể phát hiện sai lệch quan trọng, và người bảo trì biết cách xử lý ngoại lệ có chủ đích.

Quy ước không chỉ nhằm giảm tranh luận trong code review. Nó còn là **hợp đồng làm việc** giúp người tiếp quản dự đoán cấu trúc, vị trí logic, cách đặt tên và cách xử lý lỗi.

## 2. Những loại quy ước nên được diễn đạt bằng ví dụ

Không phải mọi quy ước có cùng mức ảnh hưởng.

| Loại quy ước | Ví dụ câu hỏi thường gặp | Tác động khi thiếu nhất quán |
| --- | --- | --- |
| **Định dạng (formatting)** | Thụt lề, dấu ngoặc, xuống dòng như thế nào? | Diff nhiễu, review mất thời gian |
| **Đặt tên (naming)** | Tên class, method, hằng số, đơn vị đo và khái niệm miền ra sao? | Khó đọc, dễ hiểu sai ý nghĩa |
| **Cấu trúc (structure)** | Quy tắc nghiệp vụ đặt ở đâu, adapter I/O thuộc tầng nào? | Phụ thuộc vòng, sửa một việc phải chạm nhiều nơi |
| **Hợp đồng dữ liệu** | Xử lý `null`, dữ liệu thiếu, giá trị biên và mutable object thế nào? | Sai hành vi, lỗi trạng thái hoặc trùng lặp kiểm tra |
| **Xử lý lỗi** | Lỗi đầu vào, lỗi nghiệp vụ và lỗi hạ tầng được phân loại thế nào? | Bỏ mất nguyên nhân, retry sai, phản hồi không thống nhất |
| **Kiểm thử** | Test đặt tên ra sao, phải kiểm tra giá trị biên nào, dùng fake lúc nào? | Test khó hiểu, coverage cao nhưng bỏ lọt lỗi |
| **Log và bảo mật** | Ghi gì vào log, bí mật nào không được ghi, quyền kiểm tra ở đâu? | Rò dữ liệu, khó chẩn đoán hoặc thiếu kiểm soát |
| **Tài liệu và quyết định** | Khi đổi quy tắc, cập nhật nơi nào, ghi lý do ở đâu? | Tài liệu cũ mâu thuẫn với code |

Với vấn đề **định dạng**, trình formatter thường là nguồn thực thi tốt nhất. Với **quy tắc nghiệp vụ và ranh giới trách nhiệm**, tài liệu cần ví dụ, lý do và kiểm thử; một formatter không thể quyết định khách VIP được giảm giá trong trường hợp nào.

**Nguyên tắc:** đầu tư tài liệu và cơ chế kiểm tra tương xứng với hậu quả khi làm sai. Không cần viết hàng trang giải thích từng dấu cách, nhưng phải làm rõ các quy tắc dễ gây lỗi dữ liệu, phân quyền hoặc thay đổi nhầm chức năng.

## 3. Một mục quy ước tốt nên có những thành phần nào?

Ví dụ quy ước: **giá trị tiền trong miền bài toán phải thể hiện đơn vị rõ ràng**.

Một bản ghi có thể ngắn như sau:

~~~markdown
### JAVA-NAMING-04 — Tên tiền tệ có đơn vị

Phạm vi:
- Java code trong các thành phần tính giá và đơn hàng.

Quy ước:
- Với tiền được biểu diễn bằng số nguyên VND, tên chứa hậu tố Vnd.
- Dùng tên theo ý nghĩa nghiệp vụ: subtotalVnd, shippingFeeVnd.
- Không dùng amount hoặc price nếu đơn vị và vai trò chưa rõ.

Nên:
    long shippingFeeVnd = 30_000L;

Tránh:
    long fee = 30_000L;

Lý do:
- Giảm nhầm lẫn giữa VND, xu và các giá trị tiền khác.
- Người đọc biết đơn vị tại nơi sử dụng.

Giới hạn:
- Không thay thế mô hình Money khi có đa tiền tệ và quy tắc làm tròn.

Kiểm tra:
- Code review và test các ranh giới chuyển đổi đơn vị.

Chủ sở hữu / thời điểm xem lại:
- Nhóm sở hữu nghiệp vụ thanh toán, xem lại khi thêm tiền tệ khác.
~~~

Đối với phần lớn quy ước, nên có ít nhất:

- **Tên và phạm vi:** áp dụng cho ngôn ngữ, module, loại thành phần hoặc tình huống nào.
- **Quy tắc khẳng định:** nói rõ phải làm gì; tránh chỉ viết “viết code sạch”.
- **Ví dụ nên làm và nên tránh:** ngắn, có ngữ cảnh và thể hiện đúng điểm khác biệt.
- **Lý do:** liên hệ đến độ tin cậy, khả năng hiểu, khả năng thay đổi hoặc rủi ro thực tế.
- **Cách xác minh:** formatter, linter, test, review hoặc kiểm tra kiến trúc.
- **Ngoại lệ và thời điểm xem lại:** khi nào quy tắc không phù hợp, ai có quyền quyết định.

Đừng bắt buộc mọi mục phải có cùng độ dài. Một quy tắc định dạng có thể chỉ cần liên kết đến cấu hình formatter; một quy tắc phân quyền phải diễn đạt điều kiện nghiệp vụ và ví dụ thử quyền bị từ chối.

## 4. Viết ví dụ đối chiếu: cùng một vấn đề, hai cách xử lý

Ví dụ tốt cần cho người đọc thấy **tác dụng của quy ước**, không chỉ gắn nhãn “bad” và “good”.

### 4.1. Đặt tên theo ý nghĩa và đơn vị

Ví dụ chưa rõ:

~~~java
long p = 500000;
long x = p / 10;
return p - x;
~~~

Người đọc không biết `p` là giá gốc, tổng tiền hay tiền đặt cọc; cũng không biết đơn vị đo hoặc điều kiện giảm.

Diễn đạt rõ hơn:

~~~java
long subtotalVnd = 500_000L;
long vipDiscountVnd = subtotalVnd / 10;
long amountAfterDiscountVnd =
        subtotalVnd - vipDiscountVnd;
return amountAfterDiscountVnd;
~~~

Cách này không tự giải quyết mọi lỗi nghiệp vụ: vẫn cần kiểm tra **khi nào** khách được giảm 10%, kiểu số có phù hợp và quy tắc làm tròn có được chấp nhận không. Nhưng tên rõ giúp người đọc và người review đặt câu hỏi đúng.

### 4.2. Quy tắc xử lý dữ liệu không hợp lệ

Ví dụ dễ che lỗi:

~~~java
static long calculateTotal(long amountVnd) {
    if (amountVnd < 0) {
        return 0L;
    }
    return amountVnd;
}
~~~

Đoạn này tự biến giá trị âm thành 0. Nếu nghiệp vụ không cho phép âm, lỗi đầu vào bị làm mờ và báo cáo có thể sai.

Quy ước minh họa có thể là **“phát hiện đầu vào vi phạm bất biến ở ranh giới miền, không âm thầm thay bằng giá trị có nghĩa nghiệp vụ khác”**:

~~~java
static long calculateTotal(long amountVnd) {
    if (amountVnd < 0) {
        throw new IllegalArgumentException(
                "amountVnd must not be negative");
    }
    return amountVnd;
}
~~~

Không phải lúc nào cũng phải ném `IllegalArgumentException`. Một API có thể cần trả lỗi có mã, một batch có thể ghi bản ghi lỗi để xử lý tiếp. Điều cần nhất quán là **chính sách về dữ liệu không hợp lệ**, được diễn đạt tại ranh giới phù hợp; không phải cấm mọi cơ chế phản hồi khác.

### 4.3. Đặt tên kiểm thử theo hành vi

Tên chưa mang nhiều thông tin:

~~~java
@Test
void testPrice1() {
    assertEquals(0L, ShippingPolicy.feeVnd(500_000L));
}
~~~

Tên diễn đạt hành vi:

~~~java
@Test
void waivesShippingAtExactThreshold() {
    assertEquals(0L, ShippingPolicy.feeVnd(500_000L));
}
~~~

Người đọc hiểu đây là test **đúng ngưỡng**, vì vậy nếu test thất bại sau khi đổi chính sách sẽ biết trường hợp nào bị ảnh hưởng. Giá trị `500_000L` và kết quả mong đợi phải lấy từ đặc tả, không sao chép từ biểu thức có thể sai trong mã sản xuất.

### 4.4. Đưa ví dụ “không nên làm” vào đúng phạm vi

Ví dụ cấm `null` tuyệt đối có thể khiến nhóm lúng túng khi làm việc với thư viện hoặc API hợp đồng có giá trị thiếu. Thay vì viết “không dùng null”, hãy viết:

> Trong các phương thức thuộc lõi miền, đầu vào bắt buộc phải được xác minh; nếu vắng dữ liệu là trạng thái hợp lệ thì mô hình hóa rõ bằng kiểu hoặc kết quả phù hợp. Ở adapter, được phép nhận `null` từ thư viện ngoài nhưng phải ánh xạ sang hợp đồng miền trước khi truyền tiếp.

Ví dụ cần thể hiện **điều kiện áp dụng**, **đường dữ liệu** và **nơi xử lý ngoại lệ**. Quy ước càng có phạm vi rõ, người áp dụng càng ít phải đoán.

## 5. Ví dụ hoàn chỉnh: một quy ước được thể hiện bằng Java và test

Giả sử tài liệu nhóm nêu:

> “Dữ liệu dùng để tính tổng tiền phải có tên và đơn vị rõ, bất biến sau khi tiếp nhận; dữ liệu sai được từ chối; phép cộng và nhân tiền phải phát hiện tràn số; logic tính toán không phụ thuộc I/O.”

Đây là **quy ước minh họa** cho bài học, không phải chính sách mặc định của mọi dự án. Để người đọc áp dụng được, tài liệu nên có ví dụ thể hiện cả đầu vào, xử lý và kiểm thử.

### 5.1. Mô hình dữ liệu

Ví dụ dùng Java 17:

~~~java
import java.util.List;
import java.util.Objects;

record OrderLine(String sku, long unitPriceVnd, int quantity) {
    OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException(
                    "unitPriceVnd must not be negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }
}

record OrderDraft(String requestId, List<OrderLine> lines) {
    OrderDraft {
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException(
                    "requestId is required");
        }
        Objects.requireNonNull(lines, "lines");
        lines = List.copyOf(lines);
    }
}
~~~

Những lựa chọn thể hiện quy ước:

- **`unitPriceVnd`:** tên nói rõ vai trò và đơn vị.
- **`OrderLine`, `OrderDraft`:** dữ liệu nhóm theo khái niệm miền, không theo lớp HTTP hay database.
- **Compact constructor:** kiểm tra bất biến tại điểm tạo đối tượng.
- **`List.copyOf`:** ngăn bên gọi thay đổi cấu trúc danh sách sau khi `OrderDraft` được tạo, đồng thời từ chối phần tử `null`.

Ở đây, `OrderLine` chứa các trường bất biến nên việc sao chép danh sách ở mức cấu trúc phù hợp. Nếu phần tử chứa tham chiếu mutable, **bản sao nông** chưa đủ bảo đảm bất biến sâu. Đồng thời, ví dụ cho phép danh sách rỗng và tổng bằng 0; nghiệp vụ thật phải xác nhận điều kiện này trước khi áp dụng.

### 5.2. Phần tính toán

~~~java
import java.util.Objects;

final class OrderTotalCalculator {
    static long subtotalVnd(OrderDraft order) {
        Objects.requireNonNull(order, "order");

        long subtotalVnd = 0L;
        for (OrderLine line : order.lines()) {
            long lineTotalVnd = Math.multiplyExact(
                    line.unitPriceVnd(), (long) line.quantity());
            subtotalVnd = Math.addExact(subtotalVnd, lineTotalVnd);
        }
        return subtotalVnd;
    }
}
~~~

Hàm tính toán không đọc file, gửi mạng hoặc ghi database; kết quả phụ thuộc vào đầu vào. **`Math.multiplyExact`** và **`Math.addExact`** ném `ArithmeticException` khi phép toán tràn giới hạn của `long`, giúp không âm thầm tạo kết quả sai.

Hàm này minh họa **quy ước về ranh giới trách nhiệm và an toàn dữ liệu**, không phải yêu cầu mọi phép tính đều phải là `static`. Nếu có chính sách giá phụ thuộc cấu hình, có thể dùng một đối tượng được cấp chính sách bất biến và nhận dữ liệu rõ ràng.

### 5.3. Kiểm thử thể hiện ý định của quy ước

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderTotalCalculatorTest {
    @Test
    void sumsLineTotalsInVnd() {
        OrderDraft order = new OrderDraft(
                "REQ-01",
                List.of(
                        new OrderLine("A", 120_000L, 2),
                        new OrderLine("B", 30_000L, 1)));

        assertEquals(270_000L,
                OrderTotalCalculator.subtotalVnd(order));
    }

    @Test
    void rejectsNegativeUnitPrice() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine("A", -1L, 1));
    }

    @Test
    void detectsOverflow() {
        OrderDraft order = new OrderDraft(
                "REQ-02",
                List.of(new OrderLine("A", Long.MAX_VALUE, 2)));

        assertThrows(ArithmeticException.class,
                () -> OrderTotalCalculator.subtotalVnd(order));
    }

    @Test
    void keepsSnapshotWhenCallerChangesOriginalList() {
        List<OrderLine> original = new ArrayList<>();
        original.add(new OrderLine("A", 10_000L, 1));

        OrderDraft order = new OrderDraft("REQ-03", original);
        original.clear();

        assertEquals(10_000L,
                OrderTotalCalculator.subtotalVnd(order));
    }
}
~~~

Bộ test làm rõ **kết quả nghiệp vụ**, **dữ liệu sai**, **tràn số** và **sở hữu danh sách**. Nhờ vậy, ví dụ trong tài liệu không chỉ thể hiện kiểu trình bày mà còn thể hiện **cách kiểm chứng quy tắc**.

Đoạn mã minh họa dành cho Java 17 và JUnit 5. Khi đưa vào tài liệu dự án thật, cần xác nhận phiên bản Java, thư viện, cấu trúc package và chính sách nghiệp vụ tương ứng. Không nên chép ví dụ rồi mặc định nó đã đáp ứng mọi ràng buộc như đa tiền tệ, giao dịch hoặc phân quyền.

## 6. Tài liệu dễ tra cứu cần trả lời câu hỏi trong ít bước

Một quy ước không có ích nếu người đọc phải mở mười trang và hỏi nhiều người mới tìm thấy ví dụ.

Một cấu trúc tài liệu **minh họa** cho repository Java:

~~~text
README.md
CONTRIBUTING.md
docs/
  conventions/
    README.md
    java-style.md
    domain-boundaries.md
    errors-and-logging.md
    testing.md
    exceptions.md
  decisions/
    ADR-001-sample.md
~~~

Đây chỉ là mô hình tổ chức; không yêu cầu dự án phải có đúng tên thư mục và không có nghĩa worker tạo thêm các tệp này. Ý quan trọng là có **đường dẫn vào dễ thấy** và những trang giải quyết câu hỏi của người dùng theo chủ đề.

### 6.1. Trang nhập môn là bản đồ, không phải sách chép lại

Ví dụ nội dung một `docs/conventions/README.md`:

~~~markdown
# Quy ước phát triển Java

Bắt đầu từ:
- Định dạng và tên: java-style.md
- Ranh giới logic nghiệp vụ/I-O: domain-boundaries.md
- Xử lý lỗi và log: errors-and-logging.md
- Viết test: testing.md
- Ngoại lệ được chấp nhận: exceptions.md

Cách kiểm tra trước PR:
- Chạy formatter/linter theo lệnh được repository quy định.
- Chạy kiểm thử liên quan.
- Dùng checklist PR khi thay quy tắc hoặc public API.

Nếu quy tắc không phù hợp:
- Ghi rõ lý do và đề xuất thay đổi hoặc ngoại lệ có phạm vi.
- Không tự tắt kiểm tra trên diện rộng.
~~~

Trang này **chỉ dẫn**, không sao chép nội dung chi tiết từ các trang con. Nếu cùng một quy tắc được mô tả độc lập ở README, wiki và tài liệu nhóm, khi cập nhật rất dễ có ba phiên bản mâu thuẫn nhau.

### 6.2. Trang chi tiết nên đi từ câu hỏi tới ví dụ

Một trang hướng dẫn về lỗi có thể tổ chức:

1. **Khi nào áp dụng:** tại ranh giới API, use case, miền hoặc adapter.
2. **Quy tắc chính:** dữ liệu sai, lỗi nghiệp vụ và lỗi hạ tầng được phân loại thế nào.
3. **Ví dụ nên/không nên:** Java code có thông điệp rõ ràng.
4. **Cách kiểm tra:** các test cần có, công cụ nào hỗ trợ.
5. **Trường hợp ngoại lệ:** ví dụ adapter phải ánh xạ lỗi từ thư viện ngoài.
6. **Liên kết liên quan:** xử lý retry, logging, transaction hoặc ADR.

Một người đang sửa lỗi tại API cần đi thẳng đến **quy tắc xử lý lỗi** thay vì phải đọc toàn bộ tài liệu kiến trúc.

### 6.3. Tên trang và mục lục theo câu hỏi thường gặp

Ưu tiên tiêu đề như **“Xử lý dữ liệu thiếu”**, **“Đặt tên tiền và thời gian”**, **“Chọn unit test hay integration test”** hơn là `misc-01`, `best-practices-v2` hoặc “Các vấn đề khác”. Người đọc và tính năng tìm kiếm repository sẽ dễ xác định nơi cần xem.

Các từ khóa đồng nghĩa cũng hữu ích: “exception”, “lỗi”, “failure”, “`null`”, “Optional”. Nhưng không nên lặp nội dung chỉ để nhồi từ khóa. Có thể tạo một bảng câu hỏi/đường dẫn ở trang đầu.

## 7. Làm ví dụ ngắn nhưng không gây hiểu sai

Một snippet chỉ có vài dòng dễ sao chép, nhưng nếu bỏ quá nhiều giả thiết thì có thể truyền đạt sai quy tắc.

Một ví dụ dùng trong tài liệu nên trả lời:

- **Ngôn ngữ và phiên bản:** Java 17 hay phiên bản khác?
- **Đầu vào và hợp đồng:** tham số có thể `null` hay âm không, đơn vị gì?
- **Hành vi mong đợi:** ví dụ chỉ minh họa formatting hay cũng minh họa nghiệp vụ?
- **Phụ thuộc:** dùng JDK, JUnit, SLF4J hoặc thư viện khác?
- **Giới hạn:** code mẫu có bỏ phần xác thực, transaction, giám sát hay xử lý lỗi thực tế không?
- **Cách xác minh:** có test hay kết quả đầu ra chính xác không?

Một mẫu trình bày hiệu quả là **bối cảnh → ví dụ chưa phù hợp → ví dụ phù hợp → vì sao → giới hạn**.

### 7.1. Không làm “bad example” quá cực đoan

Nếu ví dụ xấu vừa dùng tên sai, vừa có bug, vừa lộ dữ liệu, vừa gọi database không an toàn, người đọc không biết **điều nào là trọng tâm của quy ước**. Hãy thay đổi ít chi tiết nhất có thể để minh họa đúng một ý.

Ví dụ để giải thích camelCase trong Java:

~~~java
// Tránh nếu quy ước nhóm dùng camelCase cho tên phương thức.
long calculate_total(long subtotalVnd) {
    return subtotalVnd;
}

// Nên.
long calculateTotal(long subtotalVnd) {
    return subtotalVnd;
}
~~~

Hai snippet cho thấy khác biệt tên mà không thêm logic nghiệp vụ. Tất nhiên, tên phương thức thực tế vẫn phải diễn tả chức năng đúng; ở đây mục tiêu là **quy tắc đặt tên**, không phải ví dụ kiến trúc.

### 7.2. Ví dụ dài nên có điểm vào và kết quả

Khi cần ví dụ nhiều lớp, cung cấp sơ đồ và thứ tự đọc:

~~~mermaid
flowchart LR
    A[Adapter nhận dữ liệu] --> B[Use case điều phối]
    B --> C[Quy tắc miền bài toán]
    C --> B
    B --> D[Adapter lưu hoặc xuất]
~~~

Nêu rõ **mũi tên biểu diễn luồng dữ liệu lúc chạy**, không tự động là chiều phụ thuộc mã nguồn. Mục tiêu giúp người mới biết đặt logic vào đâu và cần kiểm thử gì, không phải buộc mọi ứng dụng nhỏ dùng đủ bốn lớp.

### 7.3. Ví dụ kiểm tra bảo mật không được giả vờ là giải pháp đầy đủ

Một đoạn code chỉ cho thấy việc từ chối đầu vào rỗng **không chứng minh** API an toàn trước injection, lộ dữ liệu hay thiếu phân quyền. Khi minh họa quy ước security, phải phân biệt **hợp đồng nhập liệu**, **parameter binding**, **quyền theo đối tượng** và **cấu hình vận hành**, tránh gộp chúng dưới câu “đã validate”.

Tài liệu dễ tra cứu cũng cần trung thực về giới hạn của ví dụ; nếu snippet chỉ diễn đạt ý tưởng, hãy ghi “minh họa, chưa phải triển khai production hoàn chỉnh”.

## 8. Kết hợp tài liệu với công cụ tự động

Quy ước mạnh nhất thường có cả **lời giải thích cho con người** và **cơ chế kiểm tra phù hợp**.

| Loại quy tắc | Cơ chế hỗ trợ | Đừng kỳ vọng công cụ tự giải quyết |
| --- | --- | --- |
| Định dạng | Formatter theo cấu hình dự án | Ý nghĩa nghiệp vụ hoặc tính đúng đắn |
| Import, tên, cấu trúc phổ biến | Checkstyle, PMD hoặc linter tương đương nếu đã cấu hình | Mọi tên biến đều có nghĩa, mọi trường hợp ngoại lệ đều hợp lý |
| Một số lỗi Java và cách dùng API | Static analyzer phù hợp | Mọi rủi ro phụ thuộc dữ liệu thật hoặc hợp đồng ngoài |
| Quy tắc kiến trúc theo package | Architecture tests hoặc công cụ phân tích phụ thuộc | Bản thân ranh giới đó có đúng với nghiệp vụ không |
| Hợp đồng hành vi | JUnit 5, integration test, contract test | Mọi đường đi hoặc lỗi chưa được mô hình hóa |
| Bí mật vô tình đưa vào mã | Secret scanning ở phạm vi được phép | Mọi hình thức rò dữ liệu qua log hoặc runtime |
| Tài liệu và liên kết | Kiểm tra Markdown/link, review ví dụ và lệnh mẫu | Mọi lời giải thích đều rõ và chính xác |

### 8.1. Ví dụ cấu hình định dạng để giảm tranh luận

Một nhóm có thể thống nhất một cấu hình tương tự:

~~~ini
# Ví dụ minh họa, không áp dụng tự động cho dự án hiện tại.
root = true

[*.java]
charset = utf-8
indent_style = space
indent_size = 4
end_of_line = lf
insert_final_newline = true
~~~

Đây là một **ví dụ về cách ghi quy tắc định dạng**, không phải khẳng định repository đang dùng cấu hình này. Với Java, formatter chính thức của nhóm có thể quyết định thêm các chi tiết khác như vị trí dấu ngoặc và xuống dòng; không nên sửa bằng tay để “đúng tài liệu” nếu formatter của codebase lại có quy tắc khác.

Một khi có công cụ nhất quán, tài liệu chỉ cần nói **lệnh chạy và nơi xem cấu hình**. Đừng bảo người review dành thời gian tranh luận từng khoảng trắng đã có thể tự động xác minh.

### 8.2. Quy ước nào phải được kiểm tra bằng test?

Các quy tắc về **tính đúng** có thể cần test hành vi, ví dụ:

- Giá âm phải bị từ chối.
- Phí được miễn đúng ở ngưỡng.
- Dữ liệu của tenant khác không được trả ra.
- Retry cùng một yêu cầu không tạo giao dịch trùng theo hợp đồng.

Những quy tắc này không thể được bảo vệ chỉ bằng formatter. Trong ví dụ bài học, `OrderTotalCalculatorTest` không nhằm chứng minh tên biến đẹp, mà chứng minh các **bất biến nghiệp vụ** liên quan đến chuẩn code của nhóm.

### 8.3. Kiểm tra chỉ nên chặn khi đủ căn cứ

Nếu linter đưa ra cảnh báo và nhóm áp dụng chính sách **fail build**, cần phân biệt mức lỗi:

- **Bắt buộc:** lỗi rõ ràng, bảo mật, hợp đồng dữ liệu hoặc quy tắc kiến trúc mà nhóm đã thống nhất.
- **Khuyến nghị:** vấn đề dễ đọc phụ thuộc ngữ cảnh, cần code review và có thể chấp nhận ngoại lệ.
- **Tự động sửa:** định dạng có thể chuẩn hóa không làm thay đổi ý nghĩa.

Dùng ngưỡng chặn quá nặng hoặc quy tắc thiếu căn cứ sẽ khiến người phát triển tìm cách tắt công cụ. Ngược lại, không kiểm tra bất kỳ điều gì khiến tài liệu bị lãng quên. Mục tiêu là **kiểm soát rủi ro và giảm chi phí cộng tác**, không tối đa hóa số cảnh báo.

## 9. Một nguồn quy ước chính, nhiều đường dẫn đến

Một codebase có thể có README, wiki, issue, chat, tài liệu onboarding và comment trong code. Vấn đề không phải có nhiều nơi nhắc tới quy ước, mà là **có nhiều nguồn cùng tự nhận là phiên bản chuẩn nhưng nội dung khác nhau**.

Một cách quản lý phù hợp:

1. Chọn **nguồn chính** cho quy ước: thường là tài liệu version-controlled gần repository hoặc hệ thống tài liệu có chủ sở hữu và lịch sử chỉnh sửa rõ.
2. Tại README, onboarding hoặc PR template, **liên kết** đến nguồn chính, không sao chép toàn văn.
3. Khi một quy tắc ảnh hưởng nhiều module, ghi **phạm vi áp dụng** và nơi cần ngoại lệ.
4. Cập nhật ví dụ, cấu hình và tài liệu trong **cùng thay đổi** khi hợp đồng thực sự đổi.
5. Giữ lịch sử quyết định nếu quy tắc mới thay đổi một lựa chọn kiến trúc quan trọng.

Một câu hỏi hữu ích cho người mới là: “Từ README của dự án, có thể tìm quy tắc về xử lý lỗi trong hai hoặc ba lần điều hướng không?” Nếu không, tài liệu có thể đúng nhưng **khó tra cứu**.

### 9.1. Ưu tiên khi các nguồn có vẻ mâu thuẫn

Nếu formatter, tài liệu và một file mã cũ không đồng nhất:

- Kiểm tra **quy định hiện hành** và cấu hình công cụ đang được dự án dùng.
- Xác định file cũ là trường hợp di sản, ngoại lệ có chủ đích hay phần chưa được chuyển đổi.
- Không sao chép một đoạn code chỉ vì nó tồn tại từ lâu.
- Khi phát hiện xung đột, tạo issue/PR cập nhật tài liệu hoặc cơ chế kiểm tra, ghi rõ quyết định.

Không nên tự đoán rằng “code mới nhất luôn là chuẩn”. Code có thể vừa được merge nhưng chưa được review đầy đủ; tài liệu cũng có thể đã cũ. Cần người sở hữu xác nhận điều đang được coi là quy ước có hiệu lực.

## 10. Ghi ngoại lệ để vẫn giữ sự nhất quán có lý do

Quy ước chung không thể bao trùm mọi trường hợp. Một ngoại lệ có thể hợp lý khi:

- SDK hoặc framework buộc tên, chữ ký hoặc vòng đời đặc thù.
- Cần tương thích API đang được nhiều khách hàng sử dụng.
- Mã sinh tự động có tiêu chuẩn định dạng riêng.
- Một đường chạy quan trọng đã được đo đạc và tối ưu có cơ sở.
- Một mô hình nghiệp vụ cần cách biểu diễn khác với hướng dẫn chung.

**Ngoại lệ không có nghĩa muốn viết thế nào cũng được.** Có thể ghi ngắn:

~~~markdown
### Ngoại lệ: LEGACY-API-02
Quy tắc liên quan: JAVA-NAMING-04
Phạm vi: phương thức get_customer_id() ở adapter tương thích cũ
Lý do: giữ chữ ký mà khách hàng của API đang phụ thuộc
Bằng chứng: hợp đồng phiên bản đang được hỗ trợ
Người phụ trách: nhóm tích hợp
Điều kiện xem lại: khi phiên bản API cũ hết thời gian hỗ trợ
Cách kiểm soát: adapter ánh xạ sang tên camelCase trong miền bài toán
~~~

Ví dụ này chỉ diễn đạt một **hồ sơ ngoại lệ**, không khẳng định bắt buộc phải dùng đúng tên trường. Nếu phiên bản cũ không còn được hỗ trợ, nhóm có thể loại bỏ ngoại lệ và thống nhất tên.

Đối với cảnh báo từ công cụ, chú thích tắt kiểm tra nên có **lý do và phạm vi nhỏ nhất**, không tắt toàn bộ thư mục để né một vấn đề. Với kiểm soát bảo mật bắt buộc, ngoại lệ còn có thể cần quy trình phê duyệt riêng, giới hạn thời gian và biện pháp bù trừ.

## 11. Duy trì tài liệu cùng vòng đời code

Tài liệu quy ước dễ trở nên lỗi thời vì framework, quy tắc nghiệp vụ và công cụ thay đổi. Việc tạo tài liệu lần đầu chỉ là một phần công việc.

### 11.1. Khi thêm hoặc sửa quy ước

Một PR thay đổi quy ước nên chỉ rõ:

- Vấn đề thực tế nào đang xảy ra: review tranh luận lặp, lỗi hồi quy, thiếu thống nhất hoặc khó onboarding?
- Quy tắc mới giải quyết điều gì và áp dụng ở đâu?
- Những ví dụ nào từ code hiện tại cần cập nhật?
- Công cụ kiểm tra nào được sửa và mức độ chặn có thay đổi không?
- Có phần mã cũ cần di chuyển dần hay có thể giữ nguyên?
- Người sử dụng cần biết thay đổi từ thời điểm nào?
- Có quyết định hoặc ngoại lệ nào bị thay thế?

Cùng một PR cập nhật ví dụ và cơ chế kiểm tra giúp tránh giai đoạn “tài liệu dạy một kiểu, CI yêu cầu kiểu khác”.

### 11.2. Xử lý quy ước đã lỗi thời

Nếu một hướng dẫn không còn phù hợp, đừng âm thầm xóa dấu vết khi nhóm vẫn cần hiểu code cũ. Có thể:

1. Đánh dấu **đã thay thế** hoặc **chỉ áp dụng cho phiên bản cũ**.
2. Liên kết tới quy ước mới và lý do.
3. Ghi phạm vi chuyển đổi và thời điểm kết thúc hỗ trợ nếu có.
4. Loại bỏ liên kết cũ khỏi trang nhập môn hoặc thêm chuyển hướng rõ.

Đặc biệt với cách xử lý lỗi, phân quyền hoặc hợp đồng dữ liệu, việc đổi quy ước có thể đòi hỏi kế hoạch chuyển đổi và kiểm thử tương thích, không chỉ cập nhật Markdown.

### 11.3. Quy ước không được trở thành “luật bất biến”

Tính nhất quán giúp người đọc dự đoán code, nhưng nếu một quy tắc gây chi phí lớn hơn lợi ích, nhóm cần có khả năng xem lại. Việc đánh giá nên dựa trên **khả năng hiểu, mức độ lỗi, tốc độ thay đổi và chi phí phối hợp**, không dựa trên sở thích thẩm mỹ của một người.

## 12. Quy trình viết tài liệu có thể áp dụng cho một nhóm Java

### Bước 1 — Thu thập câu hỏi có thật

Nguồn đầu vào có thể là comment code review, issue lặp lại, câu hỏi onboarding và lỗi sản xuất. Ví dụ: “Khi nào dùng `Optional`?”, “Cần validate ở controller hay domain?”, “Có được log request body không?”.

Không bắt đầu bằng cách viết một cẩm nang dài về tất cả thứ có thể nghĩ ra. Ưu tiên những quy ước đang làm nhóm mất thời gian hoặc có rủi ro lớn.

### Bước 2 — Chọn một nguồn chính và cấu trúc tìm kiếm

Đặt liên kết từ README/CONTRIBUTING hoặc điểm vào quen thuộc. Tổ chức theo **tác vụ** hoặc **vấn đề người đọc muốn giải quyết**, kèm bảng mục lục ngắn, từ khóa và liên kết tương đối.

### Bước 3 — Viết quy tắc khẳng định và phạm vi

Thay “dùng exception hợp lý” bằng “tầng miền từ chối trạng thái bất hợp lệ; adapter chuyển lỗi giao tiếp thành kết quả/lỗi mà use case có thể xử lý; không nuốt lỗi không mong đợi”.

Nếu quy tắc không thể nói rõ điều kiện áp dụng, có thể chưa phải quy tắc đủ chín để bắt buộc áp dụng toàn nhóm.

### Bước 4 — Tạo ví dụ đối chiếu và kiểm thử nếu cần

Ví dụ nên giải quyết đúng sự mơ hồ, có tên dữ liệu có nghĩa và tránh lẫn nhiều lỗi không liên quan. Với quy tắc bảo mật hoặc tính tiền, bổ sung test hành vi và nêu giới hạn của snippet.

### Bước 5 — Đặt cơ chế xác minh phù hợp

Formatter cho hình thức, lint cho các mẫu tĩnh, test cho hợp đồng, architecture test cho một số ranh giới, review cho điều kiện phụ thuộc ngữ nghĩa. Không yêu cầu một công cụ giải quyết vấn đề ngoài phạm vi của nó.

### Bước 6 — Thử tra cứu cùng người chưa biết quy tắc

Đưa một tình huống cụ thể: “Tôi cần xử lý đầu vào `null` từ SDK, nên làm gì?” Người thử phải tự tìm tài liệu, chọn ví dụ phù hợp và giải thích trường hợp ngoại lệ. Nếu họ hiểu sai, vấn đề có thể nằm ở tài liệu chứ không chỉ ở người đọc.

### Bước 7 — Kết nối vào PR và onboarding

Một checklist PR ngắn có thể hỏi:

- Có sử dụng quy ước đặt tên và hợp đồng dữ liệu đang áp dụng?
- Đã chạy công cụ định dạng/kiểm tra được yêu cầu?
- Có ví dụ hoặc test cho quy tắc mới quan trọng không?
- Nếu có ngoại lệ, đã ghi rõ phạm vi và lý do chưa?
- Nếu thay quy ước chung, đã cập nhật tài liệu tại nguồn chính chưa?

Không biến checklist thành hàng trăm ô khiến mọi người chỉ đánh dấu hình thức.

### Bước 8 — Rà soát và giảm nội dung thừa

Khi câu hỏi thường gặp đã được giải quyết bằng một trang tốt, không cần sinh thêm bản gần giống ở chỗ khác. Đánh giá tài liệu dựa trên việc giúp người đọc **tìm và áp dụng đúng**, chứ không phải số lượng trang.

## 13. Bảng tra cứu nhanh minh họa

Một phần đầu tài liệu có thể đặt bảng như sau để người đọc tìm ngay đúng mục:

| Bạn đang làm gì? | Quy ước nên tra | Ví dụ hoặc kiểm tra cần có |
| --- | --- | --- |
| Viết hàm tính tiền | Tên có đơn vị và bất biến dữ liệu | `subtotalVnd`, kiểm thử overflow và ngưỡng |
| Nhận dữ liệu từ API/SDK | Kiểm tra hợp đồng ở ranh giới | Giá trị thiếu, sai kiểu, trạng thái mới |
| Truy cập database | Ranh giới miền/I-O và nguyên tắc truy vấn an toàn | Test mapping, query và phân quyền theo đối tượng |
| Ghi log sự cố | Log có chọn lọc và bảo vệ dữ liệu | Không log token, mã tương quan có kiểm soát |
| Thêm phương thức mới | Đặt tên, trách nhiệm và test | Tên thể hiện hành vi, test trường hợp biên |
| Dùng phụ thuộc mới | Quy tắc version, scope và ranh giới phụ thuộc | Chủ sở hữu, rủi ro, kiểm thử tích hợp |
| Xử lý ngoại lệ | Phân loại lỗi miền, I/O và thông điệp | Không trả `null` để che lỗi ngoài hợp đồng |
| Sửa mã cũ khác quy ước | Chính sách di chuyển và ngoại lệ | Giữ tương thích, ghi lý do và lộ trình |
| Viết hướng dẫn mới | Mẫu ghi quy ước | Phạm vi, nên/tránh, vì sao, cách kiểm chứng |

Bảng này hữu ích khi mỗi hàng có **liên kết thực** đến trang tương ứng trong repository. Không nên đưa đường dẫn giả vào tài liệu chính thức rồi để người đọc nhận lỗi 404.

## 14. Đánh giá hiệu quả bằng tín hiệu thực tế

Có thể dùng các câu hỏi sau để xem tài liệu có giúp nhóm làm việc tốt hơn không:

| Tín hiệu | Cách diễn giải | Cần thận trọng |
| --- | --- | --- |
| Câu hỏi lặp lại giảm | Người đọc có thể tự tra quy tắc | Cũng có thể người mới ngại hỏi; cần phỏng vấn |
| Thời gian onboarding cho tác vụ quen thuộc giảm | Ví dụ và đường dẫn có hiệu quả | Phụ thuộc độ khó tác vụ và kinh nghiệm |
| Review bớt tranh luận định dạng | Formatter và hướng dẫn nhất quán | Không có nghĩa chất lượng nghiệp vụ đã tăng |
| Ít lỗi cùng loại tái xuất hiện | Test, quy ước và review có thể đang hiệu quả | Cần đối chiếu số lượng thay đổi và rủi ro |
| Ít ngoại lệ mơ hồ | Phạm vi quy tắc rõ hơn | Không nên cấm ngoại lệ hợp lý |
| Cập nhật code và docs đi cùng nhau | Ít nguy cơ tài liệu lỗi thời | Cần kiểm tra nội dung chứ không chỉ số file |
| Người mới tìm được hướng dẫn không cần hỏi | Khả năng tra cứu được cải thiện | Đừng chỉ đo số lượt mở trang |

Không nên đặt KPI “càng nhiều quy ước càng tốt”. Một bộ quy ước nhỏ, chính xác và dễ tra có thể giá trị hơn một tài liệu dài, trùng lặp và hiếm ai đọc.

## 15. Những sai lầm thường gặp

**“Đã có style guide là mọi người sẽ làm theo.”** Không. Nếu không có điểm vào, ví dụ và cách kiểm tra, người mới có thể không biết tài liệu tồn tại hoặc không hiểu áp dụng vào tình huống nào.

**“Cứ lấy một file đang chạy tốt làm ví dụ chuẩn.”** Không hẳn. File có thể chứa quyết định lịch sử, ngoại lệ hoặc lỗi chưa được phát hiện. Ví dụ chuẩn nên được review theo quy ước hiện hành.

**“Đưa càng nhiều quy tắc vào một trang càng dễ tìm.”** Không chắc. Một trang dài không có mục lục và từ khóa có thể khó tra hơn vài trang theo tác vụ với điểm vào rõ ràng.

**“Ví dụ vài dòng không cần nói giả thiết.”** Sai nếu người đọc có thể sao chép vào hệ thống thật. Ít nhất phải ghi phạm vi và giới hạn khi ví dụ bỏ qua phân quyền, giao dịch, cấu hình hoặc dữ liệu lỗi.

**“Formatter thay thế được code review.”** Không. Formatter xử lý hình thức, không quyết định phương thức tính đúng hay chính sách phân quyền phù hợp.

**“Quy ước đặt tên là vấn đề thẩm mỹ.”** Tên và đơn vị giúp hiểu hợp đồng, tránh nhầm nghĩa; song không nên đặt nặng thẩm mỹ hơn tính đúng và bảo mật.

**“Chỉ cần lệnh lint xanh là mã bảo trì tốt.”** Không. Quy tắc tự động chỉ nhìn thấy một phần cấu trúc và không thay thế test, review nghiệp vụ hoặc đánh giá rủi ro.

**“Mọi ngoại lệ đều là vi phạm.”** Không. Một ngoại lệ có thể cần để giữ tương thích hoặc đáp ứng framework; quan trọng là có lý do, phạm vi, người phụ trách và điều kiện xem lại.

**“Phải chuyển tất cả mã cũ sang chuẩn mới ngay.”** Không nhất thiết. Thay đổi hàng loạt có thể gây diff nhiễu và rủi ro hồi quy. Có thể áp dụng quy ước trên phần mới/sửa, với kế hoạch di chuyển phù hợp.

**“Tài liệu càng ít thay đổi càng tốt.”** Không. Khi quy tắc, công cụ hoặc nghiệp vụ đổi, tài liệu cần cập nhật theo. Một tài liệu ổn định nhưng sai còn gây hại hơn tài liệu thay đổi có kiểm soát.

**“Mọi ví dụ nên dùng framework đầy đủ để giống production.”** Không hẳn. Ví dụ tập trung vào một quy ước có thể dùng Java thuần; chỉ cần bổ sung adapter/framework khi muốn minh họa chính ranh giới đó.

## 16. Tình huống thực hành

### Tình huống A — Hai người review góp ý trái ngược

Một người yêu cầu mọi service trả `Optional`; người khác muốn ném ngoại lệ khi không tìm thấy bản ghi. Tài liệu nhóm chỉ ghi “tránh null”.

**Câu hỏi:** nên ghi quy ước thế nào để lần sau không tranh luận từ đầu?

**Gợi ý:** phân biệt trường hợp “không tìm thấy là kết quả nghiệp vụ hợp lệ” với “không tìm thấy vi phạm yêu cầu bắt buộc”. Nêu phạm vi ở tầng repository, use case và API; thêm ví dụ và cách ánh xạ lỗi. Không chọn `Optional` hay exception chỉ vì sở thích cú pháp.

### Tình huống B — CI chấp nhận, nhưng người mới viết mã khó hiểu

Một phương thức tuân theo formatter và linter nhưng có tên `processData`, gọi nhiều API, sửa trạng thái đơn và ghi tệp; nhóm mới không biết test ở đâu.

**Câu hỏi:** còn thiếu quy ước nào?

**Gợi ý:** cần quy ước về trách nhiệm của phương thức, ranh giới I/O với logic miền, hợp đồng tác dụng phụ và cách kiểm thử. Tự động định dạng không phát hiện hết vấn đề cấu trúc và ngữ nghĩa.

### Tình huống C — Tài liệu và code mẫu mâu thuẫn

Trang wiki yêu cầu trả `null` khi không tìm thấy, file ví dụ mới lại dùng `Optional`, còn một số service cũ ném exception.

**Câu hỏi:** tài liệu nào là nguồn chuẩn?

**Gợi ý:** không đoán. Xác định người sở hữu quy ước và hợp đồng đang được áp dụng, chốt nguồn chính, cập nhật liên kết và giải thích trường hợp cũ/ngoại lệ. Không sao chép mâu thuẫn sang một trang thứ tư.

### Tình huống D — Quy ước mới ảnh hưởng API tương thích cũ

Nhóm đổi sang camelCase nhưng client đang gọi phương thức theo tên cũ qua thư viện được phát hành nhiều phiên bản.

**Câu hỏi:** có nên đổi tên ngay để linter xanh?

**Gợi ý:** đánh giá hợp đồng công khai và tương thích. Có thể giữ adapter ở ranh giới cũ, chuyển tên nội bộ, ghi ngoại lệ và lộ trình bỏ hỗ trợ; tránh phá API chỉ để thỏa quy tắc trình bày.

### Tình huống E — Tài liệu về log vô tình hướng dẫn ghi bí mật

Một snippet xử lý lỗi HTTP log toàn bộ request header để “dễ debug”. Người mới sao chép vào service thật.

**Câu hỏi:** ví dụ cần cải thiện gì?

**Gợi ý:** thay bằng log các trường có chọn lọc như mã tương quan và loại lỗi; nêu dữ liệu không được ghi và quyền truy cập log. Cần kiểm tra chính sách thông tin nhạy cảm, không chỉ formatter hay tên biến.

## 17. Checklist trước khi công bố một quy ước

- **Đúng vấn đề:** quy ước giải quyết lỗi, chi phí đọc hiểu hoặc khó thay đổi cụ thể nào?
- **Đúng phạm vi:** áp dụng cho module, tầng, ngôn ngữ và phiên bản nào?
- **Dễ tìm:** có liên kết từ README, trang nhập môn hoặc nơi nhóm thường mở không?
- **Dễ làm:** có ví dụ nên/tránh, đầu vào, kết quả và lý do rõ ràng?
- **Trung thực:** ví dụ có nêu giả thiết, giới hạn và phụ thuộc cần thiết?
- **Đúng cấp kiểm chứng:** formatter/lint, test, architecture check hay review nghiệp vụ?
- **Nhất quán:** tài liệu có khớp cấu hình công cụ và code mẫu hiện hành?
- **Có ngoại lệ:** khi quy tắc không phù hợp, ai quyết định và ghi ở đâu?
- **Có người sở hữu:** ai sửa tài liệu khi framework hoặc yêu cầu đổi?
- **Có hiệu quả:** người mới có thể tìm và áp dụng mà không phải giải thích lại từ đầu?

Đưa quy ước vào **ví dụ rõ ràng và tài liệu dễ tra cứu** biến kiến thức ngầm của một vài người thành cách làm việc có thể chia sẻ. Khi quy tắc có phạm vi, lý do, ví dụ đối chiếu và cơ chế xác minh phù hợp, nó giúp nhóm **viết mã đáng tin cậy hơn, đọc hiểu nhanh hơn và thay đổi ít rủi ro hơn**. Trong **CODE_QUALITY_FUNDAMENTALS**, tính nhất quán có giá trị khi phục vụ những mục tiêu đó — không phải khi chỉ làm các tệp trông giống nhau.
