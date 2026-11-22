# Đám mây công cộng, riêng và lai: điều kiện lựa chọn

## 1. Chọn mô hình triển khai là một quyết định kiến trúc

Khi thiết kế hệ thống trên đám mây, câu hỏi không chỉ là "đưa ứng dụng lên cloud nào?" mà là **nên đặt từng workload, dữ liệu và trách nhiệm vận hành ở đâu** để đáp ứng yêu cầu nghiệp vụ. Ba mô hình thường được xem xét là:

- **Đám mây công cộng (public cloud):** tài nguyên và dịch vụ do nhà cung cấp cloud phục vụ nhiều khách hàng qua một nền tảng chung, với cơ chế cách ly tài nguyên phù hợp.
- **Đám mây riêng (private cloud):** môi trường cloud được dành riêng cho một tổ chức; có thể đặt tại trung tâm dữ liệu của chính tổ chức hoặc do bên thứ ba vận hành.
- **Đám mây lai (hybrid cloud):** kết hợp các môi trường cloud khác loại, điển hình là private cloud với public cloud, bằng kết nối và cơ chế tích hợp cho phép chúng phối hợp hoặc dịch chuyển dữ liệu/workload theo nhu cầu.

Đây là **mô hình triển khai**, không phải cấp độ dịch vụ. Trong mỗi mô hình, tổ chức còn phải cân nhắc cách cung cấp dịch vụ như IaaS, PaaS, container platform hoặc SaaS. "Chọn public cloud" không tự động có nghĩa "dùng serverless"; "chọn private cloud" cũng không bắt buộc phải tự vận hành toàn bộ từng máy ảo.

Trong module **CLOUD_ARCHITECTURE**, quyết định này là cầu nối giữa yêu cầu nghiệp vụ với lựa chọn mạng, compute, dữ liệu và phương án triển khai. Mọi lựa chọn cần giải thích được đánh đổi về **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành**, rồi kiểm chứng bằng tư duy Well-Architected.

**Ví dụ xuyên suốt:** doanh nghiệp cung cấp dịch vụ đặt chỗ có website phục vụ khách hàng ở nhiều vùng; hệ thống kế toán và một số dữ liệu giao dịch đang nằm trong trung tâm dữ liệu riêng. Vào kỳ nghỉ, truy vấn tìm kiếm tăng mạnh; hoạt động xác nhận đặt chỗ và thanh toán lại đòi hỏi tính đúng đắn, khả năng khôi phục và kiểm soát truy cập. Các con số trong bài chỉ là **giả định học tập**; dự án thực phải thay bằng dữ liệu đo được và yêu cầu đã phê duyệt.

## 2. Hiểu đúng ba mô hình và các khái niệm dễ nhầm

### 2.1. Public cloud

Public cloud cung cấp năng lực xử lý, lưu trữ, mạng và dịch vụ quản lý theo cách tiêu thụ linh hoạt. Hạ tầng có thể được nhiều khách hàng cùng sử dụng ở cấp vật lý nhưng mỗi khách hàng được quản lý bằng các cơ chế cách ly, danh tính, quyền và mạng riêng logic.

Điểm mạnh thường thấy là có thể cấp phát tài nguyên nhanh, tiếp cận dịch vụ quản lý đa dạng, phân phối đến nhiều khu vực và tránh phải mua trước toàn bộ phần cứng. Đổi lại, tổ chức phải thiết kế cấu hình an toàn, quản trị giới hạn dịch vụ, dữ liệu, chi phí sử dụng và phụ thuộc vào nhà cung cấp.

**Lưu ý:** "public" mô tả cách cung cấp hạ tầng, **không có nghĩa dữ liệu của mọi khách hàng đều được truy cập công khai**. Một cơ sở dữ liệu triển khai trên public cloud vẫn có thể chỉ truy cập qua mạng riêng, được mã hóa và chỉ cho phép tài khoản có quyền.

### 2.2. Private cloud

Private cloud dành tài nguyên cloud cho một tổ chức và có khả năng cung cấp dịch vụ theo cách cloud như tự phục vụ, tự động hóa cấp phát, đo lường mức dùng và quản lý tài nguyên tập trung. Nó có thể được xây dựng trên hạ tầng do doanh nghiệp sở hữu, trong trung tâm dữ liệu thuê chỗ đặt, hoặc được một nhà cung cấp vận hành riêng.

Đặc tính quan trọng là **mức kiểm soát và tính dành riêng của môi trường**; không thể suy ra rằng mọi private cloud đều dùng phần cứng đặt tại trụ sở. Ngược lại, một cụm máy chủ ảo hóa nội bộ thiếu khả năng tự phục vụ, tự động hóa và quản lý tài nguyên theo kiểu cloud thì nên gọi là hạ tầng on-premises hoặc môi trường ảo hóa, thay vì mặc nhiên coi là private cloud hoàn chỉnh.

Private cloud cho phép kiểm soát sâu nền tảng và lịch thay đổi, nhưng phải có năng lực duy trì phần cứng, điện, mạng, cập nhật, dự phòng, giám sát, bảo mật và kế hoạch mở rộng. **Dành riêng không đồng nghĩa tự động an toàn hoặc luôn sẵn sàng hơn.**

### 2.3. Hybrid cloud

Hybrid cloud kết nối những môi trường khác loại và thống nhất một số luồng xử lý, dữ liệu hoặc quy trình vận hành để mỗi workload được đặt nơi phù hợp. Có thể đặt frontend và tìm kiếm trên public cloud, trong khi dữ liệu trọng yếu và hệ thống chuyên dụng ở private cloud; hoặc đặt tài nguyên dự phòng/khôi phục ở môi trường còn lại.

Hybrid không chỉ là "có một đường VPN". Cần làm rõ **dịch vụ nào giao tiếp với nhau, dữ liệu nào được đồng bộ, mô hình xác thực nào được dùng, mức chịu lỗi của kết nối và cách vận hành thống nhất**. Một hệ thống có ứng dụng public cloud gọi thẳng vào cơ sở dữ liệu riêng qua đường truyền xa có thể mang tên hybrid nhưng hiệu năng và độ tin cậy rất kém.

