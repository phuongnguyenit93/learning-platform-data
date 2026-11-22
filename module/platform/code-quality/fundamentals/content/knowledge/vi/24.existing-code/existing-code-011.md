# Cân nhắc viết lại theo bằng chứng về chi phí và rủi ro

Một hệ thống tính giá đã tồn tại nhiều năm. Quy tắc giảm giá nằm rải rác trong ba module, tên biến khó hiểu và mỗi lần thay đổi chính sách đều cần nhiều vòng review. Một nhóm đề xuất viết lại toàn bộ bằng kiến trúc mới. Nhóm khác muốn giữ nguyên vì hệ thống vẫn đang phục vụ khách hàng. Cả hai đều có lý do, nhưng **“mã cũ khó đọc”** và **“viết lại sẽ sạch hơn”** chưa đủ để quyết định một dự án thay thế lớn.

Viết lại có thể loại bỏ những ràng buộc đã cản trở phát triển trong nhiều năm. Nó cũng có thể làm mất các quy tắc ngầm, hành vi tương thích và kiến thức vận hành chỉ tồn tại trong hệ thống hiện tại. Chi phí không dừng ở việc viết mã mới: nhóm còn phải khám phá hành vi, chuyển dữ liệu, tích hợp, kiểm thử, triển khai và hỗ trợ hai hệ thống trong giai đoạn chuyển đổi.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta tìm hiểu những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Ở chương **Mã hiện hữu**, bài này tập trung vào cách **cân nhắc viết lại theo bằng chứng về chi phí và rủi ro**. Mục tiêu là chọn phương án xử lý phù hợp với vấn đề đã được chứng minh, đồng thời giữ được hành vi cần thiết và kiểm soát rủi ro chuyển đổi.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **mã cũ**, **nợ kỹ thuật** và **mã không còn đáp ứng yêu cầu**; không mặc định hệ thống lâu năm phải viết lại.
- Thu thập bằng chứng về chi phí thay đổi, lỗi, vận hành, bảo mật và giới hạn nền tảng trước khi đề xuất thay thế.
- So sánh giữ nguyên, bổ sung kiểm soát, refactor từng phần, thay một lát cắt nghiệp vụ và viết lại toàn bộ.
- Khám phá hợp đồng và hành vi ngầm của hệ thống hiện tại bằng code reading, dữ liệu, log, caller, test và trao đổi với người vận hành.
- Phân biệt **hành vi cần bảo toàn** với **hành vi sai cần sửa**, tránh sao chép bug vào hệ thống mới.
- Thiết kế chuyển đổi theo từng bước với characterization tests, contract tests, migration, rollout, rollback và quan sát.
- Trình bày quyết định dựa trên chi phí vòng đời, tác động, bất định và rủi ro còn lại thay vì chỉ dựa vào sở thích công nghệ.

## 1. Mã hiện hữu không tự động là mã xấu

Một hệ thống được gọi là **legacy** thường có nghĩa là nó đã tồn tại, đang được sử dụng và mang theo những quyết định, dữ liệu hoặc ràng buộc từ quá khứ. Từ này không tự chứng minh hệ thống có chất lượng thấp. Một ứng dụng cũ có thể rất ổn định, hiểu rõ nghiệp vụ và có chi phí vận hành thấp; một ứng dụng mới có thể được xây dựng bằng công nghệ hiện đại nhưng chưa có đủ kiểm soát về dữ liệu, quyền truy cập hoặc khả năng phục hồi.

Điều cần đánh giá là **hệ thống hiện tại đang cản trở mục tiêu nào, với mức độ nào**:

- Một thay đổi nhỏ có phải sửa nhiều module và kiểm thử thủ công lặp lại không?
- Các lỗi có tập trung ở một số thành phần thay đổi thường xuyên không?
- Nhóm có thể triển khai, nâng cấp hoặc khôi phục hệ thống một cách an toàn không?
- Có lỗ hổng hoặc nền tảng hết hỗ trợ mà không thể giảm thiểu hợp lý không?
- Các yêu cầu mới có bị chặn bởi mô hình dữ liệu, giao thức hoặc kiến trúc hiện tại không?
- Có còn người hiểu các quy tắc và thao tác vận hành quan trọng không?

**Tuổi đời là bối cảnh, không phải bằng chứng đủ để viết lại.** Quyết định phải bắt đầu từ vấn đề và hậu quả có thể quan sát.

### Phân biệt ba khái niệm

| Khái niệm | Ý nghĩa | Điều cần xác minh |
| --- | --- | --- |
| **Mã hiện hữu/legacy** | Mã đã tồn tại và có thể đang phục vụ nghiệp vụ | Ai sử dụng, hợp đồng nào đang phụ thuộc, ràng buộc triển khai |
| **Nợ kỹ thuật** | Lựa chọn hoặc cấu trúc làm tăng chi phí/rủi ro thay đổi về sau | Cơ chế gây chi phí, tần suất gặp, tác động thực tế |
| **Không còn phù hợp** | Hệ thống không đáp ứng yêu cầu hoặc ràng buộc hiện tại | Yêu cầu nào không đạt, mức độ bắt buộc, phương án giảm thiểu |

Một hệ thống legacy có thể mang nợ kỹ thuật nhưng vẫn là phương án kinh tế tốt nhất để vận hành. Một thành phần mới có thể đã không còn phù hợp vì yêu cầu bảo mật hoặc quy mô thay đổi.

## 2. Khi nào nên cân nhắc viết lại?

Viết lại đáng được xem xét khi có bằng chứng cho thấy **cải tiến tại chỗ không thể giải quyết vấn đề với chi phí hoặc rủi ro chấp nhận được**.

Một số dấu hiệu:

### 2.1. Nền tảng không còn được hỗ trợ hoặc có rủi ro bảo mật nghiêm trọng

- Runtime, framework hoặc thư viện quan trọng đã hết hỗ trợ và không thể nâng cấp theo cách tương thích.
- Có lỗ hổng hoặc giới hạn bảo mật không thể giảm thiểu trong kiến trúc hiện tại.
- Cơ chế xác thực, mã hóa hoặc quản lý bí mật không đáp ứng yêu cầu bắt buộc.
- Việc duy trì phiên bản cũ tạo rủi ro tuân thủ hoặc vận hành không thể chấp nhận.

Ngay cả trong tình huống này, **viết lại toàn bộ chưa chắc là cách giảm rủi ro nhanh nhất**. Nâng runtime, thay adapter, cô lập thành phần hoặc chuyển một dịch vụ nhạy cảm có thể giải quyết vấn đề sớm hơn. Cần so sánh thời gian và rủi ro của từng phương án.

