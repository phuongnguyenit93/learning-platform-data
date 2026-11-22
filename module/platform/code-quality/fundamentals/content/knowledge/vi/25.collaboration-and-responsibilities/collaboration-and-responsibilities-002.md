# Thống nhất tiêu chí hoàn thành của một thay đổi

Một lập trình viên hoàn tất phần code của một tính năng, unit test đều chạy qua và pull request đã được merge. Nhưng khi người dùng thử, họ phát hiện tài liệu API vẫn mô tả trường cũ, dashboard không có metric để phát hiện lỗi, migration chưa tương thích với phiên bản ứng dụng đang chạy và nhóm vận hành không biết cách rollback. Từng người tham gia đều có thể nghĩ phần việc của mình đã xong, trong khi thay đổi chưa sẵn sàng để sử dụng an toàn.

Tình huống này thường không bắt nguồn từ thiếu nỗ lực. Nó cho thấy nhóm chưa có cách hiểu chung về câu hỏi: **khi nào một thay đổi thực sự được coi là hoàn thành?**

**Tiêu chí hoàn thành (*Definition of Done*, DoD)** là thỏa thuận chung mô tả những điều kiện chất lượng tối thiểu mà một thay đổi phải đáp ứng trước khi nhóm gọi nó là hoàn tất. DoD giúp tác giả, reviewer, người kiểm thử, người phụ trách sản phẩm và vận hành dùng cùng một chuẩn khi đánh giá kết quả. Nó biến kỳ vọng vốn dễ bị hiểu ngầm thành những điều kiện có thể quan sát và kiểm chứng.

Trong chương **Cộng tác và trách nhiệm** thuộc module `CODE_QUALITY_FUNDAMENTALS`, sự thống nhất về DoD góp phần giữ mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Một thay đổi chỉ hoàn thành khi kết quả đáp ứng mục tiêu, được kiểm tra phù hợp với rủi ro, có thể bảo trì và được bàn giao với thông tin cần thiết.

Sau bài học, bạn có thể:

- Giải thích DoD và phân biệt nó với acceptance criteria, Definition of Ready và việc hoàn thành một task cá nhân.
- Xây dựng tiêu chí chung có thể quan sát, kiểm tra và áp dụng nhất quán.
- Xác định trách nhiệm của tác giả, reviewer, nhóm sản phẩm, kiểm thử và vận hành.
- Chọn mức kiểm thử, review và kiểm tra chất lượng dựa trên loại thay đổi và rủi ro.
- Đưa bảo mật, tài liệu, khả năng quan sát và khả năng triển khai vào tiêu chí khi phù hợp.
- Xử lý ngoại lệ có kiểm soát và không biến DoD thành một checklist hình thức.
- Áp dụng DoD cho bugfix, refactor, API, migration và thay đổi cấu hình.
- Cải tiến thỏa thuận khi nhóm có bằng chứng về lỗi lọt, chi phí hoặc tiêu chí không còn phù hợp.

## 1. Definition of Done là thỏa thuận chất lượng chung

DoD trả lời câu hỏi:

> Nhóm cần thấy những điều gì đúng trước khi gọi một thay đổi là hoàn thành?

Ví dụ, với một thay đổi phần mềm thông thường, nhóm có thể yêu cầu:

- Hành vi đáp ứng mục tiêu và acceptance criteria đã thống nhất.
- Code được review theo quy trình của nhóm.
- Các test phù hợp đã chạy và đạt.
- Không còn lỗi nghiêm trọng hoặc cảnh báo chất lượng chưa được xử lý.
- Hợp đồng, tài liệu hoặc cấu hình liên quan đã được cập nhật.
- Rủi ro bảo mật và dữ liệu đã được xem xét.
- Các bước triển khai, giám sát và rollback đã rõ nếu thay đổi cần phát hành.
- Không còn công việc bắt buộc chưa được hoàn tất hoặc được chấp nhận ngoại lệ rõ ràng.

Đây là ví dụ khởi đầu, không phải danh sách bắt buộc giống nhau cho mọi đội. Một nhóm làm thư viện Java, một nhóm phát triển dịch vụ thanh toán và một nhóm xây công cụ nội bộ có thể cần những tiêu chí khác nhau.

Điểm cốt lõi là DoD phải được **những người cùng chịu trách nhiệm về sản phẩm và chất lượng hiểu giống nhau**. Nếu developer nghĩ “đã code xong” là done, QA nghĩ “đã test thủ công” mới done, còn vận hành nghĩ “đã có rollback” mới done, nhóm đang dùng nhiều định nghĩa khác nhau.

### DoD không phải khẩu hiệu

Một câu như “Code phải tốt, dễ bảo trì và không có bug” thể hiện mong muốn nhưng không giúp quyết định một PR cụ thể đã đạt hay chưa.

Một tiêu chí có thể kiểm chứng hơn:

- “Các unit test liên quan chạy qua trong CI.”
- “Thay đổi API có contract test hoặc bằng chứng tương thích với consumer hiện tại.”
- “Không còn lỗi mức blocker/high được phát hiện bởi bộ kiểm tra bảo mật đã thống nhất, hoặc có ngoại lệ được chủ sở hữu chấp nhận.”
- “Nếu migration không tương thích ngược, PR phải nêu trình tự triển khai và rollback.”

DoD cần chuyển từ **ý định chất lượng** sang **điều kiện có thể xác nhận**.

## 2. Phân biệt DoD, acceptance criteria và Definition of Ready

Ba khái niệm này liên quan nhưng trả lời những câu hỏi khác nhau.

