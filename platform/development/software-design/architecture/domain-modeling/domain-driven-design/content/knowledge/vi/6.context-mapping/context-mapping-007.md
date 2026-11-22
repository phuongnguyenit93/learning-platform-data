# Anti-Corruption Layer: bảo vệ mô hình bằng lớp chuyển đổi

Trong một hệ thống doanh nghiệp, một bounded context thường phải trao đổi với hệ thống cũ, dịch vụ của nhà cung cấp hoặc một bounded context khác. Các hệ thống này có thể dùng thuật ngữ, cấu trúc dữ liệu và quy tắc khác với mô hình mà nhóm đang xây dựng. Nếu để mô hình bên ngoài đi thẳng vào bên trong, các khái niệm và cách tổ chức của hệ thống kia dần xuất hiện trong mã nguồn của context hiện tại. Theo thời gian, mô hình nội bộ trở nên khó hiểu, khó thay đổi và phụ thuộc vào những quyết định mà nhóm không kiểm soát.

Domain-Driven Design (DDD) sử dụng **Anti-Corruption Layer (ACL, lớp chống ăn mòn)** để bảo vệ mô hình của một bounded context trước ảnh hưởng từ mô hình bên ngoài. ACL nằm tại ranh giới tích hợp, diễn giải thông tin của hệ thống đối tác và chuyển nó thành khái niệm phù hợp với ngôn ngữ nội bộ. Khi cần gửi thông tin ra ngoài, lớp này cũng có thể chuyển mô hình nội bộ thành hợp đồng mà đối tác hiểu được.

ACL không chỉ đổi tên trường dữ liệu. Nó làm rõ ý nghĩa, trạng thái, đơn vị đo, danh tính, quy tắc và cách biểu diễn của hai mô hình. Nhờ đó, context có thể hợp tác với hệ thống khác mà vẫn giữ được ngôn ngữ và các bất biến của chính mình.

## 1. Vấn đề ACL giải quyết

Giả sử một doanh nghiệp phát triển hệ thống bán hàng mới nhưng vẫn phải kết nối với ERP cũ. Hệ thống bán hàng sử dụng khái niệm `Order` để biểu diễn cam kết mua hàng của khách. ERP lại lưu một chứng từ tổng hợp với mã loại, mã trạng thái và các trường được thiết kế theo lịch sử kế toán.

Trong ERP, một mã trạng thái có thể vừa thể hiện tình trạng ghi sổ vừa thể hiện tiến trình xử lý nội bộ. Một trường `customer_code` có thể chỉ đến tài khoản công nợ, trong khi context bán hàng cần biết người mua hoặc tổ chức đặt hàng. Nếu nhóm dùng trực tiếp các kiểu dữ liệu và thuật ngữ của ERP trong mô hình bán hàng, những quy tắc của ERP sẽ dần chi phối thiết kế mới.

Ví dụ, mã trạng thái `C` trong ERP có thể có nghĩa là chứng từ đã được ghi sổ. Nếu hệ thống bán hàng gán trực tiếp `Order.status = C`, người đọc không biết đơn hàng đã được xác nhận, đã thanh toán hay đã hoàn tất giao hàng. Nếu sau này ERP đổi mã hoặc bổ sung trạng thái, mô hình bán hàng cũng bị ảnh hưởng.

Những vấn đề thường gặp khi không bảo vệ ranh giới gồm:

- **Rò rỉ ngôn ngữ:** tên trường, trạng thái và thuật ngữ của hệ thống bên ngoài xuất hiện trong entity, aggregate hoặc service nội bộ.
- **Lệch ý nghĩa:** hai bên dùng cùng một từ nhưng định nghĩa khác nhau, hoặc dùng từ khác nhau cho cùng một khái niệm.
- **Rò rỉ quy tắc:** chính sách và cách xử lý đặc thù của đối tác trở thành điều kiện bắt buộc trong mô hình nội bộ.
- **Phụ thuộc kỹ thuật:** mã nghiệp vụ gọi trực tiếp API, SDK, kiểu dữ liệu hoặc cấu trúc database của đối tác.
- **Khó thay đổi:** thay đổi phiên bản, nhà cung cấp hoặc hệ thống cũ buộc nhiều phần của mô hình nội bộ phải sửa theo.
- **Khó kiểm thử:** kiểm thử nghiệp vụ cần khởi tạo kiểu dữ liệu phức tạp hoặc giả lập hành vi của hệ thống bên ngoài.

ACL tạo một ranh giới diễn giải để những khác biệt đó được xử lý tại nơi tích hợp.

