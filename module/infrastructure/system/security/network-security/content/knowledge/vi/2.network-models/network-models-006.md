# Management network và data network

Một hệ thống có thể phục vụ hàng triệu yêu cầu của người dùng nhưng chỉ có vài quản trị viên cần thay đổi cấu hình, xem trạng thái hoặc khôi phục dịch vụ. Hai loại hoạt động đó có mục tiêu, quyền hạn và yêu cầu an toàn khác nhau. Nếu mọi thiết bị và dịch vụ đều dùng chung một mạng có thể truy cập lẫn nhau, một máy chủ ứng dụng bị xâm nhập có thể trở thành đường đến giao diện quản trị; khi mạng phục vụ người dùng gặp sự cố, người vận hành cũng có thể mất đường vào để sửa chữa.

**Management network (mạng quản trị)** là tập hợp các kết nối và chính sách phục vụ quản lý, cấu hình, giám sát và khôi phục hạ tầng. **Data network (mạng dữ liệu)** vận chuyển lưu lượng phục vụ chức năng nghiệp vụ như yêu cầu người dùng, giao tiếp giữa các dịch vụ và truy cập cơ sở dữ liệu. Một kiến trúc mạng an toàn thường **phân tách đường quản trị với đường dữ liệu** để giảm phạm vi xâm nhập, kiểm soát đặc quyền và duy trì khả năng vận hành khi có sự cố.

Bài học thuộc chương **Mô hình mạng**, nằm trong phạm vi **SECURITY_NETWORK_SECURITY**. Việc phân biệt hai loại mạng là nền tảng cho các chủ đề phân đoạn mạng, firewall, VPN, xác thực kết nối, IDS/IPS, bảo vệ DNS, Wi-Fi, cloud, phân tích lưu lượng, mô hình hóa mối đe dọa và xây dựng kiến trúc phòng vệ nhiều lớp.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt management network và data network qua mục đích, tài sản, luồng lưu lượng và mức quyền.
2. Không nhầm **mạng quản trị** với **management plane**, hoặc **mạng dữ liệu** với **data plane**.
3. So sánh thiết kế quản trị **in-band**, **out-of-band**, phân đoạn bằng VLAN/VRF và mô hình trên cloud.
4. Lập ma trận luồng được phép giữa quản trị viên, thiết bị mạng, ứng dụng, database và hệ thống giám sát.
5. Nhận diện rủi ro do dùng chung đường truy cập, cấp quyền quá rộng, lộ giao diện quản trị và thiếu đường khôi phục.
6. Đề xuất kiểm soát và phương pháp kiểm chứng phù hợp với một hệ thống thực tế.

## 1. Hai loại mạng giải quyết hai nhu cầu khác nhau

Xét một nền tảng học trực tuyến. Lưu lượng **người học → website → API → database** là lưu lượng dữ liệu phục vụ nghiệp vụ. Trong khi đó, lưu lượng **quản trị viên → cổng truy cập bảo vệ → giao diện quản trị máy chủ/router/firewall** là lưu lượng quản trị. Hệ thống giám sát thu nhận log, chỉ số hoạt động và cảnh báo cũng thuộc phạm vi vận hành, dù các tác nhân thu thập có thể chạy ngay trong mạng ứng dụng.

| Tiêu chí | Management network | Data network |
|---|---|---|
| Mục tiêu | Cấu hình, vận hành, giám sát, cập nhật và khôi phục | Cung cấp sản phẩm/dịch vụ và trao đổi dữ liệu nghiệp vụ |
| Chủ thể truy cập | Quản trị viên, công cụ tự động hóa, hệ thống giám sát, công cụ sao lưu cấu hình | Người dùng, ứng dụng, workload, thiết bị nghiệp vụ |
| Đích điển hình | SSH/HTTPS quản trị, giao diện hypervisor, firewall, switch, router, BMC, API quản trị | Web gateway, API, message broker, database, dịch vụ lưu trữ |
| Quyền cần bảo vệ | Thường có thể thay đổi cấu hình hoặc điều khiển hạ tầng; mức tác động cao | Quyền sử dụng dịch vụ và quyền dữ liệu theo nghiệp vụ |
| Mức phơi bày mong muốn | Hạn chế tối đa; chỉ qua đường vào được kiểm soát | Công khai hoặc nội bộ tùy dịch vụ; không mặc định mở mọi cổng |
| Tính sẵn sàng | Cần còn sử dụng được để chẩn đoán và khôi phục khi mạng ứng dụng lỗi | Cần đáp ứng yêu cầu về hiệu năng, độ trễ và tính liên tục của nghiệp vụ |
| Bằng chứng giám sát | Đăng nhập quản trị, thay đổi cấu hình, phiên đặc quyền, trạng thái thiết bị | Kết nối người dùng, lưu lượng ứng dụng, lỗi dịch vụ, lưu lượng bất thường |

**Lưu ý:** tên gọi thể hiện **mục đích sử dụng và chính sách tin cậy**, không nhất thiết là hai bộ dây cáp vật lý riêng. Một mạng quản trị có thể dùng hạ tầng truyền dẫn chung nhưng nằm trong VLAN hoặc VRF riêng, với firewall và kiểm soát danh tính. Ngược lại, kết nối vật lý riêng mà vẫn cho truy cập quản trị rộng rãi thì chưa an toàn.

### Một thiết bị có thể thuộc cả hai đường mạng

