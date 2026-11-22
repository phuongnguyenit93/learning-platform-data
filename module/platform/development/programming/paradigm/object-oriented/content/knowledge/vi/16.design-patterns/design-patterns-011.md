# Template Method trong Java: cố định khung thuật toán, tùy biến từng bước

> **Lộ trình:** OOP → Mẫu thiết kế → Template Method và khung thuật toán.  
> **Mục tiêu:** Hiểu Template Method là gì, biết xác định bước cố định và bước biến thiên, triển khai lớp cha cùng các lớp con trong Java, kiểm tra thứ tự thực thi, phân biệt với Strategy/Factory Method và nhận biết khi nào kế thừa gây thêm chi phí.

## 1. Template Method giải quyết vấn đề gì?

Trong nhiều chương trình, các tác vụ có **cùng quy trình tổng thể** nhưng khác ở một vài bước. Ví dụ, khi xuất báo cáo doanh thu:

1. Nhận và kiểm tra dữ liệu giao dịch.
2. Tính tổng doanh thu.
3. Tạo tiêu đề báo cáo.
4. Biểu diễn từng giao dịch.
5. Tạo dòng tổng kết.
6. Bổ sung nội dung cuối báo cáo nếu cần.

Báo cáo văn bản thuần và báo cáo Markdown đều phải thực hiện các bước này **đúng thứ tự**; chúng chỉ khác cách hiển thị tiêu đề, dòng giao dịch và tổng kết.

Nếu mỗi loại báo cáo có một phương thức `generate()` tự viết toàn bộ quá trình, phần kiểm tra dữ liệu, tính tổng và thứ tự xử lý dễ bị sao chép. Một phiên bản có thể quên kiểm tra tiền âm hoặc bỏ dòng tổng kết.

**Template Method** là mẫu thiết kế hành vi (*behavioral pattern*) theo GoF: định nghĩa **bộ khung của thuật toán trong một phương thức ở lớp cha**, đồng thời cho phép lớp con cài đặt hoặc ghi đè một số bước mà **không thay đổi cấu trúc chung của thuật toán**.

Cách đọc một thiết kế Template Method:

| Thành phần | Vai trò |
|---|---|
| **Abstract Class** | Lớp cha nắm quy trình và định nghĩa những bước mở rộng |
| **Template Method** | Phương thức điều phối thứ tự bước; thường đặt `final` để không bị ghi đè |
| **Concrete Operation** | Bước triển khai trọn vẹn tại lớp cha, dùng chung cho mọi biến thể |
| **Primitive Operation** | Bước `abstract` buộc subclass cung cấp |
| **Hook** | Bước có hành vi mặc định, subclass **có thể** ghi đè |
| **Concrete Class** | Lớp con triển khai những phần khác nhau theo từng biến thể |

Tên pattern đến từ **“mẫu quy trình”**, không phải “template” của generic type trong C++ hay một mẫu file giao diện.

## 2. Từ mã lặp đến một khung thống nhất

Một thiết kế ban đầu thường là hai class độc lập:

~~~java
// Phác thảo để thấy chỗ trùng lặp, không phải chương trình hoàn chỉnh.
class TextReport {
    String generate(List<Sale> sales) {
        validate(sales);
        BigDecimal total = calculateTotal(sales);
        // Render tiêu đề văn bản, từng dòng, tổng kết...
        return "...";
    }
}

class MarkdownReport {
    String generate(List<Sale> sales) {
        validate(sales);
        BigDecimal total = calculateTotal(sales);
        // Render tiêu đề Markdown, từng dòng, tổng kết...
        return "...";
    }
}
~~~

Hai lớp phải tự bảo đảm cùng thứ tự `validate → calculateTotal → render`. Khi nghiệp vụ thêm một bước chung, chẳng hạn kiểm tra ID giao dịch hợp lệ, cả hai có nguy cơ phải sửa.

Ý tưởng refactor:

- **Giữ trong lớp cha:** kiểm tra danh sách đầu vào, chụp snapshot, tính tổng, thứ tự các bước và trả kết quả.
- **Cho lớp con tùy biến:** nội dung tiêu đề, cách trình bày một giao dịch, cách trình bày tổng kết.
- **Dùng hook:** phần bổ sung cuối báo cáo có thể để trống hoặc được subclass định nghĩa.

Cơ chế này thường được diễn đạt bằng “**Hollywood Principle**”: *Don't call us, we'll call you*. Lớp cha quyết định khi nào gọi các bước do lớp con cung cấp; subclass không cần tự lắp lại toàn bộ luồng.

## 3. Ví dụ Java 17 đầy đủ: tạo báo cáo doanh thu

Ví dụ chỉ dùng JDK. Mỗi giao dịch có mã giao dịch và số tiền VND với hai chữ số thập phân **để đơn giản hóa bài học**; đây là quy ước của demo, không phải một phát biểu rằng VND bắt buộc có hai chữ số thập phân trong mọi hệ thống thực.

Hợp đồng đầu vào:

- Mã giao dịch chỉ chứa chữ `A–Z` viết hoa, chữ số hoặc dấu `-` để dễ biểu diễn an toàn trong văn bản/Markdown.
- Số tiền không âm, không null và biểu diễn được đến hai chữ số thập phân.
- Danh sách giao dịch không null; có thể rỗng. Không chấp nhận phần tử null.
- Lớp con chỉ làm nhiệm vụ **format**; không được sửa số tiền hoặc ngầm bỏ giao dịch.

Tạo tệp **`TemplateMethodDemo.java`** rồi chép toàn bộ đoạn sau:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

// Mỗi Sale là một value object bất biến.
// Compact constructor của record chuẩn hóa số tiền.
record Sale(String code, BigDecimal amount) {
    Sale {
        Objects.requireNonNull(code, "code");
        Objects.requireNonNull(amount, "amount");

        if (!code.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException(
                    "code must contain only A-Z, 0-9 or -");
        }
        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                    "amount must be nonnegative");
        }

        try {
            amount = amount.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "amount has fractions smaller than 0.01", ex);
        }
    }
}

// Abstract Class: chứa quy trình chung và các extension points.
abstract class SalesReportTemplate {

    // TEMPLATE METHOD: luồng xử lý cuối cùng của mọi biến thể.
    public final String generate(List<Sale> source) {
        Objects.requireNonNull(source, "source");

        // Snapshot; List.copyOf cũng từ chối phần tử null.
        List<Sale> sales = List.copyOf(source);

        // Concrete operation: cùng công thức tổng cho mọi báo cáo.
        BigDecimal total = sales.stream()
                .map(Sale::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add)
                .setScale(2, RoundingMode.UNNECESSARY);

        StringBuilder output = new StringBuilder();

        // Các primitive operations sẽ được dispatch tới subclass.
        output.append(Objects.requireNonNull(
                header(), "header returned null"));

        for (Sale sale : sales) {
            output.append(Objects.requireNonNull(
                    row(sale), "row returned null"));
        }

        output.append(Objects.requireNonNull(
                summary(sales.size(), total),
                "summary returned null"));

        // Hook tùy chọn: không yêu cầu mọi subclass tự viết lại.
        output.append(Objects.requireNonNull(
                footer(), "footer returned null"));

        return output.toString();
    }

    // Primitive operations: subclass bắt buộc cài đặt.
    protected abstract String header();
    protected abstract String row(Sale sale);
    protected abstract String summary(int count, BigDecimal total);

    // Hook: hành vi mặc định là không thêm phần cuối báo cáo.
    protected String footer() {
        return "";
    }
}

// Concrete Class A: định dạng văn bản thuần.
final class TextSalesReport extends SalesReportTemplate {
    @Override
    protected String header() {
        return "BÁO CÁO DOANH THU\n-----------------\n";
    }

    @Override
    protected String row(Sale sale) {
        return sale.code() + ": "
                + sale.amount().toPlainString() + " VND\n";
    }

    @Override
    protected String summary(int count, BigDecimal total) {
        return "Tổng " + count + " giao dịch: "
                + total.toPlainString() + " VND\n";
    }