## 2. ACL là gì và nằm ở đâu?

**Anti-Corruption Layer** là một lớp chuyển đổi và điều phối ở ranh giới giữa hai mô hình. Nó nhận thông tin theo ngôn ngữ của hệ thống bên ngoài, diễn giải thông tin đó và cung cấp cho mô hình nội bộ một biểu diễn phù hợp. Khi context nội bộ cần gọi hệ thống ngoài, ACL chuyển yêu cầu và kết quả theo hợp đồng tương ứng.

Thông thường, ACL được đặt ở phía context muốn bảo vệ. Trong quan hệ giữa một hệ thống cũ và một context mới, context mới thường là phía cần giữ mô hình độc lập khỏi cấu trúc cũ. ACL có thể gồm nhiều thành phần, chẳng hạn:

- **Adapter hoặc gateway:** giao tiếp với API, message broker, SDK, file hoặc database bên ngoài.
- **DTO/contract model:** biểu diễn cấu trúc dữ liệu theo hợp đồng của đối tác.
- **Translator/mapper:** chuyển thuật ngữ, giá trị, trạng thái và cấu trúc giữa hai mô hình.
- **Facade hoặc application service tại ranh giới:** điều phối lời gọi và trả về kết quả theo ngôn ngữ của context nội bộ.
- **Chính sách xử lý lỗi:** diễn giải lỗi của đối tác thành kết quả có ý nghĩa đối với ứng dụng nội bộ.

Các thành phần này không nhất thiết phải là những lớp riêng trong mọi dự án. Tổ chức mã phụ thuộc vào độ phức tạp của tích hợp. Điều quan trọng là mã giao tiếp và chuyển đổi nằm ở ranh giới, còn mô hình miền không phụ thuộc trực tiếp vào kiểu dữ liệu của đối tác.

```text
       Hệ thống đối tác / mô hình bên ngoài
       (API, ERP, dịch vụ nhà cung cấp)
                       |
                       v
       +-------------------------------+
       |     Anti-Corruption Layer     |
       |                               |
       |  Adapter / Gateway            |
       |  Translator / Mapper          |
       |  Error translation            |
       +-------------------------------+
                       |
                       v
       +-------------------------------+
       |     Bounded Context nội bộ    |
       |                               |
       |  Application / Domain Model   |
       |  Entity, Value Object,        |
       |  Aggregate, Domain Service    |
       +-------------------------------+
```

Sơ đồ cho thấy ACL bảo vệ mô hình nội bộ khỏi cách biểu diễn bên ngoài. Nó không phải là một domain model mới và cũng không thay thế trách nhiệm nghiệp vụ của context.

## 3. ACL chuyển đổi ý nghĩa, không chỉ chuyển đổi cấu trúc

Chuyển đổi JSON thành object hoặc đổi tên `cust_no` thành `customerNumber` có thể là một phần của tích hợp, nhưng chưa đủ để tạo thành ACL có ý nghĩa. Vấn đề cốt lõi là xác định hai bên đang nói về khái niệm gì và ý nghĩa nào cần được giữ lại.

### 3.1. Chuyển đổi thuật ngữ

Một hệ thống cũ có thể gọi đối tượng là `Debtor`, trong khi context mới sử dụng `PayerAccount`. Hai tên có thể liên quan nhưng không nhất thiết đồng nghĩa hoàn toàn. ACL cần xác định đối tượng bên ngoài đại diện cho chủ thể chịu nghĩa vụ thanh toán, tài khoản công nợ hay một hồ sơ tổng hợp.

Nếu ngữ nghĩa đã được xác nhận, translator có thể chuyển dữ liệu sang kiểu nội bộ như `PayerAccountId`. Nếu chưa rõ, nhóm cần hỏi chuyên gia nghiệp vụ thay vì suy ra từ tên trường.

### 3.2. Chuyển đổi trạng thái

Giả sử ERP có các mã `N`, `P`, `C`, `X`. Context nội bộ dùng `Draft`, `Approved`, `Posted` và `Voided`. Ánh xạ cần dựa trên định nghĩa và điều kiện chuyển trạng thái của hai hệ thống.

Không nên viết một phép thay thế tùy tiện như `C -> Completed`. `Posted` có thể chỉ có nghĩa chứng từ đã ghi sổ, trong khi `Completed` trong mô hình đơn hàng có thể yêu cầu hàng đã được giao. Hai trạng thái giống nhau về cảm giác ngôn ngữ nhưng khác nhau về sự kiện nghiệp vụ.

