# Phân biệt tính đúng của phần mềm, chất lượng câu trả lời và sức khỏe hệ thống

Một API hỏi đáp sử dụng Spring AI trả về `HTTP 200 OK` sau 800 ms. Ứng dụng không phát sinh exception, model được gọi thành công, dashboard không có cảnh báo. Người dùng hỏi: “Gói Pro được hoàn phí trong bao lâu?” và nhận câu trả lời “30 ngày”, trong khi chính sách đang áp dụng ghi “14 ngày”.

Hệ thống trong ví dụ trên có vẻ **chạy tốt** nhưng đã **trả lời sai**. Nếu sau đó ứng dụng gọi công cụ hoàn phí mà không kiểm tra quyền của người dùng, nó còn mắc lỗi về **tính đúng của phần mềm**, dù câu trả lời bằng ngôn ngữ tự nhiên có thể tình cờ đúng.

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, việc đo chất lượng bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling phải đi cùng việc đo metrics, traces, chi phí và độ trễ. Trước khi thiết kế phép đo, cần phân biệt ba mục tiêu:

1. **Tính đúng của phần mềm (software correctness):** các thành phần thực thi đúng đặc tả, hợp đồng dữ liệu, quyền hạn và quy tắc nghiệp vụ hay chưa?
2. **Chất lượng câu trả lời (answer quality):** nội dung AI tạo ra có phù hợp, được bằng chứng hỗ trợ và đáp ứng yêu cầu người dùng hay chưa?
3. **Sức khỏe hệ thống (system health):** dịch vụ có sẵn sàng, ổn định, đủ nhanh và tiêu thụ tài nguyên trong ngân sách hay chưa?

Ba mục tiêu cùng quan trọng nhưng không thể suy ra mục tiêu này từ mục tiêu kia.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài học, người học có thể:

- Giải thích vì sao “không có lỗi HTTP” không chứng minh tính đúng của phần mềm hoặc tính chính xác của câu trả lời AI.
- Thiết kế phép kiểm tra phù hợp cho từng lớp: unit/integration/contract test, evaluation bằng dữ liệu, metrics/tracing.
- Phân biệt `relevance`, `factual correctness`, `groundedness` và hiệu quả truy xuất tài liệu trong RAG.
- Nhận diện một ứng dụng *ổn về latency nhưng chất lượng thấp*, hoặc *câu trả lời đúng nhưng luồng tool không an toàn*.
- Đọc kết quả đo theo từng phiên bản prompt, model, pipeline và tìm nguyên nhân suy giảm bằng trace.
- Thiết kế tiêu chí phát hành độc lập cho chức năng, chất lượng AI và vận hành.

## 2. Ba lớp kiểm chứng có câu hỏi khác nhau

| Khía cạnh | Tính đúng của phần mềm | Chất lượng câu trả lời | Sức khỏe hệ thống |
| --- | --- | --- | --- |
| Câu hỏi cốt lõi | “Ứng dụng thực hiện đúng hợp đồng và nghiệp vụ không?” | “Người dùng nhận được thông tin phù hợp và đáng tin không?” | “Ứng dụng có phục vụ ổn định và hiệu quả không?” |
| Phạm vi chính | Java code, API, phân quyền, schema, adapter, giao dịch, lời gọi tool | Câu trả lời, bằng chứng, trích dẫn, từ chối khi thiếu dữ liệu, kết quả RAG | Availability, throughput, error rate, latency, token, cost, tải tài nguyên |
| Tín hiệu điển hình | Assertion, test result, exception, invariant, trạng thái sau giao dịch | Rubric, nhãn dataset, đánh giá của chuyên gia, evaluator score/pass | Metrics, traces, logs, SLI/SLO, cảnh báo |
| Phương pháp | Unit test, integration test, contract test, property test | Golden dataset, kiểm tra dựa trên quy tắc, LLM-as-a-judge, human review | Micrometer, tracing, dashboard, profiling, cảnh báo |
| Ví dụ lỗi | Gọi tool hoàn tiền hai lần; bỏ qua phân quyền | Tự bịa “30 ngày”; trích nguồn không liên quan | p95 = 10 giây; quá nhiều retry; tăng chi phí |
| Có được đảm bảo khi HTTP 200 không? | **Không** | **Không** | **Không**, vì một request thành công không thể hiện toàn bộ hệ thống |

Một ứng dụng có thể đạt cả ba, chỉ đạt một hoặc hai, hoặc không đạt lớp nào. **Mọi kết luận phải nêu rõ đang nói về lớp nào và bằng chứng dùng để kết luận.**

### 2.1. Hình dung theo hành trình request

~~~mermaid
flowchart TD
    A["Người dùng hỏi"] --> B["API / xác thực / validation"]
    B --> C["Spring AI orchestration"]
    C --> D["RAG retrieval hoặc gọi tool"]
    D --> E["ChatModel tạo phản hồi"]
    E --> F["Trả câu trả lời"]

    B -.-> G["Software correctness<br/>schema, quyền, trạng thái"]
    C -.-> G
    D -.-> G
    F -.-> H["Answer quality<br/>relevance, evidence, facts"]
    B -.-> I["System health<br/>error, latency, throughput"]
    D -.-> I
    E -.-> I
~~~

