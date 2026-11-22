# Điểm mở rộng trong kiến trúc DSL

Một ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường bắt đầu với một tập cú pháp và quy tắc đủ để giải quyết một nhóm bài toán cụ thể. Khi hệ thống được sử dụng rộng hơn, nhu cầu mới sẽ xuất hiện: miền cần thêm thuật ngữ, người dùng muốn định nghĩa hàm riêng, ứng dụng cần chạy DSL trên một nền tảng khác hoặc một nhóm khác muốn tích hợp dữ liệu của họ.

Nếu mọi thay đổi đều buộc nhóm phát triển sửa trực tiếp lõi ngôn ngữ, kiểm thử lại toàn bộ hệ thống và phát hành một phiên bản mới, chi phí tiến hóa DSL sẽ tăng nhanh. Kiến trúc DSL vì vậy cần xác định những vị trí có thể bổ sung hành vi một cách có kiểm soát. Những vị trí hoặc hợp đồng được thiết kế để tiếp nhận phần mở rộng được gọi là **điểm mở rộng** (*extension point*).

Điểm mở rộng giúp DSL thích nghi với nhiều nhu cầu mà vẫn giữ được cấu trúc và ngữ nghĩa cốt lõi ổn định. Tuy nhiên, càng mở rộng tùy ý thì ngôn ngữ càng khó dự đoán, kiểm thử và bảo mật. Thiết kế tốt cần xác định rõ phần nào được phép thay đổi, ai có thể mở rộng, phần mở rộng được đăng ký và thực thi ra sao, cũng như cách quản lý tương thích giữa các phiên bản.

## 1. Điểm mở rộng là gì?

### 1.1. Khái niệm

Điểm mở rộng là một vị trí trong kiến trúc hoặc một giao diện được công bố để thành phần khác có thể bổ sung chức năng mà không phải thay đổi trực tiếp phần lõi chịu trách nhiệm điều phối.

Ví dụ, một DSL tính giá có thể cung cấp các hàm tích hợp như **min**, **max** và **round**. Khi một miền cần thêm hàm **customerDiscount**, kiến trúc có thể cho phép đăng ký hàm mới thông qua một API. Bộ phân tích và bộ thực thi vẫn giữ vai trò của chúng; hàm mới được gọi thông qua hợp đồng mà DSL đã định nghĩa.

Một điểm mở rộng thường có:

- **Hợp đồng:** mô tả thành phần mở rộng phải cung cấp những gì.
- **Vị trí tích hợp:** xác định thành phần được gọi ở giai đoạn nào của vòng đời DSL.
- **Cơ chế đăng ký:** cho biết cách hệ thống phát hiện và đưa phần mở rộng vào sử dụng.
- **Quy tắc thực thi:** xác định thứ tự, phạm vi, quyền và cách xử lý lỗi.
- **Quy tắc tương thích:** mô tả cách phần mở rộng hoạt động qua các phiên bản.

Điểm mở rộng có thể là một API, một interface, một registry, một hook trong pipeline, một tập hàm có thể đăng ký hoặc một định dạng plugin. Không phải điểm mở rộng nào cũng cần cơ chế plugin động.

### 1.2. Phân biệt điểm mở rộng và phần mở rộng

Hai khái niệm có quan hệ nhưng khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Điểm mở rộng (*extension point*) | Vị trí hoặc hợp đồng mà kiến trúc cho phép bổ sung hành vi | Interface FunctionProvider |
| Phần mở rộng (*extension*) | Thành phần cụ thể triển khai hợp đồng đó | Hàm customerDiscount do module bán hàng cung cấp |
| Cơ chế mở rộng (*extension mechanism*) | Cách đăng ký, nạp, phân quyền và gọi phần mở rộng | Registry, dependency injection hoặc plugin loader |

Ví dụ, một hệ thống có thể công bố interface FunctionProvider làm điểm mở rộng. Một module triển khai interface này để cung cấp hàm mới. Registry là cơ chế tìm và đăng ký các module. Ba thành phần phối hợp với nhau nhưng không nên được gọi thay thế cho nhau.

### 1.3. Vì sao cần thiết kế điểm mở rộng?

Điểm mở rộng có ích khi:

- Nhiều nhóm cần bổ sung chức năng cho cùng một DSL.
- Các ứng dụng khác nhau cần dùng chung lõi ngôn ngữ nhưng có tập hàm hoặc dữ liệu riêng.
- Một DSL cần hỗ trợ nhiều backend hoặc môi trường thực thi.
- Quy tắc miền thay đổi thường xuyên và cần tách khỏi phần lõi.
- Tổ chức muốn phát triển module độc lập mà không sửa mã nguồn trung tâm.

Nếu DSL chỉ có một người dùng, phạm vi nhỏ và ít thay đổi, một tập chức năng cố định có thể đơn giản hơn. Điểm mở rộng chỉ đáng đầu tư khi nhu cầu đa dạng hoặc vòng đời phát triển tạo ra lợi ích thực tế.

## 2. Kiến trúc DSL và những vị trí có thể mở rộng

Một kiến trúc DSL điển hình có thể được chia thành các giai đoạn:

1. Nhận văn bản hoặc định nghĩa DSL.
2. Phân tích từ vựng và cú pháp.
3. Xây dựng cây cú pháp trừu tượng (AST).
4. Kiểm tra ngữ nghĩa, kiểu và tham chiếu.
5. Chuyển đổi sang biểu diễn trung gian (IR), nếu có.
6. Tối ưu hoặc biến đổi mô hình.
7. Sinh mã hoặc thực thi.
8. Thu thập kết quả, chẩn đoán và theo dõi.

Các giai đoạn này tạo ra nhiều vị trí có thể tiếp nhận phần mở rộng. Không nhất thiết phải mở tất cả các vị trí. Mỗi điểm mở rộng nên giải quyết một nhu cầu cụ thể và có ranh giới trách nhiệm rõ ràng.

