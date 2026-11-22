# OCID, service endpoint và vòng đời tài nguyên

Khi làm việc với Oracle Cloud Infrastructure (OCI), ba câu hỏi xuất hiện trong hầu hết thao tác: **đang nói đến tài nguyên nào**, **gửi yêu cầu đến đâu** và **tài nguyên đã sẵn sàng để làm gì**. OCID, service endpoint và vòng đời tài nguyên lần lượt giúp trả lời các câu hỏi đó.

Ba khái niệm liên quan chặt chẽ nhưng không thay thế nhau. Có OCID đúng chưa có nghĩa là tài khoản được phép truy cập. Gửi yêu cầu tới endpoint đúng chưa bảo đảm tài nguyên nằm trong region đó. Nhận phản hồi tạo tài nguyên thành công cũng chưa có nghĩa ứng dụng bên trong đã phục vụ người dùng.

Bài học này xây dựng cách đọc và kiểm tra thông tin tài nguyên OCI trước khi đi sâu vào IAM, VCN, Compute, lưu trữ và các dịch vụ cơ sở dữ liệu Oracle.

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

- Phân biệt OCID, tên hiển thị, compartment và địa chỉ truy cập dịch vụ.
- Giải thích những thành phần chính thường thấy trong OCID.
- Chọn đúng ngữ cảnh region, realm và endpoint khi gọi API.
- Phân biệt trạng thái hạ tầng với trạng thái sẵn sàng của ứng dụng.
- Xử lý đúng yêu cầu bất đồng bộ, work request và việc đọc trạng thái.
- Tránh tạo trùng hoặc xóa nhầm tài nguyên khi tự động hóa.
- Lưu đủ thông tin để vận hành, điều tra lỗi và kiểm soát chi phí.

## 2. Nhận diện một tài nguyên OCI

### 2.1. OCID là gì?

OCID là viết tắt của **Oracle Cloud Identifier**, định danh duy nhất do OCI cấp cho các tài nguyên sử dụng cơ chế định danh này.

Ví dụ, khi tạo một Compute instance, tài nguyên được cấp một OCID. Các lời gọi API lấy thông tin, thao tác trạng thái hoặc chấm dứt instance thường dùng OCID để chỉ rõ đối tượng.

Không nên giả định mọi đối tượng con trong mọi dịch vụ đều có OCID riêng. Một số API định vị đối tượng bằng tên, đường dẫn hoặc tổ hợp khóa. Trong Object Storage, chẳng hạn, các thao tác với object thường sử dụng namespace, tên bucket và tên object thay vì một OCID của từng object.

Điểm cần nhớ là: dùng đúng kiểu định danh mà API của tài nguyên yêu cầu, không cố biến mọi tên hoặc đường dẫn thành OCID.

### 2.2. OCID khác tên hiển thị

Tên hiển thị phục vụ con người. OCID phục vụ việc tham chiếu chính xác tới tài nguyên.

| Thuộc tính | Tên hiển thị | OCID |
| --- | --- | --- |
| Mục đích | Dễ đọc, dễ tìm trong Console | Xác định tài nguyên cụ thể |
| Do ai quyết định | Thường do người dùng hoặc công cụ đặt | Do OCI cấp |
| Có bảo đảm duy nhất trên toàn hệ thống không | Không | Có, đối với định danh OCID |
| Có thể dựa vào để phân biệt hai tài nguyên cùng tên không | Không | Có |
| Phù hợp làm tham chiếu trực tiếp trong nhiều API tài nguyên | Chỉ khi API cho phép tra bằng tên | Có, khi API yêu cầu OCID |
| Thay đổi khi đổi tên tài nguyên | Tên thay đổi nếu dịch vụ hỗ trợ | OCID của cùng tài nguyên không đổi |

Hai instance ở hai compartment có thể cùng mang tên **app-prod-01** nhưng có hai OCID khác nhau. Một instance mới được tạo để thay thế instance cũ cũng có OCID mới, kể cả khi bạn đặt lại cùng tên.

Vì vậy, một script tự động tìm theo tên rồi chọn kết quả đầu tiên có nguy cơ thao tác sai tài nguyên. Nếu phải tra theo tên, cần thêm các điều kiện như compartment, region, tag và trạng thái, đồng thời xử lý rõ trường hợp có nhiều kết quả.

### 2.3. Compartment OCID và resource OCID không cùng vai trò

Một lệnh tạo tài nguyên thường cần **compartment OCID** để xác định nơi đặt tài nguyên. Lệnh lấy hoặc cập nhật một tài nguyên cụ thể thường cần **resource OCID** của chính tài nguyên đó.

Ví dụ:

~~~text
compartment-id : tài nguyên thuộc phạm vi quản trị nào?
instance-id    : thao tác trên Compute instance cụ thể nào?
subnet-id      : đặt VNIC vào subnet cụ thể nào?
~~~

Không thể dùng OCID của VCN vào trường subnet ID chỉ vì subnet nằm trong VCN đó. Tương tự, tenancy OCID không thay cho OCID của instance.

Tenancy đóng vai trò compartment gốc trong những ngữ cảnh API phù hợp, nhưng điều đó không có nghĩa có thể dùng tenancy OCID cho mọi tham số có đuôi “id”.

## 3. Đọc OCID đúng mức

### 3.1. Cấu trúc khái quát

Dạng khái quát được dùng để giải thích cấu trúc OCID là:

~~~text
ocid1.<RESOURCE_TYPE>.<REALM>.[REGION][.FUTURE_USE].<UNIQUE_ID>
~~~