Máy chủ ứng dụng có thể có giao diện dữ liệu để nhận yêu cầu từ API gateway và giao diện quản trị riêng để kỹ sư vận hành truy cập. Switch có thể chuyển tiếp gói của người dùng qua các cổng dữ liệu, đồng thời nhận phiên SSH/HTTPS vào địa chỉ quản trị của chính nó. Không thể xác định loại lưu lượng chỉ bằng tên thiết bị: phải xét **ai kết nối, đến giao diện nào, để làm gì và được quyền gì**.

Một hệ thống lưu trữ còn có thể có **storage network** riêng cho iSCSI/NFS hoặc lưu lượng sao chép. Đó là một vùng chức năng khác, không đồng nghĩa với mạng quản trị; trong phân loại khái quát, nó có thể được xem là một loại mạng vận chuyển dữ liệu nội bộ cần bảo vệ riêng.

## 2. Phân biệt network với plane: ba khái niệm rất dễ nhầm

Trong tài liệu mạng, các từ **management plane**, **control plane** và **data plane** mô tả **chức năng xử lý**, còn **management network** và **data network** mô tả **đường kết nối/miền mạng** dùng để vận chuyển một số loại lưu lượng.

| Plane | Chức năng | Ví dụ |
|---|---|---|
| **Management plane** | Cho phép người hoặc công cụ quan sát và thay đổi cấu hình/trạng thái hệ thống | Giao diện SSH của router, HTTPS quản trị firewall, API cấu hình switch, công cụ quản lý cloud |
| **Control plane** | Xây dựng, duy trì thông tin điều khiển cách hệ thống chuyển tiếp/hoạt động | Giao thức định tuyến, bảng lân cận, bộ điều khiển mạng, một số API điều phối |
| **Data plane (forwarding plane)** | Xử lý và chuyển tiếp lưu lượng theo các quyết định/chính sách đã có | Chuyển gói IP, áp dụng ACL trên đường đi, chuyển lưu lượng người dùng |

Ví dụ, một router **chuyển tiếp** gói HTTPS của học viên trên data plane, **học tuyến đường** qua control plane và **cho quản trị viên sửa cấu hình** qua management plane. Router có thể truyền thông tin của cả ba plane qua cùng cơ sở hạ tầng vật lý; đó là lý do phải nêu rõ đang nói về **chức năng** hay **kết nối**.

Mối quan hệ không phải ánh xạ một-một:

- Lưu lượng SSH quản trị có thể đi qua cùng cáp vật lý đang phục vụ dữ liệu, nhưng vẫn là giao tiếp với management plane.
- Bản tin định tuyến của control plane không tự động là lưu lượng quản trị, dù cần được kiểm soát chặt chẽ.
- API quản trị cloud có thể được gọi qua endpoint của nhà cung cấp, không đi qua subnet quản trị mà tổ chức tự dựng.
- Log và telemetry có thể được gửi từ data network sang hệ thống giám sát qua kết nối đã cho phép; không nhất thiết thiết lập một đường vật lý độc lập cho mọi bản ghi.

Khi thiết kế chính sách, hãy ghi rõ **vùng nguồn, vùng đích, chức năng, giao thức, định danh và điểm cưỡng chế** thay vì chỉ gắn nhãn “management” hay “data”.

## 3. Vì sao cần phân tách?

### 3.1. Giảm khả năng di chuyển ngang và leo thang đặc quyền

Nếu một máy chủ web công khai bị chiếm quyền và mạng nội bộ không có ranh giới, kẻ tấn công có thể thử kết nối đến cổng SSH của hypervisor hoặc API quản trị firewall. Những bề mặt quản trị thường mang quyền tác động lớn hơn nhiều so với chức năng đọc một trang web. Phân tách đường quản trị, giới hạn nguồn được phép và xác thực mạnh làm giảm số đường tấn công có thể đi tiếp.

**Phân đoạn không đồng nghĩa đã cô lập hoàn toàn.** Cấu hình firewall sai, tài khoản quản trị bị lộ hoặc một máy trung gian bị chiếm vẫn có thể phá vỡ kỳ vọng bảo vệ. Phân tách là một lớp trong mô hình **defense in depth**.

### 3.2. Bảo vệ kênh vận hành khi data network gặp lỗi

Giả sử một thay đổi định tuyến gây mất kết nối từ người dùng đến ứng dụng. Nếu công cụ quản trị cũng bắt buộc dùng chính tuyến đang lỗi, đội vận hành có thể mất khả năng truy cập để hoàn tác thay đổi. Một đường quản trị **out-of-band** độc lập phù hợp có thể cho phép đăng nhập thiết bị, xem trạng thái và phục hồi mà không cần mạng dữ liệu hoạt động.

Tuy nhiên, tính độc lập phải được thiết kế và kiểm tra: hai mạng vẽ khác màu trên sơ đồ nhưng cùng phụ thuộc một switch, nguồn điện hoặc thiết bị gateway vẫn có thể hỏng cùng lúc.

### 3.3. Dễ kiểm toán đặc quyền và điều tra sự cố

Khi nguồn truy cập quản trị tập trung qua một cổng vào, hệ thống dễ ghi nhận ai đăng nhập, vào thiết bị nào, dùng cơ chế gì và có thay đổi cấu hình không. Nhật ký quản trị cần kết hợp với log firewall, DNS, VPN/ZTNA và cloud để phát hiện bất thường. Lưu log chỉ có ý nghĩa khi thời gian đồng bộ, dữ liệu được bảo vệ khỏi sửa/xóa trái phép và có người xử lý cảnh báo.

