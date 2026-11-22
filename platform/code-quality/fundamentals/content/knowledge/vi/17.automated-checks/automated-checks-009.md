# Dương tính giả, âm tính giả và giả thiết phân tích

Công cụ kiểm tra tự động có thể phát hiện một câu lệnh nguy hiểm trong vài giây, nhưng cũng có thể cảnh báo một đoạn mã vốn đã an toàn hoặc bỏ sót một lỗi chỉ xuất hiện trong môi trường thực tế. Nếu nhóm xem mọi cảnh báo là lỗi chắc chắn, thời gian review bị tiêu tốn và nhiều người sẽ tìm cách tắt quy tắc. Nếu nhóm xem báo cáo “xanh” là bằng chứng tuyệt đối rằng mã không có lỗi, những rủi ro quan trọng có thể không được kiểm tra thêm.

Bài học thuộc chương **Kiểm tra tự động** của **CODE_QUALITY_FUNDAMENTALS**. Theo mục tiêu module, kiểm tra tự động cần góp phần làm mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Trọng tâm ở đây là phân biệt **dương tính giả**, **âm tính giả**, **giới hạn và giả thiết của phép phân tích**, rồi dùng bằng chứng để quyết định cách xử lý kết quả một cách nhất quán.

## 1. Công cụ đang trả lời câu hỏi nào?

Trước khi đánh giá kết quả, cần hiểu loại kiểm tra được sử dụng.

| Nhóm kiểm tra | Thông tin công cụ có thể quan sát | Ví dụ phát hiện | Điều không tự chứng minh |
| --- | --- | --- | --- |
| **Formatter / style checker** | Văn bản, cú pháp hoặc cấu trúc mã theo quy tắc | Sai thụt lề, tên không tuân quy ước | Thuật toán và nghiệp vụ đúng |
| **Static analysis** | Mã nguồn/bytecode, kiểu, luồng dữ liệu và quy tắc có sẵn | Dereference có thể null, tài nguyên có thể chưa đóng | Mọi đường chạy, mọi cấu hình và dữ liệu thật đều an toàn |
| **SAST** | Cấu trúc và luồng dữ liệu liên quan đến bảo mật | Đầu vào không đáng tin có thể đi đến thao tác nhạy cảm | Một cảnh báo chắc chắn khai thác được trong production |
| **Architecture check** | Phụ thuộc class/package/module trong phạm vi được quét | Chu kỳ package, chiều phụ thuộc sai | Ranh giới nghiệp vụ luôn hợp lý |
| **Unit / integration tests** | Hành vi thực thi với input và môi trường đã chọn | Sai kết quả ở ngưỡng, lỗi khi kết nối DB giả lập | Mọi dữ liệu và mọi trạng thái đều đã được thử |
| **Coverage** | Phần mã/nhánh đã được thực thi theo cách đo | Dòng chưa được test chạy qua | Các dòng đã chạy cho kết quả đúng |
| **Performance test / benchmark** | Thời gian và tài nguyên với workload định nghĩa | p95 tăng, allocation lớn | Cùng kết quả sẽ xuất hiện trên mọi máy và mức tải |

Một công cụ formatter có thể xác định khá rõ một vi phạm định dạng theo cấu hình. Nhưng một công cụ SAST phân tích đường đi phức tạp có thể phải **xấp xỉ** hành vi của chương trình. Vì thế, “đúng hay sai” phải được đánh giá **theo mục tiêu, phạm vi và quy tắc cụ thể**, không theo tên công cụ.

Một lời cảnh báo kiểu “possible null dereference” nghĩa là công cụ cho rằng tồn tại **khả năng** theo mô hình của nó; không nhất thiết nó đã xác nhận một lần chạy sẽ ném `NullPointerException`.

## 2. Dương tính giả và âm tính giả là gì?

Để dùng chính xác hai thuật ngữ này, cần định nghĩa **điều kiện đúng (ground truth)** và **phạm vi quy tắc**.

- **Dương tính (positive):** công cụ đánh dấu đoạn mã hoặc hành vi là vi phạm theo quy tắc đang xét.
- **Âm tính (negative):** công cụ không đánh dấu.
- **Dương tính giả (false positive, FP):** công cụ cảnh báo, nhưng sau khi kiểm chứng có đủ căn cứ rằng **điều kiện vi phạm mà quy tắc định tìm không tồn tại** ở trường hợp ấy.
- **Âm tính giả (false negative, FN):** điều kiện vi phạm **tồn tại và thuộc phạm vi công cụ được kỳ vọng phát hiện**, nhưng công cụ không cảnh báo.

Ví dụ, giả sử quy tắc muốn phát hiện một đầu vào không đáng tin được ghép thành **cú pháp SQL**, nhưng trong mã cụ thể chỉ có tên cột được chọn từ danh sách cố định phía server, còn dữ liệu người dùng được bind bằng tham số. Nếu công cụ vẫn khẳng định có đường dữ liệu người dùng đi vào cú pháp SQL, kết quả có thể là FP **sau khi xác minh toàn bộ đường đi**.

Ngược lại, nếu code có lỗi phân quyền đối tượng thật nhưng bộ quét chỉ biết tìm API SQL nguy hiểm và không hề hỗ trợ kiểm tra logic quyền, đó là **khoảng trống phạm vi**, không nhất thiết là FN của *quy tắc SQL*. Đặt tên đúng giúp nhóm bổ sung đúng loại kiểm tra thay vì đòi một quy tắc làm công việc ngoài thiết kế.

### 2.1. Ma trận kết quả

| Tình trạng thực tế trong phạm vi đánh giá | Công cụ cảnh báo | Công cụ không cảnh báo |
| --- | --- | --- |
| Có vi phạm theo quy tắc | **TP — True Positive** | **FN — False Negative** |
| Không có vi phạm theo quy tắc | **FP — False Positive** | **TN — True Negative** |

Giả sử review một cảnh báo và thấy “không thể khai thác được trên môi trường hiện tại”. **Không nên vội gọi FP**. Có thể quy tắc đang kiểm tra một mẫu mã nguy hiểm thật, nhưng kiểm soát bên ngoài làm giảm khả năng khai thác. Khi ấy, phát hiện có thể vẫn đúng về **mẫu mã**, còn mức **rủi ro triển khai** thấp hơn. Đây là hai kết luận khác nhau.

