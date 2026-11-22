# Chọn cấp kiểm thử theo rủi ro và chi phí phản hồi

> **Chương:** Bằng chứng kiểm thử  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao **bằng chứng kiểm thử** giúp đánh giá tính đúng đắn và độ tin cậy của mã, nhưng không đồng nghĩa với lời bảo đảm “không có lỗi”.
2. Phân biệt kiểm thử **đơn vị (unit)**, **thành phần (component)**, **tích hợp (integration)**, **hợp đồng (contract)** và **đầu cuối (end-to-end, E2E)** theo **ranh giới được kiểm tra**, không chỉ theo tên thư mục test.
3. Ước lượng mức ưu tiên của một rủi ro bằng xác suất, tác động và mức độ phơi nhiễm, đồng thời đánh giá chi phí và tốc độ phản hồi của từng cấp kiểm thử.
4. Chọn **cấp kiểm thử thấp nhất có đủ khả năng phát hiện loại lỗi đang quan tâm**, rồi bổ sung kiểm thử ở ranh giới thật nếu các giả định giữa hệ thống là nguồn rủi ro.
5. Đề xuất chiến lược kiểm thử cân đối cho một luồng Java có tính giá, lưu cơ sở dữ liệu và gọi dịch vụ thanh toán.
6. Đọc kết quả CI, độ bao phủ, tính ổn định của test và dữ liệu thử để nhận định **bằng chứng hỗ trợ khẳng định nào, chưa hỗ trợ khẳng định nào**.

## 1. Kiểm thử cung cấp bằng chứng, không cung cấp sự chắc chắn tuyệt đối

Một bộ test xanh có thể cho biết: **trong những kịch bản được thực thi, trên môi trường và cấu hình đã dùng, chương trình tạo ra kết quả phù hợp với kỳ vọng trong test**. Nó không tự chứng minh mọi đầu vào, mọi tình trạng hạ tầng hoặc mọi cách sử dụng trong tương lai đều đúng.

Hãy xem một API tạo đơn hàng:

- Unit test xác minh giảm giá VIP 10% trên tổng từ 1.000.000 VND trở lên.
- Integration test xác minh đơn hàng được lưu đúng trong cơ sở dữ liệu thật.
- Contract test xác minh HTTP request và JSON response giữ đúng hợp đồng.
- E2E test xác minh người dùng có thể đặt hàng từ giao diện tới trạng thái xác nhận.

Các phép thử này **hỗ trợ những khẳng định khác nhau**. Unit test của công thức không kiểm tra được schema database; E2E thành công một lượt không chứng minh mọi giá trị biên của phép tính.

### Chất lượng của bằng chứng phụ thuộc vào câu hỏi

Một bài test có giá trị khi có thể trả lời bốn câu hỏi:

| Câu hỏi | Ví dụ |
| --- | --- |
| **Rủi ro nào đang được kiểm soát?** | Đơn áp dụng khuyến mãi có thể bị tính thiếu 1 đồng khi làm tròn |
| **Hành vi nào là đúng?** | Số tiền cuối phải theo quy tắc làm tròn đã xác nhận |
| **Test quan sát ở đâu?** | Kết quả của hàm tính giá, bản ghi DB hoặc phản hồi thanh toán |
| **Test có thể bỏ sót điều gì?** | Test đơn vị không xác nhận JSON, transaction hay cổng thanh toán thật |

Đặt mục tiêu theo **rủi ro cần phát hiện** tốt hơn đặt mục tiêu “mỗi phương thức phải có ít nhất một test”. Cùng một logic có thể cần vài bài test đơn vị cho trường hợp biên và một bài test tích hợp tại điểm kết nối quan trọng.

## 2. Phân biệt cấp kiểm thử bằng ranh giới quan sát

Tên gọi khác nhau giữa các nhóm và framework. Để tránh tranh luận về nhãn, hãy hỏi: **Những thành phần thật nào đang tham gia? Phụ thuộc nào đã được thay bằng test double? Kết quả được quan sát ở ranh giới nào?**

| Cấp/kiểu kiểm thử | Phạm vi thường gặp | Lỗi phát hiện hiệu quả | Chi phí hoặc giới hạn thường gặp |
| --- | --- | --- | --- |
| **Unit test** | Một đơn vị logic, dùng dữ liệu hoặc dependency được kiểm soát | Công thức, điều kiện, biến đổi, trạng thái biên | Không chứng minh tích hợp với DB, mạng hay cấu hình thật |
| **Component/service test** | Một thành phần ở ranh giới công khai, có thể giả lập phụ thuộc bên ngoài | Điều phối, validation, ánh xạ lỗi, tương tác giữa các lớp của thành phần | Kết quả có thể phụ thuộc giả định trong fake/mock |
| **Integration test** | Hai hoặc nhiều phần thật: Java–database, HTTP client–server thử nghiệm, message broker | Mapping, transaction, constraint, serialize, wiring, timeout | Thiết lập môi trường và cô lập dữ liệu tốn hơn |
| **Contract test** | Hợp đồng giữa bên cung cấp và bên tiêu thụ | Trường JSON, kiểu, mã lỗi, khả năng đọc/ghi giữa phiên bản | Chỉ hiệu quả nếu hợp đồng phản ánh cách dùng thực tế |
| **E2E/system test** | Một hành trình chạy qua nhiều thành phần và điểm vào thực | Sai cấu hình, routing, quyền, thiếu liên kết trong hành trình | Chậm, khó chẩn đoán và dễ chịu tác động môi trường |
| **Kiểm thử phi chức năng có mục tiêu** | Tải, bảo mật, tính chịu lỗi, accessibility... | Lỗi xuất hiện ở điều kiện phi chức năng | Có thể cần môi trường/tiêu chí chuyên biệt, không thể thay thế bằng số lượng unit test |

Đây không phải thang bậc duy nhất: **contract test có thể được thực hiện như một dạng integration test**, và **component test có thể dùng database thật**. Ranh giới thực thi và hành vi quan sát được quan trọng hơn nhãn “unit” hay “integration”.

### Chiều ngang khác với cấp kiểm thử

Một số kỹ thuật có thể áp dụng ở nhiều cấp:

- **Example-based test:** đưa đầu vào cụ thể, khẳng định kết quả cụ thể.
- **Property-based test:** sinh nhiều đầu vào hợp lệ để kiểm tra thuộc tính tổng quát.
- **Mutation testing:** cố ý thay đổi nhỏ mã sản phẩm để xem test có phát hiện được không.
- **Fuzz testing:** thử đầu vào bất thường để tìm lỗi xử lý, crash hoặc vi phạm bất biến.
- **Exploratory testing:** người kiểm thử chủ động học hệ thống và điều chỉnh kịch bản dựa trên quan sát.

Đừng nhầm **cấp test** (ranh giới chạy) với **kỹ thuật test** (cách tạo trường hợp/kỳ vọng) hoặc **loại rủi ro** (bảo mật, hiệu năng, tính đúng đắn, khả năng phục hồi).

## 3. Bài toán chọn cấp: giảm rủi ro với thời gian phản hồi chấp nhận được

Trong một dự án thực tế, thời gian và tài nguyên kiểm thử luôn hữu hạn. Kiểm thử quá ít khiến lỗi quan trọng đến môi trường thật; kiểm thử mọi thứ qua E2E có thể làm vòng phản hồi chậm và khó tìm nguyên nhân.

Một cách nghĩ thực dụng:

> **Chọn cấp thấp nhất có khả năng phát hiện lỗi đang quan tâm với bằng chứng đủ tin cậy; thêm kiểm thử ở ranh giới thật khi rủi ro nằm ở sự kết nối giữa các phần.**

Ví dụ:

- Sai dấu `>=` ở ngưỡng khuyến mãi: một **unit test** ngắn có thể phát hiện trực tiếp.
- DB không lưu được trạng thái vì ràng buộc unique hoặc transaction: cần **integration test với database**.
- Client cũ không đọc được trường JSON mới: cần **contract test** và có thể test serialization thực.
- Người dùng không thể hoàn tất đơn vì auth cookie, routing hoặc màn hình thanh toán: cần **E2E trên hành trình đại diện**.

Không nên nâng cấp độ test chỉ vì cho rằng test “càng gần production càng tốt”. Một lỗi công thức rõ ràng thường được báo nhanh và chẩn đoán tốt hơn ở unit test. Nhưng cũng không được dùng unit test để thay bằng chứng mà nó không thể cung cấp.

### Hai đại lượng quan trọng

**Rủi ro** liên quan tới khả năng xuất hiện lỗi và thiệt hại nếu lỗi xảy ra. **Chi phí phản hồi** bao gồm thời gian chạy, thiết lập môi trường, chẩn đoán, sửa test và chờ tín hiệu đáng tin cậy.

Hai đại lượng có thể thay đổi theo kiến trúc, hạ tầng CI, loại dependency và kinh nghiệm nhóm. Đánh giá dựa vào dữ liệu của nhóm tốt hơn sao chép một ngưỡng thời gian từ dự án khác.

## 4. Ưu tiên theo rủi ro thay vì phân bổ đều test

Có thể bắt đầu bằng cách liệt kê các tình huống hỏng rồi đánh giá ba yếu tố:

1. **Khả năng xảy ra:** mã thường thay đổi, thuật toán phức tạp, có lỗi lịch sử, dữ liệu đầu vào đa dạng hay phụ thuộc không ổn định?
2. **Tác động:** sai số tiền, sai quyền truy cập, mất dữ liệu, downtime, ảnh hưởng khách hàng hay chỉ lỗi hiển thị ít quan trọng?
3. **Mức độ phơi nhiễm:** chức năng có được dùng thường xuyên, ở nhiều tenant/khách hàng, hay là một quy trình hiếm?

Một bảng chấm điểm định tính có thể dùng mức `1–3` cho mỗi tiêu chí, rồi xếp thứ tự các rủi ro. Ví dụ minh họa, **không phải chuẩn công nghiệp hoặc xác suất đo lường**:

| Tình huống hỏng | Khả năng (1–3) | Tác động (1–3) | Phơi nhiễm (1–3) | Điểm gợi ý |
| --- | ---: | ---: | ---: | ---: |
| Khách thấy sai nhãn màu của nút phụ | 2 | 1 | 1 | 2 |
| VIP đúng ngưỡng không nhận giảm giá | 2 | 2 | 3 | 12 |
| Một lệnh thanh toán bị gửi hai lần sau timeout | 2 | 3 | 3 | 18 |
| Người dùng xem đơn của người khác qua ID | 2 | 3 | 3 | 18 |
| Báo cáo ngày loại sự kiện cuối ngày | 2 | 2 | 2 | 8 |

Điểm được tính bằng phép nhân ba mức chỉ để **sắp thứ tự thảo luận**. Những mức 1, 2, 3 không phải xác suất thực; điểm 18 không có nghĩa “rủi ro lớn gấp chín lần điểm 2”. Khi có dữ liệu đáng tin, nhóm có thể dùng ước lượng xác suất và tổn thất cụ thể, nhưng không nên tạo độ chính xác giả từ bảng chấm định tính.

### Ưu tiên kiểm thử dựa trên rủi ro như thế nào?

- **Tác động cao, dễ xảy ra:** cần bằng chứng ở đúng ranh giới, thường nhiều hơn một cấp nếu có side effect quan trọng.
- **Tác động cao, khó tái hiện:** cần test fault injection, điều kiện cạnh tranh, rollback hoặc diễn tập khôi phục phù hợp.
- **Tác động thấp, đường đi đơn giản:** một kiểm thử nhẹ, type check hoặc review có thể đủ theo chính sách nhóm.
- **Thay đổi nhiều:** nên đặt một vòng kiểm thử nhanh gần người sửa, vì lỗi hồi quy dễ xảy ra trong những phần này.
- **Thay đổi hiếm nhưng rất nguy hiểm:** vẫn có thể cần test chuyên biệt, dù số lần chạy ít hơn hoặc phải thực thi theo lịch.

Không nên chỉ hỏi “test nào chạy nhanh nhất” mà bỏ qua **khả năng phát hiện**. Một bài test cực nhanh nhưng hoàn toàn mock phần dễ sai nhất có giá trị hạn chế với rủi ro tích hợp.

## 5. Chi phí phản hồi gồm những gì?

“Chạy 2 giây” không phải toàn bộ chi phí của một test. Tín hiệu hữu ích phải đến đủ sớm, đủ ổn định và chỉ rõ nơi cần sửa.