Trong biểu diễn này, dấu ngoặc vuông mô tả phần có thể không hiện diện hoặc không có giá trị trong một số dạng OCID; không phải ký tự để chép vào yêu cầu API.

| Thành phần | Ý nghĩa |
| --- | --- |
| ocid1 | Dấu hiệu của định dạng OCID |
| RESOURCE_TYPE | Loại tài nguyên, chẳng hạn instance, vcn hoặc compartment |
| REALM | Miền triển khai cloud mà tài nguyên thuộc về |
| REGION | Thông tin vùng nếu loại OCID đó có sử dụng |
| FUTURE_USE | Phần dự phòng theo cấu trúc định danh |
| UNIQUE_ID | Phần do hệ thống tạo để bảo đảm tính duy nhất |

Đây không phải một quy tắc để người dùng tự tạo OCID. Khi làm việc thực tế, hãy sao chép OCID đầy đủ từ Console, phản hồi API hoặc đầu ra của công cụ triển khai.

Trong tài liệu và ví dụ chia sẻ, có thể biểu diễn như sau:

~~~text
OCID instance đã che bớt:
ocid1.instance.<realm>.<region>.<phần-định-danh-đã-che>
~~~

Chuỗi trên chỉ là minh họa khái niệm, không phải OCID hợp lệ để gọi API.

### 3.2. Không suy luận quá nhiều từ chuỗi OCID

Một số phần trong OCID giúp nhận ra loại tài nguyên hoặc ngữ cảnh triển khai. Tuy nhiên, không nên phân tích chuỗi để suy ra mọi thông tin vận hành.

OCID không phải nguồn đáng tin cậy để tự suy ra:

- Tên hiển thị hiện tại.
- Compartment hiện tại.
- Trạng thái chạy hoặc dừng.
- Địa chỉ IP hay hostname để kết nối.
- Chủ sở hữu nghiệp vụ.
- Chính sách IAM đang có hiệu lực.
- Mức sử dụng hoặc chi phí.

Muốn biết các thông tin đó, cần gọi API tương ứng hoặc đọc cấu hình và hệ thống quản lý phù hợp.

Không nên tách OCID theo dấu chấm rồi gắn ý nghĩa cố định cho mọi vị trí trên tất cả dịch vụ. Những phần có thể trống, khác dạng hoặc không có thông tin region cần được xử lý theo tài liệu của dịch vụ và công cụ chính thức.

Đặc biệt, phần region trong OCID không phải một hợp đồng để tự ghép URL. Cách an toàn hơn là cấu hình region cho SDK/CLI và để cơ chế phân giải endpoint của công cụ thực hiện phần việc được hỗ trợ.

### 3.3. Định danh ổn định trong vòng đời của cùng tài nguyên

Nếu vẫn là cùng tài nguyên, các thay đổi như đổi tên hoặc dừng rồi khởi động lại instance không tạo ra một OCID mới cho instance đó.

Khi một tài nguyên được hủy và một tài nguyên thay thế được tạo, đối tượng mới có định danh mới. Tên cũ, tag cũ hoặc cùng một vai trò nghiệp vụ không làm cho nó trở thành tài nguyên cũ.

Với những loại tài nguyên hỗ trợ chuyển compartment, việc chuyển là thay đổi vị trí quản trị của cùng tài nguyên, không nên bị hiểu nhầm là tạo lại nó. Tuy nhiên, cần xác minh tính năng chuyển, các điều kiện và tác động IAM của đúng dịch vụ.

Điều này quan trọng khi quản lý:

- Output và state của công cụ IaC.
- Cấu hình ứng dụng hoặc automation tham chiếu OCID.
- Dashboard, alarm và bộ lọc log gắn với tài nguyên.
- Allowlist hoặc cấu hình tích hợp có lưu định danh.
- Quy trình thay thế tài nguyên trong region dự phòng.

### 3.4. OCID không phải thông tin xác thực

Biết OCID không có nghĩa được cấp quyền sử dụng tài nguyên. Yêu cầu vẫn cần danh tính hợp lệ và quyền IAM phù hợp; đường mạng đến endpoint cũng phải hoạt động.

Tuy vậy, OCID có thể tiết lộ loại tài nguyên và cấu trúc hạ tầng. Nên quản lý việc chia sẻ log, ảnh chụp màn hình và dữ liệu cấu hình theo quy định của tổ chức.

Cần phân biệt rõ:

| Thông tin | Vai trò |
| --- | --- |
| Resource OCID | Định danh tài nguyên |
| User hoặc principal | Danh tính gửi yêu cầu |
| API signing key, token hoặc thông tin xác thực tương ứng | Chứng minh danh tính theo cơ chế xác thực |
| IAM policy | Quy định quyền được thực hiện |
| Endpoint | Địa chỉ nhận yêu cầu dịch vụ |

Không đưa private key hoặc token vào ví dụ chỉ để chứng minh rằng một OCID có thể truy cập được.

## 4. Service endpoint: gửi yêu cầu đến đâu?

### 4.1. Endpoint là địa chỉ của giao diện dịch vụ

Service endpoint là địa chỉ mạng để client giao tiếp với một dịch vụ. Với API HTTPS, endpoint thường gồm scheme và hostname; yêu cầu cụ thể bổ sung đường dẫn, tham số và header.

Một cách hình dung:

~~~text
https://<hostname-dịch-vụ>/<đường-dẫn-API>/<định-danh-hoặc-tài-nguyên>
        ________________/ _____________________________________/
           nơi gửi đến             thao tác/đối tượng cụ thể
~~~

Trong realm thương mại, một mẫu endpoint thường gặp của nhóm API hạ tầng là:

~~~text
https://iaas.<region>.oraclecloud.com
~~~

