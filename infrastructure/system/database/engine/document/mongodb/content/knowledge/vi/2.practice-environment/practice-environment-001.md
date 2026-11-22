# Lựa chọn MongoDB Community, Enterprise và Atlas theo môi trường

## Mục tiêu bài học

Khi triển khai một ứng dụng dùng MongoDB, lựa chọn đầu tiên không phải là viết câu lệnh truy vấn mà là quyết định **MongoDB sẽ chạy ở đâu, ai vận hành và mức bảo đảm nào cần có**. Ba tên thường gặp là **MongoDB Community Edition**, **MongoDB Enterprise (Enterprise Advanced)** và **MongoDB Atlas**. Chúng phục vụ các nhu cầu khác nhau, nhưng vẫn dựa trên mô hình dữ liệu document và hệ sinh thái driver MongoDB.

Sau bài học, người học có thể:

- Phân biệt **phiên bản máy chủ** (Community/Enterprise) với **dịch vụ triển khai và vận hành** (Atlas).
- Chọn môi trường phù hợp cho thực hành cá nhân, CI, development, staging và production.
- Nhận diện những yêu cầu có thể khiến Community không còn là lựa chọn phù hợp: kiểm toán, quản trị tập trung, hỗ trợ thương mại, vị trí dữ liệu hoặc vận hành nhiều cụm.
- Tạo môi trường Community cục bộ và chuẩn bị kết nối Atlas an toàn ở mức cơ bản.
- Giải thích quyết định dựa trên **chi phí sở hữu toàn phần, trách nhiệm vận hành, bảo mật, độ sẵn sàng và khả năng mở rộng**, thay vì chỉ so giá cài đặt.

> **Nguyên tắc cốt lõi:** Community và Enterprise là hai edition của MongoDB Server có thể tự quản lý. Atlas là dịch vụ cơ sở dữ liệu MongoDB được MongoDB vận hành trên hạ tầng đám mây. Vì vậy, so sánh ba lựa chọn phải xét cả **năng lực phần mềm** lẫn **mô hình vận hành**.

## 1. Xác định đúng bài toán môi trường

Một chương trình CRUD vài trăm document chạy trên máy cá nhân có yêu cầu rất khác với hệ thống giao dịch hàng triệu người dùng. Khi chọn MongoDB, hãy trả lời lần lượt:

1. **Dữ liệu được phép đặt ở đâu?** Máy cá nhân, máy chủ nội bộ, private cloud hay public cloud? Có yêu cầu lưu dữ liệu tại một vùng địa lý cụ thể không?
2. **Ai vận hành database?** Nhóm có người trực về backup, khôi phục, nâng cấp, giám sát và xử lý sự cố hay muốn giao bớt các công việc ấy cho nhà cung cấp?
3. **Tính năng bảo mật và tuân thủ nào bắt buộc?** Chỉ cần xác thực, phân quyền và TLS, hay còn cần audit chuyên biệt, tích hợp cơ chế định danh doanh nghiệp, mã hóa dữ liệu lưu trữ theo cơ chế cụ thể?
4. **Mức tải và yêu cầu sẵn sàng ra sao?** Học tập ngắn hạn, môi trường kiểm thử, dịch vụ ít truy cập hay production cần nhiều vùng sẵn sàng, khôi phục sau thảm họa?
5. **Giới hạn chi phí và thời gian vận hành là gì?** Chi phí license chỉ là một phần; còn máy chủ, lưu trữ, mạng, backup, hỗ trợ, nhân sự trực và thời gian xử lý sự cố.
6. **Có cần kiểm soát sâu máy chủ không?** Ví dụ truy cập hệ điều hành, cấu hình tiến trình, công cụ riêng, mạng nội bộ cách ly hoàn toàn hoặc lịch nâng cấp do doanh nghiệp tự quyết.

Các câu trả lời này là đầu vào cho quyết định kỹ thuật. Không tồn tại một edition luôn tốt nhất cho mọi môi trường.

## 2. Ba lựa chọn thực sự khác nhau ở điểm nào?

### 2.1. MongoDB Community Edition

Community Edition là **MongoDB Server miễn phí về phí sử dụng phần mềm** mà nhóm tự cài đặt trên laptop, máy ảo, máy chủ riêng hoặc container. Nó cung cấp các khả năng nền tảng như lưu document BSON, CRUD, index, aggregation pipeline, transaction theo điều kiện hỗ trợ, replica set và sharding.

Community phù hợp khi muốn:

- Học lệnh MongoDB và mô hình document bằng một database chạy tại chỗ.
- Xây dựng proof of concept, phát triển tính năng hoặc chạy integration test trong CI.
- Tự quản trị cơ sở hạ tầng và không cần bộ tính năng thương mại riêng.
- Chủ động tổ chức dữ liệu thử nghiệm, seed dữ liệu, tạo/xóa môi trường nhanh.

**Điểm cần hiểu:** Community có thể chạy production nếu đội ngũ chấp nhận và thực hiện đầy đủ công việc vận hành. Nó không tự cung cấp dịch vụ backup, hỗ trợ khẩn cấp hay cam kết uptime. Các khả năng cơ bản như TLS, authentication và role-based access control vẫn hiện diện; không nên nhầm Community với một database chỉ dành cho thử nghiệm.

MongoDB Server Community hiện đại sử dụng giấy phép **Server Side Public License (SSPL)**. Việc miễn phí không có nghĩa là được sử dụng theo bất kỳ cách nào mà không cần xem điều khoản. Đặc biệt, trường hợp cung cấp MongoDB như một dịch vụ cho bên thứ ba cần được bộ phận pháp lý đánh giá. Driver và công cụ liên quan có thể dùng giấy phép khác.

### 2.2. MongoDB Enterprise và Enterprise Advanced