| Thành phần chi phí | Ví dụ | Ảnh hưởng |
| --- | --- | --- |
| **Thời gian thực thi** | 30 ms cho hàm tính giá, vài phút cho E2E nhiều trình duyệt | Developer chờ kết quả trước khi tiếp tục |
| **Thiết lập môi trường** | Khởi động DB/container, tạo dữ liệu, cấu hình quyền | CI phức tạp hơn, nguy cơ khác môi trường thật |
| **Độ ổn định** | Test thỉnh thoảng fail vì thời gian, network hoặc dùng chung dữ liệu | Nhóm mất niềm tin hoặc phải chạy lại |
| **Khả năng chẩn đoán** | Fail ở `assertEquals` cụ thể so với “checkout failed” | Thời gian tìm và sửa lỗi khác nhau |
| **Bảo trì** | UI selector thay đổi, mock gắn cứng vào implementation | Test hỏng dù hành vi công khai vẫn đúng |
| **Chi phí tài nguyên** | Browser, database, pipeline song song, môi trường staging | Ảnh hưởng tốc độ và ngân sách CI |
| **Độ trễ phát hiện** | Lỗi bị phát hiện sau khi merge hoặc trước phát hành | Phạm vi thay đổi cần tìm kiếm lớn hơn |

Có thể mô tả đơn giản:

~~~text
Chi phí phản hồi thực tế
  ≈ thời gian thiết lập và chạy
    + thời gian chờ trong hàng đợi CI
    + thời gian đọc/chẩn đoán khi thất bại
    + chi phí chạy lại và bảo trì
~~~

Đây là sơ đồ khái niệm, không phải công thức thống kê chính xác. Một bài test lâu hơn đôi khi **tiết kiệm công sức hơn** nếu nó giảm đáng kể lỗi lọt ra sản phẩm hoặc xác nhận một rủi ro rất khó phát hiện ở cấp thấp hơn.

### Tốc độ và độ tin cậy phải được xem cùng nhau

Một test xanh sau 1 phút nhưng có nhiều false negative không có giá trị bằng test mất 3 phút mà quan sát đúng ranh giới. Tương tự, test hay fail ngẫu nhiên có thể khiến nhóm bỏ qua cảnh báo, làm giảm giá trị bằng chứng của cả pipeline.

## 6. Ví dụ Java: kiểm thử quy tắc giá ở cấp đơn vị

Giả sử đơn hàng dùng VND nguyên. Chính sách được xác nhận cho ví dụ này:

- Đơn giá không âm, số lượng mỗi dòng phải dương.
- Tổng được tính từ `đơn giá × số lượng`; nếu tràn kiểu `long` phải báo lỗi thay vì quấn số.
- Khách VIP được giảm **10% tổng** khi tổng **từ 1.000.000 VND trở lên**.
- Tiền giảm là thương nguyên của `tổng / 10`, tương đương làm tròn xuống số đồng giảm; không âm thầm dùng quy tắc làm tròn khác.

Đây là quy tắc **giả định của bài học**, không phải quy tắc mặc định của mọi cửa hàng.

~~~java
import java.util.List;
import java.util.Objects;

record OrderLine(long unitPriceVnd, int quantity) {}

final class PriceCalculator {
    private static final long VIP_THRESHOLD_VND = 1_000_000L;

    private PriceCalculator() {}

    static long amountDueVnd(List<OrderLine> lines, boolean vip) {
        Objects.requireNonNull(lines, "lines");

        long subtotal = 0L;
        for (OrderLine line : lines) {
            Objects.requireNonNull(line, "line");
            if (line.unitPriceVnd() < 0 || line.quantity() <= 0) {
                throw new IllegalArgumentException("Invalid order line");
            }

            long lineTotal = Math.multiplyExact(
                    line.unitPriceVnd(), (long) line.quantity());
            subtotal = Math.addExact(subtotal, lineTotal);
        }

        if (vip && subtotal >= VIP_THRESHOLD_VND) {
            long discount = subtotal / 10;
            return subtotal - discount;
        }
        return subtotal;
    }
}
~~~

Đơn vị này thuần tính toán: không kết nối database, không gọi HTTP, không lấy thời gian thực. Vì vậy **unit test là nơi thích hợp** để thử nhiều giá trị biên, tính chất số học và lỗi dữ liệu.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.List;

class PriceCalculatorTest {
    @Test
    void appliesVipDiscountAtExactThreshold() {
        assertEquals(900_000L,
                PriceCalculator.amountDueVnd(
                        List.of(new OrderLine(1_000_000L, 1)), true));
    }

    @Test
    void doesNotDiscountBelowThreshold() {
        assertEquals(999_999L,
                PriceCalculator.amountDueVnd(
                        List.of(new OrderLine(999_999L, 1)), true));
    }

    @Test
    void computesMultipleLinesWithoutDiscount() {
        long amount = PriceCalculator.amountDueVnd(
                List.of(new OrderLine(120_000L, 2),
                        new OrderLine(30_000L, 1)),
                false);
        assertEquals(270_000L, amount);
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> PriceCalculator.amountDueVnd(
                        List.of(new OrderLine(50_000L, 0)), false));
    }

    @Test
    void detectsOverflow() {
        assertThrows(ArithmeticException.class,
                () -> PriceCalculator.amountDueVnd(
                        List.of(new OrderLine(Long.MAX_VALUE, 2)), false));
    }

    @Test
    void roundsDownDiscountByContract() {
        assertEquals(900_005L,
                PriceCalculator.amountDueVnd(
                        List.of(new OrderLine(1_000_005L, 1)), true));
    }
}
~~~

Bài test cuối kiểm tra một kết quả có chủ đích: `1.000.005 / 10 = 100.000` theo chia nguyên, nên số còn phải trả là `900.005`. Nếu chính sách thực tế là giảm 10% rồi làm tròn tổng theo chế độ khác, **phải thay đặc tả và test**, không coi cách tính hiện tại luôn đúng.

### Bằng chứng unit test này cung cấp

**Có thể khẳng định:** với các input đã thử, hàm tính số tiền đúng theo chính sách giả định, từ chối số lượng bằng 0 và phát hiện tràn trong phép nhân đã kiểm tra.

