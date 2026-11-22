# Truy nguyên nguồn gốc và biến đổi của dữ liệu

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích **truy nguyên dữ liệu (data lineage)** và **nguồn gốc dữ liệu (data provenance)** có vai trò gì đối với tính đúng đắn, độ tin cậy và khả năng bảo trì mã nguồn.
2. Mô tả hành trình từ **nguồn đầu vào**, qua các bước **kiểm tra, chuẩn hóa, tính toán, kết hợp**, đến **đầu ra và nơi lưu trữ**.
3. Phân biệt nguồn dữ liệu, phiên bản quy tắc biến đổi, lịch sử thay đổi, log ứng dụng và trace của một yêu cầu.
4. Thiết kế một đoạn Java có khả năng truy từ kết quả tính toán về dữ liệu nguồn và quy tắc đã áp dụng.
5. Đặt câu hỏi, viết kiểm thử và lựa chọn metadata phù hợp để tìm được nguyên nhân khi giá trị ở đầu ra bị sai.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Khả năng truy nguyên dữ liệu liên quan trực tiếp đến các thuộc tính ấy: khi một kết quả bất ngờ xuất hiện, người bảo trì cần biết **giá trị đến từ đâu, đã đi qua những bước nào và quy tắc nào khiến nó có hình dạng hiện tại**.

Một chương trình có thể trả về một con số đúng trong vài bài kiểm thử nhưng vẫn khó tin cậy nếu không giải thích được con số đó khi dữ liệu thật thay đổi. Mục tiêu của bài này là xây dựng thói quen thiết kế các đường đi của dữ liệu **có thể hiểu, kiểm chứng và điều tra**.

## 1. Vì sao cần truy nguyên dữ liệu?

Giả sử trang quản trị hiển thị **tổng tiền đơn hàng là 480.000 đồng**, nhưng khách hàng khẳng định đã mua hai sản phẩm, mỗi sản phẩm 250.000 đồng. Một câu hỏi đơn giản “Vì sao tổng tiền khác 500.000 đồng?” có thể đòi hỏi kiểm tra nhiều khả năng:

- Giá từ màn hình đặt hàng là giá đã giảm hay giá gốc?
- Số lượng từ client có được đọc và kiểm tra đúng không?
- Đơn giá đã được đổi từ chuỗi sang kiểu số theo quy ước nào?
- Hệ thống có áp dụng khuyến mại, thuế hoặc phí vận chuyển không?
- Dữ liệu được lấy từ bảng giá hiện tại hay bảng giá tại thời điểm đặt hàng?
- Có chương trình nền nào sửa đơn hàng sau khi tạo không?
- API lấy kết quả từ bản ghi gốc, bảng tổng hợp hay cache chưa được cập nhật?

Nếu chỉ nhìn một phương thức **calculateTotal()**, ta không chắc trả lời được. Cần nhìn **đường đi của dữ liệu** xuyên qua những bước tạo, chuyển đổi, lưu trữ và sử dụng.

~~~mermaid
flowchart LR
    A[Nguồn đơn hàng] --> B[Kiểm tra đầu vào]
    B --> C[Chuẩn hóa dữ liệu]
    C --> D[Tra cứu bảng giá]
    D --> E[Áp dụng quy tắc tính tiền]
    E --> F[Lưu kết quả]
    F --> G[API báo cáo]
    G --> H[Giao diện người dùng]
~~~

Mỗi mũi tên là một giả định cần kiểm chứng: **dữ liệu nào được truyền đi, thuộc phiên bản nào, có thể bị đổi nghĩa hay mất thông tin ở đâu**. Khi hệ thống có nhiều lớp hoặc dịch vụ, những giả định ngầm thường là nguồn lỗi khó phát hiện.

### Truy nguyên dữ liệu giúp được gì?

| Nhu cầu | Câu hỏi cần trả lời | Lợi ích đối với mã nguồn |
| --- | --- | --- |
| Điều tra lỗi | Giá trị sai được tạo ra ở bước nào? | Thu hẹp phạm vi debug, tránh sửa mò |
| Đánh giá thay đổi | Quy tắc mới sẽ ảnh hưởng những đầu ra nào? | Dự đoán tác động và chọn test hồi quy |
| Kiểm tra nghiệp vụ | Kết quả có dùng đúng dữ liệu và phiên bản chính sách? | Tăng tính đúng đắn và khả năng giải thích |
| Phát hiện dữ liệu bất thường | Giá trị nào thiếu, trùng, đổi đơn vị hoặc sai định dạng? | Phát hiện sai lệch sớm ở ranh giới |
| Vận hành và hỗ trợ | Kết quả nào liên quan đến sự kiện nguồn hoặc lần xử lý nào? | Rút ngắn thời gian xác định nguyên nhân |
| Kiểm toán hoặc đối soát | Có bằng chứng về nguồn và cách tạo kết quả không? | Hỗ trợ truy vết theo yêu cầu nghiệp vụ và chính sách dữ liệu |

**Truy nguyên không tự bảo đảm dữ liệu đúng.** Nếu dữ liệu nguồn đã sai hoặc quy tắc nghiệp vụ được mô tả sai, một chuỗi xử lý được ghi nhận đầy đủ vẫn có thể tạo kết quả sai. Điểm mạnh của truy nguyên là làm cho lỗi **có thể giải thích và kiểm tra**.

## 2. Phân biệt các khái niệm gần nhau

### 2.1. Data lineage: đường đi và các phép biến đổi

**Data lineage** là thông tin cho biết một dữ liệu đầu ra được tạo nên từ những nguồn nào, đã đi qua những hệ thống hay bước biến đổi nào và phụ thuộc vào những quy tắc nào.

Ví dụ: cột **total_amount** ở báo cáo doanh thu được tạo từ **order_items.unit_price**, **order_items.quantity**, bảng chiết khấu tại thời điểm giao dịch và quy tắc tổng hợp theo ngày. Đây là quan hệ **nguồn → biến đổi → đích**.

Có nhiều mức chi tiết:

- **Mức hệ thống:** thông tin đi từ dịch vụ đơn hàng sang kho dữ liệu và báo cáo.
- **Mức bảng hoặc tập dữ liệu:** báo cáo doanh thu phụ thuộc vào những bảng hoặc topic nào.
- **Mức cột:** cột tổng tiền đến từ đơn giá, số lượng và các điều chỉnh nào.
- **Mức bản ghi hoặc giá trị:** kết quả cụ thể của đơn hàng **O-123** được tính từ những dòng hàng nào.

Không phải hệ thống nào cũng cần mức chi tiết cao nhất. Càng chi tiết, chi phí ghi nhận, lưu trữ và bảo vệ thông tin càng lớn.

### 2.2. Data provenance: căn cứ về nguồn gốc