Đây là mẫu minh họa, không phải một URL hoàn chỉnh khi còn ký hiệu <region>. Không áp dụng hậu tố miền này cho mọi realm hoặc mọi dịch vụ.

Một OCID nằm trong tham số của yêu cầu không thay thế endpoint. Ngược lại, endpoint của Compute không tự chỉ ra instance nào mà người dùng muốn lấy thông tin.

### 4.2. Region và realm là hai lớp khác nhau

**Region** là một khu vực triển khai của OCI. Nhiều tài nguyên như VCN và Compute instance gắn với một region cụ thể.

**Realm** là miền cloud gồm một tập region và các ranh giới triển khai tương ứng. Không nên giả định mọi realm dùng cùng hậu tố DNS hoặc có cùng khả năng truy cập dịch vụ.

Để gửi yêu cầu đúng, thường cần biết:

1. Danh tính và tenancy dùng để xác thực.
2. Region của tài nguyên hoặc region mà thao tác dịch vụ yêu cầu.
3. Dịch vụ và loại API cần gọi.
4. Cơ chế phân giải endpoint phù hợp với realm và môi trường.
5. Chính sách IAM và khả năng kết nối đến endpoint.

Một số tài nguyên hoặc thao tác IAM có phạm vi và quy tắc region riêng, bao gồm vai trò của home region. Vì vậy, không áp dụng máy móc mô hình endpoint regional của Compute cho mọi thao tác quản trị danh tính.

OCID không có phần region cũng không có nghĩa có thể gọi bất kỳ endpoint nào tùy ý.

### 4.3. Endpoint API khác địa chỉ ứng dụng

Một instance có thể liên quan đến nhiều địa chỉ khác nhau:

| Địa chỉ hoặc định danh | Dùng để làm gì |
| --- | --- |
| OCID instance | Tham chiếu instance trong API quản lý |
| Endpoint Compute API | Gửi yêu cầu lấy thông tin hoặc quản lý instance |
| Private IP | Kết nối đến hệ điều hành hoặc ứng dụng qua mạng riêng |
| Public IP nếu được cấu hình | Kết nối theo kiến trúc truy cập công khai phù hợp |
| DNS của load balancer | Người dùng truy cập ứng dụng qua tầng cân bằng tải |
| Endpoint quản trị hoặc kết nối database | Quản lý hoặc kết nối dịch vụ cơ sở dữ liệu theo đúng loại endpoint |

Bạn không SSH đến OCID. Bạn cũng không SSH đến hostname của Compute API để vào instance.

Tương tự, endpoint API của dịch vụ database không mặc nhiên là hostname trong chuỗi kết nối SQL. Chuỗi kết nối database còn có thể cần port, service name, chứng thư hoặc wallet tùy dịch vụ và cấu hình.

### 4.4. Control plane và data plane

Có thể phân biệt theo mục đích:

- **Control plane** phục vụ quản lý: tạo, cấu hình, lấy metadata, thay đổi trạng thái hoặc xóa tài nguyên.
- **Data plane** phục vụ sử dụng dữ liệu hay chức năng của tài nguyên: đọc object, kết nối database hoặc gửi yêu cầu đến ứng dụng.

Một API tạo bucket và một yêu cầu đọc nội dung object thuộc các thao tác khác nhau, dù đều nằm trong hệ sinh thái Object Storage. Một yêu cầu tạo database và một phiên SQL cũng có cơ chế kết nối khác nhau.

Ranh giới endpoint cụ thể phụ thuộc dịch vụ; không phải mọi dịch vụ đều tách control plane và data plane thành hai hostname hoàn toàn khác.

Khi chẩn đoán lỗi, phải biết thao tác nào đang thất bại. “Console thấy database” không chứng minh ứng dụng có thể kết nối SQL đến database đó.

### 4.5. Public endpoint, private endpoint và đường mạng

Một endpoint công khai vẫn có thể yêu cầu xác thực và IAM nghiêm ngặt. Tính “public” của địa chỉ truy cập không đồng nghĩa dữ liệu được công khai.

Một private endpoint yêu cầu cơ chế kết nối và phân giải DNS phù hợp với mạng riêng. Chỉ thay hostname trong cấu hình client không tự tạo ra route, VPN, FastConnect hoặc quyền truy cập cần thiết.

Các lớp cần kiểm tra thường gồm:

~~~text
DNS -> đường mạng -> TLS -> xác thực -> IAM -> yêu cầu API hợp lệ
~~~

Không phải lỗi nào cũng biểu hiện theo thứ tự trên, nhưng việc tách lớp giúp tránh sửa sai nguyên nhân. Nếu DNS không phân giải được, nới quyền IAM không sửa được DNS. Nếu chữ ký yêu cầu sai, thêm route mới không sửa được chữ ký.

## 5. Vòng đời tài nguyên là gì?

### 5.1. Một tài nguyên đi qua nhiều trạng thái

Vòng đời tài nguyên mô tả các trạng thái và chuyển đổi từ lúc được yêu cầu tạo đến khi ngừng tồn tại hoặc không còn khả năng sử dụng.

Một mô hình khái quát:

~~~text
Được yêu cầu tạo
      |
Đang cấp phát
      |
Sẵn sàng sử dụng
      |
Đang cập nhật hoặc thực hiện thao tác
      |
Sẵn sàng trở lại
      |
Đang xóa
      |
Đã xóa hoặc kết thúc
~~~

Những nhãn trên là mô hình học tập, không phải tập giá trị lifecycle-state chung cho mọi API OCI.