~~~mermaid
flowchart TD
    A["Nguồn DSL"] --> B["Lexer và Parser"]
    B --> C["AST"]
    C --> D["Kiểm tra ngữ nghĩa và kiểu"]
    D --> E["Biểu diễn trung gian (IR)"]
    E --> F["Tối ưu và biến đổi"]
    F --> G["Backend hoặc Runtime"]
    G --> H["Kết quả"]
    X1["Bổ sung cú pháp"] -.-> B
    X2["Kiểu và hàm miền"] -.-> D
    X3["Pass biến đổi"] -.-> F
    X4["Backend / Adapter"] -.-> G
    X5["Công cụ và chẩn đoán"] -.-> C
    X5 -.-> H
~~~

Sơ đồ cho thấy điểm mở rộng có thể nằm ở nhiều giai đoạn. Mỗi điểm nên tác động vào đúng phần mà nó chịu trách nhiệm, tránh để plugin tự ý thay đổi trạng thái nội bộ của toàn bộ pipeline.

## 3. Các nhóm điểm mở rộng thường gặp

### 3.1. Mở rộng từ vựng và cú pháp

Điểm mở rộng cú pháp cho phép DSL nhận thêm từ khóa, cấu trúc câu lệnh hoặc dạng biểu thức.

Ví dụ, một DSL quy tắc ban đầu chỉ hỗ trợ:

~~~text
rule HighValueOrder {
    when order.total > 1000000
    then order.markForReview()
}
~~~

Sau này, người dùng muốn có cấu trúc **within** để diễn đạt điều kiện thời gian:

~~~text
rule RecentCustomer {
    when customer.lastOrderDate within last 30 days
    then customer.applyLoyaltyBenefit()
}
~~~

Để hỗ trợ cú pháp mới, kiến trúc có thể cung cấp grammar module, parser extension hoặc một cơ chế macro. Cần xác định rõ:

- Cú pháp mới có thể dùng từ khóa nào?
- Có thể xung đột với từ khóa hoặc tên định danh hiện có không?
- Quy tắc ưu tiên toán tử và cách phân tích có thay đổi không?
- Cú pháp mới có được phép lồng với cấu trúc cũ không?
- Lỗi cú pháp được chỉ vị trí và giải thích như thế nào?

Mở rộng grammar có sức mạnh lớn nhưng cũng có rủi ro cao. Hai plugin cùng thêm một cấu trúc hoặc dùng cùng một từ khóa có thể khiến parser không biết cách diễn giải. Vì vậy, nhiều DSL chọn cú pháp lõi ổn định và cho phép mở rộng bằng hàm, toán tử đã đăng ký hoặc cấu trúc dữ liệu, thay vì cho plugin tùy ý sửa grammar.

Một lựa chọn khác là macro hoặc cú pháp mở rộng được khai báo trong một namespace. Macro thường biến đổi cú pháp trước khi kiểm tra ngữ nghĩa; do đó cần giới hạn khả năng biến đổi và cung cấp thông tin vị trí nguồn để thông báo lỗi vẫn trỏ về nội dung mà người dùng đã viết.

### 3.2. Mở rộng hàm và toán tử tích hợp

Đây là điểm mở rộng phổ biến vì DSL có thể giữ nguyên grammar trong khi tăng khả năng diễn đạt.

Ví dụ, DSL tính giá có thể cho phép đăng ký:

- Hàm miền: **customerTier(customer)**.
- Hàm xử lý chuỗi: **normalizeCode(value)**.
- Hàm ngày giờ: **businessDaysBetween(start, end)**.
- Hàm số học chuyên biệt: **taxAmount(netPrice, region)**.

Hàm mở rộng cần khai báo tên, số lượng và kiểu tham số, kiểu kết quả, quy tắc xử lý giá trị rỗng, tác động phụ nếu có và yêu cầu quyền.

Một mô tả hàm có thể có dạng:

~~~text
function taxAmount(
    netPrice: Money,
    region: Region
): Money
~~~

Khi kiểm tra ngữ nghĩa, DSL có thể xác nhận số lượng tham số và kiểu dữ liệu trước khi chạy. Nếu hàm chỉ được đăng ký ở runtime mà không có thông tin kiểu, nhiều lỗi sẽ chỉ xuất hiện khi biểu thức được thực thi.

Toán tử mới cũng có thể được đăng ký, nhưng cần xác định độ ưu tiên, tính kết hợp, kiểu toán hạng và cách hiển thị trong AST. Không nên cho phép nhiều plugin tự định nghĩa cùng một ký hiệu với ngữ nghĩa khác nhau.

### 3.3. Mở rộng kiểu dữ liệu và mô hình miền

DSL có thể cho phép ứng dụng cung cấp kiểu miền mới, chẳng hạn:

- Money cho giá trị tiền tệ.
- Distance cho khoảng cách.
- Customer cho khách hàng.
- GeoPoint cho tọa độ.
- BusinessCalendar cho lịch làm việc.

Kiểu dữ liệu mới cần mô tả cách tạo giá trị, so sánh, chuyển đổi, kiểm tra hợp lệ và cách hiển thị trong thông báo lỗi. Nếu DSL hỗ trợ toán tử, cần xác định phép toán nào hợp lệ trên kiểu đó.

Ví dụ, phép cộng hai giá trị Money cần kiểm tra cùng đơn vị tiền tệ. Phép so sánh Distance có thể yêu cầu chuẩn hóa đơn vị. Nếu kiểu dữ liệu chỉ được khai báo tên mà không có ngữ nghĩa rõ, DSL có thể chấp nhận biểu thức không có ý nghĩa trong miền.

Điểm mở rộng kiểu cũng có thể cho phép đăng ký schema hoặc kiểu đối tượng mà DSL được phép truy cập. Đây là cách giới hạn bề mặt dữ liệu: biểu thức chỉ nhìn thấy những thuộc tính đã được công bố, thay vì truy cập mọi trường nội bộ của ứng dụng.

### 3.4. Mở rộng kiểm tra ngữ nghĩa và quy tắc xác thực

Sau khi parser tạo AST, DSL thường cần kiểm tra những điều mà cú pháp không thể xác định:

- Tên biến hoặc thuộc tính có tồn tại không?
- Hàm có được gọi với đúng kiểu tham số không?
- Một thao tác có hợp lệ trong ngữ cảnh hiện tại không?
- Người dùng có quyền tham chiếu đến dữ liệu đó không?
- Hai quy tắc có mâu thuẫn theo một tập điều kiện đã biết không?

Kiến trúc có thể cung cấp validator API để module đăng ký các kiểm tra bổ sung. Ví dụ, một module tài chính có thể kiểm tra rằng biểu thức không so sánh tiền tệ khác nhau; module quản lý đơn hàng có thể cấm gọi thao tác giao hàng khi trạng thái chưa phù hợp.

Validator nên nhận một mô hình đã được phân tích và trả về danh sách chẩn đoán. Nó cần có quyền đọc rõ ràng và chỉ được sửa mô hình nếu hợp đồng cho phép. Một validator tùy tiện thay đổi AST có thể khiến kết quả phụ thuộc vào thứ tự chạy.

### 3.5. Mở rộng pipeline bằng các pass biến đổi

Một số DSL chuyển AST sang biểu diễn trung gian (IR) trước khi sinh mã hoặc thực thi. IR tạo ra một ranh giới ổn định để thêm các bước phân tích và biến đổi.

Một pass có thể:

- Chuẩn hóa biểu thức.
- Thay lời gọi hàm miền bằng thao tác chuẩn.
- Tối ưu điều kiện không đổi.
- Bổ sung metadata cho truy vết.
- Chuyển mô hình cấp cao thành mô hình phù hợp với backend.

Ví dụ, biểu thức:

~~~text
order.total > 1000000 && order.status == PAID
~~~

có thể được chuẩn hóa thành một cây biểu thức có kiểu rõ ràng trước khi backend chuyển thành truy vấn hoặc mã thực thi.

Pass cần khai báo đầu vào, đầu ra, điều kiện áp dụng và thứ tự tương thích. Nếu hai pass cùng sửa một node hoặc phụ thuộc vào kết quả của nhau, pipeline phải quy định thứ tự. Không nên để thứ tự nạp plugin ngẫu nhiên quyết định ngữ nghĩa của chương trình.

### 3.6. Mở rộng backend và mục tiêu sinh mã

Một DSL có thể cần chạy trên nhiều nền tảng:

- Sinh Java source code.
- Sinh SQL cho nhiều hệ quản trị cơ sở dữ liệu.
- Sinh cấu hình cho một hệ thống workflow.
- Biên dịch thành bytecode hoặc một định dạng trung gian.
- Thực thi trực tiếp bằng interpreter.

Backend là điểm mở rộng tự nhiên nếu DSL có IR đủ ổn định. Backend nhận mô hình đã được kiểm tra và tạo ra đầu ra cho một môi trường cụ thể.

Ví dụ, cùng một biểu thức lọc khách hàng có thể được chuyển thành SQL khi chạy trên cơ sở dữ liệu hoặc thành Java predicate khi xử lý trong bộ nhớ.

~~~text
DSL source
    |
    v
AST -> Semantic Analysis -> IR
                         /    \
                        v      v
                 SQL Backend  JVM Backend
                        |      |
                        v      v
                    SQL Query Java Code
~~~

Backend cần bảo toàn ngữ nghĩa. Nếu một phép so sánh trong DSL xử lý giá trị null theo một quy tắc cụ thể, mọi backend phải thực hiện tương đương hoặc công bố giới hạn. Nếu không, cùng một DSL có thể cho kết quả khác nhau tùy nơi chạy.

### 3.7. Mở rộng runtime và adapter

Với DSL được diễn giải khi chạy, runtime có thể cung cấp điểm mở rộng cho:

- Resolver để tìm dữ liệu hoặc biến.
- Function dispatcher để gọi hàm miền.
- Adapter truy cập hệ thống bên ngoài.
- Clock hoặc nguồn thời gian có thể thay thế khi kiểm thử.
- Cơ chế ghi log, tracing và metrics.
- Bộ giới hạn thời gian, bộ nhớ hoặc số bước thực thi.

Adapter giúp tách DSL khỏi chi tiết của dịch vụ cụ thể. Ví dụ, DSL có thể yêu cầu **customer.creditScore()** thông qua một interface; ứng dụng cung cấp adapter lấy dữ liệu từ hệ thống tín dụng đang sử dụng.

Runtime nên kiểm soát thời điểm và quyền gọi adapter. Một biểu thức không nên tự động có quyền truy cập mạng, đọc tệp hoặc ghi dữ liệu chỉ vì một plugin đã đăng ký.

### 3.8. Mở rộng công cụ phát triển

DSL có thể công bố metadata để IDE hoặc công cụ bên ngoài cung cấp:

- Tô màu cú pháp.
- Hoàn thành từ khóa, hàm và thuộc tính.
- Điều hướng đến định nghĩa.
- Kiểm tra lỗi ngay khi soạn.
- Định dạng tự động.
- Tạo tài liệu và sơ đồ.
- Gỡ lỗi hoặc xem giá trị biểu thức.

Một registry hàm có thể là nguồn thông tin chung cho parser, validator, runtime và IDE. Khi hàm **taxAmount** được đăng ký, công cụ biên tập có thể hiển thị chữ ký và mô tả của hàm đó.

Nếu metadata của công cụ khác với hợp đồng runtime, người dùng có thể thấy gợi ý một hàm nhưng khi chạy lại báo không tồn tại. Vì vậy, metadata nên được phát sinh hoặc đọc từ cùng một nguồn định nghĩa.

### 3.9. Mở rộng tích hợp dữ liệu và dịch vụ

Nhiều DSL cần làm việc với dữ liệu thuộc các hệ thống khác. Điểm mở rộng có thể cho phép đăng ký:

- Nguồn dữ liệu.
- Schema hoặc catalog.
- Bộ phân giải tên.
- Adapter giao thức.
- Bộ chuyển đổi định dạng.
- Cơ chế xác thực hoặc phân quyền.

