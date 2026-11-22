# Tách dịch vụ khi có bằng chứng về nhu cầu thay đổi độc lập

> **Nguyên tắc:** Đừng tách một module thành microservice chỉ vì mã nguồn đã lớn, sơ đồ có nhiều hộp, có nhiều API hoặc tổ chức muốn “dùng microservices”. Nên cân nhắc tách khi có **bằng chứng lặp lại** rằng một năng lực nghiệp vụ cần được thay đổi, phát hành, mở rộng hoặc vận hành theo vòng đời riêng; đồng thời có thể xác lập ranh giới nghiệp vụ và dữ liệu đủ rõ để chi phí phân tán được bù đắp.

Bài học này nằm trong chủ đề **ranh giới dịch vụ (service boundaries)**. Trọng tâm là quyết định **khi nào** cần tách và **dựa vào dữ kiện nào**, không chỉ là thao tác chuyển package Java sang một dự án Spring Boot mới.

## 1. Kết quả mong đợi

Sau bài học, bạn có thể:

1. Giải thích vì sao ranh giới module, bounded context, deployment unit và microservice là các khái niệm liên quan nhưng không đồng nhất.
2. Nhận diện tín hiệu thực sự của nhu cầu thay đổi độc lập, phân biệt với cảm giác “monolith quá lớn”.
3. Thu thập bằng chứng từ lịch sử commit, pull request, release, sự cố, tải hệ thống, nhân sự và yêu cầu nghiệp vụ.
4. Đánh giá một ứng viên tách bằng lợi ích dự kiến, độ kết dính nghiệp vụ, quyền sở hữu dữ liệu và chi phí phân tán.
5. Lập kế hoạch tách an toàn theo từng bước, với hợp đồng tương thích, chuyển quyền sở hữu dữ liệu và rollback rõ ràng.
6. Phân tích tình huống và biết khi nào **giữ modular monolith** là quyết định đúng.

## 2. Vì sao “có thể tách” chưa đồng nghĩa với “nên tách”?

Giả sử hệ thống thương mại điện tử có các module:

~~~text
commerce/
  catalog/
  pricing/
  promotion/
  ordering/
  inventory/
  payment/
  fulfillment/
~~~

Code được phân chia hợp lý theo nghiệp vụ. Đây có thể là **modular monolith** chạy trong một tiến trình Spring Boot và được triển khai bằng một artifact. Nếu module Catalog đổi mô tả sản phẩm, ứng dụng cần build và phát hành lại cùng artifact. Tuy nhiên, điều đó chưa phải điểm nghẽn đáng trả chi phí cho một kiến trúc phân tán.

Việc tách Catalog thành Catalog Service sẽ bổ sung nhiều việc:

- Xây dựng hợp đồng REST/gRPC/message rõ ràng thay cho gọi method nội bộ.
- Xử lý timeout, retry, idempotency, lỗi mạng và trạng thái không xác định.
- Quy hoạch quyền sở hữu dữ liệu, migration và tránh truy cập database xuyên dịch vụ.
- Thiết lập CI/CD, cấu hình, secrets, metrics, tracing, alert và quản trị phiên bản riêng.
- Xử lý tính nhất quán giữa các vùng nghiệp vụ qua event, read model hoặc quy trình điều phối.
- Điều hành và khắc phục sự cố trên nhiều đơn vị triển khai.

Nếu Catalog vốn đổi rất ít, mỗi lần đổi đều liên quan Ordering, chưa có vấn đề scale, và nhóm chỉ có vài người, việc tách có thể tăng chi phí mà không tạo ra thêm giá trị.

**Câu hỏi quyết định:** Sự độc lập nào đang thiếu, nó gây thiệt hại cụ thể nào và việc đưa ranh giới đó ra một deployment riêng có thực sự giải quyết thiệt hại không?

## 3. “Thay đổi độc lập” nghĩa là gì?

Độc lập không phải “hai service không bao giờ gọi nhau”. Trong hệ thống kinh doanh, các năng lực vẫn phải phối hợp. Tính độc lập được nhìn qua một số chiều sau:

| Chiều | Câu hỏi thực tế | Ví dụ |
| --- | --- | --- |
| **Nghiệp vụ** | Một quy tắc có thể đổi trong một phạm vi trách nhiệm rõ ràng không? | Thay cách tính điểm trung thành mà không sửa logic đặt hàng |
| **Mã nguồn** | Thay đổi ở module này có buộc sửa nhiều module khác không? | Thêm một luật Pricing không làm thay đổi entity của Ordering |
| **Kiểm thử** | Có thể kiểm chứng hợp đồng và hành vi của phần này một cách cô lập tương đối không? | Pricing có unit/component/contract tests riêng |
| **Phát hành** | Một thay đổi tương thích có thể đi production mà không phải triển khai lại phần khác không? | Phát hành Pricing tuần này, Ordering vẫn phiên bản cũ |
| **Mở rộng tài nguyên** | Có nhu cầu scale khác biệt đủ lớn để biện minh cho hạ tầng riêng không? | Search cần nhiều CPU, Ordering cần ưu tiên tính nhất quán |
| **Vận hành/sự cố** | Có thể giới hạn, quan sát và khôi phục lỗi của phần này mà không làm sập phần khác không? | Search lỗi không khiến luồng thanh toán dừng |
| **Tổ chức** | Có nhóm chịu trách nhiệm rõ và nhịp thay đổi khác biệt không? | Nhóm Logistics phát hành quy tắc chọn kho nhiều lần mỗi tuần |

Một dịch vụ hoàn toàn có thể phụ thuộc vào kết quả từ dịch vụ khác trong quy trình nghiệp vụ, nhưng khi **hợp đồng ổn định** thì việc đổi implementation hoặc phát hành bên trong vẫn có thể độc lập.

Ngược lại, dù đã tách thành nhiều process, nếu mỗi thay đổi schema đều đòi hỏi ba nhóm sửa code và triển khai theo một lịch khóa cứng, hệ thống vẫn có **coupling thay đổi** cao. Đây là dấu hiệu distributed monolith.

### 3.1. Phân biệt độc lập thay đổi và độc lập triển khai

