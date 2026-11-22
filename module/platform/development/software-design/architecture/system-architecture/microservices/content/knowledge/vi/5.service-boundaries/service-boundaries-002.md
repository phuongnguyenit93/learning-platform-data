# Độ hạt dịch vụ và lý do không đo bằng số dòng mã

## 1. Độ hạt dịch vụ là gì?

Trong kiến trúc microservices, **độ hạt dịch vụ** (*service granularity*) là mức độ một dịch vụ bao phủ trách nhiệm nghiệp vụ, dữ liệu, hành vi và các thay đổi liên quan. Một dịch vụ có thể phụ trách một năng lực nghiệp vụ hẹp, một nhóm quy tắc có liên quan chặt chẽ hoặc một bounded context hoàn chỉnh. Độ hạt không tương đương với kích thước file, số class, số endpoint, số bảng hay số dòng mã (Lines of Code, viết tắt là **LOC**).

Một quyết định về độ hạt thực chất trả lời:

> **Những trách nhiệm nào cần nằm trong cùng một ranh giới để có thể thay đổi, bảo vệ bất biến dữ liệu và vận hành độc lập với mức phối hợp hợp lý?**

Nếu tách quá nhỏ, hệ thống dễ phải gọi qua mạng nhiều lần cho một công việc, đồng bộ nhiều bản hợp đồng, xử lý giao dịch phân tán và điều phối nhiều nhóm phát hành. Nếu gom quá lớn, các năng lực không liên quan sẽ bị ràng buộc khi sửa, kiểm thử, mở rộng hoặc triển khai.

Mục tiêu không phải tạo ra nhiều dịch vụ nhất hay mỗi dịch vụ có số dòng mã gần bằng nhau. Mục tiêu là tìm **ranh giới đủ mạch lạc để nhóm sở hữu có thể phát triển và vận hành năng lực nghiệp vụ một cách đáng tin cậy**.

## 2. Vì sao LOC không đo được độ hạt thích hợp?

### 2.1. LOC đo lượng văn bản nguồn, không đo trách nhiệm

Hai dịch vụ cùng 3.000 dòng mã có thể rất khác nhau:

- Dịch vụ A xử lý một luồng tính giá đơn giản nhưng phụ thuộc trực tiếp vào dữ liệu của Checkout, Promotion và Inventory.
- Dịch vụ B bao gồm 3.000 dòng mã quản lý một quy tắc nghiệp vụ độc lập, có chủ dữ liệu rõ ràng, API ổn định và có thể triển khai riêng.

Dịch vụ A có thể gây coupling cao mặc dù code ngắn. Dịch vụ B có thể có ranh giới tốt mặc dù số dòng tương đương. Một dịch vụ 20.000 dòng mã vẫn có thể là một bounded context hợp lý; một dịch vụ 200 dòng mã vẫn có thể là một “nano-service” tốn nhiều chi phí phối hợp.

### 2.2. LOC thay đổi theo ngôn ngữ và cách viết

Cùng hành vi có thể cần số dòng khác nhau trong Java, Kotlin, Go hay Python; thậm chí hai người viết Java có thể dùng annotation, thư viện, mapper hoặc abstraction khác nhau. Gộp code trên một dòng không làm hệ thống ít phụ thuộc hơn. Tách một phương thức thành nhiều dòng không làm trách nhiệm tăng lên.

Số dòng mã còn bị ảnh hưởng bởi:

- File cấu hình, DTO, mapper, entity và lớp khung của framework.
- Test, migration, tài liệu, schema và mã được sinh tự động.
- Cách tính dòng trống, comment, file có minify hoặc generated code.
- Việc tái sử dụng thư viện so với tự triển khai cùng một hành vi.
- Chính sách code style và quy ước đặt package.

Nếu dùng một ngưỡng cứng như “mỗi service không quá 2.000 LOC”, nhóm dễ chia theo kích thước cơ học mà không xét mối quan hệ nghiệp vụ.

### 2.3. LOC không cho biết chi phí phân tán

Tách một chức năng thành hai service tạo thêm những vấn đề mà số dòng mã không biểu diễn:

- Xác thực và phân quyền giữa các tiến trình.
- API contract và chiến lược tương thích khi nâng phiên bản.
- Serialization, network latency, timeout, retry, circuit breaker và bulkhead.
- Idempotency, xử lý message trùng, eventual consistency, compensation/saga khi cần.
- Distributed tracing, correlation ID, logging, metrics và alerting.
- Triển khai độc lập, cấu hình, secret, autoscaling, on-call và quy trình xử lý sự cố.
- Dòng dữ liệu xuyên ranh giới, quyền sở hữu dữ liệu và migration schema.