### 2.4. Hybrid, on-premises và multi-cloud khác nhau thế nào?

| Thuật ngữ | Ý nghĩa | Điểm cần tránh nhầm |
| --- | --- | --- |
| **On-premises** | Hạ tầng đặt trong cơ sở của tổ chức | Không tự động là private cloud; còn tùy mô hình cung cấp và vận hành |
| **Hosted private cloud** | Môi trường cloud dành riêng, được lưu trú/vận hành bởi bên ngoài | Vẫn thuộc private cloud nếu đáp ứng đặc tính dành riêng và cách cung cấp cloud |
| **Hybrid cloud** | Tích hợp các môi trường cloud khác loại, thường private + public | Cần có kiến trúc dữ liệu, kết nối, danh tính và vận hành liên thông |
| **Hybrid IT** | Thuật ngữ rộng cho việc đồng thời dùng hệ thống truyền thống on-premises và cloud | Không phải mọi hệ thống on-prem đều đã trở thành private cloud |
| **Multi-cloud** | Dùng dịch vụ từ hơn một nhà cung cấp cloud | Có thể chỉ gồm hai public cloud; không nhất thiết là hybrid cloud |
| **Dedicated host trên public cloud** | Tài nguyên máy chủ vật lý dành riêng cho một khách hàng trong dịch vụ cloud công cộng | Không đủ để kết luận toàn bộ môi trường là private cloud |

## 3. So sánh ở cấp độ quyết định

| Tiêu chí | Public cloud | Private cloud | Hybrid cloud |
| --- | --- | --- | --- |
| **Khởi tạo và mở rộng** | Thường nhanh nếu dịch vụ và quota sẵn có; vẫn bị giới hạn bởi kiến trúc và hạn mức | Phụ thuộc công suất đã mua và chu kỳ cấp phát/bổ sung hạ tầng | Mở rộng linh hoạt ở một số phần, bị giới hạn ở các điểm tích hợp |
| **Quyền kiểm soát hạ tầng** | Khách hàng kiểm soát cấu hình và workload trong phạm vi dịch vụ; nhà cung cấp kiểm soát nhiều lớp hạ tầng | Có thể kiểm soát sâu phần cứng, mạng và lịch thay đổi | Mức kiểm soát khác nhau theo từng môi trường; cần chuẩn hóa chính sách |
| **Dữ liệu và tuân thủ** | Phụ thuộc khu vực cung cấp dịch vụ, hợp đồng, cấu hình và nghĩa vụ cụ thể | Có thể chủ động hơn với vị trí vật lý và thiết bị, nhưng phải tự chứng minh kiểm soát | Có thể giữ một nhóm dữ liệu tại nơi bắt buộc; luồng đồng bộ qua môi trường làm tăng việc cần đánh giá |
| **Chi phí** | Thường nghiêng về chi phí sử dụng, dễ thử nhanh; có biến động bởi lưu lượng, lưu trữ và truyền dữ liệu | Có chi phí đầu tư/thuê và vận hành công suất; hiệu quả phụ thuộc mức sử dụng | Cộng chi phí các môi trường và chi phí kết nối, tích hợp, quản trị |
| **Độ tin cậy** | Có nhiều dịch vụ và công cụ dự phòng; phải chủ động kiến trúc phân tán và kiểm thử | Có thể tối ưu theo nhu cầu riêng; chất lượng dự phòng phụ thuộc vốn và vận hành | Có thêm phương án phân bố lỗi, đồng thời thêm điểm lỗi liên kết và phụ thuộc xuyên môi trường |
| **Bảo mật** | Mô hình trách nhiệm chia sẻ; cần cấu hình đúng IAM, network, logging, key | Kiểm soát riêng nhiều lớp nhưng tự gánh thêm trách nhiệm vá lỗi, vật lý và vận hành | Diện tấn công và vòng đời danh tính mở rộng qua nhiều môi trường |
| **Vận hành** | Có nhiều dịch vụ được quản lý, song cần kỹ năng cloud, IaC và FinOps | Cần đội ngũ hạ tầng, vận hành nền tảng, lập kế hoạch công suất | Cần năng lực cả hai phía và giám sát, thay đổi, sự cố xuyên ranh giới |
| **Độ trễ** | Tốt khi đặt dịch vụ gần người dùng/nguồn dữ liệu | Có lợi khi sát hệ thống nội bộ, nhà máy hoặc thiết bị chuyên dụng | Nhạy cảm với khoảng cách, kết nối liên môi trường và lưu lượng đồng bộ |

Bảng trên mô tả xu hướng, **không phải xếp hạng cố định**. Public cloud được thiết kế tốt có thể đáp ứng yêu cầu tuân thủ khắt khe; private cloud cấu hình sai vẫn có thể bị xâm nhập và mất dữ liệu; hybrid cloud có thể tăng độ trễ nếu đặt hai phần trao đổi thường xuyên ở xa nhau.

## 4. Điều kiện thuận lợi để chọn public cloud

Public cloud thường là ứng viên tốt khi:

1. **Nhu cầu thay đổi hoặc chưa chắc chắn:** sản phẩm mới cần thử nghiệm nhanh, lưu lượng dao động theo giờ/mùa và không muốn mua trước toàn bộ công suất đỉnh.
2. **Mở rộng thị trường:** cần tiếp cận người dùng từ nhiều khu vực, triển khai môi trường thử nghiệm hoặc phục vụ các nhóm khách hàng ở các vị trí khác nhau.
3. **Đội ngũ muốn tập trung vào ứng dụng:** có thể tận dụng dịch vụ cơ sở dữ liệu, hàng đợi, giám sát, quản lý khóa và triển khai được quản lý để giảm một phần công việc hạ tầng.
4. **Có lựa chọn khu vực và dịch vụ đáp ứng yêu cầu dữ liệu:** các nghĩa vụ về vị trí dữ liệu, hợp đồng, quyền truy cập, lưu giữ và kiểm toán đã được xác minh cụ thể.
5. **Có khả năng quản trị mức dùng:** nhóm có ngân sách, cảnh báo chi phí, dự báo truyền dữ liệu và cơ chế kiểm soát tài nguyên.

