# Thiết kế CIDR cho VCN và phòng tránh chồng lấn địa chỉ

Một Virtual Cloud Network (VCN) có thể hoạt động tốt khi đứng riêng nhưng gặp vấn đề ngay khi kết nối với trung tâm dữ liệu, VCN khác hoặc mạng đối tác. Nguyên nhân thường là hai bên cùng sử dụng một dải IP, chẳng hạn cùng chọn 10.0.0.0/16. Khi đó, hệ thống định tuyến không thể chỉ nhìn địa chỉ đích để biết máy chủ mà người gửi thực sự muốn truy cập nằm ở mạng nào.

Trong Oracle Cloud Infrastructure (OCI), thiết kế CIDR là nền móng cho VCN, subnet, kết nối hybrid và nhiều dịch vụ Compute, lưu trữ, cơ sở dữ liệu. Một phương án tốt phải đáp ứng đồng thời nhu cầu địa chỉ hiện tại, khả năng mở rộng, phân tách môi trường và kết nối tương lai. Compartment và IAM giúp quản lý quyền; chúng không tạo ra tính duy nhất cho địa chỉ mạng.

Bài học này hướng dẫn lập kế hoạch IPv4 cho VCN, kiểm tra chồng lấn và lựa chọn cách xử lý khi phát hiện xung đột. Các địa chỉ trong ví dụ là dữ liệu giả định để học; cần đối chiếu với quỹ địa chỉ thực tế trước khi triển khai.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Đọc một CIDR và xác định dải địa chỉ mà nó bao phủ.
- Ước lượng kích thước subnet từ số IP cần dùng và mức tăng trưởng.
- Phân bổ địa chỉ theo tổ chức, môi trường, region, VCN và subnet.
- Phát hiện chồng lấn ngay cả khi hai CIDR có cách viết khác nhau.
- Giải thích vì sao route table, NSG, IAM hoặc compartment không tự khắc phục được trùng địa chỉ.
- Xây dựng quy trình kiểm tra trước khi tạo VCN, thêm CIDR hoặc mở kết nối mạng.

## 2. CIDR mô tả một tập địa chỉ

### 2.1. Ý nghĩa của tiền tố

IPv4 có 32 bit. CIDR viết dưới dạng địa chỉ mạng và độ dài tiền tố, ví dụ **10.64.4.0/22**:

- 22 bit đầu xác định phần mạng.
- 10 bit còn lại biểu diễn các địa chỉ trong dải.
- Tổng số địa chỉ là 2^(32 - 22) = 1.024.

Tiền tố càng dài thì dải càng nhỏ. Vì vậy, /24 chứa ít địa chỉ hơn /22.

| CIDR mẫu | Tổng số địa chỉ | Địa chỉ đầu | Địa chỉ cuối |
| --- | ---: | --- | --- |
| 10.64.0.0/16 | 65.536 | 10.64.0.0 | 10.64.255.255 |
| 10.64.0.0/20 | 4.096 | 10.64.0.0 | 10.64.15.255 |
| 10.64.4.0/22 | 1.024 | 10.64.4.0 | 10.64.7.255 |
| 10.64.8.0/23 | 512 | 10.64.8.0 | 10.64.9.255 |
| 10.64.10.0/24 | 256 | 10.64.10.0 | 10.64.10.255 |
| 10.64.10.0/26 | 64 | 10.64.10.0 | 10.64.10.63 |
| 10.64.10.64/27 | 32 | 10.64.10.64 | 10.64.10.95 |

Tổng số địa chỉ của một dải khác với số địa chỉ có thể cấp cho tài nguyên. Trong subnet IPv4 của OCI, hai địa chỉ đầu và địa chỉ cuối được dành riêng. Ví dụ, subnet 10.64.10.0/24 có 256 địa chỉ, trong đó .0, .1 và .255 được dành riêng; còn 253 địa chỉ có thể cấp.

Một dịch vụ có thể sử dụng nhiều địa chỉ cho một thành phần logic. Số IP còn trống sau khi triển khai sẽ phụ thuộc cả các IP chính, IP phụ và các endpoint do dịch vụ tạo ra.

### 2.2. Địa chỉ mạng phải đúng biên

Với /22, subnet mask là 255.255.252.0. Trong phạm vi 10.64.x.x, octet thứ ba của địa chỉ mạng phải bắt đầu tại bội số của 4:

~~~text
10.64.0.0/22  -> 10.64.0.0 đến 10.64.3.255
10.64.4.0/22  -> 10.64.4.0 đến 10.64.7.255
10.64.8.0/22  -> 10.64.8.0 đến 10.64.11.255
~~~

Cách viết 10.64.5.0/22 có các bit host khác 0, nên không phải biểu diễn địa chỉ mạng chuẩn. Nếu chuẩn hóa theo mask, nó thuộc mạng 10.64.4.0/22. Công cụ kiểm tra đầu vào có thể từ chối cách viết không chuẩn; không nên dựa vào việc công cụ sẽ tự sửa giúp.

Một lỗi phổ biến là nhìn số 5 và nghĩ dải bắt đầu ở 10.64.5.0, từ đó bỏ sót việc nó chồng lên subnet 10.64.4.0/24.

### 2.3. Phân biệt CIDR của VCN và subnet

CIDR của VCN xác định không gian địa chỉ mà VCN sử dụng. CIDR của subnet là một phần nằm trong không gian đó.

Ví dụ:

~~~text
VCN: 10.64.0.0/20
  Subnet edge: 10.64.0.0/24
  Subnet app:  10.64.4.0/22
  Subnet data: 10.64.8.0/23
~~~