**MongoDB Enterprise Server** là edition thương mại dành cho triển khai tự quản lý. **Enterprise Advanced** thường chỉ gói thuê bao bao gồm Enterprise Server, các công cụ quản lý/vận hành và hỗ trợ kỹ thuật theo hợp đồng.

So với Community, Enterprise bổ sung các khả năng có giá trị trong nhiều môi trường doanh nghiệp, tùy phiên bản và quyền sử dụng:

- **Auditing**: ghi nhận các sự kiện bảo mật và thao tác liên quan theo cấu hình, phục vụ điều tra và tuân thủ.
- **Tích hợp cơ chế xác thực doanh nghiệp** như Kerberos hoặc các lựa chọn liên quan đến danh tính doanh nghiệp, theo phiên bản và nền tảng hỗ trợ.
- **Mã hóa lưu trữ ở cấp database** và lựa chọn quản lý khóa phù hợp, ngoài khả năng mã hóa ổ đĩa ở cấp hệ điều hành.
- **Bộ công cụ quản trị tập trung**, tự động hóa backup, triển khai, giám sát và nâng cấp theo quyền lợi gói dịch vụ.
- **Hỗ trợ thương mại** và cam kết phản hồi theo hợp đồng.

Enterprise thường được chọn khi database phải chạy trên **on-premises, private cloud hoặc môi trường hybrid**, trong khi tổ chức vẫn cần kiểm soát hạ tầng và quy trình vận hành.

Một điểm phân biệt quan trọng: **mua Enterprise không biến hệ thống thành dịch vụ managed**. Đội ngũ vẫn phải lập kế hoạch hạ tầng, phân vùng mạng, giám sát, dung lượng, backup, kiểm thử restore và quản trị thay đổi. Công cụ hỗ trợ có thể tự động hóa nhiều bước, nhưng trách nhiệm vận hành vẫn thuộc đơn vị sở hữu hệ thống.

### 2.3. MongoDB Atlas

Atlas là **dịch vụ MongoDB được quản lý trên public cloud**, có lựa chọn triển khai trên AWS, Azure và Google Cloud. Người dùng chọn vùng triển khai, loại cluster, cấu hình kết nối và các chính sách phù hợp; dịch vụ hỗ trợ provisioning, vận hành hạ tầng database, nhiều tác vụ backup, nâng cấp, mở rộng, giám sát và failover tùy tier.

Atlas giúp nhóm tập trung vào schema, query, index và ứng dụng thay vì trực tiếp quản lý tiến trình MongoDB, hệ điều hành và nhiều thao tác hạ tầng.

Các nhóm cluster phổ biến gồm:

| Nhóm Atlas | Cách dùng điển hình | Điều cần lưu ý |
|---|---|---|
| **Free (M0)** | Học tập, thử driver, POC nhỏ | Tài nguyên chia sẻ, hạn mức và tính năng bị giới hạn; không dùng làm thước đo hiệu năng production |
| **Flex** | Development/test trên cloud, ứng dụng tải thấp và thay đổi | Có tính phí, hạn mức khác Dedicated; backup định kỳ và tính năng phụ thuộc tier |
| **Dedicated (M10 trở lên, tùy cấu hình)** | Staging cần gần production, dịch vụ thực tế với yêu cầu tài nguyên và kiểm soát cao hơn | Phải dự toán chi phí, topology, backup, network, độ sẵn sàng và công suất |

**Lưu ý tính thời điểm:** Atlas thay đổi tên tier, giới hạn, cấu hình và chính sách giá theo thời gian. Các tier M2/M5 và Serverless cũ đã được thay bằng mô hình mới; khi tạo môi trường, kiểm tra lại trang cluster types/limits chính thức, không sao chép hướng dẫn cũ.

Atlas **không loại bỏ trách nhiệm của nhóm ứng dụng**. Nhóm vẫn phải thiết kế dữ liệu và index, quản lý user/role, cấu hình IP access list hoặc private networking, quản lý secrets, kiểm tra backup/restore, chọn vùng dữ liệu, đặt cảnh báo và kiểm soát ngân sách.

## 3. Bảng so sánh để ra quyết định

| Tiêu chí | Community tự quản lý | Enterprise tự quản lý | Atlas managed |
|---|---|---|---|
| Mô hình | Cài MongoDB Server trên hạ tầng của bạn | Cài Enterprise Server trên hạ tầng của bạn | Sử dụng database cloud do MongoDB vận hành |
| Phí phần mềm/dịch vụ | Không có phí bản quyền Community; vẫn tốn hạ tầng/vận hành | Thuê bao, license/hỗ trợ thương mại theo hợp đồng, cộng hạ tầng | Miễn phí ở tier giới hạn hoặc trả theo cấu hình và mức sử dụng |
| Kiểm soát OS, máy chủ, tiến trình | Cao | Cao | Hạn chế theo giao diện và API dịch vụ |
| Vị trí triển khai | Laptop, VM, container, data center, private cloud | Data center, private/hybrid cloud và hạ tầng tự quản lý | Các vùng cloud được Atlas hỗ trợ |
| Cài đặt ban đầu | Tự cài; đơn giản với Docker | Tự cài và cấu hình license/công cụ liên quan | Tạo project và cluster qua cloud console/API |
| Backup, nâng cấp, monitoring | Đội ngũ tự tổ chức | Đội ngũ sở hữu, có thể dùng công cụ thương mại hỗ trợ | Nhiều thao tác được dịch vụ hỗ trợ/tự động hóa, tùy tier |
| Bảo mật cơ bản | Authentication, authorization, TLS và hardening do đội ngũ cấu hình | Tương tự, thêm các khả năng enterprise theo gói/phiên bản | Nhiều lớp bảo mật được tích hợp; vẫn cần cấu hình quyền và kết nối |
| Audit và tích hợp doanh nghiệp | Giới hạn so với Enterprise; có thể dùng công cụ bổ sung bên ngoài | Có lựa chọn chuyên biệt | Có lựa chọn tùy cluster tier và dịch vụ |
| Hỗ trợ kỹ thuật | Tài liệu, cộng đồng hoặc dịch vụ khác do tổ chức tự mua | Hỗ trợ MongoDB theo thuê bao/hợp đồng | Theo gói hỗ trợ và điều khoản Atlas |
| Phù hợp nhất | Học tập, local dev, CI, POC; production nếu tự vận hành được | Production tự quản lý có yêu cầu tuân thủ/hỗ trợ chuyên sâu | Nhóm muốn database managed trên public cloud |