Ví dụ với dịch vụ đặt chỗ: phần tìm kiếm, hiển thị danh mục, tạo ảnh thu nhỏ, phân phối nội dung và môi trường thử nghiệm có thể phù hợp với public cloud, nhất là khi lượng truy vấn tăng bất thường. Tuy nhiên, cần kiểm tra điểm nghẽn cơ sở dữ liệu, hạn mức hệ thống thanh toán, chi phí dữ liệu truyền ra và khả năng đảm bảo trạng thái giao dịch.

### Khi nào cần thận trọng?

- Workload phụ thuộc thiết bị chuyên dụng hoặc hệ thống nội bộ có yêu cầu độ trễ cực thấp.
- Dữ liệu bị ràng buộc vị trí hoặc hình thức kiểm soát mà dịch vụ/khu vực public cloud đang xét **chưa được xác minh** đáp ứng.
- Tải rất ổn định, lâu dài và lớn: cần đối chiếu tổng chi phí nhiều năm thay vì giả định public luôn rẻ.
- Ứng dụng dùng nhiều tính năng đặc thù nhà cung cấp và có yêu cầu chuyển đổi nghiêm ngặt: cần đánh giá lock-in ở cấp API, dữ liệu, vận hành và chi phí di chuyển.
- Bộ phận phụ trách không đủ năng lực quản trị IAM, mạng, cấu hình, quota, triển khai hoặc chi phí cloud.

**Sai lầm phổ biến:** chọn public cloud vì thấy dịch vụ có nhãn "multi-AZ", "auto scaling" hoặc "managed" rồi coi như đã đạt SLO. Cần xác định kiến trúc ứng dụng, chiến lược sao lưu, phụ thuộc vào dịch vụ khác và bằng chứng kiểm thử.

## 5. Điều kiện thuận lợi để chọn private cloud

Private cloud thường đáng cân nhắc khi có ít nhất một nhu cầu đủ mạnh và đội ngũ đủ năng lực vận hành:

1. **Quyền kiểm soát chuyên sâu:** cần tùy biến nền tảng, lựa chọn thiết bị/phần cứng hoặc điều khiển lịch nâng cấp mà dịch vụ public không phù hợp.
2. **Ràng buộc vật lý hoặc tích hợp tại chỗ:** dữ liệu và xử lý phải ở gần thiết bị sản xuất, hệ thống điều khiển, kho lưu trữ chuyên dụng hoặc các phụ thuộc nội bộ khó di chuyển.
3. **Yêu cầu vị trí/cách quản lý dữ liệu đã được xác nhận:** đánh giá pháp lý và kỹ thuật cho thấy giải pháp private đáp ứng yêu cầu bắt buộc tốt hơn các ứng viên khác.
4. **Đã có đầu tư hạ tầng hiệu quả:** hệ thống có mức tải ổn định, công suất còn đủ, và tổng chi phí vòng đời thực sự cạnh tranh sau khi cộng bảo trì, dự phòng, nhân sự, điện, làm mát và thay thế thiết bị.
5. **Đội ngũ vận hành trưởng thành:** có tự động hóa cấp phát, quản trị danh tính, vá lỗi, giám sát, quản lý thay đổi, backup và thực hành diễn tập sự cố.

Ví dụ: một phần mềm phân tích dữ liệu vận hành nhà máy cần tiếp nhận tín hiệu từ thiết bị tại chỗ với độ trễ nghiêm ngặt. Chạy một số xử lý sát thiết bị trên hạ tầng riêng có thể hợp lý hơn việc truyền tất cả dữ liệu ra xa qua Internet. Quyết định vẫn phải xét khả năng chịu lỗi và giải pháp phân tích dữ liệu tổng hợp sau đó.

### Điều gì khiến private cloud không phù hợp?

Nếu phải mua mới toàn bộ hệ thống để phục vụ tải đỉnh rất hiếm gặp, chi phí đầu tư có thể cao và công suất dư bị lãng phí. Nếu đội ngũ thiếu kỹ năng vận hành nền tảng, lợi thế kiểm soát sẽ chuyển thành rủi ro bảo mật, khả dụng và kéo dài thời gian khôi phục.

**Một trung tâm dữ liệu duy nhất không tạo ra khả năng phục hồi sau thảm họa.** Nếu nghiệp vụ yêu cầu chịu được mất cả site, phải có môi trường độc lập đủ xa, dữ liệu dự phòng phù hợp, kịch bản chuyển đổi và diễn tập RTO/RPO; mô hình private không tự giải quyết điều này.

## 6. Điều kiện thuận lợi để chọn hybrid cloud

Hybrid cloud hữu ích khi các nhóm workload có yêu cầu khác nhau và **giá trị của việc chia môi trường lớn hơn chi phí tích hợp**. Các tình huống thường gặp:

- **Hiện đại hóa theo giai đoạn:** giữ tạm hệ thống lõi khó di chuyển ở private cloud, xây API hoặc dịch vụ mới trên public cloud, giảm rủi ro thay đổi đồng loạt.
- **Tách dữ liệu có ràng buộc:** giữ một số dữ liệu hoặc xử lý ở môi trường riêng; chỉ chuyển tập dữ liệu/đầu ra được phép sang public cloud cho các tác vụ bổ sung.
- **Tách hệ thống gần thiết bị với tác vụ phân tích:** xử lý thời gian thực tại nơi tạo dữ liệu, đồng bộ dữ liệu tổng hợp lên cloud cho phân tích theo lô.
- **Dùng công suất linh hoạt cho phần có thể mở rộng độc lập:** ví dụ tác vụ render hoặc xử lý batch đã đóng gói và có phương án di chuyển dữ liệu hợp lý.
- **Đáp ứng kế hoạch chuyển đổi hoặc khôi phục:** sử dụng một môi trường khác cho lưu trữ bản sao hoặc tài nguyên phục hồi nếu các yêu cầu thời gian, an toàn dữ liệu và quy trình vận hành cho phép.

