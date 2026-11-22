# Kiểm thử dựa trên mô hình trạng thái, quy tắc hoặc luồng nghiệp vụ

Khi phần mềm có nhiều trạng thái, điều kiện rẽ nhánh và bước phối hợp giữa các thành phần, một danh sách test case viết riêng lẻ rất dễ bỏ sót hành vi quan trọng. Nhóm có thể kiểm tra từng màn hình hoặc API nhưng không nhận ra một chuyển trạng thái sai, một tổ hợp điều kiện chưa được xét hoặc một nhánh lỗi trong quy trình nghiệp vụ.

Kiểm thử dựa trên mô hình giúp biểu diễn hành vi cần xác minh bằng một cấu trúc có thể phân tích. Mô hình có thể mô tả trạng thái và sự kiện, quy tắc quyết định, hoặc trình tự hoạt động của một quy trình. Từ mô hình, nhóm suy ra tình huống kiểm thử, dữ liệu, kết quả mong đợi và tiêu chí bao phủ. Cách tiếp cận này đặc biệt hữu ích với luồng có nhiều nhánh, nghiệp vụ có điều kiện phức tạp, hệ thống bất đồng bộ và chức năng phải tuân thủ những quy tắc nhất quán.

## 1. Kiểm thử dựa trên mô hình là gì?

**Kiểm thử dựa trên mô hình (model-based testing)** là cách thiết kế và thực hiện kiểm thử dựa trên một biểu diễn trừu tượng của hành vi, quy tắc hoặc luồng mà hệ thống cần tuân theo. Mô hình giữ lại những đặc điểm quan trọng đối với mục tiêu kiểm thử và lược bỏ chi tiết không cần thiết.

Một mô hình kiểm thử có thể mô tả:

- Các trạng thái mà đối tượng hoặc quy trình có thể đi qua.
- Sự kiện hoặc hành động làm thay đổi trạng thái.
- Điều kiện để một hành động được phép thực hiện.
- Quy tắc quyết định kết quả từ một tập điều kiện đầu vào.
- Trình tự công việc, nhánh rẽ, vòng lặp và bước xử lý ngoại lệ.
- Bất biến hoặc thuộc tính luôn phải đúng trong suốt quá trình.

Mô hình không nhất thiết phải là sơ đồ phức tạp hoặc được sinh tự động. Nó có thể là bảng chuyển trạng thái, bảng quyết định, sơ đồ luồng, statechart, biểu đồ tuần tự, mô hình dữ liệu hoặc một tập quy tắc có cấu trúc.

Điểm quan trọng là mô hình phải đủ rõ để nhóm có thể xác định **đầu vào, hành vi được phép, kết quả mong đợi và cách đánh giá mức bao phủ**. Mô hình cần được kiểm tra với người hiểu nghiệp vụ và người chịu trách nhiệm kỹ thuật trước khi dùng làm căn cứ kiểm thử.

### 1.1. Mô hình và kiểm thử dựa trên mô hình

Mô hình là mô tả hành vi mong đợi hoặc những thuộc tính cần giữ. Kiểm thử dựa trên mô hình sử dụng mô tả đó để:

1. Xác định các tình huống cần kiểm tra.
2. Sinh hoặc thiết kế chuỗi sự kiện, dữ liệu và điều kiện.
3. Xác định kết quả mong đợi ở từng bước.
4. Đo mức bao phủ mô hình.
5. So sánh hành vi thực tế của hệ thống với mô hình.

Mô hình có thể được dùng thủ công để thiết kế test case, hoặc được công cụ dùng để sinh chuỗi kiểm thử và kiểm tra kết quả. Tự động hóa không phải điều kiện bắt buộc để áp dụng cách tiếp cận này.

Một lưu ý quan trọng: mô hình cũng có thể sai hoặc thiếu. Nếu mô hình được xây dựng từ chính hành vi sai của phần mềm rồi dùng lại làm chuẩn, kiểm thử có thể xác nhận một lỗi đang tồn tại. Vì vậy, cần có nguồn yêu cầu, quy tắc nghiệp vụ, hợp đồng hoặc người có thẩm quyền xác nhận mô hình.

## 2. Ba cách biểu diễn thường dùng

