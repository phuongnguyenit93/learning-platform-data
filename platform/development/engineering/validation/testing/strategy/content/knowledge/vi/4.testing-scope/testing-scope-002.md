# Phạm vi kiểm thử: Vẽ ranh giới hệ thống và các thành phần thuộc phạm vi trách nhiệm

## 1. Vì sao phải xác định ranh giới hệ thống?

Trước khi chọn loại kiểm thử, viết kịch bản hoặc ước lượng công sức, nhóm cần thống nhất **đang kiểm thử hệ thống nào, thành phần nào nằm trong quyền kiểm soát của nhóm và phần nào chỉ là phụ thuộc bên ngoài**. Nếu ranh giới không rõ, một nhóm có thể bỏ sót dịch vụ quan trọng, kiểm thử nhầm một hệ thống dùng chung, quy lỗi cho sai chủ sở hữu hoặc đưa ra kết luận chất lượng vượt quá bằng chứng đã thu thập.

Trong VALIDATION_TESTING_STRATEGY, xác định phạm vi là bước chuyển mục tiêu xác nhận của sản phẩm thành một mô hình có thể hành động: thành phần được kiểm thử, tương tác cần xác nhận, trách nhiệm của từng bên, môi trường và dữ liệu được sử dụng, cùng các giới hạn đã biết. Đây là cơ sở để chọn kiểm thử đơn vị, tích hợp, hệ thống, đầu cuối và chấp nhận theo rủi ro.

Một ranh giới hệ thống tốt trả lời được các câu hỏi:

- Người dùng hoặc hệ thống gọi đang tương tác với sản phẩm qua giao diện nào?
- Thành phần nào trực tiếp thực hiện quy tắc nghiệp vụ và lưu giữ trạng thái?
- Những dịch vụ, nhà cung cấp hoặc nền tảng nào nằm ngoài quyền kiểm soát của nhóm?
- Ai chịu trách nhiệm về mã nguồn, cấu hình, dữ liệu, vận hành và hợp đồng của từng thành phần?
- Nhóm có thể quan sát và thu thập bằng chứng ở những điểm nào?
- Những phần nào được kiểm thử trực tiếp, được mô phỏng, chỉ được xác nhận qua hợp đồng hoặc nằm ngoài phạm vi?

Phạm vi không phải một danh sách công cụ hay một danh sách tất cả dịch vụ xuất hiện trong sơ đồ kiến trúc. Nó là tuyên bố có căn cứ về **đối tượng, tương tác và trách nhiệm mà chiến lược kiểm thử sẽ xác nhận**.

## 2. Các khái niệm cần phân biệt

| Khái niệm | Ý nghĩa trong thiết kế phạm vi |
| --- | --- |
| Sản phẩm hoặc hệ thống cần xác nhận | Giải pháp mà người dùng hoặc hệ thống khác sử dụng để đạt một mục tiêu |
| System Under Test (SUT) | Phần hệ thống được chọn làm đối tượng của một hoạt động kiểm thử cụ thể |
| Ranh giới hệ thống | Đường phân định SUT với người dùng, hệ thống phụ thuộc, hạ tầng hoặc tổ chức bên ngoài |
| Thành phần nội bộ | Giao diện, dịch vụ, module, kho dữ liệu hoặc bộ xử lý thuộc cấu trúc sản phẩm |
| Phụ thuộc bên ngoài | Dịch vụ, nền tảng hoặc dữ liệu do nhóm khác hay nhà cung cấp khác quản lý |
| Phạm vi kiểm thử | Thành phần, hành vi, tương tác, môi trường và rủi ro mà một kế hoạch hoặc chiến lược cam kết xác nhận |
| Ngoài phạm vi | Nội dung không được xác nhận trực tiếp trong đợt kiểm thử, kèm lý do và cách xử lý rủi ro nếu có |
| Chủ sở hữu | Cá nhân hoặc nhóm chịu trách nhiệm về một thành phần, hợp đồng hoặc quyết định vận hành |