Hybrid **không tự động cung cấp mở rộng vô hạn hay failover tức thời**. Một workload chỉ có thể "burst" sang môi trường khác nếu ứng dụng, dữ liệu, kết nối, giấy phép, danh tính và cơ chế định tuyến đã sẵn sàng. Không nên mặc định sao chép cơ sở dữ liệu đang giao dịch qua kết nối xa sẽ không làm tăng độ trễ hoặc có thể giữ trạng thái nhất quán.

### Kiến trúc tham khảo: ứng dụng đặt chỗ lai

~~~mermaid
flowchart TB
    U[Khách hàng] --> E[CDN / Web / API public cloud]
    subgraph PUB[Public cloud]
        E --> S[Dịch vụ tìm kiếm và danh mục]
        E --> B[Ứng dụng đặt chỗ]
        S --> C[(Bản sao dữ liệu đọc / chỉ mục)]
        B --> G[Adapter tích hợp có xác thực]
        O[Log / metric / trace đã kiểm soát dữ liệu]
    end
    subgraph CONN[Kết nối liên môi trường]
        G --> L[Private connectivity hoặc VPN có giám sát]
    end
    subgraph PRI[Private cloud]
        L --> I[API nghiệp vụ nội bộ]
        I --> D[(Nguồn dữ liệu giao dịch)]
        I --> P[Hệ thống kế toán / đối soát]
    end
    B -. đo hành trình .-> O
    I -. đo phụ thuộc .-> O
~~~

Sơ đồ là **một phương án cần đánh giá**, không phải thiết kế chuẩn duy nhất. Nếu mọi thao tác đặt chỗ đều phải chờ API nội bộ qua kết nối xa, ứng dụng public cloud vẫn phụ thuộc chặt vào private cloud. Nhóm phải định nghĩa hành vi khi đường truyền mất kết nối, mức độ lỗi chấp nhận được, giới hạn retry và cách đối soát.

### Năm câu hỏi phải trả lời trước khi quyết định hybrid

1. **Độ trễ:** một yêu cầu người dùng cần bao nhiêu lượt gọi liên môi trường? p95/p99 của tổng hành trình có đạt ngưỡng không?
2. **Dữ liệu:** đâu là nguồn sự thật (*source of truth*)? Những trường nào được sao chép? Pháp lý có cho phép truyền dữ liệu đó qua môi trường/vùng khác không?
3. **Nhất quán:** dữ liệu đọc có thể chậm bao nhiêu? Giao dịch ghi cần atomicity, idempotency, ordering và đối soát như thế nào?
4. **Sự cố:** nếu mất VPN/private link hoặc một bên ngừng hoạt động, hành trình nào còn phục vụ được? RTO/RPO có đạt không?
5. **Vận hành:** ai giám sát đường kết nối, quản trị tài khoản liên kết, cập nhật chứng chỉ, truy vết một request từ đầu đến cuối và xử lý sự cố?

### Các mô hình tích hợp thường gặp

| Cách tích hợp | Phù hợp khi | Rủi ro cần kiểm tra |
| --- | --- | --- |
| API đồng bộ qua kết nối riêng/VPN | Giao dịch cần trả kết quả ngay, tần suất hợp lý | Độ trễ chồng tầng, timeout, circuit breaker, lỗi dây chuyền |
| Hàng đợi/sự kiện bất đồng bộ | Có thể xử lý trễ, cần tách nhịp hệ thống | Thông điệp trùng/lạc thứ tự, replay, đối soát, giám sát backlog |
| Sao chép dữ liệu đọc có kiểm soát | Truy vấn nhiều, dữ liệu chịu được độ trễ cập nhật | Độ mới dữ liệu, bảo vệ PII, xóa dữ liệu và quyền truy cập |
| Batch theo lịch | Phân tích, báo cáo, lưu trữ dữ liệu ít nhạy thời gian | Khối lượng truyền, cửa sổ đồng bộ, truy vết dữ liệu |
| Dự phòng/khôi phục khác môi trường | Có yêu cầu DR và đường khôi phục được thiết kế trước | Khả năng phục hồi thật, phụ thuộc DNS/IAM, chi phí standby, thời gian đồng bộ |

## 7. Quy trình ra quyết định: từ yêu cầu đến mô hình phù hợp

Không nên bắt đầu bằng bảng "public 8 điểm, private 7 điểm" khi chưa biết ràng buộc nào là bắt buộc. Quy trình nên chia thành hai tầng.

### Tầng A — Loại phương án không đáp ứng điều kiện bắt buộc

Trước hết, lập danh sách các ràng buộc có **chứng cứ và chủ sở hữu phê duyệt**:

- Dữ liệu phải được xử lý/lưu trữ tại vị trí nào? Định nghĩa "lưu trữ" có bao gồm backup, log, ảnh chụp hệ thống, dữ liệu hỗ trợ và DR không?
- Có loại hình phần cứng, giấy phép, kết nối tới thiết bị tại chỗ hoặc tiêu chuẩn kiểm toán bắt buộc nào không?
- Tốc độ trao đổi với hệ thống hiện hữu giới hạn bao nhiêu mili giây? Phụ thuộc có thể tái thiết kế không?
- Ngân sách và thời hạn ra mắt là ngưỡng cứng hay mục tiêu có thể điều chỉnh?
- Phương án có đủ năng lực vận hành, hỗ trợ, khôi phục và thẩm quyền xử lý sự cố không?

