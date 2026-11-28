# Certificate Transparency: quan sát chứng chỉ TLS và reconnaissance có kiểm soát

## 1. Certificate Transparency là gì?

**Certificate Transparency (CT)** là hệ sinh thái nhật ký công khai có thể kiểm chứng bằng mật mã, được thiết kế để làm cho việc **cấp phát chứng chỉ số**, đặc biệt là chứng chỉ TLS công khai, trở nên minh bạch và có thể được cộng đồng giám sát. Thay vì chỉ tin rằng Certificate Authority (CA, tổ chức cấp chứng chỉ) sẽ cấp chứng chỉ đúng, người sở hữu tên miền và bên giám sát có thể tìm thấy những chứng chỉ đã được đưa vào CT log, kể cả chứng chỉ không do họ chủ động yêu cầu.

Ví dụ, doanh nghiệp quản lý tên miền giả định **example.org**. Khi một chứng chỉ được đưa vào CT log với các tên:

~~~text
www.example.org
api.example.org
admin.example.org
~~~

người giám sát có thể nhận ra tên **admin.example.org** từng xuất hiện trong dữ liệu cấp chứng chỉ công khai và kiểm tra xem đó có phải tài sản được phép công bố hay không. Đồng thời, người thực hiện **reconnaissance** cũng có thể tìm thấy các tên miền phụ từ những dữ liệu này mà không cần quét cổng hoặc gửi gói tin tới từng máy chủ.

Trong module **SECURITY_NETWORK_SECURITY**, CT có hai ý nghĩa bổ sung cho nhau:

- **Phòng vệ:** Phát hiện hoạt động cấp chứng chỉ bất thường, hỗ trợ kiểm kê tài sản Internet-facing, theo dõi thay đổi hạ tầng và điều tra nguy cơ giả mạo dịch vụ.
- **Reconnaissance và phân tích bề mặt tấn công:** Sử dụng dữ liệu chứng chỉ được công bố để hình thành giả thuyết về tên miền, ứng dụng, cổng dịch vụ hoặc các môi trường triển khai cần xác minh.

CT **không** chứng minh một máy chủ đang hoạt động, không xác nhận mọi tên xuất hiện thuộc quyền quản lý thực tế của doanh nghiệp, không tự ngăn tấn công và không thay thế việc xác minh chứng chỉ TLS ở client.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vai trò của CA, CT log, Signed Certificate Timestamp (SCT), monitor và auditor.
2. Phân biệt việc một chứng chỉ được **ghi nhận**, **cam kết ghi nhận** và **được client tin cậy**.
3. Mô tả cách Merkle tree hỗ trợ chứng minh tính bao hàm và tính chỉ bổ sung của log.
4. Khai thác dữ liệu CT **thụ động, có phạm vi** để tạo danh sách tên miền cần xác minh.
5. Xây dựng quy trình giám sát cấp chứng chỉ, phân loại cảnh báo và xử lý tình huống bất thường.
6. Nhận diện giới hạn của CT khi phân tích DNS, TLS, VPN, firewall, IDS/IPS và kiến trúc mạng an toàn.

## 2. Vì sao cần Certificate Transparency?

Trong mô hình Public Key Infrastructure (PKI), browser hoặc ứng dụng kiểm tra chứng chỉ máy chủ dựa vào chuỗi chứng chỉ, danh tính tên miền, thời hạn hiệu lực và chính sách tin cậy tương ứng. Tuy nhiên, một chứng chỉ được CA công khai cấp phát có thể **không phải** là chứng chỉ người quản trị tên miền kỳ vọng: ví dụ CA cấp sai, quy trình xác thực quyền kiểm soát tên miền bị lợi dụng hoặc một bộ phận nội bộ tự tạo chứng chỉ cho tên mới mà chưa được ghi nhận vào danh mục tài sản.

CT bổ sung **khả năng quan sát bên ngoài**:

| Vấn đề | CT giúp ích như thế nào? | CT không tự giải quyết điều gì? |
| --- | --- | --- |
| Chứng chỉ bị cấp cho tên miền trái mong muốn | Cho phép chủ sở hữu và monitor phát hiện chứng chỉ/precertificate xuất hiện trên log được theo dõi | Không tự kết luận việc cấp sai hoặc tự thu hồi chứng chỉ |
| Danh mục tên miền phụ thiếu cập nhật | Gợi ý những DNS name có mặt trong chứng chỉ công khai | Không chứng minh DNS record tồn tại hoặc host đang phục vụ |
| Kiểm toán sự minh bạch của log | Bằng chứng Merkle tree cho phép kiểm tra dữ liệu đã ghi và sự phát triển nhất quán của log | Không đảm bảo mọi client đều kiểm tra toàn bộ bằng chứng trong mọi trường hợp |
| Nguy cơ lộ tên hệ thống qua chứng chỉ | Cho biết tên xuất hiện trên chứng chỉ có thể được người ngoài nhìn thấy | Không che giấu tên miền; CT là nguồn dữ liệu công khai |
| Máy chủ sử dụng chứng chỉ không hợp lệ | Dữ liệu CT hỗ trợ điều tra lịch sử cấp phát | Không thay thế xác minh hostname, trust chain, thời hạn và thu hồi chứng chỉ |

**Ví dụ về phạm vi:** Một chứng chỉ do **CA nội bộ** cấp cho hệ thống chỉ dùng trong mạng riêng thường không bắt buộc xuất hiện ở CT log công khai. Vì vậy, kết quả CT chỉ là một phần của kiểm kê. Ngược lại, một tên nội bộ xuất hiện trong chứng chỉ TLS **được đăng công khai** có thể làm lộ tên môi trường dù dịch vụ không thể truy cập từ Internet.

## 3. Các thành phần và quy trình hoạt động

### 3.1. Những vai trò chính