**Data provenance** nhấn mạnh **nguồn tạo hoặc cung cấp dữ liệu và những bằng chứng liên quan**: sự kiện nguồn, mã bản ghi, nguồn tích hợp, thời điểm tiếp nhận hoặc phiên bản tập dữ liệu.

Ví dụ, một dòng đơn hàng có thể mang thông tin: “đến từ hệ thống POS, bản ghi ngoài số 9821, nhận lúc 10:15 UTC, theo schema v2”. Những metadata này giúp xác định nguồn cần kiểm tra khi kết quả bất thường.

Trong thực tế hai thuật ngữ *lineage* và *provenance* có vùng giao nhau và được dùng khác nhau giữa các công cụ. Trong bài này, dùng cách phân biệt thực dụng: **provenance nói nhiều hơn về căn cứ nguồn**, còn **lineage mô tả thêm đường đi và phép biến đổi**.

### 2.3. Audit trail, log và distributed tracing không hoàn toàn giống lineage

| Khái niệm | Ghi nhận chủ yếu | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **Data lineage** | Phụ thuộc từ nguồn tới kết quả, các bước biến đổi | Cột báo cáo sinh từ hai bảng và công thức nào | Không nhất thiết ghi danh tính người sửa |
| **Data provenance** | Nguồn và căn cứ xuất xứ | Event ID, nguồn POS, phiên bản dữ liệu | Không tự mô tả đầy đủ mọi phép biến đổi |
| **Audit trail** | Ai hoặc thành phần nào thực hiện thay đổi, khi nào, trước/sau theo chính sách | Nhân viên cập nhật địa chỉ lúc 14:20 | Có thể không ghi đủ nguồn của giá trị tính toán |
| **Application log** | Sự kiện vận hành và chẩn đoán | “parse price failed” | Có thể bị thiếu, bị lấy mẫu và không phải sổ cái tin cậy |
| **Distributed trace** | Chuỗi lời gọi và thời gian giữa các service trong một lần xử lý | Request X đi qua gateway, order và pricing | Không nhất thiết chứa phụ thuộc giá trị hoặc lịch sử dữ liệu lâu dài |

Một **traceId** giúp tìm luồng xử lý; **sourceRecordId** giúp tìm bản ghi gốc; **ruleVersion** giúp hiểu logic đã áp dụng. Kết hợp các mã này có thể rất hữu ích, nhưng chúng có **ý nghĩa khác nhau** và không thay thế cho nhau.

## 3. Một hành trình dữ liệu điển hình

Hãy xét một đơn hàng từ hệ thống bên ngoài. Đường đi hợp lý thường gồm:

1. **Tiếp nhận:** đọc payload từ API, hàng đợi hoặc file. Xác định nguồn tích hợp và mã sự kiện/bản ghi theo hợp đồng.
2. **Kiểm tra:** xác định trường bắt buộc, kiểu dữ liệu, giới hạn miền giá trị, đơn vị, định dạng và quyền của nguồn gửi.
3. **Chuẩn hóa:** chuyển dữ liệu sang biểu diễn nội bộ có hợp đồng thống nhất, chẳng hạn mã SKU, mã tiền tệ, thời gian và kiểu số.
4. **Làm giàu:** ghép với dữ liệu tham chiếu như bảng giá, thông tin sản phẩm hoặc chính sách khách hàng.
5. **Biến đổi nghiệp vụ:** tính tổng, thuế, giảm giá, phí hoặc trạng thái theo phiên bản quy tắc.
6. **Lưu và phát hành:** ghi dữ liệu, tạo sự kiện hoặc cập nhật bảng tổng hợp mà các thành phần khác sẽ sử dụng.
7. **Trình bày:** định dạng giá trị cho API, báo cáo, giao diện hoặc hệ thống downstream.

### Những thông tin nên biết ở từng bước

| Bước | Đầu vào cần biết | Đầu ra nên được xác định | Lỗi thường gặp |
| --- | --- | --- | --- |
| Tiếp nhận | Nguồn, ID sự kiện, thời điểm phát/nhận | Bản ghi thô được nhận diện | Nhầm nguồn, xử lý trùng sự kiện |
| Kiểm tra | Schema, đơn vị, trường bắt buộc | Dữ liệu hợp lệ hoặc lỗi có lý do | Chấp nhận giá âm, định dạng không rõ |
| Chuẩn hóa | Quy ước mã, ngày giờ, tiền tệ | Mô hình nội bộ nhất quán | Cắt mất ký tự có ý nghĩa; đổi đơn vị sai |
| Làm giàu | Khóa tra cứu, phiên bản dữ liệu tham chiếu | Kết quả ghép và căn cứ tra cứu | Join sai khóa, tra giá hiện tại thay giá lịch sử |
| Tính toán | Quy tắc, tham số, phiên bản chính sách | Giá trị kết quả có đơn vị và ý nghĩa rõ | Điều kiện biên, làm tròn, thứ tự phép tính |
| Lưu trữ | ID nghiệp vụ, trạng thái, quy định đồng thời | Bản ghi tồn tại và có thể tra cứu | Ghi đè, mất lịch sử, retry tạo trùng |
| Báo cáo | Định nghĩa chỉ số, khoảng thời gian | Giá trị và phạm vi báo cáo | Dùng sai múi giờ hoặc lọc thiếu trạng thái |

Điểm quan trọng là mỗi bước nên có **ranh giới ý nghĩa**: người đọc nhận ra bước nào chỉ diễn giải dữ liệu đầu vào và bước nào thực sự thay đổi giá trị theo nghiệp vụ.

## 4. Dữ liệu thô, dữ liệu chuẩn hóa và kết quả không phải cùng một thứ

Một lỗi thiết kế hay gặp là dùng một đối tượng mutable duy nhất xuyên qua nhiều giai đoạn:

~~~java
// Minh họa kiểu thiết kế dễ làm mất thông tin.
class OrderLineData {
    String sku;
    String price;
    int quantity;
    String source;
}

// Bước A: gán sku = trim(sku)
// Bước B: đổi price sang một chuỗi đã làm tròn
// Bước C: ghi đè source bằng tên hệ thống hiện tại
~~~

Sau các bước trên, rất khó xác định:

- **sku** ban đầu có khoảng trắng hoặc chữ thường không?
- **price** được gửi ở định dạng và đơn vị nào?
- **source** nói tới bên gửi dữ liệu hay thành phần vừa biến đổi?
- Sự thay đổi nào là **chuẩn hóa hợp lệ**, sự thay đổi nào là **mất dữ liệu**?

Để tránh trộn các ý nghĩa, có thể dùng những kiểu dữ liệu riêng ở từng giai đoạn:

~~~text
RawLine
  └── normalize / validate ──> NormalizedLine
                                └── calculate ──> PricedLine
                                                   └── persist ──> StoredLine
~~~

Các kiểu này không nhất thiết phải tồn tại ở mọi hệ thống. Nếu phép biến đổi rất đơn giản, tạo quá nhiều DTO có thể làm mã rườm rà. Nhưng khi dữ liệu có **hợp đồng hoặc đơn vị khác nhau trước và sau biến đổi**, dùng kiểu riêng giúp người đọc tránh nhầm lẫn và giúp test đúng giai đoạn.

### Mẫu hình có ích

- **Đầu vào không tin cậy:** dữ liệu ngoài hệ thống cần kiểm tra trước khi vào mô hình nghiệp vụ.
- **Biến đổi thuần:** hàm nhận dữ liệu, tạo kết quả mới, không tự gọi I/O hay âm thầm thay đổi dữ liệu đầu vào.
- **Đối tượng bất biến:** lưu thông tin giá trị và căn cứ nguồn tại thời điểm tạo, hạn chế bị sửa không chủ đích.
- **Quy tắc có phiên bản:** biết kết quả được tính theo phiên bản nào khi chính sách thay đổi.
- **Nơi sở hữu rõ ràng:** tránh cùng một phép chuẩn hóa hoặc tính toán bị triển khai khác nhau ở nhiều nơi.

## 5. Ví dụ Java: theo dõi một dòng hàng từ nguồn tới thành tiền

Giả sử hệ thống nhập dòng hàng từ một nguồn tích hợp đáng tin cậy. Payload bên ngoài chứa:

- Hệ thống nguồn và ID của dòng hàng ở hệ thống đó.
- Mã sản phẩm có thể có khoảng trắng hoặc chữ thường.
- Đơn giá dưới dạng chuỗi ký tự, đơn vị **VND**.
- Số lượng nguyên dương.

Quy tắc minh họa: **SKU không phân biệt chữ hoa/thường, được chuẩn hóa thành chữ hoa; đơn giá VND không có phần lẻ; thành tiền = đơn giá × số lượng**. Các quy tắc này là giả định học tập, phải được xác nhận theo hợp đồng của hệ thống thật. Đặc biệt, không nên tự động chuyển chữ hoa khi mã sản phẩm thực tế có phân biệt hoa/thường.

### 5.1. Mô hình dữ liệu và hàm biến đổi

~~~java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Objects;

public final class OrderLineLineage {
    private static final String RULE_VERSION = "LINE_TOTAL_V1";

    private OrderLineLineage() {
    }

    public record SourceRef(String system, String externalLineId) {
        public SourceRef {
            Objects.requireNonNull(system, "system");
            Objects.requireNonNull(externalLineId, "externalLineId");
            if (system.isBlank() || externalLineId.isBlank()) {
                throw new IllegalArgumentException("source reference is blank");
            }
        }
    }

    // Giữ nguyên cách bên gửi biểu diễn giá và mã hàng.
    public record RawLine(
            SourceRef source,
            String rawSku,
            String rawUnitPriceVnd,
            int quantity) {
        public RawLine {
            Objects.requireNonNull(source, "source");
        }
    }

    // Mô hình nội bộ sau khi đã xác minh và chuẩn hóa.
    public record NormalizedLine(
            SourceRef source,
            String sku,
            BigDecimal unitPriceVnd,
            int quantity) {
        public NormalizedLine {
            Objects.requireNonNull(source, "source");
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPriceVnd, "unitPriceVnd");
            if (sku.isBlank()
                    || quantity <= 0
                    || unitPriceVnd.signum() < 0
                    || unitPriceVnd.stripTrailingZeros().scale() > 0) {
                throw new IllegalArgumentException("invalid normalized line");
            }
        }
    }

    // Kết quả có căn cứ nguồn và phiên bản công thức.
    public record PricedLine(
            SourceRef source,
            String sku,
            BigDecimal lineTotalVnd,
            String ruleVersion) {
        public PricedLine {
            Objects.requireNonNull(source, "source");
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(lineTotalVnd, "lineTotalVnd");
            Objects.requireNonNull(ruleVersion, "ruleVersion");
            if (sku.isBlank() || ruleVersion.isBlank()
                    || lineTotalVnd.signum() < 0) {
                throw new IllegalArgumentException("invalid priced line");
            }
        }
    }

    public static NormalizedLine normalize(RawLine raw) {
        Objects.requireNonNull(raw, "raw");
        String sku = Objects.requireNonNull(raw.rawSku(), "rawSku")
                .trim().toUpperCase(Locale.ROOT);

        String rawPrice = Objects.requireNonNull(
                raw.rawUnitPriceVnd(), "rawUnitPriceVnd").trim();
        BigDecimal price;
        try {
            price = new BigDecimal(rawPrice);
        } catch (NumberFormatException error) {
            throw new IllegalArgumentException(
                    "unit price is not a decimal number", error);
        }

        return new NormalizedLine(
                raw.source(), sku, price, raw.quantity());
    }

    public static PricedLine calculate(NormalizedLine line) {
        Objects.requireNonNull(line, "line");
        BigDecimal total = line.unitPriceVnd()
                .multiply(BigDecimal.valueOf(line.quantity()));
        return new PricedLine(
                line.source(), line.sku(), total, RULE_VERSION);
    }

    public static void main(String[] args) {
        var input = new RawLine(
                new SourceRef("POS", "line-9821"),
                " sku-01 ", "50000", 2);

        var normalized = normalize(input);
        var priced = calculate(normalized);

        System.out.println(normalized.sku());       // SKU-01
        System.out.println(priced.lineTotalVnd());    // 100000
        System.out.println(priced.source());          // SourceRef[...]
        System.out.println(priced.ruleVersion());     // LINE_TOTAL_V1
    }
}
~~~

Ví dụ sử dụng **record** của Java 17. Dữ liệu **SourceRef** trong ví dụ được giả định do **thành phần tiếp nhận tin cậy** gán sau khi xác minh nguồn tích hợp; không nên coi tên nguồn tự khai báo trong payload không xác thực là bằng chứng xuất xứ đáng tin.

Mô hình trên mang một thông tin có ích từ đầu tới cuối: **PricedLine** biết mình bắt nguồn từ dòng nào. Nó cũng biết kết quả áp dụng **LINE_TOTAL_V1**. Người điều tra có thể dùng mã dòng nguồn để tìm payload đã nhận, rồi tái kiểm tra phép chuẩn hóa và tính toán.

### 5.2. Điều gì đã cải thiện?