Sơ đồ chỉ ra **nơi quan sát** của ba lớp; không có nghĩa chúng hoạt động tách rời tuyệt đối. Chẳng hạn, một lỗi parsing trong Java có thể làm mất tài liệu RAG, khiến câu trả lời không có căn cứ. Ngược lại, tăng `top-k` để cải thiện retrieval có thể làm prompt dài hơn, tăng độ trễ và chi phí.

## 3. Tính đúng của phần mềm là gì?

Trong hệ thống Java/Spring Boot, tính đúng của phần mềm thể hiện ở việc mã chạy phù hợp với đặc tả đã xác định. Nhiều yêu cầu có thể kiểm tra **xác định**: cùng đầu vào và trạng thái được kiểm soát, ta có thể so sánh với kết quả kỳ vọng.

Đối với ứng dụng Spring AI, phạm vi này rộng hơn việc controller trả về đúng mã HTTP:

- **Đầu vào và hợp đồng API:** kiểm tra trường bắt buộc, kiểu dữ liệu, giới hạn độ dài, định dạng JSON và mã lỗi.
- **Xác thực, phân quyền:** chỉ cho phép người dùng xem hoặc thay đổi dữ liệu mà họ được quyền truy cập; bộ lọc truy xuất RAG cũng phải tôn trọng quyền này.
- **Quy tắc nghiệp vụ:** số tiền, thời hạn, trạng thái đơn hàng, quy trình xác nhận, điều kiện hoàn phí.
- **Điều phối pipeline:** gọi đúng bước khi điều kiện phù hợp, truyền đủ thông số, xử lý ngoại lệ, timeout và retry.
- **Tool calling:** tên tool và tham số hợp lệ; thao tác có tác dụng phụ được xác nhận, giới hạn quyền, không thực thi lặp ngoài ý muốn.
- **Trạng thái sau thao tác:** giao dịch được ghi đúng một lần, không mất hoặc nhân đôi dữ liệu, không trả “thành công” khi hệ thống đích thất bại.

### 3.1. Ví dụ: kiểm thử quy tắc nghiệp vụ trước khi đưa AI vào

Giả sử chính sách **minh họa** quy định gói Pro hoàn phí trong vòng 14 ngày kể từ ngày mua, còn Basic không hỗ trợ. Quy tắc này nên được lập trình và kiểm tra như mã Java thông thường nếu ứng dụng thực hiện hành động hoàn phí.

~~~java
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;

public final class RefundPolicy {

    public boolean isRefundEligible(
            String plan,
            LocalDate purchaseDate,
            LocalDate requestDate) {

        if (!"PRO".equals(plan)) {
            return false;
        }
        long elapsedDays = ChronoUnit.DAYS.between(purchaseDate, requestDate);
        return elapsedDays >= 0 && elapsedDays <= 14;
    }
}
~~~

Ví dụ unit test với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class RefundPolicyTest {

    private final RefundPolicy policy = new RefundPolicy();
    private final LocalDate purchased = LocalDate.of(2026, 5, 1);

    @Test
    void proWithinFourteenDaysIsEligible() {
        assertTrue(policy.isRefundEligible("PRO", purchased, purchased.plusDays(14)));
    }

    @Test
    void proAfterFourteenDaysIsNotEligible() {
        assertFalse(policy.isRefundEligible("PRO", purchased, purchased.plusDays(15)));
    }

    @Test
    void basicPlanIsNotEligible() {
        assertFalse(policy.isRefundEligible("BASIC", purchased, purchased.plusDays(2)));
    }

    @Test
    void futurePurchaseDateIsRejected() {
        assertFalse(policy.isRefundEligible("PRO", purchased, purchased.minusDays(1)));
    }
}
~~~

Các test này xác nhận **hàm nghiệp vụ**, chưa xác nhận chatbot diễn giải chính sách đúng. Nếu model trả lời “30 ngày” mà `RefundPolicy` vẫn tính đúng 14 ngày, unit test có thể xanh trong khi chất lượng câu trả lời vẫn không đạt.

Ngoài ra, `RefundPolicy` chỉ mô phỏng chính sách đơn giản để học. Ứng dụng thực cần xem xét múi giờ, thời điểm tính theo giờ hay theo ngày, hiệu lực chính sách, ngoại lệ và nguồn dữ liệu đáng tin.

### 3.2. Phân biệt lỗi phần mềm và hành vi xác suất

Đầu ra model có thể khác câu chữ mỗi lần chạy mà vẫn hợp lệ. Điều đó không tự động là bug của Java code. Mặt khác, nếu ứng dụng quên truyền lịch sử hội thoại vào prompt dù đặc tả yêu cầu, đây là lỗi điều phối **có thể kiểm thử bằng assertion**, ngay cả khi model đôi khi vẫn trả lời đúng.

Chia trách nhiệm kiểm thử theo tầng:

| Tầng | Ví dụ kiểm tra xác định |
| --- | --- |
| API | Request thiếu `question` trả lỗi validation theo hợp đồng |
| Quyền | Người dùng A không truy xuất được tài liệu chỉ thuộc người dùng B |
| Retrieval adapter | Bộ lọc `tenantId` được áp dụng trước khi lấy kết quả |
| Prompt assembly | Đưa đúng phiên bản nguồn và hướng dẫn an toàn vào template |
| Tool dispatcher | Chỉ gọi tool được cho phép với đối số có schema hợp lệ |
| Giao dịch | Một yêu cầu hợp lệ không gây hai lần hoàn phí |

