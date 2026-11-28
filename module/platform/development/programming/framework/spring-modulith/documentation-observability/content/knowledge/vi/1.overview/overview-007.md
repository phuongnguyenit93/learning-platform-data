# Giới hạn của quan sát runtime đối với tính đúng đắn nghiệp vụ

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **hệ thống có thể quan sát được** với **hệ thống thực thi đúng các quy tắc nghiệp vụ**.
- Nêu được điều mà module graph, Spring Boot Actuator, metrics, logs, distributed tracing và context propagation có thể hoặc không thể chứng minh.
- Nhận diện các tình huống traces đều thành công nhưng dữ liệu đơn hàng, thanh toán hoặc tồn kho vẫn sai.
- Thiết kế cách kiểm chứng kết hợp: ranh giới module, kiểm thử nghiệp vụ, ràng buộc dữ liệu, tính lặp an toàn của event consumer, đối soát và quan sát runtime.

**Bối cảnh:** Học phần này sử dụng Spring Modulith để tài liệu hóa ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Module graph, Actuator, event metrics, tracing và context propagation là các công cụ rất hữu ích để kiểm chứng kiến trúc và chẩn đoán vận hành. Tuy nhiên, mỗi công cụ chỉ cung cấp một loại bằng chứng nhất định; không công cụ nào tự hiểu đầy đủ quy tắc nghiệp vụ của hệ thống.

## 1. Ba câu hỏi khác nhau thường bị gộp thành một

Giả sử một ứng dụng thương mại điện tử được tổ chức thành các application module:

- **orders:** quản lý đơn hàng và trạng thái xử lý;
- **payments:** tiếp nhận, ghi nhận kết quả thanh toán;
- **inventory:** quản lý giữ chỗ và trừ tồn kho;
- **fulfillment:** bàn giao đơn cho vận chuyển.

Nhóm phát triển có thể hỏi ba câu:

| Câu hỏi | Bằng chứng phù hợp | Ví dụ |
| --- | --- | --- |
| **Kiến trúc có đúng ranh giới đã thiết kế?** | Định nghĩa module, phân tích phụ thuộc, kiểm tra module graph | Module orders không truy cập trực tiếp lớp nội bộ của inventory. |
| **Các thành phần có thực sự hoạt động và tương tác như kỳ vọng?** | Actuator, logs, metrics, traces, thông tin tương quan giữa các ngữ cảnh | Event thanh toán được phát; consumer tồn kho được gọi; độ trễ xử lý tăng khi tải cao. |
| **Kết quả nghiệp vụ có đúng?** | Quy tắc miền nghiệp vụ (domain invariants), trạng thái dữ liệu đã commit, kiểm thử, đối soát | Mỗi lần thanh toán hợp lệ được ghi đúng một lần; đơn không được giao khi chưa đủ điều kiện. |

Một trace thể hiện các span thành công có thể trả lời câu thứ hai, nhưng **không đủ để trả lời câu thứ ba**. Tương tự, module graph không có chu trình phụ thuộc có thể hỗ trợ câu thứ nhất, nhưng không xác nhận số tiền ghi nhận là chính xác.

Phân biệt ba loại bằng chứng giúp tránh hai kết luận sai:

1. **Không phát hiện lỗi** không đồng nghĩa với **không tồn tại lỗi**.
2. **Một luồng chạy thành công** không đồng nghĩa với **mọi ràng buộc nghiệp vụ đều được bảo toàn**.

## 2. Quan sát runtime thực sự cho biết điều gì?

Trong Spring Boot và Spring Modulith, việc quan sát runtime có thể ghép từ nhiều nguồn. Ý nghĩa của từng nguồn khác nhau:

| Nguồn quan sát | Điều có thể kết luận khi dữ liệu đáng tin cậy | Điều không thể tự kết luận |
| --- | --- | --- |
| **Module graph / tài liệu module** | Cấu trúc module, các quan hệ phụ thuộc được phát hiện theo mã nguồn và cấu hình ở phiên bản đang phân tích. | Trình tự thực tế của tất cả yêu cầu; quy tắc tính tiền, đặt hàng hoặc bồi hoàn có đúng hay không. |
| **Spring Boot Actuator** | Tình trạng và thông tin vận hành mà các endpoint được cấu hình để công bố; thông tin application module nếu bật tích hợp tương ứng. | Mọi giao dịch nghiệp vụ đều đúng chỉ vì ứng dụng báo healthy. |
| **Logs** | Những sự kiện mà chương trình đã chủ động ghi lại, kèm thời điểm và ngữ cảnh có sẵn. | Một dòng log “success” luôn tương ứng với thay đổi dữ liệu đã commit, hoặc không có sự kiện nào bị bỏ sót. |
| **Metrics** | Số lượng, tần suất, thời gian xử lý và xu hướng theo các phép đo đã định nghĩa. | Đếm chính xác các thực thể nghiệp vụ duy nhất khi có retry, duplicate, rollback hoặc mất dữ liệu đo. |
| **Tracing / spans** | Các bước xử lý đã được instrument, quan hệ cha–con hoặc liên kết giữa các bước và thời lượng của chúng. | Toàn bộ luồng không được instrument, tính nhất quán dữ liệu hoặc tính đúng của một phép tính nghiệp vụ. |
| **Context propagation** | Giúp duy trì trace/correlation context qua ranh giới thread, executor hoặc messaging khi được cấu hình đúng. | Hai thao tác có cùng trace ID nhất thiết tạo ra kết quả nghiệp vụ hợp lệ, hoặc context luôn được truyền qua mọi ranh giới. |
| **Event publication tracking** | Những publication được cơ chế theo dõi ghi nhận và trạng thái hoàn tất của listener trong phạm vi bảo đảm của cấu hình. | Hiệu ứng bên ngoài đã xảy ra đúng một lần hoặc consumer xử lý trùng luôn an toàn. |