**Chưa thể khẳng định:** endpoint HTTP gửi đúng JSON, DB lưu chính xác, client dùng đúng đơn vị tiền, gateway không thu hai lần, quyền truy cập đúng hoặc ứng dụng chạy được sau triển khai.

Chính vì giới hạn rõ ràng, unit test giúp giảm chi phí phản hồi mà không tạo **cảm giác an toàn giả**.

## 7. Khi cần integration test: ranh giới dữ liệu thật mới là nguồn rủi ro

Một ứng dụng có thể tính giá đúng nhưng vẫn sai khi lưu:

- Schema DB dùng cột nhỏ hơn miền của `long`, dẫn đến lỗi hoặc mất dữ liệu.
- Transaction commit một phần: đơn được tạo nhưng trạng thái thanh toán chưa được cập nhật.
- Hai request dùng cùng idempotency key tạo hai bản ghi do thiếu ràng buộc unique.
- ORM ánh xạ `null`, enum hoặc timestamp không đúng hợp đồng.
- Truy vấn lọc theo chủ sở hữu không đúng, khiến người dùng đọc đơn của người khác.

Các vấn đề này cần test với **adapter, schema và các ràng buộc dữ liệu thật hoặc tương đương đáng tin cậy**, không chỉ mock repository.

### Kịch bản integration test cho kho đơn hàng

Giả sử repository có phương thức `createIfAbsent(idempotencyKey, payload)`. Hợp đồng cần xác minh:

1. Tạo mới với key chưa có: ghi **một** đơn hợp lệ.
2. Gọi lại cùng key và cùng payload: trả cùng kết quả logic, không tạo bản ghi đơn thứ hai.
3. Gọi lại cùng key nhưng payload khác: từ chối theo chính sách, không âm thầm thay đơn cũ.
4. Hai lời gọi gần như đồng thời: ràng buộc database đảm bảo kết quả nhất quán.
5. Lỗi ở giữa transaction: những bước chưa commit được rollback theo hợp đồng.

**Lưu ý quan trọng:** ràng buộc unique trong database **chỉ hỗ trợ tính duy nhất của dữ liệu thuộc database**. Nó không tự chứng minh yêu cầu tới cổng thanh toán đã được gửi đúng một lần. Nếu thanh toán nằm ngoài transaction DB, cần hợp đồng idempotency của provider, trạng thái bền vững và cơ chế đối soát.

Vì sao không chỉ dùng mock? Một mock có thể được cấu hình “nếu gọi lần hai thì trả bản ghi cũ”, nhưng nó không phát hiện index bị thiếu, isolation level không phù hợp hoặc lỗi ánh xạ column trong database thật.

### Test hạ tầng phải cô lập và có thể lặp lại

Một integration test tốt nên có:

- Cơ sở dữ liệu thử với **cùng loại engine và migration/schema** liên quan, hoặc giải thích rõ giới hạn của một engine thay thế.
- Dữ liệu test độc lập; không phụ thuộc dữ liệu còn sót từ test trước.
- Quy tắc rollback/dọn dẹp, tránh test song song ghi đè lẫn nhau.
- Timeout cho dependency và kết quả lỗi rõ.
- Cách tái hiện ở máy phát triển và CI trong phạm vi môi trường phù hợp.

Nếu dùng Testcontainers hoặc containerized database, đó là phương tiện **tăng tính gần thực tế**, không phải bằng chứng tự động rằng mọi cấu hình production đều tương đương. Cần kiểm tra khác biệt phiên bản, đặc quyền, collation, timezone và mạng.

## 8. Contract test: kiểm tra hai phía hiểu cùng một lời hứa

Một hệ thống có thể có unit test và integration test đều xanh nhưng **consumer** vẫn hỏng vì provider đổi `totalVnd` thành `amountDueVnd`, thêm giá trị enum mới hoặc thay mã lỗi.

**Contract test** tập trung vào những tương tác mà các bên đã thỏa thuận:

| Điều cần kiểm tra | Ví dụ |
| --- | --- |
| Request hợp lệ | `POST /orders` nhận `items` và idempotency key đúng format |
| Response thành công | Có `orderId`, `amountDueVnd` theo đơn vị đã định, `status` hợp lệ |
| Kiểu và nullability | `amountDueVnd` là số nguyên VND, không tự biến thành chuỗi |
| Lỗi được công bố | Không tìm thấy khác lỗi hạ tầng; mã lỗi ổn định |
| Tương thích phiên bản | Consumer cũ vẫn đọc được response khi provider được nâng cấp |
| Ranh giới quyền | Không trả dữ liệu của đơn không được phép truy cập |

Contract test có thể chạy phía provider, consumer hoặc cả hai; consumer-driven contract là một cách thể hiện các tương tác **được sử dụng thực tế**. Nếu contract file được sinh chỉ từ code provider mà không kiểm tra cách consumer dùng, vẫn có thể bỏ sót giả định về ý nghĩa dữ liệu.

### Ví dụ phạm vi hợp đồng

~~~json
{
  "orderId": "OD-123",
  "amountDueVnd": 900000,
  "status": "PAID"
}
~~~

Kiểm tra JSON có đủ ba trường mới là một phần. Cần xác minh **`amountDueVnd` nghĩa là số tiền sau giảm giá**, mã `PAID` chỉ xuất hiện khi có bằng chứng thanh toán theo hợp đồng, và những trạng thái mới được consumer xử lý an toàn.

Contract test không thay thế E2E nếu rủi ro nằm ở cookie, routing, CORS, cấu hình bảo mật hoặc hành trình giao diện nhiều bước. Ngược lại, một E2E xanh cũng không kiểm tra hết tất cả biến thể schema.

## 9. E2E: dùng tiết kiệm cho hành trình và điểm nối có rủi ro cao

Một **E2E test** thường khởi tạo một hành trình thật từ điểm vào của người dùng hay API tới kết quả quan sát được, qua nhiều thành phần đã cấu hình.

Ví dụ hành trình “đặt hàng thành công”:

~~~mermaid
flowchart LR
    A["Client gửi đơn"] --> B["API xác thực & validation"]
    B --> C["Tính giá"]
    C --> D["Lưu trạng thái đơn"]
    D --> E["Thanh toán thử nghiệm"]
    E --> F["Ghi nhận kết quả"]
    F --> G["Client xem xác nhận"]
