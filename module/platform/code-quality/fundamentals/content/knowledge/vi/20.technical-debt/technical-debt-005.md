# Ghi nhận tác động bằng tình huống thay đổi hoặc sự cố cụ thể

Trong chương **Nợ kỹ thuật** của module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tập trung vào một kỹ năng thực tế: **biến nhận xét “đoạn mã này đang tạo nợ kỹ thuật” thành một hồ sơ có bối cảnh, bằng chứng và ảnh hưởng cụ thể đến công việc**.

Module **CODE_QUALITY_FUNDAMENTALS** giúp người học hiểu những thuộc tính khiến mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Nợ kỹ thuật liên quan trực tiếp đến ba thuộc tính ấy: một quyết định thiết kế có thể giúp giao hàng sớm hôm nay, nhưng tạo thêm công sức kiểm thử, sửa lỗi hoặc phối hợp trong những lần thay đổi sau.

Không phải mọi đoạn mã xấu mắt đều là một khoản nợ cần trả ngay. Một class dài nhưng ổn định có thể ít gây trở ngại hơn một điều kiện nghiệp vụ ngắn bị sao chép ở sáu nơi, buộc các nhóm chỉnh đồng thời và từng gây sự cố. Vì vậy, chỉ ghi “cần refactor cho sạch” thường chưa đủ giúp đội ngũ ưu tiên.

> **Hãy ghi nhận nợ kỹ thuật bằng điều đã xảy ra hoặc tình huống thay đổi có thể kiểm chứng: công việc nào bị cản trở, cơ chế thiết kế nào gây ra cản trở, chi phí/rủi ro là gì, và làm sao biết việc xử lý đã cải thiện tình hình.**

Bài học hướng dẫn cách đi từ **tín hiệu → tình huống → cơ chế → tác động → lựa chọn xử lý → bằng chứng sau xử lý**, với ví dụ Java, kiểm thử và mẫu ghi nhận có thể dùng trong issue hoặc code review.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **nợ kỹ thuật**, **mùi mã**, **lỗi đã xác nhận** và **một lựa chọn thiết kế có chủ đích**.
2. Chỉ ra tác động của nợ kỹ thuật bằng **thay đổi cụ thể**, **sự cố đã xảy ra** hoặc **kịch bản rủi ro có căn cứ**.
3. Ghi nhận riêng **điều quan sát được**, **giả thuyết nguyên nhân**, **chi phí** và **độ chắc chắn** của bằng chứng.
4. Lập một hồ sơ nợ kỹ thuật có đường dẫn đến thay đổi, test, sự cố hoặc dữ liệu đo, thay vì chỉ dùng đánh giá cảm tính.
5. Hiểu cách những ràng buộc cấu trúc như logic lặp, trạng thái ngầm và coupling làm tăng chi phí thay đổi Java.
6. Xây dựng test hồi quy và tiêu chí chấp nhận trước khi trả nợ kỹ thuật có tác động đến nghiệp vụ.
7. Ưu tiên xử lý dựa trên **mức ảnh hưởng, tần suất gặp lại, rủi ro và chi phí sửa**, không chỉ điểm cảnh báo của công cụ.
8. Đánh giá hiệu quả sau cải thiện, đồng thời tránh khẳng định quan hệ nhân quả từ những con số thiếu ngữ cảnh.

## 2. Nợ kỹ thuật có nghĩa gì trong bài này?

Một cách hiểu hữu ích: **nợ kỹ thuật là chi phí hoặc rủi ro phải gánh trong tương lai do các lựa chọn liên quan đến thiết kế, triển khai, kiểm thử, cấu hình hoặc vận hành ở hiện tại**. Một phần nợ được chấp nhận có chủ đích để đạt mục tiêu thời gian; phần khác hình thành do thiếu thông tin, thay đổi yêu cầu hoặc sự phát triển của hệ thống.

Khái niệm “nợ” thường được dùng như một phép so sánh:

- **Khoản gốc (*principal*):** công sức cần để cải thiện lựa chọn kỹ thuật, ví dụ tập trung một chính sách bị sao chép và bảo vệ nó bằng test.
- **Chi phí lặp lại (*interest*):** thời gian, sai sót hoặc rủi ro phát sinh khi tiếp tục thay đổi hệ thống mà chưa giải quyết nguyên nhân.
- **Quyết định trả nợ:** bỏ công sức hôm nay nhằm giảm chi phí/rủi ro trong tương lai, có tính đến lợi ích và những đánh đổi mới.

Đây là **mô hình tư duy**, không phải công thức tài chính chính xác. Có những rủi ro bảo mật hoặc mất dữ liệu không nên quy đổi đơn giản thành tiền. Cũng có những khoản nợ không phát sinh thêm chi phí đáng kể vì phần mã không còn thay đổi.

### 2.1. Phân biệt bốn loại nhận định

| Nhận định | Điều đã biết | Cần làm gì tiếp? |
| --- | --- | --- |
| “Phương thức này dài 140 dòng.” | Có **dấu hiệu cấu trúc**, có thể là mùi mã. | Hỏi trách nhiệm, tần suất thay đổi và trở ngại thực tế. |
| “Mỗi lần đổi ngưỡng đều phải sửa bốn nơi.” | Có **chi phí thay đổi lặp lại** gắn với cấu trúc. | Kiểm tra nguồn sự thật, lịch sử sửa và lựa chọn xử lý. |
| “Đơn đúng ngưỡng bị tính phí sai.” | Có **lỗi chức năng** nếu trái đặc tả. | Ưu tiên khắc phục lỗi và test hồi quy; đồng thời xem có nợ cấu trúc góp phần không. |
| “Chúng ta dùng cách đơn giản để kịp thử nghiệm, chấp nhận sửa lại khi có hai biến thể.” | Có **đánh đổi có chủ đích** và điều kiện xem lại. | Ghi rõ bối cảnh, người chịu trách nhiệm và tín hiệu kích hoạt xem lại. |

Một đoạn mã có thể vừa chứa lỗi vừa chứa nợ kỹ thuật. Khi ấy, **sửa lỗi đúng đắn** và **xử lý nguyên nhân cấu trúc** là hai phần công việc cần được nhận diện, dù có thể triển khai trong cùng kế hoạch.

### 2.2. Không phải mọi thứ “chưa tối ưu” đều phải ghi nợ

Ví dụ: một phép quét danh sách 12 phần tử bằng `List.contains` hoàn toàn đáp ứng mục tiêu, không gây chi phí bảo trì và không có dấu hiệu quy mô tăng. Việc nó chưa dùng `HashSet` không tự tạo thành nợ kỹ thuật đáng ưu tiên.

Ngược lại, một cache thiếu chính sách hết hạn có thể chưa gây sự cố hôm nay nhưng chứa **rủi ro dữ liệu lỗi thời có cơ chế rõ**; không cần chờ lỗi ảnh hưởng người dùng mới được ghi nhận.

## 3. Vì sao ghi “cần refactor” là chưa đủ?

Các mô tả sau khó giúp một nhóm quyết định:

- “Code này bẩn.”
- “Technical debt lớn.”
- “Class quá dài, nên tách.”
- “Coverage thấp, cần viết thêm test.”
- “Chỗ này làm hệ thống chậm.”

Chúng thiếu ít nhất một trong các thông tin: **công việc bị ảnh hưởng**, **bằng chứng**, **cơ chế gây chi phí**, **mức độ ưu tiên** hoặc **cách đánh giá cải thiện**.

So sánh hai bản ghi:

| Bản ghi mơ hồ | Bản ghi có thể hành động |
| --- | --- |
| “Trùng code xử lý SKU, nên gom lại.” | “Trong đợt đổi chuẩn mã SKU sang không phân biệt chữ hoa–thường, API đã được sửa còn luồng nhập CSV vẫn giữ quy tắc cũ. Test tích hợp của nhập CSV không phát hiện, khiến cùng mã được xử lý khác nhau giữa hai đường. Cần xác nhận một chính sách chuẩn hóa dùng chung và test hai đường nhập.” |
| “Query chậm.” | “Với kịch bản lấy 100 đơn và thông tin khách hàng, trace cho thấy một truy vấn danh sách rồi 100 truy vấn khách hàng. Nếu việc truy vấn lặp là nguyên nhân độ trễ trong mẫu tải đại diện, hãy xem batch fetch/join và đo lại cả số truy vấn lẫn bộ nhớ.” |
| “Lớp quá nhiều trách nhiệm.” | “Ba yêu cầu không liên quan trong bốn PR gần đây đều sửa `OrderManager`, thường xung đột cùng các field mutable. Review cần xác định nhóm trách nhiệm và bất biến chung trước khi tách.” |

Các ví dụ trong bài là **tình huống minh họa**, không phải sự cố có thật của một công ty hay kết quả đo đã diễn ra.

## 4. Một chuỗi bằng chứng tốt có sáu mắt xích

Có thể dùng mô hình:

~~~text
(1) Bối cảnh / tình huống thay đổi
                   |
                   v
(2) Quan sát có thể kiểm chứng
                   |
                   v
(3) Cơ chế kỹ thuật gây cản trở
                   |
                   v
(4) Tác động và phạm vi ảnh hưởng
                   |
                   v
(5) Phương án xử lý và đánh đổi
                   |
                   v
(6) Tiêu chí kiểm tra sau xử lý
~~~

### 4.1. Bối cảnh: khi nào vấn đề biểu hiện?

Ví dụ: “Thêm chuẩn mã sản phẩm mới cho cả API và import CSV”, “Khắc phục lỗi timeout của nhà cung cấp”, “Thay cấu hình quota khi tăng số instance”.

**Tình huống phải đủ cụ thể để tái hiện hoặc đối chiếu**, không chỉ “khi có thay đổi”.

### 4.2. Quan sát: đã nhìn thấy điều gì?

Ví dụ:

- Một pull request sửa hai trong ba bản sao của cùng một quy tắc.
- Test cho đường API đỗ, còn cùng dữ liệu đưa qua CSV cho kết quả khác.
- Một request tạo 101 lần gọi truy vấn theo trace đã thu thập.
- Trong sự cố, hai luồng cùng xác nhận đã giữ chỗ dù tổng quota bị vượt.

Chỉ ghi điều thực sự đã quan sát, với nguồn dẫn phù hợp. Nếu chỉ là kịch bản chưa xảy ra, viết **“có thể xảy ra khi…”**, không biến thành sự cố thực.

### 4.3. Cơ chế: vì sao cấu trúc tạo chi phí?

Tìm mối liên hệ kỹ thuật:

- Quy tắc bị sao chép nên thay đổi không lan sang mọi nơi.
- Dữ liệu request nằm trong field singleton nên lời gọi đồng thời có thể ghi đè.
- Không có hợp đồng lỗi chung nên mỗi client phải tự đoán kết quả.
- Logic đọc thời gian trực tiếp khiến test không tái tạo được mốc ngày.
- ORM tải dữ liệu theo từng phần tử nên phát sinh nhiều round trip.

Giải thích **cơ chế có thể kiểm chứng**, không kết luận “do code xấu” hoặc đổ lỗi cá nhân.

### 4.4. Tác động: chuyện đó gây hại thế nào?

Tác động có thể là:

- Hành vi sai hoặc không nhất quán với hợp đồng.
- Tăng thời gian sửa một yêu cầu tương tự.
- Tăng số nơi phải sửa và nguy cơ bỏ sót.
- Test không ổn định, cần môi trường khó dựng.
- Độ trễ, CPU, bộ nhớ hoặc tải hệ thống phụ thuộc tăng.
- Khó rollback, phục hồi hoặc điều tra sự cố.
- Rủi ro bảo mật, lộ dữ liệu hoặc mất khả năng kiểm soát quyền.

### 4.5. Phương án: thay đổi gì để giảm tác động?

Một hướng xử lý phải gắn với **cơ chế**, không chỉ làm đẹp chỉ số. Ví dụ, đặt chính sách SKU ở một ranh giới có trách nhiệm và dùng chung hai điểm nhập; thêm test ở cả hai đường; không cần dựng ngay một “rule engine” tổng quát.

### 4.6. Tiêu chí: làm sao biết cải thiện?

Phân biệt hai nhóm:

- **Hành vi được bảo vệ:** hai luồng tạo cùng mã chuẩn, lỗi đầu vào xử lý đúng, dữ liệu không thay đổi ngoài chủ đích.
- **Chi phí/rủi ro giảm:** thay đổi chuẩn mã tiếp theo có một nơi quyết định, ít nơi phải sửa hơn, test phát hiện sai lệch và thời gian điều tra hợp lý hơn.

Tăng điểm quality metric nhưng **không giải quyết tình huống từng gây cản trở** chưa phải bằng chứng mạnh rằng khoản nợ đã được trả.

## 5. Hai loại tình huống nên dùng để ghi tác động

### 5.1. Tình huống thay đổi (*change scenario*)

Dùng khi nợ kỹ thuật làm một yêu cầu **khó thực hiện hoặc dễ phát sinh sai sót**.

Mẫu câu:

> “Khi cần [thay đổi nghiệp vụ hoặc kỹ thuật], nhóm phải [công việc phụ/trở ngại] vì [cấu trúc hoặc phụ thuộc]. Điều đó dẫn đến [chi phí/rủi ro], được thể hiện qua [PR/test/bằng chứng].”

Ví dụ: “Khi đổi chuẩn mã SKU, đội sửa hai bộ chuyển đổi riêng. Việc không có một nguồn quy tắc chung khiến import CSV vẫn trả mã cũ, buộc sửa thêm sau khi phát hiện sai lệch.”

Trường hợp chưa có sự cố, có thể viết: “Khi cần thêm loại khuyến mại thứ ba, hiện tại ba client sẽ phải được thay đổi theo cùng chính sách; chưa có bằng chứng lần thay đổi ấy đã xảy ra.”

**Không cần chờ một vụ việc xảy ra mới được ghi nhận**, nhưng phải tách rõ tác động **đã thấy** với rủi ro **dự kiến**.

### 5.2. Sự cố (*incident scenario*)

Dùng khi thiết kế đã góp phần vào một vấn đề quan sát được trong test, staging hoặc production.

Mẫu câu:

> “Vào [thời điểm/giai đoạn], [hành vi sai] xuất hiện dưới [điều kiện]. Phạm vi ảnh hưởng được xác định là [dữ liệu có căn cứ]. Điều tra cho thấy [cơ chế kỹ thuật], còn [các yếu tố khác] cần xác minh. Biện pháp tạm thời là [cách xử lý]; khoản nợ liên quan là [nguyên nhân cấu trúc cần xử lý lâu dài].”

Ví dụ: hai đường nhận SKU cho kết quả khác nhau khiến cùng một mặt hàng xuất hiện dưới hai định danh khi đối chiếu.

Một incident cần ghi cả **những gì chưa biết**. Nếu mới thấy sự tương quan với thay đổi, chưa được khẳng định chắc chắn nguyên nhân.

### 5.3. Thay đổi và sự cố là hai góc nhìn bổ sung

Tình huống thay đổi giúp thấy **chi phí lặp lại** trước khi thành lỗi. Sự cố cung cấp bằng chứng về **rủi ro đã hiện thực hóa**. Không phải khoản nợ nào cũng có incident; không phải incident nào cũng do nợ kỹ thuật.