Các nguồn trên có giá trị lớn khi **chẩn đoán, điều tra và kiểm chứng giả thuyết**. Chúng không phải một “bộ kiểm định tính đúng đắn nghiệp vụ” tự động.

### 2.1. Module graph kiểm chứng kiến trúc tĩnh, không chứng minh logic

Spring Modulith nhận diện application module dựa trên cấu trúc ứng dụng và các quy tắc cấu hình module. Có thể dùng API kiểm chứng phụ thuộc trong một bài kiểm thử kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTest {

    @Test
    void modulesObeyDeclaredBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Ở ví dụ này, **ShopApplication** là lớp ứng dụng của dự án minh họa. Việc kiểm tra giúp phát hiện những sai phạm ranh giới mà Spring Modulith nhận diện, như quan hệ phụ thuộc không hợp lệ giữa các module. Tài liệu hoặc sơ đồ module giúp người đọc xem kết cấu và các điểm kết nối được khai báo.

Tuy nhiên, mã sau vẫn có thể nằm hoàn toàn trong module **payments** và không vi phạm cấu trúc:

~~~java
// Ví dụ lỗi nghiệp vụ: nhân nhầm 100 thay vì 1000.
long amountInMinorUnit = amountInMajorUnit * 100;
~~~

Một module graph hợp lệ không thể phát hiện lỗi chuyển đổi đơn vị tiền. Nó cũng không chứng minh xử lý cạnh tranh, chính sách giảm giá hoặc quyền hoàn tiền đúng theo yêu cầu miền nghiệp vụ.

### 2.2. “Healthy” là điều kiện vận hành, không phải chứng nhận nghiệp vụ

Actuator có thể công bố thông tin về health, metrics và các endpoint được kích hoạt. Tùy dependency và cấu hình, Spring Modulith còn cung cấp thông tin về application module trong bối cảnh runtime.

Ví dụ: ứng dụng trả về trạng thái health tốt vì cơ sở dữ liệu truy cập được, JVM hoạt động và kết nối phụ trợ đáp ứng. Trong khi đó, một đơn hàng có thể bị chuyển sang **SHIPPED** trước khi xác nhận đã giữ hàng. Đây là vi phạm chính sách xử lý đơn, dù mọi health indicator đang xanh.

Vì vậy, health indicator chỉ nên phát biểu đúng điều mà phép kiểm tra thật sự đánh giá, chẳng hạn “có thể kết nối database”, không nên được diễn giải thành “mọi đơn hàng đều hợp lệ”.

## 3. Ví dụ xuyên suốt: thanh toán thành công nhưng đơn hàng vẫn sai

Giả sử hệ thống có các quy tắc nghiệp vụ:

1. **R1 — Không ghi nhận trùng:** Một sự kiện thanh toán từ nhà cung cấp được xử lý thành một bản ghi nghiệp vụ duy nhất, kể cả khi webhook được gửi lại.
2. **R2 — Điều kiện giao hàng:** Với đơn trả trước, chỉ được chuyển sang **READY_TO_SHIP** sau khi thanh toán được xác nhận và tồn kho cần thiết đã được giữ thành công.
3. **R3 — Không trừ kho hai lần:** Retry của cùng một lệnh giữ kho không được trừ lượng khả dụng lần thứ hai.
4. **R4 — Xử lý thất bại có kiểm soát:** Khi thanh toán thành công nhưng giữ kho thất bại, hệ thống phải chuyển sang trạng thái cần giải quyết và thực hiện chính sách hoàn tiền hoặc bù trừ đã định nghĩa.

Một luồng thông điệp có thể trông như sau:

~~~mermaid
flowchart LR
    O["orders: tạo đơn"] -->|"OrderPlaced"| P["payments: xử lý thanh toán"]
    P -->|"PaymentCaptured"| O
    O -->|"ReserveStock"| I["inventory: giữ hàng"]
    I -->|"StockReserved / StockRejected"| O
    O -->|"Chỉ khi đạt điều kiện R2"| F["fulfillment: chuẩn bị giao"]
~~~

Đây là luồng minh họa; chi tiết ai phát event hoặc gọi API có thể khác theo thiết kế. Các mũi tên chỉ biểu diễn tương tác, không mặc định cho biết có transaction chung giữa những module hay hệ thống ngoài.

### 3.1. Một chuỗi sự kiện tưởng như “xanh”

| Thời điểm | Điều quan sát thấy | Điều có thể đang xảy ra |
| --- | --- | --- |
| T0 | Trace của API tạo đơn có HTTP 200. | Đơn được tạo thành công, chưa nói gì về thanh toán hay kho. |
| T1 | Span xử lý webhook thanh toán kết thúc không lỗi. | Consumer đã nhận event; giao dịch DB có thể chưa commit hoặc logic xử lý trùng chưa đúng. |
| T2 | Metrics tăng bộ đếm “payment processed”. | Cùng một webhook được gửi hai lần và bộ đếm tăng hai lần. |
| T3 | Span gửi lệnh giữ kho có trạng thái thành công. | Lệnh gửi thành công nhưng phần xử lý giữ kho xảy ra bất đồng bộ, có thể trả kết quả thất bại sau đó. |
| T4 | Actuator vẫn báo ứng dụng healthy. | Đơn bị chuyển sang **READY_TO_SHIP** trước khi kho xác nhận giữ hàng. |

Tất cả tín hiệu kỹ thuật nêu trên **có thể hoàn toàn đúng theo định nghĩa của chúng**. Kết quả nghiệp vụ vẫn vi phạm R1 hoặc R2.

### 3.2. Hai lịch sử có thể tạo dấu vết gần giống nhau

Xét log và trace cho thấy hai lần gọi handler **PaymentCaptured**, mỗi lần xử lý mất 15 ms.

- **Lịch sử A:** Handler nhận event lặp, nhận diện **eventId** đã xử lý và bỏ qua thay đổi thứ hai. Chỉ có một receipt và một lần cập nhật đơn.
- **Lịch sử B:** Handler không có idempotency; cùng event được ghi thành hai receipt và cộng tiền hai lần.

Nếu chỉ ghi span tên “handlePayment” và trạng thái “OK”, hai lịch sử có thể trông tương tự. Để phân biệt, cần xem logic idempotency, ràng buộc duy nhất ở lưu trữ và bằng chứng dữ liệu sau commit.

## 4. Những giới hạn căn bản của metrics, traces và context

### 4.1. Dữ liệu quan sát không bao phủ mọi hành vi

Không phải mọi nhánh mã đều được instrument; không phải mọi span đều được thu thập. Một hệ thống có thể sử dụng sampling, giới hạn lưu trữ, batching hoặc lọc dữ liệu để giảm chi phí quan sát. Log có thể mất vì process dừng đột ngột hoặc pipeline thu thập lỗi.

Do đó, **không nhìn thấy một lỗi trong trace** chỉ cho biết lỗi đó không xuất hiện trong tập trace bạn đang có. Không thể suy ra lỗi không tồn tại. Ngay cả khi thu thập đủ các request, dấu vết vẫn không tự bao phủ các lỗi trong ràng buộc dữ liệu hoặc đường đi chưa được chạy.

Khi điều tra, phải hỏi: “Tín hiệu này được tạo ở vị trí nào, có thể bị lấy mẫu hay bị mất không, và nó đại diện cho những thao tác nào?”

### 4.2. Span hoàn tất trước hoặc khác thời điểm transaction commit

Một method có thể trả về thành công trong khi transaction bao ngoài sau đó bị rollback. Một span ghi nhận “gọi repository thành công” chưa chứng minh trạng thái cuối cùng đã được commit. Với xử lý bất đồng bộ, span của bên phát event còn có thể kết thúc trước khi bên nhận xử lý xong.

Đặc biệt, cần phân biệt:

- **Accepted:** hệ thống đã nhận yêu cầu hoặc event.
- **Processed:** một handler đã chạy và báo kết quả theo tiêu chí của nó.
- **Committed:** trạng thái cần thiết đã được commit vào nơi lưu trữ có thẩm quyền.
- **Business completed:** mọi điều kiện nghiệp vụ để tuyên bố hoàn tất đã được đáp ứng.

Bốn thời điểm này không nhất thiết trùng nhau.

### 4.3. Retry, duplicate và xử lý bất đồng bộ làm sai cách đếm ngây thơ

Trong các mô hình giao tiếp qua event, một event có thể được giao lại do lỗi mạng, timeout, restart hoặc retry. Event Publication Registry của Spring Modulith giúp theo dõi publication và hỗ trợ xử lý publication chưa hoàn tất theo khả năng và cấu hình được sử dụng; điều đó **không tự biến mọi hiệu ứng nghiệp vụ và lời gọi ra hệ thống ngoài thành exactly-once**.

Ví dụ, handler gửi yêu cầu thu tiền ra cổng thanh toán, sau đó process dừng trước khi lưu dấu đã xử lý. Khi retry, lời gọi thứ hai có thể thu tiền thêm lần nữa nếu thiếu idempotency key hoặc cơ chế đối soát với cổng thanh toán. Đếm số event phát đi, số callback đến hoặc số span hoàn thành không giải quyết được vấn đề này.

Muốn bảo vệ quy tắc không ghi trùng phải thiết kế **idempotent consumer**, ràng buộc dữ liệu như **UNIQUE(provider_event_id)**, transaction phù hợp và cơ chế giải quyết cạnh tranh. Kiểm tra “đã tồn tại chưa?” trước khi chèn **không đủ** nếu hai consumer chạy đồng thời; database constraint hoặc thao tác nguyên tử mới là lớp bảo vệ cuối cùng.

### 4.4. Trace context bị đứt không đồng nghĩa nghiệp vụ bị đứt

Trace context có thể bị mất khi vượt qua **Executor**, một thread mới, hàng đợi thông điệp hoặc một thư viện chưa hỗ trợ propagation. Khi đó, một luồng nghiệp vụ có thể bị chia thành nhiều trace, dù xử lý vẫn diễn ra đúng.

Ngược lại, hai bước có cùng trace ID cũng không bảo đảm thuộc cùng một transaction dữ liệu hoặc cùng quyết định nghiệp vụ. Trace ID chủ yếu phục vụ tương quan quan sát. Việc truyền context phải được cấu hình và kiểm thử riêng cho từng ranh giới bất đồng bộ; cần hiểu khi nào dùng parent-child và khi nào dùng span links.

**Không dùng trace ID làm khóa định danh nghiệp vụ.** Một đơn hàng cần định danh ổn định như **orderId**; một webhook cần **providerEventId** hoặc idempotency key. Trace ID có thể thay đổi theo retry, luồng xử lý hoặc thời gian sống của trace.

### 4.5. Thứ tự thời gian trong trace không thay thế mô hình trạng thái

Trong xử lý đồng thời, hai span có thời điểm chồng lấn hoặc đồng hồ ở các máy có sai lệch. Một biểu đồ timeline có thể cho biết quan hệ quan sát được giữa các thao tác, nhưng chưa xác định thứ tự commit trên database hoặc quan hệ nhân quả nghiệp vụ.

Ví dụ: nhận kết quả **PaymentCaptured** trước **StockReserved** không hẳn là lỗi; hệ thống có thể cho phép thanh toán trước, giữ kho sau rồi bồi hoàn nếu thất bại. Đúng hay sai phụ thuộc **state machine và chính sách đã định nghĩa**, không phụ thuộc việc thứ tự có “đẹp” trên trace hay không.

### 4.6. Metrics là phép đo tổng hợp, không phải sổ cái nghiệp vụ

Một counter thường tăng mỗi lần đoạn code được chạy. Nếu tăng trước commit, rollback sẽ tạo “thành công ảo”. Nếu tăng sau commit bằng callback trong bộ nhớ, process có thể ngừng giữa commit và cập nhật metric. Cùng một giao dịch có thể được đo nhiều lần do retry. Việc gộp theo thời gian cũng có thể che giấu một số đơn hàng sai bên trong tổng số xử lý đúng.

Ví dụ, **100 yêu cầu xử lý thành công** không chứng minh **100 đơn hàng khác nhau đã thanh toán đúng**. Cần truy vấn dữ liệu nghiệp vụ theo khóa duy nhất và đối soát với nguồn có thẩm quyền khi độ chính xác kế toán là yêu cầu.

### 4.7. Tương tác được quan sát không bao trùm các bất biến liên module

Một trace có thể cho thấy orders gọi inventory đúng qua public API; một sơ đồ dependency có thể xác nhận ranh giới module hợp lệ. Nhưng quy tắc “chỉ giao hàng nếu đã trả tiền và giữ kho” là bất biến **xuyên qua nhiều trạng thái**. Nó đòi hỏi cơ chế điều phối, chuyển trạng thái hợp lệ và bảo vệ dữ liệu. Kiến trúc có cấu trúc đúng vẫn có thể cài đặt sai workflow.

## 5. Định nghĩa “đúng” dưới dạng điều kiện có thể kiểm chứng

Trước khi bổ sung dashboard, hãy diễn đạt chính xác quy tắc cần bảo đảm. Một mẫu thực dụng:

> **Với** một đơn trả trước ở trạng thái READY_TO_SHIP, **phải tồn tại** bằng chứng thanh toán đã được xác nhận và giữ kho đã commit cho đủ số lượng; **nếu không**, việc chuyển trạng thái phải bị từ chối.

Quy tắc này cho biết rõ đối tượng, điều kiện tiền đề, kết quả hợp lệ và hành vi khi không đạt điều kiện. Có thể chia các bất biến thành:

| Loại quy tắc | Ví dụ | Cách kiểm chứng chính |
| --- | --- | --- |
| **Bất biến trạng thái** | Không có đơn READY_TO_SHIP nếu chưa thanh toán và chưa giữ đủ kho. | State machine, transaction, truy vấn kiểm tra dữ liệu và test chuyển trạng thái. |
| **Tính duy nhất** | Một providerEventId chỉ tạo một payment receipt hợp lệ. | UNIQUE constraint, idempotency và test chạy đồng thời/retry. |
| **Tính toán** | Tổng phải thu bằng tiền hàng cộng phí trừ giảm giá theo quy định làm tròn. | Unit/property-based tests với trường hợp biên và dữ liệu chính xác. |
| **Tính liên tục theo thời gian** | Đơn thanh toán thành công nhưng không có hàng phải đi vào luồng bồi hoàn trong thời hạn quy định. | Workflow test, kiểm tra trạng thái quá hạn và đối soát định kỳ. |
| **Tính nhất quán với bên ngoài** | Số tiền ghi nhận khớp với giao dịch của cổng thanh toán. | Đối soát theo mã giao dịch và trạng thái xác nhận từ đối tác. |

Một bất biến có thể bị ảnh hưởng bởi điều kiện nghiệp vụ như COD, giao hàng một phần, thanh toán nhiều lần hoặc nhiều đợt giữ hàng. Khi triển khai, phải ghi rõ phạm vi áp dụng và ngoại lệ hợp lệ. Không nên cứng hóa một quy tắc của ví dụ thành quy tắc chung cho mọi hệ thống.

## 6. Sử dụng Spring Modulith đúng vai trò trong chiến lược kiểm chứng

### 6.1. Bước một: ghi rõ ranh giới và kiểm tra phụ thuộc

Xác định module nào **sở hữu dữ liệu** và **quyết định nghiệp vụ**. Ví dụ:

- orders sở hữu lifecycle của đơn và điều kiện chuyển trạng thái;
- payments sở hữu bằng chứng thanh toán, mã giao dịch đối tác và trạng thái xử lý thanh toán;
- inventory sở hữu số lượng khả dụng và các reservation.

Tài liệu module của Spring Modulith giúp nhóm phát triển nhìn thấy cấu trúc cùng phụ thuộc được phát hiện. Kiểm tra module graph giúp sớm bắt sai phạm kiến trúc. Bản đồ đó cần được cập nhật cùng phiên bản mã nguồn, nhưng không tự mô tả tất cả cam kết nghiệp vụ của từng module.

### 6.2. Bước hai: kiểm thử quy tắc ngay trong module và qua ranh giới module

Phần lớn bất biến phải được kiểm tra gần nơi thực thi quyết định. Với Spring Modulith, có thể dùng **@ApplicationModuleTest** để chạy kiểm thử trong phạm vi module phù hợp; có thể kiểm thử kịch bản phát và nhận event bằng công cụ hỗ trợ test của Spring Modulith.

Các tình huống quan trọng của ví dụ:

1. Webhook thanh toán bị gửi lại với cùng providerEventId.
2. Hai consumer xử lý cùng event một cách đồng thời.
3. Transaction bị rollback sau khi handler đã chạy một phần.
4. Event giữ kho đến muộn hoặc thất bại sau thanh toán.
5. Ứng dụng khởi động lại giữa hai bước, sau đó retry publication.
6. Một đơn thử chuyển sang READY_TO_SHIP khi còn thiếu điều kiện.

Kiểm thử phải kiểm tra **trạng thái đã lưu, số tác động và event phát ra**, thay vì chỉ xác nhận method được gọi hoặc không ném exception.

### 6.3. Bước ba: bảo vệ bất biến bằng lưu trữ và giao thức

Nếu một điều kiện phải luôn đúng, không nên chỉ trông chờ vào log hoặc điều kiện kiểm tra ở giao diện. Dùng đúng công cụ theo tính chất của quy tắc:

~~~sql
-- Minh họa: id do phía thanh toán gửi phải duy nhất trong bảng receipt.
CREATE UNIQUE INDEX uk_payment_receipt_provider_event
    ON payment_receipt (provider_event_id);
~~~

Ràng buộc trên giúp tránh hai bản ghi cùng khóa khi có race condition, nhưng **chưa tự bảo đảm** không có hai giao dịch thu tiền thật ở hệ thống ngoài. Phần đó còn cần idempotency key phía đối tác (nếu được hỗ trợ), xử lý hồi đáp và đối soát.

Với một workflow gồm nhiều bước ở các module hoặc hệ thống khác nhau, cần định nghĩa các trạng thái trung gian, retry, deadline và hành động bồi hoàn. Tránh giả định mọi event hoặc lệnh gọi ra ngoài đều nằm trong một transaction ACID duy nhất.

### 6.4. Bước bốn: instrument để biết lúc nào và ở đâu quy tắc bị đe dọa

Metrics, logs và traces nên trả lời những câu hỏi vận hành cụ thể:

- Có bao nhiêu đơn bị kẹt ở **PAYMENT_CONFIRMED_WAITING_FOR_STOCK** quá thời hạn?
- Tỷ lệ retry của event publication tăng ở module nào?
- Thời gian từ thanh toán xác nhận đến giữ kho thành công là bao lâu?
- Bao nhiêu lệnh bị chặn vì thiếu điều kiện chuyển sang READY_TO_SHIP?
- Có bao nhiêu sự kiện trùng được consumer bỏ qua an toàn?

Các chỉ số này là **tín hiệu điều tra**. Khi cần khẳng định một đơn đã được thanh toán hoặc hoàn tiền đúng, phải quay lại nguồn dữ liệu nghiệp vụ và đối tác liên quan.

### 6.5. Bước năm: đối soát ngoài luồng thực thi

Không phải lỗi nào cũng xuất hiện thành exception. Một tác vụ đối soát định kỳ có thể so sánh các tập dữ liệu độc lập:

- payment receipt nội bộ với giao dịch phía payment provider;
- đơn READY_TO_SHIP với reservation và trạng thái thanh toán;
- đơn quá hạn xử lý bồi hoàn với giao dịch hoàn tiền đã xác nhận;
- tổng lượng giữ, xuất và hoàn kho với sổ biến động tồn kho.

Đối soát có thể phát hiện mâu thuẫn cả khi request đã kết thúc từ lâu và mọi span cũ đều “OK”.

## 7. Đặt tên metric theo sự thật mà nó thực sự đo

Xét bộ đếm được cập nhật sau khi transaction chứa việc phát event đã commit:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class PaymentNotificationMetrics {

    private final Counter observedNotifications;

    PaymentNotificationMetrics(MeterRegistry registry) {
        observedNotifications = Counter.builder("shop.payment.notification.observed")
            .description("So thong bao payment ma listener nay quan sat")
            .tag("module", "payments")
            .register(registry);
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(PaymentRecorded event) {
        observedNotifications.increment();
    }
}
~~~

**PaymentRecorded** là event minh họa của ứng dụng, không phải một kiểu dựng sẵn của Spring Modulith. Đoạn code giả định event được công bố trong transaction tương ứng và được Spring phân phối cho listener. Khi đó, counter mô tả **số thông báo mà listener quan sát**, chứ không mô tả “tổng số lần thanh toán duy nhất và thành công”.

Đặt tên như vậy tránh khẳng định vượt quá khả năng đo. Ngay cả hook **AFTER_COMMIT**, tiến trình vẫn có thể dừng trước khi listener ghi metric; metric thường còn được thu thập, tổng hợp qua một pipeline khác. Nếu cần số liệu chính xác cho tài chính, hãy tính từ dữ liệu có thẩm quyền và đối soát.

Một số nguyên tắc instrument hữu ích:

- **Metric name phản ánh đối tượng đo:** received, attempted, committed, rejected, duplicated, timed_out là các trạng thái khác nhau.
- **Phân biệt kết quả kỹ thuật và kết quả nghiệp vụ:** HTTP 200 hay handler không lỗi khác với đơn đã đủ điều kiện giao.
- **Nhãn metric có cardinality hữu hạn:** dùng tên module, loại kết quả, mã lỗi đã chuẩn hóa; tránh đưa orderId, traceId, email hay mã giao dịch duy nhất vào nhãn metrics.
- **Giữ mã định danh phục vụ điều tra ở nơi phù hợp:** correlation fields trong log/trace có chính sách truy cập và bảo vệ dữ liệu; tránh làm lộ dữ liệu nhạy cảm.
- **Không dùng metric để ra quyết định nghiệp vụ bắt buộc chính xác:** quyết định phải dựa trên trạng thái và hợp đồng dữ liệu của miền nghiệp vụ.

## 8. Tracing và context propagation: có tương quan, chưa chắc có đúng đắn

Trong quá trình xử lý event bất đồng bộ, một trace có thể đi từ API vào orders, phát event và sau đó có consumer ở payments hoặc inventory. Nếu context được truyền thích hợp, người vận hành có thể lần theo các bước cùng một yêu cầu hoặc liên kết các bước thuộc cùng một workflow.

Tuy nhiên, phải phân biệt ít nhất ba loại ID:

| ID | Mục đích | Cách sử dụng |
| --- | --- | --- |
| **traceId** | Tương quan các hoạt động quan sát trong một lần xử lý hoặc một luồng trace. | Tìm kiếm/chẩn đoán traces; không làm khóa dữ liệu nghiệp vụ. |
| **orderId** | Định danh đơn hàng qua nhiều lần retry và qua thời gian. | Liên kết các trạng thái nghiệp vụ của đơn. |
| **providerEventId / idempotencyKey** | Nhận diện một thông điệp hoặc thao tác mà việc lặp lại cần an toàn. | Dedupe, bảo vệ tác động lặp, đối soát với hệ thống ngoài. |

Ví dụ một webhook được retry ngày hôm sau có thể mang **providerEventId** như cũ nhưng đi qua trace mới. Chỉ dựa vào traceId sẽ không thể phát hiện tính trùng lặp nghiệp vụ.

Khi cấu hình Micrometer Observation/Tracing và context propagation, cần thử nghiệm cả đường chạy bình thường lẫn ranh giới chuyển ngữ cảnh: executor, scheduler, asynchronous listener, message broker hoặc lời gọi HTTP ra hệ thống khác. Không giả định rằng framework sẽ tự truyền đầy đủ mọi metadata trong mọi môi trường. Context truyền được làm tăng khả năng phân tích, còn tính đúng đắn phải do xử lý nghiệp vụ bảo đảm.

## 9. Tình huống điều tra thực tế: dashboard “xanh”, đơn bị giao sai

**Triệu chứng:** Support báo một đơn trả trước đã chuyển READY_TO_SHIP dù không giữ được hàng. Dashboard cho thấy HTTP success cao, độ trễ thấp và không có exception lớn.

Một quy trình điều tra theo thứ tự hợp lý:

1. **Xác minh sự thật nghiệp vụ:** truy vấn order, payment receipt, stock reservation và lịch sử chuyển trạng thái bằng orderId; đối chiếu với bất biến R2. Không kết luận chỉ từ dashboard.
2. **Dựng lại chuỗi sự kiện:** kiểm tra eventId, business ID, thời điểm commit, retry và các trạng thái trung gian; phân biệt tín hiệu “đã gửi” với “đã xử lý và commit”.
3. **Dùng trace để khoanh vùng:** tìm các bước orders, payments và inventory; nếu trace bị tách ở ranh giới async, dùng các khóa nghiệp vụ và event ID để liên kết bằng chứng.
4. **Kiểm tra cơ chế ra quyết định:** tìm chỗ nào chuyển READY_TO_SHIP, điều kiện guard có sử dụng trạng thái đã commit không, consumer có idempotent không và event đến muộn được xử lý thế nào.
5. **Sửa bất biến và kiểm thử hồi quy:** chặn chuyển trạng thái sai tại nơi sở hữu workflow; bổ sung test cho event tới trễ, gửi trùng và rollback.
6. **Bổ sung cảnh báo có mục tiêu:** phát hiện đơn vi phạm điều kiện READY_TO_SHIP hoặc đợi giữ kho quá SLA. Sau khi sửa, đối soát những đơn đã bị ảnh hưởng trước đó.

Trong tình huống này, trace giúp xác định đường xử lý gây lỗi; database và quy tắc workflow mới là bằng chứng để khẳng định đơn đã sai.

## 10. Ma trận kiểm chứng nhiều lớp

| Lớp | Mục tiêu | Công cụ/biện pháp gợi ý | Loại khẳng định được phép đưa ra |
| --- | --- | --- | --- |
| 1. Cấu trúc | Phụ thuộc giữa các application module phù hợp thiết kế. | Spring Modulith **ApplicationModules.verify()**, module graph, tài liệu module. | Không phát hiện vi phạm kiến trúc thuộc phạm vi luật kiểm tra. |
| 2. Quy tắc miền | Tính toán, state transition, idempotency đúng với các trường hợp đã kiểm thử. | Unit tests, property-based tests, module tests, scenario tests. | Những case được kiểm thử đáp ứng bất biến kỳ vọng. |
| 3. Lưu trữ/giao thức | Chặn dữ liệu trùng và cập nhật bất hợp lệ trước race/retry. | Constraint DB, transaction, optimistic locking, idempotency key, protocol hợp lệ. | Một tập bất biến được bảo vệ trong phạm vi transaction và các giả định được xác định. |
| 4. Runtime | Nhận diện lỗi vận hành và bất thường trong trao đổi giữa module. | Actuator, metrics, structured logs, tracing, context propagation, publication tracking. | Hành vi đã quan sát và tình trạng tại thời điểm đo. |
| 5. Đối soát | Tìm sai lệch kéo dài hoặc hiệu ứng bên ngoài không phản ánh đúng dữ liệu nội bộ. | Reconciliation jobs, audit trail, kiểm tra đơn quá hạn và trạng thái mâu thuẫn. | Có/không có sai lệch trên tập dữ liệu và thời điểm đã đối chiếu. |

Các lớp bổ sung cho nhau. Chẳng hạn, module tests có thể bỏ sót một race hiếm; constraint dữ liệu chặn nó tại runtime; metrics báo có xung đột; và đối soát xác nhận không còn hệ quả nghiệp vụ bất hợp lệ. Không một lớp riêng lẻ nào đủ để tuyên bố toàn bộ ứng dụng “đúng” trong mọi trường hợp.

## 11. Những câu phát biểu nên và không nên sử dụng

| Phát biểu vội vàng | Phát biểu chính xác hơn |
| --- | --- |
| “Module graph hợp lệ nên luồng thanh toán đúng.” | “Không thấy vi phạm phụ thuộc module theo bộ luật hiện tại; cần kiểm thử và đối soát quy tắc thanh toán riêng.” |
| “Tất cả span đều OK nên đơn hàng thành công.” | “Các thao tác được instrument trong tập trace quan sát đã kết thúc theo tiêu chí của chúng; cần kiểm tra kết quả workflow đã commit.” |
| “Payment counter = 1.000 nghĩa là có 1.000 đơn đã trả tiền.” | “Listener đã ghi nhận 1.000 lần đo theo định nghĩa của counter; cần loại trùng và đối soát để tính số đơn thanh toán thực tế.” |
| “Actuator healthy nghĩa là hệ thống không có sai lệch dữ liệu.” | “Những health checks được cấu hình đang đạt; vẫn cần kiểm tra bất biến và đối soát.” |
| “Có traceId xuyên suốt nên event sẽ không mất hoặc không trùng.” | “Các bước có thể được tương quan; bảo đảm giao nhận và idempotency cần giải quyết riêng.” |

## 12. Checklist tự đánh giá

Trước khi dùng quan sát runtime để tuyên bố hệ thống tuân thủ thiết kế, hãy tự trả lời:

- **Bất biến nào** đang được xác minh? Có thể diễn đạt bằng trạng thái, điều kiện và kết quả cụ thể không?
- **Nguồn dữ liệu có thẩm quyền** cho bất biến đó là gì? Có cần đối chiếu nguồn bên ngoài không?
- **Metric và span được tạo khi nào?** Trước hay sau transaction commit? Có thể đếm lại vì retry không?
- **Quan sát có đủ độ bao phủ không?** Có sampling, mất log, asynchronous gap hoặc context propagation chưa được kiểm thử không?
- **Đường lỗi đã được kiểm thử chưa?** Gửi trùng, xử lý đồng thời, timeout, crash, rollback, sự kiện đến chậm và bồi hoàn?
- **Module graph xác nhận điều gì?** Có đang nhầm tính hợp lệ của phụ thuộc với tính đúng của workflow không?
- **Cảnh báo có dẫn tới hành động không?** Có truy xuất được thực thể nghiệp vụ bị ảnh hưởng và quy trình khắc phục không?

### Câu hỏi luyện tập

1. Một consumer ghi log “event processed” rồi transaction rollback. Những tín hiệu quan sát nào có thể báo thành công giả? Bạn sẽ kiểm chứng bằng chứng nào?
2. Một webhook thanh toán được giao ba lần, mỗi lần có traceId khác nhau nhưng providerEventId giống nhau. Bạn sẽ thiết kế idempotency và kiểm thử như thế nào?
3. Test **ApplicationModules.verify()** đều pass, nhưng đơn vẫn được giao trước khi giữ hàng. Vì sao đây không phải mâu thuẫn? Bạn sẽ kiểm chứng ở lớp nào?
4. Khi trace bị đứt giữa orders và inventory, làm sao phân biệt lỗi propagation với lỗi mất event hoặc lỗi xử lý nghiệp vụ?

**Ghi nhớ:** Spring Modulith giúp làm rõ ranh giới module và quan sát tương tác giữa các phần của Spring Boot. Module graph và runtime telemetry tạo **bằng chứng về kiến trúc và vận hành**; tính đúng đắn nghiệp vụ cần được định nghĩa bằng bất biến và được bảo vệ qua kiểm thử, transaction, idempotency, cơ chế bồi hoàn và đối soát. Một hệ thống được quan sát tốt giúp tìm lỗi nhanh hơn, nhưng tính quan sát được không tự biến mọi kết quả thành đúng.
