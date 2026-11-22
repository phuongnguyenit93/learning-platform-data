# License Included, BYOL và phạm vi trách nhiệm vận hành

Trong chương **Oracle Database trên OCI** của module **CLOUD_PROVIDERS_ORACLE**, chọn dịch vụ cơ sở dữ liệu cần trả lời hai câu hỏi độc lập: **quyền sử dụng phần mềm đến từ đâu** và **ai chịu trách nhiệm cho từng công việc vận hành**.

Một ứng dụng trên Compute có thể kết nối qua VCN đến Base Database Service hoặc Autonomous Database. Cùng một nhu cầu dữ liệu, tổ chức có thể dùng quyền phần mềm đi kèm dịch vụ hoặc đưa các license hiện có vào sử dụng nếu đáp ứng điều kiện. Lựa chọn đó ảnh hưởng chi phí và cách quản lý quyền sử dụng, nhưng không tự thay thế việc thiết kế IAM, mạng, sao lưu, giám sát hay khôi phục.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích License Included và Bring Your Own License trong ngữ cảnh dịch vụ Oracle Database.
- Phân biệt license model, database edition, compute metric và mức độ quản lý dịch vụ.
- Xác định thông tin cần đối chiếu trước khi chọn BYOL hoặc thay đổi quy mô.
- Phân công công việc vận hành giữa Oracle và đội ngũ khách hàng theo loại dịch vụ.
- Đọc cấu hình license trên OCI mà không nhầm cấu hình kỹ thuật với bằng chứng entitlement.
- Lập phương án chi phí và thay đổi tài nguyên có tính đến sao lưu, DR, clone và khả năng mở rộng.

## Hai trục lựa chọn cần tách biệt

**License model** trả lời quyền phần mềm được cung cấp hoặc áp dụng theo cách nào. **Service operating model** trả lời những lớp nào Oracle vận hành và những lớp nào khách hàng quản lý.

~~~mermaid
flowchart TD
    W["Yêu cầu của workload"] --> L["Quyền sử dụng phần mềm"]
    W --> O["Phạm vi vận hành"]
    L --> LI["License Included"]
    L --> BY["BYOL khi đủ điều kiện"]
    O --> C["Tự quản lý trên Compute"]
    O --> B["Base Database Service"]
    O --> E["Exadata Database Service"]
    O --> A["Autonomous Database"]
    LI --> R["Đối chiếu tổ hợp dịch vụ thực tế"]
    BY --> R
    C --> R
    B --> R
    E --> R
    A --> R
~~~

Sơ đồ là cách phân tích yêu cầu, không khẳng định mọi dịch vụ hoặc edition đều hỗ trợ mọi tổ hợp. Ví dụ, lựa chọn BYOL của một workload Autonomous cụ thể có thể khác với workload khác; một chương trình dành cho developer cũng có giới hạn riêng.

Hai Base Database DB system có cùng cấu hình, cùng edition và cùng cách quản lý nhưng khác license model vẫn cần người chịu trách nhiệm cập nhật phần mềm, bảo vệ dữ liệu và xử lý ứng dụng. Chuyển license model không biến một DB system thành Autonomous Database.

## License Included: quyền phần mềm đi cùng dịch vụ đã chọn

