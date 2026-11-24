# Quyền sở hữu và rà soát thay đổi trong kho hợp đồng

## Mục tiêu học tập

Trong hệ sinh thái **Spring Cloud Contract**, hợp đồng là mô tả có thể thực thi về hành vi giao tiếp giữa **producer** (dịch vụ cung cấp API hoặc phát thông điệp) và **consumer** (dịch vụ sử dụng API hoặc nhận thông điệp). Hợp đồng có thể viết bằng **Groovy/YAML DSL**, dùng để sinh kiểm thử phía producer và tạo stub cho consumer chạy với **Stub Runner**.

Khi nhiều nhóm cùng làm việc, viết được hợp đồng mới chỉ là một phần của vấn đề. Cần xác định **ai chịu trách nhiệm về hợp đồng**, **ai có quyền đề xuất và phê duyệt thay đổi**, **làm sao biết consumer nào bị ảnh hưởng**, và **CI phải chặn những rủi ro nào**. Bài học thuộc chương **Tổ chức hợp đồng** giúp bạn:

- Phân biệt quyền sở hữu giao diện, quyền đề xuất hợp đồng, quyền phê duyệt và trách nhiệm kiểm chứng.
- So sánh hai cách lưu hợp đồng phổ biến: cùng repository với producer hoặc trong repository hợp đồng dùng chung.
- Thiết lập quy trình pull request (PR), code review, quản lý nhánh và quyền truy cập phù hợp với nhiều nhóm.
- Phân loại thay đổi tương thích và thay đổi có nguy cơ phá vỡ consumer, kể cả khi producer contract test vẫn xanh.
- Kết hợp **generated tests**, **stub artifact**, **Stub Runner**, cơ chế quản lý phiên bản và cổng kiểm tra CI để giảm lỗi tích hợp.

## 1. Vì sao kho hợp đồng cần quyền sở hữu rõ ràng?

Giả sử hệ thống đặt hàng có ba dịch vụ:

- **Inventory Service** là producer của `GET /api/inventory/{sku}` và sự kiện `StockChanged`.
- **Checkout Service** là consumer của API tồn kho.
- **Recommendation Service** cũng là consumer của API tồn kho, nhưng chỉ đọc vài trường.

Cả ba nhóm có thể chỉnh sửa code độc lập. Nhóm Inventory muốn đổi phản hồi cho đơn giản, nhóm Checkout cần kiểu dữ liệu cũ để quyết định cho đặt hàng, còn Recommendation chưa kịp nâng cấp. Nếu bất kỳ ai cũng sửa DSL rồi phát hành stub mới, các build có thể báo xanh nhưng hệ thống thực tế vẫn mất khả năng tương thích.

Một kho hợp đồng cần giải quyết đồng thời ba câu hỏi:

1. **Quyết định:** Ai có quyền cam kết rằng producer sẽ cung cấp hành vi cụ thể?
2. **Ảnh hưởng:** Ai đang dựa vào hành vi đó và phải được tham vấn trước khi thay đổi?
3. **Bằng chứng:** Kiểm tra nào xác nhận producer thực sự đáp ứng hợp đồng và consumer hiểu đúng phiên bản stub dự định sử dụng?

**Quyền sở hữu không đồng nghĩa với quyền được đơn phương thay đổi mọi thứ.** Producer chịu trách nhiệm triển khai giao diện; consumer chịu trách nhiệm mô tả và kiểm thử phần họ phụ thuộc; quá trình review liên nhóm bảo vệ thỏa thuận chung.

## 2. Phân định trách nhiệm: producer, consumer và người duy trì kho

| Vai trò | Có thể đề xuất | Cần chịu trách nhiệm chính | Không nên tự kết luận |
|---|---|---|---|
| **Nhóm producer** | Endpoint, cấu trúc thông điệp, sửa lỗi, phương án tương thích | Hiện thực hợp đồng, generated contract tests, xuất bản stub, kế hoạch ngừng hỗ trợ | Consumer sẽ không bị ảnh hưởng chỉ vì producer test xanh |
| **Nhóm consumer** | Trường dữ liệu cần dùng, trường hợp lỗi, yêu cầu thêm contract, kế hoạch nâng cấp | Test logic consumer với stub, xác nhận các phụ thuộc và thời điểm chuyển đổi | Producer có thể cam kết mọi hành vi khi chưa xem xét khả năng triển khai |
| **Người duy trì kho hợp đồng** | Quy ước đường dẫn, đặt tên, mẫu PR, quy trình review | Kiểm soát thay đổi, quyền truy cập, tính nhất quán cấu trúc và lịch sử | Thay mặt chủ sở hữu API quyết định ngữ nghĩa nghiệp vụ |
| **CI/build owner** | Quy tắc kiểm tra, publish artifact, chính sách version | Giữ pipeline sinh test, build stub và kiểm tra đủ điều kiện phát hành | Test tự động có thể phát hiện mọi thay đổi phá vỡ nghiệp vụ |
| **Chủ sở hữu sản phẩm/API** (nếu tách khỏi producer) | Chính sách tương thích, vòng đời phiên bản, quyết định migration | Giải quyết xung đột giữa nhiều consumer, thông báo ngừng hỗ trợ | Bỏ qua kết quả kiểm chứng kỹ thuật |

