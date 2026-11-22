# Quy tắc hồi tố và cách điều chỉnh sự kiện hoặc giao dịch đã hoàn tất

Trong Domain-Driven Design (DDD), một sự kiện hoặc giao dịch đã hoàn tất thường là một phần của lịch sử nghiệp vụ. Ví dụ: đơn hàng đã được xác nhận, hóa đơn đã phát hành, khoản thanh toán đã ghi nhận, quyền lợi thành viên đã được cấp hoặc một kỳ lương đã chốt. Sau đó doanh nghiệp có thể phát hiện dữ liệu sai, nhận được thông tin đến muộn hoặc ban hành chính sách có hiệu lực từ một thời điểm trong quá khứ.

Khi đó, hệ thống cần xử lý **quy tắc hồi tố (retroactive rule)** và điều chỉnh kết quả đã hoàn tất. Vấn đề cốt lõi là phân biệt một sự kiện đã thực sự xảy ra với thông tin được ghi nhận về sự kiện đó, xác định quy tắc có hiệu lực tại thời điểm liên quan, rồi ghi nhận thay đổi theo cách có thể giải thích và kiểm toán.

Một nguyên tắc hữu ích là giữ lại dấu vết của điều đã xảy ra và ghi nhận việc sửa chữa hoặc điều chỉnh như một hành động nghiệp vụ mới. Hệ thống có thể cập nhật trạng thái hiện hành hoặc tạo ra kết quả mới, nhưng cần giữ được ai đã thay đổi điều gì, vì sao, có hiệu lực từ khi nào và tác động đến giao dịch nào.

## 1. Quy tắc hồi tố là gì?

Một quy tắc hồi tố là quy tắc được áp dụng cho một khoảng thời gian hoặc sự kiện trong quá khứ, dù quyết định hoặc thông tin làm phát sinh quy tắc chỉ được biết ở thời điểm hiện tại.

Ví dụ:

- Cơ quan thuế công bố mức thuế mới có hiệu lực từ đầu tháng trước.
- Doanh nghiệp phát hiện một khách hàng đã đủ điều kiện thành viên từ ngày trước đó nhưng hệ thống cập nhật muộn.
- Một hóa đơn đã phát hành bị sai đơn giá do dữ liệu đầu vào không chính xác.
- Nhân viên được điều chỉnh ngày bắt đầu làm việc, ảnh hưởng đến phép năm đã tính.
- Một khoản thanh toán được báo thành công sau khi hệ thống đã timeout và đánh dấu thất bại.
- Một chính sách bảo hành được sửa đổi với hiệu lực áp dụng cho những sản phẩm đã bán trong một khoảng thời gian xác định.

Điểm chung là kết quả đã được ghi nhận trước đó có thể cần được đánh giá lại hoặc điều chỉnh.

### Hồi tố không có nghĩa là sửa lịch sử tùy ý

Cần phân biệt:

- **Thay đổi hiện tại:** quy tắc hoặc dữ liệu mới chỉ áp dụng từ bây giờ.
- **Thông tin đến muộn:** sự kiện đã xảy ra trước đó nhưng hệ thống nhận được thông tin sau.
- **Sửa sai dữ liệu:** bản ghi trước đó không phản ánh đúng sự thật đã xảy ra.
- **Điều chỉnh hồi tố:** một quyết định mới có hiệu lực với một khoảng thời gian trong quá khứ.
- **Bù trừ nghiệp vụ:** tạo giao dịch mới để đảo hoặc cân bằng tác động của giao dịch trước.

Những trường hợp này có thể dẫn đến kết quả số học giống nhau nhưng có ý nghĩa nghiệp vụ và yêu cầu audit khác nhau. Hệ thống cần biết đang xử lý loại nào.

## 2. Phân biệt thời điểm hiệu lực và thời điểm ghi nhận

Một nền tảng quan trọng để xử lý dữ liệu hồi tố là phân biệt hai trục thời gian.

**Valid time / Effective time** là thời điểm hoặc khoảng thời gian mà một sự kiện hay dữ kiện có hiệu lực trong thế giới nghiệp vụ.

**Transaction time / Recorded time** là thời điểm hệ thống ghi nhận hoặc biết đến dữ kiện đó.

Ví dụ, nhân viên thực tế bắt đầu làm việc ngày 1 tháng 3, nhưng bộ phận nhân sự nhập thông tin vào hệ thống ngày 10 tháng 3:

| Thuộc tính | Giá trị |
|---|---|
| Effective date | 01/03 |
| Recorded at | 10/03 |
| Ý nghĩa | Ngày làm việc có hiệu lực là 01/03, hệ thống chỉ biết từ 10/03 |

Nếu chỉ có một field createdAt hoặc updatedAt, hệ thống khó phân biệt thời điểm sự việc có hiệu lực với thời điểm thông tin được ghi vào database.

### Ví dụ mô hình dữ liệu

    EmploymentPeriod
      employeeId
      validFrom
      validTo
      recordedFrom
      recordedTo
      source
      reason

validFrom và validTo biểu diễn khoảng thời gian nghiệp vụ. recordedFrom và recordedTo biểu diễn khoảng thời gian hệ thống xem một phiên bản dữ liệu là thông tin đã biết.

Đây là ý tưởng của mô hình dữ liệu hai thời gian (bitemporal data). Không phải mọi domain đều cần đầy đủ bốn field này, nhưng các nghiệp vụ cần trả lời cả “điều gì đúng vào thời điểm đó?” và “lúc đó hệ thống đã biết gì?” thường cần một cách lưu tương đương.

