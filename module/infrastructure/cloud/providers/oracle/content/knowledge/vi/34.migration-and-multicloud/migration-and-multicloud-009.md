# Các mô hình Oracle Database đa đám mây và tiêu chí lựa chọn

Trong chương **Di trú và đa đám mây** của module **CLOUD_PROVIDERS_ORACLE**, bài học này giải thích cách bố trí Oracle Database khi ứng dụng, dữ liệu hoặc hệ thống dự phòng nằm trên nhiều nền tảng cloud. Trọng tâm là lựa chọn kiến trúc phù hợp với Oracle Cloud Infrastructure (OCI), đồng thời xác định cách kết nối, phân quyền, giám sát, tự động hóa, duy trì tính sẵn sàng và kiểm soát chi phí.

Một doanh nghiệp có thể chạy ứng dụng trên Azure nhưng sử dụng database trên OCI; đặt dịch vụ Oracle Database ngay trong trung tâm dữ liệu AWS; hoặc duy trì database chính và bản sao ở hai cloud. Cả ba đều có yếu tố đa đám mây nhưng khác nhau về đường đi của giao dịch, trách nhiệm vận hành và khả năng phục hồi.

Sau bài học, người học có thể:

- Phân biệt mô hình kết nối xuyên cloud, dịch vụ Oracle Database@ và sao chép dữ liệu giữa các cloud.
- Chọn vị trí database theo đặc điểm giao dịch, tính năng bắt buộc và nơi ứng dụng đang hoạt động.
- Đánh giá độ trễ, RTO/RPO, IAM, an toàn dữ liệu, chi phí và khả năng vận hành.
- Lập phương án thử nghiệm cùng hồ sơ quyết định kiến trúc trước khi triển khai.

## 1. Phân loại theo ba câu hỏi độc lập

### 1.1. Database thực sự chạy ở đâu?

Cần tách vị trí vật lý của tầng dữ liệu khỏi nơi mua dịch vụ hoặc giao diện quản trị.

- **Database trong một OCI region:** ứng dụng tại cloud khác phải truy cập qua đường kết nối giữa hai môi trường.
- **Dịch vụ Oracle Database@ tại cloud đối tác:** hạ tầng database của dịch vụ được triển khai tại trung tâm dữ liệu đối tác; ứng dụng kết nối qua cơ chế mạng tích hợp tương ứng.
- **Oracle Database trên máy ảo hoặc dịch vụ được quản lý của cloud khác:** mức độ tương thích và trách nhiệm quản trị tùy sản phẩm cụ thể.

