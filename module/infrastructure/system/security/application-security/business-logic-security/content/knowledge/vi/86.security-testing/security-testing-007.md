# Business impact test — Kiểm thử tác động nghiệp vụ

Bài học thuộc chương **Security Testing** của module bảo mật logic nghiệp vụ (`SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`). Nội dung tập trung vào việc chứng minh một đường lạm dụng có thể gây hậu quả gì đối với tiền, quyền lợi, quy trình phê duyệt, dữ liệu và hoạt động vận hành.

Một request trả HTTP 200 chưa chứng minh doanh nghiệp đã mất tiền. Một request trả HTTP 403 cũng chưa chứng minh không có tác động sai xảy ra trước đó. **Business impact test** cần nối hành vi kỹ thuật với kết quả nghiệp vụ quan sát được: tiền được hoàn thêm, đơn được thực hiện khi chưa duyệt, quyền được cấp sai hoặc dữ liệu tenant khác bị lộ.

Sau bài học, bạn cần có thể:

- Chuyển một nghi vấn logic thành giả thuyết tác động có thể kiểm tra.
- Xác định bất biến, trạng thái chuẩn và nguồn bằng chứng độc lập.
- Đo chênh lệch giữa kết quả hợp lệ và kết quả khi lạm dụng.
- Phân biệt tác động đã quan sát, phạm vi đã xác nhận và ước lượng có điều kiện.
- Viết hợp đồng kiểm thử bằng Java cho tác động hoàn tiền và retry.
- Đặt kết quả vào bối cảnh transaction, idempotency, xử lý bất đồng bộ và cạnh tranh đồng thời.
- Lập báo cáo đủ rõ để quyết định ưu tiên sửa và tiêu chí xác nhận bản sửa.

## 1. Business impact test trả lời câu hỏi nào?

Trong bài này, thuật ngữ chỉ một cách thiết kế kiểm thử bảo mật: **thực hiện tình huống lạm dụng có kiểm soát và kiểm tra hậu quả đối với hợp đồng nghiệp vụ**.

Chuỗi lập luận cần có:

```text
Điểm yếu hoặc giả thuyết
    → hành động mà actor có thể thực hiện
    → quy tắc nghiệp vụ bị vượt qua
    → thay đổi dữ liệu hoặc tác động
    → hậu quả đối với hoạt động kinh doanh
```

Ví dụ:

```text
Idempotency không được thực thi đúng
    → gửi lại cùng yêu cầu hoàn tiền
    → cùng một thao tác được thực hiện thêm lần nữa
    → nhà cung cấp ghi nhận hai khoản hoàn thay vì một
    → phát sinh khoản chi ngoài hợp đồng và công việc đối soát
```

Nếu chỉ chứng minh có hai response thành công, chuỗi lập luận chưa đến tác động cuối. Nếu chỉ nêu “có thể thiệt hại lớn” mà không có dữ liệu hoặc điều kiện, kết luận chưa đủ để đánh giá.

### 1.1. Tác động kỹ thuật và tác động kinh doanh

| Quan sát kỹ thuật | Câu hỏi nghiệp vụ cần trả lời |
|---|---|
| Một trường giá bị thay đổi | Máy chủ có dùng giá đó để tạo nghĩa vụ thanh toán hoặc thực hiện đơn không? |
| Actor gọi được endpoint phê duyệt | Quyết định phê duyệt có được lưu và cho phép bước tiếp theo không? |
| Request được xử lý hai lần | Có thêm quyền lợi, khoản thu/chi hoặc thực hiện đơn không? |
| Đọc được object ID của tenant khác | Response có dữ liệu không được phép đọc hay chỉ là metadata được công khai? |
| Hai giao dịch cùng báo thành công | Cả hai có commit và tạo tác động vượt giới hạn không? |
| Một thao tác bị báo lỗi | Trước khi báo lỗi, có event hoặc tác động ngoài nào đã phát sinh không? |

