# Nhận diện dấu hiệu cần cải thiện thiết kế OOP

> **Chủ đề:** Tái cấu trúc (refactoring) — nhận ra lúc thiết kế bắt đầu gây khó khăn, xác định nguyên nhân và chọn bước cải thiện nhỏ, có kiểm chứng.

Một chương trình Java **chạy đúng** chưa chắc đã **dễ thay đổi**. Dấu hiệu cần cải thiện thường xuất hiện khi thêm một quy tắc nhỏ mà phải sửa nhiều nơi, một lớp phụ trách nhiều việc, cùng một điều kiện nghiệp vụ bị sao chép, hoặc kiểm thử một chức năng đơn giản lại cần khởi tạo hàng loạt phụ thuộc.

Các hiện tượng như vậy thường được gọi là **code smell**: tín hiệu gợi ý rằng cấu trúc mã có vấn đề đáng xem xét. **Code smell không tự động là lỗi** và không có quy tắc “cứ gặp là phải refactor”. Mục tiêu là đánh giá *tác động* của thiết kế đến sửa lỗi, mở rộng, hiểu mã và kiểm thử; sau đó cải thiện với chi phí hợp lý.

## 1. Nhìn vào khó khăn khi thay đổi, không chỉ độ dài của mã

Hãy đặt câu hỏi thực tế:

- Khi thêm một tính năng nhỏ, phải mở và chỉnh sửa bao nhiêu class? Các vị trí đó có cùng một lý do thay đổi không?
- Khi sửa lỗi, điều kiện hay công thức nghiệp vụ có bị lặp ở nhiều nơi?
- Có class nào vừa tính toán nghiệp vụ, vừa truy vấn dữ liệu, vừa định dạng giao diện, vừa gửi email không?
- Một hàm có dễ đọc từ tên và mức trừu tượng của các bước không, hay cần theo dõi nhiều cờ, nhánh lồng nhau và biến tạm?
- Test có thể tạo đối tượng một cách đơn giản, kiểm tra hành vi được không, hay phải mock nhiều chi tiết nội bộ?
- Sau khi sửa một class, có thường xuyên phát sinh lỗi ở các class tưởng như không liên quan?

Những câu trả lời này hữu ích hơn việc chỉ đếm số dòng: một phương thức dài nhưng ổn định, diễn đạt tuyến tính có thể ít rủi ro hơn một phương thức ngắn có nhiều tác dụng phụ khó thấy.

### Các dấu hiệu thường gặp

| Dấu hiệu (code smell) | Quan sát trong code Java | Nguy cơ thực tế | Hướng xem xét, chưa phải mệnh lệnh |
|---|---|---|---|
| **Long Method** | Một phương thức chứa nhiều bước, nhiều nhánh hoặc mức trừu tượng lẫn lộn | Khó đọc, khó test từng quy tắc | `Extract Method` để đặt tên cho các bước có ý nghĩa |
| **Large Class / God Object** | Class nắm nhiều trách nhiệm không liên quan, nhiều field và nhóm method | Mỗi thay đổi gây ảnh hưởng diện rộng | Tách theo lý do thay đổi, tăng tính kết dính |
| **Duplicate Code** | Cùng điều kiện/công thức nghiệp vụ xuất hiện ở nhiều nơi | Sửa thiếu một nơi dẫn đến sai lệch | Tập trung quy tắc chung; tránh trừu tượng hóa sự giống nhau tình cờ |
| **Shotgun Surgery** | Một yêu cầu nhỏ bắt buộc sửa nhiều class | Thay đổi phân tán, khó review | Đưa logic liên quan về một đầu mối phù hợp |
| **Divergent Change** | Một class liên tục sửa vì các lý do khác nhau | Phạm vi trách nhiệm mờ, rủi ro sửa chéo | Tách trách nhiệm theo các hướng biến đổi |
| **Feature Envy** | Method của A liên tục truy cập dữ liệu/chi tiết của B để ra quyết định | Quy tắc đặt sai chỗ, kết dính thấp | Cân nhắc `Move Method` hoặc API giàu ngữ nghĩa trên B |
| **Primitive Obsession** | `String`/`int`/`boolean` gánh nhiều quy tắc miền, “magic string” | Dễ nhầm đơn vị, trạng thái không hợp lệ | `enum`, record/value object hoặc kiểu dữ liệu miền |
| **Long Parameter List / Data Clumps** | Nhiều hàm lặp cùng cụm tham số, nhiều cờ boolean | Gọi nhầm thứ tự, tăng chi phí thay đổi | Gom thành parameter object nếu thực sự là một khái niệm |
| **Conditional Complexity** | `switch`/`if` nhiều nhánh theo loại đối tượng và lặp ở nhiều vị trí | Thêm loại mới phải sửa nhiều nơi | Polymorphism, Strategy, bảng quy tắc nếu phù hợp |
| **Inappropriate Intimacy / Tight Coupling** | Một class biết sâu về dữ liệu/nội bộ của class khác, khởi tạo trực tiếp nhiều dependency | Test khó, thay implementation khó | Giảm coupling, inject dependency ở ranh giới hợp lý |
| **Data Class / Anemic Model** | Object miền chỉ là getter/setter; quy tắc liên quan rải ở service | Bất biến khó được bảo vệ | Đưa *hành vi thuộc trách nhiệm miền* vào nơi phù hợp |
| **Speculative Generality** | Interface, inheritance, plugin point chưa có nhu cầu thực tế | Quá nhiều lớp, khó định hướng | Xóa tầng trừu tượng không đem lại lợi ích rõ ràng |
| **Comments as Deodorant** | Bình luận phải diễn giải các nhánh tối nghĩa | Ý định bị che bởi cấu trúc khó hiểu | Làm rõ tên gọi, phân rã logic; giữ comment về lý do |
| **Mutable Shared State** | Nhiều object sửa cùng danh sách/cache dùng chung | Bug theo thứ tự chạy, race condition | Bất biến dữ liệu, quản lý ownership và concurrency |