| Thành phần | Trách nhiệm |
| --- | --- |
| **Certificate Authority (CA)** | Xác thực yêu cầu theo quy trình áp dụng, cấp chứng chỉ và có thể gửi certificate hoặc precertificate tới các CT log |
| **CT log** | Nhận mục dữ liệu, phát hành bằng chứng cam kết dưới dạng SCT, duy trì cấu trúc log chỉ bổ sung và cung cấp bằng chứng mật mã |
| **Log operator** | Vận hành hạ tầng log, ký các thông tin của log và công bố giao diện truy vấn |
| **Monitor** | Đọc/xem dữ liệu được công bố để phát hiện chứng chỉ có tên hoặc đặc điểm đáng quan tâm |
| **Auditor** | Kiểm tra lời hứa SCT, tính bao hàm của mục ghi và sự nhất quán khi log phát triển |
| **Browser / TLS client** | Xác minh chứng chỉ TLS và, tùy chính sách CT áp dụng, kiểm tra sự hiện diện hoặc tính hợp lệ của SCT |
| **Chủ sở hữu tên miền** | Theo dõi chứng chỉ cho các tên thuộc quyền quản lý và điều tra cấp phát bất thường |

### 3.2. Luồng cấp chứng chỉ điển hình

~~~mermaid
sequenceDiagram
    participant O as Chủ thể yêu cầu
    participant CA as CA
    participant L as CT log
    participant C as TLS client
    participant M as Monitor
    O->>CA: Yêu cầu chứng chỉ cho tên miền
    CA->>CA: Thực hiện kiểm tra theo quy trình CA
    CA->>L: Gửi precertificate hoặc certificate
    L-->>CA: SCT (cam kết ghi log)
    CA-->>O: Cấp chứng chỉ và phương thức cung cấp SCT
    O-->>C: Kết nối TLS, trình chứng chỉ/SCT
    C->>C: Xác minh TLS và áp dụng chính sách CT
    L-->>M: Cung cấp các mục đã ghi
    M->>M: So khớp domain, điều tra mục bất thường
~~~

Đây là luồng khái quát; cách cấp chứng chỉ và cung cấp SCT thay đổi theo CA, phiên bản CT, client và quy trình triển khai.

**Precertificate** là cấu trúc phục vụ việc ghi log trước khi phát hành chứng chỉ cuối cùng. Theo cơ chế CT v1, nó có cấu trúc chứng chỉ đặc thù với **poison extension** đánh dấu rằng không thể dùng như chứng chỉ máy chủ TLS thông thường. Dữ liệu từ precertificate có thể xuất hiện trong CT ngay cả khi cuối cùng không có chứng chỉ TLS tương ứng được triển khai.

### 3.3. Signed Certificate Timestamp (SCT) thực sự xác nhận gì?

**SCT** là một **lời hứa có chữ ký** từ CT log rằng một mục được nhận sẽ được đưa vào log trong khoảng thời gian giới hạn, gọi là **Maximum Merge Delay (MMD)** theo chính sách của log. Tùy cơ chế triển khai, SCT có thể được cung cấp trong chứng chỉ, qua TLS extension hoặc qua cơ chế khác được client hỗ trợ.

Phải phân biệt:

- **SCT hợp lệ:** Log đã ký cam kết đưa mục vào log theo quy định. Chỉ riêng SCT **chưa phải** bằng chứng rằng mục đã thật sự được đưa vào cây log.
- **Inclusion proof hợp lệ:** Có thể chứng minh một mục đã được chứa trong phiên bản cây log có root cụ thể.
- **Consistency proof hợp lệ:** Có thể chứng minh phiên bản log mới duy trì đầy đủ phần đầu của phiên bản cũ, theo mô hình append-only.
- **Chứng chỉ TLS đáng tin:** Còn phải qua các kiểm tra PKI/TLS và chính sách client. Một mục hiện diện trong CT **không tự biến** chứng chỉ thành đáng tin.

Không có một quy tắc duy nhất áp dụng cho mọi browser và mọi chứng chỉ: yêu cầu CT của các chương trình root store/browser thay đổi theo nền tảng, thời điểm, loại chứng chỉ và chính sách. Khi đánh giá hệ thống thật, tham khảo chính sách hiện hành của client liên quan.

## 4. Merkle tree bảo vệ tính minh bạch của CT log như thế nào?

CT log dùng **Merkle hash tree**: dữ liệu được băm thành các leaf; những leaf được ghép, băm theo cấp để tạo một **root hash** đại diện cho nội dung và thứ tự của cây tại thời điểm xác định.

Ví dụ minh họa:

~~~text
                   Merkle root
                    /      \
                 H(AB)      H(CD)
                 /  \        /  \
               H(A) H(B)  H(C) H(D)
                 |    |     |    |
                CT-A CT-B  CT-C CT-D
~~~

Đối với cấu trúc CT v1 theo RFC 6962, cách băm lá và nút được **phân miền** bằng tiền tố byte khác nhau; mô tả khái niệm:

~~~text
leaf_hash = SHA256(0x00 || serialized_leaf)
node_hash = SHA256(0x01 || left_hash || right_hash)
~~~

Phần “serialized_leaf” là cấu trúc dữ liệu được đặc tả cho phiên bản giao thức tương ứng, không đơn giản là chuỗi tên miền. Công thức ở đây để hiểu nguyên lý; không nên tự triển khai CT verifier từ vài dòng minh họa.

### 4.1. Inclusion proof

**Inclusion proof** đưa ra một đường đi ngắn gồm các hash cần thiết để auditor tái tính được Merkle root từ leaf. Nếu root tính được khớp một phiên bản cây có chữ ký của log, mục đó được chứng minh là nằm trong cây tại phiên bản được công bố.

Độ dài bằng chứng tăng xấp xỉ **theo logarit số leaf**: không cần tải toàn bộ log chỉ để chứng minh một mục đã được ghi.

### 4.2. Consistency proof