    // Không ghi đè footer(): dùng hành vi mặc định của hook.
}

// Concrete Class B: định dạng bảng Markdown.
final class MarkdownSalesReport extends SalesReportTemplate {
    @Override
    protected String header() {
        return "| Mã giao dịch | Số tiền (VND) |\n"
                + "|---|---:|\n";
    }

    @Override
    protected String row(Sale sale) {
        return "| " + sale.code() + " | "
                + sale.amount().toPlainString() + " |\n";
    }

    @Override
    protected String summary(int count, BigDecimal total) {
        return "| **Tổng (" + count + ")** | **"
                + total.toPlainString() + "** |\n";
    }

    @Override
    protected String footer() {
        return "\n_Tự động tạo báo cáo._\n";
    }
}

public class TemplateMethodDemo {
    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("S-01", new BigDecimal("120.00")),
                new Sale("S-02", new BigDecimal("30.50"))
        );

        SalesReportTemplate textReport = new TextSalesReport();
        SalesReportTemplate markdownReport = new MarkdownSalesReport();

        System.out.println(textReport.generate(sales));
        System.out.println(markdownReport.generate(sales));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TemplateMethodDemo.java
java TemplateMethodDemo
~~~

Đầu ra:

~~~text
BÁO CÁO DOANH THU
-----------------
S-01: 120.00 VND
S-02: 30.50 VND
Tổng 2 giao dịch: 150.50 VND

| Mã giao dịch | Số tiền (VND) |
|---|---:|
| S-01 | 120.00 |
| S-02 | 30.50 |
| **Tổng (2)** | **150.50** |

_Tự động tạo báo cáo._
~~~

**Vì sao đúng mẫu Template Method?**

1. `SalesReportTemplate.generate()` sở hữu **thứ tự** các bước.
2. `generate()` là `final` nên subclass không thể ghi đè để bỏ tính tổng, đảo thứ tự hoặc quên bước chung.
3. `header()`, `row()` và `summary()` là các **primitive operations**: abstract, được gọi bởi template và được subclass triển khai.
4. `footer()` là **hook** có mặc định `""`. `TextSalesReport` không cần ghi đè; `MarkdownSalesReport` chọn bổ sung dòng chú thích.
5. `TextSalesReport`/`MarkdownSalesReport` chỉ quyết định **cách biểu diễn kết quả**, không điều khiển lại thuật toán.

Chú ý rằng `final` chỉ khóa việc override **phương thức template**, không tự động ngăn mọi lỗi subclass. Ví dụ, `row()` của một subclass vẫn có thể trả giá trị sai hoặc thực hiện tác dụng phụ không mong muốn. Hợp đồng và kiểm thử vẫn rất quan trọng.

## 4. Sơ đồ lớp và chuỗi thực thi

### 4.1. Cấu trúc lớp

~~~mermaid
classDiagram
    class SalesReportTemplate {
        <<abstract>>
        +generate(source) String
        #header() String*
        #row(sale) String*
        #summary(count,total) String*
        #footer() String
    }
    class TextSalesReport {
        #header() String
        #row(sale) String
        #summary(count,total) String
    }
    class MarkdownSalesReport {
        #header() String
        #row(sale) String
        #summary(count,total) String
        #footer() String
    }
    SalesReportTemplate <|-- TextSalesReport
    SalesReportTemplate <|-- MarkdownSalesReport
~~~

Dấu `*` trong sơ đồ đánh dấu các bước abstract. `generate()` trong Java ở ví dụ được khai báo `final`; sơ đồ chỉ tóm tắt danh sách phương thức.

### 4.2. Ai quyết định thứ tự?