### 3.3. Chuyển đổi đơn vị và giá trị

Hệ thống đối tác có thể gửi số tiền dưới dạng số nguyên theo đơn vị nhỏ nhất, chẳng hạn xu, trong khi mô hình nội bộ sử dụng `Money` với số tiền và tiền tệ. Một API khác có thể gửi khối lượng theo gram, còn mô hình nội bộ dùng kilogram.

Translator cần chuyển đổi đơn vị, làm rõ quy tắc làm tròn và kiểm tra dữ liệu hợp lệ. Không nên chỉ đổi kiểu số mà bỏ qua tiền tệ, đơn vị đo hoặc độ chính xác.

### 3.4. Chuyển đổi danh tính và quan hệ

Một đối tác có thể dùng mã khách hàng `C-1002`, còn context nội bộ dùng UUID. Hai mã không thể thay thế trực tiếp. ACL có thể tra cứu bảng ánh xạ hoặc gọi dịch vụ định danh để tìm đối tượng nội bộ tương ứng.

Tương tự, một chứng từ bên ngoài có thể gom nhiều đơn hàng, trong khi mô hình nội bộ theo dõi từng đơn riêng. ACL cần xác định quan hệ một-nhiều, nhiều-một hoặc các trường hợp không thể ánh xạ một-một.

### 3.5. Chuyển đổi lỗi và kết quả

Đối tác có thể trả lỗi `E17`, `INVALID_DOC` hoặc một thông báo kỹ thuật. Context nội bộ cần diễn giải lỗi thành kết quả có ý nghĩa, ví dụ “tài khoản thanh toán không tồn tại”, “chứng từ đã được ghi sổ” hoặc “đối tác tạm thời không khả dụng”.

Không nên làm mất thông tin chẩn đoán cần thiết. ACL có thể giữ mã lỗi gốc và thông tin tương quan trong log, đồng thời cung cấp một kiểu lỗi nội bộ ổn định cho application layer.

## 4. Ví dụ: bảo vệ context thanh toán trước ERP cũ

Giả sử context thanh toán của một hệ thống thương mại điện tử cần ghi nhận khoản phải thu trong ERP. Mô hình nội bộ sử dụng:

- `PayerAccount`: tài khoản của chủ thể chịu nghĩa vụ thanh toán.
- `Money`: giá trị tiền cùng loại tiền tệ.
- `Receivable`: khoản phải thu phát sinh từ giao dịch.
- `ReceivableStatus`: trạng thái nghiệp vụ của khoản phải thu.

ERP cũ lại yêu cầu một request có các trường `debtor_no`, `doc_type`, `amount_minor`, `currency_code` và `posting_flag`. Nhóm không nên đưa các tên trường này vào aggregate `Receivable`. Thay vào đó, ACL chuyển mô hình nội bộ sang hợp đồng ERP.

```text
Payment context
  Receivable
      |
      | Internal command / domain model
      v
  Anti-Corruption Layer
      |
      | ERP request contract
      v
Legacy ERP
  debtor_no, doc_type, amount_minor, currency_code, posting_flag
```

Một ví dụ Java đơn giản:

```java
// Mô hình nội bộ
public record Money(BigDecimal amount, Currency currency) {}

public record PayerAccountId(UUID value) {}

public record Receivable(
        UUID id,
        PayerAccountId payerAccountId,
        Money amount
) {}

// Hợp đồng riêng của ERP
public record ErpReceivableRequest(
        String debtorNo,
        String docType,
        long amountMinor,
        String currencyCode,
        boolean postingFlag
) {}

// Cổng giao tiếp mà application layer sử dụng
public interface ReceivableLedger {
    void record(Receivable receivable);
}

// ACL chuyển mô hình nội bộ sang hợp đồng ERP
public final class ErpReceivableLedger implements ReceivableLedger {
    private final ErpClient erpClient;
    private final PayerAccountNumberResolver accountResolver;

    public ErpReceivableLedger(
            ErpClient erpClient,
            PayerAccountNumberResolver accountResolver
    ) {
        this.erpClient = erpClient;
        this.accountResolver = accountResolver;
    }

    @Override
    public void record(Receivable receivable) {
        String debtorNo = accountResolver.resolve(
                receivable.payerAccountId()
        );

        ErpReceivableRequest request = new ErpReceivableRequest(
                debtorNo,
                "AR",
                toMinorUnits(receivable.amount()),
                receivable.amount().currency().getCurrencyCode(),
                true
        );

        erpClient.createReceivable(request);
    }

    private long toMinorUnits(Money money) {
        int scale = money.currency().getDefaultFractionDigits();
        return money.amount()
                .movePointRight(scale)
                .setScale(0, RoundingMode.UNNECESSARY)
                .longValueExact();
    }
}
```

