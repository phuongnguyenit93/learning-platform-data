# Cung cấp dữ liệu ngoài cho quy tắc miền qua điểm phụ thuộc phù hợp

Bài học này thuộc module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED** — **Học tổ chức phần mềm theo kiến trúc phân tầng**, trong chương **Tầng nghiệp vụ**. Trọng tâm là cách đưa dữ liệu do hệ thống bên ngoài sở hữu vào một quy tắc nghiệp vụ mà vẫn giữ được ranh giới giữa domain, application và infrastructure. Domain có thể cần dữ liệu về tỷ giá, điểm tín dụng, thuế, vận chuyển hoặc trạng thái từ một hệ thống khác. Cách truy xuất dữ liệu đó cần được đặt tại một điểm phụ thuộc có chủ đích.

## 1. Vì sao quy tắc miền cần dữ liệu bên ngoài?

Quy tắc nghiệp vụ đôi khi phụ thuộc vào một sự kiện hoặc thông tin mà ứng dụng không tự sở hữu. Ví dụ:

- Một đơn hàng chỉ được giao khi hãng vận chuyển xác nhận tuyến đường còn khả dụng.
- Một giao dịch ngoại tệ cần tỷ giá có hiệu lực tại thời điểm xác định giá.
- Một hồ sơ tín dụng cần kết hợp lịch sử thanh toán nội bộ với mức rủi ro do tổ chức đánh giá tín dụng bên ngoài cung cấp.
- Một khoản thuế cần áp dụng mức thuế suất do cơ quan hoặc dịch vụ thuế công bố.

Thông tin đó có thể được cung cấp qua HTTP API, message broker, cơ sở dữ liệu dùng chung, dịch vụ nội bộ hoặc một nguồn dữ liệu được đồng bộ định kỳ. Dù nguồn nằm ở đâu, quy tắc miền vẫn cần diễn đạt bằng ngôn ngữ nghiệp vụ. Ví dụ, domain cần biết “mức rủi ro tín dụng”, “tỷ giá áp dụng” hoặc “báo giá vận chuyển còn hiệu lực”; domain không cần biết endpoint URL, JSON response, tên bảng hoặc SDK của nhà cung cấp.

Trước khi thiết kế, cần phân biệt ba thứ:

1. **Dữ liệu bên ngoài:** thông tin được lấy từ một nguồn ngoài phạm vi sở hữu của domain hiện tại.
2. **Ý nghĩa nghiệp vụ của dữ liệu:** khái niệm và kiểu dữ liệu mà quy tắc miền cần sử dụng, chẳng hạn **RiskAssessment** hoặc **ExchangeRate**.
3. **Cơ chế truy xuất:** HTTP client, SQL query, message consumer, cache hoặc SDK cụ thể.

Chỉ phần thứ hai nên đi vào mô hình domain. Phần thứ ba thuộc infrastructure. Application hoặc một domain service sẽ phối hợp sử dụng hợp đồng truy xuất tùy vào nơi sở hữu trách nhiệm đó.

## 2. Nguyên tắc thiết kế điểm phụ thuộc

Khi quy tắc miền cần dữ liệu ngoài, hãy giữ các nguyên tắc sau:

- **Domain diễn đạt nhu cầu bằng khái niệm nghiệp vụ.** Ví dụ **RiskAssessmentReader** hoặc **ExchangeRateSource** có ý nghĩa rõ ràng hơn một interface chung chung tên **HttpClient**.
- **Chiều phụ thuộc mã nguồn hướng vào abstraction phù hợp.** Domain hoặc application định nghĩa hợp đồng mà nó cần; adapter ở infrastructure triển khai hợp đồng đó.
- **Không để domain biết chi tiết nhà cung cấp.** Không truyền DTO của một vendor, **WebClient**, **RestTemplate**, JDBC connection hoặc SDK của nhà cung cấp vào quy tắc miền.
- **Không biến entity thành thành phần truy cập mạng.** Entity nên bảo vệ trạng thái và hành vi của chính nó; không tự gọi API trong getter, constructor hoặc phương thức nghiệp vụ.
- **Dữ liệu ngoài cần có ngữ cảnh về thời điểm và độ tin cậy.** Giá trị có thể hết hạn, thay đổi hoặc không truy xuất được. Quy tắc phải biết nó đang dùng dữ liệu nào và dữ liệu có còn hợp lệ hay không.