### OccurredAt, effectiveAt và recordedAt

Với event, có thể gặp nhiều timestamp:

- occurredAt: sự kiện được cho là đã xảy ra lúc nào.
- effectiveAt: thay đổi có hiệu lực nghiệp vụ từ lúc nào.
- recordedAt: hệ thống nhận hoặc lưu thông tin lúc nào.
- processedAt: consumer xử lý thông tin lúc nào.

Các timestamp này không nhất thiết bằng nhau. Cần định nghĩa rõ ngữ nghĩa từng field thay vì dùng một timestamp chung cho mọi mục đích.

## 3. Thông tin đến muộn khác với thay đổi hồi tố

Một event đến muộn không nhất thiết là một quyết định hồi tố. Có thể sự kiện đã xảy ra đúng hạn nhưng mạng, batch hoặc hệ thống nguồn khiến thông báo tới trễ.

Ví dụ:

- Payment provider đã chấp nhận thanh toán lúc 10:00.
- Callback bị trì hoãn và tới hệ thống lúc 10:07.
- Order Service đã timeout ở 10:02 và hiển thị trạng thái đang chờ hoặc thất bại tạm thời.

Khi callback đến, hệ thống cần cập nhật theo sự thật đã xảy ra lúc 10:00. Đây là late-arriving fact. Không nên coi nó là một giao dịch thanh toán mới ở 10:07.

Ngược lại, nếu doanh nghiệp ra quyết định ngày 10 rằng một chính sách mới sẽ được áp dụng từ ngày 1, đó là thay đổi quy tắc có hiệu lực hồi tố.

| Tình huống | Effective time | Recorded time | Bản chất |
|---|---|---|---|
| Callback thanh toán đến trễ | Thời điểm provider xử lý | Thời điểm callback được nhận | Late-arriving fact |
| Nhập ngày bắt đầu làm việc muộn | Ngày nhân viên thực tế bắt đầu | Ngày HR nhập | Late-arriving fact hoặc correction |
| Chính sách thuế ban hành ngày 10, hiệu lực ngày 1 | Ngày 1 | Ngày 10 | Retroactive policy |
| Sửa đơn giá bị nhập sai | Thời điểm giao dịch gốc hoặc thời điểm hiệu lực được xác định | Thời điểm sửa | Correction |
| Hoàn tiền sau khi thu tiền | Thời điểm hoàn tiền | Thời điểm ghi nhận hoàn tiền | New compensating transaction |

Phân biệt đúng giúp hệ thống giữ timestamp nghiệp vụ và không vô tình làm sai báo cáo thời gian.

## 4. Sự kiện đã hoàn tất cần được bảo toàn như thế nào?

Một giao dịch đã hoàn tất có thể đã tạo ra nhiều hệ quả:

- Hóa đơn đã gửi cho khách hàng.
- Tiền đã được chuyển hoặc ghi sổ.
- Hàng đã được giao.
- Điểm thành viên đã được cộng.
- Báo cáo kỳ đã được chốt.
- Một context khác đã nhận integration event và cập nhật dữ liệu.

Nếu sửa trực tiếp bản ghi cũ, hệ thống có thể mất bằng chứng về điều đã xảy ra và không giải thích được vì sao báo cáo trước đó khác báo cáo hiện tại.

Một thiết kế có khả năng audit thường giữ:

1. Sự kiện hoặc giao dịch gốc.
2. Thông tin xác định bản ghi nào cần sửa.
3. Giá trị cũ và giá trị mới hoặc phần chênh lệch.
4. Lý do và căn cứ điều chỉnh.
5. Người hoặc quy trình khởi tạo.
6. Thời điểm hiệu lực và thời điểm ghi nhận.
7. Liên kết tới giao dịch gốc.
8. Kết quả và các event phát sinh từ việc điều chỉnh.

Điều này không bắt buộc mọi bảng phải append-only. Một số dữ liệu hiện hành vẫn có thể được cập nhật. Nhưng đối với các sự kiện có ý nghĩa lịch sử hoặc tài chính, cần có lịch sử thay đổi hoặc bản ghi điều chỉnh đủ để tái dựng và giải thích.

## 5. Phân biệt Correction, Adjustment và Compensation

Ba cách xử lý thường gặp có mục đích khác nhau.

### Correction — sửa thông tin sai

Correction được dùng khi dữ liệu đã ghi nhận không đúng với sự thật hoặc thông tin có thẩm quyền.

Ví dụ: hóa đơn ghi nhầm mã số thuế khách hàng; ngày bắt đầu hợp đồng nhập sai; địa chỉ được ghi sai do lỗi mapping.

Correction cần chỉ ra bản ghi nào sai và giá trị đúng là gì. Tùy domain, hệ thống có thể tạo phiên bản mới, ghi correction record hoặc phát hành chứng từ sửa đổi.

### Adjustment — điều chỉnh kết quả

Adjustment được dùng khi cần ghi nhận phần chênh lệch hoặc một thay đổi nghiệp vụ bổ sung sau giao dịch gốc.

Ví dụ:

- Hóa đơn bổ sung khoản phí còn thiếu.
- Tính thêm hoặc hoàn lại chênh lệch giá.
- Điều chỉnh số dư do chính sách có hiệu lực hồi tố.
- Ghi nhận phần lương chênh lệch cho kỳ đã chốt.