Đoạn mã minh họa ranh giới chuyển đổi, không phải một triển khai hoàn chỉnh. Trong hệ thống thực tế, nhóm cần xác định cách làm tròn theo từng loại tiền, cách tra cứu mã ERP, tính lũy đẳng khi gửi lại yêu cầu, xử lý timeout và phản hồi lỗi. Các lớp `ErpClient` và `PayerAccountNumberResolver` là cổng kỹ thuật cần được triển khai riêng.

Điểm quan trọng là aggregate `Receivable` không cần biết `debtor_no`, `doc_type` hay `posting_flag`. Nếu ERP thay đổi cấu trúc request, phần lớn thay đổi được xử lý trong ACL và adapter. Nếu quy tắc ghi nhận khoản phải thu thay đổi, nhóm vẫn sửa mô hình thanh toán theo nghiệp vụ của mình.

## 5. ACL khi nhận dữ liệu từ hệ thống bên ngoài

ACL thường được nhắc đến trong trường hợp context nội bộ gọi một hệ thống khác, nhưng nó cũng rất quan trọng khi nhận dữ liệu qua webhook, message hoặc file import.

Ví dụ, một cổng thanh toán gửi webhook:

```json
{
  "event": "charge.succeeded",
  "object": {
    "charge_id": "ch_9381",
    "customer_ref": "cus_27",
    "amount": 1250000,
    "currency": "VND",
    "captured": true
  }
}
```

Context thanh toán nội bộ có thể sử dụng thuật ngữ `PaymentCaptured` và `PaymentId`. ACL cần xác thực cấu trúc webhook, kiểm tra ý nghĩa sự kiện, tra cứu mã tham chiếu, chuyển số tiền sang `Money`, sau đó gửi một command hoặc application request phù hợp vào context.

```text
Payment provider webhook
          |
          v
  Webhook adapter
          |
          v
  ACL translator
    - validate contract
    - resolve external identity
    - map event meaning
    - convert amount/currency
          |
          v
  Payment application layer
          |
          v
  Payment domain model
```

Không nên để entity hoặc aggregate nội bộ phụ thuộc vào tên event, kiểu object hay SDK của nhà cung cấp. Khi nhà cung cấp đổi phiên bản API, nhóm chỉ cần cập nhật phần adapter và translator nếu ngữ nghĩa nghiệp vụ không thay đổi.

Webhook có thể được gửi lặp lại hoặc đến không theo thứ tự. ACL và application layer cần phối hợp với cơ chế idempotency, kiểm tra trạng thái và xử lý sự kiện trùng để tránh ghi nhận một khoản thanh toán nhiều lần. Đây là yêu cầu vận hành của tích hợp; ACL giúp diễn giải dữ liệu nhưng không tự động giải quyết mọi vấn đề phân phối thông điệp.

## 6. ACL và các chiều chuyển đổi

ACL có thể thực hiện chuyển đổi theo cả chiều nhận và chiều gửi, tùy hợp đồng tích hợp.

| Chiều | Công việc | Ví dụ |
| --- | --- | --- |
| Bên ngoài vào context nội bộ | Chuyển dữ liệu, thuật ngữ và trạng thái của đối tác thành mô hình nội bộ | Webhook `charge.succeeded` thành thông tin thanh toán đã thu |
| Context nội bộ ra bên ngoài | Chuyển yêu cầu nội bộ thành hợp đồng mà đối tác chấp nhận | `Receivable` thành request ghi sổ ERP |
| Kết quả bên ngoài quay về | Chuyển phản hồi hoặc lỗi đối tác thành kết quả nội bộ | Mã lỗi ERP thành lỗi nghiệp vụ hoặc lỗi tích hợp có thể xử lý |

Việc chuyển đổi hai chiều không có nghĩa hai mô hình phải đối xứng. Có thể chỉ một phần thông tin được gửi ra ngoài, hoặc một số giá trị không thể khôi phục chính xác khi chuyển ngược. Nhóm cần xác định rõ dữ liệu nào là nguồn sự thật, dữ liệu nào chỉ là bản chiếu và quy tắc đồng bộ thuộc về context nào.