Có hai cách tổ chức thường gặp. Cách thứ nhất là application truy xuất dữ liệu trước rồi truyền một giá trị domain đã chuẩn hóa vào quy tắc miền. Cách thứ hai là domain sở hữu một port diễn đạt khả năng lấy thông tin mà chính sách nghiệp vụ cần. Chọn cách nào phụ thuộc vào việc ai chịu trách nhiệm điều phối việc truy xuất và khái niệm nào thực sự thuộc ngôn ngữ domain.

## 3. Cách thường dùng: application lấy dữ liệu rồi truyền vào domain

Giả sử doanh nghiệp xét duyệt một yêu cầu cấp tín dụng. Quyết định phụ thuộc vào thông tin khách hàng nội bộ, số tiền yêu cầu và mức rủi ro do dịch vụ đánh giá tín dụng bên ngoài cung cấp.

Application service điều phối use case: tải khách hàng, yêu cầu dữ liệu rủi ro, chuyển dữ liệu ngoài thành kiểu domain, gọi chính sách xét duyệt rồi lưu kết quả. Chính sách miền nhận các dữ liệu cần thiết dưới dạng tham số và thực hiện quy tắc một cách xác định.

### Mô hình dữ liệu nghiệp vụ

Ví dụ kiểu domain đã chuẩn hóa:

~~~java
public enum RiskBand {
    LOW, MEDIUM, HIGH
}

public record RiskAssessment(
        RiskBand band,
        Instant assessedAt,
        Instant validUntil,
        String reference
) {
    public boolean isValidAt(Instant time) {
        return !time.isBefore(assessedAt)
                && time.isBefore(validUntil);
    }
}
~~~

**RiskAssessment** chỉ biểu đạt thông tin mà domain hiểu: mức rủi ro, thời điểm đánh giá, thời hạn hiệu lực và mã tham chiếu để truy vết. Nó không chứa tên trường JSON hay kiểu response riêng của nhà cung cấp.

Chính sách miền có thể nhận dữ liệu đó:

~~~java
public final class CreditApprovalPolicy {
    public CreditDecision evaluate(
            Customer customer,
            Money requestedAmount,
            RiskAssessment assessment,
            Instant evaluatedAt) {

        if (!assessment.isValidAt(evaluatedAt)) {
            throw new ExpiredRiskAssessmentException();
        }

        if (assessment.band() == RiskBand.HIGH) {
            return CreditDecision.rejected("RISK_TOO_HIGH");
        }

        if (requestedAmount.isGreaterThan(customer.availableCredit())) {
            return CreditDecision.rejected("CREDIT_LIMIT_EXCEEDED");
        }

        return CreditDecision.approved();
    }
}
~~~

Đây là ví dụ rút gọn; **Money**, **Customer**, **CreditDecision** và các exception là kiểu nghiệp vụ được giả định đã tồn tại. Điểm quan trọng là chính sách chỉ nhận những giá trị cần để ra quyết định. Nó không biết dữ liệu được lấy từ dịch vụ nào.

### Port truy xuất ở application

Nếu use case chịu trách nhiệm quyết định lúc nào cần truy xuất dữ liệu rủi ro, application có thể định nghĩa port:

~~~java
public interface RiskAssessmentReader {
    RiskAssessment readFor(CustomerId customerId);
}
~~~

Adapter hạ tầng triển khai port này. Ví dụ, adapter gọi dịch vụ đánh giá tín dụng qua HTTP rồi chuyển response của nhà cung cấp thành **RiskAssessment**:

~~~java
@Component
public class HttpRiskAssessmentAdapter implements RiskAssessmentReader {
    private final RiskProviderClient client;

    public HttpRiskAssessmentAdapter(RiskProviderClient client) {
        this.client = client;
    }

