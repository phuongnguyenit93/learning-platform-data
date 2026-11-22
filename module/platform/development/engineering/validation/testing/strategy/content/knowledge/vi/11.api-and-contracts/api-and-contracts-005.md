# Lựa chọn kiểm thử hợp đồng hướng người tiêu thụ khi phù hợp

## Mục tiêu bài học

Trong hệ thống có nhiều dịch vụ hoặc API được phát triển và triển khai độc lập, một thay đổi ở bên cung cấp có thể làm hỏng ứng dụng của bên tiêu thụ dù từng thành phần vẫn vượt qua kiểm thử riêng. Kiểm thử hợp đồng hướng người tiêu thụ (Consumer-Driven Contract Testing, thường viết tắt là CDC) giúp các nhóm xác định và xác minh những kỳ vọng thực sự của bên tiêu thụ đối với giao tiếp giữa các thành phần.

Trong chiến lược VALIDATION_TESTING_STRATEGY, CDC là một cách kiểm tra ranh giới tích hợp. Bên tiêu thụ mô tả những tương tác mà nó cần; bên cung cấp xác minh rằng triển khai của mình đáp ứng các tương tác đó. Nhờ vậy, các nhóm có thể phát hiện sớm thay đổi không tương thích mà không cần chạy một môi trường tích hợp lớn cho mọi lần thay đổi.

CDC không phải lựa chọn mặc định cho mọi API. Nó hữu ích khi có ranh giới dịch vụ rõ, các bên thay đổi độc lập và có nhu cầu bảo vệ khả năng tương thích. Nếu các thành phần luôn được phát triển, kiểm thử và phát hành cùng nhau, một bộ kiểm thử tích hợp trực tiếp có thể đơn giản hơn.

Sau bài học, người học có thể:

- Giải thích kiểm thử hợp đồng hướng người tiêu thụ và phân biệt nó với kiểm thử API hoặc kiểm thử tích hợp thông thường.
- Nhận diện tình huống có lợi khi áp dụng CDC và trường hợp không cần thiết.
- Mô tả vòng đời từ kỳ vọng của consumer đến xác minh ở provider.
- Thiết kế hợp đồng tập trung vào hành vi và dữ liệu thực sự được consumer sử dụng.
- Quản lý trạng thái provider, phiên bản hợp đồng và điều kiện tương thích.
- Kết hợp CDC với unit test, schema validation, integration test và end-to-end test.

## 1. Vấn đề CDC giải quyết

Giả sử một nền tảng thương mại điện tử có dịch vụ Đơn hàng cung cấp API cho ứng dụng web, ứng dụng di động và dịch vụ Hỗ trợ khách hàng. Mỗi consumer sử dụng một phần dữ liệu khác nhau:

- Ứng dụng web cần mã đơn hàng, trạng thái và tổng tiền.
- Ứng dụng di động cần thêm thời điểm cập nhật và thông tin giao hàng.
- Dịch vụ Hỗ trợ cần mã đơn hàng, trạng thái thanh toán và mã khách hàng.

Provider có thể thay đổi cấu trúc phản hồi, quy tắc trường dữ liệu hoặc cách xử lý lỗi. Thay đổi đó có thể không ảnh hưởng đến consumer này nhưng lại làm hỏng consumer khác. Chỉ kiểm thử provider riêng lẻ không thể chứng minh tất cả consumer vẫn sử dụng được API. Chỉ kiểm thử consumer với mock cũng không chứng minh provider thật đáp ứng kỳ vọng.

CDC kết nối hai phía bằng một hợp đồng có thể kiểm tra tự động:

1. Consumer mô tả một tương tác mà nó cần và kết quả mà nó kỳ vọng.
2. Công cụ tạo hợp đồng từ các kiểm tra ở phía consumer.
3. Provider chạy xác minh hợp đồng với triển khai của mình.
4. Kết quả xác minh được gắn với phiên bản consumer, provider và hợp đồng.
5. Nhóm dùng bằng chứng tương thích để quyết định có thể triển khai hoặc phát hành phiên bản hay không.

Cách làm này giúp phát hiện sớm một số vấn đề tương thích ở ranh giới dịch vụ, đồng thời cho phép mỗi nhóm duy trì nhịp phát triển riêng.

## 2. Hợp đồng hướng người tiêu thụ là gì?