**Cách đọc bảng:** Tiêu chí quan trọng nhất là **địa điểm bắt buộc của dữ liệu và người chịu trách nhiệm vận hành**. Sau đó mới so khả năng bảo mật, hiệu năng và chi phí. Atlas không phải một edition máy chủ “cao hơn” Community hay Enterprise trong mọi tiêu chí; nó là một lựa chọn kiến trúc vận hành.

## 4. Chọn theo từng môi trường thực hành và triển khai

### 4.1. Học tập trên laptop hoặc máy cá nhân

**Khuyến nghị mặc định: MongoDB Community chạy bằng Docker hoặc cài trực tiếp.**

Lý do:

- Không phải tạo tài khoản cloud hay cấu hình firewall từ Internet.
- Có thể làm lại bài tập, xóa database, reset volume, tạo user và quan sát log.
- Kết nối qua localhost nên truy cập nhanh và ít phụ thuộc đường truyền.
- Dễ kiểm soát phiên bản MongoDB để các bài thực hành chạy thống nhất.

Dùng Atlas Free khi bài học cần thực hành **kết nối database cloud, IP access list, database user, URI dạng mongodb+srv hoặc dịch vụ đặc thù của Atlas**. Hai lựa chọn có thể cùng tồn tại: Community để thử thao tác nội bộ và Atlas để học triển khai cloud.

**Ngoại lệ:** Nếu bài yêu cầu replica set, transaction hoặc change stream, một tiến trình standalone sẽ không mô phỏng đủ hành vi. Cần cấu hình replica set, có thể là single-node replica set dành riêng cho local dev, hoặc dùng môi trường Atlas phù hợp. Không đánh đồng “đã kết nối được” với “đã tái hiện đúng topology production”.

### 4.2. CI và integration test tự động

**Khuyến nghị mặc định: Community trong container tạm thời**, ví dụ MongoDB Testcontainers hoặc Docker Compose của pipeline.

Một môi trường CI tốt cần:

- Được tạo mới cho mỗi test suite hoặc build để tránh dữ liệu rò rỉ giữa các lượt.
- Dùng phiên bản MongoDB và chế độ replica set phù hợp với các tính năng được kiểm thử.
- Có health check hoặc readiness check; không dựa vào sleep cố định.
- Seed dữ liệu tối thiểu, chạy test, thu log khi lỗi và dọn tài nguyên khi hoàn tất.
- Không phụ thuộc database production hoặc database của developer.

Atlas thích hợp cho một bộ **cloud integration test** riêng khi thực sự phải kiểm chứng kết nối, private endpoint, chính sách mạng hoặc hành vi Atlas. Không dùng chung cluster đang chứa dữ liệu thật để chạy test có quyền sửa/xóa dữ liệu.

### 4.3. Development dùng chung cho nhóm

Có hai phương án hợp lý:

- **Community trên máy chủ dev của nhóm:** phù hợp khi nhóm đã có VM/Kubernetes, có người quản trị database và muốn kiểm soát cấu hình.
- **Atlas Flex hoặc Dedicated nhỏ theo nhu cầu:** phù hợp khi nhiều developer làm việc từ xa và nhóm không muốn tự quản lý database server.

Với môi trường chung, nên cấp **tài khoản riêng, database riêng hoặc namespace dữ liệu riêng** theo nhóm/tính năng; tránh mọi developer cùng dùng root. Có chính sách reset dữ liệu, hạn mức, cách tạo seed và quyền xoá.

Đừng đưa mật khẩu database vào repository. Giữ connection string trong biến môi trường hoặc secret manager; phân quyền network và database theo nguyên tắc tối thiểu.

### 4.4. Staging và kiểm thử trước phát hành

**Staging nên phản ánh các hành vi ảnh hưởng trực tiếp đến production**, đặc biệt:

- Major version MongoDB, driver, feature compatibility và cấu hình nhất quán.
- Topology replica set/sharding, write concern, read preference và transaction.
- Index quan trọng, khối lượng dữ liệu mô phỏng, phân bố truy vấn.
- Kịch bản failover, timeout, backup/restore và cơ chế kết nối của ứng dụng.
- Chính sách authentication, TLS, network và quyền truy cập.

Nếu production chạy Atlas Dedicated, staging dùng Atlas với cấu hình đủ tương đồng để kiểm thử các khả năng cần thiết; không mặc định Atlas Free phản ánh latency, throughput hoặc failover của production. Nếu production là Enterprise on-premises, staging nên kiểm thử các chính sách/tính năng Enterprise liên quan.

Không cần nhân bản toàn bộ dữ liệu production. Ưu tiên **dữ liệu tổng hợp hoặc được khử định danh** theo quy định bảo mật.

### 4.5. Production trên public cloud

**Atlas Dedicated thường là điểm xuất phát đáng cân nhắc** khi tổ chức chấp nhận public cloud và ưu tiên giảm gánh nặng quản trị database. Cần xác minh:

- Vùng cloud phù hợp yêu cầu lưu trữ dữ liệu và độ trễ đến ứng dụng.
- Cluster đủ tài nguyên, topology sẵn sàng cao, chiến lược scale.
- Backup, thời gian lưu snapshot, mục tiêu khôi phục và restore drill.
- Private connectivity nếu yêu cầu; không mở truy cập Internet rộng.
- Giám sát latency, CPU, bộ nhớ, disk I/O, slow query, kết nối, cảnh báo và chi phí.
- Thỏa thuận hỗ trợ, yêu cầu tuân thủ và phương án thoát dịch vụ.

**Community hoặc Enterprise tự quản lý** vẫn phù hợp nếu tổ chức chủ động muốn quản trị trên hạ tầng cloud của mình. Khi ấy cần tính đủ công sức triển khai, vận hành, bảo vệ và phục hồi cụm database.

### 4.6. Production trong data center, private cloud hoặc hệ thống cách ly mạng

Khi yêu cầu **on-premises, air-gapped** hoặc không được đưa dữ liệu lên Atlas, chọn **tự quản lý MongoDB**.

- Chọn **Enterprise** nếu bắt buộc audit chuyên biệt, tính năng bảo mật doanh nghiệp, công cụ quản trị tập trung hoặc hỗ trợ thương mại.
- Chọn **Community** khi các tính năng cơ bản đủ, điều khoản sử dụng phù hợp và đội ngũ chịu trách nhiệm đầy đủ việc vận hành/hỗ trợ.

Không nên chọn Atlas chỉ vì nó có tính năng managed nếu vị trí lưu trữ và luồng dữ liệu vi phạm chính sách triển khai.

### 4.7. Workshop, demo và proof of concept ngắn hạn

Hai lựa chọn tiết kiệm công sức:

1. **Community local:** tốt khi workshop phải chạy cả lúc mất Internet hoặc cần thao tác cài đặt, restart, log, dữ liệu.
2. **Atlas Free:** tốt khi muốn người học kết nối từ ứng dụng với cluster cloud nhỏ và khám phá giao diện Atlas.

Bản demo có thể cần đơn giản; điều đó không chứng minh cấu hình demo an toàn hoặc đủ tải cho production. Kết thúc workshop, nhớ dọn cluster không còn dùng, user, IP access list, secret và volume chứa dữ liệu nhạy cảm.

## 5. Quy trình ra quyết định trong sáu bước

**Bước 1 — Khoanh vùng vị trí triển khai.** Nếu dữ liệu phải nằm trong mạng riêng hoặc data center không kết nối cloud, tập trung vào Community/Enterprise. Nếu public cloud được phép, Atlas trở thành ứng viên.

**Bước 2 — Kiểm kê năng lực đội ngũ.** Có DBA/SRE trực, monitoring, phương án backup, restore và quy trình upgrade? Nếu chưa có, chi phí tự quản lý có thể vượt khoản tiết kiệm license.

**Bước 3 — Ghi yêu cầu bảo mật thành tính năng kiểm chứng được.** Ví dụ: “cần audit đăng nhập và thay đổi quyền giữ 180 ngày”, “chỉ cho phép ứng dụng qua private network”, “khóa mã hóa phải do công ty kiểm soát”. Sau đó xác minh tính năng đó được hỗ trợ bởi **edition, tier, phiên bản và khu vực** cụ thể.

**Bước 4 — Chốt mục tiêu khôi phục.** Định nghĩa RPO (độ mất dữ liệu tối đa có thể chấp nhận) và RTO (thời gian tối đa để phục hồi). Chọn topology, replication và backup tương ứng; không suy ra RPO/RTO chỉ từ tên edition.

**Bước 5 — So tổng chi phí.** Ước tính theo cùng kỳ 12–36 tháng:

- Community: VM/container, lưu trữ, IOPS, mạng, backup, monitoring, thời gian DBA/SRE và chi phí sự cố.
- Enterprise: các chi phí tự quản lý phía trên **cộng** thuê bao và dịch vụ hỗ trợ tương ứng.
- Atlas: compute/tier, dung lượng, IOPS, backup, truyền dữ liệu, mạng riêng, multi-region, dịch vụ bổ sung, hỗ trợ, vận hành ứng dụng và chênh lệch tăng trưởng tải.

**Bước 6 — Làm POC ngắn có tiêu chí đo.** Nạp mẫu dữ liệu và index thực tế, chạy truy vấn quan trọng, đo p95/p99 latency, throughput, restore time, thao tác cấp quyền và chi phí ước lượng. Chỉ chốt lựa chọn sau khi mọi yêu cầu bắt buộc đều có cách đáp ứng.

### Sơ đồ quyết định nhanh

~~~text
Có bắt buộc lưu và vận hành database trên hạ tầng nội bộ?
|
+-- CÓ --> Có yêu cầu Enterprise-only / hỗ trợ thương mại?
|            |
|            +-- CÓ  --> MongoDB Enterprise (Enterprise Advanced)
|            |
|            +-- KHÔNG --> Community + kế hoạch vận hành đầy đủ
|
+-- KHÔNG --> Muốn nhà cung cấp quản lý hạ tầng database?
             |
             +-- CÓ --> MongoDB Atlas
             |          |
             |          +-- Học/POC nhỏ --> Free
             |          +-- Dev/tải thấp --> Flex (kiểm tra giới hạn)
             |          +-- Staging/prod --> Dedicated theo yêu cầu
             |
             +-- KHÔNG --> Community hoặc Enterprise self-managed,
                          tùy yêu cầu tính năng và hỗ trợ
~~~

Đây là **bộ lọc đầu tiên**, không thay thế kiểm tra license, compliance, khả năng sẵn sàng và tài nguyên thực tế.

## 6. Thực hành A — Dựng Community local bằng Docker Compose