Mỗi subnet phải nằm trọn trong một CIDR phù hợp của VCN, và các subnet trong VCN không được chồng lấn nhau. Nếu VCN có nhiều khối IPv4, cần kiểm tra theo từng khối thay vì gộp chúng thành một vùng liên tục tưởng tượng.

Subnet 10.64.16.0/24 không nằm trong VCN 10.64.0.0/20, vì VCN này kết thúc ở 10.64.15.255.

## 3. Xác định phạm vi phải duy nhất

### 3.1. Không chỉ kiểm tra bên trong một VCN

Tính duy nhất cần được xem xét trên toàn bộ phạm vi mạng dự kiến có kết nối hoặc trao đổi lưu lượng:

- Các VCN trong cùng tenancy hoặc khác tenancy.
- Các region dùng cho production, dự phòng hoặc mở rộng.
- Trung tâm dữ liệu và văn phòng kết nối qua Site-to-Site VPN hoặc FastConnect.
- Mạng đối tác, công ty được sáp nhập và các cloud khác.
- Dải mạng của VPN người dùng, hệ thống container và các mạng ảo bên trong máy chủ.

Một dải pod hoặc service không được quảng bá trực tiếp vẫn có thể gây xung đột trên máy có route tới dải đó. Do đó, cần ghi rõ dải nào được định tuyến xuyên mạng, dải nào chỉ tồn tại nội bộ và có cơ chế dịch địa chỉ nào ở giữa.

Hai môi trường cô lập có thể sử dụng cùng CIDR về mặt kỹ thuật. Tuy nhiên, nếu chúng phải kết nối sau này, khoản tiết kiệm công sức lúc đầu có thể biến thành một dự án đổi địa chỉ. Nên cấp dải riêng cho các môi trường có khả năng cần liên thông.

### 3.2. Chọn không gian địa chỉ riêng

Các dải IPv4 riêng theo RFC 1918 gồm:

| Dải | Khoảng địa chỉ |
| --- | --- |
| 10.0.0.0/8 | 10.0.0.0 đến 10.255.255.255 |
| 172.16.0.0/12 | 172.16.0.0 đến 172.31.255.255 |
| 192.168.0.0/16 | 192.168.0.0 đến 192.168.255.255 |

“Riêng” có nghĩa là các địa chỉ này không được định tuyến công khai trên Internet; nó không có nghĩa là tổ chức khác sẽ không sử dụng cùng dải.

Không phải mọi địa chỉ bắt đầu bằng 172 đều là địa chỉ riêng. Ví dụ, 172.32.0.0 không thuộc 172.16.0.0/12.

Tương tự, 100.64.0.0/10 là không gian địa chỉ dùng chung, không phải một dải RFC 1918. Không nên lấy nó làm “quỹ địa chỉ riêng còn dư” mà chưa đánh giá môi trường nhà mạng, VPN, container và các yêu cầu của dịch vụ liên quan.

Việc chọn CIDR cho mạng nội bộ cũng không phải lý do để lấy tùy ý một dải IP công cộng của bên khác.

### 3.3. Compartment, IAM và tên môi trường không chia tách địa chỉ

Các cấu trúc sau có những vai trò khác nhau:

| Thành phần | Vai trò chính trong bài toán |
| --- | --- |
| Compartment | Tổ chức và quản trị tài nguyên |
| IAM policy | Quy định ai có quyền thực hiện thao tác |
| VCN và subnet | Xác định mạng và phạm vi địa chỉ |
| Route table | Quyết định đường đi của lưu lượng |
| NSG, security list | Cho phép hoặc hạn chế lưu lượng theo quy tắc |
| Sổ đăng ký địa chỉ/IPAM | Quản lý việc cấp phát và tránh cấp trùng |

Đặt VCN-A và VCN-B ở hai compartment khác nhau không làm cho hai khối 10.64.0.0/20 trở nên không chồng lấn. Đặt tên một mạng là “private” cũng không tạo ra cơ chế cách ly thay cho route và quy tắc bảo mật.

## 4. Tính kích thước từ nhu cầu IP thực

### 4.1. Kiểm kê theo thành phần

Không nên chọn subnet chỉ bằng số lượng máy ảo đang chạy. Hãy lập ngân sách IP cho:

- VNIC và các private IP phụ của Compute.
- Node và pod nếu mô hình mạng của nền tảng container sử dụng IP từ subnet.
- Load balancer, endpoint riêng và tài nguyên mạng do dịch vụ quản lý.
- Các cấu hình cơ sở dữ liệu sử dụng nhiều địa chỉ hoặc có yêu cầu subnet riêng.
- Tài nguyên tồn tại đồng thời trong rolling update, blue-green deployment hoặc khôi phục sự cố.
- Mức tăng trưởng dự kiến trong chu kỳ vận hành.

Với dịch vụ cơ sở dữ liệu Oracle, cần kiểm tra yêu cầu mạng của đúng dịch vụ và cấu hình lựa chọn. Không dùng một con số IP cố định cho mọi kiểu triển khai Database, RAC hoặc Exadata.

### 4.2. Công thức ước lượng

Có thể bắt đầu bằng mô hình:

~~~text
Nhu cầu đỉnh = IP cố định
              + tổng(số tài nguyên đỉnh từng nhóm × số IP mỗi tài nguyên)

Ngân sách IP = làm tròn lên(Nhu cầu đỉnh × (1 + tỷ lệ dự phòng))
~~~

Sau đó chọn subnet có số IP cấp được lớn hơn hoặc bằng ngân sách, đồng thời đáp ứng yêu cầu của từng dịch vụ.

Ví dụ một tầng ứng dụng nhỏ:

- Lúc bình thường có 30 instance.
- Trong mở rộng và triển khai cuốn chiếu, tối đa có 80 instance tồn tại đồng thời.
- Mỗi instance dùng 2 private IP.
- Có thêm 20 IP cho các thành phần khác trong cùng subnet.
- Dự phòng thêm 25%.

~~~text
Nhu cầu đỉnh = 80 × 2 + 20 = 180 IP
Ngân sách IP = ceil(180 × 1,25) = 225 IP

/25: 128 địa chỉ tổng, 125 địa chỉ cấp được -> không đủ
/24: 256 địa chỉ tổng, 253 địa chỉ cấp được -> đủ theo giả định
~~~

Kết luận này chỉ đúng nếu toàn bộ giả định đã bao gồm nhu cầu của dịch vụ và mức chạy đồng thời. Nếu 80 instance là số máy thường trực, còn blue-green cần thêm 80 máy, phải tính lại.

Với subnet regional, ngân sách cần tính tổng tài nguyên trong tất cả availability domain sử dụng subnet đó. Nếu số đỉnh đã là tổng toàn hệ thống thì không nhân thêm một lần nữa theo số availability domain.

### 4.3. Cân bằng giữa dư địa và sử dụng hiệu quả

Subnet quá nhỏ gây khó khăn khi mở rộng hoặc thay thế tài nguyên. Subnet quá lớn chiếm một phần quỹ địa chỉ mà môi trường khác có thể cần.

Số địa chỉ riêng được để trống không tự tạo ra chi phí Compute hoặc chi phí IP công cộng. Tuy nhiên, phân bổ lãng phí có thể gây chi phí vận hành sau này: đổi địa chỉ, thêm thiết bị NAT hoặc tổ chức lại kết nối hybrid.

Cách thực tế là chọn kích thước theo một khoảng thời gian tăng trưởng cụ thể, giữ các dải dự phòng liền kề và rà soát lại khi kiến trúc thay đổi.

## 5. Phân bổ theo tầng và ghi rõ vùng dự phòng

### 5.1. Từ quỹ tổ chức đến VCN

Giả sử đội mạng đã xác nhận có thể dành 10.64.0.0/12 cho hạ tầng cloud của tổ chức. Dải này bao phủ 10.64.0.0 đến 10.79.255.255.

Có thể lập kế hoạch như sau:

| Mục đích | Khối giữ chỗ trong IPAM | CIDR VCN tạo ở giai đoạn đầu |
| --- | --- | --- |
| Production, region chính | 10.64.0.0/16 | 10.64.0.0/20 |
| Staging | 10.65.0.0/16 | 10.65.0.0/20 |
| Development | 10.66.0.0/16 | 10.66.0.0/20 |
| Chưa phân bổ | 10.67.0.0/16 | Chưa tạo |
| Production, region dự phòng | 10.68.0.0/16 | 10.68.0.0/20 |

**Khối giữ chỗ trong IPAM không đồng nghĩa với CIDR đã cấu hình trên VCN.** Trong ví dụ này, VCN production ban đầu chỉ có 10.64.0.0/20. Phần còn lại của 10.64.0.0/16 được đội mạng giữ lại để phục vụ kế hoạch mở rộng.

Nếu cấu hình cả 10.64.0.0/16 cho VCN hiện tại, không được xem 10.64.16.0/20 là dải còn rảnh để cấp cho một VCN cần kết nối với nó. Dải con đó đã nằm trong CIDR của VCN hiện tại, dù chưa có subnet sử dụng.

Việc chia theo /16 và /20 ở đây là ví dụ tổ chức địa chỉ, không phải quy tắc bắt buộc cho mọi hệ thống. Một hệ thống nhỏ có thể sử dụng các khối nhỏ hơn sau khi đã tính nhu cầu và kiểm tra giới hạn OCI áp dụng.

### 5.2. Chia subnet cho VCN production

Xét VCN **10.64.0.0/20**, từ 10.64.0.0 đến 10.64.15.255:

| Vai trò | CIDR | Khoảng địa chỉ | IP cấp được trong subnet IPv4 |
| --- | --- | --- | ---: |
| Edge, chẳng hạn load balancer | 10.64.0.0/24 | 10.64.0.0–10.64.0.255 | 253 |
| Ứng dụng | 10.64.4.0/22 | 10.64.4.0–10.64.7.255 | 1.021 |
| Dữ liệu | 10.64.8.0/23 | 10.64.8.0–10.64.9.255 | 509 |
| Endpoint dịch vụ riêng | 10.64.10.0/24 | 10.64.10.0–10.64.10.255 | 253 |
| Công cụ vận hành | 10.64.11.0/24 | 10.64.11.0–10.64.11.255 | 253 |

Tầng ứng dụng của ví dụ này giả định ngân sách lớn hơn ví dụ nhỏ ở phần trước: cần khoảng 700 IP ở đỉnh, nên /24 không đủ và /22 cung cấp dư địa phù hợp với giả định đó.

Các phần chưa tạo subnet:

~~~text
10.64.1.0/24  : dự phòng gần tầng edge
10.64.2.0/23  : dự phòng cho nhu cầu bổ sung
10.64.12.0/22 : dự phòng cho một tầng ứng dụng hoặc cụm mới
~~~

Toàn bộ các dải này đều nằm trong /20 và không chồng lấn.

Phần 10.64.12.0/22 không liền kề subnet app 10.64.4.0/22, vì ở giữa đã có các subnet dữ liệu và endpoint. Nó có thể phục vụ một subnet mới, nhưng không phải bằng chứng rằng subnet app hiện tại có thể được nới thành một /21.

Thực tế, mở rộng 10.64.4.0/22 thành khối /21 bao chứa nó sẽ liên quan đến 10.64.0.0/21, nơi đã có subnet edge. Đây là lý do cần kiểm tra cả biên CIDR và các dải đã cấp trước khi dự định mở rộng tại chỗ.