**Independent change** là khả năng tiến hóa quy tắc và implementation mà ít làm tác động thành phần khác. **Independent deployment** là khả năng đưa phiên bản mới của một đơn vị vào môi trường chạy riêng. Hai tính chất hỗ trợ nhau nhưng không thay thế nhau.

Ví dụ, một modular monolith có thể có ranh giới rất tốt: sửa Pricing chỉ tác động mã Pricing, hợp đồng module ổn định; tuy vậy release vẫn là một JAR. Nếu nhịp phát hành chung không gây chậm trễ, lợi ích triển khai độc lập còn nhỏ. Tách riêng lúc này không nhất thiết có lợi.

Ngược lại, ba service có pipeline CI/CD riêng nhưng cùng import một shared-domain JAR với các entity hay đổi, hoặc cùng ghi một schema, thì vẫn phải đổi đồng thời. Tên “independent deployment” trên sơ đồ pipeline không bảo đảm khả năng thay đổi độc lập thực sự.

### 3.2. Độc lập là tương đối

Không có kiến trúc nào xóa hoàn toàn các thay đổi cắt ngang nhiều miền. Ví dụ, bổ sung mô hình đặt hàng quốc tế có thể đồng thời ảnh hưởng Pricing, Tax, Ordering, Payment và Fulfillment; phối hợp là cần thiết. Mục tiêu là để những thay đổi **chỉ thuộc một miền** không liên tục kéo theo sự thay đổi hoặc phát hành của các miền khác.

## 4. Bằng chứng cần đến từ thực tế, không từ số lượng hộp trên sơ đồ

Những dấu hiệu dưới đây đáng điều tra. Một dấu hiệu đơn lẻ thường là **giả thuyết**, chưa phải kết luận tách service.

### 4.1. Lịch sử thay đổi và phát hành

Xem các thay đổi gần đây với khoảng thời gian đại diện cho nhịp làm việc của sản phẩm, chẳng hạn 8–12 tuần hoặc vài chu kỳ release. Khoảng thời gian chỉ là **ví dụ**, không phải chuẩn bắt buộc.

Một vài chỉ dấu có ích:

- Bao nhiêu pull request chỉ thay đổi trong một miền?
- Bao nhiêu lần sửa module A buộc sửa module B vì một hợp đồng hoặc kiểu dữ liệu chung?
- Bao nhiêu lần thay đổi của A phải chờ release của B?
- Có các cuộc họp hoặc “release train” thường xuyên để phối hợp nhiều thành phần vốn không liên quan không?
- Có lần nào rollback thành phần A nhưng bị buộc rollback cả các tính năng độc lập của B?
- Các thay đổi trùng nhau là do **nghiệp vụ thực sự đan xen**, hay do thiết kế code/schema đang kết dính?

Đếm số commit là chưa đủ: một PR lớn có thể thay nhiều file vì format, refactor cơ học hoặc yêu cầu xuyên miền. Cần gắn thay đổi với **lý do nghiệp vụ và phụ thuộc cụ thể**.

### 4.2. Tắc nghẽn do nhịp release khác nhau

Ví dụ Pricing cần sửa chiến dịch giá mỗi ngày, còn Ordering được kiểm thử hồi quy và phát hành hai tuần một lần. Nếu một lỗi tính giá chỉ có thể sửa sau khi “release chung” ổn định, thời gian chờ là chi phí có thể đo.

Ngược lại, nếu cả hai thay đổi theo cùng một chiến dịch và cùng cần kiểm thử nghiệp vụ đầu cuối, việc tách service chưa chắc giảm được thời gian đưa thay đổi ra thị trường.

**Bằng chứng mạnh hơn cảm nhận:** ghi nhận thời gian từ “code ready” đến production, lý do chờ, nhóm bị chặn, số lần phát hành trì hoãn và hậu quả thực tế.

### 4.3. Sự cố và phạm vi ảnh hưởng

Ví dụ batch indexing của Search gây tăng CPU làm API checkout chậm. Nếu cô lập Search có thể giảm rủi ro và cho phép quy hoạch tài nguyên riêng, đây là tín hiệu vận hành cụ thể.

Tuy nhiên, lỗi một module làm cả ứng dụng lỗi **có thể** giải quyết bằng giới hạn pool, queue, circuit breaker, tối ưu truy vấn hoặc cải thiện cấu trúc module mà chưa cần tách tiến trình. Trước khi tách, cần xác định nguyên nhân và so sánh các phương án đơn giản hơn.

### 4.4. Nhu cầu scale khác biệt

Một dịch vụ báo cáo có thể cần xử lý hàng triệu bản ghi vào ban đêm; luồng thanh toán cần latency ổn định. Nếu chạy chung làm cả hệ thống phải scale theo công việc nặng nhất, tài nguyên bị lãng phí hoặc gây nhiễu tải. Tách tải có thể có giá trị khi có dữ liệu đo.

Cần quan sát CPU, memory, I/O, database connections, queue depth, latency, throughput và chi phí. “Module này có nhiều endpoint” hoặc “traffic có vẻ lớn” không phải bằng chứng scale đủ tốt.

### 4.5. Nhu cầu chính sách và vòng đời khác nhau

Một miền có thể cần isolation về bảo mật, vùng lưu dữ liệu, thời gian giữ log, quy trình phê duyệt hoặc SLA khác hẳn. Các yêu cầu này có thể góp phần quyết định tách, nhưng vẫn cần đánh giá ranh giới dữ liệu, hợp đồng và chi phí điều hành riêng.

### 4.6. Sự trưởng thành của ranh giới nghiệp vụ

Một ứng viên có thể đổi liên tục vì *chưa hiểu rõ domain*. Khi đó tách ra một API cứng quá sớm sẽ biến các giả định sai thành hợp đồng phân tán khó thay đổi. Đôi khi giữ các module nội bộ, thử nghiệm với chuyên gia nghiệp vụ và hoàn thiện ubiquitous language là bước tốt hơn.

**Bằng chứng quan trọng không chỉ là “cần thay đổi thường xuyên”, mà còn là “biết cái gì được phép thay đổi độc lập và cái gì cần ở lại cùng một bất biến”.**