Một quyết định “giảm 5.000 LOC mỗi service” có thể làm tăng số bước mạng trong đường thanh toán từ một lần gọi nội bộ thành năm lần gọi từ xa. Trong trường hợp đó, mục tiêu về chất lượng hệ thống có thể trở nên khó đạt hơn.

### 2.4. LOC có thể hữu ích ở đâu?

LOC vẫn có ích trong **ngữ cảnh duy trì mã nguồn**: gợi ý module cần xem xét, theo dõi quy mô codebase, ước lượng phạm vi đọc hiểu hoặc nhận diện file quá lớn. Nhưng LOC chỉ là chỉ báo phụ, không phải tiêu chí quyết định tách service. Không nên dùng LOC để chứng minh một ranh giới có cohesion tốt hay để đặt số lượng microservice mục tiêu.

## 3. Độ hạt quá mịn và quá thô

| Khía cạnh | Quá mịn (*too fine-grained*) | Quá thô (*too coarse-grained*) |
|---|---|---|
| Phân chia nghiệp vụ | Một giao dịch phải đi qua rất nhiều service nhỏ | Nhiều năng lực khác nhau cùng một service |
| Thay đổi tính năng | Phải sửa nhiều contract và triển khai phối hợp | Thay đổi một tính năng khiến cả service phải kiểm thử/phát hành |
| Dữ liệu | Một bất biến bị tách qua nhiều chủ dữ liệu | Nhiều miền cùng sử dụng model/schema lớn |
| Giao tiếp | Nhiều lời gọi đồng bộ, queue/topic và failure mode | Ít network boundary hơn nhưng dễ coupling nội bộ |
| Mở rộng | Có thể scale riêng, nhưng chi phí nền tảng cho nhiều service cao | Có thể phải scale cả service cho một workload nhỏ |
| Sở hữu | Ownership rời rạc, gánh nặng on-call và platform tăng | Nhiều nhóm có thể tranh nhau sửa một thành phần |
| Vận hành | Alert, deploy, config, tracing và sự cố phân tán | Blast radius trong cùng tiến trình có thể lớn |
| Rủi ro | Distributed monolith: tách tiến trình nhưng vẫn buộc deploy chung | Monolith trá hình ở cấp dịch vụ: một service chứa nhiều domain không liên quan |

Cả hai cực đoan đều gây vấn đề. Không có một kích thước “chuẩn” dùng cho mọi công ty hoặc mọi bounded context.

## 4. Tiêu chí quan trọng hơn số dòng mã

### 4.1. Một lý do thay đổi chủ đạo (cohesion)

Hỏi: **Các hành vi trong service có thường thay đổi vì cùng một nhu cầu nghiệp vụ không?**

Ví dụ, quy tắc tạo phiếu giảm giá, điều kiện áp dụng và quản lý hiệu lực có thể cùng thuộc năng lực Promotion. Ngược lại, đưa tính thuế, gửi email, thanh toán và cập nhật tồn kho vào Promotion chỉ vì chúng cùng được gọi sau checkout có thể tạo một khối pha trộn trách nhiệm.

Cách quan sát:

- Xem lịch sử PR/issue: mỗi thay đổi thường chạm bao nhiêu miền?
- So sánh thay đổi đồng thời giữa các module theo ngữ cảnh, bỏ qua chiến dịch format hoặc nâng dependency hàng loạt.
- Phân tích thuật ngữ nghiệp vụ, quyết định và quy tắc nào có cùng chủ sở hữu.
- Hỏi SME hoặc Product Owner xem những quy tắc nào thật sự cùng một năng lực.

Co-change là tín hiệu có ích, nhưng không đủ để gộp dịch vụ nếu nguyên nhân chỉ là shared library hoặc release pipeline chung.

### 4.2. Ranh giới bounded context

Trong Domain-Driven Design, bounded context xác định phạm vi một mô hình và ngôn ngữ nghiệp vụ có ý nghĩa thống nhất. Ví dụ, từ “Order” có thể mang ý nghĩa khác trong Checkout, Fulfillment và Billing. Mỗi context có thể cần một cách biểu diễn trạng thái và vòng đời riêng.

Dùng bounded context làm **điểm xuất phát** cho service boundary, không suy ra rằng một bounded context bắt buộc là đúng một service. Một context lớn có thể có nhiều đơn vị triển khai khi có lý do rõ; một nhóm có thể quản lý nhiều context nhỏ trong cùng modular monolith nếu chưa cần phân tán runtime.

Để đánh giá ranh giới, xác định:

1. Năng lực nghiệp vụ mà service cung cấp.
2. Thuật ngữ và quy tắc nào service sở hữu.
3. Dữ liệu nào chỉ service này có quyền ghi.
4. Các sự kiện và API công khai tới context khác.
5. Những bất biến nào cần giữ nhất quán tại một thời điểm.

### 4.3. Quyền sở hữu dữ liệu và bất biến giao dịch

Một service nên có quyền kiểm soát việc đọc/ghi dữ liệu cốt lõi của mình qua interface hợp lệ. Nếu hai service cùng cập nhật trực tiếp một bảng hoặc cần cùng transaction database cho mọi thao tác, ranh giới có thể đang cắt ngang một bất biến nghiệp vụ.

Ví dụ:

> Khi xác nhận giữ một sản phẩm, hệ thống không được bán vượt số lượng khả dụng.

Nếu kiểm tra tồn kho và ghi nhận việc giữ hàng luôn phải atomic, tách chúng thành hai service độc lập có thể tạo race condition và đòi hỏi giao thức phức tạp. Trong trường hợp này, trước tiên nên xác định **ai chịu trách nhiệm bảo vệ bất biến**. Không có quy tắc rằng “Inventory phải là một service vì có một bảng Inventory”.

Ngược lại, một luồng đặt hàng có thể cần phối hợp các context độc lập như Checkout và Payment. Chúng có thể giao tiếp bằng command/event với idempotency, trạng thái giao dịch và compensation rõ ràng nếu nghiệp vụ chấp nhận các giai đoạn nhất quán cuối cùng. Chỉ tách khi yêu cầu nhất quán đã được hiểu và xử lý được.

### 4.4. Khả năng thay đổi và triển khai độc lập

Một ranh giới có giá trị khi nhóm có thể thay đổi hành vi bên trong mà hạn chế sửa những nơi bên ngoài.

Dấu hiệu coupling cao:

- Một PR thường phải sửa đồng thời hai repository chỉ để đổi một quy tắc.
- Thay đổi DTO nội bộ ở A buộc B, C, D sửa cùng lúc.
- Bất kỳ phiên bản nào của A cũng đòi B được deploy chính xác cùng phiên bản.
- Một thay đổi ở B buộc toàn bộ hệ thống phải dừng hoặc dùng chung migration schema.
- Nhóm không thể rollback riêng vì dữ liệu/giao diện mất tương thích.

Một service có thể có 30.000 dòng mã nhưng vẫn có API ổn định và release độc lập. Một service có 500 dòng mã nhưng mỗi lần thay đổi phải sửa thêm 5 service khác thì độ hạt của nó rất có thể chưa phù hợp.

**Độc lập triển khai không có nghĩa không phụ thuộc:** vẫn cần quản lý contract, versioning, backward compatibility và kiểm thử tích hợp. Mục tiêu là **giảm phối hợp bắt buộc**, không kỳ vọng các service tuyệt đối không liên hệ với nhau.

### 4.5. Khả năng mở rộng và đặc tính tải khác nhau

Tách service có thể hữu ích nếu một miền có đặc điểm tải hoặc yêu cầu hạ tầng khác phần còn lại:

- Search cần khả năng đọc và indexing riêng.
- Video processing cần tác vụ CPU/GPU nặng, bất đồng bộ.
- Checkout cần latency thấp và độ tin cậy cao.
- Reporting có workload theo lô, chạy lúc ít người truy cập.

Tuy nhiên, scaling độc lập phải tạo **lợi ích đo được**. Nếu một service thường xuyên phụ thuộc vào sáu lời gọi đồng bộ, scale service đó riêng chưa chắc cải thiện throughput đầu cuối.

Hãy kiểm tra latency p95/p99, throughput, bão hòa tài nguyên, failure rate và chi phí trên một đơn vị giao dịch trước khi kết luận.

### 4.6. Ownership và năng lực vận hành

Một nhóm có thể hiểu, thay đổi, triển khai, quan sát và xử lý sự cố của service không? Ranh giới cần phù hợp với trách nhiệm vận hành và khả năng nhận diện chủ sở hữu.

Tách một context thành hàng chục service rất nhỏ có thể đòi hỏi quá nhiều pipeline, secret, dashboard và on-call. Nếu hầu hết service đều do cùng một nhóm phụ trách và luôn sửa cùng nhau, việc tách tiến trình có thể chỉ làm tăng chi phí.

Không dùng quy mô team để máy móc quy đổi ra số service. Hãy xem mỗi service có ownership rõ hay không và chi phí vận hành thực tế có chấp nhận được không.