**Nguyên tắc:** mọi bất biến có thể mô tả bằng logic và kiểm tra xác định thì nên có test thông thường; không cần giao cho một LLM khác quyết định đúng/sai.

## 4. Chất lượng câu trả lời là gì?

Chất lượng câu trả lời là mức độ kết quả AI giải quyết đúng mục đích người dùng trong bối cảnh cụ thể. Tính đúng ngữ nghĩa khó biểu diễn bằng một chuỗi ký tự mong đợi duy nhất.

Ví dụ, hai cách trả lời sau có thể đều đúng với cùng một chính sách:

> “Gói Pro được hoàn phí trong vòng 14 ngày kể từ ngày mua.”

> “Bạn có 14 ngày tính từ ngày mua để yêu cầu hoàn phí cho gói Pro.”

So khớp chuỗi tuyệt đối sẽ đánh trượt một biến thể dù không có lỗi thực chất. Nhưng chấp nhận mọi câu có từ “Pro” hoặc “hoàn phí” lại quá dễ dãi. Cần tiêu chí chấm nội dung.

### 4.1. Những tiêu chí dễ bị nhầm lẫn

| Tiêu chí | Câu hỏi kiểm tra | Ví dụ lỗi |
| --- | --- | --- |
| **Relevance** (liên quan) | Câu trả lời có giải quyết câu hỏi không? | Người dùng hỏi thời hạn, bot mô tả giá gói |
| **Factual correctness** (đúng sự thật/quy định) | Có đúng so với nguồn sự thật được xác minh không? | Nói 30 ngày khi chính sách thực tế là 14 |
| **Groundedness / faithfulness** (có căn cứ) | Các khẳng định có được ngữ cảnh cung cấp hỗ trợ không? | Tài liệu chỉ ghi 14 ngày, bot thêm “miễn mọi điều kiện” |
| **Completeness** (đầy đủ) | Có đáp ứng đủ các phần quan trọng trong câu hỏi không? | Nêu 14 ngày nhưng bỏ qua điều kiện bắt buộc |
| **Citation accuracy** (trích dẫn đúng) | Link/ID nguồn có thật sự hỗ trợ khẳng định không? | Dẫn tài liệu gói Basic cho chính sách gói Pro |
| **Abstention / uncertainty** (biết từ chối khi thiếu dữ liệu) | Khi không đủ bằng chứng, bot có tránh đoán không? | Bịa chính sách ngoại lệ chưa có tài liệu |

Đặc biệt:

- **Relevance không phải correctness:** câu “30 ngày” hoàn toàn liên quan tới câu hỏi về thời hạn, nhưng có thể sai.
- **Groundedness không phải sự thật toàn cục:** nếu ứng dụng truy xuất một tài liệu cũ ghi 30 ngày và trả lời đúng theo tài liệu đó, kết quả có thể grounded nhưng sai so với chính sách hiện hành.
- **Trích dẫn tồn tại không đồng nghĩa trích dẫn đúng:** đường dẫn hợp lệ nhưng không hỗ trợ khẳng định là lỗi chất lượng.
- **Chính xác một phần chưa chắc đạt:** trong câu hỏi hai vế, một vế đúng nhưng vế kia thiếu hoặc sai có thể không đạt rubric.

### 4.2. Dataset và rubric cho chất lượng câu trả lời

Xây dựng một tập ca kiểm thử phản ánh hành vi người dùng, mỗi ca có câu hỏi, nguồn tham chiếu, điều kiện đạt và điều kiện thất bại.

~~~yaml
datasetVersion: refund-quality-v1
cases:
  - id: REFUND-001
    question: "Gói Pro hoàn phí trong bao lâu?"
    referenceDocument: "refund-policy-v3#pro"
    expectedFacts:
      - "Thời hạn 14 ngày kể từ ngày mua"
    forbiddenClaims:
      - "Thời hạn 30 ngày"
      - "Hoàn phí vô điều kiện"
    expectedRetrievalIds:
      - "refund-policy-v3#pro"
    rubric:
      relevant: "Trả lời về thời hạn hoàn phí của Pro"
      factuallyCorrect: "Đúng 14 ngày, không bịa ngoại lệ"
      grounded: "Khẳng định được nguồn tham chiếu hỗ trợ"

  - id: REFUND-002
    question: "Nếu đã quá 14 ngày nhưng có mã khuyến mãi thì sao?"
    referenceDocument: "refund-policy-v3#pro"
    expectedFacts: []
    expectedBehavior: "Không khẳng định ngoại lệ chưa được tài liệu xác nhận"
    rubric:
      abstention: "Thừa nhận thiếu thông tin, hướng tới kênh hỗ trợ"
~~~

Thông tin chính sách trong dataset là **dữ liệu giả định để thực hành**. Khi dùng thật, bộ kiểm thử cần lưu phiên bản nguồn đáng tin, thời điểm có hiệu lực và người/nhóm xác minh nhãn.

Có thể chấm bằng nhiều phương pháp:

1. **Kiểm tra xác định:** JSON đúng schema, có nguồn bắt buộc, không chứa mã nhạy cảm, giá trị số chính xác trong đầu ra có cấu trúc.
2. **So sánh nội dung với đáp án chuẩn:** kiểm tra các ý bắt buộc, có thể dùng quy tắc hoặc mô hình chấm.
3. **LLM-as-a-judge:** dùng evaluator kiểm tra relevance/groundedness với rubric cụ thể, lưu feedback để xem xét.
4. **Human review:** chuyên gia đánh giá ca rủi ro cao, mơ hồ, tranh chấp hoặc ca mà các bộ chấm không thống nhất.