Giao dịch gốc vẫn giữ nguyên; adjustment liên kết với giao dịch gốc và biểu diễn phần thay đổi.

### Compensation — hành động bù trừ

Compensation là một hành động nghiệp vụ mới để đảo hoặc cân bằng tác động của hành động trước đó.

Ví dụ:

- Refund để hoàn lại khoản đã thu.
- Release reservation để giải phóng hàng đã giữ.
- Credit note để giảm nghĩa vụ thanh toán.
- Reversal entry để đảo một bút toán.

Compensation không xóa việc hành động trước đã xảy ra. Nó ghi nhận một hành động khác có quan hệ với hành động ban đầu.

| Câu hỏi | Correction | Adjustment | Compensation |
|---|---|---|---|
| Vấn đề | Dữ liệu hoặc ghi nhận sai | Kết quả cần thay đổi/bổ sung | Tác động trước cần được đảo hoặc cân bằng |
| Bản ghi gốc | Giữ lịch sử và đánh dấu đã được sửa/thay thế theo domain | Giữ nguyên | Giữ nguyên |
| Bản ghi mới | Correction/version record | Adjustment transaction | Reversal/refund/compensation transaction |
| Ví dụ | Sửa ngày hiệu lực nhập sai | Ghi khoản chênh lệch phí | Hoàn tiền đã thu |
| Ý nghĩa | Xác lập thông tin đúng | Ghi phần điều chỉnh | Ghi hành động bù trừ |

Không nên chọn cách xử lý chỉ dựa trên kỹ thuật dễ làm. Ngữ nghĩa nghiệp vụ và yêu cầu pháp lý/kế toán quyết định loại bản ghi cần tạo.

## 6. Khi nào được cập nhật bản ghi, khi nào cần ghi thêm sự kiện?

Không phải mọi dữ liệu đều cần append-only. Một hồ sơ khách hàng có thể cho phép cập nhật tên hiển thị hiện tại, trong khi hóa đơn đã phát hành cần giữ dấu vết và tuân thủ quy trình điều chỉnh riêng.

Có thể dùng các tiêu chí sau:

- Dữ liệu có đại diện cho một sự kiện đã xảy ra không?
- Có nghĩa vụ audit hoặc đối soát không?
- Có hệ thống khác đã tiêu thụ dữ liệu đó không?
- Việc sửa có làm thay đổi ý nghĩa của báo cáo lịch sử không?
- Có chứng từ hoặc bút toán liên quan không?
- Có cần tái dựng trạng thái tại một thời điểm quá khứ không?

Nếu đó là một fact lịch sử quan trọng, hãy cân nhắc ghi thêm correction/adjustment event và giữ fact gốc. Nếu đó là dữ liệu mô tả hiện hành, cập nhật phiên bản mới có thể phù hợp miễn là lịch sử cần thiết vẫn được lưu.

### Ví dụ: hồ sơ khách hàng và hóa đơn

- Customer Profile: tên hiển thị có thể được cập nhật; nếu cần audit, lưu lịch sử phiên bản.
- Issued Invoice: không nên âm thầm sửa số tiền hoặc thông tin đã phát hành; domain có thể cần credit note, debit note hoặc chứng từ thay thế theo quy trình.
- Order Draft: có thể sửa trực tiếp khi đơn chưa được xác nhận.
- Completed Order: thay đổi có thể cần một use case điều chỉnh hoặc hủy riêng.

Ranh giới này cần được xác định trong domain model và policy, không nên để một endpoint generic update quyết định.

## 7. Xác định quy tắc nào có hiệu lực tại thời điểm nào

Khi chính sách thay đổi, hệ thống phải xác định quy tắc áp dụng cho một sự kiện quá khứ.

Ví dụ, chính sách phí giao hàng:

- Policy version 1 có hiệu lực từ ngày 1 đến ngày 14.
- Policy version 2 được ban hành ngày 10 nhưng có hiệu lực từ ngày 8.
- Đơn đặt ngày 6 đã được tính theo version 1.
- Đơn đặt ngày 9 có thể cần được đánh giá lại theo version 2 nếu chính sách quy định áp dụng hồi tố.

Cần phân biệt:

- ngày chính sách được công bố;
- ngày chính sách có hiệu lực;
- ngày hệ thống cập nhật policy;
- giao dịch nào nằm trong phạm vi áp dụng;
- có điều khoản chuyển tiếp hay ngoại lệ không.

Không nên mặc định mọi policy mới đều áp dụng cho mọi giao dịch cũ. Domain expert phải xác định phạm vi, ngày hiệu lực, ngoại lệ và cách xử lý giao dịch đã hoàn tất.

### Lưu policy version khi ra quyết định

Một quyết định quan trọng nên lưu dấu vết quy tắc đã dùng:

    PricingDecision
      orderId
      quotedAmount
      currency
      policyId
      policyVersion
      effectiveAt
      decidedAt

Khi cần kiểm toán, hệ thống có thể giải thích giá ban đầu được tính theo policy version nào và quyết định điều chỉnh sau này dựa trên policy nào.

Nếu policy được lưu dưới dạng cấu hình mutable mà không có version, việc tái dựng quyết định cũ có thể không còn chính xác.

## 8. Mô hình hóa thời gian hai chiều (Bitemporal)

Trong một số domain, chỉ lưu effectiveAt và recordedAt chưa đủ. Cần biết một fact có hiệu lực trong khoảng nào và hệ thống xem phiên bản fact đó là đúng trong khoảng thời gian nào.