**Không dùng số dòng hoặc số class làm luật cứng.** Một class nhỏ nhưng chứa quy tắc mâu thuẫn vẫn có vấn đề. Ngược lại, chia một đoạn logic đơn giản thành 15 interface có thể khiến thiết kế tệ hơn.

## 2. Phân biệt những dấu hiệu dễ nhầm

**Divergent Change** và **Shotgun Surgery** đều gây đau khi sửa code nhưng khác góc nhìn:

- **Divergent Change:** *một class* phải sửa vì nhiều **lý do** khác nhau; ví dụ `OrderManager` cùng chịu ảnh hưởng của thay đổi chính sách giá, định dạng email và schema lưu trữ.
- **Shotgun Surgery:** *một lý do thay đổi* buộc sửa **nhiều class**; ví dụ đổi ngưỡng miễn phí vận chuyển phải cập nhật `Cart`, `Checkout`, `Invoice`, `OrderPreview`.

Tương tự, **Duplicate Code** không có nghĩa mọi đoạn giống nhau phải gom lại. Hai quy tắc hiện tại trông giống nhau nhưng thuộc hai ngữ cảnh có vòng đời thay đổi độc lập có thể nên giữ riêng. Khi trừu tượng hóa, cần chứng minh **cùng một tri thức/nguyên tắc**, không chỉ cùng cú pháp.

**Long Method** khác **Complex Method**: dài vì ánh xạ nhiều bước tuần tự không nhất thiết khó hiểu; ngắn nhưng có nhiều tương tác trạng thái và side effect vẫn có thể phức tạp.

### Từ quan sát đến giả thuyết thiết kế

| Quan sát thực tế | Giả thuyết cần kiểm tra | Bằng chứng nên tìm |
|---|---|---|
| Sửa một quy tắc phải sửa 5 file | Quy tắc bị phân tán | Diff của các thay đổi trước, vị trí công thức trùng lặp |
| Test một class phải mock 8 collaborator | Class gánh nhiều trách nhiệm/coupling cao | Constructor, lời gọi IO, setup trong test |
| Người mới mất nhiều thời gian hiểu một method | Mức trừu tượng hoặc tên chưa rõ | Các nhánh lồng nhau, nhiều biến tạm, diễn giải trong review |
| Có nhiều cờ `boolean` | Một hành vi bị điều khiển bởi nhiều chế độ | Những tổ hợp cờ, trường hợp bất hợp lệ và test thiếu |
| Bug lặp tại nhiều màn hình | Cùng quy tắc bị cài khác nhau | Input và output gây bug, bản sao của quy tắc |
| Tốc độ thay đổi giảm rõ rệt | Có điểm nóng thiết kế | Tần suất sửa, lỗi hồi quy, thời gian review, phạm vi diff |