| Khái niệm | Câu hỏi | Phạm vi |
| --- | --- | --- |
| **Acceptance criteria** | Tính năng hoặc bugfix này phải làm gì để được chấp nhận? | Một yêu cầu cụ thể |
| **Definition of Done (DoD)** | Mọi thay đổi cần đáp ứng chuẩn chất lượng nào để được coi là hoàn tất? | Thỏa thuận chung của nhóm/sản phẩm |
| **Definition of Ready (DoR)** | Một công việc đã đủ rõ để bắt đầu chưa? | Điều kiện trước khi thực hiện |
| **Task complete** | Người được giao đã hoàn thành phần việc của mình chưa? | Một nhiệm vụ hoặc cá nhân |
| **Release criteria** | Phiên bản có đủ điều kiện phát hành không? | Một lần phát hành hoặc rollout |

Ví dụ yêu cầu: “Đơn hàng từ 500.000 VND được miễn phí giao hàng.”

**Acceptance criteria:**

- Đơn có tổng 499.999 VND phải trả phí chuẩn.
- Đơn có tổng đúng 500.000 VND được miễn phí.
- Khách VIP vẫn được miễn phí dưới ngưỡng.
- Phép tính không chấp nhận tổng tiền tràn số.

**DoD của nhóm:**

- Hành vi mới có test cho các trường hợp biên.
- Code được review và CI đạt.
- Tài liệu chính sách giá được cập nhật nếu tài liệu đó là nguồn hướng dẫn.
- Không làm lộ dữ liệu nhạy cảm trong log.
- Thay đổi có thể triển khai theo quy trình của dịch vụ.

**DoR:**

- Đơn vị tiền và cách tính tổng đã được xác nhận.
- Quy tắc VIP và ngưỡng được chủ sở hữu nghiệp vụ làm rõ.
- Có thể xác định module và test liên quan.

Acceptance criteria nói **kết quả nghiệp vụ cụ thể**. DoD nói **chuẩn chất lượng áp dụng chung**. DoR giúp tránh bắt đầu một công việc khi còn thiếu thông tin thiết yếu.

### Một yêu cầu có thể đạt acceptance criteria nhưng chưa đạt DoD

Code có thể tính đúng ngưỡng trong unit test, nhưng nếu API contract bị phá, migration không an toàn hoặc không có review theo quy trình, thay đổi vẫn chưa hoàn tất theo DoD.

Ngược lại, một PR có thể đạt mọi quality gate chung nhưng vẫn không đáp ứng acceptance criteria vì tính sai quy tắc nghiệp vụ. Cả hai lớp điều kiện đều cần thiết.

## 3. Vì sao nhóm cần thống nhất trước?

Khi DoD chỉ tồn tại trong suy nghĩ từng người, mỗi lần review trở thành một cuộc thương lượng mới:

- Reviewer A yêu cầu test tích hợp; reviewer B cho rằng unit test là đủ.
- Developer nghĩ cập nhật README không nằm trong ticket; người dùng lại phụ thuộc vào tài liệu đó.
- Nhóm sản phẩm tưởng tính năng đã phát hành; vận hành chưa có dashboard hoặc hướng dẫn xử lý lỗi.
- Một bugfix được merge dù chưa xác nhận trường hợp biên vì không ai nghĩ đó là điều kiện bắt buộc.

Thỏa thuận chung giúp:

1. **Giảm bất đồng lặp lại:** không phải tranh luận từ đầu về tiêu chuẩn cơ bản ở mỗi PR.
2. **Làm rõ trách nhiệm:** biết ai cung cấp bằng chứng, ai review và ai chấp nhận ngoại lệ.
3. **Tăng khả năng dự đoán:** kế hoạch có thể tính đến test, tài liệu và rollout.
4. **Phát hiện thiếu sót sớm:** tác giả biết yêu cầu cần hoàn thành trước khi mở PR.
5. **Bảo vệ chất lượng dài hạn:** tiêu chuẩn không phụ thuộc reviewer cụ thể.
6. **Học từ sự cố:** lỗi lọt qua có thể dẫn tới cải tiến DoD và quy trình kiểm tra.

DoD không thay thế phán đoán chuyên môn. Nó tạo một **mức nền chung**, còn reviewer và chủ sở hữu vẫn phải xem xét rủi ro cụ thể.

## 4. Một DoD tốt cần có đặc điểm gì?

Một tiêu chí hữu ích thường có những đặc điểm sau:

### Rõ nghĩa

Người viết và người kiểm tra hiểu cùng một điều. Tránh từ như “đủ tốt”, “tối ưu”, “đẹp” nếu không có tiêu chuẩn cụ thể.

### Có thể kiểm chứng

Có thể xác nhận qua test, CI, review, tài liệu, cấu hình hoặc bằng chứng khác. Nếu tiêu chí đòi hỏi đánh giá thủ công, cần nêu ai đánh giá và xem điều gì.

### Phù hợp với rủi ro

Thay đổi một chuỗi hiển thị không cần quy trình kiểm tra giống thay đổi quyền truy cập hoặc transaction thanh toán. DoD có thể có tiêu chí chung và tiêu chí bổ sung theo loại thay đổi.

### Đủ ngắn để sử dụng

Một danh sách quá dài dễ bị đọc lướt hoặc đánh dấu máy móc. Chỉ giữ điều kiện có giá trị thực; chi tiết hướng dẫn có thể nằm trong tài liệu quy trình liên kết.

### Áp dụng nhất quán

Tiêu chí phải được sử dụng trong công việc thực tế, không chỉ xuất hiện trong template. Nếu nhóm thường xuyên bỏ qua một mục, cần hiểu nguyên nhân và sửa cách làm.

### Có thể cải tiến

DoD không phải hợp đồng bất biến. Khi công nghệ, kiến trúc, rủi ro hoặc năng lực nhóm thay đổi, tiêu chí cũng cần được xem xét.

## 5. Các nhóm tiêu chí thường gặp

Một DoD cho thay đổi phần mềm có thể được xây quanh các nhóm sau:

| Nhóm | Điều cần xác nhận | Bằng chứng có thể dùng |
| --- | --- | --- |
| **Mục tiêu và hành vi** | Yêu cầu và acceptance criteria được đáp ứng | Test, demo, kiểm tra nghiệp vụ |
| **Code và thiết kế** | Thay đổi phù hợp quy ước, có cấu trúc dễ hiểu | Review, formatter, static analysis |
| **Kiểm thử** | Mức test phù hợp với rủi ro đã chạy | Kết quả CI, test report |
| **Bảo mật và dữ liệu** | Quyền, input, secret và dữ liệu được xử lý đúng | Security checks, review, test |
| **Tài liệu và hợp đồng** | Nội dung mà consumer/người dùng phụ thuộc được cập nhật | API spec, README, migration notes |
| **Vận hành** | Có quan sát và xử lý lỗi phù hợp | Logs, metrics, traces, alert |
| **Triển khai** | Cách phát hành và rollback đã rõ khi cần | Release plan, migration/rollback procedure |
| **Review và trách nhiệm** | Các bên cần thiết đã xem xét và vấn đề blocker được giải quyết | Approval, issue resolution, sign-off |

Không phải mọi thay đổi đều cần đủ mọi loại bằng chứng. DoD nên chỉ rõ tiêu chí nào luôn áp dụng và tiêu chí nào kích hoạt theo loại/rủi ro thay đổi.

## 6. Biến tiêu chí mơ hồ thành điều kiện quan sát được

Xét một số ví dụ:

| Tiêu chí mơ hồ | Tiêu chí có thể kiểm chứng hơn |
| --- | --- |
| Code phải sạch | Formatter và linter của repository đạt; phần logic mới có tên và ranh giới được review |
| Phải có test đầy đủ | Test cho acceptance criteria và nhánh rủi ro đã xác định được thêm/chạy |
| Không được có lỗi | Không còn defect blocker/high đã biết chưa có quyết định xử lý |
| Tài liệu phải tốt | API hoặc hướng dẫn bị ảnh hưởng được cập nhật, hoặc ghi rõ không thay đổi contract |
| Hiệu năng phải ổn | Đường chạy ảnh hưởng có benchmark/metric so với ngưỡng đã thống nhất |
| Bảo mật phải an toàn | Các kiểm tra bảo mật phù hợp với bề mặt thay đổi đã hoàn tất và finding quan trọng được xử lý |
| Sẵn sàng deploy | Migration, cấu hình, feature flag, rollout và rollback được xem xét khi có liên quan |

Một tiêu chí không nhất thiết phải có con số. “Reviewer xác nhận transaction boundary không bị thay đổi” là điều kiện định tính nhưng vẫn có thể kiểm tra qua code và bằng chứng. Điều quan trọng là người thực hiện biết phải xem gì.

### Tránh dùng coverage làm đại diện cho chất lượng

“Coverage đạt 80%” có thể là một quality gate của dự án, nhưng không chứng minh test kiểm tra đúng hành vi. Một test có thể chạy qua dòng code mà không assert kết quả quan trọng.

DoD nên ưu tiên **test bảo vệ yêu cầu và rủi ro**. Coverage là một tín hiệu bổ sung, cần đọc cùng branch coverage, assertion, mutation testing hoặc review test khi phù hợp.

## 7. Ví dụ Java: áp dụng DoD cho một thay đổi tính phí

Yêu cầu: đơn hàng từ 500.000 VND trở lên được miễn phí giao hàng; khách VIP được miễn phí ở mọi mức. Phí chuẩn là 25.000 VND.

Một policy đơn giản:

```java
final class ShippingFeePolicy {
    private static final long FREE_THRESHOLD_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 25_000L;

    long calculate(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0L) {
            throw new IllegalArgumentException("Subtotal must not be negative");
        }

        if (vip || subtotalVnd >= FREE_THRESHOLD_VND) {
            return 0L;
        }

        return STANDARD_FEE_VND;
    }
}
```