~~~mermaid
flowchart TD
    A["Quỹ tổ chức: 10.64.0.0/12"] --> B["Giữ chỗ production: 10.64.0.0/16"]
    A --> C["Giữ chỗ staging: 10.65.0.0/16"]
    A --> D["Giữ chỗ DR: 10.68.0.0/16"]
    B --> E["VCN production: 10.64.0.0/20"]
    E --> F["Edge: 10.64.0.0/24"]
    E --> G["App: 10.64.4.0/22"]
    E --> H["Data: 10.64.8.0/23"]
    E --> I["Endpoint: 10.64.10.0/24"]
    E --> J["Vận hành: 10.64.11.0/24"]
    E --> K["Dải dự phòng được ghi trong IPAM"]
~~~

Sơ đồ thể hiện quan hệ cấp phát địa chỉ, không thể hiện đường đi lưu lượng hay cấu hình route.

### 5.3. CIDR và tính sẵn sàng

VCN thuộc phạm vi region. OCI có subnet regional và subnet gắn với một availability domain; subnet regional giúp cùng một subnet phục vụ tài nguyên ở nhiều availability domain của region khi dịch vụ hỗ trợ.

Không cần tạo một dải IP riêng cho mỗi availability domain chỉ vì tên của chúng khác nhau. Quyết định chia subnet cần dựa vào kiến trúc, yêu cầu dịch vụ và chính sách vận hành.

Ngược lại, region dự phòng nên có dải riêng khi có khả năng kết nối với region chính. Sử dụng lại CIDR production cho region DR có thể gây xung đột trong diễn tập, đồng bộ dữ liệu hoặc failback, khi cả hai môi trường cần hoạt động cùng lúc.

CIDR hợp lý tạo điều kiện triển khai tính sẵn sàng; nó không tự bảo đảm HA nếu toàn bộ ứng dụng hoặc cơ sở dữ liệu vẫn tập trung ở một điểm lỗi.

## 6. Kiểm tra chồng lấn đúng cách

### 6.1. Định nghĩa

Hai dải chồng lấn khi giao của chúng có ít nhất một địa chỉ.

Nếu biểu diễn mỗi CIDR thành đoạn từ địa chỉ đầu đến địa chỉ cuối:

~~~text
A = [A_start, A_end]
B = [B_start, B_end]

overlap(A, B) =
    (A_start <= B_end) AND (B_start <= A_end)
~~~

Với IPv4, có thể chuyển địa chỉ thành số nguyên không dấu:

~~~text
Giá trị của a.b.c.d =
    a × 256^3 + b × 256^2 + c × 256 + d

Kích thước khối = 2^(32 - prefix)
Đầu khối = floor(giá trị IP / kích thước khối) × kích thước khối
Cuối khối = đầu khối + kích thước khối - 1
~~~

Khi triển khai kiểm tra, nên dùng thư viện xử lý địa chỉ mạng đáng tin cậy, kiểm tra IPv4 hợp lệ, độ dài tiền tố và yêu cầu đầu vào đúng địa chỉ mạng chuẩn. Không so sánh chuỗi theo thứ tự chữ cái, vì thứ tự chuỗi không phải thứ tự số của IP.

### 6.2. Các trường hợp dễ nhầm

| Dải A | Dải B | Chồng lấn? | Giải thích |
| --- | --- | --- | --- |
| 10.64.0.0/16 | 10.64.8.0/24 | Có | B nằm trong A |
| 10.64.4.0/22 | 10.64.6.0/24 | Có | /22 bao phủ octet thứ ba từ 4 đến 7 |
| 10.64.4.0/22 | 10.64.8.0/23 | Không | A kết thúc ở 10.64.7.255 |
| 10.64.0.0/24 | 10.64.0.0/24 | Có | Hai tập địa chỉ giống nhau |
| 10.64.255.0/24 | 10.65.0.0/24 | Không | Hai dải kề nhau nhưng không giao nhau |
| 172.16.0.0/12 | 172.31.8.0/24 | Có | 172.31.x.x vẫn thuộc /12 này |

Đặc biệt, không chỉ tìm hai chuỗi CIDR giống hệt nhau. So sánh bằng chuỗi sẽ bỏ sót trường hợp một dải lớn bao phủ một dải nhỏ.

### 6.3. Phân biệt quan hệ chứa và xung đột

Trong sổ địa chỉ có cấu trúc cây, subnet nằm trong VCN là quan hệ hợp lệ; nó không phải một lỗi cần loại bỏ.

Cần áp dụng các quy tắc riêng:

1. Subnet phải nằm trọn trong CIDR VCN cha phù hợp.
2. Các subnet ngang hàng không được giao nhau.
3. Các CIDR của VCN cần kiểm tra với các VCN và mạng ngoài dự kiến liên thông.
4. Khối giữ chỗ có thể chứa các cấp phát con của chính nó.
5. Một khối đã cấp cho đội hoặc môi trường khác không được cấp lại chỉ vì hiện chưa thấy tài nguyên sử dụng.

Nếu công cụ kiểm tra báo mọi cặp cha–con là lỗi, công cụ đó sẽ tạo nhiều cảnh báo sai. Nếu công cụ bỏ qua mọi cặp bao chứa, nó lại có thể bỏ sót việc một VCN mới bị đặt bên trong CIDR VCN khác.

### 6.4. Kiểm tra cả route summary

Giả sử đội on-premises chỉ sử dụng vài subnet trong 10.0.0.0/8 nhưng quảng bá cả 10.0.0.0/8 về phía cloud. Một VCN mới 10.64.0.0/20 có thể không trùng các subnet thực tế đã cấp, nhưng vẫn nằm trong route tổng hợp đó.