### 6.1. Chuẩn bị

Cần có Docker và Docker Compose. Ví dụ dùng image MongoDB **8.0** để minh họa cách cố định một nhánh phiên bản trong môi trường thực hành; đội ngũ nên chọn phiên bản đang được hỗ trợ và thống nhất với dự án.

Tạo thư mục bài tập, đặt file **compose.yaml**:

~~~yaml
services:
  mongodb:
    image: mongo:8.0
    container_name: mongo-lab
    restart: unless-stopped
    ports:
      - "127.0.0.1:27017:27017"
    environment:
      MONGO_INITDB_ROOT_USERNAME: labadmin
      MONGO_INITDB_ROOT_PASSWORD: "change-this-local-password"
    volumes:
      - mongo_lab_data:/data/db

volumes:
  mongo_lab_data:
~~~

Chạy trong thư mục chứa file:

~~~bash
docker compose up -d
docker compose ps
~~~

Port chỉ bind vào **127.0.0.1**, giúp hạn chế truy cập từ máy ngoài. Volume giữ dữ liệu khi container được tạo lại. Tài khoản **labadmin** chỉ dùng để khởi tạo bài lab, không nên dùng làm tài khoản của ứng dụng.

> Mật khẩu đặt trực tiếp trong Compose chỉ để minh họa ở môi trường local không có dữ liệu thật. Trong dự án nhóm, dùng biến môi trường hoặc Docker/Kubernetes secrets, tránh commit credential. Không mở port 27017 ra Internet.

### 6.2. Tạo tài khoản database với quyền tối thiểu

Mở MongoDB Shell bên trong container:

~~~bash
docker exec -it mongo-lab mongosh -u labadmin -p change-this-local-password --authenticationDatabase admin
~~~

Trong **mongosh**, tạo database và user thực hành:

~~~javascript
use mongo_labs

db.createUser({
  user: "labuser",
  pwd: "replace-with-another-local-password",
  roles: [
    { role: "readWrite", db: "mongo_labs" }
  ]
})

db.lessons.insertOne({
  title: "Choosing a MongoDB environment",
  environment: "community-local",
  completed: false,
  tags: ["mongodb", "practice"]
})

db.lessons.find({ environment: "community-local" })
~~~

Kết nối ứng dụng local bằng tài khoản **labuser**:

~~~text
mongodb://labuser:replace-with-another-local-password@localhost:27017/mongo_labs?authSource=mongo_labs
~~~

Trong ứng dụng Java/Spring Boot, cấu hình URI từ **biến môi trường** (chẳng hạn biến **SPRING_DATA_MONGODB_URI** khi dùng Spring Boot auto-configuration), tránh ghi mật khẩu thật vào mã nguồn hoặc file được commit.

### 6.3. Kiểm tra các hiện tượng cần quan sát

- Thử chèn document mới rồi đọc lại theo một điều kiện.
- Dừng và khởi động lại container; dữ liệu phải còn nhờ volume.
- Thử dùng sai mật khẩu; kết nối xác thực phải thất bại.
- Thử đăng nhập bằng user chỉ có quyền trên **mongo_labs**; không nên có quyền quản trị các database khác.
- Khi kiểm thử transaction/change streams, bổ sung cấu hình replica set phù hợp trước khi viết test.

Để kết thúc và giữ lại dữ liệu:

~~~bash
docker compose down
~~~

Để **xóa hẳn dữ liệu bài lab** (chỉ khi chắc chắn không cần giữ):

~~~bash
docker compose down -v
~~~

Tùy chọn **-v** xóa volume do Compose quản lý; không dùng tùy tiện với môi trường có dữ liệu quan trọng.

## 7. Thực hành B — Tạo môi trường Atlas cho ứng dụng

Atlas phù hợp khi muốn học luồng kết nối một cluster cloud. Các bước ở đây là quy trình khái niệm; tên màn hình và giới hạn tier có thể thay đổi.

1. **Tạo Organization/Project** dành riêng cho bài thực hành, đặt tên nhận diện rõ. Không dùng chung project quản lý dữ liệu production.
2. **Tạo cluster.** Chọn Free cho học tập nếu giới hạn đủ; chọn Flex hoặc Dedicated nếu cần backup, tài nguyên, khả năng kết nối hoặc tính năng khác. Chọn cloud provider và region gần nơi ứng dụng chạy, tuân thủ yêu cầu vị trí dữ liệu.
3. **Tạo database user** có role tối thiểu trên database của bài tập. Phân biệt tài khoản đăng nhập Atlas UI với tài khoản database.
4. **Cấu hình Network Access.** Chỉ thêm IP hiện đang sử dụng hoặc cơ chế kết nối riêng được phép. Với ứng dụng production, ưu tiên mạng riêng/private endpoint khi được hỗ trợ. Tránh để dải **0.0.0.0/0** mở lâu dài.
5. **Lấy connection string** do Atlas cung cấp, thường theo dạng SRV, rồi đưa vào secret manager/biến môi trường.
6. **Kết nối bằng driver phù hợp.** Kiểm tra TLS, DNS SRV, firewall outbound và quyền database; sau đó thử một thao tác ghi/đọc.
7. **Bật và kiểm tra vận hành.** Theo dõi kết nối, query latency, backup, cảnh báo, chi phí và giới hạn cluster.
8. **Dọn tài nguyên bài thực hành** khi hoàn tất và thu hồi quyền/kết nối không còn cần.

Ví dụ cấu trúc URI (giá trị minh họa, không phải host có thật):

~~~text
mongodb+srv://APP_USER:APP_PASSWORD@CLUSTER_HOST/APP_DB?retryWrites=true&w=majority
~~~