## 5. Bộ dữ liệu tối thiểu cho quyết định tách

Thay vì bắt đầu từ cuộc tranh luận “monolith hay microservices”, hãy tạo một hồ sơ cho từng ứng viên.

| Nhóm chứng cứ | Thu thập như thế nào? | Điều cần xác nhận |
| --- | --- | --- |
| Quyền sở hữu nghiệp vụ | Trao đổi domain expert, mô tả use case, quy tắc | Có năng lực và ranh giới trách nhiệm rõ |
| Thay đổi code | PR, commit, dependency graph, kiến trúc module | Thay đổi phần lớn khu trú, coupling có thể tháo được |
| Phát hành | Release logs, pipeline, approvals, blocker notes | Có chi phí phải chờ release chung |
| Sự cố | Incident reports, tracing, error budgets | Có nhu cầu cô lập lỗi hoặc khôi phục riêng |
| Tải/tài nguyên | Metrics, profiling, chi phí hạ tầng | Có khác biệt scale hoặc yêu cầu tài nguyên đáng kể |
| Dữ liệu | ERD, migration history, read/write access | Có thể xác định quyền ghi và chuyển ownership |
| Hợp đồng | Consumer inventory, DTO/API/event schemas | Có thể duy trì compatibility khi phát hành riêng |
| Năng lực vận hành | CI/CD, alert, on-call, observability | Có đội ngũ và quy trình chịu được hệ phân tán |

Một hồ sơ tách tốt trả lời đủ ba câu:

1. **Vấn đề quan sát được là gì?** Ví dụ: bảy lần release Pricing phải chờ Ordering trong hai tháng.
2. **Tách ra sẽ loại bỏ cơ chế gây vấn đề như thế nào?** Ví dụ: Pricing sở hữu bảng giá và contract báo giá, cho phép rollout phiên bản riêng mà Ordering không rebuild.
3. **Đâu là chi phí và rủi ro mới?** Ví dụ: độ trễ gọi giá, tính nhất quán đơn giá, timeout, sở hữu dữ liệu, giám sát và vận hành riêng.

Nếu chưa giải thích được câu 2, tách thêm deployment có thể chỉ chuyển coupling từ compile-time sang runtime.

## 6. Ví dụ: có nên tách Pricing khỏi Ordering?

Giả sử một hệ thống Spring Boot phục vụ thương mại điện tử có hai module trong cùng một ứng dụng:

~~~text
Commerce application
  |-- Ordering module
  |     |-- CreateOrder
  |     |-- ConfirmOrder
  |     +-- Order history
  |
  |-- Pricing module
  |     |-- Price lists
  |     |-- Customer segment rules
  |     +-- Campaign pricing
  |
  +-- Shared application deployment
~~~

### 6.1. Dữ kiện quan sát

**Tình huống giả định minh họa**, không phải số liệu của một hệ thống thực tế:

- Trong 10 tuần, nhóm Pricing có 32 thay đổi về chính sách, trong đó 25 thay đổi không yêu cầu sửa quy tắc đặt hàng.
- Có 9 lần release thay đổi Pricing bị lùi vì bộ kiểm thử hồi quy Ordering chưa hoàn thành.
- Đã xảy ra hai lần sửa lỗi giá gấp nhưng phải chờ cửa sổ triển khai chung.
- Phần code Pricing có domain model rõ: PriceList, PriceRule, PriceQuote, PriceValidity.
- Các dòng Order cần snapshot giá đã xác nhận, không nên phụ thuộc liên tục vào giá hiện tại.
- Nhóm vận hành có tracing, alert, pipeline và khả năng trực on-call phù hợp.

Các dữ kiện này gợi ý một **nhu cầu thay đổi độc lập có thể có giá trị**. Nhưng trước khi tách, phải xem Ordering có tự JOIN bảng Pricing, dùng chung transaction để ghi PriceQuote hay không, và hợp đồng lấy giá có phù hợp latency/availability không.

### 6.2. Xác định ranh giới nghiệp vụ

**Pricing Context** sở hữu chính sách tính giá và trả về báo giá theo các đầu vào nghiệp vụ có ý nghĩa: mã sản phẩm, thị trường, phân khúc, thời điểm hiệu lực và currency.

**Ordering Context** sở hữu Order, vòng đời đặt hàng và snapshot giá đã được chấp thuận. Order không trực tiếp sửa PriceRule của Pricing. Khi checkout, Ordering cần một báo giá hợp lệ và quyết định liệu có chấp nhận đề nghị mua hay không theo chính sách đặt hàng.

Ví dụ contract giao tiếp có thể là:

~~~text
Request:
  customerSegment: "LOYAL"
  market: "VN"
  currency: "VND"
  items:
    - sku: "SKU-123"
      quantity: 2

Response:
  quoteId: "Q-2026-1001"
  effectiveUntil: "2026-11-11T15:30:00+07:00"
  currency: "VND"
  lines:
    - sku: "SKU-123"
      quantity: 2
      unitPrice: 195000
      lineTotal: 390000
  total: 390000
~~~

Thông tin chỉ có tính minh họa. Hợp đồng thật cần nêu rõ quy tắc làm tròn, thuế, khuyến mại, bảo đảm hiệu lực báo giá và cách xử lý quote hết hạn. Các con số tiền tệ chỉ là ví dụ học tập.

### 6.3. Lợi ích kỳ vọng và điều kiện thành công

Nếu Pricing có thể thay implementation hoặc chính sách định giá và phát hành riêng, trong khi Ordering vẫn dùng contract tương thích, thời gian chờ release chung giảm. Ordering lưu snapshot được chấp thuận nên lịch sử đơn không bị đổi khi bảng giá hiện tại thay đổi.

Nhưng khi Pricing bị timeout, Ordering phải có phương án nghiệp vụ: báo không thể chốt giá, tạm giữ checkout, cho phép báo giá đã xác thực còn hiệu lực hoặc chính sách khác. Không được tự dùng “giá 0” hoặc giá cũ chưa được cho phép chỉ để hoàn tất request.