~~~mermaid
sequenceDiagram
    actor Client
    participant Context as SalesReportTemplate
    participant Sub as Concrete Report
    Client->>Context: generate(sales)
    Note over Context: Snapshot danh sách + tính total
    Context->>Sub: header()
    Sub-->>Context: Văn bản tiêu đề
    loop Mỗi Sale
        Context->>Sub: row(sale)
        Sub-->>Context: Dòng đã format
    end
    Context->>Sub: summary(count, total)
    Sub-->>Context: Dòng tổng kết
    Context->>Sub: footer()
    Sub-->>Context: Nội dung hook hoặc chuỗi rỗng
    Context-->>Client: Chuỗi báo cáo hoàn chỉnh
~~~

Khi gọi `new MarkdownSalesReport().generate(...)`, trình tự vẫn bắt đầu trong phương thức kế thừa từ `SalesReportTemplate`. Chỉ từng bước ảo được JVM dispatch tới implementation của đối tượng thật.

## 5. Ba nhóm bước trong Template Method

Thiết kế tốt thường phân biệt **bước bất biến**, **bước bắt buộc thay đổi** và **bước tùy chọn**:

| Nhóm | Đặc điểm Java | Ví dụ | Cách dùng |
|---|---|---|---|
| **Bước chung** | `private` hoặc `final` method chứa logic đầy đủ | Snapshot, tính tổng, kiểm tra dữ liệu | Để ở lớp cha, không tạo điểm ghi đè nếu không cần |
| **Bước abstract** | `protected abstract` | `header()`, `row(...)`, `summary(...)` | Subclass phải cung cấp implementation |
| **Hook** | `protected` method có mặc định | `footer() { return ""; }` | Subclass chỉ override khi cần |
| **Template Method** | Thường `public final` | `generate(...)` | Điều phối các bước theo một thứ tự có chủ ý |

Từ “**thường**” quan trọng: GoF không bắt buộc mọi Template Method phải `final`. Java cho phép phương thức template không `final` và một số framework có chủ đích mở rộng cả quy trình. Tuy nhiên, nếu mục tiêu là **giữ nguyên khung thuật toán**, đánh dấu `final` giúp bảo vệ ý định thiết kế.

### 5.1. Hook dùng để làm gì?

Một hook là một điểm mở rộng **không bắt buộc**. Chẳng hạn, phần lớn báo cáo không cần footer, nhưng Markdown có thể thêm chú thích. Hook nên có hành vi mặc định an toàn, dễ hiểu, và không khiến lớp con buộc phải định nghĩa method rỗng.

Hook cũng có thể kiểm soát một quyết định:

~~~java
// Ví dụ minh họa, giả sử đặt trong một abstract class khác.
protected boolean shouldAddTimestamp() {
    return false;
}
~~~

Template Method có thể hỏi `shouldAddTimestamp()` tại điểm định trước. Cách này hợp lý khi chỉ có một tùy chọn nhỏ; nếu sinh ra hàng loạt hook liên thuộc, các tổ hợp override có thể trở nên khó dự đoán.

### 5.2. Có nên để subclass can thiệp vào dữ liệu chung?

Trong ví dụ, `row(Sale)` nhận một `record` bất biến. Subclass không thể sửa `Sale` tại chỗ, giúp bảo vệ dữ liệu nguồn. Nếu hook nhận một `List` có thể thay đổi, một subclass có thể xóa phần tử, sửa thứ tự hoặc ảnh hưởng bước tổng kết.

Do đó nên:

- Dùng tham số bất biến, value object, hoặc bản sao phù hợp.
- Phân biệt **mở rộng cách thể hiện** và **thay đổi quy tắc nghiệp vụ**.
- Công bố rõ hook nào được phép thay đổi gì, và điều gì phải giữ nguyên.
- Không đưa toàn bộ nội bộ của lớp cha ra `protected` chỉ để subclass có thể sử dụng: điều đó tăng coupling và làm refactor khó hơn.

## 6. Lỗi thiết kế dễ mắc

### Lỗi 1: mỗi subclass tự ghi đè toàn bộ template

~~~java
abstract class ImportTask {
    // Không final; mọi subclass đều có thể thay đổi thứ tự.
    public void execute() {
        validate();
        parse();
        save();
    }

    protected abstract void validate();
    protected abstract void parse();
    protected abstract void save();
}
~~~