Nếu một phương án không thể đáp ứng điều kiện bắt buộc, **không cho nó thắng bằng điểm cao ở các tiêu chí khác**. Ví dụ, nếu dữ liệu phải đặt trong một khu vực được chỉ định mà nhà cung cấp chưa có vị trí triển khai thích hợp và không có giải pháp được phê duyệt, public cloud của nhà cung cấp đó không phải phương án hợp lệ cho phần dữ liệu ấy. Điều này **không loại mọi dịch vụ public cloud** và không có nghĩa chỉ private cloud mới đáp ứng tuân thủ; phải đánh giá sản phẩm, vị trí và nghĩa vụ cụ thể.

### Tầng B — Chấm các đánh đổi của phương án còn hợp lệ

Giả sử cả ba phương án đều vượt tầng A cho một ứng dụng đặt chỗ có tải tìm kiếm thay đổi theo mùa và có phụ thuộc giao dịch ở site riêng. Bảng sau là **điểm minh họa do nhóm dự án giả định**, thang 1–5 (5 = đáp ứng tốt hơn). Không dùng điểm này như chân lý chung.

| Tiêu chí | Trọng số (%) | Public | Private | Hybrid |
| --- | ---: | ---: | ---: | ---: |
| Đáp ứng yêu cầu dữ liệu/kiểm soát đã xác nhận | 25 | 3 | 5 | 5 |
| Khả năng phục vụ tải biến động | 20 | 5 | 2 | 4 |
| Độ trễ khi tích hợp hệ thống lõi | 20 | 2 | 5 | 4 |
| Đạt mục tiêu tin cậy và phục hồi | 15 | 5 | 3 | 4 |
| Tổng chi phí vòng đời phù hợp ngân sách | 10 | 4 | 2 | 3 |
| Năng lực đội ngũ vận hành hiện tại | 10 | 4 | 2 | 2 |
| **Tổng điểm có trọng số / 500** | **100** | **370** | **350** | **395** |

**Cách tính:** tổng = Σ(trọng số × điểm), tối đa 500. Ví dụ hybrid: 25 × 5 + 20 × 4 + 20 × 4 + 15 × 4 + 10 × 3 + 10 × 2 = **395**. Có thể quy đổi thành 79/100, nhưng sự chính xác của kết luận phụ thuộc vào căn cứ đặt điểm và trọng số.

**Diễn giải đúng:** hybrid tạm dẫn đầu theo giả định này, nhưng cũng có điểm vận hành thấp và nhiều rủi ro kết nối. Nếu thực nghiệm cho thấy độ trễ đường truyền lớn hoặc chi phí vận hành vượt ngân sách, phải chấm lại hoặc thay đổi cách phân chia workload. Nếu đội ngũ muốn đơn giản hóa, có thể cân nhắc đưa toàn bộ phần liên quan chặt vào một môi trường, rồi tách chỉ những phần tương tác lỏng.

### Ma trận quyết định phải đi kèm bằng chứng

| Nội dung cần lưu | Câu hỏi kiểm chứng |
| --- | --- |
| Nguồn của từng trọng số | Ai coi dữ liệu, độ trễ, chi phí là quan trọng nhất và vì sao? |
| Nguồn của từng điểm | Báo giá, benchmark, yêu cầu pháp lý hay chỉ là ước đoán? |
| Tình huống đỉnh và lỗi | Khi tăng tải/mất mạng/mất site thì mô hình hoạt động thế nào? |
| Độ nhạy của kết luận | Nếu tăng trọng số chi phí hoặc giảm điểm vận hành hybrid thì thứ hạng có đổi không? |
| Chi phí chuyển đổi | Migrate dữ liệu, đào tạo, tổ chức vận hành và rút lui khỏi phương án tốn gì? |

Mục đích của ma trận là **làm rõ giả định và tranh luận**, không dùng một tổng điểm để thay thế quyết định kỹ thuật, an toàn và nghiệp vụ.

## 8. Không chọn một mô hình duy nhất cho mọi workload

Một doanh nghiệp có thể chọn public cloud cho phần lớn hệ thống, private cloud cho một nhóm nhỏ và dùng tích hợp lai chỉ ở những luồng cần thiết. Để phân bố workload, hãy lập hồ sơ từng thành phần:

| Workload | Câu hỏi cần thu thập | Xu hướng bố trí cần xác minh |
| --- | --- | --- |
| Web frontend, ảnh và nội dung tĩnh | Người dùng ở đâu? Có cần phân phối toàn cầu? | Public cloud/CDN có thể thuận lợi; vẫn phải kiểm tra bảo mật và ngân sách |
| Tìm kiếm, đọc danh mục | Tải đỉnh bao nhiêu? Chấp nhận dữ liệu chậm cập nhật không? | Public với chỉ mục/bản sao đọc có thể hợp lý nếu chính sách dữ liệu cho phép |
| Ghi đặt chỗ và thanh toán | Nguồn sự thật nằm đâu? Yêu cầu nhất quán, RTO/RPO và chống giao dịch trùng? | Đặt gần hệ dữ liệu ghi và tích hợp thanh toán; không quyết định chỉ theo độ nổi tiếng nền tảng |
| Tài chính/kế toán hiện hữu | Khả năng di chuyển, giấy phép, giao diện và lịch thay đổi ra sao? | Có thể giữ tại private trong giai đoạn chuyển đổi nếu di chuyển rủi ro cao |
| Phân tích theo lô | Dữ liệu nào được phép chuyển? Kích thước và chu kỳ bao nhiêu? | Có thể dùng công suất public linh hoạt nếu chi phí truyền và kiểm soát dữ liệu phù hợp |
| Quan sát hệ thống và audit | Log chứa gì? Ai được xem? Phải lưu bao lâu? | Thu thập tập trung có kiểm soát, phân vùng dữ liệu nhạy cảm và thời hạn lưu |
| Backup và DR | RPO/RTO? Cần khác site/vùng hay khác nhà cung cấp? | Chọn vị trí độc lập phù hợp; kiểm tra khả năng restore và các phụ thuộc |