Tương tự, “không có bằng chứng lỗi” không đồng nghĩa “đã chứng minh không có lỗi”. Khi chưa xác minh, dùng trạng thái **cần điều tra / chưa kết luận** thay vì ép vào FP hoặc TP.

### 2.2. Độ chính xác và khả năng phát hiện

Với bộ dữ liệu đã có nhãn kiểm chứng phù hợp, một số thước đo là:

- **Precision (độ chính xác của các cảnh báo):** `TP / (TP + FP)` — trong số cảnh báo, bao nhiêu phần đúng.
- **Recall / sensitivity (khả năng phát hiện):** `TP / (TP + FN)` — trong số vi phạm thật thuộc phạm vi, công cụ tìm được bao nhiêu.
- **False positive rate:** `FP / (FP + TN)` — trong số trường hợp thực tế không vi phạm, bao nhiêu trường hợp bị báo nhầm.
- **False negative rate:** `FN / (TP + FN)` — trong số vi phạm thật, bao nhiêu trường hợp bị bỏ sót.

Ví dụ **giả định**: trong một tập 1.000 trường hợp đã được xác minh theo cùng quy tắc, có 20 vi phạm thật; công cụ phát hiện đúng 15, bỏ sót 5 và báo nhầm 49 trường hợp không vi phạm. Khi đó:

| Chỉ số | Giá trị minh họa |
| --- | ---: |
| TP | 15 |
| FN | 5 |
| FP | 49 |
| TN | 931 |
| Precision | `15 / 64 ≈ 23,4%` |
| Recall | `15 / 20 = 75%` |
| False positive rate | `49 / 980 = 5%` |

Dù tỷ lệ cảnh báo nhầm trên các trường hợp an toàn chỉ 5%, số cảnh báo đúng vẫn có thể là tỷ lệ nhỏ khi **vi phạm thật hiếm**. Đây là một lý do không nên đánh giá công cụ chỉ bằng số cảnh báo hay tỷ lệ FP không kèm mẫu số.

**Giới hạn thực tế:** trong một repository bình thường, nhóm thường chỉ review **các cảnh báo được đưa ra**. Khi chưa biết những lỗi bị bỏ sót, không thể suy ra recall hoặc false negative rate từ số cảnh báo đơn thuần. Cần bộ mẫu đã gắn nhãn, kiểm thử bổ sung, review độc lập hoặc dữ liệu lỗi thực tế để đánh giá phần bị bỏ sót.

## 3. Vì sao công cụ phải dựa trên giả thiết?

Chương trình hiện đại có thể gọi thư viện, chạy nhiều luồng, dùng reflection, truy vấn cơ sở dữ liệu, đọc cấu hình ở runtime và giao tiếp với hệ thống bên ngoài. Để phân tích trong thời gian chấp nhận được, công cụ thường dùng **mô hình đơn giản hóa**.

Những giả thiết hoặc giới hạn thường gặp:

| Giả thiết / giới hạn | Công cụ có thể làm gì | Nguy cơ liên quan |
| --- | --- | --- |
| **Biết được tập hàm gọi** | Dựng call graph từ mã/bytecode thấy được | Reflection, plugin nạp động hoặc callback có thể làm bỏ sót đường gọi |
| **Mô hình thư viện đầy đủ** | Dự đoán hàm thư viện xử lý dữ liệu ra sao | Thư viện bên thứ ba hoặc wrapper riêng có thể bị mô hình hóa thiếu |
| **Phân biệt dữ liệu đáng tin và không đáng tin** | Theo dấu input từ source đến sink | Nhầm dữ liệu an toàn thành nguy hiểm hoặc không theo được input gián tiếp |
| **Biết hiệu lực của bước làm sạch/kiểm tra** | Công nhận một sanitizer hoặc guard | Không nhận ra cơ chế hợp lệ gây FP; công nhận nhầm cơ chế yếu gây FN |
| **Theo dõi trạng thái liên thủ tục** | Suy luận qua nhiều phương thức | Giới hạn độ sâu, độ nhạy theo ngữ cảnh và alias có thể làm mất thông tin |
| **Mô hình được môi trường runtime** | Phân tích theo những cấu hình đã biết | Feature flag, quyền, schema hoặc profile khác có thể đổi hành vi |
| **Mô hình được đồng thời** | Xét truy cập biến và thứ tự có thể xảy ra | Race condition, deadlock và lỗi chỉ xuất hiện dưới tải có thể bị bỏ sót |
| **Giả thiết về tính khả thi đường đi** | Ước lượng điều kiện nhánh | Báo đường thực tế bất khả thi hoặc bỏ qua tổ hợp hiếm |
| **Phạm vi source scan đầy đủ** | Kiểm tra những tệp thuộc cấu hình | Tệp sinh tự động, module loại trừ hoặc artifact ngoài phạm vi có thể bị bỏ qua |
| **Hợp đồng nghiệp vụ đã được mã hóa** | Đánh giá theo các rule đã biết | Công cụ không tự biết một người chỉ được xem đơn của mình |

Cùng một đoạn mã có thể tạo kết quả khác nhau nếu **phiên bản analyzer, quy tắc, cấu hình, phạm vi hoặc dependency model** thay đổi. Vì thế, hai báo cáo không nên được so sánh theo số lượng thô mà không ghi những khác biệt này.

### 3.1. Không phải giả thiết nào cũng sai

Giả thiết phân tích là cách **quản lý chi phí và độ chính xác**. Một linter đặt quy tắc “tên hằng số dạng UPPER_SNAKE_CASE” có thể kiểm tra rất nhanh và nhất quán. Điều nó cần là dự án **đồng ý** quy ước đó, không phải dự đoán mọi hành vi runtime.

Một SAST có thể cố tình ưu tiên phát hiện nhiều đường nghi ngờ để tránh bỏ sót lỗ hổng quan trọng, chấp nhận nhiều FP hơn. Một analyzer khác có thể chỉ cảnh báo khi có bằng chứng rất mạnh, giảm FP nhưng tăng khả năng bỏ sót. Lựa chọn phù hợp phụ thuộc **mục đích kiểm tra và chi phí sai sót**.

## 4. Ví dụ Java: cảnh báo SQL động nhưng đường dữ liệu đã được kiểm soát

Giả sử API lấy danh sách hóa đơn và cho phép người dùng chọn thứ tự sắp xếp theo **ngày tạo** hoặc **số tiền**. Tên cột SQL không thể được bind bằng dấu `?` như giá trị thông thường, nên một phần câu truy vấn phải chọn từ các đoạn cú pháp cố định.