Ví dụ, DSL truy vấn có thể hỗ trợ thêm nguồn dữ liệu **warehouse** thông qua một adapter. Người viết biểu thức chỉ biết tên nguồn và schema đã công bố, còn adapter chịu trách nhiệm kết nối đến hệ thống thực tế.

Việc tích hợp cần xác định timeout, lỗi kết nối, giới hạn truy vấn, phân trang, kiểu dữ liệu và quyền truy cập. Không nên để DSL che giấu các giới hạn vận hành có thể ảnh hưởng lớn đến hệ thống.

## 4. Thiết kế hợp đồng cho điểm mở rộng

### 4.1. Hợp đồng phải nhỏ và có mục đích

Một interface mở rộng nên mô tả đúng trách nhiệm cần bổ sung. Ví dụ, provider hàm không cần được quyền truy cập parser, backend hay cấu hình bảo mật.

Hợp đồng nhỏ giúp:

- Thành phần mở rộng dễ triển khai.
- Lõi DSL ít phụ thuộc vào chi tiết module.
- Kiểm thử độc lập dễ hơn.
- Có thể thay thế hoặc nâng cấp module mà không ảnh hưởng phần khác.

Tránh tạo một interface tổng quát với hàng chục phương thức mà mọi plugin đều phải triển khai dù chỉ cần một phần nhỏ.

### 4.2. Công bố dữ liệu đầu vào và đầu ra

Mỗi extension point cần định nghĩa:

- Kiểu dữ liệu đầu vào.
- Kiểu dữ liệu kết quả.
- Dữ liệu có thể thay đổi hay chỉ đọc.
- Có thể trả về nhiều kết quả không.
- Cách biểu diễn lỗi và cảnh báo.
- Quy tắc về null, thời gian và tài nguyên.

Ví dụ, một validator nên nhận AST hoặc node có kiểu xác định và trả về các diagnostic có mã, mức độ, vị trí nguồn cùng thông điệp. Nếu validator chỉ ném một exception chung chung, công cụ phía trên khó tổng hợp và hiển thị lỗi nhất quán.

### 4.3. Tránh phụ thuộc vào lớp nội bộ

Nếu plugin phải truy cập trực tiếp các lớp parser nội bộ hoặc cấu trúc AST chưa được công bố, mỗi lần lõi DSL refactor đều có thể làm plugin hỏng.

Nên công bố API ổn định ở ranh giới:

- Interface hoặc kiểu dữ liệu công khai.
- Factory tạo đối tượng mở rộng.
- Registry hoặc context chỉ cung cấp quyền cần thiết.
- Phiên bản API mà plugin phải tương thích.

Các lớp nội bộ vẫn có thể thay đổi khi không nằm trong hợp đồng công khai.

### 4.4. Xác định quyền sở hữu và vòng đời

Hợp đồng cần cho biết ai tạo, ai đóng và ai chịu trách nhiệm tài nguyên của phần mở rộng.

Ví dụ, một plugin có thể mở kết nối đến hệ thống bên ngoài khi được khởi tạo. Kiến trúc cần quy định khi nào gọi initialize, khi nào ngừng nhận yêu cầu và khi nào gọi close.

Không nên để nhiều thành phần cùng đóng một tài nguyên mà không có quy tắc sở hữu. Với đối tượng dùng chung, cần xác định rõ vòng đời theo ứng dụng, phiên DSL hay một lần thực thi.

### 4.5. Định danh và namespace

Tên hàm, kiểu dữ liệu, toán tử và plugin có thể xung đột. Có thể dùng namespace hoặc định danh đầy đủ:

~~~text
sales.customerDiscount(customer)
finance.taxAmount(amount, region)
shipping.estimatedDays(destination)
~~~

Namespace giúp tránh va chạm và làm rõ nguồn gốc chức năng. Cần quy định cách import, alias, độ ưu tiên khi tên trùng và cách báo lỗi khi tham chiếu mơ hồ.

## 5. Cơ chế đăng ký và nạp phần mở rộng

### 5.1. Đăng ký tĩnh

Với ứng dụng nhỏ, các phần mở rộng có thể được đăng ký trực tiếp khi khởi tạo DSL:

~~~java
DslEngine engine = DslEngine.builder()
    .registerFunction(new TaxAmountFunction())
    .registerType(new MoneyTypeProvider())
    .registerValidator(new OrderRuleValidator())
    .build();
~~~

Ưu điểm:

- Cấu hình rõ ràng tại thời điểm biên dịch hoặc khởi tạo.
- Dễ tìm nơi đăng ký.
- Dễ kiểm soát tập chức năng được bật.
- Không cần plugin loader phức tạp.

Hạn chế là ứng dụng phải biết và liên kết trực tiếp đến các module cần dùng. Nếu có nhiều sản phẩm hoặc module tùy chọn, danh sách đăng ký có thể tăng.

### 5.2. Dependency injection

Trong ứng dụng sử dụng dependency injection, các extension provider có thể được đăng ký như bean hoặc service. Lõi DSL nhận danh sách các provider qua constructor hoặc registry.

Cách này tận dụng vòng đời và cấu hình của framework. Tuy nhiên, cần tránh để lõi DSL phụ thuộc trực tiếp vào container cụ thể. Nên giữ API độc lập, còn adapter của framework chịu trách nhiệm chuyển bean thành extension provider.

### 5.3. Plugin discovery

Với hệ thống cần nạp module độc lập, có thể dùng cơ chế phát hiện plugin thông qua metadata, service loader hoặc thư mục module.

Một manifest plugin có thể mô tả:

~~~yaml
id: sales-functions
version: 2.1.0
extensionApi: 1
provides:
  - functions
  - types
requires:
  - dsl-core: ">=3.0 <4.0"
~~~

Đây là định dạng minh họa. Một hệ thống thực tế cần quy định schema, chữ ký hoặc nguồn tin cậy của manifest, cách giải quyết phụ thuộc và chính sách khi có plugin không tương thích.

Plugin discovery cần trả lời:

- Tìm plugin ở đâu?
- Ai được phép cài đặt hoặc bật plugin?
- Có kiểm tra chữ ký hoặc nguồn phát hành không?
- Xử lý plugin trùng ID như thế nào?
- Nếu một plugin không khởi tạo được, ứng dụng có tiếp tục chạy không?
- Có thể gỡ hoặc thay thế plugin khi hệ thống đang hoạt động không?

### 5.4. Registry và tra cứu

Registry là nơi quản lý các extension đã đăng ký. Ví dụ, FunctionRegistry ánh xạ tên hàm và chữ ký đến provider tương ứng.

Một registry nên hỗ trợ:

- Đăng ký và kiểm tra xung đột.
- Tra cứu theo tên và kiểu.
- Liệt kê metadata để phục vụ công cụ.
- Xác định nguồn cung cấp chức năng.
- Đóng băng cấu hình sau khi engine khởi tạo nếu runtime yêu cầu tính ổn định.

Nếu registry cho phép thay đổi trong lúc thực thi, cần quy định cách đồng bộ và ảnh hưởng đến các chương trình DSL đã biên dịch. Trong nhiều hệ thống, tạo một registry bất biến cho mỗi phiên engine sẽ dễ dự đoán hơn.

## 6. Ví dụ xây dựng điểm mở rộng cho hàm DSL trong Java

Giả sử DSL có thể gọi hàm miền. Ta muốn ứng dụng đăng ký các hàm khác nhau mà không sửa interpreter.

### 6.1. Khai báo hợp đồng

Có thể định nghĩa interface:

~~~java
public interface DslFunction {
    String name();

    List<ValueType> parameterTypes();

    ValueType returnType();

    DslValue invoke(List<DslValue> arguments, EvaluationContext context);
}
~~~

DslFunction mô tả tên hàm, kiểu tham số, kiểu kết quả và hành vi thực thi. EvaluationContext cung cấp dữ liệu hoặc quyền đã được cấp cho lần đánh giá hiện tại.

Trong hệ thống thực tế, hợp đồng có thể cần thêm mô tả, phiên bản, chính sách tác động phụ, timeout hoặc cơ chế hủy thực thi. Chỉ nên thêm những thành phần cần thiết và có ngữ nghĩa rõ.

### 6.2. Triển khai một hàm

Ví dụ hàm tính thuế minh họa:

~~~java
public final class TaxAmountFunction implements DslFunction {
    @Override
    public String name() {
        return "taxAmount";
    }

    @Override
    public List<ValueType> parameterTypes() {
        return List.of(ValueType.MONEY, ValueType.DECIMAL);
    }

    @Override
    public ValueType returnType() {
        return ValueType.MONEY;
    }

    @Override
    public DslValue invoke(
            List<DslValue> arguments,
            EvaluationContext context) {
        Money netPrice = arguments.get(0).asMoney();
        BigDecimal rate = arguments.get(1).asDecimal();
        return DslValue.money(netPrice.multiply(rate));
    }
}
~~~

Đây là ví dụ minh họa giao diện. Một triển khai hoàn chỉnh cần kiểm tra số lượng đối số, đơn vị tiền tệ, độ chính xác, làm tròn và giới hạn giá trị theo quy tắc miền.

### 6.3. Đăng ký và gọi hàm

Ứng dụng đăng ký provider:

~~~java
FunctionRegistry functions = new FunctionRegistry();
functions.register(new TaxAmountFunction());

DslEngine engine = DslEngine.builder()
    .functionRegistry(functions)
    .build();
~~~

Người dùng DSL có thể viết:

~~~text
let tax = taxAmount(order.netPrice, 0.10)
~~~

Trong quá trình kiểm tra ngữ nghĩa, engine tìm chữ ký taxAmount, xác thực kiểu của các đối số và kiểu kết quả. Khi thực thi, runtime gọi provider đã đăng ký với context phù hợp.

Điểm quan trọng là parser không cần biết cách tính thuế. Parser chỉ phân tích lời gọi hàm thành node trong AST; semantic analyzer kiểm tra chữ ký; runtime điều phối lời gọi qua registry.

### 6.4. Tách metadata khỏi hành vi

IDE hoặc tài liệu có thể cần mô tả hàm mà không thực thi nó. Vì vậy, trong thiết kế lớn hơn, metadata có thể được tách thành một descriptor:

~~~java
public record FunctionDescriptor(
    String qualifiedName,
    List<ValueType> parameterTypes,
    ValueType returnType,
    String description
) {}
~~~

Provider cung cấp descriptor và implementation. Công cụ biên tập đọc descriptor để hiển thị gợi ý; runtime sử dụng implementation để đánh giá.

Việc tách này giúp các công cụ không cần khởi chạy hành vi nghiệp vụ chỉ để khám phá chữ ký hàm.

## 7. Quản lý thứ tự và xung đột giữa các phần mở rộng

### 7.1. Xung đột tên

Hai plugin có thể cùng đăng ký hàm discount. Nếu registry tự chọn plugin được nạp sau cùng, kết quả có thể thay đổi theo thứ tự khởi động.

Các cách xử lý thường gặp:

- Từ chối đăng ký trùng tên.
- Bắt buộc dùng namespace.
- Cho phép alias rõ ràng trong cấu hình.
- Chỉ định provider ưu tiên một cách tường minh.

Với chức năng ảnh hưởng đến kết quả nghiệp vụ, từ chối xung đột và yêu cầu định danh đầy đủ thường an toàn hơn.

### 7.2. Thứ tự pipeline

Các pass biến đổi có thể phụ thuộc nhau. Ví dụ, pass A bổ sung metadata mà pass B cần đọc. Pipeline phải khai báo quan hệ phụ thuộc hoặc thứ tự cố định.

Không nên dùng thứ tự quét thư mục hay thứ tự trả về của hệ điều hành làm thứ tự thực thi. Thứ tự phải là một phần của cấu hình hoặc hợp đồng.

Nếu có vòng phụ thuộc giữa các pass, engine nên báo lỗi cấu hình trước khi xử lý chương trình DSL.

### 7.3. Chính sách khi plugin lỗi

Một plugin có thể lỗi khi khởi tạo, kiểm tra hoặc thực thi. Cần phân loại:

- Lỗi cấu hình khiến engine không thể khởi động.
- Lỗi trong một chương trình DSL cụ thể.
- Lỗi tạm thời của dịch vụ mà plugin gọi.
- Lỗi nội bộ của plugin.

Hệ thống nên ghi nhận plugin ID, giai đoạn, vị trí nguồn nếu có và mã lỗi. Không nên để một exception nội bộ làm lộ thông tin nhạy cảm hoặc khiến toàn bộ tiến trình kết thúc ngoài ý muốn.

Tùy mức độ quan trọng, ứng dụng có thể từ chối khởi động, vô hiệu hóa module không bắt buộc hoặc trả lỗi cho lần thực thi hiện tại. Chính sách này phải được công bố để người vận hành biết hành vi khi xảy ra sự cố.

## 8. Tương thích và quản lý phiên bản

### 8.1. Phiên bản API mở rộng

Khi hợp đồng extension thay đổi, plugin đã biên dịch có thể không còn tương thích. Có thể công bố phiên bản API riêng với phiên bản sản phẩm:

- Phiên bản DSL: ngữ nghĩa và cú pháp mà người dùng viết.
- Phiên bản extension API: hợp đồng dành cho module mở rộng.
- Phiên bản plugin: phiên bản triển khai cụ thể.
- Phiên bản runtime: môi trường thực thi plugin.

Các phiên bản này có liên quan nhưng không nhất thiết phải tăng cùng nhau.

### 8.2. Thay đổi tương thích và không tương thích

Ví dụ thay đổi thường tương thích:

- Bổ sung một phương thức mặc định không bắt buộc vào interface nếu nền tảng hỗ trợ phù hợp.
- Thêm metadata tùy chọn.
- Bổ sung một hàm mới không xung đột tên.

Ví dụ thay đổi có thể phá vỡ tương thích:

- Đổi chữ ký phương thức bắt buộc.
- Thay đổi ý nghĩa của kiểu dữ liệu.
- Đổi quy tắc xử lý null.
- Thay đổi thứ tự pass khiến kết quả biến đổi khác.
- Đổi cách xử lý exception hoặc quyền gọi.

Không nên đánh giá tương thích chỉ bằng khả năng biên dịch. Plugin có thể vẫn biên dịch nhưng cho kết quả khác do ngữ nghĩa đã thay đổi.

### 8.3. Quy tắc deprecation

Khi cần thay thế một extension point, nên có giai đoạn chuyển tiếp:

1. Công bố API mới.
2. Đánh dấu API cũ là deprecated.
3. Cung cấp hướng dẫn chuyển đổi và ví dụ.
4. Có cảnh báo khi plugin cũ được nạp.
5. Chỉ loại bỏ API sau mốc phiên bản đã công bố.

Với DSL có nội dung được lưu lâu dài, cần cân nhắc cả khả năng đọc chương trình cũ. Có thể cần parser tương thích hoặc công cụ migration để chuyển đổi nội dung sang cú pháp mới.

### 8.4. Kiểm tra tương thích khi nạp plugin

Manifest plugin nên khai báo khoảng phiên bản API được hỗ trợ. Loader cần xác thực trước khi khởi tạo plugin.

Nếu plugin yêu cầu API không tương thích, engine nên báo rõ plugin nào, yêu cầu phiên bản nào và phiên bản hiện tại là bao nhiêu. Không nên âm thầm bỏ qua plugin vì điều đó có thể làm DSL chạy thiếu chức năng mà người dùng tưởng rằng đã bật.

## 9. Bảo mật và độ tin cậy của điểm mở rộng

Phần mở rộng có thể chạy mã trong tiến trình ứng dụng hoặc truy cập dữ liệu mà DSL xử lý. Vì vậy, plugin là một ranh giới tin cậy quan trọng.

### 9.1. Không mặc định plugin là đáng tin cậy

Plugin bên thứ ba hoặc module do nhóm khác cung cấp có thể chứa lỗi, hành vi ngoài dự kiến hoặc mã độc. Chỉ nạp module từ nguồn đã được tổ chức cho phép.

Các biện pháp có thể gồm:

- Kiểm tra nguồn phát hành và chữ ký artifact.
- Kiểm soát quyền cài đặt và bật plugin.
- Ghi nhận phiên bản và checksum của module.
- Rà soát dependency và lỗ hổng đã biết.
- Tách tiến trình nếu plugin cần mức cô lập cao.

### 9.2. Cấp quyền theo nguyên tắc tối thiểu

Không nên truyền toàn bộ application context cho mọi plugin. Một hàm chỉ cần đọc tỷ lệ thuế không nên được cấp quyền gửi email, truy cập tệp hoặc ghi cơ sở dữ liệu.

Có thể cung cấp capability cụ thể:

- Quyền đọc một tập dữ liệu.
- Quyền gọi một adapter đã được cấu hình.
- Quyền phát một loại sự kiện.
- Hạn mức số lần gọi hoặc thời gian.

Runtime chỉ truyền các capability mà phần mở rộng thực sự cần.

### 9.3. Giới hạn tài nguyên

Một hàm mở rộng có thể chạy lâu, cấp phát nhiều bộ nhớ hoặc gọi dịch vụ liên tục. Runtime cần có giới hạn phù hợp như:

- Timeout.
- Hạn mức bộ nhớ hoặc số bước đánh giá.
- Giới hạn số lần gọi hàm.
- Giới hạn kích thước dữ liệu trả về.
- Hủy thực thi khi phiên hoặc yêu cầu đã kết thúc.

Timeout ở phía gọi không nhất thiết dừng được mã plugin đang chạy. Với plugin không tin cậy, cần cân nhắc cô lập tiến trình hoặc môi trường thực thi có khả năng cưỡng chế giới hạn.

### 9.4. Kiểm soát tác động phụ

Hàm DSL có thể được thiết kế thuần, tức cùng đầu vào cho cùng đầu ra và không làm thay đổi trạng thái bên ngoài. Những hàm thuần dễ tối ưu, kiểm thử và đánh giá hơn.