Để tránh kết luận vội: nhìn vào **trách nhiệm**, **lịch sử thay đổi**, **lỗi thực tế** và **test hiện hữu**. Công cụ static analysis/cảnh báo complexity có thể giúp khoanh vùng; con số metric chỉ là tín hiệu bổ trợ.

## 3. Ví dụ: ba trách nhiệm bị trộn trong một class

Giả sử hệ thống báo giá có hợp đồng đã được thống nhất:

- `subtotalCents` là số tiền hàng theo **cent**, từ `0` đến `1_000_000`.
- Loại khách hàng hợp lệ: chuỗi phân biệt hoa/thường `"STANDARD"` hoặc `"VIP"`.
- Khách VIP được giảm `10%` tiền hàng (làm tròn xuống từng cent) và miễn phí vận chuyển.
- Khách thường không giảm giá; miễn phí vận chuyển khi `subtotalCents >= 100_000`, còn lại trả `15_000` cent.
- `total = subtotal - discount + shipping`.
- Dữ liệu không hợp lệ phải ném `IllegalArgumentException`.
- Chuỗi kết quả có định dạng `discount=...;shipping=...;total=...`.

Phiên bản ban đầu kết hợp **kiểm tra đầu vào**, **tính giá**, **định dạng đầu ra** trong một method. Khi thay quy tắc vận chuyển, đổi output format hoặc bổ sung loại khách hàng, nhóm code này cùng bị tác động. Đó là dấu hiệu **Divergent Change**, đi kèm **Primitive Obsession** vì giá trị `String` đại diện cho loại khách hàng.

Refactor có thể tách một **bộ quy tắc giá**, một **bộ định dạng**, và một **facade** giữ API cũ. Đây chỉ là *một* phương án hợp lý khi các phần có lý do thay đổi độc lập; với ứng dụng rất nhỏ, chi phí thêm lớp có thể không đáng.

### Chạy thử trước và sau refactor (Java 17+)

Tạo tệp `DesignSmellsDemo.java`, đặt toàn bộ đoạn sau vào tệp đó:

~~~java
import java.util.List;

public class DesignSmellsDemo {
    private static final long MAX_SUBTOTAL = 1_000_000L;
    private static final long FREE_SHIPPING_AT = 100_000L;
    private static final long SHIPPING_FEE = 15_000L;

    // API mà client sử dụng; cả hai phiên bản đều thực hiện.
    interface QuoteService {
        String quote(String customerType, long subtotalCents);
    }

    // BEFORE: validation, chính sách giá và định dạng nằm chung.
    static final class LegacyQuoteService implements QuoteService {
        @Override
        public String quote(String customerType, long subtotalCents) {
            if (subtotalCents < 0 || subtotalCents > MAX_SUBTOTAL) {
                throw new IllegalArgumentException("subtotal");
            }
            if (!"VIP".equals(customerType)
                    && !"STANDARD".equals(customerType)) {
                throw new IllegalArgumentException("customerType");
            }

            boolean vip = "VIP".equals(customerType);
            long discount = vip ? subtotalCents / 10 : 0;
            long shipping = (vip || subtotalCents >= FREE_SHIPPING_AT)
                    ? 0 : SHIPPING_FEE;
            long total = subtotalCents - discount + shipping;

            return "discount=" + discount
                    + ";shipping=" + shipping
                    + ";total=" + total;
        }
    }

    // AFTER: biểu diễn loại khách hàng bằng một kiểu miền rõ ràng.
    enum CustomerType {
        STANDARD, VIP;

        static CustomerType parse(String text) {
            if ("STANDARD".equals(text)) return STANDARD;
            if ("VIP".equals(text)) return VIP;
            throw new IllegalArgumentException("customerType");
        }
    }

    // Value object bất biến; trường dữ liệu không bị trộn với format.
    record Price(long discount, long shipping, long total) {}

    static final class PricingRules {
        Price calculate(CustomerType type, long subtotalCents) {
            long discount = type == CustomerType.VIP ? subtotalCents / 10 : 0;
            long shipping =
                    (type == CustomerType.VIP || subtotalCents >= FREE_SHIPPING_AT)
                        ? 0 : SHIPPING_FEE;
            return new Price(discount, shipping,
                    subtotalCents - discount + shipping);
        }
    }

    static final class QuoteFormatter {
        String format(Price price) {
            return "discount=" + price.discount()
                    + ";shipping=" + price.shipping()
                    + ";total=" + price.total();
        }
    }