## 6. Ví dụ Java: cùng quy tắc SKU nhưng hai đường xử lý

Giả sử ứng dụng nhận mã sản phẩm qua **API** và **tệp CSV nhập hàng**.

Quy tắc nghiệp vụ mới được xác nhận:

- Mã được bỏ khoảng trắng ASCII ở hai đầu theo ngữ nghĩa `String.trim()`.
- Mã được chuyển sang chữ hoa theo quy tắc **không phụ thuộc locale mặc định**.
- Hai đầu vào có cùng chữ cái nhưng khác chữ hoa–thường phải tạo **cùng mã chuẩn**.
- `null` là đầu vào không hợp lệ và phải bị từ chối.
- Ví dụ này chỉ xét chuẩn hóa chuỗi; kiểm tra SKU có tồn tại, phân quyền, dữ liệu trùng và ghi database nằm ở ranh giới khác.

Trước đây, cả hai đường chỉ bỏ khoảng trắng. Trong lần đổi yêu cầu, nhóm cập nhật API nhưng bỏ sót CSV. **Đây là tình huống giả định để học cách ghi nhận tác động**, không phải dữ liệu sự cố thật.

### 6.1. Mã có dấu hiệu rủi ro sau thay đổi

~~~java
import java.util.Locale;
import java.util.Objects;

final class ApiSkuParser {
    static String parse(String rawSku) {
        Objects.requireNonNull(rawSku, "rawSku");
        return rawSku.trim().toUpperCase(Locale.ROOT);
    }
}

final class CsvSkuParser {
    static String parse(String rawSku) {
        Objects.requireNonNull(rawSku, "rawSku");
        return rawSku.trim(); // Đường này chưa nhận quy tắc mới.
    }
}
~~~

Hai phương thức ngắn, dễ đọc và không có class “God Object”. Một số chỉ số độ dài mã vẫn có thể rất đẹp. Nhưng **tri thức chuẩn hóa mã đang có hai bản triển khai khác nhau**, nên khi yêu cầu đổi, chúng có thể lệch.

Với chuỗi đầu vào `" ab-12 "`:

~~~text
API:  " ab-12 " -> "AB-12"
CSV:  " ab-12 " -> "ab-12"

=> Hai mã chuẩn khác nhau cho cùng một SKU theo quy tắc mới.
~~~

### 6.2. Nhận diện chính xác vấn đề

**Lỗi được phát hiện:** CSV không chuyển mã thành chữ hoa theo yêu cầu hiện tại.

**Khoản nợ tiềm năng phía sau:** không có một nơi chịu trách nhiệm duy nhất cho quy tắc chuẩn hóa **được kỳ vọng dùng chung** giữa hai đường nhập; mỗi lần thay đổi phải sửa nhiều điểm.

Hai nhận định khác nhau:

1. Nếu chỉ sửa `CsvSkuParser`, lỗi hiện tại có thể biến mất, nhưng hai bản quy tắc vẫn còn và có thể lệch trong lần đổi sau.
2. Nếu tập trung chính sách mà **không xác nhận** API và CSV phải có cùng ngữ nghĩa, có thể vô tình gộp hai nghiệp vụ vốn cần khác nhau. Chẳng hạn, CSV lưu nội dung gốc cho audit vẫn phải bảo tồn chuỗi đầu vào ở một trường khác.

Vì thế, **điều tra hợp đồng trước khi gộp** là bắt buộc. Trong ví dụ, đã xác nhận cả hai đường cùng cần trả mã chuẩn cho tra cứu; lưu chuỗi gốc nếu cần là trách nhiệm khác.

### 6.3. Viết một test tái hiện sai lệch

Ví dụ JUnit 5 dưới đây có thể dùng để **chứng minh hiện trạng chưa đáp ứng quy tắc mới**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SkuConsistencyRegressionTest {
    @Test
    void apiAndCsvMustProduceSameNormalizedCode() {
        String raw = " ab-12 ";

        assertEquals("AB-12", ApiSkuParser.parse(raw));
        assertEquals("AB-12", CsvSkuParser.parse(raw)); // FAIL ở bản cũ.
    }
}
~~~

Test này có giá trị vì nó kiểm tra **hợp đồng dùng chung có ý nghĩa**. Khi chạy với mã mục 6.1, assertion thứ hai thất bại một cách xác định.

Trong bài học, mã là ví dụ; không khẳng định đã chạy JUnit thật. Mục tiêu là chỉ ra một **kịch bản kiểm chứng được**, khác với nói chung chung “có duplicate code”.

### 6.4. Khoản nợ nên được mô tả ra sao?

Một bản ghi chất lượng có thể viết:

> “Hai đường nhận mã sản phẩm hiện tự duy trì phép chuẩn hóa SKU. Trong thay đổi chuyển sang không phân biệt chữ hoa–thường, chỉ parser API được cập nhật; parser CSV vẫn trả mã chữ thường. Test `apiAndCsvMustProduceSameNormalizedCode` tái hiện sự khác biệt. Cần xác nhận và đặt quy tắc chuẩn hóa chung ở một nơi, giữ hợp đồng của hai đường nhập, và bổ sung kiểm thử mỗi đường. Điều này giảm nguy cơ phải sửa nhiều bản sao trong các thay đổi quy tắc tiếp theo.”

Nó có **sự kiện thay đổi, biểu hiện, cơ chế, tác động và hướng kiểm chứng**. Không cần kết luận một lập trình viên nào đó “viết code kém”.

## 7. Phương án giảm nợ: tập trung quy tắc, không thêm trừu tượng thừa

Sau khi xác nhận cả API và CSV cần cùng quy tắc, có thể dùng một thành phần nhỏ:

~~~java
import java.util.Locale;
import java.util.Objects;

final class SkuNormalizer {
    private SkuNormalizer() {}

    static String normalize(String rawSku) {
        Objects.requireNonNull(rawSku, "rawSku");
        return rawSku.trim().toUpperCase(Locale.ROOT);
    }
}

final class ApiSkuParser {
    static String parse(String rawSku) {
        return SkuNormalizer.normalize(rawSku);
    }
}

final class CsvSkuParser {
    static String parse(String rawSku) {
        return SkuNormalizer.normalize(rawSku);
    }
}
~~~

Lúc này, một thay đổi về cách chuẩn hóa có **một nơi xác định quy tắc**. Hai phương thức ở ranh giới API và CSV vẫn có thể tồn tại nếu cần để thể hiện trách nhiệm tích hợp, kiểm tra dữ liệu nguồn hoặc xử lý lỗi đặc thù từng kênh.

Điều được cải thiện **không phải số phương thức giảm**. Thực tế phương án này có thêm một lớp; lợi ích đến từ việc **một quy tắc có chủ sở hữu rõ và không còn hai bản dễ lệch nhau**.

### 7.1. Vì sao dùng `Locale.ROOT`?

Một phép chuyển chữ hoa không nên phụ thuộc vào locale mặc định của server nếu SKU có hợp đồng không phụ thuộc vùng. `Locale.ROOT` giúp xác định quy tắc chuyển chữ rõ hơn.

Tuy nhiên, `String.toUpperCase(Locale.ROOT)` áp dụng ngữ nghĩa Unicode; nó **không tự định nghĩa đầy đủ bộ ký tự hợp lệ cho SKU**, không xử lý mọi yêu cầu chuẩn hóa Unicode và không bảo đảm một phép biến đổi một–một cho mọi mã có thể nhập. Nếu hợp đồng thực chỉ cho phép ASCII chữ/số và dấu gạch nối, việc kiểm tra miền ký tự phải được đặc tả và kiểm thử riêng, thay vì suy đoán từ ví dụ.