Log có trách nhiệm phát triển theo nguyên tắc **append-only**: thêm mục mới mà không xóa hoặc viết lại mục đã ghi. **Consistency proof** cho phép kiểm tra hai tree head có mối quan hệ tiền tố hợp lệ.

Một log vận hành sai có thể cố gắng trình bày **hai góc nhìn không nhất quán** cho các nhóm quan sát khác nhau. Do đó, việc kiểm tra bằng chứng và **so sánh các tree head giữa những bên quan sát** có ý nghĩa quan trọng trong hệ sinh thái kiểm toán CT. Không nên hiểu rằng chỉ có Merkle tree là tự động giải quyết mọi vấn đề về phát hiện split-view.

### 4.3. Signed Tree Head (STH) và các phiên bản giao thức

Trong **CT v1 (RFC 6962)**, log công bố **Signed Tree Head (STH)**, trong đó có kích thước cây, thời gian và chữ ký của log gắn với root hash. **RFC 9162** mô tả **Certificate Transparency v2** với những thay đổi về giao thức và cấu trúc dữ liệu. Khi đọc tài liệu, API hoặc công cụ, phải biết đang sử dụng phiên bản nào; không trộn cách tuần tự hóa dữ liệu, định dạng bằng chứng hoặc API giữa các phiên bản.

## 5. CT công khai những dữ liệu nào?

Khi một certificate/precertificate được log và được dịch vụ tra cứu lập chỉ mục, các thông tin thường có thể quan sát bao gồm:

| Dữ liệu | Ý nghĩa với reconnaissance | Giới hạn |
| --- | --- | --- |
| **Subject Alternative Name (SAN)** | Tên DNS được liệt kê trong chứng chỉ; gợi ý subdomain hoặc dịch vụ | Tên có mặt trong chứng chỉ không đồng nghĩa host đang tồn tại |
| **Common Name (CN)** | Có thể hỗ trợ bối cảnh lịch sử/hiển thị | Xác minh danh tính TLS hiện đại dựa trên cơ chế SAN; không coi CN là nguồn thay thế chính cho SAN |
| **Issuer / CA** | Biết tổ chức cấp phát, phát hiện CA khác quy trình | Issuer lạ chưa đủ kết luận chứng chỉ độc hại |
| **Ngày Not Before / Not After** | Mốc hiệu lực được khai báo trong chứng chỉ | Không cho biết cert đang được cài lên máy chủ nào hay có bị thu hồi hay không |
| **Serial number / fingerprint** | Phục vụ đối chiếu và loại trùng bản ghi, nhận diện chính xác chứng chỉ | Fingerprint cần tính bằng thuật toán phù hợp và đối chiếu đúng đối tượng |
| **Log entry time / SCT timestamp** | Gợi ý thời điểm dữ liệu được nộp/ghi nhận bởi log | Không đồng nhất với thời điểm máy chủ bắt đầu sử dụng chứng chỉ |
| **Public key / thuật toán chữ ký** | Hỗ trợ rà soát chất lượng cấu hình khóa và chứng chỉ | CT không công bố private key; không thể dùng chỉ dữ liệu này để đọc lưu lượng TLS |
| **Wildcards trong SAN** | Cho biết có chứng chỉ bao phủ mẫu tên như *.example.org | **Không** liệt kê cụ thể những tên như api.example.org hay shop.example.org |

CT log có thể công bố **chuỗi chứng chỉ và metadata**. Dịch vụ tìm kiếm thường bổ sung chỉ mục hoặc giao diện thuận tiện, nhưng các trường trong JSON/CSV của chúng **không nhất thiết là API chuẩn CT**. Một kết quả tìm kiếm cũng có thể đại diện cho precertificate, chứng chỉ cuối cùng hoặc những bản ghi trùng lặp.

### 5.1. Diễn giải đúng tên miền

Giả sử có các tên:

~~~text
api.example.org
admin.dev.example.org
*.staging.example.org
example.org.evil.test
~~~

Với phạm vi được phép là **example.org**:

- **api.example.org** và **admin.dev.example.org** là những tên nằm dưới hậu tố DNS example.org.
- **\*.staging.example.org** là **mẫu wildcard**; không thể suy ra có bao nhiêu host cụ thể.
- **example.org.evil.test** **không thuộc** example.org. Không được kiểm tra phạm vi bằng cách tìm chuỗi con một cách tùy tiện.

Để phân loại chính xác, chuẩn hóa tên miền (viết thường, xử lý dấu chấm cuối và tên quốc tế hóa khi cần), sau đó so khớp **tên gốc hoặc hậu tố có ranh giới dấu chấm**. Với nhiều tên miền tổ chức, xác định phạm vi bằng danh sách domain được sở hữu thực tế; đừng suy rằng một domain có nhãn giống thương hiệu chắc chắn thuộc về doanh nghiệp.

### 5.2. Một tên xuất hiện trong CT nói được và chưa nói được điều gì?

**Có thể suy luận:** Một tên đã xuất hiện trong dữ liệu cấp chứng chỉ được công bố, có thể đáng kiểm tra trong kho tài sản, quy trình thay đổi hoặc DNS.

**Chưa thể kết luận:** Tên này đang phân giải DNS, có IP cụ thể, mở cổng 443, là một máy chủ thực tế, chứa ứng dụng nhất định, có lỗ hổng hoặc đang thuộc quyền sở hữu của người bị cho là chủ thể yêu cầu. Thông tin cần được xác thực qua **nguồn được phép** và nguồn dữ liệu khác.

## 6. CT trong reconnaissance: quy trình thụ động theo phạm vi

**Passive reconnaissance** thu thập thông tin đã công khai mà không cần chủ động dò quét vào các host mục tiêu. Tra cứu CT là ví dụ tiêu biểu; tuy nhiên hành vi tra cứu vẫn gửi yêu cầu tới **dịch vụ tra cứu CT**, và dịch vụ đó có thể ghi nhật ký truy vấn.