**Nguyên tắc thực hành:** đặt những thành phần phải giao dịch đồng bộ thường xuyên **gần nhau về mạng và dữ liệu** khi khả thi; tách phần chỉ cần phản hồi bất đồng bộ, cache hoặc bản sao đọc khi đã làm rõ độ mới dữ liệu. Không phân tán theo sơ đồ tổ chức nếu làm tăng số cuộc gọi qua ranh giới mạng và tạo chuỗi lỗi khó quan sát.

## 9. Những trục đánh đổi cần tính xuyên suốt

### 9.1. Bảo mật, quyền riêng tư và trách nhiệm chia sẻ

Trên public cloud, nhà cung cấp chịu trách nhiệm cho phần hạ tầng thuộc dịch vụ họ cung cấp; khách hàng vẫn có trách nhiệm với dữ liệu, cấu hình truy cập, ứng dụng, danh tính và nhiều phần vận hành tùy loại dịch vụ. Với private cloud, tổ chức hoặc bên vận hành theo hợp đồng phải gánh thêm phần hạ tầng. Với hybrid, cần **xác định trách nhiệm ở từng đầu của đường kết nối và ở nơi dữ liệu được sao chép**.

Các kiểm soát phải xem xét bất kể mô hình: IAM với quyền tối thiểu, xác thực mạnh cho vai trò nhạy cảm, mã hóa khi truyền và khi lưu phù hợp, quản lý khóa và bí mật, phân đoạn mạng, hardening, logging/audit, quản lý lỗ hổng, backup và quy trình ứng phó sự cố.

Chỉ ra những dữ liệu có tính nhạy cảm, vị trí xử lý, cơ chế chuyển dữ liệu, người truy cập và thời hạn lưu. **"Dùng private cloud" không đủ để khẳng định đạt quy định pháp luật**; tương tự, vị trí region public cloud không phải toàn bộ câu chuyện khi log, backup, hỗ trợ hoặc sao chép vẫn có thể đi nơi khác. Cần đối chiếu nghĩa vụ cụ thể với cấu hình và hợp đồng thực tế.

### 9.2. Hiệu năng, mạng và data gravity

Khi lượng dữ liệu lớn và tần suất gọi qua mạng cao, **data gravity** khiến việc chuyển compute lại gần dữ liệu có thể hợp lý hơn việc chuyển dữ liệu qua mỗi lượt xử lý. Ước lượng ít nhất:

- Kích thước dữ liệu cần chuyển lần đầu, lượng thay đổi mỗi ngày và tốc độ băng thông thực đạt.
- Độ trễ **p95/p99** của kết nối giữa các thành phần; tổng số lượt gọi đồng bộ trong một giao dịch.
- Tốc độ truyền, chi phí dữ liệu ra và khả năng bảo vệ kết nối trước gián đoạn.
- Cách hoạt động khi mạng chậm, mất gói hoặc gián đoạn một chiều: timeout, retry có giới hạn, circuit breaker và hàng đợi.

Ví dụ: API đặt chỗ gọi 5 lần liên tiếp đến hệ thống private, mỗi lần có thêm 40 ms độ trễ mạng. Chỉ phần độ trễ mạng đã tăng khoảng 200 ms trên đường đi tuần tự, chưa tính thời gian ứng dụng, TLS, xử lý DB và độ biến thiên. Đây là phép tính minh họa, không phải độ trễ cố định của hybrid; phải đo tại đúng địa điểm triển khai.

### 9.3. Độ tin cậy và khôi phục thảm họa

Hai môi trường có thể loại bỏ một điểm lỗi, nhưng cũng thêm phụ thuộc. Vẽ **dependency map** cho từng hành trình người dùng; đo khả dụng theo hành trình, không chỉ theo tình trạng máy chủ.

Phải trả lời được: nếu mất một availability zone, một site, một đường kết nối hoặc hệ thống danh tính trung tâm thì điều gì ngừng hoạt động? Có đường truy cập dự phòng, DNS/định tuyến phù hợp, sao lưu còn truy cập được và người vận hành biết chuyển sang chế độ phục hồi không? Mục tiêu **RTO** là thời gian phục hồi, **RPO** là mức mất dữ liệu theo thời gian; cả hai cần được kiểm chứng bằng diễn tập cho đúng kịch bản mất mát.

### 9.4. Chi phí tổng thể (TCO) và chi phí vận hành

Không nên so giá thuê một máy ảo với giá mua một máy chủ rồi kết luận. Mô hình chi phí nhiều năm phải gồm các nhóm phù hợp:

~~~text
TCO vòng đời =
  compute + storage + network + truyền dữ liệu
  + phần cứng/thuê chỗ đặt + điện + làm mát (nếu có)
  + giấy phép + vận hành + hỗ trợ + bảo mật
  + backup/DR + observability + kết nối liên môi trường
  + chi phí di chuyển/đào tạo/chuyển đổi
~~~

Với public cloud, theo dõi tải trung bình/đỉnh, tài nguyên nhàn rỗi, lưu trữ tăng trưởng, retention log, egress, phí dịch vụ được quản lý và mức chi phí của cấu hình dự phòng. Với private cloud, tính khấu hao/thay thế phần cứng, công suất dư, duy trì hai site, nhân sự và vòng đời cập nhật. Với hybrid, cộng thêm liên kết chuyên dụng/VPN, dịch vụ mạng, công cụ vận hành trùng lặp và chi phí thay đổi hợp đồng.

Đánh giá ít nhất ba kịch bản **thường ngày / cao điểm / sự cố hoặc mở rộng**; đặt ngân sách và cảnh báo tương ứng. Chi phí dự kiến phải được rà soát sau khi có số liệu chạy thử, không coi bảng giá công bố là toàn bộ chi phí.