| Cách tiếp cận | Tập trung vào | Câu hỏi chính | Ví dụ phù hợp |
|---|---|---|---|
| Dựa trên mô hình trạng thái | Trạng thái, sự kiện và chuyển trạng thái | Đối tượng đang ở trạng thái nào, sự kiện nào được phép tiếp theo? | Đơn hàng, thanh toán, tài khoản, phiên đăng nhập |
| Dựa trên mô hình quy tắc | Điều kiện, tổ hợp điều kiện và hành động/kết quả | Với các điều kiện này, hệ thống phải quyết định điều gì? | Định giá, giảm giá, phân quyền, tính phí |
| Dựa trên mô hình luồng nghiệp vụ | Trình tự hoạt động, nhánh, vòng lặp và bàn giao | Quy trình đi qua những bước nào và xử lý ngoại lệ ra sao? | Đặt hàng, hoàn tiền, phê duyệt, đăng ký dịch vụ |

Ba cách biểu diễn có thể kết hợp trong một bài toán. Một quy trình đặt hàng có thể được mô hình hóa thành luồng nghiệp vụ; từng đơn hàng có state machine riêng; quy tắc xác định phí vận chuyển hoặc điều kiện hoàn tiền được biểu diễn bằng bảng quyết định.

## 3. Kiểm thử dựa trên mô hình trạng thái

### 3.1. Thành phần của mô hình trạng thái

Mô hình trạng thái mô tả cách một đối tượng thay đổi theo thời gian khi nhận sự kiện hoặc hành động. Các thành phần thường gồm:

- **Trạng thái (state):** tình trạng hiện tại của đối tượng, ví dụ PENDING_PAYMENT hoặc SHIPPED.
- **Sự kiện (event):** điều xảy ra và có thể kích hoạt thay đổi, ví dụ PaymentSucceeded hoặc CancelRequested.
- **Chuyển trạng thái (transition):** sự thay đổi từ trạng thái này sang trạng thái khác khi sự kiện và điều kiện phù hợp.
- **Điều kiện bảo vệ (guard):** điều kiện phải đúng để chuyển trạng thái được thực hiện.
- **Hành động (action):** tác động phát sinh khi chuyển trạng thái, ví dụ ghi nhận thời điểm thanh toán hoặc phát sự kiện.
- **Trạng thái đầu và trạng thái kết thúc:** điểm bắt đầu và những trạng thái hoàn tất của vòng đời đang mô hình hóa.
- **Bất biến (invariant):** thuộc tính phải luôn đúng, bất kể đối tượng đang ở trạng thái nào.

Ví dụ, đơn hàng ở trạng thái PENDING_PAYMENT chỉ được chuyển sang CONFIRMED khi nhận được kết quả thanh toán hợp lệ. Nếu thanh toán thất bại, đơn hàng có thể chuyển sang PAYMENT_FAILED; nếu hết hạn, quy trình có thể hủy đơn theo chính sách.

### 3.2. Ví dụ mô hình vòng đời đơn hàng

Giả sử một hệ thống thương mại điện tử có vòng đời đơn hàng đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_PAYMENT: Submit / đơn hợp lệ
    DRAFT --> REJECTED: Submit / dữ liệu không hợp lệ
    PENDING_PAYMENT --> CONFIRMED: PaymentSucceeded
    PENDING_PAYMENT --> PAYMENT_FAILED: PaymentFailed
    PENDING_PAYMENT --> CANCELLED: Timeout hoặc CancelAccepted
    PAYMENT_FAILED --> PENDING_PAYMENT: RetryAllowed
    PAYMENT_FAILED --> CANCELLED: RetryExpired
    CONFIRMED --> FULFILLING: StartFulfillment
    FULFILLING --> SHIPPED: ShipmentCreated
    SHIPPED --> COMPLETED: DeliveryConfirmed
    CONFIRMED --> CANCELLED: CancelAllowed
    COMPLETED --> [*]
    CANCELLED --> [*]
    REJECTED --> [*]
~~~

Sơ đồ chỉ là mô hình minh họa. Một sản phẩm thực tế cần xác định rõ điều kiện, thời hạn, quyền và chính sách cho từng chuyển trạng thái. Ví dụ, hủy đơn sau khi đã xác nhận thanh toán có thể cần quy trình hoàn tiền riêng.

Không nên gộp mọi trạng thái của đơn hàng và thanh toán vào một biến trạng thái duy nhất nếu hai đối tượng có vòng đời độc lập. Có thể mô hình hóa Order và Payment thành hai state machine liên quan với nhau qua sự kiện. Điều này giúp phát hiện các tình huống như đơn hàng đã xác nhận nhưng giao dịch vẫn chưa được đối soát.