### 2.2. Cấu trúc cũ cản trở những thay đổi thiết yếu

Ví dụ:

- Một quy tắc nghiệp vụ phải được sửa ở nhiều nơi và thường xuyên bị lệch.
- Các module phụ thuộc vòng khiến thay đổi một chức năng buộc phải triển khai cả hệ thống.
- Không thể kiểm thử logic quan trọng nếu phải kết nối nhiều dịch vụ thật.
- Mô hình dữ liệu không thể biểu diễn yêu cầu mới mà không làm hỏng dữ liệu hoặc API hiện có.
- Một thành phần thay đổi thường xuyên liên tục gây lỗi hồi quy ở các thành phần khác.

Đây là bằng chứng đáng xem xét, nhưng vẫn phải hỏi **có thể tách một ranh giới cụ thể và cải tiến từng phần không**. Nếu vấn đề tập trung ở một module, thay toàn bộ sản phẩm có thể mở rộng phạm vi và rủi ro không cần thiết.

### 2.3. Chi phí duy trì đã trở thành rào cản có thể đo

Những tín hiệu có ích:

- Thời gian trung vị để hoàn thành một loại thay đổi tăng qua nhiều kỳ.
- Số module/file phải chạm vào cho cùng một loại yêu cầu tăng.
- Tỷ lệ lỗi hồi quy hoặc số lần rollback tăng trong những thay đổi liên quan.
- Thời gian điều tra và khôi phục sự cố cao vì thiếu quan sát hoặc ranh giới trách nhiệm.
- Chi phí hỗ trợ môi trường cũ, build cũ hoặc phụ thuộc không còn người duy trì tăng.
- Năng lực phát triển bị tiêu tốn quá nhiều cho việc giữ hệ thống hoạt động thay vì cải tiến sản phẩm.

Không chỉ đếm ticket hay dòng code. Cần xem **mẫu số, mức độ khó của yêu cầu, mức sử dụng và yếu tố gây nhiễu**. Nhiều PR trong một tháng có thể do nhóm đang phát triển tính năng mới, không phải vì mã hiện hữu tệ hơn.

## 3. Khi nào chưa nên viết lại?

Một số lý do nghe có vẻ thuyết phục nhưng không đủ:

- “Mã cũ dùng công nghệ lỗi thời” trong khi nền tảng vẫn được hỗ trợ và đáp ứng nhu cầu.
- “Code không đẹp” nhưng chưa xác định được chi phí hoặc rủi ro mà nó tạo ra.
- “Người mới không thích cấu trúc này” nhưng chưa thử cải thiện tài liệu, onboarding hoặc ranh giới module.
- “Chúng ta muốn dùng framework mới” nhưng lợi ích nghiệp vụ, vận hành và tương thích chưa được chứng minh.
- “Test cũ thiếu” nên muốn bỏ hệ thống để xây lại từ đầu; hệ thống mới cũng có thể thiếu test nếu chưa hiểu hợp đồng.
- “Viết lại sẽ nhanh hơn sửa” nhưng chưa tính khám phá hành vi, migration, chạy song song và hỗ trợ người dùng.

Viết lại không tự động xóa nợ kỹ thuật. Nếu nhóm mang nguyên cách phân chia trách nhiệm, mô hình dữ liệu và giả định cũ sang nền tảng mới, nợ có thể **tái xuất hiện với cú pháp hiện đại hơn**.

### Mùi khó chịu không đồng nghĩa phải thay toàn bộ

| Vấn đề quan sát | Phương án nhỏ hơn có thể thử trước |
| --- | --- |
| Một lớp quá lớn | Tách trách nhiệm và thêm test bảo vệ hành vi |
| Hai nơi lặp quy tắc | Tạo một policy dùng chung nếu chúng thực sự cùng hợp đồng |
| Một thư viện cũ có lỗ hổng | Nâng phiên bản hoặc thay adapter bị ảnh hưởng |
| Build khó tái lập | Chuẩn hóa toolchain, dependency và pipeline |
| Database khó thay đổi | Migration expand-contract, tách schema hoặc API |
| Không hiểu luồng nghiệp vụ | Truy vết caller, dữ liệu, log và lập characterization tests |
| Một module có coupling cao | Cô lập module qua facade/contract trước khi thay |

**Viết lại nên là một lựa chọn sau khi đã so sánh**, không phải phản xạ đầu tiên khi gặp mã khó chịu.

## 4. Thu thập bằng chứng trước khi lựa chọn

Một quyết định tốt cần ít nhất bốn nhóm thông tin:

1. **Bằng chứng kỹ thuật:** cấu trúc phụ thuộc, điểm thay đổi tập trung, độ phức tạp, trạng thái dữ liệu, giới hạn nền tảng.
2. **Bằng chứng về công việc:** thời gian thực hiện các thay đổi tương tự, số vòng review, công sức kiểm thử, nhu cầu triển khai.
3. **Bằng chứng về hành vi:** lỗi nghiệp vụ, sự cố, dữ liệu đầu ra, test hiện có, các quy tắc mà người dùng đang phụ thuộc.
4. **Bằng chứng vận hành:** tải, latency, error rate, thời gian khôi phục, chi phí hạ tầng và yêu cầu hỗ trợ.

### Bảng bằng chứng cần thu thập

| Câu hỏi | Nguồn dữ liệu có thể dùng | Giới hạn cần ghi |
| --- | --- | --- |
| Thành phần nào thường xuyên thay đổi? | Lịch sử Git, PR, change frequency | Churn cao có thể do phát triển tính năng |
| Thay đổi mất bao lâu? | Ticket, thời gian bắt đầu/kết thúc, review | Phải tách thời gian làm và thời gian chờ |
| Lỗi tập trung ở đâu? | Incident, bug report, postmortem | Cần truy nguyên nguyên nhân, không chỉ vị trí phát hiện |
| Phụ thuộc nào gây rủi ro? | Dependency graph, build, runtime inventory | Reflection/config động có thể không hiện đầy đủ |
| Hành vi thật là gì? | API contract, test, log, dữ liệu, người vận hành | Log không bao phủ mọi nhánh; dữ liệu có thể nhạy cảm |
| Có thể nâng cấp thay vì viết lại? | Spike nâng runtime/dependency, compatibility tests | Spike nhỏ chưa chứng minh migration toàn hệ thống |
| Chi phí duy trì là bao nhiêu? | Nhân lực, hạ tầng, license, hỗ trợ | Tránh tính trùng chi phí giữa nhóm |
| Rủi ro chuyển đổi là gì? | Data migration, cutover plan, rollback rehearsal | Rủi ro thường tăng ở ranh giới giữa hai hệ thống |