### 9.5. Năng lực vận hành và khả năng thay đổi

Đội ngũ có thể triển khai bằng IaC, quản trị secret, quan sát end-to-end, xử lý incident, vá lỗi và chạy DR drill chưa? Hybrid có thể yêu cầu đồng thời chuyên môn network on-prem, cloud networking, hệ quản trị định danh, database replication và SRE. Nếu năng lực chưa đủ, phương án kiến trúc càng phân tán càng khó vận hành.

Phải xây quy trình thay đổi cấu hình, cấp quyền, triển khai/rollback, phát hiện lỗi và phân công trực. Mô hình có nhiều thành phần sẽ cần một kế hoạch quản trị phiên bản tương thích giữa các môi trường, tránh tình trạng ứng dụng được nâng cấp trước nhưng API nội bộ chưa hỗ trợ.

## 10. Một kịch bản thực hành từ yêu cầu đến quyết định

**Bối cảnh:** nền tảng đặt chỗ đang chạy on-premises, có nhu cầu phục vụ nhiều người dùng hơn trong mùa cao điểm. Dữ liệu giao dịch hiện ở hệ thống kế toán nội bộ; nhóm muốn hiện đại hóa phần giao diện và tìm kiếm trước.

**Yêu cầu giả định để phỏng vấn và xác nhận:**

| Mã | Phát biểu yêu cầu | Cách xác nhận |
| --- | --- | --- |
| FR-01 | Khách tìm và đặt chỗ; hệ thống không xác nhận trùng một phòng theo quy tắc nghiệp vụ | Kiểm thử tranh chấp đồng thời và idempotency |
| QR-01 | p95 thời gian phản hồi API tìm kiếm ≤ 800 ms ở mức 200 request/giây | Thử tải với bộ dữ liệu và điểm đo đã thống nhất |
| QR-02 | Hành trình tra cứu đạt SLO 99,95% mỗi tháng | SLI theo yêu cầu hợp lệ và cửa sổ đo được phê duyệt |
| QR-03 | Khi mất site chính, mục tiêu RTO ≤ 2 giờ và RPO ≤ 15 phút cho dữ liệu đặt chỗ | Diễn tập khôi phục và đo timestamp dữ liệu |
| SEC-01 | Dữ liệu nhạy cảm chỉ đi qua luồng đã được phê duyệt và truy cập theo vai trò | Sơ đồ luồng dữ liệu, kiểm thử quyền, đánh giá bảo mật |
| FIN-01 | Chi phí trong ngân sách theo ba mức tải đã duyệt | Dự toán TCO, kiểm tra log, network, backup, DR, nhân sự |

### Ba phương án ứng viên

**Phương án A — Chủ yếu public cloud:** chuyển phần lớn ứng dụng và dữ liệu sang môi trường cloud được quản lý. Ưu thế là giảm số điểm tích hợp liên môi trường và dễ cấp phát tài nguyên. Việc chuyển hệ giao dịch quan trọng phải giải quyết khả năng di chuyển, tính nhất quán, hợp đồng và nghĩa vụ dữ liệu; nếu không, A có thể không khả thi trong giai đoạn đầu.

**Phương án B — Chủ yếu private cloud:** hiện đại hóa nền tảng tại cơ sở riêng, tối ưu kết nối với hệ thống lõi. Ưu thế là giảm thay đổi trên những giao dịch sát dữ liệu nội bộ. Hạn chế có thể là thời gian mở rộng công suất và chi phí đáp ứng tải đỉnh.

**Phương án C — Hybrid cloud có ranh giới rõ:** đặt frontend/tìm kiếm ở public, giữ giao dịch cốt lõi tại private trong giai đoạn đầu; tích hợp qua API có xác thực, đồng bộ chỉ mục đọc theo quy định. Ưu thế là triển khai từng bước; thách thức là kết nối, độ trễ, dữ liệu đồng bộ và vận hành xuyên môi trường.

Kết quả hợp lý **chưa phải tuyên bố C luôn thắng**. Nhóm cần đo API trong tình huống thực, thử mất kết nối, đánh giá mức độ dữ liệu được phép chuyển, ước lượng TCO và chứng minh RTO/RPO. Nếu kết nối liên môi trường không đạt độ trễ hoặc thiếu năng lực vận hành, có thể phải đặt thêm phần xử lý gần dữ liệu nguồn, tối ưu giao tiếp bất đồng bộ hoặc thay đổi kế hoạch di chuyển.

### Quyết định kiến trúc minh họa (ADR rút gọn)

~~~text
ADR-01: Tách tìm kiếm sang public cloud trong giai đoạn 1

Bối cảnh:
- Tìm kiếm có tải cao điểm; hệ thống giao dịch đang ổn định ở môi trường riêng.
- Chưa có bằng chứng đủ chắc để di chuyển dữ liệu giao dịch.

Quyết định dự kiến:
- Thử nghiệm public cloud cho frontend và đọc tìm kiếm.
- Giữ ghi giao dịch tại môi trường riêng trong giai đoạn đầu.
- Đồng bộ dữ liệu đọc được phép, dùng API tích hợp có xác thực.

Điều kiện chấp thuận:
- Đạt QR-01 qua load test và thử mất kết nối.
- Dữ liệu đồng bộ tuân thủ chính sách đã xác nhận.
- Hoàn tất diễn tập khôi phục cho FR-01 và QR-03.
- TCO theo kịch bản nằm trong ngân sách đã duyệt.

Đánh đổi:
- Tăng khả năng mở rộng phần đọc và giảm rủi ro di chuyển đồng loạt.
- Thêm vận hành hybrid, yêu cầu observability và đối soát dữ liệu.

Xem lại khi:
- Phụ thuộc giao dịch trở thành điểm nghẽn;
- tăng chi phí kết nối hoặc vượt mức độ trễ;
- hoàn thành kế hoạch chuyển dữ liệu lõi.
~~~