**Kết quả nên kiểm chứng:** số lần Pricing phải đợi Ordering, thời gian từ merge đến production, số incident xuyên miền, latency checkout, tỷ lệ lỗi lấy giá và chi phí vận hành sau tách.

## 7. Phản ví dụ: khi chưa nên tách

### 7.1. Một module dài 100.000 dòng

Độ lớn code là dấu hiệu cần xem xét chất lượng kiến trúc, nhưng chưa đủ chứng minh cần một deployment riêng. Có thể tách package, áp dụng module boundary, giảm phụ thuộc vòng, cải tiến kiểm thử và tách class quá nhiều trách nhiệm trước.

### 7.2. “Mỗi bounded context = một microservice”

Bounded context là **giới hạn của mô hình và ngôn ngữ nghiệp vụ**; microservice là quyết định về một đơn vị thực thi/triển khai và vận hành. Một bounded context có thể là module trong monolith. Một microservice có thể chứa một phần mô hình hoặc cần ranh giới được điều chỉnh cho phù hợp quy mô thực tế. Ánh xạ một-một chỉ là lựa chọn thường hữu ích, không phải luật bắt buộc.

### 7.3. Các miền luôn thay đổi cùng nhau vì cùng một bất biến

Nếu InventoryReservation và StockLedger luôn cần commit nhất quán để không bán quá tồn, tách thành hai service chỉ vì chúng là hai bảng sẽ buộc quản lý bất biến qua mạng. Hãy xác định aggregate và transaction boundary; những thành phần cần nhất quán nguyên tử thường nên ở cùng ranh giới sở hữu.

### 7.4. Nhóm chưa có năng lực điều hành nhiều dịch vụ

Nếu chưa quản lý được logs, tracing, alerts, secrets, pipeline, rollback và contract versioning, việc tách có thể biến lỗi nội bộ dễ xử lý thành sự cố phân tán khó tái hiện. Nên nâng nền tảng vận hành hoặc tách thử một ứng viên có rủi ro thấp trước.

### 7.5. Đòi scale mà chưa đo

CPU tăng có thể do truy vấn thiếu index hoặc cấu hình connection pool, không phải do kiến trúc triển khai chung. Tách service trước khi profile có thể giữ nguyên bottleneck và thêm chi phí network.

### 7.6. Chia theo lớp kỹ thuật

~~~text
Client -> Controller Service -> Business Service
        -> Validation Service -> Repository Service -> Database
~~~

Đây thường là chuỗi các tầng kỹ thuật bị đưa qua mạng. Các service không đại diện cho năng lực nghiệp vụ độc lập, mọi thay đổi một use case vẫn đi qua tất cả tầng. Tách tiến trình không giải quyết được coupling thay đổi.

## 8. Phân biệt triệu chứng, nguyên nhân và giải pháp

Một triệu chứng có thể có nhiều giải pháp. Trước khi tách, hãy hỏi liệu có thể khắc phục vấn đề với chi phí thấp hơn mà vẫn đạt mục tiêu.

| Triệu chứng | Nguyên nhân cần xác minh | Giải pháp có thể thử trước hoặc song song |
| --- | --- | --- |
| Release chậm | Test suite chậm, pipeline tuần tự, quy trình approval quá rộng | Chạy test chọn lọc có căn cứ, tối ưu CI, feature flags |
| Thay đổi A sửa B | Shared model lớn, dependency ngược, ownership mơ hồ | Tách interface, thiết kế lại module và contract |
| Hiệu năng giảm | N+1 query, contention, blocking I/O | Profiling, caching có kiểm soát, index, resource pool |
| Lỗi lan truyền | Không có timeout, pool chung, retry không giới hạn | Bulkhead, timeout, backpressure, isolation |
| Chồng chéo nhân sự | Team boundary và domain ownership không rõ | Làm rõ trách nhiệm, kiểm tra dependency |
| Migration xung đột | Nhiều module ghi cùng bảng | Chọn một data owner, đổi đường truy cập |
| Feature cần release riêng | Artifact chung và tốc độ release khác biệt thật | Cân nhắc tách deploy sau khi ranh giới ổn định |

Đánh giá phương án dựa trên **cơ chế giải quyết vấn đề**, không theo phong trào công nghệ. Nếu tối ưu pipeline giúp giảm gần hết thời gian chờ, quyết định tách có thể không còn cấp thiết.

## 9. Một khung quyết định dùng trong kiến trúc

Có thể đặt hai trục:

- **Nhu cầu độc lập:** bằng chứng về tần suất thay đổi riêng, chậm release, khác biệt tài nguyên, cô lập lỗi hoặc quy định vận hành.
- **Khả năng tách an toàn:** mức rõ ràng của bounded context, quyền sở hữu dữ liệu, hợp đồng, bất biến và năng lực vận hành.

| | Khả năng tách còn thấp | Khả năng tách tương đối cao |
| --- | --- | --- |
| **Nhu cầu độc lập thấp** | Giữ trong monolith, làm rõ module boundary | Giữ module rõ; tách chỉ khi có giá trị mới |
| **Nhu cầu độc lập cao** | Ưu tiên tháo coupling dữ liệu và code, đo lường và làm rõ domain | Ứng viên đáng cân nhắc tách microservice có kiểm soát |

Ma trận giúp thảo luận, không phải thuật toán “đủ điểm thì tách”. Chẳng hạn một miền cần tách để đáp ứng quy định pháp lý có thể được ưu tiên dù code hiện còn kết dính, nhưng khi đó phải đầu tư giải coupling trước khi chuyển dữ liệu chạy thật.

Một bản đề xuất tách nên có các trường:

~~~text
Candidate: Pricing Context
Business owner: Nhóm chịu trách nhiệm chính sách giá
Observed pain: Thay đổi giá độc lập bị chặn bởi release Ordering
Evidence window: 10 tuần
Evidence: số PR, lần chờ release, incident, độ trễ, chi phí
Bounded context: giá, quy tắc, quote và hiệu lực
Data owner: Pricing là nguồn sự thật cho policy/quote
Consumers: Ordering, Catalog, Support
Contract: QuoteRequest/QuoteResponse, event cập nhật giá nếu cần
Consistency: Ordering lưu accepted price snapshot
Failure behavior: timeout, quote expiry, duplicate request
Operational owner: nhóm chịu trách nhiệm CI/CD và on-call
Alternatives: modular boundary + cải tiến release process
Expected benefit: giảm thời gian chờ phát hành Pricing
Expected cost: mạng, tính nhất quán, vận hành, migration
Rollback strategy: giữ đường đọc cũ có kiểm soát khi chuyển đổi
Decision: tách / chưa tách / cần thêm bằng chứng
Review date: sau một chu kỳ quan sát đã thống nhất
~~~

Không cần áp dụng một mốc số chung kiểu “trên 5 release/tuần thì phải tách”. Quyết định phụ thuộc chi phí chờ, rủi ro và quy mô đội ngũ của từng hệ thống.

## 10. Rủi ro quan trọng khi chuyển một module thành service

### 10.1. Ranh giới dữ liệu

Nếu module Ordering và Pricing đang cùng ghi bảng price_rules, việc chuyển package Pricing sang ứng dụng khác chưa tạo quyền sở hữu. Bước cần làm là quy định **ai được quyền ghi** và đường truy cập nào là hợp đồng chính thức.

Một service có thể dùng database server chung ở cấp hạ tầng trong giai đoạn chuyển đổi, nhưng không nên dùng chung quyền ghi và phụ thuộc trực tiếp vào schema nội bộ của nhau. Database-per-service nhấn mạnh ownership và khả năng tiến hóa, không nhất thiết yêu cầu mỗi service có máy chủ vật lý riêng.

### 10.2. Nhất quán dữ liệu và transaction

Trong monolith, một use case có thể dùng transaction ACID qua các repository. Sau tách, thao tác qua hai database thường không thể giả định commit atomically.

Ví dụ Ordering tạo Order rồi yêu cầu Inventory giữ hàng:

1. Order chuyển trạng thái PENDING.
2. Ordering phát lệnh ReserveStock có idempotency key.
3. Inventory quyết định giữ được hàng hay từ chối và lưu kết quả bền vững.
4. Ordering nhận kết quả, chuyển CONFIRMED hoặc REJECTED theo nghiệp vụ.
5. Với timeout hoặc kết quả chưa xác định, sử dụng tra cứu trạng thái, retry an toàn và reconciliation.

Có thể dùng transactional outbox cho thông điệp xuất phát từ transaction nội bộ và Saga khi quy trình cần bước bù. Không được tự giả định HTTP call tuần tự tạo transaction phân tán tự động.

### 10.3. Hợp đồng và khả năng tương thích

Nếu Pricing Service đổi trường amount thành unitPrice nhưng Ordering vẫn dùng bản contract cũ, việc triển khai riêng có thể làm checkout lỗi. Cần chiến lược tiến hóa hợp đồng:

- Thay đổi không phá vỡ consumer hiện hữu khi có thể.
- Thêm trường mới có giá trị mặc định rõ và không đổi ngữ nghĩa trường cũ.
- Contract tests kiểm tra yêu cầu của consumer và khả năng đáp ứng của provider.
- Deprecate trường cũ có lộ trình; chỉ xóa sau khi xác nhận consumer đã chuyển.
- Không public thẳng JPA entity hoặc database schema như API contract.

### 10.4. Độ tin cậy của mạng

Các failure mode mới gồm timeout, mất kết nối, response bị mất dù xử lý đã thành công, request/event trùng và retry storm. Phải thiết kế timeout, retry có giới hạn, backoff, idempotency, rate limit/bulkhead và cảnh báo theo nghiệp vụ. **Timeout có nghĩa là chưa biết kết quả, không đồng nghĩa thất bại.**

### 10.5. Quan sát và kiểm soát thay đổi

Một lỗi checkout có thể đi qua Ordering, Pricing, Inventory và Payment. Tracing có correlation ID, metrics theo endpoint và business outcome, logging theo service, health checks, audit trails và runbook giúp tìm nguyên nhân. Có thể tách deployment riêng nhưng nếu không theo dõi được luồng đầu cuối, tổng chi phí xử lý lỗi có thể tăng mạnh.

## 11. Quy trình tách từng bước: từ module ổn định đến deployment riêng

Quy trình dưới đây áp dụng cho ứng viên có bằng chứng đáng tin cậy và đã làm rõ ranh giới. Đây là **lộ trình minh họa**, thứ tự thực tế có thể điều chỉnh theo rủi ro dữ liệu.

### Bước 1 — Chốt mục tiêu có thể đo

Ví dụ: giảm thời gian chờ đưa quy tắc Pricing ra production; hoặc cô lập tải indexing khỏi checkout. Ghi baseline, tiêu chí thành công và các ràng buộc an toàn như latency, consistency và error rate. Không đặt mục tiêu đơn thuần “tạo thêm một service”.

### Bước 2 — Làm rõ domain boundary trong code hiện tại

Phân biệt Pricing Context và Ordering Context qua ngôn ngữ, luật, mô hình và nguồn dữ liệu. Cấm các module khác trực tiếp thao tác implementation hoặc bảng thuộc Pricing. Trong modular monolith, dùng interface làm cổng giao tiếp.

~~~text
Before:
Ordering -> PricingJpaRepository -> shared pricing tables

Boundary-first:
Ordering -> PriceQuotationPort
               |
               v
          Pricing module implementation
~~~

Nếu chưa tạo được boundary trong process, đưa nó ra mạng thường chỉ làm sự phụ thuộc khó sửa hơn.

### Bước 3 — Thiết kế contract theo nhu cầu consumer

Xác định lệnh/query/event nào cần trao đổi, dữ liệu tối thiểu, phiên bản, lỗi, timeout, tính idempotent và ngữ nghĩa. Tránh expose nguyên object nội bộ của Pricing.

Ví dụ interface tại Ordering có thể là:

~~~java
package example.ordering.application;

import java.time.Instant;
import java.util.List;

public interface PriceQuotationPort {
    PriceQuotation quote(QuoteRequest request);
}