### 4.1. Phiên bản có kiểm soát rõ ràng

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

enum InvoiceSort {
    CREATED_AT("created_at"),
    TOTAL_VND("total_vnd");

    private final String column;

    InvoiceSort(String column) {
        this.column = column;
    }

    String sqlColumn() {
        return column;
    }
}

final class InvoiceReader {
    static int countMatching(
            Connection connection,
            long ownerId,
            InvoiceSort sort) throws SQLException {

        if (connection == null || sort == null) {
            throw new IllegalArgumentException("missing input");
        }

        // Chỉ chọn từ các tên cột cố định trong mã nguồn.
        String sql = "SELECT id FROM invoices "
                + "WHERE owner_id = ? ORDER BY "
                + sort.sqlColumn();

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setLong(1, ownerId);

            try (ResultSet rows = statement.executeQuery()) {
                int count = 0;
                while (rows.next()) {
                    count++;
                }
                return count;
            }
        }
    }
}
~~~

Một quy tắc đơn giản chỉ tìm **chuỗi SQL được nối với một biểu thức** có thể cảnh báo đoạn này. Nhưng khi kiểm tra cụ thể:

- `sort` là một giá trị `InvoiceSort`, không phải một đoạn SQL bất kỳ do client đưa vào.
- `sqlColumn()` chỉ trả một trong hai hằng số đã khai báo trong enum.
- `ownerId` được truyền dưới dạng **giá trị được bind** bằng `PreparedStatement`.
- Không có dữ liệu đầu vào tự do được chèn vào cú pháp truy vấn theo đường đang xét.

Đối với **quy tắc phát hiện SQL injection từ giá trị người dùng**, cảnh báo vì `sort.sqlColumn()` có thể là FP sau khi xác minh đường đi và các giả thiết tương ứng. Nhưng nếu quy tắc được đặt tên là **“không cho phép bất kỳ SQL string concatenation nào”**, đoạn này có thể là **vi phạm quy ước thật**, dù không có đường injection theo mô hình đã kiểm tra. Kết quả phụ thuộc vào **điều quy tắc thực sự tuyên bố**.

Ngoài ra, ví dụ tập trung vào kiểm soát cú pháp SQL. Nó không tự chứng minh `ownerId` đáng tin, người gọi có quyền truy cập các bản ghi tương ứng hay truy vấn đáp ứng yêu cầu phân quyền. `ownerId` phải đến từ ngữ cảnh xác thực và chính sách truy cập có hiệu lực trong hệ thống thật.

### 4.2. Biến enum thành chuỗi ở ranh giới đúng cách

Tầng API có thể nhận `sortBy` dạng chuỗi. Không nên đưa chuỗi đó thẳng vào SQL; cần ánh xạ sang lựa chọn được phép:

~~~java
final class SortParser {
    static InvoiceSort parse(String sortBy) {
        if (sortBy == null || sortBy.isBlank()
                || "date".equals(sortBy)) {
            return InvoiceSort.CREATED_AT;
        }
        if ("total".equals(sortBy)) {
            return InvoiceSort.TOTAL_VND;
        }
        throw new IllegalArgumentException(
                "Unsupported sort field");
    }
}
~~~

Các trường hợp bị từ chối không được “lách” bằng việc đưa nguyên chuỗi vào phần `ORDER BY`. Một refactor thay parser bằng truyền chuỗi tự do có thể khiến giả thiết an toàn không còn đúng, dù phương thức truy vấn vẫn trông giống như trước.

### 4.3. Test giúp xác nhận giả thiết, nhưng không thay hết review

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class SortParserTest {
    @Test
    void acceptsOnlyKnownSortOptions() {
        assertEquals(
                InvoiceSort.CREATED_AT,
                SortParser.parse("date"));
        assertEquals(
                InvoiceSort.TOTAL_VND,
                SortParser.parse("total"));
    }

    @Test
    void rejectsUnknownSortOption() {
        assertThrows(
                IllegalArgumentException.class,
                () -> SortParser.parse("other_field"));
    }

    @Test
    void usesStableDefault() {
        assertEquals(
                InvoiceSort.CREATED_AT,
                SortParser.parse(null));
    }
}
~~~

Test chứng minh một số ca parser hoạt động như hợp đồng đã chọn. Để bảo vệ ranh giới, có thể còn cần **integration test** với database, kiểm tra ánh xạ quyền và giới hạn dữ liệu. Nếu test chỉ gọi parser, nó chưa chứng minh truy vấn SQL được thực thi an toàn trong toàn hệ thống.

## 5. Ví dụ Java: âm tính giả do không hiểu quy tắc nghiệp vụ

Một công cụ có thể nhận ra truy vấn SQL đã parameterize và báo “không có SQL injection”. Nhưng endpoint vẫn có thể sai về **phân quyền theo đối tượng**.

Ví dụ một phương thức tìm đơn hàng theo ID:

~~~java
String sql = "SELECT id, owner_id, total_vnd "
        + "FROM orders WHERE id = ?";
~~~

Câu SQL không ghép đầu vào vào cú pháp; đó là tín hiệu tốt cho một loại rủi ro. Nhưng nếu mọi người dùng đã đăng nhập có thể thay đổi `orderId` và nhận thông tin của người khác, hệ thống có thể vi phạm chính sách quyền dù không có cảnh báo injection.

Để phòng vệ, phần ứng dụng phải thực thi chính sách truy cập thực tế. Trong tình huống đơn giản “mỗi khách chỉ xem đơn của mình”, có thể giới hạn tại truy vấn:

~~~java
String sql = "SELECT id, owner_id, total_vnd "
        + "FROM orders WHERE id = ? AND owner_id = ?";
~~~

Trong đó `ownerId` phải được lấy từ danh tính đã xác thực ở server. Quy tắc thật có thể phức tạp hơn, ví dụ chia sẻ quyền, quyền quản trị, tenant và trạng thái đơn.

Nếu công cụ **được cấu hình và được tuyên bố hỗ trợ kiểm tra phân quyền theo đối tượng** nhưng không phát hiện thiếu kiểm tra quyền trong tình huống này, kết quả là FN theo mục tiêu ấy. Nếu công cụ chỉ kiểm tra SQL injection, đây là **lỗ hổng ngoài phạm vi**, không phải lỗi đếm của rule injection. Phân biệt như vậy giúp nhóm không ngộ nhận một báo cáo “0 cảnh báo” là bằng chứng bảo mật tổng thể.