### 7.2. Khi nào gộp quy tắc sẽ không phù hợp?

Nếu parser CSV chỉ để lưu **dữ liệu gốc lịch sử** còn parser API có nhiệm vụ tạo mã chuẩn mới, hai hàm có thể cần ngữ nghĩa khác nhau. Gộp chúng chỉ vì cùng gọi `trim()` là một quyết định sai.

Do đó, điều kiện để xử lý khoản nợ đã nêu là **hai ranh giới thật sự chia sẻ cùng một hợp đồng chuẩn hóa**. Điều này phải được xác nhận trước khi refactor.

## 8. Kiểm thử sau thay đổi: bảo vệ tình huống đã gây nợ

Bộ test JUnit 5 cho phương án ở mục 7:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class SkuNormalizationTest {
    @Test
    void bothEntryPointsUseTheSameContract() {
        for (String raw : List.of(" ab-12 ", "Ab-12", "AB-12")) {
            assertEquals("AB-12", ApiSkuParser.parse(raw));
            assertEquals("AB-12", CsvSkuParser.parse(raw));
        }
    }

    @Test
    void rejectsNullConsistently() {
        assertThrows(NullPointerException.class,
                () -> ApiSkuParser.parse(null));
        assertThrows(NullPointerException.class,
                () -> CsvSkuParser.parse(null));
    }

    @Test
    void doesNotChangeAlreadyNormalizedCode() {
        assertEquals("SKU-100", SkuNormalizer.normalize("SKU-100"));
    }
}
~~~

Bộ test xác minh hành vi ở mức **hai điểm nhập Java**; nếu CSV thật còn có parser file, mã hóa ký tự, cột dữ liệu hoặc lưu database, cần **integration test** để bảo vệ đường đi toàn phần.

Một cách kiểm tra bổ sung hữu ích là test bảo đảm **dữ liệu gốc được giữ đúng nếu hợp đồng yêu cầu**, đồng thời giá trị dùng cho tra cứu được chuẩn hóa. Không nên thêm logic làm mất thông tin lịch sử chỉ để loại trùng.

### 8.1. Phân biệt sửa bug và trả nợ

Trong ví dụ:

- **Bug fix:** bảo đảm đường CSV tuân thủ chính sách chuẩn hóa mới.
- **Debt paydown:** ngăn quy tắc bị nhân bản rồi lệch tiếp trong lần thay đổi sau.
- **Validation:** test kiểm tra nhất quán; nếu đường nhập thực sự đi qua database, cần test tích hợp tương ứng.
- **Future benefit:** một nơi sửa quy tắc; giảm nguy cơ bỏ sót, nhưng cần theo dõi qua các thay đổi sau chứ không tuyên bố đã tiết kiệm thời gian cụ thể khi chưa đo.

Hai phần có thể đi cùng một PR có review rõ, hoặc tách bước để giảm rủi ro. **Không nên gọi một thay đổi nghiệp vụ có chủ đích là “refactor giữ nguyên hành vi”**.

## 9. Mẫu phiếu ghi nhận nợ kỹ thuật có thể dùng trực tiếp

Một phiếu ghi nhận nên ngắn đủ để được duy trì, nhưng đủ thông tin để người khác hiểu và ưu tiên.

~~~markdown
# [Nợ kỹ thuật] <Tên ngắn gắn với cơ chế và tác động>

## Bối cảnh / tình huống
Khi cần <thay đổi> hoặc khi xảy ra <sự cố>, hệ thống cần <hành vi mong đợi>.

## Quan sát có bằng chứng
- Hiện trạng: <hành vi hoặc trở ngại đã thấy>
- Nguồn: <PR/commit/test/trace/issue/incident có thể tra lại>
- Phạm vi: <module/luồng người dùng/môi trường/thời điểm>
- Điều chưa xác nhận: <nếu có>

## Giả thuyết về cơ chế kỹ thuật
<Thiết kế hoặc phụ thuộc nào làm thay đổi khó/sai; cách kiểm tra giả thuyết>

## Tác động
- Đã xảy ra: <chi phí thời gian/rủi ro/lỗi có căn cứ>
- Có thể lặp lại khi: <tình huống cụ thể>
- Mức ảnh hưởng: <người dùng, dữ liệu, vận hành hoặc đội bảo trì>

## Phương án và đánh đổi
- Phương án A: <cách giảm nguyên nhân>
- Phương án B: <giữ hiện trạng có kiểm soát hoặc giải pháp khác>
- Chi phí/rủi ro khi thay: <test, tương thích, migration, rollback>

## Điều kiện hoàn thành
- Hành vi: <test/contract cần đỗ>
- Chất lượng thay đổi: <điểm cần giảm rủi ro/công sức>
- Kiểm tra sau xử lý: <cách đo và thời điểm đánh giá>

## Theo dõi
Chủ sở hữu: <nhóm hoặc vai trò>
Mức ưu tiên: <lý do>
Trạng thái: <đang điều tra/đã xác nhận/đã lên kế hoạch/đang xử lý/đã kiểm chứng>
Ngày xem lại: <ngày hoặc sự kiện kích hoạt>
~~~

**Không phải mọi trường đều phải là biểu mẫu bắt buộc.** Với một rủi ro nhỏ, vài đoạn rõ ràng và link test có thể đủ. Với khoản nợ ảnh hưởng đến thanh toán hoặc nhiều service, mô tả ranh giới dữ liệu và phương án rollback có thể cần chi tiết hơn.

### 9.1. Bản ghi đã điền cho ví dụ SKU

| Trường | Ví dụ nội dung |
| --- | --- |
| Tên | Quy tắc chuẩn hóa SKU bị nhân bản giữa API và CSV. |
| Tình huống | Chuyển chính sách thành không phân biệt chữ hoa–thường. |
| Hiện trạng | API trả `AB-12`, CSV trả `ab-12` với cùng đầu vào. |
| Bằng chứng | Test `apiAndCsvMustProduceSameNormalizedCode` thất bại ở bản cũ. |
| Cơ chế | Hai parser duy trì cùng một quy tắc ở hai chỗ. |
| Tác động hiện tại | Hai đường nhập không nhất quán theo đặc tả mới. |
| Rủi ro về sau | Khi chuẩn đổi tiếp, một điểm có thể tiếp tục bị bỏ sót. |
| Hướng xử lý | Một `SkuNormalizer` dùng chung ở các luồng cần mã chuẩn. |
| Bảo vệ hành vi | Test JUnit cho hai đầu vào và tích hợp import khi cần. |
| Tiêu chí kiểm chứng | Một chính sách, hai đường trả kết quả nhất quán; test đỗ. |

Bảng này là **hồ sơ giả định được xây dựng từ ví dụ**, không đại diện số liệu sản xuất.

## 10. Gắn bằng chứng cụ thể mà không tiết lộ dữ liệu nhạy cảm

Một phiếu nợ kỹ thuật cần nguồn có thể tra cứu; nhưng không nên sao chép toàn bộ log production, token, email khách hàng hoặc payload thanh toán vào issue cho dễ minh họa.

Các nguồn thường phù hợp:

- **PR/commit:** sự thay đổi nào làm bộc lộ vấn đề và bao nhiêu nơi phải sửa.
- **Test hồi quy:** đầu vào và kết quả kỳ vọng tái hiện sự khác biệt.
- **Incident report:** thời điểm, phạm vi, tác động, những điều đã xác minh.
- **Trace/metrics:** tỷ lệ lỗi, số truy vấn, thời gian xử lý theo điều kiện đo cụ thể.
- **Review discussion:** vì sao người bảo trì khó xác định ranh giới hoặc phải sửa nhiều nơi.
- **ADR/thiết kế:** ràng buộc có chủ đích khiến khoản nợ được chấp nhận ban đầu.