### 3.3. Bảng chuyển trạng thái

Bảng chuyển trạng thái giúp kiểm tra mô hình chi tiết hơn sơ đồ:

| Trạng thái hiện tại | Sự kiện | Điều kiện | Trạng thái tiếp theo | Hành động hoặc kết quả |
|---|---|---|---|---|
| DRAFT | Submit | Dữ liệu hợp lệ, tồn kho được giữ | PENDING_PAYMENT | Tạo yêu cầu thanh toán |
| DRAFT | Submit | Thiếu dữ liệu bắt buộc | REJECTED | Trả lỗi xác thực |
| PENDING_PAYMENT | PaymentSucceeded | Chữ ký và mã giao dịch hợp lệ | CONFIRMED | Ghi nhận giao dịch và xác nhận đơn |
| PENDING_PAYMENT | PaymentFailed | Phản hồi thất bại hợp lệ | PAYMENT_FAILED | Lưu lý do thất bại |
| PENDING_PAYMENT | Timeout | Đã quá thời hạn chờ | CANCELLED | Giải phóng giữ chỗ theo chính sách |
| PAYMENT_FAILED | Retry | Còn trong thời hạn và được phép thử lại | PENDING_PAYMENT | Tạo lần thử mới có liên kết |
| CONFIRMED | StartFulfillment | Đơn đủ điều kiện xử lý | FULFILLING | Gửi yêu cầu chuẩn bị hàng |
| FULFILLING | ShipmentCreated | Có mã vận đơn hợp lệ | SHIPPED | Lưu thông tin giao hàng |
| SHIPPED | DeliveryConfirmed | Có xác nhận giao hàng | COMPLETED | Đóng vòng đời đơn |

Bảng này là một nguồn để thiết kế test case. Mỗi dòng có thể trở thành một hoặc nhiều tình huống tùy theo dữ liệu, quyền, điều kiện biên và lỗi có thể xảy ra.

### 3.4. Những gì cần kiểm tra

**Bao phủ trạng thái (state coverage):** mọi trạng thái quan trọng đều được đi tới ít nhất một lần. Điều này giúp phát hiện trạng thái không thể đạt đến hoặc chưa có kiểm thử.

**Bao phủ chuyển trạng thái (transition coverage):** mọi chuyển trạng thái hợp lệ trong mô hình đều được thực hiện ít nhất một lần. Đây thường là mục tiêu hữu ích hơn chỉ bao phủ trạng thái vì lỗi có thể nằm trong hành động hoặc điều kiện chuyển.

**Bao phủ cặp chuyển trạng thái (transition-pair coverage):** kiểm tra các cặp chuyển tiếp liên tiếp hợp lệ. Ví dụ, PENDING_PAYMENT → PAYMENT_FAILED → PENDING_PAYMENT để xác minh thử lại sau thất bại.

**Bao phủ đường đi (path coverage):** kiểm tra chuỗi chuyển trạng thái dài hơn. Số đường đi có thể tăng rất nhanh khi mô hình có vòng lặp, vì vậy thường chọn đường đi theo rủi ro hoặc giới hạn độ dài.

**Chuyển trạng thái không hợp lệ:** thử gửi sự kiện không được phép ở trạng thái hiện tại, ví dụ yêu cầu giao hàng khi đơn chưa được xác nhận. Hệ thống phải từ chối hoặc xử lý theo chính sách mà không làm hỏng trạng thái.

**Điều kiện bảo vệ:** kiểm tra cả khi guard đúng và sai, đặc biệt ở ranh giới thời gian, quyền, số lượng và số tiền.

**Bất biến:** xác minh thuộc tính phải đúng ở mọi trạng thái, ví dụ đơn không được vừa CANCELLED vừa COMPLETED; một giao dịch không được ghi nhận thành công hai lần.

Không phải mọi hệ thống đều cần bao phủ mọi đường đi. Hãy chọn tiêu chí dựa trên mức rủi ro, số lượng trạng thái, độ phức tạp và chi phí thực thi.

### 3.5. Thiết kế chuỗi kiểm thử

Một test case trạng thái thường cần:

1. Khởi tạo đối tượng ở trạng thái ban đầu đã biết.
2. Gửi một hoặc nhiều sự kiện theo thứ tự xác định.
3. Thiết lập điều kiện guard và dữ liệu liên quan.
4. Quan sát trạng thái mới sau mỗi sự kiện.
5. Kiểm tra hành động phụ, dữ liệu lưu trữ và sự kiện phát ra.
6. Kiểm tra rằng các chuyển trạng thái không hợp lệ không làm thay đổi dữ liệu ngoài ý muốn.

Ví dụ:

| Bước | Hành động | Kết quả mong đợi |
|---|---|---|
| 1 | Tạo đơn có dữ liệu hợp lệ | Đơn ở DRAFT |
| 2 | Gửi yêu cầu thanh toán | Đơn chuyển PENDING_PAYMENT |
| 3 | Nhận callback thanh toán thất bại | Đơn chuyển PAYMENT_FAILED |
| 4 | Thử lại trong thời hạn cho phép | Đơn chuyển về PENDING_PAYMENT, lần thử mới được liên kết |
| 5 | Nhận callback thành công hợp lệ | Đơn chuyển CONFIRMED, giao dịch chỉ được ghi nhận một lần |
| 6 | Gửi lại cùng callback thành công | Không tạo giao dịch hoặc thông báo trùng |

## 4. Kiểm thử dựa trên mô hình quy tắc

### 4.1. Khi nào nên dùng?

Mô hình quy tắc phù hợp khi kết quả phụ thuộc vào nhiều điều kiện kết hợp. Nếu viết từng test case bằng văn bản, nhóm dễ bỏ sót tổ hợp hoặc lặp lại những trường hợp giống nhau.

Ví dụ quy tắc có thể phụ thuộc vào:

- Loại khách hàng và trạng thái tài khoản.
- Giá trị đơn hàng và loại sản phẩm.
- Khu vực giao hàng và phương thức vận chuyển.
- Thời gian, hạn mức và trạng thái chương trình.
- Vai trò người dùng và quyền thao tác.

### 4.2. Bảng quyết định

Bảng quyết định (decision table) liệt kê điều kiện và hành động tương ứng với các tổ hợp. Mỗi cột quy tắc đại diện cho một tổ hợp điều kiện có ý nghĩa.

Ví dụ, một mã giảm giá chỉ được áp dụng khi mã còn hiệu lực, đơn đạt mức tối thiểu và khách hàng thuộc nhóm được phép:

| Điều kiện / Quy tắc | R1 | R2 | R3 | R4 |
|---|---:|---:|---:|---:|
| Mã còn hiệu lực? | Có | Không | Có | Có |
| Đơn đạt giá trị tối thiểu? | Có | Có | Không | Có |
| Khách thuộc nhóm áp dụng? | Có | Có | Có | Không |
| Áp dụng giảm giá? | Có | Không | Không | Không |
| Lý do từ chối | — | Hết hạn | Chưa đạt mức tối thiểu | Không đủ điều kiện |

Từ bảng có thể tạo test case cho từng quy tắc. Nếu có nhiều điều kiện, số tổ hợp có thể tăng theo cấp số nhân. Nhóm nên dùng phân tích rủi ro, phân vùng tương đương, pairwise hoặc kỹ thuật giảm tổ hợp phù hợp, đồng thời giữ lại những tổ hợp bắt buộc theo nghiệp vụ.

### 4.3. Kỹ thuật kiểm thử quy tắc

- **Bao phủ quy tắc (rule coverage):** mỗi cột hoặc nhánh quyết định quan trọng được kiểm tra.
- **Bao phủ điều kiện (condition coverage):** từng điều kiện được kiểm tra với giá trị đúng và sai.
- **Bao phủ tổ hợp điều kiện:** kiểm tra những tổ hợp có khả năng làm thay đổi kết quả.
- **Giá trị biên:** kiểm tra ngay dưới, đúng tại và ngay trên ngưỡng, ví dụ đơn hàng tối thiểu 500.000 đồng.
- **Phân vùng tương đương:** chọn đại diện cho các nhóm dữ liệu được xử lý giống nhau.
- **MC/DC:** với logic quan trọng, kiểm tra để chứng minh mỗi điều kiện có thể tác động độc lập đến kết quả quyết định, khi tiêu chuẩn hoặc mức rủi ro yêu cầu.

Ví dụ nếu ngưỡng tối thiểu là 500.000 đồng, cần xác định chính xác cách xử lý 499.999, 500.000 và 500.001 đồng, cũng như đơn vị tiền tệ và cách làm tròn trước khi so sánh.