**Consumer** là thành phần gọi hoặc sử dụng API, sự kiện hay thông điệp do một thành phần khác cung cấp. **Provider** là thành phần cung cấp giao diện đó.

**Consumer-driven contract** là mô tả có thể thực thi về những tương tác và kết quả mà một consumer cụ thể cần từ provider. Hợp đồng được hình thành từ nhu cầu của consumer thay vì cố gắng mô tả mọi khả năng mà provider có thể cung cấp.

Một hợp đồng có thể mô tả:

- Phương thức, đường dẫn hoặc loại thông điệp.
- Các header hoặc metadata cần thiết.
- Dữ liệu yêu cầu mà consumer gửi.
- Trạng thái phản hồi hoặc loại thông điệp.
- Những trường dữ liệu consumer cần đọc và các ràng buộc quan trọng.
- Hành vi khi dữ liệu không hợp lệ, tài nguyên không tồn tại hoặc quyền truy cập bị từ chối.
- Điều kiện hoặc trạng thái ban đầu cần có để tương tác diễn ra.

Hợp đồng nên tập trung vào hành vi quan sát được tại ranh giới. Nó không nên ràng buộc consumer vào chi tiết triển khai nội bộ của provider như tên lớp, cách lưu trữ hoặc thứ tự truy vấn cơ sở dữ liệu.

### 2.1. Consumer-driven khác gì provider-defined schema?

Một schema API như OpenAPI thường mô tả giao diện do provider công bố: các endpoint, cấu trúc dữ liệu, kiểu trường và phản hồi được hỗ trợ. Đây là tài liệu quan trọng để khám phá và kiểm tra API.

CDC bổ sung một góc nhìn khác: mỗi consumer chỉ ra những tương tác và phần dữ liệu mà nó thực sự phụ thuộc. Một schema tổng quát có thể cho phép nhiều trường hoặc biến thể, trong khi hợp đồng consumer cho biết những phần nào cần được bảo vệ để consumer cụ thể tiếp tục hoạt động.

Hai cách tiếp cận bổ trợ nhau:

- Schema hoặc OpenAPI giúp mô tả bề mặt API và các quy tắc chung.
- CDC giúp kiểm tra các kỳ vọng cụ thể của từng consumer.
- Provider test xác minh logic và quy tắc nội bộ của provider.
- Integration test xác minh các thành phần hoạt động cùng nhau trong môi trường có phụ thuộc thực.

Không nên coi CDC là bản thay thế tài liệu API hoặc mọi kiểm thử tích hợp.

## 3. Cách CDC hoạt động

### 3.1. Phía consumer: xác định kỳ vọng

Consumer bắt đầu từ một nhu cầu thực tế. Ví dụ, màn hình chi tiết đơn hàng gọi:

~~~http
GET /orders/ORD-42
Accept: application/json
Authorization: Bearer <token>
~~~

Consumer cần phản hồi thành công với mã đơn hàng, trạng thái và tổng tiền. Một ví dụ phản hồi có thể là:

~~~json
{
  "id": "ORD-42",
  "status": "PAID",
  "total": {
    "amount": 125000,
    "currency": "VND"
  }
}
~~~

Hợp đồng nên mô tả những phần mà consumer thực sự sử dụng và những quy tắc có ý nghĩa. Nếu consumer chỉ hiển thị id, status và total, không nên mặc định rằng mọi trường không liên quan đều phải có giá trị cố định. Nếu consumer cần trường currency để định dạng tiền, trường đó phải được thể hiện rõ trong kỳ vọng.

Bài kiểm thử consumer thường chạy với một mock provider do công cụ hợp đồng tạo hoặc cấu hình. Mock provider trả về phản hồi phù hợp với tương tác được khai báo. Consumer kiểm tra rằng nó gửi đúng request và xử lý được response theo cách mong đợi.

Kết quả ở bước này tạo ra hợp đồng có thể chia sẻ với provider. Nó chứng minh consumer được kiểm tra với một tương tác đã mô tả; chưa chứng minh provider thật đáp ứng tương tác đó.

### 3.2. Phía provider: xác minh hợp đồng

Provider lấy hợp đồng đã được công bố và chạy các tương tác đó với triển khai provider. Công cụ xác minh thường:

1. Chuẩn bị trạng thái cần thiết cho một tương tác.
2. Gửi request hoặc cung cấp thông điệp theo hợp đồng.
3. Nhận response hoặc kết quả xử lý từ provider thật trong môi trường xác minh.
4. So sánh kết quả với kỳ vọng trong hợp đồng.
5. Ghi lại tương tác nào đạt hoặc thất bại.