Chọn **link hoặc mã tham chiếu được phân quyền**, kèm mô tả tối thiểu, thay vì chép dữ liệu nhạy cảm vào nhiều công cụ.

### 10.1. Bằng chứng yếu cần được ghi là yếu

Các nhận xét như “có vẻ xử lý chậm”, “ai cũng ghét lớp này” hoặc “nhiều người nói khó sửa” có thể là **tín hiệu khởi đầu**. Chúng nên dẫn tới câu hỏi kiểm tra, không được trình bày như đã đo chính xác.

Ví dụ có thể viết:

> “Giả thuyết: phần lớn thời gian xử lý nằm trong vòng lặp gọi repository. Chưa có trace xác nhận. Cần đo số truy vấn và phân bố độ trễ cho kịch bản báo cáo 100 đơn trước khi quyết định tối ưu.”

Câu này bảo toàn mức độ chắc chắn, tránh đưa ra quyết định kiến trúc trên một giả định chưa được kiểm tra.

## 11. Đo tác động của nợ kỹ thuật: chọn chỉ số theo câu hỏi

Tác động của nợ kỹ thuật không phải lúc nào cũng quy đổi thành “số giờ bị mất”. Thông thường nên bắt đầu từ câu hỏi hành động:

> “Khoản nợ này đang khiến thay đổi X khó hơn thế nào, và những tín hiệu nào sẽ khác sau khi xử lý?”

### 11.1. Chi phí thực hiện thay đổi

Có thể theo dõi:

- Số nơi phải sửa cho **một quy tắc**.
- Số lượt review phải trao đổi vì không rõ chủ sở hữu.
- Công sức phải viết các bản sửa giống nhau ở nhiều module.
- Thời gian chờ do tích hợp và test khó tạo.
- Số lần sửa bổ sung vì quên cập nhật một nhánh.
- Thời gian từ khi nhận yêu cầu đến lúc test xác nhận hành vi.

Nhưng các chỉ số này chịu ảnh hưởng của **độ khó yêu cầu và quy mô thay đổi**. Không nên so sánh bừa bãi một thay đổi nhỏ hôm nay với một dự án phức tạp năm trước rồi khẳng định refactor làm tiết kiệm số giờ cụ thể.

### 11.2. Rủi ro lỗi và ảnh hưởng tới người dùng

Có thể xem:

- Loại lỗi đã phát sinh và điều kiện tái hiện.
- Phạm vi người dùng/yêu cầu hoặc dữ liệu chịu tác động, khi có bằng chứng.
- Số lần rollback hoặc hotfix có quan hệ với cơ chế nợ.
- Thời gian khôi phục và khó khăn khi chẩn đoán.
- Các tình huống lỗi hoặc mất dữ liệu có thể xảy ra theo lập luận kỹ thuật.

**Một sự cố nghiêm trọng** có thể đủ để ưu tiên, dù tần suất chưa cao. Ngược lại, việc chưa từng có sự cố không chứng minh thiết kế không có rủi ro.

### 11.3. Hiệu năng và tài nguyên

Khi khoản nợ liên quan hiệu năng, dùng phép đo phù hợp:

- Số truy vấn database mỗi yêu cầu.
- CPU hoặc memory cấp phát theo tình huống.
- p95/p99 độ trễ với mẫu tải tương đương.
- Số lần retry, backlog queue hoặc tỷ lệ timeout.
- Chi phí vận hành tính trên đơn vị tải khi có dữ liệu đáng tin.

Một cảnh báo “phương thức nhiều dòng” không giúp kết luận tăng bộ nhớ. **Bằng chứng phải khớp với cơ chế kỹ thuật đang nghi ngờ.**

## 12. Một ví dụ định lượng — và giới hạn của nó

Giả sử trong một bài tập **hoàn toàn minh họa**, nhóm ghi lại ba yêu cầu thay đổi chính sách trước khi tập trung quy tắc, rồi một số yêu cầu tương đương sau khi sửa.

| Quan sát minh họa | Trước khi xử lý | Sau khi xử lý |
| --- | --- | --- |
| Số nơi chứa công thức chuẩn hóa SKU | 2 | 1 nơi chịu trách nhiệm chính |
| Số điểm nhập cần được kiểm tra | API và CSV | API và CSV |
| Một lần đổi quy tắc phải sửa ở bao nhiêu nơi có thuật toán? | 2 | 1 |
| Test chứng minh hai đường dùng cùng chuẩn | Chưa có | Có test ở hai entry point |
| Chi phí hiệu chỉnh trong các lần thay đổi sau | Chưa đủ dữ liệu đáng tin | Cần theo dõi, chưa kết luận |

Bảng minh họa chỉ một cải thiện **cấu trúc và khả năng kiểm chứng**, không khẳng định thời gian sửa mã đã giảm theo một tỷ lệ nào.

### 12.1. Vì sao không nên tự gán “tiết kiệm 40% thời gian”?

Một lần thay đổi sau refactor có thể nhanh hơn vì:

- Yêu cầu đơn giản hơn.
- Người viết đã quen mã.
- Test hoặc môi trường CI tốt hơn.
- Không có sự cố hạ tầng.
- Refactor thực sự loại bỏ nhiều nơi phải sửa.

Muốn đo tác động về thời gian, cần chọn những yêu cầu đủ tương đồng, ghi nhận các yếu tố thay đổi và tránh quy kết toàn bộ cải thiện cho một nguyên nhân. **Tương quan trước–sau không tự chứng minh quan hệ nhân quả.**

### 12.2. Công thức ước lượng chỉ là công cụ ưu tiên

Khi có dữ liệu, có thể dùng cách ước lượng thô:

\[
\text{Chi phí lặp lại kỳ vọng}
\approx
\text{Tần suất thay đổi}
\times
\text{Công sức phụ trội mỗi lần}
+
\text{Rủi ro sự cố kỳ vọng}
\]

Trong đó **rủi ro sự cố kỳ vọng** cần được mô tả cùng đơn vị nếu định cộng thành một con số; không thể cộng trực tiếp “giờ” với “mức độ nghiêm trọng”. Cũng không thể ước lượng xác suất sự cố đáng tin từ một lần xảy ra duy nhất.

Thực tế, một bảng **tác động – tần suất – mức chắc chắn – chi phí xử lý** có thể trung thực và hữu ích hơn một con số “lãi nợ” giả chính xác.

## 13. Ưu tiên xử lý khi backlog chứa nhiều khoản nợ

Một danh sách có 50 cảnh báo static analysis không có nghĩa cần 50 nhiệm vụ refactor trước khi phát triển tính năng mới. Thứ tự ưu tiên nên dựa trên bối cảnh.

| Yếu tố | Câu hỏi ưu tiên |
| --- | --- |
| **Tác động** | Nếu lỗi xảy ra hoặc việc sửa bị chặn, ảnh hưởng người dùng/dữ liệu/vận hành lớn thế nào? |
| **Khả năng gặp lại** | Quy tắc hoặc module này có thường thay đổi trong tương lai gần không? |
| **Bằng chứng hiện tại** | Đã có incident, PR phải sửa nhiều nơi, test khó tạo hoặc phép đo chậm chưa? |
| **Rủi ro khi không xử lý** | Có nguy cơ bảo mật, nhất quán, mất dữ liệu hoặc sự cố lan rộng không? |
| **Chi phí cải thiện** | Phạm vi ảnh hưởng, migration, test và thời gian triển khai ra sao? |
| **Rủi ro của refactor** | Có khả năng làm đổi hành vi hoặc phá tương thích không? |
| **Điểm can thiệp thuận lợi** | Có một yêu cầu sắp chạm phần mã đó, giúp giảm chi phí xử lý không? |
| **Mức độ chắc chắn** | Đã xác minh nguyên nhân hay còn cần điều tra? |