### Dùng số liệu như tín hiệu, không như phán quyết

Ví dụ, một module có cognitive complexity cao và 15 lần thay đổi trong 30 ngày có thể là hotspot đáng review. Nhưng nếu module đó là trung tâm của một tính năng đang phát triển mạnh, con số này chưa chứng minh cần viết lại. Cần xem **các thay đổi có bị kéo dài, gây lỗi hay phải chạm vào nhiều vùng không liên quan**.

Một tỷ lệ lỗi thấp cũng không chứng minh mã không có rủi ro nếu hệ thống thiếu telemetry hoặc có rất ít người dùng. Khi thiếu dữ liệu, ghi rõ **chưa đủ bằng chứng** thay vì suy đoán.

## 5. Khám phá hành vi ngầm của hệ thống cũ

Một trong những rủi ro lớn nhất khi viết lại là **chỉ triển khai lại những gì tài liệu nói**, trong khi người dùng và các hệ thống khác đang phụ thuộc vào những hành vi chưa từng được ghi thành hợp đồng.

Ví dụ, một API cũ có thể:

- Chấp nhận một trường bị bỏ trống và tự điền giá trị mặc định.
- Trả về một thứ tự dữ liệu không được tài liệu công bố nhưng client đang phụ thuộc.
- Làm tròn tiền ở một bước cụ thể.
- Xử lý yêu cầu lặp lại theo cách vô tình tạo idempotency.
- Trả mã lỗi đặc biệt mà một hệ thống bên ngoài dùng để quyết định retry.
- Giữ một hành vi kỳ lạ vì dữ liệu lịch sử đã được tạo theo quy tắc đó.

### Cách tìm hiểu

- Truy tìm **caller và consumer**: ứng dụng web, mobile, batch job, đối tác, báo cáo, công cụ nội bộ.
- Đọc **code path** từ điểm vào tới nơi lưu hoặc trả kết quả.
- Xem schema, migration, dữ liệu mẫu và các giá trị null/legacy.
- Kiểm tra log, metric, trace và postmortem trong phạm vi quyền truy cập phù hợp.
- Trao đổi với người vận hành, hỗ trợ khách hàng và người hiểu quy trình nghiệp vụ.
- Tìm các test hiện có, kể cả test không ổn định hoặc có vẻ lỗi thời.
- Quan sát hành vi thực tế trong môi trường thử nghiệm an toàn; không tùy tiện chạy thử thao tác ghi trên production.

### Phân loại hành vi trước khi tái tạo

| Loại hành vi | Cách xử lý khi viết lại |
| --- | --- |
| **Hợp đồng được xác nhận** | Bảo toàn hoặc thay đổi theo yêu cầu đã được phê duyệt |
| **Hành vi thực tế chưa được tài liệu hóa** | Điều tra consumer và nghiệp vụ trước khi quyết định |
| **Bug đã biết** | Không tự động sao chép; ghi nhận và quyết định cách sửa |
| **Hành vi tương thích cần duy trì tạm thời** | Có thể giữ qua adapter/versioning và kế hoạch loại bỏ |
| **Hành vi không còn được sử dụng** | Xác minh telemetry/consumer và có thể loại bỏ có kiểm soát |
| **Giả định chưa xác minh** | Ghi rõ người chịu trách nhiệm và cách kiểm tra |

Điều quan trọng là **không coi mọi hành vi hiện tại đều là yêu cầu**, nhưng cũng không tự ý xóa hành vi chỉ vì tài liệu không nhắc tới.

## 6. Characterization tests và acceptance tests có vai trò khác nhau

Khi làm việc với hệ thống cũ, đôi khi chưa biết đầy đủ kết quả đúng. **Characterization test** giúp ghi lại hành vi quan sát được của implementation hiện tại trên những đầu vào đã chọn. Nó tạo đường cơ sở để nhận diện thay đổi ngoài ý muốn.

**Acceptance/contract test** lại kiểm tra hành vi mà sản phẩm hoặc hợp đồng đã xác nhận cần đạt. Hai loại test này có thể cho kết quả khác nhau nếu hệ thống cũ có bug.

### Ví dụ Java: quy tắc giảm giá cũ

Giả sử hệ thống cũ tính tổng tiền theo cách:

1. Thành viên được giảm 5% trên subtotal.
2. Mã khuyến mãi giảm tiếp 10.00 đơn vị tiền.
3. Nếu kết quả âm, tổng tiền được chặn về 0.
4. Chỉ làm tròn đến hai chữ số thập phân ở bước cuối bằng HALF_UP.