Các ký tự đặc biệt trong username/password cần được **percent-encode** theo quy tắc URI. Nên để driver và Atlas cung cấp/đọc cấu hình kết nối chuẩn; không tự đoán hostname, cổng hoặc tham số TLS.

### 7.1. Hiểu mô hình trách nhiệm chia sẻ

| Atlas quản lý phần lớn | Nhóm ứng dụng vẫn sở hữu |
|---|---|
| Hạ tầng MongoDB do dịch vụ cung cấp | Thiết kế document, index, truy vấn và data lifecycle |
| Provisioning và nhiều thao tác bảo trì cluster | Chọn tier, region, topology và khả năng đáp ứng tải |
| Cơ chế TLS/lưu trữ mã hóa và nhiều tính năng nền tảng | Database users, role, IP allowlist, mạng riêng, secret rotation |
| Công cụ backup, metric và alerts theo tier | Chính sách retention, kiểm thử restore, cảnh báo cần theo dõi |
| Các cơ chế hỗ trợ failover theo loại cluster | Retry, timeout, connection pool, idempotency ở ứng dụng |
| Nền tảng tính phí và các công cụ quan sát mức sử dụng | Ngân sách, giới hạn chi tiêu, tối ưu query và dung lượng |

Một cluster được tạo thành công mới chỉ là bước đầu của hệ thống an toàn và tin cậy.

### 7.2. Khi nào Free/Flex không đủ?

Cần xem xét Dedicated nếu yêu cầu tài nguyên ổn định hơn, sharding, multi-region, network peering/private endpoint, lựa chọn backup nâng cao hoặc monitoring sâu. Không suy đoán rằng mọi tính năng Atlas đều có trên Free/Flex; đối chiếu bảng giới hạn hiện hành.

**Không dùng benchmark trên Free** để dự báo hiệu năng production. Cơ chế shared infrastructure và throttle có thể che lấp hoặc làm sai lệch đặc tính thực tế.

## 8. Thực hành C — Phác thảo một cụm Enterprise self-managed

Giả sử doanh nghiệp có hệ thống thanh toán nội bộ, yêu cầu dữ liệu ở data center, log audit và hỗ trợ thương mại. Enterprise là ứng viên phù hợp; triển khai thực tế cần thiết kế và phê duyệt riêng.

Một bản thiết kế tối thiểu cho production có thể gồm:

1. **Ba node replica set** trên các máy/vùng lỗi độc lập để chịu được sự cố node và duy trì cơ chế bầu primary, với cấu hình voting phù hợp.
2. **TLS cho mọi kết nối**, network segmentation, firewall chỉ cho phép client/replica set cần thiết và cơ chế xác thực đúng chính sách.
3. **Ứng dụng dùng user có quyền tối thiểu**, tách tài khoản quản trị, audit các sự kiện bắt buộc và định nghĩa nơi lưu/giữ log.
4. **Mã hóa dữ liệu lưu trữ và quản lý khóa**, kiểm tra chức năng Enterprise cần dùng theo phiên bản/hợp đồng.
5. **Backup định kỳ có tính nhất quán**, bản sao lưu cách ly và quy trình thử restore có đo thời gian.
6. **Monitoring và alert** cho replication lag, disk, IOPS, bộ nhớ, kết nối, slow query, lỗi xác thực, thời gian backup và năng lực dự phòng.
7. **Runbook** cho failover, restore, rotation credential, nâng cấp rolling, rollback theo điều kiện được hỗ trợ và diễn tập sự cố.
8. **Kiểm tra license, support contract và sự tương thích** của công cụ quản lý, OS, MongoDB Server và driver.

Những yêu cầu này cũng là cơ sở đánh giá liệu tổ chức có đủ nguồn lực chạy Community production hay không. **Enterprise bổ sung công cụ và cam kết hỗ trợ**, nhưng không thay thế kiến trúc, quy trình hay trách nhiệm vận hành.

## 9. Các tình huống chọn lựa thực tế

### Tình huống 1 — Sinh viên học truy vấn và index

**Điều kiện:** laptop 16 GB RAM, học CRUD, aggregation, index; có thể mất Internet.

**Chọn:** Community local. Chạy Docker với dữ liệu giả lập; dùng MongoDB Compass hoặc mongosh. Chỉ cần Atlas khi bài học chuyển sang kết nối cloud.

**Lý do:** điều quan trọng là thực hành nhanh và tái lập môi trường, không phải SLA hay audit thương mại.

### Tình huống 2 — Nhóm Java xây dựng API, chạy CI liên tục

**Điều kiện:** nhiều pipeline chạy độc lập, mỗi test cần database sạch; đôi khi dùng transaction.

**Chọn:** Community container cho test tự động, cấu hình replica set khi test cần. Môi trường integration cloud riêng có thể dùng Atlas nếu kiểm thử cần đường truyền Atlas.

**Lý do:** cô lập, kiểm soát phiên bản, khả năng dựng/xóa tự động và tránh phụ thuộc cluster chung.

### Tình huống 3 — Startup triển khai API trên AWS, không có DBA riêng

**Điều kiện:** chấp nhận dữ liệu trên cloud, muốn high availability và backup, lưu lượng tăng dần.

**Chọn:** đánh giá Atlas Dedicated với region, tier, backup, monitoring và hỗ trợ phù hợp. Giai đoạn thử nghiệm có thể dùng Free/Flex theo giới hạn.

**Lý do:** giảm nhiều công việc vận hành infrastructure để tập trung vào phần mềm, đồng thời vẫn phải quản trị truy vấn, phân quyền và ngân sách.

### Tình huống 4 — Ngân hàng cần audit và dữ liệu phải nằm trong data center

**Điều kiện:** không được dùng database managed public cloud; có đội hạ tầng và hợp đồng hỗ trợ.