Nếu mục đích là bắt buộc tuân thủ thứ tự `validate → parse → save`, có thể dùng `public final void execute()`. Nếu một subclass cần cố tình thay đổi thứ tự, đó có thể là dấu hiệu **khung thuật toán không thực sự ổn định**; xem lại abstraction thay vì sửa tùy tiện tại subclass.

### Lỗi 2: gọi phương thức có thể override trong constructor của lớp cha

~~~java
abstract class UnsafeBase {
    UnsafeBase() {
        configure(); // Nguy hiểm: dispatch tới subclass khi chưa khởi tạo xong.
    }
    protected abstract void configure();
}

final class UnsafeChild extends UnsafeBase {
    private final String prefix = "ready";

    @Override
    protected void configure() {
        System.out.println(prefix.length());
    }
}
~~~

Trong Java, constructor của lớp cha chạy **trước** khi field initializer của lớp con hoàn tất. `configure()` có thể chạy khi `prefix == null`, dẫn tới `NullPointerException`. Tránh gọi hook/abstract override từ constructor; hãy gọi template sau khi object đã khởi tạo đầy đủ, hoặc thiết kế factory xây dựng object xong mới bắt đầu xử lý.

### Lỗi 3: ép lớp con phải hỗ trợ những bước không hợp lý

Nếu một `ImportTask` có bước `decrypt()` nhưng nhiều nguồn không bao giờ được mã hóa, ép mọi subclass triển khai `decrypt() { throw new UnsupportedOperationException(); }` là dấu hiệu hợp đồng không phù hợp.

Tùy nghiệp vụ, có thể dùng hook mặc định an toàn, tách abstraction theo khả năng, hoặc truyền một bộ giải mã Strategy. Không dùng hook trống một cách máy móc nếu việc “không giải mã” tạo rủi ro bảo mật.

### Lỗi 4: tạo quá nhiều hook phụ thuộc thứ tự

Một framework tự viết với hàng chục method như `beforeValidate`, `afterValidate`, `beforeParse`, `afterParse`, `onError`, `finally...` rất khó hiểu khi subclass override nhiều vị trí. Template Method hữu ích nhất khi **khung thực sự ổn định** và chỉ một số ít bước cần thay thế.

### Lỗi 5: dùng kế thừa để xử lý mọi chiều biến thiên

Giả sử đồng thời có hai định dạng đầu ra (Text/Markdown), hai ngôn ngữ (VI/EN) và ba cách xuất (file/email/API). Nếu đưa tất cả vào hệ thống subclass, số tổ hợp tiềm năng là `2 × 2 × 3 = 12`, dễ dẫn tới bùng nổ lớp.

Khi có **nhiều trục thay đổi độc lập**, cân nhắc composition: `ReportFormatter`, `Translator`, `ReportPublisher` được inject riêng. Template Method vẫn có thể quản lý khung xử lý chung ở một tầng ổn định, nhưng từng biến thể có thể do các đối tượng cộng tác đảm nhiệm.

## 7. Template Method so với Strategy, Factory Method và các kỹ thuật khác

| Tiêu chí | Template Method | Strategy | Factory Method |
|---|---|---|---|
| Mục đích | Giữ **khung một thuật toán**, cho subclass thay vài bước | Thay **toàn bộ thuật toán/hành vi** bằng đối tượng cộng tác | Cho subclass quyết định **loại đối tượng được tạo** |
| Cơ chế chính | **Inheritance + dynamic dispatch** các bước override | **Composition + delegation** qua interface | **Inheritance + override** phương thức khởi tạo |
| Điểm biến thiên | Các bước trong quy trình lớp cha | Một implementation Strategy được truyền vào Context | Phương thức tạo một Product |
| Thay biến thể lúc chạy | Có thể đổi **đối tượng subclass**, nhưng không tự thay được cấu trúc quy trình bên trong cùng object | Thường dễ chọn/đổi Strategy thông qua DI hoặc parameter | Chọn Creator subclass hoặc dùng factory do Creator cung cấp |
| Lợi ích | Không lặp phần luồng chung; duy trì thứ tự xử lý | Giảm phụ thuộc vào thuật toán; linh hoạt chọn hành vi | Cô lập việc tạo sản phẩm khỏi logic xử lý |
| Rủi ro | Subclass coupling với lớp cha; hook quá nhiều | Nhiều Strategy nhỏ, cần cơ chế chọn | Nhiều Creator subclass chỉ để thay loại sản phẩm |