~~~mermaid
flowchart TD
    A["Xác định domain thuộc phạm vi"] --> B["Tra cứu CT log / công cụ chỉ mục"]
    B --> C["Tách SAN và chuẩn hóa DNS name"]
    C --> D{"Tên nằm trong phạm vi?"}
    D -- "Không" --> X["Loại khỏi danh sách mục tiêu"]
    D -- "Có" --> E["Loại bản ghi trùng, gắn nguồn chứng cứ"]
    E --> F["Đối chiếu inventory / DNS / CMDB được phép"]
    F --> G["Phân loại: known, unknown, wildcard, inactive"]
    G --> H["Báo cáo giả thuyết và yêu cầu xác minh"]
~~~

### Bước 1. Xác định mục tiêu và phạm vi

Ghi rõ tên miền được quản lý, wildcard có được đưa vào danh sách hay không, mục đích thu thập và nguồn dữ liệu. Với nhiệm vụ phòng vệ nội bộ, nên bắt đầu từ domain thuộc sở hữu hợp pháp hoặc tài sản đã được giao quản lý.

### Bước 2. Tìm dữ liệu qua nguồn công khai

Có thể tham khảo:

- **crt.sh:** Dịch vụ tra cứu chứng chỉ từ dữ liệu CT; thuận tiện để tìm chuỗi tên miền và xem chứng chỉ theo ID.
- **Google Certificate Transparency:** Tài liệu và hệ thống log CT công khai.
- **Các CT log và monitor:** Đọc dữ liệu trực tiếp hoặc sử dụng hệ thống giám sát thay vì phụ thuộc vào một bộ chỉ mục duy nhất.

Ví dụ cú pháp truy vấn **crt.sh** (để tham khảo, không yêu cầu thực thi trong bài học):

~~~text
https://crt.sh/?q=%25.example.org
https://crt.sh/?q=%25.example.org&output=json
~~~

Ở đây **%25** là ký tự % được mã hóa trong URL; kiểu truy vấn này thường được dùng để tìm các tên theo hậu tố. Cú pháp và định dạng đầu ra là tính năng của **dịch vụ crt.sh**, không phải cam kết giao diện chuẩn, nên phải kiểm tra thực tế nếu đưa vào hệ thống vận hành. Domain **example.org** là miền ví dụ; dữ liệu thực tế của nó, nếu có, không phải nội dung được dùng để kết luận trong bài này.

### Bước 3. Trích xuất, chuẩn hóa và loại trùng

Một kết quả có thể chứa nhiều tên SAN phân tách bằng dấu xuống dòng. Nhiều chứng chỉ liên tiếp có thể lặp tên miền vì gia hạn; precertificate và certificate cuối cũng có thể khiến bản ghi xuất hiện nhiều lần. Vì vậy:

1. Tách SAN thành **từng tên**, giữ liên kết về bản ghi gốc.
2. Chuẩn hóa kiểu chữ, dấu chấm cuối và xử lý wildcard riêng.
3. Chỉ chấp nhận tên đúng phạm vi domain.
4. Loại trùng theo **mục tiêu báo cáo**: danh sách tên miền thì dùng DNS name; kiểm toán chứng chỉ thì dùng fingerprint/serial kèm thông tin issuer thích hợp.
5. Lưu metadata nguồn, thời điểm quan sát và trạng thái xác minh để có thể truy xuất.

### Bước 4. Đối chiếu bằng chứng và đánh giá ưu tiên

| Tên tìm thấy | Bước xác minh phù hợp | Cách ghi kết luận |
| --- | --- | --- |
| api.example.org | So với asset inventory, DNS, cấu hình gateway đã được phép xem | “Tên xuất hiện trong CT; tình trạng dịch vụ được kiểm chứng riêng” |
| *.dev.example.org | Kiểm tra có chính sách dùng wildcard cho môi trường dev không | “Có wildcard trong chứng chỉ; chưa biết danh sách host” |
| old.example.org | So với hồ sơ ngừng vận hành và bản ghi DNS hiện tại | “Dấu vết lịch sử; chưa đủ chứng minh dịch vụ đang tồn tại” |
| vpn.example.org với issuer ngoài danh mục | Kiểm tra bằng chứng phê duyệt cấp chứng chỉ và chủ thể quản lý | “Cần rà soát issuer; chưa khẳng định cấp phát trái phép” |

Các công việc **active reconnaissance** như quét cổng, kết nối thử endpoint, dò thư mục hoặc kiểm thử bảo mật chỉ nên tiến hành khi có **phạm vi và quyền thực hiện rõ ràng**. Thu thập CT tự nó không cấp quyền làm những hoạt động đó.

## 7. Thực hành: phân tích dữ liệu CT mô phỏng bằng Python

Bài lab sử dụng **JSON được khai báo ngay trong chương trình**, không kết nối Internet và không truy vấn hệ thống bên ngoài. Nó minh họa ba việc cần làm trước khi đưa CT data vào danh mục tài sản: **tách tên SAN, khống chế phạm vi và loại trùng**.

~~~python
import json

DOMAIN = "example.org"

# Dữ liệu MÔ PHỎNG theo một số trường phổ biến của kết quả chỉ mục CT.
sample_json = r'''[
  {
    "id": 101,
    "name_value": "www.example.org\napi.example.org",
    "issuer_name": "Example Trusted CA",
    "not_before": "2026-01-01",
    "not_after": "2026-04-01"
  },
  {
    "id": 102,
    "name_value": "api.example.org\n*.dev.example.org",
    "issuer_name": "Example Trusted CA",
    "not_before": "2026-03-01",
    "not_after": "2026-06-01"
  },
  {
    "id": 103,
    "name_value": "example.org.evil.test",
    "issuer_name": "Unrelated CA",
    "not_before": "2026-02-01",
    "not_after": "2026-05-01"
  },
  {
    "id": 104,
    "name_value": "vpn.example.org",
    "issuer_name": "Needs Review CA",
    "not_before": "2026-04-01",
    "not_after": "2026-07-01"
  }
]'''