Cần làm rõ hai vấn đề:

- Có địa chỉ nào đã thực sự được cấp trùng không?
- Các route tổng hợp, route cụ thể và chính sách quảng bá sẽ đưa lưu lượng đi đâu?

Một route cụ thể hơn có thể được ưu tiên theo quy tắc định tuyến của thành phần liên quan, nhưng không nên dùng điều đó thay cho một kế hoạch địa chỉ rõ ràng. Cần thống nhất quyền sở hữu các dải và cách quảng bá trước khi đưa kết nối vào vận hành.

Đặc biệt, đừng quảng bá toàn bộ một khối giữ chỗ lớn chỉ vì nó xuất hiện trong IPAM. Quỹ dự phòng phục vụ quản trị địa chỉ và tập prefix được phép quảng bá là hai thông tin cần được quản lý riêng.

## 7. CIDR không quyết định subnet public hay private

Một subnet dùng địa chỉ RFC 1918 vẫn có thể được thiết kế để phục vụ tài nguyên có kết nối Internet. Tính public/private trong OCI liên quan đến cấu hình subnet, việc cho phép gán public IP và kiến trúc định tuyến.

Trong mô hình thông thường:

- Tài nguyên cần nhận lưu lượng từ Internet qua public IP phải có cấu hình public IP, đường đi thích hợp qua Internet Gateway và quy tắc bảo mật cho phép.
- Tài nguyên trong subnet private có thể đi ra Internet qua NAT Gateway theo route được cấu hình, mà không trở thành điểm nhận kết nối chủ động từ Internet.
- Service Gateway phục vụ truy cập các dịch vụ OCI được hỗ trợ theo thiết kế mạng tương ứng; không phải gateway chuyển tiếp Internet tổng quát.
- Route qua DRG phục vụ kết nối đến các mạng liên quan khi route ở các phía được thiết lập phù hợp.

Ví dụ, đặt subnet app là 10.64.4.0/22 không tự làm nó private. Tương tự, tách app và database thành hai subnet không tự ngăn mọi lưu lượng giữa chúng. Vẫn phải áp dụng NSG hoặc security list và các chính sách bảo mật cần thiết.

Khi dùng tên subnet như “edge”, “app” và “data” trong kế hoạch CIDR, hãy xem đó là ý định thiết kế cần được hiện thực hóa bằng cấu hình mạng.

## 8. Vì sao peering, DRG và firewall không sửa được trùng IP

Giả sử có hai VCN:

~~~text
VCN ứng dụng: 10.20.0.0/16
  Máy app: 10.20.1.10

VCN dữ liệu: 10.20.0.0/16
  Máy database: 10.20.1.10
~~~

Nếu ứng dụng cần gọi 10.20.1.10, địa chỉ đích không chứa thông tin “máy database ở VCN dữ liệu”. Đây còn có thể chính là địa chỉ máy app hoặc một địa chỉ thuộc mạng cục bộ theo góc nhìn của máy gửi.

Thêm quy tắc cho phép TCP 1521 trên NSG không thay đổi ý nghĩa của địa chỉ đích. Thêm route hoặc kết nối qua DRG cũng không biến hai tập địa chỉ trùng nhau thành hai tập duy nhất.

Một số kiểu kết nối có ràng buộc về CIDR và việc quảng bá route. Vì vậy, phải kiểm tra điều kiện của đúng mô hình peering hoặc DRG định sử dụng, thay vì giả định cứ tạo kết nối là mọi VCN sẽ liên lạc được.

Các biện pháp sau không giải quyết căn nguyên:

| Biện pháp | Vì sao chưa đủ |
| --- | --- |
| Đổi tên VCN hoặc subnet | Tên không thay địa chỉ nguồn/đích trong gói tin |
| Chuyển tài nguyên sang compartment khác | Compartment không phải cơ chế đổi địa chỉ |
| Mở thêm cổng trên NSG | Firewall cho phép gói tin nhưng không xác định lại đích |
| Tạo DNS record mới trỏ cùng IP | Tên mới vẫn phân giải về địa chỉ đang xung đột |
| Thêm route cụ thể cho địa chỉ trùng | Có thể chọn một đường đi, nhưng không tạo hai danh tính cho cùng địa chỉ đích |
| Thêm NAT Gateway OCI thông thường | Chức năng đi ra Internet không phải giải pháp NAT tùy ý giữa mọi mạng riêng |

DNS có thể hỗ trợ chuyển dịch sang địa chỉ mới, nhưng chỉ phát huy tác dụng khi tên phân giải tới một đích mạng mà bên gọi có thể định tuyến đúng.

## 9. Xử lý khi đã có chồng lấn

### 9.1. Ưu tiên sửa trước khi có workload

Nếu mới có bản thiết kế, hãy đổi CIDR ngay trong kế hoạch. Nếu mới tạo VCN thử nghiệm chưa có tài nguyên cần giữ, đánh giá phương án tạo lại với CIDR được cấp chính thức.

Chi phí sửa ở giai đoạn này thường thấp hơn nhiều so với khi IP đã xuất hiện trong cấu hình ứng dụng, allowlist, DNS, kết nối database và công cụ giám sát.

Không tự xóa tài nguyên đang chạy để xử lý xung đột. Việc thay thế phải có kế hoạch phù hợp với trạng thái thực tế của workload.

### 9.2. Đổi địa chỉ có kiểm soát cho hệ thống đang chạy

Một quy trình chuyển đổi có thể gồm:

1. Cấp dải mới không chồng lấn và ghi nhận trong IPAM.
2. Kiểm tra khả năng thêm CIDR, điều chỉnh subnet hoặc tạo subnet/VCN mới theo tính năng, giới hạn và điều kiện OCI áp dụng.
3. Chuẩn bị route, NSG, DNS, công cụ vận hành và giám sát cho địa chỉ mới.
4. Triển khai tài nguyên thay thế hoặc di chuyển workload theo cách mà dịch vụ hỗ trợ.
5. Kiểm thử hai chiều và kiểm thử các phụ thuộc trước khi chuyển lưu lượng.
6. Chuyển dần ứng dụng qua endpoint mới, theo dõi lỗi và độ trễ.
7. Giữ phương án quay lui trong cửa sổ thay đổi.
8. Thu hồi tài nguyên và địa chỉ cũ sau khi xác nhận không còn phụ thuộc.

Không lập kế hoạch dựa trên giả định mọi subnet đều có thể nới tại chỗ hoặc mọi tài nguyên đều đổi private IP mà không gián đoạn. Khả năng thay đổi phải được xác nhận cho đúng loại tài nguyên.

Thêm một CIDR không chồng lấn vào VCN cũng không tự thay địa chỉ của workload đang nằm trong CIDR cũ. Nếu lưu lượng vẫn dùng các địa chỉ trùng, xung đột vẫn còn.

### 9.3. Dịch địa chỉ khi chưa thể đổi dải gốc

Trong một số trường hợp kết nối đối tác, việc đổi dải gốc chưa khả thi. Kiến trúc NAT qua thiết bị hoặc giải pháp mạng phù hợp có thể đưa ra một dải địa chỉ đại diện không chồng lấn.

Ví dụ khái niệm:

~~~text
Mạng đối tác thực:        10.20.0.0/16
Dải đại diện với bên gọi: 172.30.0.0/16
Ánh xạ được kiểm soát:    172.30.1.10 <-> 10.20.1.10
~~~

Trước hết phải xác nhận 172.30.0.0/16 còn trống trong toàn bộ phạm vi liên quan; việc nó thuộc RFC 1918 không bảo đảm không bị dùng ở nơi khác.

Phương án này cần thiết kế riêng về SNAT/DNAT, đường đi và đường về, HA của thiết bị, DNS, log, quan sát địa chỉ nguồn và dung lượng xử lý. Không phải ứng dụng nào cũng hoạt động tốt khi giao thức trao đổi địa chỉ IP nằm trong payload.

Cơ chế NAT phải được kiểm thử theo chiều khởi tạo kết nối thực tế. Một thiết kế chỉ cho phép kết nối do một phía khởi tạo có thể không đáp ứng luồng nghiệp vụ ngược lại.

Với mạng do tổ chức tự quản lý, cấp lại địa chỉ thường là phương án lâu dài dễ vận hành hơn việc giữ thêm một lớp dịch địa chỉ.

## 10. Quản lý kế hoạch bằng sổ địa chỉ

### 10.1. Thông tin tối thiểu

Có thể bắt đầu bằng một hệ thống IPAM hoặc bảng quản lý tập trung với các trường:

| Trường | Ý nghĩa |
| --- | --- |
| CIDR chuẩn | Địa chỉ mạng và prefix đã chuẩn hóa |
| Loại bản ghi | Khối giữ chỗ, VCN, subnet hoặc mạng ngoài |
| Khối cha | Xác định quan hệ cấp phát |
| Tenancy, compartment, region | Vị trí quản trị và triển khai |
| Môi trường và mục đích | Production, development, database, endpoint... |
| Chủ sở hữu | Đội chịu trách nhiệm xác nhận và thu hồi |
| Trạng thái | Đề xuất, giữ chỗ, đang dùng, chờ thu hồi, đã thu hồi |
| Phạm vi kết nối | Mạng nào có thể hoặc sẽ trao đổi lưu lượng |
| Quảng bá route | Prefix nào được phép quảng bá, qua đâu |
| Ngày rà soát | Thời điểm xác minh gần nhất |

CIDR được đề xuất nhưng chưa tạo tài nguyên vẫn nên được giữ chỗ khi đã được cấp cho một yêu cầu cụ thể. Nếu chỉ kiểm tra các VCN đang tồn tại, hai đội có thể cùng nhận một dải trong lúc triển khai song song.

### 10.2. Phân quyền cho quy trình cấp địa chỉ

IAM có thể giới hạn người được tạo hoặc cập nhật tài nguyên mạng trong compartment mạng. Tuy nhiên, quyền tạo VCN không đồng nghĩa người đó được tự chọn một CIDR bất kỳ.

Quy trình nên gắn việc cấp CIDR với người chịu trách nhiệm quản lý địa chỉ. Nếu dùng IaC, pipeline cần nhận các dải đã được cấp và chạy kiểm tra trước khi áp dụng.

Một kiểm tra trước triển khai có thể được mô tả như sau:

~~~text
INPUT:
  CIDR VCN đề xuất
  Danh sách CIDR subnet đề xuất
  Danh sách cấp phát/giữ chỗ và quan hệ cha-con
  Danh sách mạng ngoài và route quảng bá liên quan

CHECK:
  1. Tất cả CIDR hợp lệ và đúng biên mạng.
  2. VCN nằm trong khối đã cấp cho môi trường.
  3. VCN không xung đột với cấp phát ngang hàng và mạng liên thông.
  4. Mỗi subnet nằm trọn trong một CIDR VCN phù hợp.
  5. Các subnet không chồng lấn nhau.
  6. Không sử dụng phần đã giữ chỗ cho mục đích khác.
  7. Ngân sách IP đáp ứng nhu cầu đỉnh và yêu cầu dịch vụ.
  8. Route summary không kéo lưu lượng sang sai miền mạng.