Nếu cần tác động phụ như gửi yêu cầu thanh toán hoặc cập nhật dữ liệu, phải khai báo rõ và xác định cách xử lý lỗi, retry, idempotency cùng giao dịch.

Không nên để một biểu thức trông như phép tính đơn giản nhưng âm thầm thực hiện thao tác bên ngoài. Tên hàm, metadata và quyền nên giúp người dùng nhận biết hành vi.

### 9.5. Cô lập lỗi và dữ liệu nhạy cảm

Thông báo lỗi từ plugin có thể chứa đường dẫn nội bộ, thông tin kết nối hoặc dữ liệu người dùng. Lớp runtime cần chuẩn hóa diagnostic trước khi hiển thị ra ngoài.

Log nên ghi đủ thông tin để điều tra nhưng phải tuân theo chính sách bảo vệ dữ liệu. Không ghi toàn bộ giá trị đầu vào hoặc thông tin bí mật chỉ để tiện gỡ lỗi.

## 10. Kiểm thử và quan sát phần mở rộng

### 10.1. Kiểm thử hợp đồng

Mỗi extension point nên có bộ kiểm thử hợp đồng để xác nhận:

- Provider triển khai đủ phương thức bắt buộc.
- Metadata hợp lệ.
- Kiểu đầu vào và đầu ra nhất quán.
- Lỗi được trả về theo định dạng quy định.
- Vòng đời khởi tạo và đóng tài nguyên đúng.

Kiểm thử hợp đồng giúp plugin độc lập có thể xác nhận khả năng tương thích trước khi tích hợp với ứng dụng.

### 10.2. Kiểm thử tích hợp

Kiểm thử tích hợp xác nhận phần mở rộng hoạt động đúng với parser, semantic analyzer, runtime hoặc backend thật.

Ví dụ với hàm taxAmount, cần kiểm tra:

- Hàm xuất hiện trong metadata của engine.
- Parser nhận được lời gọi hàm.
- Semantic analyzer kiểm tra đúng chữ ký.
- Runtime gọi đúng provider.
- Giá trị kết quả và lỗi làm tròn phù hợp.

### 10.3. Kiểm thử xung đột và thứ tự

Cần có trường hợp kiểm thử hai plugin đăng ký cùng tên, plugin phụ thuộc một plugin khác và hai pass có quan hệ thứ tự.

Kết quả phải ổn định giữa các lần khởi động, không phụ thuộc vào thứ tự file hoặc môi trường.

### 10.4. Kiểm thử bảo mật và giới hạn

Kiểm thử các tình huống:

- Plugin gọi capability không được cấp.
- Plugin chạy quá thời gian cho phép.
- Plugin trả về dữ liệu sai kiểu hoặc quá lớn.
- Plugin ném exception không mong đợi.
- Plugin truy cập tài nguyên đã đóng.
- Plugin gửi dữ liệu nhạy cảm vào diagnostic hoặc log.

### 10.5. Quan sát trong vận hành

Engine nên cung cấp thông tin để người vận hành biết:

- Plugin nào đã được nạp.
- Phiên bản API và phiên bản plugin.
- Extension point nào được đăng ký.
- Thời gian thực thi và tần suất gọi.
- Lỗi hoặc timeout theo plugin.
- Nguồn gốc của hàm hoặc kiểu đang được dùng.

Metadata này giúp điều tra sự cố mà không cần bật log quá chi tiết cho toàn bộ chương trình DSL.

## 11. Chọn mức độ mở rộng phù hợp

Không phải DSL nào cũng cần hệ thống plugin đầy đủ. Có thể chọn mức mở rộng tăng dần:

| Mức | Cơ chế | Phù hợp khi |
|---|---|---|
| 1 | Tập hàm và kiểu cố định | DSL nhỏ, một ứng dụng, ít thay đổi |
| 2 | API đăng ký provider lúc khởi tạo | Ứng dụng có module tùy chọn nhưng cùng vòng đời phát hành |
| 3 | Dependency injection hoặc service discovery | Nhiều module nội bộ cần đóng góp chức năng |
| 4 | Plugin có manifest và phiên bản API | Module được phát triển, phát hành tương đối độc lập |
| 5 | Plugin chạy trong tiến trình riêng hoặc sandbox | Cần cô lập mã không hoàn toàn tin cậy hoặc giới hạn tài nguyên nghiêm ngặt |

Mỗi mức cao hơn thường tăng độ linh hoạt cùng chi phí triển khai, kiểm thử, vận hành và bảo mật. Nên bắt đầu từ cơ chế đơn giản đáp ứng được nhu cầu hiện tại, đồng thời giữ hợp đồng đủ rõ để có thể phát triển sau này.

### 11.1. Câu hỏi trước khi tạo một điểm mở rộng

Trước khi công bố extension point, hãy xác định:

1. Nhu cầu nào đang lặp lại hoặc có khả năng xuất hiện ở nhiều module?
2. Phần nào của kiến trúc cần được thay đổi hoặc bổ sung?
3. Có thể đáp ứng bằng cấu hình hoặc API hiện có không?
4. Hợp đồng đầu vào, đầu ra và quyền cần thiết là gì?
5. Phần mở rộng có cần được nạp độc lập hay có thể đăng ký khi khởi tạo?
6. Có yêu cầu về thứ tự hoặc giải quyết xung đột không?
7. Ai chịu trách nhiệm tương thích và hỗ trợ plugin?
8. Hệ thống xử lý plugin lỗi hoặc không tương thích thế nào?
9. Có cần cô lập và giới hạn tài nguyên không?
10. Công cụ nào giúp kiểm thử, quan sát và gỡ lỗi?

Nếu chưa trả lời được các câu hỏi này, có thể điểm mở rộng đang được thiết kế quá sớm hoặc chưa xác định rõ trách nhiệm.

## 12. Nguyên tắc thiết kế điểm mở rộng bền vững

### 12.1. Mở đúng chỗ, không mở mọi thứ