**Nhận diện nhanh bằng ví dụ:**

- `SalesReportTemplate.generate()` giữ `header → rows → summary → footer`: **Template Method**.
- `PricingService` nhận `PricingStrategy` và gọi `calculate(...)`: **Strategy**.
- `DocumentCreator` gọi `createDocument()` được subclass override để tạo `PdfDocument` hoặc `HtmlDocument`: **Factory Method**.

Một Template Method **có thể gọi Factory Method** ở một bước, ví dụ quy trình xuất tài liệu gọi `createRenderer()`; cũng có thể nhận Strategy để thực hiện một phần tính toán. Các pattern là công cụ phối hợp, không phải danh mục loại trừ nhau.

### Template Method hay Strategy cho một bài toán?

Dùng các câu hỏi:

1. Có một **thứ tự bước bắt buộc**, nhiều bước dùng chung và chỉ một số bước khác nhau? → **Template Method** đáng cân nhắc.
2. Có nhiều **thuật toán hoàn chỉnh** cần hoán đổi, đặc biệt ở runtime hoặc theo từng request? → **Strategy** thường linh hoạt hơn.
3. Có nhiều chiều biến thiên tương đối độc lập (định dạng, ngôn ngữ, đầu ra)? → Ưu tiên **composition** hoặc phối hợp Strategy với một quy trình chung.
4. Thứ tự xử lý hay hợp đồng có thể bị lớp con phá vỡ không? → Hạn chế extension point, ghi rõ precondition/postcondition, kiểm thử mọi subclass.

Kế thừa trong Template Method tạo liên kết khá chặt với lớp cha. Một thay đổi trong thứ tự hoặc ý nghĩa hook có thể ảnh hưởng tới nhiều subclass; ngược lại, Strategy cần thiết kế interface đủ rõ và thêm bước chọn/khởi tạo object.

## 8. Template Method khác một interface thông thường

Một interface chỉ khai báo các thao tác:

~~~java
interface Exporter {
    String export(List<Sale> sales);
}
~~~

Nếu mỗi implementation của `Exporter` tự quyết định toàn bộ quá trình, chưa có **khung thuật toán dùng chung** ở một lớp cha. Đây là polymorphism qua interface, nhưng tự nó **chưa đủ** để kết luận đang dùng Template Method.

Một `abstract class` chứa `final generate()` gọi các bước `protected abstract`/hook là cấu trúc đặc trưng. Trong Java, interface có `default` method, nhưng cơ chế extension và state khác abstract class; vẫn cần xem xét **ai thực sự sở hữu skeleton** chứ không chỉ nhìn từ khóa.

## 9. Kiểm thử đúng tính chất của Template Method

Trong ứng dụng thật, không chỉ kiểm tra kết quả cuối cùng mà còn cần xác nhận:

- **Thứ tự bước** không bị thay đổi.
- **Bước chung** được thực thi ở mọi subclass.
- Các subclass tạo đầu ra đúng định dạng theo hợp đồng.
- Hook mặc định hoạt động khi subclass không override.
- Dữ liệu biên (danh sách rỗng, null, số tiền không hợp lệ) được xử lý đúng.

Các test dưới đây dùng JUnit Jupiter 5; đặt `TemplateMethodDemo.java` vào source chính và `SalesReportTemplateTest.java` vào source kiểm thử cùng package, có dependency `junit-jupiter` và test runner phù hợp.

### 9.1. Test dữ liệu, tổng kết và hook

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;