    // Giữ API cũ; phối hợp các trách nhiệm đã tách ra.
    static final class RefactoredQuoteService implements QuoteService {
        private final PricingRules pricing;
        private final QuoteFormatter formatter;

        RefactoredQuoteService(PricingRules pricing, QuoteFormatter formatter) {
            this.pricing = java.util.Objects.requireNonNull(pricing);
            this.formatter = java.util.Objects.requireNonNull(formatter);
        }

        @Override
        public String quote(String customerType, long subtotalCents) {
            if (subtotalCents < 0 || subtotalCents > MAX_SUBTOTAL) {
                throw new IllegalArgumentException("subtotal");
            }
            CustomerType type = CustomerType.parse(customerType);
            Price price = pricing.calculate(type, subtotalCents);
            return formatter.format(price);
        }
    }

    record Example(String type, long subtotal, String expected) {}

    // Expected values được viết theo yêu cầu, không tính bằng production code.
    private static final List<Example> EXAMPLES = List.of(
        new Example("STANDARD", 0,
                "discount=0;shipping=15000;total=15000"),
        new Example("STANDARD", 99_999,
                "discount=0;shipping=15000;total=114999"),
        new Example("STANDARD", 100_000,
                "discount=0;shipping=0;total=100000"),
        new Example("VIP", 100_000,
                "discount=10000;shipping=0;total=90000"),
        new Example("VIP", 250_001,
                "discount=25000;shipping=0;total=225001"),
        new Example("STANDARD", 1_000_000,
                "discount=0;shipping=0;total=1000000")
    );