Nếu một context nội bộ là bên cung cấp mô hình cho context khác, nhóm cũng cần xem xét hợp đồng công bố của mình. ACL thường hữu ích nhất ở phía phải thích nghi với mô hình của đối tác. Phía cung cấp nên công bố một ngôn ngữ và hợp đồng ổn định thay vì bắt mọi bên tiêu thụ phải hiểu cấu trúc nội bộ.

## 7. Phân biệt ACL với các cơ chế tích hợp khác

Một số mẫu thiết kế có vẻ giống ACL vì đều nằm ở ranh giới hệ thống, nhưng mục đích của chúng khác nhau.

| Cơ chế | Mục đích chính | Quan hệ với ACL |
| --- | --- | --- |
| Adapter | Chuyển đổi giao diện hoặc cách gọi để hai thành phần tương thích | Có thể là một thành phần bên trong ACL; adapter đơn giản chưa chắc đã bảo vệ ý nghĩa mô hình |
| Facade | Cung cấp một giao diện đơn giản hơn cho một hệ thống phức tạp | Có thể được dùng cùng ACL để che giấu chi tiết giao tiếp |
| DTO/Mapper | Truyền và chuyển đổi cấu trúc dữ liệu | Hỗ trợ ACL, nhưng chỉ đổi cấu trúc mà không diễn giải nghiệp vụ thì chưa đủ |
| Published Language | Định nghĩa ngôn ngữ hoặc hợp đồng được công bố để các bên trao đổi | Có thể là hợp đồng mà ACL tiêu thụ hoặc tạo ra |
| Shared Kernel | Chia sẻ một phần mô hình hoặc mã giữa các context theo thỏa thuận | Là lựa chọn khác; cần quản lý thay đổi chung và phụ thuộc chặt chẽ |
| Open Host Service | Cung cấp một giao diện dịch vụ công khai để các context khác sử dụng | Có thể giảm nhu cầu mỗi bên tự tích hợp theo cách riêng; phía tiêu thụ vẫn có thể cần ACL |
| Conformist | Context phía sau chấp nhận mô hình của nhà cung cấp mà không chuyển đổi đáng kể | Khác với ACL, vì không đặt lớp bảo vệ mô hình phía nhận |

Một adapter có thể chuyển `ExternalCustomerDto` thành `CustomerData`, nhưng nếu `CustomerData` vẫn chứa những khái niệm và quy tắc không phù hợp từ đối tác, mô hình nội bộ vẫn bị ảnh hưởng. ACL cần đưa ra một mô hình đích có ý nghĩa trong bounded context và xử lý khác biệt một cách có chủ đích.

Ngược lại, không phải tích hợp nào cũng cần ACL đầy đủ. Nếu hai bên đã thống nhất cùng một ngôn ngữ, hợp đồng đơn giản, ổn định và không kéo theo quy tắc ngoại lai, một adapter hoặc mapper mỏng có thể là đủ.

## 8. Khi nào nên sử dụng ACL?

ACL đặc biệt hữu ích trong các trường hợp sau:

- **Tích hợp hệ thống cũ:** hệ thống legacy có cấu trúc dữ liệu, thuật ngữ hoặc quy tắc được hình thành từ lâu và khó thay đổi.
- **Tích hợp nhà cung cấp:** API hoặc SDK bên ngoài có mô hình không phù hợp với ngôn ngữ nội bộ, hoặc nhà cung cấp có thể thay đổi phiên bản.
- **Tách bounded context:** hai context có mô hình khác nhau và cần chuyển đổi thông tin qua hợp đồng.
- **Thay thế hệ thống theo từng phần:** context mới cần hoạt động song song với hệ thống cũ trong một giai đoạn chuyển đổi.
- **Bảo vệ miền cốt lõi:** mô hình chứa quy tắc quan trọng cần độc lập với các quyết định kỹ thuật hoặc chính sách của hệ thống ngoài.
- **Tích hợp dữ liệu không đồng nhất:** dữ liệu đi qua nhiều nguồn có cách biểu diễn, đơn vị, mã định danh hoặc trạng thái khác nhau.

Trước khi xây dựng ACL, nhóm nên trả lời:

1. Mô hình nội bộ nào cần được bảo vệ?
2. Mô hình hoặc hợp đồng bên ngoài khác ở thuật ngữ, quy tắc, danh tính hay cấu trúc nào?
3. Context nào sở hữu từng quy tắc và dữ liệu nguồn?
4. Dữ liệu nào cần chuyển đổi, dữ liệu nào có thể bỏ qua?
5. Điều gì xảy ra khi giá trị bên ngoài không ánh xạ được sang mô hình nội bộ?
6. Hệ thống có cần gửi yêu cầu ngược lại và xử lý kết quả không?
7. Mức độ thay đổi và rủi ro có đủ lớn để biện minh cho một lớp chuyển đổi riêng không?