Ví dụ:

| Phiên bản | Valid from | Valid to | Recorded from | Recorded to |
|---|---|---|---|---|
| Địa chỉ A | 01/01 | 01/04 | 01/01 | vô hạn |
| Địa chỉ B | 01/04 | vô hạn | 12/04 | 20/04 |
| Địa chỉ C (sửa hồi tố) | 01/04 | vô hạn | 20/04 | vô hạn |

Ví dụ này cần được hiểu như các phiên bản temporal của cùng một fact: ngày 12/04 hệ thống tin địa chỉ B có hiệu lực từ 01/04; đến 20/04 phát hiện thông tin đó sai và sửa thành địa chỉ C, cũng có hiệu lực từ 01/04.

Truy vấn hai thời gian có thể trả lời:

- Địa chỉ nào có hiệu lực vào ngày 05/04 theo hiểu biết hiện tại?
- Vào ngày 15/04, hệ thống đã tin địa chỉ nào có hiệu lực ngày 05/04?
- Ngày nào hệ thống nhận được correction?
- Correction thay thế phiên bản nào?

Bitemporal modeling hữu ích trong bảo hiểm, nhân sự, thuế, hợp đồng, tín dụng và các domain cần giải thích lịch sử tri thức của hệ thống. Nó làm tăng độ phức tạp nên không cần áp dụng cho mọi bảng.

## 9. Quy tắc hiệu lực theo khoảng thời gian

Nhiều chính sách không áp dụng tại một thời điểm đơn lẻ mà áp dụng cho một khoảng:

- hợp đồng có hiệu lực từ ngày A đến ngày B;
- thành viên thuộc hạng Gold trong một giai đoạn;
- mức thuế áp dụng cho các hóa đơn trong kỳ;
- phí bảo hiểm thay đổi theo ngày bắt đầu hiệu lực;
- quyền lợi được tính theo thời gian làm việc.

Cần xác định quy ước biên rõ ràng. Một cách phổ biến là dùng khoảng nửa mở [validFrom, validTo), nghĩa là validFrom được tính nhưng validTo không được tính. Hai khoảng liên tiếp có thể nối nhau mà không chồng lấn.

Ví dụ:

    Period A: [2026-01-01, 2026-04-01)
    Period B: [2026-04-01, 2026-07-01)

Ngày 01/04 thuộc Period B. Quy ước này giúp tránh khoảng trống hoặc chồng lấn do hai đầu đều inclusive.

Nếu domain dùng ngày lịch, cần thống nhất timezone nghiệp vụ. Nếu dùng Instant, phải xác định chính xác thời điểm UTC. Không tự chuyển LocalDate thành Instant khi chưa có timezone.

## 10. Quy trình xử lý một yêu cầu hồi tố

Một yêu cầu điều chỉnh nên đi qua một use case riêng, thay vì một lệnh update tổng quát.

Quy trình gợi ý:

1. Nhận yêu cầu điều chỉnh và định danh giao dịch gốc.
2. Xác thực người hoặc vai trò được phép yêu cầu.
3. Xác định loại xử lý: correction, adjustment hay compensation.
4. Xác định effective date hoặc khoảng thời gian bị ảnh hưởng.
5. Thu thập căn cứ, lý do và tài liệu tham chiếu.
6. Xác định policy version và phạm vi giao dịch cần đánh giá.
7. Tính lại kết quả hoặc phần chênh lệch.
8. Kiểm tra trạng thái hiện tại và concurrency.
9. Ghi adjustment/correction transaction liên kết với bản gốc.
10. Phát event và cập nhật các projection liên quan.
11. Trả kết quả, mã tham chiếu và trạng thái xử lý.

Không phải yêu cầu nào cũng được tự động chấp thuận. Một số điều chỉnh có thể cần phê duyệt, hai người kiểm soát hoặc quy trình thủ công.

### Command riêng cho nghiệp vụ điều chỉnh

Ví dụ:

    CorrectEmploymentStartDateCommand
    AdjustInvoiceAmountCommand
    RefundPaymentCommand
    RecalculateMembershipBenefitsCommand

Tên command thể hiện ý định và loại thay đổi. Nó giúp authorization, audit và workflow có thể khác nhau theo từng loại.

## 11. Ví dụ: điều chỉnh hóa đơn đã phát hành

Giả sử một hóa đơn đã phát hành với tổng tiền 1.000.000 VND. Sau đó phát hiện phí dịch vụ bị tính thiếu 100.000 VND.

Không nên âm thầm đổi tổng tiền hóa đơn cũ thành 1.100.000 nếu hóa đơn đã phát hành và cần giữ lịch sử. Tùy quy định và quy trình doanh nghiệp, hệ thống có thể tạo chứng từ điều chỉnh tăng 100.000 hoặc phát hành hóa đơn thay thế.

Mô hình khái niệm:

    Invoice
      invoiceId
      issuedAt
      originalTotal
      status = ISSUED

    InvoiceAdjustment
      adjustmentId
      originalInvoiceId
      amountDelta = +100000
      reason
      effectiveAt
      recordedAt
      approvedBy

Lịch sử cho phép giải thích:

- Hóa đơn ban đầu được phát hành với số tiền nào.
- Điều chỉnh phát sinh vì lý do gì.
- Số tiền tăng thêm là bao nhiêu.
- Ai phê duyệt và khi nào.
- Số tiền phải thu hiện tại được tính như thế nào.