### 4.4. Quy tắc phải có nguồn xác nhận

Không nên suy ra quy tắc từ một vài kết quả quan sát được. Cần xác nhận công thức, thứ tự ưu tiên, ngoại lệ và nguồn dữ liệu với chủ sở hữu nghiệp vụ. Ví dụ, khi một đơn hàng có nhiều mã giảm giá, chính sách có thể quy định chỉ áp dụng mã có lợi nhất, mã được chọn trước hoặc không cho kết hợp. Mỗi cách dẫn đến kết quả khác nhau.

Nếu quy tắc thay đổi theo thời gian hoặc phân khúc, mô hình cần ghi rõ phiên bản và thời điểm hiệu lực để test case không dùng nhầm chính sách cũ.

## 5. Kiểm thử dựa trên mô hình luồng nghiệp vụ

### 5.1. Mô hình luồng là gì?

Mô hình luồng nghiệp vụ biểu diễn thứ tự các hoạt động, điểm quyết định, nhánh song song, vòng lặp và đường xử lý ngoại lệ. Nó giúp nhóm nhìn thấy hành trình hoàn chỉnh và các điểm bàn giao giữa người dùng, dịch vụ hoặc bộ phận.

Một luồng thường có:

- Điểm bắt đầu và điều kiện khởi tạo.
- Hoạt động do người dùng hoặc hệ thống thực hiện.
- Điểm quyết định dựa trên dữ liệu hoặc quy tắc.
- Nhánh thành công và nhánh thất bại.
- Vòng lặp, thử lại hoặc chờ phản hồi.
- Hoạt động song song và điểm đồng bộ.
- Bước bù trừ, rollback hoặc xử lý thủ công.
- Điểm kết thúc và kết quả nghiệp vụ.

### 5.2. Ví dụ luồng đặt hàng

~~~mermaid
flowchart TD
    A["Khách xác nhận giỏ hàng"] --> B["Kiểm tra giá và tồn kho"]
    B --> C{"Đơn hợp lệ?"}
    C -->|Không| D["Thông báo lỗi và yêu cầu chỉnh sửa"]
    D --> A
    C -->|Có| E["Tạo đơn chờ thanh toán"]
    E --> F["Gửi yêu cầu thanh toán"]
    F --> G{"Thanh toán thành công?"}
    G -->|Có| H["Xác nhận đơn"]
    G -->|Thất bại| I["Hiển thị lỗi hoặc cho thử lại"]
    I --> J{"Còn được thử lại?"}
    J -->|Có| F
    J -->|Không| K["Hủy đơn và giải phóng giữ chỗ"]
    H --> L["Chuẩn bị và giao hàng"]
    L --> M["Xác nhận giao hàng"]
    M --> N["Hoàn tất"]
~~~

Sơ đồ này cho thấy các nhánh cần kiểm tra: đơn không hợp lệ, thanh toán thất bại, thử lại, hết thời hạn, giải phóng giữ chỗ và giao hàng. Nhóm cũng cần xác định điều gì xảy ra nếu thanh toán thành công nhưng hệ thống không nhận được phản hồi, hoặc đơn đã bị hủy trước khi callback đến.

### 5.3. Tiêu chí bao phủ luồng

- **Bao phủ hoạt động:** mỗi hoạt động quan trọng được thực hiện ít nhất một lần.
- **Bao phủ nhánh:** mỗi nhánh quyết định quan trọng được đi qua.
- **Bao phủ đường đi:** các chuỗi hoạt động được chọn theo rủi ro và độ dài hợp lý.
- **Bao phủ ngoại lệ:** luồng timeout, lỗi dịch vụ, từ chối, thử lại và bù trừ được kiểm tra.
- **Bao phủ bàn giao:** dữ liệu và trạng thái được xác minh ở nơi chuyển giữa các vai trò hoặc dịch vụ.
- **Bao phủ vòng lặp:** điều kiện thoát, giới hạn số lần lặp và hành vi khi thử lại liên tục được kiểm tra.

Một quy trình có nhiều nhánh và vòng lặp có thể có số đường đi rất lớn. Không cần liệt kê mọi đường đi nếu chi phí không hợp lý. Hãy chọn đường đi quan trọng theo rủi ro, bổ sung các cặp nhánh có tương tác và kiểm tra những tình huống lỗi có hậu quả lớn.