Có thể sử dụng ma trận **RACI** để quy trách nhiệm, với:

- **R – Responsible:** người trực tiếp làm việc.
- **A – Accountable:** người chịu trách nhiệm cuối cùng về quyết định.
- **C – Consulted:** bên cần được hỏi ý kiến.
- **I – Informed:** bên cần được thông báo.

Ví dụ chính sách cho API tồn kho:

| Hoạt động | Inventory (producer) | Checkout/Recommendation (consumer) | Maintainer kho |
|---|---|---|---|
| Đề xuất hành vi mới | A/R khi chủ động bổ sung | R khi có nhu cầu | I |
| Xác nhận ý nghĩa trường và HTTP status | A/R | C | I |
| Triển khai và chạy generated tests | A/R | I | I |
| Test client với candidate stub | C | A/R cho từng consumer | I |
| Phê duyệt breaking change và lịch chuyển đổi | A cùng chủ sở hữu API | C, cần xác nhận kế hoạch nâng cấp | C về quy trình |
| Bảo vệ nhánh, mẫu PR và quy tắc review | C | C | A/R |

Ma trận này là **ví dụ phân công**, không phải cấu hình tự động của Spring Cloud Contract. Với đội nhỏ, một người có thể đảm nhận nhiều vai trò; với giao diện công cộng hoặc nhiều consumer, cần trách nhiệm rõ hơn. Đặc biệt, quy trình nên quy định **ai xử lý khi consumer phản đối thay đổi** thay vì chỉ thêm tên reviewer vào PR.

## 3. Chọn nơi lưu: cùng producer hay kho hợp đồng riêng?

Hai cách tổ chức đều có thể dùng với Spring Cloud Contract. Khác biệt chính nằm ở quyền sở hữu, quy trình đóng góp và cách build tìm file DSL.

| Cách lưu | Phù hợp khi | Điểm mạnh | Điều cần kiểm soát |
|---|---|---|---|
| **Trong repository producer** (ví dụ `src/test/resources/contracts`) | Producer có trách nhiệm phát hành API và nhóm consumer gửi PR vào cùng kho | Code triển khai và contract thay đổi cùng một lịch sử; producer chạy generated tests thuận tiện | Consumer phải có cách đề xuất/review; không để producer bỏ qua ảnh hưởng tới consumer cũ |
| **Repository hợp đồng dùng chung** | Nhiều dịch vụ/nhóm muốn cùng quản trị hợp đồng hoặc consumer đóng góp độc lập | Tập trung lịch sử quyết định và chính sách review; dễ xem giao diện giữa nhiều đội | Pipeline phải lấy đúng revision hợp đồng; producer, stub và consumer không được dùng các revision lệch nhau |

### Mô hình A: hợp đồng sống cùng producer

~~~text
inventory-service/
├── pom.xml
├── src/main/...
├── src/test/java/...
└── src/test/resources/contracts/
    ├── http/
    │   ├── stockAvailable.groovy
    │   ├── stockNotFound.groovy
    │   └── stockInvalidSku.groovy
    └── messaging/
        └── stockChanged.groovy
~~~

Nhóm Checkout có thể gửi PR vào `inventory-service` để đề xuất thêm trường `reservedQuantity`, nhưng nhóm Inventory phải xem xét khả năng và ý nghĩa cam kết. Nhóm Checkout cũng review để xác nhận response đủ dùng và không làm hỏng logic hiện tại.

### Mô hình B: repository hợp đồng dùng chung

~~~text
service-contracts/
├── contracts/
│   ├── inventory/
│   │   ├── http/
│   │   │   ├── stockAvailable.groovy
│   │   │   └── stockNotFound.yml
│   │   └── messaging/
│   │       └── stockChanged.groovy
│   └── payment/
│       └── http/
│           └── paymentStatus.groovy
├── docs/
│   └── compatibility-policy.md
└── .github/
    └── CODEOWNERS