SUT có thể thay đổi theo cấp độ kiểm thử. Khi kiểm thử một dịch vụ độc lập, dịch vụ đó là SUT và cơ sở dữ liệu hoặc API khác có thể là phụ thuộc. Khi kiểm thử toàn bộ hành trình sản phẩm, nhiều dịch vụ nội bộ cùng thuộc SUT. Vì vậy, không nên vẽ một ranh giới duy nhất rồi mặc định nó áp dụng cho mọi bài kiểm thử; cần nêu rõ ranh giới tương ứng với mục tiêu và cấp độ kiểm thử.

### 2.1. Ranh giới kỹ thuật và ranh giới trách nhiệm

Ranh giới kỹ thuật thể hiện nơi các thành phần giao tiếp qua API, event, giao thức mạng, truy vấn dữ liệu hoặc giao diện người dùng. Ranh giới trách nhiệm thể hiện ai có quyền thay đổi, triển khai, cấu hình, vận hành và hỗ trợ thành phần đó.

Hai ranh giới này thường không trùng nhau. Một dịch vụ có thể do nhóm khác vận hành nhưng vẫn nằm trên đường đi quan trọng của sản phẩm. Một nền tảng đám mây có thể do bộ phận hạ tầng quản lý, trong khi nhóm sản phẩm chịu trách nhiệm cấu hình tài nguyên và kiểm tra cách ứng dụng sử dụng chúng. Vì thế, cần ghi cả **ranh giới tương tác** lẫn **chủ sở hữu và trách nhiệm**.

### 2.2. Phạm vi kiểm thử không đồng nghĩa với quyền sở hữu mã nguồn

Một thành phần do nhà cung cấp quản lý vẫn có thể ảnh hưởng trực tiếp đến hành vi sản phẩm. Nhóm có thể cần xác nhận cách ứng dụng gọi dịch vụ đó, xử lý phản hồi, timeout, lỗi xác thực và callback. Tuy nhiên, nhóm không thể khẳng định đã xác nhận toàn bộ logic nội bộ của nhà cung cấp nếu không có quyền truy cập hoặc bằng chứng tương ứng.

Tương tự, một thành phần do nhóm sở hữu có thể được kiểm thử qua nhiều cấp độ khác nhau. Quyền sở hữu mã nguồn không tự động có nghĩa mọi chức năng của thành phần đều phải nằm trong mọi bộ kiểm thử. Phạm vi cần được quyết định theo mục tiêu, rủi ro và mức bằng chứng cần đạt.

## 3. Quy trình vẽ ranh giới hệ thống

### 3.1. Bắt đầu từ mục tiêu và hành trình cần xác nhận

Hãy mô tả điều người dùng cần hoàn thành và kết quả nghiệp vụ mà sản phẩm phải tạo ra. Một mục tiêu cụ thể giúp nhận diện đúng thành phần tham gia. Ví dụ: “người dùng có thể đặt lịch, thanh toán và nhận xác nhận đặt chỗ” rõ ràng hơn yêu cầu chung chung như “kiểm thử ứng dụng”.

Với mỗi hành trình, xác định:

1. Ai khởi tạo hành động: người dùng, tác vụ theo lịch hay một hệ thống khác?
2. Điểm vào của hành động: giao diện web, ứng dụng di động, API công khai hay sự kiện?
3. Các bước nghiệp vụ và trạng thái quan trọng.
4. Dữ liệu được tạo, đọc, cập nhật hoặc truyền qua hệ thống.
5. Kết quả mà người dùng hoặc hệ thống gọi có thể quan sát.
6. Các trường hợp lỗi có thể làm gián đoạn hoặc làm sai kết quả.

Mỗi hành trình quan trọng nên có ít nhất một kết quả mong đợi có thể kiểm chứng. Kết quả này sẽ dẫn dắt việc xác định thành phần và điểm tích hợp cần đưa vào phạm vi.