## 11. Triển khai quyết định theo từng bước có kiểm chứng

Sau khi chọn hướng đi, tránh di chuyển toàn bộ chỉ dựa vào một slide kiến trúc. Các bước thực hiện có thể là:

1. **Phân loại workload và dữ liệu:** vẽ dependency map, nguồn dữ liệu, luồng người dùng, vùng triển khai, vị trí backup/log và hệ thống bên thứ ba.
2. **Ghi rõ tiêu chí chấp nhận:** latency ở tải đỉnh, SLO cho hành trình, RTO/RPO theo sự cố, bảo mật/tuân thủ, ngân sách và khả năng vận hành.
3. **Lập kiến trúc mạng và danh tính:** IP/DNS, phân đoạn, route, kết nối private/VPN nếu có, xác thực liên môi trường, chứng chỉ và xử lý khi kết nối gián đoạn.
4. **Thiết kế dữ liệu:** hệ thống nguồn, tính nhất quán, phân loại dữ liệu, phục hồi, phương án đồng bộ/đối soát và cách thu hồi/xóa bản sao.
5. **Làm proof of concept đúng điểm rủi ro:** ưu tiên thử kết nối xuyên môi trường, thời gian đồng bộ, tính nhất quán, phương án failover và chi phí dưới tải thực.
6. **Thiết lập vận hành:** IaC, giám sát theo hành trình, tracing, cảnh báo, runbook, phân quyền, kiểm tra cấu hình và owner cho mỗi thành phần.
7. **Di chuyển theo nhóm nhỏ có đường lùi:** làm rõ rollback dữ liệu, chuyển lưu lượng có kiểm soát, đo SLI, đánh giá bảo mật và phê duyệt trước khi mở rộng.
8. **Đánh giá lại theo Well-Architected:** dựa trên số đo và sự cố, rà soát vận hành, bảo mật, độ tin cậy, hiệu năng, chi phí và hiệu quả dùng tài nguyên.

Đặc biệt, **khôi phục không chỉ là có backup**. Một kế hoạch DR cần quy trình có thể thực hiện được, người chịu trách nhiệm, quyền truy cập khi môi trường chính hỏng, thời gian DNS/chuyển kết nối, dữ liệu cuối cùng được khôi phục và phương pháp kiểm tra tính toàn vẹn.

## 12. Bài thực hành: chọn mô hình cho ba workload

Hãy đóng vai kiến trúc sư của một tổ chức có:

- Website có tải tăng gấp 8 trong các chiến dịch ngắn.
- Hệ thống kiểm soát máy móc trong nhà máy yêu cầu đáp ứng thời gian thực và hiện nằm tại site.
- Dữ liệu phân tích dài hạn có dung lượng lớn; một phần chứa thông tin nhạy cảm.

**Nhiệm vụ:**

1. Viết ít nhất **sáu yêu cầu** có thể đo (độ trễ, độ tin cậy, RTO/RPO, lưu lượng, giới hạn dữ liệu, ngân sách) và đánh dấu giả định nào chưa có chứng cứ.
2. Xác định ràng buộc loại trừ phương án, nhất là vị trí dữ liệu và phụ thuộc vào thiết bị tại chỗ.
3. Lập ma trận đặt workload trên public/private/hybrid, giải thích các đường trao đổi dữ liệu và người chịu trách nhiệm vận hành.
4. Tạo ma trận trọng số nhưng **không** dùng điểm số để bỏ qua ràng buộc bắt buộc. Thử thay đổi hai trọng số để xem kết luận có ổn định không.
5. Vẽ sơ đồ kiến trúc sơ bộ gồm mạng, compute, nguồn dữ liệu, khu vực lỗi và đường khôi phục; thử hai kịch bản **mất kết nối liên môi trường** và **mất site chính**.
6. Ghi ADR nêu lựa chọn, phương án đã xem xét, các đánh đổi còn lại và thử nghiệm phải vượt qua trước khi quyết định chính thức.

**Tiêu chí đạt:** người đọc có thể chỉ rõ **workload nào đặt ở đâu, vì sao, phụ thuộc điều gì, chi phí và rủi ro vận hành ra sao, thất bại trong tình huống nào và kiểm chứng như thế nào**.

## 13. Checklist ra quyết định trước khi chốt mô hình

- [ ] Đã phân biệt yêu cầu nghiệp vụ, yêu cầu chất lượng, ràng buộc và giả định.
- [ ] Đã phân loại dữ liệu và xác nhận nghĩa vụ pháp lý/hợp đồng cho region, backup, log và DR.
- [ ] Đã xác định nơi đặt nguồn dữ liệu ghi, tính nhất quán và khả năng di chuyển của từng workload.
- [ ] Đã đo hoặc lập thử nghiệm độ trễ và thông lượng trên những đường trao đổi quan trọng.
- [ ] Đã xác định điểm lỗi chung, phụ thuộc liên môi trường và hành vi khi mất kết nối.
- [ ] Đã có mục tiêu và kịch bản kiểm chứng SLO, RTO, RPO; không chỉ dựa vào quảng cáo dịch vụ.
- [ ] Đã tính TCO nhiều kịch bản, gồm chi phí vận hành, kết nối, truyền dữ liệu, backup và chuyển đổi.
- [ ] Đã kiểm tra kỹ năng đội ngũ, trách nhiệm giữa các bên và khả năng giám sát xuyên hệ thống.
- [ ] Đã ghi lại các phương án bị loại, điều kiện ưu tiên, ADR và thời điểm cần đánh giá lại.

**Điểm cốt lõi:** public, private và hybrid là các cách bố trí năng lực công nghệ để phục vụ yêu cầu. Kiến trúc tốt là kiến trúc chọn **đúng vị trí cho từng dữ liệu và workload**, đáp ứng các điều kiện bắt buộc, có bằng chứng về chất lượng và chấp nhận được chi phí cùng trách nhiệm vận hành trong suốt vòng đời hệ thống.
