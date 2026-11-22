# Lựa chọn region theo độ trễ, dữ liệu và dịch vụ hỗ trợ

Một nhóm chuẩn bị đưa ứng dụng đặt hàng lên Oracle Cloud Infrastructure (OCI). Người dùng chủ yếu ở Việt Nam, ứng dụng cần cơ sở dữ liệu Oracle, dữ liệu đơn hàng phải tuân theo phạm vi lưu trữ đã thống nhất với khách hàng và hệ thống phải có phương án phục hồi khi xảy ra sự cố lớn. Chọn region chỉ vì nhìn gần nhất trên bản đồ chưa giải quyết được những yêu cầu này.

Region ảnh hưởng đến đường đi của yêu cầu, vị trí dữ liệu và khả năng sử dụng dịch vụ. Một lựa chọn phù hợp cần vượt qua các điều kiện bắt buộc trước, sau đó mới được so sánh bằng độ trễ đo thực tế, chi phí và khả năng vận hành.

Trong chương **Tổng quan Oracle Cloud Infrastructure** của **CLOUD_PROVIDERS_ORACLE**, bài học này kết nối quyết định chọn region với việc triển khai VCN, Compute, lưu trữ và dịch vụ cơ sở dữ liệu Oracle. Kết quả cần hướng tới là một quyết định có bằng chứng, có thể đưa vào cấu hình tự động hóa và phù hợp với cách tổ chức kiểm soát quyền, giám sát, chi phí và tính sẵn sàng.

## 1. Hiểu đúng phạm vi của quyết định chọn region

Region là một khu vực địa lý OCI dùng để triển khai tài nguyên và dịch vụ. Bên trong region có availability domain và fault domain phục vụ các cách tổ chức hạ tầng và chịu lỗi. Chọn region khác với chọn vị trí tài nguyên bên trong region; hai quyết định cần được kiểm tra riêng theo kiến trúc của dịch vụ. Xem [Regions and Availability Domains](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm).

| Khái niệm | Ý nghĩa trong quyết định |
| --- | --- |
| Region triển khai workload | Nơi đặt tài nguyên ứng dụng, dữ liệu hoặc một phần hệ thống |
| Home region | Region gắn với việc khởi tạo tenancy và các hoạt động quản trị IAM liên quan |
| Region đã đăng ký | Region mà tenancy đã được kích hoạt quyền sử dụng, trong giới hạn tài khoản |
| Compartment | Phạm vi tổ chức và quản trị tài nguyên; không thay thế region |
| Realm | Nhóm region thuộc một phạm vi OCI được cô lập với realm khác |
| Region dự phòng | Region được chọn và cấu hình để hỗ trợ mục tiêu phục hồi của hệ thống |