Ví dụ, provider cần có đơn hàng ORD-42 với trạng thái thanh toán PAID trước khi xác minh phản hồi chi tiết đơn hàng. Trạng thái này có thể được tạo bằng một provider-state setup hoặc fixture riêng cho môi trường kiểm thử.

Provider verification trả lời câu hỏi: “Triển khai provider hiện tại có đáp ứng hợp đồng mà consumer đã công bố không?” Nó không chứng minh mọi luồng nghiệp vụ hoặc mọi biến thể của provider đều đúng.

### 3.3. Chia sẻ và lưu kết quả

Trong môi trường có nhiều nhóm, hợp đồng và kết quả xác minh thường được lưu tại một nơi có thể truy cập, chẳng hạn contract broker hoặc kho tạo tác CI. Thông tin cần truy vết gồm:

- Phiên bản hoặc mã định danh consumer.
- Phiên bản hoặc mã định danh provider.
- Phiên bản hợp đồng.
- Nhánh, commit hoặc build tạo ra kết quả.
- Trạng thái xác minh và thời điểm chạy.
- Môi trường hoặc cấu hình có liên quan.

Việc lưu kết quả giúp nhóm biết tổ hợp phiên bản nào đã được xác minh tương thích. Nếu không có thông tin phiên bản, một kết quả pass cũ có thể bị hiểu nhầm là bằng chứng cho build mới.

## 4. Vòng đời của một consumer-driven contract

~~~mermaid
flowchart TD
    A[Consumer xác định tương tác cần dùng] --> B[Viết test với mock provider]
    B --> C[Tạo và công bố hợp đồng]
    C --> D[Provider nhận hợp đồng]
    D --> E[Chuẩn bị provider state]
    E --> F[Chạy provider verification]
    F --> G{Hợp đồng đạt?}
    G -->|Có| H[Lưu kết quả theo phiên bản]
    G -->|Không| I[Điều tra sai khác]
    I --> J[Thống nhất sửa consumer, provider hoặc hợp đồng]
    J --> B
    H --> K[Kiểm tra tương thích trước triển khai]
    K --> L[Theo dõi tích hợp sau phát hành]
~~~

Các bước có thể được tự động hóa trong pipeline:

1. Consumer thay đổi mã hoặc kỳ vọng và chạy consumer contract test.
2. Hợp đồng mới được tạo, kiểm tra và công bố cùng thông tin phiên bản.
3. Provider chạy xác minh với các hợp đồng consumer còn được hỗ trợ.
4. Kết quả được lưu và cập nhật ma trận tương thích.
5. Pipeline hoặc quy trình phát hành kiểm tra tổ hợp phiên bản dự kiến triển khai.
6. Sau triển khai, nhóm tiếp tục giám sát lỗi thực tế và cập nhật hợp đồng khi nhu cầu thay đổi.

Không nhất thiết phải chạy provider verification trên mọi môi trường hoặc ở mọi bước. Nhóm cần đặt kiểm tra ở vị trí có thể cung cấp phản hồi đủ sớm trước khi phiên bản không tương thích được đưa vào sử dụng.

## 5. Khi nào nên lựa chọn CDC?

CDC thường có giá trị khi một hoặc nhiều điều kiện sau xuất hiện:

- Consumer và provider do các nhóm khác nhau sở hữu.
- Hai phía triển khai hoặc phát hành độc lập.
- Một provider phục vụ nhiều consumer với nhu cầu khác nhau.
- Tích hợp giữa các dịch vụ thường xuyên gây lỗi tương thích.
- Môi trường end-to-end đầy đủ tốn kém, chậm hoặc khó ổn định.
- Nhóm cần biết trước khi triển khai liệu phiên bản provider mới có tương thích với các consumer đang hoạt động không.
- API hoặc thông điệp là hợp đồng quan trọng giữa các ranh giới dịch vụ.

CDC đặc biệt hữu ích trong kiến trúc microservices hoặc hệ thống phân tán có nhiều consumer độc lập. Nó cũng có thể áp dụng cho giao tiếp bất đồng bộ, chẳng hạn producer phát sự kiện và consumer xử lý sự kiện, nếu nhóm có cách mô tả và xác minh hợp đồng thông điệp.