### 13.1. Mức ưu tiên không nên chỉ dựa trên số lần xảy ra

Nếu một cơ chế có thể làm lộ dữ liệu của khách hàng giữa các request, cần đánh giá và xử lý theo quy trình bảo mật dù chưa có thống kê sự cố. Ngược lại, một helper dài 80 dòng nhưng dễ hiểu, ít thay đổi và có test đáng tin có thể không cần nằm đầu danh sách.

### 13.2. Không dùng “ROI” để bỏ qua rủi ro bắt buộc

Với yêu cầu bảo mật, dữ liệu hoặc tính tuân thủ là **ràng buộc phải đáp ứng**, nhóm không nên mặc cả bằng cách nói “xác suất thấp nên chưa đáng sửa” mà không có đánh giá rủi ro được phép và chủ sở hữu phù hợp.

Ước lượng tiết kiệm thời gian thích hợp hơn cho **lựa chọn cải thiện bảo trì**, khi các yêu cầu bắt buộc đã được bảo vệ.

## 14. Cân nhắc nhiều phương án, bao gồm giữ nguyên có kiểm soát

Một khoản nợ có bằng chứng không tự động chỉ có một cách xử lý.

### 14.1. Các phương án thường có

1. **Sửa lỗi trước, refactor sau:** khi cần khôi phục chức năng nhanh, tách quyết định sửa hành vi với thay cấu trúc có rủi ro.
2. **Refactor cục bộ:** đổi tên, thu hẹp trạng thái, gom quy tắc, trích xuất một trách nhiệm rõ.
3. **Thêm test và tài liệu:** khi chưa thể đổi kiến trúc an toàn, tăng khả năng phát hiện sai lệch và làm rõ hợp đồng.
4. **Dùng lớp tương thích tạm:** khi phải duy trì client cũ trong giai đoạn chuyển đổi.
5. **Thay đổi kiến trúc lớn hơn:** khi bằng chứng cho thấy vấn đề nằm ở ownership, dữ liệu, phiên bản hoặc ranh giới service.
6. **Chấp nhận nợ có theo dõi:** khi phần mã sắp ngừng sử dụng hoặc lợi ích refactor chưa đủ so với chi phí hiện tại.

### 14.2. Bảng lựa chọn cho ví dụ SKU

| Phương án | Lợi ích | Giới hạn/rủi ro |
| --- | --- | --- |
| Chỉ sửa parser CSV | Khôi phục hành vi nhanh, diff nhỏ. | Hai bản quy tắc vẫn có thể lệch trong tương lai. |
| Dùng một `SkuNormalizer` chung | Giảm nhân bản một chính sách; test tập trung. | Phải xác nhận hai đường cùng hợp đồng và triển khai nhất quán. |
| Xây rule engine tổng quát | Có thể hỗ trợ nhiều chính sách phức tạp trong tương lai. | Chi phí hiện tại lớn, abstraction có thể quá mức khi chỉ có một quy tắc. |
| Không sửa | Không tốn công ngay. | Không chấp nhận được nếu đường CSV đang sai đặc tả; chỉ có thể hoãn phần cải tiến cấu trúc sau khi bug đã xử lý. |

**Hành động đúng không phải luôn là “xóa mùi mã”**. Nó là lựa chọn giải quyết nguyên nhân với mức phức tạp và rủi ro tương xứng.

## 15. Khi sự cố đã xảy ra: kết nối incident với khoản nợ

Một incident report tốt tập trung vào khôi phục dịch vụ, phạm vi ảnh hưởng và nguyên nhân. Một bản ghi nợ kỹ thuật liên quan tập trung vào **vấn đề cấu trúc hoặc quy trình khiến loại sự cố đó dễ tái diễn**.

Hai hồ sơ nên **liên kết**, nhưng không cần sao chép toàn bộ.

### 15.1. Ví dụ cấu trúc hai bản ghi liên quan

**Incident (giả định):**

- Một đợt nhập CSV gặp sai lệch định danh SKU khi so với API.
- Điều kiện: mã đầu vào có chữ thường và khoảng trắng.
- Tái hiện được bằng test; đường API trả `AB-12`, CSV trả `ab-12`.
- Cần xác định dữ liệu nào đã đi qua luồng nhập thực tế và cách sửa an toàn; ví dụ bài học không có số liệu production.

**Debt item liên quan:**

- Cơ chế: hai parser sở hữu cùng một quy tắc chuẩn hóa.
- Rủi ro: lần đổi chính sách sau có thể tiếp tục tạo hai kết quả khác nhau.
- Phương án: một điểm định nghĩa quy tắc và test ở hai ranh giới.
- Điều kiện xong: test hồi quy đỗ, đường tích hợp phù hợp được kiểm tra; những bản sao không cần thiết đã được loại bỏ.
- Kết quả lâu dài: theo dõi các lần đổi chuẩn hóa sau, chưa khẳng định tự động hết mọi lỗi nhập hàng.

### 15.2. Tránh “một nguyên nhân duy nhất” khi chưa điều tra đủ

Trong incident thật, sai lệch có thể còn chịu ảnh hưởng của:

- Yêu cầu không được truyền đạt tới nhóm import.
- Chưa có test theo đường nhập CSV.
- Dữ liệu không đại diện trong môi trường test.
- Khác biệt giữa version triển khai của các service.
- Quy trình phát hành không kiểm tra hợp đồng giữa các thành phần.

Nợ kỹ thuật cấu trúc có thể là **một yếu tố góp phần**, chứ không phải toàn bộ lời giải thích. Cần tách nguyên nhân đã chứng minh khỏi giả thuyết đang điều tra.

### 15.3. Việc khắc phục sự cố chưa chắc trả hết nợ

Một hotfix có thể sửa ngay parser CSV. Điều này quan trọng để khôi phục tính đúng đắn. Nhưng nếu quy tắc vẫn bị nhân bản, khoản nợ chi phí thay đổi còn tồn tại.

Ngược lại, việc tập trung logic nhưng chưa sửa dữ liệu đã lưu sai trước đó cũng **chưa hoàn thành xử lý incident**. Mỗi phần có mục đích và điều kiện hoàn tất riêng.

## 16. Tình huống khác: N+1 truy vấn trong báo cáo

Giả sử người dùng phàn nàn báo cáo đơn hàng chạy chậm. Nhóm thấy một vòng lặp Java gọi repository để lấy khách hàng cho từng đơn.

~~~java
List<Order> orders = orderRepository.findRecent(100);
for (Order order : orders) {
    Customer customer = customerRepository.findById(
            order.customerId());
    // Xây dựng từng dòng báo cáo.
}
~~~

Đây là **mã phác họa**; các kiểu `Order`, `Customer` và repository chỉ đại diện cho hệ thống giả định, không phải đoạn độc lập biên dịch được.

### 16.1. Tín hiệu ban đầu

Câu “có vòng lặp gọi repository” là tín hiệu của khả năng phát sinh N+1 truy vấn, nhưng chưa chứng minh chính xác số query: repository có thể cache, batch hoặc truy cập nơi khác.

Cần đo **số lần truy vấn thực**, độ trễ và kích thước dữ liệu trên một kịch bản xác định.

### 16.2. Cách ghi nhận khi đã có phép đo

Ví dụ bản ghi sau là **số liệu minh họa cần được thay bằng trace thật khi dùng trong dự án**:

~~~text
Tình huống: Tạo báo cáo 100 đơn kèm tên khách hàng.
Quan sát giả định: Một truy vấn lấy đơn và 100 truy vấn lấy khách.
Giả thuyết: Vòng lặp gọi repository gây 101 round trip.
Tác động: Độ trễ tăng theo số đơn và tăng tải database.
Bằng chứng cần có: SQL trace, số query, thời gian p95 theo kích thước báo cáo.
Phương án: Batch fetch hoặc join phù hợp; kiểm tra trùng lặp dữ liệu.
Tiêu chí: Báo cáo giữ đúng nội dung và thứ tự, số query giảm trên mẫu đo.
Đánh đổi: Có thể tăng lượng dữ liệu trả về và bộ nhớ khi join.
~~~

### 16.3. Không kết luận từ một phép đo cô lập

Nếu query count giảm, vẫn cần đo độ trễ tổng thể và tài nguyên. Một join rất lớn có thể làm tăng bộ nhớ và dữ liệu lặp. Nếu báo cáo thực tế chỉ có ba đơn, hiệu quả có thể khác kịch bản 100 đơn.

Bằng chứng cần gắn với **tải thực, dữ liệu đại diện và tính đúng của báo cáo**, không phải chỉ một số “từ 101 còn 1” mà chưa rõ chi phí khác.

## 17. Tình huống khác: trạng thái ngầm làm lỗi khó tái hiện

Một service giữ `currentCustomerId` trong field mutable dù object service được chia sẻ giữa nhiều request. Có thể không có sự cố đã ghi, nhưng cơ chế kỹ thuật tạo rủi ro:

~~~java
final class CustomerContextService {
    private String currentCustomerId;

    String handle(String customerId) {
        currentCustomerId = customerId;
        return loadSummary(currentCustomerId);
    }

    private String loadSummary(String id) {
        return "Summary for " + id;
    }
}
~~~

Nếu hai luồng cùng gọi `handle`, luồng thứ nhất có thể đọc giá trị do luồng thứ hai vừa ghi. Ví dụ còn đơn giản hóa việc lấy thông tin khách hàng; trong hệ thống thật, nếu dữ liệu nhạy cảm được trả cho người không đúng, đó là **rủi ro bảo mật nghiêm trọng** phải đánh giá theo quy trình tương ứng.

### 17.1. Ghi nhận đúng mức độ chắc chắn

Không nên viết: “Đã rò rỉ dữ liệu khách hàng” nếu chưa có bằng chứng. Nên viết:

> “Service có field mutable chứa customer ID của từng request trong một instance dùng chung. Với lịch gọi xen kẽ, `handle(A)` có thể sử dụng ID của B. Chưa phát hiện sự cố production; cần đánh giá phạm vi chia sẻ instance, tái hiện bằng test đồng thời và bỏ trạng thái request không cần thiết.”

### 17.2. Phương án nhỏ và rõ ràng

~~~java
final class CustomerContextService {
    String handle(String customerId) {
        return loadSummary(customerId);
    }

    private String loadSummary(String id) {
        return "Summary for " + id;
    }
}
~~~

Lúc này trạng thái request được truyền trực tiếp. Với logic minh họa, không cần tạo mutex hoặc cache. Tuy nhiên, nếu `loadSummary` gọi database, cần xác minh phân quyền truy cập tại ranh giới phù hợp; **loại field không tự chứng minh toàn bộ hệ thống bảo mật đúng**.

Tình huống này cho thấy có thể ghi nợ bằng **kịch bản rủi ro xác định**, không cần chờ sự cố gây thiệt hại mới hành động.

## 18. Những lỗi thường gặp khi ghi nhận nợ kỹ thuật

### 18.1. Dùng nhãn “nợ kỹ thuật” thay cho bằng chứng

> “God Class — ưu tiên cao.”

Nhãn chỉ gợi ý một kiểu cấu trúc. Cần thêm: lần thay đổi nào phải sửa những trách nhiệm không liên quan, test khó ở điểm nào, ai bị chặn và hậu quả là gì?

### 18.2. Ghi ước lượng chi phí quá chính xác khi chưa đo

> “Mất 37,5% năng suất vì class này.”

Nếu không có thiết kế đo, so sánh và dữ liệu đáng tin, đó có thể là **con số tưởng tượng**. Tốt hơn nên nêu các ví dụ có thể kiểm tra: “Ba PR gần nhất đều phải sửa hai parser; một PR bỏ sót đường CSV”, kèm nguồn.

### 18.3. Quy kết cá nhân thay vì cơ chế

> “Do developer X viết ẩu nên nợ.”

Cách viết này không giúp tìm giải pháp và có thể khiến sự cố bị che giấu. Hãy tập trung vào yêu cầu, quyết định, ranh giới ownership và cơ chế kiểm thử/phát hành.

### 18.4. Xem mọi bug là nợ kỹ thuật

Một typo hoặc lỗi ở điều kiện biên có thể là bug mà không đại diện một khoản nợ cấu trúc lâu dài. Sau khi sửa, nếu không có cơ chế gây chi phí lặp lại, không cần gắn một nhãn nợ kỹ thuật để làm backlog phình ra.

### 18.5. Nhầm “nợ đã thanh toán” với “code đẹp hơn”

Một PR xóa trùng lặp nhưng tạo coupling giữa hai chính sách độc lập có thể làm giảm số dòng mà **tăng chi phí sửa đổi về sau**. Cần xem mục tiêu tác động ban đầu đã được giải quyết chưa.

### 18.6. Ghi nợ không có chủ sở hữu hoặc điều kiện xem lại

Một issue tồn tại nhiều năm với nội dung “TODO refactor” không giúp quyết định. Nên ghi khi nào cần xem lại, điều kiện kích hoạt ưu tiên và ai có quyền xác nhận thay đổi.

### 18.7. Không cập nhật hồ sơ khi giả thuyết bị bác bỏ

Nếu đo đạc cho thấy thời gian chậm nằm ở mạng chứ không ở vòng lặp Java, cần cập nhật hoặc đóng giả thuyết sai. Backlog nợ kỹ thuật là **hồ sơ quyết định đang tiến hóa**, không phải kho phán xét bất biến.

## 19. Quy trình thực hành khi một người phát hiện nợ trong PR

**Bước 1 — Nêu dấu hiệu bằng câu trung lập.** “Cùng logic chuẩn hóa SKU xuất hiện ở đường API và CSV.”

**Bước 2 — Chỉ ra tình huống bị tác động.** “Trong yêu cầu đổi chuẩn mã, hai đường cần cho cùng kết quả và đã từng cập nhật thiếu.”

**Bước 3 — Kiểm tra hợp đồng.** “Hai đường có thật sự dùng cùng chuẩn hay một đường phải giữ giá trị gốc?”

**Bước 4 — Tìm hoặc tạo bằng chứng.** Test tái hiện, PR liên quan, trace hoặc mô tả điều kiện đồng thời. Chỉ dùng dữ liệu giả khi chia sẻ công khai.

**Bước 5 — Đánh giá rủi ro và phạm vi.** Có ảnh hưởng dữ liệu đã lưu, tính tương thích, bảo mật hoặc người dùng không? Có phải bug cần sửa ngay không?

**Bước 6 — Đề xuất vài lựa chọn và đánh đổi.** Có thể sửa cục bộ, tập trung chính sách, thêm test trước, hoặc hoãn phần cấu trúc khi đã khôi phục hành vi.

**Bước 7 — Xác định tiêu chí hoàn thành.** Bảo toàn hợp đồng và giảm đúng cơ chế chi phí. Không chỉ đóng issue khi chỉ số complexity giảm.

**Bước 8 — Ghi chủ sở hữu và thời điểm xem lại.** Nếu chưa xử lý, có trigger rõ (ví dụ lần thêm kênh nhập SKU tiếp theo) và người chịu trách nhiệm.