Một lõi DSL có thể ổn định hơn nếu grammar, AST và ngữ nghĩa cơ bản được kiểm soát chặt, trong khi hàm miền, adapter và backend được mở rộng qua API. Mở toàn bộ cấu trúc nội bộ khiến mọi thay đổi trở thành rủi ro tương thích.

### 12.2. Ưu tiên hợp đồng rõ ràng

Tên phương thức và kiểu dữ liệu cần thể hiện trách nhiệm. Tránh interface chung chung như execute(Object input) nếu có thể dùng kiểu đầu vào và đầu ra cụ thể.

### 12.3. Giữ ngữ nghĩa nhất quán

Phần mở rộng không được làm cho cùng một biểu thức có nghĩa khác nhau tùy thứ tự nạp module hoặc môi trường, trừ khi sự khác biệt được cấu hình và công bố rõ ràng.

### 12.4. Làm cho lỗi có thể chẩn đoán

Diagnostic nên có mã lỗi ổn định, mức độ, vị trí nguồn, extension ID và thông tin đủ để người dùng biết cách khắc phục. Không nên phụ thuộc vào nội dung exception nội bộ làm hợp đồng công khai.

### 12.5. Quản lý vòng đời và tài nguyên

Quy định rõ thời điểm khởi tạo, sử dụng, ngừng nhận yêu cầu và đóng plugin. Các tài nguyên như kết nối, thread hoặc file handle phải có chủ sở hữu.

### 12.6. Có chính sách tương thích

Phiên bản API, phạm vi hỗ trợ và quy trình deprecation phải được công bố. Thay đổi ngữ nghĩa cần có kiểm thử hồi quy và tài liệu migration.

### 12.7. Bảo mật theo nguyên tắc tối thiểu

Chỉ cấp dữ liệu và capability cần thiết. Giới hạn tài nguyên và cô lập phần mở rộng khi mức độ tin cậy yêu cầu.

### 12.8. Tài liệu hóa bằng ví dụ chạy được

Mỗi điểm mở rộng nên có ví dụ triển khai tối thiểu, hướng dẫn đăng ký, cách kiểm thử và ví dụ lỗi. Ví dụ nên được kiểm tra tự động để tránh lỗi thời.

## 13. Tình huống thiết kế: DSL quy tắc dùng chung cho nhiều phòng ban

Giả sử một tổ chức dùng DSL để mô tả quy tắc trong các miền bán hàng, tài chính và vận chuyển. Tất cả ứng dụng dùng chung parser, AST và runtime cơ bản.

Mỗi miền cần chức năng riêng:

- Bán hàng cần hàm xác định hạng khách hàng và ưu đãi.
- Tài chính cần kiểu Money, quy tắc thuế và làm tròn.
- Vận chuyển cần kiểu Region, hàm tính ngày làm việc và adapter tra cứu tuyến.

Một thiết kế có thể là:

~~~text
                    DSL Core
        Parser - AST - Type Checker - Runtime
                       |
                 Extension Registry
             /            |             \
            v             v              v
       Sales Module  Finance Module  Shipping Module
       - Functions   - Money Type   - Region Type
       - Validators  - Tax Rules    - Route Adapter
~~~

Các module chia sẻ hợp đồng nhưng có thể phát hành độc lập trong giới hạn phiên bản API. Ứng dụng chỉ bật module của những miền mà nó cần.

Khi một module được nạp, engine kiểm tra ID, phiên bản API, tên bị trùng và dependency. Registry công bố metadata cho semantic analyzer và IDE. Runtime chỉ cung cấp capability tương ứng với ứng dụng hiện tại.

Ví dụ, ứng dụng bán hàng có thể dùng hàm sales.customerDiscount, nhưng không được tự động truy cập adapter shipping.routeLookup nếu module vận chuyển chưa được bật hoặc quyền chưa được cấp.

Thiết kế này giúp lõi DSL không phải biết chi tiết nghiệp vụ của từng phòng ban. Tuy nhiên, nó cũng đặt ra trách nhiệm quản lý hợp đồng, phiên bản, quyền và xung đột giữa module. Nếu tổ chức chỉ có một ứng dụng nhỏ, chi phí của kiến trúc module như vậy có thể chưa cần thiết.

## 14. Câu hỏi tự đánh giá

1. Điểm mở rộng khác phần mở rộng và cơ chế mở rộng như thế nào?
2. Vì sao việc mở rộng hàm thường ít rủi ro hơn việc cho plugin tự sửa grammar?
3. Những giai đoạn nào trong pipeline DSL có thể cung cấp điểm mở rộng?
4. Vì sao IR là một ranh giới hữu ích để xây dựng nhiều backend?
5. Registry cần giải quyết những vấn đề nào khi nhiều plugin cùng đăng ký chức năng?
6. Phân biệt đăng ký tĩnh, dependency injection và plugin discovery.
7. Vì sao plugin cần khai báo phiên bản extension API?
8. Làm thế nào để cấp quyền tối thiểu cho một hàm DSL?
9. Những kiểm thử nào cần có cho một extension point?
10. Khi nào một DSL chỉ cần API đăng ký provider, và khi nào mới cần plugin loader hoặc sandbox?

## Kết luận

Điểm mở rộng là những hợp đồng hoặc vị trí được thiết kế để bổ sung khả năng cho DSL. Chúng có thể nằm ở cú pháp, hàm, kiểu dữ liệu, kiểm tra ngữ nghĩa, pipeline biến đổi, backend, runtime, công cụ phát triển hoặc lớp tích hợp.

Một kiến trúc mở rộng tốt xác định rõ trách nhiệm, dữ liệu đầu vào và đầu ra, cách đăng ký, vòng đời, thứ tự thực thi, quyền và chính sách tương thích. Mức mở rộng nên tương xứng với nhu cầu: API provider đơn giản có thể đủ cho một ứng dụng, còn plugin độc lập và sandbox chỉ cần thiết khi có yêu cầu tương ứng. Khi giữ được hợp đồng nhỏ, ngữ nghĩa ổn định và giới hạn bảo mật rõ ràng, DSL có thể phát triển theo nhiều miền mà không làm lõi ngôn ngữ trở nên khó kiểm soát.