Test cho hành vi và biên:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ShippingFeePolicyTest {
    private final ShippingFeePolicy policy = new ShippingFeePolicy();

    @Test
    void chargesStandardFeeBelowThreshold() {
        assertEquals(25_000L, policy.calculate(499_999L, false));
    }

    @Test
    void waivesFeeAtExactThreshold() {
        assertEquals(0L, policy.calculate(500_000L, false));
    }

    @Test
    void waivesFeeAboveThreshold() {
        assertEquals(0L, policy.calculate(500_001L, false));
    }

    @Test
    void vipReceivesFreeShippingBelowThreshold() {
        assertEquals(0L, policy.calculate(100_000L, true));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.calculate(-1L, false));
    }
}
```

Ví dụ này minh họa một thay đổi nhỏ, nhưng DoD vẫn cần xem toàn bộ bối cảnh. Nếu policy được dùng bởi nhiều consumer, cần xác minh tất cả điểm gọi. Nếu phí được lưu trong hóa đơn, cần kiểm tra cách dữ liệu lịch sử được giữ. Nếu API công khai thay đổi, cần cập nhật contract và consumer.

### Ánh xạ DoD vào thay đổi này

| Tiêu chí | Cách xác nhận |
| --- | --- |
| Acceptance criteria đúng | Test dưới ngưỡng, đúng ngưỡng, trên ngưỡng và VIP |
| Input hợp lệ | Test giá trị âm |
| Code theo chuẩn dự án | Formatter/linter và review |
| Tích hợp đúng | Test ở service hoặc consumer liên quan |
| Không phá hợp đồng | Kiểm tra API/schema nếu có ảnh hưởng |
| Có thể vận hành | Theo dõi lỗi tính phí nếu đây là đường chạy quan trọng |
| Review hoàn tất | Người review xác nhận logic và rủi ro |

Không phải tất cả hạng mục đều tạo thêm test riêng. Một tiêu chí có thể được xác nhận bằng code review, CI hoặc bằng chứng vận hành.

## 8. Chọn mức kiểm thử theo rủi ro của thay đổi

Một DoD hữu ích không yêu cầu mọi PR chạy mọi loại test. Nó xác định **mức kiểm thử tối thiểu tương ứng với tác động**.

### Unit test

Phù hợp với quy tắc thuần túy, tính toán, validation và chuyển trạng thái có thể kiểm tra độc lập.

Ví dụ: chính sách phí, quy tắc giới hạn, mapping enum.

### Integration test

Cần khi thay đổi tương tác với database, transaction manager, filesystem, message broker hoặc adapter.

Ví dụ: repository lưu đúng trạng thái, migration tạo constraint, outbox ghi event cùng transaction.

### Contract test

Hữu ích khi thay đổi ảnh hưởng producer/consumer, API hoặc message schema.

Ví dụ: trường JSON mới có giữ tương thích với client cũ không?

### End-to-end test

Dùng cho một số hành trình quan trọng xuyên nhiều thành phần. E2E có thể tốn thời gian và dễ không ổn định; không nên biến mọi quy tắc nhỏ thành test E2E.

### Kiểm thử phi chức năng

Khi thay đổi ảnh hưởng hiệu năng, bảo mật, khả năng chịu tải hoặc độ tin cậy, cần bằng chứng phù hợp như benchmark, security test, load test hoặc fault injection.

DoD có thể ghi: “Test phù hợp với rủi ro của thay đổi đã chạy; thay đổi ở ranh giới dữ liệu hoặc tích hợp ngoài phải có bằng chứng ở mức integration/contract tương ứng.” Cách này có ý nghĩa hơn yêu cầu “mọi PR phải có đủ bốn loại test”.

## 9. Review code là một phần của DoD

Review không chỉ xác nhận cú pháp hoặc phong cách. Người review cần xem:

- Logic có đáp ứng yêu cầu và xử lý đúng biên không?
- Tên, cấu trúc và abstraction có giúp người bảo trì hiểu không?
- Có thay đổi side effect, transaction, concurrency hoặc error handling không?
- Test có kiểm tra kết quả và tình huống rủi ro không?
- Có lộ secret, dữ liệu cá nhân hoặc thông tin nội bộ trong log không?
- API, schema, config và tài liệu có nhất quán không?
- Phạm vi PR có đủ tập trung để đánh giá không?

DoD nên nêu rõ quy tắc review của nhóm, chẳng hạn cần ít nhất một approval từ người có quyền review, hoặc cần chuyên gia phụ trách khi thay đổi vùng nhạy cảm. Tránh tự đặt một số lượng approval phổ quát; quy định cần theo chính sách repository và mức rủi ro.

### Approval không thay thế trách nhiệm của tác giả

Người review có thể bỏ sót vấn đề. Tác giả vẫn chịu trách nhiệm kiểm tra diff, chạy test, cung cấp bối cảnh và phản hồi nhận xét. Nhóm cùng chịu trách nhiệm về chất lượng; không nên coi một dấu approve là bằng chứng duy nhất rằng mọi rủi ro đã được xử lý.

## 10. Bảo mật và quyền riêng tư trong tiêu chí hoàn thành

Thay đổi liên quan tới xác thực, phân quyền, input, dữ liệu cá nhân, secret hoặc giao tiếp ngoài cần được xem xét theo bề mặt rủi ro.

Một số câu hỏi:

- Endpoint mới có kiểm tra quyền ở phía server không?
- Dữ liệu từ người dùng có được validate ở ranh giới tin cậy không?
- Log có ghi token, mật khẩu, thông tin thanh toán hoặc dữ liệu cá nhân không?
- Secret có được lưu trong source hoặc file cấu hình commit không?
- Có thay đổi dependency với cảnh báo bảo mật quan trọng không?
- Lỗi có tiết lộ stack trace hoặc thông tin nội bộ cho client không?
- Dữ liệu được lưu và xóa theo chính sách hiện hành không?

DoD không nên ghi chung “đã bảo mật” rồi đánh dấu xong. Có thể quy định: “Thay đổi có ảnh hưởng tới authentication, authorization, dữ liệu nhạy cảm hoặc input bên ngoài phải có security review/check phù hợp và không còn finding nghiêm trọng chưa được xử lý hoặc chấp nhận ngoại lệ.”

Một thay đổi CSS nhỏ không cần cùng mức security review như thay đổi kiểm tra quyền truy cập. Điều kiện kích hoạt phải rõ để nhóm áp dụng đúng.

## 11. Tài liệu và hợp đồng cũng là một phần của kết quả

Tài liệu cần cập nhật khi thay đổi làm người khác phải hiểu một hợp đồng hoặc quy trình khác đi.

Ví dụ:

- API thay field, status code hoặc semantics.
- Message schema thêm thuộc tính bắt buộc.
- Cấu hình mới cần giá trị mặc định và hướng dẫn triển khai.
- Quy tắc nghiệp vụ thay đổi cần được giải thích cho người sử dụng.
- Quy trình vận hành hoặc khôi phục có bước mới.
- Một public method hoặc library behavior thay đổi.

Không phải mọi refactor nội bộ đều cần sửa README. DoD có thể dùng tiêu chí: **“Tài liệu, API spec và hướng dẫn vận hành bị ảnh hưởng đã được cập nhật; nếu không ảnh hưởng, không cần thay đổi tài liệu.”**

Tài liệu lỗi thời cũng là một dạng rủi ro: người dùng có thể tích hợp sai, người vận hành có thể xử lý nhầm hoặc developer mới có thể dựa vào contract không còn đúng.

## 12. Khả năng quan sát và vận hành

Một thay đổi có thể chạy đúng trong test nhưng khó phát hiện khi lỗi ở môi trường thật. Với đường chạy quan trọng, DoD nên xem xét:

- Log có đủ ngữ cảnh để điều tra nhưng không chứa dữ liệu nhạy cảm?
- Metric có thể nhận biết lỗi, timeout, retry hoặc trạng thái bị kẹt?
- Trace có thể liên kết các bước qua service khi cần?
- Alert có chủ sở hữu và ngưỡng hành động rõ?
- Dashboard hiện tại có cần cập nhật?
- Có hướng dẫn xử lý hoặc runbook nếu hành vi vận hành thay đổi?

Ví dụ khi thêm retry cho thanh toán, cần biết số lần retry, kết quả cuối, số giao dịch đang chờ đối soát và cách nhận diện duplicate. Chỉ thêm vòng lặp retry mà không có metric có thể làm sự cố khó phát hiện hơn.

Với thay đổi chỉ sửa typo trong thông báo, việc thêm dashboard mới không có ý nghĩa. Tiêu chí observability nên được kích hoạt theo mức tác động.

## 13. Migration, tương thích và rollout

Khi thay đổi schema hoặc contract, “code đã merge” chưa đủ để gọi toàn bộ công việc hoàn tất.

Hãy xác định:

- Migration có chạy trên dữ liệu hiện có không?
- Có lock hoặc thời gian downtime đáng kể không?
- Ứng dụng cũ và mới có thể cùng chạy trong giai đoạn rollout không?
- Có consumer ngoài nào chưa được cập nhật?
- Rollback có an toàn với dữ liệu đã ghi theo schema mới không?
- Cần backfill hoặc đối soát dữ liệu không?
- Có feature flag hoặc giai đoạn canary không?

Một số thay đổi dùng chiến lược expand–migrate–contract:

```text
Expand:
  Thêm cấu trúc mới nhưng vẫn giữ tương thích.