    @Override
    public RiskAssessment readFor(CustomerId customerId) {
        RiskProviderResponse response = client.fetch(customerId.value());

        return new RiskAssessment(
                mapRiskBand(response.riskCode()),
                response.assessedAt(),
                response.validUntil(),
                response.referenceId());
    }
}
~~~

**RiskProviderClient** và **RiskProviderResponse** là chi tiết của infrastructure. Hàm **mapRiskBand** chuyển mã của nhà cung cấp sang khái niệm domain; nếu mã mới chưa được hỗ trợ, adapter phải xử lý như một kết quả không hiểu được thay vì tự đoán mức rủi ro.

Application service điều phối các bước:

~~~java
@Service
public class ReviewCreditApplicationService {
    private final CustomerRepository customers;
    private final RiskAssessmentReader riskReader;
    private final CreditApprovalPolicy policy;
    private final CreditDecisionRepository decisions;
    private final Clock clock;

    public ReviewCreditApplicationService(
            CustomerRepository customers,
            RiskAssessmentReader riskReader,
            CreditApprovalPolicy policy,
            CreditDecisionRepository decisions,
            Clock clock) {
        this.customers = customers;
        this.riskReader = riskReader;
        this.policy = policy;
        this.decisions = decisions;
        this.clock = clock;
    }

    public CreditDecision review(
            CustomerId customerId,
            Money requestedAmount) {
        Customer customer = customers.getRequired(customerId);
        RiskAssessment assessment = riskReader.readFor(customerId);

        CreditDecision decision = policy.evaluate(
                customer,
                requestedAmount,
                assessment,
                clock.instant());

        decisions.save(customerId, decision, assessment.reference());
        return decision;
    }
}
~~~

Trong ví dụ, **Clock** được inject để thời điểm đánh giá có thể kiểm soát trong kiểm thử. Việc lưu quyết định và mã tham chiếu giúp truy vết dữ liệu đã được dùng. Trong ứng dụng thực tế, cần xác định rõ ranh giới transaction cho thao tác đọc/ghi và không giữ transaction cơ sở dữ liệu mở trong thời gian chờ một API từ xa nếu không cần thiết.

### Luồng phụ thuộc và luồng gọi

~~~mermaid
flowchart TD
    A[ReviewCreditApplicationService] -->|uses| P[RiskAssessmentReader]
    A -->|calls| D[CreditApprovalPolicy]
    I[HttpRiskAssessmentAdapter] -->|implements| P
    I --> V[RiskProviderClient]
    D --> M[RiskAssessment]
~~~

Khi chạy, application gọi **RiskAssessmentReader**; Spring có thể inject **HttpRiskAssessmentAdapter** làm implementation. Trong mã nguồn, adapter phụ thuộc vào interface và application cũng phụ thuộc vào interface. Chính sách domain nhận **RiskAssessment** như một giá trị đã chuẩn hóa. Việc gọi HTTP nằm trong adapter, còn quyết định tín dụng nằm trong domain.

Ưu điểm của cách này là quy tắc miền dễ kiểm thử và không cần thực hiện I/O. Có thể truyền một **RiskAssessment** mẫu vào **CreditApprovalPolicy** để kiểm tra mọi nhánh quyết định mà không cần khởi động Spring hoặc mô phỏng mạng.

## 4. Khi nào domain nên sở hữu port?

Đôi khi khả năng lấy dữ liệu là một phần ngôn ngữ của chính sách miền. Ví dụ, một chính sách chuyển đổi tiền tệ được định nghĩa là “quy đổi theo tỷ giá có hiệu lực tại thời điểm giao dịch”. Nếu người gọi không nên tự quyết định nguồn tỷ giá hoặc cách chọn tỷ giá phù hợp, domain có thể sở hữu một interface diễn đạt nhu cầu đó:

~~~java
public interface ExchangeRateSource {
    ExchangeRate rateFor(
            CurrencyPair pair,
            Instant effectiveAt);
}
~~~

Một domain service có thể dùng port:

~~~java
public final class CurrencyConversionService {
    private final ExchangeRateSource rateSource;

    public CurrencyConversionService(ExchangeRateSource rateSource) {
        this.rateSource = rateSource;
    }

