# Property shrinking strategy — Chiến lược thu nhỏ phản ví dụ

Bài học thuộc chương **Property Testing** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Trọng tâm là thu nhỏ dữ liệu hoặc chuỗi thao tác làm lộ lỗi mà vẫn giữ được điều kiện cần để tái hiện hành vi lạm dụng: bỏ qua phê duyệt, thao tác sai quyền, hoàn tiền vượt giới hạn hoặc tạo tác động trùng.

Một property thất bại với đơn hàng gồm hàng trăm dòng, nhiều actor và vài chục request chưa phải kết quả dễ điều tra. Bạn cần biết phần nào thực sự cần thiết để lỗi xuất hiện. **Shrinking** giúp biến phản ví dụ lớn thành một tình huống nhỏ hơn, dễ hiểu, dễ tái hiện và có thể giữ lại làm regression test.

Sau bài học, bạn cần có thể:

- Phân biệt dữ liệu nhỏ hơn với phản ví dụ nhỏ hơn nhưng vẫn có ý nghĩa nghiệp vụ.
- Thiết kế generator để những quan hệ như cùng tenant, khác chủ sở hữu, vượt hạn mức và cùng idempotency key được giữ khi thu nhỏ.
- Thu nhỏ chuỗi thao tác mà không vô tình xóa tiền điều kiện hoặc đổi sang lỗi khác.
- Sử dụng Java/jqwik để biểu diễn dữ liệu phụ thuộc bằng cấu trúc có thể thu nhỏ.
- Kiểm soát tính xác định, ngân sách thực thi và khả năng quan sát tác động.
- Chuyển phản ví dụ thành bằng chứng tái hiện và regression test.

## 1. Shrinking giải quyết vấn đề gì?

### 1.1. Từ một ca thất bại lớn đến nguyên nhân dễ thấy

Giả sử property phát hiện một yêu cầu hoàn tiền được chấp nhận dù vượt số còn lại:

```text
Đã thu:             950
Đã hoàn trước đó:   600
Yêu cầu hoàn mới:   400
Số còn lại:         350

Kỳ vọng: từ chối vì 400 > 350.
Thực tế: chấp nhận.
```

Dữ liệu nhỏ hơn có thể là:

```text
Đã thu:             2
Đã hoàn trước đó:   1
Yêu cầu hoàn mới:   2
Số còn lại:         1

Kỳ vọng: từ chối vì 2 > 1.
Thực tế: chấp nhận.
```

Phản ví dụ nhỏ cho thấy rõ một khả năng: implementation đang so yêu cầu mới với tổng đã thu, thay vì số còn lại sau các lần hoàn trước.

Con số trong bài là đơn vị tiền nhỏ nhất của miền minh họa. Việc thu nhỏ số tiền giúp giải thích lỗi; mức thiệt hại thực tế vẫn phải đánh giá bằng ngữ cảnh và ca gốc.

### 1.2. Thu nhỏ phải chạy lại property

Shrinking không chỉ là xóa bớt trường trong báo cáo. Với mỗi ứng viên đơn giản hơn, công cụ cần đánh giá lại liệu property còn thất bại hay không.

```text
Mẫu thất bại ban đầu
    → tạo ứng viên nhỏ hơn
    → dựng lại fixture
    → chạy lại hành vi và property
    → giữ ứng viên nếu vẫn tái hiện lỗi cần tìm
    → tiếp tục trong giới hạn đã đặt
```

Một ứng viên nhỏ hơn nhưng đã được xử lý đúng không thể thay thế phản ví dụ hiện có.