~~~

Các đường dẫn trên là **quy ước quản trị ví dụ**. Spring Cloud Contract không tự biết file `contracts/inventory/http/stockAvailable.groovy` thuộc producer nào chỉ vì tên thư mục là `inventory`. Build phải được **cấu hình để tìm đúng nguồn hợp đồng và layout**. Khi dùng repository ngoài, producer cần lấy đúng phiên bản/revision của contract rồi sinh test, stub từ revision ấy; không để hai pipeline âm thầm lấy nội dung mới nhất theo thời điểm chạy.

Chọn một **nguồn hợp đồng có thẩm quyền** cho mỗi giao diện. Nếu cùng một endpoint có hai bản DSL duy trì độc lập ở producer và kho chung, hai bản có thể mâu thuẫn. Muốn nhân bản phục vụ build thì cần cơ chế đồng bộ và truy vết nguồn gốc rõ ràng.

## 4. Quyền sở hữu theo thư mục và quy tắc review

Với repository có nhiều nhóm, có thể biểu diễn người phụ trách từng vùng bằng file `CODEOWNERS` nếu nền tảng quản lý Git hỗ trợ. Ví dụ GitHub đặt file tại `.github/CODEOWNERS`:

~~~text
# Ví dụ: tên tổ chức/nhóm chỉ để minh họa
/contracts/inventory/  @example-org/inventory-team
/contracts/payment/    @example-org/payment-team
/docs/                 @example-org/platform-api
~~~

Cách này giúp PR sửa hợp đồng `inventory` gọi đúng nhóm producer vào review. Tuy nhiên, **CODEOWNERS chỉ hỗ trợ chỉ định reviewer** theo khả năng của nền tảng; nó không tự nhận diện mọi consumer bị ảnh hưởng, cũng không tự bảo đảm hai nhóm producer và consumer đều đã đồng ý.

Đặc biệt với GitHub:

- Phải bật **branch protection/rulesets** phù hợp và yêu cầu review từ code owner nếu muốn đây là cổng bắt buộc; riêng sự tồn tại của `CODEOWNERS` không đủ.
- Nếu một pattern có nhiều owner, không nên mặc định rằng **tất cả** owner phải phê duyệt. Quy tắc phê duyệt liên nhóm phải được mô tả và thực thi bằng cơ chế review/rulesets bổ sung.
- Kiểm tra thứ tự và độ ưu tiên pattern theo nền tảng thực tế; đừng viết quy tắc chồng chéo rồi giả định một người nhận review là đủ.

Với kho đặt cùng producer, phần lớn PR sẽ tự đi tới nhóm producer. Nhưng với API nhiều consumer, cần thêm **danh bạ phụ thuộc**: ai sử dụng endpoint, sự kiện hoặc field nào và ai liên hệ khi thay đổi.

Ví dụ bảng theo dõi do nhóm duy trì:

| Giao diện/hành vi | Producer owner | Consumer đã biết | Liên hệ khi thay đổi |
|---|---|---|---|
| `GET /api/inventory/{sku}`, trường `available` | Inventory | Checkout | Chủ nhóm Checkout |
| `GET /api/inventory/{sku}`, trường `quantity` | Inventory | Checkout, Recommendation | Chủ nhóm hai consumer |
| Sự kiện `StockChanged` | Inventory | Analytics, Notifications | Chủ nhóm Analytics, Notifications |

Danh bạ này là **thông tin vận hành**, không được DSL sinh ra đầy đủ. Nó cần được cập nhật khi có consumer mới hoặc consumer thôi sử dụng giao diện. Với số lượng consumer lớn, có thể kết hợp catalog API, telemetry và tài liệu tích hợp, nhưng telemetry chỉ cho biết một phần tình trạng sử dụng, không thể mặc nhiên thay cho cam kết giữa các nhóm.

## 5. Vòng đời một thay đổi hợp đồng qua pull request

~~~mermaid
flowchart TD
    A["Consumer/producer đề xuất nhu cầu"] --> B["Tạo PR thay đổi Groovy/YAML DSL"]
    B --> C["Xác định owner và các consumer bị ảnh hưởng"]
    C --> D["Đánh giá tương thích và kế hoạch chuyển đổi"]
    D --> E["Producer chạy generated contract tests"]
    E --> F["Sinh candidate stub từ cùng revision"]
    F --> G["Consumer chạy test với candidate stub"]
    G --> H{"Review + CI đạt?"}
    H -->|Không| I["Chỉnh contract, implementation hoặc migration"]
    I --> D
    H -->|Có| J["Phê duyệt và merge theo chính sách"]
    J --> K["Build producer, xuất bản stub có version"]
    K --> L["Consumer nâng cấp có kiểm soát"]