public record QuoteRequest(
        String customerSegment,
        String currency,
        List<QuoteLineRequest> lines) {}

public record QuoteLineRequest(String sku, int quantity) {}

public record PriceQuotation(
        String quoteId,
        String currency,
        long totalMinorUnits,
        Instant expiresAt) {}
~~~

Ý nghĩa totalMinorUnits là đơn vị tiền nhỏ nhất theo currency; chính sách currency và rounding phải được quy định trong contract thực tế. Mã chỉ minh họa interface giữa các context, không phải toàn bộ chương trình production.

### Bước 4 — Cho phép thay implementation qua adapter

Khi còn monolith, Pricing module có thể implement PriceQuotationPort trực tiếp. Khi tách service, Ordering giữ port và thay adapter gọi HTTP/gRPC.

~~~text
Phase A:
OrderApplicationService -> PriceQuotationPort
                              |
                              v
                      In-process Pricing adapter

Phase B:
OrderApplicationService -> PriceQuotationPort
                              |
                              v
                         HTTP client adapter
                              |
                              v
                         Pricing Service
~~~

Cách này giúp Order domain tránh phụ thuộc trực tiếp vào DTO, exception hoặc REST client của nhà cung cấp. Hợp đồng ngoài mạng phải có semantic rõ; chỉ bọc một repository call thành HTTP không tạo boundary nghiệp vụ.

### Bước 5 — Tách quyền sở hữu dữ liệu trước khi ngừng đường cũ

Lập bản đồ tất cả reader/writer và truy vấn JOIN xuyên module. Xác định ai được quyền ghi giá và quote, ai chỉ giữ snapshot. Lập migration có kế hoạch sao chép/backfill dữ liệu, đồng bộ tạm thời, kiểm chứng toàn vẹn, cutover và ngừng đường ghi cũ.

Tránh mô hình hai nơi **cùng được quyền ghi** không có cơ chế hòa giải cụ thể. Nếu dùng dual-write hoặc CDC trong giai đoạn chuyển tiếp, phải nêu rõ nguồn sự thật, khả năng trùng/lệch và cách đối soát. Việc chuyển dữ liệu thường là phần rủi ro lớn nhất của extraction.

### Bước 6 — Xây đường vận hành độc lập

Tạo pipeline build/deploy, cấu hình/secret phù hợp, metrics, tracing, alert, health checks và rollback cho Pricing Service. Xác nhận ownership, on-call và runbook. Kiểm thử contract với consumer đang chạy phiên bản cũ.

### Bước 7 — Chuyển traffic có kiểm soát

Dùng routing hoặc feature flag để chuyển một nhóm yêu cầu từ adapter in-process sang adapter service mới nếu nghiệp vụ cho phép. Theo dõi sự khác biệt kết quả báo giá, latency, lỗi và trạng thái timeout. Chọn phương án canary, shadow read hoặc chuyển dần tùy mức an toàn của tác vụ.

**Cảnh báo:** shadow read cho thao tác truy vấn có thể an toàn hơn; không nhân đôi thao tác có side effect như thu tiền, ghi đơn hoặc giữ kho chỉ để so sánh hai hệ thống.

### Bước 8 — Xóa coupling cũ và kiểm chứng mục tiêu

Sau khi xác nhận service mới là nguồn sự thật, loại bỏ quyền ghi/truy vấn trực tiếp sang bảng cũ, code cũ, adapter cũ và các đường migration tạm. Kiểm tra liệu Pricing có thật sự phát hành riêng và vấn đề ban đầu có giảm không. Nếu không, nguyên nhân có thể nằm ở quy trình hoặc hợp đồng vẫn quá kết dính.

## 12. Một ví dụ “before/after” bằng hành vi release

### Trước khi tách: coupling phát hành

~~~text
Change Pricing rule
  -> Modify Pricing module
  -> Rebuild Commerce application
  -> Run shared regression suite
  -> Wait for Ordering release approval
  -> Deploy one Commerce artifact
~~~

Nhược điểm đáng kể chỉ xuất hiện nếu chờ đợi, phạm vi kiểm thử hoặc rủi ro release chung là **vấn đề được đo và lặp lại**. Một artifact có thể vẫn thích hợp khi lịch release ngắn và pipeline ổn định.

### Sau khi tách hợp lý: thay đổi độc lập qua contract ổn định

~~~text
Change Pricing rule
  -> Modify Pricing Service internal implementation
  -> Run Pricing tests + consumer contract tests
  -> Deploy Pricing version N+1
  -> Ordering keeps running version M
  -> Monitor pricing outcome and checkout health
~~~

Điều kiện: Ordering vẫn hiểu contract hiện có; Pricing sở hữu data/logic; không có shared migration buộc Ordering nâng version. Các thay đổi thực sự ảnh hưởng cả hai bên vẫn cần phối hợp thiết kế.

### Sau khi tách sai: distributed monolith

~~~text
Change Pricing rule
  -> Modify Pricing Service schema
  -> Modify Ordering shared entity/SQL
  -> Modify Promotion shared entity/SQL
  -> Publish new common-model library
  -> Deploy all services in a coordinated window
~~~

Mọi thành phần vẫn bị khóa theo một lịch; thêm network và operational overhead nhưng chưa đạt giá trị độc lập.

## 13. Đo kết quả trước và sau thay đổi kiến trúc

Đo lường phải gắn với **mục tiêu đã nêu**, tránh chọn metric chỉ vì dễ đếm.

| Mục tiêu | Baseline cần có | Điều theo dõi sau tách |
| --- | --- | --- |
| Giảm chờ phát hành | Lead time của thay đổi miền, thời gian chờ release chung, blocker | Lead time mới, số release độc lập |
| Giảm sửa chéo | PR chạm nhiều module do coupling | Tỷ lệ thay đổi khu trú, số contract breaking changes |
| Cô lập lỗi | Incident một miền gây ảnh hưởng miền khác | Blast radius, tỷ lệ lỗi dây chuyền, MTTR |
| Scale riêng | CPU/RAM/DB load theo workload, chi phí | Scale behavior, capacity/cost, p95/p99 latency |
| Quyền tự chủ | Số bước bàn giao và nhóm phải phối hợp thường xuyên | Số thay đổi yêu cầu phê duyệt/đồng bộ nhiều nhóm |
| Ổn định hệ thống | Error rate, SLO, tần suất rollback | Failure/retry, trạng thái lệch, tỷ lệ reconciliation |