### 5.1. Test kiểm tra hành vi bị từ chối

Một test nghiệp vụ đáng tin phải có ít nhất hai danh tính và hai đối tượng sở hữu khác nhau:

~~~java
@Test
void userCannotReadAnotherUsersOrder() {
    // Arrange: Alice và Bob có những đơn hàng khác nhau.
    // Act: Alice thử truy cập orderId thuộc Bob.
    // Assert: kết quả phải từ chối hoặc không lộ dữ liệu của Bob.
}
~~~

Đây là **khung kiểm thử**, không phải test JUnit hoàn chỉnh: để chạy thực tế cần mô hình dữ liệu, ứng dụng và cách xác thực cụ thể. Điều quan trọng là test phải xác định **kết quả bảo mật mong đợi**, thay vì chỉ chứng minh endpoint trả HTTP 200 khi đăng nhập hợp lệ.

## 6. Dương tính giả không đồng nghĩa “cảnh báo khó chịu”

Có ít nhất bốn trạng thái dễ bị gộp nhầm:

| Trường hợp | Kết luận nên dùng | Vì sao |
| --- | --- | --- |
| Analyzer hiểu sai đường dữ liệu, điều kiện vi phạm không tồn tại | **False positive** nếu bằng chứng đủ mạnh | Quy tắc báo sai trong tình huống được phân tích |
| Quy tắc tìm đúng mẫu nguy hiểm nhưng hệ thống hiện ít phơi lộ | **Finding đúng, rủi ro có thể thấp** | Mẫu vẫn tồn tại, chỉ bối cảnh giảm khả năng/tác động |
| Kết quả có thể đúng nhưng thiếu dữ kiện về runtime hoặc quyền | **Needs investigation** | Chưa đủ căn cứ kết luận |
| Có điểm yếu thật nhưng được chấp nhận trong phạm vi có kiểm soát | **Accepted risk / exception** theo quy trình | Chấp nhận rủi ro không làm điều kiện vi phạm biến mất |
| Quy tắc không phù hợp với convention được nhóm chọn | **Cần thay đổi cấu hình hoặc scope** | Không phải code tự động sai theo mọi hệ quy ước |

Ví dụ một cảnh báo “hàm dài hơn 50 dòng” có thể **đúng theo rule** dù nhóm cho rằng hàm đó rõ ràng và chưa đáng refactor. Không nên ghi FP nếu công cụ đã đếm đúng. Nên đánh giá quy tắc, phạm vi, mức ưu tiên hoặc ghi ngoại lệ có căn cứ.

Ở chiều ngược lại, nếu một analyzer liên tục bỏ qua biến thể code nguy hiểm trong phạm vi đã tuyên bố, không thể tuyên bố “đã an toàn” chỉ nhờ tổng số cảnh báo thấp.

## 7. Âm tính giả có thể đến từ đâu?

### 7.1. Vùng mã không được quét

Ví dụ cấu hình scan loại trừ một module nội bộ, source sinh tự động, đường dẫn chứa mã tích hợp hoặc thư viện chưa được phân tích. Nếu lỗi nằm ở nơi không được quét, kết quả “0 lỗi” chỉ đúng cho **phạm vi đã thực sự quét**.

Cần ghi rõ:

- Commit và nhánh được phân tích.
- Các module, tệp và loại artifact được đưa vào.
- Những loại mã hoặc thư viện bị loại trừ.
- Bộ quy tắc đang bật và những rule bị tắt.
- Phiên bản công cụ, ngôn ngữ và build configuration.

Không chạy được một rule vì thiếu classpath hoặc build lỗi cũng khác với việc rule đã chạy đầy đủ và không phát hiện lỗi.

### 7.2. Đường gọi qua reflection hoặc cấu hình động

Java có thể chọn implementation qua reflection, `ServiceLoader`, dependency injection, plugin hoặc tên class từ cấu hình. Một phân tích chỉ dựng call graph từ các lời gọi tĩnh có thể không thấy một đường chạy được kích hoạt ở runtime.

Đây là lý do cần kết hợp **test tích hợp, kiểm tra cấu hình và quan sát runtime** cho những ranh giới quan trọng.

### 7.3. Hợp đồng thư viện bị mô hình hóa thiếu

Một analyzer theo luồng dữ liệu cần biết hàm nào trả dữ liệu không đáng tin, hàm nào làm sạch, hàm nào gửi dữ liệu tới sink. Nếu một wrapper nội bộ được xử lý như hàm “không biết”, kết quả có thể thận trọng đến mức báo nhầm hoặc lạc quan đến mức bỏ sót đường nguy hiểm.

Khi thêm thư viện hoặc wrapper mới, cần kiểm tra khả năng mô hình hóa của công cụ và các rule tương ứng; đừng mặc định danh sách nhận diện là bất biến.

### 7.4. Lỗi phụ thuộc trạng thái và đồng thời

Một đoạn mã có thể an toàn khi chạy từng request nhưng sai khi hai thread cùng cập nhật field mutable:

~~~java
final class SharedRequestHandler {
    private String currentRequestId;

    String handle(String requestId) {
        currentRequestId = requestId;
        // Trong lúc xử lý, một thread khác có thể ghi lại field.
        return currentRequestId;
    }
}
~~~

Một static analyzer không có mô hình thread interleaving hoặc không biết object được chia sẻ theo scope nào có thể không cảnh báo. Unit test tuần tự cũng có thể qua. Việc kiểm tra quyền sở hữu state, thực thi đồng thời và review cấu hình lifecycle của framework mới tạo được bằng chứng bổ sung.

Cách sửa thường là dùng **biến cục bộ/đầu vào của từng lần gọi**, không phải chỉ thêm `volatile` vào một field dùng chung.

### 7.5. Lỗi phụ thuộc ngữ nghĩa nghiệp vụ

Quy tắc “khách VIP được miễn phí vận chuyển” nằm trong đặc tả sản phẩm; một linter Java không tự biết điều đó. Lỗi tính phí có thể vượt qua mọi rule tĩnh và xuất hiện trong test biên.

Không nên gọi đây là FN của một linter định dạng, nhưng phải xem nó là **khoảng trống bằng chứng của quy trình chất lượng nếu chỉ dùng linter**.

## 8. Một bài test xanh cũng có thể tạo cảm giác âm tính giả

Trong kiểm thử động, việc “không phát hiện lỗi” phụ thuộc **test case, oracle và môi trường**. Ví dụ:

~~~java
final class ShippingPolicy {
    static long feeVnd(long subtotalVnd) {
        // Sai nếu đặc tả là "từ 500_000 VND trở lên miễn phí".
        return subtotalVnd > 500_000L ? 0L : 30_000L;
    }
}
~~~

Một test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class ShippingPolicyIncompleteTest {
    @Test
    void checksSomeValues() {
        assertEquals(30_000L, ShippingPolicy.feeVnd(400_000L));
        assertEquals(0L, ShippingPolicy.feeVnd(600_000L));
    }
}
~~~

Test vẫn qua dù chương trình sai ở **đúng 500.000 VND**. Nếu quy trình tự động được kỳ vọng phát hiện hồi quy tại ngưỡng nhưng không có dữ liệu ở ngưỡng đó, đây là một ví dụ về **bỏ sót lỗi bởi bộ kiểm thử**, chứ không phải khẳng định rule static nào đã sai.

Test bổ sung:

~~~java
@Test
void waivesShippingAtExactThreshold() {
    assertEquals(0L, ShippingPolicy.feeVnd(500_000L));
}
~~~

sẽ thất bại với phiên bản có lỗi. Dựa vào đặc tả, sửa dấu `>` thành `>=` rồi chạy lại bộ test liên quan.

### 8.1. Coverage cao vẫn có thể bỏ lọt lỗi

Cả hướng “có phí” và “miễn phí” đều đã được thực thi ở hai input 400.000 và 600.000. Một báo cáo coverage có thể hiển thị đã đi qua các nhánh của biểu thức điều kiện, nhưng **chưa kiểm chứng ranh giới số học**.

Coverage giúp tìm mã chưa chạy, không đo trực tiếp chất lượng oracle hoặc các tình huống nghiệp vụ đã xét.

### 8.2. Mutation testing giúp kiểm tra sức phát hiện

Mutation testing có thể cố ý đổi `>=` thành `>`, hoặc thay đổi hằng số rồi xem test có thất bại không. Nếu bộ test chỉ có dữ liệu cách xa ngưỡng, mutant có thể sống sót dù các dòng mã đều được chạy.

Mutation score là một tín hiệu bổ sung, không phải phép chứng minh tuyệt đối: mutant tương đương, phạm vi biến đổi, kiểm thử flaky và cấu hình công cụ đều ảnh hưởng báo cáo.

## 9. Trade-off giữa phát hiện rộng và cảnh báo chính xác

Khi chỉnh một rule, nhóm thường phải cân nhắc:

- **Ưu tiên recall:** cố phát hiện càng nhiều trường hợp đáng ngờ càng tốt; có thể tạo thêm cảnh báo cần triage.
- **Ưu tiên precision:** chỉ cảnh báo khi đủ căn cứ mạnh; giảm nhiễu nhưng có thể bỏ qua biến thể phức tạp.

Không phải mọi thay đổi ngưỡng đều dẫn tới đánh đổi tuyến tính. Một mô hình luồng dữ liệu tốt hơn hoặc cấu hình chính xác hơn có thể **đồng thời giảm FP và FN**. Vì thế, trước khi tắt rule, cần tìm xem có thể sửa mô hình nguồn/sink, ngữ cảnh hoặc khả năng hiểu framework không.

### 9.1. Chi phí của FP

- Tốn thời gian review và điều tra.
- Gây mệt mỏi vì cảnh báo, làm các vấn đề thật bị chìm.
- Thúc đẩy việc tắt rule hoặc suppress hàng loạt.
- Khiến nhóm ngại áp dụng kiểm tra tự động vào CI.

### 9.2. Chi phí của FN

- Tạo niềm tin sai rằng code không có vấn đề.
- Để lọt lỗi nghiêm trọng đến production.
- Khiến quá trình khắc phục muộn tốn kém hơn.
- Làm khó xác định loại test/review còn thiếu.

Với **formatting**, FP phiền phức thường có tác động chi phí cộng tác; với **kiểm tra quyền truy cập hoặc mất dữ liệu**, FN có thể có hậu quả cao. Do đó, ngưỡng và quy tắc xử lý cần gắn với **rủi ro của từng nhóm vấn đề**, không dùng một chính sách chặn build cho mọi cảnh báo.

## 10. Quy trình triage một cảnh báo tự động

Một cảnh báo tốt cần được xử lý bằng **bằng chứng và trạng thái rõ ràng**, không chỉ bằng cảm giác người review.

### Bước 1 — Đọc đúng quy tắc và phạm vi

Ghi rõ tool/analyzer version, rule ID, thông báo, source line, commit, module và phạm vi quét. Xác định công cụ đang tìm **vi phạm quy ước**, **khả năng xảy ra lỗi runtime** hay **đường dữ liệu bảo mật**.

### Bước 2 — Xem mã trong bối cảnh

Đọc các hàm gọi trước/sau, điều kiện bảo vệ, luồng dữ liệu và kiểu dữ liệu. Với cảnh báo bảo mật, xác định source, propagation, sink và kiểm soát có hiệu lực. Với cảnh báo tài nguyên, xem vòng đời đối tượng, `try-with-resources` và tình huống ngoại lệ.

### Bước 3 — Xác minh điều kiện báo lỗi có thật không

Có thể dùng:

- Đọc code và hợp đồng thư viện.
- Viết test với dữ liệu đại diện hoặc giá trị biên.
- Kiểm tra cấu hình runtime và quyền.
- Dùng integration/contract test cho API, database và framework.
- Tái hiện trong môi trường được phép nếu cần xác minh lỗi bảo mật.

Không yêu cầu thử khai thác trên production khi đã có đủ căn cứ từ kiểm tra an toàn.

### Bước 4 — Phân loại theo bằng chứng

| Trạng thái | Khi dùng | Hành động |
| --- | --- | --- |
| **Confirmed issue / TP** | Điều kiện vi phạm được xác nhận | Sửa nguyên nhân, test hồi quy, kiểm tra triển khai |
| **False positive / FP** | Có bằng chứng quy tắc báo sai trường hợp cụ thể | Ghi lý do, điều chỉnh model/rule hoặc suppress có phạm vi |
| **Needs investigation** | Chưa rõ đường đi hay kiểm soát | Gán người phụ trách, lập kế hoạch kiểm chứng |
| **Out of scope** | Trường hợp không thuộc rule hoặc phạm vi công cụ | Ghi giới hạn, bổ sung loại kiểm tra phù hợp nếu cần |
| **Accepted risk** | Vấn đề thật nhưng có quyết định chấp nhận có thẩm quyền | Lý do, thời hạn, biện pháp bù trừ, điều kiện rà soát |
| **Fixed / verified** | Đã sửa và có bằng chứng kiểm chứng | Liên kết test, PR và trạng thái triển khai |