### 3.2. Vẽ sơ đồ ngữ cảnh trước khi đi vào chi tiết

Sơ đồ ngữ cảnh đặt sản phẩm ở trung tâm và thể hiện các tác nhân, hệ thống bên ngoài cùng luồng tương tác chính. Ở bước này, không cần mô tả mọi class, pod hoặc bảng dữ liệu. Mục tiêu là nhìn thấy hệ thống nào gửi dữ liệu vào, hệ thống nào nhận dữ liệu ra và những ranh giới tổ chức quan trọng.

Ví dụ dưới đây minh họa một nền tảng đặt lịch. Khung “Nền tảng đặt lịch” là hệ thống đang được xác nhận; các hệ thống thanh toán, thông báo và định danh là phụ thuộc bên ngoài. Sơ đồ không đại diện cho một triển khai cụ thể.

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"Tìm kiếm, đặt lịch"| WEB["Web / Mobile"]
    WEB -->|"HTTPS / API"| SUT
    subgraph SUT["Nền tảng đặt lịch — SUT"]
        API["API / Backend"]
        BOOK["Dịch vụ lịch hẹn"]
        SLOT["Dịch vụ khung giờ"]
        DB[("Cơ sở dữ liệu đặt lịch")]
        API --> BOOK
        BOOK --> SLOT
        BOOK <--> DB
    end
    IDP["Nhà cung cấp định danh"] <-->|"OIDC / OAuth"| API
    PAY["Cổng thanh toán"] <-->|"API / callback"| BOOK
    MSG["Dịch vụ email / SMS"] <-->|"API / event"| BOOK
    OPS["Nhóm vận hành nền tảng"] -.->|"Hạ tầng, giám sát"| SUT
~~~

Khi vẽ sơ đồ thực tế, hãy đặt tên theo vai trò hoặc tên thành phần đã được nhóm thống nhất. Mỗi mũi tên nên có nhãn mô tả loại tương tác như HTTP API, event, truy vấn dữ liệu, file hoặc thao tác thủ công. Nếu một luồng đi qua nhiều nhóm, hãy ghi rõ điểm bàn giao.

### 3.3. Phân rã hệ thống thành thành phần có thể kiểm thử

Sau sơ đồ ngữ cảnh, phân rã SUT theo các nhóm có hành vi hoặc hợp đồng riêng:

- **Kênh tương tác:** web, mobile, API công khai, giao diện quản trị.
- **Thành phần nghiệp vụ:** dịch vụ hoặc module thực hiện quy tắc, kiểm tra điều kiện và chuyển trạng thái.
- **Thành phần dữ liệu:** cơ sở dữ liệu, cache, kho tệp, chỉ mục tìm kiếm và cơ chế sao chép dữ liệu.
- **Xử lý nền:** worker, scheduler, queue consumer và tác vụ định kỳ.
- **Tích hợp:** adapter, gateway, client và bộ chuyển đổi giao thức kết nối hệ thống khác.
- **Nền tảng chạy:** cấu hình triển khai, mạng, danh tính dịch vụ, secret, giám sát và cơ chế phục hồi.

Chỉ phân rã đến mức giúp xác định trách nhiệm và thiết kế kiểm thử. Không cần đưa mọi thư viện nội bộ hoặc chi tiết hạ tầng vào sơ đồ phạm vi cấp sản phẩm nếu chúng không làm thay đổi quyết định kiểm thử.