    private static void require(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static void verifyBehavior(String label, QuoteService service) {
        for (Example ex : EXAMPLES) {
            String actual = service.quote(ex.type(), ex.subtotal());
            require(ex.expected().equals(actual),
                    label + " mismatch at " + ex + "; actual=" + actual);
        }
        expectInvalid(() -> service.quote("VIP", -1));
        expectInvalid(() -> service.quote("STANDARD", 1_000_001));
        expectInvalid(() -> service.quote("UNKNOWN", 50_000));
        expectInvalid(() -> service.quote(null, 50_000));
    }

    interface Action {
        void run();
    }

    private static void expectInvalid(Action action) {
        try {
            action.run();
        } catch (IllegalArgumentException expected) {
            return;
        }
        throw new AssertionError("Expected IllegalArgumentException");
    }

    public static void main(String[] args) {
        QuoteService legacy = new LegacyQuoteService();
        QuoteService refactored =
                new RefactoredQuoteService(new PricingRules(), new QuoteFormatter());

        verifyBehavior("legacy", legacy);
        verifyBehavior("refactored", refactored);

        for (Example ex : EXAMPLES) {
            require(
                legacy.quote(ex.type(), ex.subtotal())
                    .equals(refactored.quote(ex.type(), ex.subtotal())),
                "Observable behavior changed at " + ex);
        }

        System.out.println("PASS: original business rules");
        System.out.println("PASS: refactored business rules");
        System.out.println("PASS: same public API and observable output");
        System.out.println(refactored.quote("VIP", 250_001));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DesignSmellsDemo.java
java DesignSmellsDemo
~~~

Đầu ra kỳ vọng:

~~~text
PASS: original business rules
PASS: refactored business rules
PASS: same public API and observable output
discount=25000;shipping=0;total=225001
~~~

Ở đây, **lợi ích thiết kế** nằm ở việc có thể kiểm thử và sửa `PricingRules` độc lập với `QuoteFormatter`, đồng thời giảm khả năng việc đổi cách trình bày vô tình tác động chính sách giá. `CustomerType` thay chuỗi tự do bằng enum ở tầng domain; API bên ngoài vẫn nhận chuỗi theo hợp đồng ban đầu.

**Nhận xét quan trọng:** Ví dụ cố ý nhỏ để có thể chạy độc lập. Không nên kết luận rằng mọi phương thức giống `LegacyQuoteService.quote` đều bắt buộc phải tách thành ba class. Hãy cân nhắc tần suất thay đổi và lợi ích kiểm thử trước khi tăng số lượng abstraction.

## 4. Nhận diện bằng luồng thay đổi: sửa ở đâu, tác động tới đâu?

Cùng quan sát một yêu cầu: “Tăng ngưỡng miễn phí vận chuyển từ 100.000 lên 120.000 cent”.

- Nếu chỉ thay một chính sách rõ ràng, có test cho các ngưỡng mới và không làm ảnh hưởng định dạng output, thiết kế có điểm tập trung trách nhiệm tốt.
- Nếu phải sửa cùng hằng số ở `CartController`, `CheckoutService`, `OrderConfirmationEmail` và `InvoiceExporter`, rất có thể tồn tại **Shotgun Surgery**. Cần kiểm tra chúng có dùng *cùng một quy tắc nghiệp vụ* hay không.
- Nếu phải sửa class vừa chứa công thức giá, logic lưu DB, gửi SMS và dựng HTML, có thể class đang chịu **Divergent Change**.
- Nếu thêm loại khách hàng luôn phải sửa các `switch` ở năm class, xem xét **polymorphism/Strategy** hoặc chuyển logic về một nơi thích hợp. Một `switch` duy nhất không nhất thiết là smell.

~~~mermaid
flowchart TD
    A["Phát hiện khó khăn khi sửa hoặc test"] --> B["Mô tả triệu chứng bằng ví dụ cụ thể"]
    B --> C["Xác định các lý do thay đổi và trách nhiệm"]
    C --> D{"Có bằng chứng về chi phí hoặc lỗi?"}
    D -->|Chưa| E["Theo dõi; tránh trừu tượng hóa vội"]
    D -->|Có| F["Đặt giả thuyết: lặp logic, coupling, cohesion..."]
    F --> G["Chọn phép refactor nhỏ nhất phù hợp"]
    G --> H["Chạy unit/contract/regression tests"]
    H --> I{"Hành vi còn đúng và code dễ thay đổi hơn?"}
    I -->|Không| J["Điều chỉnh hoặc hoàn tác bước vừa làm"]
    I -->|Có| K["Giữ thay đổi, ghi lại lý do thiết kế"]
~~~

## 5. Chọn phép tái cấu trúc tương ứng với nguyên nhân

| Vấn đề đã xác nhận | Kỹ thuật có thể phù hợp | Điểm cần cẩn thận |
|---|---|---|
| Một method gồm các nhóm thao tác rõ ý nghĩa | `Extract Method`, đổi tên theo ý định | Không tạo hàng loạt method chỉ gọi tiếp nhau mà không tăng độ rõ |
| Class trộn UI, nghiệp vụ, truy cập dữ liệu | `Extract Class`, phân lớp trách nhiệm | Giữ contract ở ranh giới, tránh tạo coupling vòng |
| Cùng quy tắc được sao chép | `Extract Function`, chuyển sang service/value object dùng chung | Chỉ hợp nhất khi thực sự cùng một quy tắc |
| Tham số miền chỉ là chuỗi/mã số dễ sai | `Replace Primitive with Object`, `enum`, `record` | Giữ khả năng serialize/deserialize và tương thích API |
| Nhánh phân loại lặp ở nhiều chỗ | `Replace Conditional with Polymorphism` hoặc Strategy | Đừng thêm hierarchy cho một điều kiện đơn giản, ổn định |
| Method thao tác nhiều vào dữ liệu class khác | `Move Method`, `Encapsulate Field` | Tránh phá encapsulation khi di chuyển |
| Ràng buộc tạo đối tượng gắn chặt với dependency | Constructor injection, interface ở ranh giới phù hợp | Không phải mọi class đều cần interface |
| Kế thừa chỉ để tái dùng vài dòng code | Chuyển sang composition hoặc delegate | Kiểm tra hành vi thay thế và compatibility trước khi bỏ kế thừa |
| Cờ boolean điều khiển hai hành vi khác nhau | `Replace Parameter with Explicit Methods` hoặc loại miền | Cân nhắc API dành cho client, không chỉ tên nội bộ |
| Nhiều getter/setter cho phép trạng thái sai | Đưa validation/bất biến vào entity/value object | Không biến object dữ liệu thuần thành class quá phức tạp |

**Cohesion (tính kết dính)**: các phần trong một class cùng phục vụ một trách nhiệm có ý nghĩa. **Coupling (sự phụ thuộc)**: mức độ module cần biết về nhau. Mục tiêu thường là tăng cohesion và giảm coupling không cần thiết, nhưng cũng phải cân bằng với độ phức tạp do thêm abstraction.

## 6. Bốn mức bằng chứng trước khi đề xuất refactor

### Mức 1: Dấu hiệu đọc code

Nhìn tên lớp, tên method, điều kiện lặp, field ít liên quan, số dependency; lập giả thuyết. Đây là bằng chứng ban đầu, **chưa đủ** để kết luận chi phí thiết kế.

### Mức 2: Thay đổi thật

Lấy một yêu cầu cụ thể và lần theo vùng ảnh hưởng: sửa bao nhiêu vị trí, lỗi phát sinh ở đâu, code review khó điều gì. Những vùng thường xuyên vừa **thay đổi** vừa **phức tạp** đáng ưu tiên xem xét hơn mã cũ ít khi đụng tới.

### Mức 3: Kiểm thử hành vi

Xác định input, expected output, loại ngoại lệ, trạng thái và side effect mà client quan sát. Viết test cho trường hợp thường, biên, lỗi và chuỗi thao tác. Có regression test rồi mới refactor khi thay đổi liên quan logic quan trọng.

### Mức 4: Đánh giá sau cải thiện

Một refactor có chất lượng khi những thay đổi tiếp theo dễ xác định vị trí hơn, test rõ hơn, logic ít trùng lặp hơn và không làm sai hợp đồng. Nếu kết quả chỉ là số class tăng lên, abstraction khó hiểu hơn, thì chưa có đủ cơ sở để coi đó là cải thiện.

Một vài metric có thể tham khảo: **cyclomatic complexity**, số dependency, mức lặp, các file thường sửa cùng nhau, thời gian sửa lỗi, số regression phát sinh. Không có một ngưỡng metric phổ quát áp dụng đúng cho mọi dự án.

## 7. Khi nào không nên refactor ngay?

- **Không có yêu cầu thay đổi, ít rủi ro và đoạn code đủ rõ:** ghi nhận, ưu tiên khu vực khác có tác động lớn hơn.
- **Code thiếu test và liên quan tiền bạc, dữ liệu hoặc quy trình quan trọng:** nên tạo characterization/contract tests trước, tránh refactor dựa trên phỏng đoán.
- **Chưa hiểu quy tắc nghiệp vụ:** hỏi người chịu trách nhiệm miền, làm rõ các trường hợp biên rồi mới chia class.
- **Đang trong một thay đổi sửa lỗi khẩn cấp:** có thể cô lập bản sửa và bổ sung regression test; refactor rộng cần scope riêng nếu làm tăng rủi ro.
- **Một abstraction chỉ có một implementation, ổn định và không đơn giản hóa test/đổi dependency:** cân nhắc dùng class cụ thể; interface không tự tạo ra thiết kế tốt.
- **Hai đoạn code giống nhau về cú pháp nhưng thay đổi độc lập:** gom lại có thể tạo coupling sai, khiến thay đổi ở miền A phá miền B.

**Technical debt** có thể dùng để diễn tả chi phí tương lai của thiết kế hiện tại; không nên mặc định mọi smell là nợ cần thanh toán ngay. Hãy xét tác động, xác suất phải thay đổi và chi phí sửa.

## 8. Checklist phân tích một class Java

Khi review một class, có thể đi theo trình tự:

1. **Mục đích:** Viết một câu mô tả trách nhiệm của class. Nếu cần nối nhiều cụm “và” không liên quan, xem lại cohesion.
2. **Ranh giới:** Client dùng những method nào? Có dựa vào chi tiết nội bộ, thứ tự lời gọi, trạng thái ẩn không?
3. **Thay đổi:** Nêu 2–3 yêu cầu gần đây sẽ buộc class sửa. Chúng có cùng một lý do không?
4. **Phụ thuộc:** Class tự tạo dependency và thao tác IO ở mọi method, hay dependency được quản lý theo ranh giới rõ?
5. **Biểu diễn miền:** Có thể truyền các giá trị không hợp lệ bằng `String`/`int`/nhiều boolean không? Nên dùng enum/value object không?
6. **Lặp:** Logic nghiệp vụ có xuất hiện nơi khác? Là quy tắc dùng chung hay chỉ tình cờ giống nhau?
7. **Kiểm thử:** Có thể nêu một input và expected output/exception rõ ràng? Test hiện có có bảo vệ thay đổi không?
8. **Quy mô sửa:** Phép refactor nhỏ nhất là gì, và làm sao chứng minh hành vi vẫn được giữ?

Một báo cáo code review hữu ích nên có dạng: **“Trong thay đổi X, chúng ta phải sửa cùng quy tắc ở A/B/C; đây là nguy cơ sai lệch. Đề nghị chuyển quy tắc chung vào Y và giữ các test ranh giới Z.”** Cách này cụ thể hơn nhận xét “code xấu, phải áp dụng SOLID”.

## 9. Sai lầm thường gặp

**Áp dụng SOLID như một danh sách phải hoàn thành.** SRP, OCP, LSP, ISP và DIP là nguyên tắc định hướng, không yêu cầu mỗi method hay mỗi class đều có interface. Hãy bắt đầu từ vấn đề thực tế rồi chọn nguyên tắc liên quan.

**Refactor và đổi nghiệp vụ cùng lúc nhưng không tách phạm vi.** Nếu yêu cầu giá mới làm expected output thay đổi, ghi rõ đó là sửa chức năng. Refactor thuần túy phải giữ nguyên hợp đồng quan sát được.

**Thay thế test kết quả bằng test chi tiết triển khai.** Test assert method private được gọi mấy lần sẽ hỏng khi chia class, dù đầu ra đúng. Ưu tiên public behavior; chỉ test tương tác khi bản thân nó là hợp đồng có ý nghĩa (ví dụ chỉ được gửi thông báo một lần).

**Chỉ đo complexity trước và sau.** Complexity giảm không đủ nếu API khó dùng hơn, thời gian xử lý tăng mạnh hoặc hệ thống phát sinh state không an toàn. Cần test và xem tác động lên công việc thật.

**Nhầm thêm lớp với tăng khả năng mở rộng.** Nhiều interface không có biến thể thực tế có thể làm logic bị rải rác. Trừu tượng tốt phải làm ý định và hướng thay đổi dễ hiểu hơn.

**Bỏ qua tính tương thích.** Khi chuyển `String` thành `enum` trong core, vẫn có thể cần adapter giữ dữ liệu JSON/API hoặc cơ sở dữ liệu hiện tại. Refactor nội bộ không mặc nhiên cho phép phá API công khai.

## 10. Bài tập tự đánh giá

**Bài 1 — Nhận dạng:** Class `ReportManager` có các method `loadFromDatabase()`, `calculateTax()`, `renderHtml()` và `sendEmail()`. Hãy nêu những lý do thay đổi độc lập, cho biết có thể là smell nào và đề xuất ranh giới class thích hợp. Đừng kết luận chỉ dựa vào tên; xét xem những method có luôn thay đổi cùng nhau không.

**Bài 2 — Shotgun Surgery:** Đổi mã VAT phải sửa cùng một bảng mã ở ba service. Xác định một nơi duy nhất quản lý quy tắc VAT, thiết kế test cho những trường hợp đang được sử dụng và giải thích vì sao thay đổi mới chỉ nên sửa ở đó.

**Bài 3 — Primitive Obsession:** Chữ ký `createAccount(String type, String status, int level, boolean active)` cho phép tổ hợp trạng thái mâu thuẫn. Đề xuất enum hoặc value object nhằm loại bỏ các trạng thái bất hợp lệ. Nêu một trường hợp mà không cần tạo thêm class.

**Bài 4 — Refactor an toàn:** Trong `DesignSmellsDemo`, đổi tên `PricingRules` và tách phương thức `shippingFor`. Chạy lại bài test để xác nhận output không đổi. Sau đó cố tình đổi điều kiện miễn phí từ `>=` sang `>` và chỉ ra ca test bắt được lỗi ở mức 100.000 cent.

**Bài 5 — Ưu tiên:** Có hai vùng mã: A dài 800 dòng nhưng 18 tháng không có thay đổi; B dài 150 dòng nhưng mỗi tuần được sửa và thường gây regression. Hãy chọn vùng cần đánh giá trước, mô tả dữ liệu nào cần thu thập và nêu khi nào lựa chọn có thể khác.

### Tiêu chí hoàn thành

Bạn có thể chỉ ra **một biểu hiện cụ thể**, giải thích **vì sao nó gây chi phí hoặc rủi ro**, tìm bằng chứng từ hành vi và lịch sử thay đổi, chọn một phép refactor có phạm vi rõ, và viết kiểm thử chứng minh hợp đồng Java vẫn đúng sau thay đổi. Nhận diện code smell là bước chẩn đoán; **cải thiện thiết kế phải được xác nhận bằng kết quả**, không chỉ bằng việc số dòng hoặc số class thay đổi.