Nếu không có sự khác biệt đáng kể về ngữ nghĩa hoặc mô hình, ACL phức tạp có thể tạo thêm mã, độ trễ và điểm lỗi mà không đem lại lợi ích tương xứng.

## 9. Thiết kế và triển khai ACL có kiểm soát

Một ACL tốt cần có ranh giới rõ, trách nhiệm dễ hiểu và khả năng kiểm chứng. Có thể thực hiện theo các bước sau.

### Bước 1: Xác định mô hình cần bảo vệ

Mô tả bounded context nội bộ, những khái niệm cốt lõi, các bất biến và ngôn ngữ chung. Xác định phần nào không được phụ thuộc vào cấu trúc bên ngoài.

### Bước 2: Khám phá hợp đồng của đối tác

Thu thập tài liệu API, schema message, mẫu file, mã trạng thái, quy tắc xác thực và ví dụ dữ liệu thực tế. Trao đổi với chủ sở hữu hệ thống để làm rõ những trường có tên khó hiểu hoặc ý nghĩa phụ thuộc vào quy trình.

Không nên chỉ dựa vào tên trường hoặc tài liệu kỹ thuật. Một trường `status`, `type` hoặc `customer_id` thường không đủ để suy ra ý nghĩa nghiệp vụ.

### Bước 3: Lập bảng ánh xạ ngữ nghĩa

Với từng trường hoặc khái niệm quan trọng, ghi rõ ý nghĩa nguồn, ý nghĩa đích, quy tắc chuyển đổi, trường hợp không hợp lệ và cách xử lý khi không thể ánh xạ.

| Dữ liệu bên ngoài | Khái niệm nội bộ | Quy tắc chuyển đổi cần xác nhận |
| --- | --- | --- |
| `debtor_no` | `PayerAccountId` | Tra cứu mã tài khoản đối tác sang định danh nội bộ |
| `amount_minor` | `Money` | Xác định đơn vị nhỏ nhất theo tiền tệ và quy tắc làm tròn |
| `currency_code` | `Currency` | Kiểm tra mã tiền tệ được hỗ trợ |
| `posting_flag` | Kết quả ghi sổ | Làm rõ cờ này xác nhận đã ghi sổ hay chỉ yêu cầu ghi sổ |
| `doc_status` | Trạng thái chứng từ nội bộ | Ánh xạ theo định nghĩa và vòng đời, không theo tên gần giống |

### Bước 4: Định nghĩa mô hình hợp đồng riêng

Tạo DTO hoặc contract type phản ánh đúng giao thức bên ngoài. Không dùng trực tiếp các kiểu này trong aggregate hoặc domain service. Nếu có nhiều phiên bản API, có thể giữ các contract type riêng theo phiên bản rồi chuyển về cùng mô hình nội bộ khi ý nghĩa không đổi.

### Bước 5: Viết translator và chính sách lỗi

Translator thực hiện chuyển đổi có kiểm tra. Khi dữ liệu không hợp lệ hoặc không thể ánh xạ, nó phải trả về lỗi có ý nghĩa và giữ đủ thông tin chẩn đoán. Không nên tự gán giá trị mặc định cho một trạng thái hoặc danh tính không xác định, vì điều đó có thể làm thay đổi nghiệp vụ một cách âm thầm.

### Bước 6: Đặt giao tiếp bên ngoài sau một cổng nội bộ

Application layer nên phụ thuộc vào interface thể hiện mục đích nghiệp vụ, chẳng hạn `ReceivableLedger` hoặc `PaymentProvider`. Adapter và ACL triển khai interface đó bằng cách gọi API hoặc SDK cụ thể. Nhờ vậy, application service không cần biết nhà cung cấp nào đang được sử dụng.

### Bước 7: Kiểm thử các trường hợp ánh xạ

Kiểm thử translator với dữ liệu hợp lệ, giá trị biên, trạng thái không biết, mã định danh không tồn tại, tiền tệ không hỗ trợ và phản hồi lỗi. Kiểm thử adapter riêng cho giao thức và kiểm thử tích hợp với sandbox hoặc môi trường kiểm thử của đối tác khi cần.

### Bước 8: Theo dõi thay đổi hợp đồng

Theo dõi phiên bản API, schema và thông báo thay đổi từ nhà cung cấp. Khi hợp đồng thay đổi, kiểm tra xem đó chỉ là thay đổi cấu trúc hay đã thay đổi ý nghĩa nghiệp vụ. Cập nhật ACL và kiểm thử tương ứng.