def normalize_dns_name(value: str) -> str:
    return value.strip().lower().rstrip(".")


def in_scope(name: str, apex: str) -> bool:
    # Bỏ dấu * để kiểm tra hậu tố, nhưng GIỮ wildcard ở kết quả.
    checked = name[2:] if name.startswith("*.") else name
    return checked == apex or checked.endswith("." + apex)


records = json.loads(sample_json)
names = set()
evidence = {}
apex = normalize_dns_name(DOMAIN)

for entry in records:
    for raw_name in entry["name_value"].splitlines():
        name = normalize_dns_name(raw_name)
        if not in_scope(name, apex):
            continue
        names.add(name)
        evidence.setdefault(name, []).append(entry["id"])

for name in sorted(names):
    kind = "wildcard" if name.startswith("*.") else "DNS name"
    print(f"{name:24} | {kind:8} | log IDs: {evidence[name]}")
~~~

Kết quả dự kiến:

~~~text
*.dev.example.org        | wildcard | log IDs: [102]
api.example.org          | DNS name | log IDs: [101, 102]
vpn.example.org          | DNS name | log IDs: [104]
www.example.org          | DNS name | log IDs: [101]
~~~

**Giải thích kết quả:**

- **api.example.org** xuất hiện ở hai bản ghi nhưng danh sách tên chỉ có một mục.
- **example.org.evil.test** bị loại vì không thuộc hậu tố DNS example.org.
- **\*.dev.example.org** vẫn được đánh dấu wildcard, tránh báo sai là đã phát hiện một host cụ thể.
- **vpn.example.org** cần đối chiếu hồ sơ chứng chỉ, DNS và chủ sở hữu; không thể chỉ từ tên hoặc issuer giả định mà kết luận có VPN đang chạy.

**Giới hạn bài lab:** Đây là mẫu xử lý tên DNS đơn giản, giả định chuỗi đã ở dạng ASCII phù hợp. Hệ thống sản xuất cần kiểm tra cấu trúc kết quả, xử lý IDN/Punycode, SAN chứa IP hoặc các GeneralName khác, giới hạn dung lượng, pagination, retry, nguồn dữ liệu và tính toàn vẹn của dữ liệu đầu vào. ID trong JSON là khóa chỉ mục của dịch vụ mô phỏng, không phải identifier chung của mọi CT log.

## 8. Từ reconnaissance đến quản lý bề mặt tấn công

Sơ đồ kiến trúc phòng vệ có thể tích hợp CT vào quy trình quản trị tài sản:

~~~mermaid
flowchart LR
    L["CT log / monitor"] --> P["Bộ thu thập"]
    P --> N["Chuẩn hóa và lọc domain"]
    N --> I["Asset inventory / CMDB"]
    N --> R["Bộ luật cảnh báo"]
    I --> R
    R --> T["Đội vận hành an ninh"]
    T --> V["Xác minh và xử lý"]
    V --> I
~~~

### 8.1. Những dấu hiệu cần chú ý

| Tín hiệu CT | Vì sao đáng xem xét? | Kiểm chứng bổ sung |
| --- | --- | --- |
| Xuất hiện tên miền phụ chưa có trong inventory | Có thể là dịch vụ mới hoặc môi trường bị bỏ sót | Chủ sở hữu, DNS, IaC, CMDB, cấu hình ingress |
| Một CA ngoài danh sách thường dùng phát hành cert | Có thể là thay đổi quy trình, đối tác mới hoặc cấp chứng chỉ bất thường | Ticket, owner, quy định CA, chi tiết SAN và thời điểm |
| Tên gợi ý chức năng nhạy cảm như admin, vpn, staging | Có thể làm lộ thông tin hạ tầng hoặc chính sách đặt tên | Xác minh có dịch vụ thật hay chỉ tên lịch sử/wildcard |
| Chứng chỉ phát hành vào thời điểm bất thường | Hữu ích khi đối chiếu với hoạt động thay đổi | Change log, pipeline ACME, thông báo từ CA |
| Nhiều chứng chỉ mới hoặc hàng loạt SAN thay đổi | Có thể là rollout lớn, gia hạn hoặc sự kiện đáng điều tra | Tần suất cấp phát chuẩn, nhóm triển khai, fingerprint |
| Tên miền giống thương hiệu nhưng **ngoài domain sở hữu** | Có thể liên quan giám sát giả mạo thương hiệu | Dùng quy trình threat intelligence riêng, xác minh quyền sở hữu; không tự coi là tài sản tổ chức |

**Không nên cảnh báo chỉ vì có chứng chỉ mới.** Gia hạn tự động bằng ACME hoặc thay đổi phân phối dịch vụ có thể tạo lượng lớn bản ghi hoàn toàn hợp lệ. Bộ giám sát nên dùng thông tin **owner, môi trường, issuer được phê duyệt, tần suất và lịch triển khai** để xếp hạng mức độ.

### 8.2. Quy trình giám sát tối thiểu

1. **Định nghĩa danh mục domain sở hữu:** Tách domain sản xuất, thử nghiệm và domain của đối tác. Thiết lập người phụ trách.
2. **Theo dõi nguồn CT đáng tin cậy:** Dùng monitor hoặc dịch vụ có khả năng theo dõi liên tục; đối chiếu nhiều nguồn khi mức độ rủi ro yêu cầu.
3. **Lọc và chuẩn hóa:** Xử lý SAN, wildcard, dữ liệu lặp và tên ngoài phạm vi.
4. **So với inventory:** Liên kết phát hiện với dịch vụ, chứng chỉ đang sử dụng, CA, deployment hoặc ticket.
5. **Phân loại:** Hoạt động hợp lệ / cần bổ sung inventory / nghi cấp phát bất thường / chưa đủ bằng chứng.
6. **Điều tra và khắc phục:** Liên hệ chủ sở hữu, xác minh từ nguồn cấp chứng chỉ, xử lý khóa/chứng chỉ nếu cần.
7. **Ghi nhận kết quả:** Lưu bằng chứng tối thiểu, người chịu trách nhiệm, thời điểm, độ tin cậy và ngày đánh giá lại.