## 5. Ví dụ: 200 dòng mã vẫn có thể là service quá nhỏ

Giả sử hệ thống thương mại điện tử đã tách một chuỗi xử lý đơn hàng như sau:

```text
Client
  |
Checkout API
  |
  +--> CartValidator
  |
  +--> PromotionCalculator
  |
  +--> ShippingFeeCalculator
  |
  +--> InventoryChecker
  |
  +--> OrderWriter
```

Mỗi thành phần được triển khai thành một tiến trình/service riêng, thậm chí mỗi service chỉ khoảng 200–500 LOC. Một request checkout cần năm lần gọi đồng bộ. Trong khi đó, mỗi lần đổi cấu trúc giỏ hàng có thể phải cập nhật ba contract, chạy nhiều integration test và triển khai phối hợp.

**Vấn đề là gì?** Không phải “service 200 LOC là sai”. Vấn đề là ranh giới có thể được chia theo tên hàm, khiến một yêu cầu nghiệp vụ đơn giản trở thành thao tác phân tán, nhiều điểm lỗi và khó triển khai độc lập.

Các câu hỏi cần đặt ra:

- Có service nào thực sự sở hữu một năng lực riêng và dữ liệu riêng không?
- Những phép tính này có cần triển khai, scale hoặc vòng đời độc lập không?
- Chúng có cùng thay đổi vì quy tắc checkout không?
- Có thể giữ chúng là thành phần nội bộ của một context với lời gọi trong tiến trình không?

Một lựa chọn khả thi là đặt CartValidator và ShippingFeeCalculator làm module nội bộ của một service/context thích hợp, còn Pricing/Promotion chỉ tách khi có quyền sở hữu, contract, dữ liệu và chu kỳ thay đổi độc lập thật sự.

## 6. Ví dụ đối lập: 20.000 dòng mã có thể vẫn hợp lý

Xét một **Billing** service khoảng 20.000 LOC gồm:

- Quản lý hóa đơn, dòng hóa đơn và vòng đời phát hành.
- Chính sách điều chỉnh hóa đơn, credit note và lập lịch thu phí.
- Tính trạng thái công nợ, đối soát nội bộ và kiểm tra bất biến.
- Schema migration, test nghiệp vụ và adapter tích hợp với nhà cung cấp.

Nếu các trách nhiệm này cùng nằm trong một bounded context, cùng sở hữu dữ liệu, cùng được đội Billing vận hành và có thể phát hành độc lập với các context khác, thì số dòng mã **không tự thân** là lý do tách thêm microservice.

Tất nhiên, nếu Billing trở thành nút nghẽn về ownership, tải riêng biệt hoặc chu kỳ phát hành, có thể phân tích tiếp ranh giới nhỏ hơn. Căn cứ để tách phải là **vấn đề có bằng chứng**, không phải vượt một ngưỡng LOC.

## 7. Đánh giá độ hạt bằng một tập câu hỏi thực tế

Đừng tối ưu một chỉ số duy nhất. Với mỗi boundary dự kiến, dùng tập câu hỏi sau:

| Góc nhìn | Câu hỏi quyết định | Bằng chứng có thể thu thập |
|---|---|---|
| Nghiệp vụ | Service có một năng lực và ngôn ngữ rõ ràng? | Domain map, ví dụ nghiệp vụ, trao đổi với domain expert |
| Cohesion | Phần bên trong có cùng lý do thay đổi? | PR/issue history, code ownership, change clustering |
| Coupling | Thay đổi một service có kéo theo nhiều service khác? | PR xuyên service, contract changes, release coordination |
| Dữ liệu | Ai sở hữu schema và các bất biến? | Data flow, transaction map, schema/table ownership |
| Runtime | Có quá nhiều lời gọi đồng bộ và phụ thuộc chuỗi? | Distributed traces, request graph, error propagation |
| Hiệu năng | Mỗi phần có cần scale riêng ở workload thật? | Throughput, latency p95, CPU/memory, capacity tests |
| Triển khai | Có thể deploy/rollback riêng mà vẫn tương thích? | Pipeline, version history, contract tests |
| Vận hành | Ai chịu on-call, debug và SLO đầu cuối? | Ownership map, runbooks, MTTR, incident reviews |
| Chi phí | Lợi ích độc lập có vượt overhead phân tán? | Hóa đơn cloud, nhân lực vận hành, số alert và sự cố |

Nếu phần lớn câu trả lời chưa rõ, hãy làm rõ bounded context trong code trước khi tách hạ tầng.

### Một số dấu hiệu nên cân nhắc **gộp** service