OWASP phân biệt tác động kỹ thuật với tác động kinh doanh và nhấn mạnh đánh giá cần gắn với bối cảnh tổ chức. Những yếu tố như thiệt hại tài chính, uy tín và dữ liệu không có mức quan trọng giống nhau ở mọi doanh nghiệp. [OWASP Risk Rating Methodology](https://community.owasp.org/OWASP_Risk_Rating_Methodology).

### 1.2. Không phải mọi tác động đều cần quy thành tiền

Những hậu quả quan trọng có thể gồm:

- Mất kiểm soát tách biệt người tạo và người phê duyệt.
- Cấp quyền sử dụng dịch vụ ngoài hợp đồng.
- Thay đổi người thụ hưởng hoặc dữ liệu quyết định thanh toán.
- Lộ dữ liệu giữa các tenant.
- Giữ chỗ hoặc chiếm tài nguyên vượt hạn mức.
- Làm sai ledger, báo cáo hoặc dữ liệu đối soát.
- Tăng công việc xử lý thủ công và khiếu nại.
- Gây gián đoạn một luồng nghiệp vụ quan trọng.

Đừng quy đổi tùy tiện mọi bản ghi lộ hoặc mọi lần sai phê duyệt thành một khoản tiền cố định. Có thể báo số lượng đối tượng, loại dữ liệu, mức quyền và quy trình bị ảnh hưởng trước khi chủ sở hữu nghiệp vụ đánh giá tiếp.

## 2. Bắt đầu từ bất biến và giả thuyết tác động

### 2.1. Viết điều phải được bảo vệ

Ví dụ về các bất biến:

```text
Tổng hoàn tiền thành công không vượt số tiền đã thu theo hợp đồng.
Cùng một thao tác hoàn tiền không tạo thêm tác động khi retry.
Chỉ người có quyền trên đúng đối tượng mới được phê duyệt.
Một đơn chưa được phê duyệt hợp lệ không được thực hiện.
Số tiền thực hiện phải khớp dữ liệu chuẩn phía máy chủ.
Actor tenant A không đọc hoặc sửa dữ liệu riêng của tenant B.
```

Các quy tắc phải phản ánh miền cụ thể. Nếu doanh nghiệp cho phép khoản bồi hoàn ngoài giá trị đã thu, khoản đó cần loại nghiệp vụ và thẩm quyền riêng; không tự áp bất biến hoàn tiền thông thường cho mọi hình thức chi.

### 2.2. Chuyển nghi vấn thành giả thuyết đo được

Mẫu phát biểu:

```text
Với actor và đối tượng ở điều kiện C,
khi thực hiện chuỗi A,
nếu kiểm soát bị vượt qua thì quan sát được thay đổi E,
dẫn đến tác động nghiệp vụ I.
```

Ví dụ:

```text
Với khách hàng sở hữu đơn đã thanh toán,
khi gửi lại cùng yêu cầu hoàn 300.000 đồng với cùng idempotency key,
nếu hệ thống xử lý trùng thì xuất hiện thêm một khoản hoàn thành công,
làm tổng khoản hoàn mới tăng từ 300.000 lên 600.000 đồng.
```

Phát biểu này xác định actor, tiền điều kiện, thao tác, nguồn quan sát và đại lượng tác động. Nó có thể bị bác bỏ bằng kiểm thử, thay vì chỉ là một nhận xét chung.

### 2.3. Bảng liên kết quy tắc với tác động

| Mã | Quy tắc | Tình huống thử | Tác động cần quan sát |
|---|---|---|---|
| BI-01 | Giá thực hiện do máy chủ quyết định | Giảm trường giá gửi từ client | Đơn/quyền lợi được thực hiện với số tiền thiếu |
| BI-02 | Phê duyệt đúng người và đúng dữ liệu | Tự duyệt hoặc dùng phê duyệt cũ | Cam kết hay thực hiện đơn trái thẩm quyền |
| BI-03 | Quyền theo đối tượng và tenant | Thay định danh đối tượng | Đọc/sửa dữ liệu ngoài phạm vi |
| BI-04 | Retry không tạo tác động mới | Gửi lại cùng thao tác | Thêm khoản hoàn, quyền lợi hoặc sự kiện thực hiện |
| BI-05 | Không vượt giới hạn tổng | Hai yêu cầu tranh phần còn lại | Số tiền, số lượng hoặc tài nguyên vượt hạn mức |
| BI-06 | Lỗi không để lại kết quả dở dang trái hợp đồng | Lỗi giữa các bước xử lý | Trạng thái và tác động không còn nhất quán |

## 3. Xác định kết quả chuẩn và nguồn bằng chứng

### 3.1. Oracle phải độc lập với quyết định cần kiểm tra

Oracle là cơ sở xác định kết quả đúng. Có thể dùng:

- Hợp đồng nghiệp vụ đã thống nhất.
- Giá hoặc báo giá chuẩn được tạo phía máy chủ.
- Bảng chuyển trạng thái và quyền theo đối tượng.
- Dữ liệu đã thu, đã hoàn và hạn mức còn lại.
- Kết quả giao dịch từ sandbox của nhà cung cấp.
- Ledger hoặc bản ghi tác động thành công được truy xuất theo phạm vi test.

Không dùng chính response bị nghi ngờ làm nguồn duy nhất để xác nhận số tiền đã thực hiện. Cũng không gọi lại hàm tính sai của production để tạo expected.

### 3.2. Chụp trạng thái trước và sau

Một snapshot cho hoàn tiền có thể chứa:

```text
orderId
tenantId
capturedMinor
recordedRefundedMinor
successfulRefundOperations
providerRefundedMinor
successfulProviderRefunds
postedRefundOperations
```

Các trường thể hiện những lớp khác nhau:

- `recordedRefundedMinor`: hệ thống ứng dụng ghi nhận đã hoàn bao nhiêu.
- `providerRefundedMinor`: nguồn quan sát nhà cung cấp ghi nhận đã hoàn thành bao nhiêu.
- `successfulRefundOperations`: số thao tác hoàn tiền nghiệp vụ đã hoàn tất.
- `postedRefundOperations`: số nghiệp vụ hoàn tiền đã được ghi nhận vào ledger theo định nghĩa test.

Không coi số raw message, số lần gọi hàm và số tác động thành công là cùng một đại lượng. Một message có thể được giao lại nhiều lần nhưng chỉ tạo một tác động nghiệp vụ.

### 3.3. Bằng chứng cần nối được qua các lớp

Có thể dùng các định danh liên kết:

```text
testRunId
    → orderId
    → businessOperationId
    → payment/refund reference
    → ledger posting reference
    → event correlation
```

Mục tiêu là chứng minh các dữ kiện thuộc cùng tình huống. Nếu tổng hoàn tiền tăng ở dashboard chung nhưng không tách được đơn đang test khỏi luồng khác, chưa đủ căn cứ quy thay đổi đó cho request thử nghiệm.

Dữ liệu quan sát nên có timestamp, trạng thái thành công/thất bại và phạm vi actor/tenant. Token, secret và dữ liệu nhạy cảm không cần thiết phải được loại khỏi bằng chứng.

## 4. Thiết kế môi trường và giới hạn thử nghiệm

Một bài kiểm thử tác động nên được dựng trong môi trường có thể quan sát và phục hồi:

- Dùng tài khoản, tenant và đối tượng tổng hợp.
- Dùng sandbox hoặc adapter tích hợp phù hợp cho giao dịch.
- Cố định số lần gọi, số đối tượng và giá trị thử nghiệm.
- Xác định các tác động đi kèm như giao hàng, cấp license, email hoặc ghi điểm thưởng.
- Giữ dữ liệu trước khi cleanup để còn đối chiếu.
- Dựng lại môi trường sạch cho lần thử tiếp theo.

Ví dụ, tình huống kiểm tra replay chỉ cần một thao tác hợp lệ và một lần gửi lại để đánh giá giả thuyết ban đầu. Không cần tăng hàng nghìn request khi đã đủ bằng chứng có tác động trùng.

OWASP hướng dẫn kiểm thử chức năng thanh toán phải xem xét luồng thanh toán, dữ liệu giao dịch và tác động thực tế; tài liệu cũng đề cập việc dùng thông tin test của nhà cung cấp và quản lý các đơn phát sinh trong kiểm thử. [OWASP WSTG: Payment Functionality](https://wstg.owasp.org/latest/14-Business_Logic/10-Payment_Functionality/).

Khi test dùng fake, báo rõ fake chứng minh điều gì. Một fake đếm hai lời gọi chỉ chứng minh ứng dụng gửi hai lệnh qua cổng đó; nó chưa chứng minh nhà cung cấp sẽ thực hiện hai khoản chi trong môi trường thật.

## 5. Quy trình thực hiện một business impact test

### Bước 1: Chốt hợp đồng và điều kiện

Ghi actor, quyền, tenant, trạng thái đầu, dữ liệu tiền và chính sách liên quan. Nếu thử idempotency, xác định phạm vi key, nội dung thao tác và hành vi replay mong muốn.

### Bước 2: Chạy luồng hợp lệ làm đối chứng

Xác nhận môi trường thực hiện đúng một thao tác hợp lệ. Đối chứng giúp tránh kết luận sai khi sandbox, adapter hoặc fixture vốn đang lỗi.

### Bước 3: Lưu snapshot ban đầu

Đọc dữ liệu ở nguồn có thẩm quyền cho từng lớp cần kết luận. Xác nhận trạng thái ban đầu đã ổn định, không còn job cũ có thể làm thay đổi kết quả.

### Bước 4: Thực hiện đúng một biến thể lạm dụng

Chỉ đổi yếu tố đang khảo sát khi có thể: key, actor, object ID, giá, version hoặc thứ tự bước. Giữ các điều kiện khác hợp lệ để biết nguyên nhân bị chặn hoặc được phép.

### Bước 5: Quan sát đến ranh giới xử lý đã xác định

Với xử lý bất đồng bộ, theo dõi trạng thái job, outbox/consumer hoặc giao dịch sandbox. Không chỉ ngủ một khoảng rồi giả định mọi tác động đã xong.

Nếu hết thời gian mà chưa có trạng thái kết luận, đánh dấu chưa kết luận. Một timeout không tự chứng minh an toàn hoặc có tác động nghiệp vụ.

### Bước 6: So sánh trạng thái và tác động

Tính chênh lệch thực tế với kết quả theo hợp đồng. Kiểm tra cả bản ghi ứng dụng, tác động ngoài và đối tượng không được phép thay đổi.

### Bước 7: Xác nhận mức độ tái hiện trong phạm vi nhỏ

Dùng fixture mới để loại dữ liệu còn sót hoặc trùng định danh. Chỉ thực hiện số lần cần thiết theo kế hoạch. Ghi tỷ lệ tái hiện như quan sát của cấu hình test, không suy thành xác suất bị khai thác trong production.

### Bước 8: Báo cáo, lưu bằng chứng và phục hồi dữ liệu test

Giữ trace ngắn, snapshot và tác động trước khi cleanup. Phân biệt hoàn tác trong môi trường test với khả năng đảo ngược tác động kinh doanh ngoài thực tế.

## 6. Case study: retry hoàn tiền gây khoản chi trùng

### 6.1. Hợp đồng minh họa

Giả sử một hệ thống có quy tắc:

- Một đơn đã thu 1.000.000 đồng.
- Trước test đã hoàn thành 600.000 đồng.
- Một yêu cầu hoàn mới 300.000 đồng là hợp lệ vì còn 400.000 đồng.
- Gửi lại cùng yêu cầu, cùng phạm vi và cùng key phải trả kết quả đã có.
- Retry không tạo khoản hoàn, ghi nhận ledger hoặc thao tác nghiệp vụ mới.
- Tổng hoàn tiền thông thường không được vượt số tiền đã thu.

Các số liệu là dữ liệu mô phỏng để giải thích phương pháp.

### 6.2. Kết quả hợp lệ

| Thời điểm | Tổng đã hoàn | Tổng khoản hoàn mới trong test | Số tác động hoàn mới |
|---|---:|---:|---:|
| Trước test | 600.000 | 0 | 0 |
| Sau lần đầu | 900.000 | 300.000 | 1 |
| Sau retry | 900.000 | 300.000 | 1 |

Kết quả replay có thể vẫn trả thành công cho client. Điều cần bảo vệ là cùng thao tác không tạo thêm tác động.

### 6.3. Kết quả giả định khi có lỗi

| Thời điểm | Tổng đã hoàn | Tổng khoản hoàn mới trong test | Số tác động hoàn mới |
|---|---:|---:|---:|
| Trước test | 600.000 | 0 | 0 |
| Sau lần đầu | 900.000 | 300.000 | 1 |
| Sau retry | 1.200.000 | 600.000 | 2 |

Nếu dữ liệu nguồn nhà cung cấp xác nhận cả hai khoản đều hoàn thành, có thể diễn giải:

```text
Khoản hoàn mới hợp lệ theo hợp đồng: 300.000
Khoản hoàn mới quan sát được:       600.000
Khoản chi thêm do retry:            300.000

Tổng hoàn của đơn:                1.200.000
Số đã thu:                       1.000.000
Phần tổng hoàn vượt số đã thu:      200.000
```

Hai đại lượng 300.000 và 200.000 mô tả hai khía cạnh chồng lấp của cùng tình huống. Không cộng chúng thành “thiệt hại 500.000”.

Khoản chi thêm so với luồng chuẩn là 300.000 đồng. Phần vượt tổng đã thu là 200.000 đồng. Nếu chỉ thấy bản ghi ứng dụng mà chưa thấy khoản hoàn thành ở nhà cung cấp, phải giới hạn kết luận ở lỗi ghi nhận hoặc ý định hoàn tiền tương ứng.

### 6.4. Câu hỏi điều tra bổ sung

- Retry có trả cùng business operation ID nhưng vẫn gửi thêm lệnh ngoài không?
- Kiểm soát tổng hoàn có chạy ở thời điểm thực hiện hay chỉ khi tạo yêu cầu?
- Khoản hoàn và bản ghi idempotency có được ghi nhất quán không?
- Worker có xử lý lại cùng event mà tạo tác động mới không?
- Nhà cung cấp có cơ chế idempotency và ứng dụng có sử dụng đúng không?
- Có bù trừ sau đó không, và bù trừ có xóa dấu vết tác động gốc khỏi báo cáo không?

Các câu hỏi này định hướng tìm nguyên nhân. Không nên biến tất cả chúng thành nguyên nhân đã xác nhận chỉ từ một lần thấy tác động trùng.

## 7. Hợp đồng kiểm thử bằng Java

Ví dụ sau dùng Java 17 trở lên và JUnit Jupiter. Đây là lớp kiểm thử hợp đồng trừu tượng: dự án phải cung cấp adapter `Scenario` và lớp con thực thi `createSettledScenario`.

Adapter có trách nhiệm tạo dữ liệu test, gọi luồng nghiệp vụ thật ở lớp cần kiểm tra và đọc snapshot từ nguồn quan sát phù hợp. Đoạn mã không tự tạo endpoint hay tích hợp với một nhà cung cấp cụ thể.

```java
import java.time.Duration;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

public abstract class RefundBusinessImpactContractTest {
    protected enum Decision {
        ACCEPTED, REPLAYED, REJECTED
    }

    protected record Result(
            Decision decision,
            String businessOperationId) {}

    protected record Snapshot(
            long capturedMinor,
            long recordedRefundedMinor,
            long providerRefundedMinor,
            long successfulRefundOperations,
            long successfulProviderRefunds,
            long postedRefundOperations) {}

    protected interface Scenario extends AutoCloseable {
        Result refund(long amountMinor, String idempotencyKey);

        void awaitSettled(Duration timeout);

        Snapshot snapshot();

        @Override
        void close();
    }

    protected abstract Scenario createSettledScenario(
            long capturedMinor,
            long alreadyRefundedMinor);

    @Test
    void retryOfOneRefundMustNotCreateAdditionalBusinessImpact() {
        try (Scenario scenario =
                     createSettledScenario(1_000_000L, 600_000L)) {
            Snapshot before = scenario.snapshot();

            assertAll(
                    () -> assertEquals(
                            1_000_000L, before.capturedMinor()),
                    () -> assertEquals(
                            600_000L, before.recordedRefundedMinor()),
                    () -> assertEquals(
                            600_000L, before.providerRefundedMinor()));

            Result first = scenario.refund(300_000L, "refund-key-a");
            scenario.awaitSettled(Duration.ofSeconds(5));
            Snapshot afterFirst = scenario.snapshot();

            assertAll(
                    () -> assertEquals(
                            Decision.ACCEPTED, first.decision()),
                    () -> assertEquals(
                            before.capturedMinor(),
                            afterFirst.capturedMinor()),
                    () -> assertEquals(
                            before.recordedRefundedMinor() + 300_000L,
                            afterFirst.recordedRefundedMinor()),
                    () -> assertEquals(
                            before.providerRefundedMinor() + 300_000L,
                            afterFirst.providerRefundedMinor()),
                    () -> assertEquals(
                            before.successfulRefundOperations() + 1L,
                            afterFirst.successfulRefundOperations()),
                    () -> assertEquals(
                            before.successfulProviderRefunds() + 1L,
                            afterFirst.successfulProviderRefunds()),
                    () -> assertEquals(
                            before.postedRefundOperations() + 1L,
                            afterFirst.postedRefundOperations()));

            Result replay = scenario.refund(300_000L, "refund-key-a");
            scenario.awaitSettled(Duration.ofSeconds(5));
            Snapshot afterReplay = scenario.snapshot();

            assertAll(
                    () -> assertEquals(
                            Decision.REPLAYED, replay.decision()),
                    () -> assertNotNull(first.businessOperationId()),
                    () -> assertEquals(
                            first.businessOperationId(),
                            replay.businessOperationId()),
                    () -> assertEquals(afterFirst, afterReplay),
                    () -> assertTrue(
                            afterReplay.recordedRefundedMinor()
                                    <= afterReplay.capturedMinor()));
        }
    }

    @Test
    void refundAboveRemainingAmountMustHaveNoBusinessEffect() {
        try (Scenario scenario =
                     createSettledScenario(1_000_000L, 800_000L)) {
            Snapshot before = scenario.snapshot();

            assertAll(
                    () -> assertEquals(
                            1_000_000L, before.capturedMinor()),
                    () -> assertEquals(
                            800_000L, before.recordedRefundedMinor()),
                    () -> assertEquals(
                            800_000L, before.providerRefundedMinor()));

            Result rejected =
                    scenario.refund(300_000L, "refund-key-b");
            scenario.awaitSettled(Duration.ofSeconds(5));
            Snapshot after = scenario.snapshot();

            assertAll(
                    () -> assertEquals(
                            Decision.REJECTED, rejected.decision()),
                    () -> assertEquals(before, after));
        }
    }
}
```

### 7.1. Những lựa chọn có ý nghĩa trong ví dụ

- Test đầu tiên xác nhận cả luồng hợp lệ, tránh một implementation luôn từ chối.
- Chụp riêng trạng thái sau lần đầu và sau retry để cô lập tác động của retry.
- Kiểm tra số tiền cùng số nghiệp vụ thành công, không chỉ operation ID.
- Snapshot bao gồm nguồn ứng dụng và nguồn nhà cung cấp.
- Test từ chối kiểm tra dữ liệu và tác động giữ nguyên.
- Cleanup xảy ra sau khi đã quan sát và assert.

Các bộ đếm trong ví dụ là **số tác động nghiệp vụ thành công theo phạm vi đơn**, không phải số dòng raw ledger, số HTTP request hoặc số lần giao message. Nếu ledger dùng ghi sổ kép, một nghiệp vụ có thể có nhiều dòng; adapter phải tổng hợp theo định nghĩa nghiệp vụ phù hợp.

### 7.2. Hợp đồng của awaitSettled

`awaitSettled` không được chỉ sleep rồi trả về. Nó cần chờ những công việc đã biết của tình huống đến trạng thái kết luận và báo lỗi nếu hết thời gian.

Khoảng năm giây chỉ là giá trị minh họa. Adapter có thể cần theo dõi job ID, trạng thái provider hoặc mốc xử lý của consumer. Việc không thấy thay đổi trong một khoảng ngắn không chứng minh hệ thống không bao giờ tạo tác động muộn.

Những đường callback trễ, giao message lại hoặc worker phục hồi sau crash cần ca kiểm thử riêng có điều phối phù hợp.

### 7.3. Phạm vi bảo đảm tùy adapter

| Adapter | Điều có thể kết luận |
|---|---|
| Fake trong bộ nhớ | Cách phối hợp và tác động được fake mô hình hóa |
| Logic ứng dụng với cơ sở dữ liệu thật | Dữ liệu lưu, transaction và các cổng đã tích hợp trong test |
| Sandbox nhà cung cấp | Kết quả tích hợp quan sát được trong sandbox |
| Consumer/outbox thật trong môi trường test | Tác động sau xử lý bất đồng bộ của cấu hình đó |

Không ghi “đã chứng minh hoàn tiền ngoài thực tế” nếu `providerRefundedMinor` chỉ được lấy từ một stub luôn trả thành công.

## 8. Các nhóm business impact test cần có

### 8.1. Sửa giá và số lượng

Thiết kế một đơn với giá chuẩn phía máy chủ, rồi thay trường client có thể gửi như đơn giá, tổng hoặc số lượng ở vị trí đang nghi ngờ.

Quan sát:

- Giá trị được tạo trên đơn và yêu cầu thanh toán.
- Số tiền đã được xác nhận.
- Hàng hóa, quyền lợi hoặc dịch vụ được thực hiện.
- Chênh lệch so với giá hợp lệ theo hợp đồng.

Nếu hợp đồng quy định máy chủ tính lại giá và bỏ qua giá client, test có thể pass dù request không bị từ chối. Điều cần xác nhận là không thực hiện đơn với giá trái hợp đồng.

Đừng coi giá hiển thị bị đổi là đã mất doanh thu khi server vẫn tính đúng ở bước cuối. Cũng không coi việc chỉ validate số dương là đủ khi một giá dương rất nhỏ vẫn có thể sai về logic.

### 8.2. Bỏ qua hoặc lạm dụng phê duyệt

Các trường hợp:

```text
DRAFT → gọi trực tiếp bước thực hiện
Người tạo có thêm role approver → tự duyệt
Phê duyệt version cũ → sửa người thụ hưởng → thực hiện
Approver cùng role nhưng khác tenant → phê duyệt
```

Quan sát quyết định được lưu, dữ liệu được bao phủ bởi quyết định và bước thực hiện sau đó.

“Giá trị đơn được duyệt sai” là mức phơi nhiễm hoặc cam kết trái thẩm quyền. Chỉ gọi đó là khoản chi thực hiện nếu có bằng chứng tiền đã được chuyển hoặc nghĩa vụ tương ứng đã phát sinh theo hợp đồng.

OWASP khuyến nghị thực thi ủy quyền giao dịch phía máy chủ, kiểm soát chuyển trạng thái và bảo vệ dữ liệu giao dịch khỏi thay đổi sau khi được ủy quyền. Đây là cơ sở để test cả người thực hiện lẫn dữ liệu được phép thực hiện. [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).

### 8.3. Sai quyền theo đối tượng

Dùng hai tenant tổng hợp với dữ liệu dễ phân biệt. Actor tenant A thử đọc hoặc sửa đối tượng của tenant B.

Bằng chứng nên xác định:

- Loại tài nguyên và thuộc tính bị truy cập.
- Quyền dự kiến của actor.
- Dữ liệu riêng thực sự xuất hiện trong response hoặc bị thay đổi.
- Tác động xuống bước sau nếu đó là thao tác ghi.

Chứng minh bằng mẫu dữ liệu tối thiểu đủ xác nhận. Không cần thu thập hàng loạt dữ liệu để chứng minh một đường truy cập sai đã được xác nhận.

Không suy “mọi tenant đều bị ảnh hưởng” chỉ từ một cặp test nếu chưa kiểm tra đường truy vấn, chính sách và các điều kiện phân vùng khác.

### 8.4. Coupon, điểm thưởng và cấp quyền sử dụng

Định nghĩa đơn vị tác động:

- Số lần dùng coupon vượt hợp đồng.
- Số điểm được cấp và khả năng quy đổi.
- Số license hoặc ngày dịch vụ được cấp ngoài quyền lợi.
- Tài nguyên bị giữ vượt quota.

Điểm thưởng không tự tương đương tiền mặt. Cần biết tỷ lệ quy đổi, hạn sử dụng, điều kiện dùng và việc thực sự sử dụng được hay chưa. Báo trước số quyền lợi đã cấp sai, rồi tách ước lượng giá trị theo giả định.

### 8.5. Transaction và lỗi giữa chừng

Thử lỗi ở ranh giới như ghi đơn, ghi outbox, gửi lệnh ngoài hoặc cập nhật kết quả.

Quan sát:

- Bản ghi nào commit và bản ghi nào rollback.
- Có tác động ngoài đã hoàn thành không.
- Trạng thái nào còn chờ xử lý hoặc cần đối soát.
- Có báo thành công khi kết quả nghiệp vụ chưa được ghi nhận đúng không.

Một HTTP 500 có thể đi kèm khoản chi đã thực hiện. Ngược lại, một lỗi unique constraint được xử lý đúng có thể là dấu hiệu cơ chế chống trùng đang hoạt động. Cần đọc kết quả cuối cùng ở nguồn phù hợp.

## 9. Định lượng tác động mà không phóng đại

### 9.1. Tách ba mức kết luận

| Mức | Ví dụ phát biểu |
|---|---|
| Đã quan sát | Trong sandbox, một retry tạo thêm khoản hoàn thành công 300.000 đồng |
| Phạm vi đã xác nhận | Tái hiện trên các fixture và cấu hình được liệt kê; actor cần sở hữu đơn |
| Ước lượng có điều kiện | Nếu có N đơn đủ điều kiện và cùng đường xử lý, kịch bản có thể tạo N lần tác động tương tự |

Không chuyển mức thứ ba thành thiệt hại đã xảy ra.

### 9.2. Tính chênh lệch với luồng chuẩn

Với một tình huống:

```text
Tác động ngoài hợp đồng
  = kết quả quan sát được - kết quả hợp lệ tương ứng
```

Đại lượng cần chọn đúng chiều và đơn vị. Ví dụ:

- Khoản hoàn thêm: tổng khoản hoàn mới thực tế trừ tổng khoản hoàn mới hợp lệ.
- Thiếu tiền thanh toán: giá trị phải thu theo hợp đồng trừ số đã thu cho phần đã thực hiện.
- Quyền lợi cấp thêm: số đơn vị thực cấp trừ số đơn vị được phép.
- Dữ liệu truy cập sai: số đối tượng hoặc thuộc tính không được phép đọc đã xác nhận.

Không dùng một công thức số học chung để thay thế ngữ nghĩa của từng miền.

### 9.3. Ước lượng phạm vi có ràng buộc

Một ước lượng kịch bản đơn giản:

```text
Giá trị tác động kịch bản
  = tác động thêm trên một trường hợp × số trường hợp khả thi
```

“Số trường hợp khả thi” cần xem:

- Số đối tượng thực sự có trạng thái và số dư phù hợp.
- Quyền actor cần có.
- Quota, hạn mức và phạm vi key.
- Cửa sổ thời gian.
- Chi phí tạo điều kiện khai thác.
- Kiểm soát của nhà cung cấp hoặc bước hậu kiểm.
- Mức độ có thể lặp lại trên đối tượng khác.

Ví dụ, 300.000 đồng nhân 20 trường hợp bằng 6.000.000 đồng chỉ là một kịch bản nếu cả 20 trường hợp đều đủ điều kiện. Một lần quan sát không chứng minh con số 20, càng không chứng minh khả năng lặp vô hạn.

### 9.4. Không cộng trùng các đại lượng chồng lấp

Trong case study:

- Khoản chi thêm 300.000 đồng là chênh lệch với luồng đúng.
- Phần vượt tổng đã thu 200.000 đồng là một ngưỡng bất biến khác.
- Giá trị đơn 1.000.000 đồng là quy mô giao dịch gốc.

Đây không phải ba khoản thiệt hại độc lập để cộng.

Tương tự, tổng giá bán, chi phí hàng hóa và khoản hoàn có thể chồng lấp tùy mô hình kế toán. Khi chưa có dữ liệu đủ rõ, báo từng đại lượng và để chủ sở hữu nghiệp vụ xác nhận cách tính.

### 9.5. Tách tác động gộp, bù trừ và tổn thất còn lại

Một khoản chi sai được thu hồi sau đó vẫn có thể đã gây tác động:

```text
Tác động gộp đã thực hiện
Khoản đã bù trừ hoặc thu hồi
Phần chưa xử lý
Thời gian và công việc phục hồi
```

Không kết luận “không có tác động” chỉ vì số dư cuối quay lại đúng sau một thao tác bù. Cần quan sát lịch sử đủ để biết tác động sai đã xảy ra và chi phí phục hồi là gì.

## 10. Đánh giá khả năng lặp, phạm vi ảnh hưởng và kiểm soát hiện có

### 10.1. Một số câu hỏi cần tách riêng

| Chiều | Câu hỏi |
|---|---|
| Điều kiện khai thác | Cần tài khoản thường, quyền nội bộ hay trạng thái đặc biệt? |
| Phạm vi đối tượng | Chỉ đơn của actor hay có thể tác động người khác? |
| Phạm vi tenant | Chỉ một tenant hay vượt phân vùng? |
| Khả năng lặp | Một lần trên đối tượng, mỗi key hay nhiều lần? |
| Tính đảo ngược | Có thể thu hồi quyền, hủy đơn hoặc đối soát không? |
| Thời điểm phát hiện | Trước thực hiện, ngay sau đó hay khi đối soát? |
| Kiểm soát giới hạn | Hạn mức, bước phê duyệt, quota hoặc nhà cung cấp có chặn tiếp không? |

Không dùng “dễ gửi request” làm bằng chứng rằng tác động kinh doanh chắc chắn cao. Cũng không coi tác động nhỏ của một fixture là giới hạn tối đa nếu fixture đã được cố ý thu nhỏ.

### 10.2. Phòng ngừa, phát hiện và bù trừ có tác dụng khác nhau

- Kiểm soát phòng ngừa ngăn chuyển trạng thái hoặc tác động trái hợp đồng.
- Kiểm soát phát hiện tạo tín hiệu để nhận biết vấn đề đã hoặc đang xảy ra.
- Kiểm soát bù trừ/khôi phục xử lý hậu quả theo thiết kế.

Một alert được gửi sau khoản hoàn trùng không làm test chống trùng pass. Có thể có kết quả riêng rằng phát hiện hoạt động nhưng phòng ngừa thất bại.

Tương tự, sự hiện diện của log chưa chứng minh có người hoặc cơ chế xử lý nó trong thời gian cần thiết. Nếu thời gian phát hiện là một phần mục tiêu test, phải có nguồn thời gian và sự kiện rõ ràng.

### 10.3. Phân loại ưu tiên theo bối cảnh

Báo cáo nên cung cấp dữ liệu cho người ra quyết định: tác động xác nhận, điều kiện, phạm vi, tính đảo ngược và kiểm soát còn lại.

Có thể dùng thang nội bộ của tổ chức. Không tự áp một ngưỡng tiền hoặc một nhãn nghiêm trọng chung cho mọi doanh nghiệp. Các vấn đề dữ liệu nhạy cảm hoặc vượt quyền quan trọng có thể cần ưu tiên cao dù chưa quy được thành tiền.

Nếu liên quan nghĩa vụ hợp đồng hoặc quy định, ghi loại nghĩa vụ cần xem xét cùng bằng chứng kỹ thuật; không tự suy mức phạt hay kết luận pháp lý từ một ca test.

## 11. Xử lý bất đồng bộ và cạnh tranh đồng thời

### 11.1. Không bỏ qua worker và callback

Một request bị từ chối có thể đã tạo message trước đó; một response thành công có thể chỉ xác nhận nhận việc. Test cần theo dõi đủ đường xử lý:

```text
API
  → transaction ứng dụng
  → outbox/job
  → worker
  → nhà cung cấp
  → callback
  → ledger/trạng thái cuối
```

Không nhất thiết mọi hệ thống có đúng các thành phần này. Chọn những ranh giới thực sự có trong thiết kế và ghi rõ phần nào đã được quan sát.

### 11.2. Retry tuần tự và yêu cầu đồng thời là hai tình huống

Hai lần gọi tuần tự có thể hoạt động đúng, trong khi hai transaction cùng đọc số còn lại vẫn vượt giới hạn.

Ví dụ:

```text
Còn có thể hoàn: 400.000
A đọc còn lại: 400.000
B đọc còn lại: 400.000
A yêu cầu hoàn: 300.000
B yêu cầu hoàn: 300.000
```

Mỗi yêu cầu riêng lẻ có vẻ hợp lệ trên bản chụp cũ. Kết quả cần bảo vệ là không cho tổng tác động mới thành 600.000 khi chỉ còn 400.000.

Test cạnh tranh nên dùng lịch điều phối hoặc transaction thật phù hợp. Quan sát số lần ghi thành công, tổng tiền thực hiện và kết quả của từng yêu cầu. Không chỉ đếm response 2xx.

### 11.3. Không suy bảo đảm từ policy thuần

Policy có thể kiểm tra đúng `requested <= remaining` nhưng cả hai yêu cầu đồng thời đều vượt qua. Cơ chế lưu phải bảo vệ điều kiện khi ghi hoặc giữ quyền thực hiện.

Kiểm thử cần xác nhận compare-and-set, khóa, uniqueness hoặc cơ chế tương ứng ở nơi nó được thực thi. Một fake trả xung đột chỉ kiểm tra cách ứng dụng xử lý kết quả đó.

## 12. Mẫu báo cáo business impact test

Một báo cáo ngắn nhưng đủ bằng chứng có thể theo cấu trúc:

```text
Tiêu đề:
  Retry cùng thao tác hoàn tiền tạo thêm khoản hoàn thành công

Mã quy tắc:
  BI-04 / không tạo tác động mới khi replay

Môi trường và phạm vi:
  Sandbox, tenant/account tổng hợp, phiên bản build và cấu hình ghi rõ

Điều kiện:
  Đơn đã thu 1.000.000, đã hoàn 600.000
  Actor sở hữu đơn, đủ điều kiện yêu cầu hoàn 300.000
  Hai request cùng phạm vi, cùng key và cùng nội dung

Kỳ vọng:
  Một khoản hoàn mới 300.000
  Retry trả kết quả đã có, không tạo tác động mới

Kết quả quan sát minh họa:
  Hai khoản hoàn mới, mỗi khoản 300.000
  Tổng đã hoàn của đơn thành 1.200.000
  Có reference và dữ liệu đối chiếu tương ứng

Tác động:
  Thêm 300.000 so với luồng hợp lệ
  Tổng hoàn vượt số đã thu 200.000
  Hai đại lượng chồng lấp, không cộng lại

Giới hạn:
  Chưa xác nhận trên production
  Chưa xác nhận số đối tượng tối đa có thể chịu ảnh hưởng
  Kết quả concurrency cần ca riêng

Bằng chứng:
  Trace tối thiểu, snapshot trước/sau, operation/provider/ledger references

Tiêu chí bản sửa:
  Retry không tăng tổng tiền hoặc số tác động
  Yêu cầu vượt số còn lại bị từ chối và không tạo tác động
  Luồng hoàn hợp lệ vẫn hoàn tất
```

Phần “kết quả quan sát” trong mẫu trên là dữ liệu tình huống minh họa của bài học, không phải báo cáo kiểm thử một hệ thống thực đã được chạy.

Một báo cáo thực tế phải phân biệt rõ điều đã đo, suy luận nguyên nhân, giả định về phạm vi và câu hỏi còn mở.

## 13. Xác nhận bản sửa bằng cùng thước đo tác động

Chỉ sửa response hoặc thêm thông báo lỗi chưa đủ. Dùng lại oracle nghiệp vụ và kiểm tra:

1. Hành động bị cấm không tạo tác động mới.
2. Dữ liệu được bảo vệ giữ nguyên khi bị từ chối.
3. Retry hợp lệ có kết quả theo hợp đồng và không nhân đôi tác động.
4. Luồng hợp lệ vẫn hoạt động.
5. Đường API, worker và callback liên quan đều sử dụng quy tắc.
6. Cạnh tranh đồng thời không vượt bất biến tổng.
7. Bằng chứng sau sửa được thu từ cùng loại nguồn như trước sửa.

Với case hoàn tiền, có thể phân bổ kiểm thử:

| Lớp | Mục tiêu |
|---|---|
| Unit test policy | Số còn lại, quyền, trạng thái và tiền điều kiện |
| Property test | Nhiều tổ hợp số tiền, lịch sử và retry theo mô hình |
| Test tích hợp lưu trữ | Transaction, uniqueness, version và rollback |
| Test tích hợp sandbox | Lệnh ngoài và kết quả nhà cung cấp |
| Test luồng xử lý | Worker/callback không tạo tác động thêm |
| Business impact regression | Tình huống từng gây lỗi không còn thay đổi kết quả ngoài hợp đồng |

Không cần nhân bản mọi chi tiết ở mọi lớp. Mỗi lớp phải bảo vệ một phần trách nhiệm rõ ràng và cùng hướng tới bất biến nghiệp vụ.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ dùng mã HTTP để kết luận | Bỏ qua tác động đã commit hoặc xử lý muộn | Đọc dữ liệu và tác động ở nguồn phù hợp |
| Hai response thành công nghĩa là hai lần mất tiền | Có thể chỉ là replay hợp lệ | Kiểm tra tác động thành công độc lập |
| Dùng tổng dashboard chung | Không nối được nguyên nhân với test | Cô lập phạm vi và correlation |
| Coi lời gọi fake là khoản chi thật | Vượt phạm vi bằng chứng | Ghi rõ lớp quan sát |
| Lấy một ca nhỏ làm giới hạn tối đa | Đánh giá thiếu phạm vi | Tách mẫu đã đo và phạm vi cần xác nhận |
| Nhân tác động với số người dùng tùy ý | Phóng đại thiệt hại | Nêu điều kiện và ràng buộc khả thi |
| Cộng các chỉ số chồng lấp | Tính trùng tác động | Báo riêng đại lượng và ý nghĩa |
| Cleanup trước khi đối soát | Mất bằng chứng hoặc che tác động | Chụp và lưu dữ liệu trước cleanup |
| Chờ sleep cố định | Có thể bỏ sót tác động bất đồng bộ | Chờ trạng thái xử lý có căn cứ |
| Chỉ sửa guard trong một endpoint | Worker hoặc đường cũ vẫn bỏ qua | Kiểm tra các đường thực hiện cùng nghiệp vụ |
| Chỉ kiểm tra từ chối | Implementation luôn chặn vẫn pass | Giữ luồng hợp lệ làm đối chứng |
| Alert hoặc bù trừ nghĩa là đã ngăn lỗi | Tác động sai vẫn có thể đã xảy ra | Đánh giá từng loại kiểm soát riêng |

## 15. Bài tập thực hành

### Bài tập 1: Sửa giá

Một đơn có giá chuẩn 500.000 đồng, client gửi tổng 5.000 đồng. Thiết kế test xác nhận số tiền dùng khi thực hiện đơn.

Nêu ít nhất ba nguồn quan sát và phân biệt trường hợp chỉ sai giao diện với trường hợp thực hiện dịch vụ khi thiếu tiền.

### Bài tập 2: Tự duyệt

Người tạo đơn có thêm role approver. Thiết kế test kiểm tra tách biệt người tạo/người duyệt và bước thực hiện sau quyết định.

Báo riêng giá trị đơn được duyệt trái thẩm quyền và giá trị đã thực hiện; không tự coi chúng là hai khoản thiệt hại độc lập.

### Bài tập 3: Hoàn tiền trùng

Dùng case study trong bài, xác định khoản hoàn thêm và phần tổng hoàn vượt số đã thu. Giải thích vì sao không cộng hai đại lượng.

Viết yêu cầu cho adapter đọc dữ liệu nhà cung cấp sao cho không nhầm số request với số khoản hoàn thành công.

### Bài tập 4: Khác tenant

Dựng hai tenant với dữ liệu tổng hợp. Chọn một thao tác đọc và một thao tác ghi để kiểm tra quyền theo đối tượng.

Nêu bằng chứng tối thiểu đủ xác nhận tác động và những điều chưa thể suy ra về toàn bộ hệ thống từ một cặp tenant.

### Bài tập 5: Hai yêu cầu tranh hạn mức

Còn được hoàn 400.000 đồng; hai yêu cầu đồng thời cùng xin 300.000 đồng. Định nghĩa kết quả chấp nhận được cho cả hai yêu cầu và cho tổng tác động.

Phân biệt kiểm tra policy thuần với kiểm tra cơ chế lưu hoặc tích hợp tạo khoản hoàn.

## 16. Tiêu chí hoàn thành một business impact test

- Giả thuyết nối được hành động, quy tắc bị vượt và hậu quả.
- Có luồng hợp lệ làm đối chứng.
- Actor, tenant, đối tượng và trạng thái đầu được xác định.
- Oracle không chỉ dựa vào response của chức năng bị nghi ngờ.
- Snapshot và tác động được tách theo đúng ý nghĩa nghiệp vụ.
- Xử lý bất đồng bộ được quan sát đến ranh giới có căn cứ.
- Đại lượng tác động có đơn vị và không bị cộng trùng.
- Kết luận tách rõ quan sát, phạm vi xác nhận và ước lượng.
- Kiểm soát phòng ngừa, phát hiện và phục hồi được đánh giá riêng.
- Phạm vi bảo đảm của fake, cơ sở dữ liệu và sandbox được ghi rõ.
- Có bằng chứng tái hiện tối thiểu và tiêu chí xác nhận bản sửa.
- Luồng hợp lệ và các đường cạnh tranh/retry liên quan được kiểm tra phù hợp.

Business impact test có giá trị khi biến một nghi vấn kỹ thuật thành bằng chứng rõ về hợp đồng nghiệp vụ bị phá vỡ. Kết quả tốt cho biết điều gì đã xảy ra, trên đối tượng nào, với tác động nào và còn giới hạn nào cần được xác nhận.