class SalesReportTemplateTest {
    @Test
    void textAndMarkdownUseSameTotal() {
        List<Sale> sales = List.of(
                new Sale("S-01", new BigDecimal("120.00")),
                new Sale("S-02", new BigDecimal("30.50"))
        );

        String text = new TextSalesReport().generate(sales);
        String markdown = new MarkdownSalesReport().generate(sales);

        assertTrue(text.contains(
                "Tổng 2 giao dịch: 150.50 VND"));
        assertTrue(markdown.contains(
                "| **Tổng (2)** | **150.50** |"));

        // Hook mặc định không thêm chú thích; Markdown có override.
        assertFalse(text.contains("_Tự động tạo báo cáo._"));
        assertTrue(markdown.endsWith(
                "_Tự động tạo báo cáo._\n"));
    }

    @Test
    void emptyListStillGetsASummary() {
        String result = new TextSalesReport()
                .generate(List.of());

        assertTrue(result.contains(
                "Tổng 0 giao dịch: 0.00 VND"));
    }

    @Test
    void invalidSalesAreRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new Sale("BAD|ID", new BigDecimal("10.00")));
        assertThrows(IllegalArgumentException.class,
                () -> new Sale("S-01", new BigDecimal("-1.00")));
        assertThrows(IllegalArgumentException.class,
                () -> new Sale("S-01", new BigDecimal("1.005")));
        assertThrows(NullPointerException.class,
                () -> new TextSalesReport().generate(null));
    }
}
~~~

### 9.2. Test thứ tự các bước bằng một subclass ghi nhận lời gọi

Test này hữu ích khi sau này ai đó sửa template và vô tình đảo vị trí các bước:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class SalesReportOrderTest {
    static final class TracingReport extends SalesReportTemplate {
        final List<String> calls = new ArrayList<>();

        @Override
        protected String header() {
            calls.add("header");
            return "";
        }

        @Override
        protected String row(Sale sale) {
            calls.add("row:" + sale.code());
            return "";
        }

        @Override
        protected String summary(int count, BigDecimal total) {
            calls.add("summary:" + count);
            return "";
        }

        @Override
        protected String footer() {
            calls.add("footer");
            return "";
        }
    }

    @Test
    void templateControlsTheStepOrder() {
        TracingReport report = new TracingReport();

        report.generate(List.of(
                new Sale("S-01", new BigDecimal("20.00")),
                new Sale("S-02", new BigDecimal("15.00"))
        ));

        assertEquals(List.of(
                "header",
                "row:S-01",
                "row:S-02",
                "summary:2",
                "footer"
        ), report.calls);
    }
}
~~~

Lưu ý test về thứ tự chỉ chạy trên một subclass quan sát. Kiểm thử contract chung với tất cả subclass sản phẩm cũng cần thiết khi số biến thể tăng. Nếu một hook sinh tác dụng phụ thật (ghi DB, gửi mail), dùng fake dependency để tránh tạo tác động ngoài ý muốn trong unit test.

## 10. Khi dùng Template Method trong hệ thống thực

Một số trường hợp khung tương đối ổn định:

| Bài toán | Bước chung | Bước tùy biến |
|---|---|---|
| Nhập dữ liệu ETL | Kiểm tra → đọc → chuyển đổi → lưu → tổng kết | Parse CSV/XML, chuẩn hóa từng loại bản ghi |
| Xuất báo cáo | Lấy dữ liệu → tổng hợp → trình bày → xuất | Header, định dạng dòng, footer |
| Chạy tác vụ batch | Khởi tạo → xử lý từng item → cập nhật trạng thái → kết thúc | Xử lý mỗi item, hook trước/sau batch |
| Xử lý tài liệu | Kiểm tra quyền → đọc nội dung → biến đổi → ghi ra | Cách biến đổi/renderer |
| Mẫu kiểm thử cơ sở | Setup chung → thực thi kịch bản → xác nhận chung → cleanup | Dữ liệu fixture, bước thực thi riêng |

Đối với ví dụ **ETL**, có một điểm cần làm rõ: template chỉ cố định thứ tự **không có nghĩa tự bảo đảm giao dịch nguyên tử**. Nếu lưu nhiều bản ghi rồi có lỗi giữa chừng, kết quả có thể là ghi dở; cần transaction, rollback hoặc thiết kế idempotent tùy yêu cầu. Đừng gán năng lực của framework giao dịch cho pattern.