- Hai service luôn cần triển khai cùng lúc sau những thay đổi nhỏ.
- Một request phổ biến bị chia thành nhiều bước đồng bộ chỉ để gọi các hàm rất đơn giản.
- Dữ liệu và quy tắc không thể phân quyền sở hữu nếu không làm phức tạp giao dịch.
- Cùng một nhóm sở hữu, cùng vòng đời và cùng đặc điểm tải, nhưng overhead vận hành tăng mạnh.
- Việc chia đôi chỉ dựa trên số dòng mã hoặc tên danh từ trên domain model.

### Một số dấu hiệu nên cân nhắc **tách** service

- Hai phần có trách nhiệm và vocabulary nghiệp vụ khác nhau, thường phát triển độc lập.
- Mỗi phần có chủ dữ liệu, bất biến và contract ổn định riêng.
- Một phần có tải, SLO hoặc yêu cầu bảo mật/tuân thủ khác biệt rõ.
- Thay đổi của một phần đang gây va chạm phát hành với các phần còn lại.
- Các nhóm có đủ năng lực ownership và đo được lợi ích khi phân tán.

Đây là **dấu hiệu để điều tra**, không phải checklist mà chỉ cần vài dấu tích là có thể tự động tách/gộp.

## 8. Đo độ hạt qua mức độc lập thay đổi

Nếu cần số liệu định hướng thay vì LOC, có thể dùng các thước đo thực tế sau.

### 8.1. Tỷ lệ thay đổi lan qua ranh giới

```text
Cross-boundary change rate
  = Số thay đổi nghiệp vụ phải sửa từ 2 service trở lên
    / Tổng số thay đổi nghiệp vụ trong phạm vi đo
```

Cần định nghĩa thế nào là “một thay đổi”: PR, ticket hoặc feature; phải dùng nhất quán. Tỷ lệ cao có thể cho thấy boundary chưa tốt, contract không ổn định hoặc cách tổ chức PR chưa phù hợp. Xem thêm **nguyên nhân** trước khi kết luận.

### 8.2. Tỷ lệ cần triển khai phối hợp

```text
Coordinated deployment rate
  = Số release bắt buộc đồng bộ phiên bản giữa nhiều service
    / Tổng số release thuộc phạm vi phân tích
```

Không đếm sự kiện các nhóm tình cờ cùng deploy. Chỉ đếm trường hợp **bắt buộc** triển khai phối hợp vì tương thích hoặc dữ liệu.

### 8.3. Số hop đồng bộ trên đường quan trọng

Theo dõi số lời gọi service-to-service trên một hành trình đầu cuối như tạo đơn hàng. Song song với số hop, cần đo **latency phân vị**, timeout và độ sẵn sàng phụ thuộc. Đừng đặt mục tiêu “0 hop” vì một số tương tác là ranh giới nghiệp vụ chính đáng; điều cần biết là chi phí và failure mode có chấp nhận được hay không.

### 8.4. Thời gian thay đổi và độ tin cậy

Theo dõi lead time for changes, deployment frequency, change failure rate và thời gian phục hồi theo đúng phạm vi service/nhóm. Độ hạt tốt phải hỗ trợ mục tiêu sản phẩm và vận hành, chứ không đơn thuần tối ưu ma trận lớp.

### 8.5. Overhead vận hành trên một năng lực

Ví dụ: số pipeline, secret, dashboard, cảnh báo và giờ on-call cho mỗi năng lực nghiệp vụ; tổng chi phí cloud và công cụ trên một giao dịch thành công. Tách nhiều service nhỏ có thể tăng chi phí cố định mà không tạo năng lực độc lập tương ứng.

**Không có ngưỡng chung:** tỷ lệ thay đổi xuyên ranh giới 15% có thể quá cao với context vốn phải độc lập, hoặc hợp lý với một luồng phối hợp liên miền. Phải gắn metric với mục tiêu và baseline của hệ thống.

## 9. Phương pháp tìm service boundary theo từng bước

### Bước 1: Vẽ bản đồ năng lực, đừng bắt đầu từ thư mục

Làm việc với người hiểu nghiệp vụ để nhận diện Checkout, Payment, Inventory, Fulfillment, Catalog... Định nghĩa đầu vào, đầu ra, quy tắc và thuật ngữ cho từng context. Phân biệt năng lực nghiệp vụ với một thao tác kỹ thuật như “SaveEntityService” hay “EmailFormatterService”.

### Bước 2: Ghi bất biến và chủ dữ liệu

Với mỗi context, liệt kê dữ liệu cốt lõi và thao tác cập nhật. Ai đảm bảo điều kiện “không thanh toán hai lần”, “không bán vượt tồn kho” hoặc “chỉ hóa đơn hợp lệ được phát hành”? Nhóm những quy tắc cần cùng transaction vào cùng vùng kiểm soát khi phù hợp.