Đây là **hành vi minh họa**; trước khi dùng làm hợp đồng, nhóm phải xác nhận thứ tự giảm giá và quy tắc làm tròn với chủ sở hữu nghiệp vụ.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class LegacyPricingCalculator {
    public BigDecimal calculate(
            BigDecimal subtotal,
            boolean member,
            boolean couponApplied) {
        BigDecimal total = subtotal;

        if (member) {
            total = total.multiply(new BigDecimal("0.95"));
        }
        if (couponApplied) {
            total = total.subtract(new BigDecimal("10.00"));
        }
        if (total.signum() < 0) {
            total = BigDecimal.ZERO;
        }

        return total.setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Một characterization test có thể ghi lại kết quả đang quan sát:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class LegacyPricingCalculatorCharacterizationTest {
    private final LegacyPricingCalculator calculator =
        new LegacyPricingCalculator();

    @Test
    void recordsCurrentMemberAndCouponOrder() {
        BigDecimal actual = calculator.calculate(
            new BigDecimal("100.00"),
            true,
            true
        );

        assertEquals(new BigDecimal("85.00"), actual);
    }

    @Test
    void recordsCurrentFloorAtZero() {
        BigDecimal actual = calculator.calculate(
            new BigDecimal("5.00"),
            false,
            true
        );

        assertEquals(new BigDecimal("0.00"), actual);
    }
}
~~~

Test đầu tiên cho thấy kết quả theo thứ tự giảm 5% trước rồi trừ 10.00. Nếu đảo thứ tự, kết quả sẽ là 85.50 thay vì 85.00. Test thứ hai ghi lại việc chặn tổng âm về 0.

**Nhưng characterization test không tự chứng minh chính sách này là đúng.** Nếu chủ sở hữu nghiệp vụ xác nhận coupon phải được áp dụng trước giảm giá thành viên, test đầu tiên đang mô tả bug cần sửa. Khi đó cần tạo acceptance test theo hợp đồng mới, ghi nhận thay đổi có chủ đích và tránh “bảo vệ” lỗi cũ chỉ vì nó đã tồn tại lâu.

### Nguyên tắc khi tạo test cho mã cũ

- Ghi rõ test nào **ghi nhận hiện trạng**, test nào **định nghĩa hành vi mong muốn**.
- Chọn dữ liệu đại diện và giá trị biên, không chỉ dùng một vài ví dụ dễ chạy.
- Lưu ý timezone, locale, thứ tự xử lý, rounding, null, exception và side effects.
- Nếu đầu ra phụ thuộc thời gian hoặc dữ liệu ngoài, kiểm soát clock/fixture ở mức có thể.
- Không biến mọi kết quả cũ thành bất biến; cần người có thẩm quyền xác nhận quy tắc.
- Khi test không thể viết do phụ thuộc quá nhiều, có thể bắt đầu bằng một seam hoặc adapter nhỏ để cô lập hành vi.

## 7. So sánh các lựa chọn thay vì chỉ có “giữ” hoặc “viết lại”

Có nhiều phương án trung gian:

| Phương án | Khi phù hợp | Lợi ích | Rủi ro/chi phí |
| --- | --- | --- | --- |
| **Giữ nguyên và theo dõi** | Hệ thống ổn định, vấn đề chưa gây chi phí đáng kể | Không tạo rủi ro chuyển đổi | Nợ hiện tại tiếp tục tồn tại |
| **Thêm kiểm soát** | Rủi ro tập trung ở một điểm có thể bảo vệ | Giảm rủi ro nhanh, phạm vi nhỏ | Có thể giữ kiến trúc khó thay đổi |
| **Refactor tại chỗ** | Hợp đồng và kiến trúc còn phù hợp, vấn đề nằm ở cấu trúc | Cải thiện từng phần, tận dụng hệ thống đang chạy | Cần test và có thể vẫn bị giới hạn nền tảng |
| **Thay adapter/thư viện** | Một dependency hoặc tích hợp đã trở thành vấn đề | Giải quyết nguyên nhân hẹp | Tương thích API và vận hành |
| **Thay một lát cắt nghiệp vụ** | Có thể cô lập một capability hoặc luồng rõ ràng | Học được qua phạm vi nhỏ, giảm dần phụ thuộc | Phải duy trì ranh giới hai hệ thống |
| **Strangler migration** | Có thể định tuyến từng phần sang implementation mới | Chuyển đổi theo giai đoạn, có thể rollback phạm vi | Routing, dữ liệu và quan sát phức tạp |
| **Viết lại toàn bộ** | Có ràng buộc nền tảng/kiến trúc mang tính hệ thống, phương án nhỏ hơn không khả thi | Có thể thay đổi mô hình và nền tảng đồng bộ | Phạm vi, chi phí, thời gian và rủi ro rất lớn |

**Không có lựa chọn nào luôn tốt nhất.** Mức độ phù hợp phụ thuộc khả năng cô lập, yêu cầu thời gian, rủi ro dữ liệu, năng lực nhóm và chi phí duy trì hai phiên bản.

### Ma trận quyết định gợi ý

| Bằng chứng | Phương án nên xem xét trước |
| --- | --- |
| Vấn đề nhỏ, ít thay đổi, không có tác động đáng kể | Giữ nguyên, theo dõi |
| Lỗi bảo mật có thể cô lập và vá ngay | Vá/contain trước, lập kế hoạch nâng cấp hoặc thay thế |
| Logic trùng lặp trong vài module có cùng hợp đồng | Refactor và gom trách nhiệm |
| Một thư viện hoặc giao thức cũ chặn nâng cấp | Thay adapter hoặc capability bị ảnh hưởng |
| Một luồng có ranh giới rõ, consumer kiểm soát được | Thay từng lát cắt và chuyển dần traffic |
| Mọi module bị khóa bởi mô hình dữ liệu/giao thức không thể đáp ứng yêu cầu bắt buộc | Đánh giá chương trình thay thế rộng hơn, có thể full rewrite |

Ma trận chỉ giúp **đặt câu hỏi**, không thay thế đánh giá chi phí và rủi ro. Ví dụ một thành phần nhỏ nhưng xử lý thanh toán có thể cần ưu tiên hơn một module lớn ít ảnh hưởng.

## 8. Tính chi phí vòng đời, không chỉ chi phí viết mã mới

Một dự án viết lại thường có những khoản chi phí bị bỏ sót:

- **Khám phá:** đọc mã, phỏng vấn, phân tích dữ liệu và tìm consumer chưa được tài liệu hóa.
- **Đặc tả:** thống nhất quy tắc, lỗi, tính tương thích và hành vi cần thay đổi.
- **Xây dựng:** thiết kế, implementation, test, security review và tài liệu.
- **Tích hợp:** API, database, queue, file format, identity, monitoring và đối tác.
- **Di trú dữ liệu:** chuyển đổi schema, làm sạch dữ liệu, backfill, đối soát và xử lý dữ liệu lỗi.
- **Vận hành song song:** hạ tầng, giám sát, hỗ trợ và đồng bộ trong giai đoạn chuyển đổi.
- **Cutover:** chuyển traffic, điều phối phiên bản, xử lý request đang chạy và rollback.
- **Đào tạo và chuyển giao:** người vận hành, hỗ trợ khách hàng, nhóm phát triển và đối tác.
- **Ngừng hệ thống cũ:** lưu trữ dữ liệu, đáp ứng audit, gỡ credential và hạ tầng.

Chi phí tiếp tục dùng hệ thống cũ cũng cần được tính:

- Công bảo trì và xử lý lỗi.
- Hạ tầng, license và chi phí hỗ trợ.
- Tốc độ đưa tính năng mới ra thị trường.
- Tổn thất từ sự cố hoặc giới hạn không thể đáp ứng.
- Chi phí cơ hội do nhóm phải dành thời gian né tránh cấu trúc cũ.

### Mô hình so sánh đơn giản

Có thể so sánh hai phương án theo cùng một khoảng thời gian:

~~~text
Tổng chi phí phương án
  = chi phí triển khai ban đầu
  + chi phí vận hành trong kỳ
  + chi phí thay đổi/bảo trì trong kỳ
  + chi phí sự cố và rủi ro kỳ vọng
  + chi phí chuyển đổi và kết thúc vòng đời
~~~

Đây là **khung liệt kê**, không phải công thức cho phép cộng chính xác mọi loại rủi ro. Xác suất sự cố, mức thiệt hại và thời gian dự báo thường không chắc chắn. Nên dùng khoảng ước lượng, kịch bản và giả định được công bố thay vì tạo ra một con số ROI giả chính xác.

### Ví dụ ước lượng minh họa

Giả sử nhóm ước lượng:

| Khoản mục | Tiếp tục cải tiến hệ thống cũ | Thay một capability |
| --- | ---: | ---: |
| Công ban đầu | 20 ngày công | 55 ngày công |
| Công bảo trì liên quan trong 12 tháng | 35 ngày công | 15 ngày công |
| Công tích hợp/chuyển đổi | 5 ngày công | 20 ngày công |
| Tổng công ước lượng | 60 ngày công | 90 ngày công |

Trong kịch bản này, thay capability tốn nhiều công hơn trong 12 tháng đầu. Nó chỉ đáng chọn nếu lợi ích bổ sung — chẳng hạn đáp ứng yêu cầu bảo mật bắt buộc, giảm thời gian phát triển về sau hoặc loại bỏ rủi ro không thể chấp nhận — đủ lớn so với chênh lệch. Nếu yêu cầu chỉ là giảm một số lần sửa lặp, cải tiến tại chỗ có thể hợp lý hơn.

Các con số chỉ là **ví dụ lập luận**. Ước lượng thực tế cần tách công kỹ thuật, lịch chờ, chi phí hạ tầng, hỗ trợ và bất định; không cộng trùng cùng một khoản giữa nhiều nhóm.

## 9. Ví dụ Java: thay một capability qua facade

Giả sử nhóm chưa muốn thay toàn bộ ứng dụng hóa đơn. Họ chỉ muốn thay **bộ tính giá** vì quy tắc giảm giá cũ khó thay đổi. Một cách giảm rủi ro là đặt một hợp đồng ổn định ở ranh giới, rồi có thể định tuyến giữa implementation cũ và mới.

### 9.1. Định nghĩa hợp đồng chung

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record PricingRequest(
    BigDecimal subtotal,
    boolean member,
    boolean couponApplied
) {
    public PricingRequest {
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.signum() < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }
    }
}
~~~

~~~java
import java.math.BigDecimal;

public interface PricingEngine {
    BigDecimal calculate(PricingRequest request);
}
~~~

Hợp đồng này chỉ là ví dụ tối giản. Dự án thực tế cần quyết định rõ currency, scale, thuế, rounding, nullability, lỗi và phiên bản chính sách. Không nên dùng một `BigDecimal` trần nếu nhiều loại tiền tệ hoặc quy tắc làm tròn khác nhau có thể xuất hiện.

### 9.2. Adapter cho hệ thống cũ

~~~java
import java.util.Objects;

public final class LegacyPricingAdapter implements PricingEngine {
    private final LegacyPricingCalculator legacy;

    public LegacyPricingAdapter(LegacyPricingCalculator legacy) {
        this.legacy = Objects.requireNonNull(legacy, "legacy");
    }

    @Override
    public java.math.BigDecimal calculate(PricingRequest request) {
        Objects.requireNonNull(request, "request");
        return legacy.calculate(
            request.subtotal(),
            request.member(),
            request.couponApplied()
        );
    }
}
~~~

Adapter giúp phần ứng dụng gọi theo **một hợp đồng mới**, trong khi implementation cũ vẫn được sử dụng. Nó cũng tạo một vị trí để kiểm soát chuyển đổi tham số và exception.

### 9.3. Implementation mới

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class ReplacementPricingEngine implements PricingEngine {
    private static final BigDecimal MEMBER_FACTOR =
        new BigDecimal("0.95");
    private static final BigDecimal COUPON_DISCOUNT =
        new BigDecimal("10.00");

    @Override
    public BigDecimal calculate(PricingRequest request) {
        Objects.requireNonNull(request, "request");

        BigDecimal total = request.subtotal();
        if (request.member()) {
            total = total.multiply(MEMBER_FACTOR);
        }
        if (request.couponApplied()) {
            total = total.subtract(COUPON_DISCOUNT);
        }
        return total.max(BigDecimal.ZERO)
            .setScale(2, RoundingMode.HALF_UP);
    }
}
~~~

Implementation mới minh họa cách đưa quy tắc vào một thành phần riêng, nhưng **không nên giả định nó đã đúng chỉ vì code rõ hơn**. Nó cần acceptance tests dựa trên chính sách đã được phê duyệt, bao gồm thứ tự giảm giá, làm tròn, dữ liệu thiếu và giới hạn tiền.

### 9.4. Định tuyến có kiểm soát

~~~java
import java.util.Objects;
import java.util.function.Predicate;

public final class PricingRouter implements PricingEngine {
    private final PricingEngine legacy;
    private final PricingEngine replacement;
    private final Predicate<PricingRequest> useReplacement;

    public PricingRouter(
            PricingEngine legacy,
            PricingEngine replacement,
            Predicate<PricingRequest> useReplacement) {
        this.legacy = Objects.requireNonNull(legacy, "legacy");
        this.replacement = Objects.requireNonNull(replacement, "replacement");
        this.useReplacement =
            Objects.requireNonNull(useReplacement, "useReplacement");
    }

    @Override
    public java.math.BigDecimal calculate(PricingRequest request) {
        return useReplacement.test(request)
            ? replacement.calculate(request)
            : legacy.calculate(request);
    }
}
~~~

Router minh họa cách chuyển **một tập yêu cầu có kiểm soát** sang implementation mới. Predicate trong ví dụ có thể đại diện cho feature flag hoặc cohort đã được xác định; trong hệ thống thật, cấu hình cần ổn định, có audit và không thay đổi tùy tiện giữa các bước của cùng một giao dịch.

Nếu checkout dùng engine mới nhưng hóa đơn cuối cùng dùng engine cũ cho cùng một đơn, kết quả có thể lệch. Vì vậy cần quyết định **phiên bản chính sách nào gắn với một đơn hàng** và lưu thông tin cần thiết để các bước sau dùng cùng hợp đồng.

### 9.5. Kiểm thử hợp đồng giữa hai implementation

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class PricingEngineContractTest {
    private final PricingEngine legacy =
        new LegacyPricingAdapter(new LegacyPricingCalculator());
    private final PricingEngine replacement =
        new ReplacementPricingEngine();

    @Test
    void bothImplementationsMatchApprovedExample() {
        PricingRequest request = new PricingRequest(
            new BigDecimal("100.00"),
            true,
            true
        );

        BigDecimal expected = new BigDecimal("85.00");
        assertEquals(expected, legacy.calculate(request));
        assertEquals(expected, replacement.calculate(request));
    }
}
~~~

Test này chỉ có giá trị nếu `85.00` đã được **chủ sở hữu nghiệp vụ xác nhận**. Nếu nó chỉ được sao chép từ hệ thống cũ, test có thể giữ lại một bug. Cần có thêm ca giá trị biên, dữ liệu không hợp lệ, rounding, coupon và quy tắc thay đổi theo thời điểm.

**Không so sánh hai implementation bằng equality duy nhất rồi kết luận đúng.** Hai bên có thể cùng sai. Hãy dùng acceptance tests độc lập, và chỉ chạy shadow comparison khi thao tác tính toán thuần, xác định và không tạo tác dụng phụ.

## 10. Strangler migration: chuyển từng phần thay vì cắt một lần

**Strangler pattern** là cách thay thế dần một hệ thống bằng cách đưa một lớp định tuyến/facade vào trước hệ thống cũ, rồi chuyển từng capability hoặc luồng sang hệ thống mới. Hệ thống cũ tiếp tục phục vụ phần chưa thay thế.

Một trình tự khái niệm:

~~~text
                Client / Consumer
                       |
                       v
                API / Routing Layer
                       |
             +---------+---------+
             |                   |
             v                   v
        Legacy system       New capability
             |                   |
             +---------+---------+
                       |
                Data / Events
                       |
                 Reconciliation
~~~

Sơ đồ này chỉ mô tả ý tưởng. Trong hệ thống thật, không nên để cả hai bên **cùng ghi một nguồn dữ liệu** mà không có quy tắc sở hữu rõ. Cần xác định hệ thống nào là source of truth, cách phát sự kiện, xử lý retry và đối soát.

### Các bước chuyển đổi

1. **Đặt facade hoặc ranh giới định tuyến.** Consumer không gọi trực tiếp vào mọi chi tiết của implementation cũ.
2. **Chọn một capability nhỏ.** Phạm vi có thể đo, có owner và có hợp đồng rõ.
3. **Đặc tả hành vi.** Dùng characterization/contract/acceptance tests để phân biệt hành vi cần giữ và hành vi cần sửa.
4. **Xây implementation mới và adapter.** Không thay đổi tất cả consumer cùng lúc nếu có thể tránh.
5. **Chạy kiểm tra song song ở chế độ an toàn.** Chỉ so sánh output nếu tính toán không có side effects; không gửi hai lệnh thanh toán hoặc hai lần ghi dữ liệu thật.
6. **Chuyển một cohort nhỏ.** Theo dõi lỗi, latency, kết quả nghiệp vụ và khả năng rollback.
7. **Mở rộng dần.** Chỉ tăng phạm vi khi bằng chứng cho thấy hành vi và vận hành đạt yêu cầu.
8. **Ngừng đường cũ.** Xác minh consumer đã chuyển, dữ liệu đã đối soát và quy trình hỗ trợ không còn phụ thuộc trước khi decommission.

### Những rủi ro cần kiểm soát

- **Routing không nhất quán:** một giao dịch đi qua hai engine khác nhau ở các bước.
- **Dual write:** hai hệ thống ghi cùng một dữ liệu và tạo trạng thái lệch.
- **Event ordering:** sự kiện đến trễ hoặc lặp khiến trạng thái mới bị ghi đè.
- **Migration dữ liệu:** bản ghi cũ thiếu trường, giá trị không hợp lệ hoặc có quy tắc mặc định khác.
- **Rollback giả định:** ứng dụng cũ không đọc được dữ liệu đã được hệ thống mới ghi theo schema mới.
- **Quan sát thiếu:** nhóm không biết cohort nào gặp lỗi và lỗi bắt đầu từ phiên bản nào.

Strangler giảm quy mô mỗi bước, nhưng **tăng thời gian vận hành hai hệ thống và số ranh giới cần quản lý**. Nếu không thể kiểm soát routing, dữ liệu và ownership, cách chuyển đổi này có thể tốn kém hơn một phương án nâng cấp trực tiếp.

## 11. Migration dữ liệu và tương thích ngược

Viết lại thường thay đổi mô hình dữ liệu. Đây là phần có thể nguy hiểm hơn việc viết service mới.

Một chiến lược phổ biến là **expand–migrate–contract**:

1. **Expand:** thêm cấu trúc mới theo cách phiên bản cũ vẫn hoạt động, chẳng hạn cột mới nullable hoặc bảng mới.
2. **Migrate:** backfill/chuyển dữ liệu, đối soát số lượng và giá trị, theo dõi lỗi.
3. **Switch:** chuyển consumer/producer theo cohort hoặc theo capability.
4. **Contract:** chỉ bỏ cấu trúc cũ sau khi xác minh không còn consumer cần nó và phiên bản cũ đã được ngừng an toàn.

Ví dụ, nếu hệ thống cũ lưu trạng thái đơn hàng bằng số nguyên còn hệ thống mới dùng enum/string, cần một **mapping tường minh**. Không nên dựa vào thứ tự enum hoặc giả định mọi giá trị cũ đều thuộc tập hợp mới.

### Những câu hỏi về dữ liệu

- Có bao nhiêu bản ghi và phân bố giá trị ra sao?
- Có bản ghi null, sai định dạng hoặc giá trị không còn được hỗ trợ không?
- Có thể chuyển đổi lặp lại an toàn (idempotent) không?
- Làm sao phát hiện bản ghi đã chuyển một phần?
- Nếu backfill dừng giữa chừng, có thể tiếp tục không?
- Có cần giữ lịch sử, audit hoặc khả năng đối soát không?
- Phiên bản ứng dụng cũ có thể đọc/ghi trong giai đoạn chuyển đổi không?
- Khi rollback, dữ liệu mới có thể được đọc bởi hệ thống cũ không?

**Rollback ứng dụng không tự động rollback dữ liệu.** Nếu schema hoặc dữ liệu mới không tương thích ngược, có thể cần forward fix hoặc kế hoạch phục hồi riêng. Phải thử diễn tập migration và khôi phục với dữ liệu đại diện trước khi chuyển production.

## 12. Kiểm soát rollout, rollback và tác dụng phụ

Một kế hoạch chuyển đổi cần xác định:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| **Cohort** | Người dùng, tenant hoặc luồng nào chuyển trước? |
| **Feature flag** | Ai được bật/tắt, flag có ổn định và audit được không? |
| **Routing** | Một request/giao dịch có luôn dùng cùng phiên bản logic không? |
| **Data ownership** | Hệ thống nào là nguồn dữ liệu có thẩm quyền? |
| **Idempotency** | Retry hoặc gửi lại có tạo tác dụng phụ trùng không? |
| **Monitoring** | Theo dõi metric, trace và lỗi nào để quyết định tiếp tục/dừng? |
| **Rollback** | Có thể quay lại code cũ với dữ liệu hiện tại không? |
| **Forward recovery** | Nếu không rollback an toàn, kế hoạch sửa tiến tới là gì? |
| **Communication** | Ai cần biết thời điểm thay đổi, lỗi và giới hạn hỗ trợ? |

### Không dùng shadow mode tùy tiện

Shadow execution có thể hữu ích khi hệ thống mới chỉ **tính toán kết quả** và không tạo side effects. Ví dụ, chạy engine cũ để phục vụ request và chạy engine mới ở chế độ chỉ tính, sau đó so sánh giá trị.

Không được nhân đôi:

- Lệnh thanh toán hoặc hoàn tiền.
- Email, SMS hoặc thông báo tới người dùng.
- Ghi dữ liệu nghiệp vụ mà không có cơ chế phân biệt.
- Lệnh gọi đối tác có tác dụng phụ.

Nếu cần kiểm tra hành vi có side effects, hãy dùng môi trường giả lập, adapter ghi nhận lệnh, hoặc dữ liệu thử được cô lập. Khi so sánh, phải che dữ liệu nhạy cảm và xác định rõ output nào được lưu.

### Rollback cần được thử, không chỉ viết trong kế hoạch

Một kế hoạch “có thể tắt feature flag” chưa đủ nếu hệ thống mới đã ghi dữ liệu mà hệ thống cũ không đọc được. Cần kiểm tra:

- Tắt routing có đưa traffic về hệ thống cũ an toàn không?
- Dữ liệu đã ghi trong thời gian cohort có tương thích không?
- Có request đang chạy hoặc message trong queue chưa xử lý không?
- Có giao dịch cần đối soát trước khi quay lại không?
- Có thể giữ nguyên lịch sử và audit không?

Với hệ thống giao dịch, đôi khi **forward recovery** an toàn hơn rollback. Quyết định phải dựa trên trạng thái dữ liệu thực tế và hợp đồng giữa các phiên bản.

## 13. Đánh giá kết quả sau khi thay thế

Sau khi chuyển một capability, cần kiểm chứng cả ba lớp:

### 13.1. Cấu trúc và khả năng thay đổi

- Có giảm số nơi sở hữu cùng một quy tắc không?
- Consumer có phụ thuộc vào interface ổn định thay vì chi tiết nội bộ không?
- Số module bị ảnh hưởng bởi một thay đổi cùng loại có giảm không?
- Nhóm có thể kiểm thử capability mới độc lập hơn không?

### 13.2. Hành vi và tương thích

- Acceptance/contract tests có đạt trên các đầu vào và trạng thái đã xác nhận không?
- Có khác biệt nào giữa hệ thống cũ và mới? Khác biệt nào là sửa bug được phê duyệt?
- Dữ liệu trước và sau migration có được đối soát?
- Consumer cũ, API version cũ và job nền có còn hoạt động?

### 13.3. Vận hành và chi phí thực tế

- Latency, error rate, throughput và chi phí hạ tầng có thay đổi không?
- Sự cố và thời gian phục hồi có giảm trong kỳ quan sát đủ ý nghĩa không?
- Thời gian thực hiện những thay đổi tương tự có giảm không?
- Chi phí vận hành hai hệ thống có được loại bỏ sau decommission không?
- Có phát sinh loại lỗi mới hoặc điểm tập trung rủi ro mới không?

### Ví dụ bảng theo dõi trước–sau

| Chỉ số minh họa | Trước chuyển đổi | Sau chuyển đổi | Cách diễn giải |
| --- | ---: | ---: | --- |
| Vị trí triển khai chính sách | 3 | 1 | Cải thiện cấu trúc đã quan sát |
| Số module cần sửa cho thay đổi cùng loại | 4 | 2 | Chỉ báo sớm về phạm vi thay đổi |
| Trung vị thời gian PR cùng loại | 8 giờ | 5 giờ | Cần kiểm tra độ khó và thời gian chờ có tương đương |
| Lỗi hồi quy được ghi nhận | 2/18 thay đổi | 1/20 thay đổi | Mẫu nhỏ, chưa đủ kết luận dài hạn |
| p95 latency | 180 ms | 195 ms | Cần điều tra tác động hiệu năng |
| Chi phí hạ tầng trong giai đoạn chạy song song | 1 đơn vị | 1,6 đơn vị | Chi phí chuyển đổi đang tăng tạm thời |

Các số liệu chỉ là ví dụ minh họa. Không nên tuyên bố thành công chỉ vì một số cột tốt hơn. Có thể cấu trúc và thời gian PR đã cải thiện, trong khi latency tăng và chi phí vận hành song song chưa giảm. Báo cáo phải ghi **phạm vi, mẫu số, khoảng quan sát và rủi ro còn lại**.

## 14. Viết quyết định kỹ thuật có thể xem lại

Một quyết định viết lại hoặc thay thế capability nên được lưu bằng ADR hoặc tài liệu quyết định có cấu trúc:

~~~text
Tiêu đề:
  Thay thế capability tính giá

Bối cảnh:
  Quy tắc giảm giá nằm ở ba module.
  Các thay đổi cùng loại thường phải sửa nhiều điểm.
  Hợp đồng hiện tại và consumer đã được kiểm kê.

Vấn đề có bằng chứng:
  <PR/incident/metric/test đã xác minh>

Phương án:
  A. Giữ nguyên và thêm kiểm soát
  B. Refactor tại chỗ
  C. Thay capability qua facade
  D. Viết lại toàn bộ

Quyết định:
  <phương án được chọn và lý do>

Chi phí/rủi ro:
  <ước lượng, giả định, bất định, migration, vận hành>

Bảo toàn hành vi:
  <contract tests, characterization tests, acceptance tests>

Rollout/rollback:
  <cohort, data ownership, quan sát, điều kiện dừng>

Tiêu chí đánh giá:
  <baseline, kỳ quan sát, chỉ số, owner>

Rủi ro còn lại:
  <những điều chưa được giải quyết>
~~~

Đây là **mẫu minh họa**, không phải ADR đã được phê duyệt. Một quyết định tốt cũng ghi rõ **vì sao không chọn** các phương án khác, để người bảo trì sau này hiểu những đánh đổi đã được cân nhắc.

## 15. Những sai lầm thường gặp khi quyết định viết lại

| Sai lầm | Hệ quả | Cách tránh |
| --- | --- | --- |
| Viết lại vì công nghệ mới hấp dẫn | Chi phí lớn nhưng vấn đề gốc vẫn còn | Nêu vấn đề và lợi ích đo được trước |
| Chỉ đọc tài liệu, không truy vết consumer | Bỏ sót hành vi ngầm và hợp đồng cũ | Kiểm kê caller, dữ liệu, log và vận hành |
| Sao chép mọi output cũ thành expected | Giữ cả bug cũ | Phân biệt characterization với acceptance |
| Bỏ test vì hệ thống mới “đơn giản hơn” | Mất bằng chứng cho các đường quan trọng | Viết test theo hợp đồng trước và trong chuyển đổi |
| Thay nhiều module cùng lúc | Khó xác định nguyên nhân khi lỗi | Chia theo capability và ranh giới có thể kiểm soát |
| Chạy song song hai hệ thống có side effects | Thanh toán/ghi dữ liệu trùng | Chỉ shadow logic thuần hoặc dùng adapter giả lập |
| Coi feature flag là rollback đầy đủ | Dữ liệu mới có thể không tương thích hệ thống cũ | Diễn tập cả code path và data compatibility |
| Đánh giá bằng số dòng hoặc điểm complexity | Tối ưu hình thức, bỏ sót chi phí thật | Theo dõi thay đổi, sự cố và chi phí vận hành |
| Không có kế hoạch ngừng hệ thống cũ | Duy trì hai hệ thống vô thời hạn | Định nghĩa tiêu chí decommission từ đầu |

## 16. Bài tập tình huống

Một doanh nghiệp đang dùng hệ thống quản lý đơn hàng đã tồn tại 9 năm. Nhóm đề xuất viết lại toàn bộ vì:

- Build phụ thuộc vào một JDK cũ.
- Logic tính phí và kiểm tra trạng thái đơn bị lặp ở nhiều module.
- Các PR liên quan tới đơn hàng thường mất nhiều vòng review.
- Có một sự cố hóa đơn sai sau khi thay đổi ngưỡng miễn phí.
- Một số đối tác vẫn gọi API phiên bản cũ.

Nhóm đưa ra ước lượng sơ bộ: viết lại toàn bộ mất 8 tháng; refactor và nâng cấp từng phần mất 4 tháng; chưa có danh sách đầy đủ consumer, dữ liệu lịch sử và quy tắc lỗi của API cũ.

**Câu hỏi A.** Những bằng chứng nào hiện có hỗ trợ việc xử lý hệ thống? Những thông tin nào còn thiếu để quyết định viết lại toàn bộ?

**Câu hỏi B.** Hãy đề xuất ít nhất ba phương án, bao gồm một phương án không viết lại toàn bộ.

**Câu hỏi C.** Vì sao characterization tests cần được phân biệt với acceptance tests trong trường hợp này?

**Câu hỏi D.** Nếu thay capability tính phí trước, cần kiểm soát những rủi ro nào khi hệ thống cũ và mới cùng tồn tại?

**Câu hỏi E.** Hãy viết một kết luận tạm thời có thể trình bày với người ra quyết định mà không khẳng định quá mức bằng chứng hiện có.

### Gợi ý đáp án

**A.** Có bằng chứng về nền tảng cũ, logic lặp, chi phí review và sự cố hóa đơn. Nhưng chưa biết JDK cũ có thể nâng cấp tại chỗ không, sự cố xuất phát chính xác từ điểm lặp nào, API consumer nào còn hoạt động, dữ liệu lịch sử có dạng gì, mức sử dụng và chi phí vận hành của từng module ra sao. Cần thu thập thêm trước khi chọn phạm vi thay thế.

**B.** Có thể cân nhắc: (1) nâng JDK và dependency trước, đồng thời thêm kiểm soát; (2) refactor chính sách tính phí và trạng thái đơn theo từng module; (3) thay capability tính phí qua facade/strangler; (4) viết lại toàn bộ nếu đánh giá chứng minh kiến trúc/nền tảng hiện tại không thể đáp ứng yêu cầu bắt buộc với chi phí hợp lý.

**C.** Characterization tests giúp ghi nhận những gì hệ thống cũ đang làm, kể cả hành vi chưa được tài liệu hóa. Acceptance tests xác định hành vi cần đạt theo chính sách đã được xác nhận. Nếu chỉ sao chép kết quả cũ, nhóm có thể giữ bug hóa đơn sai; nếu chỉ viết test theo tài liệu thiếu, có thể bỏ sót hợp đồng mà đối tác đang sử dụng.

**D.** Cần thống nhất routing theo đơn, phiên bản chính sách được lưu, source of truth, migration dữ liệu, tính idempotent, không dual-write tùy tiện, đối soát output, feature flag, telemetry, điều kiện dừng và khả năng rollback/forward recovery.

**E.** Ví dụ: “Bằng chứng hiện tại cho thấy chi phí thay đổi và rủi ro tính phí lệch đáng được xử lý. Chưa đủ dữ liệu để kết luận cần viết lại toàn bộ vì chưa kiểm kê consumer, dữ liệu và khả năng nâng cấp nền tảng. Đề xuất thực hiện một spike có giới hạn: nâng JDK ở module ít phụ thuộc, đặc tả chính sách tính phí bằng acceptance tests và thử thay capability qua facade. Sau khi đo chi phí, kiểm tra tương thích và đánh giá rollout, nhóm sẽ quyết định phạm vi thay thế tiếp theo.”

## Ghi nhớ

**Viết lại hệ thống hiện hữu là một quyết định về chi phí và rủi ro vòng đời, không phải cuộc thi giữa công nghệ cũ và mới.** Trước khi chọn, hãy xác định vấn đề thực tế, tìm cơ chế gây ra chi phí, khám phá hợp đồng và hành vi ngầm, rồi so sánh giữ nguyên, bổ sung kiểm soát, refactor, thay từng capability và viết lại toàn bộ.

Nếu thay thế, cần bảo toàn những hành vi đã xác nhận, chủ động quyết định những bug cần sửa, kiểm thử tại ranh giới, quản lý dữ liệu và consumer, rollout theo phạm vi có thể quan sát, đồng thời diễn tập rollback hoặc forward recovery. **Một quyết định tốt nêu rõ điều đã biết, giả định, chi phí, rủi ro còn lại và bằng chứng sẽ dùng để đánh giá kết quả.**