## 6. Kết hợp mô hình trạng thái, quy tắc và luồng

Trong sản phẩm thực tế, ba mô hình bổ sung cho nhau:

- Mô hình luồng cho biết người dùng hoặc dịch vụ đi qua các bước nào.
- Mô hình trạng thái xác định đối tượng có thể ở trạng thái nào và chuyển đổi ra sao.
- Mô hình quy tắc quyết định nhánh hoặc hành động nào được chọn trong một tình huống.

Ví dụ, luồng đặt hàng gọi quy tắc kiểm tra mã giảm giá; nếu đơn hợp lệ, nó tạo đơn ở trạng thái PENDING_PAYMENT; khi nhận sự kiện thanh toán, state machine chuyển đơn sang CONFIRMED hoặc PAYMENT_FAILED. Một bộ kiểm thử tốt cần xác minh cả quyết định, trạng thái và tác động xuyên suốt quy trình.

~~~mermaid
flowchart LR
    A["Luồng nghiệp vụ<br/>Các bước và bàn giao"] --> B["Quy tắc quyết định<br/>Điều kiện và hành động"]
    B --> C["Mô hình trạng thái<br/>Trạng thái và chuyển trạng thái"]
    C --> D["Test case, dữ liệu và oracle"]
    D --> E["Kết quả và độ bao phủ"]
~~~

Không nên tạo ba mô hình tách rời rồi để chúng mâu thuẫn. Cần dùng cùng thuật ngữ, định danh, quy tắc và phiên bản. Nếu một quy tắc thay đổi, hãy xác định các chuyển trạng thái và nhánh luồng bị ảnh hưởng.

## 7. Quy trình áp dụng kiểm thử dựa trên mô hình

### Bước 1: Chọn đối tượng và rủi ro

Chọn một chức năng, đối tượng hoặc quy trình có hành vi đủ phức tạp hoặc có rủi ro đáng kể. Xác định mục tiêu chất lượng, phạm vi và hậu quả nếu hành vi sai.

### Bước 2: Thu thập cơ sở và xác nhận người có thẩm quyền

Thu thập yêu cầu, tiêu chí chấp nhận, quy tắc nghiệp vụ, hợp đồng và dữ liệu tham chiếu. Xác định ai giải thích và ai phê duyệt mô hình. Ghi nhận những giả định chưa được xác nhận.

### Bước 3: Chọn dạng mô hình

- Chọn state machine khi hành vi phụ thuộc trạng thái hiện tại và sự kiện.
- Chọn bảng quyết định khi kết quả phụ thuộc tổ hợp điều kiện.
- Chọn sơ đồ luồng khi cần kiểm tra trình tự hoạt động, nhánh, vòng lặp và bàn giao.
- Kết hợp các dạng khi bài toán có nhiều chiều.

### Bước 4: Xây dựng và rà soát mô hình

Liệt kê trạng thái, sự kiện, điều kiện, hành động, quy tắc, nhánh và điểm kết thúc. Kiểm tra trạng thái không thể đạt đến, chuyển trạng thái không có điều kiện rõ ràng, nhánh thiếu hoặc vòng lặp không có điều kiện thoát. Nhờ người hiểu nghiệp vụ và kỹ thuật xác nhận.

### Bước 5: Xác định oracle và tiêu chí bao phủ

Với mỗi trạng thái, chuyển trạng thái, quy tắc hoặc nhánh, xác định kết quả mong đợi và bằng chứng quan sát được. Chọn tiêu chí bao phủ phù hợp với rủi ro: state, transition, rule, condition, branch hoặc path coverage.

### Bước 6: Thiết kế dữ liệu và chuỗi kiểm thử

Chuẩn bị dữ liệu để đạt được trạng thái hoặc điều kiện cần kiểm tra. Với luồng dài, tạo fixture hoặc API hỗ trợ để đưa hệ thống đến trạng thái ban đầu có kiểm soát. Không bỏ qua việc kiểm tra chuỗi sự kiện thực tế nếu thứ tự và độ trễ là một phần của rủi ro.

### Bước 7: Thực thi và so sánh

Chạy test case, quan sát trạng thái, dữ liệu, sự kiện, log và tác động phụ. So sánh với oracle đã thống nhất. Khi thất bại, ghi lại chuỗi sự kiện, dữ liệu, môi trường và trạng thái trước/sau để tái hiện.

### Bước 8: Cập nhật mô hình