    public Money convert(Money amount, Currency target, Instant at) {
        CurrencyPair pair = new CurrencyPair(
                amount.currency(), target);
        ExchangeRate rate = rateSource.rateFor(pair, at);
        return rate.convert(amount);
    }
}
~~~

Adapter ở infrastructure triển khai **ExchangeRateSource** bằng cách gọi dịch vụ tỷ giá, đọc dữ liệu đã đồng bộ hoặc tra cứu một nguồn được quản lý. Domain chỉ biết hợp đồng và kiểu **ExchangeRate**.

Cách này phù hợp khi việc chọn tỷ giá là một phần của chính sách nghiệp vụ và mọi caller phải tuân theo cùng một định nghĩa. Tuy nhiên, port trong domain không có nghĩa entity được phép tự gọi mạng. Nếu cần I/O, hãy thực hiện nó qua một domain service hoặc thành phần phối hợp có thể thay thế và kiểm thử được. Cần cân nhắc độ trễ, timeout và transaction vì lời gọi có thể là một thao tác từ xa.

Việc đặt interface ở domain hay application không có một đáp án cố định:

| Câu hỏi | Port thuộc application | Port thuộc domain |
|---|---|---|
| Ai quyết định lúc nào lấy dữ liệu? | Use case/application service | Chính sách hoặc domain service sở hữu nhu cầu |
| Hợp đồng mô tả điều gì? | Bước phối hợp của use case | Khả năng hoặc khái niệm trong ngôn ngữ nghiệp vụ |
| Domain nhận gì? | Giá trị đã truy xuất và chuẩn hóa | Có thể gọi port qua domain service để lấy giá trị |
| Phù hợp khi | Application chủ động gom dữ liệu trước khi gọi quy tắc | Việc truy xuất là một phần không thể tách khỏi chính sách miền |

Đừng đặt port trong domain chỉ vì muốn mọi interface đều nằm ở layer trong cùng. Cũng đừng đẩy mọi hợp đồng xuống application nếu chúng thực sự mô tả một khái niệm mà domain sở hữu. Hãy đặt abstraction nơi có trách nhiệm và ngôn ngữ phù hợp nhất để định nghĩa hợp đồng.

## 5. Dữ liệu ngoài cần được kiểm soát như thế nào?

Dữ liệu ngoài không phải lúc nào cũng đúng, mới hoặc sẵn sàng. Một quy tắc miền cần biết điều kiện sử dụng dữ liệu đó.

### Thời điểm và thời hạn hiệu lực

Một tỷ giá, báo giá vận chuyển hoặc đánh giá tín dụng thường có thời điểm tạo và thời hạn hiệu lực. Không nên chỉ lưu một con số mà bỏ qua ngữ cảnh của nó. Hãy cân nhắc biểu diễn:

- Thời điểm nguồn dữ liệu tạo ra giá trị.
- Thời điểm ứng dụng nhận hoặc sử dụng dữ liệu.
- Thời hạn hiệu lực hoặc chính sách hết hạn.
- Mã tham chiếu, phiên bản hoặc nguồn cung cấp nếu cần truy vết.

Quy tắc phải quyết định dùng thời điểm nào để kiểm tra hiệu lực. Ví dụ, một giao dịch có thể phải dùng tỷ giá tại thời điểm chốt giao dịch thay vì thời điểm hệ thống gửi request. Điều này cần được xác định trong chính sách nghiệp vụ.

### Thiếu dữ liệu và lỗi truy xuất

Các tình huống sau không nên bị nhập làm một:

| Tình huống | Ý nghĩa | Cách xử lý có thể chọn |
|---|---|---|
| Không tìm thấy dữ liệu | Nguồn trả lời hợp lệ nhưng không có bản ghi phù hợp | Từ chối, yêu cầu bổ sung hoặc chuyển kiểm tra thủ công |
| Dữ liệu hết hạn | Có dữ liệu nhưng không còn đủ điều kiện sử dụng | Lấy mới hoặc trả trạng thái chờ |
| Timeout / mất kết nối | Không biết nguồn có thể trả kết quả hay không | Retry có giới hạn, dùng cache hợp lệ hoặc chuyển trạng thái chờ |
| Dữ liệu không hiểu được | Schema hoặc mã trạng thái thay đổi ngoài dự kiến | Ghi nhận lỗi tích hợp và không tự suy đoán |
| Kết quả từ chối nghiệp vụ | Nguồn phản hồi rõ ràng rằng điều kiện không đạt | Áp dụng quy tắc từ chối tương ứng |

