# Xác định data flow

## 1. Data flow là gì và vì sao cần xác định trước yêu cầu bảo mật?

**Data flow**, hay **luồng dữ liệu**, mô tả dữ liệu di chuyển từ nguồn nào đến đích nào, qua thành phần xử lý nào, trong ngữ cảnh nghiệp vụ và quyền truy cập nào.

Một luồng không chỉ là “trình duyệt gọi API”. Để phân tích bảo mật, cần biết:

- Dữ liệu nào được gửi, nhận, biến đổi hoặc tạo mới?
- Ai khởi phát và thành phần nào thực sự thực hiện thao tác?
- Dữ liệu đi qua ranh giới tin cậy nào?
- Ở mỗi điểm, ai có thể đọc, sửa hoặc sao chép dữ liệu?
- Có lưu lại dữ liệu trong cơ sở dữ liệu, hàng đợi, tệp tạm, log hoặc bản sao lưu không?
- Khi thất bại, thử lại hoặc phục hồi, dữ liệu tiếp tục đi đâu?

Ví dụ, chức năng “xuất hóa đơn” có thể tạo ra các luồng: nhận yêu cầu xuất, ghi công việc vào hàng đợi, đọc hóa đơn, tạo tệp, lưu tệp, trả đường tải, tải tệp, ghi sự kiện kiểm toán và sao lưu. Chỉ ghi một mũi tên “người dùng → hệ thống” sẽ bỏ qua nhiều nơi có khả năng làm lộ dữ liệu.

Trong thiết kế yêu cầu bảo mật, data flow giúp chuyển từ mục tiêu chung sang nghĩa vụ cụ thể:

| Mục tiêu | Câu hỏi theo luồng dữ liệu | Yêu cầu có thể phát sinh |
| --- | --- | --- |
| Giữ bí mật | Ai nhận bản gốc và những bản sao? | Giới hạn trường dữ liệu, quyền đọc và phạm vi tenant |
| Giữ toàn vẹn | Ai có thể thay đổi dữ liệu giữa nguồn và đích? | Kiểm tra nguồn, cấu trúc, quyền thao tác và tính nhất quán |
| Duy trì khả năng phục vụ | Luồng phụ thuộc vào đâu, có bị tắc hoặc mất dữ liệu không? | Giới hạn tải, xử lý lỗi, thử lại và phục hồi |
| Truy vết được thao tác | Dấu vết được tạo ở đâu, có bị mất hoặc chứa bí mật không? | Sự kiện kiểm toán, mã tương quan và quy tắc loại trừ dữ liệu |
| Thu hồi được quyền | Bản sao hoặc liên kết nào vẫn hoạt động sau thu hồi? | Kiểm tra quyền tại thời điểm dùng và giới hạn hiệu lực |

Kết quả cần có không chỉ là sơ đồ đẹp. Đó là **mô hình đủ rõ để xác định rủi ro, giao trách nhiệm và chọn điểm kiểm chứng**.

## 2. Chốt bối cảnh và phạm vi mô hình

Xét một cổng quản lý hóa đơn cho nhiều doanh nghiệp. Mỗi doanh nghiệp là một **tenant**, có dữ liệu và phạm vi quyền riêng.

Một thành viên có thể đọc hóa đơn thuộc phạm vi được cấp, yêu cầu tạo bản xuất, xem trạng thái công việc và tải tệp kết quả. Quản trị viên tenant có thể cấp hoặc thu hồi quyền của thành viên. Hệ thống tạo tệp qua tác vụ chạy nền và có log cùng bản sao lưu.

### 2.1. Phạm vi minh họa

| Trong phạm vi phân tích | Phụ thuộc hoặc phần cần mô hình bổ sung |
| --- | --- |
| API đọc hóa đơn, tạo và tra cứu công việc xuất, tải bản xuất | Cơ chế cấp, đổi và khôi phục thông tin xác thực |
| API quản lý quyền trong tenant | Quy trình kiểm tra danh tính ngoài phần giao tiếp của dịch vụ |
| Cơ sở dữ liệu hóa đơn và quyền | Mạng và hạ tầng chi tiết của từng môi trường |
| Hàng đợi, worker, tệp tạm và kho bản xuất | Cách nhà cung cấp quản lý nội bộ các dịch vụ lưu trữ |
| Log, sự kiện kiểm toán và sao lưu liên quan | Quy trình hỗ trợ khách hàng nếu chưa được khảo sát |
| Quy trình phục hồi và điều kiện mở lại nghiệp vụ | Tích hợp chưa có thông tin hoặc chưa được xác nhận |

Trong ví dụ, giả định API nhận bằng chứng danh tính từ cơ chế xác thực đã chọn. **Không giả định client tự khai danh tính hoặc tenant là đã đáng tin cậy.** Cách phát hành, xác minh và thu hồi bằng chứng đó phải được làm rõ bằng mô hình luồng xác thực riêng khi đặc tả toàn bộ hệ thống.

“Phụ thuộc” hoặc “ngoài phạm vi triển khai” không có nghĩa là bỏ khỏi phân tích. Vẫn phải ghi giao diện dữ liệu, trách nhiệm, giả định và hành vi khi phụ thuộc lỗi. Một hệ thống bên ngoài có thể giữ dữ liệu nhạy cảm hoặc quyết định tính đúng của luồng trong phạm vi.

### 2.2. Ghi rõ điều đã biết và điều chưa biết

Trước khi vẽ, ghi lại:

- Mục đích nghiệp vụ và các thao tác người dùng thực hiện.
- Tài sản, loại dữ liệu và chủ sở hữu cần bảo vệ.
- Thành phần do nhóm quản lý và thành phần do bên khác quản lý.
- Môi trường đang được mô hình hóa.
- Giả định, nguồn xác nhận và câu hỏi còn mở.
- Phiên bản hoặc thời điểm mà mô hình phản ánh.

Ví dụ, “worker dùng danh tính dịch vụ để đọc dữ liệu” khác với “worker chỉ được đọc dữ liệu của tenant trong công việc”. Câu thứ nhất chưa chứng minh câu thứ hai. Nếu chưa biết cơ chế giới hạn phạm vi, phải ghi là điểm cần xác minh.

## 3. Nhận diện các thành phần của sơ đồ luồng dữ liệu

**Data Flow Diagram — DFD** là sơ đồ thể hiện các thực thể, quá trình xử lý, kho dữ liệu và luồng dữ liệu giữa chúng.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Thực thể bên ngoài | Chủ thể hoặc hệ thống gửi, nhận dữ liệu ở ngoài phạm vi đang xét | Thành viên, quản trị viên, hệ thống danh tính |
| Quá trình xử lý | Hoạt động tiếp nhận, biến đổi, kiểm tra hoặc tạo dữ liệu | API hóa đơn, worker tạo bản xuất |
| Kho dữ liệu | Nơi giữ dữ liệu để dùng lại | Cơ sở dữ liệu, hàng đợi, kho tệp, log, bản sao lưu |
| Luồng dữ liệu | Dữ liệu đi từ nguồn đến đích | Yêu cầu xuất, danh sách hóa đơn, nội dung tệp, sự kiện |
| Ranh giới tin cậy | Nơi thay đổi giả định về danh tính, quyền hoặc mức kiểm soát | Client vào dịch vụ, dịch vụ vào kho dữ liệu, dữ liệu chuyển sang bên vận hành khác |

Một hàng đợi vừa là phương tiện giao tiếp vừa giữ thông điệp. Nếu việc lưu, đọc lại hoặc thử lại có ý nghĩa bảo mật, cần thể hiện nó như một kho dữ liệu hoặc mô tả rõ đặc tính lưu giữ.

### 3.1. Ranh giới tin cậy không chỉ là đường mạng

Có thể có ranh giới tin cậy giữa:

- Trình duyệt do người dùng kiểm soát và API.
- Hai tenant dùng chung một dịch vụ.
- Dịch vụ có quyền hạn chế và worker dùng danh tính có quyền rộng hơn.
- Ứng dụng và hệ thống log do một nhóm khác vận hành.
- Dữ liệu đang phục vụ và bản sao lưu truy cập qua quy trình phục hồi.
- Người dùng thường và tài khoản hỗ trợ hoặc quản trị.

Hai thành phần nằm cùng mạng nội bộ không tự động tin cậy mọi dữ liệu của nhau. Mã tenant đi qua mạng nội bộ vẫn có thể bắt nguồn từ đầu vào không đáng tin.

Ngược lại, một kết nối được bảo vệ khi truyền chỉ giải quyết một phần rủi ro. Nó không chứng minh người nhận có quyền nhận dữ liệu hoặc dữ liệu được phép lưu ở đích.

### 3.2. Phân biệt với các sơ đồ khác

DFD tập trung vào **dữ liệu và nơi dữ liệu đi qua**. Nó không tự thể hiện đầy đủ:

- Thứ tự, thời gian hoặc điều kiện rẽ nhánh như sơ đồ tuần tự.
- Cấu trúc triển khai vật lý và cấu hình mạng chi tiết.
- Mọi bước thực thi trong mã nguồn.
- Tính nguyên tử của cập nhật nghiệp vụ và ghi kiểm toán.

Khi thứ tự có ảnh hưởng đến bảo mật, bổ sung mô tả hoặc sơ đồ tuần tự. Khi vị trí triển khai làm thay đổi quyền hoặc chủ thể vận hành, bổ sung sơ đồ triển khai. Không cố nhồi tất cả thông tin vào một hình.

## 4. Quy trình nhận diện luồng dữ liệu

### Bước 1: Bắt đầu từ hành vi nghiệp vụ

Liệt kê các thao tác có ý nghĩa với người dùng hoặc vận hành:

- Đọc chi tiết và tìm kiếm hóa đơn.
- Tạo bản xuất, xem trạng thái, tải hoặc hủy bản xuất.
- Cấp và thu hồi quyền.
- Xử lý công việc chạy nền.
- Ghi và truy vấn sự kiện kiểm toán.
- Sao lưu, phục hồi và xử lý sự cố.

Với mỗi thao tác, lần theo từ điểm khởi phát tới kết quả cuối. Đừng dừng lại khi API đã trả phản hồi, vì tác vụ nền có thể tiếp tục xử lý dữ liệu sau đó.

### Bước 2: Tìm nguồn, nơi xử lý và nơi nhận

Hỏi lần lượt:

1. Dữ liệu bắt đầu từ đâu?
2. Thành phần nào tiếp nhận?
3. Thành phần đó kiểm tra hoặc biến đổi gì?
4. Có ghi vào kho nào không?
5. Thành phần hoặc chủ thể nào nhận kết quả?
6. Có đường phụ cho log, lỗi, thông báo hoặc sao lưu không?

Phải phân biệt **người khởi phát nghiệp vụ** với **danh tính thực thi kỹ thuật**. Người dùng A yêu cầu xuất không có nghĩa worker đang chạy bằng quyền của A. Worker có thể dùng danh tính dịch vụ rộng hơn; cơ chế giữ phạm vi quyền của A cần được chỉ rõ.

### Bước 3: Gọi tên dữ liệu bằng nội dung