~~~mermaid
flowchart TB
    subgraph SUT["SUT — Nền tảng đặt lịch"]
        CH["Web / Mobile / Public API"]
        subgraph APP["Lớp ứng dụng"]
            AUTH["Xử lý phiên và quyền"]
            BOOK["Quản lý đặt lịch"]
            SLOT["Kiểm tra khung giờ"]
        end
        subgraph DATA["Lớp dữ liệu"]
            DB[("Đặt lịch và khách hàng")]
            CACHE[("Cache khung giờ")]
        end
        WORK["Worker và scheduler"]
        CH --> AUTH
        AUTH --> BOOK
        BOOK --> SLOT
        BOOK <--> DB
        SLOT <--> CACHE
        WORK <--> DB
    end
    IDP["Định danh bên ngoài"] <-->|"Token / claim"| AUTH
    PAY["Thanh toán bên ngoài"] <-->|"Payment API / callback"| BOOK
    NOTIFY["Thông báo bên ngoài"] <-->|"Message API"| WORK
~~~

### 3.4. Đánh dấu các ranh giới tin cậy và dữ liệu

Ranh giới tin cậy thường xuất hiện khi dữ liệu đi từ thiết bị người dùng vào backend, từ mạng nội bộ ra nhà cung cấp, giữa các tenant hoặc giữa môi trường kiểm thử và production. Ở mỗi ranh giới, cần xác định:

- Ai được phép gửi dữ liệu và danh tính được xác minh bằng cách nào?
- Dữ liệu được kiểm tra, lọc, mã hóa hoặc biến đổi ở đâu?
- Có thông tin cá nhân, thông tin thanh toán hoặc bí mật nào đi qua không?
- Thành phần nào được phép đọc hoặc ghi dữ liệu?
- Có log hoặc trace nào có thể vô tình chứa dữ liệu nhạy cảm không?

Những câu hỏi này giúp đưa kiểm soát bảo mật và quyền riêng tư vào phạm vi phù hợp. Kiểm thử nên sử dụng dữ liệu tổng hợp hoặc dữ liệu đã được khử định danh, với quyền truy cập tối thiểu cần thiết.

## 4. Phân loại thành phần theo phạm vi và trách nhiệm

Không nên chỉ đánh dấu một thành phần là “có” hoặc “không” trong phạm vi. Trên thực tế, một thành phần bên ngoài có thể cần kiểm thử hợp đồng, một nền tảng dùng chung có thể cần xác nhận cấu hình, còn một hệ thống legacy có thể chỉ được kiểm tra qua luồng tương tác được hỗ trợ.

Có thể dùng bốn nhóm sau:

| Phân loại | Ý nghĩa | Cách xử lý trong chiến lược |
| --- | --- | --- |
| Trong phạm vi trực tiếp | Nhóm sở hữu hoặc kiểm soát đủ để kiểm thử hành vi của thành phần | Kiểm thử logic, trạng thái, dữ liệu, lỗi và các thuộc tính chất lượng liên quan |
| Trong phạm vi qua giao diện | Thành phần ngoài nhóm quản lý nhưng tương tác của SUT với thành phần đó là quan trọng | Kiểm thử hợp đồng, cấu hình client, timeout, retry, xử lý lỗi và kết quả quan sát được |
| Phụ thuộc được mô phỏng | Phụ thuộc được thay bằng stub, fake hoặc sandbox trong một số cấp độ kiểm thử | Ghi rõ điều được mô phỏng, hành vi giả định và các rủi ro cần xác nhận ở môi trường khác |
| Ngoài phạm vi đợt kiểm thử | Không được xác nhận trong mục tiêu hoặc lịch kiểm thử hiện tại | Ghi lý do, tác động, chủ sở hữu rủi ro và cách xác nhận thay thế nếu cần |

“Ngoài phạm vi” không có nghĩa là thành phần đó không quan trọng. Nếu một phụ thuộc quan trọng chưa được kiểm thử, báo cáo cần nêu rõ giới hạn bằng chứng và rủi ro còn lại để người quyết định phát hành hiểu đúng.

### 4.1. Ma trận thành phần và trách nhiệm

Mỗi thành phần nên có một bản ghi tối thiểu gồm vai trò, nhóm sở hữu, ranh giới tương tác, cách kiểm thử và bằng chứng. Ví dụ:

| Thành phần | Vai trò | Chủ sở hữu giả định | Phạm vi xác nhận | Bằng chứng |
| --- | --- | --- | --- | --- |
| Web / Mobile | Thu nhận thao tác và hiển thị trạng thái | Nhóm kênh người dùng | Luồng thao tác, validation phía client, khả năng hiển thị lỗi và quyền truy cập | Kết quả UI, ảnh chụp, request/response liên quan |
| API / Backend | Điều phối nghiệp vụ và cung cấp hợp đồng | Nhóm nền tảng sản phẩm | Quy tắc nghiệp vụ, schema, xác thực, phân quyền và mã lỗi | API test, log, trace và trạng thái nghiệp vụ |
| Dịch vụ lịch hẹn | Tạo, đổi, hủy và chuyển trạng thái đặt lịch | Nhóm lịch hẹn | Quy tắc đặt lịch, xung đột khung giờ, tính nhất quán và idempotency | Trạng thái bản ghi, event và kết quả API |
| Cơ sở dữ liệu | Lưu trạng thái đặt lịch | Nhóm dữ liệu hoặc nhóm dịch vụ | Ràng buộc, migration, giao dịch và truy cập theo quyền | Kiểm tra dữ liệu được cho phép, migration report |
| Cổng thanh toán | Xử lý giao dịch bên ngoài | Nhà cung cấp thanh toán | Hợp đồng gọi dịch vụ, callback, timeout và đối soát trạng thái | Sandbox result, callback log đã làm sạch dữ liệu |
| Dịch vụ thông báo | Gửi email hoặc SMS | Nhóm nền tảng thông báo / nhà cung cấp | Nội dung, điều kiện phát, retry và xử lý lỗi gửi | Event, trạng thái gửi và thông tin correlation |
| Nền tảng triển khai | Cung cấp môi trường chạy | Nhóm vận hành / hạ tầng | Cấu hình, quyền, kết nối, health check và khả năng quan sát | Deployment record, cấu hình đã che secret, metric |

Tên nhóm trong bảng chỉ là ví dụ. Khi lập ma trận thật, thay bằng chủ sở hữu được xác nhận trong tổ chức. Nếu trách nhiệm được chia sẻ, hãy tách rõ ai chịu trách nhiệm về mã nguồn, ai quản lý môi trường, ai sở hữu dữ liệu và ai xử lý sự cố.

### 4.2. Xác định trách nhiệm ở điểm tích hợp

Với mỗi API hoặc event, cần chỉ ra bên cung cấp và bên tiêu thụ hợp đồng:

- **Provider:** công bố schema, ý nghĩa trường, quy tắc tương thích, mã lỗi và cam kết vận hành.
- **Consumer:** gửi dữ liệu đúng hợp đồng, xác thực phản hồi, xử lý timeout và lỗi, bảo đảm retry an toàn.
- **Chủ sở hữu luồng nghiệp vụ:** xác định kết quả đầu cuối mong đợi và cách xử lý khi một bên không sẵn sàng.
- **Nhóm vận hành:** cung cấp giám sát, cảnh báo, quyền truy cập và quy trình xử lý sự cố trong phạm vi trách nhiệm.

Một điểm tích hợp có thể có nhiều chủ sở hữu. Cần ghi người hoặc nhóm chịu trách nhiệm cuối cùng cho từng quyết định để lỗi không bị chuyển vòng giữa các nhóm.

## 5. Chuyển ranh giới thành kế hoạch kiểm thử

Sau khi phân loại thành phần, chọn cấp độ kiểm thử dựa trên hành vi và rủi ro. Một thành phần có thể xuất hiện ở nhiều cấp độ, nhưng mỗi cấp độ cần có mục tiêu và oracle riêng.