### 3.4. Hạn chế ảnh hưởng giữa lưu lượng vận hành và nghiệp vụ

Các hoạt động như sao lưu cấu hình, cập nhật firmware, lấy telemetry hay sao chép dữ liệu có thể tạo tải. Thiết kế đường truyền, giới hạn băng thông và ưu tiên thích hợp giúp hoạt động quản trị không làm nghẽn dịch vụ. Mặt khác, mạng quản trị không nên phụ thuộc vào mọi thành phần ứng dụng nếu mục tiêu là khả năng phục hồi độc lập.

## 4. Kiến trúc tham khảo: nơi nào được phép đi tới đâu?

Ví dụ hạ tầng gồm ứng dụng và cơ sở dữ liệu tách vùng, một mạng quản trị dành cho vận hành và một hệ thống tập trung log:

~~~mermaid
flowchart TB
    U["Người học / Internet"]
    ADMIN["Quản trị viên"]
    ID["SSO + MFA / xác minh thiết bị"]

    subgraph D["DATA NETWORK - luồng nghiệp vụ"]
      EDGE["Gateway HTTPS công khai"]
      APP["Vùng ứng dụng / API"]
      DB[("Vùng cơ sở dữ liệu")]
      EDGE -->|"API cần thiết"| APP
      APP -->|"Cổng DB theo chính sách"| DB
    end

    subgraph M["MANAGEMENT NETWORK - truy cập đặc quyền"]
      ACCESS["VPN / ZTNA / bastion"]
      HOST["Giao diện quản trị server / hypervisor"]
      NET["Giao diện quản trị router / firewall / switch"]
      ACCESS -->|"Chỉ tài sản được cấp quyền"| HOST
      ACCESS -->|"Chỉ tài sản được cấp quyền"| NET
    end

    subgraph O["QUAN SÁT VÀ KIỂM TOÁN"]
      LOG["Collector / SIEM"]
    end

    U -->|"HTTPS 443"| EDGE
    ADMIN --> ID
    ID -->|"Phiên hợp lệ"| ACCESS
    HOST -.->|"Telemetry / audit"| LOG
    NET -.->|"Syslog / telemetry"| LOG
    APP -.->|"Ứng dụng gửi log"| LOG
~~~

Sơ đồ biểu diễn **nhóm luồng được chủ đích cho phép**. Việc quản trị ứng dụng không được hiểu là cần mở mọi kết nối từ management network sang data network; các đích quản trị phải được xác định riêng. Các mũi tên log biểu diễn đường gửi bằng cơ chế được cấu hình và bảo vệ, không ngụ ý collector cho phép truy cập ngược vào mọi nguồn log.

### Ma trận luồng tham khảo

Giả định một tổ chức dùng các vùng địa chỉ riêng sau:

| Vùng mạng | Ví dụ subnet | Vai trò |
|---|---|---|
| Management | 10.10.10.0/24 | Endpoint quản trị thiết bị, cổng quản trị máy chủ |
| Monitoring | 10.10.20.0/24 | Collector, syslog, hệ thống giám sát |
| Frontend/data | 10.20.10.0/24 | Gateway và dịch vụ giao tiếp phía trước |
| Backend/data | 10.20.20.0/24 | API và các workload ứng dụng |
| Database/data | 10.20.30.0/24 | Database nội bộ |

Các dải IP chỉ để minh họa. Một chính sách nguyên tắc có thể là:

| Nguồn → Đích | Dịch vụ ví dụ | Quyết định mặc định | Lý do |
|---|---|---|---|
| Internet → Gateway công khai | HTTPS/TCP 443 | **Cho phép có kiểm soát** | Cung cấp website/API |
| Internet → Giao diện quản trị | SSH 22, HTTPS quản trị 443 | **Từ chối** | Không công khai trực tiếp control quản trị |
| Frontend → Backend | Cổng API được công bố | **Cho phép đúng đích** | Luồng nghiệp vụ đã đăng ký |
| Backend → Database | PostgreSQL/TCP 5432 nếu thực dùng | **Chỉ cho workload cần thiết** | Giới hạn kết nối dữ liệu |
| Frontend → Management | Mọi cổng quản trị | **Từ chối** | Chặn đường đi từ vùng công khai đến đặc quyền |
| Quản trị viên đã MFA → Bastion/ZTNA | Theo phương thức truy cập | **Cho phép có điều kiện** | Gắn truy cập với người/thiết bị và quyền |
| Bastion → Giao diện quản trị mục tiêu | SSH/HTTPS theo tài sản | **Chỉ nguồn và đích được phê duyệt** | Hạn chế phạm vi phiên đặc quyền |
| Thiết bị → Collector | Syslog qua TLS/TCP 6514 nếu hỗ trợ | **Chỉ đến collector** | Chuyển bằng chứng và bảo vệ tính toàn vẹn |
| Collector → thiết bị để khảo sát | SNMPv3/UDP 161 nếu triển khai | **Chỉ nguồn giám sát được chỉ định** | Thu thập dữ liệu quản lý có xác thực và bảo vệ phù hợp |