Spring AI có các evaluator như `RelevancyEvaluator` và `FactCheckingEvaluator` để hỗ trợ đánh giá câu trả lời. **Evaluator cũng là một phần mềm có sai số**, nhất là khi dùng LLM để chấm. Phải kiểm tra độ phù hợp của evaluator với nhãn con người; tránh coi mọi kết quả `pass` là chân lý.

### 4.3. Trong RAG, cần kiểm tra retrieval và generation riêng

Luồng RAG có ít nhất hai chỗ có thể làm chất lượng giảm:

~~~mermaid
flowchart LR
    Q["Câu hỏi"] --> R["Retrieval<br/>VectorStore / filter"]
    R --> C["Tài liệu thực tế<br/>đã truy xuất"]
    C --> M["Model sinh<br/>câu trả lời"]
    M --> A["Câu trả lời"]
    R -.-> ER["Đánh giá retrieval<br/>hit@k, recall@k"]
    A -.-> EG["Đánh giá câu trả lời<br/>relevance, groundedness"]
~~~

**Retrieval failure:** chính sách 14 ngày không nằm trong các tài liệu tìm được. Model không có bằng chứng cần thiết. Cần xem index, embedding, cách chia đoạn, bộ lọc metadata, `top-k`.

**Generation failure:** tài liệu đúng đã nằm trong context nhưng model trả lời 30 ngày. Cần xem prompt, cấu trúc ngữ cảnh, cách diễn giải, model và yêu cầu trích dẫn.

Với dataset có nhãn tài liệu liên quan, có thể tính `Recall@k` để đánh giá retrieval. Ví dụ một câu có 2 đoạn liên quan đã gắn nhãn, kết quả `top-5` chỉ chứa 1 trong 2 đoạn thì `Recall@5 = 1/2 = 50%`. Chỉ số này không chứng minh rằng câu trả lời cuối cùng sẽ đúng.

Để chấm groundedness của một lần chạy, cần cung cấp **các đoạn thực sự được truy xuất trong lần chạy đó**. Đưa đáp án chuẩn hoặc tài liệu lý tưởng vào bộ chấm thay cho ngữ cảnh thực tế sẽ che giấu lỗi retrieval.

### 4.4. Với tool calling, chất lượng và tính đúng phần mềm giao nhau

Người dùng yêu cầu “Xem trạng thái đơn DH-123”. Model nói “đang giao” nhưng **không hề gọi công cụ kiểm tra đơn hàng**.

- **Chất lượng câu trả lời:** kết luận không có căn cứ từ trạng thái thực tế, dù câu chữ thuyết phục.
- **Tính đúng phần mềm:** nếu đặc tả yêu cầu mọi truy vấn trạng thái phải đi qua `getOrderStatus`, quá trình điều phối đã không đáp ứng hợp đồng.
- **Sức khỏe hệ thống:** lời gọi vẫn có thể nhanh, HTTP 200 và không lỗi.

Khi kiểm thử, chấm cả quyết định dùng tool, tên tool, tham số, kết quả trả về, trạng thái sau thao tác và cách model diễn giải kết quả. Dùng test double hoặc sandbox cho các tool gây thay đổi dữ liệu. Không bao giờ dùng điểm relevance của câu trả lời để thay thế kiểm tra phân quyền và tác dụng phụ của tool.

## 5. Sức khỏe hệ thống là gì?

Sức khỏe hệ thống là khả năng ứng dụng duy trì chất lượng dịch vụ về mặt kỹ thuật và vận hành theo thời gian. Một request chạy tốt không chứng minh dịch vụ khỏe: điều quan trọng là **phân bố kết quả của nhiều request**, trên nhiều đường đi và trong các tình trạng tải khác nhau.

Các tín hiệu phổ biến:

| Chỉ số/tín hiệu | Điều phản ánh | Cảnh báo khi diễn giải |
| --- | --- | --- |
| **Availability** | Dịch vụ có xử lý yêu cầu hợp lệ thành công không | HTTP 200 không phản ánh độ đúng ngữ nghĩa |
| **Error rate** | Tỷ lệ lỗi API, model, retrieval, tool, timeout | Một model trả lời sai vẫn có thể không phát sinh lỗi kỹ thuật |
| **Latency** | Thời gian hoàn tất request và từng bước | Average không thay cho p95/p99; streaming còn có TTFT |
| **Throughput** | Lượng request xử lý trên một đơn vị thời gian | Cao hơn không tự động nghĩa là tốt nếu chất lượng giảm |
| **Token usage** | Token input/output và số lượt gọi model | Provider có thể báo usage khác nhau hoặc thiếu trường |
| **Cost** | Giá trị ước tính/tính tiền theo usage và hạ tầng | Không nên đồng nhất chi phí ước tính với hóa đơn thực |
| **Saturation** | Mức sử dụng tài nguyên, hàng đợi, giới hạn kết nối/rate | Thiếu tài nguyên có thể làm timeout hoặc retry tăng |
| **Traces** | Đường đi request: retrieval, model, tool, retry | Trace giải thích quá trình; tự nó không chấm được câu trả lời |