| Cấp độ | Ranh giới thường gặp | Câu hỏi xác nhận |
| --- | --- | --- |
| Unit / Component | Một hàm, module hoặc dịch vụ cô lập | Quy tắc và trạng thái nội bộ có đúng với đầu vào đã cho? |
| Contract | Ranh giới giữa provider và consumer | Hai bên có hiểu cùng schema, semantics, mã lỗi và version không? |
| Integration | Một nhóm thành phần nội bộ hoặc một phụ thuộc | Dữ liệu và trạng thái có được truyền, lưu và xử lý đúng giữa các thành phần? |
| System / End-to-end | Toàn bộ SUT qua hành trình nghiệp vụ | Người dùng có đạt kết quả mong đợi qua các thành phần thuộc SUT? |
| Acceptance | Ranh giới giữa sản phẩm và nhu cầu người dùng/nghiệp vụ | Sản phẩm có đáp ứng tiêu chí chấp nhận trong bối cảnh sử dụng thực tế? |

Không phải mọi thành phần đều cần một bài kiểm thử đầu cuối riêng. Hãy đặt kiểm thử gần ranh giới nơi hành vi có thể được xác nhận rõ nhất. Kiểm thử đầu cuối nên tập trung vào hành trình có giá trị cao và tương tác mà các tầng thấp hơn không thể chứng minh đầy đủ.

### 5.1. Ví dụ: luồng đặt lịch có thanh toán

Giả sử người dùng chọn khung giờ, tạo đặt lịch, thanh toán và nhận thông báo. Phạm vi hệ thống là nền tảng đặt lịch; nhà cung cấp định danh, cổng thanh toán và dịch vụ email/SMS nằm ngoài quyền quản lý trực tiếp của nhóm sản phẩm.

Một lát cắt kiểm thử có thể được xác định như sau:

| Tình huống | Thành phần trực tiếp liên quan | Phần thuộc trách nhiệm nhóm sản phẩm | Bằng chứng cần có |
| --- | --- | --- | --- |
| Người dùng đã đăng nhập đặt khung giờ còn trống | Web, API, dịch vụ lịch hẹn, database, định danh | Kiểm tra token, quyền, điều kiện khung giờ và trạng thái đặt lịch | Kết quả UI/API và trạng thái đặt lịch |
| Hai người cùng chọn một khung giờ | API, dịch vụ lịch hẹn, database | Bảo đảm quy tắc chống đặt trùng và xử lý xung đột | Một kết quả thành công, kết quả còn lại bị từ chối theo quy tắc |
| Thanh toán được chấp nhận | Dịch vụ lịch hẹn, adapter thanh toán, cổng thanh toán | Gửi yêu cầu đúng hợp đồng, liên kết giao dịch và cập nhật trạng thái | Mã tham chiếu giao dịch, callback và trạng thái cuối |
| Thanh toán timeout | Adapter thanh toán, dịch vụ lịch hẹn | Giữ trạng thái chưa xác định phù hợp, đối soát và tránh tạo giao dịch lặp | Log/trace theo correlation ID và trạng thái sau đối soát |
| Nhà cung cấp email tạm thời lỗi | Worker, queue, adapter thông báo | Retry theo chính sách, ghi nhận lỗi và không làm mất trạng thái đặt lịch | Trạng thái event, số lần retry và kết quả gửi cuối |

Trong ví dụ này, nhóm sản phẩm không xác nhận thuật toán nội bộ của nhà cung cấp thanh toán hay hạ tầng email. Nhóm xác nhận cách sản phẩm sử dụng hợp đồng, phản ứng với các kết quả và bảo toàn trạng thái nghiệp vụ. Nếu cần xác nhận độ tin cậy của nhà cung cấp, đó là một hoạt động riêng với dữ liệu SLA, báo cáo vận hành hoặc bằng chứng từ nhà cung cấp.

### 5.2. Đặt oracle đúng phía ranh giới

Một assertion phải kiểm tra điều mà thành phần chịu trách nhiệm. Ví dụ, consumer có trách nhiệm gửi đúng request và xử lý phản hồi; consumer không thể chứng minh nội bộ provider đã ghi nhận giao dịch nếu không có phản hồi hoặc bằng chứng đối soát đáng tin cậy.