- **Nguồn được mang theo qua phép biến đổi:** không đánh mất tham chiếu khi chuyển từ RawLine sang NormalizedLine và PricedLine.
- **Mỗi giai đoạn có hợp đồng riêng:** RawLine là dữ liệu bên ngoài; NormalizedLine bảo đảm các bất biến về mã, số lượng và giá; PricedLine bảo đảm giá trị kết quả không âm.
- **Chuẩn hóa có tên rõ:** người đọc biết mã được cắt khoảng trắng và chuyển chữ hoa tại bước nào.
- **Quy tắc tính toán có phiên bản:** khi nâng chính sách, có thể phân biệt kết quả lịch sử với kết quả mới.
- **Hàm dễ kiểm thử:** normalize và calculate không tự đọc database hay gọi mạng.

Cần lưu ý **record không bảo đảm bất biến sâu** nếu bên trong chứa danh sách hoặc đối tượng mutable. Ở ví dụ, các trường được dùng là chuỗi, số, BigDecimal và record khác có các trường bất biến nên phù hợp để minh họa. Với danh sách, bản đồ hoặc đối tượng thay đổi được, cần sao chép phòng vệ hoặc định nghĩa quyền sở hữu dữ liệu.

### 5.3. Giới hạn của ví dụ

Đoạn mã chỉ xử lý **một dòng hàng** và **một công thức đơn giản**. Nó chưa giải quyết:

- Dữ liệu nguồn được lưu bền vững thế nào và trong bao lâu.
- Hệ thống nhận lại cùng sự kiện nhiều lần có tạo bản ghi trùng không.
- Một SKU đã chuẩn hóa được ánh xạ tới sản phẩm nội bộ nào.
- Giá lấy từ nguồn có đúng theo chính sách giá tại thời điểm đặt hàng không.
- Thuế, khuyến mại, phí vận chuyển, làm tròn và nhiều loại tiền tệ.
- Các trường hợp nhiều dòng hàng cùng tham gia tạo một kết quả tổng hợp.
- Quy tắc bảo mật và lưu giữ dữ liệu của nguồn.

Những vấn đề này thuộc bối cảnh nghiệp vụ và hạ tầng; cần được thiết kế khi triển khai thật. **Mang theo source ID và ruleVersion là một điểm khởi đầu**, không tự tạo nên hệ thống truy nguyên hoàn chỉnh.

## 6. Kiểm thử khả năng truy nguyên và biến đổi

Test không chỉ xác nhận số tiền cuối cùng; cần kiểm tra những thuộc tính giúp chứng minh kết quả được tạo đúng cách.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderLineLineageTest {
    private static final OrderLineLineage.SourceRef SOURCE =
            new OrderLineLineage.SourceRef("POS", "line-9821");

    @Test
    void normalizesSkuAndPreservesSource() {
        var raw = new OrderLineLineage.RawLine(
                SOURCE, " sku-01 ", "50000", 2);

        var normalized = OrderLineLineage.normalize(raw);

        assertEquals("SKU-01", normalized.sku());
        assertEquals(SOURCE, normalized.source());
        assertEquals(" sku-01 ", raw.rawSku());
    }

    @Test
    void calculatesTotalAndRecordsRuleVersion() {
        var normalized = OrderLineLineage.normalize(
                new OrderLineLineage.RawLine(
                        SOURCE, "sku-01", "50000", 2));

        var result = OrderLineLineage.calculate(normalized);

        assertEquals(new BigDecimal("100000"), result.lineTotalVnd());
        assertEquals(SOURCE, result.source());
        assertEquals("LINE_TOTAL_V1", result.ruleVersion());
    }

    @Test
    void rejectsInvalidSourcePriceInsteadOfReplacingItWithZero() {
        var raw = new OrderLineLineage.RawLine(
                SOURCE, "sku-01", "khong-phai-so", 2);

        assertThrows(IllegalArgumentException.class,
                () -> OrderLineLineage.normalize(raw));
    }

    @Test
    void rejectsFractionalPriceForThisVndContract() {
        var raw = new OrderLineLineage.RawLine(
                SOURCE, "sku-01", "1000.25", 1);

        assertThrows(IllegalArgumentException.class,
                () -> OrderLineLineage.normalize(raw));
    }
}
~~~

Ở ví dụ này, test không chỉ kiểm tra giá trị **100000**, mà còn kiểm tra **nguồn còn được giữ**, **quy tắc có phiên bản**, **dữ liệu đầu vào không bị sửa** và **lỗi được báo rõ**. Đây là các bảo đảm quan trọng khi cần tìm nguyên nhân một kết quả sai.

Một số tình huống nên thêm vào trong hệ thống thật: giá âm, số lượng bằng 0, giá trị quá lớn, mã sản phẩm rỗng, nguồn sự kiện thiếu ID, xử lý sự kiện lặp, phiên bản schema thay đổi, quy tắc mới tạo khác biệt trên dữ liệu lịch sử.

**Không nên thay dữ liệu lỗi bằng giá trị mặc định vô hại một cách im lặng.** Ví dụ, bắt lỗi parse giá rồi đặt **price = 0** có thể khiến đơn hàng hợp lệ giả xuất hiện, còn người điều tra không biết dữ liệu gốc đã sai. Nếu nghiệp vụ thật sự có chính sách thay thế mặc định, chính sách đó phải rõ và kết quả cần thể hiện đã áp dụng fallback.

## 7. Khi một giá trị đến từ nhiều nguồn

Trong báo cáo và tính toán tổng hợp, một đầu ra thường không ứng với một bản ghi nguồn duy nhất.

Giả sử doanh thu ngày được tính bằng:

~~~text
doanhThuNgay =
    tổng tiền các đơn PAID trong ngày
    - tổng tiền các khoản REFUND được tính vào ngày
~~~

Một giá trị **doanhThuNgay** có thể phụ thuộc vào hàng nghìn đơn và hàng trăm khoản hoàn tiền. Muốn truy nguyên, ít nhất phải xác định:

1. Định nghĩa chỉ số: lấy trạng thái nào, có bao gồm thuế hay vận chuyển không, dùng ngày giao dịch hay ngày ghi nhận.
2. Các tập dữ liệu nguồn: bảng đơn hàng, giao dịch hoàn tiền và bảng liên quan.
3. Điều kiện lọc: trạng thái, khoảng ngày, múi giờ, loại giao dịch.
4. Phép ghép và tổng hợp: khóa join, cách tránh nhân đôi bản ghi, công thức.
5. Phiên bản hoặc thời điểm dữ liệu được chụp: báo cáo tính với snapshot nào.
6. Mốc xử lý: job/run ID, thời gian sinh báo cáo, phiên bản code hoặc quy tắc.

### Một ví dụ lineage ở mức cột