Trong hệ sinh thái Spring Boot/Spring AI, **Micrometer** và cơ chế **observation/tracing** cung cấp hạ tầng đo cho các thành phần như ChatClient, ChatModel, VectorStore và tool, với mức hỗ trợ tùy phiên bản. Spring Boot Actuator có thể cung cấp endpoint metrics; collector/registry như Prometheus hoặc OpenTelemetry dùng để hiển thị và phân tích sau khi được cấu hình.

### 5.1. Metrics, traces và logs làm việc cùng nhau

- **Metrics:** trả lời “Trong 5 phút qua, p95 latency và tỷ lệ lỗi biến động thế nào?” bằng dữ liệu tổng hợp.
- **Traces:** trả lời “Request này mất thời gian ở VectorStore hay ChatModel?”, “Tool có được gọi không?”, “Có retry không?” qua các span liên kết.
- **Logs/events:** trả lời “Lỗi xảy ra tại điều kiện nào, với mã lỗi nào?” và cung cấp thông tin cụ thể để chẩn đoán.

Ví dụ một trace logic:

~~~text
POST /chat                                     3.8 s
└── ChatClient                                 3.6 s
    ├── Advisor / RAG retrieval                0.4 s
    │   └── VectorStore query                  0.3 s
    ├── ChatModel (gọi tool)                    1.1 s
    ├── getOrderStatus tool                     0.6 s
    └── ChatModel (tổng hợp câu trả lời)        1.5 s
~~~

Các span có thể lồng nhau: không cộng thời gian span cha với toàn bộ span con như các khoảng độc lập. Muốn phân tích độ trễ của từng bước, xem thời gian thực thi và quan hệ cha–con, các đoạn chạy song song, retry và phần thời gian chờ.

### 5.2. SLI, SLO và SLA

- **SLI (Service Level Indicator):** thước đo thực tế, chẳng hạn tỷ lệ request hoàn tất trong thời hạn.
- **SLO (Service Level Objective):** mục tiêu nội bộ cho SLI, chẳng hạn “99% request trong 30 ngày đáp ứng dưới 3 giây”.
- **SLA (Service Level Agreement):** cam kết mức dịch vụ với bên sử dụng và có thể gắn điều khoản xử lý vi phạm.

Các ngưỡng trên chỉ là **ví dụ**, không phải mặc định của Spring AI. Khi xây dựng SLO, phải xác định rõ phạm vi request, loại trừ hợp lệ, khoảng thời gian, cách ghi nhận streaming và thế nào là “thành công”.

Điểm cần nhớ: **đạt SLO độ trễ không chứng minh model trả lời đúng**. Nếu yêu cầu có rủi ro cao, có thể đặt thêm *quality SLO* hoặc *quality release gate* dựa trên bộ dữ liệu đánh giá, nhưng phải mô tả riêng ranh giới đo và độ tin cậy của nhãn.

### 5.3. Token và chi phí không phải chất lượng

Một prompt dài hơn có thể giúp câu trả lời có căn cứ hơn, nhưng cũng tăng token input, thời gian xử lý và chi phí. Không thể kết luận “ứng dụng tốt hơn” chỉ từ việc số token giảm.

Cách tính chi phí model giản lược, với giá cung cấp theo mỗi triệu token:

\[
\text{Cost} =
\frac{\text{inputTokens} \times \text{pricePerMillionInput}}{10^6}
+
\frac{\text{outputTokens} \times \text{pricePerMillionOutput}}{10^6}
\]

Ví dụ giả định, 2.000 input tokens với giá 2 USD/triệu và 500 output tokens với giá 8 USD/triệu tạo chi phí \((2000 \times 2 + 500 \times 8)/10^6 = 0{,}008\) USD. Con số này **chưa gồm** embedding, reranking, vector store, retry, cache hoặc phí chấm evaluator. Giá chỉ để minh họa; khi đo hệ thống thật cần dùng giá và quy tắc tính của nhà cung cấp tại thời điểm tương ứng.

Theo dõi cả **chi phí trên một câu trả lời đáp ứng chất lượng**. Nếu một pipeline rẻ nhưng 20% câu trả lời phải xử lý lại, chi phí trên request có thể đánh lừa quyết định thiết kế.

## 6. Những tổ hợp đúng/sai thường gặp

Giả định ba lớp được kiểm tra trên một yêu cầu cụ thể. Bảng sau cho thấy các cách hiểu khác nhau:

| Software correctness | Answer quality | System health | Diễn giải |
| --- | --- | --- | --- |
| Đạt | Đạt | Đạt | Hành vi đúng, thông tin có chất lượng, vận hành trong giới hạn |
| Đạt | **Không đạt** | Đạt | Pipeline chạy đúng đặc tả nhưng model diễn giải sai hoặc nguồn thiếu |
| Đạt | Đạt | **Không đạt** | Đáp án đúng nhưng chậm, timeout nhiều hoặc vượt ngân sách |
| **Không đạt** | Đạt | Đạt | Có thể trả lời đúng “do may mắn” nhưng vi phạm phân quyền/schema/quy tắc |
| **Không đạt** | **Không đạt** | Đạt | Vận hành trông ổn, cả logic lẫn nội dung đều gặp lỗi |
| Đạt | **Không đạt** | **Không đạt** | Có cả vấn đề chất lượng và vận hành, cần điều tra hai nhánh |
| **Không đạt** | Đạt | **Không đạt** | Trả lời đúng một ca nhưng quy trình không an toàn và vận hành kém |
| **Không đạt** | **Không đạt** | **Không đạt** | Hỏng trên cả ba mục tiêu |