### 5.1. Khi nào CDC có thể không cần thiết?

CDC có thể tạo thêm chi phí nếu:

- Các thành phần luôn được phát triển và phát hành cùng nhau.
- Chỉ có một consumer và một provider đơn giản, với bộ integration test trực tiếp đã nhanh và đáng tin cậy.
- Giao diện còn thay đổi liên tục và chưa có ranh giới ổn định để mô tả kỳ vọng.
- Provider bên ngoài không thể xác minh hợp đồng và nhóm không có môi trường thử nghiệm hoặc cơ chế kiểm tra tương thích thay thế.
- Hệ thống chưa có khả năng quản lý phiên bản hợp đồng, kết quả và trạng thái tương thích.
- Chi phí duy trì hợp đồng cao hơn rủi ro mà nó giúp giảm.

Không nên áp dụng CDC chỉ vì tổ chức đang sử dụng microservices. Hãy xác định vấn đề tương thích cụ thể và xem hợp đồng có thể cung cấp bằng chứng hữu ích hay không.

## 6. Thiết kế hợp đồng tốt

### 6.1. Chỉ mô tả điều consumer thực sự cần

Một hợp đồng quá rộng sẽ ràng buộc provider vào các chi tiết không cần thiết. Nếu consumer chỉ sử dụng một số trường, hợp đồng nên kiểm tra những trường và quy tắc có liên quan.

Ví dụ, nếu consumer chỉ cần id, status và total, không nên yêu cầu mọi trường metadata nội bộ của provider phải có mặt hoặc có giá trị cố định. Hợp đồng cũng không nên khẳng định thứ tự trường JSON nếu thứ tự đó không có ý nghĩa theo giao thức.

Ngược lại, không được lược bỏ các ràng buộc thực sự quan trọng. Nếu consumer cần currency để diễn giải amount, hoặc cần status thuộc một tập giá trị xác định, các kỳ vọng đó phải được nêu rõ.

### 6.2. Phân biệt trường bắt buộc, tùy chọn và không được sử dụng

Hợp đồng nên thể hiện chính xác:

- Trường bắt buộc phải có.
- Trường có thể vắng mặt hoặc nhận giá trị null.
- Kiểu dữ liệu và định dạng cần thiết.
- Các giá trị hoặc điều kiện mà consumer có thể xử lý.
- Trường nào consumer không phụ thuộc và không cần ràng buộc.

Cần phân biệt “không có trường”, “trường có giá trị null” và “trường có giá trị rỗng” nếu API định nghĩa chúng khác nhau. Đây là nguồn gây lỗi tương thích phổ biến.

### 6.3. Kiểm tra ngữ nghĩa, không chỉ cấu trúc

Một response có thể đúng JSON schema nhưng sai ý nghĩa nghiệp vụ. Ví dụ:

- status có kiểu chuỗi nhưng trả về trạng thái không được consumer hiểu.
- total.amount là số nhưng được tính sai.
- Timestamp hợp lệ về định dạng nhưng dùng múi giờ không đúng quy ước.
- API trả 200 nhưng nội dung cho biết giao dịch chưa hoàn tất.

Hợp đồng cần thể hiện các quy tắc ngữ nghĩa mà consumer dựa vào. Tuy nhiên, các quy tắc nghiệp vụ phức tạp nên được kiểm tra thêm trong provider test và integration test, tránh biến hợp đồng thành một bản sao toàn bộ đặc tả nghiệp vụ.

### 6.4. Kiểm tra cả phản hồi lỗi khi cần

Consumer thường cần xử lý các trường hợp:

- Tài nguyên không tồn tại.
- Dữ liệu yêu cầu không hợp lệ.
- Không được phép truy cập.
- Xung đột hoặc trạng thái không hợp lệ.
- Giới hạn tần suất.
- Dịch vụ tạm thời không sẵn sàng.

Không phải mọi consumer đều cần mọi trường hợp lỗi. Hãy chọn những phản hồi mà consumer thực sự xử lý hoặc cần bảo vệ. Với lỗi có cấu trúc, hợp đồng nên xác định mã trạng thái, mã lỗi hoặc trường dữ liệu mà consumer dựa vào.

## 7. Provider state và dữ liệu kiểm thử

**Provider state** mô tả trạng thái ban đầu mà provider cần có để thực hiện một tương tác hợp đồng. Ví dụ: “đơn hàng ORD-42 tồn tại và đã thanh toán”, “khách hàng đang hoạt động” hoặc “mã sản phẩm có tồn kho”.