Một mũi tên tên “HTTPS” chỉ cho biết cách truyền dự kiến. Một mũi tên tên “request” vẫn chưa cho biết dữ liệu cần bảo vệ.

Tên có ích hơn là:

- Yêu cầu tạo bản xuất: mã công việc, phạm vi hóa đơn, tham chiếu danh tính.
- Công việc xuất: mã công việc, tenant, người yêu cầu, bộ lọc.
- Dữ liệu hóa đơn: mã hóa đơn, thông tin khách hàng, số tiền.
- Tệp xuất: nội dung đã chọn và metadata sở hữu.
- Sự kiện kiểm toán: chủ thể, thao tác, tài nguyên, kết quả, thời điểm.

Tên luồng nên mô tả dữ liệu; giao thức, định dạng và cơ chế bảo vệ được ghi trong hồ sơ chi tiết. Nếu chưa biết, ghi “chưa xác nhận”, không tự biến dự kiến thiết kế thành thực tế.

### Bước 4: Theo dõi biến đổi và bản sao

Dữ liệu có thể đổi dạng hoặc được kết hợp:

| Dữ liệu đầu vào | Biến đổi hoặc bản sao | Điều cần xem xét |
| --- | --- | --- |
| Hóa đơn trong cơ sở dữ liệu | Tệp CSV hoặc bảng tính | Có xuất thừa trường hoặc thừa tenant không? |
| Tham chiếu tệp | Liên kết tải | Người có liên kết có được coi là có quyền tải không? |
| Yêu cầu có token | Log lỗi | Token có bị ghi lại không? |
| Dữ liệu nhiều hóa đơn | Báo cáo tổng hợp | Mức tổng hợp có còn làm lộ thông tin cần bảo vệ không? |
| Dữ liệu đang hoạt động | Bản sao lưu | Ai được phục hồi và quyền sau phục hồi được xác định thế nào? |
| Thông điệp công việc | Bản gửi lại hoặc hàng đợi lỗi | Có giữ dữ liệu lâu hơn hoặc bị người khác đọc không? |

Mã hóa, băm, thay định danh hoặc tổng hợp không tự động làm dữ liệu hết nhạy cảm. Cần đánh giá theo dữ liệu đầu vào, khả năng liên kết lại và quyền sử dụng kết quả.

### Bước 5: Xác định ranh giới và điểm kiểm soát

Với mỗi luồng, đánh dấu nơi thay đổi:

- Chủ thể kiểm soát dữ liệu.
- Danh tính thực thi.
- Quyền truy cập.
- Tenant hoặc phạm vi dữ liệu.
- Cơ chế lưu giữ và vận hành.
- Mức tin cậy dành cho đầu vào.

Sau đó đặt câu hỏi về yêu cầu bảo vệ. Chưa cần chọn ngay một công nghệ để giải quyết. Ví dụ, trước khi chọn cơ chế bảo vệ thông điệp, phải biết ai được tạo thông điệp, ai được đọc và trường nào quyết định phạm vi dữ liệu.

## 5. Minh họa luồng xuất hóa đơn

Sơ đồ dưới đây biểu diễn lát cắt tạo và tải bản xuất. Luồng đăng nhập, quản lý quyền, log và phục hồi cần được ghi bổ sung; chúng không biến mất chỉ vì hình tập trung vào nghiệp vụ chính.

~~~mermaid
flowchart LR
    U["Thành viên tenant"]
    subgraph Service["Phạm vi dịch vụ hóa đơn"]
        API["P1: API hóa đơn"]
        Q[("D1: Hàng đợi công việc")]
        W["P2: Worker tạo bản xuất"]
        DB[("D2: Hóa đơn, quyền, trạng thái công việc")]
        OBJ[("D3: Kho bản xuất")]
    end
    U -->|"F01: yêu cầu và bằng chứng danh tính"| API
    API -->|"A01: truy vấn quyền và công việc"| DB
    DB -->|"A02: dữ liệu quyền và công việc"| API
    API -->|"F02: lệnh xuất"| Q
    Q -->|"F03: công việc xuất"| W
    W -->|"F04: truy vấn phạm vi dữ liệu"| DB
    DB -->|"F05: dữ liệu hóa đơn và quyền"| W
    W -->|"F06: tệp xuất và metadata"| OBJ
    W -->|"F07: trạng thái và tham chiếu tệp"| DB
    API -->|"F08: yêu cầu đọc tệp"| OBJ
    OBJ -->|"F09: nội dung tệp"| API
    API -->|"F10: kết quả hoặc nội dung tải"| U
~~~

Khung “Phạm vi dịch vụ hóa đơn” thể hiện phạm vi phân tích, **không chứng minh các thành phần bên trong có cùng mức tin cậy**. Trong khung vẫn có ranh giới giữa API, worker, hàng đợi và kho dữ liệu, tùy danh tính cùng quyền của từng thành phần.

Hình minh họa chọn cách tải qua API. Nếu triển khai thực tế tải trực tiếp từ kho tệp, phải thay bằng luồng thực tế và phân tích quyền tại điểm tải đó.

### 5.1. Danh mục luồng nghiệp vụ