Ví dụ số liệu **giả định**:

~~~text
Before extraction (8 weeks):
  Pricing-only business changes: 18
  Releases blocked by unrelated regression/release window: 7
  Median waiting time: 4 days
  Checkout p95: 420 ms

After extraction (8 weeks):
  Pricing-only business changes: 21
  Releases blocked by unrelated regression/release window: 1
  Median waiting time: 0.5 day
  Checkout p95: 470 ms
~~~

Không thể kết luận “thành công tuyệt đối” chỉ vì thời gian chờ giảm: latency checkout đã tăng, cần xem SLO, tác động khách hàng và chi phí hạ tầng. Cũng cần cân nhắc thay đổi quy mô đội, số lượng tính năng, hệ thống test hoặc chiến dịch trong hai giai đoạn. Đây là đánh giá kỹ thuật theo giả thuyết ban đầu, không phải so sánh điểm số vô điều kiện.

Nếu kết quả không như dự kiến, hãy kiểm tra coupling còn sót, các nguyên nhân chậm release chưa được xử lý và chi phí phân tán mới. Quyết định kiến trúc có thể cần điều chỉnh hoặc hợp nhất lại.

## 14. Bộ câu hỏi đánh giá trước khi đồng ý tách

Khi đề xuất “tách module X thành microservice”, người review có thể hỏi:

1. X chịu trách nhiệm cho năng lực nghiệp vụ nào? Những quy tắc và thuật ngữ nào chỉ thuộc X?
2. Trong các thay đổi gần đây, trường hợp nào bị chậm hoặc gây lỗi vì X đang chung deployment với Y?
3. Có số liệu hoặc ví dụ release/incident cụ thể minh họa không?
4. Nếu tách hôm nay, **thành phần nào không còn phải đổi hoặc phát hành cùng X nữa**?
5. X có chủ sở hữu duy nhất của những dữ liệu nào? Có ai đang đọc/ghi bảng đó trực tiếp?
6. X có bất biến nào cần transaction cục bộ? Có giao dịch xuyên ranh giới nào phải thiết kế lại?
7. Consumer nào sử dụng X và họ có thể giữ phiên bản cũ trong lúc X deploy phiên bản mới không?
8. Timeout, retry, request trùng và trạng thái không rõ sẽ được xử lý thế nào?
9. Có thể giải quyết vấn đề bằng modular boundary, CI cải tiến hoặc resource isolation trước không?
10. Ai theo dõi vận hành, chịu trách nhiệm alert, log, tracing và khắc phục sự cố?
11. Có kế hoạch migration, cutover và rollback trong trường hợp dữ liệu/call lỗi không?
12. Metric nào xác nhận việc tách thực sự giải quyết vấn đề sau một giai đoạn vận hành?

Câu trả lời “đã có Docker/Kubernetes/API Gateway”, “đã chia repository” hay “mỗi team sẽ sở hữu một service” là thông tin triển khai hoặc tổ chức; tự nó chưa chứng minh nhu cầu thay đổi độc lập.

## 15. Các tình huống thực hành

### Tình huống A: Nên cân nhắc tách

Module Search có 3–4 lần thay đổi thuật toán ranking mỗi tuần; batch indexing thường làm chậm checkout dù Search không tham gia xử lý thanh toán. Nhóm Search muốn scale CPU riêng, có mô hình dữ liệu projection độc lập và có hợp đồng query ổn định.

**Phân tích:** Có bằng chứng về nhịp thay đổi, tải và nhu cầu cô lập lỗi riêng. Search là ứng viên đáng xem xét tách, nhưng vẫn cần đánh giá Search lấy dữ liệu từ Catalog thế nào, xử lý stale index, timeout và fallback trải nghiệm. Có thể thử cô lập workload hoặc queue trước để đo hiệu quả.

### Tình huống B: Chưa nên tách

Một ứng dụng nhỏ có module Order và OrderLine. Mỗi thay đổi OrderLine gần như luôn đi cùng Order; cả hai chung bất biến tổng tiền và trạng thái đơn. Team định tách OrderLine Service để giảm số class trong module Order.

**Phân tích:** Không có bằng chứng về nhu cầu độc lập; tách có thể phân tán một aggregate và tạo transaction phức tạp. Nên chỉnh thiết kế trong module, giữ các bất biến gần nhau.

### Tình huống C: Có vấn đề nhưng chưa sẵn sàng tách

Pricing phát hành thường xuyên, nhưng Ordering đang SELECT trực tiếp bảng price_rules để tự tính tổng, Promotion cũng UPDATE bảng đó và toàn bộ ba module import common-domain.jar.

**Phân tích:** Đau đớn phát hành có thật, nhưng ranh giới quyền sở hữu và hợp đồng chưa sẵn sàng. Bước trước là chọn chủ dữ liệu, định nghĩa Quote contract, chuyển consumer ra khỏi shared tables và shared entity. Sau khi tháo coupling, đánh giá lại lợi ích của deployment riêng.

### Tình huống D: Cùng deployment nhưng vẫn thay đổi độc lập đủ tốt

Catalog và Review nằm trong modular monolith. Chúng không import implementation của nhau, integration tests nhanh, hệ thống có pipeline liên tục và ứng dụng deploy nhiều lần một ngày. Review đổi chức năng mà không chậm do Catalog, không có vấn đề scale.

**Phân tích:** Chưa có lợi ích rõ ràng khi tách. Có thể giữ kiến trúc hiện tại và bảo vệ module boundary bằng kiểm tra phụ thuộc.

### Tình huống E: Tách process chưa tạo độc lập

Inventory và Ordering được đưa thành hai Spring Boot service, chạy trên Kubernetes. Tuy nhiên hai service cùng ghi bảng reservation, cùng cập nhật shared DTO theo mỗi release, và lỗi Inventory khiến mọi request Order retry không giới hạn.