Mỗi dịch vụ có bộ trạng thái riêng. “Sẵn sàng” của volume có thể được biểu diễn khác “đang chạy” của Compute. Một bucket cũng không có chu trình start/stop như một instance.

### 5.2. Ví dụ Compute instance

Một số trạng thái thường gặp khi vận hành Compute instance:

| Trạng thái | Ý nghĩa vận hành cơ bản |
| --- | --- |
| PROVISIONING | OCI đang cấp phát instance |
| RUNNING | Instance đã ở trạng thái chạy theo góc nhìn dịch vụ Compute |
| STOPPING | Đang thực hiện dừng |
| STOPPED | Instance đã dừng |
| STARTING | Đang thực hiện khởi động |
| TERMINATING | Đang chấm dứt tài nguyên |
| TERMINATED | Instance đã được chấm dứt |

Các trạng thái và đường chuyển cụ thể cần được đối chiếu với loại thao tác và API hiện dùng. Bảng này tập trung vào luồng phổ biến, không liệt kê mọi tình huống đặc biệt.

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> RUNNING
    RUNNING --> STOPPING
    STOPPING --> STOPPED
    STOPPED --> STARTING
    STARTING --> RUNNING
    RUNNING --> TERMINATING
    STOPPED --> TERMINATING
    TERMINATING --> TERMINATED
~~~

Sơ đồ đơn giản hóa luồng hoạt động bình thường. Nó không mô tả đầy đủ các đường lỗi, thao tác đặc biệt hoặc điều kiện chuyển trạng thái của mọi loại instance.

### 5.3. RUNNING không đồng nghĩa ứng dụng đã sẵn sàng

Khi instance chuyển sang RUNNING, có thể vẫn còn:

- Hệ điều hành đang hoàn tất khởi động.
- Cloud-init đang cài package hoặc chạy script.
- Ứng dụng chưa khởi động xong.
- Secret chưa được lấy về.
- Database chưa chấp nhận kết nối.
- Backend chưa vượt qua health check của load balancer.
- Route, DNS hoặc quy tắc bảo mật chưa hoàn chỉnh.

Cần tách ít nhất ba mức kiểm tra:

| Mức | Câu hỏi |
| --- | --- |
| Trạng thái hạ tầng | Dịch vụ OCI báo tài nguyên ở trạng thái nào? |
| Khả năng kết nối | Client có tới được port hoặc endpoint cần dùng không? |
| Sẵn sàng nghiệp vụ | Ứng dụng có thực hiện được yêu cầu thực tế không? |

Ví dụ, một instance RUNNING nhưng trả HTTP 503 chưa đủ điều kiện nhận lưu lượng người dùng. Một database tồn tại trong Console nhưng ứng dụng đăng nhập thất bại cũng chưa được xem là sẵn sàng.

### 5.4. Stop khác terminate

Dừng và chấm dứt là hai thao tác khác nhau.

**Stop** chuyển instance sang trạng thái dừng theo cơ chế hỗ trợ. Tài nguyên vẫn còn định danh để quản lý và có thể được khởi động lại khi đáp ứng điều kiện.

**Terminate** chấm dứt instance. Nếu muốn có instance phục vụ lại sau đó, thường phải tạo tài nguyên mới hoặc khôi phục theo phương án đã chuẩn bị; không xem đây là nút pause.

Tác động đến boot volume, block volume, IP và các tài nguyên liên quan cần được xác nhận từ tùy chọn thao tác và quy tắc của từng tài nguyên. Không giả định terminate sẽ xóa tất cả, cũng không giả định mọi thứ sẽ được giữ lại.

Chi phí cũng phải kiểm tra theo dịch vụ, loại tài nguyên và mô hình giá. Một instance đã dừng không có nghĩa các volume, backup, public IP hoặc thành phần mạng liên quan đều ngừng phát sinh chi phí.

## 6. Yêu cầu thành công chưa chắc công việc đã hoàn tất

### 6.1. Phản hồi API và kết quả cuối cùng

Nhiều thao tác cloud thực hiện bất đồng bộ. API tiếp nhận yêu cầu trước, còn việc cấp phát hoặc thay đổi tài nguyên diễn ra sau.

Luồng điển hình:

~~~text
Client gửi yêu cầu tạo
        |
API xác thực, kiểm tra quyền và tiếp nhận
        |
Client nhận phản hồi cùng thông tin tài nguyên hoặc công việc
        |
OCI tiếp tục xử lý
        |
Client kiểm tra đến khi thành công, thất bại hoặc hết thời gian chờ
~~~

HTTP 202 thường thể hiện yêu cầu đã được chấp nhận để xử lý. HTTP 201 có thể trả về tài nguyên vừa được tạo nhưng chưa ở trạng thái sẵn sàng sử dụng. Không nên dùng riêng mã HTTP thành công để kết luận ứng dụng đã hoạt động.

Cần đọc hợp đồng API: phản hồi có tài nguyên không, trạng thái ban đầu là gì, có work request không và phải kiểm tra kết quả cuối cùng ở đâu.

### 6.2. Work request

Một số dịch vụ hoặc thao tác OCI trả về **work request**, đại diện cho công việc bất đồng bộ.

Khi API hỗ trợ, phản hồi có thể cung cấp định danh công việc qua header **opc-work-request-id**. Client dùng định danh đó với API work request thích hợp để xem tiến độ, kết quả, log hoặc lỗi mà dịch vụ cung cấp.

Không phải mọi thao tác bất đồng bộ đều có work request, và không có một endpoint work request duy nhất áp dụng cho mọi dịch vụ.

Một công việc có thể đi qua các mức khái quát:

~~~text
Đã tiếp nhận -> Đang xử lý -> Thành công
                            -> Thất bại
                            -> Bị hủy, nếu thao tác hỗ trợ
~~~

Tên trạng thái thực tế phụ thuộc API. Khi viết automation, phải dùng chính tập trạng thái của dịch vụ đang gọi.

Work request ID khác resource OCID. Một tài nguyên có thể liên quan đến nhiều công việc trong suốt vòng đời.

### 6.3. Request ID để điều tra

Một phản hồi có thể chứa **opc-request-id**, dùng để đối chiếu một yêu cầu khi điều tra lỗi.

Ba loại định danh cần lưu đúng mục đích:

| Loại | Câu hỏi được trả lời |
| --- | --- |
| Resource OCID | Tài nguyên nào? |
| Work request ID | Công việc bất đồng bộ nào? |
| Request ID | Lần gọi API nào? |

Không dùng request ID để thay cho instance ID trong lời gọi lấy thông tin instance. Cũng không dùng việc có request ID làm bằng chứng công việc đã thành công.

Nếu một thao tác thất bại, thông tin hữu ích thường gồm thời điểm, dịch vụ, region, thao tác, resource OCID liên quan, request ID và lỗi đã được che thông tin nhạy cảm.

### 6.4. Đọc lại tài nguyên và tính nhất quán

Sau khi tạo hoặc thay đổi tài nguyên, các lần đọc ở những giao diện khác nhau có thể chưa phản ánh đồng thời trạng thái mới.

Ví dụ:

- Phản hồi tạo đã có OCID nhưng danh sách trong Console chưa cập nhật ngay.
- Một lần đọc thấy trạng thái trung gian.
- Hệ thống IAM hoặc một thành phần phụ thuộc cần thêm thời gian trước khi thay đổi có hiệu lực đầy đủ.

Không nên coi lần đọc đầu tiên chưa thấy kết quả là bằng chứng chắc chắn rằng thao tác tạo đã thất bại.

Cũng không được viện lý do “cần chờ” để bỏ qua region sai, principal sai hoặc quyền thiếu. Cần đối chiếu ngữ cảnh yêu cầu trước, sau đó chờ hoặc retry trong giới hạn được quy định.

## 7. Viết automation theo trạng thái

### 7.1. Chờ có điều kiện và có giới hạn

Một cách làm dễ sai là:

~~~text
Gửi lệnh tạo
Chờ cố định 30 giây
Tiếp tục cấu hình ứng dụng
~~~

Ba mươi giây có thể quá dài với một lần chạy nhưng quá ngắn với lần khác.

Một quy trình tốt hơn:

~~~text
1. Gửi thao tác và lưu OCID/công việc nếu phản hồi cung cấp.
2. Chọn trạng thái đích được API định nghĩa.
3. Kiểm tra tài nguyên hoặc work request theo cách dịch vụ hỗ trợ.
4. Dừng khi:
   - đạt trạng thái đích;
   - gặp trạng thái lỗi cuối cùng;
   - hoặc vượt thời gian chờ.
5. Chỉ sau đó kiểm tra kết nối và sẵn sàng của ứng dụng.
~~~

SDK/CLI có thể cung cấp waiter cho những thao tác cụ thể. Cần kiểm tra tùy chọn của chính lệnh hoặc phương thức, thay vì giả định mọi lệnh đều có cùng cơ chế chờ.

Nếu tự triển khai polling, nên dùng khoảng chờ hợp lý, tăng dần khi phù hợp và thêm dao động nhỏ để tránh nhiều client gọi đồng thời. Tôn trọng giới hạn dịch vụ và hướng dẫn retry của API.

### 7.2. Hết thời gian chờ ở client không có nghĩa cloud đã dừng

Giả sử client đợi 10 phút rồi timeout. Công việc trên OCI có thể vẫn đang xử lý và hoàn tất sau đó.

Automation cần phân biệt:

| Tình huống | Cách hiểu |
| --- | --- |
| Work request báo thất bại | Dịch vụ đã báo công việc không thành công |
| Client hết thời gian chờ | Client chưa quan sát được kết quả trong thời hạn |
| Mất mạng khi gửi yêu cầu | Có thể chưa biết OCI đã tiếp nhận hay chưa |
| Tài nguyên đạt trạng thái đích | Điều kiện hạ tầng cần chờ đã được đáp ứng |

Trước khi gửi một yêu cầu tạo mới, cần tra lại công việc hoặc tài nguyên theo thông tin đã nhận được. Tạo lại ngay có thể tạo hai tài nguyên và phát sinh chi phí ngoài ý muốn.

### 7.3. Retry và tính lặp an toàn

Không phải lời gọi nào cũng có thể lặp lại mà không gây thêm tác động.

Một số thao tác hỗ trợ **opc-retry-token** để giúp xử lý yêu cầu lặp trong phạm vi và thời hạn mà API quy định. Khi sử dụng cơ chế này:

- Dùng cùng token cho việc gửi lại cùng một thao tác logic.
- Giữ nhất quán nội dung yêu cầu theo hợp đồng API.
- Không tạo token mới cho mỗi lần retry của cùng thao tác nếu mục đích là tránh tạo trùng.
- Không tái sử dụng token để đại diện cho một thao tác nghiệp vụ khác.
- Không xem token là cơ chế chống trùng tồn tại vô hạn.

Chỉ sử dụng header hoặc tham số retry token khi API hỗ trợ. Không tự thêm vào mọi endpoint rồi giả định nó có hiệu lực.

Với lỗi tạm thời, có thể retry theo hướng dẫn dịch vụ. Với sai tham số hoặc thiếu quyền, gửi lại nguyên yêu cầu nhiều lần thường không giải quyết nguyên nhân.