Nếu dùng chỉ mục bên thứ ba, cần chú ý **độ trễ chỉ mục, giới hạn truy vấn, khả năng thiếu log, thay đổi API và dữ liệu trùng**. Để theo dõi sự kiện quan trọng, nên dựa vào pipeline được vận hành và kiểm chứng có chủ đích thay vì coi một truy vấn tra cứu là đầy đủ tuyệt đối.

## 9. CT kết hợp với DNS, PKI và kiểm soát mạng

Một tên miền phụ xuất hiện trong CT chỉ là một dữ kiện. Cần kết hợp nhiều lớp để đưa ra kết luận an ninh:

| Lớp | Kiểm tra cần thực hiện | CT đóng vai trò gì? |
| --- | --- | --- |
| **PKI/TLS** | Chuỗi tin cậy, SAN, chứng chỉ đang dùng, hết hạn và trạng thái thu hồi | Bổ sung lịch sử và khả năng phát hiện cấp phát ngoài kỳ vọng |
| **DNS** | Bản ghi DNS, nguồn quản lý zone, CAA, thay đổi DNS | Gợi ý tên cần đối chiếu; bản thân CT không xác nhận DNS hiện hành |
| **Phân đoạn/firewall** | Dịch vụ được phép truy cập từ đâu và qua cổng nào | Không chứng minh các cổng thực sự mở |
| **VPN và truy cập từ xa** | Endpoint được quản lý, cấu hình xác thực, MFA, chính sách truy cập | Tên như vpn.example.org là tín hiệu cần kiểm chứng, không phải bằng chứng hoạt động |
| **IDS/IPS/NDR** | Lưu lượng bất thường, hành vi xâm nhập và tương quan sự kiện | Có thể cung cấp tên tài sản để bổ sung ngữ cảnh điều tra |
| **Cloud/Ingress** | Load balancer, gateway, certificate manager, namespace, public endpoint | Hỗ trợ phát hiện tên có khả năng chưa được đưa vào inventory |
| **Threat modeling** | Trust boundary, tài sản, điều kiện khai thác, rủi ro | CT cho biết một loại thông tin công khai mà đối thủ có thể sử dụng |

### 9.1. DNS CAA có thay được CT không?

Không. **CAA (Certification Authority Authorization)** là bản ghi DNS để chủ sở hữu domain biểu đạt CA nào được phép cấp chứng chỉ theo cơ chế tiêu chuẩn. CAA là một **kiểm soát trước khi cấp** có ý nghĩa trong quy trình CA, còn CT là **cơ chế minh bạch và giám sát việc cấp phát**.

CAA không bảo đảm ngăn chặn mọi trường hợp cấp phát sai do lỗi hoặc việc bị xâm nhập; CT cũng không thay việc cấu hình CAA. Kết hợp CAA, quản lý tài khoản ACME, quản lý chứng chỉ và theo dõi CT tạo ra phòng vệ tốt hơn từng cơ chế riêng lẻ.

### 9.2. CT có giải quyết việc hết hạn chứng chỉ không?

CT hiển thị **Not After** trong chứng chỉ, nhưng một chứng chỉ xuất hiện trên log có thể đã bị thay, không còn triển khai hoặc đã bị thu hồi. Để cảnh báo chứng chỉ sắp hết hạn, phải biết **chứng chỉ nào đang được sử dụng trên endpoint hoặc trong certificate manager**. CT hỗ trợ phát hiện vật chứng cần kiểm tra, không phải nguồn duy nhất để quản lý vòng đời TLS.

### 9.3. CT có cho biết địa chỉ IP và cổng dịch vụ không?

Không theo cách mặc định của trường SAN DNS. CT đưa ra **tên** và dữ liệu chứng chỉ; DNS, CDN, load balancer và service discovery mới quyết định cách tên ánh xạ sang hạ tầng tại một thời điểm. Một IP có thể phục vụ nhiều tên qua SNI; một tên có thể thay IP theo vùng, thời điểm hoặc nhà cung cấp.

## 10. Threat modeling: CT tạo ra những tín hiệu và rủi ro nào?

CT cải thiện khả năng phát hiện cấp phát chứng chỉ bất thường, đồng thời làm tăng thông tin công khai về một số tên miền. Trong STRIDE, có thể xem xét cả góc nhìn phòng vệ và dấu vết hỗ trợ tấn công:

| Nhóm STRIDE | Kịch bản liên quan | Cách xử lý |
| --- | --- | --- |
| **Spoofing** | Chứng chỉ được cấp ngoài kỳ vọng cho tên doanh nghiệp hoặc có tên gần giống nhằm gây nhầm lẫn | Monitor CT, xác minh quy trình CA; client vẫn phải kiểm tra TLS đúng tên/chuỗi tin cậy |
| **Tampering** | Bên không tin cậy tìm cách thay cấu hình TLS/DNS hoặc chứng chỉ trong triển khai | Kiểm soát thay đổi, chữ ký cấu hình, phân quyền và đối chiếu chứng chỉ đang dùng |
| **Repudiation** | Tranh chấp việc chứng chỉ đã từng được đưa vào log hay chưa | Bằng chứng CT và dữ liệu kiểm toán hỗ trợ truy vết; không chứng minh đầy đủ ai đã yêu cầu cấp |
| **Information Disclosure** | SAN chứa tên hệ thống nội bộ, môi trường test hoặc thông tin đặt tên nhạy cảm | Chính sách đặt tên, phân loại thông tin trước khi xin public cert |
| **Denial of Service** | Phụ thuộc vào duy nhất dịch vụ tra cứu CT, monitor mất dữ liệu khi dịch vụ chậm/gián đoạn | Giám sát độ trễ, lưu checkpoint, retry, nhiều nguồn |
| **Elevation of Privilege** | Người có quyền cấp cert hoặc thay đổi DNS/ACME quá rộng có thể lợi dụng quy trình cấp phát | Giới hạn quyền, xác thực mạnh, phê duyệt, audit |