| Trường đầu ra | Nguồn | Biến đổi | Thông tin cần lưu hoặc mô tả |
| --- | --- | --- | --- |
| **report_date** | Thời điểm giao dịch | Chuyển sang ngày theo múi giờ báo cáo | Múi giờ và định nghĩa ranh giới ngày |
| **gross_amount** | Đơn hàng đã thanh toán | Lọc trạng thái rồi tổng hợp | Điều kiện lọc, đơn vị tiền và snapshot |
| **refund_amount** | Bản ghi hoàn tiền | Tổng theo ngày ghi nhận | Quy tắc loại trùng, trạng thái hoàn tiền |
| **net_amount** | gross_amount và refund_amount | Lấy gross trừ refund | Phiên bản công thức và quy tắc làm tròn |

Nếu thay công thức mà không lưu **phiên bản định nghĩa chỉ số**, hai báo cáo cùng tên được sinh ở hai thời điểm có thể không còn so sánh được. Đó là rủi ro về **ngữ nghĩa dữ liệu**, không chỉ về cách viết code.

### Truy nguyên tập hợp: một tập kết quả có nhiều đóng góp

Khi dữ liệu được **join**, **group by** hoặc **aggregate**, việc giữ một **sourceRecordId** duy nhất không đủ. Có thể cần:

- Tập ID bản ghi đóng góp, hoặc một đường dẫn truy vấn để tìm lại chúng.
- ID của lần xử lý và phiên bản snapshot.
- Công thức tổng hợp và cấu hình lọc.
- Thông tin nguồn của các bảng tham chiếu.
- Cơ chế truy vấn ngược từ kết quả tới tập bản ghi phù hợp.

Không nhất thiết sao chép tất cả ID vào mỗi dòng báo cáo; với dữ liệu lớn, điều đó có thể quá tốn kém. Có thể lưu một **run ID** liên kết tới metadata và tập dữ liệu có phiên bản, rồi tái thực hiện truy vấn khi nguồn lịch sử còn khả dụng.

## 8. Phép biến đổi có thể làm mất thông tin

Không phải mọi phép biến đổi đều có thể đảo ngược:

| Phép biến đổi | Dữ liệu có thể mất | Hệ quả khi truy nguyên |
| --- | --- | --- |
| **trim / uppercase** | Khoảng trắng và kiểu chữ ban đầu | Không thể khôi phục chính xác chuỗi gốc từ chuỗi chuẩn hóa |
| **Làm tròn số tiền** | Phần thập phân trước làm tròn | Muốn giải thích chênh lệch phải biết giá trị trước và quy tắc làm tròn |
| **Ẩn thông tin nhạy cảm** | Nội dung đầy đủ của dữ liệu | Cần nguồn lưu trữ có kiểm soát nếu nghiệp vụ cho phép truy hồi |
| **Tổng hợp theo ngày** | Đóng góp của từng bản ghi nếu không giữ quan hệ nguồn | Khó lần ngược lỗi nếu không lưu snapshot hoặc khóa tra cứu |
| **Lọc bản ghi** | Những dòng bị loại khỏi kết quả | Cần biết tiêu chí và số lượng bản ghi bị loại |
| **Join** | Ý nghĩa quan hệ và số lần nhân bản bản ghi nếu khóa không duy nhất | Tổng có thể bị phóng đại, cần kiểm tra cardinality |
| **Ghi đè trạng thái** | Giá trị cũ và thời điểm thay đổi | Không đủ bằng chứng để điều tra lịch sử |

Điều này không có nghĩa phải lưu **mọi bản dữ liệu thô mãi mãi**. Quyết định lưu giữ cần cân nhắc nhu cầu kiểm toán, tái tính, chi phí, an toàn và chính sách bảo vệ dữ liệu. Có trường hợp chỉ cần lưu **tham chiếu an toàn**, **hash phù hợp với mục tiêu**, **phiên bản dữ liệu** hoặc **metadata tổng hợp**. Một hash đơn thuần không chứng minh dữ liệu nguồn là đúng hay đáng tin; nó chỉ có thể hỗ trợ đối chiếu tính toàn vẹn trong những điều kiện nhất định.

Với các phép biến đổi mất thông tin, điều quan trọng là **biết sự mất mát đó có chủ đích**, có hợp đồng rõ ràng và không phá khả năng giải thích đã cam kết.

## 9. Phiên bản và thời điểm: hai yếu tố dễ gây hiểu nhầm

Một kết quả được sinh hôm nay không nhất thiết dùng cùng dữ liệu, cùng quy tắc và cùng bối cảnh như kết quả được sinh tháng trước.

### 9.1. Phiên bản quy tắc

Giả sử chính sách khuyến mại trước đây dùng ngưỡng **500.000 đồng**, sau đó đổi thành **700.000 đồng**. Nếu hệ thống chỉ lưu mức chiết khấu cuối cùng mà không có **policyVersion**, người điều tra khó biết chính sách nào đã áp dụng.

Những thông tin hữu ích có thể là:
- **ruleId / policyVersion**: định danh chính sách nghiệp vụ.
- **schemaVersion**: cấu trúc dữ liệu của sự kiện hoặc bản ghi.
- **applicationVersion** hoặc build identifier: phiên bản hiện thực đã chạy, khi cần chẩn đoán lỗi code.
- **referenceDataVersion**: phiên bản bảng giá, tỷ giá hay danh mục sản phẩm.
- **calculationTime**: thời điểm phép tính được thực hiện.

Cần phân biệt **phiên bản chính sách** với **phiên bản phần mềm**. Một bản triển khai có thể chứa nhiều chính sách, hoặc một chính sách giữ nguyên trong nhiều bản phát hành.

### 9.2. Thời điểm sự kiện và thời điểm xử lý

Trong hệ thống nhận sự kiện bất đồng bộ, có ít nhất hai mốc:

- **Event time:** khi sự kiện được tạo hoặc xảy ra ở nguồn, theo định nghĩa hợp đồng nguồn.
- **Processing time:** khi hệ thống hiện tại tiếp nhận hoặc xử lý sự kiện.

Ví dụ, một giao dịch xảy ra lúc 23:58 nhưng đến hệ thống lúc 00:03 ngày hôm sau. Báo cáo phân nhóm theo ngày **giao dịch** có thể khác báo cáo phân nhóm theo ngày **tiếp nhận**. Cả hai có thể hợp lệ nếu tên chỉ số nói rõ ý nghĩa; sẽ gây lỗi nếu dùng lẫn mà không nhận ra.

Thời gian nên có đơn vị và múi giờ xác định. Trong Java, **Instant** phù hợp để biểu diễn một mốc thời gian trên trục UTC, còn **LocalDate** có thể dùng cho ngày nghiệp vụ khi đã xác định **ZoneId**. Tránh coi một chuỗi ngày giờ không có múi giờ là một thời điểm tuyệt đối.

### 9.3. Dữ liệu “hiện tại” có thể thay đổi