OUTPUT:
  Kết quả đạt hoặc danh sách cặp xung đột kèm chủ sở hữu.
~~~

Đây là mã giả về quy trình kiểm tra, không phải lệnh OCI CLI.

### 10.3. Theo dõi sau khi tạo

Sau triển khai, cần đối chiếu thiết kế với thực tế:

- CIDR VCN và subnet đã tạo có đúng bản ghi được cấp không.
- Số IP đã dùng và còn trống có đáp ứng các đợt mở rộng tiếp theo không.
- Có dịch vụ nào tạo thêm private IP hoặc endpoint ngoài dự tính không.
- Route được quảng bá có đúng danh sách đã thống nhất không.
- Có tài nguyên cũ giữ địa chỉ sau quá trình di chuyển không.

VCN Flow Logs và các công cụ chẩn đoán mạng có thể cung cấp thêm bằng chứng về lưu lượng theo phạm vi được bật. Chúng hỗ trợ điều tra, nhưng không thay thế sổ cấp phát và kiểm tra chồng lấn.

Khi cần tăng tài nguyên, nên đánh giá dung lượng IP trước đợt triển khai thay vì đợi đến lúc tạo instance hoặc endpoint thất bại.

## 11. Thực hành: duyệt kế hoạch cho một VCN production

Bài thực hành tập trung vào thiết kế; có thể làm trên giấy hoặc hệ thống quản lý địa chỉ, không cần tạo tài nguyên tính phí.

### 11.1. Đầu vào

Giả sử đã kiểm kê đầy đủ các mạng liên quan sau:

| Hệ thống | CIDR |
| --- | --- |
| Trung tâm dữ liệu hiện tại | 10.0.0.0/12 |
| Đối tác A | 172.20.0.0/16 |
| VCN công cụ dùng chung | 10.80.0.0/16 |
| Quỹ cloud mới được cấp | 10.64.0.0/12 |

Yêu cầu:

- Tạo VCN production tại region chính.
- Có tầng edge, ứng dụng, dữ liệu, endpoint và vận hành.
- Dự kiến kết nối về trung tâm dữ liệu.
- Giữ địa chỉ cho region dự phòng có thể hoạt động đồng thời.
- Tầng ứng dụng cần ngân sách khoảng 700 IP ở đỉnh.

### 11.2. Bước 1: kiểm tra VCN đề xuất

Chọn **10.64.0.0/20**.

- Trung tâm dữ liệu 10.0.0.0/12 kết thúc ở 10.15.255.255, nên không chồng lấn.
- Đối tác dùng 172.20.0.0/16, nên không chồng lấn.
- VCN dùng chung bắt đầu ở 10.80.0.0, nằm ngoài quỹ 10.64.0.0/12, nên không chồng lấn với VCN đề xuất.
- VCN đề xuất nằm trong quỹ cloud đã được cấp.

Kết luận này dựa trên giả định danh sách kiểm kê đầy đủ. Trong thực tế phải đưa cả những dải đã giữ chỗ và các route tổng hợp liên quan vào kiểm tra.

### 11.3. Bước 2: kiểm tra các subnet

Dùng năm subnet trong kế hoạch ở phần 5:

~~~text
Edge:       10.64.0.0/24
App:        10.64.4.0/22
Data:       10.64.8.0/23
Endpoint:   10.64.10.0/24
Vận hành:   10.64.11.0/24
~~~

Xác minh:

1. Tất cả địa chỉ mạng đều đúng biên.
2. Tất cả dải đều nằm trong 10.64.0.0/20.
3. Không có cặp subnet nào giao nhau.
4. Subnet app có 1.021 IP cấp được, đáp ứng ngân sách 700 IP theo giả định.
5. Dải dự phòng còn lại được ghi rõ, chưa cấp cho đội khác.
6. Phương án public/private và kiểm soát lưu lượng được thiết kế riêng.

### 11.4. Bước 3: xử lý hai yêu cầu phát sinh

**Yêu cầu A:** một đội xin 10.64.6.0/24 cho subnet batch mới.

Kết quả: từ chối dải đề xuất, vì nó nằm trong subnet app 10.64.4.0/22. Không thể coi .6 là vùng trống chỉ vì chưa có instance ở đó. Đội mạng có thể xem xét một phần của quỹ dự phòng và cập nhật kế hoạch sau khi tính nhu cầu.

**Yêu cầu B:** một đội xin 10.64.16.0/24 trong cùng VCN.

Kết quả: dải này không chồng lấn với năm subnet hiện tại, nhưng nằm ngoài CIDR VCN 10.64.0.0/20. Cần đánh giá phương án cấp thêm không gian hợp lệ cho VCN hoặc chọn dải trong phần dự phòng hiện có; không thể tạo subnet này chỉ dựa trên kết quả “không trùng”.

### 11.5. Bước 4: chuẩn bị DR và kết nối hybrid

Giữ chỗ **10.68.0.0/20** cho VCN DR theo kế hoạch đã thống nhất. Nếu DR nằm ở region khác, vẫn kiểm tra nó trong cùng phạm vi liên thông với production và on-premises.

Trước khi mở kết nối, thống nhất:

- Những prefix được quảng bá từ mỗi phía.
- Những subnet nào cần giao tiếp với nhau.
- Đường đi và đường về, bao gồm trường hợp đi qua firewall hoặc thiết bị trung gian.
- Quy tắc bảo mật và tên DNS cho từng dịch vụ.
- Cách kiểm thử khi production và DR cùng chạy.