### Mô hình rủi ro đơn giản

Ví dụ trường hợp **SAN tiết lộ tên admin-preprod.example.org**:

~~~text
Tài sản: Tên môi trường thử nghiệm và cấu trúc dịch vụ
Nguồn công khai: CT entry chứa admin-preprod.example.org
Người quan sát: Bất kỳ ai truy cập dữ liệu CT công khai
Điều có thể biết: Một tên gợi ý sự tồn tại của dịch vụ/môi trường
Điều chưa được biết: Host đang online, IP, port, phần mềm, lỗ hổng
Rủi ro: Tăng khả năng phát hiện mục tiêu qua reconnaissance
Biện pháp: Chính sách đặt tên, xác thực mạnh, phân đoạn, không lộ
           dịch vụ ngoài phạm vi cần thiết, giám sát cấu hình
Bằng chứng: Inventory, cấu hình ingress/firewall, kiểm tra DNS và
            chính sách truy cập đã được phê duyệt
~~~

**Không thể “ẩn một hostname đã đưa vào CT” bằng cách xóa DNS record.** Dữ liệu đã công bố có thể còn được lưu giữ trong log và các chỉ mục bên thứ ba. Nếu tên hệ thống quá nhạy cảm, giải pháp dài hạn là điều chỉnh chính sách thiết kế và phát hành chứng chỉ; đồng thời bảo vệ dịch vụ thật bằng kiểm soát truy cập phù hợp. Đừng dựa vào việc “khó đoán hostname” như một biện pháp xác thực.

## 11. Case study: phát hiện chứng chỉ cho tên truy cập quản trị

**Bối cảnh giả định:** Đội an ninh vận hành tên miền **example.org** và có danh mục được duyệt gồm **www.example.org**, **api.example.org** và một số tên dịch vụ nội bộ. Một ngày, monitor CT thông báo chứng chỉ hoặc precertificate mới chứa **admin.example.org** với issuer khác nhà cung cấp thường dùng.

### Diễn biến xử lý

1. **Tiếp nhận tín hiệu:** Lưu CT log/entry hoặc đường dẫn tra cứu, tên SAN, issuer, mốc thời gian và dấu nhận diện chứng chỉ. Không coi sự kiện là sự cố xâm nhập trước khi xác minh.
2. **Phân biệt dạng bản ghi:** Kiểm tra dữ liệu là precertificate hay certificate; tìm các bản ghi liên quan và trùng lặp. SCT và log entry chưa chứng minh chứng chỉ đã triển khai.
3. **Đối chiếu chủ sở hữu:** Tra inventory, lịch triển khai, ticket và người được phép cấp chứng chỉ cho admin.example.org.
4. **Đối chiếu DNS và cấu hình:** Dùng nguồn cấu hình được phép để xem record, certificate manager, ingress và endpoint có sử dụng chứng chỉ đó hay không.
5. **Kiểm tra tuyến cấp phát:** Xác minh tài khoản ACME/CA, quyền thay đổi DNS, chứng chỉ/khóa và CAA. Một issuer khác có thể do migration hợp lệ.
6. **Xếp loại và xử lý:** Nếu hợp lệ, cập nhật inventory; nếu nghi cấp sai, liên hệ CA, xác minh nguy cơ lộ khóa và yêu cầu thu hồi khi phù hợp. Nếu có xâm nhập tài khoản hoặc private key, thực hiện quy trình ứng phó và thay khóa, rà soát tác động.
7. **Học từ sự kiện:** Cải thiện cảnh báo, danh mục domain, quản lý quyền cấp chứng chỉ và quy trình phê duyệt.

### Ma trận quyết định

| Bằng chứng tìm được | Cách diễn giải | Hành động tiếp theo |
| --- | --- | --- |
| Có ticket và owner xác nhận tạo cert cho admin.example.org | Nhiều khả năng phát hành hợp lệ | Cập nhật inventory, đóng cảnh báo có bằng chứng |
| Chưa có trong inventory nhưng thuộc dự án thử nghiệm được phê duyệt | Thiếu cập nhật quản trị tài sản | Bổ sung chủ sở hữu và quy trình đăng ký |
| Không có owner, tài khoản ACME đáng ngờ, issuer khác quy định | Có nguy cơ cấp phát ngoài kỳ vọng | Điều tra khẩn, làm việc với CA và đội hạ tầng |
| Chỉ thấy precertificate, không thấy endpoint sử dụng | Có khả năng nộp log nhưng chưa triển khai | Tiếp tục xác minh, không tự khẳng định có endpoint nguy hiểm |
| Chứng chỉ đã hết hạn hoặc tên không phân giải | Dấu vết lịch sử có thể không còn hoạt động | Lưu bối cảnh, cân nhắc mức ưu tiên và lịch sử sự kiện |