### 7.4. Tránh cập nhật đè bằng ETag khi được hỗ trợ

Một số API trả ETag và hỗ trợ điều kiện **If-Match** khi cập nhật hoặc xóa.

Ví dụ khái niệm:

~~~text
Client A đọc tài nguyên -> nhận ETag phiên bản 1
Client B cập nhật        -> tài nguyên có ETag phiên bản 2
Client A cập nhật với If-Match phiên bản 1
                        -> điều kiện không còn đúng
~~~

Cơ chế này giúp phát hiện dữ liệu đã thay đổi kể từ lúc client đọc. Nó không thay cho IAM và không phải khóa toàn bộ workflow nhiều bước.

Khi gặp lỗi điều kiện, nên đọc lại, xem xét thay đổi và quyết định cách xử lý. Bỏ điều kiện để thử lại ngay có thể làm mất thay đổi hợp lệ của người khác.

## 8. Thực hành đọc thông tin bằng OCI CLI

Phần này minh họa thao tác **chỉ đọc** một Compute instance. Các lệnh là nội dung học tập, không được thực thi tự động trong bài.

### 8.1. Điều kiện

Cần có:

- OCI CLI đã được cài và xác thực bằng cơ chế phù hợp.
- Principal có quyền đọc instance cần kiểm tra.
- Region đúng của instance.
- OCID đầy đủ của instance.
- Đường mạng tới endpoint API tương ứng.

Ví dụ dưới đây dùng PowerShell và hai biến môi trường do người học chuẩn bị:

~~~powershell
$env:OCI_REGION = "<region-cua-instance>"
$env:OCI_INSTANCE_OCID = "<ocid-day-du-cua-instance>"
~~~

Các chuỗi trong dấu ngoặc nhọn là placeholder. Không dùng OCID đã che bớt trong một lời gọi thật.

### 8.2. Đọc instance

~~~powershell
if ([string]::IsNullOrWhiteSpace($env:OCI_REGION)) {
    throw "Chua co OCI_REGION."
}

if ([string]::IsNullOrWhiteSpace($env:OCI_INSTANCE_OCID)) {
    throw "Chua co OCI_INSTANCE_OCID."
}

$instanceJson = oci compute instance get --instance-id $env:OCI_INSTANCE_OCID --region $env:OCI_REGION --output json
$ociExitCode = $LASTEXITCODE

if ($ociExitCode -ne 0) {
    throw "Khong doc duoc instance. Kiem tra loi CLI, region va quyen IAM."
}

$instanceResponse = ($instanceJson -join [Environment]::NewLine) | ConvertFrom-Json
$instanceData = $instanceResponse.data

[pscustomobject]@{
    Id            = $instanceData.id
    DisplayName   = $instanceData.'display-name'
    CompartmentId = $instanceData.'compartment-id'
    Lifecycle     = $instanceData.'lifecycle-state'
}
~~~

Lệnh lấy thông tin dùng instance OCID để chỉ đối tượng và region để chọn ngữ cảnh gọi dịch vụ. Cấu hình xác thực của CLI cung cấp danh tính; OCID không thay vai trò đó.

Không chèn private key hoặc token vào đoạn lệnh. Nếu cần chọn cấu hình xác thực khác, sử dụng cơ chế cấu hình được CLI hỗ trợ.

### 8.3. Đọc kết quả đúng

Khi có kết quả, hãy trả lời:

1. **Id** có khớp tài nguyên dự định kiểm tra không?
2. **DisplayName** có đúng kỳ vọng không, và có thể trùng tên với tài nguyên khác không?
3. **CompartmentId** có đúng phạm vi quản trị không?
4. **Lifecycle** là trạng thái cuối cùng mong muốn hay trạng thái trung gian?
5. Sau trạng thái hạ tầng, còn phải kiểm tra điều kiện ứng dụng nào?

Không dùng kết quả RUNNING để tự động kết luận rằng website, SSH hoặc database đã truy cập được.

Nếu đọc được tài nguyên nhưng không kết nối được ứng dụng, chuyển sang kiểm tra đường mạng, cổng dịch vụ, hệ điều hành, chứng thư và cấu hình ứng dụng.

### 8.4. Đối chiếu trong Console

Trong OCI Console, có thể mở trang chi tiết tài nguyên để đối chiếu các thông tin tương ứng:

- OCID và tên hiển thị.
- Compartment.
- Region đang chọn.
- Trạng thái hiện tại.
- Những tài nguyên liên quan, chẳng hạn VNIC, subnet hoặc volume nếu có.

Tên nhóm mục và cách hiển thị có thể khác theo dịch vụ. Mục đích của bước này là đối chiếu cùng một tài nguyên, không chỉ tìm một tên giống nhau.

## 9. Chẩn đoán các tình huống thường gặp

### 9.1. Có OCID nhưng API báo không tìm thấy hoặc không được phép

Một số phản hồi của OCI có thể không giúp người gọi phân biệt trực tiếp tài nguyên không tồn tại với tài nguyên không được phép truy cập.

Kiểm tra theo thứ tự có ích:

1. OCID có đầy đủ, đúng loại tài nguyên và không có khoảng trắng thừa không?
2. Lệnh có đang dùng đúng principal, profile và tenancy không?
3. Region và endpoint có đúng ngữ cảnh của tài nguyên không?
4. Tài nguyên có còn tồn tại, hoặc đã được thay thế bằng tài nguyên mới không?
5. Principal có quyền phù hợp ở compartment hiện tại không?
6. Có thay đổi IAM gần đây cần được kiểm tra hiệu lực không?