~~~

Một luồng review hữu ích gồm các bước sau.

### Bước 1: Mô tả nhu cầu thay đổi

Người tạo PR nêu:

- Tình huống nghiệp vụ nào chưa được hỗ trợ?
- Ai đang sử dụng giao diện và người dùng chịu ảnh hưởng như thế nào?
- Request/response hoặc thông điệp thay đổi chính xác ở đâu?
- Đây là bổ sung, sửa lỗi hành vi, hay thay đổi không tương thích?
- Có cần giữ giao diện cũ trong thời gian chuyển đổi không?

Không nên chỉ ghi “refactor JSON” nếu thực tế thay đổi tên field, kiểu dữ liệu hoặc ngữ nghĩa.

### Bước 2: Review ý nghĩa trước khi review cú pháp

DSL hợp lệ về mặt cú pháp vẫn có thể mô tả sai nghĩa. Nhóm producer cần đánh giá:

- Tình huống có thể triển khai nhất quán không?
- Error status, header và thông tin trả về có thống nhất với chính sách API không?
- Có lộ chi tiết nội bộ hay thông tin nhạy cảm trong body/error message không?
- Matcher có quá cứng với dữ liệu động hoặc quá lỏng với field quan trọng không?

Nhóm consumer cần đánh giá:

- Contract có đúng thứ mà client đang hoặc sẽ phụ thuộc không?
- Hình dạng JSON/message và các kiểu dữ liệu có dùng được không?
- Có tình huống thành công, rỗng, lỗi mà consumer cần xử lý nhưng chưa được mô tả không?
- Nếu breaking change, client cần nâng cấp ở đâu và trước ngày nào?

### Bước 3: Kiểm chứng với code và stub thực tế

Spring Cloud Contract hỗ trợ sinh **generated contract tests** để producer chứng minh triển khai đáp ứng hợp đồng. Nó cũng tạo **stub** để consumer có thể kiểm tra logic tích hợp, thường qua **Stub Runner**.

Điểm quan trọng là hai phía phải kiểm chứng **cùng một candidate contract**. Nếu producer test chạy với commit mới nhưng consumer test dùng stub cũ từ artifact repository, cả hai có thể xanh trong khi thay đổi phá vỡ khả năng tương thích.

### Bước 4: Ghi nhận quyết định và công bố phiên bản

Khi review hoàn tất, PR nên lưu được **động cơ, mức ảnh hưởng, phương án tương thích, bằng chứng CI và các bên đã phê duyệt**. Sau khi merge, chỉ phát hành stub từ revision đã được kiểm chứng. Bảo vệ branch chính, gắn version cho artifact và cho consumer biết họ cần nâng cấp như thế nào.

## 6. Phân loại thay đổi trước khi phê duyệt

Tương thích không thể kết luận chỉ bằng việc DSL mới sinh test thành công. Cần xem xét **consumer đang phụ thuộc vào đâu**.

| Thay đổi ví dụ | Đánh giá ban đầu | Câu hỏi review cần đặt ra |
|---|---|---|
| Thêm field tùy chọn `warehouseCode` vào JSON response | Có thể tương thích | Consumer có bỏ qua field lạ hay parser đang strict? |
| Đổi `available` từ boolean sang string `"yes"/"no"` | Rủi ro cao, thường phá vỡ | Có consumer đang deserialize thành boolean không? |
| Đổi `GET /api/inventory/{sku}` thành path mới, bỏ path cũ | Phá vỡ request cũ | Có thể duy trì alias hoặc version cũ không? |
| Đổi `404` thành `200` + error body cho mã hàng không tồn tại | Rủi ro cao | Consumer có phân nhánh theo HTTP status không? |
| Thêm validation yêu cầu header vốn không bắt buộc | Có thể phá vỡ | Consumer cũ có gửi header này không? |
| Chỉ thay tên method Java nhưng giữ nguyên request/response | Thường không đổi hợp đồng | Generated test còn đại diện đúng hành vi không? |
| Đổi `quantity` từ số sang chuỗi trong event `StockChanged` | Rủi ro cao | Các subscriber có thể deserialize event cũ và mới không? |
| Thêm giá trị enum mới trong message | Tùy logic consumer | Consumer có xử lý giá trị chưa biết an toàn không? |
| Bỏ hoặc đổi thứ tự field JSON object | Bỏ field thường phá vỡ; đổi thứ tự key thường không cần cam kết | Consumer có lỡ phụ thuộc cấu trúc không được công bố không? |