~~~

Một kịch bản E2E quan trọng có thể xác minh: người dùng đã xác thực gửi một giỏ hàng hợp lệ, số tiền cuối được hiển thị đúng, hệ thống dùng cổng thanh toán thử nghiệm, và trạng thái đơn quan sát ở giao diện phù hợp với kết quả thực.

Tại sao không làm **hàng trăm E2E cho mọi ngưỡng giá**?

- Mỗi test phải khởi động nhiều phần, chiếm tài nguyên và thường chậm hơn.
- Khi thất bại, nguyên nhân có thể là logic giá, auth, routing, DB, gateway, trình duyệt hoặc môi trường.
- Test giao diện dễ hỏng vì selector hoặc timing dù quy tắc tính tiền không đổi.
- Các trường hợp biên có thể kiểm tra nhanh và giải thích rõ hơn ở unit/component test.

Hãy giữ **một số hành trình có giá trị cao** ở E2E, rồi phân bổ biến thể công thức, lỗi validation và trường hợp biên ở cấp thấp hơn. Số lượng E2E cụ thể phụ thuộc rủi ro và năng lực vận hành, không có tỷ lệ phần trăm cố định.

### Điều kiện để E2E đáng tin

- Dữ liệu đầu vào và kết quả mong đợi được kiểm soát.
- Dùng điểm đồng bộ sự kiện/kết quả thực thay vì `sleep` thời gian cố định khi có thể.
- Dùng môi trường và tài khoản thử nghiệm được cấp quyền; không vô tình tạo thanh toán thật.
- Có log, request ID hoặc ảnh/chứng cứ phù hợp để xác định điểm hỏng.
- Cô lập trạng thái giữa test song song, giới hạn retry và phân biệt flaky với lỗi sản phẩm.

Test thất bại ngẫu nhiên không nên được “chữa” bằng cách retry vô hạn rồi coi xanh là bằng chứng đầy đủ. Cần điều tra điều kiện tranh chấp và môi trường.

## 10. Rủi ro bảo mật, hiệu năng và phục hồi cần phép đo chuyên biệt

Các loại lỗi không chức năng có thể quan trọng hơn lỗi UI nhỏ nhưng khó phát hiện bằng các test thông thường.

### Bảo mật và phân quyền

Một unit test có thể xác nhận hàm chính sách `canReadOrder(userId, order)` từ chối người không phải chủ đơn. Nhưng để chứng minh API **thực sự gọi kiểm tra quyền**, nên có test HTTP/integration với hai tài khoản và một đơn không thuộc quyền người gọi.

Các rủi ro như SQL injection, xử lý file, secrets trong log, lộ dữ liệu khi exception hoặc phân tách tenant cần kiểm thử và review ở ranh giới thực, bổ sung công cụ phù hợp theo quy trình tổ chức. Unit test về tên trường không đủ để kết luận hệ thống an toàn.

### Hiệu năng

Một unit test hàm tính giá chạy trong 1 ms không chứng minh API đáp ứng được tải đồng thời. Cần định nghĩa mục tiêu (ví dụ độ trễ percentile, throughput, tỷ lệ lỗi), mô hình lưu lượng và môi trường đủ gần điều kiện cần đánh giá.

Kết quả benchmark đơn lẻ không tự cho biết hệ thống thực sẽ ra sao nếu dataset, cache, network và cấu hình khác biệt. Một bài performance regression test chỉ có ý nghĩa khi điều kiện so sánh đủ ổn định và mục tiêu được công bố.

### Phục hồi và tính nhất quán

Muốn kiểm tra “timeout sau khi gateway đã xử lý không làm thu tiền hai lần”, cần mô phỏng **lỗi ở đúng thời điểm** và xác minh kết quả trên trạng thái bền vững/cổng thử nghiệm theo hợp đồng. Đây có thể là integration test hoặc fault-injection test, không nhất thiết phải điều khiển toàn bộ trình duyệt.

Điều cần quan sát là **invariant nghiệp vụ**: mỗi thao tác logic có kết quả thanh toán nhất quán, retry không tạo side effect không được phép và có cách đối soát nếu trạng thái chưa rõ.

## 11. Case study: phân bổ kiểm thử cho luồng checkout

Giả sử hệ thống Java có:

- `PriceCalculator` tính số tiền từ giỏ hàng.
- `CheckoutService` điều phối xác thực, giá, đặt trạng thái đơn và thanh toán.
- `OrderRepository` lưu DB có ràng buộc giao dịch.
- `PaymentGateway` gọi đối tác thanh toán với idempotency key.
- HTTP API và giao diện cho khách hàng.

Rủi ro nổi bật: tính tiền sai, ghi đơn trùng, thu tiền trùng, lộ đơn của người khác và đường đi thanh toán bị đứt.

### Bảng phân bổ có lý do

| Rủi ro/kỳ vọng | Cấp kiểm thử chủ lực | Bằng chứng cần có | Có cần thêm cấp khác? |
| --- | --- | --- | --- |
| VIP đúng ngưỡng, giá âm, tràn số | **Unit** | Kết quả và exception ở giá trị biên | Một test tích hợp xác nhận giá đi qua API không đổi đơn vị |
| Mapping request thiếu trường, dữ liệu sai kiểu | **Component/API** | Status, mã lỗi, validation trước side effect | Contract test nếu có client độc lập |
| Truy vấn theo `ownerId` đúng, không lộ đơn | **Integration/API** | Kết quả thật với hai tài khoản, DB lọc đúng | Có thể thêm security review/thử nghiệm phù hợp |
| Idempotency key tạo một đơn logic | **DB integration** | Unique constraint và trạng thái bền vững khi gọi đồng thời | Test gateway và xử lý retry toàn luồng |
| Timeout sau khi gateway đã nhận lệnh | **Integration/fault injection** | Xác minh không gửi side effect trùng không kiểm soát | Một E2E hành trình thất bại quan trọng nếu cần |
| Provider đổi tên trường JSON | **Contract** | Cả client cũ/mới đọc được trong thời gian hỗ trợ | API serialization test với cấu hình thật |
| Người dùng đặt một đơn từ giao diện | **E2E** | Hành trình chạy tới trạng thái cuối | Unit test riêng cho biến thể giá và validation |
| Nhiều request đồng thời làm quá tải | **Load/performance** | Phân bố độ trễ, tỷ lệ lỗi trong mô hình tải | Unit test không thay thế được |