## 10. Kiểm thử, vận hành và các giới hạn của ACL

ACL giảm sự phụ thuộc giữa các mô hình, nhưng nó không loại bỏ các vấn đề của tích hợp phân tán. Nhóm vẫn cần thiết kế cho timeout, retry, dữ liệu trùng, lỗi mạng, thay đổi schema và sự không đồng bộ giữa các hệ thống.

### 10.1. Kiểm thử translator độc lập

Translator nên có các kiểm thử xác nhận từng quy tắc ánh xạ. Ví dụ:

- Mã trạng thái ERP đã biết được chuyển thành trạng thái nội bộ đúng.
- Mã trạng thái mới hoặc không xác định được xử lý theo chính sách rõ ràng.
- Số tiền và tiền tệ được chuyển đổi chính xác, không mất độ chính xác.
- Mã khách hàng bên ngoài được ánh xạ đến đúng định danh nội bộ.
- Lỗi từ đối tác được chuyển thành lỗi nội bộ có thể phân loại.

Những kiểm thử này giúp phát hiện thay đổi ngữ nghĩa sớm hơn việc chỉ kiểm tra API trả HTTP 200.

### 10.2. Kiểm thử hợp đồng tích hợp

Khi có thể, nhóm nên xác nhận request và response tuân theo hợp đồng của đối tác. Với hệ thống do nhóm kiểm soát, contract test giúp phát hiện hai phía hiểu khác nhau về schema hoặc hành vi. Với nhà cung cấp bên ngoài, kiểm thử trên sandbox và theo dõi phiên bản API giúp giảm rủi ro.

### 10.3. Quan sát và truy vết

Log nên giữ mã tương quan, mã giao dịch bên ngoài và thông tin lỗi cần thiết để truy vết. Không ghi dữ liệu nhạy cảm vượt quá nhu cầu vận hành. Metric có thể theo dõi tỷ lệ ánh xạ thất bại, lỗi đối tác, timeout, retry và độ trễ của tích hợp.

### 10.4. Quản lý lỗi và tính lũy đẳng

Một yêu cầu gửi sang đối tác có thể timeout dù đối tác đã xử lý thành công. Nếu gửi lại mà không có cơ chế lũy đẳng, khoản phải thu hoặc giao dịch có thể bị tạo trùng. ACL cần phối hợp với application layer để sử dụng idempotency key, mã tham chiếu và quy trình đối soát phù hợp.

ACL cũng cần phân biệt lỗi nghiệp vụ có thể xử lý, lỗi dữ liệu không hợp lệ và lỗi hạ tầng tạm thời. Không phải lỗi nào cũng nên retry; retry vô hạn có thể làm hệ thống quá tải hoặc tạo ra tác dụng phụ lặp lại.

### 10.5. Chi phí và giới hạn

ACL bổ sung mã chuyển đổi, kiểm thử, giám sát và trách nhiệm duy trì hợp đồng. Nếu có quá nhiều đối tác hoặc mỗi bên có hàng trăm quy tắc ánh xạ, lớp này có thể trở thành một subsystem đáng kể. Nhóm cần giữ ranh giới rõ và tránh để ACL biến thành nơi chứa mọi logic nghiệp vụ.

Các quy tắc quyết định một khoản phải thu có hợp lệ hay không thuộc về mô hình thanh toán. ACL chỉ chuyển đổi và điều phối thông tin cần thiết để mô hình đó làm việc với bên ngoài. Nếu chính sách nghiệp vụ bị đặt trong translator, nhóm sẽ khó biết quy tắc nào thuộc context và quy tắc nào chỉ là cách thích nghi với đối tác.