Đây là phân loại để **chẩn đoán**, không phải điểm số tự động. Cùng một lỗi gốc có thể ảnh hưởng nhiều lớp. Một request bị timeout cũng khiến người dùng không nhận được câu trả lời chất lượng; khi tính chỉ số, cần quy định rõ ca “không có câu trả lời” được tính vào nhóm lỗi kỹ thuật, quality failure hay cả hai để tránh che giấu dữ liệu.

## 7. Chọn phép đo đúng cho từng câu hỏi

Để đánh giá một ứng dụng Spring AI, nên hình thành ba tập kiểm tra rõ ràng.

### 7.1. Functional correctness suite

Kiểm tra những hợp đồng mà code bắt buộc phải tuân thủ:

~~~text
[PASS] JSON request đúng schema
[PASS] Người dùng không có quyền không đọc được tài liệu nội bộ
[PASS] Tool được gọi với orderId chính xác
[PASS] Không gọi hai lần hành động hoàn phí
[PASS] Tool timeout được xử lý theo hợp đồng
[PASS] Không đánh dấu giao dịch thành công khi backend từ chối
~~~

Các phép kiểm lý tưởng nên chạy nhanh, ổn định, dùng stub/fake cho thành phần ngoài khi thích hợp và có test tích hợp cho ranh giới thực. Đừng dùng LLM judge để quyết định xem biến `orderId` có đúng kiểu dữ liệu hay không.

### 7.2. Answer quality evaluation suite

Dựa trên dataset và rubric:

~~~text
[CASE REFUND-001]
question: "Gói Pro được hoàn phí bao lâu?"
expectedEvidence: refund-policy-v3#pro
expectedFact: 14 ngày
relevance: PASS
groundedness: FAIL
factualCorrectness: FAIL
retrievalHitAt5: PASS
reason: "Model trả lời 30 ngày dù tài liệu 14 ngày đã ở trong context"
~~~

Nếu `retrievalHitAt5` là PASS còn factual correctness là FAIL, tập trung xem khâu generation. Nếu retrieval là FAIL, cần điều tra truy xuất trước. Lưu feedback/rubric thay vì chỉ một con số `passRate`.

### 7.3. Operational health suite

Theo dõi theo phiên bản triển khai và khoảng thời gian đo:

~~~text
[RUN candidate-v2]
requestCount: 10000
technicalErrorRate: 0.4%
p95LatencyMs: 2700
averageInputTokens: 2400
averageOutputTokens: 380
estimatedModelCostUsdPerRequest: 0.0078
modelTimeoutCount: 12
~~~

Các số liệu là **minh họa**, không phải kết quả chạy thật. Nhìn chúng có thể biết dịch vụ nhanh/chậm và tiêu thụ tài nguyên thế nào, nhưng chưa biết 10.000 câu trả lời có đúng hay không.

## 8. Thống nhất dữ liệu kết quả để tìm nguyên nhân

Ba lớp nên được báo cáo riêng nhưng có **khóa liên kết an toàn** để tra cứu cùng một lần chạy đánh giá. Ví dụ:

~~~json
{
  "evaluationRunId": "eval-2026-05-18-candidate-v2",
  "caseId": "REFUND-001",
  "datasetVersion": "refund-quality-v1",
  "promptVersion": "prompt-v4",
  "model": "model-candidate",
  "corpusVersion": "refund-policy-v3",
  "pipelineVersion": "rag-v2",
  "softwareChecks": {
    "authorized": true,
    "schemaValid": true,
    "toolContractValid": true
  },
  "answerQuality": {
    "relevancePass": true,
    "groundednessPass": false,
    "factualCorrectnessPass": false
  },
  "operational": {
    "httpStatus": 200,
    "latencyMs": 1220,
    "inputTokens": 1850,
    "outputTokens": 155
  },
  "traceId": "trace-id-from-telemetry"
}
~~~

Tập dữ liệu báo cáo chỉ nên chứa metadata cần thiết. **Không dùng nguyên văn prompt hay ID người dùng làm nhãn metric**: điều này dễ rò rỉ dữ liệu nhạy cảm và tạo cardinality cao. Nếu cần điều tra một request cụ thể, dùng trace ID trong hệ thống có phân quyền, chính sách che dữ liệu và thời gian lưu phù hợp.

### 8.1. Từ phát hiện đến giả thuyết

Giả sử tỷ lệ groundedness giảm sau khi chuyển `rag-v1` sang `rag-v2`. Dựa vào từng lớp, đặt câu hỏi theo thứ tự:

1. **Phát hiện có đáng tin không?** Cùng dataset/rubric/judge hay đã đổi cách chấm? Có đủ mẫu? Các nhóm câu hỏi bị ảnh hưởng là gì?
2. **Tài liệu nào đã được truy xuất?** `hit@k`, `Recall@k`, phiên bản nguồn, bộ lọc, chunk và thứ tự kết quả có thay đổi?
3. **Model đã nhận gì?** Prompt thực tế có chứa đoạn chứng cứ cần thiết, có bị cắt ngắn do giới hạn context không?
4. **Vận hành có thay đổi không?** Trace có retry, timeout, token tăng, công cụ trả lỗi hoặc provider đổi tuyến không?
5. **Có lỗi logic điều phối không?** Có bỏ qua advisor, gắn nhầm nguồn, áp dụng sai quyền hoặc thiếu bước tool không?