Migrate:
  Đồng bộ hoặc chuyển dữ liệu, kiểm tra kết quả.

Switch:
  Chuyển ứng dụng/consumer sang cách mới và quan sát.

Contract:
  Xóa cấu trúc cũ sau khi xác nhận không còn consumer.
```

DoD cho một giai đoạn có thể yêu cầu “trạng thái tương thích của giai đoạn này được kiểm tra và rollout plan được ghi rõ”. Không cần xóa cấu trúc cũ trong cùng PR nếu nó phải tồn tại cho tới khi tất cả consumer chuyển đổi.

### Phân biệt hoàn thành code với hoàn thành rollout

Một PR có thể đạt DoD để merge nhưng chưa đồng nghĩa tính năng đã được bật cho tất cả người dùng. Nhóm cần phân biệt:

- **Code complete:** thay đổi đã được xây dựng, kiểm tra và review theo DoD.
- **Ready to release:** đủ điều kiện phát hành theo tiêu chí release.
- **Released:** đã triển khai theo kế hoạch.
- **Enabled/available:** chức năng đã được bật và có thể sử dụng.
- **Verified in production:** đã quan sát kết quả sau triển khai theo tiêu chí đã đặt.

Tên trạng thái có thể khác giữa tổ chức, nhưng cần tránh dùng chung từ “done” cho tất cả.

## 14. Trách nhiệm của từng vai trò

DoD là thỏa thuận của nhóm, nhưng mỗi vai trò đóng góp bằng chứng khác nhau.

| Vai trò | Trách nhiệm thường gặp |
| --- | --- |
| **Tác giả/developer** | Hiểu yêu cầu, triển khai, tự đọc diff, thêm test, cập nhật tài liệu và cung cấp kết quả kiểm tra |
| **Reviewer** | Đánh giá logic, thiết kế, rủi ro, test và tuân thủ quy ước |
| **Product owner/người phụ trách nghiệp vụ** | Làm rõ acceptance criteria, xác nhận kết quả nghiệp vụ khi cần |
| **QA/test engineer** | Hỗ trợ chiến lược kiểm thử, dữ liệu và các tình huống rủi ro |
| **Security specialist** | Đánh giá thay đổi có bề mặt bảo mật quan trọng |
| **Operations/SRE** | Xem xét khả năng triển khai, giám sát, khôi phục và runbook |
| **Cả nhóm** | Duy trì DoD, xử lý ngoại lệ và cải tiến dựa trên sự cố |

Không phải mọi PR cần tất cả vai trò tham gia trực tiếp. DoD cần nói rõ **khi nào cần người có chuyên môn tương ứng**, ví dụ thay đổi authorization cần security review theo quy trình của nhóm.

### Trách nhiệm không nên bị đẩy hết sang QA

Developer cần tự kiểm tra code và test trước khi giao. QA giúp phát hiện rủi ro và xác minh hành vi, nhưng không phải “cửa cuối” chịu trách nhiệm duy nhất cho chất lượng. Reviewer cũng không thể thay thế kiểm thử tự động hoặc xác nhận nghiệp vụ.

Chất lượng là kết quả của cách nhóm làm việc cùng nhau, không phải một công đoạn được chuyển giao ở cuối.

## 15. Đưa DoD vào CI và công cụ mà không biến thành thủ tục

Những tiêu chí có thể tự động hóa nên được thực thi gần nơi thay đổi được tạo:

- Compile/build.
- Unit và integration test phù hợp.
- Formatter/linter.
- Static analysis.
- Dependency/security scan.
- Kiểm tra schema/API compatibility khi có công cụ phù hợp.
- Coverage hoặc mutation threshold nếu nhóm đã định nghĩa cách dùng.
- Kiểm tra migration hoặc generated files.

Một pipeline khái quát:

```text
Developer tạo thay đổi
        |
        v
Tự kiểm tra và mở PR
        |
        v
CI: build + test + static checks
        |
        v
Review và xác nhận các tiêu chí thủ công
        |
        v
Merge khi blocker đã được giải quyết
        |
        v
Release/rollout theo điều kiện riêng
        |
        v