**Bước 9 — Sau khi sửa, kiểm tra lại.** Test hành vi đỗ; có còn các bản sao quy tắc không? Khi một yêu cầu tương tự xuất hiện, việc đổi có dễ hơn theo quan sát thực tế không?

### 19.1. Nhận xét code review có thể hành động

> “Mình thấy parser API và CSV đều tự định nghĩa chuẩn hóa SKU. Với quy tắc mới không phân biệt chữ hoa–thường, chỉ API được cập nhật nên hai đường cho kết quả khác nhau với `" ab-12 "`. Có thể xác nhận hai điểm nhập phải dùng chung một quy tắc và tạo test cho cả hai không? Nếu đúng, một `SkuNormalizer` nhỏ sẽ giảm nguy cơ bỏ sót khi chuẩn thay đổi tiếp. Trường dữ liệu gốc của CSV, nếu cần cho audit, nên được giữ riêng.”

Nhận xét tập trung vào **tình huống và tác động**, không gắn nhãn tiêu cực cho người viết.

## 20. Bài tập tự đánh giá

### Tình huống A: class dài

Một class báo cáo 350 dòng, mỗi tháng chỉ sửa một lần, có test tin cậy và không có lỗi ghi nhận. Công cụ cho điểm cognitive complexity cao.

**Câu hỏi:** có đủ bằng chứng để ưu tiên refactor lên đầu backlog chưa?

**Gợi ý:** chưa. Hãy tìm các khó khăn thực tế hoặc tình huống sắp thay đổi: nhiệm vụ sửa có phải chạm nhiều trách nhiệm, thời gian review cao do nguyên nhân gì, test có khó tạo không? Điểm công cụ là tín hiệu, không thay thế tác động.

### Tình huống B: ba lần sửa cùng một chính sách

Nhóm sửa ngưỡng vận chuyển ở ba module trong mỗi đợt thay đổi. Một lần quên sửa module xuất hóa đơn, dẫn tới sai số tiền hiển thị.

**Câu hỏi:** viết hai bản ghi gì và chúng liên quan thế nào?

**Gợi ý:** ghi bug/sự cố hóa đơn sai để khôi phục tính đúng, đồng thời ghi nợ cấu trúc nhân bản chính sách khiến thay đổi phải đồng bộ nhiều nơi. Có thể ưu tiên một nguồn sự thật nếu các module dùng cùng hợp đồng; giữ test cho hành vi theo thời điểm nghiệp vụ.

### Tình huống C: tối ưu hóa thiếu số liệu

Một lập trình viên đề nghị viết lại toàn bộ đường xử lý bằng cache vì “đọc database quá chậm”.

**Câu hỏi:** cần bằng chứng nào trước khi ưu tiên?

**Gợi ý:** truy vấn nào đang chậm, trong mẫu tải nào, tỷ lệ thời gian nằm ở đâu? Cần trace, số truy vấn, độ trễ, mức sử dụng tài nguyên và ràng buộc nhất quán. Cache có thể tạo nợ kỹ thuật mới nếu dữ liệu lỗi thời hoặc khóa không đủ.

### Tình huống D: trạng thái dùng chung

Một singleton giữ `currentUserId` cho từng request. Chưa có incident, nhưng service có thể được gọi đồng thời.

**Câu hỏi:** có được ghi nhận nợ/rủi ro khi chưa có sự cố không?

**Gợi ý:** được, nếu mô tả cơ chế race condition rõ và xác định điều kiện kiểm chứng. Nếu có khả năng lộ dữ liệu, đánh giá ưu tiên bảo mật ngay; không chờ thống kê incident.

### Tình huống E: quyết định chấp nhận nợ có chủ đích

Một đội dùng cách triển khai thủ công cho thử nghiệm hai tuần, chưa xây engine tổng quát. Họ có test cho hành vi đang dùng và xác định sẽ xem lại khi có trên ba biến thể chính sách.

**Câu hỏi:** có phải mọi lựa chọn chưa tổng quát đều là khoản nợ xấu?

**Gợi ý:** không. Đây có thể là một đánh đổi hợp lý, được giới hạn bằng giả định và trigger xem lại. Chỉ nên mở rộng thiết kế khi nhu cầu và tác động chứng minh lợi ích.

## 21. Checklist trước khi báo cáo và xử lý một khoản nợ

- [ ] Tôi mô tả **tình huống thay đổi, sự cố hoặc kịch bản rủi ro** cụ thể.
- [ ] Tôi phân biệt rõ **điều đã xảy ra** với **điều có thể xảy ra**.
- [ ] Có bằng chứng có thể truy lại: test, PR, trace, report hoặc lập luận kỹ thuật.
- [ ] Tôi đã xác định **cơ chế thiết kế** gây chi phí/rủi ro, không chỉ đặt tên mùi mã.
- [ ] Tôi biết những người dùng, nhóm bảo trì, dữ liệu hoặc quy trình chịu ảnh hưởng.
- [ ] Các chi phí định lượng có đơn vị, phạm vi và điều kiện đo rõ ràng.
- [ ] Tôi không tự gán phần trăm tiết kiệm hoặc xác suất sự cố khi chưa có dữ liệu.
- [ ] Tôi phân biệt bug cần sửa với nợ cấu trúc có thể gây tái diễn.
- [ ] Nếu có rủi ro bảo mật/mất dữ liệu, tôi không hạ ưu tiên bằng lý do “chưa có incident”.
- [ ] Tôi đã kiểm tra hai đoạn mã giống nhau có thực sự cùng trách nhiệm hay không.
- [ ] Phương án xử lý đánh trúng nguyên nhân thay vì chỉ xóa cảnh báo công cụ.
- [ ] Tôi đã cân nhắc chi phí và rủi ro mới do refactor, cache, abstraction hoặc di chuyển logic.
- [ ] Có test bảo vệ kết quả, ngoại lệ, giá trị biên và tác dụng phụ liên quan.
- [ ] Điều kiện hoàn thành gồm **tính đúng đắn** và **tác động được cải thiện**.
- [ ] Hồ sơ có chủ sở hữu, trạng thái, điểm xem lại và các giả định chưa xác minh.
- [ ] Nếu giả thuyết bị bác bỏ, tôi sẽ sửa hoặc đóng hồ sơ thay vì giữ một kết luận sai.
- [ ] Mọi bằng chứng chia sẻ đều không chứa bí mật hoặc dữ liệu nhạy cảm không cần thiết.

## 22. Kết luận

**Ghi nhận tác động của nợ kỹ thuật bằng tình huống thay đổi hoặc sự cố cụ thể** giúp đưa cuộc thảo luận từ “mã này trông xấu” sang “thiết kế này đã gây trở ngại gì, có thể gây rủi ro gì, và sửa như thế nào mới đáng công sức”.

Một hồ sơ hữu ích cần cho biết **bối cảnh**, **quan sát**, **cơ chế**, **tác động**, **phương án** và **điều kiện kiểm chứng**. Có thể dùng sự cố đã xảy ra, thay đổi từng bị chậm hoặc kịch bản rủi ro có lập luận rõ; nhưng phải trung thực về mức độ bằng chứng và không biến giả thuyết thành khẳng định.

Trong **CODE_QUALITY_FUNDAMENTALS**, cách nhìn này hỗ trợ mục tiêu xây dựng mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Khi nhóm ghi lại đúng nguồn tạo chi phí, ưu tiên theo ảnh hưởng và xác minh sau cải thiện, nợ kỹ thuật trở thành **vấn đề kỹ thuật có thể quản lý**, không phải một nhãn dán lên mọi đoạn mã chưa hoàn hảo.