Ví dụ từ dữ liệu:

| Quan sát | Kết luận có thể nêu | Không thể kết luận chỉ từ quan sát đó |
| --- | --- | --- |
| HTTP 200, latency thấp | Request được xử lý thành công về mặt HTTP và nhanh | Nội dung câu trả lời đúng |
| Retrieval Recall@5 giảm | Bộ truy xuất tìm thiếu tài liệu liên quan đã gắn nhãn | Model chắc chắn gây ra lỗi |
| Relevance đạt, groundedness giảm | Trả lời vẫn đúng chủ đề nhưng thiếu bằng chứng hỗ trợ | Tài liệu nền chắc chắn đúng và mới nhất |
| Span ChatModel tăng mạnh | Thời gian gọi model đang tăng | Model suy luận chính xác hơn |
| Tool trả 403 và model nói “hoàn phí thành công” | Có lỗi hành vi/diễn giải cần điều tra | Giao dịch backend đã hoàn tất |
| Input tokens tăng 70% | Context/prompt/đường gọi có thể dài hơn | Chất lượng tốt hơn |

**Correlation không tự chứng minh causation.** Số liệu giúp khoanh vùng; muốn xác minh nguyên nhân cần đối chiếu phiên bản và thử thay đổi có kiểm soát.

## 9. Quality gate, correctness gate và health gate

Ba loại tiêu chí có thể cùng nằm trong pipeline phát hành nhưng **phải kiểm tra độc lập**. Không nên cộng mọi thứ thành một điểm trung bình: điểm chất lượng cao không bù được lỗi phân quyền nghiêm trọng.

Ví dụ **ngưỡng giả định cho một dự án thực hành**:

| Gate | Điều kiện | Kết quả nếu không đạt |
| --- | --- | --- |
| Software correctness | 100% test phân quyền, hợp đồng tool và bất biến nghiệp vụ quan trọng đạt | Chặn phát hành |
| Answer quality | Groundedness ≥ 95%; factual correctness ≥ 98% trên dataset đã duyệt; 100% ca từ chối nguy hiểm bắt buộc đạt | Xem xét lỗi theo nhóm, chặn nếu vi phạm tiêu chí trọng yếu |
| System health | p95 end-to-end ≤ 2,5 giây theo tải kiểm thử; error rate ≤ 1%; chi phí/request trong ngân sách | Điều chỉnh và kiểm thử lại trước khi mở rộng |
| Regression | Không xuất hiện lỗi mới ở bộ case đã biết rủi ro cao | Chặn hoặc yêu cầu phê duyệt ngoại lệ rõ ràng |

Đây **không phải chuẩn chung** cho mọi ứng dụng. Ngưỡng phải được xác lập theo yêu cầu sản phẩm, mức rủi ro, tải, kích thước dataset và chất lượng nhãn.

### 9.1. Chất lượng là thước đo có sai số

Ví dụ tỷ lệ pass 95% trên chỉ 20 câu tương đương 19 câu đạt. Kết quả có thể dao động lớn khi thêm vài câu. Với tác vụ có rủi ro cao, cần dataset đủ đa dạng, kiểm tra phân nhóm, xem bất định thống kê và tiến hành đánh giá chuyên gia. Chỉ báo điểm tổng khi chưa báo **số mẫu, cách lấy mẫu và phiên bản rubric** sẽ dễ gây hiểu nhầm.

Nếu chấm bằng LLM, độ ngẫu nhiên và thiên lệch của judge cũng cần được đo. Có thể giữ một bộ trường hợp đã gắn nhãn bởi chuyên gia để so sánh đánh giá tự động, xem mẫu dương tính giả/âm tính giả, hoặc chạy lặp một số trường hợp khó.

### 9.2. So sánh công bằng giữa các phiên bản

Khi so `prompt-v1` và `prompt-v2`:

- Dùng cùng bộ câu hỏi, nhãn, nguồn chuẩn và rubric; ghi riêng corpus/index nếu phải đổi.
- Ghi model/provider, tham số sinh, cấu hình tool, `top-k`, bộ lọc và chính sách retry.
- Báo cáo các nhóm case tăng/giảm điểm, không chỉ điểm trung bình.
- Đo cả latency/token/cost trong điều kiện tải tương tự.
- Phân tách chi phí của ứng dụng khỏi chi phí chạy evaluator.
- Giữ lại trace của case lỗi để phát hiện nguyên nhân thay vì chỉ so sánh thống kê tổng.

Vì model có tính xác suất, hai lần chạy cùng cấu hình có thể tạo khác biệt. Với phép so sánh quan trọng, nên chạy nhiều lần hoặc có thiết kế thống kê phù hợp; ghi rõ biến nào được cố định và biến nào chưa kiểm soát được.

## 10. Tình huống tổng hợp: một chatbot chính sách có ba vấn đề

Xét chatbot hỗ trợ khách hàng sử dụng Spring AI, VectorStore và tool `refundOrder`. Chính sách giả định: gói Pro chỉ được hoàn phí trong 14 ngày, hành động hoàn phí cần xác thực quyền sở hữu đơn hàng.

Bản triển khai mới có ba triệu chứng:

1. Khách hỏi về thời hạn nhận câu trả lời “30 ngày”.
2. Khi nhờ hoàn tiền, một số request gọi `refundOrder` mà thiếu kiểm tra chủ sở hữu.
3. Trong giờ cao điểm, p95 latency tăng từ 2,0 lên 5,5 giây.

**Phân loại ban đầu:**

- **Software correctness:** lỗi kiểm tra quyền ở luồng tool, phải khắc phục bằng mã/backend policy và kiểm thử phân quyền; không thể chỉ sửa prompt để đảm bảo an toàn.
- **Answer quality:** câu “30 ngày” sai với chính sách giả định. Kiểm tra tài liệu RAG đã truy xuất và rubric groundedness/factual correctness.
- **System health:** p95 vượt mục tiêu giả định, xem traces để tìm span chậm và lỗi retry; không dùng điểm đúng/sai của câu trả lời để thay thế phân tích latency.

**Hướng xử lý:** trước tiên bảo vệ hành động có tác dụng phụ bằng kiểm tra quyền bắt buộc ở backend, sau đó đối chiếu RAG context của case trả lời sai; đồng thời dùng telemetry để xác định bước gây chậm. Mỗi bản sửa phải có bài kiểm tra hồi quy tương ứng, đo cả những tác động ngoài ý muốn lên hai lớp còn lại.

Đây là lý do “model tốt hơn” hay “server khỏe hơn” không thể thay thế chiến lược kiểm chứng toàn diện.

## 11. Thực hành: thiết kế bộ đo ba lớp

**Bối cảnh:** Xây dựng mini chatbot Spring AI hỏi đáp chính sách dịch vụ giả định, có RAG và một tool đọc trạng thái đơn. Chọn ít nhất 12 câu hỏi gồm câu thường gặp, câu không có nguồn, câu có nhiều điều kiện và câu yêu cầu tool.

**Bước 1 — Xác định bất biến phần mềm.** Viết test kiểm tra phân quyền tài liệu, schema đầu vào, tool chỉ nhận ID đơn hợp lệ, và không làm lộ thông tin đơn của người khác.

**Bước 2 — Xây dựng rubric chất lượng.** Với mỗi câu có nguồn, lưu nguồn chính xác và phiên bản, điều kiện đúng/sai, kỳ vọng có/không gọi tool; với câu không có nguồn, ghi rõ hành vi từ chối hoặc yêu cầu làm rõ.

**Bước 3 — Thu tín hiệu sức khỏe.** Theo dõi mã trạng thái, error rate, p50/p95, độ trễ VectorStore/ChatModel/tool, token input/output, số retry và chi phí ước tính. Dùng một trace ID để điều tra một request chậm.

**Bước 4 — Cố ý tạo ba loại lỗi trong môi trường thử nghiệm.**

| Thay đổi thử nghiệm | Kỳ vọng quan sát |
| --- | --- |
| Làm sai tham số tool | Functional/contract test phát hiện lỗi |
| Đưa tài liệu cũ vào bộ truy xuất | Factual correctness hoặc nhãn freshness phát hiện; groundedness *có thể* vẫn đạt |
| Thêm độ trễ giả lập vào VectorStore | p95/traces phát hiện; câu trả lời có thể vẫn đúng |

**Bước 5 — Viết báo cáo từng lớp.** Với mỗi lỗi, ghi bằng chứng nào xác nhận, giả thuyết nguyên nhân và điều kiện để kết luận đã sửa xong. Sau đó khôi phục thử nghiệm, chạy lại cùng dataset và so sánh.

### Câu hỏi tự kiểm tra

1. API HTTP 200 trong 0,5 giây nhưng trả lời sai chính sách. Những lớp nào đã có bằng chứng, và lớp nào chưa?
2. Retriever tìm được tài liệu đúng, model vẫn thêm thông tin không được hỗ trợ. Cần xem phép đánh giá nào?
3. Khi một tool hoàn tiền được gọi mà chưa xác thực quyền, có thể dùng `FactCheckingEvaluator` để chứng minh hệ thống an toàn không? Vì sao?
4. Vì sao phải báo p95 và số mẫu cùng với average latency?
5. Khi groundedness giảm và input token tăng, dữ liệu nào sẽ giúp phân biệt lỗi retrieval, prompt và chậm do model?
6. Tại sao không nên gộp “qua hết test”, “quality pass rate 98%” và “p95 dưới 3 giây” thành một điểm duy nhất?

## 12. Tổng kết

**Tính đúng của phần mềm** bảo đảm ứng dụng thực hiện đúng quy tắc và hợp đồng. **Chất lượng câu trả lời** đánh giá thông tin AI cung cấp có liên quan, chính xác, có căn cứ và đủ đáp ứng yêu cầu. **Sức khỏe hệ thống** mô tả độ ổn định, độ trễ, lỗi, mức tiêu thụ token và chi phí trong vận hành.

Trong ứng dụng Spring AI, unit/integration/contract tests, evaluation dataset/rubric và metrics/traces tạo thành **ba góc nhìn bổ trợ**. Một thay đổi prompt, model hoặc pipeline chỉ có thể coi là cải tiến khi nó đáp ứng các yêu cầu bắt buộc ở cả ba lớp, với minh chứng và phạm vi đo được mô tả rõ ràng.

### Tài liệu đọc thêm

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html)