Provider verification cần chuẩn bị trạng thái độc lập cho mỗi tương tác hoặc nhóm tương tác. Điều này giúp kết quả có thể lặp lại và tránh phụ thuộc vào thứ tự chạy.

Nguyên tắc thiết kế provider state:

- Mô tả điều kiện nghiệp vụ cần thiết, không mô tả chi tiết triển khai nội bộ không liên quan.
- Tạo dữ liệu cô lập, có thể tái tạo và dọn dẹp.
- Không phụ thuộc vào dữ liệu production hoặc tài khoản thật.
- Không giả định tương tác trước đã tạo trạng thái cho tương tác sau.
- Kiểm soát thời gian, ID, dữ liệu ngẫu nhiên và phụ thuộc ngoài.
- Bảo đảm dữ liệu không chứa thông tin cá nhân hoặc bí mật không cần thiết.

Nếu provider state setup quá phức tạp, đó có thể là dấu hiệu provider khó kiểm thử hoặc hợp đồng đang bao phủ quá nhiều hành vi. Nhóm nên xem xét tạo fixture, test data builder hoặc API hỗ trợ thiết lập trạng thái riêng cho môi trường xác minh.

## 8. Quản lý thay đổi và tương thích hợp đồng

Thay đổi API không phải lúc nào cũng phá vỡ tương thích. Nhóm cần đánh giá tác động dựa trên cách consumer sử dụng giao diện.

| Thay đổi | Rủi ro tương thích thường gặp | Hướng xử lý |
|---|---|---|
| Thêm trường response tùy chọn | Thường tương thích nếu consumer bỏ qua trường chưa biết và schema cho phép. | Xác minh consumer không yêu cầu cấu trúc đóng; kiểm tra serializer và schema. |
| Xóa hoặc đổi tên trường đang dùng | Có thể làm consumer không phân tích được response. | Coi là thay đổi phá vỡ; cung cấp giai đoạn chuyển tiếp hoặc phiên bản mới. |
| Đổi kiểu dữ liệu | Có thể làm lỗi parse hoặc thay đổi ý nghĩa. | Kiểm tra mọi consumer bị ảnh hưởng; tránh đổi kiểu trực tiếp nếu không có lộ trình. |
| Thêm giá trị enum | Consumer có thể không xử lý giá trị mới nếu giả định tập giá trị đóng. | Thiết kế consumer xử lý giá trị không nhận diện; kiểm tra kỳ vọng theo hợp đồng. |
| Thay đổi ý nghĩa trường nhưng giữ nguyên kiểu | Dễ gây lỗi ngữ nghĩa mà schema không phát hiện. | Xem là thay đổi hợp đồng; mô tả ngữ nghĩa và kiểm tra các consumer liên quan. |
| Thay đổi mã lỗi hoặc cấu trúc lỗi | Consumer có thể đi sai nhánh xử lý. | Xác minh phản hồi lỗi và cập nhật hợp đồng trước khi phát hành. |
| Thay đổi xác thực hoặc quyền | Có thể làm consumer không gọi được hoặc vô tình mở quyền. | Kiểm tra contract về header/credential và bổ sung kiểm thử bảo mật, tích hợp. |

Không nên cho rằng mọi thay đổi bổ sung đều an toàn. Consumer có thể dùng schema strict, giải mã enum theo tập cố định hoặc phụ thuộc vào hành vi ngầm. Tính tương thích cần được kiểm tra với các consumer thực tế và cách họ xử lý dữ liệu.

### 8.1. Consumer mới và consumer cũ

Provider thường cần hỗ trợ nhiều phiên bản consumer cùng lúc trong quá trình triển khai. Một consumer mới có thể yêu cầu trường mới trong khi consumer cũ vẫn đang hoạt động. Trước khi xóa trường hoặc thay đổi hành vi, provider cần biết consumer nào còn phụ thuộc.

Quy trình an toàn thường gồm:

1. Bổ sung khả năng mới theo cách tương thích.
2. Triển khai provider hỗ trợ cả hành vi cũ và mới.
3. Cập nhật consumer để sử dụng khả năng mới.
4. Xác minh các phiên bản consumer đang được hỗ trợ.
5. Theo dõi việc sử dụng khả năng cũ.
6. Chỉ loại bỏ hành vi cũ khi không còn consumer được hỗ trợ phụ thuộc và có kế hoạch chuyển đổi rõ ràng.