Cách phát hành chứng từ cụ thể phải tuân theo quy định tài chính và chính sách của doanh nghiệp. Mô hình DDD cần biểu diễn đúng các khái niệm chứng từ mà nghiệp vụ yêu cầu.

### Không sửa tổng tiền gốc để làm báo cáo hiện tại đúng

Một báo cáo có thể tính số tiền phải thu hiện tại bằng tổng hóa đơn gốc cộng các adjustment hợp lệ:

    outstandingAmount =
        invoice.originalTotal
        + sum(approvedAdjustments)
        - sum(allocatedPayments)

Báo cáo lịch sử tại thời điểm trước adjustment vẫn có thể tái dựng được.

## 12. Ví dụ: hoàn tiền và bù trừ thanh toán

Một khoản thanh toán đã được provider xác nhận thành công. Sau đó khách hàng được duyệt hoàn 200.000 VND.

Refund là một hành động mới, không phải xóa payment gốc:

    PaymentCaptured
      paymentId
      amount = 500000
      capturedAt

    RefundIssued
      refundId
      originalPaymentId
      amount = 200000
      reason
      issuedAt

Số tiền đã hoàn có thể được tính từ các refund đã thành công. Payment gốc vẫn là bằng chứng rằng 500.000 VND từng được thu.

Nếu provider timeout trong lúc refund, hệ thống cần idempotency key và đối soát trạng thái với provider. Không được tạo refund mới chỉ vì client không nhận được response.

Nếu refund bị từ chối, đó là một kết quả của quy trình refund; không được ghi như thể tiền đã hoàn.

## 13. Event Sourcing và sự kiện điều chỉnh

Trong Event Sourcing, trạng thái Aggregate được dựng từ chuỗi event. Lịch sử event là nguồn để tái dựng state, vì vậy sửa event cũ trực tiếp thường phá vỡ ý nghĩa append-only và khả năng audit.

Có thể ghi thêm event thể hiện correction hoặc compensation:

    InvoiceIssued
    InvoiceAmountCorrected
    InvoiceAdjustmentApproved
    RefundIssued

Hoặc với event sourcing, event mới có thể biểu diễn việc một fact trước đó bị thay thế:

    EmploymentStartDateRecorded
    EmploymentStartDateCorrected

Projection cần hiểu semantics của event correction để cập nhật state hiện hành. Khi replay, cùng một chuỗi event phải tái dựng được trạng thái theo quy tắc đã định.

### Correction event cần tham chiếu điều gì?

Một correction event nên có đủ thông tin:

- Identity của fact hoặc event bị sửa.
- Giá trị cũ hoặc version bị thay thế.
- Giá trị mới.
- Effective time.
- Recorded time.
- Reason code.
- Actor hoặc workflow thực hiện.
- Correlation/causation ID.

Không phải lúc nào cũng cần nhúng toàn bộ payload cũ và mới. Cần cân bằng khả năng audit với bảo vệ dữ liệu nhạy cảm.

### Projection và báo cáo lịch sử

Có thể cần nhiều projection:

- Current state: trạng thái hiện hành sau tất cả correction.
- As-of valid time: dữ liệu có hiệu lực tại một ngày.
- As-known-at time: dữ liệu mà hệ thống đã biết tại một thời điểm.
- Financial ledger: các bút toán gốc và điều chỉnh.
- Audit view: ai đã sửa, vì sao và khi nào.

Không nên giả định một bảng trạng thái hiện tại đủ đáp ứng mọi câu hỏi lịch sử.

## 14. Điều chỉnh trong sổ cái và nghiệp vụ tài chính

Trong accounting, bút toán đã ghi sổ thường không được xóa hoặc sửa âm thầm. Sai sót được xử lý bằng bút toán điều chỉnh hoặc bút toán đảo, tuân theo nguyên tắc và quy định kế toán áp dụng.

Ví dụ:

- Bút toán gốc ghi nhận doanh thu 1.000.000.
- Phát hiện doanh thu cần giảm 100.000.
- Ghi bút toán điều chỉnh giảm 100.000, liên kết với bút toán gốc và kỳ có liên quan.

Mô hình ledger nên giữ:

- Journal entry ID.
- Account.
- Debit/credit.
- Currency.
- Effective date hoặc accounting date.
- PostedAt.
- Source transaction reference.
- Adjustment/reversal reference.
- Reason và approval reference.

Tổng debit và credit phải cân bằng theo quy tắc ledger. Điều chỉnh một bút toán không có nghĩa sửa lại lịch sử giao dịch gốc.

Đây là ví dụ khái niệm, không thay thế hướng dẫn kế toán hoặc quy định pháp lý cho từng loại chứng từ.

## 15. Khi điều chỉnh ảnh hưởng đến nhiều Bounded Context

Một correction có thể tác động đến nhiều context.

Ví dụ, ngày bắt đầu hợp đồng của khách hàng được sửa hồi tố:

- Customer Management cập nhật lịch sử hợp đồng.
- Billing tính lại phí.
- Entitlement cập nhật quyền lợi.
- Reporting cập nhật số liệu.
- Notification có thể cần thông báo cho người liên quan.

Không nên cố gắng giữ một database transaction mở qua tất cả context. Mỗi context xử lý một local transaction và phát event hoặc kết quả cho process manager.

    ContractEffectiveDateCorrected
              |
              v
       Retroactive Adjustment Process
          /       |        \
         v        v         v
      Billing  Entitlement Reporting
         |        |         |
         v        v         v
      result    result     result
          \       |        /
           v      v       v
          Adjustment Completed / Needs Review