Điểm cốt lõi: **CT giúp phát hiện sự kiện cần điều tra**, còn kết luận phụ thuộc vào bằng chứng vận hành và tính hợp lệ của việc cấp phát.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Certificate Transparency là kho chứa toàn bộ website trên Internet.” | CT ghi dữ liệu chứng chỉ/precertificate được công bố; không kiểm kê đầy đủ host hoặc ứng dụng. |
| “Có domain trong CT nghĩa là domain đang hoạt động.” | DNS, endpoint và dịch vụ đang dùng phải được kiểm tra riêng. |
| “SCT chứng minh chứng chỉ đã được ghi vào log.” | SCT là cam kết có chữ ký; cần inclusion proof để chứng minh đã ghi. |
| “Một mục nằm trong CT là chứng chỉ TLS đáng tin.” | Sự hiện diện trong log không thay thế xác minh PKI, hostname, hạn và chính sách client. |
| “CT luôn hiển thị mọi chứng chỉ nội bộ.” | Chứng chỉ do CA nội bộ cấp thường nằm ngoài phạm vi public CT. |
| “Wildcard *.example.org cho biết tất cả subdomain.” | Wildcard chỉ là mẫu tên, không liệt kê host được triển khai. |
| “Tên giống thương hiệu chắc chắn thuộc doanh nghiệp.” | Phải xác minh quyền sở hữu; tên ngoài hậu tố domain đã duyệt không tự nằm trong phạm vi. |
| “CT có thể ngăn CA phát hành chứng chỉ sai.” | CT tăng khả năng phát hiện và kiểm toán; phản ứng/thu hồi cần quy trình riêng. |
| “CT hiển thị certificate hết hạn là server hiện tại hết hạn.” | Có thể đó là chứng chỉ lịch sử; kiểm tra cert đang phục vụ thực tế. |
| “CT thay thế DNSSEC hoặc CAA.” | Mỗi cơ chế có mục tiêu và phạm vi riêng; CT không xác thực bản ghi DNS hay hạn chế CA như chính sách CAA. |

## 13. Câu hỏi tự kiểm tra

1. **Certificate Transparency hỗ trợ reconnaissance ra sao?** Nó đưa ra dữ liệu chứng chỉ công khai, đặc biệt các tên SAN, để hình thành danh sách tên miền cần xác minh mà không phải quét host trực tiếp.
2. **SCT có nghĩa là chứng chỉ đã được bao hàm trong log chưa?** Chưa. SCT là lời hứa được log ký; cần inclusion proof tương ứng để kiểm tra bao hàm.
3. **Vì sao cần consistency proof?** Để kiểm tra các phiên bản cây log duy trì quan hệ append-only khi cây phát triển.
4. **Trong CT có \*.dev.example.org thì có thể kết luận dev1.example.org đang chạy không?** Không. Wildcard không liệt kê hoặc chứng minh host cụ thể.
5. **Một issuer lạ trong CT có chắc là CA bị tấn công không?** Không. Có thể do thay đổi nhà cung cấp hoặc quy trình hợp lệ; cần bằng chứng cấp phát và chủ sở hữu.
6. **Tại sao không dùng so khớp chuỗi đơn giản \`contains("example.org")\` để xác định phạm vi?** Nó nhận nhầm tên như example.org.evil.test; phải kiểm tra chính xác domain gốc hoặc hậu tố có dấu chấm.
7. **CT có giúp thấy private key của máy chủ không?** Không. CT công khai dữ liệu chứng chỉ/khóa công khai, không công bố private key.
8. **Tại sao browser vẫn cần kiểm tra chứng chỉ TLS sau khi chứng chỉ được log?** Vì CT phục vụ minh bạch cấp phát; xác thực endpoint, hostname, thời hạn và chính sách tin cậy là các phép kiểm riêng.
9. **Khi thấy cert mới cho admin.example.org, bước ưu tiên đầu tiên là gì?** Ghi nhận bằng chứng, đối chiếu owner/inventory/ticket và xác minh đường cấp phát, tránh suy luận chỉ từ CT.
10. **Vì sao CT phải kết hợp với quản lý DNS, PKI và giám sát mạng?** Vì CT chỉ cung cấp một phần tín hiệu về tên và chứng chỉ, trong khi DNS, endpoint, quyền truy cập và lưu lượng có đặc tính vận hành riêng.

### Bài tập vận dụng

Một tổ chức sở hữu **example.org** nhận ba phát hiện CT:

~~~text
A. SAN = api.example.org; issuer = CA đã phê duyệt
B. SAN = *.internal.example.org; issuer = CA đã phê duyệt
C. SAN = login.example.org.evil.test; issuer = CA chưa biết
~~~

Hãy lập bảng gồm: **thuộc phạm vi hay không, CT thật sự chứng minh điều gì, cần xác minh thêm gì và mức ưu tiên điều tra**. Gợi ý: A cần đối chiếu inventory; B là dấu hiệu lộ mẫu tên có chữ “internal” nhưng không chỉ ra host cụ thể; C nằm ngoài hậu tố tên miền sở hữu, phù hợp xử lý như tín hiệu thương hiệu/giả mạo nếu có căn cứ chứ không đưa vào danh mục host của example.org.

## 14. Tài liệu chuẩn để đọc thêm

- **RFC 6962 – Certificate Transparency:** Mô hình CT v1, log, SCT, Merkle tree, inclusion proof và consistency proof. https://www.rfc-editor.org/rfc/rfc6962
- **RFC 9162 – Certificate Transparency Version 2.0:** Phiên bản CT v2 và các thay đổi giao thức. https://www.rfc-editor.org/rfc/rfc9162
- **RFC 5280 – Internet X.509 Public Key Infrastructure Certificate and CRL Profile:** Nền tảng đọc chứng chỉ X.509 và các trường của chứng chỉ. https://www.rfc-editor.org/rfc/rfc5280
- **RFC 8659 – DNS Certification Authority Authorization (CAA) Resource Record:** Cơ chế DNS CAA. https://www.rfc-editor.org/rfc/rfc8659
- **RFC 8555 – Automatic Certificate Management Environment (ACME):** Quy trình tự động hóa yêu cầu/cấp chứng chỉ. https://www.rfc-editor.org/rfc/rfc8555

**Ghi nhớ khi áp dụng:** CT là **nguồn bằng chứng về việc cấp phát chứng chỉ được công khai** và là công cụ **reconnaissance thụ động** rất hữu ích. Để xây dựng kiến trúc mạng an toàn, cần liên kết dữ liệu CT với chủ sở hữu tài sản, DNS, PKI, xác thực kết nối, phân đoạn, chính sách firewall, VPN và hoạt động giám sát. Mọi phát hiện nên được ghi là **giả thuyết có nguồn** cho tới khi đã xác minh bằng bằng chứng vận hành phù hợp.