Không có quy tắc “**thêm field luôn an toàn**”. Với consumer có bộ giải mã nghiêm ngặt, field mới cũng có thể gây lỗi. Ngược lại, thay đổi nội bộ producer có thể hoàn toàn không ảnh hưởng giao diện.

### Ví dụ review: đổi kiểu và đổi tên field

Contract đang công bố:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Ton kho cho SKU hop le'

    request {
        method 'GET'
        url '/api/inventory/SKU-101'
    }

    response {
        status 200
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-101',
            available: true,
            quantity: 12
        )
    }
}
~~~

Một PR đề xuất đổi `available: true` thành `availability: 'IN_STOCK'`, đồng thời xóa `available`. Producer có thể sửa implementation và contract mới để generated test xanh. Nhưng Checkout đang đọc boolean `available` sẽ không còn hoạt động.

Có ba hướng thường cần cân nhắc:

1. **Giữ tương thích trong giai đoạn chuyển tiếp:** producer trả thêm `availability` trong khi vẫn giữ `available`; nhóm consumer nâng cấp, sau đó lên lịch loại bỏ trường cũ.
2. **Đưa ra phiên bản giao diện mới:** giữ API/message cũ và công bố API/message version mới theo chính sách của hệ thống.
3. **Thay đổi cùng thời điểm có kiểm soát:** chỉ phù hợp khi tất cả consumer liên quan có thể triển khai đồng bộ và kế hoạch rollback/khả năng tương thích đã được đánh giá.

Dù chọn hướng nào, PR phải nói rõ **bản contract nào được dùng để tạo stub**, consumer nào đã thử phiên bản đó và mốc ngừng hỗ trợ hành vi cũ.

## 7. Ai phê duyệt một thay đổi phá vỡ tương thích?

Một quy tắc quản trị dễ thực hiện là:

- **Thay đổi bổ sung, được đánh giá tương thích:** producer owner duyệt ý nghĩa; CI phải chạy. Consumer liên quan được thông báo hoặc tham vấn theo mức rủi ro.
- **Thay đổi làm mất hoặc đổi hành vi đã cam kết:** producer owner và các consumer bị ảnh hưởng cần thống nhất kế hoạch chuyển đổi; chủ sở hữu API/nhóm phụ trách phát hành ra quyết định cuối theo quy định của tổ chức.
- **Thay đổi về cấu trúc kho hay quy trình kiểm tra:** maintainer kho duyệt phần công cụ/quy ước, đồng thời tham vấn producer/consumer nếu ảnh hưởng luồng build.

**Spring Cloud Contract không tự thực thi chính sách phê duyệt con người.** Đây là trách nhiệm của Git hosting, branch protection, review policy và quy trình làm việc. CI chứng minh một số tính chất kỹ thuật, không thay người chịu trách nhiệm xác nhận ý nghĩa nghiệp vụ.

Nếu một consumer không phản hồi, cũng không nên mặc định im lặng là đã chấp nhận thay đổi phá vỡ. Cần có lịch phản hồi và người có trách nhiệm quyết định cuối cùng đã được thống nhất trước.

## 8. Mẫu PR giúp reviewer quyết định nhanh

Một PR thay đổi contract nên có phần mô tả đủ để người không viết code vẫn đánh giá được ảnh hưởng:

~~~markdown
## Mục tiêu
Checkout cần phân biệt còn hàng và tạm hết hàng mà không suy đoán từ quantity.

## Giao diện thay đổi
- Producer: Inventory Service
- HTTP: GET /api/inventory/{sku}
- Contract: contracts/inventory/http/stockAvailable.groovy

## Trước / sau
- Trước: available: boolean
- Sau: thêm availability: "IN_STOCK" | "OUT_OF_STOCK"
- Giữ available trong giai đoạn chuyển tiếp

## Consumer chịu ảnh hưởng
- Checkout: đã chạy test với candidate stub
- Recommendation: chưa dùng field availability, vẫn cần kiểm tra parser

## Tương thích và chuyển đổi
- Đánh giá: bổ sung có điều kiện; cần kiểm tra consumer strict parsing
- Mốc dự kiến bỏ field cũ: chỉ xác định sau khi tất cả consumer chuyển đổi
- Kế hoạch rollback: duy trì response cũ nếu rollout gặp lỗi

## Bằng chứng kiểm chứng
- Generated contract tests producer: PASS
- Candidate stub artifact/revision: <điền phiên bản/commit thực tế>
- Consumer tests với Stub Runner: <điền link và trạng thái thực tế>