Các cổng là ví dụ phổ biến, không phải yêu cầu mở cổng cho mọi thiết bị. Một số hệ thống dùng HTTPS, gRPC, agent hoặc API riêng cho quản trị và quan sát. Quy tắc cuối cùng phải dựa trên danh mục luồng thật, đặc tả của nhà cung cấp và kết quả kiểm thử. Cũng phải xét chính sách **chiều ra**, lưu lượng **IPv6** và cơ chế theo dõi trạng thái kết nối nếu có.

## 5. In-band và out-of-band: hai cách xây dựng đường quản trị

### 5.1. In-band management

**In-band** nghĩa là truy cập quản trị đi qua cùng hạ tầng vận chuyển đang chở lưu lượng dịch vụ, dù có thể được ngăn cách bằng VLAN, VRF, subnet hoặc firewall. Ví dụ, một switch có địa chỉ quản trị trong VLAN riêng nhưng VLAN đó vẫn đi qua các đường uplink chung của hệ thống.

Ưu điểm: tận dụng hạ tầng sẵn có, chi phí thường thấp, dễ triển khai trên quy mô lớn. Nhược điểm: nếu thiết bị trung gian, đường uplink hoặc định tuyến chung gặp lỗi, đường quản trị cũng có thể mất; việc phân đoạn logic không sửa được lỗi hạ tầng vật lý chung.

Thiết kế in-band vẫn có thể đủ an toàn cho nhiều hệ thống nếu dùng các chính sách truy cập chặt, xác thực mạnh, giám sát và một phương án khôi phục phù hợp.

### 5.2. Out-of-band management (OOB)

**Out-of-band** là đường quản trị được thiết kế độc lập với đường mang lưu lượng nghiệp vụ chính. Ví dụ, cổng management chuyên dụng của switch/router hoặc cổng BMC như iDRAC/iLO của máy chủ kết nối đến switch quản trị riêng; ở địa điểm cần độ sẵn sàng cao, đường vào có thể dùng tuyến truyền dẫn dự phòng độc lập.

OOB hữu ích khi cần khôi phục thiết bị dù hệ điều hành, cấu hình data-plane hoặc uplink chính bị lỗi. Tuy nhiên:

- Cổng BMC là bề mặt có quyền đặc biệt lớn; phải cập nhật firmware, vô hiệu tài khoản mặc định, hạn chế nguồn truy cập và theo dõi nhật ký.
- Mạng OOB không nên công khai trực tiếp ra Internet hoặc mở tự do cho mọi nhân viên có VPN.
- “Hai switch khác nhau” chưa đảm bảo độc lập nếu cùng thiết bị nguồn, cùng tuyến uplink hoặc cùng dịch vụ nhận dạng không có phương án dự phòng.
- OOB có thể khắc phục lỗi truyền thông hoặc hệ điều hành trong một số trường hợp, **không** thay thế backup, quyền khôi phục hợp lệ hay kế hoạch ứng phó sự cố.

### So sánh lựa chọn triển khai

| Thiết kế | Cách phân tách | Khi nào phù hợp | Điều cần kiểm chứng |
|---|---|---|---|
| Dùng chung mạng không phân đoạn | Ít hoặc không có ranh giới | Chỉ nên tồn tại tạm thời trong môi trường thử nghiệm rất hạn chế | Bề mặt quản trị bị mở rộng; rủi ro khó kiểm soát |
| In-band với VLAN + ACL/firewall | Phân đoạn logic trên hạ tầng chung | Hệ thống nhỏ và vừa, ngân sách hoặc vị trí có hạn | Luồng giữa VLAN có thực sự bị giới hạn? |
| In-band với VRF và điểm kiểm soát | Tách bảng định tuyến và chính sách giữa miền | Nhiều tenant, nhiều vùng mạng và yêu cầu định tuyến riêng | Route leak, peering và chính sách liên VRF có đúng không? |
| OOB với đường và thiết bị quản trị riêng | Độc lập đáng kể với data path | Core network, trung tâm dữ liệu, môi trường cần khôi phục từ xa | Điện, uplink, định danh và đường vào dự phòng có độc lập đủ không? |
| Mô hình kết hợp | In-band cho vận hành thường ngày; OOB cho thiết bị trọng yếu/khôi phục | Tổ chức có nhiều cấp độ quan trọng | Ai được dùng đường khẩn cấp, khi nào và được ghi log ra sao? |

**VLAN** là cơ chế phân chia miền lớp 2, còn **VRF** tạo các bảng định tuyến logic riêng. Cả hai đều hỗ trợ phân tách, nhưng **không tự thay thế chính sách xác thực, phân quyền và firewall**. Nếu bật định tuyến giữa các mạng và cho phép quá rộng, mục tiêu bảo mật có thể không đạt.

## 6. Thiết kế một mạng quản trị an toàn

### 6.1. Xác định tài sản và giao diện cần quản trị

Kiểm kê router, switch, firewall, hypervisor, host, BMC, access point, thiết bị lưu trữ, load balancer, gateway VPN/ZTNA và API cloud. Với mỗi tài sản, ghi **chủ sở hữu, điểm truy cập quản trị, danh tính được phép, giao thức, cổng, đường đi, phương án phục hồi và nơi ghi log**.

Một máy có nhiều giao diện không có nghĩa được phép quản trị từ mọi giao diện. Nên giới hạn dịch vụ quản trị lắng nghe trên giao diện/địa chỉ phù hợp nếu nền tảng hỗ trợ, đồng thời dùng chính sách mạng ở nơi có thể cưỡng chế.