Bảng cho thấy **mỗi rủi ro được đặt ở nơi phát hiện hiệu quả nhất**, không phải tất cả đều đẩy lên E2E. Một số rủi ro cần bằng chứng ở **hai cấp bổ sung nhau**, vì một cấp chứng minh quy tắc còn cấp khác chứng minh các thành phần thực thi đúng hợp đồng ở ranh giới.

### Ví dụ: một lỗi, ba góc nhìn

**Lỗi:** người dùng nhận hóa đơn 900.000 VND, nhưng hệ thống gửi gateway 1.000.000 VND.

- Unit test của `PriceCalculator` có thể xanh: hàm trả `900000` đúng.
- Component test của `CheckoutService` với fake `PaymentGateway` có thể phát hiện service truyền nhầm subtotal cho gateway.
- Integration hoặc contract test có thể cần nếu lỗi nằm trong mapping dữ liệu/đơn vị tiền của adapter.

Bởi vậy, khi test xanh nhưng lỗi vẫn xuất hiện, đừng ngay lập tức kết luận “cần nhiều E2E”. Hãy xác định **ranh giới nơi kỳ vọng sai bị truyền qua** và thêm bằng chứng tại đúng nơi.

## 12. Đọc ma trận rủi ro và quyết định cấp test

Một quy trình có thể thực hiện ngay trong code review:

1. **Viết hành vi cần giữ đúng:** “Khi đơn được thanh toán, số tiền gửi gateway bằng số tiền cuối do chính sách tính.”
2. **Liệt kê cách hành vi có thể sai:** công thức, mapping, DB schema, retry, thiếu phân quyền, cấu hình.
3. **Đánh giá rủi ro:** tác động, khả năng, phạm vi người bị ảnh hưởng; đánh dấu các sai sót đã từng xảy ra.
4. **Tìm ranh giới phát hiện sớm nhất:** unit cho công thức, component cho điều phối, integration cho DB/gateway, contract cho client, E2E cho hành trình.
5. **Kiểm tra lỗ hổng bằng chứng:** fake/mock đang giả định điều gì? Có phần nào chỉ production mới chạy thật?
6. **Chọn cách chạy:** test nhanh mỗi lần sửa/PR; test nặng ở cổng phù hợp trước khi phát hành hoặc theo lịch theo mức rủi ro.
7. **Ghi giới hạn của test:** test xanh chứng minh điều gì và còn cần kiểm chứng nào khác.

Để tránh chọn test theo trực giác, có thể làm bảng quyết định ngắn:

| Câu hỏi | Nếu trả lời “Có” | Gợi ý |
| --- | --- | --- |
| Quy tắc thuần có thể tách khỏi I/O không? | Có thể truyền đầu vào và quan sát kết quả trực tiếp | Bắt đầu bằng unit test |
| Lỗi phụ thuộc serializer, schema, transaction hay broker không? | Có một ranh giới thực cần kiểm tra | Integration hoặc contract test |
| Lỗi chỉ lộ khi nhiều bước/định tuyến/phiên đăng nhập kết hợp? | Cần một hành trình hoàn chỉnh | E2E test đại diện |
| Rủi ro nằm ở tải, quyền, lỗi hạ tầng hoặc đồng thời? | Điều kiện khác luồng thành công đơn giản | Test chuyên biệt/fault injection ở cấp thích hợp |
| Test thất bại có chỉ rõ nguyên nhân không? | Không | Cần cải thiện quan sát, cách chia và dữ liệu test |

Đây là bảng **gợi ý để ra quyết định**, không phải thuật toán tuyệt đối. Mỗi nhóm cần xét thời gian phản hồi, công cụ, kiến trúc và mức rủi ro chấp nhận được.

## 13. Tổ chức vòng phản hồi: nhanh trước, đầy đủ ở đúng cổng

Một cách tổ chức thường hữu ích là **xếp lớp phản hồi**:

~~~text
Trên máy phát triển:
  Kiểm tra tĩnh + unit test liên quan
          ↓ phản hồi nhanh
Khi mở pull request:
  Unit + component + contract + integration liên quan
          ↓ xác nhận ranh giới thay đổi
Trước phát hành / theo lịch hoặc điều kiện:
  E2E hành trình trọng yếu + bảo mật/hiệu năng/khả năng phục hồi phù hợp
          ↓ tăng bằng chứng ở môi trường gần thật
Sau triển khai:
  Giám sát, canary/smoke test, cảnh báo và phương án rollback
~~~

Bố trí trên là **mẫu tham khảo**, không phải quy định mọi E2E đều chỉ nên chạy trước phát hành. Một E2E cực kỳ quan trọng và ổn định có thể chạy trên mọi PR; test tải nặng có thể chạy theo lịch hoặc trước thay đổi hạ tầng lớn.

### Ví dụ ngân sách phản hồi minh họa

Giả sử nhóm mong muốn nhận tín hiệu cơ bản trong vài phút:

| Vòng | Mục tiêu gợi ý của nhóm giả định | Ưu tiên |
| --- | --- | --- |
| Developer chạy tại chỗ | Vài giây đến khoảng một phút | Test liên quan, lỗi biên và thông tin chẩn đoán trực tiếp |
| Pull request | Vài phút | Phát hiện hồi quy chính và lỗi ranh giới thay đổi |
| Pipeline mở rộng | Thời gian lâu hơn theo SLA nội bộ | Hành trình trọng yếu, cross-version, tải hoặc fault injection |
| Sau triển khai | Liên tục hoặc theo chu kỳ thích hợp | Lỗi thực tế, chỉ số sức khỏe và tính đúng đắn nghiệp vụ |

Đây là **ví dụ hoạch định**, không phải số liệu đo hay ngưỡng bắt buộc. Nếu hiện tại integration test kéo dài quá lâu, có thể phân tách test độc lập, chạy song song có kiểm soát hoặc cải thiện dữ liệu/môi trường, thay vì bỏ kiểm thử rủi ro cao chỉ để đạt thời gian CI.

### Chạy theo thay đổi có một giới hạn