Đặc biệt, timeout của dịch vụ đánh giá tín dụng không đồng nghĩa khách hàng có rủi ro cao. Đó là hai sự kiện khác nhau và có thể dẫn đến hai kết quả nghiệp vụ khác nhau, chẳng hạn “chưa thể quyết định” thay vì “từ chối”.

### Cache và dữ liệu cũ

Cache có thể giảm độ trễ và tải cho hệ thống ngoài, nhưng cache thay đổi ý nghĩa của dữ liệu mà quy tắc sử dụng. Cần có chính sách rõ về thời hạn, phiên bản, invalidation và trường hợp nào được phép dùng dữ liệu cũ. Không nên âm thầm dùng giá trị đã hết hạn chỉ để hệ thống tiếp tục chạy.

Với giao dịch cần kiểm toán, hãy lưu snapshot hoặc mã tham chiếu của dữ liệu đã dùng để ra quyết định. Nếu chỉ lưu quyết định cuối cùng, sau này có thể không giải thích được vì sao quyết định đó được đưa ra khi dữ liệu nguồn đã thay đổi.

## 6. Giữ ranh giới giữa domain, application và infrastructure

Một cách chia trách nhiệm thực tế:

- **Domain:** định nghĩa ý nghĩa nghiệp vụ của dữ liệu, các value object, bất biến và chính sách ra quyết định.
- **Application:** xác định use case cần dữ liệu nào, khi nào lấy, thứ tự phối hợp, xử lý trạng thái chờ và lưu kết quả.
- **Infrastructure:** gọi API, truy vấn nguồn dữ liệu, chuyển đổi schema nhà cung cấp, cache, retry kỹ thuật và cấu hình kết nối.
- **Presentation:** nhận dữ liệu từ giao thức đầu vào và chuyển kết quả nghiệp vụ thành response phù hợp.

Một số dự án có thể đặt port trong application, số khác đặt trong domain. Dù chọn cách nào, implementation của adapter vẫn ở infrastructure và phụ thuộc vào abstraction. Domain không nên import package của Spring Web, SDK của nhà cung cấp hoặc DTO được sinh từ OpenAPI của hệ thống ngoài.

Không nên truyền một object response khổng lồ của nhà cung cấp xuyên qua nhiều layer. Hãy chuyển đổi ở ranh giới adapter thành một mô hình nhỏ, có kiểu rõ ràng, chỉ chứa thông tin cần thiết. Việc này giảm ảnh hưởng khi nhà cung cấp đổi tên field, định dạng ngày giờ hoặc cấu trúc response.

## 7. Kiểm thử quy tắc miền và điểm tích hợp

Tách dữ liệu ngoài khỏi quy tắc miền giúp kiểm thử ở nhiều mức:

1. **Unit test domain policy:** truyền dữ liệu hợp lệ, dữ liệu hết hạn, mức rủi ro cao và các ngưỡng khác nhau để xác minh quyết định.
2. **Unit test application service:** dùng fake hoặc mock cho port để xác minh application gọi đúng bước, xử lý thiếu dữ liệu và không lưu quyết định khi chưa đủ điều kiện.
3. **Contract test adapter:** xác minh adapter ánh xạ response thực tế của nhà cung cấp thành kiểu nội bộ đúng, bao gồm mã không nhận diện được và lỗi giao thức.
4. **Integration test:** kiểm tra cấu hình HTTP client, authentication, timeout, serialization và kết nối thật ở môi trường thử nghiệm phù hợp.

Ví dụ unit test cho chính sách có thể tập trung vào quyết định:

~~~java
@Test
void rejectsHighRiskAssessment() {
    CreditApprovalPolicy policy = new CreditApprovalPolicy();
    Customer customer = customerWithAvailableCredit(Money.of("5000"));
    RiskAssessment assessment = new RiskAssessment(
            RiskBand.HIGH,
            Instant.parse("2026-10-01T10:00:00Z"),
            Instant.parse("2026-10-02T10:00:00Z"),
            "RISK-123");

    CreditDecision decision = policy.evaluate(
            customer,
            Money.of("1000"),
            assessment,
            Instant.parse("2026-10-01T11:00:00Z"));

    assertFalse(decision.approved());
    assertEquals("RISK_TOO_HIGH", decision.reasonCode());
}
~~~

Unit test này không cần mock HTTP client vì domain chỉ nhận một **RiskAssessment** đã có sẵn. Một contract test riêng sẽ xác nhận **HttpRiskAssessmentAdapter** chuyển dữ liệu của nhà cung cấp thành giá trị trên đúng cách.

## 8. Những cách làm dễ tạo coupling

- **Entity tự gọi API:** entity gọi **WebClient** hoặc SDK để lấy tỷ giá khi tính giá. Điều này trộn hành vi domain với I/O và làm cho việc kiểm thử, tái sử dụng trở nên khó khăn.
- **Domain import DTO của vendor:** thay đổi schema ngoài có thể lan vào quy tắc nghiệp vụ. Adapter nên chuyển đổi DTO thành kiểu nội bộ.
- **Application truyền dữ liệu thô:** truyền một map hoặc JSON tùy ý khiến domain phải biết cấu trúc không có ý nghĩa nghiệp vụ. Hãy dùng value object có kiểu.
- **Đặt interface ở nơi không sở hữu hợp đồng:** interface kỹ thuật tổng quát không thể hiện nhu cầu thực của domain hoặc use case. Đặt port theo trách nhiệm và ngôn ngữ của bên cần nó.
- **Coi lỗi tích hợp là kết quả nghiệp vụ:** timeout không phải là từ chối, và dữ liệu thiếu không đồng nghĩa giá trị bằng không.
- **Giữ transaction mở khi chờ dịch vụ ngoài:** lời gọi mạng có thể chậm hoặc treo. Cần xác định ranh giới transaction và trạng thái xử lý phù hợp.
- **Dùng cache không có quy tắc hiệu lực:** dữ liệu cũ có thể dẫn đến quyết định sai mà không thể giải thích.

## 9. Checklist khi đưa dữ liệu ngoài vào quy tắc miền

Trước khi hoàn thiện thiết kế, hãy kiểm tra:

- Quy tắc nghiệp vụ thực sự cần dữ liệu nào và cần để quyết định điều gì?
- Khái niệm dữ liệu đã được biểu diễn bằng kiểu domain có ý nghĩa chưa?
- Application hay domain là nơi phù hợp để sở hữu hợp đồng truy xuất?
- Adapter có cô lập giao thức, SDK và schema của nhà cung cấp không?
- Dữ liệu có thời điểm tạo, thời hạn hiệu lực và nguồn tham chiếu khi cần không?
- Hệ thống phân biệt được dữ liệu không tồn tại, dữ liệu hết hạn, lỗi kết nối và kết quả từ chối nghiệp vụ không?
- Cache, retry, timeout và fallback có tuân theo chính sách nghiệp vụ không?
- Quy tắc miền có thể được kiểm thử độc lập bằng dữ liệu mẫu không?
- Quyết định có thể được truy vết về dữ liệu đã dùng khi cần kiểm toán không?

Khi domain cần dữ liệu ngoài, hãy đưa vào đúng ý nghĩa mà quy tắc nghiệp vụ cần và cung cấp nó qua một điểm phụ thuộc được đặt có chủ đích. Application có thể truy xuất trước rồi truyền dữ liệu đã chuẩn hóa vào domain; hoặc domain có thể sở hữu một port khi khả năng đó là một phần của chính sách miền. Trong cả hai trường hợp, adapter chịu trách nhiệm giao tiếp với thế giới bên ngoài, còn quy tắc miền tiếp tục được diễn đạt bằng ngôn ngữ nghiệp vụ và có thể kiểm thử độc lập.