### 6.2. Bảo vệ lối vào mạng quản trị

- Xác thực người dùng bằng **MFA** và quản lý quyền tập trung khi phù hợp; áp dụng quyền tối thiểu theo vai trò (RBAC) và thời hạn truy cập.
- Dùng **VPN hoặc ZTNA** và cổng trung gian như **bastion/jump host** khi thích hợp. Đường truyền được mã hóa **không** đồng nghĩa với quyền quản trị không giới hạn.
- Với quyền nhạy cảm, cân nhắc **privileged access management (PAM)**, cấp quyền tạm thời (**just-in-time**), phê duyệt nghiệp vụ và ghi nhận phiên theo quy định.
- Kiểm tra trạng thái thiết bị đầu cuối nếu có khả năng: thiết bị quản lý, cập nhật, chống mã độc, lưu khóa an toàn.
- Có tài khoản/đường **break-glass** cho tình huống cấp bách; bảo vệ nghiêm ngặt, thử khả năng sử dụng và giám sát sau khi dùng.

### 6.3. Áp dụng phân đoạn và chính sách deny-by-default

Cho phép từng nguồn quản trị đi đến đúng đích và giao thức cần thiết. Tránh các quy tắc kiểu “VPN được tới toàn bộ các dải nội bộ” hoặc “mọi workload được vào management subnet”. Tách mạng người dùng, mạng khách Wi-Fi và IoT khỏi khu quản trị. Trường hợp bắt buộc truy cập giao diện quản trị từ mạng dữ liệu, hãy định nghĩa luồng đặc biệt, người sở hữu và biện pháp bù trừ, thay vì mở một đường hai chiều rộng.

Kiểm soát cả kết nối ra ngoài từ mạng quản trị: các hệ thống này có thể cần DNS, NTP, repository cập nhật hoặc hệ thống giám sát, nhưng không nên tự động kết nối mọi đích Internet. Tránh để một bộ lọc quá nghiêm khiến xác thực, cấp chứng chỉ, đồng bộ thời gian hay khôi phục bị hỏng; thiết kế cần có danh sách phụ thuộc và thử nghiệm.

### 6.4. Bảo vệ giao thức và cấu hình

Ưu tiên SSH, HTTPS/TLS được cấu hình phù hợp; dùng **SNMPv3 với mức bảo vệ thích hợp** thay cho các cơ chế cộng đồng SNMP cũ thiếu bảo vệ khi có thể. Vô hiệu dịch vụ quản trị không dùng và giao thức truyền thông tin xác thực dạng rõ. Quản lý khóa SSH, chứng chỉ, mật khẩu và secret theo vòng đời; cập nhật firmware, hệ điều hành và công cụ điều khiển.

Không giả định mọi cổng 443 đều là kết nối an toàn: cần xác minh danh tính máy chủ/chứng chỉ và chính sách ứng dụng. Không ghi mật khẩu, token hay khóa riêng vào log hoặc tài liệu sơ đồ mạng.

### 6.5. Quan sát và khả năng khôi phục

Thu thập log đăng nhập, thay đổi cấu hình, nâng quyền, phiên quản trị, sự kiện firewall, thiết bị mạng, DNS và giám sát kết nối. Cân nhắc thiết kế collector tập trung, truyền log bảo vệ, lưu giữ theo nhu cầu và đồng bộ thời gian. Tạo cảnh báo đối với đăng nhập lạ, cấu hình ACL thay đổi, truy cập BMC bất thường và hoạt động quản trị ngoài khung dự kiến.

Sao lưu cấu hình và lưu bản cấu hình có thể khôi phục, phân quyền ai được xem/khôi phục, định kỳ thử đường OOB và quy trình xử lý khi mất đường data. Một đường quản trị có ý nghĩa khi nhân sự có thể **thực sự sử dụng nó trong điều kiện lỗi đã giả định**.

## 7. Liên hệ kiến trúc cloud và container

Trong cloud, không phải lúc nào cũng tồn tại một “management VLAN” vật lý. Cần tách hai bình diện:

1. **Đường truy cập quản trị workload:** truy cập VM, máy chủ, cluster và dịch vụ mà tổ chức vận hành. Có thể dùng private subnet, VPN, kết nối riêng, identity-aware access, session manager hoặc bastion; hạn chế mở SSH/RDP ra Internet.
2. **Cloud control plane:** API/IAM/console để tạo hoặc thay đổi mạng ảo, route, security group, VM, database, secret và khóa. Những API này có thể nằm ngoài đường truyền data của VPC/VNet. Bảo vệ bằng IAM, MFA, phân quyền vai trò, giới hạn nguồn/điều kiện khi được hỗ trợ, logging và quy trình thay đổi.

Ví dụ: database ở private subnet vẫn có thể bị phơi bày nếu ai đó có quyền quá rộng thay đổi security group hoặc bật endpoint công khai. Vì vậy, bảo mật mạng cloud luôn cần đi cùng **bảo mật danh tính và control plane**.

### Ánh xạ vào các môi trường thường gặp