Quan sát kết quả khi cần
```

CI nên báo lỗi cụ thể và chỉ cách khắc phục. Một quality gate chỉ trả “pipeline failed” mà không chỉ ra test hoặc rule nào lỗi sẽ khiến DoD trở thành trải nghiệm gây khó chịu.

### Không tự động hóa mọi tiêu chí

Có những điều cần đánh giá bằng con người:

- Tên và mô hình có diễn đạt đúng nghiệp vụ không?
- Abstraction có cần thiết không?
- Test có assert điều quan trọng không?
- Rollback có thực sự an toàn với dữ liệu đã ghi không?
- Hướng dẫn vận hành có giúp người trực xử lý sự cố không?

Dùng automation cho điều có thể kiểm tra lặp lại; giữ review chuyên môn cho quyết định cần ngữ cảnh.

## 16. Ngoại lệ: khi nào có thể chấp nhận và phải ghi gì?

Đôi khi một tiêu chí chưa thể đáp ứng ngay: integration environment đang lỗi, test legacy không ổn định, dependency scan phát hiện finding chưa thể nâng hoặc migration phải đợi cửa sổ triển khai.

Ngoại lệ không nên là một ô được đánh dấu “N/A” không lời giải thích. Một ngoại lệ có kiểm soát cần nêu:

1. **Tiêu chí nào chưa đạt?**
2. **Vì sao chưa thể đáp ứng?**
3. **Rủi ro thực tế là gì?**
4. **Biện pháp giảm thiểu tạm thời nào đang áp dụng?**
5. **Ai có thẩm quyền chấp nhận?**
6. **Khi nào và bằng điều kiện nào sẽ xử lý tiếp?**

Ví dụ:

```text
Ngoại lệ:
  Integration test với payment sandbox chưa chạy được.

Lý do:
  Môi trường sandbox đang gián đoạn ngoài phạm vi nhóm.

Bằng chứng thay thế:
  Unit test policy, contract test với fixture đã xác nhận,
  và test adapter giả lập timeout.

Rủi ro còn lại:
  Chưa xác minh tương tác thực với sandbox ở phiên bản API hiện tại.

Người chấp nhận:
  Chủ sở hữu dịch vụ theo quy trình của nhóm.

Hành động tiếp:
  Chạy integration test khi sandbox phục hồi trước rollout đầy đủ.
```

Ví dụ này không tự khẳng định có thể phát hành. Nếu thay đổi ảnh hưởng thanh toán thật, người có thẩm quyền phải quyết định rủi ro có thể chấp nhận hay phải chặn rollout.

**Ngoại lệ không được dùng để hợp thức hóa việc bỏ qua một yêu cầu an toàn quan trọng mà không có quyết định và kiểm soát phù hợp.** Nếu rủi ro không thể chấp nhận, thay đổi chưa đạt điều kiện hoàn thành.

## 17. DoD khác nhau theo loại thay đổi

Một bộ tiêu chí chung cần có phần áp dụng cho mọi thay đổi và phần kích hoạt theo loại công việc.

| Loại thay đổi | Tiêu chí bổ sung thường cần |
| --- | --- |
| **Bugfix** | Test tái hiện lỗi, xác nhận kết quả mong đợi, kiểm tra hồi quy liên quan |
| **Refactor** | Bằng chứng hành vi được giữ, test hiện có chạy, không trộn thay đổi chức năng ngoài mục tiêu |
| **API/contract** | Tương thích consumer, tài liệu spec, versioning/deprecation nếu cần |
| **Database migration** | Migration test, dữ liệu cũ, transaction/lock, rollout và rollback |
| **Security change** | Threat/risk review, authorization/input tests, scan và kiểm tra dữ liệu nhạy cảm |
| **Performance change** | Baseline và phép đo sau thay đổi trong workload phù hợp |
| **Dependency update** | Compatibility, security/license review khi cần, test đường dùng |
| **Configuration/feature flag** | Default, validation, quyền thay đổi, hành vi khi thiếu hoặc sai cấu hình |
| **Generated code** | Nguồn sinh, phiên bản generator và khả năng tái tạo |
| **Documentation-only** | Nội dung đúng, liên kết và ví dụ được kiểm tra theo phạm vi |

Không nên yêu cầu một bugfix nhỏ chạy load test toàn hệ thống nếu không ảnh hưởng hiệu năng. Nhưng nếu bugfix thay đổi query chính của dịch vụ có tải lớn, phép đo hoặc kiểm tra truy vấn có thể là điều kiện hợp lý.

## 18. Xây dựng DoD cùng nhóm

Một DoD chỉ có giá trị khi những người sử dụng nó hiểu và chấp nhận. Có thể tổ chức một buổi thống nhất ngắn:

### Bước 1 — Thu thập vấn đề từng gặp

Hỏi nhóm về lỗi lọt production, PR bị trả lại, migration gây sự cố, tài liệu lỗi thời hoặc công việc phải làm lại. Tập trung vào ví dụ thực tế thay vì bắt đầu từ danh sách tiêu chuẩn chung trên Internet.

### Bước 2 — Xác định chất lượng tối thiểu

Chọn các điều kiện cần cho hầu hết thay đổi: build/test, review, xử lý finding nghiêm trọng và cập nhật hợp đồng bị ảnh hưởng.

### Bước 3 — Xác định điều kiện theo rủi ro

Thêm các yêu cầu riêng cho bảo mật, dữ liệu, hiệu năng, migration, API hoặc rollout. Ghi rõ trigger nào khiến tiêu chí được áp dụng.

### Bước 4 — Chọn bằng chứng và người xác nhận

Với mỗi tiêu chí, ghi công cụ, test, tài liệu hoặc vai trò cần kiểm tra. Tránh tiêu chí không ai biết cách xác nhận.

### Bước 5 — Thử với các thay đổi gần đây

Lấy một bugfix, một refactor, một migration và một thay đổi API. Áp DoD dự thảo để xem có mục nào quá mơ hồ, thừa hoặc thiếu.

### Bước 6 — Công bố và dùng trong công việc

Đặt DoD ở nơi nhóm thường xem khi tạo PR hoặc hoàn thành ticket. Hướng dẫn cách xử lý ngoại lệ và ai có quyền chấp nhận.

### Bước 7 — Xem lại theo chu kỳ

Dựa trên dữ liệu CI, lỗi lọt, thời gian review, sự cố rollout và phản hồi của nhóm để cải tiến. Không nên thay đổi tiêu chí liên tục theo từng ý kiến cá nhân mà không có bằng chứng.

## 19. Mẫu Definition of Done có thể điều chỉnh

Mẫu dưới đây là điểm khởi đầu. Nhóm cần sửa để phù hợp với repository, mức rủi ro và cách phát hành thực tế.

```markdown
# Definition of Done — thay đổi phần mềm