jqwik có cơ chế shrinking gắn với quá trình sinh dữ liệu và thử tìm mẫu nhỏ hơn vẫn làm property thất bại. Cấu trúc generator vì thế ảnh hưởng trực tiếp đến khả năng thu nhỏ. [jqwik User Guide: Result Shrinking](https://jqwik.net/docs/current/user-guide.html#result-shrinking).

### 1.3. Không mặc định kết quả là nhỏ nhất toàn cục

“Không còn tìm được ứng viên nhỏ hơn” phụ thuộc vào:

- Những phép thu nhỏ được generator hoặc reducer cung cấp.
- Thứ tự thử ứng viên.
- Cách đo mức độ đơn giản.
- Các ràng buộc của dữ liệu.
- Ngân sách thời gian và số lần chạy.
- Khả năng tái hiện của lỗi.

Một kết quả có thể chỉ nhỏ nhất theo tập phép biến đổi đã thử, hoặc là mẫu tốt nhất tìm được trước khi hết ngân sách. Không nên gọi nó là phản ví dụ nhỏ nhất toàn cục khi chưa có cơ sở.

## 2. Hợp đồng của một chiến lược shrinking

Gọi:

```text
D(x): fixture x có ý nghĩa trong phạm vi property
F(x): x tái hiện vi phạm nghiệp vụ cần điều tra
M(x): độ phức tạp của x
```

Một bước thu nhỏ được chấp nhận khi:

```text
D(candidate)
AND F(candidate)
AND M(candidate) < M(current)
```

### 2.1. Fixture hợp lệ không có nghĩa hành động phải được phép

Đây là điểm quan trọng trong kiểm thử bảo mật logic nghiệp vụ.

Một fixture có thể hợp lệ khi:

- Đơn hàng tồn tại, có dữ liệu nhất quán.
- Actor đã được xác thực.
- Báo giá được tạo từ nguồn tin cậy trong môi trường test.
- Yêu cầu đang cố phê duyệt sai quyền hoặc hoàn tiền quá số còn lại.

Hành động cố ý vi phạm quy tắc chính là điều cần thử. Nếu coi mọi request bị nghiệp vụ từ chối là “fixture không hợp lệ” rồi lọc bỏ, bộ kiểm thử sẽ mất các ca lạm dụng.

Ví dụ với hoàn tiền:

```text
Điều kiện nền:
  captured > 0
  0 ≤ alreadyRefunded ≤ captured
  requested > 0

Điều kiện tình huống đang thử:
  requested > captured - alreadyRefunded

Hợp đồng:
  yêu cầu phải bị từ chối và không tạo tác động hoàn tiền mới
```

Điều kiện cuối là hành vi bị cấm cần kiểm tra, không phải lý do để bỏ mẫu.

### 2.2. Giữ nguyên loại vi phạm đang điều tra

Nếu ca gốc làm lộ tự phê duyệt nhưng ứng viên nhỏ chỉ gây `NullPointerException`, cả hai đều có thể làm test đỏ. Tuy nhiên, ứng viên sau không còn giải thích lỗi bảo mật ban đầu.

Nên định danh lỗi bằng ý nghĩa nghiệp vụ:

```text
BR-SELF-APPROVAL: người tạo được tự duyệt
BR-OVER-REFUND: tổng hoàn có thể vượt tổng đã thu
BR-DUPLICATE-PAYMENT: cùng thao tác tạo tác động thanh toán thêm
BR-CROSS-TENANT: actor vượt phạm vi tenant
```

Không nên giả định framework tự giữ nguyên nguyên nhân nghiệp vụ trong mọi trường hợp. Hãy tách property theo bất biến đủ rõ, giữ quan hệ của tình huống bằng generator và ghi nhận kết quả thực tế.

Cũng không nên ràng buộc chữ ký lỗi vào mọi chi tiết như số thứ tự bước hoặc nguyên stack trace. Những chi tiết đó có thể đổi khi thu nhỏ dù vẫn là cùng một vi phạm.

### 2.3. Phân biệt lỗi mục tiêu với lỗi môi trường

Kết quả của một lần đánh giá ứng viên có thể thuộc nhiều nhóm:

| Nhóm kết quả | Ví dụ | Cách xử lý khi điều tra lỗi mục tiêu |
|---|---|---|
| Vi phạm mục tiêu | Hoàn tiền vượt số còn lại vẫn được chấp nhận | Có thể giữ làm phản ví dụ mới |
| Property được thỏa mãn | Yêu cầu vượt giới hạn bị từ chối đúng | Không thay phản ví dụ hiện có |
| Fixture không dựng được | Command tham chiếu đơn chưa được tạo | Loại ứng viên hoặc sửa cách sinh |
| Lỗi khác | Exception ngoài ý muốn trong mapper | Ghi nhận riêng, không giả là cùng lỗi |
| Chưa kết luận | Timeout dịch vụ ngoài, mất kết nối | Điều tra tính xác định; không coi là bằng chứng |

Không bắt mọi `Throwable` rồi trả về “không tái hiện”. Cách đó có thể che lỗi thật, lỗi assertion và lỗi của bộ kiểm thử. Một reducer tùy chỉnh cần phân loại kết quả tường minh; framework property testing vẫn phải báo các lỗi phát sinh theo cách quan sát được.

## 3. Chọn thước đo nhỏ hơn theo ý nghĩa miền

Với số nguyên đơn lẻ, nhỏ hơn thường gắn với độ lớn. Với nghiệp vụ, con số nhỏ nhất chưa chắc giữ được điều kiện gây lỗi.

Có thể dùng một thứ tự ưu tiên như:

```text
M(case) = (
  số command,
  số đối tượng,
  số actor,
  số trường tùy chọn,
  độ lớn dữ liệu số,
  độ dài chuỗi
)
```

Thứ tự từ trái sang phải thể hiện ưu tiên của chiến lược minh họa. Một miền khác có thể ưu tiên giảm số đối tượng trước số command.

Ví dụ:

- Với lỗi gửi trùng, giữ hai lần gửi nhưng bỏ các lệnh đọc không liên quan.
- Với lỗi tự duyệt, giữ quan hệ actor là người tạo nhưng giản lược định danh.
- Với lỗi tràn số, giữ vùng giá trị đủ lớn để tràn; thu về 0 có thể xóa lỗi.
- Với lỗi hết hạn, giữ quan hệ thời gian tại hoặc sau hạn, rồi giảm độ lệch.
- Với lỗi khác tenant, giảm số tenant xuống hai thay vì nhập chúng thành một.

Nếu tự viết reducer, phép “đơn giản hơn” cần một thứ tự không tạo vòng lặp. Bổ sung tập ứng viên đã thử và ngân sách hữu hạn để tránh đi qua lại giữa các biểu diễn tương đương.

## 4. Sinh dữ liệu theo quan hệ thay vì các trường độc lập

### 4.1. Vấn đề của generator độc lập rồi lọc mạnh

Một cách dễ nghĩ tới:

```text
sinh captured, refunded, requested độc lập
lọc:
  captured > 0
  0 ≤ refunded ≤ captured
  requested > captured - refunded
```

Không phải mọi cách lọc đều sai. Nhưng nếu các điều kiện hiếm, nhiều mẫu bị loại và nhiều ứng viên thu nhỏ không còn phù hợp. Tăng số lần thử không giải quyết được cấu trúc dữ liệu phụ thuộc.

Có thể biểu diễn tình huống bằng các thành phần độc lập có ý nghĩa hơn:

```text
refunded  ≥ 0
remaining ≥ 1
excess    ≥ 1

captured = refunded + remaining
requested = remaining + excess
```

Khi thu nhỏ các thành phần này rồi dựng lại đối tượng:

```text
captured - refunded = remaining
requested > remaining
```

Quan hệ vượt số còn lại được giữ theo cách xây dựng dữ liệu.

### 4.2. Thu nhỏ phần gốc và tính lại phần dẫn xuất

Nên coi các dữ liệu như tổng tiền, fingerprint hoặc version tham chiếu là những quan hệ cần quản lý, không phải các trường độc lập để sửa tùy ý.

| Tình huống | Phần có thể thu nhỏ | Quan hệ cần giữ hoặc tính lại |
|---|---|---|
| Hoàn quá số còn lại | Đã hoàn, còn lại, phần vượt | Tổng đã thu và yêu cầu mới |
| Tự duyệt | Định danh ngắn hơn | actorId = createdBy |
| Khác tenant | Tên tenant ngắn hơn | actorTenant khác orderTenant |
| Báo giá hết hạn | Độ lệch thời gian | now ≥ expiresAt |
| Retry cùng thao tác | Key và payload đơn giản hơn | Cùng phạm vi, cùng key, cùng ý nghĩa payload |
| Phê duyệt cũ | Chuỗi chỉnh sửa ngắn hơn | Version được duyệt khác version cần áp dụng |

Không “sửa” dữ liệu theo cách vô tình làm hành động trở nên hợp lệ. Ví dụ, với property kiểm tra báo giá sai version, việc luôn ghi lại quote version bằng order version sẽ xóa tình huống tấn công.

## 5. Ví dụ Java/jqwik: thu nhỏ lỗi hoàn tiền

Ví dụ dùng Java 17 trở lên, jqwik và JUnit Jupiter API cho assertion. Hàm `allowsRefund` **cố ý chứa lỗi** để minh họa: nó so yêu cầu với tổng đã thu, bỏ qua khoản đã hoàn trước đó.

Mọi số tiền là số nguyên theo đơn vị nhỏ nhất. Các giới hạn của generator giữ phép tính trong vùng an toàn của `long`; việc dùng `Math.addExact` còn giúp tránh âm thầm tràn số nếu sau này sửa giới hạn.

```java
import net.jqwik.api.Arbitraries;
import net.jqwik.api.Arbitrary;
import net.jqwik.api.Combinators;
import net.jqwik.api.ForAll;
import net.jqwik.api.Property;
import net.jqwik.api.Provide;
import net.jqwik.api.ShrinkingMode;

import static org.junit.jupiter.api.Assertions.assertFalse;

class RefundShrinkingProperties {
    record RefundCase(
            long captured,
            long alreadyRefunded,
            long requested) {}

    @Provide
    Arbitrary<RefundCase> overRefundCases() {
        Arbitrary<Long> refunded =
                Arbitraries.longs().between(0L, 1_000_000L);
        Arbitrary<Long> remaining =
                Arbitraries.longs().between(1L, 1_000_000L);
        Arbitrary<Long> excess =
                Arbitraries.longs().between(1L, 10_000L);

        return Combinators.combine(refunded, remaining, excess)
                .as((refundedValue, remainingValue, excessValue) ->
                        new RefundCase(
                                Math.addExact(refundedValue, remainingValue),
                                refundedValue,
                                Math.addExact(remainingValue, excessValue)));
    }

    @Property(tries = 400, shrinking = ShrinkingMode.BOUNDED)
    void rejectsEveryRequestAboveTheRemainingAmount(
            @ForAll("overRefundCases") RefundCase input) {
        assertFalse(
                allowsRefund(input),
                () -> "BR-OVER-REFUND: accepted " + input);
    }

    static boolean allowsRefund(RefundCase input) {
        if (input.captured() <= 0
                || input.alreadyRefunded() < 0
                || input.alreadyRefunded() > input.captured()
                || input.requested() <= 0) {
            return false;
        }

        // Cố ý sai: chưa trừ phần đã hoàn trước đó.
        return input.requested() <= input.captured();
    }
}
```

### 5.1. Vì sao generator hỗ trợ shrinking?

Ba đầu vào gốc đều có miền đơn giản. Khi công cụ thử giá trị nhỏ hơn, đối tượng `RefundCase` được dựng lại qua combinator, giữ các quan hệ đã thiết kế.

Không cần mutate một đối tượng sau khi sinh để “vá” các trường phụ thuộc. Generator cũng không gọi policy production để quyết định mẫu có thuộc tình huống vượt giới hạn hay không.

Một mẫu có `alreadyRefunded = 0` vẫn thuộc miền yêu cầu vượt số còn lại. Implementation lỗi ở ví dụ sẽ từ chối mẫu đó nếu requested lớn hơn captured, nên mẫu này có thể không làm property thất bại. Shrinking phải giữ **cả quan hệ tình huống và việc tái hiện lỗi**, không phải mọi mẫu từ generator đều là phản ví dụ.

### 5.2. Một quá trình giản lược về mặt nghiệp vụ

Có thể diễn giải các bộ thành phần như sau:

| Đã hoàn | Còn lại | Phần vượt | Đã thu | Yêu cầu | Kết quả của hàm lỗi |
|---:|---:|---:|---:|---:|---:|---|
| 600 | 350 | 50 | 950 | 400 | Chấp nhận sai |
| 50 | 350 | 50 | 400 | 400 | Chấp nhận sai |
| 50 | 1 | 50 | 51 | 51 | Chấp nhận sai |
| 1 | 1 | 1 | 2 | 2 | Chấp nhận sai |

Bảng là minh họa các mẫu vẫn làm lộ lỗi, không phải log chạy hoặc cam kết về thứ tự thu nhỏ của jqwik. Công cụ có thể thử nhiều ứng viên khác và dừng ở kết quả khác tùy cấu hình.

### 5.3. Sửa guard và giữ regression test

Với điều kiện nền đã được kiểm tra, guard đúng cho ví dụ là:

```java
return input.requested()
        <= input.captured() - input.alreadyRefunded();
```

Một ca hồi quy tường minh có thể thêm vào cùng lớp:

```java
@net.jqwik.api.Example
void previousRefundMustReduceTheAvailableAmount() {
    RefundCase input = new RefundCase(2L, 1L, 2L);

    assertFalse(
            allowsRefund(input),
            "Cannot refund 2 when only 1 remains");
}
```

Ca này sẽ thất bại với hàm cố ý sai và được kỳ vọng vượt qua sau khi sửa guard. Ví dụ đang mô tả cách xây dựng kiểm thử; không coi đoạn mã minh họa là báo cáo đã chạy trong một dự án cụ thể.

### 5.4. Không để property phủ định làm mất đường hợp lệ

Property trên chỉ bảo vệ tình huống yêu cầu vượt số còn lại. Một implementation luôn trả `false` sẽ vượt qua property này.

Bộ kiểm thử hoàn chỉnh cần property hoặc example khác cho yêu cầu hợp lệ, gồm đúng số còn lại, cùng các kiểm tra dữ liệu không hợp lệ. Đồng thời thêm nhóm riêng cho `remaining = 0`, vì generator ở đây cố ý chỉ xét miền còn ít nhất một đơn vị.

Shrinking cải thiện phản ví dụ của property đang xét; nó không thay thế việc thiết kế tập property đầy đủ.

## 6. Thu nhỏ dữ liệu phân quyền và quan hệ đối tượng

### 6.1. Giữ quan hệ định danh

Đối với lỗi tự duyệt:

```text
actor.id = order.createdBy
actor có quyền approver
actor.tenant = order.tenant
order đang chờ phê duyệt
```

Có thể thu nhỏ tên actor hoặc số đối tượng, nhưng phải giữ quan hệ bằng nhau của hai định danh. Nếu sinh hai chuỗi độc lập rồi hy vọng chúng trùng nhau, cả phát hiện lỗi lẫn shrinking đều kém hiệu quả.

Đối với lỗi khác tenant:

```text
actor.tenant ≠ order.tenant
actor có vai trò cần thiết
các điều kiện khác đều hợp lệ
```

Nếu cả hai tenant bị thu nhỏ thành cùng một chuỗi, mẫu không còn kiểm tra vượt phạm vi tenant.

Một cách biểu diễn fixture:

```text
TenantRole = SAME_TENANT | OTHER_TENANT
Ownership  = CREATOR | DIFFERENT_USER
Permission = APPROVER | NO_APPROVAL_PERMISSION
```

Từ các vai trò quan hệ đó, factory test tạo principal và đối tượng thật. Khi giản lược định danh, giữ nguyên vai trò quan hệ đang cần thử.

### 6.2. Không biến principal tin cậy thành dữ liệu client tùy ý

Actor của kiểm thử phải đi qua cơ chế dựng ngữ cảnh xác thực phù hợp với lớp đang test. Không đổi role trong body HTTP rồi kết luận đã kiểm thử phân quyền phía máy chủ.

Nếu request chứa token hoặc dữ liệu ký, thay đổi payload có thể làm chữ ký không còn hợp lệ và khiến yêu cầu bị chặn trước logic nghiệp vụ. Muốn thu nhỏ một ca đã xác thực:

- Sinh danh tính và thuộc tính qua fixture của môi trường test.
- Tạo lại chứng cứ xác thực bằng cơ chế test được kiểm soát khi cần.
- Giữ trường client được phép sửa là dữ liệu không tin cậy.
- Xác nhận yêu cầu vẫn đi đến đúng lớp cần khảo sát.

Tên kiểu dữ liệu hoặc factory không tự chứng minh độ tin cậy. Nguồn tạo và ranh giới xác thực mới quyết định phần đó.

### 6.3. Giữ các guard không phải mục tiêu ở trạng thái hợp lệ

Nếu đang điều tra tự duyệt, giữ tenant, trạng thái và giá hợp lệ. Nếu đang điều tra khác tenant, đừng đồng thời thu nhỏ vai trò thành không có quyền.

Mục tiêu là tránh một guard khác chặn trước, hoặc một lỗi khác xuất hiện sớm hơn làm phản ví dụ đổi ý nghĩa. Các ca kết hợp nhiều vi phạm vẫn có giá trị, nhưng nên được định danh riêng.

## 7. Thu nhỏ chuỗi thao tác có trạng thái

### 7.1. Loại nhiễu trước, giữ lịch sử cần thiết

Giả sử fixture ban đầu cung cấp một đơn nháp. Một trace làm lộ tạo payment intent trùng:

```text
READ_ORDER
SUBMIT(owner)
READ_ORDER
APPROVE(reviewer)
READ_ORDER
PAY(owner, key-a)
READ_ORDER
PAY(owner, key-a)
```

Nếu các lệnh đọc không liên quan đến lỗi, có thể thu về:

```text
SUBMIT(owner)
APPROVE(reviewer)
PAY(owner, key-a)
PAY(owner, key-a)
```

Không mặc định xóa được `SUBMIT` hoặc `APPROVE`. Khi thiếu tiền điều kiện, cả hai lần PAY có thể bị từ chối, khiến lỗi trùng tác động không xuất hiện.

Nếu lỗi chỉ xuất hiện khi một lần đọc làm mới cache hoặc kích hoạt hành vi cụ thể, lệnh đọc đó không còn là nhiễu. Mọi phép xóa phải được đánh giá bằng chạy lại.

### 7.2. Chọn ranh giới giữa fixture và trace

Có thể đặt đơn ở trạng thái APPROVED ngay trong fixture rồi giữ hai lệnh PAY. Cách này hữu ích cho test mục tiêu hẹp nếu hợp đồng cho phép dựng trạng thái đó một cách đáng tin cậy.

Tuy nhiên, nó thay đổi câu hỏi đang kiểm thử:

- Trace đầy đủ kiểm tra đường đi tới trạng thái và hành vi sau đó.
- Fixture đã duyệt kiểm tra hành vi trên một trạng thái đầu vào xác định.

Không tự chuyển các command quan trọng sang fixture trong quá trình thu nhỏ rồi tuyên bố đã giữ nguyên mọi đặc tính của ca gốc. Ghi rõ trạng thái ban đầu và những điều kiện đã được dựng sẵn.

### 7.3. Giữ tham chiếu bằng định danh tượng trưng

Trace có thể dùng:

```text
CREATE_ORDER(as order-A)
SUBMIT(order-A)
APPROVE(order-A)
PAY(order-A)
```

Nếu lệnh tạo bị xóa, các lệnh sau mất đối tượng. Một reducer có thể:

- Từ chối ứng viên không còn tham chiếu hợp lệ.
- Xóa cùng các command phụ thuộc, rồi kiểm tra lỗi có còn không.
- Dựng lại qua model theo quy tắc tường minh nếu đó là thiết kế của test.

Không âm thầm tạo thêm đơn hoặc bỏ qua lệnh không chạy được. Điều đó có thể thay đổi hành vi mà báo cáo không thể hiện.

Dùng tên tượng trưng rồi ánh xạ sang ID thật ở mỗi lần replay thường dễ quản lý hơn việc thu nhỏ trực tiếp ID cơ sở dữ liệu.

### 7.4. Thứ tự thu nhỏ phù hợp cho trace

Một chiến lược có thể là:

1. Thử bỏ các đoạn command lớn không cần thiết.
2. Thử bỏ từng command.
3. Giảm số đối tượng và actor không liên quan.
4. Thu nhỏ payload của các command còn lại.
5. Giản lược định danh, key và thời gian nhưng giữ các quan hệ.
6. Chạy lại toàn trace từ trạng thái sạch sau mỗi ứng viên.

Không phải mọi reducer đều thử đúng thứ tự này. Đây là một chiến lược thiết kế để ưu tiên giảm nhiễu cấu trúc trước khi tối ưu chi tiết.

Khi trace có lệnh bị cấm có chủ đích, không “sửa” nó thành lệnh hợp lệ chỉ để model dễ chạy. Sự từ chối và việc không tạo tác động có thể là chính điều property cần kiểm tra.

## 8. Thu nhỏ idempotency, payload và fingerprint

Các quan hệ thường quan trọng hơn độ dài key:

| Tình huống | Quan hệ cần giữ |
|---|---|
| Retry cùng thao tác | Cùng phạm vi key, cùng key, cùng nội dung nghiệp vụ |
| Tái dùng key cho nội dung khác | Cùng phạm vi, cùng key, khác fingerprint |
| Cùng chuỗi key ở hai tenant | Chuỗi key bằng nhau, phạm vi tenant khác nhau |
| Thao tác mới trên đối tượng đã hoàn tất | Key khác, bất biến trạng thái vẫn áp dụng |

Ví dụ, rút key thành chuỗi rỗng có thể làm request bị từ chối ở validation, thay vì đi tới logic idempotency. Nếu property đang xét retry hợp lệ, key sau thu nhỏ vẫn phải đáp ứng điều kiện định dạng.

Với payload:

- Nếu đang kiểm tra replay cùng nội dung, mọi giản lược phải được áp dụng nhất quán cho cả hai lần gửi.
- Nếu đang kiểm tra xung đột nội dung, giữ ít nhất một khác biệt có ý nghĩa nghiệp vụ.
- Nếu fingerprint được tính từ biểu diễn chuẩn hóa, dựng lại nó theo hợp đồng của môi trường test.
- Không chỉ so chuỗi JSON thô nếu hợp đồng cho phép các biểu diễn khác nhau nhưng cùng ý nghĩa.

Không dùng hàm quyết định replay của production để tự tính expected. Có thể dùng chung dữ liệu chuẩn của fixture, nhưng oracle về tác động mới hoặc xung đột phải độc lập.

Một phản ví dụ trùng tác động cần quan sát được tác động đó, chẳng hạn số payment intent hoặc ledger entry tăng lên. Hai response cùng thành công chưa đủ chứng minh tác động bị nhân đôi; status không đổi cũng chưa đủ chứng minh an toàn.

## 9. Thu nhỏ số tiền, thời gian và version theo biên

### 9.1. Dùng độ lệch so với biên

Thay vì sinh trực tiếp một số tiền lớn, biểu diễn:

```text
requested = remaining + excess
excess ≥ 1
```

Đối với hết hạn:

```text
now = expiresAt + delay
delay ≥ 0
```

Nếu hợp đồng hết hiệu lực tại đúng `expiresAt`, delay bằng 0 vẫn thuộc lớp hết hạn. Nếu hợp đồng dùng điều kiện khác, generator và oracle phải thay đổi tương ứng.

Đối với version cũ:

```text
currentVersion = baseVersion + gap
gap ≥ 1
command.expectedVersion = baseVersion
```

Khi giảm gap về 1, vẫn giữ bản chất stale version. Không giảm cả hai trường về cùng giá trị rồi coi đó là cùng tình huống.

### 9.2. Không buộc mọi lỗi co về 0

Một lỗi tràn số có thể chỉ xuất hiện gần giới hạn kiểu dữ liệu. Một lỗi làm tròn chỉ xuất hiện ở scale hoặc phần lẻ cụ thể. Một lỗi thời hạn có thể cần thứ tự giữa nhiều mốc thời gian.

Cần giữ điều kiện gây lỗi, chẳng hạn:

- Quan hệ tổng vượt giới hạn biểu diễn khi điều tra overflow.
- Tiền tệ và quy tắc scale khi điều tra tính tiền.
- Độ chính xác lưu timestamp khi điều tra lỗi ở adapter.
- Thứ tự tạo, hết hạn và sử dụng khi điều tra quyền có thời hạn.

jqwik cho phép thay đổi mục tiêu thu nhỏ của bộ sinh số bằng `shrinkTowards`. Chọn mục tiêu theo biên có ý nghĩa giúp mô tả ý định, nhưng không bảo đảm tìm được một phản ví dụ duy nhất. [jqwik User Guide: Change the Shrinking Target](https://jqwik.net/docs/current/user-guide.html#change-the-shrinking-target).

Ví dụ cú pháp cho một hạn mức minh họa:

```java
Arbitrary<Long> amounts = Arbitraries.longs()
        .between(0L, 1_000_000L)
        .shrinkTowards(100_000L);
```

Generator này chỉ đặt mục tiêu số; nó chưa giữ quan hệ “vượt hạn mức”. Nếu property cần luôn thử phần vượt, dùng cấu trúc `limit + positiveExcess` hoặc generator riêng cho lớp đó.

## 10. Tính xác định là điều kiện để shrinking có ích

Một ứng viên thường được đánh giá nhiều lần. Nếu cùng dữ liệu lúc lỗi lúc không, quá trình thu nhỏ có thể dừng ở mẫu không tái hiện ổn định hoặc bỏ qua mẫu quan trọng.

Cần kiểm soát:

| Nguồn không xác định | Biện pháp phù hợp |
|---|---|
| Đồng hồ thật | Truyền thời gian hoặc dùng clock điều khiển được |
| Random bên trong SUT/fixture | Biểu diễn lựa chọn thành dữ liệu test hoặc nguồn có thể tái hiện |
| Dữ liệu còn lại từ mẫu trước | Tạo mới hoặc reset state, repository, event buffer |
| Thứ tự collection ảnh hưởng hành vi | Làm rõ hợp đồng thứ tự và cấu trúc dữ liệu |
| Cache dùng chung | Cô lập hoặc điều khiển trạng thái cache |
| Dịch vụ ngoài | Dùng adapter giả phù hợp ở unit test; tách test tích hợp |
| Race condition | Điều phối lịch thực thi thay vì dựa vào sleep |

Mỗi lần replay cần trả về cùng trạng thái ban đầu về mặt nghiệp vụ. Một immutable input chưa đủ nếu SUT, singleton, cache hoặc fake repository vẫn giữ dữ liệu cũ.

Nếu ca thất bại liên quan hệ thống ngoài, giữ lại bằng chứng trước khi thử tối ưu nhiều lần. Không lặp các tác động thanh toán thật chỉ để tìm trace ngắn hơn; dùng môi trường và cơ chế test đúng phạm vi đã thiết kế.

## 11. Thu nhỏ lịch đồng thời và lỗi transaction

### 11.1. Trace tuần tự không thay thế lịch cạnh tranh

Một lỗi có thể cần:

```text
A đọc đơn APPROVED, version 7
B đọc đơn APPROVED, version 7
A thực hiện ghi/thanh toán
B thực hiện ghi/thanh toán
```

Nếu chuyển nó thành:

```text
A hoàn tất
B bắt đầu đọc dữ liệu mới
```

thì có thể không còn race condition. Vì vậy, trường hợp đồng thời cần thu nhỏ cả các điểm điều phối và quan hệ thứ tự cần thiết.

Có thể mô hình hóa:

```text
A.read < A.commit
B.read < B.commit
A.read và B.read đều diễn ra trước cập nhật thành công đầu tiên
```

Tùy lỗi, còn cần điều kiện về gửi lệnh ngoài hoặc nhận callback. Chỉ giữ các bước và quan hệ cần thiết, nhưng không xóa điểm đồng bộ tạo ra tranh chấp.

### 11.2. Phân biệt thất bại quan sát được

Khi kiểm tra transaction, thu nhỏ có thể gặp:

- Xung đột version được xử lý đúng.
- Deadlock hoặc lỗi hạ tầng.
- Hai giao dịch cùng commit trái hợp đồng.
- Chỉ một giao dịch commit nhưng tác động ngoài đã được gọi hai lần.

Những kết quả này không tương đương. Property cần quan sát trạng thái đã lưu và tác động nghiệp vụ phù hợp, thay vì coi mọi exception là dấu hiệu đã bảo vệ được bất biến.

Một fake tuần tự không chứng minh tính nguyên tử của idempotency, isolation hoặc rollback thực tế. Việc thu nhỏ trên fake chỉ giải thích mô hình fake; xác nhận lỗi lưu trữ phải chạy trên cơ chế tương ứng.

Nếu có transaction và hệ thống thanh toán ngoài, rollback cơ sở dữ liệu không tự hoàn tác việc thu tiền đã xảy ra. Giữ đúng ranh giới transaction và cơ chế đối soát/bù trừ trong mô hình tái hiện.

## 12. Khi nào dùng shrinking mặc định, khi nào cần tùy chỉnh?

Nên bắt đầu bằng các bộ sinh tiêu chuẩn, giới hạn miền rõ ràng và cấu trúc dữ liệu phụ thuộc tường minh. Nhiều trường hợp không cần viết một shrinker riêng.

Cân nhắc tùy chỉnh ở cấp mô hình/reducer khi:

- Trace có tham chiếu hoặc phụ thuộc phức tạp.
- Muốn giữ một loại vi phạm nghiệp vụ cụ thể.
- Dữ liệu gồm đồ thị, nhiều đối tượng hoặc lịch đồng thời.
- Thao tác xóa hoặc giảm giá trị mặc định phá hỏng điều kiện tái hiện.
- Chi phí replay cao, cần ưu tiên phép giản lược theo giá trị điều tra.

Một reducer khái niệm có thể hoạt động như sau. Đây là giả mã, không phải API mở rộng của jqwik:

```text
best = original
assert evaluateFresh(best) == TARGET_FAILURE

while còn ngân sách:
    improved = false

    for candidate in simplerCandidates(best):
        if không nhỏ hơn theo thước đo:
            continue
        if đã thử candidate:
            continue
        if không giữ được hợp đồng fixture:
            ghi nhận INVALID_INPUT
            continue

        outcome = evaluateFresh(candidate)

        if outcome == TARGET_FAILURE:
            best = candidate
            improved = true
            break

        if outcome == OTHER_FAILURE:
            ghi nhận để điều tra riêng

        if outcome == INCONCLUSIVE:
            ghi nhận nguyên nhân chưa kết luận

    if not improved:
        break

return best cùng trạng thái ngân sách và lịch sử đánh giá
```

`evaluateFresh` phải dựng lại môi trường cho từng ứng viên. `simplerCandidates` nên hữu hạn hoặc được giới hạn rõ. Sau mỗi cải thiện, sinh lại ứng viên từ phản ví dụ tốt nhất mới.

Không sửa collection của `best` tại chỗ rồi dùng nó làm “bản gốc” cho các phép so sánh sau. Dùng dữ liệu bất biến hoặc sao chép đủ sâu để lịch sử thu nhỏ có thể kiểm tra lại.

## 13. Ngân sách, chế độ shrinking và chi phí chạy

jqwik cung cấp các chế độ `BOUNDED`, `FULL` và `OFF` cho shrinking. Chế độ có giới hạn phù hợp với vòng chạy thường xuyên; chế độ đầy đủ có thể tốn nhiều thời gian. [jqwik User Guide: Property Attributes](https://jqwik.net/docs/current/user-guide.html#optional-property-attributes).

Các quyết định nên gắn với chi phí:

| Hoàn cảnh | Chiến lược |
|---|---|
| Policy thuần chạy nhanh | Cho phép thử nhiều ứng viên nhỏ |
| Trace dùng cơ sở dữ liệu | Giới hạn số lần replay và đo chi phí reset |
| Lịch đồng thời có điều phối | Giảm số actor/bước trước, giữ quan hệ thứ tự |
| Timeout khó tái hiện | Ổn định môi trường trước khi tăng ngân sách |
| Muốn xem mẫu lỗi ban đầu | Có thể tạm tắt shrinking để chẩn đoán, vẫn giữ failure |

Khi dừng do ngân sách, báo “mẫu nhỏ hơn tốt nhất đã tìm được”, thay vì khẳng định không thể thu nhỏ thêm. Luôn giữ mẫu ban đầu để tránh mất chứng cứ nếu mẫu thu nhỏ có vấn đề.

Nếu phần lớn ứng viên bị loại vì fixture không còn hợp lệ, sửa mô hình dữ liệu hoặc cách dựng phụ thuộc trước khi chỉ tăng thời gian. Nếu mỗi lần replay chậm, tìm phần có thể kiểm tra ở lớp miền thuần, đồng thời giữ test tích hợp cần thiết cho bảo đảm thực tế.

## 14. Từ phản ví dụ đến bằng chứng và regression test

### 14.1. Giữ cả mẫu gốc và mẫu đã thu nhỏ

Một báo cáo hữu ích gồm:

| Trường | Nội dung |
|---|---|
| Property hoặc BR-ID | Bất biến đã bị vi phạm |
| Mẫu ban đầu | Dữ liệu hoặc trace khi phát hiện |
| Mẫu đã thu nhỏ | Phiên bản dễ đọc để tái hiện |
| Fixture ban đầu | Actor, đối tượng, trạng thái, thời gian |
| Expected/actual | Quyết định, trạng thái và tác động |
| Điểm lệch đầu tiên | Bước đầu tiên khác mô hình |
| Thông tin tái hiện | Seed, phiên bản công cụ, generator và cấu hình liên quan |
| Kết quả thu nhỏ | Hoàn tất theo phép thử hiện có hoặc dừng do ngân sách |
| Phạm vi | Miền thuần, adapter, transaction hay hệ thống ngoài |

Dùng dữ liệu tổng hợp và định danh tượng trưng khi có thể. Nếu thay ID hoặc che dữ liệu trong báo cáo, áp dụng ánh xạ nhất quán để vẫn thấy quan hệ cùng người, khác tenant hoặc cùng key. Không đưa token, secret hoặc dữ liệu khách hàng thật vào regression fixture.

### 14.2. Seed hỗ trợ tái hiện nhưng không thay ca hồi quy

Seed đi cùng phiên bản và generator giúp tái tạo quá trình sinh trong môi trường phù hợp. Khi generator hoặc công cụ thay đổi, cùng seed có thể không còn tạo đúng mẫu cũ.

Vì vậy:

1. Giữ seed để phục vụ điều tra lần chạy.
2. Lưu trace hoặc dữ liệu cụ thể đã xác nhận.
3. Đặt tên test theo hành vi bị cấm.
4. Assert dữ liệu và tác động có ý nghĩa, không chỉ exception hoặc mã HTTP.
5. Giữ property để tiếp tục khám phá các biến thể khác.

Regression test không nên sao chép nguyên báo cáo dài, định danh ngẫu nhiên hoặc các trường không liên quan. Nó cần thể hiện rõ lý do ca đó từng gây lỗi.

### 14.3. Xác nhận phạm vi lỗi đã sửa

Với lỗi hoàn tiền, phản ví dụ nhỏ có thể chỉ cần một lần gọi trên trạng thái đã hoàn trước đó. Tuy nhiên, bản sửa vẫn cần được đặt vào ngữ cảnh:

- Quy tắc tính số còn lại đúng trong miền.
- Application service thực sự sử dụng quy tắc.
- Cơ sở dữ liệu không cho hai yêu cầu đồng thời vượt tổng.
- Retry không tạo tác động hoàn tiền thêm.

Shrinking giúp làm rõ điều kiện lỗi; nó không tự bổ sung các lớp bảo vệ hoặc chứng minh toàn bộ đường xử lý.

## 15. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ cần test còn đỏ | Mẫu cuối có thể là lỗi khác | Định danh property và loại vi phạm rõ ràng |
| Giảm mọi số về 0 | Xóa điều kiện vượt biên hoặc overflow | Sinh theo độ lệch và quan hệ miền |
| Thu nhỏ ID độc lập | Mất quan hệ tự duyệt/cùng đối tượng | Dùng vai trò quan hệ và factory |
| Xóa mọi bước trước lỗi | PAY/APPROVE không còn tiền điều kiện | Giữ phụ thuộc hoặc báo fixture không dựng được |
| “Repair” dữ liệu tùy ý | Vô tình sửa mất tình huống tấn công | Quy định phép dựng lại và kiểm tra witness |
| Lọc quá mạnh | Mất thời gian sinh, ít mẫu có ích | Sinh cấu trúc thỏa quan hệ theo thiết kế |
| Chỉ lưu seed | Khó tái hiện sau khi generator đổi | Giữ mẫu cụ thể làm regression test |
| Dùng state chung giữa replay | Lỗi lúc có lúc không | Reset toàn bộ ngữ cảnh cần thiết |
| Coi timeout là vi phạm nghiệp vụ | Kết luận sai nguyên nhân | Phân loại kết quả chưa kết luận |
| Gọi kết quả là nhỏ nhất tuyệt đối | Đánh giá quá mức khả năng reducer | Nêu phép thu nhỏ và ngân sách |
| Chỉ nhìn status | Bỏ sót tác động trùng hoặc số tiền sai | Quan sát snapshot và tác động |
| Cho rằng shrinking chứng minh bảo mật | Bỏ qua thiếu sót của property và generator | Kết hợp example, property và test ở đúng lớp |

## 16. Bài tập thực hành

### Bài tập 1: Hoàn tiền vượt số còn lại

Dùng generator trong ví dụ, giải thích vì sao quan hệ vượt số còn lại được giữ khi ba thành phần gốc giảm.

Tìm một bộ dữ liệu nhỏ làm lộ lỗi so sánh với tổng đã thu. Sau đó thêm property cho trường hợp hợp lệ để implementation luôn từ chối không thể vượt qua cả bộ kiểm thử.

### Bài tập 2: Thu nhỏ tự phê duyệt

Thiết kế fixture có actor là người tạo, cùng tenant và có quyền approver. Mô tả phép giản lược định danh vẫn giữ quan hệ này.

Chỉ ra vì sao giảm role thành người dùng thường hoặc đổi tenant sẽ làm phản ví dụ không còn tập trung vào tự duyệt.

### Bài tập 3: Trace gửi thanh toán trùng

Bắt đầu từ trace có submit, approve, hai lần PAY cùng key và nhiều lệnh đọc. Đề xuất thứ tự thử xóa từng nhóm command.

Ghi rõ fixture ban đầu, các tiền điều kiện không được mất và quan sát nào chứng minh có payment intent thứ hai.

### Bài tập 4: Quyết định phê duyệt cũ

Dựng chuỗi submit, approve, sửa tổng tiền rồi thanh toán theo chính sách yêu cầu duyệt lại. Thu nhỏ tổng tiền và version nhưng giữ việc quyết định cũ không bao phủ dữ liệu mới.

Phân biệt ứng viên không còn gây lỗi với ứng viên làm phát sinh exception khác.

### Bài tập 5: Thu nhỏ lịch cạnh tranh

Mô tả hai yêu cầu cùng đọc version trước khi ghi. Chọn các điểm đồng bộ tối thiểu cần giữ để tái hiện một vi phạm mà bạn xác định.

Nêu rõ giới hạn của mô hình trong bộ nhớ và điều cần xác nhận với transaction/cơ chế lưu thực tế.

## 17. Tiêu chí đánh giá chiến lược shrinking

- Mẫu thu nhỏ vẫn thể hiện cùng vi phạm nghiệp vụ cần điều tra.
- Dữ liệu nền có ý nghĩa, trong khi hành vi lạm dụng không bị lọc bỏ.
- Những quan hệ bằng nhau, khác nhau, vượt biên và phụ thuộc thời gian được giữ.
- Trace không mất đối tượng tham chiếu hoặc tiền điều kiện một cách âm thầm.
- Mỗi ứng viên được replay từ trạng thái sạch và có thể tái hiện.
- Lỗi khác hoặc timeout được ghi nhận tách biệt với lỗi mục tiêu.
- Phép đơn giản hóa có thứ tự rõ, không tạo vòng lặp và có ngân sách.
- Báo cáo giữ được mẫu gốc, mẫu thu nhỏ, expected/actual và phạm vi bảo đảm.
- Phản ví dụ đã xác nhận được chuyển thành regression test dễ đọc.
- Các bảo đảm về transaction, idempotency và đồng thời được kiểm tra ở đúng lớp.

Một chiến lược shrinking tốt giúp nhóm phát triển nhìn thấy quan hệ nghiệp vụ bị phá vỡ trong tình huống ít nhiễu nhất có thể. Giá trị của kết quả nằm ở việc lỗi còn nguyên ý nghĩa, tái hiện được và dẫn đến một kiểm thử hồi quy rõ ràng.