### 8.2. Ma trận tương thích

Với nhiều consumer và provider, nhóm cần biết phiên bản nào đã được xác minh. Một contract broker hoặc hệ thống CI có thể lưu ma trận gồm:

- Consumer và phiên bản hoặc commit.
- Provider và phiên bản hoặc build.
- Hợp đồng được kiểm tra.
- Kết quả provider verification.
- Môi trường, thời điểm và trạng thái triển khai.
- Các phiên bản còn được hỗ trợ.

Ma trận giúp trả lời câu hỏi: “Provider build này đã được xác minh với các consumer cần hỗ trợ chưa?” Kết quả của một consumer không đủ để kết luận provider tương thích với mọi consumer khác.

## 9. Tích hợp CDC vào CI/CD

CDC có thể được tích hợp thành các bước trong pipeline.

### 9.1. Pipeline phía consumer

- Chạy unit test và consumer test.
- Khởi tạo mock provider theo tương tác khai báo.
- Xác minh consumer gửi request đúng và xử lý response phù hợp.
- Tạo hợp đồng có định danh phiên bản.
- Công bố hợp đồng cùng metadata build hoặc commit.

Nếu consumer thay đổi cách sử dụng API, hợp đồng mới cần được công bố để provider xác minh. Nếu chỉ thay đổi logic nội bộ không ảnh hưởng giao tiếp, hợp đồng có thể không thay đổi.

### 9.2. Pipeline phía provider

- Lấy các hợp đồng consumer còn được hỗ trợ.
- Chuẩn bị provider state cho từng tương tác.
- Chạy provider verification trên build hiện tại.
- Lưu kết quả gắn với phiên bản provider và hợp đồng.
- Báo lỗi nếu có kỳ vọng quan trọng không được đáp ứng.

Provider cần xác minh hợp đồng của các consumer liên quan, không chỉ hợp đồng của một ứng dụng được chọn tùy ý. Với hệ thống nhiều consumer, cần quy định cách chọn phiên bản còn được hỗ trợ và xử lý hợp đồng đã hết hạn.

### 9.3. Điều kiện trước triển khai

Trước khi triển khai provider hoặc consumer, pipeline có thể kiểm tra ma trận tương thích của tổ hợp phiên bản dự kiến. Việc này giúp tránh triển khai provider mới trong khi một consumer đang hoạt động không tương thích.

Cần xác định rõ:

- Phiên bản consumer nào phải được hỗ trợ.
- Kết quả xác minh nào được coi là còn hiệu lực.
- Khi nào một hợp đồng có thể hết hạn hoặc bị ngừng hỗ trợ.
- Cách xử lý trường hợp một consumer không thể nâng cấp ngay.
- Ai có quyền chấp nhận ngoại lệ và rủi ro còn lại.

Không nên dùng một kết quả pass cũ cho build mới nếu mã nguồn, cấu hình hoặc hợp đồng đã thay đổi theo cách ảnh hưởng đến giao tiếp.

## 10. CDC cho giao tiếp bất đồng bộ và thông điệp

CDC không chỉ giới hạn ở HTTP request/response. Với hệ thống hướng sự kiện, producer phát thông điệp và consumer đăng ký hoặc xử lý thông điệp đó. Hợp đồng có thể mô tả:

- Tên hoặc loại sự kiện.
- Schema và trường bắt buộc.
- Ý nghĩa của từng trường.
- Metadata, key, partition hoặc header quan trọng.
- Quy tắc tương thích schema.
- Hành vi khi consumer nhận phiên bản sự kiện mới.
- Quy tắc xử lý thông điệp lặp, thứ tự hoặc retry nếu thuộc hợp đồng giao tiếp.

Ví dụ, producer phát OrderPaid với orderId, paidAt và amount. Consumer gửi hóa đơn cần orderId và paidAt; consumer phân tích doanh thu cần thêm amount và currency. Hợp đồng của mỗi consumer có thể mô tả phần dữ liệu nó phụ thuộc.

Với thông điệp bất đồng bộ, provider verification cần xác minh producer có thể phát thông điệp phù hợp và consumer có thể xử lý hợp đồng. Cần bổ sung integration test với broker thật hoặc tương đương để xác minh routing, serialization, acknowledgement, retry và cấu hình. CDC không tự chứng minh toàn bộ hành vi vận chuyển thông điệp.