## Mục tiêu và hành vi
- [ ] Acceptance criteria đã được đáp ứng.
- [ ] Hành vi biên và trường hợp lỗi quan trọng đã được xem xét.
- [ ] Thay đổi ngoài phạm vi đã được loại bỏ hoặc giải thích.

## Code và thiết kế
- [ ] Code tuân theo formatter/linter và quy ước repository.
- [ ] Tên, cấu trúc và abstraction đủ rõ để bảo trì.
- [ ] Không còn debug code, secret hoặc dữ liệu nhạy cảm ngoài ý muốn.

## Kiểm thử
- [ ] Unit test phù hợp đã được thêm/cập nhật và chạy.
- [ ] Integration/contract/E2E test được bổ sung khi rủi ro yêu cầu.
- [ ] CI và các quality gate bắt buộc đạt.
- [ ] Test thất bại hoặc flaky đã được điều tra, không che giấu.

## Review
- [ ] Diff và mô tả PR đủ rõ để đánh giá.
- [ ] Review bắt buộc đã hoàn tất.
- [ ] Blocker đã được giải quyết hoặc có quyết định ngoại lệ hợp lệ.

## Bảo mật và dữ liệu
- [ ] Quyền, input, secret và dữ liệu nhạy cảm đã được xem xét.
- [ ] Migration/schema/API compatibility đã được xác minh khi liên quan.

## Tài liệu và vận hành
- [ ] API spec, README hoặc hướng dẫn bị ảnh hưởng đã cập nhật.
- [ ] Log/metric/trace/alert được xem xét khi thay đổi đường chạy quan trọng.
- [ ] Rollout, feature flag và rollback đã được chuẩn bị khi cần.