| Mã | Nguồn → đích | Dữ liệu chính | Câu hỏi bảo mật cần làm rõ |
| --- | --- | --- | --- |
| F01 | Thành viên → API | Yêu cầu, bộ lọc, mã tài nguyên, bằng chứng danh tính | Dữ liệu nào do client khai, danh tính được xác minh thế nào? |
| A01 | API → cơ sở dữ liệu | Truy vấn quyền và metadata công việc | Truy vấn có giới hạn đúng tenant và tài nguyên không? |
| A02 | Cơ sở dữ liệu → API | Quyền, trạng thái, chủ thể sở hữu công việc | API dùng dữ liệu nào để cho phép hoặc từ chối? |
| F02 | API → hàng đợi | Lệnh xuất và ngữ cảnh công việc | Chỉ bên nào được tạo lệnh hợp lệ? |
| F03 | Hàng đợi → worker | Thông điệp công việc | Worker dựa vào đâu để xác định phạm vi được phép? |
| F04 | Worker → cơ sở dữ liệu | Truy vấn hóa đơn và quyền | Danh tính dịch vụ có bị dùng để đọc vượt phạm vi không? |
| F05 | Cơ sở dữ liệu → worker | Hóa đơn và dữ liệu quyền cần thiết | Có lấy thừa trường hoặc thừa tenant không? |
| F06 | Worker → kho bản xuất | Nội dung tệp và metadata | Tệp có được gắn đúng tenant, người được cấp và thời hạn không? |
| F07 | Worker → cơ sở dữ liệu | Trạng thái và tham chiếu kết quả | Có thể gắn nhầm tệp cho công việc khác không? |
| F08 | API → kho bản xuất | Yêu cầu đọc một đối tượng | Đối tượng đích có được xác định từ mapping đáng tin cậy không? |
| F09 | Kho bản xuất → API | Nội dung tệp | Quyền đã được kiểm tra trước khi truyền nội dung chưa? |
| F10 | API → thành viên | Kết quả, trạng thái hoặc tệp | Có lộ dữ liệu, tham chiếu hoặc lỗi của tenant khác không? |

F01 và F10 là nhóm luồng ở hình tổng hợp. Khi lập hồ sơ chi tiết, tách thành các nhánh như **F01-CREATE**, **F01-STATUS**, **F01-DOWNLOAD** và phản hồi tương ứng. Chúng có dữ liệu, điều kiện quyền và kết quả khác nhau.

Nếu API phải tạo bản ghi công việc trước khi đẩy lệnh, bổ sung luồng ghi bản ghi đó. Nếu có thông điệp xác nhận, cache hoặc callback, cũng phải bổ sung. Sơ đồ là mô hình cần kiểm tra với thực tế, không phải căn cứ để phủ nhận luồng chưa vẽ.

### 5.2. Giữ nhất quán giữa mức tổng quan và mức chi tiết

Có thể bắt đầu bằng một quá trình duy nhất “hệ thống hóa đơn”, rồi phân rã thành API, worker và kho dữ liệu.

Khi phân rã, dữ liệu đi vào và đi ra ở mức tổng quan phải được giải thích ở mức chi tiết. Nếu mức tổng quan không có đối tác nhận dữ liệu nhưng mức chi tiết lại gửi dữ liệu cho nhà cung cấp bên ngoài, cần cập nhật lại phạm vi hoặc giải thích rõ phần bổ sung.

Sơ đồ càng chi tiết không có nghĩa càng đúng. Tách khi việc tách làm rõ dữ liệu, ranh giới, trách nhiệm hoặc yêu cầu bảo vệ. Không cần vẽ mọi hàm trong mã nguồn.

## 6. Viết hồ sơ cho từng luồng quan trọng

Mũi tên trên sơ đồ thường không đủ chỗ chứa điều kiện bảo mật. Với luồng qua ranh giới tin cậy hoặc chứa dữ liệu nhạy cảm, cần có hồ sơ chi tiết.

### 6.1. Mẫu hồ sơ luồng dữ liệu

| Thuộc tính | Nội dung cần ghi |
| --- | --- |
| Mã và tên | Định danh ổn định, khớp với sơ đồ và danh mục |
| Mục đích | Nghiệp vụ cần dữ liệu này để làm gì |
| Nguồn và đích | Thành phần gửi, nhận, môi trường và bên chịu trách nhiệm |
| Chủ thể | Người khởi phát, danh tính kỹ thuật gửi/nhận, phạm vi quyền |
| Nội dung | Trường dữ liệu, định dạng, kích thước hoặc khối lượng có ý nghĩa |
| Mức nhạy cảm | Dữ liệu cá nhân, nghiệp vụ, bí mật xác thực hoặc cấu hình cần bảo vệ |
| Căn cứ phạm vi | Cách xác định tenant, tài nguyên và thao tác được phép |
| Ranh giới | Điểm đổi mức tin cậy, quyền, chủ thể vận hành hoặc vùng lưu trữ |
| Cách truyền | Giao thức, cơ chế xác thực và bảo vệ khi truyền đã chọn |
| Xử lý và lưu giữ | Biến đổi, cache, tệp tạm, thời hạn và bản sao phát sinh |
| Lỗi và thử lại | Timeout, gửi lại, trùng lặp, hàng đợi lỗi, dữ liệu sai |
| Yêu cầu liên quan | Nghĩa vụ bảo vệ được rút ra từ rủi ro của luồng |
| Kiểm chứng | Bằng chứng cần có để xác nhận mô tả và yêu cầu |
| Điểm chưa rõ | Giả định, người cần xác nhận và ảnh hưởng nếu giả định sai |

Không cần ghi giá trị bí mật thật vào hồ sơ. Ví dụ schema nên dùng dữ liệu giả và mô tả loại bí mật thay vì sao chép token đang hoạt động.

### 6.2. Hồ sơ minh họa cho F03: hàng đợi gửi công việc tới worker

**Mục đích:** chuyển yêu cầu xuất đã được hệ thống tiếp nhận sang tác vụ nền.