## 11. Những giới hạn của CDC

CDC tập trung vào giao tiếp tại ranh giới, vì vậy không thể thay thế các loại kiểm thử khác:

- **Không chứng minh toàn bộ nghiệp vụ đúng:** hợp đồng chỉ xác minh các tương tác được mô tả. Provider vẫn cần unit test và kiểm thử nghiệp vụ.
- **Không chứng minh hạ tầng production hoạt động:** DNS, mạng, TLS, secrets, quyền, cấu hình và năng lực môi trường cần được kiểm tra riêng.
- **Không thay thế kiểm thử end-to-end:** các luồng xuyên nhiều dịch vụ, giao diện và quy trình người dùng vẫn cần kiểm tra ở mức phù hợp.
- **Không tự động chứng minh hiệu năng hoặc khả năng chịu tải:** cần kiểm thử hiệu năng và kiểm tra tải riêng.
- **Không thay thế kiểm thử bảo mật:** hợp đồng có thể mô tả phản hồi xác thực hoặc quyền, nhưng không chứng minh hệ thống chống được mọi tấn công.
- **Không bảo đảm consumer xử lý mọi dữ liệu hợp lệ:** consumer test và provider verification cần được thiết kế với các giá trị, trạng thái và trường hợp biên có ý nghĩa.
- **Không loại bỏ nhu cầu quản trị phiên bản:** hợp đồng cũ hoặc metadata thiếu có thể tạo kết luận tương thích sai.

CDC là một lớp bằng chứng trong chiến lược kiểm thử. Cần kết hợp nó với unit test, schema validation, integration test, end-to-end test, kiểm thử phi chức năng và giám sát.

## 12. Ví dụ thực tế: dịch vụ hồ sơ khách hàng

Một nền tảng có ba consumer gọi Customer Profile API: ứng dụng web, ứng dụng di động và dịch vụ chăm sóc khách hàng. Provider muốn đổi cách lưu tên hiển thị và thêm trường preferredLanguage.

**Bước 1 — Xác định kỳ vọng:** Ứng dụng web cần customerId, displayName và trạng thái hồ sơ. Ứng dụng di động cần thêm preferredLanguage. Dịch vụ chăm sóc khách hàng cần customerId và trạng thái xác minh.

**Bước 2 — Tạo hợp đồng:** mỗi consumer mô tả request và các trường response mà nó sử dụng. Hợp đồng không yêu cầu mọi trường nội bộ hoặc metadata provider phải cố định nếu consumer không phụ thuộc.

**Bước 3 — Xác minh provider:** provider chuẩn bị các trạng thái hồ sơ đại diện và chạy các hợp đồng. Nếu provider đổi displayName thành name mà không giữ trường cũ, xác minh có thể phát hiện ứng dụng web và di động vẫn cần displayName.

**Bước 4 — Lập kế hoạch chuyển đổi:** provider có thể bổ sung trường mới trước, cập nhật consumer theo từng đợt, theo dõi consumer còn dùng trường cũ và chỉ loại bỏ trường cũ sau khi các phiên bản được hỗ trợ đã chuyển đổi.

**Bước 5 — Kiểm thử bổ sung:** nhóm vẫn chạy integration test với kho dữ liệu và kiểm thử bảo mật cho quyền truy cập hồ sơ. CDC giúp bảo vệ kỳ vọng giao tiếp của từng consumer, còn các kiểm tra khác xác minh dữ liệu, bảo mật và hành vi tổng thể.

## 13. Quy trình lựa chọn CDC có thể áp dụng

1. **Xác định ranh giới:** lập danh sách consumer, provider, API hoặc kênh thông điệp.
2. **Xác định vấn đề tương thích:** xem lỗi tích hợp, thay đổi độc lập, thời gian chờ môi trường và số lượng consumer.
3. **Đánh giá mức phù hợp:** cân nhắc lợi ích so với chi phí tạo, lưu, xác minh và quản lý hợp đồng.
4. **Chọn tương tác quan trọng:** bắt đầu từ các luồng consumer thực sự phụ thuộc, bao gồm phản hồi lỗi quan trọng.
5. **Thiết kế hợp đồng tối thiểu:** mô tả request, response, dữ liệu và ngữ nghĩa cần bảo vệ; tránh ràng buộc thừa.
6. **Viết consumer test:** xác minh consumer sử dụng mock provider đúng cách và tạo hợp đồng.
7. **Thiết lập provider verification:** chuẩn bị provider state, chạy tương tác trên triển khai provider và lưu kết quả.
8. **Tích hợp vào pipeline:** công bố hợp đồng, xác minh phiên bản và kiểm tra tương thích trước triển khai.
9. **Quản lý thay đổi:** cập nhật hợp đồng khi kỳ vọng consumer thay đổi; thống nhất lộ trình khi thay đổi phá vỡ tương thích.
10. **Đánh giá hiệu quả:** theo dõi lỗi tương thích, thời gian phản hồi, chi phí bảo trì và lỗi lọt qua sau phát hành.