| Môi trường | Data network / luồng dữ liệu | Thành phần quản trị | Kiểm soát tiêu biểu |
|---|---|---|---|
| Trung tâm dữ liệu vật lý | VLAN/subnet ứng dụng, kết nối máy chủ và lưu trữ | Cổng quản trị router/switch, hypervisor, BMC | Management VLAN/VRF, bastion, OOB, ACL, MFA, log |
| VM trên cloud | VPC/VNet, subnet riêng/công khai, đường tới dịch vụ | Session manager, OS management endpoint, cloud console/API | Security group, private endpoint, IAM, audit log |
| Kubernetes | Pod-to-pod, Service, ingress, egress ứng dụng | Kubernetes API, node, kubelet, bộ điều khiển và công cụ triển khai | RBAC, xác thực API, network policy, giới hạn quyền node, log |
| Văn phòng/Wi-Fi | Kết nối nhân viên, thiết bị IoT, mạng khách | Giao diện quản trị AP, switch và hệ thống quản lý Wi-Fi | Mạng quản trị riêng, Wi-Fi doanh nghiệp, phân đoạn khách/IoT, MFA |

Với **Kubernetes**, đừng nhầm control plane của cluster với một subnet quản trị tự động an toàn. RBAC quyết định thao tác qua Kubernetes API; network policy (khi CNI hỗ trợ và thực thi) kiểm soát những luồng mạng phù hợp, nhưng không thay thế bảo vệ API, node hay thông tin xác thực.

Với **hạ tầng đa đám mây hoặc kết nối on-premises ↔ cloud**, việc nối hai mạng riêng cũng tạo ra đường đi mới. Cần rà soát định tuyến, quyền xuyên môi trường, DNS, logging và các vùng được phép trao đổi, đặc biệt khi mở private peering hoặc VPN site-to-site.

## 8. Mô hình hóa mối đe dọa cho management network

Để đánh giá thiết kế, hãy bắt đầu bằng tài sản, ranh giới tin cậy và một số tình huống cụ thể:

| Tình huống | Tài sản/rủi ro | Kiểm soát nên cân nhắc | Bằng chứng kiểm chứng |
|---|---|---|---|
| Web server bị chiếm và thử vào SSH của hypervisor | Toàn bộ máy ảo, dữ liệu và tính sẵn sàng | Tách management zone, deny từ app subnet, kiểm soát endpoint quản trị | Kiểm tra kết nối sai vùng bị chặn, cảnh báo từ firewall |
| Tài khoản VPN bị lộ | Quyền điều khiển thiết bị và dữ liệu cấu hình | MFA, quyền theo vai trò, kiểm tra thiết bị, cấp quyền có thời hạn | Log phiên và danh sách đích thực tế truy cập được |
| Đường uplink dùng chung bị hỏng | Mất truy cập quản trị trong khi dịch vụ gián đoạn | OOB độc lập hợp lý, đường/phương tiện dự phòng | Diễn tập mất đường data và thử truy cập OOB |
| Quản trị BMC bằng mật khẩu mặc định | Chiếm điều khiển mức phần cứng, gây gián đoạn | Đổi thông tin xác thực, giới hạn nguồn, cập nhật firmware, log | Kiểm kê BMC, kiểm tra quyền và phiên đăng nhập |
| Tài khoản cloud có thể sửa mọi security group | Mở dịch vụ quản trị hoặc database ra Internet | IAM tối thiểu, bảo vệ thay đổi, giám sát cấu hình | Audit event, kiểm tra quyền và cảnh báo thay đổi |
| Máy quản trị bị nhiễm mã độc | Di chuyển ngang sang các hệ thống đặc quyền | Thiết bị quản trị chuyên dụng hoặc được quản lý, MFA/PAM, giới hạn phiên | Kiểm tra posture, log phiên, giới hạn đích đã thử |
| Thiếu hoặc bị xóa log quản trị | Mất bằng chứng, khó phát hiện thay đổi trái phép | Collector tập trung, quyền lưu trữ bất biến khi phù hợp | Thử phát log và phân quyền xóa/sửa, kiểm tra cảnh báo |

Một phương pháp đơn giản là vẽ **nguồn → ranh giới → đích → quyền có thể đạt được** cho từng đường tấn công. Sau đó hỏi: nếu chỉ một máy ứng dụng hoặc một tài khoản bị xâm nhập, kẻ tấn công có thể đến được những giao diện quản trị nào và ở đó làm gì?

### Tình huống minh họa: phân đoạn chỉ tồn tại trên sơ đồ

Một tổ chức đặt mạng quản trị và dữ liệu ở hai VLAN nhưng dùng rule firewall **allow any** giữa chúng để giảm lỗi vận hành. Trong thực tế, máy ứng dụng vẫn có thể truy cập SSH, HTTPS quản trị và BMC ở vùng quản trị. **Có VLAN riêng chưa chứng minh đã có ranh giới bảo mật.** Cần sửa ma trận cho phép theo từng nhu cầu, áp dụng quy tắc chặn mặc định, rồi xác minh các kết nối từ data zone đến management zone thực sự bị từ chối.

## 9. Kiểm tra phân tách và đường đi trên hệ thống thật

Việc kiểm chứng phải thực hiện trong môi trường được phép quản trị, dùng tài khoản và phạm vi đã được phê duyệt. Một kiểm tra tốt có **cặp ca đối xứng**: một luồng nghiệp vụ hợp lệ phải thành công và một luồng không có quyền phải bị từ chối.

### Bước 1: ghi nhận kỳ vọng

Trước khi thử, lập bảng cho mỗi ca: nguồn, đích, cổng/giao thức, chính sách mong đợi, nơi kiểm chứng (log firewall, log gateway, log ứng dụng), người sở hữu. Ví dụ:

| Kiểm tra | Kết quả mong đợi | Ý nghĩa |
|---|---|---|
| Người học → HTTPS gateway | Thành công | Data path hoạt động |
| Backend API → database | Thành công trong phạm vi quyền ứng dụng | Luồng dữ liệu nội bộ hợp lệ |
| Workload frontend → địa chỉ BMC/SSH quản trị | Bị từ chối | Không vượt ranh giới sang quản trị |
| Bastion của quản trị viên đã xác thực → thiết bị được cấp quyền | Thành công và có log | Truy cập đặc quyền theo chính sách |
| Bastion → thiết bị ngoài phạm vi cấp quyền | Bị từ chối | Quyền tối thiểu có hiệu lực |
| Ngắt đường data theo kịch bản diễn tập → truy cập OOB | Vẫn có thể phục hồi trong phạm vi thiết kế | Xác minh mức độc lập đường quản trị |

### Bước 2: quan sát địa chỉ, định tuyến và cổng đang mở

Trên Linux, một số lệnh **đọc trạng thái** hữu ích:

~~~bash
# Hiển thị interface, địa chỉ IPv4/IPv6 và đường mặc định
ip -br address
ip route
ip -6 route

# Liệt kê socket TCP/UDP đang lắng nghe (quyền xem tên tiến trình tùy máy)
ss -lntup

# Nếu cần kiểm tra policy routing / nhiều bảng định tuyến
ip rule show
ip route show table all
~~~

Các lệnh trên chỉ cho biết **trạng thái từ điểm đang đứng**. Chúng không chứng minh firewall hoặc route trên toàn mạng hoạt động đúng. Hãy kết hợp với sơ đồ, bảng chính sách và log của thiết bị kiểm soát tại ranh giới.

### Bước 3: kiểm tra kết nối từ đúng vùng nguồn

Nếu được phép thử kết nối tới cổng cụ thể:

~~~bash
# Ví dụ chạy từ máy trong vùng API, tới một DB test đã cho phép
nc -vz -w 3 10.20.30.10 5432

# Ví dụ chạy từ máy trong vùng frontend, tới cổng quản trị không được phép
nc -vz -w 3 10.10.10.10 22
~~~

Dòng đầu **dự kiến thành công**, dòng sau **dự kiến bị chặn** theo kiến trúc minh họa. Một thông báo kết nối thất bại có thể do routing, firewall, dịch vụ không lắng nghe hoặc lỗi tạm thời; **không tự động chứng minh một rule bảo mật đã chặn**. Cần đối chiếu log và nguyên nhân. Cũng không nên suy ra quyền đăng nhập hợp lệ chỉ từ việc mở được kết nối TCP.

Trên Windows, có thể kiểm tra cổng đến một đích được phê duyệt bằng PowerShell:

~~~powershell
Test-NetConnection -ComputerName 10.20.30.10 -Port 5432
~~~

### Bước 4: quan sát log, cấu hình và trạng thái khôi phục

Đối chiếu bản ghi firewall theo IP nguồn/đích, giao thức, thời điểm, rule, lý do chặn; đối chiếu log xác thực và phiên quản trị. Xác minh thay đổi route, VLAN, VRF, security group hoặc policy được kiểm soát và phát hiện khi lệch chuẩn. Trường hợp có OOB, diễn tập theo quy trình đã thống nhất với đội vận hành; không tự ý ngắt dịch vụ production.

### Cách diễn giải một mẫu log

~~~text
2026-11-28T02:10:12Z action=ALLOW src=10.20.20.14 dst=10.20.30.10 proto=TCP dport=5432 rule=api-to-db
2026-11-28T02:10:13Z action=DENY  src=10.20.10.18 dst=10.10.10.10 proto=TCP dport=22   rule=deny-data-to-management
2026-11-28T02:10:18Z action=ALLOW src=10.10.10.5  dst=10.10.10.10 proto=TCP dport=22   rule=bastion-to-managed-host
~~~

Dòng một cho thấy luồng nghiệp vụ nội bộ được cho phép; dòng hai cho thấy nguồn thuộc data zone bị chặn khi thử tới cổng quản trị; dòng ba là truy cập từ bastion đến đích quản trị. **Ba dòng chưa đủ kết luận hệ thống an toàn**: cần xác minh đúng danh tính, phạm vi rule, các giao thức khác, IPv6, luồng chiều ra và điều kiện thay đổi chính sách. Địa chỉ và nhật ký trên là dữ liệu mô phỏng.

## 10. Những sai lầm phổ biến trong thiết kế và vận hành

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “Có VLAN quản trị là đã cách ly hoàn toàn.” | Cần kiểm tra định tuyến liên VLAN, firewall, quyền truy cập, đường vào từ xa và cấu hình thực tế. |
| “Mạng quản trị phải luôn có cáp riêng.” | Có thể tách logic hoặc vật lý tùy yêu cầu; chọn theo rủi ro, chi phí và mục tiêu phục hồi. |
| “Đã vào VPN thì có thể SSH mọi máy.” | VPN bảo vệ đường kết nối; quyền đến từng tài sản vẫn phải được xác thực, phân quyền và ghi nhận. |
| “Out-of-band không có rủi ro.” | BMC/console cho quyền cao, có thể bị chiếm hoặc phụ thuộc vào hạ tầng chung; cần bảo vệ đặc biệt. |
| “Management network là management plane.” | Một khái niệm là đường/miền mạng, khái niệm còn lại là chức năng quản lý thiết bị và dịch vụ. |
| “Data network chỉ chứa Internet traffic.” | Còn có lưu lượng east–west giữa các workload, API, database và lưu trữ. |
| “Ứng dụng trong cloud có private subnet thì đã an toàn.” | Phải bảo vệ thêm cloud IAM/API, security group, định tuyến, endpoint và đường quản trị workload. |
| “Không mở cổng SSH ra Internet thì không cần giám sát.” | Truy cập nội bộ, VPN, bastion và đặc quyền bị lạm dụng cũng cần phát hiện. |
| “Kết nối TCP thành công nghĩa là truy cập đã được ủy quyền.” | Mở được socket chưa chứng minh xác thực/phân quyền ứng dụng, người dùng hoặc lệnh quản trị hợp lệ. |