Process Manager theo dõi các bước, retry, deadline và kết quả. Nếu một bước thất bại, quy trình có thể tiếp tục sau hoặc chuyển sang xử lý thủ công. Compensation chỉ được thực hiện nếu nghiệp vụ xác định cần và có hành động bù trừ tương ứng.

### Trạng thái của quy trình điều chỉnh

Một workflow có thể có các trạng thái:

    REQUESTED
       -> VALIDATING
       -> APPROVED
       -> APPLYING
       -> COMPLETED

Các nhánh khác:

    VALIDATING -> REJECTED
    APPLYING -> PARTIALLY_APPLIED
    PARTIALLY_APPLIED -> RETRYING
    PARTIALLY_APPLIED -> MANUAL_REVIEW

Không nên đánh dấu hoàn tất khi chỉ một context đã cập nhật. Cần xác định rõ điều kiện hoàn tất của toàn bộ adjustment process.

## 16. Tính toán lại kết quả đã hoàn tất

Một thay đổi hồi tố có thể yêu cầu tính lại nhiều kết quả phụ thuộc.

Ví dụ, điều chỉnh ngày bắt đầu làm việc có thể ảnh hưởng:

- Số ngày phép được tích lũy.
- Thâm niên.
- Mức thưởng.
- Phụ cấp.
- Quyền lợi bảo hiểm.

Cần xác định các kết quả nào là derived data có thể tái tính, và kết quả nào là quyết định hoặc giao dịch đã được chốt cần adjustment riêng.

### Phân biệt dữ liệu dẫn xuất và giao dịch đã ghi nhận

- Projection hoặc report total thường có thể được rebuild từ facts và adjustment.
- Invoice đã phát hành thường cần chứng từ điều chỉnh theo nghiệp vụ.
- Payment đã capture cần refund/reversal qua provider.
- Entitlement hiện tại có thể được tính lại nhưng quyền lợi đã sử dụng có thể cần xử lý riêng.

Không nên xóa mọi kết quả cũ rồi tính lại nếu điều đó làm mất bằng chứng về quyết định đã từng được thực hiện.

### Dependency graph

Khi tính lại, cần biết dữ liệu nào phụ thuộc vào fact được sửa:

    Employment Start Date
          |
          +--> Tenure
          |      +--> Bonus eligibility
          |
          +--> Leave accrual
          |
          +--> Insurance coverage

Dependency graph giúp xác định phạm vi ảnh hưởng và thứ tự xử lý. Với hệ thống lớn, có thể dùng event hoặc workflow để lan truyền thay đổi và theo dõi kết quả từng bước.

## 17. Quyền hạn, phê duyệt và kiểm soát điều chỉnh

Điều chỉnh hồi tố có thể ảnh hưởng tiền, quyền lợi hoặc báo cáo pháp lý. Không phải mọi người dùng đều được quyền thực hiện.

Một policy có thể yêu cầu:

- Người yêu cầu có quyền trên loại giao dịch.
- Lý do điều chỉnh là bắt buộc.
- Tài liệu chứng minh phải được đính kèm hoặc tham chiếu.
- Mức điều chỉnh vượt ngưỡng cần người thứ hai phê duyệt.
- Không cho phép người tạo tự phê duyệt.
- Ghi nhận actor, approver và thời điểm.
- Không cho sửa lại adjustment đã hoàn tất nếu chưa tạo quy trình correction tiếp theo.

Các quy tắc này có thể nằm trong Application Policy hoặc domain policy tùy ngữ nghĩa. Aggregate cần bảo vệ các chuyển trạng thái quan trọng như approve, reject, apply và complete.

### Phân biệt người yêu cầu, người phê duyệt và người thực thi

Một adjustment có thể do người dùng yêu cầu, người quản lý phê duyệt và một worker tự động thực thi. Audit cần giữ riêng các danh tính đó thay vì chỉ có một field updatedBy.

## 18. Concurrency và idempotency khi điều chỉnh

Hai yêu cầu điều chỉnh có thể cùng nhắm vào một giao dịch gốc. Nếu cả hai đọc cùng state và áp dụng đồng thời, hệ thống có thể tính sai số chênh lệch hoặc vượt giới hạn.

Cần cân nhắc:

- Optimistic locking trên Aggregate hoặc adjustment target.
- Unique constraint cho external reference hoặc idempotency key.
- Quy tắc một adjustment loại nào được áp dụng một lần.
- Re-evaluation khi version thay đổi.
- Khóa hoặc serialize theo invoice/payment/contract nếu cần.
- Không retry trên dữ liệu cũ.

Ví dụ, hai request cùng hoàn 200.000 VND từ một payment 300.000 VND. Nếu không kiểm tra tổng refund đã thành công, hệ thống có thể chấp nhận hoàn 400.000 VND.

Một invariant có thể là:

    totalSuccessfulRefunds(paymentId) <= capturedAmount(paymentId)

Invariant cần được bảo vệ tại nơi sở hữu Payment hoặc Refund aggregate bằng transaction/concurrency control phù hợp.

Idempotency key ngăn cùng một yêu cầu bị thực hiện lặp do timeout. Nó không tự giải quyết hai yêu cầu khác nhau nhưng cùng vượt quá giới hạn; domain vẫn phải kiểm tra invariant.