### Bước 3: Phân tích lịch sử thay đổi

Xem 3–6 tháng PR/issue hoặc vài chu kỳ phát hành gần nhất (tùy dự án). Tìm các cặp module thường sửa cùng nhau, các contract thay đổi kéo theo sửa ở service khác và các feature phải phối hợp giữa nhóm. Loại/gắn nhãn thay đổi hàng loạt gây nhiễu.

Nếu hai miền thường sửa cùng nhau vì một quy tắc duy nhất, xem xét liệu ranh giới có chia cắt trách nhiệm. Nếu cùng sửa do thư viện dùng chung hoặc nâng framework, có thể xử lý bằng cách giảm coupling kỹ thuật.

### Bước 4: Đối chiếu runtime và deployment

Quan sát sơ đồ lời gọi, p95/p99 latency, số lần retry/timeout, những điểm lỗi dây chuyền và dữ liệu dùng chung. Kiểm tra các service có thể triển khai/rollback riêng với backward-compatible API hoặc event schema hay không.

### Bước 5: So sánh các phương án

Ít nhất so sánh:

1. **Giữ chung trong modular monolith:** boundary nội bộ rõ, gọi trong tiến trình, chưa thêm overhead phân tán.
2. **Một service cho bounded context:** triển khai độc lập khi context đủ trưởng thành.
3. **Tách service hẹp hơn:** chỉ khi có nhu cầu độc lập rõ về thay đổi, dữ liệu, tải, SLO hoặc ownership.
4. **Gộp lại các service quá nhỏ:** khi chúng thay đổi, deploy và xử lý giao dịch như một đơn vị.

Đối chiếu từng phương án theo cùng KPI và guardrails, không chỉ theo số service.

### Bước 6: Thử nghiệm giới hạn

Chọn một luồng nghiệp vụ ít rủi ro, làm rõ contract, thêm tracing và contract tests. Nếu tách, sử dụng một lộ trình chuyển đổi có thể rollback (ví dụ strangler pattern khi phù hợp). Giữ tương thích dữ liệu và giao diện theo từng bước. Tránh chia đôi dữ liệu đột ngột khiến rollback bất khả thi.

### Bước 7: Đánh giá và điều chỉnh

Sau một vài chu kỳ thay đổi đủ đại diện, so sánh:

- Số thay đổi cần sửa nhiều service.
- Số lần cần deploy phối hợp.
- Lead time và change failure rate.
- p95 latency và lỗi trên hành trình quan trọng.
- Chi phí vận hành, alert, incident và trách nhiệm on-call.

Ranh giới dịch vụ **có thể tiến hóa**. Một quyết định đúng ở giai đoạn đầu không nhất thiết tối ưu khi phạm vi nghiệp vụ, quy mô đội và tải thay đổi.

## 10. Tình huống minh họa: tách Payment khỏi Checkout

Một hệ thống ban đầu có module Checkout và Payment nằm trong cùng một ứng dụng. Nhóm tranh luận vì Payment chỉ có 1.200 dòng mã nên “không đủ lớn để thành microservice”.

Phân tích thay vì đếm LOC:

- **Nghiệp vụ:** Payment quản lý yêu cầu thanh toán, trạng thái giao dịch, hoàn tiền và idempotency; Checkout tạo và xác nhận đơn.
- **Dữ liệu:** Payment sở hữu payment attempt và trạng thái từ nhà cung cấp; Checkout sở hữu order và trạng thái đặt hàng.
- **Thay đổi:** chính sách tích hợp cổng thanh toán có thể đổi độc lập với logic tạo đơn.
- **Vận hành:** Payment cần giám sát, kiểm soát truy cập và lịch phát hành riêng.
- **Tương tác:** Checkout vẫn phải phối hợp trạng thái thanh toán; cần thiết kế luồng pending/succeeded/failed, callback trùng và thời gian chờ rõ ràng.

Trong tình huống giả định này, Payment **có thể** là một service riêng nếu lợi ích deploy/ownership độc lập đủ lớn và nhóm xử lý được bất đồng bộ, tính nhất quán và vận hành. Việc chỉ có 1.200 LOC không phủ định ranh giới ấy.

Ngược lại, nếu Checkout và Payment luôn cùng thay đổi vì chúng đang dùng một schema chung và không có ownership dữ liệu riêng, tách vật lý trước khi giải quyết data boundary có thể tạo distributed monolith.

### Bảng so sánh giả định