Đừng đánh dấu FP chỉ để làm bảng điều khiển “sạch”. Cũng đừng ghi “fixed” nếu mới sửa nguồn mã nhưng một phiên bản cũ vẫn còn chạy trong môi trường ảnh hưởng.

### Bước 5 — Chọn điểm xử lý phù hợp

- **Sửa code** nếu cảnh báo đúng và code có thể cải thiện.
- **Sửa cấu hình analyzer** nếu rule đang áp dụng sai phạm vi hoặc thiếu mô hình.
- **Thêm test** nếu trường hợp bị bỏ sót do thiếu dữ liệu hoặc oracle.
- **Cập nhật quy ước** nếu rule mâu thuẫn với quyết định có căn cứ của nhóm.
- **Suppress cục bộ** khi đã kiểm chứng và có lý do rõ ràng.
- **Đánh giá lại rủi ro** khi phát hiện phụ thuộc runtime, dữ liệu hoặc quyền mới.

### Bước 6 — Theo dõi sau thay đổi

Một thay đổi từ analyzer version mới có thể tăng hoặc giảm số cảnh báo mà không có một dòng code nào đổi. Nên phân biệt **drift của công cụ** với **thay đổi chất lượng code**; kiểm tra một tập cảnh báo đại diện khi nâng cấp lớn.

## 11. Suppression và ngoại lệ: ghi đủ lý do, không che vấn đề

Một annotation hoặc comment tắt rule có thể cần thiết, nhưng là **quyết định được kiểm soát**. Ví dụ sau chỉ minh họa cấu trúc, không khẳng định rule ID này có trong công cụ đang dùng:

~~~java
// Ví dụ ý tưởng, không phải annotation áp dụng cho mọi analyzer.
// Suppress rule XYZ ở đúng vị trí đã được kiểm chứng.
// Lý do: sortColumn chỉ đến từ enum allowlist.
// Tham chiếu: quyết định SEC-012; rà soát khi thay cách parse sortBy.
~~~

Một suppression có chất lượng cần ghi:

1. Rule nào và tại vị trí nào đang được tắt?
2. Vì sao cảnh báo là FP hoặc vì sao ngoại lệ được chấp nhận?
3. Bằng chứng hoặc test nào hỗ trợ kết luận?
4. Ai chịu trách nhiệm rà soát?
5. Điều kiện nào làm lý do không còn đúng?

**Không nên** tắt toàn bộ SAST hoặc loại cả module khỏi phân tích chỉ để loại bỏ vài cảnh báo khó hiểu. Cũng không nên coi việc thêm `@SuppressWarnings` là bằng chứng mã đã an toàn: annotation chỉ điều chỉnh báo cáo, không thay đổi hành vi ứng dụng.

Với rủi ro thật, quy trình **risk acceptance** thường phải tách khỏi **false-positive disposition**. Một sai sót được chấp nhận trong giới hạn thời gian vẫn là sai sót cần theo dõi.

## 12. Ngăn âm tính giả bằng cách kết hợp nhiều lớp bằng chứng

Không có một công cụ tự động nào bảo đảm tìm hết mọi lỗi. Các loại kiểm tra nên **bổ sung nhau**:

~~~mermaid
flowchart TD
    A[Quy tắc và giả thiết chất lượng] --> B[Static analysis / SAST]
    A --> C[Unit và property tests]
    A --> D[Contract / integration tests]
    A --> E[Review kiến trúc và nghiệp vụ]
    B --> F[Tổng hợp bằng chứng và giới hạn]
    C --> F
    D --> F
    E --> F
    F --> G{Đủ căn cứ theo mức rủi ro?}
    G -- Có --> H[Quyết định phát hành có điều kiện]
    G -- Chưa --> I[Bổ sung kiểm tra mục tiêu]
    I --> F
~~~

Ví dụ:

- **Formatter và style rule:** tạo định dạng nhất quán, nhưng không thay test nghiệp vụ.
- **Static analysis:** phát hiện một số mô hình sai phổ biến, nhưng không thay kiểm thử runtime.
- **Test đúng biên:** xác minh quy tắc tính phí, nhưng không chứng minh truy vấn SQL hoặc chứng chỉ TLS đúng.
- **Integration test:** kiểm chứng kết nối và hợp đồng, nhưng không tự bảo đảm quyền cho mọi vai trò và tenant.
- **Review bảo mật:** tìm các trường hợp công cụ không biết ngữ nghĩa nghiệp vụ.
- **Quan sát vận hành:** giúp phát hiện vấn đề chỉ xảy ra dưới tải hoặc cấu hình cụ thể, nhưng không thay phòng ngừa trước phát hành.

Sự đa dạng này tạo **bằng chứng độc lập hơn**, giảm nguy cơ tất cả các bước đều mắc cùng một giả thiết sai. Dù vậy, nhiều công cụ cùng báo “xanh” chưa chắc độc lập nếu chúng sử dụng cùng một mock, cùng cấu hình thiếu dữ liệu hoặc cùng bỏ qua một module.

## 13. Cải thiện rule dựa trên kết quả thực tế

Một công cụ chỉ trở nên đáng tin trong dự án khi được **hiệu chỉnh theo công nghệ, quy ước và lỗi thực tế**.

### 13.1. Tạo bộ ví dụ dương và âm đã kiểm chứng

Nên duy trì những ví dụ nhỏ:

- **Positive case:** mã thật sự vi phạm quy tắc, rule cần cảnh báo.
- **Negative case:** mã an toàn hoặc tuân quy tắc, rule không được cảnh báo.
- **Boundary case:** mẫu gần giống nhưng có khác biệt làm thay đổi kết luận.
- **Regression case:** lỗi hoặc FP từng gặp ở dự án.

Ví dụ với SQL động:

| Trường hợp | Mong muốn của rule injection |
| --- | --- |
| Chuỗi đầu vào tự do được nối vào điều kiện SQL | Cảnh báo khi đường dữ liệu được hỗ trợ |
| Giá trị đầu vào được bind vào `PreparedStatement` | Không cảnh báo ở phần giá trị đã bind đúng |
| Tên cột chọn từ enum chứa hằng số phía server | Không kết luận injection chỉ vì có concatenation |
| Tên cột nhận nguyên văn từ request | Cảnh báo hoặc yêu cầu review theo mức mô hình hóa |
| Đường gọi qua reflection không được phân tích | Ghi nhận giới hạn, bổ sung kiểm thử nếu có rủi ro |

Các test này chỉ đáng tin khi **expected được review độc lập**, không lấy nguyên từ kết quả analyzer đang thử.

### 13.2. Kiểm tra tác dụng của việc đổi cấu hình

Khi bật hoặc tắt rule, đổi ngưỡng hoặc nâng analyzer:

1. Ghi cấu hình trước/sau và mục đích thay đổi.
2. Chạy trên cùng tập code hoặc tập ví dụ đã gắn nhãn.
3. So sánh TP, FP và những trường hợp từng bị bỏ sót **nếu có nhãn đủ tin cậy**.
4. Kiểm tra công cụ có quét đủ module và phân tích thành công không.
5. Đánh giá thời gian chạy, số cảnh báo phải triage và mức ưu tiên.
6. Quyết định chính sách CI: chặn lỗi mới có căn cứ, cảnh báo có điều kiện hoặc chỉ báo cáo.
7. Lưu giả thiết và mốc xem lại.

Không nên tối ưu số lượng cảnh báo về 0 bằng cách loại bỏ module hoặc tắt hầu hết quy tắc. **Số cảnh báo ít đi không tự chứng minh độ tin cậy tăng.**

### 13.3. Đừng chỉ đếm tổng số finding

Một báo cáo có 100 finding có thể gồm 90 vấn đề định dạng, 8 điểm cần review và 2 lỗi nghiêm trọng. Báo cáo khác có 3 finding nhưng cả 3 đều ảnh hưởng đến dữ liệu khách hàng. So sánh “100 tệ hơn 3” là vô nghĩa nếu không xét loại lỗi, mức ảnh hưởng, phạm vi và bằng chứng.

Để theo dõi hiệu quả quy trình, có thể xem:

- Thời gian trung vị từ cảnh báo đến kết luận có căn cứ.
- Tỷ lệ cảnh báo được xác nhận/FP trong **mẫu đã review** và mức độ đại diện của mẫu.
- Số lỗi nghiêm trọng phát hiện sau release nhưng đáng lẽ thuộc phạm vi rule/test.
- Tỷ lệ rule quan trọng có positive và negative regression cases.
- Số suppression còn hiệu lực nhưng quá hạn rà soát.
- Chênh lệch phạm vi scan giữa các phiên bản hoặc môi trường.

Không gộp mọi tiêu chí vào một điểm “code quality” rồi suy ra chính xác hệ thống có bao nhiêu rủi ro.

## 14. Ghi giả thiết phân tích để người sau hiểu kết quả

Khi một quyết định phụ thuộc nhiều vào kết quả công cụ, nên ghi rõ **báo cáo có thể và không thể chứng minh điều gì**.

~~~markdown
### CHECK-009 — <tên quy tắc hoặc nhóm kiểm tra>
- Mục tiêu: <loại vi phạm cần tìm>
- Tool/analyzer và phiên bản:
- Commit, module, artifact và phạm vi scan:
- Cấu hình, rule IDs và những phần bị loại:
- Giả thiết về call graph, thư viện, input, runtime:
- Có hỗ trợ reflection/concurrency/framework không?
- Bằng chứng positive case:
- Bằng chứng negative case:
- Các FP đã xác minh và lý do:
- Các FN hoặc khoảng trống phạm vi đã biết:
- Rủi ro nếu bỏ sót một vi phạm:
- Chính sách CI/review khi có finding:
- Người phụ trách và điều kiện xem lại:
~~~

Ví dụ một nhóm dùng analyzer để phát hiện vi phạm về `null` có thể ghi: “Chúng tôi áp dụng rule cho mã Java nằm trong ba module chính. Một số đường phản chiếu của framework chưa được analyzer theo dõi. Vì vậy, báo cáo không có cảnh báo `null` không thay integration tests với payload thiếu hoặc kiểm tra hợp đồng trên controller.”

Điều này giúp người đọc **không diễn giải quá mức một báo cáo xanh**, đồng thời biết loại kiểm tra nào phải bổ sung nếu framework hoặc cấu trúc dự án thay đổi.

## 15. Những nhầm lẫn thường gặp

**“Có cảnh báo nghĩa là chắc chắn có bug.”** Không. Cần đọc rule, kiểm tra điều kiện và kết luận theo bằng chứng. Nhưng một cảnh báo chưa được xác minh cũng không thể tùy ý bỏ qua.

**“Dương tính giả nghĩa là đoạn mã không có bất kỳ rủi ro nào.”** Sai. FP chỉ nói cảnh báo sai đối với một điều kiện cụ thể; vẫn có thể tồn tại vấn đề khác hoặc rủi ro đổi khi bối cảnh thay đổi.

**“Không có cảnh báo nghĩa là không có lỗi.”** Sai. Công cụ chỉ kiểm tra những trường hợp nó được thiết kế và cấu hình để kiểm tra.

**“Tắt rule gây nhiều cảnh báo sẽ tăng chất lượng báo cáo.”** Chỉ số có thể đẹp hơn nhưng khả năng phát hiện có thể giảm. Cần phân loại nguyên nhân FP và điều chỉnh có kiểm chứng.

**“Có test và coverage 100% thì không còn FN.”** Không đúng. Dữ liệu biên, oracle yếu, tác dụng phụ ngoài phạm vi hoặc cấu hình khác vẫn có thể che lỗi.

**“Bất kỳ cảnh báo nào bị chấp nhận đều là FP.”** Không. Một vấn đề thật có thể được chấp nhận rủi ro trong điều kiện giới hạn, nhưng phải giữ trạng thái và trách nhiệm tương ứng.

**“Số cảnh báo giảm sau nâng cấp tức là mã tốt hơn.”** Có thể do analyzer đổi logic, phạm vi scan thay đổi hoặc rule bị tắt. Chỉ so sánh có ý nghĩa khi giữ rõ bối cảnh.

**“FP và FN có thể được đo chính xác chỉ bằng việc review các finding.”** Không. Review finding giúp ước tính precision trên mẫu; muốn ước tính recall/FN cần biết hoặc lấy mẫu cả những trường hợp không được cảnh báo.