## 11. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ đổi tên trường rồi gọi đó là ACL | Ngữ nghĩa và quy tắc của đối tác vẫn rò rỉ vào mô hình nội bộ | Xác minh ý nghĩa, trạng thái, danh tính và đơn vị trước khi ánh xạ |
| Để domain model phụ thuộc SDK hoặc DTO bên ngoài | Mô hình nội bộ bị khóa vào nhà cung cấp | Đặt cổng nội bộ và chuyển đổi tại adapter/ACL |
| Đưa mọi logic nghiệp vụ vào translator | ACL trở thành nơi chứa quy tắc không có chủ sở hữu rõ | Giữ bất biến trong aggregate/domain service; ACL chỉ thích nghi hợp đồng |
| Gán mặc định khi không hiểu trạng thái bên ngoài | Dữ liệu sai có thể được chấp nhận âm thầm | Từ chối hoặc đưa vào luồng xử lý ngoại lệ có quan sát |
| Không quản lý phiên bản hợp đồng | Thay đổi API làm hỏng tích hợp bất ngờ | Theo dõi schema, contract test và quản lý phiên bản |
| Chuyển đổi danh tính bằng cách đoán | Liên kết nhầm khách hàng hoặc tài khoản | Dùng resolver hoặc bảng ánh xạ có kiểm soát |
| Bỏ qua timeout và gửi lặp | Có thể tạo giao dịch hoặc chứng từ trùng | Thiết kế idempotency, retry có giới hạn và đối soát |
| Xây ACL quá lớn cho tích hợp đơn giản | Tăng chi phí và độ phức tạp không cần thiết | Chọn mức chuyển đổi tương xứng với khác biệt thực tế |

## 12. Nguyên tắc thực hành

Khi xây dựng ACL, nhóm nên duy trì các nguyên tắc sau:

- **Bảo vệ một mô hình cụ thể.** Xác định bounded context và các bất biến cần giữ trước khi viết mapper.
- **Chuyển đổi ý nghĩa có chủ đích.** Không suy ra quy tắc từ tên trường, mã trạng thái hoặc cấu trúc dữ liệu đơn thuần.
- **Giữ hợp đồng bên ngoài ở ranh giới.** DTO, SDK và mã lỗi của đối tác không nên xuất hiện trong domain model.
- **Để context sở hữu quy tắc của mình.** ACL thích nghi với hệ thống ngoài; aggregate và domain service bảo vệ chính sách nội bộ.
- **Xử lý rõ dữ liệu không thể ánh xạ.** Không tự tạo giá trị mặc định có thể làm sai ý nghĩa nghiệp vụ.
- **Quản lý danh tính và đơn vị.** Mã tham chiếu, tiền tệ, độ chính xác và đơn vị đo cần được chuyển đổi chính xác.
- **Thiết kế cho lỗi tích hợp.** Có timeout, retry có kiểm soát, idempotency, log và khả năng đối soát khi phù hợp.
- **Kiểm thử hợp đồng và translator.** Xác nhận cả cấu trúc lẫn ngữ nghĩa của dữ liệu trao đổi.
- **Giữ ACL vừa đủ.** Chỉ thêm mức chuyển đổi cần thiết để bảo vệ mô hình và quản lý rủi ro.

Anti-Corruption Layer giúp một bounded context duy trì ngôn ngữ và quy tắc của mình khi phải hợp tác với hệ thống có mô hình khác. Giá trị của ACL nằm ở việc chuyển đổi đúng ý nghĩa tại ranh giới, giữ cho mô hình nội bộ không bị chi phối bởi cấu trúc bên ngoài và làm cho thay đổi của hệ thống đối tác có phạm vi ảnh hưởng rõ ràng.

## 13. Câu hỏi tự kiểm tra

1. Anti-Corruption Layer giải quyết vấn đề gì khi một bounded context tích hợp với hệ thống cũ hoặc dịch vụ bên ngoài?
2. Vì sao ACL cần chuyển đổi ý nghĩa nghiệp vụ thay vì chỉ đổi tên trường dữ liệu?
3. ACL thường được đặt ở phía nào của quan hệ tích hợp và vì sao?
4. Phân biệt trách nhiệm của adapter, translator và domain model trong một ACL.
5. Vì sao mã trạng thái của ERP không nên được gán trực tiếp cho trạng thái của aggregate nội bộ?
6. Khi chuyển số tiền từ đơn vị nhỏ nhất của API sang `Money`, nhóm cần xác nhận những quy tắc nào?
7. Vì sao cùng một mã khách hàng bên ngoài không thể luôn được dùng làm định danh nội bộ?
8. Phân biệt ACL với Adapter, Facade, Published Language, Shared Kernel và Conformist.
9. Khi nào một mapper đơn giản là đủ và khi nào cần một ACL có trách nhiệm rõ ràng?
10. ACL cần phối hợp với idempotency và xử lý lỗi như thế nào khi gọi hệ thống bên ngoài?
11. Những kiểm thử nào giúp xác nhận translator đang bảo toàn đúng ý nghĩa của dữ liệu?
12. Hãy chọn một hệ thống bên ngoài mà ứng dụng của bạn cần tích hợp, xác định khác biệt về thuật ngữ, trạng thái và danh tính, rồi phác thảo ACL để bảo vệ mô hình nội bộ.