**Phân tích:** Đây là dấu hiệu distributed monolith. Cần làm rõ quyền sở hữu reservation, contract, idempotency và timeout/backpressure. Nếu chưa có, số deployment tăng nhưng khả năng thay đổi độc lập không tăng tương ứng.

### Tình huống F: Tách có thể dựa trên yêu cầu pháp lý

Một miền Payments xử lý thông tin nhạy cảm có kiểm soát truy cập, audit và quy trình phát hành chặt hơn hệ thống nội dung marketing. Yêu cầu nghiệp vụ và tuân thủ đòi tách phạm vi quyền hạn và vận hành.

**Phân tích:** Đây có thể là bằng chứng đủ mạnh về sự khác biệt vận hành/bảo mật, ngay cả khi tần suất thay đổi Payments không cao. Cần thiết kế theo quy định thực tế, dữ liệu được phép lưu và trách nhiệm của các bên; việc tách service không tự động tạo tuân thủ.

## 16. Bài tập tự đánh giá

**Bài 1.** Nhóm có 14 microservice, nhưng khi đổi tên một trường Customer thì phải build 11 service cùng lúc. Việc tách đã đạt mục tiêu thay đổi độc lập chưa?

*Gợi ý:* Chưa. Cần phân tích shared model, published contract, bounded context và semantics của Customer trong từng ngữ cảnh.

**Bài 2.** Một module tính phí vận chuyển có thay đổi hàng ngày, 80% thay đổi chỉ ảnh hưởng nội bộ, nhưng đội chỉ deploy monolith một lần mỗi tháng vì quy trình kiểm thử thủ công. Nên làm gì trước?

*Gợi ý:* Đo chính xác nơi bị chặn; cải thiện kiểm thử/pipeline và ranh giới module. Nếu release chung vẫn là điểm nghẽn sau cải tiến và boundary đủ rõ, tách thành service là ứng viên hợp lý.

**Bài 3.** Đơn vị Fulfillment cần scale batch xử lý kho ban đêm, còn Order có SLO latency thấp. Liệu có thể tách Fulfillment chỉ vì CPU peak?

*Gợi ý:* Dữ kiện là tín hiệu đáng điều tra, chưa đủ. So sánh worker pool/queue/resource isolation với tách service; kiểm tra dữ liệu, luồng Order–Fulfillment và chính sách nhất quán trước.

**Bài 4.** Sau tách Pricing, nhóm vẫn phải phát hành Ordering mỗi lần đổi chính sách giá. Ba nguyên nhân khả dĩ là gì?

*Gợi ý:* Ordering biết thuật toán giá; API contract thay đổi khi đổi rule; Ordering dùng chung entity/schema hoặc đọc trực tiếp dữ liệu Pricing. Cần tìm nguyên nhân quan sát thực tế trước khi kết luận.

**Bài 5.** Nhóm muốn tách Inventory để deploy độc lập. Nhưng một reservation thất bại giữa bước OrderPlaced và PaymentCaptured. Cần bổ sung loại thiết kế gì?

*Gợi ý:* Trạng thái nghiệp vụ trung gian, idempotent commands, timeout, reconciliation, event/outbox hoặc Saga/bù trừ; đồng thời giữ bất biến tồn kho trong Inventory.

**Bài 6.** Một modular monolith được chia thành các bounded context rõ, có contract nội bộ tốt và mọi thay đổi được triển khai trong vài phút mà không gây incident. Vì sao “chưa tách microservice” vẫn có thể là quyết định tốt?

*Gợi ý:* Lợi ích độc lập deploy có thể chưa bù chi phí phân tán; module boundary đã giải quyết nhu cầu thay đổi hiện tại.

## 17. Checklist chuẩn bị một đề xuất tách có trách nhiệm

Dùng checklist này khi thảo luận thiết kế:

- [ ] Có bài toán nghiệp vụ và ranh giới mô hình rõ.
- [ ] Có bằng chứng thay đổi, chờ release, tải hoặc sự cố cụ thể theo thời gian.
- [ ] Có baseline và kỳ vọng cải thiện được định nghĩa bằng metric.
- [ ] Đã đánh giá các phương án đơn giản hơn để giải quyết nguyên nhân.
- [ ] Có chủ sở hữu dữ liệu, quyền ghi và bất biến rõ.
- [ ] Có hợp đồng đủ ổn định và người tiêu thụ được xác định.
- [ ] Có thiết kế timeout, retry, idempotency, consistency và recovery.
- [ ] Có đường migration, cutover, theo dõi và rollback phù hợp.
- [ ] Có năng lực CI/CD, log, tracing, metrics, alert và vận hành.
- [ ] Có tiêu chí đánh giá sau tách và cơ chế xem lại quyết định.

Checklist hỗ trợ buổi quyết định kiến trúc; không phải bộ điều kiện cứng hay chứng nhận microservices.

## 18. Ghi nhớ

- **Tách khi có bằng chứng về nhu cầu độc lập:** thay đổi code, phát hành, scale hoặc vận hành phải có lý do cụ thể, lặp lại và đủ giá trị.
- **Bằng chứng mạnh là thay đổi thực tế:** lịch sử PR/release, thời gian chờ, lỗi và giới hạn tài nguyên; số package, endpoint, container không đủ.
- **Bắt đầu từ ranh giới nghiệp vụ và quyền sở hữu dữ liệu.** Nếu chưa thể xác định ai quyết định một bất biến hoặc ai được ghi dữ liệu, việc tách process thường làm vấn đề phức tạp hơn.
- **Độc lập triển khai cần hợp đồng ổn định và xử lý lỗi phân tán.** Nhiều pipeline riêng chưa chứng minh các miền có thể tiến hóa riêng.
- **Modular monolith là lựa chọn hợp lệ và thường là bước chuẩn bị tốt.** Nếu vấn đề đã được giải quyết bằng module boundary, test và release process, chưa cần trả chi phí microservices.
- **Đo lại sau khi tách.** Kiến trúc chỉ đem lại giá trị khi giải quyết được điểm nghẽn được quan sát mà không tạo chi phí và rủi ro vượt quá lợi ích.