Với từng ranh giới, xác định:

1. Dữ liệu được gửi và phiên bản hợp đồng.
2. Kết quả được kỳ vọng theo hợp đồng.
3. Trạng thái mà bên gọi có thể quan sát.
4. Bằng chứng bổ sung cần lấy từ provider hoặc hệ thống giám sát.
5. Giới hạn kết luận khi không truy cập được hệ thống phía bên kia.

Điều này tránh khẳng định quá mức. Chẳng hạn, phản hồi HTTP thành công chỉ chứng minh request được chấp nhận theo hợp đồng tại điểm đó; nó chưa chắc chứng minh một tác vụ bất đồng bộ đã hoàn tất.

## 6. Môi trường, dữ liệu và cấu hình cũng thuộc phạm vi

Ranh giới kiểm thử không chỉ bao gồm mã ứng dụng. Môi trường và dữ liệu có thể làm thay đổi kết quả, do đó cần xác định rõ:

- **Môi trường:** local, integration, staging, sandbox hoặc production-like; nêu các khác biệt quan trọng so với production.
- **Cấu hình:** feature flag, endpoint, timeout, retry policy, giới hạn tài nguyên và phiên bản schema.
- **Danh tính và quyền:** tài khoản kiểm thử, vai trò, quyền service-to-service và cách cấp/thu hồi quyền.
- **Dữ liệu:** nguồn tạo dữ liệu, trạng thái ban đầu, tính cách ly, dữ liệu nhạy cảm và cách dọn dẹp.
- **Phụ thuộc:** phiên bản dịch vụ ngoài, sandbox hay stub, trạng thái sẵn sàng và giới hạn quota.
- **Quan sát:** log, metric, trace, correlation ID và quyền truy cập bằng chứng.

Một kết quả kiểm thử chỉ có thể tái lập nếu thông tin về artifact, cấu hình và dữ liệu đủ rõ. Không ghi secret hoặc token thật vào tài liệu, log hay ảnh chụp; chỉ ghi tên cấu hình hoặc tham chiếu an toàn.

## 7. Quản lý thay đổi phạm vi và các rủi ro thường gặp

Phạm vi cần được xem xét lại khi kiến trúc, yêu cầu, hợp đồng hoặc quyền sở hữu thay đổi. Một dịch vụ mới, một event mới hoặc việc chuyển dữ liệu sang nhà cung cấp khác có thể tạo ra ranh giới kiểm thử mới dù giao diện người dùng không đổi.

Các lỗi thường gặp gồm:

| Lỗi xác định phạm vi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ vẽ các thành phần do nhóm trực tiếp viết | Bỏ qua phụ thuộc có ảnh hưởng lớn đến hành vi | Bổ sung hệ thống ngoài và hợp đồng trên đường đi nghiệp vụ |
| Gộp mọi thành phần vào một SUT | Khó xác định oracle, chủ sở hữu và nguyên nhân lỗi | Chia phạm vi theo cấp độ kiểm thử và ranh giới tương tác |
| Ghi “ngoài phạm vi” mà không có lý do | Rủi ro bị che khuất và không ai nhận xử lý | Ghi tác động, chủ sở hữu rủi ro và bằng chứng thay thế |
| Nhầm mock với tích hợp thật | Kết quả pass tạo cảm giác tin cậy quá mức | Ghi rõ hành vi được mô phỏng và kiểm thử bổ sung cần thiết |
| Không xác định chủ sở hữu hợp đồng | Lỗi tích hợp bị chuyển qua lại giữa các nhóm | Gán provider, consumer và người chịu trách nhiệm luồng nghiệp vụ |
| Không cập nhật sơ đồ khi kiến trúc đổi | Bộ kiểm thử không còn phản ánh sản phẩm | Gắn rà soát phạm vi vào quy trình thay đổi kiến trúc và release |
| Bỏ qua môi trường và dữ liệu | Lỗi khó tái hiện hoặc kết quả không đại diện | Quản lý phiên bản cấu hình, dữ liệu và điều kiện chạy |