Với **License Included**, giá của tài nguyên dịch vụ bao gồm quyền phần mềm Oracle Database trong phạm vi gói/edition được chọn cùng dịch vụ cloud. Người dùng không cần đưa license hiện có vào để đáp ứng chính phần quyền đã được bao gồm đó. Tài liệu tạo Base Database phân biệt trực tiếp lựa chọn này với BYOL; xem [License type khi tạo DB system](https://docs.oracle.com/en/cloud/paas/base-database/guide/dbs-create-new.html).

Cần hiểu đúng giới hạn của từ “included”:

| Điều có thể hiểu | Điều không được tự suy ra |
| --- | --- |
| Dịch vụ đã chọn cung cấp phần quyền phần mềm theo điều khoản của dịch vụ | Mọi sản phẩm, edition, option và management pack của Oracle đều được dùng |
| Phần chi phí dịch vụ phản ánh lựa chọn license | Toàn bộ storage, backup, DR và kết nối mạng đều không có chi phí riêng |
| Có quyền sử dụng trong phạm vi đăng ký dịch vụ | Có thêm một license vĩnh viễn có thể đem đi triển khai tùy ý ở nơi khác |
| Support đi theo phạm vi thuê bao tương ứng | Oracle chịu trách nhiệm sửa mọi lỗi ứng dụng hoặc quản trị mọi schema |

Ví dụ, một đội xây ứng dụng mới chưa có pool license phù hợp có thể đánh giá License Included để không phải đưa quyền phần mềm hiện có vào tài nguyên đó. Họ vẫn cần chọn đúng dịch vụ, edition và tính năng cần dùng, rồi tính chi phí theo hình thức tiêu thụ thực tế.

Không dùng một bản báo giá chỉ ghi “Oracle Database” để kết luận mọi khả năng enterprise đều được bao gồm. Phải biết chính xác SKU/dịch vụ, edition, phiên bản và quyền tính năng áp dụng.

## BYOL: áp dụng quyền sử dụng hiện có, vẫn trả tiền dịch vụ

**Bring Your Own License — BYOL** cho phép sử dụng các license Oracle hiện có, đủ điều kiện, cho dịch vụ cloud tương ứng. Tổ chức đưa entitlement của mình vào thay cho phần quyền phần mềm mà dịch vụ License Included cung cấp.

BYOL vẫn có thuê bao cloud và các khoản vận hành liên quan. Tổ chức cũng tiếp tục thực hiện nghĩa vụ support áp dụng cho license đã đưa vào. Các license áp dụng cho dịch vụ BYOL được xem là đang sử dụng; không được coi chúng vẫn rảnh chỉ vì đang nằm trong cloud. Xem [mô hình thanh toán BYOL của Oracle](https://docs.oracle.com/en/cloud/get-started/subscriptions-cloud/ocpib/billing-models-offered.html).

**Entitlement** là phạm vi quyền sử dụng có căn cứ từ hợp đồng và tài liệu liên quan: sản phẩm, edition, metric, số lượng, phạm vi triển khai và những điều kiện đi kèm. Nó không phải một cờ cấu hình trong OCI.

Ba việc sau cần được phân biệt:

~~~text
Tổ chức có hồ sơ license phù hợp
    -> phân bổ entitlement cho workload cloud
    -> cấu hình license model BYOL trên đúng tài nguyên
~~~

Nếu thiếu bước đầu hoặc bước phân bổ, một tài nguyên vẫn có thể hiển thị BYOL nhưng tổ chức chưa chứng minh được quyền sử dụng tương ứng. API chấp nhận thao tác chỉ xác nhận thao tác kỹ thuật hợp lệ trong ngữ cảnh API.

### BYOL to PaaS khác triển khai tự quản lý trên IaaS

Đưa license vào một dịch vụ database có quản lý không đồng nghĩa cài Oracle Database lên một Compute VM thông thường. Các quyền bổ sung, cách ánh xạ năng lực và công việc vận hành có thể khác.

Oracle có chương trình BYOL to PaaS và mô tả khác biệt với BYOL to IaaS, bao gồm một số quyền tính năng bổ sung trong phạm vi PaaS. Vì vậy, không dùng bảng quyền của PaaS để mặc định cấp quyền tương tự cho một bản cài tự quản lý trên Compute. Xem [Oracle BYOL FAQ](https://www.oracle.com/cloud/bring-your-own-license/faq/).

Điều ngược lại cũng cần tránh: không tự kết luận phải mua riêng mọi option hiện có trong PaaS. Phải đối chiếu quyền được dịch vụ cấp bổ sung với license tổ chức thực sự cần mang vào.

## Những thông tin phải đối chiếu cho BYOL

Trước khi triển khai, cần nối được thông tin hợp đồng với cấu hình workload dự kiến:

| Nhóm thông tin | Cần xác định | Vì sao cần |
| --- | --- | --- |
| Sản phẩm và edition | Quyền cho sản phẩm nào, edition nào | Cùng tên Oracle Database chưa đủ để khớp mọi dịch vụ |
| Metric | Processor, Named User Plus hoặc metric được hợp đồng quy định | Không quy đổi metric bằng suy đoán về số người dùng hay số CPU |
| Số lượng | Số quyền có thể phân bổ, số đã dùng và số còn lại | Tránh dùng trùng entitlement |
| Option và pack | Những tính năng nào đã được cấp và những quyền nào dịch vụ bao gồm | Khả năng kỹ thuật không tự xác nhận quyền sử dụng |
| Support | Hợp đồng support nào bao phủ và tình trạng hiệu lực | Khớp điều kiện dịch vụ và đường hỗ trợ |
| Dịch vụ đích | Base, Exadata, Autonomous; cấu hình triển khai cụ thể | Ánh xạ và giới hạn có thể khác |
| Compute model | ECPU, OCPU hoặc metric của offering đang dùng | Không xem các đơn vị là tương đương mặc định |
| Môi trường | Production, test, clone, standby và migration | Phạm vi sử dụng có thể rộng hơn primary |
| Hợp đồng đặc thù | Điều khoản ULA hoặc chương trình riêng nếu có | Không áp dụng quy tắc của chương trình khác một cách máy móc |

Nguồn đối chiếu gồm agreement, ordering document, service description và policy áp dụng cho tổ chức. Oracle mô tả cấu trúc hợp đồng cloud theo các thành phần này tại [Cloud Services Contracts](https://www.oracle.com/contracts/cloud-services/).

Tài liệu sản phẩm giúp hiểu tham số và khả năng dịch vụ; tài liệu hợp đồng xác định quyền áp dụng. Một ảnh chụp Console hoặc thông tin từ một môi trường khác không thay thế được chuỗi bằng chứng này.

### Không dùng một tỷ lệ CPU chung cho mọi trường hợp

Đừng ghi quy tắc nội bộ kiểu “một license luôn bằng một CPU cloud” hoặc lấy một phép ánh xạ OCPU rồi áp thẳng vào ECPU. Phép quy đổi cần đúng sản phẩm, edition, metric, dịch vụ và phiên bản điều khoản.

Cách làm thực tế là ghi rõ nguồn của phép ánh xạ, ngày hiệu lực và cấu hình được áp dụng. Khi đổi compute model hoặc dịch vụ, tính lại theo nguồn tương ứng thay vì chỉ đổi tên cột trong bảng tính.

Catalog cũng có thể thay đổi theo thời gian. Tài liệu Base Database hiện có thông báo thay đổi/retirement với một số shape và SKU cũ; không dùng nguyên một cấu hình trong bài hướng dẫn cũ làm bằng chứng rằng tài nguyên mới vẫn provision được. Xem [About Oracle Base Database Service](https://docs.oracle.com/en/cloud/paas/base-database/guide/about.html).

## Edition, license model và tính năng là ba thông tin riêng

Một tài nguyên có thể được mô tả bằng các thuộc tính khác nhau:

~~~text
Service: loại dịch vụ database
Edition: gói phần mềm được chọn
License model: LICENSE_INCLUDED hoặc BRING_YOUR_OWN_LICENSE
Compute model: đơn vị đo năng lực và tính phí
Capacity: quy mô tài nguyên đang cấu hình
Features: các tính năng thực sự sử dụng
~~~

Tên edition giúp xác định gói khả năng; license model cho biết cách cung cấp quyền. Không dùng một thuộc tính để thay cho thuộc tính còn lại.

Ví dụ, muốn sử dụng RAC, một option database hoặc management pack, đội dự án phải xác nhận cả khả năng hỗ trợ của dịch vụ và quyền sử dụng tương ứng. Có thể bật được một tính năng không chứng minh rằng mọi triển khai của tính năng đó đều hợp lệ.

Với Base Database Service, License Included có support thông qua thuê bao dịch vụ database. Khách hàng BYOL phải có hợp đồng support hợp lệ bao phủ các license đang dùng trong dịch vụ. Khách hàng vẫn chịu trách nhiệm áp dụng cập nhật database kịp thời. Xem [Support Requirements của Base Database Service](https://docs.oracle.com/en/cloud/paas/base-database/guide/about.html).

Không suy rộng điều kiện riêng của Base Database thành bảng nghĩa vụ giống hệt cho mọi offering khác.

## Trách nhiệm vận hành theo mức dịch vụ

Oracle chịu trách nhiệm về những lớp được dịch vụ quản lý; khách hàng chịu trách nhiệm với workload, cấu hình và dữ liệu trong phạm vi của mình. Mô hình bảo mật OCI cũng phân biệt trách nhiệm hạ tầng với bảo vệ workload và hệ điều hành của Compute. Xem [Shared Security Model của OCI](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_overview.htm).

Bảng sau là bản định hướng để phân công, cần cụ thể hóa theo dịch vụ đã chọn:

| Công việc | Tự cài database trên Compute | Base Database Service | Exadata Database Service trên Dedicated Infrastructure | Autonomous Database |
| --- | --- | --- | --- | --- |
| Hạ tầng cloud do Oracle cung cấp | Oracle quản lý lớp hạ tầng | Oracle quản lý | Oracle quản lý hạ tầng Exadata | Oracle quản lý |
| Guest OS của môi trường database | Khách hàng quản lý | Khách hàng chịu trách nhiệm cập nhật lớp OS của DB system | Khách hàng chịu trách nhiệm Guest VM OS | Oracle quản lý lớp phục vụ dịch vụ |
| Phần mềm database và bảo trì thường kỳ | Khách hàng tổ chức thực hiện | Có tooling, khách hàng tổ chức cập nhật và kiểm thử | Có automation, khách hàng chịu trách nhiệm DB/GI của môi trường được quản lý | Oracle tự động hóa các tác vụ quản trị thuộc dịch vụ |
| Schema, dữ liệu và quyền ứng dụng | Khách hàng | Khách hàng | Khách hàng | Khách hàng |
| Mục tiêu phục hồi và xác minh nghiệp vụ | Khách hàng xác định và diễn tập | Khách hàng xác định và diễn tập | Khách hàng xác định và diễn tập | Khách hàng vẫn xác định và xác minh |
| Phân bổ entitlement BYOL nếu dùng | Khách hàng | Khách hàng | Khách hàng | Khách hàng |

### Base Database: có automation, vẫn cần đội vận hành

Oracle cung cấp hạ tầng và các công cụ vòng đời dịch vụ. Đội khách hàng vẫn phải tổ chức cập nhật OS/database, kiểm thử, theo dõi ứng dụng và quản lý backup/recovery của dữ liệu theo phân công. Có nút Patch hoặc chức năng Backup không có nghĩa mọi nghĩa vụ lập kế hoạch và nghiệm thu đã được Oracle tiếp nhận. Xem [bảng trách nhiệm bảo mật và vận hành Base Database](https://docs.oracle.com/en/cloud/paas/base-database/guide/security-guide.html).

Đội vận hành nên có người nhận cảnh báo patch, chọn lịch, thực hiện tiền kiểm tra, xác nhận backup cần thiết và kiểm tra ứng dụng sau thay đổi. Người sở hữu công việc có thể dùng automation để làm, nhưng vẫn phải chịu trách nhiệm về kết quả.

### Exadata Database Service không đồng nghĩa Autonomous Database

Với Exadata Database Service trên Dedicated Infrastructure, Oracle quản lý hạ tầng; khách hàng quản lý các thành phần truy cập được như Guest VM và dịch vụ database, bao gồm trách nhiệm bảo trì tương ứng. Đây không phải cùng ranh giới vận hành với Autonomous Database chỉ vì cả hai có thể chạy trên công nghệ Exadata. Xem [Security Guide của Exadata Database Service](https://docs.oracle.com/en/engineered-systems/exadata-cloud-service/ecscm/ecs-security-guide.html).

### Autonomous: tự động hóa nhiều hơn, khách hàng vẫn quản lý ứng dụng

Autonomous Database tự động hóa các công việc như áp dụng bản vá bảo mật và cung cấp backup tự động theo khả năng, cấu hình của dịch vụ. Xem [Security Features Overview của Autonomous Database](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/security-features-overview.html).

Khách hàng vẫn phải thiết kế schema, kiểm soát tài khoản, cấu hình kết nối, bảo vệ bí mật và kiểm tra hành vi ứng dụng. Khi xảy ra lỗi dữ liệu do ứng dụng, cần có người chọn điểm phục hồi, điều phối ứng dụng và xác nhận dữ liệu sau restore.

Một ví dụ cho ranh giới này: backup database không bao gồm các tệp dữ liệu ngoài trên Object Storage dùng cho external table. Khách hàng phải tổ chức bảo vệ và phục hồi các tệp đó để có bộ dữ liệu nhất quán. Xem [Restore and Recover Autonomous Database](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/backup-recover.html).

Vì vậy, “Oracle quản lý backup” và “toàn hệ thống phục hồi đúng nghiệp vụ” là hai kết quả khác nhau cần có người phụ trách.

## Scale, clone và DR làm thay đổi phạm vi cần tính

Một bản kiểm kê chỉ ghi số CPU của primary tại thời điểm bình thường thường không đủ cho một thiết kế có mở rộng và phục hồi.

| Thay đổi | Điều cần đánh giá trước |
| --- | --- |
| Tăng compute của primary | Ánh xạ entitlement theo metric dịch vụ và năng lực sau thay đổi |
| Bật auto scaling | Phần năng lực có thể được dùng thêm và cách dịch vụ tính license/billing |
| Tạo clone để kiểm thử | License model, edition và thời gian tồn tại của clone |
| Tạo standby | Quyền cho triển khai dự phòng, các tính năng dùng trên standby và điều khoản liên quan |
| Diễn tập DR | Quyền cho môi trường được kích hoạt, thời gian chạy đồng thời và quy mô khi failover |
| Migration | Giai đoạn source và target cùng chạy, quyền và điều kiện chuyển tiếp áp dụng |
| Đổi dịch vụ hoặc compute model | Kiểm tra lại cách ánh xạ, gói tính năng và chi phí |
| Dừng hoặc xóa tài nguyên | Điều kiện tính phí, dữ liệu/backup còn giữ và việc cập nhật phân bổ license |

Đừng mặc định môi trường test, clone, standby hoặc server ít hoạt động đều không cần tính quyền. Cũng không áp dụng một quy tắc dự phòng chung cho mọi sản phẩm mà chưa đối chiếu điều khoản tương ứng.

Với clone Base Database, lựa chọn license của clone áp dụng cho clone và không thay đổi nguồn. Điều đó cho thấy cần kiểm tra từng tài nguyên phát sinh thay vì coi chúng là bản sao miễn phí về quyền sử dụng. Xem [Clone a DB System](https://docs.oracle.com/en/cloud/paas/base-database/guide/dbs-clone.html).

### Giới hạn BYOL có thể là giới hạn phần được bao phủ, không phải giới hạn công suất

Autonomous Database với ECPU có lựa chọn BYOL và edition theo workload được hỗ trợ. Với Enterprise Edition, tài liệu mô tả tùy chọn BYOL ECPU limit xác định phần ECPU được các license đưa vào bao phủ. Các ràng buộc với Standard Edition khác với Enterprise Edition. Xem [BYOL trên Autonomous Database ECPU](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/autonomous-update-license.html).

Trong API/CLI Autonomous, thuộc tính `byol-compute-count-limit` mô tả giới hạn CPU được BYOL bao phủ; phần dùng vượt giới hạn được xem là License Included và tính phí theo đó. Phạm vi được mô tả còn liên quan auto scaling và các tài nguyên sử dụng cho DR/công cụ tương ứng. Xem [tham số BYOL compute count limit](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/autonomous-database/create.html).

Điểm cần nhớ là một giới hạn BYOL được hỗ trợ có thể phân chia cách bao phủ quyền và tính phí; không được mặc định nó là một hard cap chặn toàn bộ nhu cầu compute.

Đây là hành vi của offering được tài liệu mô tả, không phải quy tắc chung rằng mọi dịch vụ Oracle đều cho trộn BYOL và License Included trên cùng tài nguyên. Khi thiết kế theo tài liệu FAQ tổng quát, phải kiểm tra thêm tài liệu hiện hành của chính dịch vụ và compute model.

### Ví dụ quản lý phân bổ

Giả sử tổ chức đã xác nhận một pool entitlement, sau khi ánh xạ đúng cho dịch vụ đích, có khả năng bao phủ **100 đơn vị năng lực giả định**:

~~~text
Workload A đã phân bổ: 40
Workload B đã phân bổ: 30
Phần chưa phân bổ:    30

Đề xuất workload C:   50
Khoảng thiếu:         20
~~~

Đơn vị trên chỉ dùng minh họa việc phân bổ; nó không phải ECPU, OCPU hay tỷ lệ Oracle công bố. Không đưa các số đó vào một phép tính licensing thật.

Kết luận có thể rút ra là đề xuất C cần được điều chỉnh hoặc có cơ chế quyền/thuê bao bổ sung đã xác nhận. Việc C chỉ dùng trung bình 10 đơn vị khi chạy thử không tự chứng minh rằng phạm vi cấp phép chỉ cần 10; phải áp đúng metric và điều kiện đo lường.

## Đánh giá chi phí theo toàn hệ thống

So sánh License Included với BYOL nên bắt đầu từ cùng một yêu cầu workload: cùng dịch vụ, cùng mục tiêu hiệu năng, cùng phương án sẵn sàng và cùng phạm vi dữ liệu được bảo vệ.

Một mô hình tính chi phí nội bộ có thể viết:

~~~text
Tổng chi phí trong kỳ
  = phí dịch vụ cloud theo mô hình license đã chọn
  + storage và backup tính riêng
  + tài nguyên DR, clone và môi trường kiểm thử
  + truyền dữ liệu và các dịch vụ hỗ trợ
  + support hoặc quyền phần mềm bổ sung chưa nằm trong khoản khác
  + chi phí vận hành và thay đổi hệ thống
~~~

Đây là khung phân tích, không phải bảng giá. Khi một khoản đã nằm trong thuê bao, không cộng lần hai. Khi BYOL sử dụng license đã mua, vẫn cần tính nghĩa vụ support và ảnh hưởng của việc không còn entitlement đó để dùng cho workload khác.

Các sai lệch so sánh thường gặp:

- So giá primary BYOL với giá primary cộng DR của phương án License Included.
- So Base Database phải có người quản trị với Autonomous nhưng bỏ toàn bộ công việc vận hành.
- Dùng giá một compute model cho năng lực của compute model khác.
- Bỏ thời gian chạy đồng thời khi migration hoặc diễn tập.
- Cho rằng dừng compute sẽ làm mọi khoản storage, backup và support biến mất.
- Lấy chi phí chạy thử ít ngày để dự báo production mà chưa tính tải cao điểm.

BYOL có thể giúp tận dụng quyền hiện có; lợi ích thực tế phụ thuộc entitlement còn dùng được và cấu hình dịch vụ. License Included có thể phù hợp khi cần phần quyền do dịch vụ cung cấp. Không có kết luận một phương án luôn rẻ hơn cho mọi tổ chức.

## Thực hành: đọc cấu hình và đối chiếu quyền

Bài thực hành này dùng thao tác đọc. Mục tiêu là phân biệt ba lớp bằng chứng: **cấu hình OCI**, **hồ sơ entitlement** và **phân công vận hành**. Không cần tạo database hay chuyển sang BYOL chỉ để quan sát một giá trị.

Chuẩn bị một tài nguyên lab hoặc tài nguyên được cấp quyền xem, đúng region và compartment, cùng OCI CLI đã xác thực. Chỉ chạy nhóm lệnh phù hợp với dịch vụ đang có. Không cần có cả Base Database lẫn Autonomous Database.

### Đọc License model của Base Database

Các lệnh dưới đây dùng Bash; thay region và OCID bằng tài nguyên được phép đọc:

~~~bash
REGION="ap-singapore-1"
DB_SYSTEM_ID="REPLACE_WITH_BASE_DB_SYSTEM_OCID"

oci db system get \
  --region "$REGION" \
  --db-system-id "$DB_SYSTEM_ID" \
  --query 'data.{id:id,name:"display-name",license:"license-model",edition:"database-edition",shape:shape}' \
  --output json
~~~

Lệnh lấy thông tin DB system, không truy cập dữ liệu trong bảng nghiệp vụ. Xem [OCI CLI db system get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/system/get.html). Không dùng mô hình API DB system cũ này làm mẫu quản lý mọi tài nguyên Exadata hiện hành.

Quan sát license model và edition độc lập. Hai giá trị license model thường gặp là:

~~~text
LICENSE_INCLUDED
BRING_YOUR_OWN_LICENSE
~~~

Nếu tài nguyên trả về BYOL, chỉ có thể kết luận OCI đang cấu hình mô hình đó. Chưa thể kết luận số license đã đủ, support đã hợp lệ hay quyền option đã được xác nhận.

Nếu một trường không có hoặc trả về null, xem output đầy đủ và schema đúng tài nguyên; đừng tự biến null thành “không cần license”.

### Đọc thông tin Autonomous Database

Với Autonomous Database Serverless, có thể đọc các trường liên quan như sau:

~~~bash
REGION="ap-singapore-1"
ADB_ID="REPLACE_WITH_AUTONOMOUS_DATABASE_OCID"

oci db autonomous-database get \
  --region "$REGION" \
  --autonomous-database-id "$ADB_ID" \
  --query 'data.{id:id,name:"display-name",license:"license-model",edition:"db-edition",computeModel:"compute-model",computeCount:"compute-count",autoScaling:"is-auto-scaling-enabled",byolLimit:"byol-compute-count-limit"}' \
  --output json
~~~

Xem [OCI CLI autonomous-database get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/autonomous-database/get.html). Các trường có ý nghĩa theo compute model, workload và deployment đang dùng; không lấy `compute-count` thay thế mọi thuộc tính công suất của mọi loại database.

Trong một triển khai Autonomous trên dedicated infrastructure, license có thể được đặt ở cấp tài nguyên hạ tầng theo mô hình dịch vụ, thay vì được chọn độc lập trên từng database. Vì vậy, nếu cần đối chiếu offering đó, phải đọc đúng cấp cấu hình. Tham khảo [mô tả license-model của Autonomous](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/autonomous-database/create.html).

### Ghi nhận kết quả đối chiếu

Dùng một bản ghi làm việc như mẫu dưới đây trong quy trình quản lý tài nguyên của tổ chức:

~~~text
Resource OCID: giá trị đọc từ OCI
Region / compartment: đã đối chiếu
Service / deployment: đã xác định
Edition: giá trị cấu hình
License model: giá trị cấu hình
Compute model / capacity: giá trị và đơn vị cụ thể
Auto scaling / BYOL limit: giá trị hoặc không áp dụng
Clone / standby / DR liên quan: đã kiểm kê

Entitlement reference: mã hồ sơ nội bộ, hoặc CHƯA XÁC NHẬN
Mapping rule reference: nguồn điều khoản và ngày hiệu lực
Allocated entitlement: số lượng đã đối chiếu, hoặc CHƯA XÁC NHẬN
Support reference: hồ sơ bao phủ, hoặc CHƯA XÁC NHẬN

License owner: vai trò chịu trách nhiệm
Patch owner: vai trò chịu trách nhiệm
Backup / recovery owner: vai trò chịu trách nhiệm
Application validation owner: vai trò chịu trách nhiệm
~~~

Đây là mẫu học tập, không phải hồ sơ license thật hay yêu cầu đưa hợp đồng nhạy cảm vào repository. Tham chiếu mã hồ sơ trong nơi lưu trữ phù hợp thay vì sao chép bí mật hoặc toàn văn hợp đồng vào log triển khai.

Bài thực hành đạt mục tiêu khi người học giải thích được giá trị nào đã đọc trực tiếp, giá trị nào có nguồn entitlement và phần nào còn chưa xác nhận. Điền một con số phỏng đoán vào ô trống không phải hoàn tất đối chiếu.

## Thay đổi license model là một thay đổi cần được kiểm soát

Base Database có thao tác cập nhật license type trên DB system. Lựa chọn đó ảnh hưởng metering và billing; nó không tự tạo hoặc mua thêm entitlement hiện có cho tổ chức. Xem [Manage Licenses on a DB System](https://docs.oracle.com/en/cloud/paas/base-database/guide/dbs-licenses.html).

Một quy trình thay đổi có thể gồm:

1. Xác định đúng tài nguyên, dịch vụ, edition và cấu hình hiện tại.
2. Xác nhận mô hình đích được dịch vụ hỗ trợ và entitlement có thể phân bổ nếu dùng BYOL.
3. Đánh giá compute, auto scaling, clone, DR, support và ảnh hưởng chi phí.
4. Ghi nhận quyết định và người chịu trách nhiệm trước khi thay đổi.
5. Áp dụng đúng thao tác của dịch vụ; chờ hoàn tất và đọc lại trạng thái.
6. Đối chiếu usage/billing sau thời điểm thay đổi và cập nhật sổ phân bổ.
7. Xác minh ứng dụng, cảnh báo và cấu hình liên quan vẫn đáp ứng yêu cầu.

Không suy ra đổi license model sẽ đổi database edition hoặc gỡ những tính năng đã sử dụng. Cũng không coi nó là cách hợp thức hóa ngược quyền phần mềm cho toàn bộ thời gian trước đó.

Khi dự báo chi phí chuyển đổi, kiểm tra cả Known Issues của dịch vụ thay vì giả định metering chuyển tức thời không có giao thoa. Tài liệu [Known Issues của Base Database](https://docs.oracle.com/en/cloud/paas/base-database/guide/known-issues.html) có mục riêng về billing khi đổi license type.

Với hạ tầng được tự động hóa, khai báo license model có chủ ý và kiểm tra lại sau provisioning. Không dựa vào default của UI/SDK hoặc sao chép template BYOL của một nhóm khác: default không xác nhận rằng workload của bạn có entitlement.

## Phân công đội vận hành thành công việc cụ thể

Những câu như “DBA lo database” hoặc “Oracle lo cloud” quá rộng để dùng khi có sự cố. Cần giao công việc, quyền thực hiện và bằng chứng kết quả.

Bảng dưới là ví dụ phân công **trong tổ chức khách hàng**, không sửa ranh giới hợp đồng giữa Oracle và khách hàng:

| Công việc | Vai trò chủ trì đề xuất | Phối hợp | Bằng chứng hoàn tất |
| --- | --- | --- | --- |
| Xác nhận quyền BYOL | Người quản lý license | Mua sắm, DBA, phụ trách hợp đồng | Hồ sơ và phân bổ entitlement khớp tài nguyên |
| Chọn quy mô và edition | DBA/kiến trúc sư dữ liệu | Nhóm ứng dụng, license owner | Cấu hình đáp ứng tải và quyền tính năng |
| Cấu hình VCN, subnet, NSG | Nhóm nền tảng/mạng | DBA và bảo mật | Kết nối đúng nguồn, đúng cổng, đúng đích |
| IAM và quyền database | Nhóm bảo mật cùng DBA | Chủ ứng dụng | Quyền quản trị và quyền SQL tách đúng phạm vi |
| Lập lịch patch của lớp khách hàng quản lý | Đội vận hành database | Nhóm ứng dụng | Tiền kiểm tra, kết quả cập nhật và kiểm thử sau thay đổi |
| Chính sách và giám sát backup | Chủ nhiệm phục hồi dữ liệu | DBA, nhóm nền tảng | Backup đáp ứng phạm vi và thời gian lưu yêu cầu |
| Diễn tập restore/DR | Chủ nhiệm phục hồi | Nhóm ứng dụng, mạng, license owner | Dữ liệu và luồng nghiệp vụ được xác minh |
| Kiểm soát chi phí | Chủ ngân sách/FinOps | DBA, license owner | Usage, phân bổ và chi phí dự báo được đối chiếu |

IAM cấp quyền quản lý tài nguyên OCI; quyền trong database kiểm soát truy cập đối tượng dữ liệu theo cơ chế database. Được gọi API xem DB system không tự cho phép SELECT bảng nghiệp vụ. Ngược lại, một tài khoản SQL không mặc nhiên được scale hoặc xóa tài nguyên cloud.

Đối với patch, owner phải biết lớp nào do Oracle cập nhật và lớp nào đội mình thực hiện. Với Autonomous, owner ứng dụng vẫn theo dõi thông báo bảo trì liên quan, kiểm tra kết nối và khả năng phục hồi của ứng dụng; không lên kế hoạch SSH vào OS dịch vụ như một máy Compute tự quản lý.

Đối với backup, cần xác định phạm vi dữ liệu, thời gian lưu, khóa mã hóa, quyền restore và điểm khôi phục cần dùng. Autonomous có các tác vụ quản lý backup/restore theo offering; khách hàng vẫn phải chọn cấu hình phù hợp trong khả năng được cung cấp. Xem [Backup and Restore Autonomous Database](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/backup-restore.html).

Một backup thành công chưa chứng minh RTO/RPO của toàn hệ thống. **RPO** là mức mất dữ liệu có thể chấp nhận theo thời gian; **RTO** là thời gian mục tiêu để phục hồi dịch vụ. Đội ứng dụng phải kiểm tra cả dữ liệu trên database và phụ thuộc ở Object Storage hoặc hệ thống khác nếu có.

## Những hiểu nhầm thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| Chọn BYOL trên Console nghĩa là Oracle đã xác nhận license | Đó là cấu hình kỹ thuật; entitlement cần hồ sơ đối chiếu riêng |
| BYOL nghĩa là dùng database cloud miễn phí | Vẫn có chi phí dịch vụ và nghĩa vụ liên quan |
| License Included là Oracle vận hành mọi thứ | Mức vận hành phụ thuộc dịch vụ, không phụ thuộc riêng license model |
| License Included cho phép mọi option Oracle | Chỉ dùng trong phạm vi quyền của gói và điều khoản tương ứng |
| Enterprise Edition tự bao gồm mọi quyền cho mọi nơi triển khai | Phải kiểm tra option, pack và khác biệt IaaS/PaaS |
| ECPU và OCPU có thể thay trực tiếp bằng nhau | Phải xác định đúng compute model và quy tắc ánh xạ |
| CPU trung bình thấp thì luôn chỉ cần quyền cho mức trung bình | Phải áp dụng metric và điều kiện đo đúng dịch vụ/hợp đồng |
| Có license primary là mọi clone và standby được bao phủ | Phải tính cả các triển khai và giai đoạn sử dụng liên quan |
| Có backup tự động thì không cần chủ nhiệm phục hồi | Vẫn cần quyết định restore, điều phối và xác minh nghiệp vụ |
| Dừng database là không còn khoản chi phí nào | Phải kiểm tra compute, storage, backup, support và các khoản còn tồn tại |
| Tự động hóa thành công chứng minh toàn bộ thiết kế hợp lệ | Automation chỉ thực hiện cấu hình; vẫn cần bằng chứng về quyền và vận hành |

Một thiết kế sẵn sàng triển khai phải nối được ba phần: cấu hình dịch vụ thực tế, quyền phần mềm có căn cứ và danh sách công việc có người chịu trách nhiệm. Khi một phần chưa được xác nhận, ghi rõ phần còn thiếu trước khi mở rộng phạm vi sử dụng.