**Nguồn và đích:** hàng đợi D1 gửi thông điệp tới worker P2. Nhóm vận hành phải xác nhận những danh tính nào được ghi, đọc và quản trị hàng đợi.

**Chủ thể:** thành viên là người yêu cầu nghiệp vụ; worker sử dụng danh tính dịch vụ để xử lý. Quyền kỹ thuật của worker không thay thế quyền nghiệp vụ của người yêu cầu.

**Nội dung dự kiến:**

~~~json
{
  "jobId": "job-example-01",
  "tenantId": "tenant-example-a",
  "requesterId": "user-example-07",
  "filterRef": "filter-example-02",
  "schemaVersion": 1,
  "correlationId": "corr-example-09"
}
~~~

Các trường đều là dữ liệu giả. Thông điệp chỉ mang tham chiếu cần thiết, không mang toàn bộ hóa đơn hoặc token truy cập của người dùng trong thiết kế minh họa này.

Việc không mang toàn bộ hóa đơn giúp giảm dữ liệu lưu trong hàng đợi, nhưng không loại bỏ rủi ro. Các định danh vẫn có thể tiết lộ thông tin, và thông điệp vẫn có thể bị tạo sai hoặc bị phát lại.

**Căn cứ xác định quyền:** worker đối chiếu công việc với bản ghi có thẩm quyền trong hệ thống. Không chỉ đọc một trường tenant từ thông điệp rồi coi đó là bằng chứng cho phép truy cập. Cần đối chiếu chủ thể, tenant, bộ lọc và chính sách quyền tại mốc đã đặc tả.

**Giả định chính sách trong ví dụ:** quyền xuất được kiểm tra khi tiếp nhận yêu cầu, khi worker bắt đầu xử lý và khi người dùng tải tệp. Quy tắc cho quyền bị thu hồi trong lúc worker đang chạy phải được làm rõ riêng; không suy ra rằng ba mốc trên tự động xử lý mọi thay đổi đồng thời.

**Ranh giới tin cậy:** từ một thông điệp được lưu và chuyển tiếp sang quá trình dùng danh tính dịch vụ để đọc dữ liệu. Đây là nơi đầu vào có thể làm một thành phần có quyền rộng thực hiện hành động ngoài ý định.

**Lỗi và thử lại:** nếu cơ chế hàng đợi có thể phát lại, worker phải xử lý theo chính sách công việc đã chọn. Cần biết có tạo nhiều tệp, ghi đè kết quả hoặc giữ tệp lỗi không. Thông điệp sai cấu trúc phải được xử lý mà không làm lộ dữ liệu qua thông báo lỗi.

**Bản sao:** thông điệp có thể tồn tại trong hàng đợi, bản gửi lại, hàng đợi lỗi và công cụ quan sát. Cần xác định thời hạn lưu, người được đọc và cách loại bỏ.

**Kiểm chứng dự kiến:** thử công việc hợp lệ, thông điệp bị sửa tenant, tham chiếu công việc không tồn tại, quyền đã thu hồi, thông điệp trùng và lỗi đọc dữ liệu. Quan sát cả dữ liệu mà worker đọc và tệp thực tế được tạo.

Chỉ thấy worker “xử lý thành công thông điệp” chưa chứng minh nó đọc đúng dữ liệu.

## 7. Tìm những luồng thường bị bỏ sót

### 7.1. Log, dấu vết và dữ liệu chẩn đoán

Bổ sung ít nhất:

| Mã | Nguồn → đích | Nội dung cần khảo sát |
| --- | --- | --- |
| L01 | API → hệ thống log/kiểm toán | Chủ thể, thao tác, tài nguyên, kết quả, mã tương quan |
| L02 | Worker → hệ thống log/kiểm toán | Công việc, phạm vi xử lý, lỗi, trạng thái hoàn tất |
| L03 | Hệ thống log → công cụ truy vấn hoặc bên hỗ trợ | Trường được hiển thị, tải xuống hoặc chia sẻ |

Log là một đích nhận dữ liệu, không chỉ là chức năng phụ của mã nguồn. Dữ liệu có thể tiếp tục được sao chép tới nơi tìm kiếm, kho lưu dài hạn hoặc báo cáo hỗ trợ.

Cần hỏi:

- Có ghi header, token, tham số truy vấn hoặc toàn bộ nội dung yêu cầu không?
- Ngoại lệ có chứa bản ghi hóa đơn hoặc nội dung tệp không?
- Middleware và công cụ thu lỗi có quy tắc lọc riêng không?
- Nhân sự xem log có quyền xem dữ liệu nghiệp vụ tương ứng không?
- Bộ đệm gửi log có lưu dữ liệu trên đĩa không?

### 7.2. Tệp tạm, cache và kết quả tải xuống

Worker có thể tạo tệp trên đĩa trước khi gửi vào kho bản xuất. Tệp tạm là một kho dữ liệu cần được mô hình hóa nếu có dữ liệu nhạy cảm.

Cần kiểm tra tệp còn lại khi thành công, khi tác vụ lỗi hoặc khi tiến trình bị dừng. Quyền đọc thư mục tạm và cơ chế dọn tệp không nên bị bỏ qua chỉ vì tệp được gọi là “tạm”.

Cache có thể giữ nội dung hóa đơn, metadata công việc hoặc quyền. Phải biết khóa cache có phân biệt tenant không, dữ liệu cũ tồn tại bao lâu và việc thu hồi quyền tác động ra sao.

Tệp đã tải về thiết bị người dùng là một bản sao khác. Chặn tải ở máy chủ hoặc xóa bản xuất không tự xóa được bản mà người dùng đã lưu. Nếu nghiệp vụ yêu cầu kiểm soát sau tải, phải đánh giá khả năng thực hiện và ghi rõ giới hạn.