### Checklist thiết kế khung thuật toán

1. Viết **tên và thứ tự** các bước trước khi tạo abstract class. Chỉ phần thật sự bất biến mới vào template.
2. Mô tả **hợp đồng của từng extension point**: đầu vào, kết quả, ngoại lệ và tác dụng phụ được phép.
3. Để phương thức template `final` nếu subclass không được sửa khung.
4. Sử dụng `protected abstract` cho bước bắt buộc; hook có mặc định an toàn cho bước tùy chọn.
5. Giữ validation, bảo vệ trạng thái và quy tắc chung ở lớp cha.
6. Tránh gọi override trong constructor và tránh cho subclass can thiệp tự do vào dữ liệu mutable.
7. Viết test cho **thứ tự gọi, bước chung, kết quả và các biến thể**, kể cả dữ liệu biên.
8. Nếu các biến thể tăng theo nhiều chiều độc lập, đánh giá lại inheritance và chuyển một phần sang Strategy/composition.

## 11. Bài tập thực hành: khung xử lý file nhập sản phẩm

Một hệ thống nhận file sản phẩm từ đối tác theo hai định dạng giả định: `CSV-SIMPLE` và `PIPE-SIMPLE`. Mỗi dòng chứa mã hàng và số lượng, nhưng cách tách trường khác nhau.

Hãy thiết kế:

~~~java
abstract class ProductImportTemplate {
    public final int importText(String raw) {
        // 1. validate raw
        // 2. parseRecords(raw) - abstract
        // 3. validate từng Product
        // 4. persistAll(records) - bước chung
        // 5. afterImport(count) - hook tùy chọn
        // 6. return count
        throw new UnsupportedOperationException("Exercise");
    }

    protected abstract List<Product> parseRecords(String raw);

    protected void afterImport(int count) {
        // mặc định không làm gì
    }
}
~~~

Đây chỉ là **skeleton bài tập**, không phải một implementation hoàn chỉnh; người học cần định nghĩa `Product`, `persistAll` và xử lý lỗi cho đúng.

Yêu cầu bài tập:

- Viết hai subclass `CsvProductImport` và `PipeProductImport`.
- Lớp cha kiểm tra số lượng > 0 trước khi lưu.
- Không cho subclass ghi đè `importText` để bỏ validation.
- Viết test xác minh khi parse hoặc validate thất bại thì **chưa gọi bước lưu**.
- Nếu cần bảo đảm toàn bộ file được lưu hoặc toàn bộ bị hủy, chỉ rõ nơi bắt đầu/kết thúc transaction trong thiết kế của bạn.
- Thảo luận lúc nào thêm một `RecordParser` interface và dùng Strategy lại hợp lý hơn subclass theo định dạng.

### Câu hỏi tự kiểm tra

1. Phương thức nào trong ví dụ báo cáo là **Template Method**? Vì sao dùng `final`?
2. `header()` là primitive operation hay hook? `footer()` là gì?
3. Nếu Text và Markdown dùng **khác công thức tính tổng doanh thu**, việc thay riêng bước format đã còn đủ không? Cần thay đổi abstraction nào?
4. Vì sao gọi một method có thể override từ constructor của abstract class có thể gây `NullPointerException`?
5. Đổi thuật toán tính giá theo từng HTTP request nên cân nhắc Strategy hay tạo một subclass Template Method cho từng request? Vì sao?
6. Abstract class dùng chung data validation có tự động là Template Method nếu không có phương thức điều phối skeleton không?

**Điều cần nhớ:** Template Method để **lớp cha giữ quyền điều phối một quy trình ổn định**, còn lớp con chỉ **cài đặt những bước được cho phép thay đổi**. Sự rõ ràng về ranh giới giữa bước cố định, abstract step và hook mới là giá trị chính của pattern; không phải cứ dùng `abstract class` là đã áp dụng Template Method.