Chỉ chạy “test bị ảnh hưởng” dựa trên dependency graph có thể tiết kiệm thời gian, nhưng cần đủ độ tin cậy rằng graph phản ánh cả **hợp đồng runtime, cấu hình, migration và các phụ thuộc gián tiếp**. Khi thay đổi schema hoặc logic dùng chung, một bộ test rộng hơn là cần thiết.

## 14. Test double, mock và fake: tăng tốc nhưng dễ che lỗi

Mock và fake giúp kiểm soát đầu vào, mô phỏng lỗi, tăng tốc phản hồi. Chúng hữu ích khi kiểm tra **điều phối hoặc logic riêng**. Tuy nhiên, nếu test double tự thực hiện điều mà hệ thống thật **không bảo đảm**, test xanh có thể đánh lừa.

Ví dụ:

~~~java
interface PaymentGateway {
    PaymentResult charge(String idempotencyKey, long amountVnd);
}

record PaymentResult(String reference, boolean accepted) {}
~~~

Trong component test, fake gateway có thể ghi lại số tiền đã nhận để kiểm tra `CheckoutService` gọi đúng. Nhưng fake không tự chứng minh:

- Cổng thật chấp nhận đơn vị VND hay số đơn vị nhỏ hơn.
- Timeout xảy ra trước hay sau khi cổng thật tạo giao dịch.
- Cổng thật bảo đảm idempotency trong bao lâu và theo phạm vi nào.
- SDK có ánh xạ trạng thái lỗi và thông tin thanh toán đúng không.

**Quy tắc sử dụng:** mock ở nơi nó giúp test rõ và nhanh; với giả định nguy hiểm ở ranh giới thật, bổ sung contract/integration test bằng môi trường thử nghiệm thích hợp.

Ngoài ra, việc verify mọi lời gọi nội bộ theo thứ tự thực thi có thể làm test quá gắn với implementation. Khi refactor mà hành vi công khai không đổi, test dạng đó dễ hỏng không cần thiết. Ưu tiên assert **đầu ra, trạng thái và tương tác thực sự là một phần hợp đồng**.

## 15. Độ bao phủ và các chỉ số không nói thay chất lượng bằng chứng

**Code coverage** cho biết phần mã nào được thực thi khi chạy test, thường ở mức dòng hoặc nhánh. Nó hữu ích để phát hiện vùng chưa được chạm tới, nhưng **không chứng minh test có assertion đúng hay bao phủ rủi ro quan trọng**.

Ví dụ:

~~~java
@Test
void testPriceWithoutMeaningfulAssertion() {
    PriceCalculator.amountDueVnd(
            List.of(new OrderLine(1_000_000L, 1)), true);
    // Chạy qua nhiều dòng nhưng không xác minh số tiền mong đợi.
}
~~~

Test này có thể tăng line coverage dù không kiểm tra phép giảm giá đúng. Ngược lại, một số ít test có giá trị biên tốt có thể bảo vệ quy tắc nghiệp vụ quan trọng hơn nhiều test chỉ gọi phương thức.

| Chỉ số | Được dùng để hỏi | Không được suy ra |
| --- | --- | --- |
| Line/branch coverage | Những vùng mã/nhánh nào chưa được thực thi? | “Đạt 100% là không còn lỗi” |
| Mutation score | Test có phát hiện một số thay đổi sai có chủ đích không? | “Không thể có lỗi ngoài tập mutation đã dùng” |
| Thời gian pipeline | Tín hiệu đến đủ nhanh không? | “Nhanh nghĩa là tốt hơn” |
| Tỷ lệ flaky | Kết quả có lặp lại ổn định không? | “Mọi failure đều do môi trường” |
| Tỷ lệ lỗi lọt ra production | Rủi ro nào đang thiếu bằng chứng trước phát hành? | “Không có bug report nghĩa là test hoàn hảo” |
| Số lượng test | Phạm vi tự động hóa đang tăng hay giảm? | “Nhiều test nghĩa là nhiều chất lượng” |

Một chỉ số hữu ích khi được đặt cạnh **rủi ro, loại code, phạm vi môi trường và xu hướng theo thời gian**. Không nên đánh giá người phát triển chỉ bằng số lượng test hoặc một con số coverage.

### Vấn đề flaky test

Flaky test là test có thể cho kết quả khác nhau với cùng mã sản phẩm vì điều kiện không được kiểm soát, ví dụ thời gian, dữ liệu dùng chung, concurrency, network, thứ tự thực thi. Nó làm nhóm tốn công và dần bỏ qua các tín hiệu thất bại.

Cách xử lý nên là **tái hiện, cô lập, tìm nguyên nhân, sửa điểm đồng bộ hoặc dữ liệu test**, không chỉ tự động retry cho tới khi xanh. Nếu phải tạm cách ly test, cần ghi nhận rủi ro và lộ trình sửa, tránh quên mất vùng bằng chứng bị mất.

## 16. Test cần phát hiện lỗi nhưng cũng phải giúp sửa nhanh

Chi phí phản hồi không kết thúc khi pipeline báo đỏ. Một failure có thể dẫn tới:

- **Tín hiệu rõ:** `expected 900000 but was 1000000` tại test tính giá ở ngưỡng.
- **Tín hiệu khó:** E2E báo “payment confirmation missing” sau mười phút, trong khi nguyên nhân thật là một điều kiện VIP sai.

Với một lỗi công thức, unit test giúp định vị tốt. Với lỗi kết nối thực, integration test cung cấp chứng cứ tốt hơn mock. Vì vậy phân bổ cấp test hợp lý còn là cách cải thiện **khả năng chẩn đoán**.

Bài test tốt cần:

1. Tên diễn tả hành vi và điều kiện đầu vào.
2. Kỳ vọng độc lập với cách cài đặt đang bị kiểm tra.
3. Dữ liệu thử có nghĩa, đủ đại diện cho giá trị biên.
4. Kiểm soát thời gian và trạng thái dùng chung.
5. Thông báo thất bại đủ để tái hiện mà không lộ dữ liệu nhạy cảm.
6. Số lần thử lại có chủ đích, không che kết quả không ổn định.

Một kiểm thử có thể chậm hơn nhưng dễ tìm ra lỗi quan trọng sẽ có giá trị cao hơn test nhanh song chỉ báo “có gì đó không ổn”.

## 17. Những ngộ nhận thường gặp