## 11. Bài tập tình huống

**Bài tập 1 — Phân loại luồng.** Hãy phân loại các luồng theo mục đích chính: (a) học viên gửi yêu cầu HTTPS để mở bài học; (b) kỹ sư kết nối SSH vào switch; (c) API truy vấn database; (d) SIEM nhận syslog từ firewall; (e) router trao đổi thông tin định tuyến với router khác.

**Gợi ý:** (a), (c) là data network; (b) là truy cập quản trị; (d) là telemetry/giám sát thuộc hoạt động quản trị; (e) là control-plane traffic. Lưu ý tên của loại lưu lượng chưa cho biết cáp, VLAN hoặc subnet nào đang chở nó.

**Bài tập 2 — Thiết kế mạng cho hai môi trường.** Một doanh nghiệp có các dịch vụ public web, API, database, router, switch, hypervisor và thiết bị của nhân viên. Hãy đề xuất hai phương án:

1. Một phương án dùng hạ tầng chung nhưng tách management VLAN/VRF và đặt firewall/bastion ở ranh giới.
2. Một phương án có thêm OOB cho thiết bị trọng yếu, kiểm tra mức độc lập về tuyến, nguồn điện và cơ chế vào khẩn cấp.

Với mỗi phương án, viết tối thiểu sáu dòng chính sách nguồn → đích, xác định ai được phép sửa cấu hình firewall và nêu cách kiểm tra khi frontend bị xâm nhập. Không phải thiết bị nào cũng cần cùng một mức độ tách biệt; hãy giải thích dựa vào tác động khi mất quyền điều khiển hoặc mất đường khôi phục.

**Bài tập 3 — Phân tích sự cố.** Một thay đổi cấu hình router khiến API mất kết nối tới database. Đội vận hành chỉ dùng jump host nằm trên cùng uplink với ứng dụng nên không đăng nhập được router. Hãy đề xuất biện pháp phòng ngừa và quy trình khôi phục.

**Gợi ý:** xét sao lưu cấu hình, kiểm soát thay đổi, kiểm tra luồng trước/sau triển khai, đường quản trị dự phòng/OOB và cách xác thực người có quyền sử dụng đường đó. Kiểm tra cả các phụ thuộc dùng chung như switch trung gian, điện và hệ thống định danh.

## 12. Checklist triển khai thực tế

- [ ] Đã kiểm kê tài sản và giao diện quản trị (bao gồm BMC, hypervisor, API cloud, thiết bị mạng, Wi-Fi).
- [ ] Đã phân loại từng luồng theo **mục đích**: dữ liệu nghiệp vụ, quản trị, control plane, giám sát hoặc lưu trữ.
- [ ] Đã vẽ các vùng và ranh giới tin cậy, xác định nguồn/đích/cổng và điểm thực thi chính sách.
- [ ] Không công khai trực tiếp các giao diện quản trị không cần thiết ra Internet.
- [ ] Có MFA, phân quyền tối thiểu và kiểm soát phiên đặc quyền phù hợp.
- [ ] Data zone bị giới hạn khi truy cập management zone; có thử từ đúng vị trí nguồn.
- [ ] Có log truy cập quản trị, thay đổi cấu hình và sự kiện từ chối; thời gian và quyền bảo vệ log phù hợp.
- [ ] Với cloud, đã xét riêng IAM/API control plane, security group, private endpoint và audit log.
- [ ] Có phương án khôi phục quản trị khi data path hỏng; đã thử đường in-band/OOB theo yêu cầu sẵn sàng.
- [ ] Đã xác minh các kết nối nghiệp vụ hợp lệ vẫn hoạt động sau khi siết chính sách.

## Ghi nhớ

**Management network bảo vệ khả năng điều khiển và vận hành hạ tầng; data network phục vụ luồng dữ liệu của nghiệp vụ.** Mục tiêu phân tách là giảm đường đi từ vùng ít tin cậy đến quyền quản trị, tạo khả năng giám sát rõ ràng và duy trì đường phục hồi. Sự phân tách có thể là logic, vật lý hoặc kết hợp, nhưng phải được chứng minh bằng **ma trận luồng, xác thực/phân quyền, chính sách cưỡng chế, log và kiểm thử cả tình huống thành công lẫn bị từ chối**.

Khi đọc một sơ đồ mạng, luôn đặt ba câu hỏi: **Ai đang gửi lưu lượng? Họ cần dùng dịch vụ hay điều khiển hạ tầng? Nếu đường dữ liệu bị chiếm hoặc bị gián đoạn, đường quản trị còn an toàn và còn sử dụng được không?**