### 7.3. Thử lại, hàng đợi lỗi và kênh xử lý thủ công

Đường thất bại có thể tạo thêm:

- Bản thông điệp trong hàng đợi lỗi.
- Nội dung yêu cầu trong hệ thống theo dõi sự cố.
- Tệp chưa hoàn chỉnh trong kho tạm.
- Bản xuất trùng khi công việc được chạy lại.
- Dữ liệu được nhân sự vận hành tải xuống để phân tích.

Một luồng thành công không đại diện cho các luồng này. Cần mô tả ai được xem dữ liệu lỗi, ai được chạy lại và quyền của người yêu cầu có được đánh giá lại không.

### 7.4. Quản lý quyền và danh tính

Bổ sung các luồng quản trị như:

- Quản trị viên gửi yêu cầu cấp hoặc thu hồi quyền tới API.
- API ghi thay đổi vào nơi lưu quyền.
- Thay đổi được truyền tới cache hoặc các điểm quyết định quyền.
- Kết quả được trả cho quản trị viên và ghi vào kiểm toán.

Trong mô hình xác thực riêng, khảo sát việc cấp, đổi, thu hồi phiên, xác thực bổ sung và khôi phục tài khoản. Với mỗi luồng, xác định dữ liệu xác thực có đi qua dịch vụ hóa đơn không, hay chỉ qua bên cung cấp danh tính.

Không vẽ mật khẩu đi qua ứng dụng nếu cơ chế thực tế không làm như vậy. Cũng không bỏ qua dữ liệu phiên chỉ vì mật khẩu được xử lý bên ngoài.

### 7.5. Sao lưu và phục hồi

Đối với dữ liệu hóa đơn và quyền, ít nhất cần thể hiện:

| Mã | Nguồn → đích | Dữ liệu |
| --- | --- | --- |
| B01 | Kho dữ liệu → quá trình sao lưu | Dữ liệu được chọn cùng metadata cần thiết |
| B02 | Quá trình sao lưu → kho sao lưu | Bản sao lưu và thông tin nhận diện điểm dữ liệu |
| B03 | Kho sao lưu → quá trình phục hồi | Dữ liệu dùng cho một lần phục hồi |
| B04 | Quá trình phục hồi → kho dữ liệu phục vụ | Dữ liệu đã khôi phục và được xác minh |

Tách quá trình xử lý khỏi kho sao lưu giúp làm rõ ai đọc, biến đổi, ghi và xác minh dữ liệu.

Cần hỏi thêm: bản xuất có được sao lưu không; khóa cần thiết có sẵn khi phục hồi không; dữ liệu phục hồi được đưa vào môi trường nào; ai được kích hoạt quy trình; và quyền đã thu hồi sau điểm sao lưu được xử lý thế nào.

Không mở lại nghiệp vụ nhạy cảm chỉ vì dữ liệu đã đọc được. Trạng thái quyền và điều kiện bảo vệ sau phục hồi cũng phải đáng tin cậy.

## 8. Theo dõi vòng đời dữ liệu qua các luồng

Một danh mục luồng cho biết dữ liệu di chuyển; vòng đời dữ liệu giúp biết nó tồn tại bao lâu và ở những dạng nào.

Với bản xuất hóa đơn, có thể theo dõi:

| Giai đoạn | Vị trí hoặc dạng dữ liệu | Câu hỏi cần trả lời |
| --- | --- | --- |
| Tiếp nhận | Bộ lọc và thông tin công việc | Có cần lưu toàn bộ đầu vào không? |
| Chờ xử lý | Thông điệp trong hàng đợi | Thông điệp hết hạn thế nào, ai được đọc? |
| Xử lý | Dữ liệu trong bộ nhớ hoặc tệp tạm | Khi tác vụ bị dừng, bản sao nào còn lại? |
| Lưu kết quả | Tệp và metadata trong kho bản xuất | Tenant, chủ thể và thời điểm hết hạn được gắn thế nào? |
| Sử dụng | Nội dung truyền qua API hoặc tải về thiết bị | Quyền được kiểm tra lúc nào, có cache trung gian không? |
| Chẩn đoán | Log và dấu vết công việc | Có chứa nội dung hoặc bí mật không? |
| Hết hạn | Tệp không còn được phép tải | Chặn truy cập và xóa vật lý có cùng thời điểm không? |
| Xóa hoặc lưu theo chính sách | Bản hiện hành, phiên bản cũ, bản sao lưu | Phạm vi xóa là gì, bản sao nào còn được giữ và vì sao? |

**Không còn truy cập được** và **đã loại bỏ dữ liệu khỏi mọi bản sao trong phạm vi** là hai điều khác nhau. Một hệ thống có thể chặn tải ngay khi hết hạn nhưng dọn tệp sau đó. Nếu kho hỗ trợ nhiều phiên bản, xóa bản hiện hành có thể không loại bỏ phiên bản cũ.

Chính sách lưu giữ phải xác định phạm vi cho dữ liệu gốc, bản xuất, log và sao lưu. Không mặc định mọi bản sao có cùng thời hạn hoặc đều xóa được đồng thời.

Cũng cần theo dõi dữ liệu dẫn xuất. Một tệp chỉ còn mã khách hàng vẫn có thể liên kết tới người cụ thể qua dữ liệu khác. Việc đổi định dạng hoặc bỏ một số trường không đủ để tự kết luận dữ liệu không còn cần bảo vệ.

## 9. Từ data flow đến rủi ro, yêu cầu và kiểm thử