Nếu kiểm thử kết nối thất bại, cần kiểm tra lần lượt địa chỉ, route, quy tắc bảo mật, hệ điều hành và dịch vụ đang lắng nghe. Không suy ra “không chồng lấn” đồng nghĩa với “chắc chắn kết nối được”.

## 12. Các lỗi thường gặp và hệ quả

| Lỗi thiết kế | Hệ quả | Cách phòng tránh |
| --- | --- | --- |
| Mọi môi trường đều chọn 10.0.0.0/16 | Khó kết nối hybrid hoặc liên môi trường | Cấp CIDR tập trung trước khi tạo VCN |
| Chỉ so sánh chuỗi CIDR giống nhau | Bỏ sót dải con nằm trong dải lớn | So sánh khoảng địa chỉ và quan hệ chứa |
| Chỉ đếm số VM hiện tại | Hết IP khi mở rộng hoặc rolling update | Tính VNIC, IP phụ, endpoint và nhu cầu đỉnh |
| Dùng cả quỹ giữ chỗ làm CIDR VCN ngay lập tức | Không còn không gian không chồng lấn cho các VCN khác | Phân biệt giữ chỗ trong IPAM với CIDR đã cấu hình |
| Dùng chung CIDR cho production và DR | Vướng khi hai bên cần chạy đồng thời | Cấp dải riêng cho từng phạm vi cần liên thông |
| Tưởng subnet liền số là có thể mở rộng tại chỗ | Mở rộng đụng biên hoặc đè lên subnet khác | Kiểm tra khối CIDR bao chứa và điều kiện thay đổi |
| Tin rằng IAM hoặc NSG sửa được trùng địa chỉ | Mất thời gian điều tra sai lớp | Giải quyết kế hoạch IP trước, rồi kiểm tra route và bảo mật |
| Quảng bá một prefix quá rộng | Lưu lượng đến các dải khác có thể bị hút sai đường | Quản lý danh sách quảng bá tách khỏi quỹ dự phòng |
| Quên thu hồi dải sau di chuyển | Sổ địa chỉ sai lệch, khó cấp phát tiếp | Xác minh phụ thuộc và cập nhật trạng thái vòng đời |

## 13. Tự kiểm tra

### Câu 1: Hai dải 10.64.0.0/20 và 10.64.8.0/23 có chồng lấn không?

Có. Dải /20 bao phủ 10.64.0.0 đến 10.64.15.255; /23 nằm hoàn toàn bên trong.

Nếu /23 là subnet của VCN /20 thì đây là quan hệ cha–con hợp lệ. Nếu /23 thuộc một VCN khác cần kết nối với VCN /20 thì phải xử lý xung đột.

### Câu 2: 10.64.4.0/22 và 10.64.8.0/22 có chồng lấn không?

Không. Dải đầu kết thúc ở 10.64.7.255, dải sau bắt đầu tại 10.64.8.0. Chúng liền kề nhưng không có địa chỉ chung.

### Câu 3: Có thể dùng /24 cho ngân sách 260 private IP không?

Không. /24 chỉ có 256 địa chỉ tổng, và subnet IPv4 OCI có 253 địa chỉ cấp được. Phải chọn khối lớn hơn hoặc phân chia workload theo một kiến trúc phù hợp; không giải quyết bằng cách giảm phần dự phòng đã được yêu cầu.

### Câu 4: Hai VCN ở hai region khác nhau cùng dùng 10.10.0.0/16 có tự động an toàn không?

Không thể kết luận như vậy. Region khác nhau không làm địa chỉ trở nên duy nhất. Nếu cần đồng bộ, peering, kết nối qua DRG hoặc cùng truy cập từ on-premises, cần đánh giá và xử lý khả năng chồng lấn.

### Câu 5: Thêm 10.70.0.0/20 vào VCN có tự sửa workload đang dùng dải bị trùng không?

Không. Các workload vẫn giữ địa chỉ hiện có cho đến khi có thay đổi hoặc di chuyển phù hợp. CIDR mới chỉ bổ sung không gian địa chỉ; phải chuyển các phụ thuộc liên quan thì mới loại bỏ xung đột trong luồng lưu lượng đó.

## 14. Danh sách kiểm tra trước triển khai

- [ ] Đã có sổ địa chỉ bao gồm mạng đang dùng, dải giữ chỗ và mạng ngoài liên quan.
- [ ] CIDR được viết đúng biên và nằm trong quỹ cấp cho môi trường.
- [ ] Đã phân biệt khối giữ chỗ, CIDR VCN và CIDR subnet.
- [ ] Không có chồng lấn ngoài những quan hệ cha–con được phép.
- [ ] Đã tính nhu cầu IP ở đỉnh, IP phụ, endpoint và các giai đoạn chạy song song.
- [ ] Các subnet đáp ứng yêu cầu của đúng dịch vụ Compute hoặc database sử dụng.
- [ ] Có địa chỉ riêng cho các môi trường và region cần hoạt động cùng lúc.
- [ ] Có dải dự phòng và hiểu rõ dải đó phục vụ subnet mới hay khả năng mở rộng nào.
- [ ] Đã kiểm tra route quảng bá và route tổng hợp với đội mạng liên quan.
- [ ] Đã thiết kế public/private, gateway và quy tắc bảo mật phù hợp.
- [ ] Có chủ sở hữu, cách theo dõi dung lượng IP và quy trình thu hồi.

Một kế hoạch CIDR có giá trị khi đội vận hành có thể trả lời rõ: dải này thuộc ai, phục vụ mục đích gì, có thể kết nối với đâu, còn bao nhiêu dung lượng và sẽ mở rộng bằng cách nào. Đó là cơ sở để triển khai mạng OCI có kiểm soát thay vì phải sửa địa chỉ sau khi ứng dụng đã phụ thuộc vào chúng.