Khi yêu cầu hoặc chính sách thay đổi, cập nhật mô hình, test case, dữ liệu và tiêu chí bao phủ. Khi phát hiện hành vi chưa được mô hình hóa, làm rõ đó là yêu cầu mới, ngoại lệ hợp lệ hay lỗi của hệ thống.

## 8. Ví dụ tổng hợp: kiểm thử thanh toán và hoàn tiền

Một hệ thống thanh toán cần phối hợp nhiều trạng thái, quy tắc và luồng. Có thể chia mô hình như sau:

| Mô hình | Nội dung cần biểu diễn | Tình huống kiểm thử tiêu biểu |
|---|---|---|
| Trạng thái Payment | INITIATED, AUTHORIZED, CAPTURED, FAILED, VOIDED, REFUND_PENDING, REFUNDED | Không capture hai lần; không hoàn tiền trước khi giao dịch đủ điều kiện |
| Quy tắc hoàn tiền | Thời hạn, loại giao dịch, số tiền còn có thể hoàn, quyền người yêu cầu | Ngay trước, tại và sau hạn; hoàn một phần; vượt số dư có thể hoàn |
| Luồng nghiệp vụ | Tạo giao dịch, xác thực, capture, đối soát, yêu cầu hoàn, nhận callback và cập nhật đơn | Timeout, callback lặp, nhà cung cấp từ chối, hệ thống gián đoạn giữa hai bước |

Một số bất biến cần cân nhắc:

- Tổng số tiền hoàn thành công không vượt quá số tiền đã capture, theo chính sách áp dụng.
- Một yêu cầu hoặc callback lặp không tạo tác động tài chính lặp.
- Trạng thái REFUNDED chỉ được ghi nhận khi có bằng chứng xác nhận theo hợp đồng.
- Mọi thay đổi trạng thái quan trọng đều có dấu vết giao dịch và thời điểm.
- Khi quy trình thất bại giữa chừng, trạng thái phải cho phép đối soát hoặc xử lý tiếp mà không tạo giao dịch sai.

Những bất biến này phải được xác nhận với chủ nghiệp vụ và chủ sở hữu tích hợp. Chúng có thể trở thành oracle cho nhiều test case ở cấp đơn vị, API, tích hợp và đầu cuối.

## 9. Lựa chọn mức độ tự động hóa

Mô hình có thể hỗ trợ tự động hóa theo nhiều mức:

- **Thiết kế thủ công từ mô hình:** phù hợp khi mô hình nhỏ, thay đổi ít hoặc cần chuyên gia đánh giá từng tình huống.
- **Sinh test case từ mô hình:** công cụ tạo chuỗi chuyển trạng thái, tổ hợp điều kiện hoặc đường đi theo tiêu chí bao phủ.
- **Sinh dữ liệu và điều khiển hệ thống:** công cụ tạo dữ liệu, gọi API hoặc kích hoạt sự kiện để đưa hệ thống đến trạng thái cần kiểm tra.
- **Kiểm tra kết quả tự động:** assertion so sánh trạng thái, sự kiện, dữ liệu và bất biến với oracle.
- **Kiểm tra mô hình và hệ thống:** dùng cùng mô hình để sinh chuỗi sự kiện rồi so sánh phản hồi của hệ thống với hành vi được mô hình cho phép.

Khi tự động hóa, cần quan tâm đến khả năng tái lập, thời gian chạy, độ ổn định của môi trường và cách chẩn đoán lỗi. Một test case sinh tự động nhưng khó hiểu hoặc khó tái hiện có thể làm giảm giá trị của bộ kiểm thử.

Không nên dùng cùng một hàm triển khai nghiệp vụ làm cả mã sản phẩm và oracle mà không có kiểm chứng độc lập. Nếu cả hai cùng chứa một lỗi, so sánh sẽ không phát hiện được sai lệch. Với logic quan trọng, nên có ví dụ chuẩn, công thức độc lập hoặc xác nhận từ chuyên gia.

## 10. Những sai lầm thường gặp