Data flow chỉ ra nơi đặt câu hỏi; nó không tự sinh ra kết luận rằng một luồng đang có lỗ hổng. Cần phân biệt:

1. **Điều đã mô tả:** dữ liệu đi qua các thành phần nào.
2. **Tình huống đe dọa:** điều gì có thể làm dữ liệu bị lộ, bị sửa hoặc không còn sẵn sàng.
3. **Điểm yếu đã xác nhận:** cơ chế hiện có thực sự thiếu hoặc sai ở đâu.
4. **Yêu cầu:** hệ thống phải bảo vệ thế nào.
5. **Bằng chứng:** quan sát nào đủ để kiểm chứng nghĩa vụ đó.

Ví dụ, việc worker dùng danh tính dịch vụ rộng là một yếu tố cần phân tích. Chưa thể kết luận có truy cập trái phép nếu đã tồn tại cơ chế giới hạn phạm vi đúng và được kiểm chứng.

### 9.1. Bảng chuyển đổi minh họa

| Luồng | Rủi ro cần xem xét | Yêu cầu bảo vệ | Cách kiểm chứng |
| --- | --- | --- | --- |
| F01, A01, A02 | Client thay mã tài nguyên hoặc tenant để đọc dữ liệu ngoài quyền | SR-DF-01: xác minh danh tính và kiểm tra quyền trên tài nguyên đích ở phía dịch vụ | Dùng tài khoản tenant A gọi trực tiếp tài nguyên tenant B; đối chứng bằng truy cập hợp lệ |
| F02–F05 | Thông điệp khiến worker đọc dữ liệu vượt phạm vi | SR-DF-02: đối chiếu công việc với dữ liệu có thẩm quyền và giới hạn truy vấn theo chính sách quyền | Sửa các trường trong thông điệp, thử quyền đã thu hồi; kiểm tra dữ liệu đọc và tệp tạo |
| F06–F10 | Truy cập bản xuất của người khác hoặc tải sau khi mất quyền | SR-DF-03: kiểm tra quyền đối với bản xuất trước khi truyền nội dung theo mốc chính sách | Đổi mã công việc, tenant, tham chiếu tệp; dùng phiên cũ sau thu hồi |
| L01–L03 | Bí mật hoặc nội dung nghiệp vụ bị lộ qua log | SR-DF-04: chỉ ghi các trường được phép, loại trừ token và nội dung bị cấm | Dùng dữ liệu giả có dấu nhận diện; kiểm tra cả nhánh lỗi và các nơi nhận log |
| F06 và các bản sao liên quan | Tệp vẫn tải được hoặc còn giữ quá hạn | SR-DF-05: chặn tải tại thời điểm hết hạn và dọn bản sao theo thời hạn đã đặc tả | Thử tải ở hai phía mốc hết hạn; kiểm tra trạng thái các bản sao trong phạm vi |
| B01–B04 | Phục hồi thiếu dữ liệu hoặc mở lại quyền đã thu hồi | SR-DF-06: xác minh dữ liệu, cấu hình và trạng thái quyền trước khi mở nghiệp vụ nhạy cảm | Diễn tập phục hồi, đối chiếu dữ liệu và thử tài khoản bị thu hồi quyền sau điểm sao lưu |

Các mã là ví dụ trong bài. Khi dùng trong dự án, cần định nghĩa đầy đủ phạm vi và tiêu chí chấp nhận cho từng yêu cầu.

### 9.2. Viết một yêu cầu có ranh giới đo rõ ràng

Giả sử chủ sở hữu nghiệp vụ đã chọn chính sách minh họa: bản xuất được tải trong 24 giờ, sau đó phải bị chặn; việc dọn bản sao thuộc kho bản xuất hoàn tất trong tối đa một giờ tiếp theo.

Có thể viết:

> **SR-DF-05:** Mỗi bản xuất phải có thời điểm hết hạn bằng thời điểm tạo thành công cộng 24 giờ. Mọi yêu cầu tải bắt đầu từ thời điểm hết hạn phải bị từ chối trước khi truyền nội dung. Trong tối đa một giờ từ mốc hết hạn, hệ thống phải loại bỏ tệp và các phiên bản thuộc phạm vi kho bản xuất đã xác định. Tệp tạm và bản sao lưu được quản lý theo chính sách riêng có liên kết trong hồ sơ luồng.

Các giá trị là **giả định học tập**, không phải khuyến nghị mặc định.

Kế hoạch kiểm chứng phải xác định nguồn thời gian, sai lệch cho phép, các điểm tải và phạm vi phiên bản. Cần làm rõ yêu cầu tải đã bắt đầu trước mốc hết hạn có được hoàn tất hay phải dừng. Nếu thiết kế không xóa được một loại bản sao trong thời hạn, phải ghi khoảng trống và xử lý yêu cầu tương ứng.

Ví dụ này cho thấy một yêu cầu cần gắn với cả luồng đọc lẫn vòng đời lưu giữ. Chỉ kiểm tra rằng giao diện đã ẩn nút tải không chứng minh yêu cầu được đáp ứng.

### 9.3. Không chọn cơ chế trước khi hiểu nghĩa vụ

“Mã hóa tất cả” chưa trả lời:

- Ai được nhận dữ liệu sau giải mã?
- Thành phần nào có quyền dùng khóa?
- Dữ liệu có được xuất đúng tenant không?
- Bản sao trong log hoặc tệp tạm có nằm trong phạm vi bảo vệ không?
- Khóa có còn dùng được khi phục hồi không?

Tương tự, “đặt mọi thứ trong mạng nội bộ” không thay thế việc xác định danh tính, quyền và dữ liệu được phép qua từng luồng.