**“Cấp kiểm thử càng cao thì bằng chứng càng mạnh cho mọi rủi ro.”** E2E quan sát nhiều thành phần, nhưng test đơn vị thường chính xác và hiệu quả hơn với công thức hoặc giá trị biên.

**“Chỉ cần nhiều unit test là đủ.”** Unit test không chứng minh được database schema, serialization, quyền thực ở endpoint hay tác dụng phụ bên ngoài.

**“Có một E2E xanh thì cả luồng không thể sai.”** Một hành trình thành công không bao phủ hết lỗi, đồng thời, timeout, dữ liệu khác thường và thao tác người dùng khác.

**“Mock đúng thì cổng tích hợp thật chắc chắn đúng.”** Test double phản ánh giả định của người viết; phải kiểm chứng các giả định quan trọng tại ranh giới thật.

**“Coverage càng cao thì chất lượng càng tốt.”** Coverage chỉ mô tả mã được chạy; một assertion sai hoặc thiếu không trở nên đúng vì coverage cao.

**“Mọi test đều phải chạy ở mọi commit.”** Một pipeline có thể phân tầng theo rủi ro và thời gian phản hồi, với các cổng bổ sung trước phát hành hoặc theo lịch.

**“Test chậm cứ bỏ đi là pipeline tốt hơn.”** Phải đánh giá mức rủi ro đang được phát hiện và cân nhắc cách làm test đáng tin cậy, cô lập, nhanh hơn.

**“Flaky thì cứ retry cho xanh.”** Retry có thể che lỗi đồng thời, dữ liệu dùng chung hoặc hạ tầng; cần điều tra nguyên nhân.

**“Tất cả lỗi đều nên tái hiện bằng E2E.”** Nên tái hiện ở cấp thấp nhất mô tả được nguyên nhân, rồi thêm test ranh giới khi cần.

**“Test xanh đồng nghĩa có thể triển khai an toàn.”** Còn cần đánh giá môi trường, dữ liệu migration, khả năng rollback, quan sát production và rủi ro ngoài phạm vi test.

## 18. Bài tập thực hành

### Bài tập A — chọn cấp kiểm thử

Với mỗi tình huống sau, hãy chọn cấp **chủ lực**, nêu **điều sẽ assert** và **giới hạn bằng chứng**:

1. Khách VIP được giảm khi tổng **bằng đúng** 1.000.000 VND.
2. Hai request đồng thời có cùng idempotency key chỉ tạo một bản ghi đơn logic.
3. API đổi kiểu `amountDueVnd` từ số nguyên sang chuỗi, khiến ứng dụng cũ không giải mã được.
4. Người dùng đăng nhập không thể xem đơn thuộc tài khoản khác.
5. Một lời gọi thanh toán timeout sau khi cổng đã tạo giao dịch; retry không được tạo tác dụng phụ trùng.
6. Trang checkout không hiện nút xác nhận sau khi thay routing.
7. Dưới tải cao, 99% request cần hoàn tất trong giới hạn độ trễ do sản phẩm đặt ra.

### Bài tập B — đọc bằng chứng

Đội phát triển có 2.000 unit test xanh, line coverage 95%, không có integration test cho database và vừa đổi schema cột `amount_due`. Bạn sẽ:

- Kết luận được những điều gì?
- Chưa thể kết luận được những điều gì?
- Ưu tiên thêm ba bài kiểm thử hoặc nhóm tình huống nào trước khi phát hành?
- Làm sao giảm thời gian feedback mà vẫn kiểm tra được schema thật?

### Bài tập C — thiết kế ma trận cho một thay đổi

Một pull request thay đổi chính sách giảm giá VIP và cập nhật JSON response từ `totalVnd` sang `amountDueVnd`. Hãy lập ma trận gồm **rủi ro → cấp kiểm thử → đầu vào → kỳ vọng → giới hạn**. Bắt buộc có test ngưỡng, test consumer cũ và một trường hợp lỗi thanh toán.

## 19. Câu hỏi tự kiểm tra

1. Vì sao cùng một yêu cầu nghiệp vụ có thể cần unit test và integration test, dù cả hai đều kiểm tra một “tính năng”?
2. Làm thế nào để chọn cấp kiểm thử mà không bắt đầu bằng “test nào dễ viết nhất” hoặc “mọi thứ phải E2E”?
3. Điểm rủi ro định tính 1–3 có hạn chế gì? Vì sao không nên coi phép nhân các điểm ấy là xác suất thật?
4. Một mock repository trả dữ liệu đúng nhưng database thật vi phạm unique constraint. Test nào nên phát hiện điều này?
5. Thế nào là thay đổi hợp đồng có thể không làm test backend lỗi nhưng làm client cũ hỏng?
6. Vì sao test `Future.get(timeout)` hoặc HTTP timeout không tự chứng minh công việc phía bên kia đã dừng?
7. Khi nào một E2E test có giá trị hơn nhiều unit test, và khi nào điều ngược lại đúng?
8. Độ bao phủ 100% và một bài test không có assertion có thể cùng tồn tại không? Điều đó nói gì về bằng chứng?
9. Nếu pipeline hay fail ngẫu nhiên, bạn sẽ làm gì trước khi tăng số lần retry?
10. Hãy nêu một cách kiểm thử rủi ro bảo mật và một cách kiểm thử rủi ro hiệu năng phù hợp với ranh giới thực.
11. Vì sao cần test consumer mới với provider cũ trong giai đoạn phát hành nhiều phiên bản?
12. Làm thế nào để trình bày giới hạn của bộ test cho người ra quyết định phát hành?

## Ghi nhớ

**Chọn cấp kiểm thử là quyết định về bằng chứng cần có cho một rủi ro cụ thể, cân bằng với chi phí và độ trễ phản hồi.** Hãy dùng unit test cho quy tắc thuần và nhiều trường hợp biên; dùng integration/contract test cho những ranh giới có thể hiểu khác nhau; giữ E2E cho các hành trình quan trọng; bổ sung kiểm thử chuyên biệt cho bảo mật, tải và khả năng phục hồi. Một chiến lược tốt không chỉ khiến pipeline xanh mà còn giúp người phát triển biết **điều gì đã được kiểm chứng, điều gì chưa và sẽ biết sớm đến đâu khi có lỗi**.