- **Mô hình quá chi tiết:** mô tả mọi thao tác kỹ thuật làm mô hình khó hiểu và khó bảo trì. Chỉ giữ chi tiết cần thiết cho mục tiêu kiểm thử.
- **Mô hình quá đơn giản:** bỏ qua trạng thái lỗi, điều kiện bảo vệ, thời gian hoặc quyền truy cập khiến kiểm thử thiếu giá trị.
- **Nhầm trạng thái với sự kiện:** PAID là trạng thái; PaymentSucceeded là sự kiện có thể làm trạng thái thay đổi. Phân biệt rõ giúp thiết kế test case chính xác.
- **Chỉ kiểm tra trạng thái cuối:** một quy trình có thể kết thúc đúng nhưng tạo sự kiện trùng hoặc trạng thái trung gian sai. Kiểm tra các bước quan trọng và tác động phụ.
- **Chỉ kiểm tra chuyển trạng thái hợp lệ:** cần xác minh cả sự kiện không được phép, quyền không hợp lệ và thứ tự sai.
- **Không kiểm tra guard ở hai phía:** kiểm tra điều kiện đúng mà bỏ qua điều kiện sai hoặc sát ngưỡng sẽ bỏ sót lỗi quyết định.
- **Bỏ qua vòng lặp và timeout:** thử lại vô hạn, callback lặp hoặc chờ không kết thúc có thể gây lỗi nghiêm trọng.
- **Tin mô hình mà không xác nhận:** mô hình sai sẽ tạo ra expected result sai. Cần người có thẩm quyền và nguồn yêu cầu xác nhận.
- **Theo đuổi bao phủ đường đi tuyệt đối:** số đường đi có thể tăng không giới hạn khi có vòng lặp. Chọn mục tiêu theo rủi ro và tiêu chí có thể đo.
- **Không cập nhật mô hình:** mô hình cũ khiến test case xác nhận hành vi đã hết hiệu lực. Gắn cập nhật mô hình với quản lý thay đổi.

## 11. Checklist trước khi sử dụng mô hình

- [ ] Mục tiêu, đối tượng và ranh giới kiểm thử đã rõ.
- [ ] Mô hình dựa trên yêu cầu hoặc quy tắc có nguồn và phiên bản xác định.
- [ ] Trạng thái, sự kiện, guard, hành động và điểm kết thúc được định nghĩa rõ khi dùng state machine.
- [ ] Các điều kiện và kết quả trong bảng quyết định không mơ hồ.
- [ ] Luồng có nhánh lỗi, vòng lặp, timeout và bước bù trừ phù hợp với rủi ro.
- [ ] Các trạng thái hoặc nhánh không thể đạt đến đã được xem xét.
- [ ] Có nguồn xác nhận expected result và người chịu trách nhiệm phê duyệt.
- [ ] Tiêu chí bao phủ phù hợp với rủi ro và có thể đo được.
- [ ] Dữ liệu và môi trường cho phép tái lập chuỗi kiểm thử.
- [ ] Có kiểm tra bất biến, tác động phụ và sự kiện lặp khi phù hợp.
- [ ] Mô hình, test case và oracle được cập nhật khi yêu cầu thay đổi.

## 12. Mối liên hệ giữa mô hình và bằng chứng kiểm thử

Quy trình có thể được tóm tắt như sau:

~~~mermaid
flowchart TD
    A["Yêu cầu, rủi ro và quy tắc đã xác nhận"]
    B["Chọn mô hình<br/>Trạng thái, quy tắc hoặc luồng"]
    C["Rà soát mô hình và nguồn xác nhận"]
    D["Chọn tiêu chí bao phủ"]
    E["Thiết kế chuỗi kiểm thử và dữ liệu"]
    F["Thực thi trên hệ thống"]
    G["So sánh kết quả với oracle"]
    H{"Đạt và đủ bằng chứng?"}
    I["Ghi nhận lỗi hoặc khoảng trống mô hình"]
    J["Cập nhật mô hình, test case và phạm vi"]
    B --> C --> D --> E --> F --> G --> H
    A --> B
    H -->|Có| J
    H -->|Không| I --> J
    J -. "Thay đổi tiếp theo" .-> B
~~~

Kiểm thử dựa trên mô hình giúp nhóm chuyển một mô tả nghiệp vụ phức tạp thành những điều kiện có thể kiểm tra và đo lường. Khi mô hình đúng, có nguồn xác nhận rõ và được duy trì cùng sản phẩm, nhóm dễ nhận ra trạng thái bị bỏ sót, tổ hợp quy tắc sai và nhánh quy trình chưa được xác minh. Kết quả kiểm thử khi đó phản ánh được cả hành vi cục bộ lẫn cách các phần phối hợp trong toàn bộ luồng.