Nên bắt đầu với một ranh giới dịch vụ có vấn đề tương thích rõ ràng. Sau khi chứng minh được giá trị, nhóm có thể mở rộng sang các consumer/provider khác theo mức rủi ro và nhu cầu.

## 14. Những sai lầm thường gặp

- **Coi consumer test với mock provider là bằng chứng provider hoạt động đúng:** cần provider verification để xác minh triển khai thực tế đáp ứng hợp đồng.
- **Mô tả mọi khả năng của provider trong hợp đồng:** làm hợp đồng lớn, dễ vỡ và không phản ánh nhu cầu consumer.
- **Chỉ kiểm tra cấu trúc JSON:** có thể bỏ sót ngữ nghĩa, giá trị trạng thái và hành vi lỗi quan trọng.
- **Dùng dữ liệu provider state phụ thuộc môi trường:** làm kết quả không lặp lại và khó chẩn đoán.
- **Chỉ xác minh consumer mới nhất:** có thể bỏ sót consumer cũ vẫn đang được hỗ trợ.
- **Không gắn kết quả với phiên bản:** khiến kết quả pass cũ bị dùng nhầm cho build mới.
- **Coi mọi thay đổi bổ sung là an toàn:** consumer có thể xử lý enum hoặc schema theo cách nghiêm ngặt.
- **Dùng CDC thay cho integration test:** bỏ sót cấu hình mạng, broker, cơ sở dữ liệu, xác thực và môi trường.
- **Không có quy trình loại bỏ hợp đồng cũ:** tạo gánh nặng duy trì và làm ma trận tương thích khó hiểu.
- **Không thống nhất quyền sở hữu:** consumer và provider không rõ ai cập nhật hợp đồng, ai sửa lỗi và ai chấp nhận ngoại lệ.

## 15. Checklist trước khi áp dụng CDC

- [ ] Có ranh giới consumer/provider rõ ràng.
- [ ] Có vấn đề tương thích hoặc nhu cầu phát hành độc lập mà CDC có thể giải quyết.
- [ ] Consumer xác định được các tương tác và dữ liệu thực sự cần.
- [ ] Hợp đồng mô tả request, response, lỗi và ngữ nghĩa quan trọng.
- [ ] Consumer test chạy với mock provider và tạo hợp đồng có thể truy vết.
- [ ] Provider verification chạy trên triển khai provider với provider state tái lập.
- [ ] Kết quả được gắn với phiên bản consumer, provider và hợp đồng.
- [ ] Các consumer còn được hỗ trợ được đưa vào xác minh tương thích.
- [ ] Có quy trình thay đổi, hết hạn và loại bỏ hợp đồng.
- [ ] Có integration test và các kiểm thử khác cho rủi ro CDC không bao phủ.
- [ ] Pipeline có điều kiện rõ để chặn triển khai hoặc xử lý ngoại lệ.
- [ ] Có người sở hữu hợp đồng và quy trình xử lý khi xác minh thất bại.

## Kết luận

Kiểm thử hợp đồng hướng người tiêu thụ phù hợp khi consumer và provider có ranh giới rõ, thay đổi độc lập và cần bảo vệ khả năng tương thích. Consumer mô tả tương tác thực sự cần; provider xác minh triển khai đáp ứng các kỳ vọng đó; pipeline lưu kết quả theo phiên bản để hỗ trợ quyết định triển khai. Hợp đồng nên nhỏ, tập trung vào hành vi và được quản lý cùng vòng đời dịch vụ. CDC bổ sung cho unit test, schema validation, integration test và end-to-end test; lựa chọn áp dụng cần dựa trên rủi ro và lợi ích thực tế của từng ranh giới.