**“Một công cụ chuyên bảo mật có thể kiểm tra mọi quy tắc nghiệp vụ.”** Không. Các chính sách như chủ sở hữu đơn hàng hoặc giới hạn tiền phụ thuộc ngữ nghĩa và hợp đồng của hệ thống.

**“Không biết code đang chạy thì cứ suppress.”** Sai. Thiếu thông tin phải được ghi là **chưa xác minh**, có người phụ trách làm rõ.

## 16. Bài tập vận dụng

### Tình huống A — SAST báo SQL injection

Công cụ cảnh báo một câu SQL nối chuỗi. Review cho thấy phần được nối là tên cột lấy từ `enum` cố định, còn giá trị input được bind bằng `PreparedStatement`.

**Câu hỏi:** nên kết luận ra sao?

**Gợi ý:** đọc mục tiêu rule. Nếu rule tìm dữ liệu không đáng tin đi vào cú pháp SQL thì cần xác minh toàn bộ đường đi; khi không tồn tại, có thể kết luận FP cho cảnh báo đó. Nếu rule cấm mọi dạng SQL nối chuỗi, đây có thể là vi phạm quy ước thật. Dù kết luận nào, vẫn cần kiểm tra quyền truy cập dữ liệu riêng biệt.

### Tình huống B — Báo cáo “0 cảnh báo” nhưng có bug phân quyền

Endpoint dùng ORM an toàn nhưng cho phép người dùng đọc bản ghi của tenant khác. Bộ quét đang bật chỉ có rule injection và mật khẩu hard-coded.

**Câu hỏi:** đây có phải FN của rule injection?

**Gợi ý:** không. Đây là khoảng trống kiểm tra phân quyền ngoài phạm vi rule injection. Cần bổ sung review/test quyền theo đối tượng, hoặc rule phù hợp nếu công cụ hỗ trợ. Không dùng “0 cảnh báo” như bằng chứng an toàn tổng thể.

### Tình huống C — Rule nullability báo nhầm

Một analyzer cảnh báo giá trị có thể `null`. Code đã kiểm tra và trả về sớm, nhưng bước bảo vệ nằm trong một helper mà công cụ không hiểu.

**Câu hỏi:** cần làm gì trước khi suppress?

**Gợi ý:** xác minh helper thực sự chặn mọi đường `null` liên quan, xem contract và test biên. Nếu đúng là FP, có thể cải thiện annotation/mô hình analyzer hoặc suppress hẹp, kèm bằng chứng. Không chỉ nhìn thấy tên hàm `validate` rồi mặc định an toàn.

### Tình huống D — Cùng code, số cảnh báo giảm một nửa

Sau khi nâng phiên bản analyzer, số cảnh báo giảm từ 200 còn 100. Không có thay đổi mã nguồn.

**Câu hỏi:** có thể tuyên bố chất lượng tăng 50%?

**Gợi ý:** không. So sánh cấu hình, phạm vi quét, rule IDs, cách tính và log phân tích. Một số FP có thể được sửa, nhưng cũng có thể một phần rule không còn chạy. Cần kiểm tra mẫu báo cáo và các lỗi đã biết trước khi kết luận.

### Tình huống E — Test xanh dù tính phí sai

Quy tắc miễn phí từ 500.000 VND trở lên; code dùng `>`. Test chỉ chạy 400.000 và 600.000 và báo branch coverage cao.

**Câu hỏi:** lỗi bị bỏ sót do đâu?

**Gợi ý:** dữ liệu không kích hoạt trường hợp biên, dù các nhánh chính đã được thực thi. Thêm ca đúng 500.000 với oracle từ đặc tả, xem test thất bại rồi mới sửa và kiểm tra hồi quy.

### Tình huống F — Dùng suppress cho lỗi có tác động thật

Một static check xác nhận luồng code ghi token vào log. Nhóm nói log chỉ lưu nội bộ nên đánh dấu FP.

**Câu hỏi:** kết luận đó đã đúng chưa?

**Gợi ý:** nếu token thực sự được ghi, phát hiện có thể đúng; mức phơi lộ của log chỉ ảnh hưởng rủi ro và biện pháp kiểm soát. Nên ngừng ghi bí mật và kiểm tra quyền lưu trữ/log retention, thay vì dùng nhãn FP để đóng vấn đề.

## 17. Checklist khi nhận hoặc vận hành kết quả kiểm tra tự động

- **Mục tiêu:** công cụ đang tìm loại vi phạm nào, thuộc rule và phạm vi gì?
- **Nhãn đúng:** đã phân biệt TP, FP, FN, ngoài phạm vi và chưa xác minh chưa?
- **Giả thiết:** công cụ biết được call graph, source/sink, thư viện, runtime và ranh giới nghiệp vụ ở mức nào?
- **Phạm vi:** module, tệp, build artifact và rule có thực sự được phân tích không?
- **Bằng chứng:** đã xem đường dữ liệu, điều kiện, hợp đồng và hành vi cụ thể chưa?
- **Tính đúng:** nếu rule liên quan nghiệp vụ, test có oracle và trường hợp biên phù hợp không?
- **Rủi ro:** hậu quả nếu cảnh báo đúng hoặc nếu lỗi bị bỏ sót là gì?
- **Suppression:** có lý do, phạm vi hẹp, chủ sở hữu và mốc xem lại?
- **Độ tin cậy số liệu:** precision/recall được tính trên mẫu có nhãn đủ tin cậy hay chỉ suy từ báo cáo?
- **Theo thời gian:** khi nâng công cụ hoặc thay cấu hình, đã kiểm tra lại phạm vi và bộ ví dụ gắn nhãn?
- **Hành động:** có sửa nguyên nhân, thêm test hoặc bổ sung công cụ cho khoảng trống đã phát hiện?

**Dương tính giả, âm tính giả và giả thiết phân tích** là những khái niệm giúp nhóm nhìn đúng giá trị của kiểm tra tự động. Một cảnh báo là lời mời kiểm chứng, còn báo cáo không có cảnh báo là kết luận có phạm vi. Khi hiểu công cụ giả định điều gì, ghi lại bằng chứng và kết hợp đúng loại kiểm thử, nhóm sẽ sử dụng kiểm tra tự động để **phát hiện lỗi thật, giảm nhiễu và duy trì mã đáng tin cậy, dễ hiểu, dễ thay đổi** — đúng mục tiêu của **CODE_QUALITY_FUNDAMENTALS**.