Khi có thay đổi, hãy đánh giá tác động theo chuỗi: thành phần thay đổi → hợp đồng bị ảnh hưởng → hành trình nghiệp vụ liên quan → kịch bản và dữ liệu cần cập nhật → bằng chứng cần thu thập. Cách truy vết này giúp điều chỉnh phạm vi có kiểm soát thay vì mở rộng toàn bộ bộ kiểm thử sau mỗi thay đổi nhỏ.

## 8. Mẫu tuyên bố phạm vi kiểm thử

Một tuyên bố ngắn, có cấu trúc giúp các bên thống nhất trước khi thực thi. Có thể dùng mẫu sau và điền thông tin của sản phẩm:

~~~text
Mục tiêu xác nhận:
Hành trình / khả năng nghiệp vụ:

SUT:
Thành phần trong phạm vi trực tiếp:
Các ranh giới API / event / dữ liệu cần xác nhận:

Phụ thuộc bên ngoài:
Cách xác nhận phụ thuộc (contract / stub / sandbox / live):
Các thành phần ngoài phạm vi:
Lý do và rủi ro còn lại:

Chủ sở hữu thành phần:
Chủ sở hữu hợp đồng:
Chủ sở hữu môi trường và dữ liệu:

Môi trường và phiên bản:
Dữ liệu kiểm thử và cách dọn dẹp:
Tiêu chí chấp nhận / quality gate:
Bằng chứng cần lưu:
Điều kiện xem xét lại phạm vi:
~~~

Tuyên bố này nên được thống nhất bởi chủ sản phẩm, QA, kiến trúc, phát triển và vận hành khi họ cùng chịu trách nhiệm cho kết quả. Nếu một thành phần chưa có chủ sở hữu rõ ràng, cần ghi nhận đây là khoảng trống trách nhiệm trước khi dựa vào thành phần đó làm điều kiện phát hành.

## 9. Checklist trước khi chốt ranh giới

- [ ] Mục tiêu người dùng và hành trình nghiệp vụ cần xác nhận đã được mô tả cụ thể.
- [ ] SUT được định nghĩa cho từng cấp độ kiểm thử.
- [ ] Sơ đồ ngữ cảnh có tác nhân, hệ thống nội bộ, phụ thuộc bên ngoài và luồng tương tác chính.
- [ ] Các thành phần nội bộ được phân rã đến mức đủ để xác định trách nhiệm và oracle.
- [ ] Ranh giới kỹ thuật, ranh giới tin cậy và ranh giới tổ chức đã được xem xét.
- [ ] Mỗi thành phần có chủ sở hữu về mã nguồn, hợp đồng, dữ liệu hoặc vận hành phù hợp.
- [ ] Phụ thuộc bên ngoài có cách xác nhận rõ ràng và giới hạn bằng chứng được ghi nhận.
- [ ] Thành phần ngoài phạm vi có lý do, tác động và chủ sở hữu rủi ro.
- [ ] Môi trường, cấu hình, dữ liệu và danh tính kiểm thử đã được xác định.
- [ ] Các kịch bản được gắn với thành phần, điểm tích hợp và tiêu chí chấp nhận.
- [ ] Có cách thu thập log, metric, trace và kết quả để tái hiện lỗi.
- [ ] Có điều kiện rà soát lại phạm vi khi yêu cầu hoặc kiến trúc thay đổi.

Khi hoàn tất các bước này, nhóm có thể giải thích rõ hệ thống nào đang được xác nhận, tương tác nào được kiểm thử, ai chịu trách nhiệm cho từng ranh giới và phần nào còn là rủi ro chưa được chứng minh. Đó là nền tảng để chiến lược validation testing có phạm vi thực tế, có thể truy vết và hỗ trợ quyết định phát hành.