| Dữ liệu được đo | Trước thay đổi | Sau thử tách | Ý nghĩa cần xem |
|---|---:|---:|---|
| Tỷ lệ thay đổi Payment cần sửa Checkout | 65% | 20% | Dấu hiệu giảm change coupling |
| Release Payment phải deploy cùng Checkout | 70% | 10% | Khả năng deploy độc lập cải thiện |
| p95 hành trình checkout | 450 ms | 520 ms | Chi phí latency tăng, cần so với SLO |
| Tỷ lệ lỗi thanh toán | 0,15% | 0,14% | Guardrail độ tin cậy chưa xấu đi |
| Chi phí vận hành mỗi 1.000 thanh toán | 100 đơn vị | 125 đơn vị | Overhead tăng, cần so với lợi ích |

**Tất cả số liệu trong bảng là minh họa**, không phải số liệu tiêu chuẩn của microservices. Nếu mục tiêu phát hành độc lập đạt nhưng latency vượt SLO hoặc chi phí không bù được lợi ích, kết luận có thể là tối ưu thiết kế, điều chỉnh boundary hoặc quay về phương án đơn giản hơn.

## 11. Ví dụ Java: cùng chức năng, ranh giới khác nhau

Xét một thao tác “tính tổng giỏ hàng”:

```java
public final class CheckoutCalculator {
    private final PricingPolicy pricingPolicy;
    private final TaxPolicy taxPolicy;

    public Money calculate(Cart cart) {
        Money subtotal = pricingPolicy.subtotal(cart.items());
        Money tax = taxPolicy.tax(subtotal, cart.destination());
        return subtotal.plus(tax);
    }
}
```

Ở đây, `PricingPolicy` và `TaxPolicy` có thể là **các đối tượng/module trong cùng tiến trình**. Đoạn mã ngắn không buộc chúng thành ba service. Nếu biến mỗi policy thành một service chỉ vì “mỗi class thực hiện một trách nhiệm”, checkout sẽ cần thêm giao tiếp mạng và quản trị hợp đồng trong khi có thể không có giá trị độc lập nào.

Tuy nhiên, nếu định giá và thuế thuộc hai bounded context thực sự khác nhau, với ownership, chu kỳ luật định, dữ liệu và nhu cầu triển khai riêng, việc tách có thể hợp lý. Khi đó cần thiết kế API/event, dữ liệu đầu vào, tính nhất quán và trách nhiệm kết quả cuối.

**Single Responsibility Principle không đồng nghĩa với “mỗi class/mỗi method là một microservice”.** Từ cấp class đến cấp service, đơn vị “lý do thay đổi” phải được xem trong bối cảnh tổ chức và nghiệp vụ.

## 12. Các phản ví dụ thường gây nhầm lẫn

**“Microservice là dịch vụ có ít hơn N dòng mã.”** Không có con số N phổ quát. Số dòng mã không đo data ownership, business cohesion, khả năng deploy hoặc chi phí phân tán.

**“Mỗi bảng database là một service.”** Bảng có thể cùng phục vụ một bất biến hoặc cùng thuộc một aggregate. Tách bảng thành service không đồng nghĩa tách bounded context.

**“Mỗi chức năng trên màn hình là một service.”** Một màn hình có thể ghép thông tin từ nhiều context; ngược lại, nhiều màn hình có thể dùng cùng một năng lực nghiệp vụ.

**“Có nhiều repository là có microservices tốt.”** Nhiều repository vẫn có thể bị version lockstep, shared database hoặc phải triển khai đồng thời.

**“Service nào nhiều LOC cũng phải cắt đôi.”** Một context có thể lớn vì quy tắc phức tạp nhưng vẫn gắn kết tốt. Trước tiên xem cohesion nội bộ và chi phí thay đổi.

**“Service nào nhỏ LOC cũng phải gộp.”** Một adapter nhỏ sở hữu ranh giới bảo mật hoặc sự kiện độc lập có thể có lý do vận hành chính đáng để tách. Quyết định dựa trên mục tiêu và trade-off, không lấy LOC làm dấu hiệu duy nhất.

**“Tách nhỏ sẽ tự động scale tốt hơn.”** Nhiều network hop, shared database và bottleneck chung có thể làm scaling tệ hơn. Đo workload đầu cuối.

**“Gộp service sẽ tự động giảm coupling.”** Gộp runtime có thể bớt gọi qua mạng nhưng vẫn giữ thiết kế nội bộ rối nếu không làm rõ boundary, API và ownership.

## 13. Mẫu ghi nhận quyết định độ hạt dịch vụ