## Reviewer cần xác nhận
- Producer owner
- Các consumer chịu ảnh hưởng
- API owner nếu có thay đổi tương thích/phiên bản
~~~

Các dòng `PASS` trong ví dụ là **mẫu để điền kết quả thực**, không phải kết quả đã chạy. Review phải dẫn đến build log/artifact hoặc commit cụ thể thay vì ghi trạng thái chung chung.

Khi xem diff, nên đánh dấu những thay đổi có tác động đến ngữ nghĩa:

~~~diff
 body(
     sku: 'SKU-101',
-    available: true,
+    availability: 'IN_STOCK',
     quantity: 12
 )
~~~

Diff như vậy cần review về **việc xóa field cũ và kiểu dữ liệu mới**, dù đoạn code nhỏ. Với Groovy/YAML DSL, reviewer cũng cần xem matcher và request condition: thay đổi matcher từ “chỉ nhận số” sang “chấp nhận mọi chuỗi” có thể làm kiểm thử bớt khả năng phát hiện lỗi dù body ví dụ gần như giữ nguyên.

## 9. Quản lý phiên bản hợp đồng và artifact stub

Các revision cần có mối liên hệ truy vết:

~~~mermaid
flowchart LR
    A["Commit/Tag của contract"] --> B["Producer generated tests"]
    B --> C["Producer build đã xác minh"]
    C --> D["Stub artifact có version"]
    D --> E["Consumer test với Stub Runner"]
    E --> F["Kết quả CI gắn với version đó"]
~~~

Trong dự án dùng Maven, artifact stub thường được phát hành cùng producer dưới classifier `stubs`, ví dụ tọa độ minh họa `com.example:inventory-service:1.4.0:stubs`. Consumer cần biết mình đã dùng **chính xác tọa độ và phiên bản nào**.

Để một báo cáo review có giá trị, nên liên kết được:

| Đối tượng | Cần biết |
|---|---|
| Revision hợp đồng | Commit/tag của DSL Groovy/YAML đã được duyệt |
| Producer build | Commit producer chạy generated contract tests thành công |
| Stub artifact | Tọa độ, version, checksum hoặc build id nếu có |
| Consumer verification | Consumer nào, commit nào, phiên bản stub nào, test nào đã chạy |
| Quyết định phát hành | Ai duyệt, thời điểm hỗ trợ giao diện mới, thời gian duy trì hành vi cũ |

Không nên chỉ viết “đã test với latest stub”. Một alias trỏ tới phiên bản mới có thể thay đổi giữa các lần chạy CI, khiến lỗi khó tái hiện. Với kiểm thử dùng làm **điều kiện phát hành**, ưu tiên bản stub hoặc candidate artifact được xác định rõ ràng.

### Các nguyên tắc phát hành

1. **Chỉ phát hành stub đã kiểm chứng:** generated contract tests của producer phải chạy thành công trên đúng revision contract sẽ công bố.
2. **Không ghi đè artifact bất biến:** cùng một version của stub nên luôn trả về cùng nội dung, để build có thể tái lập.
3. **Duy trì phiên bản cũ khi còn consumer phụ thuộc:** đặc biệt với breaking change.
4. **Khai báo cách nâng cấp:** consumer phải biết khi nào chuyển sang stub mới và hành vi cũ được giữ đến bao giờ.
5. **Dùng chính sách version thống nhất:** có thể áp dụng quy ước SemVer hoặc quy ước phát hành của tổ chức, nhưng phiên bản không tự thay thế đánh giá tương thích.

Trong trường hợp hợp đồng được lưu ở repository dùng chung, producer cần ghi lại **revision của kho hợp đồng đã dùng để sinh test**. Nếu repository contract và repository producer có vòng đời độc lập, việc chỉ ghi version của producer có thể chưa đủ để truy nguồn.

## 10. Kiểm soát thay đổi bằng CI

Một pipeline phù hợp nên bao gồm cả kiểm tra cấu trúc kho và kiểm chứng hành vi:

| Cổng kiểm tra | Khi nào chạy | Mục đích |
|---|---|---|
| Kiểm tra file và quyền review | PR mở/cập nhật | Đúng vị trí hợp đồng, đúng owner, không bỏ qua quy tắc bảo vệ nhánh |
| Kiểm tra DSL và sinh test | PR của producer hoặc PR contract | Phát hiện cú pháp/cấu hình contract khiến việc sinh test thất bại |
| Chạy generated producer tests | Trước merge và phát hành | Kiểm tra producer thực thi đúng hợp đồng đang xét |
| Sinh candidate stub từ revision PR | Sau khi producer tests đạt | Cho consumer kiểm thử chính xác hành vi dự kiến công bố |
| Chạy consumer tests với Stub Runner | Với consumer chịu ảnh hưởng; theo mức độ ưu tiên | Kiểm tra request và xử lý response của client đối với candidate stub |
| Kiểm tra tương thích với giao diện cũ | Khi có thay đổi hoặc phát hành | Phát hiện việc xóa/đổi trường hợp mà consumer cũ còn phụ thuộc |
| Kiểm tra release và version artifact | Khi merge/release | Không phát hành stub sai revision hoặc ghi đè artifact đã phát hành |

Một luồng tổng quát có thể diễn đạt như sau:

~~~text
PR sửa contract
    |
    +-- Xác định owner, consumer phụ thuộc và mức độ thay đổi
    |
    +-- Parse DSL -> sinh test và stub
    |
    +-- Chạy producer generated contract tests
    |       |
    |       +-- FAIL -> chặn merge/phát hành, điều tra hợp đồng hoặc implementation
    |
    +-- Tạo candidate stub gắn với commit PR
    |
    +-- Consumer tests dùng Stub Runner + candidate stub
    |       |
    |       +-- FAIL -> giải quyết khả năng tương thích hoặc kế hoạch migration
    |
    +-- Phê duyệt bắt buộc -> merge -> phát hành stub có version
~~~

Đây là **quy trình tham khảo**, không phải file pipeline có thể chạy nguyên văn. Với Maven, build producer có thể dùng `./mvnw verify` khi plugin được cấu hình đúng; với Gradle, sử dụng các task của plugin phù hợp phiên bản đang dùng. Nếu dự án có nhiều producer/consumer, CI có thể chạy ma trận kiểm thử theo danh bạ phụ thuộc để tránh chạy tất cả dịch vụ cho mỗi thay đổi nhỏ.

**Giới hạn cần biết:**

- Producer generated tests có thể xanh sau khi **cả contract và code producer đều đổi**, nhưng consumer cũ vẫn bị phá vỡ. Cần kiểm tra khả năng tương thích với các contract/stub đang được sử dụng.
- Consumer test dùng stub chỉ kiểm chứng logic consumer đối với stub, không chứng minh producer thật đang chạy đúng. Cần cả phía producer.
- Test chỉ bảo vệ các tình huống đã được đặc tả. Việc bỏ sót một mã lỗi, một loại thông điệp hoặc một field quan trọng vẫn tạo ra lỗ hổng.
- Quy tắc reviewer, vòng đời version và chính sách ngừng hỗ trợ **không được Spring Cloud Contract tự quyết định**.

## 11. Những sai lầm quản trị thường gặp

| Tình huống | Hệ quả | Cách xử lý |
|---|---|---|
| Ai cũng có thể sửa DSL rồi merge trực tiếp | Thay đổi thiếu người chịu trách nhiệm | Bảo vệ nhánh, gán owner theo giao diện |
| Producer là owner nên bỏ qua consumer review | API đổi đúng theo code mới nhưng client cũ lỗi | Liệt kê consumer chịu ảnh hưởng, quy định review/migration |
| Một kho chung nhưng producer luôn kéo nhánh `main` mới nhất | Build không tái lập, có thể lấy contract chưa ổn định | Pin tag/commit/version của contract |
| Stub sinh ra nhưng không chạy generated tests producer | Stub có thể khác implementation thật | Bắt buộc test producer trước khi publish |
| Reviewer chỉ nhìn JSON mẫu mà không xem matcher | Test dễ quá lỏng hoặc quá cứng | Review cả điều kiện request, matcher, status, header |
| Có `CODEOWNERS` nhưng không yêu cầu review | Hệ thống vẫn cho merge thiếu phê duyệt | Cấu hình branch protection/rulesets |
| Thay đổi phá vỡ được ngụy trang bằng version nhỏ | Consumer nâng cấp tự động rồi lỗi | Đánh giá tương thích và truyền thông phiên bản rõ ràng |
| Không lưu bằng chứng consumer test đã dùng stub nào | Không thể kiểm chứng quyết định phát hành | Ghi artifact coordinates, version, build/commit trong PR và CI |
| Mọi test xanh nên cho xóa trường cũ ngay | Có consumer chưa được liệt kê hoặc chưa triển khai | Cập nhật danh bạ phụ thuộc và quy trình ngừng hỗ trợ |