Home region không bắt buộc là nơi đặt mọi workload. Tuy nhiên, đây là lựa chọn cần xem xét từ khi tạo tài khoản vì không thể đổi home region sau khi tenancy đã được khởi tạo. Các hoạt động IAM tương ứng được quản lý qua home region; không nên xem việc đổi bộ lọc region là cách đổi vị trí quản trị này. Xem [Managing Regions](https://docs.oracle.com/en-us/iaas/Content/Identity/regions/managingregions.htm).

Tenancy tồn tại trong một realm và truy cập các region thuộc realm đó. Region thương mại, region dành cho chính phủ hoặc các mô hình sovereign không phải những lựa chọn luôn có thể chuyển qua lại trong cùng tenancy. Cần xác định loại môi trường và điều kiện truy cập ngay từ đầu. Xem mục realm trong [OCI Glossary](https://docs.oracle.com/en-us/iaas/Content/libraries/glossary/glossary-intro.htm).

Khi đổi region trên Console, người dùng đổi góc nhìn đối với các tài nguyên có phạm vi region; tài nguyên cũ không tự di chuyển sang region mới. Nếu không thấy instance hoặc bucket dự kiến, kiểm tra region, compartment và quyền trước khi tạo lại tài nguyên. Xem [Working in Regions](https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/working-with-regions.htm).

## 2. Tách điều kiện bắt buộc khỏi tiêu chí so sánh

Một sai lầm phổ biến là chấm điểm mọi tiêu chí rồi chọn region có tổng điểm cao nhất. Cách đó có thể khiến độ trễ tốt hoặc chi phí thấp bù cho việc không đáp ứng yêu cầu dữ liệu hoặc thiếu dịch vụ cốt lõi.

Nên thực hiện hai bước:

1. **Lọc điều kiện bắt buộc:** loại những phương án không đáp ứng yêu cầu không được phép đánh đổi.
2. **So sánh phương án hợp lệ:** đánh giá độ trễ, vận hành, chi phí và khả năng mở rộng trên cùng cơ sở đo.

| Nhóm yêu cầu | Câu hỏi cần trả lời | Cách xử lý |
| --- | --- | --- |
| Phạm vi dữ liệu | Các loại dữ liệu được lưu và xử lý tại đâu? | Điều kiện bắt buộc theo yêu cầu đã phê duyệt |
| Dịch vụ | Region có đúng dịch vụ, chế độ triển khai và tính năng cần dùng không? | Điều kiện bắt buộc nếu kiến trúc không có phương án thay thế |
| Tài khoản và kết nối | Tenancy có thể dùng region, có đường kết nối và quyền cần thiết không? | Kiểm tra khả năng triển khai |
| Mục tiêu hiệu năng | Luồng nghiệp vụ có đáp ứng ngưỡng thời gian đã thống nhất không? | Ngưỡng tối thiểu trước, tối ưu thêm sau |
| Phục hồi | Có phương án đáp ứng mục tiêu dữ liệu và thời gian khôi phục không? | Điều kiện kiến trúc nếu nghiệp vụ yêu cầu |
| Chi phí và vận hành | Phương án cần bao nhiêu nguồn lực để chạy ổn định? | So sánh giữa các phương án còn lại |

Ví dụ, nếu hợp đồng của một dự án giả định chỉ cho phép lưu dữ liệu giao dịch trong một phạm vi địa lý xác định, region ngoài phạm vi đó phải được loại khỏi thiết kế lưu dữ liệu giao dịch. Không thể dùng điểm độ trễ cao hơn để làm điều kiện này biến mất.

Nếu không còn phương án hợp lệ, cần xem lại yêu cầu, cách triển khai hoặc dịch vụ thay thế với người có thẩm quyền quyết định. Không tự nới điều kiện dữ liệu hoặc tự thay dịch vụ cơ sở dữ liệu chỉ để hoàn thành bảng so sánh.

## 3. Đánh giá độ trễ theo đường đi của nghiệp vụ

### 3.1. Đo đúng cặp nguồn và đích

Độ trễ có ý nghĩa khi biết rõ phép đo bắt đầu ở đâu, kết thúc ở đâu và đi qua đường kết nối nào.

```text
Người dùng
    │ Internet, DNS, TLS
    ▼
Điểm vào ứng dụng ở region A
    │ Gọi dịch vụ nội bộ
    ▼
Dịch vụ xử lý
    │ Truy vấn cơ sở dữ liệu
    ▼
Cơ sở dữ liệu ở region A hoặc region B
```

Có ít nhất ba câu hỏi khác nhau:

- Người dùng ở Hà Nội hoặc Thành phố Hồ Chí Minh truy cập ứng dụng mất bao lâu?
- Ứng dụng kết nối đến cơ sở dữ liệu, hệ thống tại chỗ hoặc đối tác mất bao lâu?
- Hai region trao đổi dữ liệu phục vụ sao chép hoặc phục hồi mất bao lâu?

Một kết quả tốt cho câu hỏi thứ ba chưa trả lời được hai câu hỏi đầu. Máy đo đặt trong một OCI region cũng không đại diện cho điện thoại của khách hàng trên mạng di động.

Khoảng cách địa lý giúp lập danh sách ứng viên ban đầu. Đường định tuyến, nhà mạng, kết nối doanh nghiệp, proxy và các thành phần trung gian mới quyết định đường đi thực tế. Vì vậy, “gần Việt Nam hơn” là một giả thuyết cần kiểm chứng bằng phép đo từ các nguồn truy cập đại diện.

### 3.2. Nhận ra tác động của nhiều lần trao đổi tuần tự

Giả sử một thao tác tạo đơn hàng cần tám lần trao đổi tuần tự với một phụ thuộc ở xa. Trong mô hình đơn giản, nếu mỗi vòng trao đổi chịu thêm 25 ms thì phần thời gian tăng thêm có thể xấp xỉ:

```text
8 vòng trao đổi × 25 ms/vòng = 200 ms
```

Đây là minh họa cho chi phí của độ trễ tích lũy, không phải công thức dự báo chính xác mọi giao dịch. Các lời gọi có thể chạy song song, sử dụng cache hoặc connection pool; truy vấn còn có thời gian thực thi riêng.

Hệ quả thiết kế là không nên chỉ đặt tầng ứng dụng gần người dùng rồi mặc định để cơ sở dữ liệu ở xa. Với ứng dụng giao dịch có nhiều lượt gọi qua lại, đường ứng dụng → dữ liệu có thể quan trọng hơn phần độ trễ tiết kiệm được ở đường người dùng → ứng dụng.

Các cách giảm ảnh hưởng có thể gồm giảm số lần gọi tuần tự, gộp truy vấn phù hợp, cache dữ liệu được phép cache và đặt các tầng tương tác thường xuyên gần nhau. Mỗi cách đều cần kiểm tra tính nhất quán và yêu cầu dữ liệu của nghiệp vụ.

### 3.3. Chọn số đo phù hợp

| Số đo | Cho biết điều gì? | Hạn chế cần nhớ |
| --- | --- | --- |
| RTT | Thời gian trao đổi khứ hồi trên đường được đo | Không bao gồm toàn bộ xử lý nghiệp vụ |
| TTFB | Thời gian tới byte đầu tiên của phản hồi | Phụ thuộc cả kết nối, máy chủ và đường phản hồi |
| Thời gian phản hồi toàn bộ | Thời gian hoàn tất yêu cầu ở phía đo | Bị ảnh hưởng bởi kích thước dữ liệu và cách tải |
| P50 | Mức trung vị của các mẫu | Không thể hiện đầy đủ trải nghiệm của nhóm chậm |
| P95 | Mốc mà khoảng 95% mẫu không vượt quá | Phải đọc cùng số mẫu, cách lấy mẫu và tỷ lệ lỗi |
| Tỷ lệ lỗi, timeout | Mức độ yêu cầu không hoàn tất đúng kỳ vọng | Không được loại bỏ âm thầm để bảng độ trễ trông tốt hơn |

Không cộng các giá trị P95 riêng của từng tầng để gọi đó là P95 của toàn giao dịch. Phân vị của tổng thời gian phụ thuộc cách các thành phần cùng xuất hiện trong từng yêu cầu. Muốn biết P95 nghiệp vụ, cần đo chính luồng nghiệp vụ đó.

Nên đo vào nhiều khung giờ, từ các nhóm người dùng và nhà mạng quan trọng. Tách phép đo kết nối mới khỏi kết nối đã được tái sử dụng; ứng dụng có connection pool có thể hành xử khác một lệnh thử đơn lẻ.

### 3.4. Dùng công cụ OCI đúng mục đích

OCI có bảng **Inter-Region Latency** cung cấp RTT trung bình giữa các cặp region trong một realm. Đây là số liệu tổng quan để lập kế hoạch trao đổi dữ liệu giữa region, không phải phép đo riêng cho workload hoặc đường Internet của khách hàng. Xem [Inter-Region Latency](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/inter_region_latency.htm).

Có thể dùng bảng đó để sàng lọc cặp region cho backup hoặc replication. Sau đó vẫn cần kiểm thử đường truyền thực tế, khối lượng dữ liệu, dịch vụ sao chép và thời gian phục hồi của ứng dụng.

CDN hoặc cache ở gần người dùng có thể cải thiện nội dung được cache. Không nên lấy tốc độ tải ảnh tĩnh qua cache để kết luận một giao dịch ghi dữ liệu ở origin đã đủ nhanh.

## 4. Xác định toàn bộ phạm vi dữ liệu

### 4.1. Lập bản đồ dữ liệu trước khi chốt region

Yêu cầu về nơi lưu trữ và xử lý dữ liệu phải được làm rõ cùng chủ sở hữu dữ liệu, bộ phận phụ trách hợp đồng và quản trị của tổ chức. Tài liệu lập kế hoạch của Oracle cũng yêu cầu cân nhắc vị trí người dùng, yêu cầu riêng tư dữ liệu và các region được dịch vụ hỗ trợ. Xem [Planning an Applications Environment](https://docs.oracle.com/en-us/iaas/Content/applications-manager/plan-apps-environment.htm).

Một bản đồ dữ liệu nên bao gồm:

| Thành phần | Cần xác định |
| --- | --- |
| Cơ sở dữ liệu chính | Loại dữ liệu, nơi ghi và xử lý, người được truy cập |
| Object Storage hoặc File Storage | Tệp gốc, tệp xuất, tài liệu tải lên và nơi lưu |
| Backup và snapshot | Vị trí, thời gian lưu, quyền phục hồi và xóa |
| Replica hoặc standby | Region đích, loại dữ liệu được sao chép và độ trễ sao chép |
| Log và trace | Có chứa định danh, nội dung yêu cầu hoặc dữ liệu nhạy cảm không? |
| Khóa và bí mật | Dịch vụ quản lý khóa, phạm vi dùng khóa và phụ thuộc phục hồi |
| Hệ thống bên ngoài OCI | Analytics, email, thanh toán, giám sát hoặc công cụ hỗ trợ |
| Dữ liệu quản trị liên quan | Cấu hình tài khoản, danh tính và thông tin vận hành cần đánh giá riêng |

Phạm vi dữ liệu không chỉ gồm bảng trong cơ sở dữ liệu production. Một bản backup ở region khác hoặc một trace chứa nội dung yêu cầu cũng có thể đưa thông tin ra khỏi phạm vi đã thống nhất.

Ví dụ, nhóm đặt database trong vùng địa lý được duyệt nhưng cấu hình job xuất dữ liệu mỗi đêm sang bucket ngoài vùng đó. Việc chọn region của database đúng chưa đủ để chứng minh luồng dữ liệu tổng thể đáp ứng yêu cầu.

### 4.2. Phân biệt các loại yêu cầu

- **Nơi lưu dữ liệu:** dữ liệu được giữ ở những vị trí nào, gồm cả bản sao.
- **Nơi xử lý dữ liệu:** dịch vụ nào đọc, biến đổi hoặc phân tích dữ liệu, tại đâu.
- **Quyền truy cập và vận hành:** ai có thể truy cập, theo cơ chế và điều kiện nào.
- **Yêu cầu chủ quyền hoặc mô hình triển khai:** các điều kiện bổ sung về phạm vi quản trị, môi trường và cam kết áp dụng.

Các yêu cầu này liên quan nhưng không thay thế nhau. Mã hóa dữ liệu không tự làm thay đổi vị trí dữ liệu; chọn một region cũng không tự xác định ai được truy cập. Cần kiểm tra cả cấu hình dịch vụ, IAM, đường xuất dữ liệu và các cam kết áp dụng cho mô hình triển khai đã chọn.

Nếu dùng sovereign hoặc government cloud, phải xem đúng tài liệu và điều kiện của môi trường đó. Không suy ra rằng một region thương mại nằm trong cùng quốc gia sẽ có đầy đủ đặc điểm quản trị của một môi trường sovereign.

### 4.3. Giải quyết mâu thuẫn giữa dữ liệu và hiệu năng

Giả sử người dùng ở nhiều quốc gia nhưng dữ liệu giao dịch chỉ được lưu trong một phạm vi đã duyệt. Các hướng xem xét có thể gồm:

1. Giữ xử lý giao dịch và dữ liệu nhạy cảm tại region hợp lệ.
2. Phục vụ nội dung công khai qua cache nếu chính sách cho phép.
3. Giảm số lời gọi đồng bộ đến nơi lưu dữ liệu.
4. Chỉ dùng dữ liệu đã được xử lý phù hợp tại nơi khác sau khi có đánh giá và chấp thuận.
5. Đánh giá lại trải nghiệm hoặc yêu cầu nghiệp vụ nếu không đạt mục tiêu.

Không mặc định triển khai replica ở mọi nơi người dùng sinh sống. Replica giúp phục vụ một số luồng đọc hoặc phục hồi nhưng đồng thời tạo thêm bản sao dữ liệu và trách nhiệm quản trị.

## 5. Kiểm tra dịch vụ được hỗ trợ tới mức tính năng

### 5.1. “Có dịch vụ” chưa đủ cho quyết định triển khai

Oracle công bố thông tin service availability theo region và lưu ý khả năng cung cấp có thể thay đổi; một số SKU hoặc dịch vụ chuyên biệt không có ở mọi region. Vì vậy, phải kiểm tra danh mục hiện hành cùng tài liệu của dịch vụ cụ thể. Xem [Service Availability](https://www.oracle.com/cloud/distributed-cloud/service-availability/).

Với ứng dụng dùng Oracle Database, không nên dừng ở câu “region này có database”. Cần ghi rõ loại dịch vụ đã chọn, chế độ triển khai, tính năng bảo mật, kết nối và phục hồi thực sự cần dùng.

| Thành phần | Nội dung cần xác minh tại mỗi region ứng viên |
| --- | --- |
| Compute | Shape, kiến trúc CPU, yêu cầu GPU hoặc phần cứng đặc thù nếu có |
| Cơ sở dữ liệu Oracle | Dịch vụ, phiên bản hoặc chế độ được hỗ trợ, khả năng phục hồi cần thiết |
| VCN và kết nối | Private endpoint, VPN, FastConnect hoặc kết nối đối tác theo thiết kế |
| Lưu trữ | Loại lưu trữ, backup, copy hoặc replication được hỗ trợ |
| Bảo mật | Cách dùng khóa, bí mật và khả năng đáp ứng yêu cầu bảo vệ |
| Giám sát | Metric, log, cảnh báo và cách thu thập bằng chứng vận hành |
| Tích hợp | Dịch vụ đối tác và cặp địa điểm kết nối tương ứng |

Không dùng trạng thái planned hoặc preview để chứng minh một phụ thuộc bắt buộc của hệ thống production đã sẵn sàng. Ghi lại thời điểm kiểm tra và điều kiện sử dụng của tính năng.

### 5.2. Phân biệt hỗ trợ, hạn mức và capacity

Ba câu hỏi sau độc lập với nhau:

1. Dịch vụ hoặc cấu hình có được hỗ trợ ở region không?
2. Tenancy có đủ service limit và compartment quota để yêu cầu tài nguyên không?
3. Tại thời điểm cấp phát, hạ tầng có đủ capacity cho cấu hình đó không?

Một shape có trong danh mục và còn hạn mức vẫn có thể không cấp phát được vì thiếu host capacity. OCI phân biệt service limit với khả năng sẵn có của hạ tầng vật lý. Xem [Overview of the Compute Service](https://docs.oracle.com/en-us/iaas/Content/Compute/Concepts/computeoverview.htm).

Capacity còn phụ thuộc shape và vị trí cấp phát cụ thể, đồng thời thay đổi theo thời gian. Bằng chứng thử tạo thành công hôm nay không phải cam kết rằng mọi đợt mở rộng sau này đều thành công. Xem [Resolving Out of Host Capacity error](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-out-of-host-capacity.htm).

Với cấu hình quan trọng, cần đánh giá phương án dự phòng tương thích và cơ chế bảo đảm capacity nếu dịch vụ hỗ trợ. Không tự đổi kiến trúc CPU, loại database hoặc region ngoài phạm vi dữ liệu chỉ để xử lý một lần cấp phát thất bại.

### 5.3. Kiểm tra khả năng sử dụng từ tenancy hiện tại

Region có trong danh mục OCI chưa đồng nghĩa tenancy đã đăng ký sử dụng region đó. Khả năng đăng ký thêm còn phụ thuộc loại tài khoản, giới hạn và điều kiện áp dụng.

Việc đăng ký region là ở cấp tenancy. OCI lưu ý không thể hủy đăng ký region sau đó; vì vậy, bước tìm hiểu ban đầu nên bắt đầu bằng truy vấn danh sách và kiểm tra điều kiện. Xem [Subscribing to an Infrastructure Region](https://docs.oracle.com/en-us/iaas/Content/Identity/regions/To_subscribe_to_an_infrastructure_region.htm).

Nếu học trên Free Tier, cần đối chiếu điều kiện của từng loại tài nguyên trước khi chọn region thực hành. Chẳng hạn, tài liệu Always Free quy định Compute đủ điều kiện Always Free phải được tạo trong home region. Không suy ra mọi region trong danh mục đều phù hợp để chạy lab miễn phí. Xem [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

## 6. Chọn region chính cùng với phương án phục hồi

Nếu nghiệp vụ cần chịu được sự cố ở cấp region, lựa chọn ban đầu phải xét cả nơi chạy chính và nơi có thể phục hồi. Một region thứ hai chưa tự tạo thành giải pháp disaster recovery.

Hai mục tiêu cơ bản:

- **RPO:** mức mất dữ liệu tối đa chấp nhận được, thường biểu diễn bằng khoảng thời gian.
- **RTO:** thời gian gián đoạn tối đa mục tiêu trước khi dịch vụ được phục hồi.

Đây là mục tiêu thiết kế cần kiểm chứng bằng diễn tập, không phải kết quả tự có khi chọn hai region. Xem [Full Stack Disaster Recovery Terminology and Concepts](https://docs.oracle.com/en-us/iaas/disaster-recovery/doc/disaster-recovery-terminology.html).

Khi đánh giá region dự phòng, kiểm tra:

| Nội dung | Câu hỏi thực tế |
| --- | --- |
| Dữ liệu | Region dự phòng có nằm trong phạm vi được phép không? |
| Dịch vụ | Có đủ các thành phần để chạy phiên bản phục hồi không? |
| Sao chép | Cơ chế của dịch vụ có hỗ trợ cặp region và cấu hình đã chọn không? |
| Năng lực | Có thể cấp phát hoặc duy trì tài nguyên cần thiết khi chuyển vùng không? |
| Kết nối | Người dùng và hệ thống tại chỗ có đường đến nơi phục hồi không? |
| Danh tính, khóa và bí mật | Khi nơi chính gặp sự cố, các phụ thuộc này còn dùng được không? |
| Vận hành | Ai kích hoạt phục hồi, kiểm tra dữ liệu và đưa hệ thống trở lại? |

Độ trễ giữa region có thể ảnh hưởng khả năng sao chép và lựa chọn cơ chế đồng bộ hoặc bất đồng bộ. Cơ chế phù hợp còn tùy dịch vụ, khoảng cách và yêu cầu dữ liệu; không giả định mọi cặp region đều hỗ trợ cùng một kiểu replication.

RTO của ứng dụng còn bao gồm thời gian phát hiện, ra quyết định, khôi phục dữ liệu, khởi động phụ thuộc và chuyển truy cập. Backup có mặt ở region dự phòng mới giải quyết một phần bài toán. Xem [Disaster Recovery](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/disaster-recovery.htm).

Nếu dự án chỉ cần phục hồi trong cùng region, cần ghi rõ phạm vi sự cố đã chấp nhận. Không gọi một bản sao ở availability domain khác là bằng chứng đã chịu được mọi sự cố toàn region.

## 7. So sánh chi phí và khả năng vận hành

Không quyết định region từ một dòng giá Compute. Ngay cả khi đơn giá của các SKU tương đương, kiến trúc kết nối, lượng bản sao và cách vận hành vẫn làm tổng chi phí khác nhau.

Một mô hình ước tính có thể gồm:

```text
Chi phí vận hành phương án
  = Compute và dịch vụ cơ sở dữ liệu
  + Lưu trữ chính và backup
  + Dịch vụ mạng, kết nối và cân bằng tải
  + Truyền dữ liệu nếu có phí áp dụng
  + Tài nguyên phục hồi hoặc dự phòng
  + Công sức vận hành và diễn tập
```

Đây là mô hình so sánh nội bộ, không phải công thức tính hóa đơn OCI. Cần đối chiếu SKU, hợp đồng, mức sử dụng và biểu phí hiện hành; tránh đếm hai lần cùng khoản truyền dữ liệu.

Ví dụ, đặt ứng dụng ở region A nhưng gọi database tại region B có thể tăng số lần trao đổi, lượng dữ liệu đi giữa region và độ phức tạp xử lý sự cố. Phương án nhìn rẻ hơn ở một tài nguyên đơn lẻ có thể đắt hơn khi xét cả luồng nghiệp vụ.

Khả năng vận hành cũng cần bằng chứng: đội ngũ có thể quan sát lỗi tại đâu, triển khai bản sửa bằng pipeline nào, liên hệ hỗ trợ ra sao và duy trì phụ thuộc khi một nơi bị gián đoạn. Thời gian làm việc thuận tiện chỉ là một yếu tố; không thay thế quyền truy cập, công cụ và quy trình đã kiểm thử.

## 8. Ví dụ ra quyết định với ba region giả định

Toàn bộ dữ liệu và tên A, B, C dưới đây là **giả định để học cách đánh giá**, không phải số đo hoặc công bố khả năng cung cấp của region OCI cụ thể.

Một ứng dụng có các yêu cầu:

- Dữ liệu và bản sao chỉ được đặt trong phạm vi địa lý đã duyệt của dự án.
- Phải có đúng dịch vụ cơ sở dữ liệu Oracle và cơ chế backup đã chọn.
- P95 của thao tác đặt hàng từ nhóm người dùng chính không vượt quá 400 ms.
- Phải có phương án phục hồi đáp ứng RPO/RTO đã thống nhất.

### 8.1. Lọc điều kiện bắt buộc

| Kiểm tra | Region A | Region B | Region C |
| --- | --- | --- | --- |
| Phạm vi dữ liệu đã duyệt | Đạt | Đạt | Không đạt |
| Dịch vụ và tính năng bắt buộc | Đạt | Đạt | Đạt |
| Khả năng sử dụng từ tenancy | Đạt | Đạt | Đạt |
| P95 nghiệp vụ trong thử nghiệm | 225 ms | 280 ms | 170 ms |
| Phương án phục hồi khả thi | Đạt, cần hoàn thiện diễn tập | Đạt, đã có bằng chứng diễn tập | Không xét tiếp |
| Kết quả | Giữ lại | Giữ lại | Loại |

C có thời gian phản hồi thấp nhất nhưng không đáp ứng yêu cầu dữ liệu, nên không tham gia chấm điểm. A và B đều vượt qua ngưỡng hiệu năng 400 ms; lúc này có thể đánh đổi mức tối ưu độ trễ với chất lượng vận hành.

### 8.2. Chấm điểm các phương án hợp lệ

Nhóm thống nhất trọng số và thang 1–5 trước khi tổng hợp kết quả. Riêng độ trễ, quy ước minh họa là P95 không quá 250 ms được 5 điểm, trên 250 đến 300 ms được 4 điểm. Các mức chậm hơn vẫn phải xét ngưỡng bắt buộc trước.

Điểm vận hành phản ánh mức hoàn thiện của bằng chứng và diễn tập; điểm chi phí phản ánh tổng phương án, không chỉ một SKU. Điểm mở rộng đánh giá mức chuẩn bị và phương án thay thế đã kiểm tra, không phải lời bảo đảm capacity tương lai.

| Tiêu chí | Trọng số | Điểm A | Điểm B |
| --- | --- | --- | --- |
| Độ trễ nghiệp vụ | 40% | 5 | 4 |
| Mức sẵn sàng vận hành và phục hồi | 30% | 3 | 5 |
| Tổng chi phí phương án | 20% | 3 | 4 |
| Bằng chứng chuẩn bị mở rộng | 10% | 3 | 4 |
| Tổng điểm có trọng số | 100% | 3,80 | 4,30 |

```text
Điểm A = 5 × 0,40 + 3 × 0,30 + 3 × 0,20 + 3 × 0,10 = 3,80
Điểm B = 4 × 0,40 + 5 × 0,30 + 4 × 0,20 + 4 × 0,10 = 4,30
```

Theo tiêu chí đã thống nhất, B là phương án ưu tiên dù chậm hơn A trong thử nghiệm. Đây là kết luận cho bộ yêu cầu giả định này. Nếu nghiệp vụ đổi ngưỡng P95 thành 250 ms, B không còn đạt điều kiện bắt buộc và phải được đánh giá lại.

Một bảng điểm không thay thế bằng chứng. Mỗi điểm nên liên kết với kết quả thử nghiệm, ước tính hoặc tài liệu đã kiểm tra; chênh lệch nhỏ hơn mức bất định của dữ liệu là lý do cần đo thêm.

## 9. Thực hành thu thập bằng chứng

### 9.1. Kiểm tra region bằng OCI CLI

Chuẩn bị OCI CLI đã xác thực và tài khoản có quyền đọc thông tin cần thiết. Các lệnh sau chỉ truy vấn; không đăng ký region và không tạo tài nguyên.

```powershell
# Danh sách region mà API trả về trong realm đang dùng.
oci iam region list --output table

# Các region tenancy đã đăng ký.
# Thay placeholder bằng OCID tenancy được phép kiểm tra.
oci iam region-subscription list `
    --tenancy-id '<TENANCY_OCID>' `
    --all `
    --output json
```

Trong kết quả region subscription, chú ý các trường:

| Trường | Ý nghĩa cần ghi nhận |
| --- | --- |
| `region-name` | Định danh region dùng khi cấu hình triển khai |
| `region-key` | Mã ngắn tương ứng của region |
| `is-home-region` | Region có phải home region của tenancy không |
| `status` | Trạng thái đăng ký; cần kiểm tra đã sẵn sàng trước khi dùng |

Danh sách đăng ký không phải danh sách tài nguyên đang có ở từng region và không chứng minh mọi dịch vụ đều triển khai được. Tham khảo [OCI CLI: region-subscription list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/region-subscription/list.html) và [Region Subscription](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/region-subscription.html).

### 9.2. Đo một endpoint thử nghiệm đại diện

Dùng hai môi trường thử nghiệm có cùng phiên bản ứng dụng, cấu hình tài nguyên và dữ liệu giả lập tương đương. Mỗi endpoint phải thực sự dẫn đến region đang đánh giá. Nếu cả hai tên miền cùng đi qua một cache và trả cùng nội dung đã cache, phép so sánh có thể đang đo lớp cache thay vì ứng dụng.

Ví dụ PowerShell dưới đây dùng `curl.exe` trên Windows. Thay URL mẫu bằng endpoint HTTPS được phép kiểm tra của chính môi trường thử nghiệm:

```powershell
$TargetUrl = 'https://replace-with-your-test-host.example/health'

curl.exe --silent --show-error `
    --connect-timeout 5 `
    --max-time 15 `
    --output NUL `
    --write-out 'http=%{http_code} dns=%{time_namelookup}s connect=%{time_connect}s tls=%{time_appconnect}s ttfb=%{time_starttransfer}s total=%{time_total}s\n' `
    $TargetUrl

$CurlExitCode = $LASTEXITCODE
$CurlExitCode
```

Các mốc thời gian của curl được tính từ lúc bắt đầu yêu cầu, không phải những khoảng độc lập để cộng lại. Chẳng hạn, `time_starttransfer` đã chứa thời gian chuẩn bị kết nối và chờ byte đầu tiên. Đọc định nghĩa tại [curl man page: write-out](https://curl.se/docs/manpage.html#-w).

Ghi cả mã HTTP và exit code. Một phản hồi HTTP lỗi nhanh không phải giao dịch thành công nhanh. curl có thể hoàn tất truyền HTTP mà vẫn nhận mã lỗi từ máy chủ, nên exit code bằng 0 riêng lẻ chưa đủ kết luận ứng dụng khỏe.

Endpoint health chỉ giúp khảo sát bước đầu. Nó không thay thế phép đo đặt hàng, tải tệp hoặc truy vấn dữ liệu thật của bài toán. Mỗi lần chạy curl riêng là một lần chạy công cụ riêng; cần kiểm thử thêm hành vi kết nối được tái sử dụng của ứng dụng nếu đó là cách production hoạt động.

### 9.3. Lập kế hoạch đo có thể so sánh

Một đợt thử nghiệm nên ghi lại:

- Region, endpoint, phiên bản ứng dụng và cấu hình từng môi trường.
- Vị trí máy đo, loại mạng, proxy/VPN và thời điểm đo.
- Luồng nghiệp vụ, dữ liệu thử và trạng thái cache.
- Số yêu cầu, mức đồng thời, kết quả thành công và timeout.
- P50, P95 và tỷ lệ lỗi cho từng nhóm nguồn truy cập.
- Dấu vết phía máy chủ để phân biệt mạng, chờ tài nguyên và thời gian truy vấn.

Bắt đầu với lưu lượng thấp đã được cho phép, sau đó tăng theo kế hoạch kiểm thử của dự án. Không gửi tải lớn đến endpoint sản xuất chỉ để tìm P95.

Để minh họa cách tính P95 theo phương pháp nearest-rank, nếu có 100 mẫu thành công đã sắp xếp tăng dần thì lấy mẫu ở vị trí `ceil(0,95 × 100) = 95`, với vị trí bắt đầu từ 1. Luôn báo cáo riêng số lỗi và timeout; không xóa chúng khỏi kết luận chỉ vì không có thời gian phản hồi thành công.

Nếu một region có 100 yêu cầu nhưng 20 timeout, P95 của 80 phản hồi thành công không mô tả đầy đủ độ tin cậy của phương án đó. Khi số mẫu ít hoặc khác biệt nhỏ, tiếp tục đo trong các điều kiện đại diện trước khi kết luận.

## 10. Ghi lại quyết định và đưa vào triển khai

Kết quả chọn region nên là một hồ sơ quyết định ngắn, đủ để người triển khai không phải tự đoán lại:

| Nội dung | Bằng chứng hoặc kết quả cần lưu |
| --- | --- |
| Yêu cầu bắt buộc | Phạm vi dữ liệu, dịch vụ, hiệu năng và phục hồi đã được chấp thuận |
| Danh sách ứng viên | Tên/định danh region, realm và trạng thái đăng ký |
| Phương án bị loại | Lý do cụ thể, không chỉ ghi “không phù hợp” |
| Kết quả đo | Nguồn đo, khung giờ, workload, phân vị và tỷ lệ lỗi |
| Kiểm tra dịch vụ | Tính năng, cấu hình và nguồn tài liệu tại thời điểm đánh giá |
| Khả năng cấp phát | Hạn mức, quota, bằng chứng thử nghiệm và phương án mở rộng |
| Luồng dữ liệu | Vị trí dữ liệu chính, backup, replica, log và hệ thống ngoài |
| Phương án được chọn | Region chính, phạm vi phục hồi và các đánh đổi |
| Chi phí | Giả định sử dụng, các khoản tính vào ước tính và mức bất định |
| Chủ sở hữu | Người quyết định, người triển khai và người kiểm tra lại |

Sau khi quyết định, đưa region vào cấu hình triển khai một cách tường minh. Pipeline cần biết region đích, compartment đích và endpoint dịch vụ tương ứng; việc người dùng đang nhìn một region trên Console không quyết định đích của mọi công cụ CLI hoặc Infrastructure as Code.

Kiểm tra lại quyết định khi xuất hiện thay đổi có ý nghĩa: nhóm người dùng mới, yêu cầu dữ liệu mới, dịch vụ hoặc tính năng mới, thay đổi kiến trúc database, lượng dữ liệu tăng mạnh hoặc mục tiêu phục hồi thay đổi. Ngày kiểm tra nguồn tài liệu và kết quả đo giúp phân biệt bằng chứng còn phù hợp với giả định đã cũ.

## 11. Những sai lầm cần tránh

| Sai lầm | Hệ quả | Cách điều chỉnh |
| --- | --- | --- |
| Chọn region gần nhất trên bản đồ | Bỏ qua định tuyến và đường tới dữ liệu | Đo từ nguồn truy cập đại diện và theo luồng nghiệp vụ |
| Dùng RTT giữa region làm độ trễ khách hàng | So sánh sai đường truyền | Tách phép đo người dùng, phụ thuộc và replication |
| Chỉ nhìn trung bình hoặc P50 | Bỏ sót trải nghiệm của nhóm chậm | Đọc thêm P95, timeout và lỗi |
| Chỉ xét database chính khi đánh giá dữ liệu | Backup, log hoặc công cụ ngoài đưa dữ liệu ra nơi khác | Lập bản đồ toàn bộ bản sao và đường xuất dữ liệu |
| Thấy tên dịch vụ là cho rằng đủ tính năng | Thiếu cấu hình hoặc cơ chế phục hồi cần dùng | Kiểm tra dịch vụ tới chế độ triển khai và tính năng |
| Còn quota nên cho rằng chắc chắn cấp phát được | Bất ngờ khi thiếu capacity | Tách hỗ trợ, hạn mức và capacity trong đánh giá |
| Đăng ký hai region rồi cho rằng đã có DR | Không khôi phục được ứng dụng khi sự cố | Thiết kế và diễn tập với RPO/RTO cụ thể |
| Chấm điểm để bù một điều kiện bắt buộc bị vi phạm | Chọn phương án không đáp ứng yêu cầu | Lọc điều kiện trước khi chấm điểm |
| Đổi region trên Console rồi tạo lại tài nguyên | Dễ tạo trùng hoặc phát sinh chi phí | Kiểm tra đúng region, compartment và quyền trước |
| Chọn theo điều kiện miễn phí nhưng không kiểm tra phạm vi | Lab không triển khai được hoặc không đúng điều kiện miễn phí | Đối chiếu quy định của tài khoản và từng loại tài nguyên |

Region phù hợp là nơi hệ thống có thể vận hành với hiệu năng chấp nhận được, luồng dữ liệu đúng yêu cầu và dịch vụ đủ khả năng phục vụ kiến trúc đã chọn. Quyết định đó cần được chứng minh bằng cùng một bộ yêu cầu, kết quả kiểm thử và thông tin dịch vụ được kiểm tra tại thời điểm triển khai.