Dùng một Architecture Decision Record (ADR) ngắn để quyết định có thể xem lại:

```markdown
# ADR: Ranh giới và độ hạt cho <năng lực nghiệp vụ>

Bối cảnh:
- Năng lực nghiệp vụ và bounded context:
- Nhóm sở hữu:
- Vấn đề đo được:
- Chứng cứ từ PR/issue, runtime và vận hành:

Ranh giới dữ liệu và giao dịch:
- Dữ liệu do thành phần này sở hữu:
- Bất biến cần giữ:
- Tương tác với các context khác:
- Contract và yêu cầu tương thích:

Phương án:
1. Giữ chung trong modular monolith
2. Một service cho context
3. Tách một phần riêng
4. Gộp các service hiện có

Đánh đổi theo từng phương án:
- Cohesion / thay đổi độc lập:
- Dữ liệu / nhất quán:
- Runtime / độ trễ / khả năng phục hồi:
- Scaling / chi phí:
- Ownership / vận hành:

Quyết định và lý do:
Giả định cần kiểm chứng:
KPI baseline / mục tiêu:
Guardrails:
Kế hoạch thử nghiệm và rollback:
Ngày xem lại:
```

Trong ADR có thể ghi LOC để mô tả quy mô hiện có, nhưng **không dùng LOC thay cho lý do quyết định**.

## 14. Bài tập thực hành

Một sản phẩm SaaS có ba thành phần:

- **TenantProfile:** 600 LOC, thay đổi 9 lần trong ba tháng, có 8 thay đổi phải sửa cùng Billing vì chung schema.
- **Billing:** 22.000 LOC, thay đổi 20 lần, sở hữu hóa đơn, đối soát và thu phí, deploy riêng được.
- **Notification:** 4.000 LOC, thay đổi 15 lần, xử lý gửi email/SMS, chạy worker queue và cần scale riêng vào các đợt cao điểm.

Đội kỹ thuật đề xuất tách Billing thành 11 service, mỗi service 2.000 LOC; đồng thời giữ TenantProfile vì “quá nhỏ để tách”.

Hãy trả lời:

1. Vì sao phương án chia Billing thành các service bằng nhau theo LOC chưa đủ căn cứ? Nêu ít nhất ba rủi ro.
2. Với TenantProfile, 8/9 lần đổi cùng Billing gợi ý điều gì? Cần xem những bằng chứng nào trước khi chọn gộp hay tách?
3. Notification có lý do độc lập nào quan trọng hơn 4.000 LOC?
4. Đề xuất hai cách tổ chức ranh giới: một cách ưu tiên modular monolith, một cách ưu tiên tách service khi có nhu cầu vận hành rõ.
5. Chọn ba KPI và hai guardrails để kiểm chứng phương án qua vài chu kỳ phát hành.

Gợi ý: xét các câu hỏi về ownership dữ liệu, lý do thay đổi, độc lập triển khai, runtime coupling, workload và chi phí thay vì tìm con số LOC “đúng”.

## 15. Checklist trước khi chốt độ hạt

- [ ] Đã xác định năng lực nghiệp vụ và ngôn ngữ của từng bounded context.
- [ ] Có một chủ sở hữu rõ ràng cho dữ liệu và bất biến quan trọng.
- [ ] Đã xem các thay đổi thường gặp có bị rải qua nhiều service không.
- [ ] Có sơ đồ các lời gọi đồng bộ, sự kiện và giao dịch liên miền.
- [ ] Đã cân nhắc tác động đến latency, lỗi dây chuyền và tính nhất quán.
- [ ] Có cơ sở cho nhu cầu triển khai hoặc scaling độc lập.
- [ ] Phân định được trách nhiệm nhóm, on-call, contract và SLO.
- [ ] Đã so sánh chi phí vận hành với lợi ích dự kiến.
- [ ] Có phương án thí điểm, đo baseline, guardrails và đường rollback.
- [ ] Không dùng số dòng mã làm tiêu chí chính hoặc ngưỡng chia service.

## 16. Ghi nhớ

**Độ hạt dịch vụ là quyết định về ranh giới trách nhiệm và mức độc lập, không phải phép chia tổng LOC cho số service.** Một service nhỏ có thể quá gắn chặt với hàng xóm; một service lớn có thể vẫn có cohesion tốt. Chọn độ hạt bằng hiểu biết về bounded context, quyền sở hữu dữ liệu, bất biến, lịch sử thay đổi, runtime, khả năng triển khai và chi phí vận hành. Tối ưu cho **thay đổi nghiệp vụ an toàn và độc lập ở mức cần thiết**, rồi kiểm chứng qua số liệu thực tế.