## 12. Tình huống thực hành: ai có quyền merge?

Nhóm Inventory muốn đổi `GET /api/inventory/{sku}` để trả:

~~~json
{
  "sku": "SKU-101",
  "stockStatus": "IN_STOCK",
  "quantity": 12
}
~~~

Trước đây response là:

~~~json
{
  "sku": "SKU-101",
  "available": true,
  "quantity": 12
}
~~~

Checkout đọc `available` để cho phép đặt hàng, trong khi Recommendation chỉ đọc `quantity`. Nhóm Inventory cập nhật Groovy DSL và code; producer generated tests đều xanh. PR chỉ có một reviewer thuộc Inventory.

Hãy tự trả lời trước khi xem gợi ý:

1. **PR đã an toàn để merge chưa?** Chưa đủ cơ sở. Generated tests mới xác nhận producer đáp ứng contract mới; Checkout vẫn có thể lỗi vì field `available` bị xóa.
2. **Ai cần tham gia review?** Inventory xác nhận nghĩa và khả năng triển khai; Checkout xác nhận tác động và kế hoạch nâng cấp. Recommendation cũng cần được kiểm tra về khả năng parse field lạ/thiếu dù không đọc `available`. Maintainer và API owner tham gia theo chính sách của kho.
3. **Phương án ít làm gián đoạn hơn?** Giữ `available` trong thời gian chuyển đổi và bổ sung `stockStatus`; viết contract cho cả hành vi mới và nghĩa vụ giữ tương thích. Với thay đổi lớn, cân nhắc API/version mới.
4. **Cần bằng chứng gì?** Generated tests với producer candidate; candidate stub gắn với revision PR; kết quả test các consumer bị ảnh hưởng với Stub Runner; ghi phiên bản và quyết định migration.
5. **Khi nào có thể xóa `available`?** Khi đạt điều kiện ngừng hỗ trợ đã thỏa thuận, các consumer liên quan đã chuyển đổi hoặc có phương án tương thích, và quy trình review/phát hành được hoàn thành.

### Checklist ngắn trước khi phê duyệt

- [ ] Tên giao diện và producer owner được xác định rõ.
- [ ] Consumer chịu ảnh hưởng và người liên hệ đã được rà soát.
- [ ] PR giải thích chính xác hành vi cũ, mới và mức độ tương thích.
- [ ] Trường hợp thành công, dữ liệu rỗng, lỗi và messaging liên quan đã được cân nhắc.
- [ ] DSL và matcher được review cả về cú pháp lẫn ý nghĩa.
- [ ] Generated contract tests producer chạy trên đúng revision.
- [ ] Candidate stub được phát hành/tạo với tọa độ có thể truy vết.
- [ ] Consumer test kiểm chứng client thật với đúng candidate stub.
- [ ] Có kế hoạch migration và mốc ngừng hỗ trợ nếu thay đổi phá vỡ tương thích.
- [ ] Review, branch protection và CI đáp ứng chính sách trước khi merge.

## 13. Câu hỏi tự kiểm tra

1. Vì sao người sở hữu repository không nhất thiết là người duy nhất được quyết định một thay đổi hợp đồng?
2. Ưu điểm và rủi ro khác nhau giữa hợp đồng lưu chung với producer và trong kho hợp đồng độc lập là gì?
3. Khi có `CODEOWNERS`, điều gì vẫn cần cấu hình để bảo đảm review bắt buộc?
4. Vì sao thay đổi Groovy DSL cùng code producer có thể khiến generated tests xanh nhưng vẫn phá vỡ consumer?
5. Cần ghi lại những thông tin nào để biết consumer test thực sự sử dụng stub của revision PR?
6. Với một sự kiện không còn trường cũ, việc kiểm tra consumer còn quan trọng như thế nào dù không có HTTP status?

## Ghi nhớ

**Kho hợp đồng là điểm phối hợp giữa các nhóm, không chỉ là nơi chứa file Groovy/YAML.** Producer chịu trách nhiệm hiện thực và phát hành hành vi đã cam kết; consumer phải xác nhận những gì mình phụ thuộc; người duy trì kho tổ chức quy tắc đóng góp và bảo vệ lịch sử thay đổi. Một quy trình review đáng tin cậy kết hợp **quyền sở hữu theo giao diện, đánh giá tương thích, generated tests phía producer, candidate stub qua Stub Runner, quản lý phiên bản và cổng kiểm tra CI**. Nhờ đó, thay đổi API hoặc thông điệp có thể được trao đổi và phát hiện rủi ro trước khi phá vỡ consumer trong môi trường thật.