Trong tài liệu hiện hành, Oracle sử dụng các tên Oracle AI Database@Azure, Oracle AI Database@Google Cloud và Oracle AI Database@AWS. Bài học dùng cách gọi ngắn **Database@Azure**, **Database@Google Cloud**, **Database@AWS** khi không cần phân biệt nhãn sản phẩm. Các nền tảng đối tác này được trình bày trong [hướng dẫn triển khai dịch vụ database đa đám mây của Oracle](https://docs.oracle.com/en/solutions/oci-best-practices/deploy-multicloud-oci-oracle-database-services1.html).

### 1.2. Ai quản lý từng thành phần?

Một hệ thống có thể bao gồm đồng thời:

- Nhà cung cấp vận hành phần cứng và lớp dịch vụ nền.
- Đội cloud quản lý tenancy, compartment, subscription, project, tài khoản, mạng và quyền tạo tài nguyên.
- DBA quản lý database, tài khoản dữ liệu, schema và những tác vụ mà dịch vụ giao cho khách hàng.
- Đội ứng dụng quản lý connection pool, giao dịch, retry, timeout và quy tắc xử lý lỗi.

Mức tự động hóa càng cao thì phạm vi cấu hình khách hàng trực tiếp can thiệp thường càng hẹp. Vì vậy, yêu cầu như “phải có quyền truy cập hệ điều hành” cần được xem là điều kiện lựa chọn sản phẩm.

### 1.3. Dữ liệu được sử dụng theo kiểu nào?

Ba kiểu sử dụng phổ biến là:

1. **Một nguồn ghi chính:** ứng dụng từ một hoặc nhiều cloud truy cập cùng database chính.
2. **Một nguồn ghi với bản sao:** bản sao dùng để khôi phục hoặc phục vụ những luồng đọc được phép chấp nhận dữ liệu trễ.
3. **Nhiều nguồn ghi:** từng database có thể nhận ghi theo quy tắc sở hữu dữ liệu và cơ chế xử lý xung đột đã thiết kế.

Vị trí database, mức quản lý và topology sao chép là ba trục có thể kết hợp. Ví dụ, một Database@ có thể là database chính trong cấu hình dự phòng được hỗ trợ. Tuy nhiên, lựa chọn Database@ riêng lẻ chưa xác định topology DR.

| Mô hình | Bố trí điển hình | Động lực lựa chọn | Câu hỏi cần trả lời |
| --- | --- | --- | --- |
| Ứng dụng cloud khác, database trên OCI | Azure/AWS/Google Cloud → kết nối riêng → OCI | Giữ dịch vụ dữ liệu trên OCI | Độ trễ và độ ổn định đường truyền có đáp ứng giao dịch không? |
| Database@ | Ứng dụng và tầng dữ liệu đặt gần nhau tại cloud đối tác | Giảm khoảng cách ứng dụng–database, giữ năng lực Oracle phù hợp | Region, dịch vụ và tính năng bắt buộc có sẵn không? |
| Oracle Database tự quản trên IaaS | Máy ảo, storage và mạng của cloud được chọn | Cần quyền điều khiển sâu | Đội nội bộ có vận hành và khôi phục được toàn bộ stack không? |
| Dịch vụ Oracle do cloud khác quản lý | Chẳng hạn Amazon RDS for Oracle | Giảm công việc quản trị nền tảng | Có giới hạn tính năng hoặc quyền quản trị nào ảnh hưởng ứng dụng không? |
| Sao chép một chiều | Database chính → standby hoặc đích CDC | DR, di trú, phân tích dữ liệu | Bản sao được bảo vệ và sử dụng theo cam kết nào? |
| Sao chép hai chiều hoặc phân vùng dữ liệu | Nhiều database độc lập | Phục vụ ghi ở nhiều vị trí | Ai sở hữu từng dữ liệu và giải quyết bất đồng ra sao? |

## 2. Mô hình ứng dụng tại cloud khác, database trên OCI

### 2.1. Kiến trúc và đường đi của giao dịch

Ở mô hình thường gọi là **split-stack**, tầng ứng dụng nằm tại một cloud, còn Oracle Database nằm trong OCI. Mọi thao tác SQL từ ứng dụng tới database phụ thuộc vào đường truyền giữa hai môi trường.

~~~mermaid
flowchart LR
    subgraph Partner["Cloud đặt ứng dụng"]
        APP["Ứng dụng / connection pool"]
        NET["Mạng ứng dụng"]
        APP --> NET
    end
    LINK["Kết nối riêng hoặc VPN"]
    subgraph OCI["Oracle Cloud Infrastructure"]
        DRG["DRG / định tuyến"]
        VCN["VCN / subnet database"]
        DB["Oracle Database"]
        DRG --> VCN --> DB
    end
    NET --> LINK --> DRG
~~~

Đây là sơ đồ khái niệm cho database dùng private endpoint trong VCN. Các cơ chế endpoint và mạng phải điều chỉnh theo dịch vụ thực tế.

Với Azure, Oracle Interconnect kết hợp **OCI FastConnect** và **Azure ExpressRoute** tại các vị trí hỗ trợ. Kết nối cần được cấu hình ở cả hai phía. Xem [Oracle Interconnect for Azure](https://docs.oracle.com/en-us/iaas/Content/multicloud/interconnect-azure.htm).

Với Google Cloud, Oracle Interconnect sử dụng **OCI FastConnect** và **Google Cloud Partner Interconnect** tại các cặp region được hỗ trợ. Xem [Oracle Interconnect for Google Cloud](https://docs.oracle.com/en-us/iaas/Content/multicloud/interconnect-gcp.htm).

Đối với AWS hoặc những vị trí khác, phải khảo sát phương án interconnect hiện có, kết nối qua đối tác hoặc VPN phù hợp. Không suy ra khả năng kết nối từ tên region. [Danh mục Multicloud Interconnect của Oracle](https://docs.oracle.com/en-us/iaas/Content/multicloud/interconnect.htm) là điểm bắt đầu để kiểm tra phương án được hỗ trợ.

### 2.2. Khi nào mô hình này có lợi?

Mô hình đáng xem xét khi doanh nghiệp đã có nền tảng database trên OCI, muốn giữ quy trình DBA và giám sát đang dùng, đồng thời ứng dụng cần tiếp tục sử dụng dịch vụ của cloud khác.

Những workload trao đổi ít lượt, gửi yêu cầu theo lô hoặc xử lý phần lớn công việc trong database thường dễ bố trí hơn workload có nhiều truy vấn nhỏ phụ thuộc tuần tự.

Ví dụ, một tác vụ gửi tập lệnh tổng hợp dữ liệu rồi nhận một kết quả có đặc điểm khác với màn hình thực hiện hàng chục lần truy vấn để dựng danh sách. Cùng số byte truyền qua mạng nhưng số lượt chờ và tác động đến người dùng khác nhau.

### 2.3. Đánh giá độ trễ bằng số lượt trao đổi

Một phép ước lượng ban đầu:

~~~text
Thời gian yêu cầu ≈
  thời gian xử lý ứng dụng
  + thời gian xử lý database
  + số lượt trao đổi mạng tuần tự × RTT
  + thời gian chờ hàng đợi và truyền dữ liệu
~~~

Giả sử một thao tác thực hiện 18 lượt trao đổi tuần tự:

- RTT ứng dụng–database là 2 ms: thành phần chờ theo công thức khoảng 36 ms.
- RTT tăng lên 9 ms: thành phần này khoảng 162 ms.
- Chênh lệch khoảng 126 ms xuất hiện trước khi xét việc tăng tải hoặc retry.

Đây là **ví dụ tính toán**, không phải số đo của dịch vụ Oracle hoặc cam kết hiệu năng. Việc gom lệnh, fetch nhiều dòng mỗi lượt và xử lý song song có thể làm thay đổi số lượt hiệu dụng. Phải đo lại với ứng dụng thực, đặc biệt ở p95 và p99.

### 2.4. Những phần phải thiết kế đồng thời

| Thành phần | Việc cần làm | Lỗi có thể gặp nếu bỏ sót |
| --- | --- | --- |
| Địa chỉ mạng | Lập kế hoạch CIDR không chồng lấn cho các mạng được kết nối | Định tuyến nhầm hoặc phải bổ sung NAT phức tạp |
| Route hai chiều | Kiểm tra đường đi, đường về và quảng bá route | Kết nối chỉ hoạt động một chiều |
| DNS riêng | Bảo đảm máy ứng dụng phân giải đúng tên endpoint | TCP theo IP thành công nhưng ứng dụng không kết nối được |
| Kiểm soát truy cập mạng | Giới hạn nguồn ứng dụng và cổng thực tế của listener | Mở quá rộng hoặc chặn nhầm lưu lượng hợp lệ |
| Mã hóa trên đường truyền | Kiểm tra cấu hình mã hóa, chứng thư và xác minh danh tính | Có mạng riêng nhưng chưa đáp ứng yêu cầu bảo vệ dữ liệu |
| Dự phòng kết nối | Kiểm tra circuit, thiết bị, tuyến và điểm kết cuối độc lập | Hai kết nối cùng hỏng do chung một thành phần |
| Connection pool | Đặt timeout, kiểm tra kết nối hỏng và chính sách retry | Luồng ứng dụng bị giữ lâu khi mạng gián đoạn |
| Quan sát hệ thống | Thu thập RTT, packet loss, DNS, pool wait và database wait | Khó phân biệt sự cố mạng với sự cố SQL |

Kết nối riêng giải quyết đường truyền và khả năng cô lập. Cần kiểm tra riêng việc mã hóa và xác thực theo yêu cầu của tổ chức.

## 3. Mô hình Oracle Database@ tại cloud đối tác

### 3.1. Bản chất của mô hình

Database@ đưa tầng dữ liệu của dịch vụ Oracle tới gần ứng dụng đang chạy tại cloud đối tác. Vị trí hạ tầng phục vụ truy vấn và vị trí các thành phần điều khiển có thể khác nhau.

Đối với Database@Azure, Oracle mô tả hạ tầng tại trung tâm dữ liệu Azure là **child site**, gắn với **parent site** OCI. Hạ tầng Oracle được vận hành bởi nhân sự OCI. Vì vậy, việc xác định vị trí database phải xét kiến trúc dịch vụ, không chỉ nhìn tên cloud trên hóa đơn. Xem [kiến trúc Oracle AI Database@Azure](https://docs.oracle.com/en-us/iaas/Content/database-at-azure/getting-started-architecture.htm).

~~~mermaid
flowchart TB
    subgraph DC["Trung tâm dữ liệu cloud đối tác"]
        APP["Ứng dụng"]
        INTEGRATION["Cơ chế mạng tích hợp"]
        DB["Tầng dữ liệu Oracle Database@"]
        APP --> INTEGRATION --> DB
    end
    CONTROL["Mặt phẳng điều khiển và dịch vụ quản lý"]
    CONTROL -. "Quản lý theo kiến trúc dịch vụ" .-> DB
~~~

Mũi tên nét đứt biểu diễn quản lý, không có nghĩa mọi câu SQL phải đi qua parent region. Khi thiết kế, cần vẽ riêng đường dữ liệu, đường quản trị, đường sao lưu và đường sao chép.

### 3.2. Ba dịch vụ có cơ chế tích hợp khác nhau

| Dịch vụ | Một điểm tích hợp cần biết | Hệ quả khi lập thiết kế |
| --- | --- | --- |
| Database@Azure | Kết nối với mạng ứng dụng qua delegated subnet theo mô hình dịch vụ | Cần phối hợp kế hoạch VNet, subnet, quyền ủy quyền và tài nguyên OCI liên quan |
| Database@Google Cloud | Sử dụng Oracle Database network, thường gọi ODB network, để kết nối với VPC ứng dụng | Cần kiểm tra mạng dịch vụ, kết nối VPC và phạm vi project/tenancy |
| Database@AWS | Sử dụng ODB network và ODB peering để kết nối với VPC ứng dụng | Cần cấu hình route, DNS và quyền quản lý đúng theo tài liệu AWS |

Các cơ chế được trình bày trong [tổng quan Database@Azure](https://docs.oracle.com/en-us/iaas/Content/database-at-azure/overview.htm), [tổng quan Database@Google Cloud](https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/overview.htm) và [hướng dẫn ODB peering của AWS](https://docs.aws.amazon.com/odb/latest/UserGuide/configuring.html).

ODB peering là tài nguyên kết nối với ODB network, có khác biệt so với VPC peering thông thường. Khi thiết kế nhiều VPC, cần dùng đúng mô hình được dịch vụ hỗ trợ; không giả định peering có tính bắc cầu. Xem [cách Oracle Database@AWS hoạt động](https://docs.aws.amazon.com/odb/latest/UserGuide/how-it-works.html).

### 3.3. Những gì cần kiểm tra trước khi lựa chọn

Tên Database@ chưa đủ để xác định một cấu hình có triển khai được hay không. Hồ sơ khảo sát cần nêu rõ:

1. Cloud và region của ứng dụng.
2. Region, zone, năng lực cung cấp và quota cho dịch vụ database.
3. Loại dịch vụ cần dùng: Exadata Database Service, Autonomous Database hoặc loại khác trong danh mục thực tế.
4. Phiên bản, edition, tính năng, giới hạn quản trị và mô hình tính tài nguyên.
5. Phạm vi backup, phục hồi, HA/DR và topology được hỗ trợ.
6. Cách liên kết tài khoản đối tác với OCI tenancy, đồng bộ quyền và theo dõi chi phí.

Danh mục và hỗ trợ không nên được giả định giống nhau giữa Azure, Google Cloud, AWS hoặc giữa các region. Với Database@AWS, quy trình ban đầu có bước liên kết AWS account và OCI tenancy theo [tổng quan dịch vụ của Oracle](https://docs.oracle.com/en-us/iaas/Content/database-at-aws/oaaws-overview.htm).

### 3.4. Ưu điểm và giới hạn thực tế

Về kiến trúc, đặt ứng dụng và tầng dữ liệu gần nhau có thể giảm phần chờ do truyền thông. Đây là lý do đáng thử nghiệm với ứng dụng nhạy độ trễ hoặc khó giảm số lượt gọi database.

Tuy vậy, vẫn phải đo với vị trí đặt ứng dụng cụ thể. Một ứng dụng ở sai zone, đi qua thành phần trung gian hoặc dùng endpoint không phù hợp có thể không nhận được kết quả như mong muốn.

Database@ cũng không tự di chuyển schema, dữ liệu, tài khoản hay cấu hình ứng dụng từ hệ thống cũ. Nhóm dự án vẫn cần phương án di trú, đối soát và chuyển kết nối. Việc tài nguyên xuất hiện trong cổng quản trị đối tác cũng không thay thế việc phân quyền database và quản trị OCI liên quan.

## 4. Oracle Database trên hạ tầng hoặc dịch vụ của cloud khác

### 4.1. Tự quản trên IaaS

Doanh nghiệp triển khai Oracle Database trên máy ảo, sử dụng mạng và storage của nhà cung cấp đã chọn. Đội vận hành thường phải lo nhiều phần hơn:

- Hệ điều hành, bản vá, cài đặt database và cấu hình listener.
- Dung lượng, hiệu năng I/O, backup, phục hồi và kiểm tra tính toàn vẹn.
- Bảo mật, tài khoản quản trị, giám sát và lịch bảo trì.
- Cơ chế HA/DR, tự động hóa và trực xử lý sự cố.

Mô hình này phù hợp để đánh giá khi workload cần mức kiểm soát mà dịch vụ được quản lý không cung cấp. Điều kiện tiên quyết là nền tảng, hệ điều hành, loại máy và cấu hình database đáp ứng yêu cầu hỗ trợ của Oracle cùng nhà cung cấp.

Đừng suy ra khả năng RAC hoặc hỗ trợ database chỉ từ việc máy ảo có đủ CPU và RAM. Các yêu cầu về storage, mạng cụm và chứng nhận cần được kiểm tra riêng.

### 4.2. Dịch vụ được cloud khác quản lý

Một ví dụ là **Amazon RDS for Oracle**. Dịch vụ giảm một phần công việc quản trị nhưng có giới hạn về quyền và tính năng. Chẳng hạn tài khoản quản trị trong RDS thông thường không được coi tương đương quyền SYSDBA đầy đủ. Xem [tài liệu Amazon RDS for Oracle](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Oracle.html).

RDS for Oracle thông thường không hỗ trợ Oracle RAC. Do đó, workload có yêu cầu RAC bắt buộc phải qua bước sàng lọc tính năng trước khi so sánh giá. Xem [danh mục tính năng RDS for Oracle](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Oracle.Concepts.FeatureSupport.html).

Cần phân biệt rõ Database@AWS với RDS for Oracle: chúng có kiến trúc dịch vụ, năng lực và phạm vi vận hành khác nhau. Không chuyển kết luận về sản phẩm này sang sản phẩm kia.

### 4.3. Đánh giá quyền sử dụng phần mềm và chi phí

Trước khi đưa chi phí vào bảng lựa chọn, cần xác nhận các dữ kiện áp dụng cho hợp đồng và cấu hình thực tế:

- Mô hình license đi kèm dịch vụ hay BYOL.
- Edition, option và management pack mà workload thực sự sử dụng.
- Phạm vi quyền sử dụng cho môi trường chính, dự phòng, kiểm thử và giai đoạn chạy song song.
- Cách tính tài nguyên và điều kiện hỗ trợ của dịch vụ được chọn.

Không lấy số vCPU của một nhà cung cấp rồi mặc định tương đương đơn vị tính của dịch vụ khác. Trong bài toán kiến trúc, dùng bảng tài nguyên đã quy đổi theo hồ sơ thương mại được xác nhận thay vì tự suy diễn quy tắc license.

## 5. Sao chép Oracle Database giữa các cloud

Đây là một lớp thiết kế dữ liệu có thể bổ sung cho các mô hình vị trí ở trên. Phải xác định mục đích trước: bảo vệ toàn database, cấp dữ liệu phân tích, di trú hay cho phép ghi ở nhiều nơi.

### 5.1. Một nguồn ghi với Oracle Data Guard

Data Guard duy trì database standby bằng việc vận chuyển và áp dụng redo. Với physical standby, database chính là nơi nhận ghi ứng dụng thông thường; standby có vai trò bảo vệ dữ liệu và có thể đảm nhiệm những tác vụ đọc phù hợp với cấu hình, tính năng và quyền sử dụng được cấp. Xem [giới thiệu Oracle Data Guard](https://docs.oracle.com/en/database/oracle/oracle-database/26/sbydb/introduction-to-oracle-data-guard-concepts.html).

~~~text
Ứng dụng ghi
     |
     v
Primary ở địa điểm A -- redo --> Standby ở địa điểm B
                                 |
                                 +-- Chuyển vai trò khi đủ điều kiện
~~~

Hai quyết định cần phân biệt:

- **Chế độ vận chuyển redo:** đồng bộ hay bất đồng bộ.
- **Chế độ bảo vệ:** yêu cầu về độ bền dữ liệu và hành vi khi mất liên lạc.

Vận chuyển đồng bộ đưa xác nhận từ phía standby vào đường commit theo cấu hình; RTT và I/O từ xa vì vậy ảnh hưởng độ trễ giao dịch. Bất đồng bộ cho phép commit không chờ xác nhận từ xa nhưng có nguy cơ thiếu redo tại nơi dự phòng khi gặp sự cố. Tham khảo [các chế độ bảo vệ Data Guard](https://docs.oracle.com/en/database/oracle/oracle-database/26/sbydb/oracle-data-guard-protection-modes.html).

Không hứa RPO bằng 0 chỉ từ chữ “SYNC”. Phải xác định chế độ bảo vệ, trạng thái đồng bộ, độ bền của xác nhận và kịch bản mất kết nối. Các tùy chọn như SYNC, FASTSYNC và ASYNC có yêu cầu khác nhau trong [tài liệu quản lý chế độ bảo vệ](https://docs.oracle.com/en/database/oracle/oracle-database/26/dgbkr/managing-data-protection-modes.html).

Việc xây dựng Data Guard qua ranh giới cloud còn phụ thuộc phiên bản, loại dịch vụ, giới hạn tự động hóa và topology được hỗ trợ. Cần đối chiếu [MAA Multicloud Certification Matrix](https://docs.oracle.com/en/database/oracle/oracle-database/19/haovw/multilcoud-certification-matrix.html) cho cấu hình cụ thể; không mặc định mọi cặp database đều có thể cấu hình bằng cùng một quy trình.

### 5.2. Sao chép logic và CDC với Oracle GoldenGate

GoldenGate thích hợp để đánh giá khi cần cấp thay đổi dữ liệu sang hệ thống khác, đồng bộ một phần dữ liệu hoặc hỗ trợ di trú với thời gian gián đoạn thấp. Khả năng nguồn, đích, kiểu dữ liệu và thao tác được sao chép phải được đối chiếu theo phiên bản.

Data Guard và GoldenGate có thể bổ trợ nhau: một cơ chế bảo vệ database trong khi cơ chế kia phục vụ phân phối dữ liệu hoặc chuyển đổi hệ thống. Oracle trình bày cách kết hợp trong [thực hành Data Guard và GoldenGate](https://docs.oracle.com/en/database/oracle/oracle-database/26/haovw/best-practice-oracle-active-data-guard-and-oracle-goldengate.html).

~~~text
Oracle Database giao dịch
         |
         +-- GoldenGate / CDC --> Dữ liệu phục vụ phân tích ở cloud khác
         |
         +-- Cơ chế HA/DR riêng theo mục tiêu bảo vệ database
~~~

Một pipeline CDC chạy tốt chưa chứng minh có thể khôi phục toàn bộ hệ thống. Cần kiểm tra cả đối tượng ngoài phạm vi sao chép, cấu hình bảo mật, job, kết nối tích hợp và quy trình mở lại ứng dụng.

### 5.3. Nhiều nguồn ghi và active-active

GoldenGate có thể hỗ trợ topology hai chiều nhưng là cơ chế sao chép bất đồng bộ. Hai database có thể đồng thời sửa cùng một dữ liệu trước khi nhận thay đổi của nhau. Cần cơ chế phát hiện và giải quyết xung đột để dữ liệu hội tụ. Xem [so sánh active-active và active-passive](https://docs.oracle.com/en/database/goldengate/core/26/ggsol/active-active-vs-active-passive.html).

Ví dụ, hai cloud đều cho phép bán đơn vị hàng cuối cùng. Việc cả hai nơi cùng xác nhận đơn hàng có thể vi phạm quy tắc tồn kho trước khi hệ thống phát hiện xung đột. Lựa chọn “bản cập nhật sau cùng thắng” không giải quyết được cam kết giao hàng đã gửi cho hai khách.

Những quyết định cần có trước khi mở ghi hai phía:

- Chia quyền ghi theo vùng, chi nhánh, tenant hoặc khóa nghiệp vụ nếu có thể.
- Thiết kế khóa duy nhất và quy tắc sinh ID không va chạm.
- Xác định cách xử lý insert, update, delete và thay đổi schema.
- Ngăn dữ liệu sao chép quay vòng trở lại nguồn.
- Định nghĩa hành vi khi mất kết nối, tồn đọng và hòa giải dữ liệu.

Các yêu cầu phát hiện và giải quyết xung đột được Oracle trình bày trong [hướng dẫn GoldenGate active-active](https://docs.oracle.com/en/database/oracle/oracle-database/26/haovw/ogg-active-active-guidance-dev-and-admin1.html).

Nếu nhu cầu cốt lõi là phân chia dữ liệu theo khóa và xử lý gần nơi phát sinh, có thể khảo sát Oracle Globally Distributed Database thay cho cách tự ghép nhiều nguồn ghi cùng tập dữ liệu. Đây là thiết kế phân tán chuyên biệt, cần đánh giá khóa phân vùng, giao dịch liên vùng và yêu cầu ứng dụng; xem [tổng quan Globally Distributed Database](https://www.oracle.com/database/distributed-database/).

### 5.4. Chọn công cụ theo mục đích

| Mục đích | Hướng đánh giá trước | Điều không nên suy ra |
| --- | --- | --- |
| Bảo vệ database với một nguồn ghi | Data Guard và topology MAA được hỗ trợ | Có standby là chắc chắn đạt mọi RTO/RPO |
| Chuyển dữ liệu chọn lọc sang nền tảng phân tích | GoldenGate/CDC hoặc cơ chế tích hợp thích hợp | Đích phân tích luôn đọc được dữ liệu mới nhất ngay sau commit |
| Di trú ít gián đoạn | Initial load, đồng bộ thay đổi, đối soát và cutover | Bật sao chép là hoàn thành di trú |
| Cho phép ghi ở nhiều nơi | Quy tắc sở hữu dữ liệu, xung đột và khả năng ứng dụng | Sao chép hai chiều tạo ra một giao dịch ACID toàn cầu |
| Phân chia dữ liệu theo địa lý hoặc khóa | Kiến trúc phân vùng và định tuyến phù hợp | Mọi truy vấn đều được xử lý cục bộ |

## 6. Bộ tiêu chí lựa chọn

### 6.1. Tương thích và khả năng cung cấp

Đây là nhóm tiêu chí loại trừ. Một phương án rẻ hơn vẫn không phù hợp nếu thiếu tính năng bắt buộc.

Hãy lập danh sách yêu cầu ở mức có thể xác minh: phiên bản database, edition, RAC nếu cần, đặc điểm PL/SQL, kiểu dữ liệu, quyền quản trị, tích hợp ứng dụng đóng gói, công cụ backup và yêu cầu hỗ trợ.

Với từng yêu cầu, ghi bằng chứng từ tài liệu, kiểm tra kỹ thuật hoặc xác nhận dịch vụ. Trạng thái “chưa xác minh” cần được xử lý trước quyết định triển khai.

Region có tên trong danh mục chưa đủ. Cần kiểm tra loại dịch vụ tại region đó, quota, dung lượng tối thiểu, năng lực cấp phát và thời gian chuẩn bị hạ tầng.

### 6.2. Đặc điểm giao dịch và đường truyền

| Đặc điểm workload | Tác động đến lựa chọn |
| --- | --- |
| Nhiều lượt SQL tuần tự cho một request | Ưu tiên đánh giá vị trí ứng dụng và database gần nhau |
| Truy vấn trả tập dữ liệu lớn | Băng thông, thời gian truyền và lưu lượng phát sinh quan trọng |
| Batch xử lý theo cửa sổ | Có thể linh hoạt hơn về độ trễ từng truy vấn nhưng phải đáp ứng thời gian hoàn thành |
| Dịch vụ đọc sau ghi ngay lập tức | Cần tránh đưa luồng đọc sang bản sao bất đồng bộ khi chưa có cơ chế bảo đảm phù hợp |
| Giao dịch ghi liên tục | Cần đo redo phát sinh, khả năng vận chuyển và tốc độ áp dụng |
| Dữ liệu được sở hữu rõ theo vùng | Có thể đánh giá phân vùng hoặc topology nhiều nguồn ghi có kiểm soát |

Ngoài latency, hãy đo throughput và số kết nối đồng thời. Một phương án có RTT tốt vẫn có thể nghẽn ở connection pool, I/O, CPU, listener hoặc đường sao chép.

Băng thông dùng cho replication phải đáp ứng được các đợt phát sinh redo cao và có phần dư để giải phóng backlog sau gián đoạn. Lấy trung bình ngày làm chuẩn duy nhất dễ dẫn đến cấu hình không bắt kịp giờ cao điểm.

### 6.3. HA, DR và miền lỗi

**HA** xử lý sự cố trong phạm vi được thiết kế, chẳng hạn instance hoặc một thành phần hạ tầng. **DR** phục hồi dịch vụ khi mất một địa điểm hoặc miền lỗi lớn hơn.

Một hệ thống có tài nguyên ở hai cloud vẫn có thể chung:

- Một nhà cung cấp DNS hoặc identity.
- Một tuyến kết nối vật lý.
- Một vùng địa lý.
- Một hệ thống quản lý secret hoặc khóa mã hóa.
- Một quy trình phát hành gây lỗi đồng thời ở cả hai nơi.

Cần vẽ sơ đồ phụ thuộc và đối chiếu từng kịch bản mất thành phần. Không lấy logo hai nhà cung cấp làm bằng chứng rằng hai miền phục hồi độc lập.

Hai chỉ tiêu phải tách rõ:

- **RPO:** mức mất dữ liệu tối đa có thể chấp nhận theo mục tiêu khôi phục.
- **RTO:** thời gian mục tiêu để khôi phục dịch vụ tới mức sử dụng đã thống nhất.

Một mô hình phân rã để lập kế hoạch:

~~~text
RTO đầu cuối ≈
  phát hiện sự cố
  + quyết định chuyển đổi
  + khôi phục hoặc chuyển vai trò database
  + cập nhật định tuyến / endpoint
  + tái kết nối ứng dụng
  + kiểm tra nghiệp vụ tối thiểu
~~~

Database sẵn sàng sau vài phút chưa có nghĩa người dùng đã giao dịch được sau đúng thời gian đó.

Với standby bất đồng bộ, cần theo dõi **transport lag** và **apply lag** theo định nghĩa của công cụ. Redo đã đến nơi nhưng chưa áp dụng có thể kéo dài thời gian mở dịch vụ; redo chưa đến nơi có thể tạo khoảng mất dữ liệu khi nguồn bị mất. Không quy đổi một chỉ số lag thành RPO bảo đảm cho mọi kiểu sự cố.

Replication cũng có thể truyền thao tác xóa sai hoặc thay đổi dữ liệu không mong muốn. Cần có backup, retention, khả năng phục hồi theo thời điểm phù hợp và diễn tập khôi phục. Phải bảo đảm còn truy cập được cả bản sao lưu, khóa mã hóa và quyền cần thiết khi miền chính gặp sự cố.

### 6.4. Phân quyền và an toàn dữ liệu

Hệ thống đa đám mây có ít nhất ba lớp quyền:

| Lớp | Phạm vi quản lý | Ví dụ quyết định cần làm |
| --- | --- | --- |
| Cloud đối tác | Subscription/project/account, mạng và tài nguyên ứng dụng | Ai tạo kết nối tới mạng database? |
| OCI | Tenancy, compartment, policy và tài nguyên dịch vụ liên quan | Ai được quản lý database, mạng, backup và thông số dịch vụ? |
| Database | User, role và quyền trên schema, bảng, procedure | Ứng dụng được đọc/ghi dữ liệu nào? |

Đăng nhập được cổng quản trị cloud không đồng nghĩa có quyền truy vấn dữ liệu. Federation hoặc liên kết tài khoản cũng không tự tạo bộ quyền tối thiểu phù hợp.

Một phương án vận hành cần xác định:

- Phân tách quản trị nền tảng, quản trị database và tài khoản ứng dụng.
- Lưu secret bằng cơ chế phù hợp; có quy trình thay mật khẩu, wallet hoặc chứng thư.
- Kiểm soát quyền sử dụng khóa mã hóa và thao tác khôi phục.
- Thu thập audit của cả cloud lẫn database, thống nhất thời gian và cách liên kết sự kiện.
- Có quyền truy cập khẩn cấp được kiểm soát khi hệ thống identity chính gián đoạn.

Phạm vi bảo vệ dữ liệu phải bao gồm bản chính, standby, bản sao phân tích, backup và log. Đưa dữ liệu sang cloud thứ hai để làm báo cáo vẫn là tạo thêm một phạm vi cần quản lý truy cập.

### 6.5. Khả năng vận hành và tự động hóa

Đánh giá năng lực của đội vận hành theo những tác vụ cụ thể: vá lỗi, phục hồi dữ liệu, xoay vòng chứng thư, mở rộng tài nguyên, xử lý replication lag và chuyển vai trò khi sự cố.

Cần có bảng trách nhiệm cho nhà cung cấp, đội nền tảng, DBA và đội ứng dụng. Với mỗi tác vụ, ghi người thực hiện, điều kiện kích hoạt, cửa sổ bảo trì và nơi tiếp nhận cảnh báo.

Tự động hóa bằng Terraform hoặc công cụ tương đương cần xét đồng thời hai hệ sinh thái:

- Quyền tạo và sửa tài nguyên ở mỗi phía.
- Thứ tự liên kết tài khoản, mạng và database.
- Quản lý state, secret và các giá trị đầu ra.
- Phát hiện thay đổi cấu hình thủ công.
- Khôi phục khi một bước thành công nhưng bước tiếp theo thất bại.

Một lần chạy triển khai qua nhiều API không mặc nhiên là một giao dịch nguyên tử. Quy trình phải biết tài nguyên nào đã tạo và bước nào có thể chạy lại an toàn.

Về giám sát, nên có dashboard liên kết tình trạng ứng dụng, mạng, database, replication và backup. Cảnh báo “database vẫn chạy” là chưa đủ nếu pool kết nối đã cạn hoặc ứng dụng không phân giải được endpoint.

### 6.6. Vị trí dữ liệu và phạm vi quản trị

Lập bản đồ riêng cho:

1. Database chính và các replica.
2. Backup cùng bản sao backup.
3. Redo, trail file hoặc dữ liệu tạm trong pipeline.
4. Log, audit và dữ liệu chẩn đoán.
5. Đường quản trị, hỗ trợ và công cụ quan sát.

Vị trí của database chính chỉ trả lời một phần câu hỏi dữ liệu nằm ở đâu. Hồ sơ lựa chọn phải đối chiếu các luồng còn lại với yêu cầu nội bộ và điều kiện dịch vụ áp dụng.

### 6.7. Tổng chi phí sở hữu

Nên so sánh theo cùng workload và cùng mục tiêu bảo vệ:

~~~text
TCO theo kỳ =
  compute và database
  + storage và I/O liên quan
  + quyền sử dụng phần mềm và hỗ trợ
  + kết nối riêng / VPN / thiết bị mạng
  + lưu lượng theo đường truyền thực tế
  + backup và nơi phục hồi
  + tài nguyên dự phòng
  + giám sát và công vận hành
  + chi phí di trú, thử nghiệm, chạy song song
~~~

Kiểm tra riêng từng luồng: ứng dụng–database, redo, CDC, backup và log. Điều kiện tính phí của một luồng không tự áp dụng cho luồng khác. Cần tính cả tải thường ngày lẫn khôi phục sau gián đoạn.

Một phương án có chi phí database thấp nhưng buộc ứng dụng tải tập dữ liệu lớn qua ranh giới cloud nhiều lần có thể có TCO cao hơn. Ngược lại, đặt database gần ứng dụng nhưng cấp hạ tầng lớn hơn nhu cầu cũng có thể không hiệu quả.

Budgets, cảnh báo và tag giúp phát hiện chi phí. Không mặc định cảnh báo ngân sách là cơ chế tự động dừng tài nguyên. Quy trình dọn môi trường thử cần xét cả tài nguyên và cam kết thương mại còn hiệu lực.

## 7. Quy trình lựa chọn có thể kiểm chứng

### Bước 1: Chốt nhu cầu và điều kiện loại trừ

Ghi rõ workload hiện tại, nơi chạy ứng dụng, dung lượng dữ liệu, tăng trưởng, giờ cao điểm, tính năng bắt buộc, SLO, RTO/RPO và ngân sách.

Điều kiện loại trừ có thể là thiếu region được phép, không hỗ trợ tính năng bắt buộc, không cấp được tài nguyên đúng hạn hoặc vượt giới hạn chi phí đã duyệt.

### Bước 2: Lập danh sách phương án khả thi

Thông thường nên có từ hai đến ba phương án đủ khác biệt để so sánh, chẳng hạn:

- Ứng dụng giữ nguyên, database trên OCI qua kết nối riêng.
- Ứng dụng giữ nguyên, database trên Database@ tương ứng.
- Di chuyển cả ứng dụng và database về OCI nếu mục tiêu và ràng buộc cho phép.

Phương án thứ ba tạo đường cơ sở để đánh giá chi phí của việc duy trì ranh giới cloud. Nếu ứng dụng bắt buộc giữ ở cloud hiện tại, loại phương án này ngay theo ràng buộc thay vì tiếp tục chấm điểm.

### Bước 3: Vẽ đường dữ liệu và miền lỗi

Cho mỗi phương án, đánh dấu vị trí ứng dụng, database, standby, DNS, secret, backup và thành phần quan sát. Vẽ rõ từng luồng có đi qua ranh giới region, zone hoặc cloud hay không.

Gắn mỗi thành phần với đội chịu trách nhiệm. Nếu chưa xác định được ai xử lý một cảnh báo, thiết kế vận hành còn thiếu.

### Bước 4: Thực hiện thử nghiệm đại diện

Chọn những giao dịch thật sự chi phối trải nghiệm: đăng nhập, tìm kiếm, tạo đơn, thanh toán, chạy batch hoặc tổng hợp báo cáo.

Giữ dataset, tải và cấu hình ứng dụng tương đương khi so sánh. Đo trạng thái bình thường, giờ cao điểm và một số kịch bản lỗi đã thống nhất. Lưu kết quả theo từng điều kiện, không chỉ lưu số trung bình tổng hợp.

### Bước 5: Sàng lọc rồi mới chấm điểm

Chỉ chấm điểm các phương án đã đáp ứng điều kiện bắt buộc. Có thể dùng bộ trọng số minh họa:

| Tiêu chí so sánh | Trọng số minh họa |
| --- | ---: |
| Hiệu năng và dư địa tăng trưởng | 30% |
| Khả năng phục hồi và kết quả diễn tập | 25% |
| TCO theo workload | 20% |
| Năng lực vận hành hiện có | 15% |
| Khả năng di trú và thay đổi về sau | 10% |

~~~text
Điểm tổng = tổng (trọng số × điểm từng tiêu chí)

Ví dụ thang điểm: 1 đến 5.
Tổng trọng số: 100%.
Mỗi điểm cần gắn với bằng chứng hoặc giả định được ghi rõ.
~~~

Đây là phương pháp ra quyết định minh họa, không phải thang đánh giá của Oracle. Không dùng điểm tổng cao để bù cho việc vi phạm RPO bắt buộc hoặc thiếu tính năng cần thiết.

### Bước 6: Chốt kế hoạch chuyển đổi và phương án quay lại

Bản thiết kế cần có cách initial load, đồng bộ thay đổi, đối soát, đóng/mở ghi và cập nhật kết nối ứng dụng.

Phải chỉ ra thời điểm việc quay lại hệ thống cũ còn đơn giản. Sau khi hệ thống mới đã nhận ghi, quay endpoint về nguồn cũ có thể làm mất hoặc phân kỳ dữ liệu. Lúc đó cần phương án đồng bộ ngược hay khôi phục đã được kiểm chứng.

## 8. Ví dụ lựa chọn cho ứng dụng bán hàng đang chạy trên Azure

### 8.1. Dữ kiện giả định

Một doanh nghiệp có:

- Ứng dụng bán hàng bắt buộc giữ trên Azure.
- Oracle Database khoảng 6 TB, nhiều PL/SQL và yêu cầu tính năng tương đương môi trường hiện tại.
- Giao dịch tạo đơn có khoảng 24 lượt trao đổi database tuần tự.
- Mục tiêu p99 của thao tác tạo đơn không quá 250 ms.
- RTO 30 phút, RPO tối đa 60 giây cho kịch bản DR đã xác định.
- Đội DBA đã quen OCI nhưng chưa vận hành database tự quản trên IaaS của Azure.

Các số liệu trong ví dụ chỉ phục vụ học tập, không mô tả khách hàng thật hay hiệu năng của dịch vụ.

Hai phương án ban đầu:

- **A:** ứng dụng trên Azure, database trên OCI qua kết nối riêng.
- **B:** ứng dụng trên Azure, database trên Database@Azure tại vị trí hỗ trợ phù hợp.

### 8.2. Ước lượng trước khi thử nghiệm

Giả sử phần xử lý ngoài thời gian trao đổi mạng khoảng 95 ms và RTT của phương án A là 8 ms:

~~~text
Ước lượng đơn giản cho một yêu cầu:
95 + 24 × 8 = 287 ms
~~~

Kết quả cho thấy A có nguy cơ không đáp ứng mục tiêu và đáng ưu tiên khảo sát việc giảm số lượt gọi. Đây không phải phép tính p99: không thể dùng việc cộng các số minh họa để suy ra percentile của hệ thống thật.

Với B, vị trí gần ứng dụng tạo cơ sở để kỳ vọng giảm phần chờ mạng, nhưng kết quả vẫn phải xác nhận bằng đo tải.

### 8.3. Kết quả thử nghiệm minh họa và quyết định

Giả sử nhóm dự án đã kiểm tra đủ tính năng, điều kiện cấp phát và thực hiện thử tải. Bảng sau là dữ liệu giả lập cho ví dụ:

| Hạng mục | Phương án A | Phương án B |
| --- | --- | --- |
| Tính năng bắt buộc | Đã xác nhận đáp ứng | Đã xác nhận đáp ứng |
| p99 tạo đơn ở tải mục tiêu | 315 ms | 185 ms |
| Mục tiêu p99 ≤ 250 ms | Không đạt | Đạt |
| RTO/RPO | Cần tiếp tục đánh giá nếu thay đổi ứng dụng để thử lại | Đạt trong kịch bản diễn tập đã mô tả |
| Ngân sách đã xác định | Trong giới hạn | Trong giới hạn |
| Trách nhiệm quản trị | Đã phân công | Đã phân công giữa đội Azure, OCI, DBA và ứng dụng |

Trong tập giả định này, **chọn B** vì đáp ứng điều kiện bắt buộc của ứng dụng hiện tại. A bị loại bởi phép đo hiệu năng; không cần dùng bảng điểm trọng số để hợp thức hóa quyết định đó.

Nếu nhóm cải tiến ứng dụng, giảm số lượt trao đổi và thử lại A thành công, cả hai có thể quay về vòng so sánh TCO cùng khả năng vận hành. Kết luận kiến trúc phụ thuộc workload đã đo.

Trước triển khai thật, phương án B vẫn cần kế hoạch di trú và hồ sơ HA/DR chính xác cho loại dịch vụ đã chọn. Mức RTO/RPO đạt trong một diễn tập không đại diện cho mọi kiểu sự cố.

## 9. Bài thực hành: tạo bằng chứng cho một quyết định

Bài thực hành tập trung vào khảo sát và kiểm chứng. Có thể thực hiện phần thiết kế mà chưa cấp phát tài nguyên trả phí.

### 9.1. Chuẩn bị hồ sơ workload

Chọn một ứng dụng Java hoặc ứng dụng doanh nghiệp quen thuộc. Ghi:

- Cloud và region ứng dụng dự kiến chạy.
- Phiên bản database, dung lượng và tính năng cần giữ.
- Ba luồng nghiệp vụ quan trọng.
- SLO, RTO/RPO và giới hạn chi phí.
- Mức độ trễ dữ liệu mà từng luồng đọc có thể chấp nhận.

Nếu chưa có dữ liệu, đánh dấu “giả định cần đo”. Không biến số giả định thành bằng chứng hệ thống đã đáp ứng yêu cầu.

### 9.2. Thiết kế hai phương án

Vẽ hai sơ đồ: database trên OCI qua kết nối riêng và Database@ tại cloud ứng dụng. Đánh dấu rõ VCN/VNet/VPC, CIDR, DNS, lớp quyền, backup, standby và đường giám sát.

Nếu Database@ chưa hỗ trợ dịch vụ hoặc vị trí cần dùng, ghi lý do loại và chọn phương án khả thi khác. Không giả định tính năng chưa có chỉ để hoàn thành sơ đồ.

### 9.3. Kiểm tra kết nối trong môi trường đã được cấp

Ví dụ PowerShell sau dùng từ máy thuộc mạng ứng dụng, sau khi thay endpoint và cổng bằng cấu hình dịch vụ thực tế:

~~~powershell
$dbHostName = "db-private.example.internal"
$dbListenerPort = 1521

Resolve-DnsName -Name $dbHostName
Test-NetConnection -ComputerName $dbHostName -Port $dbListenerPort
~~~

Tên host là ví dụ; 1521 là cổng minh họa. Một dịch vụ hoặc cấu hình TLS có thể dùng cổng khác. Lấy giá trị chính xác từ thông tin kết nối của database.

Kết quả TCP thành công chỉ chứng minh kiểm tra tới cổng đã chọn thành công. Nó chưa xác minh được chứng thư, tài khoản, service name, quyền truy cập schema hoặc hiệu năng giao dịch.

Sau khi đăng nhập bằng client Oracle thích hợp, có thể xác nhận ngữ cảnh phiên bằng câu SQL chỉ đọc:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

Đối chiếu kết quả với database đích dự kiến trước khi thử tải. Với ứng dụng Java, dùng JDBC driver và thông số kết nối phù hợp với phiên bản, dịch vụ và phương thức bảo mật đã chọn; giữ thông tin bí mật ngoài mã nguồn.

### 9.4. Đo tải và lỗi có kiểm soát

Lập bảng kết quả tối thiểu:

| Thử nghiệm | Chỉ số cần thu thập | Bằng chứng cần giữ |
| --- | --- | --- |
| Tải bình thường | p50/p95/p99, throughput, lỗi | Cấu hình tải và thời gian đo |
| Giờ cao điểm | Pool wait, CPU, I/O, network | Tải đồng thời và trạng thái hệ thống |
| Mất một đường kết nối | Thời gian phát hiện, mất request, phục hồi | Mốc sự kiện và tuyến còn hoạt động |
| Chuyển vai trò theo quy trình | RTO đầu cuối và dữ liệu kiểm chứng | Thời điểm giao dịch xác nhận cuối cùng trước lỗi, kết quả sau chuyển đổi |
| Khôi phục từ backup | Thời gian phục hồi và tính toàn vẹn | Điểm khôi phục, quyền và khóa đã sử dụng |

Chỉ thực hiện mô phỏng lỗi trong môi trường thử nghiệm có phạm vi được thống nhất. Với DR, cần dữ liệu đánh dấu hoặc sổ ghi giao dịch từ phía client để đối chiếu các giao dịch đã được xác nhận trước sự cố. Đếm số dòng đơn thuần không đủ chứng minh RPO.

Các thử nghiệm này là kế hoạch kiểm chứng cho người học; bài học không giả định chúng đã chạy trên hệ thống thật.

### 9.5. Dọn môi trường và chốt kết quả

Nếu đã cấp phát tài nguyên, rà soát tài nguyên database, storage, backup, endpoint, kết nối mạng, log và các tài nguyên phụ thuộc trước khi đóng lab. Đối chiếu phần nào được phép xóa, phần nào cần giữ và phần chi phí còn tiếp tục phát sinh.

Kết quả thực hành là một quyết định có căn cứ: phương án chọn, phương án loại, bằng chứng, giới hạn của kết quả đo và danh sách điều kiện phải xác minh trước production.

## 10. Các sai lầm cần tránh

| Sai lầm | Cách sửa cách tiếp cận |
| --- | --- |
| Gọi mọi kết nối Azure–OCI là Database@Azure | Xác định database nằm trong OCI region hay trong hạ tầng dịch vụ tại Azure |
| Cho rằng Database@ ở mọi cloud có cùng danh mục | Kiểm tra dịch vụ, region, phiên bản và topology cụ thể |
| So sánh giá database trước khi kiểm tra tính năng | Sàng lọc yêu cầu bắt buộc rồi mới so TCO |
| Dùng băng thông lớn để kết luận độ trễ thấp | Đo RTT và số lượt trao đổi tuần tự của ứng dụng |
| Cho rằng mạng riêng đã đáp ứng mọi yêu cầu bảo mật | Kiểm tra quyền, mã hóa, chứng thư, secret và audit |
| Gọi standby là một nguồn ghi độc lập | Xác định vai trò database và luồng ghi được hỗ trợ |
| Xem replication lag thấp là cam kết RPO tuyệt đối | Đối chiếu chế độ bảo vệ và dữ liệu qua kịch bản sự cố |
| Chỉ kiểm tra database sau failover | Đo cả DNS, pool, retry và khả năng hoàn tất giao dịch nghiệp vụ |
| Cho rằng hai cloud luôn là hai miền lỗi độc lập | Kiểm tra các phụ thuộc dùng chung |
| Quay endpoint về nguồn cũ sau khi đích đã nhận ghi | Thực hiện phương án xử lý dữ liệu phát sinh và đồng bộ ngược đã thiết kế |

## 11. Mẫu hồ sơ quyết định kiến trúc

Có thể dùng mẫu ngắn sau trong tài liệu thiết kế của dự án:

~~~text
Quyết định: Chọn mô hình Oracle Database đa đám mây cho <workload>.

Bối cảnh:
- Vị trí ứng dụng:
- Loại dịch vụ và vị trí database:
- Yêu cầu tính năng:
- SLO và tải mục tiêu:
- RTO/RPO cùng phạm vi sự cố:
- Ngân sách:

Các phương án:
- Phương án 1:
- Phương án 2:
- Phương án bị loại và điều kiện không đáp ứng:

Bằng chứng:
- Tài liệu hỗ trợ dịch vụ/region/topology:
- Kết quả thử tải:
- Kết quả diễn tập phục hồi:
- Ước tính TCO và các giả định:

Quyết định và trách nhiệm:
- Phương án chọn:
- Lý do:
- Chủ sở hữu mạng, IAM, database, ứng dụng, backup và cảnh báo:

Triển khai:
- Initial load và đồng bộ:
- Đối soát trước cutover:
- Điều kiện đóng/mở ghi:
- Phương án quay lại và điểm giới hạn:
- Điều kiện cần đánh giá lại:
~~~

Một hồ sơ đủ dùng phải cho phép người khác giải thích được vì sao chọn mô hình đó, dữ liệu nào chứng minh lựa chọn và thay đổi nào sẽ khiến quyết định cần được xem xét lại.