Giả sử tra bảng giá hiện tại để giải thích một đơn hàng cũ. Bảng giá đã đổi, nên việc tính lại hôm nay không tái tạo kết quả đã tính lúc đặt hàng. Muốn **reproducibility** (tái tạo kết quả), có thể cần snapshot giá tại thời điểm giao dịch, phiên bản bảng giá hoặc nguồn dữ liệu lịch sử.

Không nên giả định rằng “có source ID” thì chắc chắn tính lại được. ID chỉ hữu ích khi dữ liệu tương ứng còn tồn tại và được diễn giải theo đúng schema, quy tắc và thời điểm.

## 10. Theo dõi biến đổi qua nhiều dịch vụ

Trong hệ thống nhiều service, thông tin có thể đi qua các bước:

~~~mermaid
flowchart LR
    A[POS / API] --> B[Ingestion]
    B --> C[Order Service]
    C --> D[Pricing Service]
    D --> E[Database]
    E --> F[Reporting Job]
    F --> G[Dashboard]
~~~

Vấn đề không chỉ là tìm *service nào* đã được gọi. Ta còn cần biết **mã thực thể nghiệp vụ** nào tương ứng qua các ranh giới.

Một bộ nhận diện có thể gồm:

| Nhận diện | Vai trò |
| --- | --- |
| **sourceSystem + sourceRecordId** | Tìm bản ghi bên ngoài đã cung cấp dữ liệu |
| **eventId** | Xác định sự kiện cụ thể; hỗ trợ kiểm tra xử lý trùng |
| **orderId** | Xác định thực thể nghiệp vụ trong hệ thống |
| **traceId / correlationId** | Tìm chuỗi lời gọi hoặc sự kiện vận hành liên quan |
| **jobRunId** | Xác định một lượt xử lý batch hoặc báo cáo |
| **ruleVersion** | Biết quy tắc tính toán nào đã áp dụng |

Không nên dùng một mã duy nhất cho mọi mục đích. Chẳng hạn, cùng **orderId** có thể được cập nhật nhiều lần, qua nhiều trace và được đưa vào nhiều job báo cáo. Ngược lại, một trace có thể xử lý nhiều bản ghi. Các mối quan hệ cần được mô tả đúng.

### Ràng buộc đáng chú ý

**Nguồn đáng tin:** nếu client bên ngoài tự gửi **sourceSystem = "ERP"**, chuỗi đó không thể tự chứng minh dữ liệu đến từ ERP. Hệ thống tiếp nhận phải gắn nguồn dựa trên kênh xác thực hoặc hợp đồng tích hợp đáng tin cậy.

**Idempotency:** cùng một sự kiện có thể đến nhiều lần vì retry hoặc cơ chế giao hàng của message broker. Việc ghi lineage đầy đủ không tự ngăn cộng doanh thu hai lần. Cần cơ chế nhận diện/khử trùng và transaction tương ứng với ngữ nghĩa xử lý.

**Tính nhất quán giữa dữ liệu và sự kiện:** nếu lưu đơn hàng thành công nhưng phát sự kiện thất bại, downstream có thể không thấy thay đổi. Khi cần cập nhật dữ liệu và phát sự kiện một cách đáng tin cậy, có thể cân nhắc **transactional outbox** hoặc cơ chế phối hợp phù hợp. Chọn theo hệ thống lưu trữ và bảo đảm cần đạt.

**Truy nguyên xuyên hệ thống:** một service có thể đổi khóa, ẩn bớt trường hoặc tổng hợp nhiều bản ghi. Cần tài liệu hoặc metadata ánh xạ; chỉ nối trace ID chưa mô tả được logic giá trị.

## 11. Quan sát mà không làm lộ dữ liệu

Nhu cầu debug không đồng nghĩa được ghi toàn bộ payload, token, thông tin cá nhân hoặc dữ liệu thanh toán vào log.

Một chiến lược phù hợp có thể gồm:

1. Ghi **mã tương quan**, tên bước, phiên bản quy tắc, loại kết quả, thời gian xử lý và nhóm lỗi.
2. Chỉ ghi giá trị nghiệp vụ thật sự cần cho chẩn đoán nếu được chính sách dữ liệu cho phép.
3. Hạn chế việc đưa **định danh duy nhất có cardinality cao** vào nhãn metrics; dùng trace hoặc log có kiểm soát cho truy vết từng yêu cầu.
4. Giới hạn truy cập và thời gian lưu trữ log/audit theo mức độ nhạy cảm.
5. Làm sạch hoặc che các trường nhạy cảm và bảo đảm bản ghi gốc, nếu cần giữ, được bảo vệ riêng.
6. Không trả lại thông tin nội bộ hoặc stack trace có thể tiết lộ dữ liệu trong thông báo lỗi cho client.

Ví dụ log mức khái niệm:

~~~text
event=order_line_priced
orderId=O-123
sourceSystem=POS
sourceRecordId=line-9821
ruleVersion=LINE_TOTAL_V1
result=SUCCESS
traceId=...
~~~

Ví dụ không ghi số thẻ, token, địa chỉ hay nội dung payload. Trong hệ thống thật, **orderId** và **sourceRecordId** vẫn có thể là dữ liệu nhạy cảm tùy bối cảnh và phải được bảo vệ tương ứng.

## 12. Những lỗi thiết kế khiến khó truy nguyên

| Dấu hiệu | Vì sao gây khó khăn? | Hướng cải thiện |
| --- | --- | --- |
| Truyền **Map<String, Object>** xuyên nhiều tầng mà không có schema | Không biết trường nào tồn tại và mang ý nghĩa gì | Định nghĩa kiểu hoặc hợp đồng đầu vào/đầu ra rõ |
| Ghi đè biến nguồn trong quá trình chuẩn hóa | Mất giá trị và định dạng ban đầu | Tách dữ liệu nguồn với dữ liệu đã chuẩn hóa |
| Bắt lỗi rồi trả 0, rỗng hoặc null mà không có chính sách | Kết quả sai trông giống dữ liệu hợp lệ | Trả lỗi có ngữ nghĩa hoặc kết quả fallback được đánh dấu |
| Sao chép quy tắc tính toán ở nhiều nơi | Cùng đầu vào có thể tạo đầu ra khác nhau | Xác định nơi sở hữu quy tắc, test hợp đồng |
| Không lưu phiên bản quy tắc hoặc dữ liệu tham chiếu | Không giải thích được khác biệt giữa các lần chạy | Mang theo metadata phiên bản phù hợp |
| Mã nguồn được lấy trực tiếp từ trường client tự khai | Không chứng minh được xuất xứ thật | Xác định nguồn dựa trên tích hợp được xác thực |
| Dùng thời điểm xử lý như thời điểm nghiệp vụ | Tổng hợp hoặc phân loại sai khoảng thời gian | Phân biệt event time, processing time và múi giờ |
| Join trên khóa không duy nhất rồi tổng hợp | Đếm trùng bản ghi và phóng đại số tiền | Kiểm tra cardinality, khóa và điều kiện join |
| Chỉ dựa vào log debug có thể bị xóa/lấy mẫu | Không có bằng chứng truy nguyên bền vững | Lưu metadata hoặc dữ liệu kiểm toán theo yêu cầu |
| Lưu mọi payload vô thời hạn | Tăng rủi ro lộ dữ liệu, chi phí và nghĩa vụ lưu giữ | Thiết kế giữ dữ liệu theo mục tiêu và chính sách |