## Ngoại lệ
- [ ] Mọi tiêu chí chưa đạt có lý do, rủi ro, người chấp nhận và hành động tiếp theo.
```

Không cần ép mọi mục thành checkbox cho mọi PR. Có thể chia thành:
- **Luôn áp dụng:** build, test phù hợp, review, diff rõ.
- **Kích hoạt theo thay đổi:** migration, security, API, performance, observability, rollout.
- **Ngoại lệ có kiểm soát:** tiêu chí chưa thể đáp ứng nhưng có quyết định được ghi lại.

Mẫu cần ngắn đủ để tác giả và reviewer sử dụng trong công việc hằng ngày.

## 20. Đánh giá DoD có đang giúp nhóm hay không

Một DoD tốt không được đánh giá bằng số lượng checkbox. Hãy quan sát kết quả:

- Lỗi do thiếu test hoặc thiếu review có giảm không?
- PR có ít lượt trả lại vì những điều kiện cơ bản bị bỏ sót không?
- Migration và rollout có ít bất ngờ hơn không?
- Tài liệu/API contract có cập nhật đúng lúc hơn không?
- Các ngoại lệ có chủ sở hữu và được xử lý sau đó không?
- CI phát hiện vấn đề đủ sớm và đưa ra thông báo hữu ích không?
- Nhóm có đang đánh dấu hoàn thành máy móc mà không xem bằng chứng không?

Không nên lấy “100% checkbox được tick” làm KPI cá nhân. Nó có thể khuyến khích đánh dấu cho xong. Chất lượng DoD thể hiện qua **khả năng giảm lỗi, làm rõ trách nhiệm và giúp thay đổi được bàn giao an toàn**.

### Khi DoD quá nặng

Nếu một sửa typo phải chờ security review, load test và sign-off vận hành dù không ảnh hưởng các vùng đó, DoD có thể đang quá rộng. Hãy phân loại tiêu chí theo trigger rủi ro.

### Khi DoD quá nhẹ

Nếu nhiều thay đổi được merge nhưng liên tục thiếu test, tài liệu hoặc migration, DoD có thể chưa phản ánh chi phí thực. Hãy xem các sự cố và bổ sung điều kiện có thể kiểm chứng.

### Khi một tiêu chí không thể đo trực tiếp

Một số mục như “thiết kế dễ hiểu” cần review định tính. Có thể hỗ trợ bằng câu hỏi cụ thể: trách nhiệm có rõ không, dữ liệu nào được sở hữu, side effect nằm ở đâu, test có thể cô lập hành vi không. Không cần biến mọi phẩm chất thành một con số giả chính xác.

## 21. Những sai lầm thường gặp

**“Done nghĩa là code đã viết xong.”** Code chỉ là một phần của kết quả. Test, review, tài liệu và khả năng vận hành có thể còn thiếu.

**“Acceptance criteria chính là DoD.”** Acceptance criteria gắn với một yêu cầu; DoD là chuẩn chất lượng chung áp dụng cho nhiều thay đổi.

**“Mọi PR phải có cùng một bộ test.”** Mức kiểm tra phải theo loại thay đổi và rủi ro.

**“Có approval nghĩa là chất lượng đã bảo đảm.”** Review có thể bỏ sót; cần test và quality gate phù hợp.

**“Coverage đạt ngưỡng là đủ.”** Coverage không chứng minh assertion đúng hoặc mọi hành vi quan trọng đã được xác minh.

**“Không còn bug đã biết nghĩa là không có rủi ro.”** Có thể còn giả thuyết, phụ thuộc hoặc vùng chưa quan sát; cần ghi rõ giới hạn.

**“Ngoại lệ chỉ cần ghi N/A.”** Ngoại lệ phải có lý do, rủi ro, người chấp nhận và hành động tiếp theo.

**“DoD phải càng dài càng tốt.”** Danh sách dài dễ bị bỏ qua; giữ điều kiện có giá trị và bằng chứng rõ.

**“DoD là việc của QA.”** Chất lượng thuộc trách nhiệm chung của nhóm; tác giả, reviewer, sản phẩm và vận hành đều đóng góp.

**“Merge là release.”** Merge, sẵn sàng phát hành, rollout và xác minh production là những trạng thái khác nhau.

**“Một lần thống nhất là đủ mãi mãi.”** Công nghệ, rủi ro và sản phẩm thay đổi; DoD cần được xem lại dựa trên bằng chứng.

**“Đạt checklist nghĩa là không cần phán đoán.”** Checklist hỗ trợ quyết định; các thay đổi có rủi ro đặc biệt vẫn cần đánh giá chuyên môn.

## 22. Bài tập tình huống

### Tình huống A — Bugfix đã qua unit test

Một bugfix sửa điều kiện hoàn tiền. Unit test mới chạy qua nhưng không có test integration với repository; nhóm phát hiện trạng thái hoàn tiền và audit record đôi khi lệch nhau.

Hãy xác định acceptance criteria và DoD cần bổ sung. Integration test nào giúp kiểm tra tính nhất quán? Vai trò nào cần xác nhận ranh giới transaction?

### Tình huống B — Refactor không đổi hành vi

Một PR tách `OrderPricingPolicy` khỏi `CheckoutService`. Tác giả nói “chỉ refactor” nên không cần cập nhật test.

Hãy xác định bằng chứng tối thiểu để cho thấy hành vi được giữ. DoD có cần yêu cầu test mới trong mọi refactor không? Nếu test hiện có không bảo vệ quy tắc quan trọng, nhóm nên làm gì?

### Tình huống C — API thay đổi nhưng tài liệu chưa cập nhật

Một endpoint đổi status code khi dữ liệu không hợp lệ. CI và unit test đều đạt, nhưng API spec vẫn ghi status code cũ.

Hãy giải thích vì sao thay đổi chưa hoàn thành theo DoD. Ai cần cập nhật hoặc xác nhận contract? Có cần contract test không?

### Tình huống D — Migration không rollback được

Một migration thêm cột mới và chuyển dữ liệu. Code mới chạy tốt, nhưng rollback phiên bản ứng dụng sẽ không đọc được dữ liệu sau migration.

Hãy xác định điều kiện rollout, tương thích ngược và rollback cần có trong DoD. Khi nào cần chia thành nhiều giai đoạn expand–migrate–contract?

### Tình huống E — Security scan có finding

PR thêm endpoint quản trị. CI phát hiện một dependency có lỗ hổng mức cao, nhưng chưa rõ dependency có nằm trên đường sử dụng hay không.

Hãy đề xuất cách phân loại finding, bằng chứng cần xem, người có thẩm quyền chấp nhận rủi ro và điều kiện để merge hoặc chặn rollout.

### Tình huống F — DoD có quá nhiều checkbox

Nhóm yêu cầu mọi thay đổi phải có unit, integration, E2E, load test, security sign-off, tài liệu và runbook. Một PR sửa typo phải chờ nhiều ngày.

Hãy phân loại tiêu chí luôn áp dụng và tiêu chí kích hoạt theo rủi ro. Đề xuất cách rút gọn mà vẫn giữ mức chất lượng cần thiết.

### Tình huống G — Mọi người tick checklist nhưng sự cố vẫn xảy ra

Dashboard cho thấy 100% PR có đủ checkbox. Tuy nhiên, lỗi do timeout, retry trùng và thiếu alert vẫn xảy ra.

Hãy phân tích vì sao tỷ lệ tick không phản ánh chất lượng. Đề xuất bằng chứng, metric hoặc câu hỏi review cần bổ sung và cách cập nhật DoD sau sự cố.

### Tình huống H — Ai quyết định ngoại lệ?

Một test tích hợp không chạy được do môi trường ngoài bị gián đoạn. Developer muốn merge; reviewer muốn chờ; product owner cần phát hành sớm.

Hãy xác định thông tin cần có, rủi ro còn lại, bằng chứng thay thế, người có thẩm quyền quyết định và hành động bắt buộc sau khi merge. Phân biệt quyết định merge với quyết định bật tính năng cho người dùng.

Với mỗi tình huống, trả lời theo chuỗi: **yêu cầu → acceptance criteria → tiêu chí DoD liên quan → bằng chứng → người xác nhận → ngoại lệ/rủi ro → trạng thái hoàn thành**.

## 23. Ghi nhớ

**Thống nhất tiêu chí hoàn thành của một thay đổi** giúp nhóm biết chính xác điều gì cần đúng trước khi gọi công việc là done.

- Acceptance criteria mô tả kết quả của một yêu cầu; DoD mô tả chuẩn chất lượng chung.
- DoD cần rõ nghĩa, kiểm chứng được, phù hợp rủi ro, đủ ngắn và được dùng nhất quán.
- Xem xét hành vi, code, test, review, bảo mật, dữ liệu, tài liệu, vận hành và triển khai theo phạm vi thích hợp.
- Tác giả chịu trách nhiệm cung cấp bằng chứng; reviewer và chuyên gia liên quan xác nhận các vùng cần thiết; chất lượng là trách nhiệm chung.
- Tự động hóa những điều kiểm tra lặp lại được, giữ đánh giá chuyên môn cho quyết định cần ngữ cảnh.
- Ngoại lệ phải nêu lý do, rủi ro, người chấp nhận và hành động tiếp theo.
- Phân biệt code complete, ready to release, released và verified in production.
- Xem lại DoD bằng dữ liệu sự cố, lỗi lọt, thời gian review và phản hồi của nhóm; không dùng checkbox làm thước đo thành tích.

Một thay đổi thực sự hoàn thành khi **kết quả đáp ứng yêu cầu, chất lượng đã được xác minh phù hợp với rủi ro và người tiếp nhận có đủ thông tin để duy trì hoặc vận hành nó**. DoD giúp cả nhóm cùng chịu trách nhiệm cho kết quả đó.