Không khắc phục bằng cách cấp quyền quản trị toàn tenancy chỉ để thử. Trước hết xác định đúng đối tượng và quyền cần thiết.

### 9.2. Lỗi DNS, TLS hoặc timeout

Nếu không kết nối được tới endpoint, cần kiểm tra:

- Hostname có đúng với dịch vụ, region và realm không.
- DNS từ môi trường chạy client có phân giải đúng không.
- Proxy, VPN, firewall và route có cho phép đường đi không.
- Với private endpoint, có đúng kết nối mạng riêng và DNS tương ứng không.
- Kiểm tra TLS có thành công, chuỗi tin cậy có hợp lệ không.
- Thời gian hệ thống và cơ chế ký yêu cầu có phù hợp khi đã kết nối được.

Không tắt xác minh TLS như một cách sửa lâu dài. Việc đó che triệu chứng và làm suy yếu tính xác thực của endpoint.

### 9.3. Trạng thái trung gian kéo dài

Nếu tài nguyên nằm lâu ở trạng thái cấp phát hoặc cập nhật:

1. Xác định đây là trạng thái của tài nguyên hay của work request.
2. Đọc log và lỗi của công việc nếu dịch vụ cung cấp.
3. Kiểm tra quota, giới hạn, năng lực cấp phát, phụ thuộc mạng và điều kiện cấu hình phù hợp.
4. Đối chiếu request ID và thời điểm xảy ra.
5. Tiếp tục chờ trong giới hạn đã định hoặc chuyển sang quy trình xử lý sự cố.

Không gửi đồng thời nhiều thao tác start, stop, update hoặc delete để “thúc” tài nguyên. Các thao tác có thể xung đột với trạng thái hiện tại và gây khó điều tra.

### 9.4. Không xóa được tài nguyên

Nguyên nhân có thể là tài nguyên đang thực hiện thao tác khác, còn phụ thuộc, chưa thỏa điều kiện xóa hoặc principal thiếu quyền.

Cần đọc lỗi thực tế và kiểm tra quan hệ phụ thuộc. Ví dụ, thao tác xóa một thành phần mạng có thể cần xử lý các thành phần đang gắn với nó trước, theo quy tắc của dịch vụ.

Một work request xóa thành công cũng cần được đối chiếu với mục tiêu dọn dẹp: tài nguyên con, volume, backup hoặc endpoint khác có được giữ lại có chủ đích không?

Không coi danh sách Console trống tạm thời là bằng chứng duy nhất rằng mọi tài nguyên và chi phí liên quan đã được thu hồi.

## 10. Vòng đời gắn với chi phí, IAM và tính sẵn sàng

### 10.1. Kiểm soát chi phí theo tập tài nguyên

Một hệ thống ứng dụng thường gồm nhiều tài nguyên có vòng đời riêng:

~~~text
Ứng dụng
  + Compute instance
  + Boot/block volume
  + Load balancer
  + Public IP theo cấu hình
  + Object Storage/backup
  + Database
  + Thành phần mạng và giám sát
~~~

Dừng hoặc xóa một instance không đồng nghĩa toàn bộ tập này được dừng hoặc xóa theo. Chính sách dọn dẹp phải xác định từng thành phần, dữ liệu cần giữ và điều kiện phát sinh chi phí của chúng.

Nên theo dõi tag, chủ sở hữu, thời hạn sử dụng và các tham chiếu OCID để tìm tài nguyên mồ côi sau thử nghiệm hoặc thay thế hệ thống.

### 10.2. Thay đổi compartment có thể đổi quyền hiệu lực

Với tài nguyên hỗ trợ chuyển compartment, OCID của cùng tài nguyên có thể được giữ nguyên trong khi quyền truy cập hiệu lực thay đổi theo chính sách áp dụng ở vị trí mới.

Điều này có thể ảnh hưởng đến:

- Automation đang đọc hoặc quản lý tài nguyên.
- Người vận hành phụ trách ứng dụng.
- Hệ thống thu thập dữ liệu giám sát.
- Các tích hợp có điều kiện IAM liên quan.

Do đó, định danh ổn định không có nghĩa quyền truy cập ổn định. Cần kiểm tra quyền và những ràng buộc riêng của dịch vụ trước và sau việc chuyển.

### 10.3. Thay thế tài nguyên và DR

Khi triển khai lại ở region khác, phải dự kiến:

- OCID mới cho các tài nguyên được tạo mới.
- Endpoint API theo region đích.
- Endpoint ứng dụng hoặc database có thể thay đổi.
- IAM, mạng và secret phải phù hợp với kiến trúc mới.
- Các bộ lọc giám sát hoặc automation tham chiếu OCID cũ cần cập nhật.

Một tên DNS ổn định có thể giúp ứng dụng giảm phụ thuộc vào địa chỉ triển khai, nhưng không tự di chuyển state, dữ liệu hoặc quyền IAM.

Đối với database, cần một phương án bảo vệ và khôi phục dữ liệu riêng. Việc tạo lại tài nguyên hạ tầng không đồng nghĩa dữ liệu và giao dịch đã được phục hồi.

## 11. Tình huống tổng hợp

### Bối cảnh

Một pipeline tạo Compute instance cho ứng dụng học tập. Lời gọi tạo trả về OCID, nhưng pipeline mất kết nối trước khi quan sát được trạng thái cuối cùng.

Người vận hành thấy Console chưa hiển thị instance trong danh sách vừa mở và định chạy lại toàn bộ bước tạo.

### Phân tích

Có ba việc chưa được phân biệt:

1. Yêu cầu đã được dịch vụ tiếp nhận hay chưa?
2. Tài nguyên đã có trạng thái nào?
3. Ứng dụng đã sẵn sàng hay chưa?

Việc chưa thấy kết quả trong danh sách không trả lời đủ ba câu hỏi. Chạy lại ngay có thể tạo thêm instance nếu lần đầu đã thành công.

### Cách xử lý

- Xác nhận region, principal và compartment của pipeline.
- Dùng OCID đã nhận để đọc trực tiếp tài nguyên qua endpoint phù hợp.
- Kiểm tra work request nếu thao tác đã cung cấp thông tin đó.
- Nếu đang PROVISIONING, tiếp tục theo dõi có thời hạn thay vì tạo lại.
- Nếu đạt RUNNING, kiểm tra khởi tạo hệ điều hành và health check của ứng dụng.
- Nếu thất bại, thu thập lỗi, request ID và trạng thái của các tài nguyên liên quan trước khi quyết định thử lại.
- Nếu phải retry thao tác tạo, áp dụng cơ chế lặp an toàn mà API hỗ trợ và đối chiếu tài nguyên đã có.
- Sau khi hoàn tất, ghi OCID và các endpoint cần sử dụng vào đầu ra triển khai phù hợp.

### Thông tin nên được lưu

| Nhóm | Dữ liệu |
| --- | --- |
| Ngữ cảnh | Môi trường, region, compartment và danh tính thực thi theo mức cần thiết |
| Tài nguyên | OCID, tên hiển thị, loại tài nguyên và chủ sở hữu |
| Thao tác | Loại yêu cầu, thời điểm, request ID, work request ID nếu có |
| Kết quả | Trạng thái hạ tầng cuối cùng và kết quả health check |
| Truy cập | Endpoint API hoặc endpoint ứng dụng cần dùng, tránh lẫn vai trò |
| Vận hành | Thời hạn sử dụng, quy tắc giữ dữ liệu và cách thu hồi |

Không lưu khóa bí mật hoặc toàn bộ header xác thực chỉ để có thêm thông tin điều tra.

## 12. Tự kiểm tra

### Câu 1: Hai instance cùng tên có cùng OCID không?

Không. Tên hiển thị không bảo đảm duy nhất. Mỗi instance là một tài nguyên riêng và có OCID riêng.

### Câu 2: Đổi tên instance có làm OCID thay đổi không?

Không, nếu vẫn là cùng instance và thao tác đổi tên được hỗ trợ. Tạo instance mới với tên cũ là trường hợp khác và tạo định danh mới.

### Câu 3: Có thể dùng OCID để SSH không?

Không. SSH cần địa chỉ hoặc hostname có thể kết nối, đường mạng, cổng, thông tin đăng nhập và cấu hình hệ điều hành phù hợp. OCID dùng để tham chiếu tài nguyên trong các API tương ứng.

### Câu 4: API trả HTTP thành công có nghĩa ứng dụng đã sẵn sàng không?

Không. API có thể mới tiếp nhận hoặc tạo tài nguyên ở trạng thái trung gian. Cần theo dõi trạng thái hạ tầng, rồi kiểm tra khả năng kết nối và sẵn sàng ứng dụng.

### Câu 5: Client timeout có nên tạo lại ngay không?

Không nên. Trước tiên cần kiểm tra tài nguyên hoặc công việc đã được tiếp nhận. Timeout ở client không chứng minh thao tác trên cloud đã thất bại hoặc bị hủy.

### Câu 6: Endpoint đúng và OCID đúng đã đủ để đọc tài nguyên chưa?

Chưa. Còn cần xác thực đúng danh tính, IAM phù hợp và kết nối mạng hoạt động. Một số thao tác còn có các điều kiện riêng theo dịch vụ.

### Câu 7: Stop có bảo đảm không còn chi phí không?

Không. Cần xem mô hình giá và trạng thái của toàn bộ tài nguyên liên quan, bao gồm lưu trữ, backup, địa chỉ và các thành phần dịch vụ còn tồn tại.

## 13. Danh sách kiểm tra khi thao tác với tài nguyên OCI

- [ ] Đã xác định đúng loại tài nguyên và định danh API yêu cầu.
- [ ] Đã lấy OCID đầy đủ từ nguồn đáng tin cậy, không dùng chuỗi đã che bớt.
- [ ] Đã phân biệt tên hiển thị, resource OCID và compartment OCID.
- [ ] Đã chọn đúng principal, tenancy, region và endpoint.
- [ ] Đã kiểm tra điều kiện xác thực, IAM và đường mạng.
- [ ] Đã đọc trạng thái mà API thực sự trả về, không áp dụng nhãn chung cho mọi dịch vụ.
- [ ] Đã phân biệt tiếp nhận yêu cầu với hoàn tất công việc.
- [ ] Có request ID và work request ID khi dịch vụ cung cấp.
- [ ] Có cơ chế chờ giới hạn, xử lý lỗi và tránh tạo trùng khi retry.
- [ ] Đã kiểm tra sẵn sàng ứng dụng sau sẵn sàng hạ tầng.
- [ ] Với stop, delete hoặc terminate, đã hiểu dữ liệu giữ lại và các tài nguyên tiếp tục tồn tại.
- [ ] Sau thay thế hoặc DR, đã cập nhật tham chiếu OCID, endpoint và giám sát.

Khi đọc một phản hồi OCI, hãy ghép ba thông tin: **định danh tài nguyên**, **ngữ cảnh gọi dịch vụ** và **trạng thái quan sát được**. Có đủ ba phần này, việc triển khai, tự động hóa và điều tra sự cố sẽ có căn cứ rõ ràng hơn.