## 19. Phát event và cập nhật projection sau điều chỉnh

Khi correction hoặc adjustment được commit, các context khác có thể cần nhận thông tin.

Một event nên diễn đạt điều đã xảy ra:

    InvoiceAdjusted
    PaymentRefunded
    ContractEffectiveDateCorrected
    MembershipEligibilityRecalculated

Event có thể mang:

- Event ID.
- Aggregate ID.
- Adjustment ID.
- Original transaction reference.
- Effective time.
- Recorded time.
- Adjustment type.
- Amount delta hoặc state version.
- Reason code nếu được phép chia sẻ.

Ghi event vào outbox cùng transaction với adjustment để tránh trạng thái đã commit nhưng không có thông điệp cần phát.

Consumer cần idempotency, version và cơ chế xử lý event đến trễ. Nếu event chỉ là thông báo thay đổi, consumer có thể tải lại trạng thái hiện hành. Nếu event mang delta, consumer cần xử lý sequence/gap đúng cách.

## 20. Bảo toàn khả năng giải thích và kiểm toán

Một điều chỉnh hoàn tất cần trả lời được:

- Giao dịch nào bị ảnh hưởng?
- Thông tin nào được xem là sai hoặc đã thay đổi?
- Điều gì có hiệu lực từ ngày nào?
- Hệ thống ghi nhận điều chỉnh lúc nào?
- Quy tắc hoặc policy version nào được áp dụng?
- Ai yêu cầu và ai phê duyệt?
- Phần chênh lệch được tính như thế nào?
- Context nào đã xử lý xong?
- Có bước nào thất bại hoặc đang chờ?
- Bản ghi gốc và điều chỉnh liên kết ra sao?

Một audit record có thể gồm:

    AdjustmentAudit
      adjustmentId
      targetType
      targetId
      originalVersion
      newVersion
      effectiveAt
      recordedAt
      reasonCode
      requestedBy
      approvedBy
      correlationId

Không nên chỉ ghi một chuỗi tự do như “sửa dữ liệu” mà không có target, lý do và tham chiếu. Reason code ổn định giúp báo cáo và kiểm soát, còn phần diễn giải có thể bổ sung chi tiết.

## 21. API và giao diện cho yêu cầu hồi tố

Một API điều chỉnh nên thể hiện rõ đây là use case đặc biệt. Tránh dùng endpoint generic PUT để thay thế toàn bộ trạng thái giao dịch đã hoàn tất.

Ví dụ:

    POST /api/invoices/{invoiceId}/adjustments

    {
      "type": "INCREASE",
      "amount": "100000",
      "currency": "VND",
      "effectiveAt": "2026-03-01",
      "reasonCode": "SERVICE_FEE_OMITTED",
      "reference": "CASE-4821"
    }

API cần:

- Xác thực actor và quyền điều chỉnh.
- Validate cấu trúc request.
- Chuẩn hóa amount, currency và effective date.
- Tạo command riêng.
- Xác định transaction gốc và policy áp dụng.
- Yêu cầu phê duyệt nếu cần.
- Trả adjustment ID và trạng thái workflow.
- Cung cấp endpoint tra cứu lịch sử và trạng thái xử lý.

Với quy trình nhiều context, API có thể trả 202 Accepted cùng adjustment ID nếu yêu cầu đã được tiếp nhận nhưng chưa hoàn tất. Client có thể truy vấn trạng thái workflow thay vì giả định mọi context đã cập nhật đồng bộ.

## 22. Kiểm thử quy tắc hồi tố

Kiểm thử cần bao phủ cả thời gian, lịch sử và tác động của adjustment.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Fact được ghi nhận đúng thời điểm | Effective time và recorded time phù hợp |
| Fact có hiệu lực quá khứ nhưng được nhập muộn | Giữ cả hai thời điểm |
| Correction thay thế một phiên bản fact | Lịch sử phiên bản cũ vẫn truy vấn được |
| Adjustment tăng/giảm giá trị | Giao dịch gốc không bị mất |
| Refund vượt số tiền đã capture | Bị từ chối |
| Hai adjustment cạnh tranh | Concurrency control ngăn áp dụng vượt giới hạn |
| Request lặp cùng idempotency key | Không tạo adjustment trùng |
| Policy mới có hiệu lực hồi tố | Chỉ giao dịch thuộc phạm vi được đánh giá |
| Event adjustment được giao lặp | Consumer không áp dụng hai lần |
| Một context xử lý thất bại | Workflow ghi nhận trạng thái chưa hoàn tất và có thể retry |
| Query as-of | Trả kết quả theo đúng valid time và recorded time |

### Test thời điểm biên

Nếu policy có hiệu lực từ 01/04, cần test:

- 31/03 23:59:59 theo timezone nghiệp vụ.
- 01/04 00:00:00.
- Thời điểm kết thúc policy.
- Giao dịch được ghi muộn nhưng effectiveAt nằm trong khoảng.

Không dùng clock hệ thống trực tiếp trong domain test. Truyền thời điểm đánh giá hoặc dùng Clock abstraction để test có thể lặp lại.

## 23. Những sai lầm thường gặp

### Sửa trực tiếp giao dịch đã hoàn tất

Làm mất dấu vết về điều đã xảy ra và khó đối soát với chứng từ hoặc hệ thống ngoài.

### Dùng updatedAt thay cho effectiveAt

Không thể phân biệt sự kiện có hiệu lực từ khi nào với lúc hệ thống cập nhật dữ liệu.