Data flow giúp chọn đúng nơi áp dụng cơ chế. Sau khi có yêu cầu, thiết kế mới giải thích cơ chế nào đáp ứng và bằng chứng nào chứng minh điều đó.

## 10. Xác nhận mô hình với thực tế

Một mô hình có thể phản ánh thiết kế dự kiến, hiện thực đang chạy hoặc phương án tương lai. Phải ghi rõ đang mô tả loại nào.

Trong một dự án thực tế, có thể đối chiếu mô hình với:

- Luồng nghiệp vụ và hợp đồng API.
- Cấu hình quyền của dịch vụ, hàng đợi và kho dữ liệu.
- Đường đọc, ghi dữ liệu trong hiện thực.
- Cấu hình log, công cụ thu lỗi và cơ chế sao lưu.
- Thông tin quan sát từ một yêu cầu thử nghiệm.
- Xác nhận của người vận hành hoặc bên quản lý phụ thuộc.

Việc thu thập bằng chứng phải tránh sao chép bí mật và dữ liệu thật không cần thiết vào tài liệu. Có thể dùng yêu cầu thử với dữ liệu giả, mã tương quan và quan sát đã lọc dữ liệu.

### 10.1. Đi qua một tình huống từ đầu đến cuối

Với chức năng xuất, lần theo một công việc:

1. API nhận trường gì và xác định người yêu cầu ra sao?
2. Công việc được ghi ở đâu trước khi gửi?
3. Thông điệp chứa những trường nào?
4. Worker lấy quyền và bộ lọc từ nguồn nào?
5. Dữ liệu được đọc, biến đổi và lưu vào những đâu?
6. Trạng thái công việc liên kết với tệp thế nào?
7. Người tải đi qua điểm kiểm tra quyền nào?
8. Log, tệp tạm và thông điệp lỗi còn lại ở đâu?
9. Sau hết hạn hoặc thu hồi quyền, các đường truy cập thay đổi thế nào?

Thực hiện thêm tình huống lỗi, vì đường thành công không cho thấy mọi bản sao. Ví dụ, dừng worker sau khi ghi tệp nhưng trước khi cập nhật trạng thái có thể làm lộ một tệp không còn được theo dõi đầy đủ.

### 10.2. Các dấu hiệu mô hình còn thiếu

| Dấu hiệu | Khoảng trống có thể tồn tại |
| --- | --- |
| Có bên nhận dữ liệu nhưng không có luồng đầu ra | Thiếu tích hợp hoặc đường chia sẻ |
| Mọi mũi tên đều tên “request/response” | Chưa xác định nội dung và mức nhạy cảm |
| Worker có quyền rộng nhưng không có ngữ cảnh nghiệp vụ | Chưa rõ cách giới hạn tenant và người yêu cầu |
| Có log nhưng không có chủ thể đọc log | Bỏ sót đường dữ liệu rời hệ thống quan sát |
| Có bản sao lưu nhưng không có luồng phục hồi | Chưa xét ai khôi phục, khôi phục vào đâu và quyền sau đó |
| Có tệp nhưng không có thời hạn hoặc quy trình dọn | Bỏ sót vòng đời dữ liệu |
| Sơ đồ chỉ có API được gọi qua giao diện | Có thể bỏ sót endpoint nội bộ hoặc cách gọi trực tiếp |
| Gộp yêu cầu và phản hồi thành một mũi tên không chú giải | Có thể bỏ sót dữ liệu nhạy cảm chỉ xuất hiện ở một chiều |
| Mọi thành phần trong cùng một khung đều được coi là tin cậy | Đã bỏ qua ranh giới quyền hoặc tenant bên trong |

Các dấu hiệu là câu hỏi cần điều tra, không tự chứng minh hệ thống có điểm yếu.

## 11. Duy trì data flow khi hệ thống thay đổi

Mô hình cần được xem lại khi:

- Thêm API, tác vụ nền, kênh xuất hoặc nhà cung cấp.
- Thêm trường nhạy cảm vào dữ liệu hoặc thông điệp.
- Đổi danh tính dịch vụ và phạm vi quyền.
- Chuyển từ tải qua API sang tải trực tiếp từ kho.
- Thêm cache, công cụ quan sát hoặc hàng đợi lỗi.
- Thay đổi thời hạn lưu, cách sao lưu hoặc môi trường phục hồi.
- Chuyển dữ liệu cho nhóm vận hành hoặc bên nhận mới.

Một thay đổi nhỏ về trải nghiệm có thể tạo đường dữ liệu mới. Ví dụ, “gửi liên kết tải qua thông báo” thêm nơi lưu liên kết và thêm bên nhận; nếu liên kết mang quyền truy cập theo người nắm giữ, cần phân tích lại cơ chế bảo vệ.

Bộ đầu ra đủ để tiếp tục đặc tả bảo mật nên gồm:

- Phạm vi, tài sản, chủ sở hữu và các giả định đã ghi rõ.
- Sơ đồ có thành phần, luồng dữ liệu và ranh giới quan trọng.
- Danh mục luồng khớp với sơ đồ.
- Hồ sơ chi tiết cho luồng nhạy cảm hoặc qua ranh giới tin cậy.
- Danh sách bản sao, điểm lưu và vòng đời dữ liệu.
- Câu hỏi còn mở cùng người chịu trách nhiệm xác nhận.
- Liên kết từ luồng tới rủi ro, yêu cầu và cách kiểm chứng.

Mô hình có ích khi người đọc lần được đường đi của một loại dữ liệu, giải thích được ai được tác động ở mỗi điểm và biết cần kiểm chứng điều gì trước khi chấp nhận thiết kế.