**Chọn:** Enterprise Advanced self-managed, sau khi kiểm tra khả năng audit, mã hóa, xác thực và các yêu cầu của đơn vị kiểm toán.

**Lý do:** đáp ứng vị trí triển khai và kiểm soát hạ tầng, dùng tính năng doanh nghiệp/hỗ trợ thương mại.

### Tình huống 5 — Công ty đã có đội SRE và hạ tầng Kubernetes

**Điều kiện:** có tiêu chuẩn internal platform, khả năng backup/monitoring, không yêu cầu Enterprise-only.

**Chọn:** Community hoặc Enterprise tự quản lý là những phương án khả thi; cần so chi phí vận hành, license và yêu cầu compliance với Atlas.

**Lý do:** năng lực tổ chức có thể làm thay đổi bài toán chi phí, nhưng không tự động chứng minh self-managed rẻ hơn.

### Tình huống 6 — Bài demo chạy một ngày cho khách hàng

**Điều kiện:** dữ liệu mẫu, ít người dùng, ưu tiên thiết lập nhanh.

**Chọn:** Atlas Free nếu cần chia sẻ kết nối cloud và mức tải nằm trong giới hạn; Community local nếu demo tại máy riêng.

**Lý do:** phù hợp mục tiêu ngắn hạn. Sau demo phải thu hồi user, secret và cluster/volume không còn cần.

## 10. Những nhầm lẫn thường gặp

**“Community không có bảo mật.”** Sai. Community hỗ trợ authentication, role-based access control và TLS; nhiều kiểm soát phụ thuộc cấu hình triển khai. Enterprise bổ sung các khả năng chuyên biệt như auditing, một số cơ chế xác thực và mã hóa ở cấp server.

**“Community không thể chạy production.”** Không chính xác. Có thể vận hành Community production, nhưng phải tự đáp ứng mọi yêu cầu về hạ tầng, bảo mật, độ sẵn sàng, backup, tuân thủ và hỗ trợ. Việc khả thi về kỹ thuật không đồng nghĩa phù hợp với ràng buộc của doanh nghiệp.

**“Enterprise tức là cloud managed.”** Sai. Enterprise Server thông thường vẫn chạy trên hạ tầng do khách hàng quản lý. Enterprise Advanced bổ sung license/công cụ/hỗ trợ, không tự chuyển trách nhiệm vận hành sang nhà cung cấp.

**“Atlas miễn phí hoàn toàn.”** Sai. Chỉ những tier và giới hạn nhất định là miễn phí. Flex, Dedicated, backup nâng cao, mạng và dịch vụ bổ sung có thể phát sinh chi phí theo cấu hình/mức sử dụng.

**“Dùng Atlas thì không cần backup.”** Sai. Dù Atlas cung cấp các tính năng backup, nhóm vẫn phải chọn chính sách phù hợp, xác minh tính năng của tier, thực hành khôi phục và kiểm tra RPO/RTO.

**“Chỉ cần dữ liệu giống nhau là staging tương đương production.”** Sai. Version, topology, giới hạn tier, index, volume, mạng, latency, auth, read/write concern và failover đều có thể làm hành vi khác nhau.

**“Mọi URI MongoDB đều giống nhau.”** Sai. URI local thường dùng địa chỉ localhost và cổng; Atlas thường dùng DNS SRV với tham số kết nối do hệ thống cung cấp. Ngoài URI còn phải xét TLS, DNS, firewall, user role và database authentication.

**“Cứ chọn tier nhỏ nhất rồi tăng khi chậm.”** Không đủ. Cần kiểm tra khả năng scale, yêu cầu high availability, backup và network ngay từ đầu; một số tính năng không có ở tier thấp dù tải hiện tại nhỏ.

**“Chi phí Community bằng 0.”** Sai nếu xét tổng chi phí. Máy chủ, điện toán, lưu trữ, nhân sự, downtime, backup và hỗ trợ đều có chi phí.

## 11. Từ môi trường thực hành đến production: kế hoạch chuyển đổi

Không có quy tắc bắt buộc rằng ứng dụng phải đi qua Community → Enterprise → Atlas. Ba lựa chọn không phải một chuỗi level. Một nhóm có thể học local trên Community rồi triển khai thẳng Atlas; nhóm khác có thể chạy Enterprise on-premises từ đầu.

Khi chuyển đổi môi trường, nên thực hiện:

1. **Kiểm tra tương thích:** phiên bản server/driver, tính năng BSON, index, authentication, transaction/change stream, read/write concern.
2. **Xác định cách sao chép dữ liệu:** công cụ migration do MongoDB hỗ trợ, dump/restore cho dữ liệu phù hợp, hoặc phương án đồng bộ liên tục nếu không được dừng dịch vụ.
3. **Định nghĩa thời điểm nhất quán:** nguồn có còn nhận ghi trong lúc copy không? Làm sao tránh mất hoặc ghi trùng dữ liệu?
4. **Chuẩn bị quyền và mạng:** tạo database user, role tối thiểu, xác nhận TLS, firewall/private connectivity, tách secret theo môi trường.
5. **Chạy smoke test và đo hiệu năng:** kiểm tra truy vấn/index, consistency, latencies, ứng dụng sau chuyển đổi.
6. **Lập kế hoạch cutover/rollback:** thời điểm chuyển URI, thời gian ngừng ghi nếu cần, điều kiện trở về môi trường cũ và phương án khôi phục dữ liệu.
7. **Thử backup/restore ở môi trường đích** trước khi nhận lưu lượng thật.

Nếu nâng **Community lên Enterprise** trên hạ tầng tự quản lý, làm theo quy trình upgrade chính thức cho loại deployment tương ứng (standalone, replica set hoặc sharded cluster), đồng thời phân biệt **đổi edition** với **nâng phiên bản MongoDB**. Nếu chuyển lên **Atlas**, cần đánh giá công cụ di chuyển, downtime, vùng dữ liệu và kiểm soát mạng.