### Áp dụng policy mới cho toàn bộ quá khứ

Không kiểm tra phạm vi, ngày hiệu lực, điều khoản chuyển tiếp hoặc ngoại lệ.

### Nhầm late-arriving event với retroactive decision

Event đến trễ có thể chỉ là thông tin về sự kiện đã xảy ra. Không nên tạo giao dịch mới ở thời điểm nhận event.

### Dùng compensation để che lỗi dữ liệu

Refund hoặc reversal không thay thế việc correction fact sai. Chọn loại hành động theo nguyên nhân và ngữ nghĩa nghiệp vụ.

### Rebuild projection rồi coi lịch sử đã được sửa

Projection hiện tại có thể được dựng lại, nhưng hóa đơn, payment hoặc quyết định đã phát hành vẫn cần adjustment theo quy trình riêng.

### Không lưu policy version

Sau khi cấu hình thay đổi, hệ thống không thể giải thích vì sao quyết định cũ được đưa ra.

### Cho phép adjustment không có lý do hoặc phê duyệt

Khó kiểm soát gian lận, audit và trách nhiệm.

### Không xử lý adjustment trùng hoặc đồng thời

Có thể hoàn tiền quá mức, ghi nhận chênh lệch nhiều lần hoặc tạo số dư sai.

### Đánh dấu workflow hoàn tất quá sớm

Một context đã xử lý không có nghĩa toàn bộ các context liên quan đã cập nhật.

### Xem rollback như cách đảo giao dịch bên ngoài

Rollback database không thu hồi payment, email, shipment hoặc message đã phát. Cần hành động bù trừ có ý nghĩa nghiệp vụ.

## 24. Quy trình thiết kế một cơ chế điều chỉnh

Khi thiết kế một use case hồi tố, có thể đi theo trình tự:

1. **Xác định sự thật gốc:** sự kiện nào đã xảy ra và giao dịch nào đã hoàn tất?
2. **Phân loại yêu cầu:** late-arriving fact, correction, policy change, adjustment hay compensation?
3. **Xác định thời gian:** occurredAt, effectiveAt, recordedAt và khoảng thời gian bị ảnh hưởng.
4. **Xác định ownership:** Bounded Context nào sở hữu fact hoặc invariant?
5. **Xác định policy:** version nào áp dụng, có ngoại lệ hoặc approval không?
6. **Xác định phạm vi:** một Aggregate, nhiều Aggregate hay nhiều context?
7. **Tính phần thay đổi:** kết quả mới, delta hoặc hành động bù trừ.
8. **Bảo vệ concurrency:** version, idempotency key và invariant.
9. **Ghi lịch sử:** liên kết bản gốc, adjustment, reason, actor và approver.
10. **Điều phối tác động:** outbox, event, process manager hoặc saga.
11. **Theo dõi hoàn tất:** trạng thái từng bước và kết quả cuối.
12. **Đối soát và kiểm thử:** báo cáo as-of, audit, duplicate, retry và lỗi một phần.

## 25. Checklist quy tắc hồi tố

Trước khi cho phép điều chỉnh một giao dịch đã hoàn tất, hãy kiểm tra:

- Sự kiện gốc và identity của nó đã được xác định chưa?
- Đây là thông tin đến muộn, correction, adjustment hay compensation?
- Effective time có tách khỏi recorded time không?
- Khoảng thời gian và quy tắc biên đã rõ chưa?
- Policy version và phạm vi áp dụng đã xác định chưa?
- Giao dịch gốc có được bảo toàn và liên kết với adjustment không?
- Có lý do, căn cứ và actor rõ ràng không?
- Có cần approval hoặc kiểm soát hai người không?
- Adjustment có thể vượt giới hạn do request lặp hoặc cạnh tranh không?
- Idempotency và optimistic/pessimistic concurrency đã được thiết kế chưa?
- Có external side effect cần compensation hoặc đối soát không?
- Các context phụ thuộc có nhận được event sau commit không?
- Workflow có theo dõi trạng thái xử lý từng context không?
- Projection và báo cáo có thể tái dựng theo thời điểm không?
- Có retention, privacy và audit policy phù hợp không?
- Có test thời điểm biên, late event, correction và partial failure không?

## 26. Kết luận

Quy tắc hồi tố cho phép doanh nghiệp áp dụng thông tin hoặc chính sách mới cho một khoảng thời gian trong quá khứ, nhưng không nên làm mất dấu vết của những gì đã thực sự xảy ra. Muốn xử lý đúng, hệ thống cần phân biệt thời điểm hiệu lực với thời điểm ghi nhận, thông tin đến muộn với quyết định hồi tố, và correction với adjustment hoặc compensation.

Trong DDD, hãy biểu diễn điều chỉnh thành use case có tên, có quyền hạn và có quy tắc riêng. Giữ liên kết tới giao dịch gốc, lưu lý do và policy version, bảo vệ concurrency và idempotency, rồi điều phối các tác động tới context khác bằng event hoặc workflow phù hợp. Với dữ liệu cần giải thích lịch sử tri thức, mô hình hai thời gian có thể giúp truy vấn cả điều gì có hiệu lực và hệ thống đã biết gì ở từng thời điểm.

Cách tiếp cận này giúp lịch sử nghiệp vụ có thể kiểm toán, kết quả hiện tại có thể được điều chỉnh có kiểm soát và các bounded context vẫn giữ quyền sở hữu đối với dữ liệu cùng invariant của mình.