Một mẫu chung của nhiều lỗi là **ý nghĩa của dữ liệu chỉ tồn tại trong đầu người viết code**. Khi quy tắc, đơn vị, khóa và phạm vi thời gian được thể hiện trong kiểu dữ liệu, hợp đồng và test, việc sửa hoặc kiểm tra trở nên đáng tin cậy hơn.

## 13. Cách thiết kế khả năng truy nguyên theo rủi ro

Không phải mọi phương thức đều cần một hệ thống lineage phức tạp. Một phép tính nhỏ trong bộ nhớ có thể được kiểm chứng bằng kiểu dữ liệu rõ ràng, test và tên biến tốt. Khi kết quả ảnh hưởng tiền bạc, quyền truy cập, báo cáo hoặc nhiều hệ thống, nhu cầu truy nguyên thường cao hơn.

### Bước 1 — Xác định câu hỏi cần trả lời

Ví dụ: “Vì sao dòng đơn hàng này có thành tiền 100.000 đồng?”, “Nguồn nào đóng góp vào doanh thu ngày 12/11?”, “Sau khi đổi bảng giá, báo cáo nào bị ảnh hưởng?”.

Câu hỏi cụ thể giúp biết có cần truy nguyên **mức trường, mức bản ghi, mức tập dữ liệu** hay chỉ cần thông tin về dịch vụ.

### Bước 2 — Xác định các nguồn và điểm đổi nghĩa

Vẽ đường dữ liệu từ đầu vào đến kết quả. Đánh dấu nơi diễn ra: parse, chuẩn hóa, ánh xạ ID, chuyển đổi đơn vị, join, tính toán, lọc, gộp, lưu và phát hành.

Đặc biệt chú ý **phép biến đổi mất thông tin** và **bước sử dụng dữ liệu tham chiếu thay đổi theo thời gian**.

### Bước 3 — Xác định hợp đồng dữ liệu

Với mỗi bước, làm rõ:

- Dữ liệu nào bắt buộc, có được null không?
- Giá trị thuộc đơn vị hoặc múi giờ nào?
- Dữ liệu lỗi được từ chối hay có fallback?
- Có trạng thái nào không hợp lệ cần ngăn?
- Nếu xử lý lại, kết quả có giống nhau không?
- Nếu sự kiện lặp, có gây tác dụng phụ trùng không?

### Bước 4 — Chọn metadata tối thiểu nhưng đủ

Một API tính toán đơn giản có thể chỉ cần nguồn bản ghi và phiên bản quy tắc. Một báo cáo tài chính có thể cần snapshot, chính sách thời gian, điều kiện lọc, danh sách nguồn và job run. Không nên ghi metadata tràn lan không có người dùng, vì nó sẽ tạo chi phí lưu trữ và rủi ro bảo mật.

### Bước 5 — Viết test cho cả giá trị và đường biến đổi

Kiểm tra đầu ra, điều kiện biên, dữ liệu lỗi, nguồn không bị mất, quy tắc áp dụng đúng phiên bản và dữ liệu đầu vào không bị sửa trái hợp đồng. Với pipeline, thêm integration test cho mapping, join, transaction và xử lý lại sự kiện.

### Bước 6 — Đánh giá khả năng điều tra thực tế

Cho một kết quả giả định bị sai, thử trả lời: “Nguồn nào? Bước nào? Quy tắc nào? Thời điểm nào? Có dữ liệu để xác minh không?” Nếu vẫn không trả lời được, đánh giá thêm metadata hoặc cơ chế lưu giữ cần thiết.

### Bước 7 — Kiểm soát chi phí và quyền truy cập

Lineage có thể chứa định danh nghiệp vụ và liên kết tới dữ liệu nhạy cảm. Cần xác định ai được xem, lưu bao lâu, dữ liệu nào phải ẩn, cách xử lý xóa dữ liệu theo yêu cầu và cách giữ tính hữu ích của các tham chiếu mà không lưu quá mức.

## 14. Tình huống tổng hợp: báo cáo doanh thu sai sau một đợt cập nhật

Một đội phát triển nhận thông báo: **doanh thu ngày hôm qua tăng bất thường 15%** sau khi hệ thống nâng phiên bản. Họ phát hiện:

- Dịch vụ đơn hàng gửi sự kiện **ORDER_PAID**.
- Job đồng bộ mới nhận cùng event từ broker và ghi vào bảng staging.
- Một retry xảy ra sau timeout, khiến một số event được xử lý lần hai.
- Job báo cáo join staging với bảng chiết khấu bằng khóa không duy nhất.
- Report chỉ lưu tổng doanh thu cuối cùng, không lưu run ID hay phiên bản truy vấn.

### Phân tích

Có ít nhất hai nguyên nhân có thể làm số liệu bị nhân:

1. **Dữ liệu trùng do retry hoặc cơ chế giao nhận sự kiện.** Nếu không có cơ chế chống trùng phù hợp, cùng một đơn có thể được tính nhiều lần.
2. **Join nhiều dòng với nhiều dòng ngoài dự kiến.** Nếu một đơn khớp nhiều bản ghi chiết khấu, tổng tiền có thể bị nhân lên ngay cả khi staging không trùng.

Không nên chọn một nguyên nhân chỉ bằng trực giác. Cần kiểm tra **eventId, orderId, số bản ghi staging theo khóa, số dòng trước/sau join**, phiên bản SQL và thời điểm chạy.

### Hướng xử lý có thể kiểm chứng

- Xác định hợp đồng **một sự kiện hay một đơn** được tính bao nhiêu lần trong báo cáo.
- Kiểm tra cơ chế xử lý trùng dựa trên khóa và transaction phù hợp.
- Xác định khóa join và cardinality được kỳ vọng; viết test với trường hợp có nhiều dòng tham chiếu.
- Ghi **jobRunId**, phiên bản truy vấn hoặc quy tắc, snapshot đầu vào và thống kê số lượng trước/sau biến đổi.
- Thực hiện đối soát tổng và số bản ghi cho một khoảng thời gian xác định.
- Nếu cần tính lại, sử dụng đúng tập dữ liệu và định nghĩa thời gian của kỳ báo cáo.