## 12. Bài tập tình huống và câu hỏi tự đánh giá

### Bài tập A — Lập bảng quyết định

Với mỗi yêu cầu sau, hãy điền ba cột: **lựa chọn đề xuất**, **lý do**, **điều phải xác minh trước khi triển khai**.

| Yêu cầu | Hướng lựa chọn tham khảo | Điều phải xác minh |
|---|---|---|
| Một người học CRUD offline | Community local | Máy đủ tài nguyên, Docker/OS và phiên bản |
| CI chạy hàng trăm integration tests | Community container tạm | Readiness, dữ liệu độc lập, replica set khi cần |
| Nhóm nhỏ cần database cloud chia sẻ | Atlas Flex/Dedicated tùy nhu cầu | Giới hạn tier, region, backup, IP/private networking |
| Hệ thống public cloud có SLA cao | Atlas Dedicated hoặc self-managed được thiết kế kỹ | Availability, vùng lỗi, restore, ngân sách, support |
| On-premises bắt buộc audit chuyên biệt | Enterprise self-managed | Edition/version/license, audit retention, tích hợp danh tính |
| Production on-prem, đội vận hành mạnh, tính năng cơ bản đủ | Community hoặc Enterprise sau đánh giá | Chính sách sử dụng, support, chi phí hạ tầng và phục hồi |

### Bài tập B — Phân tích trade-off

Một ứng dụng Java có 50.000 người dùng, chạy trên public cloud, dữ liệu phải ở một region được phép, đội phát triển chỉ có hai kỹ sư và yêu cầu phục hồi trong 60 phút.

Hãy viết một đề xuất gồm:

1. Lựa chọn MongoDB ban đầu và ít nhất một phương án thay thế.
2. Topology/tier dự kiến và cách xác minh đạt yêu cầu khôi phục.
3. Mô hình xác thực, secret, network và quyền database.
4. Danh sách metric/alert cần theo dõi.
5. Các thành phần làm thay đổi chi phí khi dữ liệu tăng gấp 10 lần.

**Gợi ý:** Atlas Dedicated có thể giảm công vận hành; không được kết luận tier hoặc SLA cụ thể chỉ từ số người dùng. Cần đo workload thực tế, tập trung vào RPO/RTO, query profile và hạn mức cluster.

### Câu hỏi ôn tập

1. Vì sao Community và Enterprise là hai edition, còn Atlas là một mô hình dịch vụ?
2. Tại sao môi trường CI thường phù hợp với Community container hơn database cloud dùng chung?
3. Một nhóm cần audit doanh nghiệp và hệ thống air-gapped nên ưu tiên hướng nào? Vì sao?
4. Sử dụng Atlas có làm ứng dụng hết trách nhiệm với index, user role và backup restore không?
5. Những mục nào phải có khi so tổng chi phí Community tự quản lý với Atlas?
6. Khi production dùng replica set, vì sao standalone local có thể khiến integration test bỏ sót lỗi?
7. Vì sao không nên dùng Atlas Free làm cơ sở tính năng lực xử lý của Dedicated production?

## 13. Kết luận chọn môi trường

- **Học tập, local development, CI:** bắt đầu với **Community** để có môi trường chủ động, tái lập và dễ cô lập. Thêm replica set khi chức năng cần.
- **Development hoặc thử nghiệm cloud nhanh:** dùng **Atlas Free/Flex** nếu giới hạn đáp ứng; chuyển Dedicated khi cần tài nguyên và tính năng phù hợp.
- **Production trên public cloud:** đánh giá **Atlas Dedicated** khi ưu tiên vận hành managed, nhưng kiểm chứng topology, backup, network, RPO/RTO và chi phí.
- **Production tự quản lý có yêu cầu doanh nghiệp:** cân nhắc **Enterprise Advanced**, nhất là khi cần audit, tích hợp bảo mật, quản trị tập trung hoặc hỗ trợ thương mại.
- **Production tự quản lý với tính năng cơ bản:** **Community** vẫn có thể phù hợp nếu đội ngũ đáp ứng yêu cầu vận hành và sử dụng hợp pháp.

Quyết định tốt là quyết định **được chứng minh bằng yêu cầu và bài kiểm thử của chính môi trường**, không chỉ bằng tên sản phẩm hoặc bảng giá ban đầu.

## Tài liệu chính thức tham khảo

Các tài liệu dưới đây là điểm kiểm tra chi tiết về phiên bản, tính năng, license và giới hạn dịch vụ; cần xem lại khi chuẩn bị triển khai thực tế.

- [MongoDB — Choose Your Deployment Environment](https://www.mongodb.com/docs/deployment/)
- [MongoDB — Install Community and Enterprise Editions](https://www.mongodb.com/docs/manual/installation/)
- [MongoDB — Community Edition](https://www.mongodb.com/products/self-managed/community-edition)
- [MongoDB — Enterprise Advanced](https://www.mongodb.com/products/self-managed/enterprise-advanced)
- [MongoDB — Upgrade Community to Enterprise](https://www.mongodb.com/docs/rapid/administration/upgrade-community-to-enterprise/)
- [MongoDB — Atlas Cluster Types and Creation](https://www.mongodb.com/docs/atlas/create-database-deployment/)
- [MongoDB — Atlas Free, Flex, Dedicated Comparison](https://www.mongodb.com/docs/atlas/manage-clusters/)
- [MongoDB — Atlas Security Configuration](https://www.mongodb.com/docs/atlas/setup-cluster-security/)
- [MongoDB — Community Licensing](https://www.mongodb.com/legal/licensing/community-edition)