Bài học của tình huống là **trace một request thành công không đủ để giải thích một giá trị tổng hợp sai**. Cần kết hợp thông tin **nguồn**, **biến đổi**, **định danh bản ghi**, **phiên bản** và **điều kiện tổng hợp**.

## 15. Bài tập tự luyện

### Bài tập 1 — Vẽ đường đi của giá tiền

Một ứng dụng nhận **unitPriceText**, **quantity** và **productCode** từ API, chuẩn hóa mã sản phẩm, lấy mức thuế từ bảng chính sách rồi tạo **payableAmount**.

Hãy vẽ chuỗi nguồn → kiểm tra → chuẩn hóa → tra cứu → tính toán → lưu. Với mỗi bước, chỉ ra **đầu vào, đầu ra, phiên bản hoặc thời điểm nào có thể cần lưu** để giải thích số tiền trong tương lai.

*Gợi ý:* Hãy phân biệt giá do client gửi với giá được hệ thống xác nhận, chính sách thuế tại thời điểm giao dịch, quy tắc làm tròn và giá trị được lưu trong đơn.

### Bài tập 2 — Tìm thông tin bị mất

Cho đoạn mã:

~~~java
String code = request.productCode().trim().toUpperCase();
BigDecimal price = new BigDecimal(request.priceText());
order.setProductCode(code);
order.setUnitPrice(price);
~~~

Hãy trả lời:

1. Những thông tin nào đã bị mất nếu chỉ lưu **order**?
2. Khi nào việc chuyển chữ hoa có thể làm sai dữ liệu?
3. Có nên giữ toàn bộ request gốc vô thời hạn chỉ để debug?
4. Bạn sẽ ghi nhận nguồn, phiên bản quy tắc và quyền truy cập như thế nào?

*Gợi ý:* Giá trị nhập ban đầu, định dạng chuỗi, nguồn gửi và thời điểm có thể không còn. Việc giữ payload phải theo nhu cầu truy nguyên và chính sách dữ liệu; bản ghi nguồn có thể được thay bằng tham chiếu phù hợp.

### Bài tập 3 — Phân biệt trace và lineage

Một yêu cầu tính phí vận chuyển có **traceId** cho thấy lời gọi đi qua API Gateway → Order Service → Pricing Service. Kết quả là **30.000 đồng**.

**TraceId đã đủ để biết vì sao phí bằng 30.000 đồng chưa?** Hãy nêu ít nhất ba thông tin bổ sung.

*Gợi ý:* Dữ liệu đầu vào, khu vực giao hàng, chính sách phí và phiên bản áp dụng, nguồn dữ liệu tham chiếu, thời điểm có hiệu lực.

### Bài tập 4 — Xây dựng test về nguồn gốc

Hãy mở rộng ví dụ **OrderLineLineage** để kiểm tra:

1. Cùng một source ID được giữ từ đầu đến cuối.
2. Dữ liệu thiếu hoặc sai định dạng không bị thay thành 0.
3. Công thức sử dụng đúng số lượng đã được kiểm tra.
4. Việc cập nhật phiên bản quy tắc không làm biến mất tham chiếu tới nguồn.

*Gợi ý:* Test nên có assertion về **giá trị**, **metadata** và **trường hợp bị từ chối**. Không chỉ kiểm tra phương thức không ném exception.

### Bài tập 5 — Chọn mức độ truy nguyên

So sánh ba tính năng:
- Tính độ dài chuỗi cho giao diện.
- Tính số tiền phải thanh toán.
- Tổng hợp doanh thu theo ngày từ nhiều nguồn.

Với mỗi tính năng, đề xuất mức metadata phù hợp và giải thích chi phí/lợi ích. Không nhất thiết dùng cùng một hệ thống audit và lineage cho cả ba.

## 16. Tự kiểm tra kiến thức

**Câu 1.** Một kết quả có **sourceRecordId** thì chắc chắn có thể tái tính chính xác không?

*Trả lời:* Không. Còn cần dữ liệu nguồn còn truy cập được, phiên bản quy tắc, các bảng tham chiếu, đơn vị và những bối cảnh liên quan tới thời điểm tính toán.

**Câu 2.** Log có **traceId** và tên phương thức đã đủ thay data lineage chưa?

*Trả lời:* Chưa. Nó giúp theo dõi lời gọi, nhưng không nhất thiết cho biết trường đầu ra phụ thuộc trường đầu vào nào hay qua phép biến đổi gì.

**Câu 3.** Tại sao cần phân biệt dữ liệu thô và dữ liệu chuẩn hóa?

*Trả lời:* Hai giai đoạn có hợp đồng khác nhau. Tách chúng giúp không vô tình ghi đè giá trị nguồn, cho biết điểm kiểm tra dữ liệu và dễ xác minh phép biến đổi.

**Câu 4.** Một job báo cáo đúng công thức nhưng join sai khóa có thể tạo số liệu sai không?

*Trả lời:* Có. Quan hệ dữ liệu và cardinality của phép join quyết định tập bản ghi tham gia phép tính; công thức đúng trên tập dữ liệu sai vẫn tạo kết quả sai.

**Câu 5.** Có nên ghi toàn bộ payload của mọi request để bảo đảm truy nguyên?

*Trả lời:* Không mặc định. Cần thiết kế metadata, tham chiếu, lưu trữ và quyền truy cập theo nhu cầu, thời hạn giữ và mức nhạy cảm của dữ liệu.

**Câu 6.** Một phép tổng hợp mất khả năng xác định từng bản ghi nguồn có luôn là lỗi không?

*Trả lời:* Không nhất thiết. Đó có thể là đánh đổi có chủ đích theo chi phí và yêu cầu. Tuy nhiên, cần biết giới hạn truy nguyên và có cơ chế đối soát hoặc tái tính đủ cho mục tiêu nghiệp vụ.

## Ghi nhớ

**Truy nguyên nguồn gốc và biến đổi dữ liệu** giúp trả lời ba câu hỏi: **dữ liệu từ đâu đến, đã thay đổi như thế nào và kết quả hiện tại dựa trên bằng chứng nào**. Trong mã nguồn dễ bảo trì, những điều này được hỗ trợ bằng hợp đồng dữ liệu rõ ràng, ranh giới kiểm tra và chuẩn hóa, phép biến đổi có thể kiểm thử, định danh nguồn, phiên bản quy tắc và metadata được chọn theo rủi ro. Truy nguyên tốt không chỉ giúp tìm lỗi nhanh hơn; nó còn giúp đánh giá tác động thay đổi, đối soát kết quả và tăng độ tin cậy của hệ thống mà vẫn cân nhắc chi phí lưu trữ và bảo vệ dữ liệu.
